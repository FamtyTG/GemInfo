"""Исключения проекта.

У каждого исключения есть атрибут ``user_message`` — готовый текст, который
можно показать пользователю в Telegram. Благодаря этому слой представления
не придумывает сообщения об ошибках сам, а берёт их из доменного слоя.

Любая ошибка перехватывается в обработчиках бота, поэтому возникновение
исключения никогда не приводит к аварийному завершению работы бота.
"""

from __future__ import annotations


class TravelHunterError(Exception):
    """Базовое исключение проекта (ожидаемая ошибка)."""

    user_message = "Что-то пошло не так. Попробуйте ещё раз позже."


class ConfigError(TravelHunterError):
    """Ошибка конфигурации: не задан обязательный параметр окружения."""

    user_message = "Бот настроен неправильно. Проверьте файл .env."


class ExternalServiceError(TravelHunterError):
    """Ошибка обращения к внешнему сервису (сеть, таймаут, неверный ответ)."""

    user_message = "Внешний сервис временно недоступен. Попробуйте ещё раз позже."

    def __init__(self, service: str = "", reason: str = "") -> None:
        self.service = service
        self.reason = reason
        details = " ".join(part for part in (service, reason) if part)
        super().__init__(details or self.__class__.__name__)


class HolidaysUnavailableError(ExternalServiceError):
    """Не удалось получить список праздников."""

    user_message = "Не удалось получить список праздников. Попробуйте ещё раз позже."


class CitySearchUnavailableError(ExternalServiceError):
    """Не удалось выполнить поиск города во внешнем сервисе."""

    user_message = "Не удалось найти город. Попробуйте ещё раз позже."


class CityInfoUnavailableError(ExternalServiceError):
    """Не удалось получить информацию о городе из Википедии."""

    user_message = "Не удалось получить информацию о городе. Попробуйте ещё раз позже."


class CityNotFoundError(TravelHunterError):
    """Введённый пользователем город не найден."""

    user_message = "Город не найден. Проверьте название города и попробуйте ещё раз."


class NearbyCitiesNotFoundError(TravelHunterError):
    """В заданном радиусе не найдено ни одного другого города."""

    def __init__(self, city_name: str = "", radius_km: int = 0) -> None:
        self.city_name = city_name
        self.radius_km = radius_km
        super().__init__(f"Не найдено городов рядом с {city_name}")

    @property
    def user_message(self) -> str:  # noqa: D102 - текст зависит от города
        return (
            f"К сожалению, рядом с городом «{self.city_name}» не найдено других "
            f"городов в радиусе {self.radius_km} км.\n"
            "Попробуйте указать другой город."
        )


class DatabaseError(TravelHunterError):
    """Ошибка при работе с базой данных."""

    user_message = "Ошибка при работе с базой данных. Попробуйте ещё раз позже."


class TripNotFoundError(TravelHunterError):
    """Поездка не найдена (или принадлежит другому пользователю)."""

    user_message = (
        "Поездка не найдена. Вернитесь в историю поездок и выберите поездку из списка."
    )


class NoteTooLongError(TravelHunterError):
    """Заметка длиннее допустимого количества символов."""

    def __init__(self, limit: int = 1000) -> None:
        self.limit = limit
        super().__init__(f"Заметка длиннее {limit} символов")

    @property
    def user_message(self) -> str:  # noqa: D102 - текст зависит от лимита
        return (
            f"Заметка не должна превышать {self.limit} символов. "
            "Сократите текст и попробуйте ещё раз."
        )


class EmptyNoteError(TravelHunterError):
    """Пользователь отправил пустую заметку."""

    user_message = "Заметка не может быть пустой. Введите текст заметки."
