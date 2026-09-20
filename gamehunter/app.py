"""Композиционный корень приложения.

Здесь создаются объекты всех трёх слоёв и связываются между собой
(внедрение зависимостей через конструкторы, без глобальных переменных):

    infrastructure (клиенты API, база данных)
            ↓  реализуют интерфейсы домена
        domain (сервисы бизнес-логики)
            ↓  используются
    presentation (экраны, клавиатуры, обработчики Telegram)
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import telebot

from gamehunter.config import Settings
from gamehunter.domain.age_ratings import AgePolicy
from gamehunter.domain.exceptions import ConfigError, DatabaseError, GameHunterError
from gamehunter.domain.services import GameService, LibraryService, ProfileService
from gamehunter.infrastructure.api import (
    IpLocationClient,
    JsonHttpClient,
    RawgClient,
)
from gamehunter.infrastructure.db import Database, SqlLibraryRepository, SqlProfileRepository
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.handlers import BotHandlers
from gamehunter.presentation.screens import ScreenContainer, build_screens
from gamehunter.presentation.state import StateStorage

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Настраивает логирование приложения."""
    resolved = getattr(logging, level.strip().upper(), logging.INFO)
    logging.basicConfig(level=resolved, format=LOG_FORMAT, stream=sys.stdout)
    # basicConfig не меняет уровень, если обработчики уже добавлены (например, в тестах)
    logging.getLogger().setLevel(resolved)
    # telebot пишет много служебных сообщений — оставляем только важное
    logging.getLogger("telebot").setLevel(logging.WARNING)


class Application:
    """Собирает и запускает Telegram-бота GameHunter."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # ---------------- Слой 3. Инфраструктура ---------------- #
        self.database = Database(settings.database_url)
        self.database.create_all()

        http_client = JsonHttpClient(timeout=settings.http_timeout)
        self.games_provider = RawgClient(
            http_client,
            api_key=settings.rawg_api_key,
            page_size=settings.max_games,
            language=settings.catalog_language,
        )
        self.ip_provider = IpLocationClient(
            http_client, base_url=settings.ip_location_base_url
        )
        self.profile_repository = SqlProfileRepository(self.database)
        self.library_repository = SqlLibraryRepository(self.database)

        # ---------------- Слой 2. Бизнес-логика ---------------- #
        age_policy = AgePolicy()
        self.game_service = GameService(
            provider=self.games_provider,
            age_policy=age_policy,
            max_games=settings.max_games,
            max_genres=settings.max_genres,
            max_franchises=settings.max_franchises,
            details_fetch_limit=settings.details_fetch_limit,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            ordering=settings.default_ordering,
        )
        self.profile_service = ProfileService(
            repository=self.profile_repository,
            ip_provider=self.ip_provider,
            age_policy=age_policy,
        )
        self.library_service = LibraryService(
            repository=self.library_repository,
            page_size=settings.library_page_size,
            note_max_length=settings.review_max_length,
        )

        # ---------------- Слой 1. Представление ---------------- #
        self.bot = telebot.TeleBot(settings.bot_token, parse_mode=None, threaded=True)
        self.gateway = TelegramGateway(self.bot)
        self.storage = StateStorage()
        self.screens: ScreenContainer = build_screens(
            gateway=self.gateway,
            storage=self.storage,
            game_service=self.game_service,
            profile_service=self.profile_service,
            library_service=self.library_service,
        )
        self.handlers = BotHandlers(
            bot=self.bot,
            gateway=self.gateway,
            storage=self.storage,
            screens=self.screens,
        )

        logger.info("Приложение GameHunter собрано")

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Регистрирует обработчики и запускает long polling."""
        self.handlers.register()
        logger.info("Telegram-бот GameHunter запущен. Для остановки нажмите Ctrl+C")
        self.bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=True)

    def stop(self) -> None:
        """Останавливает бота и освобождает ресурсы."""
        try:
            self.bot.stop_polling()
        except Exception:  # noqa: BLE001 - остановка не должна вызывать ошибок
            logger.debug("Опрос Telegram уже остановлен")
        self.database.dispose()
        logger.info("Бот остановлен")


def build_application(env_file: Optional[str] = ".env") -> Application:
    """Создаёт приложение из настроек окружения (удобно для тестов и запуска)."""
    return Application(Settings.from_env(env_file))


def main() -> None:
    """Точка входа: загрузка настроек, сборка приложения и запуск бота."""
    configure_logging()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"[ОШИБКА НАСТРОЙКИ] {exc}", file=sys.stderr)
        print("Скопируйте .env.example в .env и заполните значения.", file=sys.stderr)
        sys.exit(1)

    configure_logging(settings.log_level)

    try:
        application = Application(settings)
    except DatabaseError as exc:
        logger.error("Не удалось подключиться к базе данных: %s", exc.user_message)
        print(
            "[ОШИБКА БАЗЫ ДАННЫХ] Проверьте DATABASE_URL и доступность PostgreSQL.",
            file=sys.stderr,
        )
        sys.exit(1)
    except GameHunterError as exc:
        logger.error("Ошибка запуска: %s", exc)
        print(f"[ОШИБКА ЗАПУСКА] {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        application.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    finally:
        application.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
