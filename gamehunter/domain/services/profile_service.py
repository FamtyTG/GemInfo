"""Сервис анкеты пользователя.

Бизнес-правила:
    * анкета создаётся автоматически при первом обращении;
    * возраст — целое число от 3 до 120 (используется для возрастного фильтра);
    * интересы — жанры каталога, платформы — PC/PlayStation/Xbox/Nintendo/…;
    * регион определяется по публичному IP-адресу через внешний сервис
      геолокации (страна, город, часовой пояс, валюта).
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Optional, Sequence

from gamehunter.domain.age_ratings import AgePolicy
from gamehunter.domain.entities import Genre, Platform, Region, UserProfile
from gamehunter.domain.exceptions import (
    GameHunterError,
    InvalidAgeError,
    InvalidIpError,
    PrivateIpError,
    RegionUnavailableError,
)
from gamehunter.domain.interfaces import IpLocationProvider, ProfileRepository

logger = logging.getLogger(__name__)

# Шаблон для поиска IP-адреса внутри произвольного текста пользователя
IPV4_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
IPV6_PATTERN = re.compile(r"\b[0-9a-fA-F:]{2,}::?[0-9a-fA-F:]*\b")


def extract_ip(raw_text: str) -> Optional[str]:
    """Достаёт IP-адрес из текста (пользователь может прислать его с пояснением)."""
    text = (raw_text or "").strip()
    if not text:
        return None

    match = IPV4_PATTERN.search(text) or IPV6_PATTERN.search(text)
    return match.group(0) if match else text


class ProfileService:
    """Работа с анкетой пользователя и его регионом."""

    def __init__(
        self,
        repository: ProfileRepository,
        ip_provider: IpLocationProvider,
        age_policy: Optional[AgePolicy] = None,
    ) -> None:
        self._repository = repository
        self._ip_provider = ip_provider
        self._age_policy = age_policy or AgePolicy()

    @property
    def age_policy(self) -> AgePolicy:
        return self._age_policy

    # ------------------------------------------------------------------ #
    # Анкета
    # ------------------------------------------------------------------ #
    def get_profile(self, tg_user_id: int) -> UserProfile:
        """Возвращает анкету пользователя (создаёт её при первом обращении)."""
        return self._repository.get_or_create(tg_user_id)

    def set_age(self, tg_user_id: int, raw_value: str) -> UserProfile:
        """Сохраняет возраст пользователя.

        :raises InvalidAgeError: значение не является допустимым возрастом.
        """
        text = (raw_value or "").strip()
        digits = re.sub(r"\D", "", text)

        # Знак «минус» отбрасывать нельзя: «-5» — это не возраст 5
        if not text or not digits or len(digits) > 3 or "-" in text:
            raise InvalidAgeError()

        age = int(digits)
        try:
            age = self._age_policy.validate_age(age)
        except ValueError as exc:
            logger.info("Недопустимый возраст %r: %s", raw_value, exc)
            raise InvalidAgeError() from exc

        profile = self._repository.get_or_create(tg_user_id)
        saved = self._repository.save(profile.with_age(age))
        logger.info("Возраст пользователя %s установлен: %s", tg_user_id, age)
        return saved

    def reset_age(self, tg_user_id: int) -> UserProfile:
        """Убирает возраст из анкеты (игры подбираются без возрастного фильтра)."""
        profile = self._repository.get_or_create(tg_user_id)
        return self._repository.save(profile.with_age(None))

    def set_genres(self, tg_user_id: int, genres: Sequence[Genre]) -> UserProfile:
        """Сохраняет интересы пользователя (выбранные жанры)."""
        profile = self._repository.get_or_create(tg_user_id)
        saved = self._repository.save(profile.with_genres(tuple(genres)))
        logger.info(
            "Интересы пользователя %s: %s", tg_user_id, saved.genre_slugs or "не указаны"
        )
        return saved

    def set_platforms(self, tg_user_id: int, platforms: Sequence[Platform]) -> UserProfile:
        """Сохраняет платформы пользователя."""
        profile = self._repository.get_or_create(tg_user_id)
        saved = self._repository.save(profile.with_platforms(tuple(platforms)))
        logger.info(
            "Платформы пользователя %s: %s", tg_user_id, saved.platform_ids or "не указаны"
        )
        return saved

    # ------------------------------------------------------------------ #
    # Регион по IP-адресу
    # ------------------------------------------------------------------ #
    def set_region_by_ip(self, tg_user_id: int, raw_ip: str) -> UserProfile:
        """Определяет регион по IP-адресу и сохраняет его в анкете.

        :raises InvalidIpError: адрес некорректен;
        :raises PrivateIpError: адрес локальный (не публичный);
        :raises RegionUnavailableError: сервис геолокации недоступен.
        """
        ip = self.validate_ip(raw_ip)

        try:
            region: Optional[Region] = self._ip_provider.locate(ip)
        except GameHunterError as exc:
            logger.error("Ошибка определения региона по IP %s: %s", ip, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при определении региона по IP")
            raise RegionUnavailableError("ipapi", str(exc)) from exc

        if region is None or not region.is_known:
            raise RegionUnavailableError("ipapi", "region not found")

        profile = self._repository.get_or_create(tg_user_id)
        saved = self._repository.save(profile.with_region(region))
        logger.info(
            "Регион пользователя %s по IP %s: %s", tg_user_id, ip, saved.region_text
        )
        return saved

    def reset_region(self, tg_user_id: int) -> UserProfile:
        """Удаляет сохранённый регион из анкеты."""
        profile = self._repository.get_or_create(tg_user_id)
        return self._repository.save(profile.with_region(None))

    @staticmethod
    def validate_ip(raw_ip: str) -> str:
        """Проверяет IP-адрес, присланный пользователем.

        :raises InvalidIpError: строка не является IP-адресом;
        :raises PrivateIpError: адрес из локальной сети.
        """
        candidate = extract_ip(raw_ip)
        if not candidate:
            raise InvalidIpError()

        try:
            address = ipaddress.ip_address(candidate)
        except ValueError as exc:
            logger.info("Некорректный IP-адрес %r: %s", raw_ip, exc)
            raise InvalidIpError() from exc

        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            logger.info("Локальный IP-адрес %r — геолокация невозможна", candidate)
            raise PrivateIpError()

        return str(address)
