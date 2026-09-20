"""Сервис городов.

Бизнес-правила экранов «Города куда съездить»:
    * проверка существования введённого города и получение его координат;
    * поиск ближайших городов в радиусе ``radius_km`` км;
    * исключение из выдачи города, который ввёл пользователь;
    * выбор первых ``max_cities`` городов;
    * получение описания и изображения города из Википедии.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from travelhunter.domain.entities import City, CityInfo, NearbyCity
from travelhunter.domain.exceptions import (
    CityInfoUnavailableError,
    CityNotFoundError,
    CitySearchUnavailableError,
    NearbyCitiesNotFoundError,
    TravelHunterError,
)
from travelhunter.domain.interfaces import CityInfoProvider, CityProvider

logger = logging.getLogger(__name__)

# Максимальная длина краткого описания города (Telegram ограничивает сообщение)
DEFAULT_SUMMARY_MAX_LENGTH = 1000


def normalize_name(name: str) -> str:
    """Приводит название города к виду, пригодному для сравнения."""
    return " ".join((name or "").lower().split())


class CityService:
    """Поиск города, ближайших городов и информации о городе."""

    def __init__(
        self,
        city_provider: CityProvider,
        city_info_provider: CityInfoProvider,
        radius_km: int = 500,
        max_cities: int = 5,
        summary_max_length: int = DEFAULT_SUMMARY_MAX_LENGTH,
    ) -> None:
        self._city_provider = city_provider
        self._city_info_provider = city_info_provider
        self._radius_km = radius_km
        self._max_cities = max_cities
        self._summary_max_length = summary_max_length

    @property
    def radius_km(self) -> int:
        return self._radius_km

    @property
    def max_cities(self) -> int:
        return self._max_cities

    # ------------------------------------------------------------------ #
    # Экран 4. Ввод текущего города
    # ------------------------------------------------------------------ #
    def find_city(self, raw_name: str) -> City:
        """Проверяет существование города и возвращает его координаты.

        :raises CityNotFoundError: город не найден внешним сервисом;
        :raises CitySearchUnavailableError: сервис недоступен.
        """
        name = (raw_name or "").strip()
        if not name:
            raise CityNotFoundError()

        try:
            city = self._city_provider.search_city(name)
        except TravelHunterError as exc:
            logger.error("Ошибка поиска города «%s»: %s", name, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при поиске города «%s»", name)
            raise CitySearchUnavailableError("geonames", str(exc)) from exc

        if city is None:
            raise CityNotFoundError()

        logger.info("Город найден: %s (%s, %s)", city.name, city.latitude, city.longitude)
        return city

    # ------------------------------------------------------------------ #
    # Экран 5. Список ближайших городов
    # ------------------------------------------------------------------ #
    def find_nearby_cities(self, current_city: City) -> List[NearbyCity]:
        """Возвращает ближайшие города (не больше ``max_cities``).

        Из результатов исключается сам текущий город и дубликаты названий.

        :raises NearbyCitiesNotFoundError: рядом нет других городов;
        :raises CitySearchUnavailableError: сервис недоступен.
        """
        latitude, longitude = current_city.coordinates
        try:
            found = self._city_provider.find_nearby_cities(
                latitude=latitude,
                longitude=longitude,
                radius_km=self._radius_km,
                limit=self._max_cities * 4,  # берём с запасом: часть отфильтруется
            )
        except TravelHunterError as exc:
            logger.error("Ошибка поиска ближайших городов: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при поиске ближайших городов")
            raise CitySearchUnavailableError("geonames", str(exc)) from exc

        nearby = self._filter_cities(found, current_city)[: self._max_cities]
        if not nearby:
            raise NearbyCitiesNotFoundError(current_city.name, self._radius_km)
        return nearby

    def _filter_cities(
        self, cities: List[NearbyCity], current_city: City
    ) -> List[NearbyCity]:
        """Убирает текущий город, дубликаты и сортирует по расстоянию."""
        current_name = normalize_name(current_city.name)
        unique: List[NearbyCity] = []
        seen_names = set()

        for city in sorted(cities, key=lambda item: item.distance_km):
            name = normalize_name(city.name)
            if not name or name == current_name:
                continue  # это сам город пользователя
            if name in seen_names:
                continue  # дубликат (например, район того же города)
            seen_names.add(name)
            unique.append(city)

        return unique

    # ------------------------------------------------------------------ #
    # Экран 6. Информация о выбранном городе
    # ------------------------------------------------------------------ #
    def get_city_info(self, city_name: str) -> CityInfo:
        """Возвращает описание и изображение города из Википедии.

        :raises CityInfoUnavailableError: статья не найдена или сервис недоступен.
        """
        try:
            info: Optional[CityInfo] = self._city_info_provider.fetch_city_info(city_name)
        except TravelHunterError as exc:
            logger.error("Ошибка получения информации о городе «%s»: %s", city_name, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при получении информации о городе")
            raise CityInfoUnavailableError("wikipedia", str(exc)) from exc

        if info is None:
            raise CityInfoUnavailableError("wikipedia", "article not found")

        return CityInfo(
            title=info.title or city_name,
            summary=self._truncate(info.summary),
            image_url=info.image_url,
        )

    def _truncate(self, text: str) -> str:
        """Обрезает описание города до допустимой длины."""
        text = (text or "").strip()
        if len(text) <= self._summary_max_length:
            return text
        cut = text[: self._summary_max_length]
        # обрезаем по последнему пробелу, чтобы не рвать слово
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return f"{cut}…"
