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
        if pid not in by_id:
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
            "product_name": by_id[pid]["name"],
            "category": by_id[pid].get("category"),
            "reason": str(it.get("reason") or "Recommended"),
            "confidence": conf,
            "source": "ai",
        })
    recs.sort(key=lambda r: r["confidence"], reverse=True)
    return recs
