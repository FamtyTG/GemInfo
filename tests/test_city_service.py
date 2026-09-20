"""Тесты сервиса городов (Экраны 4, 5, 6)."""

from __future__ import annotations

import pytest

from travelhunter.domain.entities import CityInfo
from travelhunter.domain.exceptions import (
    CityInfoUnavailableError,
    CityNotFoundError,
    CitySearchUnavailableError,
    NearbyCitiesNotFoundError,
)
from travelhunter.domain.services import CityService, normalize_name
from tests.fakes import FakeCityInfoProvider, FakeCityProvider, make_city, make_nearby_city


def build_service(city=None, nearby=None, info=None, **kwargs) -> CityService:
    return CityService(
        city_provider=FakeCityProvider(city=city, nearby=nearby),
        city_info_provider=FakeCityInfoProvider(info=info),
        **kwargs,
    )


# ---------------------------------------------------------------------- #
# Экран 4. Поиск города
# ---------------------------------------------------------------------- #
def test_find_city_returns_city_with_coordinates():
    city = make_city("Москва", 55.7558, 37.6173)
    service = build_service(city=city)

    assert service.find_city("Москва") == city


def test_find_city_strips_extra_spaces():
    service = build_service(city=make_city("Тула"))
    provider = service._city_provider  # noqa: SLF001 - проверка аргумента запроса

    service.find_city("  Тула  ")

    assert provider.search_calls == ["Тула"]


def test_find_city_raises_when_city_not_found():
    service = build_service(city=None)

    with pytest.raises(CityNotFoundError):
        service.find_city("Несуществующий город")


def test_find_city_raises_on_empty_input():
    service = build_service(city=make_city("Москва"))

    with pytest.raises(CityNotFoundError):
        service.find_city("   ")


def test_city_not_found_message_matches_spec():
    assert CityNotFoundError().user_message == (
        "Город не найден. Проверьте название города и попробуйте ещё раз."
    )


def test_find_city_converts_unexpected_error():
    provider = FakeCityProvider(search_error=RuntimeError("boom"))
    service = CityService(
        city_provider=provider, city_info_provider=FakeCityInfoProvider()
    )

    with pytest.raises(CitySearchUnavailableError):
        service.find_city("Москва")


def test_find_city_propagates_domain_error():
    provider = FakeCityProvider(
        search_error=CitySearchUnavailableError("geonames", "limit exceeded")
    )
    service = CityService(
        city_provider=provider, city_info_provider=FakeCityInfoProvider()
    )

    with pytest.raises(CitySearchUnavailableError):
        service.find_city("Москва")


# ---------------------------------------------------------------------- #
# Экран 5. Ближайшие города
# ---------------------------------------------------------------------- #
def test_find_nearby_cities_uses_current_city_coordinates():
    service = build_service(
        city=None,
        nearby=[make_nearby_city("Тула", 180.0)],
        radius_km=500,
    )
    provider = service._city_provider  # noqa: SLF001

    service.find_nearby_cities(make_city("Москва", 55.7558, 37.6173))

    assert provider.nearby_calls[0]["lat"] == 55.7558
    assert provider.nearby_calls[0]["lng"] == 37.6173
    assert provider.nearby_calls[0]["radius"] == 500


def test_find_nearby_cities_excludes_current_city():
    nearby = [
        make_nearby_city("Москва", 0.0),
        make_nearby_city("Тула", 180.0),
        make_nearby_city("москва", 5.0),  # тот же город в другом регистре
    ]
    service = build_service(nearby=nearby)

    result = service.find_nearby_cities(make_city("Москва"))

    assert [city.name for city in result] == ["Тула"]


def test_find_nearby_cities_sorts_by_distance_and_removes_duplicates():
    nearby = [
        make_nearby_city("Рязань", 340.0),
        make_nearby_city("Тула", 180.0),
        make_nearby_city("Рязань", 345.0),
        make_nearby_city("Калуга", 250.0),
    ]
    service = build_service(nearby=nearby)

    result = service.find_nearby_cities(make_city("Москва"))

    assert [city.name for city in result] == ["Тула", "Калуга", "Рязань"]
    assert [city.rounded_distance for city in result] == [180, 250, 340]


def test_find_nearby_cities_returns_at_most_five():
    nearby = [make_nearby_city(f"Город {i}", float(10 * i)) for i in range(1, 12)]
    service = build_service(nearby=nearby)

    assert len(service.find_nearby_cities(make_city("Москва"))) == 5


def test_find_nearby_cities_raises_when_nothing_found():
    service = build_service(nearby=[make_nearby_city("Москва", 0.0)])

    with pytest.raises(NearbyCitiesNotFoundError) as exc_info:
        service.find_nearby_cities(make_city("Москва"))

    assert "Норильск" not in exc_info.value.user_message
    assert "Москва" in exc_info.value.user_message
    assert "500" in exc_info.value.user_message


def test_find_nearby_cities_converts_unexpected_error():
    provider = FakeCityProvider(nearby_error=ValueError("bad data"))
    service = CityService(
        city_provider=provider, city_info_provider=FakeCityInfoProvider()
    )

    with pytest.raises(CitySearchUnavailableError):
        service.find_nearby_cities(make_city("Москва"))


def test_normalize_name():
    assert normalize_name("  Москва ") == "москва"
    assert normalize_name("") == ""


# ---------------------------------------------------------------------- #
# Экран 6. Информация о городе
# ---------------------------------------------------------------------- #
def test_get_city_info_returns_title_summary_and_image():
    info = CityInfo(
        title="Тула",
        summary="Тула — город в России, административный центр Тульской области.",
        image_url="https://upload.wikimedia.org/tula.jpg",
    )
    service = build_service(info=info)

    result = service.get_city_info("Тула")

    assert result.title == "Тула"
    assert result.summary.startswith("Тула — город")
    assert result.has_image


def test_get_city_info_raises_when_article_not_found():
    service = build_service(info=None)

    with pytest.raises(CityInfoUnavailableError):
        service.get_city_info("Неизвестный город")


def test_get_city_info_truncates_long_summary():
    long_summary = "слово " * 500  # 3000 символов
    service = build_service(
        info=CityInfo(title="Город", summary=long_summary), summary_max_length=100
    )

    result = service.get_city_info("Город")

    assert len(result.summary) <= 101  # 100 символов + многоточие
    assert result.summary.endswith("…")


def test_get_city_info_converts_unexpected_error():
    provider = FakeCityInfoProvider(error=RuntimeError("no internet"))
    service = CityService(city_provider=FakeCityProvider(), city_info_provider=provider)

    with pytest.raises(CityInfoUnavailableError):
        service.get_city_info("Тула")


def test_city_info_without_image_is_allowed():
    service = build_service(info=CityInfo(title="Тула", summary="Описание", image_url=None))

    result = service.get_city_info("Тула")

    assert result.has_image is False
