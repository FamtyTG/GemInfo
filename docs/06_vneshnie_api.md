# 06. Интеграция с внешними API

| Сервис | Назначение | Аутентификация | Клиент в проекте |
|--------|------------|----------------|------------------|
| **RAWG Video Games Database** | каталог видеоигр: жанры, платформы, игры, карточки, франшизы | API-ключ в query-параметре `key` | `infrastructure/api/rawg_client.py` → `RawgClient` |
| **ipapi.co** (запасной — **ipwho.is**) | регион по IP-адресу: город, страна, часовой пояс, валюта | не требуется | `infrastructure/api/ip_location_client.py` → `IpLocationClient` |
| **Telegram Bot API** | обмен сообщениями с пользователем | токен бота | библиотека `pyTelegramBotAPI` (telebot) через `presentation/gateway.py` |

Все HTTP-запросы к внешним сервисам выполняются через один класс
`JsonHttpClient` (`infrastructure/api/http_client.py`): он задаёт таймаут
(`HTTP_TIMEOUT`, по умолчанию 10 секунд), проверяет код ответа, разбирает JSON и
преобразует сетевые ошибки в доменное исключение `ExternalServiceError`.

```
Экран → Сервис домена → Интерфейс (GamesProvider / IpLocationProvider)
                                    │
                        RawgClient / IpLocationClient
                                    │
                              JsonHttpClient → requests → внешний API
```

---

## 1. RAWG Video Games Database — каталог видеоигр

* Документация: <https://rawg.io/apidocs>
* Базовый адрес: `https://api.rawg.io/api`
* Аутентификация: параметр `key={RAWG_API_KEY}` добавляется ко всем запросам
  (`RawgClient._params`). Ключ хранится только в `.env`.
* Язык ответа: параметр `language=ru` (настройка `CATALOG_LANGUAGE`) — RAWG
  отдаёт русские названия и описания там, где они есть.
* Лимиты бесплатного тарифа: 20 000 запросов в месяц, до 20 записей на страницу.
  Чтобы укладываться в лимиты, справочники и карточки игр кэшируются в
  `GameService` на `CACHE_TTL_SECONDS` (по умолчанию 600 секунд).

### 1.1. Жанры (интересы пользователя) — Экраны 3 и 9б

```
GET https://api.rawg.io/api/genres?key={RAWG_API_KEY}&language=ru
```

Пример ответа:

```json
{
  "count": 19,
  "results": [
    {"id": 4, "name": "Action", "slug": "action", "games_count": 158342,
     "image_background": "https://media.rawg.io/media/games/618/618c2031a07bbff6b4f611f10b6bcdbc.jpg"},
    {"id": 5, "name": "RPG", "slug": "role-playing-games-rpg", "games_count": 52741}
  ]
}
```

Обработка (`RawgClient.fetch_genres`):

| Поле ответа | Куда попадает |
|-------------|---------------|
| `results[].id` | `Genre.id` |
| `results[].name` | `Genre.name` — показывается пользователю |
| `results[].slug` | `Genre.slug` — используется в фильтре `genres` запроса `/games` |
| `results[].games_count` | `Genre.games_count` |

Список сортируется по числу игр и обрезается до `MAX_GENRES` (по умолчанию 12).
Записи без `id`, `name` или `slug` пропускаются.

### 1.2. Платформы — Экран 9в

```
GET https://api.rawg.io/api/platforms/lists/parents?key={RAWG_API_KEY}&language=ru
```

Ответ содержит «родительские» платформы (PC, PlayStation, Xbox, Nintendo,
Android, iOS, Linux, macOS …) — именно их идентификаторы принимает фильтр
`parent_platforms` запроса `/games`.

Обработка (`RawgClient.fetch_platforms`):

* поля `result`/`results` → `Platform(id, name, slug, games_count, is_parent=True)`;
* если каталог ответил 404 или пустым списком, используется запасной перечень
  `PARENT_PLATFORM_FALLBACK` (PC, PlayStation, Xbox, Nintendo, Android, iOS) —
  бот продолжает работать без запроса к API.

### 1.3. Поиск игр (подборка) — Экран 4

```
GET https://api.rawg.io/api/games
    ?key={RAWG_API_KEY}
    &language=ru
    &page=1
    &page_size=5
    &ordering=-rating
    &genres=action,role-playing-games-rpg
    &parent_platforms=1,2
    &exclude_games=32,58175
    &exclude_additions=true
```

| Параметр | Откуда берётся |
|----------|----------------|
| `page`, `page_size` | `GameQuery.page`, настройка `MAX_GAMES` (+ запас на фильтрацию по возрасту) |
| `ordering` | настройка `DEFAULT_ORDERING` (`-rating` или `-released`) |
| `genres` | slug'и жанров, отмеченных на Экране 3, либо интересы из анкеты |
| `parent_platforms` | идентификаторы платформ из анкеты |
| `search` | название франшизы (запасной путь Экрана 8) |
| `exclude_games` | идентификаторы игр из таблицы `played_games` — «во что я уже играл» |
| `exclude_additions` | `true`: скрываем DLC и дополнения, оставляем самостоятельные игры |

Пример ответа (сокращён):

```json
{
  "count": 3187,
  "next": "https://api.rawg.io/api/games?page=2&...",
  "previous": null,
  "results": [
    {
      "id": 32,
      "slug": "the-witcher-3-wild-hunt",
      "name": "The Witcher 3: Wild Hunt",
      "released": "2015-05-18",
      "rating": 4.62,
      "metacritic": 93,
      "playtime": 50,
      "background_image": "https://media.rawg.io/media/games/618/618c2031a07bbff6b4f611f10b6bcdbc.jpg",
      "genres": [{"id": 4, "name": "Action", "slug": "action"}],
      "parent_platforms": [{"platform": {"id": 1, "name": "PC", "slug": "pc"}}],
      "platforms": [{"platform": {"id": 4, "name": "PC", "slug": "pc"}}]
    }
  ]
}
```

Обработка (`RawgClient.search_games` → `GamePage`):

| Поле ответа | Куда попадает |
|-------------|---------------|
| `results[]` | список `Game` (метод `_parse_game`) |
| `results[].released` | `Game.released` (`parse_release_date` понимает `YYYY-MM-DD`, `YYYY-MM`, `YYYY`) |
| `results[].rating`, `metacritic`, `playtime` | `Game.rating`, `Game.metacritic`, `Game.playtime_hours` |
| `results[].genres[].name` | `Game.genres` (кортеж названий) |
| `results[].parent_platforms[].platform.name` | `Game.platforms` (если поля нет — берётся `platforms[].platform.name`) |
| `count`, `page`, `page_size` | `GamePage.total_count`, `page`, `page_size` |
| `next`, `previous` | `GamePage.has_next`, `has_previous` |

### 1.4. Карточка игры — Экран 5 и возрастной фильтр

```
GET https://api.rawg.io/api/games/{id}?key={RAWG_API_KEY}&language=ru
```

Дополнительные поля, которых нет в списке игр:

| Поле ответа | Куда попадает |
|-------------|---------------|
| `description_raw` (или `description`) | `GameDetails.summary` — HTML-теги снимаются функцией `strip_html`, текст сокращается до 400 символов |
| `esrb_rating` (`{id, name, slug}`) | `GameDetails.min_age` и `age_rating_label` через `AgePolicy` |
| `developers[].name`, `publishers[].name` | `GameDetails.developers`, `publishers` |
| `stores[].store.name` | `GameDetails.stores` (до 6) |
| `tags[].name` | `GameDetails.tags` (до 6) |

Особенности:

* **Возрастной рейтинг есть только в карточке игры**, поэтому `GameService`
  догружает не более `DETAILS_FETCH_LIMIT` (по умолчанию 8) карточек на страницу
  подборки и отбрасывает игры, чей `min_age` больше возраста пользователя.
  Игры без рейтинга показываются всегда.
* Если игры нет в каталоге, RAWG возвращает `{"detail": "Not found."}` — клиент
  трактует это как «карточка не найдена» (`None`), а не как ошибку.
* Карточки игр кэшируются в `GameService` на `CACHE_TTL_SECONDS`.

### 1.5. Поиск франшиз (IP) — Экран 7

```
GET https://api.rawg.io/api/franchises
    ?key={RAWG_API_KEY}
    &search=Marvel
    &ordering=-games_count
    &page_size=5
    &language=ru
```

Обработка (`RawgClient.search_franchises`): `results[]` → `Franchise(id, name,
slug, games_count)`; список обрезается до `MAX_FRANCHISES` (по умолчанию 5).

### 1.6. Игры франшизы — Экран 8

```
GET https://api.rawg.io/api/franchises/{id}?key={RAWG_API_KEY}&page_size=5&language=ru
```

Ответ содержит поле `games` — список игр франшизы. Обработка
(`RawgClient.fetch_franchise_games`):

1. если `games` не пустой — игры разбираются методом `_parse_game` и обрезаются
   до `MAX_GAMES`;
2. если списка игр нет — запасной путь: поиск `GET /games?search={название
   франшизы}` (так работают франшизы, у которых RAWG не хранит перечень игр).

---

## 2. Геолокация по IP-адресу — Экран 9г

### Зачем это нужно

Регион пользователя используется в карточке игры: бот показывает строку
«Ваш регион: Kazan, Tatarstan Republic, Russia, валюта RUB», а часовой пояс и
валюта сохраняются в анкете (`user_profiles`).

### Ограничение Telegram Bot API

**Telegram Bot API не передаёт боту IP-адрес пользователя.** В объекте `User`
есть только `id`, `is_bot`, `first_name`, `last_name`, `username`,
`language_code`. Поэтому:

1. бот просит пользователя прислать свой **публичный** IP-адрес сообщением
   (его можно посмотреть на сайте 2ip.ru);
2. адрес извлекается из текста регулярным выражением
   (`profile_service.extract_ip`) — можно написать «мой адрес 5.188.0.1»;
3. адрес проверяется (`ProfileService.validate_ip`): формат IPv4/IPv6 и
   принадлежность к публичному диапазону. Локальные адреса
   (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1`,
   link-local, reserved, multicast) отклоняются с объяснением;
4. адрес отправляется в сервис геолокации, результат сохраняется в анкету.

### 2.1. ipapi.co (основной сервис)

```
GET https://ipapi.co/5.188.0.1/json/
```

Ключ не требуется. Бесплатный лимит — около 1000 запросов в сутки, поэтому
результат сохраняется в анкете и повторно не запрашивается.

Пример ответа:

```json
{
  "ip": "5.188.0.1",
  "city": "Kazan",
  "region": "Tatarstan Republic",
  "country": "RU",
  "country_name": "Russia",
  "timezone": "Europe/Moscow",
  "currency": "RUB",
  "latitude": 55.7887,
  "longitude": 49.1221,
  "org": "AS12389 PJSC Rostelecom"
}
```

Ответ об ошибке: `{"error": true, "reason": "Invalid IP Address"}` — клиент
преобразует его в `RegionUnavailableError`.

### 2.2. ipwho.is (запасной сервис)

Базовый адрес задаётся настройкой `IP_LOCATION_BASE_URL`, поэтому сервис можно
заменить без изменения кода:

```
GET https://ipwho.is/5.188.0.1
```

Формат ответа отличается: `timezone` и `currency` — вложенные объекты
(`timezone.id`, `currency.code`), признак успеха — поле `success`. Клиент
`IpLocationClient._parse_region` понимает **оба** формата: строковые и вложенные
значения, `country` как код (2 символа) и как название.

### Обработка ответа

| Поле | Куда попадает |
|------|---------------|
| `city` | `Region.city` |
| `region` / `region_name` | `Region.region_name` |
| `country_name` / `country` | `Region.country`, `Region.country_code` |
| `timezone` (строка или `{id}`) | `Region.timezone` |
| `currency` (строка или `{code}`) | `Region.currency` |
| `latitude`, `longitude` | `Region.latitude`, `Region.longitude` |
| IP из запроса | `Region.ip` |

Если в ответе нет ни города, ни страны (`Region.is_known == False`), регион не
сохраняется, а пользователь видит сообщение об ошибке определения региона.

---

## 3. Telegram Bot API

* Токен бота выдаёт [@BotFather](https://t.me/BotFather) и хранится в `BOT_TOKEN`.
* Бот работает в режиме long polling (`bot.infinity_polling()`), вебхук не
  используется — это упрощает запуск на локальной машине.
* Все обращения к Telegram идут через `TelegramGateway`:
  * `send_text` — текст длиннее 4096 символов обрезается с многоточием;
  * `send_photo` — обложка игры с подписью-карточкой; при ошибке экран
    автоматически отправляет текст;
  * `answer_callback` — ответ на нажатие inline-кнопки.
* Поддерживаемые типы входящих сообщений: текст и команда `/start`. Фото, видео,
  голосовые, стикеры и локации игнорируются (бот не отвечает), чтобы не мешать
  диалогу.

---

## Обработка ошибок внешних сервисов

| Ситуация | Что делает `JsonHttpClient` | Какое исключение видит домен | Что видит пользователь |
|----------|-----------------------------|------------------------------|------------------------|
| Превышен таймаут (`HTTP_TIMEOUT`) | логирует и преобразует | `ExternalServiceError(service, "timeout")` → конкретный наследник клиента | «Не удалось получить список игр…» / «Не удалось определить регион по IP-адресу…» |
| Нет соединения | то же | `ExternalServiceError(service, "connection error")` | то же |
| HTTP 4xx / 5xx | логирует код ответа | `ExternalServiceError(service, "http 403")` | то же |
| HTTP 404 при `allow_404=True` | возвращает `None` | исключения нет | игра/регион считается ненайденной, показывается соответствующее сообщение |
| Ответ не JSON | логирует | `ExternalServiceError(service, "invalid json")` | то же |
| `RAWG_API_KEY` не задан | запрос не выполняется | `GenresUnavailableError` / `GamesUnavailableError` / `FranchiseSearchUnavailableError` (в зависимости от операции) | «Бот настроен неправильно…» при запуске либо сообщение о недоступности каталога |
| Сервис геолокации вернул `error: true` / `success: false` | — | `RegionUnavailableError` | «Не удалось определить регион по IP-адресу…» |
| Любая непредвиденная ошибка клиента | логируется | преобразуется в доменное исключение того же типа | понятное сообщение, бот продолжает работать |

Правило проекта: **ни одна ошибка внешнего сервиса не приводит к падению бота**.
Исключение перехватывает декоратор `safe_handler`, пользователь получает текст
`user_message`, подробности пишутся в лог с именем сервиса и экрана.

---

## Как получить ключи

### RAWG Video Games Database

1. Зарегистрируйтесь на <https://rawg.io> (бесплатно).
2. Откройте профиль → **API Key** (<https://rawg.io/profile/api>).
3. Скопируйте ключ в `.env`:

   ```dotenv
   RAWG_API_KEY=ваш_ключ
   ```

Ключ обязателен: без него бот запустится, но все обращения к каталогу будут
возвращать сообщение о недоступности (проверка `RawgClient.is_configured`).

### Telegram-бот

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Придумайте имя и username бота.
3. Скопируйте выданный токен в `.env`:

   ```dotenv
   BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Сервис геолокации

Ключ не требуется. При желании смените сервис в `.env`:

```dotenv
IP_LOCATION_BASE_URL=https://ipapi.co    # по умолчанию
# IP_LOCATION_BASE_URL=https://ipwho.is  # запасной вариант
```

---

## Настройки интеграций в `.env`

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `RAWG_API_KEY` | — | ключ каталога RAWG (обязателен для работы подборки) |
| `IP_LOCATION_BASE_URL` | `https://ipapi.co` | сервис геолокации |
| `CATALOG_LANGUAGE` | `ru` | язык названий и описаний игр |
| `MAX_GAMES` | `5` | размер страницы подборки |
| `MAX_GENRES` | `12` | сколько жанров показывать на выбор |
| `MAX_FRANCHISES` | `5` | сколько франшиз показывать в результатах поиска |
| `DETAILS_FETCH_LIMIT` | `8` | сколько карточек догружать для проверки возраста |
| `DEFAULT_ORDERING` | `-rating` | сортировка подборки |
| `HTTP_TIMEOUT` | `10` | таймаут запросов к внешним API, секунд |
| `CACHE_TTL_SECONDS` | `600` | время жизни кэша справочников и карточек |
