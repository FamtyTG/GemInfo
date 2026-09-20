"""Тесты возрастных рейтингов и правила допуска игры по возрасту."""

from __future__ import annotations

import pytest

from gamehunter.domain.age_ratings import (
    AGE_LABELS,
    ESRB_MIN_AGE,
    PEGI_MIN_AGE,
    AgePolicy,
    age_label,
    min_age_from_label,
)


class TestMinAgeFromLabel:
    @pytest.mark.parametrize(
        "label, expected",
        [
            ("Early Childhood", 3),
            ("Everyone", 6),
            ("E", 6),
            ("Everyone 10+", 10),
            ("E10+", 10),
            ("Teen", 13),
            ("T", 13),
            ("Mature", 17),
            ("M", 17),
            ("Adults Only", 18),
            ("AO", 18),
        ],
    )
    def test_esrb_labels(self, label, expected):
        assert min_age_from_label(label) == expected

    def test_esrb_label_is_case_insensitive(self):
        assert min_age_from_label("mature") == 17
        assert min_age_from_label("TEEN") == 13

    @pytest.mark.parametrize(
        "label, expected",
        [
            ("PEGI 3", 3),
            ("PEGI 7", 7),
            ("PEGI 12", 12),
            ("pegi-16", 16),
            ("PEGI: 18", 18),
            ("PEGI_16", 16),
        ],
    )
    def test_pegi_labels(self, label, expected):
        assert min_age_from_label(label) == expected

    @pytest.mark.parametrize(
        "label, expected",
        [("16+", 16), ("18+", 18), ("12", 12), ("6+", 6), ("10+", 10)],
    )
    def test_numeric_labels(self, label, expected):
        assert min_age_from_label(label) == expected

    @pytest.mark.parametrize("label", ["", None, "   ", "Rating Pending", "нет данных", "99"])
    def test_unknown_labels(self, label):
        assert min_age_from_label(label) is None

    def test_rating_pending_is_not_a_number(self):
        # «RP» — рейтинг ещё не присвоен, игру нельзя отнести к возрастной группе
        assert min_age_from_label("RP") is None

    def test_unknown_pegi_value_is_ignored(self):
        # 11 не входит в шкалу PEGI — вместо ошибки возвращаем None
        assert min_age_from_label("PEGI 11") is None


class TestAgeLabel:
    def test_raw_label_has_priority(self):
        assert age_label(17, "ESRB Mature") == "ESRB Mature"

    @pytest.mark.parametrize(
        "min_age, expected",
        [(3, "ESRB Early Childhood"), (6, "ESRB Everyone"), (10, "ESRB Everyone 10+"),
         (13, "ESRB Teen"), (17, "ESRB Mature"), (18, "18+")],
    )
    def test_known_min_age(self, min_age, expected):
        assert age_label(min_age) == expected

    def test_unknown_min_age_falls_back_to_number(self):
        assert age_label(16) == "16+"

    def test_without_rating(self):
        assert age_label(None) == ""

    def test_labels_table_covers_esrb_and_pegi(self):
        assert AGE_LABELS[17].startswith("ESRB")
        assert AGE_LABELS[18] == "18+"


class TestRatingTables:
    @pytest.mark.parametrize(
        "code, expected",
        [("ec", 3), ("e", 6), ("e10+", 10), ("t", 13), ("m", 17), ("ao", 18)],
    )
    def test_esrb_table(self, code, expected):
        assert ESRB_MIN_AGE[code] == expected

    def test_esrb_rating_pending_has_no_age(self):
        assert ESRB_MIN_AGE["rp"] is None

    @pytest.mark.parametrize("value", [3, 7, 12, 16, 18])
    def test_pegi_table(self, value):
        assert PEGI_MIN_AGE[value] == value


class TestAgePolicy:
    @pytest.fixture()
    def policy(self) -> AgePolicy:
        return AgePolicy()

    @pytest.mark.parametrize(
        "min_age, user_age, expected",
        [
            (17, 21, True),
            (17, 17, True),
            (17, 13, False),
            (18, 17, False),
            (3, 5, True),
            (None, 10, True),   # рейтинг игры неизвестен — не отсеиваем
            (18, None, True),   # возраст пользователя неизвестен — показываем всё
            (None, None, True),
        ],
    )
    def test_is_suitable(self, policy, min_age, user_age, expected):
        assert policy.is_suitable(min_age, user_age) is expected

    @pytest.mark.parametrize("age", [3, 10, 18, 65, 120])
    def test_validate_age_accepts_valid_values(self, age):
        assert AgePolicy.validate_age(age) == age

    @pytest.mark.parametrize("age", [0, 2, -1, 121, 1000])
    def test_validate_age_rejects_invalid_values(self, age):
        with pytest.raises(ValueError):
            AgePolicy.validate_age(age)

    def test_error_message_mentions_bounds(self):
        with pytest.raises(ValueError) as info:
            AgePolicy.validate_age(1)

        assert "от 3" in str(info.value)
        assert "120" in str(info.value)

    def test_constants(self):
        assert AgePolicy.MIN_PROFILE_AGE == 3
        assert AgePolicy.MAX_PROFILE_AGE == 120
        assert AgePolicy.DEFAULT_AGE == 18
