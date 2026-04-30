# Store visibility buckets — design

**Date:** 2026-04-30
**Status:** Draft, awaiting user review.

## Problem

After Phase 1 (canonicalize + payment-artifact filter) and Phase 2 (one-shot
backfill cleanup), the Stores dropdown still shows every merchant the user
has ever visited. Long tail of one-off / event purchases (a stadium snack
bar, an out-of-town dinner spot) crowd out the stores the user shops at
weekly. User wants:

> Have option to ignore store names that aren't often used. Or leave them
> in the list but list them below under a different label saying "low
> frequency" or something.

The need is not "delete data" — historical purchases at rare merchants
must remain attributable. The need is **declutter the picker**.

## Solution overview

Add a per-store visibility bucket: `frequent`, `low_freq`, or `hidden`.
Auto-classify based on purchase recency + count. Let the user pin any
store to a specific bucket via a Settings panel. Render the picker as
two `<optgroup>` sections (frequent on top, low-freq below). Hidden
rows are excluded from the picker entirely but still resolve in
historical pages.

## Architecture

### Data model

Single nullable column on `stores`:

```python
class Store(Base):
    ...
    is_payment_artifact = Column(Boolean, nullable=False, default=False)  # existing
    visibility_override = Column(String(16), nullable=True)               # NEW
```

`visibility_override` values:

| Value         | Meaning                                                    |
|---------------|------------------------------------------------------------|
| `NULL`        | Follow auto-classify rule.                                 |
| `"frequent"`  | Pin to top section regardless of usage.                    |
| `"low_freq"`  | Pin to "Rarely Used" section regardless of usage.          |
| `"hidden"`    | Exclude from the picker; still resolves in historical UI.  |

### Auto-classify rule

Time math is in **days from now** (ignoring calendar month length jitter).
`FREQUENT_DAYS = 90`. `LOW_FREQ_DAYS = 365`.

When `visibility_override IS NULL` and `is_payment_artifact = 0`:

| Bucket       | Condition                                                          |
|--------------|--------------------------------------------------------------------|
| `frequent`   | Last purchase within last 90 days.                                 |
| `low_freq`   | Last purchase 91–365 days ago.                                     |
| `hidden`     | No purchase, or last purchase > 365 days ago.                      |

When `is_payment_artifact = 1`: always `hidden`, regardless of override.
(Intentional — artifacts are never real merchants, never appear in picker.)

Thresholds (90 d, 365 d) are hardcoded for v1; promote to a settings page
only if real-world tuning demands it. Recency-based rather than lifetime
count: a store visited 10 times five years ago is not "frequent" today.

## Components

### Backend

- **`src/backend/initialize_database_schema.py`** — add `visibility_override`
  column to `Store`.
- **`alembic/versions/018_store_visibility_override.py`** — idempotent
  ADD COLUMN. Pattern: `_column_exists` PRAGMA guard, no-op downgrade.
  Default `NULL` ensures legacy rows fall through to auto-classify
  (which mirrors current behaviour: most rows are visible).
- **`src/backend/manage_stores.py`** *(new module)*:
  - `classify_store(store, last_purchase_at, purchase_count, now=None) -> str`
    — pure function, returns one of {`frequent`, `low_freq`, `hidden`}.
    Honours override + artifact flag.
  - `get_store_buckets(session)` — runs one query joining `stores` ←
    `purchases` with `MAX(purchase_date) AS last_purchase_at` and
    `COUNT(*) AS purchase_count`. Returns dict shaped:
    `{frequent: [{id, name, last_purchase_at, purchase_count}, ...],
      low_freq: [...], hidden: [...]}`.
- **`src/backend/manage_stores_endpoint.py`** *(new module, registered
  blueprint)*:
  - `GET /api/stores` — returns the bucket dict; requires auth.
  - `POST /api/stores/{id}/visibility` — body
    `{"override": "frequent" | "low_freq" | "hidden" | null}`. Validates
    enum, persists, returns updated record. 400 on bad enum, 404 on
    missing store, 403 on unauthenticated.
- **`src/backend/manage_shopping_list.py`** — replace the
  `available_stores` set with `available_store_buckets`:
  ```python
  available_store_buckets = {
      "frequent": [...sorted names],
      "low_freq": [...sorted names],
  }
  ```
  Drop `hidden` entirely. Keep `available_stores` (flat list of
  `frequent + low_freq` names) for backward compat with any consumer
  that doesn't yet handle the bucket shape.
- **`src/backend/create_flask_application.py`** — register the new
  stores blueprint after the existing receipts blueprint.

### Frontend

- **Settings page (`src/frontend/index.html`)** — new card after the
  existing "🏪 Plaid" card titled "🏪 Manage Stores":
  - Filter pills: All / Frequent / Rarely Used / Hidden / Auto.
  - Table rows: name · last purchase (formatted date or "—") · purchase
    count · current bucket badge · action select (`Auto` |
    `Pin Frequent` | `Pin Rarely Used` | `Pin Hidden`).
  - Action select onchange → POST `/api/stores/{id}/visibility`.
  - Refresh table after each save.
- **Store dropdown render helper** — update
  `renderInventoryStoreOptionTags`, `renderShoppingStoreOptionTags`,
  and the receipt filter store option emitter so they:
  1. Read `available_store_buckets` (set on `/shopping-list` fetch).
  2. Emit `<optgroup label="Stores">…</optgroup>` then
     `<optgroup label="Rarely Used">…</optgroup>` when both sets are
     non-empty.
  3. Emit a flat list (no optgroup) when only one bucket is present.
- **Hardcoded defaults** (`Costco`, `Kroger`, `Target`, `India Bazar`)
  go into the `frequent` bucket.

## Data flow

```
[receipt insert / Plaid promote] → unchanged. visibility_override defaults NULL.
                  ↓
[GET /shopping-list] → manage_stores.get_store_buckets() → embeds
                       available_store_buckets in response.
                  ↓
[frontend] populates dropdowns with optgroups.
                  ↓
[user opens Settings → Manage Stores] → GET /api/stores → table render.
                  ↓
[user picks "Pin Hidden"] → POST /api/stores/{id}/visibility → row update →
                            next dropdown fetch reflects change.
```

## Error handling

- **Migration:** PRAGMA-guarded ADD COLUMN; safe under restore-from-old-tar
  (Alembic upgrade head is run on container boot, will add the column to a
  legacy DB without disturbing existing rows).
- **Invalid override value** in POST body: 400 with `{"error": "invalid override"}`.
- **Store id not found:** 404.
- **Unauthenticated:** 403 (existing `require_auth` decorator).
- **Concurrent writes:** last write wins. Single-user-at-a-time pattern;
  not worth optimistic locking.
- **No purchases at all (new install):** auto-classify treats every store
  as `hidden` — but new installs have no stores either, so empty state
  is the correct render.

## Backup / restore safety

- Migration is additive ADD COLUMN with PRAGMA-guarded idempotency. Restoring
  an older `tar.gz` that lacks the column leaves the column to be re-added on
  next container boot (Alembic runs on startup).
- No new files outside `/data/`. No volume renames. Backup script
  (`scripts/backup_database_and_volumes.sh`) needs no changes.
- Smoke gate: after the migration ships, run the existing backup → restore
  flow on dev with the post-migration tar; verify the dropdown still
  renders and the Manage Stores panel works.

## Testing

### Unit (`tests/test_manage_stores.py`)

`classify_store` truth table:

| Override     | Artifact | Last purchase | Count | Expected     |
|--------------|----------|---------------|-------|--------------|
| `NULL`       | False    | 30 days ago   | 2     | `frequent`   |
| `NULL`       | False    | 89 days ago   | 1     | `frequent`   |
| `NULL`       | False    | 91 days ago   | 1     | `low_freq`   |
| `NULL`       | False    | 200 days ago  | 1     | `low_freq`   |
| `NULL`       | False    | 365 days ago  | 1     | `low_freq`   |
| `NULL`       | False    | 366 days ago  | 1     | `hidden`     |
| `NULL`       | False    | 18 months ago | 7     | `hidden`     |
| `NULL`       | False    | none          | 0     | `hidden`     |
| `"frequent"` | False    | 18 months ago | 0     | `frequent`   |
| `"low_freq"` | False    | 30 days ago   | 10    | `low_freq`   |
| `"hidden"`   | False    | 30 days ago   | 10    | `hidden`     |
| `"frequent"` | True     | 30 days ago   | 10    | `hidden`     |

### Integration (`tests/test_manage_stores_endpoint.py`)

- `GET /api/stores` returns 3 buckets shaped as expected.
- `POST /api/stores/{id}/visibility {override: "hidden"}` flips bucket on
  next GET.
- `POST .../visibility {override: null}` reverts to auto.
- 400 on bogus enum.
- 404 on missing id.

### Smoke checklist (post-deploy)

- [ ] Settings → Manage Stores card renders, lists all stores with last-purchase + count.
- [ ] Filter pills work (All / Frequent / Rarely Used / Hidden).
- [ ] Pin a store to Hidden → next dropdown render excludes it.
- [ ] Pin a store to Frequent → appears in top optgroup even if no recent purchase.
- [ ] Pin → Auto reverts cleanly.
- [ ] Existing CC artifacts (Phase 2) still hidden, unaffected by override.
- [ ] Backup → restore on dev → Manage Stores panel still renders.

## YAGNI removed

- **Per-user hide** — global hide chosen up-front; revisit if multiple
  users disagree about what's "frequent".
- **Configurable thresholds** — hardcoded 3 mo / 12 mo / 5 purchases.
  Add a settings exposure only if data drives it.
- **Bulk actions in Manage Stores** — single-row actions for v1.
- **Hidden-store search** — Manage Stores filter pills are enough; no
  separate search box.

## Out of scope

- Auto-merging dupes (Phase 2 covered that).
- Suggested stores promotion (existing `suggested_stores` array stays
  unchanged — it's purchase-driven, naturally excludes rare visits).
- Per-receipt UI for "this was a one-off, don't add to picker" — too
  intrusive at scan time.
