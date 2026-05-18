"""Telegram /split conversation state machine for shared dining.

State stored in TelegramSplitSession.state (JSON):
  {
    "step": str,            # select_receipt | select_scenario | add_participants | confirm
    "purchase_id": int,
    "purchase_label": str,
    "payment_scenario": str,
    "total_amount": float,
    "participants": [
      {"name": str, "contact_id": int|null, "share_amount": float, "is_self": bool}
    ],
    "awaiting_participant_name": bool
  }
"""
from __future__ import annotations

import logging
import os

from src.backend.initialize_database_schema import (
    TelegramSplitSession, DiningContact, Purchase, SharedExpense,
)
from src.backend.manage_shared_dining import (
    create_shared_expense, get_all_balances, settle_all_with_contact,
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_or_create_split_session(session, chat_id: str):
    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        row = TelegramSplitSession(chat_id=chat_id, state={})
        session.add(row)
        session.flush()
    return row


def save_split_state(session, chat_id: str, state: dict) -> None:
    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        row = TelegramSplitSession(chat_id=chat_id, state=state)
        session.add(row)
    else:
        row.state = state
    session.commit()


def clear_split_session(session, chat_id: str) -> None:
    row = session.get(TelegramSplitSession, chat_id)
    if row:
        session.delete(row)
        session.commit()


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def build_receipt_keyboard(session) -> list[dict]:
    """Return up to 5 recent purchases as inline buttons."""
    purchases = (
        session.query(Purchase)
        .outerjoin(SharedExpense, SharedExpense.purchase_id == Purchase.id)
        .filter(SharedExpense.id.is_(None))
        .order_by(Purchase.date.desc())
        .limit(5)
        .all()
    )
    buttons = []
    for p in purchases:
        label = f"${p.total_amount:.2f}"
        if hasattr(p, "store") and p.store:
            label = f"{p.store.name} {label}"
        buttons.append({
            "text": label,
            "callback_data": f"split:receipt:{p.id}:{p.total_amount:.2f}",
        })
    return buttons


def build_scenario_keyboard() -> list[list[dict]]:
    return [[
        {"text": "I Paid All",     "callback_data": "split:scenario:PAID_ALL"},
        {"text": "Paid My Share",  "callback_data": "split:scenario:PAID_OWN"},
        {"text": "I Owe Someone",  "callback_data": "split:scenario:OWED"},
    ]]


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

def _send(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    import requests
    import json as _json
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = _json.dumps(reply_markup)
    try:
        requests.post(f"{TELEGRAM_API_BASE}/sendMessage", json=payload, timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send Telegram message: %s", exc)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def start_split(session, chat_id: str) -> None:
    """Handle /split command — show recent receipts."""
    buttons = build_receipt_keyboard(session)
    if not buttons:
        _send(chat_id, "No receipts found to split.")
        return

    save_split_state(session, chat_id, {"step": "select_receipt"})
    _send(
        chat_id,
        "Which receipt do you want to split?",
        reply_markup={"inline_keyboard": [buttons]},
    )


def handle_split_callback(session, chat_id: str, data: str) -> bool:
    """Dispatch a split:* callback_data string. Returns True if consumed."""
    if not data.startswith("split:"):
        return False

    parts = data.split(":")
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "receipt":
        if len(parts) < 4:
            return False
        try:
            purchase_id = int(parts[2])
            total = float(parts[3])
        except (ValueError, IndexError):
            return False
        save_split_state(session, chat_id, {
            "step": "select_scenario",
            "purchase_id": purchase_id,
            "total_amount": total,
            "purchase_label": f"${total:.2f}",
            "participants": [],
        })
        _send(
            chat_id,
            f"Receipt: <b>${total:.2f}</b>\n\nWho paid?",
            reply_markup={"inline_keyboard": build_scenario_keyboard()},
        )
        return True

    if sub == "scenario":
        if len(parts) < 3:
            return False
        scenario = parts[2]
        row = get_or_create_split_session(session, chat_id)
        state = dict(row.state)
        state["step"] = "add_participants"
        state["payment_scenario"] = scenario
        state["participants"] = [
            {"name": "You", "is_self": True, "contact_id": None, "share_amount": 0.0}
        ]
        save_split_state(session, chat_id, state)
        _send(
            chat_id,
            (
                f"Scenario: <b>{scenario.replace('_', ' ').title()}</b>\n\n"
                "Type participant names one at a time (e.g. \"John Smith\").\n"
                "Send /splitdone when everyone is added."
            ),
        )
        return True

    if sub == "confirm":
        _finalize_split(session, chat_id)
        return True

    if sub == "cancel":
        clear_split_session(session, chat_id)
        _send(chat_id, "Split cancelled.")
        return True

    return False


def consume_split_text(session, chat_id: str, text: str) -> bool:
    """Try to consume typed text as a participant name. Returns True if consumed."""
    row = session.get(TelegramSplitSession, chat_id)
    if row is None or row.state.get("step") != "add_participants":
        return False

    name = text.strip()
    if not name:
        return False

    state = dict(row.state)
    total = state.get("total_amount", 0.0)
    participants: list = state.get("participants", [])

    existing_contact = (
        session.query(DiningContact)
        .filter(DiningContact.name.ilike(f"%{name}%"))
        .first()
    )
    contact_id = existing_contact.id if existing_contact else None
    participants.append({
        "name": name,
        "is_self": False,
        "contact_id": contact_id,
        "share_amount": 0.0,
    })
    state["participants"] = participants

    count = len(participants)
    equal_share = round(total / count, 2) if count else 0.0
    remainder = round(total - equal_share * count, 2) if count else 0.0
    for i, p in enumerate(state["participants"]):
        p["share_amount"] = round(equal_share + (remainder if i == 0 else 0.0), 2)

    save_split_state(session, chat_id, state)

    names_list = "\n".join(
        f"  {'(You)' if p['is_self'] else p['name']}: ${p['share_amount']:.2f}"
        for p in participants
    )
    _send(
        chat_id,
        (
            f"Added <b>{name}</b>{'  ✓ saved contact' if contact_id else ' (new)'}\n\n"
            f"Current split (${total:.2f} total):\n{names_list}\n\n"
            "Add more names or send /splitdone to confirm."
        ),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirm Split", "callback_data": "split:confirm"},
            {"text": "❌ Cancel",        "callback_data": "split:cancel"},
        ]]},
    )
    return True


def handle_splitdone_command(session, chat_id: str) -> None:
    """Handle /splitdone — show summary and ask for confirmation."""
    row = session.get(TelegramSplitSession, chat_id)
    if row is None or row.state.get("step") != "add_participants":
        _send(chat_id, "No split in progress. Use /split to start.")
        return

    state = dict(row.state)
    participants = state.get("participants", [])
    if len(participants) < 2:
        _send(chat_id, "Add at least one other person before confirming.")
        return

    total = state.get("total_amount", 0.0)
    names_list = "\n".join(
        f"  {'You' if p['is_self'] else p['name']}: ${p['share_amount']:.2f}"
        for p in participants
    )
    scenario_label = state.get("payment_scenario", "").replace("_", " ").title()

    _send(
        chat_id,
        (
            f"<b>Split Summary</b>\n"
            f"Scenario: {scenario_label}\n\n"
            f"{names_list}\n"
            f"Total: ${total:.2f}\n\n"
            "Confirm?"
        ),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Save", "callback_data": "split:confirm"},
            {"text": "❌ Cancel", "callback_data": "split:cancel"},
        ]]},
    )


def _finalize_split(session, chat_id: str) -> None:
    """Create the SharedExpense from current state and clear the session."""
    row = session.get(TelegramSplitSession, chat_id)
    if row is None:
        _send(chat_id, "No split in progress.")
        return

    state = dict(row.state)
    purchase_id = state.get("purchase_id")
    payment_scenario = state.get("payment_scenario", "PAID_OWN")
    participants = list(state.get("participants", []))

    # OWED with 3+ participants: first non-self person is assumed payer (spec gap)
    if payment_scenario == "OWED" and len(participants) >= 2:
        participants[1] = {**participants[1], "payer": True}

    try:
        expense = create_shared_expense(session, purchase_id, payment_scenario, participants)
        my_amount = expense.my_amount
        clear_split_session(session, chat_id)
        _send(chat_id, f"✅ Split saved! Your share: <b>${my_amount:.2f}</b>")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to finalize split for chat %s: %s", chat_id, exc)
        _send(chat_id, f"❌ Could not save split: {exc}")


# ---------------------------------------------------------------------------
# /balances, /settle, /owed commands
# ---------------------------------------------------------------------------

def handle_balances_command(session, chat_id: str) -> None:
    balances = get_all_balances(session)
    if not balances:
        _send(chat_id, "No outstanding balances.")
        return

    lines = []
    for b in balances:
        amount = b["net_amount"]
        if amount > 0:
            lines.append(f"  {b['name']} owes you <b>${amount:.2f}</b>")
        else:
            lines.append(f"  You owe {b['name']} <b>${abs(amount):.2f}</b>")
    _send(chat_id, "💰 <b>Balances</b>\n" + "\n".join(lines))


def handle_settle_command(session, chat_id: str, args: str) -> None:
    name = args.strip().lstrip("@")
    if not name:
        _send(chat_id, "Usage: /settle <name>")
        return

    contact = (
        session.query(DiningContact)
        .filter(DiningContact.name.ilike(f"%{name}%"))
        .first()
    )
    if not contact:
        _send(chat_id, f"No contact found matching '{name}'.")
        return

    count = settle_all_with_contact(session, contact.id)
    _send(chat_id, f"✅ Settled {count} debt(s) with {contact.name}.")


def handle_owed_command(session, chat_id: str) -> None:
    balances = get_all_balances(session)
    owed = [b for b in balances if b["net_amount"] < 0]
    if not owed:
        _send(chat_id, "You don't owe anyone right now.")
        return

    lines = [f"  {b['name']}: <b>${abs(b['net_amount']):.2f}</b>" for b in owed]
    _send(chat_id, "You owe:\n" + "\n".join(lines))
