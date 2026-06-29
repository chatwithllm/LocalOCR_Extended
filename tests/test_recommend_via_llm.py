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
    names = {r["product_name"] for r in recs}
    assert "Milk" in names and "Charcoal" not in names
    assert recs[0]["source"] == "ai"

def test_judge_rejects_hallucinated_ids(monkeypatch):
    from src.backend import recommend_via_llm as mod
    monkeypatch.setattr(mod, "generate_ollama_json", lambda *a, **k: {
        "items": [{"product_id": 999, "recommend": True, "confidence": 0.9, "reason": "made up"}]})
    recs = mod.judge_candidates(CANDS, model="qwen2.5:7b")
    assert recs == []

def test_judge_raises_on_llm_failure(monkeypatch):
    from src.backend import recommend_via_llm as mod
    def boom(*a, **k): raise ValueError("bad json")
    monkeypatch.setattr(mod, "generate_ollama_json", boom)
    with pytest.raises(Exception):
        mod.judge_candidates(CANDS, model="qwen2.5:7b")
