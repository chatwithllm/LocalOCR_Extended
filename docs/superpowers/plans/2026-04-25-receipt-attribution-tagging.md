# Receipt Attribution Tagging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make receipt attribution easy enough that the household actually fills it in — bulk-tag the 169-receipt backlog from a single Receipts-page action, and auto-suggest attribution for new uploads from the uploader's per-store history.

**Architecture:** Two backend endpoints (bulk-attribution, attribution-stats) + an auto-suggest helper that the existing `/receipts/{id}/approve` path calls right after the Purchase row is saved. Three frontend additions (Untagged-only filter chip, multi-select bulk toolbar, dashboard nudge banner). Reuses every existing column, picker, and helper — zero schema change.

**Tech Stack:** Python 3.11 + Flask + SQLAlchemy 1.4 backend; vanilla JS + custom CSS frontend. Tests: pytest with in-memory SQLite (matches existing `tests/test_full_receipt_flow.py` pattern).

**Spec:** `docs/superpowers/specs/2026-04-25-receipt-attribution-tagging-design.md`

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `src/backend/handle_receipt_upload.py` | Modify | Add `POST /receipts/bulk-attribution`, `GET /receipts/attribution-stats`, `_suggest_attribution_for_upload` helper, and a wire-up call from `approve_receipt` so newly-saved Purchase rows get auto-tagged when confidence is high. |
| `src/frontend/index.html` | Modify | Receipts page: "Untagged only" filter chip + multi-select checkboxes + sticky bulk toolbar. Dashboard: new untagged-nudge banner. Upload-review modal: render `attribution_suggestion` hint. |
| `src/frontend/styles/design-system.css` | Modify | `.attr-bulk-toolbar`, `.dash-attr-nudge`, `.attr-suggest-pill` styles. |
| `tests/test_attribution_bulk.py` | Create | Bulk endpoint + attribution-stats + auto-suggest helper unit tests. In-memory SQLite, no Flask app context (mirrors `tests/test_chat_temporal.py`). |

The existing `attribution=unset` token on the receipts list endpoint already powers the filter — no backend change needed for that.

---

## Task 1: Bulk-attribution endpoint (TDD)

**Files:**
- Modify: `src/backend/handle_receipt_upload.py` (add new route after the existing per-row attribution route at ~line 2380)
- Create: `tests/test_attribution_bulk.py`

- [ ] **Step 1.1: Create `tests/test_attribution_bulk.py` with the failing tests**

```python
"""Unit tests for the bulk-attribution + attribution-stats endpoints
and the auto-suggest helper. Mirror tests/test_chat_temporal.py:
in-memory SQLite, no Flask app, env vars set BEFORE imports.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FERNET_SECRET_KEY", "test-fernet-key-for-unit-tests-only")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.initialize_database_schema import (
    Base, Purchase, ReceiptItem, Store, User,
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
    mom = User(name="Mom", email="mom@example.com")
    dad = User(name="Dad", email="dad@example.com")
    session.add_all([mom, dad])
    session.flush()

    costco = Store(name="Costco")
    target = Store(name="Target")
    session.add_all([costco, target])
    session.flush()

    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def _purchase(days_ago, uploader, store, attr=None, kind=None,
                  attr_ids=None, amount=50.0):
        p = Purchase(
            store_id=store.id,
            total_amount=amount,
            date=NOW - timedelta(days=days_ago),
            domain="grocery",
            transaction_type="purchase",
            user_id=uploader.id,
            attribution_user_id=attr.id if attr else None,
            attribution_user_ids=(
                json.dumps([u.id for u in attr_ids]) if attr_ids else None
            ),
            attribution_kind=kind,
        )
        session.add(p)
        session.flush()
        return p

    return {
        "mom": mom, "dad": dad,
        "costco": costco, "target": target,
        "now": NOW, "_purchase": _purchase,
    }


def test_bulk_attribution_updates_multiple_rows(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    p2 = household["_purchase"](2, household["mom"], household["costco"])
    p3 = household["_purchase"](3, household["dad"], household["target"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id, p2.id, p3.id],
        user_ids=[household["mom"].id],
        kind="personal",
        apply_to_items=False,
    )
    assert result["updated"] == 3
    assert result["skipped"] == []

    for pid in [p1.id, p2.id, p3.id]:
        row = session.query(Purchase).get(pid)
        assert row.attribution_user_id == household["mom"].id
        assert row.attribution_kind == "personal"


def test_bulk_attribution_skips_missing_ids(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id, 9999, 8888],
        user_ids=[household["mom"].id],
        kind="personal",
        apply_to_items=False,
    )
    assert result["updated"] == 1
    assert {row["purchase_id"] for row in result["skipped"]} == {9999, 8888}


def test_bulk_attribution_household_clears_user_ids(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id],
        user_ids=[],
        kind="household",
        apply_to_items=False,
    )
    assert result["updated"] == 1
    row = session.query(Purchase).get(p1.id)
    assert row.attribution_kind == "household"
    assert row.attribution_user_id is None
    # JSON list either None or "[]" — both acceptable.
    assert row.attribution_user_ids in (None, "[]")


def test_bulk_attribution_apply_to_items_propagates(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    item = ReceiptItem(
        purchase_id=p1.id, product_id=1, quantity=1, unit_price=10.0,
    )
    session.add(item)
    session.commit()

    _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id],
        user_ids=[household["dad"].id],
        kind="personal",
        apply_to_items=True,
    )
    refreshed = session.query(ReceiptItem).get(item.id)
    assert refreshed.attribution_user_id == household["dad"].id
    assert refreshed.attribution_kind == "personal"
```

- [ ] **Step 1.2: Run tests, confirm import error**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 4 failures with `ImportError: cannot import name '_bulk_apply_attribution'`.

- [ ] **Step 1.3: Add `_bulk_apply_attribution` and the route**

In `src/backend/handle_receipt_upload.py`, find the per-row endpoint at line 2326 (`update_receipt_attribution`). The new bulk helper + route go IMMEDIATELY AFTER `update_receipt_attribution` (around line 2380, before `update_receipt_item_attribution` at 2382).

Insert:

```python
def _bulk_apply_attribution(
    session,
    *,
    purchase_ids: list[int],
    user_ids: list[int],
    kind: str | None,
    apply_to_items: bool,
) -> dict:
    """Apply the same attribution to many Purchase rows.

    Pure-DB helper, no Flask. Returns
    ``{"updated": N, "skipped": [{"purchase_id": int, "reason": str}]}``.
    The caller is responsible for committing the session.
    """
    from src.backend.initialize_database_schema import Purchase, ReceiptItem

    legacy_single = user_ids[0] if len(user_ids) == 1 else None
    ids_json = _serialize_user_ids(user_ids)

    skipped: list[dict] = []
    updated = 0
    rows = (
        session.query(Purchase)
        .filter(Purchase.id.in_(purchase_ids))
        .all()
    )
    found_ids = {r.id for r in rows}
    for missing in purchase_ids:
        if missing not in found_ids:
            skipped.append({"purchase_id": missing, "reason": "not_found"})

    for row in rows:
        row.attribution_user_id = legacy_single
        row.attribution_user_ids = ids_json
        row.attribution_kind = kind
        updated += 1

    if apply_to_items and rows:
        ids = [r.id for r in rows]
        session.query(ReceiptItem).filter(
            ReceiptItem.purchase_id.in_(ids)
        ).update(
            {
                "attribution_user_id": legacy_single,
                "attribution_user_ids": ids_json,
                "attribution_kind": kind,
            },
            synchronize_session=False,
        )

    return {"updated": updated, "skipped": skipped}


@receipts_bp.route("/bulk-attribution", methods=["POST"])
@require_write_access
def bulk_update_receipt_attribution():
    """Apply the same attribution to many Purchase rows in one call.

    Body:
      { "purchase_ids": [int],
        "user_ids": [int],
        "kind": "household"|"personal"|"shared"|null,
        "apply_to_items": bool }
    """
    from src.backend.initialize_database_schema import User

    session = g.db_session
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("purchase_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "purchase_ids must be a non-empty list"}), 400
    if len(raw_ids) > 200:
        return jsonify({"error": "Too many ids; max 200 per request"}), 400
    try:
        purchase_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "purchase_ids must be integers"}), 400

    ok, result = _normalize_attribution_payload(data, session, User)
    if not ok:
        payload, status = result
        return jsonify(payload), status

    bulk = _bulk_apply_attribution(
        session,
        purchase_ids=purchase_ids,
        user_ids=result["user_ids"],
        kind=result["kind"],
        apply_to_items=bool(data.get("apply_to_items", True)),
    )
    session.commit()
    return jsonify(bulk), 200
```

- [ ] **Step 1.4: Run the 4 bulk tests**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 4 passed.

- [ ] **Step 1.5: Commit**

```
git add tests/test_attribution_bulk.py src/backend/handle_receipt_upload.py
git commit -m "feat(receipts): bulk attribution endpoint + helper"
```

---

## Task 2: Attribution-stats endpoint (TDD)

**Files:**
- Modify: `src/backend/handle_receipt_upload.py` (add route immediately after `bulk_update_receipt_attribution`)
- Modify: `tests/test_attribution_bulk.py`

- [ ] **Step 2.1: Add the failing test**

Append to `tests/test_attribution_bulk.py`:

```python
def test_attribution_stats_counts_correctly(session, household):
    from src.backend.handle_receipt_upload import _compute_attribution_stats

    # 3 untagged, 2 tagged (one personal, one household)
    household["_purchase"](1, household["mom"], household["costco"])
    household["_purchase"](2, household["mom"], household["costco"])
    household["_purchase"](3, household["dad"], household["target"])
    household["_purchase"](
        4, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        5, household["dad"], household["target"], kind="household",
    )
    session.commit()

    stats = _compute_attribution_stats(session)
    assert stats["untagged_count"] == 3
    assert stats["tagged_count"] == 2
    assert len(stats["untagged_sample_ids"]) == 3
    # Sample ids should all be in the untagged set (any order).
    untagged_actual = {
        row.id
        for row in session.query(Purchase).filter(
            Purchase.attribution_user_id.is_(None),
            Purchase.attribution_kind.is_(None),
        ).all()
    }
    assert set(stats["untagged_sample_ids"]).issubset(untagged_actual)


def test_attribution_stats_zero_untagged(session, household):
    from src.backend.handle_receipt_upload import _compute_attribution_stats

    household["_purchase"](
        1, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    session.commit()
    stats = _compute_attribution_stats(session)
    assert stats["untagged_count"] == 0
    assert stats["tagged_count"] == 1
    assert stats["untagged_sample_ids"] == []
```

- [ ] **Step 2.2: Run tests, confirm failure**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 2 new tests fail with ImportError on `_compute_attribution_stats`.

- [ ] **Step 2.3: Add the helper + route**

Insert AFTER `bulk_update_receipt_attribution` in `src/backend/handle_receipt_upload.py`:

```python
def _compute_attribution_stats(session) -> dict:
    """Counts of tagged vs untagged Purchase rows + a few sample
    untagged ids for the dashboard banner. Pure-DB helper."""
    from src.backend.initialize_database_schema import Purchase
    from sqlalchemy import or_

    untagged_filter = and_(
        Purchase.attribution_user_id.is_(None),
        Purchase.attribution_kind.is_(None),
        or_(
            Purchase.attribution_user_ids.is_(None),
            Purchase.attribution_user_ids == "[]",
        ),
    )
    untagged_count = (
        session.query(Purchase).filter(untagged_filter).count()
    )
    total = session.query(Purchase).count()
    tagged_count = total - untagged_count
    sample_rows = (
        session.query(Purchase.id)
        .filter(untagged_filter)
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(5)
        .all()
    )
    return {
        "untagged_count": int(untagged_count),
        "tagged_count": int(tagged_count),
        "untagged_sample_ids": [int(r[0]) for r in sample_rows],
    }


@receipts_bp.route("/attribution-stats", methods=["GET"])
@require_auth
def attribution_stats():
    """Return tagged/untagged purchase counts + sample untagged ids
    for the dashboard nudge banner."""
    return jsonify(_compute_attribution_stats(g.db_session)), 200
```

- [ ] **Step 2.4: Run tests**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 6 tests pass (4 from Task 1 + 2 new).

- [ ] **Step 2.5: Commit**

```
git add tests/test_attribution_bulk.py src/backend/handle_receipt_upload.py
git commit -m "feat(receipts): attribution-stats endpoint for dashboard banner"
```

---

## Task 3: Auto-suggest helper (TDD)

**Files:**
- Modify: `src/backend/handle_receipt_upload.py` (helper near the bulk helpers)
- Modify: `tests/test_attribution_bulk.py`

- [ ] **Step 3.1: Add failing tests**

Append to `tests/test_attribution_bulk.py`:

```python
def test_suggest_high_confidence(session, household):
    """4 of last 5 Costco uploads by Mom were personal/Mom → high."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["mom"], household["costco"],
            attr=household["mom"], kind="personal",
        )
    # Add one outlier: shared with Dad
    household["_purchase"](
        12, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is not None
    assert s["confidence"] == "high"
    assert s["kind"] == "personal"
    assert s["user_ids"] == [household["mom"].id]


def test_suggest_medium_confidence(session, household):
    """2 of last 5 split — medium confidence."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # 2 personal/Mom, 1 personal/Dad, 1 household, 1 shared
    household["_purchase"](
        10, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        8, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        6, household["mom"], household["costco"],
        attr=household["dad"], kind="personal",
    )
    household["_purchase"](
        4, household["mom"], household["costco"], kind="household",
    )
    household["_purchase"](
        2, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is not None
    assert s["confidence"] == "medium"


def test_suggest_none_when_no_history(session, household):
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None


def test_suggest_none_when_low_diversity(session, household):
    """5 different attributions in last 5 → no modal majority → None."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # Each row has a different (user, kind) combination
    household["_purchase"](
        10, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        8, household["mom"], household["costco"],
        attr=household["dad"], kind="personal",
    )
    household["_purchase"](
        6, household["mom"], household["costco"], kind="household",
    )
    household["_purchase"](
        4, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None  # No group reaches the 2-of-5 threshold


def test_suggest_scoped_per_uploader(session, household):
    """History from a different uploader doesn't influence this one."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # Dad's strong history at Costco
    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["dad"], household["costco"],
            attr=household["dad"], kind="personal",
        )
    session.commit()

    # Mom asks → no history of her own at Costco → None
    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None
```

- [ ] **Step 3.2: Run tests, confirm failure**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 5 new tests fail with ImportError on `_suggest_attribution_for_upload`.

- [ ] **Step 3.3: Add the helper**

Insert AFTER `_compute_attribution_stats` in `src/backend/handle_receipt_upload.py`:

```python
def _suggest_attribution_for_upload(
    session,
    *,
    uploader_id: int | None,
    store_id: int | None,
) -> dict | None:
    """Suggest attribution for a new Purchase row based on the
    uploader's history at the same store.

    Returns ``{"user_ids": [...], "kind": "...", "confidence":
    "high" | "medium"}`` or ``None``. Confidence:
      * 3+ of last 5 attributed receipts share the same
        (user_ids, kind) → high
      * 2 of 5 → medium
      * less → None
    """
    from src.backend.initialize_database_schema import Purchase
    from sqlalchemy import or_

    if not uploader_id or not store_id:
        return None

    rows = (
        session.query(Purchase)
        .filter(Purchase.user_id == uploader_id)
        .filter(Purchase.store_id == store_id)
        .filter(
            or_(
                Purchase.attribution_user_id.isnot(None),
                Purchase.attribution_kind.isnot(None),
            )
        )
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(10)
        .all()
    )
    if len(rows) < 2:
        return None

    last_5 = rows[:5]
    counts: dict[tuple, int] = {}
    representative: dict[tuple, dict] = {}
    for r in last_5:
        ids_raw = r.attribution_user_ids
        try:
            parsed = json.loads(ids_raw) if ids_raw else []
            if not isinstance(parsed, list):
                parsed = []
        except (TypeError, ValueError):
            parsed = []
        if not parsed and r.attribution_user_id:
            parsed = [int(r.attribution_user_id)]
        ids_tuple = tuple(sorted(int(x) for x in parsed))
        kind = r.attribution_kind
        key = (ids_tuple, kind)
        counts[key] = counts.get(key, 0) + 1
        representative.setdefault(key, {
            "user_ids": list(ids_tuple),
            "kind": kind,
        })

    if not counts:
        return None
    top_key = max(counts, key=counts.get)
    top_count = counts[top_key]
    if top_count >= 3:
        confidence = "high"
    elif top_count == 2:
        confidence = "medium"
    else:
        return None

    payload = dict(representative[top_key])
    payload["confidence"] = confidence
    return payload
```

- [ ] **Step 3.4: Run tests**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 11 tests pass (6 existing + 5 new).

- [ ] **Step 3.5: Commit**

```
git add tests/test_attribution_bulk.py src/backend/handle_receipt_upload.py
git commit -m "feat(receipts): _suggest_attribution_for_upload history helper"
```

---

## Task 4: Wire auto-suggest into the upload-approve path

**Files:**
- Modify: `src/backend/handle_receipt_upload.py:1477-1536` (the existing `approve_receipt` function)

- [ ] **Step 4.1: Edit `approve_receipt` to call the suggester**

Find the existing `approve_receipt` function (`src/backend/handle_receipt_upload.py:1477`). Replace the final block — from `record.purchase_id = purchase_id` through `return jsonify({...}), 200` (lines 1525-1536) — with this expanded version:

```python
    record.purchase_id = purchase_id
    record.status = "processed"
    record.receipt_type = receipt_type
    record.raw_ocr_json = json.dumps(ocr_data)
    session.commit()

    # Auto-suggest attribution from uploader+store history. High
    # confidence is silently applied right here; medium is returned
    # so the upload-review modal can pre-select it without
    # committing.
    attribution_suggestion: dict | None = None
    auto_applied = False
    saved_purchase = (
        session.query(Purchase).filter_by(id=purchase_id).first()
    )
    if saved_purchase and not saved_purchase.attribution_user_id \
       and not saved_purchase.attribution_kind:
        suggestion = _suggest_attribution_for_upload(
            session,
            uploader_id=user_id,
            store_id=saved_purchase.store_id,
        )
        if suggestion and suggestion["confidence"] == "high":
            _bulk_apply_attribution(
                session,
                purchase_ids=[purchase_id],
                user_ids=suggestion["user_ids"],
                kind=suggestion["kind"],
                apply_to_items=True,
            )
            session.commit()
            auto_applied = True
            attribution_suggestion = suggestion
        elif suggestion:
            attribution_suggestion = suggestion

    return jsonify({
        "status": "processed",
        "purchase_id": purchase_id,
        "receipt_id": record.id,
        "receipt_type": receipt_type,
        "attribution_suggestion": attribution_suggestion,
        "attribution_auto_applied": auto_applied,
    }), 200
```

(Verify `Purchase` is already imported at the top of `approve_receipt`. It's imported lazily inside many sibling functions — if the existing code doesn't import it locally, add `from src.backend.initialize_database_schema import Purchase` at the top of the function body, right after the other local imports.)

- [ ] **Step 4.2: Add an integration-style test for the wire-up**

Append to `tests/test_attribution_bulk.py`:

```python
def test_approve_receipt_auto_applies_high_confidence(session, household):
    """End-to-end-ish: seed strong history, then call the helper
    chain that approve_receipt uses, confirm the new row is tagged."""
    from src.backend.handle_receipt_upload import (
        _bulk_apply_attribution, _suggest_attribution_for_upload,
    )
    from src.backend.initialize_database_schema import Purchase

    # Strong Mom history at Costco
    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["mom"], household["costco"],
            attr=household["mom"], kind="personal",
        )
    # New, unattributed purchase
    new_p = household["_purchase"](
        0, household["mom"], household["costco"],
    )
    session.commit()

    suggestion = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert suggestion["confidence"] == "high"

    _bulk_apply_attribution(
        session,
        purchase_ids=[new_p.id],
        user_ids=suggestion["user_ids"],
        kind=suggestion["kind"],
        apply_to_items=True,
    )
    session.commit()

    refreshed = session.query(Purchase).get(new_p.id)
    assert refreshed.attribution_user_id == household["mom"].id
    assert refreshed.attribution_kind == "personal"
```

- [ ] **Step 4.3: Run all tests**

Run: `.venv314/bin/python -m pytest tests/test_attribution_bulk.py -v`
Expected: 12 tests pass.

- [ ] **Step 4.4: Verify the file imports cleanly**

Run: `.venv314/bin/python -c "from src.backend.handle_receipt_upload import receipts_bp, approve_receipt, _bulk_apply_attribution, _suggest_attribution_for_upload, _compute_attribution_stats; print('OK')"`
Expected: prints `OK` with no errors.

- [ ] **Step 4.5: Commit**

```
git add src/backend/handle_receipt_upload.py tests/test_attribution_bulk.py
git commit -m "feat(receipts): silent auto-tag at receipt approve when high confidence"
```

---

## Task 5: Frontend — "Untagged only" filter chip + multi-select on Receipts page

**Files:**
- Modify: `src/frontend/index.html` (Receipts page filter row + receipts table render)
- Modify: `src/frontend/styles/design-system.css` (`.attr-bulk-toolbar` styles)

The existing `attribution=unset` query param already powers the SQL filter (see `handle_receipt_upload.py:1169-1190`), so this task is purely frontend.

- [ ] **Step 5.1: Locate the existing receipts filter row**

Run: `grep -n "Receipts page filter\|receipts-filter-row\|receipt-filter-card" src/frontend/index.html | head -5`
Use the results to find the existing filter chip area on the Receipts page.

- [ ] **Step 5.2: Add the "Untagged only" toggle chip**

Inside the receipts filter row (next to the existing store/status/source filter chips), insert this HTML:

```html
<button type="button"
        id="receipts-filter-untagged-btn"
        class="filter-chip"
        onclick="toggleReceiptsUntaggedFilter()"
        aria-pressed="false"
        title="Show only receipts that haven't been tagged to a household member">
  🏷 Untagged only
</button>
```

- [ ] **Step 5.3: Add the toggle JS**

Find the existing receipts-page IIFE (search for `loadReceipts(` to locate the loader). Insert this near the other filter helpers:

```javascript
let _receiptsUntaggedOnly = false;
const _receiptsBulkSelection = new Set();

function toggleReceiptsUntaggedFilter() {
  _receiptsUntaggedOnly = !_receiptsUntaggedOnly;
  const btn = document.getElementById("receipts-filter-untagged-btn");
  if (btn) btn.setAttribute("aria-pressed", String(_receiptsUntaggedOnly));
  if (btn) btn.classList.toggle("is-active", _receiptsUntaggedOnly);
  _receiptsBulkSelection.clear();
  _renderReceiptsBulkToolbar();
  loadReceipts();  // existing loader
}

function _appendUntaggedFilterToQuery(params) {
  // Called from the existing loadReceipts query-builder.
  if (_receiptsUntaggedOnly) {
    const existing = params.get("attribution");
    params.set("attribution", existing ? `${existing},unset` : "unset");
  }
  return params;
}
```

Then find the existing `loadReceipts` function and locate where it builds query params (look for `URLSearchParams` or `?store=` pattern). Insert a call to `_appendUntaggedFilterToQuery(params)` right before the fetch call.

- [ ] **Step 5.4: Add row checkboxes when filter is active**

Find the receipts table row renderer (search for the function that renders one `<tr>` per receipt — likely contains `escHtml(record.store)` or similar). Add this column AT THE FRONT of each `<tr>`:

```javascript
const checkboxCell = _receiptsUntaggedOnly
  ? `<td class="receipt-bulk-cell">
       <input type="checkbox"
              data-purchase-id="${record.purchase_id || ''}"
              ${_receiptsBulkSelection.has(record.purchase_id) ? "checked" : ""}
              ${record.purchase_id ? "" : "disabled"}
              onchange="toggleReceiptBulkRow(${record.purchase_id || 'null'}, this.checked)" />
     </td>`
  : "";
```

And insert `${checkboxCell}` at the start of each row's HTML template. Add a matching empty `<th>` to the table header so columns stay aligned.

- [ ] **Step 5.5: Add the bulk-select handler + toolbar render**

```javascript
function toggleReceiptBulkRow(purchaseId, checked) {
  if (!purchaseId) return;
  if (checked) _receiptsBulkSelection.add(purchaseId);
  else _receiptsBulkSelection.delete(purchaseId);
  _renderReceiptsBulkToolbar();
}

function _renderReceiptsBulkToolbar() {
  let bar = document.getElementById("receipts-bulk-toolbar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "receipts-bulk-toolbar";
    bar.className = "attr-bulk-toolbar";
    const host = document.querySelector("#page-receipts");
    if (host) host.prepend(bar);
  }
  const n = _receiptsBulkSelection.size;
  if (!n) {
    bar.style.display = "none";
    bar.innerHTML = "";
    return;
  }
  bar.style.display = "";
  bar.innerHTML = `
    <span class="attr-bulk-toolbar__label">${n} selected</span>
    <button type="button" class="btn btn-primary btn-sm"
            onclick="openBulkAttributionPicker()">
      🏷 Tag ${n} as…
    </button>
    <button type="button" class="btn btn-ghost btn-sm"
            onclick="_clearReceiptsBulkSelection()">Clear</button>
  `;
}

function _clearReceiptsBulkSelection() {
  _receiptsBulkSelection.clear();
  document
    .querySelectorAll('#page-receipts input[type="checkbox"][data-purchase-id]')
    .forEach((el) => { el.checked = false; });
  _renderReceiptsBulkToolbar();
}

async function openBulkAttributionPicker() {
  const ids = Array.from(_receiptsBulkSelection);
  if (!ids.length) return;
  const picked = await openAttributionPickerModal({
    title: `Tag ${ids.length} receipt${ids.length > 1 ? "s" : ""}`,
    initialState: { kind: null, userIds: [] },
  });
  if (!picked) return;
  const res = await api(`/receipts/bulk-attribution`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      purchase_ids: ids,
      user_ids: picked.userIds || [],
      kind: picked.kind,
      apply_to_items: true,
    }),
  });
  if (!res.ok) {
    alert("Bulk-tag failed: " + res.status);
    return;
  }
  const data = await res.json();
  toast(`Tagged ${data.updated} receipt${data.updated === 1 ? "" : "s"}.`);
  _clearReceiptsBulkSelection();
  loadReceipts();
  refreshAttributionStats();
}
```

The `openAttributionPickerModal` helper does NOT exist yet — it needs to wrap the existing per-row picker into a Promise-returning modal. If the existing picker is already promise-shaped, reuse it. Otherwise, add this small wrapper near the existing picker code:

```javascript
function openAttributionPickerModal({ title, initialState }) {
  return new Promise((resolve) => {
    // Reuse the existing attribution picker UI by mounting a transient
    // host container. Find the existing picker constructor —
    // typically named `mountAttributionPicker(hostEl, opts, onCommit)`
    // or similar — and wire it up here. If the existing picker is
    // tightly coupled to a row, fall back to a simple prompt with
    // <select> elements for user_ids and kind, since v1 ships
    // working bulk action even with a basic picker.
    const dlg = document.createElement("dialog");
    dlg.className = "attr-bulk-modal";
    dlg.innerHTML = `
      <h3>${title}</h3>
      <p>Pick household member(s) and kind, then confirm.</p>
      <label>Kind:
        <select id="attr-bulk-kind">
          <option value="personal">Personal</option>
          <option value="shared">Shared (2+ people)</option>
          <option value="household">Household (everyone)</option>
        </select>
      </label>
      <label>Members (comma-separated user IDs):
        <input id="attr-bulk-uids" placeholder="e.g. 1,2" />
      </label>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button id="attr-bulk-cancel" class="btn btn-ghost">Cancel</button>
        <button id="attr-bulk-ok" class="btn btn-primary">Apply</button>
      </div>
    `;
    document.body.appendChild(dlg);
    dlg.showModal();
    dlg.querySelector("#attr-bulk-cancel").onclick = () => {
      dlg.close(); dlg.remove(); resolve(null);
    };
    dlg.querySelector("#attr-bulk-ok").onclick = () => {
      const kind = dlg.querySelector("#attr-bulk-kind").value;
      const raw = dlg.querySelector("#attr-bulk-uids").value;
      const userIds = raw
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));
      dlg.close(); dlg.remove();
      resolve({ kind, userIds });
    };
  });
}
```

(This is an intentionally minimal fallback so the bulk path ships and works. Polishing the modal to match the existing per-row picker's UX is out of scope for v1 — file a follow-up task if desired.)

- [ ] **Step 5.6: Add CSS for the bulk toolbar**

Append to `src/frontend/styles/design-system.css`:

```css
/* === Receipts bulk-attribution toolbar === */
.attr-bulk-toolbar {
  position: sticky;
  top: 12px;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: var(--color-surface-1, #fff);
  border: 1px solid var(--color-accent, #4aa3ff);
  border-radius: 999px;
  box-shadow: var(--shadow-2, 0 4px 12px rgba(0,0,0,0.08));
  font-weight: 600;
  font-size: 0.92rem;
}
.attr-bulk-toolbar__label {
  margin-right: auto;
  font-variant-numeric: tabular-nums;
}
.receipt-bulk-cell {
  width: 28px;
  text-align: center;
}
.attr-bulk-modal {
  border: 1px solid var(--color-border-soft, rgba(127,127,127,0.18));
  border-radius: 12px;
  padding: 18px;
  min-width: 320px;
}
```

- [ ] **Step 5.7: Manual smoke check (no test framework)**

Open the dev container, refresh `http://localhost:8090`, navigate to Receipts page, click "Untagged only" — expect rows to filter and checkboxes to appear. Select 2 rows → toolbar appears with "2 selected" + "Tag 2 as…" button.

- [ ] **Step 5.8: Commit**

```
git add src/frontend/index.html src/frontend/styles/design-system.css
git commit -m "feat(receipts): Untagged-only filter + multi-select bulk-tag toolbar"
```

---

## Task 6: Frontend — Dashboard nudge banner

**Files:**
- Modify: `src/frontend/index.html` (add banner HTML + JS in dashboard page)
- Modify: `src/frontend/styles/design-system.css` (`.dash-attr-nudge`)

- [ ] **Step 6.1: Add the banner HTML**

Find the dashboard page block (search `id="page-dashboard"`). Insert this banner BETWEEN the leaderboard row and the KPI row (use grep to find the right anchor — typically the existing KPI row has class `dashboard-stats-grid` or `kpi-row`):

```html
<div id="dashboard-attr-nudge" class="dash-attr-nudge" style="display:none">
  <span class="dash-attr-nudge__icon">💡</span>
  <span id="dashboard-attr-nudge-text" class="dash-attr-nudge__text"></span>
  <a class="dash-attr-nudge__cta" onclick="navToReceiptsUntagged()">Tag now →</a>
</div>
```

- [ ] **Step 6.2: Add the loader + nav helper JS**

Add inside the existing dashboard IIFE (or near the other dashboard loaders):

```javascript
async function refreshAttributionStats() {
  try {
    const res = await api("/receipts/attribution-stats");
    if (!res.ok) return;
    const data = await res.json();
    const banner = document.getElementById("dashboard-attr-nudge");
    const text = document.getElementById("dashboard-attr-nudge-text");
    if (!banner || !text) return;
    if (data.untagged_count > 0) {
      const word = data.untagged_count === 1 ? "receipt" : "receipts";
      text.textContent = `${data.untagged_count} ${word} untagged`;
      banner.style.display = "";
    } else {
      banner.style.display = "none";
    }
  } catch (_e) {
    // Banner stays hidden on error — non-critical
  }
}

function navToReceiptsUntagged() {
  if (typeof nav === "function") nav("receipts");
  // Activate the filter chip after navigation
  setTimeout(() => {
    if (!_receiptsUntaggedOnly) toggleReceiptsUntaggedFilter();
  }, 150);
}
```

- [ ] **Step 6.3: Hook into existing dashboard load**

Find the existing dashboard load function (search `loadDashboard\|initDashboard`). Add `refreshAttributionStats();` to its end so the banner updates on every dashboard view.

- [ ] **Step 6.4: Add CSS**

Append to `src/frontend/styles/design-system.css`:

```css
/* === Dashboard attribution-nudge banner === */
.dash-attr-nudge {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin: 0 0 16px;
  background: var(--color-surface-1, #fff);
  border: 1px solid var(--color-accent-soft, rgba(74,163,255,0.3));
  border-radius: var(--radius-lg, 12px);
  font-size: 0.92rem;
}
.dash-attr-nudge__icon { font-size: 1.1rem; }
.dash-attr-nudge__text { flex: 1; font-weight: 600; }
.dash-attr-nudge__cta {
  cursor: pointer;
  font-weight: 700;
  color: var(--color-accent, #4aa3ff);
  white-space: nowrap;
}
.dash-attr-nudge__cta:hover { text-decoration: underline; }
```

- [ ] **Step 6.5: Smoke**

Refresh dev. Dashboard should show banner with the actual untagged count. Click "Tag now →" → navigates to Receipts page with the Untagged filter active.

- [ ] **Step 6.6: Commit**

```
git add src/frontend/index.html src/frontend/styles/design-system.css
git commit -m "feat(dashboard): nudge banner for untagged receipts"
```

---

## Task 7: Frontend — Upload-review modal suggestion hint

**Files:**
- Modify: `src/frontend/index.html` (the upload-review modal that appears after an OCR completes)

- [ ] **Step 7.1: Locate the upload-review modal**

Run: `grep -n "approveReceipt\|upload-review\|/receipts/.*/approve" src/frontend/index.html | head -5`
The modal is the one that POSTs to `/receipts/<id>/approve`. The response now carries `attribution_suggestion` (an object) and `attribution_auto_applied` (bool).

- [ ] **Step 7.2: Render the suggestion hint after a successful approve**

Find the function that handles the approve response. Add this immediately after the response is parsed (after `const data = await res.json();` or equivalent):

```javascript
if (data.attribution_auto_applied && data.attribution_suggestion) {
  const s = data.attribution_suggestion;
  const label = s.kind === "household"
    ? "🏠 Household"
    : (s.user_ids && s.user_ids.length === 1
        ? `👤 user #${s.user_ids[0]}`
        : `👤 ${s.user_ids?.length || 0} people`);
  toast(`Auto-tagged as ${label} based on past uploads — change in Receipts if wrong.`);
} else if (data.attribution_suggestion) {
  const s = data.attribution_suggestion;
  const label = s.kind === "household"
    ? "🏠 Household"
    : (s.user_ids && s.user_ids.length === 1
        ? `👤 user #${s.user_ids[0]}`
        : `👤 ${s.user_ids?.length || 0} people`);
  toast(`Suggested attribution: ${label}. Open the receipt to apply.`);
}
```

(`toast()` is the existing notification helper — verify with `grep -n "function toast" src/frontend/index.html | head`. If absent, use `console.info(...)` instead and document the gap.)

- [ ] **Step 7.3: Smoke**

Upload two receipts at the same store as the same user, both tagged manually with "Mom". Then upload a third — expect a toast saying "Auto-tagged as 👤 user #N — change in Receipts if wrong."

- [ ] **Step 7.4: Commit**

```
git add src/frontend/index.html
git commit -m "feat(upload): show toast when auto-suggest tags or proposes a tag"
```

---

## Task 8: Smoke + dev rebuild

**Files:** none — manual verification only.

- [ ] **Step 8.1: Run all backend tests**

Run: `.venv314/bin/python -m pytest -x -q tests/test_attribution_bulk.py tests/test_chat_temporal.py`
Expected: 12 + 30 = 42 passed (existing 30 + new 12).

- [ ] **Step 8.2: Rebuild + restart the dev container**

Run:
```
docker compose up -d --build backend
sleep 4 && curl -sf http://localhost:8090/health
```
Expected: `{"service":"localocr-extended-backend","status":"healthy"}`.

- [ ] **Step 8.3: Manual smoke checklist**

Open `http://localhost:8090` and run through:

| # | Action | Expected |
|---|--------|----------|
| 1 | Open Dashboard | Banner reads "💡 N receipts untagged — tag now →" with the actual count |
| 2 | Click "Tag now →" | Receipts page opens; "Untagged only" filter is active; rows show row checkboxes |
| 3 | Select 5 rows | Sticky toolbar shows "5 selected · 🏷 Tag 5 as… · Clear" |
| 4 | Click "Tag 5 as…" → pick "personal" + your user id → Apply | Toast "Tagged 5 receipts."; rows disappear from the untagged view; banner count drops by 5 |
| 5 | Upload a new receipt at a store with strong history (≥3 of last 5 same-attribution) | Receipt appears already tagged; toast says "Auto-tagged as …" |
| 6 | Upload a new receipt at a store with weaker history (2 of 5) | Receipt appears untagged; toast says "Suggested attribution: …" |
| 7 | Open chat panel; ask "who last shopped?" | Bot now quotes per-person attribution from real data instead of "no purchases tagged" |

- [ ] **Step 8.4: Commit any prompt or copy refinements surfaced by smoke**

```
git add -p src/frontend/index.html src/backend/handle_receipt_upload.py
git commit -m "polish(receipts): smoke-test fixups for attribution flow"
```

(Skip this step if no fixes needed.)

---

## Self-Review Notes

- **Spec coverage**:
  - Spec § "Backend — bulk-attribution endpoint" ↔ Task 1.
  - Spec § "Backend — attribution-stats endpoint" ↔ Task 2.
  - Spec § "Backend — _suggest_attribution_for_upload" ↔ Task 3.
  - Spec § "Wire-up in approve" ↔ Task 4.
  - Spec § "Receipts page — filter + multi-select + bulk toolbar" ↔ Task 5.
  - Spec § "Dashboard nudge banner" ↔ Task 6.
  - Spec § "Upload-review modal suggestion hint" ↔ Task 7.
  - Spec § "Testing — manual smoke" ↔ Task 8.
- **Placeholder scan**: every code block is fully written. The Task 5 picker fallback is a documented v1 simplification, not a TODO — the bulk action ships and works with that minimal modal.
- **Type consistency**: `_bulk_apply_attribution` returns `{"updated": int, "skipped": [{"purchase_id": int, "reason": str}]}` consistently across Task 1 tests, Task 4 wire-up, and Task 5 frontend. `_suggest_attribution_for_upload` returns `{"user_ids": [int], "kind": str | None, "confidence": "high" | "medium"} | None` consistently across Tasks 3 and 4.
- **Caveats** for the executing engineer:
  - The Task 5 picker is intentionally a minimal modal to avoid getting tangled with the existing per-row picker's coupling to a single row context. Polishing it to reuse the existing UI is a follow-up.
  - Task 7 references `toast()` — if absent, fall back to `console.info`. Don't introduce a new notification framework just for this.
  - Task 6 uses `nav("receipts")` — verify that's the actual SPA navigation function name (search `function nav(`); adjust if different.

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-receipt-attribution-tagging.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
