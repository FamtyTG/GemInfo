"""Репозитории: доступ к таблицам базы данных через SQLAlchemy.

Классы реализуют интерфейсы ``ProfileRepository`` и ``LibraryRepository``
из доменного слоя, поэтому бизнес-логика не знает, что данные лежат именно
в PostgreSQL. Все ошибки SQLAlchemy преобразуются в ``DatabaseError``.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from gamehunter.domain.entities import (
    FavoriteGame,
    Game,
    LibraryPage,
    PlayedGame,
    Region,
    UserProfile,
)
from gamehunter.domain.exceptions import DatabaseError
from gamehunter.domain.interfaces import LibraryRepository, ProfileRepository
from gamehunter.infrastructure.db.database import Database
from gamehunter.infrastructure.db.models import (
    FavoriteGameORM,
    PlayedGameORM,
    UserProfileORM,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- #
# Преобразование «список в строке» <-> кортеж значений
# ---------------------------------------------------------------------- #
def _join(values: Sequence[object]) -> str:
    return ",".join(str(value) for value in values if str(value))


def _split_str(text: Optional[str]) -> Tuple[str, ...]:
    if not text:
        return ()
    return tuple(part for part in (item.strip() for item in text.split(",")) if part)


def _split_int(text: Optional[str]) -> Tuple[int, ...]:
    result: List[int] = []
    for part in _split_str(text):
        try:
            result.append(int(part))
        except ValueError:
            logger.warning("Пропущено нечисловое значение платформы в анкете: %r", part)
    return tuple(result)


def _to_profile(row: UserProfileORM) -> UserProfile:
    """Преобразует ORM-строку анкеты в доменную сущность."""
    region: Optional[Region] = None
    if row.country or row.city or row.country_code:
        region = Region(
            ip=row.ip_address or "",
            country=row.country or "",
            country_code=row.country_code or "",
            city=row.city or "",
            region_name=row.region_name or "",
            timezone=row.timezone or "",
            currency=row.currency or "",
            latitude=row.latitude,
            longitude=row.longitude,
        )

    return UserProfile(
        tg_user_id=row.tg_user_id,
        age=row.age,
        genre_slugs=_split_str(row.genre_slugs),
        genre_names=_split_str(row.genre_names),
        platform_ids=_split_int(row.platform_ids),
        platform_names=_split_str(row.platform_names),
        region=region,
        updated_at=row.updated_at,
    )


def _to_played(row: PlayedGameORM) -> PlayedGame:
    """Преобразует ORM-строку в запись о сыгранной игре."""
    return PlayedGame(
        id=row.id,
        tg_user_id=row.tg_user_id,
        game_id=row.game_id,
        slug=row.slug or "",
        name=row.name,
        played_at=row.played_at,
        review=row.review,
        image_url=row.image_url,
    )


def _to_favorite(row: FavoriteGameORM) -> FavoriteGame:
    """Преобразует ORM-строку в запись избранного."""
    return FavoriteGame(
        id=row.id,
        tg_user_id=row.tg_user_id,
        game_id=row.game_id,
        slug=row.slug or "",
        name=row.name,
        added_at=row.added_at,
        image_url=row.image_url,
    )


# ---------------------------------------------------------------------- #
# Анкета пользователя
# ---------------------------------------------------------------------- #
class SqlProfileRepository(ProfileRepository):
    """Хранилище анкет пользователей (таблица user_profiles)."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get_or_create(self, tg_user_id: int) -> UserProfile:
        """Возвращает анкету пользователя, создавая её при первом обращении."""
        try:
            with self._database.session_scope() as session:
                row = self._find(session, tg_user_id)
                if row is None:
                    row = UserProfileORM(tg_user_id=tg_user_id, updated_at=datetime.now())
                    session.add(row)
                    session.flush()
                    logger.info("Создана анкета пользователя %s", tg_user_id)
                return _to_profile(row)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить анкету пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    def save(self, profile: UserProfile) -> UserProfile:
        """Сохраняет изменения анкеты."""
        region = profile.region
        try:
            with self._database.session_scope() as session:
                row = self._find(session, profile.tg_user_id)
                if row is None:
                    row = UserProfileORM(tg_user_id=profile.tg_user_id)
                    session.add(row)

                row.age = profile.age
                row.genre_slugs = _join(profile.genre_slugs)
                row.genre_names = _join(profile.genre_names)
                row.platform_ids = _join(profile.platform_ids)
                row.platform_names = _join(profile.platform_names)
                row.ip_address = region.ip if region else None
                row.country = region.country if region else None
                row.country_code = region.country_code if region else None
                row.city = region.city if region else None
                row.region_name = region.region_name if region else None
                row.timezone = region.timezone if region else None
                row.currency = region.currency if region else None
                row.latitude = region.latitude if region else None
                row.longitude = region.longitude if region else None
                row.updated_at = datetime.now()

                session.flush()
                return _to_profile(row)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось сохранить анкету пользователя %s", profile.tg_user_id)
            raise DatabaseError(str(exc)) from exc

    @staticmethod
    def _find(session, tg_user_id: int) -> Optional[UserProfileORM]:
        stmt = select(UserProfileORM).where(UserProfileORM.tg_user_id == tg_user_id)
        return session.scalars(stmt).first()


# ---------------------------------------------------------------------- #
# Библиотека: сыгранные игры и избранное
# ---------------------------------------------------------------------- #
class SqlLibraryRepository(LibraryRepository):
    """Хранилище библиотеки пользователя (played_games, favorite_games)."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------- «Во что я играл» ------------------------- #
    def add_played(
        self, tg_user_id: int, game: Game, played_at: Optional[datetime] = None
    ) -> PlayedGame:
        """Добавляет игру в список сыгранных."""
        try:
            with self._database.session_scope() as session:
                row = PlayedGameORM(
                    tg_user_id=tg_user_id,
                    game_id=game.id,
                    slug=game.slug or "",
                    name=game.name,
                    image_url=game.image_url,
                    played_at=played_at or datetime.now(),
                    review=None,
                )
                session.add(row)
                session.flush()
                return _to_played(row)
        except SQLAlchemyError as exc:
            logger.exception(
                "Не удалось добавить игру «%s» в список сыгранных пользователя %s",
                game.name,
                tg_user_id,
            )
            raise DatabaseError(str(exc)) from exc

    def find_played_by_id(self, record_id: int, tg_user_id: int) -> Optional[PlayedGame]:
        stmt = select(PlayedGameORM).where(
            PlayedGameORM.id == record_id,
            PlayedGameORM.tg_user_id == tg_user_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                return _to_played(row) if row is not None else None
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить запись #%s", record_id)
            raise DatabaseError(str(exc)) from exc

    def update_review(
        self, record_id: int, tg_user_id: int, review: str
    ) -> Optional[PlayedGame]:
        """Сохраняет отзыв к сыгранной игре."""
        stmt = select(PlayedGameORM).where(
            PlayedGameORM.id == record_id,
            PlayedGameORM.tg_user_id == tg_user_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                if row is None:
                    return None
                row.review = review
                session.flush()
                return _to_played(row)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось сохранить отзыв к записи #%s", record_id)
            raise DatabaseError(str(exc)) from exc

    def delete_played(self, record_id: int, tg_user_id: int) -> bool:
        """Удаляет запись из списка сыгранных."""
        stmt = select(PlayedGameORM).where(
            PlayedGameORM.id == record_id,
            PlayedGameORM.tg_user_id == tg_user_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            logger.exception("Не удалось удалить запись #%s", record_id)
            raise DatabaseError(str(exc)) from exc

    def played_game_ids(self, tg_user_id: int) -> Set[int]:
        """Идентификаторы игр, в которые пользователь уже играл."""
        stmt = select(PlayedGameORM.game_id).where(PlayedGameORM.tg_user_id == tg_user_id)
        try:
            with self._database.session_scope() as session:
                return {int(game_id) for game_id in session.scalars(stmt).all()}
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить сыгранные игры пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    def has_played(self, tg_user_id: int, game_id: int) -> bool:
        stmt = select(func.count()).select_from(PlayedGameORM).where(
            PlayedGameORM.tg_user_id == tg_user_id,
            PlayedGameORM.game_id == game_id,
        )
        try:
            with self._database.session_scope() as session:
                return int(session.scalar(stmt) or 0) > 0
        except SQLAlchemyError as exc:
            logger.exception("Не удалось проверить игру #%s у пользователя %s", game_id, tg_user_id)
            raise DatabaseError(str(exc)) from exc

    def page_played(
        self, tg_user_id: int, page: int, page_size: int
    ) -> LibraryPage[PlayedGame]:
        """Страница списка сыгранных игр (от новых к старым)."""
        page, page_size = self._normalize_page(page, page_size)

        count_stmt = (
            select(func.count())
            .select_from(PlayedGameORM)
            .where(PlayedGameORM.tg_user_id == tg_user_id)
        )
        try:
            with self._database.session_scope() as session:
                total = int(session.scalar(count_stmt) or 0)
                total_pages = max(1, math.ceil(total / page_size))
                page = min(page, total_pages)  # защита от выхода за границы
                items_stmt = (
                    select(PlayedGameORM)
                    .where(PlayedGameORM.tg_user_id == tg_user_id)
                    .order_by(PlayedGameORM.played_at.desc(), PlayedGameORM.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
                rows = session.scalars(items_stmt).all()
                return LibraryPage(
                    items=[_to_played(row) for row in rows],
                    page=page,
                    total_pages=total_pages,
                )
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить список сыгранных игр пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------ Избранное ------------------------------ #
    def add_favorite(self, tg_user_id: int, game: Game) -> FavoriteGame:
        """Добавляет игру в избранное."""
        try:
            with self._database.session_scope() as session:
                row = FavoriteGameORM(
                    tg_user_id=tg_user_id,
                    game_id=game.id,
                    slug=game.slug or "",
                    name=game.name,
                    image_url=game.image_url,
                    added_at=datetime.now(),
                )
                session.add(row)
                session.flush()
                return _to_favorite(row)
        except SQLAlchemyError as exc:
            logger.exception(
                "Не удалось добавить игру «%s» в избранное пользователя %s",
                game.name,
                tg_user_id,
            )
            raise DatabaseError(str(exc)) from exc

    def remove_favorite(self, tg_user_id: int, game_id: int) -> bool:
        """Убирает игру из избранного."""
        stmt = select(FavoriteGameORM).where(
            FavoriteGameORM.tg_user_id == tg_user_id,
            FavoriteGameORM.game_id == game_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            logger.exception("Не удалось убрать игру #%s из избранного", game_id)
            raise DatabaseError(str(exc)) from exc

    def is_favorite(self, tg_user_id: int, game_id: int) -> bool:
        stmt = select(func.count()).select_from(FavoriteGameORM).where(
            FavoriteGameORM.tg_user_id == tg_user_id,
            FavoriteGameORM.game_id == game_id,
        )
        try:
            with self._database.session_scope() as session:
                return int(session.scalar(stmt) or 0) > 0
        except SQLAlchemyError as exc:
            logger.exception("Не удалось проверить избранное пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    def page_favorites(
        self, tg_user_id: int, page: int, page_size: int
    ) -> LibraryPage[FavoriteGame]:
        """Страница списка избранных игр (от новых к старым)."""
        page, page_size = self._normalize_page(page, page_size)

        count_stmt = (
            select(func.count()).select_from(FavoriteGameORM).where(
                FavoriteGameORM.tg_user_id == tg_user_id
            )
        )
        try:
            with self._database.session_scope() as session:
                total = int(session.scalar(count_stmt) or 0)
                total_pages = max(1, math.ceil(total / page_size))
                page = min(page, total_pages)
                rows = session.scalars(
                    select(FavoriteGameORM)
                    .where(FavoriteGameORM.tg_user_id == tg_user_id)
                    .order_by(FavoriteGameORM.added_at.desc(), FavoriteGameORM.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                ).all()
                return LibraryPage(
                    items=[_to_favorite(row) for row in rows],
                    page=page,
                    total_pages=total_pages,
                )
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить избранное пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------ Служебное ------------------------------ #
    @staticmethod
    def _normalize_page(page: int, page_size: int) -> Tuple[int, int]:
        return max(1, int(page)), max(1, int(page_size))
