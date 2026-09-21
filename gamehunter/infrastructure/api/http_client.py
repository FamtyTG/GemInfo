"""Базовый HTTP-клиент для обращения к внешним API.

Задача класса — один раз и одинаково обработать все типовые проблемы сети:
таймаут, отсутствие соединения, HTTP-ошибку, некорректный JSON.
Наружу всегда отдаётся доменное исключение ``ExternalServiceError``,
поэтому бот не «падает» при недоступности внешних сервисов.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import requests

from gamehunter.domain.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class JsonHttpClient:
    """Тонкая обёртка над requests.Session, возвращающая JSON."""

    def __init__(
        self,
        timeout: int = 10,
        session: Optional[requests.Session] = None,
        proxy: str = "",
    ) -> None:
        self._timeout = timeout
        self._session = session or requests.Session()
        self._proxy = (proxy or "").strip()
        if self._proxy:
            # Прокси используется, когда внешние сервисы недоступны напрямую
            self._session.proxies = {"http": self._proxy, "https": self._proxy}
            logger.info("HTTP-запросы идут через прокси %s", self.safe_proxy)

    @property
    def proxy(self) -> str:
        """Адрес прокси (пустая строка — запросы идут напрямую)."""
        return self._proxy

    @property
    def safe_proxy(self) -> str:
        """Адрес прокси для логов: логин и пароль скрыты."""
        return re.sub(r"://[^/@\s]*@", "://***@", self._proxy)

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        service: str = "",
        allow_404: bool = False,
    ) -> Any:
        """Выполняет GET-запрос и возвращает разобранный JSON.

        :param allow_404: если True, ответ 404 возвращается как None вместо ошибки
            (удобно для запросов «есть ли такой объект в каталоге»);
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

        if response.status_code == 404 and allow_404:
            logger.info("Сервис %s не нашёл объект (HTTP 404): %s", service or url, url)
            return None

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
            logger.error(
                "Сервис %s вернул не-JSON ответ: %s", service or url, response.text[:300]
            )
            raise ExternalServiceError(service, "invalid json") from exc
