from datetime import datetime, timedelta

def derive_planning_month(
    due_date: str = None,
    service_period_end: str = None,
    receipt_date: str = None,
    billing_cycle_month: str = None,
) -> str:
    # 1. Planning month primarily follows the due date month.
    if due_date and str(due_date).strip():
        try:
            dt = datetime.strptime(str(due_date).strip(), "%Y-%m-%d")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    # 2. If due date is unavailable, fall back to the service period end month.
    if service_period_end and str(service_period_end).strip():
        try:
            dt = datetime.strptime(str(service_period_end).strip(), "%Y-%m-%d")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    # 3. Preserve compatibility with older bill metadata that explicitly stored
    # a cycle month before service-period capture became the preferred source.
    if billing_cycle_month and str(billing_cycle_month).strip():
        try:
            dt = datetime.strptime(str(billing_cycle_month).strip(), "%Y-%m")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    # 4. Final fallback is the receipt / statement month.
    if receipt_date and str(receipt_date).strip():
        try:
            dt = datetime.strptime(str(receipt_date).strip(), "%Y-%m-%d")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    # Final fallback if absolutely nothing valid was provided
    return None


def derive_planning_month_for_cash_transaction(
    transaction_date: str | datetime | None,
    service_line=None,
) -> str | None:
    if not transaction_date:
        return None

    if isinstance(transaction_date, datetime):
        tx_dt = transaction_date
    else:
        try:
            tx_dt = datetime.strptime(str(transaction_date).strip(), "%Y-%m-%d")
        except ValueError:
            return None

    rule = str(getattr(service_line, "planning_month_rule", "") or "").strip().lower()
    expected_payment_day = getattr(service_line, "expected_payment_day", None)

    if rule == "paid_date_month":
        return tx_dt.strftime("%Y-%m")

    if rule == "due_date_month" and expected_payment_day:
        try:
            expected_day = int(expected_payment_day)
        except (TypeError, ValueError):
            expected_day = None

        if expected_day:
            expected_dt = tx_dt.replace(day=expected_day)
            if expected_day == 1 and tx_dt.day >= 28:
                expected_dt = (expected_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
            return expected_dt.strftime("%Y-%m")

    return tx_dt.strftime("%Y-%m")
