from datetime import datetime

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
