"""Тесты сервиса анкеты пользователя (возраст, интересы, платформы, регион по IP)."""

from __future__ import annotations

import pytest

from gamehunter.domain.age_ratings import AgePolicy
from gamehunter.domain.entities import Region
from gamehunter.domain.exceptions import (
    DatabaseError,
    InvalidAgeError,
    InvalidIpError,
    PrivateIpError,
    RegionUnavailableError,
)
from gamehunter.domain.services import ProfileService, extract_ip
from gamehunter.infrastructure.db import SqlProfileRepository
from tests.fakes import (
    FakeIpProvider,
    InMemoryProfileRepository,
    make_genre,
    make_platform,
    make_region,
)

USER_ID = 200


@pytest.fixture()
def repository() -> InMemoryProfileRepository:
    return InMemoryProfileRepository()


@pytest.fixture()
def ip_provider() -> FakeIpProvider:
    return FakeIpProvider(region=make_region())


@pytest.fixture()
def service(repository, ip_provider) -> ProfileService:
    return ProfileService(repository=repository, ip_provider=ip_provider)


# ---------------------------------------------------------------------- #
# Анкета
# ---------------------------------------------------------------------- #
class TestGetProfile:
    def test_creates_profile_on_first_access(self, service: ProfileService, repository):
        profile = service.get_profile(USER_ID)

        assert profile.tg_user_id == USER_ID
        assert profile.age is None
        assert profile.genre_slugs == ()
        assert USER_ID in repository.profiles

    def test_returns_saved_profile(self, service: ProfileService):
        service.set_age(USER_ID, "27")

        assert service.get_profile(USER_ID).age == 27

    def test_profiles_of_different_users_are_independent(self, service: ProfileService):
        service.set_age(200, "20")
        service.set_age(300, "40")

        assert service.get_profile(200).age == 20
        assert service.get_profile(300).age == 40

    def test_age_policy_is_available(self, service: ProfileService):
        assert isinstance(service.age_policy, AgePolicy)


class TestSetAge:
    @pytest.mark.parametrize(
        "raw, expected",
        [("27", 27), (" 30 ", 30), ("27 лет", 27), ("мне 18", 18), ("3", 3), ("120", 120)],
    )
    def test_valid_values(self, service: ProfileService, raw, expected):
        profile = service.set_age(USER_ID, raw)

        assert profile.age == expected

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "двадцать", "!", "2", "121", "1000", "-5"])
    def test_invalid_values(self, service: ProfileService, raw):
        with pytest.raises(InvalidAgeError):
            service.set_age(USER_ID, raw)

    def test_decimal_value_is_rejected(self, service: ProfileService):
        # «12.5» превращается в 125 — это уже не возраст
        with pytest.raises(InvalidAgeError):
            service.set_age(USER_ID, "12.5")

    def test_age_is_saved_in_repository(self, service: ProfileService, repository):
        service.set_age(USER_ID, "21")

        assert repository.profiles[USER_ID].age == 21

    def test_reset_age(self, service: ProfileService, repository):
        service.set_age(USER_ID, "21")
        profile = service.reset_age(USER_ID)

        assert profile.age is None
        assert repository.profiles[USER_ID].age is None

    def test_reset_age_without_profile_creates_it(self, service: ProfileService, repository):
        service.reset_age(USER_ID)

        assert repository.profiles[USER_ID].age is None

    def test_other_fields_are_kept(self, service: ProfileService):
        service.set_genres(USER_ID, [make_genre("Action", "action", 4)])
        service.set_age(USER_ID, "25")

        profile = service.get_profile(USER_ID)
        assert profile.genre_slugs == ("action",)
        assert profile.age == 25


class TestSetGenres:
    def test_stores_slugs_and_names(self, service: ProfileService, repository):
        genres = [make_genre("Action", "action", 4), make_genre("RPG", "role-playing-games-rpg", 5)]

        profile = service.set_genres(USER_ID, genres)

        assert profile.genre_slugs == ("action", "role-playing-games-rpg")
        assert profile.genre_names == ("Action", "RPG")
        assert repository.profiles[USER_ID].genre_names == ("Action", "RPG")

    def test_empty_list_clears_interests(self, service: ProfileService):
        service.set_genres(USER_ID, [make_genre()])
        profile = service.set_genres(USER_ID, [])

        assert profile.genre_slugs == ()
        assert profile.genre_names == ()

    def test_accepts_tuple(self, service: ProfileService):
        profile = service.set_genres(USER_ID, (make_genre("Strategy", "strategy", 7),))

        assert profile.genre_slugs == ("strategy",)

    def test_age_is_kept(self, service: ProfileService):
        service.set_age(USER_ID, "30")
        service.set_genres(USER_ID, [make_genre()])

        assert service.get_profile(USER_ID).age == 30


class TestSetPlatforms:
    def test_stores_ids_and_names(self, service: ProfileService, repository):
        platforms = [make_platform("PC", "pc", 1), make_platform("Xbox", "xbox", 3)]

        profile = service.set_platforms(USER_ID, platforms)

        assert profile.platform_ids == (1, 3)
        assert profile.platform_names == ("PC", "Xbox")
        assert repository.profiles[USER_ID].platform_ids == (1, 3)

    def test_empty_list_clears_platforms(self, service: ProfileService):
        service.set_platforms(USER_ID, [make_platform()])
        profile = service.set_platforms(USER_ID, [])

        assert profile.platform_ids == ()
        assert profile.platform_names == ()


# ---------------------------------------------------------------------- #
# Регион по IP-адресу
# ---------------------------------------------------------------------- #
class TestSetRegionByIp:
    def test_saves_region(self, service: ProfileService, ip_provider: FakeIpProvider):
        profile = service.set_region_by_ip(USER_ID, "8.8.8.8")

        assert profile.region is not None
        assert profile.region.country_code == "US"
        assert ip_provider.calls == ["8.8.8.8"]

    def test_extracts_ip_from_text(self, service: ProfileService, ip_provider: FakeIpProvider):
        service.set_region_by_ip(USER_ID, "Мой адрес 1.1.1.1, проверил на 2ip.ru")

        assert ip_provider.calls == ["1.1.1.1"]

    def test_ipv6_is_supported(self, service: ProfileService, ip_provider: FakeIpProvider):
        service.set_region_by_ip(USER_ID, "2001:4860:4860::8888")

        assert ip_provider.calls == ["2001:4860:4860::8888"]

    @pytest.mark.parametrize("raw", ["", "   ", "привет", "999.999.999.999", "1.2.3"])
    def test_invalid_ip(self, service: ProfileService, ip_provider: FakeIpProvider, raw):
        with pytest.raises(InvalidIpError):
            service.set_region_by_ip(USER_ID, raw)

        assert ip_provider.calls == []

    @pytest.mark.parametrize(
        "raw", ["192.168.1.10", "127.0.0.1", "10.0.0.5", "169.254.1.1", "::1", "0.0.0.0"]
    )
    def test_private_ip(self, service: ProfileService, ip_provider: FakeIpProvider, raw):
        with pytest.raises(PrivateIpError):
            service.set_region_by_ip(USER_ID, raw)

        assert ip_provider.calls == []

    def test_provider_error_is_passed_through(self, repository, ip_provider: FakeIpProvider):
        ip_provider.error = RegionUnavailableError("ipapi", "429")
        service = ProfileService(repository=repository, ip_provider=ip_provider)

        with pytest.raises(RegionUnavailableError):
            service.set_region_by_ip(USER_ID, "8.8.8.8")

    def test_unexpected_provider_error_becomes_service_error(self, repository):
        ip_provider = FakeIpProvider(error=RuntimeError("network down"))
        service = ProfileService(repository=repository, ip_provider=ip_provider)

        with pytest.raises(RegionUnavailableError) as info:
            service.set_region_by_ip(USER_ID, "8.8.8.8")

        assert info.value.service == "ipapi"

    def test_unknown_region_is_reported_as_unavailable(self, repository):
        ip_provider = FakeIpProvider(region=None)
        service = ProfileService(repository=repository, ip_provider=ip_provider)

        with pytest.raises(RegionUnavailableError):
            service.set_region_by_ip(USER_ID, "8.8.8.8")

    def test_empty_region_is_reported_as_unavailable(self, repository):
        ip_provider = FakeIpProvider(region=Region(ip="8.8.8.8"))
        service = ProfileService(repository=repository, ip_provider=ip_provider)

        with pytest.raises(RegionUnavailableError):
            service.set_region_by_ip(USER_ID, "8.8.8.8")

    def test_region_can_be_replaced(self, repository):
        ip_provider = FakeIpProvider(
            regions={
                "8.8.8.8": make_region(ip="8.8.8.8", country="United States", country_code="US"),
                "5.188.0.1": make_region(ip="5.188.0.1", country="Russia", country_code="RU"),
            }
        )
        service = ProfileService(repository=repository, ip_provider=ip_provider)

        service.set_region_by_ip(USER_ID, "8.8.8.8")
        profile = service.set_region_by_ip(USER_ID, "5.188.0.1")

        assert profile.region.country_code == "RU"

    def test_reset_region(self, service: ProfileService, repository):
        service.set_region_by_ip(USER_ID, "8.8.8.8")
        profile = service.reset_region(USER_ID)

        assert profile.region is None
        assert repository.profiles[USER_ID].region is None

    def test_reset_region_keeps_other_fields(self, service: ProfileService):
        service.set_age(USER_ID, "25")
        service.set_region_by_ip(USER_ID, "8.8.8.8")
        service.reset_region(USER_ID)

        assert service.get_profile(USER_ID).age == 25


class TestValidateIp:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("8.8.8.8", "8.8.8.8"),
            ("  1.1.1.1  ", "1.1.1.1"),
            ("ip: 9.9.9.9", "9.9.9.9"),
            ("2001:4860:4860::8888", "2001:4860:4860::8888"),
        ],
    )
    def test_valid_addresses(self, raw, expected):
        assert ProfileService.validate_ip(raw) == expected

    def test_invalid_address(self):
        with pytest.raises(InvalidIpError):
            ProfileService.validate_ip("не адрес")

    def test_empty_address(self):
        with pytest.raises(InvalidIpError):
            ProfileService.validate_ip("")

    def test_private_address(self):
        with pytest.raises(PrivateIpError):
            ProfileService.validate_ip("192.168.0.1")

    def test_multicast_address_is_rejected(self):
        with pytest.raises(PrivateIpError):
            ProfileService.validate_ip("224.0.0.1")


class TestExtractIp:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("8.8.8.8", "8.8.8.8"),
            ("Мой IP: 8.8.8.8 (2ip.ru)", "8.8.8.8"),
            ("текст 2001:db8::1 текст", "2001:db8::1"),
        ],
    )
    def test_extracts_address(self, raw, expected):
        assert extract_ip(raw) == expected

    def test_returns_text_when_no_address_found(self):
        assert extract_ip("просто текст") == "просто текст"

    @pytest.mark.parametrize("raw", ["", None, "   "])
    def test_empty_text(self, raw):
        assert extract_ip(raw) is None


# ---------------------------------------------------------------------- #
# Работа с настоящим репозиторием (SQLite)
# ---------------------------------------------------------------------- #
class TestWithSqlRepository:
    def test_profile_survives_service_recreation(self, database):
        ip_provider = FakeIpProvider(region=make_region())
        first = ProfileService(repository=SqlProfileRepository(database), ip_provider=ip_provider)
        first.set_age(USER_ID, "33")
        first.set_genres(USER_ID, [make_genre("RPG", "role-playing-games-rpg", 5)])
        first.set_region_by_ip(USER_ID, "8.8.8.8")

        second = ProfileService(repository=SqlProfileRepository(database), ip_provider=ip_provider)
        profile = second.get_profile(USER_ID)

        assert profile.age == 33
        assert profile.genre_slugs == ("role-playing-games-rpg",)
        assert profile.region is not None
        assert profile.region.timezone == "America/Los_Angeles"

    def test_database_error_is_propagated(self, database, monkeypatch):
        repository = SqlProfileRepository(database)
        monkeypatch.setattr(
            repository, "get_or_create", lambda user_id: (_ for _ in ()).throw(DatabaseError())
        )
        service = ProfileService(repository=repository, ip_provider=FakeIpProvider())

        with pytest.raises(DatabaseError):
            service.get_profile(USER_ID)
