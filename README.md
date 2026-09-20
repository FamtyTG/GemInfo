# GameHunter — Telegram-бот для поиска видеоигр по интересам

Учебный проект: чат-бот на **Python + pyTelegramBotAPI (telebot)**, который
подбирает видеоигры по интересам, жанрам, возрасту и франшизе (IP), определяет
регион пользователя по IP-адресу и запоминает, во что он уже играл.
Данные хранятся в **PostgreSQL** через **SQLAlchemy 2.0**, каталог игр берётся из
**RAWG Video Games Database**. Код написан в ООП-стиле и разделён на три слоя:
`presentation` → `domain` ← `infrastructure`.

---

## 1. Идея проекта

GameHunter помогает ответить на вопрос «во что бы поиграть?» и не предлагает то,
что пользователь уже прошёл.

| # | Возможность | Где в боте |
|---|-------------|------------|
| 1 | Выбрать интересы (жанры) и получить подборку игр | Экраны 3–4 |
| 2 | Открыть карточку игры: обложка, рейтинг, жанры, платформы, возрастной рейтинг, описание, магазины | Экран 5 |
| 3 | Найти игры по франшизе (IP): Marvel, Star Wars, Warcraft | Экраны 6–8 |
| 4 | Заполнить анкету: возраст, интересы, платформы | Экраны 9, 9б, 9в |
| 5 | Определить регион по IP-адресу: город, страна, часовой пояс, валюта | Экран 9г |
| 6 | Отметить игру как сыгранную — она исключается из следующих подборок | Экран 5 → 10 |
| 7 | Оставить отзыв о сыгранной игре (до 1000 символов) | Экран 11а |
| 8 | Просмотреть список «Во что я играл» с пагинацией | Экран 10 |
| 9 | Сохранять игры в избранное и просматривать его | Экран 12 |

Как это работает:

* **Интересы** — пользователь отмечает жанры (Action, RPG, Shooter…), бот
  запрашивает каталог с фильтром `genres` и сортировкой по рейтингу.
* **Анкета** — возраст, платформы и интересы из анкеты применяются как фильтры
  по умолчанию: бот не предлагает игры «18+» подростку и не показывает игры для
  консоли, которой у пользователя нет.
* **Возрастной рейтинг** — ESRB и PEGI переводятся в минимальный возраст
  (`AgePolicy`): EC → 3, E → 6, E10+ → 10, T → 13, M → 17, AO → 18.
* **Франшиза (IP)** — поиск по вселенной: `GET /franchises?search=Marvel`, затем
  список игр выбранной франшизы.
* **Регион по IP** — Telegram Bot API не передаёт IP пользователя, поэтому бот
  просит прислать публичный адрес (его видно на 2ip.ru) и определяет по нему
  город, страну, часовой пояс и валюту.
* **«Во что я играл»** — отмеченные игры передаются в параметр `exclude_games`,
  поэтому подборка каждый раз предлагает новое.

---

## 2. Быстрый старт

### 2.1. Требования

* Python **3.10+** (разработка велась на 3.11, проверено также на 3.14)
* Git
* PostgreSQL 14+ (или Docker — в проекте есть `docker-compose.yml`)
* Telegram-бот (токен от [@BotFather](https://t.me/BotFather))
* ключ [RAWG API](https://rawg.io/apidocs) (бесплатный)
* доступ к `api.telegram.org` (при блокировках — VPN или прокси, см. `PROXY_URL`)

### 2.2. Установка

```bash
git clone <адрес-репозитория> GemInfo
cd GemInfo

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt         # telebot, requests, SQLAlchemy, psycopg2, dotenv
pip install -r requirements-dev.txt     # + pytest
```

### 2.3. Настройка `.env`

```bash
cp .env.example .env
```

Обязательные значения:

```dotenv
BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/gamehunter
RAWG_API_KEY=ваш_ключ_RAWG
```

Необязательные (значения по умолчанию уже прописаны в `.env.example`):

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `IP_LOCATION_BASE_URL` | `https://ipapi.co` | сервис геолокации (поддерживается и `https://ipwho.is`) |
| `CATALOG_LANGUAGE` | `ru` | язык названий и описаний игр |
| `MAX_GAMES` | `5` | игр на странице подборки |
| `MAX_GENRES` | `12` | сколько жанров показывать на выбор |
| `MAX_FRANCHISES` | `5` | сколько франшиз показывать в результатах поиска |
| `DETAILS_FETCH_LIMIT` | `8` | сколько карточек догружать для проверки возраста |
| `LIBRARY_PAGE_SIZE` | `5` | записей на странице «Во что я играл» и «Избранное» |
| `REVIEW_MAX_LENGTH` | `1000` | максимальная длина отзыва |
| `DEFAULT_ORDERING` | `-rating` | сортировка подборки (`-rating`, `-released`) |
| `PROXY_URL` | — (пусто) | прокси для Telegram API и внешних сервисов, например `socks5://127.0.0.1:1080` (нужен `PySocks`) |
| `HTTP_TIMEOUT` | `10` | таймаут запросов к внешним API, секунд |
| `CACHE_TTL_SECONDS` | `600` | время жизни кэша справочников и карточек |
| `LOG_LEVEL` | `INFO` | уровень логирования |

**Секреты в Git не попадают:** файл `.env` добавлен в `.gitignore`, в репозитории
лежит только шаблон `.env.example`. Строка подключения к базе логируется без
пароля (`Database.safe_url`).

### 2.4. Создание таблиц и запуск

База данных в Docker (PostgreSQL 16 + Adminer для просмотра таблиц) — команды
выполняются **из папки проекта**, где лежит `docker-compose.yml`:

```bash
cd GemInfo
docker compose up -d          # postgres:5432, adminer: http://localhost:8080
docker compose ps             # статус контейнеров
```

В Adminer входите так: сервер **postgres**, пользователь `postgres`, пароль
`postgres`, база `gamehunter`.

Создание таблиц, демо-данные и запуск бота:

```bash
python -m scripts.init_db          # таблицы user_profiles, played_games, favorite_games
python -m scripts.init_db --demo   # + демо-анкета, 3 сыгранные игры, 2 избранные
python run.py                      # запуск бота (long polling)
```

или через Makefile:

```bash
make init-db && make run
make demo        # то же + демонстрационные данные
```

Остановка бота — `Ctrl+C`: опрос Telegram завершается корректно, соединения с
базой закрываются.

Без PostgreSQL можно запустить бота на SQLite (только для разработки):

```dotenv
DATABASE_URL=sqlite:///gamehunter.db
```

### 2.5. Если Telegram API недоступен

Если при запуске вы видите `ConnectTimeout` к `api.telegram.org` (частая
ситуация при блокировках в сети), бот напечатает `[ОШИБКА СЕТИ]` и завершится.
Решение — VPN на компьютере либо прокси в `.env`:

```dotenv
PROXY_URL=socks5://127.0.0.1:1080
```

Через этот прокси пойдут и запросы к Telegram, и обращения к RAWG / сервису
геолокации. Для `socks5://` требуется `PySocks` (уже в `requirements.txt`).
Учётные данные прокси в логи не попадают — печатается `socks5://***@host:port`.
Перед стартом опроса бот делает `getMe` и сообщает понятным текстом о неверном
токене (401) или о втором запущенном экземпляре (409).

---

## 3. Архитектура проекта

Три слоя, зависимости направлены только «внутрь»:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION — что видит пользователь                                    │
│   handlers.py   BotHandlers: /start, callback (28 маршрутов), текст,      │
│                 «мусор»; декоратор safe_handler (ошибка → user_message)   │
│   screens/      17 экранов: menu, picking, franchise, profile, library    │
│   texts.py      все сообщения бота и форматирование                       │
│   keyboards.py  reply/inline-клавиатуры и схема callback-данных           │
│   state.py      ContextScreen, UserContext, StateStorage                  │
│   gateway.py    TelegramGateway: текст, фото, ответ на callback           │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DOMAIN — правила предметной области (без Telegram, SQL и HTTP)            │
│   GameService     подбор игр: жанры, платформы, возраст, исключение       │
│                   сыгранных, карточки, франшизы, кэш                      │
│   ProfileService  анкета: возраст, интересы, платформы, регион по IP      │
│   LibraryService  «во что я играл», отзывы, избранное, пагинация          │
│   entities.py     12 сущностей (Game, GameDetails, UserProfile, …)        │
│   age_ratings.py  AgePolicy: ESRB/PEGI → минимальный возраст              │
│   exceptions.py   21 тип ошибки, у каждого — user_message                 │
│   interfaces.py   GamesProvider, IpLocationProvider,                      │
│                   ProfileRepository, LibraryRepository                    │
└───────────────┬───────────────────────────────────────┬─────────────────┘
                ▼                                       ▼
┌───────────────────────────────────┐  ┌──────────────────────────────────┐
│ INFRASTRUCTURE / API              │  │ INFRASTRUCTURE / DB              │
│   http_client.py  JsonHttpClient  │  │   database.py     Database       │
│   rawg_client.py  RawgClient      │  │   models.py       3 ORM-таблицы  │
│   ip_location_    IpLocationClient│  │   repositories.py SqlProfile…,   │
│     client.py     (ipapi.co)      │  │                   SqlLibrary…    │
└───────────────────────────────────┘  └──────────────────────────────────┘

Сквозные модули: config.py (Settings — все ключи из окружения),
                 app.py (Application — композиционный корень, main)
```

### Структура каталогов

```
GemInfo/
├── run.py                          # точка входа: python run.py
├── gamehunter/
│   ├── app.py                      # Application, configure_logging, main
│   ├── config.py                   # Settings (frozen dataclass), from_env
│   ├── domain/
│   │   ├── age_ratings.py          # AgePolicy: ESRB / PEGI → возраст
│   │   ├── entities.py             # Game, GameDetails, UserProfile, …
│   │   ├── exceptions.py           # GameHunterError и наследники
│   │   ├── interfaces.py           # порты домена (ABC)
│   │   └── services/
│   │       ├── game_service.py     # подбор игр и работа с каталогом
│   │       ├── library_service.py  # сыгранные игры, отзывы, избранное
│   │       └── profile_service.py  # анкета, возраст, IP, регион
│   ├── infrastructure/
│   │   ├── api/
│   │   │   ├── http_client.py      # JsonHttpClient (requests)
│   │   │   ├── ip_location_client.py   # ipapi.co / ipwho.is
│   │   │   └── rawg_client.py      # RAWG Video Games Database
│   │   └── db/
│   │       ├── database.py         # engine, session_scope, create_all
│   │       ├── models.py           # user_profiles, played_games, favorite_games
│   │       └── repositories.py     # SqlProfileRepository, SqlLibraryRepository
│   └── presentation/
│       ├── gateway.py              # TelegramGateway
│       ├── handlers.py             # BotHandlers + safe_handler
│       ├── keyboards.py            # ButtonText, CallbackAction, клавиатуры
│       ├── state.py                # ContextScreen, UserContext, StateStorage
│       ├── texts.py                # тексты сообщений и форматирование
│       └── screens/                # 17 экранов (base, menu, picking,
│                                   #  franchise, profile, library)
├── scripts/
│   ├── init_db.py                  # создание таблиц и демо-данных
│   └── generate_mockups.py         # генерация SVG-мокапов экранов
├── tests/                          # 1409 тестов (pytest)
│   ├── conftest.py                 # фикстуры: SQLite, сервисы, экраны, бот
│   ├── fakes.py                    # подставные провайдеры, шлюз, фабрики
│   └── test_*.py                   # 20 модулей тестов
├── docs/                           # 9 документов + диаграммы + мокапы
│   ├── 01_ideya_i_trebovaniya.md
│   ├── 02_scenarii_ispolzovaniya.md
│   ├── 03_baza_dannyh.md
│   ├── 04_karta_ekranov.md
│   ├── 05_arhitektura.md
│   ├── 06_vneshnie_api.md
│   ├── 07_ustanovka_i_zapusk.md
│   ├── 08_plan_proekta.md
│   ├── 09_testirovanie.md
│   ├── diagrams/                   # 4 диаграммы DrawIO
│   └── mockups/                    # 17 SVG-мокапов экранов
├── .env.example                    # шаблон настроек
├── docker-compose.yml              # PostgreSQL 16 + Adminer
├── Makefile
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

---

## 4. Сценарии работы бота

```
/start
  └─▶ Экран 1 «Приветствие» ──Старт──▶ Экран 2 «Главное меню»

Экран 2 «Главное меню»
  ├─ Подобрать игру ──▶ Экран 3 «Выбор интересов»
  │                       ├─ отметить жанры (✔)
  │                       ├─ Показать подборку ──▶ Экран 4 «Подборка игр»
  │                       │                          ├─ Выбрать игру N ──▶ Экран 5 «Карточка игры»
  │                       │                          │                        ├─ Уже играл (игра исключается из подборок)
  │                       │                          │                        ├─ В избранное / Убрать из избранного
  │                       │                          │                        └─ Назад ──▶ Экран 4
  │                       │                          └─ Назад / Вперёд (страницы)
  │                       └─ Показать всё (без фильтра по жанрам)
  ├─ Игры по франшизе ──▶ Экран 6 «Ввод названия» ──▶ Экран 7 «Найденные франшизы»
  │                                                       └─ Выбрать франшизу ──▶ Экран 8 «Игры франшизы»
  │                                                                                  └─ Выбрать игру N ──▶ Экран 5
  ├─ Моя анкета ──▶ Экран 9 «Моя анкета»
  │                   ├─ Указать возраст ──▶ Экран 9а (ввод числа 3…120)
  │                   ├─ Выбрать интересы ──▶ Экран 9б (отметить жанры → Сохранить)
  │                   ├─ Выбрать платформы ──▶ Экран 9в (отметить → Сохранить)
  │                   └─ Определить регион по IP ──▶ Экран 9г (ввод публичного IP)
  ├─ Во что я играл ──▶ Экран 10 «Список» ──▶ Экран 11 «Информация и отзыв»
  │                                              ├─ Написать отзыв ──▶ Экран 11а (до 1000 символов)
  │                                              └─ Удалить из списка ──▶ Экран 10
  └─ Избранное ──▶ Экран 12 «Избранное» ──▶ Экран 5 «Карточка игры»
```

Команда `/start` возвращает в главное меню с любого экрана. Произвольный текст
вне режима ввода получает ответ «Нераспознанная команда…», а фото, голосовые,
стикеры и локации бот игнорирует.

Полное описание экранов, кнопок и особых случаев — в
[docs/04_karta_ekranov.md](docs/04_karta_ekranov.md), пошаговые сценарии — в
[docs/02_scenarii_ispolzovaniya.md](docs/02_scenarii_ispolzovaniya.md).

---

## 5. База данных

Три таблицы (PostgreSQL, SQLAlchemy 2.0). Все запросы фильтруются по
`tg_user_id`, поэтому пользователь не может получить чужие данные.

```sql
CREATE TABLE user_profiles (
    id             SERIAL PRIMARY KEY,
    tg_user_id     BIGINT       NOT NULL UNIQUE,
    age            INTEGER      NULL,
    genre_slugs    VARCHAR(300) NOT NULL DEFAULT '',
    genre_names    VARCHAR(300) NOT NULL DEFAULT '',
    platform_ids   VARCHAR(200) NOT NULL DEFAULT '',
    platform_names VARCHAR(200) NOT NULL DEFAULT '',
    ip_address     VARCHAR(45)  NULL,
    country        VARCHAR(80)  NULL,
    country_code   VARCHAR(8)   NULL,
    city           VARCHAR(80)  NULL,
    region_name    VARCHAR(80)  NULL,
    timezone       VARCHAR(80)  NULL,
    currency       VARCHAR(16)  NULL,
    latitude       FLOAT        NULL,
    longitude      FLOAT        NULL,
    updated_at     TIMESTAMP    NOT NULL
);

CREATE TABLE played_games (
    id         SERIAL PRIMARY KEY,
    tg_user_id BIGINT        NOT NULL,
    game_id    BIGINT        NOT NULL,
    slug       VARCHAR(150)  NOT NULL DEFAULT '',
    name       VARCHAR(150)  NOT NULL,
    image_url  VARCHAR(500)  NULL,
    played_at  TIMESTAMP     NOT NULL,
    review     VARCHAR(1000) NULL,
    CONSTRAINT uq_played_games_user_game UNIQUE (tg_user_id, game_id)
);
CREATE INDEX ix_played_games_user_date ON played_games (tg_user_id, played_at);

CREATE TABLE favorite_games (
    id         SERIAL PRIMARY KEY,
    tg_user_id BIGINT       NOT NULL,
    game_id    BIGINT       NOT NULL,
    slug       VARCHAR(150) NOT NULL DEFAULT '',
    name       VARCHAR(150) NOT NULL,
    image_url  VARCHAR(500) NULL,
    added_at   TIMESTAMP    NOT NULL,
    CONSTRAINT uq_favorite_games_user_game UNIQUE (tg_user_id, game_id)
);
CREATE INDEX ix_favorite_games_user_date ON favorite_games (tg_user_id, added_at);
```

Таблицы создаются из ORM-моделей автоматически: `python -m scripts.init_db`
(`--demo` добавляет демонстрационные данные, запуск идемпотентен).
Подробности — в [docs/03_baza_dannyh.md](docs/03_baza_dannyh.md).

---

## 6. Внешние API

| Сервис | Назначение | Аутентификация | Запросы |
|--------|------------|----------------|---------|
| [RAWG Video Games Database](https://rawg.io/apidocs) | каталог видеоигр | `key={RAWG_API_KEY}` в query | `GET /genres`, `GET /platforms/lists/parents`, `GET /games`, `GET /games/{id}`, `GET /franchises?search=…`, `GET /franchises/{id}` |
| [ipapi.co](https://ipapi.co) (запасной — [ipwho.is](https://ipwho.is)) | регион по IP: город, страна, часовой пояс, валюта | не требуется | `GET https://ipapi.co/{ip}/json/` |
| Telegram Bot API | обмен сообщениями | `BOT_TOKEN` | long polling через `pyTelegramBotAPI` |

Все запросы идут через `JsonHttpClient`: таймаут, проверка кода ответа,
разбор JSON и преобразование сетевых ошибок в доменные исключения. Справочники
и карточки игр кэшируются в `GameService` на `CACHE_TTL_SECONDS`, чтобы
укладываться в лимиты RAWG (20 000 запросов в месяц на бесплатном тарифе).

Подробное описание параметров, примеров ответов и разбора полей — в
[docs/06_vneshnie_api.md](docs/06_vneshnie_api.md).

---

## 7. Обработка ошибок

Бот не должен «падать» ни при каких обстоятельствах, поэтому ошибки
обрабатываются на трёх уровнях:

| Уровень | Что происходит |
|---------|----------------|
| HTTP-клиент | таймаут, ошибка соединения, 4xx/5xx, невалидный JSON → `ExternalServiceError` (или `None` при 404 и `allow_404=True`) |
| Клиенты сервисов | ошибка превращается в доменное исключение: `GamesUnavailableError`, `GenresUnavailableError`, `FranchiseSearchUnavailableError`, `RegionUnavailableError` |
| Репозитории | `SQLAlchemyError` → `DatabaseError`; каждая операция — в своей транзакции (`commit` / `rollback`) |
| Домен | ошибки ввода и логики: `InvalidAgeError`, `InvalidIpError`, `PrivateIpError`, `NoGamesFoundError`, `GameNotFoundError`, `FranchiseNotFoundError`, `PlayedGameNotFoundError`, `GameAlreadyPlayedError`, `ReviewTooLongError` |
| Экраны | `BaseScreen.show_error` отправляет `user_message` и возвращает пользователя в меню; при потере состояния — `state_lost` |
| Обработчики | декоратор `safe_handler` перехватывает **все** исключения: доменное → его `user_message`, неожиданное → «Произошла ошибка. Попробуйте ещё раз позже.»; подробности пишутся в лог |
| Telegram-шлюз | ошибки Telegram API логируются и возвращают `False`: бот продолжает работать |
| Запуск (`main`) | до опроса выполняется `getMe`: неверный токен (401), второй экземпляр бота (409) и отсутствие сети (`ConnectTimeout`) превращаются в понятное сообщение в консоли и код возврата 1 — вместо «сырой» трассировки |

Примеры сообщений пользователю:

| Ситуация | Сообщение |
|----------|-----------|
| Каталог игр недоступен | «Не удалось получить список игр. Попробуйте ещё раз позже.» |
| Игр по критериям нет | «По выбранным критериям игр не найдено. Попробуйте изменить интересы или снять фильтры в анкете.» |
| Возраст указан неверно | «Возраст должен быть числом от 3 до 120. Попробуйте ещё раз.» |
| Прислан локальный IP | «Это локальный (внутренний) IP-адрес — по нему нельзя определить регион…» |
| Сервис геолокации недоступен | «Не удалось определить регион по IP-адресу. Проверьте адрес и попробуйте ещё раз позже.» |
| Отзыв слишком длинный | «Отзыв не должен превышать 1000 символов. Сократите текст и попробуйте ещё раз.» |
| Нет связи с базой | «Ошибка при работе с базой данных. Попробуйте ещё раз позже.» |
| Не задан токен бота | `[ОШИБКА НАСТРОЙКИ] …` в консоли при запуске, процесс завершается с кодом 1 |
| Токен неверный (401) | `[ОШИБКА НАСТРОЙКИ] … проверьте BOT_TOKEN` |
| Бот уже запущен (409) | `[ОШИБКА ЗАПУСКА] … закройте второй процесс` |
| Нет связи с `api.telegram.org` | `[ОШИБКА СЕТИ] … включите VPN или укажите PROXY_URL` |

---

## 8. Тесты

```bash
make test                                   # все тесты
python -m pytest -q                         # то же самое
python -m pytest -q tests/test_bot_flow.py  # сквозные сценарии использования
python -m pytest --collect-only -q | tail -1
```

**1409 тестов** в 20 модулях. Тесты не требуют интернета и PostgreSQL: внешние
сервисы заменены подставными объектами из `tests/fakes.py`, база данных — SQLite
во временной папке, Telegram — `FakeGateway`.

| Группа | Модули | Что проверяется |
|--------|--------|-----------------|
| Домен | `test_entities`, `test_age_ratings`, `test_exceptions`, `test_game_service`, `test_profile_service`, `test_library_service` | сущности, возрастные рейтинги ESRB/PEGI, тексты ошибок, подбор игр, анкета, библиотека |
| Инфраструктура | `test_http_client`, `test_rawg_client`, `test_ip_location_client`, `test_repositories` | HTTP-ошибки, разбор ответов RAWG и сервисов геолокации, схема БД и репозитории |
| Представление | `test_texts`, `test_keyboards`, `test_state`, `test_screens`, `test_handlers`, `test_app`, `test_mockups` | тексты и лимит 4096 символов, клавиатуры и callback-данные, состояние, все 17 экранов, обработчики, сборка приложения, мокапы |
| Настройки и скрипты | `test_config`, `test_init_db` | `Settings.from_env`, создание таблиц и демо-данных, CLI |
| Сквозные | `test_bot_flow` | 48 сценариев «от /start до результата», включая ошибки сервисов и базы |

Проверка синтаксиса всех модулей: `make lint` (`python -m compileall`).

Подробнее — в [docs/09_testirovanie.md](docs/09_testirovanie.md).

---

## 9. Полезные команды (Makefile)

| Команда | Что делает |
|---------|------------|
| `make help` | список доступных команд |
| `make install` | установить основные зависимости |
| `make install-dev` | установить зависимости для разработки (pytest) |
| `make init-db` | создать таблицы базы данных |
| `make demo` | создать таблицы и добавить демонстрационные данные |
| `make run` | запустить Telegram-бота |
| `make test` | запустить тесты |
| `make mockups` | перегенерировать SVG-мокапы 17 экранов |
| `make ae-assets` | собрать анимированные карточки и слои для After Effects (`docs/ae`) |
| `make lint` | проверить синтаксис всех файлов проекта |
| `make clean` | удалить кэш Python и локальную базу SQLite |

---

## 10. Документация проекта (артефакты)

| Документ | Содержание |
|----------|------------|
| [01_ideya_i_trebovaniya.md](docs/01_ideya_i_trebovaniya.md) | идея, возможности, технологические требования, безопасность секретов |
| [02_scenarii_ispolzovaniya.md](docs/02_scenarii_ispolzovaniya.md) | акторы, Use Case диаграмма, 9 детализированных сценариев |
| [03_baza_dannyh.md](docs/03_baza_dannyh.md) | три таблицы, SQL-схема, ER-диаграмма, ORM-модели, операции с данными |
| [04_karta_ekranov.md](docs/04_karta_ekranov.md) | карта перемещения, 17 экранов, кнопки, особые случаи, сводка callback-данных |
| [05_arhitektura.md](docs/05_arhitektura.md) | принципы, схема слоёв, состав модулей, поток данных, дерево проекта |
| [06_vneshnie_api.md](docs/06_vneshnie_api.md) | RAWG и сервисы геолокации: запросы, примеры ответов, разбор полей, ошибки |
| [07_ustanovka_i_zapusk.md](docs/07_ustanovka_i_zapusk.md) | пошаговая установка, запуск, проверка в Telegram, возможные проблемы |
| [08_plan_proekta.md](docs/08_plan_proekta.md) | план по этапам, чек-лист ручного тестирования, работа с Git, риски |
| [09_testirovanie.md](docs/09_testirovanie.md) | состав тестов, что проверяется по слоям, пример сквозного теста |
| [10_ae_animaciya_kartochek.md](docs/10_ae_animaciya_kartochek.md) | анимированные карточки для After Effects: раскадровка, слои, экспорт GIF |
| [11_pamyatka_stop_i_start.md](docs/11_pamyatka_stop_i_start.md) | памятка: как остановить и снова запустить бота, Docker и PostgreSQL на Windows |

Диаграммы DrawIO (открываются на [app.diagrams.net](https://app.diagrams.net)):

| Файл | Диаграмма |
|------|-----------|
| [docs/diagrams/use_case.drawio](docs/diagrams/use_case.drawio) | варианты использования и акторы |
| [docs/diagrams/er_diagram.drawio](docs/diagrams/er_diagram.drawio) | структура базы данных |
| [docs/diagrams/screens_flow.drawio](docs/diagrams/screens_flow.drawio) | карта перемещения по экранам |
| [docs/diagrams/architecture.drawio](docs/diagrams/architecture.drawio) | трёхслойная архитектура |

Мокапы экранов — [docs/mockups/](docs/mockups/): 17 SVG-файлов, по одному на
экран. Они **генерируются из кода бота** (`scripts/generate_mockups.py` берёт
тексты из `presentation/texts.py` и кнопки из `presentation/keyboards.py`),
поэтому макеты всегда соответствуют реальному интерфейсу:

```bash
make mockups        # пересобрать мокапы после изменения текстов или кнопок
```

Тест `tests/test_mockups.py::TestRepoMockups::test_content_is_up_to_date`
проверяет, что мокапы в репозитории не устарели.

Анимированные карточки для Adobe After Effects — [docs/ae/](docs/ae/): три
карточки (приветствие, выбор жанра, выбор игры) в виде готовых GIF, слоёв PNG с
прозрачностью, раскадровки `timeline.json` (секунды и кадры AE) и скрипта
`import_layers.jsx`. Инструкция по сборке композиции и экспорту GIF —
[docs/10_ae_animaciya_kartochek.md](docs/10_ae_animaciya_kartochek.md), живое
превью «карточка сверху + текст снизу» — `docs/ae/preview.html`.

```bash
make ae-assets      # пересобрать карточки, слои и раскадровку (нужен Pillow)
```

---

## 11. Лицензия

Учебный проект. Распространяется по лицензии [MIT](LICENSE).
Данные об играх предоставлены [RAWG Video Games Database](https://rawg.io).
