import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import build_dart


def test_typography_emitted_for_body():
    out = build_dart(json.loads((REPO / "design" / "design-tokens.json").read_text()))
    assert "TextStyle(fontSize: 16.96" in out or "TextStyle(fontSize: 16.96000000000001" in out, out[:200]
    assert "fontWeight: FontWeight.w400" in out
    assert "letterSpacing: -0.374" in out
    assert "height: 1.47" in out


def test_per_theme_tracking_override():
    out = build_dart(json.loads((REPO / "design" / "design-tokens.json").read_text()))
    # Clay overrides tracking on hero to -2.125px.
    assert "letterSpacing: -2.125" in out, "clay tracking override not emitted"
