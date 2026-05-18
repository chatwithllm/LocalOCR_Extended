# tests/test_shared_dining.py
from __future__ import annotations
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")


@pytest.fixture
def session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "test.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


@pytest.fixture
def purchase(session):
    from src.backend.initialize_database_schema import Purchase
    from datetime import datetime, timezone
    p = Purchase(total_amount=370.20, date=datetime.now(timezone.utc), domain="restaurant")
    session.add(p)
    session.commit()
    return p


def test_dining_contact_round_trip(session):
    from src.backend.initialize_database_schema import DiningContact
    c = DiningContact(name="John Smith", phone="555-1234")
    session.add(c)
    session.commit()
    fetched = session.get(DiningContact, c.id)
    assert fetched.name == "John Smith"
    assert fetched.phone == "555-1234"


def test_shared_expense_round_trip(session, purchase):
    from src.backend.initialize_database_schema import SharedExpense
    exp = SharedExpense(
        purchase_id=purchase.id,
        total_amount=370.20,
        my_amount=92.55,
        payment_scenario="PAID_ALL",
    )
    session.add(exp)
    session.commit()
    fetched = session.get(SharedExpense, exp.id)
    assert fetched.payment_scenario == "PAID_ALL"
    assert fetched.my_amount == 92.55


def test_shared_participant_round_trip(session, purchase):
    from src.backend.initialize_database_schema import SharedExpense, SharedParticipant
    exp = SharedExpense(purchase_id=purchase.id, total_amount=370.20, my_amount=92.55, payment_scenario="PAID_ALL")
    session.add(exp)
    session.flush()
    p = SharedParticipant(shared_expense_id=exp.id, is_self=True, share_amount=92.55, ad_hoc_name=None)
    session.add(p)
    session.commit()
    fetched = session.get(SharedParticipant, p.id)
    assert fetched.is_self is True
    assert fetched.share_amount == 92.55


def test_shared_debt_round_trip(session, purchase):
    from src.backend.initialize_database_schema import SharedExpense, SharedParticipant, SharedDebt
    exp = SharedExpense(purchase_id=purchase.id, total_amount=100.0, my_amount=50.0, payment_scenario="PAID_ALL")
    session.add(exp)
    session.flush()
    p = SharedParticipant(shared_expense_id=exp.id, is_self=False, share_amount=50.0, ad_hoc_name="Ali")
    session.add(p)
    session.flush()
    d = SharedDebt(shared_expense_id=exp.id, participant_id=p.id, direction="THEY_OWE_ME", amount=50.0)
    session.add(d)
    session.commit()
    fetched = session.get(SharedDebt, d.id)
    assert fetched.direction == "THEY_OWE_ME"
    assert fetched.settled is False


def test_telegram_split_session_round_trip(session):
    from src.backend.initialize_database_schema import TelegramSplitSession
    s = TelegramSplitSession(chat_id="99999", state={"step": "select_receipt"})
    session.add(s)
    session.commit()
    fetched = session.get(TelegramSplitSession, "99999")
    assert fetched.state["step"] == "select_receipt"


# --- Service layer tests ---

def test_create_paid_all_creates_they_owe_me_debts(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense
    from src.backend.initialize_database_schema import SharedDebt

    participants = [
        {"is_self": True, "share_amount": 92.55, "ad_hoc_name": None, "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "John", "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Sarah", "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Ali",   "contact_id": None},
    ]
    expense = create_shared_expense(session, purchase.id, "PAID_ALL", participants)

    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 3
    assert all(d.direction == "THEY_OWE_ME" for d in debts)
    assert expense.my_amount == 92.55


def test_create_paid_own_creates_no_debts(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense
    from src.backend.initialize_database_schema import SharedDebt

    participants = [
        {"is_self": True, "share_amount": 92.55, "ad_hoc_name": None, "contact_id": None},
        {"is_self": False, "share_amount": 277.65, "ad_hoc_name": "Others", "contact_id": None},
    ]
    expense = create_shared_expense(session, purchase.id, "PAID_OWN", participants)

    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 0
    assert expense.payment_scenario == "PAID_OWN"
    assert expense.my_amount == 92.55


def test_create_owed_creates_i_owe_them_debt(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense
    from src.backend.initialize_database_schema import SharedDebt

    participants = [
        {"is_self": True, "share_amount": 92.55, "ad_hoc_name": None, "contact_id": None},
        {"is_self": False, "share_amount": 277.65, "ad_hoc_name": "John (paid)", "contact_id": None, "payer": True},
    ]
    expense = create_shared_expense(session, purchase.id, "OWED", participants)

    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 1
    assert debts[0].direction == "I_OWE_THEM"
    assert debts[0].amount == pytest.approx(92.55)


def test_create_raises_when_amounts_dont_match(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, SplitValidationError

    participants = [
        {"is_self": True, "share_amount": 100.0, "ad_hoc_name": None, "contact_id": None},
        {"is_self": False, "share_amount": 100.0, "ad_hoc_name": "Bob", "contact_id": None},
    ]
    with pytest.raises(SplitValidationError, match="sum"):
        create_shared_expense(session, purchase.id, "PAID_ALL", participants)


def test_create_raises_on_duplicate(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, SplitValidationError

    participants = [
        {"is_self": True, "share_amount": 185.10, "ad_hoc_name": None, "contact_id": None},
        {"is_self": False, "share_amount": 185.10, "ad_hoc_name": "Bob", "contact_id": None},
    ]
    create_shared_expense(session, purchase.id, "PAID_ALL", participants)
    with pytest.raises(SplitValidationError, match="already has"):
        create_shared_expense(session, purchase.id, "PAID_ALL", participants)


@pytest.fixture
def paid_all_expense(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense
    from src.backend.initialize_database_schema import DiningContact

    contact = DiningContact(name="John Smith")
    session.add(contact)
    session.flush()

    participants = [
        {"is_self": True,  "share_amount": 92.55, "ad_hoc_name": None,  "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": None,  "contact_id": contact.id},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Ali", "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Sam", "contact_id": None},
    ]
    exp = create_shared_expense(session, purchase.id, "PAID_ALL", participants)
    return exp, contact


def test_settle_debt_marks_settled(session, paid_all_expense):
    from src.backend.manage_shared_dining import settle_debt
    from src.backend.initialize_database_schema import SharedDebt

    expense, _ = paid_all_expense
    debt = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).first()
    assert debt.settled is False

    settle_debt(session, debt.id, note="Cash paid")
    session.expire_all()

    updated = session.get(SharedDebt, debt.id)
    assert updated.settled is True
    assert updated.settled_note == "Cash paid"
    assert updated.settled_at is not None


def test_get_balance_with_contact(session, paid_all_expense):
    from src.backend.manage_shared_dining import get_balance_with_contact

    expense, contact = paid_all_expense
    balance = get_balance_with_contact(session, contact.id)
    assert balance == pytest.approx(92.55)


def test_get_balance_after_settle(session, paid_all_expense):
    from src.backend.manage_shared_dining import get_balance_with_contact, settle_all_with_contact

    expense, contact = paid_all_expense
    count = settle_all_with_contact(session, contact.id)
    assert count == 1

    balance = get_balance_with_contact(session, contact.id)
    assert balance == 0.0


def test_get_all_balances_excludes_zero(session, paid_all_expense):
    from src.backend.manage_shared_dining import get_all_balances, settle_all_with_contact

    expense, contact = paid_all_expense
    balances = get_all_balances(session)
    assert any(b["contact_id"] == contact.id for b in balances)

    settle_all_with_contact(session, contact.id)
    balances_after = get_all_balances(session)
    assert not any(b["contact_id"] == contact.id for b in balances_after)


def test_merge_contact_repoints_participant(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, merge_contact
    from src.backend.initialize_database_schema import DiningContact, SharedParticipant

    participants = [
        {"is_self": True,  "share_amount": 185.10, "ad_hoc_name": None,  "contact_id": None},
        {"is_self": False, "share_amount": 185.10, "ad_hoc_name": "Bob", "contact_id": None},
    ]
    expense = create_shared_expense(session, purchase.id, "PAID_ALL", participants)

    ad_hoc = session.query(SharedParticipant).filter_by(
        shared_expense_id=expense.id, is_self=False
    ).one()
    assert ad_hoc.contact_id is None

    contact = DiningContact(name="Bob Jones")
    session.add(contact)
    session.commit()

    merge_contact(session, ad_hoc.id, contact.id)
    session.expire_all()

    updated = session.get(SharedParticipant, ad_hoc.id)
    assert updated.contact_id == contact.id
    assert updated.ad_hoc_name is None


def test_update_split_paid_all_adjusts_shares(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, update_split
    from src.backend.initialize_database_schema import SharedDebt, SharedParticipant

    participants = [
        {"is_self": True,  "share_amount": 92.55, "ad_hoc_name": None,  "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "John", "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Ali",  "contact_id": None},
        {"is_self": False, "share_amount": 92.55, "ad_hoc_name": "Sam",  "contact_id": None},
    ]
    expense = create_shared_expense(session, purchase.id, "PAID_ALL", participants)

    # Get the self participant
    self_p = session.query(SharedParticipant).filter_by(
        shared_expense_id=expense.id, is_self=True
    ).one()

    # Update self share to 120.00; others should share the remaining 250.20
    updated = update_split(session, expense.id, self_p.id, 120.00)
    session.expire_all()

    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 3  # one per non-self participant
    assert all(d.direction == "THEY_OWE_ME" for d in debts)
    total_debts = sum(d.amount for d in debts)
    assert abs(total_debts + 120.00 - 370.20) < 0.05  # debts + self share ≈ total


def test_update_split_owed_preserves_debt(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, update_split
    from src.backend.initialize_database_schema import SharedDebt, SharedParticipant

    participants = [
        {"is_self": True,  "share_amount": 92.55, "ad_hoc_name": None,  "contact_id": None},
        {"is_self": False, "share_amount": 277.65, "ad_hoc_name": "John", "contact_id": None, "payer": True},
    ]
    expense = create_shared_expense(session, purchase.id, "OWED", participants)

    # Verify initial debt exists
    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 1
    assert debts[0].direction == "I_OWE_THEM"

    # Update self share amount
    self_p = session.query(SharedParticipant).filter_by(
        shared_expense_id=expense.id, is_self=True
    ).one()
    updated = update_split(session, expense.id, self_p.id, 100.00)
    session.expire_all()

    debts_after = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts_after) == 1
    assert debts_after[0].direction == "I_OWE_THEM"
    assert debts_after[0].amount == pytest.approx(100.00)


def test_update_split_raises_on_invalid_expense(session):
    from src.backend.manage_shared_dining import update_split, SplitValidationError
    with pytest.raises(SplitValidationError, match="not found"):
        update_split(session, 99999, 1, 50.0)


def test_update_split_paid_own_no_debts(session, purchase):
    from src.backend.manage_shared_dining import create_shared_expense, update_split
    from src.backend.initialize_database_schema import SharedDebt, SharedParticipant

    participants = [
        {"is_self": True,  "share_amount": 185.10, "ad_hoc_name": None,  "contact_id": None},
        {"is_self": False, "share_amount": 185.10, "ad_hoc_name": "Bob", "contact_id": None},
    ]
    expense = create_shared_expense(session, purchase.id, "PAID_OWN", participants)

    self_p = session.query(SharedParticipant).filter_by(
        shared_expense_id=expense.id, is_self=True
    ).one()
    update_split(session, expense.id, self_p.id, 100.00)
    session.expire_all()

    debts = session.query(SharedDebt).filter_by(shared_expense_id=expense.id).all()
    assert len(debts) == 0
