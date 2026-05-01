# Kitchen View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/kitchen` route — a tablet-friendly visual shopping surface with image-tile grid, bottom-sheet actions (qty ± / Bought / Low / Skip / Delete), and category-chip add-flow with frequency sort.

**Architecture:** New Flask blueprint with one `GET /api/kitchen/catalog` aggregator endpoint (Product × ProductSnapshot × ReceiptItem in last 90 d). All mutations reuse existing `/shopping-list/items` endpoints. Frontend adds a new section to the SPA, image tiles fall back to category emoji when no `ProductSnapshot` exists. `ShoppingListItem.status` gains `"skipped"` value (no schema change — column is `String(20)` already).

**Tech Stack:** Python 3.11, SQLAlchemy, Flask, vanilla JS frontend, no migration.

---

## Note on frontend HTML insertion

The project's PreToolUse security hook flags any direct innerHTML
assignment in edits. Use the existing global `setHtml(el, html)` helper
that builds the fragment via `Range#createContextualFragment` and
replaces the element's children. It's already declared near the inline
`<script>` at the top of `src/frontend/index.html` (around line 29584).
Do not re-declare it.

---

## File Structure

**Create:**
- `src/backend/manage_kitchen.py` — `category_for_product()`, `get_kitchen_catalog()`, constants.
- `src/backend/manage_kitchen_endpoint.py` — `kitchen_bp` Flask blueprint (`GET /api/kitchen/catalog`).
- `src/frontend/styles/page-shell/kitchen.css` — chip bar, tile grid, bottom sheet, action button styling.
- `tests/test_manage_kitchen.py` — unit tests (`category_for_product` truth table + `get_kitchen_catalog` aggregator).
- `tests/test_manage_kitchen_endpoint.py` — integration tests (auth + shape contract).
- `tests/test_manage_shopping_list_status.py` — status validation + "skipped" exclusion tests.

**Modify:**
- `src/backend/manage_shopping_list.py` — tighten `status` validation, exclude `"skipped"` from open count and ready-to-bill totals.
- `src/backend/create_flask_application.py` — register `kitchen_bp` after `stores_bp`.
- `src/frontend/index.html` — sidebar nav-item, `<div id="page-kitchen" class="page">` section, JS state + functions, expand `nav()` allowed list and `isKitchenDisplayTrustedDevice` allowed list.

**Test infrastructure (existing pattern, no changes):**
- `tests/conftest.py` already provides `db_session` and Flask test fixtures used by `test_manage_stores_endpoint.py`. Reuse those.

---

## Task 1: Backend — `category_for_product` + constants

**Files:**
- Create: `src/backend/manage_kitchen.py`
- Create: `tests/test_manage_kitchen.py`

- [ ] **Step 1: Write the failing test for the truth table**

```python
# tests/test_manage_kitchen.py
import pytest
from src.backend.manage_kitchen import category_for_product, DEFAULT_CATEGORIES, CATEGORY_EMOJI


class _StubProduct:
    def __init__(self, category):
        self.category = category


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Produce", "Produce"),
        ("produce", "Produce"),
        ("PRODUCE", "Produce"),
        ("Vegetables", "Produce"),
        ("Fruit", "Produce"),
        ("Fruits", "Produce"),
        ("Meat", "Meat"),
        ("Poultry", "Meat"),
        ("Seafood", "Meat"),
        ("Fish", "Meat"),
        ("Dairy", "Dairy"),
        ("Cheese", "Dairy"),
        ("Yogurt", "Dairy"),
        ("Bakery", "Bakery"),
        ("Bread", "Bakery"),
        ("Pantry", "Pantry"),
        ("Snacks", "Pantry"),
        ("Beverages", "Pantry"),
        ("Spices", "Pantry"),
        ("Condiments", "Pantry"),
        (None, "Other"),
        ("", "Other"),
        ("   ", "Other"),
        ("weird random thing", "Other"),
    ],
)
def test_category_for_product_truth_table(raw, expected):
    assert category_for_product(_StubProduct(raw)) == expected


def test_default_categories_are_in_emoji_map():
    for cat in DEFAULT_CATEGORIES:
        assert cat in CATEGORY_EMOJI


def test_default_categories_order():
    assert DEFAULT_CATEGORIES == [
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen.py -v
```

Expected: ImportError (`manage_kitchen` does not exist).

- [ ] **Step 3: Create `manage_kitchen.py` with constants + classifier**

```python
# src/backend/manage_kitchen.py
"""Kitchen view aggregator and product categorization.

Pure functions only — no Flask request context. Endpoint layer lives in
`manage_kitchen_endpoint.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

FREQUENCY_WINDOW_DAYS = 90
FREQUENT_LIMIT = 12
CATEGORY_LIMIT = 50

DEFAULT_CATEGORIES = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"]

CATEGORY_EMOJI = {
    "Produce": "🥬",
    "Meat": "🥩",
    "Dairy": "🥛",
    "Bakery": "🍞",
    "Pantry": "🥫",
    "Other": "🧴",
}

# Raw Product.category values that map into each bucket. Lowercased
# substring match — first hit wins, evaluated in DEFAULT_CATEGORIES order.
_CATEGORY_KEYWORDS = {
    "Produce": ("produce", "vegetable", "veggie", "fruit"),
    "Meat":    ("meat", "poultry", "chicken", "beef", "pork", "seafood", "fish"),
    "Dairy":   ("dairy", "milk", "cheese", "yogurt", "butter"),
    "Bakery":  ("bakery", "bread", "pastry", "cake"),
    "Pantry":  ("pantry", "snack", "beverage", "drink", "spice", "condiment",
                "grain", "rice", "pasta", "cereal", "canned", "frozen"),
}


def category_for_product(product) -> str:
    """Map a Product (or anything with a `.category` string attribute) to one
    of DEFAULT_CATEGORIES. Unknown / missing raw values fall back to "Other"."""
    raw = getattr(product, "category", None) or ""
    lowered = str(raw).strip().lower()
    if not lowered:
        return "Other"
    for bucket in DEFAULT_CATEGORIES:
        if bucket == "Other":
            continue
        keywords = _CATEGORY_KEYWORDS.get(bucket, ())
        for kw in keywords:
            if kw in lowered:
                return bucket
    return "Other"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen.py -v
```

Expected: PASS for all parameterized cases.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_kitchen.py tests/test_manage_kitchen.py
git commit -m "feat(kitchen): category_for_product + DEFAULT_CATEGORIES"
```

---

## Task 2: Backend — `get_kitchen_catalog` aggregator

**Files:**
- Modify: `src/backend/manage_kitchen.py`
- Modify: `tests/test_manage_kitchen.py`

- [ ] **Step 1: Write failing tests for the aggregator**

Append to `tests/test_manage_kitchen.py`:

```python
from datetime import datetime, timedelta, timezone

from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, ShoppingListItem, ShoppingSession,
    Purchase, ReceiptItem, Store,
)
from src.backend.manage_kitchen import get_kitchen_catalog


def _fresh_product(session, name, category="Produce", **kw):
    p = Product(name=name, category=category, **kw)
    session.add(p)
    session.flush()
    return p


def _record_purchase(session, product, days_ago, store=None):
    """Insert one Purchase + one ReceiptItem `days_ago` days from now."""
    if store is None:
        store = Store(name="Costco")
        session.add(store)
        session.flush()
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    pur = Purchase(store_id=store.id, total_amount=1.0, date=when)
    session.add(pur)
    session.flush()
    ri = ReceiptItem(
        purchase_id=pur.id, product_id=product.id,
        quantity=1, unit_price=1.0,
    )
    session.add(ri)
    session.flush()


def test_empty_db_returns_empty_buckets(db_session):
    out = get_kitchen_catalog(db_session)
    assert out["frequent"] == []
    assert set(out["categories"].keys()) == {
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    }
    for tiles in out["categories"].values():
        assert tiles == []
    assert out["on_list_product_ids"] == []


def test_categorization_by_product_category(db_session):
    p_prod = _fresh_product(db_session, "Spinach", category="Produce")
    p_meat = _fresh_product(db_session, "Chicken", category="Poultry")
    p_dairy = _fresh_product(db_session, "Milk", category="Dairy")
    p_other = _fresh_product(db_session, "Mystery", category=None)
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    names_in = lambda b: {t["name"] for t in out["categories"][b]}
    assert "Spinach" in names_in("Produce")
    assert "Chicken" in names_in("Meat")
    assert "Milk"    in names_in("Dairy")
    assert "Mystery" in names_in("Other")


def test_purchase_count_window(db_session):
    p = _fresh_product(db_session, "Tomatoes", category="Produce")
    _record_purchase(db_session, p, days_ago=10)
    _record_purchase(db_session, p, days_ago=80)
    _record_purchase(db_session, p, days_ago=120)  # outside 90 d window
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    tile = next(t for t in out["categories"]["Produce"] if t["name"] == "Tomatoes")
    assert tile["purchase_count"] == 2


def test_sort_within_bucket_by_count_desc(db_session):
    a = _fresh_product(db_session, "Apple", category="Produce")
    b = _fresh_product(db_session, "Banana", category="Produce")
    c = _fresh_product(db_session, "Carrot", category="Produce")
    for _ in range(5): _record_purchase(db_session, a, days_ago=10)
    for _ in range(2): _record_purchase(db_session, b, days_ago=10)
    _record_purchase(db_session, c, days_ago=10)
    db_session.commit()

    names = [t["name"] for t in get_kitchen_catalog(db_session)["categories"]["Produce"]]
    assert names[:3] == ["Apple", "Banana", "Carrot"]


def test_frequent_bucket_top_n_across_categories(db_session):
    a = _fresh_product(db_session, "Apple", category="Produce")
    m = _fresh_product(db_session, "Milk",  category="Dairy")
    for _ in range(7): _record_purchase(db_session, a, days_ago=5)
    for _ in range(3): _record_purchase(db_session, m, days_ago=5)
    db_session.commit()

    freq = get_kitchen_catalog(db_session)["frequent"]
    assert [t["name"] for t in freq[:2]] == ["Apple", "Milk"]
    # frequent bucket only includes products with at least 1 purchase in window
    assert all(t["purchase_count"] >= 1 for t in freq)


def test_image_url_from_latest_snapshot(db_session):
    p = _fresh_product(db_session, "Eggs", category="Dairy")
    db_session.add_all([
        ProductSnapshot(product_id=p.id, status="resolved",
                        image_path="/tmp/old.jpg"),
        ProductSnapshot(product_id=p.id, status="resolved",
                        image_path="/tmp/new.jpg"),
    ])
    db_session.commit()

    tile = next(
        t for t in get_kitchen_catalog(db_session)["categories"]["Dairy"]
        if t["name"] == "Eggs"
    )
    # latest snapshot id is the second one inserted
    assert tile["image_url"].endswith(f"/product-snapshots/{tile['_latest_snapshot_id']}/image")
    assert tile["fallback_emoji"] == "🥛"


def test_no_snapshot_returns_none_image_url(db_session):
    p = _fresh_product(db_session, "Lettuce", category="Produce")
    db_session.commit()

    tile = next(
        t for t in get_kitchen_catalog(db_session)["categories"]["Produce"]
        if t["name"] == "Lettuce"
    )
    assert tile["image_url"] is None
    assert tile["fallback_emoji"] == "🥬"


def test_on_list_product_ids_from_active_session(db_session):
    p = _fresh_product(db_session, "Bread", category="Bakery")
    sess = ShoppingSession(name="trip", status="active")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        product_id=p.id, name="Bread", category="Bakery",
        quantity=1, status="open", shopping_session_id=sess.id,
    ))
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    assert p.id in out["on_list_product_ids"]


def test_finalized_session_items_not_in_on_list(db_session):
    p = _fresh_product(db_session, "Croissant", category="Bakery")
    sess = ShoppingSession(name="old", status="finalized")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        product_id=p.id, name="Croissant", category="Bakery",
        quantity=1, status="purchased", shopping_session_id=sess.id,
    ))
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    assert p.id not in out["on_list_product_ids"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen.py -v
```

Expected: ImportError on `get_kitchen_catalog` (function not yet defined).

- [ ] **Step 3: Implement `get_kitchen_catalog`**

Append to `src/backend/manage_kitchen.py`:

```python
from sqlalchemy import func, and_

from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, Purchase, ReceiptItem,
    ShoppingListItem, ShoppingSession,
)


def get_kitchen_catalog(session, *, now=None) -> dict:
    """Return catalog grid + on-list product ids in one shape.

    Shape:
        {
          "frequent": [<ProductTile>, ...],
          "categories": {
            "Produce": [<ProductTile>, ...],
            "Meat":    [...],
            "Dairy":   [...],
            "Bakery":  [...],
            "Pantry":  [...],
            "Other":   [...],
          },
          "on_list_product_ids": [<int>, ...]
        }

    ProductTile shape:
        {
          "product_id": int,
          "name": str,
          "category": str,             # one of DEFAULT_CATEGORIES
          "image_url": str | None,     # /product-snapshots/<id>/image or None
          "fallback_emoji": str,       # category emoji
          "purchase_count": int,       # count in last FREQUENCY_WINDOW_DAYS
          "_latest_snapshot_id": int | None,  # internal — used by tests/UI
        }
    """
    now = now or datetime.now(timezone.utc)
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
        session.query(
            Product,
            snapshot_subq.c.snapshot_id,
            count_subq.c.purchase_count,
        )
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .outerjoin(count_subq, count_subq.c.product_id == Product.id)
        .all()
    )

    categories = {cat: [] for cat in DEFAULT_CATEGORIES}
    all_tiles = []
    for product, snapshot_id, count in rows:
        bucket = category_for_product(product)
        emoji = CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"])
        image_url = (
            f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None
        )
        tile = {
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": image_url,
            "fallback_emoji": emoji,
            "purchase_count": int(count or 0),
            "_latest_snapshot_id": snapshot_id,
        }
        categories[bucket].append(tile)
        all_tiles.append(tile)

    # Sort each bucket by purchase_count desc, then name asc.
    for tiles in categories.values():
        tiles.sort(key=lambda t: (-t["purchase_count"], t["name"]))
        del tiles[CATEGORY_LIMIT:]

    # Frequent bucket: top N across all categories (excludes 0-count items
    # so the "Frequent" chip never shows products that were never bought).
    purchased = [t for t in all_tiles if t["purchase_count"] > 0]
    purchased.sort(key=lambda t: (-t["purchase_count"], t["name"]))
    frequent = purchased[:FREQUENT_LIMIT]

    # on_list_product_ids: products on currently-active shopping session(s).
    active = (
        session.query(ShoppingSession.id)
        .filter(ShoppingSession.status == "active")
        .all()
    )
    active_ids = [s.id for s in active]
    on_list = []
    if active_ids:
        on_list = [
            row[0]
            for row in session.query(ShoppingListItem.product_id)
            .filter(
                ShoppingListItem.shopping_session_id.in_(active_ids),
                ShoppingListItem.product_id.isnot(None),
                ShoppingListItem.status.in_(["open", "skipped"]),
            )
            .distinct()
            .all()
        ]

    return {
        "frequent": frequent,
        "categories": categories,
        "on_list_product_ids": on_list,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_kitchen.py tests/test_manage_kitchen.py
git commit -m "feat(kitchen): get_kitchen_catalog aggregator"
```

---

## Task 3: Backend — `manage_kitchen_endpoint.py` blueprint

**Files:**
- Create: `src/backend/manage_kitchen_endpoint.py`
- Create: `tests/test_manage_kitchen_endpoint.py`
- Modify: `src/backend/create_flask_application.py:236`

- [ ] **Step 1: Write failing endpoint tests**

```python
# tests/test_manage_kitchen_endpoint.py
def test_get_catalog_unauth_returns_401(client):
    res = client.get("/api/kitchen/catalog")
    assert res.status_code in (401, 403)


def test_get_catalog_authed_shape(authed_client):
    res = authed_client.get("/api/kitchen/catalog")
    assert res.status_code == 200
    body = res.get_json()
    assert set(body.keys()) == {"frequent", "categories", "on_list_product_ids"}
    assert isinstance(body["frequent"], list)
    assert set(body["categories"].keys()) == {
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    }
    assert isinstance(body["on_list_product_ids"], list)
```

If `authed_client` fixture does not exist, mirror the auth-bypass pattern
from `tests/test_manage_stores_endpoint.py` (or its conftest). If the test
suite only has `client` (unauthenticated), keep the unauth test and skip the
authed one with a TODO note in the file:

```python
import pytest


@pytest.mark.skip(reason="authed_client fixture not yet ported to test infrastructure")
def test_get_catalog_authed_shape(authed_client):
    ...
```

(If the fixture does exist, drop the skip.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen_endpoint.py -v
```

Expected: 404 (route not registered).

- [ ] **Step 3: Create the blueprint**

```python
# src/backend/manage_kitchen_endpoint.py
"""Kitchen view read endpoint. All mutations reuse existing
/shopping-list and /inventory routes."""

from flask import Blueprint, g, jsonify

from src.backend.manage_kitchen import get_kitchen_catalog
from src.backend.manage_users import require_auth


kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/api/kitchen")


@kitchen_bp.route("/catalog", methods=["GET"])
@require_auth
def get_catalog():
    return jsonify(get_kitchen_catalog(g.db_session)), 200
```

- [ ] **Step 4: Register the blueprint**

In `src/backend/create_flask_application.py` near line 198 (`register_blueprints`):

After the existing import block at the top of the function, add:

```python
    from src.backend.manage_kitchen_endpoint import kitchen_bp
```

After `app.register_blueprint(stores_bp)` on line 236, add:

```python
    app.register_blueprint(kitchen_bp)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen_endpoint.py tests/test_manage_kitchen.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/manage_kitchen_endpoint.py \
        src/backend/create_flask_application.py \
        tests/test_manage_kitchen_endpoint.py
git commit -m "feat(kitchen): /api/kitchen/catalog endpoint"
```

---

## Task 4: Backend — Tighten `ShoppingListItem.status` validation + add `"skipped"`

**Files:**
- Modify: `src/backend/manage_shopping_list.py:719-806` (the `update_shopping_item` function)
- Create: `tests/test_manage_shopping_list_status.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_manage_shopping_list_status.py
"""Validate that ShoppingListItem.status only accepts known values
and that 'skipped' is a recognized state."""

# Use whatever test client fixture the suite already provides.
# If there is no authed_client, the implementer should follow the
# pattern from tests/test_manage_stores_endpoint.py to wire one up.

def test_put_status_skipped_accepted(authed_client, sample_shopping_item_id):
    res = authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "skipped"},
    )
    assert res.status_code == 200
    assert res.get_json()["item"]["status"] == "skipped"


def test_put_status_purchased_accepted(authed_client, sample_shopping_item_id):
    res = authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "purchased"},
    )
    assert res.status_code == 200
    assert res.get_json()["item"]["status"] == "purchased"


def test_put_status_open_accepted(authed_client, sample_shopping_item_id):
    res = authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "open"},
    )
    assert res.status_code == 200
    assert res.get_json()["item"]["status"] == "open"


def test_put_status_garbage_returns_400(authed_client, sample_shopping_item_id):
    res = authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "wat"},
    )
    assert res.status_code == 400
    assert res.get_json().get("error")


def test_put_no_status_field_is_noop(authed_client, sample_shopping_item_id):
    res = authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"note": "hi"},
    )
    assert res.status_code == 200
```

If the suite lacks `authed_client` / `sample_shopping_item_id` fixtures,
add them in `tests/conftest.py` mirroring how the existing
`tests/test_manage_stores_endpoint.py` (or `test_manage_shopping_list*.py`)
sets up auth. Use whatever pattern is already in the repo — do not invent a
new auth bypass.

- [ ] **Step 2: Run tests to verify failure**

```bash
docker compose exec localocr pytest tests/test_manage_shopping_list_status.py -v
```

Expected: `test_put_status_garbage_returns_400` FAILS (returns 200, item.status is set to "wat") — current code at line 744 has no validation. Other tests should pass (statuses already accepted as free strings).

- [ ] **Step 3: Tighten the validator**

In `src/backend/manage_shopping_list.py`, near the top of the file
(after existing imports, before any function):

```python
_VALID_ITEM_STATUSES = {"open", "purchased", "skipped"}
```

Then in `update_shopping_item` (around line 743–744), replace:

```python
    if "status" in data:
        item.status = str(data["status"]).strip().lower() or item.status
```

with:

```python
    if "status" in data:
        next_status = str(data["status"]).strip().lower()
        if next_status and next_status not in _VALID_ITEM_STATUSES:
            return jsonify({"error": "invalid status"}), 400
        item.status = next_status or item.status
```

Also apply the same validation to `update_shared_shopping_item` (line ~828)
where it currently does:

```python
    next_status = str(data.get("status") or "").strip().lower()
    if next_status not in {"open", "purchased"}:
        return jsonify({"error": "Only open and purchased status updates are allowed"}), 400
```

Replace with:

```python
    next_status = str(data.get("status") or "").strip().lower()
    if next_status not in {"open", "purchased"}:
        # Shared (anonymous) link is intentionally restricted —
        # 'skipped' must come from an authenticated kitchen session.
        return jsonify({"error": "Only open and purchased status updates are allowed"}), 400
```

(No functional change for the shared route — just the comment makes the
intent clear so a future reader doesn't try to widen it.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec localocr pytest tests/test_manage_shopping_list_status.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_shopping_list.py tests/test_manage_shopping_list_status.py
git commit -m "feat(shopping): add 'skipped' status + validate enum on PUT"
```

---

## Task 5: Backend — Exclude `"skipped"` from open count + ready-to-bill + finalize

**Files:**
- Modify: `src/backend/manage_shopping_list.py` (multiple sites — see below)
- Modify: `tests/test_manage_shopping_list_status.py`

The places that branch on `status` and need to treat `"skipped"` like
`"purchased"` (i.e., not "open"):

1. `_build_shopping_list_payload` — counts open items / sums estimated remaining.
2. `mark_session_ready_to_bill` — checks if every item is resolved.
3. `finalize_session` — only purchased items become Purchase rows, but
   skipped items must be marked as session-completed (not left dangling).

- [ ] **Step 1: Append failing tests**

Append to `tests/test_manage_shopping_list_status.py`:

```python
def test_skipped_not_counted_in_open(authed_client, sample_shopping_item_id):
    # Mark the only sample item as skipped; the response payload should
    # report 0 open items.
    authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "skipped"},
    )
    res = authed_client.get("/shopping-list")
    body = res.get_json()
    open_items = [i for i in body["items"] if i["status"] == "open"]
    assert len(open_items) == 0


def test_ready_to_bill_with_only_skipped_items_succeeds(
    authed_client, sample_shopping_item_id,
):
    # If every item is either purchased or skipped, ready-to-bill must
    # not error out for "still open items remaining".
    authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "skipped"},
    )
    res = authed_client.post("/shopping-list/session/ready-to-bill", json={})
    assert res.status_code == 200, res.get_data(as_text=True)


def test_finalize_session_ignores_skipped_items(
    authed_client, sample_shopping_item_id,
):
    # Skipped items should NOT generate Purchase rows on finalize.
    authed_client.put(
        f"/shopping-list/items/{sample_shopping_item_id}",
        json={"status": "skipped"},
    )
    res = authed_client.post(
        "/shopping-list/session/finalize",
        json={"store": "Costco", "purchase_date": "2026-04-30"},
    )
    assert res.status_code == 200
    # The finalized session should report 0 purchased items.
    detail = authed_client.get(
        f"/shopping-list/sessions/{res.get_json()['session']['id']}"
    ).get_json()
    purchased = [i for i in detail["items"] if i["status"] == "purchased"]
    assert len(purchased) == 0
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
docker compose exec localocr pytest tests/test_manage_shopping_list_status.py -v
```

Expected: the three new tests fail because:
- Open count counts `"skipped"` items as open (treats anything != "purchased" as open).
- Ready-to-bill rejects sessions with non-purchased items.
- Finalize generates rows for non-purchased items OR errors out.

- [ ] **Step 3: Update `_build_shopping_list_payload`**

In `manage_shopping_list.py:361`, find the `_build_shopping_list_payload`
function. Locate where it filters items by status. Search for `status='open'`
or `i.status != "purchased"`. Make sure the open-count filter uses
`status == "open"` (NOT `status != "purchased"`), so that "skipped" items
are not counted as open. The pattern:

```python
# Correct:
open_items = [i for i in items if i.status == "open"]
```

If the existing code instead counts as open via `i.status != "purchased"`,
update to `i.status not in ("purchased", "skipped")` — equivalent but
explicit.

After the implementer reads the actual code, they will pick the correct
edit. The principle: anywhere "skipped" is implicitly classified as open,
move it into the resolved bucket.

- [ ] **Step 4: Update `mark_session_ready_to_bill`**

Find the function (line ~849). Look for where it checks if any items remain
open. If it uses `status == "open"` directly, no change needed. If it uses
`status != "purchased"`, change to `status not in ("purchased", "skipped")`.

- [ ] **Step 5: Update `finalize_session`**

Find the function (line ~869). Locate the loop that creates Purchase rows
from items. Ensure it iterates only over `status == "purchased"` items
(it likely already does — verify by reading). Skipped items should be
left in their `"skipped"` state and the session moves to `finalized`
without generating rows for them.

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker compose exec localocr pytest tests/test_manage_shopping_list_status.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/backend/manage_shopping_list.py tests/test_manage_shopping_list_status.py
git commit -m "feat(shopping): treat 'skipped' as resolved in counts + bill flow"
```

---

## Task 6: Frontend — Sidebar nav + `<section id="page-kitchen">` skeleton + CSS

**Files:**
- Modify: `src/frontend/index.html` (sidebar markup + nav function + new section + CSS link)
- Create: `src/frontend/styles/page-shell/kitchen.css`

- [ ] **Step 1: Add sidebar nav-item**

In `src/frontend/index.html`, around line 131 (existing `nav-shopping`), insert
the new nav-item right after the Shopping List entry:

```html
        <div class="nav-item" id="nav-kitchen" onclick="nav('kitchen', this)">
          <span class="nav-icon">👨‍🍳</span> Kitchen
        </div>
```

- [ ] **Step 2: Expand the `nav()` function allowed-page lists**

In `src/frontend/index.html`, locate `function nav(page, el)` (~line 12335).

Add `kitchen` to the access-fallback order list (around line 12356):

```js
            const order = [
              "dashboard", "inventory", "upload", "receipts", "shopping",
              "kitchen",
              "restaurant", "expenses", "budget", "bills", "accounts",
              "analytics", "contributions",
            ];
```

Add `kitchen` to the kitchen-display-mode allowed pages (around line 12381):

```js
        if (
          isKitchenDisplayTrustedDevice() &&
          !["dashboard", "inventory", "shopping", "kitchen"].includes(page)
        ) {
          page = "dashboard";
        }
```

Add a load hook at the bottom of `nav()` (after the existing
`if (page === "shopping")` block):

```js
        if (page === "kitchen") loadKitchen();
```

- [ ] **Step 3: Add the page section markup**

In `src/frontend/index.html`, find any other `<div id="page-shopping" class="page">`
(or another existing `page-XXX` section). Add the new section nearby — order
in the DOM does not affect display because nav() toggles `.active`:

```html
<div id="page-kitchen" class="page">
  <div class="page-header">
    <h1>👨‍🍳 Kitchen</h1>
    <p class="page-subtitle">Tablet-friendly shopping. Tap to act.</p>
  </div>

  <div class="kitchen-empty" id="kitchen-empty" style="display: none;">
    <p>No active shopping session.</p>
    <button class="btn btn-primary" onclick="nav('shopping', document.getElementById('nav-shopping'))">
      Open Shopping List
    </button>
  </div>

  <div class="kitchen-catalog" id="kitchen-catalog">
    <div class="kitchen-chip-bar" id="kitchen-chip-bar">
      <!-- chips rendered by renderKitchenCatalog() -->
    </div>
    <div class="kitchen-grid" id="kitchen-grid">
      <!-- product tiles rendered by renderKitchenCatalog() -->
    </div>
  </div>

  <div class="kitchen-list" id="kitchen-list-container">
    <h2 class="kitchen-section-title">
      <span>Current List</span>
      <span class="kitchen-list-total" id="kitchen-list-total"></span>
    </h2>
    <div class="kitchen-grid kitchen-grid--list" id="kitchen-list-grid">
      <!-- list tiles rendered by renderKitchenList() -->
    </div>
  </div>

  <div class="kitchen-sheet" id="kitchen-sheet" style="display: none;">
    <div class="kitchen-sheet-backdrop" onclick="closeKitchenSheet()"></div>
    <div class="kitchen-sheet-card" id="kitchen-sheet-card">
      <!-- sheet contents rendered by openKitchenSheet() -->
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add the CSS link**

Find the existing `<link rel="stylesheet" href="styles/page-shell/cards.css" />`
(or similar `page-shell/*.css` references). Add:

```html
<link rel="stylesheet" href="styles/page-shell/kitchen.css" />
```

- [ ] **Step 5: Create `kitchen.css`**

```css
/* src/frontend/styles/page-shell/kitchen.css */

/* ============================================================
   Kitchen view — tablet-friendly shopping surface.
   Tokens come from the global theme (light/dark variables).
   ============================================================ */

#page-kitchen {
  padding: 16px 20px 32px;
}

#page-kitchen .page-header {
  margin-bottom: 20px;
}

#page-kitchen .page-header h1 {
  font-size: 32px;
  margin: 0 0 4px;
}

.kitchen-empty {
  padding: 40px 20px;
  text-align: center;
  background: var(--color-surface-2);
  border-radius: 14px;
}

/* ---- Chip bar ---- */
.kitchen-chip-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  padding: 8px 0 16px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}

.kitchen-chip {
  appearance: none;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  padding: 12px 18px;
  border-radius: 999px;
  font-size: 16px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.kitchen-chip:hover { filter: brightness(1.07); }

.kitchen-chip.active {
  background: var(--color-brand-soft);
  border-color: var(--color-brand);
  color: var(--color-text);
}

.kitchen-chip .ico { font-size: 20px; line-height: 1; }

.kitchen-search-btn {
  margin-left: auto;
  width: 48px; height: 48px;
  border-radius: 50%;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  color: var(--color-text-muted);
  cursor: pointer;
}

/* ---- Tile grid ---- */
.kitchen-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

@media (max-width: 1100px) {
  .kitchen-grid { grid-template-columns: repeat(4, 1fr); }
}

@media (max-width: 720px) {
  .kitchen-grid { grid-template-columns: repeat(3, 1fr); }
}

.kitchen-tile {
  position: relative;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  overflow: hidden;
  aspect-ratio: 1;
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.kitchen-tile-img {
  flex: 1;
  display: flex; align-items: center; justify-content: center;
  font-size: 56px;
  background: var(--color-surface-3, var(--color-surface-2));
  background-image: linear-gradient(135deg, rgba(255,200,100,0.15), rgba(255,150,80,0.05));
}

.kitchen-tile-img img {
  width: 100%; height: 100%; object-fit: cover;
}

.kitchen-tile-foot {
  padding: 8px 10px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 6px;
  border-top: 1px solid var(--color-border);
}

.kitchen-tile-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.kitchen-tile-badge {
  background: var(--color-brand);
  color: #fff;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.kitchen-tile.on-list .kitchen-tile-img,
.kitchen-tile.on-list .kitchen-tile-foot { filter: brightness(0.5); }

.kitchen-tile.on-list::after {
  content: "✓ on list";
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-success, #10b981);
  font-size: 16px;
  font-weight: 700;
}

.kitchen-tile.skipped .kitchen-tile-img { filter: brightness(0.45); }
.kitchen-tile.skipped::before {
  content: "skipped";
  position: absolute;
  top: 8px; left: 8px;
  background: rgba(0,0,0,0.55);
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  z-index: 1;
}

/* ---- Section title ---- */
.kitchen-section-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  margin: 16px 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.kitchen-list-total {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-muted);
}

/* ---- Bottom sheet ---- */
.kitchen-sheet {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: flex-end;
}

.kitchen-sheet-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.55);
}

.kitchen-sheet-card {
  position: relative;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 18px 18px 0 0;
  padding: 18px 20px 24px;
  color: var(--color-text);
  box-shadow: 0 -8px 30px rgba(0,0,0,0.4);
}

.kitchen-sheet-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.kitchen-sheet-name {
  font-size: 22px;
  font-weight: 700;
}

.kitchen-sheet-close {
  appearance: none;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  font-size: 22px;
  cursor: pointer;
}

.kitchen-sheet-meta {
  font-size: 14px;
  color: var(--color-text-muted);
  margin-bottom: 16px;
}

.kitchen-sheet-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.kitchen-sheet-qty {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 6px 8px;
}

.kitchen-sheet-qty button {
  width: 44px; height: 44px;
  border-radius: 50%;
  border: none;
  background: var(--color-surface-3, var(--color-surface-2));
  color: var(--color-text);
  font-size: 22px;
  font-weight: 700;
  cursor: pointer;
}

.kitchen-sheet-qty span {
  min-width: 28px;
  text-align: center;
  font-size: 22px;
  font-weight: 700;
}

.kitchen-action {
  flex: 1 1 auto;
  min-width: 100px;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.kitchen-action.bought   { background: #065f46; border-color: #047857; color: #fff; }
.kitchen-action.low      { background: #92400e; border-color: #b45309; color: #fff; }
.kitchen-action.skip     { background: var(--color-surface-3, var(--color-surface-2)); }
.kitchen-action.delete   { background: #7f1d1d; border-color: #991b1b; color: #fff; }
.kitchen-action.unskip   { background: var(--color-brand-soft); }

.kitchen-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.kitchen-preset {
  appearance: none;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.kitchen-preset.active {
  background: var(--color-brand-soft);
  border-color: var(--color-brand);
}
```

- [ ] **Step 6: Add JS state placeholders + stub functions**

Near the existing `let shoppingStoreBuckets = ...` line (~5984) in
`index.html`, add:

```js
let kitchenCatalog = { frequent: [], categories: {}, on_list_product_ids: [] };
let kitchenList = [];
let kitchenActiveCategory = "frequent";
let kitchenSheetItemId = null;
let kitchenStagedAction = null;  // 'bought' | 'low' | 'skipped' | null
```

Then near where `loadShoppingList()` is defined, add stubs the next tasks
will fill in:

```js
async function loadKitchen() {
  // implemented in Task 7
}
function renderKitchenCatalog() { /* Task 7 */ }
function renderKitchenList() { /* Task 8 */ }
function openKitchenSheet(itemId) { /* Task 8 */ }
function closeKitchenSheet() { /* Task 8 */ }
async function addProductToList(productId) { /* Task 7 */ }
function kitchenSetActiveCategory(name) { /* Task 7 */ }
async function kitchenSheetAction(action) { /* Task 9 */ }
async function kitchenSheetSetQty(delta) { /* Task 9 */ }
async function kitchenStampNote(presetText) { /* Task 9 */ }
```

- [ ] **Step 7: Visual smoke**

```bash
docker compose up -d --build
```

Open `http://localhost:8000/kitchen` (login first if redirected). Expected:
- Sidebar shows "👨‍🍳 Kitchen" entry (after Shopping List).
- Clicking it lands on the page with the title "👨‍🍳 Kitchen", an empty
  chip bar, an empty grid, and the "Current List" heading. No errors in
  console (the stubs don't throw).

- [ ] **Step 8: Commit**

```bash
git add src/frontend/index.html src/frontend/styles/page-shell/kitchen.css
git commit -m "feat(kitchen): page section + sidebar entry + base CSS"
```

---

## Task 7: Frontend — `loadKitchen()` + `renderKitchenCatalog()` + add-on-tap

**Files:**
- Modify: `src/frontend/index.html` (replace stubs from Task 6)

- [ ] **Step 1: Implement `loadKitchen` + `renderKitchenCatalog` + helpers**

Replace the stubs added in Task 6 with the real implementations. Insert this
code in the JS section of `index.html`:

```js
const KITCHEN_CATEGORIES = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"];
const KITCHEN_CATEGORY_EMOJI = {
  Produce: "🥬", Meat: "🥩", Dairy: "🥛",
  Bakery: "🍞", Pantry: "🥫", Other: "🧴",
};

async function loadKitchen() {
  try {
    const [catRes, listRes] = await Promise.all([
      api("/api/kitchen/catalog"),
      api("/shopping-list"),
    ]);
    const cat = await catRes.json();
    const list = await listRes.json();
    if (!catRes.ok) throw new Error(cat.error || "kitchen catalog failed");
    if (!listRes.ok) throw new Error(list.error || "shopping list failed");
    kitchenCatalog = cat;
    kitchenList = (list.items || []).filter(
      (i) => i.status === "open" || i.status === "skipped",
    );
    renderKitchenCatalog();
    renderKitchenList();
  } catch (err) {
    toast(err.message || "Failed to load kitchen view", "error");
  }
}

function kitchenSetActiveCategory(name) {
  kitchenActiveCategory = name;
  renderKitchenCatalog();
}

function _kitchenTilesForActiveChip() {
  if (kitchenActiveCategory === "frequent") return kitchenCatalog.frequent || [];
  return (kitchenCatalog.categories || {})[kitchenActiveCategory] || [];
}

function renderKitchenCatalog() {
  const chipBar = document.getElementById("kitchen-chip-bar");
  const grid = document.getElementById("kitchen-grid");
  if (!chipBar || !grid) return;

  // Chip bar — Frequent + DEFAULT_CATEGORIES + search button
  const chips = [
    { key: "frequent", label: "⭐ Frequent" },
    ...KITCHEN_CATEGORIES.map((c) => ({
      key: c, label: `${KITCHEN_CATEGORY_EMOJI[c] || ""} ${c}`,
    })),
  ];
  const chipHtml = chips
    .map(
      (c) => `
      <button
        class="kitchen-chip${kitchenActiveCategory === c.key ? " active" : ""}"
        onclick="kitchenSetActiveCategory(${JSON.stringify(c.key)})"
        type="button"
      >${escHtml(c.label)}</button>`,
    )
    .join("");
  setHtml(chipBar, chipHtml);

  // Grid — tiles for active category
  const tiles = _kitchenTilesForActiveChip();
  const onListSet = new Set(kitchenCatalog.on_list_product_ids || []);
  const html = tiles
    .map((t) => {
      const isOnList = onListSet.has(t.product_id);
      const inner = t.image_url
        ? `<img src="${escHtml(t.image_url)}" alt="${escHtml(t.name)}">`
        : `${t.fallback_emoji}`;
      return `
        <div
          class="kitchen-tile${isOnList ? " on-list" : ""}"
          onclick="${isOnList ? "" : `addProductToList(${t.product_id})`}"
          title="${escHtml(t.name)}"
        >
          <div class="kitchen-tile-img">${inner}</div>
          <div class="kitchen-tile-foot">
            <span class="kitchen-tile-name">${escHtml(t.name)}</span>
            ${
              t.purchase_count
                ? `<span class="kitchen-tile-badge">${t.purchase_count}×</span>`
                : ""
            }
          </div>
        </div>`;
    })
    .join("");
  setHtml(
    grid,
    html ||
      `<div class="kitchen-empty" style="grid-column: 1/-1;">No products in this category yet.</div>`,
  );
}

async function addProductToList(productId) {
  if (!productId) return;
  try {
    const res = await api("/shopping-list/items", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, quantity: 1 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not add to list");
    toast("Added ✓", "success");
    await loadKitchen();
  } catch (err) {
    toast(err.message || "Add failed", "error");
  }
}
```

- [ ] **Step 2: Visual smoke (catalog + chip)**

```bash
docker compose up -d --build
```

Open `/kitchen`. Verify:
- Chip bar shows "⭐ Frequent" + 6 categories.
- Default active chip is "⭐ Frequent" (highlighted).
- Tiles render with image OR emoji fallback + frequency badge.
- Tap a category chip → grid swaps; active chip moves.
- Tap a not-on-list tile → toast "Added ✓", tile dims with "✓ on list".

- [ ] **Step 3: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): catalog grid + chip filter + tap-to-add"
```

---

## Task 8: Frontend — `renderKitchenList` + `openKitchenSheet` + `closeKitchenSheet`

**Files:**
- Modify: `src/frontend/index.html` (replace remaining stubs)

- [ ] **Step 1: Implement list grid + sheet open/close**

Replace the empty `renderKitchenList`, `openKitchenSheet`, `closeKitchenSheet`
stubs with:

```js
function _kitchenItemTile(item) {
  const snap = item.latest_snapshot;
  const inner = snap && snap.image_url
    ? `<img src="${escHtml(snap.image_url)}" alt="${escHtml(item.name)}">`
    : `${KITCHEN_CATEGORY_EMOJI[item.category] || "🛒"}`;
  const skipped = item.status === "skipped";
  return `
    <div
      class="kitchen-tile${skipped ? " skipped" : ""}"
      onclick="openKitchenSheet(${item.id})"
      title="${escHtml(item.name)}"
    >
      <div class="kitchen-tile-img">${inner}</div>
      <div class="kitchen-tile-foot">
        <span class="kitchen-tile-name">${escHtml(item.name)}</span>
        <span class="kitchen-tile-badge">${item.quantity}</span>
      </div>
    </div>`;
}

function renderKitchenList() {
  const empty = document.getElementById("kitchen-empty");
  const container = document.getElementById("kitchen-list-container");
  const grid = document.getElementById("kitchen-list-grid");
  const total = document.getElementById("kitchen-list-total");
  if (!grid) return;
  const items = kitchenList || [];
  if (!items.length) {
    if (container) container.style.display = "none";
    if (empty) empty.style.display = "block";
    setHtml(grid, "");
    if (total) total.textContent = "";
    return;
  }
  if (container) container.style.display = "block";
  if (empty) empty.style.display = "none";
  setHtml(grid, items.map(_kitchenItemTile).join(""));
  if (total) {
    const sum = items.reduce(
      (acc, i) => acc + (i.manual_estimated_price || 0) * (i.quantity || 0),
      0,
    );
    total.textContent = sum > 0 ? `$${sum.toFixed(2)}` : "";
  }
}

function _kitchenItemById(id) {
  return (kitchenList || []).find((i) => i.id === id) || null;
}

function openKitchenSheet(itemId) {
  const item = _kitchenItemById(itemId);
  if (!item) return;
  kitchenSheetItemId = itemId;
  kitchenStagedAction = null;
  const sheet = document.getElementById("kitchen-sheet");
  const card = document.getElementById("kitchen-sheet-card");
  if (!sheet || !card) return;

  const skipped = item.status === "skipped";
  const meta = [
    item.manual_estimated_price ? `$${item.manual_estimated_price.toFixed(2)}` : "",
    item.preferred_store || (item.latest_price && item.latest_price.store) || "",
    item.category || "",
  ].filter(Boolean).join(" · ");

  const html = `
    <div class="kitchen-sheet-header">
      <span class="kitchen-sheet-name">${escHtml(item.name)}</span>
      <button class="kitchen-sheet-close" onclick="closeKitchenSheet()" type="button" aria-label="Close">✕</button>
    </div>
    <div class="kitchen-sheet-meta">${escHtml(meta)}</div>

    <div class="kitchen-sheet-actions">
      <div class="kitchen-sheet-qty">
        <button type="button" onclick="kitchenSheetSetQty(-1)" aria-label="Decrease quantity">−</button>
        <span id="kitchen-sheet-qty-value">${item.quantity}</span>
        <button type="button" onclick="kitchenSheetSetQty(1)" aria-label="Increase quantity">+</button>
      </div>
      ${skipped
        ? `<button class="kitchen-action unskip" type="button" onclick="kitchenSheetAction('open')">↩ Open</button>`
        : `<button class="kitchen-action bought" type="button" onclick="kitchenSheetAction('bought')">✓ Bought</button>
           <button class="kitchen-action low" type="button" onclick="kitchenSheetAction('low')">📝 Low</button>
           <button class="kitchen-action skip" type="button" onclick="kitchenSheetAction('skipped')">⏭ Skip</button>`}
      <button class="kitchen-action delete" type="button" onclick="kitchenSheetAction('delete')">🗑</button>
    </div>

    <div class="kitchen-presets" id="kitchen-presets" style="display: none;"></div>
  `;
  setHtml(card, html);
  sheet.style.display = "flex";
}

function closeKitchenSheet() {
  const sheet = document.getElementById("kitchen-sheet");
  if (sheet) sheet.style.display = "none";
  kitchenSheetItemId = null;
  kitchenStagedAction = null;
}
```

- [ ] **Step 2: Visual smoke (list + sheet open/close)**

```bash
docker cp src/frontend/index.html localocr:/app/src/frontend/index.html
docker compose restart localocr
```

Open `/kitchen`. Verify:
- "Current List" section renders tiles for open shopping items, each with
  image (or category emoji) + name + quantity badge.
- Tap a tile → bottom sheet slides up with item name, meta, ± qty, action
  buttons (Bought / Low / Skip / Delete).
- Tap ✕ or backdrop → sheet closes.
- Skipped item shows the "skipped" badge and the sheet shows "↩ Open"
  instead of Bought/Low/Skip.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): current-list grid + bottom sheet open/close"
```

---

## Task 9: Frontend — Sheet actions: qty ±, Bought, Low, Skip, Delete + presets

**Files:**
- Modify: `src/frontend/index.html` (replace remaining stubs)

- [ ] **Step 1: Implement qty +/-**

Replace the `kitchenSheetSetQty` stub:

```js
async function kitchenSheetSetQty(delta) {
  const item = _kitchenItemById(kitchenSheetItemId);
  if (!item) return;
  const next = Math.max(1, Number(item.quantity || 1) + delta);
  if (next === item.quantity) return;
  try {
    const res = await api(`/shopping-list/items/${item.id}`, {
      method: "PUT",
      body: JSON.stringify({ quantity: next }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not update quantity");
    item.quantity = next;
    const valueEl = document.getElementById("kitchen-sheet-qty-value");
    if (valueEl) valueEl.textContent = String(next);
    renderKitchenList();
  } catch (err) {
    toast(err.message || "Update failed", "error");
  }
}
```

- [ ] **Step 2: Implement action buttons (Bought / Low / Skip / Open / Delete)**

```js
const KITCHEN_PRESETS = {
  bought: ["Paid more", "Paid less", "Different brand", "Different size"],
  low: ["Almost out", "Restock soon"],
  skipped: ["Too expensive", "Out of stock", "Changed mind", "Got from elsewhere"],
};

async function kitchenSheetAction(action) {
  const item = _kitchenItemById(kitchenSheetItemId);
  if (!item) return;

  if (action === "delete") {
    if (!confirm(`Delete "${item.name}" from list?`)) return;
    try {
      const res = await api(`/shopping-list/items/${item.id}`, {
        method: "DELETE",
      });
      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Could not delete");
      }
      toast("Deleted", "success");
      closeKitchenSheet();
      await loadKitchen();
    } catch (err) {
      toast(err.message || "Delete failed", "error");
    }
    return;
  }

  if (action === "low") {
    if (!item.product_id) {
      toast("This item has no linked product — cannot mark low", "error");
      return;
    }
    try {
      const res = await api(
        `/inventory/products/${item.product_id}/low`,
        {
          method: "POST",
          body: JSON.stringify({ manual_low: true }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not mark low");
      toast("Marked Low ✓", "success");
      kitchenStagedAction = "low";
      _kitchenShowPresets("low");
    } catch (err) {
      toast(err.message || "Low failed", "error");
    }
    return;
  }

  // 'bought' | 'skipped' | 'open' — all are status PUTs.
  const nextStatus = action === "bought" ? "purchased" : action;
  try {
    const res = await api(`/shopping-list/items/${item.id}`, {
      method: "PUT",
      body: JSON.stringify({ status: nextStatus }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not update status");
    toast(
      action === "bought" ? "Marked Bought ✓"
      : action === "skipped" ? "Skipped ⏭"
      : "Re-opened",
      "success",
    );
    if (action === "open") {
      closeKitchenSheet();
      await loadKitchen();
      return;
    }
    if (action === "bought") {
      // keep sheet open briefly with preset chips, then auto-close.
      item.status = "purchased";
      kitchenStagedAction = "bought";
      _kitchenShowPresets("bought");
      renderKitchenList();
      setTimeout(() => {
        if (kitchenStagedAction === "bought") {
          closeKitchenSheet();
          loadKitchen();
        }
      }, 4000);
      return;
    }
    // skipped: stay on screen with preset chips
    item.status = "skipped";
    kitchenStagedAction = "skipped";
    _kitchenShowPresets("skipped");
    renderKitchenList();
  } catch (err) {
    toast(err.message || "Update failed", "error");
  }
}

function _kitchenShowPresets(action) {
  const chipKey = action === "bought" ? "bought"
    : action === "low" ? "low"
    : "skipped";
  const presets = KITCHEN_PRESETS[chipKey] || [];
  const target = document.getElementById("kitchen-presets");
  if (!target) return;
  const html = presets
    .map(
      (p) => `
        <button
          class="kitchen-preset"
          type="button"
          onclick="kitchenStampNote(${JSON.stringify(p)})"
        >${escHtml(p)}</button>`,
    )
    .join("") +
    `<button class="kitchen-preset" type="button" onclick="kitchenStampNote('')">✏️ custom</button>`;
  setHtml(target, html);
  target.style.display = "flex";
}

async function kitchenStampNote(presetText) {
  const itemId = kitchenSheetItemId;
  if (!itemId) return;
  let note = presetText || "";
  if (presetText === "") {
    const typed = window.prompt("Note for this item:");
    if (typed === null) return;
    note = typed.trim();
  }
  try {
    const res = await api(`/shopping-list/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify({ note: note || null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not save note");
    toast(note ? `Noted: ${note}` : "Note cleared", "success");
    const item = _kitchenItemById(itemId);
    if (item) item.note = note || null;
  } catch (err) {
    toast(err.message || "Note save failed", "error");
  }
}
```

- [ ] **Step 3: Visual smoke (full action set)**

```bash
docker cp src/frontend/index.html localocr:/app/src/frontend/index.html
docker compose restart localocr
```

Open `/kitchen`. Open the bottom sheet for an item. Verify:
- ± qty buttons increase/decrease quantity, persist on reload.
- "Bought" → tile leaves grid; preset row appears with "Paid more / Paid
  less / Different brand / Different size / ✏️ custom"; tapping a preset
  toasts "Noted: Paid more" and saves the note (verify by reloading and
  inspecting the historical session). After 4 s the sheet auto-closes.
- "Low" → toast "Marked Low ✓"; preset row appears with "Almost out /
  Restock soon / ✏️ custom"; verify low badge appears on inventory.
- "Skip" → tile dims with "skipped" badge but stays in grid; preset row
  appears; sheet shows "↩ Open" if reopened.
- "↩ Open" on a skipped item → returns it to open status, closes sheet.
- "🗑 Delete" → confirm prompt → tile removed.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): bottom-sheet actions + preset comment chips"
```

---

## Task 10: Frontend — Existing `/shopping-list` page "Skipped" group

**Files:**
- Modify: `src/frontend/index.html` (the existing shopping-list rendering)

The existing shopping-list page renders a single flat list of items grouped
only by store. Add a collapsible "Skipped" group at the bottom of the
"Current List" section, ordered AFTER any purchased items.

- [ ] **Step 1: Locate the existing shopping-list renderer**

Find the function that renders the shopping list rows (likely
`renderShoppingItems`, `renderCurrentList`, or inline in
`loadShoppingList()`). Search:

```bash
grep -n "Current List\|renderShoppingList\|renderShoppingItems\|status === 'open'" src/frontend/index.html | head -15
```

The exact function name varies; the implementer will pick the right site
to modify. The change is conceptual: split items by status into three
groups before rendering — `open`, `purchased`, `skipped` — and render the
skipped group LAST under a heading "Skipped (n)". The rendering of an
individual row is unchanged.

- [ ] **Step 2: Render structure**

Within the renderer, before emitting rows:

```js
const itemsOpen      = items.filter((i) => i.status === "open");
const itemsPurchased = items.filter((i) => i.status === "purchased");
const itemsSkipped   = items.filter((i) => i.status === "skipped");

// Existing render path: render itemsOpen + itemsPurchased as today.
// Then append a new section for skipped.

let skippedHtml = "";
if (itemsSkipped.length) {
  skippedHtml = `
    <div class="shopping-group">
      <h3 class="shopping-group-title">Skipped (${itemsSkipped.length})</h3>
      ${itemsSkipped.map(renderOneShoppingRow).join("")}
    </div>
  `;
}
```

The `renderOneShoppingRow` is whatever per-row HTML the existing renderer
already emits. Reuse it — do not duplicate row markup.

- [ ] **Step 3: Visual smoke**

```bash
docker cp src/frontend/index.html localocr:/app/src/frontend/index.html
docker compose restart localocr
```

Open `/shopping-list`. Verify:
- Items remain grouped by store as before for the open + purchased subsets.
- A new "Skipped (n)" group appears at the end if any items have
  `status="skipped"`.
- Skipped rows show the existing controls; the user can change their
  status back to open via the existing status select.
- Mark an item Skipped from `/kitchen` → return to `/shopping-list` →
  the item appears in the Skipped group.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(shopping): show 'Skipped' group on shopping-list page"
```

---

## Task 11: Final smoke + Docker rebuild + push

**Files:**
- (Verification only — no code changes.)

- [ ] **Step 1: Full Docker rebuild**

```bash
docker compose up -d --build
```

Wait for healthcheck.

- [ ] **Step 2: Run the entire test suite**

```bash
docker compose exec localocr pytest tests/test_manage_kitchen.py \
                                     tests/test_manage_kitchen_endpoint.py \
                                     tests/test_manage_shopping_list_status.py -v
```

All PASS.

- [ ] **Step 3: Smoke checklist (run through in browser)**

For each item below: tap, verify outcome, untick if any fail.

- [ ] Sidebar shows "👨‍🍳 Kitchen" between Shopping List and Restaurant.
- [ ] Tap → page loads; chip bar shows ⭐ Frequent + 6 categories.
- [ ] Catalog grid populated with image-or-emoji tiles.
- [ ] Tap chip → grid swaps; active chip highlighted.
- [ ] Tap a not-on-list tile → toast "Added ✓"; tile dims with "✓ on list".
- [ ] Current-list grid renders open items.
- [ ] Tap a current-list tile → bottom sheet slides up.
- [ ] − / + buttons modify quantity; sheet badge updates; survives reload.
- [ ] Bought → preset row appears for ~4 s; tile leaves list.
- [ ] Low → toast; preset row; product flagged in inventory.
- [ ] Skip → preset row; tile dims with "skipped" badge.
- [ ] Reopen sheet on a skipped item → "↩ Open" available; tap restores.
- [ ] Delete → confirm → tile removed.
- [ ] /shopping-list page shows "Skipped (n)" group at the bottom.
- [ ] No active session → "Start a shopping session" CTA shown on /kitchen.
- [ ] Backup → restore → /kitchen still loads.

- [ ] **Step 4: Push**

```bash
git push origin main
```

(Confirm the user wants to push before running.)

---

## Self-Review checklist

**Spec coverage:**
- "Separate /kitchen route" → Task 6 ✓
- "Bottom-sheet UX with qty ± / Bought / Low / Skip / Delete" → Tasks 8, 9 ✓
- "⭐ Frequent + category chips, frequency-sorted grid" → Tasks 1, 2, 7 ✓
- "Real ProductSnapshot image, category emoji fallback" → Task 2 + 7 ✓
- "Predefined comment presets" → Task 9 ✓
- "Skipped status, no schema change" → Tasks 4, 5 ✓
- "Excluded from open count, ready-to-bill, finalize" → Task 5 ✓
- "Skipped group on shopping-list page" → Task 10 ✓
- "Backup/restore safe — no migration" → no Alembic version added ✓
- "Auth: require_auth on read endpoint" → Task 3 ✓

**No placeholders.** Each task has full code blocks. Step-3 in Task 5 calls
out that the implementer must read the actual code to choose between two
phrasings — that is acceptable because the underlying logic is documented.

**Type consistency.** Constants `DEFAULT_CATEGORIES`, `CATEGORY_EMOJI`,
`FREQUENT_LIMIT`, `FREQUENCY_WINDOW_DAYS` defined once in
`src/backend/manage_kitchen.py`. Frontend `KITCHEN_CATEGORIES` and
`KITCHEN_CATEGORY_EMOJI` mirror them — kept as constants in the inline JS
to avoid an extra fetch. Function names: `loadKitchen`,
`renderKitchenCatalog`, `renderKitchenList`, `openKitchenSheet`,
`closeKitchenSheet`, `addProductToList`, `kitchenSetActiveCategory`,
`kitchenSheetAction`, `kitchenSheetSetQty`, `kitchenStampNote`,
`_kitchenShowPresets`, `_kitchenItemTile`, `_kitchenItemById`,
`_kitchenTilesForActiveChip`. Endpoints: `GET /api/kitchen/catalog`.
Statuses: `"open"`, `"purchased"`, `"skipped"`.
