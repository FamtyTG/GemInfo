# Короткие команды для работы с проектом GameHunter
# Запуск: make <цель>   (список целей — make help)

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip

.PHONY: help install install-dev init-db demo run test mockups ae-assets lint clean

help:
	@echo "Доступные команды:"
	@echo "  make install      - установить основные зависимости"
	@echo "  make install-dev  - установить зависимости для разработки (pytest)"
	@echo "  make init-db      - создать таблицы базы данных"
	@echo "  make demo         - создать таблицы и добавить демонстрационные данные"
	@echo "  make run          - запустить Telegram-бота"
	@echo "  make test         - запустить тесты"
	@echo "  make mockups      - перегенерировать SVG-мокапы экранов"
	@echo "  make ae-assets    - собрать карточки и слои для After Effects (docs/ae)"
	@echo "  make lint         - проверить синтаксис всех файлов проекта"
	@echo "  make clean        - удалить кэш Python и локальную базу SQLite"

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

init-db:
	$(PYTHON) -m scripts.init_db

demo:
	$(PYTHON) -m scripts.init_db --demo

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m pytest

mockups:
	$(PYTHON) -m scripts.generate_mockups

ae-assets:
	$(PYTHON) scripts/generate_ae_assets.py

lint:
	$(PYTHON) -m compileall -q gamehunter tests scripts run.py

clean:
	rm -rf .pytest_cache gamehunter.db
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
