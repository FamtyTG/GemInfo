"""Тесты сервиса поездок (Экраны 5–9)."""

from __future__ import annotations

from datetime import datetime

import pytest

from travelhunter.domain.exceptions import (
    EmptyNoteError,
    NoteTooLongError,
    TripNotFoundError,
)
from travelhunter.domain.services import TripService
from travelhunter.domain.services.trip_service import CITY_NAME_MAX_LENGTH
from tests.fakes import InMemoryTripRepository

USER_ID = 123456789


@pytest.fixture()
def repository() -> InMemoryTripRepository:
    return InMemoryTripRepository()


@pytest.fixture()
def service(repository: InMemoryTripRepository) -> TripService:
    return TripService(
        repository=repository,
        page_size=5,
        note_max_length=1000,
        now_provider=lambda: datetime(2026, 8, 10, 12, 0, 0),
    )


def test_create_trip_saves_user_city_and_date(service, repository):
    trip = service.create_trip(USER_ID, "Тула")

    assert trip.id == 1
    assert trip.tg_user_id == USER_ID
    assert trip.name == "Тула"
    assert trip.arrival_date == datetime(2026, 8, 10, 12, 0, 0)
    assert trip.note is None
    assert len(repository.trips) == 1


def test_create_trip_truncates_too_long_city_name(service):
    trip = service.create_trip(USER_ID, "Г" * 120)

    assert len(trip.name) == CITY_NAME_MAX_LENGTH


def test_create_trip_strips_spaces(service):
    assert service.create_trip(USER_ID, "  Калуга  ").name == "Калуга"


def test_history_is_sorted_from_new_to_old(service):
    service.create_trip(USER_ID, "Тула", arrival_date=datetime(2026, 8, 1))
    service.create_trip(USER_ID, "Калуга", arrival_date=datetime(2026, 8, 5))
    service.create_trip(USER_ID, "Орёл", arrival_date=datetime(2026, 8, 3))

    page = service.get_history(USER_ID)

    assert [trip.name for trip in page.trips] == ["Калуга", "Орёл", "Тула"]
    assert page.total_pages == 1
    assert page.has_previous is False
    assert page.has_next is False


def test_history_returns_only_current_user_trips(service):
    service.create_trip(USER_ID, "Тула")
    service.create_trip(987654321, "Сочи")

    page = service.get_history(USER_ID)

    assert [trip.name for trip in page.trips] == ["Тула"]


def test_history_pagination(service):
    for index in range(7):
        service.create_trip(USER_ID, f"Город {index}", arrival_date=datetime(2026, 8, index + 1))

    first_page = service.get_history(USER_ID, page=1)
    second_page = service.get_history(USER_ID, page=2)

    assert len(first_page.trips) == 5
    assert len(second_page.trips) == 2
    assert first_page.total_pages == 2
    assert first_page.has_next is True
    assert second_page.has_previous is True
    assert second_page.has_next is False


def test_history_page_number_is_normalized(service):
    service.create_trip(USER_ID, "Тула")

    assert service.get_history(USER_ID, page=-3).page == 1


def test_history_of_new_user_is_empty(service):
    page = service.get_history(USER_ID)

    assert page.is_empty is True
    assert page.trips == []


def test_get_trip_returns_existing_trip(service):
    created = service.create_trip(USER_ID, "Тула")

    assert service.get_trip(USER_ID, created.id) == created


def test_get_trip_raises_when_trip_not_found(service):
    with pytest.raises(TripNotFoundError):
        service.get_trip(USER_ID, 999)


def test_get_trip_raises_for_another_user_trip(service):
    created = service.create_trip(987654321, "Сочи")

    with pytest.raises(TripNotFoundError):
        service.get_trip(USER_ID, created.id)


def test_add_note_saves_text(service):
    created = service.create_trip(USER_ID, "Тула")

    trip = service.add_note(USER_ID, created.id, "Красивый город, приедем ещё!")

    assert trip.note == "Красивый город, приедем ещё!"
    assert trip.has_note is True


def test_add_note_strips_spaces(service):
    created = service.create_trip(USER_ID, "Тула")

    assert service.add_note(USER_ID, created.id, "  Заметка  ").note == "Заметка"


def test_add_note_rejects_too_long_text(service):
    created = service.create_trip(USER_ID, "Тула")

    with pytest.raises(NoteTooLongError) as exc_info:
        service.add_note(USER_ID, created.id, "с" * 1001)

    assert exc_info.value.user_message == (
        "Заметка не должна превышать 1000 символов. "
        "Сократите текст и попробуйте ещё раз."
    )
    assert service.get_trip(USER_ID, created.id).note is None


def test_add_note_accepts_exactly_1000_symbols(service):
    created = service.create_trip(USER_ID, "Тула")

    trip = service.add_note(USER_ID, created.id, "с" * 1000)

    assert len(trip.note) == 1000


def test_add_note_rejects_empty_text(service):
    created = service.create_trip(USER_ID, "Тула")

    with pytest.raises(EmptyNoteError):
        service.add_note(USER_ID, created.id, "   ")


def test_add_note_raises_when_trip_not_found(service):
    with pytest.raises(TripNotFoundError):
        service.add_note(USER_ID, 42, "Заметка")


def test_note_max_length_is_configurable(repository):
    service = TripService(repository=repository, note_max_length=10)
    created = service.create_trip(USER_ID, "Тула")

    with pytest.raises(NoteTooLongError):
        service.add_note(USER_ID, created.id, "12345678901")
