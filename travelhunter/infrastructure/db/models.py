"""ORM-модели базы данных (SQLAlchemy 2.0).

Таблица visited_cities хранит поездки пользователей Telegram-бота:

    id            int          первичный ключ, генерируется автоматически;
    tg_user_id    bigint       Telegram ID пользователя;
    name          varchar(50)  название города;
    arrival_date  datetime     дата поездки (при создании — текущая дата);
    note          varchar(1000) заметка о поездке (необязательное поле).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта."""


class VisitedCityORM(Base):
    """Поездка пользователя (строка таблицы visited_cities)."""

    __tablename__ = "visited_cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    arrival_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        # История поездок всегда выбирается по пользователю от новых к старым
        Index("ix_visited_cities_user_date", "tg_user_id", "arrival_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - только для отладки
        return (
            f"<VisitedCityORM id={self.id} tg_user_id={self.tg_user_id} "
            f"name={self.name!r} arrival_date={self.arrival_date:%d.%m.%Y}>"
        )
