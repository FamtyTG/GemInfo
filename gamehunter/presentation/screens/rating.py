"""Экран 13 «Возрастной рейтинг»: подбор игр по категории ESRB/PEGI.

Пользователь выбирает категорию (6+, 13+, 18+…), она сохраняется в состоянии
(``UserContext.age_rating``) и подменяет возраст из анкеты на время подборки:
список игр показывает только игры, подходящие под выбранный рейтинг.
"""

from __future__ import annotations

import logging

from gamehunter.domain import age_ratings
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.screens.picking import GameListScreen
from gamehunter.presentation.state import StateStorage

logger = logging.getLogger(__name__)


class AgeRatingScreen(BaseScreen):
    """Экран 13. Выбор возрастного рейтинга для подборки игр."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_list_screen: GameListScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._game_list = game_list_screen

    def show(self, chat_id: int, user_id: int, note: str = "") -> None:
        """Показывает категории рейтингов и текущий выбор."""
        logger.debug("Экран 13 «Возрастной рейтинг» для пользователя %s", user_id)
        context = self.context(user_id).at_age_rating()
        self.save(user_id, context)

        message = texts.AGE_RATING_TITLE
        if context.age_rating is not None:
            label = age_ratings.rating_label(context.age_rating)
            message = f"{message}\n\n{texts.AGE_RATING_CURRENT.format(label)}"
        if note:
            message = f"{note}\n\n{message}"

        self.send(
            chat_id,
            message,
            reply_markup=keyboards.age_rating_keyboard(context.age_rating),
        )

    def pick(self, chat_id: int, user_id: int, age: int) -> None:
        """Категория выбрана: сохраняем и показываем подборку игр."""
        if age not in {choice[0] for choice in age_ratings.RATING_CHOICES}:
            logger.warning("Неизвестный возрастной рейтинг %s от пользователя %s", age, user_id)
            self.show(chat_id, user_id)
            return
        self.save(user_id, self.context(user_id).with_age_rating(age))
        logger.info("Пользователь %s выбрал возрастной рейтинг %s+", user_id, age)
        self._game_list.show(chat_id, user_id, page=1)

    def reset(self, chat_id: int, user_id: int) -> None:
        """Сброс рейтинга: подборка снова по возрасту из анкеты."""
        self.save(user_id, self.context(user_id).with_age_rating(None))
        self.show(chat_id, user_id, note=texts.AGE_RATING_RESET_DONE)
