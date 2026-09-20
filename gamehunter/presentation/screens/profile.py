"""Экран 9 «Моя анкета» и его режимы: возраст, интересы, платформы, регион по IP."""

from __future__ import annotations

import logging
from typing import List, Optional

from gamehunter.domain.entities import Genre, UserProfile
from gamehunter.domain.exceptions import (
    GameHunterError,
    InvalidAgeError,
    InvalidIpError,
)
from gamehunter.domain.services import GameService, ProfileService
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import StateStorage, UserContext

logger = logging.getLogger(__name__)


class ProfileScreen(BaseScreen):
    """Экран 9. Анкета пользователя (возраст, интересы, платформы, регион)."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        profile_service: ProfileService,
    ) -> None:
        super().__init__(gateway, storage)
        self._profiles = profile_service

    def show(self, chat_id: int, user_id: int, notice: str = "") -> None:
        logger.debug("Экран 9 «Моя анкета» для пользователя %s", user_id)
        try:
            profile = self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self.save(user_id, self.context(user_id).at_profile())

        message = texts.format_profile(profile)
        if notice:
            message = f"{notice}\n\n{message}"

        self.send(
            chat_id,
            message,
            reply_markup=keyboards.profile_keyboard(
                has_age=profile.age is not None,
                has_region=profile.region is not None and profile.region.is_known,
            ),
        )

    def reset_age(self, chat_id: int, user_id: int) -> None:
        """Убирает возраст из анкеты."""
        try:
            self._profiles.reset_age(user_id)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return
        self.show(chat_id, user_id, notice=texts.PROFILE_AGE_RESET)

    def reset_region(self, chat_id: int, user_id: int) -> None:
        """Убирает регион из анкеты."""
        try:
            self._profiles.reset_region(user_id)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return
        self.show(chat_id, user_id, notice=texts.PROFILE_REGION_RESET)


class AgeInputScreen(BaseScreen):
    """Экран 9а. Ввод возраста пользователя."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        profile_service: ProfileService,
        profile_screen: ProfileScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._profiles = profile_service
        self._profile_screen = profile_screen

    def show(self, chat_id: int, user_id: int, error_text: str = "") -> None:
        logger.debug("Экран 9а «Ввод возраста» для пользователя %s", user_id)
        self.save(user_id, self.context(user_id).at_age_input())

        message = texts.PROFILE_AGE_PROMPT
        if error_text:
            message = f"{error_text}\n\n{message}"
        self.send(chat_id, message, reply_markup=keyboards.hide_keyboard())

    def handle_age(self, chat_id: int, user_id: int, raw_value: str) -> None:
        """Сохраняет возраст из текстового сообщения."""
        try:
            self._profiles.set_age(user_id, raw_value)
        except InvalidAgeError as exc:
            logger.info("Недопустимый возраст %r от пользователя %s", raw_value, user_id)
            self.show(chat_id, user_id, error_text=exc.user_message)
            return
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self._profile_screen.show(chat_id, user_id, notice=texts.PROFILE_AGE_SAVED)


class ProfileGenresScreen(BaseScreen):
    """Экран 9б. Выбор интересов (жанров) для анкеты."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        profile_service: ProfileService,
        profile_screen: ProfileScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._profiles = profile_service
        self._profile_screen = profile_screen

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 9б «Интересы анкеты» для пользователя %s", user_id)
        genres = self._genres(chat_id, user_id)
        if genres is None:
            return

        profile = self._profile_of(user_id)
        context = self.context(user_id).at_profile_genres(genres, profile.genre_slugs)
        self.save(user_id, context)
        self._render(chat_id, context)

    def toggle(self, chat_id: int, user_id: int, slug: str) -> None:
        context = self.context(user_id)
        if not context.genre_catalog:
            self.show(chat_id, user_id)
            return

        updated = context.toggle_profile_genre(slug)
        self.save(user_id, updated)
        self._render(chat_id, updated)

    def save_selection(self, chat_id: int, user_id: int) -> None:
        """Кнопка «Сохранить»: записывает выбранные жанры в анкету."""
        context = self.context(user_id)
        by_slug = {genre.slug: genre for genre in context.genre_catalog}
        selected = [by_slug[slug] for slug in context.profile_genres if slug in by_slug]

        try:
            self._profiles.set_genres(user_id, selected)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self._profile_screen.show(chat_id, user_id, notice=texts.PROFILE_GENRES_SAVED)

    # ------------------------------------------------------------------ #
    def _render(self, chat_id: int, context: "UserContext") -> None:
        self.send(
            chat_id,
            texts.format_genres_selection(
                context.genre_catalog,
                context.profile_genres,
                texts.PROFILE_GENRES_TITLE,
                texts.PROFILE_GENRES_SAVED_HINT,
            ),
            reply_markup=keyboards.profile_genres_keyboard(
                context.genre_catalog, context.profile_genres
            ),
        )

    def _genres(self, chat_id: int, user_id: int) -> Optional[List[Genre]]:
        try:
            return self._games.get_genres()[: self._games.max_genres]
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return None

    def _profile_of(self, user_id: int) -> UserProfile:
        try:
            return self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            logger.error("Не удалось прочитать анкету пользователя %s: %s", user_id, exc)
            return UserProfile(tg_user_id=user_id)


class ProfilePlatformsScreen(BaseScreen):
    """Экран 9в. Выбор платформ, на которых играет пользователь."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        game_service: GameService,
        profile_service: ProfileService,
        profile_screen: ProfileScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._games = game_service
        self._profiles = profile_service
        self._profile_screen = profile_screen

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 9в «Платформы анкеты» для пользователя %s", user_id)
        try:
            platforms = self._games.get_platforms()
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        profile = self._profile_of(user_id)
        context = self.context(user_id).at_profile_platforms(platforms, profile.platform_ids)
        self.save(user_id, context)
        self._render(chat_id, context)

    def toggle(self, chat_id: int, user_id: int, platform_id: int) -> None:
        context = self.context(user_id)
        if not context.platform_catalog:
            self.show(chat_id, user_id)
            return

        updated = context.toggle_profile_platform(platform_id)
        self.save(user_id, updated)
        self._render(chat_id, updated)

    def save_selection(self, chat_id: int, user_id: int) -> None:
        """Кнопка «Сохранить»: записывает выбранные платформы в анкету."""
        context = self.context(user_id)
        by_id = {platform.id: platform for platform in context.platform_catalog}
        selected = [by_id[pid] for pid in context.profile_platforms if pid in by_id]

        try:
            self._profiles.set_platforms(user_id, selected)
        except GameHunterError as exc:
            self.show_error(chat_id, user_id, exc)
            return

        self._profile_screen.show(chat_id, user_id, notice=texts.PROFILE_PLATFORMS_SAVED)

    # ------------------------------------------------------------------ #
    def _render(self, chat_id: int, context: "UserContext") -> None:
        selected_names = [
            platform.name
            for platform in context.platform_catalog
            if platform.id in context.profile_platforms
        ]
        hint = (
            texts.PROFILE_PLATFORMS_SELECTED.format(", ".join(selected_names))
            if selected_names
            else texts.PROFILE_PLATFORMS_NONE
        )
        self.send(
            chat_id,
            f"{texts.PROFILE_PLATFORMS_TITLE}\n\n{hint}",
            reply_markup=keyboards.platforms_keyboard(
                context.platform_catalog, context.profile_platforms
            ),
        )

    def _profile_of(self, user_id: int) -> UserProfile:
        try:
            return self._profiles.get_profile(user_id)
        except GameHunterError as exc:
            logger.error("Не удалось прочитать анкету пользователя %s: %s", user_id, exc)
            return UserProfile(tg_user_id=user_id)


class RegionInputScreen(BaseScreen):
    """Экран 9г. Определение региона по IP-адресу пользователя."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        profile_service: ProfileService,
        profile_screen: ProfileScreen,
    ) -> None:
        super().__init__(gateway, storage)
        self._profiles = profile_service
        self._profile_screen = profile_screen

    def show(self, chat_id: int, user_id: int, error_text: str = "") -> None:
        logger.debug("Экран 9г «Ввод IP-адреса» для пользователя %s", user_id)
        self.save(user_id, self.context(user_id).at_ip_input())

        message = texts.PROFILE_IP_PROMPT
        if error_text:
            message = f"{error_text}\n\n{message}"
        self.send(chat_id, message, reply_markup=keyboards.hide_keyboard())

    def handle_ip(self, chat_id: int, user_id: int, raw_value: str) -> None:
        """Определяет регион по присланному IP-адресу и сохраняет его в анкете."""
        try:
            profile = self._profiles.set_region_by_ip(user_id, raw_value)
        except InvalidIpError as exc:
            # Некорректный или локальный адрес — просим прислать другой
            logger.info("Некорректный IP от пользователя %s: %r", user_id, raw_value)
            self.show(chat_id, user_id, error_text=exc.user_message)
            return
        except GameHunterError as exc:
            logger.error("Не удалось определить регион пользователя %s: %s", user_id, exc)
            self._profile_screen.show(chat_id, user_id, notice=exc.user_message)
            return

        region = profile.region
        notice = texts.PROFILE_REGION_SAVED
        if region is not None and region.is_known:
            notice = f"{notice}\n{region.title}"
        self._profile_screen.show(chat_id, user_id, notice=notice)
