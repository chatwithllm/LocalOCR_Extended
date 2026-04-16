"""
Plaid transaction → LocalOCR receipt mapper + deduplication helpers.

Pure functions so they can be unit-tested in isolation; the caller owns
the database session. The mapper produces suggestions; the user still
reviews before anything is written to the receipts table (Phase 4).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from src.backend.initialize_database_schema import (
    PlaidStagedTransaction,
    Purchase,
    Store,
)


logger = logging.getLogger(__name__)


# Plaid category primary names (personal_finance_category.primary) we map.
# Fallback covers legacy top-level category strings too.
# Reference: https://plaid.com/docs/api/products/transactions/#transactionsget
PLAID_CATEGORY_MAP = {
    # (primary, default_receipt_type, default_spending_domain, default_budget_category)
    "FOOD_AND_DRINK": ("restaurant", "restaurant", "dining"),
    "Food and Drink": ("restaurant", "restaurant", "dining"),
    "GENERAL_MERCHANDISE": ("general_expense", "general_expense", "other"),
    "Shops": ("general_expense", "general_expense", "other"),
    "ENTERTAINMENT": ("general_expense", "general_expense", "other"),
    "Recreation": ("general_expense", "general_expense", "other"),
    "PERSONAL_CARE": ("general_expense", "general_expense", "other"),
    "MEDICAL": ("general_expense", "general_expense", "health"),
    "Healthcare": ("general_expense", "general_expense", "health"),
    "TRAVEL": ("general_expense", "general_expense", "other"),
    "Travel": ("general_expense", "general_expense", "other"),
    "GENERAL_SERVICES": ("general_expense", "general_expense", "other"),
    "Service": ("general_expense", "general_expense", "other"),
    "HOME_IMPROVEMENT": ("general_expense", "general_expense", "other"),
    "RENT_AND_UTILITIES": ("household_bill", "household_obligations", "utilities"),
    "Payment": ("household_bill", "household_obligations", "other_recurring"),
    "LOAN_PAYMENTS": ("household_bill", "household_obligations", "other_recurring"),
    "GOVERNMENT_AND_NON_PROFIT": ("general_expense", "general_expense", "other"),
    "INCOME": ("unknown", "general_expense", "other"),
    "TRANSFER_IN": ("unknown", "general_expense", "other"),
    "TRANSFER_OUT": ("unknown", "general_expense", "other"),
    "Transfer": ("unknown", "general_expense", "other"),
    "BANK_FEES": ("general_expense", "general_expense", "other"),
}

# Grocery-store hint: if merchant name matches any of these substrings AND
# primary category is Food and Drink, route to Grocery instead of Restaurant.
GROCERY_MERCHANT_HINTS = (
    "market",
    "grocery",
    "mart",
    "aldi",
    "costco",
    "sam's club",
    "sams club",
    "walmart",
    "target",
    "whole foods",
    "trader joe",
    "kroger",
    "safeway",
    "publix",
    "wegman",
    "heb",
    "meijer",
    "giant",
    "food lion",
    "stop & shop",
    "stop and shop",
    "sprouts",
    "winn-dixie",
    "piggly wiggly",
    "shoprite",
    "foodmaxx",
    "food 4 less",
    "ralphs",
    "ralph's",
    "fresh thyme",
    "price chopper",
    "harris teeter",
)

# Utility-bill hint: routes Payment / Service to Household Bill with utilities cat.
UTILITY_MERCHANT_HINTS = (
    "energy",
    "electric",
    "power",
    "water",
    "gas",
    "utility",
    "utilities",
    "sewer",
    "sewage",
    "waste",
    "trash",
    "comcast",
    "xfinity",
    "verizon",
    "at&t",
    "att",
    "t-mobile",
    "tmobile",
    "spectrum",
    "cox",
    "internet",
)

# Transfer / deposit should be skipped from receipt mapping.
SKIP_CATEGORIES = {"TRANSFER_IN", "TRANSFER_OUT", "INCOME", "Transfer", "Deposit"}


def _match_any(text: str, hints: Iterable[str]) -> bool:
    haystack = (text or "").strip().lower()
    if not haystack:
        return False
    return any(hint in haystack for hint in hints)


def map_plaid_transaction(staged: PlaidStagedTransaction) -> dict:
    """Return suggested {receipt_type, spending_domain, budget_category, skip} for a staged txn.

    - skip=True means this is a transfer/deposit the user should review but not auto-import.
    - Refunds are flagged when amount < 0 (Plaid convention: positive = debit).
    """
    primary = (staged.plaid_category_primary or "").strip()
    merchant = staged.merchant_name or staged.name or ""

    if primary in SKIP_CATEGORIES:
        return {
            "receipt_type": "unknown",
            "spending_domain": "general_expense",
            "budget_category": "other",
            "skip": True,
            "transaction_type": "purchase" if float(staged.amount or 0) >= 0 else "refund",
        }

    mapped = PLAID_CATEGORY_MAP.get(primary)

    if mapped:
        receipt_type, spending_domain, budget_category = mapped
    else:
        receipt_type, spending_domain, budget_category = ("general_expense", "general_expense", "other")

    # Food and Drink → Grocery if merchant is clearly a grocery store
    if primary in {"FOOD_AND_DRINK", "Food and Drink"} and _match_any(merchant, GROCERY_MERCHANT_HINTS):
        receipt_type = "grocery"
        spending_domain = "grocery"
        budget_category = "grocery"

    # Payment / Service with utility-ish merchant → Household Bill
    if primary in {"Payment", "GENERAL_SERVICES", "Service"} and _match_any(merchant, UTILITY_MERCHANT_HINTS):
        receipt_type = "household_bill"
        spending_domain = "household_obligations"
        budget_category = "utilities"

    transaction_type = "purchase" if float(staged.amount or 0) >= 0 else "refund"

    return {
        "receipt_type": receipt_type,
        "spending_domain": spending_domain,
        "budget_category": budget_category,
        "skip": False,
        "transaction_type": transaction_type,
    }


def run_dedup_check(session: Session, staged: PlaidStagedTransaction) -> int | None:
    """Return Purchase.id of a likely duplicate receipt, or None.

    Match rules:
    1. A Purchase with the same Plaid transaction id already promoted — via
       TelegramReceipt.telegram_user_id prefix (checked elsewhere, not here).
    2. Same date + absolute(total) within $0.01 + store-name partial match.
    """
    txn_date = staged.transaction_date
    if not txn_date:
        return None
    target_amount = abs(float(staged.amount or 0))
    if target_amount <= 0:
        return None
    merchant_key = (staged.merchant_name or staged.name or "").strip().lower()
    if not merchant_key:
        return None

    window_start = txn_date - timedelta(days=1)
    window_end = txn_date + timedelta(days=1)

    candidates = (
        session.query(Purchase, Store)
        .outerjoin(Store, Store.id == Purchase.store_id)
        .filter(Purchase.date >= datetime.combine(window_start, datetime.min.time()))
        .filter(Purchase.date <= datetime.combine(window_end, datetime.max.time()))
        .all()
    )
    for purchase, store in candidates:
        if abs(abs(float(purchase.total_amount or 0)) - target_amount) > 0.01:
            continue
        store_name = (store.name if store else "") or ""
        store_key = store_name.strip().lower()
        if not store_key:
            continue
        # Loose match: either string contains the other.
        if merchant_key in store_key or store_key in merchant_key:
            return purchase.id
    return None


def annotate_staged_transaction(
    session: Session,
    staged: PlaidStagedTransaction,
) -> PlaidStagedTransaction:
    """Populate suggested_* fields + dedup status on a staged row.

    Caller is responsible for session.commit(). Idempotent — safe to run
    after every sync.
    """
    suggestion = map_plaid_transaction(staged)
    staged.suggested_receipt_type = suggestion["receipt_type"]
    staged.suggested_spending_domain = suggestion["spending_domain"]
    staged.suggested_budget_category = suggestion["budget_category"]

    if staged.status in {"confirmed", "dismissed"}:
        return staged

    # Transfers / deposits / income → skip the review queue (user can opt in later)
    if suggestion["skip"]:
        staged.status = "skipped_pending"
        return staged

    if staged.pending:
        staged.status = "skipped_pending"
        return staged

    dup_id = run_dedup_check(session, staged)
    if dup_id is not None:
        staged.duplicate_purchase_id = dup_id
        staged.status = "duplicate_flagged"
    else:
        staged.duplicate_purchase_id = None
        if staged.status != "ready_to_import":
            staged.status = "ready_to_import"
    return staged


def annotate_all_ready_staged(session: Session, plaid_item_id: int | None = None) -> int:
    """Re-run annotation for every staged row that still needs review.

    Returns the number of rows touched. Safe to call after every sync.
    """
    query = session.query(PlaidStagedTransaction).filter(
        PlaidStagedTransaction.status.in_(
            ["ready_to_import", "duplicate_flagged", "skipped_pending"]
        )
    )
    if plaid_item_id is not None:
        query = query.filter(PlaidStagedTransaction.plaid_item_id == plaid_item_id)
    rows = query.all()
    for staged in rows:
        annotate_staged_transaction(session, staged)
    return len(rows)
