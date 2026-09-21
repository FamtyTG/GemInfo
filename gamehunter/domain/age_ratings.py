"""Возрастные рейтинги игр и правило «подходит ли игра пользователю».

RAWG отдаёт возрастной рейтинг в формате ESRB (Early Childhood, Everyone,
Teen, Mature…), иногда встречаются обозначения PEGI (3, 7, 12, 16, 18).
Здесь они приводятся к минимальному возрасту, чтобы можно было отфильтровать
игры по возрасту пользователя из анкеты.

Модуль намеренно не зависит ни от чего внешнего — это чистое бизнес-правило.
"""

from __future__ import annotations

import re
from typing import Optional

# ESRB (США) — минимальный возраст
ESRB_MIN_AGE = {
    "rp": None,       # Rating Pending — рейтинг ещё не присвоен
    "ec": 3,          # Early Childhood
    "e": 6,           # Everyone
    "e10+": 10,       # Everyone 10 and older
    "t": 13,          # Teen
    "m": 17,          # Mature 17+
    "ao": 18,         # Adults Only 18+
}

# PEGI (Европа) — минимальный возраст
PEGI_MIN_AGE = {3: 3, 7: 7, 12: 12, 16: 16, 18: 18}

# Подписи возрастных рейтингов для показа пользователю
AGE_LABELS = {
    3: "ESRB Early Childhood",
    6: "ESRB Everyone",
    10: "ESRB Everyone 10+",
    13: "ESRB Teen",
    17: "ESRB Mature",
    18: "18+",
}

_PEGI_PATTERN = re.compile(r"pegi[\s_-]*(\d{1,2})", re.IGNORECASE)
_ESRB_PATTERN = re.compile(
    r"\b(everyone\s*10\s*\+|everyone\s*10|early\s*childhood|everyone|mature|teen|adults?\s*only|"
    r"rating\s*pending|e10\+|ao|rp|ec|e|m|t)\b",
    re.IGNORECASE,
)
_ESRB_SHORT_TO_LABEL = {
    "e10+": "e10+",
    "everyone 10+": "e10+",
    "everyone 10": "e10+",
    "early childhood": "ec",
    "everyone": "e",
    "mature": "m",
    "teen": "t",
    "adults only": "ao",
    "adult only": "ao",
    "rating pending": "rp",
    "ao": "ao",
    "rp": "rp",
    "ec": "ec",
    "e": "e",
    "m": "m",
    "t": "t",
}


def min_age_from_label(label: Optional[str]) -> Optional[int]:
    """Определяет минимальный возраст по текстовой метке рейтинга.

    Поддерживает ESRB («Teen», «Mature», «E10+») и PEGI («PEGI 16», «12+»).
    Возвращает None, если рейтинг неизвестен.
    """
    if not label:
        return None

    text = str(label).strip()
    if not text:
        return None

    # 1) PEGI 16 / pegi-12 / PEGI: 7
    match = _PEGI_PATTERN.search(text)
    if match:
        value = int(match.group(1))
        if value in PEGI_MIN_AGE:
            return PEGI_MIN_AGE[value]

    # 2) числовой рейтинг вида «16+», «18+», «12»
    digits = re.findall(r"(\d{1,2})\s*\+?", text)
    for digit in digits:
        value = int(digit)
        if value in (3, 6, 7, 10, 12, 13, 16, 17, 18):
            return value

    # 3) ESRB по названию
    match = _ESRB_PATTERN.search(text)
    if match:
        key = _ESRB_SHORT_TO_LABEL.get(match.group(1).lower().strip())
        if key is not None:
            return ESRB_MIN_AGE.get(key)

    return None


def age_label(min_age: Optional[int], raw_label: str = "") -> str:
    """Человекочитаемая подпись возрастного рейтинга."""
    if raw_label:
        return raw_label
    if min_age is None:
        return ""
    return AGE_LABELS.get(min_age, f"{min_age}+")


class AgePolicy:
    """Правило допуска игры по возрасту пользователя."""

    #: Минимальный и максимальный возраст в анкете пользователя
    MIN_PROFILE_AGE = 3
    MAX_PROFILE_AGE = 120

    #: Возраст по умолчанию, если пользователь его не указал
    DEFAULT_AGE = 18

    def is_suitable(self, min_age: Optional[int], user_age: Optional[int]) -> bool:
        """Подходит ли игра пользователю указанного возраста.

        * возраст пользователя неизвестен — подходят все игры;
        * рейтинг игры неизвестен — игра не отсеивается (показываем с пометкой);
        * иначе игра подходит, если ``min_age <= user_age``.
        """
        if user_age is None:
            return True
        if min_age is None:
            return True
        return min_age <= user_age

    @staticmethod
    def validate_age(value: int) -> int:
        """Проверяет, что возраст допустим для анкеты."""
        if value < AgePolicy.MIN_PROFILE_AGE or value > AgePolicy.MAX_PROFILE_AGE:
            raise ValueError(
                f"Возраст должен быть от {AgePolicy.MIN_PROFILE_AGE} "
                f"до {AgePolicy.MAX_PROFILE_AGE}"
            )
        return value


# --------------------------------------------------------------------------- #
# Категории выбора на Экране 14 «Возрастной рейтинг»
# --------------------------------------------------------------------------- #
#: (минимальный возраст, подпись кнопки) — пары для клавиатуры выбора рейтинга
RATING_CHOICES: Tuple[Tuple[int, str], ...] = (
    (3, "3+ — малышам (ESRB EC)"),
    (6, "6+ — всем (ESRB E)"),
    (10, "10+ — ESRB E10+"),
    (13, "13+ — подросткам (ESRB T)"),
    (17, "17+ — взрослым (ESRB M)"),
    (18, "18+ — только взрослым (ESRB AO)"),
)


def rating_label(age: Optional[int]) -> str:
    """Подпись выбранного рейтинга для текстов: 13 → «13+ …»."""
    if age is None:
        return ""
    return dict(RATING_CHOICES).get(age, f"{age}+")
