"""Тесты композиционного корня, шлюза Telegram и точки входа."""

from __future__ import annotations

import logging

import pytest
from telebot.apihelper import ApiTelegramException

from gamehunter import __project__, __version__
from gamehunter.app import (
    LOG_FORMAT,
    Application,
    build_application,
    configure_logging,
    main,
)
from gamehunter.config import Settings
from gamehunter.domain.exceptions import ConfigError, DatabaseError
from gamehunter.domain.services import GameService, LibraryService, ProfileService
from gamehunter.infrastructure.api import IpLocationClient, JsonHttpClient, RawgClient
from gamehunter.infrastructure.db import Database, SqlLibraryRepository, SqlProfileRepository
from gamehunter.presentation.gateway import MESSAGE_MAX_LENGTH, TelegramGateway
from gamehunter.presentation.handlers import BotHandlers
from gamehunter.presentation.keyboards import CallbackAction
from gamehunter.presentation.screens import ScreenContainer
from gamehunter.presentation.state import StateStorage


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Окружение для сборки приложения (SQLite, ключ каталога задан)."""
    monkeypatch.setenv("BOT_TOKEN", "123456789:TEST")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("RAWG_API_KEY", "test-key")
    monkeypatch.setenv("MAX_GAMES", "4")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    return monkeypatch


@pytest.fixture()
def application(env) -> Application:
    app = Application(Settings.from_env(env_file=None))
    try:
        yield app
    finally:
        app.stop()


# ---------------------------------------------------------------------- #
# Метаданные проекта
# ---------------------------------------------------------------------- #
class TestPackage:
    def test_project_name(self):
        assert __project__ == "GameHunter"

    def test_version_is_semver(self):
        major, minor, patch = __version__.split(".")

        assert int(major) >= 2
        assert int(minor) >= 0
        assert int(patch) >= 0


# ---------------------------------------------------------------------- #
# Логирование
# ---------------------------------------------------------------------- #
class TestLogging:
    @pytest.fixture(autouse=True)
    def _restore_root_level(self):
        """Возвращаем исходный уровень корневого логгера после теста."""
        original = logging.getLogger().level
        yield
        logging.getLogger().setLevel(original)

    def test_configures_root_logger(self):
        configure_logging("DEBUG")

        assert logging.getLogger().level == logging.DEBUG

    def test_unknown_level_falls_back_to_info(self):
        configure_logging("НЕТ-ТАКОГО-УРОВНЯ")

        assert logging.getLogger().level == logging.INFO

    def test_telebot_logger_is_quiet(self):
        configure_logging("DEBUG")

        assert logging.getLogger("telebot").level == logging.WARNING

    def test_log_format_mentions_level_and_module(self):
        assert "%(levelname)" in LOG_FORMAT
        assert "%(name)s" in LOG_FORMAT


# ---------------------------------------------------------------------- #
# Сборка приложения
# ---------------------------------------------------------------------- #
class TestApplicationAssembly:
    def test_infrastructure_layer(self, application: Application):
        assert isinstance(application.database, Database)
        assert isinstance(application.games_provider, RawgClient)
        assert isinstance(application.ip_provider, IpLocationClient)
        assert isinstance(application.profile_repository, SqlProfileRepository)
        assert isinstance(application.library_repository, SqlLibraryRepository)

    def test_domain_layer(self, application: Application):
        assert isinstance(application.game_service, GameService)
        assert isinstance(application.profile_service, ProfileService)
        assert isinstance(application.library_service, LibraryService)

    def test_presentation_layer(self, application: Application):
        assert isinstance(application.gateway, TelegramGateway)
        assert isinstance(application.storage, StateStorage)
        assert isinstance(application.screens, ScreenContainer)
        assert isinstance(application.handlers, BotHandlers)

    def test_settings_are_applied(self, application: Application):
        assert application.game_service.max_games == 4
        assert application.games_provider.is_configured is True
        assert application.library_service.page_size == 5
        assert application.library_service.note_max_length == 1000

    def test_tables_are_created(self, application: Application, tmp_path):
        assert (tmp_path / "app.db").exists()

    def test_all_screens_are_present(self, application: Application):
        assert len(application.screens.__dataclass_fields__) == 17

    def test_all_callback_actions_are_routed(self, application: Application):
        actions = {
            value
            for name, value in vars(CallbackAction).items()
            if not name.startswith("_") and isinstance(value, str)
        }

        assert actions == set(application.handlers._callback_routes)  # noqa: SLF001

    def test_age_policy_is_shared_between_services(self, application: Application):
        assert application.game_service.age_policy is application.profile_service.age_policy

    def test_build_application(self, env):
        app = build_application(env_file=None)
        try:
            assert isinstance(app, Application)
        finally:
            app.stop()

    def test_missing_token_raises_config_error(self, env):
        env.delenv("BOT_TOKEN")

        with pytest.raises(ConfigError):
            Application(Settings.from_env(env_file=None))

    def test_broken_database_url_raises_database_error(self, env, tmp_path):
        env.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'нет' / 'такой' / 'папки' / 'app.db'}")

        with pytest.raises(DatabaseError):
            Application(Settings.from_env(env_file=None))


class TestApplicationRun:
    def test_run_registers_handlers_and_starts_polling(self, application: Application, monkeypatch):
        started = []
        monkeypatch.setattr(
            application.bot,
            "infinity_polling",
            lambda *args, **kwargs: started.append((args, kwargs)),
        )

        application.run()

        assert started
        assert application.bot.message_handlers
        assert application.bot.callback_query_handlers

    def test_stop_is_safe_twice(self, application: Application, monkeypatch):
        monkeypatch.setattr(application.bot, "stop_polling", lambda: None)

        application.stop()
        application.stop()

    def test_stop_ignores_polling_errors(self, application: Application, monkeypatch):
        def boom():
            raise RuntimeError("опрос уже остановлен")

        monkeypatch.setattr(application.bot, "stop_polling", boom)

        application.stop()  # не должно вызывать исключение


# ---------------------------------------------------------------------- #
# Точка входа
# ---------------------------------------------------------------------- #
class TestMain:
    def test_missing_token_exits_with_error(self, monkeypatch, capsys):
        monkeypatch.setenv("BOT_TOKEN", "")
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(SystemExit) as info:
            main()

        assert info.value.code == 1
        assert "ОШИБКА НАСТРОЙКИ" in capsys.readouterr().err

    def test_database_error_exits(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("BOT_TOKEN", "123456789:TEST")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'нет' / 'папки' / 'app.db'}")

        with pytest.raises(SystemExit) as info:
            main()

        assert info.value.code == 1
        assert "ОШИБКА БАЗЫ ДАННЫХ" in capsys.readouterr().err

    def test_successful_start_and_stop(self, env, monkeypatch):
        created = []
        stopped = []

        class FakeApplication(Application):
            def __init__(self, settings):
                super().__init__(settings)
                created.append(self)

            def run(self):
                raise KeyboardInterrupt

            def stop(self):
                stopped.append(self)
                super().stop()

        monkeypatch.setattr("gamehunter.app.Application", FakeApplication)

        main()

        assert len(created) == 1
        assert stopped == created

    def test_unexpected_startup_error_exits(self, env, monkeypatch, capsys):
        class BrokenApplication(Application):
            def __init__(self, settings):
                raise ConfigError("не удалось собрать приложение")

        monkeypatch.setattr("gamehunter.app.Application", BrokenApplication)

        with pytest.raises(SystemExit) as info:
            main()

        assert info.value.code == 1
        assert "ОШИБКА ЗАПУСКА" in capsys.readouterr().err


# ---------------------------------------------------------------------- #
# Шлюз Telegram
# ---------------------------------------------------------------------- #
class FakeBot:
    """Подставной объект TeleBot для проверки шлюза."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent = []
        self.photos = []
        self.answers = []

    def send_message(self, chat_id, text, reply_markup=None):
        if self.error is not None:
            raise self.error
        self.sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup})

    def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        if self.error is not None:
            raise self.error
        self.photos.append({"chat_id": chat_id, "photo": photo, "caption": caption})

    def answer_callback_query(self, callback_id, text=None):
        if self.error is not None:
            raise self.error
        self.answers.append({"id": callback_id, "text": text})


class TestTelegramGateway:
    @pytest.fixture()
    def bot(self) -> FakeBot:
        return FakeBot()

    @pytest.fixture()
    def gateway(self, bot: FakeBot) -> TelegramGateway:
        return TelegramGateway(bot)

    def test_send_text(self, gateway: TelegramGateway, bot: FakeBot):
        assert gateway.send_text(100, "Привет") is True
        assert bot.sent[0]["chat_id"] == 100
        assert bot.sent[0]["text"] == "Привет"

    def test_send_text_with_markup(self, gateway: TelegramGateway, bot: FakeBot):
        markup = object()

        gateway.send_text(100, "Текст", reply_markup=markup)

        assert bot.sent[0]["markup"] is markup

    def test_long_text_is_truncated(self, gateway: TelegramGateway, bot: FakeBot):
        gateway.send_text(100, "с" * 5000)

        text = bot.sent[0]["text"]
        assert len(text) == MESSAGE_MAX_LENGTH
        assert text.endswith("…")

    def test_exact_limit_is_not_truncated(self, gateway: TelegramGateway, bot: FakeBot):
        gateway.send_text(100, "с" * MESSAGE_MAX_LENGTH)

        assert bot.sent[0]["text"] == "с" * MESSAGE_MAX_LENGTH

    def test_send_text_api_error(self, bot: FakeBot):
        bot.error = ApiTelegramException(
            "sendMessage",
            {"ok": False},
            {"error_code": 403, "description": "bot was blocked by the user"},
        )
        gateway = TelegramGateway(bot)

        assert gateway.send_text(100, "Текст") is False

    def test_send_text_unexpected_error(self):
        gateway = TelegramGateway(FakeBot(error=RuntimeError("сбой")))

        assert gateway.send_text(100, "Текст") is False

    def test_send_photo(self, gateway: TelegramGateway, bot: FakeBot):
        assert gateway.send_photo(100, "https://cdn/img.jpg", "Обложка") is True
        assert bot.photos[0]["photo"] == "https://cdn/img.jpg"
        assert bot.photos[0]["caption"] == "Обложка"

    def test_send_photo_error(self):
        gateway = TelegramGateway(FakeBot(error=RuntimeError("сбой")))

        assert gateway.send_photo(100, "https://cdn/img.jpg", "Обложка") is False

    def test_answer_callback(self, gateway: TelegramGateway, bot: FakeBot):
        class Call:
            id = "callback-1"

        gateway.answer_callback(Call(), "Готово")

        assert bot.answers == [{"id": "callback-1", "text": "Готово"}]

    def test_answer_callback_without_text(self, gateway: TelegramGateway, bot: FakeBot):
        class Call:
            id = "callback-2"

        gateway.answer_callback(Call())

        assert bot.answers[0]["text"] is None

    def test_answer_callback_with_none(self, gateway: TelegramGateway, bot: FakeBot):
        gateway.answer_callback(None)

        assert bot.answers == []

    def test_answer_callback_error_is_ignored(self):
        gateway = TelegramGateway(FakeBot(error=RuntimeError("сбой")))

        class Call:
            id = "callback-3"

        gateway.answer_callback(Call())  # не должно вызывать исключение
