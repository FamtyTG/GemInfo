"""Сущности (модели) доменного слоя.

Обычные объекты Python (dataclass), описывающие понятия предметной области:
игра, жанр, платформа, франшиза, регион, анкета пользователя, запись библиотеки.
Они ничего не знают ни про Telegram, ни про SQLAlchemy, ни про RAWG API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime  # noqa: F401 - используется в аннотациях
from typing import Any, Generic, List, Optional, Tuple, TypeVar

# Формат даты, который видит пользователь (например, 06.09.2023)
DATE_FORMAT = "%d.%m.%Y"

T = TypeVar("T")


# ---------------------------------------------------------------------- #
# Каталог игр
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Genre:
    """Жанр игры (интерес пользователя): Action, RPG, Indie, Strategy…"""

    id: int
    name: str
    slug: str
    games_count: int = 0
    image_url: Optional[str] = None


@dataclass(frozen=True)
class Platform:
    """Платформа: PC, PlayStation, Xbox, Nintendo, Android, iOS…"""

    id: int
    name: str
    slug: str
    games_count: int = 0
    is_parent: bool = True  # parent_platform в терминах RAWG


@dataclass(frozen=True)
class Game:
    """Игра из каталога (краткая информация — достаточно для списка)."""

    id: int
    slug: str
    name: str
    released: Optional[date] = None
    rating: Optional[float] = None
    genres: Tuple[str, ...] = ()
    platforms: Tuple[str, ...] = ()
    image_url: Optional[str] = None
    metacritic: Optional[int] = None
    playtime_hours: Optional[int] = None
    announced: bool = False  # дата выхода ещё не объявлена (tba)

    @property
    def formatted_released(self) -> str:
        if self.announced or self.released is None:
            return "дата выхода не объявлена"
        return self.released.strftime(DATE_FORMAT)

    @property
    def release_year(self) -> str:
        if self.released is None:
            return "—"
        return str(self.released.year)

    @property
    def formatted_rating(self) -> str:
        if self.rating is None:
            return "без оценки"
        return f"{self.rating:.1f}"

    @property
    def genres_text(self) -> str:
        return ", ".join(self.genres) if self.genres else "жанр не указан"

    @property
    def platforms_text(self) -> str:
        return ", ".join(self.platforms) if self.platforms else "платформа не указана"

    @property
    def has_image(self) -> bool:
        return bool(self.image_url)


@dataclass(frozen=True)
class GameDetails:
    """Подробная информация об игре (карточка)."""

    game: Game
    summary: str = ""
    min_age: Optional[int] = None
    age_rating_label: str = ""
    developers: Tuple[str, ...] = ()
    publishers: Tuple[str, ...] = ()
    stores: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.game.name

    @property
    def game_id(self) -> int:
        return self.game.id

    @property
    def image_url(self) -> Optional[str]:
        return self.game.image_url

    @property
    def has_image(self) -> bool:
        return self.game.has_image

    @property
    def formatted_age(self) -> str:
        if self.min_age is None:
            return self.age_rating_label or "возрастной рейтинг не указан"
        if self.age_rating_label:
            return f"{self.age_rating_label} ({self.min_age}+)"
        return f"{self.min_age}+"


@dataclass(frozen=True)
class Franchise:
    """Франшиза (IP — интеллектуальная собственность): Marvel, Star Wars, Warcraft…"""

    id: int
    name: str
    slug: str
    games_count: int = 0
    games: Tuple[Game, ...] = ()


@dataclass(frozen=True)
class GameQuery:
    """Параметры поиска игр (фильтры подбора)."""

    genres: Tuple[str, ...] = ()
    parent_platforms: Tuple[int, ...] = ()
    search: str = ""
    ordering: str = "-rating"
    page: int = 1
    page_size: int = 5
    exclude_game_ids: Tuple[int, ...] = ()
    exclude_additions: bool = True

    @property
    def is_empty(self) -> bool:
        """True, если пользователь не задал ни одного фильтра."""
        return not (self.genres or self.parent_platforms or self.search.strip())

    def with_page(self, page: int) -> "GameQuery":
        return replace(self, page=max(1, page))


@dataclass(frozen=True)
class GamePage:
    """Страница результатов поиска игр."""

    games: List[Game]
    page: int
    page_size: int
    total_count: int
    has_next: bool
    has_previous: bool

    @property
    def is_empty(self) -> bool:
        return not self.games

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return max(1, math.ceil(self.total_count / self.page_size))


# ---------------------------------------------------------------------- #
# Регион пользователя (определяется по IP-адресу)
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Region:
    """Результат геолокации по IP-адресу."""

    ip: str
    country: str = ""
    country_code: str = ""
    city: str = ""
    region_name: str = ""
    timezone: str = ""
    currency: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def title(self) -> str:
        """Название региона для показа пользователю."""
        parts = [part for part in (self.city, self.region_name, self.country) if part]
        return ", ".join(parts) if parts else (self.country_code or "не определён")

    @property
    def is_known(self) -> bool:
        return bool(self.country or self.city or self.country_code)


# ---------------------------------------------------------------------- #
# Анкета пользователя
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class UserProfile:
    """Анкета пользователя: возраст, интересы, платформы, регион."""

    tg_user_id: int
    age: Optional[int] = None
    genre_slugs: Tuple[str, ...] = ()
    genre_names: Tuple[str, ...] = ()
    platform_ids: Tuple[int, ...] = ()
    platform_names: Tuple[str, ...] = ()
    region: Optional[Region] = None
    updated_at: Optional[datetime] = None

    # ------------------------- изменения ------------------------- #
    def with_age(self, age: Optional[int]) -> "UserProfile":
        return replace(self, age=age)

    def with_genres(self, genres: Tuple[Genre, ...]) -> "UserProfile":
        return replace(
            self,
            genre_slugs=tuple(genre.slug for genre in genres),
            genre_names=tuple(genre.name for genre in genres),
        )

    def with_platforms(self, platforms: Tuple[Platform, ...]) -> "UserProfile":
        return replace(
            self,
            platform_ids=tuple(platform.id for platform in platforms),
            platform_names=tuple(platform.name for platform in platforms),
        )

    def with_region(self, region: Optional[Region]) -> "UserProfile":
        return replace(self, region=region)

    # ------------------------- представление ------------------------- #
    @property
    def interests_text(self) -> str:
        return ", ".join(self.genre_names) if self.genre_names else "не указаны"

    @property
    def platforms_text(self) -> str:
        return ", ".join(self.platform_names) if self.platform_names else "не указаны"

    @property
    def region_text(self) -> str:
        if self.region is None or not self.region.is_known:
            return "не определён"
        return self.region.title

    @property
    def is_filled(self) -> bool:
        """Заполнена ли анкета хотя бы частично."""
        return bool(self.age or self.genre_slugs or self.platform_ids or self.region)


# ---------------------------------------------------------------------- #
# Библиотека пользователя
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlayedGame:
    """Запись «во что я уже играл» (таблица played_games)."""

    id: int
    tg_user_id: int
    game_id: int
    slug: str
    name: str
    played_at: datetime
    review: Optional[str] = None
    image_url: Optional[str] = None

    @property
    def formatted_date(self) -> str:
        return self.played_at.strftime(DATE_FORMAT)

    @property
    def has_review(self) -> bool:
        return bool(self.review and self.review.strip())

    def with_review(self, review: Optional[str]) -> "PlayedGame":
        return replace(self, review=review)


@dataclass(frozen=True)
class FavoriteGame:
    """Запись избранного (таблица favorite_games)."""

    id: int
    tg_user_id: int
    game_id: int
    slug: str
    name: str
    added_at: datetime
    image_url: Optional[str] = None

    @property
    def formatted_date(self) -> str:
        return self.added_at.strftime(DATE_FORMAT)


@dataclass(frozen=True)
class LibraryPage(Generic[T]):
    """Страница библиотеки (сыгранные игры или избранное)."""

    items: List[T]
    page: int
    total_pages: int

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def game_ids_of(items: List[Any]) -> Tuple[int, ...]:
    """Собирает идентификаторы игр из записей библиотеки."""
    return tuple(item.game_id for item in items)
