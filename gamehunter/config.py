"""Настройки приложения GameHunter.

Все секретные значения (токен бота, API-ключ каталога игр, строка подключения
к базе) читаются из переменных окружения или файла ``.env``, который НЕ
добавляется в Git. В исходном коде ключей нет.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from gamehunter.domain.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Строка подключения к локальному SQLite-файлу.
# Используется, если DATABASE_URL не задан (удобно для быстрого запуска).
DEFAULT_SQLITE_URL = "sqlite:///gamehunter.db"


def _env_int(name: str, default: int) -> int:
    """Читает целое число из окружения, при ошибке возвращает значение по умолчанию."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(
            "Параметр %s=%r не является числом, использую значение по умолчанию %s",
            name,
            raw,
            default,
        )
        return default


@dataclass(frozen=True)
class Settings:
    """Неизменяемый набор настроек приложения."""

    # --- Telegram ---
    bot_token: str

    # --- База данных ---
    database_url: str

    # --- Внешние API ---
    rawg_api_key: str = ""
    ip_location_base_url: str = "https://ipapi.co"
    catalog_language: str = "ru"

    # --- Параметры предметной области ---
    max_games: int = 5                # сколько игр показывать на одной странице
    max_genres: int = 12              # сколько жанров предлагать на выбор
    max_franchises: int = 5           # сколько франшиз показывать в результатах поиска
    details_fetch_limit: int = 8      # сколько карточек догружать для возрастного фильтра
    library_page_size: int = 5        # записей на странице библиотеки
    review_max_length: int = 1000     # максимальная длина отзыва
    default_ordering: str = "-rating" # сортировка результатов подбора

    # --- Технические параметры ---
    http_timeout: int = 10
    cache_ttl_seconds: int = 600
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
            rawg_api_key=os.getenv("RAWG_API_KEY", "").strip(),
            ip_location_base_url=os.getenv(
                "IP_LOCATION_BASE_URL", "https://ipapi.co"
            ).strip()
            or "https://ipapi.co",
            catalog_language=os.getenv("CATALOG_LANGUAGE", "ru").strip() or "ru",
            max_games=_env_int("MAX_GAMES", 5),
            max_genres=_env_int("MAX_GENRES", 12),
            max_franchises=_env_int("MAX_FRANCHISES", 5),
            details_fetch_limit=_env_int("DETAILS_FETCH_LIMIT", 8),
            library_page_size=_env_int("LIBRARY_PAGE_SIZE", 5),
            review_max_length=_env_int("REVIEW_MAX_LENGTH", 1000),
            default_ordering=os.getenv("DEFAULT_ORDERING", "-rating").strip() or "-rating",
            http_timeout=_env_int("HTTP_TIMEOUT", 10),
            cache_ttl_seconds=_env_int("CACHE_TTL_SECONDS", 600),
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
        if not self.rawg_api_key:
            warnings.append(
                "Не задан RAWG_API_KEY — подбор игр, жанры и поиск по франшизе "
                "покажут сообщение об ошибке. Бесплатный ключ: https://rawg.io/apidocs"
            )
        return warnings
