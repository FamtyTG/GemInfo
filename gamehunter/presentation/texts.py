"""Тексты сообщений и правила их форматирования.

Все пользовательские строки собраны в одном модуле: так удобно менять
формулировки, не трогая логику экранов.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from gamehunter.domain.entities import (
    FavoriteGame,
    Franchise,
    Game,
    GameDetails,
    GamePage,
    Genre,
    LibraryPage,
    PlayedGame,
    UserProfile,
)

BOT_NAME = "GameHunter"

# ---------------------------------------------------------------------- #
# Экран 1. Старт
# ---------------------------------------------------------------------- #
START_WELCOME = (
    f"Добро пожаловать в {BOT_NAME}\n"
    "Чат-бот, который помогает подобрать видеоигру по интересам, жанрам, "
    "возрасту и франшизе (IP).\n"
    "/start — переведёт Вас в главное меню, где бы Вы ни находились."
)

# ---------------------------------------------------------------------- #
# Экран 2. Главное меню
# ---------------------------------------------------------------------- #
MAIN_MENU_WELCOME = f"Добро пожаловать в {BOT_NAME}\nВыберите кнопку из главного меню."

UNKNOWN_COMMAND = (
    "Нераспознанная команда. Пожалуйста, нажмите выбранную кнопку в меню."
)

# ---------------------------------------------------------------------- #
# Экран 3. Подбор игр — интересы (жанры)
# ---------------------------------------------------------------------- #
GENRES_TITLE = "Какие жанры Вам интересны?\nМожно выбрать несколько вариантов."
GENRES_FOOTER = (
    "Когда закончите выбор — нажмите «Показать подборку».\n"
    "Чтобы подобрать игры без фильтра по жанру — «Показать всё»."
)
GENRES_SELECTED_COUNT = "Выбрано жанров: {}"
GENRES_SELECTED_LINE = "Выбрано: {}"
GENRES_NO_SELECTION = (
    "Вы не выбрали ни одного жанра.\n"
    "Нажмите «Показать всё» или отметьте жанры ещё раз."
)

# ---------------------------------------------------------------------- #
# Экран 4. Список игр (результаты подбора)
# ---------------------------------------------------------------------- #
GAMES_TITLE = "Подборка игр для Вас:"
GAMES_SEARCH_TITLE = "Найденные игры:"
GAMES_FOOTER = "Выберите игру, чтобы посмотреть карточку."
GAMES_FILTERS_LINE = "Фильтры: {}"
GAMES_NO_FILTERS = "без фильтров (по рейтингу)"
GAMES_PLAYED_EXCLUDED = "Игры, в которые Вы уже играли, исключены из подборки."

# ---------------------------------------------------------------------- #
# Экран 5. Карточка игры
# ---------------------------------------------------------------------- #
GAME_CARD_TITLE = "Карточка игры:"
GAME_STATUS_PLAYED = "Вы уже играли в эту игру."
GAME_STATUS_FAVORITE = "Игра в избранном."
GAME_REGION_LINE = "Ваш регион: {}"

GAME_ADDED_TO_PLAYED = "Игра добавлена в список «Во что я играл»."
GAME_ALREADY_PLAYED = "Эта игра уже есть в Вашем списке «Во что я играл»."
GAME_ADDED_TO_FAVORITES = "Игра добавлена в избранное."
GAME_REMOVED_FROM_FAVORITES = "Игра убрана из избранного."

# ---------------------------------------------------------------------- #
# Экраны 6–8. Поиск игр по франшизе (IP)
# ---------------------------------------------------------------------- #
FRANCHISE_INPUT_PROMPT = (
    "Введите название франшизы (IP), по которой нужно найти игры.\n"
    "Например: Marvel, Star Wars, Warcraft, Assassin's Creed."
)
FRANCHISE_EMPTY_NAME = "Введите название франшизы, например: Marvel."
FRANCHISES_TITLE = "Найденные франшизы:"
FRANCHISES_FOOTER = "Выберите франшизу, чтобы посмотреть её игры."
FRANCHISE_GAMES_TITLE = "Игры франшизы {}:"

# ---------------------------------------------------------------------- #
# Экран 9. Моя анкета
# ---------------------------------------------------------------------- #
PROFILE_TITLE = "Моя анкета:"
PROFILE_FOOTER = (
    "Анкета используется при подборе игр:\n"
    "• возраст — чтобы не показывать игры не по возрасту;\n"
    "• интересы и платформы — чтобы предлагать подходящие игры;\n"
    "• регион — чтобы показывать доступные магазины и валюту."
)
PROFILE_AGE_PROMPT = "Введите Ваш возраст (число от 3 до 120)."
PROFILE_AGE_SAVED = "Возраст сохранён в анкете."
PROFILE_AGE_RESET = "Возраст убран из анкеты — игры подбираются без возрастного фильтра."
PROFILE_IP_PROMPT = (
    "Пришлите Ваш публичный IP-адрес — по нему бот определит страну, город,\n"
    "часовой пояс и валюту.\n"
    "Узнать свой IP-адрес можно на сайте 2ip.ru. Пример: 8.8.8.8"
)
PROFILE_REGION_SAVED = "Регион определён и сохранён в анкете."
PROFILE_REGION_RESET = "Регион удалён из анкеты."
PROFILE_GENRES_SAVED = "Интересы сохранены в анкете."
PROFILE_PLATFORMS_SAVED = "Платформы сохранены в анкете."
PROFILE_GENRES_TITLE = "Выберите жанры для своей анкеты (можно несколько):"
PROFILE_GENRES_SAVED_HINT = (
    "Отмеченные жанры будут использоваться при подборе игр.\n"
    "Когда закончите — нажмите «Сохранить»."
)
PROFILE_PLATFORMS_TITLE = "Выберите платформы, на которых Вы играете:"
PROFILE_PLATFORMS_SELECTED = "Выбрано платформ: {}"
PROFILE_PLATFORMS_NONE = "Платформы не выбраны — подборка будет без фильтра по платформам."

# ---------------------------------------------------------------------- #
# Экраны 10–12. «Во что я играл», отзыв, избранное
# ---------------------------------------------------------------------- #
PLAYED_TITLE = "Во что я уже играл:"
PLAYED_EMPTY = (
    "Список пока пуст.\n"
    "Откройте карточку любой игры и нажмите «Уже играл»."
)
PLAYED_FOOTER = "Выберите игру, чтобы посмотреть информацию и отзыв."
PLAYED_REMOVED = "Игра «{}» удалена из списка «Во что я играл»."

PLAYED_INFO_TITLE = "Информация об игре:"
REVIEW_ABSENT = "Отзыв об игре отсутствует."
REVIEW_PROMPT = "Введите текст отзыва об игре (не более 1000 символов)."
REVIEW_SAVED = "Отзыв успешно сохранён."

FAVORITES_TITLE = "Избранное:"
FAVORITES_EMPTY = (
    "В избранном пока пусто.\n"
    "Откройте карточку игры и нажмите «В избранное»."
)
FAVORITES_FOOTER = "Выберите игру, чтобы открыть её карточку."

# ---------------------------------------------------------------------- #
# Общие сообщения
# ---------------------------------------------------------------------- #
GENERIC_ERROR = "Произошла ошибка. Попробуйте ещё раз позже."
STATE_LOST = (
    "Данные предыдущего шага не сохранились. "
    "Вернитесь в главное меню и начните заново."
)


# ---------------------------------------------------------------------- #
# Функции форматирования
# ---------------------------------------------------------------------- #
def format_game_line(index: int, game: Game) -> str:
    """Одна строка в списке игр."""
    parts = [game.release_year, f"рейтинг {game.formatted_rating}"]
    if game.genres:
        parts.append(game.genres[0])
    return f"{index}. {game.name}\n   {' · '.join(parts)}"


def format_filters(genre_names: Sequence[str], platform_names: Sequence[str], age: Optional[int]) -> str:
    """Строка с применёнными фильтрами подбора."""
    parts: List[str] = []
    if genre_names:
        parts.append(f"жанры: {', '.join(genre_names)}")
    if platform_names:
        parts.append(f"платформы: {', '.join(platform_names)}")
    if age is not None:
        parts.append(f"возраст: {age}")
    return "; ".join(parts) if parts else GAMES_NO_FILTERS


def format_games_list(
    games: Sequence[Game],
    page: int,
    total_pages: int,
    filters_line: str,
    played_excluded: bool = False,
    title: str = GAMES_TITLE,
) -> str:
    """Список игр со страницей и применёнными фильтрами."""
    lines: List[str] = [title, "", GAMES_FILTERS_LINE.format(filters_line)]
    if total_pages > 1:
        lines.append(f"Страница {page} из {total_pages}")
    if played_excluded:
        lines.append(GAMES_PLAYED_EXCLUDED)
    lines.append("")

    for index, game in enumerate(games, start=1):
        lines.append(format_game_line(index, game))

    lines.append("")
    lines.append(GAMES_FOOTER)
    return "\n".join(lines)


def format_games(
    page: GamePage,
    filters_line: str,
    played_excluded: bool = False,
    title: str = GAMES_TITLE,
) -> str:
    """Список игр для Экрана 4 (результаты поиска в каталоге)."""
    return format_games_list(
        page.games,
        page.page,
        page.total_pages,
        filters_line,
        played_excluded=played_excluded,
        title=title,
    )


def format_game_list(games: Sequence[Game], title: str) -> str:
    """Простой список игр без пагинации (игры франшизы, избранное)."""
    lines: List[str] = [title, ""]
    for index, game in enumerate(games, start=1):
        lines.append(format_game_line(index, game))
    lines.append("")
    lines.append(GAMES_FOOTER)
    return "\n".join(lines)


def format_game_card(
    details: GameDetails,
    profile: Optional[UserProfile] = None,
    is_played: bool = False,
    is_favorite: bool = False,
) -> str:
    """Карточка игры для Экрана 5."""
    game = details.game
    lines: List[str] = [GAME_CARD_TITLE, "", f"Название: {game.name}"]

    lines.append(f"Выход: {game.formatted_released}")
    rating_line = f"Рейтинг: {game.formatted_rating}"
    if game.metacritic:
        rating_line += f" · Metacritic {game.metacritic}"
    lines.append(rating_line)
    lines.append(f"Жанры: {game.genres_text}")
    lines.append(f"Платформы: {game.platforms_text}")
    lines.append(f"Возрастной рейтинг: {details.formatted_age}")

    if details.developers:
        lines.append(f"Разработчик: {', '.join(details.developers)}")
    if details.publishers:
        lines.append(f"Издатель: {', '.join(details.publishers)}")
    if game.playtime_hours:
        lines.append(f"Среднее время прохождения: {game.playtime_hours} ч.")
    if details.stores:
        lines.append(f"Магазины: {', '.join(details.stores)}")
    if details.tags:
        lines.append(f"Метки: {', '.join(details.tags)}")

    if profile is not None and profile.region is not None and profile.region.is_known:
        region = profile.region
        currency = f", валюта {region.currency}" if region.currency else ""
        lines.append(GAME_REGION_LINE.format(f"{region.title}{currency}"))

    lines.append("")
    if is_played:
        lines.append(f"✔ {GAME_STATUS_PLAYED}")
    if is_favorite:
        lines.append(f"★ {GAME_STATUS_FAVORITE}")
    if is_played or is_favorite:
        lines.append("")

    if details.summary:
        lines.append(details.summary)

    return "\n".join(lines)


def format_franchises(franchises: Sequence[Franchise]) -> str:
    """Список найденных франшиз (IP)."""
    lines: List[str] = [FRANCHISES_TITLE, ""]
    for index, franchise in enumerate(franchises, start=1):
        lines.append(f"{index}. {franchise.name}")
        lines.append(f"   игр в каталоге: {franchise.games_count}")
    lines.append("")
    lines.append(FRANCHISES_FOOTER)
    return "\n".join(lines)


def format_profile(profile: UserProfile) -> str:
    """Анкета пользователя для Экрана 9."""
    age = f"{profile.age} лет" if profile.age is not None else "не указан"

    lines: List[str] = [PROFILE_TITLE, "", f"Возраст: {age}"]
    lines.append(f"Интересы (жанры): {profile.interests_text}")
    lines.append(f"Платформы: {profile.platforms_text}")

    region = profile.region
    if region is not None and region.is_known:
        region_lines = [f"Регион: {region.title}"]
        if region.country_code:
            region_lines.append(f"   страна: {region.country_code}")
        if region.timezone:
            region_lines.append(f"   часовой пояс: {region.timezone}")
        if region.currency:
            region_lines.append(f"   валюта: {region.currency}")
        if region.ip:
            region_lines.append(f"   определён по IP: {region.ip}")
        lines.extend(region_lines)
    else:
        lines.append("Регион: не определён")

    lines.append("")
    lines.append(PROFILE_FOOTER)
    return "\n".join(lines)


def format_genres_selection(
    genres: Sequence[Genre], selected_slugs: Sequence[str], title: str, footer: str
) -> str:
    """Текст экрана выбора жанров (интересов)."""
    lines: List[str] = [title, ""]
    for genre in genres:
        mark = "✔ " if genre.slug in selected_slugs else ""
        lines.append(f"{mark}{genre.name}")
    lines.append("")
    if selected_slugs:
        names = [genre.name for genre in genres if genre.slug in selected_slugs]
        lines.append(GENRES_SELECTED_LINE.format(", ".join(names)))
    lines.append(footer)
    return "\n".join(lines)


def format_played_history(page: LibraryPage[PlayedGame]) -> str:
    """Список сыгранных игр для Экрана 10."""
    if page.is_empty:
        return PLAYED_EMPTY

    lines: List[str] = [PLAYED_TITLE]
    if page.total_pages > 1:
        lines.append(f"Страница {page.page} из {page.total_pages}")
    lines.append("")

    for index, record in enumerate(page.items, start=1):
        lines.append(f"{index}. {record.formatted_date} — {record.name}")

    lines.append("")
    lines.append(PLAYED_FOOTER)
    return "\n".join(lines)


def format_played_info(record: PlayedGame) -> str:
    """Информация о сыгранной игре для Экрана 11."""
    review = record.review.strip() if record.has_review else ""
    return "\n".join(
        [
            PLAYED_INFO_TITLE,
            "",
            f"Дата добавления: {record.formatted_date}",
            f"Игра: {record.name}",
            f"Отзыв: {review}" if review else REVIEW_ABSENT,
        ]
    )


def format_favorites(page: LibraryPage[FavoriteGame]) -> str:
    """Список избранных игр для Экрана 12."""
    if page.is_empty:
        return FAVORITES_EMPTY

    lines: List[str] = [FAVORITES_TITLE]
    if page.total_pages > 1:
        lines.append(f"Страница {page.page} из {page.total_pages}")
    lines.append("")

    for index, record in enumerate(page.items, start=1):
        lines.append(f"{index}. {record.name}")
        lines.append(f"   добавлена: {record.formatted_date}")

    lines.append("")
    lines.append(FAVORITES_FOOTER)
    return "\n".join(lines)
