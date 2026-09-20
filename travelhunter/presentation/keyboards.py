"""Клавиатуры Telegram и работа с callback-данными.

Два вида кнопок:
    * ReplyKeyboardMarkup — кнопки главного меню (постоянно видны под полем ввода);
    * InlineKeyboardMarkup — кнопки выбора из списков и переходов между экранами.

Callback-данные ограничены 64 байтами, поэтому используются короткие префиксы:
    menu             — главное меню;
    holidays         — праздники на 7 дней;
    city_input       — ввод текущего города;
    city:{номер}     — выбор города из списка ближайших;
    history:{стр}    — страница истории поездок;
    trip:{id}        — информация о поездке;
    note:{id}        — добавление заметки к поездке.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ---------------------------------------------------------------------- #
# Надписи на кнопках
# ---------------------------------------------------------------------- #


class ButtonText:
    """Тексты кнопок (сверены с описанием экранов из ТЗ)."""

    START = "Старт"
    HOLIDAYS = "Праздники на 7 дней"
    CITIES = "Города куда съездить"
    HISTORY = "История поездок"
    BACK_TO_MENU = "В главное меню"
    BACK = "Назад"
    FORWARD = "Вперёд"
    WRITE_NOTE = "Написать заметку"
    SELECT_CITY = "Выбрать город {}"


# Текст кнопки, который пользователь может прислать обычным сообщением
MENU_BUTTON_TEXTS = {
    ButtonText.START,
    ButtonText.HOLIDAYS,
    ButtonText.CITIES,
    ButtonText.HISTORY,
}


# ---------------------------------------------------------------------- #
# Callback-данные
# ---------------------------------------------------------------------- #
class CallbackAction:
    """Префиксы callback-данных."""

    MAIN_MENU = "menu"
    HOLIDAYS = "holidays"
    CITY_INPUT = "city_input"
    SELECT_CITY = "city"
    HISTORY = "history"
    TRIP = "trip"
    NOTE = "note"


@dataclass(frozen=True)
class Callback:
    """Разобранные callback-данные кнопки."""

    action: str
    value: Optional[int] = None


def parse_callback(data: Optional[str]) -> Optional[Callback]:
    """Преобразует строку callback-данных в объект Callback."""
    if not data:
        return None

    action, _, raw_value = data.partition(":")
    if not raw_value:
        return Callback(action=action)
    try:
        return Callback(action=action, value=int(raw_value))
    except ValueError:
        return None


def select_city_callback(index: int) -> str:
    return f"{CallbackAction.SELECT_CITY}:{index}"


def history_callback(page: int = 1) -> str:
    return f"{CallbackAction.HISTORY}:{page}"


def trip_callback(trip_id: int) -> str:
    return f"{CallbackAction.TRIP}:{trip_id}"


def note_callback(trip_id: int) -> str:
    return f"{CallbackAction.NOTE}:{trip_id}"


# ---------------------------------------------------------------------- #
# Reply-клавиатуры
# ---------------------------------------------------------------------- #
def start_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Экрана 1 «Старт»."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(ButtonText.START)
    return markup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Экрана 2 «Главное меню»."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(ButtonText.HOLIDAYS)
    markup.add(ButtonText.CITIES)
    markup.add(ButtonText.HISTORY)
    return markup


def hide_keyboard() -> ReplyKeyboardRemove:
    """Убирает reply-клавиатуру (например, на время ввода текста)."""
    return ReplyKeyboardRemove()


# ---------------------------------------------------------------------- #
# Inline-клавиатуры
# ---------------------------------------------------------------------- #
def _inline(*rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for row in rows:
        if row:
            markup.row(*row)
    return markup


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Одна кнопка «В главное меню» (Экраны 3, 6, 7)."""
    return _inline(
        [
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            )
        ]
    )


def nearby_cities_keyboard(cities_count: int) -> InlineKeyboardMarkup:
    """Кнопки выбора города и «Назад» для Экрана 5."""
    rows: List[List[InlineKeyboardButton]] = []
    for index in range(1, cities_count + 1):
        rows.append(
            [
                InlineKeyboardButton(
                    ButtonText.SELECT_CITY.format(index),
                    callback_data=select_city_callback(index),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.BACK, callback_data=CallbackAction.CITY_INPUT
            )
        ]
    )
    return _inline(*rows)


def history_keyboard(
    trip_ids: List[int], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Кнопки выбора поездки, пагинация и «В главное меню» для Экрана 7.

    Кнопки «Назад» нет на первой странице, кнопки «Вперёд» — на последней.
    """
    rows: List[List[InlineKeyboardButton]] = []

    for index, trip_id in enumerate(trip_ids, start=1):
        rows.append(
            [
                InlineKeyboardButton(
                    ButtonText.SELECT_CITY.format(index),
                    callback_data=trip_callback(trip_id),
                )
            ]
        )

    pagination: List[InlineKeyboardButton] = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                ButtonText.BACK, callback_data=history_callback(page - 1)
            )
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(
                ButtonText.FORWARD, callback_data=history_callback(page + 1)
            )
        )
    rows.append(pagination)

    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            )
        ]
    )
    return _inline(*rows)


def trip_info_keyboard(trip_id: int, history_page: int = 1) -> InlineKeyboardMarkup:
    """Кнопки Экрана 8: «Написать заметку», «Назад», «В главное меню»."""
    return _inline(
        [
            InlineKeyboardButton(
                ButtonText.WRITE_NOTE, callback_data=note_callback(trip_id)
            )
        ],
        [
            InlineKeyboardButton(
                ButtonText.BACK, callback_data=history_callback(history_page)
            ),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ],
    )
