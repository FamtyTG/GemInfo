"""Клиент MediaWiki Action API (русская Википедия).

Документация: https://www.mediawiki.org/wiki/API:Main_page
Endpoint:     https://ru.wikipedia.org/w/api.php

Для получения данных о городе используется action=query со свойствами:
    extracts  — краткое текстовое описание статьи;
    pageimages  — изображение города (если оно есть).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from travelhunter.domain.entities import CityInfo
from travelhunter.domain.exceptions import CityInfoUnavailableError
from travelhunter.domain.interfaces import CityInfoProvider
from travelhunter.infrastructure.api.http_client import JsonHttpClient

logger = logging.getLogger(__name__)


class WikipediaClient(CityInfoProvider):
    """Получение описания и изображения города из Википедии."""

    SERVICE_NAME = "wikipedia"

    def __init__(
        self,
        http_client: JsonHttpClient,
        language: str = "ru",
        thumbnail_size: int = 800,
    ) -> None:
        self._http_client = http_client
        self._language = language or "ru"
        self._thumbnail_size = thumbnail_size

    @property
    def api_url(self) -> str:
        return f"https://{self._language}.wikipedia.org/w/api.php"

    def fetch_city_info(self, city_name: str) -> Optional[CityInfo]:
        """Возвращает информацию о городе или None, если статья не найдена."""
        params: Dict[str, Any] = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageimages",
            "titles": city_name,
            "redirects": 1,          # учитывать перенаправления (Тула -> Тула (город))
            "exintro": 1,            # только вступление статьи
            "explaintext": 1,        # текст без wiki-разметки
            "pithumbsize": self._thumbnail_size,
            "origin": "*",
        }

        try:
            payload = self._http_client.get_json(
                self.api_url, params=params, service=self.SERVICE_NAME
            )
        except CityInfoUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - преобразуем в доменную ошибку
            raise CityInfoUnavailableError(self.SERVICE_NAME, str(exc)) from exc

        page = self._extract_page(payload)
        if page is None:
            logger.info("Статья о городе «%s» не найдена в Википедии", city_name)
            return None

        summary = str(page.get("extract") or "").strip()
        if not summary:
            logger.info("Статья «%s» найдена, но описание пустое", city_name)
            return None

        return CityInfo(
            title=str(page.get("title") or city_name),
            summary=summary,
            image_url=self._extract_image(page),
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_page(payload: Any) -> Optional[Dict[str, Any]]:
        """Достаёт страницу из ответа MediaWiki API."""
        if not isinstance(payload, dict):
            return None
        pages = (payload.get("query") or {}).get("pages")
        if not isinstance(pages, dict):
            return None

        for page_id, page in pages.items():
            if not isinstance(page, dict):
                continue
            # pageid = -1 означает, что статья не найдена
            if str(page_id).startswith("-") or page.get("missing") == "":
                continue
            return page
        return None

    @staticmethod
    def _extract_image(page: Dict[str, Any]) -> Optional[str]:
        """Достаёт ссылку на изображение города (если оно есть)."""
        thumbnail = page.get("thumbnail")
        if isinstance(thumbnail, dict):
            source = thumbnail.get("source")
            if source:
                return str(source)

        original = page.get("originalimage")
        if isinstance(original, dict):
            source = original.get("source")
            if source:
                return str(source)

        return None
