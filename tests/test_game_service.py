"""Тесты сервиса каталога игр (подбор, возраст, франшизы, кэширование)."""

from __future__ import annotations

import time

import pytest

from gamehunter.domain.age_ratings import AgePolicy
from gamehunter.domain.entities import Game, GameDetails, GameQuery, Genre
from gamehunter.domain.exceptions import (
    FranchiseNotFoundError,
    FranchiseSearchUnavailableError,
    GameInfoUnavailableError,
    GameNotFoundError,
    GamesUnavailableError,
    GenresUnavailableError,
    NoGamesFoundError,
)
from gamehunter.domain.services import GameService
from tests.fakes import (
    FakeGamesProvider,
    default_provider,
    make_details,
    make_franchise,
    make_game,
    make_genre,
    make_platform,
    make_profile,
)

USER_ID = 200


@pytest.fixture()
def provider() -> FakeGamesProvider:
    return default_provider()


@pytest.fixture()
def service(provider: FakeGamesProvider) -> GameService:
    return GameService(
        provider=provider,
        max_games=3,
        max_genres=6,
        max_franchises=5,
        details_fetch_limit=4,
        cache_ttl_seconds=600,
    )


# ---------------------------------------------------------------------- #
# Параметры сервиса
# ---------------------------------------------------------------------- #
class TestServiceSettings:
    def test_properties(self, service: GameService):
        assert service.max_games == 3
        assert service.max_genres == 6
        assert isinstance(service.age_policy, AgePolicy)

    def test_default_ordering(self, service: GameService):
        assert service.ordering == "-rating"

    def test_custom_ordering(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, ordering="-released")

        assert service.ordering == "-released"
        assert service.build_query().ordering == "-released"


# ---------------------------------------------------------------------- #
# Жанры и платформы
# ---------------------------------------------------------------------- #
class TestGenres:
    def test_sorts_genres_by_popularity(self, provider: FakeGamesProvider):
        provider.genres = [
            Genre(id=1, name="Racing", slug="racing", games_count=10),
            Genre(id=4, name="Action", slug="action", games_count=500),
            Genre(id=5, name="RPG", slug="role-playing-games-rpg", games_count=100),
        ]
        service = GameService(provider=provider, max_genres=10)

        genres = service.get_genres()

        assert [genre.slug for genre in genres] == ["action", "role-playing-games-rpg", "racing"]

    def test_limits_number_of_genres(self, provider: FakeGamesProvider):
        provider.genres = [make_genre(f"Жанр {index}", f"genre-{index}", index) for index in range(20)]
        service = GameService(provider=provider, max_genres=6)

        assert len(service.get_genres()) == 6

    def test_caches_genres(self, service: GameService, provider: FakeGamesProvider):
        first = service.get_genres()
        second = service.get_genres()

        assert first == second
        assert provider.genre_calls == 1

    def test_cache_expires(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, cache_ttl_seconds=0)

        service.get_genres()
        service.get_genres()

        assert provider.genre_calls == 2

    def test_clear_cache_forces_refetch(self, service: GameService, provider: FakeGamesProvider):
        service.get_genres()
        service.clear_cache()
        service.get_genres()

        assert provider.genre_calls == 2

    def test_unexpected_error_becomes_genres_unavailable(self, provider: FakeGamesProvider):
        provider.errors["genres"] = RuntimeError("boom")
        service = GameService(provider=provider)

        with pytest.raises(GenresUnavailableError) as info:
            service.get_genres()

        assert info.value.service == "rawg"

    def test_domain_error_is_passed_through(self, provider: FakeGamesProvider):
        provider.errors["genres"] = GenresUnavailableError("rawg", "timeout")
        service = GameService(provider=provider)

        with pytest.raises(GenresUnavailableError):
            service.get_genres()

    def test_returns_copy_of_cached_list(self, service: GameService):
        genres = service.get_genres()
        genres.clear()

        assert service.get_genres()


class TestPlatforms:
    def test_returns_platforms(self, service: GameService, provider: FakeGamesProvider):
        platforms = service.get_platforms()

        assert [platform.slug for platform in platforms] == ["pc", "playstation", "xbox", "nintendo"]
        assert provider.platform_calls == 1

    def test_caches_platforms(self, service: GameService, provider: FakeGamesProvider):
        service.get_platforms()
        service.get_platforms()

        assert provider.platform_calls == 1

    def test_unexpected_error_becomes_genres_unavailable(self, provider: FakeGamesProvider):
        provider.errors["platforms"] = RuntimeError("boom")
        service = GameService(provider=provider)

        with pytest.raises(GenresUnavailableError):
            service.get_platforms()

    def test_domain_error_is_passed_through(self, provider: FakeGamesProvider):
        provider.errors["platforms"] = GenresUnavailableError("rawg", "503")
        service = GameService(provider=provider)

        with pytest.raises(GenresUnavailableError):
            service.get_platforms()


class TestFindGenre:
    def test_finds_genre_by_slug(self, service: GameService):
        genre = service.find_genre("action")

        assert genre is not None
        assert genre.name == "Action"

    def test_returns_none_for_unknown_slug(self, service: GameService):
        assert service.find_genre("no-such-genre") is None

    def test_uses_cached_genres(self, service: GameService, provider: FakeGamesProvider):
        service.find_genre("action")
        service.find_genre("adventure")

        assert provider.genre_calls == 1


# ---------------------------------------------------------------------- #
# Параметры поиска
# ---------------------------------------------------------------------- #
class TestBuildQuery:
    def test_defaults(self, service: GameService):
        query = service.build_query()

        assert query.genres == ()
        assert query.parent_platforms == ()
        assert query.search == ""
        assert query.page == 1
        assert query.page_size == 3
        assert query.ordering == "-rating"

    def test_uses_given_values(self, service: GameService):
        query = service.build_query(
            genres=["action", "adventure"], platforms=[1, 2], search="  witcher ", page=2
        )

        assert query.genres == ("action", "adventure")
        assert query.parent_platforms == (1, 2)
        assert query.search == "witcher"
        assert query.page == 2

    def test_page_never_below_one(self, service: GameService):
        assert service.build_query(page=0).page == 1
        assert service.build_query(page=-3).page == 1


class TestMergeWithProfile:
    def test_profile_genres_are_used_when_query_is_empty(self, service: GameService):
        profile = make_profile(genre_slugs=("action", "shooter"))
        query = service.build_query()

        merged = service.merge_with_profile(query, profile, ())

        assert merged.genres == ("action", "shooter")

    def test_query_genres_win_over_profile(self, service: GameService):
        profile = make_profile(genre_slugs=("action",))
        query = service.build_query(genres=["racing"])

        merged = service.merge_with_profile(query, profile, ())

        assert merged.genres == ("racing",)

    def test_profile_platforms_are_used(self, service: GameService):
        profile = make_profile(platform_ids=(1, 3))

        merged = service.merge_with_profile(service.build_query(), profile, ())

        assert merged.parent_platforms == (1, 3)

    def test_played_games_are_excluded(self, service: GameService):
        merged = service.merge_with_profile(service.build_query(), None, [32, 58175])

        assert merged.exclude_game_ids == (32, 58175)

    def test_exclusions_are_merged_without_duplicates(self, service: GameService):
        query = service.build_query()
        query = GameQuery(exclude_game_ids=(32, 4200))

        merged = service.merge_with_profile(query, None, [32, 28])

        assert merged.exclude_game_ids == (32, 4200, 28)

    def test_without_profile_keeps_query_as_is(self, service: GameService):
        query = service.build_query(genres=["action"], page=2)

        merged = service.merge_with_profile(query, None, ())

        assert merged.genres == ("action",)
        assert merged.page == 2
        assert merged.page_size == query.page_size

    def test_additions_are_excluded_by_default(self, service: GameService):
        merged = service.merge_with_profile(service.build_query(), None, ())

        assert merged.exclude_additions is True


# ---------------------------------------------------------------------- #
# Подбор игр
# ---------------------------------------------------------------------- #
class TestFindGames:
    def test_returns_first_page(self, service: GameService):
        page = service.find_games(service.build_query())

        assert len(page.games) == 3
        assert page.page == 1
        assert page.total_pages == 3  # 7 игр по 3 на странице

    def test_second_page(self, service: GameService):
        page = service.find_games(service.build_query(page=2))

        assert page.page == 2
        assert [game.id for game in page.games] == [41494, 28, 4200]
        assert page.has_previous is True

    def test_passes_filters_to_provider(self, service: GameService, provider: FakeGamesProvider):
        service.find_games(service.build_query(genres=["action"], platforms=[1]))

        query = provider.search_calls[-1]
        assert query.genres == ("action",)
        assert query.parent_platforms == (1,)
        assert query.page_size == 3

    def test_played_games_are_excluded_from_results(self, service: GameService, provider):
        page = service.find_games(service.build_query(), None, [32, 58175])

        assert 32 not in [game.id for game in page.games]
        assert 58175 not in [game.id for game in page.games]
        assert set(provider.search_calls[-1].exclude_game_ids) == {32, 58175}

    def test_profile_is_applied(self, service: GameService, provider: FakeGamesProvider):
        profile = make_profile(genre_slugs=("shooter",), platform_ids=(2,))

        service.find_games(service.build_query(), profile, [4200])

        query = provider.search_calls[-1]
        assert query.genres == ("shooter",)
        assert query.parent_platforms == (2,)
        assert 4200 in query.exclude_game_ids

    def test_no_games_found(self, provider: FakeGamesProvider):
        provider.games = []
        service = GameService(provider=provider)

        with pytest.raises(NoGamesFoundError):
            service.find_games(service.build_query())

    def test_provider_error_is_passed_through(self, provider: FakeGamesProvider):
        provider.errors["search"] = GamesUnavailableError("rawg", "500")
        service = GameService(provider=provider)

        with pytest.raises(GamesUnavailableError):
            service.find_games(service.build_query())

    def test_unexpected_error_becomes_games_unavailable(self, provider: FakeGamesProvider):
        provider.errors["search"] = RuntimeError("network down")
        service = GameService(provider=provider)

        with pytest.raises(GamesUnavailableError) as info:
            service.find_games(service.build_query())

        assert info.value.service == "rawg"


class TestAgeFilter:
    def test_games_are_filtered_by_age(self, provider: FakeGamesProvider):
        # Первые четыре игры — 17+, пятая подходит подростку 13 лет
        provider.games = [
            make_game(1, "Adult Game 1"),
            make_game(2, "Adult Game 2"),
            make_game(3, "Adult Game 3"),
            make_game(4, "Adult Game 4"),
            make_game(5, "Teen Friendly"),
        ]
        provider.details = {
            1: make_details(make_game(1), min_age=17),
            2: make_details(make_game(2), min_age=18),
            3: make_details(make_game(3), min_age=17),
            4: make_details(make_game(4), min_age=13),
            5: make_details(make_game(5), min_age=10),
        }
        service = GameService(provider=provider, max_games=3, details_fetch_limit=5)
        profile = make_profile(age=13)

        page = service.find_games(service.build_query(), profile)

        assert [game.id for game in page.games] == [4, 5]

    def test_adult_gets_all_games(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)
        profile = make_profile(age=30)

        page = service.find_games(service.build_query(), profile)

        assert len(page.games) == 3

    def test_requests_more_candidates_for_age_filter(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)
        profile = make_profile(age=18)

        service.find_games(service.build_query(), profile)

        assert provider.search_calls[-1].page_size == 7

    def test_without_age_details_are_not_fetched(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)

        service.find_games(service.build_query(), make_profile(age=None))

        assert provider.details_calls == []
        assert provider.search_calls[-1].page_size == 3

    def test_no_suitable_games(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)
        profile = make_profile(age=6)

        with pytest.raises(NoGamesFoundError):
            service.find_games(service.build_query(), profile)

    def test_unavailable_details_mean_service_error(self, provider: FakeGamesProvider):
        provider.errors["details"] = GameInfoUnavailableError("rawg", "timeout")
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)
        profile = make_profile(age=13)

        with pytest.raises(GamesUnavailableError):
            service.find_games(service.build_query(), profile)

    def test_missing_details_are_skipped(self, provider: FakeGamesProvider):
        provider.details = {32: None, 58175: None}
        provider.games = [make_game(32), make_game(58175), make_game(4200)]
        provider.details[4200] = make_details(make_game(4200), min_age=10)
        service = GameService(provider=provider, max_games=3, details_fetch_limit=4)

        page = service.find_games(service.build_query(), make_profile(age=12))

        assert [game.id for game in page.games] == [4200]


# ---------------------------------------------------------------------- #
# Карточка игры
# ---------------------------------------------------------------------- #
class TestGameDetails:
    def test_returns_details(self, service: GameService):
        details = service.get_game_details(32)

        assert details is not None
        assert details.name == "The Witcher 3: Wild Hunt"
        assert details.min_age == 17

    def test_caches_details(self, service: GameService, provider: FakeGamesProvider):
        service.get_game_details(32)
        service.get_game_details(32)

        assert provider.details_calls == [32]

    def test_truncates_long_summary(self, provider: FakeGamesProvider):
        long_text = "слово " * 500
        provider.details = {1: make_details(make_game(1, "Игра"), summary=long_text.strip())}
        service = GameService(provider=provider, summary_max_length=50)

        details = service.get_game_details(1)

        assert len(details.summary) <= 51
        assert details.summary.endswith("…")

    def test_short_summary_is_untouched(self, provider: FakeGamesProvider):
        provider.details = {1: make_details(make_game(1), summary="Короткое описание")}
        service = GameService(provider=provider)

        assert service.get_game_details(1).summary == "Короткое описание"

    def test_unknown_game(self, service: GameService):
        with pytest.raises(GameNotFoundError):
            service.get_game_details(999999)

    def test_unknown_game_with_default_returns_none(self, service: GameService):
        known = make_game(999999, "Из списка")

        assert service.get_game_details(999999, default_game=known) is None

    def test_provider_error_with_default_returns_none(self, provider: FakeGamesProvider):
        provider.errors["details"] = GameInfoUnavailableError("rawg", "timeout")
        service = GameService(provider=provider)

        assert service.get_game_details(32, default_game=make_game(32)) is None

    def test_provider_error_without_default_is_raised(self, provider: FakeGamesProvider):
        provider.errors["details"] = GameInfoUnavailableError("rawg", "timeout")
        service = GameService(provider=provider)

        with pytest.raises(GameInfoUnavailableError):
            service.get_game_details(32)

    def test_unexpected_error_becomes_game_info_unavailable(self, provider: FakeGamesProvider):
        provider.errors["details"] = RuntimeError("boom")
        service = GameService(provider=provider)

        with pytest.raises(GameInfoUnavailableError):
            service.get_game_details(32)

    def test_cache_is_limited(self, provider: FakeGamesProvider):
        provider.games = [make_game(index, f"Игра {index}") for index in range(1, 250)]
        provider.details = {
            game.id: make_details(game, summary=f"Описание {game.id}") for game in provider.games
        }
        service = GameService(provider=provider)

        for game in provider.games[:210]:
            service.get_game_details(game.id)

        # Кэш переполнен и очищен — следующая игра запрашивается заново
        provider.details_calls.clear()
        service.get_game_details(1)

        assert provider.details_calls == [1]


class TestGameFromLibrary:
    def test_builds_game_object(self, service: GameService):
        game = service.game_from_library(41494, "cyberpunk-2077", "Cyberpunk 2077")

        assert isinstance(game, Game)
        assert game.id == 41494
        assert game.slug == "cyberpunk-2077"
        assert game.name == "Cyberpunk 2077"
        assert game.rating is None


# ---------------------------------------------------------------------- #
# Франшизы (IP)
# ---------------------------------------------------------------------- #
class TestFranchises:
    def test_search_by_name(self, service: GameService):
        franchises = service.search_franchises("marvel")

        assert [item.name for item in franchises] == ["Marvel", "Marvel Ultimate Alliance"]

    def test_search_is_case_insensitive(self, service: GameService):
        assert service.search_franchises("MARVEL")[0].slug == "marvel"

    def test_empty_name(self, service: GameService):
        with pytest.raises(FranchiseNotFoundError):
            service.search_franchises("   ")

    def test_not_found(self, service: GameService):
        with pytest.raises(FranchiseNotFoundError):
            service.search_franchises("нет такой франшизы")

    def test_franchises_without_games_are_skipped(self, provider: FakeGamesProvider):
        provider.franchises = [
            make_franchise(1, "Marvel Empty", "marvel-empty", games_count=0),
            make_franchise(2, "Marvel", "marvel", games_count=10),
        ]
        service = GameService(provider=provider)

        franchises = service.search_franchises("marvel")

        assert [item.id for item in franchises] == [2]

    def test_limit_is_applied(self, provider: FakeGamesProvider):
        provider.franchises = [
            make_franchise(index, f"Marvel {index}", f"marvel-{index}", games_count=5)
            for index in range(1, 10)
        ]
        service = GameService(provider=provider, max_franchises=3)

        assert len(service.search_franchises("marvel")) == 3

    def test_explicit_limit_overrides_default(self, provider: FakeGamesProvider):
        provider.franchises = [
            make_franchise(index, f"Marvel {index}", f"marvel-{index}", games_count=5)
            for index in range(1, 10)
        ]
        service = GameService(provider=provider, max_franchises=5)

        assert len(service.search_franchises("marvel", limit=2)) == 2

    def test_provider_error_is_passed_through(self, provider: FakeGamesProvider):
        provider.errors["franchises"] = FranchiseSearchUnavailableError("rawg", "500")
        service = GameService(provider=provider)

        with pytest.raises(FranchiseSearchUnavailableError):
            service.search_franchises("marvel")

    def test_unexpected_error_becomes_service_error(self, provider: FakeGamesProvider):
        provider.errors["franchises"] = RuntimeError("boom")
        service = GameService(provider=provider)

        with pytest.raises(FranchiseSearchUnavailableError):
            service.search_franchises("marvel")

    def test_games_of_franchise_are_taken_from_catalog(self, service: GameService):
        games = service.get_franchise_games(make_franchise(101, "Marvel", "marvel", 42))

        assert [game.id for game in games] == [9001, 9002]

    def test_games_embedded_in_franchise_are_used(self, service: GameService, provider):
        embedded = (make_game(777, "Встроенная игра"),)
        franchise = make_franchise(101, "Marvel", "marvel", 1, games=embedded)

        games = service.get_franchise_games(franchise)

        assert [game.id for game in games] == [777]
        assert provider.franchise_games_calls == []

    def test_embedded_games_are_limited(self, service: GameService):
        embedded = tuple(make_game(index, f"Игра {index}") for index in range(1, 10))
        franchise = make_franchise(1, "Marvel", "marvel", 9, games=embedded)

        assert len(service.get_franchise_games(franchise)) == 3

    def test_franchise_games_are_sorted_by_rating(self, provider: FakeGamesProvider):
        provider.franchise_games = {
            1: [
                make_game(1, "Без рейтинга", rating=None),
                make_game(2, "Средняя", rating=3.5),
                make_game(3, "Лучшая", rating=4.9),
            ]
        }
        provider.franchises = [make_franchise(1, "Marvel", "marvel", 3)]
        service = GameService(provider=provider, max_games=3)

        games = service.get_franchise_games(make_franchise(1, "Marvel", "marvel", 3))

        assert [game.id for game in games] == [3, 2, 1]

    def test_franchise_without_games(self, provider: FakeGamesProvider):
        provider.franchise_games = {1: []}
        service = GameService(provider=provider)

        with pytest.raises(NoGamesFoundError):
            service.get_franchise_games(make_franchise(1, "Marvel", "marvel", 3))

    def test_franchise_games_error(self, provider: FakeGamesProvider):
        provider.errors["franchise_games"] = FranchiseSearchUnavailableError("rawg", "503")
        service = GameService(provider=provider)

        with pytest.raises(FranchiseSearchUnavailableError):
            service.get_franchise_games(make_franchise(101, "Marvel", "marvel", 42))

    def test_franchise_games_unexpected_error(self, provider: FakeGamesProvider):
        provider.errors["franchise_games"] = RuntimeError("boom")
        service = GameService(provider=provider)

        with pytest.raises(FranchiseSearchUnavailableError):
            service.get_franchise_games(make_franchise(101, "Marvel", "marvel", 42))


# ---------------------------------------------------------------------- #
# Кэш
# ---------------------------------------------------------------------- #
class TestCache:
    def test_clear_cache_resets_everything(self, service: GameService, provider):
        service.get_genres()
        service.get_platforms()
        service.get_game_details(32)

        service.clear_cache()

        service.get_genres()
        service.get_platforms()
        service.get_game_details(32)

        assert provider.genre_calls == 2
        assert provider.platform_calls == 2
        assert provider.details_calls == [32, 32]

    def test_cache_ttl_is_respected(self, provider: FakeGamesProvider):
        service = GameService(provider=provider, cache_ttl_seconds=600)

        service.get_genres()
        time.sleep(0.01)
        service.get_genres()

        assert provider.genre_calls == 1

    def test_details_entity_is_reused(self, service: GameService):
        first = service.get_game_details(32)
        second = service.get_game_details(32)

        assert first == second
        assert isinstance(second, GameDetails)
