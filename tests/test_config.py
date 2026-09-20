"""Тесты настроек приложения (переменные окружения и файл .env)."""

from __future__ import annotations

import pytest

from gamehunter.config import DEFAULT_SQLITE_URL, Settings
from gamehunter.domain.exceptions import ConfigError


@pytest.fixture()
def env(monkeypatch):
    """Чистое окружение с обязательными настройками."""
    for name in (
        "BOT_TOKEN",
        "DATABASE_URL",
        "RAWG_API_KEY",
        "IP_LOCATION_BASE_URL",
        "CATALOG_LANGUAGE",
        "MAX_GAMES",
        "MAX_GENRES",
        "MAX_FRANCHISES",
        "DETAILS_FETCH_LIMIT",
        "LIBRARY_PAGE_SIZE",
        "REVIEW_MAX_LENGTH",
        "DEFAULT_ORDERING",
        "HTTP_TIMEOUT",
        "CACHE_TTL_SECONDS",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123456789:TEST")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    return monkeypatch


class TestRequiredSettings:
    def test_reads_bot_token(self, env):
        settings = Settings.from_env(env_file=None)

        assert settings.bot_token == "123456789:TEST"

    def test_missing_bot_token_raises_config_error(self, env):
        env.delenv("BOT_TOKEN")

        with pytest.raises(ConfigError):
            Settings.from_env(env_file=None)

    def test_empty_bot_token_raises_config_error(self, env):
        env.setenv("BOT_TOKEN", "   ")

        with pytest.raises(ConfigError) as info:
            Settings.from_env(env_file=None)

        assert "BOT_TOKEN" in str(info.value)

    def test_config_error_has_user_message(self, env):
        env.delenv("BOT_TOKEN")

        with pytest.raises(ConfigError) as info:
            Settings.from_env(env_file=None)

        assert info.value.user_message.strip()

    def test_reads_database_url(self, env):
        assert Settings.from_env(env_file=None).database_url == "sqlite:///test.db"

    def test_default_database_is_sqlite(self, env):
        env.delenv("DATABASE_URL")

        assert Settings.from_env(env_file=None).database_url == DEFAULT_SQLITE_URL

    def test_empty_database_url_falls_back_to_default(self, env):
        env.setenv("DATABASE_URL", "  ")

        assert Settings.from_env(env_file=None).database_url == DEFAULT_SQLITE_URL


class TestApiKeys:
    def test_reads_rawg_key(self, env):
        env.setenv("RAWG_API_KEY", "my-secret-key")

        assert Settings.from_env(env_file=None).rawg_api_key == "my-secret-key"

    def test_rawg_key_is_optional(self, env):
        assert Settings.from_env(env_file=None).rawg_api_key == ""

    def test_keys_are_trimmed(self, env):
        env.setenv("RAWG_API_KEY", "  key  ")

        assert Settings.from_env(env_file=None).rawg_api_key == "key"

    def test_warning_when_rawg_key_is_missing(self, env):
        settings = Settings.from_env(env_file=None)

        warnings = settings.missing_keys_warnings()

        assert len(warnings) == 1
        assert "RAWG_API_KEY" in warnings[0]

    def test_no_warnings_when_key_is_set(self, env):
        env.setenv("RAWG_API_KEY", "key")

        assert Settings.from_env(env_file=None).missing_keys_warnings() == []

    def test_log_missing_keys_does_not_raise(self, env, caplog):
        Settings.from_env(env_file=None).log_missing_keys()

        assert "RAWG_API_KEY" in caplog.text

    def test_no_secret_values_in_warnings(self, env):
        env.setenv("RAWG_API_KEY", "key")
        env.setenv("BOT_TOKEN", "secret-token")

        warnings = Settings.from_env(env_file=None).missing_keys_warnings()

        assert "secret-token" not in "".join(warnings)


class TestOptionalSettings:
    def test_defaults(self, env):
        settings = Settings.from_env(env_file=None)

        assert settings.max_games == 5
        assert settings.max_genres == 12
        assert settings.max_franchises == 5
        assert settings.details_fetch_limit == 8
        assert settings.library_page_size == 5
        assert settings.review_max_length == 1000
        assert settings.default_ordering == "-rating"
        assert settings.http_timeout == 10
        assert settings.cache_ttl_seconds == 600
        assert settings.log_level == "INFO"
        assert settings.catalog_language == "ru"
        assert settings.ip_location_base_url == "https://ipapi.co"

    def test_custom_values(self, env):
        env.setenv("MAX_GAMES", "10")
        env.setenv("MAX_GENRES", "20")
        env.setenv("LIBRARY_PAGE_SIZE", "4")
        env.setenv("REVIEW_MAX_LENGTH", "500")
        env.setenv("HTTP_TIMEOUT", "3")
        env.setenv("LOG_LEVEL", "debug")
        env.setenv("DEFAULT_ORDERING", "-released")
        env.setenv("IP_LOCATION_BASE_URL", "https://ipwho.is")
        env.setenv("CATALOG_LANGUAGE", "en")

        settings = Settings.from_env(env_file=None)

        assert settings.max_games == 10
        assert settings.max_genres == 20
        assert settings.library_page_size == 4
        assert settings.review_max_length == 500
        assert settings.http_timeout == 3
        assert settings.log_level == "DEBUG"
        assert settings.default_ordering == "-released"
        assert settings.ip_location_base_url == "https://ipwho.is"
        assert settings.catalog_language == "en"

    @pytest.mark.parametrize("name", ["MAX_GAMES", "HTTP_TIMEOUT", "CACHE_TTL_SECONDS"])
    def test_invalid_number_falls_back_to_default(self, env, name, caplog):
        env.setenv(name, "не число")

        settings = Settings.from_env(env_file=None)

        assert name in caplog.text
        assert getattr(settings, name.lower()) > 0

    def test_empty_number_falls_back_to_default(self, env):
        env.setenv("MAX_GAMES", "   ")

        assert Settings.from_env(env_file=None).max_games == 5

    def test_empty_ordering_falls_back(self, env):
        env.setenv("DEFAULT_ORDERING", "")

        assert Settings.from_env(env_file=None).default_ordering == "-rating"

    def test_empty_ip_base_url_falls_back(self, env):
        env.setenv("IP_LOCATION_BASE_URL", "  ")

        assert Settings.from_env(env_file=None).ip_location_base_url == "https://ipapi.co"


class TestEnvFile:
    def test_reads_values_from_env_file(self, tmp_path, env):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "BOT_TOKEN=111:from-file\n"
            "DATABASE_URL=sqlite:///from_file.db\n"
            "RAWG_API_KEY=file-key\n",
            encoding="utf-8",
        )
        env.delenv("BOT_TOKEN")
        env.delenv("DATABASE_URL")

        settings = Settings.from_env(str(env_file))

        assert settings.bot_token == "111:from-file"
        assert settings.database_url == "sqlite:///from_file.db"
        assert settings.rawg_api_key == "file-key"

    def test_environment_has_priority_over_file(self, tmp_path, env):
        env_file = tmp_path / ".env"
        env_file.write_text("BOT_TOKEN=111:from-file\n", encoding="utf-8")

        settings = Settings.from_env(str(env_file))

        assert settings.bot_token == "123456789:TEST"

    def test_missing_env_file_is_not_an_error(self, tmp_path, env):
        settings = Settings.from_env(str(tmp_path / "нет-такого-файла.env"))

        assert settings.bot_token == "123456789:TEST"

    def test_settings_are_immutable(self, env):
        settings = Settings.from_env(env_file=None)

        with pytest.raises(Exception):
            settings.max_games = 100  # type: ignore[misc]


class TestSqliteWarning:
    def test_warns_about_sqlite(self, env, caplog):
        env.delenv("DATABASE_URL")

        Settings.from_env(env_file=None)

        assert "SQLite" in caplog.text

    def test_no_warning_for_postgres(self, env, caplog):
        env.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/gamehunter")

        Settings.from_env(env_file=None)

        assert "DATABASE_URL не задан" not in caplog.text
