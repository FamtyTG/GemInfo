"""Экраны 7–9 раздела «История поездок»."""

from __future__ import annotations

import logging

from travelhunter.domain.exceptions import (
    EmptyNoteError,
    NoteTooLongError,
    TravelHunterError,
)
from travelhunter.domain.services import TripService
from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class HistoryScreen:
    """Экран 7. Список поездок пользователя с пагинацией по 5 записей."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        trip_service: TripService,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._service = trip_service

    def show(self, chat_id: int, user_id: int, page: int = 1) -> None:
        logger.debug("Экран 7 «История поездок» (страница %s), пользователь %s", page, user_id)

        try:
            trip_page = self._service.get_history(user_id, page=page)
        except TravelHunterError as exc:
            logger.error("Не удалось получить историю поездок: %s", exc)
            self._storage.save(user_id, UserContext().at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        self._storage.save(
            user_id, (self._storage.get(user_id) or UserContext()).with_history_page(trip_page.page)
        )

        if trip_page.is_empty:
            # Показываем только кнопку «В главное меню»
            self._gateway.send_text(
                chat_id, texts.HISTORY_EMPTY, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        markup = keyboards.history_keyboard(
            trip_ids=[trip.id for trip in trip_page.trips],
            page=trip_page.page,
            total_pages=trip_page.total_pages,
        )
        self._gateway.send_text(chat_id, texts.format_history(trip_page), reply_markup=markup)


class TripInfoScreen:
    """Экран 8. Информация о конкретной поездке."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        trip_service: TripService,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._service = trip_service

    def show(self, chat_id: int, user_id: int, trip_id: int) -> None:
        logger.debug("Экран 8 «Информация о поездке» #%s, пользователь %s", trip_id, user_id)
        context = self._storage.get(user_id) or UserContext()

        try:
            trip = self._service.get_trip(user_id, trip_id)
        except TravelHunterError as exc:
            logger.error("Не удалось показать поездку #%s: %s", trip_id, exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        self._storage.save(user_id, context.at_trip_info(trip.id))
        self._gateway.send_text(
            chat_id,
            texts.format_trip(trip),
            reply_markup=keyboards.trip_info_keyboard(trip.id, context.history_page),
        )


class NoteInputScreen:
    """Экран 9. Добавление заметки к поездке."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        trip_service: TripService,
        trip_info_screen: TripInfoScreen,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._service = trip_service
        self._trip_info_screen = trip_info_screen

    def show(self, chat_id: int, user_id: int, trip_id: int) -> None:
        logger.debug("Экран 9 «Добавление заметки» к поездке #%s", trip_id)
        context = self._storage.get(user_id) or UserContext()

        # Проверяем, что поездка существует, чтобы не принимать заметку «в никуда»
        try:
            self._service.get_trip(user_id, trip_id)
        except TravelHunterError as exc:
            logger.error("Поездка #%s недоступна для заметки: %s", trip_id, exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        self._storage.save(user_id, context.at_note_input(trip_id))
        self._gateway.send_text(
            chat_id, texts.NOTE_PROMPT, reply_markup=keyboards.hide_keyboard()
        )

    def save(self, chat_id: int, user_id: int, raw_text: str) -> bool:
        """Сохраняет введённую заметку.

        :return: True, если пользователь покинул экран ввода заметки.
        """
        context = self._storage.get(user_id) or UserContext()
        trip_id = context.selected_trip_id

        if trip_id is None:
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, texts.STATE_LOST, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return True

        try:
            self._service.add_note(user_id, trip_id, raw_text)
        except (NoteTooLongError, EmptyNoteError) as exc:
            # Остаёмся на Экране 9 и ждём повторного ввода заметки
            logger.info("Заметка к поездке #%s не принята: %s", trip_id, exc)
            self._gateway.send_text(chat_id, exc.user_message)
            return False
        except TravelHunterError as exc:
            logger.error("Не удалось сохранить заметку к поездке #%s: %s", trip_id, exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return True

        self._gateway.send_text(chat_id, texts.NOTE_SAVED)
        # Возвращаем пользователя на Экран 8 — уже с сохранённой заметкой
        self._trip_info_screen.show(chat_id, user_id, trip_id)
        return True
