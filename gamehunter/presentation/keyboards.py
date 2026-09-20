"""Клавиатуры Telegram и работа с callback-данными.

Два вида кнопок:
    * ReplyKeyboardMarkup  — кнопки главного меню (постоянно видны под полем ввода);
    * InlineKeyboardMarkup — выбор жанров, игр, страниц и переходы между экранами.

Callback-данные ограничены 64 байтами, поэтому используются короткие префиксы:
    menu                — главное меню;
    pick                — подбор игр: выбор жанров;
    g:{slug}            — отметить/снять жанр при подборе;
    pick_show           — показать подборку по выбранным жанрам;
    pick_all            — показать подборку без фильтра по жанру;
    games:{стр}         — страница результатов подбора;
    game:{id}           — карточка игры;
    played:{id}         — добавить игру в «Во что я играл»;
    fav:{id}            — добавить/убрать игру из избранного;
    fr / frs:{номер} / frg:{id} — поиск по франшизе (IP);
    profile, p_age, p_genres, pg:{slug}, p_platforms, pl:{id}, p_ip — анкета;
    lib:{стр} / rec:{id} / rev:{id} / del:{id} — «Во что я играл» и отзыв;
    favs:{стр}          — избранное;
    back_games          — назад к списку игр.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from gamehunter.domain.entities import FavoriteGame, Franchise, Game, Genre, PlayedGame, Platform


# ---------------------------------------------------------------------- #
# Надписи на кнопках
# ---------------------------------------------------------------------- #
class ButtonText:
    """Тексты кнопок главного меню и навигации."""

    START = "Старт"
    PICK = "Подобрать игру"
    FRANCHISE = "Игры по франшизе"
    PROFILE = "Моя анкета"
    PLAYED = "Во что я играл"
    FAVORITES = "Избранное"

    BACK_TO_MENU = "В главное меню"
    BACK = "Назад"
    FORWARD = "Вперёд"

    SHOW_SELECTION = "Показать подборку"
    SHOW_ALL = "Показать всё"
    SELECT_GAME = "Выбрать игру {}"
    SELECT_FRANCHISE = "Выбрать франшизу {}"

    SET_AGE = "Указать возраст"
    RESET_AGE = "Убрать возраст"
    SET_GENRES = "Выбрать интересы"
    SET_PLATFORMS = "Выбрать платформы"
    SET_REGION = "Определить регион по IP"
    RESET_REGION = "Убрать регион"
    SAVE = "Сохранить"

    ADD_PLAYED = "Уже играл"
    ADD_FAVORITE = "В избранное"
    REMOVE_FAVORITE = "Убрать из избранного"
    WRITE_REVIEW = "Написать отзыв"
    DELETE_PLAYED = "Удалить из списка"
    OTHER_FRANCHISE = "Другая франшиза"
    OTHER_GENRES = "Другие жанры"


#: Текст reply-кнопки, который пользователь может прислать обычным сообщением
MENU_BUTTON_TEXTS = frozenset(
    {
        ButtonText.START,
        ButtonText.PICK,
        ButtonText.FRANCHISE,
        ButtonText.PROFILE,
        ButtonText.PLAYED,
        ButtonText.FAVORITES,
    }
)


# ---------------------------------------------------------------------- #
# Callback-данные
# ---------------------------------------------------------------------- #
class CallbackAction:
    """Префиксы callback-данных."""

    MAIN_MENU = "menu"
    PICK_GENRES = "pick"
    TOGGLE_GENRE = "g"
    PICK_SHOW = "pick_show"
    PICK_ALL = "pick_all"
    GAMES_PAGE = "games"
    GAME_CARD = "game"
    ADD_PLAYED = "played"
    TOGGLE_FAVORITE = "fav"
    FRANCHISE_INPUT = "fr"
    FRANCHISE_PICK = "frs"
    PROFILE = "profile"
    PROFILE_AGE = "p_age"
    PROFILE_AGE_RESET = "p_age_reset"
    PROFILE_GENRES = "p_genres"
    TOGGLE_PROFILE_GENRE = "pg"
    PROFILE_GENRES_DONE = "p_genres_done"
    PROFILE_PLATFORMS = "p_platforms"
    TOGGLE_PLATFORM = "pl"
    PROFILE_PLATFORMS_DONE = "p_platforms_done"
    PROFILE_IP = "p_ip"
    PROFILE_IP_RESET = "p_ip_reset"
    PLAYED_PAGE = "lib"
    PLAYED_ITEM = "rec"
    REVIEW_INPUT = "rev"
    DELETE_PLAYED = "del"
    FAVORITES_PAGE = "favs"
    BACK_GAMES = "back_games"


@dataclass(frozen=True)
class Callback:
    """Разобранные callback-данные кнопки."""

    action: str
    value: Optional[str] = None

    @property
    def int_value(self) -> Optional[int]:
        """Числовое значение (номер страницы, идентификатор)."""
        if self.value is None:
            return None
        try:
            return int(self.value)
        except ValueError:
            return None


def parse_callback(data: Optional[str]) -> Optional[Callback]:
    """Преобразует строку callback-данных в объект Callback."""
    if not data:
        return None
    action, _, raw_value = data.partition(":")
    if not action:
        return None
    return Callback(action=action, value=raw_value or None)


def _build(action: str, value: Any) -> str:
    return f"{action}:{value}"


def genre_callback(slug: str) -> str:
    return _build(CallbackAction.TOGGLE_GENRE, slug)


def profile_genre_callback(slug: str) -> str:
    return _build(CallbackAction.TOGGLE_PROFILE_GENRE, slug)


def platform_callback(platform_id: int) -> str:
    return _build(CallbackAction.TOGGLE_PLATFORM, platform_id)


def games_page_callback(page: int) -> str:
    return _build(CallbackAction.GAMES_PAGE, max(1, page))


def game_callback(game_id: int) -> str:
    return _build(CallbackAction.GAME_CARD, game_id)


def add_played_callback(game_id: int) -> str:
    return _build(CallbackAction.ADD_PLAYED, game_id)


def favorite_callback(game_id: int) -> str:
    return _build(CallbackAction.TOGGLE_FAVORITE, game_id)


def franchise_pick_callback(index: int) -> str:
    return _build(CallbackAction.FRANCHISE_PICK, index)


def played_page_callback(page: int) -> str:
    return _build(CallbackAction.PLAYED_PAGE, max(1, page))


def record_callback(record_id: int) -> str:
    return _build(CallbackAction.PLAYED_ITEM, record_id)


def review_callback(record_id: int) -> str:
    return _build(CallbackAction.REVIEW_INPUT, record_id)


def delete_played_callback(record_id: int) -> str:
    return _build(CallbackAction.DELETE_PLAYED, record_id)


def favorites_page_callback(page: int) -> str:
    return _build(CallbackAction.FAVORITES_PAGE, max(1, page))


# ---------------------------------------------------------------------- #
# Reply-клавиатуры
# ---------------------------------------------------------------------- #
def start_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Экрана 1 «Старт»."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(ButtonText.START)
    return markup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Экрана 2 «Главное меню»."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(ButtonText.PICK, ButtonText.FRANCHISE)
    markup.add(ButtonText.PROFILE)
    markup.add(ButtonText.PLAYED, ButtonText.FAVORITES)
    return markup


def hide_keyboard() -> ReplyKeyboardRemove:
    """Убирает reply-клавиатуру (на время ввода текста)."""
    return ReplyKeyboardRemove()


# ---------------------------------------------------------------------- #
# Inline-клавиатуры
# ---------------------------------------------------------------------- #
def _inline(*rows: Sequence[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for row in rows:
        if row:
            markup.row(*row)
    return markup


def _pairs(items: Sequence) -> List[Tuple[Any, Any]]:
    """Разбивает последовательность на пары (кнопки в два столбца)."""
    values = list(items)
    result: List[Tuple[Any, Any]] = []
    for index in range(0, len(values), 2):
        right = values[index + 1] if index + 1 < len(values) else None
        result.append((values[index], right))
    return result


def _label(text: str, selected: bool) -> str:
    return f"✔ {text}" if selected else text


def _pagination_row(
    page: int, total_pages: int, callback_builder
) -> List[InlineKeyboardButton]:
    """Строка с кнопками «Назад» / «Вперёд» для списков со страницами."""
    row: List[InlineKeyboardButton] = []
    if page > 1:
        row.append(
            InlineKeyboardButton(ButtonText.BACK, callback_data=callback_builder(page - 1))
        )
    if page < total_pages:
        row.append(
            InlineKeyboardButton(ButtonText.FORWARD, callback_data=callback_builder(page + 1))
        )
    return row


def action_menu_keyboard(action_label: str, action: str) -> InlineKeyboardMarkup:
    """Две кнопки: повторить действие и вернуться в главное меню."""
    return _inline(
        [
            InlineKeyboardButton(action_label, callback_data=action),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ]
    )


def no_games_keyboard() -> InlineKeyboardMarkup:
    """Показывается, когда игр по выбранным критериям не найдено."""
    return action_menu_keyboard(ButtonText.OTHER_GENRES, CallbackAction.PICK_GENRES)


def retry_franchise_keyboard() -> InlineKeyboardMarkup:
    """Показывается, когда франшиза не найдена."""
    return action_menu_keyboard(ButtonText.OTHER_FRANCHISE, CallbackAction.FRANCHISE_INPUT)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Одна кнопка «В главное меню»."""
    return _inline(
        [InlineKeyboardButton(ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU)]
    )


def picking_genres_keyboard(
    genres: Sequence[Genre], selected_slugs: Sequence[str]
) -> InlineKeyboardMarkup:
    """Экран 3: выбор интересов (жанров) для подбора игр."""
    rows: List[Sequence[InlineKeyboardButton]] = []

    for left, right in _pairs(genres):
        row = [
            InlineKeyboardButton(
                _label(left.name, left.slug in selected_slugs),
                callback_data=genre_callback(left.slug),
            )
        ]
        if right is not None:
            row.append(
                InlineKeyboardButton(
                    _label(right.name, right.slug in selected_slugs),
                    callback_data=genre_callback(right.slug),
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.SHOW_SELECTION, callback_data=CallbackAction.PICK_SHOW
            ),
            InlineKeyboardButton(ButtonText.SHOW_ALL, callback_data=CallbackAction.PICK_ALL),
        ]
    )
    rows.append(
        [InlineKeyboardButton(ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU)]
    )
    return _inline(*rows)


def profile_genres_keyboard(
    genres: Sequence[Genre], selected_slugs: Sequence[str]
) -> InlineKeyboardMarkup:
    """Экран 9б: выбор интересов для анкеты."""
    rows: List[Sequence[InlineKeyboardButton]] = []

    for left, right in _pairs(genres):
        row = [
            InlineKeyboardButton(
                _label(left.name, left.slug in selected_slugs),
                callback_data=profile_genre_callback(left.slug),
            )
        ]
        if right is not None:
            row.append(
                InlineKeyboardButton(
                    _label(right.name, right.slug in selected_slugs),
                    callback_data=profile_genre_callback(right.slug),
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.SAVE, callback_data=CallbackAction.PROFILE_GENRES_DONE
            ),
            InlineKeyboardButton(ButtonText.BACK, callback_data=CallbackAction.PROFILE),
        ]
    )
    return _inline(*rows)


def platforms_keyboard(
    platforms: Sequence[Platform], selected_ids: Sequence[int], limit: int = 8
) -> InlineKeyboardMarkup:
    """Экран 9в: выбор платформ."""
    rows: List[Sequence[InlineKeyboardButton]] = []

    for left, right in _pairs(platforms[:limit]):
        row = [
            InlineKeyboardButton(
                _label(left.name, left.id in selected_ids),
                callback_data=platform_callback(left.id),
            )
        ]
        if right is not None:
            row.append(
                InlineKeyboardButton(
                    _label(right.name, right.id in selected_ids),
                    callback_data=platform_callback(right.id),
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.SAVE, callback_data=CallbackAction.PROFILE_PLATFORMS_DONE
            ),
            InlineKeyboardButton(ButtonText.BACK, callback_data=CallbackAction.PROFILE),
        ]
    )
    return _inline(*rows)


def games_keyboard(
    games: Sequence[Game],
    page: int,
    has_next: bool = False,
    has_previous: bool = False,
    back_action: str = CallbackAction.PICK_GENRES,
    back_label: str = ButtonText.OTHER_GENRES,
) -> InlineKeyboardMarkup:
    """Экран 4: выбор игры из подборки + пагинация."""
    rows: List[Sequence[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ButtonText.SELECT_GAME.format(index), callback_data=game_callback(game.id)
            )
        ]
        for index, game in enumerate(games, start=1)
    ]

    pagination: List[InlineKeyboardButton] = []
    if has_previous:
        pagination.append(
            InlineKeyboardButton(
                ButtonText.BACK, callback_data=games_page_callback(page - 1)
            )
        )
    if has_next:
        pagination.append(
            InlineKeyboardButton(
                ButtonText.FORWARD, callback_data=games_page_callback(page + 1)
            )
        )
    rows.append(pagination)
    rows.append([InlineKeyboardButton(back_label, callback_data=back_action)])
    rows.append(
        [InlineKeyboardButton(ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU)]
    )
    return _inline(*rows)


def franchise_games_keyboard(games: Sequence[Game]) -> InlineKeyboardMarkup:
    """Экран 8: игры выбранной франшизы."""
    rows: List[Sequence[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ButtonText.SELECT_GAME.format(index), callback_data=game_callback(game.id)
            )
        ]
        for index, game in enumerate(games, start=1)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                ButtonText.OTHER_FRANCHISE, callback_data=CallbackAction.FRANCHISE_INPUT
            ),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ]
    )
    return _inline(*rows)


def game_card_keyboard(game_id: int, is_favorite: bool = False) -> InlineKeyboardMarkup:
    """Экран 5: действия с игрой."""
    favorite_label = ButtonText.REMOVE_FAVORITE if is_favorite else ButtonText.ADD_FAVORITE
    return _inline(
        [
            InlineKeyboardButton(
                ButtonText.ADD_PLAYED, callback_data=add_played_callback(game_id)
            ),
            InlineKeyboardButton(favorite_label, callback_data=favorite_callback(game_id)),
        ],
        [
            InlineKeyboardButton(ButtonText.BACK, callback_data=CallbackAction.BACK_GAMES),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ],
    )


def franchises_keyboard(franchises: Sequence[Franchise]) -> InlineKeyboardMarkup:
    """Экран 7: выбор найденной франшизы."""
    rows: List[Sequence[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ButtonText.SELECT_FRANCHISE.format(index),
                callback_data=franchise_pick_callback(index),
            )
        ]
        for index in range(1, len(franchises) + 1)
    ]
    rows.append(
        [
            InlineKeyboardButton(ButtonText.BACK, callback_data=CallbackAction.FRANCHISE_INPUT),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ]
    )
    return _inline(*rows)


def profile_keyboard(has_age: bool = False, has_region: bool = False) -> InlineKeyboardMarkup:
    """Экран 9: разделы анкеты."""
    age_row: List[InlineKeyboardButton] = [
        InlineKeyboardButton(ButtonText.SET_AGE, callback_data=CallbackAction.PROFILE_AGE)
    ]
    if has_age:
        age_row.append(
            InlineKeyboardButton(
                ButtonText.RESET_AGE, callback_data=CallbackAction.PROFILE_AGE_RESET
            )
        )

    region_row: List[InlineKeyboardButton] = [
        InlineKeyboardButton(ButtonText.SET_REGION, callback_data=CallbackAction.PROFILE_IP)
    ]
    if has_region:
        region_row.append(
            InlineKeyboardButton(
                ButtonText.RESET_REGION, callback_data=CallbackAction.PROFILE_IP_RESET
            )
        )

    return _inline(
        age_row,
        [
            InlineKeyboardButton(
                ButtonText.SET_GENRES, callback_data=CallbackAction.PROFILE_GENRES
            ),
            InlineKeyboardButton(
                ButtonText.SET_PLATFORMS, callback_data=CallbackAction.PROFILE_PLATFORMS
            ),
        ],
        region_row,
        [
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            )
        ],
    )


def played_list_keyboard(
    records: Sequence[PlayedGame], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Экран 10: список сыгранных игр с пагинацией."""
    rows: List[Sequence[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ButtonText.SELECT_GAME.format(index), callback_data=record_callback(record.id)
            )
        ]
        for index, record in enumerate(records, start=1)
    ]

    rows.append(_pagination_row(page, total_pages, played_page_callback))
    rows.append(
        [InlineKeyboardButton(ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU)]
    )
    return _inline(*rows)


def played_info_keyboard(record_id: int, library_page: int = 1) -> InlineKeyboardMarkup:
    """Экран 11: информация о сыгранной игре."""
    return _inline(
        [
            InlineKeyboardButton(
                ButtonText.WRITE_REVIEW, callback_data=review_callback(record_id)
            ),
            InlineKeyboardButton(
                ButtonText.DELETE_PLAYED, callback_data=delete_played_callback(record_id)
            ),
        ],
        [
            InlineKeyboardButton(
                ButtonText.BACK, callback_data=played_page_callback(library_page)
            ),
            InlineKeyboardButton(
                ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU
            ),
        ],
    )


def favorites_keyboard(
    records: Sequence[FavoriteGame], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Экран 12: избранное с пагинацией."""
    rows: List[Sequence[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ButtonText.SELECT_GAME.format(index),
                callback_data=game_callback(record.game_id),
            )
        ]
        for index, record in enumerate(records, start=1)
    ]

    rows.append(_pagination_row(page, total_pages, favorites_page_callback))
    rows.append(
        [InlineKeyboardButton(ButtonText.BACK_TO_MENU, callback_data=CallbackAction.MAIN_MENU)]
    )
    return _inline(*rows)
