"""Подставные объекты (fakes) для тестов.

Они позволяют проверять логику проекта без сети, без Telegram и без PostgreSQL:
    FakeHolidaysProvider / FakeCityProvider / FakeCityInfoProvider — внешние API;
    FakeSession / FakeResponse                                      — HTTP-слой;
    FakeGateway                                                     — отправка сообщений;
    make_message / make_callback                                    — события Telegram.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from travelhunter.domain.entities import City, CityInfo, Holiday, NearbyCity, Trip, TripPage


# ---------------------------------------------------------------------- #
# Внешние API
# ---------------------------------------------------------------------- #
class FakeHolidaysProvider:
    """Замена NinjasHolidaysClient."""

    def __init__(
        self,
        holidays: Optional[List[Holiday]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.holidays: List[Holiday] = holidays or []
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    def fetch_holidays(self, country: str, year: int) -> List[Holiday]:
        self.calls.append({"country": country, "year": year})
        if self.error is not None:
            raise self.error
        return list(self.holidays)


class FakeCityProvider:
    """Замена GeoNamesClient."""

    def __init__(
        self,
        city: Optional[City] = None,
        nearby: Optional[List[NearbyCity]] = None,
        search_error: Optional[Exception] = None,
        nearby_error: Optional[Exception] = None,
    ) -> None:
        self.city = city
        self.nearby: List[NearbyCity] = nearby or []
        self.search_error = search_error
        self.nearby_error = nearby_error
        self.search_calls: List[str] = []
        self.nearby_calls: List[Dict[str, Any]] = []

    def search_city(self, name: str) -> Optional[City]:
        self.search_calls.append(name)
        if self.search_error is not None:
            raise self.search_error
        return self.city

    def find_nearby_cities(
        self, latitude: float, longitude: float, radius_km: int, limit: int
    ) -> List[NearbyCity]:
        self.nearby_calls.append(
            {
                "lat": latitude,
                "lng": longitude,
                "radius": radius_km,
                "limit": limit,
            }
        )
        if self.nearby_error is not None:
            raise self.nearby_error
        return list(self.nearby[:limit])


class FakeCityInfoProvider:
    """Замена WikipediaClient."""

    def __init__(
        self, info: Optional[CityInfo] = None, error: Optional[Exception] = None
    ) -> None:
        self.info = info
        self.error = error
        self.calls: List[str] = []

    def fetch_city_info(self, city_name: str) -> Optional[CityInfo]:
        self.calls.append(city_name)
        if self.error is not None:
            raise self.error
        return self.info


class InMemoryTripRepository:
    """Замена SqlTripRepository: хранит поездки в списке (для юнит-тестов)."""

    def __init__(self) -> None:
        self.trips: List[Trip] = []
        self._next_id = 1

    def add(self, tg_user_id: int, city_name: str, arrival_date=None) -> Trip:
        trip = Trip(
            id=self._next_id,
            tg_user_id=tg_user_id,
            name=city_name,
            arrival_date=arrival_date or datetime.now(),
            note=None,
        )
        self._next_id += 1
        self.trips.append(trip)
        return trip

    def _user_trips(self, tg_user_id: int) -> List[Trip]:
        return sorted(
            (trip for trip in self.trips if trip.tg_user_id == tg_user_id),
            key=lambda trip: (trip.arrival_date, trip.id),
            reverse=True,
        )

    def find_by_user(self, tg_user_id: int, limit: int, offset: int) -> List[Trip]:
        return self._user_trips(tg_user_id)[offset : offset + limit]

    def count_by_user(self, tg_user_id: int) -> int:
        return len(self._user_trips(tg_user_id))

    def find_by_id(self, trip_id: int, tg_user_id: int) -> Optional[Trip]:
        for trip in self.trips:
            if trip.id == trip_id and trip.tg_user_id == tg_user_id:
                return trip
        return None

    def update_note(self, trip_id: int, tg_user_id: int, note: str) -> Optional[Trip]:
        for index, trip in enumerate(self.trips):
            if trip.id == trip_id and trip.tg_user_id == tg_user_id:
                updated = trip.with_note(note)
                self.trips[index] = updated
                return updated
        return None

    def page_by_user(self, tg_user_id: int, page: int, page_size: int) -> TripPage:
        total = self.count_by_user(tg_user_id)
        total_pages = max(1, math.ceil(total / max(1, page_size)))
        page = min(max(1, page), total_pages)
        offset = (page - 1) * page_size
        return TripPage(
            trips=self.find_by_user(tg_user_id, page_size, offset),
            page=page,
            total_pages=total_pages,
        )


# ---------------------------------------------------------------------- #
# HTTP-слой
# ---------------------------------------------------------------------- #
class FakeResponse:
    """Имитация ответа requests.Response."""

    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        text: str = "",
        invalid_json: bool = False,
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.text = text if text else str(json_data)
        self._invalid_json = invalid_json

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        if self._invalid_json:
            raise ValueError("Expecting value: no JSON object could be decoded")
        return self._json_data


class FakeSession:
    """Имитация requests.Session: отдаёт заранее подготовленные ответы."""

    def __init__(self, responses: Optional[List[FakeResponse]] = None) -> None:
        self.responses: List[FakeResponse] = list(responses or [])
        self.requests: List[Dict[str, Any]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(json_data=[], status_code=200)


# ---------------------------------------------------------------------- #
# Telegram
# ---------------------------------------------------------------------- #
@dataclass
class SentMessage:
    """Сообщение, «отправленное» подставным шлюзом."""

    chat_id: int
    text: str
    markup: Any = None
    photo: Optional[str] = None


@dataclass
class FakeGateway:
    """Замена TelegramGateway: записывает сообщения вместо отправки в Telegram."""

    photo_fails: bool = False
    events: List[SentMessage] = field(default_factory=list)
    messages: List[SentMessage] = field(default_factory=list)
    photos: List[SentMessage] = field(default_factory=list)
    answered_callbacks: int = 0

    def send_text(self, chat_id: int, text: str, reply_markup=None) -> bool:
        message = SentMessage(chat_id=chat_id, text=text, markup=reply_markup)
        self.messages.append(message)
        self.events.append(message)
        return True

    def send_photo(
        self, chat_id: int, image_url: str, caption: str, reply_markup=None
    ) -> bool:
        if self.photo_fails:
            return False
        message = SentMessage(
            chat_id=chat_id, text=caption, markup=reply_markup, photo=image_url
        )
        self.photos.append(message)
        self.events.append(message)
        return True

    def answer_callback(self, call, text: str = "") -> None:
        self.answered_callbacks += 1

    # ---------------------- вспомогательные ---------------------- #
    @property
    def all_texts(self) -> List[str]:
        return [event.text for event in self.events]

    @property
    def last_event(self) -> Optional[SentMessage]:
        return self.events[-1] if self.events else None

    @property
    def last_text(self) -> str:
        return self.events[-1].text if self.events else ""

    @property
    def last_markup(self):
        return self.events[-1].markup if self.events else None


def make_message(
    text: str = "",
    chat_id: int = 100,
    user_id: int = 200,
    content_type: str = "text",
):
    """Создаёт объект, похожий на telebot.types.Message."""
    return SimpleNamespace(
        id=1,
        text=text,
        content_type=content_type,
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
    )


def make_callback(data: str = "", chat_id: int = 100, user_id: int = 200):
    """Создаёт объект, похожий на telebot.types.CallbackQuery."""
    return SimpleNamespace(
        id="callback-1",
        data=data,
        chat_instance="instance",
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
    )


# ---------------------------------------------------------------------- #
# Фабрики доменных объектов
# ---------------------------------------------------------------------- #
def make_holiday(name: str, holiday_date: date, type_: str = "National holiday") -> Holiday:
    return Holiday(
        name=name,
        date=holiday_date,
        day=holiday_date.strftime("%a"),
        type=type_,
        country="Russia",
        iso="RU",
        year=holiday_date.year,
    )


def make_city(
    name: str, latitude: float = 55.75, longitude: float = 37.62, **kwargs
) -> City:
    return City(name=name, latitude=latitude, longitude=longitude, **kwargs)


def make_nearby_city(
    name: str, distance_km: float, latitude: float = 0.0, longitude: float = 0.0, **kwargs
) -> NearbyCity:
    return NearbyCity(
        name=name,
        latitude=latitude,
        longitude=longitude,
        distance_km=distance_km,
        **kwargs,
    )
