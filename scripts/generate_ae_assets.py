#!/usr/bin/env python3
"""Генератор анимированных карточек интерфейса для Adobe After Effects.

Скрипт собирает в `docs/ae` всё, что нужно, чтобы сделать три анимированные
карточки (приветствие, выбор жанра, выбор игры) в After Effects и получить GIF:

    cards/<экран>.gif        — черновая анимация карточки (готовый GIF)
    layers/<экран>/*.png     — слои карточки с прозрачностью (импорт в AE)
    timeline.json            — тайминг-шит: слои, секунды, кадры AE (30 fps), easing
    preview.html             — страница «карточка сверху + текст снизу» (живое превью)
    import_layers.jsx        — скрипт для AE: импорт слоёв, сборка композиции,
                               расстановка ключевых кадров по timeline.json

Тексты сообщений и подписи кнопок берутся из кода бота — через генератор мокапов
`scripts/generate_mockups.py` (модули `gamehunter.presentation.texts` и
`gamehunter.presentation.keyboards`). Поэтому карточки соответствуют настоящему
интерфейсу бота, а после правки текстов их можно пересобрать: `make ae-assets`.

Запуск:
    python scripts/generate_ae_assets.py [--out docs/ae] [--fps 15] [--gif-width 720]
                                         [--backdrop light|dark|none]
                                         [--only 01_start] [--frames]

Нужен Pillow (только для генерации ассетов, в рантайме бота не используется):
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
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "ae"

# --------------------------------------------------------------------------- #
# Размеры и палитра (координаты «1x» совпадают с мокапами docs/mockups)
# --------------------------------------------------------------------------- #
CANVAS_W = 1080          # канва карточки 4:5 — удобно для презентаций и соцсетей
CANVAS_H = 1350
CANVAS_PAD = 54          # отступ карточки от края канвы (там же живёт тень)
SS = 3                   # суперсэмплинг: рисуем втрое крупнее и уменьшаем
AE_FPS = 30              # частота кадров тайминг-шита для After Effects
DEFAULT_GIF_FPS = 15     # частота кадров чернового GIF
DEFAULT_GIF_WIDTH = 720  # ширина GIF (слои для AE остаются полноразмерными)

CARD_W1 = 375            # ширина «телефона» в координатах 1x
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


# --------------------------------------------------------------------------- #
# Карточки: какие экраны анимируем и какой текст к ним подписываем
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Card:
    """Описание одной анимированной карточки."""

    key: str            # имя файлов: "01_start"
    screen_file: str    # экран из мокапов
    heading: str        # заголовок для превью и текстового слоя AE
    description: str    # поясняющий текст под карточкой
    duration: float     # длительность анимации, секунд


CARDS: Tuple[Card, ...] = (
    Card(
        key="01_start",
        screen_file="01_start",
        heading="Приветствие",
        description=(
            "Первое сообщение бота после /start: коротко о том, что он умеет, "
            "и кнопка «Старт». Появление сообщения повторяет настоящий Telegram — "
            "сначала «печатает…», затем пузырь текста и клавиатура."
        ),
        duration=6.0,
    ),
    Card(
        key="03_picking_genres",
        screen_file="03_picking_genres",
        heading="Выбор жанра",
        description=(
            "Бот предлагает жанры; отметка ✔ появляется сразу после нажатия, "
            "а текст сообщения и строка «Выбрано: …» обновляются. В конце — "
            "кнопка «Показать подборку»."
        ),
        duration=7.5,
    ),
    Card(
        key="04_game_list",
        screen_file="04_game_list",
        heading="Выбор игры",
        description=(
            "Подборка игр по анкете: фильтры, номер страницы и игры, в которые "
            "пользователь ещё не играл. Нажатие на строку ведёт в карточку игры "
            "с обложкой из RAWG."
        ),
        duration=7.5,
    ),
)


# --------------------------------------------------------------------------- #
# Слои и шаги анимации
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Step:
    """Один шаг анимации слоя (время в секундах)."""

    layer: str
    effect: str                 # fade | slide_up | pop | keyboard_up | tap | hide
    start: float
    duration: float = 0.4
    ease: str = "ease_out"
    offset: float = 0.0         # смещение в px (координаты 1x) для slide/keyboard
    amplitude: float = 0.06     # глубина «нажатия» для tap

    def to_payload(self) -> Dict[str, Any]:
        """Шаг в виде JSON — с номерами кадров для After Effects (30 fps)."""
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
    """Слой карточки: имя, порядок и положение в координатах 1x."""

    name: str
    order: int
    x1: float
    y1: float
    w1: float
    h1: float
    image: Any                  # изображение в суперсэмплинге (SS)

    @property
    def file_name(self) -> str:
        return f"{self.order:02d}_{self.name}.png"


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": lambda p: p,
    "ease_out": lambda p: 1 - (1 - p) ** 3,
    "ease_in": lambda p: p ** 3,
    "ease_in_out": lambda p: 3 * p ** 2 - 2 * p ** 3,
    # выход с небольшим «перелётом» — оживляет появление кнопок
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
            # слой уже виден: просто опускаем его (сообщение выросло)
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


def fit_scale(card_height1: float, scale_max: float = 2.6) -> float:
    """Масштаб карточки: целиком помещается в канву и не крупнее scale_max."""
    available_w = CANVAS_W - 2 * CANVAS_PAD
    available_h = CANVAS_H - 2 * CANVAS_PAD
    return max(0.4, min(scale_max, available_w / CARD_W1, available_h / card_height1))


# --------------------------------------------------------------------------- #
# Рисование слоёв (Pillow; координаты 1x, суперсэмплинг SS)
# --------------------------------------------------------------------------- #
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
    """Шрифт нужного кегля с учётом суперсэмплинга (кэшируется)."""
    from PIL import ImageFont

    cache_key = (bold, int(round(size1x * SS)))
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


def draw_backdrop(w1: float, h1: float) -> Any:
    """Подложка карточки: фон чата со скруглёнными углами."""
    from PIL import ImageDraw

    image = _new(w1, h1)
    ImageDraw.Draw(image).rounded_rectangle(
        [0, 0, _px(w1) - 1, _px(h1) - 1], radius=_px(CARD_RADIUS), fill=BACKGROUND
    )
    return image


def draw_header(w1: float) -> Any:
    """Шапка чата: имя бота, @username, разделитель."""
    from PIL import ImageDraw

    image = _new(w1, HEADER_H)
    draw = ImageDraw.Draw(image)
    # белая шапка со скруглёнными верхними углами
    draw.rounded_rectangle(
        [0, 0, _px(w1) - 1, _px(HEADER_H) - 1 + _px(CARD_RADIUS)],
        radius=_px(CARD_RADIUS),
        fill=HEADER_BG,
    )
    draw.rectangle(
        [0, _px(HEADER_H) - _px(CARD_RADIUS), _px(w1), _px(HEADER_H)], fill=HEADER_BG
    )
    draw.line([0, _px(HEADER_H) - SS, _px(w1), _px(HEADER_H) - SS], fill=HEADER_LINE, width=SS)

    name = texts.BOT_NAME
    draw.text((_center_x(draw, name, w1, 15, True), _px(15)), name,
              font=font(15, True), fill=BUBBLE_TEXT)
    status = f"@{BOT_USERNAME} · в сети"
    draw.text((_center_x(draw, status, w1, SMALL_FONT_SIZE), _px(40)), status,
              font=font(SMALL_FONT_SIZE), fill=NOTE_TEXT)
    return image


def draw_typing(active: int = 0) -> Any:
    """Пузырь «печатает…» с тремя точками (active — какая точка подсвечена)."""
    from PIL import ImageDraw

    image = _new(TYPING_W, TYPING_H)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [0, 0, _px(TYPING_W) - 1, _px(TYPING_H) - 1], radius=_px(14), fill=BUBBLE_BG
    )
    radius = _px(3.4)
    for index in range(3):
        cx = _px(16 + index * 12)
        cy = _px(TYPING_H / 2)
        color = DOT_ON if index == active % 3 else DOT_OFF
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)
    return image


def bubble_height(text: str, note: str = "") -> float:
    """Высота пузыря сообщения (та же формула, что в мокапах)."""
    lines = mockups.wrap(text)
    note_lines = mockups.wrap(note) if note else []
    return 18 + len(lines) * LINE_HEIGHT + len(note_lines) * (LINE_HEIGHT - 2) + 18


def draw_bubble(text: str, note: str = "") -> Any:
    """Пузырь сообщения бота: имя отправителя, текст, примечание."""
    from PIL import ImageDraw

    w1 = CARD_W1 - 2 * MARGIN
    h1 = bubble_height(text, note)
    image = _new(w1, h1)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, _px(w1) - 1, _px(h1) - 1], radius=_px(16), fill=BUBBLE_BG)
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
    """Ширины кнопок в ряду (логика та же, что в мокапах)."""
    if len(labels) == 1:
        return [float(total_width)]
    widths = [
        float(mockups.button_width(label, int(total_width), len(labels)))
        for label in labels
    ]
    needed = sum(widths) + 8 * (len(widths) - 1)
    if needed > total_width:
        ratio = total_width / needed
        widths = [width * ratio for width in widths]
    return widths


def draw_inline_row(labels: Sequence[str], primaries: Sequence[bool] = ()) -> Any:
    """Один ряд inline-кнопок во всю ширину карточки."""
    from PIL import ImageDraw

    total = CARD_W1 - 2 * MARGIN
    flags = list(primaries) + [False] * (len(labels) - len(primaries))
    widths = row_widths(labels, total)
    image = _new(total, ROW_H)
    draw = ImageDraw.Draw(image)

    x = 0.0
    for label, primary, width in zip(labels, flags, widths):
        box = [_px(x), 0, _px(x + width) - 1, _px(ROW_H) - 1]
        draw.rounded_rectangle(box, radius=_px(10), fill=PRIMARY_BG if primary else BUTTON_BG)
        if not primary:
            draw.rounded_rectangle(box, radius=_px(10), outline=BUTTON_BORDER, width=SS)
        draw.text(
            (_px(x) + (_px(width) - _text_width(draw, label, BUTTON_FONT_SIZE)) // 2, _px(9)),
            label,
            font=font(BUTTON_FONT_SIZE),
            fill=PRIMARY_TEXT if primary else BUTTON_TEXT,
        )
        x += width + 8
    return image


def draw_inline_rows_block(rows: Sequence[Sequence[str]]) -> Any:
    """Блок из нескольких рядов inline-кнопок (вариант «жанры отмечены»)."""
    total = CARD_W1 - 2 * MARGIN
    height = max(1, len(rows)) * (ROW_H + ROW_GAP)
    block = _new(total, height)
    y = 0.0
    for row in rows:
        block.alpha_composite(draw_inline_row(list(row)), (0, _px(y)))
        y += ROW_H + ROW_GAP
    return block


def reply_height(rows: Sequence[Sequence[str]]) -> float:
    """Высота блока обычной (reply) клавиатуры."""
    return len(rows) * (REPLY_ROW_H + 8) + 16


def draw_reply_keyboard(rows: Sequence[Sequence[str]]) -> Any:
    """Обычная (reply) клавиатура — блок внизу карточки."""
    from PIL import ImageDraw

    h1 = reply_height(rows)
    image = _new(CARD_W1, h1)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, _px(CARD_W1), _px(h1)], fill=REPLY_BG)
    draw.line([0, 0, _px(CARD_W1), 0], fill=HEADER_LINE, width=SS)

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
                radius=_px(10),
                fill=REPLY_BUTTON_BG,
                outline=BUTTON_BORDER,
                width=SS,
            )
            draw.text(
                (_px(x) + (_px(width) - _text_width(draw, label, BUTTON_FONT_SIZE)) // 2,
                 _px(y + 14)),
                label,
                font=font(BUTTON_FONT_SIZE),
                fill=BUBBLE_TEXT,
            )
            x += width + 8
        y += REPLY_ROW_H + 8
    return image


def draw_caption(text: str) -> Any:
    """Подпись под карточкой: какой это экран."""
    from PIL import ImageDraw

    image = _new(CARD_W1, CAPTION_H)
    draw = ImageDraw.Draw(image)
    draw.text((_center_x(draw, text, CARD_W1, SMALL_FONT_SIZE), 0), text,
              font=font(SMALL_FONT_SIZE), fill=NOTE_TEXT)
    return image


def draw_shadow(width: int, height: int, radius: int, offset: int = 10) -> Any:
    """Мягкая тень под карточкой (сразу в финальном размере)."""
    from PIL import Image, ImageDraw, ImageFilter

    pad = radius * 3
    image = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle(
        [pad, pad + offset, pad + width - 1, pad + height + offset - 1],
        radius=radius,
        fill=(20, 26, 38, 96),
    )
    return image.filter(ImageFilter.GaussianBlur(radius))


# --------------------------------------------------------------------------- #
# Раскладка карточки: какие слои и где лежат
# --------------------------------------------------------------------------- #
def screen_by_file(screen_file: str) -> Any:
    """Экран из генератора мокапов по имени файла."""
    for screen in mockups.SCREENS:
        if screen.file == screen_file:
            return screen
    raise KeyError(f"Экран {screen_file} не найден среди мокапов")


def genre_variants() -> Dict[str, Tuple[str, Tuple[Tuple[str, ...], ...]]]:
    """Варианты экрана «Выбор интересов»: без отметок → один жанр → два жанра."""
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


def build_layers(card: Card) -> Tuple[List[LayerSpec], float, float]:
    """Собирает слои карточки.

    Возвращает (слои, высота карточки в 1x, на сколько px опускаются кнопки,
    когда сообщение растёт после выбора жанра).
    """
    screen = screen_by_file(card.screen_file)
    layers: List[LayerSpec] = []

    bubble_text: str = screen.text
    bubble_note: str = screen.note
    inline_rows: List[Tuple[str, ...]] = [tuple(row) for row in screen.buttons]
    variants: Dict[str, Tuple[str, Tuple[Tuple[str, ...], ...]]] = {}

    if card.key == "03_picking_genres":
        stages = genre_variants()
        bubble_text, rows_none = stages["none"]
        inline_rows = [tuple(row) for row in rows_none]
        variants = {"one": stages["one"], "two": stages["two"]}

    # --- раскладка по вертикали ----------------------------------------- #
    content_top = HEADER_H + 16
    bubble_h = bubble_height(bubble_text, bubble_note)
    # когда жанр отмечают, сообщение растёт: кнопки в этот момент плавно
    # съезжают вниз на delta_h — место под это резервируем сразу
    delta_h = 0.0
    if variants:
        delta_h = max(
            bubble_height(message, bubble_note) for message, _ in variants.values()
        ) - bubble_h
    rows_top = content_top + bubble_h + 12
    y = rows_top
    row_positions: List[float] = []
    for _ in inline_rows:
        row_positions.append(y)
        y += ROW_H + ROW_GAP
    y += delta_h  # итоговое положение кнопок после «нажатий»

    reply_rows = [tuple(row) for row in screen.keyboard]
    reply_y = y + 4
    if reply_rows:
        y = reply_y + reply_height(reply_rows)
    caption_y = y + 8
    card_h = caption_y + CAPTION_H + 12

    # --- слои ------------------------------------------------------------ #
    def add(name: str, x1: float, y1: float, image: Any) -> None:
        layers.append(
            LayerSpec(
                name=name,
                order=len(layers) + 1,
                x1=x1,
                y1=y1,
                w1=image.size[0] / SS,
                h1=image.size[1] / SS,
                image=image,
            )
        )

    add("backdrop", 0, 0, draw_backdrop(CARD_W1, card_h))
    add("header", 0, 0, draw_header(CARD_W1))
    for index in range(3):
        add(f"typing_{index}", MARGIN, content_top + bubble_h - TYPING_H - 12,
            draw_typing(index))
    add("bubble", MARGIN, content_top, draw_bubble(bubble_text, bubble_note))
    for index, row in enumerate(inline_rows, start=1):
        pairs = mockups.normalize_rows([row])[0]
        add(f"inline_{index}", MARGIN, row_positions[index - 1],
            draw_inline_row([label for label, _ in pairs], [flag for _, flag in pairs]))
    shift = 0.0
    for stage, (message, rows) in variants.items():
        add(f"bubble_{stage}", MARGIN, content_top, draw_bubble(message, bubble_note))
        # первый вариант появляется там же, где были кнопки без отметок,
        # и затем съезжает вниз; следующие — сразу на итоговом месте
        add(f"rows_{stage}", MARGIN, row_positions[0] + shift,
            draw_inline_rows_block(rows))
        shift = delta_h
    if reply_rows:
        add("reply_keyboard", 0, reply_y, draw_reply_keyboard(reply_rows))
    add("caption", 0, caption_y, draw_caption(screen.caption))
    return layers, card_h, delta_h


# --------------------------------------------------------------------------- #
# Раскадровка: шаги анимации для каждой карточки
# --------------------------------------------------------------------------- #
def intro_steps(bubble_start: float) -> List[Step]:
    """Общее начало: тень, подложка, шапка, «печатает…», сообщение."""
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
    ]


def inline_names(layers: Sequence[LayerSpec]) -> List[str]:
    """Имена слоёв-рядов inline-кнопок в числовом порядке."""
    numbers = sorted(
        int(layer.name.split("_", 1)[1])
        for layer in layers
        if layer.name.startswith("inline_") and layer.name.split("_", 1)[1].isdigit()
    )
    return [f"inline_{number}" for number in numbers]


def build_steps(card: Card, layers: Sequence[LayerSpec], delta_h: float = 0.0) -> List[Step]:
    """Раскадровка карточки: порядок появления слоёв и «нажатия» кнопок."""
    names = {layer.name for layer in layers}
    steps: List[Step] = list(intro_steps(1.05 if card.key == "01_start" else 1.00))

    if card.key == "01_start":
        steps.append(Step("reply_keyboard", "keyboard_up", 1.75, 0.45, offset=70))
        steps.append(Step("reply_keyboard", "tap", 2.55, 0.35))
        steps.append(Step("caption", "fade", 2.30, 0.45))

    elif card.key == "03_picking_genres":
        rows = inline_names(layers)
        for index, name in enumerate(rows):
            steps.append(Step(name, "slide_up", 1.65 + index * 0.11, 0.38, offset=14))
        # первое нажатие: отмечен один жанр — сообщение и клавиатура обновились
        steps.append(Step("inline_1", "tap", 3.30, 0.30))
        steps.append(Step("bubble", "hide", 3.42, 0.10))
        steps.append(Step("bubble_one", "fade", 3.42, 0.18))
        for name in rows:
            steps.append(Step(name, "hide", 3.42, 0.01, ease="linear"))
        steps.append(Step("rows_one", "pop", 3.42, 0.24, ease="back_out"))
        if delta_h:
            steps.append(Step("rows_one", "shift_down", 3.50, 0.30, offset=delta_h))
        # второе нажатие: отмечены два жанра
        steps.append(Step("rows_one", "tap", 4.30, 0.30))
        steps.append(Step("bubble_one", "hide", 4.42, 0.10))
        steps.append(Step("bubble_two", "fade", 4.42, 0.18))
        steps.append(Step("rows_one", "hide", 4.42, 0.01, ease="linear"))
        steps.append(Step("rows_two", "pop", 4.42, 0.24, ease="back_out"))
        steps.append(Step("caption", "fade", 5.15, 0.45))

    else:  # 04_game_list — выбор игры
        rows = inline_names(layers)
        for index, name in enumerate(rows):
            steps.append(Step(name, "slide_up", 1.70 + index * 0.13, 0.40, offset=16))
        steps.append(Step("inline_1", "tap", 4.60, 0.34))
        steps.append(Step("caption", "fade", 5.20, 0.45))

    unknown = {step.layer for step in steps} - (names | {"shadow"})
    if unknown:  # pragma: no cover - защита от опечатки в раскадровке
        raise RuntimeError(f"В раскадровке есть несуществующие слои: {sorted(unknown)}")
    return sorted(steps, key=lambda step: (step.start, step.layer))


# --------------------------------------------------------------------------- #
# Рендер: слои в финальном масштабе и кадры анимации
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RenderedLayer:
    """Слой в финальном масштабе: изображение и позиция на канве."""

    name: str
    order: int
    image: Any
    x: int
    y: int
    width: int
    height: int


def render_layers(
    layers: Sequence[LayerSpec],
    card_h1: float,
    scale: float,
    card_x: int,
    card_y: int,
) -> List[RenderedLayer]:
    """Уменьшает слои из суперсэмплинга в финальный масштаб и считает позиции."""
    from PIL import Image

    rendered: List[RenderedLayer] = []
    for layer in layers:
        width = max(1, int(round(layer.w1 * scale)))
        height = max(1, int(round(layer.h1 * scale)))
        rendered.append(
            RenderedLayer(
                name=layer.name,
                order=layer.order,
                image=layer.image.resize((width, height), Image.LANCZOS),
                x=card_x + int(round(layer.x1 * scale)),
                y=card_y + int(round(layer.y1 * scale)),
                width=width,
                height=height,
            )
        )

    shadow = draw_shadow(
        int(round(CARD_W1 * scale)),
        int(round(card_h1 * scale)),
        max(6, int(round(12 * scale))),
        offset=int(round(6 * scale)),
    )
    card_w = int(round(CARD_W1 * scale))
    pad = (shadow.size[0] - card_w) // 2
    rendered.insert(
        0,
        RenderedLayer(
            name="shadow",
            order=0,
            image=shadow,
            x=card_x - pad,
            y=card_y - pad,
            width=shadow.size[0],
            height=shadow.size[1],
        ),
    )
    return rendered


def paste_clipped(canvas: Any, image: Any, x: int, y: int) -> None:
    """Вставляет слой на канву, обрезая выход за границы (как в AE)."""
    width, height = image.size
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(width, canvas.size[0] - x), min(height, canvas.size[1] - y)
    if right <= left or bottom <= top:
        return
    canvas.alpha_composite(image.crop((left, top, right, bottom)),
                           (x + left, y + top))


def compose_frame(
    rendered: Sequence[RenderedLayer],
    steps_by_layer: Dict[str, List[Step]],
    time: float,
    backdrop: Any,
    scale: float,
) -> Any:
    """Собирает один кадр анимации."""
    from PIL import Image

    canvas = backdrop.copy()
    for layer in rendered:
        alpha, dy1, layer_scale = layer_state(steps_by_layer.get(layer.name, []), time)
        if alpha <= 0.01:
            continue
        image = layer.image
        x, y = layer.x, layer.y + int(round(dy1 * scale))
        if abs(layer_scale - 1.0) > 0.002:
            width = max(1, int(round(image.size[0] * layer_scale)))
            height = max(1, int(round(image.size[1] * layer_scale)))
            resized = image.resize((width, height), Image.LANCZOS)
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
    """Моменты времени кадров; последний кадр — ровно конец анимации."""
    count = max(2, int(round(duration * fps)))
    return [index / fps for index in range(count)] + [duration]


def render_card_frames(
    rendered: Sequence[RenderedLayer],
    steps: Sequence[Step],
    duration: float,
    fps: int,
    scale: float,
    backdrop_color: Optional[str],
) -> Tuple[List[Any], List[int]]:
    """Кадры карточки и длительность каждого в мс.

    Одинаковые «статичные» кадры в конце не пересчитываются и не дублируются:
    последний кадр просто показывается дольше. Это сильно уменьшает размер GIF
    и не меняет восприятие анимации.
    """
    from PIL import Image

    backdrop = Image.new(
        "RGBA", (CANVAS_W, CANVAS_H), backdrop_color if backdrop_color else (0, 0, 0, 0)
    )
    steps_by_layer: Dict[str, List[Step]] = {}
    for step in steps:
        steps_by_layer.setdefault(step.layer, []).append(step)

    animation_end = max((step.start + step.duration for step in steps), default=0.0)
    frame_ms = int(round(1000 / fps))
    frames: List[Any] = []
    durations: List[int] = []
    static_frame: Optional[Any] = None
    for time in frame_times(duration, fps):
        if static_frame is not None:
            durations[-1] += frame_ms
            continue
        frame = compose_frame(rendered, steps_by_layer, time, backdrop, scale)
        frames.append(frame)
        durations.append(frame_ms)
        if time >= animation_end:
            static_frame = frame
    return frames, durations


def save_gif(frames: Sequence[Any], durations: Sequence[int], path: Path,
             colors: int = 128, width: int = 0) -> int:
    """Сохраняет GIF с общей палитрой; возвращает размер файла в байтах.

    Палитра строится по последнему кадру: он самый «наполненный», поэтому в
    палитру попадают все цвета интерфейса (иначе первый почти пустой кадр даёт
    вырожденную палитру и обесцвеченный GIF).
    """
    from PIL import Image

    prepared: List[Any] = []
    for frame in frames:
        image = frame
        if width and image.size[0] != width:
            height = max(1, round(image.size[1] * width / image.size[0]))
            image = image.resize((width, height), Image.LANCZOS)
        prepared.append(image.convert("RGB"))

    palette_image = prepared[-1].convert("P", palette=Image.ADAPTIVE, colors=colors)
    quantized = [image.quantize(palette=palette_image) for image in prepared]

    path.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        path,
        save_all=True,
        append_images=quantized[1:],
        duration=list(durations),
        loop=0,
        optimize=True,
        format="GIF",
    )
    return path.stat().st_size


def save_frames(frames: Sequence[Any], directory: Path) -> int:
    """Сохраняет PNG-последовательность кадров (для MP4/WebM с прозрачностью)."""
    directory.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames, start=1):
        frame.save(directory / f"frame_{index:04d}.png")
    return len(frames)


# --------------------------------------------------------------------------- #
# Экспорт: слои, тайминг-шит, превью, скрипт для AE
# --------------------------------------------------------------------------- #
def build_card_payload(
    card: Card,
    out_dir: Path,
    fps: int = DEFAULT_GIF_FPS,
    backdrop_name: str = "light",
    gif_width: int = DEFAULT_GIF_WIDTH,
    write_layers: bool = True,
    write_gif: bool = True,
    write_frames: bool = False,
    colors: int = 128,
) -> Dict[str, Any]:
    """Собирает одну карточку: слои на диске, кадры, GIF и описание таймингов."""
    layers1x, card_h1, delta_h = build_layers(card)
    scale = fit_scale(card_h1)
    card_w = int(round(CARD_W1 * scale))
    card_h = int(round(card_h1 * scale))
    card_x = (CANVAS_W - card_w) // 2
    card_y = (CANVAS_H - card_h) // 2

    rendered = render_layers(layers1x, card_h1, scale, card_x, card_y)
    steps = build_steps(card, layers1x, delta_h)

    if write_layers:
        layers_dir = out_dir / "layers" / card.key
        layers_dir.mkdir(parents=True, exist_ok=True)
        for layer in rendered:
            if layer.name == "shadow":
                continue
            layer.image.save(layers_dir / f"{layer.order:02d}_{layer.name}.png")

    frames, durations = render_card_frames(
        rendered, steps, card.duration, fps, scale, BACKDROPS.get(backdrop_name)
    )

    gif_size = 0
    if write_gif and BACKDROPS.get(backdrop_name) is not None:
        gif_size = save_gif(frames, durations, out_dir / "cards" / f"{card.key}.gif",
                            colors=colors, width=gif_width)
    frames_count = save_frames(frames, out_dir / "frames" / card.key) if write_frames else 0

    screen = screen_by_file(card.screen_file)
    return {
        "key": card.key,
        "title": screen.title,
        "heading": card.heading,
        "description": card.description,
        "screen_note": screen.note,
        "canvas": {"width": CANVAS_W, "height": CANVAS_H},
        "card": {"width": card_w, "height": card_h, "x": card_x, "y": card_y},
        "scale": round(scale, 3),
        "duration_seconds": card.duration,
        "gif_fps": fps,
        "ae_fps": AE_FPS,
        "gif_file": f"cards/{card.key}.gif" if gif_size else None,
        "gif_bytes": gif_size,
        "frames_exported": frames_count,
        "layers": [
            {
                "name": layer.name,
                "file": f"layers/{card.key}/{layer.order:02d}_{layer.name}.png",
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
            {"role": "заголовок", "text": card.heading, "font_size_px": 64,
             "color": "#16202E"},
            {"role": "описание", "text": card.description, "font_size_px": 34,
             "color": "#4A5568"},
        ],
    }


PREVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GameHunter — анимированные карточки (превью для After Effects)</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px 64px;
    background: #EDF1F7; color: #16202E;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}
  h1 {{ font-size: 30px; margin: 0 0 8px; }}
  .lead {{ margin: 0 0 32px; color: #4A5568; font-size: 16px; line-height: 1.55; }}
  .grid {{ display: grid; gap: 28px;
           grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
  section {{ background: #fff; border-radius: 18px; padding: 20px 20px 24px;
             box-shadow: 0 10px 30px rgba(20, 30, 50, .10); }}
  section img {{ width: 100%; height: auto; border-radius: 12px; display: block; }}
  h2 {{ font-size: 20px; margin: 18px 0 6px; }}
  p {{ margin: 0 0 10px; color: #4A5568; font-size: 15px; line-height: 1.55; }}
  code {{ background: #F1F4F9; border-radius: 6px; padding: 1px 6px; font-size: 13px; }}
  .meta {{ font-size: 13px; color: #7A8699; }}
  footer {{ margin-top: 32px; font-size: 14px; color: #4A5568; line-height: 1.6; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Анимированные карточки GameHunter</h1>
  <p class="lead">
    Три карточки: приветствие, выбор жанра и выбор игры — анимация сверху, текст
    снизу. Слои для After Effects лежат в <code>layers/&lt;экран&gt;/*.png</code>,
    тайминги — в <code>timeline.json</code>, инструкция —
    <code>docs/10_ae_animaciya_kartochek.md</code>.
  </p>
  <div class="grid">
{sections}
  </div>
  <footer>
    Канва {canvas_w}&times;{canvas_h}, черновой GIF {fps} fps, тайминг-шит — {ae_fps} fps
    (как в After Effects). Слои PNG полноразмерные: их можно импортировать в AE
    и перенести ключевые кадры из <code>timeline.json</code> либо запустить
    <code>import_layers.jsx</code>.
  </footer>
</div>
</body>
</html>
"""

SECTION_TEMPLATE = """    <section>
      <img src="{gif}" alt="{heading} — анимированная карточка GameHunter">
      <h2>{index}. {heading}</h2>
      <p>{description}</p>
      <p class="meta">{title} · карточка {card_w}&times;{card_h} px · {layers} слоёв ·
      {steps} шагов анимации · {duration} с{size}</p>
      <p class="meta"><code>{gif}</code></p>
    </section>"""


def preview_html(payloads: Sequence[Dict[str, Any]], fps: int) -> str:
    """Страница-превью: карточка сверху, текст снизу."""
    sections: List[str] = []
    for index, payload in enumerate(payloads, start=1):
        card = payload["card"]
        size = payload.get("gif_bytes") or 0
        sections.append(
            SECTION_TEMPLATE.format(
                gif=payload.get("gif_file") or f"cards/{payload['key']}.gif",
                heading=payload["heading"],
                description=payload["description"],
                title=payload["title"],
                card_w=card["width"],
                card_h=card["height"],
                layers=len(payload["layers"]),
                steps=len(payload["steps"]),
                duration=payload["duration_seconds"],
                index=index,
                size=f" · GIF {size / 1024 / 1024:.2f} МБ" if size else "",
            )
        )
    return PREVIEW_TEMPLATE.format(
        sections="\n".join(sections),
        fps=fps,
        ae_fps=AE_FPS,
        canvas_w=CANVAS_W,
        canvas_h=CANVAS_H,
    )


JSX_TEMPLATE = """// GameHunter: импорт слоёв карточки и сборка композиции в After Effects.
//
// Как пользоваться:
//   1. File -> Scripts -> Run Script File... и выберите этот файл.
//   2. В диалоге укажите папку docs/ae/layers/<экран> (например, 01_start).
//   3. Скрипт создаст композицию {width}x{height}, {fps} fps, разложит слои по местам
//      и проставит ключевые кадры Opacity/Position из timeline.json.
//
// Скрипт вспомогательный: эффекты «pop» и «tap» (масштаб) доделайте вручную —
// в AE это Scale с Easy Ease (F9) либо expression overshoot (см. документ
// docs/10_ae_animaciya_kartochek.md).
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
                    pos.setValueAtTime(t0, [base[0], base[1] + step.offset_px * cardInfo.scale]);
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


def write_outputs(out_dir: Path, payloads: Sequence[Dict[str, Any]], fps: int) -> List[Path]:
    """Сохраняет timeline.json, preview.html и скрипт для AE."""
    out_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = out_dir / "timeline.json"
    timeline_path.write_text(
        json.dumps(
            {
                "project": texts.BOT_NAME,
                "generated_by": "scripts/generate_ae_assets.py",
                "canvas": {"width": CANVAS_W, "height": CANVAS_H},
                "ae_fps": AE_FPS,
                "gif_fps": fps,
                "palette": {
                    "background": BACKGROUND,
                    "bubble": BUBBLE_BG,
                    "accent": SENDER,
                    "text": BUBBLE_TEXT,
                    "note": NOTE_TEXT,
                },
                "cards": payloads,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    preview_path = out_dir / "preview.html"
    preview_path.write_text(preview_html(payloads, fps), encoding="utf-8")

    jsx_path = out_dir / "import_layers.jsx"
    jsx_path.write_text(
        JSX_TEMPLATE.format(width=CANVAS_W, height=CANVAS_H, fps=AE_FPS), encoding="utf-8"
    )
    return [timeline_path, preview_path, jsx_path]


def generate(
    output: Path = DEFAULT_OUTPUT,
    fps: int = DEFAULT_GIF_FPS,
    backdrop: str = "light",
    gif_width: int = DEFAULT_GIF_WIDTH,
    only: Optional[str] = None,
    write_frames: bool = False,
    write_gif: bool = True,
) -> List[Path]:
    """Главная функция: собирает карточки и служебные файлы."""
    cards = [card for card in CARDS if only in (None, card.key)]
    if not cards:
        raise SystemExit(
            f"Карточка {only!r} не найдена. Доступны: "
            f"{', '.join(card.key for card in CARDS)}"
        )

    payloads: List[Dict[str, Any]] = []
    for card in cards:
        payload = build_card_payload(
            card,
            output,
            fps=fps,
            backdrop_name=backdrop,
            gif_width=gif_width,
            write_gif=write_gif,
            write_frames=write_frames,
        )
        box = payload["card"]
        size = (payload.get("gif_bytes") or 0) / 1024 / 1024
        print(
            f"  {card.key:<18} карточка {box['width']}x{box['height']} px, "
            f"слоёв {len(payload['layers'])}, шагов {len(payload['steps'])}, "
            f"{payload['duration_seconds']} с"
            + (f", GIF {size:.2f} МБ" if size else "")
        )
        payloads.append(payload)

    written = write_outputs(output, payloads, fps)
    for path in written:
        print(f"  {path.relative_to(PROJECT_ROOT)}")
    return written


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ассеты для анимации карточек в AE")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="каталог для ассетов")
    parser.add_argument("--fps", type=int, default=DEFAULT_GIF_FPS, help="кадры в секунду GIF")
    parser.add_argument("--gif-width", type=int, default=DEFAULT_GIF_WIDTH,
                        help="ширина GIF в px (0 — как канва)")
    parser.add_argument(
        "--backdrop",
        choices=sorted(BACKDROPS),
        default="light",
        help="фон канвы: light, dark или none (прозрачный — GIF тогда не пишется)",
    )
    parser.add_argument("--only", default=None, help="собрать одну карточку (например 01_start)")
    parser.add_argument("--frames", action="store_true",
                        help="сохранить PNG-последовательность кадров (для MP4/WebM)")
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

    print("Собираем анимированные карточки GameHunter…")
    generate(
        Path(args.out),
        fps=args.fps,
        backdrop=args.backdrop,
        gif_width=args.gif_width,
        only=args.only,
        write_frames=args.frames,
        write_gif=not args.no_gif,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
