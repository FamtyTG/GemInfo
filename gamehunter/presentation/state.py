"""Состояния экранов и пользовательский контекст сессии.

Контекст хранится только в памяти бота (в словаре по chat_id) и нужен, чтобы
знать, на каком экране находится пользователь и какие данные выбрать кнопкой.
Анкета, сыгранные игры и избранное хранятся в базе данных, поэтому после
перезапуска бота данные пользователя не теряются.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import threading
from typing import Dict, Optional, Sequence, Tuple

from gamehunter.domain.entities import Franchise, Game, Genre, Platform

#: Экраны, на которых бот ждёт текстовое сообщение пользователя
TEXT_INPUT_SCREENS = frozenset(
    {
        "franchise_input",
        "age_input",
        "ip_input",
        "review_input",
    }
)


class ContextScreen(str, Enum):
    """Возможные состояния пользователя в диалоге."""

    MAIN_MENU = "main_menu"
    PICKING_GENRES = "picking_genres"      # Экран 3
    GAME_LIST = "game_list"                # Экран 4
    GAME_CARD = "game_card"                # Экран 5
    FRANCHISE_INPUT = "franchise_input"    # Экран 6
    FRANCHISE_LIST = "franchise_list"      # Экран 7
    FRANCHISE_GAMES = "franchise_games"    # Экран 8
    PROFILE = "profile"                    # Экран 9
    AGE_INPUT = "age_input"                # Экран 9а
    PROFILE_GENRES = "profile_genres"      # Экран 9б
    PROFILE_PLATFORMS = "profile_platforms"  # Экран 9в
    IP_INPUT = "ip_input"                  # Экран 9г
    PLAYED_LIST = "played_list"            # Экран 10
    PLAYED_INFO = "played_info"            # Экран 11
    REVIEW_INPUT = "review_input"          # Экран 11а
    FAVORITES_LIST = "favorites_list"      # Экран 12
    AGE_RATING = "age_rating"              # Экран 13

    def is_waiting_for_text(self) -> bool:
        """True, если на этом экране ожидается текстовый ввод."""
        return self.value in TEXT_INPUT_SCREENS


@dataclass(frozen=True)
class UserContext:
    """Неизменяемое состояние одного пользователя."""

    screen: ContextScreen = ContextScreen.MAIN_MENU

    # --- подбор игр по интересам ---
    #: переопределение возраста подборки (Экран 13), None — по анкете
    age_rating: Optional[int] = None
    picked_genres: Tuple[str, ...] = ()
    genre_catalog: Tuple[Genre, ...] = ()

    # --- анкета (черновики выбора) ---
    profile_genres: Tuple[str, ...] = ()
    platform_catalog: Tuple[Platform, ...] = ()
    profile_platforms: Tuple[int, ...] = ()

    # --- текущий список игр (подборка, игры франшизы, избранное) ---
    games: Tuple[Game, ...] = ()
    games_page: int = 1
    games_total_pages: int = 1
    games_has_next: bool = False
    games_has_previous: bool = False
    filters_line: str = ""
    played_excluded: bool = False

    # --- франшизы (IP) ---
    franchises: Tuple[Franchise, ...] = ()
    franchise_id: Optional[int] = None
    franchise_name: str = ""

    # --- карточка игры ---
    current_game_id: Optional[int] = None
    #: экран, из которого открыта карточка (куда ведёт кнопка «Назад»)
    list_source: ContextScreen = ContextScreen.GAME_LIST

    # --- «Во что я играл» ---
    records: Tuple[int, ...] = ()
    library_page: int = 1
    library_total_pages: int = 1
    selected_record_id: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "games_page", max(1, int(self.games_page)))
        object.__setattr__(self, "games_total_pages", max(1, int(self.games_total_pages)))
        object.__setattr__(self, "library_page", max(1, int(self.library_page)))
        object.__setattr__(self, "library_total_pages", max(1, int(self.library_total_pages)))

    # ------------------------------------------------------------------ #
    # Переходы между экранами
    # ------------------------------------------------------------------ #
    def at_main_menu(self) -> "UserContext":
        """Экран 2: главное меню — очищаем всё временное состояние."""
        return replace(
            self,
            screen=ContextScreen.MAIN_MENU,
            genre_catalog=(),
            platform_catalog=(),
            games=(),
            franchises=(),
            franchise_id=None,
            current_game_id=None,
            records=(),
            selected_record_id=None,
            filters_line="",
        )

    def at_age_rating(self) -> "UserContext":
        """Переход на Экран 13 «Возрастной рейтинг»."""
        return replace(self, screen=ContextScreen.AGE_RATING)

    def with_age_rating(self, age: Optional[int]) -> "UserContext":
        """Выбор (или сброс, age=None) возрастного рейтинга подборки."""
        return replace(self, age_rating=age)

    def at_picking(
        self,
        genre_catalog: Sequence[Genre] = (),
        picked_genres: Optional[Sequence[str]] = None,
    ) -> "UserContext":
        """Экран 3: выбор интересов для подбора игр."""
        return replace(
            self,
            screen=ContextScreen.PICKING_GENRES,
            genre_catalog=tuple(genre_catalog),
            picked_genres=tuple(picked_genres) if picked_genres is not None else self.picked_genres,
        )

    def toggle_picked_genre(self, slug: str) -> "UserContext":
        """Отмечает или снимает жанр при подборе игр."""
        picked = list(self.picked_genres)
        if slug in picked:
            picked.remove(slug)
        else:
            picked.append(slug)
        return replace(self, screen=ContextScreen.PICKING_GENRES, picked_genres=tuple(picked))

    def with_picked_genres(self, slugs: Sequence[str]) -> "UserContext":
        """Устанавливает выбранные жанры подбора."""
        return replace(self, screen=ContextScreen.PICKING_GENRES, picked_genres=tuple(slugs))

    def at_game_list(
        self,
        games: Sequence[Game],
        page: int = 1,
        total_pages: int = 1,
        filters_line: str = "",
        has_next: bool = False,
        has_previous: bool = False,
        played_excluded: bool = False,
    ) -> "UserContext":
        """Экран 4: результаты подбора."""
        return replace(
            self,
            screen=ContextScreen.GAME_LIST,
            games=tuple(games),
            games_page=max(1, page),
            games_total_pages=max(1, total_pages),
            games_has_next=has_next,
            games_has_previous=has_previous,
            filters_line=filters_line,
            played_excluded=played_excluded,
            current_game_id=None,
        )

    def back_to_list(self, screen: ContextScreen) -> "UserContext":
        """Возвращает пользователя к сохранённому списку игр (кнопка «Назад» в карточке)."""
        return replace(self, screen=screen, current_game_id=None)

    def game_by_id(self, game_id: int) -> Optional[Game]:
        """Игра из текущего списка по идентификатору каталога."""
        for game in self.games:
            if game.id == game_id:
                return game
        return None

    def at_game_card(
        self, game_id: int, list_source: Optional[ContextScreen] = None
    ) -> "UserContext":
        """Экран 5: карточка игры.

        ``list_source`` запоминает экран, из которого открыта карточка, чтобы
        кнопка «Назад» вернула пользователя именно туда. Если карточка уже
        открыта (повторное действие с игрой), источник списка сохраняется.
        """
        source = list_source if list_source is not None else self.screen
        if source == ContextScreen.GAME_CARD:
            source = self.list_source
        return replace(
            self,
            screen=ContextScreen.GAME_CARD,
            current_game_id=game_id,
            list_source=source,
        )

    def at_franchise_input(self) -> "UserContext":
        """Экран 6: ожидание названия франшизы."""
        return replace(
            self,
            screen=ContextScreen.FRANCHISE_INPUT,
            franchises=(),
            franchise_id=None,
            games=(),
        )

    def with_franchises(self, franchises: Sequence[Franchise]) -> "UserContext":
        """Экран 7: список найденных франшиз."""
        return replace(
            self, screen=ContextScreen.FRANCHISE_LIST, franchises=tuple(franchises)
        )

    def franchise_at(self, index: int) -> Optional[Franchise]:
        """Франшиза из списка по номеру кнопки (нумерация с 1)."""
        if 1 <= index <= len(self.franchises):
            return self.franchises[index - 1]
        return None

    def at_franchise_games(
        self, franchise_id: int, games: Sequence[Game], name: str = ""
    ) -> "UserContext":
        """Экран 8: игры выбранной франшизы (без пагинации)."""
        return replace(
            self,
            screen=ContextScreen.FRANCHISE_GAMES,
            franchise_id=franchise_id,
            franchise_name=name,
            games=tuple(games),
            games_page=1,
            games_total_pages=1,
            games_has_next=False,
            games_has_previous=False,
            current_game_id=None,
        )

    def at_profile(self) -> "UserContext":
        """Экран 9: анкета пользователя."""
        return replace(self, screen=ContextScreen.PROFILE)

    def at_age_input(self) -> "UserContext":
        """Экран 9а: ожидание возраста."""
        return replace(self, screen=ContextScreen.AGE_INPUT)

    def at_profile_genres(
        self, genre_catalog: Sequence[Genre], selected: Sequence[str]
    ) -> "UserContext":
        """Экран 9б: выбор интересов для анкеты."""
        return replace(
            self,
            screen=ContextScreen.PROFILE_GENRES,
            genre_catalog=tuple(genre_catalog),
            profile_genres=tuple(selected),
        )

    def toggle_profile_genre(self, slug: str) -> "UserContext":
        """Отмечает или снимает жанр в черновике анкеты."""
        selected = list(self.profile_genres)
        if slug in selected:
            selected.remove(slug)
        else:
            selected.append(slug)
        return replace(self, screen=ContextScreen.PROFILE_GENRES, profile_genres=tuple(selected))

    def at_profile_platforms(
        self, platform_catalog: Sequence[Platform], selected: Sequence[int]
    ) -> "UserContext":
        """Экран 9в: выбор платформ для анкеты."""
        return replace(
            self,
            screen=ContextScreen.PROFILE_PLATFORMS,
            platform_catalog=tuple(platform_catalog),
            profile_platforms=tuple(selected),
        )

    def toggle_profile_platform(self, platform_id: int) -> "UserContext":
        """Отмечает или снимает платформу в черновике анкеты."""
        selected = list(self.profile_platforms)
        if platform_id in selected:
            selected.remove(platform_id)
        else:
            selected.append(platform_id)
        return replace(
            self, screen=ContextScreen.PROFILE_PLATFORMS, profile_platforms=tuple(selected)
        )

    def at_ip_input(self) -> "UserContext":
        """Экран 9г: ожидание IP-адреса (или названия города)."""
        return replace(self, screen=ContextScreen.IP_INPUT)

    def at_played_list(
        self, records: Sequence[int], page: int = 1, total_pages: int = 1
    ) -> "UserContext":
        """Экран 10: список сыгранных игр."""
        return replace(
            self,
            screen=ContextScreen.PLAYED_LIST,
            records=tuple(records),
            library_page=max(1, page),
            library_total_pages=max(1, total_pages),
            selected_record_id=None,
        )


    def at_played_info(self, record_id: int) -> "UserContext":
        """Экран 11: информация о сыгранной игре."""
        return replace(
            self, screen=ContextScreen.PLAYED_INFO, selected_record_id=record_id
        )

    def at_review_input(self, record_id: int) -> "UserContext":
        """Экран 11а: ожидание текста отзыва."""
        return replace(
            self, screen=ContextScreen.REVIEW_INPUT, selected_record_id=record_id
        )

    def at_favorites(
        self, games: Sequence[Game], page: int = 1, total_pages: int = 1
    ) -> "UserContext":
        """Экран 12: избранное."""
        return replace(
            self,
            screen=ContextScreen.FAVORITES_LIST,
            games=tuple(games),
            games_page=max(1, page),
            games_total_pages=max(1, total_pages),
            games_has_next=page < total_pages,
            games_has_previous=page > 1,
            current_game_id=None,
        )


class StateStorage:
    """Потокобезопасное хранилище состояний пользователей (в памяти бота)."""

    def __init__(self) -> None:
        self._states: Dict[int, UserContext] = {}
        self._lock = threading.RLock()

    def get(self, user_id: int) -> Optional[UserContext]:
        """Возвращает сохранённое состояние или None, если его ещё нет."""
        with self._lock:
            return self._states.get(user_id)

    def get_or_default(self, user_id: int) -> UserContext:
        """Возвращает состояние пользователя, при отсутствии — пустое."""
        with self._lock:
            return self._states.get(user_id) or UserContext()

    def has(self, user_id: int) -> bool:
        """Проверяет, начинал ли пользователь работу с ботом."""
        with self._lock:
            return user_id in self._states

    def save(self, user_id: int, context: UserContext) -> UserContext:
        """Сохраняет состояние пользователя."""
        with self._lock:
            self._states[user_id] = context
        return context

    def reset(self, user_id: int) -> None:
        """Удаляет состояние пользователя (например, при команде /start)."""
        with self._lock:
            self._states.pop(user_id, None)

    def clear(self) -> None:
        """Очищает состояния всех пользователей (используется в тестах)."""
        with self._lock:
            self._states.clear()

    def __len__(self) -> int:  # pragma: no cover - служебный метод
        with self._lock:
            return len(self._states)


__all__ = ["ContextScreen", "StateStorage", "UserContext"]
