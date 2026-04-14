from src.backend.bill_planning import derive_planning_month


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
