"""Общие фикстуры pytest для тестов проекта GameHunter."""

from __future__ import annotations

from typing import Iterator

import pytest
from telebot import TeleBot

from gamehunter.domain.services import GameService, LibraryService, ProfileService
from gamehunter.infrastructure.db import (
    Database,
    SqlLibraryRepository,
    SqlProfileRepository,
)
from gamehunter.presentation.handlers import BotHandlers
from gamehunter.presentation.screens import ScreenContainer, build_screens
from gamehunter.presentation.state import StateStorage
from tests.fakes import (
    FakeGateway,
    FakeIpProvider,
    FakeGamesProvider,
    default_provider,
    make_region,
)

#: Идентификаторы чата и пользователя, используемые в тестах
CHAT_ID = 100
USER_ID = 200


# ---------------------------------------------------------------------- #
# База данных
# ---------------------------------------------------------------------- #
@pytest.fixture()
def database(tmp_path) -> Iterator[Database]:
    """Локальная тестовая база данных SQLite (структура как в PostgreSQL)."""
    db_file = tmp_path / "gamehunter_test.db"
    db = Database(f"sqlite:///{db_file}")
    db.create_all()
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture()
def profile_repository(database: Database) -> SqlProfileRepository:
    """Репозиторий анкет поверх тестовой базы данных."""
    return SqlProfileRepository(database)


@pytest.fixture()
def library_repository(database: Database) -> SqlLibraryRepository:
    """Репозиторий библиотеки (сыгранные игры и избранное)."""
    return SqlLibraryRepository(database)


# ---------------------------------------------------------------------- #
# Внешние сервисы
# ---------------------------------------------------------------------- #
@pytest.fixture()
def games_provider() -> FakeGamesProvider:
    """Каталог игр с реалистичным набором данных (без сети)."""
    return default_provider()


@pytest.fixture()
def ip_provider() -> FakeIpProvider:
    """Сервис геолокации, который всегда определяет один и тот же регион."""
    return FakeIpProvider(region=make_region())


# ---------------------------------------------------------------------- #
# Сервисы бизнес-логики
# ---------------------------------------------------------------------- #
@pytest.fixture()
def game_service(games_provider: FakeGamesProvider) -> GameService:
    """Сервис каталога игр: 3 игры на странице, 6 жанров на выбор."""
    return GameService(
        provider=games_provider,
        max_games=3,
        max_genres=6,
        max_franchises=5,
        details_fetch_limit=4,
        cache_ttl_seconds=600,
    )


@pytest.fixture()
def profile_service(
    profile_repository: SqlProfileRepository, ip_provider: FakeIpProvider
) -> ProfileService:
    """Сервис анкеты пользователя."""
    return ProfileService(repository=profile_repository, ip_provider=ip_provider)


@pytest.fixture()
def library_service(library_repository: SqlLibraryRepository) -> LibraryService:
    """Сервис библиотеки: 3 записи на странице, отзыв до 1000 символов."""
    return LibraryService(repository=library_repository, page_size=3, note_max_length=1000)


# ---------------------------------------------------------------------- #
# Слой представления
# ---------------------------------------------------------------------- #
@pytest.fixture()
def gateway() -> FakeGateway:
    """Подставной шлюз Telegram: записывает отправленные сообщения."""
    return FakeGateway()


@pytest.fixture()
def storage() -> StateStorage:
    """Хранилище состояний пользователей."""
    return StateStorage()


@pytest.fixture()
def screens(
    gateway: FakeGateway,
    storage: StateStorage,
    game_service: GameService,
    profile_service: ProfileService,
    library_service: LibraryService,
) -> ScreenContainer:
    """Все экраны бота, собранные на подставных объектах."""
    return build_screens(
        gateway=gateway,
        storage=storage,
        game_service=game_service,
        profile_service=profile_service,
        library_service=library_service,
    )


@pytest.fixture()
def bot() -> TeleBot:
    """Объект бота (без сети: обработчики вызываются напрямую из тестов)."""
    return TeleBot("123456789:TEST", parse_mode=None, threaded=True)


@pytest.fixture()
def handlers(
    bot: TeleBot,
    gateway: FakeGateway,
    storage: StateStorage,
    screens: ScreenContainer,
) -> BotHandlers:
    """Обработчики событий Telegram."""
    return BotHandlers(bot=bot, gateway=gateway, storage=storage, screens=screens)
