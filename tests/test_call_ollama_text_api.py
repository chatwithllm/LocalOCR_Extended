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
