"""Тесты генератора мокапов интерфейса (scripts/generate_mockups.py)."""

from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from gamehunter.presentation import keyboards, texts

SPEC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "generate_mockups.py"
MOCKUPS_DIR = Path(__file__).resolve().parent.parent / "docs" / "mockups"
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def load_module():
    """Загружает скрипт как модуль (он лежит вне пакета)."""
    spec = importlib.util.spec_from_file_location("generate_mockups", SPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    # модуль нужен в sys.modules ещё до выполнения: dataclass разрешает аннотации по имени
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mockups = load_module()
SCREENS = mockups.SCREENS
IDS = [screen.file for screen in SCREENS]


def texts_of(svg: str, fragment: bool = False) -> list[str]:
    """Все текстовые узлы SVG."""
    root = parse_fragment(svg) if fragment else ET.fromstring(svg)
    return [node.text or "" for node in root.iter("{http://www.w3.org/2000/svg}text")]


def rects_of(svg: str, fragment: bool = False) -> list[tuple[float, float, float, float]]:
    """Прямоугольники SVG: (x, y, width, height)."""
    root = parse_fragment(svg) if fragment else ET.fromstring(svg)
    return [
        (
            float(node.get("x", 0)),
            float(node.get("y", 0)),
            float(node.get("width", 0)),
            float(node.get("height", 0)),
        )
        for node in root.iter("{http://www.w3.org/2000/svg}rect")
    ]


def parse_fragment(svg: str) -> ET.Element:
    """Разбирает фрагмент SVG (без корневого элемента), обернув его в <svg>."""
    return ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{svg}</svg>')


def screen_by_file(name: str) -> mockups.Screen:
    return next(screen for screen in SCREENS if screen.file == name)


# --------------------------------------------------------------------------- #
# Набор экранов
# --------------------------------------------------------------------------- #
class TestScreenSet:
    def test_seventeen_screens(self):
        assert len(SCREENS) == 18

    def test_file_names_are_unique(self):
        assert len(IDS) == len(set(IDS))

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_screen_has_required_fields(self, screen):
        assert screen.title.startswith("Экран")
        assert screen.text.strip()
        assert screen.file
        assert screen.caption.endswith("GameHunter")

    def test_screen_numbers_match_docs(self):
        numbers = {screen.file.split("_")[0] for screen in SCREENS}

        assert numbers == {
            "01", "02", "03", "04", "05", "06", "07", "08", "09", "09a", "09b",
            "09c", "09d", "10", "11", "11a", "12", "13",
        }

    def test_titles_are_unique(self):
        titles = [screen.title for screen in SCREENS]
        assert len(titles) == len(set(titles))

    def test_only_card_screen_has_photo(self):
        with_photo = [screen.file for screen in SCREENS if screen.photo]

        assert with_photo == ["05_game_card"]

    def test_text_input_screens_hide_keyboard(self):
        hidden = [screen.file for screen in SCREENS if screen.hidden_keyboard]

        assert hidden == [
            "06_franchise_input",
            "09a_profile_age",
            "09d_profile_region",
            "11a_review_input",
        ]

    def test_only_long_screens_grow(self):
        tall = [screen.file for screen in SCREENS if mockups.frame_height(screen) > mockups.HEIGHT]

        assert tall == ["05_game_card"]

    def test_reply_keyboard_only_on_menu_screens(self):
        with_keyboard = [screen.file for screen in SCREENS if screen.keyboard]

        assert with_keyboard == ["01_start", "02_main_menu"]


# --------------------------------------------------------------------------- #
# Мокапы строятся из кода бота
# --------------------------------------------------------------------------- #
class TestContentComesFromCode:
    def test_start_screen_text(self):
        assert screen_by_file("01_start").text == texts.START_WELCOME

    def test_main_menu_text(self):
        assert screen_by_file("02_main_menu").text == texts.MAIN_MENU_WELCOME

    def test_main_menu_keyboard(self):
        assert screen_by_file("02_main_menu").keyboard == (
            (keyboards.ButtonText.PICK, keyboards.ButtonText.FRANCHISE),
            (keyboards.ButtonText.PROFILE,),
            (keyboards.ButtonText.PLAYED, keyboards.ButtonText.FAVORITES),
            (keyboards.ButtonText.AGE_RATING,),
        )

    def test_start_keyboard(self):
        assert screen_by_file("01_start").keyboard == ((keyboards.ButtonText.START,),)

    def test_franchise_prompt(self):
        assert screen_by_file("06_franchise_input").text == texts.FRANCHISE_INPUT_PROMPT

    def test_age_prompt(self):
        assert screen_by_file("09a_profile_age").text == texts.PROFILE_AGE_PROMPT

    def test_region_prompt_mentions_manual_ip(self):
        screen = screen_by_file("09d_profile_region")

        assert screen.text == texts.PROFILE_IP_PROMPT
        assert "2ip.ru" in screen.text or "2ip.ru" in screen.note
        assert "Telegram Bot API не передаёт IP" in screen.note

    def test_profile_screen_is_formatted_by_service_text(self):
        screen = screen_by_file("09_profile")

        assert screen.text.startswith(texts.PROFILE_TITLE)
        assert texts.PROFILE_FOOTER in screen.text
        assert "Возраст: 27 лет" in screen.text

    def test_game_card_screen_is_formatted(self):
        screen = screen_by_file("05_game_card")

        assert screen.text.startswith(texts.GAME_CARD_TITLE)
        assert f"Название: {mockups.WITCHER.name}" in screen.text
        assert texts.GAME_STATUS_PLAYED in screen.text
        assert texts.GAME_STATUS_FAVORITE in screen.text

    def test_games_list_screen_mentions_filters(self):
        screen = screen_by_file("04_game_list")

        assert screen.text.startswith(texts.GAMES_TITLE)
        assert texts.GAMES_PLAYED_EXCLUDED in screen.text
        assert "жанры: Action, RPG" in screen.text

    def test_franchise_games_title(self):
        screen = screen_by_file("08_franchise_games")

        assert screen.text.startswith(texts.FRANCHISE_GAMES_TITLE.format("Marvel"))

    def test_played_list_screen(self):
        screen = screen_by_file("10_played_list")

        assert screen.text.startswith(texts.PLAYED_TITLE)
        assert texts.PLAYED_FOOTER in screen.text

    def test_favorites_screen(self):
        screen = screen_by_file("12_favorites")

        assert screen.text.startswith(texts.FAVORITES_TITLE)
        assert texts.FAVORITES_FOOTER in screen.text

    def test_review_screen_mentions_limit(self):
        screen = screen_by_file("11a_review_input")

        assert texts.REVIEW_PROMPT in screen.text
        assert "1000" in screen.text
        assert mockups.PLAYED[0].name in screen.text

    def test_buttons_are_real_keyboard_labels(self):
        card = screen_by_file("05_game_card")
        expected = mockups.labels_of(
            keyboards.game_card_keyboard(mockups.WITCHER.id, is_favorite=True)
        )

        assert card.buttons == expected

    def test_games_list_buttons_match_keyboard(self):
        screen = screen_by_file("04_game_list")
        expected = mockups.labels_of(
            keyboards.games_keyboard(
                mockups.GAME_PAGE.games, mockups.GAME_PAGE.page, has_next=True
            )
        )

        assert screen.buttons == expected

    def test_profile_buttons_match_keyboard(self):
        screen = screen_by_file("09_profile")

        assert screen.buttons == mockups.labels_of(
            keyboards.profile_keyboard(has_age=True, has_region=True)
        )

    def test_picking_genres_buttons_mark_selected(self):
        screen = screen_by_file("03_picking_genres")
        labels = [label for row in screen.buttons for label in row]

        assert "✔ Action" in labels
        assert "✔ RPG" in labels
        assert "Shooter" in labels


# --------------------------------------------------------------------------- #
# Примеры данных
# --------------------------------------------------------------------------- #
class TestSampleData:
    def test_games_are_complete(self):
        for game in mockups.GAMES:
            assert game.name
            assert game.slug
            assert game.genres
            assert game.platforms
            assert game.released is not None

    def test_page_is_consistent(self):
        page = mockups.GAME_PAGE

        assert len(page.games) == page.page_size
        assert page.total_count > len(page.games)
        assert page.has_next is True

    def test_profile_has_region(self):
        profile = mockups.PROFILE

        assert profile.region is not None
        assert profile.region.is_known is True
        assert profile.genre_slugs == mockups.SELECTED_GENRES

    def test_franchises_have_game_counts(self):
        assert [franchise.games_count for franchise in mockups.FRANCHISES] == [24, 4]

    def test_played_records_have_dates_in_past(self):
        dates = [record.played_at for record in mockups.PLAYED]

        assert dates == sorted(dates, reverse=True)

    def test_labels_of_inline_markup(self):
        markup = keyboards.back_to_menu_keyboard()

        assert mockups.labels_of(markup) == ((keyboards.ButtonText.BACK_TO_MENU,),)

    def test_labels_of_dict_buttons(self):
        class Markup:
            keyboard = [[{"text": "Кнопка"}]]

        assert mockups.labels_of(Markup()) == (("Кнопка",),)

    def test_labels_of_empty_markup(self):
        assert mockups.labels_of(keyboards.hide_keyboard()) == ()


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #
class TestHelpers:
    def test_escape_special_characters(self):
        assert mockups.escape("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_wrap_short_line(self):
        assert mockups.wrap("Короткая строка") == ["Короткая строка"]

    def test_wrap_long_line(self):
        lines = mockups.wrap("слово " * 30)

        assert all(len(line) <= mockups.CHARS_PER_LINE for line in lines)
        assert "".join(lines).count("слово") == 30

    def test_wrap_keeps_paragraphs(self):
        assert mockups.wrap("Первая строка\n\nВторая строка") == [
            "Первая строка",
            "",
            "Вторая строка",
        ]

    def test_wrap_does_not_split_words(self):
        assert mockups.wrap("ОченьДлинноеСловоБезПробелов", limit=10) == [
            "ОченьДлинноеСловоБезПробелов"
        ]

    @pytest.mark.parametrize(
        "buttons, expected",
        [
            ((("Текст",),), [[("Текст", False)]]),
            ((("Текст", True),), [[("Текст", True)]]),
            ((("Первая", "Вторая"),), [[("Первая", False), ("Вторая", False)]]),
            ((("Единственная",),), [[("Единственная", False)]]),
        ],
    )
    def test_normalize_rows(self, buttons, expected):
        assert mockups.normalize_rows(buttons) == expected

    def test_normalize_rows_mixed(self):
        rows = mockups.normalize_rows((("Главная", True), ("Одна", "Две")))

        assert rows == [[("Главная", True)], [("Одна", False), ("Две", False)]]

    def test_button_width_has_bounds(self):
        width = mockups.button_width("Очень длинная подпись кнопки", 351, 1)

        assert 110 <= width <= 351

    def test_button_width_min_for_short_label(self):
        assert mockups.button_width("ОК", 351, 1) == 110

    def test_buttons_row_fits_screen(self):
        svg, y = mockups.render_buttons(
            mockups.normalize_rows((("Первая длинная кнопка", "Вторая длинная кнопка"),)), 100
        )

        for x, _, width, _ in rects_of(svg, fragment=True):
            assert x + width <= mockups.WIDTH - mockups.MARGIN + 1
        assert y > 100

    def test_single_button_spans_row(self):
        svg, _ = mockups.render_buttons(mockups.normalize_rows((("Одна кнопка",),)), 100)
        _, _, width, _ = rects_of(svg, fragment=True)[0]

        assert width == mockups.WIDTH - 2 * mockups.MARGIN

    def test_reply_keyboard_is_at_the_bottom(self):
        svg = mockups.render_reply_keyboard((("Кнопка",),))
        _, y, _, height = rects_of(svg, fragment=True)[0]

        assert y + height == mockups.HEIGHT

    def test_reply_keyboard_rows(self):
        svg = mockups.render_reply_keyboard((("Первая",), ("Вторая", "Третья")))

        assert len([rect for rect in rects_of(svg, fragment=True) if rect[3] == 44]) == 3

    def test_hidden_keyboard_note(self):
        svg = mockups.render_hidden_keyboard()

        assert "клавиатура скрыта" in " ".join(texts_of(svg, fragment=True))

    def test_empty_rows_are_skipped(self):
        svg, y = mockups.render_buttons(mockups.normalize_rows(()), 100)

        assert svg == ""
        assert y == 100


class TestBubbles:
    def test_bubble_contains_all_lines(self):
        svg, _ = mockups.render_bubble(["Строка 1", "Строка 2"], 100)

        assert "Строка 1" in texts_of(svg, fragment=True)
        assert "Строка 2" in texts_of(svg, fragment=True)

    def test_bubble_height_grows_with_text(self):
        _, short = mockups.render_bubble(["Одна строка"], 100)
        _, tall = mockups.render_bubble(["Строка"] * 10, 100)

        assert tall > short

    def test_photo_placeholder(self):
        svg, with_photo = mockups.render_bubble(["Текст"], 100, photo=True)
        _, without_photo = mockups.render_bubble(["Текст"], 100)

        assert with_photo > without_photo
        assert "обложка игры" in " ".join(texts_of(svg, fragment=True))

    def test_note_is_rendered_smaller(self):
        svg, _ = mockups.render_bubble(["Текст"], 100, note="Примечание к экрану")

        assert "Примечание к экрану" in " ".join(texts_of(svg, fragment=True))
        assert f'font-size="{mockups.SMALL_FONT_SIZE}"' in svg

    def test_bubble_width_fits_screen(self):
        svg, _ = mockups.render_bubble(["Текст"], 100)

        for x, _, width, _ in rects_of(svg, fragment=True):
            assert x >= 0
            assert x + width <= mockups.WIDTH

    def test_title_lines_are_bold(self):
        svg, _ = mockups.render_bubble([texts.PROFILE_TITLE], 100)

        assert 'font-weight="600"' in svg


# --------------------------------------------------------------------------- #
# Отрисовка экранов
# --------------------------------------------------------------------------- #
class TestRendering:
    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_svg_is_well_formed(self, screen):
        root = ET.fromstring(mockups.render_screen(screen))

        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert root.get("width") == str(mockups.WIDTH)
        assert root.get("height") == str(mockups.frame_height(screen))

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_title_and_header(self, screen):
        svg = mockups.render_screen(screen)
        root = ET.fromstring(svg)
        title = root.find("svg:title", SVG_NS)

        assert title is not None
        assert title.text == screen.title
        assert texts.BOT_NAME in " ".join(texts_of(svg))
        assert "@GameHunterBot" in " ".join(texts_of(svg))

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_message_text_is_present(self, screen):
        rendered = " ".join(texts_of(mockups.render_screen(screen)))

        for line in mockups.wrap(screen.text):
            if line:
                assert line in rendered

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_buttons_are_rendered(self, screen):
        rendered = " ".join(texts_of(mockups.render_screen(screen)))

        for row in mockups.normalize_rows(screen.buttons):
            for label, _ in row:
                assert label in rendered

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_keyboard_buttons_are_rendered(self, screen):
        if not screen.keyboard:
            pytest.skip("экран без обычной клавиатуры")

        rendered = " ".join(texts_of(mockups.render_screen(screen)))

        for row in screen.keyboard:
            for label in row:
                assert label in rendered

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_hidden_keyboard_is_rendered(self, screen):
        if not screen.hidden_keyboard:
            pytest.skip("экран с видимой клавиатурой")

        rendered = " ".join(texts_of(mockups.render_screen(screen)))

        assert "клавиатура скрыта" in rendered

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_content_fits_phone_frame(self, screen):
        svg = mockups.render_screen(screen)
        height = mockups.frame_height(screen)
        limit = height - 44  # оставляем место для подписи экрана
        rows = screen.keyboard or ()
        keyboard_top = height - (len(rows) * 52 + 16) if rows else height

        for x, y, width, height in rects_of(svg):
            if height >= mockups.HEADER_HEIGHT and x == 0 and width == mockups.WIDTH:
                continue  # фон экрана, шапка и подложка клавиатуры
            if y >= keyboard_top:
                continue  # кнопки обычной клавиатуры прижаты к низу экрана
            assert y + height <= limit, f"{screen.file}: контент выходит за рамку"

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_text_fits_phone_frame(self, screen):
        root = ET.fromstring(mockups.render_screen(screen))
        height = mockups.frame_height(screen)

        for node in root.iter("{http://www.w3.org/2000/svg}text"):
            if node.text == screen.caption:
                continue  # подпись экрана под рамкой диалога
            assert float(node.get("y")) <= height - 20, screen.file

    @pytest.mark.parametrize("screen", SCREENS, ids=IDS)
    def test_message_does_not_overlap_keyboard(self, screen):
        rows = screen.keyboard or ()
        if not rows:
            pytest.skip("экран без обычной клавиатуры")

        keyboard_top = mockups.frame_height(screen) - (len(rows) * 52 + 16)
        _, content_bottom = mockups.render_bubble(
            mockups.wrap(screen.text), mockups.HEADER_HEIGHT + 16
        )

        assert content_bottom <= keyboard_top, screen.file

    def test_no_unescaped_entities(self):
        for screen in SCREENS:
            svg = mockups.render_screen(screen)
            ET.fromstring(svg)  # бросит исключение при некорректном XML
            assert " & " not in svg.replace("&amp;", "")


# --------------------------------------------------------------------------- #
# Сохранение файлов
# --------------------------------------------------------------------------- #
class TestGenerate:
    def test_creates_all_files(self, tmp_path):
        created = mockups.generate(tmp_path, with_png=False)

        assert len(created) == 18
        assert all(path.exists() for path in created)
        assert {path.name for path in created} == {f"{screen.file}.svg" for screen in SCREENS}

    def test_files_are_valid_svg(self, tmp_path):
        mockups.generate(tmp_path, with_png=False)

        for path in tmp_path.glob("*.svg"):
            root = ET.parse(path).getroot()

            assert root.tag.endswith("svg")
            assert path.read_text(encoding="utf-8").startswith("<svg")

    def test_creates_output_directory(self, tmp_path):
        target = tmp_path / "вложенная" / "папка"

        mockups.generate(target, with_png=False)

        assert target.exists()
        assert len(list(target.glob("*.svg"))) == 18

    def test_png_is_skipped_without_converter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mockups, "save_png", lambda path: None)

        mockups.generate(tmp_path, with_png=True)

        assert list(tmp_path.glob("*.png")) == []

    def test_png_is_created_with_converter(self, tmp_path, monkeypatch):
        def fake_save_png(path: Path) -> str:
            target = path.with_suffix(".png")
            target.write_bytes(b"png")
            return str(target)

        monkeypatch.setattr(mockups, "save_png", fake_save_png)

        mockups.generate(tmp_path, with_png=True)

        assert len(list(tmp_path.glob("*.png"))) == 18

    def test_save_png_reports_missing_converter(self, tmp_path, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "cairosvg":
                raise ImportError("нет cairosvg")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        path = tmp_path / "screen.svg"
        path.write_text("<svg/>", encoding="utf-8")

        assert mockups.save_png(path) is None

    def test_save_png_handles_converter_error(self, tmp_path, monkeypatch, capsys):
        import sys

        class FakeCairo:
            @staticmethod
            def svg2png(**kwargs):
                raise OSError("не удалось растеризовать")

        monkeypatch.setitem(sys.modules, "cairosvg", FakeCairo)
        path = tmp_path / "screen.svg"
        path.write_text("<svg/>", encoding="utf-8")

        assert mockups.save_png(path) is None
        assert "Не удалось сохранить PNG" in capsys.readouterr().out

    def test_cli_creates_files(self, tmp_path, capsys):
        code = mockups.main(["--out", str(tmp_path), "--no-png"])

        assert code == 0
        assert "Создано мокапов: 18" in capsys.readouterr().out
        assert len(list(tmp_path.glob("*.svg"))) == 18

    def test_cli_reports_missing_png_converter(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(mockups, "save_png", lambda path: None)

        mockups.main(["--out", str(tmp_path)])

        assert "PNG пропущены" in capsys.readouterr().out


class TestRepoMockups:
    """Мокапы в репозитории должны совпадать с результатом генератора."""

    def test_directory_exists(self):
        assert MOCKUPS_DIR.exists()

    def test_all_screens_are_present(self):
        assert {path.name for path in MOCKUPS_DIR.glob("*.svg")} == {
            f"{screen.file}.svg" for screen in SCREENS
        }

    def test_no_extra_files(self):
        extra = [path.name for path in MOCKUPS_DIR.iterdir() if path.suffix != ".svg"]

        assert extra == [], "в папке должны быть только SVG-мокапы (PNG создаёт cairosvg)"

    def test_content_is_up_to_date(self):
        stale = [
            screen.file
            for screen in SCREENS
            if (MOCKUPS_DIR / f"{screen.file}.svg").read_text(encoding="utf-8")
            != mockups.render_screen(screen)
        ]

        assert stale == [], f"пересоберите мокапы: make mockups (устарели: {stale})"
