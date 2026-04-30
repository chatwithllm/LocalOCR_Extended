"""
Helpers for standardizing store names and merging obvious duplicates.

Also exposes ``is_payment_artifact`` — a predicate for detecting credit-card
payments, autopay rows, and similar bank-statement artifacts that get
mis-promoted into the Stores table from Plaid transactions. These rows
clutter the Stores dropdown without representing actual merchants.
"""

from __future__ import annotations

import re


# Substrings that mark a row as a credit-card / autopay / interest / fee
# artifact rather than a real merchant. Matched against the lowercased
# original name (preserving punctuation/spaces) for cheap, high-precision hits.
_PAYMENT_ARTIFACT_NEEDLES = (
    "auto-pmt",
    "auto pmt",
    "autopay",
    "auto pay",
    "credit crd",
    "credit card bill",
    "credit card payment",
    "card payment",
    "bill payment",
    "bill pay",
    "online payment",
    "online scheduled payment",
    "scheduled payment",
    "mobile payment",
    "ach payment",
    "ach pmt",
    "ach debit",
    "ach credit",
    "ach transfer",
    "webpay",
    "web pay",
    "des:",
    "interest charged",
    "interest charge",
    "finance charge",
    "late fee",
    "annual fee",
    "service charge",
    "overdraft",
    "transfer in",
    "transfer out",
    "wire transfer",
    "zelle",
    "venmo cashout",
    "paypal transfer",
    " id:",
    "from chk",
    "to chk",
    "from crd",
    "to crd",
    "confirmation#",
    "conf#",
    "conf #",
    "thank you",
    "payment thank",
)

# Whole-name patterns (after lowercasing + collapsing whitespace) that mark
# the row as a credit-card brand / issuer rather than a merchant.
_CC_BRAND_RE = re.compile(
    r"\b("
    r"chase\s+(?:sapphire|freedom|ink|amazon|united|southwest|hyatt|disney|marriott|ihg|aeroplan)"
    r"|amex|american\s+express"
    r"|capital\s+one|cap\s+one"
    r"|discover\s+card|discover\s+it"
    r"|citi(?:bank)?\s+(?:card|double|premier|prestige|aadvantage|costco)"
    r"|barclays?\s+(?:card|view|aviator|jetblue)"
    r"|wells\s+fargo\s+(?:card|active|reflect|autograph|propel)"
    r"|bank\s+of\s+america\s+(?:card|customized|travel|premium|cash\s+rewards)"
    r"|usaa\s+card"
    r"|synchrony"
    r"|mastercard|visa\s+card|visa\s+signature"
    r")\b"
)


def is_payment_artifact(name: str) -> bool:
    """Return True when ``name`` looks like a bank/CC artifact, not a store.

    Used to filter the Stores dropdown and to flag legacy rows during cleanup.
    Conservative on purpose — matches obvious payment / autopay / interest /
    transfer phrasing and well-known credit-card brand SKUs.
    """
    text = re.sub(r"\s+", " ", str(name or "").strip().lower())
    if not text:
        return False
    for needle in _PAYMENT_ARTIFACT_NEEDLES:
        if needle in text:
            return True
    if _CC_BRAND_RE.search(text):
        return True
    # "id:xxxxxxx" trailing identifier (>=5 alnum) that some banks append.
    if re.search(r"\bid:[a-z0-9]{5,}", text):
        return True
    return False


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

    # Costco — collapse "Costco Wholesale", "Costco #123", "COSTCO WHSE" etc.
    # Keep "Costco Tire Center" / "Costco Gas" distinct since they're separate
    # business units that show up on receipts under their own names.
    if "costco" in compact and "tirecenter" not in compact and "gas" not in compact:
        return "Costco"

    # Indian/India Bazar appears on receipts with a few close variants and
    # frequent typos (double-a, extra n, OCR slips).
    india_bazar_variants = {
        "indiabazar",
        "indiabazarinc",
        "indianbazar",
        "indianbazarinc",
        "indiaabazar",
        "indiabazaar",
        "indianbazaar",
        "indiaabazaar",
    }
    if compact in india_bazar_variants:
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
