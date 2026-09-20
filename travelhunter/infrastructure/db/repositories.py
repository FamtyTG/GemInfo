"""Репозиторий поездок: доступ к таблице visited_cities через SQLAlchemy.

Класс реализует интерфейс ``TripRepository`` из доменного слоя, поэтому
бизнес-логика не знает, что данные лежат именно в PostgreSQL.
Все ошибки SQLAlchemy преобразуются в доменное исключение ``DatabaseError``.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from travelhunter.domain.entities import Trip, TripPage
from travelhunter.domain.exceptions import DatabaseError
from travelhunter.domain.interfaces import TripRepository
from travelhunter.infrastructure.db.database import Database
from travelhunter.infrastructure.db.models import VisitedCityORM

logger = logging.getLogger(__name__)


def to_entity(row: VisitedCityORM) -> Trip:
    """Преобразует ORM-строку в доменную сущность Trip."""
    return Trip(
        id=row.id,
        tg_user_id=row.tg_user_id,
        name=row.name,
        arrival_date=row.arrival_date,
        note=row.note,
    )


class SqlTripRepository(TripRepository):
    """Реализация хранилища поездок на SQLAlchemy."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ #
    def add(
        self,
        tg_user_id: int,
        city_name: str,
        arrival_date: Optional[datetime] = None,
    ) -> Trip:
        """Создаёт запись о поездке."""
        try:
            with self._database.session_scope() as session:
                row = VisitedCityORM(
                    tg_user_id=tg_user_id,
                    name=city_name,
                    arrival_date=arrival_date or datetime.now(),
                    note=None,
                )
                session.add(row)
                session.flush()  # получаем автоматически сгенерированный id
                return to_entity(row)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось сохранить поездку пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    def find_by_user(self, tg_user_id: int, limit: int, offset: int) -> List[Trip]:
        """Возвращает поездки пользователя от новых к старым."""
        stmt = (
            select(VisitedCityORM)
            .where(VisitedCityORM.tg_user_id == tg_user_id)
            .order_by(VisitedCityORM.arrival_date.desc(), VisitedCityORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            with self._database.session_scope() as session:
                rows = session.scalars(stmt).all()
                return [to_entity(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить поездки пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    def count_by_user(self, tg_user_id: int) -> int:
        """Возвращает количество поездок пользователя."""
        stmt = select(func.count()).select_from(VisitedCityORM).where(
            VisitedCityORM.tg_user_id == tg_user_id
        )
        try:
            with self._database.session_scope() as session:
                return int(session.scalar(stmt) or 0)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось посчитать поездки пользователя %s", tg_user_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    def find_by_id(self, trip_id: int, tg_user_id: int) -> Optional[Trip]:
        """Возвращает поездку, если она принадлежит указанному пользователю."""
        stmt = select(VisitedCityORM).where(
            VisitedCityORM.id == trip_id,
            VisitedCityORM.tg_user_id == tg_user_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                return to_entity(row) if row is not None else None
        except SQLAlchemyError as exc:
            logger.exception("Не удалось получить поездку #%s", trip_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    def update_note(self, trip_id: int, tg_user_id: int, note: str) -> Optional[Trip]:
        """Сохраняет заметку к поездке."""
        stmt = select(VisitedCityORM).where(
            VisitedCityORM.id == trip_id,
            VisitedCityORM.tg_user_id == tg_user_id,
        )
        try:
            with self._database.session_scope() as session:
                row = session.scalars(stmt).first()
                if row is None:
                    return None
                row.note = note
                session.flush()
                return to_entity(row)
        except SQLAlchemyError as exc:
            logger.exception("Не удалось сохранить заметку к поездке #%s", trip_id)
            raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    def page_by_user(self, tg_user_id: int, page: int, page_size: int) -> TripPage:
        """Возвращает страницу истории поездок (по ``page_size`` записей)."""
        page_size = max(1, page_size)
        page = max(1, page)

        total = self.count_by_user(tg_user_id)
        total_pages = max(1, math.ceil(total / page_size))
        page = min(page, total_pages)  # защита от выхода за границы

        offset = (page - 1) * page_size
        trips = self.find_by_user(tg_user_id=tg_user_id, limit=page_size, offset=offset)
        return TripPage(trips=list(trips), page=page, total_pages=total_pages)
