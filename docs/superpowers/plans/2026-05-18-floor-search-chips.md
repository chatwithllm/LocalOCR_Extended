# Floor Obligations — Search + Category Chips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a search box and dynamic category chips to both the Selected and Available tabs of the floor obligations panel so users can quickly filter long lists.

**Architecture:** Backend adds `provider_category` to both list and available responses (one new field, no schema change). Frontend adds a `_floorFilterControls()` helper that renders search + chips above each tab's table; `updateFloorSearch`/`updateFloorCategory` update global state and re-render only the current tab's content.

**Tech Stack:** Python/Flask/SQLAlchemy, vanilla JS (inline in index.html), pytest via `venv/bin/pytest`

---

## File Map

| File | Change |
|------|--------|
| `src/backend/handle_floor_obligations.py` | `_serialize()` + `list_obligations()` include `provider_category`; `list_available()` includes `provider_category` |
| `tests/test_floor_obligations.py` | 2 new tests asserting `provider_category` in responses |
| `src/frontend/index.html` | CSS for chips; filter state globals; `_floorFilterControls()`, `updateFloorSearch()`, `updateFloorCategory()`, `_reRenderCurrentFloorTab()`; update `_renderSelectedTab` and `_renderAvailableTab` to prepend controls and apply filters; reset filters in `showFloorTab()` |

---

### Task 1: Backend — `provider_category` in list and available responses

**Files:**
- Modify: `src/backend/handle_floor_obligations.py`
- Test: `tests/test_floor_obligations.py`

**Key schema facts:**
- `BillProvider.provider_category` is a `String(30)`, default `'other'`; values in prod: `'utility'`, `'subscription'`, `'other'`
- `FloorObligation` has no `provider_category` column — must be looked up from `BillProvider`
- Manual obligations (no `bill_provider_id`) → `provider_category: 'manual'`
- `g.db_session` = per-request SQLAlchemy session
- Existing passing tests: 14; do not break them

- [ ] **Step 1: Write failing tests**

Append to `tests/test_floor_obligations.py`:

```python
def test_list_includes_provider_category(client, app):
    """List response includes provider_category: 'manual' for manual rows, string for bill-linked."""
    # Manual obligation → 'manual'
    r = client.post("/floor-obligations/", json={"label": "RentCat", "expected_monthly_amount": 900})
    assert r.status_code == 201
    r2 = client.get("/floor-obligations/")
    assert r2.status_code == 200
    obs = r2.get_json()["obligations"]
    rent = next(o for o in obs if o["label"] == "RentCat")
    assert rent["provider_category"] == "manual"

    # Bill-linked obligation → inherits BillProvider.provider_category
    provider_id = _create_provider_and_purchase(app, "CatElec", 50.0, 1)
    # Set provider_category on the provider
    with app.app_context():
        from src.backend.initialize_database_schema import BillProvider, FloorObligation
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            p = session.query(BillProvider).filter_by(id=provider_id).first()
            p.provider_category = "utility"
            ob = FloorObligation(label="CatElec", expected_monthly_amount=50, is_active=True, bill_provider_id=provider_id)
            session.add(ob)
            session.commit()
        finally:
            session.close()
    r3 = client.get("/floor-obligations/")
    obs3 = r3.get_json()["obligations"]
    elec = next(o for o in obs3 if o["label"] == "CatElec")
    assert elec["provider_category"] == "utility"


def test_available_includes_provider_category(client, app):
    """/available response includes provider_category for each entry."""
    provider_id = _create_provider_and_purchase(app, "AvailCatProv", 40.0, 1)
    with app.app_context():
        from src.backend.initialize_database_schema import BillProvider
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            p = session.query(BillProvider).filter_by(id=provider_id).first()
            p.provider_category = "subscription"
            session.commit()
        finally:
            session.close()
    r = client.get("/floor-obligations/available")
    assert r.status_code == 200
    available = r.get_json()["available"]
    entry = next((a for a in available if a["bill_provider_id"] == provider_id), None)
    assert entry is not None
    assert entry["provider_category"] == "subscription"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_floor_obligations.py::test_list_includes_provider_category tests/test_floor_obligations.py::test_available_includes_provider_category -v 2>&1 | tail -15
```

Expected: FAIL — `provider_category` not in response

- [ ] **Step 3: Implement**

In `src/backend/handle_floor_obligations.py`, make these three changes:

**3a. Update `_serialize()`** to accept `provider_category=None`:

```python
def _serialize(ob, avg_6mo=None, latest_actual=None, provider_category=None) -> dict:
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
        "provider_category": provider_category if ob.bill_provider_id else "manual",
    }
```

**3b. Update `list_obligations()`** to batch-load providers and pass `provider_category`:

```python
@floor_obligations_bp.route("/", methods=["GET"])
@require_auth
def list_obligations():
    from src.backend.initialize_database_schema import FloorObligation, BillProvider
    rows = (
        g.db_session.query(FloorObligation)
        .order_by(FloorObligation.is_active.desc(), FloorObligation.label)
        .all()
    )
    # Batch-load provider categories to avoid N+1
    provider_ids = [r.bill_provider_id for r in rows if r.bill_provider_id is not None]
    providers = {}
    if provider_ids:
        providers = {
            p.id: p
            for p in g.db_session.query(BillProvider).filter(BillProvider.id.in_(provider_ids)).all()
        }
    result = []
    for r in rows:
        if r.bill_provider_id is not None:
            avg_6mo, latest_actual = _compute_history(g.db_session, r.bill_provider_id)
            prov = providers.get(r.bill_provider_id)
            provider_category = prov.provider_category if prov else "other"
        else:
            avg_6mo, latest_actual = None, None
            provider_category = None  # _serialize will set 'manual' for rows with no bill_provider_id
        result.append(_serialize(r, avg_6mo=avg_6mo, latest_actual=latest_actual, provider_category=provider_category))
    return jsonify({"obligations": result}), 200
```

**3c. Update `list_available()`** — add `"provider_category": p.provider_category` to each entry dict:

Find the entry-building block in `list_available()`:
```python
        entry = {
            "bill_provider_id": p.id,
            "label": p.canonical_name,
            "avg_6mo": avg_6mo,
            "latest_actual": latest_actual,
        }
```

Change to:
```python
        entry = {
            "bill_provider_id": p.id,
            "label": p.canonical_name,
            "avg_6mo": avg_6mo,
            "latest_actual": latest_actual,
            "provider_category": p.provider_category or "other",
        }
```

- [ ] **Step 4: Run all tests**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py -v 2>&1 | tail -20
```

Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && git add src/backend/handle_floor_obligations.py tests/test_floor_obligations.py && git commit -m "feat(floor-filter): provider_category in list + available responses"
```

---

### Task 2: Frontend — search box + category chips on both tabs

**Files:**
- Modify: `src/frontend/index.html`

**Approach:**
- Filter state: `window._floorSearch` (string), `window._floorCategoryFilter` (string, default `'all'`)
- `window._floorAvailableAll` caches the last-fetched available list so re-filtering doesn't need a network call
- `_floorFilterControls(items, categoryKey)` renders search input + chip buttons
- `_applyFloorFilters(items, labelKey, categoryKey)` returns the filtered subset
- `updateFloorSearch(val)` and `updateFloorCategory(cat)` update state and call `_reRenderCurrentFloorTab()`
- `_reRenderCurrentFloorTab()` re-renders only the current tab's content div and restores focus to search input
- `showFloorTab(tab)` resets both filter state vars before switching
- Category display names: `{ all: 'All', utility: 'Utility', subscription: 'Subscription', other: 'Other', manual: 'Manual' }`
- Chips only show categories present in the **full unfiltered** list (dynamic)

**CSS to add** (after the `.floor-add-inline input` rule, around line 1535 in the floor CSS block):

```css
      #floor-obligations-section .floor-chip { padding:3px 10px; border-radius:12px; border:1px solid var(--border,#444); background:transparent; color:var(--muted,#aaa); cursor:pointer; font-size:0.78rem; }
      #floor-obligations-section .floor-chip.active { background:var(--accent,#3b82f6); color:#fff; border-color:var(--accent,#3b82f6); }
      #floor-obligations-section .floor-search { padding:5px 10px; border-radius:6px; border:1px solid var(--border,#444); background:var(--surface2,#2c2c2e); color:var(--text,#fff); font-size:0.82rem; width:180px; }
```

- [ ] **Step 1: Locate exact insertion points**

Run:
```bash
grep -n "floor-add-inline input\|#floor-obligations-section .floor-tab-btn.active\|function showFloorTab\|function _renderSelectedTab\|function _renderAvailableTab\|function loadFloorObligations" src/frontend/index.html
```

Note the line numbers — you'll need them for precise edits.

- [ ] **Step 2: Add CSS**

Find the CSS block ending with:
```css
      #floor-obligations-section .floor-add-inline input { padding:3px 6px; border-radius:4px; border:1px solid var(--border,#444); background:var(--surface2,#2c2c2e); color:var(--text,#fff); font-size:0.8rem; width:80px; }
```

After that line, insert:
```css
      #floor-obligations-section .floor-chip { padding:3px 10px; border-radius:12px; border:1px solid var(--border,#444); background:transparent; color:var(--muted,#aaa); cursor:pointer; font-size:0.78rem; }
      #floor-obligations-section .floor-chip.active { background:var(--accent,#3b82f6); color:#fff; border-color:var(--accent,#3b82f6); }
      #floor-obligations-section .floor-search { padding:5px 10px; border-radius:6px; border:1px solid var(--border,#444); background:var(--surface2,#2c2c2e); color:var(--text,#fff); font-size:0.82rem; width:180px; }
```

- [ ] **Step 3: Add filter helper functions**

Find `function showFloorTab(tab)`. Insert the following four functions immediately before it:

```javascript
      function _floorFilterControls(items, categoryKey) {
        const catLabel = { all: 'All', utility: 'Utility', subscription: 'Subscription', other: 'Other', manual: 'Manual' };
        const currentCat = window._floorCategoryFilter || 'all';
        const currentSearch = window._floorSearch || '';
        // Derive distinct categories from the full (unfiltered) item list
        const seen = new Set();
        const cats = ['all'];
        items.forEach(function(item) {
          const c = item[categoryKey] || 'other';
          if (!seen.has(c)) { seen.add(c); cats.push(c); }
        });
        const chips = cats.map(function(c) {
          const active = c === currentCat;
          return '<button class="floor-chip' + (active ? ' active' : '') + '" onclick="updateFloorCategory(\'' + c + '\')">' + (catLabel[c] || c.charAt(0).toUpperCase() + c.slice(1)) + '</button>';
        }).join('');
        return '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">'
          + '<input id="floor-search-input" class="floor-search" type="text" placeholder="Search…" value="' + escHtml(currentSearch) + '" oninput="updateFloorSearch(this.value)">'
          + '<div style="display:flex;gap:5px;flex-wrap:wrap">' + chips + '</div>'
          + '</div>';
      }

      function _applyFloorFilters(items, labelKey, categoryKey) {
        const search = (window._floorSearch || '').toLowerCase().trim();
        const cat = window._floorCategoryFilter || 'all';
        return items.filter(function(item) {
          if (search && !((item[labelKey] || '').toLowerCase().includes(search))) return false;
          if (cat !== 'all' && (item[categoryKey] || 'other') !== cat) return false;
          return true;
        });
      }

      function updateFloorSearch(val) {
        window._floorSearch = val || '';
        _reRenderCurrentFloorTab();
      }

      function updateFloorCategory(cat) {
        window._floorCategoryFilter = cat || 'all';
        _reRenderCurrentFloorTab();
      }

      function _reRenderCurrentFloorTab() {
        if (window._floorActiveTab === 'selected') {
          _renderSelectedTab(window._floorObligations || []);
        } else {
          _renderAvailableTab(window._floorAvailableAll || []);
        }
        var inp = document.getElementById('floor-search-input');
        if (inp) { inp.focus(); var len = inp.value.length; inp.setSelectionRange(len, len); }
      }
```

- [ ] **Step 4: Update `showFloorTab` to reset filters on tab switch**

Find `function showFloorTab(tab)`. At the very start of the function body (before `window._floorActiveTab = tab;`), insert:

```javascript
        window._floorSearch = '';
        window._floorCategoryFilter = 'all';
```

So the full function becomes:

```javascript
      function showFloorTab(tab) {
        window._floorSearch = '';
        window._floorCategoryFilter = 'all';
        window._floorActiveTab = tab;
        document.querySelectorAll('#floor-obligations-section .floor-tab-btn').forEach(function(b, i) {
          b.classList.toggle('active', (tab === 'selected' && i === 0) || (tab === 'available' && i === 1));
        });
        if (tab === 'selected') {
          _renderSelectedTab(window._floorObligations || []);
        } else {
          api('/floor-obligations/available').then(function(r) {
            return r.ok ? r.json().catch(function() { return null; }) : null;
          }).then(function(d) {
            _renderAvailableTab(d ? (d.available || []) : null);
          });
        }
      }
```

- [ ] **Step 5: Update `_renderSelectedTab` to prepend filter controls and filter items**

Find `function _renderSelectedTab(obligations)`. Replace it entirely:

```javascript
      function _renderSelectedTab(obligations) {
        const active = obligations.filter(function(o) { return o.is_active; });
        const content = document.getElementById('floor-tab-content');
        if (!content) return;

        const filtered = _applyFloorFilters(active, 'label', 'provider_category');

        const rows = filtered.map(function(ob) {
          const avg = ob.avg_6mo != null
            ? '<span style="color:var(--muted,#888)">' + formatMoney(ob.avg_6mo) + '</span>'
            : '<span style="color:var(--border,#555)">—</span>';
          const latest = ob.latest_actual != null
            ? '<span style="color:var(--muted,#888)">' + formatMoney(ob.latest_actual) + '</span>'
            : '<span style="color:var(--border,#555)">—</span>';
          const src = ob.source === 'bill_provider'
            ? '<span style="font-size:0.75rem;color:var(--muted,#aaa)">Bills</span>'
            : '<span style="font-size:0.75rem;color:var(--info,#60a5fa)">Manual</span>';
          const action = ob.source === 'bill_provider'
            ? '<button class="btn btn-ghost btn-sm" onclick="removeFloorObligation(' + ob.id + ')" style="font-size:0.78rem">Remove</button>'
            : '<button class="btn btn-ghost btn-sm" onclick="deleteFloorObligation(' + ob.id + ')" style="color:var(--danger,#ef4444);padding:2px 6px">&#xd7;</button>';
          const amt = '<input type="number" step="0.01" min="0" value="' + ob.expected_monthly_amount + '" style="width:90px;padding:4px 6px;border-radius:5px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem" onblur="saveFloorObligationAmount(' + ob.id + ', this.value)" title="Expected $/mo">';
          return '<tr>'
            + '<td style="padding:7px 10px">' + escHtml(ob.label) + '</td>'
            + '<td style="padding:7px 10px">' + amt + '</td>'
            + '<td style="padding:7px 10px;text-align:right">' + avg + '</td>'
            + '<td style="padding:7px 10px;text-align:right">' + latest + '</td>'
            + '<td style="padding:7px 10px;text-align:center">' + src + '</td>'
            + '<td style="padding:7px 10px;text-align:right">' + action + '</td>'
            + '</tr>';
        }).join('');

        const noResults = filtered.length === 0 && active.length > 0
          ? '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">No items match your filter.</p>'
          : '';

        content.innerHTML = _floorFilterControls(active, 'provider_category')
          + (active.length === 0
            ? '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">No obligations on floor yet. Add one below or pick from Available.</p>'
            : noResults || '<table class="floor-table"><thead><tr>'
              + '<th>Name</th><th>Expected/mo</th>'
              + '<th style="text-align:right">Avg (6mo)</th>'
              + '<th style="text-align:right">Latest</th>'
              + '<th style="text-align:center">Source</th>'
              + '<th></th>'
              + '</tr></thead><tbody>' + rows + '</tbody></table>')
          + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px">'
          + '<input id="floor-new-label" type="text" placeholder="Label (e.g. Car Loan)" style="padding:5px 8px;border-radius:6px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem;width:160px">'
          + '<input id="floor-new-amount" type="number" step="0.01" min="0" placeholder="$/mo" style="width:80px;padding:5px 8px;border-radius:6px;border:1px solid var(--border,#444);background:var(--surface2,#2c2c2e);color:var(--text,#fff);font-size:0.84rem">'
          + '<button class="btn btn-primary btn-sm" onclick="addFloorObligation()">&#xff0b; Add</button>'
          + '</div>';
      }
```

- [ ] **Step 6: Update `_renderAvailableTab` to cache data, prepend filter controls, and filter items**

Find `function _renderAvailableTab(available)`. Replace it entirely:

```javascript
      function _renderAvailableTab(available) {
        const content = document.getElementById('floor-tab-content');
        if (!content) return;

        if (available === null) {
          content.innerHTML = '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">Could not load available providers.</p>';
          return;
        }

        // Cache for re-filtering without network
        window._floorAvailableAll = available;

        const filtered = _applyFloorFilters(available, 'label', 'provider_category');

        const rows = filtered.map(function(item) {
          const avg = item.avg_6mo != null ? formatMoney(item.avg_6mo) : '—';
          const latest = item.latest_actual != null ? formatMoney(item.latest_actual) : '—';
          const prefill = item.avg_6mo != null ? parseFloat(item.avg_6mo).toFixed(2) : '';
          const obId = item.existing_obligation_id != null ? item.existing_obligation_id : 'null';
          return '<tr id="avail-row-' + item.bill_provider_id + '">'
            + '<td style="padding:7px 10px">' + escHtml(item.label) + '</td>'
            + '<td style="padding:7px 10px;text-align:right;color:var(--muted,#aaa)">' + avg + '</td>'
            + '<td style="padding:7px 10px;text-align:right;color:var(--muted,#aaa)">' + latest + '</td>'
            + '<td style="padding:7px 10px;text-align:right" id="avail-action-' + item.bill_provider_id + '">'
            + '<button class="btn btn-ghost btn-sm" style="font-size:0.78rem;color:var(--accent,#3b82f6)" data-label="' + escHtml(item.label) + '" data-prefill="' + escHtml(prefill) + '" data-ob-id="' + obId + '" onclick="showAddFromAvailable(' + item.bill_provider_id + ', this)">+ Add</button>'
            + '</td>'
            + '</tr>';
        }).join('');

        const noResults = filtered.length === 0 && available.length > 0
          ? '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">No items match your filter.</p>'
          : '';

        content.innerHTML = _floorFilterControls(available, 'provider_category')
          + (available.length === 0
            ? '<p style="color:var(--muted,#aaa);font-size:0.85rem;padding:8px 0">All bill providers are already on your floor.</p>'
            : noResults || '<table class="floor-table"><thead><tr>'
              + '<th>Name</th>'
              + '<th style="text-align:right">Avg (6mo)</th>'
              + '<th style="text-align:right">Latest</th>'
              + '<th></th>'
              + '</tr></thead><tbody>' + rows + '</tbody></table>');
      }
```

- [ ] **Step 7: Verify no regressions**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && venv/bin/pytest tests/test_floor_obligations.py -v 2>&1 | tail -15
```

Expected: All 16 tests PASS

Also verify the dead-reference check:
```bash
grep -c "syncFloorFromBillProviders\|toggleFloorObligation" src/frontend/index.html
```
Expected: 0

- [ ] **Step 8: Commit**

```bash
cd /Users/assistant/.gemini/antigravity/LocalOCR_Extended && git add src/frontend/index.html && git commit -m "feat(floor-filter): search box + category chips on Selected and Available tabs"
```

---

## Done

Both tasks complete → run `superpowers:finishing-a-development-branch`.
