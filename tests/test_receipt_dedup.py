"""Tests for /receipts/dedup-scan and /receipts/merge.

Phase 3 of the Plaid duplicate-receipt story. Phase 1 prevents NEW dupes;
these endpoints let a user clean up EXISTING ones from before Guard B
was in place.
"""
from __future__ import annotations

import os
from datetime import date as _date, datetime as _dt, time as _time, timedelta

import pytest

# Force in-memory SQLite even if the shell has DATABASE_URL exported
# (e.g. inside the prod container where setdefault would be a no-op
# and tests could mutate real data).
os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture(scope="module")
def user_ids(app):
    """Seed two users; tests reference user_a and user_b."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    s = SF()
    ids = {}
    try:
        for key, role in (("user_a", "admin"), ("user_b", "user")):
            existing = s.query(User).filter_by(email=f"{key}@dedup.test").first()
            if existing:
                ids[key] = existing.id
                continue
            u = User(
                name=key,
                email=f"{key}@dedup.test",
                role=role,
                is_active=1,
                password_hash="x",
                session_version=0,
            )
            s.add(u)
            s.flush()
            ids[key] = u.id
        s.commit()
    finally:
        s.close()
    return ids


def _invoke(app, method, path, user_id, json_data=None):
    """Forge g.current_user + g.db_session to exercise auth-decorated views."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context(path, method=method, json=json_data):
            g.current_user = user
            g.db_session = session
            path_only = path.split("?", 1)[0]
            endpoint, args = app.url_map.bind("").match(path_only, method=method)
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            rv = fn(**args)
            if isinstance(rv, tuple):
                body = rv[0].get_json() if hasattr(rv[0], "get_json") else None
                return rv[1], body
            return 200, rv.get_json() if hasattr(rv, "get_json") else rv
    finally:
        session.close()


def _mk_purchase(user_id, store_name, amount, when, items=0, with_receipt=False):
    """Create a Store + Purchase + optional ReceiptItems + TelegramReceipt."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        Product,
        Purchase,
        ReceiptItem,
        Store,
        TelegramReceipt,
    )
    _, SF = _get_db()
    s = SF()
    try:
        store = Store(name=store_name)
        s.add(store)
        s.flush()
        dt = _dt.combine(when, _time.min) if not isinstance(when, _dt) else when
        p = Purchase(user_id=user_id, store_id=store.id, total_amount=amount, date=dt)
        s.add(p)
        s.flush()
        for i in range(items):
            # Products have uq(name, category) and persist across _wipe
            # calls — include a random suffix so each test run is fresh.
            nonce = os.urandom(3).hex()
            prod = Product(
                name=f"Item {i}-{p.id}-{nonce}",
                category=f"grocery-{p.id}-{i}-{nonce}",
            )
            s.add(prod)
            s.flush()
            s.add(ReceiptItem(
                purchase_id=p.id,
                product_id=prod.id,
                quantity=1,
                unit_price=float(amount) / max(items, 1),
            ))
        if with_receipt:
            s.add(TelegramReceipt(
                telegram_user_id=str(user_id),
                purchase_id=p.id,
                status="processed",
                image_path=f"/fake/{p.id}.jpg",
            ))
        s.commit()
        return p.id
    finally:
        s.close()


def _wipe(user_id):
    """Reset all dedup state for one user between tests."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        DedupDismissal,
        PlaidStagedTransaction,
        Purchase,
        ReceiptItem,
        Store,
        TelegramReceipt,
    )
    _, SF = _get_db()
    s = SF()
    try:
        s.query(DedupDismissal).filter_by(user_id=user_id).delete(synchronize_session=False)
        pids = [p.id for p in s.query(Purchase).filter_by(user_id=user_id).all()]
        if pids:
            s.query(ReceiptItem).filter(ReceiptItem.purchase_id.in_(pids)).delete(synchronize_session=False)
            s.query(TelegramReceipt).filter(TelegramReceipt.purchase_id.in_(pids)).delete(synchronize_session=False)
            s.query(PlaidStagedTransaction).filter(
                PlaidStagedTransaction.confirmed_purchase_id.in_(pids)
            ).update({"confirmed_purchase_id": None}, synchronize_session=False)
            s.query(Purchase).filter(Purchase.id.in_(pids)).delete(synchronize_session=False)
        # Orphan Stores are harmless — other tables (ProductSnapshot,
        # PriceHistory) may still FK-ref them, so we leave them in place.
        s.commit()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# dedup-scan
# ---------------------------------------------------------------------------

def test_dedup_scan_finds_alias_pair(app, user_ids):
    """Two purchases with alias-matching merchants + same amount + same date
    should be reported as a dupe pair."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    # OCR receipt: has 3 items + image → should be 'keep'.
    keep_id = _mk_purchase(uid, "Anthropic, PBC", 20.00, today, items=3, with_receipt=True)
    # Plaid-confirmed stub: no items, no image → should be 'drop'.
    drop_id = _mk_purchase(uid, "Claude.Ai Su", 20.00, today, items=0, with_receipt=False)

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body
    assert len(body["pairs"]) == 1
    pair = body["pairs"][0]
    assert pair["keep_id"] == keep_id
    assert pair["drop_id"] == drop_id
    assert pair["keep"]["item_count"] == 3
    assert pair["keep"]["has_image"] is True
    assert pair["drop"]["item_count"] == 0
    _wipe(uid)


def test_dedup_scan_respects_date_window(app, user_ids):
    """Purchases >3 days apart should NOT be paired."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    _mk_purchase(uid, "Anthropic", 20.00, today)
    _mk_purchase(uid, "Claude.Ai", 20.00, today - timedelta(days=5))  # outside ±3d

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body
    assert body["pairs"] == []
    _wipe(uid)


def test_dedup_scan_respects_amount_epsilon(app, user_ids):
    """Amount diff > $0.02 should NOT pair."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    _mk_purchase(uid, "Target", 50.00, today)
    _mk_purchase(uid, "TGT", 50.05, today)  # Δ=$0.05 → miss

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body
    assert body["pairs"] == []
    _wipe(uid)


def test_dedup_scan_user_isolation(app, user_ids):
    """User A's duplicates must not appear in User B's scan."""
    uid_a = user_ids["user_a"]
    uid_b = user_ids["user_b"]
    _wipe(uid_a)
    _wipe(uid_b)
    today = _date.today()
    _mk_purchase(uid_a, "Netflix", 15.00, today)
    _mk_purchase(uid_a, "Netflix.com", 15.00, today)

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid_b)
    assert status == 200, body
    assert body["pairs"] == []
    _wipe(uid_a)


def test_dedup_scan_never_pairs_a_row_twice(app, user_ids):
    """Three near-identical rows should produce ONE pair, not three."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    _mk_purchase(uid, "Amazon", 9.99, today)
    _mk_purchase(uid, "AMZN Mktp", 9.99, today)
    _mk_purchase(uid, "Amazon.com", 9.99, today)

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body
    # First pair locks one row as drop; remaining row has no unpaired partner.
    assert len(body["pairs"]) == 1
    _wipe(uid)


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def test_merge_happy_path_consolidates_rows(app, user_ids):
    """After merge, drop Purchase + its TelegramReceipt are gone; keep remains."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        Purchase,
        ReceiptItem,
        TelegramReceipt,
    )

    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    keep_id = _mk_purchase(uid, "Kroger", 30.00, today, items=2, with_receipt=True)
    drop_id = _mk_purchase(uid, "Kroger", 30.00, today, items=0, with_receipt=True)

    status, body = _invoke(
        app, "POST", "/receipts/merge", uid,
        json_data={"keep_id": keep_id, "drop_id": drop_id},
    )
    assert status == 200, body
    assert body["kept_purchase_id"] == keep_id
    assert body["dropped_purchase_id"] == drop_id

    _, SF = _get_db()
    s = SF()
    try:
        assert s.get(Purchase, keep_id) is not None
        assert s.get(Purchase, drop_id) is None
        # Keep's TelegramReceipt is preserved; drop's is deleted (not
        # reparented, since keep already had one).
        remaining = s.query(TelegramReceipt).filter_by(purchase_id=keep_id).count()
        assert remaining == 1
        # Items stay attached to keep.
        assert s.query(ReceiptItem).filter_by(purchase_id=keep_id).count() == 2
    finally:
        s.close()
    _wipe(uid)


def test_merge_reparents_staged_tx_confirmed_pointer(app, user_ids):
    """If a staged tx was confirmed to drop, after merge it should point to keep."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidItem,
        PlaidStagedTransaction,
    )

    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    keep_id = _mk_purchase(uid, "Tesla", 100.00, today, items=1, with_receipt=True)
    drop_id = _mk_purchase(uid, "Tesla Inc", 100.00, today, items=0, with_receipt=False)

    _, SF = _get_db()
    s = SF()
    try:
        # Need a plaid item first for the FK.
        item = PlaidItem(
            user_id=uid,
            plaid_item_id=f"dedup_test_item_{uid}_{drop_id}",
            institution_id="ins_x",
            institution_name="X",
            access_token_encrypted="e",
            accounts_json="[]",
            status="active",
        )
        s.add(item)
        s.flush()
        staged = PlaidStagedTransaction(
            plaid_item_id=item.id,
            user_id=uid,
            plaid_transaction_id=f"ptx_dedup_{drop_id}_{os.urandom(3).hex()}",
            plaid_account_id="acc",
            amount=100.00,
            iso_currency_code="USD",
            transaction_date=today,
            name="Tesla Inc",
            merchant_name="Tesla",
            status="confirmed",
            confirmed_purchase_id=drop_id,
            raw_json="{}",
        )
        s.add(staged)
        s.commit()
        staged_id = staged.id
    finally:
        s.close()

    status, body = _invoke(
        app, "POST", "/receipts/merge", uid,
        json_data={"keep_id": keep_id, "drop_id": drop_id},
    )
    assert status == 200, body

    s = SF()
    try:
        reloaded = s.get(PlaidStagedTransaction, staged_id)
        assert reloaded.confirmed_purchase_id == keep_id
    finally:
        s.close()
    _wipe(uid)


def test_merge_rejects_cross_user_ids(app, user_ids):
    """User A cannot merge involving User B's Purchase."""
    uid_a = user_ids["user_a"]
    uid_b = user_ids["user_b"]
    _wipe(uid_a)
    _wipe(uid_b)
    today = _date.today()
    pid_a = _mk_purchase(uid_a, "Shell", 40.00, today)
    pid_b = _mk_purchase(uid_b, "Shell Oil", 40.00, today)

    status, body = _invoke(
        app, "POST", "/receipts/merge", uid_a,
        json_data={"keep_id": pid_a, "drop_id": pid_b},
    )
    assert status == 404, body
    _wipe(uid_a)
    _wipe(uid_b)


def test_merge_rejects_same_id_pair(app, user_ids):
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    pid = _mk_purchase(uid, "Spotify", 10.00, today)
    status, body = _invoke(
        app, "POST", "/receipts/merge", uid,
        json_data={"keep_id": pid, "drop_id": pid},
    )
    assert status == 400, body
    _wipe(uid)


def test_merge_rejects_bad_payload(app, user_ids):
    uid = user_ids["user_a"]
    status, body = _invoke(
        app, "POST", "/receipts/merge", uid,
        json_data={"keep_id": "not-an-int"},
    )
    assert status == 400, body


# ---------------------------------------------------------------------------
# dedup-dismiss — persistent "not a duplicate" decisions
# ---------------------------------------------------------------------------

def test_dismiss_hides_pair_from_future_scans(app, user_ids):
    """After dismissing, the same pair should not show up again.

    Regression target: user reported two legit same-day same-amount charges
    ("Meena" dance vs music) kept reappearing in the dedup UI with no way
    to keep both.
    """
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    a_id = _mk_purchase(uid, "Meena School Of Dance", 100.00, today)
    b_id = _mk_purchase(uid, "Meena School Of Music", 100.00, today)

    status, body = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body
    assert len(body["pairs"]) == 1, "alias-match should flag the pair pre-dismiss"
    pair = body["pairs"][0]

    status, dbody = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid,
        json_data={"keep_id": pair["keep_id"], "drop_id": pair["drop_id"]},
    )
    assert status == 200, dbody
    assert dbody["dismissed"] is True
    assert dbody["created"] is True
    assert dbody["purchase_id_low"] == min(a_id, b_id)
    assert dbody["purchase_id_high"] == max(a_id, b_id)

    status, body2 = _invoke(app, "GET", "/receipts/dedup-scan", uid)
    assert status == 200, body2
    assert body2["pairs"] == [], "dismissed pair must not resurface"
    _wipe(uid)


def test_dismiss_is_idempotent(app, user_ids):
    """Dismissing the same pair twice should succeed both times (created=False on repeat)."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    a_id = _mk_purchase(uid, "Some Shop", 50.00, today)
    b_id = _mk_purchase(uid, "Some Shop", 50.00, today)

    payload = {"keep_id": a_id, "drop_id": b_id}
    status, body = _invoke(app, "POST", "/receipts/dedup-dismiss", uid, json_data=payload)
    assert status == 200, body
    assert body["created"] is True

    status2, body2 = _invoke(app, "POST", "/receipts/dedup-dismiss", uid, json_data=payload)
    assert status2 == 200, body2
    assert body2["created"] is False, "second dismiss must be a no-op, not a duplicate row"
    _wipe(uid)


def test_dismiss_is_order_independent(app, user_ids):
    """Dismissing (a,b) and then (b,a) should hit the same row (low/high normalization)."""
    uid = user_ids["user_a"]
    _wipe(uid)
    today = _date.today()
    a_id = _mk_purchase(uid, "Merchant X", 12.34, today)
    b_id = _mk_purchase(uid, "Merchant X", 12.34, today)

    status, body = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid,
        json_data={"keep_id": a_id, "drop_id": b_id},
    )
    assert status == 200 and body["created"] is True

    status2, body2 = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid,
        json_data={"keep_id": b_id, "drop_id": a_id},
    )
    assert status2 == 200, body2
    assert body2["created"] is False, "reversed-order dismiss must not create a second row"
    _wipe(uid)


def test_dismiss_rejects_cross_user_ids(app, user_ids):
    """A user must not be able to dismiss a pair that includes another user's purchase."""
    uid_a = user_ids["user_a"]
    uid_b = user_ids["user_b"]
    _wipe(uid_a)
    _wipe(uid_b)
    today = _date.today()
    a_id = _mk_purchase(uid_a, "Shared Name", 10.00, today)
    b_id = _mk_purchase(uid_b, "Shared Name", 10.00, today)

    status, body = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid_a,
        json_data={"keep_id": a_id, "drop_id": b_id},
    )
    assert status == 404, body
    _wipe(uid_a)
    _wipe(uid_b)


def test_dismiss_rejects_same_id_pair(app, user_ids):
    uid = user_ids["user_a"]
    _wipe(uid)
    pid = _mk_purchase(uid, "Solo", 9.99, _date.today())
    status, body = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid,
        json_data={"keep_id": pid, "drop_id": pid},
    )
    assert status == 400, body
    _wipe(uid)


def test_dismiss_rejects_bad_payload(app, user_ids):
    uid = user_ids["user_a"]
    status, body = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid,
        json_data={"keep_id": "nope"},
    )
    assert status == 400, body


def test_dismiss_is_user_scoped(app, user_ids):
    """User A's dismiss should not suppress an unrelated dupe pair for user B."""
    uid_a = user_ids["user_a"]
    uid_b = user_ids["user_b"]
    _wipe(uid_a)
    _wipe(uid_b)
    today = _date.today()
    a1 = _mk_purchase(uid_a, "Alias Co", 7.50, today)
    a2 = _mk_purchase(uid_a, "Alias Co", 7.50, today)
    b1 = _mk_purchase(uid_b, "Alias Co", 7.50, today)
    b2 = _mk_purchase(uid_b, "Alias Co", 7.50, today)

    # user_a dismisses their pair.
    status, body = _invoke(
        app, "POST", "/receipts/dedup-dismiss", uid_a,
        json_data={"keep_id": a1, "drop_id": a2},
    )
    assert status == 200, body

    # user_a's scan: empty. user_b's scan: still flags their pair.
    status_a, body_a = _invoke(app, "GET", "/receipts/dedup-scan", uid_a)
    assert status_a == 200 and body_a["pairs"] == []
    status_b, body_b = _invoke(app, "GET", "/receipts/dedup-scan", uid_b)
    assert status_b == 200, body_b
    assert len(body_b["pairs"]) == 1
    ids = {body_b["pairs"][0]["keep_id"], body_b["pairs"][0]["drop_id"]}
    assert ids == {b1, b2}
    _wipe(uid_a)
    _wipe(uid_b)
