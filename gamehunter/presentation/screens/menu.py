"""Экран 1 «Старт» и Экран 2 «Главное меню»."""

from __future__ import annotations

import logging

from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens import tutorial
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class StartScreen(BaseScreen):
    """Экран 1. Старт — приветствие при первом открытии бота."""

    def show(self, chat_id: int) -> None:
        logger.debug("Экран 1 «Старт» для чата %s", chat_id)
        markup = keyboards.start_keyboard()
        if not tutorial.send_tutorial(
            self._gateway, chat_id, "start", texts.START_WELCOME, markup
        ):
            self.send(chat_id, texts.START_WELCOME, reply_markup=markup)


class MainMenuScreen(BaseScreen):
    """Экран 2. Главное меню — пять разделов бота."""

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 2 «Главное меню» для пользователя %s", user_id)
        # При переходе в главное меню промежуточные данные диалога сбрасываются
        self.save(user_id, UserContext().at_main_menu())
        self.send(
            chat_id, texts.MAIN_MENU_WELCOME, reply_markup=keyboards.main_menu_keyboard()
        )
