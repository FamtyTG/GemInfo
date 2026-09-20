"""Обработчики событий Telegram (контроллеры слоя представления).

Класс ``BotHandlers`` связывает события Telegram (команды, нажатия кнопок,
текстовые сообщения) с экранами бота. Маршрутизация callback-кнопок задана
таблицей ``_callback_routes``: по одному методу на действие.

Важно: любой обработчик обёрнут декоратором ``safe_handler``, поэтому ни одна
ошибка — в Telegram, в базе данных или во внешних сервисах — не приводит к
аварийному завершению работы бота.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from gamehunter.domain.exceptions import GameHunterError
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.keyboards import Callback, CallbackAction
from gamehunter.presentation.screens import ScreenContainer
from gamehunter.presentation.state import ContextScreen, StateStorage, UserContext

logger = logging.getLogger(__name__)

# Типы сообщений, которые бот игнорирует (согласно ТЗ)
UNSUPPORTED_CONTENT_TYPES: List[str] = [
    "photo",
    "audio",
    "document",
    "video",
    "video_note",
    "sticker",
    "animation",
    "location",
    "venue",
    "contact",
    "dice",
    "poll",
]


def safe_handler(func: Callable) -> Callable:
    """Декоратор: перехватывает любые ошибки обработчика и пишет их в лог."""

    @functools.wraps(func)
    def wrapper(self: "BotHandlers", event: Any) -> None:
        try:
            func(self, event)
        except GameHunterError as exc:
            logger.error("Ожидаемая ошибка в обработчике %s: %s", func.__name__, exc)
            self.notify_error(event, exc.user_message)
        except Exception:  # noqa: BLE001 - бот обязан продолжить работу
            logger.exception("Непредвиденная ошибка в обработчике %s", func.__name__)
            self.notify_error(event, texts.GENERIC_ERROR)

    return wrapper


class BotHandlers:
    """Регистрация и обработка всех событий Telegram-бота."""

    def __init__(
        self,
        bot: TeleBot,
        gateway: TelegramGateway,
        storage: StateStorage,
        screens: ScreenContainer,
    ) -> None:
        self._bot = bot
        self._gateway = gateway
        self._storage = storage
        self._screens = screens
        self._callback_routes: Dict[str, Callable[[int, int, Callback], None]] = {
            CallbackAction.MAIN_MENU: self._route_main_menu,
            CallbackAction.PICK_GENRES: self._route_pick_genres,
            CallbackAction.TOGGLE_GENRE: self._route_toggle_genre,
            CallbackAction.PICK_SHOW: self._route_pick_show,
            CallbackAction.PICK_ALL: self._route_pick_all,
            CallbackAction.GAMES_PAGE: self._route_games_page,
            CallbackAction.GAME_CARD: self._route_game_card,
            CallbackAction.ADD_PLAYED: self._route_add_played,
            CallbackAction.TOGGLE_FAVORITE: self._route_toggle_favorite,
            CallbackAction.FRANCHISE_INPUT: self._route_franchise_input,
            CallbackAction.FRANCHISE_PICK: self._route_franchise_pick,
            CallbackAction.PROFILE: self._route_profile,
            CallbackAction.PROFILE_AGE: self._route_age_input,
            CallbackAction.PROFILE_AGE_RESET: self._route_age_reset,
            CallbackAction.PROFILE_GENRES: self._route_profile_genres,
            CallbackAction.TOGGLE_PROFILE_GENRE: self._route_toggle_profile_genre,
            CallbackAction.PROFILE_GENRES_DONE: self._route_profile_genres_done,
            CallbackAction.PROFILE_PLATFORMS: self._route_profile_platforms,
            CallbackAction.TOGGLE_PLATFORM: self._route_toggle_platform,
            CallbackAction.PROFILE_PLATFORMS_DONE: self._route_profile_platforms_done,
            CallbackAction.PROFILE_IP: self._route_ip_input,
            CallbackAction.PROFILE_IP_RESET: self._route_ip_reset,
            CallbackAction.PLAYED_PAGE: self._route_played_page,
            CallbackAction.PLAYED_ITEM: self._route_played_item,
            CallbackAction.REVIEW_INPUT: self._route_review_input,
            CallbackAction.DELETE_PLAYED: self._route_delete_played,
            CallbackAction.FAVORITES_PAGE: self._route_favorites_page,
            CallbackAction.BACK_GAMES: self._route_back_to_list,
        }

    # ------------------------------------------------------------------ #
    # Регистрация обработчиков
    # ------------------------------------------------------------------ #
    def register(self) -> None:
        """Регистрирует обработчики в объекте бота."""
        self._bot.message_handler(commands=["start"])(self.on_start)
        self._bot.callback_query_handler()(self.on_callback)
        self._bot.message_handler(content_types=["text"])(self.on_text)
        self._bot.message_handler(content_types=UNSUPPORTED_CONTENT_TYPES)(
            self.on_unsupported
        )
        logger.info("Обработчики Telegram зарегистрированы")

    # ------------------------------------------------------------------ #
    # Команда /start
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_start(self, message: Message) -> None:
        """Команда /start: первый запуск — Экран 1, иначе — главное меню."""
        chat_id, user_id = self._ids_of_message(message)
        if chat_id is None or user_id is None:
            return

        if not self._storage.has(user_id):
            # Пользователь открыл бота впервые — показываем приветственный экран
            self._storage.save(user_id, UserContext())
            self._screens.start.show(chat_id)
            return

        # /start всегда возвращает в главное меню, где бы пользователь ни был
        self._screens.main_menu.show(chat_id, user_id)

    # ------------------------------------------------------------------ #
    # Inline-кнопки
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_callback(self, call: CallbackQuery) -> None:
        """Обработка нажатий inline-кнопок."""
        chat_id, user_id = self._ids_of_callback(call)
        if chat_id is None or user_id is None:
            return

        # Убираем «часики» у нажатой кнопки
        self._gateway.answer_callback(call)

        callback = keyboards.parse_callback(call.data)
        if callback is None:
            logger.warning("Неизвестные callback-данные: %r", call.data)
            self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)
            return

        logger.debug(
            "Callback пользователя %s: action=%s value=%s",
            user_id,
            callback.action,
            callback.value,
        )

        route = self._callback_routes.get(callback.action)
        if route is None:
            logger.warning("Неподдерживаемое действие кнопки: %s", callback.action)
            self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)
            return

        route(chat_id, user_id, callback)

    # ------------------------------------------------------------------ #
    # Маршруты callback-кнопок
    # ------------------------------------------------------------------ #
    def _route_main_menu(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.main_menu.show(chat_id, user_id)

    def _route_pick_genres(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.genre_picking.show(chat_id, user_id)

    def _route_toggle_genre(self, chat_id: int, user_id: int, callback: Callback) -> None:
        if not callback.value:
            self._unknown_button(chat_id, callback)
            return
        self._screens.genre_picking.toggle(chat_id, user_id, callback.value)

    def _route_pick_show(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.genre_picking.show_selection(chat_id, user_id)

    def _route_pick_all(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.genre_picking.show_all(chat_id, user_id)

    def _route_games_page(self, chat_id: int, user_id: int, callback: Callback) -> None:
        page = callback.int_value or 1
        self._screens.game_list.show(chat_id, user_id, page=page)

    def _route_game_card(self, chat_id: int, user_id: int, callback: Callback) -> None:
        game_id = callback.int_value
        if game_id is None:
            self._unknown_button(chat_id, callback)
            return
        context = self._storage.get_or_default(user_id)
        self._screens.game_card.show(
            chat_id, user_id, game_id, source=context.screen
        )

    def _route_add_played(self, chat_id: int, user_id: int, callback: Callback) -> None:
        game_id = callback.int_value
        if game_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.game_card.add_to_played(chat_id, user_id, game_id)

    def _route_toggle_favorite(self, chat_id: int, user_id: int, callback: Callback) -> None:
        game_id = callback.int_value
        if game_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.game_card.toggle_favorite(chat_id, user_id, game_id)

    def _route_franchise_input(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.franchise_input.show(chat_id, user_id)

    def _route_franchise_pick(self, chat_id: int, user_id: int, callback: Callback) -> None:
        index = callback.int_value
        if index is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.franchise_games.show(chat_id, user_id, index)

    def _route_profile(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.profile.show(chat_id, user_id)

    def _route_age_input(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.age_input.show(chat_id, user_id)

    def _route_age_reset(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.profile.reset_age(chat_id, user_id)

    def _route_profile_genres(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.profile_genres.show(chat_id, user_id)

    def _route_toggle_profile_genre(
        self, chat_id: int, user_id: int, callback: Callback
    ) -> None:
        if not callback.value:
            self._unknown_button(chat_id, callback)
            return
        self._screens.profile_genres.toggle(chat_id, user_id, callback.value)

    def _route_profile_genres_done(
        self, chat_id: int, user_id: int, callback: Callback
    ) -> None:
        self._screens.profile_genres.save_selection(chat_id, user_id)

    def _route_profile_platforms(
        self, chat_id: int, user_id: int, callback: Callback
    ) -> None:
        self._screens.profile_platforms.show(chat_id, user_id)

    def _route_toggle_platform(self, chat_id: int, user_id: int, callback: Callback) -> None:
        platform_id = callback.int_value
        if platform_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.profile_platforms.toggle(chat_id, user_id, platform_id)

    def _route_profile_platforms_done(
        self, chat_id: int, user_id: int, callback: Callback
    ) -> None:
        self._screens.profile_platforms.save_selection(chat_id, user_id)

    def _route_ip_input(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.region_input.show(chat_id, user_id)

    def _route_ip_reset(self, chat_id: int, user_id: int, callback: Callback) -> None:
        self._screens.profile.reset_region(chat_id, user_id)

    def _route_played_page(self, chat_id: int, user_id: int, callback: Callback) -> None:
        page = callback.int_value or 1
        self._screens.played_list.show(chat_id, user_id, page=page)

    def _route_played_item(self, chat_id: int, user_id: int, callback: Callback) -> None:
        record_id = callback.int_value
        if record_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.played_info.show(chat_id, user_id, record_id)

    def _route_review_input(self, chat_id: int, user_id: int, callback: Callback) -> None:
        record_id = callback.int_value
        if record_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.review_input.show(chat_id, user_id, record_id)

    def _route_delete_played(self, chat_id: int, user_id: int, callback: Callback) -> None:
        record_id = callback.int_value
        if record_id is None:
            self._unknown_button(chat_id, callback)
            return
        self._screens.played_info.delete(chat_id, user_id, record_id)

    def _route_favorites_page(self, chat_id: int, user_id: int, callback: Callback) -> None:
        page = callback.int_value or 1
        self._screens.favorites.show(chat_id, user_id, page=page)

    def _route_back_to_list(self, chat_id: int, user_id: int, callback: Callback) -> None:
        """Кнопка «Назад» в карточке игры — возврат к списку, из которого пришли."""
        context = self._storage.get_or_default(user_id)

        if context.list_source == ContextScreen.FRANCHISE_GAMES:
            self._screens.franchise_games.rerender(chat_id, user_id)
        elif context.list_source == ContextScreen.FAVORITES_LIST:
            self._screens.favorites.show(chat_id, user_id, page=context.games_page)
        elif context.games:
            self._screens.game_list.rerender(chat_id, user_id)
        else:
            self._screens.main_menu.show(chat_id, user_id)

    # ------------------------------------------------------------------ #
    # Текстовые сообщения
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_text(self, message: Message) -> None:
        """Текст пользователя: кнопка меню, название франшизы, возраст, IP или отзыв."""
        chat_id, user_id = self._ids_of_message(message)
        if chat_id is None or user_id is None:
            return

        text = (message.text or "").strip()
        context = self._storage.get(user_id)

        if context is None:
            # Пользователь написал боту первым — показываем Экран 1
            self._storage.save(user_id, UserContext())
            self._screens.start.show(chat_id)
            return

        if context.screen.is_waiting_for_text():
            self._handle_text_input(chat_id, user_id, context.screen, text)
            return

        if text in keyboards.MENU_BUTTON_TEXTS:
            self._handle_menu_button(chat_id, user_id, text)
            return

        # В любом другом состоянии обычный текст не распознаётся
        logger.debug("Нераспознанный текст от пользователя %s: %r", user_id, text[:50])
        self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)

    # ------------------------------------------------------------------ #
    # Неподдерживаемые сообщения (фото, файлы, голосовые и т.п.)
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_unsupported(self, message: Message) -> None:
        """Согласно ТЗ бот игнорирует сообщения неподдерживаемых типов."""
        logger.debug(
            "Проигнорировано сообщение типа %s от пользователя %s",
            getattr(message, "content_type", "?"),
            getattr(getattr(message, "from_user", None), "id", "?"),
        )

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _handle_text_input(
        self, chat_id: int, user_id: int, screen: ContextScreen, text: str
    ) -> None:
        """Передаёт введённый текст на экран, который его ожидает."""
        if screen == ContextScreen.FRANCHISE_INPUT:
            self._screens.franchise_input.search(chat_id, user_id, text)
        elif screen == ContextScreen.AGE_INPUT:
            self._screens.age_input.handle_age(chat_id, user_id, text)
        elif screen == ContextScreen.IP_INPUT:
            self._screens.region_input.handle_ip(chat_id, user_id, text)
        elif screen == ContextScreen.REVIEW_INPUT:
            self._screens.review_input.handle_review(chat_id, user_id, text)
        else:  # pragma: no cover - защищаемся от рассогласования состояний
            logger.warning("Экран %s не ожидает текстовый ввод", screen)
            self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)

    def _handle_menu_button(self, chat_id: int, user_id: int, text: str) -> None:
        """Обрабатывает нажатие кнопки reply-клавиатуры главного меню."""
        if text == keyboards.ButtonText.START:
            self._screens.main_menu.show(chat_id, user_id)
        elif text == keyboards.ButtonText.PICK:
            self._screens.genre_picking.show(chat_id, user_id)
        elif text == keyboards.ButtonText.FRANCHISE:
            self._screens.franchise_input.show(chat_id, user_id)
        elif text == keyboards.ButtonText.PROFILE:
            self._screens.profile.show(chat_id, user_id)
        elif text == keyboards.ButtonText.PLAYED:
            self._screens.played_list.show(chat_id, user_id, page=1)
        elif text == keyboards.ButtonText.FAVORITES:
            self._screens.favorites.show(chat_id, user_id, page=1)

    def _unknown_button(self, chat_id: int, callback: Callback) -> None:
        """Кнопка пришла без значения (например, из устаревшего сообщения)."""
        logger.warning("Кнопка %s нажата без значения", callback.action)
        self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)

    def notify_error(self, event: Any, message: str) -> None:
        """Показывает пользователю сообщение об ошибке (если это возможно)."""
        try:
            chat_id = self._chat_id_of(event)
            if chat_id is not None:
                self._gateway.send_text(
                    chat_id, message, reply_markup=keyboards.back_to_menu_keyboard()
                )
        except Exception:  # noqa: BLE001 - главное не «уронить» бота
            logger.debug("Не удалось отправить сообщение об ошибке пользователю")

    @staticmethod
    def _chat_id_of(event: Any) -> Optional[int]:
        """Определяет чат, в который нужно отправить сообщение об ошибке."""
        # CallbackQuery хранит чат внутри event.message, Message — в event.chat
        if isinstance(event, CallbackQuery) or hasattr(event, "message"):
            chat_id, _ = BotHandlers._ids_of_callback(event)
            if chat_id is not None:
                return chat_id
        chat_id, _ = BotHandlers._ids_of_message(event)
        return chat_id

    @staticmethod
    def _ids_of_message(message: Optional[Message]) -> Tuple[Optional[int], Optional[int]]:
        """Возвращает (chat_id, user_id) для обычного сообщения."""
        if message is None:
            return None, None
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        user_id = getattr(getattr(message, "from_user", None), "id", None)
        return chat_id, user_id

    @staticmethod
    def _ids_of_callback(call: Optional[CallbackQuery]) -> Tuple[Optional[int], Optional[int]]:
        """Возвращает (chat_id, user_id) для нажатия inline-кнопки."""
        if call is None:
            return None, None
        user_id = getattr(getattr(call, "from_user", None), "id", None)
        inner_message = getattr(call, "message", None)
        chat_id = getattr(getattr(inner_message, "chat", None), "id", None)
        return chat_id, user_id
