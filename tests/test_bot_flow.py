"""Сквозные тесты сценариев использования бота (без сети и без Telegram).

Проверяются переходы между экранами согласно «Карте перемещения пользователя»:

    Экран 1 → Экран 2 → Экран 3                     (праздники)
    Экран 2 → Экран 4 → Экран 5 → Экран 6           (города куда съездить)
    Экран 2 → Экран 7 → Экран 8 → Экран 9 → Экран 8 (история поездок)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest

from travelhunter.domain.entities import CityInfo
from travelhunter.domain.services import CityService, HolidayService, TripService
from travelhunter.infrastructure.db import SqlTripRepository
from travelhunter.presentation.handlers import BotHandlers
from travelhunter.presentation.screens import build_screens
from travelhunter.presentation.state import Screen, StateStorage
from tests.fakes import (
    FakeCityInfoProvider,
    FakeCityProvider,
    FakeGateway,
    FakeHolidaysProvider,
    make_callback,
    make_city,
    make_holiday,
    make_message,
    make_nearby_city,
)

CHAT_ID = 100
USER_ID = 200

TODAY = date.today()  # праздники в тестах считаются от реальной текущей даты


@dataclass
class Flow:
    """Набор объектов для имитации диалога пользователя с ботом."""

    handlers: BotHandlers
    gateway: FakeGateway
    storage: StateStorage
    holidays: FakeHolidaysProvider
    cities: FakeCityProvider
    city_info: FakeCityInfoProvider
    trip_service: TripService
    repository: SqlTripRepository

    # ----------------------------- действия ----------------------------- #
    def command_start(self) -> str:
        self.handlers.on_start(make_message("/start", CHAT_ID, USER_ID))
        return self.gateway.last_text

    def send_text(self, text: str) -> str:
        self.handlers.on_text(make_message(text, CHAT_ID, USER_ID))
        return self.gateway.last_text

    def press(self, callback_data: str) -> str:
        self.handlers.on_callback(make_callback(callback_data, CHAT_ID, USER_ID))
        return self.gateway.last_text

    def screen(self) -> Screen:
        return self.storage.get(USER_ID).screen

    # ----------------------------- проверки ----------------------------- #
    @property
    def last_buttons(self):
        markup = self.gateway.last_markup
        # у ReplyKeyboardRemove нет атрибута keyboard — кнопок нет
        if markup is None or not hasattr(markup, "keyboard"):
            return []
        return [
            (button.text if hasattr(button, "text") else button.get("text"))
            for row in markup.keyboard
            for button in row
        ]

    @property
    def last_callback_data(self):
        markup = self.gateway.last_markup
        if markup is None or not hasattr(markup, "keyboard"):
            return []
        return [
            getattr(button, "callback_data", None) or button.get("callback_data")
            for row in markup.keyboard
            for button in row
        ]


@pytest.fixture()
def flow(database) -> Flow:
    """Собирает бота на подставных провайдерах и тестовой базе данных."""
    gateway = FakeGateway()
    storage = StateStorage()

    holidays_provider = FakeHolidaysProvider(
        holidays=[
            make_holiday("День физкультурника", TODAY + timedelta(days=2)),
            make_holiday("День государственного флага", TODAY + timedelta(days=5), "Observance"),
            make_holiday("Прошедший праздник", TODAY - timedelta(days=10)),
            make_holiday("Далёкий праздник", TODAY + timedelta(days=40)),
        ]
    )
    city_provider = FakeCityProvider(
        city=make_city("Москва", 55.7558, 37.6173, country="Россия"),
        nearby=[
            make_nearby_city("Москва", 0.0),
            make_nearby_city("Тула", 172.4, region="Тульская область"),
            make_nearby_city("Калуга", 249.6, region="Калужская область"),
            make_nearby_city("Владимир", 310.2),
            make_nearby_city("Рязань", 340.8),
            make_nearby_city("Тверь", 410.5),
            make_nearby_city("Орёл", 480.9),
        ],
    )
    city_info_provider = FakeCityInfoProvider(
        info=CityInfo(
            title="Тула",
            summary="Тула — город в России, административный центр Тульской области.",
            image_url="https://upload.wikimedia.org/wikipedia/commons/tula.jpg",
        )
    )

    repository = SqlTripRepository(database)
    holiday_service = HolidayService(provider=holidays_provider)
    city_service = CityService(city_provider=city_provider, city_info_provider=city_info_provider)
    trip_service = TripService(repository=repository)

    screens = build_screens(
        gateway=gateway,
        storage=storage,
        holiday_service=holiday_service,
        city_service=city_service,
        trip_service=trip_service,
    )
    handlers = BotHandlers(
        bot=None,  # в тестах регистрация не используется
        gateway=gateway,
        storage=storage,
        screens=screens,
        city_service=city_service,
    )
    return Flow(
        handlers=handlers,
        gateway=gateway,
        storage=storage,
        holidays=holidays_provider,
        cities=city_provider,
        city_info=city_info_provider,
        trip_service=trip_service,
        repository=repository,
    )


# ====================================================================== #
# Экран 1 → Экран 2. Старт и главное меню
# ====================================================================== #
def test_first_start_shows_welcome_screen(flow: Flow):
    text = flow.command_start()

    assert "Добро пожаловать в TravelHunter" in text
    assert "/start" in text
    assert flow.last_buttons == ["Старт"]


def test_second_start_shows_main_menu(flow: Flow):
    flow.command_start()

    text = flow.command_start()

    assert text == (
        "Добро пожаловать в TravelHunter\nВыберите кнопку из главного меню."
    )
    assert flow.last_buttons == [
        "Праздники на 7 дней",
        "Города куда съездить",
        "История поездок",
    ]
    assert flow.screen() == Screen.MAIN_MENU


def test_start_button_leads_to_main_menu(flow: Flow):
    flow.command_start()

    text = flow.send_text("Старт")

    assert "Выберите кнопку из главного меню" in text


def test_first_text_message_shows_welcome_screen(flow: Flow):
    text = flow.send_text("Привет")

    assert "Чат-бот, который помогает подобрать лучшее путешествие" in text


def test_start_returns_to_main_menu_from_city_input(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    assert flow.screen() == Screen.WAITING_CITY_NAME

    flow.command_start()

    assert flow.screen() == Screen.MAIN_MENU
    assert "Выберите кнопку из главного меню" in flow.gateway.last_text


# ====================================================================== #
# Экран 3. Праздники на 7 дней
# ====================================================================== #
def test_holidays_shows_only_next_seven_days(flow: Flow):
    flow.command_start()

    text = flow.send_text("Праздники на 7 дней")

    assert "1. День физкультурника" in text
    assert "2. День государственного флага" in text
    assert "Прошедший праздник" not in text
    assert "Далёкий праздник" not in text
    assert flow.last_buttons == ["В главное меню"]


def test_holidays_available_via_inline_button(flow: Flow):
    flow.command_start()

    text = flow.press("holidays")

    assert "Праздники на ближайшие 7 дней" in text
    assert flow.holidays.calls[0]["country"] == "RU"


def test_holidays_shows_date_and_type(flow: Flow):
    flow.command_start()

    text = flow.press("holidays")

    expected_date = (TODAY + timedelta(days=5)).strftime("%d.%m.%Y")
    assert expected_date in text
    assert "Observance" in text


def test_holidays_when_none_found(flow: Flow):
    flow.holidays.holidays = []
    flow.command_start()

    text = flow.press("holidays")

    assert text == (
        "К сожалению, ни одного праздника не найдено. "
        "Рекомендуем придумать себе праздник самостоятельно."
    )
    assert flow.last_buttons == ["В главное меню"]


def test_holidays_when_api_unavailable(flow: Flow):
    flow.holidays.error = RuntimeError("connection refused")
    flow.command_start()

    text = flow.press("holidays")

    assert text == (
        "Не удалось получить список праздников. Попробуйте ещё раз позже."
    )
    assert flow.last_buttons == ["В главное меню"]


def test_holidays_back_to_main_menu(flow: Flow):
    flow.command_start()
    flow.press("holidays")

    text = flow.press("menu")

    assert "Выберите кнопку из главного меню" in text
    assert flow.screen() == Screen.MAIN_MENU


# ====================================================================== #
# Экраны 4 → 5 → 6. Города куда съездить
# ====================================================================== #
def test_city_input_prompt(flow: Flow):
    flow.command_start()

    text = flow.send_text("Города куда съездить")

    assert text == "Введите название города, в котором Вы сейчас находитесь."
    assert flow.screen() == Screen.WAITING_CITY_NAME


def test_nearby_cities_list(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")

    text = flow.send_text("Москва")

    assert "Текущий город: Москва" in text
    assert "Радиус поиска: 500 км" in text
    assert "1. Тула — 172 км" in text
    assert "2. Калуга — 250 км" in text
    # город пользователя исключён из списка, показаны только первые 5
    assert "Москва —" not in text
    assert "Орёл" not in text
    assert flow.last_buttons == [
        "Выбрать город 1",
        "Выбрать город 2",
        "Выбрать город 3",
        "Выбрать город 4",
        "Выбрать город 5",
        "Назад",
    ]
    assert flow.screen() == Screen.NEARBY_CITIES


def test_nearby_cities_requested_with_city_coordinates(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    call = flow.cities.nearby_calls[0]

    assert call["lat"] == 55.7558
    assert call["lng"] == 37.6173
    assert call["radius"] == 500


def test_city_not_found_asks_again(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.cities.city = None  # сервис не нашёл город

    text = flow.send_text("Атлантида")

    assert text.endswith("Введите название города, в котором Вы сейчас находитесь.")
    assert "Город не найден. Проверьте название города и попробуйте ещё раз." in text
    assert flow.screen() == Screen.WAITING_CITY_NAME

    # повторный ввод корректного города работает
    flow.cities.city = make_city("Москва", 55.7558, 37.6173)
    text = flow.send_text("Москва")

    assert "1. Тула — 172 км" in text


def test_city_search_service_error(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.cities.search_error = RuntimeError("geonames down")

    text = flow.send_text("Москва")

    assert "Не удалось найти город. Попробуйте ещё раз позже." in text
    assert flow.last_buttons == ["В главное меню"]
    assert flow.screen() == Screen.MAIN_MENU


def test_select_city_saves_trip_and_shows_info(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:1")

    # поездка сохранена в базе данных
    assert flow.repository.count_by_user(USER_ID) == 1
    saved_trip = flow.repository.find_by_user(USER_ID, 10, 0)[0]
    assert saved_trip.name == "Тула"
    assert saved_trip.note is None

    # показана информация о городе из Википедии
    assert flow.gateway.photos, "ожидалось сообщение с фотографией города"
    assert "Город: Тула" in text
    assert "Расстояние от города Москва: 172 км" in text
    assert "Тула — город в России" in text
    assert flow.last_buttons == ["В главное меню"]
    assert flow.screen() == Screen.CITY_INFO


def test_select_city_without_image_sends_text(flow: Flow):
    flow.city_info.info = CityInfo(title="Тула", summary="Описание города.", image_url=None)
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:1")

    assert flow.gateway.photos == []
    assert "Город: Тула" in text
    assert "Описание города." in text


def test_select_city_when_photo_sending_fails(flow: Flow):
    flow.gateway.photo_fails = True
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:1")

    assert "Город: Тула" in text  # информация показана текстом


def test_select_city_when_wikipedia_unavailable(flow: Flow):
    flow.city_info.error = RuntimeError("wikipedia down")
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:1")

    assert "Не удалось получить информацию о городе" in text
    # поездка при этом сохранена
    assert flow.repository.count_by_user(USER_ID) == 1
    assert flow.last_buttons == ["В главное меню"]


def test_select_city_out_of_range(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:9")

    assert "Данные предыдущего шага не сохранились" in text
    assert flow.repository.count_by_user(USER_ID) == 0


def test_nearby_screen_without_city_returns_to_input(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")

    # имитируем потерю данных: состояние сброшено, но пользователь жмёт «Назад»
    flow.press("city_input")

    assert flow.screen() == Screen.WAITING_CITY_NAME
    assert "Введите название города" in flow.gateway.last_text


def test_nearby_cities_not_found(flow: Flow):
    flow.cities.nearby = [make_nearby_city("Москва", 0.0)]
    flow.command_start()
    flow.send_text("Города куда съездить")

    text = flow.send_text("Москва")

    assert "не найдено других городов" in text
    assert flow.last_buttons == ["В главное меню"]


# ====================================================================== #
# Экраны 7 → 8 → 9. История поездок
# ====================================================================== #
def add_trips(flow: Flow, count: int, user_id: int = USER_ID) -> None:
    for index in range(count):
        flow.trip_service.create_trip(
            user_id, f"Город {index}", arrival_date=datetime(2026, 8, index + 1, 12)
        )


def test_history_empty(flow: Flow):
    flow.command_start()

    text = flow.send_text("История поездок")

    assert text == (
        "История поездок пока пуста. Выберите город для своей первой поездки."
    )
    assert flow.last_buttons == ["В главное меню"]


def test_history_lists_trips_from_new_to_old(flow: Flow):
    add_trips(flow, 3)
    flow.command_start()

    text = flow.send_text("История поездок")

    assert "1. 03.08.2026 — Город 2" in text
    assert "2. 02.08.2026 — Город 1" in text
    assert "3. 01.08.2026 — Город 0" in text
    assert flow.screen() == Screen.HISTORY


def test_history_pagination(flow: Flow):
    add_trips(flow, 7)
    flow.command_start()
    flow.send_text("История поездок")

    assert "Страница 1 из 2" in flow.gateway.last_text
    assert "5. 03.08.2026 — Город 2" in flow.gateway.last_text
    assert "Вперёд" in flow.last_buttons
    assert "Назад" not in flow.last_buttons
    assert "history:2" in flow.last_callback_data

    text = flow.press("history:2")

    assert "Страница 2 из 2" in text
    assert "1. 02.08.2026 — Город 1" in text
    assert "2. 01.08.2026 — Город 0" in text
    assert "Назад" in flow.last_buttons
    assert "Вперёд" not in flow.last_buttons


def test_history_shows_only_own_trips(flow: Flow):
    add_trips(flow, 2)
    add_trips(flow, 3, user_id=999)
    flow.command_start()

    flow.send_text("История поездок")

    assert "Город 0" in flow.gateway.last_text
    assert "Страница" not in flow.gateway.last_text


def test_trip_info_without_note(flow: Flow):
    add_trips(flow, 1)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.send_text("История поездок")

    text = flow.press(f"trip:{trip_id}")

    assert "Дата поездки: 01.08.2026" in text
    assert "Город: Город 0" in text
    assert "Заметка о поездке отсутствует." in text
    assert flow.last_buttons == ["Написать заметку", "Назад", "В главное меню"]
    assert flow.screen() == Screen.TRIP_INFO


def test_trip_info_back_to_history(flow: Flow):
    add_trips(flow, 7)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.send_text("История поездок")
    flow.press("history:2")
    flow.press(f"trip:{trip_id}")

    text = flow.press("history:2")

    assert "Страница 2 из 2" in text
    assert flow.screen() == Screen.HISTORY


def test_trip_not_found(flow: Flow):
    flow.command_start()

    text = flow.press("trip:4242")

    assert "Поездка не найдена" in text
    assert flow.last_buttons == ["В главное меню"]


def test_note_prompt(flow: Flow):
    add_trips(flow, 1)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.send_text("История поездок")
    flow.press(f"trip:{trip_id}")

    text = flow.press(f"note:{trip_id}")

    assert text == "Введите текст вашей заметки."
    assert flow.screen() == Screen.WAITING_NOTE


def test_note_saved_and_return_to_trip_info(flow: Flow):
    add_trips(flow, 1)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.send_text("История поездок")
    flow.press(f"trip:{trip_id}")
    flow.press(f"note:{trip_id}")

    saved_message = flow.send_text("Были в Туле, гуляли по набережной.")

    assert saved_message != "Заметка успешно сохранена."  # после сохранения показан Экран 8
    assert "Заметка успешно сохранена." in flow.gateway.all_texts
    assert "Заметка: Были в Туле, гуляли по набережной." in flow.gateway.last_text
    assert flow.repository.find_by_id(trip_id, USER_ID).note == "Были в Туле, гуляли по набережной."
    assert flow.screen() == Screen.TRIP_INFO


def test_note_too_long_stays_on_note_screen(flow: Flow):
    add_trips(flow, 1)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.send_text("История поездок")
    flow.press(f"note:{trip_id}")

    text = flow.send_text("с" * 1001)

    assert text == (
        "Заметка не должна превышать 1000 символов. "
        "Сократите текст и попробуйте ещё раз."
    )
    assert flow.screen() == Screen.WAITING_NOTE
    assert flow.repository.find_by_id(trip_id, USER_ID).note is None

    # после ошибки можно ввести корректную заметку
    flow.send_text("Короткая заметка")

    assert flow.repository.find_by_id(trip_id, USER_ID).note == "Короткая заметка"


def test_empty_note_is_rejected(flow: Flow):
    add_trips(flow, 1)
    trip_id = flow.repository.find_by_user(USER_ID, 1, 0)[0].id
    flow.command_start()
    flow.press(f"note:{trip_id}")

    text = flow.send_text("   ")

    assert "Заметка не может быть пустой" in text
    assert flow.screen() == Screen.WAITING_NOTE


def test_note_without_trip_returns_to_menu(flow: Flow):
    flow.command_start()
    flow.storage.save(USER_ID, flow.storage.get(USER_ID).at_note_input(999))

    text = flow.send_text("Заметка к несуществующей поездке")

    assert "Поездка не найдена" in text
    assert flow.last_buttons == ["В главное меню"]


# ====================================================================== #
# Обработка неправильного ввода
# ====================================================================== #
def test_unknown_text_in_main_menu(flow: Flow):
    flow.command_start()

    text = flow.send_text("какой-то текст")

    assert text == (
        "Нераспознанная команда. Пожалуйста, нажмите выбранную кнопку в меню."
    )


def test_unknown_text_while_viewing_cities(flow: Flow):
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.send_text("просто текст")

    assert "Нераспознанная команда" in text
    assert flow.screen() == Screen.NEARBY_CITIES


def test_unsupported_message_is_ignored(flow: Flow):
    flow.command_start()
    before = len(flow.gateway.events)

    flow.handlers.on_unsupported(
        make_message("", CHAT_ID, USER_ID, content_type="photo")
    )

    assert len(flow.gateway.events) == before


def test_unknown_callback_data(flow: Flow):
    flow.command_start()

    text = flow.press("что-то:непонятное")

    assert "Нераспознанная команда" in text


def test_callback_is_answered(flow: Flow):
    flow.command_start()

    flow.press("holidays")

    assert flow.gateway.answered_callbacks == 1


def test_menu_buttons_work_from_any_screen(flow: Flow):
    """Reply-кнопки главного меню действуют даже во время ввода города."""
    flow.command_start()
    flow.send_text("Города куда съездить")

    text = flow.send_text("История поездок")

    assert "История поездок пока пуста" in text
    assert flow.screen() == Screen.HISTORY


# ====================================================================== #
# Отказоустойчивость
# ====================================================================== #
def test_unexpected_error_does_not_crash_bot(flow: Flow, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(TripService, "create_trip", boom)
    flow.command_start()
    flow.send_text("Города куда съездить")
    flow.send_text("Москва")

    text = flow.press("city:1")  # исключение не должно выйти наружу

    assert "Произошла ошибка. Попробуйте ещё раз позже." in text
    assert flow.last_buttons == ["В главное меню"]
    # сообщение об ошибке отправлено именно в чат пользователя
    assert flow.gateway.last_event.chat_id == CHAT_ID


def test_unexpected_error_in_history_does_not_crash_bot(flow: Flow, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(TripService, "get_history", boom)
    flow.command_start()

    text = flow.send_text("История поездок")

    assert "Произошла ошибка. Попробуйте ещё раз позже." in text
    assert flow.gateway.last_event.chat_id == CHAT_ID


def test_chat_id_detected_for_message_and_callback(flow: Flow):
    from travelhunter.presentation.handlers import BotHandlers

    assert BotHandlers._chat_id_of(make_message("текст", CHAT_ID, USER_ID)) == CHAT_ID
    assert BotHandlers._chat_id_of(make_callback("menu", CHAT_ID, USER_ID)) == CHAT_ID


def test_message_without_user_is_ignored(flow: Flow):
    from types import SimpleNamespace

    broken = SimpleNamespace(text="привет", chat=None, from_user=None, content_type="text")

    flow.handlers.on_text(broken)

    assert flow.gateway.events == []


def test_handlers_register_in_telebot(flow: Flow):
    """Проверяем, что обработчики действительно регистрируются в telebot."""
    import telebot

    bot = telebot.TeleBot("123456789:TEST-TOKEN-FOR-UNIT-TESTS")
    handlers = BotHandlers(
        bot=bot,
        gateway=flow.gateway,
        storage=flow.storage,
        screens=flow.handlers._screens,  # noqa: SLF001 - проверка регистрации
        city_service=flow.handlers._city_service,  # noqa: SLF001
    )

    handlers.register()

    assert len(bot.message_handlers) >= 3
    assert len(bot.callback_query_handlers) == 1
