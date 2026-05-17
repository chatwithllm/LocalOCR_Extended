# Shared Dining / Receipt Splitting — Design

**Date:** 2026-05-17  
**Status:** Approved  
**Branch:** feat/shared-dining

---

## Problem

A scanned restaurant receipt shows the full table total (e.g. $370.20). When dining was shared between multiple families, there is no way to record your actual portion without editing the raw receipt amount. Users need to mark a receipt as shared, track who paid what, and manage debts across contacts.

---

## Scope

- Mark any scanned receipt as a shared expense
- Record user's actual portion for budgeting (full scanned amount preserved)
- Track three payment scenarios: paid all, paid own share, owe someone else
- Equal split by default; per-person custom override
- Saved contacts + ad-hoc names
- Per-receipt debt settlement + running balance per contact
- Web UI + Telegram bot

---

## Data Models

### Contact
```
id            PK
name          str
phone         str?
email         str?
created_at    datetime
```
Saved friends. Ad-hoc names are stored on `SharedParticipant.ad_hoc_name`; they can be promoted to a Contact later.

### SharedExpense
```
id                PK
receipt_id        FK(Receipt), UNIQUE  — 1:1 relationship
total_amount      decimal              — mirrors receipt total (read-only copy)
my_amount         decimal              — user's actual portion
payment_scenario  enum: PAID_ALL | PAID_OWN | OWED
notes             str?
created_at        datetime
```

### SharedParticipant
```
id                  PK
shared_expense_id   FK(SharedExpense)
contact_id          FK(Contact)?       — null = ad-hoc or self
ad_hoc_name         str?               — used when contact_id is null and not self
is_self             bool (default false) — marks the current user's row
share_amount        decimal            — their portion of the bill
created_at          datetime
```
Exactly one row per person at the table, including the user themselves. The user's row has `is_self=True`; `my_amount` on `SharedExpense` must equal this row's `share_amount`.

### Debt
```
id                  PK
shared_expense_id   FK(SharedExpense)
participant_id      FK(SharedParticipant)
direction           enum: THEY_OWE_ME | I_OWE_THEM
amount              decimal
settled             bool (default false)
settled_at          datetime?
settled_note        str?
created_at          datetime
```

---

## Debt Creation Rules

| Scenario  | Debts created |
|-----------|---------------|
| PAID_ALL  | `THEY_OWE_ME` for every participant except self |
| PAID_OWN  | None — everyone settled at table |
| OWED      | Single `I_OWE_THEM` for the specified payer contact |

---

## Service Layer

`SharedExpenseService` — all operations transactional:

```python
create_shared_expense(
    receipt_id, participants, payment_scenario, my_amount=None
)
# Validates: sum(share_amounts) == receipt.total_amount
# Auto equal-splits if no custom amounts given
# Creates SharedExpense + SharedParticipants + Debts atomically

update_split(shared_expense_id, participant_id, new_amount)
# Recalculates remaining participants proportionally (or manual)
# Regenerates debts

settle_debt(debt_id, note=None)
# Marks settled, stamps settled_at

settle_all_with_contact(contact_id)
# Bulk-settles all unsettled debts with contact across all receipts

get_balance_with_contact(contact_id) -> Decimal
# Positive = they owe you, Negative = you owe them

get_all_balances() -> list[{contact, net_amount}]

merge_contact(ad_hoc_participant_id, contact_id)
# Promotes ad-hoc participant to saved contact
# Repoints all debts from that participant to the contact
```

### Validation Rules
- `sum(share_amounts)` must equal `receipt.total_amount` — hard block
- `my_amount` must match user's own `SharedParticipant.share_amount`
- `OWED` scenario requires exactly one payer contact specified
- Partial custom amounts: remaining balance distributed equally among untouched participants

---

## Web UI

### Receipt Detail Page
"Split this receipt" button opens inline panel (no page redirect):

```
┌─ Split Receipt: $370.20 ─────────────────────────────────┐
│ Payment scenario:  [Paid All] [Paid Own] [I Owe]         │
│                                                           │
│ Participants  (+Add person)                               │
│  You          $92.55   [edit]                            │
│  John Smith   $92.55   [edit]   [× remove]               │
│  Sarah K.     $92.55   [edit]   [× remove]               │
│  Ad-hoc: "Ali family"  $92.55  [edit]  [× remove]        │
│                                                           │
│ Total split: $370.20 ✓  (must match receipt)             │
│                                         [Cancel] [Save]  │
└───────────────────────────────────────────────────────────┘
```

### Balances Page (new nav item)
```
Contact          They owe you    You owe
John Smith       $92.55          —
Sarah K.         $46.00          —
Ali family (ad)  —               $30.00

[View history]  [Settle all]  ← per row
```

### Receipt List
Shared receipts show badge: `👥 $92.55 (your share)` in budget/spend views instead of full amount.

### Contacts Page
Simple CRUD. Merge ad-hoc → saved contact when added later; existing debts repoint to the new Contact.

---

## Telegram Bot

Flow triggered by `/split` command or inline button after scanning:

```
Bot:  "Which receipt to split?"
      [lists recent unsplit receipts as buttons]

User: [taps receipt]

Bot:  "Who paid?"
      [Paid All] [Paid Own] [I Owe Someone]

      → PAID_ALL path:

Bot:  "How many people (including you)?"
User: 4

Bot:  "Split $370.20 equally → $92.55 each. Add participants:"
      [Pick from contacts] [Type a name]

      ... user adds 3 participants ...

Bot:  "Summary:
       You        $92.55
       John Smith $92.55
       Sarah K.   $92.55
       Ali family $92.55
       Total: $370.20 ✓

       Any custom amounts?"
       [Yes, adjust] [No, save]

User: [No, save] → debts created, confirmation sent
```

**Additional commands:**
- `/balances` — net balance per contact
- `/settle @name` — mark all debts with contact settled
- `/owed` — what you owe others

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Split total ≠ receipt total | Hard block; show diff ("$5.00 unaccounted") |
| Duplicate contact name | Prompt: merge or keep separate |
| Receipt already split | Show existing split; offer edit or delete |
| Contact deleted | Debts retain name snapshot at time of split |
| OWED with no payer specified | Validation error before save |
| Partial custom amounts | Remaining distributed equally among untouched participants |

---

## Testing Plan

**Unit:**
- `SharedExpenseService` — all 3 payment scenarios, equal split, custom split, validation errors
- Balance calculation — multi-receipt accumulation, partial settlements

**Integration:**
- Receipt → split → debt creation → settlement full flow
- Telegram conversation flow (mirrors existing bot test patterns)

**E2E:**
- Scan receipt → split → Balances page shows correct net amounts

---

## Migration

Additive only — 4 new tables (`contacts`, `shared_expenses`, `shared_participants`, `debts`). Zero changes to existing `receipts` table. Safe to deploy alongside current schema.
