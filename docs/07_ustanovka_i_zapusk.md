# 07. Установка и запуск проекта

Инструкция рассчитана на «чистую» машину: Python, Git, Docker (по желанию) и
аккаунт в Telegram. Все команды выполняются из корня проекта.

```bash
git clone <адрес-репозитория> GemInfo
cd GemInfo
```

## Шаг 1. Установить Python 3.10+

Проект написан на Python 3.10 и новее (разработка велась на 3.11).

```bash
python3 --version     # ожидается Python 3.10.x или новее
```

* Windows: установщик с <https://www.python.org/downloads/>, при установке
  отметьте **Add Python to PATH**.
* macOS: `brew install python@3.11`.
* Linux (Debian/Ubuntu): `sudo apt install python3 python3-venv python3-pip`.

## Шаг 2. Установить Git

```bash
git --version
```

* Windows: <https://git-scm.com/download/win>
* macOS: `xcode-select --install` или `brew install git`
* Linux: `sudo apt install git`

## Шаг 3. Создать виртуальное окружение и установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt          # основные зависимости
pip install -r requirements-dev.txt      # + pytest для тестов
```

Состав `requirements.txt`:

| Пакет | Зачем |
|-------|-------|
| `pyTelegramBotAPI` (telebot) | взаимодействие с Telegram Bot API |
| `requests` | HTTP-запросы к RAWG и сервису геолокации |
| `SQLAlchemy` 2.0 | ORM для работы с базой данных |
| `psycopg2-binary` | драйвер PostgreSQL |
| `python-dotenv` | загрузка настроек из файла `.env` |

## Шаг 4. Создать Telegram-бота и получить токен

1. Откройте в Telegram [@BotFather](https://t.me/BotFather).
2. Отправьте `/newbot`.
3. Придумайте имя (например, `GameHunter`) и username (например,
   `game_hunter_bot`) — username должен заканчиваться на `bot`.
4. BotFather выдаст токен вида `1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.

Токен — это секрет: не публикуйте его и не добавляйте в Git.

## Шаг 5. Получить ключ внешнего API

### RAWG Video Games Database (каталог игр)

1. Зарегистрируйтесь на <https://rawg.io> (бесплатно).
2. Откройте профиль → **API Key** (<https://rawg.io/profile/api>).
3. Скопируйте ключ — он понадобится в переменной `RAWG_API_KEY`.

### Сервис геолокации по IP

Ключ не требуется: используется <https://ipapi.co> (бесплатно, около 1000
запросов в сутки). При необходимости в `.env` можно указать запасной сервис
<https://ipwho.is> — клиент понимает оба формата ответов.

## Шаг 6. Подготовить базу данных

### Вариант А. PostgreSQL в Docker (рекомендуется)

```bash
docker compose up -d
```

Команды из `docker-compose.yml`:

| Сервис | Что делает | Адрес |
|--------|------------|-------|
| `postgres` (postgres:16-alpine) | база `gamehunter`, пользователь `postgres`, пароль `postgres` | `localhost:5432` |
| `adminer` | веб-интерфейс для просмотра таблиц | <http://localhost:8080> |

Данные хранятся в volume `gamehunter_pgdata` и не теряются при перезапуске.
Остановка: `docker compose down` (данные сохранятся), полное удаление:
`docker compose down -v`.

### Вариант Б. Локальный PostgreSQL

```bash
sudo -u postgres psql -c "CREATE DATABASE gamehunter;"
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"
```

### Вариант В. Без PostgreSQL (только для разработки)

В `.env` укажите SQLite — таблицы создадутся в файле рядом с проектом:

```dotenv
DATABASE_URL=sqlite:///gamehunter.db
```

Тесты всегда работают на SQLite во временной папке, поэтому PostgreSQL для
проверки кода не нужен.

## Шаг 7. Заполнить `.env`

```bash
cp .env.example .env
```

Минимально необходимый набор:

```dotenv
BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/gamehunter
RAWG_API_KEY=ваш_ключ_RAWG
```

Необязательные настройки (значения по умолчанию уже заданы в `.env.example`):
`IP_LOCATION_BASE_URL`, `CATALOG_LANGUAGE`, `MAX_GAMES`, `MAX_GENRES`,
`MAX_FRANCHISES`, `DETAILS_FETCH_LIMIT`, `LIBRARY_PAGE_SIZE`,
`REVIEW_MAX_LENGTH`, `DEFAULT_ORDERING`, `HTTP_TIMEOUT`, `CACHE_TTL_SECONDS`,
`LOG_LEVEL`.

Файл `.env` добавлен в `.gitignore` — в репозиторий попадает только шаблон
`.env.example`.

## Шаг 8. Создать таблицы и запустить бота

```bash
python -m scripts.init_db          # создать таблицы user_profiles, played_games, favorite_games
python -m scripts.init_db --demo   # то же + демо-анкета, 3 сыгранные игры, 2 избранные
python run.py                      # запустить бота
```

Эквивалентные команды Makefile:

```bash
make init-db
make demo
make run
```

Успешный запуск выглядит так:

```
2026-09-20 18:41:02 | INFO     | gamehunter.app | Приложение GameHunter собрано
2026-09-20 18:41:02 | INFO     | gamehunter.app | Telegram-бот GameHunter запущен. Для остановки нажмите Ctrl+C
```

Остановка бота: `Ctrl+C` (опрос Telegram корректно завершается, соединения с
базой закрываются).

Демонстрационные данные создаются для пользователя с `tg_user_id = 111111111`
(параметр `--user-id` позволяет указать другой). Скрипт идемпотентен: повторный
запуск не создаёт дубликаты.

## Шаг 9. Проверить бота в Telegram

Откройте своего бота и нажмите **Start** (или отправьте `/start`):

| Что сделать | Ожидаемый результат |
|-------------|---------------------|
| `/start` | Экран 1 «Приветствие», затем главное меню |
| «Подобрать игру» → отметить 2 жанра → «Показать подборку» | Экран 4: список игр с рейтингом и годом выхода |
| «Выбрать игру 1» | Экран 5: карточка игры с обложкой, возрастным рейтингом и описанием |
| «Уже играл» | «Игра добавлена в список «Во что я играл».» |
| «Подобрать игру» → «Показать всё» | В подборке больше нет отмеченной игры и есть строка об исключении сыгранных |
| «Игры по франшизе» → отправить `Marvel` | Экран 7: найденные франшизы; выбор → Экран 8: игры франшизы |
| «Моя анкета» → «Указать возраст» → `13` | Экран 9: «Возраст: 13 лет»; в подборке не будет игр «17+» |
| «Моя анкета» → «Определить регион по IP» → отправить свой IP (с 2ip.ru) | Экран 9: регион, часовой пояс и валюта |
| «Во что я играл» → выбрать игру → «Написать отзыв» | Экран 11 с отзывом |
| «Избранное» | Экран 12: сохранённые игры |
| Отправить фото или стикер | Бот не отвечает (сообщение игнорируется) |
| Отключить RAWG-ключ и повторить подбор | «Не удалось получить список игр. Попробуйте ещё раз позже.» — бот не падает |

## Шаг 10. Запустить тесты

```bash
make test          # или: python -m pytest
python -m pytest -q tests/test_bot_flow.py    # только сквозные сценарии
python -m pytest --collect-only -q | tail -1  # сколько тестов в проекте
```

Тесты не требуют ни сети, ни PostgreSQL: внешние сервисы заменены подставными
объектами из `tests/fakes.py`, база данных — SQLite во временной папке.

## Шаг 11. Перегенерировать мокапы (по желанию)

```bash
make mockups       # или: python -m scripts.generate_mockups
```

SVG-мокапы всех 17 экранов появятся в `docs/mockups/`. Тексты и кнопки берутся
из модулей `texts.py` и `keyboards.py`, поэтому мокапы всегда соответствуют коду.
Если установлен `cairosvg`, дополнительно создаются PNG-версии.

## Все команды Makefile

| Команда | Что делает |
|---------|------------|
| `make help` | список доступных команд |
| `make install` | установить основные зависимости |
| `make install-dev` | установить зависимости для разработки (pytest) |
| `make init-db` | создать таблицы базы данных |
| `make demo` | создать таблицы и добавить демонстрационные данные |
| `make run` | запустить Telegram-бота |
| `make test` | запустить тесты |
| `make mockups` | перегенерировать SVG-мокапы экранов |
| `make lint` | проверить синтаксис всех файлов проекта (`compileall`) |
| `make clean` | удалить кэш Python и локальную базу SQLite |

## Возможные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `[ОШИБКА НАСТРОЙКИ] Не задан BOT_TOKEN…` | нет `.env` или пустой токен | `cp .env.example .env` и заполнить `BOT_TOKEN` |
| В логе `RAWG_API_KEY не задан — каталог игр недоступен` | нет ключа каталога | получить ключ на rawg.io и указать в `.env` (бот запускается, но подборка не работает) |
| В логе `DATABASE_URL не задан — используется локальный SQLite` | не указана строка подключения | это не ошибка: для разработки подойдёт SQLite, для продакшена укажите PostgreSQL |
| `A request to the Telegram API was unsuccessful. Error code: 401` | неверный токен бота | пересоздать токен у @BotFather |
| `A request to the Telegram API was unsuccessful. Error code: 409. Conflict: terminated by other getUpdates request` | бот запущен дважды | остановить второй процесс |
| `[ОШИБКА БАЗЫ ДАННЫХ] …` при запуске | PostgreSQL не запущен или неверный `DATABASE_URL` | `docker compose up -d`, проверить строку подключения |
| «Не удалось получить список игр…» в Telegram | ключ RAWG неверный или исчерпан лимит | проверить ключ и лимиты в профиле RAWG |
| «Не удалось определить регион по IP-адресу…» | исчерпан лимит ipapi.co или адрес локальный | попробовать позже, использовать публичный IP (2ip.ru) |
| `ModuleNotFoundError: No module named 'gamehunter'` | запуск не из корня проекта | `cd GemInfo` или `export PYTHONPATH=$(pwd)` |
| `error: externally-managed-environment` при `pip install` | системный Python защищён (PEP 668) | использовать виртуальное окружение `.venv` |
| Мокапы не сохраняются в PNG | не установлен `cairosvg` | `pip install cairosvg` (необязательно) |

## Диагностика при запуске

Бот пишет подробный лог в консоль. Уровень задаётся переменной `LOG_LEVEL`:

```dotenv
LOG_LEVEL=DEBUG
```

| Что искать в логе | О чём говорит |
|-------------------|---------------|
| `Экран 3 «Интересы» для пользователя 123` | какие экраны открывает пользователь |
| `RAWG_API_KEY не задан — каталог игр недоступен` | проблема с настройками |
| `Ошибка запроса к RAWG /games: http 401` | неверный ключ каталога |
| `Непредвиденная ошибка при поиске игр` | ошибка внутри сервиса домена (показывается трассировка) |
| `Экран GameListScreen: rawg timeout` | ошибка внешнего сервиса, перехваченная `safe_handler` |
| `Регион по IP 5.188.0.1: Kazan (RU), часовой пояс Europe/Moscow` | успешное определение региона |

Логи службы Telegram (`telebot`) ограничены уровнем WARNING, чтобы не мешать
чтению сообщений приложения.
