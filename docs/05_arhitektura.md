# 05. Архитектура проекта

## Принципы

1. **Трёхслойная архитектура** — представление, бизнес-логика, инфраструктура.
2. **ООП-стиль** — каждый слой состоит из классов с одной зоной ответственности;
   поведение наследуется от абстрактных базовых классов (`abc.ABC`).
3. **Инверсия зависимостей** — бизнес-логика объявляет интерфейсы (порты),
   а инфраструктура их реализует (адаптеры).
4. **Внедрение зависимостей через конструктор** — глобальных переменных и
   «импортов ради side-effect» нет; все объекты собираются в `travelhunter/app.py`.
5. **Единая обработка ошибок** — доменные исключения содержат готовый текст
   для пользователя; обработчики Telegram перехватывают любые ошибки.

## Схема слоёв

```mermaid
graph TD
    subgraph P["СЛОЙ 1 — PRESENTATION (travelhunter/presentation)"]
        H["BotHandlers<br/>события Telegram"]
        SC["Экраны 1–9<br/>screens/*"]
        KB["keyboards.py"]
        TX["texts.py"]
        ST["state.py — UserContext, StateStorage"]
        GW["gateway.py — TelegramGateway"]
    end

    subgraph D["СЛОЙ 2 — DOMAIN (travelhunter/domain)"]
        HS["HolidayService"]
        CS["CityService"]
        TS["TripService"]
        EN["entities.py"]
        EX["exceptions.py"]
        IF["interfaces.py — порты"]
    end

    subgraph I["СЛОЙ 3 — INFRASTRUCTURE (travelhunter/infrastructure)"]
        NH["NinjasHolidaysClient"]
        GN["GeoNamesClient"]
        WK["WikipediaClient"]
        HC["JsonHttpClient (requests)"]
        REPO["SqlTripRepository"]
        DB["Database + VisitedCityORM (SQLAlchemy)"]
    end

    TG[(Telegram Bot API)]
    PG[(PostgreSQL)]
    API1[[Ninjas API]]
    API2[[GeoNames API]]
    API3[[Wikipedia API]]

    H --> SC
    SC --> KB
    SC --> TX
    SC --> ST
    SC --> GW
    H --> ST
    GW --> TG

    SC --> HS
    SC --> CS
    SC --> TS
    H --> CS

    HS --> IF
    CS --> IF
    TS --> IF

    IF -.реализуют.-> NH
    IF -.реализуют.-> GN
    IF -.реализуют.-> WK
    IF -.реализуют.-> REPO

    NH --> HC
    GN --> HC
    WK --> HC
    HC --> API1
    HC --> API2
    HC --> API3

    REPO --> DB
    DB --> PG
```

Стрелки показывают направление зависимостей: **presentation → domain ← infrastructure**.
Доменный слой не импортирует ни `telebot`, ни `sqlalchemy`, ни `requests`.

## Состав слоёв

### Слой 1. Presentation — «что видит пользователь»

| Модуль | Класс / функции | Ответственность |
|--------|-----------------|-----------------|
| `handlers.py` | `BotHandlers`, декоратор `safe_handler` | приём событий Telegram (команда, кнопка, текст, unsupported-типы), маршрутизация к экранам, перехват всех ошибок |
| `gateway.py` | `TelegramGateway` | единственная точка отправки сообщений и фото; ошибки Telegram API логируются и не «роняют» бота |
| `keyboards.py` | `ButtonText`, `CallbackAction`, `parse_callback`, фабрики клавиатур | reply- и inline-клавиатуры, формат callback-данных |
| `texts.py` | константы и функции `format_*` | все тексты бота и их форматирование |
| `state.py` | `Screen`, `UserContext`, `StateStorage` | конечный автомат диалога: какой экран сейчас, выбранный город, список городов, страница истории, id поездки |
| `screens/*` | `StartScreen`, `MainMenuScreen`, `HolidaysScreen`, `CityInputScreen`, `NearbyCitiesScreen`, `CityInfoScreen`, `HistoryScreen`, `TripInfoScreen`, `NoteInputScreen` | по одному классу на экран из карты перемещения |

### Слой 2. Domain — «правила предметной области»

| Модуль | Содержание |
|--------|------------|
| `entities.py` | `Holiday`, `City`, `NearbyCity`, `CityInfo`, `Trip`, `TripPage` — неизменяемые dataclass-сущности |
| `exceptions.py` | `TravelHunterError` и наследники: `ConfigError`, `ExternalServiceError`, `HolidaysUnavailableError`, `CitySearchUnavailableError`, `CityInfoUnavailableError`, `CityNotFoundError`, `NearbyCitiesNotFoundError`, `DatabaseError`, `TripNotFoundError`, `NoteTooLongError`, `EmptyNoteError`, `InvalidStateError`. У каждого есть `user_message` |
| `interfaces.py` | порты: `HolidaysProvider`, `CityProvider`, `CityInfoProvider`, `TripRepository` |
| `services/holiday_service.py` | окно в 7 дней, сортировка по дате, лимит 5 праздников, запрос двух годов на стыке лет |
| `services/city_service.py` | поиск города, исключение города пользователя и дубликатов, сортировка по расстоянию, лимит 5, обрезка описания города |
| `services/trip_service.py` | создание поездки, история с пагинацией, проверка владельца поездки, валидация заметки (≤ 1000 символов, непустая) |

### Слой 3. Infrastructure — «как данные приходят и хранятся»

| Модуль | Содержание |
|--------|------------|
| `api/http_client.py` | `JsonHttpClient` — общий GET-запрос: таймаут, ошибки соединения, HTTP-статусы, разбор JSON |
| `api/ninjas_client.py` | `NinjasHolidaysClient` — `GET /v2/holidays`, заголовок `X-Api-Key`, разбор дат в разных форматах |
| `api/geonames_client.py` | `GeoNamesClient` — `searchJSON` и `findNearbyPlaceNameJSON`, выбор города с наибольшим населением, обработка ошибок аккаунта GeoNames |
| `api/wikipedia_client.py` | `WikipediaClient` — MediaWiki Action API: `prop=extracts|pageimages`, перенаправления, миниатюра изображения |
| `db/database.py` | `Database` — движок SQLAlchemy, фабрика сессий, контекст `session_scope()` с commit/rollback, `create_all()` |
| `db/models.py` | `Base`, `VisitedCityORM` — таблица `visited_cities` |
| `db/repositories.py` | `SqlTripRepository` — реализация порта `TripRepository`; преобразование ORM → доменная сущность `Trip` |

### Сквозные модули

| Модуль | Содержание |
|--------|------------|
| `config.py` | `Settings` — чтение настроек из `.env`/переменных окружения, валидация, предупреждения о незаполненных ключах |
| `app.py` | `Application` — композиционный корень: создаёт инфраструктуру, сервисы, экраны и обработчики; `main()` — запуск бота |

## Поток данных на примере «Выбрать город для поездки»

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant TG as Telegram
    participant H as BotHandlers
    participant S6 as CityInfoScreen
    participant TS as TripService
    participant R as SqlTripRepository
    participant DB as PostgreSQL
    participant CS as CityService
    participant W as WikipediaClient

    U->>TG: нажал «Выбрать город 1»
    TG->>H: CallbackQuery(data="city:1")
    H->>S6: show(chat_id, user_id, city_index=1)
    S6->>S6: достаёт город из UserContext
    S6->>TS: create_trip(user_id, "Тула")
    TS->>R: add(user_id, "Тула", now)
    R->>DB: INSERT INTO visited_cities
    DB-->>R: id = 42
    R-->>TS: Trip(id=42, …)
    TS-->>S6: Trip
    S6->>CS: get_city_info("Тула")
    CS->>W: fetch_city_info("Тула")
    W-->>CS: CityInfo(title, summary, image_url)
    CS-->>S6: CityInfo
    S6->>TG: send_photo(image_url, caption)
    TG-->>U: фото города + описание
```

## Почему выбраны такие решения

| Решение | Обоснование |
|---------|-------------|
| Интерфейсы в доменном слое | сервисы можно тестировать на фейках; базу можно заменить (PostgreSQL → SQLite) без изменения бизнес-логики |
| Состояние пользователя в памяти (`StateStorage`) | не требуется Redis; данные диалога живут между экранами; хранилище потокобезопасно (`threading.RLock`), так как telebot обрабатывает апдейты в пуле потоков |
| Сущности отдельны от ORM-моделей | бизнес-логика не зависит от схемы базы и от «ленивой загрузки» SQLAlchemy |
| Все тексты в `texts.py` | легко сверять формулировки с техническим заданием |
| Единый `JsonHttpClient` | одинаковая обработка сетевых ошибок для всех трёх внешних API |
| `Settings` как неизменяемый dataclass | настройки читаются один раз при старте и не могут «испортиться» в процессе работы |
