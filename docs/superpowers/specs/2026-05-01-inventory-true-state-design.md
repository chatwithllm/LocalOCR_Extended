# Inventory as true source of truth — design

**Date:** 2026-05-01
**Status:** Draft, awaiting user review.

## Problem

Today the Inventory page is a derived projection: `rebuild_active_inventory`
recomputes quantities from receipts inside a 2-month rolling window and
overwrites the `Inventory` table. Consequences:

1. **Quantities lie.** Recent purchase ≠ on hand; nothing tracks consumption.
2. **Items vanish after 2 months** even when still on the shelf.
3. **Location is fictional** — every row defaults to `"Pantry"`.
4. **No expiration / aging** — no signal that produce is going bad.

Users want the inventory page to be the **authoritative state** of household
goods, not a list of recent receipts.

## Solution overview

Move from "Inventory is a derived projection" to "Inventory is the
state machine; receipt finalize is the only event that writes it."
Add real `location`, real `expires_at`, and a per-category shelf-life
table that drives sensible defaults.

The nightly `rebuild_active_inventory` cron call is dropped. The function
itself stays as a one-shot migration / disaster-recovery helper.

UI shows tiles grouped by location with color-coded expiry stripes
(green/yellow/orange/red) and pulsing animation when within 2 days of
expiry. Per-tile actions: ✎ edit, ⏸ +3d / +7d defer presets, −1 used,
✓ used up.

## Architecture

### Data model

**`Inventory` — five new columns** (additive, all nullable / defaulted):

```python
location           = Column(String(40),  default="Pantry")
expires_at         = Column(Date,        nullable=True)
expires_at_system  = Column(Date,        nullable=True)   # last system-computed
expires_source     = Column(String(10),  default="system")  # "system" | "user" | "defer"
last_purchased_at  = Column(DateTime,    nullable=True)
```

**`CategoryShelfLifeDefault` — new table:**

```python
class CategoryShelfLifeDefault(Base):
    category         = Column(String(40), primary_key=True)
    location_default = Column(String(40), nullable=False)
    shelf_life_days  = Column(Integer,    nullable=False, default=0)
```

`shelf_life_days = 0` means "no auto-expiry" (household, personal_care).

**Seed (inserted by migration 021):**

| Category | Location | Days |
|---|---|---|
| dairy | Fridge | 14 |
| produce | Fridge | 7 |
| meat | Fridge | 3 |
| seafood | Fridge | 2 |
| bakery | Pantry | 5 |
| beverages | Pantry | 365 |
| snacks | Pantry | 90 |
| frozen | Freezer | 180 |
| canned | Pantry | 730 |
| condiments | Pantry | 365 |
| household | Cabinet | 0 |
| personal_care | Bathroom | 0 |
| restaurant | Fridge | 3 |
| other | Pantry | 0 |

### Write paths (single source of truth)

**Receipt finalize** — the only automatic writer:

```python
for item in receipt_items:
    inv = session.query(Inventory).filter_by(product_id=item.product_id).first()
    if not inv:
        d = get_category_default(product.category)
        inv = Inventory(
            product_id=product.id, quantity=0,
            location=d.location_default,
            expires_source="system",
        )
        session.add(inv)

    inv.quantity         += float(item.quantity) * purchase_amount_sign(purchase)
    inv.last_purchased_at = purchase.date

    if d.shelf_life_days > 0:
        new_system = purchase.date.date() + timedelta(days=d.shelf_life_days)
        inv.expires_at_system = max(new_system, inv.expires_at_system or date.min)
        # Only overwrite the effective date when source == "system"
        if inv.expires_source == "system":
            inv.expires_at = inv.expires_at_system

    inv.last_updated = now()
```

User edits + defers are preserved across new receipts because the
guard `if expires_source == "system"` skips them.

**Manual PATCH endpoint** — `PATCH /api/inventory/<product_id>`:

Body fields (all optional): `quantity`, `location`, `expires_at`,
`defer_days`. Behavior:

- `quantity` — diff vs current quantity; writes
  `InventoryAdjustment(delta=…, reason="manual_edit"|"consumed"|"consumed_all")`.
- `location` — sets new value, `InventoryAdjustment(reason="moved")`.
- `expires_at` — sets explicit date, marks `expires_source="user"`,
  `InventoryAdjustment(reason="edit_expiry")`.
- `defer_days` (e.g. `3` or `7`) — bumps `expires_at += N` from
  whatever its current value is, marks `expires_source="defer"`,
  writes `InventoryAdjustment(reason="defer_expiry_+Nd")`.
  Successive clicks accumulate: two ⏸ +3d clicks = +6 days total.

A single PATCH may include multiple of these. Quantity floor is 0
(refund-induced negative balances clamp to 0; the audit row records
the requested delta even when the stored balance saturates).

**Reset to system** — `DELETE /api/inventory/<product_id>/expiry-override`
clears `expires_source="system"` and copies `expires_at_system → expires_at`.

**Shopping-list "Bought"** — explicit no-op for inventory. Only the
canonical receipt finalize event ever increments inventory. (Decision
locked Section 2.)

### Scheduler change

`rebuild_active_inventory` is no longer registered with APScheduler. It
remains importable as a CLI / admin tool for one-shot migration or
disaster recovery (e.g., DB rebuild from receipts).

`check_inventory_thresholds` still runs every 5 minutes; it reads
`Inventory.quantity` directly.

### UI

**Inventory page (`#page-inventory` in `index.html`):**

- Top toolbar: search box, location filter, sort (expiry asc / name /
  quantity), `+ Add` button, `Show empty` toggle (default off).
- Tiles grouped by location (Fridge / Freezer / Pantry / Cabinet /
  Bathroom). Each group is a collapsible section with summary line:
  `🧊 Fridge · 4 items · 2 expiring soon`.
- Tile content (180-260 px wide):
  - Header row: `Nd left` / `EXPIRED Nd ago` / `no expiry` (left), `×qty` (right). Color matches stripe.
  - Title: product name.
  - Metadata block: `📅 Bought YYYY-MM-DD`, `⏳ Shelf life ~Nd (category)`,
    `🍂 Expires YYYY-MM-DD` with provenance tag (`user` blue chip / `+3d defer` amber chip / no chip = system).
  - Actions row: `✎ edit` · `⏸ +3d` · `⏸ +7d` · `−1` · `✓ used up`.
- Stripe color states: red (≤0d), orange (1-3d), yellow (4-7d),
  green (8+d or NULL).
- Pulse animation on the expiry-date label and header when ≤2d. Respects
  `prefers-reduced-motion` — animation disabled, static color stays.
- "Used up" → toast with 5s undo. Zero-qty rows hide unless `Show empty`
  is on; greyed-out empty tile shows a "restock?" link → adds to current
  shopping list.

### Migration

**`alembic/versions/021_inventory_true_state.py`** (additive):

- ADD COLUMN × 5 on `inventory`, each PRAGMA-guarded with
  `_column_exists` (matches 020's pattern).
- CREATE TABLE IF NOT EXISTS `category_shelf_life_default`.
- INSERT 14 seed rows (idempotent via `INSERT OR IGNORE`).
- Downgrade: no-op.

**Data backfill** runs on container boot after `alembic upgrade head`,
once per DB:

```python
def backfill_inventory_truth(session):
    today = date.today()
    floor = today + timedelta(days=7)   # never compute past-date
    defaults = {row.category: row for row in
                session.query(CategoryShelfLifeDefault).all()}
    for inv in session.query(Inventory).all():
        if inv.expires_at_system is not None:
            continue   # already migrated
        product = session.query(Product).get(inv.product_id)
        if not product:
            continue
        d = defaults.get(product.category) or defaults["other"]
        last_ri = (session.query(ReceiptItem).filter_by(product_id=product.id)
                   .join(Purchase).order_by(Purchase.date.desc()).first())
        last_purchased = last_ri.purchase.date if last_ri else None
        inv.last_purchased_at = last_purchased
        if not inv.location:
            inv.location = d.location_default
        if d.shelf_life_days > 0 and last_purchased:
            inv.expires_at_system = max(
                last_purchased.date() + timedelta(days=d.shelf_life_days),
                floor,
            )
        else:
            inv.expires_at_system = None
        inv.expires_at = inv.expires_at_system
        inv.expires_source = "system"
    session.commit()
```

The `expires_at_system IS NOT NULL` guard makes re-runs safe.

## Data flow

```
[receipt finalize]
   for each ReceiptItem:
      Inventory upsert
        quantity += signed(qty)
        last_purchased_at = purchase.date
        expires_at_system = max(prev, purchase.date + shelf_life)
        if expires_source == "system": expires_at = expires_at_system
   per-row commit

[user opens Inventory page]
   GET /api/inventory?group=location
      returns rows grouped by location with computed days_left
      tile renders with stripe + pulse

[user taps ⏸ +3d]
   PATCH /api/inventory/<pid>  body: {defer_days: 3}
      expires_at += 3
      expires_source = "defer"
      InventoryAdjustment(delta=0, reason="defer_expiry_+3d")
      tile re-renders without flash

[user taps ✓ used up]
   PATCH /api/inventory/<pid>  body: {quantity: 0}
      InventoryAdjustment(delta=-old_qty, reason="consumed_all")
      toast "Used up · undo"
      tile hides (Show empty toggles back)
```

## Error handling

- Unknown product category → fall back to `"other"` defaults.
- Missing `CategoryShelfLifeDefault` table (corrupt DB) → hardcoded
  sentinel (Pantry, no expiry); warn-log.
- Invalid PATCH body (negative qty, malformed date) → 400 with field
  error; no partial write.
- Backfill mid-crash → per-row commit; re-run skips migrated rows.
- Receipt-finalize + PATCH race → SQLAlchemy session lock; last write
  wins. `expires_source="user"|"defer"` protects user intent from later
  receipts.

## Backup / restore safety

- Migration 021 is additive ADD COLUMN with `_column_exists` PRAGMA
  guard, no-op downgrade. Restoring an old tar without these columns
  upgrades cleanly on container boot.
- New `category_shelf_life_default` table uses CREATE IF NOT EXISTS.
- No new volumes. No moves under `/data`.
- Backup script (`manage_environment_ops`) is column-list-agnostic; new
  columns ride along transparently.

## Testing

### Unit — extends `tests/test_active_inventory.py`

- `test_finalize_inserts_inventory_with_category_defaults`
- `test_finalize_extends_expiry_when_newer_purchase`
- `test_finalize_preserves_user_override` — `expires_source="user"`
  not touched by next receipt
- `test_finalize_preserves_defer` — `expires_source="defer"` not touched
- `test_refund_decrements_quantity`
- `test_unknown_category_falls_back_to_other`

### Integration — new `tests/test_inventory_endpoints.py`

- `test_patch_quantity_writes_adjustment_row`
- `test_patch_expires_sets_user_source`
- `test_patch_defer_days_bumps_and_marks_defer_source`
- `test_reset_to_system_clears_override`
- `test_get_inventory_groups_by_location`
- `test_get_inventory_filters_zero_qty_by_default`

### Migration — new `tests/test_migration_021.py`

- `test_021_upgrade_adds_columns_idempotent`
- `test_021_seed_inserts_14_categories`
- `test_021_backfill_floors_to_today_plus_7`
- `test_021_backfill_skips_already_migrated`
- `test_021_downgrade_is_noop`

### Smoke (manual, post-deploy)

- [ ] `alembic upgrade head` → `.schema inventory` includes new columns
- [ ] `SELECT count(*) FROM category_shelf_life_default` = 14
- [ ] Inventory page renders with location groups
- [ ] Tile shows 📅 / ⏳ / 🍂 fields
- [ ] ≤2d expiry tile pulses; `prefers-reduced-motion` disables it
- [ ] ✎ edit persists with `user` chip
- [ ] ⏸ +3d persists with `+3d defer` chip
- [ ] −1 used and ✓ used up write `InventoryAdjustment` audit rows
- [ ] Receipt finalize on existing item extends `expires_at` only when
      `expires_source == "system"`
- [ ] **Backup → restore on dev → all above still works**

## YAGNI removed

- Per-item shelf-life override column (use category default; `✎ edit`
  on `expires_at` is the escape hatch)
- Multi-location for one product (one row per product+location)
- Auto-decrement on shopping-list "Bought" (locked no-op)
- Recipe-based bulk consumption
- Expiry notifications via Telegram / MQTT
- Frozen-extends-shelf-life automation (move to Freezer is just a
  location change; user can ⏸ +180d if they want the date too)
- Bulk import from external inventory trackers

## Out of scope

- Recipe planner integration
- Mobile app native push for expiry alerts
- Per-household personalized shelf-life learning (sees how fast you
  actually use a product)
- Barcode-scan add flow
