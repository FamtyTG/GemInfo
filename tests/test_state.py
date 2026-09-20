"""Тесты состояния пользователя и хранилища состояний."""

from __future__ import annotations

import threading

import pytest

from gamehunter.presentation.state import ContextScreen, StateStorage, UserContext
from tests.fakes import make_franchise, make_game, make_genre, make_platform

USER_ID = 200


class TestContextScreen:
    def test_default_screen_is_main_menu(self):
        assert UserContext().screen == ContextScreen.MAIN_MENU

    @pytest.mark.parametrize(
        "screen",
        [
            ContextScreen.FRANCHISE_INPUT,
            ContextScreen.AGE_INPUT,
            ContextScreen.IP_INPUT,
            ContextScreen.REVIEW_INPUT,
        ],
    )
    def test_screens_waiting_for_text(self, screen):
        assert screen.is_waiting_for_text() is True

    @pytest.mark.parametrize(
        "screen",
        [
            ContextScreen.MAIN_MENU,
            ContextScreen.PICKING_GENRES,
            ContextScreen.GAME_LIST,
            ContextScreen.GAME_CARD,
            ContextScreen.PROFILE,
            ContextScreen.PLAYED_LIST,
            ContextScreen.FAVORITES_LIST,
        ],
    )
    def test_screens_with_buttons(self, screen):
        assert screen.is_waiting_for_text() is False

    def test_all_screens_have_unique_values(self):
        values = [screen.value for screen in ContextScreen]

        assert len(values) == len(set(values))

    def test_screen_count_matches_documented_map(self):
        # 12 экранов из карты перемещения + режимы анкеты и ввода отзыва
        assert len(list(ContextScreen)) == 16


class TestMainMenu:
    def test_clears_temporary_state(self):
        context = (
            UserContext()
            .at_picking(genre_catalog=[make_genre()], picked_genres=["action"])
            .at_game_list([make_game()], page=2, total_pages=3, filters_line="жанры: Action")
            .at_game_card(32)
        )

        cleared = context.at_main_menu()

        assert cleared.screen == ContextScreen.MAIN_MENU
        assert cleared.games == ()
        assert cleared.genre_catalog == ()
        assert cleared.current_game_id is None
        assert cleared.filters_line == ""
        assert cleared.franchises == ()

    def test_keeps_picked_genres(self):
        context = UserContext().at_picking(picked_genres=["action"])

        assert context.at_main_menu().picked_genres == ("action",)


class TestPicking:
    def test_at_picking_stores_catalog(self):
        genres = [make_genre("Action", "action", 4), make_genre("RPG", "rpg", 5)]

        context = UserContext().at_picking(genre_catalog=genres)

        assert context.screen == ContextScreen.PICKING_GENRES
        assert context.genre_catalog == tuple(genres)

    def test_at_picking_keeps_previous_selection(self):
        context = UserContext().at_picking(picked_genres=["action"]).at_picking(genre_catalog=[make_genre()])

        assert context.picked_genres == ("action",)

    def test_at_picking_can_reset_selection(self):
        context = UserContext().at_picking(picked_genres=["action"]).at_picking(picked_genres=[])

        assert context.picked_genres == ()

    def test_toggle_genre_selects_and_deselects(self):
        context = UserContext().at_picking(genre_catalog=[make_genre("Action", "action", 4)])

        selected = context.toggle_picked_genre("action")
        assert selected.picked_genres == ("action",)

        deselected = selected.toggle_picked_genre("action")
        assert deselected.picked_genres == ()

    def test_toggle_keeps_order(self):
        context = UserContext().at_picking(genre_catalog=[])
        context = context.toggle_picked_genre("action").toggle_picked_genre("rpg")

        assert context.picked_genres == ("action", "rpg")

    def test_toggle_stays_on_picking_screen(self):
        context = UserContext().at_picking(genre_catalog=[make_genre()]).toggle_picked_genre("action")

        assert context.screen == ContextScreen.PICKING_GENRES

    def test_with_picked_genres(self):
        context = UserContext().with_picked_genres(["action", "rpg"])

        assert context.picked_genres == ("action", "rpg")


class TestGameList:
    @pytest.fixture()
    def games(self):
        return [make_game(32), make_game(58175), make_game(4200)]

    def test_at_game_list(self, games):
        context = UserContext().at_game_list(
            games, page=2, total_pages=3, filters_line="жанры: Action", has_next=True, has_previous=True
        )

        assert context.screen == ContextScreen.GAME_LIST
        assert context.games == tuple(games)
        assert context.games_page == 2
        assert context.games_total_pages == 3
        assert context.games_has_next is True
        assert context.games_has_previous is True
        assert context.filters_line == "жанры: Action"
        assert context.current_game_id is None

    def test_played_excluded_flag(self, games):
        context = UserContext().at_game_list(games, played_excluded=True)

        assert context.played_excluded is True

    def test_game_by_id(self, games):
        context = UserContext().at_game_list(games)

        assert context.game_by_id(58175).id == 58175
        assert context.game_by_id(32) is games[0]
        assert context.game_by_id(999) is None

    def test_page_is_at_least_one(self, games):
        context = UserContext().at_game_list(games, page=0, total_pages=0)

        assert context.games_page == 1
        assert context.games_total_pages == 1

    def test_rerender_data_is_available(self, games):
        context = UserContext().at_game_list(games, page=1, total_pages=3, filters_line="без фильтров")

        assert context.games_page == 1
        assert context.filters_line == "без фильтров"


class TestGameCard:
    def test_at_game_card(self):
        context = UserContext().at_game_list([make_game(32)]).at_game_card(32)

        assert context.screen == ContextScreen.GAME_CARD
        assert context.current_game_id == 32
        assert context.list_source == ContextScreen.GAME_LIST

    def test_explicit_source(self):
        context = UserContext().at_game_card(32, list_source=ContextScreen.FAVORITES_LIST)

        assert context.list_source == ContextScreen.FAVORITES_LIST

    def test_source_is_kept_when_card_is_reopened(self):
        context = (
            UserContext()
            .at_favorites([make_game(32)], page=2, total_pages=3)
            .at_game_card(32, list_source=ContextScreen.FAVORITES_LIST)
        )

        reopened = context.at_game_card(32, list_source=ContextScreen.GAME_CARD)

        assert reopened.list_source == ContextScreen.FAVORITES_LIST

    def test_games_are_kept_for_the_back_button(self):
        games = [make_game(32)]
        context = UserContext().at_game_list(games).at_game_card(32)

        assert context.games == tuple(games)


class TestFranchises:
    def test_at_franchise_input_clears_games(self):
        context = UserContext().at_game_list([make_game()]).at_franchise_input()

        assert context.screen == ContextScreen.FRANCHISE_INPUT
        assert context.games == ()
        assert context.franchises == ()
        assert context.franchise_id is None

    def test_with_franchises(self):
        franchises = [make_franchise(1, "Marvel"), make_franchise(2, "Star Wars")]

        context = UserContext().at_franchise_input().with_franchises(franchises)

        assert context.screen == ContextScreen.FRANCHISE_LIST
        assert context.franchises == tuple(franchises)

    def test_franchise_at(self):
        context = UserContext().with_franchises([make_franchise(1, "Marvel"), make_franchise(2, "Star Wars")])

        assert context.franchise_at(2).name == "Star Wars"
        assert context.franchise_at(0) is None
        assert context.franchise_at(5) is None

    def test_at_franchise_games(self):
        games = [make_game(9001)]

        context = UserContext().at_franchise_games(101, games, name="Marvel")

        assert context.screen == ContextScreen.FRANCHISE_GAMES
        assert context.franchise_id == 101
        assert context.franchise_name == "Marvel"
        assert context.games == tuple(games)
        assert context.games_page == 1
        assert context.games_has_next is False


class TestProfileContext:
    def test_at_profile(self):
        assert UserContext().at_profile().screen == ContextScreen.PROFILE

    def test_at_age_input(self):
        context = UserContext().at_age_input()

        assert context.screen == ContextScreen.AGE_INPUT
        assert context.screen.is_waiting_for_text() is True

    def test_at_profile_genres(self):
        genres = [make_genre("Action", "action", 4)]

        context = UserContext().at_profile_genres(genres, ["action"])

        assert context.screen == ContextScreen.PROFILE_GENRES
        assert context.genre_catalog == tuple(genres)
        assert context.profile_genres == ("action",)

    def test_toggle_profile_genre(self):
        context = UserContext().at_profile_genres([make_genre()], [])

        selected = context.toggle_profile_genre("action")
        assert selected.profile_genres == ("action",)

        assert selected.toggle_profile_genre("action").profile_genres == ()

    def test_profile_genres_are_separate_from_picking(self):
        context = UserContext().at_picking(picked_genres=["racing"]).at_profile_genres([], ["action"])

        assert context.picked_genres == ("racing",)
        assert context.profile_genres == ("action",)

    def test_at_profile_platforms(self):
        platforms = [make_platform("PC", "pc", 1)]

        context = UserContext().at_profile_platforms(platforms, [1])

        assert context.screen == ContextScreen.PROFILE_PLATFORMS
        assert context.platform_catalog == tuple(platforms)
        assert context.profile_platforms == (1,)

    def test_toggle_profile_platform(self):
        context = UserContext().at_profile_platforms([make_platform()], [])

        selected = context.toggle_profile_platform(1)
        assert selected.profile_platforms == (1,)

        assert selected.toggle_profile_platform(1).profile_platforms == ()

    def test_at_ip_input(self):
        assert UserContext().at_ip_input().screen == ContextScreen.IP_INPUT


class TestLibraryContext:
    def test_at_played_list(self):
        context = UserContext().at_played_list([1, 2, 3], page=2, total_pages=3)

        assert context.screen == ContextScreen.PLAYED_LIST
        assert context.records == (1, 2, 3)
        assert context.library_page == 2
        assert context.library_total_pages == 3
        assert context.selected_record_id is None

    def test_at_played_info_keeps_page(self):
        context = UserContext().at_played_list([1, 2], page=2, total_pages=3).at_played_info(2)

        assert context.screen == ContextScreen.PLAYED_INFO
        assert context.selected_record_id == 2
        assert context.library_page == 2

    def test_at_review_input(self):
        context = UserContext().at_review_input(5)

        assert context.screen == ContextScreen.REVIEW_INPUT
        assert context.selected_record_id == 5

    def test_at_favorites(self):
        games = [make_game(41494)]

        context = UserContext().at_favorites(games, page=1, total_pages=2)

        assert context.screen == ContextScreen.FAVORITES_LIST
        assert context.games == tuple(games)
        assert context.games_has_next is True
        assert context.games_has_previous is False

    def test_empty_played_list(self):
        context = UserContext().at_played_list(())

        assert context.records == ()
        assert context.library_total_pages == 1


class TestImmutability:
    def test_context_is_frozen(self):
        context = UserContext()

        with pytest.raises(Exception):
            context.screen = ContextScreen.PROFILE  # type: ignore[misc]

    def test_transitions_return_new_objects(self):
        context = UserContext()

        assert context.at_main_menu() is not context
        assert context.at_profile() is not context


class TestStateStorage:
    @pytest.fixture()
    def storage(self) -> StateStorage:
        return StateStorage()

    def test_get_returns_none_for_unknown_user(self, storage: StateStorage):
        assert storage.get(USER_ID) is None

    def test_get_or_default_returns_empty_context(self, storage: StateStorage):
        context = storage.get_or_default(USER_ID)

        assert isinstance(context, UserContext)
        assert context.screen == ContextScreen.MAIN_MENU

    def test_save_and_get(self, storage: StateStorage):
        storage.save(USER_ID, UserContext().at_profile())

        assert storage.get(USER_ID).screen == ContextScreen.PROFILE

    def test_save_returns_context(self, storage: StateStorage):
        context = UserContext().at_profile()

        assert storage.save(USER_ID, context) is context

    def test_get_or_default_returns_saved_context(self, storage: StateStorage):
        storage.save(USER_ID, UserContext().at_profile())

        assert storage.get_or_default(USER_ID).screen == ContextScreen.PROFILE

    def test_has(self, storage: StateStorage):
        assert storage.has(USER_ID) is False

        storage.save(USER_ID, UserContext())

        assert storage.has(USER_ID) is True

    def test_reset(self, storage: StateStorage):
        storage.save(USER_ID, UserContext())
        storage.reset(USER_ID)

        assert storage.has(USER_ID) is False

    def test_reset_unknown_user(self, storage: StateStorage):
        storage.reset(USER_ID)  # не должно вызывать ошибку

        assert storage.has(USER_ID) is False

    def test_clear(self, storage: StateStorage):
        storage.save(1, UserContext())
        storage.save(2, UserContext())

        storage.clear()

        assert len(storage) == 0

    def test_len(self, storage: StateStorage):
        storage.save(1, UserContext())
        storage.save(2, UserContext())

        assert len(storage) == 2

    def test_users_are_isolated(self, storage: StateStorage):
        storage.save(1, UserContext().at_profile())
        storage.save(2, UserContext().at_franchise_input())

        assert storage.get(1).screen == ContextScreen.PROFILE
        assert storage.get(2).screen == ContextScreen.FRANCHISE_INPUT

    def test_thread_safety(self, storage: StateStorage):
        def writer(user_id: int) -> None:
            for _ in range(50):
                storage.save(user_id, UserContext().at_profile())

        threads = [threading.Thread(target=writer, args=(user_id,)) for user_id in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(storage) == 10
        assert all(storage.get(user_id).screen == ContextScreen.PROFILE for user_id in range(10))
