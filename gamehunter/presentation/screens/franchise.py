"""Экраны 6–8: поиск игр по франшизе (IP)."""

from __future__ import annotations

import logging
from typing import Optional

from gamehunter.domain.exceptions import (
    FranchiseNotFoundError,
    GameHunterError,
    NoGamesFoundError,
)
from gamehunter.domain.services import GameService
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import ContextScreen, StateStorage

logger = logging.getLogger(__name__)


class FranchiseInputScreen(BaseScreen):
    """Экран 6. Ввод названия франшизы (IP)."""

    def __init__(self, gateway: TelegramGateway, storage: StateStorage) -> None:
        super().__init__(gateway, storage)
        self._list_screen: Optional["FranchiseListScreen"] = None

    def attach_list_screen(self, list_screen: "FranchiseListScreen") -> None:
        """Связывает экран ввода с экраном результатов (взаимные переходы)."""
        self._list_screen = list_screen

    def show(self, chat_id: int, user_id: int, error_text: str = "") -> None:
        logger.debug("Экран 6 «Ввод франшизы» для пользователя %s", user_id)
        self.save(user_id, self.context(user_id).at_franchise_input())

        message = texts.FRANCHISE_INPUT_PROMPT
        if error_text:
            message = f"{error_text}\n\n{message}"

        # Скрываем reply-клавиатуру: пользователь будет вводить текст
        self.send(chat_id, message, reply_markup=keyboards.hide_keyboard())

    def search(self, chat_id: int, user_id: int, raw_name: str) -> None:
        """Обрабатывает введённое название франшизы."""
        name = (raw_name or "").strip()
        if not name:
            self.show(chat_id, user_id, error_text=texts.FRANCHISE_EMPTY_NAME)
            return
        if self._list_screen is not None:
            self._list_screen.search(chat_id, user_id, name)


class FranchiseListScreen(BaseScreen):
    """Экран 7. Список найденных франшиз."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        input_screen: FranchiseInputScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._input_screen = input_screen

    def search(self, chat_id: int, user_id: int, name: str) -> None:
        """Ищет франшизы в каталоге и показывает результаты."""
        logger.debug("Экран 7 «Список франшиз» по запросу «%s»", name)
        try:
            franchises = self._games.search_franchises(name)
        except FranchiseNotFoundError as exc:
            logger.info("Франшиза «%s» не найдена", name)
            self._input_screen.show(chat_id, user_id, error_text=exc.user_message)
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self.save(user_id, self.context(user_id).with_franchises(franchises))
        self.send(
            chat_id,
            texts.format_franchises(franchises),
            reply_markup=keyboards.franchises_keyboard(franchises),
        )


class FranchiseGamesScreen(BaseScreen):
    """Экран 8. Игры выбранной франшизы."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service

    def show(self, chat_id: int, user_id: int, index: int) -> None:
        """Показывает игры франшизы, выбранной кнопкой «Выбрать франшизу N»."""
        context = self.context(user_id)
        franchise = context.franchise_at(index)

        if franchise is None:
            # Кнопка нажата, но список франшиз уже неактуален
            self.state_lost(chat_id, user_id)
            return

        logger.debug(
            "Экран 8 «Игры франшизы» %s (#%s) для пользователя %s",
            franchise.name,
            franchise.id,
            user_id,
        )

        try:
            games = self._games.get_franchise_games(franchise)
        except NoGamesFoundError as exc:
            logger.info("У франшизы «%s» нет игр в каталоге", franchise.name)
            self.send(
                chat_id,
                exc.user_message,
                reply_markup=keyboards.retry_franchise_keyboard(),
            )
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self.save(user_id, context.at_franchise_games(franchise.id, games, franchise.name))
        self._render(chat_id, games, franchise.name)

    def rerender(self, chat_id: int, user_id: int) -> None:
        """Показывает сохранённые игры франшизы (кнопка «Назад» из карточки)."""
        context = self.context(user_id)
        if not context.games:
            self.state_lost(chat_id, user_id)
            return

        self.save(user_id, context.back_to_list(ContextScreen.FRANCHISE_GAMES))
        self._render(chat_id, context.games, context.franchise_name)

    # ------------------------------------------------------------------ #
    def _render(self, chat_id: int, games, franchise_name: str) -> None:
        title = texts.FRANCHISE_GAMES_TITLE.format(franchise_name or "—")
        self.send(
            chat_id,
            texts.format_game_list(games, title),
            reply_markup=keyboards.franchise_games_keyboard(games),
        )
