"""
Helpers for standardizing store names and merging obvious duplicates.
"""

from __future__ import annotations

import re


def canonicalize_store_name(name: str) -> str:
    """Normalize store names into a consistent display form."""
    text = re.sub(r"\s+", " ", str(name or "").strip())
    if not text:
        return "Unknown Store"

    compact = re.sub(r"[^a-z0-9]+", "", text.lower())

    # McDonald's receipts often append a location/store number such as
    # "#2674" or the word "Restaurant". We treat those as the same chain.
    if compact.startswith("mcdonald"):
        return "McDonald's"

    # Indian/India Bazar appears on receipts with a few close variants.
    if compact in {"indiabazar", "indiabazarinc", "indianbazar", "indianbazarinc"}:
        return "India Bazar"

    known_upper_tokens = {"CVS", "H-E-B", "HEB", "ALDI", "IKEA"}

    def normalize_token(token: str) -> str:
        if not token:
            return token
        if token.upper() in known_upper_tokens:
            return token.upper()
        if "/" in token:
            return "/".join(normalize_token(part) for part in token.split("/"))
        if "-" in token:
            return "-".join(normalize_token(part) for part in token.split("-"))
        return token[:1].upper() + token[1:].lower()

    return " ".join(normalize_token(token) for token in text.split(" "))


def find_matching_store(session, name: str):
    """Find a store by canonicalized, case-insensitive name."""
    from sqlalchemy import func

    from src.backend.initialize_database_schema import Store

    canonical_name = canonicalize_store_name(name)
    return (
        session.query(Store)
        .filter(func.lower(Store.name) == canonical_name.lower())
        .order_by(Store.id.asc())
        .first()
    )
