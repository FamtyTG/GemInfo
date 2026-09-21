"""Обучающие видеокарточки: бот шлёт их прямо на нужных экранах.

Ролики собраны скриптом `scripts/generate_ae_assets.py` из настоящего
интерфейса бота и лежат в `gamehunter/assets/tutorial/*.mp4` (1920×1080,
60 fps, H.264). Отдельного раздела «Обучение» нет: карточка-подсказка
приходит вместе с экраном, к которому относится:

* Экран 1 «Старт»          → 01_start.mp4
* Экран 3 «Выбор жанра»    → 03_picking_genres.mp4
* Экран 4 «Подборка игр»   → 04_game_list.mp4

Подпись ролика — шаги из `texts.TUTORIAL_STEPS`: те же строки нарисованы на
панели внутри видео, поэтому ролик, подпись и интерфейс не расходятся.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from gamehunter.presentation import texts
from gamehunter.presentation.gateway import TelegramGateway

logger = logging.getLogger(__name__)

#: Каталог с обучающими роликами (пересобирается командой `make ae-assets`)
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "tutorial"

#: Ключи карточек в порядке обучения: приветствие → жанры → выбор игры
TUTORIAL_CARDS = ("01_start", "03_picking_genres", "04_game_list")

#: Какая карточка к какому экрану относится
CARD_BY_SCREEN: Dict[str, str] = {
    "start": "01_start",
    "picking": "03_picking_genres",
    "game_list": "04_game_list",
}


def animation_path(card_key: str) -> Path:
    """Путь к файлу обучающего ролика."""
    return ASSETS_DIR / f"{card_key}.mp4"


def send_tutorial(gateway: TelegramGateway, chat_id: int, screen_key: str,
                  caption: str, reply_markup=None) -> bool:
    """Отправляет обучающий ролик ВМЕСТЕ с сообщением экрана.

    Ролик приходит одним сообщением: сверху видео, снизу — подпись с текстом
    экрана (`caption`) и привычной клавиатурой (`reply_markup`). Никаких
    «Карточка 1 из 3» и отдельных сообщений: пользователь видит свой экран,
    просто дополненный видеоинструкцией.

    Обучение не должно мешать основному сценарию: если файла нет или Telegram
    отклонил анимацию — возвращаем False, и экран отправится обычным текстом.
    """
    card_key = CARD_BY_SCREEN.get(screen_key, screen_key)
    path = animation_path(card_key)
    if not path.exists():
        logger.error("Файл обучения отсутствует: %s", path)
        return False

    logger.info("Отправляю обучающий ролик %s в чат %s", card_key, chat_id)
    if not gateway.send_animation(chat_id, path, caption, reply_markup):
        logger.warning("Не удалось отправить обучающий ролик %s в чат %s", card_key, chat_id)
        return False
    return True
