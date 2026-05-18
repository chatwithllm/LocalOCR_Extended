# Floor Obligations v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6-month avg/latest-actual history fields to the floor obligations list and management UI, plus a Selected/Available tabbed panel so users can tune their floor list without deleting items.

**Architecture:** Pure Flask + vanilla-JS SPA. Backend: new `_compute_history()` helper enriches `GET /floor-obligations/` response; new `GET /floor-obligations/available` returns unlinked bill providers. Frontend: replace flat floor table in `index.html` with a two-tab panel (Selected / Available) that consumes both endpoints.

**Tech Stack:** Python/Flask/SQLAlchemy, vanilla JS (inline in index.html), pytest via `venv/bin/pytest`

---

## File Map

| File | Change |
|------|--------|
| `src/backend/handle_floor_obligations.py` | Add `_compute_history()`, enrich `_serialize()`, update `list_obligations()`, add `list_available()` route |
| `tests/test_floor_obligations.py` | Add `_create_provider_and_purchase()` fixture + 5 new tests |
| `src/frontend/index.html` | Replace lines 39268-39362 with tabbed panel; add tab CSS; remove `syncFloorFromBillProviders` and `toggleFloorObligation` |

---

### Task 1: Backend — history helper + enriched list response

**Files:**
- Modify: `src/backend/handle_floor_obligations.py`
- Test: `tests/test_floor_obligations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_floor_obligations.py` after the existing imports/fixtures:

```python
# --- helpers for v2 tests ---

def _create_provider_and_purchase(app, provider_name, amount, months_ago):
    """Create a BillProvider + Purchase + BillMeta dated `months_ago` calendar months before now."""
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta
    from src.backend.initialize_database_schema import BillProvider, BillMeta, Purchase
    now = datetime.now(timezone.utc).replace(day=15, hour=0, minute=0, second=0, microsecond=0)
    target = now - relativedelta(months=months_ago)
    purchase_date = target.replace(tzinfo=None)  # naïve, matches DB convention
    with app.app_context():
        from src.backend.create_flask_application import db_session_factory
        session = db_session_factory()
        try:
            provider = BillProvider(name=provider_name, canonical_name=provider_name, is_active=True)
            session.add(provider)
            session.flush()
            purchase = Purchase(
                date=purchase_date,
                description=provider_name,
                total_amount=amount,
                account_id=1,
            )
            session.add(purchase)
            session.flush()
            meta = BillMeta(purchase_id=purchase.id, provider_id=provider.id)
            session.add(meta)
            session.commit()
            return provider.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def test_list_includes_avg_and_latest_for_manual(client, app):
    """Manual obligations have null avg_6mo and latest_actual."""
    r = client.post("/floor-obligations/", json={"label": "Rent", "expected_monthly_amount": 1200})
    assert r.status_code == 201
    r2 = client.get("/floor-obligations/")
    assert r2.status_code == 200
    obs = r2.get_json()["obligations"]
    rent = next(o for o in obs if o["label"] == "Rent")
    assert rent["avg_6mo"] is None
    assert rent["latest_actual"] is None


def test_list_includes_avg_and_latest_for_bill_provider(client, app):
    """Bill-linked obligations surface avg_6mo and latest_actual from purchase history."""
    provider_id = _create_provider_and_purchase(app, "TestElectric", 100.0, 1)
    _create_provider_and_purchase  # already imported; re-use same provider is not needed
    # Add purchases for months 2 and 3 ago via second call (different provider_name to get new provider)
    # Instead: create obligation linked to provider_id, then check avg/latest
    with app.app_context():
        from src.backend.create_flask_application import db_session_factory
        from src.backend.initialize_database_schema import FloorObligation
        session = db_session_factory()
        ob = FloorObligation(label="TestElectric", expected_monthly_amount=95, is_active=True, bill_provider_id=provider_id)
        session.add(ob)
        session.commit()
        session.close()
    r = client.get("/floor-obligations/")
    assert r.status_code == 200
    obs = r.get_json()["obligations"]
    te = next(o for o in obs if o["label"] == "TestElectric")
    assert te["avg_6mo"] == 100.0
    assert te["latest_actual"] == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_floor_obligations.py::test_list_includes_avg_and_latest_for_manual tests/test_floor_obligations.py::test_list_includes_avg_and_latest_for_bill_provider -v 2>&1 | tail -20
```

Expected: FAIL (KeyError or AssertionError — `avg_6mo` not in response)

- [ ] **Step 3: Implement `_compute_history()` and enrich `_serialize()` + `list_obligations()`**

Replace the top of `src/backend/handle_floor_obligations.py` (keep existing imports, add datetime):

Update `_serialize()` signature and body:

```python
def _serialize(ob, avg_6mo=None, latest_actual=None) -> dict:
    return {
        "id": ob.id,
        "label": ob.label,
        "expected_monthly_amount": ob.expected_monthly_amount,
        "is_active": ob.is_active,
        "bill_provider_id": ob.bill_provider_id,
        "source": "bill_provider" if ob.bill_provider_id else "manual",
        "created_at": ob.created_at.isoformat() if ob.created_at else None,
        "updated_at": ob.updated_at.isoformat() if ob.updated_at else None,
        "avg_6mo": avg_6mo,
        "latest_actual": latest_actual,
    }
```

Add `_compute_history()` after `_summary_row`:

```python
def _compute_history(session, provider_id):
    """Return (avg_6mo, latest_actual) from last 6 complete calendar months (naïve datetimes)."""
    from datetime import datetime, timezone
    from src.backend.initialize_database_schema import BillMeta, Purchase
    now = datetime.now(timezone.utc)
    window_end = datetime(now.year, now.month, 1)  # first of this month (exclusive)
    if now.month <= 6:
        window_start = datetime(now.year - 1, now.month + 6, 1)
    else:
        window_start = datetime(now.year, now.month - 6, 1)

    rows = (
        session.query(Purchase)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
        .filter(
            BillMeta.provider_id == provider_id,
            Purchase.date >= window_start,
            Purchase.date < window_end,
        )
        .all()
    )
    if not rows:
        return None, None

    # Group by calendar month
    by_month: dict = {}
    for p in rows:
        key = (p.date.year, p.date.month)
        by_month[key] = by_month.get(key, 0.0) + float(p.total_amount or 0)

    monthly_totals = list(by_month.values())
    avg_6mo = round(sum(monthly_totals) / len(monthly_totals), 2)

    # latest_actual = sum of purchases in the most recent month present
    latest_key = max(by_month.keys())
    latest_actual = round(by_month[latest_key], 2)
    return avg_6mo, latest_actual
```

Update `list_obligations()`:

```python
@floor_obligations_bp.route("/", methods=["GET"])
@require_auth
def list_obligations():
    from src.backend.initialize_database_schema import FloorObligation
    rows = (
        g.db_session.query(FloorObligation)
        .order_by(FloorObligation.is_active.desc(), FloorObligation.label)
        .all()
    )
    result = []
    for r in rows:
        if r.bill_provider_id is not None:
            avg_6mo, latest_actual = _compute_history(g.db_session, r.bill_provider_id)
        else:
            avg_6mo, latest_actual = None, None
        result.append(_serialize(r, avg_6mo=avg_6mo, latest_actual=latest_actual))
    return jsonify({"obligations": result}), 200
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py -v 2>&1 | tail -20
```

Expected: All tests PASS (10 total)

- [ ] **Step 5: Commit**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && git add src/backend/handle_floor_obligations.py tests/test_floor_obligations.py && git commit -m "feat(floor-v2): _compute_history + avg_6mo/latest_actual in list response"
```

---

### Task 2: Backend — `GET /floor-obligations/available` endpoint

**Files:**
- Modify: `src/backend/handle_floor_obligations.py`
- Test: `tests/test_floor_obligations.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_floor_obligations.py`:

```python
def test_available_returns_unlinked_providers(client, app):
    """Providers with no active FloorObligation appear in /available."""
    provider_id = _create_provider_and_purchase(app, "AvailProv", 75.0, 1)
    r = client.get("/floor-obligations/available")
    assert r.status_code == 200
    available = r.get_json()["available"]
    ids = [a["bill_provider_id"] for a in available]
    assert provider_id in ids
    entry = next(a for a in available if a["bill_provider_id"] == provider_id)
    assert entry["avg_6mo"] == 75.0
    assert entry["latest_actual"] == 75.0
    assert "label" in entry


def test_available_excludes_active_floor_item(client, app):
    """Provider linked to an active FloorObligation does NOT appear in /available."""
    provider_id = _create_provider_and_purchase(app, "ActiveProv", 50.0, 1)
    client.post("/floor-obligations/", json={
        "label": "ActiveProv",
        "expected_monthly_amount": 50,
        "bill_provider_id": provider_id,
    })
    r = client.get("/floor-obligations/available")
    assert r.status_code == 200
    ids = [a["bill_provider_id"] for a in r.get_json()["available"]]
    assert provider_id not in ids


def test_available_includes_inactive_floor_item_with_ob_id(client, app):
    """Provider with inactive FloorObligation appears in /available with existing_obligation_id."""
    provider_id = _create_provider_and_purchase(app, "InactiveProv", 60.0, 2)
    cr = client.post("/floor-obligations/", json={
        "label": "InactiveProv",
        "expected_monthly_amount": 60,
        "bill_provider_id": provider_id,
    })
    ob_id = cr.get_json()["obligation"]["id"]
    client.patch(f"/floor-obligations/{ob_id}", json={"is_active": False})
    r = client.get("/floor-obligations/available")
    assert r.status_code == 200
    available = r.get_json()["available"]
    entry = next((a for a in available if a["bill_provider_id"] == provider_id), None)
    assert entry is not None
    assert entry["existing_obligation_id"] == ob_id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py::test_available_returns_unlinked_providers tests/test_floor_obligations.py::test_available_excludes_active_floor_item tests/test_floor_obligations.py::test_available_includes_inactive_floor_item_with_ob_id -v 2>&1 | tail -20
```

Expected: FAIL (404 — route not found)

- [ ] **Step 3: Implement `list_available()` route**

Add after `delete_obligation` in `src/backend/handle_floor_obligations.py`:

```python
@floor_obligations_bp.route("/available", methods=["GET"])
@require_auth
def list_available():
    """Bill providers that have no active FloorObligation."""
    from src.backend.initialize_database_schema import BillProvider, FloorObligation

    # provider_ids that are currently active on the floor
    active_provider_ids = {
        row.bill_provider_id
        for row in g.db_session.query(FloorObligation)
        .filter(FloorObligation.is_active == True, FloorObligation.bill_provider_id.isnot(None))
        .all()
    }

    # inactive floor rows keyed by provider_id (for reactivation)
    inactive_by_provider = {
        row.bill_provider_id: row.id
        for row in g.db_session.query(FloorObligation)
        .filter(FloorObligation.is_active == False, FloorObligation.bill_provider_id.isnot(None))
        .all()
    }

    providers = (
        g.db_session.query(BillProvider)
        .filter(BillProvider.is_active == True)
        .order_by(BillProvider.canonical_name)
        .all()
    )

    result = []
    for p in providers:
        if p.id in active_provider_ids:
            continue
        avg_6mo, latest_actual = _compute_history(g.db_session, p.id)
        entry = {
            "bill_provider_id": p.id,
            "label": p.canonical_name or p.name,
            "avg_6mo": avg_6mo,
            "latest_actual": latest_actual,
        }
        if p.id in inactive_by_provider:
            entry["existing_obligation_id"] = inactive_by_provider[p.id]
        result.append(entry)

    return jsonify({"available": result}), 200
```

- [ ] **Step 4: Run all tests**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py -v 2>&1 | tail -25
```

Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && git add src/backend/handle_floor_obligations.py tests/test_floor_obligations.py && git commit -m "feat(floor-v2): GET /floor-obligations/available endpoint"
```

---

### Task 3: Frontend — Tabbed Selected/Available panel

**Files:**
- Modify: `src/frontend/index.html` (lines 39268-39362 replaced; CSS added; two dead functions removed)

- [ ] **Step 1: Add tab CSS**

Find the `.floor-table` CSS block (around line 1516). After the closing `}` of that block, insert:

```css
.floor-tabs { display:flex; gap:0; margin-bottom:12px; }
.floor-tab-btn { padding:5px 16px; border:1px solid #444; background:#2c2c2e; color:#aaa; cursor:pointer; font-size:0.82rem; }
.floor-tab-btn:first-child { border-radius:4px 0 0 4px; }
.floor-tab-btn:last-child { border-radius:0 4px 4px 0; }
.floor-tab-btn.active { background:#3b82f6; color:#fff; border-color:#3b82f6; }
.floor-available-row td { color:#ccc; }
.floor-add-inline { display:flex; gap:6px; align-items:center; }
.floor-add-inline input { padding:3px 6px; border-radius:4px; border:1px solid #444; background:#1c1c1e; color:#fff; font-size:0.8rem; width:80px; }
```

- [ ] **Step 2: Replace the floor obligations JS block**

The block to replace starts at `function loadFloorObligations()` (around line 39268) and ends just before `function loadFloorWidget()` (around line 39362).

Replace the entire `loadFloorObligations` … `syncFloorFromBillProviders` block with:

```javascript
function loadFloorObligations() {
  api('/floor-obligations/').then(data => {
    _renderFloorTabPanel(data.obligations || [], window._floorActiveTab || 'selected');
  });
}

function _renderFloorTabPanel(obligations, activeTab) {
  window._floorObligations = obligations;
  window._floorActiveTab = activeTab;
  const selectedCount = obligations.filter(o => o.is_active).length;
  const section = document.getElementById('floor-obligations-section');
  if (!section) return;

  const wrap = section.querySelector('.floor-obligations-wrap') || section;

  // Fetch available count for tab label
  api('/floor-obligations/available').then(avData => {
    const available = avData.available || [];
    wrap.innerHTML = `
      <div class="floor-tabs">
        <button class="floor-tab-btn ${activeTab==='selected'?'active':''}" onclick="showFloorTab('selected')">Selected (${selectedCount})</button>
        <button class="floor-tab-btn ${activeTab==='available'?'active':''}" onclick="showFloorTab('available')">Available (${available.length})</button>
      </div>
      <div id="floor-tab-content"></div>
    `;
    if (activeTab === 'selected') {
      _renderSelectedTab(obligations);
    } else {
      _renderAvailableTab(available);
    }
  });
}

function showFloorTab(tab) {
  window._floorActiveTab = tab;
  if (tab === 'selected') {
    _renderSelectedTab(window._floorObligations || []);
    document.querySelectorAll('.floor-tab-btn').forEach((b,i) => b.classList.toggle('active', i===0));
  } else {
    api('/floor-obligations/available').then(d => {
      _renderAvailableTab(d.available || []);
      document.querySelectorAll('.floor-tab-btn').forEach((b,i) => b.classList.toggle('active', i===1));
    });
  }
}

function _renderSelectedTab(obligations) {
  const active = obligations.filter(o => o.is_active);
  const content = document.getElementById('floor-tab-content');
  if (!content) return;

  const rows = active.map(ob => {
    const avg = ob.avg_6mo != null ? `<span style="color:#888">${formatMoney(ob.avg_6mo)}</span>` : `<span style="color:#555">—</span>`;
    const latest = ob.latest_actual != null ? `<span style="color:#888">${formatMoney(ob.latest_actual)}</span>` : `<span style="color:#555">—</span>`;
    const source = ob.source === 'bill_provider'
      ? `<span class="badge badge-blue">Bills</span>`
      : `<span class="badge badge-gray">Manual</span>`;
    const action = ob.source === 'bill_provider'
      ? `<button class="btn-sm btn-outline" onclick="removeFloorObligation(${ob.id})">Remove</button>`
      : `<button class="btn-sm btn-danger-outline" onclick="deleteFloorObligation(${ob.id})">&#128465;</button>`;
    return `<tr>
      <td style="padding:5px 8px">${escHtml(ob.label)}</td>
      <td style="padding:5px 8px;text-align:right">
        <span class="floor-amount" data-id="${ob.id}" onclick="saveFloorObligationAmount(${ob.id},this)" title="Click to edit">${formatMoney(ob.expected_monthly_amount)}</span>
      </td>
      <td style="padding:5px 8px;text-align:right">${avg}</td>
      <td style="padding:5px 8px;text-align:right">${latest}</td>
      <td style="padding:5px 8px;text-align:center">${source}</td>
      <td style="padding:5px 8px">${action}</td>
    </tr>`;
  }).join('');

  content.innerHTML = `
    <table class="floor-table" style="width:100%">
      <thead><tr>
        <th style="text-align:left;padding:5px 8px">Name</th>
        <th style="text-align:right;padding:5px 8px">Expected/mo</th>
        <th style="text-align:right;padding:5px 8px">Avg (6mo)</th>
        <th style="text-align:right;padding:5px 8px">Latest</th>
        <th style="text-align:center;padding:5px 8px">Source</th>
        <th style="padding:5px 8px"></th>
      </tr></thead>
      <tbody>${rows || '<tr><td colspan="6" style="color:#555;padding:10px 8px">No items on floor</td></tr>'}</tbody>
    </table>
    <div style="margin-top:14px">
      <div style="font-size:0.8rem;color:#888;margin-bottom:6px">Add manual item</div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="new-floor-label" placeholder="Label" style="padding:5px 8px;border-radius:4px;border:1px solid #444;background:#1c1c1e;color:#fff;font-size:0.82rem;width:140px">
        <input id="new-floor-amount" type="number" placeholder="$/mo" style="padding:5px 8px;border-radius:4px;border:1px solid #444;background:#1c1c1e;color:#fff;font-size:0.82rem;width:80px">
        <button class="btn-sm btn-primary" onclick="addFloorObligation()">+ Add</button>
      </div>
    </div>
  `;
}

function _renderAvailableTab(available) {
  const content = document.getElementById('floor-tab-content');
  if (!content) return;

  const rows = available.map(item => {
    const avg = item.avg_6mo != null ? formatMoney(item.avg_6mo) : '—';
    const latest = item.latest_actual != null ? formatMoney(item.latest_actual) : '—';
    const prefill = item.avg_6mo != null ? item.avg_6mo.toFixed(2) : '';
    const obId = item.existing_obligation_id ? `data-ob-id="${item.existing_obligation_id}"` : '';
    return `<tr class="floor-available-row" id="avail-row-${item.bill_provider_id}">
      <td style="padding:5px 8px">${escHtml(item.label)}</td>
      <td style="padding:5px 8px;text-align:right;color:#888">${avg}</td>
      <td style="padding:5px 8px;text-align:right;color:#888">${latest}</td>
      <td style="padding:5px 8px" id="avail-action-${item.bill_provider_id}">
        <button class="btn-sm btn-outline-blue"
          onclick="showAddFromAvailable(${item.bill_provider_id}, ${JSON.stringify(escHtml(item.label))}, '${prefill}', ${item.existing_obligation_id || 'null'})">
          + Add
        </button>
      </td>
    </tr>`;
  }).join('');

  content.innerHTML = `
    <table class="floor-table" style="width:100%">
      <thead><tr>
        <th style="text-align:left;padding:5px 8px">Name</th>
        <th style="text-align:right;padding:5px 8px">Avg (6mo)</th>
        <th style="text-align:right;padding:5px 8px">Latest</th>
        <th style="padding:5px 8px"></th>
      </tr></thead>
      <tbody>${rows || '<tr><td colspan="4" style="color:#555;padding:10px 8px">All bill providers are on your floor</td></tr>'}</tbody>
    </table>
  `;
}

function showAddFromAvailable(providerId, label, prefillAmount, existingObId) {
  const cell = document.getElementById(`avail-action-${providerId}`);
  if (!cell) return;
  cell.innerHTML = `
    <div class="floor-add-inline">
      <input id="avail-amt-${providerId}" type="number" value="${escHtml(prefillAmount)}" placeholder="$/mo" style="width:80px">
      <button class="btn-sm btn-primary" onclick="addFromAvailable(${providerId}, ${JSON.stringify(label)}, ${existingObId || 'null'})">Save</button>
      <button class="btn-sm btn-outline" onclick="loadFloorObligations()">Cancel</button>
    </div>
  `;
  const inp = document.getElementById(`avail-amt-${providerId}`);
  if (inp) inp.focus();
}

function addFromAvailable(providerId, label, existingObId) {
  const inp = document.getElementById(`avail-amt-${providerId}`);
  const amount = parseFloat(inp ? inp.value : 0);
  if (isNaN(amount) || amount < 0) { toast('Enter a valid amount', 'error'); return; }
  if (existingObId) {
    api(`/floor-obligations/${existingObId}`, { method: 'PATCH', body: JSON.stringify({ is_active: true, expected_monthly_amount: amount }) })
      .then(() => { toast('Added to floor', 'success'); loadFloorObligations(); })
      .catch(() => { toast('Failed to add', 'error'); loadFloorObligations(); });
  } else {
    api('/floor-obligations/', { method: 'POST', body: JSON.stringify({ label, expected_monthly_amount: amount, bill_provider_id: providerId }) })
      .then(() => { toast('Added to floor', 'success'); loadFloorObligations(); })
      .catch(() => { toast('Failed to add', 'error'); loadFloorObligations(); });
  }
}

function removeFloorObligation(obId) {
  api(`/floor-obligations/${obId}`, { method: 'PATCH', body: JSON.stringify({ is_active: false }) })
    .then(() => { toast('Removed from floor', 'success'); loadFloorObligations(); })
    .catch(() => { toast('Failed to remove', 'error'); loadFloorObligations(); });
}
```

Keep `saveFloorObligationAmount()`, `deleteFloorObligation()`, and `addFloorObligation()` unchanged.

- [ ] **Step 3: Verify no references to removed functions remain**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && grep -n "syncFloorFromBillProviders\|toggleFloorObligation" src/frontend/index.html
```

Expected: no output (both functions removed and no callers remain)

- [ ] **Step 4: Run backend tests (frontend has no automated tests)**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py -v 2>&1 | tail -20
```

Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && git add src/frontend/index.html && git commit -m "feat(floor-v2): tabbed Selected/Available panel with avg+latest columns"
```

---

## Done

All three tasks complete → run `superpowers:finishing-a-development-branch`.
