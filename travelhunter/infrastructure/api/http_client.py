"""Базовый HTTP-клиент для обращения к внешним API.

Задача класса — один раз и одинаково обработать все типовые проблемы сети:
таймаут, отсутствие соединения, HTTP-ошибку, некорректный JSON.
Наружу всегда отдаётся доменное исключение ``ExternalServiceError``,
поэтому бот не «падает» при недоступности внешних сервисов.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from travelhunter.domain.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class JsonHttpClient:
    """Тонкая обёртка над requests.Session, возвращающая JSON."""

    def __init__(self, timeout: int = 10, session: Optional[requests.Session] = None) -> None:
        self._timeout = timeout
        self._session = session or requests.Session()

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        service: str = "",
    ) -> Any:
        """Выполняет GET-запрос и возвращает разобранный JSON.

        :raises ExternalServiceError: при любой проблеме с запросом или ответом.
        """
        try:
            response = self._session.get(
                url, params=params, headers=headers, timeout=self._timeout
            )
        except requests.Timeout as exc:
            logger.error("Таймаут запроса к %s: %s", service or url, exc)
            raise ExternalServiceError(service, "timeout") from exc
        except requests.ConnectionError as exc:
            logger.error("Нет соединения с %s: %s", service or url, exc)
            raise ExternalServiceError(service, "connection error") from exc
        except requests.RequestException as exc:
            logger.error("Ошибка запроса к %s: %s", service or url, exc)
            raise ExternalServiceError(service, str(exc)) from exc

        if not response.ok:
            logger.error(
                "Сервис %s вернул HTTP %s: %s",
                service or url,
                response.status_code,
                response.text[:300],
            )
            raise ExternalServiceError(service, f"http {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Сервис %s вернул не-JSON ответ: %s", service or url, response.text[:300])
            raise ExternalServiceError(service, "invalid json") from exc
