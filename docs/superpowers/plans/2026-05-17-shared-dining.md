# Shared Dining / Receipt Splitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users mark a scanned receipt as a shared dining expense, record their actual portion, and track who owes what — accessible from both web UI and Telegram.

**Architecture:** Four new ORM models (`DiningContact`, `SharedExpense`, `SharedParticipant`, `SharedDebt`) + `TelegramSplitSession` live in `initialize_database_schema.py`. A service layer in `manage_shared_dining.py` owns all business logic. A Flask blueprint (`shared_dining_endpoints.py`) exposes REST API. A Telegram handler (`handle_shared_dining_walk.py`) drives the `/split` conversation flow.

**Tech Stack:** Python 3.14, SQLAlchemy ORM, Alembic, Flask blueprints, python-telegram-bot HTTP API, pytest + sqlite in-memory.

**Spec:** `docs/superpowers/specs/2026-05-17-shared-dining-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/backend/initialize_database_schema.py` | Add 5 new ORM model classes |
| Create | `alembic/versions/033_shared_dining.py` | Additive migration for 5 new tables |
| Create | `src/backend/manage_shared_dining.py` | Service layer — all business logic |
| Create | `src/backend/shared_dining_endpoints.py` | Flask blueprint — REST API |
| Modify | `src/backend/create_flask_application.py` | Register new blueprint |
| Create | `src/backend/handle_shared_dining_walk.py` | Telegram split conversation state machine |
| Modify | `src/backend/handle_telegram_messages.py` | Route /split, /balances, /settle, /owed commands + callbacks |
| Create | `tests/test_shared_dining.py` | Unit tests — service layer |
| Create | `tests/test_shared_dining_e2e.py` | Integration test — full receipt→split→balance flow |

---

## Task 1: ORM Models

**Files:**
- Modify: `src/backend/initialize_database_schema.py` (after `Medication` class, before `# Schema Initialization`)
- Test: `tests/test_shared_dining.py`

- [ ] **Step 1.1: Write failing model round-trip test**

```python
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
```

- [ ] **Step 1.2: Run test — expect ImportError / AttributeError**

```bash
pytest tests/test_shared_dining.py::test_dining_contact_round_trip -v
```
Expected: `ImportError: cannot import name 'DiningContact'`

- [ ] **Step 1.3: Add models to initialize_database_schema.py**

Insert the following five classes into `src/backend/initialize_database_schema.py` **after the `Medication` class** (before `# ---------------------------------------------------------------------------\n# Schema Initialization`):

```python
class DiningContact(Base):
    __tablename__ = "dining_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_dining_contacts_name", "name"),
    )


class SharedExpense(Base):
    __tablename__ = "shared_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False, unique=True)
    total_amount = Column(Float, nullable=False)
    my_amount = Column(Float, nullable=False)
    payment_scenario = Column(String(20), nullable=False)  # PAID_ALL | PAID_OWN | OWED
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_shared_expenses_purchase_id", "purchase_id"),
    )

    purchase = relationship("Purchase", backref="shared_expense", uselist=False)
    participants = relationship(
        "SharedParticipant", back_populates="shared_expense", cascade="all, delete-orphan"
    )
    debts = relationship(
        "SharedDebt", back_populates="shared_expense", cascade="all, delete-orphan"
    )


class SharedParticipant(Base):
    __tablename__ = "shared_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shared_expense_id = Column(Integer, ForeignKey("shared_expenses.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("dining_contacts.id"), nullable=True)
    ad_hoc_name = Column(String(200), nullable=True)
    is_self = Column(Boolean, nullable=False, default=False)
    share_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_shared_participants_expense_id", "shared_expense_id"),
        Index("ix_shared_participants_contact_id", "contact_id"),
    )

    shared_expense = relationship("SharedExpense", back_populates="participants")
    contact = relationship("DiningContact")
    debts = relationship("SharedDebt", back_populates="participant")


class SharedDebt(Base):
    __tablename__ = "shared_debts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shared_expense_id = Column(Integer, ForeignKey("shared_expenses.id"), nullable=False)
    participant_id = Column(Integer, ForeignKey("shared_participants.id"), nullable=False)
    direction = Column(String(20), nullable=False)  # THEY_OWE_ME | I_OWE_THEM
    amount = Column(Float, nullable=False)
    settled = Column(Boolean, nullable=False, default=False)
    settled_at = Column(DateTime, nullable=True)
    settled_note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_shared_debts_expense_id", "shared_expense_id"),
        Index("ix_shared_debts_participant_id", "participant_id"),
        Index("ix_shared_debts_settled", "settled"),
    )

    shared_expense = relationship("SharedExpense", back_populates="debts")
    participant = relationship("SharedParticipant", back_populates="debts")


class TelegramSplitSession(Base):
    """Transient in-progress /split conversation state per chat."""

    __tablename__ = "telegram_split_session"

    chat_id = Column(String(64), primary_key=True)
    state = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

- [ ] **Step 1.4: Run all model tests — expect PASS**

```bash
pytest tests/test_shared_dining.py -v
```
Expected: 5 tests PASS

- [ ] **Step 1.5: Commit**

```bash
git add src/backend/initialize_database_schema.py tests/test_shared_dining.py
git commit -m "feat(shared-dining): add ORM models + model round-trip tests"
```

---

## Task 2: Alembic Migration

**Files:**
- Create: `alembic/versions/033_shared_dining.py`
- Test: `tests/test_migration_033.py`

- [ ] **Step 2.1: Write failing migration test**

```python
# tests/test_migration_033.py
from __future__ import annotations
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")


def _get_table_names(conn):
    return {
        row[0]
        for row in conn.execute(
            __import__("sqlalchemy").text("SELECT name FROM sqlite_master WHERE type='table'")
        )
    }


def test_migration_033_upgrade_creates_tables(tmp_path):
    from alembic.config import Config
    from alembic import command
    import sqlalchemy as sa

    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "033_shared_dining")

    engine = sa.create_engine(db_url)
    with engine.connect() as conn:
        tables = _get_table_names(conn)

    assert "dining_contacts" in tables
    assert "shared_expenses" in tables
    assert "shared_participants" in tables
    assert "shared_debts" in tables
    assert "telegram_split_session" in tables


def test_migration_033_downgrade_drops_tables(tmp_path):
    from alembic.config import Config
    from alembic import command
    import sqlalchemy as sa

    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "033_shared_dining")
    command.downgrade(cfg, "032_telegram_shopping_session")

    engine = sa.create_engine(db_url)
    with engine.connect() as conn:
        tables = _get_table_names(conn)

    assert "dining_contacts" not in tables
    assert "shared_expenses" not in tables
```

- [ ] **Step 2.2: Run migration test — expect FileNotFoundError**

```bash
pytest tests/test_migration_033.py::test_migration_033_upgrade_creates_tables -v
```
Expected: FAIL — migration file does not exist yet.

- [ ] **Step 2.3: Create migration file**

```python
# alembic/versions/033_shared_dining.py
"""shared_dining: 5 new tables for shared expense tracking and Telegram split session.

Revision ID: 033_shared_dining
Revises: 032_telegram_shopping_session
Create Date: 2026-05-17

Additive only — creates 5 new tables, no existing tables modified.
Downgrade drops the 5 tables. Both are idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "033_shared_dining"
down_revision: Union[str, None] = "032_telegram_shopping_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "dining_contacts"):
        op.create_table(
            "dining_contacts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        )
        op.create_index("ix_dining_contacts_name", "dining_contacts", ["name"])

    if not _table_exists(bind, "shared_expenses"):
        op.create_table(
            "shared_expenses",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("purchase_id", sa.Integer, sa.ForeignKey("purchases.id"), nullable=False),
            sa.Column("total_amount", sa.Float, nullable=False),
            sa.Column("my_amount", sa.Float, nullable=False),
            sa.Column("payment_scenario", sa.String(20), nullable=False),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint("purchase_id", name="uq_shared_expenses_purchase_id"),
        )
        op.create_index("ix_shared_expenses_purchase_id", "shared_expenses", ["purchase_id"])

    if not _table_exists(bind, "shared_participants"):
        op.create_table(
            "shared_participants",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("shared_expense_id", sa.Integer, sa.ForeignKey("shared_expenses.id"), nullable=False),
            sa.Column("contact_id", sa.Integer, sa.ForeignKey("dining_contacts.id"), nullable=True),
            sa.Column("ad_hoc_name", sa.String(200), nullable=True),
            sa.Column("is_self", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("share_amount", sa.Float, nullable=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        )
        op.create_index("ix_shared_participants_expense_id", "shared_participants", ["shared_expense_id"])
        op.create_index("ix_shared_participants_contact_id", "shared_participants", ["contact_id"])

    if not _table_exists(bind, "shared_debts"):
        op.create_table(
            "shared_debts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("shared_expense_id", sa.Integer, sa.ForeignKey("shared_expenses.id"), nullable=False),
            sa.Column("participant_id", sa.Integer, sa.ForeignKey("shared_participants.id"), nullable=False),
            sa.Column("direction", sa.String(20), nullable=False),
            sa.Column("amount", sa.Float, nullable=False),
            sa.Column("settled", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("settled_at", sa.DateTime, nullable=True),
            sa.Column("settled_note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        )
        op.create_index("ix_shared_debts_expense_id", "shared_debts", ["shared_expense_id"])
        op.create_index("ix_shared_debts_participant_id", "shared_debts", ["participant_id"])
        op.create_index("ix_shared_debts_settled", "shared_debts", ["settled"])

    if not _table_exists(bind, "telegram_split_session"):
        op.create_table(
            "telegram_split_session",
            sa.Column("chat_id", sa.String(64), primary_key=True),
            sa.Column("state", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for tbl in [
        "telegram_split_session",
        "shared_debts",
        "shared_participants",
        "shared_expenses",
        "dining_contacts",
    ]:
        if _table_exists(bind, tbl):
            op.drop_table(tbl)
```

- [ ] **Step 2.4: Run migration tests — expect PASS**

```bash
pytest tests/test_migration_033.py -v
```
Expected: 2 tests PASS

- [ ] **Step 2.5: Commit**

```bash
git add alembic/versions/033_shared_dining.py tests/test_migration_033.py
git commit -m "feat(shared-dining): add Alembic migration 033"
```

---

## Task 3: Service Layer — create_shared_expense

**Files:**
- Create: `src/backend/manage_shared_dining.py`
- Test: `tests/test_shared_dining.py` (append)

- [ ] **Step 3.1: Write failing tests for create_shared_expense**

Append to `tests/test_shared_dining.py`:

```python
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
```

- [ ] **Step 3.2: Run — expect ImportError**

```bash
pytest tests/test_shared_dining.py -k "test_create" -v
```
Expected: `ImportError: No module named 'src.backend.manage_shared_dining'`

- [ ] **Step 3.3: Create src/backend/manage_shared_dining.py**

```python
"""Shared dining / receipt splitting service layer.

All public functions take a SQLAlchemy session as their first argument and
commit at the end. Callers should not commit again.
"""
from __future__ import annotations

from datetime import datetime, timezone


class SplitValidationError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_shared_expense(
    session,
    purchase_id: int,
    payment_scenario: str,
    participants: list[dict],
    notes: str | None = None,
) -> object:
    """Create a SharedExpense for an existing purchase.

    participants is a list of dicts with keys:
        is_self (bool), contact_id (int|None), ad_hoc_name (str|None),
        share_amount (float), payer (bool, OWED scenario only)

    Raises SplitValidationError for bad input.
    """
    from src.backend.initialize_database_schema import (
        Purchase, SharedExpense, SharedParticipant, SharedDebt,
    )

    if payment_scenario not in ("PAID_ALL", "PAID_OWN", "OWED"):
        raise SplitValidationError(f"Invalid payment_scenario: {payment_scenario!r}")

    purchase = session.get(Purchase, purchase_id)
    if purchase is None:
        raise SplitValidationError(f"Purchase {purchase_id} not found")

    self_rows = [p for p in participants if p.get("is_self")]
    if len(self_rows) != 1:
        raise SplitValidationError("Exactly one participant must have is_self=True")

    total_amount = purchase.total_amount or 0.0
    share_sum = round(sum(p["share_amount"] for p in participants), 2)
    if abs(share_sum - round(total_amount, 2)) > 0.01:
        raise SplitValidationError(
            f"Share amounts sum to {share_sum:.2f} but purchase total is {total_amount:.2f}"
        )

    if payment_scenario == "OWED":
        payers = [p for p in participants if p.get("payer")]
        if len(payers) != 1:
            raise SplitValidationError("OWED scenario requires exactly one participant marked payer=True")

    existing = session.query(SharedExpense).filter_by(purchase_id=purchase_id).one_or_none()
    if existing:
        raise SplitValidationError(f"Purchase {purchase_id} already has a shared expense")

    my_amount = self_rows[0]["share_amount"]
    expense = SharedExpense(
        purchase_id=purchase_id,
        total_amount=total_amount,
        my_amount=my_amount,
        payment_scenario=payment_scenario,
        notes=notes,
    )
    session.add(expense)
    session.flush()

    participant_rows: list[tuple] = []
    for p_data in participants:
        row = SharedParticipant(
            shared_expense_id=expense.id,
            contact_id=p_data.get("contact_id"),
            ad_hoc_name=p_data.get("ad_hoc_name"),
            is_self=bool(p_data.get("is_self")),
            share_amount=p_data["share_amount"],
        )
        session.add(row)
        session.flush()
        participant_rows.append((row, p_data))

    if payment_scenario == "PAID_ALL":
        for row, _ in participant_rows:
            if not row.is_self:
                session.add(SharedDebt(
                    shared_expense_id=expense.id,
                    participant_id=row.id,
                    direction="THEY_OWE_ME",
                    amount=row.share_amount,
                ))

    elif payment_scenario == "OWED":
        payer_row = next(row for row, pd in participant_rows if pd.get("payer"))
        session.add(SharedDebt(
            shared_expense_id=expense.id,
            participant_id=payer_row.id,
            direction="I_OWE_THEM",
            amount=my_amount,
        ))

    session.commit()
    session.refresh(expense)
    return expense
```

- [ ] **Step 3.4: Run create tests — expect PASS**

```bash
pytest tests/test_shared_dining.py -k "test_create" -v
```
Expected: 5 tests PASS

- [ ] **Step 3.5: Commit**

```bash
git add src/backend/manage_shared_dining.py tests/test_shared_dining.py
git commit -m "feat(shared-dining): service layer create_shared_expense + tests"
```

---

## Task 4: Service Layer — Settlement and Balances

**Files:**
- Modify: `src/backend/manage_shared_dining.py` (append functions)
- Test: `tests/test_shared_dining.py` (append)

- [ ] **Step 4.1: Write failing settlement and balance tests**

Append to `tests/test_shared_dining.py`:

```python
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
    from src.backend.initialize_database_schema import SharedDebt

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
```

- [ ] **Step 4.2: Run — expect ImportError / AttributeError**

```bash
pytest tests/test_shared_dining.py -k "test_settle or test_get_balance or test_merge" -v
```
Expected: FAIL — functions not yet defined in manage_shared_dining.py

- [ ] **Step 4.3: Append settlement/balance/merge functions to manage_shared_dining.py**

```python
def update_split(
    session,
    shared_expense_id: int,
    participant_id: int,
    new_amount: float,
) -> object:
    """Change one participant's share_amount, adjusting others proportionally.

    After the update, all debt records for the expense are regenerated.
    """
    from src.backend.initialize_database_schema import SharedExpense, SharedParticipant, SharedDebt

    expense = session.get(SharedExpense, shared_expense_id)
    if expense is None:
        raise SplitValidationError(f"SharedExpense {shared_expense_id} not found")

    target = session.get(SharedParticipant, participant_id)
    if target is None or target.shared_expense_id != shared_expense_id:
        raise SplitValidationError(f"Participant {participant_id} not in expense {shared_expense_id}")

    old_amount = target.share_amount
    delta = new_amount - old_amount
    others = [p for p in expense.participants if p.id != participant_id]
    if not others:
        raise SplitValidationError("Cannot update: no other participants")

    target.share_amount = new_amount
    others_total = sum(p.share_amount for p in others)
    if others_total > 0.001:
        for p in others:
            p.share_amount = round(p.share_amount - delta * (p.share_amount / others_total), 2)

    new_sum = sum(p.share_amount for p in expense.participants)
    if abs(new_sum - expense.total_amount) > 0.01:
        raise SplitValidationError(
            f"Amounts don't balance to {expense.total_amount:.2f} after update (got {new_sum:.2f})"
        )

    self_row = next((p for p in expense.participants if p.is_self), None)
    if self_row:
        expense.my_amount = self_row.share_amount

    for debt in list(expense.debts):
        session.delete(debt)
    session.flush()

    if expense.payment_scenario == "PAID_ALL":
        for p in expense.participants:
            if not p.is_self:
                session.add(SharedDebt(
                    shared_expense_id=expense.id,
                    participant_id=p.id,
                    direction="THEY_OWE_ME",
                    amount=p.share_amount,
                ))
    elif expense.payment_scenario == "OWED":
        payer = next(
            (p for p in expense.participants
             if any(d.direction == "I_OWE_THEM" for d in p.debts)),
            None,
        )
        if payer:
            session.add(SharedDebt(
                shared_expense_id=expense.id,
                participant_id=payer.id,
                direction="I_OWE_THEM",
                amount=expense.my_amount,
            ))

    session.commit()
    session.refresh(expense)
    return expense


def settle_debt(session, debt_id: int, note: str | None = None) -> object:
    """Mark a single debt as settled."""
    from src.backend.initialize_database_schema import SharedDebt

    debt = session.get(SharedDebt, debt_id)
    if debt is None:
        raise SplitValidationError(f"Debt {debt_id} not found")
    debt.settled = True
    debt.settled_at = _utcnow()
    debt.settled_note = note
    session.commit()
    return debt


def settle_all_with_contact(session, contact_id: int) -> int:
    """Settle all unsettled debts linked to a contact. Returns count settled."""
    from src.backend.initialize_database_schema import SharedDebt, SharedParticipant

    debts = (
        session.query(SharedDebt)
        .join(SharedParticipant, SharedDebt.participant_id == SharedParticipant.id)
        .filter(SharedParticipant.contact_id == contact_id, SharedDebt.settled == False)  # noqa: E712
        .all()
    )
    now = _utcnow()
    for debt in debts:
        debt.settled = True
        debt.settled_at = now
    session.commit()
    return len(debts)


def get_balance_with_contact(session, contact_id: int) -> float:
    """Net unsettled balance with a contact.

    Returns: positive = they owe you, negative = you owe them.
    """
    from src.backend.initialize_database_schema import SharedDebt, SharedParticipant

    debts = (
        session.query(SharedDebt)
        .join(SharedParticipant, SharedDebt.participant_id == SharedParticipant.id)
        .filter(SharedParticipant.contact_id == contact_id, SharedDebt.settled == False)  # noqa: E712
        .all()
    )
    balance = 0.0
    for debt in debts:
        if debt.direction == "THEY_OWE_ME":
            balance += debt.amount
        else:
            balance -= debt.amount
    return round(balance, 2)


def get_all_balances(session) -> list[dict]:
    """Return [{contact_id, name, net_amount}] for contacts with non-zero unsettled balance."""
    from src.backend.initialize_database_schema import DiningContact

    contacts = session.query(DiningContact).all()
    result = []
    for contact in contacts:
        balance = get_balance_with_contact(session, contact.id)
        if abs(balance) >= 0.01:
            result.append({
                "contact_id": contact.id,
                "name": contact.name,
                "net_amount": balance,
            })
    return sorted(result, key=lambda x: abs(x["net_amount"]), reverse=True)


def merge_contact(session, ad_hoc_participant_id: int, contact_id: int) -> object:
    """Promote an ad-hoc participant to a saved contact. Debts follow automatically."""
    from src.backend.initialize_database_schema import SharedParticipant, DiningContact

    participant = session.get(SharedParticipant, ad_hoc_participant_id)
    if participant is None:
        raise SplitValidationError(f"Participant {ad_hoc_participant_id} not found")
    if participant.contact_id is not None:
        raise SplitValidationError("Participant already linked to a saved contact")

    contact = session.get(DiningContact, contact_id)
    if contact is None:
        raise SplitValidationError(f"Contact {contact_id} not found")

    participant.contact_id = contact_id
    participant.ad_hoc_name = None
    session.commit()
    return participant
```

- [ ] **Step 4.4: Run all service tests — expect PASS**

```bash
pytest tests/test_shared_dining.py -v
```
Expected: all tests PASS

- [ ] **Step 4.5: Commit**

```bash
git add src/backend/manage_shared_dining.py tests/test_shared_dining.py
git commit -m "feat(shared-dining): settlement, balance, merge_contact + tests"
```

---

## Task 5: REST API Blueprint

**Files:**
- Create: `src/backend/shared_dining_endpoints.py`
- Modify: `src/backend/create_flask_application.py`
- Test: `tests/test_shared_dining_e2e.py`

- [ ] **Step 5.1: Write failing API tests**

```python
# tests/test_shared_dining_e2e.py
from __future__ import annotations
import os
import json
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")


@pytest.fixture
def app(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    from src.backend.create_flask_application import create_app

    db_path = tmp_path / "e2e.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url

    eng = create_db_engine(db_url)
    Base.metadata.create_all(eng)

    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {os.environ['INITIAL_ADMIN_TOKEN']}"}


@pytest.fixture
def purchase_id(app):
    from src.backend.initialize_database_schema import (
        create_db_engine, create_session_factory, Purchase
    )
    from datetime import datetime, timezone

    eng = create_db_engine(os.environ["DATABASE_URL"])
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    p = Purchase(total_amount=100.0, date=datetime.now(timezone.utc), domain="restaurant")
    s.add(p)
    s.commit()
    pid = p.id
    s.close()
    return pid


def test_create_shared_expense_via_api(client, auth_headers, purchase_id):
    payload = {
        "payment_scenario": "PAID_ALL",
        "participants": [
            {"is_self": True,  "share_amount": 50.0, "ad_hoc_name": None, "contact_id": None},
            {"is_self": False, "share_amount": 50.0, "ad_hoc_name": "Bob", "contact_id": None},
        ],
    }
    resp = client.post(
        f"/shared-dining/purchases/{purchase_id}",
        data=json.dumps(payload),
        content_type="application/json",
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["my_amount"] == 50.0


def test_create_contact_and_list(client, auth_headers):
    resp = client.post(
        "/shared-dining/contacts",
        data=json.dumps({"name": "Alice", "phone": "555-9999"}),
        content_type="application/json",
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp2 = client.get("/shared-dining/contacts", headers=auth_headers)
    assert resp2.status_code == 200
    contacts = resp2.get_json()
    assert any(c["name"] == "Alice" for c in contacts)


def test_get_balances_empty(client, auth_headers):
    resp = client.get("/shared-dining/balances", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_settle_debt_via_api(client, auth_headers, purchase_id):
    payload = {
        "payment_scenario": "PAID_ALL",
        "participants": [
            {"is_self": True,  "share_amount": 50.0, "ad_hoc_name": None, "contact_id": None},
            {"is_self": False, "share_amount": 50.0, "ad_hoc_name": "Bob", "contact_id": None},
        ],
    }
    create_resp = client.post(
        f"/shared-dining/purchases/{purchase_id}",
        data=json.dumps(payload),
        content_type="application/json",
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    from src.backend.initialize_database_schema import (
        create_db_engine, create_session_factory, SharedDebt
    )
    eng = create_db_engine(os.environ["DATABASE_URL"])
    sess = create_session_factory(eng)()
    debt = sess.query(SharedDebt).first()
    debt_id = debt.id
    sess.close()

    settle_resp = client.post(
        f"/shared-dining/debts/{debt_id}/settle",
        data=json.dumps({"note": "paid cash"}),
        content_type="application/json",
        headers=auth_headers,
    )
    assert settle_resp.status_code == 200
```

- [ ] **Step 5.2: Run — expect 404 (blueprint not registered)**

```bash
pytest tests/test_shared_dining_e2e.py::test_get_balances_empty -v
```
Expected: FAIL — `assert 404 == 200`

- [ ] **Step 5.3: Create src/backend/shared_dining_endpoints.py**

```python
"""Flask blueprint for shared dining / receipt splitting REST API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, g

from src.backend.manage_shared_dining import (
    SplitValidationError,
    create_shared_expense,
    update_split,
    settle_debt,
    settle_all_with_contact,
    get_balance_with_contact,
    get_all_balances,
    merge_contact,
)
from src.backend.initialize_database_schema import DiningContact, SharedExpense

shared_dining_bp = Blueprint("shared_dining", __name__, url_prefix="/shared-dining")


def _session():
    return g.db_session


@shared_dining_bp.route("/purchases/<int:purchase_id>", methods=["POST"])
def create_expense(purchase_id: int):
    from src.backend.create_flask_application import require_write_access
    from functools import wraps
    data = request.get_json(silent=True) or {}
    try:
        expense = create_shared_expense(
            _session(),
            purchase_id=purchase_id,
            payment_scenario=data.get("payment_scenario", ""),
            participants=data.get("participants", []),
            notes=data.get("notes"),
        )
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"id": expense.id, "my_amount": expense.my_amount}), 201


@shared_dining_bp.route("/<int:expense_id>/participants/<int:participant_id>", methods=["PATCH"])
def patch_participant(expense_id: int, participant_id: int):
    data = request.get_json(silent=True) or {}
    new_amount = data.get("share_amount")
    if new_amount is None:
        return jsonify({"error": "share_amount required"}), 400
    try:
        update_split(_session(), expense_id, participant_id, float(new_amount))
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200


@shared_dining_bp.route("/debts/<int:debt_id>/settle", methods=["POST"])
def settle(debt_id: int):
    data = request.get_json(silent=True) or {}
    try:
        settle_debt(_session(), debt_id, note=data.get("note"))
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200


@shared_dining_bp.route("/contacts/<int:contact_id>/settle-all", methods=["POST"])
def settle_all(contact_id: int):
    count = settle_all_with_contact(_session(), contact_id)
    return jsonify({"settled": count}), 200


@shared_dining_bp.route("/balances", methods=["GET"])
def balances():
    return jsonify(get_all_balances(_session())), 200


@shared_dining_bp.route("/balances/<int:contact_id>", methods=["GET"])
def balance_with_contact(contact_id: int):
    amount = get_balance_with_contact(_session(), contact_id)
    return jsonify({"contact_id": contact_id, "net_amount": amount}), 200


@shared_dining_bp.route("/contacts", methods=["GET"])
def list_contacts():
    contacts = _session().query(DiningContact).order_by(DiningContact.name).all()
    return jsonify([
        {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email}
        for c in contacts
    ]), 200


@shared_dining_bp.route("/contacts", methods=["POST"])
def create_contact():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    contact = DiningContact(name=name, phone=data.get("phone"), email=data.get("email"))
    _session().add(contact)
    _session().commit()
    return jsonify({"id": contact.id, "name": contact.name}), 201


@shared_dining_bp.route("/contacts/merge", methods=["POST"])
def merge():
    data = request.get_json(silent=True) or {}
    try:
        merge_contact(_session(), data.get("participant_id"), data.get("contact_id"))
    except (SplitValidationError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200
```

- [ ] **Step 5.4: Register the blueprint in create_flask_application.py**

In `src/backend/create_flask_application.py`, inside `register_blueprints()`, add after `medications_bp`:

```python
    from src.backend.shared_dining_endpoints import shared_dining_bp
    app.register_blueprint(shared_dining_bp)
```

Also add to the existing import block at line ~220 where other blueprints are registered.

- [ ] **Step 5.5: Run API tests — expect PASS**

```bash
pytest tests/test_shared_dining_e2e.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5.6: Commit**

```bash
git add src/backend/shared_dining_endpoints.py src/backend/create_flask_application.py tests/test_shared_dining_e2e.py
git commit -m "feat(shared-dining): REST API blueprint + E2E tests"
```

---

## Task 6: Telegram Handler — /split Flow

**Files:**
- Create: `src/backend/handle_shared_dining_walk.py`
- Test: `tests/test_shared_dining_e2e.py` (append)

- [ ] **Step 6.1: Write failing Telegram state tests**

Append to `tests/test_shared_dining_e2e.py`:

```python
# --- Telegram split flow tests ---

@pytest.fixture
def tg_session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "tg.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


def test_get_or_create_split_session(tg_session):
    from src.backend.handle_shared_dining_walk import get_or_create_split_session
    row = get_or_create_split_session(tg_session, "chat_abc")
    assert row.chat_id == "chat_abc"
    assert row.state == {}
    # idempotent
    row2 = get_or_create_split_session(tg_session, "chat_abc")
    assert row2.chat_id == "chat_abc"


def test_build_receipt_keyboard(tg_session):
    from src.backend.handle_shared_dining_walk import build_receipt_keyboard
    from src.backend.initialize_database_schema import Purchase
    from datetime import datetime, timezone

    for i in range(3):
        tg_session.add(Purchase(
            total_amount=float(10 * (i + 1)),
            date=datetime.now(timezone.utc),
            domain="restaurant",
        ))
    tg_session.commit()

    kb = build_receipt_keyboard(tg_session)
    assert len(kb) <= 5
    assert all("callback_data" in btn for btn in kb)
    assert all(btn["callback_data"].startswith("split:receipt:") for btn in kb)


def test_save_split_state(tg_session):
    from src.backend.handle_shared_dining_walk import get_or_create_split_session, save_split_state
    row = get_or_create_split_session(tg_session, "chat_xyz")
    save_split_state(tg_session, "chat_xyz", {"step": "select_scenario", "purchase_id": 5})
    tg_session.expire_all()
    row2 = tg_session.get(
        __import__("src.backend.initialize_database_schema", fromlist=["TelegramSplitSession"]).TelegramSplitSession,
        "chat_xyz",
    )
    assert row2.state["step"] == "select_scenario"
    assert row2.state["purchase_id"] == 5
```

- [ ] **Step 6.2: Run — expect ImportError**

```bash
pytest tests/test_shared_dining_e2e.py -k "test_get_or_create_split or test_build_receipt or test_save_split" -v
```
Expected: `ImportError: No module named 'src.backend.handle_shared_dining_walk'`

- [ ] **Step 6.3: Create src/backend/handle_shared_dining_walk.py**

```python
"""Telegram /split conversation state machine for shared dining.

State stored in TelegramSplitSession.state (JSON):
  {
    "step": str,            # select_receipt | select_scenario | add_participants | confirm
    "purchase_id": int,
    "purchase_label": str,
    "payment_scenario": str,
    "total_amount": float,
    "participants": [
      {"name": str, "contact_id": int|null, "share_amount": float, "is_self": bool}
    ],
    "awaiting_participant_name": bool
  }
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_or_create_split_session(session, chat_id: str):
    from src.backend.initialize_database_schema import TelegramSplitSession
    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        row = TelegramSplitSession(chat_id=chat_id, state={})
        session.add(row)
        session.flush()
    return row


def save_split_state(session, chat_id: str, state: dict) -> None:
    from src.backend.initialize_database_schema import TelegramSplitSession
    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        row = TelegramSplitSession(chat_id=chat_id, state=state)
        session.add(row)
    else:
        row.state = state
    session.commit()


def clear_split_session(session, chat_id: str) -> None:
    from src.backend.initialize_database_schema import TelegramSplitSession
    row = session.get(TelegramSplitSession, chat_id)
    if row:
        session.delete(row)
        session.commit()


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def build_receipt_keyboard(session) -> list[dict]:
    """Return up to 5 recent restaurant/dining purchases as inline buttons."""
    from src.backend.initialize_database_schema import Purchase
    purchases = (
        session.query(Purchase)
        .order_by(Purchase.date.desc())
        .limit(5)
        .all()
    )
    buttons = []
    for p in purchases:
        label = f"${p.total_amount:.2f}"
        if hasattr(p, "store") and p.store:
            label = f"{p.store.name} {label}"
        buttons.append({
            "text": label,
            "callback_data": f"split:receipt:{p.id}:{p.total_amount:.2f}",
        })
    return buttons


def build_scenario_keyboard() -> list[list[dict]]:
    return [[
        {"text": "I Paid All",  "callback_data": "split:scenario:PAID_ALL"},
        {"text": "Paid My Share", "callback_data": "split:scenario:PAID_OWN"},
        {"text": "I Owe Someone", "callback_data": "split:scenario:OWED"},
    ]]


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

def _send(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    import requests
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        import json
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TELEGRAM_API_BASE}/sendMessage", json=payload, timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send Telegram message: %s", exc)


# ---------------------------------------------------------------------------
# Entry points called from handle_telegram_messages.py
# ---------------------------------------------------------------------------

def start_split(session, chat_id: str) -> None:
    """Handle /split command — show recent receipts."""
    buttons = build_receipt_keyboard(session)
    if not buttons:
        _send(chat_id, "No receipts found to split.")
        return

    save_split_state(session, chat_id, {"step": "select_receipt"})
    _send(
        chat_id,
        "Which receipt do you want to split?",
        reply_markup={"inline_keyboard": [buttons]},
    )


def handle_split_callback(session, chat_id: str, data: str) -> bool:
    """Dispatch a split:* callback_data string. Returns True if consumed."""
    if not data.startswith("split:"):
        return False

    parts = data.split(":")
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "receipt":
        # split:receipt:<purchase_id>:<total>
        purchase_id = int(parts[2])
        total = float(parts[3]) if len(parts) > 3 else 0.0
        save_split_state(session, chat_id, {
            "step": "select_scenario",
            "purchase_id": purchase_id,
            "total_amount": total,
            "participants": [],
        })
        _send(
            chat_id,
            f"Receipt: <b>${total:.2f}</b>\n\nWho paid?",
            reply_markup={"inline_keyboard": build_scenario_keyboard()},
        )
        return True

    if sub == "scenario":
        scenario = parts[2]  # PAID_ALL | PAID_OWN | OWED
        row = get_or_create_split_session(session, chat_id)
        state = dict(row.state)
        total = state.get("total_amount", 0.0)
        state["step"] = "add_participants"
        state["payment_scenario"] = scenario
        state["participants"] = [
            {"name": "You", "is_self": True, "contact_id": None, "share_amount": 0.0}
        ]
        save_split_state(session, chat_id, state)
        _send(
            chat_id,
            (
                f"Scenario: <b>{scenario.replace('_', ' ').title()}</b>\n\n"
                "Type participant names one at a time (e.g. \"John Smith\").\n"
                "Send /splitdone when everyone is added."
            ),
        )
        return True

    if sub == "confirm":
        _finalize_split(session, chat_id)
        return True

    if sub == "cancel":
        clear_split_session(session, chat_id)
        _send(chat_id, "Split cancelled.")
        return True

    return False


def consume_split_text(session, chat_id: str, text: str) -> bool:
    """Try to consume typed text as a participant name. Returns True if consumed."""
    from src.backend.initialize_database_schema import TelegramSplitSession, DiningContact

    row = session.get(TelegramSplitSession, chat_id)
    if row is None or row.state.get("step") != "add_participants":
        return False

    name = text.strip()
    if not name:
        return False

    state = dict(row.state)
    total = state.get("total_amount", 0.0)
    participants: list = state.get("participants", [])

    existing_contact = (
        session.query(DiningContact)
        .filter(DiningContact.name.ilike(f"%{name}%"))
        .first()
    )
    contact_id = existing_contact.id if existing_contact else None
    participants.append({
        "name": name,
        "is_self": False,
        "contact_id": contact_id,
        "share_amount": 0.0,
    })
    state["participants"] = participants

    count = len(participants)
    equal_share = round(total / count, 2) if count else 0.0
    for p in state["participants"]:
        p["share_amount"] = equal_share

    save_split_state(session, chat_id, state)

    names_list = "\n".join(
        f"  {'(You)' if p['is_self'] else p['name']}: ${p['share_amount']:.2f}"
        for p in participants
    )
    _send(
        chat_id,
        (
            f"Added <b>{name}</b>{'  ✓ saved contact' if contact_id else ' (new)'}\n\n"
            f"Current split (${total:.2f} total):\n{names_list}\n\n"
            "Add more names or send /splitdone to confirm."
        ),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirm Split", "callback_data": "split:confirm"},
            {"text": "❌ Cancel",         "callback_data": "split:cancel"},
        ]]},
    )
    return True


def handle_splitdone_command(session, chat_id: str) -> None:
    """Handle /splitdone — show summary and ask for confirmation."""
    from src.backend.initialize_database_schema import TelegramSplitSession

    row = session.get(TelegramSplitSession, chat_id)
    if row is None or row.state.get("step") != "add_participants":
        _send(chat_id, "No split in progress. Use /split to start.")
        return

    state = row.state
    participants = state.get("participants", [])
    if len(participants) < 2:
        _send(chat_id, "Add at least one other person before confirming.")
        return

    total = state.get("total_amount", 0.0)
    names_list = "\n".join(
        f"  {'You' if p['is_self'] else p['name']}: ${p['share_amount']:.2f}"
        for p in participants
    )
    scenario_label = state.get("payment_scenario", "").replace("_", " ").title()

    _send(
        chat_id,
        (
            f"<b>Split Summary</b>\n"
            f"Scenario: {scenario_label}\n\n"
            f"{names_list}\n"
            f"Total: ${total:.2f}\n\n"
            "Confirm?"
        ),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Save", "callback_data": "split:confirm"},
            {"text": "❌ Cancel", "callback_data": "split:cancel"},
        ]]},
    )


def _finalize_split(session, chat_id: str) -> None:
    """Create the SharedExpense from current state and clear the session."""
    from src.backend.initialize_database_schema import TelegramSplitSession

    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        _send(chat_id, "No split in progress.")
        return

    state = row.state
    purchase_id = state.get("purchase_id")
    payment_scenario = state.get("payment_scenario", "PAID_OWN")
    participants = state.get("participants", [])

    if payment_scenario == "OWED" and len(participants) >= 2:
        participants[1]["payer"] = True

    try:
        from src.backend.manage_shared_dining import create_shared_expense
        expense = create_shared_expense(session, purchase_id, payment_scenario, participants)
        my_amount = expense.my_amount
        clear_split_session(session, chat_id)
        _send(chat_id, f"✅ Split saved! Your share: <b>${my_amount:.2f}</b>")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to finalize split for chat %s: %s", chat_id, exc)
        _send(chat_id, f"❌ Could not save split: {exc}")


# ---------------------------------------------------------------------------
# /balances, /settle, /owed convenience commands
# ---------------------------------------------------------------------------

def handle_balances_command(session, chat_id: str) -> None:
    from src.backend.manage_shared_dining import get_all_balances

    balances = get_all_balances(session)
    if not balances:
        _send(chat_id, "No outstanding balances.")
        return

    lines = []
    for b in balances:
        amount = b["net_amount"]
        if amount > 0:
            lines.append(f"  {b['name']} owes you <b>${amount:.2f}</b>")
        else:
            lines.append(f"  You owe {b['name']} <b>${abs(amount):.2f}</b>")
    _send(chat_id, "💰 <b>Balances</b>\n" + "\n".join(lines))


def handle_settle_command(session, chat_id: str, args: str) -> None:
    from src.backend.initialize_database_schema import DiningContact
    from src.backend.manage_shared_dining import settle_all_with_contact

    name = args.strip().lstrip("@")
    if not name:
        _send(chat_id, "Usage: /settle <name>")
        return

    contact = (
        session.query(DiningContact)
        .filter(DiningContact.name.ilike(f"%{name}%"))
        .first()
    )
    if not contact:
        _send(chat_id, f"No contact found matching '{name}'.")
        return

    count = settle_all_with_contact(session, contact.id)
    _send(chat_id, f"✅ Settled {count} debt(s) with {contact.name}.")


def handle_owed_command(session, chat_id: str) -> None:
    from src.backend.manage_shared_dining import get_all_balances

    balances = get_all_balances(session)
    owed = [b for b in balances if b["net_amount"] < 0]
    if not owed:
        _send(chat_id, "You don't owe anyone right now.")
        return

    lines = [f"  {b['name']}: <b>${abs(b['net_amount']):.2f}</b>" for b in owed]
    _send(chat_id, "You owe:\n" + "\n".join(lines))
```

- [ ] **Step 6.4: Run Telegram handler tests — expect PASS**

```bash
pytest tests/test_shared_dining_e2e.py -k "test_get_or_create_split or test_build_receipt or test_save_split" -v
```
Expected: 3 tests PASS

- [ ] **Step 6.5: Commit**

```bash
git add src/backend/handle_shared_dining_walk.py tests/test_shared_dining_e2e.py
git commit -m "feat(shared-dining): Telegram split walk handler"
```

---

## Task 7: Wire into Telegram Dispatcher

**Files:**
- Modify: `src/backend/handle_telegram_messages.py`

- [ ] **Step 7.1: Add /split, /splitdone, /balances, /settle, /owed to _handle_command()**

In `src/backend/handle_telegram_messages.py`, inside `_handle_command()`, add before the `commands = {...}` dict:

```python
    if cmd == "/split":
        from src.backend.handle_shared_dining_walk import start_split
        start_split(g.db_session, chat_id)
        g.db_session.commit()
        return ""

    if cmd == "/splitdone":
        from src.backend.handle_shared_dining_walk import handle_splitdone_command
        handle_splitdone_command(g.db_session, chat_id)
        g.db_session.commit()
        return ""

    if cmd == "/balances":
        from src.backend.handle_shared_dining_walk import handle_balances_command
        handle_balances_command(g.db_session, chat_id)
        return ""

    if cmd.startswith("/settle"):
        args = command[len("/settle"):].strip()
        from src.backend.handle_shared_dining_walk import handle_settle_command
        handle_settle_command(g.db_session, chat_id, args)
        return ""

    if cmd == "/owed":
        from src.backend.handle_shared_dining_walk import handle_owed_command
        handle_owed_command(g.db_session, chat_id)
        return ""
```

- [ ] **Step 7.2: Add split:* callback routing in _handle_callback_query()**

In `src/backend/handle_telegram_messages.py`, inside `_handle_callback_query()`, add after the existing `if data.startswith(...)` blocks:

```python
    if data.startswith("split:"):
        try:
            from src.backend.handle_shared_dining_walk import handle_split_callback
            handle_split_callback(g.db_session, chat_id, data)
            g.db_session.commit()
        except Exception as e:
            logger.warning(f"split callback failed: {e}")
        return jsonify({"status": "ok"}), 200
```

- [ ] **Step 7.3: Add split typed-text consumer in telegram_webhook()**

In `src/backend/handle_telegram_messages.py`, inside `telegram_webhook()`, after the shopping walk `consume_typed_text` block:

```python
        try:
            from src.backend.handle_shared_dining_walk import consume_split_text
            if consume_split_text(g.db_session, chat_id, text):
                g.db_session.commit()
                return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.warning(f"split typed-text consume failed: {e}")
```

- [ ] **Step 7.4: Update /help text to include split commands**

In `src/backend/handle_telegram_messages.py`, find the `/help` entry in the `commands` dict and append:

```
\n💸 /split → Split a restaurant receipt with friends\n💰 /balances → See who owes what\n📤 /settle <name> → Settle debts with someone\n📥 /owed → See what you owe
```

- [ ] **Step 7.5: Run full test suite to verify no regressions**

```bash
pytest tests/ -v --timeout=30 -x
```
Expected: all existing tests + new tests PASS

- [ ] **Step 7.6: Commit**

```bash
git add src/backend/handle_telegram_messages.py
git commit -m "feat(shared-dining): wire /split commands + callbacks into Telegram dispatcher"
```

---

## Task 8: Smoke Test Checklist

After all tasks complete, verify manually:

**Web API:**
- [ ] `POST /shared-dining/contacts` with `{"name": "John"}` → 201
- [ ] `GET /shared-dining/contacts` → returns John
- [ ] `POST /shared-dining/purchases/<id>` with PAID_ALL + 4 equal participants → 201, `my_amount` correct
- [ ] `GET /shared-dining/balances` → shows John's debt
- [ ] `POST /shared-dining/debts/<id>/settle` → 200
- [ ] `GET /shared-dining/balances` → John's balance now 0 or absent

**Telegram (manual or via test webhook):**
- [ ] `/split` → bot shows recent receipts
- [ ] Tap a receipt → bot asks who paid
- [ ] Tap "I Paid All" → bot prompts for names
- [ ] Type "John Smith" → bot adds with equal split
- [ ] `/splitdone` → bot shows summary
- [ ] Tap "Save" → bot confirms with your share
- [ ] `/balances` → shows John owes you
- [ ] `/settle John` → settles all debts with John
- [ ] `/balances` → John no longer listed

---

## Self-Review Notes

- All 4 spec payment scenarios covered: PAID_ALL, PAID_OWN, OWED ✓
- `is_self` flag implemented on SharedParticipant ✓
- `merge_contact` in both service layer and REST endpoint ✓
- Migration is additive-only, idempotent ✓
- Running balance = sum of unsettled debts per contact ✓
- Telegram typed-text consumer follows same pattern as shopping walk ✓
- No changes to existing `purchases` or `receipt_items` tables ✓
