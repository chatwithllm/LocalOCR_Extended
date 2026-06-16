"""product essential + backup flags for the Kitchen essentials grid.

Revision ID: 034_product_essential_backup
Revises: 033_shared_dining
Create Date: 2026-06-16

Additive only — two boolean columns on products, both default False.
Downgrade drops them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "034_product_essential_backup"
down_revision: Union[str, None] = "033_shared_dining"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_essential", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "products",
        sa.Column("has_backup", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("products", "has_backup")
    op.drop_column("products", "is_essential")
