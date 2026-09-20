"""Клиент RAWG Video Games Database API — каталог видеоигр.

Документация: https://rawg.io/apidocs

Используемые endpoint'ы:
    GET /api/genres                     — жанры (интересы пользователя);
    GET /api/platforms/lists/parents    — платформы (PC, PlayStation, Xbox…);
    GET /api/games                      — поиск игр по фильтрам;
    GET /api/games/{id}                 — карточка игры (описание, возрастной рейтинг);
    GET /api/franchises?search=…        — поиск франшиз (IP);
    GET /api/franchises/{id}            — игры выбранной франшизы.

API-ключ передаётся параметром ``key`` и берётся из переменной окружения
RAWG_API_KEY — в коде и в Git его нет.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from gamehunter.domain.age_ratings import min_age_from_label
from gamehunter.domain.entities import (
    Franchise,
    Game,
    GameDetails,
    GamePage,
    GameQuery,
    Genre,
    Platform,
)
from gamehunter.domain.exceptions import (
    FranchiseSearchUnavailableError,
    GamesUnavailableError,
    GenresUnavailableError,
)
from gamehunter.domain.interfaces import GamesProvider
from gamehunter.infrastructure.api.http_client import JsonHttpClient

logger = logging.getLogger(__name__)

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

#: Родительские платформы RAWG — используются, если API ответил неожиданно.
PARENT_PLATFORM_FALLBACK: Tuple[Tuple[int, str, str], ...] = (
    (1, "PC", "pc"),
    (2, "PlayStation", "playstation"),
    (3, "Xbox", "xbox"),
    (7, "Nintendo", "nintendo"),
    (8, "Android", "android"),
    (4, "iOS", "ios"),
    (5, "macOS", "apple-macintosh"),
    (6, "Linux", "linux"),
)


def strip_html(text: Any) -> str:
    """Убирает HTML-разметку из описания игры."""
    if not isinstance(text, str) or not text.strip():
        return ""
    plain = HTML_TAG_PATTERN.sub(" ", text)
    plain = html.unescape(plain)
    return " ".join(plain.split()).strip()


def parse_release_date(raw: Any) -> Optional[date]:
    """Разбирает дату выхода игры из ответа API."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None

    value = raw.strip().split("T")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _names(items: Any, limit: int = 5) -> Tuple[str, ...]:
    """Достаёт названия из списка объектов API (разработчики, магазины, теги…)."""
    if not isinstance(items, list):
        return ()
    names: List[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            # у платформ и магазинов объект вложен в ключ с тем же именем
            nested = item.get("platform") or item.get("store") or item
            name = nested.get("name") if isinstance(nested, dict) else None
            if name:
                names.append(str(name))
        elif isinstance(item, str) and item:
            names.append(item)
    return tuple(dict.fromkeys(names))


class RawgClient(GamesProvider):
    """Доступ к каталогу видеоигр RAWG."""

    BASE_URL = "https://api.rawg.io/api"
    SERVICE_NAME = "rawg"

    def __init__(
        self,
        http_client: JsonHttpClient,
        api_key: str = "",
        page_size: int = 5,
        language: str = "ru",
    ) -> None:
        self._http_client = http_client
        self._api_key = api_key
        self._page_size = page_size
        self._language = language

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    # ------------------------------------------------------------------ #
    # Жанры (интересы пользователя)
    # ------------------------------------------------------------------ #
    def fetch_genres(self) -> List[Genre]:
        payload = self._get("/genres", {}, error=GenresUnavailableError)
        results = self._results(payload)

        genres: List[Genre] = []
        for item in results:
            name = str(item.get("name") or "").strip()
            slug = str(item.get("slug") or "").strip()
            if not name or not slug:
                continue
            genres.append(
                Genre(
                    id=_to_int(item.get("id")),
                    name=name,
                    slug=slug,
                    games_count=_to_int(item.get("games_count")),
                    image_url=item.get("image_background") or None,
                )
            )

        logger.info("Получено жанров из каталога: %s", len(genres))
        return genres

    # ------------------------------------------------------------------ #
    # Платформы (категории устройств)
    # ------------------------------------------------------------------ #
    def fetch_platforms(self) -> List[Platform]:
        payload = self._get(
            "/platforms/lists/parents", {}, error=GenresUnavailableError, allow_404=True
        )

        items: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            for key in ("result", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, dict)]
                    break

        if not items:
            logger.warning(
                "Каталог не вернул список платформ — используется запасной перечень"
            )
            return [
                Platform(id=pid, name=name, slug=slug, is_parent=True)
                for pid, name, slug in PARENT_PLATFORM_FALLBACK
            ]

        platforms: List[Platform] = []
        for item in items:
            pid = _to_int(item.get("id"))
            name = str(item.get("name") or "").strip()
            slug = str(item.get("slug") or "").strip()
            if not pid or not name:
                continue
            platforms.append(
                Platform(
                    id=pid,
                    name=name,
                    slug=slug,
                    games_count=_to_int(item.get("games_count")),
                    is_parent=True,
                )
            )

        return platforms or [
            Platform(id=pid, name=name, slug=slug, is_parent=True)
            for pid, name, slug in PARENT_PLATFORM_FALLBACK
        ]

    # ------------------------------------------------------------------ #
    # Поиск игр
    # ------------------------------------------------------------------ #
    def search_games(self, query: GameQuery) -> GamePage:
        params: Dict[str, Any] = {
            "page": max(1, query.page),
            "page_size": max(1, query.page_size),
        }
        if query.ordering:
            params["ordering"] = query.ordering
        if query.genres:
            params["genres"] = ",".join(query.genres)
        if query.parent_platforms:
            params["parent_platforms"] = ",".join(str(pid) for pid in query.parent_platforms)
        if query.search.strip():
            params["search"] = query.search.strip()
        if query.exclude_game_ids:
            params["exclude_games"] = ",".join(str(gid) for gid in query.exclude_game_ids)
        if query.exclude_additions:
            # скрываем DLC и дополнения — оставляем самостоятельные игры
            params["exclude_additions"] = "true"

        payload = self._get("/games", params, error=GamesUnavailableError)
        games = [
            game for game in (self._parse_game(item) for item in self._results(payload)) if game
        ]

        total_count = _to_int(
            payload.get("count") if isinstance(payload, dict) else None, len(games)
        )
        has_next = bool(payload.get("next")) if isinstance(payload, dict) else False
        has_previous = bool(payload.get("previous")) if isinstance(payload, dict) else False

        logger.info(
            "Поиск игр: найдено %s (страница %s, всего в каталоге %s)",
            len(games),
            query.page,
            total_count,
        )
        return GamePage(
            games=games,
            page=max(1, query.page),
            page_size=max(1, query.page_size),
            total_count=total_count,
            has_next=has_next,
            has_previous=has_previous,
        )

    # ------------------------------------------------------------------ #
    # Карточка игры
    # ------------------------------------------------------------------ #
    def fetch_game_details(self, game_id: int) -> Optional[GameDetails]:
        payload = self._get(
            f"/games/{game_id}", {}, error=GamesUnavailableError, allow_404=True
        )
        if not isinstance(payload, dict) or not payload:
            return None

        # RAWG сообщает об отсутствии игры телом {"detail": "Not found."}
        if "detail" in payload and "name" not in payload:
            logger.info("Игра #%s не найдена в каталоге: %s", game_id, payload.get("detail"))
            return None

        game = self._parse_game(payload, default_id=game_id)
        if game is None:
            return None

        summary = strip_html(payload.get("description_raw") or payload.get("description"))
        min_age, age_label = self._parse_age_rating(payload)

        return GameDetails(
            game=game,
            summary=summary,
            min_age=min_age,
            age_rating_label=age_label,
            developers=_names(payload.get("developers")),
            publishers=_names(payload.get("publishers")),
            stores=_names(payload.get("stores"), limit=6),
            tags=_names(payload.get("tags"), limit=6),
        )

    # ------------------------------------------------------------------ #
    # Франшизы (IP)
    # ------------------------------------------------------------------ #
    def search_franchises(self, name: str, limit: int) -> List[Franchise]:
        params = {
            "search": name.strip(),
            "page_size": max(1, min(limit, 20)),
            "ordering": "-games_count",
        }
        payload = self._get("/franchises", params, error=FranchiseSearchUnavailableError)

        franchises: List[Franchise] = []
        for item in self._results(payload):
            franchise_id = _to_int(item.get("id"))
            franchise_name = str(item.get("name") or "").strip()
            if not franchise_id or not franchise_name:
                continue
            franchises.append(
                Franchise(
                    id=franchise_id,
                    name=franchise_name,
                    slug=str(item.get("slug") or ""),
                    games_count=_to_int(item.get("games_count")),
                )
            )

        logger.info("Найдено франшиз по запросу «%s»: %s", name, len(franchises))
        return franchises

    def fetch_franchise_games(self, franchise_id: int, limit: int) -> List[Game]:
        payload = self._get(
            f"/franchises/{franchise_id}",
            {"page_size": max(1, limit)},
            error=FranchiseSearchUnavailableError,
            allow_404=True,
        )
        if not isinstance(payload, dict):
            return []

        items = payload.get("games")
        if isinstance(items, list) and items:
            games = [game for game in (self._parse_game(item) for item in items) if game]
            if games:
                return games[:limit]

        # Запасной вариант: ищем игры по названию франшизы
        franchise_name = str(payload.get("name") or "").strip()
        if not franchise_name:
            return []

        logger.info(
            "Франшиза #%s не вернула список игр — ищем по названию «%s»",
            franchise_id,
            franchise_name,
        )
        page = self.search_games(
            GameQuery(search=franchise_name, page=1, page_size=limit, ordering="-rating")
        )
        return page.games[:limit]

    # ------------------------------------------------------------------ #
    # Разбор ответа API
    # ------------------------------------------------------------------ #
    def _parse_game(self, item: Any, default_id: int = 0) -> Optional[Game]:
        """Преобразует элемент ответа API в сущность Game."""
        if not isinstance(item, dict):
            return None

        name = str(item.get("name") or "").strip()
        game_id = _to_int(item.get("id"), default_id)
        if not name or not game_id:
            return None

        genres = _names(item.get("genres"), limit=4)
        platforms = _names(item.get("parent_platforms"), limit=5) or _names(
            item.get("platforms"), limit=5
        )

        return Game(
            id=game_id,
            slug=str(item.get("slug") or ""),
            name=name,
            released=parse_release_date(item.get("released")),
            rating=_to_float(item.get("rating")),
            genres=genres,
            platforms=platforms,
            image_url=item.get("background_image") or item.get("image_background") or None,
            metacritic=_to_int(item.get("metacritic")) or None,
            playtime_hours=_to_int(item.get("playtime")) or None,
            announced=bool(item.get("tba")),
        )

    @staticmethod
    def _parse_age_rating(payload: Dict[str, Any]) -> Tuple[Optional[int], str]:
        """Определяет возрастной рейтинг игры (ESRB или PEGI)."""
        label = ""

        esrb = payload.get("esrb_rating")
        if isinstance(esrb, dict):
            label = str(esrb.get("name") or esrb.get("slug") or "")
        elif isinstance(esrb, str):
            label = esrb

        if not label:
            ratings = payload.get("age_ratings")
            if isinstance(ratings, list) and ratings:
                first = ratings[0]
                if isinstance(first, dict):
                    label = str(first.get("title") or first.get("rating") or "")
                else:
                    label = str(first)

        if not label:
            for key in ("pegi", "pegi_rating"):
                value = payload.get(key)
                if isinstance(value, dict):
                    label = str(value.get("name") or value.get("rating") or "")
                elif isinstance(value, (str, int)):
                    label = str(value)
                if label:
                    break

        return min_age_from_label(label), label.strip()

    @staticmethod
    def _results(payload: Any) -> List[Dict[str, Any]]:
        """Достаёт список элементов из ответа API."""
        if not isinstance(payload, dict):
            return []
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        return [item for item in results if isinstance(item, dict)]

    # ------------------------------------------------------------------ #
    # Выполнение запросов
    # ------------------------------------------------------------------ #
    def _ensure_configured(self, error) -> None:
        """Проверяет, что API-ключ задан в настройках окружения."""
        if not self._api_key:
            logger.error("RAWG_API_KEY не задан — каталог игр недоступен")
            raise error(self.SERVICE_NAME, "api key is not configured")

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {"key": self._api_key}
        params.update(extra)
        if self._language:
            params.setdefault("language", self._language)
        return params

    def _get(
        self,
        path: str,
        params: Dict[str, Any],
        error,
        allow_404: bool = False,
    ) -> Any:
        """Выполняет запрос к RAWG и преобразует ошибки в доменные."""
        self._ensure_configured(error)
        url = f"{self.BASE_URL}{path}"
        try:
            return self._http_client.get_json(
                url,
                params=self._params(params),
                service=self.SERVICE_NAME,
                allow_404=allow_404,
            )
        except error:
            raise
        except Exception as exc:  # noqa: BLE001 - преобразуем в доменную ошибку
            logger.error("Ошибка запроса к RAWG %s: %s", path, exc)
            raise error(self.SERVICE_NAME, str(exc)) from exc
