"""Состояние пользователя (конечный автомат переходов между экранами).

telebot не хранит «шаги» диалога сам, поэтому состояние каждого пользователя
сохраняется в памяти бота. Это позволяет:
    * понимать, что означает присланное текстовое сообщение (город или заметка);
    * помнить выбранный город и список ближайших городов между экранами;
    * возвращать пользователя на нужный экран по кнопке «Назад».

Хранилище потокобезопасно: telebot обрабатывает апдейты в пуле потоков.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple

from travelhunter.domain.entities import City, NearbyCity


class Screen(str, Enum):
    """Экраны, на которых бот ждёт действия пользователя."""

    MAIN_MENU = "main_menu"                  # Экран 2. Главное меню
    WAITING_CITY_NAME = "waiting_city_name"  # Экран 4. Ввод текущего города
    NEARBY_CITIES = "nearby_cities"          # Экран 5. Список ближайших городов
    CITY_INFO = "city_info"                  # Экран 6. Информация о городе
    HISTORY = "history"                      # Экран 7. Список поездок
    TRIP_INFO = "trip_info"                  # Экран 8. Информация о поездке
    WAITING_NOTE = "waiting_note"            # Экран 9. Добавление заметки


@dataclass(frozen=True)
class UserContext:
    """Всё, что бот помнит о текущем диалоге с пользователем."""

    screen: Screen = Screen.MAIN_MENU
    current_city: Optional[City] = None
    nearby_cities: Tuple[NearbyCity, ...] = ()
    selected_trip_id: Optional[int] = None
    history_page: int = 1

    # ------------------------- переходы ------------------------- #
    def at_main_menu(self) -> "UserContext":
        """Контекст главного меню (промежуточные данные больше не нужны)."""
        return UserContext(screen=Screen.MAIN_MENU)

    def at_city_input(self) -> "UserContext":
        """Контекст Экрана 4: ждём название текущего города."""
        return replace(
            self, screen=Screen.WAITING_CITY_NAME, current_city=None, nearby_cities=()
        )

    def with_current_city(self, city: City) -> "UserContext":
        """Сохраняем найденный город пользователя."""
        return replace(self, current_city=city, nearby_cities=())

    def with_nearby_cities(self, cities: List[NearbyCity]) -> "UserContext":
        """Сохраняем список ближайших городов для кнопок выбора."""
        return replace(
            self, screen=Screen.NEARBY_CITIES, nearby_cities=tuple(cities)
        )

    def with_trip(self, trip_id: int) -> "UserContext":
        """Сохраняем идентификатор созданной/выбранной поездки."""
        return replace(self, screen=Screen.CITY_INFO, selected_trip_id=trip_id)

    def with_history_page(self, page: int) -> "UserContext":
        """Сохраняем номер страницы истории поездок."""
        return replace(self, screen=Screen.HISTORY, history_page=max(1, page))

    def at_trip_info(self, trip_id: int) -> "UserContext":
        """Контекст Экрана 8: просматриваем конкретную поездку."""
        return replace(self, screen=Screen.TRIP_INFO, selected_trip_id=trip_id)

    def at_note_input(self, trip_id: int) -> "UserContext":
        """Контекст Экрана 9: ждём текст заметки."""
        return replace(self, screen=Screen.WAITING_NOTE, selected_trip_id=trip_id)

    # ------------------------- данные ------------------------- #
    def nearby_city(self, index: int) -> Optional[NearbyCity]:
        """Возвращает город из списка по номеру кнопки (нумерация с 1)."""
        if index < 1 or index > len(self.nearby_cities):
            return None
        return self.nearby_cities[index - 1]


class StateStorage:
    """Потокобезопасное хранилище состояний пользователей."""

    def __init__(self) -> None:
        self._states: Dict[int, UserContext] = {}
        self._lock = threading.RLock()

    def get(self, user_id: int) -> Optional[UserContext]:
        """Возвращает сохранённое состояние или None, если его ещё нет."""
        with self._lock:
            return self._states.get(user_id)

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
