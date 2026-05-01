# Proactive product image backfill — design

**Date:** 2026-04-30
**Status:** Draft, awaiting user review.

## Problem

Kitchen view tiles + shopping-list rows show category emoji fallbacks
(🥬 🥩 🥛 …) for any product without a `ProductSnapshot`. From 3 ft on
a kitchen tablet that's abstract — the user wants real imagery. Today
snapshots only exist for products the user manually photographed
(receipt-item link or `/shopping-list/identify-product-photo` flow).
Every other product is permanently emoji-only.

## Solution overview

Nightly APScheduler job fetches a matching image per qualifying product
and writes a real `ProductSnapshot` row. Frontend untouched — the
kitchen aggregator (`manage_kitchen.get_kitchen_catalog`) already picks
`MAX(snapshot.id)` per product and surfaces `image_url`, so new
auto-fetched snapshots flow through transparently.

Three free providers in fanout order — Wikimedia (no key) → Unsplash
(`UNSPLASH_ACCESS_KEY`) → Pexels (`PEXELS_API_KEY`). First success
wins. Images normalized to 600 px wide JPEG before persistence.

Snapshots are tagged `source_context="auto_fetch"`,
`status="auto"`. Hybrid review model: tile shows the image on next
page-load, AND the existing
`/product-snapshots/review-queue` surfaces them so an admin can
relink/dismiss bad matches after-the-fact via existing tooling.

## Architecture

### Data model

One new column on `Product`:

```python
last_image_fetch_attempt_at = Column(DateTime, nullable=True)
```

NULL = never tried. Used to enforce a 7-day retry cooldown so a
permanently-unmatched product (e.g., made-up brand name) doesn't get
re-queried every night.

`ProductSnapshot` schema is unchanged. Two new string values for
existing string columns:

| Column | New value | Meaning |
|---|---|---|
| `source_context` | `"auto_fetch"` | Image was fetched by the nightly backfill. |
| `status` | `"auto"` | Awaiting passive admin review (visible in tile + review queue). |

Both must be added to `ALLOWED_SOURCE_CONTEXTS` and `ALLOWED_STATUSES`
in `manage_product_snapshots.py` so the existing review-queue + upload
endpoints accept the values.

### Modules

**`src/backend/fetch_product_image.py`** *(new, pure)*:

```python
def fetch_product_image(
    product_name: str,
    category: str | None = None,
    *,
    max_bytes: int = 1_048_576,
    target_width: int = 600,
    timeout: float = 10.0,
) -> bytes | None
```

Returns JPEG bytes (post-downscale, post-recompress) or None. No DB,
no FS — caller handles persistence.

Internal helpers:
- `_query_wikimedia(query, timeout) -> str | None` — returns image URL.
- `_query_unsplash(query, timeout) -> str | None`.
- `_query_pexels(query, timeout) -> str | None`.
- `_download_and_normalize(url, max_bytes, target_width, timeout) -> bytes | None`
  — streams response, rejects non-image Content-Type, rejects > max_bytes,
  Pillow `verify()` integrity check, downscale to target_width via
  `Image.Resampling.LANCZOS`, re-encode JPEG q=82.

Module-level constants:

```python
USER_AGENT = (
    "LocalOCR_Extended/1.0 "
    "(https://github.com/chatwithllm/LocalOCR_Extended; image-backfill)"
)
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
WIKIMEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
UNSPLASH_ENDPOINT = "https://api.unsplash.com/search/photos"
PEXELS_ENDPOINT = "https://api.pexels.com/v1/search"
```

### Provider query specifics

- **Wikimedia**: GET with
  `action=query&format=json&prop=pageimages&piprop=thumbnail&pithumbsize=600&generator=search&gsrsearch=<query>&gsrlimit=1&gsrnamespace=0`.
  User-Agent header is mandatory by Wikimedia API policy.
- **Unsplash**: GET `?query=<q>&per_page=1&orientation=squarish` with
  `Authorization: Client-ID <key>`. Pull `results[0].urls.regular`.
- **Pexels**: GET `?query=<q>&per_page=1&size=small` with
  `Authorization: <key>`. Pull `photos[0].src.medium`.

Query string = `product.display_name or product.name`, suffixed with
`category` when category is meaningful (not `"other"` / `"unknown"`).

**`src/backend/backfill_product_images.py`** *(new, DB layer)*:

```python
RETRY_INTERVAL = timedelta(days=7)

def find_products_needing_images(session, max_products: int = 20) -> list[Product]
def backfill_images_for_products(session, products) -> dict  # {fetched, failed}
```

`find_products_needing_images` constraints:
1. NO existing `ProductSnapshot` rows (`product_id NOT IN (SELECT product_id FROM product_snapshots WHERE product_id IS NOT NULL)`).
2. Referenced by ≥1 `ReceiptItem` OR ≥1 `ShoppingListItem` (don't burn quota on orphan products).
3. `last_image_fetch_attempt_at IS NULL OR < now - 7 days`.
4. ORDER BY `last_image_fetch_attempt_at ASC NULLS FIRST, id ASC`. Limit `max_products`.

`backfill_images_for_products`:
- For each product: build query from `display_name or name`, call
  `fetch_product_image()`.
- If bytes: write to `<root>/YYYY/MM/<timestamp>_<uuid8>.jpg`, INSERT
  `ProductSnapshot(product_id=p.id, source_context="auto_fetch",
  status="auto", image_path=<absolute>, captured_at=now)`.
- Always set `product.last_image_fetch_attempt_at = now`.
- Per-product `session.commit()` so partial failures persist progress.

### Job registration

`src/backend/schedule_daily_recommendations.py` adds:

```python
def _run_image_backfill():
    """Nightly: fetch images for products with no ProductSnapshot."""
    try:
        from src.backend.initialize_database_schema import (
            create_db_engine, create_session_factory,
        )
        from src.backend.backfill_product_images import (
            find_products_needing_images, backfill_images_for_products,
        )
        engine = create_db_engine()
        Session = create_session_factory(engine)
        session = Session()
        try:
            products = find_products_needing_images(session, max_products=50)
            if not products:
                logger.info("Image backfill: nothing to do.")
                return
            stats = backfill_images_for_products(session, products)
            logger.info("Image backfill: fetched=%d failed=%d (cap=50)",
                        stats["fetched"], stats["failed"])
        finally:
            session.close()
    except Exception as exc:
        logger.error("Image backfill failed: %s", exc)
```

Registered:

```python
_scheduler.add_job(
    _run_image_backfill,
    trigger="cron",
    hour=4,
    minute=0,
    id="image_backfill",
    name="Proactive Product Image Backfill",
    misfire_grace_time=3600,
)
```

### Storage

Reuses existing pattern from `manage_product_snapshots.py`:
`<PRODUCT_SNAPSHOTS_DIR or /data/product_snapshots>/YYYY/MM/<ts>_<uuid8>.jpg`.

Lifts the private `_get_snapshot_root()` to a public `get_snapshot_root()`
in `manage_product_snapshots.py` (alias the old name to keep existing
callers happy).

### Configuration

| Env var | Required? | Effect when unset |
|---|---|---|
| `UNSPLASH_ACCESS_KEY` | Optional | Unsplash provider silently skipped. |
| `PEXELS_API_KEY` | Optional | Pexels provider silently skipped. |
| `PRODUCT_SNAPSHOTS_DIR` | Optional | Defaults `/data/product_snapshots` (Docker) or `<repo>/data/product_snapshots` (dev). |

Wikimedia is always tried (no key required).

`README.md` gets a short "Proactive image backfill" subsection
linking to provider signup pages and listing the env vars.

## Data flow

```
[04:00 cron]
   → _run_image_backfill()
      → find_products_needing_images(session, 50)
         constraints: no existing snapshot, has receipt/shopping ref,
                       attempted > 7d ago. ORDER BY attempt ASC NULLS FIRST.
      → backfill_images_for_products(session, products)
         for each product:
           bytes = fetch_product_image(display_name, category)
              Wikimedia → Unsplash (if key) → Pexels (if key)
              Pillow normalize: 600px wide, JPEG q=82, max 1 MB
           if bytes:
              write /data/product_snapshots/YYYY/MM/<ts>_<uuid>.jpg
              INSERT product_snapshot (source_context='auto_fetch',
                                        status='auto', ...)
           UPDATE product SET last_image_fetch_attempt_at = now
           COMMIT (per product)

[next kitchen page-load]
GET /api/kitchen/catalog
   → manage_kitchen.get_kitchen_catalog
      snapshot_subq: MAX(snapshot.id) per product
      tile.image_url = '/product-snapshots/<id>/image'
   → tiles render new images, no frontend change.

[admin review path]
GET /product-snapshots/review-queue
   → existing endpoint surfaces `auto` status
   → admin can: approve (status='linked'), dismiss (status='archived'),
                relink (re-target product_id), upload-replacement.
```

## Error handling

- Wikimedia / Unsplash / Pexels HTTP 5xx / timeout → log warning, fall through.
- Non-image Content-Type or > 1 MB → reject, fall through.
- Pillow decode error → reject, fall through.
- All providers fail → no snapshot row, `last_image_fetch_attempt_at`
  still set so 7-day cooldown applies.
- Job-level uncaught exception → top-level `try/except` in
  `_run_image_backfill` logs and returns; scheduler reschedules tomorrow.
- Per-product `session.commit()` ensures crash mid-run preserves
  successful snapshots already written.

## Backup / restore safety

- Migration `020_product_image_fetch_attempt.py` is additive ADD COLUMN
  with `_column_exists` PRAGMA guard, no-op downgrade. Restoring an old
  tar that lacks the column upgrades cleanly on container boot.
- Image files written under existing backed-up
  `/data/product_snapshots/` volume. No new volumes.
- Job is idempotent: never overwrites existing snapshots; never
  re-fetches a product whose `last_image_fetch_attempt_at` is fresh.

## Testing

### Unit (`tests/test_fetch_product_image.py`)

- `test_wikimedia_first_success` — mock chain returns Wikimedia JSON +
  PNG bytes; assert Unsplash/Pexels never called.
- `test_falls_back_to_unsplash_when_wikimedia_empty` — Wikimedia
  returns empty `pages`; Unsplash succeeds.
- `test_falls_back_to_pexels` — both prior fail.
- `test_returns_none_when_all_fail`.
- `test_skips_unsplash_when_no_key` — `monkeypatch.delenv` then assert
  no call to Unsplash endpoint.
- `test_rejects_non_image_content_type` — `Content-Type: text/html` →
  None.
- `test_rejects_oversize_response` — chunked stream > 1 MB → None.
- `test_downscales_to_target_width` — stub a 2400px PNG, assert
  returned JPEG decoded width == 600.
- `test_user_agent_header_set_for_wikimedia` — outgoing request's
  `User-Agent` contains `"LocalOCR_Extended"`.

### Integration (`tests/test_backfill_product_images.py`)

In-memory SQLite session.

- `test_excludes_products_with_existing_snapshot`.
- `test_excludes_orphan_products` — product with no `ReceiptItem` and
  no `ShoppingListItem`.
- `test_includes_product_referenced_only_by_shopping_list_item`.
- `test_respects_seven_day_retry_window` — 3-day-old attempt excluded;
  8-day-old included.
- `test_max_products_cap_honored`.
- `test_backfill_creates_snapshot_and_marks_attempt` — patch
  `fetch_product_image` to return canned JPEG bytes; assert
  ProductSnapshot row + `last_image_fetch_attempt_at`.
- `test_backfill_marks_attempt_even_when_fetch_fails` — None bytes →
  no snapshot but cooldown updated.
- `test_per_product_commit_survives_partial_failure` — first OK,
  second raises; first snapshot persisted.

### Smoke (post-deploy)

- [ ] `alembic upgrade head` — column exists in `products`.
- [ ] Manual trigger inside container: `from
      src.backend.schedule_daily_recommendations import
      _run_image_backfill; _run_image_backfill()` — log shows
      `fetched=N failed=M`.
- [ ] `/data/product_snapshots/YYYY/MM/` — new `.jpg` files appear.
- [ ] SQL: rows with `source_context='auto_fetch'`.
- [ ] Kitchen view — real images replace emoji on tiles.
- [ ] Re-run job → `nothing to do`.
- [ ] Backup → restore on dev → kitchen still loads, snapshots intact.

## YAGNI removed

- AI image generation (deferred — user opted out for v1).
- Manual "Fetch now" admin button (nightly is enough; cron schedule
  visible in scheduler logs).
- DB-encrypted API keys (env-only for v1; free non-rotating keys).
- Replacing existing user-uploaded snapshots (only fills gaps).
- De-duplication of identical images across products (premature).
- Per-provider rate limiting (the 50/night cap + per-product DB
  commit naturally paces requests well within free quotas).

## Out of scope

- Frontend changes — kitchen tiles already render `image_url`.
- Auto-promotion of `status="auto"` to `"linked"` based on confidence
  (admin still in the loop).
- Cross-product image dedup.
- Search-by-image (reverse lookup).
- Multilingual queries (English Wikimedia only for v1).
