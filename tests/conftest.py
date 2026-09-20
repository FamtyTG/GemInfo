"""Общие фикстуры pytest для тестов проекта TravelHunter."""

from __future__ import annotations

from typing import Iterator

import pytest

from travelhunter.infrastructure.db import Database, SqlTripRepository


@pytest.fixture()
def database(tmp_path) -> Iterator[Database]:
    """Локальная тестовая база данных SQLite (структура как в PostgreSQL)."""
    db_file = tmp_path / "travelhunter_test.db"
    db = Database(f"sqlite:///{db_file}")
    db.create_all()
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture()
def trip_repository(database: Database) -> SqlTripRepository:
    """Репозиторий поездок поверх тестовой базы данных."""
    return SqlTripRepository(database)
