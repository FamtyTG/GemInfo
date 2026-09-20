"""Сервис каталога игр.

Бизнес-правила подбора игр:
    * поиск по интересам (жанрам), платформам и названию;
    * учёт возраста пользователя из анкеты (возрастные рейтинги ESRB/PEGI);
    * исключение игр, в которые пользователь уже играл;
    * поиск игр по франшизе (IP);
    * карточка игры: описание, разработчики, магазины, возрастной рейтинг.

Ответы внешнего каталога кэшируются в памяти (жанры, платформы, карточки игр),
чтобы не тратить лимиты API на повторяющиеся запросы.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional, Sequence, Tuple

from gamehunter.domain.age_ratings import AgePolicy
from gamehunter.domain.entities import (
    Franchise,
    Game,
    GameDetails,
    GamePage,
    GameQuery,
    Genre,
    Platform,
    UserProfile,
)
from gamehunter.domain.exceptions import (
    FranchiseNotFoundError,
    FranchiseSearchUnavailableError,
    GameHunterError,
    GameInfoUnavailableError,
    GameNotFoundError,
    GamesUnavailableError,
    GenresUnavailableError,
    NoGamesFoundError,
)
from gamehunter.domain.interfaces import GamesProvider

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_MAX_LENGTH = 1000
#: Сортировка результатов подбора по умолчанию (в терминах RAWG)
DEFAULT_ORDERING = "-rating"


class GameService:
    """Поиск и подбор игр по интересам, возрасту и франшизе."""

    def __init__(
        self,
        provider: GamesProvider,
        age_policy: Optional[AgePolicy] = None,
        max_games: int = 5,
        max_genres: int = 12,
        max_franchises: int = 5,
        details_fetch_limit: int = 8,
        summary_max_length: int = DEFAULT_SUMMARY_MAX_LENGTH,
        cache_ttl_seconds: int = 600,
        ordering: str = DEFAULT_ORDERING,
    ) -> None:
        self._provider = provider
        self._age_policy = age_policy or AgePolicy()
        self._max_games = max_games
        self._max_genres = max_genres
        self._max_franchises = max_franchises
        self._details_fetch_limit = details_fetch_limit
        self._summary_max_length = summary_max_length
        self._cache_ttl = cache_ttl_seconds
        self._ordering = ordering or DEFAULT_ORDERING

        self._lock = threading.RLock()
        self._genres_cache: Optional[Tuple[List[Genre], float]] = None
        self._platforms_cache: Optional[Tuple[List[Platform], float]] = None
        self._details_cache: Dict[int, GameDetails] = {}
        self._details_cache_limit = 200

    # ------------------------------------------------------------------ #
    # Параметры сервиса
    # ------------------------------------------------------------------ #
    @property
    def max_games(self) -> int:
        return self._max_games

    @property
    def max_genres(self) -> int:
        return self._max_genres

    @property
    def age_policy(self) -> AgePolicy:
        return self._age_policy

    @property
    def ordering(self) -> str:
        """Сортировка результатов подбора, принятая в сервисе."""
        return self._ordering

    # ------------------------------------------------------------------ #
    # Жанры и платформы (интересы и категории пользователя)
    # ------------------------------------------------------------------ #
    def get_genres(self) -> List[Genre]:
        """Возвращает популярные жанры каталога (не больше ``max_genres``)."""
        with self._lock:
            if self._genres_cache and not self._is_expired(self._genres_cache[1]):
                return list(self._genres_cache[0])

        try:
            genres = self._provider.fetch_genres()
        except GameHunterError as exc:
            logger.error("Ошибка получения жанров: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при получении жанров")
            raise GenresUnavailableError("rawg", str(exc)) from exc

        ordered = sorted(genres, key=lambda genre: genre.games_count, reverse=True)
        result = ordered[: self._max_genres]
        with self._lock:
            self._genres_cache = (result, time.monotonic())
        logger.info("Получено жанров: %s (показываем %s)", len(genres), len(result))
        return list(result)

    def get_platforms(self) -> List[Platform]:
        """Возвращает список платформ (PC, PlayStation, Xbox, Nintendo, Android, iOS)."""
        with self._lock:
            if self._platforms_cache and not self._is_expired(self._platforms_cache[1]):
                return list(self._platforms_cache[0])

        try:
            platforms = self._provider.fetch_platforms()
        except GameHunterError as exc:
            logger.error("Ошибка получения платформ: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при получении платформ")
            raise GenresUnavailableError("rawg", str(exc)) from exc

        ordered = sorted(platforms, key=lambda item: item.games_count, reverse=True)
        with self._lock:
            self._platforms_cache = (ordered, time.monotonic())
        return list(ordered)

    def find_genre(self, slug: str) -> Optional[Genre]:
        """Ищет жанр по slug в кэше/каталоге."""
        for genre in self.get_genres():
            if genre.slug == slug:
                return genre
        return None

    # ------------------------------------------------------------------ #
    # Подбор игр
    # ------------------------------------------------------------------ #
    def build_query(
        self,
        genres: Sequence[str] = (),
        platforms: Sequence[int] = (),
        search: str = "",
        page: int = 1,
        ordering: str = "",
    ) -> GameQuery:
        """Собирает параметры поиска игр."""
        return GameQuery(
            genres=tuple(genres),
            parent_platforms=tuple(platforms),
            search=search.strip(),
            ordering=ordering or self._ordering,
            page=max(1, page),
            page_size=self._max_games,
        )

    def find_games(
        self,
        query: GameQuery,
        profile: Optional[UserProfile] = None,
        played_game_ids: Sequence[int] = (),
    ) -> GamePage:
        """Ищет игры с учётом анкеты пользователя и уже сыгранных игр.

        :raises NoGamesFoundError: игр по критериям не найдено;
        :raises GamesUnavailableError: каталог недоступен.
        """
        effective = self.merge_with_profile(query, profile, played_game_ids)
        need_age_filter = profile is not None and profile.age is not None

        if need_age_filter:
            # запрашиваем больше кандидатов: часть отсеется по возрасту
            effective = GameQuery(
                genres=effective.genres,
                parent_platforms=effective.parent_platforms,
                search=effective.search,
                ordering=effective.ordering,
                page=effective.page,
                page_size=effective.page_size + self._details_fetch_limit,
                exclude_game_ids=effective.exclude_game_ids,
                exclude_additions=effective.exclude_additions,
            )

        page = self._search(effective)

        if page.is_empty:
            raise NoGamesFoundError()

        if need_age_filter:
            # показываем не больше max_games игр, но проверяем все загруженные
            page = self._filter_by_age(page, profile.age, query.page_size or self._max_games)
            if page.is_empty:
                raise NoGamesFoundError()

        logger.info(
            "Подбор игр: жанры=%s платформы=%s найдено=%s (страница %s)",
            effective.genres or "-",
            effective.parent_platforms or "-",
            len(page.games),
            page.page,
        )
        return page

    def _search(self, query: GameQuery) -> GamePage:
        try:
            return self._provider.search_games(query)
        except GameHunterError as exc:
            logger.error("Ошибка поиска игр: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при поиске игр")
            raise GamesUnavailableError("rawg", str(exc)) from exc

    def merge_with_profile(
        self,
        query: GameQuery,
        profile: Optional[UserProfile],
        played_game_ids: Sequence[int],
    ) -> GameQuery:
        """Дополняет запрос данными анкеты и списком сыгранных игр."""
        genres = tuple(query.genres) or (tuple(profile.genre_slugs) if profile else ())
        platforms = tuple(query.parent_platforms) or (
            tuple(profile.platform_ids) if profile else ()
        )
        excluded = tuple(dict.fromkeys(tuple(query.exclude_game_ids) + tuple(played_game_ids)))

        return GameQuery(
            genres=genres,
            parent_platforms=platforms,
            search=query.search,
            ordering=query.ordering,
            page=query.page,
            page_size=query.page_size or self._max_games,
            exclude_game_ids=excluded,
            exclude_additions=query.exclude_additions,
        )

    def _filter_by_age(
        self, page: GamePage, user_age: int, page_size: int
    ) -> GamePage:
        """Оставляет только игры, подходящие пользователю по возрасту.

        Возрастной рейтинг есть только в карточке игры, поэтому для кандидатов
        догружаются подробности (с кэшированием).
        """
        candidates = page.games[: self._details_fetch_limit + page_size]
        suitable: List[Game] = []
        failures = 0

        for game in candidates:
            details = self.get_game_details(game.id, default_game=game)
            if details is None:
                failures += 1  # карточка недоступна — игру не показываем
                continue
            if self._age_policy.is_suitable(details.min_age, user_age):
                suitable.append(game)
            if len(suitable) >= page_size:
                break

        # если не удалось получить ни одной карточки — каталог недоступен,
        # а не «игр нет»: показываем пользователю соответствующую ошибку
        if candidates and not suitable and failures == len(candidates):
            raise GamesUnavailableError("rawg", "game details are unavailable")

        return GamePage(
            games=suitable,
            page=page.page,
            page_size=page_size,
            total_count=page.total_count,
            has_next=page.has_next and len(suitable) >= page_size,
            has_previous=page.has_previous,
        )

    # ------------------------------------------------------------------ #
    # Карточка игры
    # ------------------------------------------------------------------ #
    def get_game_details(
        self, game_id: int, default_game: Optional[Game] = None
    ) -> Optional[GameDetails]:
        """Возвращает подробную информацию об игре (с кэшированием).

        :param default_game: если карточка недоступна, можно вернуть игру из списка;
        :return: None, если подробности получить не удалось и ``default_game`` задан.
        :raises GameNotFoundError: игры нет в каталоге;
        :raises GameInfoUnavailableError: каталог недоступен.
        """
        with self._lock:
            cached = self._details_cache.get(game_id)
        if cached is not None:
            return cached

        try:
            details = self._provider.fetch_game_details(game_id)
        except GameHunterError as exc:
            logger.error("Ошибка получения информации об игре #%s: %s", game_id, exc)
            if default_game is not None:
                return None
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при получении информации об игре")
            if default_game is not None:
                return None
            raise GameInfoUnavailableError("rawg", str(exc)) from exc

        if details is None:
            if default_game is not None:
                return None
            raise GameNotFoundError()

        details = GameDetails(
            game=details.game,
            summary=self._truncate(details.summary),
            min_age=details.min_age,
            age_rating_label=details.age_rating_label,
            developers=details.developers,
            publishers=details.publishers,
            stores=details.stores,
            tags=details.tags,
        )

        with self._lock:
            if len(self._details_cache) >= self._details_cache_limit:
                self._details_cache.clear()
            self._details_cache[game_id] = details
        return details

    def game_from_library(self, game_id: int, slug: str, name: str) -> Game:
        """Собирает объект игры из данных библиотеки пользователя."""
        return Game(id=game_id, slug=slug, name=name)

    # ------------------------------------------------------------------ #
    # Франшизы (IP)
    # ------------------------------------------------------------------ #
    def search_franchises(self, raw_name: str, limit: Optional[int] = None) -> List[Franchise]:
        """Ищет франшизы (IP) по названию.

        :raises FranchiseNotFoundError: франшиза не найдена;
        :raises FranchiseSearchUnavailableError: каталог недоступен.
        """
        name = (raw_name or "").strip()
        if not name:
            raise FranchiseNotFoundError()

        limit = limit or self._max_franchises
        try:
            franchises = self._provider.search_franchises(name, limit)
        except GameHunterError as exc:
            logger.error("Ошибка поиска франшизы «%s»: %s", name, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при поиске франшизы")
            raise FranchiseSearchUnavailableError("rawg", str(exc)) from exc

        franchises = [item for item in franchises if item.games_count > 0] or list(franchises)
        if not franchises:
            raise FranchiseNotFoundError()

        logger.info("Найдено франшиз по запросу «%s»: %s", name, len(franchises))
        return franchises[:limit]

    def get_franchise_games(self, franchise: Franchise) -> List[Game]:
        """Возвращает игры франшизы (не больше ``max_games``).

        :raises NoGamesFoundError: игр у франшизы нет;
        :raises FranchiseSearchUnavailableError: каталог недоступен.
        """
        if franchise.games:
            return list(franchise.games)[: self._max_games]

        try:
            games = self._provider.fetch_franchise_games(
                franchise.id, self._max_games * 2
            )
        except GameHunterError as exc:
            logger.error("Ошибка получения игр франшизы #%s: %s", franchise.id, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при получении игр франшизы")
            raise FranchiseSearchUnavailableError("rawg", str(exc)) from exc

        if not games:
            raise NoGamesFoundError()

        ordered = sorted(
            games,
            key=lambda game: (game.rating is None, -(game.rating or 0)),
        )
        return ordered[: self._max_games]

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _is_expired(self, timestamp: float) -> bool:
        return (time.monotonic() - timestamp) > self._cache_ttl

    def _truncate(self, text: str) -> str:
        """Обрезает описание игры до допустимой длины."""
        text = (text or "").strip()
        if len(text) <= self._summary_max_length:
            return text
        cut = text[: self._summary_max_length]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return f"{cut}…"

    def clear_cache(self) -> None:
        """Очищает кэш жанров, платформ и карточек игр (используется в тестах)."""
        with self._lock:
            self._genres_cache = None
            self._platforms_cache = None
            self._details_cache.clear()
