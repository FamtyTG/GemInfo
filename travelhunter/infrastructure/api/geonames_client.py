"""Клиент GeoNames API (поиск городов и ближайших населённых пунктов).

Документация: https://www.geonames.org/export/web-services.html

Экран 4. Поиск города по названию:
    https://secure.geonames.org/searchJSON
Экран 5. Поиск ближайших городов по координатам:
    https://secure.geonames.org/findNearbyPlaceNameJSON

Имя пользователя GeoNames берётся из переменной окружения GEONAMES_USERNAME.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from travelhunter.domain.entities import City, NearbyCity
from travelhunter.domain.exceptions import CitySearchUnavailableError
from travelhunter.domain.interfaces import CityProvider
from travelhunter.infrastructure.api.http_client import JsonHttpClient

logger = logging.getLogger(__name__)


def _to_float(value: Any, default: float = 0.0) -> float:
    """Безопасно преобразует значение API в float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    """Безопасно преобразует значение API в int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class GeoNamesClient(CityProvider):
    """Поиск городов и ближайших населённых пунктов через GeoNames."""

    SEARCH_URL = "https://secure.geonames.org/searchJSON"
    NEARBY_URL = "https://secure.geonames.org/findNearbyPlaceNameJSON"
    SERVICE_NAME = "geonames"

    def __init__(
        self,
        http_client: JsonHttpClient,
        username: str = "",
        country_bias: str = "",
        language: str = "ru",
    ) -> None:
        self._http_client = http_client
        self._username = username
        self._country_bias = country_bias
        self._language = language

    @property
    def is_configured(self) -> bool:
        return bool(self._username)

    # ------------------------------------------------------------------ #
    # Экран 4. Проверка существования города
    # ------------------------------------------------------------------ #
    def search_city(self, name: str) -> Optional[City]:
        """Ищет город по названию и возвращает его координаты.

        Возвращает None, если подходящий населённый пункт не найден.
        """
        self._ensure_configured()

        params: Dict[str, Any] = {
            "q": name,
            "maxRows": 10,
            "featureClass": "P",  # только населённые пункты
            "style": "FULL",
            "username": self._username,
            "type": "JSON",
        }
        if self._language:
            params["lang"] = self._language
        if self._country_bias:
            params["countryBias"] = self._country_bias

        payload = self._request(self.SEARCH_URL, params)
        entries = self._extract_entries(payload)
        if not entries:
            logger.info("Город «%s» не найден в GeoNames", name)
            return None

        # Если сервис вернул несколько вариантов — выбираем самый крупный
        entry = max(entries, key=lambda item: _to_int(item.get("population")))
        return City(
            name=str(entry.get("name") or name),
            latitude=_to_float(entry.get("lat")),
            longitude=_to_float(entry.get("lng")),
            country=str(entry.get("countryName") or ""),
            region=str(entry.get("adminName1") or ""),
            geoname_id=_to_int(entry.get("geonameId")) or None,
        )

    # ------------------------------------------------------------------ #
    # Экран 5. Поиск ближайших городов
    # ------------------------------------------------------------------ #
    def find_nearby_cities(
        self, latitude: float, longitude: float, radius_km: int, limit: int
    ) -> List[NearbyCity]:
        """Возвращает населённые пункты в радиусе ``radius_km`` км от точки."""
        self._ensure_configured()

        params: Dict[str, Any] = {
            "lat": latitude,
            "lng": longitude,
            "radius": radius_km,
            "maxRows": max(limit, 1),
            "style": "FULL",
            "username": self._username,
            "type": "JSON",
        }
        if self._language:
            params["lang"] = self._language

        payload = self._request(self.NEARBY_URL, params)
        entries = self._extract_entries(payload)

        cities: List[NearbyCity] = []
        for entry in entries:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            cities.append(
                NearbyCity(
                    name=name,
                    latitude=_to_float(entry.get("lat")),
                    longitude=_to_float(entry.get("lng")),
                    country=str(entry.get("countryName") or ""),
                    region=str(entry.get("adminName1") or ""),
                    geoname_id=_to_int(entry.get("geonameId")) or None,
                    distance_km=_to_float(entry.get("distance")),
                )
            )

        cities = cities[: max(limit, 1)]
        logger.info(
            "GeoNames вернул %s ближайших населённых пунктов (радиус %s км)",
            len(cities),
            radius_km,
        )
        return cities

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _ensure_configured(self) -> None:
        if not self._username:
            logger.error("GEONAMES_USERNAME не задан — поиск городов недоступен")
            raise CitySearchUnavailableError(self.SERVICE_NAME, "username is not configured")

    def _request(self, url: str, params: Dict[str, Any]) -> Any:
        """Выполняет запрос к GeoNames и проверяет ответ сервиса."""
        try:
            payload = self._http_client.get_json(
                url, params=params, service=self.SERVICE_NAME
            )
        except CitySearchUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - преобразуем в доменную ошибку
            raise CitySearchUnavailableError(self.SERVICE_NAME, str(exc)) from exc

        # GeoNames сообщает об ошибках аккаунта/лимита в теле ответа
        if isinstance(payload, dict) and "status" in payload:
            status = payload.get("status") or {}
            message = str(status.get("message") or "unknown error")
            logger.error("GeoNames вернул ошибку: %s", message)
            raise CitySearchUnavailableError(self.SERVICE_NAME, message)
        return payload

    @staticmethod
    def _extract_entries(payload: Any) -> List[Dict[str, Any]]:
        """Достаёт список населённых пунктов из ответа GeoNames."""
        if not isinstance(payload, dict):
            return []
        entries = payload.get("geonames")
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]
