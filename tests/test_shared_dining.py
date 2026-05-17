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
