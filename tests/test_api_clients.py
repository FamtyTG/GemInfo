"""Тесты клиентов внешних API и базового HTTP-клиента.

HTTP-слой подменяется (FakeSession), поэтому тесты не требуют интернета.
"""

from __future__ import annotations

from datetime import date

import pytest
import requests

from travelhunter.domain.exceptions import (
    CityInfoUnavailableError,
    CitySearchUnavailableError,
    ExternalServiceError,
    HolidaysUnavailableError,
)
from travelhunter.infrastructure.api import (
    GeoNamesClient,
    JsonHttpClient,
    NinjasHolidaysClient,
    WikipediaClient,
)
from travelhunter.infrastructure.api.ninjas_client import parse_holiday_date
from tests.fakes import FakeResponse, FakeSession


def http_client(responses) -> tuple[JsonHttpClient, FakeSession]:
    session = FakeSession(responses=responses)
    return JsonHttpClient(timeout=5, session=session), session


# ====================================================================== #
# JsonHttpClient
# ====================================================================== #
def test_http_client_returns_json():
    client, session = http_client([FakeResponse(json_data={"ok": True})])

    assert client.get_json("https://example.com", params={"a": 1}, service="test") == {"ok": True}
    assert session.requests[0]["params"] == {"a": 1}
    assert session.requests[0]["timeout"] == 5


def test_http_client_raises_on_timeout():
    class TimeoutSession(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            raise requests.Timeout("timeout")

    client = JsonHttpClient(timeout=5, session=TimeoutSession())

    with pytest.raises(ExternalServiceError):
        client.get_json("https://example.com", service="test")


def test_http_client_raises_on_connection_error():
    class BrokenSession(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            raise requests.ConnectionError("no route to host")

    client = JsonHttpClient(timeout=5, session=BrokenSession())

    with pytest.raises(ExternalServiceError):
        client.get_json("https://example.com", service="test")


def test_http_client_raises_on_http_error_status():
    client, _ = http_client([FakeResponse(json_data=None, status_code=503, text="Service Unavailable")])

    with pytest.raises(ExternalServiceError) as exc_info:
        client.get_json("https://example.com", service="test")

    assert "503" in str(exc_info.value)


def test_http_client_raises_on_invalid_json():
    client, _ = http_client([FakeResponse(invalid_json=True, text="<html>error</html>")])

    with pytest.raises(ExternalServiceError):
        client.get_json("https://example.com", service="test")


# ====================================================================== #
# Ninjas Holidays API
# ====================================================================== #
NINJAS_PAYLOAD = [
    {
        "country": "Russia",
        "iso": "RU",
        "year": 2026,
        "date": "2026-08-12",
        "day": "We",
        "name": "Day of the Flag",
        "type": "Observance",
    },
    {
        "country": "Russia",
        "iso": "RU",
        "year": 2026,
        "date": "2026-12-31",
        "day": "Th",
        "name": "New Year Eve",
        "type": "Observance",
    },
]


def test_ninjas_client_sends_api_key_and_country():
    client_http, session = http_client([FakeResponse(json_data=NINJAS_PAYLOAD)])
    client = NinjasHolidaysClient(client_http, api_key="SECRET-KEY")

    holidays = client.fetch_holidays("RU", 2026)

    request = session.requests[0]
    assert request["url"] == "https://api.api-ninjas.com/v2/holidays"
    assert request["params"]["country"] == "RU"
    assert request["params"]["date"] == "2026-01-01"
    assert request["headers"] == {"X-Api-Key": "SECRET-KEY"}
    assert len(holidays) == 2
    assert holidays[0].date == date(2026, 8, 12)
    assert holidays[0].name == "Day of the Flag"
    assert holidays[0].type == "Observance"
    assert holidays[0].iso == "RU"


def test_ninjas_client_parses_alternative_date_formats():
    payload = [{"name": "Праздник", "date": "12/08/2026", "day": "We", "type": "Public"}]
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = NinjasHolidaysClient(client_http, api_key="KEY")

    holidays = client.fetch_holidays("RU", 2026)

    assert holidays[0].date == date(2026, 8, 12)


def test_parse_holiday_date_supported_formats():
    assert parse_holiday_date("2026-08-12") == date(2026, 8, 12)
    assert parse_holiday_date("12.08.2026") == date(2026, 8, 12)
    assert parse_holiday_date("2026-08-12T00:00:00") == date(2026, 8, 12)
    assert parse_holiday_date("не дата") is None
    assert parse_holiday_date(None) is None


def test_ninjas_client_skips_items_without_name_or_date():
    payload = [
        {"name": "", "date": "2026-08-12"},
        {"name": "Без даты", "date": "unknown"},
        "строка вместо объекта",
        {"name": "Нормальный", "date": "2026-08-13"},
    ]
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = NinjasHolidaysClient(client_http, api_key="KEY")

    holidays = client.fetch_holidays("RU", 2026)

    assert [holiday.name for holiday in holidays] == ["Нормальный"]


def test_ninjas_client_requires_api_key():
    client_http, session = http_client([FakeResponse(json_data=[])])
    client = NinjasHolidaysClient(client_http, api_key="")

    with pytest.raises(HolidaysUnavailableError):
        client.fetch_holidays("RU", 2026)

    assert session.requests == []  # запрос не выполнялся
    assert client.is_configured is False


def test_ninjas_client_handles_error_object():
    client_http, _ = http_client([FakeResponse(json_data={"error": "Invalid API key"})])
    client = NinjasHolidaysClient(client_http, api_key="KEY")

    with pytest.raises(HolidaysUnavailableError) as exc_info:
        client.fetch_holidays("RU", 2026)

    assert "Invalid API key" in str(exc_info.value)


def test_ninjas_client_handles_unexpected_payload_type():
    client_http, _ = http_client([FakeResponse(json_data="просто строка")])
    client = NinjasHolidaysClient(client_http, api_key="KEY")

    with pytest.raises(HolidaysUnavailableError):
        client.fetch_holidays("RU", 2026)


def test_ninjas_client_converts_http_errors():
    client_http, _ = http_client([FakeResponse(status_code=401, text="Unauthorized")])
    client = NinjasHolidaysClient(client_http, api_key="KEY")

    with pytest.raises(HolidaysUnavailableError):
        client.fetch_holidays("RU", 2026)


# ====================================================================== #
# GeoNames API
# ====================================================================== #
GEONAMES_SEARCH_PAYLOAD = {
    "totalResultsCount": 2,
    "geonames": [
        {
            "geonameId": 524901,
            "name": "Москва",
            "lat": "55.7558",
            "lng": "37.6173",
            "countryName": "Russia",
            "adminName1": "Москва",
            "population": 12615882,
            "featureClass": "P",
            "featureCode": "PPLC",
        },
        {
            "geonameId": 1,
            "name": "Moskva",
            "lat": "55.75",
            "lng": "37.62",
            "countryName": "Russia",
            "population": 10,
            "featureClass": "P",
        },
    ],
}

GEONAMES_NEARBY_PAYLOAD = {
    "geonames": [
        {
            "geonameId": 524901,
            "name": "Москва",
            "lat": "55.7558",
            "lng": "37.6173",
            "distance": "0.0",
            "countryName": "Russia",
            "population": 12615882,
        },
        {
            "geonameId": 480508,
            "name": "Тула",
            "lat": "54.2021",
            "lng": "37.6443",
            "distance": "172.45",
            "countryName": "Russia",
            "adminName1": "Тульская область",
            "population": 482873,
        },
        {
            "name": "",
            "lat": "0",
            "lng": "0",
            "distance": "10",
        },
    ]
}


def test_geonames_search_city_returns_biggest_match():
    client_http, session = http_client([FakeResponse(json_data=GEONAMES_SEARCH_PAYLOAD)])
    client = GeoNamesClient(client_http, username="demo")

    city = client.search_city("Москва")

    assert city is not None
    assert city.name == "Москва"
    assert city.latitude == 55.7558
    assert city.longitude == 37.6173
    assert city.geoname_id == 524901
    assert city.country == "Russia"

    request = session.requests[0]
    assert request["url"] == "https://secure.geonames.org/searchJSON"
    assert request["params"]["q"] == "Москва"
    assert request["params"]["username"] == "demo"
    assert request["params"]["featureClass"] == "P"


def test_geonames_search_city_returns_none_when_not_found():
    client_http, _ = http_client([FakeResponse(json_data={"totalResultsCount": 0, "geonames": []})])
    client = GeoNamesClient(client_http, username="demo")

    assert client.search_city("Несуществующий") is None


def test_geonames_search_city_requires_username():
    client_http, session = http_client([FakeResponse(json_data=GEONAMES_SEARCH_PAYLOAD)])
    client = GeoNamesClient(client_http, username="")

    with pytest.raises(CitySearchUnavailableError):
        client.search_city("Москва")

    assert session.requests == []
    assert client.is_configured is False


def test_geonames_handles_account_error_status():
    payload = {"status": {"message": "user account disabled", "value": 10}}
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = GeoNamesClient(client_http, username="demo")

    with pytest.raises(CitySearchUnavailableError) as exc_info:
        client.search_city("Москва")

    assert "user account disabled" in str(exc_info.value)


def test_geonames_find_nearby_cities_parses_distance():
    client_http, session = http_client([FakeResponse(json_data=GEONAMES_NEARBY_PAYLOAD)])
    client = GeoNamesClient(client_http, username="demo")

    cities = client.find_nearby_cities(latitude=55.7558, longitude=37.6173, radius_km=500, limit=5)

    assert [city.name for city in cities] == ["Москва", "Тула"]  # пустая запись отброшена
    assert cities[1].distance_km == 172.45
    assert cities[1].rounded_distance == 172

    request = session.requests[0]
    assert request["url"] == "https://secure.geonames.org/findNearbyPlaceNameJSON"
    assert request["params"]["radius"] == 500
    assert request["params"]["lat"] == 55.7558
    assert request["params"]["lng"] == 37.6173


def test_geonames_find_nearby_cities_respects_limit():
    client_http, session = http_client([FakeResponse(json_data=GEONAMES_NEARBY_PAYLOAD)])
    client = GeoNamesClient(client_http, username="demo")

    cities = client.find_nearby_cities(55.75, 37.61, radius_km=500, limit=1)

    assert len(cities) == 1
    assert session.requests[0]["params"]["maxRows"] == 1  # запрашиваем ровно столько, сколько нужно


def test_geonames_converts_http_error():
    client_http, _ = http_client([FakeResponse(status_code=400, text="bad request")])
    client = GeoNamesClient(client_http, username="demo")

    with pytest.raises(CitySearchUnavailableError):
        client.search_city("Москва")


def test_geonames_handles_unexpected_payload():
    client_http, _ = http_client([FakeResponse(json_data=[])])
    client = GeoNamesClient(client_http, username="demo")

    assert client.search_city("Москва") is None
    assert client.find_nearby_cities(0, 0, 500, 5) == []


def test_geonames_uses_country_bias_and_language():
    client_http, session = http_client(
        [FakeResponse(json_data={"geonames": []}), FakeResponse(json_data={"geonames": []})]
    )
    client = GeoNamesClient(
        client_http, username="demo", country_bias="RU", language="ru"
    )

    client.search_city("Тула")

    params = session.requests[0]["params"]
    assert params["countryBias"] == "RU"
    assert params["lang"] == "ru"


# ====================================================================== #
# Wikipedia API
# ====================================================================== #
WIKI_PAYLOAD = {
    "query": {
        "pages": {
            "12345": {
                "pageid": 12345,
                "title": "Тула",
                "extract": "Тула — город в России, административный центр Тульской области.",
                "thumbnail": {
                    "source": "https://upload.wikimedia.org/wikipedia/commons/tula.jpg",
                    "width": 800,
                },
            }
        }
    }
}


def test_wikipedia_returns_city_info():
    client_http, session = http_client([FakeResponse(json_data=WIKI_PAYLOAD)])
    client = WikipediaClient(client_http, language="ru")

    info = client.fetch_city_info("Тула")

    assert info is not None
    assert info.title == "Тула"
    assert info.summary.startswith("Тула — город в России")
    assert info.image_url.endswith("tula.jpg")

    request = session.requests[0]
    assert request["url"] == "https://ru.wikipedia.org/w/api.php"
    assert request["params"]["titles"] == "Тула"
    assert request["params"]["prop"] == "extracts|pageimages"
    assert request["params"]["exintro"] == 1
    assert request["params"]["explaintext"] == 1
    assert request["params"]["redirects"] == 1


def test_wikipedia_language_is_used_in_url():
    client = WikipediaClient(JsonHttpClient(session=FakeSession()), language="en")

    assert client.api_url == "https://en.wikipedia.org/w/api.php"


def test_wikipedia_returns_none_for_missing_page():
    payload = {"query": {"pages": {"-1": {"ns": 0, "title": "Нет такого", "missing": ""}}}}
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = WikipediaClient(client_http)

    assert client.fetch_city_info("Нет такого города") is None


def test_wikipedia_returns_none_for_empty_extract():
    payload = {"query": {"pages": {"1": {"title": "Тула", "extract": "   "}}}}
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = WikipediaClient(client_http)

    assert client.fetch_city_info("Тула") is None


def test_wikipedia_handles_page_without_image():
    payload = {
        "query": {
            "pages": {
                "7": {"title": "Малый город", "extract": "Описание города без фото."}
            }
        }
    }
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = WikipediaClient(client_http)

    info = client.fetch_city_info("Малый город")

    assert info is not None
    assert info.image_url is None
    assert info.has_image is False


def test_wikipedia_uses_originalimage_as_fallback():
    payload = {
        "query": {
            "pages": {
                "7": {
                    "title": "Город",
                    "extract": "Описание.",
                    "originalimage": {"source": "https://example.org/full.jpg"},
                }
            }
        }
    }
    client_http, _ = http_client([FakeResponse(json_data=payload)])
    client = WikipediaClient(client_http)

    assert client.fetch_city_info("Город").image_url == "https://example.org/full.jpg"


def test_wikipedia_converts_http_error():
    client_http, _ = http_client([FakeResponse(status_code=500, text="server error")])
    client = WikipediaClient(client_http)

    with pytest.raises(CityInfoUnavailableError):
        client.fetch_city_info("Тула")


def test_wikipedia_handles_unexpected_payload():
    client_http, _ = http_client([FakeResponse(json_data=[])])
    client = WikipediaClient(client_http)

    assert client.fetch_city_info("Тула") is None
