"""Тесты клавиатур и callback-данных."""

from __future__ import annotations

import pytest
from telebot.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from gamehunter.presentation import keyboards
from gamehunter.presentation.keyboards import (
    ButtonText,
    Callback,
    CallbackAction,
    parse_callback,
)
from tests.fakes import buttons_of, callbacks_of, make_favorite, make_franchise, make_game, make_genre, make_platform, make_played


# ---------------------------------------------------------------------- #
# Callback-данные
# ---------------------------------------------------------------------- #
class TestParseCallback:
    @pytest.mark.parametrize(
        "data, action, value",
        [
            ("menu", "menu", None),
            ("pick", "pick", None),
            ("pick_show", "pick_show", None),
            ("g:action", "g", "action"),
            ("pg:role-playing-games-rpg", "pg", "role-playing-games-rpg"),
            ("game:32", "game", "32"),
            ("games:2", "games", "2"),
            ("pl:1", "pl", "1"),
            ("frs:3", "frs", "3"),
            ("rec:7", "rec", "7"),
            ("rev:7", "rev", "7"),
            ("del:7", "del", "7"),
            ("favs:2", "favs", "2"),
            ("lib:3", "lib", "3"),
            ("back_games", "back_games", None),
        ],
    )
    def test_parses_action_and_value(self, data, action, value):
        callback = parse_callback(data)

        assert callback == Callback(action=action, value=value)

    @pytest.mark.parametrize("data", [None, "", ":без-действия"])
    def test_invalid_data(self, data):
        assert parse_callback(data) is None

    def test_int_value(self):
        assert Callback(action="game", value="32").int_value == 32
        assert Callback(action="game", value="abc").int_value is None
        assert Callback(action="menu", value=None).int_value is None

    def test_value_with_colon_inside_is_kept(self):
        callback = parse_callback("g:half-life:2")

        assert callback.action == "g"
        assert callback.value == "half-life:2"

    def test_callback_is_immutable(self):
        callback = Callback(action="menu")

        with pytest.raises(Exception):
            callback.action = "pick"  # type: ignore[misc]


class TestCallbackBuilders:
    @pytest.mark.parametrize(
        "builder, args, expected",
        [
            (keyboards.genre_callback, ("action",), "g:action"),
            (keyboards.profile_genre_callback, ("racing",), "pg:racing"),
            (keyboards.platform_callback, (3,), "pl:3"),
            (keyboards.games_page_callback, (2,), "games:2"),
            (keyboards.game_callback, (32,), "game:32"),
            (keyboards.add_played_callback, (32,), "played:32"),
            (keyboards.favorite_callback, (32,), "fav:32"),
            (keyboards.franchise_pick_callback, (1,), "frs:1"),
            (keyboards.played_page_callback, (4,), "lib:4"),
            (keyboards.record_callback, (7,), "rec:7"),
            (keyboards.review_callback, (7,), "rev:7"),
            (keyboards.delete_played_callback, (7,), "del:7"),
            (keyboards.favorites_page_callback, (2,), "favs:2"),
        ],
    )
    def test_builders(self, builder, args, expected):
        assert builder(*args) == expected

    @pytest.mark.parametrize("page", [0, -3])
    def test_page_builders_never_below_one(self, page):
        assert keyboards.games_page_callback(page) == "games:1"
        assert keyboards.played_page_callback(page) == "lib:1"
        assert keyboards.favorites_page_callback(page) == "favs:1"

    def test_round_trip(self):
        data = keyboards.game_callback(58175)

        callback = parse_callback(data)

        assert callback.action == CallbackAction.GAME_CARD
        assert callback.int_value == 58175

    def test_data_fits_telegram_limit(self):
        long_slug = "massively-multiplayer-online-role-playing"

        assert len(keyboards.genre_callback(long_slug)) <= 64
        assert len(keyboards.profile_genre_callback(long_slug)) <= 64
        assert len(keyboards.game_callback(123456789)) <= 64


class TestCallbackActions:
    def test_actions_are_unique(self):
        actions = [
            value
            for name, value in vars(CallbackAction).items()
            if not name.startswith("_") and isinstance(value, str)
        ]

        assert len(actions) == len(set(actions))

    def test_no_action_contains_colon(self):
        actions = [
            value
            for name, value in vars(CallbackAction).items()
            if not name.startswith("_") and isinstance(value, str)
        ]

        assert all(":" not in action for action in actions)


# ---------------------------------------------------------------------- #
# Reply-клавиатуры
# ---------------------------------------------------------------------- #
class TestReplyKeyboards:
    def test_start_keyboard(self):
        markup = keyboards.start_keyboard()

        assert isinstance(markup, ReplyKeyboardMarkup)
        assert buttons_of(markup) == [[ButtonText.START]]
        assert markup.one_time_keyboard is True

    def test_main_menu_keyboard(self):
        markup = keyboards.main_menu_keyboard()

        rows = buttons_of(markup)
        assert [ButtonText.PICK, ButtonText.FRANCHISE] in rows
        assert [ButtonText.PROFILE] in rows
        assert [ButtonText.PLAYED, ButtonText.FAVORITES] in rows

    def test_main_menu_buttons_are_known_texts(self):
        for row in buttons_of(keyboards.main_menu_keyboard()):
            for label in row:
                assert label in keyboards.MENU_BUTTON_TEXTS

    def test_menu_button_texts_contains_start(self):
        assert ButtonText.START in keyboards.MENU_BUTTON_TEXTS

    def test_hide_keyboard(self):
        markup = keyboards.hide_keyboard()

        assert isinstance(markup, ReplyKeyboardRemove)
        assert not hasattr(markup, "keyboard")


# ---------------------------------------------------------------------- #
# Inline-клавиатуры
# ---------------------------------------------------------------------- #
class TestBackToMenu:
    def test_single_button(self):
        markup = keyboards.back_to_menu_keyboard()

        assert buttons_of(markup) == [[ButtonText.BACK_TO_MENU]]
        assert callbacks_of(markup) == [CallbackAction.MAIN_MENU]

    def test_action_menu_keyboard(self):
        markup = keyboards.action_menu_keyboard("Повторить", "pick")

        assert buttons_of(markup) == [["Повторить", ButtonText.BACK_TO_MENU]]
        assert callbacks_of(markup) == ["pick", CallbackAction.MAIN_MENU]

    def test_no_games_keyboard(self):
        callbacks = callbacks_of(keyboards.no_games_keyboard())

        assert CallbackAction.PICK_GENRES in callbacks
        assert CallbackAction.MAIN_MENU in callbacks

    def test_retry_franchise_keyboard(self):
        callbacks = callbacks_of(keyboards.retry_franchise_keyboard())

        assert CallbackAction.FRANCHISE_INPUT in callbacks
        assert CallbackAction.MAIN_MENU in callbacks


class TestGenresKeyboards:
    @pytest.fixture()
    def genres(self):
        return [
            make_genre("Action", "action", 4),
            make_genre("Adventure", "adventure", 3),
            make_genre("RPG", "role-playing-games-rpg", 5),
        ]

    def test_genre_buttons_in_two_columns(self, genres):
        markup = keyboards.picking_genres_keyboard(genres, ())

        rows = buttons_of(markup)
        assert rows[0] == ["Action", "Adventure"]
        assert rows[1] == ["RPG"]

    def test_selected_genres_are_marked(self, genres):
        markup = keyboards.picking_genres_keyboard(genres, ("action",))

        assert buttons_of(markup)[0] == ["✔ Action", "Adventure"]

    def test_genre_callbacks(self, genres):
        callbacks = callbacks_of(keyboards.picking_genres_keyboard(genres, ()))

        assert "g:action" in callbacks
        assert "g:role-playing-games-rpg" in callbacks

    def test_picking_keyboard_has_action_buttons(self, genres):
        labels = [label for row in buttons_of(keyboards.picking_genres_keyboard(genres, ())) for label in row]

        assert ButtonText.SHOW_SELECTION in labels
        assert ButtonText.SHOW_ALL in labels
        assert ButtonText.BACK_TO_MENU in labels

    def test_picking_keyboard_action_callbacks(self, genres):
        callbacks = callbacks_of(keyboards.picking_genres_keyboard(genres, ()))

        assert CallbackAction.PICK_SHOW in callbacks
        assert CallbackAction.PICK_ALL in callbacks
        assert CallbackAction.MAIN_MENU in callbacks

    def test_profile_genres_keyboard(self, genres):
        markup = keyboards.profile_genres_keyboard(genres, ("adventure",))

        callbacks = callbacks_of(markup)
        labels = [label for row in buttons_of(markup) for label in row]

        assert "pg:adventure" in callbacks
        assert "✔ Adventure" in labels
        assert CallbackAction.PROFILE_GENRES_DONE in callbacks
        assert CallbackAction.PROFILE in callbacks
        assert ButtonText.SAVE in labels

    def test_empty_genre_list(self):
        markup = keyboards.picking_genres_keyboard([], ())

        labels = [label for row in buttons_of(markup) for label in row]

        assert ButtonText.SHOW_ALL in labels


class TestPlatformsKeyboard:
    @pytest.fixture()
    def platforms(self):
        return [make_platform(f"Платформа {index}", f"platform-{index}", index) for index in range(1, 11)]

    def test_limit_by_default(self, platforms):
        markup = keyboards.platforms_keyboard(platforms, ())

        assert len(callbacks_of(markup)) - 2 == 8  # 8 платформ + «Сохранить» + «Назад»

    def test_custom_limit(self, platforms):
        markup = keyboards.platforms_keyboard(platforms, (), limit=4)

        assert len(callbacks_of(markup)) - 2 == 4

    def test_selected_platforms_are_marked(self, platforms):
        markup = keyboards.platforms_keyboard(platforms[:4], (2,))

        assert buttons_of(markup)[0] == ["Платформа 1", "✔ Платформа 2"]

    def test_callbacks_and_actions(self, platforms):
        markup = keyboards.platforms_keyboard(platforms[:2], ())

        callbacks = callbacks_of(markup)
        labels = [label for row in buttons_of(markup) for label in row]

        assert "pl:1" in callbacks
        assert CallbackAction.PROFILE_PLATFORMS_DONE in callbacks
        assert CallbackAction.PROFILE in callbacks
        assert ButtonText.SAVE in labels


class TestGamesKeyboard:
    @pytest.fixture()
    def games(self):
        return [make_game(32), make_game(58175, "God of War"), make_game(4200, "Portal 2")]

    def test_game_buttons(self, games):
        markup = keyboards.games_keyboard(games, page=1)

        rows = buttons_of(markup)
        assert rows[0] == [ButtonText.SELECT_GAME.format(1)]
        assert callbacks_of(markup)[:3] == ["game:32", "game:58175", "game:4200"]

    def test_pagination_buttons(self, games):
        markup = keyboards.games_keyboard(games, page=2, has_next=True, has_previous=True)

        callbacks = callbacks_of(markup)
        assert "games:1" in callbacks
        assert "games:3" in callbacks

    def test_no_pagination_on_single_page(self, games):
        callbacks = callbacks_of(keyboards.games_keyboard(games, page=1))

        assert not any(callback.startswith("games:") for callback in callbacks)

    def test_forward_only_on_first_page(self, games):
        callbacks = callbacks_of(keyboards.games_keyboard(games, page=1, has_next=True))

        assert "games:2" in callbacks
        assert "games:0" not in callbacks

    def test_back_action_default(self, games):
        markup = keyboards.games_keyboard(games, page=1)

        callbacks = callbacks_of(markup)
        labels = [label for row in buttons_of(markup) for label in row]

        assert CallbackAction.PICK_GENRES in callbacks
        assert ButtonText.OTHER_GENRES in labels

    def test_custom_back_action(self, games):
        markup = keyboards.games_keyboard(
            games, page=1, back_action=CallbackAction.MAIN_MENU, back_label="Другой раздел"
        )

        labels = [label for row in buttons_of(markup) for label in row]

        assert "Другой раздел" in labels
        assert callbacks_of(markup).count(CallbackAction.MAIN_MENU) == 2

    def test_menu_button_is_last(self, games):
        rows = buttons_of(keyboards.games_keyboard(games, page=1))

        assert rows[-1] == [ButtonText.BACK_TO_MENU]


class TestGameCardKeyboard:
    def test_buttons(self):
        markup = keyboards.game_card_keyboard(32)

        labels = [label for row in buttons_of(markup) for label in row]
        callbacks = callbacks_of(markup)

        assert labels[0] == ButtonText.ADD_PLAYED
        assert labels[1] == ButtonText.ADD_FAVORITE
        assert "played:32" in callbacks
        assert "fav:32" in callbacks
        assert CallbackAction.BACK_GAMES in callbacks
        assert CallbackAction.MAIN_MENU in callbacks

    def test_favorite_label_when_already_favorite(self):
        markup = keyboards.game_card_keyboard(32, is_favorite=True)

        assert ButtonText.REMOVE_FAVORITE in buttons_of(markup)[0]

    def test_two_rows(self):
        assert len(buttons_of(keyboards.game_card_keyboard(32))) == 2


class TestFranchiseKeyboards:
    def test_franchises_keyboard(self):
        franchises = [make_franchise(1, "Marvel"), make_franchise(2, "Star Wars")]

        markup = keyboards.franchises_keyboard(franchises)

        labels = [label for row in buttons_of(markup) for label in row]
        callbacks = callbacks_of(markup)

        assert ButtonText.SELECT_FRANCHISE.format(1) in labels
        assert "frs:1" in callbacks
        assert "frs:2" in callbacks
        assert CallbackAction.FRANCHISE_INPUT in callbacks
        assert CallbackAction.MAIN_MENU in callbacks

    def test_franchise_games_keyboard(self):
        games = [make_game(9001, "Marvel's Spider-Man")]

        markup = keyboards.franchise_games_keyboard(games)

        assert callbacks_of(markup)[0] == "game:9001"
        assert ButtonText.OTHER_FRANCHISE in [label for row in buttons_of(markup) for label in row]


class TestProfileKeyboard:
    def test_default_buttons(self):
        markup = keyboards.profile_keyboard()

        labels = [label for row in buttons_of(markup) for label in row]
        callbacks = callbacks_of(markup)

        assert ButtonText.SET_AGE in labels
        assert ButtonText.SET_GENRES in labels
        assert ButtonText.SET_PLATFORMS in labels
        assert ButtonText.SET_REGION in labels
        assert ButtonText.BACK_TO_MENU in labels
        assert ButtonText.RESET_AGE not in labels
        assert ButtonText.RESET_REGION not in labels
        assert CallbackAction.PROFILE_AGE in callbacks
        assert CallbackAction.PROFILE_IP in callbacks

    def test_reset_age_button(self):
        labels = [label for row in buttons_of(keyboards.profile_keyboard(has_age=True)) for label in row]

        assert ButtonText.RESET_AGE in labels
        assert CallbackAction.PROFILE_AGE_RESET in callbacks_of(keyboards.profile_keyboard(has_age=True))

    def test_reset_region_button(self):
        markup = keyboards.profile_keyboard(has_region=True)

        assert ButtonText.RESET_REGION in [label for row in buttons_of(markup) for label in row]
        assert CallbackAction.PROFILE_IP_RESET in callbacks_of(markup)


class TestLibraryKeyboards:
    def test_played_list_keyboard(self):
        records = [make_played(record_id=1), make_played(record_id=2, game_id=58175)]

        markup = keyboards.played_list_keyboard(records, page=1, total_pages=3)

        labels = [label for row in buttons_of(markup) for label in row]
        callbacks = callbacks_of(markup)

        assert labels[0] == ButtonText.SELECT_GAME.format(1)
        assert "rec:1" in callbacks
        assert "rec:2" in callbacks
        assert "lib:2" in callbacks
        assert "lib:0" not in callbacks

    def test_played_list_pagination_back(self):
        records = [make_played(record_id=1)]

        callbacks = callbacks_of(keyboards.played_list_keyboard(records, page=2, total_pages=3))

        assert "lib:1" in callbacks
        assert "lib:3" in callbacks

    def test_played_list_last_page(self):
        records = [make_played(record_id=1)]

        callbacks = callbacks_of(keyboards.played_list_keyboard(records, page=3, total_pages=3))

        assert "lib:4" not in callbacks
        assert "lib:2" in callbacks

    def test_empty_played_list(self):
        markup = keyboards.played_list_keyboard([], page=1, total_pages=1)

        assert buttons_of(markup) == [[ButtonText.BACK_TO_MENU]]

    def test_played_info_keyboard(self):
        markup = keyboards.played_info_keyboard(7, library_page=2)

        callbacks = callbacks_of(markup)
        labels = [label for row in buttons_of(markup) for label in row]

        assert "rev:7" in callbacks
        assert "del:7" in callbacks
        assert "lib:2" in callbacks
        assert CallbackAction.MAIN_MENU in callbacks
        assert ButtonText.WRITE_REVIEW in labels
        assert ButtonText.DELETE_PLAYED in labels

    def test_favorites_keyboard(self):
        records = [make_favorite(record_id=1, game_id=41494), make_favorite(record_id=2, game_id=28)]

        markup = keyboards.favorites_keyboard(records, page=1, total_pages=2)

        callbacks = callbacks_of(markup)

        assert "game:41494" in callbacks
        assert "game:28" in callbacks
        assert "favs:2" in callbacks

    def test_empty_favorites(self):
        markup = keyboards.favorites_keyboard([], page=1, total_pages=1)

        assert buttons_of(markup) == [[ButtonText.BACK_TO_MENU]]


class TestMarkupTypes:
    @pytest.mark.parametrize(
        "markup",
        [
            keyboards.back_to_menu_keyboard(),
            keyboards.picking_genres_keyboard([make_genre()], ()),
            keyboards.games_keyboard([make_game()], 1),
            keyboards.game_card_keyboard(1),
            keyboards.franchises_keyboard([make_franchise()]),
            keyboards.profile_keyboard(),
            keyboards.played_list_keyboard([make_played()], 1, 1),
            keyboards.played_info_keyboard(1),
            keyboards.favorites_keyboard([make_favorite()], 1, 1),
            keyboards.no_games_keyboard(),
        ],
    )
    def test_all_keyboards_are_inline_markups(self, markup):
        assert isinstance(markup, InlineKeyboardMarkup)
        assert markup.keyboard
