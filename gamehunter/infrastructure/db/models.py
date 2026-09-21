"""ORM-модели базы данных (SQLAlchemy 2.0).

В проекте три таблицы:

user_profiles   — анкета пользователя (возраст, интересы, платформы, регион);
played_games    — «во что я уже играл» + отзыв;
favorite_games  — избранное.

Во всех таблицах есть поле ``tg_user_id`` (Telegram ID пользователя), поэтому
каждый пользователь видит и изменяет только свои данные.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта."""


class UserProfileORM(Base):
    """Анкета пользователя (одна строка на Telegram-пользователя)."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, index=True
    )

    # Возраст пользователя (для возрастного фильтра подборки)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Интересы и платформы хранятся списками через запятую:
    # slugs — для запросов к каталогу, names — для показа пользователю
    genre_slugs: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    genre_names: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    platform_ids: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    platform_names: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # Регион, определённый по IP-адресу пользователя
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    region_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:  # pragma: no cover - только для отладки
        return (
            f"<UserProfileORM tg_user_id={self.tg_user_id} age={self.age} "
            f"genres={self.genre_slugs!r} country={self.country!r}>"
        )


class PlayedGameORM(Base):
    """Запись «во что я уже играл» с отзывом пользователя."""

    __tablename__ = "played_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    played_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    review: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        # одна и та же игра не может быть добавлена дважды
        UniqueConstraint("tg_user_id", "game_id", name="uq_played_games_user_game"),
        # список «во что я играл» выбирается по пользователю от новых к старым
        Index("ix_played_games_user_date", "tg_user_id", "played_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - только для отладки
        return (
            f"<PlayedGameORM id={self.id} tg_user_id={self.tg_user_id} "
            f"game_id={self.game_id} name={self.name!r}>"
        )


class FavoriteGameORM(Base):
    """Запись избранного."""

    __tablename__ = "favorite_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    __table_args__ = (
        UniqueConstraint("tg_user_id", "game_id", name="uq_favorite_games_user_game"),
        Index("ix_favorite_games_user_date", "tg_user_id", "added_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - только для отладки
        return (
            f"<FavoriteGameORM id={self.id} tg_user_id={self.tg_user_id} "
            f"game_id={self.game_id} name={self.name!r}>"
        )
