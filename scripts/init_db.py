"""Инициализация базы данных GameHunter.

Создаёт таблицы ``user_profiles``, ``played_games`` и ``favorite_games``,
а в режиме ``--demo`` заполняет анкету и библиотеку демонстрационного
пользователя (удобно проверить работу бота и посмотреть данные в Adminer).

Запуск из корня проекта:
    python -m scripts.init_db           # создать таблицы
    python -m scripts.init_db --demo    # создать таблицы и добавить демо-данные

Скрипт использует те же настройки, что и бот (файл .env / переменные окружения),
поэтому таблицы создаются именно в той базе, с которой работает GameHunter.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple

# Позволяет запускать скрипт напрямую: python scripts/init_db.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gamehunter.app import configure_logging  # noqa: E402
from gamehunter.config import Settings  # noqa: E402
from gamehunter.domain.entities import Game, Genre, Platform  # noqa: E402
from gamehunter.domain.exceptions import GameHunterError  # noqa: E402
from gamehunter.domain.interfaces import IpLocationProvider  # noqa: E402
from gamehunter.domain.services import LibraryService, ProfileService  # noqa: E402
from gamehunter.infrastructure.db import (  # noqa: E402
    Database,
    SqlLibraryRepository,
    SqlProfileRepository,
)

logger = logging.getLogger("scripts.init_db")

#: Идентификатор демонстрационного пользователя Telegram
DEMO_USER_ID = 111111111

#: Игры из каталога RAWG (идентификаторы настоящие — их же использует API)
DEMO_PLAYED_GAMES: Tuple[Game, ...] = (
    Game(
        id=32,
        slug="the-witcher-3-wild-hunt",
        name="The Witcher 3: Wild Hunt",
        released=date(2015, 5, 19),
        rating=4.6,
        genres=("RPG", "Action", "Adventure"),
        platforms=("PC", "PlayStation", "Xbox", "Nintendo"),
        metacritic=93,
        playtime_hours=50,
    ),
    Game(
        id=3498,
        slug="grand-theft-auto-v",
        name="Grand Theft Auto V",
        released=date(2013, 9, 17),
        rating=4.5,
        genres=("Action", "Shooter", "Adventure"),
        platforms=("PC", "PlayStation", "Xbox"),
        metacritic=97,
        playtime_hours=30,
    ),
    Game(
        id=58175,
        slug="god-of-war-2",
        name="God of War",
        released=date(2018, 4, 20),
        rating=4.4,
        genres=("Action", "Adventure"),
        platforms=("PC", "PlayStation"),
        metacritic=94,
        playtime_hours=20,
    ),
)

#: Игры, которые попадут в избранное демонстрационного пользователя
DEMO_FAVORITE_GAMES: Tuple[Game, ...] = (
    Game(
        id=41494,
        slug="cyberpunk-2077",
        name="Cyberpunk 2077",
        released=date(2020, 12, 10),
        rating=4.1,
        genres=("RPG", "Action", "Shooter"),
        platforms=("PC", "PlayStation", "Xbox"),
    ),
    Game(
        id=28,
        slug="red-dead-redemption-2",
        name="Red Dead Redemption 2",
        released=date(2018, 10, 26),
        rating=4.6,
        genres=("Action", "Adventure", "Shooter"),
        platforms=("PC", "PlayStation", "Xbox"),
    ),
)

#: Интересы демонстрационного пользователя.
#: Идентификаторы жанров здесь нужны только для хранения в базе:
#: каталог RAWG фильтрует игры по slug'ам жанров.
DEMO_GENRES: Tuple[Genre, ...] = (
    Genre(id=4, name="Action", slug="action"),
    Genre(id=3, name="Adventure", slug="adventure"),
    Genre(id=5, name="RPG", slug="role-playing-games-rpg"),
)

#: Платформы демонстрационного пользователя (идентификаторы RAWG parent_platforms)
DEMO_PLATFORMS: Tuple[Platform, ...] = (
    Platform(id=1, name="PC", slug="pc"),
    Platform(id=2, name="PlayStation", slug="playstation"),
)

DEMO_REVIEWS: Tuple[str, ...] = (
    "Прошёл на 100%: отличный сюжет и боевая система, но концовки дополнений спорные.",
    "Играл в режиме GTA Online — много контента, но гринд денег утомляет.",
    "",
)


def create_tables(database: Database) -> None:
    """Создаёт таблицы базы данных."""
    database.create_all()
    logger.info("Таблицы базы данных созданы (или уже существовали)")


def add_demo_data(database: Database, user_id: int = DEMO_USER_ID) -> int:
    """Заполняет анкету и библиотеку демонстрационного пользователя."""
    profile_service = ProfileService(
        repository=SqlProfileRepository(database), ip_provider=_NoIpProvider()
    )
    library_service = LibraryService(repository=SqlLibraryRepository(database))

    # --- анкета: возраст, интересы, платформы ---
    profile_service.set_age(user_id, "27")
    profile_service.set_genres(user_id, DEMO_GENRES)
    profile_service.set_platforms(user_id, DEMO_PLATFORMS)

    # --- «Во что я играл» + отзывы ---
    # Скрипт можно запускать повторно: уже добавленные игры пропускаются.
    now = datetime.now()
    records: List[int] = []
    for index, game in enumerate(DEMO_PLAYED_GAMES):
        if library_service.is_played(user_id, game.id):
            logger.info("Игра #%s уже есть в демо-библиотеке — пропускаем", game.id)
            continue
        record = library_service.add_played(
            user_id, game, played_at=now - timedelta(days=index * 30)
        )
        records.append(record.id)

    for record_id, review in zip(records, DEMO_REVIEWS):
        if review:
            library_service.add_review(user_id, record_id, review)

    # --- избранное ---
    for game in DEMO_FAVORITE_GAMES:
        if library_service.is_favorite(user_id, game.id):
            logger.info("Игра #%s уже в избранном — пропускаем", game.id)
            continue
        library_service.add_favorite(user_id, game)

    total = len(records) + len(DEMO_FAVORITE_GAMES)
    logger.info(
        "Добавлено демонстрационных записей: %s (пользователь %s)", total, user_id
    )
    return total


class _NoIpProvider(IpLocationProvider):
    """Заглушка сервиса геолокации: демо-данные регион не определяют."""

    def locate(self, ip: str) -> None:  # pragma: no cover - не вызывается в скрипте
        return None


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Инициализация базы данных GameHunter")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="добавить демонстрационные анкету, сыгранные игры и избранное",
    )
    parser.add_argument(
        "--user-id", type=int, default=DEMO_USER_ID, help="идентификатор пользователя Telegram"
    )
    parser.add_argument(
        "--env-file", default=".env", help="путь к файлу настроек (по умолчанию .env)"
    )
    args = parser.parse_args(argv)

    configure_logging("INFO")

    try:
        settings = Settings.from_env(args.env_file)
    except GameHunterError as exc:
        print(f"[ОШИБКА НАСТРОЙКИ] {exc}", file=sys.stderr)
        return 1

    database = Database(settings.database_url)
    try:
        create_tables(database)
        if args.demo:
            add_demo_data(database, args.user_id)
    except GameHunterError as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        return 1
    finally:
        database.dispose()

    print("Готово. База данных:", database.safe_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
