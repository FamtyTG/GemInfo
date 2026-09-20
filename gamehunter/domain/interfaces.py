"""Интерфейсы (порты) доменного слоя.

Бизнес-логика описывает, ЧТО ей нужно от внешнего мира, но не знает, КАК это
реализовано. Конкретные реализации живут в слое infrastructure:

    GamesProvider    -> RawgClient          (RAWG Video Games Database API);
    IpLocationProvider -> IpLocationClient  (ipapi.co — геолокация по IP);
    ProfileRepository  -> SqlProfileRepository (PostgreSQL через SQLAlchemy);
    LibraryRepository  -> SqlLibraryRepository (PostgreSQL через SQLAlchemy).

Такой подход (Dependency Inversion) позволяет:
    * подменять реализацию (например, использовать SQLite вместо PostgreSQL);
    * тестировать сервисы на подставных объектах без сети и базы данных.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Set

from gamehunter.domain.entities import (
    FavoriteGame,
    Franchise,
    Game,
    GameDetails,
    GamePage,
    GameQuery,
    Genre,
    LibraryPage,
    Platform,
    PlayedGame,
    Region,
    UserProfile,
)


class GamesProvider(ABC):
    """Источник данных о играх, жанрах, платформах и франшизах."""

    @abstractmethod
    def fetch_genres(self) -> List[Genre]:
        """Возвращает список жанров каталога."""

    @abstractmethod
    def fetch_platforms(self) -> List[Platform]:
        """Возвращает список платформ (PC, PlayStation, Xbox, Nintendo, Android, iOS)."""

    @abstractmethod
    def search_games(self, query: GameQuery) -> GamePage:
        """Ищет игры по фильтрам и возвращает страницу результатов."""

    @abstractmethod
    def fetch_game_details(self, game_id: int) -> Optional[GameDetails]:
        """Возвращает подробную информацию об игре или None, если игры нет."""

    @abstractmethod
    def search_franchises(self, name: str, limit: int) -> List[Franchise]:
        """Ищет франшизы (IP) по названию."""

    @abstractmethod
    def fetch_franchise_games(self, franchise_id: int, limit: int) -> List[Game]:
        """Возвращает игры выбранной франшизы."""


class IpLocationProvider(ABC):
    """Источник данных о регионе пользователя по IP-адресу."""

    @abstractmethod
    def locate(self, ip: str) -> Optional[Region]:
        """Определяет регион по IP. Возвращает None, если адрес не найден."""


class ProfileRepository(ABC):
    """Хранилище анкет пользователей (таблица user_profiles)."""

    @abstractmethod
    def get_or_create(self, tg_user_id: int) -> UserProfile:
        """Возвращает анкету пользователя, создавая её при первом обращении."""

    @abstractmethod
    def save(self, profile: UserProfile) -> UserProfile:
        """Сохраняет изменения анкеты."""


class LibraryRepository(ABC):
    """Хранилище библиотеки: сыгранные игры и избранное."""

    # ------------------------- «Во что я играл» ------------------------- #
    @abstractmethod
    def add_played(self, tg_user_id: int, game: Game, played_at: Optional[datetime] = None) -> PlayedGame:
        """Добавляет игру в список сыгранных."""

    @abstractmethod
    def find_played_by_id(self, record_id: int, tg_user_id: int) -> Optional[PlayedGame]:
        """Возвращает запись из списка сыгранных."""

    @abstractmethod
    def update_review(self, record_id: int, tg_user_id: int, review: str) -> Optional[PlayedGame]:
        """Сохраняет отзыв к сыгранной игре."""

    @abstractmethod
    def delete_played(self, record_id: int, tg_user_id: int) -> bool:
        """Удаляет запись из списка сыгранных."""

    @abstractmethod
    def played_game_ids(self, tg_user_id: int) -> Set[int]:
        """Идентификаторы игр, в которые пользователь уже играл (для исключения)."""

    @abstractmethod
    def has_played(self, tg_user_id: int, game_id: int) -> bool:
        """Проверяет, есть ли игра в списке сыгранных."""

    @abstractmethod
    def page_played(self, tg_user_id: int, page: int, page_size: int) -> LibraryPage[PlayedGame]:
        """Возвращает страницу списка сыгранных игр."""

    # ------------------------------ Избранное ------------------------------ #
    @abstractmethod
    def add_favorite(self, tg_user_id: int, game: Game) -> FavoriteGame:
        """Добавляет игру в избранное."""

    @abstractmethod
    def remove_favorite(self, tg_user_id: int, game_id: int) -> bool:
        """Убирает игру из избранного."""

    @abstractmethod
    def is_favorite(self, tg_user_id: int, game_id: int) -> bool:
        """Проверяет, находится ли игра в избранном."""

    @abstractmethod
    def page_favorites(self, tg_user_id: int, page: int, page_size: int) -> LibraryPage[FavoriteGame]:
        """Возвращает страницу списка избранных игр."""
