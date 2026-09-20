# TravelHunter — Telegram-бот для подбора путешествий выходного дня

Выпускной проект: Python, `telebot`, `requests`, `SQLAlchemy`, PostgreSQL и внешние API
(Ninjas Holidays, GeoNames, Wikipedia). Код написан в ООП-стиле и разделён на три слоя:
представление, бизнес-логика и инфраструктура.

---

## 1. Идея проекта

TravelHunter помогает пользователю выбрать город для небольшого путешествия выходного дня.

Пользователь может:

| № | Возможность | Экран |
|---|-------------|-------|
| 1 | Посмотреть российские праздники на ближайшие 7 дней | Экран 3 |
| 2 | Указать город, в котором он сейчас находится | Экран 4 |
| 3 | Получить список ближайших городов в радиусе 500 км | Экран 5 |
| 4 | Выбрать город для поездки (поездка сохраняется в базу данных) | Экран 6 |
| 5 | Посмотреть историю своих поездок (с пагинацией по 5 записей) | Экран 7 |
| 6 | Посмотреть информацию о конкретной поездке | Экран 8 |
| 7 | Добавить заметку о поездке (до 1000 символов) | Экран 9 |

---

## 2. Быстрый старт

### 2.1. Требования

* Python 3.10+;
* PostgreSQL 14+ (для локальной разработки подойдёт и SQLite — см. ниже);
* Git.

### 2.2. Установка

```bash
git clone <адрес вашего репозитория>
cd GemInfo

# виртуальное окружение (рекомендуется)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt          # основные зависимости
pip install -r requirements-dev.txt      # + pytest (для тестов)
```

### 2.3. Настройка `.env`

Секреты **не хранятся в коде и не попадают в Git** — они читаются из файла `.env`
(файл добавлен в `.gitignore`).

```bash
cp .env.example .env
```

Заполните в `.env`:

| Переменная | Где взять | Обязательна |
|------------|-----------|-------------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` | да |
| `DATABASE_URL` | строка подключения к PostgreSQL | да (иначе SQLite) |
| `NINJAS_API_KEY` | [api-ninjas.com](https://api-ninjas.com/) → личный кабинет | для праздников |
| `GEONAMES_USERNAME` | [geonames.org](https://www.geonames.org/login) → включить Free Web Services | для городов |

Пример строки подключения к PostgreSQL:

```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/travelhunter
```

Поднять PostgreSQL одной командой (если установлен Docker):

```bash
docker compose up -d
```

### 2.4. Создание таблиц и запуск

```bash
python -m scripts.init_db          # создать таблицу visited_cities
python -m scripts.init_db --demo   # то же + 6 демонстрационных поездок

python run.py                      # запуск бота (long polling)
```

Бот также создаёт таблицы автоматически при старте — скрипт `init_db.py` удобен,
когда базу нужно подготовить заранее или добавить демо-данные.

> **Локальный запуск без PostgreSQL.** Если `DATABASE_URL` не задан, бот использует
> файл `travelhunter.db` (SQLite). Это удобно для быстрой проверки, но для сдачи
> проекта настроьте PostgreSQL — драйвер `psycopg2` уже есть в `requirements.txt`.

---

## 3. Архитектура проекта

Проект построен на **трёхслойной архитектуре**; зависимости направлены внутрь —
бизнес-логика не знает ни про Telegram, ни про SQLAlchemy, ни про конкретные API.

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. PRESENTATION — слой представления                                  │
│    handlers.py (события Telegram) → screens/* (Экраны 1–9)            │
│    keyboards.py, texts.py, state.py, gateway.py                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ вызывает сервисы
┌───────────────────────────────▼──────────────────────────────────────┐
│ 2. DOMAIN — слой бизнес-логики                                        │
│    services/ (HolidayService, CityService, TripService)               │
│    entities.py, exceptions.py, interfaces.py (порты)                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ работает через интерфейсы
┌───────────────────────────────▼──────────────────────────────────────┐
│ 3. INFRASTRUCTURE — слой доступа к данным                             │
│    db/ (SQLAlchemy: Database, VisitedCityORM, SqlTripRepository)      │
│    api/ (NinjasHolidaysClient, GeoNamesClient, WikipediaClient)       │
└──────────────────────────────────────────────────────────────────────┘
```

### Структура каталогов

```
GemInfo/
├── run.py                     # точка входа: python run.py
├── requirements.txt           # основные зависимости
├── requirements-dev.txt       # зависимости для тестов
├── pytest.ini                 # настройки pytest
├── docker-compose.yml         # PostgreSQL для локальной разработки
├── Makefile                   # короткие команды (install / run / test)
├── .env.example               # шаблон настроек (секреты — в .env, не в Git)
├── scripts/
│   ├── init_db.py             # создание таблиц и демо-данных
│   └── generate_mockups.py    # генерация SVG-мокапов экранов
├── travelhunter/
│   ├── config.py              # Settings: чтение настроек из окружения
│   ├── app.py                 # композиционный корень (сборка всех слоёв)
│   ├── presentation/          # СЛОЙ 1
│   │   ├── handlers.py        # обработчики команд, кнопок и текста
│   │   ├── gateway.py         # отправка сообщений/фото в Telegram
│   │   ├── keyboards.py       # reply- и inline-клавиатуры, callback-данные
│   │   ├── texts.py           # все тексты бота и их форматирование
│   │   ├── state.py           # состояние пользователя (переходы экранов)
│   │   └── screens/           # Экраны 1–9
│   │       ├── start_menu.py  #   Экран 1 «Старт», Экран 2 «Главное меню»
│   │       ├── holidays.py    #   Экран 3 «Праздники на 7 дней»
│   │       ├── cities.py      #   Экраны 4–6 «Города куда съездить»
│   │       └── history.py     #   Экраны 7–9 «История поездок»
│   ├── domain/                # СЛОЙ 2
│   │   ├── entities.py        # Holiday, City, NearbyCity, CityInfo, Trip, TripPage
│   │   ├── exceptions.py      # ошибки с готовыми текстами для пользователя
│   │   ├── interfaces.py      # HolidaysProvider, CityProvider, TripRepository…
│   │   └── services/
│   │       ├── holiday_service.py
│   │       ├── city_service.py
│   │       └── trip_service.py
│   └── infrastructure/        # СЛОЙ 3
│       ├── db/
│       │   ├── database.py    # движок и сессии SQLAlchemy
│       │   ├── models.py      # ORM-модель таблицы visited_cities
│       │   └── repositories.py# SqlTripRepository
│       └── api/
│           ├── http_client.py     # общий HTTP-клиент (requests)
│           ├── ninjas_client.py   # праздники
│           ├── geonames_client.py # города и координаты
│           └── wikipedia_client.py# описание и фото города
├── docs/                      # артефакты проекта (план, диаграммы, ТЗ)
│   ├── diagrams/              # диаграммы DrawIO (.drawio)
│   └── mockups/               # мокапы экранов (.svg)
└── tests/                     # 198 тестов (pytest), без сети и без Telegram
```

Подробнее: [docs/05_arhitektura.md](docs/05_arhitektura.md).

---

## 4. Сценарии работы бота

```
/start ─► Экран 1 «Старт» ─► Экран 2 «Главное меню»
                                   │
             ┌─────────────────────┼──────────────────────┐
             ▼                     ▼                      ▼
   Экран 3 «Праздники»    Экран 4 «Ввод города»   Экран 7 «История поездок»
             │                     ▼                      ▼
             │             Экран 5 «Ближайшие города»  Экран 8 «Информация о поездке»
             │                     ▼                      ▼
             │             Экран 6 «Информация о городе»  Экран 9 «Заметка» ──► Экран 8
             └─────────────── «В главное меню» ────────────┘
```

* `/start` всегда возвращает в главное меню, где бы пользователь ни находился;
* текстовое сообщение вне режимов ввода — «Нераспознанная команда…»;
* фото, файлы, голосовые и видео — бот игнорирует.

Полное описание экранов: [docs/04_karta_ekranov.md](docs/04_karta_ekranov.md).

---

## 5. База данных

Таблица `visited_cities` (PostgreSQL):

```sql
CREATE TABLE visited_cities (
    id           SERIAL PRIMARY KEY,
    tg_user_id   BIGINT        NOT NULL,
    name         VARCHAR(50)   NOT NULL,
    arrival_date TIMESTAMP     NOT NULL,
    note         VARCHAR(1000) NULL
);
CREATE INDEX ix_visited_cities_user_date ON visited_cities (tg_user_id, arrival_date);
```

Таблица создаётся автоматически из ORM-модели `VisitedCityORM` (SQLAlchemy 2.0).
Подробности и ER-диаграмма: [docs/03_baza_dannyh.md](docs/03_baza_dannyh.md).

---

## 6. Внешние API

| Сервис | Назначение | Endpoint |
|--------|-----------|----------|
| Ninjas Holidays API | праздники страны | `GET https://api.api-ninjas.com/v2/holidays` |
| GeoNames `searchJSON` | проверка города и его координаты | `GET https://secure.geonames.org/searchJSON` |
| GeoNames `findNearbyPlaceNameJSON` | города в радиусе 500 км | `GET https://secure.geonames.org/findNearbyPlaceNameJSON` |
| MediaWiki (ru.wikipedia.org) | описание и фото города | `GET https://ru.wikipedia.org/w/api.php` |

Параметры запросов, примеры ответов и обработка ошибок:
[docs/06_vneshnie_api.md](docs/06_vneshnie_api.md).

---

## 7. Обработка ошибок

Ни одна ошибка не приводит к аварийному завершению бота:

| Источник ошибки | Что происходит |
|-----------------|----------------|
| Внешний API (таймаут, HTTP 4xx/5xx, не-JSON) | клиент порождает `ExternalServiceError` → пользователь видит «Не удалось получить список праздников…» / «Не удалось получить информацию о городе…» |
| Город не найден | «Город не найден. Проверьте название города и попробуйте ещё раз.» + повторный ввод |
| База данных | `DatabaseError` → «Ошибка при работе с базой данных…» |
| Заметка длиннее 1000 символов | заметка не сохраняется, бот ждёт повторного ввода |
| Любая непредвиденная ошибка | декоратор `safe_handler` логирует её и отвечает «Произошла ошибка. Попробуйте ещё раз позже.» |
| Потеря состояния (перезапуск бота) | «Данные предыдущего шага не сохранились…» + возврат в главное меню |

---

## 8. Тесты

```bash
pytest            # 198 тестов
pytest -v         # подробный вывод
```

Тесты не требуют интернета, Telegram и PostgreSQL: внешние API подменяются
фейками, база данных — временным SQLite-файлом. Покрыты:

* доменные сервисы (фильтрация праздников, выбор ближайших городов, валидация заметок);
* клиенты внешних API (разбор ответов, ошибки сети, ошибки аккаунтов);
* репозиторий и структура таблицы `visited_cities`;
* клавиатуры, тексты и состояния пользователя;
* сквозные сценарии переходов по всем девяти экранам.

Подробности: [docs/09_testirovanie.md](docs/09_testirovanie.md).

---

## 9. Полезные команды (Makefile)

```bash
make install     # установить зависимости
make init-db     # создать таблицы
make run         # запустить бота
make test        # запустить тесты
make mockups     # перегенерировать мокапы экранов
make lint        # проверить синтаксис всех файлов
```

---

## 10. Документация проекта (артефакты)

| Документ | Содержание |
|----------|-----------|
| [docs/01_ideya_i_trebovaniya.md](docs/01_ideya_i_trebovaniya.md) | идея, возможности, технологические требования |
| [docs/02_scenarii_ispolzovaniya.md](docs/02_scenarii_ispolzovaniya.md) | сценарии использования + Use Case диаграмма |
| [docs/03_baza_dannyh.md](docs/03_baza_dannyh.md) | структура данных, ER-диаграмма, SQL |
| [docs/04_karta_ekranov.md](docs/04_karta_ekranov.md) | карта перемещения и описание экранов 1–9 |
| [docs/05_arhitektura.md](docs/05_arhitektura.md) | трёхслойная архитектура, ООП, модули |
| [docs/06_vneshnie_api.md](docs/06_vneshnie_api.md) | интеграция с Ninjas, GeoNames, Wikipedia |
| [docs/07_ustanovka_i_zapusk.md](docs/07_ustanovka_i_zapusk.md) | пошаговая установка и получение ключей |
| [docs/08_plan_proekta.md](docs/08_plan_proekta.md) | план проекта по этапам |
| [docs/09_testirovanie.md](docs/09_testirovanie.md) | тесты и проверка качества |
| [docs/diagrams/](docs/diagrams/) | диаграммы в формате DrawIO: Use Case, карта экранов, ER-диаграмма, архитектура |
| [docs/mockups/](docs/mockups/) | мокапы экранов 1–9 (SVG), генерируются из кода бота |

---

## 11. Лицензия

Проект распространяется под лицензией MIT — см. файл [LICENSE](LICENSE).
