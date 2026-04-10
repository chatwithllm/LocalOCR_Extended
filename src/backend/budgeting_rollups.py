"""Helpers for line-item-based spending allocations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from src.backend.budgeting_domains import (
    default_budget_category_for_spending_domain,
    normalize_budget_category,
    normalize_spending_domain,
)


def month_bounds(month: str) -> tuple[datetime, datetime]:
    year, month_num = month.split("-")
    start_date = datetime(int(year), int(month_num), 1)
    if int(month_num) == 12:
        end_date = datetime(int(year) + 1, 1, 1)
    else:
        end_date = datetime(int(year), int(month_num) + 1, 1)
    return start_date, end_date


def purchase_defaults(purchase) -> tuple[str, str]:
    spending_domain = normalize_spending_domain(
        getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", None),
        default="other",
    )
    budget_category = normalize_budget_category(
        getattr(purchase, "default_budget_category", None),
        default=default_budget_category_for_spending_domain(spending_domain),
    )
    return spending_domain, budget_category


def effective_item_classification(purchase, receipt_item) -> tuple[str, str]:
    default_domain, default_category = purchase_defaults(purchase)
    spending_domain = normalize_spending_domain(getattr(receipt_item, "spending_domain", None), default=default_domain)
    budget_category = normalize_budget_category(
        getattr(receipt_item, "budget_category", None),
        default=default_category,
    )
    return spending_domain, budget_category


def calculate_budget_allocations(purchases, receipt_items_by_purchase):
    categories = defaultdict(lambda: {"spent": 0.0, "purchase_ids": set(), "line_count": 0})
    domains = defaultdict(lambda: {"spent": 0.0, "purchase_ids": set(), "line_count": 0})

    for purchase in purchases:
        items = list(receipt_items_by_purchase.get(purchase.id, []))
        default_domain, default_category = purchase_defaults(purchase)
        total_amount = float(getattr(purchase, "total_amount", 0) or 0)

        if not items:
            categories[default_category]["spent"] += total_amount
            categories[default_category]["purchase_ids"].add(purchase.id)
            domains[default_domain]["spent"] += total_amount
            domains[default_domain]["purchase_ids"].add(purchase.id)
            continue

        line_totals = []
        subtotal = 0.0
        for item in items:
            line_total = float(getattr(item, "quantity", 0) or 0) * float(getattr(item, "unit_price", 0) or 0)
            item_domain, item_category = effective_item_classification(purchase, item)
            line_totals.append((item_domain, item_category, line_total))
            subtotal += line_total
            categories[item_category]["spent"] += line_total
            categories[item_category]["purchase_ids"].add(purchase.id)
            categories[item_category]["line_count"] += 1
            domains[item_domain]["spent"] += line_total
            domains[item_domain]["purchase_ids"].add(purchase.id)
            domains[item_domain]["line_count"] += 1

        remainder = total_amount - subtotal
        if abs(remainder) < 0.0001:
            continue

        if subtotal > 0 and line_totals:
            category_shares = defaultdict(float)
            domain_shares = defaultdict(float)
            for item_domain, item_category, line_total in line_totals:
                share = line_total / subtotal
                category_shares[item_category] += share
                domain_shares[item_domain] += share
            for item_category, share in category_shares.items():
                categories[item_category]["spent"] += remainder * share
                categories[item_category]["purchase_ids"].add(purchase.id)
            for item_domain, share in domain_shares.items():
                domains[item_domain]["spent"] += remainder * share
                domains[item_domain]["purchase_ids"].add(purchase.id)
        else:
            categories[default_category]["spent"] += total_amount
            categories[default_category]["purchase_ids"].add(purchase.id)
            domains[default_domain]["spent"] += total_amount
            domains[default_domain]["purchase_ids"].add(purchase.id)

    def finalize(bucket_map):
        return sorted(
            [
                {
                    "key": key,
                    "spent": round(values["spent"], 2),
                    "purchase_count": len(values["purchase_ids"]),
                    "line_count": values["line_count"],
                }
                for key, values in bucket_map.items()
            ],
            key=lambda item: (-item["spent"], item["key"]),
        )

    return {
        "categories": finalize(categories),
        "domains": finalize(domains),
    }


def calculate_budget_breakdowns(purchases, receipt_items_by_purchase):
    breakdowns = defaultdict(list)

    for purchase in purchases:
        items = list(receipt_items_by_purchase.get(purchase.id, []))
        default_domain, default_category = purchase_defaults(purchase)
        total_amount = float(getattr(purchase, "total_amount", 0) or 0)
        purchase_breakdown = defaultdict(lambda: {"amount": 0.0, "items": []})

        if not items:
            purchase_breakdown[default_category]["amount"] += total_amount
        else:
            line_totals = []
            subtotal = 0.0
            for item in items:
                line_total = float(getattr(item, "quantity", 0) or 0) * float(getattr(item, "unit_price", 0) or 0)
                _, item_category = effective_item_classification(purchase, item)
                line_totals.append((item_category, line_total))
                subtotal += line_total
                purchase_breakdown[item_category]["amount"] += line_total
                purchase_breakdown[item_category]["items"].append({
                    "name": getattr(item, "name", None) or getattr(item, "product_name", None) or "Unknown",
                    "quantity": float(getattr(item, "quantity", 0) or 0),
                    "amount": round(line_total, 2),
                })

            remainder = total_amount - subtotal
            if abs(remainder) >= 0.0001:
                if subtotal > 0 and line_totals:
                    shares = defaultdict(float)
                    for item_category, line_total in line_totals:
                        shares[item_category] += line_total / subtotal
                    for item_category, share in shares.items():
                        purchase_breakdown[item_category]["amount"] += remainder * share
                else:
                    purchase_breakdown[default_category]["amount"] += total_amount

        for category, entry in purchase_breakdown.items():
            breakdowns[category].append({
                "purchase_id": getattr(purchase, "id", None),
                "store": getattr(purchase, "store_name", None) or getattr(purchase, "merchant", None) or "Unknown",
                "date": getattr(purchase, "date", None).strftime("%Y-%m-%d") if getattr(purchase, "date", None) else None,
                "amount": round(entry["amount"], 2),
                "items": entry["items"][:5],
            })

    for category in breakdowns:
        breakdowns[category].sort(key=lambda row: (-row["amount"], row.get("date") or ""))
    return breakdowns
