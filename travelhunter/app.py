"""Композиционный корень приложения.

Здесь создаются объекты всех трёх слоёв и связываются между собой
(внедрение зависимостей через конструкторы, без глобальных переменных):

    infrastructure (API-клиенты, база данных)
            ↓  реализуют интерфейсы
        domain (сервисы бизнес-логики)
            ↓  используются
    presentation (экраны, клавиатуры, обработчики Telegram)
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import telebot

from travelhunter.config import Settings
from travelhunter.domain.exceptions import ConfigError, DatabaseError, TravelHunterError
from travelhunter.domain.services import CityService, HolidayService, TripService
from travelhunter.infrastructure.api import (
    GeoNamesClient,
    JsonHttpClient,
    NinjasHolidaysClient,
    WikipediaClient,
)
from travelhunter.infrastructure.db import Database, SqlTripRepository
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.handlers import BotHandlers
from travelhunter.presentation.screens import ScreenContainer, build_screens
from travelhunter.presentation.state import StateStorage

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Настраивает логирование приложения."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
    )
    # telebot пишет много служебных сообщений — оставляем только важное
    logging.getLogger("telebot").setLevel(logging.WARNING)


class Application:
    """Собирает и запускает Telegram-бота TravelHunter."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # ---------------- Слой 3. Инфраструктура ---------------- #
        self.database = Database(settings.database_url)
        self.database.create_all()

        http_client = JsonHttpClient(timeout=settings.http_timeout)
        self.holidays_provider = NinjasHolidaysClient(
            http_client, api_key=settings.ninjas_api_key
        )
        self.city_provider = GeoNamesClient(
            http_client,
            username=settings.geonames_username,
            country_bias=settings.geonames_country_bias,
            language=settings.wikipedia_language,
        )
        self.city_info_provider = WikipediaClient(
            http_client, language=settings.wikipedia_language
        )
        self.trip_repository = SqlTripRepository(self.database)

        # ---------------- Слой 2. Бизнес-логика ---------------- #
        self.holiday_service = HolidayService(
            provider=self.holidays_provider,
            days_ahead=settings.holidays_days_ahead,
            max_holidays=settings.max_holidays,
            country=settings.country,
        )
        self.city_service = CityService(
            city_provider=self.city_provider,
            city_info_provider=self.city_info_provider,
            radius_km=settings.nearby_radius_km,
            max_cities=settings.max_nearby_cities,
        )
        self.trip_service = TripService(
            repository=self.trip_repository,
            page_size=settings.history_page_size,
            note_max_length=settings.note_max_length,
        )

        # ---------------- Слой 1. Представление ---------------- #
        self.bot = telebot.TeleBot(settings.bot_token, parse_mode=None, threaded=True)
        self.gateway = TelegramGateway(self.bot)
        self.storage = StateStorage()
        self.screens: ScreenContainer = build_screens(
            gateway=self.gateway,
            storage=self.storage,
            holiday_service=self.holiday_service,
            city_service=self.city_service,
            trip_service=self.trip_service,
        )
        self.handlers = BotHandlers(
            bot=self.bot,
            gateway=self.gateway,
            storage=self.storage,
            screens=self.screens,
            city_service=self.city_service,
        )

        logger.info("Приложение TravelHunter собрано")

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Регистрирует обработчики и запускает long polling."""
        self.handlers.register()
        logger.info("Telegram-бот TravelHunter запущен. Для остановки нажмите Ctrl+C")
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
    except TravelHunterError as exc:
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
