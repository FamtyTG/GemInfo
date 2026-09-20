"""Клиенты внешних API (Ninjas, GeoNames, Wikipedia)."""

from travelhunter.infrastructure.api.geonames_client import GeoNamesClient
from travelhunter.infrastructure.api.http_client import JsonHttpClient
from travelhunter.infrastructure.api.ninjas_client import NinjasHolidaysClient
from travelhunter.infrastructure.api.wikipedia_client import WikipediaClient

__all__ = [
    "GeoNamesClient",
    "JsonHttpClient",
    "NinjasHolidaysClient",
    "WikipediaClient",
]
