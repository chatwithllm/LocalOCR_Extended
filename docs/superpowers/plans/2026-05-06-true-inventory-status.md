# True Inventory Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Spec:** `docs/superpowers/specs/2026-05-06-true-inventory-status-design.md`

**Goal:** Replace static `x1/x2` count tiles with auto-decaying `% remaining` + status (fresh/low/out), rendered as a subtle fill behind the existing title row. No new rows. Tap to cycle status; long-press to drag override; existing actions (`−1`, `✓`) augmented to update the override.

**Architecture:** Migration 027 adds two nullable columns: `Product.expected_shelf_days` and `Inventory.consumed_pct_override`. A new pure-function `compute_inventory_status(product, inventory, now)` returns `{remaining_pct, status, shelf_days, is_estimated}` from time-since-purchase + category default + optional override. `GET /inventory` emits these fields per row. Frontend tile reads them into CSS variables on the title row's `::before` fill. Existing `−1` and `✓` actions update the override server-side.

**Tech Stack:** Python 3.14 / Flask / SQLAlchemy / Alembic; vanilla JS frontend in `src/frontend/index.html`; pytest. Inline-CSS `::before` for the row-bg fill.

---

## File Structure

**Created:**
- `alembic/versions/027_inventory_true_status.py` — migration
- `src/backend/inventory_status.py` — pure compute helper + category shelf-life table

**Modified:**
- `src/backend/initialize_database_schema.py` — add two columns
- `src/backend/manage_inventory.py` — extend `list_inventory` serializer; augment `consume_item` and used-up paths
- `src/frontend/index.html` — tile rendering + CSS + drag interactions
- `tests/test_cards_overview.py` — append regression tests

---

## Task 1: Migration 027 + model columns

**Files:**
- Create: `alembic/versions/027_inventory_true_status.py`
- Modify: `src/backend/initialize_database_schema.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Add the schema test**

Append to `tests/test_cards_overview.py`:

```python
def test_inventory_has_consumed_pct_override_column():
    """Migration 027 must add Inventory.consumed_pct_override."""
    cols = {c.name for c in Base.metadata.tables["inventory"].columns}
    assert "consumed_pct_override" in cols


def test_product_has_expected_shelf_days_column():
    """Migration 027 must add Product.expected_shelf_days."""
    cols = {c.name for c in Base.metadata.tables["products"].columns}
    assert "expected_shelf_days" in cols
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py -k "consumed_pct_override or expected_shelf_days" -v
```

Expected: both FAIL.

- [ ] **Step 3: Add the model columns**

In `src/backend/initialize_database_schema.py`:

1. Find the `Product` class (around line 105). Add **after** `barcode = Column(...)`:

```python
    barcode = Column(String(50), nullable=True)
    expected_shelf_days = Column(Integer, nullable=True)
```

2. Find the `Inventory` class (around line 160). Add **after** `last_purchased_at`:

```python
    last_purchased_at = Column(DateTime, nullable=True)
    consumed_pct_override = Column(Float, nullable=True)
```

- [ ] **Step 4: Write the migration file**

Open `alembic/versions/026_plaid_account_loan_original_amount.py` to confirm its `revision = "..."` string. Use that as `down_revision`.

Create `alembic/versions/027_inventory_true_status.py`:

```python
"""inventory true-status columns

Revision ID: 027_true_status
Revises: 026_loan_original_amount
Create Date: 2026-05-06

Adds Product.expected_shelf_days (Integer) and
Inventory.consumed_pct_override (Float). Both nullable. Power the
auto-decaying %-remaining + fresh/low/out status that replaces the
meaningless x1/x2 tile counts.

PRAGMA-guarded idempotent pattern. Downgrade is no-op (additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "027_true_status"
down_revision = "026_loan_original_amount"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "products", "expected_shelf_days"):
        op.add_column(
            "products",
            sa.Column("expected_shelf_days", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "inventory", "consumed_pct_override"):
        op.add_column(
            "inventory",
            sa.Column("consumed_pct_override", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep columns to avoid data loss on revert.
    pass
```

If 026 revision string differs, paste the exact value.

- [ ] **Step 5: Run schema tests → expect PASS**

```bash
pytest tests/test_cards_overview.py -k "consumed_pct_override or expected_shelf_days" -v
```

- [ ] **Step 6: Run full file**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: all pass (count = previous + 2).

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/027_inventory_true_status.py \
        src/backend/initialize_database_schema.py \
        tests/test_cards_overview.py
git commit -m "feat(inventory): add expected_shelf_days + consumed_pct_override columns"
```

---

## Task 2: `inventory_status` compute helper + category table

**Files:**
- Create: `src/backend/inventory_status.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cards_overview.py`:

```python
def test_compute_remaining_auto_decay_midway():
    """No override, 3 days into 7-day shelf → ~57% remaining, status low."""
    from datetime import datetime, timedelta
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1, 12, 0, 0)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 4, 12, 0, 0)  # 3 days later
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 7
    # 3/7 = 42.857... consumed → 57.1 remaining (rounded to 1 dp)
    assert abs(result["remaining_pct"] - 57.1) < 0.2
    assert result["status"] == "low"
    assert result["is_estimated"] is True


def test_compute_remaining_override_wins():
    """Manual override beats auto-decay regardless of date math."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2020, 1, 1)  # ancient
        last_updated = None
        consumed_pct_override = 10.0  # only 10% consumed

    now = datetime(2026, 5, 4)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["remaining_pct"] == 90.0
    assert result["status"] == "fresh"
    assert result["is_estimated"] is False


def test_compute_remaining_uses_product_override_shelf_days():
    """Product.expected_shelf_days beats category default."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"  # default 7
        expected_shelf_days = 30  # override
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 16)  # 15 days
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 30
    # 15/30 = 50% consumed → 50 remaining
    assert abs(result["remaining_pct"] - 50.0) < 0.2
    assert result["status"] == "low"


def test_compute_remaining_uses_other_when_category_unknown():
    """Null category falls back to 'other' (30 days)."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = None
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 4)  # 3 days into 30 → 10% consumed
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 30
    assert result["remaining_pct"] == 90.0
    assert result["status"] == "fresh"


def test_compute_remaining_clamps_to_zero():
    """Far past shelf life → 0% remaining, status out."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"  # 7 days
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 1, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 1)  # months later
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["remaining_pct"] == 0.0
    assert result["status"] == "out"


def test_compute_remaining_falls_back_to_last_updated():
    """When last_purchased_at is null, last_updated anchors decay."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = None
        last_updated = datetime(2026, 5, 1)
        consumed_pct_override = None

    now = datetime(2026, 5, 4)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 7
    # 3/7 → ~57.1 remaining
    assert abs(result["remaining_pct"] - 57.1) < 0.2
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py -k "compute_remaining" -v
```

Expected: all FAIL — module doesn't exist.

- [ ] **Step 3: Create the helper module**

Create `src/backend/inventory_status.py`:

```python
"""Pure-function helpers for inventory %-remaining + status computation.

Single source of truth for the auto-decaying shelf-life model. Used by
the inventory list endpoint and any future consumer (recommendations,
shopping suggestions, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


# Per-category shelf-life defaults in days. User-tunable in Phase 2.
CATEGORY_SHELF_DAYS: dict[str, int] = {
    "dairy": 7,
    "milk": 7,
    "eggs": 21,
    "leafy_produce": 5,
    "produce": 7,
    "root_vegetables": 14,
    "fruit": 7,
    "meat": 4,
    "fish": 2,
    "frozen": 90,
    "pantry": 60,
    "snacks": 30,
    "beverages": 14,
    "condiments": 90,
    "baked": 5,
    "household": 180,
    "other": 30,
}


def shelf_days_for(product: Any) -> int:
    """Resolve effective shelf days: product override → category default → 30."""
    explicit = getattr(product, "expected_shelf_days", None)
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    category = (getattr(product, "category", None) or "other").lower()
    return CATEGORY_SHELF_DAYS.get(category, CATEGORY_SHELF_DAYS["other"])


def compute_inventory_status(
    product: Any,
    inventory: Any,
    *,
    now: datetime | None = None,
) -> dict:
    """Return {shelf_days, remaining_pct, status, is_estimated} for a row.

    Override (`inventory.consumed_pct_override`) wins when present. Otherwise
    auto-decays linearly from `last_purchased_at` (or `last_updated` as
    fallback) over `shelf_days`.
    """
    if now is None:
        now = datetime.utcnow()

    shelf_days = shelf_days_for(product)
    override = getattr(inventory, "consumed_pct_override", None)

    if override is not None:
        consumed = max(0.0, min(100.0, float(override)))
        is_estimated = False
    else:
        anchor = (
            getattr(inventory, "last_purchased_at", None)
            or getattr(inventory, "last_updated", None)
            or now
        )
        days_elapsed = max(0, (now - anchor).days)
        consumed = min(100.0, (days_elapsed / max(1, shelf_days)) * 100.0)
        is_estimated = True

    remaining_pct = round(100.0 - consumed, 1)
    if remaining_pct >= 60:
        status = "fresh"
    elif remaining_pct >= 20:
        status = "low"
    else:
        status = "out"

    return {
        "shelf_days": shelf_days,
        "remaining_pct": remaining_pct,
        "status": status,
        "is_estimated": is_estimated,
    }
```

- [ ] **Step 4: Run tests → expect PASS**

```bash
pytest tests/test_cards_overview.py -k "compute_remaining" -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/inventory_status.py tests/test_cards_overview.py
git commit -m "feat(inventory): add compute_inventory_status helper + category shelf-life table"
```

---

## Task 3: Inventory list emits status fields + consume action updates override

**Files:**
- Modify: `src/backend/manage_inventory.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test for the list endpoint**

Append to `tests/test_cards_overview.py`:

```python
def _invoke_list_inventory(app, user_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context("/inventory", method="GET"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match("/inventory", method="GET")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn()
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                return resp[1], (resp[0].get_json() if hasattr(resp[0], "get_json") else resp[0])
            return 200, resp
    finally:
        session.close()


def test_list_inventory_emits_status_fields(app):
    """GET /inventory rows carry remaining_pct, status, shelf_days, is_estimated."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"truinv_{uuid.uuid4().hex[:6]}@test.local", name="True Inv")
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"TestMilk-{uuid.uuid4().hex[:6]}", category="dairy")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=2, location="Fridge",
            is_active_window=True,
            last_purchased_at=_dt.utcnow(),  # 0 days → 100% remaining
        )
        session.add(inv); session.commit()
    finally:
        session.close()

    status, body = _invoke_list_inventory(app, user_id)
    assert status == 200, body
    rows = body["inventory"]
    matches = [r for r in rows if r["product_name"].startswith("TestMilk-") or r.get("raw_name", "").startswith("TestMilk-")]
    assert len(matches) >= 1
    row = matches[0]
    assert "remaining_pct" in row
    assert "status" in row
    assert "shelf_days" in row
    assert "is_estimated" in row
    assert row["shelf_days"] == 7  # dairy
    assert row["remaining_pct"] >= 90.0  # just bought
    assert row["status"] == "fresh"
    assert row["is_estimated"] is True
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py::test_list_inventory_emits_status_fields -v
```

Expected: FAIL — `KeyError: 'remaining_pct'`.

- [ ] **Step 3: Extend the list serializer**

In `src/backend/manage_inventory.py`, find the dict comprehension that returns rows in `list_inventory()` (around lines 161-194). Inside the per-row dict, immediately after `"days_left": ...`, add the four new fields:

```python
"days_left": (item.expires_at - _today).days if item.expires_at else None,
**_status_fields(item),
```

Then at the top of `manage_inventory.py`, import the helper and define the small wrapper. Find the existing `from src.backend.normalize_product_names import ...` import group near the top. Add this BELOW the existing imports:

```python
from src.backend.inventory_status import compute_inventory_status
```

Just below the existing `_get_latest_price` helper definition (or near other private helpers — find a private helper like `_is_item_low`), add:

```python
def _status_fields(item) -> dict:
    """Wrap compute_inventory_status into the inventory-row dict shape."""
    s = compute_inventory_status(item.product, item)
    return {
        "remaining_pct": s["remaining_pct"],
        "status": s["status"],
        "shelf_days": s["shelf_days"],
        "is_estimated": s["is_estimated"],
    }
```

- [ ] **Step 4: Run test → expect PASS**

```bash
pytest tests/test_cards_overview.py::test_list_inventory_emits_status_fields -v
```

- [ ] **Step 5: Write tests for consume + used-up override updates**

Append to `tests/test_cards_overview.py`:

```python
def _invoke_consume(app, user_id, item_id, amount=1):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/consume"
        with app.test_request_context(path, method="PUT", json={"amount": amount}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(item_id=item_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                return resp[1], (resp[0].get_json() if hasattr(resp[0], "get_json") else resp[0])
            return 200, resp
    finally:
        session.close()


def test_consume_action_bumps_consumed_override(app):
    """−1 from qty=4 sets override to ≈25 (one quarter consumed)."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"consume_{uuid.uuid4().hex[:6]}@test.local", name="Consume")
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Bagel-{uuid.uuid4().hex[:6]}", category="baked")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=4, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    status, _body = _invoke_consume(app, user_id, item_id, amount=1)
    assert status == 200

    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        # 1 of original 4 consumed → ≈25%
        assert inv.consumed_pct_override is not None
        assert 20.0 <= inv.consumed_pct_override <= 30.0
    finally:
        session.close()
```

- [ ] **Step 6: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py::test_consume_action_bumps_consumed_override -v
```

Expected: FAIL — override stays None.

- [ ] **Step 7: Augment `consume_item` to update override**

In `src/backend/manage_inventory.py`, find `consume_item()` (line ~301). Currently it does:

```python
actual_amount = min(float(item.quantity or 0), float(amount or 0))
if actual_amount > 0:
    item.updated_by = user_id
    record_inventory_adjustment(session, item.product_id, -actual_amount, user_id, "consume")
    rebuild_active_inventory(session)
```

Add override-bump just before `record_inventory_adjustment`:

```python
actual_amount = min(float(item.quantity or 0), float(amount or 0))
if actual_amount > 0:
    item.updated_by = user_id
    # Bump consumed_pct_override proportional to the fraction of the
    # current quantity being consumed. If override was already set, add
    # to it; if null, treat current auto-decay as the baseline so the
    # action shifts the bar visibly forward.
    qty_at_time = float(item.quantity or 0)
    if qty_at_time > 0:
        bump = (actual_amount / qty_at_time) * 100.0
        from src.backend.inventory_status import compute_inventory_status
        baseline = item.consumed_pct_override
        if baseline is None:
            baseline = 100.0 - compute_inventory_status(item.product, item)["remaining_pct"]
        item.consumed_pct_override = max(0.0, min(100.0, baseline + bump))
    record_inventory_adjustment(session, item.product_id, -actual_amount, user_id, "consume")
    rebuild_active_inventory(session)
```

- [ ] **Step 8: Run test → expect PASS**

```bash
pytest tests/test_cards_overview.py::test_consume_action_bumps_consumed_override -v
```

- [ ] **Step 9: Find used-up endpoint + augment**

Search for the "used up" endpoint:

```bash
grep -n "used.up\|use.*up\|mark_used\|@inventory_bp.route.*used\|status.*used" src/backend/manage_inventory.py | head
```

If it's a separate endpoint, augment it to set `item.consumed_pct_override = 100.0`.

If "used up" is just `consume` with quantity-to-zero, the bump in step 7 will already drive it to 100% (or close — the formula caps at 100). Verify by reading the test expectation:

```python
def test_used_up_sets_override_100(app):
    """Consuming entire quantity drives override to 100%."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"useup_{uuid.uuid4().hex[:6]}@test.local", name="Use Up")
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Yogurt-{uuid.uuid4().hex[:6]}", category="dairy")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=1, location="Fridge",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    status, _ = _invoke_consume(app, user_id, item_id, amount=1)
    assert status == 200
    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        # consumed all → override should be ~100
        assert inv.consumed_pct_override is not None
        assert inv.consumed_pct_override >= 95.0
    finally:
        session.close()
```

Append this test. Run:

```bash
pytest tests/test_cards_overview.py::test_used_up_sets_override_100 -v
```

Should PASS via the same code path.

- [ ] **Step 10: Run full file**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add src/backend/manage_inventory.py tests/test_cards_overview.py
git commit -m "feat(inventory): list emits status fields; consume bumps consumed_pct_override"
```

---

## Task 4: Frontend tile rendering — title-row fill + colors

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Locate the inventory tile renderer**

Search for the function that renders inventory tiles:

```bash
grep -n "renderInventoryTile\|inventory-card\|inv-tile\|getInventoryItems\|item.product_name" src/frontend/index.html | head -20
```

The tile is rendered in a function inside `loadInventory` flow. Find the title row that emits the product name + countdown ("2d left"). It will be a template-string fragment.

- [ ] **Step 2: Add the new CSS**

Find the existing `<style>` block that has `.card-usage-pie-panel` (added in earlier phases). Append:

```css
.inv-tile-title-row {
  position: relative;
  overflow: hidden;
  border-radius: 6px;
  padding: 6px 10px;
}
.inv-tile-title-row::before {
  content: "";
  position: absolute;
  inset: 0;
  width: var(--remaining-pct, 100%);
  background: var(--status-fill, rgba(52, 199, 89, 0.18));
  z-index: 0;
  transition: width 240ms ease;
  pointer-events: none;
}
.inv-tile-title-row > * { position: relative; z-index: 1; }

.inv-tile-est-suffix {
  font-size: 0.78em;
  color: var(--muted, #888);
  margin-left: 6px;
  opacity: 0.75;
}
```

- [ ] **Step 3: Wrap the title row in `inv-tile-title-row` + apply CSS variables**

Find the existing template render of the tile (look for the line that contains the product name and the countdown — `2d left` text). Replace the title HTML with:

```html
<div class="inv-tile-title-row"
     data-inv-id="${item.id}"
     style="--remaining-pct: ${Math.max(0, Math.min(100, item.remaining_pct ?? 100))}%;
            --status-fill: ${_invStatusFill(item.status)}">
  <span class="inv-tile-name">${escHtml(item.product_name || "")}</span>
  <span class="inv-tile-countdown">${item.days_left != null ? `${item.days_left}d left` : ""}${
    item.is_estimated && _invShowEstSuffix(item) ? `<span class="inv-tile-est-suffix">~est</span>` : ""
  }</span>
</div>
```

If the existing render uses different variable names, adapt — the key points are:
- the wrapping `<div class="inv-tile-title-row" ...>` with the two CSS vars
- inner `<span>` siblings retain z-index:1 via the CSS rule

- [ ] **Step 4: Add the helper JS functions**

In the same `<script>` block, near other `_inv*` helpers, append:

```javascript
function _invStatusFill(status) {
  switch (status) {
    case "fresh": return "rgba(52, 199, 89, 0.18)";
    case "low":   return "rgba(255, 159, 10, 0.20)";
    case "out":   return "rgba(255, 69, 58, 0.22)";
    default:      return "rgba(52, 199, 89, 0.18)";
  }
}

function _invShowEstSuffix(item) {
  // Show "~est" suffix only when no manual override touched recently AND
  // last_purchased_at is more than ~7 days old (i.e. the auto-decay
  // estimate is now non-trivial and worth flagging as approximate).
  if (!item.is_estimated) return false;
  if (!item.last_purchased_at) return false;
  const ageDays = (Date.now() - new Date(item.last_purchased_at).getTime()) / 86400000;
  return ageDays > 7;
}
```

- [ ] **Step 5: Smoke test the render**

If a dev server is running:
- Open Inventory page → tile title rows should now have a subtle colored fill behind name + countdown
- Recently-purchased items (≤2 days) should be ~full green
- Items at 30-50% remaining should be ~half amber
- Items past shelf life should be barely-filled red

If no dev server, syntax-verify:
```bash
git show HEAD -- src/frontend/index.html | grep -i innerhtml
```
Should be empty for additions. Look for balanced braces in your additions.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(inventory): subtle title-row fill drives status visualization"
```

---

## Task 5: Frontend interactions — tap to cycle, long-press to drag

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add the cycle-status handler**

In the same `<script>` block, append:

```javascript
const _INV_STATUS_BUCKET = { fresh: 80, low: 40, out: 10 };

async function _invCycleStatus(itemId, currentStatus) {
  const order = ["fresh", "low", "out"];
  const idx = Math.max(0, order.indexOf(currentStatus));
  const next = order[(idx + 1) % order.length];
  const nextRemaining = _INV_STATUS_BUCKET[next];
  // Persist override = 100 - remaining (i.e. consumed)
  const consumed = 100 - nextRemaining;
  await _invSetOverride(itemId, consumed);
}

async function _invSetOverride(itemId, consumedPct) {
  try {
    const res = await api(`/inventory/${itemId}/update`, {
      method: "PUT",
      body: JSON.stringify({ consumed_pct_override: consumedPct }),
    });
    if (!res.ok) {
      toast("Could not update status", "error");
      return;
    }
    if (typeof loadInventory === "function") loadInventory();
  } catch (e) {
    toast("Update failed", "error");
  }
}
```

Note the endpoint: `/inventory/<id>/update` (existing `update_item` route — it sets quantity). Inspect it: does it accept `consumed_pct_override` in the body? If not, you must augment it. Search for `update_item` in `src/backend/manage_inventory.py`. If the body parsing only handles `quantity`, add a branch:

```python
data = request.get_json(silent=True) or {}
if "quantity" in data:
    item.quantity = float(data["quantity"])
if "consumed_pct_override" in data:
    raw = data.get("consumed_pct_override")
    if raw is None:
        item.consumed_pct_override = None
    else:
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return jsonify({"error": "consumed_pct_override must be a number or null"}), 400
        if v < 0 or v > 100:
            return jsonify({"error": "consumed_pct_override must be 0..100"}), 400
        item.consumed_pct_override = v
item.updated_by = user_id
session.commit()
```

If you augmented the route, commit that change as part of the task and add a regression test:

```python
def test_update_item_sets_consumed_pct_override(app):
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product
    from flask import g
    from src.backend.initialize_database_schema import User

    user_id = _make_user(app, email=f"override_{uuid.uuid4().hex[:6]}@test.local", name="Ovr")
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Apples-{uuid.uuid4().hex[:6]}", category="fruit")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=3, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/update"
        with app.test_request_context(path, method="PUT", json={"consumed_pct_override": 30.0}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(item_id=item_id)
        inv = session.get(Inventory, item_id)
        assert inv.consumed_pct_override == 30.0
    finally:
        session.close()
```

- [ ] **Step 2: Wire the click handler on the title row**

In the tile template, add an onclick to the wrapper:

```html
<div class="inv-tile-title-row"
     data-inv-id="${item.id}"
     data-inv-status="${item.status || 'fresh'}"
     onclick="_invCycleStatus(${item.id}, '${item.status || 'fresh'}')"
     style="--remaining-pct: ${Math.max(0, Math.min(100, item.remaining_pct ?? 100))}%;
            --status-fill: ${_invStatusFill(item.status)};
            cursor: pointer">
```

(Adjust to match the wrapper added in Task 4 step 3.)

- [ ] **Step 3: Long-press drag to set %**

Append:

```javascript
let _invDragState = null;

function _invInitDragHandlers() {
  document.addEventListener("touchstart", _invDragMaybeStart, { passive: true });
  document.addEventListener("touchmove", _invDragMove, { passive: false });
  document.addEventListener("touchend", _invDragEnd);
  document.addEventListener("mousedown", _invDragMaybeStart);
  document.addEventListener("mousemove", _invDragMove);
  document.addEventListener("mouseup", _invDragEnd);
}

function _invDragMaybeStart(e) {
  const target = (e.target && e.target.closest)
    ? e.target.closest(".inv-tile-title-row")
    : null;
  if (!target) return;
  const itemId = target.dataset.invId;
  if (!itemId) return;
  const longPressTimer = setTimeout(() => {
    _invDragState = {
      itemId: parseInt(itemId, 10),
      el: target,
      rect: target.getBoundingClientRect(),
      active: true,
    };
    target.style.cursor = "ew-resize";
  }, 450);
  const cancel = () => clearTimeout(longPressTimer);
  document.addEventListener("touchend", cancel, { once: true });
  document.addEventListener("mouseup", cancel, { once: true });
  document.addEventListener("touchmove", function _firstMove() {
    cancel();
    document.removeEventListener("touchmove", _firstMove);
  }, { once: true, passive: true });
}

function _invDragMove(e) {
  if (!_invDragState || !_invDragState.active) return;
  e.preventDefault && e.preventDefault();
  const point = e.touches ? e.touches[0] : e;
  const rect = _invDragState.rect;
  const ratio = (point.clientX - rect.left) / rect.width;
  const remaining = Math.round(Math.max(0, Math.min(100, ratio * 100)) / 5) * 5;
  _invDragState.el.style.setProperty("--remaining-pct", remaining + "%");
  _invDragState.lastRemaining = remaining;
}

async function _invDragEnd() {
  if (!_invDragState || !_invDragState.active) {
    _invDragState = null;
    return;
  }
  const finalRemaining = _invDragState.lastRemaining;
  const itemId = _invDragState.itemId;
  if (_invDragState.el) _invDragState.el.style.cursor = "";
  _invDragState = null;
  if (typeof finalRemaining === "number") {
    await _invSetOverride(itemId, 100 - finalRemaining);
  }
}

document.addEventListener("DOMContentLoaded", _invInitDragHandlers);
```

The click handler from Step 2 will still fire on a quick tap (the long-press only activates after 450ms hold + a horizontal drag). Quick taps cycle status; held drags set exact %.

- [ ] **Step 4: Smoke test**

If a dev server runs:
- Quick tap on title row → status cycles fresh→low→out→fresh, fill width animates to bucket midpoint
- Long-press (>450ms) + drag horizontally → fill follows finger; release saves
- Browser console has no errors

If no dev server, just confirm syntax of additions.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html src/backend/manage_inventory.py tests/test_cards_overview.py
git commit -m "feat(inventory): tap-to-cycle status + long-press drag to set %"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run all cards-overview tests**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: every test passes.

- [ ] **Step 2: Browser smoke checklist**

- [ ] Open Inventory page → tiles render with subtle colored fill behind name + countdown
- [ ] Just-purchased items: green, near-100% wide
- [ ] Mid-shelf items: amber, ~50% wide
- [ ] Past-shelf items: red, narrow
- [ ] Tap title row → status cycles, fill animates
- [ ] Long-press + drag → fill follows finger, releases save
- [ ] `−1` button → fill width shrinks proportionally
- [ ] After full consume → fill collapses, row turns red
- [ ] Receipt scan / re-purchase → row resets to ~100% green
- [ ] `~est` suffix appears next to countdown only when (a) `is_estimated == true` AND (b) last_purchased_at > 7 days ago
- [ ] DOM inspection: name + mask use `textContent` (no HTML injection)

- [ ] **Step 3: No new commit**

If smoke passes, ship. Failures → follow-up commit.

---

## Self-review

**Spec coverage:**
- §1 Architecture → Tasks 1-5
- §2 Data model → Task 1 (migration, model)
- §3 Compute (server-side) → Task 2 (`compute_inventory_status` + tests)
- §4 Action behavior → Task 3 (consume), Task 5 (override-set on update + drag/cycle)
- §5 Frontend → Tasks 4 + 5
- §6 Errors + edge cases → covered by Task 2 tests (null anchor, unknown category, ancient purchase, override clamp)
- §7 Testing → all named tests included

**Placeholder scan:** No "TBD"/"TODO". Each step has complete code or a concrete grep-and-edit instruction.

**Type consistency:** `consumed_pct_override`, `expected_shelf_days`, `remaining_pct`, `status`, `shelf_days`, `is_estimated` used identically across migration, model, helper, serializer, response JSON, frontend reads.
