"""Экраны 10–12: «Во что я играл», отзыв об игре и избранное."""

from __future__ import annotations

import logging
from typing import Optional

from gamehunter.domain.entities import FavoriteGame, Game
from gamehunter.domain.exceptions import (
    EmptyReviewError,
    GameHunterError,
    PlayedGameNotFoundError,
    ReviewTooLongError,
)
from gamehunter.domain.services import LibraryService
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import StateStorage

logger = logging.getLogger(__name__)


class PlayedListScreen(BaseScreen):
    """Экран 10. Список игр, в которые пользователь уже играл."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        library_service: LibraryService,
    ) -> None:
        super().__init__(gateway, storage)
        self._library = library_service

    def show(self, chat_id: int, user_id: int, page: int = 1, notice: str = "") -> None:
        logger.debug("Экран 10 «Во что я играл» для пользователя %s", user_id)
        context = self.context(user_id)

        try:
            history = self._library.get_played_history(user_id, page)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        if history.is_empty:
            self.save(user_id, context.at_played_list((), 1, 1))
            message = texts.PLAYED_EMPTY if not notice else f"{notice}\n\n{texts.PLAYED_EMPTY}"
            self.send(chat_id, message, reply_markup=keyboards.back_to_menu_keyboard())
            return

        self.save(
            user_id,
            context.at_played_list(
                [record.id for record in history.items], history.page, history.total_pages
            ),
        )

        message = texts.format_played_history(history)
        if notice:
            message = f"{notice}\n\n{message}"

        self.send(
            chat_id,
            message,
            reply_markup=keyboards.played_list_keyboard(
                history.items, history.page, history.total_pages
            ),
        )


class PlayedInfoScreen(BaseScreen):
    """Экран 11. Информация о сыгранной игре: дата добавления и отзыв."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        library_service: LibraryService,
        list_screen: PlayedListScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._library = library_service
        self._list_screen = list_screen

    def show(self, chat_id: int, user_id: int, record_id: int, notice: str = "") -> None:
        logger.debug("Экран 11 «Информация об игре» #%s", record_id)
        context = self.context(user_id)

        try:
            record = self._library.get_played(user_id, record_id)
        except PlayedGameNotFoundError as exc:
            logger.info("Запись #%s не найдена у пользователя %s", record_id, user_id)
            self._list_screen.show(chat_id, user_id, page=1, notice=exc.user_message)
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self.save(user_id, context.at_played_info(record_id))

        message = texts.format_played_info(record)
        if notice:
            message = f"{notice}\n\n{message}"

        self.send(
            chat_id,
            message,
            reply_markup=keyboards.played_info_keyboard(record_id, context.library_page),
        )

    def delete(self, chat_id: int, user_id: int, record_id: int) -> None:
        """Кнопка «Удалить из списка»."""
        try:
            name = self._library.remove_played(user_id, record_id)
        except PlayedGameNotFoundError as exc:
            self._list_screen.show(chat_id, user_id, page=1, notice=exc.user_message)
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self._list_screen.show(
            chat_id, user_id, page=1, notice=texts.PLAYED_REMOVED.format(name)
        )


class ReviewInputScreen(BaseScreen):
    """Экран 11а. Ввод отзыва об игре (до 1000 символов)."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        library_service: LibraryService,
        info_screen: PlayedInfoScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._library = library_service
        self._info_screen = info_screen

    def show(
        self, chat_id: int, user_id: int, record_id: int, error_text: str = ""
    ) -> None:
        logger.debug("Экран 11а «Ввод отзыва» для записи #%s", record_id)
        self.save(user_id, self.context(user_id).at_review_input(record_id))

        message = texts.REVIEW_PROMPT
        if error_text:
            message = f"{error_text}\n\n{message}"
        self.send(chat_id, message, reply_markup=keyboards.hide_keyboard())

    def handle_review(self, chat_id: int, user_id: int, raw_text: str) -> None:
        """Сохраняет отзыв из текстового сообщения."""
        record_id: Optional[int] = self.context(user_id).selected_record_id
        if record_id is None:
            self.state_lost(chat_id, user_id)
            return

        try:
            self._library.add_review(user_id, record_id, raw_text)
        except (EmptyReviewError, ReviewTooLongError) as exc:
            logger.info("Отзыв не сохранён для записи #%s: %s", record_id, exc)
            self.show(chat_id, user_id, record_id, error_text=exc.user_message)
            return
        except PlayedGameNotFoundError as exc:
            self.notify(chat_id, exc.user_message)
            self._info_screen.show(chat_id, user_id, record_id)
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self._info_screen.show(chat_id, user_id, record_id, notice=texts.REVIEW_SAVED)


class FavoritesScreen(BaseScreen):
    """Экран 12. Избранные игры пользователя."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        library_service: LibraryService,
    ) -> None:
        super().__init__(gateway, storage)
        self._library = library_service

    def show(self, chat_id: int, user_id: int, page: int = 1, notice: str = "") -> None:
        logger.debug("Экран 12 «Избранное» для пользователя %s", user_id)
        context = self.context(user_id)

        try:
            favorites = self._library.get_favorites(user_id, page)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        if favorites.is_empty:
            self.save(user_id, context.at_favorites((), 1, 1))
            message = (
                texts.FAVORITES_EMPTY if not notice else f"{notice}\n\n{texts.FAVORITES_EMPTY}"
            )
            self.send(chat_id, message, reply_markup=keyboards.back_to_menu_keyboard())
            return

        games = [self._as_game(record) for record in favorites.items]
        self.save(user_id, context.at_favorites(games, favorites.page, favorites.total_pages))

        message = texts.format_favorites(favorites)
        if notice:
            message = f"{notice}\n\n{message}"

        self.send(
            chat_id,
            message,
            reply_markup=keyboards.favorites_keyboard(
                favorites.items, favorites.page, favorites.total_pages
            ),
        )

    @staticmethod
    def _as_game(record: FavoriteGame) -> Game:
        """Собирает объект игры из записи избранного (для карточки игры)."""
        return Game(
            id=record.game_id, slug=record.slug, name=record.name, image_url=record.image_url
        )
