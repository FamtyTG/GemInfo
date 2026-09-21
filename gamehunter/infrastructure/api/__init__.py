"""Клиенты внешних API (RAWG — каталог игр, ipapi.co — геолокация по IP)."""

from gamehunter.infrastructure.api.http_client import JsonHttpClient
from gamehunter.infrastructure.api.ip_location_client import IpLocationClient
from gamehunter.infrastructure.api.rawg_client import RawgClient

__all__ = ["IpLocationClient", "JsonHttpClient", "RawgClient"]
