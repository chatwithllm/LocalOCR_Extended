from __future__ import annotations

from datetime import datetime


BILLING_CYCLE_MONTHS = {
    "monthly": 1,
    "bimonthly": 2,
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
}


def normalize_billing_cycle(value: str | None, default: str = "monthly") -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "month": "monthly",
        "monthly": "monthly",
        "every_month": "monthly",
        "2_months": "bimonthly",
        "bimonthly": "bimonthly",
        "every_2_months": "bimonthly",
        "quarter": "quarterly",
        "quarterly": "quarterly",
        "every_3_months": "quarterly",
        "semiannual": "semiannual",
        "semi-annual": "semiannual",
        "semi_annually": "semiannual",
        "every_6_months": "semiannual",
        "half_yearly": "semiannual",
        "annual": "annual",
        "annually": "annual",
        "yearly": "annual",
        "every_12_months": "annual",
    }
    resolved = aliases.get(normalized, normalized)
    return resolved if resolved in BILLING_CYCLE_MONTHS else default


def billing_cycle_month_count(value: str | None) -> int:
    return BILLING_CYCLE_MONTHS[normalize_billing_cycle(value)]


def month_matches_billing_cycle(
    target_month: str,
    anchor_month: str | None,
    billing_cycle: str | None,
) -> bool:
    """Return whether target_month belongs to the cadence anchored at anchor_month."""
    normalized_cycle = normalize_billing_cycle(billing_cycle)
    interval = BILLING_CYCLE_MONTHS[normalized_cycle]
    if interval == 1:
        return True
    if not anchor_month:
        return True
    try:
        target = datetime.strptime(target_month, "%Y-%m")
        anchor = datetime.strptime(anchor_month, "%Y-%m")
    except ValueError:
        return True
    diff = (target.year - anchor.year) * 12 + (target.month - anchor.month)
    return diff % interval == 0
