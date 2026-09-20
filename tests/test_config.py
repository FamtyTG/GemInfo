"""Тесты загрузки настроек из переменных окружения (секреты не хранятся в коде)."""

from __future__ import annotations

import pytest

from travelhunter.config import DEFAULT_SQLITE_URL, Settings
from travelhunter.domain.exceptions import ConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Убираем влияние реального окружения на тесты."""
    for name in (
        "BOT_TOKEN",
        "DATABASE_URL",
        "NINJAS_API_KEY",
        "GEONAMES_USERNAME",
        "GEONAMES_COUNTRY_BIAS",
        "WIKIPEDIA_LANGUAGE",
        "MAX_HOLIDAYS",
        "NEARBY_RADIUS_KM",
        "NOTE_MAX_LENGTH",
        "HTTP_TIMEOUT",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_reads_all_values(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/db")
    monkeypatch.setenv("NINJAS_API_KEY", "ninjas-key")
    monkeypatch.setenv("GEONAMES_USERNAME", "student")
    monkeypatch.setenv("MAX_HOLIDAYS", "3")
    monkeypatch.setenv("NEARBY_RADIUS_KM", "300")
    monkeypatch.setenv("NOTE_MAX_LENGTH", "500")

    settings = Settings.from_env(env_file=None)

    assert settings.bot_token == "123:ABC"
    assert settings.database_url.startswith("postgresql+psycopg2://")
    assert settings.ninjas_api_key == "ninjas-key"
    assert settings.geonames_username == "student"
    assert settings.max_holidays == 3
    assert settings.nearby_radius_km == 300
    assert settings.note_max_length == 500


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")

    settings = Settings.from_env(env_file=None)

    assert settings.database_url == DEFAULT_SQLITE_URL
    assert settings.country == "RU"
    assert settings.holidays_days_ahead == 7
    assert settings.max_holidays == 5
    assert settings.nearby_radius_km == 500
    assert settings.max_nearby_cities == 5
    assert settings.history_page_size == 5
    assert settings.note_max_length == 1000
    assert settings.http_timeout == 10
    assert settings.wikipedia_language == "ru"


def test_missing_bot_token_raises_config_error():
    with pytest.raises(ConfigError) as exc_info:
        Settings.from_env(env_file=None)

    assert "BOT_TOKEN" in str(exc_info.value)


def test_blank_bot_token_is_not_accepted(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "   ")

    with pytest.raises(ConfigError):
        Settings.from_env(env_file=None)


def test_invalid_number_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("MAX_HOLIDAYS", "много")

    assert Settings.from_env(env_file=None).max_holidays == 5


def test_missing_api_keys_are_reported_as_warnings(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")

    warnings = Settings.from_env(env_file=None).missing_keys_warnings()

    assert any("NINJAS_API_KEY" in warning for warning in warnings)
    assert any("GEONAMES_USERNAME" in warning for warning in warnings)


def test_no_warnings_when_keys_are_set(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("NINJAS_API_KEY", "key")
    monkeypatch.setenv("GEONAMES_USERNAME", "user")

    assert Settings.from_env(env_file=None).missing_keys_warnings() == []


def test_env_file_is_loaded(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=token-from-file\nNINJAS_API_KEY=key-from-file\n", encoding="utf-8"
    )

    settings = Settings.from_env(env_file=str(env_file))

    assert settings.bot_token == "token-from-file"
    assert settings.ninjas_api_key == "key-from-file"
