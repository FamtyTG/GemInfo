"""Экраны Экрана 1 «Старт» и Экрана 2 «Главное меню»."""

from __future__ import annotations

import logging

from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class StartScreen:
    """Экран 1. Старт — приветствие при первом открытии бота."""

    def __init__(self, gateway: TelegramGateway) -> None:
        self._gateway = gateway

    def show(self, chat_id: int) -> None:
        logger.debug("Экран 1 «Старт» для чата %s", chat_id)
        self._gateway.send_text(
            chat_id, texts.START_WELCOME, reply_markup=keyboards.start_keyboard()
        )


class MainMenuScreen:
    """Экран 2. Главное меню — три основных раздела бота."""

    def __init__(self, gateway: TelegramGateway, storage: StateStorage) -> None:
        self._gateway = gateway
        self._storage = storage

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 2 «Главное меню» для пользователя %s", user_id)
        # При переходе в главное меню промежуточные данные диалога сбрасываются
        self._storage.save(user_id, UserContext().at_main_menu())
        self._gateway.send_text(
            chat_id, texts.MAIN_MENU_WELCOME, reply_markup=keyboards.main_menu_keyboard()
        )
