"""Интерфейсы (порты) доменного слоя.

Бизнес-логика описывает, ЧТО ей нужно от внешнего мира, но не знает, КАК это
реализовано. Конкретные реализации живут в слое infrastructure:

    HolidaysProvider  -> NinjasHolidaysClient   (API Ninjas);
    CityProvider      -> GeoNamesClient         (API GeoNames);
    CityInfoProvider  -> WikipediaClient        (API Википедии);
    TripRepository    -> SqlTripRepository      (PostgreSQL через SQLAlchemy).

Такой подход (Dependency Inversion) позволяет:
    * подменять реализацию (например, использовать SQLite вместо PostgreSQL);
    * тестировать сервисы на подставных объектах без сети и базы данных.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from travelhunter.domain.entities import City, CityInfo, Holiday, NearbyCity, Trip, TripPage


class HolidaysProvider(ABC):
    """Источник данных о праздниках."""

    @abstractmethod
    def fetch_holidays(self, country: str, year: int) -> List[Holiday]:
        """Возвращает список праздников страны за указанный год."""


class CityProvider(ABC):
    """Источник данных о городах и их координатах."""

    @abstractmethod
    def search_city(self, name: str) -> Optional[City]:
        """Ищет город по названию. Если город не найден — возвращает None."""

    @abstractmethod
    def find_nearby_cities(
        self, latitude: float, longitude: float, radius_km: int, limit: int
    ) -> List[NearbyCity]:
        """Возвращает населённые пункты в радиусе ``radius_km`` км от точки."""


class CityInfoProvider(ABC):
    """Источник описания и изображения города."""

    @abstractmethod
    def fetch_city_info(self, city_name: str) -> Optional[CityInfo]:
        """Возвращает информацию о городе или None, если статья не найдена."""


class TripRepository(ABC):
    """Хранилище поездок пользователя (таблица visited_cities)."""

    @abstractmethod
    def add(self, tg_user_id: int, city_name: str, arrival_date: Optional[datetime] = None) -> Trip:
        """Создаёт запись о поездке и возвращает её."""

    @abstractmethod
    def find_by_user(self, tg_user_id: int, limit: int, offset: int) -> List[Trip]:
        """Возвращает поездки пользователя от новых к старым."""

    @abstractmethod
    def count_by_user(self, tg_user_id: int) -> int:
        """Возвращает количество поездок пользователя."""

    @abstractmethod
    def find_by_id(self, trip_id: int, tg_user_id: int) -> Optional[Trip]:
        """Возвращает поездку по идентификатору (только своего пользователя)."""

    @abstractmethod
    def update_note(self, trip_id: int, tg_user_id: int, note: str) -> Optional[Trip]:
        """Сохраняет заметку к поездке и возвращает обновлённую поездку."""

    @abstractmethod
    def page_by_user(self, tg_user_id: int, page: int, page_size: int) -> TripPage:
        """Возвращает страницу истории поездок."""
