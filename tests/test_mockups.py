"""Тесты генератора мокапов экранов (артефакт проекта)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import scripts.generate_mockups as mockups_module
from scripts.generate_mockups import ScreenMockup, build_mockups, render_screen
from travelhunter.presentation import keyboards, texts


def test_build_mockups_covers_all_nine_screens():
    filenames = [mockup.filename for mockup in build_mockups()]

    assert filenames == [
        "screen_01_start.svg",
        "screen_02_main_menu.svg",
        "screen_03_holidays.svg",
        "screen_04_city_input.svg",
        "screen_05_nearby_cities.svg",
        "screen_06_city_info.svg",
        "screen_07_history.svg",
        "screen_08_trip_info.svg",
        "screen_09_note.svg",
    ]


def test_mockup_texts_are_taken_from_bot_texts():
    mockups = {mockup.filename: mockup for mockup in build_mockups()}

    assert mockups["screen_01_start.svg"].message == texts.START_WELCOME
    assert mockups["screen_02_main_menu.svg"].message == texts.MAIN_MENU_WELCOME
    assert mockups["screen_04_city_input.svg"].message == texts.CITY_INPUT_PROMPT
    assert mockups["screen_09_note.svg"].message == texts.NOTE_PROMPT
    assert texts.HOLIDAYS_TITLE in mockups["screen_03_holidays.svg"].message
    assert texts.HISTORY_TITLE in mockups["screen_07_history.svg"].message
    assert texts.NOTE_ABSENT in mockups["screen_08_trip_info.svg"].message


def test_mockup_buttons_are_taken_from_keyboards():
    mockups = {mockup.filename: mockup for mockup in build_mockups()}

    assert mockups["screen_01_start.svg"].reply_buttons == (keyboards.ButtonText.START,)
    assert mockups["screen_02_main_menu.svg"].reply_buttons == (
        keyboards.ButtonText.HOLIDAYS,
        keyboards.ButtonText.CITIES,
        keyboards.ButtonText.HISTORY,
    )
    assert mockups["screen_05_nearby_cities.svg"].inline_buttons == (
        "Выбрать город 1",
        "Выбрать город 2",
        "Выбрать город 3",
        "Выбрать город 4",
        "Выбрать город 5",
        "Назад",
    )
    assert mockups["screen_08_trip_info.svg"].inline_buttons == (
        keyboards.ButtonText.WRITE_NOTE,
        keyboards.ButtonText.BACK,
        keyboards.ButtonText.BACK_TO_MENU,
    )
    assert mockups["screen_06_city_info.svg"].photo is True


def test_render_screen_creates_valid_svg(tmp_path, monkeypatch):
    monkeypatch.setattr(mockups_module, "OUT_DIR", tmp_path)

    path = render_screen(build_mockups()[0])

    assert path.exists()
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert float(root.get("width")) == mockups_module.PHONE_WIDTH
    # содержимое не выходит за границы холста
    height = float(root.get("height"))
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag == "rect":
            assert float(element.get("y", 0)) + float(element.get("height", 0)) <= height + 1
        if tag == "text":
            assert float(element.get("y", 0)) <= height


def test_select_buttons_helper():
    assert mockups_module.select_buttons(2) == ("Выбрать город 1", "Выбрать город 2")


def test_mockup_dataclass_defaults():
    mockup = ScreenMockup(filename="test.svg", title="Экран", message="Текст")

    assert mockup.inline_buttons == ()
    assert mockup.reply_buttons == ()
    assert mockup.photo is False
    assert mockup.comment == ""
