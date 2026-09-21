"""Тесты экранов бота (слой представления)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from gamehunter.domain.entities import Region
from gamehunter.domain.exceptions import (
    DatabaseError,
    GameInfoUnavailableError,
    GamesUnavailableError,
    GenresUnavailableError,
    InvalidAgeError,
    NoGamesFoundError,
    PlayedGameNotFoundError,
    RegionUnavailableError,
)
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.state import ContextScreen, UserContext
from tests.fakes import (
    buttons_of,
    callbacks_of,
    make_details,
    make_game,
    make_genre,
    make_platform,
)

CHAT_ID = 100
USER_ID = 200


def last_text(gateway) -> str:
    return gateway.last_text


def last_buttons(gateway):
    return buttons_of(gateway.last_markup)


def last_callbacks(gateway):
    return callbacks_of(gateway.last_markup)


# ---------------------------------------------------------------------- #
# Экран 1 и Экран 2
# ---------------------------------------------------------------------- #
class TestStartScreen:
    def test_shows_welcome(self, screens, gateway):
        screens.start.show(CHAT_ID)

        assert last_text(gateway) == texts.START_WELCOME

    def test_shows_start_button(self, screens, gateway):
        screens.start.show(CHAT_ID)

        assert last_buttons(gateway) == [[keyboards.ButtonText.START]]

    def test_sends_to_given_chat(self, screens, gateway):
        screens.start.show(999)

        assert gateway.last_event.chat_id == 999


class TestMainMenuScreen:
    def test_shows_menu_text(self, screens, gateway):
        screens.main_menu.show(CHAT_ID, USER_ID)

        assert last_text(gateway) == texts.MAIN_MENU_WELCOME

    def test_shows_menu_buttons(self, screens, gateway):
        screens.main_menu.show(CHAT_ID, USER_ID)

        labels = [label for row in last_buttons(gateway) for label in row]

        assert keyboards.ButtonText.PICK in labels
        assert keyboards.ButtonText.FRANCHISE in labels
        assert keyboards.ButtonText.PROFILE in labels
        assert keyboards.ButtonText.PLAYED in labels
        assert keyboards.ButtonText.FAVORITES in labels

    def test_resets_context(self, screens, storage):
        storage.save(USER_ID, UserContext().at_game_card(32))

        screens.main_menu.show(CHAT_ID, USER_ID)

        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU
        assert storage.get(USER_ID).games == ()


# ---------------------------------------------------------------------- #
# Экран 3. Интересы (жанры)
# ---------------------------------------------------------------------- #
class TestGenrePickingScreen:
    def test_shows_genres(self, screens, gateway):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.GENRES_TITLE in message
        assert "Action" in message
        assert "RPG" in message

    def test_limited_number_of_genres(self, screens, gateway):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        genre_callbacks = [
            callback for callback in last_callbacks(gateway) if callback.startswith("g:")
        ]

        assert len(genre_callbacks) == 6  # max_genres из фикстуры

    def test_saves_state_and_catalog(self, screens, storage):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        context = storage.get(USER_ID)
        assert context.screen == ContextScreen.PICKING_GENRES
        assert len(context.genre_catalog) == 6

    def test_action_buttons(self, screens, gateway):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        callbacks = last_callbacks(gateway)
        assert keyboards.CallbackAction.PICK_SHOW in callbacks
        assert keyboards.CallbackAction.PICK_ALL in callbacks
        assert keyboards.CallbackAction.MAIN_MENU in callbacks

    def test_toggle_marks_genre(self, screens, gateway, storage):
        screens.genre_picking.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")

        assert "✔ Action" in last_text(gateway)
        assert storage.get(USER_ID).picked_genres == ("action",)

    def test_toggle_twice_removes_mark(self, screens, gateway, storage):
        screens.genre_picking.show(CHAT_ID, USER_ID)
        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")
        gateway.clear()

        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")

        assert "✔" not in last_text(gateway)
        assert storage.get(USER_ID).picked_genres == ()

    def test_toggle_without_catalog_reloads_genres(self, screens, gateway, games_provider):
        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")

        assert games_provider.genre_calls == 1
        assert texts.GENRES_TITLE in last_text(gateway)

    def test_show_selection_opens_game_list(self, screens, gateway, storage):
        screens.genre_picking.show(CHAT_ID, USER_ID)
        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")
        gateway.clear()

        screens.genre_picking.show_selection(CHAT_ID, USER_ID)

        assert storage.get(USER_ID).screen == ContextScreen.GAME_LIST
        assert texts.GAMES_TITLE in last_text(gateway)

    def test_show_selection_uses_profile_interests(self, screens, gateway, profile_service):
        profile_service.set_genres(USER_ID, [make_genre("Shooter", "shooter", 10)])
        screens.genre_picking.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.genre_picking.show_selection(CHAT_ID, USER_ID)

        assert texts.GAMES_TITLE in last_text(gateway)
        assert "Shooter" in last_text(gateway)

    def test_show_selection_without_interests(self, screens, gateway, storage):
        screens.genre_picking.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.genre_picking.show_selection(CHAT_ID, USER_ID)

        assert texts.GENRES_NO_SELECTION in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.PICKING_GENRES

    def test_show_all_ignores_profile_interests(self, screens, gateway, profile_service, games_provider):
        profile_service.set_genres(USER_ID, [make_genre("Shooter", "shooter", 10)])
        screens.genre_picking.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.genre_picking.show_all(CHAT_ID, USER_ID)

        query = games_provider.search_calls[-1]
        assert query.genres == ()
        assert texts.GAMES_TITLE in last_text(gateway)

    def test_genres_unavailable(self, screens, gateway, games_provider, storage):
        games_provider.errors["genres"] = GenresUnavailableError("rawg", "timeout")

        screens.genre_picking.show(CHAT_ID, USER_ID)

        assert GenresUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


# ---------------------------------------------------------------------- #
# Экран 4. Список игр
# ---------------------------------------------------------------------- #
class TestGameListScreen:
    def test_shows_games(self, screens, gateway):
        screens.game_list.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.GAMES_TITLE in message
        assert "1. The Witcher 3: Wild Hunt" in message

    def test_shows_three_games_per_page(self, screens, gateway):
        screens.game_list.show(CHAT_ID, USER_ID)

        game_callbacks = [c for c in last_callbacks(gateway) if c.startswith("game:")]

        assert len(game_callbacks) == 3

    def test_saves_games_in_context(self, screens, storage):
        screens.game_list.show(CHAT_ID, USER_ID)

        context = storage.get(USER_ID)
        assert context.screen == ContextScreen.GAME_LIST
        assert len(context.games) == 3
        assert context.games_page == 1

    def test_filters_line_without_profile(self, screens, gateway):
        screens.game_list.show(CHAT_ID, USER_ID)

        assert texts.GAMES_NO_FILTERS in last_text(gateway)

    def test_filters_line_with_profile(self, screens, gateway, profile_service):
        profile_service.set_age(USER_ID, "20")
        profile_service.set_genres(USER_ID, [make_genre("RPG", "role-playing-games-rpg", 5)])
        profile_service.set_platforms(USER_ID, [])

        screens.game_list.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert "жанры: RPG" in message
        assert "возраст: 20" in message

    def test_played_games_are_excluded(self, screens, gateway, library_service, games_provider):
        library_service.add_played(USER_ID, make_game(32))
        library_service.add_played(USER_ID, make_game(58175))

        screens.game_list.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.GAMES_PLAYED_EXCLUDED in message
        assert "The Witcher 3" not in message
        assert set(games_provider.search_calls[-1].exclude_game_ids) == {32, 58175}

    def test_second_page(self, screens, gateway, storage):
        screens.game_list.show(CHAT_ID, USER_ID, page=2)

        assert storage.get(USER_ID).games_page == 2
        assert "Страница 2 из 3" in last_text(gateway)

    def test_pagination_buttons(self, screens, gateway):
        screens.game_list.show(CHAT_ID, USER_ID, page=2)

        callbacks = last_callbacks(gateway)
        assert "games:1" in callbacks
        assert "games:3" in callbacks

    def test_custom_title(self, screens, gateway):
        screens.game_list.show(CHAT_ID, USER_ID, title=texts.GAMES_SEARCH_TITLE)

        assert last_text(gateway).startswith(texts.GAMES_SEARCH_TITLE)

    def test_ignore_profile_genres(self, screens, gateway, profile_service, games_provider):
        profile_service.set_genres(USER_ID, [make_genre("RPG", "role-playing-games-rpg", 5)])

        screens.game_list.show(CHAT_ID, USER_ID, ignore_profile_genres=True)

        assert games_provider.search_calls[-1].genres == ()

    def test_no_games_found(self, screens, gateway, games_provider, storage):
        games_provider.games = []

        screens.game_list.show(CHAT_ID, USER_ID)

        assert NoGamesFoundError().user_message in last_text(gateway)
        assert keyboards.CallbackAction.PICK_GENRES in last_callbacks(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.PICKING_GENRES

    def test_catalog_unavailable(self, screens, gateway, games_provider, storage):
        games_provider.errors["search"] = GamesUnavailableError("rawg", "500")

        screens.game_list.show(CHAT_ID, USER_ID)

        assert GamesUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_profile_error(self, screens, gateway, profile_service, monkeypatch):
        monkeypatch.setattr(
            profile_service, "get_profile", lambda user_id: (_ for _ in ()).throw(DatabaseError())
        )

        screens.game_list.show(CHAT_ID, USER_ID)

        assert DatabaseError.user_message in last_text(gateway)

    def test_rerender_from_context(self, screens, gateway, games_provider):
        screens.game_list.show(CHAT_ID, USER_ID)
        calls_before = len(games_provider.search_calls)
        gateway.clear()

        screens.game_list.rerender(CHAT_ID, USER_ID)

        assert texts.GAMES_TITLE in last_text(gateway)
        assert len(games_provider.search_calls) == calls_before  # каталог не запрашивался заново

    def test_rerender_without_games(self, screens, gateway, storage):
        screens.game_list.rerender(CHAT_ID, USER_ID)

        assert texts.STATE_LOST in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_rerender_keeps_filters(self, screens, gateway, profile_service):
        profile_service.set_age(USER_ID, "25")
        screens.game_list.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.game_list.rerender(CHAT_ID, USER_ID)

        assert "возраст: 25" in last_text(gateway)


# ---------------------------------------------------------------------- #
# Экран 5. Карточка игры
# ---------------------------------------------------------------------- #
class TestGameCardScreen:
    def test_shows_card(self, screens, gateway):
        screens.game_card.show(CHAT_ID, USER_ID, 32)

        message = last_text(gateway)
        assert texts.GAME_CARD_TITLE in message
        assert "The Witcher 3: Wild Hunt" in message
        assert "ESRB Mature (17+)" in message

    def test_sends_cover_photo(self, screens, gateway):
        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert gateway.photos
        assert gateway.photos[0].photo == "https://cdn.example/game.jpg"

    def test_no_photo_when_image_is_missing(self, screens, gateway, games_provider):
        games_provider.details[32] = make_details(make_game(32, image_url=None))

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert gateway.photos == []

    def test_card_buttons(self, screens, gateway):
        screens.game_card.show(CHAT_ID, USER_ID, 32)

        callbacks = last_callbacks(gateway)
        assert "played:32" in callbacks
        assert "fav:32" in callbacks
        assert keyboards.CallbackAction.BACK_GAMES in callbacks

    def test_saves_state(self, screens, storage):
        screens.game_list.show(CHAT_ID, USER_ID)
        screens.game_card.show(CHAT_ID, USER_ID, 32)

        context = storage.get(USER_ID)
        assert context.screen == ContextScreen.GAME_CARD
        assert context.current_game_id == 32
        assert context.list_source == ContextScreen.GAME_LIST

    def test_marks_played_game(self, screens, gateway, library_service):
        library_service.add_played(USER_ID, make_game(32))

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert texts.GAME_STATUS_PLAYED in last_text(gateway)

    def test_marks_favorite_game(self, screens, gateway, library_service):
        library_service.add_favorite(USER_ID, make_game(32))

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert texts.GAME_STATUS_FAVORITE in last_text(gateway)
        assert keyboards.ButtonText.REMOVE_FAVORITE in [
            label for row in last_buttons(gateway) for label in row
        ]

    def test_add_to_played(self, screens, gateway, library_service):
        screens.game_list.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.game_card.add_to_played(CHAT_ID, USER_ID, 32)

        assert library_service.is_played(USER_ID, 32) is True
        assert any(texts.GAME_ADDED_TO_PLAYED in text for text in gateway.all_texts)
        assert texts.GAME_STATUS_PLAYED in last_text(gateway)

    def test_add_to_played_twice(self, screens, gateway, library_service):
        screens.game_list.show(CHAT_ID, USER_ID)
        screens.game_card.add_to_played(CHAT_ID, USER_ID, 32)
        gateway.clear()

        screens.game_card.add_to_played(CHAT_ID, USER_ID, 32)

        assert any(
            "уже есть" in text for text in gateway.all_texts
        )
        assert texts.GAME_CARD_TITLE in last_text(gateway)

    def test_add_to_played_without_list_context(self, screens, gateway, library_service):
        screens.game_card.add_to_played(CHAT_ID, USER_ID, 32)

        assert library_service.is_played(USER_ID, 32) is True

    def test_toggle_favorite_adds(self, screens, gateway, library_service):
        screens.game_list.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.game_card.toggle_favorite(CHAT_ID, USER_ID, 32)

        assert library_service.is_favorite(USER_ID, 32) is True
        assert any(texts.GAME_ADDED_TO_FAVORITES in text for text in gateway.all_texts)

    def test_toggle_favorite_removes(self, screens, gateway, library_service):
        library_service.add_favorite(USER_ID, make_game(32))
        screens.game_list.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.game_card.toggle_favorite(CHAT_ID, USER_ID, 32)

        assert library_service.is_favorite(USER_ID, 32) is False
        assert any(texts.GAME_REMOVED_FROM_FAVORITES in text for text in gateway.all_texts)

    def test_card_falls_back_to_list_data(self, screens, gateway, games_provider):
        games_provider.errors["details"] = GameInfoUnavailableError("rawg", "timeout")
        screens.game_list.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        message = last_text(gateway)
        assert texts.GAME_CARD_TITLE in message
        assert "The Witcher 3: Wild Hunt" in message
        assert "возрастной рейтинг не указан" in message

    def test_unknown_game(self, screens, gateway, storage):
        screens.game_card.show(CHAT_ID, USER_ID, 999999)

        assert "не найдена" in last_text(gateway).lower()
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_catalog_error(self, screens, gateway, games_provider, storage):
        games_provider.errors["details"] = GameInfoUnavailableError("rawg", "500")

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert GameInfoUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_profile_error_does_not_break_card(self, screens, gateway, profile_service, monkeypatch):
        monkeypatch.setattr(
            profile_service, "get_profile", lambda user_id: (_ for _ in ()).throw(DatabaseError())
        )

        screens.game_card.show(CHAT_ID, USER_ID, 32)

        assert texts.GAME_CARD_TITLE in last_text(gateway)


# ---------------------------------------------------------------------- #
# Экраны 6–8. Франшиза (IP)
# ---------------------------------------------------------------------- #
class TestFranchiseInputScreen:
    def test_shows_prompt(self, screens, gateway):
        screens.franchise_input.show(CHAT_ID, USER_ID)

        assert texts.FRANCHISE_INPUT_PROMPT in last_text(gateway)

    def test_hides_reply_keyboard(self, screens, gateway):
        screens.franchise_input.show(CHAT_ID, USER_ID)

        assert not hasattr(gateway.last_markup, "keyboard")

    def test_saves_state(self, screens, storage):
        screens.franchise_input.show(CHAT_ID, USER_ID)

        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_INPUT

    def test_error_text_is_shown(self, screens, gateway):
        screens.franchise_input.show(CHAT_ID, USER_ID, error_text="Франшиза не найдена.")

        assert last_text(gateway).startswith("Франшиза не найдена.")
        assert texts.FRANCHISE_INPUT_PROMPT in last_text(gateway)

    def test_empty_input(self, screens, gateway, games_provider):
        screens.franchise_input.search(CHAT_ID, USER_ID, "   ")

        assert texts.FRANCHISE_EMPTY_NAME in last_text(gateway)
        assert games_provider.franchise_calls == []

    def test_search_delegates_to_list_screen(self, screens, gateway):
        screens.franchise_input.search(CHAT_ID, USER_ID, "Marvel")

        assert texts.FRANCHISES_TITLE in last_text(gateway)


class TestFranchiseListScreen:
    def test_shows_franchises(self, screens, gateway):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")

        message = last_text(gateway)
        assert texts.FRANCHISES_TITLE in message
        assert "1. Marvel" in message

    def test_saves_franchises(self, screens, storage):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")

        context = storage.get(USER_ID)
        assert context.screen == ContextScreen.FRANCHISE_LIST
        assert len(context.franchises) == 2

    def test_buttons(self, screens, gateway):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")

        callbacks = last_callbacks(gateway)
        assert "frs:1" in callbacks
        assert "frs:2" in callbacks

    def test_not_found(self, screens, gateway, storage):
        screens.franchise_list.search(CHAT_ID, USER_ID, "нет такой франшизы")

        assert "не найдена" in last_text(gateway).lower()
        assert texts.FRANCHISE_INPUT_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_INPUT

    def test_catalog_error(self, screens, gateway, games_provider, storage):
        games_provider.errors["franchises"] = GamesUnavailableError("rawg", "500")

        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")

        assert GamesUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


class TestFranchiseGamesScreen:
    def test_shows_games(self, screens, gateway, storage):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        gateway.clear()

        screens.franchise_games.show(CHAT_ID, USER_ID, 1)

        message = last_text(gateway)
        assert "Игры франшизы Marvel:" in message
        assert "Marvel's Spider-Man" in message
        assert storage.get(USER_ID).screen == ContextScreen.FRANCHISE_GAMES

    def test_buttons_use_game_ids(self, screens, gateway):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        gateway.clear()

        screens.franchise_games.show(CHAT_ID, USER_ID, 1)

        callbacks = last_callbacks(gateway)
        assert "game:9001" in callbacks
        assert keyboards.CallbackAction.FRANCHISE_INPUT in callbacks

    def test_wrong_index(self, screens, gateway, storage):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        gateway.clear()

        screens.franchise_games.show(CHAT_ID, USER_ID, 99)

        assert texts.STATE_LOST in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_franchise_without_games(self, screens, gateway, games_provider):
        games_provider.franchise_games = {101: []}
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        gateway.clear()

        screens.franchise_games.show(CHAT_ID, USER_ID, 1)

        assert NoGamesFoundError().user_message in last_text(gateway)
        assert keyboards.CallbackAction.FRANCHISE_INPUT in last_callbacks(gateway)

    def test_catalog_error(self, screens, gateway, games_provider, storage):
        games_provider.errors["franchise_games"] = GamesUnavailableError("rawg", "500")
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        gateway.clear()

        screens.franchise_games.show(CHAT_ID, USER_ID, 1)

        assert GamesUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_rerender(self, screens, gateway, games_provider):
        screens.franchise_list.search(CHAT_ID, USER_ID, "Marvel")
        screens.franchise_games.show(CHAT_ID, USER_ID, 1)
        calls = len(games_provider.franchise_games_calls)
        gateway.clear()

        screens.franchise_games.rerender(CHAT_ID, USER_ID)

        assert "Игры франшизы Marvel:" in last_text(gateway)
        assert len(games_provider.franchise_games_calls) == calls

    def test_rerender_without_games(self, screens, gateway):
        screens.franchise_games.rerender(CHAT_ID, USER_ID)

        assert texts.STATE_LOST in last_text(gateway)


# ---------------------------------------------------------------------- #
# Экран 9. Анкета
# ---------------------------------------------------------------------- #
class TestProfileScreen:
    def test_shows_empty_profile(self, screens, gateway):
        screens.profile.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.PROFILE_TITLE in message
        assert "Возраст: не указан" in message
        assert "Регион: не определён" in message

    def test_shows_filled_profile(self, screens, gateway, profile_service):
        profile_service.set_age(USER_ID, "27")
        profile_service.set_genres(USER_ID, [make_genre("RPG", "role-playing-games-rpg", 5)])

        screens.profile.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert "Возраст: 27 лет" in message
        assert "Интересы (жанры): RPG" in message

    def test_saves_state(self, screens, storage):
        screens.profile.show(CHAT_ID, USER_ID)

        assert storage.get(USER_ID).screen == ContextScreen.PROFILE

    def test_buttons_without_data(self, screens, gateway):
        screens.profile.show(CHAT_ID, USER_ID)

        labels = [label for row in last_buttons(gateway) for label in row]

        assert keyboards.ButtonText.RESET_AGE not in labels
        assert keyboards.ButtonText.RESET_REGION not in labels

    def test_buttons_with_age_and_region(self, screens, gateway, profile_service):
        profile_service.set_age(USER_ID, "27")
        profile_service.set_region_by_ip(USER_ID, "8.8.8.8")

        screens.profile.show(CHAT_ID, USER_ID)

        callbacks = last_callbacks(gateway)
        assert keyboards.CallbackAction.PROFILE_AGE_RESET in callbacks
        assert keyboards.CallbackAction.PROFILE_IP_RESET in callbacks

    def test_notice_is_shown(self, screens, gateway):
        screens.profile.show(CHAT_ID, USER_ID, notice="Возраст сохранён в анкете.")

        assert last_text(gateway).startswith("Возраст сохранён в анкете.")

    def test_reset_age(self, screens, gateway, profile_service):
        profile_service.set_age(USER_ID, "27")
        gateway.clear()

        screens.profile.reset_age(CHAT_ID, USER_ID)

        assert profile_service.get_profile(USER_ID).age is None
        assert texts.PROFILE_AGE_RESET in last_text(gateway)

    def test_reset_region(self, screens, gateway, profile_service):
        profile_service.set_region_by_ip(USER_ID, "8.8.8.8")
        gateway.clear()

        screens.profile.reset_region(CHAT_ID, USER_ID)

        assert profile_service.get_profile(USER_ID).region is None
        assert texts.PROFILE_REGION_RESET in last_text(gateway)

    def test_database_error(self, screens, gateway, profile_service, monkeypatch, storage):
        monkeypatch.setattr(
            profile_service, "get_profile", lambda user_id: (_ for _ in ()).throw(DatabaseError())
        )

        screens.profile.show(CHAT_ID, USER_ID)

        assert DatabaseError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


class TestAgeInputScreen:
    def test_shows_prompt(self, screens, gateway, storage):
        screens.age_input.show(CHAT_ID, USER_ID)

        assert texts.PROFILE_AGE_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.AGE_INPUT
        assert not hasattr(gateway.last_markup, "keyboard")

    def test_valid_age(self, screens, gateway, profile_service):
        screens.age_input.handle_age(CHAT_ID, USER_ID, "27")

        assert profile_service.get_profile(USER_ID).age == 27
        assert texts.PROFILE_AGE_SAVED in last_text(gateway)
        assert texts.PROFILE_TITLE in last_text(gateway)

    def test_invalid_age(self, screens, gateway, profile_service, storage):
        screens.age_input.handle_age(CHAT_ID, USER_ID, "много")

        assert InvalidAgeError().user_message in last_text(gateway)
        assert texts.PROFILE_AGE_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.AGE_INPUT
        assert profile_service.get_profile(USER_ID).age is None

    def test_database_error(self, screens, gateway, profile_service, monkeypatch):
        monkeypatch.setattr(
            profile_service, "set_age", lambda *args: (_ for _ in ()).throw(DatabaseError())
        )

        screens.age_input.handle_age(CHAT_ID, USER_ID, "27")

        assert DatabaseError.user_message in last_text(gateway)


class TestProfileGenresScreen:
    def test_shows_genres(self, screens, gateway, storage):
        screens.profile_genres.show(CHAT_ID, USER_ID)

        assert texts.PROFILE_GENRES_TITLE in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE_GENRES

    def test_marks_saved_interests(self, screens, gateway, profile_service):
        profile_service.set_genres(USER_ID, [make_genre("Action", "action", 4)])

        screens.profile_genres.show(CHAT_ID, USER_ID)

        assert "✔ Action" in last_text(gateway)

    def test_toggle(self, screens, gateway, storage):
        screens.profile_genres.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.profile_genres.toggle(CHAT_ID, USER_ID, "racing")

        assert storage.get(USER_ID).profile_genres == ("racing",)
        assert "✔ Racing" in last_text(gateway)

    def test_toggle_without_catalog(self, screens, gateway, games_provider):
        screens.profile_genres.toggle(CHAT_ID, USER_ID, "action")

        assert games_provider.genre_calls == 1
        assert texts.PROFILE_GENRES_TITLE in last_text(gateway)

    def test_save_selection(self, screens, gateway, profile_service):
        screens.profile_genres.show(CHAT_ID, USER_ID)
        screens.profile_genres.toggle(CHAT_ID, USER_ID, "action")
        screens.profile_genres.toggle(CHAT_ID, USER_ID, "role-playing-games-rpg")
        gateway.clear()

        screens.profile_genres.save_selection(CHAT_ID, USER_ID)

        profile = profile_service.get_profile(USER_ID)
        assert profile.genre_slugs == ("action", "role-playing-games-rpg")
        assert texts.PROFILE_GENRES_SAVED in last_text(gateway)

    def test_save_empty_selection(self, screens, gateway, profile_service):
        profile_service.set_genres(USER_ID, [make_genre("Action", "action", 4)])
        screens.profile_genres.show(CHAT_ID, USER_ID)
        screens.profile_genres.toggle(CHAT_ID, USER_ID, "action")
        gateway.clear()

        screens.profile_genres.save_selection(CHAT_ID, USER_ID)

        assert profile_service.get_profile(USER_ID).genre_slugs == ()

    def test_genres_unavailable(self, screens, gateway, games_provider, storage):
        games_provider.errors["genres"] = GenresUnavailableError("rawg", "500")

        screens.profile_genres.show(CHAT_ID, USER_ID)

        assert GenresUnavailableError.user_message in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU


class TestProfilePlatformsScreen:
    def test_shows_platforms(self, screens, gateway, storage):
        screens.profile_platforms.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        labels = [label for row in last_buttons(gateway) for label in row]

        assert texts.PROFILE_PLATFORMS_TITLE in message
        assert texts.PROFILE_PLATFORMS_NONE in message
        assert "PC" in labels
        assert "PlayStation" in labels
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE_PLATFORMS

    def test_marks_saved_platforms(self, screens, gateway, profile_service):
        profile_service.set_platforms(USER_ID, [make_platform("PC", "pc", 1)])

        screens.profile_platforms.show(CHAT_ID, USER_ID)

        labels = [label for row in last_buttons(gateway) for label in row]

        assert "✔ PC" in labels
        assert "Выбрано платформ: PC" in last_text(gateway)

    def test_hint_without_selection(self, screens, gateway):
        screens.profile_platforms.show(CHAT_ID, USER_ID)

        assert texts.PROFILE_PLATFORMS_NONE in last_text(gateway)

    def test_toggle(self, screens, gateway, storage):
        screens.profile_platforms.show(CHAT_ID, USER_ID)
        gateway.clear()

        screens.profile_platforms.toggle(CHAT_ID, USER_ID, 2)

        labels = [label for row in last_buttons(gateway) for label in row]

        assert storage.get(USER_ID).profile_platforms == (2,)
        assert "✔ PlayStation" in labels
        assert "Выбрано платформ: PlayStation" in last_text(gateway)

    def test_save_selection(self, screens, gateway, profile_service):
        screens.profile_platforms.show(CHAT_ID, USER_ID)
        screens.profile_platforms.toggle(CHAT_ID, USER_ID, 1)
        screens.profile_platforms.toggle(CHAT_ID, USER_ID, 3)
        gateway.clear()

        screens.profile_platforms.save_selection(CHAT_ID, USER_ID)

        profile = profile_service.get_profile(USER_ID)
        assert profile.platform_ids == (1, 3)
        assert profile.platform_names == ("PC", "Xbox")
        assert texts.PROFILE_PLATFORMS_SAVED in last_text(gateway)

    def test_platforms_unavailable(self, screens, gateway, games_provider):
        games_provider.errors["platforms"] = GenresUnavailableError("rawg", "500")

        screens.profile_platforms.show(CHAT_ID, USER_ID)

        assert GenresUnavailableError.user_message in last_text(gateway)


class TestRegionInputScreen:
    def test_shows_prompt(self, screens, gateway, storage):
        screens.region_input.show(CHAT_ID, USER_ID)

        assert "2ip.ru" in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.IP_INPUT

    def test_valid_ip(self, screens, gateway, profile_service):
        screens.region_input.handle_ip(CHAT_ID, USER_ID, "8.8.8.8")

        profile = profile_service.get_profile(USER_ID)
        assert profile.region is not None
        assert profile.region.country_code == "US"
        assert texts.PROFILE_REGION_SAVED in last_text(gateway)

    def test_invalid_ip(self, screens, gateway, profile_service, storage):
        screens.region_input.handle_ip(CHAT_ID, USER_ID, "не адрес")

        assert "Некорректный IP-адрес" in last_text(gateway)
        assert texts.PROFILE_IP_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.IP_INPUT
        assert profile_service.get_profile(USER_ID).region is None

    def test_private_ip(self, screens, gateway, storage):
        screens.region_input.handle_ip(CHAT_ID, USER_ID, "192.168.1.5")

        assert "локальный" in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.IP_INPUT

    def test_service_error(self, screens, gateway, ip_provider, storage):
        ip_provider.error = RegionUnavailableError("ipapi", "rate limit")

        screens.region_input.handle_ip(CHAT_ID, USER_ID, "8.8.8.8")

        assert RegionUnavailableError.user_message in last_text(gateway)
        assert texts.PROFILE_TITLE in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.PROFILE

    def test_region_is_shown_in_notice(self, screens, gateway, ip_provider):
        ip_provider.region = Region(ip="8.8.8.8", city="Kazan", country="Russia")

        screens.region_input.handle_ip(CHAT_ID, USER_ID, "8.8.8.8")

        assert "Kazan" in last_text(gateway)


# ---------------------------------------------------------------------- #
# Экраны 10–12. Библиотека пользователя
# ---------------------------------------------------------------------- #
class TestPlayedListScreen:
    @pytest.fixture()
    def with_records(self, library_service):
        now = datetime(2026, 5, 1, 12, 0)
        for index in range(5):
            library_service.add_played(
                USER_ID, make_game(100 + index, f"Игра {index}"), played_at=now - timedelta(days=index)
            )
        return library_service

    def test_empty_list(self, screens, gateway, storage):
        screens.played_list.show(CHAT_ID, USER_ID)

        assert texts.PLAYED_EMPTY in last_text(gateway)
        assert last_callbacks(gateway) == [keyboards.CallbackAction.MAIN_MENU]
        assert storage.get(USER_ID).screen == ContextScreen.PLAYED_LIST

    def test_shows_records(self, screens, gateway, with_records):
        screens.played_list.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.PLAYED_TITLE in message
        assert "Игра 0" in message

    def test_page_size(self, screens, gateway, with_records):
        screens.played_list.show(CHAT_ID, USER_ID)

        record_callbacks = [c for c in last_callbacks(gateway) if c.startswith("rec:")]

        assert len(record_callbacks) == 3

    def test_pagination(self, screens, gateway, with_records, storage):
        screens.played_list.show(CHAT_ID, USER_ID, page=2)

        callbacks = last_callbacks(gateway)
        assert "lib:1" in callbacks
        assert storage.get(USER_ID).library_page == 2
        assert storage.get(USER_ID).library_total_pages == 2

    def test_saves_record_ids(self, screens, storage, with_records):
        screens.played_list.show(CHAT_ID, USER_ID)

        assert len(storage.get(USER_ID).records) == 3

    def test_notice(self, screens, gateway, with_records):
        screens.played_list.show(CHAT_ID, USER_ID, notice="Игра удалена")

        assert last_text(gateway).startswith("Игра удалена")

    def test_database_error(self, screens, gateway, library_service, monkeypatch):
        monkeypatch.setattr(
            library_service,
            "get_played_history",
            lambda *args, **kwargs: (_ for _ in ()).throw(DatabaseError()),
        )

        screens.played_list.show(CHAT_ID, USER_ID)

        assert DatabaseError.user_message in last_text(gateway)


class TestPlayedInfoScreen:
    @pytest.fixture()
    def record(self, library_service):
        return library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))

    def test_shows_info(self, screens, gateway, record, storage):
        screens.played_info.show(CHAT_ID, USER_ID, record.id)

        message = last_text(gateway)
        assert texts.PLAYED_INFO_TITLE in message
        assert "Игра: The Witcher 3" in message
        assert texts.REVIEW_ABSENT in message
        assert storage.get(USER_ID).screen == ContextScreen.PLAYED_INFO

    def test_shows_review(self, screens, gateway, library_service, record):
        library_service.add_review(USER_ID, record.id, "Отличная игра")

        screens.played_info.show(CHAT_ID, USER_ID, record.id)

        assert "Отзыв: Отличная игра" in last_text(gateway)

    def test_buttons(self, screens, gateway, record):
        screens.played_info.show(CHAT_ID, USER_ID, record.id)

        callbacks = last_callbacks(gateway)
        assert f"rev:{record.id}" in callbacks
        assert f"del:{record.id}" in callbacks
        assert "lib:1" in callbacks

    def test_unknown_record(self, screens, gateway, storage):
        screens.played_info.show(CHAT_ID, USER_ID, 999)

        assert PlayedGameNotFoundError().user_message in last_text(gateway)
        assert texts.PLAYED_EMPTY in last_text(gateway)

    def test_delete(self, screens, gateway, library_service, record):
        screens.played_info.delete(CHAT_ID, USER_ID, record.id)

        assert library_service.played_game_ids(USER_ID) == set()
        assert texts.PLAYED_REMOVED.format("The Witcher 3") in last_text(gateway)

    def test_delete_unknown_record(self, screens, gateway, library_service):
        screens.played_info.delete(CHAT_ID, USER_ID, 999)

        assert PlayedGameNotFoundError().user_message in last_text(gateway)


class TestReviewInputScreen:
    @pytest.fixture()
    def record(self, library_service):
        return library_service.add_played(USER_ID, make_game(32, "The Witcher 3"))

    def test_shows_prompt(self, screens, gateway, record, storage):
        screens.review_input.show(CHAT_ID, USER_ID, record.id)

        assert texts.REVIEW_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.REVIEW_INPUT
        assert storage.get(USER_ID).selected_record_id == record.id

    def test_saves_review(self, screens, gateway, library_service, record):
        screens.review_input.show(CHAT_ID, USER_ID, record.id)
        gateway.clear()

        screens.review_input.handle_review(CHAT_ID, USER_ID, "Шедевр!")

        assert library_service.get_played(USER_ID, record.id).review == "Шедевр!"
        assert texts.REVIEW_SAVED in last_text(gateway)
        assert "Отзыв: Шедевр!" in last_text(gateway)

    def test_too_long_review(self, screens, gateway, library_service, record, storage):
        screens.review_input.show(CHAT_ID, USER_ID, record.id)
        gateway.clear()

        screens.review_input.handle_review(CHAT_ID, USER_ID, "с" * 1001)

        assert "не должен превышать" in last_text(gateway)
        assert texts.REVIEW_PROMPT in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.REVIEW_INPUT
        assert library_service.get_played(USER_ID, record.id).review is None

    def test_empty_review(self, screens, gateway, record, storage):
        screens.review_input.show(CHAT_ID, USER_ID, record.id)
        gateway.clear()

        screens.review_input.handle_review(CHAT_ID, USER_ID, "   ")

        assert "не может быть пустым" in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.REVIEW_INPUT

    def test_without_record(self, screens, gateway, storage):
        screens.review_input.handle_review(CHAT_ID, USER_ID, "Текст отзыва")

        assert texts.STATE_LOST in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.MAIN_MENU

    def test_deleted_record(self, screens, gateway, library_service, record):
        screens.review_input.show(CHAT_ID, USER_ID, record.id)
        library_service.remove_played(USER_ID, record.id)
        gateway.clear()

        screens.review_input.handle_review(CHAT_ID, USER_ID, "Отзыв")

        assert PlayedGameNotFoundError().user_message in last_text(gateway)


class TestFavoritesScreen:
    @pytest.fixture()
    def with_records(self, library_service):
        for index in range(5):
            library_service.add_favorite(USER_ID, make_game(100 + index, f"Игра {index}"))
        return library_service

    def test_empty_list(self, screens, gateway, storage):
        screens.favorites.show(CHAT_ID, USER_ID)

        assert texts.FAVORITES_EMPTY in last_text(gateway)
        assert storage.get(USER_ID).screen == ContextScreen.FAVORITES_LIST

    def test_shows_records(self, screens, gateway, with_records):
        screens.favorites.show(CHAT_ID, USER_ID)

        message = last_text(gateway)
        assert texts.FAVORITES_TITLE in message
        assert "1. Игра 4" in message

    def test_buttons_open_cards(self, screens, gateway, with_records):
        screens.favorites.show(CHAT_ID, USER_ID)

        callbacks = last_callbacks(gateway)
        assert len([c for c in callbacks if c.startswith("game:")]) == 3

    def test_saves_games_in_context(self, screens, storage, with_records):
        screens.favorites.show(CHAT_ID, USER_ID)

        context = storage.get(USER_ID)
        assert len(context.games) == 3
        assert context.games[0].id == 104

    def test_pagination(self, screens, gateway, with_records):
        screens.favorites.show(CHAT_ID, USER_ID, page=2)

        callbacks = last_callbacks(gateway)
        assert "favs:1" in callbacks

    def test_card_from_favorites_keeps_source(self, screens, storage, with_records):
        screens.favorites.show(CHAT_ID, USER_ID)
        screens.game_card.show(CHAT_ID, USER_ID, 104, source=ContextScreen.FAVORITES_LIST)

        assert storage.get(USER_ID).list_source == ContextScreen.FAVORITES_LIST

    def test_database_error(self, screens, gateway, library_service, monkeypatch):
        monkeypatch.setattr(
            library_service,
            "get_favorites",
            lambda *args, **kwargs: (_ for _ in ()).throw(DatabaseError()),
        )

        screens.favorites.show(CHAT_ID, USER_ID)

        assert DatabaseError.user_message in last_text(gateway)
