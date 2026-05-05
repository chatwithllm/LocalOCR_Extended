"""Tests for cards-overview feature: schema migration, endpoint, math, scoping."""
from src.backend.initialize_database_schema import Base


def test_plaid_account_has_credit_limit_columns():
    """Migration 025 must add credit_limit_cents and available_credit_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "credit_limit_cents" in cols
    assert "available_credit_cents" in cols
