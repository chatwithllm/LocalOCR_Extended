# Chat Assistant: Temporal & Consumption Questions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `build_data_context` so the in-app chat assistant can answer "when did we shop lately", "how often do we shop", and "how much are we consuming" using a new lazy-loaded `shopping_activity` block.

**Architecture:** Two new helpers in `src/backend/chat_assistant.py` — `_extract_temporal_intent(message)` (regex-only, returns bool) and `_compute_shopping_activity(session, user, now)` (returns dict | None). Wire into the existing `build_data_context` after the item-search block; only fire the aggregator when the extractor returns True. Mirrors the existing lazy item-search pattern. Plus a system-prompt addendum so the model knows how to cite the new fields.

**Tech Stack:** Python 3.11, SQLAlchemy 1.4, pytest, in-memory SQLite for tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-25-chat-temporal-shopping-activity-design.md`

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `src/backend/chat_assistant.py` | Modify | Add `_extract_temporal_intent` + `_compute_shopping_activity`; wire into `build_data_context`; extend `SYSTEM_PROMPT` and `chat_complete` context_summary. |
| `tests/test_chat_temporal.py` | Create | New unit tests for extractor + aggregator + empty-data short-circuit + refund exclusion. Self-contained (in-memory SQLite, no Flask). |

No frontend changes. No DB migrations (existing `Purchase` and `ReceiptItem` tables already carry every field needed).

---

## Task 1: Temporal-intent extractor (TDD)

**Files:**
- Modify: `src/backend/chat_assistant.py` (add new helper near other extractors, around line 455)
- Create: `tests/test_chat_temporal.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_chat_temporal.py` with this exact content:

```python
"""Unit tests for the chat-assistant temporal-intent extractor and
shopping-activity aggregator. In-memory SQLite, no Flask, no network.
"""
import os

# Configure env BEFORE importing the project — chat_assistant.py touches
# AIModelConfig at import time which expects FERNET_SECRET_KEY.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FERNET_SECRET_KEY", "test-fernet-key-for-unit-tests-only")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")

import pytest

from src.backend.chat_assistant import _extract_temporal_intent


@pytest.mark.parametrize(
    "message",
    [
        "When did we shop lately?",
        "how often do we shop",
        "what's our consumption rate?",
        "show me recent shopping",
        "when was the last trip to the store",
        "we go pretty frequently right?",
        "how much are we consuming",
        "trend in our buying",
    ],
)
def test_temporal_intent_positive(message):
    assert _extract_temporal_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "how much did we spend on milk last month",
        "where do property taxes belong",
        "list uncategorized receipts",
        "show me the top stores",
        "what's the grocery total",
        "",
    ],
)
def test_temporal_intent_negative(message):
    assert _extract_temporal_intent(message) is False
```

- [ ] **Step 1.2: Run the tests to confirm they fail with import error**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: ImportError on `_extract_temporal_intent` (function does not exist yet).

- [ ] **Step 1.3: Add the extractor to `chat_assistant.py`**

Find the block at `src/backend/chat_assistant.py:455` (the `_extract_item_query_terms` function) and add this BEFORE it (so it lives next to the other extractor):

```python
# Temporal-intent extractor — gates the lazy `shopping_activity`
# block. Conservative: false positives just add ~1 KB to the data
# context; false negatives block the new feature, so when in doubt
# we let the regex match.
_TEMPORAL_INTENT_RE = re.compile(
    r"\b(when|lately|recent(ly)?|last\s+(time|visit|trip|shop)|"
    r"frequent(ly)?|often|trend|rate|consumption|consum(e|ing))\b"
    r"|how\s+(much|many|fast)\s+(do\s+)?(we|i)\s+(shop|consum|buy)"
    r"|how\s+often",
    re.IGNORECASE,
)


def _extract_temporal_intent(message: str | None) -> bool:
    """Return True if ``message`` looks like a recency / frequency /
    consumption question — recent visits, cadence, or rate-of-buying.
    Used by ``build_data_context`` to decide whether to compute the
    (relatively expensive) ``shopping_activity`` block.
    """
    if not message:
        return False
    return bool(_TEMPORAL_INTENT_RE.search(message))
```

- [ ] **Step 1.4: Run tests to confirm they pass**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: 14 passed (8 positive + 6 negative).

- [ ] **Step 1.5: Commit**

```bash
git add tests/test_chat_temporal.py src/backend/chat_assistant.py
git commit -m "feat(chat): temporal-intent extractor for shopping-activity gating"
```

---

## Task 2: Shopping-activity aggregator — windows + cadence (TDD)

**Files:**
- Modify: `src/backend/chat_assistant.py` (add `_compute_shopping_activity` near `_top_stores` / `_spend_by_person`, around line 380)
- Modify: `tests/test_chat_temporal.py` (add aggregator fixture + tests)

- [ ] **Step 2.1: Add the SQLAlchemy fixture + first failing test**

Append to `tests/test_chat_temporal.py`:

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.initialize_database_schema import (
    Base,
    Purchase,
    ReceiptItem,
    Store,
    User,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def household(session):
    """Two users + one store + a spread of receipts across 90 days.

    Layout (relative to NOW = 2026-04-25 UTC):
      - mom: 4 purchases inside 7d window, 12 in 30d total, 30 in 90d
      - dad: 2 purchases inside 7d, 6 in 30d, 18 in 90d
      - one refund row inside 7d (must be excluded from counts/spend)
    """
    mom = User(name="Mom", email="mom@example.com")
    dad = User(name="Dad", email="dad@example.com")
    session.add_all([mom, dad])
    session.flush()

    store = Store(name="Costco")
    session.add(store)
    session.flush()

    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def _add_purchase(days_ago, attr_user, amount, items=1, refund=False):
        p = Purchase(
            store_id=store.id,
            total_amount=amount,
            date=NOW - timedelta(days=days_ago),
            domain="grocery",
            transaction_type="refund" if refund else "purchase",
            attribution_user_id=attr_user.id,
            attribution_kind="personal",
            user_id=attr_user.id,
        )
        session.add(p)
        session.flush()
        for _ in range(items):
            session.add(ReceiptItem(
                purchase_id=p.id,
                product_id=1,
                quantity=1,
                unit_price=amount / max(items, 1),
                attribution_user_id=attr_user.id,
                attribution_kind="personal",
            ))
        return p

    # Mom: 4 in last 7d, 8 more in 8-30d (=12 in 30d), 18 more in 31-90d
    for d in [1, 2, 4, 6]:
        _add_purchase(d, mom, 50.0, items=3)
    for d in [10, 12, 14, 18, 22, 25, 27, 29]:
        _add_purchase(d, mom, 60.0, items=4)
    for d in range(31, 91, 4)[:18]:
        _add_purchase(d, mom, 70.0, items=2)

    # Dad: 2 in 7d, 4 more in 30d, 12 more in 90d
    for d in [3, 5]:
        _add_purchase(d, dad, 40.0, items=2)
    for d in [11, 16, 20, 24]:
        _add_purchase(d, dad, 45.0, items=3)
    for d in range(33, 91, 5)[:12]:
        _add_purchase(d, dad, 55.0, items=2)

    # Refund inside 7d — should NOT count
    _add_purchase(2, mom, 25.0, items=1, refund=True)

    session.commit()
    return {"mom": mom, "dad": dad, "store": store, "now": NOW}


def test_shopping_activity_windows_excludes_refunds(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    assert result is not None
    # 6 (mom in 7d) + 2 (dad in 7d) = 8; refund excluded
    assert result["windows"]["last_7d"]["trips"] == 6
    # mom 12 + dad 6 = 18 in 30d
    assert result["windows"]["last_30d"]["trips"] == 18


def test_shopping_activity_recent_receipts_top5(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    rec = result["recent_receipts"]
    assert len(rec) == 5
    # Sorted desc by date — first is the most recent (1 day ago)
    assert rec[0]["date"] == "2026-04-24"
    assert rec[0]["store"] == "Costco"
    assert rec[0]["attribution"] in ("Mom", "Dad")
    # No refunds in recent_receipts
    assert all("amount" in r and r["amount"] >= 0 for r in rec)


def test_shopping_activity_per_person_split(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    names = [p["name"] for p in result["per_person"]]
    assert "Mom" in names
    assert "Dad" in names
    mom_block = next(p for p in result["per_person"] if p["name"] == "Mom")
    # Mom had 4 purchases inside 7d (refund excluded)
    assert mom_block["windows"]["last_7d"]["trips"] == 4
    assert mom_block["last_trip"]["store"] == "Costco"


def test_shopping_activity_cadence_trend_classification(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    cad = result["cadence"]
    assert "trips_per_week_30d" in cad
    assert "trips_per_week_90d" in cad
    assert cad["trend"] in ("up", "down", "steady")


def test_shopping_activity_returns_none_on_empty_db(session):
    from src.backend.chat_assistant import _compute_shopping_activity
    user = User(name="Lonely", email="alone@example.com")
    session.add(user)
    session.commit()
    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    assert _compute_shopping_activity(session, user, NOW) is None
```

- [ ] **Step 2.2: Run tests to confirm they fail**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: 5 new tests fail with `ImportError` on `_compute_shopping_activity`.

- [ ] **Step 2.3: Add the aggregator to `chat_assistant.py`**

Insert this AFTER `_uncategorized_count` (around line 401) and BEFORE the `# Cheap-and-dirty stop-word list` comment:

```python
def _compute_shopping_activity(
    session,
    user: User,
    now: datetime,
) -> dict[str, Any] | None:
    """Recency / cadence / consumption rollup used to answer
    "when did we shop", "how often", and "how much are we consuming".

    Returns ``None`` when the household has zero purchase rows in the
    last 90 days. Refunds (``transaction_type == "refund"``) are
    excluded from every count and total. Per-person figures use the
    same attribution semantics as :func:`_spend_by_person` — split
    rows count toward each named person but the household roll-up
    counts each receipt only once.
    """
    import json as _json
    import sqlalchemy as _sa

    WINDOWS = {"last_7d": 7, "last_30d": 30, "last_90d": 90}
    cutoff_90 = now - timedelta(days=90)

    not_refund = _sa.or_(
        Purchase.transaction_type.is_(None),
        Purchase.transaction_type != "refund",
    )

    purchases_90 = (
        session.query(Purchase, Store.name)
        .outerjoin(Store, Store.id == Purchase.store_id)
        .filter(Purchase.date >= cutoff_90)
        .filter(not_refund)
        .order_by(Purchase.date.desc())
        .all()
    )
    if not purchases_90:
        return None

    purchase_ids = [p.id for p, _ in purchases_90]
    items_rows = (
        session.query(ReceiptItem.purchase_id)
        .filter(ReceiptItem.purchase_id.in_(purchase_ids))
        .all()
        if purchase_ids
        else []
    )
    items_by_purchase: dict[int, int] = {}
    for (pid,) in items_rows:
        items_by_purchase[pid] = items_by_purchase.get(pid, 0) + 1

    def _ids_from(obj) -> list[int]:
        raw = getattr(obj, "attribution_user_ids", None)
        if raw:
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, list):
                    return [int(x) for x in parsed if x is not None]
            except (TypeError, ValueError):
                pass
        legacy = getattr(obj, "attribution_user_id", None)
        return [int(legacy)] if legacy else []

    user_ids: set[int] = set()
    for p, _ in purchases_90:
        user_ids.update(_ids_from(p))
    user_names: dict[int, str] = {}
    if user_ids:
        for u in session.query(User).filter(User.id.in_(list(user_ids))).all():
            user_names[u.id] = u.name or u.email or f"User {u.id}"

    def _attr_label(p: Purchase) -> str | None:
        ids = _ids_from(p)
        if not ids:
            return None
        names = [user_names.get(uid) for uid in ids]
        names = [n for n in names if n]
        if not names:
            return None
        return " & ".join(names)

    # ---- Household windows ---------------------------------------
    def _agg(rows: list[Purchase]) -> dict[str, Any]:
        trips = len(rows)
        spend = round(sum(float(r.total_amount or 0.0) for r in rows), 2)
        items_count = sum(items_by_purchase.get(r.id, 0) for r in rows)
        return {"trips": trips, "spend": spend, "items_count": items_count}

    windows: dict[str, Any] = {}
    for label, days in WINDOWS.items():
        cutoff = now - timedelta(days=days)
        rows_in_window = [p for p, _ in purchases_90 if p.date >= cutoff]
        windows[label] = _agg(rows_in_window)

    # ---- Cadence + trend -----------------------------------------
    def _avg_gap(rows: list[Purchase]) -> float | None:
        if len(rows) < 2:
            return None
        sorted_rows = sorted(rows, key=lambda r: r.date)
        gaps = [
            (sorted_rows[i + 1].date - sorted_rows[i].date).total_seconds()
            / 86400.0
            for i in range(len(sorted_rows) - 1)
        ]
        return round(sum(gaps) / len(gaps), 2)

    rows_30 = [p for p, _ in purchases_90 if p.date >= now - timedelta(days=30)]
    rows_90 = [p for p, _ in purchases_90]
    tpw_30 = round(len(rows_30) / (30 / 7), 2) if rows_30 else 0.0
    tpw_90 = round(len(rows_90) / (90 / 7), 2) if rows_90 else 0.0
    if tpw_90 == 0:
        trend = "steady"
    elif tpw_30 > tpw_90 * 1.15:
        trend = "up"
    elif tpw_30 < tpw_90 * 0.85:
        trend = "down"
    else:
        trend = "steady"
    cadence = {
        "avg_gap_days_30d": _avg_gap(rows_30),
        "avg_gap_days_90d": _avg_gap(rows_90),
        "trips_per_week_30d": tpw_30,
        "trips_per_week_90d": tpw_90,
        "trend": trend,
    }

    # ---- Recent receipts (top 5 desc) ----------------------------
    recent_receipts = []
    for p, store_name in purchases_90[:5]:
        recent_receipts.append({
            "date": p.date.strftime("%Y-%m-%d") if p.date else None,
            "store": store_name or "Unknown",
            "amount": round(float(p.total_amount or 0.0), 2),
            "attribution": _attr_label(p),
        })

    # ---- Per-person blocks ---------------------------------------
    per_user_rows: dict[int, list[Purchase]] = {}
    for p, _ in purchases_90:
        for uid in _ids_from(p):
            per_user_rows.setdefault(uid, []).append(p)

    per_person = []
    for uid, rows in per_user_rows.items():
        name = user_names.get(uid, f"User {uid}")
        u_windows = {}
        for label, days in WINDOWS.items():
            cutoff = now - timedelta(days=days)
            sub = [r for r in rows if r.date >= cutoff]
            u_windows[label] = _agg(sub)
        u_rows_30 = [r for r in rows if r.date >= now - timedelta(days=30)]
        u_rows_90 = rows
        u_cadence = {
            "avg_gap_days_30d": _avg_gap(u_rows_30),
            "avg_gap_days_90d": _avg_gap(u_rows_90),
            "trips_per_week_30d": (
                round(len(u_rows_30) / (30 / 7), 2) if u_rows_30 else 0.0
            ),
            "trips_per_week_90d": (
                round(len(u_rows_90) / (90 / 7), 2) if u_rows_90 else 0.0
            ),
        }
        most_recent = sorted(rows, key=lambda r: r.date, reverse=True)[0]
        last_trip_store = (
            session.query(Store.name)
            .filter(Store.id == most_recent.store_id)
            .scalar()
        )
        last_trip = {
            "date": most_recent.date.strftime("%Y-%m-%d"),
            "store": last_trip_store or "Unknown",
            "amount": round(float(most_recent.total_amount or 0.0), 2),
        }
        per_person.append({
            "name": name,
            "windows": u_windows,
            "cadence": u_cadence,
            "last_trip": last_trip,
        })
    per_person.sort(key=lambda p: p["windows"]["last_30d"]["trips"], reverse=True)

    # ---- Top items (last 30d) ------------------------------------
    cutoff_30 = now - timedelta(days=30)
    top_items_rows = (
        session.query(
            ReceiptItem.product_id,
            _sa.func.count(ReceiptItem.id),
            _sa.func.sum(ReceiptItem.quantity * ReceiptItem.unit_price),
        )
        .join(Purchase, Purchase.id == ReceiptItem.purchase_id)
        .filter(Purchase.date >= cutoff_30)
        .filter(not_refund)
        .group_by(ReceiptItem.product_id)
        .order_by(_sa.func.count(ReceiptItem.id).desc())
        .limit(5)
        .all()
    )
    top_items = []
    if top_items_rows:
        from src.backend.initialize_database_schema import Product
        product_names = {
            row.id: row.name
            for row in session.query(Product.id, Product.name)
            .filter(Product.id.in_([pid for pid, _, _ in top_items_rows]))
            .all()
        }
        for pid, qty, spend in top_items_rows:
            top_items.append({
                "name": product_names.get(pid) or f"product#{pid}",
                "qty": int(qty or 0),
                "spend": round(float(spend or 0.0), 2),
            })

    return {
        "recent_receipts": recent_receipts,
        "windows": windows,
        "cadence": cadence,
        "per_person": per_person,
        "top_items_30d": top_items,
    }
```

- [ ] **Step 2.4: Run tests to confirm aggregator tests pass**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: all 19 tests pass (14 from Task 1 + 5 aggregator tests).

- [ ] **Step 2.5: Commit**

```bash
git add tests/test_chat_temporal.py src/backend/chat_assistant.py
git commit -m "feat(chat): _compute_shopping_activity aggregator + tests"
```

---

## Task 3: Wire the new block into `build_data_context`

**Files:**
- Modify: `src/backend/chat_assistant.py:781-801` (the return dict at the end of `build_data_context`)
- Modify: `tests/test_chat_temporal.py` (add an integration-style test for the wire-up)

- [ ] **Step 3.1: Write the wire-up test**

Append to `tests/test_chat_temporal.py`:

```python
def test_build_data_context_includes_shopping_activity_when_intent_hits(
    session, household,
):
    from src.backend import chat_assistant
    # Freeze "now" so the fixture's relative dates land in our windows.
    NOW = household["now"]
    real_datetime = chat_assistant.datetime

    class _FrozenDT(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    chat_assistant.datetime = _FrozenDT
    try:
        ctx = chat_assistant.build_data_context(
            session, household["mom"], user_message="when did we shop lately"
        )
        assert ctx["shopping_activity"] is not None
        assert ctx["shopping_activity"]["windows"]["last_7d"]["trips"] >= 1

        ctx2 = chat_assistant.build_data_context(
            session, household["mom"], user_message="how much did we spend on milk"
        )
        assert ctx2["shopping_activity"] is None
    finally:
        chat_assistant.datetime = real_datetime
```

- [ ] **Step 3.2: Run test to confirm failure**

Run: `pytest tests/test_chat_temporal.py::test_build_data_context_includes_shopping_activity_when_intent_hits -v`

Expected: KeyError or AssertionError on `ctx["shopping_activity"]`.

- [ ] **Step 3.3: Edit `build_data_context`**

In `src/backend/chat_assistant.py`, find the block at `build_data_context` ending around line 801. Replace the existing tail:

```python
    item_results = _search_items(session, item_terms) if item_terms else []

    return {
        # Intentionally minimal user identity — no email, no FK ids
        # the model could try to leak. Just the display name so it can
        # address the admin politely.
        "user": {"name": user.name},
        "current_month": cur_start.strftime("%Y-%m"),
        ...
        "categories_supported": sorted(BUDGET_CATEGORIES),
    }
```

With:

```python
    item_results = _search_items(session, item_terms) if item_terms else []

    shopping_activity = None
    if _extract_temporal_intent(user_message or ""):
        shopping_activity = _compute_shopping_activity(session, user, now)

    return {
        # Intentionally minimal user identity — no email, no FK ids
        # the model could try to leak. Just the display name so it can
        # address the admin politely.
        "user": {"name": user.name},
        "current_month": cur_start.strftime("%Y-%m"),
        "previous_month": prev_start.strftime("%Y-%m"),
        "month_total_current": round(sum(cur.values()), 2),
        "month_total_previous": round(sum(prev.values()), 2),
        "by_category": by_category,
        "top_stores_current_month": _top_stores(session, cur_start, cur_end),
        "uncategorized_count_current_month": _uncategorized_count(session, cur_start, cur_end),
        "spend_by_person_current_month": _spend_by_person(session, cur_start, cur_end),
        "spend_by_person_previous_month": _spend_by_person(session, prev_start, cur_start),
        "item_search_terms": item_terms,
        "item_search_results": item_results,
        "item_search_topic_carried_from_history": carried_from_history,
        "shopping_activity": shopping_activity,
        "categories_supported": sorted(BUDGET_CATEGORIES),
    }
```

(The only structural changes: a 3-line block computing `shopping_activity` after `item_results`, and one extra dict key `"shopping_activity": shopping_activity`. Every other field is unchanged.)

- [ ] **Step 3.4: Run the wire-up test**

Run: `pytest tests/test_chat_temporal.py::test_build_data_context_includes_shopping_activity_when_intent_hits -v`

Expected: PASS.

- [ ] **Step 3.5: Run the full chat test file**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: 20 tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add tests/test_chat_temporal.py src/backend/chat_assistant.py
git commit -m "feat(chat): wire shopping_activity block into build_data_context"
```

---

## Task 4: System-prompt addendum + context-summary chip

**Files:**
- Modify: `src/backend/chat_assistant.py:61-220` (`SYSTEM_PROMPT` text)
- Modify: `src/backend/chat_assistant.py:1053-1067` (`summary_parts` in `chat_complete`)

- [ ] **Step 4.1: Append the temporal section to `SYSTEM_PROMPT`**

In `src/backend/chat_assistant.py`, find the line that closes `SYSTEM_PROMPT` (currently at line 220, the last line before the closing triple-quote). Insert this new paragraph BEFORE the final closing `"""`, immediately after the existing "Keep answers terse" paragraph:

```
For recency / frequency / consumption questions ("when did we shop",
"how often do we go", "how much are we consuming", "trend"), use the
``shopping_activity`` block when present. Pick framing from the user's
wording:

  * Spending / cost / budget phrasing → quote ``windows.spend`` and the
    matching ``cadence.trips_per_week_*`` figure.
  * Items / products / "buying X" phrasing → quote ``top_items_30d``.
  * Visits / trips / "how often" phrasing → quote ``cadence`` plus
    ``windows.trips``.

When answering "when" questions, cite specific dates and stores from
``recent_receipts`` (already top-5, descending). Per-person breakdowns
live under ``per_person`` — only surface them when the user asks who
shopped or compares people. Never invent dates: if the user asks about
a date not in ``recent_receipts`` or ``per_person.last_trip``, say so.
If ``shopping_activity`` is null, the household has no purchase rows
in the last 90 days — say so plainly instead of guessing.

Example for "when did we shop lately":

    **Recent shopping (last 5 receipts):**
    - 2026-04-24 — Costco — $50.00 (Mom)
    - 2026-04-23 — Costco — $40.00 (Dad)
    - 2026-04-21 — Costco — $50.00 (Mom)
    - 2026-04-20 — Costco — $40.00 (Dad)
    - 2026-04-19 — Costco — $50.00 (Mom)

Example for "how often do we shop":

    **Shopping cadence:** about 4.2 trips per week over the last 30
    days (vs 4.0 over 90 days — steady). Average gap between trips:
    1.6 days.

Example for "how much are we consuming":

    **Top items (last 30 days):**
    - Milk — 8 (\$32.40)
    - Eggs — 6 (\$24.00)
    - Bread — 5 (\$18.50)
```

- [ ] **Step 4.2: Extend `summary_parts` in `chat_complete`**

In `src/backend/chat_assistant.py:1053-1067`, find:

```python
    summary_parts = [
        f"totals for {data_context['current_month']}",
        f"{data_context['uncategorized_count_current_month']} uncategorized",
    ]
    if data_context.get("item_search_terms"):
        terms = ", ".join(data_context["item_search_terms"])
        hits = len(data_context.get("item_search_results") or [])
        summary_parts.append(
            f"item search: {terms} → {hits} match{'es' if hits != 1 else ''}"
        )
    if fallback_used:
        summary_parts.append(
            f"⚠️ fell back to {used_provider} ({primary_label} unavailable)"
        )
```

Add this block right BEFORE `if fallback_used:`:

```python
    sa = data_context.get("shopping_activity")
    if sa:
        wk = sa["windows"]["last_7d"]["trips"]
        wk30 = sa["windows"]["last_30d"]["trips"]
        summary_parts.append(
            f"shopping activity: {wk} trips/7d, {wk30} trips/30d"
        )
```

- [ ] **Step 4.3: Sanity-run the test file**

Run: `pytest tests/test_chat_temporal.py -v`

Expected: 20 tests still pass (no new tests, but verifying nothing broke).

- [ ] **Step 4.4: Run the full test suite to make sure nothing else regressed**

Run: `pytest -x -q`

Expected: existing tests still pass. If a test fails because the project doesn't have a working test target, note the unrelated failure and proceed — but DO NOT skip a failure that mentions `chat_assistant.py`, `Purchase`, or `ReceiptItem`.

- [ ] **Step 4.5: Commit**

```bash
git add src/backend/chat_assistant.py
git commit -m "feat(chat): system prompt + context summary for shopping_activity"
```

---

## Task 5: Manual smoke test

**Files:** none. This is a manual verification step the engineer runs against a live (or local) database.

- [ ] **Step 5.1: Start the backend with a populated DB**

Run the project's normal dev server (the engineer should know `flask --app create_flask_application run` or the equivalent, but if unsure ask the user — DO NOT invent a command). Confirm the chat panel loads in the browser and the admin user is signed in.

- [ ] **Step 5.2: Ask each of the three sample questions in the chat panel**

| Prompt | Expected reply uses |
|--------|--------------------|
| `When did we shop lately?` | `recent_receipts` — bullet list of dates + stores |
| `How often do we shop?` | `cadence` — trips/week + trend |
| `How much are we consuming?` | `top_items_30d` — bullet list of products |

- [ ] **Step 5.3: Ask one unrelated question and confirm shopping_activity is None**

Ask: `How much did we spend on groceries this month?`

In the inline chip below the reply (or in DevTools → Network → `/chat/messages` response → `tool_trace.context_summary`), confirm there is **no** "shopping activity" segment — proves the lazy gate held.

- [ ] **Step 5.4: Ask a per-person question**

Ask: `When did Mom last shop?`

Expected: bot quotes the matching `per_person[i].last_trip` row by name.

- [ ] **Step 5.5: Final commit message tweak (optional)**

If the smoke test surfaces a phrasing issue in the system prompt, fix it inline and commit:

```bash
git add src/backend/chat_assistant.py
git commit -m "fix(chat): clarify shopping_activity prompt examples after smoke test"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 ↔ extractor decision (lazy gate, Q5 = B). Task 2 ↔ aggregator output schema (windows, cadence, per_person, recent_receipts, top_items_30d) and edge cases (refund exclusion, empty short-circuit). Task 3 ↔ wire-up + lazy gate. Task 4 ↔ system prompt addendum + context summary chip. Task 5 ↔ manual smoke list from spec.
- **Placeholder scan**: every code block is fully written; no TBD/TODO; no "similar to Task N" backreferences.
- **Type consistency**: `_extract_temporal_intent` returns `bool` everywhere; `_compute_shopping_activity` returns `dict | None` everywhere; aggregator field names match the spec's JSON schema verbatim.
- **Known caveats** the executing engineer should watch:
  - `chat_assistant.datetime` monkey-patch in Task 3.1 works because `chat_assistant.py` does `from datetime import datetime, timedelta, timezone` at the top — verify with `grep "^from datetime" src/backend/chat_assistant.py` before running. If the import was rewritten as `import datetime as _dt`, adjust the patch site.
  - Fixture relies on `Product.id == 1` not existing — `ReceiptItem.product_id` is a non-null FK in the schema. If SQLite enforces FKs in tests, the engineer must either turn FK enforcement off (`PRAGMA foreign_keys = OFF` on the test engine) or seed a `Product` row with id=1 in the fixture. SQLite's default is OFF, so the existing tests likely work as-is, but note this if the FK error surfaces.

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-chat-temporal-shopping-activity.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
