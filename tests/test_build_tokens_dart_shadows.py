import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import css_shadow_to_dart


def test_shadow_none():
    assert css_shadow_to_dart("none") == "<BoxShadow>[]"


def test_shadow_single_color_first():
    # Form: "<color> <ox> <oy> <blur> <spread>"
    expected_color = "Color.fromRGBO(0, 0, 0, 0.22)"
    out = css_shadow_to_dart("rgba(0, 0, 0, 0.22) 3px 5px 30px 0px")
    assert out.startswith("<BoxShadow>[")
    assert expected_color in out
    assert "Offset(3.0, 5.0)" in out
    assert "blurRadius: 30.0" in out
    assert "spreadRadius: 0.0" in out


def test_shadow_single_offset_first():
    # Form: "<ox> <oy> <blur> <color>"
    out = css_shadow_to_dart("0 0 0 1px rgba(245, 245, 244, 0.08)")
    assert "Color.fromRGBO(245, 245, 244, 0.08)" in out
    assert "spreadRadius: 1.0" in out


def test_shadow_multi_layer_color_first():
    out = css_shadow_to_dart(
        "rgba(0, 0, 0, 0.14) 0px 6px 20px 0px, "
        "rgba(0, 0, 0, 0.06) 0px 2px 4px 0px"
    )
    assert out.count("BoxShadow(") == 2
    assert "Color.fromRGBO(0, 0, 0, 0.14)" in out
    assert "Color.fromRGBO(0, 0, 0, 0.06)" in out
