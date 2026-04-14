from types import SimpleNamespace

from src.backend.bill_planning import (
    derive_planning_month,
    derive_planning_month_for_cash_transaction,
)


def test_derive_from_due_date_month():
    assert derive_planning_month(
        due_date="2026-05-02",
        service_period_end="2026-04-30",
        receipt_date="2026-05-05",
        billing_cycle_month="2026-04",
    ) == "2026-05"


def test_derive_from_service_period_end_when_due_date_missing():
    assert derive_planning_month(
        due_date=None,
        service_period_end="2026-04-30",
        receipt_date="2026-05-05",
        billing_cycle_month=None,
    ) == "2026-04"


def test_derive_from_legacy_billing_cycle_month_for_compatibility():
    assert derive_planning_month(
        due_date=None,
        service_period_end=None,
        receipt_date="2026-05-05",
        billing_cycle_month="2026-04",
    ) == "2026-04"


def test_derive_from_receipt_date_as_final_fallback():
    assert derive_planning_month(
        due_date=None,
        service_period_end=None,
        receipt_date="2026-07-22",
        billing_cycle_month=None,
    ) == "2026-07"


def test_derive_empty_values_handled_safely():
    assert derive_planning_month(
        due_date="",
        service_period_end="",
        receipt_date="2026-03-10",
        billing_cycle_month="",
    ) == "2026-03"


def test_edge_case_invalid_dates():
    assert derive_planning_month(
        due_date="invalid-date",
        service_period_end="invalid-date",
        receipt_date="invalid-date",
        billing_cycle_month="invalid-month",
    ) is None


def test_cash_transaction_derive_from_paid_date_month():
    service_line = SimpleNamespace(planning_month_rule="paid_date_month", expected_payment_day=None)
    assert derive_planning_month_for_cash_transaction("2026-04-10", service_line) == "2026-04"


def test_cash_transaction_derive_from_due_date_month():
    service_line = SimpleNamespace(planning_month_rule="due_date_month", expected_payment_day=1)
    assert derive_planning_month_for_cash_transaction("2026-04-10", service_line) == "2026-04"


def test_cash_transaction_derive_fallback_to_transaction_month():
    service_line = SimpleNamespace(planning_month_rule=None, expected_payment_day=None)
    assert derive_planning_month_for_cash_transaction("2026-04-10", service_line) == "2026-04"


def test_cash_transaction_cross_month_advances_for_first_of_month_services():
    service_line = SimpleNamespace(planning_month_rule="due_date_month", expected_payment_day=1)
    assert derive_planning_month_for_cash_transaction("2026-02-28", service_line) == "2026-03"
