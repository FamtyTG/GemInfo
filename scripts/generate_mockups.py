"""Генератор мокапов экранов Telegram-бота в формате SVG.

Мокапы строятся по реальным текстам и кнопкам из кода бота
(`travelhunter.presentation.texts` и `keyboards`), поэтому картинки
всегда соответствуют реализации.

Запуск из корня проекта:
    python -m scripts.generate_mockups

Результат: папка docs/mockups/ с файлами screen_01_start.svg … screen_09_note.svg
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from travelhunter.presentation import keyboards, texts  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "mockups"

# ---------------------------------------------------------------------- #
# Параметры отрисовки
# ---------------------------------------------------------------------- #
PHONE_WIDTH = 400
PADDING = 14
HEADER_HEIGHT = 56
FONT_SIZE = 13
LINE_HEIGHT = 18
BUBBLE_PADDING = 10
BUTTON_HEIGHT = 34
BUTTON_GAP = 8
BOTTOM_GAP = 18
PHOTO_HEIGHT = 170

COLOR_BG = "#e7ebf0"
COLOR_HEADER = "#2a76c6"
COLOR_BUBBLE = "#ffffff"
COLOR_BUBBLE_BORDER = "#c9d3dd"
COLOR_INLINE = "#d9ebff"
COLOR_INLINE_BORDER = "#7aa9de"
COLOR_REPLY = "#f2f5f8"
COLOR_REPLY_BORDER = "#c3ccd6"
COLOR_TEXT = "#16202b"
COLOR_MUTED = "#5c6b7a"


@dataclass(frozen=True)
class ScreenMockup:
    """Описание одного мокапа экрана."""

    filename: str
    title: str
    message: str
    inline_buttons: Tuple[str, ...] = ()
    reply_buttons: Tuple[str, ...] = ()
    photo: bool = False
    comment: str = ""


# ---------------------------------------------------------------------- #
# Примитивы отрисовки
# ---------------------------------------------------------------------- #
def _lines(text: str) -> List[str]:
    return text.split("\n") if text else [""]


def _svg_text(
    lines: Sequence[str], x: int, y: int, fill: str = COLOR_TEXT, bold_first: bool = False
) -> str:
    parts = []
    for index, line in enumerate(lines):
        weight = ' font-weight="600"' if (bold_first and index == 0) else ""
        parts.append(
            f'<text x="{x}" y="{y + index * LINE_HEIGHT}" '
            f'font-family="Segoe UI, Arial, sans-serif" font-size="{FONT_SIZE}" '
            f'fill="{fill}"{weight}>{escape(line)}</text>'
        )
    return "\n".join(parts)


def _bubble(y: int, text: str, width: int) -> Tuple[str, int]:
    """«Пузырь» сообщения бота. Возвращает (SVG-фрагмент, занятая высота)."""
    lines = _lines(text)
    height = BUBBLE_PADDING * 2 + LINE_HEIGHT * len(lines)
    svg = (
        f'<rect x="{PADDING}" y="{y}" width="{width - 2 * PADDING}" height="{height}" '
        f'rx="12" fill="{COLOR_BUBBLE}" stroke="{COLOR_BUBBLE_BORDER}"/>\n'
        + _svg_text(
            lines, PADDING + BUBBLE_PADDING, y + BUBBLE_PADDING + FONT_SIZE, bold_first=True
        )
    )
    return svg, height + BUTTON_GAP * 2


def _inline_buttons(y: int, labels: Sequence[str], width: int) -> Tuple[str, int]:
    """Inline-кнопки под сообщением (по одной в ряд, как в Telegram)."""
    blocks = []
    for label in labels:
        blocks.append(
            f'<rect x="{PADDING}" y="{y}" width="{width - 2 * PADDING}" '
            f'height="{BUTTON_HEIGHT}" rx="8" fill="{COLOR_INLINE}" '
            f'stroke="{COLOR_INLINE_BORDER}"/>\n'
            + _svg_text([label], PADDING + 12, y + 22, fill="#123f6d")
        )
        y += BUTTON_HEIGHT + 4
    return "\n".join(blocks), len(labels) * (BUTTON_HEIGHT + 4)


def _reply_keyboard(y: int, labels: Sequence[str], width: int) -> Tuple[str, int]:
    """Reply-клавиатура над полем ввода."""
    total_height = len(labels) * (BUTTON_HEIGHT + 6) + 14
    blocks = [
        f'<rect x="0" y="{y - 6}" width="{width}" height="{total_height}" fill="{COLOR_REPLY}"/>'
    ]
    for label in labels:
        blocks.append(
            f'<rect x="{PADDING}" y="{y}" width="{width - 2 * PADDING}" '
            f'height="{BUTTON_HEIGHT}" rx="10" fill="#ffffff" stroke="{COLOR_REPLY_BORDER}"/>\n'
            + _svg_text([label], PADDING + 14, y + 22)
        )
        y += BUTTON_HEIGHT + 6
    return "\n".join(blocks), total_height + 6


def render_screen(mockup: ScreenMockup) -> Path:
    """Рисует экран бота и сохраняет SVG-файл."""
    width = PHONE_WIDTH
    body: List[str] = []
    y = HEADER_HEIGHT + PADDING

    if mockup.photo:
        body.append(
            f'<rect x="{PADDING}" y="{y}" width="{width - 2 * PADDING}" height="{PHOTO_HEIGHT}" '
            f'rx="12" fill="#bcd6f2" stroke="{COLOR_BUBBLE_BORDER}"/>\n'
            + _svg_text(
                ["[ изображение города из Википедии ]"],
                PADDING + 95,
                y + PHOTO_HEIGHT // 2,
                fill="#3d5a78",
            )
        )
        y += PHOTO_HEIGHT + BUTTON_GAP * 2

    bubble_svg, bubble_height = _bubble(y, mockup.message, width)
    body.append(bubble_svg)
    y += bubble_height

    if mockup.inline_buttons:
        buttons_svg, buttons_height = _inline_buttons(y, mockup.inline_buttons, width)
        body.append(buttons_svg)
        y += buttons_height + BUTTON_GAP

    if mockup.reply_buttons:
        keyboard_svg, keyboard_height = _reply_keyboard(y, mockup.reply_buttons, width)
        body.append(keyboard_svg)
        y += keyboard_height

    if mockup.comment:
        comment_lines = _lines(mockup.comment)
        body.append(_svg_text(comment_lines, PADDING, y + FONT_SIZE + 6, fill=COLOR_MUTED))
        y += LINE_HEIGHT * len(comment_lines) + 12

    total_height = int(y + BOTTOM_GAP)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}" '
        f'viewBox="0 0 {width} {total_height}">\n'
        f'  <rect width="{width}" height="{total_height}" fill="{COLOR_BG}"/>\n'
        f'  <rect width="{width}" height="{HEADER_HEIGHT}" fill="{COLOR_HEADER}"/>\n'
        f'  <text x="{PADDING}" y="26" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="15" font-weight="600" fill="#ffffff">TravelHunter</text>\n'
        f'  <text x="{PADDING}" y="44" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="12" fill="#dce8f6">{escape(mockup.title)}</text>\n'
        f'  <text x="{width - PADDING - 120}" y="34" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="12" fill="#dce8f6">@TravelHunterBot</text>\n'
        + "\n".join(f"  {block}" for block in body)
        + "\n</svg>\n"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / mockup.filename
    path.write_text(svg, encoding="utf-8")
    return path


# ---------------------------------------------------------------------- #
# Описания экранов (тексты и кнопки берутся из кода бота)
# ---------------------------------------------------------------------- #
def select_buttons(count: int) -> Tuple[str, ...]:
    return tuple(keyboards.ButtonText.SELECT_CITY.format(index) for index in range(1, count + 1))


def build_mockups() -> List[ScreenMockup]:
    holidays_message = "\n".join([
        texts.HOLIDAYS_TITLE,
        "",
        "1. День физкультурника",
        "   08.08.2026 · Sa · Observance",
        "2. День государственного флага",
        "   22.08.2026 · Sa · National holiday",
    ])

    nearby_message = "\n".join([
        texts.NEARBY_TITLE,
        "Текущий город: Москва",
        "Радиус поиска: 500 км",
        "",
        "1. Тула — 172 км",
        "2. Калуга — 250 км",
        "3. Владимир — 310 км",
        "4. Рязань — 341 км",
        "5. Тверь — 411 км",
        "",
        texts.NEARBY_FOOTER,
    ])

    city_info_message = "\n".join([
        texts.CITY_INFO_TITLE,
        "",
        "Город: Тула",
        "Расстояние от города Москва: 172 км",
        "Регион: Тульская область",
        "Страна: Россия",
        "",
        texts.TRIP_SAVED,
        "",
        "Тула — город в России, административный центр Тульской области.",
        "Город-герой, впервые упомянут в 1146 году. Известен пряниками,",
        "самоварами и Тульским кремлём…",
    ])

    history_message = "\n".join([
        texts.HISTORY_TITLE,
        "Страница 1 из 2",
        "",
        "1. 10.08.2026 — Москва",
        "2. 03.08.2026 — Калуга",
        "3. 25.07.2026 — Орёл",
        "4. 18.07.2026 — Тула",
        "5. 11.07.2026 — Рязань",
        "",
        texts.HISTORY_FOOTER,
    ])

    trip_message = "\n".join([
        texts.TRIP_INFO_TITLE,
        "",
        "Дата поездки: 10.08.2026",
        "Город: Тула",
        texts.NOTE_ABSENT,
    ])

    return [
        ScreenMockup(
            filename="screen_01_start.svg",
            title="Экран 1. Старт",
            message=texts.START_WELCOME,
            reply_buttons=(keyboards.ButtonText.START,),
        ),
        ScreenMockup(
            filename="screen_02_main_menu.svg",
            title="Экран 2. Главное меню",
            message=texts.MAIN_MENU_WELCOME,
            reply_buttons=(
                keyboards.ButtonText.HOLIDAYS,
                keyboards.ButtonText.CITIES,
                keyboards.ButtonText.HISTORY,
            ),
        ),
        ScreenMockup(
            filename="screen_03_holidays.svg",
            title="Экран 3. Праздники на 7 дней",
            message=holidays_message,
            inline_buttons=(keyboards.ButtonText.BACK_TO_MENU,),
            comment=(
                "Если праздников нет: «К сожалению, ни одного праздника не найдено…»\n"
                "Если API недоступен: «Не удалось получить список праздников…»"
            ),
        ),
        ScreenMockup(
            filename="screen_04_city_input.svg",
            title="Экран 4. Города куда съездить — ввод города",
            message=texts.CITY_INPUT_PROMPT,
            comment=(
                "Если город не найден: «Город не найден. Проверьте название города\n"
                "и попробуйте ещё раз.» — бот ждёт повторного ввода."
            ),
        ),
        ScreenMockup(
            filename="screen_05_nearby_cities.svg",
            title="Экран 5. Города куда съездить — список городов",
            message=nearby_message,
            inline_buttons=select_buttons(5) + (keyboards.ButtonText.BACK,),
        ),
        ScreenMockup(
            filename="screen_06_city_info.svg",
            title="Экран 6. Города куда съездить — информация о городе",
            message=city_info_message,
            inline_buttons=(keyboards.ButtonText.BACK_TO_MENU,),
            photo=True,
            comment="Если изображения нет — информация показывается только текстом.",
        ),
        ScreenMockup(
            filename="screen_07_history.svg",
            title="Экран 7. История поездок — список поездок",
            message=history_message,
            inline_buttons=select_buttons(5)
            + (keyboards.ButtonText.FORWARD, keyboards.ButtonText.BACK_TO_MENU),
            comment=(
                "На первой странице нет кнопки «Назад», на последней — «Вперёд».\n"
                "Если поездок нет: «История поездок пока пуста…»"
            ),
        ),
        ScreenMockup(
            filename="screen_08_trip_info.svg",
            title="Экран 8. История поездок — информация о поездке",
            message=trip_message,
            inline_buttons=(
                keyboards.ButtonText.WRITE_NOTE,
                keyboards.ButtonText.BACK,
                keyboards.ButtonText.BACK_TO_MENU,
            ),
            comment=(
                "Если заметка есть, вместо «Заметка о поездке отсутствует.»\n"
                "показывается её текст."
            ),
        ),
        ScreenMockup(
            filename="screen_09_note.svg",
            title="Экран 9. История поездок — добавление заметки",
            message=texts.NOTE_PROMPT,
            comment=(
                "После сохранения: «Заметка успешно сохранена.» → возврат на Экран 8.\n"
                "Если символов больше 1000: «Заметка не должна превышать 1000 символов…»"
            ),
        ),
    ]


def main() -> int:
    created = [render_screen(mockup) for mockup in build_mockups()]
    for path in created:
        print("создан мокап:", path.name)
    print(f"Всего мокапов: {len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
