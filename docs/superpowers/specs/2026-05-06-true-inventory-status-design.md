# True Inventory Status — Design

**Date:** 2026-05-06
**Status:** Approved (brainstorming)

## Goal

Replace meaningless `x1 / x2` count tiles with a continuous "% remaining" status that auto-decays based on time-since-purchase + product shelf-life, plus a single-row visual fill (no extra UI rows). User taps the existing actions (`−1`, `✓`, `+3d`) and the bar reflects state automatically. Manual override available via long-press drag.

## Scope

**In:**
- `Product.expected_shelf_days` (per-product override; nullable)
- `Inventory.consumed_pct_override` (manual override; nullable)
- Server computes `remaining_pct` + `status` per row from `last_purchased_at`, `expected_shelf_days`, optional override
- Inventory tile title row gets a subtle fill behind the text (linear gradient via CSS variable). Status drives color (green/amber/red).
- Existing actions (`−1`, `✓`, `+3d`) updated to also adjust `consumed_pct_override`
- Long-press title row → drag-to-set % override

**Out (deferred):**
- Brand-aware shelf-life (ultra-pasteurized vs. regular milk) — Phase 2
- AI shelf-life suggestions on product creation — Phase 2
- Per-recipe planning consumption ("how many eggs do I have?") — relies on raw `quantity` + future `pack_size` — separate spec

---

## §1. Architecture

```
Migration 027 → Inventory.consumed_pct_override + Product.expected_shelf_days
                       ↓
Inventory list serializer computes remaining_pct + status per row
                       ↓
Frontend tile renders title-row fill via CSS variables
                       ↓
Tap actions (−1, ✓, +3d) → adjust override, refetch
```

No new endpoints. The inventory list response gains computed fields. Existing action endpoints get small additive logic.

---

## §2. Data Model

### Migration `027_inventory_true_status`

```python
op.add_column(
    "products",
    sa.Column("expected_shelf_days", sa.Integer(), nullable=True),
)
op.add_column(
    "inventory",
    sa.Column("consumed_pct_override", sa.Float(), nullable=True),
)
```

Idempotent + no-op downgrade (project pattern).

`expected_shelf_days = null` → fall back to `CATEGORY_SHELF_DAYS` table (in code). `consumed_pct_override = null` → use auto-decay.

### Category shelf-life defaults (in code, not DB)

```python
CATEGORY_SHELF_DAYS = {
    "dairy": 7,
    "milk": 7,
    "eggs": 21,
    "leafy_produce": 5,
    "produce": 7,
    "root_vegetables": 14,
    "fruit": 7,
    "meat": 4,
    "fish": 2,
    "frozen": 90,
    "pantry": 60,
    "snacks": 30,
    "beverages": 14,
    "condiments": 90,
    "baked": 5,
    "household": 180,
    "other": 30,
}
```

User-tunable later via Settings page; Phase 2.

---

## §3. Compute (server-side)

For each Inventory row in the list response:

```python
def compute_remaining(product, inventory, now):
    shelf_days = (
        product.expected_shelf_days
        or CATEGORY_SHELF_DAYS.get(product.category, CATEGORY_SHELF_DAYS["other"])
    )
    if inventory.consumed_pct_override is not None:
        consumed = max(0.0, min(100.0, inventory.consumed_pct_override))
    else:
        anchor = inventory.last_purchased_at or inventory.last_updated or now
        days_elapsed = max(0, (now - anchor).days)
        consumed = min(100.0, (days_elapsed / max(1, shelf_days)) * 100.0)
    remaining_pct = round(100.0 - consumed, 1)
    if remaining_pct >= 60:
        status = "fresh"
    elif remaining_pct >= 20:
        status = "low"
    else:
        status = "out"
    return {
        "shelf_days": shelf_days,
        "remaining_pct": remaining_pct,
        "status": status,
        "is_estimated": inventory.consumed_pct_override is None,
    }
```

Emitted on every Inventory row in `GET /inventory`:

```json
{
  "id": 12,
  "...existing fields...": "...",
  "remaining_pct": 60.0,
  "status": "low",
  "shelf_days": 7,
  "is_estimated": true
}
```

---

## §4. Action behavior changes

Only three existing actions need adjustment:

| Action | Current | New |
|--------|---------|-----|
| `−1` | quantity -= 1 | quantity -= 1 AND `consumed_pct_override = clamp(prev_or_auto + 100/qty_at_time, 0, 100)` |
| `✓` (used up) | quantity = 0, mark deleted | unchanged + `consumed_pct_override = 100` (so status flips to "out") |
| `+3d` | shifts `expires_at` by 3 days | unchanged + `consumed_pct_override = max(0, current - 30)` (treat as "got more time"). Optional. |
| Receipt scan / "+ Bought again" | adds quantity, updates `last_purchased_at` | unchanged + `consumed_pct_override = null` (resets to auto-decay from new purchase) |

`+3d` adjustment is debatable — keeping it isolated from override is also valid. **Default decision: leave `+3d` as date-only** (don't touch override). User can still drag bar.

---

## §5. Frontend

### Inventory tile (existing layout preserved)

Title row gets a subtle background fill via CSS pseudo-element. No new rows.

```html
<div class="inv-tile-title-row"
     style="--remaining-pct: 60%; --status-fill: rgba(255,159,10,0.20)">
  <span class="inv-tile-name">Organic Ataulfo</span>
  <span class="inv-tile-countdown">2d left</span>
</div>
```

```css
.inv-tile-title-row {
  position: relative;
  overflow: hidden;
  border-radius: 6px;
  padding: 6px 10px;
}
.inv-tile-title-row::before {
  content: "";
  position: absolute;
  inset: 0;
  width: var(--remaining-pct, 100%);
  background: var(--status-fill, rgba(52,199,89,0.18));
  z-index: 0;
  transition: width 240ms ease;
  pointer-events: none;
}
.inv-tile-title-row > * { position: relative; z-index: 1; }
```

Status colors (alpha 18-22%):
- fresh: `rgba(52,199,89,0.18)` (green)
- low: `rgba(255,159,10,0.20)` (amber)
- out: `rgba(255,69,58,0.22)` (red)

### Existing left-edge accent strip

Already there (green vertical bar). Make color match status (same palette as fill, full alpha).

### Interactions

- Tap title row anywhere except text → cycle status: fresh→low→out→fresh, sets override to bucket midpoint (80/40/10).
- Long-press title row (>500ms) → enter drag mode: bar follows finger horizontally, releases set override. Snap to 5% increments.
- Existing `−1`, `✓`, `+3d` buttons unchanged in appearance; behavior augmented per §4.

### `is_estimated` indicator

When `is_estimated == true` AND `last_purchased_at` is older than ~7 days, append a tiny faded "~est" suffix to the countdown text:

```
2d left · ~est
```

If user has touched the override within 7 days, drop the `~est`. Indicates trust level without clutter.

---

## §6. Errors + Edge Cases

| Case | Behavior |
|------|----------|
| `last_purchased_at == null` (legacy rows) | Fall back to `last_updated`; if also null, treat as "just purchased" → 100% remaining. |
| `expected_shelf_days == 0` or negative | Treat as null, use category default. |
| `consumed_pct_override` out-of-range | Clamp to [0, 100] on save. |
| `category == null` | Use `"other"` default (30 days). |
| Inventory row with `quantity == 0` | Tile shows `0%` remaining, status `out`. Existing "used up" path unchanged. |
| Drag during scroll | First 500ms = touch threshold avoids accidental drag. |
| Multiple Inventory rows for one Product (different locations) | Each row computes independently. |

---

## §7. Testing

### Backend (pytest, append to `tests/test_cards_overview.py` or new file)

- `test_compute_remaining_pure_auto_decay` — no override, 3 days into 7-day shelf → 57% remaining, status="low"
- `test_compute_remaining_override_wins` — override=10 → remaining=90 regardless of date math
- `test_compute_remaining_uses_category_default` — product.expected_shelf_days=null, category="dairy" → uses 7
- `test_compute_remaining_uses_other_when_category_unknown` — category=null → "other" → 30 days
- `test_compute_remaining_clamps_to_zero` — 60 days into 7-day shelf → 0%, status="out"
- `test_inventory_response_emits_status_fields` — `GET /inventory` rows carry `remaining_pct`, `status`, `shelf_days`, `is_estimated`
- `test_action_used_up_sets_override_100` — `✓` action sets `consumed_pct_override = 100`
- `test_action_decrement_bumps_override` — `−1` from qty=4 sets override to ≈25 (one quarter consumed)
- `test_purchase_resets_override_null` — buying again sets override = null

### Frontend (manual smoke)

- Tile shows green fill at fresh, amber at low, red at out
- Tap title row → status cycles, fill width updates with animation
- Long-press + drag → fill follows finger, releases save override
- `−1` button → fill width shrinks proportional to remaining qty
- `✓` button → fill collapses to 0%, row turns red
- `+3d` button → expiry pushes out, fill UNAFFECTED (per §4 default)
- New receipt for the product → fill returns to 100%, color reverts green
- "~est" suffix appears only when no manual touch in last 7d AND status is auto-derived

---

## Open questions / non-decisions

- `+3d` extending shelf life vs. only date display — kept as date-only for now. If users complain, change to also subtract 30% from override.
- Per-product `expected_shelf_days` editing UI — exposed in Phase 2 (Product detail page) so this spec doesn't block on form work. For now, populated via category defaults.
- Brand-aware shelf-life and AI suggestions — Phase 2.
