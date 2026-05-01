# Product Image Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nightly APScheduler job that fetches a matching image (Wikimedia → Unsplash → Pexels) for products missing a `ProductSnapshot` and persists it as a real snapshot row, so kitchen tiles and shopping rows display real imagery instead of category-emoji fallbacks.

**Architecture:** Two new pure modules — `fetch_product_image.py` (provider fanout, no DB/FS) and `backfill_product_images.py` (DB query + persist). Cron at 04:00 caps 50 products/run; 7-day retry cooldown via new `Product.last_image_fetch_attempt_at` column. Snapshots tagged `source_context="auto_fetch"`, `status="auto"` so the existing review queue surfaces them for admin oversight.

**Tech Stack:** Python 3.11, SQLAlchemy, Alembic, APScheduler, Pillow, requests. No frontend changes — kitchen tiles already render `image_url` from latest snapshot.

---

## File Structure

**Create:**
- `src/backend/fetch_product_image.py` — pure fanout fetcher (Wikimedia → Unsplash → Pexels). No DB, no FS.
- `src/backend/backfill_product_images.py` — DB layer: query qualifying products + persist downloaded bytes as `ProductSnapshot` rows.
- `alembic/versions/020_product_image_fetch_attempt.py` — additive ADD COLUMN migration.
- `tests/test_fetch_product_image.py` — mocked HTTP unit tests.
- `tests/test_backfill_product_images.py` — in-memory SQLite integration tests.

**Modify:**
- `src/backend/initialize_database_schema.py` — add `Product.last_image_fetch_attempt_at` column.
- `src/backend/manage_product_snapshots.py` — add `"auto_fetch"` to `ALLOWED_SOURCE_CONTEXTS`, `"auto"` to `ALLOWED_STATUSES`. Lift `_get_snapshot_root` → public `get_snapshot_root` (alias old name).
- `src/backend/schedule_daily_recommendations.py` — add `_run_image_backfill()` + cron registration at 04:00.
- `README.md` — short "Proactive image backfill" subsection.

**Test infrastructure (no changes):**
- Tests mirror `tests/test_manage_kitchen.py` fixture pattern (local `tmp_path` SQLite + `Base.metadata.create_all`).

---

## Task 1: Schema column + Alembic migration 020

**Files:**
- Modify: `src/backend/initialize_database_schema.py:Product` (around line 119)
- Create: `alembic/versions/020_product_image_fetch_attempt.py`

- [ ] **Step 1: Add the column to the Product model**

In `src/backend/initialize_database_schema.py`, locate the `Product` class. After the existing `enriched_at` line (around line 119), add:

```python
    last_image_fetch_attempt_at = Column(DateTime, nullable=True)
```

The full block around it should read:

```python
    enrichment_confidence = Column(Float, nullable=True)
    enriched_at = Column(DateTime, nullable=True)
    last_image_fetch_attempt_at = Column(DateTime, nullable=True)
    review_state = Column(String(20), nullable=True, default="pending")
```

- [ ] **Step 2: Create the migration**

Create `alembic/versions/020_product_image_fetch_attempt.py`:

```python
"""product_image_fetch_attempt: track last attempt at auto image backfill.

Revision ID: 020_product_image_fetch_attempt
Revises: 019_trusted_device_allowed_pages
Create Date: 2026-04-30

Adds a nullable DateTime column to ``products`` so the nightly image
backfill job can enforce a 7-day retry cooldown and not re-query
permanently-unmatched products every night.

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching
the pattern used by 017/018/019.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_product_image_fetch_attempt"
down_revision: Union[str, None] = "019_trusted_device_allowed_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_products"))

    if not _column_exists(conn, "products", "last_image_fetch_attempt_at"):
        op.add_column(
            "products",
            sa.Column("last_image_fetch_attempt_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    # No-op: matches 017/018/019 — drop-column on SQLite is invasive and
    # the column is harmless when left in place.
    pass
```

- [ ] **Step 3: Run the migration**

```bash
docker compose exec -T -w /app backend alembic upgrade head
```

Expected: alembic logs `Running upgrade 019_trusted_device_allowed_pages -> 020_product_image_fetch_attempt`.

- [ ] **Step 4: Verify column exists**

```bash
docker compose exec -T backend sqlite3 /data/db/extended.db ".schema products" | grep last_image_fetch_attempt_at
```

Expected output: a line containing `last_image_fetch_attempt_at DATETIME`.

(If the DB path differs, find it via `docker compose exec backend env | grep DATABASE_URL`.)

- [ ] **Step 5: Commit**

```bash
git add src/backend/initialize_database_schema.py \
        alembic/versions/020_product_image_fetch_attempt.py
git commit -m "feat(images): add Product.last_image_fetch_attempt_at column + migration 020"
```

---

## Task 2: `fetch_product_image` module + unit tests

**Files:**
- Create: `src/backend/fetch_product_image.py`
- Create: `tests/test_fetch_product_image.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_product_image.py`:

```python
"""Unit tests for the fetch_product_image provider fanout module.

All HTTP traffic is mocked. We test:
  - Wikimedia first wins.
  - Fallback to Unsplash when Wikimedia returns empty.
  - Fallback to Pexels when both prior fail.
  - Returns None when every provider fails.
  - Provider silently skipped when its API key env var is unset.
  - Content-Type validation (rejects non-images).
  - Size cap (rejects > max_bytes).
  - Pillow downscale to target_width.
  - Required User-Agent header on outbound calls.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _make_png_bytes(width: int = 800, height: int = 800, color=(180, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _mock_streamed_response(*, content_type: str, body: bytes, status_code: int = 200):
    """Build a MagicMock that mimics requests.get(..., stream=True) for our reader."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()

    def _iter_content(chunk_size=16384):
        idx = 0
        while idx < len(body):
            yield body[idx : idx + chunk_size]
            idx += chunk_size

    resp.iter_content = _iter_content
    return resp


def _mock_json_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


@pytest.fixture
def png_bytes() -> bytes:
    return _make_png_bytes()


def test_wikimedia_first_success(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    wikimedia_json = {
        "query": {"pages": {"123": {"thumbnail": {"source": "https://up.wikimedia.org/foo.png"}}}}
    }
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "wikipedia.org" in url:
            return _mock_json_response(wikimedia_json)
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    out = mod.fetch_product_image("Strawberries")
    assert isinstance(out, bytes) and len(out) > 0
    # Verify it's JPEG (post-recompress).
    assert out[:3] == b"\xff\xd8\xff"
    # Unsplash + Pexels must NOT have been called.
    assert all("unsplash.com" not in c and "pexels.com" not in c for c in calls)


def test_falls_back_to_unsplash_when_wikimedia_empty(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "test-key")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": [{"urls": {"regular": "https://images.unsplash.com/x.jpg"}}]})
        if "images.unsplash.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Tomato")
    assert isinstance(out, bytes) and out[:3] == b"\xff\xd8\xff"


def test_falls_back_to_pexels(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": []})
        if "api.pexels.com" in url:
            return _mock_json_response({"photos": [{"src": {"medium": "https://images.pexels.com/y.jpg"}}]})
        if "images.pexels.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Mirchi")
    assert isinstance(out, bytes)


def test_returns_none_when_all_fail(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": []})
        if "api.pexels.com" in url:
            return _mock_json_response({"photos": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Nonexistent Product") is None


def test_skips_unsplash_when_no_key(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    seen_urls = []

    def fake_get(url, **kwargs):
        seen_urls.append(url)
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        if "api.pexels.com" in url:
            return _mock_json_response({"photos": [{"src": {"medium": "https://images.pexels.com/z.jpg"}}]})
        if "images.pexels.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    mod.fetch_product_image("Eggs")
    # Unsplash endpoint must never have been hit.
    assert all("api.unsplash.com" not in u for u in seen_urls)


def test_rejects_non_image_content_type(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/spam.html"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="text/html", body=b"<html>not an image</html>")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Bread") is None


def test_rejects_oversize_response(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    big_body = b"\x00" * (2 * 1024 * 1024)  # 2 MB

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/big.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=big_body)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Cheese") is None


def test_downscales_to_target_width(monkeypatch):
    from src.backend import fetch_product_image as mod

    big_png = _make_png_bytes(width=2400, height=2400)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/big.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=big_png)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    out = mod.fetch_product_image("Tomatoes", target_width=600)
    assert out is not None
    img = Image.open(io.BytesIO(out))
    assert img.width == 600


def test_user_agent_header_set_for_wikimedia(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    captured_headers = []

    def fake_get(url, **kwargs):
        captured_headers.append(kwargs.get("headers", {}))
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/x.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    mod.fetch_product_image("Onions")
    # Both calls (search + image download) carry our User-Agent.
    assert all("LocalOCR_Extended" in (h.get("User-Agent") or "") for h in captured_headers)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
docker cp tests/test_fetch_product_image.py localocr-extended-backend:/app/tests/test_fetch_product_image.py
docker compose exec -T -w /app backend python -m pytest tests/test_fetch_product_image.py -v
```

Expected: ImportError (`fetch_product_image` does not exist).

- [ ] **Step 3: Create the module**

Create `src/backend/fetch_product_image.py`:

```python
"""Provider-fanout image fetcher for proactive product image backfill.

Tries free image providers in order: Wikimedia (no key), Unsplash
(``UNSPLASH_ACCESS_KEY`` env var), Pexels (``PEXELS_API_KEY`` env var).
First success wins. Returns post-normalized JPEG bytes or None.

Free key signups:
  - Unsplash: https://unsplash.com/oauth/applications  (50 req/hr demo, 5000/hr prod)
  - Pexels:   https://www.pexels.com/api/              (200 req/hr free)

Wikimedia requires the courtesy User-Agent below per their API policy:
https://www.mediawiki.org/wiki/API:Etiquette
"""
from __future__ import annotations

import io
import logging
import os

import requests
from PIL import Image


logger = logging.getLogger(__name__)

USER_AGENT = (
    "LocalOCR_Extended/1.0 "
    "(https://github.com/chatwithllm/LocalOCR_Extended; image-backfill)"
)
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
WIKIMEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
UNSPLASH_ENDPOINT = "https://api.unsplash.com/search/photos"
PEXELS_ENDPOINT = "https://api.pexels.com/v1/search"


def _query_wikimedia(query: str, timeout: float) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "piprop": "thumbnail",
        "pithumbsize": 600,
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": 1,
        "gsrnamespace": 0,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(WIKIMEDIA_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            thumb = (page.get("thumbnail") or {}).get("source")
            if thumb:
                return thumb
    except Exception as exc:
        logger.warning("Wikimedia query failed for %r: %s", query, exc)
    return None


def _query_unsplash(query: str, timeout: float) -> str | None:
    key = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        return None
    headers = {
        "Authorization": f"Client-ID {key}",
        "Accept-Version": "v1",
        "User-Agent": USER_AGENT,
    }
    params = {"query": query, "per_page": 1, "orientation": "squarish"}
    try:
        resp = requests.get(UNSPLASH_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if results:
            return ((results[0].get("urls") or {}).get("regular")
                    or (results[0].get("urls") or {}).get("small"))
    except Exception as exc:
        logger.warning("Unsplash query failed for %r: %s", query, exc)
    return None


def _query_pexels(query: str, timeout: float) -> str | None:
    key = (os.getenv("PEXELS_API_KEY") or "").strip()
    if not key:
        return None
    headers = {"Authorization": key, "User-Agent": USER_AGENT}
    params = {"query": query, "per_page": 1, "size": "small"}
    try:
        resp = requests.get(PEXELS_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        if photos:
            return ((photos[0].get("src") or {}).get("medium")
                    or (photos[0].get("src") or {}).get("small"))
    except Exception as exc:
        logger.warning("Pexels query failed for %r: %s", query, exc)
    return None


def _download_and_normalize(
    image_url: str, max_bytes: int, target_width: int, timeout: float
) -> bytes | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(image_url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct not in ALLOWED_CONTENT_TYPES:
            logger.info("rejecting %s: content-type %r", image_url, ct)
            return None
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=16384):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > max_bytes:
                logger.info("rejecting %s: exceeded max_bytes=%d", image_url, max_bytes)
                return None
        raw = bytes(buf)
        # Pillow integrity check.
        Image.open(io.BytesIO(raw)).verify()
        # Reopen for actual processing (verify() exhausts the stream).
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        if img.width > target_width:
            new_h = int(img.height * (target_width / img.width))
            img = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("download/normalize failed for %s: %s", image_url, exc)
        return None


def fetch_product_image(
    product_name: str,
    category: str | None = None,
    *,
    max_bytes: int = 1_048_576,
    target_width: int = 600,
    timeout: float = 10.0,
) -> bytes | None:
    """Return JPEG bytes for the best-matching image, or None if all providers fail.

    Pure function — no DB, no FS. Caller persists the bytes wherever it likes.
    """
    name = (product_name or "").strip()
    if not name:
        return None
    query = name
    if category:
        cat = category.strip()
        if cat and cat.lower() not in {"other", "unknown"}:
            query = f"{name} {cat}"

    for provider in (_query_wikimedia, _query_unsplash, _query_pexels):
        url = provider(query, timeout)
        if not url:
            continue
        data = _download_and_normalize(url, max_bytes, target_width, timeout)
        if data:
            return data
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker cp src/backend/fetch_product_image.py localocr-extended-backend:/app/src/backend/fetch_product_image.py
docker compose exec -T -w /app backend python -m pytest tests/test_fetch_product_image.py -v
```

Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/backend/fetch_product_image.py tests/test_fetch_product_image.py
git commit -m "feat(images): fetch_product_image provider fanout (Wikimedia/Unsplash/Pexels)"
```

---

## Task 3: `backfill_product_images` module + integration tests

**Files:**
- Create: `src/backend/backfill_product_images.py`
- Create: `tests/test_backfill_product_images.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill_product_images.py`:

```python
"""Integration tests for the nightly product-image backfill.

In-memory SQLite session (mirrors tests/test_manage_kitchen.py pattern).
``fetch_product_image`` is patched to return canned JPEG bytes so we
test the DB-layer logic in isolation from network providers.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from PIL import Image

from src.backend.initialize_database_schema import (
    Base, Product, ProductSnapshot, Purchase, ReceiptItem,
    ShoppingListItem, ShoppingSession, Store,
    create_db_engine, create_session_factory,
)


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (600, 600), color=(50, 100, 150))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "backfill.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def snapshots_dir(tmp_path, monkeypatch):
    d = tmp_path / "snapshots"
    d.mkdir()
    monkeypatch.setenv("PRODUCT_SNAPSHOTS_DIR", str(d))
    return d


def _add_product(session, name, category="Produce"):
    p = Product(name=name, category=category)
    session.add(p)
    session.flush()
    return p


def _add_receipt_ref(session, product):
    store = Store(name="Test Store")
    session.add(store); session.flush()
    pur = Purchase(store_id=store.id, total_amount=1.0, date=datetime.now(timezone.utc))
    session.add(pur); session.flush()
    ri = ReceiptItem(purchase_id=pur.id, product_id=product.id, quantity=1, unit_price=1.0)
    session.add(ri); session.flush()


def _add_shopping_ref(session, product):
    sess = ShoppingSession(name="trip", status="active")
    session.add(sess); session.flush()
    item = ShoppingListItem(
        product_id=product.id, name=product.name, category=product.category,
        quantity=1, status="open", shopping_session_id=sess.id,
    )
    session.add(item); session.flush()


def test_excludes_products_with_existing_snapshot(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Apples")
    _add_receipt_ref(db_session, p)
    db_session.add(ProductSnapshot(product_id=p.id, status="linked", image_path="/x.jpg"))
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id not in [r.id for r in out]


def test_excludes_orphan_products(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Lonely Item")  # no receipt, no shopping ref
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id not in [r.id for r in out]


def test_includes_product_referenced_only_by_shopping_list_item(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Bread")
    _add_shopping_ref(db_session, p)
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id in [r.id for r in out]


def test_respects_seven_day_retry_window(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Cheese")
    _add_receipt_ref(db_session, p)
    p.last_image_fetch_attempt_at = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.commit()
    assert p.id not in [r.id for r in find_products_needing_images(db_session)]
    p.last_image_fetch_attempt_at = datetime.now(timezone.utc) - timedelta(days=8)
    db_session.commit()
    assert p.id in [r.id for r in find_products_needing_images(db_session)]


def test_max_products_cap_honored(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    for i in range(30):
        p = _add_product(db_session, f"Item {i}")
        _add_receipt_ref(db_session, p)
    db_session.commit()
    out = find_products_needing_images(db_session, max_products=10)
    assert len(out) == 10


def test_backfill_creates_snapshot_and_marks_attempt(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p = _add_product(db_session, "Eggs")
    _add_receipt_ref(db_session, p)
    db_session.commit()

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image",
               return_value=_jpeg_bytes()):
        stats = backfill_images_for_products(db_session, products)

    assert stats == {"fetched": 1, "failed": 0}
    snaps = db_session.query(ProductSnapshot).filter_by(product_id=p.id).all()
    assert len(snaps) == 1
    assert snaps[0].source_context == "auto_fetch"
    assert snaps[0].status == "auto"
    # File on disk under our tmp snapshots dir.
    from pathlib import Path
    assert Path(snaps[0].image_path).exists()
    assert str(snapshots_dir) in snaps[0].image_path
    db_session.refresh(p)
    assert p.last_image_fetch_attempt_at is not None


def test_backfill_marks_attempt_even_when_fetch_fails(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p = _add_product(db_session, "Mystery")
    _add_receipt_ref(db_session, p)
    db_session.commit()

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image",
               return_value=None):
        stats = backfill_images_for_products(db_session, products)

    assert stats == {"fetched": 0, "failed": 1}
    assert db_session.query(ProductSnapshot).filter_by(product_id=p.id).count() == 0
    db_session.refresh(p)
    assert p.last_image_fetch_attempt_at is not None


def test_per_product_commit_survives_partial_failure(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p1 = _add_product(db_session, "First")
    p2 = _add_product(db_session, "Second")
    for p in (p1, p2):
        _add_receipt_ref(db_session, p)
    db_session.commit()

    call_count = {"n": 0}
    def _fake(name, *a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _jpeg_bytes()
        raise RuntimeError("simulated provider crash")

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image", side_effect=_fake):
        stats = backfill_images_for_products(db_session, products)

    # First product persisted; second's failure was caught and counted.
    assert stats["fetched"] == 1
    assert stats["failed"] == 1
    snaps = db_session.query(ProductSnapshot).all()
    assert len(snaps) == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
docker cp tests/test_backfill_product_images.py localocr-extended-backend:/app/tests/test_backfill_product_images.py
docker compose exec -T -w /app backend python -m pytest tests/test_backfill_product_images.py -v
```

Expected: ImportError (`backfill_product_images` does not exist).

- [ ] **Step 3: Lift `_get_snapshot_root` to public name**

In `src/backend/manage_product_snapshots.py`, locate the existing `_get_snapshot_root` function (line 41). Add a public alias right after the function body:

```python
def _get_snapshot_root() -> Path:
    configured = os.getenv("PRODUCT_SNAPSHOTS_DIR")
    if configured:
        return Path(configured)
    # ... existing body unchanged ...


# Public alias — see backfill_product_images.py and other future callers.
get_snapshot_root = _get_snapshot_root
```

- [ ] **Step 4: Add `auto_fetch` and `auto` to allowed sets**

In the same file (`manage_product_snapshots.py:31` and line 38), update:

```python
ALLOWED_SOURCE_CONTEXTS = {
    "before_purchase",
    "during_purchase",
    "after_purchase",
    "receipt_backfill",
    "manual",
    "auto_fetch",
}
ALLOWED_STATUSES = {"unreviewed", "linked", "needs_review", "archived", "auto"}
```

- [ ] **Step 5: Create the backfill module**

Create `src/backend/backfill_product_images.py`:

```python
"""Nightly DB-layer backfill: download images for products with no
ProductSnapshot and persist as new snapshot rows tagged ``auto_fetch``.

Per-product commit so partial failures preserve previous successes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import not_

from src.backend.fetch_product_image import fetch_product_image
from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, ReceiptItem, ShoppingListItem,
)
from src.backend.manage_product_snapshots import get_snapshot_root


logger = logging.getLogger(__name__)

RETRY_INTERVAL = timedelta(days=7)


def find_products_needing_images(session, max_products: int = 20) -> list[Product]:
    """Products with NO snapshot, referenced by receipt or shopping list,
    not attempted in the last 7 days. Ordered by oldest-attempt-first."""
    cutoff = datetime.now(timezone.utc) - RETRY_INTERVAL

    has_snapshot_subq = (
        session.query(ProductSnapshot.product_id)
        .filter(ProductSnapshot.product_id.isnot(None))
        .distinct()
        .subquery()
    )
    receipts_subq = (
        session.query(ReceiptItem.product_id)
        .filter(ReceiptItem.product_id.isnot(None))
        .distinct()
        .subquery()
    )
    shopping_subq = (
        session.query(ShoppingListItem.product_id)
        .filter(ShoppingListItem.product_id.isnot(None))
        .distinct()
        .subquery()
    )

    query = (
        session.query(Product)
        .filter(not_(Product.id.in_(session.query(has_snapshot_subq.c.product_id))))
        .filter(
            Product.id.in_(session.query(receipts_subq.c.product_id))
            | Product.id.in_(session.query(shopping_subq.c.product_id))
        )
        .filter(
            (Product.last_image_fetch_attempt_at.is_(None))
            | (Product.last_image_fetch_attempt_at < cutoff)
        )
        .order_by(Product.last_image_fetch_attempt_at.asc().nullsfirst(),
                  Product.id.asc())
        .limit(max_products)
    )
    return query.all()


def backfill_images_for_products(session, products) -> dict:
    """For each product: fetch image bytes, persist as ProductSnapshot row,
    update last_image_fetch_attempt_at. Per-product commit."""
    fetched = 0
    failed = 0
    for product in products:
        query_name = (product.display_name or product.name or "").strip()
        if not query_name:
            product.last_image_fetch_attempt_at = datetime.now(timezone.utc)
            session.commit()
            failed += 1
            continue
        try:
            data = fetch_product_image(query_name, product.category)
        except Exception as exc:
            logger.exception("fetch_product_image raised for %s: %s", product.id, exc)
            data = None

        if data:
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{uuid4().hex[:8]}.jpg"
            save_dir = get_snapshot_root() / year_month
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename
            save_path.write_bytes(data)

            session.add(ProductSnapshot(
                product_id=product.id,
                source_context="auto_fetch",
                status="auto",
                image_path=str(save_path),
                captured_at=now,
            ))
            fetched += 1
        else:
            failed += 1

        product.last_image_fetch_attempt_at = datetime.now(timezone.utc)
        session.commit()
    return {"fetched": fetched, "failed": failed}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker cp src/backend/backfill_product_images.py localocr-extended-backend:/app/src/backend/backfill_product_images.py
docker cp src/backend/manage_product_snapshots.py localocr-extended-backend:/app/src/backend/manage_product_snapshots.py
docker compose exec -T -w /app backend python -m pytest tests/test_backfill_product_images.py tests/test_fetch_product_image.py -v
```

Expected: 8 backfill tests + 9 fetch tests = 17 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/backend/backfill_product_images.py \
        src/backend/manage_product_snapshots.py \
        tests/test_backfill_product_images.py
git commit -m "feat(images): backfill_product_images module + lift snapshot root + extend allowed sets"
```

---

## Task 4: Wire scheduler

**Files:**
- Modify: `src/backend/schedule_daily_recommendations.py`

- [ ] **Step 1: Read the existing scheduler init**

Run `grep -n "add_job\|def push_daily_recommendations\|def _run_" src/backend/schedule_daily_recommendations.py | head -10` and confirm the existing pattern.

- [ ] **Step 2: Add the new job function**

In `src/backend/schedule_daily_recommendations.py`, near the other `_run_*` job functions (search for `def _run_plaid_sync` or similar — pick a spot consistent with neighbors), add:

```python
def _run_image_backfill():
    """Nightly: fetch images for products missing a ProductSnapshot."""
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
            logger.info(
                "Image backfill: fetched=%d failed=%d (cap=50)",
                stats["fetched"], stats["failed"],
            )
        finally:
            session.close()
    except Exception as exc:
        logger.error("Image backfill failed: %s", exc)
```

- [ ] **Step 3: Register the cron job**

Find `start_recommendation_scheduler()` (or whichever function calls `_scheduler.add_job(...)`). After the existing `_run_plaid_sync` registration (or the last `add_job` call before `_scheduler.start()`), add:

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

- [ ] **Step 4: Update scheduler-startup log message**

Find the `logger.info(...)` line that lists the registered jobs (search for `"All scheduler jobs registered"` or similar). Append `image_backfill@04:00` to the list. If the message format is concise and not enumerable, this step is a no-op — confirm by reading the log statement.

- [ ] **Step 5: Smoke the manual trigger**

```bash
docker cp src/backend/schedule_daily_recommendations.py localocr-extended-backend:/app/src/backend/schedule_daily_recommendations.py
docker compose restart backend
sleep 4
docker compose exec -T backend python -c "from src.backend.schedule_daily_recommendations import _run_image_backfill; _run_image_backfill()"
```

Expected output (one of):
- `Image backfill: nothing to do.` — fresh DB, no qualifying products, OR
- `Image backfill: fetched=N failed=M (cap=50)` — products processed.

If neither shows, check `docker compose logs backend | tail -20` for traceback.

- [ ] **Step 6: Verify a snapshot was created (if any fetch succeeded)**

```bash
docker compose exec -T backend sqlite3 /data/db/extended.db \
  "SELECT id, product_id, source_context, status FROM product_snapshots WHERE source_context='auto_fetch' LIMIT 5;"
```

If `Wikimedia` returned nothing for every queried product, this will be empty — that's acceptable. The `last_image_fetch_attempt_at` column should be set for the queried products either way:

```bash
docker compose exec -T backend sqlite3 /data/db/extended.db \
  "SELECT id, name, last_image_fetch_attempt_at FROM products WHERE last_image_fetch_attempt_at IS NOT NULL LIMIT 5;"
```

- [ ] **Step 7: Commit**

```bash
git add src/backend/schedule_daily_recommendations.py
git commit -m "feat(images): nightly 04:00 cron triggers image backfill (cap=50)"
```

---

## Task 5: README + final smoke + push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the README subsection**

Open `README.md`. Find a sensible spot (likely near "Optional integrations" or end of the deployment section — read the file structure first via `head -80 README.md` and `grep -n "^## " README.md`). Append:

```markdown
## Proactive image backfill

A nightly job (04:00) fetches a matching image for any `Product` that
has no `ProductSnapshot` yet, so kitchen tiles + shopping rows show
real imagery instead of category-emoji fallbacks.

Providers (tried in order, first success wins):
1. Wikimedia (always tried, no API key required, requires courtesy User-Agent)
2. Unsplash — set `UNSPLASH_ACCESS_KEY` to enable
   (signup: https://unsplash.com/oauth/applications)
3. Pexels — set `PEXELS_API_KEY` to enable
   (signup: https://www.pexels.com/api/)

The job processes up to 50 products per run, with a 7-day retry
cooldown for products no provider could match. Auto-fetched
snapshots are tagged `source_context="auto_fetch"`, `status="auto"`
so they appear immediately on tiles AND surface in the existing
`/product-snapshots/review-queue` for admin oversight.

Manual trigger (one-off):
\`\`\`bash
docker compose exec backend python -c \\
  "from src.backend.schedule_daily_recommendations import _run_image_backfill; _run_image_backfill()"
\`\`\`
```

(Note the escaped backticks if you copy-paste — render plain triple-backticks in the actual file.)

- [ ] **Step 2: Run the full new test suite once more**

```bash
docker compose exec -T -w /app backend python -m pytest \
  tests/test_fetch_product_image.py \
  tests/test_backfill_product_images.py \
  tests/test_manage_kitchen.py \
  tests/test_manage_kitchen_endpoint.py \
  tests/test_manage_shopping_list_status.py \
  -v
```

Expected: all green (9 + 8 + 38 + 1 + 11 = 67 tests).

- [ ] **Step 3: Visual smoke**

Open the kitchen view in the browser. Products that had only emoji fallbacks before — and that the backfill matched against Wikimedia/etc — now render real images.

(If no provider matched any product, this step will look unchanged. Set `UNSPLASH_ACCESS_KEY` or `PEXELS_API_KEY` and re-run the manual trigger to broaden coverage.)

- [ ] **Step 4: Backup-restore safety check (post-deploy gate)**

Per the project memory rule: schema changes must survive backup→restore round-trips. After this lands in prod:

```bash
ssh udimmich "cd /opt/extended/LocalOCR_Extended && bash scripts/backup_database_and_volumes.sh"
# (later) restore to dev with the new tarball
# verify alembic upgrade head still applies cleanly and column persists
```

- [ ] **Step 5: Commit + push**

```bash
git add README.md
git commit -m "docs(images): README subsection for proactive image backfill"
git push origin main
```

---

## Self-Review checklist

**Spec coverage:**
- "Wikimedia → Unsplash → Pexels fanout, free providers only" → Task 2 ✓
- "Pillow normalize 600px JPEG, max 1 MB raw" → Task 2 ✓
- "Find products with no snapshot, ref'd by receipt/shopping, 7-day cooldown" → Task 3 (`find_products_needing_images`) ✓
- "Per-product commit on partial failure" → Task 3 (`backfill_images_for_products`) ✓
- "New `Product.last_image_fetch_attempt_at` column + migration 020" → Task 1 ✓
- "Nightly APScheduler 04:00, cap 50" → Task 4 ✓
- "auto_fetch / auto values added to allowed sets" → Task 3 step 4 ✓
- "Lift `_get_snapshot_root` to public alias" → Task 3 step 3 ✓
- "Hybrid review: snapshots show in tiles AND review queue" → covered by tagging in Task 3 (review-queue endpoint pre-exists, no new code needed) ✓
- "User-Agent header for Wikimedia" → Task 2 (constants + `_query_wikimedia`) ✓
- "Backup/restore safe: PRAGMA-guarded ADD COLUMN, no-op downgrade" → Task 1 step 2 ✓
- "Tests: 9 fetch + 8 backfill" → Tasks 2, 3 ✓
- "README subsection with env vars + signup URLs + manual trigger" → Task 5 step 1 ✓

**No placeholders.** Every step has full code or a concrete command. The README step uses escaped backticks intentionally (markdown-in-markdown).

**Type consistency.** Function/symbol names: `fetch_product_image`, `_query_wikimedia`, `_query_unsplash`, `_query_pexels`, `_download_and_normalize`, `find_products_needing_images`, `backfill_images_for_products`, `_run_image_backfill`, `RETRY_INTERVAL`, `USER_AGENT`, `ALLOWED_CONTENT_TYPES`. Constants `WIKIMEDIA_ENDPOINT` / `UNSPLASH_ENDPOINT` / `PEXELS_ENDPOINT`. Column name `last_image_fetch_attempt_at` consistent across model, migration, query, test fixtures. Snapshot tagging strings `"auto_fetch"` / `"auto"` consistent across tests, backfill, allowed sets.
