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
