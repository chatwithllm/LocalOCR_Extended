# Cards Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-05-cards-overview-design.md`

**Goal:** Show every Plaid-linked credit card and loan account in one place with balance, credit limit, utilization %, month-to-date spend, and txn count.

**Architecture:** New read-only endpoint `GET /plaid/cards-overview` joins the existing `plaid_accounts` cache (extended with two new nullable credit-limit columns) with `plaid_staged_transactions` for month-to-date spend. The existing `POST /plaid/accounts/refresh-balances` is updated to persist limit + available data that Plaid already returns but we currently discard. Frontend renders as a new panel at the top of the existing **Accounts** page (deviation from spec §4 — see note below).

**Tech Stack:** Python 3.14 / Flask / SQLAlchemy / Alembic; vanilla JS frontend in `src/frontend/index.html`; pytest with existing `tests/conftest.py` fixtures.

**Spec deviation (intentional):** Spec §4 calls for a brand-new `Cards` page in the side nav. Existing `page-accounts` already exists and already exposes `Refresh Balances`. To avoid duplicate navigation for related concepts, this plan adds a `Card Usage` panel as the **first card on the existing Accounts page**, instead of a new top-level nav entry. The panel itself matches the spec layout (summary block + Credit Cards group + Loans group). All other spec sections (§1, §2, §3, §5, §6) implemented as written.

**Frontend safety note:** Every interpolation of backend-supplied strings (`name`, `mask`, `currency`, `plaid_account_id`) goes through `escapeHTML()` or `textContent`. No `innerHTML` is used with untrusted concatenation. Account names come from Plaid (institution-supplied) and must be treated as untrusted.

---

## File Structure

**Created:**
- `alembic/versions/025_plaid_account_credit_limits.py` — schema migration
- `tests/test_cards_overview.py` — endpoint + math + scoping tests

**Modified:**
- `src/backend/initialize_database_schema.py` — add two columns to `PlaidAccount` model
- `src/backend/plaid_integration.py` — `_serialize_plaid_account()` returns new fields; `refresh_balances()` persists them; new `cards_overview()` route
- `src/frontend/index.html` — new panel HTML in `page-accounts`; new JS functions `loadCardsOverview()`, `renderCardsOverview()`, `_cardsOverviewAutoRefresh()`; CSS for the new panel

---

## Task 1: Migration — add credit limit columns

**Files:**
- Create: `alembic/versions/025_plaid_account_credit_limits.py`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cards_overview.py` with this initial test:

```python
"""Tests for cards-overview feature: schema migration, endpoint, math, scoping."""
from src.backend.initialize_database_schema import Base


def test_plaid_account_has_credit_limit_columns():
    """Migration 025 must add credit_limit_cents and available_credit_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "credit_limit_cents" in cols
    assert "available_credit_cents" in cols
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cards_overview.py::test_plaid_account_has_credit_limit_columns -v
```

Expected: FAIL — `assert "credit_limit_cents" in cols`.

- [ ] **Step 3: Write the migration file**

Before writing, confirm the actual revision identifier of the latest migration. Open `alembic/versions/024_medication_user_id.py` and read the `revision = "..."` line. Use that exact string as `down_revision` below.

Create `alembic/versions/025_plaid_account_credit_limits.py`:

```python
"""plaid_account credit limit columns

Revision ID: 025_credit_limits
Revises: <PASTE EXACT down_revision FROM 024 HERE>
Create Date: 2026-05-05

Adds nullable credit_limit_cents and available_credit_cents to plaid_accounts.
Both are populated on the next /plaid/accounts/refresh-balances call; no
backfill is required because Plaid's Balance API already returns these fields
on every refresh — we previously discarded them.
"""
from alembic import op
import sqlalchemy as sa


revision = "025_credit_limits"
down_revision = "<PASTE EXACT down_revision FROM 024 HERE>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plaid_accounts",
        sa.Column("credit_limit_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "plaid_accounts",
        sa.Column("available_credit_cents", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plaid_accounts", "available_credit_cents")
    op.drop_column("plaid_accounts", "credit_limit_cents")
```

- [ ] **Step 4: Add the columns to the SQLAlchemy model**

In `src/backend/initialize_database_schema.py`, find the `PlaidAccount` class (around line 781) and add these two columns immediately after `balance_iso_currency_code`:

```python
    balance_iso_currency_code = Column(String(3), nullable=False, default="USD")
    credit_limit_cents = Column(Integer, nullable=True)
    available_credit_cents = Column(Integer, nullable=True)
    balance_updated_at = Column(DateTime, nullable=True)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_cards_overview.py::test_plaid_account_has_credit_limit_columns -v
```

Expected: PASS.

- [ ] **Step 6: Apply the migration locally and verify**

```bash
alembic upgrade head
```

Then list columns to confirm:

```bash
python3 -c "from src.backend.initialize_database_schema import engine, Base; from sqlalchemy import inspect; print([c['name'] for c in inspect(engine).get_columns('plaid_accounts')])"
```

Expected output includes `credit_limit_cents` and `available_credit_cents`.

If the project uses a different engine bootstrap path, look in `src/backend/initialize_database_schema.py` for how the engine is constructed and adapt the import line.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/025_plaid_account_credit_limits.py \
        src/backend/initialize_database_schema.py \
        tests/test_cards_overview.py
git commit -m "feat(plaid): add credit_limit_cents + available_credit_cents to plaid_accounts"
```

---

## Task 2: `refresh_balances()` persists limit + available

**Files:**
- Modify: `src/backend/plaid_integration.py:1645-1820` (the `refresh_balances` route body)
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cards_overview.py`:

```python
from datetime import datetime
from unittest.mock import patch, MagicMock


def _seed_plaid_item(session, user_id, item_token="test_item_1", inst_id="ins_1"):
    from src.backend.initialize_database_schema import PlaidItem
    item = PlaidItem(
        user_id=user_id,
        plaid_item_id=item_token,
        plaid_institution_id=inst_id,
        institution_name="Test Bank",
        access_token_encrypted="ENC",
        status="active",
        accounts_json="[]",
        cursor=None,
    )
    session.add(item)
    session.commit()
    return item


def test_refresh_balances_persists_limit_and_available(app, db_session, auth_user):
    """When Plaid returns balances.limit and balances.available, both must be stored."""
    from src.backend.initialize_database_schema import PlaidAccount

    item = _seed_plaid_item(db_session, auth_user.id)

    fake_plaid_response = {
        "accounts": [{
            "account_id": "plaid_acct_1",
            "name": "Sapphire",
            "mask": "4521",
            "type": "credit",
            "subtype": "credit card",
            "balances": {
                "current": 1243.00,
                "limit": 5000.00,
                "available": 3757.00,
                "iso_currency_code": "USD",
            },
        }],
    }

    fake_client = MagicMock()
    fake_client.accounts_balance_get.return_value = fake_plaid_response

    with patch("src.backend.plaid_integration.is_plaid_configured", return_value=True), \
         patch("src.backend.plaid_integration.get_client", return_value=fake_client), \
         patch("src.backend.plaid_integration.decrypt_api_key", return_value="access_token_xxx"):
        client = app.test_client()
        with client.session_transaction() as s:
            s["user_id"] = auth_user.id
        res = client.post("/plaid/accounts/refresh-balances")
        assert res.status_code == 200, res.get_json()

    row = db_session.query(PlaidAccount).filter_by(plaid_account_id="plaid_acct_1").one()
    assert row.balance_cents == 124300
    assert row.credit_limit_cents == 500000
    assert row.available_credit_cents == 375700
```

If `app`, `db_session`, or `auth_user` fixtures don't already exist in `tests/conftest.py`, run:

```bash
grep -nE "^def (app|db_session|auth_user)" tests/conftest.py
```

If any are missing, stop and add them following the patterns in `tests/test_plaid_integration.py`. Inspect existing fixtures with `grep -nE "^def " tests/conftest.py | head` and adapt.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cards_overview.py::test_refresh_balances_persists_limit_and_available -v
```

Expected: FAIL — `credit_limit_cents` is None because `refresh_balances` does not yet persist `limit`.

- [ ] **Step 3: Update `refresh_balances` to persist the new fields**

In `src/backend/plaid_integration.py`, find the loop inside `refresh_balances()` (around line 1707) where `current` is parsed.

Find this block (current code):

```python
            balances = plaid_acct.get("balances") or {}
            current = balances.get("current")
            currency = balances.get("iso_currency_code") or "USD"
            balance_cents = None
            if current is not None:
                try:
                    balance_cents = int(round(float(current) * 100))
                except (TypeError, ValueError):
                    balance_cents = None
```

Replace with:

```python
            balances = plaid_acct.get("balances") or {}
            current = balances.get("current")
            limit = balances.get("limit")
            available = balances.get("available")
            currency = balances.get("iso_currency_code") or "USD"

            def _to_cents(v):
                if v is None:
                    return None
                try:
                    return int(round(float(v) * 100))
                except (TypeError, ValueError):
                    return None

            balance_cents = _to_cents(current)
            credit_limit_cents = _to_cents(limit)
            available_credit_cents = _to_cents(available)
```

Then locate the place that writes the row (a few lines below — both the lazy-create branch and the update branch). Update both.

For the lazy-create branch (search for `row = PlaidAccount(`):

```python
                row = PlaidAccount(
                    plaid_item_id=item.id,
                    user_id=user_id,
                    plaid_account_id=plaid_acct_id,
                    account_name=plaid_acct.get("name"),
                    account_mask=plaid_acct.get("mask"),
                    account_type=plaid_acct.get("type"),
                    account_subtype=plaid_acct.get("subtype"),
                    balance_cents=balance_cents,
                    credit_limit_cents=credit_limit_cents,
                    available_credit_cents=available_credit_cents,
                    balance_iso_currency_code=currency,
                    balance_updated_at=now,
                )
                session.add(row)
```

For the update branch (search for `row.balance_cents = balance_cents`):

```python
            row.balance_cents = balance_cents
            row.credit_limit_cents = credit_limit_cents
            row.available_credit_cents = available_credit_cents
            row.balance_iso_currency_code = currency
            row.balance_updated_at = now
```

If the existing code does not match this pattern exactly, mirror the logic but include the two new fields. Inspect lines ~1700–1760 to see the exact structure.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_cards_overview.py::test_refresh_balances_persists_limit_and_available -v
```

Expected: PASS.

- [ ] **Step 5: Run the broader Plaid test file to confirm no regression**

```bash
pytest tests/test_plaid_integration.py -v
```

Expected: PASS (any failures here are regressions caused by step 3 — fix before moving on).

- [ ] **Step 6: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): persist credit limit and available credit on balance refresh"
```

---

## Task 3: Update `_serialize_plaid_account` to expose new fields

**Files:**
- Modify: `src/backend/plaid_integration.py:249-262`
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cards_overview.py`:

```python
def test_serialize_plaid_account_includes_credit_fields():
    """Account serializer must surface credit limit and available credit."""
    from src.backend.initialize_database_schema import PlaidAccount
    from src.backend.plaid_integration import _serialize_plaid_account

    acct = PlaidAccount(
        id=1,
        plaid_item_id=1,
        user_id=1,
        plaid_account_id="x",
        account_name="Sapphire",
        account_mask="4521",
        account_type="credit",
        account_subtype="credit card",
        balance_cents=124300,
        credit_limit_cents=500000,
        available_credit_cents=375700,
        balance_iso_currency_code="USD",
        balance_updated_at=None,
    )
    out = _serialize_plaid_account(acct)
    assert out["credit_limit_cents"] == 500000
    assert out["available_credit_cents"] == 375700
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cards_overview.py::test_serialize_plaid_account_includes_credit_fields -v
```

Expected: FAIL — `KeyError: 'credit_limit_cents'`.

- [ ] **Step 3: Update the serializer**

In `src/backend/plaid_integration.py`, replace the body of `_serialize_plaid_account` (currently lines 249–262):

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
        "balance_currency": acct.balance_iso_currency_code,
        "balance_updated_at": _iso_utc(acct.balance_updated_at),
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_cards_overview.py::test_serialize_plaid_account_includes_credit_fields -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): expose credit_limit_cents + available_credit_cents in account serializer"
```

---

## Task 4: New endpoint `GET /plaid/cards-overview` — empty case

**Files:**
- Modify: `src/backend/plaid_integration.py` (append a new route)
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cards_overview.py`:

```python
def test_cards_overview_empty(app, auth_user):
    """User with no Plaid items returns empty groups + zero totals."""
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    res = client.get("/plaid/cards-overview")
    assert res.status_code == 200
    body = res.get_json()
    assert body["groups"] == []
    assert body["totals"]["credit_balance_cents"] == 0
    assert body["totals"]["credit_limit_cents"] == 0
    assert body["totals"]["overall_utilization_pct"] is None
    assert body["totals"]["credit_spend_mtd_cents"] == 0
    assert body["totals"]["loan_balance_cents"] == 0
    assert "as_of" in body
    assert "month_start" in body
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_empty -v
```

Expected: FAIL — 404 (route does not exist).

- [ ] **Step 3: Add the route**

Append to `src/backend/plaid_integration.py` (place after `refresh_balances`):

```python
@plaid_bp.route("/cards-overview", methods=["GET"])
@require_auth
def cards_overview():
    """Card-usage view: balance, credit limit, utilization %, MTD spend per card.

    Read-only. No throttle. Sources data exclusively from the
    `plaid_accounts` cache and `plaid_staged_transactions`. Use
    `POST /plaid/accounts/refresh-balances` to refresh balances first.

    Includes accounts where `account_type` is `credit` or `loan`. Depository
    and investment accounts are excluded.
    """
    from datetime import datetime, timezone
    from sqlalchemy import case, func

    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    accounts_q = session.query(PlaidAccount).filter(
        PlaidAccount.user_id == user_id,
        PlaidAccount.account_type.in_(("credit", "loan")),
    )
    if visible_ids is not None:
        if not visible_ids:
            accounts = []
        else:
            accounts = accounts_q.filter(PlaidAccount.plaid_item_id.in_(visible_ids)).all()
    else:
        accounts = accounts_q.all()

    # MTD spend per plaid_account_id
    spend_rows = (
        session.query(
            PlaidStagedTransaction.plaid_account_id,
            func.sum(PlaidStagedTransaction.amount).label("net_amount"),
            func.sum(case((PlaidStagedTransaction.amount > 0, 1), else_=0)).label("debit_count"),
        )
        .filter(PlaidStagedTransaction.user_id == user_id)
        .filter(PlaidStagedTransaction.transaction_date >= month_start.date())
        .filter(PlaidStagedTransaction.status != "dismissed")
        .group_by(PlaidStagedTransaction.plaid_account_id)
        .all()
    )
    spend_map = {
        r.plaid_account_id: {
            "spend_mtd_cents": int(round(float(r.net_amount or 0) * 100)),
            "txn_count_mtd": int(r.debit_count or 0),
        }
        for r in spend_rows
    }

    credit_rows = []
    loan_rows = []
    for a in accounts:
        base = _serialize_plaid_account(a)
        bucket = spend_map.get(a.plaid_account_id, {"spend_mtd_cents": 0, "txn_count_mtd": 0})
        base["spend_mtd_cents"] = bucket["spend_mtd_cents"]
        base["txn_count_mtd"] = bucket["txn_count_mtd"]

        limit = a.credit_limit_cents
        balance = a.balance_cents
        if a.account_type == "credit" and limit and limit > 0 and balance is not None:
            base["utilization_pct"] = round(balance / limit * 100, 2)
        else:
            base["utilization_pct"] = None

        base["currency"] = a.balance_iso_currency_code

        if a.account_type == "credit":
            credit_rows.append(base)
        else:
            loan_rows.append(base)

    credit_rows.sort(key=lambda r: r["utilization_pct"] if r["utilization_pct"] is not None else -1, reverse=True)
    loan_rows.sort(key=lambda r: r["balance_cents"] or 0, reverse=True)

    groups = []
    if credit_rows:
        groups.append({"type": "credit_card", "label": "Credit Cards", "accounts": credit_rows})
    if loan_rows:
        groups.append({"type": "loan", "label": "Loans", "accounts": loan_rows})

    # Totals — USD only, only accounts with non-null limit contribute to limit/util
    usd_credit = [r for r in credit_rows if (r["currency"] or "USD") == "USD"]
    usd_loan = [r for r in loan_rows if (r["currency"] or "USD") == "USD"]

    credit_balance_cents = sum((r["balance_cents"] or 0) for r in usd_credit)
    credit_limit_cents = sum((r["credit_limit_cents"] or 0) for r in usd_credit if r["credit_limit_cents"])
    credit_spend_mtd_cents = sum((r["spend_mtd_cents"] or 0) for r in usd_credit)
    loan_balance_cents = sum((r["balance_cents"] or 0) for r in usd_loan)

    overall_util = None
    if credit_limit_cents > 0:
        overall_util = round(credit_balance_cents / credit_limit_cents * 100, 2)

    return jsonify({
        "as_of": now.replace(tzinfo=None).isoformat() + "Z",
        "month_start": month_start.date().isoformat(),
        "groups": groups,
        "totals": {
            "credit_balance_cents": credit_balance_cents,
            "credit_limit_cents": credit_limit_cents,
            "overall_utilization_pct": overall_util,
            "credit_spend_mtd_cents": credit_spend_mtd_cents,
            "loan_balance_cents": loan_balance_cents,
        },
    }), 200
```

Make sure `PlaidStagedTransaction` is imported at the top of the file. If not, add it.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_empty -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/plaid_integration.py tests/test_cards_overview.py
git commit -m "feat(plaid): GET /plaid/cards-overview — empty case"
```

---

## Task 5: `cards-overview` populated case — credit card with limit + MTD spend

**Files:**
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_cards_overview.py`:

```python
def _seed_credit_account(session, user_id, item_id, plaid_account_id="cc_1",
                         balance_cents=124300, limit_cents=500000, avail_cents=375700):
    from src.backend.initialize_database_schema import PlaidAccount
    acct = PlaidAccount(
        plaid_item_id=item_id,
        user_id=user_id,
        plaid_account_id=plaid_account_id,
        account_name="Sapphire",
        account_mask="4521",
        account_type="credit",
        account_subtype="credit card",
        balance_cents=balance_cents,
        credit_limit_cents=limit_cents,
        available_credit_cents=avail_cents,
        balance_iso_currency_code="USD",
        balance_updated_at=datetime.utcnow(),
    )
    session.add(acct)
    session.commit()
    return acct


def _seed_staged(session, *, user_id, plaid_item_id, plaid_account_id, amount, date_str,
                 status="ready_to_import", txn_id=None):
    from datetime import date as date_cls
    from src.backend.initialize_database_schema import PlaidStagedTransaction
    txn = PlaidStagedTransaction(
        plaid_item_id=plaid_item_id,
        user_id=user_id,
        plaid_transaction_id=txn_id or f"txn_{plaid_account_id}_{amount}_{date_str}",
        plaid_account_id=plaid_account_id,
        amount=amount,
        transaction_date=date_cls.fromisoformat(date_str),
        status=status,
        raw_json="{}",
    )
    session.add(txn)
    session.commit()
    return txn


def test_cards_overview_credit_card_with_limit(app, db_session, auth_user):
    """Credit card with limit: util%, MTD spend net of refunds, debit-only count."""
    from datetime import date as date_cls

    item = _seed_plaid_item(db_session, auth_user.id)
    _seed_credit_account(db_session, auth_user.id, item.id)

    today = date_cls.today().replace(day=15).isoformat()
    month_start = date_cls.today().replace(day=1).isoformat()

    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=200.00, date_str=today, txn_id="t1")
    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=250.00, date_str=today, txn_id="t2")
    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=-37.50, date_str=today, txn_id="t3")  # refund

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    res = client.get("/plaid/cards-overview")
    assert res.status_code == 200
    body = res.get_json()

    assert body["month_start"] == month_start
    assert len(body["groups"]) == 1
    cc = body["groups"][0]["accounts"][0]
    assert cc["balance_cents"] == 124300
    assert cc["credit_limit_cents"] == 500000
    assert cc["utilization_pct"] == 24.86
    assert cc["spend_mtd_cents"] == 41250  # (200 + 250 - 37.50) × 100
    assert cc["txn_count_mtd"] == 2  # refund excluded

    assert body["totals"]["credit_balance_cents"] == 124300
    assert body["totals"]["credit_limit_cents"] == 500000
    assert body["totals"]["overall_utilization_pct"] == 24.86
    assert body["totals"]["credit_spend_mtd_cents"] == 41250
```

Note: this test schedules a transaction on day 15, so it relies on the test running between the 15th and the end of the month. If `today.day < 15` would be valid, no special handling needed — but if you run on a day where day-15 has already passed, this still works because we're only using day 15 of the current month. If running on day 31, this still works. If today.day is 1–14 inclusive, replace `today.replace(day=15)` with `today` to keep the seeded date in MTD.

To keep the test deterministic, replace `today.replace(day=15)` with `date_cls.today()` (today's actual date — guaranteed to be in MTD).

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_cards_overview.py::test_cards_overview_credit_card_with_limit -v
```

Expected: PASS (Task 4's implementation already covers this; this test exercises the math).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cards_overview.py
git commit -m "test(cards-overview): credit card with limit — math + grouping"
```

---

## Task 6: `cards-overview` — null limit, loan, depository exclusion, scoping, boundaries

**Files:**
- Test: `tests/test_cards_overview.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cards_overview.py`:

```python
def test_cards_overview_credit_card_no_limit(app, db_session, auth_user):
    """Credit card with null limit: utilization_pct null, available null, still rendered."""
    from src.backend.initialize_database_schema import PlaidAccount

    item = _seed_plaid_item(db_session, auth_user.id)
    db_session.add(PlaidAccount(
        plaid_item_id=item.id, user_id=auth_user.id, plaid_account_id="cc_nolim",
        account_name="No Limit Card", account_mask="0000",
        account_type="credit", account_subtype="credit card",
        balance_cents=10000, credit_limit_cents=None, available_credit_cents=None,
        balance_iso_currency_code="USD",
    ))
    db_session.commit()

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    body = client.get("/plaid/cards-overview").get_json()
    cc = body["groups"][0]["accounts"][0]
    assert cc["utilization_pct"] is None
    assert cc["credit_limit_cents"] is None
    assert cc["available_credit_cents"] is None
    assert body["totals"]["overall_utilization_pct"] is None


def test_cards_overview_loan_excludes_util(app, db_session, auth_user):
    """Loan accounts: no util%, balance + spend only."""
    from src.backend.initialize_database_schema import PlaidAccount

    item = _seed_plaid_item(db_session, auth_user.id)
    db_session.add(PlaidAccount(
        plaid_item_id=item.id, user_id=auth_user.id, plaid_account_id="ln_1",
        account_name="Mortgage", account_mask="8821",
        account_type="loan", account_subtype="mortgage",
        balance_cents=18240000, credit_limit_cents=None, available_credit_cents=None,
        balance_iso_currency_code="USD",
    ))
    db_session.commit()

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    body = client.get("/plaid/cards-overview").get_json()
    assert body["groups"][0]["type"] == "loan"
    loan = body["groups"][0]["accounts"][0]
    assert loan["utilization_pct"] is None
    assert body["totals"]["loan_balance_cents"] == 18240000


def test_cards_overview_excludes_depository(app, db_session, auth_user):
    """Checking / savings accounts must not appear in the response."""
    from src.backend.initialize_database_schema import PlaidAccount

    item = _seed_plaid_item(db_session, auth_user.id)
    db_session.add(PlaidAccount(
        plaid_item_id=item.id, user_id=auth_user.id, plaid_account_id="chk",
        account_name="Checking", account_mask="1111",
        account_type="depository", account_subtype="checking",
        balance_cents=500000, balance_iso_currency_code="USD",
    ))
    db_session.commit()

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    body = client.get("/plaid/cards-overview").get_json()
    assert body["groups"] == []


def test_cards_overview_visibility_filter(app, db_session, auth_user, second_user):
    """User A must not see user B's accounts."""
    from src.backend.initialize_database_schema import PlaidAccount, PlaidItem

    other_item = PlaidItem(
        user_id=second_user.id, plaid_item_id="other_item",
        plaid_institution_id="ins_2", institution_name="Other Bank",
        access_token_encrypted="ENC", status="active", accounts_json="[]",
    )
    db_session.add(other_item)
    db_session.commit()
    db_session.add(PlaidAccount(
        plaid_item_id=other_item.id, user_id=second_user.id, plaid_account_id="cc_other",
        account_name="Other CC", account_mask="9999",
        account_type="credit", account_subtype="credit card",
        balance_cents=100000, credit_limit_cents=200000,
        balance_iso_currency_code="USD",
    ))
    db_session.commit()

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    body = client.get("/plaid/cards-overview").get_json()
    assert body["groups"] == []  # auth_user sees nothing of second_user


def test_cards_overview_mtd_boundary_and_dismissed(app, db_session, auth_user):
    """Last day of prev month excluded; first day of current included; dismissed excluded."""
    from datetime import date as date_cls, timedelta

    item = _seed_plaid_item(db_session, auth_user.id)
    _seed_credit_account(db_session, auth_user.id, item.id)

    today = date_cls.today()
    first_of_month = today.replace(day=1)
    last_of_prev = first_of_month - timedelta(days=1)

    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=999.00,
                 date_str=last_of_prev.isoformat(), txn_id="prev")
    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=10.00,
                 date_str=first_of_month.isoformat(), txn_id="first")
    _seed_staged(db_session, user_id=auth_user.id, plaid_item_id=item.id,
                 plaid_account_id="cc_1", amount=5000.00,
                 date_str=first_of_month.isoformat(), status="dismissed",
                 txn_id="dismissed")

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = auth_user.id
    body = client.get("/plaid/cards-overview").get_json()
    cc = body["groups"][0]["accounts"][0]
    assert cc["spend_mtd_cents"] == 1000  # only $10 first-of-month debit counted
    assert cc["txn_count_mtd"] == 1
```

If `second_user` fixture does not exist, add it to `tests/conftest.py` modeled on `auth_user`. Run the tests; if you see a missing-fixture error, add the fixture.

- [ ] **Step 2: Run all cards-overview tests**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: all PASS.

If `test_cards_overview_credit_card_no_limit` fails because two test runs accumulate accounts, ensure your `db_session` fixture is function-scoped and rolls back between tests. If not, add an explicit cleanup or scope it down.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cards_overview.py
git commit -m "test(cards-overview): edge cases — null limit, loan, depository, scoping, boundary"
```

---

## Task 7: Frontend — Card Usage panel scaffold inside Accounts page

**Files:**
- Modify: `src/frontend/index.html` (around line 3122 — the `page-accounts` div, immediately after `<div class="page-header">…</div>` and before `Connected Accounts`)

- [ ] **Step 1: Add the panel HTML**

Locate the start of the Accounts page (line ~3122):

```html
<div class="page" id="page-accounts">
  <div class="page-header">
    <div>
      <h1>Accounts</h1>
      <p id="accounts-subtitle">…</p>
    </div>
  </div>

  <!-- Panel 1 — Connected Accounts -->
```

Insert this block immediately before the `<!-- Panel 1 — Connected Accounts -->` comment so the new panel appears at the top:

```html
<!-- Panel 0 — Card Usage -->
<div class="card" id="card-usage-card">
  <div class="card-header accounts-card-header">
    <span class="card-title">📊 Card Usage</span>
    <div class="accounts-toolbar">
      <button
        class="btn btn-ghost btn-sm"
        id="card-usage-refresh-btn"
        onclick="refreshCardUsage()"
        title="Refresh balances and reload"
      >
        ↻ Refresh
      </button>
    </div>
  </div>
  <div id="card-usage-summary" class="card-usage-summary" style="display:none"></div>
  <div id="card-usage-banner" class="card-usage-banner" style="display:none"></div>
  <div id="card-usage-body">
    <div class="empty-state"><p>Loading card usage…</p></div>
  </div>
</div>
<!-- /Panel 0 -->
```

- [ ] **Step 2: Add CSS for the panel**

Find the existing `<style>` section that contains `.accounts-card-header` (search for it). Append:

```css
.card-usage-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.card-usage-summary .stat {
  background: var(--surface2, #2c2c2e);
  border-radius: 12px;
  padding: 12px 14px;
}
.card-usage-summary .stat-label {
  font-size: 0.78rem;
  color: var(--muted, #888);
  margin-bottom: 4px;
}
.card-usage-summary .stat-value {
  font-size: 1.05rem;
  font-weight: 600;
}
.card-usage-banner {
  background: var(--warn-bg, #3a2a18);
  color: var(--warn-fg, #f0c060);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 0.9rem;
}
.card-usage-group { margin-top: 12px; }
.card-usage-group h3 {
  font-size: 0.92rem;
  color: var(--muted, #888);
  margin: 12px 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.card-usage-row {
  background: var(--surface2, #2c2c2e);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 8px;
  cursor: pointer;
}
.card-usage-row .row-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
  gap: 12px;
  flex-wrap: wrap;
}
.card-usage-row .row-name { font-weight: 600; }
.card-usage-row .row-util { font-variant-numeric: tabular-nums; }
.card-usage-row .util-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--surface, #1c1c1e);
  overflow: hidden;
  margin: 6px 0 8px;
}
.card-usage-row .util-bar > span {
  display: block;
  height: 100%;
  border-radius: 3px;
}
.util-good { background: #34c759; color: #34c759; }
.util-warn { background: #ff9f0a; color: #ff9f0a; }
.util-bad  { background: #ff453a; color: #ff453a; }
.card-usage-row .row-meta {
  font-size: 0.84rem;
  color: var(--muted, #888);
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
```

(The `color:` lines on `.util-good/warn/bad` are deliberately the same as `background:` so the same class can be applied to text elements like the percentage label without painting a colored block.)

- [ ] **Step 3: Smoke check**

Reload the dev frontend in browser, navigate to Accounts. The `Card Usage` card should appear at the top showing "Loading card usage…". Refresh button visible.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): add Card Usage panel scaffold + CSS"
```

---

## Task 8: Frontend — fetch + safe-DOM render

**Files:**
- Modify: `src/frontend/index.html` (append JS near other Plaid-related functions; search for `loadConnectedAccounts` to find the right neighborhood)

> **Security note:** This task uses `textContent`, `createElement`, and `appendChild` exclusively for any user-controlled string. The only place dynamic CSS class strings are set is via `classList.add()` with values produced by `_utilClass()` (a closed enum: `util-good` / `util-warn` / `util-bad`).

- [ ] **Step 1: Add helpers + loader**

Append to the same JS block:

```javascript
let __cardsOverviewCache = null;
let __cardsOverviewAutoRefreshed = false;

function _fmtMoneyCents(cents, currency) {
  const cur = currency || "USD";
  const abs = Math.abs(cents || 0) / 100;
  const fmt = abs.toLocaleString("en-US", { style: "currency", currency: cur });
  return ((cents || 0) < 0 ? "-" : "") + fmt.replace("-", "");
}

function _utilClass(pct) {
  if (pct == null) return null;
  if (pct < 30) return "util-good";
  if (pct < 70) return "util-warn";
  return "util-bad";
}

function _relativeTime(iso) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const dt = (Date.now() - t) / 1000;
  if (dt < 60) return "just now";
  if (dt < 3600) return Math.floor(dt / 60) + " min ago";
  if (dt < 86400) return Math.floor(dt / 3600) + " hr ago";
  return Math.floor(dt / 86400) + " d ago";
}

async function loadCardsOverview() {
  const body = document.getElementById("card-usage-body");
  const summary = document.getElementById("card-usage-summary");
  const banner = document.getElementById("card-usage-banner");
  if (!body) return;
  body.replaceChildren();
  summary.replaceChildren();
  banner.replaceChildren();
  summary.style.display = "none";
  banner.style.display = "none";
  const loading = document.createElement("div");
  loading.className = "empty-state";
  const lp = document.createElement("p");
  lp.textContent = "Loading card usage…";
  loading.appendChild(lp);
  body.appendChild(loading);

  try {
    const res = await api("/plaid/cards-overview");
    if (!res.ok) {
      _renderCardUsageEmpty("Card usage unavailable.");
      return;
    }
    const data = await res.json();
    __cardsOverviewCache = data;
    renderCardsOverview(data);
    _cardsOverviewAutoRefresh(data);
  } catch (e) {
    _renderCardUsageEmpty("Failed to load card usage.");
  }
}

function _renderCardUsageEmpty(msg) {
  const body = document.getElementById("card-usage-body");
  const summary = document.getElementById("card-usage-summary");
  body.replaceChildren();
  summary.style.display = "none";
  const empty = document.createElement("div");
  empty.className = "empty-state";
  const p = document.createElement("p");
  p.textContent = msg;
  empty.appendChild(p);
  body.appendChild(empty);
}
```

- [ ] **Step 2: Add the renderer**

Append:

```javascript
function _stat(label, value, klass) {
  const wrap = document.createElement("div");
  wrap.className = "stat";
  const l = document.createElement("div");
  l.className = "stat-label";
  l.textContent = label;
  const v = document.createElement("div");
  v.className = "stat-value";
  if (klass) v.classList.add(klass);
  v.textContent = value;
  wrap.appendChild(l);
  wrap.appendChild(v);
  return wrap;
}

function renderCardsOverview(data) {
  const body = document.getElementById("card-usage-body");
  const summary = document.getElementById("card-usage-summary");
  const banner = document.getElementById("card-usage-banner");
  body.replaceChildren();
  summary.replaceChildren();
  banner.replaceChildren();
  summary.style.display = "none";
  banner.style.display = "none";

  if (!data.groups || data.groups.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const p1 = document.createElement("p");
    p1.textContent = "No linked credit cards or loans yet.";
    const p2 = document.createElement("p");
    p2.style.marginTop = "8px";
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = "Link via Plaid below.";
    a.addEventListener("click", function (e) {
      e.preventDefault();
      const btn = document.getElementById("accounts-connect-btn");
      if (btn) btn.click();
    });
    p2.appendChild(a);
    empty.appendChild(p1);
    empty.appendChild(p2);
    body.appendChild(empty);
    return;
  }

  // Summary
  const t = data.totals || {};
  const utilTxt = t.overall_utilization_pct == null ? "—" : t.overall_utilization_pct.toFixed(1) + "%";
  summary.style.display = "grid";
  summary.appendChild(_stat("Total credit balance", _fmtMoneyCents(t.credit_balance_cents || 0, "USD")));
  summary.appendChild(_stat("Total credit limit", _fmtMoneyCents(t.credit_limit_cents || 0, "USD")));
  summary.appendChild(_stat("Overall utilization", utilTxt, _utilClass(t.overall_utilization_pct)));
  summary.appendChild(_stat("Credit spend (this month)", _fmtMoneyCents(t.credit_spend_mtd_cents || 0, "USD")));

  // Cross-currency note
  const hasNonUsd = data.groups.some(g => g.accounts.some(a => (a.currency || "USD") !== "USD"));
  if (hasNonUsd) {
    banner.style.display = "block";
    banner.textContent = "Some accounts use a non-USD currency and are excluded from totals.";
  }

  data.groups.forEach(group => {
    const wrap = document.createElement("div");
    wrap.className = "card-usage-group";
    const h = document.createElement("h3");
    h.textContent = group.label;
    wrap.appendChild(h);

    const isCredit = group.type === "credit_card";
    group.accounts.forEach(a => {
      wrap.appendChild(_renderCardRow(a, isCredit));
    });
    body.appendChild(wrap);
  });
}

function _renderCardRow(a, isCredit) {
  const row = document.createElement("div");
  row.className = "card-usage-row";
  row.addEventListener("click", function () { _drillIntoAccount(a.plaid_account_id); });

  const head = document.createElement("div");
  head.className = "row-head";

  const name = document.createElement("span");
  name.className = "row-name";
  // Build name safely: "💳 " + name + " ····" + mask
  const prefix = isCredit ? "💳 " : "🏦 ";
  name.textContent = prefix + (a.name || "Account") + " ····" + (a.mask || "");
  head.appendChild(name);

  const util = document.createElement("span");
  util.className = "row-util";
  const utilClass = _utilClass(a.utilization_pct);
  if (isCredit) {
    if (utilClass) util.classList.add(utilClass);
    const balanceTxt = _fmtMoneyCents(a.balance_cents || 0, a.currency);
    const limitTxt = a.credit_limit_cents == null ? "—" : _fmtMoneyCents(a.credit_limit_cents, a.currency);
    const utilTxt = a.utilization_pct == null ? "—" : a.utilization_pct.toFixed(1) + "%";
    util.textContent = balanceTxt + " / " + limitTxt + " · " + utilTxt;
  } else {
    util.textContent = _fmtMoneyCents(a.balance_cents || 0, a.currency);
  }
  head.appendChild(util);

  row.appendChild(head);

  if (isCredit) {
    const bar = document.createElement("div");
    bar.className = "util-bar";
    const fill = document.createElement("span");
    if (utilClass) fill.classList.add(utilClass);
    const w = a.utilization_pct == null ? 0 : Math.min(100, a.utilization_pct);
    fill.style.width = w + "%";
    bar.appendChild(fill);
    row.appendChild(bar);
  }

  const meta = document.createElement("div");
  meta.className = "row-meta";

  const spendCents = a.spend_mtd_cents || 0;
  const spendSpan = document.createElement("span");
  spendSpan.textContent = "This month: " + _fmtMoneyCents(spendCents, a.currency) +
    (spendCents < 0 ? " (net refund)" : "") +
    " · " + (a.txn_count_mtd || 0) + " txns";
  meta.appendChild(spendSpan);

  if (a.available_credit_cents != null) {
    const avail = document.createElement("span");
    avail.textContent = "Available: " + _fmtMoneyCents(a.available_credit_cents, a.currency);
    meta.appendChild(avail);
  }

  const updated = document.createElement("span");
  updated.textContent = a.balance_updated_at
    ? "Updated " + _relativeTime(a.balance_updated_at)
    : "Not refreshed yet";
  meta.appendChild(updated);

  row.appendChild(meta);
  return row;
}

function _drillIntoAccount(plaidAccountId) {
  // Phase 1: scroll to existing transaction-review UI on this page
  const txnSection = document.getElementById("accounts-staged-card") ||
                     document.getElementById("accounts-transactions-card");
  if (txnSection) txnSection.scrollIntoView({ behavior: "smooth", block: "start" });
}
```

- [ ] **Step 3: Add an entry-point hook so the panel loads when Accounts page opens**

Find where the Accounts page mount path lives. Search for `loadConnectedAccounts` in `src/frontend/index.html`. Wherever `loadConnectedAccounts()` is invoked (from the `nav('accounts'...)` path or from an `if (page === 'accounts')` branch), call `loadCardsOverview()` immediately after.

If the trigger is not obvious, search for `case "accounts":` or `if (page === "accounts")` and add `loadCardsOverview();` inside that branch.

- [ ] **Step 4: Manual smoke test in browser**

Start the dev server. Open the app, navigate to **Accounts**. Confirm:

- `Card Usage` panel renders at top of page
- If you have linked credit cards: summary stats show + at least one card row with util bar
- If you have no credit/loan accounts: empty state with link to Plaid Connect
- Account names render as plain text even if they contain unusual characters (data is set via `textContent`)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): card usage panel — fetch + safe-DOM render with util bars"
```

---

## Task 9: Frontend — Refresh button + auto-stale-refresh

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add `refreshCardUsage` and auto-stale logic**

Append to the same JS block:

```javascript
async function refreshCardUsage() {
  const btn = document.getElementById("card-usage-refresh-btn");
  if (btn) { btn.disabled = true; btn.textContent = "↻ Refreshing…"; }
  try {
    const res = await api("/plaid/accounts/refresh-balances", { method: "POST" });
    if (res.status === 429) {
      const data = await res.json().catch(function () { return {}; });
      const sec = data.retry_after_seconds || 60;
      toast("Refreshed recently. Try again in " + sec + "s.", "info");
    } else if (!res.ok) {
      toast("Refresh failed. Cached data shown.", "error");
    }
  } catch (e) {
    toast("Refresh failed.", "error");
  }
  await loadCardsOverview();
  if (btn) { btn.disabled = false; btn.textContent = "↻ Refresh"; }
}

function _cardsOverviewAutoRefresh(data) {
  if (__cardsOverviewAutoRefreshed) return;
  if (!data.groups || data.groups.length === 0) return;

  let newest = 0;
  data.groups.forEach(function (g) {
    g.accounts.forEach(function (a) {
      if (a.balance_updated_at) {
        const t = new Date(a.balance_updated_at).getTime();
        if (t > newest) newest = t;
      }
    });
  });
  if (newest === 0) return;

  const ageMs = Date.now() - newest;
  if (ageMs > 60 * 60 * 1000) {
    __cardsOverviewAutoRefreshed = true;
    refreshCardUsage();
  }
  if (ageMs > 24 * 60 * 60 * 1000) {
    const banner = document.getElementById("card-usage-banner");
    if (banner) {
      banner.style.display = "block";
      banner.textContent = "Balances may be outdated. Tap Refresh.";
    }
  }
}
```

- [ ] **Step 2: Manual smoke test**

In browser:

- Click Refresh → button disables → toast on 429 if previously refreshed → list re-renders
- Wait > 1 hour (or temporarily lower the threshold to test) → reopen Accounts page → auto-refresh fires once

- [ ] **Step 3: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(accounts): refresh button + 1hr auto-stale-refresh for card usage"
```

---

## Task 10: Final verification + smoke checklist

- [ ] **Step 1: Run the full new test file**

```bash
pytest tests/test_cards_overview.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run the affected Plaid test files for regressions**

```bash
pytest tests/test_plaid_integration.py tests/test_cards_overview.py -v
```

Expected: all PASS.

- [ ] **Step 3: Manual end-to-end smoke test (dev)**

In a browser, log in as a user with at least one Plaid credit card linked. Navigate to **Accounts** and verify:

- [ ] Card Usage panel appears at top
- [ ] Summary block: total credit balance, total credit limit, overall utilization (color-coded), credit spend MTD
- [ ] At least one credit card row showing balance / limit / util%, util bar with correct color (green <30, amber 30–70, red >70)
- [ ] Loan rows (if any) show balance only — no util bar
- [ ] Refunds net out in spend; refund-only month shows "(net refund)"
- [ ] Tap a card row → scrolls to transactions section
- [ ] Click Refresh → either re-renders or toasts 429
- [ ] Util bar capped at 100% width if util > 100%; numeric value shown unclamped, red
- [ ] On a fresh user with no Plaid: empty state with link to connect

- [ ] **Step 4: No new commit required**

If smoke test passes, the feature is ready. If anything fails, fix in a follow-up commit.

---

## Self-review

**Spec coverage:**
- §1 Architecture → Tasks 1–4 (schema + serializer + endpoint)
- §2 Data Model → Task 1 (migration + model), Task 2 (refresh persistence), Task 4 (period-spend join)
- §3 API → Task 4 (route, response shape, type bucketing, compute rules)
- §4 Frontend → Tasks 7, 8, 9 (panel scaffold, render, refresh) — note spec deviation: panel inside Accounts page, not new nav entry
- §5 Errors + Edge Cases → Task 4 (server-side rules), Task 8 (empty state, drill, currency banner), Task 9 (refresh fail / 429 / stale banner)
- §6 Testing → Tasks 1, 2, 3, 4, 5, 6 cover all named pytest cases

**Placeholder scan:** No "TBD"/"TODO"/"similar to". Every code block is complete enough to paste, with one explicit TODO marker for the engineer to look up the alembic `down_revision` in Task 1 step 3 (resolved via the file they already have on disk).

**Type consistency:** `credit_limit_cents`/`available_credit_cents` (snake_case) used identically across migration, model, serializer, response JSON, frontend reads. `utilization_pct` used identically in JSON + frontend. `plaid_account_id` is the join key throughout.

**Security:** Frontend uses `textContent`/`createElement`/`classList.add` exclusively for any string sourced from API data. No `innerHTML` interpolation of dynamic content.

Two spec items are deferred to a future plan, by spec: Phase 2 (Plaid Liabilities API) and statement-cycle period spend. These are explicitly out of scope for this plan.
