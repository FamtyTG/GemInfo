"""Клиент Ninjas Holidays API (праздники).

Документация: https://api-ninjas.com/api/holidays
Endpoint:     https://api.api-ninjas.com/v2/holidays  (метод GET)
Параметры:    country=RU, date=ГГГГ-ММ-ДД (год, за который нужны праздники)
Авторизация:  API-ключ в HTTP-заголовке X-Api-Key.

API-ключ берётся из переменной окружения NINJAS_API_KEY и не хранится в коде.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from travelhunter.domain.entities import Holiday
from travelhunter.domain.exceptions import HolidaysUnavailableError
from travelhunter.domain.interfaces import HolidaysProvider
from travelhunter.infrastructure.api.http_client import JsonHttpClient

logger = logging.getLogger(__name__)

# Возможные форматы даты в ответе сервиса (разные версии API отвечают по-разному)
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y")


def parse_holiday_date(raw: Any) -> Optional[date]:
    """Разбирает дату праздника из строки или объекта date/datetime."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None

    value = raw.strip()
    # дата может прийти вместе со временем — оставляем только её часть
    value = value.split("T")[0].split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Не удалось разобрать дату праздника: %r", raw)
    return None


class NinjasHolidaysClient(HolidaysProvider):
    """Получение списка праздников страны из внешнего сервиса."""

    BASE_URL = "https://api.api-ninjas.com/v2/holidays"
    SERVICE_NAME = "ninjas-holidays"

    def __init__(self, http_client: JsonHttpClient, api_key: str = "") -> None:
        self._http_client = http_client
        self._api_key = api_key

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def fetch_holidays(self, country: str, year: int) -> List[Holiday]:
        """Возвращает праздники страны за указанный год.

        :raises HolidaysUnavailableError: ключ не задан, сервис недоступен
            или вернул некорректный ответ.
        """
        if not self._api_key:
            logger.error("NINJAS_API_KEY не задан — праздники недоступны")
            raise HolidaysUnavailableError(self.SERVICE_NAME, "api key is not configured")

        params: Dict[str, Any] = {"country": country, "date": f"{year}-01-01"}
        headers = {"X-Api-Key": self._api_key}

        try:
            payload = self._http_client.get_json(
                self.BASE_URL, params=params, headers=headers, service=self.SERVICE_NAME
            )
        except HolidaysUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - преобразуем в доменную ошибку
            raise HolidaysUnavailableError(self.SERVICE_NAME, str(exc)) from exc

        # Сервис может вернуть объект с описанием ошибки вместо массива
        if isinstance(payload, dict):
            message = payload.get("error") or payload.get("message") or "unexpected response"
            logger.error("Ninjas API вернул ошибку: %s", message)
            raise HolidaysUnavailableError(self.SERVICE_NAME, str(message))
        if not isinstance(payload, list):
            raise HolidaysUnavailableError(self.SERVICE_NAME, "unexpected response type")

        holidays: List[Holiday] = []
        for item in payload:
            holiday = self._parse_item(item, year)
            if holiday is not None:
                holidays.append(holiday)

        logger.info("Получено праздников от Ninjas API: %s (год %s)", len(holidays), year)
        return holidays

    def _parse_item(self, item: Any, default_year: int) -> Optional[Holiday]:
        """Преобразует один элемент ответа API в сущность Holiday."""
        if not isinstance(item, dict):
            return None

        parsed_date = parse_holiday_date(item.get("date"))
        if parsed_date is None:
            return None  # без даты праздник бесполезен — пропускаем

        name = str(item.get("name") or "").strip()
        if not name:
            return None

        year_value = item.get("year")
        try:
            year = int(year_value) if year_value is not None else parsed_date.year
        except (TypeError, ValueError):
            year = default_year

        return Holiday(
            name=name,
            date=parsed_date,
            day=str(item.get("day") or ""),
            type=str(item.get("type") or ""),
            country=str(item.get("country") or ""),
            iso=str(item.get("iso") or ""),
            year=year,
        )
