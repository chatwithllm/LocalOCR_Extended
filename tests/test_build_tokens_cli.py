import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build_tokens.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_default_target_emits_css_to_stdout():
    r = _run("--target", "css", "--stdout")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("/* AUTO-GENERATED")
    assert "--color-brand:" in r.stdout


def test_no_target_flag_means_css_for_backcompat():
    r = _run("--stdout")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("/* AUTO-GENERATED")
    assert "--color-brand:" in r.stdout


def test_unknown_target_errors():
    r = _run("--target", "wat", "--stdout")
    assert r.returncode != 0
    assert "invalid choice" in r.stderr.lower() or "wat" in r.stderr
