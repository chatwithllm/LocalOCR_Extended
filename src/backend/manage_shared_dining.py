"""Shared dining / receipt splitting service layer.

All public functions take a SQLAlchemy session as their first argument and
commit at the end. Callers should not commit again.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.backend.initialize_database_schema import (
    Purchase, SharedExpense, SharedParticipant, SharedDebt, DiningContact,
)


class SplitValidationError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # used by Task 4 settlement functions


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
        if payers[0].get("is_self"):
            raise SplitValidationError("Payer must not be the self participant")

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


def update_split(
    session,
    shared_expense_id: int,
    participant_id: int,
    new_amount: float,
) -> object:
    """Change one participant's share_amount, adjusting others proportionally.

    After the update, all debt records for the expense are regenerated.
    """
    expense = session.get(SharedExpense, shared_expense_id)
    if expense is None:
        raise SplitValidationError(f"SharedExpense {shared_expense_id} not found")

    target = session.get(SharedParticipant, participant_id)
    if target is None or target.shared_expense_id != shared_expense_id:
        raise SplitValidationError(f"Participant {participant_id} not in expense {shared_expense_id}")

    old_amount = target.share_amount
    delta = new_amount - old_amount
    others = [p for p in expense.participants if p.id != participant_id]
    if not others:
        raise SplitValidationError("Cannot update: no other participants")

    target.share_amount = new_amount
    others_total = sum(p.share_amount for p in others)
    if others_total > 0.001:
        for p in others:
            p.share_amount = round(p.share_amount - delta * (p.share_amount / others_total), 2)

    new_sum = sum(p.share_amount for p in expense.participants)
    if abs(new_sum - expense.total_amount) > 0.01:
        raise SplitValidationError(
            f"Amounts don't balance to {expense.total_amount:.2f} after update (got {new_sum:.2f})"
        )

    self_row = next((p for p in expense.participants if p.is_self), None)
    if self_row:
        expense.my_amount = self_row.share_amount

    # Capture payer identity before deleting debts
    owed_payer_id: int | None = None
    if expense.payment_scenario == "OWED":
        for p in expense.participants:
            if any(d.direction == "I_OWE_THEM" for d in p.debts):
                owed_payer_id = p.id
                break

    for debt in list(expense.debts):
        session.delete(debt)
    session.flush()

    if expense.payment_scenario == "PAID_ALL":
        for p in expense.participants:
            if not p.is_self:
                session.add(SharedDebt(
                    shared_expense_id=expense.id,
                    participant_id=p.id,
                    direction="THEY_OWE_ME",
                    amount=p.share_amount,
                ))
    elif expense.payment_scenario == "OWED" and owed_payer_id is not None:
        session.add(SharedDebt(
            shared_expense_id=expense.id,
            participant_id=owed_payer_id,
            direction="I_OWE_THEM",
            amount=expense.my_amount,
        ))

    session.commit()
    session.refresh(expense)
    return expense


def settle_debt(session, debt_id: int, note: str | None = None) -> object:
    """Mark a single debt as settled."""
    debt = session.get(SharedDebt, debt_id)
    if debt is None:
        raise SplitValidationError(f"Debt {debt_id} not found")
    debt.settled = True
    debt.settled_at = _utcnow()
    debt.settled_note = note
    session.commit()
    return debt


def settle_all_with_contact(session, contact_id: int) -> int:
    """Settle all unsettled debts linked to a contact. Returns count settled."""
    debts = (
        session.query(SharedDebt)
        .join(SharedParticipant, SharedDebt.participant_id == SharedParticipant.id)
        .filter(SharedParticipant.contact_id == contact_id, SharedDebt.settled == False)  # noqa: E712
        .all()
    )
    now = _utcnow()
    for debt in debts:
        debt.settled = True
        debt.settled_at = now
    session.commit()
    return len(debts)


def get_balance_with_contact(session, contact_id: int) -> float:
    """Net unsettled balance with a contact.

    Returns: positive = they owe you, negative = you owe them.
    """
    debts = (
        session.query(SharedDebt)
        .join(SharedParticipant, SharedDebt.participant_id == SharedParticipant.id)
        .filter(SharedParticipant.contact_id == contact_id, SharedDebt.settled == False)  # noqa: E712
        .all()
    )
    balance = 0.0
    for debt in debts:
        if debt.direction == "THEY_OWE_ME":
            balance += debt.amount
        else:
            balance -= debt.amount
    return round(balance, 2)


def get_all_balances(session) -> list[dict]:
    """Return [{contact_id, name, net_amount}] for contacts with non-zero unsettled balance."""
    contacts = session.query(DiningContact).all()
    result = []
    for contact in contacts:
        balance = get_balance_with_contact(session, contact.id)
        if abs(balance) >= 0.01:
            result.append({
                "contact_id": contact.id,
                "name": contact.name,
                "net_amount": balance,
            })
    return sorted(result, key=lambda x: abs(x["net_amount"]), reverse=True)


def merge_contact(session, ad_hoc_participant_id: int, contact_id: int) -> object:
    """Promote an ad-hoc participant to a saved contact. Debts follow automatically."""
    participant = session.get(SharedParticipant, ad_hoc_participant_id)
    if participant is None:
        raise SplitValidationError(f"Participant {ad_hoc_participant_id} not found")
    if participant.contact_id is not None:
        raise SplitValidationError("Participant already linked to a saved contact")

    contact = session.get(DiningContact, contact_id)
    if contact is None:
        raise SplitValidationError(f"Contact {contact_id} not found")

    participant.contact_id = contact_id
    participant.ad_hoc_name = None
    session.commit()
    return participant
