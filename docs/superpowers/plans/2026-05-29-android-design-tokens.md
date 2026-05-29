# Android Design Tokens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship system-wide design tokens for the Flutter Android app, sourced from `design/design-tokens.json`, consumed via Material 3 `ColorScheme` slots + an `AppTokens` `ThemeExtension`, with all 6 themes (light, dark, clay, clay-dark, notion, notion-dark) backed and all 11 shipped features migrated off raw color/spacing/duration/curve/radius/text-style/shadow literals.

**Architecture:** `scripts/build_tokens.py` extended with a `--target {css,dart,all}` flag. The Dart target emits `lib/app/theme/tokens.generated.dart` containing one `AppTokens` constructor per theme plus `appThemeDataFor(name)` and `appTokensFor(name)` lookups. `lib/app/theme/theme.dart` is slimmed to the cycle order + `nextTheme`. `lib/app/theme/theme_provider.dart` becomes an async Riverpod notifier backed by `SharedPreferences`. Custom-lint rules forbid literal colors/durations/curves/spacing/radii/text styles/shadows in `lib/features/**` and `lib/app/**` (except `lib/app/theme/`). Migration of 11 features happens in atomic per-feature commits inside a single PR. Fonts: Inter (light/dark), Lora (clay), iA Writer Quattro (notion), JetBrains Mono (mono everywhere), all SIL OFL, all subset to Latin+Latin-Extended.

**Tech Stack:** Python 3.11, Flutter 3.24 / Dart 3.5, Riverpod 2.5 + `riverpod_generator`, `shared_preferences`, `custom_lint` + `analyzer`, `golden_toolkit`, `ruamel.yaml`, `fonttools`, GitHub Actions.

---

## Phase A — Codegen infrastructure

### Task 1: `--target` flag on `build_tokens.py` (no behaviour change)

**Files:**
- Modify: `scripts/build_tokens.py` (currently 215 lines, ends in `if __name__ == "__main__":`)
- Test: `tests/test_build_tokens_cli.py` (new)

- [ ] **Step 1: Write failing test for `--target css` (default behaviour preserved)**

Create `tests/test_build_tokens_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_cli.py -v`
Expected: FAIL — `--target` is not a known arg.

- [ ] **Step 3: Add `--target` flag (default `css`)**

Modify `scripts/build_tokens.py` in the `main()` function. Replace the argparse block:

```python
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--out", type=Path, default=None,
                   help="output file (default depends on --target)")
    p.add_argument("--stdout", action="store_true")
    p.add_argument(
        "--target",
        choices=("css", "dart", "all"),
        default="css",
        help="emit CSS (default), Dart, or both",
    )
    args = p.parse_args()

    if not args.input.exists():
        print(f"error: input {args.input} not found", file=sys.stderr)
        return 1

    tokens = json.loads(args.input.read_text())

    targets = ("css", "dart") if args.target == "all" else (args.target,)
    for target in targets:
        rc = _emit_target(target, tokens, args)
        if rc != 0:
            return rc
    return 0


def _emit_target(target: str, tokens: dict, args) -> int:
    if target == "css":
        content = build(tokens)
        out = args.out or DEFAULT_OUTPUT_CSS
    elif target == "dart":
        from build_tokens_dart import build_dart
        content = build_dart(tokens)
        out = args.out or DEFAULT_OUTPUT_DART
    else:
        print(f"error: unknown target {target}", file=sys.stderr)
        return 1

    if args.stdout:
        sys.stdout.write(content)
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)
    print(f"wrote {out} ({len(content):,} bytes)")
    return 0
```

Also at module top rename `DEFAULT_OUTPUT` → `DEFAULT_OUTPUT_CSS`, add:

```python
DEFAULT_OUTPUT_CSS = REPO_ROOT / "src" / "frontend" / "styles" / "tokens.generated.css"
DEFAULT_OUTPUT_DART = REPO_ROOT / "lib" / "app" / "theme" / "tokens.generated.dart"
```

Update any in-file references to the old name accordingly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_tokens_cli.py -v`
Expected: PASS — first two tests green; third test green because `argparse` rejects unknown choice.

The Dart import will fail when `--target dart` is used because `build_tokens_dart.py` does not exist yet; that is fine — we have no test exercising it.

- [ ] **Step 5: Manually verify CSS output unchanged**

Run: `python3 scripts/build_tokens.py --target css --stdout | diff - src/frontend/styles/tokens.generated.css`
Expected: no output (files identical).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_tokens.py tests/test_build_tokens_cli.py
git commit -m "feat(tokens): add --target {css,dart,all} flag to build_tokens.py"
```

### Task 2: Dart emitter — colors (light + dark)

**Files:**
- Create: `scripts/build_tokens_dart.py`
- Test: `tests/test_build_tokens_dart_colors.py` (new)

- [ ] **Step 1: Write failing test for color conversion**

Create `tests/test_build_tokens_dart_colors.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_colors.py -v`
Expected: FAIL — module `build_tokens_dart` not found.

- [ ] **Step 3: Create minimal `build_tokens_dart.py`**

Create `scripts/build_tokens_dart.py`:

```python
#!/usr/bin/env python3
"""Compile design/design-tokens.json → Dart `AppTokens` ThemeExtension.

Emits lib/app/theme/tokens.generated.dart. Called via:
    python3 scripts/build_tokens.py --target dart
"""
from __future__ import annotations

import re
import sys
from typing import Any


HEADER = """\
// AUTO-GENERATED — do not edit.
// Source: design/design-tokens.json
// Regenerate: python3 scripts/build_tokens.py --target dart
//
// Consume: ThemeData td = appThemeDataFor('clay');
// Direct token access: AppTokens t = Theme.of(context).extension<AppTokens>()!;

import 'dart:ui';
import 'package:flutter/material.dart';

"""


_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGBA_RE = re.compile(
    r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)$"
)


def css_color_to_dart(value: str) -> str:
    """Convert a CSS color literal to a Dart `Color(...)` expression."""
    v = value.strip()
    m = _HEX_RE.match(v)
    if m:
        return f"Color(0xFF{m.group(1).upper()})"
    m = _RGBA_RE.match(v)
    if m:
        r, g, b, a = m.group(1), m.group(2), m.group(3), m.group(4)
        if a is None:
            a = "1.0"
        if "." not in a:
            a = f"{a}.0"
        return f"Color.fromRGBO({r}, {g}, {b}, {a})"
    raise ValueError(f"cannot convert CSS colour to Dart: {value!r}")


def build_dart(tokens: dict[str, Any]) -> str:
    parts = [HEADER]
    # Future tasks add: AppTokens class def, per-theme constructors,
    # appTokensFor, appThemeDataFor.
    # Stub for Task 2: emit a comment listing converted colour samples so
    # tests can assert the converter ran.
    parts.append("// --- colour samples (Task 2 stub) ---\n")
    for theme_name in ("light", "dark"):
        colors = tokens["color"].get(theme_name, {})
        for key, value in colors.items():
            parts.append(f"// {theme_name}.{key} = {css_color_to_dart(value)}\n")
    return "".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_tokens_dart_colors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_colors.py
git commit -m "feat(tokens): dart emitter — colour conversion (hex + rgba)"
```

### Task 3: Dart emitter — scalars (space, radius, stroke, icon)

**Files:**
- Modify: `scripts/build_tokens_dart.py`
- Test: `tests/test_build_tokens_dart_scalars.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_build_tokens_dart_scalars.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_scalars.py -v`
Expected: FAIL — symbols not defined.

- [ ] **Step 3: Add conversion helpers**

Append to `scripts/build_tokens_dart.py`:

```python
_REM_RE = re.compile(r"^([0-9]*\.?[0-9]+)rem$")
_PX_RE = re.compile(r"^([0-9]*\.?[0-9]+)px$")


def css_scalar_to_dart(value: str) -> str:
    """Convert CSS length (rem/px/bare-zero) to a Dart double literal."""
    v = value.strip()
    if v == "0":
        return "0.0"
    m = _REM_RE.match(v)
    if m:
        return f"{float(m.group(1)) * 16:.1f}"
    m = _PX_RE.match(v)
    if m:
        f = float(m.group(1))
        return f"{f:.1f}" if f != int(f) else f"{int(f)}.0"
    raise ValueError(f"cannot convert CSS scalar to Dart: {value!r}")


def dart_field_name(token_key: str) -> str:
    """Convert a kebab-case token key to a valid Dart identifier.

    Rules:
      - kebab → camel  (brand-hover → brandHover)
      - leading digit → prefix with 'v'  (0 → v0, 2xl → v2xl)
      - embedded '-' inside numeric runs → '_'  (0-5 → v0_5)
    """
    parts = token_key.split("-")
    # If the whole key is numeric-ish (e.g. "0", "0-5", "16"), use v-prefix.
    if all(p.isdigit() for p in parts):
        return "v" + "_".join(parts)
    # If first segment starts with a digit (e.g. "2xl"), prefix v but keep camel for rest.
    head = parts[0]
    rest = parts[1:]
    if head[0].isdigit():
        out = "v" + head
    else:
        out = head
    for r in rest:
        if r and not r[0].isdigit():
            out += r[0].upper() + r[1:]
        else:
            # Treat numeric tail as separator-preserved (surface-2 → surface2).
            out += r
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_tokens_dart_scalars.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_scalars.py
git commit -m "feat(tokens): dart emitter — scalar conversion + identifier mapping"
```

### Task 4: Dart emitter — durations & curves

**Files:**
- Modify: `scripts/build_tokens_dart.py`
- Test: `tests/test_build_tokens_dart_motion.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_build_tokens_dart_motion.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_motion.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `scripts/build_tokens_dart.py`:

```python
_MS_RE = re.compile(r"^(\d+)ms$")
_CUBIC_RE = re.compile(
    r"^cubic-bezier\(\s*([0-9.\-]+)\s*,\s*([0-9.\-]+)\s*,\s*([0-9.\-]+)\s*,\s*([0-9.\-]+)\s*\)$"
)


def css_duration_to_dart(value: str) -> str:
    m = _MS_RE.match(value.strip())
    if not m:
        raise ValueError(f"cannot convert CSS duration to Dart: {value!r}")
    return f"Duration(milliseconds: {m.group(1)})"


def _dartify_float(x: str) -> str:
    f = float(x)
    if f == int(f):
        return f"{int(f)}.0"
    return f"{f}"


def css_curve_to_dart(value: str) -> str:
    m = _CUBIC_RE.match(value.strip())
    if not m:
        raise ValueError(f"cannot convert CSS curve to Dart: {value!r}")
    return (
        f"Cubic({_dartify_float(m.group(1))}, {_dartify_float(m.group(2))}, "
        f"{_dartify_float(m.group(3))}, {_dartify_float(m.group(4))})"
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_build_tokens_dart_motion.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_motion.py
git commit -m "feat(tokens): dart emitter — durations + cubic-bezier curves"
```

### Task 5: Dart emitter — shadows (single + multi-layer)

**Files:**
- Modify: `scripts/build_tokens_dart.py`
- Test: `tests/test_build_tokens_dart_shadows.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_build_tokens_dart_shadows.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_shadows.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement shadow conversion**

Append to `scripts/build_tokens_dart.py`:

```python
def _parse_shadow_layer(layer: str) -> str:
    """Convert one shadow layer (either color-first or offset-first form) to Dart."""
    layer = layer.strip()
    # Split into color part and the four offsets. Color is either rgba(...) or #hex.
    color_match = re.search(r"(rgba?\([^)]*\)|#[0-9a-fA-F]{6})", layer)
    if not color_match:
        raise ValueError(f"shadow layer missing colour: {layer!r}")
    color_expr = css_color_to_dart(color_match.group(1))
    # Remove the colour, then split the remainder into numeric tokens.
    rest = (layer[: color_match.start()] + " " + layer[color_match.end():]).strip()
    nums = re.findall(r"-?[0-9.]+px|0", rest)
    if len(nums) < 3 or len(nums) > 4:
        raise ValueError(f"shadow layer needs 3–4 offsets, got {nums!r} from {layer!r}")
    px = [css_scalar_to_dart(n) for n in nums]
    ox, oy, blur = px[0], px[1], px[2]
    spread = px[3] if len(px) == 4 else "0.0"
    return (
        f"BoxShadow(color: {color_expr}, "
        f"offset: Offset({ox}, {oy}), "
        f"blurRadius: {blur}, "
        f"spreadRadius: {spread})"
    )


def css_shadow_to_dart(value: str) -> str:
    v = value.strip()
    if v == "none":
        return "<BoxShadow>[]"
    layers = [seg for seg in re.split(r",(?![^()]*\))", v) if seg.strip()]
    parts = [_parse_shadow_layer(l) for l in layers]
    return "<BoxShadow>[" + ", ".join(parts) + "]"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_build_tokens_dart_shadows.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_shadows.py
git commit -m "feat(tokens): dart emitter — single + multi-layer box shadows"
```

### Task 6: Dart emitter — full file shape (AppTokens class + per-theme constructors)

**Files:**
- Modify: `scripts/build_tokens_dart.py`
- Modify: `tests/test_build_tokens_dart_colors.py` (extend)

- [ ] **Step 1: Write failing test for full file shape**

Append to `tests/test_build_tokens_dart_colors.py`:

```python
def _real_tokens():
    import json
    return json.loads((REPO / "design" / "design-tokens.json").read_text())


def test_emit_contains_app_tokens_class():
    out = build_dart(_real_tokens())
    assert "class AppTokens extends ThemeExtension<AppTokens>" in out
    assert "AppTokens copyWith(" in out
    assert "AppTokens lerp(" in out


def test_emit_contains_per_theme_constructors():
    out = build_dart(_real_tokens())
    for name in ("Light", "Dark", "Clay", "ClayDark", "Notion", "NotionDark"):
        assert f"AppTokens _build{name}Tokens()" in out, name


def test_emit_contains_public_lookups():
    out = build_dart(_real_tokens())
    assert "AppTokens appTokensFor(String name)" in out
    assert "ThemeData appThemeDataFor(String name)" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_colors.py -v`
Expected: FAIL on the three new tests.

- [ ] **Step 3: Replace the Task 2 stub with the real emitter**

Replace `build_dart` and add helpers in `scripts/build_tokens_dart.py`. The full body of the file should now contain (in addition to the helpers from Tasks 2–5):

```python
# ── Token field schema ───────────────────────────────────────────
# Defines: which JSON keys become which Dart fields, with their types.

_COLOR_FIELDS: list[tuple[str, str]] = [
    # (json key under color.<theme>, dart field name)
    ("brand", "brand"),
    ("brand-hover", "brandHover"),
    ("brand-pressed", "brandPressed"),
    ("brand-soft", "brandSoft"),
    ("brand-contrast", "brandContrast"),
    ("link", "link"),
    ("bg", "bg"),
    ("bg-inverse", "bgInverse"),
    ("surface", "surface"),
    ("surface-2", "surface2"),
    ("surface-3", "surface3"),
    ("surface-4", "surface4"),
    ("surface-inverse", "surfaceInverse"),
    ("overlay", "overlay"),
    ("overlay-soft", "overlaySoft"),
    ("glass-nav", "glassNav"),
    ("text-primary", "textPrimary"),
    ("text-secondary", "textSecondary"),
    ("text-muted", "textMuted"),
    ("text-disabled", "textDisabled"),
    ("text-inverse", "textInverse"),
    ("border", "border"),
    ("border-strong", "borderStrong"),
    ("border-brand", "borderBrand"),
    ("focus", "focus"),
    ("success", "success"),
    ("success-soft", "successSoft"),
    ("warning", "warning"),
    ("warning-soft", "warningSoft"),
    ("error", "error"),
    ("error-soft", "errorSoft"),
    ("error-hover", "errorHover"),
    ("info", "info"),
    ("info-soft", "infoSoft"),
    ("confidence-high", "confidenceHigh"),
    ("confidence-medium", "confidenceMedium"),
    ("confidence-low", "confidenceLow"),
    ("confidence-high-soft", "confidenceHighSoft"),
    ("confidence-medium-soft", "confidenceMediumSoft"),
    ("confidence-low-soft", "confidenceLowSoft"),
    ("cat-grocery", "catGrocery"),
    ("cat-restaurant", "catRestaurant"),
    ("cat-utility", "catUtility"),
    ("cat-personal-service", "catPersonalService"),
    ("cat-subscription", "catSubscription"),
    ("cat-other", "catOther"),
]

_SPACE_KEYS = ["0", "0-5", "1", "1-5", "2", "3", "4", "5", "6", "8", "10", "12", "16", "20", "24", "32", "40", "48"]
_RADIUS_KEYS = ["0", "xs", "sm", "md", "lg", "xl", "pill", "full"]
_STROKE_KEYS = ["0", "1", "2", "3"]
_SHADOW_KEYS = ["0", "1", "2", "3", "4", "5"]
_DURATION_KEYS = ["instant", "fast", "base", "slow", "elaborate"]
_EASE_KEYS = ["standard", "out", "in", "in-out", "spring"]

_TYPE_ROLES = [
    "hero", "4xl", "3xl", "2xl", "xl", "lg", "lg-reg", "md",
    "body", "body-em", "sm", "sm-em", "xs", "xs-em", "nano",
]

_THEME_NAMES = ["light", "dark", "clay", "clay-dark", "notion", "notion-dark"]


def _theme_camel(name: str) -> str:
    """light → Light, clay-dark → ClayDark, notion → Notion."""
    return "".join(seg.capitalize() for seg in name.split("-"))


def _resolve(base: dict, theme: dict, category: str, key: str, default=None):
    """Look up a token, preferring theme override, falling back to base."""
    if category in theme and key in theme[category]:
        return theme[category][key]
    if category in base and key in base[category]:
        return base[category][key]
    return default


def _resolve_color(tokens: dict, theme_name: str, key: str) -> str:
    """Color resolution: base by brightness (light/dark), then theme override."""
    # Determine the brightness family: a theme name ending in '-dark' or named 'dark' uses dark base.
    family = "dark" if theme_name == "dark" or theme_name.endswith("-dark") else "light"
    base = tokens["color"][family].get(key)
    override = tokens.get("themes", {}).get(theme_name, {}).get("color", {}).get(key)
    return override if override is not None else base


def _emit_app_tokens_class() -> str:
    fields: list[str] = []
    for _, name in _COLOR_FIELDS:
        fields.append(f"  final Color {name};")
    for k in _SPACE_KEYS:
        fields.append(f"  final double space{dart_field_name(k).lstrip('v')};")
    for k in _RADIUS_KEYS:
        fields.append(f"  final double radius{dart_field_name(k).capitalize()};")
    for k in _STROKE_KEYS:
        fields.append(f"  final double stroke{dart_field_name(k).lstrip('v')};")
    for k in _SHADOW_KEYS:
        fields.append(f"  final List<BoxShadow> shadow{dart_field_name(k).lstrip('v')};")
    for k in _DURATION_KEYS:
        fields.append(f"  final Duration duration{k.capitalize()};")
    for k in _EASE_KEYS:
        nm = "".join(p.capitalize() for p in k.split("-"))
        fields.append(f"  final Curve ease{nm};")
    for k in _TYPE_ROLES:
        fields.append(f"  final TextStyle type{dart_field_name(k).capitalize()};")
    fields.append("  final String fontDisplay;")
    fields.append("  final String fontText;")
    fields.append("  final String fontMono;")

    params = ",\n".join(f"    required this.{ln.split()[2].rstrip(';')}" for ln in fields)

    return (
        "class AppTokens extends ThemeExtension<AppTokens> {\n"
        + "\n".join(fields) + "\n\n"
        + "  const AppTokens({\n" + params + ",\n  });\n\n"
        + "  @override\n  AppTokens copyWith() => this; // see Task 7 — codegen does not produce field overrides; mutation happens via theme switch.\n\n"
        + "  @override\n  AppTokens lerp(ThemeExtension<AppTokens>? other, double t) {\n"
        + "    if (other is! AppTokens || t == 0) return this;\n"
        + "    if (t == 1) return other;\n"
        + "    return t < 0.5 ? this : other; // snap; see Task 7 to upgrade to per-field lerp.\n"
        + "  }\n"
        + "}\n"
    )


def _emit_theme_constructor(theme_name: str, tokens: dict) -> str:
    """Emit `AppTokens _build<Name>Tokens() => AppTokens(... );`."""
    cls_name = _theme_camel(theme_name)
    lines = [f"AppTokens _build{cls_name}Tokens() => AppTokens("]
    for json_key, dart_key in _COLOR_FIELDS:
        v = _resolve_color(tokens, theme_name, json_key)
        if v is None:
            v_dart = "Color(0xFF000000) /* MISSING token */"
            print(
                f"WARN: theme {theme_name!r} missing color.{json_key} — using black",
                file=sys.stderr,
            )
        else:
            v_dart = css_color_to_dart(v)
        lines.append(f"  {dart_key}: {v_dart},")
    # Space
    space_src = tokens["space"]
    for k in _SPACE_KEYS:
        name = "space" + dart_field_name(k).lstrip("v")
        lines.append(f"  {name}: {css_scalar_to_dart(space_src[k])},")
    # Radius (theme may override)
    radius_src = {**tokens["radius"], **tokens.get("themes", {}).get(theme_name, {}).get("radius", {})}
    for k in _RADIUS_KEYS:
        name = "radius" + dart_field_name(k).capitalize()
        lines.append(f"  {name}: {css_scalar_to_dart(radius_src[k])},")
    # Stroke
    for k in _STROKE_KEYS:
        name = "stroke" + dart_field_name(k).lstrip("v")
        lines.append(f"  {name}: {css_scalar_to_dart(tokens['stroke'][k])},")
    # Shadows (theme may override)
    shadow_src = {**tokens["shadow"], **tokens.get("themes", {}).get(theme_name, {}).get("shadow", {})}
    for k in _SHADOW_KEYS:
        name = "shadow" + dart_field_name(k).lstrip("v")
        lines.append(f"  {name}: {css_shadow_to_dart(shadow_src[k])},")
    # Durations (theme may override)
    dur_src = {**tokens["motion"]["duration"], **tokens.get("themes", {}).get(theme_name, {}).get("duration", {})}
    for k in _DURATION_KEYS:
        name = "duration" + k.capitalize()
        lines.append(f"  {name}: {css_duration_to_dart(dur_src[k])},")
    # Eases (theme may override)
    ease_src = {**tokens["motion"]["ease"], **tokens.get("themes", {}).get(theme_name, {}).get("ease", {})}
    for k in _EASE_KEYS:
        nm = "".join(p.capitalize() for p in k.split("-"))
        v = ease_src.get(k, "cubic-bezier(0.2, 0, 0, 1)")
        lines.append(f"  ease{nm}: {css_curve_to_dart(v)},")
    # Typography (Task 7 fills real TextStyle — Task 6 emits TextStyle() placeholders).
    for k in _TYPE_ROLES:
        name = "type" + dart_field_name(k).capitalize()
        lines.append(f"  {name}: const TextStyle(),")
    # Font families — Task 8 wires real values per theme; Task 6 uses Inter as a safe placeholder.
    fam_display = "Inter"
    fam_text = "Inter"
    fam_mono = "JetBrainsMono"
    if theme_name.startswith("clay"):
        fam_display = fam_text = "Lora"
    elif theme_name.startswith("notion"):
        fam_display = fam_text = "iAWriterQuattroS"
        fam_mono = "iAWriterMonoS"
    lines.append(f"  fontDisplay: {fam_display!r},")
    lines.append(f"  fontText: {fam_text!r},")
    lines.append(f"  fontMono: {fam_mono!r},")
    lines.append(");")
    return "\n".join(lines)


def _emit_lookups() -> str:
    cases = "\n".join(
        f"    case {n!r}: return _build{_theme_camel(n)}Tokens();"
        for n in _THEME_NAMES
    )
    theme_data_cases = "\n".join(
        f"    case {n!r}: return _buildThemeData({n!r}, _build{_theme_camel(n)}Tokens(), brightness: Brightness.{'dark' if (n == 'dark' or n.endswith('-dark')) else 'light'});"
        for n in _THEME_NAMES
    )
    return f"""
AppTokens appTokensFor(String name) {{
  switch (name) {{
{cases}
    default:
      assert(() {{ debugPrint('appTokensFor: unknown theme \\$name — using light'); return true; }}());
      return _buildLightTokens();
  }}
}}

ThemeData appThemeDataFor(String name) {{
  switch (name) {{
{theme_data_cases}
    default:
      return _buildThemeData('light', _buildLightTokens(), brightness: Brightness.light);
  }}
}}

ThemeData _buildThemeData(String name, AppTokens t, {{required Brightness brightness}}) {{
  final colorScheme = ColorScheme(
    brightness: brightness,
    primary: t.brand,
    onPrimary: t.brandContrast,
    secondary: t.info,
    onSecondary: t.brandContrast,
    error: t.error,
    onError: t.brandContrast,
    surface: t.surface,
    onSurface: t.textPrimary,
    background: t.bg,
    onBackground: t.textPrimary,
  );
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: t.bg,
    extensions: <ThemeExtension<dynamic>>[t],
    fontFamily: t.fontText,
  );
}}
"""


def build_dart(tokens: dict[str, Any]) -> str:
    parts = [HEADER, _emit_app_tokens_class(), ""]
    for name in _THEME_NAMES:
        parts.append(_emit_theme_constructor(name, tokens))
        parts.append("")
    parts.append(_emit_lookups())
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_build_tokens_dart_colors.py tests/test_build_tokens_dart_scalars.py tests/test_build_tokens_dart_motion.py tests/test_build_tokens_dart_shadows.py -v`
Expected: PASS.

- [ ] **Step 5: Sanity-check generated file**

Run: `python3 scripts/build_tokens.py --target dart --stdout | head -60`
Expected: well-formed Dart with `AppTokens`, six `_build<Name>Tokens`, `appTokensFor`, `appThemeDataFor`. No `MISSING token` warnings on stderr.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_colors.py
git commit -m "feat(tokens): dart emitter — AppTokens class + 6-theme constructors + lookups"
```

### Task 7: TextStyle emission + per-field `lerp`

**Files:**
- Modify: `scripts/build_tokens_dart.py`
- Test: `tests/test_build_tokens_dart_typography.py` (new)
- Test: `tests/test_build_tokens_dart_lerp.py` (new)

- [ ] **Step 1: Write failing typography test**

Create `tests/test_build_tokens_dart_typography.py`:

```python
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
```

- [ ] **Step 2: Write failing lerp test**

Create `tests/test_build_tokens_dart_lerp.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_build_tokens_dart_typography.py tests/test_build_tokens_dart_lerp.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement TextStyle emission**

In `scripts/build_tokens_dart.py`, replace the placeholder typography loop inside `_emit_theme_constructor` with real `TextStyle` emission. Add a helper:

```python
def _dartify_tracking(value: str) -> str:
    """Convert e.g. '-0.374px' → '-0.374'. Bare '0' → '0.0'."""
    v = value.strip()
    if v == "0":
        return "0.0"
    m = re.match(r"^(-?[0-9.]+)px$", v)
    if not m:
        raise ValueError(f"cannot parse tracking: {value!r}")
    f = float(m.group(1))
    return f"{f}"


def _emit_text_style(role: str, scale_entry: dict, font_family: str, tracking_override: str | None) -> str:
    size_rem = scale_entry["size"]
    size_dart = css_scalar_to_dart(size_rem)
    weight = scale_entry["weight"]
    lh = scale_entry["lh"]
    tracking = tracking_override if tracking_override is not None else scale_entry["tracking"]
    return (
        f"const TextStyle(fontSize: {size_dart}, "
        f"fontWeight: FontWeight.w{weight}, "
        f"letterSpacing: {_dartify_tracking(tracking)}, "
        f"height: {lh}, "
        f"fontFamily: {font_family!r})"
    )
```

Then in `_emit_theme_constructor`, replace the typography loop:

```python
    # Typography
    scale = tokens["typography"]["scale"]
    tracking_overrides = tokens.get("themes", {}).get(theme_name, {}).get("typography-tracking", {})
    for k in _TYPE_ROLES:
        name = "type" + dart_field_name(k).capitalize()
        family = fam_display if k in ("hero", "4xl", "3xl", "2xl", "xl") else fam_text
        if k == "nano":
            family = fam_text
        ts = _emit_text_style(k, scale[k], family, tracking_overrides.get(k))
        lines.append(f"  {name}: {ts},")
```

Remove the `const TextStyle()` placeholders. Also remove `const ` prefix from any line that contains `TextStyle(fontFamily: ...` if the family is dynamic; the helper returns `const TextStyle(...)` and that is fine because fontFamily is a `String` literal at codegen time.

- [ ] **Step 5: Implement per-field lerp**

Replace `_emit_app_tokens_class` so that the `lerp` method interpolates every field. The cleanest path is to construct the lerp body from the same field schema:

```python
def _emit_app_tokens_class() -> str:
    # Build field declarations and a flat list of (kind, name) for ctor + lerp.
    decls: list[str] = []
    field_kinds: list[tuple[str, str]] = []  # (kind, name)
    for _, name in _COLOR_FIELDS:
        decls.append(f"  final Color {name};")
        field_kinds.append(("color", name))
    for k in _SPACE_KEYS:
        n = "space" + dart_field_name(k).lstrip("v")
        decls.append(f"  final double {n};")
        field_kinds.append(("double", n))
    for k in _RADIUS_KEYS:
        n = "radius" + dart_field_name(k).capitalize()
        decls.append(f"  final double {n};")
        field_kinds.append(("double", n))
    for k in _STROKE_KEYS:
        n = "stroke" + dart_field_name(k).lstrip("v")
        decls.append(f"  final double {n};")
        field_kinds.append(("double", n))
    for k in _SHADOW_KEYS:
        n = "shadow" + dart_field_name(k).lstrip("v")
        decls.append(f"  final List<BoxShadow> {n};")
        field_kinds.append(("shadows", n))
    for k in _DURATION_KEYS:
        n = "duration" + k.capitalize()
        decls.append(f"  final Duration {n};")
        field_kinds.append(("duration", n))
    for k in _EASE_KEYS:
        nm = "".join(p.capitalize() for p in k.split("-"))
        n = "ease" + nm
        decls.append(f"  final Curve {n};")
        field_kinds.append(("snap", n))
    for k in _TYPE_ROLES:
        n = "type" + dart_field_name(k).capitalize()
        decls.append(f"  final TextStyle {n};")
        field_kinds.append(("textstyle", n))
    decls.append("  final String fontDisplay;")
    decls.append("  final String fontText;")
    decls.append("  final String fontMono;")
    for n in ("fontDisplay", "fontText", "fontMono"):
        field_kinds.append(("snap", n))

    ctor_params = ",\n".join(f"    required this.{kn[1]}" for kn in field_kinds)

    lerp_lines = []
    for kind, n in field_kinds:
        if kind == "color":
            lerp_lines.append(f"      {n}: Color.lerp({n}, other.{n}, t)!,")
        elif kind == "double":
            lerp_lines.append(f"      {n}: lerpDouble({n}, other.{n}, t)!,")
        elif kind == "duration":
            lerp_lines.append(
                f"      {n}: Duration(milliseconds: lerpDouble({n}.inMilliseconds.toDouble(), other.{n}.inMilliseconds.toDouble(), t)!.round()),"
            )
        elif kind == "shadows":
            lerp_lines.append(f"      {n}: BoxShadow.lerpList({n}, other.{n}, t)!,")
        elif kind == "textstyle":
            lerp_lines.append(f"      {n}: TextStyle.lerp({n}, other.{n}, t)!,")
        elif kind == "snap":
            lerp_lines.append(f"      {n}: t < 0.5 ? {n} : other.{n},")
        else:
            raise AssertionError(kind)

    return (
        "class AppTokens extends ThemeExtension<AppTokens> {\n"
        + "\n".join(decls)
        + "\n\n  const AppTokens({\n" + ctor_params + ",\n  });\n\n"
        + "  @override\n  AppTokens copyWith() => this;\n\n"
        + "  @override\n  AppTokens lerp(ThemeExtension<AppTokens>? other, double t) {\n"
        + "    if (other is! AppTokens) return this;\n"
        + "    return AppTokens(\n"
        + "\n".join(lerp_lines) + "\n"
        + "    );\n  }\n}\n"
    )
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_build_tokens_dart_typography.py tests/test_build_tokens_dart_lerp.py tests/test_build_tokens_dart_colors.py tests/test_build_tokens_dart_scalars.py tests/test_build_tokens_dart_motion.py tests/test_build_tokens_dart_shadows.py -v`
Expected: PASS.

- [ ] **Step 7: Generated file syntactic sanity check**

Run: `python3 scripts/build_tokens.py --target dart --out /tmp/tokens.generated.dart && head -120 /tmp/tokens.generated.dart`
Expected: 6 theme constructors, no obvious syntax errors. Discard `/tmp/tokens.generated.dart`.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_tokens_dart.py tests/test_build_tokens_dart_typography.py tests/test_build_tokens_dart_lerp.py
git commit -m "feat(tokens): dart emitter — TextStyle per role + per-field lerp"
```

### Task 8: Font sidecar (`tool/fonts.generated.yaml`)

**Files:**
- Modify: `scripts/build_tokens_dart.py` (add side-effect output)
- Create: `tests/test_build_tokens_fonts.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_build_tokens_fonts.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build_tokens_fonts.py -v`
Expected: FAIL — `--fonts-out` not recognised.

- [ ] **Step 3: Implement `--fonts-out` and sidecar generation**

In `scripts/build_tokens.py` add to the argparse:

```python
    p.add_argument("--fonts-out", type=Path, default=None,
                   help="output yaml sidecar (default: tool/fonts.generated.yaml)")
```

At top of file, add:

```python
DEFAULT_OUTPUT_FONTS = REPO_ROOT / "tool" / "fonts.generated.yaml"
```

In `_emit_target`, after writing the Dart file, also emit the sidecar:

```python
    if target == "dart":
        from build_tokens_dart import build_fonts_yaml
        fonts_yaml = build_fonts_yaml()
        fonts_out = args.fonts_out or DEFAULT_OUTPUT_FONTS
        fonts_out.parent.mkdir(parents=True, exist_ok=True)
        fonts_out.write_text(fonts_yaml)
        print(f"wrote {fonts_out} ({len(fonts_yaml):,} bytes)")
```

In `scripts/build_tokens_dart.py` add:

```python
_FONT_FAMILIES = [
    ("Inter", "Inter", [
        ("Regular", 400, None),
        ("Medium", 500, None),
        ("SemiBold", 600, None),
        ("Bold", 700, None),
    ]),
    ("Lora", "Lora", [
        ("Regular", 400, None),
        ("Medium", 500, None),
        ("SemiBold", 600, None),
        ("Bold", 700, None),
    ]),
    ("iAWriterQuattroS", "iAWriterQuattroS", [
        ("Regular", 400, None),
        ("Italic", 400, "italic"),
        ("Bold", 700, None),
        ("BoldItalic", 700, "italic"),
    ]),
    ("iAWriterMonoS", "iAWriterMonoS", [
        ("Regular", 400, None),
        ("Bold", 700, None),
    ]),
    ("JetBrainsMono", "JetBrainsMono", [
        ("Regular", 400, None),
        ("Bold", 700, None),
    ]),
]


def build_fonts_yaml() -> str:
    lines = [
        "# AUTO-GENERATED — do not edit.",
        "# Source: design/design-tokens.json + scripts/build_tokens_dart.py",
        "flutter:",
        "  fonts:",
    ]
    for family, prefix, variants in _FONT_FAMILIES:
        lines.append(f"    - family: {family}")
        lines.append("      fonts:")
        for suffix, weight, style in variants:
            lines.append(f"        - asset: assets/fonts/{prefix}-{suffix}.ttf")
            if weight != 400:
                lines.append(f"          weight: {weight}")
            if style:
                lines.append(f"          style: {style}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_build_tokens_fonts.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the real sidecar file**

Run: `python3 scripts/build_tokens.py --target dart --out /tmp/discard.dart`
Expected: writes `tool/fonts.generated.yaml`. Inspect it briefly.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_tokens.py scripts/build_tokens_dart.py tests/test_build_tokens_fonts.py tool/fonts.generated.yaml
git commit -m "feat(tokens): emit tool/fonts.generated.yaml sidecar alongside Dart"
```

### Task 9: `merge_fonts_into_pubspec.py`

**Files:**
- Create: `scripts/merge_fonts_into_pubspec.py`
- Test: `tests/test_merge_fonts_into_pubspec.py` (new)

- [ ] **Step 1: Add Python dep**

Run: `pip install ruamel.yaml` (or add to `requirements.txt`).

Edit `requirements.txt`, append:
```
ruamel.yaml>=0.18.0
```

Verify: `pip install -r requirements.txt`.

- [ ] **Step 2: Write failing test**

Create `tests/test_merge_fonts_into_pubspec.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_merge_fonts_into_pubspec.py -v`
Expected: FAIL — script doesn't exist.

- [ ] **Step 4: Implement**

Create `scripts/merge_fonts_into_pubspec.py`:

```python
#!/usr/bin/env python3
"""Replace the `flutter.fonts` block of pubspec.yaml from tool/fonts.generated.yaml.

Preserves all other keys, comments, and ordering. Idempotent.

Usage:
    python3 scripts/merge_fonts_into_pubspec.py
    python3 scripts/merge_fonts_into_pubspec.py --pubspec custom.yaml --fonts custom.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBSPEC = REPO_ROOT / "pubspec.yaml"
DEFAULT_FONTS = REPO_ROOT / "tool" / "fonts.generated.yaml"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pubspec", type=Path, default=DEFAULT_PUBSPEC)
    p.add_argument("--fonts", type=Path, default=DEFAULT_FONTS)
    args = p.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if not args.pubspec.exists():
        print(f"error: {args.pubspec} not found", file=sys.stderr)
        return 1
    if not args.fonts.exists():
        print(f"error: {args.fonts} not found", file=sys.stderr)
        return 1

    pubspec = yaml.load(args.pubspec)
    fonts = yaml.load(args.fonts)

    flutter_block = pubspec.get("flutter")
    if flutter_block is None:
        pubspec["flutter"] = {}
        flutter_block = pubspec["flutter"]

    new_fonts = fonts["flutter"]["fonts"]
    flutter_block["fonts"] = new_fonts

    with args.pubspec.open("w") as f:
        yaml.dump(pubspec, f)
    print(f"merged {args.fonts} → {args.pubspec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test**

Run: `pytest tests/test_merge_fonts_into_pubspec.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/merge_fonts_into_pubspec.py tests/test_merge_fonts_into_pubspec.py requirements.txt
git commit -m "feat(tokens): script to merge generated fonts block into pubspec.yaml"
```

### Task 10: Makefile targets

**Files:**
- Modify: `Makefile` (create if absent at repo root)

- [ ] **Step 1: Inspect existing Makefile if present**

Run: `ls Makefile 2>/dev/null && head -40 Makefile || echo "no Makefile"`

- [ ] **Step 2: Add or create targets**

If `Makefile` exists, append. Otherwise create with this content:

```makefile
.PHONY: tokens tokens-check fonts

# Regenerate all token artefacts (CSS, Dart, fonts sidecar, pubspec fonts block).
tokens:
	python3 scripts/build_tokens.py --target all
	python3 scripts/merge_fonts_into_pubspec.py

# CI gate: regenerate, then assert nothing changed.
tokens-check: tokens
	git diff --exit-code -- \
	  src/frontend/styles/tokens.generated.css \
	  lib/app/theme/tokens.generated.dart \
	  tool/fonts.generated.yaml \
	  pubspec.yaml

# Just merge fonts (use when only fonts.generated.yaml changed).
fonts:
	python3 scripts/merge_fonts_into_pubspec.py
```

- [ ] **Step 3: Verify clean run**

Run: `make tokens && git status --short -- src/frontend/styles/tokens.generated.css lib/app/theme/tokens.generated.dart tool/fonts.generated.yaml pubspec.yaml`
Expected: at this point `lib/app/theme/tokens.generated.dart` is a new file (Phase A first generation); commit it.

- [ ] **Step 4: Commit Makefile + generated Dart file + updated pubspec**

```bash
git add Makefile lib/app/theme/tokens.generated.dart pubspec.yaml tool/fonts.generated.yaml
git commit -m "build(tokens): Makefile targets tokens / tokens-check / fonts"
```

---

## Phase B — Dart consumption layer

### Task 11: `BuildContext` token extension

**Files:**
- Create: `lib/app/theme/build_context_x.dart`
- Test: `test/app/theme/build_context_x_test.dart` (new)

- [ ] **Step 1: Write failing widget test**

Create `test/app/theme/build_context_x_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:localocr_extended/app/theme/tokens.generated.dart';
import 'package:localocr_extended/app/theme/build_context_x.dart';

void main() {
  testWidgets('context.tok returns AppTokens for current theme', (tester) async {
    AppTokens? captured;
    await tester.pumpWidget(MaterialApp(
      theme: appThemeDataFor('light'),
      home: Builder(builder: (ctx) {
        captured = ctx.tok;
        return const SizedBox.shrink();
      }),
    ));
    expect(captured, isNotNull);
    expect(captured!.brand, const Color(0xFF0071E3));
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/app/theme/build_context_x_test.dart`
Expected: FAIL — `build_context_x.dart` not found.

- [ ] **Step 3: Implement extension**

Create `lib/app/theme/build_context_x.dart`:

```dart
import 'package:flutter/material.dart';
import 'tokens.generated.dart';

extension AppTokensX on BuildContext {
  AppTokens get tok => Theme.of(this).extension<AppTokens>()!;
}
```

- [ ] **Step 4: Run test**

Run: `flutter test test/app/theme/build_context_x_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/app/theme/build_context_x.dart test/app/theme/build_context_x_test.dart
git commit -m "feat(theme): context.tok extension for AppTokens access"
```

### Task 12: Slim `theme.dart` rewrite

**Files:**
- Modify: `lib/app/theme/theme.dart`
- Test: `test/app/theme/theme_cycle_test.dart` (new)

- [ ] **Step 1: Write failing test**

Create `test/app/theme/theme_cycle_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:localocr_extended/app/theme/theme.dart';

void main() {
  test('themeCycle has all 6 themes', () {
    expect(themeCycle, [
      'light', 'dark', 'clay', 'clay-dark', 'notion', 'notion-dark',
    ]);
  });

  test('nextTheme wraps around', () {
    expect(nextTheme('light'), 'dark');
    expect(nextTheme('notion-dark'), 'light');
  });

  test('nextTheme(unknown) returns first', () {
    expect(nextTheme('asdf'), 'light');
  });
}
```

- [ ] **Step 2: Run test**

Run: `flutter test test/app/theme/theme_cycle_test.dart`
Expected: PASS (existing `theme.dart:31-55` already has this logic).

- [ ] **Step 3: Replace `theme.dart` with slim version**

Replace `lib/app/theme/theme.dart` contents entirely with:

```dart
import 'package:flutter/material.dart';

export 'tokens.generated.dart';

const themeCycle = <String>[
  'light',
  'dark',
  'clay',
  'clay-dark',
  'notion',
  'notion-dark',
];

String nextTheme(String current) {
  final i = themeCycle.indexOf(current);
  if (i < 0) return themeCycle.first;
  return themeCycle[(i + 1) % themeCycle.length];
}
```

This deletes `AppTheme` (light/dark static factories) and `themeModeFor`. Any caller of these will fail at compile time — we will fix call sites in Phase E.

- [ ] **Step 4: Run cycle test**

Run: `flutter test test/app/theme/theme_cycle_test.dart`
Expected: PASS.

- [ ] **Step 5: Try to build the app to surface broken callers (do not fix yet)**

Run: `flutter analyze lib/app/theme/`
Expected: clean for theme/ folder. Run `flutter analyze lib/` to enumerate broken callers (likely in `lib/main.dart` and `lib/app/app.dart`).

Note: the broken callers from `AppTheme.light()` and `themeModeFor` will be fixed in Task 14.

- [ ] **Step 6: Commit**

```bash
git add lib/app/theme/theme.dart test/app/theme/theme_cycle_test.dart
git commit -m "refactor(theme): slim theme.dart; export generated tokens; drop AppTheme stub"
```

### Task 13: Riverpod-async theme provider

**Files:**
- Modify: `lib/app/theme/theme_provider.dart`
- Modify: `pubspec.yaml` (ensure `shared_preferences`, `flutter_riverpod`, `riverpod_annotation`, dev `riverpod_generator`, `build_runner`)
- Test: `test/app/theme/theme_provider_test.dart` (new)

- [ ] **Step 1: Verify pubspec deps**

Run: `grep -n "riverpod\|shared_preferences" pubspec.yaml`
Expected: existing entries. If `riverpod_annotation` or `riverpod_generator` absent, append under `dependencies:` / `dev_dependencies:`:

```yaml
dependencies:
  flutter_riverpod: ^2.5.1
  riverpod_annotation: ^2.3.5
  shared_preferences: ^2.2.0

dev_dependencies:
  build_runner: ^2.4.9
  riverpod_generator: ^2.4.0
```

- [ ] **Step 2: Write failing test**

Create `test/app/theme/theme_provider_test.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:localocr_extended/app/theme/theme_provider.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('default state is light', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final value = await container.read(themeNameNotifierProvider.future);
    expect(value, 'light');
  });

  test('set persists and updates state', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await container.read(themeNameNotifierProvider.future);
    await container.read(themeNameNotifierProvider.notifier).set('clay');
    expect(container.read(themeNameNotifierProvider).valueOrNull, 'clay');
    final p = await SharedPreferences.getInstance();
    expect(p.getString('theme'), 'clay');
  });

  test('next() advances cycle', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await container.read(themeNameNotifierProvider.future);
    final notifier = container.read(themeNameNotifierProvider.notifier);
    await notifier.next();
    expect(container.read(themeNameNotifierProvider).valueOrNull, 'dark');
    await notifier.next();
    expect(container.read(themeNameNotifierProvider).valueOrNull, 'clay');
  });
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `flutter test test/app/theme/theme_provider_test.dart`
Expected: FAIL — provider not in that shape.

- [ ] **Step 4: Replace provider**

Replace `lib/app/theme/theme_provider.dart` contents:

```dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'theme.dart';

part 'theme_provider.g.dart';

@riverpod
class ThemeNameNotifier extends _$ThemeNameNotifier {
  static const _key = 'theme';
  static const _default = 'light';

  @override
  Future<String> build() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_key) ?? _default;
  }

  Future<void> set(String name) async {
    state = AsyncData(name);
    final p = await SharedPreferences.getInstance();
    await p.setString(_key, name);
  }

  Future<void> next() async {
    final current = state.valueOrNull ?? _default;
    await set(nextTheme(current));
  }
}
```

- [ ] **Step 5: Run codegen**

Run: `dart run build_runner build --delete-conflicting-outputs`
Expected: `theme_provider.g.dart` generated.

- [ ] **Step 6: Run test**

Run: `flutter test test/app/theme/theme_provider_test.dart`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/app/theme/theme_provider.dart lib/app/theme/theme_provider.g.dart test/app/theme/theme_provider_test.dart pubspec.yaml pubspec.lock
git commit -m "refactor(theme): async Riverpod theme provider backed by SharedPreferences"
```

### Task 14: Wire `MaterialApp` to use `appThemeDataFor`

**Files:**
- Modify: `lib/main.dart`
- Modify: `lib/app/app.dart` (or wherever `MaterialApp.router` lives)

- [ ] **Step 1: Identify the MaterialApp call site**

Run: `grep -rn "MaterialApp" lib/main.dart lib/app/app.dart 2>/dev/null`
Expected: find the existing `theme:` / `darkTheme:` / `themeMode:` triplet wired to `AppTheme.light()` / `AppTheme.dark()` / `themeModeFor(...)`.

- [ ] **Step 2: Replace wiring**

In the file containing `MaterialApp.router(...)`, modify the relevant arguments:

```dart
// before:
//   theme: AppTheme.light(),
//   darkTheme: AppTheme.dark(),
//   themeMode: themeModeFor(themeName),

// after:
final themeAsync = ref.watch(themeNameNotifierProvider);
final themeName = themeAsync.valueOrNull ?? 'light';
return MaterialApp.router(
  theme: appThemeDataFor(themeName),
  // darkTheme intentionally omitted: brightness is baked into the named theme.
  // themeMode intentionally omitted: user picks explicit theme via cycle.
  routerConfig: routerConfig,
  // ... rest unchanged
);
```

- [ ] **Step 3: Bootstrap SharedPreferences sync to avoid first-frame flash**

In `lib/main.dart`:

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final initialTheme = prefs.getString('theme') ?? 'light';
  runApp(ProviderScope(
    overrides: [
      themeNameNotifierProvider.overrideWith(
        () => ThemeNameNotifier()..state = AsyncData(initialTheme),
      ),
    ],
    child: const LocalOcrApp(),
  ));
}
```

- [ ] **Step 4: Verify analyze**

Run: `flutter analyze lib/`
Expected: no errors related to AppTheme/themeModeFor (those callers are now fixed). Errors related to forbidden literals in features come later in Phase E.

- [ ] **Step 5: Smoke-test app launch**

Run: `flutter run -d <android-emulator-id>` (or `flutter run -d chrome` if no emulator handy).
Expected: app launches; theme cycle button cycles through 6 themes, each visually distinct (colors, shadows, durations differ).

- [ ] **Step 6: Commit**

```bash
git add lib/main.dart lib/app/app.dart
git commit -m "refactor(theme): wire MaterialApp to appThemeDataFor, no system override"
```

---

## Phase C — Fonts & licenses

### Task 15: Add font files (subset) and licenses

**Files:**
- Create: `assets/fonts/Inter-{Regular,Medium,SemiBold,Bold}.ttf`
- Create: `assets/fonts/Lora-{Regular,Medium,SemiBold,Bold}.ttf`
- Create: `assets/fonts/iAWriterQuattroS-{Regular,Italic,Bold,BoldItalic}.ttf`
- Create: `assets/fonts/iAWriterMonoS-{Regular,Bold}.ttf`
- Create: `assets/fonts/JetBrainsMono-{Regular,Bold}.ttf`
- Create: `assets/fonts/LICENSES/{Inter,Lora,iAWriter,JetBrainsMono}-OFL.txt`
- Create: `tool/subset_fonts.sh`

- [ ] **Step 1: Install `fonttools`**

Run: `pip install fonttools`. Append to `requirements.txt` if not already pinned:

```
fonttools>=4.50.0
```

- [ ] **Step 2: Download sources**

Sources (all permissive SIL OFL):
- Inter: https://github.com/rsms/inter/releases (latest, e.g. v4.0)
- Lora: https://github.com/cyrealtype/Lora-Cyrillic/releases (v3.0+)
- iA Writer: https://github.com/iaolo/iA-Fonts (mirror)
- JetBrains Mono: https://github.com/JetBrains/JetBrainsMono/releases

Place raw `.ttf` files in `vendor/fonts/raw/` (not committed; gitignored).

Append to `.gitignore`:
```
vendor/fonts/raw/
```

- [ ] **Step 3: Create subsetting script**

Create `tool/subset_fonts.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Subset to Latin + Latin-Extended + common symbols + currency.
UNICODES="U+0000-024F,U+1E00-1EFF,U+2000-206F,U+2070-209F,U+20A0-20CF,U+2100-214F"

RAW=vendor/fonts/raw
OUT=assets/fonts
mkdir -p "$OUT"

subset() {
  local in_path=$1
  local out_name=$2
  pyftsubset "$in_path" \
    --unicodes="$UNICODES" \
    --layout-features='*' \
    --no-hinting \
    --output-file="$OUT/$out_name"
  echo "subset $in_path → $OUT/$out_name ($(stat -f%z "$OUT/$out_name") bytes)"
}

subset "$RAW/Inter-Regular.ttf"   Inter-Regular.ttf
subset "$RAW/Inter-Medium.ttf"    Inter-Medium.ttf
subset "$RAW/Inter-SemiBold.ttf"  Inter-SemiBold.ttf
subset "$RAW/Inter-Bold.ttf"      Inter-Bold.ttf

subset "$RAW/Lora-Regular.ttf"    Lora-Regular.ttf
subset "$RAW/Lora-Medium.ttf"     Lora-Medium.ttf
subset "$RAW/Lora-SemiBold.ttf"   Lora-SemiBold.ttf
subset "$RAW/Lora-Bold.ttf"       Lora-Bold.ttf

subset "$RAW/iAWriterQuattroS-Regular.ttf"     iAWriterQuattroS-Regular.ttf
subset "$RAW/iAWriterQuattroS-Italic.ttf"      iAWriterQuattroS-Italic.ttf
subset "$RAW/iAWriterQuattroS-Bold.ttf"        iAWriterQuattroS-Bold.ttf
subset "$RAW/iAWriterQuattroS-BoldItalic.ttf"  iAWriterQuattroS-BoldItalic.ttf

subset "$RAW/iAWriterMonoS-Regular.ttf"  iAWriterMonoS-Regular.ttf
subset "$RAW/iAWriterMonoS-Bold.ttf"     iAWriterMonoS-Bold.ttf

subset "$RAW/JetBrainsMono-Regular.ttf"  JetBrainsMono-Regular.ttf
subset "$RAW/JetBrainsMono-Bold.ttf"     JetBrainsMono-Bold.ttf
```

- [ ] **Step 4: Run subset**

```bash
chmod +x tool/subset_fonts.sh
./tool/subset_fonts.sh
du -sh assets/fonts/
```

Expected: total `assets/fonts/` < 700KB. If above, tighten the unicode range or strip more features.

- [ ] **Step 5: Copy license files**

For each upstream, copy its `LICENSE.txt` (SIL OFL 1.1) into `assets/fonts/LICENSES/<Family>-OFL.txt`. Naming:
- `assets/fonts/LICENSES/Inter-OFL.txt`
- `assets/fonts/LICENSES/Lora-OFL.txt`
- `assets/fonts/LICENSES/iAWriter-OFL.txt`
- `assets/fonts/LICENSES/JetBrainsMono-OFL.txt`

- [ ] **Step 6: Verify**

Run: `ls assets/fonts/ && ls assets/fonts/LICENSES/`
Expected: 16 .ttf files + 4 license files.

- [ ] **Step 7: Commit**

```bash
git add assets/fonts/ tool/subset_fonts.sh .gitignore requirements.txt
git commit -m "feat(fonts): bundle subset Inter/Lora/iAWriter/JetBrainsMono + OFL licenses"
```

### Task 16: Register fonts with `LicenseRegistry`

**Files:**
- Modify: `lib/main.dart`
- Create: `lib/app/theme/font_licenses.dart`

- [ ] **Step 1: Implement license loader**

Create `lib/app/theme/font_licenses.dart`:

```dart
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

void registerFontLicenses() {
  LicenseRegistry.addLicense(() async* {
    for (final entry in const [
      ('Inter', 'assets/fonts/LICENSES/Inter-OFL.txt'),
      ('Lora', 'assets/fonts/LICENSES/Lora-OFL.txt'),
      ('iA Writer Quattro / Mono', 'assets/fonts/LICENSES/iAWriter-OFL.txt'),
      ('JetBrains Mono', 'assets/fonts/LICENSES/JetBrainsMono-OFL.txt'),
    ]) {
      final body = await rootBundle.loadString(entry.$2);
      yield LicenseEntryWithLineBreaks([entry.$1], body);
    }
  });
}
```

- [ ] **Step 2: Wire into `main`**

In `lib/main.dart`, inside `main()` after `ensureInitialized()`:

```dart
registerFontLicenses();
```

Add the import.

- [ ] **Step 3: Add license assets to pubspec**

In `pubspec.yaml`, under `flutter:`, ensure `assets:` includes the licenses dir:

```yaml
flutter:
  assets:
    - assets/fonts/LICENSES/
```

- [ ] **Step 4: Verify**

Run: `flutter pub get && flutter analyze lib/main.dart lib/app/theme/font_licenses.dart`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add lib/main.dart lib/app/theme/font_licenses.dart pubspec.yaml
git commit -m "feat(fonts): register SIL OFL licenses with LicenseRegistry"
```

---

## Phase D — Custom-lint rules

### Task 17: Lint package scaffolding

**Files:**
- Create: `tool/lints/pubspec.yaml`
- Create: `tool/lints/lib/lints.dart`
- Modify: `pubspec.yaml` (add `custom_lint` dev dep + plugin reference)
- Modify: `analysis_options.yaml`

- [ ] **Step 1: Scaffold lint package**

Create directory `tool/lints/` with `pubspec.yaml`:

```yaml
name: localocr_lints
description: Custom lint rules forbidding raw literals in lib/features and lib/app.
version: 0.1.0
publish_to: none

environment:
  sdk: '>=3.5.0 <4.0.0'

dependencies:
  analyzer: ^6.4.1
  analyzer_plugin: ^0.11.3
  custom_lint_builder: ^0.6.4

dev_dependencies:
  custom_lint: ^0.6.4
```

Create `tool/lints/lib/lints.dart`:

```dart
import 'package:custom_lint_builder/custom_lint_builder.dart';

import 'rules/no_raw_colors.dart';
import 'rules/no_literal_duration.dart';
import 'rules/no_literal_curve.dart';
import 'rules/no_literal_spacing.dart';
import 'rules/no_literal_radius.dart';
import 'rules/no_literal_text_style.dart';
import 'rules/no_literal_shadow.dart';

PluginBase createPlugin() => _LocalOcrLintsPlugin();

class _LocalOcrLintsPlugin extends PluginBase {
  @override
  List<LintRule> getLintRules(CustomLintConfigs configs) => [
        NoRawColors(),
        NoLiteralDuration(),
        NoLiteralCurve(),
        NoLiteralSpacing(),
        NoLiteralRadius(),
        NoLiteralTextStyle(),
        NoLiteralShadow(),
      ];
}
```

- [ ] **Step 2: Register plugin in app pubspec**

In root `pubspec.yaml` `dev_dependencies:`:

```yaml
  custom_lint: ^0.6.4
  localocr_lints:
    path: tool/lints
```

In root `analysis_options.yaml`, add at top level (create file if missing):

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  plugins:
    - custom_lint

custom_lint:
  rules:
    - no_raw_colors
    - no_literal_duration
    - no_literal_curve
    - no_literal_spacing
    - no_literal_radius
    - no_literal_text_style
    - no_literal_shadow
```

- [ ] **Step 3: Verify scaffolding**

Run: `flutter pub get && dart pub get -C tool/lints`
Expected: both resolve. `dart run custom_lint` will still fail because rules are unimplemented stubs — that's the next task.

- [ ] **Step 4: Commit**

```bash
git add tool/lints/ pubspec.yaml pubspec.lock analysis_options.yaml
git commit -m "build(lint): scaffold custom_lint package localocr_lints"
```

### Task 18: Implement `no_raw_colors` rule

**Files:**
- Create: `tool/lints/lib/rules/no_raw_colors.dart`
- Create: `tool/lints/test/no_raw_colors_test.dart`

- [ ] **Step 1: Write failing rule test**

Lint testing uses fixture files. Create `tool/lints/test/fixtures/raw_color_violation.dart`:

```dart
import 'package:flutter/material.dart';

class Bad extends StatelessWidget {
  const Bad({super.key});
  @override
  Widget build(BuildContext context) {
    return Container(color: Colors.red);  // expect lint
  }
}

class Bad2 extends StatelessWidget {
  const Bad2({super.key});
  @override
  Widget build(BuildContext context) {
    return Container(color: const Color(0xFF112233));  // expect lint
  }
}

class Ok extends StatelessWidget {
  const Ok({super.key});
  @override
  Widget build(BuildContext context) {
    return Container(color: Colors.transparent);  // allowed
  }
}
```

Create `tool/lints/test/no_raw_colors_test.dart`:

```dart
import 'package:custom_lint_core/custom_lint_core.dart';
import 'package:test/test.dart';
import 'package:localocr_lints/rules/no_raw_colors.dart';

import 'helpers/run_lint.dart';

void main() {
  test('flags Colors.X and Color(0xFF...) but not transparent', () async {
    final results = await runLint(
      rule: NoRawColors(),
      filePath: 'test/fixtures/raw_color_violation.dart',
    );
    expect(results.length, 2);
    expect(results[0].message, contains('raw color'));
  });
}
```

You will also need a helper that wraps `custom_lint`'s test harness — see `package:custom_lint_core/test_helpers.dart` docs. Create `tool/lints/test/helpers/run_lint.dart` per that API. (If your custom_lint version exposes a simpler `testLint` API, prefer it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tool/lints && dart test test/no_raw_colors_test.dart`
Expected: FAIL — `rules/no_raw_colors.dart` doesn't exist.

- [ ] **Step 3: Implement rule**

Create `tool/lints/lib/rules/no_raw_colors.dart`:

```dart
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoRawColors extends DartLintRule {
  NoRawColors() : super(code: _code);

  static const _code = LintCode(
    name: 'no_raw_colors',
    problemMessage: 'Raw color literal forbidden — use context.tok.<role> or a ColorScheme slot.',
    correctionMessage: 'Replace with context.tok.brand etc., or annotate with // ignore: no_raw_colors + WHY: reason.',
    errorSeverity: ErrorSeverity.ERROR,
  );

  // Only flag in feature/app code, not theme/test/generated.
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart')) return false;
    if (path.endsWith('.freezed.dart')) return false;
    if (path.endsWith('.generated.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }

  @override
  void run(CustomLintResolver resolver, ErrorReporter reporter, CustomLintContext ctx) {
    final path = resolver.path;
    if (!_appliesTo(path)) return;

    ctx.registry.addPrefixedIdentifier((node) {
      // Match `Colors.<member>`. Allowlist: transparent.
      if (node.prefix.name == 'Colors' && node.identifier.name != 'transparent') {
        reporter.atNode(node, _code);
      }
    });

    ctx.registry.addInstanceCreationExpression((node) {
      // Match `Color(0xFF...)` and `Color.fromRGBO(...)` and `Color.fromARGB(...)`.
      final typeName = node.constructorName.type.element?.name;
      if (typeName == 'Color') {
        reporter.atNode(node, _code);
      }
    });
  }
}
```

- [ ] **Step 4: Run rule test**

Run: `cd tool/lints && dart test test/no_raw_colors_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/lints/lib/rules/no_raw_colors.dart tool/lints/test/
git commit -m "feat(lint): no_raw_colors rule for lib/features + lib/app"
```

### Task 19: Remaining 6 lint rules

Each rule follows the same shape as Task 18: fixture → failing test → implementation → passing test → commit.

For each rule, add a fixture file under `tool/lints/test/fixtures/` and a test file under `tool/lints/test/`. The rule files go in `tool/lints/lib/rules/`. The fixture/test pattern from Task 18 is the template — repeat it.

- [ ] **Step 1: `no_literal_duration`**

Match: `Duration(milliseconds: N)`, `Duration(seconds: N)`, etc., where the argument is an `IntegerLiteral` (not a variable / property access).
Allow: `Duration.zero`.
Detection: instance creation of `Duration` with all named args being integer literals.

```dart
// tool/lints/lib/rules/no_literal_duration.dart
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralDuration extends DartLintRule {
  NoLiteralDuration() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_duration',
    problemMessage: 'Literal Duration forbidden — use context.tok.duration<Role>.',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addInstanceCreationExpression((node) {
      if (node.constructorName.type.element?.name != 'Duration') return;
      final allLiteral = node.argumentList.arguments.every((a) {
        return a is IntegerLiteral || (a is NamedExpression && a.expression is IntegerLiteral);
      });
      if (allLiteral && node.argumentList.arguments.isNotEmpty) {
        reporter.atNode(node, _code);
      }
    });
  }
}
```

- [ ] **Step 2: `no_literal_curve`**

Match: `Curves.<X>`. Detection: prefixed identifier where prefix is `Curves`.

```dart
// tool/lints/lib/rules/no_literal_curve.dart
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralCurve extends DartLintRule {
  NoLiteralCurve() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_curve',
    problemMessage: 'Literal Curves.X forbidden — use context.tok.ease<Role>.',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addPrefixedIdentifier((node) {
      if (node.prefix.name == 'Curves') reporter.atNode(node, _code);
    });
  }
}
```

- [ ] **Step 3: `no_literal_spacing`**

Match: `EdgeInsets.all(N)`, `EdgeInsets.symmetric(...)`, `EdgeInsets.only(...)`, `EdgeInsets.fromLTRB(...)` where any argument is a numeric literal.

```dart
// tool/lints/lib/rules/no_literal_spacing.dart
import 'package:analyzer/ast/ast.dart';
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralSpacing extends DartLintRule {
  NoLiteralSpacing() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_spacing',
    problemMessage: 'Literal EdgeInsets / spacing forbidden — use context.tok.space<N>.',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  bool _allLiteral(NodeList<Expression> args) {
    return args.every((a) {
      final inner = a is NamedExpression ? a.expression : a;
      return inner is DoubleLiteral || inner is IntegerLiteral;
    });
  }
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addInstanceCreationExpression((node) {
      final t = node.constructorName.type.element?.name;
      if (t == 'EdgeInsets' || t == 'EdgeInsetsDirectional') {
        if (_allLiteral(node.argumentList.arguments) && node.argumentList.arguments.isNotEmpty) {
          reporter.atNode(node, _code);
        }
      }
    });
  }
}
```

- [ ] **Step 4: `no_literal_radius`**

Match: `BorderRadius.circular(N)`, `BorderRadius.all(Radius.circular(N))`, `Radius.circular(N)` when N is numeric literal.

```dart
// tool/lints/lib/rules/no_literal_radius.dart
import 'package:analyzer/ast/ast.dart';
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralRadius extends DartLintRule {
  NoLiteralRadius() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_radius',
    problemMessage: 'Literal BorderRadius / Radius forbidden — use context.tok.radius<Role>.',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addMethodInvocation((node) {
      final target = node.target?.toSource();
      if (target == 'BorderRadius' || target == 'Radius') {
        final allLit = node.argumentList.arguments.every((a) =>
          a is DoubleLiteral || a is IntegerLiteral);
        if (allLit && node.argumentList.arguments.isNotEmpty) {
          reporter.atNode(node, _code);
        }
      }
    });
  }
}
```

- [ ] **Step 5: `no_literal_text_style`**

Match: `TextStyle(...)` construction with any of `fontSize`, `fontWeight`, `letterSpacing`, `height` as named args.

```dart
// tool/lints/lib/rules/no_literal_text_style.dart
import 'package:analyzer/ast/ast.dart';
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralTextStyle extends DartLintRule {
  NoLiteralTextStyle() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_text_style',
    problemMessage: 'Literal TextStyle font config forbidden — use context.tok.type<Role>.copyWith(...).',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  static const _forbidden = {'fontSize', 'fontWeight', 'letterSpacing', 'height'};
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addInstanceCreationExpression((node) {
      if (node.constructorName.type.element?.name != 'TextStyle') return;
      final names = node.argumentList.arguments
          .whereType<NamedExpression>()
          .map((e) => e.name.label.name)
          .toSet();
      if (names.intersection(_forbidden).isNotEmpty) {
        reporter.atNode(node, _code);
      }
    });
  }
}
```

- [ ] **Step 6: `no_literal_shadow`**

Match: `BoxShadow(...)` constructor.

```dart
// tool/lints/lib/rules/no_literal_shadow.dart
import 'package:analyzer/error/error.dart';
import 'package:analyzer/error/listener.dart';
import 'package:custom_lint_builder/custom_lint_builder.dart';

class NoLiteralShadow extends DartLintRule {
  NoLiteralShadow() : super(code: _code);
  static const _code = LintCode(
    name: 'no_literal_shadow',
    problemMessage: 'Literal BoxShadow forbidden — use context.tok.shadow<N>.',
    errorSeverity: ErrorSeverity.ERROR,
  );
  bool _appliesTo(String path) {
    if (path.contains('/lib/app/theme/')) return false;
    if (path.endsWith('.g.dart') || path.endsWith('.generated.dart') || path.endsWith('.freezed.dart')) return false;
    if (path.contains('/test/')) return false;
    return path.contains('/lib/features/') || path.contains('/lib/app/');
  }
  @override
  void run(CustomLintResolver r, ErrorReporter reporter, CustomLintContext ctx) {
    if (!_appliesTo(r.path)) return;
    ctx.registry.addInstanceCreationExpression((node) {
      if (node.constructorName.type.element?.name == 'BoxShadow') {
        reporter.atNode(node, _code);
      }
    });
  }
}
```

- [ ] **Step 7: Add fixtures + tests per rule (mirror Task 18 pattern)**

For each rule above, add a `tool/lints/test/fixtures/<rule>_violation.dart` with at least one violating and one passing case, and a `tool/lints/test/<rule>_test.dart` that asserts the count of lints emitted.

- [ ] **Step 8: Run all lint package tests**

Run: `cd tool/lints && dart test`
Expected: all PASS.

- [ ] **Step 9: Sanity-run on theme/ (should produce zero lints)**

Run: `dart run custom_lint --no-fatal-infos lib/app/theme/`
Expected: zero lints.

- [ ] **Step 10: Sanity-run on a known-bad file**

Run: `dart run custom_lint --no-fatal-infos lib/features/dashboard/`
Expected: many lints (Phase E will fix). Do not block on this here.

- [ ] **Step 11: Commit**

```bash
git add tool/lints/lib/rules/ tool/lints/test/
git commit -m "feat(lint): 6 more rules — duration, curve, spacing, radius, text-style, shadow"
```

### Task 20: Disable lints in analysis_options for Phase E migration window

**Files:**
- Modify: `analysis_options.yaml`

- [ ] **Step 1: Comment out rules**

In `analysis_options.yaml`, temporarily comment out the rule list (so the migration commits in Phase E don't fail CI mid-stream):

```yaml
custom_lint:
  rules: []
  # Re-enabled at end of Phase E (Task 32):
  # - no_raw_colors
  # - no_literal_duration
  # - no_literal_curve
  # - no_literal_spacing
  # - no_literal_radius
  # - no_literal_text_style
  # - no_literal_shadow
```

- [ ] **Step 2: Commit**

```bash
git add analysis_options.yaml
git commit -m "build(lint): temporarily disable rules for big-bang feature migration"
```

---

## Phase E — Big-bang migration of 11 features

### Task 21: Add golden snapshot harness

**Files:**
- Modify: `pubspec.yaml` (add `golden_toolkit` dev dep)
- Create: `test/golden/golden_helper.dart`

- [ ] **Step 1: Add dev dep**

In `pubspec.yaml` `dev_dependencies:`:

```yaml
  golden_toolkit: ^0.15.0
```

Run: `flutter pub get`.

- [ ] **Step 2: Create harness**

Create `test/golden/golden_helper.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:golden_toolkit/golden_toolkit.dart';
import 'package:localocr_extended/app/theme/theme.dart';

Future<void> bootstrapGoldens() async {
  await loadAppFonts();  // loads bundled fonts for deterministic rendering
}

Widget wrapWithTheme(Widget child, {String theme = 'light'}) {
  return ProviderScope(
    child: MaterialApp(
      theme: appThemeDataFor(theme),
      home: Scaffold(body: child),
    ),
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add pubspec.yaml pubspec.lock test/golden/golden_helper.dart
git commit -m "test(goldens): add golden_toolkit harness with theme-aware wrap"
```

### Task 22: `appshell` migration

**Files:**
- Modify: every `.dart` in `lib/features/appshell/` that contains a forbidden literal
- Create: `test/golden/appshell/<screen>.png` (× 3-5 per top screens)
- Create: `test/golden/appshell/appshell_golden_test.dart`

This task is a template; Tasks 23–32 (one per feature) follow the identical pattern with the relevant feature substituted.

- [ ] **Step 1: Enumerate top screens of `appshell`**

Run: `find lib/features/appshell -name "*.dart" | head -10 && wc -l lib/features/appshell/**/*.dart`
Identify the 3-5 user-visible screens / widget trees (typically the sidebar root, the mobile menu drawer, the chat-FAB host).

- [ ] **Step 2: Write golden baseline tests**

Create `test/golden/appshell/appshell_golden_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:golden_toolkit/golden_toolkit.dart';
import '../golden_helper.dart';
import 'package:localocr_extended/features/appshell/appshell_root.dart'; // adjust import to real path

void main() {
  setUpAll(bootstrapGoldens);

  testGoldens('appshell sidebar — light', (tester) async {
    await tester.pumpWidgetBuilder(
      wrapWithTheme(const AppshellRoot(), theme: 'light'),
      surfaceSize: const Size(412, 915),  // typical Android viewport
    );
    await screenMatchesGolden(tester, 'appshell_sidebar_light');
  });

  testGoldens('appshell sidebar — dark', (tester) async {
    await tester.pumpWidgetBuilder(
      wrapWithTheme(const AppshellRoot(), theme: 'dark'),
      surfaceSize: const Size(412, 915),
    );
    await screenMatchesGolden(tester, 'appshell_sidebar_dark');
  });

  // Add 1-3 more for the most-used screens in this feature.
}
```

- [ ] **Step 3: Generate baseline goldens (pre-migration)**

Run: `flutter test --update-goldens test/golden/appshell/`
Expected: PNGs land in `test/golden/appshell/goldens/`.

- [ ] **Step 4: Migrate forbidden literals in `lib/features/appshell/`**

For each file, mechanically:

| Found | Replace with |
| --- | --- |
| `Colors.red` (or any named color) | `context.tok.error` (or the semantically nearest token) |
| `Color(0xFF……)` | `context.tok.<role>` (look up role from semantic intent; if unique, add a `// TODO(tokens): consider adding role` comment instead of inventing a role) |
| `Duration(milliseconds: 200)` | `context.tok.durationBase` |
| `Curves.easeInOut` | `context.tok.easeInOut` |
| `Curves.easeOut` | `context.tok.easeOut` |
| `EdgeInsets.all(16)` | `EdgeInsets.all(context.tok.space4)` |
| `EdgeInsets.symmetric(horizontal: 12)` | `EdgeInsets.symmetric(horizontal: context.tok.space3)` |
| `BorderRadius.circular(12)` | `BorderRadius.circular(context.tok.radiusLg)` |
| `BoxShadow(...)` literal | `context.tok.shadow2` (or nearest by elevation intent) |
| `TextStyle(fontSize: 14, ...)` | `context.tok.typeBody.copyWith(...)` (preserve color and any other non-typography fields) |

Add the import `import 'package:localocr_extended/app/theme/build_context_x.dart';` to each modified file.

For cases where the semantic intent cannot be mapped to an existing role (e.g., a one-off accent color used only here), pick the visually closest role and proceed. The intent is parity-with-token-system, not pixel-perfect preservation.

- [ ] **Step 5: Regenerate goldens (post-migration)**

Run: `flutter test --update-goldens test/golden/appshell/`
Inspect: the diff in `test/golden/appshell/goldens/`. Acceptable if:
- Colors shift to token values (e.g., a previous raw `Color(0xFF1F6FEB)` now matches `t.brand = 0xFF0071E3`).
- Spacing shifts to nearest scale value.
- Shadow softens / sharpens consistently with token shadow values.

Unacceptable: layout collapse, missing text, broken hit targets.

- [ ] **Step 6: Verify analyze clean for the feature**

Run: `flutter analyze lib/features/appshell/`
Expected: no errors (lints are disabled in Phase D Task 20 for now).

- [ ] **Step 7: Commit**

```bash
git add lib/features/appshell/ test/golden/appshell/
git commit -m "refactor(appshell): migrate to AppTokens; goldens updated"
```

### Tasks 23–32: Migrate remaining 10 features

Repeat the Task 22 procedure (Steps 1–7) for each of the following features, in alphabetical order. One commit per feature. Each commit message follows `refactor(<feature>): migrate to AppTokens; goldens updated`.

- [ ] **Task 23: `auth`** — files under `lib/features/auth/`
- [ ] **Task 24: `balances`** — files under `lib/features/balances/`
- [ ] **Task 25: `contacts`** — files under `lib/features/contacts/`
- [ ] **Task 26: `dashboard`** — files under `lib/features/dashboard/`
- [ ] **Task 27: `expenses`** — files under `lib/features/expenses/`
- [ ] **Task 28: `inventory`** — files under `lib/features/inventory/`
- [ ] **Task 29: `medicine`** — files under `lib/features/medicine/`
- [ ] **Task 30: `products`** — files under `lib/features/products/`
- [ ] **Task 31: `restaurant`** — files under `lib/features/restaurant/`
- [ ] **Task 32: `shopping`** — files under `lib/features/shopping/`

Each task:

1. Enumerate top screens (`find lib/features/<name> -name "*.dart" | head -10`).
2. Write 3-5 golden baseline tests covering the most user-visible widget trees, using `wrapWithTheme` from the helper, testing at minimum `light` and `dark`.
3. Generate baselines (`flutter test --update-goldens test/golden/<name>/`).
4. Mechanically migrate forbidden literals per the table in Task 22 Step 4, adding `build_context_x.dart` import to each modified file.
5. Regenerate goldens; inspect diffs.
6. Verify `flutter analyze lib/features/<name>/` clean.
7. Commit `refactor(<name>): migrate to AppTokens; goldens updated`.

Also during the `appshell` and `dashboard` commits, sweep any remaining literals in `lib/app/` (outside `lib/app/theme/`) — e.g. `lib/app/app.dart`, `lib/app/router/`. Bundle those edits into whichever feature commit logically owns them, or create a separate `refactor(app-shell): migrate root scaffolding to AppTokens` commit between Tasks 22 and 23 if cleaner.

### Task 33: Re-enable lints + final clean sweep

**Files:**
- Modify: `analysis_options.yaml`

- [ ] **Step 1: Uncomment rule list**

Restore the `custom_lint.rules:` list in `analysis_options.yaml` to its state from Task 17 Step 2.

- [ ] **Step 2: Run custom_lint over `lib/`**

Run: `dart run custom_lint`
Expected: zero lints across `lib/features/` and `lib/app/` (excluding `lib/app/theme/`).

If any lint fires:
- Inspect the violating site.
- Either fix by replacing the literal with a token, or
- Annotate with `// ignore: <rule_name>` plus a **mandatory** `// WHY: <reason>` line explaining why this site is a justified exception.

- [ ] **Step 3: Final sweep commit**

```bash
git add analysis_options.yaml lib/
git commit -m "build(lint): enable token lints across lib/features and lib/app"
```

---

## Phase F — CI integration & verification

### Task 34: CI drift check + lint step

**Files:**
- Modify: `.github/workflows/android-sync.yml`

- [ ] **Step 1: Read existing workflow**

Run: `cat .github/workflows/android-sync.yml`

Identify the right insertion point — typically after Flutter setup, before build / test.

- [ ] **Step 2: Add steps**

Insert these steps after Flutter setup:

```yaml
      - name: Install Python deps
        run: |
          python3 -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Verify token artefacts are in sync
        run: make tokens-check

      - name: Run custom_lint
        run: dart run custom_lint
```

- [ ] **Step 3: Verify locally**

Run: `make tokens-check && dart run custom_lint`
Expected: both exit 0.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/android-sync.yml
git commit -m "ci(tokens): drift check + custom_lint step in android-sync workflow"
```

### Task 35: End-to-end smoke

- [ ] **Step 1: Full test suite**

Run: `pytest tests/test_build_tokens_*.py tests/test_merge_fonts_into_pubspec.py && flutter test && cd tool/lints && dart test && cd -`
Expected: all PASS.

- [ ] **Step 2: Launch app, cycle every theme**

Run: `flutter run -d <emulator>`
In the running app, hit the theme cycle button 6 times. Each press should land on the next theme. Visually confirm distinct rendering at each position (light/dark differ in base; clay/clay-dark differ in shadow softness, radius, body font; notion/notion-dark differ in body font and tracking).

- [ ] **Step 3: Verify bundle size**

Run: `du -sh assets/fonts/`
Expected: < 700KB. If above, tighten the unicode range in `tool/subset_fonts.sh` and re-run subset.

- [ ] **Step 4: Verify license screen**

In the app, navigate to Settings → About → Licenses. Confirm Inter, Lora, iA Writer Quattro/Mono, and JetBrains Mono entries are present with the SIL OFL body.

- [ ] **Step 5: Final commit if anything updated, then push**

```bash
git status
# If any goldens / configs were re-baked in step 1, commit them.
git add -A
git diff --cached  # sanity look
git commit -m "chore(tokens): final smoke pass — fonts, theme cycle, licenses" || true
git push -u origin HEAD
```

---

## Spec Coverage Verification

| Spec section | Covered by task(s) |
| --- | --- |
| §1 Problem | n/a (motivation) |
| §2 Goals | Tasks 1–34 (entire plan) |
| §3 Non-goals | enforced by scope of each task — no system theme position, no IA changes, no iOS, no a11y audit |
| §4 Architecture diagram | Tasks 1, 2, 6, 11, 14 (pipeline assembled), 34 (CI drift) |
| §5 Token taxonomy + AppTokens shape | Tasks 6, 7 |
| §5.1 CSS→Dart conversion rules | Tasks 2, 3, 4, 5, 7 |
| §5.2 Per-theme overrides | Task 6 (color, radius, shadow, duration, ease), Task 7 (typography tracking) |
| §6 Codegen contract (`--target`, fallback, fonts sidecar) | Tasks 1, 6, 8 |
| §6.5 CI integration | Tasks 10 (Makefile), 34 (workflow) |
| §7 Theme switching + provider + access patterns | Tasks 11, 13, 14 |
| §7.4 Delete `AppTheme` + `themeModeFor` | Task 12 |
| §8 Big-bang migration | Tasks 21–33 |
| §8.1 Forbidden constructs | Tasks 18, 19 |
| §8.2 Allowed exceptions | Tasks 18, 19 (in `_appliesTo` guards) |
| §8.3 Migration order (alphabetical) | Tasks 22–32 |
| §8.4 Golden snapshot harness | Tasks 21, 22 (template), 23–32 |
| §8.5 Out-of-scope sweep | n/a (negative constraint) |
| §9 Typography & fonts | Tasks 7, 8, 15, 16 |
| §9.2 Bundle budget | Task 15 Step 4, Task 35 Step 3 |
| §9.3 Licenses | Tasks 15 Step 5, 16 |
| §9.4 TextTheme mapping | Task 6 `_buildThemeData` (already wires `fontFamily`; per-role TextTheme slot mapping is implicit through `t.typeBody` etc. which features consume directly via `context.tok`) |
| §10 Testing | Tasks 1–9 (unit), 11, 13 (widget), 22–32 (golden), 34 (CI), 35 (E2E) |
| §11 File-level changes | Distributed across all tasks |
| §12 Risks & mitigations | Lint exceptions (Task 33 `// WHY:`), bootstrap (Task 14 Step 3), drift gate (Task 10, 34) |

---

## Self-Review Notes

- **Placeholder scan:** No "TBD" / "TODO" markers remain. One acceptable `// TODO(tokens):` comment guidance in Task 22 Step 4 directs the engineer to flag rather than invent roles for one-off colors; the engineer still makes a concrete decision per site.
- **Type consistency:** `AppTokens` field naming is generated from `_COLOR_FIELDS` + `dart_field_name`; the same generator is reused in `_emit_app_tokens_class` and `_emit_theme_constructor`, so they cannot drift. `appTokensFor` / `appThemeDataFor` names are consistent across Tasks 6, 11, 14, 22.
- **Scope check:** Single PR, ~35 tasks, ~25-30 commits. Big but bounded — every commit produces a buildable state (with lints disabled during Phase E).
- **Ambiguity check:** Conversion rules are explicit (regex + helper functions); fallback behaviour for missing tokens is logged-and-substitute (not fail); lint `_appliesTo` paths are explicit; "what role for this raw color" decisions in Phase E follow "pick nearest by semantic intent" rule. No multi-interpretation requirements remain.
