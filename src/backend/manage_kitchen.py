# src/backend/manage_kitchen.py
"""Kitchen view aggregator and product categorization.

Pure functions only — no Flask request context. Endpoint layer lives in
`manage_kitchen_endpoint.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

FREQUENCY_WINDOW_DAYS = 90
FREQUENT_LIMIT = 12
CATEGORY_LIMIT = 50

DEFAULT_CATEGORIES = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"]

CATEGORY_EMOJI = {
    "Produce": "🥬",
    "Meat": "🥩",
    "Dairy": "🥛",
    "Bakery": "🍞",
    "Pantry": "🥫",
    "Other": "🧴",
}

# Raw Product.category values that map into each bucket. Lowercased
# substring match — first hit wins, evaluated in DEFAULT_CATEGORIES order.
_CATEGORY_KEYWORDS = {
    "Produce": ("produce", "vegetable", "veggie", "fruit"),
    "Meat":    ("meat", "poultry", "chicken", "beef", "pork", "seafood", "fish"),
    "Dairy":   ("dairy", "milk", "cheese", "yogurt", "butter"),
    "Bakery":  ("bakery", "bread", "pastry", "cake"),
    "Pantry":  ("pantry", "snack", "beverage", "drink", "spice", "condiment",
                "grain", "rice", "pasta", "cereal", "canned", "frozen"),
}


def category_for_product(product) -> str:
    """Map a Product (or anything with a `.category` string attribute) to one
    of DEFAULT_CATEGORIES. Unknown / missing raw values fall back to "Other"."""
    raw = getattr(product, "category", None) or ""
    lowered = str(raw).strip().lower()
    if not lowered:
        return "Other"
    for bucket in DEFAULT_CATEGORIES:
        if bucket == "Other":
            continue
        keywords = _CATEGORY_KEYWORDS.get(bucket, ())
        for kw in keywords:
            if kw in lowered:
                return bucket
    return "Other"
