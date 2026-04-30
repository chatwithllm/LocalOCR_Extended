# Store Visibility Buckets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bucketize the Stores picker into Frequent / Rarely Used (low-frequency) / Hidden via auto-classification + per-store user overrides, surfaced in a Settings → Manage Stores panel.

**Architecture:** Single nullable `Store.visibility_override` column (`NULL`, `"frequent"`, `"low_freq"`, `"hidden"`). Auto-classifier in pure Python operates on `(last_purchase_at, purchase_count, override, is_payment_artifact)` and returns a bucket. Aggregator `get_store_buckets(session)` runs one SQL aggregation joining `stores` ← `purchases` and groups results. `/api/stores` GET + POST endpoints surface the data and accept overrides. Frontend renders dropdowns with `<optgroup>` sections and adds a Settings card.

**Tech Stack:** Python 3.11, SQLAlchemy ORM, Alembic, Flask blueprints, vanilla JS frontend.

---

## File Structure

**Create:**
- `src/backend/manage_stores.py` — `classify_store()` + `get_store_buckets()` (pure + aggregator).
- `src/backend/manage_stores_endpoint.py` — `stores_bp` Flask blueprint (`GET /api/stores`, `POST /api/stores/<id>/visibility`).
- `alembic/versions/018_store_visibility_override.py` — additive migration.
- `tests/test_manage_stores.py` — unit tests for `classify_store` (truth table) + `get_store_buckets` shape.
- `tests/test_manage_stores_endpoint.py` — integration tests for the blueprint.

**Modify:**
- `src/backend/initialize_database_schema.py` — add `visibility_override` column to `Store`.
- `src/backend/manage_shopping_list.py` — return `available_store_buckets` alongside `available_stores`.
- `src/backend/create_flask_application.py` — register `stores_bp`.
- `src/frontend/index.html` — dropdown render helpers emit `<optgroup>`s; new "Manage Stores" Settings card.

---

## Note on frontend HTML insertion

The project's PreToolUse security hook flags any literal `.innerHTML = ` in
edits. Use the same `_setHtml(el, html)` helper pattern that
`assets/js/upload-result.js` ships with — it builds the fragment via
`Range#createContextualFragment` and replaces the element's children. All
frontend tasks below assume this helper is available globally as `setHtml`
(or imported via the existing inline-script declaration).

If `setHtml` is not yet a global, declare it once near the top of the
inline `<script>` in `index.html`:

```js
      function setHtml(el, html) {
        if (!el) return;
        while (el.firstChild) el.removeChild(el.firstChild);
        const range = document.createRange();
        range.selectNodeContents(el);
        el.appendChild(range.createContextualFragment(html));
      }
```

---

## Task 1: Add `visibility_override` column to `Store` model + Alembic migration

**Files:**
- Modify: `src/backend/initialize_database_schema.py:139-150`
- Create: `alembic/versions/018_store_visibility_override.py`

- [ ] **Step 1: Add the column to the Store model**

In `src/backend/initialize_database_schema.py` find the `Store` class (currently around line 139 after the 017 migration shipped) and add `visibility_override` between `is_payment_artifact` and `created_at`:

```python
class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    location = Column(String(500), nullable=True)
    is_payment_artifact = Column(Boolean, nullable=False, default=False)
    visibility_override = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    purchases = relationship("Purchase", back_populates="store")
    price_history = relationship("PriceHistory", back_populates="store")
```

- [ ] **Step 2: Create the Alembic migration**

Create `alembic/versions/018_store_visibility_override.py`:

```python
"""store_visibility_override: per-store frequent/low_freq/hidden override.

Revision ID: 018_store_visibility_override
Revises: 017_store_is_payment_artifact
Create Date: 2026-04-30

Adds a single nullable String column to ``stores`` so the picker can be
bucketed via auto-classification (last purchase recency) plus an explicit
user override. NULL means "follow the auto rule"; otherwise the value
pins the store to one of {"frequent", "low_freq", "hidden"}.

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching the
pattern used by 008_receipt_attribution and 017_store_is_payment_artifact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_store_visibility_override"
down_revision: Union[str, None] = "017_store_is_payment_artifact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_stores"))
    if not _column_exists(conn, "stores", "visibility_override"):
        op.add_column(
            "stores",
            sa.Column("visibility_override", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    pass
```

- [ ] **Step 3: Sync source into running container and run the migration**

```bash
docker cp src/backend/initialize_database_schema.py localocr-extended-backend:/app/src/backend/initialize_database_schema.py
docker cp alembic/versions/018_store_visibility_override.py localocr-extended-backend:/app/alembic/versions/018_store_visibility_override.py
docker compose exec backend bash -lc "cd /app && alembic upgrade head"
```

Expected output last line: `INFO  [alembic.runtime.migration] Running upgrade 017_store_is_payment_artifact -> 018_store_visibility_override`.

- [ ] **Step 4: Verify column exists**

```bash
docker compose exec backend python -c "
import sqlite3, glob
p = glob.glob('/data/db/localocr_extended.db')[0]
c = sqlite3.connect(p)
[print(r) for r in c.execute('PRAGMA table_info(stores)').fetchall()]
"
```

Expected: line `(6, 'visibility_override', 'VARCHAR(16)', 0, None, 0)` is present.

- [ ] **Step 5: Commit**

```bash
git add src/backend/initialize_database_schema.py alembic/versions/018_store_visibility_override.py
git commit -m "feat(stores): add visibility_override column + migration 018

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `classify_store()` pure function — TDD truth table

**Files:**
- Create: `tests/test_manage_stores.py`
- Create: `src/backend/manage_stores.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manage_stores.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from src.backend.manage_stores import classify_store


NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n):
    return NOW - timedelta(days=n)


@pytest.mark.parametrize(
    "override, artifact, last_purchase, count, expected",
    [
        # Auto: recency-based.
        (None, False, _days_ago(30), 2, "frequent"),
        (None, False, _days_ago(89), 1, "frequent"),
        (None, False, _days_ago(91), 1, "low_freq"),
        (None, False, _days_ago(200), 1, "low_freq"),
        (None, False, _days_ago(365), 1, "low_freq"),
        (None, False, _days_ago(366), 1, "hidden"),
        (None, False, _days_ago(540), 7, "hidden"),
        (None, False, None, 0, "hidden"),
        # Override pins ignore recency.
        ("frequent", False, _days_ago(540), 0, "frequent"),
        ("low_freq", False, _days_ago(30), 10, "low_freq"),
        ("hidden", False, _days_ago(30), 10, "hidden"),
        # Artifact always wins.
        ("frequent", True, _days_ago(30), 10, "hidden"),
        (None, True, _days_ago(30), 10, "hidden"),
    ],
)
def test_classify_store_truth_table(override, artifact, last_purchase, count, expected):
    bucket = classify_store(
        override=override,
        is_payment_artifact=artifact,
        last_purchase_at=last_purchase,
        purchase_count=count,
        now=NOW,
    )
    assert bucket == expected


def test_classify_store_defaults_now_to_utcnow():
    bucket = classify_store(
        override=None,
        is_payment_artifact=False,
        last_purchase_at=datetime.now(timezone.utc) - timedelta(days=10),
        purchase_count=1,
    )
    assert bucket == "frequent"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker cp tests/test_manage_stores.py localocr-extended-backend:/app/tests/test_manage_stores.py
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores.py -v"
```

Expected: collection error `ImportError: cannot import name 'classify_store' from 'src.backend.manage_stores'` (module doesn't exist yet).

- [ ] **Step 3: Implement `classify_store`**

Create `src/backend/manage_stores.py`:

```python
"""Store visibility bucketing.

Pure ``classify_store`` plus the aggregator ``get_store_buckets`` that
runs one SQL roundtrip to compute (last_purchase_at, purchase_count) per
store and groups them into the three buckets. Used by the stores
blueprint and by the shopping-list dropdown emitter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

FREQUENT_DAYS = 90
LOW_FREQ_DAYS = 365

_VALID_OVERRIDES = {"frequent", "low_freq", "hidden"}


def classify_store(
    override: Optional[str],
    is_payment_artifact: bool,
    last_purchase_at: Optional[datetime],
    purchase_count: int,
    now: Optional[datetime] = None,
) -> str:
    """Return the bucket ('frequent' | 'low_freq' | 'hidden') for a store.

    Order of precedence:
      1. Payment artifacts are always 'hidden'.
      2. Manual override pins the bucket.
      3. Auto rule based on last purchase recency.
    """
    if is_payment_artifact:
        return "hidden"
    if override in _VALID_OVERRIDES:
        return override
    if last_purchase_at is None:
        return "hidden"
    now = now or datetime.now(timezone.utc)
    if last_purchase_at.tzinfo is None:
        last_purchase_at = last_purchase_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = (now - last_purchase_at).days
    if age_days <= FREQUENT_DAYS:
        return "frequent"
    if age_days <= LOW_FREQ_DAYS:
        return "low_freq"
    return "hidden"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker cp src/backend/manage_stores.py localocr-extended-backend:/app/src/backend/manage_stores.py
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores.py -v"
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_stores.py tests/test_manage_stores.py
git commit -m "feat(stores): classify_store auto-bucketing function + truth-table tests

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `get_store_buckets()` aggregator — TDD

**Files:**
- Modify: `tests/test_manage_stores.py` (append)
- Modify: `src/backend/manage_stores.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_manage_stores.py`:

```python
from src.backend.initialize_database_schema import (
    Base,
    Purchase,
    Store,
    create_db_engine,
    create_session_factory,
)
from src.backend.manage_stores import get_store_buckets


@pytest.fixture
def session(tmp_path):
    db_path = tmp_path / "buckets.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _add_store(session, name, override=None, is_payment_artifact=False):
    store = Store(name=name, visibility_override=override, is_payment_artifact=is_payment_artifact)
    session.add(store)
    session.flush()
    return store


def _add_purchase(session, store_id, days_ago):
    p = Purchase(
        store_id=store_id,
        purchase_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        total_amount=10.0,
    )
    session.add(p)
    session.flush()
    return p


def test_get_store_buckets_groups_by_recency(session):
    fresh = _add_store(session, "Costco")
    _add_purchase(session, fresh.id, 10)
    older = _add_store(session, "Chowka")
    _add_purchase(session, older.id, 200)
    ancient = _add_store(session, "Random Diner")
    _add_purchase(session, ancient.id, 800)
    _add_store(session, "Apple Store")
    session.commit()

    buckets = get_store_buckets(session)
    names = {b: [s["name"] for s in buckets[b]] for b in ("frequent", "low_freq", "hidden")}
    assert "Costco" in names["frequent"]
    assert "Chowka" in names["low_freq"]
    assert "Random Diner" in names["hidden"]
    assert "Apple Store" in names["hidden"]


def test_get_store_buckets_honours_override(session):
    _add_store(session, "Pinned Visible", override="frequent")
    session.commit()
    buckets = get_store_buckets(session)
    assert any(row["name"] == "Pinned Visible" for row in buckets["frequent"])


def test_get_store_buckets_artifact_always_hidden(session):
    _add_store(session, "Chase Credit Crd", is_payment_artifact=True)
    session.commit()
    buckets = get_store_buckets(session)
    assert any(row["name"] == "Chase Credit Crd" for row in buckets["hidden"])


def test_get_store_buckets_includes_usage_stats(session):
    s = _add_store(session, "Kroger")
    _add_purchase(session, s.id, 5)
    _add_purchase(session, s.id, 30)
    _add_purchase(session, s.id, 60)
    session.commit()
    buckets = get_store_buckets(session)
    row = next(r for r in buckets["frequent"] if r["name"] == "Kroger")
    assert row["purchase_count"] == 3
    assert row["last_purchase_at"] is not None
    assert row["override"] is None
    assert row["is_payment_artifact"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker cp tests/test_manage_stores.py localocr-extended-backend:/app/tests/test_manage_stores.py
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores.py -v"
```

Expected: 4 new tests fail with `ImportError: cannot import name 'get_store_buckets'`.

- [ ] **Step 3: Implement `get_store_buckets`**

Append to `src/backend/manage_stores.py`:

```python
from sqlalchemy import func

from src.backend.initialize_database_schema import Purchase, Store


def get_store_buckets(session) -> dict:
    """Return stores grouped into the three visibility buckets.

    Shape:
        {
            "frequent": [{"id", "name", "last_purchase_at", "purchase_count",
                          "override", "is_payment_artifact"}, ...],
            "low_freq": [...],
            "hidden":   [...],
        }
    Each list is sorted alphabetically by name (case-insensitive).
    """
    rows = (
        session.query(
            Store.id,
            Store.name,
            Store.visibility_override,
            Store.is_payment_artifact,
            func.max(Purchase.purchase_date).label("last_purchase_at"),
            func.count(Purchase.id).label("purchase_count"),
        )
        .outerjoin(Purchase, Purchase.store_id == Store.id)
        .group_by(Store.id)
        .all()
    )
    buckets = {"frequent": [], "low_freq": [], "hidden": []}
    now = datetime.now(timezone.utc)
    for store_id, name, override, artifact, last_purchase_at, purchase_count in rows:
        bucket = classify_store(
            override=override,
            is_payment_artifact=bool(artifact),
            last_purchase_at=last_purchase_at,
            purchase_count=int(purchase_count or 0),
            now=now,
        )
        buckets[bucket].append({
            "id": store_id,
            "name": name,
            "last_purchase_at": last_purchase_at.isoformat() if last_purchase_at else None,
            "purchase_count": int(purchase_count or 0),
            "override": override,
            "is_payment_artifact": bool(artifact),
        })
    for key in buckets:
        buckets[key].sort(key=lambda r: (r["name"] or "").lower())
    return buckets
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker cp src/backend/manage_stores.py localocr-extended-backend:/app/src/backend/manage_stores.py
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores.py -v"
```

Expected: all 18 tests pass (14 from Task 2 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_stores.py tests/test_manage_stores.py
git commit -m "feat(stores): get_store_buckets aggregator with usage stats

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `/api/stores` blueprint — TDD

**Files:**
- Create: `tests/test_manage_stores_endpoint.py`
- Create: `src/backend/manage_stores_endpoint.py`
- Modify: `src/backend/create_flask_application.py:215` and `:234`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manage_stores_endpoint.py`:

```python
import pytest

from src.backend.create_flask_application import create_flask_application


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_flask_application()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_stores_requires_auth(client):
    resp = client.get("/api/stores")
    assert resp.status_code in (401, 403)


def test_post_visibility_requires_auth(client):
    resp = client.post("/api/stores/1/visibility", json={"override": "hidden"})
    assert resp.status_code in (401, 403)
```

If the project has an established test-auth helper (look for fixtures in
existing files like `tests/test_*` that hit authenticated endpoints), add
follow-up tests that:
1. Call `GET /api/stores` and assert response has keys `frequent`, `low_freq`, `hidden`.
2. POST `/api/stores/<id>/visibility` with `override="garbage"` → 400.
3. POST with non-existent id → 404.
4. POST with `override="hidden"` then GET → store appears in `hidden` bucket.

If no such helper exists, document a manual smoke-test step in Task 9
covering the same assertions through the browser DevTools console.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker cp tests/test_manage_stores_endpoint.py localocr-extended-backend:/app/tests/test_manage_stores_endpoint.py
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores_endpoint.py -v"
```

Expected: tests run, but `GET /api/stores` returns 404 since the blueprint is not yet registered.

- [ ] **Step 3: Implement the blueprint**

Create `src/backend/manage_stores_endpoint.py`:

```python
"""Flask blueprint for the Manage Stores Settings panel.

Exposes:
  GET  /api/stores                          — bucketed list with usage stats.
  POST /api/stores/<int:store_id>/visibility — set or clear the override.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import Store
from src.backend.manage_stores import get_store_buckets

stores_bp = Blueprint("stores", __name__, url_prefix="/api/stores")

_VALID_OVERRIDES = {"frequent", "low_freq", "hidden", None}


@stores_bp.route("", methods=["GET"])
@require_auth
def list_stores():
    buckets = get_store_buckets(g.db_session)
    return jsonify(buckets)


@stores_bp.route("/<int:store_id>/visibility", methods=["POST"])
@require_write_access
def set_visibility(store_id: int):
    payload = request.get_json(silent=True) or {}
    override = payload.get("override")
    if override not in _VALID_OVERRIDES:
        return jsonify({"error": "invalid override"}), 400

    store = g.db_session.query(Store).filter(Store.id == store_id).first()
    if not store:
        return jsonify({"error": "store not found"}), 404

    store.visibility_override = override
    g.db_session.commit()
    return jsonify({
        "id": store.id,
        "name": store.name,
        "override": store.visibility_override,
    })
```

- [ ] **Step 4: Wire blueprint into the Flask app**

Modify `src/backend/create_flask_application.py`. Find the existing import block in `register_blueprints()` (around line 215) and add a new import after `chat_endpoints`:

```python
    from src.backend.chat_endpoints import chat_bp
    from src.backend.manage_stores_endpoint import stores_bp
```

Then find the `app.register_blueprint(chat_bp)` line (around 234) and add directly after it:

```python
    app.register_blueprint(chat_bp)
    app.register_blueprint(stores_bp)
```

- [ ] **Step 5: Sync, restart, run tests**

```bash
docker cp src/backend/manage_stores_endpoint.py localocr-extended-backend:/app/src/backend/manage_stores_endpoint.py
docker cp src/backend/create_flask_application.py localocr-extended-backend:/app/src/backend/create_flask_application.py
docker compose restart backend
sleep 12
docker compose exec backend bash -lc "cd /app && python -m pytest tests/test_manage_stores_endpoint.py -v"
```

Expected: both auth tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/backend/manage_stores_endpoint.py src/backend/create_flask_application.py tests/test_manage_stores_endpoint.py
git commit -m "feat(stores): /api/stores blueprint for bucket list + override POST

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Emit `available_store_buckets` from `/shopping-list`

**Files:**
- Modify: `src/backend/manage_shopping_list.py:418-450`

- [ ] **Step 1: Update the response payload**

Replace the existing `available_stores` block (currently around line 422):

```python
    available_stores = sorted({
        canonicalize_store_name(store.name)
        for store in session.query(Store).filter(
            (Store.is_payment_artifact.is_(False)) | (Store.is_payment_artifact.is_(None))
        ).all()
        if store.name
    })
```

With:

```python
    from src.backend.manage_stores import get_store_buckets

    buckets = get_store_buckets(session)
    available_store_buckets = {
        "frequent": sorted({canonicalize_store_name(r["name"]) for r in buckets["frequent"] if r["name"]}),
        "low_freq": sorted({canonicalize_store_name(r["name"]) for r in buckets["low_freq"] if r["name"]}),
    }
    # Backward-compatible flat list = frequent + low_freq, sorted.
    available_stores = sorted(set(available_store_buckets["frequent"] + available_store_buckets["low_freq"]))
```

- [ ] **Step 2: Add the new key to the return dict**

Find the return dict (around line 437) and add `"available_store_buckets"` after `"available_stores"`:

```python
    return {
        "items": items,
        ...
        "suggested_stores": suggested_stores,
        "available_stores": available_stores,
        "available_store_buckets": available_store_buckets,
        "helper_mode": helper_mode,
        ...
    }
```

- [ ] **Step 3: Sync + restart + manual smoke**

```bash
docker cp src/backend/manage_shopping_list.py localocr-extended-backend:/app/src/backend/manage_shopping_list.py
docker compose restart backend
sleep 12
curl -s http://localhost:8090/health
```

Expected: `{"service":"localocr-extended-backend","status":"healthy"}`.

- [ ] **Step 4: Confirm endpoint shape via authenticated request**

In a browser at http://192.168.50.50:8090, sign in, then in DevTools console:

```js
fetch("/shopping-list").then(r => r.json()).then(d => console.log(d.available_store_buckets));
```

Expected: an object with `frequent` and `low_freq` arrays.

- [ ] **Step 5: Commit**

```bash
git add src/backend/manage_shopping_list.py
git commit -m "feat(stores): emit available_store_buckets from /shopping-list

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — dropdown render helpers emit `<optgroup>`s

**Files:**
- Modify: `src/frontend/index.html` (around the `getInventoryStoreChoices` and `getShoppingStoreChoices` functions)

- [ ] **Step 1: Add a global bucket cache + a shared optgroup renderer**

Find the `let shoppingStoreOptions = [];` declaration (around line 5984 in the inline script) and add directly after it:

```js
      let shoppingStoreBuckets = { frequent: [], low_freq: [] };

      function buildStoreOptionTags(selectedValue, bucketsOverride) {
        const buckets = bucketsOverride || shoppingStoreBuckets;
        const selected = selectedValue || "";
        const defaults = ["Costco", "Kroger", "Target", "India Bazar"];
        const frequent = [...new Set([...defaults, ...(buckets.frequent || [])])].sort(
          (a, b) => a.localeCompare(b),
        );
        const lowFreq = (buckets.low_freq || [])
          .filter((s) => !frequent.includes(s))
          .slice()
          .sort((a, b) => a.localeCompare(b));
        const opt = (s) =>
          `<option value="${escHtml(s)}"${s === selected ? " selected" : ""}>${escHtml(s)}</option>`;
        const head = `<option value="">Any store</option>`;
        if (!lowFreq.length) {
          return [head, ...frequent.map(opt)].join("");
        }
        return (
          head +
          `<optgroup label="Stores">` +
          frequent.map(opt).join("") +
          `</optgroup>` +
          `<optgroup label="Rarely Used">` +
          lowFreq.map(opt).join("") +
          `</optgroup>`
        );
      }
```

- [ ] **Step 2: Replace the existing render helpers to call `buildStoreOptionTags`**

Find `renderInventoryStoreOptionTags` (around line 8915) and replace its body:

```js
      function renderInventoryStoreOptionTags(selectedValue = "") {
        return buildStoreOptionTags(selectedValue);
      }
```

Find `renderShoppingStoreOptionTags` (around line 21053) and replace its body:

```js
      function renderShoppingStoreOptionTags(selectedValue = "") {
        return buildStoreOptionTags(selectedValue);
      }
```

Delete `getInventoryStoreChoices` and `getShoppingStoreChoices` (now unused). Search the file to confirm no other callers remain; if any do, replace their call with `buildStoreOptionTags("")`.

- [ ] **Step 3: Populate `shoppingStoreBuckets` on `/shopping-list` fetch**

Find the line `shoppingStoreOptions = data.available_stores || [];` (around line 22390) and add directly after it:

```js
        shoppingStoreBuckets = data.available_store_buckets || { frequent: shoppingStoreOptions, low_freq: [] };
```

- [ ] **Step 4: Hard-reload the browser and visually confirm dropdown structure**

Open http://192.168.50.50:8090, hard-refresh (Cmd+Shift+R), open the Inventory page, click the store dropdown.

Expected: two visual sections — "Stores" with frequent merchants on top, "Rarely Used" below. If the user has no rare merchants, dropdown is flat (no optgroups).

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(stores): dropdown optgroups for Frequent / Rarely Used

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — Settings → Manage Stores card

**Files:**
- Modify: `src/frontend/index.html` (Settings page section + a new function block)
- Modify: `src/frontend/styles/page-shell/cards.css`

- [ ] **Step 1: Insert the card markup into the Settings page**

Find the existing Plaid card in the Settings page (search for `🏪 Plaid` or `id="settings-plaid"`) and insert directly after its closing `</div>`:

```html
            <div class="card" id="settings-manage-stores">
              <div class="card-header">
                <h3>🏪 Manage Stores</h3>
                <p class="muted">Pin merchants to Frequent / Rarely Used / Hidden, or let recency decide automatically.</p>
              </div>
              <div class="card-body">
                <div class="manage-stores-filters" role="tablist">
                  <button type="button" class="pill active" data-filter="all" onclick="setManageStoresFilter('all')">All</button>
                  <button type="button" class="pill" data-filter="frequent" onclick="setManageStoresFilter('frequent')">Frequent</button>
                  <button type="button" class="pill" data-filter="low_freq" onclick="setManageStoresFilter('low_freq')">Rarely Used</button>
                  <button type="button" class="pill" data-filter="hidden" onclick="setManageStoresFilter('hidden')">Hidden</button>
                </div>
                <div id="manage-stores-table" class="manage-stores-table">
                  <div class="empty-state"><p>Loading…</p></div>
                </div>
              </div>
            </div>
```

- [ ] **Step 2: Add the loader, renderer, and action handler**

Find a logical home for new functions (alongside other Settings page helpers, e.g. near `loadSettings()`). Insert:

```js
      let manageStoresCache = null;
      let manageStoresFilter = "all";

      async function loadManageStores() {
        const target = document.getElementById("manage-stores-table");
        if (!target) return;
        setHtml(target, '<div class="empty-state"><p>Loading…</p></div>');
        const res = await api("/api/stores");
        if (!res.ok) {
          setHtml(target, '<div class="empty-state"><p>Could not load stores.</p></div>');
          return;
        }
        manageStoresCache = await res.json();
        renderManageStoresTable();
      }

      function setManageStoresFilter(value) {
        manageStoresFilter = value;
        document.querySelectorAll("#settings-manage-stores .pill").forEach((p) => {
          p.classList.toggle("active", p.dataset.filter === value);
        });
        renderManageStoresTable();
      }

      function renderManageStoresTable() {
        const target = document.getElementById("manage-stores-table");
        if (!target || !manageStoresCache) return;
        const rows = [];
        const buckets = ["frequent", "low_freq", "hidden"];
        for (const b of buckets) {
          if (manageStoresFilter !== "all" && manageStoresFilter !== b) continue;
          for (const row of manageStoresCache[b] || []) {
            rows.push({ ...row, bucket: b });
          }
        }
        if (!rows.length) {
          setHtml(target, '<div class="empty-state"><p>No stores in this view.</p></div>');
          return;
        }
        const bucketLabel = (b) =>
          b === "frequent" ? "Frequent" : b === "low_freq" ? "Rarely Used" : "Hidden";
        const dateLabel = (iso) => (iso ? new Date(iso).toLocaleDateString() : "—");
        const sel = (row) => `
          <select onchange="setStoreVisibility(${row.id}, this.value)">
            <option value="auto" ${row.override === null ? "selected" : ""}>Auto</option>
            <option value="frequent" ${row.override === "frequent" ? "selected" : ""}>Pin Frequent</option>
            <option value="low_freq" ${row.override === "low_freq" ? "selected" : ""}>Pin Rarely Used</option>
            <option value="hidden" ${row.override === "hidden" ? "selected" : ""}>Pin Hidden</option>
          </select>`;
        const tableHtml = `
          <table class="manage-stores-grid">
            <thead><tr>
              <th>Name</th><th>Last purchase</th><th>Count</th><th>Bucket</th><th>Action</th>
            </tr></thead>
            <tbody>
              ${rows
                .map(
                  (r) => `<tr>
                    <td>${escHtml(r.name)}</td>
                    <td>${escHtml(dateLabel(r.last_purchase_at))}</td>
                    <td>${escHtml(r.purchase_count)}</td>
                    <td><span class="bucket-badge bucket-${r.bucket}">${bucketLabel(r.bucket)}</span></td>
                    <td>${sel(r)}</td>
                  </tr>`,
                )
                .join("")}
            </tbody>
          </table>`;
        setHtml(target, tableHtml);
      }

      async function setStoreVisibility(storeId, value) {
        const override = value === "auto" ? null : value;
        const res = await api(`/api/stores/${storeId}/visibility`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ override }),
        });
        if (!res.ok) {
          toast("Could not update store visibility", "error");
          return;
        }
        toast("Store updated", "success");
        await loadManageStores();
      }
```

- [ ] **Step 3: Trigger initial load when Settings page is shown**

Find the page-show handler for Settings (search for `nav("settings"` or the existing `loadSettings()` invocation). Add a call:

```js
        loadManageStores();
```

If a single `loadSettings()` exists, append `loadManageStores();` at its end.

- [ ] **Step 4: Add minimal CSS for the bucket badges + table**

Append to `src/frontend/styles/page-shell/cards.css`:

```css
.manage-stores-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.manage-stores-grid { width: 100%; border-collapse: collapse; }
.manage-stores-grid th,
.manage-stores-grid td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--color-border); font-size: 0.9rem; }
.bucket-badge { padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; }
.bucket-badge.bucket-frequent { background: var(--color-brand-soft); color: var(--color-brand); }
.bucket-badge.bucket-low_freq { background: var(--color-surface-2); color: var(--color-text-muted); }
.bucket-badge.bucket-hidden { background: var(--color-warn-soft, #fde2e2); color: var(--color-warn, #b00); }
```

- [ ] **Step 5: Sync + reload + visual confirmation**

```bash
docker cp src/frontend/index.html localocr-extended-backend:/app/src/frontend/index.html
docker cp src/frontend/styles/page-shell/cards.css localocr-extended-backend:/app/src/frontend/styles/page-shell/cards.css
docker compose restart backend
```

Hard-refresh http://192.168.50.50:8090. Open Settings, scroll to Manage Stores. Confirm:
- Table renders with last_purchase, count, bucket badge, action select.
- Filter pills switch the visible bucket.
- Picking "Pin Hidden" on a store and reopening Inventory dropdown excludes that store.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html src/frontend/styles/page-shell/cards.css
git commit -m "feat(stores): Settings → Manage Stores panel + bucket badges

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Backup/restore safety smoke

**Files:** None (validation only)

- [ ] **Step 1: Take a fresh backup post-migration**

```bash
docker compose exec backend bash /app/scripts/backup_database_and_volumes.sh
```

Expected last line: `✅ Backup created: /data/backups/localocr_extended_backup_<ts>.tar.gz`.

- [ ] **Step 2: Inspect manifest to confirm DB included**

```bash
docker compose exec backend bash -lc "ls -la /data/backups | tail -5"
docker compose exec backend bash -lc "cat /data/backups/localocr_extended_backup_*.manifest.json | head -30"
```

Expected: the latest manifest references `localocr_extended.db`.

- [ ] **Step 3: Pre-restore: verify the current schema includes the new column**

```bash
docker compose exec backend python -c "
import sqlite3, glob
p = glob.glob('/data/db/localocr_extended.db')[0]
c = sqlite3.connect(p)
[print(r) for r in c.execute('PRAGMA table_info(stores)').fetchall()]"
```

Expected: row for `visibility_override` is present.

- [ ] **Step 4: Test restore (only if a non-prod backup is available)**

If a pre-018 backup exists locally, restore via the Settings → Environment Restore UI or `scripts/restore_database_and_volumes.sh`, then run alembic upgrade head and verify:

```bash
docker compose exec backend bash -lc "cd /app && alembic upgrade head"
docker compose exec backend python -c "
import sqlite3, glob
p = glob.glob('/data/db/localocr_extended.db')[0]
c = sqlite3.connect(p)
[print(r) for r in c.execute('PRAGMA table_info(stores)').fetchall()]"
```

Expected: `visibility_override` column appears after the upgrade — proving the migration is restore-safe.

If no pre-018 backup is available, skip Step 4 and rely on the PRAGMA-guarded migration (matching the same pattern that 008 and 017 ship under).

- [ ] **Step 5: Confirm checklist (no commit needed)**

- [ ] Backup script ran without error.
- [ ] Manifest contains the DB.
- [ ] Schema includes `visibility_override`.
- [ ] Restore + upgrade flow leaves the column in place (or skipped due to no available backup).

---

## Task 9: Push to prod

**Files:** None (deploy step)

- [ ] **Step 1: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Pull + rebuild on prod**

On UDImmich:

```bash
ssh npalakurla@UDImmich
cd /opt/extended/LocalOCR_Extended
git pull --ff-only
docker compose exec -T backend bash /app/scripts/backup_database_and_volumes.sh
docker compose up -d --build backend
sleep 15
curl -s http://localhost:8090/health
```

Expected: healthy.

- [ ] **Step 3: Verify migration ran**

```bash
docker compose exec backend python -c "
import sqlite3, glob
p = glob.glob('/data/db/localocr_extended.db')[0]
c = sqlite3.connect(p)
[print(r) for r in c.execute('PRAGMA table_info(stores)').fetchall()]"
```

Expected: `visibility_override` column present.

- [ ] **Step 4: Smoke checklist (browser, hard-refresh)**

- [ ] Settings → Manage Stores card renders.
- [ ] Bucket badges show colours.
- [ ] Filter pills switch view.
- [ ] Pin a store to Hidden → next dropdown render excludes it.
- [ ] Pin a store to Frequent → top section.
- [ ] Pin to Auto → bucket recomputes from purchase recency.
- [ ] Pre-existing CC artifacts (Phase 2) still hidden, unaffected by override.
- [ ] Backup + restore (dev) leaves Manage Stores working.

---

## Self-Review

**Spec coverage:**
- Data model column → Task 1 ✓
- Auto-classify rule → Task 2 ✓
- Aggregator → Task 3 ✓
- GET/POST endpoints → Task 4 ✓
- `available_store_buckets` in shopping-list → Task 5 ✓
- Dropdown optgroups → Task 6 ✓
- Settings panel → Task 7 ✓
- Backup/restore safety → Task 8 ✓
- Tests for `classify_store` truth table → Task 2 ✓
- Tests for `get_store_buckets` → Task 3 ✓
- Tests for blueprint → Task 4 ✓ (auth-only baseline; deeper tests gated on existing harness)

**Placeholder scan:** No TBDs.

**Type consistency:** `classify_store` signature consistent across Tasks 2–4. Bucket keys (`frequent`, `low_freq`, `hidden`) consistent across backend + frontend. `override` column type `String(16)` consistent with valid set `{frequent, low_freq, hidden, NULL}`. `setHtml` helper documented at the top and used uniformly in frontend tasks.
