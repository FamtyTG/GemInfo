"""Тесты сущностей доменного слоя."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gamehunter.domain.entities import (
    DATE_FORMAT,
    FavoriteGame,
    Franchise,
    Game,
    GameDetails,
    GamePage,
    GameQuery,
    Genre,
    LibraryPage,
    PlayedGame,
    Platform,
    Region,
    UserProfile,
)
from tests.fakes import (
    make_details,
    make_favorite,
    make_game,
    make_genre,
    make_played,
    make_platform,
    make_profile,
    make_region,
)


# ---------------------------------------------------------------------- #
# Игра
# ---------------------------------------------------------------------- #
class TestGame:
    def test_formatted_released_uses_russian_date_format(self):
        game = make_game(released=date(2015, 5, 19))

        assert game.formatted_released == "19.05.2015"
        assert game.formatted_released == game.released.strftime(DATE_FORMAT)

    def test_formatted_released_when_date_is_unknown(self):
        game = make_game(released=None)

        assert game.formatted_released == "дата выхода не объявлена"

    def test_formatted_released_when_release_is_announced(self):
        game = make_game(released=date(2027, 1, 1), announced=True)

        assert game.formatted_released == "дата выхода не объявлена"

    def test_release_year(self):
        assert make_game(released=date(2018, 4, 20)).release_year == "2018"
        assert make_game(released=None).release_year == "—"

    @pytest.mark.parametrize(
        "rating, expected",
        [(4.64, "4.6"), (5, "5.0"), (0, "0.0"), (None, "без оценки")],
    )
    def test_formatted_rating(self, rating, expected):
        assert make_game(rating=rating).formatted_rating == expected

    def test_genres_and_platforms_text(self):
        game = make_game(genres=("RPG", "Action"), platforms=("PC", "Xbox"))

        assert game.genres_text == "RPG, Action"
        assert game.platforms_text == "PC, Xbox"

    def test_genres_and_platforms_text_when_empty(self):
        game = make_game(genres=(), platforms=())

        assert game.genres_text == "жанр не указан"
        assert game.platforms_text == "платформа не указана"

    def test_has_image(self):
        assert make_game(image_url="https://cdn/img.jpg").has_image is True
        assert make_game(image_url=None).has_image is False
        assert make_game(image_url="").has_image is False

    def test_game_is_immutable(self):
        game = make_game()

        with pytest.raises(Exception):
            game.name = "Другая игра"  # type: ignore[misc]


# ---------------------------------------------------------------------- #
# Карточка игры
# ---------------------------------------------------------------------- #
class TestGameDetails:
    def test_shortcuts_to_game_fields(self):
        game = make_game(game_id=32, name="The Witcher 3", image_url="https://cdn/w.jpg")
        details = make_details(game)

        assert details.name == "The Witcher 3"
        assert details.game_id == 32
        assert details.image_url == "https://cdn/w.jpg"
        assert details.has_image is True

    def test_has_image_without_picture(self):
        details = make_details(make_game(image_url=None))

        assert details.has_image is False

    @pytest.mark.parametrize(
        "min_age, label, expected",
        [
            (17, "ESRB Mature", "ESRB Mature (17+)"),
            (13, "", "13+"),
            (None, "PEGI 16", "PEGI 16"),
            (None, "", "возрастной рейтинг не указан"),
        ],
    )
    def test_formatted_age(self, min_age, label, expected):
        details = make_details(min_age=min_age, age_rating_label=label)

        assert details.formatted_age == expected

    def test_default_fields_are_empty(self):
        details = GameDetails(game=make_game())

        assert details.summary == ""
        assert details.developers == ()
        assert details.stores == ()
        assert details.tags == ()


# ---------------------------------------------------------------------- #
# Справочники
# ---------------------------------------------------------------------- #
class TestCatalogEntities:
    def test_genre_defaults(self):
        genre = Genre(id=4, name="Action", slug="action")

        assert genre.games_count == 0
        assert genre.image_url is None

    def test_platform_defaults(self):
        platform = Platform(id=1, name="PC", slug="pc")

        assert platform.is_parent is True

    def test_franchise_defaults(self):
        franchise = Franchise(id=1, name="Marvel", slug="marvel")

        assert franchise.games_count == 0
        assert franchise.games == ()

    def test_factories_create_expected_objects(self):
        assert isinstance(make_genre(), Genre)
        assert isinstance(make_platform(), Platform)


# ---------------------------------------------------------------------- #
# Параметры поиска и страница результатов
# ---------------------------------------------------------------------- #
class TestGameQuery:
    def test_defaults(self):
        query = GameQuery()

        assert query.genres == ()
        assert query.parent_platforms == ()
        assert query.ordering == "-rating"
        assert query.page == 1
        assert query.exclude_additions is True

    def test_is_empty(self):
        assert GameQuery().is_empty is True
        assert GameQuery(genres=("action",)).is_empty is False
        assert GameQuery(search="witcher").is_empty is False

    def test_with_page_never_below_one(self):
        assert GameQuery().with_page(3).page == 3
        assert GameQuery().with_page(0).page == 1
        assert GameQuery().with_page(-5).page == 1


class TestGamePage:
    def _page(self, games, page_size=3, total_count=9, page=1):
        return GamePage(
            games=list(games),
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_next=True,
            has_previous=page > 1,
        )

    def test_is_empty(self):
        assert self._page([]).is_empty is True
        assert self._page([make_game()]).is_empty is False

    @pytest.mark.parametrize(
        "total_count, page_size, expected",
        [(9, 3, 3), (10, 3, 4), (1, 3, 1), (0, 3, 1), (7, 0, 1)],
    )
    def test_total_pages(self, total_count, page_size, expected):
        page = self._page([make_game()], page_size=page_size, total_count=total_count)

        assert page.total_pages == expected


# ---------------------------------------------------------------------- #
# Регион пользователя
# ---------------------------------------------------------------------- #
class TestRegion:
    def test_title_contains_city_region_and_country(self):
        region = make_region(city="Kazan", country="Russia")
        region = Region(
            ip="8.8.8.8", city=region.city, region_name="Tatarstan", country="Russia"
        )

        assert region.title == "Kazan, Tatarstan, Russia"

    def test_title_falls_back_to_country_code(self):
        region = Region(ip="8.8.8.8", country_code="RU")

        assert region.title == "RU"

    def test_title_when_nothing_is_known(self):
        assert Region(ip="8.8.8.8").title == "не определён"

    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            ({"country": "Russia"}, True),
            ({"city": "Kazan"}, True),
            ({"country_code": "RU"}, True),
            ({}, False),
        ],
    )
    def test_is_known(self, kwargs, expected):
        assert Region(ip="8.8.8.8", **kwargs).is_known is expected


# ---------------------------------------------------------------------- #
# Анкета пользователя
# ---------------------------------------------------------------------- #
class TestUserProfile:
    def test_empty_profile(self):
        profile = UserProfile(tg_user_id=200)

        assert profile.age is None
        assert profile.genre_slugs == ()
        assert profile.region is None
        assert profile.is_filled is False

    def test_with_age(self):
        profile = make_profile(age=None).with_age(21)

        assert profile.age == 21

    def test_with_genres_stores_slugs_and_names(self):
        profile = UserProfile(tg_user_id=200).with_genres(
            (make_genre("Action", "action", 4), make_genre("RPG", "role-playing-games-rpg", 5))
        )

        assert profile.genre_slugs == ("action", "role-playing-games-rpg")
        assert profile.genre_names == ("Action", "RPG")

    def test_with_genres_can_clear_interests(self):
        profile = make_profile().with_genres(())

        assert profile.genre_slugs == ()
        assert profile.genre_names == ()

    def test_with_platforms_stores_ids_and_names(self):
        profile = UserProfile(tg_user_id=200).with_platforms(
            (make_platform("PC", "pc", 1), make_platform("Xbox", "xbox", 3))
        )

        assert profile.platform_ids == (1, 3)
        assert profile.platform_names == ("PC", "Xbox")

    def test_with_region_and_reset(self):
        profile = make_profile().with_region(make_region())
        assert profile.region is not None

        cleared = profile.with_region(None)
        assert cleared.region is None

    def test_interests_and_platforms_text(self):
        profile = make_profile(
            genre_names=("Action", "RPG"), platform_names=("PC", "PlayStation")
        )

        assert profile.interests_text == "Action, RPG"
        assert profile.platforms_text == "PC, PlayStation"

    def test_interests_and_platforms_text_when_empty(self):
        profile = make_profile(genre_names=(), platform_names=())

        assert profile.interests_text == "не указаны"
        assert profile.platforms_text == "не указаны"

    def test_region_text_uses_known_region(self):
        region = Region(ip="1.1.1.1", city="Kazan", country="Russia")
        profile = make_profile(region=region)

        assert profile.region_text == "Kazan, Russia"

    def test_region_text_when_region_is_unknown(self):
        profile = make_profile(region=Region(ip="8.8.8.8"))

        assert profile.region_text == "не определён"

    def test_is_filled(self):
        assert make_profile(age=None, genre_slugs=(), platform_ids=()).is_filled is False
        assert make_profile(age=18, genre_slugs=(), platform_ids=()).is_filled is True
        assert make_profile(age=None, genre_slugs=("action",), platform_ids=()).is_filled is True
        assert make_profile(age=None, genre_slugs=(), platform_ids=(1,)).is_filled is True
        assert make_profile(age=None, genre_slugs=(), platform_ids=(), region=make_region()).is_filled is True


# ---------------------------------------------------------------------- #
# Библиотека пользователя
# ---------------------------------------------------------------------- #
class TestPlayedGame:
    def test_formatted_date(self):
        record = make_played(played_at=datetime(2026, 3, 8, 15, 30))

        assert record.formatted_date == "08.03.2026"

    def test_has_review(self):
        assert make_played(review="Отличная игра").has_review is True
        assert make_played(review=None).has_review is False
        assert make_played(review="   ").has_review is False

    def test_with_review(self):
        record = make_played(review=None).with_review("Хорошо")

        assert record.review == "Хорошо"

    def test_with_review_can_clear_text(self):
        record = make_played(review="Текст").with_review(None)

        assert record.review is None
        assert record.has_review is False


class TestFavoriteGame:
    def test_formatted_date(self):
        record = make_favorite(added_at=datetime(2026, 12, 31))

        assert record.formatted_date == "31.12.2026"

    def test_fields(self):
        record = make_favorite(game_id=41494, name="Cyberpunk 2077")

        assert record.game_id == 41494
        assert record.slug == "cyberpunk-2077"


class TestLibraryPage:
    def test_empty_page(self):
        page: LibraryPage[PlayedGame] = LibraryPage(items=[], page=1, total_pages=1)

        assert page.is_empty is True
        assert page.has_previous is False
        assert page.has_next is False

    def test_first_page_of_three(self):
        page: LibraryPage[PlayedGame] = LibraryPage(
            items=[make_played(record_id=1)], page=1, total_pages=3
        )

        assert page.is_empty is False
        assert page.has_previous is False
        assert page.has_next is True

    def test_last_page(self):
        page: LibraryPage[FavoriteGame] = LibraryPage(
            items=[make_favorite()], page=3, total_pages=3
        )

        assert page.has_previous is True
        assert page.has_next is False
