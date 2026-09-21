"""Тесты клиента RAWG Video Games Database API."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gamehunter.domain.entities import GameQuery
from gamehunter.domain.exceptions import (
    ExternalServiceError,
    FranchiseSearchUnavailableError,
    GamesUnavailableError,
    GenresUnavailableError,
)
from gamehunter.infrastructure.api.http_client import JsonHttpClient
from gamehunter.infrastructure.api.rawg_client import (
    PARENT_PLATFORM_FALLBACK,
    RawgClient,
    parse_release_date,
    strip_html,
)
from tests.fakes import FakeResponse, FakeSession

API_KEY = "test-rawg-key"


# ---------------------------------------------------------------------- #
# Примеры ответов API
# ---------------------------------------------------------------------- #
GAME_ITEM = {
    "id": 32,
    "slug": "the-witcher-3-wild-hunt",
    "name": "The Witcher 3: Wild Hunt",
    "released": "2015-05-18",
    "tba": False,
    "background_image": "https://cdn.rawg.io/witcher3.jpg",
    "rating": 4.62,
    "metacritic": 93,
    "playtime": 50,
    "genres": [
        {"id": 5, "name": "RPG", "slug": "role-playing-games-rpg"},
        {"id": 4, "name": "Action", "slug": "action"},
    ],
    "parent_platforms": [
        {"platform": {"id": 1, "name": "PC", "slug": "pc"}},
        {"platform": {"id": 2, "name": "PlayStation", "slug": "playstation"}},
    ],
}

GAMES_PAYLOAD = {
    "count": 7,
    "next": "https://api.rawg.io/api/games?page=2",
    "previous": None,
    "results": [GAME_ITEM],
}

GENRES_PAYLOAD = {
    "results": [
        {
            "id": 4,
            "name": "Action",
            "slug": "action",
            "games_count": 500000,
            "image_background": "https://cdn.rawg.io/action.jpg",
        },
        {"id": 5, "name": "RPG", "slug": "role-playing-games-rpg", "games_count": 100000},
    ]
}

PLATFORMS_PAYLOAD = {
    "result": [
        {"id": 1, "name": "PC", "slug": "pc", "games_count": 300000},
        {"id": 2, "name": "PlayStation", "slug": "playstation", "games_count": 200000},
    ]
}

DETAILS_PAYLOAD = {
    "id": 32,
    "slug": "the-witcher-3-wild-hunt",
    "name": "The Witcher 3: Wild Hunt",
    "released": "2015-05-18",
    "rating": 4.62,
    "metacritic": 93,
    "playtime": 50,
    "background_image": "https://cdn.rawg.io/witcher3.jpg",
    "description": "<p>История <b>ведьмака</b> Геральта.</p>",
    "description_raw": "История ведьмака Геральта.",
    "esrb_rating": {"id": 4, "name": "Mature", "slug": "mature"},
    "developers": [{"id": 1, "name": "CD Projekt RED"}],
    "publishers": [{"id": 2, "name": "CD Projekt"}],
    "stores": [
        {"id": 10, "store": {"id": 1, "name": "Steam"}},
        {"id": 11, "store": {"id": 5, "name": "GOG"}},
    ],
    "tags": [{"id": 1, "name": "open world"}, {"id": 2, "name": "story rich"}],
    "genres": [{"id": 5, "name": "RPG", "slug": "role-playing-games-rpg"}],
    "parent_platforms": [{"platform": {"id": 1, "name": "PC", "slug": "pc"}}],
}

FRANCHISES_PAYLOAD = {
    "results": [
        {"id": 101, "name": "Marvel", "slug": "marvel", "games_count": 42},
        {"id": 102, "name": "Marvel Ultimate", "slug": "marvel-ultimate", "games_count": 5},
    ]
}

FRANCHISE_PAYLOAD = {
    "id": 101,
    "name": "Marvel",
    "slug": "marvel",
    "games_count": 42,
    "games": [
        {
            "id": 9001,
            "slug": "marvels-spider-man",
            "name": "Marvel's Spider-Man",
            "released": "2018-09-07",
            "rating": 4.5,
        },
        {
            "id": 9002,
            "slug": "marvels-guardians-of-the-galaxy",
            "name": "Marvel's Guardians of the Galaxy",
            "released": "2021-10-26",
            "rating": 4.2,
        },
    ],
}


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def client(session: FakeSession) -> RawgClient:
    return RawgClient(
        JsonHttpClient(timeout=5, session=session), api_key=API_KEY, page_size=3, language="ru"
    )


def respond(session: FakeSession, payload, status_code: int = 200) -> None:
    session.responses.append(FakeResponse(json_data=payload, status_code=status_code))


def last_request(session: FakeSession):
    return session.requests[-1]


# ---------------------------------------------------------------------- #
# Общие свойства клиента
# ---------------------------------------------------------------------- #
class TestClientBasics:
    def test_is_configured(self, client: RawgClient):
        assert client.is_configured is True

    def test_is_not_configured_without_key(self, session: FakeSession):
        client = RawgClient(JsonHttpClient(session=session), api_key="")

        assert client.is_configured is False

    def test_requests_go_to_rawg_base_url(self, client: RawgClient, session: FakeSession):
        respond(session, GENRES_PAYLOAD)

        client.fetch_genres()

        assert last_request(session)["url"] == "https://api.rawg.io/api/genres"

    def test_api_key_is_sent_as_query_parameter(self, client: RawgClient, session: FakeSession):
        respond(session, GENRES_PAYLOAD)

        client.fetch_genres()

        assert last_request(session)["params"]["key"] == API_KEY

    def test_language_is_sent(self, client: RawgClient, session: FakeSession):
        respond(session, GENRES_PAYLOAD)

        client.fetch_genres()

        assert last_request(session)["params"]["language"] == "ru"

    def test_language_can_be_disabled(self, session: FakeSession):
        client = RawgClient(JsonHttpClient(session=session), api_key=API_KEY, language="")
        respond(session, GENRES_PAYLOAD)

        client.fetch_genres()

        assert "language" not in last_request(session)["params"]

    @pytest.mark.parametrize(
        "method, args, error",
        [
            ("fetch_genres", (), GenresUnavailableError),
            ("fetch_platforms", (), GenresUnavailableError),
            ("search_games", (GameQuery(),), GamesUnavailableError),
            ("fetch_game_details", (32,), GamesUnavailableError),
            ("search_franchises", ("marvel", 5), FranchiseSearchUnavailableError),
            ("fetch_franchise_games", (101, 5), FranchiseSearchUnavailableError),
        ],
    )
    def test_without_api_key_no_request_is_made(self, session: FakeSession, method, args, error):
        client = RawgClient(JsonHttpClient(session=session), api_key="")

        with pytest.raises(error) as info:
            getattr(client, method)(*args)

        assert info.value.reason == "api key is not configured"
        assert session.requests == []

    def test_service_error_is_converted_to_domain_error(
        self, client: RawgClient, session: FakeSession
    ):
        session.error = ExternalServiceError("rawg", "timeout")

        with pytest.raises(GenresUnavailableError):
            client.fetch_genres()

    def test_unexpected_error_is_converted(self, client: RawgClient, session: FakeSession):
        session.error = RuntimeError("boom")

        with pytest.raises(GamesUnavailableError) as info:
            client.search_games(GameQuery())

        assert info.value.service == "rawg"

    def test_domain_error_is_passed_through(self, client: RawgClient, session: FakeSession):
        session.error = GamesUnavailableError("rawg", "http 500")

        with pytest.raises(GamesUnavailableError):
            client.search_games(GameQuery())


# ---------------------------------------------------------------------- #
# Жанры
# ---------------------------------------------------------------------- #
class TestFetchGenres:
    def test_parses_genres(self, client: RawgClient, session: FakeSession):
        respond(session, GENRES_PAYLOAD)

        genres = client.fetch_genres()

        assert [genre.slug for genre in genres] == ["action", "role-playing-games-rpg"]
        assert genres[0].name == "Action"
        assert genres[0].id == 4
        assert genres[0].games_count == 500000
        assert genres[0].image_url == "https://cdn.rawg.io/action.jpg"

    def test_skips_items_without_name_or_slug(self, client: RawgClient, session: FakeSession):
        respond(
            session,
            {
                "results": [
                    {"id": 1, "name": "", "slug": "empty-name"},
                    {"id": 2, "name": "Без slug", "slug": ""},
                    {"id": 3, "name": "RPG", "slug": "rpg"},
                    "не словарь",
                ]
            },
        )

        genres = client.fetch_genres()

        assert [genre.slug for genre in genres] == ["rpg"]

    def test_empty_response(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": []})

        assert client.fetch_genres() == []

    def test_response_without_results(self, client: RawgClient, session: FakeSession):
        respond(session, {})

        assert client.fetch_genres() == []

    def test_http_error(self, client: RawgClient, session: FakeSession):
        respond(session, {"detail": "Unauthorized"}, status_code=401)

        with pytest.raises(GenresUnavailableError):
            client.fetch_genres()


# ---------------------------------------------------------------------- #
# Платформы
# ---------------------------------------------------------------------- #
class TestFetchPlatforms:
    def test_parses_parent_platforms(self, client: RawgClient, session: FakeSession):
        respond(session, PLATFORMS_PAYLOAD)

        platforms = client.fetch_platforms()

        assert [platform.slug for platform in platforms] == ["pc", "playstation"]
        assert platforms[0].is_parent is True
        assert platforms[0].games_count == 300000

    def test_requests_parents_list(self, client: RawgClient, session: FakeSession):
        respond(session, PLATFORMS_PAYLOAD)

        client.fetch_platforms()

        assert last_request(session)["url"].endswith("/platforms/lists/parents")

    def test_accepts_results_key(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": [{"id": 1, "name": "PC", "slug": "pc"}]})

        platforms = client.fetch_platforms()

        assert [platform.name for platform in platforms] == ["PC"]

    def test_fallback_when_response_is_empty(self, client: RawgClient, session: FakeSession):
        respond(session, {})

        platforms = client.fetch_platforms()

        assert [(platform.id, platform.name) for platform in platforms] == [
            (pid, name) for pid, name, _ in PARENT_PLATFORM_FALLBACK
        ]

    def test_fallback_when_endpoint_is_missing(self, client: RawgClient, session: FakeSession):
        respond(session, {}, status_code=404)

        assert len(client.fetch_platforms()) == len(PARENT_PLATFORM_FALLBACK)

    def test_fallback_when_items_are_invalid(self, client: RawgClient, session: FakeSession):
        respond(session, {"result": [{"id": 0, "name": ""}, "строка"]})

        platforms = client.fetch_platforms()

        assert platforms[0].name == "PC"


# ---------------------------------------------------------------------- #
# Поиск игр
# ---------------------------------------------------------------------- #
class TestSearchGames:
    def test_parses_games(self, client: RawgClient, session: FakeSession):
        respond(session, GAMES_PAYLOAD)

        page = client.search_games(GameQuery(page_size=3))

        assert len(page.games) == 1
        game = page.games[0]
        assert game.id == 32
        assert game.name == "The Witcher 3: Wild Hunt"
        assert game.released == date(2015, 5, 18)
        assert game.rating == pytest.approx(4.62)
        assert game.metacritic == 93
        assert game.playtime_hours == 50
        assert game.genres == ("RPG", "Action")
        assert game.platforms == ("PC", "PlayStation")
        assert game.image_url == "https://cdn.rawg.io/witcher3.jpg"

    def test_pagination_flags(self, client: RawgClient, session: FakeSession):
        respond(session, GAMES_PAYLOAD)

        page = client.search_games(GameQuery(page=1, page_size=3))

        assert page.total_count == 7
        assert page.total_pages == 3
        assert page.has_next is True
        assert page.has_previous is False

    def test_previous_page_flag(self, client: RawgClient, session: FakeSession):
        respond(session, {**GAMES_PAYLOAD, "previous": "https://api.rawg.io/api/games?page=1"})

        page = client.search_games(GameQuery(page=2, page_size=3))

        assert page.has_previous is True
        assert page.page == 2

    def test_count_falls_back_to_number_of_games(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": [GAME_ITEM], "next": None})

        page = client.search_games(GameQuery())

        assert page.total_count == 1

    def test_filters_are_sent_as_parameters(self, client: RawgClient, session: FakeSession):
        respond(session, GAMES_PAYLOAD)

        client.search_games(
            GameQuery(
                genres=("action", "role-playing-games-rpg"),
                parent_platforms=(1, 2),
                search="witcher",
                ordering="-rating",
                page=2,
                page_size=5,
                exclude_game_ids=(32, 58175),
                exclude_additions=True,
            )
        )

        params = last_request(session)["params"]
        assert params["genres"] == "action,role-playing-games-rpg"
        assert params["parent_platforms"] == "1,2"
        assert params["search"] == "witcher"
        assert params["ordering"] == "-rating"
        assert params["page"] == 2
        assert params["page_size"] == 5
        assert params["exclude_games"] == "32,58175"
        assert params["exclude_additions"] == "true"

    def test_empty_filters_are_not_sent(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": [], "count": 0})

        client.search_games(GameQuery(exclude_additions=False))

        params = last_request(session)["params"]
        for key in ("genres", "parent_platforms", "search", "exclude_games", "exclude_additions"):
            assert key not in params

    def test_page_and_page_size_are_at_least_one(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": [], "count": 0})

        client.search_games(GameQuery(page=0, page_size=0))

        params = last_request(session)["params"]
        assert params["page"] == 1
        assert params["page_size"] == 1

    def test_invalid_items_are_skipped(self, client: RawgClient, session: FakeSession):
        respond(
            session,
            {
                "count": 3,
                "results": [
                    {"id": 1, "name": ""},
                    {"id": 0, "name": "Без id"},
                    "строка",
                    GAME_ITEM,
                ],
            },
        )

        page = client.search_games(GameQuery())

        assert [game.id for game in page.games] == [32]

    def test_tba_game_is_marked_as_announced(self, client: RawgClient, session: FakeSession):
        respond(
            session,
            {"results": [{**GAME_ITEM, "tba": True, "released": None}], "count": 1},
        )

        game = client.search_games(GameQuery()).games[0]

        assert game.announced is True
        assert game.formatted_released == "дата выхода не объявлена"

    def test_platforms_fall_back_to_platform_field(self, client: RawgClient, session: FakeSession):
        item = {k: v for k, v in GAME_ITEM.items() if k != "parent_platforms"}
        item["platforms"] = [{"platform": {"id": 4, "name": "PC", "slug": "pc"}}]
        respond(session, {"results": [item], "count": 1})

        game = client.search_games(GameQuery()).games[0]

        assert game.platforms == ("PC",)

    def test_zero_metacritic_and_playtime_become_none(self, client: RawgClient, session: FakeSession):
        respond(
            session, {"results": [{**GAME_ITEM, "metacritic": 0, "playtime": 0}], "count": 1}
        )

        game = client.search_games(GameQuery()).games[0]

        assert game.metacritic is None
        assert game.playtime_hours is None

    def test_http_error(self, client: RawgClient, session: FakeSession):
        respond(session, {"detail": "error"}, status_code=500)

        with pytest.raises(GamesUnavailableError):
            client.search_games(GameQuery())


# ---------------------------------------------------------------------- #
# Карточка игры
# ---------------------------------------------------------------------- #
class TestFetchGameDetails:
    def test_parses_details(self, client: RawgClient, session: FakeSession):
        respond(session, DETAILS_PAYLOAD)

        details = client.fetch_game_details(32)

        assert details is not None
        assert details.game_id == 32
        assert details.summary == "История ведьмака Геральта."
        assert details.min_age == 17
        assert details.age_rating_label == "Mature"
        assert details.developers == ("CD Projekt RED",)
        assert details.publishers == ("CD Projekt",)
        assert details.stores == ("Steam", "GOG")
        assert details.tags == ("open world", "story rich")

    def test_requests_game_by_id(self, client: RawgClient, session: FakeSession):
        respond(session, DETAILS_PAYLOAD)

        client.fetch_game_details(58175)

        assert last_request(session)["url"].endswith("/games/58175")

    def test_description_is_used_when_raw_is_absent(self, client: RawgClient, session: FakeSession):
        payload = {k: v for k, v in DETAILS_PAYLOAD.items() if k != "description_raw"}
        respond(session, payload)

        details = client.fetch_game_details(32)

        assert details.summary == "История ведьмака Геральта."

    def test_html_is_stripped(self, client: RawgClient, session: FakeSession):
        respond(session, {**DETAILS_PAYLOAD, "description_raw": "<p>Текст &amp; <b>жирный</b></p>"})

        details = client.fetch_game_details(32)

        assert details.summary == "Текст & жирный"

    def test_not_found_returns_none(self, client: RawgClient, session: FakeSession):
        respond(session, {}, status_code=404)

        assert client.fetch_game_details(999999) is None

    def test_detail_not_found_body_returns_none(self, client: RawgClient, session: FakeSession):
        respond(session, {"detail": "Not found."})

        assert client.fetch_game_details(999999) is None

    def test_empty_payload_returns_none(self, client: RawgClient, session: FakeSession):
        respond(session, {})

        assert client.fetch_game_details(32) is None

    def test_payload_without_name_returns_none(self, client: RawgClient, session: FakeSession):
        respond(session, {"id": 32, "slug": "game"})

        assert client.fetch_game_details(32) is None

    def test_missing_id_is_taken_from_request(self, client: RawgClient, session: FakeSession):
        payload = {k: v for k, v in DETAILS_PAYLOAD.items() if k != "id"}
        respond(session, payload)

        details = client.fetch_game_details(32)

        assert details.game_id == 32

    @pytest.mark.parametrize(
        "rating, expected_age, expected_label",
        [
            ({"id": 4, "name": "Mature", "slug": "mature"}, 17, "Mature"),
            ({"id": 3, "name": "Teen", "slug": "teen"}, 13, "Teen"),
            ("E10+", 10, "E10+"),
        ],
    )
    def test_esrb_rating_variants(self, client: RawgClient, session: FakeSession, rating, expected_age, expected_label):
        respond(session, {**DETAILS_PAYLOAD, "esrb_rating": rating})

        details = client.fetch_game_details(32)

        assert details.min_age == expected_age
        assert details.age_rating_label == expected_label

    def test_pegi_from_age_ratings_list(self, client: RawgClient, session: FakeSession):
        payload = {k: v for k, v in DETAILS_PAYLOAD.items() if k != "esrb_rating"}
        payload["age_ratings"] = [{"id": 1, "title": "PEGI 16"}]
        respond(session, payload)

        details = client.fetch_game_details(32)

        assert details.min_age == 16
        assert details.age_rating_label == "PEGI 16"

    def test_pegi_field_is_used(self, client: RawgClient, session: FakeSession):
        payload = {k: v for k, v in DETAILS_PAYLOAD.items() if k != "esrb_rating"}
        payload["pegi"] = {"name": "PEGI 12"}
        respond(session, payload)

        assert client.fetch_game_details(32).min_age == 12

    def test_unknown_rating(self, client: RawgClient, session: FakeSession):
        payload = {k: v for k, v in DETAILS_PAYLOAD.items() if k != "esrb_rating"}
        respond(session, payload)

        details = client.fetch_game_details(32)

        assert details.min_age is None
        assert details.age_rating_label == ""

    def test_stores_are_limited(self, client: RawgClient, session: FakeSession):
        stores = [{"id": index, "store": {"id": index, "name": f"Магазин {index}"}} for index in range(10)]
        respond(session, {**DETAILS_PAYLOAD, "stores": stores})

        details = client.fetch_game_details(32)

        assert len(details.stores) == 6

    def test_duplicate_names_are_removed(self, client: RawgClient, session: FakeSession):
        respond(
            session,
            {
                **DETAILS_PAYLOAD,
                "tags": [{"id": 1, "name": "open world"}, {"id": 2, "name": "open world"}],
            },
        )

        assert client.fetch_game_details(32).tags == ("open world",)

    def test_http_error(self, client: RawgClient, session: FakeSession):
        respond(session, {"detail": "error"}, status_code=500)

        with pytest.raises(GamesUnavailableError):
            client.fetch_game_details(32)


# ---------------------------------------------------------------------- #
# Франшизы (IP)
# ---------------------------------------------------------------------- #
class TestFranchises:
    def test_search_franchises(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISES_PAYLOAD)

        franchises = client.search_franchises("marvel", limit=5)

        assert [item.name for item in franchises] == ["Marvel", "Marvel Ultimate"]
        assert franchises[0].id == 101
        assert franchises[0].games_count == 42

    def test_search_parameters(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISES_PAYLOAD)

        client.search_franchises("  Marvel  ", limit=3)

        params = last_request(session)["params"]
        assert params["search"] == "Marvel"
        assert params["page_size"] == 3
        assert params["ordering"] == "-games_count"

    def test_page_size_is_capped(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISES_PAYLOAD)

        client.search_franchises("marvel", limit=100)

        assert last_request(session)["params"]["page_size"] == 20

    def test_page_size_is_at_least_one(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISES_PAYLOAD)

        client.search_franchises("marvel", limit=0)

        assert last_request(session)["params"]["page_size"] == 1

    def test_invalid_items_are_skipped(self, client: RawgClient, session: FakeSession):
        respond(session, {"results": [{"id": 0, "name": ""}, {"id": 5, "name": "Warcraft", "slug": "warcraft"}]})

        franchises = client.search_franchises("warcraft", limit=5)

        assert [item.id for item in franchises] == [5]

    def test_search_error(self, client: RawgClient, session: FakeSession):
        respond(session, {"detail": "error"}, status_code=500)

        with pytest.raises(FranchiseSearchUnavailableError):
            client.search_franchises("marvel", limit=5)

    def test_franchise_games(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISE_PAYLOAD)

        games = client.fetch_franchise_games(101, limit=5)

        assert [game.id for game in games] == [9001, 9002]
        assert games[0].name == "Marvel's Spider-Man"
        assert last_request(session)["url"].endswith("/franchises/101")

    def test_franchise_games_limit(self, client: RawgClient, session: FakeSession):
        respond(session, FRANCHISE_PAYLOAD)

        assert len(client.fetch_franchise_games(101, limit=1)) == 1

    def test_franchise_games_fallback_to_search(self, client: RawgClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={"id": 101, "name": "Marvel", "games": []}))
        session.responses.append(FakeResponse(json_data=GAMES_PAYLOAD))

        games = client.fetch_franchise_games(101, limit=3)

        assert [game.id for game in games] == [32]
        assert session.requests[-1]["params"]["search"] == "Marvel"

    def test_franchise_games_without_name(self, client: RawgClient, session: FakeSession):
        respond(session, {"id": 101, "games": []})

        assert client.fetch_franchise_games(101, limit=3) == []

    def test_franchise_not_found(self, client: RawgClient, session: FakeSession):
        respond(session, {}, status_code=404)

        assert client.fetch_franchise_games(999, limit=3) == []


# ---------------------------------------------------------------------- #
# Вспомогательные функции
# ---------------------------------------------------------------------- #
class TestHelpers:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("<p>Текст</p>", "Текст"),
            ("<b>Жирный</b> и <i>курсив</i>", "Жирный и курсив"),
            ("&amp; &laquo;кавычки&raquo;", '& «кавычки»'),
            ("  много   пробелов  ", "много пробелов"),
            ("", ""),
            (None, ""),
            (123, ""),
        ],
    )
    def test_strip_html(self, raw, expected):
        assert strip_html(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2015-05-18", date(2015, 5, 18)),
            ("2015-05-18T00:00:00", date(2015, 5, 18)),
            ("2015", date(2015, 1, 1)),
            ("18.05.2015", date(2015, 5, 18)),
            ("18/05/2015", date(2015, 5, 18)),
        ],
    )
    def test_parse_release_date_from_string(self, raw, expected):
        assert parse_release_date(raw) == expected

    def test_parse_release_date_from_objects(self):
        assert parse_release_date(date(2020, 1, 2)) == date(2020, 1, 2)
        assert parse_release_date(datetime(2020, 1, 2, 10, 30)) == date(2020, 1, 2)

    @pytest.mark.parametrize("raw", [None, "", "   ", "не дата", "tba", 12345])
    def test_parse_release_date_unknown(self, raw):
        assert parse_release_date(raw) is None
