"""Подставные объекты (fakes) для тестов.

Они позволяют проверять логику проекта без сети, без Telegram и без PostgreSQL:
    FakeGamesProvider      — каталог игр RAWG;
    FakeIpProvider         — сервис геолокации по IP;
    InMemoryProfileRepository / InMemoryLibraryRepository — база данных;
    FakeSession / FakeResponse                            — HTTP-слой;
    FakeGateway                                           — отправка сообщений;
    make_message / make_callback                          — события Telegram.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from gamehunter.domain.entities import (
    FavoriteGame,
    Franchise,
    Game,
    GameDetails,
    GamePage,
    GameQuery,
    Genre,
    LibraryPage,
    PlayedGame,
    Platform,
    Region,
    UserProfile,
)
from gamehunter.domain.interfaces import (
    GamesProvider,
    IpLocationProvider,
    LibraryRepository,
    ProfileRepository,
)


# ---------------------------------------------------------------------- #
# Внешние API
# ---------------------------------------------------------------------- #
class FakeGamesProvider(GamesProvider):
    """Замена RawgClient: отдаёт подготовленные данные и запоминает запросы."""

    def __init__(
        self,
        genres: Optional[Sequence[Genre]] = None,
        platforms: Optional[Sequence[Platform]] = None,
        games: Optional[Sequence[Game]] = None,
        details: Optional[Dict[int, Optional[GameDetails]]] = None,
        franchises: Optional[Sequence[Franchise]] = None,
        franchise_games: Optional[Dict[int, Sequence[Game]]] = None,
        errors: Optional[Dict[str, Exception]] = None,
        genre_slugs: Optional[Dict[int, Tuple[str, ...]]] = None,
        total_count: Optional[int] = None,
    ) -> None:
        self.genres: List[Genre] = list(genres or [])
        self.platforms: List[Platform] = list(platforms or [])
        self.games: List[Game] = list(games or [])
        self.details: Dict[int, Optional[GameDetails]] = dict(details or {})
        self.franchises: List[Franchise] = list(franchises or [])
        self.franchise_games: Dict[int, List[Game]] = {
            key: list(value) for key, value in (franchise_games or {}).items()
        }
        #: ошибки по имени операции: "genres", "platforms", "search", "details",
        #: "franchises", "franchise_games"
        self.errors: Dict[str, Exception] = dict(errors or {})
        #: slug'ы жанров по идентификатору игры (для фильтрации в тестах)
        self.genre_slugs: Dict[int, Tuple[str, ...]] = dict(genre_slugs or {})
        self.total_count = total_count

        self.genre_calls = 0
        self.platform_calls = 0
        self.search_calls: List[GameQuery] = []
        self.details_calls: List[int] = []
        self.franchise_calls: List[Dict[str, Any]] = []
        self.franchise_games_calls: List[Dict[str, Any]] = []

    # ------------------------------ справочники ------------------------------ #
    def fetch_genres(self) -> List[Genre]:
        self.genre_calls += 1
        if "genres" in self.errors:
            raise self.errors["genres"]
        return list(self.genres)

    def fetch_platforms(self) -> List[Platform]:
        self.platform_calls += 1
        if "platforms" in self.errors:
            raise self.errors["platforms"]
        return list(self.platforms)

    # --------------------------------- поиск --------------------------------- #
    def search_games(self, query: GameQuery) -> GamePage:
        self.search_calls.append(query)
        if "search" in self.errors:
            raise self.errors["search"]

        games = [game for game in self.games if game.id not in set(query.exclude_game_ids)]
        if query.genres and self.genre_slugs:
            wanted = set(query.genres)
            games = [
                game
                for game in games
                if wanted.intersection(self.genre_slugs.get(game.id, ()))
            ]

        page_size = query.page_size or len(games) or 1
        start = (max(1, query.page) - 1) * page_size
        chunk = games[start : start + page_size]
        total = self.total_count if self.total_count is not None else len(games)

        return GamePage(
            games=chunk,
            page=max(1, query.page),
            page_size=page_size,
            total_count=total,
            has_next=start + page_size < total,
            has_previous=max(1, query.page) > 1,
        )

    def fetch_game_details(self, game_id: int) -> Optional[GameDetails]:
        self.details_calls.append(game_id)
        if "details" in self.errors:
            raise self.errors["details"]
        if game_id in self.details:
            return self.details[game_id]
        for game in self.games:
            if game.id == game_id:
                return GameDetails(game=game)
        return None

    # -------------------------------- франшизы -------------------------------- #
    def search_franchises(self, name: str, limit: int) -> List[Franchise]:
        self.franchise_calls.append({"name": name, "limit": limit})
        if "franchises" in self.errors:
            raise self.errors["franchises"]
        wanted = name.strip().lower()
        found = [item for item in self.franchises if wanted in item.name.lower()]
        return found[:limit]

    def fetch_franchise_games(self, franchise_id: int, limit: int) -> List[Game]:
        self.franchise_games_calls.append({"id": franchise_id, "limit": limit})
        if "franchise_games" in self.errors:
            raise self.errors["franchise_games"]
        return list(self.franchise_games.get(franchise_id, []))[:limit]


class FakeIpProvider(IpLocationProvider):
    """Замена IpLocationClient."""

    def __init__(
        self,
        region: Optional[Region] = None,
        error: Optional[Exception] = None,
        regions: Optional[Dict[str, Region]] = None,
    ) -> None:
        self.region = region
        self.error = error
        self.regions: Dict[str, Region] = dict(regions or {})
        self.calls: List[str] = []

    def locate(self, ip: str) -> Optional[Region]:
        self.calls.append(ip)
        if self.error is not None:
            raise self.error
        if ip in self.regions:
            return self.regions[ip]
        return self.region


# ---------------------------------------------------------------------- #
# База данных в памяти
# ---------------------------------------------------------------------- #
class InMemoryProfileRepository(ProfileRepository):
    """Замена SqlProfileRepository: анкеты в словаре."""

    def __init__(self) -> None:
        self.profiles: Dict[int, UserProfile] = {}
        self.save_calls = 0

    def get_or_create(self, tg_user_id: int) -> UserProfile:
        profile = self.profiles.get(tg_user_id)
        if profile is None:
            profile = UserProfile(tg_user_id=tg_user_id)
            self.profiles[tg_user_id] = profile
        return profile

    def save(self, profile: UserProfile) -> UserProfile:
        self.save_calls += 1
        saved = UserProfile(
            tg_user_id=profile.tg_user_id,
            age=profile.age,
            genre_slugs=profile.genre_slugs,
            genre_names=profile.genre_names,
            platform_ids=profile.platform_ids,
            platform_names=profile.platform_names,
            region=profile.region,
            updated_at=profile.updated_at or datetime.now(),
        )
        self.profiles[saved.tg_user_id] = saved
        return saved


class InMemoryLibraryRepository(LibraryRepository):
    """Замена SqlLibraryRepository: списки сыгранных игр и избранного."""

    def __init__(self) -> None:
        self.played: List[PlayedGame] = []
        self.favorites: List[FavoriteGame] = []
        self._next_id = 1

    # ------------------------- «Во что я играл» ------------------------- #
    def add_played(
        self, tg_user_id: int, game: Game, played_at: Optional[datetime] = None
    ) -> PlayedGame:
        record = PlayedGame(
            id=self._next_id,
            tg_user_id=tg_user_id,
            game_id=game.id,
            slug=game.slug,
            name=game.name,
            played_at=played_at or datetime.now(),
            image_url=game.image_url,
        )
        self._next_id += 1
        self.played.append(record)
        return record

    def find_played_by_id(self, record_id: int, tg_user_id: int) -> Optional[PlayedGame]:
        for record in self.played:
            if record.id == record_id and record.tg_user_id == tg_user_id:
                return record
        return None

    def update_review(
        self, record_id: int, tg_user_id: int, review: str
    ) -> Optional[PlayedGame]:
        for index, record in enumerate(self.played):
            if record.id == record_id and record.tg_user_id == tg_user_id:
                updated = record.with_review(review)
                self.played[index] = updated
                return updated
        return None

    def delete_played(self, record_id: int, tg_user_id: int) -> bool:
        for index, record in enumerate(self.played):
            if record.id == record_id and record.tg_user_id == tg_user_id:
                del self.played[index]
                return True
        return False

    def played_game_ids(self, tg_user_id: int) -> Set[int]:
        return {record.game_id for record in self.played if record.tg_user_id == tg_user_id}

    def has_played(self, tg_user_id: int, game_id: int) -> bool:
        return game_id in self.played_game_ids(tg_user_id)

    def page_played(
        self, tg_user_id: int, page: int, page_size: int
    ) -> LibraryPage[PlayedGame]:
        records = sorted(
            (item for item in self.played if item.tg_user_id == tg_user_id),
            key=lambda item: (item.played_at, item.id),
            reverse=True,
        )
        return _paginate(records, page, page_size, PlayedGame)

    # ------------------------------ Избранное ------------------------------ #
    def add_favorite(self, tg_user_id: int, game: Game) -> FavoriteGame:
        record = FavoriteGame(
            id=self._next_id,
            tg_user_id=tg_user_id,
            game_id=game.id,
            slug=game.slug,
            name=game.name,
            added_at=datetime.now(),
            image_url=game.image_url,
        )
        self._next_id += 1
        self.favorites.append(record)
        return record

    def remove_favorite(self, tg_user_id: int, game_id: int) -> bool:
        for index, record in enumerate(self.favorites):
            if record.game_id == game_id and record.tg_user_id == tg_user_id:
                del self.favorites[index]
                return True
        return False

    def is_favorite(self, tg_user_id: int, game_id: int) -> bool:
        return any(
            record.game_id == game_id and record.tg_user_id == tg_user_id
            for record in self.favorites
        )

    def page_favorites(
        self, tg_user_id: int, page: int, page_size: int
    ) -> LibraryPage[FavoriteGame]:
        records = sorted(
            (item for item in self.favorites if item.tg_user_id == tg_user_id),
            key=lambda item: (item.added_at, item.id),
            reverse=True,
        )
        return _paginate(records, page, page_size, FavoriteGame)


def _paginate(records: Sequence[Any], page: int, page_size: int, item_type: Any) -> Any:
    """Общая пагинация для списков библиотеки."""
    page_size = max(1, page_size)
    total_pages = max(1, math.ceil(len(records) / page_size))
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    return LibraryPage(
        items=list(records[start : start + page_size]), page=page, total_pages=total_pages
    )


# ---------------------------------------------------------------------- #
# HTTP-слой
# ---------------------------------------------------------------------- #
class FakeResponse:
    """Имитация ответа requests.Response."""

    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        text: str = "",
        invalid_json: bool = False,
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.text = text if text else str(json_data)
        self._invalid_json = invalid_json

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        if self._invalid_json:
            raise ValueError("Expecting value: no JSON object could be decoded")
        return self._json_data


class FakeSession:
    """Имитация requests.Session: отдаёт заранее подготовленные ответы."""

    def __init__(self, responses: Optional[List[FakeResponse]] = None) -> None:
        self.responses: List[FakeResponse] = list(responses or [])
        self.requests: List[Dict[str, Any]] = []
        self.error: Optional[Exception] = None
        self.proxies: Dict[str, str] = {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(json_data={}, status_code=200)


# ---------------------------------------------------------------------- #
# Telegram
# ---------------------------------------------------------------------- #
@dataclass
class SentMessage:
    """Сообщение, «отправленное» подставным шлюзом."""

    chat_id: int
    text: str
    markup: Any = None
    photo: Optional[str] = None
    animation: Optional[Path] = None


@dataclass
class FakeGateway:
    """Замена TelegramGateway: записывает сообщения вместо отправки в Telegram."""

    photo_fails: bool = False
    animation_fails: bool = False
    events: List[SentMessage] = field(default_factory=list)
    messages: List[SentMessage] = field(default_factory=list)
    photos: List[SentMessage] = field(default_factory=list)
    animations: List[SentMessage] = field(default_factory=list)
    answered_callbacks: int = 0

    def send_text(self, chat_id: int, text: str, reply_markup=None) -> bool:
        message = SentMessage(chat_id=chat_id, text=text, markup=reply_markup)
        self.messages.append(message)
        self.events.append(message)
        return True

    def send_photo(
        self, chat_id: int, image_url: str, caption: str, reply_markup=None
    ) -> bool:
        if self.photo_fails:
            return False
        message = SentMessage(
            chat_id=chat_id, text=caption, markup=reply_markup, photo=image_url
        )
        self.photos.append(message)
        self.events.append(message)
        return True

    def send_animation(self, chat_id: int, animation: Path, caption: str = "") -> bool:
        if self.animation_fails:
            return False
        message = SentMessage(
            chat_id=chat_id, text=caption, animation=Path(animation)
        )
        self.animations.append(message)
        self.events.append(message)
        return True

    def answer_callback(self, call, text: str = "") -> None:
        self.answered_callbacks += 1

    # ---------------------- вспомогательные ---------------------- #
    @property
    def all_texts(self) -> List[str]:
        return [event.text for event in self.events]

    @property
    def last_event(self) -> Optional[SentMessage]:
        return self.events[-1] if self.events else None

    @property
    def last_text(self) -> str:
        return self.events[-1].text if self.events else ""

    @property
    def last_markup(self):
        return self.events[-1].markup if self.events else None

    def clear(self) -> None:
        self.events.clear()
        self.messages.clear()
        self.photos.clear()
        self.animations.clear()


def make_message(
    text: str = "", chat_id: int = 100, user_id: int = 200, content_type: str = "text"
):
    """Создаёт объект, похожий на telebot.types.Message."""
    return SimpleNamespace(
        id=1,
        text=text,
        content_type=content_type,
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
    )


def make_callback(data: str = "", chat_id: int = 100, user_id: int = 200):
    """Создаёт объект, похожий на telebot.types.CallbackQuery."""
    return SimpleNamespace(
        id="callback-1",
        data=data,
        chat_instance="instance",
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
    )


def _label_of(button) -> str:
    """Надпись кнопки: у inline-кнопок это атрибут, у reply-кнопок — словарь."""
    if isinstance(button, dict):
        return str(button.get("text", ""))
    return str(getattr(button, "text", button))


def buttons_of(markup) -> List[List[str]]:
    """Надписи кнопок клавиатуры по строкам (inline и reply)."""
    keyboard = getattr(markup, "keyboard", None)
    if not keyboard:
        return []
    return [[_label_of(button) for button in row] for row in keyboard]


def callbacks_of(markup) -> List[str]:
    """Значения callback_data всех кнопок inline-клавиатуры."""
    keyboard = getattr(markup, "keyboard", None)
    if not keyboard:
        return []
    values: List[str] = []
    for row in keyboard:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data:
                values.append(str(data))
    return values


# ---------------------------------------------------------------------- #
# Фабрики доменных объектов
# ---------------------------------------------------------------------- #
def make_genre(name: str = "RPG", slug: str = "role-playing-games-rpg", id: int = 5) -> Genre:
    return Genre(id=id, name=name, slug=slug, games_count=1000)


def make_platform(name: str = "PC", slug: str = "pc", id: int = 1) -> Platform:
    return Platform(id=id, name=name, slug=slug, games_count=5000)


def make_game(
    game_id: int = 32,
    name: str = "The Witcher 3: Wild Hunt",
    slug: str = "the-witcher-3-wild-hunt",
    rating: Optional[float] = 4.6,
    released: Optional[date] = date(2015, 5, 19),
    genres: Tuple[str, ...] = ("RPG", "Action"),
    platforms: Tuple[str, ...] = ("PC", "PlayStation"),
    image_url: Optional[str] = "https://cdn.example/game.jpg",
    metacritic: Optional[int] = 93,
    **kwargs: Any,
) -> Game:
    return Game(
        id=game_id,
        slug=slug,
        name=name,
        released=released,
        rating=rating,
        genres=genres,
        platforms=platforms,
        image_url=image_url,
        metacritic=metacritic,
        **kwargs,
    )


def make_details(
    game: Optional[Game] = None,
    min_age: Optional[int] = 17,
    age_rating_label: str = "ESRB Mature",
    summary: str = "История ведьмака Геральта.",
    developers: Tuple[str, ...] = ("CD Projekt RED",),
    publishers: Tuple[str, ...] = ("CD Projekt",),
    stores: Tuple[str, ...] = ("Steam", "GOG"),
    tags: Tuple[str, ...] = ("open world", "story rich"),
) -> GameDetails:
    return GameDetails(
        game=game or make_game(),
        summary=summary,
        min_age=min_age,
        age_rating_label=age_rating_label,
        developers=developers,
        publishers=publishers,
        stores=stores,
        tags=tags,
    )


def make_franchise(
    franchise_id: int = 1,
    name: str = "Marvel",
    slug: str = "marvel",
    games_count: int = 42,
    games: Tuple[Game, ...] = (),
) -> Franchise:
    return Franchise(
        id=franchise_id, name=name, slug=slug, games_count=games_count, games=games
    )


def make_region(
    ip: str = "8.8.8.8",
    country: str = "United States",
    country_code: str = "US",
    city: str = "Mountain View",
    timezone: str = "America/Los_Angeles",
    currency: str = "USD",
) -> Region:
    return Region(
        ip=ip,
        country=country,
        country_code=country_code,
        city=city,
        region_name="California",
        timezone=timezone,
        currency=currency,
        latitude=37.4,
        longitude=-122.07,
    )


def make_profile(
    tg_user_id: int = 200,
    age: Optional[int] = 27,
    genre_slugs: Tuple[str, ...] = ("action", "role-playing-games-rpg"),
    genre_names: Tuple[str, ...] = ("Action", "RPG"),
    platform_ids: Tuple[int, ...] = (1,),
    platform_names: Tuple[str, ...] = ("PC",),
    region: Optional[Region] = None,
) -> UserProfile:
    return UserProfile(
        tg_user_id=tg_user_id,
        age=age,
        genre_slugs=genre_slugs,
        genre_names=genre_names,
        platform_ids=platform_ids,
        platform_names=platform_names,
        region=region,
    )


def make_played(
    record_id: int = 1,
    tg_user_id: int = 200,
    game_id: int = 32,
    name: str = "The Witcher 3: Wild Hunt",
    review: Optional[str] = None,
    played_at: Optional[datetime] = None,
) -> PlayedGame:
    return PlayedGame(
        id=record_id,
        tg_user_id=tg_user_id,
        game_id=game_id,
        slug="the-witcher-3-wild-hunt",
        name=name,
        played_at=played_at or datetime(2026, 1, 15, 12, 0),
        review=review,
    )


def make_favorite(
    record_id: int = 1,
    tg_user_id: int = 200,
    game_id: int = 41494,
    name: str = "Cyberpunk 2077",
    added_at: Optional[datetime] = None,
) -> FavoriteGame:
    return FavoriteGame(
        id=record_id,
        tg_user_id=tg_user_id,
        game_id=game_id,
        slug="cyberpunk-2077",
        name=name,
        added_at=added_at or datetime(2026, 2, 1, 10, 0),
    )


def default_provider(**kwargs: Any) -> FakeGamesProvider:
    """Провайдер с небольшим реалистичным набором данных."""
    genres = [
        make_genre("Action", "action", 4),
        make_genre("Adventure", "adventure", 3),
        make_genre("RPG", "role-playing-games-rpg", 5),
        make_genre("Shooter", "shooter", 10),
        make_genre("Strategy", "strategy", 7),
        make_genre("Racing", "racing", 1),
    ]
    platforms = [
        make_platform("PC", "pc", 1),
        make_platform("PlayStation", "playstation", 2),
        make_platform("Xbox", "xbox", 3),
        make_platform("Nintendo", "nintendo", 7),
    ]
    games = [
        make_game(32, "The Witcher 3: Wild Hunt", rating=4.6),
        make_game(58175, "God of War", slug="god-of-war-2", rating=4.4, genres=("Action",)),
        make_game(3498, "Grand Theft Auto V", slug="grand-theft-auto-v", rating=4.5),
        make_game(41494, "Cyberpunk 2077", rating=4.1),
        make_game(28, "Red Dead Redemption 2", slug="red-dead-redemption-2", rating=4.6),
        make_game(4200, "Portal 2", rating=4.7),
        make_game(13537, "Half-Life 2", slug="half-life-2", rating=4.6),
    ]
    details = {
        32: make_details(games[0], min_age=17, age_rating_label="ESRB Mature"),
        58175: make_details(games[1], min_age=17, age_rating_label="ESRB Mature"),
        3498: make_details(games[2], min_age=17, age_rating_label="ESRB Mature"),
        41494: make_details(games[3], min_age=17, age_rating_label="ESRB Mature"),
        28: make_details(games[4], min_age=17, age_rating_label="ESRB Mature"),
        4200: make_details(games[5], min_age=10, age_rating_label="ESRB Everyone 10+"),
        13537: make_details(games[6], min_age=17, age_rating_label="ESRB Mature"),
    }
    franchises = [
        make_franchise(101, "Marvel", "marvel", 42),
        make_franchise(102, "Marvel Ultimate Alliance", "marvel-ultimate", 5),
    ]
    franchise_games = {
        101: [
            make_game(9001, "Marvel's Spider-Man", slug="marvels-spider-man", rating=4.5),
            make_game(9002, "Marvel's Guardians of the Galaxy", slug="gotg", rating=4.2),
        ],
        102: [make_game(9003, "Marvel Ultimate Alliance 3", slug="mua3", rating=3.9)],
    }
    defaults: Dict[str, Any] = {
        "genres": genres,
        "platforms": platforms,
        "games": games,
        "details": details,
        "franchises": franchises,
        "franchise_games": franchise_games,
    }
    defaults.update(kwargs)
    return FakeGamesProvider(**defaults)
