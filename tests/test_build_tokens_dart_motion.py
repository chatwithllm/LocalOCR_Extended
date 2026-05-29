import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import css_duration_to_dart, css_curve_to_dart


def test_duration_ms():
    assert css_duration_to_dart("200ms") == "Duration(milliseconds: 200)"
    assert css_duration_to_dart("1600ms") == "Duration(milliseconds: 1600)"


def test_curve_cubic():
    assert css_curve_to_dart("cubic-bezier(0.2, 0, 0, 1)") == "Cubic(0.2, 0.0, 0.0, 1.0)"
    assert css_curve_to_dart("cubic-bezier(0.16, 1, 0.3, 1)") == "Cubic(0.16, 1.0, 0.3, 1.0)"
