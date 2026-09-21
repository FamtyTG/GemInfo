"""Тесты скрипта инициализации базы данных (scripts/init_db.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from gamehunter.domain.services import LibraryService, ProfileService
from gamehunter.infrastructure.db import Database, SqlLibraryRepository, SqlProfileRepository

SPEC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "init_db.py"


def load_module():
    """Загружает скрипт как модуль (он лежит вне пакета)."""
    spec = importlib.util.spec_from_file_location("init_db", SPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    # модуль нужен в sys.modules ещё до выполнения: dataclass разрешает аннотации по имени
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


init_db = load_module()


@pytest.fixture()
def database(tmp_path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'demo.db'}")
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456789:TEST")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("RAWG_API_KEY", "test-key")
    return monkeypatch


# --------------------------------------------------------------------------- #
# Демонстрационные данные
# --------------------------------------------------------------------------- #
class TestDemoData:
    def test_games_are_real_rawg_ids(self):
        ids = {game.id for game in init_db.DEMO_PLAYED_GAMES}

        assert ids == {32, 3498, 58175}

    def test_favorite_games_are_real_rawg_ids(self):
        ids = {game.id for game in init_db.DEMO_FAVORITE_GAMES}

        assert ids == {41494, 28}

    def test_games_have_required_fields(self):
        for game in init_db.DEMO_PLAYED_GAMES + init_db.DEMO_FAVORITE_GAMES:
            assert game.name
            assert game.slug
            assert game.genres

    def test_reviews_fit_the_limit(self):
        for review in init_db.DEMO_REVIEWS:
            assert len(review) <= 1000

    def test_genres_and_platforms_are_defined(self):
        assert [genre.slug for genre in init_db.DEMO_GENRES] == [
            "action",
            "adventure",
            "role-playing-games-rpg",
        ]
        assert [platform.id for platform in init_db.DEMO_PLATFORMS] == [1, 2]


class TestCreateTables:
    def test_creates_tables(self, database: Database):
        init_db.create_tables(database)

        from sqlalchemy import inspect

        tables = set(inspect(database.engine).get_table_names())

        assert {"user_profiles", "played_games", "favorite_games"} <= tables

    def test_is_idempotent(self, database: Database):
        init_db.create_tables(database)
        init_db.create_tables(database)  # не должно вызывать исключение


class TestAddDemoData:
    def test_fills_profile(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database)

        profile = ProfileService(
            SqlProfileRepository(database), ip_provider=init_db._NoIpProvider()
        ).get_profile(init_db.DEMO_USER_ID)

        assert profile.age == 27
        assert profile.genre_slugs == ("action", "adventure", "role-playing-games-rpg")
        assert profile.platform_ids == (1, 2)

    def test_adds_played_games_with_reviews(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database)

        library = LibraryService(SqlLibraryRepository(database))
        history = library.get_played_history(init_db.DEMO_USER_ID).items

        assert [record.game_id for record in history] == [32, 3498, 58175]
        assert history[0].review is not None  # отзыв к The Witcher 3
        assert history[-1].review is None  # у God of War отзыва нет

    def test_adds_favorites(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database)

        library = LibraryService(SqlLibraryRepository(database))

        favorites = library.get_favorites(init_db.DEMO_USER_ID).items

        assert {record.game_id for record in favorites} == {41494, 28}

    def test_returns_number_of_records(self, database: Database):
        init_db.create_tables(database)

        total = init_db.add_demo_data(database)

        assert total == len(init_db.DEMO_PLAYED_GAMES) + len(init_db.DEMO_FAVORITE_GAMES)

    def test_is_idempotent(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database)
        init_db.add_demo_data(database)

        library = LibraryService(SqlLibraryRepository(database))

        assert len(library.get_played_history(init_db.DEMO_USER_ID).items) == 3
        assert len(library.get_favorites(init_db.DEMO_USER_ID).items) == 2

    def test_custom_user_id(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database, user_id=42)

        library = LibraryService(SqlLibraryRepository(database))

        assert len(library.get_played_history(42).items) == 3
        assert library.get_played_history(init_db.DEMO_USER_ID).items == []

    def test_played_dates_go_back_in_time(self, database: Database):
        init_db.create_tables(database)
        init_db.add_demo_data(database)

        library = LibraryService(SqlLibraryRepository(database))
        dates = [
            record.played_at
            for record in library.get_played_history(init_db.DEMO_USER_ID).items
        ]

        # история отдаётся от новых записей к старым, а даты в демо-данных «уходят» в прошлое
        assert dates == sorted(dates, reverse=True)
        assert dates[0] > dates[-1]

    def test_no_ip_provider_returns_none(self):
        assert init_db._NoIpProvider().locate("8.8.8.8") is None


# --------------------------------------------------------------------------- #
# Запуск из командной строки
# --------------------------------------------------------------------------- #
class TestCli:
    def test_creates_tables(self, env, capsys, tmp_path):
        code = init_db.main([])

        assert code == 0
        assert "Готово. База данных:" in capsys.readouterr().out
        assert (tmp_path / "cli.db").exists()

    def test_demo_flag(self, env, capsys, tmp_path):
        code = init_db.main(["--demo"])

        assert code == 0
        database = Database(f"sqlite:///{tmp_path / 'cli.db'}")
        try:
            library = LibraryService(SqlLibraryRepository(database))
            assert len(library.get_played_history(init_db.DEMO_USER_ID).items) == 3
        finally:
            database.dispose()

    def test_custom_user_id_and_env_file(self, env, capsys, tmp_path):
        # переменная из файла настроек не должна перекрываться значением из окружения
        env.delenv("DATABASE_URL")
        env_file = tmp_path / "custom.env"
        env_file.write_text(
            "BOT_TOKEN=123456789:TEST\n"
            f"DATABASE_URL=sqlite:///{tmp_path / 'custom.db'}\n"
            "RAWG_API_KEY=test-key\n",
            encoding="utf-8",
        )

        code = init_db.main(["--demo", "--user-id", "7", "--env-file", str(env_file)])

        assert code == 0
        database = Database(f"sqlite:///{tmp_path / 'custom.db'}")
        try:
            library = LibraryService(SqlLibraryRepository(database))
            assert len(library.get_played_history(7).items) == 3
        finally:
            database.dispose()

    def test_settings_error(self, env, capsys):
        env.delenv("BOT_TOKEN")
        env.setenv("ENV_FILE", "")

        code = init_db.main(["--env-file", "нет-такого-файла.env"])

        assert code == 1
        assert "[ОШИБКА НАСТРОЙКИ]" in capsys.readouterr().err

    def test_database_error(self, env, capsys, tmp_path):
        env.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'нет' / 'папки' / 'db.sqlite'}")

        code = init_db.main([])

        assert code == 1
        assert "[ОШИБКА]" in capsys.readouterr().err

    def test_help_message(self, capsys):
        with pytest.raises(SystemExit) as info:
            init_db.main(["--help"])

        assert info.value.code == 0
        output = capsys.readouterr().out
        assert "--demo" in output
        assert "--user-id" in output
