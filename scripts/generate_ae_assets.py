#!/usr/bin/env python3
"""Генератор обучающих анимированных карточек GameHunter (16:9, 60 fps).

Карточка — это учебный кадр 1920×1080: слева «телефон» с настоящим интерфейсом
бота (тексты и кнопки берутся из `gamehunter.presentation.texts` / `keyboards`),
справа — панель с пояснениями по шагам (`texts.TUTORIAL_STEPS`). В момент
«нажатия» кнопки вокруг неё появляется подсвечивающее кольцо.

Результат (команда `make ae-assets`):

    gamehunter/assets/tutorial/<экран>.gif — обучающая анимация, её шлёт бот
                                             (Экран 13 «Обучение», 60 fps)
    docs/ae/layers/<экран>/*.png           — слои кадра с прозрачностью для AE
    docs/ae/timeline.json                  — раскадровка: секунды и кадры AE (60 fps)
    docs/ae/preview.html                   — превью «карточка сверху + текст снизу»
    docs/ae/import_layers.jsx              — сборка композиции в After Effects

Тексты шагов обучения живут в `gamehunter.presentation.texts.TUTORIAL_STEPS`:
они же попадают в GIF-панель и в подписи, которые бот шлёт вместе с GIF, —
поэтому ролик, подпись и интерфейс никогда не расходятся.

Запуск:
    python scripts/generate_ae_assets.py [--fps 60] [--gif-width 960]
                                         [--backdrop light|dark|none]
                                         [--only 01_start] [--frames]

Нужен Pillow (только для генерации, в рантайме бота не используется):
    pip install pillow
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

AE_OUTPUT = PROJECT_ROOT / "docs" / "ae"
ASSETS_OUTPUT = PROJECT_ROOT / "gamehunter" / "assets" / "tutorial"

# --------------------------------------------------------------------------- #
# Геометрия кадра 16:9
# --------------------------------------------------------------------------- #
CANVAS_W = 1920                 # итоговый кадр (16:9)
CANVAS_H = 1080
CANVAS1_H = CANVAS_H // 2
PAD = 48                        # отступ кадра
PHONE_AREA_W = 800              # максимум ширины под «телефон»
PHONE_GAP = 56                  # расстояние между телефоном и панелью
AE_FPS = 60                     # частота кадров раскадровки (и композиции AE)
DEFAULT_GIF_FPS = 60            # частота кадров GIF
DEFAULT_GIF_WIDTH = 960         # ширина GIF (960×540 — экономит размер)

CARD_W1 = 375                   # ширина «телефона» в его собственных 1x
MARGIN = 12
HEADER_H = 74
CARD_RADIUS = 26
ROW_H = 34
ROW_GAP = 8
REPLY_ROW_H = 44
LINE_HEIGHT = 18
FONT_SIZE = 13
BUTTON_FONT_SIZE = 13
SMALL_FONT_SIZE = 11
TYPING_W = 62
TYPING_H = 36
CAPTION_H = 18

BACKGROUND = "#EFEFF4"
HEADER_BG = "#FFFFFF"
HEADER_LINE = "#D1D1D6"
BUBBLE_BG = "#FFFFFF"
BUBBLE_TEXT = "#1C1C1E"
SENDER = "#2481CC"
BUTTON_BG = "#FFFFFF"
BUTTON_BORDER = "#C7C7CC"
BUTTON_TEXT = "#2481CC"
PRIMARY_BG = "#2481CC"
PRIMARY_TEXT = "#FFFFFF"
REPLY_BG = "#F7F7F7"
REPLY_BUTTON_BG = "#FFFFFF"
NOTE_TEXT = "#8E8E93"
DOT_ON = "#8E8E93"
DOT_OFF = "#C7C7CC"
HEADING_COLOR = "#16202E"
ACCENT = "#2481CC"
BOT_USERNAME = "GameHunterBot"

BACKDROPS: Dict[str, Optional[str]] = {
    "light": "#EDF1F7",
    "dark": "#14171C",
    "none": None,
}

FONT_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "regular": (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
    ),
    "bold": (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ),
}


def load_mockups() -> Any:
    """Загружает генератор мокапов как модуль (он лежит вне пакета)."""
    path = PROJECT_ROOT / "scripts" / "generate_mockups.py"
    spec = importlib.util.spec_from_file_location("generate_mockups", path)
    if spec is None or spec.loader is None:  # pragma: no cover - защита пути
        raise RuntimeError(f"Не удалось загрузить {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mockups = load_mockups()
texts = mockups.texts
keyboards = mockups.kb

TUTORIAL_CARDS: Tuple[str, ...] = ("01_start", "03_picking_genres", "04_game_list")


@dataclass(frozen=True)
class Card:
    """Описание одной обучающей карточки."""

    key: str
    screen_file: str
    heading: str
    description: str
    duration: float
    step_times: Tuple[float, ...]   # когда на панели зажигаются шаги обучения


CARDS: Tuple[Card, ...] = (
    Card(
        key="01_start",
        screen_file="01_start",
        heading="Приветствие",
        description=(
            "Первое сообщение бота после /start: коротко о том, что он умеет, "
            "и кнопка «Старт»."
        ),
        duration=6.0,
        step_times=(0.20, 1.05, 2.55),
    ),
    Card(
        key="03_picking_genres",
        screen_file="03_picking_genres",
        heading="Выбор жанра",
        description=(
            "Бот предлагает жанры; отметка ✔ появляется сразу после нажатия, "
            "а текст сообщения обновляется."
        ),
        duration=7.5,
        step_times=(0.20, 1.65, 4.30),
    ),
    Card(
        key="04_game_list",
        screen_file="04_game_list",
        heading="Выбор игры",
        description=(
            "Подборка игр по анкете: сыгранные исключены, нажатие на строку "
            "открывает карточку игры с обложкой."
        ),
        duration=7.5,
        step_times=(0.20, 1.00, 4.60),
    ),
)


# --------------------------------------------------------------------------- #
# Шаги анимации
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Step:
    """Один шаг анимации слоя (время в секундах)."""

    layer: str
    effect: str                 # fade | slide_up | pop | keyboard_up | tap | hide | shift_down
    start: float
    duration: float = 0.4
    ease: str = "ease_out"
    offset: float = 0.0
    amplitude: float = 0.06

    def to_payload(self) -> Dict[str, Any]:
        """Шаг в виде JSON — с номерами кадров для After Effects."""
        return {
            "layer": self.layer,
            "effect": self.effect,
            "start_s": round(self.start, 3),
            "duration_s": round(self.duration, 3),
            "ease": self.ease,
            "offset_px": self.offset,
            "amplitude": self.amplitude if self.effect == "tap" else None,
            "ae": {
                "in_frame": round(self.start * AE_FPS),
                "duration_frames": max(1, round(self.duration * AE_FPS)),
                "out_frame": round((self.start + self.duration) * AE_FPS),
            },
        }


@dataclass(frozen=True)
class LayerSpec:
    """Слой: имя, порядок, положение в своих 1x и готовое изображение."""

    name: str
    order: int
    space: str                  # "phone" | "canvas"
    x1: float
    y1: float
    w1: float
    h1: float
    image: Any

    @property
    def file_name(self) -> str:
        return f"{self.order:02d}_{self.name}.png"


EASINGS: Dict[str, Any] = {
    "linear": lambda p: p,
    "ease_out": lambda p: 1 - (1 - p) ** 3,
    "ease_in": lambda p: p ** 3,
    "ease_in_out": lambda p: 3 * p ** 2 - 2 * p ** 3,
    "back_out": lambda p: 1 + 2.2 * (p - 1) ** 3 + 1.2 * (p - 1) ** 2,
}


def ease(name: str, progress: float) -> float:
    """Значение easing-функции в точке progress (0…1)."""
    fn = EASINGS.get(name, EASINGS["ease_out"])
    return max(0.0, min(1.2, fn(max(0.0, min(1.0, progress)))))


def layer_state(steps: Sequence[Step], time: float) -> Tuple[float, float, float]:
    """Состояние слоя в момент time: (прозрачность 0…1, смещение px 1x, масштаб)."""
    alpha = 0.0
    dy = 0.0
    scale = 1.0
    for step in sorted(steps, key=lambda item: item.start):
        if time < step.start:
            break
        progress = (time - step.start) / step.duration if step.duration > 0 else 1.0
        progress = max(0.0, min(1.0, progress))
        value = ease(step.ease, progress)
        if step.effect == "hide":
            alpha = 1.0 - value
            dy = 0.0
            scale = 1.0
        elif step.effect == "tap":
            scale = 1.0 - step.amplitude * math.sin(math.pi * progress)
            alpha = 1.0
        elif step.effect == "shift_down":
            alpha = 1.0
            dy = value * step.offset
        elif step.effect == "pop":
            alpha = min(1.0, value * 1.6)
            scale = 0.86 + 0.14 * value
            dy = (1.0 - value) * step.offset
        else:  # fade, slide_up, keyboard_up
            alpha = min(1.0, value)
            dy = (1.0 - value) * step.offset
            scale = 1.0
    return alpha, dy, scale


def phone_scale(card_height1: float) -> float:
    """Масштаб «телефона»: по высоте кадра и отведённой ему ширине."""
    available_h = CANVAS_H - 2 * PAD
    return max(0.4, min(available_h / card_height1, PHONE_AREA_W / CARD_W1))


# --------------------------------------------------------------------------- #
# Рисование: общий механизм шрифтов
# --------------------------------------------------------------------------- #
SS = 2.0  # текущий масштаб рисования (итоговые px на единицу 1x); меняется ниже


def set_ss(value: float) -> None:
    global SS
    SS = value


def _px(value: float) -> int:
    return int(round(value * SS))


_FONTS: Dict[Tuple[bool, int], Any] = {}
_FONT_PATHS: Dict[str, Optional[str]] = {}


def find_font(bold: bool = False) -> Optional[str]:
    """Ищет шрифт с кириллицей в системе (Windows / Linux / macOS)."""
    key = "bold" if bold else "regular"
    if key not in _FONT_PATHS:
        found: Optional[str] = None
        for candidate in FONT_CANDIDATES[key]:
            if Path(candidate).exists():
                found = candidate
                break
        _FONT_PATHS[key] = found
    return _FONT_PATHS[key]


def font(size1x: float, bold: bool = False) -> Any:
    """Шрифт нужного кегля в текущем масштабе (кэшируется)."""
    from PIL import ImageFont

    cache_key = (bold, max(6, int(round(size1x * SS))))
    if cache_key not in _FONTS:
        path = find_font(bold)
        if path is None:  # pragma: no cover - зависит от системы
            _FONTS[cache_key] = ImageFont.load_default()
        else:
            _FONTS[cache_key] = ImageFont.truetype(path, cache_key[1])
    return _FONTS[cache_key]


def _new(w1: float, h1: float) -> Any:
    from PIL import Image

    return Image.new("RGBA", (max(1, _px(w1)), max(1, _px(h1))), (0, 0, 0, 0))


def _text_width(draw: Any, text: str, size1x: float, bold: bool = False) -> int:
    box = draw.textbbox((0, 0), text, font=font(size1x, bold))
    return box[2] - box[0]


def _center_x(draw: Any, text: str, width1x: float, size1x: float, bold: bool = False) -> int:
    return max(0, (_px(width1x) - _text_width(draw, text, size1x, bold)) // 2)


# --------------------------------------------------------------------------- #
# Рисование «телефона» (координаты 1x = экранные пиксели макета)
# --------------------------------------------------------------------------- #
def draw_backdrop_phone(w1: float, h1: float) -> Any:
    from PIL import ImageDraw

    image = _new(w1, h1)
    ImageDraw.Draw(image).rounded_rectangle(
        [0, 0, _px(w1) - 1, _px(h1) - 1], radius=_px(CARD_RADIUS), fill=BACKGROUND
    )
    return image


def draw_header(w1: float) -> Any:
    from PIL import ImageDraw

    image = _new(w1, HEADER_H)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [0, 0, _px(w1) - 1, _px(HEADER_H) - 1 + _px(CARD_RADIUS)],
        radius=_px(CARD_RADIUS),
        fill=HEADER_BG,
    )
    draw.rectangle([0, _px(HEADER_H) - _px(CARD_RADIUS), _px(w1), _px(HEADER_H)],
                   fill=HEADER_BG)
    draw.line([0, _px(HEADER_H) - SS, _px(w1), _px(HEADER_H) - SS], fill=HEADER_LINE,
              width=max(1, int(SS)))

    name = texts.BOT_NAME
    draw.text((_center_x(draw, name, w1, 15, True), _px(15)), name,
              font=font(15, True), fill=BUBBLE_TEXT)
    status = f"@{BOT_USERNAME} · в сети"
    draw.text((_center_x(draw, status, w1, SMALL_FONT_SIZE), _px(40)), status,
              font=font(SMALL_FONT_SIZE), fill=NOTE_TEXT)
    return image


def draw_typing(active: int = 0) -> Any:
    from PIL import ImageDraw

    image = _new(TYPING_W, TYPING_H)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, _px(TYPING_W) - 1, _px(TYPING_H) - 1],
                           radius=_px(14), fill=BUBBLE_BG)
    radius = _px(3.4)
    for index in range(3):
        cx = _px(16 + index * 12)
        cy = _px(TYPING_H / 2)
        color = DOT_ON if index == active % 3 else DOT_OFF
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)
    return image


def bubble_height(text: str, note: str = "") -> float:
    lines = mockups.wrap(text)
    note_lines = mockups.wrap(note) if note else []
    return 18 + len(lines) * LINE_HEIGHT + len(note_lines) * (LINE_HEIGHT - 2) + 18


def draw_bubble(text: str, note: str = "") -> Any:
    from PIL import ImageDraw

    w1 = CARD_W1 - 2 * MARGIN
    h1 = bubble_height(text, note)
    image = _new(w1, h1)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, _px(w1) - 1, _px(h1) - 1], radius=_px(16),
                           fill=BUBBLE_BG)
    draw.text((_px(14), _px(12)), texts.BOT_NAME, font=font(SMALL_FONT_SIZE), fill=SENDER)

    y = 32.0
    for line in mockups.wrap(text):
        bold = line.endswith(":") and len(line) < 60
        draw.text((_px(14), _px(y)), line, font=font(FONT_SIZE, bold), fill=BUBBLE_TEXT)
        y += LINE_HEIGHT

    if note:
        y += 2
        for line in mockups.wrap(note):
            draw.text((_px(14), _px(y)), line, font=font(SMALL_FONT_SIZE), fill=NOTE_TEXT)
            y += LINE_HEIGHT - 2
    return image


def row_widths(labels: Sequence[str], total_width: float) -> List[float]:
    if len(labels) == 1:
        return [float(total_width)]
    widths = [float(mockups.button_width(label, int(total_width), len(labels)))
              for label in labels]
    needed = sum(widths) + 8 * (len(widths) - 1)
    if needed > total_width:
        ratio = total_width / needed
        widths = [width * ratio for width in widths]
    return widths


def draw_inline_row(labels: Sequence[str], primaries: Sequence[bool] = ()) -> Any:
    from PIL import ImageDraw

    total = CARD_W1 - 2 * MARGIN
    flags = list(primaries) + [False] * (len(labels) - len(primaries))
    widths = row_widths(labels, total)
    image = _new(total, ROW_H)
    draw = ImageDraw.Draw(image)

    x = 0.0
    for label, primary, width in zip(labels, flags, widths):
        box = [_px(x), 0, _px(x + width) - 1, _px(ROW_H) - 1]
        draw.rounded_rectangle(box, radius=_px(10),
                               fill=PRIMARY_BG if primary else BUTTON_BG)
        if not primary:
            draw.rounded_rectangle(box, radius=_px(10), outline=BUTTON_BORDER,
                                   width=max(1, int(SS)))
        draw.text(
            (_px(x) + (_px(width) - _text_width(draw, label, BUTTON_FONT_SIZE)) // 2,
             _px(9)),
            label,
            font=font(BUTTON_FONT_SIZE),
            fill=PRIMARY_TEXT if primary else BUTTON_TEXT,
        )
        x += width + 8
    return image


def draw_inline_rows_block(rows: Sequence[Sequence[str]]) -> Any:
    total = CARD_W1 - 2 * MARGIN
    height = max(1, len(rows)) * (ROW_H + ROW_GAP)
    block = _new(total, height)
    y = 0.0
    for row in rows:
        block.alpha_composite(draw_inline_row(list(row)), (0, _px(y)))
        y += ROW_H + ROW_GAP
    return block


def reply_height(rows: Sequence[Sequence[str]]) -> float:
    return len(rows) * (REPLY_ROW_H + 8) + 16


def draw_reply_keyboard(rows: Sequence[Sequence[str]]) -> Any:
    from PIL import ImageDraw

    h1 = reply_height(rows)
    image = _new(CARD_W1, h1)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, _px(CARD_W1), _px(h1)], fill=REPLY_BG)
    draw.line([0, 0, _px(CARD_W1), 0], fill=HEADER_LINE, width=max(1, int(SS)))

    total = CARD_W1 - 2 * MARGIN
    y = 12.0
    for row in rows:
        if not row:
            continue
        width = total / len(row) - 8
        x = float(MARGIN)
        for label in row:
            draw.rounded_rectangle(
                [_px(x), _px(y), _px(x + width) - 1, _px(y + REPLY_ROW_H) - 1],
                radius=_px(10), fill=REPLY_BUTTON_BG, outline=BUTTON_BORDER,
                width=max(1, int(SS)),
            )
            draw.text(
                (_px(x) + (_px(width) - _text_width(draw, label, BUTTON_FONT_SIZE)) // 2,
                 _px(y + 14)),
                label,
                font=font(BUTTON_FONT_SIZE), fill=BUBBLE_TEXT,
            )
            x += width + 8
        y += REPLY_ROW_H + 8
    return image


def draw_caption(text: str) -> Any:
    from PIL import ImageDraw

    image = _new(CARD_W1, CAPTION_H)
    draw = ImageDraw.Draw(image)
    draw.text((_center_x(draw, text, CARD_W1, SMALL_FONT_SIZE), 0), text,
              font=font(SMALL_FONT_SIZE), fill=NOTE_TEXT)
    return image


def draw_shadow(width: int, height: int, radius: int, offset: int = 10) -> Any:
    from PIL import Image, ImageDraw, ImageFilter

    pad = radius * 3
    image = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle(
        [pad, pad + offset, pad + width - 1, pad + height + offset - 1],
        radius=radius, fill=(20, 26, 38, 96),
    )
    return image.filter(ImageFilter.GaussianBlur(radius))


def draw_pointer(width: int, height: int) -> Any:
    """Подсвечивающее кольцо вокруг кнопки, на которую «нажимают»."""
    from PIL import Image, ImageDraw

    pad = 14
    image = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [2, 2, width + pad * 2 - 3, height + pad * 2 - 3],
        radius=18, outline=ACCENT, width=6,
    )
    return image


# --------------------------------------------------------------------------- #
# Рисование панели обучения (координаты 1x = итоговые px / 2)
# --------------------------------------------------------------------------- #
PANEL_STEP_FONT = 15
PANEL_TITLE_FONT = 26
PANEL_SUB_FONT = 13


_MEASURE: Dict[str, Any] = {}


def _measure_draw() -> Any:
    from PIL import Image, ImageDraw

    if "draw" not in _MEASURE:
        _MEASURE["draw"] = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    return _MEASURE["draw"]


def wrap_panel(text: str, width1: float) -> List[str]:
    """Переносит текст шага по реальной ширине панели (измерением, не на глаз)."""
    limit_px = max(80.0, (width1 - 34) * 2)
    draw = _measure_draw()
    lines: List[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            box = draw.textbbox((0, 0), candidate, font=font(PANEL_STEP_FONT, True))
            if box[2] - box[0] <= limit_px or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def draw_panel_heading(heading: str, number: int, total: int, width1: float) -> Any:
    """Заголовок карточки: «Выбор жанра» + «Карточка 2 из 3»."""
    from PIL import ImageDraw

    h1 = 64.0
    image = _new(width1, h1)
    draw = ImageDraw.Draw(image)
    draw.text((0, _px(2)), heading, font=font(PANEL_TITLE_FONT, True), fill=HEADING_COLOR)
    draw.text((0, _px(38)), f"Карточка {number} из {total} · обучение GameHunter",
              font=font(PANEL_SUB_FONT), fill=NOTE_TEXT)
    return image


def step_block_height(text: str, width1: float) -> float:
    return len(wrap_panel(text, width1 - 34)) * 21 + 30


def draw_panel_step(index: int, text: str, width1: float, done: bool = False) -> Any:
    """Строка шага обучения: кружок с номером (или ✔) и текст."""
    from PIL import ImageDraw

    lines = wrap_panel(text, width1 - 34)
    h1 = len(lines) * 21 + 30
    image = _new(width1, h1)
    draw = ImageDraw.Draw(image)

    cx, cy, r = _px(13), _px(15), _px(11)
    if done:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=NOTE_TEXT,
                     width=max(1, int(SS * 1.2)))
        draw.text((cx - _px(5), cy - _px(8)), "✓", font=font(12, True), fill=NOTE_TEXT)
        color = NOTE_TEXT
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
        digit = str(index)
        draw.text((cx - _text_width(draw, digit, 12, True) // 2, cy - _px(8)),
                  digit, font=font(12, True), fill="#FFFFFF")
        color = HEADING_COLOR

    y = 6.0
    for line in lines:
        draw.text((_px(34), _px(y)), line, font=font(PANEL_STEP_FONT, not done),
                  fill=color)
        y += 21
    return image


def draw_progress(current: int, total: int) -> Any:
    """Точки-индикаторы «какая карточка сейчас» внизу панели."""
    from PIL import ImageDraw

    image = _new(90, 14)
    draw = ImageDraw.Draw(image)
    for index in range(total):
        cx = _px(7 + index * 26)
        cy = _px(7)
        r = _px(6 if index + 1 == current else 4)
        color = ACCENT if index + 1 == current else DOT_OFF
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    return image


# --------------------------------------------------------------------------- #
# Раскладка
# --------------------------------------------------------------------------- #
def screen_by_file(screen_file: str) -> Any:
    for screen in mockups.SCREENS:
        if screen.file == screen_file:
            return screen
    raise KeyError(f"Экран {screen_file} не найден среди мокапов")


def genre_variants() -> Dict[str, Tuple[str, Tuple[Tuple[str, ...], ...]]]:
    genres = mockups.GENRES
    variants: Dict[str, Tuple[str, Tuple[Tuple[str, ...], ...]]] = {}
    for stage, selected in (
        ("none", ()),
        ("one", (mockups.SELECTED_GENRES[0],)),
        ("two", tuple(mockups.SELECTED_GENRES)),
    ):
        message = texts.format_genres_selection(
            genres, selected, title=texts.GENRES_TITLE, footer=texts.GENRES_FOOTER
        )
        rows = mockups.labels_of(keyboards.picking_genres_keyboard(genres, selected))
        variants[stage] = (message, rows)
    return variants


def build_layers(card: Card) -> Dict[str, Any]:
    """Собирает слои карточки: «телефон» (phone) и панель обучения (canvas)."""
    screen = screen_by_file(card.screen_file)

    bubble_text: str = screen.text
    bubble_note: str = screen.note
    inline_rows: List[Tuple[str, ...]] = [tuple(row) for row in screen.buttons]
    variants: Dict[str, Tuple[str, Tuple[Tuple[str, ...], ...]]] = {}
    if card.key == "03_picking_genres":
        stages = genre_variants()
        bubble_text, rows_none = stages["none"]
        inline_rows = [tuple(row) for row in rows_none]
        variants = {"one": stages["one"], "two": stages["two"]}

    content_top = HEADER_H + 16
    bubble_h = bubble_height(bubble_text, bubble_note)
    delta_h = 0.0
    if variants:
        delta_h = max(bubble_height(message, bubble_note)
                      for message, _ in variants.values()) - bubble_h
    rows_top = content_top + bubble_h + 12
    y = rows_top
    row_positions: List[float] = []
    for _ in inline_rows:
        row_positions.append(y)
        y += ROW_H + ROW_GAP
    y += delta_h

    reply_rows = [tuple(row) for row in screen.keyboard]
    reply_y = y + 4
    if reply_rows:
        y = reply_y + reply_height(reply_rows)
    caption_y = y + 8
    card_h = caption_y + CAPTION_H + 12

    # --- слои телефона (масштаб задаётся перед рисованием) --------------- #
    scale = phone_scale(card_h)
    set_ss(scale)
    phone: List[LayerSpec] = []

    def add_phone(name: str, x1: float, y1: float, image: Any) -> None:
        phone.append(
            LayerSpec(name=name, order=len(phone) + 1, space="phone",
                      x1=x1, y1=y1, w1=image.size[0] / scale, h1=image.size[1] / scale,
                      image=image)
        )

    add_phone("backdrop", 0, 0, draw_backdrop_phone(CARD_W1, card_h))
    add_phone("header", 0, 0, draw_header(CARD_W1))
    for index in range(3):
        add_phone(f"typing_{index}", MARGIN, content_top + bubble_h - TYPING_H - 12,
                  draw_typing(index))
    add_phone("bubble", MARGIN, content_top, draw_bubble(bubble_text, bubble_note))
    for index, row in enumerate(inline_rows, start=1):
        pairs = mockups.normalize_rows([row])[0]
        add_phone(f"inline_{index}", MARGIN, row_positions[index - 1],
                  draw_inline_row([label for label, _ in pairs],
                                  [flag for _, flag in pairs]))
    shift = 0.0
    for stage, (message, rows) in variants.items():
        add_phone(f"bubble_{stage}", MARGIN, content_top, draw_bubble(message, bubble_note))
        add_phone(f"rows_{stage}", MARGIN, row_positions[0] + shift,
                  draw_inline_rows_block(rows))
        shift = delta_h
    if reply_rows:
        add_phone("reply_keyboard", 0, reply_y, draw_reply_keyboard(reply_rows))
    add_phone("caption", 0, caption_y, draw_caption(screen.caption))

    # --- панель обучения (1x = итог / 2) --------------------------------- #
    set_ss(2.0)
    phone_w = CARD_W1 * scale
    panel_x1 = (PAD + phone_w + PHONE_GAP) / 2
    panel_w1 = (CANVAS_W - PAD) / 2 - panel_x1

    canvas: List[LayerSpec] = []

    def add_canvas(name: str, x1: float, y1: float, image: Any) -> None:
        canvas.append(
            LayerSpec(name=name, order=len(canvas) + 1, space="canvas",
                      x1=x1, y1=y1, w1=image.size[0] / 2, h1=image.size[1] / 2,
                      image=image)
        )

    add_canvas("panel_heading", panel_x1, 62,
               draw_panel_heading(card.heading,
                                  TUTORIAL_CARDS.index(card.key) + 1,
                                  len(TUTORIAL_CARDS), panel_w1))

    step_y = 148.0
    step_texts = texts.TUTORIAL_STEPS.get(card.key, ())
    for index, text in enumerate(step_texts, start=1):
        add_canvas(f"step_{index}_on", panel_x1, step_y,
                   draw_panel_step(index, text, panel_w1, done=False))
        add_canvas(f"step_{index}_off", panel_x1, step_y,
                   draw_panel_step(index, text, panel_w1, done=True))
        step_y += step_block_height(text, panel_w1)

    add_canvas("progress", panel_x1, CANVAS1_H - 46,
               draw_progress(TUTORIAL_CARDS.index(card.key) + 1, len(TUTORIAL_CARDS)))

    set_ss(2.0)
    return {
        "phone": phone,
        "canvas": canvas,
        "card_h1": card_h,
        "delta_h": delta_h,
        "scale": scale,
        "panel_x1": panel_x1,
        "step_count": len(step_texts),
    }


# --------------------------------------------------------------------------- #
# Раскадровка
# --------------------------------------------------------------------------- #
def intro_steps(bubble_start: float) -> List[Step]:
    return [
        Step("shadow", "fade", 0.00, 0.35),
        Step("backdrop", "fade", 0.00, 0.35),
        Step("header", "slide_up", 0.05, 0.45, offset=10),
        Step("typing_0", "pop", 0.45, 0.22, ease="back_out"),
        Step("typing_0", "hide", 0.62, 0.01, ease="linear"),
        Step("typing_1", "pop", 0.62, 0.01, ease="linear"),
        Step("typing_1", "hide", 0.79, 0.01, ease="linear"),
        Step("typing_2", "pop", 0.79, 0.01, ease="linear"),
        Step("typing_2", "hide", bubble_start - 0.25, 0.18),
        Step("bubble", "slide_up", bubble_start, 0.55, offset=26),
        Step("panel_heading", "slide_up", 0.10, 0.5, offset=12),
        Step("progress", "fade", 0.30, 0.5),
    ]


def panel_steps(card: Card) -> List[Step]:
    """Шаги панели обучения: загораются по одному, предыдущий гаснет в «✔»."""
    steps: List[Step] = []
    total = card.step_times
    for index, moment in enumerate(total, start=1):
        steps.append(Step(f"step_{index}_on", "fade", moment, 0.35))
        if index < len(total):
            steps.append(Step(f"step_{index}_on", "hide", total[index] - 0.05, 0.12))
            steps.append(Step(f"step_{index}_off", "fade", total[index] - 0.05, 0.25))
    return steps


def inline_names(layers: Sequence[LayerSpec]) -> List[str]:
    numbers = sorted(
        int(layer.name.split("_", 1)[1])
        for layer in layers
        if layer.name.startswith("inline_") and layer.name.split("_", 1)[1].isdigit()
    )
    return [f"inline_{number}" for number in numbers]


def build_steps(card: Card, layout: Dict[str, Any]) -> List[Step]:
    """Раскадровка карточки: телефон + панель + подсветка нажатий."""
    phone = layout["phone"]
    names = {layer.name for layer in phone} | {layer.name for layer in layout["canvas"]}
    delta_h: float = layout["delta_h"]
    steps: List[Step] = list(intro_steps(1.05 if card.key == "01_start" else 1.00))
    steps += panel_steps(card)
    taps: List[Tuple[float, str]] = []

    if card.key == "01_start":
        steps.append(Step("reply_keyboard", "keyboard_up", 1.75, 0.45, offset=70))
        steps.append(Step("reply_keyboard", "tap", 2.55, 0.35))
        taps.append((2.55, "reply_keyboard"))
        steps.append(Step("caption", "fade", 2.30, 0.45))

    elif card.key == "03_picking_genres":
        rows = inline_names(phone)
        for index, name in enumerate(rows):
            steps.append(Step(name, "slide_up", 1.65 + index * 0.11, 0.38, offset=14))
        steps.append(Step("inline_1", "tap", 3.30, 0.30))
        taps.append((3.30, "inline_1"))
        steps.append(Step("bubble", "hide", 3.42, 0.10))
        steps.append(Step("bubble_one", "fade", 3.42, 0.18))
        for name in rows:
            steps.append(Step(name, "hide", 3.42, 0.01, ease="linear"))
        steps.append(Step("rows_one", "pop", 3.42, 0.24, ease="back_out"))
        if delta_h:
            steps.append(Step("rows_one", "shift_down", 3.50, 0.30, offset=delta_h))
        steps.append(Step("rows_one", "tap", 4.30, 0.30))
        taps.append((4.30, "rows_one"))
        steps.append(Step("bubble_one", "hide", 4.42, 0.10))
        steps.append(Step("bubble_two", "fade", 4.42, 0.18))
        steps.append(Step("rows_one", "hide", 4.42, 0.01, ease="linear"))
        steps.append(Step("rows_two", "pop", 4.42, 0.24, ease="back_out"))
        steps.append(Step("caption", "fade", 5.15, 0.45))

    else:  # 04_game_list
        rows = inline_names(phone)
        for index, name in enumerate(rows):
            steps.append(Step(name, "slide_up", 1.70 + index * 0.13, 0.40, offset=16))
        steps.append(Step("inline_1", "tap", 4.60, 0.34))
        taps.append((4.60, "inline_1"))
        steps.append(Step("caption", "fade", 5.20, 0.45))

    # подсветка кнопки в момент «нажатия»
    for index, (moment, target) in enumerate(taps, start=1):
        steps.append(Step(f"pointer_{index}", "pop", moment, 0.25, ease="back_out"))
        steps.append(Step(f"pointer_{index}", "hide", moment + 1.0, 0.3))

    unknown = {step.layer for step in steps} - (names | {"shadow"} |
                                                {f"pointer_{i}" for i in range(1, 5)})
    if unknown:  # pragma: no cover - защита от опечатки в раскадровке
        raise RuntimeError(f"В раскадровке есть несуществующие слои: {sorted(unknown)}")
    return sorted(steps, key=lambda step: (step.start, step.layer)), taps


# --------------------------------------------------------------------------- #
# Рендер кадров
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RenderedLayer:
    name: str
    order: int
    space: str
    image: Any
    x: int
    y: int
    width: int
    height: int


def render_layers(layout: Dict[str, Any]) -> Tuple[List[RenderedLayer], Dict[str, Any]]:
    """Считает итоговые позиции слоёв телефона и панели на канве 1920×1080."""
    scale: float = layout["scale"]
    card_h1: float = layout["card_h1"]
    phone_w = int(round(CARD_W1 * scale))
    phone_h = int(round(card_h1 * scale))
    phone_x = PAD
    phone_y = (CANVAS_H - phone_h) // 2

    rendered: List[RenderedLayer] = []
    for layer in layout["phone"]:
        rendered.append(
            RenderedLayer(
                name=layer.name, order=layer.order, space="phone", image=layer.image,
                x=phone_x + int(round(layer.x1 * scale)),
                y=phone_y + int(round(layer.y1 * scale)),
                width=layer.image.size[0], height=layer.image.size[1],
            )
        )
    for layer in layout["canvas"]:
        rendered.append(
            RenderedLayer(
                name=layer.name, order=100 + layer.order, space="canvas",
                image=layer.image,
                x=int(round(layer.x1 * 2)), y=int(round(layer.y1 * 2)),
                width=layer.image.size[0], height=layer.image.size[1],
            )
        )

    shadow = draw_shadow(phone_w, phone_h, max(8, int(round(12 * scale))),
                         offset=int(round(6 * scale)))
    pad = (shadow.size[0] - phone_w) // 2
    rendered.insert(
        0,
        RenderedLayer(name="shadow", order=0, space="phone", image=shadow,
                      x=phone_x - pad, y=phone_y - pad,
                      width=shadow.size[0], height=shadow.size[1]),
    )
    geometry = {"phone": (phone_x, phone_y, phone_w, phone_h)}
    return rendered, geometry


def add_pointers(rendered: List[RenderedLayer],
                 taps: Sequence[Tuple[float, str]]) -> List[RenderedLayer]:
    """Добавляет слои-кольца подсветки вокруг кнопок в моменты нажатий."""
    by_name = {layer.name: layer for layer in rendered}
    for index, (_, target) in enumerate(taps, start=1):
        target_layer = by_name.get(target)
        if target_layer is None:
            continue
        ring = draw_pointer(target_layer.width, target_layer.height)
        rendered.append(
            RenderedLayer(
                name=f"pointer_{index}", order=200 + index, space="phone", image=ring,
                x=target_layer.x - 14, y=target_layer.y - 14,
                width=ring.size[0], height=ring.size[1],
            )
        )
    return rendered


def paste_clipped(canvas: Any, image: Any, x: int, y: int) -> None:
    width, height = image.size
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(width, canvas.size[0] - x), min(height, canvas.size[1] - y)
    if right <= left or bottom <= top:
        return
    canvas.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def compose_frame(rendered: Sequence[RenderedLayer],
                  steps_by_layer: Dict[str, List[Step]], time: float,
                  backdrop: Any, scale: float) -> Any:
    canvas = backdrop.copy()
    for layer in rendered:
        alpha, dy1, layer_scale = layer_state(steps_by_layer.get(layer.name, []), time)
        if alpha <= 0.01:
            continue
        image = layer.image
        # смещения телефона заданы в его 1x, панели — в канвасных 1x (итог / 2)
        factor = scale if layer.space == "phone" else 2.0
        x, y = layer.x, layer.y + int(round(dy1 * factor))
        if abs(layer_scale - 1.0) > 0.002:
            width = max(1, int(round(image.size[0] * layer_scale)))
            height = max(1, int(round(image.size[1] * layer_scale)))
            resized = image.resize((width, height))
            x += (image.size[0] - width) // 2
            y += (image.size[1] - height) // 2
            image = resized
        if alpha < 0.999:
            faded = image.copy()
            faded.putalpha(image.getchannel("A").point(lambda v: int(v * alpha)))
            image = faded
        paste_clipped(canvas, image, x, y)
    return canvas


def frame_times(duration: float, fps: int) -> List[float]:
    count = max(2, int(round(duration * fps)))
    return [index / fps for index in range(count)] + [duration]


def frame_cs(index: int, fps: int) -> int:
    """Длительность кадра в сотых секунды (единица хранения GIF).

    Точные 60 fps в сотых не выразить (1.67 сотых), поэтому чередуем
    паттерн [2, 2, 1] — в среднем ровно 1/60 c, и суммарная длительность
    ролика совпадает с заданной.
    """
    if fps >= 55:
        return (2, 2, 1)[index % 3]
    return max(1, round(100 / fps))


def iter_card_frames(rendered: Sequence[RenderedLayer], steps: Sequence[Step],
                     duration: float, fps: int, scale: float,
                     backdrop_color: Optional[str]) -> Any:
    """Генератор кадров: по одному в памяти (иначе 450 кадров 1920×1080 = OOM).

    Одинаковые кадры подряд не выдаются повторно: вызывающий сам суммирует
    их длительности (Pillow молча выбрасывает дубликаты без суммы duration).
    """
    from PIL import Image

    backdrop = Image.new("RGBA", (CANVAS_W, CANVAS_H),
                         backdrop_color if backdrop_color else (0, 0, 0, 0))
    steps_by_layer: Dict[str, List[Step]] = {}
    for step in steps:
        steps_by_layer.setdefault(step.layer, []).append(step)

    animation_end = max((step.start + step.duration for step in steps), default=0.0)
    previous: Optional[bytes] = None
    for time in frame_times(duration, fps):
        if time >= animation_end and previous is not None:
            return
        frame = compose_frame(rendered, steps_by_layer, time, backdrop, scale)
        digest = frame.tobytes()
        if digest == previous:
            continue
        previous = digest
        yield frame


def render_card_frames(rendered: Sequence[RenderedLayer], steps: Sequence[Step],
                       duration: float, fps: int, scale: float,
                       backdrop_color: Optional[str]) -> Tuple[List[Any], List[int]]:
    """Кадры и длительности (для тестов и разовых проверок)."""
    frames = list(iter_card_frames(rendered, steps, duration, fps, scale, backdrop_color))
    durations = [frame_cs(i, fps) * 10 for i in range(len(frames))]
    if durations:
        durations[-1] += max(0, int(round(duration * 1000)) - sum(durations))
    return frames, durations


def export_card_frames(rendered: Sequence[RenderedLayer], steps: Sequence[Step],
                       duration: float, fps: int, scale: float,
                       backdrop_color: Optional[str], gif_path: Optional[Path],
                       frames_dir: Optional[Path], colors: int = 128,
                       width: int = 0) -> Tuple[int, int]:
    """Один проход по кадрам: GIF (покадровая палитра) и/или PNG-последовательность.

    Возвращает (размер GIF в байтах, число сохранённых PNG-кадров).
    """
    from PIL import Image

    total_ms = int(round(duration * 1000))
    prepared: List[Any] = []
    durations: List[int] = []
    last_digest: Optional[bytes] = None
    frames_count = 0
    pattern_index = 0

    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)

    for frame in iter_card_frames(rendered, steps, duration, fps, scale, backdrop_color):
        image = frame
        if width and image.size[0] != width:
            height = max(1, round(image.size[1] * width / image.size[0]))
            image = image.resize((width, height), Image.LANCZOS)
        rgb = image.convert("RGB")
        if frames_dir is not None:
            frames_count += 1
            frame.save(frames_dir / f"frame_{frames_count:04d}.png")
        digest = rgb.tobytes()
        step_ms = frame_cs(pattern_index, fps) * 10
        pattern_index += 1
        if digest == last_digest:
            durations[-1] += step_ms
            continue
        last_digest = digest
        prepared.append(rgb.convert("P", palette=Image.ADAPTIVE, colors=colors))
        durations.append(step_ms)

    if durations:
        durations[-1] += max(0, total_ms - sum(durations))

    gif_size = 0
    if gif_path is not None and prepared:
        gif_path.parent.mkdir(parents=True, exist_ok=True)
        prepared[0].save(
            gif_path, save_all=True, append_images=prepared[1:],
            duration=durations, loop=0, optimize=True, format="GIF",
        )
        gif_size = gif_path.stat().st_size
    return gif_size, frames_count


# --------------------------------------------------------------------------- #
# Сборка карточки и экспорт
# --------------------------------------------------------------------------- #
def build_card_payload(card: Card, assets_dir: Path, ae_dir: Path, fps: int,
                       backdrop_name: str, gif_width: int, write_gif: bool,
                       write_frames: bool) -> Dict[str, Any]:
    layout = build_layers(card)
    scale: float = layout["scale"]
    steps, taps = build_steps(card, layout)
    rendered, geometry = render_layers(layout)
    rendered = add_pointers(rendered, taps)

    layers_dir = ae_dir / "layers" / card.key
    layers_dir.mkdir(parents=True, exist_ok=True)
    for layer in rendered:
        if layer.name in {"shadow"}:
            continue
        layer.image.save(layers_dir / f"{layer.order:03d}_{layer.name}.png")

    gif_path = assets_dir / f"{card.key}.gif"
    gif_size, frames_count = export_card_frames(
        rendered, steps, card.duration, fps, scale, BACKDROPS.get(backdrop_name),
        gif_path if (write_gif and BACKDROPS.get(backdrop_name) is not None) else None,
        ae_dir / "frames" / card.key if write_frames else None,
        width=gif_width,
    )

    screen = screen_by_file(card.screen_file)
    phone_x, phone_y, phone_w, phone_h = geometry["phone"]
    return {
        "key": card.key,
        "title": screen.title,
        "heading": card.heading,
        "description": card.description,
        "tutorial_steps": list(texts.TUTORIAL_STEPS.get(card.key, ())),
        "canvas": {"width": CANVAS_W, "height": CANVAS_H},
        "phone": {"x": phone_x, "y": phone_y, "width": phone_w, "height": phone_h},
        "scale": round(scale, 3),
        "duration_seconds": card.duration,
        "gif_fps": fps,
        "ae_fps": AE_FPS,
        "gif_file": f"gamehunter/assets/tutorial/{card.key}.gif" if gif_size else None,
        "gif_bytes": gif_size,
        "frames_exported": frames_count,
        "layers": [
            {
                "name": layer.name,
                "space": layer.space,
                "file": f"layers/{card.key}/{layer.order:03d}_{layer.name}.png",
                "x": layer.x,
                "y": layer.y,
                "width": layer.width,
                "height": layer.height,
                "z": layer.order,
            }
            for layer in rendered
        ],
        "steps": [step.to_payload() for step in steps],
        "ae_text_layers": [
            {"role": "заголовок", "text": card.heading, "font_size_px": 52,
             "color": HEADING_COLOR},
            {"role": "описание", "text": card.description, "font_size_px": 30,
             "color": "#4A5568"},
        ],
    }


PREVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GameHunter — обучающие карточки 16:9, 60 fps</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 40px 20px 64px; background: #EDF1F7; color: #16202E;
         font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  h1 {{ font-size: 30px; margin: 0 0 8px; }}
  .lead {{ margin: 0 0 32px; color: #4A5568; font-size: 16px; line-height: 1.55; }}
  section {{ background: #fff; border-radius: 18px; padding: 20px 20px 24px;
             box-shadow: 0 10px 30px rgba(20, 30, 50, .10); margin-bottom: 28px; }}
  section img {{ width: 100%; height: auto; border-radius: 12px; display: block; }}
  h2 {{ font-size: 22px; margin: 18px 0 6px; }}
  p {{ margin: 0 0 10px; color: #4A5568; font-size: 15px; line-height: 1.55; }}
  ol {{ margin: 0 0 12px; padding-left: 22px; color: #4A5568; font-size: 15px;
        line-height: 1.6; }}
  code {{ background: #F1F4F9; border-radius: 6px; padding: 1px 6px; font-size: 13px; }}
  .meta {{ font-size: 13px; color: #7A8699; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Обучающие карточки GameHunter — 16:9, 60 fps</h1>
  <p class="lead">
    Слева — «телефон» с настоящим интерфейсом бота, справа — шаги обучения,
    в момент нажатия кнопка подсвечивается кольцом. Эти же GIF бот отправляет
    на экране «🎬 Как пользоваться». Слои для After Effects —
    <code>docs/ae/layers/</code>, раскадровка — <code>docs/ae/timeline.json</code>.
  </p>
{sections}
</div>
</body>
</html>
"""

SECTION_TEMPLATE = """  <section>
    <img src="{gif}" alt="{heading} — обучающая карточка GameHunter">
    <h2>{index}. {heading}</h2>
    <p>{description}</p>
    <ol>
{steps_html}
    </ol>
    <p class="meta">{title} · 1920×1080 · 60 fps · {duration} с{size} ·
    <code>{gif}</code></p>
  </section>"""


def preview_html(payloads: Sequence[Dict[str, Any]], fps: int) -> str:
    sections: List[str] = []
    for index, payload in enumerate(payloads, start=1):
        size = payload.get("gif_bytes") or 0
        steps_html = "\n".join(
            f"      <li>{step}</li>" for step in payload["tutorial_steps"]
        )
        sections.append(
            SECTION_TEMPLATE.format(
                gif=f"../../{payload['gif_file']}" if payload.get("gif_file") else "",
                heading=payload["heading"],
                description=payload["description"],
                title=payload["title"],
                steps_html=steps_html,
                duration=payload["duration_seconds"],
                index=index,
                size=f" · GIF {size / 1024 / 1024:.2f} МБ" if size else "",
            )
        )
    return PREVIEW_TEMPLATE.format(sections="\n".join(sections))


JSX_TEMPLATE = """// GameHunter: импорт слоёв обучающей карточки в After Effects.
//
// Как пользоваться:
//   1. File -> Scripts -> Run Script File... и выберите этот файл.
//   2. Укажите папку docs/ae/layers/<экран> (например, 01_start).
//   3. Скрипт создаст композицию {width}x{height}, {fps} fps, разложит слои и
//      проставит ключевые кадры Opacity/Position из timeline.json.
//
// Эффекты «pop», «tap» и «shift_down» доделайте вручную по раскадровке
// (docs/10_ae_animaciya_kartochek.md): Scale с Easy Ease (F9).
(function () {{
    var WIDTH = {width}, HEIGHT = {height}, FPS = {fps};

    var layersFolder = Folder.selectDialog("Выберите папку слоёв (docs/ae/layers/<экран>)");
    if (!layersFolder) return;

    var cardKey = layersFolder.name;
    var timelineFile = new File(layersFolder.parent.parent.fsName + "/timeline.json");
    var cardInfo = null;
    if (timelineFile.exists) {{
        timelineFile.open("r");
        timelineFile.encoding = "UTF-8";
        var raw = timelineFile.read();
        timelineFile.close();
        try {{
            var timeline = JSON.parse(raw);
            for (var i = 0; i < timeline.cards.length; i++) {{
                if (timeline.cards[i].key === cardKey) cardInfo = timeline.cards[i];
            }}
        }} catch (e) {{ cardInfo = null; }}
    }}

    app.beginUndoGroup("GameHunter: карточка " + cardKey);
    var comp = app.project.items.addComp(
        "GameHunter " + cardKey, WIDTH, HEIGHT, 1,
        cardInfo ? cardInfo.duration_seconds : 6, FPS
    );

    var files = layersFolder.getFiles(function (f) {{
        return f instanceof File && /\\.png$/i.test(f.name);
    }});
    files.sort(function (a, b) {{ return a.name < b.name ? -1 : 1; }});

    var added = [];
    for (var k = files.length - 1; k >= 0; k--) {{
        var item = app.project.importFile(new ImportOptions(files[k]));
        var layer = comp.layers.add(item);
        added.push(layer);
        if (cardInfo) {{
            var shortName = item.name.replace(/\\.png$/i, "").replace(/^\\d+_/, "");
            for (var m = 0; m < cardInfo.layers.length; m++) {{
                var meta = cardInfo.layers[m];
                if (meta.name === shortName) {{
                    layer.property("Position").setValue(
                        [meta.x + meta.width / 2, meta.y + meta.height / 2]
                    );
                }}
            }}
        }}
    }}

    if (cardInfo) {{
        for (var s = 0; s < cardInfo.steps.length; s++) {{
            var step = cardInfo.steps[s];
            if (step.effect !== "fade" && step.effect !== "slide_up"
                && step.effect !== "hide") continue;
            for (var L = 1; L <= comp.numLayers; L++) {{
                var cl = comp.layer(L);
                if (cl.name.replace(/^\\d+_/, "").replace(/\\.png$/i, "") !== step.layer) continue;
                var t0 = step.start_s, t1 = step.start_s + step.duration_s;
                var op = cl.property("Opacity");
                if (step.effect === "hide") {{
                    op.setValueAtTime(t0, 100);
                    op.setValueAtTime(t1, 0);
                }} else {{
                    op.setValueAtTime(t0, 0);
                    op.setValueAtTime(t1, 100);
                }}
                if (step.effect === "slide_up") {{
                    var pos = cl.property("Position");
                    var base = pos.value;
                    var factor = (cardInfo.layers && step.layer.indexOf("step_") === 0
                        || step.layer === "panel_heading" || step.layer === "progress") ? 2 : cardInfo.scale;
                    pos.setValueAtTime(t0, [base[0], base[1] + step.offset_px * factor]);
                    pos.setValueAtTime(t1, base);
                }}
            }}
        }}
    }}

    comp.openInViewer();
    app.endUndoGroup();
    alert("Композиция «GameHunter " + cardKey + "» готова.\\nСлоёв: " + added.length);
}})();
"""


def write_outputs(ae_dir: Path, payloads: Sequence[Dict[str, Any]], fps: int) -> List[Path]:
    ae_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = ae_dir / "timeline.json"
    timeline_path.write_text(
        json.dumps(
            {
                "project": texts.BOT_NAME,
                "generated_by": "scripts/generate_ae_assets.py",
                "canvas": {"width": CANVAS_W, "height": CANVAS_H},
                "aspect": "16:9",
                "ae_fps": AE_FPS,
                "gif_fps": fps,
                "palette": {
                    "background": BACKGROUND,
                    "bubble": BUBBLE_BG,
                    "accent": ACCENT,
                    "text": BUBBLE_TEXT,
                    "note": NOTE_TEXT,
                    "heading": HEADING_COLOR,
                },
                "cards": payloads,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    preview_path = ae_dir / "preview.html"
    preview_path.write_text(preview_html(payloads, fps), encoding="utf-8")

    jsx_path = ae_dir / "import_layers.jsx"
    jsx_path.write_text(
        JSX_TEMPLATE.format(width=CANVAS_W, height=CANVAS_H, fps=AE_FPS), encoding="utf-8"
    )
    return [timeline_path, preview_path, jsx_path]


def generate(output_ae: Path = AE_OUTPUT, output_assets: Path = ASSETS_OUTPUT,
             fps: int = DEFAULT_GIF_FPS, backdrop: str = "light",
             gif_width: int = DEFAULT_GIF_WIDTH, only: Optional[str] = None,
             write_frames: bool = False, write_gif: bool = True) -> List[Path]:
    cards = [card for card in CARDS if only in (None, card.key)]
    if not cards:
        raise SystemExit(
            f"Карточка {only!r} не найдена. Доступны: {', '.join(c.key for c in CARDS)}"
        )

    payloads: List[Dict[str, Any]] = []
    for card in cards:
        payload = build_card_payload(
            card, output_assets, output_ae, fps=fps, backdrop_name=backdrop,
            gif_width=gif_width, write_gif=write_gif, write_frames=write_frames,
        )
        size = (payload.get("gif_bytes") or 0) / 1024 / 1024
        phone = payload["phone"]
        print(
            f"  {card.key:<18} телефон {phone['width']}x{phone['height']} px, "
            f"слоёв {len(payload['layers'])}, шагов {len(payload['steps'])}, "
            f"{payload['duration_seconds']} с" + (f", GIF {size:.2f} МБ" if size else "")
        )
        payloads.append(payload)

    written = write_outputs(output_ae, payloads, fps)
    for path in written:
        print(f"  {path.relative_to(PROJECT_ROOT)}")
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Обучающие карточки 16:9 для бота и AE")
    parser.add_argument("--out", default=str(AE_OUTPUT), help="каталог AE-ассетов")
    parser.add_argument("--assets", default=str(ASSETS_OUTPUT),
                        help="каталог GIF для бота")
    parser.add_argument("--fps", type=int, default=DEFAULT_GIF_FPS, help="кадры в секунду GIF")
    parser.add_argument("--gif-width", type=int, default=DEFAULT_GIF_WIDTH,
                        help="ширина GIF в px (0 — как канва 1920)")
    parser.add_argument("--backdrop", choices=sorted(BACKDROPS), default="light",
                        help="фон кадра: light, dark или none")
    parser.add_argument("--only", default=None, help="собрать одну карточку")
    parser.add_argument("--frames", action="store_true",
                        help="сохранить PNG-последовательность кадров")
    parser.add_argument("--no-gif", action="store_true", help="не сохранять GIF")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        import PIL  # noqa: F401
    except ImportError:  # pragma: no cover - зависит от окружения
        print(
            "Нужен Pillow: pip install pillow\n"
            "Он используется только для генерации карточек и не нужен самому боту.",
            file=sys.stderr,
        )
        return 1

    print("Собираем обучающие карточки GameHunter (16:9, 60 fps)…")
    generate(
        Path(args.out), Path(args.assets), fps=args.fps, backdrop=args.backdrop,
        gif_width=args.gif_width, only=args.only, write_frames=args.frames,
        write_gif=not args.no_gif,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
