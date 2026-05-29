import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import css_color_to_dart, build_dart


def test_hex_rrggbb():
    assert css_color_to_dart("#0071e3") == "Color(0xFF0071E3)"


def test_hex_rrggbb_lower():
    assert css_color_to_dart("#ffffff") == "Color(0xFFFFFFFF)"


def test_rgba_opaque():
    assert css_color_to_dart("rgba(0, 113, 227, 1)") == "Color.fromRGBO(0, 113, 227, 1.0)"


def test_rgba_alpha_decimal():
    assert css_color_to_dart("rgba(0, 0, 0, 0.48)") == "Color.fromRGBO(0, 0, 0, 0.48)"


def test_rgba_alpha_with_spaces():
    assert css_color_to_dart("rgba(245, 245, 247, 0.86)") == "Color.fromRGBO(245, 245, 247, 0.86)"


def test_rgba_alpha_without_leading_zero():
    assert css_color_to_dart("rgba(0, 0, 0, .5)") == "Color.fromRGBO(0, 0, 0, 0.5)"


def test_build_dart_contains_header():
    tokens = {
      "color": {"light": {"brand": "#0071e3"}, "dark": {"brand": "#0a84ff"}},
      "shadow": {}, "typography": {"font-family": {"display": "x", "text": "y", "mono": "z"}, "scale": {}},
      "space": {}, "radius": {}, "stroke": {}, "icon": {},
      "motion": {"duration": {}, "ease": {}},
      "themes": {},
    }
    out = build_dart(tokens)
    assert out.startswith("// AUTO-GENERATED")
    assert "Color(0xFF0071E3)" in out
    assert "Color(0xFF0A84FF)" in out
