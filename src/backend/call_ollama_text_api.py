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
