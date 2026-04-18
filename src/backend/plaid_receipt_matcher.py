"""
Fuzzy matching between Plaid staged transactions and existing Purchase rows.

Used by /plaid/staged-transactions/<id>/confirm (and bulk-confirm) so we do
NOT create a duplicate receipt when the same charge is already captured —
either via a photo upload, a forwarded email receipt, or a prior manual
entry.

Public API
----------
- merchants_match(a, b) -> bool
    Loose-but-not-sloppy merchant comparison. Survives card-descriptor vs
    legal-name drift ("Anthropic, Pbc" vs "Claude.Ai Su") via an alias table.

- find_matching_purchase(session, user_id, amount, date, merchant_name) -> Purchase | None
    Returns an existing Purchase that likely represents the same charge,
    or None. Tolerances: |Δamount| ≤ $0.02, |Δdate| ≤ 3 days, merchant
    match per merchants_match().
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.backend.initialize_database_schema import Purchase, Store


# --- Tolerances -----------------------------------------------------------
AMOUNT_EPSILON = 0.02        # US dollars — cent-level match
DATE_WINDOW_DAYS = 3         # ±3 days (receipt vs post date drift)
MIN_TOKEN_OVERLAP_LEN = 4    # "anth", "clau", "amzn"


# --- Merchant alias table -------------------------------------------------
# When the card descriptor differs from the legal/DBA name, both sides
# should map to the same canonical token. Add entries here as new dupes
# surface.
MERCHANT_ALIASES: dict[str, set[str]] = {
    "claude.ai":   {"anthropic", "claude", "claude.ai", "claude ai", "claudeai", "anthropic pbc"},
    "openai":      {"openai", "chatgpt", "open ai", "openai.com"},
    "apple":       {"apple.com/bill", "apple services", "apple.com bill", "itunes"},
    "amazon":      {"amazon", "amzn", "amzn mktp", "amazon.com", "amazon mktplace", "amazon prime"},
    "netflix":     {"netflix", "netflix.com"},
    "spotify":     {"spotify", "spotify usa"},
    "costco":      {"costco", "costco whse", "costco wholesale"},
    "walmart":     {"walmart", "wal-mart", "wm supercenter", "wal mart"},
    "target":      {"target", "tgt"},
    "whole foods": {"whole foods", "wfm", "wholefds"},
    "trader joe":  {"trader joe", "traderjoe", "trader joes", "trader joe's"},
    "meijer":      {"meijer"},
    "kroger":      {"kroger"},
    "tesla":       {"tesla", "tesla motors", "tesla inc"},
    "at&t":        {"at&t", "att ", "att*", "at t"},
    "taxslayer":   {"taxslayer", "taxslayer llc"},
    "citizens energy": {"citizens energy", "citizens energy group"},
    "chase":       {"chase credit crd", "chase card", "chase"},
}


def _norm(text: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _alias_key(text: str) -> Optional[str]:
    """Return canonical alias key if text contains any known alias."""
    if not text:
        return None
    for canonical, aliases in MERCHANT_ALIASES.items():
        if any(alias in text for alias in aliases):
            return canonical
    return None


def merchants_match(a: Optional[str], b: Optional[str]) -> bool:
    """Loose-but-not-sloppy merchant comparison.

    - Exact match after normalization → match
    - Both map to the same alias key → match
    - Share at least one token of length ≥ MIN_TOKEN_OVERLAP_LEN → match
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ka, kb = _alias_key(na), _alias_key(nb)
    if ka and kb and ka == kb:
        return True
    toks_a = {t for t in na.split() if len(t) >= MIN_TOKEN_OVERLAP_LEN}
    toks_b = {t for t in nb.split() if len(t) >= MIN_TOKEN_OVERLAP_LEN}
    return bool(toks_a & toks_b)


def find_matching_purchase(
    session: Session,
    user_id: int,
    amount: float,
    date,                            # datetime.date | datetime.datetime
    merchant_name: Optional[str],
) -> Optional[Purchase]:
    """Return a Purchase likely representing the same charge, or None.

    Criteria (all three must hold):
      - |Purchase.total_amount| within AMOUNT_EPSILON of |amount|
      - Purchase.date within ±DATE_WINDOW_DAYS of `date`
      - merchants_match(merchant_name, purchase.store.name)

    Narrowest-scoring match is returned (most-recent Purchase id on ties).
    """
    if amount is None or date is None:
        return None

    target = abs(float(amount))
    lo = date - timedelta(days=DATE_WINDOW_DAYS)
    hi = date + timedelta(days=DATE_WINDOW_DAYS + 1)  # include end-of-day

    rows = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= lo)
        .filter(Purchase.date < hi)
        .filter(
            func.abs(func.coalesce(Purchase.total_amount, 0.0) - target) <= AMOUNT_EPSILON
        )
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .all()
    )

    for purchase, store in rows:
        store_name = store.name if store is not None else None
        if merchants_match(merchant_name, store_name):
            return purchase
    return None
