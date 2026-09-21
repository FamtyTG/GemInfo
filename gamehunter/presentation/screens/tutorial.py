"""Экран 13 «Обучение»: анимированные карточки-подсказки (GIF).

Карточки собираются скриптом `scripts/generate_ae_assets.py` из настоящего
интерфейса бота и лежат в `gamehunter/assets/tutorial/*.gif`. Бот отправляет их
как анимации: пользователь видит не просто интерфейс, а обучающий ролик —
слева телефон с действиями, справа пояснения по шагам.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.base import BaseScreen
from gamehunter.presentation.state import StateStorage

logger = logging.getLogger(__name__)

#: Каталог с обучающими GIF (пересобирается командой `make ae-assets`)
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "tutorial"

#: Порядок карточек: приветствие → жанры → выбор игры
TUTORIAL_CARDS: Tuple[str, ...] = ("01_start", "03_picking_genres", "04_game_list")


class TutorialScreen(BaseScreen):
    """Экран 13. Обучение — выбор и просмотр анимированных карточек."""

    def show(self, chat_id: int, user_id: int) -> None:
        """Показывает меню обучения с выбором карточек."""
        logger.debug("Экран 13 «Обучение» для пользователя %s", user_id)
        self.send(
            chat_id,
            texts.TUTORIAL_MENU_TITLE,
            reply_markup=keyboards.tutorial_keyboard(),
        )

    def send_card(self, chat_id: int, user_id: int, card_key: str) -> None:
        """Отправляет одну обучающую карточку с подписью-инструкцией."""
        if card_key not in TUTORIAL_CARDS:
            logger.warning("Неизвестная карточка обучения: %s", card_key)
            self.show(chat_id, user_id)
            return

        path = ASSETS_DIR / f"{card_key}.gif"
        number = texts.TUTORIAL_CARD_NUMBERS.get(card_key, 0)
        caption = (
            f"Карточка {number} из {len(TUTORIAL_CARDS)}\n"
            f"{texts.tutorial_caption(card_key)}"
        )
        if not path.exists():
            logger.error("Файл обучения отсутствует: %s", path)
            self.notify(chat_id, texts.TUTORIAL_MISSING)
            return

        logger.info("Отправляю обучающую карточку %s пользователю %s", card_key, user_id)
        if not self._gateway.send_animation(chat_id, path, caption):
            self.notify(chat_id, texts.TUTORIAL_MISSING)

    def send_all(self, chat_id: int, user_id: int) -> None:
        """Отправляет все карточки подряд — мини-курс по боту."""
        for card_key in TUTORIAL_CARDS:
            self.send_card(chat_id, user_id, card_key)
