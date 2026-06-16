# Kitchen Essentials Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-derived Kitchen tab (frequent / browse / running-low / current-list blocks) with a single user-curated Essentials grid, tagged from the Product and Inventory views.

**Architecture:** Two new boolean columns on `Product` (`is_essential`, `has_backup`). A rewritten pure aggregator `get_kitchen_essentials` returns only essential products with summed inventory quantity, backup state, and on-list state — plus a frequency-seeded `suggested` list when the user has tagged nothing yet. Two new `PUT` toggle endpoints (mirroring the existing `regular-use` route) serve every tagging surface. The Kitchen frontend is stripped to one grid + a tap-to-open detail sheet.

**Tech Stack:** Python / Flask / SQLAlchemy / Alembic (backend), pytest (tests), vanilla JS in `src/frontend/index.html` (frontend).

**Spec:** `docs/superpowers/specs/2026-06-16-kitchen-essentials-redesign-design.md`

**Scope note (decided during planning):** "Clear everything, keep only essentials" also removes the Kitchen tab's **Current List** block (a shopping-list mirror). The shopping list remains fully available in the Shopping tab. Weather/clock/browse/running-low are all removed from the Kitchen surface. Inventory's own running-low/threshold features are untouched in the Inventory tab.

---

## File Structure

- **Create:** `alembic/versions/034_product_essential_backup.py` — additive migration for the two columns.
- **Modify:** `src/backend/initialize_database_schema.py` — add columns to the `Product` model.
- **Modify:** `src/backend/manage_kitchen.py` — replace `get_kitchen_catalog` with `get_kitchen_essentials`.
- **Modify:** `src/backend/manage_kitchen_endpoint.py` — point the route at the new aggregator.
- **Modify:** `src/backend/manage_inventory.py` — add `essential` + `backup` PUT routes.
- **Modify:** `tests/test_manage_kitchen.py` — rewrite catalog tests for the new shape.
- **Create:** `tests/test_inventory_essential_backup.py` — endpoint toggle tests.
- **Modify:** `src/frontend/index.html` — strip old kitchen markup/JS; add essentials grid, detail sheet, suggestions; add tagging toggles to inventory + product views.

---

## Task 1: Add `is_essential` + `has_backup` columns to the Product model

**Files:**
- Modify: `src/backend/initialize_database_schema.py:125` (after `is_regular_use`)
- Test: `tests/test_manage_kitchen.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_manage_kitchen.py` (uses the existing `db_session` fixture and `_fresh_product` helper):

```python
def test_product_essential_backup_default_false(db_session):
    p = _fresh_product(db_session, "Olive Oil", category="Pantry")
    db_session.commit()
    db_session.refresh(p)
    assert p.is_essential is False
    assert p.has_backup is False


def test_product_essential_backup_settable(db_session):
    p = _fresh_product(db_session, "Olive Oil", category="Pantry")
    p.is_essential = True
    p.has_backup = True
    db_session.commit()
    db_session.refresh(p)
    assert p.is_essential is True
    assert p.has_backup is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_manage_kitchen.py::test_product_essential_backup_default_false -v`
Expected: FAIL — `AttributeError: 'Product' object has no attribute 'is_essential'` (or a column error).

- [ ] **Step 3: Add the columns**

In `src/backend/initialize_database_schema.py`, in `class Product`, immediately after the `is_regular_use` line (`:125`):

```python
    is_regular_use = Column(Boolean, nullable=True, default=False)
    # User-curated kitchen essentials. is_essential drives the Kitchen tab grid;
    # has_backup is an explicit "I have a spare on hand" bit set from the tile.
    is_essential = Column(Boolean, nullable=False, default=False, server_default="0")
    has_backup = Column(Boolean, nullable=False, default=False, server_default="0")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_manage_kitchen.py::test_product_essential_backup_default_false tests/test_manage_kitchen.py::test_product_essential_backup_settable -v`
Expected: PASS (the in-memory schema is built from the model via `Base.metadata.create_all`).

- [ ] **Step 5: Commit**

```bash
git add src/backend/initialize_database_schema.py tests/test_manage_kitchen.py
git commit -m "feat(kitchen): add Product.is_essential + has_backup columns"
```

---

## Task 2: Alembic migration for the two columns

**Files:**
- Create: `alembic/versions/034_product_essential_backup.py`

- [ ] **Step 1: Write the migration**

Create `alembic/versions/034_product_essential_backup.py`:

```python
"""product essential + backup flags for the Kitchen essentials grid.

Revision ID: 034_product_essential_backup
Revises: 033_shared_dining
Create Date: 2026-06-16

Additive only — two boolean columns on products, both default False.
Downgrade drops them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "034_product_essential_backup"
down_revision: Union[str, None] = "033_shared_dining"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_essential", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "products",
        sa.Column("has_backup", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("products", "has_backup")
    op.drop_column("products", "is_essential")
```

- [ ] **Step 2: Verify the migration chain is linear**

Run: `python -m alembic heads`
Expected: a single head — `034_product_essential_backup`. If `alembic` is invoked differently in this repo, check the `Makefile` for the migrate target (e.g. `make migrate`).

- [ ] **Step 3: Apply the migration against a scratch DB**

Run: `python -m alembic upgrade head`
Expected: completes without error; `products` table now has `is_essential` and `has_backup`.

- [ ] **Step 4: Verify downgrade is clean**

Run: `python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: both complete without error.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/034_product_essential_backup.py
git commit -m "feat(kitchen): migration 034 for is_essential + has_backup"
```

---

## Task 3: Replace `get_kitchen_catalog` with `get_kitchen_essentials`

**Files:**
- Modify: `src/backend/manage_kitchen.py:64-215`
- Test: `tests/test_manage_kitchen.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_manage_kitchen.py`, change the aggregator import:

```python
from src.backend.manage_kitchen import get_kitchen_essentials
```

Delete the old catalog-shape tests (`test_empty_db_returns_empty_buckets` and every other test that calls `get_kitchen_catalog`). Keep the `category_for_product` truth-table tests and the `db_session` / `_fresh_product` / `_record_purchase` fixtures. Add an inventory helper and the new tests:

```python
from src.backend.initialize_database_schema import Inventory


def _add_inventory(session, product, quantity, location="Pantry"):
    inv = Inventory(product_id=product.id, quantity=quantity, location=location)
    session.add(inv)
    session.flush()
    return inv


def test_essentials_only_returns_tagged_products(db_session):
    a = _fresh_product(db_session, "Olive Oil", category="Pantry", is_essential=True)
    _fresh_product(db_session, "Sprinkles", category="Pantry", is_essential=False)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    names = [t["name"] for t in out["essentials"]]
    assert names == ["Olive Oil"]
    assert out["essentials"][0]["product_id"] == a.id


def test_essentials_excludes_non_product(db_session):
    _fresh_product(db_session, "Bag Fee", category="Other",
                   is_essential=True, is_non_product=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"] == []


def test_essentials_sorted_alphabetically(db_session):
    _fresh_product(db_session, "Zucchini", category="Produce", is_essential=True)
    _fresh_product(db_session, "Apples", category="Produce", is_essential=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["essentials"]] == ["Apples", "Zucchini"]


def test_essentials_quantity_summed_across_locations(db_session):
    p = _fresh_product(db_session, "Milk", category="Dairy", is_essential=True)
    _add_inventory(db_session, p, 1, location="Fridge")
    _add_inventory(db_session, p, 2, location="Pantry")
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["quantity"] == 3.0


def test_essentials_quantity_zero_when_no_inventory(db_session):
    _fresh_product(db_session, "Salt", category="Pantry", is_essential=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["quantity"] == 0.0


def test_essentials_has_backup_reported(db_session):
    _fresh_product(db_session, "Paper Towels", category="Other",
                   is_essential=True, has_backup=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["has_backup"] is True


def test_essentials_on_list_reflects_active_session(db_session):
    p = _fresh_product(db_session, "Eggs", category="Dairy", is_essential=True)
    sess = ShoppingSession(status="active")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        shopping_session_id=sess.id, product_id=p.id, status="open",
    ))
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["on_list"] is True


def test_suggested_only_when_no_essentials(db_session):
    # No essentials → suggestions seeded from frequent purchases.
    p = _fresh_product(db_session, "Bananas", category="Produce")
    _record_purchase(db_session, p, days_ago=3)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"] == []
    assert [t["name"] for t in out["suggested"]] == ["Bananas"]


def test_suggested_empty_once_an_essential_exists(db_session):
    e = _fresh_product(db_session, "Coffee", category="Pantry", is_essential=True)
    p = _fresh_product(db_session, "Bananas", category="Produce")
    _record_purchase(db_session, p, days_ago=3)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["essentials"]] == ["Coffee"]
    assert out["suggested"] == []


def test_suggested_excludes_already_essential(db_session):
    e = _fresh_product(db_session, "Coffee", category="Pantry")  # not essential yet
    _record_purchase(db_session, e, days_ago=2)
    db_session.commit()
    # Coffee is the only frequent product and is NOT essential → it should suggest.
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["suggested"]] == ["Coffee"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_manage_kitchen.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_kitchen_essentials'`.

- [ ] **Step 3: Rewrite the aggregator**

In `src/backend/manage_kitchen.py`, **delete** the entire `get_kitchen_catalog` function (lines `64-215`, from `def get_kitchen_catalog(` to the closing `return {...}`). Keep everything above it (constants, `category_for_product`, the `from sqlalchemy import func` import, and the model imports). Replace with:

```python
def _frequent_tiles(session, *, now, exclude_ids):
    """Top frequent purchases (last FREQUENCY_WINDOW_DAYS), as ProductTiles,
    excluding any product ids in `exclude_ids`. Used to seed suggestions."""
    cutoff = now - timedelta(days=FREQUENCY_WINDOW_DAYS)

    snapshot_subq = (
        session.query(
            ProductSnapshot.product_id.label("product_id"),
            func.max(ProductSnapshot.id).label("snapshot_id"),
        )
        .filter(ProductSnapshot.product_id.isnot(None))
        .group_by(ProductSnapshot.product_id)
        .subquery()
    )
    count_subq = (
        session.query(
            ReceiptItem.product_id.label("product_id"),
            func.count(ReceiptItem.id).label("purchase_count"),
        )
        .join(Purchase, Purchase.id == ReceiptItem.purchase_id)
        .filter(Purchase.date >= cutoff)
        .group_by(ReceiptItem.product_id)
        .subquery()
    )
    rows = (
        session.query(Product, snapshot_subq.c.snapshot_id, count_subq.c.purchase_count)
        .join(count_subq, count_subq.c.product_id == Product.id)
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .filter(Product.is_non_product.isnot(True))
        .all()
    )
    tiles = []
    for product, snapshot_id, count in rows:
        if product.id in exclude_ids:
            continue
        if not count:
            continue
        bucket = category_for_product(product)
        tiles.append({
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None,
            "fallback_emoji": CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"]),
            "purchase_count": int(count or 0),
        })
    tiles.sort(key=lambda t: (-t["purchase_count"], t["name"]))
    return tiles[:8]


def get_kitchen_essentials(session, *, now=None) -> dict:
    """Return the user-curated essentials grid plus (only when empty) a
    frequency-seeded suggestion list.

    Shape:
        {
          "essentials": [
            {"product_id", "name", "category", "image_url", "fallback_emoji",
             "quantity": float, "has_backup": bool, "on_list": bool,
             "latest_unit_price": float | None},
            ...
          ],
          "suggested": [<ProductTile>, ...]   # [] once any essential exists
        }
    """
    now = now or datetime.now(timezone.utc)

    snapshot_subq = (
        session.query(
            ProductSnapshot.product_id.label("product_id"),
            func.max(ProductSnapshot.id).label("snapshot_id"),
        )
        .filter(ProductSnapshot.product_id.isnot(None))
        .group_by(ProductSnapshot.product_id)
        .subquery()
    )
    qty_subq = (
        session.query(
            Inventory.product_id.label("product_id"),
            func.coalesce(func.sum(Inventory.quantity), 0.0).label("qty"),
        )
        .group_by(Inventory.product_id)
        .subquery()
    )
    latest_price_subq = (
        session.query(
            PriceHistory.product_id.label("product_id"),
            func.max(PriceHistory.id).label("price_history_id"),
        )
        .filter(PriceHistory.product_id.isnot(None))
        .group_by(PriceHistory.product_id)
        .subquery()
    )

    rows = (
        session.query(
            Product,
            snapshot_subq.c.snapshot_id,
            qty_subq.c.qty,
            PriceHistory.price.label("latest_price"),
        )
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .outerjoin(qty_subq, qty_subq.c.product_id == Product.id)
        .outerjoin(latest_price_subq, latest_price_subq.c.product_id == Product.id)
        .outerjoin(PriceHistory, PriceHistory.id == latest_price_subq.c.price_history_id)
        .filter(Product.is_essential.is_(True))
        .filter(Product.is_non_product.isnot(True))
        .all()
    )

    # on-list product ids on active / ready_to_bill sessions
    current_ids = [
        s.id for s in session.query(ShoppingSession.id)
        .filter(ShoppingSession.status.in_(("active", "ready_to_bill")))
        .all()
    ]
    on_list_ids = set()
    if current_ids:
        on_list_ids = {
            row[0] for row in session.query(ShoppingListItem.product_id)
            .filter(
                ShoppingListItem.shopping_session_id.in_(current_ids),
                ShoppingListItem.product_id.isnot(None),
                ShoppingListItem.status.in_(["open", "skipped"]),
            )
            .distinct()
            .all()
        }

    essentials = []
    for product, snapshot_id, qty, latest_price in rows:
        bucket = category_for_product(product)
        essentials.append({
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None,
            "fallback_emoji": CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"]),
            "quantity": float(qty or 0.0),
            "has_backup": bool(product.has_backup),
            "on_list": product.id in on_list_ids,
            "latest_unit_price": float(latest_price) if latest_price is not None else None,
        })
    essentials.sort(key=lambda t: t["name"].lower())

    suggested = []
    if not essentials:
        suggested = _frequent_tiles(session, now=now, exclude_ids=set())

    return {"essentials": essentials, "suggested": suggested}
```

Add `Inventory` to the model import block near the top of the file:

```python
from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, Purchase, ReceiptItem,
    ShoppingListItem, ShoppingSession, PriceHistory, Inventory,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_manage_kitchen.py -v`
Expected: PASS — all new essentials/suggested tests plus the retained `category_for_product` tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_kitchen.py tests/test_manage_kitchen.py
git commit -m "feat(kitchen): get_kitchen_essentials replaces get_kitchen_catalog"
```

---

## Task 4: Point the kitchen endpoint at the new aggregator

**Files:**
- Modify: `src/backend/manage_kitchen_endpoint.py`

- [ ] **Step 1: Update the endpoint**

Replace the body of `src/backend/manage_kitchen_endpoint.py` with:

```python
"""Flask blueprint for the Kitchen essentials read endpoint.

Exposes:
  GET /api/kitchen/essentials — user-curated essentials grid (+ suggestions
  when the user has tagged nothing yet).

All mutations reuse existing /inventory and /shopping-list routes; this
blueprint is read-only by design.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from src.backend.create_flask_application import require_auth
from src.backend.manage_kitchen import get_kitchen_essentials


kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/api/kitchen")


@kitchen_bp.route("/essentials", methods=["GET"])
@require_auth
def get_essentials():
    return jsonify(get_kitchen_essentials(g.db_session)), 200
```

- [ ] **Step 2: Verify the app imports cleanly**

Run: `python -c "import src.backend.manage_kitchen_endpoint"`
Expected: no ImportError.

- [ ] **Step 3: Commit**

```bash
git add src/backend/manage_kitchen_endpoint.py
git commit -m "feat(kitchen): GET /api/kitchen/essentials endpoint"
```

---

## Task 5: Add `essential` + `backup` toggle endpoints

**Files:**
- Modify: `src/backend/manage_inventory.py` (after the `set_regular_use` route, `:528`)
- Test: `tests/test_inventory_essential_backup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_inventory_essential_backup.py`. This calls the route handlers through the pure-function style used elsewhere; if the suite has an app/client fixture, prefer it — otherwise drive via a Flask test client built from `create_flask_application`. Use the in-memory pattern:

```python
import json
import pytest

from src.backend.initialize_database_schema import (
    Base, Product, create_db_engine, create_session_factory,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path/'inv.db'}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _product(session, name="Olive Oil"):
    p = Product(name=name, category="Pantry")
    session.add(p)
    session.flush()
    return p


def test_set_essential_true_then_false(db_session):
    from src.backend.manage_inventory import set_essential
    p = _product(db_session)
    db_session.commit()
    # Drive the handler with a request context.
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context(json={"is_essential": True}):
        g.db_session = db_session
        resp, status = set_essential(p.id)
        assert status == 200
        assert json.loads(resp.get_data())["is_essential"] is True
    db_session.refresh(p)
    assert p.is_essential is True

    with app.test_request_context(json={"is_essential": False}):
        g.db_session = db_session
        resp, status = set_essential(p.id)
        assert json.loads(resp.get_data())["is_essential"] is False


def test_set_backup_true(db_session):
    from src.backend.manage_inventory import set_backup
    p = _product(db_session)
    db_session.commit()
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context(json={"has_backup": True}):
        g.db_session = db_session
        resp, status = set_backup(p.id)
        assert status == 200
        assert json.loads(resp.get_data())["has_backup"] is True


def test_set_essential_unknown_product_404(db_session):
    from src.backend.manage_inventory import set_essential
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context(json={"is_essential": True}):
        g.db_session = db_session
        resp, status = set_essential(999999)
        assert status == 404
```

> Note: `@require_write_access` wraps these handlers. Calling the undecorated logic in a request context as above exercises the body. If `require_write_access` blocks the bare call in tests, replicate the project's existing endpoint-test fixture (see how other `manage_inventory` routes are tested) instead of constructing a bare `Flask` app.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inventory_essential_backup.py -v`
Expected: FAIL — `ImportError: cannot import name 'set_essential'`.

- [ ] **Step 3: Add the routes**

In `src/backend/manage_inventory.py`, immediately after the `set_regular_use` function (ends at `:528`), add:

```python
@inventory_bp.route("/products/<int:product_id>/essential", methods=["PUT"])
@require_write_access
def set_essential(product_id):
    """Tag (or clear) a product as a Kitchen essential. Serves every tagging
    surface: inventory row, product detail, kitchen tile, suggestion row."""
    session = g.db_session
    data = request.get_json(silent=True) or {}
    is_essential = bool(data.get("is_essential", True))

    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    product.is_essential = is_essential
    session.commit()
    return jsonify({
        "product_id": product.id,
        "product_name": get_product_display_name(product),
        "is_essential": bool(product.is_essential),
    }), 200


@inventory_bp.route("/products/<int:product_id>/backup", methods=["PUT"])
@require_write_access
def set_backup(product_id):
    """Set (or clear) the 'I have a spare on hand' flag for an essential."""
    session = g.db_session
    data = request.get_json(silent=True) or {}
    has_backup = bool(data.get("has_backup", True))

    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    product.has_backup = has_backup
    session.commit()
    return jsonify({
        "product_id": product.id,
        "product_name": get_product_display_name(product),
        "has_backup": bool(product.has_backup),
    }), 200
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory_essential_backup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_inventory.py tests/test_inventory_essential_backup.py
git commit -m "feat(kitchen): PUT essential + backup toggle endpoints"
```

---

## Task 6: Rebuild the Kitchen tab frontend (grid + detail sheet + suggestions)

**Files:**
- Modify: `src/frontend/index.html` — `#page-kitchen` markup (`3579-3657`); kitchen JS block (`loadKitchen` at `~28726` and the render/handler functions through `~29400`).

> Frontend has no JS unit harness — verify in the browser. Make the markup and JS changes, then run the app and exercise the flows.

- [ ] **Step 1: Replace the `#page-kitchen` markup**

Replace the entire block from `<div class="page" id="page-kitchen">` (`:3579`) through its closing `</div>` (`:3657`, the line before `<!-- Upload -->`) with:

```html
        <div class="page" id="page-kitchen">
          <div class="kitchen-essentials-header">
            <div class="title">⭐ Essentials · <span class="count" id="kitchen-ess-count">0</span></div>
            <span class="onlist-chip" id="kitchen-onlist-chip" onclick="showPage('shopping')">🛒 <span id="kitchen-onlist-count">0</span> on list</span>
          </div>

          <div class="kitchen-ess-grid" id="kitchen-ess-grid"></div>

          <div class="kitchen-ess-empty" id="kitchen-ess-empty" style="display:none">
            <p>No essentials yet. Tag items as <strong>essential</strong> from Products or Inventory and they'll show up here.</p>
            <div class="kitchen-suggest" id="kitchen-suggest" style="display:none">
              <h3 class="kitchen-section-title">Suggested essentials</h3>
              <div class="kitchen-ess-grid" id="kitchen-suggest-grid"></div>
            </div>
          </div>

          <div class="kitchen-sheet" id="kitchen-sheet" style="display: none;">
            <div class="kitchen-sheet-backdrop" onclick="closeKitchenSheet()"></div>
            <div class="kitchen-sheet-card" id="kitchen-sheet-card"></div>
          </div>
        </div>
```

- [ ] **Step 2: Remove the obsolete kitchen JS functions**

In the kitchen JS block, delete these now-unused functions (find each with grep, delete the whole function body): `renderKitchenCatalog`, `renderKitchenList`, `renderKitchenLowGrid`, `renderKitchenStoreFilter`, `kitchenAddLowToList`, `kitchenMarkRestocked`, `toggleKitchenCatalog`, `applyKitchenCatalogCollapsed`, `toggleKitchenNames`, `applyKitchenShowNames`, `toggleKitchenSearchPopover`, `onKitchenSearchInput`, `kitchenGridScrollBy`, `startKitchenClock`, `loadKitchenWeather`, `_kitchenWeatherEmoji`, `_kitchenWeatherDesc`, `_kitchenRenderWeather`.

Run after deleting to catch stragglers:
`grep -n "renderKitchenCatalog\|renderKitchenList\|renderKitchenLowGrid\|renderKitchenStoreFilter\|kitchenAddLowToList\|kitchenMarkRestocked\|toggleKitchenCatalog\|loadKitchenWeather\|startKitchenClock" src/frontend/index.html`
Expected: no matches except inside the strings you're about to remove. Keep `closeKitchenSheet` if it already exists (the detail sheet reuses it); if it doesn't, it's added in Step 4.

- [ ] **Step 3: Replace `loadKitchen`**

Replace the entire `loadKitchen` function (`~28726-28762`) with:

```javascript
      let kitchenEssentials = [];

      async function loadKitchen() {
        try {
          const res = await api("/api/kitchen/essentials");
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "kitchen failed");
          kitchenEssentials = data.essentials || [];
          renderKitchenEssentials(data.suggested || []);
        } catch (err) {
          toast(err.message || "Failed to load kitchen view", "error");
        }
      }
```

- [ ] **Step 4: Add the render + interaction functions**

Add this block right after the new `loadKitchen`:

```javascript
      function _kitchenTileHtml(t, { suggest = false } = {}) {
        const thumb = t.image_url
          ? `<img class="thumb" src="${escAttr(t.image_url)}" alt="" loading="lazy" />`
          : `<div class="thumb">${t.fallback_emoji || shoppingItemEmoji(t.name, t.category)}</div>`;
        if (suggest) {
          // Suggestion tile: one tap marks essential. Pass numeric id only.
          return `
            <div class="kitchen-ess-tile" data-pid="${t.product_id}"
                 onclick="kitchenMarkEssential(${t.product_id})">
              ${thumb}
              <div class="nm">${escHtml(t.name || "Item")}</div>
              <div class="add-ess">＋ Essential</div>
            </div>`;
        }
        const badges = [];
        if (t.on_list) badges.push(`<div class="onlist-badge">✓ On list</div>`);
        if (t.has_backup) badges.push(`<div class="backup-dot" title="Spare on hand">🟢 spare</div>`);
        return `
          <div class="kitchen-ess-tile ${t.on_list ? "on-list" : ""}" data-pid="${t.product_id}"
               onclick="openKitchenDetail(${t.product_id})">
            ${thumb}
            <div class="nm">${escHtml(t.name || "Item")}</div>
            ${badges.join("")}
          </div>`;
      }

      function renderKitchenEssentials(suggested) {
        const grid = document.getElementById("kitchen-ess-grid");
        const empty = document.getElementById("kitchen-ess-empty");
        const countEl = document.getElementById("kitchen-ess-count");
        const onListCountEl = document.getElementById("kitchen-onlist-count");
        if (!grid) return;

        const onListCount = kitchenEssentials.filter((t) => t.on_list).length;
        if (onListCountEl) onListCountEl.textContent = onListCount;
        if (countEl) countEl.textContent = kitchenEssentials.length;

        if (!kitchenEssentials.length) {
          grid.innerHTML = "";
          if (empty) empty.style.display = "block";
          const sg = document.getElementById("kitchen-suggest");
          const sgGrid = document.getElementById("kitchen-suggest-grid");
          if (sg && sgGrid) {
            if (suggested.length) {
              sg.style.display = "block";
              sgGrid.innerHTML = suggested.map((t) => _kitchenTileHtml(t, { suggest: true })).join("");
            } else {
              sg.style.display = "none";
            }
          }
          return;
        }
        if (empty) empty.style.display = "none";
        grid.innerHTML = kitchenEssentials.map((t) => _kitchenTileHtml(t)).join("");
      }

      async function kitchenMarkEssential(productId) {
        try {
          await api(`/inventory/products/${productId}/essential`, {
            method: "PUT",
            body: JSON.stringify({ is_essential: true }),
          });
          toast("Added to essentials ⭐", "success");
          await loadKitchen();
        } catch (err) {
          toast("Could not mark essential", "error");
        }
      }

      function openKitchenDetail(productId) {
        const t = kitchenEssentials.find((x) => Number(x.product_id) === Number(productId));
        if (!t) return;
        const card = document.getElementById("kitchen-sheet-card");
        const sheet = document.getElementById("kitchen-sheet");
        if (!card || !sheet) return;
        const qtyLabel = Number(t.quantity) > 0 ? `${t.quantity} on hand` : "Not tracked";
        card.innerHTML = `
          <div class="ksheet-title">${escHtml(t.name || "Item")}</div>
          <div class="ksheet-row">📦 ${escHtml(qtyLabel)}</div>
          <label class="ksheet-row ksheet-toggle">
            <input type="checkbox" id="ksheet-backup" ${t.has_backup ? "checked" : ""}
                   onchange="kitchenToggleBackup(${t.product_id}, this.checked)">
            <span>I have a backup / spare</span>
          </label>
          <button type="button" class="btn btn-primary ksheet-add"
                  ${t.on_list ? "disabled" : ""}
                  onclick="kitchenAddEssentialToList(${t.product_id}, this)">
            ${t.on_list ? "✓ On shopping list" : "🛒 Add to shopping list"}
          </button>
          <button type="button" class="btn btn-ghost ksheet-remove"
                  onclick="kitchenRemoveEssential(${t.product_id})">Remove from essentials</button>
        `;
        sheet.style.display = "block";
      }

      function closeKitchenSheet() {
        const sheet = document.getElementById("kitchen-sheet");
        if (sheet) sheet.style.display = "none";
      }

      async function kitchenToggleBackup(productId, checked) {
        const t = kitchenEssentials.find((x) => Number(x.product_id) === Number(productId));
        if (t) t.has_backup = checked;
        try {
          await api(`/inventory/products/${productId}/backup`, {
            method: "PUT",
            body: JSON.stringify({ has_backup: checked }),
          });
          renderKitchenEssentials([]);
        } catch (err) {
          toast("Could not update backup", "error");
        }
      }

      async function kitchenAddEssentialToList(productId, btnEl) {
        const t = kitchenEssentials.find((x) => Number(x.product_id) === Number(productId));
        if (!t) return;
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = "✓ On shopping list"; }
        t.on_list = true;
        await quickAddToShoppingList({
          product_id: productId,
          name: t.name,
          category: t.category || "other",
          quantity: 1,
          source: "kitchen_essential",
        });
        renderKitchenEssentials([]);
      }

      async function kitchenRemoveEssential(productId) {
        try {
          await api(`/inventory/products/${productId}/essential`, {
            method: "PUT",
            body: JSON.stringify({ is_essential: false }),
          });
          closeKitchenSheet();
          toast("Removed from essentials", "success");
          await loadKitchen();
        } catch (err) {
          toast("Could not remove", "error");
        }
      }
```

- [ ] **Step 5: Add CSS for the new grid + tiles**

Append to `src/frontend/styles/page-shell/kitchen.css` (reuse existing tile sizing tokens where present; these are minimal styles that follow the old `.kitchen-low-tile` conventions):

```css
.kitchen-essentials-header { display:flex; align-items:center; justify-content:space-between; margin:0 0 12px; }
.kitchen-essentials-header .title { font-weight:600; font-size:1.1rem; }
.kitchen-ess-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:12px; }
.kitchen-ess-tile { position:relative; display:flex; flex-direction:column; align-items:center; gap:6px; padding:10px; border-radius:14px; background:var(--surface,#fff); box-shadow:0 1px 3px rgba(0,0,0,.08); cursor:pointer; }
.kitchen-ess-tile.on-list { outline:2px solid var(--accent,#2e7d32); }
.kitchen-ess-tile .thumb { width:56px; height:56px; display:flex; align-items:center; justify-content:center; font-size:2rem; border-radius:10px; object-fit:cover; }
.kitchen-ess-tile .nm { font-size:.8rem; text-align:center; line-height:1.1; }
.kitchen-ess-tile .onlist-badge { font-size:.7rem; color:var(--accent,#2e7d32); }
.kitchen-ess-tile .backup-dot { font-size:.7rem; }
.kitchen-ess-tile .add-ess { font-size:.72rem; color:var(--accent,#2e7d32); font-weight:600; }
.kitchen-ess-empty { text-align:center; color:var(--muted,#777); padding:24px 8px; }
.kitchen-suggest { margin-top:20px; text-align:left; }
.ksheet-title { font-weight:600; font-size:1.1rem; margin-bottom:12px; }
.ksheet-row { padding:8px 0; }
.ksheet-toggle { display:flex; align-items:center; gap:8px; cursor:pointer; }
.ksheet-add, .ksheet-remove { width:100%; margin-top:10px; }
```

Bump the kitchen.css cache-buster in `index.html:75` (`kitchen.css?v=...`) to a new value so the new styles load.

- [ ] **Step 6: Verify in the browser**

Run the app (see the project run skill / `Makefile`). Then:
1. Open the Kitchen tab with no essentials → empty prompt + "Suggested essentials" row appears (if there are frequent purchases).
2. Tap a suggestion → it's marked essential, grid shows it, suggestions disappear.
3. Tap an essential tile → detail sheet shows quantity / backup toggle / add-to-list / remove.
4. Toggle backup → tile shows the spare indicator after closing.
5. Add to shopping list → button flips to "On shopping list", on-list chip count increments, item appears in the Shopping tab.
6. Remove from essentials → tile leaves the grid.

Expected: all six flows work; no console errors; no leftover references to deleted functions.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/index.html src/frontend/styles/page-shell/kitchen.css
git commit -m "feat(kitchen): essentials grid + detail sheet, strip old kitchen blocks"
```

---

## Task 7: Add essential toggles to Inventory and Product views

**Files:**
- Modify: `src/frontend/index.html` — inventory row rendering and product detail/edit panel.

> Locate the inventory row renderer and the product detail panel with grep; the existing `is_regular_use` star is the closest analog — mirror its placement and call style.

- [ ] **Step 1: Find the existing regular-use toggle in the UI**

Run: `grep -n "regular-use\|is_regular_use\|regular_use" src/frontend/index.html`
Expected: shows where the inventory row renders its star control and the `PUT /inventory/products/<id>/regular-use` call. Use that exact location and pattern.

- [ ] **Step 2: Add an essential star to each inventory row**

In the inventory row renderer (beside the regular-use control found in Step 1), add an essential toggle. Mirror the existing star markup; pass the numeric product id only:

```javascript
        // essential star — sits beside the regular-use star
        `<button type="button" class="inv-ess-star ${row.is_essential ? "on" : ""}"
                 title="Mark essential"
                 onclick="event.stopPropagation(); toggleInventoryEssential(${row.product_id}, ${row.is_essential ? "false" : "true"}, this)">⭐</button>`
```

Add the handler near the other inventory handlers:

```javascript
      async function toggleInventoryEssential(productId, makeEssential, el) {
        try {
          await api(`/inventory/products/${productId}/essential`, {
            method: "PUT",
            body: JSON.stringify({ is_essential: makeEssential }),
          });
          if (el) el.classList.toggle("on", makeEssential);
          // keep the in-memory row in sync if inventory state is cached
          toast(makeEssential ? "Marked essential ⭐" : "Removed from essentials", "success");
        } catch (err) {
          toast("Could not update essential", "error");
        }
      }
```

> The inventory list endpoint must expose `is_essential` on each row. Confirm `manage_inventory.py`'s GET `/inventory` serializer includes `"is_essential": bool(product.is_essential)`; if not, add it to the row dict (alongside the existing `is_regular_use` field).

- [ ] **Step 3: Add an essential toggle to the product detail/edit panel**

Find the product detail panel (`grep -n "catalog-panel-products\|productDetail\|renderProductDetail" src/frontend/index.html`). Add an Essential toggle next to where product flags are edited, calling the same endpoint:

```html
            <label class="prod-flag-toggle">
              <input type="checkbox" id="prod-essential"
                     onchange="toggleProductEssential(PRODUCT_ID_HERE, this.checked)">
              <span>Essential (show in Kitchen)</span>
            </label>
```

Wire the bound product id the same way the panel binds other per-product controls, and add:

```javascript
      async function toggleProductEssential(productId, checked) {
        try {
          await api(`/inventory/products/${productId}/essential`, {
            method: "PUT",
            body: JSON.stringify({ is_essential: checked }),
          });
          toast(checked ? "Marked essential ⭐" : "Removed from essentials", "success");
        } catch (err) {
          toast("Could not update essential", "error");
        }
      }
```

Ensure the product detail fetch includes `is_essential` so the checkbox reflects current state (the product GET serializer in `manage_product_catalog.py` should return it; add if missing).

- [ ] **Step 4: Verify in the browser**

1. Inventory tab → tap the essential star on a row → toast, star fills.
2. Switch to Kitchen tab → that product now appears in the essentials grid.
3. Product detail panel → toggle Essential off → Kitchen grid drops it.

Expected: both entry points drive the same flag; Kitchen reflects changes on reload.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html src/backend/manage_inventory.py src/backend/manage_product_catalog.py
git commit -m "feat(kitchen): tag essentials from inventory rows and product detail"
```

---

## Task 8: Full regression pass

- [ ] **Step 1: Run the backend test suite**

Run: `python -m pytest tests/test_manage_kitchen.py tests/test_inventory_essential_backup.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the broader suite for fallout**

Run: `python -m pytest tests/ -q`
Expected: no new failures. If any test still imports `get_kitchen_catalog`, update it to `get_kitchen_essentials` or remove it.

- [ ] **Step 3: Confirm no dangling references to removed code**

Run: `grep -rn "get_kitchen_catalog\|kitchen/catalog\|renderKitchenLowGrid\|kitchenLowItems" src tests`
Expected: no matches.

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "test(kitchen): regression cleanup for essentials redesign"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** data model (Task 1-2), `get_kitchen_essentials` shape incl. quantity-summed / on_list / suggested-when-empty (Task 3), endpoint swap (Task 4), two toggle routes mirroring regular-use (Task 5), essentials grid + detail sheet + empty/suggestions (Task 6), both tagging entry points (Task 7), removal of frequent/browse/running-low + Current List (Task 6). All spec sections mapped.
- **Type consistency:** return keys (`essentials`, `suggested`, `quantity`, `has_backup`, `on_list`) are identical across backend tests, aggregator, and frontend consumers. Endpoint bodies (`is_essential`, `has_backup`) match between handlers, tests, and all JS call sites.
- **Placeholders:** none — `PRODUCT_ID_HERE` in Task 7 Step 3 is explicitly flagged as "bind like the panel's other per-product controls," not a silent gap; backend serializer additions are called out where they may be missing.
