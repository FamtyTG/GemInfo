# 05. Архитектура проекта

## Принципы

1. **Трёхслойная архитектура.** Проект разделён на слои `presentation`,
   `domain` и `infrastructure`. Зависимости направлены только «внутрь»: слой
   представления использует домен, домен не знает ни о Telegram, ни о SQLAlchemy,
   ни о HTTP.
2. **Инверсия зависимостей.** Домен объявляет интерфейсы (`GamesProvider`,
   `IpLocationProvider`, `ProfileRepository`, `LibraryRepository`), а
   инфраструктура их реализует (`RawgClient`, `IpLocationClient`,
   `SqlProfileRepository`, `SqlLibraryRepository`). Благодаря этому бизнес-логику
   можно тестировать на подставных объектах без сети и базы данных.
3. **Один композиционный корень.** Класс `Application` (`gamehunter/app.py`)
   создаёт настройки, базу, клиенты, сервисы, экраны и обработчики и связывает их
   между собой. Никакой другой модуль не собирает зависимости «вручную».
4. **Ошибки — часть домена.** Любая проблема (сеть, база, некорректный ввод)
   превращается в исключение из `gamehunter/domain/exceptions.py` с готовым
   текстом `user_message`. Декоратор `safe_handler` отправляет этот текст
   пользователю и пишет подробности в лог, поэтому бот не «падает».
5. **Экраны не хранят состояние.** Текущий экран, выбранные жанры, страница и
   открытая игра хранятся в `StateStorage` (`UserContext`), а экраны лишь читают
   и обновляют контекст.
6. **Текст и кнопки — отдельно от логики.** Все сообщения живут в
   `presentation/texts.py`, все клавиатуры и callback-данные — в
   `presentation/keyboards.py`. Мокапы генерируются из этих же модулей, поэтому
   макеты всегда соответствуют коду.

## Схема слоёв

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION — «что видит пользователь»                                  │
│                                                                          │
│  handlers.py ── BotHandlers (команды, callback, текст, «мусор»)           │
│      │           декоратор safe_handler: ошибка → user_message + лог      │
│      ▼                                                                   │
│  screens/ ─── StartScreen, MainMenuScreen, GenrePickingScreen,           │
│      │        GameListScreen, GameCardScreen, FranchiseInputScreen,      │
│      │        FranchiseListScreen, FranchiseGamesScreen, ProfileScreen,  │
│      │        AgeInputScreen, ProfileGenresScreen, ProfilePlatformsScreen│
│      │        RegionInputScreen, PlayedListScreen, PlayedInfoScreen,     │
│      │        ReviewInputScreen, FavoritesScreen   (все ← BaseScreen)    │
│      │                                                                   │
│      ├── texts.py      (тексты сообщений и форматирование)               │
│      ├── keyboards.py  (reply/inline-клавиатуры, CallbackAction)         │
│      ├── state.py      (ContextScreen, UserContext, StateStorage)        │
│      └── gateway.py    (TelegramGateway: send_text / send_photo /        │
│                         answer_callback, ошибки Telegram не роняют бота)  │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ вызывает сервисы
┌───────────────────────────────▼──────────────────────────────────────────┐
│  DOMAIN — «правила предметной области» (без Telegram, SQL и HTTP)         │
│                                                                          │
│  services/GameService     — подбор игр: жанры, платформы, возраст,        │
│                             исключение сыгранных, карточки, франшизы, кэш │
│  services/ProfileService  — анкета: возраст, интересы, платформы,         │
│                             регион по IP, проверка IP-адреса              │
│  services/LibraryService  — «во что я играл», отзывы, избранное           │
│                                                                          │
│  entities.py     — Game, GameDetails, GamePage, GameQuery, Genre,         │
│                    Platform, Franchise, Region, UserProfile, PlayedGame,  │
│                    FavoriteGame, LibraryPage                              │
│  age_ratings.py  — AgePolicy: ESRB/PEGI → минимальный возраст             │
│  exceptions.py   — GameHunterError и 20+ наследников с user_message       │
│  interfaces.py   — GamesProvider, IpLocationProvider,                     │
│                    ProfileRepository, LibraryRepository (ABC)             │
└───────────────┬──────────────────────────────────────┬───────────────────┘
                │ реализация интерфейсов                │
┌───────────────▼────────────────────┐  ┌──────────────▼───────────────────┐
│  INFRASTRUCTURE / API              │  │  INFRASTRUCTURE / DB             │
│                                    │  │                                  │
│  http_client.py — JsonHttpClient   │  │  database.py — Database          │
│    (requests, таймаут, 4xx/5xx,    │  │    (engine, session_scope,       │
│     JSON, allow_404)               │  │     create_all, safe_url)        │
│  rawg_client.py — RawgClient       │  │  models.py — UserProfileORM,     │
│    (жанры, платформы, игры,        │  │    PlayedGameORM,                │
│     карточки, франшизы, кэш)       │  │    FavoriteGameORM (SQLAlchemy   │
│  ip_location_client.py —           │  │    2.0, Mapped/mapped_column)    │
│    IpLocationClient (ipapi.co /    │  │  repositories.py —               │
│    ipwho.is)                       │  │    SqlProfileRepository,         │
│                                    │  │    SqlLibraryRepository          │
└────────────────────────────────────┘  └──────────────────────────────────┘

Сквозные модули: config.py (Settings) и app.py (Application, configure_logging)
```

Диаграмма в формате DrawIO: [diagrams/architecture.drawio](diagrams/architecture.drawio).

## Состав слоёв

### Слой 1. Presentation — «что видит пользователь»

| Модуль | Классы и функции | Ответственность |
|--------|------------------|-----------------|
| `handlers.py` | `BotHandlers`, `safe_handler`, `UNSUPPORTED_CONTENT_TYPES` | регистрация обработчиков telebot, разбор callback-данных (28 маршрутов), маршрутизация текста по текущему экрану, перехват всех ошибок |
| `screens/base.py` | `BaseScreen` | общий предок экранов: `send`, `context`, `save`, `show_error`, `state_lost`, логирование экрана |
| `screens/menu.py` | `StartScreen`, `MainMenuScreen` | Экраны 1–2 |
| `screens/picking.py` | `GenrePickingScreen`, `GameListScreen`, `GameCardScreen` | Экраны 3–5 |
| `screens/franchise.py` | `FranchiseInputScreen`, `FranchiseListScreen`, `FranchiseGamesScreen` | Экраны 6–8 |
| `screens/profile.py` | `ProfileScreen`, `AgeInputScreen`, `ProfileGenresScreen`, `ProfilePlatformsScreen`, `RegionInputScreen` | Экраны 9, 9а–9г |
| `screens/library.py` | `PlayedListScreen`, `PlayedInfoScreen`, `ReviewInputScreen`, `FavoritesScreen` | Экраны 10–12 |
| `screens/__init__.py` | `ScreenContainer`, `build_screens` | контейнер из 17 экранов и их связывание (взаимные переходы) |
| `texts.py` | константы и `format_*` | все тексты бота и форматирование списков, карточек, анкеты |
| `keyboards.py` | `ButtonText`, `CallbackAction`, `Callback`, `parse_callback`, `*_keyboard()` | подписи кнопок, схема callback-данных, сборка клавиатур |
| `state.py` | `ContextScreen`, `UserContext`, `StateStorage` | состояние диалога пользователя и переходы между экранами |
| `gateway.py` | `TelegramGateway` | единственная точка общения с Telegram API: текст, фото, ответ на callback |

### Слой 2. Domain — «правила предметной области»

| Модуль | Классы | Ответственность |
|--------|--------|-----------------|
| `services/game_service.py` | `GameService` | справочники жанров и платформ с кэшем, построение `GameQuery`, слияние с анкетой, поиск игр с учётом возраста и сыгранных игр, карточка игры, поиск франшиз и их игр |
| `services/profile_service.py` | `ProfileService` | чтение и изменение анкеты, валидация возраста, проверка IP-адреса (`validate_ip`, `extract_ip`), определение региона через `IpLocationProvider` |
| `services/library_service.py` | `LibraryService` | сыгранные игры, отзывы (проверка длины), удаление записей, избранное (`toggle_favorite`), пагинация |
| `entities.py` | 12 dataclass'ов | неизменяемые объекты предметной области и их представление (`formatted_rating`, `interests_text`, `total_pages` и др.) |
| `age_ratings.py` | `AgePolicy` | соответствие ESRB/PEGI минимальному возрасту, `is_allowed(details, age)` |
| `exceptions.py` | `GameHunterError` и 20 наследников | типы ошибок и тексты для пользователя |
| `interfaces.py` | 4 ABC | контракты для инфраструктуры |

### Слой 3. Infrastructure — «как данные приходят и хранятся»

| Модуль | Классы | Ответственность |
|--------|--------|-----------------|
| `api/http_client.py` | `JsonHttpClient` | HTTP-запросы через `requests`: таймаут, коды ответа, разбор JSON, `allow_404`, преобразование ошибок в `ExternalServiceError` |
| `api/rawg_client.py` | `RawgClient` | каталог RAWG: `/genres`, `/platforms/lists/parents`, `/games`, `/games/{id}`, `/franchises`, `/franchises/{id}`; разбор ответов, запасной список платформ |
| `api/ip_location_client.py` | `IpLocationClient` | геолокация по IP (`ipapi.co`, при необходимости `ipwho.is`), защита от локальных адресов, преобразование в `Region` |
| `db/database.py` | `Database` | движок SQLAlchemy, `session_scope()` (commit/rollback), `create_all()`, `safe_url` |
| `db/models.py` | `UserProfileORM`, `PlayedGameORM`, `FavoriteGameORM` | ORM-модели 2.0-стиля, ограничения уникальности и индексы |
| `db/repositories.py` | `SqlProfileRepository`, `SqlLibraryRepository` | реализация интерфейсов репозиториев, преобразование ORM ↔ доменные сущности, `SQLAlchemyError` → `DatabaseError` |

### Сквозные модули

| Модуль | Ответственность |
|--------|-----------------|
| `config.py` | `Settings` (frozen dataclass) и `Settings.from_env()`: чтение `.env` и переменных окружения, проверка обязательных значений (`BOT_TOKEN`, `DATABASE_URL`), приведение типов |
| `app.py` | `configure_logging`, `Application` (композиционный корень), `build_application`, `main` (запуск polling'а и корректная остановка) |
| `run.py` | точка входа: `python run.py` |

## Поток данных на примере «Показать подборку игр»

Пользователь отметил жанры на Экране 3 и нажал «Показать подборку»
(callback `pick_show`).

| Шаг | Модуль | Что происходит |
|-----|--------|----------------|
| 1 | `handlers.BotHandlers.on_callback` | telebot передаёт `CallbackQuery`; декоратор `safe_handler` включает перехват ошибок |
| 2 | `keyboards.parse_callback` | строка `pick_show` разбирается в `Callback(action="pick_show", value=None)` |
| 3 | `gateway.answer_callback` | Telegram получает ответ на callback (убирает «часики» на кнопке) |
| 4 | `handlers._callback_routes` | действие `pick_show` → метод `GameListScreen.show(chat_id, user_id, page=1)` |
| 5 | `state.StateStorage` | экран читает `UserContext`: отмеченные жанры, каталог жанров |
| 6 | `ProfileService.get_profile` | анкета пользователя из `user_profiles` (через `SqlProfileRepository`) |
| 7 | `LibraryService.played_game_ids` | множество идентификаторов сыгранных игр из `played_games` |
| 8 | `GameService.build_query` + `merge_with_profile` | собирается `GameQuery`: жанры, платформы из анкеты, `exclude_game_ids`, `ordering=-rating`, `page_size` |
| 9 | `GameService.find_games` | запрос к каталогу через `RawgClient.search_games` → `JsonHttpClient.get_json` → `GET https://api.rawg.io/api/games?key=…&genres=…&exclude_games=…` |
| 10 | `GameService._filter_by_age` | для части игр догружаются карточки (`RawgClient.fetch_game_details`), `AgePolicy.is_allowed` отбрасывает игры не по возрасту |
| 11 | `GameService` | результат — `GamePage(games, page, total_pages, has_next, has_previous)` |
| 12 | `texts.format_games` | текст Экрана 4: заголовок, фильтры, пометка об исключённых играх, страница, список игр |
| 13 | `keyboards.games_keyboard` | inline-кнопки «Выбрать игру N», пагинация, «Другие жанры», «В главное меню» |
| 14 | `state.StateStorage.save` | контекст обновляется: `screen=GAME_LIST`, сохранены игры, страница, строка фильтров |
| 15 | `gateway.send_text` | сообщение отправляется в Telegram; ошибка API логируется и не роняет бота |

Если на шаге 9 каталог недоступен, `RawgClient` бросает `GamesUnavailableError`;
на шаге 10, если подходящих игр не осталось, — `NoGamesFoundError`. Оба
исключения перехватывает `safe_handler`, и пользователь видит понятный текст
вместо трассировки.

## Дерево проекта

```
GemInfo/
├── run.py                       # точка входа: python run.py
├── gamehunter/
│   ├── __init__.py              # версия и имя проекта
│   ├── app.py                   # Application, configure_logging, main
│   ├── config.py                # Settings (чтение .env)
│   ├── domain/
│   │   ├── age_ratings.py
│   │   ├── entities.py
│   │   ├── exceptions.py
│   │   ├── interfaces.py
│   │   └── services/
│   │       ├── game_service.py
│   │       ├── library_service.py
│   │       └── profile_service.py
│   ├── infrastructure/
│   │   ├── api/
│   │   │   ├── http_client.py
│   │   │   ├── ip_location_client.py
│   │   │   └── rawg_client.py
│   │   └── db/
│   │       ├── database.py
│   │       ├── models.py
│   │       └── repositories.py
│   └── presentation/
│       ├── gateway.py
│       ├── handlers.py
│       ├── keyboards.py
│       ├── state.py
│       ├── texts.py
│       └── screens/
│           ├── __init__.py      # ScreenContainer, build_screens
│           ├── base.py
│           ├── franchise.py
│           ├── library.py
│           ├── menu.py
│           ├── picking.py
│           └── profile.py
├── scripts/
│   ├── init_db.py               # создание таблиц и демо-данных
│   └── generate_mockups.py      # генерация SVG-мокапов
├── tests/                       # 1409 тестов: юнит + интеграционные + сквозные
│   ├── conftest.py              # фикстуры: база SQLite, сервисы, экраны, бот
│   ├── fakes.py                 # подставные провайдеры, шлюз, фабрики сущностей
│   └── test_*.py                # 20 модулей тестов
├── docs/                        # 9 документов, диаграммы DrawIO, мокапы SVG
├── .env.example                 # шаблон настроек (ключи — только из окружения)
├── docker-compose.yml           # PostgreSQL 16 + Adminer
├── Makefile                     # install, init-db, run, test, mockups, lint
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## Почему выбраны такие решения

| Решение | Обоснование |
|---------|-------------|
| Три слоя вместо «всё в одном файле» | бизнес-правила (возрастной фильтр, исключение сыгранных игр) можно проверить без Telegram и без сети; замена API или базы не затрагивает логику |
| Интерфейсы провайдеров и репозиториев | в тестах используются `FakeGamesProvider`, `FakeIpProvider` и SQLite — тесты работают за секунды и не зависят от внешних сервисов |
| Состояние диалога в `StateStorage`, а не в `register_next_step_handler` | состояние явно, его можно проверить в тестах, оно не «протекает» между экранами и корректно сбрасывается по `/start` |
| Callback-данные вида `game:32` | компактно (лимит Telegram 64 байта), читаемо в логах, легко разбирается `parse_callback` |
| Отдельный `TelegramGateway` | экраны не знают про telebot: их можно тестировать на `FakeGateway`, а ошибки Telegram API логируются в одном месте |
| Тексты и клавиатуры в отдельных модулях | правка формулировок не затрагивает логику; мокапы собираются из тех же констант |
| Кэш справочников и карточек в `GameService` | жанры, платформы и карточки игр меняются редко, а лимиты RAWG ограничены; TTL задаётся настройкой `CACHE_TTL_SECONDS` |
| `Settings` как frozen dataclass | настройки неизменяемы, валидируются в одном месте, легко подменяются в тестах |
| Список жанров/платформ строкой в анкете | значения справочные и не требуют отдельных таблиц связей; схема остаётся из трёх таблиц |
| Возрастной фильтр по карточкам игр | список `GET /games` не содержит возрастной рейтинг, поэтому бот догружает ограниченное число карточек (`DETAILS_FETCH_LIMIT`) и фильтрует по ним |
