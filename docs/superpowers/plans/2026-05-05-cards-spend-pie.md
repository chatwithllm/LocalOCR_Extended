# Cards Spend-by-Category Pie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-05-cards-spend-pie-design.md`

**Goal:** Add a per-credit-account `categories_mtd` array to `GET /plaid/cards-overview` and render an SVG donut + legend + account filter inside the existing Card Usage panel on the Accounts page.

**Architecture:** Server adds one extra GROUP BY query in the existing `cards_overview()` route, attaches a sorted `[{category, amount_cents}]` array per credit account. Frontend caches the full response, builds a filter `<select>`, aggregates client-side on filter change, renders an inline SVG donut + legend table — same pattern as `renderSpendingTrendsChart`. No new endpoint, no new fetch, no chart library.

**Tech Stack:** Python 3.14 / Flask / SQLAlchemy; vanilla JS frontend in `src/frontend/index.html`; pytest. Inline-SVG charts (project pattern, no external chart lib).

---

## File Structure

**Modified:**
- `src/backend/plaid_integration.py` — add a category aggregation query to `cards_overview()`; attach `categories_mtd` to each account dict before grouping
- `src/frontend/index.html` — add new sub-panel HTML inside `#card-usage-card`; add CSS for donut + legend; add JS functions for aggregation, donut SVG, legend, filter handling
- `tests/test_cards_overview.py` — append five new tests for category behavior

No new files.

---

## Task 1: Backend — `categories_mtd` aggregation + serialization

**Files:**
- Modify: `src/backend/plaid_integration.py` (the `cards_overview()` route — currently around lines 1773-1888 after recent edits)
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test (basic case)**

Append to `tests/test_cards_overview.py`:

```python
def test_cards_overview_categories_basic(app):
    """Per-account categories_mtd: debits only, sorted by amount desc, refund excluded."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="cat_basic@test.local", name="Cat Basic")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_basic", inst_id="ins_cat_basic")
        _seed_credit_account(session, user_id, item.id)

        today_iso = date_cls.today().isoformat()
        from src.backend.initialize_database_schema import PlaidStagedTransaction
        # Use direct seeding to set plaid_category_primary
        for txn_id, amount, cat in [
            ("c1", 50.00, "FOOD_AND_DRINK"),
            ("c2", 30.00, "TRANSPORTATION"),
            ("c3", -10.00, "FOOD_AND_DRINK"),  # refund — excluded
        ]:
            session.add(PlaidStagedTransaction(
                plaid_item_id=item.id, user_id=user_id,
                plaid_transaction_id=txn_id,
                plaid_account_id="cc_1",
                amount=amount,
                transaction_date=date_cls.fromisoformat(today_iso),
                plaid_category_primary=cat,
                status="ready_to_import",
                raw_json="{}",
            ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body

    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [
        {"category": "FOOD_AND_DRINK", "amount_cents": 5000},
        {"category": "TRANSPORTATION", "amount_cents": 3000},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_categories_basic -v
```

Expected: FAIL — `KeyError: 'categories_mtd'` (route doesn't emit the field yet).

- [ ] **Step 3: Add the category aggregation query to the route**

Open `src/backend/plaid_integration.py`. Inside `cards_overview()`, locate the `spend_q` block that builds `spend_map` (around lines 1810-1830). Immediately after that block, add a parallel query for category aggregation:

```python
    # Per-account category breakdown — debits only (refunds excluded from pie)
    cat_q = (
        session.query(
            PlaidStagedTransaction.plaid_account_id,
            PlaidStagedTransaction.plaid_category_primary,
            func.sum(PlaidStagedTransaction.amount).label("amt"),
        )
        .filter(PlaidStagedTransaction.transaction_date >= month_start.date())
        .filter(PlaidStagedTransaction.status != "dismissed")
        .filter(PlaidStagedTransaction.amount > 0)
        .group_by(
            PlaidStagedTransaction.plaid_account_id,
            PlaidStagedTransaction.plaid_category_primary,
        )
    )
    if visible_ids is not None:
        if not visible_ids:
            cat_q = cat_q.filter(sa_false())
        else:
            cat_q = cat_q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
    cat_rows = cat_q.all()

    # Group: { plaid_account_id: [(category_or_UNCATEGORIZED, amount_cents), ...] }
    cat_map: dict[str, list[dict]] = {}
    for r in cat_rows:
        cat = r.plaid_category_primary or "UNCATEGORIZED"
        amt_cents = int(round(float(r.amt or 0) * 100))
        if amt_cents <= 0:
            continue
        cat_map.setdefault(r.plaid_account_id, []).append({
            "category": cat,
            "amount_cents": amt_cents,
        })
    # Sort each account's categories by amount desc
    for slices in cat_map.values():
        slices.sort(key=lambda s: s["amount_cents"], reverse=True)
```

If `sa_false` is not already imported at the top of the file, add it. Look for existing imports of `sa_false` (the existing `list_accounts` uses it). If imported as e.g. `from sqlalchemy.sql import false as sa_false`, reuse that.

- [ ] **Step 4: Inject `categories_mtd` into each account dict**

In the same function, find the per-account loop (around lines 1832-1855):

```python
    for a in accounts:
        base = _serialize_plaid_account(a)
        bucket = spend_map.get(a.plaid_account_id, ...)
        ...
```

Right after `base["currency"] = a.balance_iso_currency_code` (or whichever line is the last addition before group bucketing), add:

```python
        if a.account_type == "credit":
            base["categories_mtd"] = cat_map.get(a.plaid_account_id, [])
        else:
            base["categories_mtd"] = []
```

- [ ] **Step 5: Run the basic test**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_categories_basic -v
```

Expected: PASS.

- [ ] **Step 6: Run all cards-overview tests for regression check**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 11 passed (10 prior + new basic test).

- [ ] **Step 7: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): cards-overview emits per-account categories_mtd (debits, sorted desc)"
```

---

## Task 2: Backend edge cases — null bucket, dismissed, loan, visibility

**Files:**
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the four edge-case tests**

Append:

```python
def test_cards_overview_categories_null_bucket(app):
    """Null plaid_category_primary buckets as UNCATEGORIZED."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_id = _make_user(app, email="cat_null@test.local", name="Cat Null")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_null", inst_id="ins_cat_null")
        _seed_credit_account(session, user_id, item.id)
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cn1", plaid_account_id="cc_1",
            amount=42.00,
            transaction_date=date_cls.today(),
            plaid_category_primary=None,
            status="ready_to_import", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [{"category": "UNCATEGORIZED", "amount_cents": 4200}]


def test_cards_overview_categories_dismissed_excluded(app):
    """Dismissed txns must not contribute to categories_mtd."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_id = _make_user(app, email="cat_dis@test.local", name="Cat Dis")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_dis", inst_id="ins_cat_dis")
        _seed_credit_account(session, user_id, item.id)
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cd_keep", plaid_account_id="cc_1",
            amount=20.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="ready_to_import", raw_json="{}",
        ))
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cd_drop", plaid_account_id="cc_1",
            amount=999.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="dismissed", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [{"category": "FOOD_AND_DRINK", "amount_cents": 2000}]


def test_cards_overview_loans_have_empty_categories(app):
    """Loan accounts always emit categories_mtd: []."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_cat@test.local", name="Loan Cat")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cat", inst_id="ins_loan_cat")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_cat",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=18240000, balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["categories_mtd"] == []


def test_cards_overview_categories_visibility_filter(app):
    """User A's category data must not leak to user B."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_a = _make_user(app, email="cat_a@test.local", name="Cat A")
    user_b = _make_user(app, email="cat_b@test.local", name="Cat B")

    _, SF = _get_db()
    session = SF()
    try:
        item_a = _seed_plaid_item_simple(session, user_a, item_token="item_cat_a", inst_id="ins_cat_a")
        _seed_credit_account(session, user_a, item_a.id, plaid_account_id="cc_a")
        session.add(PlaidStagedTransaction(
            plaid_item_id=item_a.id, user_id=user_a,
            plaid_transaction_id="cv1", plaid_account_id="cc_a",
            amount=99.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="ready_to_import", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_b)
    assert status == 200
    assert body["groups"] == []  # user B sees nothing
```

- [ ] **Step 2: Run all four**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_categories_null_bucket \
       tests/test_cards_overview.py::test_cards_overview_categories_dismissed_excluded \
       tests/test_cards_overview.py::test_cards_overview_loans_have_empty_categories \
       tests/test_cards_overview.py::test_cards_overview_categories_visibility_filter -v
```

Expected: 4 passed.

- [ ] **Step 3: Run full file**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 15 passed (11 + 4).

- [ ] **Step 4: Commit**

```bash
git add tests/test_cards_overview.py
git commit -m "test(cards-overview): categories_mtd edge cases — null, dismissed, loans, visibility"
```

---

## Task 3: Frontend — sub-panel scaffold + CSS

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add the sub-panel HTML inside `#card-usage-card`**

Search `src/frontend/index.html` for `<!-- Panel 0 — Card Usage -->`. Inside the `<div class="card" id="card-usage-card">` block, locate the line containing `<div id="card-usage-banner"` and insert the new sub-panel **after** the banner div but **before** `<div id="card-usage-body">`:

```html
<div id="card-usage-pie-panel" class="card-usage-pie-panel" style="display:none">
  <div class="card-usage-pie-head">
    <span class="card-usage-pie-title">Spend by Category (this month)</span>
    <label class="card-usage-pie-filter">
      Filter:
      <select id="card-usage-pie-filter-select" onchange="_onCardUsageFilterChange(event)">
        <option value="all">All Cards</option>
      </select>
    </label>
  </div>
  <div id="card-usage-pie-body" class="card-usage-pie-body">
    <!-- donut + legend rendered by _renderCardUsagePie() -->
  </div>
</div>
```

- [ ] **Step 2: Append CSS for the sub-panel**

Find the existing `<style>` block that contains `.card-usage-summary` (added in the prior cards-overview phase). Append:

```css
.card-usage-pie-panel {
  background: var(--surface, #1c1c1e);
  border-radius: 12px;
  padding: 14px;
  margin: 16px 0 8px;
  border: 1px solid var(--border, #3a3a3c);
}
.card-usage-pie-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.card-usage-pie-title {
  font-weight: 600;
  font-size: 0.95rem;
}
.card-usage-pie-filter {
  font-size: 0.84rem;
  color: var(--muted, #888);
  display: flex;
  align-items: center;
  gap: 6px;
}
.card-usage-pie-filter select {
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--surface2, #2c2c2e);
  color: var(--text, #fff);
  border: 1px solid var(--border, #3a3a3c);
  font-size: 0.88rem;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}
.card-usage-pie-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 18px;
}
.card-usage-pie-body svg.donut { flex: 0 0 160px; }
.card-usage-pie-body .donut-legend {
  flex: 1 1 220px;
  min-width: 220px;
  font-size: 0.88rem;
}
.card-usage-pie-body .donut-legend table {
  width: 100%;
  border-collapse: collapse;
}
.card-usage-pie-body .donut-legend td {
  padding: 4px 6px;
  vertical-align: middle;
}
.card-usage-pie-body .donut-legend .swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 8px;
  vertical-align: middle;
}
.card-usage-pie-body .donut-legend .total-row td {
  border-top: 1px solid var(--border, #3a3a3c);
  font-weight: 600;
  padding-top: 8px;
  margin-top: 4px;
}
.card-usage-pie-body .donut-empty {
  flex: 1;
  color: var(--muted, #888);
  font-size: 0.92rem;
  text-align: center;
  padding: 20px 0;
}
```

- [ ] **Step 3: Smoke check (visual)**

Reload the dev frontend, navigate to Accounts. The `Spend by Category` panel should NOT show yet (`display:none` until JS reveals it). The existing Card Usage panel should still render normally.

If the dev server isn't running, just confirm the diff and that the sub-panel is between `card-usage-banner` and `card-usage-body`.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): card usage spend-by-category sub-panel scaffold + CSS"
```

---

## Task 4: Frontend — aggregation, donut, legend, filter wiring

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add helpers (aggregation + label + palette)**

Search `src/frontend/index.html` for `_drillIntoAccount`. Append the new functions **after** `_drillIntoAccount`:

```javascript
const __cardUsagePalette = ['#2e7d6b', '#0a84ff', '#ff9f0a', '#bf5af2', '#ff453a', '#34c759'];
const __cardUsageOtherColor = '#8e8e93';

function _categoryLabel(raw) {
  if (!raw) return "Uncategorized";
  if (raw === "UNCATEGORIZED") return "Uncategorized";
  // "FOOD_AND_DRINK" → "Food And Drink" → "Food & Drink" (basic)
  return raw
    .split("_")
    .map(w => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ")
    .replace(/\bAnd\b/g, "&");
}

function _aggregateCategories(scope, cache) {
  // Returns { slices: [{category, amount_cents, label, color}], totalCents }
  // Top 6 are sliced individually; remainder → "Other" (grey).
  if (!cache || !cache.groups) return { slices: [], totalCents: 0 };
  const credit = cache.groups.find(g => g.type === "credit_card");
  if (!credit) return { slices: [], totalCents: 0 };

  const accounts = scope === "all"
    ? credit.accounts
    : credit.accounts.filter(a => a.plaid_account_id === scope);

  // Sum per category (USD-only, matching parent panel rule)
  const byCat = new Map();
  accounts.forEach(a => {
    if ((a.balance_currency || "USD") !== "USD") return;
    (a.categories_mtd || []).forEach(c => {
      byCat.set(c.category, (byCat.get(c.category) || 0) + c.amount_cents);
    });
  });

  let entries = Array.from(byCat.entries())
    .map(([cat, cents]) => ({ category: cat, amount_cents: cents }))
    .sort((a, b) => b.amount_cents - a.amount_cents);

  const totalCents = entries.reduce((acc, e) => acc + e.amount_cents, 0);

  // Top 6 + Other
  let slices;
  if (entries.length > 6) {
    const top = entries.slice(0, 6);
    const restCents = entries.slice(6).reduce((acc, e) => acc + e.amount_cents, 0);
    slices = top.concat([{ category: "OTHER", amount_cents: restCents }]);
  } else {
    slices = entries;
  }

  // Attach label + color
  slices.forEach((s, i) => {
    s.label = s.category === "OTHER" ? "Other" : _categoryLabel(s.category);
    s.color = s.category === "OTHER"
      ? __cardUsageOtherColor
      : __cardUsagePalette[i % __cardUsagePalette.length];
  });

  return { slices, totalCents };
}
```

- [ ] **Step 2: Add the donut renderer (SVG)**

Append:

```javascript
function _renderCardUsageDonut(slices, totalCents) {
  // Returns an SVG element with arc paths for each slice.
  const SVG_NS = "http://www.w3.org/2000/svg";
  const size = 160, cx = size / 2, cy = size / 2;
  const outerR = 70, innerR = 42;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("viewBox", "0 0 " + size + " " + size);
  svg.classList.add("donut");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Spend by category donut chart");

  if (totalCents <= 0) return svg;

  // Single slice (100%) → draw a full ring
  if (slices.length === 1) {
    const ring = document.createElementNS(SVG_NS, "path");
    const d = [
      "M " + cx + " " + (cy - outerR),
      "A " + outerR + " " + outerR + " 0 1 1 " + cx + " " + (cy + outerR),
      "A " + outerR + " " + outerR + " 0 1 1 " + cx + " " + (cy - outerR),
      "M " + cx + " " + (cy - innerR),
      "A " + innerR + " " + innerR + " 0 1 0 " + cx + " " + (cy + innerR),
      "A " + innerR + " " + innerR + " 0 1 0 " + cx + " " + (cy - innerR),
      "Z"
    ].join(" ");
    ring.setAttribute("d", d);
    ring.setAttribute("fill", slices[0].color);
    ring.setAttribute("fill-rule", "evenodd");
    svg.appendChild(ring);
    return svg;
  }

  // Multi-slice
  let startAngle = -Math.PI / 2; // start at 12 o'clock
  slices.forEach(s => {
    const frac = s.amount_cents / totalCents;
    if (frac <= 0) return;
    const endAngle = startAngle + frac * 2 * Math.PI;
    const largeArc = frac > 0.5 ? 1 : 0;

    const x1 = cx + outerR * Math.cos(startAngle);
    const y1 = cy + outerR * Math.sin(startAngle);
    const x2 = cx + outerR * Math.cos(endAngle);
    const y2 = cy + outerR * Math.sin(endAngle);
    const x3 = cx + innerR * Math.cos(endAngle);
    const y3 = cy + innerR * Math.sin(endAngle);
    const x4 = cx + innerR * Math.cos(startAngle);
    const y4 = cy + innerR * Math.sin(startAngle);

    const path = document.createElementNS(SVG_NS, "path");
    const d = [
      "M " + x1 + " " + y1,
      "A " + outerR + " " + outerR + " 0 " + largeArc + " 1 " + x2 + " " + y2,
      "L " + x3 + " " + y3,
      "A " + innerR + " " + innerR + " 0 " + largeArc + " 0 " + x4 + " " + y4,
      "Z"
    ].join(" ");
    path.setAttribute("d", d);
    path.setAttribute("fill", s.color);
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = s.label + ": " + _fmtMoneyCents(s.amount_cents, "USD");
    path.appendChild(title);
    svg.appendChild(path);

    startAngle = endAngle;
  });
  return svg;
}
```

- [ ] **Step 3: Add the legend renderer**

Append:

```javascript
function _renderCardUsageLegend(slices, totalCents) {
  const wrap = document.createElement("div");
  wrap.className = "donut-legend";
  const table = document.createElement("table");
  slices.forEach(s => {
    const tr = document.createElement("tr");

    const tdName = document.createElement("td");
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = s.color;
    tdName.appendChild(sw);
    tdName.appendChild(document.createTextNode(s.label));
    tr.appendChild(tdName);

    const tdAmt = document.createElement("td");
    tdAmt.style.textAlign = "right";
    tdAmt.style.whiteSpace = "nowrap";
    tdAmt.textContent = _fmtMoneyCents(s.amount_cents, "USD");
    tr.appendChild(tdAmt);

    const tdPct = document.createElement("td");
    tdPct.style.textAlign = "right";
    tdPct.style.color = "var(--muted, #888)";
    const pct = totalCents > 0 ? Math.round((s.amount_cents / totalCents) * 100) : 0;
    tdPct.textContent = pct + "%";
    tr.appendChild(tdPct);

    table.appendChild(tr);
  });

  // Total row
  const totalTr = document.createElement("tr");
  totalTr.className = "total-row";
  const tdTLabel = document.createElement("td");
  tdTLabel.textContent = "Gross spend";
  const tdTAmt = document.createElement("td");
  tdTAmt.style.textAlign = "right";
  tdTAmt.style.whiteSpace = "nowrap";
  tdTAmt.textContent = _fmtMoneyCents(totalCents, "USD");
  const tdTPct = document.createElement("td");
  totalTr.appendChild(tdTLabel);
  totalTr.appendChild(tdTAmt);
  totalTr.appendChild(tdTPct);
  table.appendChild(totalTr);

  wrap.appendChild(table);
  return wrap;
}
```

- [ ] **Step 4: Add the panel renderer + filter handler**

Append:

```javascript
function _renderCardUsagePie(scope) {
  const panel = document.getElementById("card-usage-pie-panel");
  const body = document.getElementById("card-usage-pie-body");
  if (!panel || !body) return;

  const cache = __cardsOverviewCache;
  if (!cache) { panel.style.display = "none"; return; }

  const credit = (cache.groups || []).find(g => g.type === "credit_card");
  if (!credit || credit.accounts.length === 0) {
    panel.style.display = "none";
    return;
  }
  panel.style.display = "block";

  body.replaceChildren();

  const { slices, totalCents } = _aggregateCategories(scope, cache);

  if (totalCents <= 0 || slices.length === 0) {
    const empty = document.createElement("div");
    empty.className = "donut-empty";
    let label = "this month";
    if (scope !== "all") {
      const acct = credit.accounts.find(a => a.plaid_account_id === scope);
      if (acct) label = "on " + acct.name;
    }
    empty.textContent = "No spend " + label + ".";
    body.appendChild(empty);
    return;
  }

  body.appendChild(_renderCardUsageDonut(slices, totalCents));
  body.appendChild(_renderCardUsageLegend(slices, totalCents));
}

function _refreshCardUsageFilterOptions() {
  const sel = document.getElementById("card-usage-pie-filter-select");
  if (!sel) return;
  const cache = __cardsOverviewCache;
  const credit = cache && (cache.groups || []).find(g => g.type === "credit_card");
  const prev = sel.value || "all";

  sel.replaceChildren();
  const optAll = document.createElement("option");
  optAll.value = "all";
  optAll.textContent = "All Cards";
  sel.appendChild(optAll);

  if (credit) {
    credit.accounts.forEach(a => {
      const opt = document.createElement("option");
      opt.value = a.plaid_account_id;
      opt.textContent = "💳 " + (a.name || "Account") + " ····" + (a.mask || "");
      sel.appendChild(opt);
    });
  }

  // Restore previous selection if still valid; else fall back to "all"
  const valid = Array.from(sel.options).some(o => o.value === prev);
  sel.value = valid ? prev : "all";
}

function _onCardUsageFilterChange(e) {
  const scope = (e && e.target && e.target.value) || "all";
  _renderCardUsagePie(scope);
}
```

- [ ] **Step 5: Wire pie render into existing `renderCardsOverview`**

Find the existing `renderCardsOverview(data)` function. Locate the line that processes data.groups and appends to body (the `data.groups.forEach(group => {...})` loop). Immediately AFTER that loop block (before the final closing `}` of `renderCardsOverview`), add:

```javascript
  // Pie sub-panel inside the same card
  _refreshCardUsageFilterOptions();
  const sel = document.getElementById("card-usage-pie-filter-select");
  _renderCardUsagePie(sel ? sel.value : "all");
```

If `renderCardsOverview` returns early on the empty-state branch, the pie won't render either — which is correct (whole pie panel hidden when no credit accounts). Verify by inspection: the empty-state branch has its own `return` and never falls through to this added block.

- [ ] **Step 6: Smoke test in browser**

Reload the dev frontend. Navigate to Accounts. Confirm:

- If you have a credit card with at least one MTD debit: "Spend by Category (this month)" sub-panel appears between the summary block and the per-card list. Donut + legend visible. Filter shows "All Cards" + the card.
- Selecting the card from the filter re-renders donut + legend (visually identical here since it's the only card, but check console — no errors).
- If you have no credit accounts: pie panel hidden.
- If you have a credit card with zero MTD spend (or refunds only): donut hidden, message "No spend this month." or "No spend on <name>." in panel body. Filter still works.
- View page source / inspect a slice path → `<title>` shows category and amount on hover.
- Try a category-name with HTML chars (impossible from Plaid in practice, but verify by manually inserting into the cache via DevTools console: `__cardsOverviewCache.groups[0].accounts[0].categories_mtd.push({category: "<img>", amount_cents: 100}); _renderCardUsagePie("all")`) → renders literally as text.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): card usage spend-by-category — SVG donut + legend + filter"
```

---

## Task 5: Final verification + smoke checklist

- [ ] **Step 1: Run all cards-overview tests**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 15 passed.

- [ ] **Step 2: Regression check — all Plaid-related tests**

```bash
pytest tests/test_cards_overview.py tests/test_accounts_dashboard.py -v 2>&1 | tail -10
```

Expected: cards-overview all pass. Pre-existing failures `test_patch_item_*` and (under shared-DB run-order) `test_get_accounts_happy_path` may still appear — those are unrelated and predate this branch.

- [ ] **Step 3: Browser smoke checklist**

In a browser, log in as a user with at least one Plaid credit card linked. Navigate to **Accounts** and verify:

- [ ] "Spend by Category (this month)" sub-panel appears between the summary stats grid and the per-card list inside the same Card Usage card
- [ ] Filter dropdown defaults to "All Cards" + lists each linked card
- [ ] Donut renders with up to 6 colored slices + grey "Other" if 7+ categories
- [ ] Legend table shows category, amount, percentage, with a "Gross spend" total row
- [ ] Hovering a slice shows native SVG `<title>` tooltip with category and amount
- [ ] Switching filter to a single card re-renders without a fetch
- [ ] Card with zero MTD debits (or refunds-only): empty-state message, donut hidden
- [ ] Account with non-USD currency: contributes nothing to pie (matches existing totals behavior)
- [ ] No credit cards at all: whole pie panel hidden
- [ ] Inspect element on a category cell — text content is escaped (no HTML injection from category names)
- [ ] Refresh button on the parent panel still works and re-renders both summary AND pie

- [ ] **Step 4: No new commit**

If smoke passes, ship it. If anything fails, fix in a follow-up commit.

---

## Self-review

**Spec coverage:**
- §1 Architecture → Tasks 1, 4 (server query + client aggregation)
- §3 API (`categories_mtd` shape, sort, null bucket, refund exclusion) → Task 1 + Task 2
- §4 Frontend (panel placement, filter, donut, legend, palette, top-6+Other, safety) → Tasks 3 + 4
- §5 Errors + Edge Cases → Task 2 (server) + Task 4 (client empty/orphan/non-USD branches)
- §6 Testing → Task 1 + Task 2 (all 5 named pytest cases) + Task 5 (manual smoke)

**Placeholder scan:** No "TBD"/"TODO"/"similar to". Each step shows complete code.

**Type consistency:** `categories_mtd` (snake_case) used identically across migration, server, response JSON, frontend reads. `category`/`amount_cents` keys consistent. `UNCATEGORIZED`/`OTHER` sentinel strings handled consistently in `_categoryLabel`.

**Security:** Frontend uses `textContent`/`createElement`/`createElementNS` exclusively for any string sourced from API data. Category labels and amounts go through `textContent`; SVG `<title>` uses `textContent`. No `innerHTML` interpolation.

**Open spec items deferred:** Slice click drill-down, statement-cycle window, theme-aware palette — all explicitly out of scope per §"Open questions" of the spec.
