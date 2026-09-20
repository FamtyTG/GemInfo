"""Клиент сервиса геолокации по IP-адресу.

По умолчанию используется ipapi.co (бесплатный, ключ не требуется):
    GET https://ipapi.co/{ip}/json/

Поддерживается также формат ответа ipwho.is — на случай, если адрес сервиса
будет изменён в настройках (``IP_LOCATION_BASE_URL``).

Зачем это боту: Telegram Bot API не передаёт IP-адрес пользователя, поэтому
пользователь сам присылает свой публичный IP (или город), а бот определяет
страну, город, часовой пояс и валюту — и сохраняет их в анкете. Регион
используется при показе карточки игры (магазины и валюта региона).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gamehunter.domain.entities import Region
from gamehunter.domain.exceptions import RegionUnavailableError
from gamehunter.domain.interfaces import IpLocationProvider
from gamehunter.infrastructure.api.http_client import JsonHttpClient

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class IpLocationClient(IpLocationProvider):
    """Определение региона пользователя по IP-адресу."""

    SERVICE_NAME = "ipapi"
    DEFAULT_BASE_URL = "https://ipapi.co"

    def __init__(
        self, http_client: JsonHttpClient, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        self._http_client = http_client
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def locate(self, ip: str) -> Optional[Region]:
        """Возвращает регион по IP-адресу или None, если адрес не распознан.

        :raises RegionUnavailableError: сервис недоступен или вернул ошибку.
        """
        address = _text(ip)
        if not address:
            return None

        url = f"{self._base_url}/{address}/json/"
        try:
            payload = self._http_client.get_json(
                url, service=self.SERVICE_NAME, allow_404=True
            )
        except RegionUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - преобразуем в доменную ошибку
            logger.error("Ошибка определения региона по IP %s: %s", address, exc)
            raise RegionUnavailableError(self.SERVICE_NAME, str(exc)) from exc

        if payload is None or not isinstance(payload, dict):
            logger.info("Сервис геолокации не вернул данных для IP %s", address)
            return None

        # Ответы об ошибке: ipapi.co — {"error": true, "reason": ...},
        # ipwho.is — {"success": false, "message": ...}
        if payload.get("error") or payload.get("success") is False:
            reason = _text(payload.get("reason") or payload.get("message") or "error")
            logger.warning("Сервис геолокации вернул ошибку для IP %s: %s", address, reason)
            raise RegionUnavailableError(self.SERVICE_NAME, reason)

        region = self._parse_region(address, payload)
        if region is None:
            logger.info("Не удалось определить регион для IP %s", address)
        else:
            logger.info(
                "Регион по IP %s: %s (%s), часовой пояс %s",
                address,
                region.title,
                region.country_code,
                region.timezone,
            )
        return region

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_region(ip: str, payload: Dict[str, Any]) -> Optional[Region]:
        """Разбирает ответ сервиса геолокации (ipapi.co и ipwho.is)."""
        country = _text(payload.get("country_name"))
        country_code = _text(payload.get("country_code")).upper()
        country_field = _text(payload.get("country"))

        if country_field:
            if len(country_field) == 2:
                country_code = country_code or country_field.upper()
            else:
                country = country or country_field

        timezone = payload.get("timezone")
        if isinstance(timezone, dict):
            timezone = _text(timezone.get("id") or timezone.get("timezone"))
        else:
            timezone = _text(timezone)

        currency = payload.get("currency")
        if isinstance(currency, dict):
            currency = _text(currency.get("code") or currency.get("name"))
        else:
            currency = _text(currency)

        region = Region(
            ip=ip,
            country=country,
            country_code=country_code,
            city=_text(payload.get("city")),
            region_name=_text(payload.get("region") or payload.get("region_name")),
            timezone=timezone,
            currency=currency,
            latitude=_number(payload.get("latitude")),
            longitude=_number(payload.get("longitude")),
        )
        return region if region.is_known else None
