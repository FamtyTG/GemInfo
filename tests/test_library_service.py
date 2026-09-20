"""Тесты сервиса библиотеки: «во что я играл», отзывы и избранное."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from gamehunter.domain.exceptions import (
    EmptyReviewError,
    FavoriteAlreadyExistsError,
    FavoriteNotFoundError,
    GameAlreadyPlayedError,
    PlayedGameNotFoundError,
    ReviewTooLongError,
)
from gamehunter.domain.services import GAME_NAME_MAX_LENGTH, LibraryService
from gamehunter.infrastructure.db import SqlLibraryRepository
from tests.fakes import (
    InMemoryLibraryRepository,
    make_favorite,
    make_game,
    make_played,
)

USER_ID = 200
OTHER_USER_ID = 300


@pytest.fixture()
def repository() -> InMemoryLibraryRepository:
    return InMemoryLibraryRepository()


@pytest.fixture()
def service(repository) -> LibraryService:
    return LibraryService(repository=repository, page_size=3, note_max_length=1000)


def fixed_now() -> datetime:
    return datetime(2026, 5, 1, 12, 0, 0)


# ---------------------------------------------------------------------- #
# «Во что я уже играл»
# ---------------------------------------------------------------------- #
class TestAddPlayed:
    def test_adds_record(self, service: LibraryService, repository):
        record = service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        assert record.id == 1
        assert record.game_id == 32
        assert record.name == "The Witcher 3"
        assert record.tg_user_id == USER_ID
        assert len(repository.played) == 1

    def test_stores_slug_and_image(self, service: LibraryService):
        game = make_game(32, image_url="https://cdn/img.jpg")

        record = service.add_played(USER_ID, game)

        assert record.slug == game.slug
        assert record.image_url == "https://cdn/img.jpg"

    def test_default_date_is_now(self, service: LibraryService):
        record = service.add_played(USER_ID, make_game())

        assert record.played_at.date() == datetime.now().date()

    def test_custom_date(self, service: LibraryService):
        moment = datetime(2025, 12, 31, 23, 59)

        record = service.add_played(USER_ID, make_game(), played_at=moment)

        assert record.played_at == moment

    def test_now_provider_is_used(self, repository):
        service = LibraryService(repository=repository, now_provider=fixed_now)

        record = service.add_played(USER_ID, make_game())

        assert record.played_at == fixed_now()

    def test_duplicate_is_rejected(self, service: LibraryService, repository):
        service.add_played(USER_ID, make_game(32))

        with pytest.raises(GameAlreadyPlayedError):
            service.add_played(USER_ID, make_game(32))

        assert len(repository.played) == 1

    def test_same_game_can_be_added_by_another_user(self, service: LibraryService):
        service.add_played(USER_ID, make_game(32))
        record = service.add_played(OTHER_USER_ID, make_game(32))

        assert record.tg_user_id == OTHER_USER_ID

    def test_long_name_is_truncated(self, service: LibraryService):
        long_name = "И" * (GAME_NAME_MAX_LENGTH + 50)

        record = service.add_played(USER_ID, make_game(1, long_name))

        assert len(record.name) == GAME_NAME_MAX_LENGTH

    def test_short_name_is_untouched(self, service: LibraryService):
        record = service.add_played(USER_ID, make_game(1, "Portal 2"))

        assert record.name == "Portal 2"


class TestPlayedHistory:
    @pytest.fixture()
    def filled(self, service: LibraryService) -> LibraryService:
        now = fixed_now()
        for index in range(7):
            service.add_played(
                USER_ID,
                make_game(100 + index, f"Игра {index}"),
                played_at=now - timedelta(days=index),
            )
        return service

    def test_first_page(self, filled: LibraryService):
        page = filled.get_played_history(USER_ID, page=1)

        assert [item.name for item in page.items] == ["Игра 0", "Игра 1", "Игра 2"]
        assert page.page == 1
        assert page.total_pages == 3

    def test_last_page(self, filled: LibraryService):
        page = filled.get_played_history(USER_ID, page=3)

        assert len(page.items) == 1
        assert page.has_next is False
        assert page.has_previous is True

    def test_page_beyond_last_is_clamped(self, filled: LibraryService):
        page = filled.get_played_history(USER_ID, page=99)

        assert page.page == 3

    def test_page_below_one_is_clamped(self, filled: LibraryService):
        assert filled.get_played_history(USER_ID, page=0).page == 1
        assert filled.get_played_history(USER_ID, page=-2).page == 1

    def test_empty_history(self, service: LibraryService):
        page = service.get_played_history(USER_ID)

        assert page.is_empty is True
        assert page.total_pages == 1

    def test_other_user_history_is_not_visible(self, filled: LibraryService):
        assert filled.get_played_history(OTHER_USER_ID).is_empty is True

    def test_records_are_ordered_from_new_to_old(self, filled: LibraryService):
        dates = [item.played_at for item in filled.get_played_history(USER_ID).items]

        assert dates == sorted(dates, reverse=True)

    def test_page_size_from_settings(self, repository):
        service = LibraryService(repository=repository, page_size=2)
        for index in range(5):
            service.add_played(USER_ID, make_game(index, f"Игра {index}"))

        assert service.page_size == 2
        assert len(service.get_played_history(USER_ID).items) == 2

    def test_page_size_is_at_least_one(self, repository):
        assert LibraryService(repository=repository, page_size=0).page_size == 1


class TestGetPlayed:
    def test_returns_record(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        record = service.get_played(USER_ID, created.id)

        assert record.id == created.id
        assert record.name == "The Witcher 3"

    def test_unknown_record(self, service: LibraryService):
        with pytest.raises(PlayedGameNotFoundError):
            service.get_played(USER_ID, 42)

    def test_record_of_another_user(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game(32))

        with pytest.raises(PlayedGameNotFoundError):
            service.get_played(OTHER_USER_ID, created.id)


class TestReview:
    def test_saves_review(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        record = service.add_review(USER_ID, created.id, "Отличная игра!")

        assert record.review == "Отличная игра!"
        assert record.has_review is True

    def test_review_is_trimmed(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game())

        record = service.add_review(USER_ID, created.id, "  Текст с пробелами  ")

        assert record.review == "Текст с пробелами"

    def test_review_replaces_previous(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game())
        service.add_review(USER_ID, created.id, "Первый отзыв")

        record = service.add_review(USER_ID, created.id, "Второй отзыв")

        assert record.review == "Второй отзыв"

    def test_max_length_is_allowed(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game())

        record = service.add_review(USER_ID, created.id, "с" * 1000)

        assert len(record.review) == 1000

    def test_too_long_review(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game())

        with pytest.raises(ReviewTooLongError) as info:
            service.add_review(USER_ID, created.id, "с" * 1001)

        assert info.value.limit == 1000

    def test_custom_limit(self, repository):
        service = LibraryService(repository=repository, note_max_length=140)
        created = service.add_played(USER_ID, make_game())

        assert service.note_max_length == 140
        with pytest.raises(ReviewTooLongError):
            service.add_review(USER_ID, created.id, "с" * 141)

    def test_limit_is_at_least_one(self, repository):
        assert LibraryService(repository=repository, note_max_length=0).note_max_length == 1

    @pytest.mark.parametrize("text", ["", "   ", "\n\t "])
    def test_empty_review(self, service: LibraryService, text):
        created = service.add_played(USER_ID, make_game())

        with pytest.raises(EmptyReviewError):
            service.add_review(USER_ID, created.id, text)

    def test_unknown_record(self, service: LibraryService):
        with pytest.raises(PlayedGameNotFoundError):
            service.add_review(USER_ID, 999, "Текст")

    def test_review_of_another_user_is_not_updated(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game())

        with pytest.raises(PlayedGameNotFoundError):
            service.add_review(OTHER_USER_ID, created.id, "Чужой отзыв")


class TestRemovePlayed:
    def test_removes_record_and_returns_name(self, service: LibraryService, repository):
        created = service.add_played(USER_ID, make_game(32, "The Witcher 3"))

        name = service.remove_played(USER_ID, created.id)

        assert name == "The Witcher 3"
        assert repository.played == []

    def test_unknown_record(self, service: LibraryService):
        with pytest.raises(PlayedGameNotFoundError):
            service.remove_played(USER_ID, 42)

    def test_record_of_another_user(self, service: LibraryService, repository):
        created = service.add_played(USER_ID, make_game())

        with pytest.raises(PlayedGameNotFoundError):
            service.remove_played(OTHER_USER_ID, created.id)

        assert len(repository.played) == 1

    def test_game_can_be_added_again_after_removal(self, service: LibraryService):
        created = service.add_played(USER_ID, make_game(32))
        service.remove_played(USER_ID, created.id)

        record = service.add_played(USER_ID, make_game(32))

        assert record.game_id == 32


class TestPlayedIds:
    def test_returns_ids(self, service: LibraryService):
        service.add_played(USER_ID, make_game(32))
        service.add_played(USER_ID, make_game(58175))

        assert service.played_game_ids(USER_ID) == {32, 58175}

    def test_empty_for_unknown_user(self, service: LibraryService):
        assert service.played_game_ids(USER_ID) == set()

    def test_is_played(self, service: LibraryService):
        service.add_played(USER_ID, make_game(32))

        assert service.is_played(USER_ID, 32) is True
        assert service.is_played(USER_ID, 3498) is False
        assert service.is_played(OTHER_USER_ID, 32) is False


# ---------------------------------------------------------------------- #
# Избранное
# ---------------------------------------------------------------------- #
class TestFavorites:
    def test_add_favorite(self, service: LibraryService, repository):
        record = service.add_favorite(USER_ID, make_game(41494, "Cyberpunk 2077"))

        assert record.game_id == 41494
        assert record.name == "Cyberpunk 2077"
        assert len(repository.favorites) == 1

    def test_duplicate_favorite(self, service: LibraryService, repository):
        service.add_favorite(USER_ID, make_game(41494))

        with pytest.raises(FavoriteAlreadyExistsError):
            service.add_favorite(USER_ID, make_game(41494))

        assert len(repository.favorites) == 1

    def test_long_name_is_truncated(self, service: LibraryService):
        record = service.add_favorite(USER_ID, make_game(1, "И" * 200))

        assert len(record.name) == GAME_NAME_MAX_LENGTH

    def test_remove_favorite(self, service: LibraryService, repository):
        service.add_favorite(USER_ID, make_game(41494))

        assert service.remove_favorite(USER_ID, 41494) is True
        assert repository.favorites == []

    def test_remove_unknown_favorite(self, service: LibraryService):
        with pytest.raises(FavoriteNotFoundError):
            service.remove_favorite(USER_ID, 41494)

    def test_remove_favorite_of_another_user(self, service: LibraryService, repository):
        service.add_favorite(USER_ID, make_game(41494))

        with pytest.raises(FavoriteNotFoundError):
            service.remove_favorite(OTHER_USER_ID, 41494)

        assert len(repository.favorites) == 1

    def test_toggle_adds_favorite(self, service: LibraryService):
        record, added = service.toggle_favorite(USER_ID, make_game(41494, "Cyberpunk 2077"))

        assert added is True
        assert record.game_id == 41494

    def test_toggle_removes_favorite(self, service: LibraryService, repository):
        service.add_favorite(USER_ID, make_game(41494))

        record, added = service.toggle_favorite(USER_ID, make_game(41494))

        assert added is False
        assert record.game_id == 41494
        assert repository.favorites == []

    def test_is_favorite(self, service: LibraryService):
        service.add_favorite(USER_ID, make_game(41494))

        assert service.is_favorite(USER_ID, 41494) is True
        assert service.is_favorite(USER_ID, 32) is False
        assert service.is_favorite(OTHER_USER_ID, 41494) is False

    def test_favorites_paging(self, service: LibraryService):
        for index in range(7):
            service.add_favorite(USER_ID, make_game(index, f"Игра {index}"))

        first = service.get_favorites(USER_ID, page=1)
        last = service.get_favorites(USER_ID, page=3)

        assert len(first.items) == 3
        assert first.total_pages == 3
        assert len(last.items) == 1

    def test_favorites_page_is_clamped(self, service: LibraryService):
        service.add_favorite(USER_ID, make_game(1))

        assert service.get_favorites(USER_ID, page=0).page == 1
        assert service.get_favorites(USER_ID, page=42).page == 1

    def test_empty_favorites(self, service: LibraryService):
        page = service.get_favorites(USER_ID)

        assert page.is_empty is True
        assert page.total_pages == 1

    def test_other_user_favorites_are_not_visible(self, service: LibraryService):
        service.add_favorite(USER_ID, make_game(1))

        assert service.get_favorites(OTHER_USER_ID).is_empty is True


class TestNamesOf:
    def test_extracts_names(self):
        records = [make_played(name="Первая"), make_favorite(name="Вторая")]

        assert LibraryService.names_of(records) == ["Первая", "Вторая"]

    def test_handles_objects_without_name(self):
        assert LibraryService.names_of([object()]) == ["?"]

    def test_empty_list(self):
        assert LibraryService.names_of([]) == []


# ---------------------------------------------------------------------- #
# Работа с настоящим репозиторием (SQLite)
# ---------------------------------------------------------------------- #
class TestWithSqlRepository:
    @pytest.fixture()
    def sql_service(self, database) -> LibraryService:
        return LibraryService(
            repository=SqlLibraryRepository(database), page_size=3, note_max_length=1000
        )

    def test_library_survives_service_recreation(self, database, sql_service: LibraryService):
        created = sql_service.add_played(USER_ID, make_game(32, "The Witcher 3"))
        sql_service.add_review(USER_ID, created.id, "Шедевр")
        sql_service.add_favorite(USER_ID, make_game(41494, "Cyberpunk 2077"))

        fresh = LibraryService(repository=SqlLibraryRepository(database), page_size=3)
        history = fresh.get_played_history(USER_ID)
        favorites = fresh.get_favorites(USER_ID)

        assert history.items[0].review == "Шедевр"
        assert favorites.items[0].name == "Cyberpunk 2077"
        assert fresh.is_played(USER_ID, 32) is True

    def test_unique_constraint_protects_from_duplicates(self, sql_service: LibraryService):
        sql_service.add_favorite(USER_ID, make_game(41494))

        with pytest.raises(FavoriteAlreadyExistsError):
            sql_service.add_favorite(USER_ID, make_game(41494))
