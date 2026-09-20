"""Тесты текстов сообщений и функций форматирования."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gamehunter.domain.entities import GameDetails, GamePage, LibraryPage, PlayedGame, Region
from gamehunter.presentation import texts
from tests.fakes import (
    make_details,
    make_favorite,
    make_franchise,
    make_game,
    make_genre,
    make_played,
    make_profile,
)


class TestConstants:
    def test_bot_name(self):
        assert texts.BOT_NAME == "GameHunter"
        assert texts.BOT_NAME in texts.START_WELCOME

    def test_start_text_mentions_start_command(self):
        assert "/start" in texts.START_WELCOME

    def test_start_text_mentions_main_menu(self):
        assert "главное меню" in texts.START_WELCOME.lower()

    def test_main_menu_text(self):
        assert texts.BOT_NAME in texts.MAIN_MENU_WELCOME

    def test_unknown_command_text(self):
        assert texts.UNKNOWN_COMMAND.strip()

    def test_generic_error_text(self):
        assert texts.GENERIC_ERROR.strip()

    def test_state_lost_text(self):
        assert "главное меню" in texts.STATE_LOST.lower()

    def test_ip_prompt_explains_how_to_get_ip(self):
        assert "2ip.ru" in texts.PROFILE_IP_PROMPT
        assert "IP" in texts.PROFILE_IP_PROMPT

    def test_review_prompt_mentions_limit(self):
        assert "1000" in texts.REVIEW_PROMPT

    def test_franchise_prompt_gives_examples(self):
        assert "Marvel" in texts.FRANCHISE_INPUT_PROMPT

    def test_played_empty_text_explains_how_to_add(self):
        assert "Уже играл" in texts.PLAYED_EMPTY

    def test_favorites_empty_text_explains_how_to_add(self):
        assert "В избранное" in texts.FAVORITES_EMPTY


class TestFormatGameLine:
    def test_contains_name_year_and_rating(self):
        line = texts.format_game_line(1, make_game(released=date(2015, 5, 19), rating=4.62))

        assert line.startswith("1. The Witcher 3: Wild Hunt")
        assert "2015" in line
        assert "4.6" in line
        assert "RPG" in line

    def test_without_genres(self):
        line = texts.format_game_line(2, make_game(genres=()))

        assert "2." in line
        assert "рейтинг" in line

    def test_without_rating(self):
        line = texts.format_game_line(1, make_game(rating=None))

        assert "без оценки" in line


class TestFormatFilters:
    def test_all_filters(self):
        line = texts.format_filters(["Action", "RPG"], ["PC"], 18)

        assert "жанры: Action, RPG" in line
        assert "платформы: PC" in line
        assert "возраст: 18" in line

    def test_only_genres(self):
        assert texts.format_filters(["RPG"], [], None) == "жанры: RPG"

    def test_without_filters(self):
        assert texts.format_filters([], [], None) == texts.GAMES_NO_FILTERS


class TestFormatGames:
    def _page(self, games, page=1, page_size=3, total=9, has_next=True, has_previous=False):
        return GamePage(
            games=list(games),
            page=page,
            page_size=page_size,
            total_count=total,
            has_next=has_next,
            has_previous=has_previous,
        )

    def test_contains_title_and_filters(self):
        page = self._page([make_game(32, "The Witcher 3")])

        message = texts.format_games(page, "жанры: RPG")

        assert message.startswith(texts.GAMES_TITLE)
        assert "жанры: RPG" in message

    def test_lists_games_with_numbers(self):
        page = self._page([make_game(1, "Первая"), make_game(2, "Вторая")])

        message = texts.format_games(page, "без фильтров")

        assert "1. Первая" in message
        assert "2. Вторая" in message

    def test_shows_page_number(self):
        page = self._page([make_game(1)], page=2, total=9)

        assert "Страница 2 из 3" in texts.format_games(page, "фильтры")

    def test_single_page_is_not_shown(self):
        page = self._page([make_game(1)], page=1, total=3)

        assert "Страница" not in texts.format_games(page, "фильтры")

    def test_played_excluded_note(self):
        page = self._page([make_game(1)])

        assert texts.GAMES_PLAYED_EXCLUDED in texts.format_games(page, "фильтры", played_excluded=True)
        assert texts.GAMES_PLAYED_EXCLUDED not in texts.format_games(page, "фильтры")

    def test_custom_title(self):
        page = self._page([make_game(1)])

        assert texts.format_games(page, "фильтры", title="Игры франшизы Marvel:").startswith(
            "Игры франшизы Marvel:"
        )

    def test_footer_asks_to_choose(self):
        page = self._page([make_game(1)])

        assert texts.format_games(page, "фильтры").endswith(texts.GAMES_FOOTER)

    def test_format_games_list(self):
        message = texts.format_games_list([make_game(1, "Игра")], 1, 2, "жанры: RPG")

        assert "1. Игра" in message
        assert "Страница 1 из 2" in message


class TestFormatGameList:
    def test_lists_games(self):
        message = texts.format_game_list([make_game(1, "Первая"), make_game(2, "Вторая")], "Игры:")

        assert message.startswith("Игры:")
        assert "1. Первая" in message
        assert "2. Вторая" in message
        assert message.endswith(texts.GAMES_FOOTER)


class TestFormatGameCard:
    def test_contains_main_fields(self):
        details = make_details(
            make_game(32, "The Witcher 3: Wild Hunt", rating=4.62, metacritic=93, playtime_hours=50),
            min_age=17,
            age_rating_label="ESRB Mature",
            summary="История ведьмака.",
        )

        message = texts.format_game_card(details)

        assert message.startswith(texts.GAME_CARD_TITLE)
        assert "Название: The Witcher 3: Wild Hunt" in message
        assert "19.05.2015" in message
        assert "4.6" in message
        assert "Metacritic 93" in message
        assert "ESRB Mature (17+)" in message
        assert "Разработчик: CD Projekt RED" in message
        assert "Издатель: CD Projekt" in message
        assert "Магазины: Steam, GOG" in message
        assert "Метки: open world, story rich" in message
        assert "50 ч." in message
        assert "История ведьмака." in message

    def test_genres_and_platforms(self):
        message = texts.format_game_card(make_details(make_game(genres=("RPG",), platforms=("PC",))))

        assert "Жанры: RPG" in message
        assert "Платформы: PC" in message

    def test_status_when_played(self):
        message = texts.format_game_card(make_details(), is_played=True)

        assert texts.GAME_STATUS_PLAYED in message

    def test_status_when_favorite(self):
        message = texts.format_game_card(make_details(), is_favorite=True)

        assert texts.GAME_STATUS_FAVORITE in message

    def test_status_without_flags(self):
        message = texts.format_game_card(make_details())

        assert texts.GAME_STATUS_PLAYED not in message
        assert texts.GAME_STATUS_FAVORITE not in message

    def test_region_is_shown(self):
        profile = make_profile(
            region=Region(ip="5.188.0.1", city="Kazan", country="Russia", currency="RUB")
        )

        message = texts.format_game_card(make_details(), profile=profile)

        assert "Ваш регион:" in message
        assert "Kazan" in message
        assert "RUB" in message

    def test_region_without_currency(self):
        profile = make_profile(region=Region(ip="1.1.1.1", country="Russia"))

        message = texts.format_game_card(make_details(), profile=profile)

        assert "валюта" not in message

    def test_unknown_region_is_not_shown(self):
        profile = make_profile(region=Region(ip="1.1.1.1"))

        assert "Ваш регион:" not in texts.format_game_card(make_details(), profile=profile)

    def test_without_profile(self):
        assert "Ваш регион:" not in texts.format_game_card(make_details())

    def test_without_optional_fields(self):
        details = GameDetails(game=make_game(metacritic=None, playtime_hours=None))

        message = texts.format_game_card(details)

        assert "Metacritic" not in message
        assert "прохождения" not in message
        assert "Разработчик" not in message

    def test_without_summary(self):
        message = texts.format_game_card(make_details(summary=""))

        assert message.strip().endswith(texts.GAME_STATUS_PLAYED) is False

    def test_unknown_age_rating(self):
        details = make_details(min_age=None, age_rating_label="")

        assert "возрастной рейтинг не указан" in texts.format_game_card(details)


class TestFormatFranchises:
    def test_lists_franchises(self):
        franchises = [make_franchise(1, "Marvel", games_count=42), make_franchise(2, "Star Wars", games_count=80)]

        message = texts.format_franchises(franchises)

        assert message.startswith(texts.FRANCHISES_TITLE)
        assert "1. Marvel" in message
        assert "2. Star Wars" in message
        assert "игр в каталоге: 42" in message
        assert message.endswith(texts.FRANCHISES_FOOTER)


class TestFormatGenresSelection:
    def test_lists_genres(self):
        genres = [make_genre("Action", "action", 4), make_genre("RPG", "rpg", 5)]

        message = texts.format_genres_selection(genres, (), "Заголовок", "Подсказка")

        assert message.startswith("Заголовок")
        assert "Action" in message
        assert "RPG" in message
        assert message.endswith("Подсказка")

    def test_selected_genres_are_marked(self):
        genres = [make_genre("Action", "action", 4), make_genre("RPG", "rpg", 5)]

        message = texts.format_genres_selection(genres, ("rpg",), "Заголовок", "Подсказка")

        assert "✔ RPG" in message
        assert "Выбрано: RPG" in message

    def test_without_selection(self):
        message = texts.format_genres_selection([make_genre()], (), "Заголовок", "Подсказка")

        assert "Выбрано:" not in message


class TestFormatProfile:
    def test_filled_profile(self):
        profile = make_profile(
            age=27,
            genre_names=("Action", "RPG"),
            platform_names=("PC", "PlayStation"),
            region=Region(
                ip="5.188.0.1",
                country="Russia",
                country_code="RU",
                city="Kazan",
                timezone="Europe/Moscow",
                currency="RUB",
            ),
        )

        message = texts.format_profile(profile)

        assert message.startswith(texts.PROFILE_TITLE)
        assert "Возраст: 27 лет" in message
        assert "Интересы (жанры): Action, RPG" in message
        assert "Платформы: PC, PlayStation" in message
        assert "Регион: Kazan, Russia" in message
        assert "страна: RU" in message
        assert "часовой пояс: Europe/Moscow" in message
        assert "валюта: RUB" in message
        assert "определён по IP: 5.188.0.1" in message
        assert texts.PROFILE_FOOTER in message

    def test_empty_profile(self):
        message = texts.format_profile(make_profile(age=None, genre_names=(), platform_names=()))

        assert "Возраст: не указан" in message
        assert "Интересы (жанры): не указаны" in message
        assert "Платформы: не указаны" in message
        assert "Регион: не определён" in message

    def test_profile_with_unknown_region(self):
        profile = make_profile(region=Region(ip="1.1.1.1"))

        assert "Регион: не определён" in texts.format_profile(profile)

    def test_region_without_optional_fields(self):
        profile = make_profile(region=Region(ip="1.1.1.1", country="Russia"))

        message = texts.format_profile(profile)

        assert "часовой пояс" not in message
        assert "валюта" not in message


class TestFormatPlayedHistory:
    def test_lists_records(self):
        page: LibraryPage[PlayedGame] = LibraryPage(
            items=[
                make_played(record_id=1, name="The Witcher 3", played_at=datetime(2026, 1, 15)),
                make_played(record_id=2, name="God of War", played_at=datetime(2025, 12, 1)),
            ],
            page=1,
            total_pages=1,
        )

        message = texts.format_played_history(page)

        assert message.startswith(texts.PLAYED_TITLE)
        assert "1. 15.01.2026 — The Witcher 3" in message
        assert "2. 01.12.2025 — God of War" in message
        assert message.endswith(texts.PLAYED_FOOTER)

    def test_shows_page_number(self):
        page: LibraryPage[PlayedGame] = LibraryPage(items=[make_played()], page=2, total_pages=3)

        assert "Страница 2 из 3" in texts.format_played_history(page)

    def test_empty_history_is_not_formatted_here(self):
        page: LibraryPage[PlayedGame] = LibraryPage(items=[], page=1, total_pages=1)

        # Для пустого списка экран показывает отдельный текст
        assert texts.PLAYED_EMPTY.strip()


class TestFormatPlayedInfo:
    def test_with_review(self):
        record = make_played(played_at=datetime(2026, 1, 15), review="Отличная игра")

        message = texts.format_played_info(record)

        assert message.startswith(texts.PLAYED_INFO_TITLE)
        assert "Дата добавления: 15.01.2026" in message
        assert "Игра: The Witcher 3: Wild Hunt" in message
        assert "Отзыв: Отличная игра" in message

    def test_without_review(self):
        message = texts.format_played_info(make_played(review=None))

        assert texts.REVIEW_ABSENT in message
        assert "Отзыв:" not in message

    def test_blank_review_is_treated_as_absent(self):
        message = texts.format_played_info(make_played(review="   "))

        assert texts.REVIEW_ABSENT in message


class TestFormatFavorites:
    def test_lists_favorites(self):
        page = LibraryPage(
            items=[make_favorite(game_id=41494, name="Cyberpunk 2077", added_at=datetime(2026, 2, 1))],
            page=1,
            total_pages=2,
        )

        message = texts.format_favorites(page)

        assert message.startswith(texts.FAVORITES_TITLE)
        assert "1. Cyberpunk 2077" in message
        assert "добавлена: 01.02.2026" in message
        assert "Страница 1 из 2" in message
        assert message.endswith(texts.FAVORITES_FOOTER)

    def test_empty_page(self):
        page = LibraryPage(items=[], page=1, total_pages=1)

        assert texts.format_favorites(page) == texts.FAVORITES_EMPTY


class TestTextLength:
    @pytest.mark.parametrize(
        "message",
        [
            texts.START_WELCOME,
            texts.MAIN_MENU_WELCOME,
            texts.GENRES_TITLE,
            texts.PROFILE_FOOTER,
            texts.PLAYED_EMPTY,
        ],
    )
    def test_messages_fit_telegram_limit(self, message):
        assert len(message) <= 4096

    def test_long_game_list_is_formatted(self):
        games = [make_game(index, f"Очень длинное название игры номер {index}") for index in range(1, 21)]
        page = GamePage(games=games, page=1, page_size=20, total_count=20, has_next=False, has_previous=False)

        message = texts.format_games(page, "жанры: Action")

        assert len(message) <= 4096
        assert "20. Очень длинное название игры номер 20" in message
