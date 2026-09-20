"""Экраны 4–6 раздела «Города куда съездить»."""

from __future__ import annotations

import logging

from travelhunter.domain.exceptions import TravelHunterError
from travelhunter.domain.services import CityService, TripService
from travelhunter.presentation import keyboards, texts
from travelhunter.presentation.gateway import TelegramGateway
from travelhunter.presentation.state import Screen, StateStorage, UserContext

logger = logging.getLogger(__name__)


class CityInputScreen:
    """Экран 4. Ввод названия текущего города пользователя."""

    def __init__(self, gateway: TelegramGateway, storage: StateStorage) -> None:
        self._gateway = gateway
        self._storage = storage

    def show(self, chat_id: int, user_id: int, error_text: str = "") -> None:
        logger.debug("Экран 4 «Ввод города» для пользователя %s", user_id)
        self._storage.save(user_id, UserContext().at_city_input())

        message = error_text or texts.CITY_INPUT_PROMPT
        if error_text:
            message = f"{error_text}\n\n{texts.CITY_INPUT_PROMPT}"

        # Скрываем reply-клавиатуру: пользователь будет вводить текст
        self._gateway.send_text(
            chat_id, message, reply_markup=keyboards.hide_keyboard()
        )


class NearbyCitiesScreen:
    """Экран 5. Список ближайших городов в радиусе 500 км."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        city_service: CityService,
        city_input_screen: CityInputScreen,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._service = city_service
        self._city_input_screen = city_input_screen

    def show(self, chat_id: int, user_id: int) -> None:
        logger.debug("Экран 5 «Ближайшие города» для пользователя %s", user_id)
        context = self._storage.get(user_id) or UserContext()
        current_city = context.current_city

        if current_city is None:
            # Пользователь не вводил город (например, бот перезапустился)
            self._city_input_screen.show(chat_id, user_id, error_text=texts.STATE_LOST)
            return

        try:
            nearby = self._service.find_nearby_cities(current_city)
        except TravelHunterError as exc:
            logger.error("Не удалось получить список ближайших городов: %s", exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        # Сохраняем список городов: он нужен для кнопок «Выбрать город N»
        self._storage.save(user_id, context.with_nearby_cities(nearby))

        message = texts.format_nearby_cities(
            current_city, nearby, self._service.radius_km
        )
        self._gateway.send_text(
            chat_id,
            message,
            reply_markup=keyboards.nearby_cities_keyboard(len(nearby)),
        )


class CityInfoScreen:
    """Экран 6. Информация о выбранном городе + сохранение поездки в базу."""

    def __init__(
        self,
        gateway: TelegramGateway,
        storage: StateStorage,
        city_service: CityService,
        trip_service: TripService,
    ) -> None:
        self._gateway = gateway
        self._storage = storage
        self._city_service = city_service
        self._trip_service = trip_service

    def show(self, chat_id: int, user_id: int, city_index: int) -> None:
        logger.debug(
            "Экран 6 «Информация о городе» (вариант %s) для пользователя %s",
            city_index,
            user_id,
        )
        context = self._storage.get(user_id) or UserContext()
        city = context.nearby_city(city_index)

        if city is None or context.screen not in (
            Screen.NEARBY_CITIES,
            Screen.CITY_INFO,
        ):
            # Кнопка нажата, но список городов уже неактуален
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, texts.STATE_LOST, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        # 1) Сохраняем поездку в базе данных
        try:
            trip = self._trip_service.create_trip(user_id, city.name)
        except TravelHunterError as exc:
            logger.error("Не удалось сохранить поездку: %s", exc)
            self._storage.save(user_id, context.at_main_menu())
            self._gateway.send_text(
                chat_id, exc.user_message, reply_markup=keyboards.back_to_menu_keyboard()
            )
            return

        context = context.with_trip(trip.id)
        self._storage.save(user_id, context)

        # 2) Получаем описание и изображение города из Википедии
        try:
            info = self._city_service.get_city_info(city.name)
        except TravelHunterError as exc:
            logger.error("Не удалось получить информацию о городе «%s»: %s", city.name, exc)
            self._gateway.send_text(
                chat_id,
                f"{exc.user_message}\n\n{texts.TRIP_SAVED}",
                reply_markup=keyboards.back_to_menu_keyboard(),
            )
            return

        caption = texts.format_city_info(city, info, context.current_city)
        markup = keyboards.back_to_menu_keyboard()

        # Если изображения нет или Telegram не смог его отправить —
        # показываем информацию текстом.
        if info.has_image and self._gateway.send_photo(
            chat_id, info.image_url, caption, reply_markup=markup
        ):
            return

        self._gateway.send_text(chat_id, caption, reply_markup=markup)
