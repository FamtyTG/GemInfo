"""Тест сборки приложения: все три слоя создаются и связаны между собой."""

from __future__ import annotations

import pytest

from travelhunter.app import Application, configure_logging
from travelhunter.config import Settings
from travelhunter.domain.services import CityService, HolidayService, TripService
from travelhunter.infrastructure.api import (
    GeoNamesClient,
    NinjasHolidaysClient,
    WikipediaClient,
)
from travelhunter.infrastructure.db import SqlTripRepository
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.handlers import BotHandlers
from travelhunter.presentation.screens import ScreenContainer


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        bot_token="123456789:TEST-TOKEN-FOR-UNIT-TESTS",
        database_url=f"sqlite:///{tmp_path / 'app_test.db'}",
        ninjas_api_key="test-ninjas-key",
        geonames_username="test-geonames-user",
    )


@pytest.fixture()
def application(settings: Settings) -> Application:
    app = Application(settings)
    try:
        yield app
    finally:
        app.stop()


def test_application_creates_infrastructure(application: Application):
    assert isinstance(application.database.engine.url.database, str)
    assert isinstance(application.holidays_provider, NinjasHolidaysClient)
    assert isinstance(application.city_provider, GeoNamesClient)
    assert isinstance(application.city_info_provider, WikipediaClient)
    assert isinstance(application.trip_repository, SqlTripRepository)
    assert application.holidays_provider.is_configured is True
    assert application.city_provider.is_configured is True


def test_application_creates_services(application: Application):
    assert isinstance(application.holiday_service, HolidayService)
    assert isinstance(application.city_service, CityService)
    assert isinstance(application.trip_service, TripService)
    assert application.city_service.radius_km == 500
    assert application.city_service.max_cities == 5
    assert application.trip_service.page_size == 5
    assert application.trip_service.note_max_length == 1000


def test_application_creates_all_screens(application: Application):
    assert isinstance(application.screens, ScreenContainer)
    assert isinstance(application.gateway, TelegramGateway)
    assert isinstance(application.handlers, BotHandlers)

    for screen in (
        application.screens.start,
        application.screens.main_menu,
        application.screens.holidays,
        application.screens.city_input,
        application.screens.nearby_cities,
        application.screens.city_info,
        application.screens.history,
        application.screens.trip_info,
        application.screens.note_input,
    ):
        assert screen is not None


def test_application_creates_database_tables(application: Application):
    from sqlalchemy import inspect

    assert "visited_cities" in inspect(application.database.engine).get_table_names()


def test_settings_from_environment_are_applied(tmp_path):
    settings = Settings(
        bot_token="123456789:TEST-TOKEN-FOR-UNIT-TESTS",
        database_url=f"sqlite:///{tmp_path / 'custom.db'}",
        nearby_radius_km=250,
        max_nearby_cities=3,
        history_page_size=2,
    )

    app = Application(settings)
    try:
        assert app.city_service.radius_km == 250
        assert app.city_service.max_cities == 3
        assert app.trip_service.page_size == 2
    finally:
        app.stop()


def test_configure_logging_accepts_any_level():
    configure_logging("DEBUG")
    configure_logging("unknown-level")  # не должно вызывать исключение
