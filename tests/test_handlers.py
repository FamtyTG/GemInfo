"""Тесты обработчиков событий Telegram."""

from __future__ import annotations

import pytest

from gamehunter.domain.exceptions import DatabaseError, GamesUnavailableError
from gamehunter.presentation import texts
from gamehunter.presentation.handlers import UNSUPPORTED_CONTENT_TYPES, BotHandlers, safe_handler
from gamehunter.presentation.keyboards import ButtonText, CallbackAction
from gamehunter.presentation.state import ContextScreen, UserContext
from tests.fakes import make_callback, make_game, make_message

CHAT_ID = 100
USER_ID = 200


@pytest.fixture()
def started(handlers, storage) -> BotHandlers:
    """Пользователь уже открыл бота (состояние сохранено)."""
    storage.save(USER_ID, UserContext())
    return handlers


# ---------------------------------------------------------------------- #
# Регистрация обработчиков
# ---------------------------------------------------------------------- #
class TestRegister:
    def test_registers_handlers(self, handlers: BotHandlers, bot):
        handlers.register()

        assert bot.message_handlers
        assert bot.callback_query_handlers

    def test_registers_start_command(self, handlers: BotHandlers, bot):
        handlers.register()

        commands = [
            command
            for handler in bot.message_handlers
            for command in (handler.get("filters") or {}).get("commands", [])
        ]

        assert "start" in commands

    def test_registers_text_handler(self, handlers: BotHandlers, bot):
        handlers.register()

        content_types = [
            content_type
            for handler in bot.message_handlers
            for content_type in (handler.get("filters") or {}).get("content_types", [])
        ]

        assert "text" in content_types

    def test_registers_callback_handler(self, handlers: BotHandlers, bot):
        handlers.register()

        assert len(bot.callback_query_handlers) == 1

    def test_registers_unsupported_content_types(self, handlers: BotHandlers, bot):
        handlers.register()

        content_types = [
            content_type
            for handler in bot.message_handlers
            for content_type in (handler.get("filters") or {}).get("content_types", [])
        ]

        for expected in UNSUPPORTED_CONTENT_TYPES:
            assert expected in content_types

    def test_all_callback_actions_are_routed(self, handlers: BotHandlers):
        actions = {
            value
            for name, value in vars(CallbackAction).items()
            if not name.startswith("_") and isinstance(value, str)
        }

        assert actions == set(handlers._callback_routes)  # noqa: SLF001 - проверка полноты


# ---------------------------------------------------------------------- #
# Команда /start
# ---------------------------------------------------------------------- #
class TestStart:
    def test_first_launch_shows_start_screen(self, handlers: BotHandlers, gateway, storage):
        handlers.on_start(make_message("/start"))

        assert texts.START_WELCOME in gateway.last_text
        assert storage.has(USER_ID) is True

    def test_second_launch_shows_main_menu(self, started: BotHandlers, gateway):
        started.on_start(make_message("/start"))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text

    def test_start_resets_context(self, started: BotHandlers, gateway, storage):
        storage.save(USER_ID, UserContext().at_game_card(32))

        started.on_start(make_message("/start"))

        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_message_without_chat_is_ignored(self, handlers: BotHandlers, gateway):
        handlers.on_start(make_message("/start"))  # обычный случай
        gateway.clear()

        broken = make_message("/start")
        broken.chat = None
        handlers.on_start(broken)

        assert gateway.events == []

    def test_message_without_user_is_ignored(self, handlers: BotHandlers, gateway):
        message = make_message("/start")
        message.from_user = None

        handlers.on_start(message)

        assert gateway.events == []


# ---------------------------------------------------------------------- #
# Inline-кнопки
# ---------------------------------------------------------------------- #
class TestCallbacks:
    def test_answers_callback(self, started: BotHandlers, gateway):
        started.on_callback(make_callback(CallbackAction.MAIN_MENU))

        assert gateway.answered_callbacks == 1

    def test_main_menu(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.MAIN_MENU))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_pick_genres(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PICK_GENRES))

        assert texts.GENRES_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PICKING_GENRES

    def test_toggle_genre(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PICK_GENRES))
        started.on_callback(make_callback("g:action"))

        assert "✔ Action" in gateway.last_text
        assert storage.get(USER_ID).picked_genres == ("action",)

    def test_toggle_genre_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("g:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_pick_show(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PICK_GENRES))
        started.on_callback(make_callback("g:action"))
        started.on_callback(make_callback(CallbackAction.PICK_SHOW))

        assert storage.get(USER_ID).screen == ContextScreen.GAME_LIST

    def test_pick_all(self, started: BotHandlers, gateway, storage, games_provider):
        started.on_callback(make_callback(CallbackAction.PICK_GENRES))
        started.on_callback(make_callback("g:action"))
        started.on_callback(make_callback(CallbackAction.PICK_ALL))

        assert storage.get(USER_ID).picked_genres == ()
        assert games_provider.search_calls[-1].genres == ()

    def test_games_page(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PICK_ALL))
        started.on_callback(make_callback("games:2"))

        assert storage.get(USER_ID).games_page == 2
        assert "Страница 2 из 3" in gateway.last_text

    def test_games_page_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("games:"))

        assert texts.UNKNOWN_COMMAND not in gateway.last_text  # страница по умолчанию — 1

    def test_game_card(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PICK_ALL))
        started.on_callback(make_callback("game:32"))

        assert storage.get(USER_ID).screen == ContextScreen.GAME_CARD
        assert texts.GAME_CARD_TITLE in gateway.last_text

    def test_game_card_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("game:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_add_played(self, started: BotHandlers, gateway, library_service):
        started.on_callback(make_callback(CallbackAction.PICK_ALL))
        started.on_callback(make_callback("played:32"))

        assert library_service.is_played(USER_ID, 32) is True

    def test_toggle_favorite(self, started: BotHandlers, gateway, library_service):
        started.on_callback(make_callback(CallbackAction.PICK_ALL))
        started.on_callback(make_callback("fav:32"))

        assert library_service.is_favorite(USER_ID, 32) is True

        started.on_callback(make_callback("fav:32"))

        assert library_service.is_favorite(USER_ID, 32) is False

    def test_franchise_input(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.FRANCHISE_INPUT))

        assert texts.FRANCHISE_INPUT_PROMPT in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_INPUT

    def test_franchise_pick(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.FRANCHISE_INPUT))
        started.on_text(make_message("Marvel"))
        started.on_callback(make_callback("frs:1"))

        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_GAMES

    def test_franchise_pick_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("frs:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_profile(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE))

        assert texts.PROFILE_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE

    def test_age_input(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE_AGE))

        assert texts.PROFILE_AGE_PROMPT in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.AGE_INPUT

    def test_age_reset(self, started: BotHandlers, gateway, profile_service):
        profile_service.set_age(USER_ID, "27")
        started.on_callback(make_callback(CallbackAction.PROFILE_AGE_RESET))

        assert profile_service.get_profile(USER_ID).age is None

    def test_profile_genres(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE_GENRES))

        assert texts.PROFILE_GENRES_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE_GENRES

    def test_profile_genre_toggle_and_save(self, started: BotHandlers, gateway, profile_service):
        started.on_callback(make_callback(CallbackAction.PROFILE_GENRES))
        started.on_callback(make_callback("pg:action"))
        started.on_callback(make_callback(CallbackAction.PROFILE_GENRES_DONE))

        assert profile_service.get_profile(USER_ID).genre_slugs == ("action",)
        assert texts.PROFILE_GENRES_SAVED in gateway.last_text

    def test_profile_genre_toggle_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("pg:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_profile_platforms(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE_PLATFORMS))

        assert texts.PROFILE_PLATFORMS_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE_PLATFORMS

    def test_platform_toggle_and_save(self, started: BotHandlers, gateway, profile_service):
        started.on_callback(make_callback(CallbackAction.PROFILE_PLATFORMS))
        started.on_callback(make_callback("pl:1"))
        started.on_callback(make_callback("pl:3"))
        started.on_callback(make_callback(CallbackAction.PROFILE_PLATFORMS_DONE))

        assert profile_service.get_profile(USER_ID).platform_ids == (1, 3)

    def test_platform_toggle_without_value(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("pl:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_ip_input(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE_IP))

        assert "2ip.ru" in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.IP_INPUT

    def test_ip_reset(self, started: BotHandlers, gateway, profile_service):
        profile_service.set_region_by_ip(USER_ID, "8.8.8.8")
        started.on_callback(make_callback(CallbackAction.PROFILE_IP_RESET))

        assert profile_service.get_profile(USER_ID).region is None

    def test_played_page(self, started: BotHandlers, gateway, library_service, storage):
        for index in range(5):
            library_service.add_played(USER_ID, make_game(100 + index, f"Игра {index}"))

        started.on_callback(make_callback("lib:2"))

        assert storage.get(USER_ID).library_page == 2

    def test_played_item(self, started: BotHandlers, gateway, library_service, storage):
        record = library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        started.on_callback(make_callback(f"rec:{record.id}"))

        assert texts.PLAYED_INFO_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PLAYED_INFO

    def test_review_input(self, started: BotHandlers, gateway, library_service):
        record = library_service.add_played(USER_ID, make_game(32))

        started.on_callback(make_callback(f"rev:{record.id}"))

        assert texts.REVIEW_PROMPT in gateway.last_text

    def test_delete_played(self, started: BotHandlers, gateway, library_service):
        record = library_service.add_played(USER_ID, make_game(32))

        started.on_callback(make_callback(f"del:{record.id}"))

        assert library_service.played_game_ids(USER_ID) == set()

    def test_favorites_page(self, started: BotHandlers, gateway, library_service, storage):
        for index in range(5):
            library_service.add_favorite(USER_ID, make_game(100 + index, f"Игра {index}"))

        started.on_callback(make_callback("favs:2"))

        assert storage.get(USER_ID).screen == ContextScreen.FAVORITES_LIST
        assert storage.get(USER_ID).games_page == 2

    def test_unknown_action(self, started: BotHandlers, gateway):
        started.on_callback(make_callback("что-то-непонятное"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_empty_callback_data(self, started: BotHandlers, gateway):
        started.on_callback(make_callback(""))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_callback_without_chat(self, started: BotHandlers, gateway):
        call = make_callback(CallbackAction.MAIN_MENU)
        call.message = None

        started.on_callback(call)

        assert gateway.events == []

    def test_callback_without_user(self, started: BotHandlers, gateway):
        call = make_callback(CallbackAction.MAIN_MENU)
        call.from_user = None

        started.on_callback(call)

        assert gateway.events == []


class TestBackToList:
    def test_back_from_picked_games(self, started: BotHandlers, gateway, games_provider, storage):
        started.on_callback(make_callback(CallbackAction.PICK_ALL))
        searches = len(games_provider.search_calls)
        started.on_callback(make_callback("game:32"))
        gateway.clear()

        started.on_callback(make_callback(CallbackAction.BACK_GAMES))

        assert texts.GAMES_TITLE in gateway.last_text
        assert len(games_provider.search_calls) == searches  # список показан из памяти

    def test_back_from_franchise_games(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.FRANCHISE_INPUT))
        started.on_text(make_message("Marvel"))
        started.on_callback(make_callback("frs:1"))
        started.on_callback(make_callback("game:9001"))
        gateway.clear()

        started.on_callback(make_callback(CallbackAction.BACK_GAMES))

        assert "Игры франшизы Marvel:" in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_GAMES

    def test_back_from_favorites(self, started: BotHandlers, gateway, library_service, storage):
        library_service.add_favorite(USER_ID, make_game(41494, "Cyberpunk 2077"))
        started.on_callback(make_callback("favs:1"))
        started.on_callback(make_callback("game:41494"))
        gateway.clear()

        started.on_callback(make_callback(CallbackAction.BACK_GAMES))

        assert texts.FAVORITES_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.FAVORITES_LIST

    def test_back_without_list(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.BACK_GAMES))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


# ---------------------------------------------------------------------- #
# Текстовые сообщения
# ---------------------------------------------------------------------- #
class TestTextMessages:
    def test_first_message_shows_start_screen(self, handlers: BotHandlers, gateway, storage):
        handlers.on_text(make_message("Привет"))

        assert texts.START_WELCOME in gateway.last_text
        assert storage.has(USER_ID) is True

    @pytest.mark.parametrize(
        "text, expected_screen, expected_text",
        [
            (ButtonText.START, ContextScreen.MAIN_MENU, texts.MAIN_MENU_WELCOME),
            (ButtonText.PICK, ContextScreen.PICKING_GENRES, texts.GENRES_TITLE),
            (ButtonText.FRANCHISE, ContextScreen.FRANCHISE_INPUT, texts.FRANCHISE_INPUT_PROMPT),
            (ButtonText.PROFILE, ContextScreen.PROFILE, texts.PROFILE_TITLE),
        ],
    )
    def test_menu_buttons(self, started: BotHandlers, gateway, storage, text, expected_screen, expected_text):
        started.on_text(make_message(text))

        assert expected_text in gateway.last_text
        assert storage.get(USER_ID).screen == expected_screen

    def test_played_menu_button(self, started: BotHandlers, gateway, storage):
        started.on_text(make_message(ButtonText.PLAYED))

        assert texts.PLAYED_EMPTY in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PLAYED_LIST

    def test_favorites_menu_button(self, started: BotHandlers, gateway, storage):
        started.on_text(make_message(ButtonText.FAVORITES))

        assert texts.FAVORITES_EMPTY in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.FAVORITES_LIST

    def test_unknown_text(self, started: BotHandlers, gateway):
        started.on_text(make_message("расскажи joke"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_franchise_input(self, started: BotHandlers, gateway, storage):
        started.on_text(make_message(ButtonText.FRANCHISE))
        gateway.clear()

        started.on_text(make_message("Star Wars"))

        assert texts.FRANCHISES_TITLE in gateway.last_text or "не найдена" in gateway.last_text
        assert storage.get(USER_ID).screen in (
            ContextScreen.FRANCHISE_LIST,
            ContextScreen.FRANCHISE_INPUT,
        )

    def test_age_input(self, started: BotHandlers, gateway, profile_service):
        started.on_text(make_message(ButtonText.PROFILE))
        started.on_callback(make_callback(CallbackAction.PROFILE_AGE))
        gateway.clear()

        started.on_text(make_message("27"))

        assert profile_service.get_profile(USER_ID).age == 27
        assert texts.PROFILE_AGE_SAVED in gateway.last_text

    def test_ip_input(self, started: BotHandlers, gateway, profile_service):
        started.on_callback(make_callback(CallbackAction.PROFILE_IP))
        gateway.clear()

        started.on_text(make_message("8.8.8.8"))

        assert profile_service.get_profile(USER_ID).region is not None
        assert texts.PROFILE_REGION_SAVED in gateway.last_text

    def test_review_input(self, started: BotHandlers, gateway, library_service):
        record = library_service.add_played(USER_ID, make_game(32))
        started.on_callback(make_callback(f"rev:{record.id}"))
        gateway.clear()

        started.on_text(make_message("Отличная игра!"))

        assert library_service.get_played(USER_ID, record.id).review == "Отличная игра!"
        assert texts.REVIEW_SAVED in gateway.last_text

    def test_text_on_button_screen_is_not_consumed(self, started: BotHandlers, gateway, storage):
        started.on_callback(make_callback(CallbackAction.PROFILE))
        gateway.clear()

        started.on_text(make_message("случайный текст"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE

    def test_message_without_ids(self, started: BotHandlers, gateway):
        message = make_message("текст")
        message.chat = None

        started.on_text(message)

        assert gateway.events == []


class TestUnsupportedMessages:
    @pytest.mark.parametrize("content_type", ["photo", "voice", "sticker", "location"])
    def test_ignored(self, started: BotHandlers, gateway, content_type):
        started.on_unsupported(make_message("", content_type=content_type))

        assert gateway.events == []

    def test_broken_message_is_ignored(self, started: BotHandlers, gateway):
        started.on_unsupported(object())

        assert gateway.events == []


# ---------------------------------------------------------------------- #
# Устойчивость к ошибкам
# ---------------------------------------------------------------------- #
class TestErrorHandling:
    def test_domain_error_is_shown_to_user(self, started: BotHandlers, gateway, games_provider):
        games_provider.errors["genres"] = GamesUnavailableError("rawg", "timeout")

        started.on_callback(make_callback(CallbackAction.PICK_GENRES))

        assert GamesUnavailableError.user_message in gateway.last_text

    def test_unexpected_error_does_not_crash_bot(self, started: BotHandlers, gateway, screens, monkeypatch):
        def boom(*args, **kwargs):
            raise ZeroDivisionError("внутренний сбой")

        monkeypatch.setattr(screens.genre_picking, "show", boom)

        started.on_callback(make_callback(CallbackAction.PICK_GENRES))

        assert texts.GENERIC_ERROR in gateway.last_text

    def test_service_error_is_converted_by_domain(self, started: BotHandlers, gateway, games_provider):
        # Непредвиденная ошибка в клиенте каталога становится доменной
        games_provider.errors["search"] = ZeroDivisionError("внутренний сбой")

        started.on_callback(make_callback(CallbackAction.PICK_ALL))

        assert GamesUnavailableError.user_message in gateway.last_text

    def test_bot_continues_after_error(self, started: BotHandlers, gateway, games_provider):
        games_provider.errors["genres"] = GamesUnavailableError("rawg", "timeout")
        started.on_callback(make_callback(CallbackAction.PICK_GENRES))
        games_provider.errors.clear()
        gateway.clear()

        started.on_callback(make_callback(CallbackAction.MAIN_MENU))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text

    def test_notify_error(self, started: BotHandlers, gateway):
        started.notify_error(make_message("/start"), "Сообщение об ошибке")

        assert "Сообщение об ошибке" in gateway.last_text

    def test_notify_error_from_callback(self, started: BotHandlers, gateway):
        started.notify_error(make_callback("menu"), "Ошибка из callback")

        assert "Ошибка из callback" in gateway.last_text

    def test_notify_error_without_chat(self, started: BotHandlers, gateway):
        started.notify_error(object(), "Некуда отправлять")

        assert gateway.events == []

    def test_notify_error_when_gateway_fails(self, started: BotHandlers, gateway, monkeypatch):
        monkeypatch.setattr(gateway, "send_text", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))

        started.notify_error(make_message("/start"), "Ошибка")  # не должно падать

    def test_safe_handler_passes_arguments(self, started: BotHandlers, gateway):
        class Sample:
            def __init__(self):
                self.calls = []

            @safe_handler
            def handle(self, event):
                self.calls.append(event)

            def notify_error(self, event, message):
                self.calls.append(message)

        sample = Sample()
        sample.handle("событие")

        assert sample.calls == ["событие"]

    def test_safe_handler_catches_errors(self):
        class Sample:
            def __init__(self):
                self.errors = []

            @safe_handler
            def handle(self, event):
                raise RuntimeError("сбой")

            def notify_error(self, event, message):
                self.errors.append(message)

        sample = Sample()
        sample.handle("событие")

        assert sample.errors == [texts.GENERIC_ERROR]

    def test_safe_handler_uses_domain_message(self):
        class Sample:
            def __init__(self):
                self.errors = []

            @safe_handler
            def handle(self, event):
                raise DatabaseError("нет соединения")

            def notify_error(self, event, message):
                self.errors.append(message)

        sample = Sample()
        sample.handle("событие")

        assert sample.errors == [DatabaseError.user_message]

    def test_handler_without_chat_in_event(self, started: BotHandlers, gateway):
        class Broken:
            pass

        started.notify_error(Broken(), "Ошибка")

        assert gateway.events == []
