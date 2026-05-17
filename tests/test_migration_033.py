# tests/test_migration_033.py
"""Tests for Alembic migration 033_shared_dining."""
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
    / "033_shared_dining.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_033", MIGRATION_PATH)
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
        if hasattr(arg, "compile"):
            default = f" DEFAULT {arg.compile(dialect=dialect)}"
        else:
            default = f" DEFAULT {arg!r}"
    return f"{col.name} {col_type}{pk}{notnull}{default}"


def _install_op_patches(sa_conn):
    """Patch alembic.op helpers to execute DDL on `sa_conn` directly."""
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


def test_033_module_loads():
    mig = _load_migration()
    assert mig.revision == "033_shared_dining"
    assert mig.down_revision == "032_telegram_shopping_session"


def test_migration_033_upgrade_creates_tables(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "test.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    # shared_expenses references purchases — create a stub so FK text compiles
    with engine.connect() as sa_conn:
        sa_conn.execute(sa.text("CREATE TABLE purchases (id INTEGER PRIMARY KEY)"))
        sa_conn.commit()

    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.upgrade()
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    tables = set(insp.get_table_names())
    assert "dining_contacts" in tables
    assert "shared_expenses" in tables
    assert "shared_participants" in tables
    assert "shared_debts" in tables
    assert "telegram_split_session" in tables


def test_033_upgrade_is_idempotent(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "idem.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        sa_conn.execute(sa.text("CREATE TABLE purchases (id INTEGER PRIMARY KEY)"))
        sa_conn.commit()

    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.upgrade()
            mig.upgrade()  # second call must not raise
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    assert "dining_contacts" in insp.get_table_names()


def test_migration_033_downgrade_drops_tables(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "test.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        sa_conn.execute(sa.text("CREATE TABLE purchases (id INTEGER PRIMARY KEY)"))
        sa_conn.commit()

    # Upgrade first, then downgrade
    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.upgrade()
            mig.downgrade()
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    tables = set(insp.get_table_names())
    assert "dining_contacts" not in tables
    assert "shared_expenses" not in tables
    assert "shared_participants" not in tables
    assert "shared_debts" not in tables
    assert "telegram_split_session" not in tables


def test_033_downgrade_is_noop_when_tables_absent(tmp_path):
    mig = _load_migration()
    db_path = tmp_path / "noop.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.connect() as sa_conn:
        patches = _install_op_patches(sa_conn)
        for p in patches:
            p.start()
        try:
            mig.downgrade()  # must not raise when tables don't exist
        finally:
            for p in patches:
                p.stop()
        sa_conn.commit()

    insp = sa.inspect(engine)
    assert "dining_contacts" not in insp.get_table_names()
