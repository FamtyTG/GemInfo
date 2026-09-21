"""Сервис библиотеки пользователя: «во что я играл», избранное и отзывы.

Бизнес-правила:
    * одна и та же игра не добавляется в список сыгранных дважды;
    * список сыгранных и избранное выводятся постранично (по ``page_size``);
    * отзыв к игре — не длиннее ``note_max_length`` символов и не пустой;
    * пользователь видит и изменяет только свои записи (по ``tg_user_id``).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, List, Optional, Sequence, Set

from gamehunter.domain.entities import (
    FavoriteGame,
    Game,
    LibraryPage,
    PlayedGame,
)
from gamehunter.domain.exceptions import (
    EmptyReviewError,
    FavoriteAlreadyExistsError,
    FavoriteNotFoundError,
    GameAlreadyPlayedError,
    PlayedGameNotFoundError,
    ReviewTooLongError,
)
from gamehunter.domain.interfaces import LibraryRepository

logger = logging.getLogger(__name__)

# Ограничение поля name в таблицах библиотеки (varchar(150))
GAME_NAME_MAX_LENGTH = 150


class LibraryService:
    """Работа со списком сыгранных игр, избранным и отзывами."""

    def __init__(
        self,
        repository: LibraryRepository,
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
    # «Во что я уже играл»
    # ------------------------------------------------------------------ #
    def add_played(
        self,
        tg_user_id: int,
        game: Game,
        played_at: Optional[datetime] = None,
    ) -> PlayedGame:
        """Добавляет игру в список сыгранных.

        :raises GameAlreadyPlayedError: игра уже добавлена ранее.
        """
        if self._repository.has_played(tg_user_id, game.id):
            logger.info(
                "Игра #%s уже есть в списке сыгранных пользователя %s", game.id, tg_user_id
            )
            raise GameAlreadyPlayedError()

        record = self._repository.add_played(
            tg_user_id=tg_user_id,
            game=self._with_short_name(game),
            played_at=played_at or self._now_provider(),
        )
        logger.info(
            "Игра «%s» добавлена в список сыгранных пользователя %s", game.name, tg_user_id
        )
        return record

    def get_played_history(self, tg_user_id: int, page: int = 1) -> LibraryPage[PlayedGame]:
        """Возвращает страницу списка сыгранных игр (от новых к старым)."""
        return self._repository.page_played(
            tg_user_id=tg_user_id, page=max(1, int(page)), page_size=self._page_size
        )

    def get_played(self, tg_user_id: int, record_id: int) -> PlayedGame:
        """Возвращает запись о сыгранной игре.

        :raises PlayedGameNotFoundError: записи нет у этого пользователя.
        """
        record = self._repository.find_played_by_id(record_id, tg_user_id)
        if record is None:
            logger.warning(
                "Запись #%s не найдена для пользователя %s", record_id, tg_user_id
            )
            raise PlayedGameNotFoundError()
        return record

    def add_review(self, tg_user_id: int, record_id: int, text: str) -> PlayedGame:
        """Сохраняет отзыв к сыгранной игре.

        :raises ReviewTooLongError: отзыв длиннее лимита;
        :raises EmptyReviewError: отзыв пустой;
        :raises PlayedGameNotFoundError: записи не существует.
        """
        review = (text or "").strip()

        if not review:
            raise EmptyReviewError()
        if len(review) > self._note_max_length:
            raise ReviewTooLongError(self._note_max_length)

        record = self._repository.update_review(record_id, tg_user_id, review)
        if record is None:
            raise PlayedGameNotFoundError()

        logger.info("Отзыв сохранён для записи #%s", record_id)
        return record

    def remove_played(self, tg_user_id: int, record_id: int) -> str:
        """Удаляет запись из списка сыгранных и возвращает название игры.

        :raises PlayedGameNotFoundError: записи не существует.
        """
        record = self.get_played(tg_user_id, record_id)
        deleted = self._repository.delete_played(record_id, tg_user_id)
        if not deleted:
            raise PlayedGameNotFoundError()

        logger.info("Запись #%s удалена из списка сыгранных", record_id)
        return record.name

    def played_game_ids(self, tg_user_id: int) -> Set[int]:
        """Идентификаторы игр, в которые пользователь уже играл."""
        return self._repository.played_game_ids(tg_user_id)

    def is_played(self, tg_user_id: int, game_id: int) -> bool:
        """Проверяет, играл ли пользователь в эту игру."""
        return self._repository.has_played(tg_user_id, game_id)

    # ------------------------------------------------------------------ #
    # Избранное
    # ------------------------------------------------------------------ #
    def add_favorite(self, tg_user_id: int, game: Game) -> FavoriteGame:
        """Добавляет игру в избранное.

        :raises FavoriteAlreadyExistsError: игра уже в избранном.
        """
        if self._repository.is_favorite(tg_user_id, game.id):
            raise FavoriteAlreadyExistsError()

        record = self._repository.add_favorite(tg_user_id, self._with_short_name(game))
        logger.info("Игра «%s» добавлена в избранное пользователя %s", game.name, tg_user_id)
        return record

    def remove_favorite(self, tg_user_id: int, game_id: int) -> bool:
        """Убирает игру из избранного.

        :raises FavoriteNotFoundError: игры нет в избранном.
        """
        removed = self._repository.remove_favorite(tg_user_id, game_id)
        if not removed:
            raise FavoriteNotFoundError()
        logger.info("Игра #%s убрана из избранного пользователя %s", game_id, tg_user_id)
        return removed

    def toggle_favorite(self, tg_user_id: int, game: Game) -> tuple[FavoriteGame, bool]:
        """Добавляет игру в избранное или убирает её.

        :return: (запись избранного, добавлена ли игра).
        """
        if self._repository.is_favorite(tg_user_id, game.id):
            self.remove_favorite(tg_user_id, game.id)
            return FavoriteGame(
                id=0,
                tg_user_id=tg_user_id,
                game_id=game.id,
                slug=game.slug,
                name=game.name,
                added_at=self._now_provider(),
            ), False

        record = self._repository.add_favorite(tg_user_id, self._with_short_name(game))
        return record, True

    def get_favorites(self, tg_user_id: int, page: int = 1) -> LibraryPage[FavoriteGame]:
        """Возвращает страницу списка избранных игр."""
        return self._repository.page_favorites(
            tg_user_id=tg_user_id, page=max(1, int(page)), page_size=self._page_size
        )

    def is_favorite(self, tg_user_id: int, game_id: int) -> bool:
        """Проверяет, находится ли игра в избранном."""
        return self._repository.is_favorite(tg_user_id, game_id)

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    @staticmethod
    def _with_short_name(game: Game) -> Game:
        """Обрезает название игры под ограничение поля в базе данных."""
        name = (game.name or "").strip()[:GAME_NAME_MAX_LENGTH]
        if name == game.name:
            return game
        return Game(
            id=game.id,
            slug=game.slug,
            name=name,
            released=game.released,
            rating=game.rating,
            genres=game.genres,
            platforms=game.platforms,
            image_url=game.image_url,
            metacritic=game.metacritic,
            playtime_hours=game.playtime_hours,
            announced=game.announced,
        )

    @staticmethod
    def names_of(records: Sequence[object]) -> List[str]:
        """Названия игр из записей библиотеки (для логов и отладки)."""
        return [getattr(record, "name", "?") for record in records]
