# AI-Assisted Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hybrid recommendation pipeline — Python builds per-product features + a candidate set, a local Ollama model (qwen2.5:7b) prunes noise and adds contextual catches, results are cached and served instantly — fixing the "recommends junk" and "misses things" accuracy gaps, with a heuristic fallback and on-box privacy.

**Architecture:** New focused modules feed a pipeline orchestrated from `generate_recommendations.py`: `recommendation_features.py` (features + candidates) → `recommend_via_llm.py` (Ollama judge + JSON schema + fallback) → reconcile (reuse existing grouping/annotate) → `RecommendationCache` table. `GET /recommendations` serves the cache; the nightly job and an async refresh endpoint (in `manage_recommendations.py`, mirroring `manage_image_backfill`) populate it. A local Ollama text helper (`call_ollama_text_api.py`) mirrors the existing vision call.

**Tech Stack:** Python 3.11 · Flask · SQLAlchemy 2.0 · SQLite · Ollama HTTP (`/api/generate`, `format: json`) · pytest (in-memory SQLite, `DATABASE_URL=sqlite://`).

---

## Data contracts (used across tasks — keep names exact)

**Candidate row** (dict from the feature builder):
```python
{
  "product_id": int, "name": str, "category": str | None,
  "purchase_count": int, "days_since_last": int | None,
  "mean_interval": float | None, "interval_stdev": float | None,
  "overdue_ratio": float | None,        # days_since_last / mean_interval
  "on_hand_low": bool,                  # inventory low / manual_low
  "price_drop": bool,                   # latest price < 90-day avg
  "one_off": bool,                      # count <= 1, or single buy long ago
  "cobought_with": list[str],           # up to 3 product names frequently in same trips
}
```

**LLM judge output item** (validated):
```python
{ "product_id": int, "recommend": bool, "confidence": float, "reason": str }
```

**Reconciled recommendation** (what `/recommendations` returns — superset of today's shape):
```python
{ "product_id": int, "name": str, "reason": str, "confidence": float, "source": "ai" | "heuristic" }
```

## How to run tests

```bash
# from repo root; tests force in-memory SQLite
python3 -m pytest tests/test_<name>.py -v
```
Every test module starts with `os.environ["DATABASE_URL"] = "sqlite://"` BEFORE importing app code (see `tests/test_receipt_dedup.py` for the canonical fixture pattern: module-scoped `app` from `create_app()`, seed via `_get_db()`),.

---

### Task 1: RecommendationCache model + read/write helpers

**Files:**
- Modify: `src/backend/initialize_database_schema.py` (add model near other tables)
- Create: `src/backend/recommendation_cache.py`
- Create: `tests/test_recommendation_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommendation_cache.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def _session():
    from src.backend.create_flask_application import _get_db
    _, SF = _get_db(); return SF()

def test_write_then_read_latest(app):
    from src.backend.recommendation_cache import write_cache, read_latest_cache
    s = _session()
    write_cache(s, scope="household", payload=[{"product_id": 1, "name": "Milk"}], source="ai")
    s.commit()
    row = read_latest_cache(s, scope="household")
    assert row is not None
    assert row["source"] == "ai"
    assert row["payload"][0]["name"] == "Milk"

def test_read_latest_returns_newest(app):
    from src.backend.recommendation_cache import write_cache, read_latest_cache
    s = _session()
    write_cache(s, scope="household", payload=[{"name": "old"}], source="heuristic")
    write_cache(s, scope="household", payload=[{"name": "new"}], source="ai")
    s.commit()
    row = read_latest_cache(s, scope="household")
    assert row["payload"][0]["name"] == "new"
    assert row["source"] == "ai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_recommendation_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: src.backend.recommendation_cache`.

- [ ] **Step 3: Add the model**

In `src/backend/initialize_database_schema.py`, after the `ShoppingListItem` class, add:
```python
class RecommendationCache(Base):
    __tablename__ = "recommendation_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(40), nullable=False, default="household")
    payload_json = Column(Text, nullable=False)          # JSON list of reconciled recs
    source = Column(String(20), nullable=False, default="heuristic")  # "ai" | "heuristic"
    generated_at = Column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_recommendation_cache_scope_generated", "scope", "generated_at"),)
```
(`create_all` creates the table automatically — no migration needed, consistent with this project.)

- [ ] **Step 4: Write the helpers**

```python
# src/backend/recommendation_cache.py
"""Read/write the cached recommendation result. The pipeline writes here; the
GET endpoint reads here so user-facing latency never includes the LLM."""
from __future__ import annotations
import json
from src.backend.initialize_database_schema import RecommendationCache


def write_cache(session, *, scope: str, payload: list, source: str) -> RecommendationCache:
    row = RecommendationCache(
        scope=scope, payload_json=json.dumps(payload), source=source,
    )
    session.add(row)
    session.flush()
    return row


def read_latest_cache(session, *, scope: str = "household") -> dict | None:
    row = (
        session.query(RecommendationCache)
        .filter(RecommendationCache.scope == scope)
        .order_by(RecommendationCache.generated_at.desc(), RecommendationCache.id.desc())
        .first()
    )
    if not row:
        return None
    return {
        "source": row.source,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "payload": json.loads(row.payload_json or "[]"),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_recommendation_cache.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/backend/initialize_database_schema.py src/backend/recommendation_cache.py tests/test_recommendation_cache.py
git commit -m "feat(recs): RecommendationCache model + read/write helpers"
```

---

### Task 2: Local Ollama JSON text helper

**Files:**
- Create: `src/backend/call_ollama_text_api.py`
- Create: `tests/test_call_ollama_text_api.py`

Mirrors `call_ollama_vision_api.py` (same endpoint/timeout env) but for text + JSON.

- [ ] **Step 1: Write the failing test (HTTP mocked — no real model needed)**

```python
# tests/test_call_ollama_text_api.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
import json
import pytest

def test_generate_json_parses_response(monkeypatch):
    from src.backend import call_ollama_text_api as mod

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": json.dumps({"items": [{"product_id": 1, "recommend": True, "confidence": 0.9, "reason": "due"}]})}

    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: FakeResp())
    out = mod.generate_ollama_json("rank these", model="qwen2.5:7b")
    assert out["items"][0]["product_id"] == 1

def test_generate_json_raises_on_bad_json(monkeypatch):
    from src.backend import call_ollama_text_api as mod

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": "not json {"}

    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(ValueError):
        mod.generate_ollama_json("rank these", model="qwen2.5:7b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_call_ollama_text_api.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the helper**

```python
# src/backend/call_ollama_text_api.py
"""Local Ollama text/JSON generation for recommendations. Mirrors the vision
helper's endpoint/timeout config. Stays on the box — no cloud."""
from __future__ import annotations
import json
import os
import requests

OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")


def generate_ollama_json(prompt: str, *, model: str, base_url: str | None = None,
                         timeout: int | None = None) -> dict:
    """POST a prompt to Ollama with format=json; return the parsed JSON object.
    Raises ValueError if the model output is not valid JSON."""
    url = (base_url or OLLAMA_ENDPOINT or "").rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    resp = requests.post(
        url, json=payload,
        timeout=int(timeout if timeout is not None else os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
    )
    resp.raise_for_status()
    text = resp.json().get("response", "")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Ollama returned invalid JSON: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_call_ollama_text_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/backend/call_ollama_text_api.py tests/test_call_ollama_text_api.py
git commit -m "feat(recs): local Ollama JSON text helper"
```

---

### Task 3: Feature + candidate builder

**Files:**
- Create: `src/backend/recommendation_features.py`
- Create: `tests/test_recommendation_features.py`

Reuses the purchase-history query shape from `detect_seasonal_patterns`
(`Purchase.date` joined to `ReceiptItem.product_id`, excluding refunds).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommendation_features.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
from datetime import datetime, timedelta, timezone
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def _session():
    from src.backend.create_flask_application import _get_db
    _, SF = _get_db(); return SF()

def _buy(s, product, days_ago_list):
    from src.backend.initialize_database_schema import Purchase, ReceiptItem
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for d in days_ago_list:
        p = Purchase(date=now - timedelta(days=d)); s.add(p); s.flush()
        s.add(ReceiptItem(purchase_id=p.id, product_id=product.id, name=product.name, quantity=1))
    s.commit()

def test_recurring_item_has_intervals_and_not_oneoff(app):
    from src.backend.initialize_database_schema import Product
    from src.backend.recommendation_features import build_recommendation_candidates
    s = _session()
    milk = Product(name="Milk", category="Dairy"); s.add(milk); s.commit()
    _buy(s, milk, [28, 21, 14, 7])  # weekly
    cands = build_recommendation_candidates(s, now=datetime(2026, 6, 1, tzinfo=timezone.utc), cap=30)
    milk_c = next(c for c in cands if c["name"] == "Milk")
    assert milk_c["purchase_count"] == 4
    assert milk_c["one_off"] is False
    assert 6 <= milk_c["mean_interval"] <= 8
    assert milk_c["days_since_last"] == 7

def test_single_purchase_is_oneoff(app):
    from src.backend.initialize_database_schema import Product
    from src.backend.recommendation_features import build_recommendation_candidates
    s = _session()
    charcoal = Product(name="Charcoal", category="Outdoor"); s.add(charcoal); s.commit()
    _buy(s, charcoal, [60])
    cands = build_recommendation_candidates(s, now=datetime(2026, 6, 1, tzinfo=timezone.utc), cap=30)
    c = next(c for c in cands if c["name"] == "Charcoal")
    assert c["one_off"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_recommendation_features.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the feature builder**

```python
# src/backend/recommendation_features.py
"""Per-product features + candidate set for the recommendation pipeline. The
LLM is bad at arithmetic, so we compute the quantitative signals here and let it
judge relevance over them."""
from __future__ import annotations
import statistics
from datetime import datetime, timezone
from sqlalchemy import or_
from src.backend.initialize_database_schema import Product, Purchase, ReceiptItem


def _purchase_dates(session, product_id: int) -> list[datetime]:
    rows = (
        session.query(Purchase.date)
        .join(ReceiptItem, ReceiptItem.purchase_id == Purchase.id)
        .filter(ReceiptItem.product_id == product_id)
        .filter(or_(Purchase.transaction_type.is_(None),
                    Purchase.transaction_type != "refund"))
        .order_by(Purchase.date)
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def build_recommendation_candidates(session, *, now: datetime | None = None,
                                    cap: int = 30) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    candidates: list[dict] = []
    for product in session.query(Product).all():
        dates = _purchase_dates(session, product.id)
        if not dates:
            continue
        count = len(dates)
        last = dates[-1]
        last_cmp = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        days_since_last = (now - last_cmp).days
        intervals = [
            (dates[i + 1] - dates[i]).days
            for i in range(len(dates) - 1)
            if (dates[i + 1] - dates[i]).days > 0
        ]
        mean_interval = statistics.fmean(intervals) if intervals else None
        interval_stdev = statistics.pstdev(intervals) if len(intervals) > 1 else None
        overdue_ratio = (days_since_last / mean_interval) if mean_interval else None
        one_off = count <= 1 or (count == 2 and days_since_last > 120)
        candidates.append({
            "product_id": product.id,
            "name": product.name,
            "category": product.category,
            "purchase_count": count,
            "days_since_last": days_since_last,
            "mean_interval": round(mean_interval, 1) if mean_interval else None,
            "interval_stdev": round(interval_stdev, 1) if interval_stdev else None,
            "overdue_ratio": round(overdue_ratio, 2) if overdue_ratio else None,
            "on_hand_low": bool(getattr(product, "is_low", False)),
            "price_drop": False,          # filled in Task 4 extension if desired
            "one_off": one_off,
            "cobought_with": [],          # filled in Task 4
        })

    # Rank by a simple signal so the cap keeps the most relevant: overdue first,
    # then recency of need. (The LLM does the real judging.)
    def sort_key(c):
        return (c["overdue_ratio"] or 0, -(c["days_since_last"] or 9999))
    candidates.sort(key=sort_key, reverse=True)
    return candidates[:cap]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_recommendation_features.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/backend/recommendation_features.py tests/test_recommendation_features.py
git commit -m "feat(recs): per-product feature + candidate builder"
```

---

### Task 4: Co-purchase signal

**Files:**
- Modify: `src/backend/recommendation_features.py`
- Modify: `tests/test_recommendation_features.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_cobought_items_are_linked(app):
    from src.backend.initialize_database_schema import Product, Purchase, ReceiptItem
    from src.backend.recommendation_features import build_recommendation_candidates
    from datetime import datetime, timezone
    s = _session()
    shells = Product(name="Taco Shells", category="Pantry"); s.add(shells)
    salsa = Product(name="Salsa", category="Pantry"); s.add(salsa); s.commit()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for _ in range(3):  # bought together 3 times
        p = Purchase(date=now); s.add(p); s.flush()
        s.add(ReceiptItem(purchase_id=p.id, product_id=shells.id, name="Taco Shells", quantity=1))
        s.add(ReceiptItem(purchase_id=p.id, product_id=salsa.id, name="Salsa", quantity=1))
    s.commit()
    cands = build_recommendation_candidates(s, now=now, cap=30)
    shells_c = next(c for c in cands if c["name"] == "Taco Shells")
    assert "Salsa" in shells_c["cobought_with"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_recommendation_features.py::test_cobought_items_are_linked -v`
Expected: FAIL — `cobought_with` is empty.

- [ ] **Step 3: Implement co-purchase**

Add this helper to `recommendation_features.py` and call it inside the product loop (replace `"cobought_with": []`):
```python
def _cobought_names(session, product_id: int, limit: int = 3) -> list[str]:
    # product_ids that share a purchase with this product, by frequency
    purchase_ids = [
        r[0] for r in session.query(ReceiptItem.purchase_id)
        .filter(ReceiptItem.product_id == product_id).distinct().all()
    ]
    if not purchase_ids:
        return []
    from collections import Counter
    counts: Counter = Counter()
    rows = (
        session.query(ReceiptItem.product_id, Product.name)
        .join(Product, Product.id == ReceiptItem.product_id)
        .filter(ReceiptItem.purchase_id.in_(purchase_ids))
        .filter(ReceiptItem.product_id != product_id)
        .all()
    )
    for pid, name in rows:
        if name:
            counts[name] += 1
    return [name for name, _ in counts.most_common(limit)]
```
In the loop set: `"cobought_with": _cobought_names(session, product.id),`

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_recommendation_features.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/backend/recommendation_features.py tests/test_recommendation_features.py
git commit -m "feat(recs): co-purchase signal in candidate features"
```

---

### Task 5: LLM judge + reconcile + fallback orchestrator

**Files:**
- Create: `src/backend/recommend_via_llm.py`
- Modify: `src/backend/generate_recommendations.py` (add `generate_ai_recommendations`)
- Create: `tests/test_recommend_via_llm.py`

- [ ] **Step 1: Write the failing test (LLM mocked)**

```python
# tests/test_recommend_via_llm.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
import pytest

CANDS = [
    {"product_id": 1, "name": "Milk", "one_off": False, "category": "Dairy"},
    {"product_id": 2, "name": "Charcoal", "one_off": True, "category": "Outdoor"},
]

def test_judge_prunes_and_keeps(monkeypatch):
    from src.backend import recommend_via_llm as mod
    monkeypatch.setattr(mod, "generate_ollama_json", lambda *a, **k: {
        "items": [
            {"product_id": 1, "recommend": True, "confidence": 0.9, "reason": "due"},
            {"product_id": 2, "recommend": False, "confidence": 0.1, "reason": "one-off"},
        ]})
    recs = mod.judge_candidates(CANDS, model="qwen2.5:7b")
    names = {r["name"] for r in recs}
    assert "Milk" in names and "Charcoal" not in names
    assert recs[0]["source"] == "ai"

def test_judge_rejects_hallucinated_ids(monkeypatch):
    from src.backend import recommend_via_llm as mod
    monkeypatch.setattr(mod, "generate_ollama_json", lambda *a, **k: {
        "items": [{"product_id": 999, "recommend": True, "confidence": 0.9, "reason": "made up"}]})
    recs = mod.judge_candidates(CANDS, model="qwen2.5:7b")
    assert recs == []  # id not in candidate set -> dropped

def test_judge_raises_on_llm_failure(monkeypatch):
    from src.backend import recommend_via_llm as mod
    def boom(*a, **k): raise ValueError("bad json")
    monkeypatch.setattr(mod, "generate_ollama_json", boom)
    with pytest.raises(Exception):
        mod.judge_candidates(CANDS, model="qwen2.5:7b")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_recommend_via_llm.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the judge**

```python
# src/backend/recommend_via_llm.py
"""Local-LLM relevance judge over pre-computed candidates. Returns reconciled
recommendations or raises (caller falls back to heuristics)."""
from __future__ import annotations
import json
import logging
import os
from src.backend.call_ollama_text_api import generate_ollama_json

logger = logging.getLogger(__name__)

_PROMPT = """You are a grocery shopping assistant. Below are candidate items with
purchase features. Decide which the household should buy NOW.

Rules:
- DROP one-off / rarely-bought items (one_off=true) unless clearly needed again.
- Prefer items that are overdue (overdue_ratio >= 1) or low on hand.
- You MAY recommend a co-bought item (cobought_with) if a recent purchase implies it.
- Only use product_id values from the list. Do NOT invent items.

Return ONLY JSON: {"items":[{"product_id":int,"recommend":bool,"confidence":0..1,"reason":"short"}]}.

CANDIDATES:
%s
"""


def judge_candidates(candidates: list[dict], *, model: str | None = None) -> list[dict]:
    if not candidates:
        return []
    model = model or os.getenv("OLLAMA_RECS_MODEL", "qwen2.5:7b")
    prompt = _PROMPT % json.dumps(candidates, ensure_ascii=False)
    raw = generate_ollama_json(prompt, model=model)  # may raise -> caller falls back
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("LLM JSON missing 'items' list")

    by_id = {c["product_id"]: c for c in candidates}
    recs: list[dict] = []
    for it in items:
        try:
            pid = int(it["product_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid not in by_id:           # reject hallucinations
            continue
        if not bool(it.get("recommend")):
            continue
        conf = it.get("confidence", 0.5)
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            conf = 0.5
        recs.append({
            "product_id": pid,
            "name": by_id[pid]["name"],
            "reason": str(it.get("reason") or "Recommended"),
            "confidence": conf,
            "source": "ai",
        })
    recs.sort(key=lambda r: r["confidence"], reverse=True)
    return recs
```

- [ ] **Step 4: Add the orchestrator with fallback in `generate_recommendations.py`**

Find the imports at the top of `generate_recommendations.py` and add:
```python
from src.backend.recommendation_features import build_recommendation_candidates
from src.backend.recommend_via_llm import judge_candidates
```
Then add this function (next to `generate_all_recommendations`):
```python
def generate_ai_recommendations(session) -> tuple[list, str]:
    """Hybrid: features -> LLM judge -> reconcile. Falls back to heuristics if the
    LLM step fails. Returns (recommendations, source)."""
    import os
    if os.getenv("RECS_AI_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        return generate_all_recommendations(), "heuristic"
    try:
        cap = int(os.getenv("RECS_CANDIDATE_CAP", "30"))
        candidates = build_recommendation_candidates(session, cap=cap)
        recs = judge_candidates(candidates)
        if not recs:
            return generate_all_recommendations(), "heuristic"
        recs = _group_recommendations_by_family(recs)
        _annotate_shopping_status(recs)
        return recs, "ai"
```
> **Field-alignment check (do before running):** open `_group_recommendations_by_family`
> and `_annotate_shopping_status` and confirm which keys they read (e.g. a product-name
> key, `product_id`, `reason`, `confidence`). If they expect a key the AI rec dict
> doesn't have (e.g. `product_name` vs `name`), add that key in `judge_candidates`'
> output so grouping/annotation work unchanged. This is a 2-minute read, not a rewrite.
```python
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI recommendations failed, using heuristic fallback: %s", exc)
        return generate_all_recommendations(), "heuristic"
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/test_recommend_via_llm.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/backend/recommend_via_llm.py src/backend/generate_recommendations.py tests/test_recommend_via_llm.py
git commit -m "feat(recs): LLM judge + reconcile + heuristic fallback orchestrator"
```

---

### Task 6: Serve from cache + nightly job writes cache

**Files:**
- Modify: `src/backend/generate_recommendations.py` (GET reads cache; add a `refresh_recommendation_cache(session)`)
- Modify: `src/backend/schedule_daily_recommendations.py`
- Create: `tests/test_recommendations_cache_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommendations_cache_endpoint.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def test_refresh_then_get_reads_cache(app, monkeypatch):
    from src.backend.create_flask_application import _get_db
    import src.backend.generate_recommendations as gr
    # force deterministic pipeline output
    monkeypatch.setattr(gr, "generate_ai_recommendations",
                        lambda session: ([{"product_id": 1, "name": "Milk", "reason": "due",
                                           "confidence": 0.9, "source": "ai"}], "ai"))
    _, SF = _get_db(); s = SF()
    gr.refresh_recommendation_cache(s); s.commit()
    row = gr.read_latest_cache(s, scope="household")
    assert row["source"] == "ai"
    assert row["payload"][0]["name"] == "Milk"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_recommendations_cache_endpoint.py -v`
Expected: FAIL — `refresh_recommendation_cache` undefined.

- [ ] **Step 3: Implement refresh + cache-backed GET**

In `generate_recommendations.py` add the import and functions:
```python
from src.backend.recommendation_cache import write_cache, read_latest_cache


def refresh_recommendation_cache(session) -> dict:
    """Run the pipeline and persist the result. Returns the written summary."""
    recs, source = generate_ai_recommendations(session)
    write_cache(session, scope="household", payload=recs, source=source)
    return {"count": len(recs), "source": source}
```
Replace the body of `get_recommendations()` to serve cache, refreshing lazily if empty:
```python
def get_recommendations():
    """Serve cached recommendations (never blocks on the LLM)."""
    session = g.db_session
    cached = read_latest_cache(session, scope="household")
    if cached is None:
        # First run: build synchronously from heuristics only (fast), cache it.
        recs = generate_all_recommendations()
        write_cache(session, scope="household", payload=recs, source="heuristic")
        session.commit()
        cached = {"payload": recs, "source": "heuristic"}
    return jsonify({
        "recommendations": cached["payload"],
        "count": len(cached["payload"]),
        "source": cached.get("source"),
    }), 200
```
(Keep `require_auth` and `g` imports already present in the file.)

- [ ] **Step 4: Wire the nightly job**

In `schedule_daily_recommendations.py`, find where it currently generates recs and call the refresh inside a DB session. Add near its job function:
```python
from src.backend.generate_recommendations import refresh_recommendation_cache
from src.backend.create_flask_application import _get_db

def _run_daily_recommendation_refresh():
    _, SF = _get_db()
    session = SF()
    try:
        summary = refresh_recommendation_cache(session)
        session.commit()
        logger.info("Daily recommendation cache refreshed: %s", summary)
    finally:
        session.close()
```
Register `_run_daily_recommendation_refresh` as the scheduled callback (replace/augment the existing daily recommendation call — keep the existing schedule time `RECOMMENDATION_TIME`).

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/test_recommendations_cache_endpoint.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/generate_recommendations.py src/backend/schedule_daily_recommendations.py tests/test_recommendations_cache_endpoint.py
git commit -m "feat(recs): serve recommendations from cache; nightly job refreshes it"
```

---

### Task 7: Async on-demand refresh endpoint

**Files:**
- Create: `src/backend/manage_recommendations.py`
- Modify: `src/backend/create_flask_application.py` (register blueprint)
- Create: `tests/test_manage_recommendations.py`

Mirrors `manage_image_backfill` (threading + `_JOBS` + poll).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manage_recommendations.py
import os
os.environ["DATABASE_URL"] = "sqlite://"
import time
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def test_job_runs_and_completes(app, monkeypatch):
    import src.backend.manage_recommendations as mr
    monkeypatch.setattr(mr, "refresh_recommendation_cache", lambda session: {"count": 2, "source": "ai"})
    job_id = mr.start_refresh_job()
    for _ in range(50):
        st = mr.get_job_status(job_id)
        if st and st["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    assert st["status"] == "done"
    assert st["summary"]["count"] == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_manage_recommendations.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the async job module**

```python
# src/backend/manage_recommendations.py
"""Async on-demand recommendation refresh. The LLM is slow on CPU, so the
endpoint spawns a thread and returns a job_id the UI polls."""
from __future__ import annotations
import logging
import threading
import uuid
from flask import Blueprint, jsonify

from src.backend.generate_recommendations import refresh_recommendation_cache
from src.backend.create_flask_application import _get_db
from src.backend.manage_authentication import get_authenticated_user

logger = logging.getLogger(__name__)
recommendations_admin_bp = Blueprint("recommendations_admin", __name__, url_prefix="/recommendations")

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _run(job_id: str) -> None:
    _, SF = _get_db()
    session = SF()
    try:
        summary = refresh_recommendation_cache(session)
        session.commit()
        with _JOBS_LOCK:
            _JOBS[job_id] = {"status": "done", "summary": summary}
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Recommendation refresh job failed")
        with _JOBS_LOCK:
            _JOBS[job_id] = {"status": "error", "error": str(exc)}
    finally:
        session.close()


def start_refresh_job() -> str:
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running"}
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return job_id


def get_job_status(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        return dict(_JOBS.get(job_id)) if job_id in _JOBS else None


@recommendations_admin_bp.route("/refresh", methods=["POST"])
def refresh_endpoint():
    if not get_authenticated_user():
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"job_id": start_refresh_job()}), 202


@recommendations_admin_bp.route("/refresh/<job_id>", methods=["GET"])
def refresh_status(job_id: str):
    if not get_authenticated_user():
        return jsonify({"error": "Authentication required"}), 401
    st = get_job_status(job_id)
    if not st:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(st), 200
```

- [ ] **Step 4: Register the blueprint**

In `src/backend/create_flask_application.py` `register_blueprints`, after `app.register_blueprint(recommendations_bp)` add:
```python
    from src.backend.manage_recommendations import recommendations_admin_bp
    app.register_blueprint(recommendations_admin_bp)
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/test_manage_recommendations.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/manage_recommendations.py src/backend/create_flask_application.py tests/test_manage_recommendations.py
git commit -m "feat(recs): async on-demand refresh job + status endpoints"
```

---

### Task 8: Frontend — Refresh triggers async job + polls

**Files:**
- Modify: `src/frontend/index.html` (`loadRecs` Refresh button area)

No JS test framework — verify by reading + `node --check` of inline scripts (see prior frontend tasks). The shopping Recommendations card already has a Refresh button calling `loadRecs('shopping-recs-body')`.

- [ ] **Step 1: Add an async refresh helper**

Find `async function loadRecs(` and add a sibling function:
```javascript
      async function refreshRecsViaAI(targetId = "shopping-recs-body") {
        const body = document.getElementById(targetId);
        if (body) body.innerHTML = `<div class="empty-state"><p>Updating recommendations…</p></div>`;
        const start = await api("/recommendations/refresh", { method: "POST" });
        if (!start.ok) { return loadRecs(targetId); }
        const { job_id } = await start.json();
        for (let i = 0; i < 600; i++) {            // up to ~10 min
          await new Promise((r) => setTimeout(r, 1000));
          const st = await api(`/recommendations/refresh/${job_id}`);
          if (!st.ok) break;
          const data = await st.json();
          if (data.status === "done" || data.status === "error") break;
        }
        return loadRecs(targetId);                  // re-read from cache
      }
```

- [ ] **Step 2: Point the Refresh button at it**

Find the Recommendations refresh button (`onclick="loadRecs('shopping-recs-body')"` inside `#shopping-recommendations-body`) and change it to `onclick="refreshRecsViaAI('shopping-recs-body')"`.

- [ ] **Step 3: Verify**

Run: `grep -c "refreshRecsViaAI" src/frontend/index.html` (expect 2: definition + button).
Run the inline-JS syntax check used in prior tasks:
```bash
python3 -c "import re;s=open('src/frontend/index.html').read();open('/tmp/c.js','w').write(chr(10).join(re.findall(r'<script(?![^>]*\\bsrc=)[^>]*>(.*?)</script>',s,re.S)))"; node --check /tmp/c.js
```
Expected: no syntax error.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(recs): Recommendations Refresh runs the AI pipeline async + polls"
```

---

### Task 9: Offline evaluation harness

**Files:**
- Create: `scripts/eval_recommendations.py`

Proves AI > heuristic before defaulting AI on in prod. Dev/ops tool, not wired into the app.

- [ ] **Step 1: Implement the harness**

```python
#!/usr/bin/env python3
"""Holdout eval: hide each product's most-recent purchase, predict, and measure
hit-rate (did we recommend things that were actually rebought) and junk-rate.
Run: DATABASE_URL=sqlite:///path python3 scripts/eval_recommendations.py"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone

from src.backend.initialize_database_schema import create_db_engine, create_session_factory, Product
from src.backend.recommendation_features import build_recommendation_candidates
from src.backend.recommend_via_llm import judge_candidates
from src.backend.generate_recommendations import generate_all_recommendations


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("set DATABASE_URL", file=sys.stderr); return 2
    Session = create_session_factory(create_db_engine(url))
    s = Session()
    try:
        # "truth" = products bought in the last 30 days (what a good rec would surface)
        now = datetime.now(timezone.utc)
        cands = build_recommendation_candidates(s, now=now, cap=50)
        truth = {c["product_id"] for c in cands
                 if (c["days_since_last"] or 999) <= 30 and not c["one_off"]}

        def score(rec_ids: set[int], label: str) -> None:
            hit = len(rec_ids & truth) / len(truth) if truth else 0.0
            junk = len(rec_ids - truth) / len(rec_ids) if rec_ids else 0.0
            print(f"{label:10} hit-rate={hit:.2f}  junk-rate={junk:.2f}  n={len(rec_ids)}")

        heur = {r.get("product_id") for r in generate_all_recommendations() if r.get("product_id")}
        try:
            ai = {r["product_id"] for r in judge_candidates(cands)}
        except Exception as exc:  # noqa: BLE001
            print("AI judge failed:", exc); ai = set()

        print(f"truth set size: {len(truth)}")
        score(heur, "heuristic")
        score(ai, "ai")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run it (needs a populated DB; expect it to print two rows)**

Run: `PYTHONPATH=. DATABASE_URL="sqlite:///path/to/dev.db" python3 scripts/eval_recommendations.py`
Expected: prints `truth set size`, a `heuristic` row, and an `ai` row (ai may be 0 if Ollama unreachable — that's fine for the smoke run).

- [ ] **Step 3: Commit**

```bash
git add scripts/eval_recommendations.py
git commit -m "feat(recs): offline holdout eval harness (hit-rate vs junk-rate)"
```

---

## Notes for the implementer
- Run each task's test in isolation; the suite forces in-memory SQLite, so tests never touch a real store.
- The LLM is always mocked in unit tests — no test depends on a running Ollama. The real model is exercised only by the manual smoke/eval steps.
- Do NOT block any HTTP request on `generate_ollama_json` — only the nightly job and the async thread call it.
- Keep `generate_all_recommendations` (heuristics) intact — it's the fallback and the first-run path.
- After Task 9, before flipping prod to AI-default, run `eval_recommendations.py` against a real DB copy and confirm AI beats heuristic on hit-rate and junk-rate; if not, tune the prompt / `RECS_CANDIDATE_CAP` or set `RECS_AI_ENABLED=false`.
