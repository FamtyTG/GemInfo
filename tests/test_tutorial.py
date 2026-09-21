"""Тесты обучающих видеокарточек: ролик приходит тем же сообщением, что экран.

Отдельного раздела «Обучение» и подписей «Карточка N из 3» нет: сверху видео,
снизу — обычный текст экрана (подпись) и его клавиатура. Ошибки отправки не
должны ломать основной сценарий: экран тогда уходит простым текстом.
"""

from __future__ import annotations

from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.screens import tutorial as tutorial_module
from gamehunter.presentation.screens.tutorial import TUTORIAL_CARDS
from gamehunter.presentation.state import UserContext
from tests.fakes import buttons_of

CHAT_ID = 100
USER_ID = 200


class TestTutorialAssets:
    """Ролики собраны и лежат в репозитории."""

    def test_all_cards_exist(self):
        for card_key in TUTORIAL_CARDS:
            video = tutorial_module.animation_path(card_key)
            assert video.exists(), f"нет файла {video}"
            assert video.stat().st_size > 100_000  # не пустая заглушка

    def test_steps_live_in_texts(self):
        """Шаги обучения рисуются внутри ролика (панель справа)."""
        for card_key in TUTORIAL_CARDS:
            assert texts.TUTORIAL_STEPS[card_key]


class TestInlineDelivery:
    """Видео и текст экрана — одно сообщение Telegram."""

    def test_start_screen_single_message_with_video(self, screens, gateway):
        screens.start.show(CHAT_ID)

        assert len(gateway.events) == 1          # одно сообщение, не два
        assert not gateway.messages              # отдельного текстового нет
        sent = gateway.animations[0]
        assert sent.chat_id == CHAT_ID
        assert sent.animation.name == "01_start.mp4"
        assert sent.text == texts.START_WELCOME  # подпись = текст экрана
        assert "Карточка" not in sent.text       # без нумерации карточек
        assert buttons_of(sent.markup) == [[keyboards.ButtonText.START]]

    def test_genre_picking_single_message_with_video(self, screens, gateway):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        assert len(gateway.events) == 1
        sent = gateway.animations[0]
        assert sent.animation.name == "03_picking_genres.mp4"
        assert texts.GENRES_TITLE in sent.text
        assert texts.GENRES_FOOTER in sent.text
        flat = [label for row in buttons_of(sent.markup) for label in row]
        assert "Показать подборку" in flat

    def test_game_list_single_message_with_video(self, screens, gateway, storage):
        storage.save(USER_ID, UserContext())
        screens.game_list.show(CHAT_ID, USER_ID, page=1)

        assert len(gateway.events) == 1
        sent = gateway.animations[0]
        assert sent.animation.name == "04_game_list.mp4"
        assert texts.GAMES_TITLE in sent.text

    def test_toggle_genre_has_no_video(self, screens, gateway):
        """Отметка жанра — не новый вход на экран, ролик повторно не шлётся."""
        screens.genre_picking.show(CHAT_ID, USER_ID)
        screens.genre_picking.toggle(CHAT_ID, USER_ID, "action")

        assert len(gateway.animations) == 1
        assert texts.GENRES_TITLE in gateway.last_text  # текст обновился

    def test_pagination_does_not_resend_video(self, screens, gateway, storage):
        """Листание страниц — это rerender, ролик повторно не шлётся."""
        storage.save(USER_ID, UserContext())
        screens.game_list.show(CHAT_ID, USER_ID, page=1)

        screens.game_list.rerender(CHAT_ID, USER_ID)

        assert len(gateway.animations) == 1

    def test_missing_file_falls_back_to_text(self, screens, gateway, monkeypatch, tmp_path):
        monkeypatch.setattr(tutorial_module, "ASSETS_DIR", tmp_path)

        screens.start.show(CHAT_ID)

        assert not gateway.animations
        assert gateway.messages[0].text == texts.START_WELCOME  # экран работает
        assert buttons_of(gateway.messages[0].markup) == [[keyboards.ButtonText.START]]

    def test_send_failure_falls_back_to_text(self, screens, gateway):
        gateway.animation_fails = True

        screens.start.show(CHAT_ID)

        assert not gateway.animations
        assert gateway.messages[0].text == texts.START_WELCOME
