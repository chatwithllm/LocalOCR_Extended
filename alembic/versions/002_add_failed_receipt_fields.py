"""add failed receipt retry fields - file_hash, error_message, retry_count, last_reprocessed_at

Revision ID: 002_add_failed_receipt_fields
Revises: 001_initial
Create Date: 2026-04-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_add_failed_receipt_fields"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fields to telegram_receipts for failed receipt tracking and deduplication."""
    # file_hash: SHA-256 hash of uploaded file for duplicate detection
    op.add_column(
        "telegram_receipts",
        sa.Column("file_hash", sa.String(64), nullable=True),
    )
    # Create index on file_hash for fast duplicate lookup
    op.create_index(
        "ix_telegram_receipts_file_hash",
        "telegram_receipts",
        ["file_hash"],
    )

    # error_message: store OCR/validation failure reason
    op.add_column(
        "telegram_receipts",
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # retry_count: track how many times reprocess was attempted
    op.add_column(
        "telegram_receipts",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # last_reprocessed_at: timestamp of most recent reprocess attempt
    op.add_column(
        "telegram_receipts",
        sa.Column("last_reprocessed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Remove failed receipt tracking fields."""
    op.drop_index("ix_telegram_receipts_file_hash", table_name="telegram_receipts")
    op.drop_column("telegram_receipts", "file_hash")
    op.drop_column("telegram_receipts", "error_message")
    op.drop_column("telegram_receipts", "retry_count")
    op.drop_column("telegram_receipts", "last_reprocessed_at")
