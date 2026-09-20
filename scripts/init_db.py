"""Инициализация базы данных: создание таблицы visited_cities.

Запуск из корня проекта:
    python -m scripts.init_db           # создать таблицы
    python -m scripts.init_db --demo    # создать таблицы и добавить демо-данные

Скрипт использует те же настройки, что и бот (файл .env / переменные окружения),
поэтому таблицы создаются именно в той базе, с которой работает TravelHunter.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Позволяет запускать скрипт напрямую: python scripts/init_db.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from travelhunter.app import configure_logging  # noqa: E402
from travelhunter.config import Settings  # noqa: E402
from travelhunter.domain.exceptions import TravelHunterError  # noqa: E402
from travelhunter.infrastructure.db import Database, SqlTripRepository  # noqa: E402

logger = logging.getLogger("scripts.init_db")

DEMO_USER_ID = 111111111
DEMO_CITIES = ["Тула", "Калуга", "Владимир", "Рязань", "Тверь", "Ярославль"]


def create_tables(database: Database) -> None:
    """Создаёт таблицы базы данных."""
    database.create_all()
    logger.info("Таблицы базы данных созданы (или уже существовали)")


def add_demo_data(database: Database, user_id: int = DEMO_USER_ID) -> int:
    """Добавляет несколько демонстрационных поездок (для проверки истории)."""
    repository = SqlTripRepository(database)
    now = datetime.now()
    created = 0
    for index, city_name in enumerate(DEMO_CITIES):
        repository.add(
            tg_user_id=user_id,
            city_name=city_name,
            arrival_date=now - timedelta(days=index * 7),
        )
        created += 1
    logger.info("Добавлено демонстрационных поездок: %s (пользователь %s)", created, user_id)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Инициализация базы данных TravelHunter")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="добавить демонстрационные поездки в базу данных",
    )
    parser.add_argument(
        "--env-file", default=".env", help="путь к файлу настроек (по умолчанию .env)"
    )
    args = parser.parse_args(argv)

    configure_logging("INFO")

    try:
        settings = Settings.from_env(args.env_file)
    except TravelHunterError as exc:
        print(f"[ОШИБКА НАСТРОЙКИ] {exc}", file=sys.stderr)
        return 1

    database = Database(settings.database_url)
    try:
        create_tables(database)
        if args.demo:
            add_demo_data(database)
    except TravelHunterError as exc:
        print(f"[ОШИБКА БАЗЫ ДАННЫХ] {exc}", file=sys.stderr)
        return 1
    finally:
        database.dispose()

    print("Готово. База данных:", database.safe_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
