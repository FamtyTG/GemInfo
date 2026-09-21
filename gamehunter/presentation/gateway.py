"""Шлюз к Telegram: единственное место, где экраны «разговаривают» с telebot.

Экраны не работают с объектом бота напрямую, а используют этот класс.
Благодаря этому:
    * логику экранов можно тестировать на подставном шлюзе без Telegram;
    * ошибки Telegram API не приводят к падению бота (они логируются).
"""

from __future__ import annotations

from pathlib import Path

import logging
from typing import Optional

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery

logger = logging.getLogger(__name__)

# Ограничение Telegram на длину текстового сообщения
MESSAGE_MAX_LENGTH = 4096


class TelegramGateway:
    """Отправка сообщений, фотографий и ответы на callback-запросы."""

    def __init__(self, bot: TeleBot) -> None:
        self._bot = bot

    # ------------------------------------------------------------------ #
    def send_text(self, chat_id: int, text: str, reply_markup=None) -> bool:
        """Отправляет текстовое сообщение. Возвращает True при успехе."""
        try:
            self._bot.send_message(
                chat_id, self._truncate(text), reply_markup=reply_markup
            )
            return True
        except ApiTelegramException as exc:
            logger.error("Telegram API отклонил сообщение для чата %s: %s", chat_id, exc)
        except Exception:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Не удалось отправить сообщение в чат %s", chat_id)
        return False

    # ------------------------------------------------------------------ #
    def send_photo(
        self, chat_id: int, image_url: str, caption: str, reply_markup=None
    ) -> bool:
        """Отправляет фото с подписью. Возвращает False, если не получилось."""
        try:
            self._bot.send_photo(
                chat_id, image_url, caption=self._truncate(caption), reply_markup=reply_markup
            )
            return True
        except ApiTelegramException as exc:
            logger.warning("Не удалось отправить фото %s: %s", image_url, exc)
        except Exception:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Ошибка при отправке фото в чат %s", chat_id)
        return False

    # ------------------------------------------------------------------ #
    def send_animation(
        self, chat_id: int, animation: Path, caption: str = ""
    ) -> bool:
        """Отправляет GIF-анимацию файлом. Возвращает False, если не получилось."""
        try:
            with open(animation, "rb") as handle:
                self._bot.send_animation(
                    chat_id, handle, caption=self._truncate(caption) or None
                )
            return True
        except FileNotFoundError:
            logger.warning("Файл анимации не найден: %s", animation)
        except ApiTelegramException as exc:
            logger.warning("Не удалось отправить анимацию %s: %s", animation, exc)
        except Exception:  # noqa: BLE001 - бот не должен «падать»
            logger.exception("Ошибка при отправке анимации в чат %s", chat_id)
        return False

    # ------------------------------------------------------------------ #
    def answer_callback(self, call: Optional[CallbackQuery], text: str = "") -> None:
        """Подтверждает нажатие inline-кнопки (убирает «часики» в Telegram)."""
        if call is None:
            return
        try:
            self._bot.answer_callback_query(call.id, text=text or None)
        except Exception:  # noqa: BLE001 - не критично для работы бота
            logger.debug("Не удалось ответить на callback-запрос %s", call.id)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _truncate(text: str) -> str:
        """Обрезает текст до ограничения Telegram."""
        if text is None:
            return ""
        if len(text) <= MESSAGE_MAX_LENGTH:
            return text
        return text[: MESSAGE_MAX_LENGTH - 1] + "…"
