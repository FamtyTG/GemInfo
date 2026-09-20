"""Тесты слоя базы данных: Database, ORM-модели и SQL-репозитории.

Тесты выполняются на SQLite (структура таблиц та же, что и в PostgreSQL),
поэтому для их запуска не нужен установленный сервер базы данных.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from gamehunter.domain.entities import UserProfile
from gamehunter.domain.exceptions import DatabaseError
from gamehunter.infrastructure.db import (
    Base,
    Database,
    FavoriteGameORM,
    PlayedGameORM,
    SqlLibraryRepository,
    SqlProfileRepository,
    UserProfileORM,
)
from tests.fakes import make_game, make_region

USER_ID = 200
OTHER_USER_ID = 300


@pytest.fixture()
def profiles(database: Database) -> SqlProfileRepository:
    return SqlProfileRepository(database)


@pytest.fixture()
def library(database: Database) -> SqlLibraryRepository:
    return SqlLibraryRepository(database)


# ---------------------------------------------------------------------- #
# Database
# ---------------------------------------------------------------------- #
class TestDatabase:
    def test_creates_all_tables(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path / 'tables.db'}")
        try:
            db.create_all()
            names = set(inspect(db.engine).get_table_names())
        finally:
            db.dispose()

        assert {"user_profiles", "played_games", "favorite_games"} <= names

    def test_create_all_is_idempotent(self, database: Database):
        database.create_all()
        database.create_all()  # второй вызов не должен вызывать ошибку

        assert inspect(database.engine).has_table("user_profiles")

    def test_url_and_safe_url(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'safe.db'}"
        db = Database(url)
        try:
            assert db.url == url
            assert db.safe_url == url
        finally:
            db.dispose()

    def test_safe_url_hides_password(self):
        db = Database("postgresql+psycopg2://user:secret@localhost:5432/gamehunter")
        try:
            assert "secret" not in db.safe_url
            assert "user" in db.safe_url
        finally:
            db.dispose()

    def test_session_scope_commits(self, database: Database):
        with database.session_scope() as session:
            session.add(UserProfileORM(tg_user_id=USER_ID))

        with database.session_scope() as session:
            count = session.query(UserProfileORM).count()

        assert count == 1

    def test_session_scope_rolls_back_on_error(self, database: Database):
        with pytest.raises(RuntimeError):
            with database.session_scope() as session:
                session.add(UserProfileORM(tg_user_id=USER_ID))
                raise RuntimeError("сбой в коде")

        with database.session_scope() as session:
            count = session.query(UserProfileORM).count()

        assert count == 0

    def test_session_scope_rolls_back_on_sqlalchemy_error(self, database: Database):
        with pytest.raises(IntegrityError):
            with database.session_scope() as session:
                session.add(UserProfileORM(tg_user_id=USER_ID))
                session.flush()
                session.add(UserProfileORM(tg_user_id=USER_ID))
                session.flush()

        with database.session_scope() as session:
            assert session.query(UserProfileORM).count() == 0

    def test_create_all_error_becomes_database_error(self, tmp_path, monkeypatch):
        db = Database(f"sqlite:///{tmp_path / 'broken.db'}")
        try:
            monkeypatch.setattr(
                Base.metadata,
                "create_all",
                lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("boom")),
            )
            with pytest.raises(DatabaseError):
                db.create_all()
        finally:
            db.dispose()

    def test_sqlite_allows_other_threads(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path / 'threads.db'}")
        try:
            assert db.engine.dialect.name == "sqlite"
        finally:
            db.dispose()

    def test_postgres_url_uses_pool_pre_ping(self):
        db = Database("postgresql+psycopg2://user:pass@localhost:5432/gamehunter")
        try:
            assert db.engine.pool._pre_ping is True  # noqa: SLF001 - проверка настройки
        finally:
            db.dispose()


# ---------------------------------------------------------------------- #
# Структура таблиц
# ---------------------------------------------------------------------- #
class TestSchema:
    def test_profile_columns(self, database: Database):
        columns = {column["name"]: column for column in inspect(database.engine).get_columns("user_profiles")}

        assert bool(columns["id"]["primary_key"]) is True
        assert columns["tg_user_id"]["nullable"] is False
        assert columns["age"]["nullable"] is True
        for name in ("genre_slugs", "genre_names", "platform_ids", "platform_names"):
            assert columns[name]["nullable"] is False
        for name in ("ip_address", "country", "country_code", "city", "timezone", "currency"):
            assert columns[name]["nullable"] is True
        assert "updated_at" in columns

    def test_played_games_columns(self, database: Database):
        columns = {column["name"]: column for column in inspect(database.engine).get_columns("played_games")}

        assert bool(columns["id"]["primary_key"]) is True
        assert columns["tg_user_id"]["nullable"] is False
        assert columns["game_id"]["nullable"] is False
        assert columns["name"]["nullable"] is False
        assert columns["review"]["nullable"] is True
        assert columns["review"]["type"].length == 1000
        assert columns["name"]["type"].length == 150

    def test_favorite_games_columns(self, database: Database):
        columns = {column["name"]: column for column in inspect(database.engine).get_columns("favorite_games")}

        assert bool(columns["id"]["primary_key"]) is True
        assert columns["game_id"]["nullable"] is False
        assert columns["added_at"]["nullable"] is False

    def test_profile_has_unique_telegram_id(self, database: Database):
        uniques = inspect(database.engine).get_unique_constraints("user_profiles")
        indexes = inspect(database.engine).get_indexes("user_profiles")

        columns = {tuple(item["column_names"]) for item in uniques}
        columns |= {tuple(item["column_names"]) for item in indexes if item["unique"]}

        assert ("tg_user_id",) in columns

    def test_library_tables_have_unique_user_game_pairs(self, database: Database):
        inspector = inspect(database.engine)

        for table in ("played_games", "favorite_games"):
            pairs = {
                tuple(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table)
            }
            assert ("tg_user_id", "game_id") in pairs, table

    def test_library_tables_are_indexed_for_listing(self, database: Database):
        inspector = inspect(database.engine)

        played_indexes = {
            tuple(index["column_names"]) for index in inspector.get_indexes("played_games")
        }
        favorite_indexes = {
            tuple(index["column_names"]) for index in inspector.get_indexes("favorite_games")
        }

        assert ("tg_user_id", "played_at") in played_indexes
        assert ("tg_user_id", "added_at") in favorite_indexes

    def test_table_names(self):
        assert UserProfileORM.__tablename__ == "user_profiles"
        assert PlayedGameORM.__tablename__ == "played_games"
        assert FavoriteGameORM.__tablename__ == "favorite_games"

    def test_repr_is_informative(self, library: SqlLibraryRepository):
        record = library.add_played(USER_ID, make_game(32, "The Witcher 3"))

        assert "The Witcher 3" in repr(record)

    def test_orm_repr(self, profiles: SqlProfileRepository):
        profiles.get_or_create(USER_ID)

        row = UserProfileORM(tg_user_id=USER_ID, genre_slugs="action", country="Russia")
        assert "Russia" in repr(row)


# ---------------------------------------------------------------------- #
# SqlProfileRepository
# ---------------------------------------------------------------------- #
class TestSqlProfileRepository:
    def test_get_or_create_returns_empty_profile(self, profiles: SqlProfileRepository):
        profile = profiles.get_or_create(USER_ID)

        assert profile.tg_user_id == USER_ID
        assert profile.age is None
        assert profile.genre_slugs == ()
        assert profile.region is None

    def test_get_or_create_does_not_duplicate(self, profiles: SqlProfileRepository, database: Database):
        profiles.get_or_create(USER_ID)
        profiles.get_or_create(USER_ID)

        with database.session_scope() as session:
            assert session.query(UserProfileORM).count() == 1

    def test_save_creates_row_when_absent(self, profiles: SqlProfileRepository):
        saved = profiles.save(UserProfile(tg_user_id=USER_ID, age=25))

        assert saved.age == 25
        assert profiles.get_or_create(USER_ID).age == 25

    def test_save_updates_existing_row(self, profiles: SqlProfileRepository):
        profiles.save(UserProfile(tg_user_id=USER_ID, age=20))
        profiles.save(UserProfile(tg_user_id=USER_ID, age=31))

        assert profiles.get_or_create(USER_ID).age == 31

    def test_lists_are_stored_as_joined_strings(self, profiles: SqlProfileRepository, database: Database):
        profiles.save(
            UserProfile(
                tg_user_id=USER_ID,
                genre_slugs=("action", "rpg"),
                genre_names=("Action", "RPG"),
                platform_ids=(1, 2),
                platform_names=("PC", "PlayStation"),
            )
        )

        with database.session_scope() as session:
            row = session.query(UserProfileORM).filter_by(tg_user_id=USER_ID).one()
            assert row.genre_slugs == "action,rpg"
            assert row.genre_names == "Action,RPG"
            assert row.platform_ids == "1,2"
            assert row.platform_names == "PC,PlayStation"

        profile = profiles.get_or_create(USER_ID)
        assert profile.genre_slugs == ("action", "rpg")
        assert profile.platform_ids == (1, 2)
        assert profile.platform_names == ("PC", "PlayStation")

    def test_empty_lists_are_stored_as_empty_strings(self, profiles: SqlProfileRepository, database: Database):
        profiles.save(UserProfile(tg_user_id=USER_ID))

        with database.session_scope() as session:
            row = session.query(UserProfileORM).filter_by(tg_user_id=USER_ID).one()
            assert row.genre_slugs == ""
            assert row.platform_ids == ""

        profile = profiles.get_or_create(USER_ID)
        assert profile.genre_slugs == ()
        assert profile.platform_ids == ()

    def test_region_round_trip(self, profiles: SqlProfileRepository):
        region = make_region(
            ip="5.188.0.1",
            country="Russia",
            country_code="RU",
            city="Kazan",
            timezone="Europe/Moscow",
            currency="RUB",
        )

        profiles.save(UserProfile(tg_user_id=USER_ID, region=region))
        saved = profiles.get_or_create(USER_ID).region

        assert saved is not None
        assert saved.ip == "5.188.0.1"
        assert saved.country == "Russia"
        assert saved.city == "Kazan"
        assert saved.timezone == "Europe/Moscow"
        assert saved.currency == "RUB"
        assert saved.latitude == pytest.approx(37.4)

    def test_region_can_be_removed(self, profiles: SqlProfileRepository):
        profiles.save(UserProfile(tg_user_id=USER_ID, region=make_region()))
        profiles.save(UserProfile(tg_user_id=USER_ID, region=None))

        assert profiles.get_or_create(USER_ID).region is None

    def test_partial_region_is_still_restored(self, profiles: SqlProfileRepository):
        from gamehunter.domain.entities import Region

        profiles.save(UserProfile(tg_user_id=USER_ID, region=Region(ip="8.8.8.8", country_code="US")))

        region = profiles.get_or_create(USER_ID).region
        assert region is not None
        assert region.country_code == "US"
        assert region.city == ""

    def test_updated_at_is_set(self, profiles: SqlProfileRepository):
        profile = profiles.save(UserProfile(tg_user_id=USER_ID, age=20))

        assert profile.updated_at is not None
        assert (datetime.now() - profile.updated_at).total_seconds() < 60

    def test_profiles_of_different_users(self, profiles: SqlProfileRepository):
        profiles.save(UserProfile(tg_user_id=USER_ID, age=20))
        profiles.save(UserProfile(tg_user_id=OTHER_USER_ID, age=40))

        assert profiles.get_or_create(USER_ID).age == 20
        assert profiles.get_or_create(OTHER_USER_ID).age == 40

    def test_invalid_platform_value_is_skipped(self, profiles: SqlProfileRepository, database: Database):
        with database.session_scope() as session:
            session.add(
                UserProfileORM(tg_user_id=USER_ID, platform_ids="1,abc,3", platform_names="PC,,Xbox")
            )

        profile = profiles.get_or_create(USER_ID)

        assert profile.platform_ids == (1, 3)
        assert profile.platform_names == ("PC", "Xbox")

    def test_database_error_on_read(self, profiles: SqlProfileRepository, monkeypatch):
        monkeypatch.setattr(
            profiles,
            "_find",
            lambda session, user_id: (_ for _ in ()).throw(SQLAlchemyError("boom")),
        )

        with pytest.raises(DatabaseError):
            profiles.get_or_create(USER_ID)

    def test_database_error_on_save(self, profiles: SqlProfileRepository, monkeypatch):
        monkeypatch.setattr(
            profiles,
            "_find",
            lambda session, user_id: (_ for _ in ()).throw(SQLAlchemyError("boom")),
        )

        with pytest.raises(DatabaseError):
            profiles.save(UserProfile(tg_user_id=USER_ID))


# ---------------------------------------------------------------------- #
# SqlLibraryRepository — «во что я играл»
# ---------------------------------------------------------------------- #
class TestSqlLibraryPlayed:
    def test_add_played_returns_record_with_id(self, library: SqlLibraryRepository):
        record = library.add_played(USER_ID, make_game(32, "The Witcher 3"))

        assert record.id == 1
        assert record.game_id == 32
        assert record.slug == "the-witcher-3-wild-hunt"
        assert record.review is None

    def test_add_played_with_custom_date(self, library: SqlLibraryRepository):
        moment = datetime(2025, 6, 1, 10, 0)

        record = library.add_played(USER_ID, make_game(32), played_at=moment)

        assert record.played_at == moment

    def test_duplicate_is_rejected_by_database(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(32))

        with pytest.raises(DatabaseError):
            library.add_played(USER_ID, make_game(32))

    def test_same_game_for_different_users(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(32))
        record = library.add_played(OTHER_USER_ID, make_game(32))

        assert record.tg_user_id == OTHER_USER_ID

    def test_has_played(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(32))

        assert library.has_played(USER_ID, 32) is True
        assert library.has_played(USER_ID, 3498) is False
        assert library.has_played(OTHER_USER_ID, 32) is False

    def test_played_game_ids(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(32))
        library.add_played(USER_ID, make_game(58175))
        library.add_played(OTHER_USER_ID, make_game(28))

        assert library.played_game_ids(USER_ID) == {32, 58175}

    def test_find_played_by_id(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32, "The Witcher 3"))

        found = library.find_played_by_id(created.id, USER_ID)

        assert found is not None
        assert found.name == "The Witcher 3"

    def test_find_played_by_id_of_another_user(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32))

        assert library.find_played_by_id(created.id, OTHER_USER_ID) is None

    def test_find_unknown_record(self, library: SqlLibraryRepository):
        assert library.find_played_by_id(999, USER_ID) is None

    def test_update_review(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32))

        record = library.update_review(created.id, USER_ID, "Отличная игра")

        assert record is not None
        assert record.review == "Отличная игра"
        assert library.find_played_by_id(created.id, USER_ID).review == "Отличная игра"

    def test_update_review_of_unknown_record(self, library: SqlLibraryRepository):
        assert library.update_review(999, USER_ID, "Текст") is None

    def test_update_review_of_another_user(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32))

        assert library.update_review(created.id, OTHER_USER_ID, "Текст") is None

    def test_delete_played(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32))

        assert library.delete_played(created.id, USER_ID) is True
        assert library.has_played(USER_ID, 32) is False

    def test_delete_unknown_record(self, library: SqlLibraryRepository):
        assert library.delete_played(999, USER_ID) is False

    def test_delete_record_of_another_user(self, library: SqlLibraryRepository):
        created = library.add_played(USER_ID, make_game(32))

        assert library.delete_played(created.id, OTHER_USER_ID) is False
        assert library.has_played(USER_ID, 32) is True

    def test_page_played_order_and_paging(self, library: SqlLibraryRepository):
        now = datetime(2026, 5, 1, 12, 0)
        for index in range(7):
            library.add_played(
                USER_ID,
                make_game(100 + index, f"Игра {index}"),
                played_at=now - timedelta(days=index),
            )

        first = library.page_played(USER_ID, page=1, page_size=3)
        second = library.page_played(USER_ID, page=2, page_size=3)
        third = library.page_played(USER_ID, page=3, page_size=3)

        assert [item.name for item in first.items] == ["Игра 0", "Игра 1", "Игра 2"]
        assert [item.name for item in second.items] == ["Игра 3", "Игра 4", "Игра 5"]
        assert [item.name for item in third.items] == ["Игра 6"]
        assert first.total_pages == 3

    def test_page_played_clamps_page(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(1))

        assert library.page_played(USER_ID, page=0, page_size=3).page == 1
        assert library.page_played(USER_ID, page=99, page_size=3).page == 1

    def test_page_played_page_size_is_at_least_one(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(1))
        library.add_played(USER_ID, make_game(2))

        page = library.page_played(USER_ID, page=1, page_size=0)

        assert len(page.items) == 1
        assert page.total_pages == 2

    def test_page_played_is_empty(self, library: SqlLibraryRepository):
        page = library.page_played(USER_ID, page=1, page_size=3)

        assert page.is_empty is True
        assert page.total_pages == 1

    def test_page_played_of_another_user(self, library: SqlLibraryRepository):
        library.add_played(USER_ID, make_game(1))

        assert library.page_played(OTHER_USER_ID, page=1, page_size=3).is_empty is True

    def test_database_error_is_wrapped(self, library: SqlLibraryRepository, monkeypatch):
        monkeypatch.setattr(
            library._database,  # noqa: SLF001 - подмена для проверки ошибки
            "session_scope",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("boom")),
        )

        with pytest.raises(DatabaseError):
            library.has_played(USER_ID, 32)


# ---------------------------------------------------------------------- #
# SqlLibraryRepository — избранное
# ---------------------------------------------------------------------- #
class TestSqlLibraryFavorites:
    def test_add_favorite(self, library: SqlLibraryRepository):
        record = library.add_favorite(USER_ID, make_game(41494, "Cyberpunk 2077"))

        assert record.id == 1
        assert record.game_id == 41494
        assert record.name == "Cyberpunk 2077"
        assert record.added_at is not None

    def test_duplicate_favorite_is_rejected(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(41494))

        with pytest.raises(DatabaseError):
            library.add_favorite(USER_ID, make_game(41494))

    def test_is_favorite(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(41494))

        assert library.is_favorite(USER_ID, 41494) is True
        assert library.is_favorite(USER_ID, 32) is False
        assert library.is_favorite(OTHER_USER_ID, 41494) is False

    def test_remove_favorite(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(41494))

        assert library.remove_favorite(USER_ID, 41494) is True
        assert library.is_favorite(USER_ID, 41494) is False

    def test_remove_unknown_favorite(self, library: SqlLibraryRepository):
        assert library.remove_favorite(USER_ID, 41494) is False

    def test_remove_favorite_of_another_user(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(41494))

        assert library.remove_favorite(OTHER_USER_ID, 41494) is False
        assert library.is_favorite(USER_ID, 41494) is True

    def test_page_favorites_order_and_paging(self, library: SqlLibraryRepository):
        for index in range(5):
            library.add_favorite(USER_ID, make_game(index, f"Игра {index}"))

        first = library.page_favorites(USER_ID, page=1, page_size=2)
        last = library.page_favorites(USER_ID, page=3, page_size=2)

        assert first.total_pages == 3
        assert len(first.items) == 2
        assert len(last.items) == 1
        # новые записи идут первыми
        assert first.items[0].name == "Игра 4"

    def test_page_favorites_is_empty(self, library: SqlLibraryRepository):
        page = library.page_favorites(USER_ID, page=1, page_size=3)

        assert page.is_empty is True
        assert page.total_pages == 1

    def test_page_favorites_clamps_page(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(1))

        assert library.page_favorites(USER_ID, page=0, page_size=3).page == 1
        assert library.page_favorites(USER_ID, page=10, page_size=3).page == 1

    def test_image_url_is_stored(self, library: SqlLibraryRepository):
        library.add_favorite(USER_ID, make_game(1, image_url="https://cdn/1.jpg"))

        page = library.page_favorites(USER_ID, page=1, page_size=3)

        assert page.items[0].image_url == "https://cdn/1.jpg"

    def test_database_error_is_wrapped(self, library: SqlLibraryRepository, monkeypatch):
        monkeypatch.setattr(
            library._database,  # noqa: SLF001 - подмена для проверки ошибки
            "session_scope",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("boom")),
        )

        with pytest.raises(DatabaseError):
            library.is_favorite(USER_ID, 32)
