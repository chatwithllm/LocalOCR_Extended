# AI-Assisted Shopping Recommendations — Design

**Date:** 2026-06-14
**Status:** Approved (design), pending implementation plan
**Goal:** Replace/augment the rule-based shopping recommendations with a hybrid pipeline — Python computes features, a **local** LLM (Ollama) prunes noise and adds contextual catches — to fix the two observed accuracy problems: **recommends junk** (false positives) and **misses things** (false negatives). Privacy-first: purchase data never leaves the box.

## Problem

`src/backend/generate_recommendations.py` recommends via heuristics:
`detect_price_deals` (price vs 90-day avg), `detect_seasonal_patterns`
(days-since-last vs average interval), plus low-stock / manual-low flags.

Observed gaps (user-confirmed):
- **Junk** — one-off / rare purchases get treated as recurring and surface as noise.
- **Misses** — irregular or context-dependent needs (complementary items, things the
  interval math can't see) never surface.

LLMs are weak at quantitative prediction but strong at reasoning over structured
context. So accuracy comes from **good features computed in Python** plus an LLM
acting as a **relevance judge**, not from raw model horsepower. This makes a small
**local** model (Ollama `qwen2.5:7b`) sufficient — verified: in a smoke test it
correctly recommended a due staple, **rejected a one-off (charcoal)**, and **caught
a complementary item** (tortillas after taco shells).

## Constraints

- **Privacy:** self-hosted promise — only aggregated features (item names + numbers)
  go to a **local** Ollama model; nothing to any cloud SaaS. Ollama stays on the
  `extended-internal` (no-egress) network for inference.
- **Performance:** prod (UDImmich) is **CPU-only**. LLM calls are slow (minutes), so
  they must **never block a request**. Recommendations are precomputed and cached;
  the LLM runs in the background.
- **Reliability:** AI is **additive** — if Ollama is unavailable, slow, or returns
  invalid JSON, the system falls back to today's heuristic recommendations. No hard
  dependency on the model.

## Architecture: hybrid pipeline

Four stages, each independently testable.

### 1. Feature builder (Python) — `recommendation_features.py` (new)
Per product with any purchase history, compute a compact feature row:
- purchase count, first/last purchase date, **days since last**
- mean + stdev of inter-purchase **intervals**; **overdue ratio** = days_since_last / mean_interval
- quantity trend; current **inventory level / low / manual-low** flags
- **price trend** (latest vs 90-day avg) — reuse `detect_price_deals` signal
- **one-off score** (count == 1, or very long since single purchase → likely not recurring)
- **co-purchase** edges: products frequently appearing in the same trips/receipts
  (a lightweight basket count, capped)

Emit the **candidate set**: top ~30–40 products ranked by any positive signal,
each as a structured row. (Cap keeps the LLM batch small for CPU.)

### 2. LLM judge (local Ollama) — `recommend_via_llm.py` (new)
One **batched** call (`/api/generate`, `format: json`, low temperature) containing
all candidate rows and a strict instruction:
> Given these candidates with features, return the items worth recommending now,
> each with `confidence` (0–1) and a one-line `reason`. Drop one-offs and noise.
> You MAY add a complementary item implied by recent purchases if clearly needed.

Output validated against a JSON schema. Model id from `OLLAMA_RECS_MODEL`
(default `qwen2.5:7b`; can drop to a 3b on a slow CPU — the hybrid design keeps a
3b viable). Endpoint from existing `OLLAMA_ENDPOINT`.

### 3. Reconcile (Python) — in `generate_recommendations.py`
- Reject hallucinated items (anything not in the candidate set OR not a real product/
  recent purchase) — never recommend an item the user has no relationship to.
- Clamp confidence; map to the existing `reason` taxonomy where possible, else carry
  the LLM reason text.
- Reuse existing `_group_recommendations_by_family` + `_annotate_shopping_status`.

### 4. Cache + serve
- Persist the reconciled result in a new `recommendation_cache` table (`id`, `scope`
  (e.g. "household"), `payload_json`, `source`, `generated_at`), created via the
  SQLAlchemy model + `create_all` like other tables in this project (no hand-written
  migration required). `/recommendations` serves the latest **cache** row — instant,
  unchanged response contract for the frontend.
- **Nightly batch:** `schedule_daily_recommendations` runs the pipeline and writes the
  cache.
- **On-demand:** the Refresh button POSTs to start an **async background job**
  (threading + `_JOBS` registry, mirroring `manage_image_backfill`); returns a
  `job_id`. The UI shows "Updating recommendations…" and polls a status endpoint;
  when done it reloads from cache. Never a synchronous LLM call.

## Fallback path
If the LLM step fails (timeout, connection, invalid JSON after one retry), stages 1
and the existing heuristics produce the result and the cache is written from those.
A `source: "ai" | "heuristic"` field records which path ran (for debugging + eval).

## Evaluation (proves it's actually better)
`scripts/eval_recommendations.py` (new, offline/dev): hold out each user's last N
purchases, run both the heuristic and the AI pipeline against the truncated history,
and measure:
- **hit-rate** — fraction of held-out repurchases that were recommended (↑ = fewer misses)
- **junk-rate** — recommended items NOT in the held-out window (↓ = less junk)
Report heuristic-vs-AI side by side. Gate: AI must beat heuristic on both before the
nightly job defaults to AI in prod. Also used to tune the prompt / candidate cap.

## Files

- **New:** `src/backend/recommendation_features.py` (feature + candidate builder),
  `src/backend/recommend_via_llm.py` (Ollama judge + JSON schema + fallback),
  `src/backend/manage_recommendations.py` (async refresh job + status endpoints,
  mirroring `manage_image_backfill`), `scripts/eval_recommendations.py` (holdout eval),
  and the `RecommendationCache` model added to `initialize_database_schema.py`.
- **Modify:** `src/backend/generate_recommendations.py` (orchestrate pipeline +
  reconcile + cache + serve-from-cache), `schedule_daily_recommendations.py` (call
  the pipeline), `.env.example` (`OLLAMA_RECS_MODEL`, optional
  `RECS_AI_ENABLED`/`RECS_CANDIDATE_CAP`), frontend Refresh → async poll.
- **No change:** the `/recommendations` GET response shape (frontend stays compatible).

## Success criteria
1. `/recommendations` still returns instantly (served from cache; never blocks on LLM).
2. Nightly job populates the cache via the AI pipeline; on-demand Refresh runs it async
   with a visible "updating" state and no request blocking.
3. One-off purchases are pruned (junk ↓); at least co-purchase-implied items can surface
   (misses ↓), demonstrated by the eval harness beating the heuristic on hit-rate and
   junk-rate.
4. Ollama down / invalid JSON → automatic heuristic fallback, no user-visible failure.
5. No purchase data sent to any cloud service; Ollama stays on the no-egress network.
6. Model + candidate cap are env-configurable to tune for CPU speed.

## Open / deployment notes
- Prod CPU-only: first run cold-loads the model (~seconds) then generates at the box's
  CPU rate; keep `RECS_CANDIDATE_CAP` tight (~30). If a nightly run is too slow, drop
  `OLLAMA_RECS_MODEL` to a 3b.
- Ollama provisioning (container on `local-infra` profile, or native for GPU) and the
  model pull are an ops prerequisite, tracked separately from this feature code.
