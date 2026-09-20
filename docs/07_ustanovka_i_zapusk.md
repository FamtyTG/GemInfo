# 07. Установка и запуск проекта

Пошаговая инструкция: от чистой машины до работающего бота.

---

## Шаг 1. Установить Python 3.10+

```bash
python --version   # ожидается Python 3.10.x или новее
```

Windows: <https://www.python.org/downloads/> (при установке отметьте **Add Python to PATH**).

## Шаг 2. Установить Git

* Скачать: <https://git-scm.com/>
* Полезное расширение для VS Code — **Git Graph**:
  <https://marketplace.visualstudio.com/items?itemName=mhutchie.git-graph>
* Зарегистрироваться на <https://github.com> (сюда будем пушить проект).

```bash
git --version
git config --global user.name "Ваше Имя"
git config --global user.email "ваша@почта"
```

## Шаг 3. Получить код и установить зависимости

```bash
git clone <адрес репозитория>
cd GemInfo

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt        # telebot, requests, SQLAlchemy, psycopg2, dotenv
pip install -r requirements-dev.txt    # + pytest
```

## Шаг 4. Создать Telegram-бота и получить токен

1. Откройте [@BotFather](https://t.me/BotFather);
2. отправьте `/newbot`;
3. придумайте имя (`TravelHunter`) и username (`travelhunter_bot`);
4. скопируйте выданный токен — он понадобится в `.env`.

Полезные команды BotFather: `/setdescription` (описание), `/setuserpic` (аватар),
`/mybots` → *API Token* (показать токен ещё раз).

## Шаг 5. Получить ключи внешних API

### Ninjas API (праздники)

1. Регистрация: <https://api-ninjas.com/>;
2. личный кабинет → **API Key**;
3. значение записать в `NINJAS_API_KEY`.

### GeoNames (города)

1. Регистрация: <https://www.geonames.org/login>;
2. после подтверждения e-mail откройте <https://www.geonames.org/manageaccount>;
3. нажмите **Enable** напротив «Free Web Services» (без этого API отвечает ошибкой
   `user account not enabled`);
4. логин записать в `GEONAMES_USERNAME`.

### Wikipedia

Ключ не требуется.

## Шаг 6. Подготовить базу данных

### Вариант А. PostgreSQL в Docker (быстрее всего)

```bash
docker compose up -d
```

Команда поднимет PostgreSQL 16 с базой `travelhunter`, пользователем `postgres`
и паролем `postgres` (значения заданы в `docker-compose.yml` и совпадают
с `.env.example`).

### Вариант Б. Локальный PostgreSQL

```bash
psql -U postgres -c "CREATE DATABASE travelhunter;"
```

### Вариант В. Без PostgreSQL (только для разработки)

Если `DATABASE_URL` не задан, бот использует файл `travelhunter.db` (SQLite).
Таблицы создаются автоматически. Для сдачи проекта используйте PostgreSQL.

## Шаг 7. Заполнить `.env`

```bash
cp .env.example .env
```

```ini
BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/travelhunter
NINJAS_API_KEY=ваш_ключ_ninjas
GEONAMES_USERNAME=ваш_логин_geonames
```

> Файл `.env` **не коммитится**: он перечислен в `.gitignore`. В репозиторий
> попадает только шаблон `.env.example`.

## Шаг 8. Создать таблицы и запустить бота

```bash
python -m scripts.init_db --demo   # таблицы + 6 демо-поездок (необязательно)
python run.py
```

Успешный запуск выглядит так:

```
2026-08-10 12:00:00 | INFO | travelhunter.infrastructure.db.database | Движок базы данных создан: postgresql+psycopg2://postgres:***@localhost:5432/travelhunter
2026-08-10 12:00:00 | INFO | travelhunter.infrastructure.db.database | Таблицы базы данных созданы/проверены
2026-08-10 12:00:00 | INFO | travelhunter.app | Приложение TravelHunter собрано
2026-08-10 12:00:01 | INFO | travelhunter.presentation.handlers | Обработчики Telegram зарегистрированы
2026-08-10 12:00:01 | INFO | travelhunter.app | Telegram-бот TravelHunter запущен. Для остановки нажмите Ctrl+C
```

Остановка — `Ctrl+C`.

## Шаг 9. Проверить бота в Telegram

1. Откройте своего бота по ссылке `https://t.me/<username>`;
2. нажмите **Старт** или отправьте `/start`;
3. пройдите сценарии: праздники → ввод города → выбор города → история → заметка.

## Шаг 10. Запустить тесты

```bash
pytest          # 198 тестов, интернет и Telegram не нужны
pytest -v
```

---

## Возможные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `[ОШИБКА НАСТРОЙКИ] Не задан BOT_TOKEN` | нет файла `.env` | `cp .env.example .env` и заполнить |
| `A request to the Telegram API was unsuccessful… 401 Unauthorized` | неверный токен | получить новый токен у @BotFather |
| `conflict: terminated by other getUpdates request` | бот запущен дважды | остановить второй процесс |
| «Не удалось получить список праздников» | не задан или неверен `NINJAS_API_KEY` | проверить ключ в личном кабинете Ninjas |
| «Не удалось найти город» + `user account not enabled` в логе | GeoNames не активирован | включить Free Web Services в настройках аккаунта |
| «Не удалось найти город» + `daily limit of credits exceeded` | исчерпан дневной лимит GeoNames | дождаться следующего дня или использовать другой аккаунт |
| Ошибка подключения к PostgreSQL | база не запущена / неверный `DATABASE_URL` | `docker compose up -d`, проверить логин, пароль, порт, имя базы |
| `ModuleNotFoundError: No module named 'telebot'` | не активировано виртуальное окружение | `source .venv/bin/activate` и `pip install -r requirements.txt` |

## Диагностика при запуске

При старте бот пишет в лог предупреждения о незаполненных ключах:

```
WARNING | Не задан NINJAS_API_KEY — экран «Праздники на 7 дней» покажет сообщение об ошибке.
WARNING | Не задан GEONAMES_USERNAME — экран «Города куда съездить» покажет сообщение об ошибке.
```

Уровень логирования настраивается переменной `LOG_LEVEL` (`DEBUG` — подробнее).
