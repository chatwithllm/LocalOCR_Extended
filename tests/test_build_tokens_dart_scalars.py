import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_tokens_dart import css_scalar_to_dart, dart_field_name


def test_rem():
    assert css_scalar_to_dart("1rem") == "16.0"
    assert css_scalar_to_dart("1.5rem") == "24.0"
    assert css_scalar_to_dart("0.75rem") == "12.0"


def test_px():
    assert css_scalar_to_dart("8px") == "8.0"
    assert css_scalar_to_dart("9999px") == "9999.0"
    assert css_scalar_to_dart("0") == "0.0"


def test_dart_field_name_basic():
    assert dart_field_name("brand") == "brand"
    assert dart_field_name("brand-hover") == "brandHover"
    assert dart_field_name("text-primary") == "textPrimary"


def test_dart_field_name_numeric_suffix():
    assert dart_field_name("surface-2") == "surface2"
    assert dart_field_name("0") == "v0"
    assert dart_field_name("0-5") == "v0_5"
    assert dart_field_name("16") == "v16"


def test_dart_field_name_special_chars():
    assert dart_field_name("2xl") == "v2xl"
    assert dart_field_name("body-em") == "bodyEm"
