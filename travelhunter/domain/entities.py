"""Сущности (модели) доменного слоя.

Это обычные объекты Python (dataclass), которые описывают понятия предметной
области: праздник, город, поездка. Они ничего не знают ни про Telegram,
ни про SQLAlchemy — так бизнес-логика остаётся независимой от способов
хранения и отображения данных.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
# date используется в аннотации поля Holiday.date (имя поля совпадает с именем типа,
# поэтому статические анализаторы могут считать импорт неиспользуемым — это не так)
from datetime import date, datetime  # noqa: F401
from typing import List, Optional

# Формат даты, который видит пользователь (например, 10.08.2026)
DATE_FORMAT = "%d.%m.%Y"


@dataclass(frozen=True)
class Holiday:
    """Праздник, полученный из внешнего сервиса (Ninjas Holidays API)."""

    name: str
    date: date
    day: str = ""
    type: str = ""
    country: str = ""
    iso: str = ""
    year: Optional[int] = None

    @property
    def formatted_date(self) -> str:
        """Дата праздника в формате ДД.ММ.ГГГГ."""
        return self.date.strftime(DATE_FORMAT)


@dataclass(frozen=True)
class City:
    """Город с координатами (результат поиска GeoNames)."""

    name: str
    latitude: float
    longitude: float
    country: str = ""
    region: str = ""
    geoname_id: Optional[int] = None

    @property
    def coordinates(self) -> tuple[float, float]:
        return self.latitude, self.longitude


@dataclass(frozen=True)
class NearbyCity(City):
    """Город, расположенный рядом с текущим городом пользователя."""

    distance_km: float = 0.0

    @property
    def rounded_distance(self) -> int:
        """Расстояние в километрах, округлённое до целого (для показа)."""
        return int(round(self.distance_km))


@dataclass(frozen=True)
class CityInfo:
    """Дополнительная информация о городе из Википедии."""

    title: str
    summary: str
    image_url: Optional[str] = None

    @property
    def has_image(self) -> bool:
        return bool(self.image_url)


@dataclass(frozen=True)
class Trip:
    """Поездка пользователя — запись таблицы visited_cities."""

    id: int
    tg_user_id: int
    name: str
    arrival_date: datetime
    note: Optional[str] = None

    @property
    def formatted_date(self) -> str:
        return self.arrival_date.strftime(DATE_FORMAT)

    @property
    def has_note(self) -> bool:
        return bool(self.note and self.note.strip())

    def with_note(self, note: Optional[str]) -> "Trip":
        """Возвращает копию поездки с новой заметкой."""
        return replace(self, note=note)


@dataclass(frozen=True)
class TripPage:
    """Страница истории поездок (для пагинации по 5 записей)."""

    trips: List[Trip]
    page: int
    total_pages: int

    @property
    def is_empty(self) -> bool:
        return not self.trips

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages
