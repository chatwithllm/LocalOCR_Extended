"""shared_dining: 5 new tables for shared expense tracking and Telegram split session.

Revision ID: 033_shared_dining
Revises: 032_telegram_shopping_session
Create Date: 2026-05-17

Additive only — creates 5 new tables, no existing tables modified.
Downgrade drops the 5 tables. Both operations are idempotent.
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
