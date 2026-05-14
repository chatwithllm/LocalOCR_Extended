"""Tests for Alembic migration 031_telegram_inventory_session."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "031_telegram_inventory_session.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_031", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compile_column(col, dialect) -> str:
    """Render a sa.Column into a SQLite-compatible DDL fragment."""
    col_type = col.type.compile(dialect=dialect)
    pk = " PRIMARY KEY" if col.primary_key else ""
    notnull = " NOT NULL" if (not col.nullable and not col.primary_key) else ""
    default = ""
    if col.server_default is not None:
        arg = col.server_default.arg
        # Function defaults (e.g. CURRENT_TIMESTAMP) render via str(); literals get quoted.
        if hasattr(arg, "compile"):
            default = f" DEFAULT {arg.compile(dialect=dialect)}"
        else:
            default = f" DEFAULT {arg!r}"
    return f"{col.name} {col_type}{pk}{notnull}{default}"


def _install_op_patches(sa_conn):
    """Patch alembic.op helpers to execute DDL on `sa_conn` directly.

    Mirrors the approach used in tests/test_migration_021.py — alembic.op
    requires a MigrationContext to run; patching the helpers lets us drive
    the migration against a plain SQLAlchemy connection.
    """
    dialect = sa_conn.engine.dialect

    def fake_create_table(table_name, *columns, **_kw):
        col_defs = [
            _compile_column(c, dialect) for c in columns if isinstance(c, sa.Column)
        ]
        ddl = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
        sa_conn.execute(sa.text(ddl))

    def fake_create_index(index_name, table_name, cols, **_kw):
        ddl = f"CREATE INDEX {index_name} ON {table_name} ({', '.join(cols)})"
        sa_conn.execute(sa.text(ddl))

    def fake_drop_index(index_name, table_name=None, **_kw):
        sa_conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))

    def fake_drop_table(table_name, **_kw):
        sa_conn.execute(sa.text(f"DROP TABLE IF EXISTS {table_name}"))

    return [
        patch("alembic.op.get_bind", return_value=sa_conn),
        patch("alembic.op.create_table", side_effect=fake_create_table),
        patch("alembic.op.create_index", side_effect=fake_create_index),
        patch("alembic.op.drop_index", side_effect=fake_drop_index),
        patch("alembic.op.drop_table", side_effect=fake_drop_table),
    ]


def test_031_module_loads():
    mig = _load_migration()
    assert mig.revision == "031_telegram_inventory_session"
    assert mig.down_revision == "030_acct_identity"


def test_031_downgrade_drops_table_when_present(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "d.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        sa_conn.execute(
            sa.text(
                "CREATE TABLE telegram_inventory_session ("
                " chat_id TEXT PRIMARY KEY,"
                " status TEXT NOT NULL DEFAULT 'active')"
            )
        )
        sa_conn.execute(sa.text("CREATE INDEX ix_tg_inv_status ON telegram_inventory_session (status)"))
        sa_conn.execute(sa.text("CREATE INDEX ix_tg_inv_last_action ON telegram_inventory_session (status)"))
        sa_conn.commit()

        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.downgrade()
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    assert "telegram_inventory_session" not in insp.get_table_names()


def test_031_downgrade_is_noop_when_table_absent(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "d2.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.downgrade()  # must not raise
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    assert "telegram_inventory_session" not in insp.get_table_names()


def test_031_upgrade_creates_table_and_is_idempotent(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "u.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.upgrade()
            mig.upgrade()  # idempotent — must not raise
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    assert "telegram_inventory_session" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("telegram_inventory_session")}
    expected = {
        "chat_id", "user_id", "status", "current_category", "item_queue",
        "cursor", "page", "pending_prompt", "last_item_id", "stats",
        "nudge_muted_until", "last_nudge_sent_at", "started_at", "last_action_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"

    idx_names = {i["name"] for i in insp.get_indexes("telegram_inventory_session")}
    assert "ix_tg_inv_status" in idx_names
    assert "ix_tg_inv_last_action" in idx_names
