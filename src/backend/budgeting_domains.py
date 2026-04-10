"""Shared spending-domain and budget-category helpers."""

from __future__ import annotations

SPENDING_DOMAINS = {
    "grocery",
    "restaurant",
    "general_expense",
    "event",
    "other",
}

BUDGET_CATEGORIES = {
    "grocery",
    "dining",
    "housing",
    "insurance",
    "childcare",
    "health",
    "subscriptions",
    "household",
    "retail",
    "events",
    "other",
}


def normalize_spending_domain(value: str | None, default: str = "other") -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "general expense":
        normalized = "general_expense"
    return normalized if normalized in SPENDING_DOMAINS else default


def normalize_budget_category(value: str | None, default: str = "other") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"general_expense", "general expense"}:
        normalized = "other"
    return normalized if normalized in BUDGET_CATEGORIES else default


def default_budget_category_for_spending_domain(spending_domain: str | None) -> str:
    domain = normalize_spending_domain(spending_domain)
    if domain == "grocery":
        return "grocery"
    if domain == "restaurant":
        return "dining"
    if domain == "event":
        return "events"
    if domain == "general_expense":
        return "other"
    return "other"


def derive_receipt_budget_defaults(receipt_type: str | None) -> tuple[str, str]:
    normalized_type = normalize_spending_domain(receipt_type, default="other")
    return normalized_type, default_budget_category_for_spending_domain(normalized_type)
