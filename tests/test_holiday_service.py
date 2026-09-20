"""Тесты сервиса праздников (Экран 3)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from travelhunter.domain.exceptions import HolidaysUnavailableError
from travelhunter.domain.services import HolidayService
from tests.fakes import FakeHolidaysProvider, make_holiday


@pytest.fixture()
def today() -> date:
    return date(2026, 8, 10)


def build_service(holidays, **kwargs) -> HolidayService:
    provider = FakeHolidaysProvider(holidays=holidays)
    return HolidayService(provider=provider, **kwargs), provider


def test_returns_only_holidays_within_seven_days(today):
    holidays = [
        make_holiday("Вчера", today - timedelta(days=1)),
        make_holiday("Сегодня", today),
        make_holiday("Через 3 дня", today + timedelta(days=3)),
        make_holiday("Через 7 дней", today + timedelta(days=7)),
        make_holiday("Через 8 дней", today + timedelta(days=8)),
    ]
    service, _ = build_service(holidays)

    result = service.get_upcoming_holidays(today=today)

    assert [holiday.name for holiday in result] == [
        "Сегодня",
        "Через 3 дня",
        "Через 7 дней",
    ]


def test_sorted_by_date(today):
    holidays = [
        make_holiday("Позже", today + timedelta(days=5)),
        make_holiday("Раньше", today + timedelta(days=1)),
    ]
    service, _ = build_service(holidays)

    result = service.get_upcoming_holidays(today=today)

    assert [holiday.name for holiday in result] == ["Раньше", "Позже"]


def test_returns_at_most_five_holidays(today):
    holidays = [make_holiday(f"Праздник {i}", today + timedelta(days=1)) for i in range(8)]
    service, _ = build_service(holidays)

    result = service.get_upcoming_holidays(today=today)

    assert len(result) == 5


def test_max_holidays_is_configurable(today):
    holidays = [make_holiday(f"Праздник {i}", today + timedelta(days=1)) for i in range(8)]
    service, _ = build_service(holidays, max_holidays=3)

    assert len(service.get_upcoming_holidays(today=today)) == 3


def test_returns_empty_list_when_no_holidays(today):
    holidays = [make_holiday("Далеко", today + timedelta(days=30))]
    service, _ = build_service(holidays)

    assert service.get_upcoming_holidays(today=today) == []


def test_requests_current_year(today):
    service, provider = build_service([make_holiday("Праздник", today)])

    service.get_upcoming_holidays(today=today)

    assert provider.calls == [{"country": "RU", "year": 2026}]


def test_requests_next_year_on_year_boundary():
    today = date(2026, 12, 30)
    service, provider = build_service(
        [make_holiday("Новый год", date(2027, 1, 1))]
    )

    result = service.get_upcoming_holidays(today=today)

    assert [holiday.name for holiday in result] == ["Новый год"]
    assert [call["year"] for call in provider.calls] == [2026, 2027]


def test_deduplicates_holidays_on_year_boundary():
    today = date(2026, 12, 30)
    service, _ = build_service([make_holiday("Новый год", date(2027, 1, 1))])

    result = service.get_upcoming_holidays(today=today)

    assert len(result) == 1


def test_country_is_configurable(today):
    service, provider = build_service([make_holiday("Праздник", today)], country="BY")

    service.get_upcoming_holidays(today=today)

    assert provider.calls[0]["country"] == "BY"


def test_provider_error_converted_to_holidays_unavailable(today):
    provider = FakeHolidaysProvider(error=RuntimeError("network down"))
    service = HolidayService(provider=provider)

    with pytest.raises(HolidaysUnavailableError) as exc_info:
        service.get_upcoming_holidays(today=today)

    assert "праздник" in exc_info.value.user_message.lower()


def test_domain_error_from_provider_is_propagated(today):
    provider = FakeHolidaysProvider(
        error=HolidaysUnavailableError("ninjas-holidays", "http 500")
    )
    service = HolidayService(provider=provider)

    with pytest.raises(HolidaysUnavailableError):
        service.get_upcoming_holidays(today=today)

    assert provider.calls  # запрос действительно выполнялся
