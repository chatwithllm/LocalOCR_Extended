# Fixed Obligations Manager + Analytics Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users curate a "monthly floor" list of must-pay expenses and surface a month-over-month comparison panel on the Dashboard above Spending by Category.

**Architecture:** New `FloorObligation` SQLAlchemy model + SQLite migration → new `handle_floor_obligations.py` blueprint with CRUD + summary endpoints → Bills page gets a management table, Dashboard gets a read-only widget. Bill-linked rows resolve actuals from existing BillMeta+Purchase data; manual rows show expected amount only.

**Tech Stack:** Python/SQLAlchemy/Flask, vanilla JS (no build step), SQLite (prod uses same ORM; `_ensure_runtime_columns` handles SQLite dev migration).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/backend/initialize_database_schema.py` | Modify | Add `FloorObligation` model; add SQLite migration in `_ensure_runtime_columns` |
| `src/backend/handle_floor_obligations.py` | Create | Blueprint `floor_obligations_bp` with CRUD + summary endpoints |
| `src/backend/create_flask_application.py` | Modify | Register `floor_obligations_bp` |
| `src/frontend/index.html` | Modify | Bills page: management table; Dashboard page: floor widget |
| `tests/test_floor_obligations.py` | Create | API tests for CRUD and summary |

---

## Task 1: FloorObligation Model + Migration

**Files:**
- Modify: `src/backend/initialize_database_schema.py`
- Test: `tests/test_floor_obligations.py`

### Background
Models live in `initialize_database_schema.py`. New tables auto-created by `Base.metadata.create_all(engine)`. For existing SQLite dev DBs, `_ensure_runtime_columns` (line ~1139) runs DDL inside `with engine.begin() as conn:`. `existing_tables` set is already computed there. `utcnow` helper at line ~66. Add `FloorObligation` after `SharedExpense` (~line 1053).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_obligations.py
"""FloorObligation model and CRUD API tests."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")


@pytest.fixture
def app(tmp_path):
    import src.backend.create_flask_application as cfa
    import src.backend.initialize_database_schema as schema_module
    from src.backend.create_flask_application import create_app

    db_url = f"sqlite:///{tmp_path / 'floor_test.db'}"
    os.environ["DATABASE_URL"] = db_url
    schema_module.DATABASE_URL = db_url
    cfa._engine = None
    cfa._SessionFactory = None

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(client):
    return {"Authorization": "Bearer test-admin-token"}


def test_floor_obligation_table_exists(app):
    from src.backend.initialize_database_schema import FloorObligation
    from src.backend.create_flask_application import _engine
    from sqlalchemy import inspect
    insp = inspect(_engine)
    assert "floor_obligations" in insp.get_table_names()
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended
python -m pytest tests/test_floor_obligations.py::test_floor_obligation_table_exists -v
```

Expected: `ImportError: cannot import name 'FloorObligation'`

- [ ] **Step 3: Add FloorObligation model to `initialize_database_schema.py`**

Add after the `SharedExpense` class (after line ~1053), before `SharedParticipant`:

```python
class FloorObligation(Base):
    """A must-pay monthly expense tracked for the household floor calculation."""

    __tablename__ = "floor_obligations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(255), nullable=False)
    expected_monthly_amount = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=True)
    bill_provider_id = Column(Integer, ForeignKey("bill_providers.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_floor_obligations_is_active", "is_active"),
    )

    provider = relationship("BillProvider", foreign_keys=[bill_provider_id])
```

- [ ] **Step 4: Add SQLite migration in `_ensure_runtime_columns`**

At the end of `_ensure_runtime_columns`, inside `with engine.begin() as conn:`, append:

```python
        if "floor_obligations" not in existing_tables:
            conn.execute(text(
                """CREATE TABLE IF NOT EXISTS floor_obligations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label VARCHAR(255) NOT NULL,
                    expected_monthly_amount FLOAT NOT NULL DEFAULT 0.0,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    bill_provider_id INTEGER REFERENCES bill_providers(id),
                    created_at DATETIME,
                    updated_at DATETIME
                )"""
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_floor_obligations_is_active "
                "ON floor_obligations (is_active)"
            ))
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest tests/test_floor_obligations.py::test_floor_obligation_table_exists -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/backend/initialize_database_schema.py tests/test_floor_obligations.py
git commit -m "feat(floor): add FloorObligation model and SQLite migration"
```

---

## Task 2: CRUD Endpoints

**Files:**
- Create: `src/backend/handle_floor_obligations.py`
- Modify: `src/backend/create_flask_application.py`
- Test: `tests/test_floor_obligations.py`

### Background
Blueprint pattern: see `manage_cash_transactions.py`. `g.db_session` is the per-request SQLAlchemy session. Register blueprints in `create_flask_application.py` around line 391 (Blueprint Registration section). `require_auth` and `require_write_access` imported from `create_flask_application`.

- [ ] **Step 1: Add CRUD tests**

Append to `tests/test_floor_obligations.py`:

```python
def test_list_floor_obligations_empty(client):
    res = client.get("/floor-obligations/", headers=_auth(client))
    assert res.status_code == 200
    assert res.get_json()["obligations"] == []


def test_create_manual_obligation(client):
    res = client.post(
        "/floor-obligations/",
        json={"label": "Rent", "expected_monthly_amount": 1500.0},
        headers=_auth(client),
    )
    assert res.status_code == 201
    ob = res.get_json()["obligation"]
    assert ob["label"] == "Rent"
    assert ob["expected_monthly_amount"] == 1500.0
    assert ob["is_active"] is True
    assert ob["source"] == "manual"


def test_patch_obligation_toggle(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Car Loan", "expected_monthly_amount": 450.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    patch_res = client.patch(
        f"/floor-obligations/{oid}",
        json={"is_active": False},
        headers=_auth(client),
    )
    assert patch_res.status_code == 200
    assert patch_res.get_json()["obligation"]["is_active"] is False


def test_delete_manual_obligation(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Allowance", "expected_monthly_amount": 200.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    del_res = client.delete(f"/floor-obligations/{oid}", headers=_auth(client))
    assert del_res.status_code == 200
    ids = [o["id"] for o in client.get("/floor-obligations/", headers=_auth(client)).get_json()["obligations"]]
    assert oid not in ids
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_floor_obligations.py -k "list or create or patch or delete" -v 2>&1 | tail -15
```

Expected: 4 failures with 404.

- [ ] **Step 3: Create `src/backend/handle_floor_obligations.py`**

```python
"""CRUD and summary endpoints for FloorObligation (monthly floor tracking)."""
from __future__ import annotations
import logging
from flask import Blueprint, g, jsonify, request
from src.backend.create_flask_application import require_auth, require_write_access

logger = logging.getLogger(__name__)

floor_obligations_bp = Blueprint(
    "floor_obligations", __name__, url_prefix="/floor-obligations"
)


def _serialize(ob) -> dict:
    return {
        "id": ob.id,
        "label": ob.label,
        "expected_monthly_amount": ob.expected_monthly_amount,
        "is_active": ob.is_active,
        "bill_provider_id": ob.bill_provider_id,
        "source": "bill_provider" if ob.bill_provider_id else "manual",
        "created_at": ob.created_at.isoformat() if ob.created_at else None,
    }


@floor_obligations_bp.route("/", methods=["GET"])
@require_auth
def list_obligations():
    from src.backend.initialize_database_schema import FloorObligation
    rows = (
        g.db_session.query(FloorObligation)
        .order_by(FloorObligation.is_active.desc(), FloorObligation.label)
        .all()
    )
    return jsonify({"obligations": [_serialize(r) for r in rows]}), 200


@floor_obligations_bp.route("/", methods=["POST"])
@require_write_access
def create_obligation():
    from src.backend.initialize_database_schema import FloorObligation
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or "").strip()
    if not label:
        return jsonify({"error": "label is required"}), 400
    try:
        amount = float(payload.get("expected_monthly_amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "expected_monthly_amount must be a number"}), 400
    bill_provider_id = payload.get("bill_provider_id")
    if bill_provider_id is not None:
        try:
            bill_provider_id = int(bill_provider_id)
        except (TypeError, ValueError):
            return jsonify({"error": "bill_provider_id must be an integer"}), 400
    ob = FloorObligation(
        label=label,
        expected_monthly_amount=amount,
        is_active=True,
        bill_provider_id=bill_provider_id,
    )
    g.db_session.add(ob)
    g.db_session.commit()
    return jsonify({"obligation": _serialize(ob)}), 201


@floor_obligations_bp.route("/<int:ob_id>", methods=["PATCH"])
@require_write_access
def update_obligation(ob_id: int):
    from src.backend.initialize_database_schema import FloorObligation
    ob = g.db_session.query(FloorObligation).filter_by(id=ob_id).first()
    if not ob:
        return jsonify({"error": "Not found"}), 404
    payload = request.get_json(silent=True) or {}
    if "is_active" in payload:
        ob.is_active = bool(payload["is_active"])
    if "expected_monthly_amount" in payload:
        try:
            ob.expected_monthly_amount = float(payload["expected_monthly_amount"])
        except (TypeError, ValueError):
            return jsonify({"error": "expected_monthly_amount must be a number"}), 400
    if "label" in payload:
        label = (payload["label"] or "").strip()
        if not label:
            return jsonify({"error": "label cannot be empty"}), 400
        ob.label = label
    g.db_session.commit()
    return jsonify({"obligation": _serialize(ob)}), 200


@floor_obligations_bp.route("/<int:ob_id>", methods=["DELETE"])
@require_write_access
def delete_obligation(ob_id: int):
    from src.backend.initialize_database_schema import FloorObligation
    ob = g.db_session.query(FloorObligation).filter_by(id=ob_id).first()
    if not ob:
        return jsonify({"error": "Not found"}), 404
    if ob.bill_provider_id is not None:
        return jsonify({"error": "Bill-linked obligations cannot be deleted — toggle is_active instead"}), 400
    g.db_session.delete(ob)
    g.db_session.commit()
    return jsonify({"deleted": ob_id}), 200
```

- [ ] **Step 4: Register blueprint in `create_flask_application.py`**

In the Blueprint Registration section (around line 391), add:

```python
    from src.backend.handle_floor_obligations import floor_obligations_bp
    app.register_blueprint(floor_obligations_bp)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_floor_obligations.py -k "list or create or patch or delete" -v
```

Expected: all 4 pass.

- [ ] **Step 6: Commit**

```bash
git add src/backend/handle_floor_obligations.py src/backend/create_flask_application.py tests/test_floor_obligations.py
git commit -m "feat(floor): CRUD endpoints for FloorObligation"
```

---

## Task 3: Summary Endpoint

**Files:**
- Modify: `src/backend/handle_floor_obligations.py`
- Test: `tests/test_floor_obligations.py`

### Background
For bill-linked obligations, actuals come from Purchase rows joined through BillMeta where `BillMeta.provider_id == ob.bill_provider_id` and `Purchase.date` falls in the calendar month. For manual obligations (bill_provider_id is None), actuals are always None and status is "manual".

Status logic:
- `"paid"` — actual found, amount <= expected * 1.05 (5% tolerance)
- `"paid_over"` — actual found, amount > expected * 1.05
- `"not_recorded"` — no actual found (bill-linked only)
- `"manual"` — manual obligation

- [ ] **Step 1: Add summary tests**

Append to `tests/test_floor_obligations.py`:

```python
def test_summary_manual_obligation_shows_expected(client):
    client.post(
        "/floor-obligations/",
        json={"label": "Internet", "expected_monthly_amount": 80.0},
        headers=_auth(client),
    )
    res = client.get("/floor-obligations/summary?month=2026-05", headers=_auth(client))
    assert res.status_code == 200
    data = res.get_json()
    assert data["floor_total"] == 80.0
    assert len(data["obligations"]) == 1
    ob = data["obligations"][0]
    assert ob["label"] == "Internet"
    assert ob["this_month_actual"] is None
    assert ob["last_month_actual"] is None
    assert ob["status"] == "manual"


def test_summary_inactive_excluded(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Gym", "expected_monthly_amount": 50.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    client.patch(f"/floor-obligations/{oid}", json={"is_active": False}, headers=_auth(client))
    res = client.get("/floor-obligations/summary?month=2026-05", headers=_auth(client))
    assert res.status_code == 200
    labels = [o["label"] for o in res.get_json()["obligations"]]
    assert "Gym" not in labels
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_floor_obligations.py -k "summary" -v
```

Expected: 2 failures with 404.

- [ ] **Step 3: Add summary endpoint — append to `handle_floor_obligations.py`**

```python
@floor_obligations_bp.route("/summary", methods=["GET"])
@require_auth
def obligations_summary():
    """Monthly floor summary with this-month and last-month actuals."""
    import re
    from datetime import datetime, timezone
    from src.backend.initialize_database_schema import FloorObligation, BillMeta, Purchase

    month_str = (request.args.get("month") or "").strip()
    if not month_str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
    if not re.match(r"^\d{4}-\d{2}$", month_str):
        return jsonify({"error": "month must be YYYY-MM"}), 400

    year, mon = int(month_str[:4]), int(month_str[5:7])
    this_start = datetime(year, mon, 1, tzinfo=timezone.utc)
    this_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if mon == 12 else datetime(year, mon + 1, 1, tzinfo=timezone.utc)
    prev_end = this_start
    prev_start = datetime(year - 1, 12, 1, tzinfo=timezone.utc) if mon == 1 else datetime(year, mon - 1, 1, tzinfo=timezone.utc)

    session = g.db_session
    obligations = (
        session.query(FloorObligation)
        .filter_by(is_active=True)
        .order_by(FloorObligation.label)
        .all()
    )

    def _month_actual(provider_id, start, end):
        rows = (
            session.query(Purchase)
            .join(BillMeta, BillMeta.purchase_id == Purchase.id)
            .filter(BillMeta.provider_id == provider_id, Purchase.date >= start, Purchase.date < end)
            .all()
        )
        if not rows:
            return None
        return round(sum(float(p.total_amount or 0) for p in rows), 2)

    result = []
    floor_total = 0.0
    for ob in obligations:
        floor_total += ob.expected_monthly_amount or 0.0
        if ob.bill_provider_id is None:
            result.append({**_serialize(ob), "this_month_actual": None, "last_month_actual": None, "delta": None, "status": "manual"})
            continue
        this_actual = _month_actual(ob.bill_provider_id, this_start, this_end)
        last_actual = _month_actual(ob.bill_provider_id, prev_start, prev_end)
        delta = round(this_actual - last_actual, 2) if this_actual is not None and last_actual is not None else None
        if this_actual is None:
            status = "not_recorded"
        elif this_actual <= (ob.expected_monthly_amount or 0) * 1.05:
            status = "paid"
        else:
            status = "paid_over"
        result.append({**_serialize(ob), "this_month_actual": this_actual, "last_month_actual": last_actual, "delta": delta, "status": status})

    return jsonify({"month": month_str, "floor_total": round(floor_total, 2), "obligations": result}), 200
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_floor_obligations.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_floor_obligations.py tests/test_floor_obligations.py
git commit -m "feat(floor): summary endpoint with MoM actuals"
```

---

## Task 4: Bills Page — Management Table

**Files:**
- Modify: `src/frontend/index.html`

### Background
Bills page: `id="page-bills"` (~line 4185), content in `id="bills-body"` (~line 4195). `loadBills()` at line ~37258. All JS in one `<script>` block near end of file. Use `escHtml(str)` for user strings in innerHTML, `formatMoney(n)` for amounts, `api(path, opts)` for fetch, `toast(msg, type)` for notifications. `api()` already sets JSON Content-Type and auth headers.

- [ ] **Step 1: Add HTML slot at top of bills-body**

Find the line (around 4195):
```html
          <div id="bills-body" class="workspace-scroll">
```

Immediately after it (before the next element), add:

```html
            <div id="floor-obligations-section" style="margin-bottom:16px"></div>
```

- [ ] **Step 2: Add CSS near other bill styles**

In the `<style>` block (search for `.bills-section`), add before or after it:

```css
      #floor-obligations-section .floor-table {
        width: 100%; border-collapse: collapse; font-size: 0.88rem;
      }
      #floor-obligations-section .floor-table th {
        text-align: left; padding: 6px 10px;
        color: var(--muted, #aaa); font-weight: 500;
        border-bottom: 1px solid var(--border, #333);
      }
      #floor-obligations-section .floor-table td {
        padding: 7px 10px; border-bottom: 1px solid var(--border, #2a2a2a);
        vertical-align: middle;
      }
```

- [ ] **Step 3: Add JS functions**

Find `async function loadBalances()` in the JS block and add the following functions directly after it:

```javascript
      async function loadFloorObligations() {
        const el = document.getElementById('floor-obligations-section');
        if (!el) return;
        el.innerHTML = '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">Loading…</p>';
        try {
          const res = await api('/floor-obligations/');
          const data = await res.json().catch(function() { return {}; });
          if (!res.ok) { el.innerHTML = ''; return; }
          el.innerHTML = _renderFloorObligationsTable(data.obligations || []);
        } catch (e) { el.innerHTML = ''; }
      }

      function _renderFloorObligationsTable(obligations) {
        const rows = obligations.map(function(ob) {
          const chk = '<input type="checkbox" ' + (ob.is_active ? 'checked' : '') + ' onchange="toggleFloorObligation(' + ob.id + ', this.checked)" title="Include in monthly floor">';
          const amt = '<input type="number" step="0.01" min="0" value="' + ob.expected_monthly_amount + '" style="width:90px;padding:4px 6px;border-radius:5px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem" onblur="saveFloorObligationAmount(' + ob.id + ', this.value)" title="Expected $/mo">';
          const src = ob.source === 'bill_provider'
            ? '<span style="font-size:0.75rem;color:var(--muted,#aaa)">Bills</span>'
            : '<span style="font-size:0.75rem;color:var(--info,#60a5fa)">Manual</span>';
          const del = ob.source === 'manual'
            ? '<button class="btn btn-ghost btn-sm" onclick="deleteFloorObligation(' + ob.id + ')" style="color:var(--danger,#ef4444);padding:2px 6px" title="Remove">×</button>'
            : '';
          return '<tr><td style="width:32px">' + chk + '</td><td>' + escHtml(ob.label) + '</td><td>' + amt + '</td><td>' + src + '</td><td style="width:32px">' + del + '</td></tr>';
        }).join('');

        const table = obligations.length === 0
          ? '<p style="color:var(--muted,#aaa);font-size:0.85rem">No obligations yet. Add one below or sync from Bills.</p>'
          : '<table class="floor-table"><thead><tr><th></th><th>Name</th><th>Expected/mo</th><th>Source</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';

        return '<div style="padding:4px 0 8px">'
          + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
          + '<h4 style="margin:0;font-size:0.95rem">📌 Fixed Monthly Obligations</h4></div>'
          + table
          + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px">'
          + '<input id="floor-new-label" type="text" placeholder="Label (e.g. Car Loan)" style="padding:5px 8px;border-radius:6px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem;width:160px">'
          + '<input id="floor-new-amount" type="number" step="0.01" min="0" placeholder="$/mo" style="width:80px;padding:5px 8px;border-radius:6px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem">'
          + '<button class="btn btn-primary btn-sm" onclick="addFloorObligation()">＋ Add</button>'
          + '<button class="btn btn-ghost btn-sm" onclick="syncFloorFromBillProviders()" title="Import bill providers not yet in your floor list">Sync from Bills</button>'
          + '</div></div>';
      }

      async function toggleFloorObligation(id, isActive) {
        const res = await api('/floor-obligations/' + id, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) });
        if (!res.ok) { toast('Save failed', 'error'); loadFloorObligations(); }
      }

      async function saveFloorObligationAmount(id, value) {
        const amount = parseFloat(value);
        if (isNaN(amount) || amount < 0) { toast('Invalid amount', 'error'); return; }
        const res = await api('/floor-obligations/' + id, { method: 'PATCH', body: JSON.stringify({ expected_monthly_amount: amount }) });
        if (!res.ok) toast('Save failed', 'error');
      }

      async function deleteFloorObligation(id) {
        if (!confirm('Remove this obligation?')) return;
        const res = await api('/floor-obligations/' + id, { method: 'DELETE' });
        if (res.ok) { toast('Removed', 'success'); loadFloorObligations(); }
        else toast('Delete failed', 'error');
      }

      async function addFloorObligation() {
        const label = (document.getElementById('floor-new-label') ? document.getElementById('floor-new-label').value : '').trim();
        const amount = parseFloat(document.getElementById('floor-new-amount') ? document.getElementById('floor-new-amount').value : '0');
        if (!label) { toast('Enter a label', 'error'); return; }
        if (isNaN(amount) || amount < 0) { toast('Enter a valid amount', 'error'); return; }
        const res = await api('/floor-obligations/', { method: 'POST', body: JSON.stringify({ label: label, expected_monthly_amount: amount }) });
        if (res.ok) {
          document.getElementById('floor-new-label').value = '';
          document.getElementById('floor-new-amount').value = '';
          toast('Added', 'success');
          loadFloorObligations();
        } else {
          const d = await res.json().catch(function() { return {}; });
          toast(d.error || 'Add failed', 'error');
        }
      }

      async function syncFloorFromBillProviders() {
        const obligRes = await api('/floor-obligations/').then(function(r) { return r.json().catch(function() { return {}; }); });
        const provRes = await api('/receipts/bill-providers').then(function(r) { return r.json().catch(function() { return {}; }); });
        const existingIds = new Set((obligRes.obligations || []).filter(function(o) { return o.bill_provider_id != null; }).map(function(o) { return o.bill_provider_id; }));
        const toAdd = (provRes.providers || []).filter(function(p) { return !existingIds.has(p.id); });
        if (toAdd.length === 0) { toast('All bill providers already in your floor list', 'info'); return; }
        var added = 0;
        for (var i = 0; i < toAdd.length; i++) {
          const p = toAdd[i];
          const res = await api('/floor-obligations/', { method: 'POST', body: JSON.stringify({ label: p.canonical_name || p.name || 'Unknown', expected_monthly_amount: p.typical_amount_max || p.typical_amount_min || 0, bill_provider_id: p.id }) });
          if (res.ok) added++;
        }
        toast('Added ' + added + ' provider' + (added === 1 ? '' : 's'), 'success');
        loadFloorObligations();
      }
```

- [ ] **Step 4: Wire into `loadBills()`**

Find `async function loadBills(options)` (~line 37258). At the start of the function body, after `if (!monthInput) return;`, add:

```javascript
        loadFloorObligations();
```

- [ ] **Step 5: Verify manually**

Navigate to Bills page. Confirm:
- "Fixed Monthly Obligations" section appears at top
- Add form creates a new row (visible in the table)
- Checkbox toggle saves without error toast
- Delete button removes manual rows
- "Sync from Bills" imports providers not already in the list

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(floor): Bills page management table for fixed obligations"
```

---

## Task 5: Dashboard Widget

**Files:**
- Modify: `src/frontend/index.html`

### Background
Dashboard page HTML is around lines 2250-2312. Inventory row: `id="dashboard-stats-row"` (~2252). Spending card: `id="dashboard-spending-card"` (~2298). New widget goes between them. The nav hook that calls `loadSpendingByCategory()` on Dashboard load is around line 14282 — search for `if (page === "dashboard"` or `loadSpendingByCategory` near a nav handler. `formatMoney(n)` formats currency. `escHtml(s)` for user strings.

- [ ] **Step 1: Add HTML widget slot between inventory row and spending card**

Find (around line 2294):
```html
          <!-- Row 2: Spending by Category
```

Insert before that comment:

```html
          <!-- Row 1.5: Fixed Obligations floor widget -->
          <div class="card" id="dashboard-floor-card" style="display:none">
            <div class="card-header">
              <span class="card-title">&#128204; Fixed Obligations</span>
              <span class="card-header-inline-stat" id="dashboard-floor-total"></span>
            </div>
            <div id="dashboard-floor-body" style="overflow-x:auto"></div>
          </div>
```

- [ ] **Step 2: Add `loadFloorWidget()` and `_renderFloorWidget()` JS functions**

Add after `syncFloorFromBillProviders()` (from Task 4):

```javascript
      async function loadFloorWidget() {
        const card = document.getElementById('dashboard-floor-card');
        const body = document.getElementById('dashboard-floor-body');
        const totalEl = document.getElementById('dashboard-floor-total');
        if (!card || !body) return;
        const now = new Date();
        const ym = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
        try {
          const res = await api('/floor-obligations/summary?month=' + encodeURIComponent(ym));
          const data = await res.json().catch(function() { return {}; });
          if (!res.ok || !data.obligations || data.obligations.length === 0) { card.style.display = 'none'; return; }
          card.style.display = '';
          if (totalEl) totalEl.textContent = 'Floor: ' + formatMoney(data.floor_total);
          body.innerHTML = _renderFloorWidget(data.obligations);
        } catch (e) { card.style.display = 'none'; }
      }

      function _renderFloorWidget(obligations) {
        const statusIcon = { paid: '✅', paid_over: '⚠️', not_recorded: '🔴', manual: '📝' };
        const statusLabel = { paid: 'paid', paid_over: 'paid (over)', not_recorded: 'not recorded', manual: 'manual' };
        const rows = obligations.map(function(ob) {
          const thisMo = ob.this_month_actual != null ? formatMoney(ob.this_month_actual) : '—';
          const lastMo = ob.last_month_actual != null ? formatMoney(ob.last_month_actual) : '—';
          var deltaHtml = '—';
          if (ob.delta != null) {
            const sign = ob.delta > 0 ? '+' : '';
            const color = ob.delta > 0 ? 'var(--warning,#d97706)' : 'var(--success,#16a34a)';
            deltaHtml = '<span style="color:' + color + '">' + sign + formatMoney(ob.delta) + '</span>';
          }
          const icon = statusIcon[ob.status] || '';
          const lbl = statusLabel[ob.status] || ob.status;
          return '<tr>'
            + '<td style="padding:6px 10px;font-size:0.88rem">' + escHtml(ob.label) + '</td>'
            + '<td style="padding:6px 10px;font-size:0.88rem;text-align:right">' + thisMo + '</td>'
            + '<td style="padding:6px 10px;font-size:0.88rem;text-align:right;color:var(--muted,#aaa)">' + lastMo + '</td>'
            + '<td style="padding:6px 10px;font-size:0.88rem;text-align:right">' + deltaHtml + '</td>'
            + '<td style="padding:6px 10px;font-size:0.82rem">' + icon + ' ' + lbl + '</td>'
            + '</tr>';
        }).join('');
        const totalRecorded = obligations.reduce(function(s, ob) { return s + (ob.this_month_actual != null ? ob.this_month_actual : 0); }, 0);
        const lastTotal = obligations.reduce(function(s, ob) { return s + (ob.last_month_actual != null ? ob.last_month_actual : 0); }, 0);
        const totalDelta = totalRecorded - lastTotal;
        const totalDeltaHtml = totalRecorded > 0
          ? '<span style="color:' + (totalDelta > 0 ? 'var(--warning,#d97706)' : 'var(--success,#16a34a)') + '">' + (totalDelta > 0 ? '+' : '') + formatMoney(totalDelta) + '</span>'
          : '—';
        return '<table style="width:100%;border-collapse:collapse;font-size:0.88rem">'
          + '<thead><tr style="border-bottom:1px solid var(--border,#333)">'
          + '<th style="padding:5px 10px;text-align:left;color:var(--muted,#aaa);font-weight:500">Obligation</th>'
          + '<th style="padding:5px 10px;text-align:right;color:var(--muted,#aaa);font-weight:500">This mo.</th>'
          + '<th style="padding:5px 10px;text-align:right;color:var(--muted,#aaa);font-weight:500">Last mo.</th>'
          + '<th style="padding:5px 10px;text-align:right;color:var(--muted,#aaa);font-weight:500">Δ</th>'
          + '<th style="padding:5px 10px;color:var(--muted,#aaa);font-weight:500">Status</th>'
          + '</tr></thead><tbody>' + rows
          + '<tr style="border-top:1px solid var(--border,#333);font-weight:600">'
          + '<td style="padding:6px 10px">Total recorded</td>'
          + '<td style="padding:6px 10px;text-align:right">' + (totalRecorded > 0 ? formatMoney(totalRecorded) : '—') + '</td>'
          + '<td style="padding:6px 10px;text-align:right;color:var(--muted,#aaa)">' + (lastTotal > 0 ? formatMoney(lastTotal) : '—') + '</td>'
          + '<td style="padding:6px 10px;text-align:right">' + totalDeltaHtml + '</td>'
          + '<td></td></tr>'
          + '</tbody></table>';
      }
```

- [ ] **Step 3: Call `loadFloorWidget()` on Dashboard load**

Search for where `loadSpendingByCategory()` is called inside the nav/dashboard-load handler (around line 14282, inside `if (page === "dashboard"` or equivalent). Add `loadFloorWidget();` on the next line after `loadSpendingByCategory()`.

- [ ] **Step 4: Verify manually**

1. Go to Bills page, add at least one obligation (or sync from Bills)
2. Go to Dashboard
3. Confirm: "Fixed Obligations" card appears between inventory stats and Spending by Category
4. Rows show name, this month actual (or —), last month, delta, status icon
5. Card header shows "Floor: $X,XXX"
6. If zero obligations, the card is hidden

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/test_floor_obligations.py -v
```

Expected: all 7 pass.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(floor): Dashboard floor obligations widget with MoM comparison"
```
