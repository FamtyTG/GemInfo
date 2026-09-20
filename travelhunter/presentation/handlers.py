"""Обработчики событий Telegram (контроллеры слоя представления).

Класс ``BotHandlers`` связывает события Telegram (команды, кнопки, текст)
с экранами бота и сервисами бизнес-логики.

Важно: любой обработчик обёрнут в перехват ошибок, поэтому ни одна ошибка —
в Telegram, в базе данных или во внешних сервисах — не приводит к аварийному
завершению работы бота.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, List, Optional

from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from travelhunter.domain.exceptions import CityNotFoundError, TravelHunterError
from travelhunter.domain.services import CityService
from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.screens import ScreenContainer
from travelhunter.presentation.state import Screen, StateStorage, UserContext

logger = logging.getLogger(__name__)

# Типы сообщений, которые бот игнорирует (согласно ТЗ)
UNSUPPORTED_CONTENT_TYPES: List[str] = [
    "photo",
    "audio",
    "document",
    "video",
    "voice",
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
        except TravelHunterError as exc:
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
        city_service: CityService,
    ) -> None:
        self._bot = bot
        self._gateway = gateway
        self._storage = storage
        self._screens = screens
        self._city_service = city_service

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

        action = callback.action
        if action == keyboards.CallbackAction.MAIN_MENU:
            self._screens.main_menu.show(chat_id, user_id)
        elif action == keyboards.CallbackAction.HOLIDAYS:
            self._screens.holidays.show(chat_id, user_id)
        elif action == keyboards.CallbackAction.CITY_INPUT:
            self._screens.city_input.show(chat_id, user_id)
        elif action == keyboards.CallbackAction.SELECT_CITY:
            self._screens.city_info.show(chat_id, user_id, callback.value or 0)
        elif action == keyboards.CallbackAction.HISTORY:
            self._screens.history.show(chat_id, user_id, page=callback.value or 1)
        elif action == keyboards.CallbackAction.TRIP:
            self._screens.trip_info.show(chat_id, user_id, callback.value or 0)
        elif action == keyboards.CallbackAction.NOTE:
            self._screens.note_input.show(chat_id, user_id, callback.value or 0)
        else:
            logger.warning("Неподдерживаемое действие кнопки: %s", action)
            self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)

    # ------------------------------------------------------------------ #
    # Текстовые сообщения
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_text(self, message: Message) -> None:
        """Текст пользователя: кнопка меню, название города или заметка."""
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

        if context.screen == Screen.WAITING_NOTE:
            # Экран 9: текст воспринимается как заметка к поездке
            self._screens.note_input.save(chat_id, user_id, text)
            return

        if text in keyboards.MENU_BUTTON_TEXTS:
            self._handle_menu_button(chat_id, user_id, text)
            return

        if context.screen == Screen.WAITING_CITY_NAME:
            # Экран 4: текст воспринимается как название города
            self._process_city_input(chat_id, user_id, text)
            return

        # В любом другом состоянии обычный текст не распознаётся
        self._gateway.send_text(chat_id, texts.UNKNOWN_COMMAND)

    # ------------------------------------------------------------------ #
    # Неподдерживаемые сообщения (фото, файлы, голосовые и т.п.)
    # ------------------------------------------------------------------ #
    @safe_handler
    def on_unsupported(self, message: Message) -> None:
        """Согласно ТЗ бот игнорирует сообщения неподдерживаемых типов."""
        logger.debug(
            "Проигнорировано сообщение типа %s от пользователя %s",
            message.content_type,
            getattr(getattr(message, "from_user", None), "id", "?"),
        )

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _handle_menu_button(self, chat_id: int, user_id: int, text: str) -> None:
        """Обрабатывает нажатие кнопки reply-клавиатуры главного меню."""
        if text == keyboards.ButtonText.START:
            self._screens.main_menu.show(chat_id, user_id)
        elif text == keyboards.ButtonText.HOLIDAYS:
            self._screens.holidays.show(chat_id, user_id)
        elif text == keyboards.ButtonText.CITIES:
            self._screens.city_input.show(chat_id, user_id)
        elif text == keyboards.ButtonText.HISTORY:
            self._screens.history.show(chat_id, user_id, page=1)

    def _process_city_input(self, chat_id: int, user_id: int, raw_text: str) -> None:
        """Экран 4 -> 5: проверка города и переход к списку ближайших."""
        context = self._storage.get(user_id) or UserContext()

        # Поиск города — это запрос к внешнему API: предупреждаем, что он идёт
        self._gateway.send_text(chat_id, texts.CITY_SEARCHING)

        try:
            city = self._city_service.find_city(raw_text)
        except CityNotFoundError as exc:
            # Город не найден — показываем ошибку и ждём повторного ввода
            logger.info("Город «%s» не найден (пользователь %s)", raw_text, user_id)
            self._screens.city_input.show(chat_id, user_id, error_text=exc.user_message)
            return
        except TravelHunterError as exc:
            logger.error("Ошибка поиска города «%s»: %s", raw_text, exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        self._storage.save(user_id, context.with_current_city(city))
        self._screens.nearby_cities.show(chat_id, user_id)

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
    def _ids_of_message(message: Optional[Message]) -> tuple[Optional[int], Optional[int]]:
        """Возвращает (chat_id, user_id) для обычного сообщения."""
        if message is None:
            return None, None
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        user_id = getattr(getattr(message, "from_user", None), "id", None)
        return chat_id, user_id

    @staticmethod
    def _ids_of_callback(call: Optional[CallbackQuery]) -> tuple[Optional[int], Optional[int]]:
        """Возвращает (chat_id, user_id) для нажатия inline-кнопки."""
        if call is None:
            return None, None
        user_id = getattr(getattr(call, "from_user", None), "id", None)
        inner_message = getattr(call, "message", None)
        chat_id = getattr(getattr(inner_message, "chat", None), "id", None)
        return chat_id, user_id
