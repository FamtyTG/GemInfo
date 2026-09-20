"""Тесты слоя представления: тексты, клавиатуры, состояния пользователя."""

from __future__ import annotations

from datetime import date, datetime

from travelhunter.domain.entities import (
    City,
    CityInfo,
    Holiday,
    NearbyCity,
    Trip,
    TripPage,
)
from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.state import Screen, StateStorage, UserContext


# ====================================================================== #
# Тексты и форматирование
# ====================================================================== #
def test_start_text_matches_spec():
    assert texts.START_WELCOME == (
        "Добро пожаловать в TravelHunter\n"
        "Чат-бот, который помогает подобрать лучшее путешествие выходного дня.\n"
        "/start — переведёт Вас в главное меню, где бы Вы ни находились."
    )


def test_main_menu_text_matches_spec():
    assert texts.MAIN_MENU_WELCOME == (
        "Добро пожаловать в TravelHunter\nВыберите кнопку из главного меню."
    )


def test_unknown_command_text_matches_spec():
    assert texts.UNKNOWN_COMMAND == (
        "Нераспознанная команда. Пожалуйста, нажмите выбранную кнопку в меню."
    )


def test_format_holidays_numbered_list():
    holidays = [
        Holiday(name="День флага", date=date(2026, 8, 12), day="We", type="Observance"),
        Holiday(name="День знаний", date=date(2026, 9, 1), day="Mo", type="Public"),
    ]

    message = texts.format_holidays(holidays)

    assert message.startswith(texts.HOLIDAYS_TITLE)
    assert "1. День флага" in message
    assert "   12.08.2026 · We · Observance" in message
    assert "2. День знаний" in message
    assert "01.09.2026" in message


def test_format_holidays_without_type_and_day():
    holidays = [Holiday(name="Праздник", date=date(2026, 8, 12))]

    assert "12.08.2026" in texts.format_holidays(holidays)


def test_format_holidays_when_empty():
    assert texts.format_holidays([]) == texts.HOLIDAYS_EMPTY


def test_holidays_empty_text_matches_spec():
    assert texts.HOLIDAYS_EMPTY == (
        "К сожалению, ни одного праздника не найдено. "
        "Рекомендуем придумать себе праздник самостоятельно."
    )


def test_format_nearby_cities():
    current = City(name="Москва", latitude=55.75, longitude=37.61)
    cities = [
        NearbyCity(name="Тула", latitude=54.2, longitude=37.64, distance_km=172.4),
        NearbyCity(name="Калуга", latitude=54.5, longitude=36.27, distance_km=249.6),
    ]

    message = texts.format_nearby_cities(current, cities, radius_km=500)

    assert "Текущий город: Москва" in message
    assert "Радиус поиска: 500 км" in message
    assert "1. Тула — 172 км" in message
    assert "2. Калуга — 250 км" in message
    assert texts.NEARBY_FOOTER in message


def test_format_history_with_page_info():
    trips = [
        Trip(id=1, tg_user_id=1, name="Москва", arrival_date=datetime(2026, 8, 10)),
        Trip(id=2, tg_user_id=1, name="Калуга", arrival_date=datetime(2026, 8, 3)),
    ]
    page = TripPage(trips=trips, page=2, total_pages=3)

    message = texts.format_history(page)

    assert "Страница 2 из 3" in message
    assert "1. 10.08.2026 — Москва" in message
    assert "2. 03.08.2026 — Калуга" in message


def test_format_history_single_page_has_no_page_info():
    page = TripPage(
        trips=[Trip(id=1, tg_user_id=1, name="Тула", arrival_date=datetime(2026, 8, 10))],
        page=1,
        total_pages=1,
    )

    assert "Страница" not in texts.format_history(page)


def test_format_history_when_empty():
    assert texts.format_history(TripPage(trips=[], page=1, total_pages=1)) == texts.HISTORY_EMPTY


def test_history_empty_text_matches_spec():
    assert texts.HISTORY_EMPTY == (
        "История поездок пока пуста. Выберите город для своей первой поездки."
    )


def test_format_trip_with_note():
    trip = Trip(
        id=1,
        tg_user_id=1,
        name="Тула",
        arrival_date=datetime(2026, 8, 10),
        note="Очень понравилось!",
    )

    message = texts.format_trip(trip)

    assert "Дата поездки: 10.08.2026" in message
    assert "Город: Тула" in message
    assert "Заметка: Очень понравилось!" in message


def test_format_trip_without_note():
    trip = Trip(id=1, tg_user_id=1, name="Тула", arrival_date=datetime(2026, 8, 10))

    assert texts.NOTE_ABSENT in texts.format_trip(trip)
    assert texts.NOTE_ABSENT == "Заметка о поездке отсутствует."


def test_format_city_info_with_wikipedia_data():
    city = NearbyCity(
        name="Тула",
        latitude=54.2,
        longitude=37.6,
        region="Тульская область",
        country="Россия",
        distance_km=172.4,
    )
    info = CityInfo(title="Тула", summary="Город-герой.", image_url="https://img/tula.jpg")
    current = City(name="Москва", latitude=55.75, longitude=37.61)

    message = texts.format_city_info(city, info, current_city=current)

    assert "Город: Тула" in message
    assert "Расстояние от города Москва: 172 км" in message
    assert "Регион: Тульская область" in message
    assert texts.TRIP_SAVED in message
    assert "Город-герой." in message


def test_note_texts_match_spec():
    assert texts.NOTE_PROMPT == "Введите текст вашей заметки."
    assert texts.NOTE_SAVED == "Заметка успешно сохранена."


def test_city_input_prompt_matches_spec():
    assert texts.CITY_INPUT_PROMPT == (
        "Введите название города, в котором Вы сейчас находитесь."
    )


# ====================================================================== #
# Клавиатуры
# ====================================================================== #
def test_start_keyboard():
    markup = keyboards.start_keyboard()

    assert markup.keyboard == [[{"text": "Старт"}]]


def test_main_menu_keyboard_buttons():
    markup = keyboards.main_menu_keyboard()

    buttons = [row[0]["text"] for row in markup.keyboard]
    assert buttons == ["Праздники на 7 дней", "Города куда съездить", "История поездок"]


def test_back_to_menu_keyboard():
    markup = keyboards.back_to_menu_keyboard()

    button = markup.keyboard[0][0]
    assert button.text == "В главное меню"
    assert button.callback_data == "menu"


def test_nearby_cities_keyboard():
    markup = keyboards.nearby_cities_keyboard(3)

    rows = markup.keyboard
    assert [row[0].text for row in rows] == [
        "Выбрать город 1",
        "Выбрать город 2",
        "Выбрать город 3",
        "Назад",
    ]
    assert rows[0][0].callback_data == "city:1"
    assert rows[2][0].callback_data == "city:3"
    assert rows[3][0].callback_data == "city_input"


def test_history_keyboard_first_page_has_no_back_button():
    markup = keyboards.history_keyboard(trip_ids=[1, 2, 3], page=1, total_pages=3)

    buttons = [button.text for row in markup.keyboard for button in row]
    assert "Назад" not in buttons
    assert "Вперёд" in buttons
    assert buttons.count("Выбрать город") == 0
    assert "Выбрать город 1" in buttons
    assert "В главное меню" in buttons


def test_history_keyboard_last_page_has_no_forward_button():
    markup = keyboards.history_keyboard(trip_ids=[1], page=3, total_pages=3)

    buttons = [button.text for row in markup.keyboard for button in row]
    assert "Вперёд" not in buttons
    assert "Назад" in buttons


def test_history_keyboard_callback_data():
    markup = keyboards.history_keyboard(trip_ids=[7, 8], page=2, total_pages=4)

    data = [button.callback_data for row in markup.keyboard for button in row]
    assert data == ["trip:7", "trip:8", "history:1", "history:3", "menu"]


def test_trip_info_keyboard():
    markup = keyboards.trip_info_keyboard(trip_id=42, history_page=2)

    rows = markup.keyboard
    assert rows[0][0].text == "Написать заметку"
    assert rows[0][0].callback_data == "note:42"
    assert [button.text for button in rows[1]] == ["Назад", "В главное меню"]
    assert rows[1][0].callback_data == "history:2"


def test_parse_callback():
    assert keyboards.parse_callback("menu") == keyboards.Callback(action="menu", value=None)
    assert keyboards.parse_callback("city:3") == keyboards.Callback(action="city", value=3)
    assert keyboards.parse_callback("history:2") == keyboards.Callback(action="history", value=2)
    assert keyboards.parse_callback("trip:15") == keyboards.Callback(action="trip", value=15)
    assert keyboards.parse_callback("note:15") == keyboards.Callback(action="note", value=15)


def test_parse_callback_with_invalid_data():
    assert keyboards.parse_callback("") is None
    assert keyboards.parse_callback(None) is None
    assert keyboards.parse_callback("city:abc") is None


def test_menu_button_texts():
    assert keyboards.MENU_BUTTON_TEXTS == {
        "Старт",
        "Праздники на 7 дней",
        "Города куда съездить",
        "История поездок",
    }


# ====================================================================== #
# Состояние пользователя
# ====================================================================== #
def test_user_context_defaults_to_main_menu():
    context = UserContext()

    assert context.screen == Screen.MAIN_MENU
    assert context.current_city is None
    assert context.nearby_cities == ()
    assert context.history_page == 1


def test_user_context_transitions_are_immutable():
    context = UserContext()
    new_context = context.at_city_input()

    assert new_context is not context
    assert context.screen == Screen.MAIN_MENU
    assert new_context.screen == Screen.WAITING_CITY_NAME


def test_user_context_stores_city_and_nearby_cities():
    city = City(name="Москва", latitude=55.75, longitude=37.61)
    nearby = [
        NearbyCity(name="Тула", latitude=54.2, longitude=37.6, distance_km=172.0),
        NearbyCity(name="Калуга", latitude=54.5, longitude=36.2, distance_km=250.0),
    ]

    context = UserContext().with_current_city(city).with_nearby_cities(nearby)

    assert context.current_city == city
    assert context.screen == Screen.NEARBY_CITIES
    assert context.nearby_city(1) == nearby[0]
    assert context.nearby_city(2) == nearby[1]


def test_user_context_nearby_city_bounds():
    context = UserContext().with_nearby_cities(
        [NearbyCity(name="Тула", latitude=0, longitude=0, distance_km=1)]
    )

    assert context.nearby_city(0) is None
    assert context.nearby_city(2) is None


def test_user_context_keeps_history_page_for_note_screen():
    context = UserContext().with_history_page(3).at_note_input(trip_id=17)

    assert context.screen == Screen.WAITING_NOTE
    assert context.selected_trip_id == 17
    assert context.history_page == 3


def test_state_storage_save_get_reset():
    storage = StateStorage()

    assert storage.get(1) is None
    assert storage.has(1) is False

    storage.save(1, UserContext().at_city_input())

    assert storage.has(1) is True
    assert storage.get(1).screen == Screen.WAITING_CITY_NAME

    storage.reset(1)

    assert storage.has(1) is False
    assert len(storage) == 0


def test_state_storage_isolates_users():
    storage = StateStorage()

    storage.save(1, UserContext().at_city_input())
    storage.save(2, UserContext().at_main_menu())

    assert storage.get(1).screen == Screen.WAITING_CITY_NAME
    assert storage.get(2).screen == Screen.MAIN_MENU

    storage.clear()

    assert len(storage) == 0
