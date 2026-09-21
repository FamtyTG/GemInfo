"""Базовый класс экрана: отправка сообщений, работа с состоянием и ошибками."""

from __future__ import annotations

import logging
from typing import Optional

from gamehunter.domain.exceptions import GameHunterError
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class BaseScreen:
    """Общие возможности всех экранов бота.

    Экран отвечает только за показ данных и сохранение состояния пользователя.
    Бизнес-логика находится в сервисах предметной области.
    """

    def __init__(self, gateway: TelegramGateway, storage: StateStorage) -> None:
        self._gateway = gateway
        self._storage = storage

    # ------------------------------------------------------------------ #
    # Состояние
    # ------------------------------------------------------------------ #
    def context(self, user_id: int) -> UserContext:
        """Текущее состояние пользователя (пустое, если его ещё нет)."""
        return self._storage.get_or_default(user_id)

    def save(self, user_id: int, context: UserContext) -> UserContext:
        """Сохраняет состояние пользователя."""
        return self._storage.save(user_id, context)

    # ------------------------------------------------------------------ #
    # Отправка сообщений
    # ------------------------------------------------------------------ #
    def send(self, chat_id: int, text: str, reply_markup=None) -> bool:
        """Отправляет текстовое сообщение."""
        return self._gateway.send_text(chat_id, text, reply_markup=reply_markup)

    def notify(self, chat_id: int, text: str) -> None:
        """Отправляет короткое сообщение без кнопок (например, подтверждение)."""
        self._gateway.send_text(chat_id, text)

    def send_photo(self, chat_id: int, image_url: Optional[str], caption: str) -> bool:
        """Отправляет обложку игры; False, если картинки нет или отправить не удалось."""
        if not image_url:
            return False
        return self._gateway.send_photo(chat_id, image_url, caption)

    # ------------------------------------------------------------------ #
    # Ошибки и потерянное состояние
    # ------------------------------------------------------------------ #
    def show_error(
        self, chat_id: int, user_id: int, error: GameHunterError, reply_markup=None
    ) -> None:
        """Показывает текст доменной ошибки и возвращает пользователя в меню."""
        logger.error("Экран %s: %s", type(self).__name__, error)
        self.save(user_id, UserContext().at_main_menu())
        self.send(
            chat_id,
            error.user_message,
            reply_markup=reply_markup or keyboards.back_to_menu_keyboard(),
        )

    def state_lost(self, chat_id: int, user_id: int) -> None:
        """Сообщает, что данные предыдущего шага не сохранились."""
        logger.warning("Потеряно состояние пользователя %s", user_id)
        self.save(user_id, UserContext().at_main_menu())
        self.send(chat_id, texts.STATE_LOST, reply_markup=keyboards.back_to_menu_keyboard())
