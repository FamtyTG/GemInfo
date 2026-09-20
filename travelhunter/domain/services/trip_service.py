"""Сервис поездок пользователя.

Бизнес-правила экранов «История поездок»:
    * сохранение поездки при выборе города (дата = текущая);
    * история поездок текущего пользователя от новых к старым;
    * пагинация по ``page_size`` записей;
    * заметка к поездке не длиннее ``note_max_length`` символов.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from travelhunter.domain.entities import Trip, TripPage
from travelhunter.domain.exceptions import (
    EmptyNoteError,
    NoteTooLongError,
    TripNotFoundError,
)
from travelhunter.domain.interfaces import TripRepository

logger = logging.getLogger(__name__)

# Ограничение поля name в таблице visited_cities (varchar(50))
CITY_NAME_MAX_LENGTH = 50


class TripService:
    """Работа с поездками пользователя (создание, история, заметки)."""

    def __init__(
        self,
        repository: TripRepository,
        page_size: int = 5,
        note_max_length: int = 1000,
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._repository = repository
        self._page_size = max(1, page_size)
        self._note_max_length = max(1, note_max_length)
        # now_provider позволяет подменить «сейчас» в тестах
        self._now_provider = now_provider or datetime.now

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def note_max_length(self) -> int:
        return self._note_max_length

    # ------------------------------------------------------------------ #
    # Экран 5 -> 6. Сохранение поездки
    # ------------------------------------------------------------------ #
    def create_trip(
        self,
        tg_user_id: int,
        city_name: str,
        arrival_date: Optional[datetime] = None,
    ) -> Trip:
        """Создаёт запись о поездке и возвращает её."""
        name = (city_name or "").strip()[:CITY_NAME_MAX_LENGTH]
        trip = self._repository.add(
            tg_user_id=tg_user_id,
            city_name=name,
            arrival_date=arrival_date or self._now_provider(),
        )
        logger.info("Создана поездка #%s пользователя %s: %s", trip.id, tg_user_id, name)
        return trip

    # ------------------------------------------------------------------ #
    # Экран 7. История поездок
    # ------------------------------------------------------------------ #
    def get_history(self, tg_user_id: int, page: int = 1) -> TripPage:
        """Возвращает страницу истории поездок пользователя."""
        page = max(1, int(page))
        return self._repository.page_by_user(
            tg_user_id=tg_user_id, page=page, page_size=self._page_size
        )

    # ------------------------------------------------------------------ #
    # Экран 8. Информация о поездке
    # ------------------------------------------------------------------ #
    def get_trip(self, tg_user_id: int, trip_id: int) -> Trip:
        """Возвращает поездку пользователя.

        :raises TripNotFoundError: поездки с таким id у пользователя нет.
        """
        trip = self._repository.find_by_id(trip_id=trip_id, tg_user_id=tg_user_id)
        if trip is None:
            logger.warning(
                "Поездка #%s не найдена для пользователя %s", trip_id, tg_user_id
            )
            raise TripNotFoundError()
        return trip

    # ------------------------------------------------------------------ #
    # Экран 9. Добавление заметки
    # ------------------------------------------------------------------ #
    def add_note(self, tg_user_id: int, trip_id: int, text: str) -> Trip:
        """Сохраняет заметку к поездке.

        :raises NoteTooLongError: заметка длиннее допустимого лимита;
        :raises EmptyNoteError: заметка пустая;
        :raises TripNotFoundError: поездка не найдена.
        """
        note = (text or "").strip()

        if not note:
            raise EmptyNoteError()
        if len(note) > self._note_max_length:
            raise NoteTooLongError(self._note_max_length)

        trip = self._repository.update_note(
            trip_id=trip_id, tg_user_id=tg_user_id, note=note
        )
        if trip is None:
            raise TripNotFoundError()

        logger.info("Заметка сохранена для поездки #%s", trip_id)
        return trip
