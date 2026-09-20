"""Тесты репозитория поездок (SQLAlchemy + таблица visited_cities).

Тесты выполняются на SQLite, структура таблицы идентична PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect

from travelhunter.infrastructure.db import Database, VisitedCityORM
from travelhunter.infrastructure.db.repositories import SqlTripRepository

USER_ID = 111111111
OTHER_USER_ID = 222222222


def test_visited_cities_table_structure(database: Database):
    inspector = inspect(database.engine)

    assert "visited_cities" in inspector.get_table_names()

    columns = {column["name"]: column for column in inspector.get_columns("visited_cities")}
    # драйвер может вернуть primary_key как True или как 1
    assert bool(columns["id"]["primary_key"]) is True
    assert columns["tg_user_id"]["nullable"] is False
    assert columns["name"]["nullable"] is False
    assert columns["arrival_date"]["nullable"] is False
    assert columns["note"]["nullable"] is True
    assert str(columns["name"]["type"]).lower().startswith("varchar(50)")
    assert str(columns["note"]["type"]).lower().startswith("varchar(1000)")


def test_add_creates_row_with_generated_id(trip_repository: SqlTripRepository):
    trip = trip_repository.add(USER_ID, "Тула", arrival_date=datetime(2026, 8, 10, 9, 30))

    assert trip.id is not None
    assert trip.tg_user_id == USER_ID
    assert trip.name == "Тула"
    assert trip.arrival_date == datetime(2026, 8, 10, 9, 30)
    assert trip.note is None


def test_add_uses_current_date_by_default(trip_repository: SqlTripRepository):
    before = datetime.now()

    trip = trip_repository.add(USER_ID, "Калуга")

    assert before <= trip.arrival_date <= datetime.now()


def test_find_by_user_sorted_from_new_to_old(trip_repository: SqlTripRepository):
    trip_repository.add(USER_ID, "Старый", arrival_date=datetime(2026, 1, 1))
    trip_repository.add(USER_ID, "Новый", arrival_date=datetime(2026, 8, 1))
    trip_repository.add(USER_ID, "Средний", arrival_date=datetime(2026, 5, 1))

    trips = trip_repository.find_by_user(USER_ID, limit=10, offset=0)

    assert [trip.name for trip in trips] == ["Новый", "Средний", "Старый"]


def test_find_by_user_respects_limit_and_offset(trip_repository: SqlTripRepository):
    for index in range(7):
        trip_repository.add(USER_ID, f"Город {index}", arrival_date=datetime(2026, 8, index + 1))

    trips = trip_repository.find_by_user(USER_ID, limit=5, offset=5)

    assert len(trips) == 2
    # сортировка от новых к старым: первыми созданы самые «старые» даты
    assert [trip.name for trip in trips] == ["Город 1", "Город 0"]


def test_find_by_user_returns_only_own_trips(trip_repository: SqlTripRepository):
    trip_repository.add(USER_ID, "Тула")
    trip_repository.add(OTHER_USER_ID, "Сочи")

    trips = trip_repository.find_by_user(USER_ID, limit=10, offset=0)

    assert [trip.name for trip in trips] == ["Тула"]


def test_count_by_user(trip_repository: SqlTripRepository):
    assert trip_repository.count_by_user(USER_ID) == 0

    trip_repository.add(USER_ID, "Тула")
    trip_repository.add(USER_ID, "Калуга")
    trip_repository.add(OTHER_USER_ID, "Сочи")

    assert trip_repository.count_by_user(USER_ID) == 2


def test_find_by_id(trip_repository: SqlTripRepository):
    created = trip_repository.add(USER_ID, "Тула")

    found = trip_repository.find_by_id(created.id, USER_ID)

    assert found is not None
    assert found.id == created.id
    assert found.name == "Тула"


def test_find_by_id_returns_none_for_missing_id(trip_repository: SqlTripRepository):
    assert trip_repository.find_by_id(999, USER_ID) is None


def test_find_by_id_returns_none_for_another_user(trip_repository: SqlTripRepository):
    created = trip_repository.add(USER_ID, "Тула")

    assert trip_repository.find_by_id(created.id, OTHER_USER_ID) is None


def test_update_note_persists_value(trip_repository: SqlTripRepository):
    created = trip_repository.add(USER_ID, "Тула")

    updated = trip_repository.update_note(created.id, USER_ID, "Очень понравилось!")

    assert updated is not None
    assert updated.note == "Очень понравилось!"
    # значение действительно записано в базу, а не только в объект
    assert trip_repository.find_by_id(created.id, USER_ID).note == "Очень понравилось!"


def test_update_note_returns_none_for_missing_trip(trip_repository: SqlTripRepository):
    assert trip_repository.update_note(999, USER_ID, "Заметка") is None


def test_page_by_user_pagination(trip_repository: SqlTripRepository):
    for index in range(12):
        trip_repository.add(USER_ID, f"Город {index}", arrival_date=datetime(2026, 8, index + 1))

    first = trip_repository.page_by_user(USER_ID, page=1, page_size=5)
    third = trip_repository.page_by_user(USER_ID, page=3, page_size=5)

    assert first.total_pages == 3
    assert len(first.trips) == 5
    assert len(third.trips) == 2
    assert third.page == 3


def test_page_by_user_clamps_page_number(trip_repository: SqlTripRepository):
    trip_repository.add(USER_ID, "Тула")

    page = trip_repository.page_by_user(USER_ID, page=99, page_size=5)

    assert page.page == 1
    assert page.total_pages == 1
    assert len(page.trips) == 1


def test_page_by_user_for_empty_history(trip_repository: SqlTripRepository):
    page = trip_repository.page_by_user(USER_ID, page=1, page_size=5)

    assert page.is_empty is True
    assert page.total_pages == 1


def test_repository_works_with_big_telegram_id(database: Database):
    """tg_user_id — bigint: должны помещаться большие идентификаторы Telegram."""
    repository = SqlTripRepository(database)
    big_id = 9_007_199_254_740_991

    trip = repository.add(big_id, "Тула")

    assert repository.find_by_id(trip.id, big_id) is not None


def test_orm_model_repr(database: Database):
    row = VisitedCityORM(
        id=1, tg_user_id=USER_ID, name="Тула", arrival_date=datetime(2026, 8, 10)
    )

    assert "Тула" in repr(row)


def test_database_create_all_is_idempotent(tmp_path):
    """Повторное создание таблиц не должно вызывать ошибку."""
    db = Database(f"sqlite:///{tmp_path / 'db.sqlite'}")

    db.create_all()
    db.create_all()

    assert "visited_cities" in inspect(db.engine).get_table_names()
    db.dispose()


def test_database_raises_database_error_on_bad_url():
    from travelhunter.domain.exceptions import DatabaseError

    db = Database("postgresql+psycopg2://user:pass@127.0.0.1:1/missing")

    with pytest.raises(DatabaseError):
        db.create_all()
    db.dispose()
