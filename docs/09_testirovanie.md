# 09. Тестирование проекта

## Запуск тестов

```bash
make test                          # все тесты
python -m pytest                   # то же самое
python -m pytest -q tests/test_bot_flow.py     # только сквозные сценарии
python -m pytest -q tests/test_game_service.py # только один модуль
python -m pytest -k "age" -q                   # тесты, в названии которых есть «age»
python -m pytest --collect-only -q | tail -1   # сколько тестов в проекте
```

Настройки pytest заданы в `pytest.ini`:

```ini
[pytest]
pythonpath = .        # корень проекта — чтобы импортировать gamehunter
testpaths = tests
addopts = -q
filterwarnings =
    ignore::DeprecationWarning
```

**Тесты не требуют интернета и PostgreSQL.** Внешние сервисы заменены
подставными объектами (`tests/fakes.py`), база данных — SQLite во временной
папке (`tmp_path`), Telegram — `FakeGateway` и `FakeBot`. Полный прогон занимает
около 10 секунд.

## Состав тестов

| Модуль | Тестов | Что проверяет |
|--------|--------|---------------|
| `test_mockups.py` | 242 | генератор мокапов: 17 экранов, SVG-разметка, соответствие текстов и кнопок коду бота, актуальность файлов в `docs/mockups/` |
| `test_screens.py` | 126 | все 17 экранов: текст, кнопки, переходы, состояние контекста, ошибки |
| `test_keyboards.py` | 92 | подписи кнопок, состав клавиатур, схема callback-данных и её разбор |
| `test_rawg_client.py` | 86 | разбор ответов RAWG: жанры, платформы, поиск игр, карточка, франшизы, ошибки |
| `test_exceptions.py` | 84 | иерархия исключений, `user_message` для каждой ошибки |
| `test_handlers.py` | 82 | регистрация обработчиков, все 28 callback-маршрутов, ввод текста, ошибки, игнорирование «мусора» |
| `test_game_service.py` | 73 | подбор игр: фильтры, слияние с анкетой, возрастной фильтр, исключение сыгранных, пагинация, кэш |
| `test_age_ratings.py` | 73 | `AgePolicy`: ESRB, PEGI, неизвестные рейтинги, граница возраста |
| `test_profile_service.py` | 68 | анкета: возраст, интересы, платформы, извлечение и проверка IP, определение региона |
| `test_repositories.py` | 65 | `Database`, схема таблиц (колонки, уникальность, индексы), оба SQL-репозитория |
| `test_state.py` | 63 | `ContextScreen`, `UserContext` (переходы, неизменяемость), `StateStorage` |
| `test_texts.py` | 61 | тексты сообщений и функции форматирования, ограничение Telegram 4096 символов |
| `test_entities.py` | 59 | все 12 сущностей: поля, свойства, форматирование дат и рейтингов |
| `test_library_service.py` | 58 | сыгранные игры, отзывы, удаление, избранное, пагинация библиотеки |
| `test_bot_flow.py` | 48 | сквозные сценарии использования (docs/02) «от /start до результата» |
| `test_app.py` | 36 | логирование, сборка приложения по слоям, запуск и остановка, `main`, `TelegramGateway` |
| `test_config.py` | 28 | `Settings.from_env`: переменные окружения, `.env`, значения по умолчанию, ошибки |
| `test_ip_location_client.py` | 25 | форматы ipapi.co и ipwho.is, ошибки сервиса, пустые ответы |
| `test_init_db.py` | 21 | скрипт инициализации базы: таблицы, демо-данные, идемпотентность, CLI |
| `test_http_client.py` | 19 | HTTP-клиент: таймаут, коды ответа, JSON, `allow_404`, ошибки |
| **Всего** | **1409** | |

Инфраструктура тестов:

| Файл | Назначение |
|------|------------|
| `tests/fakes.py` | `FakeGamesProvider`, `FakeIpProvider`, `InMemoryProfileRepository`, `InMemoryLibraryRepository`, `FakeSession`/`FakeResponse` (подмена `requests`), `FakeGateway`, фабрики сущностей (`make_game`, `make_details`, `make_profile`, `make_played` …), `default_provider` — каталог из 7 игр |
| `tests/conftest.py` | фикстуры: `database` (SQLite в `tmp_path`), репозитории, сервисы, `games_provider`, `ip_provider`, `gateway`, `storage`, `screens` (все 17 экранов), `bot`, `handlers` |

## Что именно проверяется по слоям

### Доменный слой (бизнес-правила)

* **`AgePolicy`**: ESRB (EC → 3, E → 6, E10+ → 10, T → 13, M → 17, AO → 18),
  PEGI (число в названии), неизвестный рейтинг → игра разрешена, отсутствие
  возраста у пользователя → фильтр не применяется.
* **`GameService`**: построение `GameQuery`, слияние с анкетой (жанры, платформы,
  возраст, исключение сыгранных), возрастной фильтр при догрузке карточек,
  поведение при «все игры не по возрасту» (`NoGamesFoundError`), пагинация,
  кэш справочников и карточек (`clear_cache`), поиск франшиз и их игр.
* **`ProfileService`**: валидация возраста (3–120, «27 лет», «-5», «много»),
  извлечение IP из произвольного текста, отклонение локальных адресов,
  сохранение региона, сброс полей анкеты.
* **`LibraryService`**: добавление сыгранной игры (повторно — `GameAlreadyPlayedError`),
  проверка длины отзыва (`ReviewTooLongError`), удаление записи, избранное
  (`toggle_favorite` возвращает пару «запись + добавлено/убрано»), пагинация.
* **Исключения**: у каждой ошибки есть непустой `user_message`, наследование
  соответствует схеме (`PrivateIpError` → `InvalidIpError` → `GameHunterError`).

### Слой инфраструктуры

* **`JsonHttpClient`**: таймаут и ошибка соединения → `ExternalServiceError`;
  коды 4xx/5xx → ошибка с кодом; 404 при `allow_404=True` → `None`; невалидный
  JSON → ошибка; параметры и заголовки передаются в `requests` без изменений.
* **`RawgClient`**: разбор реальных по форме ответов RAWG, включая вложенные
  `parent_platforms[].platform`, отсутствие `esrb_rating` в списке игр, ответ
  `{"detail": "Not found."}`, запасной перечень платформ при 404, добавление
  `key` и `language` ко всем запросам, ошибки → конкретные доменные исключения.
* **`IpLocationClient`**: оба формата ответов (ipapi.co и ipwho.is), ошибки
  сервиса (`error: true`, `success: false`), пустой ответ → `None`.
* **Репозитории и схема БД**: состав колонок, уникальность `tg_user_id` в анкете,
  уникальность пары (`tg_user_id`, `game_id`) в обеих библиотеках, индексы,
  commit/rollback в `session_scope`, `safe_url` скрывает пароль, ошибки
  SQLAlchemy → `DatabaseError`, чужие записи недоступны.

### Слой представления

* **Тексты**: каждое сообщение содержит ожидаемые данные (название игры,
  рейтинг, filters-строку, номер страницы), ни одно сообщение не длиннее 4096
  символов, пустые значения показываются как «не указан» / «не определён».
* **Клавиатуры**: состав рядов и подписи, callback-данные каждой кнопки,
  `parse_callback` для всех 28 действий, неполные данные (`game:`) → `None`.
* **Состояние**: `UserContext` неизменяем, переходы (`at_game_card`,
  `at_franchise_games`, `back_to_list` …) меняют только нужные поля,
  `is_waiting_for_text()` верно определяет 4 экрана ввода.
* **Экраны**: текст и кнопки каждого экрана, сохранение контекста, переходы,
  поведение при потере состояния (`state_lost`), ошибки домена → `user_message`.
* **Обработчики**: регистрация `/start`, callback, текста и
  `UNSUPPORTED_CONTENT_TYPES`; все действия `CallbackAction` покрыты маршрутами;
  `safe_handler` отправляет `user_message` доменной ошибки и `GENERIC_ERROR` для
  неожиданной; сообщения без `chat`/`from_user` игнорируются.
* **Шлюз**: обрезка текста до 4096 символов с многоточием, ошибки Telegram API
  возвращают `False` и не роняют бота, ответ на callback без текста.
* **Сборка приложения**: `Application` связывает все три слоя, настройки
  применяются к сервисам, таблицы создаются, все 17 экранов присутствуют,
  `main` завершается с кодом 1 при ошибке настроек или базы данных.

## Пример сквозного теста

`tests/test_bot_flow.py` — сценарий «подбор игры по интересам»:

```python
class TestScenarioPicking:
    def test_full_path(self, flow, gateway, storage, library_service):
        # Экран 2 → Экран 3: выбор интересов
        message = flow(text=ButtonText.PICK)
        assert texts.GENRES_TITLE in message

        message = flow(callback="g:action")
        assert "✔ Action" in message

        # Экран 4: подборка игр
        message = flow(callback=CallbackAction.PICK_SHOW)
        assert texts.GAMES_TITLE in message
        assert storage.get(USER_ID).screen == ContextScreen.GAME_LIST

        # Экран 5: карточка первой игры
        first_game = storage.get(USER_ID).games[0]
        message = flow(callback=f"game:{first_game.id}")
        assert first_game.name in message

        # Отмечаем игру как сыгранную и пишем отзыв
        flow(callback=f"played:{first_game.id}")
        assert library_service.is_played(USER_ID, first_game.id) is True

        flow(text=ButtonText.PLAYED)                       # Экран 10
        record_id = storage.get(USER_ID).records[0]
        flow(callback=f"rec:{record_id}")                  # Экран 11
        flow(callback=f"rev:{record_id}")                  # Экран 11а
        message = flow(text="Прошёл на 100%, отличный сюжет.")

        assert texts.REVIEW_SAVED in message
```

Фикстура `flow` имитирует действия пользователя: отправляет сообщения и нажатия
кнопок настоящим обработчикам и возвращает последний текст бота. Проверяются
и текст ответа, и сохранённое состояние, и данные в базе.

Сквозные тесты покрывают все девять сценариев из
[02_scenarii_ispolzovaniya.md](02_scenarii_ispolzovaniya.md), включая ошибки
внешних сервисов и базы данных: после любой ошибки бот продолжает отвечать.

## Ручное тестирование

Автоматические тесты не проверяют реальное общение с Telegram и RAWG, поэтому
перед сдачей проекта пройдите чек-лист из 24 пунктов в
[08_plan_proekta.md](08_plan_proekta.md) (раздел «Чек-лист ручного тестирования»)
с настоящим ботом и настоящим ключом каталога.

## Качество кода

| Проверка | Команда | Что делает |
|----------|---------|------------|
| Синтаксис всех модулей | `make lint` | `python -m compileall -q gamehunter tests scripts run.py` |
| Тесты | `make test` | полный прогон pytest |
| Актуальность мокапов | `python -m pytest tests/test_mockups.py -k up_to_date` | сравнивает файлы в `docs/mockups/` с результатом генератора |
| Отсутствие секретов в коде | `grep -rn "api_key =" gamehunter/` | показывает только чтение значения из настроек |

Принципы, которых придерживается проект:

* каждая ошибка пользователя имеет собственный тип исключения и готовый текст;
* ни один внешний вызов не остаётся без обработки — исключение преобразуется в
  доменное на границе слоя;
* тесты проверяют поведение, а не реализацию: подставные провайдеры возвращают
  данные той же формы, что и настоящие API;
* новые экраны и сервисы добавляются вместе с тестами и обновлением мокапов
  (`make mockups`).
