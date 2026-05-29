import shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "merge_fonts_into_pubspec.py"


def test_merge_replaces_fonts_block_only(tmp_path):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text(
        "name: localocr_extended\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  dio: ^5.0.0\n"
        "flutter:\n"
        "  uses-material-design: true\n"
        "  fonts:\n"
        "    - family: OldFont\n"
        "      fonts:\n"
        "        - asset: assets/fonts/Old.ttf\n"
    )
    fonts_yaml = tmp_path / "fonts.generated.yaml"
    fonts_yaml.write_text(
        "flutter:\n"
        "  fonts:\n"
        "    - family: Inter\n"
        "      fonts:\n"
        "        - asset: assets/fonts/Inter-Regular.ttf\n"
    )
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--pubspec", str(pubspec),
         "--fonts", str(fonts_yaml)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    out = pubspec.read_text()
    assert "OldFont" not in out
    assert "Inter-Regular.ttf" in out
    assert "uses-material-design: true" in out
    assert "dio: ^5.0.0" in out  # untouched
