"""Тесты клиента сервиса геолокации по IP-адресу (ipapi.co / ipwho.is)."""

from __future__ import annotations

import pytest

from gamehunter.domain.exceptions import ExternalServiceError, RegionUnavailableError
from gamehunter.infrastructure.api.http_client import JsonHttpClient
from gamehunter.infrastructure.api.ip_location_client import IpLocationClient
from tests.fakes import FakeResponse, FakeSession

#: Ответ ipapi.co (основной формат)
IPAPI_PAYLOAD = {
    "ip": "5.188.0.1",
    "city": "Kazan",
    "region": "Tatarstan Republic",
    "region_code": "TA",
    "country": "RU",
    "country_code": "RU",
    "country_name": "Russia",
    "timezone": "Europe/Moscow",
    "currency": "RUB",
    "latitude": 55.7887,
    "longitude": 49.1221,
}

#: Ответ ipwho.is (альтернативный формат с вложенными объектами)
IPWHO_PAYLOAD = {
    "success": True,
    "ip": "8.8.8.8",
    "country": "United States",
    "country_code": "US",
    "city": "Mountain View",
    "region": "California",
    "timezone": {"id": "America/Los_Angeles", "abbr": "PDT"},
    "currency": {"code": "USD", "name": "US Dollar"},
    "latitude": 37.4,
    "longitude": -122.07,
}


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def client(session: FakeSession) -> IpLocationClient:
    return IpLocationClient(JsonHttpClient(timeout=5, session=session))


def respond(session: FakeSession, payload, status_code: int = 200) -> None:
    session.responses.append(FakeResponse(json_data=payload, status_code=status_code))


class TestRequest:
    def test_default_service_url(self, client: IpLocationClient, session: FakeSession):
        respond(session, IPAPI_PAYLOAD)

        client.locate("5.188.0.1")

        assert session.requests[0]["url"] == "https://ipapi.co/5.188.0.1/json/"

    def test_custom_base_url(self, session: FakeSession):
        client = IpLocationClient(JsonHttpClient(session=session), base_url="https://ipwho.is/")
        respond(session, IPWHO_PAYLOAD)

        client.locate("8.8.8.8")

        assert session.requests[0]["url"] == "https://ipwho.is/8.8.8.8/json/"

    def test_empty_base_url_falls_back_to_default(self, session: FakeSession):
        client = IpLocationClient(JsonHttpClient(session=session), base_url="")
        respond(session, IPAPI_PAYLOAD)

        client.locate("1.1.1.1")

        assert session.requests[0]["url"].startswith("https://ipapi.co/")

    def test_ip_is_trimmed(self, client: IpLocationClient, session: FakeSession):
        respond(session, IPAPI_PAYLOAD)

        client.locate("  5.188.0.1  ")

        assert session.requests[0]["url"].endswith("/5.188.0.1/json/")

    @pytest.mark.parametrize("ip", ["", "   ", None])
    def test_empty_ip_does_not_call_service(self, client: IpLocationClient, session: FakeSession, ip):
        assert client.locate(ip) is None
        assert session.requests == []


class TestParsing:
    def test_ipapi_payload(self, client: IpLocationClient, session: FakeSession):
        respond(session, IPAPI_PAYLOAD)

        region = client.locate("5.188.0.1")

        assert region is not None
        assert region.ip == "5.188.0.1"
        assert region.country == "Russia"
        assert region.country_code == "RU"
        assert region.city == "Kazan"
        assert region.region_name == "Tatarstan Republic"
        assert region.timezone == "Europe/Moscow"
        assert region.currency == "RUB"
        assert region.latitude == pytest.approx(55.7887)
        assert region.longitude == pytest.approx(49.1221)
        assert region.title == "Kazan, Tatarstan Republic, Russia"

    def test_ipwho_payload(self, client: IpLocationClient, session: FakeSession):
        respond(session, IPWHO_PAYLOAD)

        region = client.locate("8.8.8.8")

        assert region is not None
        assert region.country == "United States"
        assert region.city == "Mountain View"
        assert region.timezone == "America/Los_Angeles"
        assert region.currency == "USD"

    def test_country_field_with_long_name(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"country": "Russia", "city": "Kazan"})

        region = client.locate("5.188.0.1")

        assert region.country == "Russia"
        assert region.country_code == ""

    def test_country_code_from_short_country_field(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"country": "ru", "city": "Kazan"})

        region = client.locate("5.188.0.1")

        assert region.country_code == "RU"
        assert region.country == ""

    def test_missing_fields_become_empty(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"city": "Kazan"})

        region = client.locate("1.1.1.1")

        assert region.timezone == ""
        assert region.currency == ""
        assert region.latitude is None

    def test_invalid_coordinates_are_ignored(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"city": "Kazan", "latitude": "не число", "longitude": None})

        region = client.locate("1.1.1.1")

        assert region.latitude is None
        assert region.longitude is None

    def test_unknown_region_returns_none(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"ip": "1.1.1.1", "timezone": "UTC"})

        assert client.locate("1.1.1.1") is None

    def test_only_country_code_is_enough(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"country_code": "RU"})

        region = client.locate("1.1.1.1")

        assert region is not None
        assert region.title == "RU"

    def test_non_dict_payload_returns_none(self, client: IpLocationClient, session: FakeSession):
        respond(session, ["unexpected", "list"])

        assert client.locate("1.1.1.1") is None

    def test_404_returns_none(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"error": True}, status_code=404)

        assert client.locate("999.999.999.999") is None


class TestErrors:
    def test_ipapi_error_payload(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"error": True, "reason": "Reserved range"})

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("0.0.0.0")

        assert info.value.service == "ipapi"
        assert info.value.reason == "Reserved range"

    def test_ipapi_error_payload_with_message(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"error": True, "message": "Rate limited"})

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("1.1.1.1")

        assert info.value.reason == "Rate limited"

    def test_ipwho_failure_payload(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"success": False, "message": "Invalid IP"})

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("abc")

        assert info.value.reason == "Invalid IP"

    def test_error_payload_without_reason(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"error": True})

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("1.1.1.1")

        assert info.value.reason == "error"

    def test_http_error(self, client: IpLocationClient, session: FakeSession):
        respond(session, {}, status_code=500)

        with pytest.raises(RegionUnavailableError):
            client.locate("1.1.1.1")

    def test_network_error(self, client: IpLocationClient, session: FakeSession):
        session.error = ExternalServiceError("ipapi", "timeout")

        with pytest.raises(RegionUnavailableError):
            client.locate("1.1.1.1")

    def test_unexpected_error(self, client: IpLocationClient, session: FakeSession):
        session.error = RuntimeError("boom")

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("1.1.1.1")

        assert info.value.service == "ipapi"

    def test_user_message_is_understandable(self, client: IpLocationClient, session: FakeSession):
        respond(session, {"error": True, "reason": "Rate limited"})

        with pytest.raises(RegionUnavailableError) as info:
            client.locate("1.1.1.1")

        message = info.value.user_message
        assert message.strip()
        assert "сервис" in message.lower() or "регион" in message.lower()
