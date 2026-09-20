"""Тесты базового HTTP-клиента."""

from __future__ import annotations

import pytest
import requests

from gamehunter.domain.exceptions import ExternalServiceError
from gamehunter.infrastructure.api.http_client import JsonHttpClient
from tests.fakes import FakeResponse, FakeSession


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def client(session: FakeSession) -> JsonHttpClient:
    return JsonHttpClient(timeout=7, session=session)


class TestGetJson:
    def test_returns_parsed_json(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={"results": [1, 2]}))

        assert client.get_json("https://api.example/data") == {"results": [1, 2]}

    def test_passes_url_params_headers_and_timeout(
        self, client: JsonHttpClient, session: FakeSession
    ):
        session.responses.append(FakeResponse(json_data={}))

        client.get_json(
            "https://api.example/data",
            params={"page": 2},
            headers={"Accept": "application/json"},
        )

        request = session.requests[0]
        assert request["url"] == "https://api.example/data"
        assert request["params"] == {"page": 2}
        assert request["headers"] == {"Accept": "application/json"}
        assert request["timeout"] == 7

    def test_default_timeout(self, session: FakeSession):
        client = JsonHttpClient(session=session)
        session.responses.append(FakeResponse(json_data={}))

        client.get_json("https://api.example")

        assert session.requests[0]["timeout"] == 10

    def test_list_response_is_returned_as_is(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data=[1, 2, 3]))

        assert client.get_json("https://api.example") == [1, 2, 3]


class TestErrors:
    @pytest.mark.parametrize(
        "exception, expected_reason",
        [
            (requests.Timeout("timeout"), "timeout"),
            (requests.ConnectionError("no connection"), "connection error"),
            (requests.RequestException("other"), "other"),
        ],
    )
    def test_network_errors(self, client: JsonHttpClient, session: FakeSession, exception, expected_reason):
        session.error = exception

        with pytest.raises(ExternalServiceError) as info:
            client.get_json("https://api.example", service="rawg")

        assert info.value.service == "rawg"
        assert info.value.reason == expected_reason

    @pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500, 502, 503])
    def test_http_errors(self, client: JsonHttpClient, session: FakeSession, status_code):
        session.responses.append(FakeResponse(json_data={}, status_code=status_code))

        with pytest.raises(ExternalServiceError) as info:
            client.get_json("https://api.example", service="rawg")

        assert str(status_code) in info.value.reason

    def test_invalid_json(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data=None, invalid_json=True, text="<html>"))

        with pytest.raises(ExternalServiceError) as info:
            client.get_json("https://api.example", service="rawg")

        assert info.value.reason == "invalid json"

    def test_error_without_service_name(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={}, status_code=500))

        with pytest.raises(ExternalServiceError) as info:
            client.get_json("https://api.example")

        assert info.value.service == ""


class TestAllow404:
    def test_404_returns_none_when_allowed(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={}, status_code=404))

        assert client.get_json("https://api.example", allow_404=True) is None

    def test_404_raises_when_not_allowed(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={}, status_code=404))

        with pytest.raises(ExternalServiceError):
            client.get_json("https://api.example")

    def test_other_errors_are_not_ignored(self, client: JsonHttpClient, session: FakeSession):
        session.responses.append(FakeResponse(json_data={}, status_code=500))

        with pytest.raises(ExternalServiceError):
            client.get_json("https://api.example", allow_404=True)
