"""Тесты Экрана 14 «Возрастной рейтинг» (подбор игр по категории ESRB/PEGI)."""

from __future__ import annotations

from gamehunter.domain import age_ratings
from gamehunter.presentation import keyboards, texts
from gamehunter.presentation.state import ContextScreen

CHAT_ID = 100
USER_ID = 200


def last_buttons(gateway):
    from tests.fakes import buttons_of

    return buttons_of(gateway.last_markup)


class TestAgeRatingScreen:
    def test_show_lists_categories(self, screens, gateway, storage):
        screens.age_rating.show(CHAT_ID, USER_ID)

        assert texts.AGE_RATING_TITLE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.AGE_RATING
        flat = [label for row in last_buttons(gateway) for label in row]
        assert "13+ — подросткам (ESRB T)" in flat

    def test_show_mentions_current_choice(self, screens, gateway):
        screens.age_rating.pick(CHAT_ID, USER_ID, 10)
        screens.age_rating.show(CHAT_ID, USER_ID)

        assert texts.AGE_RATING_CURRENT.format(age_ratings.rating_label(10)) in gateway.last_text
        assert "✔ 10+ — ESRB E10+" in [
            label for row in last_buttons(gateway) for label in row
        ]

    def test_pick_saves_rating_and_shows_games(self, screens, gateway, storage):
        screens.age_rating.pick(CHAT_ID, USER_ID, 17)

        assert storage.get(USER_ID).age_rating == 17
        assert storage.get(USER_ID).screen == ContextScreen.GAME_LIST
        assert texts.GAMES_TITLE_WITH_RATING.format("17+ — взрослым (ESRB M)") in gateway.last_text
        # в клавиатуре подборки появляется строка смены рейтинга
        assert any(
            keyboards.ButtonText.CHANGE_RATING in row for row in last_buttons(gateway)
        )

    def test_pick_unknown_rating_returns_to_choice(self, screens, gateway, storage):
        screens.age_rating.pick(CHAT_ID, USER_ID, 99)

        assert storage.get(USER_ID).age_rating is None
        assert texts.AGE_RATING_TITLE in gateway.last_text

    def test_reset_returns_to_profile_age(self, screens, gateway, storage):
        screens.age_rating.pick(CHAT_ID, USER_ID, 17)
        screens.age_rating.reset(CHAT_ID, USER_ID)

        assert storage.get(USER_ID).age_rating is None
        assert texts.AGE_RATING_RESET_DONE in gateway.last_text
        assert storage.get(USER_ID).screen == ContextScreen.AGE_RATING
