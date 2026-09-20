"""Сценарии использования бота (сквозные тесты).

Каждый тест проходит путь пользователя от команды /start до результата,
используя настоящие экраны, обработчики и базу данных SQLite. Внешние сервисы
(каталог игр и геолокация) заменены подставными объектами, поэтому тесты
работают без сети.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from gamehunter.domain.exceptions import (
    DatabaseError,
    GamesUnavailableError,
    GenresUnavailableError,
    RegionUnavailableError,
)
from gamehunter.presentation import texts
from gamehunter.presentation.keyboards import ButtonText, CallbackAction
from gamehunter.presentation.state import ContextScreen, UserContext
from tests.fakes import buttons_of, make_callback, make_details, make_game, make_message

CHAT_ID = 100
USER_ID = 200


@pytest.fixture()
def flow(handlers, gateway):
    """Пользователь открыл бота и дошёл до главного меню."""

    def step(callback: str | None = None, text: str | None = None) -> str:
        """Один шаг диалога: нажатие кнопки или отправка текста."""
        gateway.clear()
        if callback is not None:
            handlers.on_callback(make_callback(callback, chat_id=CHAT_ID, user_id=USER_ID))
        else:
            handlers.on_text(make_message(text or "", chat_id=CHAT_ID, user_id=USER_ID))
        return gateway.last_text

    handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))
    step(text=ButtonText.START)
    return step


# ---------------------------------------------------------------------- #
# Сценарий 1. Подбор игры по интересам
# ---------------------------------------------------------------------- #
class TestScenarioPicking:
    def test_full_path(self, flow, gateway, storage, library_service):
        # Экран 2 → Экран 3: выбор интересов
        message = flow(text=ButtonText.PICK)
        assert texts.GENRES_TITLE in message

        # Отмечаем два жанра
        message = flow(callback="g:action")
        assert "✔ Action" in message

        message = flow(callback="g:role-playing-games-rpg")
        assert "✔ RPG" in message

        # Экран 4: подборка игр
        message = flow(callback=CallbackAction.PICK_SHOW)
        assert texts.GAMES_TITLE in message
        assert "жанры: Action, RPG" in message
        assert storage.get(USER_ID).screen == ContextScreen.GAME_LIST

        # Экран 5: карточка первой игры
        first_game = storage.get(USER_ID).games[0]
        message = flow(callback=f"game:{first_game.id}")
        assert texts.GAME_CARD_TITLE in message
        assert first_game.name in message

        # Отмечаем игру как сыгранную
        message = flow(callback=f"played:{first_game.id}")
        assert texts.GAME_ADDED_TO_PLAYED in message
        assert library_service.is_played(USER_ID, first_game.id) is True

        # Экран 10: список сыгранных игр
        message = flow(text=ButtonText.PLAYED)
        assert first_game.name in message

        record_id = storage.get(USER_ID).records[0]

        # Экран 11: информация об игре
        message = flow(callback=f"rec:{record_id}")
        assert texts.PLAYED_INFO_TITLE in message
        assert texts.REVIEW_ABSENT in message

        # Экран 11а: отзыв
        message = flow(callback=f"rev:{record_id}")
        assert texts.REVIEW_PROMPT in message

        message = flow(text="Прошёл на 100%, отличный сюжет.")
        assert texts.REVIEW_SAVED in message
        assert "Отзыв: Прошёл на 100%, отличный сюжет." in message

    def test_show_all_without_genres(self, flow, gateway, games_provider):
        flow(text=ButtonText.PICK)
        message = flow(callback=CallbackAction.PICK_ALL)

        assert texts.GAMES_TITLE in message
        assert games_provider.search_calls[-1].genres == ()

    def test_no_selection_and_no_profile_interests(self, flow):
        flow(text=ButtonText.PICK)

        message = flow(callback=CallbackAction.PICK_SHOW)

        assert texts.GENRES_NO_SELECTION in message

    def test_no_games_found(self, flow, games_provider):
        games_provider.games = []
        flow(text=ButtonText.PICK)
        flow(callback="g:action")

        message = flow(callback=CallbackAction.PICK_SHOW)

        assert "не найдено" in message.lower() or "Не удалось найти" in message

    def test_back_to_genres_from_list(self, flow, storage):
        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)

        message = flow(callback=CallbackAction.PICK_GENRES)

        assert texts.GENRES_TITLE in message
        assert storage.get(USER_ID).screen == ContextScreen.PICKING_GENRES

    def test_back_from_card_to_list(self, flow, storage, games_provider):
        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)
        game = storage.get(USER_ID).games[0]
        flow(callback=f"game:{game.id}")
        searches = len(games_provider.search_calls)

        message = flow(callback=CallbackAction.BACK_GAMES)

        assert texts.GAMES_TITLE in message
        assert len(games_provider.search_calls) == searches

    def test_pagination(self, flow, storage):
        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)
        first_page = [game.id for game in storage.get(USER_ID).games]

        flow(callback="games:2")
        second_page = [game.id for game in storage.get(USER_ID).games]

        assert first_page != second_page
        assert storage.get(USER_ID).games_page == 2

        message = flow(callback="games:1")
        assert "Страница 1 из 3" in message

    def test_start_returns_to_menu_from_anywhere(self, flow, handlers, gateway, storage):
        flow(text=ButtonText.PICK)
        flow(callback="g:action")
        gateway.clear()

        handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


# ---------------------------------------------------------------------- #
# Сценарий 2. Поиск игр по франшизе (IP)
# ---------------------------------------------------------------------- #
class TestScenarioFranchise:
    def test_full_path(self, flow, gateway, storage, library_service):
        # Экран 6: ввод названия франшизы
        message = flow(text=ButtonText.FRANCHISE)
        assert texts.FRANCHISE_INPUT_PROMPT in message

        # Экран 7: найденные франшизы
        message = flow(text="Marvel")
        assert texts.FRANCHISES_TITLE in message
        assert "1. Marvel" in message
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_LIST

        # Экран 8: игры франшизы
        message = flow(callback="frs:1")
        assert "Игры франшизы Marvel:" in message
        assert "Marvel's Spider-Man" in message

        # Экран 5: карточка игры и добавление в избранное
        message = flow(callback="game:9001")
        assert texts.GAME_CARD_TITLE in message

        message = flow(callback="fav:9001")
        assert texts.GAME_ADDED_TO_FAVORITES in message
        assert library_service.is_favorite(USER_ID, 9001) is True

        # Экран 12: избранное
        message = flow(text=ButtonText.FAVORITES)
        assert texts.FAVORITES_TITLE in message
        assert "Marvel's Spider-Man" in message

        # Карточка из избранного и удаление из избранного
        message = flow(callback="game:9001")
        assert texts.GAME_STATUS_FAVORITE in message
        assert ButtonText.REMOVE_FAVORITE in "\n".join(
            label for row in buttons_of(gateway.last_markup) for label in row
        )

        message = flow(callback="fav:9001")
        assert texts.GAME_REMOVED_FROM_FAVORITES in message
        assert library_service.is_favorite(USER_ID, 9001) is False

    def test_second_franchise_from_list(self, flow, storage):
        flow(text=ButtonText.FRANCHISE)
        flow(text="Marvel")

        message = flow(callback="frs:2")

        assert "Игры франшизы Marvel Ultimate Alliance:" in message

    def test_franchise_not_found(self, flow):
        flow(text=ButtonText.FRANCHISE)

        message = flow(text="абракадабра")

        assert "не найдена" in message.lower()
        assert texts.FRANCHISE_INPUT_PROMPT in message

    def test_empty_franchise_name(self, flow):
        flow(text=ButtonText.FRANCHISE)

        message = flow(text="   ")

        assert texts.FRANCHISE_EMPTY_NAME in message

    def test_another_franchise_button(self, flow, storage):
        flow(text=ButtonText.FRANCHISE)
        flow(text="Marvel")
        flow(callback="frs:1")

        message = flow(callback=CallbackAction.FRANCHISE_INPUT)

        assert texts.FRANCHISE_INPUT_PROMPT in message
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_INPUT

    def test_back_from_card_to_franchise_games(self, flow, storage):
        flow(text=ButtonText.FRANCHISE)
        flow(text="Marvel")
        flow(callback="frs:1")
        flow(callback="game:9001")

        message = flow(callback=CallbackAction.BACK_GAMES)

        assert "Игры франшизы Marvel:" in message
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_GAMES


# ---------------------------------------------------------------------- #
# Сценарий 3. Анкета пользователя
# ---------------------------------------------------------------------- #
class TestScenarioProfile:
    def test_full_profile(self, flow, gateway, profile_service, ip_provider):
        # Экран 9: пустая анкета
        message = flow(text=ButtonText.PROFILE)
        assert "Возраст: не указан" in message
        assert "Регион: не определён" in message

        # Возраст
        flow(callback=CallbackAction.PROFILE_AGE)
        message = flow(text="27")
        assert texts.PROFILE_AGE_SAVED in message
        assert "Возраст: 27 лет" in message

        # Интересы
        flow(callback=CallbackAction.PROFILE_GENRES)
        flow(callback="pg:action")
        flow(callback="pg:role-playing-games-rpg")
        message = flow(callback=CallbackAction.PROFILE_GENRES_DONE)
        assert texts.PROFILE_GENRES_SAVED in message
        assert "Интересы (жанры): Action, RPG" in message

        # Платформы
        flow(callback=CallbackAction.PROFILE_PLATFORMS)
        flow(callback="pl:1")
        message = flow(callback=CallbackAction.PROFILE_PLATFORMS_DONE)
        assert texts.PROFILE_PLATFORMS_SAVED in message
        assert "Платформы: PC" in message

        # Регион по IP
        flow(callback=CallbackAction.PROFILE_IP)
        message = flow(text="8.8.8.8")
        assert texts.PROFILE_REGION_SAVED in message
        assert "Mountain View" in message
        assert "часовой пояс: America/Los_Angeles" in message
        assert "валюта: USD" in message
        assert ip_provider.calls == ["8.8.8.8"]

        assert profile_service.get_profile(USER_ID).age == 27

    def test_profile_is_used_in_picking(self, flow, gateway, games_provider):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)
        flow(text="30")
        flow(callback=CallbackAction.PROFILE_GENRES)
        flow(callback="pg:shooter")
        flow(callback=CallbackAction.PROFILE_GENRES_DONE)
        flow(callback=CallbackAction.PROFILE_PLATFORMS)
        flow(callback="pl:1")
        flow(callback=CallbackAction.PROFILE_PLATFORMS_DONE)

        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_SHOW)

        query = games_provider.search_calls[-1]
        assert query.genres == ("shooter",)
        assert query.parent_platforms == (1,)
        assert texts.GAMES_TITLE in gateway.last_text

    def test_invalid_age(self, flow):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)

        message = flow(text="много")

        assert "Возраст должен быть числом" in message
        assert texts.PROFILE_AGE_PROMPT in message

    def test_age_below_minimum(self, flow):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)

        message = flow(text="2")

        assert "Возраст должен быть числом" in message

    def test_reset_age(self, flow, profile_service):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)
        flow(text="27")

        message = flow(callback=CallbackAction.PROFILE_AGE_RESET)

        assert texts.PROFILE_AGE_RESET in message
        assert profile_service.get_profile(USER_ID).age is None

    def test_invalid_ip(self, flow):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_IP)

        message = flow(text="это не адрес")

        assert "Некорректный IP-адрес" in message
        assert "2ip.ru" in message

    def test_private_ip(self, flow):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_IP)

        message = flow(text="192.168.1.10")

        assert "локальный" in message.lower()
        assert "публичный" in message

    def test_ip_from_text_with_explanation(self, flow, ip_provider):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_IP)

        flow(text="Мой адрес 5.188.0.1, посмотрел на 2ip.ru")

        assert ip_provider.calls == ["5.188.0.1"]

    def test_reset_region(self, flow, profile_service):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_IP)
        flow(text="8.8.8.8")

        message = flow(callback=CallbackAction.PROFILE_IP_RESET)

        assert texts.PROFILE_REGION_RESET in message
        assert profile_service.get_profile(USER_ID).region is None

    def test_saved_interests_are_marked_on_reopen(self, flow, profile_service):
        from tests.fakes import make_genre

        profile_service.set_genres(USER_ID, [make_genre("Strategy", "strategy", 7)])
        flow(text=ButtonText.PROFILE)

        message = flow(callback=CallbackAction.PROFILE_GENRES)

        assert "✔ Strategy" in message


# ---------------------------------------------------------------------- #
# Сценарий 4. Учёт сыгранных игр и возраста
# ---------------------------------------------------------------------- #
class TestScenarioPlayedAndAge:
    def test_played_games_are_excluded(self, flow, gateway, library_service, games_provider):
        library_service.add_played(USER_ID, make_game(32, "The Witcher 3: Wild Hunt"))
        library_service.add_played(USER_ID, make_game(58175, "God of War"))

        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)

        message = gateway.last_text
        assert texts.GAMES_PLAYED_EXCLUDED in message
        assert "The Witcher 3" not in message
        assert "God of War" not in message
        assert set(games_provider.search_calls[-1].exclude_game_ids) == {32, 58175}

    def test_marked_game_is_excluded_on_next_search(self, flow, gateway, storage, library_service):
        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)
        game_id = storage.get(USER_ID).games[0].id

        flow(callback=f"game:{game_id}")
        flow(callback=f"played:{game_id}")
        assert library_service.is_played(USER_ID, game_id) is True

        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)

        assert game_id not in [game.id for game in storage.get(USER_ID).games]

    def test_age_filter_hides_adult_games(self, flow, gateway, profile_service):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)
        flow(text="13")

        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)

        message = gateway.last_text
        # В тестовом каталоге только Portal 2 подходит подростку (10+)
        assert "Portal 2" in message
        assert "The Witcher 3" not in message
        assert "возраст: 13" in message

    def test_adult_sees_all_games(self, flow, gateway):
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)
        flow(text="30")

        flow(text=ButtonText.PICK)
        flow(callback=CallbackAction.PICK_ALL)

        assert "The Witcher 3: Wild Hunt" in gateway.last_text

    def test_no_suitable_games_for_child(self, flow, gateway, games_provider):
        games_provider.details = {
            game.id: make_details(game, min_age=18) for game in games_provider.games
        }
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_AGE)
        flow(text="6")

        flow(text=ButtonText.PICK)
        message = flow(callback=CallbackAction.PICK_ALL)

        assert "не найдено" in message.lower() or "Не удалось найти" in message

    def test_played_history_pagination(self, flow, gateway, library_service, storage):
        now = datetime(2026, 5, 1, 12, 0)
        for index in range(5):
            library_service.add_played(
                USER_ID, make_game(500 + index, f"Игра {index}"), played_at=now - timedelta(days=index)
            )

        flow(text=ButtonText.PLAYED)
        assert "Страница 1 из 2" in gateway.last_text

        message = flow(callback="lib:2")
        assert "Страница 2 из 2" in message
        assert "Игра 4" in message

    def test_delete_played_game(self, flow, gateway, library_service, storage):
        record = library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        flow(text=ButtonText.PLAYED)
        message = flow(callback=f"del:{record.id}")

        assert texts.PLAYED_REMOVED.format("The Witcher 3") in message
        assert library_service.played_game_ids(USER_ID) == set()

    def test_review_is_too_long(self, flow, gateway, library_service):
        record = library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))
        flow(text=ButtonText.PLAYED)
        flow(callback=f"rec:{record.id}")
        flow(callback=f"rev:{record.id}")

        message = flow(text="с" * 1200)

        assert "не должен превышать 1000" in message
        assert texts.REVIEW_PROMPT in message

    def test_empty_review(self, flow, gateway, library_service):
        record = library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))
        flow(text=ButtonText.PLAYED)
        flow(callback=f"rev:{record.id}")

        message = flow(text="   ")

        assert "не может быть пустым" in message

    def test_review_is_visible_in_list_flow(self, flow, gateway, library_service, storage):
        record = library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))
        flow(text=ButtonText.PLAYED)
        flow(callback=f"rec:{record.id}")
        flow(callback=f"rev:{record.id}")
        flow(text="Очень понравилась")

        message = flow(callback=f"lib:{storage.get(USER_ID).library_page}")
        assert texts.PLAYED_TITLE in message

        message = flow(callback=f"rec:{record.id}")
        assert "Отзыв: Очень понравилась" in message


# ---------------------------------------------------------------------- #
# Сценарий 5. Ошибки внешних сервисов и базы данных
# ---------------------------------------------------------------------- #
class TestScenarioErrors:
    def test_catalog_unavailable(self, flow, gateway, games_provider, storage):
        games_provider.errors["genres"] = GenresUnavailableError("rawg", "timeout")

        message = flow(text=ButtonText.PICK)

        assert GenresUnavailableError.user_message in message
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

        # Бот продолжает работать
        games_provider.errors.clear()
        message = flow(text=ButtonText.PICK)
        assert texts.GENRES_TITLE in message

    def test_search_unavailable(self, flow, gateway, games_provider):
        games_provider.errors["search"] = GamesUnavailableError("rawg", "503")
        flow(text=ButtonText.PICK)

        message = flow(callback=CallbackAction.PICK_ALL)

        assert GamesUnavailableError.user_message in message

    def test_franchise_search_unavailable(self, flow, gateway, games_provider):
        games_provider.errors["franchises"] = GamesUnavailableError("rawg", "503")
        flow(text=ButtonText.FRANCHISE)

        message = flow(text="Marvel")

        assert GamesUnavailableError.user_message in message

    def test_region_service_unavailable(self, flow, gateway, ip_provider):
        ip_provider.error = RegionUnavailableError("ipapi", "429")
        flow(text=ButtonText.PROFILE)
        flow(callback=CallbackAction.PROFILE_IP)

        message = flow(text="8.8.8.8")

        assert RegionUnavailableError.user_message in message
        assert texts.PROFILE_TITLE in message

    def test_database_unavailable(self, flow, gateway, profile_service, monkeypatch):
        monkeypatch.setattr(
            profile_service, "get_profile", lambda user_id: (_ for _ in ()).throw(DatabaseError())
        )

        message = flow(text=ButtonText.PROFILE)

        assert DatabaseError.user_message in message

    def test_played_list_database_error(self, flow, gateway, library_service, monkeypatch):
        monkeypatch.setattr(
            library_service,
            "get_played_history",
            lambda *args, **kwargs: (_ for _ in ()).throw(DatabaseError()),
        )

        message = flow(text=ButtonText.PLAYED)

        assert DatabaseError.user_message in message

    def test_bot_survives_sequence_of_errors(self, flow, gateway, games_provider):
        games_provider.errors["genres"] = GenresUnavailableError("rawg", "timeout")
        flow(text=ButtonText.PICK)
        games_provider.errors["search"] = GamesUnavailableError("rawg", "timeout")
        flow(text=ButtonText.PICK)
        games_provider.errors.clear()

        message = flow(text=ButtonText.PICK)

        assert texts.GENRES_TITLE in message

    def test_unsupported_messages_are_ignored(self, flow, gateway, handlers):
        gateway.clear()

        handlers.on_unsupported(make_message("", chat_id=CHAT_ID, user_id=USER_ID, content_type="photo"))

        assert gateway.events == []

    def test_unknown_text(self, flow, gateway):
        message = flow(text="какая сегодня погода?")

        assert texts.UNKNOWN_COMMAND in message


# ---------------------------------------------------------------------- #
# Сценарий 6. Первый запуск и неизвестное состояние
# ---------------------------------------------------------------------- #
class TestScenarioFirstLaunch:
    def test_first_message_shows_start_screen(self, handlers, gateway, storage):
        handlers.on_text(make_message("Привет", chat_id=CHAT_ID, user_id=USER_ID))

        assert texts.START_WELCOME in gateway.last_text
        assert storage.has(USER_ID) is True

    def test_start_command_for_new_user(self, handlers, gateway):
        handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))

        assert texts.START_WELCOME in gateway.last_text

    def test_second_start_shows_menu(self, handlers, gateway, storage):
        handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))
        gateway.clear()

        handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))

        assert texts.MAIN_MENU_WELCOME in gateway.last_text

    def test_users_are_isolated(self, handlers, gateway, storage, library_service):
        handlers.on_start(make_message("/start", chat_id=CHAT_ID, user_id=USER_ID))
        handlers.on_callback(make_callback(CallbackAction.PICK_ALL, chat_id=CHAT_ID, user_id=USER_ID))
        library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        handlers.on_start(make_message("/start", chat_id=101, user_id=300))
        handlers.on_text(make_message(ButtonText.PLAYED, chat_id=101, user_id=300))

        assert texts.PLAYED_EMPTY in gateway.last_text
        assert storage.get(300).screen == ContextScreen.PLAYED_LIST

    def test_button_from_old_message_after_restart(self, flow, gateway, storage):
        # Пользователь нажал старую кнопку, а список игр уже не сохранён
        storage.save(USER_ID, UserContext().at_main_menu())

        message = flow(callback=CallbackAction.BACK_GAMES)

        assert texts.MAIN_MENU_WELCOME in message
