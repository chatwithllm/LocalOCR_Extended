"""
Thin wrapper around the Plaid Python SDK.

All outbound Plaid calls go through this module so we can:
- Centralize sandbox / development / production switching
- Keep API-version and product configuration in one place
- Surface consistent error types to the rest of the backend
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.products import Products


logger = logging.getLogger(__name__)

PLAID_API_VERSION = "2020-09-14"
DEFAULT_PRODUCTS = ("transactions", "liabilities")
DEFAULT_COUNTRY_CODES = ("US",)


class PlaidConfigurationError(RuntimeError):
    """Raised when Plaid env vars are missing or misconfigured."""


def _env_to_host(env_name: str) -> str:
    normalized = str(env_name or "sandbox").strip().lower()
    if normalized == "sandbox":
        return plaid.Environment.Sandbox
    if normalized in {"development", "dev"}:
        return plaid.Environment.Development
    if normalized in {"production", "prod"}:
        return plaid.Environment.Production
    raise PlaidConfigurationError(
        f"Unsupported PLAID_ENV '{env_name}'. Expected sandbox | development | production."
    )


def is_plaid_configured() -> bool:
    """Return True if the Plaid env vars are populated enough to make calls."""
    return bool(
        (os.getenv("PLAID_CLIENT_ID") or "").strip()
        and (os.getenv("PLAID_SECRET") or "").strip()
    )


def get_plaid_env_name() -> str:
    return (os.getenv("PLAID_ENV") or "sandbox").strip().lower()


def _build_client() -> plaid_api.PlaidApi:
    client_id = (os.getenv("PLAID_CLIENT_ID") or "").strip()
    secret = (os.getenv("PLAID_SECRET") or "").strip()
    if not client_id or not secret:
        raise PlaidConfigurationError(
            "PLAID_CLIENT_ID and PLAID_SECRET must be set to use Plaid integration."
        )
    configuration = plaid.Configuration(
        host=_env_to_host(get_plaid_env_name()),
        api_key={
            "clientId": client_id,
            "secret": secret,
            "plaidVersion": PLAID_API_VERSION,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def get_client() -> plaid_api.PlaidApi:
    """Return a Plaid API client. Raises PlaidConfigurationError if unconfigured."""
    return _build_client()


def products_from_strings(names: Iterable[str] | None = None) -> list[Products]:
    items = list(names) if names else list(DEFAULT_PRODUCTS)
    return [Products(name) for name in items]


def country_codes_from_strings(codes: Iterable[str] | None = None) -> list[CountryCode]:
    items = list(codes) if codes else list(DEFAULT_COUNTRY_CODES)
    return [CountryCode(code) for code in items]


def redact_token(token: str | None) -> str:
    """Return a safe-for-logs representation of an access / public token."""
    if not token:
        return "<empty>"
    length = len(token)
    if length <= 8:
        return "*" * length
    return f"{token[:4]}…{token[-4:]} (len={length})"
