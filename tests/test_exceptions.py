"""Тесты исключений: у каждой ошибки есть понятный текст для пользователя."""

from __future__ import annotations

import pytest

from gamehunter.domain.exceptions import (
    ConfigError,
    DatabaseError,
    EmptyReviewError,
    ExternalServiceError,
    FavoriteAlreadyExistsError,
    FavoriteNotFoundError,
    FranchiseNotFoundError,
    FranchiseSearchUnavailableError,
    GameAlreadyPlayedError,
    GameHunterError,
    GameInfoUnavailableError,
    GameNotFoundError,
    GamesUnavailableError,
    GenresUnavailableError,
    InvalidAgeError,
    InvalidIpError,
    NoGamesFoundError,
    PlayedGameNotFoundError,
    PrivateIpError,
    RegionUnavailableError,
    ReviewTooLongError,
)

ALL_ERRORS = [
    ConfigError,
    DatabaseError,
    EmptyReviewError,
    ExternalServiceError,
    FavoriteAlreadyExistsError,
    FavoriteNotFoundError,
    FranchiseNotFoundError,
    FranchiseSearchUnavailableError,
    GameAlreadyPlayedError,
    GameInfoUnavailableError,
    GameNotFoundError,
    GamesUnavailableError,
    GenresUnavailableError,
    InvalidAgeError,
    InvalidIpError,
    NoGamesFoundError,
    PlayedGameNotFoundError,
    PrivateIpError,
    RegionUnavailableError,
]


class TestHierarchy:
    @pytest.mark.parametrize("error", ALL_ERRORS)
    def test_all_errors_inherit_base_error(self, error):
        assert issubclass(error, GameHunterError)
        assert issubclass(error, Exception)

    def test_private_ip_is_invalid_ip(self):
        assert issubclass(PrivateIpError, InvalidIpError)

    @pytest.mark.parametrize(
        "error",
        [
            ExternalServiceError,
            GamesUnavailableError,
            GameInfoUnavailableError,
            GenresUnavailableError,
            FranchiseSearchUnavailableError,
            RegionUnavailableError,
        ],
    )
    def test_service_errors_inherit_external_service_error(self, error):
        assert issubclass(error, ExternalServiceError)


class TestUserMessages:
    @pytest.mark.parametrize("error", ALL_ERRORS)
    def test_every_error_has_non_empty_user_message(self, error):
        message = error().user_message

        assert isinstance(message, str)
        assert message.strip()

    @pytest.mark.parametrize("error", ALL_ERRORS)
    def test_user_message_is_written_for_people(self, error):
        message = error().user_message

        # Текст сообщения не должен содержать технических деталей
        assert "Traceback" not in message
        assert message != repr(error())

    def test_base_error_message(self):
        assert "Попробуйте ещё раз позже" in GameHunterError().user_message

    def test_config_error_mentions_env_file(self):
        assert ".env" in ConfigError().user_message

    def test_invalid_ip_message_gives_example(self):
        message = InvalidIpError().user_message

        assert "8.8.8.8" in message
        assert "2ip.ru" in message

    def test_private_ip_message_explains_problem(self):
        message = PrivateIpError().user_message

        assert "локальный" in message
        assert "публичный" in message

    def test_invalid_age_message_mentions_bounds(self):
        message = InvalidAgeError().user_message

        assert "3" in message
        assert "120" in message

    def test_no_games_found_message_suggests_action(self):
        message = NoGamesFoundError().user_message

        assert message.strip()
        assert len(message) > 20

    def test_franchise_not_found_message_gives_examples(self):
        message = FranchiseNotFoundError().user_message

        assert "Marvel" in message or "Star Wars" in message

    def test_game_already_played_message(self):
        assert "уже есть" in GameAlreadyPlayedError().user_message

    def test_favorite_errors_messages(self):
        assert "избранное" in FavoriteAlreadyExistsError().user_message
        assert "избранном" in FavoriteNotFoundError().user_message

    def test_database_error_message(self):
        assert "базой данных" in DatabaseError().user_message


class TestExternalServiceError:
    def test_stores_service_and_reason(self):
        error = ExternalServiceError("rawg", "timeout")

        assert error.service == "rawg"
        assert error.reason == "timeout"
        assert "rawg" in str(error)
        assert "timeout" in str(error)

    def test_str_without_details_falls_back_to_class_name(self):
        error = ExternalServiceError()

        assert str(error) == "ExternalServiceError"

    def test_str_with_service_only(self):
        assert str(ExternalServiceError("ipapi")) == "ipapi"

    def test_subclass_keeps_service_and_reason(self):
        error = GamesUnavailableError("rawg", "500")

        assert error.service == "rawg"
        assert error.reason == "500"
        assert error.user_message == GamesUnavailableError.user_message


class TestReviewErrors:
    def test_review_too_long_default_limit(self):
        error = ReviewTooLongError()

        assert error.limit == 1000
        assert "1000" in error.user_message

    def test_review_too_long_custom_limit(self):
        error = ReviewTooLongError(140)

        assert error.limit == 140
        assert "140" in error.user_message
        assert "1000" not in error.user_message

    def test_review_too_long_message_asks_to_shorten(self):
        assert "Сократите" in ReviewTooLongError().user_message

    def test_empty_review_message(self):
        assert "не может быть пустым" in EmptyReviewError().user_message

    def test_played_game_not_found_message_mentions_list(self):
        assert "Во что я играл" in PlayedGameNotFoundError().user_message

    def test_game_not_found_message(self):
        assert "не найдена" in GameNotFoundError().user_message
