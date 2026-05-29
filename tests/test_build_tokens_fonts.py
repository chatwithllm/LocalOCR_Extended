import subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build_tokens.py"


def test_dart_target_emits_fonts_sidecar(tmp_path):
    dart_out = tmp_path / "tokens.generated.dart"
    fonts_out = tmp_path / "fonts.generated.yaml"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--target", "dart",
         "--out", str(dart_out),
         "--fonts-out", str(fonts_out)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    body = fonts_out.read_text()
    assert "family: Inter" in body
    assert "family: Lora" in body
    assert "family: iAWriterQuattroS" in body
    assert "family: JetBrainsMono" in body
    assert "assets/fonts/Inter-Regular.ttf" in body
    assert "weight: 700" in body
