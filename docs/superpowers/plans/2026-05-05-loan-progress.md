# Loan Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Spec:** `docs/superpowers/specs/2026-05-05-loan-progress-design.md`

**Goal:** Per-loan mini-donut showing paid-off vs. unpaid against a user-entered original loan amount, inline-edit ✏️ per loan row.

**Architecture:** Migration 026 adds `original_loan_amount_cents` (nullable Integer) to `plaid_accounts`. New `PUT /plaid/accounts/<id>/loan-meta` endpoint sets/clears it. `GET /plaid/cards-overview` extends loan rows with `original_loan_amount_cents` + computed `paid_off_cents`. Frontend renders a third sub-panel inside the existing Card Usage card with one mini SVG donut per loan.

**Tech Stack:** Python 3.14 / Flask / SQLAlchemy / Alembic; vanilla JS frontend in `src/frontend/index.html`; pytest. Inline-SVG donut.

---

## File Structure

**Created:**
- `alembic/versions/026_plaid_account_loan_original_amount.py` — schema migration

**Modified:**
- `src/backend/initialize_database_schema.py` — add `original_loan_amount_cents` column to `PlaidAccount`
- `src/backend/plaid_integration.py` — extend `_serialize_plaid_account`; new `PUT /plaid/accounts/<id>/loan-meta` route; extend `cards_overview()` to compute `paid_off_cents`
- `src/frontend/index.html` — add `#card-usage-loans-panel` HTML + CSS + JS (loan row renderer, mini donut, inline edit, save handler)
- `tests/test_cards_overview.py` — append loan-progress tests

---

## Task 1: Migration 026 + model column

**Files:**
- Create: `alembic/versions/026_plaid_account_loan_original_amount.py`
- Modify: `src/backend/initialize_database_schema.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Add the schema test**

Append to `tests/test_cards_overview.py`:

```python
def test_plaid_account_has_original_loan_amount_column():
    """Migration 026 must add original_loan_amount_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "original_loan_amount_cents" in cols
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_cards_overview.py::test_plaid_account_has_original_loan_amount_column -v
```

Expected: FAIL.

- [ ] **Step 3: Add the model column**

In `src/backend/initialize_database_schema.py`, find the `PlaidAccount` class. Add the new column immediately after `available_credit_cents`:

```python
    available_credit_cents = Column(Integer, nullable=True)
    original_loan_amount_cents = Column(Integer, nullable=True)
    balance_updated_at = Column(DateTime, nullable=True)
```

- [ ] **Step 4: Write the migration**

Open `alembic/versions/025_plaid_account_credit_limits.py` and copy the `_column_exists` helper + import structure exactly. Apply the same pattern to a new file.

Create `alembic/versions/026_plaid_account_loan_original_amount.py`:

```python
"""plaid_account loan original amount column

Revision ID: 026_loan_original_amount
Revises: 025_credit_limits
Create Date: 2026-05-05

Adds nullable original_loan_amount_cents to plaid_accounts. User-entered
per loan via PUT /plaid/accounts/<id>/loan-meta. Phase 2 (Plaid Liabilities)
will auto-populate nulls without overwriting user values.

Mirrors the PRAGMA-guarded idempotent pattern of 025. Downgrade is no-op
(additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "026_loan_original_amount"
down_revision = "025_credit_limits"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "plaid_accounts", "original_loan_amount_cents"):
        op.add_column(
            "plaid_accounts",
            sa.Column("original_loan_amount_cents", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep column to avoid data loss on revert.
    pass
```

Confirm `down_revision = "025_credit_limits"` matches the actual `revision` string at the top of `025_plaid_account_credit_limits.py`. If different, use the exact string from there.

- [ ] **Step 5: Run the schema test → expect PASS**

```bash
pytest tests/test_cards_overview.py::test_plaid_account_has_original_loan_amount_column -v
```

- [ ] **Step 6: Idempotency smoke**

```bash
TMP=$(mktemp /tmp/test026.XXXXXX.db)
DATABASE_URL="sqlite:///$TMP" alembic stamp 025_credit_limits
DATABASE_URL="sqlite:///$TMP" alembic upgrade head
DATABASE_URL="sqlite:///$TMP" alembic upgrade head  # second run = no-op
DATABASE_URL="sqlite:///$TMP" alembic current        # should show 026_loan_original_amount (head)
rm "$TMP"
```

If `DATABASE_URL` isn't honored by `alembic/env.py`, look at how the URL resolves and adapt. If the smoke can't run in <5 minutes, skip it; idempotency is enforced by `_column_exists`.

- [ ] **Step 7: Run all cards-overview tests**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 16 passed.

- [ ] **Step 8: Commit**

```bash
git add alembic/versions/026_plaid_account_loan_original_amount.py \
        src/backend/initialize_database_schema.py \
        tests/test_cards_overview.py
git commit -m "feat(plaid): add original_loan_amount_cents column to plaid_accounts"
```

---

## Task 2: Serializer + PUT loan-meta endpoint

**Files:**
- Modify: `src/backend/plaid_integration.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Update `_serialize_plaid_account`**

In `src/backend/plaid_integration.py`, find `_serialize_plaid_account` (around line 249). Add `original_loan_amount_cents` to the returned dict, immediately after `available_credit_cents`:

```python
def _serialize_plaid_account(acct: PlaidAccount) -> dict:
    return {
        "id": acct.id,
        "plaid_item_id": acct.plaid_item_id,
        "plaid_account_id": acct.plaid_account_id,
        "name": acct.account_name,
        "mask": acct.account_mask,
        "type": acct.account_type,
        "subtype": acct.account_subtype,
        "balance_cents": acct.balance_cents,
        "credit_limit_cents": acct.credit_limit_cents,
        "available_credit_cents": acct.available_credit_cents,
        "original_loan_amount_cents": acct.original_loan_amount_cents,
        "balance_currency": acct.balance_iso_currency_code,
        "balance_updated_at": _iso_utc(acct.balance_updated_at),
    }
```

- [ ] **Step 2: Write failing test for PUT happy path**

Append to `tests/test_cards_overview.py`:

```python
def test_put_loan_meta_happy_path(app):
    """PUT /plaid/accounts/<id>/loan-meta updates original_loan_amount_cents."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_put@test.local", name="Loan PUT")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_put", inst_id="ins_loan_put")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_put",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=12240000, balance_iso_currency_code="USD",
        )
        session.add(loan)
        session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": 18500000})
    assert status == 200, body
    assert body["account"]["original_loan_amount_cents"] == 18500000

    # Verify persisted
    session = SF()
    try:
        row = session.get(PlaidAccount, loan_id)
        assert row.original_loan_amount_cents == 18500000
    finally:
        session.close()
```

Add a helper for invoking the new endpoint near the other `_invoke_*` helpers in the file:

```python
def _invoke_put_loan_meta(app, user_id, account_id, body):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    import json

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/plaid/accounts/{account_id}/loan-meta"
        with app.test_request_context(path, method="PUT", json=body):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(account_id=account_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj, status = resp[0], resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else (json.loads(obj) if isinstance(obj, str) else obj)
                return status, payload
            return 200, resp
    finally:
        session.close()
```

If the existing `_invoke_cards_overview` uses a different unwrap idiom, mirror that exactly.

- [ ] **Step 3: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py::test_put_loan_meta_happy_path -v
```

Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 4: Add the PUT endpoint**

Append to `src/backend/plaid_integration.py` (after `cards_overview`):

```python
@plaid_bp.route("/accounts/<int:account_id>/loan-meta", methods=["PUT"])
@require_auth
@require_write_access
def update_loan_meta(account_id: int):
    """Set or clear the user-entered original_loan_amount_cents on a loan account.

    Body: { "original_loan_amount_cents": int >= 0 | null }

    Returns 404 if the account is not visible to the user OR is not a loan
    (avoids leaking existence). Returns 400 if the value is malformed or
    negative.
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    payload = request.get_json(silent=True) or {}
    if "original_loan_amount_cents" not in payload:
        return jsonify({"error": "original_loan_amount_cents is required"}), 400

    raw = payload.get("original_loan_amount_cents")
    if raw is None:
        new_value = None
    else:
        if not isinstance(raw, int) or isinstance(raw, bool):
            return jsonify({"error": "original_loan_amount_cents must be a non-negative integer or null"}), 400
        if raw < 0:
            return jsonify({"error": "original_loan_amount_cents must be a non-negative integer or null"}), 400
        new_value = raw

    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)

    q = session.query(PlaidAccount).filter(PlaidAccount.id == account_id)
    if visible_ids is not None:
        if not visible_ids:
            return jsonify({"error": "Account not found"}), 404
        q = q.filter(PlaidAccount.plaid_item_id.in_(visible_ids))
    acct = q.first()
    if acct is None or acct.account_type != "loan":
        return jsonify({"error": "Account not found"}), 404

    acct.original_loan_amount_cents = new_value
    session.commit()

    return jsonify({"account": _serialize_plaid_account(acct)}), 200
```

Confirm `request` and `require_write_access` are already imported at the top of the file. If `require_write_access` doesn't exist as a decorator, look at how other write-protected routes (like `refresh_balances`) gate writes and mirror that.

- [ ] **Step 5: Run the happy-path test → expect PASS**

```bash
pytest tests/test_cards_overview.py::test_put_loan_meta_happy_path -v
```

- [ ] **Step 6: Add validation + visibility tests**

Append:

```python
def test_put_loan_meta_clear_with_null(app):
    """PUT with null clears the column."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_clear@test.local", name="Loan Clear")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_clear", inst_id="ins_loan_clear")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_clear",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
            original_loan_amount_cents=50000,
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": None})
    assert status == 200
    assert body["account"]["original_loan_amount_cents"] is None


def test_put_loan_meta_rejects_negative(app):
    """Negative values rejected with 400."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_neg@test.local", name="Loan Neg")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_neg", inst_id="ins_loan_neg")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_neg",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": -100})
    assert status == 400


def test_put_loan_meta_rejects_non_integer(app):
    """Non-integer values rejected with 400."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_str@test.local", name="Loan Str")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_str", inst_id="ins_loan_str")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_str",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": "abc"})
    assert status == 400


def test_put_loan_meta_rejects_credit_account(app):
    """Credit accounts return 404 (not loans)."""
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="loan_cc@test.local", name="Loan CC")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cc", inst_id="ins_loan_cc")
        cc = _seed_credit_account(session, user_id, item.id)
        cc_id = cc.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, cc_id, {"original_loan_amount_cents": 50000})
    assert status == 404


def test_put_loan_meta_visibility_filter(app):
    """User A cannot edit user B's loan."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_a = _make_user(app, email="loan_va@test.local", name="Loan VA")
    user_b = _make_user(app, email="loan_vb@test.local", name="Loan VB")

    _, SF = _get_db()
    session = SF()
    try:
        item_a = _seed_plaid_item_simple(session, user_a, item_token="item_loan_va", inst_id="ins_loan_va")
        loan = PlaidAccount(
            plaid_item_id=item_a.id, user_id=user_a, plaid_account_id="ln_v",
            account_name="A's Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_b, loan_id, {"original_loan_amount_cents": 50000})
    assert status == 404
```

- [ ] **Step 7: Run all PUT tests**

```bash
pytest tests/test_cards_overview.py -k "loan_meta" -v
```

Expected: 5 passed.

- [ ] **Step 8: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): PUT /plaid/accounts/<id>/loan-meta — set original loan amount"
```

---

## Task 3: cards-overview emits paid_off_cents

**Files:**
- Modify: `src/backend/plaid_integration.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cards_overview.py`:

```python
def test_cards_overview_loan_paid_off_computed(app):
    """Loan with original > balance: paid_off = original - balance."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_po@test.local", name="Loan PO")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_po", inst_id="ins_loan_po")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_po",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=400000, original_loan_amount_cents=1000000,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["original_loan_amount_cents"] == 1000000
    assert loan["paid_off_cents"] == 600000


def test_cards_overview_loan_paid_off_overbalance(app):
    """balance > original → paid_off capped at original."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_ob@test.local", name="Loan OB")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_ob", inst_id="ins_loan_ob")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_ob",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=1100000, original_loan_amount_cents=1000000,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["paid_off_cents"] == 1000000


def test_cards_overview_loan_no_original(app):
    """Loan with original=null → paid_off=null."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_no@test.local", name="Loan NO")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_no", inst_id="ins_loan_no")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_no",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=400000, original_loan_amount_cents=None,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["original_loan_amount_cents"] is None
    assert loan["paid_off_cents"] is None


def test_cards_overview_credit_row_no_loan_fields(app):
    """Credit accounts have original=null and paid_off=null."""
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="loan_cc2@test.local", name="Loan CC2")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cc2", inst_id="ins_loan_cc2")
        _seed_credit_account(session, user_id, item.id)
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["original_loan_amount_cents"] is None
    assert cc["paid_off_cents"] is None
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_loan_paid_off_computed -v
```

Expected: FAIL — `KeyError: 'paid_off_cents'`.

- [ ] **Step 3: Compute paid_off in cards_overview**

In `src/backend/plaid_integration.py`, find the per-account loop in `cards_overview()` (where each `a in accounts` is iterated). Locate where the loan branch sets `categories_mtd: []` (added in earlier phase). Add this just before bucketing into `loan_rows`:

```python
        # Loan-only fields: original_loan_amount_cents already on base via serializer.
        # paid_off_cents is computed (max 0, capped at original).
        if a.account_type == "loan":
            orig = a.original_loan_amount_cents
            bal = a.balance_cents
            if orig is None or bal is None:
                base["paid_off_cents"] = None
            else:
                paid = orig - bal
                if paid < 0:
                    paid = 0
                if paid > orig:
                    paid = orig
                base["paid_off_cents"] = paid
        else:
            base["paid_off_cents"] = None
```

The `original_loan_amount_cents` field is already on `base` via the updated `_serialize_plaid_account` (Task 2). Frontend reads both.

- [ ] **Step 4: Run all loan tests → expect PASS**

```bash
pytest tests/test_cards_overview.py -k "loan_paid_off or loan_no_original or credit_row_no_loan_fields" -v
```

- [ ] **Step 5: Run full file**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 24 passed (16 + 5 PUT + 4 paid-off).

- [ ] **Step 6: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): cards-overview emits paid_off_cents for loans (max 0, capped at original)"
```

---

## Task 4: Frontend — Loan Progress sub-panel + mini donut

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add the sub-panel HTML**

Search `src/frontend/index.html` for `<div id="card-usage-pie-panel"` (the spend-by-category panel from Phase 1.5). After its closing `</div>` (`<!-- end card-usage-pie-panel -->` may not exist; match the panel block boundary), and BEFORE `<div id="card-usage-body">`, insert:

```html
<div id="card-usage-loans-panel" class="card-usage-loans-panel" style="display:none">
  <div class="card-usage-pie-head">
    <span class="card-usage-pie-title">Loan Progress</span>
  </div>
  <div id="card-usage-loans-body" class="card-usage-loans-body">
    <!-- per-loan rows rendered by _renderLoanProgressPanel() -->
  </div>
</div>
```

(Reuses `.card-usage-pie-head` / `.card-usage-pie-title` styles from Phase 1.5.)

- [ ] **Step 2: Append CSS**

Find the existing `<style>` block that contains `.card-usage-pie-panel` (from Phase 1.5). Append:

```css
.card-usage-loans-panel {
  background: var(--surface, #1c1c1e);
  border-radius: 12px;
  padding: 14px;
  margin: 0 0 8px;
  border: 1px solid var(--border, #3a3a3c);
}
.card-usage-loans-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.loan-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border, #3a3a3c);
}
.loan-row:last-child { border-bottom: none; }
.loan-row .mini-donut { flex: 0 0 100px; position: relative; }
.loan-row .mini-donut svg { display: block; }
.loan-row .mini-donut .donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text, #fff);
  pointer-events: none;
}
.loan-row .loan-info {
  flex: 1 1 220px;
  min-width: 200px;
  font-size: 0.9rem;
}
.loan-row .loan-info .loan-name {
  font-weight: 600;
  margin-bottom: 4px;
}
.loan-row .loan-info .loan-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted, #888);
  font-variant-numeric: tabular-nums;
}
.loan-row .loan-info .loan-line.paid-off-line { color: #34c759; }
.loan-row .loan-info .loan-line.total-line {
  color: var(--text, #fff);
  font-weight: 600;
  border-top: 1px solid var(--border, #3a3a3c);
  padding-top: 4px;
  margin-top: 4px;
}
.loan-row .loan-edit-btn {
  background: var(--surface2, #2c2c2e);
  border: 1px solid var(--border, #3a3a3c);
  color: var(--text, #fff);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 0.85rem;
  cursor: pointer;
}
.loan-row .loan-edit-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex: 1 1 220px;
}
.loan-row .loan-edit-form input {
  flex: 1;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--surface2, #2c2c2e);
  color: var(--text, #fff);
  border: 1px solid var(--border, #3a3a3c);
  font-size: 0.92rem;
}
.loan-row .loan-edit-form button {
  padding: 8px 12px;
  border-radius: 8px;
  border: none;
  font-size: 0.9rem;
  cursor: pointer;
}
.loan-row .loan-edit-form button.save { background: #0a84ff; color: #fff; }
.loan-row .loan-edit-form button.cancel { background: var(--surface2, #2c2c2e); color: var(--text, #fff); border: 1px solid var(--border, #3a3a3c); }
```

- [ ] **Step 3: Add JS — mini donut renderer**

Search `src/frontend/index.html` for `_renderCardUsageDonut`. Append after it (or near the other card-usage functions):

```javascript
function _renderLoanMiniDonut(paidCents, totalCents) {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const size = 100, cx = size / 2, cy = size / 2;
  const outerR = 44, innerR = 30;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("viewBox", "0 0 " + size + " " + size);
  svg.setAttribute("role", "img");

  if (!totalCents || totalCents <= 0) {
    // Placeholder ring (light grey)
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
    ring.setAttribute("fill", "#3a3a3c");
    ring.setAttribute("fill-rule", "evenodd");
    svg.appendChild(ring);
    return svg;
  }

  const paid = Math.max(0, Math.min(paidCents || 0, totalCents));
  const frac = paid / totalCents;

  if (frac >= 1) {
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
    ring.setAttribute("fill", "#34c759");
    ring.setAttribute("fill-rule", "evenodd");
    svg.appendChild(ring);
    return svg;
  }

  // Two-slice donut: paid (green) + unpaid (grey)
  const slices = [
    { frac: frac, color: "#34c759" },
    { frac: 1 - frac, color: "#8e8e93" },
  ];
  let startAngle = -Math.PI / 2;
  slices.forEach(s => {
    if (s.frac <= 0) return;
    const endAngle = startAngle + s.frac * 2 * Math.PI;
    const largeArc = s.frac > 0.5 ? 1 : 0;
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
    svg.appendChild(path);
    startAngle = endAngle;
  });
  return svg;
}
```

- [ ] **Step 4: Add JS — loan row renderer**

Append:

```javascript
function _renderLoanRow(account) {
  const row = document.createElement("div");
  row.className = "loan-row";
  row.dataset.loanId = account.id;

  // Donut wrapper (donut + center label)
  const donutWrap = document.createElement("div");
  donutWrap.className = "mini-donut";
  const total = account.original_loan_amount_cents;
  const paid = account.paid_off_cents;
  donutWrap.appendChild(_renderLoanMiniDonut(paid, total));
  if (total && total > 0) {
    const center = document.createElement("div");
    center.className = "donut-center";
    const pct = Math.round(((paid || 0) / total) * 100);
    center.textContent = pct + "%";
    donutWrap.appendChild(center);
  }
  row.appendChild(donutWrap);

  // Info column
  const info = document.createElement("div");
  info.className = "loan-info";
  const name = document.createElement("div");
  name.className = "loan-name";
  name.textContent = "🏦 " + (account.name || "Loan") + " ····" + (account.mask || "");
  info.appendChild(name);

  if (total) {
    const paidLine = document.createElement("div");
    paidLine.className = "loan-line paid-off-line";
    const paidL = document.createElement("span");
    paidL.textContent = "Paid off:";
    const paidV = document.createElement("span");
    const pct = Math.round(((paid || 0) / total) * 100);
    paidV.textContent = _fmtMoneyCents(paid || 0, account.balance_currency) + " (" + pct + "%)";
    paidLine.appendChild(paidL); paidLine.appendChild(paidV);
    info.appendChild(paidLine);

    const unpaidLine = document.createElement("div");
    unpaidLine.className = "loan-line unpaid-line";
    const unpL = document.createElement("span"); unpL.textContent = "Unpaid:";
    const unpV = document.createElement("span");
    unpV.textContent = _fmtMoneyCents(account.balance_cents || 0, account.balance_currency);
    unpaidLine.appendChild(unpL); unpaidLine.appendChild(unpV);
    info.appendChild(unpaidLine);

    const totalLine = document.createElement("div");
    totalLine.className = "loan-line total-line";
    const totL = document.createElement("span"); totL.textContent = "Total:";
    const totV = document.createElement("span");
    totV.textContent = _fmtMoneyCents(total, account.balance_currency);
    totalLine.appendChild(totL); totalLine.appendChild(totV);
    info.appendChild(totalLine);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "loan-line";
    placeholder.textContent = "Original amount not set.";
    info.appendChild(placeholder);
  }

  row.appendChild(info);

  // Edit button
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "loan-edit-btn";
  editBtn.textContent = total ? "✏️ Edit" : "✏️ Set original amount";
  editBtn.addEventListener("click", function () { _toggleLoanEditMode(account.id, true); });
  row.appendChild(editBtn);

  return row;
}

function _toggleLoanEditMode(accountId, on) {
  const row = document.querySelector('.loan-row[data-loan-id="' + accountId + '"]');
  if (!row) return;
  const cache = __cardsOverviewCache;
  const loanGroup = cache && (cache.groups || []).find(g => g.type === "loan");
  const account = loanGroup && loanGroup.accounts.find(a => a.id === accountId);
  if (!account) return;

  if (!on) {
    row.replaceWith(_renderLoanRow(account));
    return;
  }

  // Replace info + edit button with form
  const info = row.querySelector(".loan-info");
  const btn = row.querySelector(".loan-edit-btn");
  if (info) info.style.display = "none";
  if (btn) btn.style.display = "none";

  const form = document.createElement("div");
  form.className = "loan-edit-form";
  const input = document.createElement("input");
  input.type = "number";
  input.min = "0";
  input.step = "0.01";
  input.placeholder = "Original loan amount ($)";
  if (account.original_loan_amount_cents) {
    input.value = (account.original_loan_amount_cents / 100).toFixed(2);
  }
  const save = document.createElement("button");
  save.type = "button";
  save.className = "save";
  save.textContent = "Save";
  save.addEventListener("click", function () { _saveLoanOriginal(accountId, input.value); });
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "cancel";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", function () { _toggleLoanEditMode(accountId, false); });

  form.appendChild(input);
  form.appendChild(save);
  form.appendChild(cancel);
  row.appendChild(form);
  input.focus();
  input.select();
}

async function _saveLoanOriginal(accountId, rawValue) {
  let cents = null;
  const trimmed = String(rawValue || "").trim();
  if (trimmed !== "") {
    const num = Number(trimmed);
    if (!isFinite(num) || num < 0) {
      toast("Enter a non-negative number.", "error");
      return;
    }
    cents = Math.round(num * 100);
  }
  try {
    const res = await api("/plaid/accounts/" + accountId + "/loan-meta", {
      method: "PUT",
      body: JSON.stringify({ original_loan_amount_cents: cents }),
    });
    if (!res.ok) {
      toast("Save failed.", "error");
      return;
    }
    toast("Updated.", "success");
    await loadCardsOverview();
  } catch (e) {
    toast("Save failed.", "error");
  }
}

function _renderLoanProgressPanel() {
  const panel = document.getElementById("card-usage-loans-panel");
  const body = document.getElementById("card-usage-loans-body");
  if (!panel || !body) return;
  body.replaceChildren();

  const cache = __cardsOverviewCache;
  const loanGroup = cache && (cache.groups || []).find(g => g.type === "loan");
  if (!loanGroup || loanGroup.accounts.length === 0) {
    panel.style.display = "none";
    return;
  }
  panel.style.display = "block";
  loanGroup.accounts.forEach(a => {
    body.appendChild(_renderLoanRow(a));
  });
}
```

- [ ] **Step 5: Hook into `renderCardsOverview`**

Find the existing wiring lines added in Phase 1.5 (`_refreshCardUsageFilterOptions(); _renderCardUsagePie(...)` inside `renderCardsOverview`). Immediately AFTER those two lines, add:

```javascript
  _renderLoanProgressPanel();
```

- [ ] **Step 6: Smoke test**

If a dev server is running:
- A user with a loan + `original_loan_amount_cents` set → mini donut + paid-off / unpaid / total + ✏️ Edit
- A user with a loan + null original → placeholder ring + "Original amount not set." + "✏️ Set original amount"
- Click ✏️ → inline form appears, pre-filled with dollars
- Save valid → toast success, donut updates
- Save invalid (negative) → toast error
- Save empty → clears (null), placeholder returns
- A user with no loans → panel hidden
- Console: no errors

If no dev server:
- Confirm syntax: `git show HEAD -- src/frontend/index.html | grep -i innerhtml` → empty for this commit's additions
- Visual diff inspection

- [ ] **Step 7: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): loan progress mini-donuts + inline edit per loan row"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run all cards-overview tests**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: 24 passed (15 from prior phases + 1 schema + 5 PUT + 4 paid-off-computation tests).

- [ ] **Step 2: Regression check**

```bash
pytest tests/test_cards_overview.py tests/test_accounts_dashboard.py -v 2>&1 | tail -10
```

Pre-existing 3-4 failures in `test_accounts_dashboard::test_patch_item_*` and `test_get_accounts_happy_path` are unrelated.

- [ ] **Step 3: Browser smoke checklist**

In a browser, navigate to **Accounts** as a user with at least one Plaid loan account:

- [ ] "Loan Progress" sub-panel appears between the spend pie and the per-card list (only if loans exist)
- [ ] Each loan with `original_loan_amount_cents` set shows mini donut + center % + paid/unpaid/total + ✏️ Edit
- [ ] Each loan without `original_loan_amount_cents` shows placeholder ring + "Original amount not set." + ✏️ Set CTA
- [ ] ✏️ Edit → inline input pre-filled with dollar amount, Save / Cancel buttons
- [ ] Saving a valid number updates the donut + summary; toast shows success
- [ ] Saving negative or non-numeric → error toast, no save
- [ ] Saving empty value clears the field; placeholder returns
- [ ] Multiple loans → multiple independently-editable rows
- [ ] No-loan account → panel hidden
- [ ] DOM inspection: loan name + amounts use `textContent` (no HTML injection)
- [ ] Refresh button on parent panel still works; loan donuts re-render after refresh

- [ ] **Step 4: No new commit**

If smoke passes, ship it. Failures → follow-up commit.

---

## Self-review

**Spec coverage:**
- §1 Architecture → Tasks 1, 2, 3, 4
- §2 Data Model → Task 1 (migration + model)
- §3 API → Task 2 (PUT) + Task 3 (paid_off)
- §4 Frontend → Task 4 (panel, donut, row, edit)
- §5 Errors → Task 2 (server-side validation, visibility) + Task 4 (client-side, empty / negative / non-numeric)
- §6 Testing → Tasks 1, 2, 3 cover all named pytest cases; Task 5 has manual smoke

**Placeholder scan:** No "TBD"/"TODO"/"similar to". Every code block is complete.

**Type consistency:** `original_loan_amount_cents` (snake_case) used identically across migration, model, serializer, response JSON, frontend reads, request body. `paid_off_cents` consistent in JSON + frontend.

**Security:** Server validates body type (`isinstance(int)`), value range (`>= 0`), account type (must be loan), and visibility (`_visible_plaid_item_ids`). Frontend uses `textContent` / `createElement` / `createElementNS` for all dynamic strings.
