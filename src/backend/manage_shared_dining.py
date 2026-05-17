"""Shared dining / receipt splitting service layer.

All public functions take a SQLAlchemy session as their first argument and
commit at the end. Callers should not commit again.
"""
from __future__ import annotations

from datetime import datetime, timezone


class SplitValidationError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_shared_expense(
    session,
    purchase_id: int,
    payment_scenario: str,
    participants: list[dict],
    notes: str | None = None,
) -> object:
    """Create a SharedExpense for an existing purchase.

    participants is a list of dicts with keys:
        is_self (bool), contact_id (int|None), ad_hoc_name (str|None),
        share_amount (float), payer (bool, OWED scenario only)

    Raises SplitValidationError for bad input.
    """
    from src.backend.initialize_database_schema import (
        Purchase, SharedExpense, SharedParticipant, SharedDebt,
    )

    if payment_scenario not in ("PAID_ALL", "PAID_OWN", "OWED"):
        raise SplitValidationError(f"Invalid payment_scenario: {payment_scenario!r}")

    purchase = session.get(Purchase, purchase_id)
    if purchase is None:
        raise SplitValidationError(f"Purchase {purchase_id} not found")

    self_rows = [p for p in participants if p.get("is_self")]
    if len(self_rows) != 1:
        raise SplitValidationError("Exactly one participant must have is_self=True")

    total_amount = purchase.total_amount or 0.0
    share_sum = round(sum(p["share_amount"] for p in participants), 2)
    if abs(share_sum - round(total_amount, 2)) > 0.01:
        raise SplitValidationError(
            f"Share amounts sum to {share_sum:.2f} but purchase total is {total_amount:.2f}"
        )

    if payment_scenario == "OWED":
        payers = [p for p in participants if p.get("payer")]
        if len(payers) != 1:
            raise SplitValidationError("OWED scenario requires exactly one participant marked payer=True")

    existing = session.query(SharedExpense).filter_by(purchase_id=purchase_id).one_or_none()
    if existing:
        raise SplitValidationError(f"Purchase {purchase_id} already has a shared expense")

    my_amount = self_rows[0]["share_amount"]
    expense = SharedExpense(
        purchase_id=purchase_id,
        total_amount=total_amount,
        my_amount=my_amount,
        payment_scenario=payment_scenario,
        notes=notes,
    )
    session.add(expense)
    session.flush()

    participant_rows: list[tuple] = []
    for p_data in participants:
        row = SharedParticipant(
            shared_expense_id=expense.id,
            contact_id=p_data.get("contact_id"),
            ad_hoc_name=p_data.get("ad_hoc_name"),
            is_self=bool(p_data.get("is_self")),
            share_amount=p_data["share_amount"],
        )
        session.add(row)
        session.flush()
        participant_rows.append((row, p_data))

    if payment_scenario == "PAID_ALL":
        for row, _ in participant_rows:
            if not row.is_self:
                session.add(SharedDebt(
                    shared_expense_id=expense.id,
                    participant_id=row.id,
                    direction="THEY_OWE_ME",
                    amount=row.share_amount,
                ))

    elif payment_scenario == "OWED":
        payer_row = next(row for row, pd in participant_rows if pd.get("payer"))
        session.add(SharedDebt(
            shared_expense_id=expense.id,
            participant_id=payer_row.id,
            direction="I_OWE_THEM",
            amount=my_amount,
        ))

    session.commit()
    session.refresh(expense)
    return expense
