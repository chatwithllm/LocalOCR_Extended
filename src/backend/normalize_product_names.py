"""
Helpers for standardizing product names and merging obvious duplicates.
"""

from __future__ import annotations

import re

from sqlalchemy import func, or_

PRODUCT_ALIAS_RULES = [
    {
        "pattern": re.compile(r"\bhtgf\b.*\bchk\b.*\bthigh\b", re.IGNORECASE),
        "name": "Heritage Farm Chicken Thighs",
        "category": "meat",
    },
    {
        "pattern": re.compile(r"\bahoxi\b.*\b200\s*lds\b", re.IGNORECASE),
        "name": "Laundry Detergent",
        "category": "household",
    },
    {
        "pattern": re.compile(r"\bk\s*s?\s*oxi\s*pacs?\b|\bksoxipacs\b", re.IGNORECASE),
        "name": "Laundry Detergent Pacs",
        "category": "household",
    },
]

CANONICAL_NAME_MAP = {
    "org spinach": "Organic Spinach",
    "organic spinach": "Organic Spinach",
    "vine tomato": "Vine Tomato",
    "vine tomatoes": "Vine Tomato",
}


def _normalized_product_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def canonicalize_product_identity(name: str, category: str | None = None) -> tuple[str, str]:
    """Return the best canonical shopping-friendly name/category pair."""
    normalized_name = canonicalize_product_name(name)
    normalized_category = normalize_product_category(category)
    key = _normalized_product_key(name)

    for rule in PRODUCT_ALIAS_RULES:
        if rule["pattern"].search(key):
            return rule["name"], rule["category"]

    return normalized_name, normalized_category


def get_product_display_name(product) -> str:
    return getattr(product, "display_name", None) or getattr(product, "name", None) or "Unknown Item"


def canonicalize_product_name(name: str) -> str:
    """Normalize OCR-heavy product names into a consistent display form."""
    text = re.sub(r"\s+", " ", str(name or "").strip())
    if not text:
        return "Unknown Item"

    mapped = CANONICAL_NAME_MAP.get(_normalized_product_key(text))
    if mapped:
        return mapped

    known_upper_tokens = {"KS", "HBO", "ABF", "CK", "CAD", "TV", "BD"}
    token_aliases = {
        "org": "Organic",
    }

    def normalize_token(token: str) -> str:
        if not token:
            return token
        mapped_token = token_aliases.get(token.lower())
        if mapped_token:
            return mapped_token
        if re.fullmatch(r"[A-Z0-9/&+-]{2,}", token):
            if any(ch.isdigit() for ch in token):
                return token.upper()
            if token.upper() in known_upper_tokens:
                return token.upper()
        if "/" in token:
            return "/".join(normalize_token(part) for part in token.split("/"))
        if "-" in token:
            return "-".join(normalize_token(part) for part in token.split("-"))
        return token[:1].upper() + token[1:].lower()

    return " ".join(normalize_token(token) for token in text.split(" "))


def normalize_product_category(category: str | None) -> str:
    return str(category or "other").strip().lower() or "other"


def find_matching_product(session, name: str, category: str) -> Product | None:
    """Look up a product by normalized, case-insensitive name within a category."""
    from src.backend.initialize_database_schema import Product

    normalized_category = normalize_product_category(category)
    raw_candidate = canonicalize_product_name(name)
    normalized_name, _normalized_category = canonicalize_product_identity(name, category)
    return (
        session.query(Product)
        .filter(
            or_(
                func.lower(Product.name) == normalized_name.lower(),
                func.lower(func.coalesce(Product.raw_name, "")) == raw_candidate.lower(),
                func.lower(func.coalesce(Product.display_name, "")) == normalized_name.lower(),
            )
        )
        .filter(func.lower(func.coalesce(Product.category, "other")) == normalized_category)
        .order_by(Product.id.asc())
        .first()
    )


def merge_case_variant_products(session) -> int:
    """Merge products that only differ by case/spacing within the same category."""
    from src.backend.initialize_database_schema import Product
    from src.backend.manage_product_catalog import _merge_products

    products = session.query(Product).order_by(Product.id.asc()).all()
    grouped_products: dict[tuple[str, str], list[Product]] = {}
    merged_count = 0

    for product in products:
        canonical_name, canonical_category = canonicalize_product_identity(product.name, product.category)
        key = (canonical_name.lower(), canonical_category)
        grouped_products.setdefault(key, []).append(product)

    keeper_targets: list[tuple[Product, str, str]] = []

    with session.no_autoflush:
        for (_canonical_name_lower, canonical_category), group in grouped_products.items():
            canonical_name = canonicalize_product_name(group[0].name)
            keeper = group[0]
            keeper_targets.append((keeper, canonical_name, canonical_category))

            for duplicate in group[1:]:
                if not keeper.raw_name and duplicate.raw_name:
                    keeper.raw_name = duplicate.raw_name
                if not keeper.display_name:
                    keeper.display_name = keeper.name
                if not keeper.brand and getattr(duplicate, "brand", None):
                    keeper.brand = duplicate.brand
                if not keeper.size and getattr(duplicate, "size", None):
                    keeper.size = duplicate.size
                if not keeper.enrichment_confidence and getattr(duplicate, "enrichment_confidence", None):
                    keeper.enrichment_confidence = duplicate.enrichment_confidence
                if not keeper.enriched_at and getattr(duplicate, "enriched_at", None):
                    keeper.enriched_at = duplicate.enriched_at
                keeper = _merge_products(session, keeper, duplicate)
                merged_count += 1

    session.flush()

    for keeper, canonical_name, canonical_category in keeper_targets:
        keeper.name = canonical_name
        keeper.display_name = canonical_name
        keeper.category = canonical_category
        if not keeper.raw_name:
            keeper.raw_name = canonical_name

    return merged_count
