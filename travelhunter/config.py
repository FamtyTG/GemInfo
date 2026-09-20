"""Настройки приложения.

Все секретные значения (токен бота, API-ключи, строка подключения к базе)
читаются из переменных окружения или файла ``.env``, который НЕ добавляется
в Git. В исходном коде ключей нет.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from travelhunter.domain.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Строка подключения к локальному SQLite-файлу.
# Используется, если DATABASE_URL не задан (удобно для быстрого запуска).
DEFAULT_SQLITE_URL = "sqlite:///travelhunter.db"


def _env_int(name: str, default: int) -> int:
    """Читает целое число из окружения, при ошибке возвращает значение по умолчанию."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("Параметр %s=%r не является числом, использую %s", name, raw, default)
        return default


@dataclass(frozen=True)
class Settings:
    """Неизменяемый набор настроек приложения."""

    # --- Telegram ---
    bot_token: str

    # --- База данных ---
    database_url: str

    # --- Внешние API ---
    ninjas_api_key: str = ""
    geonames_username: str = ""
    geonames_country_bias: str = ""
    wikipedia_language: str = "ru"

    # --- Параметры предметной области ---
    country: str = "RU"
    holidays_days_ahead: int = 7
    max_holidays: int = 5
    nearby_radius_km: int = 500
    max_nearby_cities: int = 5
    history_page_size: int = 5
    note_max_length: int = 1000

    # --- Технические параметры ---
    http_timeout: int = 10
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_file: Optional[str] = ".env") -> "Settings":
        """Создаёт настройки из переменных окружения (и файла .env)."""
        if env_file:
            path = Path(env_file)
            if path.exists():
                load_dotenv(path, override=False)
                logger.info("Загружен файл настроек: %s", path)
            else:
                load_dotenv(override=False)  # ищем .env стандартным способом

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ConfigError(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите "
                "токен бота, полученный у @BotFather."
            )

        database_url = os.getenv("DATABASE_URL", "").strip() or DEFAULT_SQLITE_URL
        if database_url == DEFAULT_SQLITE_URL:
            logger.warning(
                "DATABASE_URL не задан — используется локальный SQLite (%s). "
                "Для сдачи проекта настройте PostgreSQL.",
                DEFAULT_SQLITE_URL,
            )

        settings = cls(
            bot_token=bot_token,
            database_url=database_url,
            ninjas_api_key=os.getenv("NINJAS_API_KEY", "").strip(),
            geonames_username=os.getenv("GEONAMES_USERNAME", "").strip(),
            geonames_country_bias=os.getenv("GEONAMES_COUNTRY_BIAS", "").strip(),
            wikipedia_language=os.getenv("WIKIPEDIA_LANGUAGE", "ru").strip() or "ru",
            country=os.getenv("HOLIDAYS_COUNTRY", "RU").strip() or "RU",
            holidays_days_ahead=_env_int("HOLIDAYS_DAYS", 7),
            max_holidays=_env_int("MAX_HOLIDAYS", 5),
            nearby_radius_km=_env_int("NEARBY_RADIUS_KM", 500),
            max_nearby_cities=_env_int("MAX_NEARBY_CITIES", 5),
            history_page_size=_env_int("HISTORY_PAGE_SIZE", 5),
            note_max_length=_env_int("NOTE_MAX_LENGTH", 1000),
            http_timeout=_env_int("HTTP_TIMEOUT", 10),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
        settings.log_missing_keys()
        return settings

    def log_missing_keys(self) -> None:
        """Пишет в лог предупреждения о незаполненных ключах внешних API."""
        for warning in self.missing_keys_warnings():
            logger.warning("%s", warning)

    def missing_keys_warnings(self) -> List[str]:
        """Возвращает список предупреждений о недостающих ключах (для диагностики)."""
        warnings: List[str] = []
        if not self.ninjas_api_key:
            warnings.append(
                "Не задан NINJAS_API_KEY — экран «Праздники на 7 дней» "
                "покажет сообщение об ошибке."
            )
        if not self.geonames_username:
            warnings.append(
                "Не задан GEONAMES_USERNAME — экран «Города куда съездить» "
                "покажет сообщение об ошибке."
            )
        return warnings
