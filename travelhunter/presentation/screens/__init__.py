"""Экраны Telegram-бота и их сборка (контейнер экранов)."""

from __future__ import annotations

from dataclasses import dataclass

from travelhunter.domain.services import CityService, HolidayService, TripService
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.screens.cities import (
    CityInfoScreen,
    CityInputScreen,
    NearbyCitiesScreen,
)
from travelhunter.presentation.screens.history import (
    HistoryScreen,
    NoteInputScreen,
    TripInfoScreen,
)
from travelhunter.presentation.screens.holidays import HolidaysScreen
from travelhunter.presentation.screens.start_menu import MainMenuScreen, StartScreen
from travelhunter.presentation.state import StateStorage


@dataclass(frozen=True)
class ScreenContainer:
    """Набор всех экранов бота (экраны соответствуют карте перемещения)."""

    start: StartScreen                  # Экран 1
    main_menu: MainMenuScreen           # Экран 2
    holidays: HolidaysScreen            # Экран 3
    city_input: CityInputScreen         # Экран 4
    nearby_cities: NearbyCitiesScreen   # Экран 5
    city_info: CityInfoScreen           # Экран 6
    history: HistoryScreen              # Экран 7
    trip_info: TripInfoScreen           # Экран 8
    note_input: NoteInputScreen         # Экран 9


def build_screens(
    gateway: TelegramGateway,
    storage: StateStorage,
    holiday_service: HolidayService,
    city_service: CityService,
    trip_service: TripService,
) -> ScreenContainer:
    """Создаёт экраны и связывает их с сервисами (композиция без глобальных объектов)."""
    start_screen = StartScreen(gateway)
    main_menu_screen = MainMenuScreen(gateway, storage)
    holidays_screen = HolidaysScreen(gateway, storage, holiday_service)

    city_input_screen = CityInputScreen(gateway, storage)
    nearby_cities_screen = NearbyCitiesScreen(
        gateway, storage, city_service, city_input_screen
    )
    city_info_screen = CityInfoScreen(gateway, storage, city_service, trip_service)

    history_screen = HistoryScreen(gateway, storage, trip_service)
    trip_info_screen = TripInfoScreen(gateway, storage, trip_service)
    note_input_screen = NoteInputScreen(
        gateway, storage, trip_service, trip_info_screen
    )

    return ScreenContainer(
        start=start_screen,
        main_menu=main_menu_screen,
        holidays=holidays_screen,
        city_input=city_input_screen,
        nearby_cities=nearby_cities_screen,
        city_info=city_info_screen,
        history=history_screen,
        trip_info=trip_info_screen,
        note_input=note_input_screen,
    )


__all__ = [
    "CityInfoScreen",
    "CityInputScreen",
    "HistoryScreen",
    "HolidaysScreen",
    "MainMenuScreen",
    "NearbyCitiesScreen",
    "NoteInputScreen",
    "ScreenContainer",
    "StartScreen",
    "TripInfoScreen",
    "build_screens",
]
