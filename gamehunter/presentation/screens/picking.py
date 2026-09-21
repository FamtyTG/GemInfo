"""Экраны 3–5: подбор игр по интересам, список игр и карточка игры."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from gamehunter.domain import age_ratings
from gamehunter.domain.entities import Game, GameDetails, UserProfile
from gamehunter.domain.exceptions import (
    GameHunterError,
    GameNotFoundError,
    NoGamesFoundError,
)
from gamehunter.domain.services import GameService, LibraryService, ProfileService
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens import tutorial
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import ContextScreen, StateStorage, UserContext

logger = logging.getLogger(__name__)


class GenrePickingScreen(BaseScreen):
    """Экран 3. Выбор интересов (жанров) для подбора игр."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        profile_service: ProfileService,
        game_list_screen: "GameListScreen",
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._profiles = profile_service
        self._game_list = game_list_screen

    def show(self, chat_id: int, user_id: int) -> None:
        """Запрашивает список жанров и показывает экран выбора."""
        logger.debug("Экран 3 «Интересы» для пользователя %s", user_id)
        try:
            genres = self._games.get_genres()[: self._games.max_genres]
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        context = self.context(user_id).at_picking(genre_catalog=genres)
        self.save(user_id, context)
        self._render(chat_id, context, with_tutorial=True)

    def toggle(self, chat_id: int, user_id: int, slug: str) -> None:
        """Отмечает или снимает жанр и обновляет экран."""
        context = self.context(user_id)
        if not context.genre_catalog:
            # Кнопка нажата, но список жанров не сохранился (бот перезапускался)
            self.show(chat_id, user_id)
            return

        updated = context.toggle_picked_genre(slug)
        self.save(user_id, updated)
        self._render(chat_id, updated)

    def show_selection(self, chat_id: int, user_id: int) -> None:
        """Кнопка «Показать подборку» по отмеченным жанрам."""
        context = self.context(user_id)
        profile = self._profile_of(user_id)

        if not context.picked_genres and not profile.genre_slugs:
            self._render(chat_id, context, note=texts.GENRES_NO_SELECTION)
            return

        self._game_list.show(chat_id, user_id, page=1)

    def show_all(self, chat_id: int, user_id: int) -> None:
        """Кнопка «Показать всё» — подборка без фильтра по жанрам."""
        context = self.context(user_id).with_picked_genres(())
        self.save(user_id, context)
        self._game_list.show(chat_id, user_id, page=1, ignore_profile_genres=True)

    # ------------------------------------------------------------------ #
    def _render(self, chat_id: int, context: UserContext, note: str = "",
                with_tutorial: bool = False) -> None:
        genres = context.genre_catalog
        message = texts.format_genres_selection(
            genres, context.picked_genres, texts.GENRES_TITLE, texts.GENRES_FOOTER
        )
        if note:
            message = f"{note}\n\n{message}"
        markup = keyboards.picking_genres_keyboard(genres, context.picked_genres)
        if with_tutorial and tutorial.send_tutorial(
            self._gateway, chat_id, "picking", message, markup
        ):
            return
        self.send(chat_id, message, reply_markup=markup)

    def _profile_of(self, user_id: int) -> UserProfile:
        """Анкета пользователя (пустая, если базу прочитать не удалось)."""
        try:
            return self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            logger.error("Не удалось прочитать анкету пользователя %s: %s", user_id, exc)
            return UserProfile(tg_user_id=user_id)


class GameListScreen(BaseScreen):
    """Экран 4. Список игр, подобранных по интересам и анкете."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        profile_service: ProfileService,
        library_service: LibraryService,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._profiles = profile_service
        self._library = library_service

    def show(
        self,
        chat_id: int,
        user_id: int,
        page: int = 1,
        ignore_profile_genres: bool = False,
        title: str = texts.GAMES_TITLE,
    ) -> None:
        """Ищет игры и показывает страницу результатов."""
        logger.debug("Экран 4 «Список игр» для пользователя %s (страница %s)", user_id, page)
        context = self.context(user_id)

        try:
            profile = self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        if ignore_profile_genres:
            # «Показать всё» — интересы из анкеты не применяем
            profile = profile.with_genres(())

        if context.age_rating is not None:
            # Экран 13: рейтинг важнее возраста из анкеты
            profile = profile.with_age(context.age_rating)
            if title == texts.GAMES_TITLE:
                title = texts.GAMES_TITLE_WITH_RATING.format(
                    age_ratings.rating_label(context.age_rating)
                )

        played_ids = self._library.played_game_ids(user_id)
        query = self._games.build_query(genres=context.picked_genres, page=max(1, page))
        effective = self._games.merge_with_profile(query, profile, played_ids)

        try:
            game_page = self._games.find_games(effective, profile, played_ids)
        except NoGamesFoundError as exc:
            logger.info("Игры не найдены для пользователя %s", user_id)
            self.save(user_id, context.at_picking(genre_catalog=context.genre_catalog))
            self.send(chat_id, exc.user_message, reply_markup=keyboards.no_games_keyboard())
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        filters_line = self._filters_line(effective.genres, effective.parent_platforms, context, profile)
        self.save(
            user_id,
            context.at_game_list(
                game_page.games,
                game_page.page,
                game_page.total_pages,
                filters_line,
                has_next=game_page.has_next,
                has_previous=game_page.has_previous,
                played_excluded=bool(played_ids),
            ),
        )

        message = texts.format_games(
            game_page,
            filters_line,
            played_excluded=bool(played_ids),
            title=title,
        )
        markup = keyboards.games_keyboard(
            game_page.games,
            game_page.page,
            has_next=game_page.has_next,
            has_previous=game_page.has_previous,
            rating_active=context.age_rating is not None,
        )
        if not tutorial.send_tutorial(
            self._gateway, chat_id, "game_list", message, markup
        ):
            self.send(chat_id, message, reply_markup=markup)

    def rerender(self, chat_id: int, user_id: int) -> None:
        """Показывает сохранённый список игр (кнопка «Назад» из карточки игры)."""
        context = self.context(user_id)
        if not context.games:
            self.state_lost(chat_id, user_id)
            return

        self.save(user_id, context.back_to_list(ContextScreen.GAME_LIST))
        self.send(
            chat_id,
            texts.format_games_list(
                context.games,
                context.games_page,
                context.games_total_pages,
                context.filters_line,
                played_excluded=context.played_excluded,
            ),
            reply_markup=keyboards.games_keyboard(
                context.games,
                context.games_page,
                has_next=context.games_has_next,
                has_previous=context.games_has_previous,
            ),
        )

    # ------------------------------------------------------------------ #
    def _filters_line(
        self,
        genre_slugs: Sequence[str],
        platform_ids: Sequence[int],
        context: UserContext,
        profile: UserProfile,
    ) -> str:
        """Строка с применёнными фильтрами (жанры, платформы, возраст)."""
        names: Dict[str, str] = {genre.slug: genre.name for genre in context.genre_catalog}
        for slug, name in zip(profile.genre_slugs, profile.genre_names):
            names.setdefault(slug, name)

        genre_names: List[str] = [names.get(slug, slug) for slug in genre_slugs]
        platform_names = list(profile.platform_names) if platform_ids else []
        return texts.format_filters(genre_names, platform_names, profile.age)


class GameCardScreen(BaseScreen):
    """Экран 5. Карточка игры с действиями «Уже играл» и «В избранное»."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        profile_service: ProfileService,
        library_service: LibraryService,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._profiles = profile_service
        self._library = library_service

    def show(
        self,
        chat_id: int,
        user_id: int,
        game_id: int,
        source: Optional[ContextScreen] = None,
        notice: str = "",
    ) -> None:
        """Показывает карточку игры."""
        logger.debug("Экран 5 «Карточка игры» #%s для пользователя %s", game_id, user_id)
        context = self.context(user_id)
        known_game = context.game_by_id(game_id)

        try:
            details = self._games.get_game_details(game_id, default_game=known_game)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        if details is None:
            if known_game is not None:
                # Каталог не ответил, но игра известна из списка — показываем, что есть
                details = GameDetails(game=known_game)
            else:
                self.show_error(chat_id, user_id, GameNotFoundError())
                return

        profile = self._safe_profile(user_id)
        is_played = self._library.is_played(user_id, game_id)
        is_favorite = self._library.is_favorite(user_id, game_id)

        self.save(user_id, context.at_game_card(game_id, list_source=source or context.screen))

        self.send_photo(chat_id, details.image_url, details.game.name)
        message = texts.format_game_card(details, profile, is_played, is_favorite)
        if notice:
            message = f"{notice}\n\n{message}"
        self.send(chat_id, message, reply_markup=keyboards.game_card_keyboard(game_id, is_favorite))

    # ------------------------------------------------------------------ #
    def add_to_played(self, chat_id: int, user_id: int, game_id: int) -> None:
        """Кнопка «Уже играл»: добавляет игру в список сыгранных."""
        game = self._resolve_game(chat_id, user_id, game_id)
        if game is None:
            return

        try:
            self._library.add_played(user_id, game)
        except GameHunterError as exc:
            # Игра уже добавлена или база недоступна — сообщаем и показываем карточку
            self.notify(chat_id, exc.user_message)
            self.show(chat_id, user_id, game_id)
            return

        logger.info("Пользователь %s отметил игру #%s как сыгранную", user_id, game_id)
        self.show(chat_id, user_id, game_id, notice=texts.GAME_ADDED_TO_PLAYED)

    def toggle_favorite(self, chat_id: int, user_id: int, game_id: int) -> None:
        """Кнопка «В избранное» / «Убрать из избранного»."""
        game = self._resolve_game(chat_id, user_id, game_id)
        if game is None:
            return

        try:
            _, added = self._library.toggle_favorite(user_id, game)
        except GameHunterError as exc:
            self.notify(chat_id, exc.user_message)
            self.show(chat_id, user_id, game_id)
            return

        notice = texts.GAME_ADDED_TO_FAVORITES if added else texts.GAME_REMOVED_FROM_FAVORITES
        self.show(chat_id, user_id, game_id, notice=notice)

    # ------------------------------------------------------------------ #
    def _resolve_game(self, chat_id: int, user_id: int, game_id: int) -> Optional[Game]:
        """Возвращает игру из текущего списка или догружает её из каталога."""
        context = self.context(user_id)
        game = context.game_by_id(game_id)
        if game is not None:
            return game

        try:
            details = self._games.get_game_details(game_id)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return None

        if details is None:
            self.show_error(chat_id, user_id, GameNotFoundError())
            return None
        return details.game

    def _safe_profile(self, user_id: int) -> Optional[UserProfile]:
        """Анкета пользователя или None, если базу прочитать не удалось."""
        try:
            return self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            logger.error("Не удалось прочитать анкету пользователя %s: %s", user_id, exc)
            return None
