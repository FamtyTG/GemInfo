"""Тесты Экрана 13 «Обучение»: анимированные карточки-инструкции (GIF)."""

from __future__ import annotations

from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.screens import tutorial as tutorial_module
from gamehunter.presentation.screens.tutorial import TUTORIAL_CARDS
from tests.fakes import buttons_of, make_callback

CHAT_ID = 100
USER_ID = 200


class TestTutorialAssets:
    """Сами карточки собраны и лежат в репозитории."""

    def test_all_cards_exist(self):
        for card_key in TUTORIAL_CARDS:
            gif = tutorial_module.ASSETS_DIR / f"{card_key}.gif"
            assert gif.exists(), f"нет файла {gif}"
            assert gif.stat().st_size > 100_000  # не пустая заглушка

    def test_cards_have_steps_in_texts(self):
        assert texts.TUTORIAL_CARD_NUMBERS["01_start"] == 1
        for card_key in TUTORIAL_CARDS:
            assert texts.TUTORIAL_STEPS[card_key]
            assert texts.tutorial_caption(card_key)


class TestTutorialScreen:
    def test_show_lists_cards(self, screens, gateway):
        screens.tutorial.show(CHAT_ID, USER_ID)

        assert texts.TUTORIAL_MENU_TITLE in gateway.last_text
        flat = [label for row in buttons_of(gateway.last_markup) for label in row]
        assert "1️⃣ Приветствие" in flat
        assert "▶️ Смотреть все" in flat
        callbacks = [
            button.callback_data
            for row in gateway.last_markup.keyboard
            for button in row
            if getattr(button, "callback_data", None)
        ]
        assert keyboards.CallbackAction.TUTORIAL_ALL in callbacks
        for card_key in TUTORIAL_CARDS:
            assert f"{keyboards.CallbackAction.TUTORIAL_CARD}:{card_key}" in callbacks

    def test_send_card_sends_animation_with_caption(self, screens, gateway):
        screens.tutorial.send_card(CHAT_ID, USER_ID, "01_start")

        assert len(gateway.animations) == 1
        sent = gateway.animations[0]
        assert sent.chat_id == CHAT_ID
        assert sent.animation is not None and sent.animation.name == "01_start.gif"
        assert "Карточка 1 из 3" in sent.text
        assert texts.TUTORIAL_STEPS["01_start"][0] in sent.text

    def test_send_all_sends_three_cards_in_order(self, screens, gateway):
        screens.tutorial.send_all(CHAT_ID, USER_ID)

        assert [item.animation.stem for item in gateway.animations] == list(TUTORIAL_CARDS)

    def test_unknown_card_returns_to_menu(self, screens, gateway):
        screens.tutorial.send_card(CHAT_ID, USER_ID, "no_such_card")

        assert not gateway.animations
        assert texts.TUTORIAL_MENU_TITLE in gateway.last_text

    def test_missing_file_notifies(self, screens, gateway, tmp_path, monkeypatch):
        monkeypatch.setattr(tutorial_module, "ASSETS_DIR", tmp_path)

        screens.tutorial.send_card(CHAT_ID, USER_ID, "01_start")

        assert not gateway.animations
        assert texts.TUTORIAL_MISSING in gateway.last_text

    def test_send_failure_notifies(self, screens, gateway):
        gateway.animation_fails = True

        screens.tutorial.send_card(CHAT_ID, USER_ID, "03_picking_genres")

        assert texts.TUTORIAL_MISSING in gateway.last_text


class TestTutorialRoutes:
    def test_callback_opens_menu(self, handlers, gateway):
        handlers.on_callback(make_callback(keyboards.CallbackAction.TUTORIAL))

        assert texts.TUTORIAL_MENU_TITLE in gateway.last_text

    def test_callback_sends_card(self, handlers, gateway):
        handlers.on_callback(
            make_callback(f"{keyboards.CallbackAction.TUTORIAL_CARD}:04_game_list")
        )

        assert len(gateway.animations) == 1
        assert gateway.animations[0].animation.name == "04_game_list.gif"

    def test_callback_card_without_value(self, handlers, gateway):
        handlers.on_callback(make_callback(f"{keyboards.CallbackAction.TUTORIAL_CARD}:"))

        assert texts.UNKNOWN_COMMAND in gateway.last_text

    def test_callback_sends_all(self, handlers, gateway):
        handlers.on_callback(make_callback(keyboards.CallbackAction.TUTORIAL_ALL))

        assert len(gateway.animations) == 3

    def test_menu_button_opens_tutorial(self, handlers, gateway, storage):
        from gamehunter.presentation.state import UserContext
        from tests.fakes import make_message

        storage.save(USER_ID, UserContext())
        handlers.on_text(make_message(text=keyboards.ButtonText.TUTORIAL))

        assert texts.TUTORIAL_MENU_TITLE in gateway.last_text
