"""Сервис праздников.

Бизнес-правила экрана «Праздники на 7 дней»:
    * запрашиваем праздники страны (по умолчанию RU) за текущий год;
    * если окно в 7 дней переходит на следующий год — дозапрашиваем и его;
    * оставляем только праздники в диапазоне [сегодня; сегодня + 7 дней];
    * сортируем по дате и показываем не более ``max_holidays`` штук.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, List, Optional

from travelhunter.domain.entities import Holiday
from travelhunter.domain.exceptions import (
    HolidaysUnavailableError,
    TravelHunterError,
)
from travelhunter.domain.interfaces import HolidaysProvider

logger = logging.getLogger(__name__)


class HolidayService:
    """Подготовка списка ближайших праздников для показа пользователю."""

    def __init__(
        self,
        provider: HolidaysProvider,
        days_ahead: int = 7,
        max_holidays: int = 5,
        country: str = "RU",
        today_provider: Optional[Callable[[], date]] = None,
    ) -> None:
        self._provider = provider
        self._days_ahead = days_ahead
        self._max_holidays = max_holidays
        self._country = country
        # today_provider позволяет подменить «сегодня» в тестах
        self._today_provider = today_provider or date.today

    @property
    def days_ahead(self) -> int:
        return self._days_ahead

    @property
    def max_holidays(self) -> int:
        return self._max_holidays

    def get_upcoming_holidays(self, today: Optional[date] = None) -> List[Holiday]:
        """Возвращает ближайшие праздники (не больше ``max_holidays``).

        :raises HolidaysUnavailableError: если внешний сервис недоступен
            или вернул некорректный ответ.
        """
        today = today or self._today_provider()
        last_day = today + timedelta(days=self._days_ahead)

        raw_holidays: List[Holiday] = []
        for year in self._years_to_request(today, last_day):
            raw_holidays.extend(self._fetch_year(year))

        upcoming = self._deduplicate(
            [holiday for holiday in raw_holidays if today <= holiday.date <= last_day]
        )
        upcoming.sort(key=lambda holiday: (holiday.date, holiday.name))
        return upcoming[: self._max_holidays]

    @staticmethod
    def _deduplicate(holidays: List[Holiday]) -> List[Holiday]:
        """Убирает повторы (возможны при запросе двух годов на стыке лет)."""
        unique: List[Holiday] = []
        seen = set()
        for holiday in holidays:
            key = (holiday.date.isoformat(), holiday.name.lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(holiday)
        return unique

    # ------------------------------------------------------------------ #
    # Внутренние методы
    # ------------------------------------------------------------------ #
    def _years_to_request(self, today: date, last_day: date) -> List[int]:
        """Годы, за которые нужно запросить праздники.

        API Ninjas отдаёт праздники за один год, поэтому на стыке годов
        (например, 30 декабря) нужно запросить два года.
        """
        years = [today.year]
        if last_day.year != today.year:
            years.append(last_day.year)
        return years

    def _fetch_year(self, year: int) -> List[Holiday]:
        """Запрос праздников за один год с преобразованием ошибок."""
        try:
            return self._provider.fetch_holidays(self._country, year)
        except HolidaysUnavailableError:
            # Сервис-клиент уже сформировал понятную ошибку — пробрасываем её.
            raise
        except TravelHunterError as exc:
            logger.error("Ошибка получения праздников за %s год: %s", year, exc)
            raise HolidaysUnavailableError("ninjas-holidays", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Непредвиденная ошибка при получении праздников")
            raise HolidaysUnavailableError("ninjas-holidays", str(exc)) from exc
