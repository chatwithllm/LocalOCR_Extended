"""medication_user_id: add user_id FK to medications

Revision ID: 024_medication_user_id
Revises: 023_medicine_cabinet
Create Date: 2026-05-04
"""
from alembic import op

revision = "024_medication_user_id"
down_revision = "023_medicine_cabinet"
branch_labels = None
depends_on = None


def _col_exists(table, column):
    import sqlalchemy as sa
    bind = op.get_bind()
    cols = [r[1] for r in bind.execute(sa.text(f"PRAGMA table_info({table})"))]
    return column in cols


def upgrade():
    if not _col_exists("medications", "user_id"):
        op.execute("ALTER TABLE medications ADD COLUMN user_id INTEGER REFERENCES users(id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_medications_user_id ON medications(user_id)")


def downgrade():
    pass  # additive only
