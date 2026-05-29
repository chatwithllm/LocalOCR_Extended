import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import build_dart


def test_lerp_interpolates_every_color_field():
    out = build_dart(json.loads((REPO / "design" / "design-tokens.json").read_text()))
    # Per-field Color.lerp call must exist for at least the brand field.
    assert "Color.lerp(brand, other.brand, t)" in out


def test_lerp_handles_doubles():
    out = build_dart(json.loads((REPO / "design" / "design-tokens.json").read_text()))
    assert "lerpDouble(space4, other.space4, t)" in out
