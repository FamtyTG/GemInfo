"""Экран 3. Праздники на 7 дней."""

from __future__ import annotations

import logging

from travelhunter.domain.exceptions import TravelHunterError
from travelhunter.domain.services import HolidayService
from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class HolidaysScreen:
    """Показывает российские праздники на ближайшие 7 дней (не более 5)."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        holiday_service: HolidayService,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._service = holiday_service

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 3 «Праздники на 7 дней» для пользователя %s", user_id)
        self._storage.save(user_id, UserContext().at_main_menu())

        try:
            holidays = self._service.get_upcoming_holidays()
            message = texts.format_holidays(holidays)
        except TravelHunterError as exc:
            # Внешний API недоступен или вернул некорректный ответ —
            # показываем сообщение об ошибке и не завершаем работу бота.
            logger.error("Не удалось показать праздники: %s", exc)
            message = exc.user_message

        self._gateway.send_text(
            chat_id, message, reply_markup=keyboards.back_to_menu_keyboard()
        )
