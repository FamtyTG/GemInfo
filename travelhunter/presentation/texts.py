"""Тексты сообщений и правила их форматирования.

Все пользовательские строки собраны в одном модуле: так удобно сверять их
с техническим заданием и менять, не трогая логику экранов.
"""

from __future__ import annotations

from typing import List, Optional

from travelhunter.domain.entities import (
    City,
    CityInfo,
    Holiday,
    NearbyCity,
    Trip,
    TripPage,
)

BOT_NAME = "TravelHunter"

# ---------------------------------------------------------------------- #
# Экран 1. Старт
# ---------------------------------------------------------------------- #
START_WELCOME = (
    f"Добро пожаловать в {BOT_NAME}\n"
    "Чат-бот, который помогает подобрать лучшее путешествие выходного дня.\n"
    "/start — переведёт Вас в главное меню, где бы Вы ни находились."
)

# ---------------------------------------------------------------------- #
# Экран 2. Главное меню
# ---------------------------------------------------------------------- #
MAIN_MENU_WELCOME = (
    f"Добро пожаловать в {BOT_NAME}\n"
    "Выберите кнопку из главного меню."
)

UNKNOWN_COMMAND = (
    "Нераспознанная команда. Пожалуйста, нажмите выбранную кнопку в меню."
)

# ---------------------------------------------------------------------- #
# Экран 3. Праздники на 7 дней
# ---------------------------------------------------------------------- #
HOLIDAYS_TITLE = "Праздники на ближайшие 7 дней:"
HOLIDAYS_EMPTY = (
    "К сожалению, ни одного праздника не найдено. "
    "Рекомендуем придумать себе праздник самостоятельно."
)

# ---------------------------------------------------------------------- #
# Экран 4. Города куда съездить — ввод города
# ---------------------------------------------------------------------- #
CITY_INPUT_PROMPT = "Введите название города, в котором Вы сейчас находитесь."
CITY_SEARCHING = "Ищу город, подождите, пожалуйста…"

# ---------------------------------------------------------------------- #
# Экран 5. Города куда съездить — список ближайших городов
# ---------------------------------------------------------------------- #
NEARBY_TITLE = "Города, куда можно съездить:"
NEARBY_FOOTER = "Выберите город кнопкой ниже."

# ---------------------------------------------------------------------- #
# Экран 6. Города куда съездить — информация о городе
# ---------------------------------------------------------------------- #
CITY_INFO_TITLE = "Информация о городе:"
TRIP_SAVED = "Поездка сохранена в Вашей истории."

# ---------------------------------------------------------------------- #
# Экран 7. История поездок — список
# ---------------------------------------------------------------------- #
HISTORY_TITLE = "История поездок:"
HISTORY_EMPTY = (
    "История поездок пока пуста. Выберите город для своей первой поездки."
)
HISTORY_FOOTER = "Выберите поездку, чтобы посмотреть подробности."

# ---------------------------------------------------------------------- #
# Экран 8. История поездок — информация о поездке
# ---------------------------------------------------------------------- #
TRIP_INFO_TITLE = "Информация о поездке:"
NOTE_ABSENT = "Заметка о поездке отсутствует."

# ---------------------------------------------------------------------- #
# Экран 9. История поездок — добавление заметки
# ---------------------------------------------------------------------- #
NOTE_PROMPT = "Введите текст вашей заметки."
NOTE_SAVED = "Заметка успешно сохранена."

# ---------------------------------------------------------------------- #
# Общие сообщения
# ---------------------------------------------------------------------- #
GENERIC_ERROR = "Произошла ошибка. Попробуйте ещё раз позже."
STATE_LOST = (
    "Данные предыдущего шага не сохранились. "
    "Вернитесь в главное меню и начните заново."
)


# ---------------------------------------------------------------------- #
# Функции форматирования
# ---------------------------------------------------------------------- #
def format_holiday_description(holiday: Holiday) -> str:
    """Краткое описание праздника: дата, день недели и тип."""
    parts = [holiday.formatted_date]
    if holiday.day:
        parts.append(holiday.day)
    if holiday.type:
        parts.append(holiday.type)
    return " · ".join(parts)


def format_holidays(holidays: List[Holiday]) -> str:
    """Список праздников для Экрана 3."""
    if not holidays:
        return HOLIDAYS_EMPTY

    lines: List[str] = [HOLIDAYS_TITLE, ""]
    for index, holiday in enumerate(holidays, start=1):
        lines.append(f"{index}. {holiday.name}")
        lines.append(f"   {format_holiday_description(holiday)}")
    return "\n".join(lines)


def format_nearby_cities(
    current_city: City, cities: List[NearbyCity], radius_km: int
) -> str:
    """Список ближайших городов для Экрана 5."""
    header = (
        f"{NEARBY_TITLE}\n"
        f"Текущий город: {current_city.name}\n"
        f"Радиус поиска: {radius_km} км\n"
    )
    lines: List[str] = [header]
    for index, city in enumerate(cities, start=1):
        lines.append(f"{index}. {city.name} — {city.rounded_distance} км")
    lines.append("")
    lines.append(NEARBY_FOOTER)
    return "\n".join(lines)


def format_history(page: TripPage) -> str:
    """Список поездок для Экрана 7."""
    if page.is_empty:
        return HISTORY_EMPTY

    header = HISTORY_TITLE
    if page.total_pages > 1:
        header += f"\nСтраница {page.page} из {page.total_pages}"

    lines: List[str] = [header, ""]
    for index, trip in enumerate(page.trips, start=1):
        lines.append(f"{index}. {trip.formatted_date} — {trip.name}")
    lines.append("")
    lines.append(HISTORY_FOOTER)
    return "\n".join(lines)


def format_trip(trip: Trip) -> str:
    """Информация о поездке для Экрана 8."""
    note = trip.note.strip() if trip.has_note else ""
    lines = [
        TRIP_INFO_TITLE,
        "",
        f"Дата поездки: {trip.formatted_date}",
        f"Город: {trip.name}",
        f"Заметка: {note}" if note else NOTE_ABSENT,
    ]
    return "\n".join(lines)


def format_city_info(
    city: NearbyCity, info: Optional[CityInfo], current_city: Optional[City] = None
) -> str:
    """Информация о выбранном городе для Экрана 6."""
    title = info.title if info else city.name
    summary = info.summary if info and info.summary else ""

    lines: List[str] = [CITY_INFO_TITLE, "", f"Город: {title}"]
    if current_city is not None:
        lines.append(f"Расстояние от города {current_city.name}: {city.rounded_distance} км")
    else:
        lines.append(f"Расстояние: {city.rounded_distance} км")

    if city.region:
        lines.append(f"Регион: {city.region}")
    if city.country:
        lines.append(f"Страна: {city.country}")

    lines.append("")
    lines.append(TRIP_SAVED)

    if summary:
        lines.append("")
        lines.append(summary)

    return "\n".join(lines)
