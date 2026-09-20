"""Подключение к базе данных и управление сессиями SQLAlchemy.

По техническому заданию используется PostgreSQL (драйвер psycopg2).
Для локальной разработки без PostgreSQL поддерживается SQLite —
достаточно указать ``DATABASE_URL=sqlite:///travelhunter.db``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from travelhunter.domain.exceptions import DatabaseError
from travelhunter.infrastructure.db.models import Base

logger = logging.getLogger(__name__)


class Database:
    """Обёртка над движком SQLAlchemy и фабрикой сессий."""

    def __init__(self, url: str, echo: bool = False) -> None:
        self._url = url
        engine_kwargs: dict = {"echo": echo, "future": True}
        if url.startswith("sqlite"):
            # SQLite по умолчанию разрешает работу только из создавшего потока,
            # а telebot обрабатывает апдейты в пуле потоков.
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # Для PostgreSQL полезно проверять соединение перед выдачей из пула.
            engine_kwargs["pool_pre_ping"] = True

        self._engine: Engine = create_engine(url, **engine_kwargs)
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True
        )
        logger.info("Движок базы данных создан: %s", self.safe_url)

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def safe_url(self) -> str:
        """Строка подключения без пароля — её не страшно писать в логи."""
        try:
            return self._engine.url.render_as_string(hide_password=True)
        except Exception:  # noqa: BLE001
            return "<database url>"

    def create_all(self) -> None:
        """Создаёт таблицы базы данных, если их ещё нет."""
        try:
            Base.metadata.create_all(self._engine)
            logger.info("Таблицы базы данных созданы/проверены")
        except SQLAlchemyError as exc:
            logger.exception("Не удалось создать таблицы базы данных")
            raise DatabaseError(str(exc)) from exc

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Контекст работы с сессией: commit при успехе, rollback при ошибке."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Закрывает пул соединений (используется при остановке бота)."""
        self._engine.dispose()
