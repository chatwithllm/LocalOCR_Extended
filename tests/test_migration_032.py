"""Tests for Alembic migration 032_telegram_shopping_session."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "032_telegram_shopping_session.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_032", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compile_column(col):
    parts = [col.name, str(col.type)]
    if col.primary_key:
        parts.append("PRIMARY KEY")
    if not col.nullable and not col.primary_key:
        parts.append("NOT NULL")
    if col.server_default is not None and hasattr(col.server_default, "arg"):
        arg = col.server_default.arg
        # String literals (e.g. "active", "[]", "{}") must be quoted for SQLite;
        # SQL expressions like func.current_timestamp() must not be.
        if isinstance(arg, str):
            parts.append(f"DEFAULT {arg!r}")
        else:
            parts.append(f"DEFAULT {arg}")
    return " ".join(parts)


def _install_op_patches(engine):
    from contextlib import ExitStack
    stack = ExitStack()

    def fake_create_table(name, *cols, **_kw):
        col_sql = ", ".join(_compile_column(c) for c in cols)
        with engine.begin() as conn:
            conn.execute(sa.text(f"CREATE TABLE {name} ({col_sql})"))

    def fake_drop_table(name, **_kw):
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))

    def fake_create_index(name, table, cols, **_kw):
        cs = ", ".join(cols)
        with engine.begin() as conn:
            conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cs})"))

    def fake_drop_index(name, table_name=None, **_kw):
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))

    bind = engine.connect()
    stack.enter_context(patch("alembic.op.get_bind", return_value=bind))
    stack.enter_context(patch("alembic.op.create_table", side_effect=fake_create_table))
    stack.enter_context(patch("alembic.op.drop_table", side_effect=fake_drop_table))
    stack.enter_context(patch("alembic.op.create_index", side_effect=fake_create_index))
    stack.enter_context(patch("alembic.op.drop_index", side_effect=fake_drop_index))
    return stack


def test_032_module_loads():
    mig = _load_migration()
    assert mig.revision == "032_telegram_shopping_session"
    assert mig.down_revision == "031_telegram_inventory_session"


def test_032_upgrade_creates_table_and_is_idempotent(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'u.db'}")
    with _install_op_patches(engine):
        mig.upgrade()
        mig.upgrade()

    insp = sa.inspect(engine)
    assert "telegram_shopping_session" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("telegram_shopping_session")}
    expected = {
        "chat_id", "user_id", "status",
        "category_queue", "current_category", "item_queue", "cursor",
        "pending_prompt", "pending_action",
        "last_item_id", "pending_name", "pending_qty",
        "stats", "nudge_muted_until", "last_nudge_sent_at",
        "started_at", "last_action_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"

    idx_names = {i["name"] for i in insp.get_indexes("telegram_shopping_session")}
    assert "ix_tg_shop_status" in idx_names
    assert "ix_tg_shop_last_action" in idx_names


def test_032_downgrade_drops_table_when_present(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    with _install_op_patches(engine):
        mig.upgrade()
        mig.downgrade()
    insp = sa.inspect(engine)
    assert "telegram_shopping_session" not in insp.get_table_names()


def test_032_downgrade_is_noop_when_table_absent(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'd2.db'}")
    with _install_op_patches(engine):
        mig.downgrade()  # must not raise
