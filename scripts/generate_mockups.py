#!/usr/bin/env python3
"""Генератор мокапов интерфейса бота GameHunter (docs/mockups).

Мокапы рисуются в формате SVG (векторный, открывается в любом браузере),
а при наличии cairosvg дополнительно сохраняются в PNG. Такой подход позволяет
держать макеты вместе с кодом и пересобирать их командой `make mockups`.

Важно: тексты сообщений и подписи кнопок берутся не «от руки», а из самого
проекта — из модулей `gamehunter.presentation.texts` и
`gamehunter.presentation.keyboards`. Поэтому мокапы всегда соответствуют
реальному интерфейсу бота, а пересборка после изменения текстов обновляет их.

Каждый файл соответствует одному экрану из docs/04 и docs/05:
    01_start.svg            — приветствие и кнопка «Старт»
    02_main_menu.svg        — главное меню
    03_picking_genres.svg   — выбор интересов
    04_game_list.svg        — подборка игр
    05_game_card.svg        — карточка игры
    06_franchise_input.svg  — ввод названия франшизы (IP)
    07_franchise_list.svg   — найденные франшизы
    08_franchise_games.svg  — игры франшизы
    09_profile.svg          — моя анкета
    09a_profile_age.svg     — ввод возраста
    09b_profile_genres.svg  — интересы в анкете
    09c_profile_platforms.svg — платформы в анкете
    09d_profile_region.svg  — регион по IP-адресу
    10_played_list.svg      — во что я играл
    11_played_info.svg      — информация о сыгранной игре
    11a_review_input.svg    — ввод отзыва
    12_favorites.svg        — избранное

Запуск:
    python scripts/generate_mockups.py [--out docs/mockups] [--no-png]
"""

from __future__ import annotations

import argparse
import html
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gamehunter.domain import age_ratings  # noqa: E402
from gamehunter.domain.entities import (  # noqa: E402
    FavoriteGame,
    Franchise,
    Game,
    GameDetails,
    GamePage,
    Genre,
    LibraryPage,
    Platform,
    PlayedGame,
    Region,
    UserProfile,
)
from gamehunter.presentation import keyboards as kb  # noqa: E402
from gamehunter.presentation import texts  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "mockups"

# --------------------------------------------------------------------------- #
# Палитра и размеры (стиль Telegram)
# --------------------------------------------------------------------------- #
WIDTH = 375
HEIGHT = 812
MARGIN = 12
HEADER_HEIGHT = 74
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
PHOTO_BG = "#DDE3EA"
FONT_SIZE = 13
BUTTON_FONT_SIZE = 13
SMALL_FONT_SIZE = 11
CHARS_PER_LINE = 44
LINE_HEIGHT = 18


# --------------------------------------------------------------------------- #
# Модель экрана
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Screen:
    """Описание одного мокапа."""

    file: str
    title: str
    text: str
    buttons: Tuple[Tuple[str, ...], ...] = ()
    keyboard: Tuple[Tuple[str, ...], ...] = ()
    photo: bool = False
    hidden_keyboard: bool = False
    note: str = ""

    @property
    def caption(self) -> str:
        """Подпись под макетом (номер и название экрана)."""
        return f"{self.title} — GameHunter"


# --------------------------------------------------------------------------- #
# Примеры данных (такие же объекты бот получает из каталога RAWG)
# --------------------------------------------------------------------------- #
GENRES: Tuple[Genre, ...] = (
    Genre(id=4, name="Action", slug="action", games_count=158_000),
    Genre(id=5, name="RPG", slug="role-playing-games-rpg", games_count=52_000),
    Genre(id=3, name="Adventure", slug="adventure", games_count=141_000),
    Genre(id=2, name="Shooter", slug="shooter", games_count=98_000),
    Genre(id=10, name="Strategy", slug="strategy", games_count=71_000),
    Genre(id=1, name="Racing", slug="racing", games_count=24_000),
    Genre(id=7, name="Puzzle", slug="puzzle", games_count=48_000),
    Genre(id=11, name="Arcade", slug="arcade", games_count=36_000),
)

PLATFORMS: Tuple[Platform, ...] = (
    Platform(id=1, name="PC", slug="pc", games_count=210_000),
    Platform(id=2, name="PlayStation", slug="playstation", games_count=96_000),
    Platform(id=3, name="Xbox", slug="xbox", games_count=88_000),
    Platform(id=7, name="Nintendo", slug="nintendo", games_count=64_000),
    Platform(id=8, name="Android", slug="android", games_count=41_000),
    Platform(id=4, name="iOS", slug="ios", games_count=39_000),
)

SELECTED_GENRES: Tuple[str, ...] = ("action", "role-playing-games-rpg")
SELECTED_PLATFORMS: Tuple[int, ...] = (1, 2)

GAMES: Tuple[Game, ...] = (
    Game(
        id=32,
        slug="the-witcher-3-wild-hunt",
        name="The Witcher 3: Wild Hunt",
        released=date(2015, 5, 19),
        rating=4.62,
        genres=("RPG", "Action", "Adventure"),
        platforms=("PC", "PlayStation 4", "Xbox One", "Nintendo Switch"),
        image_url="https://media.rawg.io/media/games/618/618c2031a07bbff6b4f611f10b6bcdbc.jpg",
        metacritic=93,
        playtime_hours=50,
    ),
    Game(
        id=58175,
        slug="god-of-war-2",
        name="God of War",
        released=date(2018, 4, 20),
        rating=4.51,
        genres=("Action", "Adventure", "RPG"),
        platforms=("PC", "PlayStation 4"),
        image_url="https://media.rawg.io/media/games/4be/4be6a6ad0364751a96229c56bf69be59.jpg",
        metacritic=94,
        playtime_hours=30,
    ),
    Game(
        id=41494,
        slug="cyberpunk-2077",
        name="Cyberpunk 2077",
        released=date(2020, 12, 10),
        rating=4.31,
        genres=("RPG", "Action", "Shooter"),
        platforms=("PC", "PlayStation 5", "Xbox Series S/X"),
        image_url="https://media.rawg.io/media/games/26d/26d4437715bee60138dab4a7c8c59c92.jpg",
        metacritic=86,
        playtime_hours=40,
    ),
)

WITCHER = GAMES[0]

DETAILS = GameDetails(
    game=WITCHER,
    summary=(
        "Третья часть серии игр по книгам Анджея Сапковского. Герой ищет Цириллу, "
        "а заодно выполняет контракты на чудовищ: открытый мир, сюжетные выборы и "
        "карточная игра в гвинт."
    ),
    min_age=17,
    age_rating_label="M",
    developers=("CD PROJEKT RED",),
    publishers=("CD PROJEKT RED",),
    stores=("Steam", "GOG", "PlayStation Store"),
    tags=("Открытый мир", "Сюжет", "Славянское фэнтези"),
)

REGION = Region(
    ip="5.188.0.1",
    country="Russia",
    country_code="RU",
    city="Kazan",
    region_name="Tatarstan Republic",
    timezone="Europe/Moscow",
    currency="RUB",
    latitude=55.7887,
    longitude=49.1221,
)

PROFILE = UserProfile(
    tg_user_id=111111111,
    age=27,
    genre_slugs=SELECTED_GENRES,
    genre_names=("Action", "RPG"),
    platform_ids=SELECTED_PLATFORMS,
    platform_names=("PC", "PlayStation"),
    region=REGION,
    updated_at=datetime(2026, 9, 20, 12, 0),
)

FRANCHISES: Tuple[Franchise, ...] = (
    Franchise(id=4482, name="Marvel", slug="marvel", games_count=24),
    Franchise(
        id=5436,
        name="Marvel Ultimate Alliance",
        slug="marvel-ultimate-alliance",
        games_count=4,
    ),
)

FRANCHISE_GAMES: Tuple[Game, ...] = (
    Game(
        id=16134,
        slug="marvels-spider-man",
        name="Marvel's Spider-Man",
        released=date(2018, 9, 7),
        rating=4.24,
        genres=("Action", "Adventure"),
        platforms=("PlayStation 4", "PC"),
        metacritic=87,
    ),
    Game(
        id=35100,
        slug="marvels-guardians-of-the-galaxy",
        name="Marvel's Guardians of the Galaxy",
        released=date(2021, 10, 26),
        rating=4.1,
        genres=("Action", "Adventure"),
        platforms=("PC", "PlayStation 5", "Xbox Series S/X"),
        metacritic=78,
    ),
    Game(
        id=9001,
        slug="marvel-vs-capcom-infinite",
        name="Marvel vs. Capcom: Infinite",
        released=date(2017, 9, 19),
        rating=3.4,
        genres=("Fighting", "Action"),
        platforms=("PC", "PlayStation 4", "Xbox One"),
        metacritic=62,
    ),
)

PLAYED: Tuple[PlayedGame, ...] = (
    PlayedGame(
        id=1,
        tg_user_id=111111111,
        game_id=32,
        slug="the-witcher-3-wild-hunt",
        name="The Witcher 3: Wild Hunt",
        played_at=datetime(2026, 5, 12, 20, 15),
        review=(
            "Прошёл на 100%: отличный сюжет и боевая система, "
            "но концовки дополнений спорные."
        ),
        image_url=WITCHER.image_url,
    ),
    PlayedGame(
        id=2,
        tg_user_id=111111111,
        game_id=58175,
        slug="god-of-war-2",
        name="God of War",
        played_at=datetime(2026, 4, 3, 19, 40),
        review=None,
    ),
)

FAVORITES: Tuple[FavoriteGame, ...] = (
    FavoriteGame(
        id=1,
        tg_user_id=111111111,
        game_id=41494,
        slug="cyberpunk-2077",
        name="Cyberpunk 2077",
        added_at=datetime(2026, 8, 30, 21, 5),
    ),
    FavoriteGame(
        id=2,
        tg_user_id=111111111,
        game_id=32,
        slug="the-witcher-3-wild-hunt",
        name="The Witcher 3: Wild Hunt",
        added_at=datetime(2026, 9, 1, 22, 30),
    ),
)

GAME_PAGE = GamePage(
    games=GAMES,
    page=1,
    page_size=3,
    total_count=7,
    has_next=True,
    has_previous=False,
)


# --------------------------------------------------------------------------- #
# Вспомогательные функции отрисовки
# --------------------------------------------------------------------------- #
def escape(value: object) -> str:
    """Экранирует текст для XML."""
    return html.escape(str(value), quote=True)


def wrap(text: str, limit: int = CHARS_PER_LINE) -> List[str]:
    """Переносит текст по словам (как в мессенджере)."""
    lines: List[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def button_label(button: object) -> str:
    """Подпись кнопки телебот-клавиатуры (объект или словарь)."""
    if isinstance(button, dict):
        return str(button.get("text", ""))
    return str(getattr(button, "text", "") or "")


def labels_of(markup: object) -> Tuple[Tuple[str, ...], ...]:
    """Подписи кнопок inline-клавиатуры по рядам."""
    rows = getattr(markup, "keyboard", None) or ()
    return tuple(tuple(button_label(button) for button in row) for row in rows if row)


def reply_rows(markup: object) -> Tuple[Tuple[str, ...], ...]:
    """Подписи кнопок обычной (reply) клавиатуры по рядам."""
    rows = getattr(markup, "keyboard", None) or ()
    return tuple(tuple(button_label(button) for button in row) for row in rows if row)


def normalize_rows(buttons: Sequence) -> List[List[Tuple[str, bool]]]:
    """Приводит описание кнопок к единому виду: список рядов пар (подпись, основная).

    Поддерживаются сокращённые формы записи:
        "Текст"                     — одна обычная кнопка в ряду
        ("Текст", True)             — одна «главная» кнопка (залита синим)
        ("Текст 1", "Текст 2")      — две обычные кнопки в одном ряду
    """
    rows: List[List[Tuple[str, bool]]] = []
    for row in buttons:
        if isinstance(row, str):
            rows.append([(row, False)])
        elif len(row) == 2 and isinstance(row[1], bool):
            rows.append([(row[0], row[1])])
        else:
            rows.append(
                [
                    (item, False) if isinstance(item, str) else (item[0], bool(item[1]))
                    for item in row
                ]
            )
    return rows


def button_width(label: str, total_width: int, siblings: int, padding: int = 26) -> int:
    """Ширина кнопки inline-клавиатуры (не больше доступной и не меньше текста)."""
    available = total_width - (siblings - 1) * 8
    natural = len(label) * 8 + padding
    return max(110, min(available, natural))


def render_buttons(
    rows: Sequence[Sequence[Tuple[str, bool]]],
    top: int,
    total_width: int = WIDTH - 2 * MARGIN,
) -> Tuple[str, int]:
    """Рисует ряды кнопок. Возвращает (SVG, новая координата Y)."""
    parts: List[str] = []
    x_start = MARGIN
    y = top

    for row in rows:
        if not row:
            continue
        labels = [label for label, _ in row]
        if len(row) == 1:
            # одна кнопка в ряду растягивается на всю ширину — как в Telegram
            widths = [total_width]
        else:
            widths = [button_width(label, total_width, len(row)) for label in labels]
            if sum(widths) + 8 * (len(widths) - 1) > total_width:
                scale = total_width / (sum(widths) + 8 * (len(widths) - 1))
                widths = [int(width * scale) for width in widths]

        x = x_start
        for (label, primary), width in zip(row, widths):
            fill = PRIMARY_BG if primary else BUTTON_BG
            stroke = "" if primary else f' stroke="{BUTTON_BORDER}" stroke-width="1"'
            text_color = PRIMARY_TEXT if primary else BUTTON_TEXT
            parts.append(
                f'<rect x="{x}" y="{y}" width="{width}" height="34" rx="10" '
                f'fill="{fill}"{stroke} />'
            )
            parts.append(
                f'<text x="{x + width / 2}" y="{y + 22}" text-anchor="middle" '
                f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="{BUTTON_FONT_SIZE}" '
                f'fill="{text_color}">{escape(label)}</text>'
            )
            x += width + 8
        y += 34 + 8

    return "".join(parts), y


def render_reply_keyboard(rows: Sequence[Sequence[str]], frame_height: int = HEIGHT) -> str:
    """Рисует обычную клавиатуру внизу экрана (главное меню)."""
    parts: List[str] = []
    row_height = 44
    height = len(rows) * (row_height + 8) + 16
    y0 = frame_height - height

    parts.append(
        f'<rect x="0" y="{y0}" width="{WIDTH}" height="{height}" fill="{REPLY_BG}" />'
    )
    parts.append(f'<line x1="0" y1="{y0}" x2="{WIDTH}" y2="{y0}" stroke="{HEADER_LINE}" />')

    y = y0 + 12
    total_width = WIDTH - 2 * MARGIN
    for row in rows:
        if not row:
            continue
        widths = [total_width // len(row) - 8 for _ in row]
        x = MARGIN
        for label, width in zip(row, widths):
            parts.append(
                f'<rect x="{x}" y="{y}" width="{width}" height="{row_height}" rx="10" '
                f'fill="{REPLY_BUTTON_BG}" stroke="{BUTTON_BORDER}" stroke-width="1" />'
            )
            parts.append(
                f'<text x="{x + width / 2}" y="{y + 28}" text-anchor="middle" '
                f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="{BUTTON_FONT_SIZE}" '
                f'fill="{BUBBLE_TEXT}">{escape(label)}</text>'
            )
            x += width + 8
        y += row_height + 8

    return "".join(parts)


def render_hidden_keyboard(frame_height: int = HEIGHT) -> str:
    """Пометка о том, что обычная клавиатура скрыта на время ввода текста."""
    y = frame_height - 40
    return (
        f'<text x="{WIDTH / 2}" y="{y}" text-anchor="middle" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="{SMALL_FONT_SIZE}" '
        f'fill="{NOTE_TEXT}">обычная клавиатура скрыта — пользователь вводит текст</text>'
    )


def render_bubble(
    lines: Sequence[str], top: int, photo: bool = False, note: Optional[str] = None
) -> Tuple[str, int]:
    """Рисует «пузырь» сообщения бота. Возвращает (SVG, новая координата Y)."""
    photo_height = 150 if photo else 0
    note_lines = wrap(note, CHARS_PER_LINE) if note else []
    height = 18 + len(lines) * LINE_HEIGHT + photo_height + len(note_lines) * (LINE_HEIGHT - 2) + 18

    parts: List[str] = [
        f'<rect x="{MARGIN}" y="{top}" width="{WIDTH - 2 * MARGIN}" height="{height}" rx="16" '
        f'fill="{BUBBLE_BG}" />'
    ]
    y = top + 24
    parts.append(
        f'<text x="{MARGIN + 14}" y="{y}" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
        f'font-size="{SMALL_FONT_SIZE}" fill="{SENDER}">{escape(texts.BOT_NAME)}</text>'
    )
    y += 20

    if photo:
        parts.append(
            f'<rect x="{MARGIN + 14}" y="{y}" width="{WIDTH - 2 * MARGIN - 28}" '
            f'height="{photo_height - 16}" rx="10" fill="{PHOTO_BG}" />'
        )
        parts.append(
            f'<text x="{WIDTH / 2}" y="{y + (photo_height - 16) / 2}" text-anchor="middle" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="{SMALL_FONT_SIZE}" '
            f'fill="#6B7280">обложка игры (фото из каталога)</text>'
        )
        y += photo_height

    for line in lines:
        weight = ' font-weight="600"' if line.endswith(":") and len(line) < 60 else ""
        parts.append(
            f'<text x="{MARGIN + 14}" y="{y}" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
            f'font-size="{FONT_SIZE}" fill="{BUBBLE_TEXT}"{weight}>{escape(line)}</text>'
        )
        y += LINE_HEIGHT

    for line in note_lines:
        parts.append(
            f'<text x="{MARGIN + 14}" y="{y}" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
            f'font-size="{SMALL_FONT_SIZE}" fill="{NOTE_TEXT}">{escape(line)}</text>'
        )
        y += LINE_HEIGHT - 2

    return "".join(parts), top + height + 12


def render_frame(
    title: str, caption: str, body: str, keyboard: str = "", frame_height: int = HEIGHT
) -> str:
    """Собирает полный SVG-макет экрана."""
    header = (
        f'<rect x="0" y="0" width="{WIDTH}" height="{HEADER_HEIGHT}" fill="{HEADER_BG}" />'
        f'<line x1="0" y1="{HEADER_HEIGHT}" x2="{WIDTH}" y2="{HEADER_HEIGHT}" stroke="{HEADER_LINE}" />'
        f'<text x="{WIDTH / 2}" y="32" text-anchor="middle" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
        f'font-size="15" font-weight="600" fill="{BUBBLE_TEXT}">{escape(texts.BOT_NAME)}</text>'
        f'<text x="{WIDTH / 2}" y="52" text-anchor="middle" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
        f'font-size="{SMALL_FONT_SIZE}" fill="{NOTE_TEXT}">@GameHunterBot · в сети</text>'
        f'<text x="{WIDTH / 2}" y="{frame_height - 8}" text-anchor="middle" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="{SMALL_FONT_SIZE}" '
        f'fill="{NOTE_TEXT}">{escape(caption)}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{frame_height}" '
        f'viewBox="0 0 {WIDTH} {frame_height}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
        f"<title>{escape(title)}</title>"
        f'<rect width="{WIDTH}" height="{frame_height}" fill="{BACKGROUND}" />'
        f"{header}{body}{keyboard}"
        f"</svg>"
    )


def content_bottom(screen: "Screen") -> int:
    """Нижняя граница контента экрана (сообщение и inline-кнопки)."""
    _, y = render_bubble(
        wrap(screen.text), HEADER_HEIGHT + 16, photo=screen.photo, note=screen.note or None
    )
    if screen.buttons:
        _, y = render_buttons(normalize_rows(screen.buttons), y)
    return y


def frame_height(screen: "Screen") -> int:
    """Высота макета экрана.

    Обычный экран занимает размер телефона (HEIGHT). Длинные сообщения
    (например, карточка игры) в Telegram прокручиваются, поэтому макет
    такого экрана делается выше — весь текст остаётся видимым.
    """
    return max(HEIGHT, content_bottom(screen) + 56)


def render_screen(screen: Screen) -> str:
    """Рисует один экран и возвращает содержимое SVG-файла."""
    body_parts: List[str] = []
    y = HEADER_HEIGHT + 16
    height = frame_height(screen)

    bubble, y = render_bubble(
        wrap(screen.text), y, photo=screen.photo, note=screen.note or None
    )
    body_parts.append(bubble)

    if screen.buttons:
        buttons_svg, y = render_buttons(normalize_rows(screen.buttons), y)
        body_parts.append(buttons_svg)

    keyboard = render_reply_keyboard(screen.keyboard, height) if screen.keyboard else ""
    if screen.hidden_keyboard:
        keyboard = render_hidden_keyboard(height)

    return render_frame(screen.title, screen.caption, "".join(body_parts), keyboard, height)


# --------------------------------------------------------------------------- #
# Экраны: текст и кнопки берутся из кода бота
# --------------------------------------------------------------------------- #
def build_screens() -> Tuple[Screen, ...]:
    """Собирает все мокапы из настоящих текстов и клавиатур бота."""
    filters_line = texts.format_filters(
        PROFILE.genre_names, PROFILE.platform_names, PROFILE.age
    )
    played_history = LibraryPage(items=list(PLAYED), page=1, total_pages=1)
    favorites_page = LibraryPage(items=list(FAVORITES), page=1, total_pages=1)

    return (
        # Экран 1. Приветствие
        Screen(
            file="01_start",
            title="Экран 1. Приветствие",
            text=texts.START_WELCOME,
            keyboard=reply_rows(kb.start_keyboard()),
            note="Показывается один раз при первом запуске бота (команда /start).",
        ),
        # Экран 2. Главное меню
        Screen(
            file="02_main_menu",
            title="Экран 2. Главное меню",
            text=texts.MAIN_MENU_WELCOME,
            keyboard=reply_rows(kb.main_menu_keyboard()),
            note="Команда /start из любого места бота возвращает в это меню.",
        ),
        # Экран 3. Выбор интересов
        Screen(
            file="03_picking_genres",
            title="Экран 3. Выбор интересов",
            text=texts.format_genres_selection(
                GENRES,
                SELECTED_GENRES,
                title=texts.GENRES_TITLE,
                footer=texts.GENRES_FOOTER,
            ),
            buttons=labels_of(kb.picking_genres_keyboard(GENRES, SELECTED_GENRES)),
            note="Жанры отмечаются галочкой; можно ничего не выбирать — тогда возьмутся интересы из анкеты.",
        ),
        # Экран 4. Подборка игр
        Screen(
            file="04_game_list",
            title="Экран 4. Подборка игр",
            text=texts.format_games(GAME_PAGE, filters_line, played_excluded=True),
            buttons=labels_of(
                kb.games_keyboard(
                    GAME_PAGE.games,
                    GAME_PAGE.page,
                    has_next=True,
                    has_previous=False,
                )
            ),
            note="Сыгранные игры исключены из подборки автоматически.",
        ),
        # Экран 5. Карточка игры
        Screen(
            file="05_game_card",
            title="Экран 5. Карточка игры",
            text=texts.format_game_card(
                DETAILS, PROFILE, is_played=True, is_favorite=True
            ),
            buttons=labels_of(kb.game_card_keyboard(WITCHER.id, is_favorite=True)),
            photo=True,
            note="Описание игры сокращается до 400 символов.",
        ),
        # Экран 6. Ввод названия франшизы
        Screen(
            file="06_franchise_input",
            title="Экран 6. Поиск по франшизе — ввод названия",
            text=texts.FRANCHISE_INPUT_PROMPT,
            hidden_keyboard=True,
            note="Франшиза — интеллектуальная собственность (IP): Marvel, Star Wars, Warcraft.",
        ),
        # Экран 7. Найденные франшизы
        Screen(
            file="07_franchise_list",
            title="Экран 7. Найденные франшизы",
            text=texts.format_franchises(FRANCHISES),
            buttons=labels_of(kb.franchises_keyboard(FRANCHISES)),
        ),
        # Экран 8. Игры франшизы
        Screen(
            file="08_franchise_games",
            title="Экран 8. Игры франшизы",
            text=texts.format_game_list(
                FRANCHISE_GAMES,
                texts.FRANCHISE_GAMES_TITLE.format(FRANCHISES[0].name),
            ),
            buttons=labels_of(kb.franchise_games_keyboard(FRANCHISE_GAMES)),
        ),
        # Экран 9. Моя анкета
        Screen(
            file="09_profile",
            title="Экран 9. Моя анкета",
            text=texts.format_profile(PROFILE),
            buttons=labels_of(kb.profile_keyboard(has_age=True, has_region=True)),
            note="Анкета применяется как фильтр по умолчанию при подборе игр.",
        ),
        # Экран 9а. Ввод возраста
        Screen(
            file="09a_profile_age",
            title="Экран 9а. Ввод возраста",
            text=texts.PROFILE_AGE_PROMPT,
            hidden_keyboard=True,
            note="Возраст нужен, чтобы не предлагать игры с рейтингом выше допустимого.",
        ),
        # Экран 9б. Интересы в анкете
        Screen(
            file="09b_profile_genres",
            title="Экран 9б. Интересы в анкете",
            text=texts.format_genres_selection(
                GENRES,
                SELECTED_GENRES,
                title=texts.PROFILE_GENRES_TITLE,
                footer=texts.PROFILE_GENRES_SAVED_HINT,
            ),
            buttons=labels_of(kb.profile_genres_keyboard(GENRES, SELECTED_GENRES)),
        ),
        # Экран 9в. Платформы в анкете
        Screen(
            file="09c_profile_platforms",
            title="Экран 9в. Платформы в анкете",
            text="\n\n".join(
                (
                    texts.PROFILE_PLATFORMS_TITLE,
                    texts.PROFILE_PLATFORMS_SELECTED.format("PC, PlayStation"),
                )
            ),
            buttons=labels_of(kb.platforms_keyboard(PLATFORMS, SELECTED_PLATFORMS)),
        ),
        # Экран 9г. Регион по IP
        Screen(
            file="09d_profile_region",
            title="Экран 9г. Регион по IP-адресу",
            text=texts.PROFILE_IP_PROMPT,
            hidden_keyboard=True,
            note="Telegram Bot API не передаёт IP пользователя, поэтому адрес нужно прислать вручную.",
        ),
        # Экран 10. Во что я играл
        Screen(
            file="10_played_list",
            title="Экран 10. Во что я играл",
            text=texts.format_played_history(played_history),
            buttons=labels_of(
                kb.played_list_keyboard(
                    played_history.items, played_history.page, played_history.total_pages
                )
            ),
            note="Записи из этого списка исключаются из подбора игр.",
        ),
        # Экран 11. Информация о сыгранной игре
        Screen(
            file="11_played_info",
            title="Экран 11. Информация о сыгранной игре",
            text=texts.format_played_info(PLAYED[0]),
            buttons=labels_of(kb.played_info_keyboard(PLAYED[0].id, 1)),
        ),
        # Экран 11а. Ввод отзыва
        Screen(
            file="11a_review_input",
            title="Экран 11а. Ввод отзыва",
            text=f"{texts.REVIEW_PROMPT}\n\nИгра: {PLAYED[0].name}",
            hidden_keyboard=True,
            note="Отзыв может занимать до 1000 символов.",
        ),
        # Экран 12. Избранное
        Screen(
            file="12_favorites",
            title="Экран 12. Избранное",
            text=texts.format_favorites(favorites_page),
            buttons=labels_of(
                kb.favorites_keyboard(
                    favorites_page.items, favorites_page.page, favorites_page.total_pages
                )
            ),
        ),
        # Экран 13. Подбор по возрастному рейтингу
        Screen(
            file="13_age_rating",
            title="Экран 13. Возрастной рейтинг",
            text=texts.AGE_RATING_TITLE
            + "\n\n"
            + texts.AGE_RATING_CURRENT.format(age_ratings.rating_label(13)),
            buttons=labels_of(kb.age_rating_keyboard(13)),
            note="Выбранный рейтинг подменяет возраст из анкеты: подборка "
            "показывает игры, подходящие под категорию.",
        ),
    )


SCREENS: Tuple[Screen, ...] = build_screens()


# --------------------------------------------------------------------------- #
# Сохранение файлов
# --------------------------------------------------------------------------- #
def save_png(path: Path) -> Optional[str]:
    """Конвертирует SVG в PNG. Возвращает None, если конвертер недоступен."""
    try:
        import cairosvg  # type: ignore
    except ImportError:
        return None
    try:
        cairosvg.svg2png(url=str(path), write_to=str(path.with_suffix(".png")), scale=2)
    except Exception as exc:  # noqa: BLE001 - PNG необязателен
        print(f"⚠️  Не удалось сохранить PNG для {path.name}: {exc}")
        return None
    return str(path.with_suffix(".png"))


def generate(output: Path, with_png: bool = True) -> List[Path]:
    """Создаёт все мокапы. Возвращает список сохранённых SVG-файлов."""
    output.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []
    png_count = 0

    for screen in SCREENS:
        path = output / f"{screen.file}.svg"
        path.write_text(render_screen(screen), encoding="utf-8")
        created.append(path)
        if with_png and save_png(path):
            png_count += 1

    print(f"✅ Создано мокапов: {len(created)} ({output})")
    if with_png:
        if png_count:
            print(f"   PNG-версий: {png_count}")
        else:
            print("   PNG пропущены: установите cairosvg (pip install cairosvg)")
    return created


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Генератор мокапов интерфейса GameHunter")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="папка для файлов")
    parser.add_argument("--no-png", action="store_true", help="не создавать PNG-версии")
    args = parser.parse_args(list(argv) if argv is not None else None)

    generate(Path(args.out), with_png=not args.no_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
