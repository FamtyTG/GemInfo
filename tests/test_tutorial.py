"""Тесты обучающих видеокарточек: бот шлёт их прямо на своих экранах.

Отдельного раздела «Обучение» нет: ролик приветствия приходит после /start,
ролик выбора жанра — на Экране 3, ролик подборки — на Экране 4. Ошибки
отправки не должны ломать основной сценарий экрана.
"""

from __future__ import annotations

from gamehunter.presentation import texts
from gamehunter.presentation.screens import tutorial as tutorial_module
from gamehunter.presentation.screens.tutorial import TUTORIAL_CARDS
from gamehunter.presentation.state import UserContext

CHAT_ID = 100
USER_ID = 200


class TestTutorialAssets:
    """Ролики собраны и лежат в репозитории."""

    def test_all_cards_exist(self):
        for card_key in TUTORIAL_CARDS:
            video = tutorial_module.animation_path(card_key)
            assert video.exists(), f"нет файла {video}"
            assert video.stat().st_size > 100_000  # не пустая заглушка

    def test_cards_have_steps_in_texts(self):
        assert texts.TUTORIAL_CARD_NUMBERS["01_start"] == 1
        for card_key in TUTORIAL_CARDS:
            assert texts.TUTORIAL_STEPS[card_key]
            caption = texts.tutorial_caption(card_key)
            for step in texts.TUTORIAL_STEPS[card_key]:
                assert step in caption


class TestInlineDelivery:
    """Каждый экран присылает свою обучающую карточку."""

    def test_start_screen_sends_greeting_video(self, screens, gateway):
        screens.start.show(CHAT_ID)

        assert len(gateway.animations) == 1
        sent = gateway.animations[0]
        assert sent.chat_id == CHAT_ID
        assert sent.animation.name == "01_start.mp4"
        assert "Карточка 1 из 3" in sent.text
        assert texts.TUTORIAL_STEPS["01_start"][0] in sent.text
        # приветственное сообщение ушло ДО ролика
        assert gateway.messages[0].text == texts.START_WELCOME

    def test_genre_picking_sends_video(self, screens, gateway):
        screens.genre_picking.show(CHAT_ID, USER_ID)

        assert [item.animation.name for item in gateway.animations] == [
            "03_picking_genres.mp4"
        ]

    def test_game_list_sends_video(self, screens, gateway, storage):
        storage.save(USER_ID, UserContext())
        screens.game_list.show(CHAT_ID, USER_ID, page=1)

        assert [item.animation.name for item in gateway.animations] == [
            "04_game_list.mp4"
        ]

    def test_pagination_does_not_resend_video(self, screens, gateway, storage):
        """Листание страниц — это rerender, ролик повторно не шлётся."""
        storage.save(USER_ID, UserContext())
        screens.game_list.show(CHAT_ID, USER_ID, page=1)
        before = len(gateway.animations)

        screens.game_list.rerender(CHAT_ID, USER_ID)

        assert len(gateway.animations) == before

    def test_missing_file_is_not_fatal(self, screens, gateway, monkeypatch, tmp_path):
        monkeypatch.setattr(tutorial_module, "ASSETS_DIR", tmp_path)

        screens.start.show(CHAT_ID)

        assert not gateway.animations
        assert gateway.messages[0].text == texts.START_WELCOME  # экран работает

    def test_send_failure_is_not_fatal(self, screens, gateway):
        gateway.animation_fails = True

        screens.start.show(CHAT_ID)

        assert not gateway.animations
        assert gateway.messages[0].text == texts.START_WELCOME
