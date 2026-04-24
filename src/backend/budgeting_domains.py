"""Shared spending-domain and budget-category helpers."""

from __future__ import annotations

SPENDING_DOMAINS = {
    "grocery",
    "restaurant",
    "general_expense",
    "household_obligations",
    "event",
    "entertainment",
    "utility",
    "other",
}

BUDGET_CATEGORIES = {
    "grocery",
    "dining",
    "utilities",
    "housing",
    "insurance",
    "childcare",
    "health",
    "subscriptions",
    "household",
    "retail",
    "events",
    "entertainment",
    "other_recurring",
    "other",
}

# Maps utility provider_type values to the appropriate budget_category.
# Used when classifying household-bill receipts so electricity, rent,
# daycare, and streaming subscriptions land in the right bucket.
UTILITY_PROVIDER_TYPE_TO_BUDGET_CATEGORY: dict[str, str] = {
    "electricity": "utilities",
    "water": "utilities",
    "sewage": "utilities",
    "gas": "utilities",
    "trash": "utilities",
    "internet": "utilities",
    "phone": "utilities",
    "cable": "utilities",
    "rent": "housing",
    "mortgage": "housing",
    "hoa": "housing",
    "insurance": "insurance",
    "daycare": "childcare",
    "school": "childcare",
    "gym": "subscriptions",
    "streaming": "subscriptions",
    "software": "subscriptions",
    "subscription": "subscriptions",
    "health": "health",
}

UTILITY_PROVIDER_TYPES: list[str] = [
    "electricity",
    "water",
    "sewage",
    "gas",
    "internet",
    "phone",
    "cable",
    "trash",
    "hoa",
    "rent",
    "mortgage",
    "insurance",
    "daycare",
    "school",
    "gym",
    "streaming",
    "software",
    "subscription",
    "health",
    "other",
]


def normalize_utility_service_types(values, provider_type: str | None = None) -> list[str]:
    normalized: list[str] = []
    candidates = values if isinstance(values, (list, tuple, set)) else [values]
    for value in candidates:
        key = str(value or "").strip().lower()
        if key and key in UTILITY_PROVIDER_TYPES and key not in normalized:
            normalized.append(key)
    fallback = str(provider_type or "").strip().lower()
    if fallback and fallback in UTILITY_PROVIDER_TYPES and fallback not in normalized:
        normalized.insert(0, fallback)
    return normalized


def normalize_spending_domain(value: str | None, default: str = "other") -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "general expense":
        normalized = "general_expense"
    if normalized in {"utility_bill", "household_bill", "utility"}:
        normalized = "household_obligations"
    return normalized if normalized in SPENDING_DOMAINS else default


def normalize_budget_category(value: str | None, default: str = "other") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"general_expense", "general expense"}:
        normalized = "other"
    if normalized in {"utility", "utilities"}:
        normalized = "utilities"
    if normalized in {"other recurring", "other-recurring"}:
        normalized = "other_recurring"
    return normalized if normalized in BUDGET_CATEGORIES else default


def default_budget_category_for_utility(
    provider_type: str | None,
    service_types: list[str] | None = None,
) -> str:
    """Return the budget category that best represents a household bill.

    Prefer provider_type when it maps to something concrete. If provider_type
    is missing or 'other', scan service_types and pick the first one that
    maps to a non-other_recurring category (covers multi-service bills like
    water/sewage/gas combined, where OCR leaves provider_type as 'other').
    """
    key = str(provider_type or "").strip().lower()
    mapped = UTILITY_PROVIDER_TYPE_TO_BUDGET_CATEGORY.get(key)
    if mapped:
        return mapped
    for service in service_types or []:
        svc_key = str(service or "").strip().lower()
        candidate = UTILITY_PROVIDER_TYPE_TO_BUDGET_CATEGORY.get(svc_key)
        if candidate:
            return candidate
    return "other_recurring"


def default_budget_category_for_spending_domain(
    spending_domain: str | None,
    provider_type: str | None = None,
    service_types: list[str] | None = None,
) -> str:
    domain = normalize_spending_domain(spending_domain)
    if domain == "grocery":
        return "grocery"
    if domain == "restaurant":
        return "dining"
    if domain == "event":
        return "events"
    if domain == "entertainment":
        return "entertainment"
    if domain == "general_expense":
        return "other"
    if domain in {"utility", "household_obligations"}:
        return default_budget_category_for_utility(provider_type, service_types)
    return "other"


def derive_receipt_budget_defaults(
    receipt_type: str | None,
    provider_type: str | None = None,
    service_types: list[str] | None = None,
) -> tuple[str, str]:
    """Return (spending_domain, budget_category) defaults for a given receipt type."""
    if str(receipt_type or "").strip().lower() in {"utility_bill", "household_bill"}:
        domain = "household_obligations"
        category = default_budget_category_for_utility(provider_type, service_types)
        return domain, category
    normalized_type = normalize_spending_domain(receipt_type, default="other")
    return normalized_type, default_budget_category_for_spending_domain(normalized_type)
