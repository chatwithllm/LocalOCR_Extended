#!/usr/bin/env python3
"""Compile design/design-tokens.json → CSS custom properties.

Emits a single file (default: src/frontend/styles/tokens.generated.css) that can
be either `@import`-ed or inlined into the SPA's `<style>` block.

Usage:
    python3 scripts/build_tokens.py                  # writes the default output
    python3 scripts/build_tokens.py --stdout         # prints to stdout
    python3 scripts/build_tokens.py --out path.css   # custom output path

This is the single source of truth for tokens — do not edit the generated CSS
by hand. Edit `design/design-tokens.json` and re-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "design" / "design-tokens.json"
DEFAULT_OUTPUT = REPO_ROOT / "src" / "frontend" / "styles" / "tokens.generated.css"


def _css_var(name: str, value: str, indent: str = "  ") -> str:
    return f"{indent}--{name}: {value};"


def _emit_color_block(colors: dict, selector: str) -> str:
    lines = [f"{selector} {{"]
    for key, value in colors.items():
        lines.append(_css_var(f"color-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_typography(typography: dict) -> str:
    lines = [":root {"]
    fam = typography["font-family"]
    lines.append(_css_var("font-sans", fam["sans"]))
    lines.append(_css_var("font-display", fam["display"]))
    lines.append(_css_var("font-mono", fam["mono"]))
    for step, spec in typography["scale"].items():
        lines.append(_css_var(f"font-{step}", spec["size"]))
        lines.append(_css_var(f"font-{step}-weight", str(spec["weight"])))
        lines.append(_css_var(f"font-{step}-lh", str(spec["lh"])))
        lines.append(_css_var(f"font-{step}-tracking", spec["tracking"]))
    lines.append("}")
    return "\n".join(lines)


def _emit_scale(name_prefix: str, scale: dict, selector: str = ":root") -> str:
    lines = [f"{selector} {{"]
    for key, value in scale.items():
        lines.append(_css_var(f"{name_prefix}-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_shadow_theme(shadows: dict, selector: str) -> str:
    lines = [f"{selector} {{"]
    for level, value in shadows.items():
        lines.append(_css_var(f"shadow-{level}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_motion(motion: dict) -> str:
    lines = [":root {"]
    for key, value in motion["ease"].items():
        lines.append(_css_var(f"ease-{key}", value))
    for key, value in motion["duration"].items():
        lines.append(_css_var(f"duration-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_icon(icon: dict) -> str:
    lines = [":root {"]
    for key, value in icon["size"].items():
        lines.append(_css_var(f"icon-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_legacy_aliases() -> str:
    """Map historical CSS variable names to the new --color-* tokens.

    Keeps the existing component CSS working unchanged. When a component is
    rewritten to use the new tokens directly, its legacy reference here can
    be deleted.
    """
    aliases = [
        # color
        ("bg",             "var(--color-bg)"),
        ("surface",        "var(--color-surface)"),
        ("surface2",       "var(--color-surface-2)"),
        ("surface-3",      "var(--color-surface-3)"),
        ("border",         "var(--color-border)"),
        ("border-strong", "var(--color-border-strong)"),
        ("text",           "var(--color-text-primary)"),
        ("text-subtle",    "var(--color-text-secondary)"),
        ("muted",          "var(--color-text-muted)"),
        ("accent",         "var(--color-brand)"),
        ("accent-hover",   "var(--color-brand-hover)"),
        ("accent-pressed", "var(--color-brand-pressed)"),
        ("accent-soft",    "var(--color-brand-soft)"),
        ("accent2",        "var(--color-success)"),
        ("accent3",        "var(--color-error)"),
        ("success",        "var(--color-success)"),
        ("success-soft",   "var(--color-success-soft)"),
        ("warning",        "var(--color-warning)"),
        ("warning-soft",   "var(--color-warning-soft)"),
        ("danger",         "var(--color-error)"),
        ("danger-soft",    "var(--color-error-soft)"),
        ("ring",           "var(--color-border-brand)"),
        ("overlay",        "var(--color-overlay)"),
        # typography — legacy font-body/family points at new sans
        ("font-body",      "var(--font-sans)"),
        # legacy size scale kept at original values; the new --font-* tokens
        # coexist so new components can adopt them freely
        ("fs-xs",          "0.72rem"),
        ("fs-sm",          "0.82rem"),
        ("fs-base",        "0.92rem"),
        ("fs-md",          "1rem"),
        ("fs-lg",          "1.15rem"),
        ("fs-xl",          "1.4rem"),
        ("fs-2xl",         "1.85rem"),
        ("fs-3xl",         "2.4rem"),
        ("lh-tight",       "1.15"),
        ("lh-snug",        "1.3"),
        ("lh-base",        "1.5"),
        # legacy shadow names → levels
        ("shadow-xs",      "var(--shadow-1)"),
        ("shadow-sm",      "var(--shadow-1)"),
        ("shadow-md",      "var(--shadow-2)"),
        ("shadow-lg",      "var(--shadow-3)"),
    ]
    lines = [":root {"]
    for name, expr in aliases:
        lines.append(_css_var(name, expr))
    lines.append("}")
    return "\n".join(lines)


def build(tokens: dict) -> str:
    parts: list[str] = []
    parts.append(
        "/* AUTO-GENERATED — do not edit.\n"
        " * Source: design/design-tokens.json\n"
        " * Regenerate with: python3 scripts/build_tokens.py\n"
        " */"
    )
    parts.append(
        _emit_color_block(tokens["color"]["light"], ":root,\n[data-theme=\"light\"]")
    )
    parts.append(_emit_color_block(tokens["color"]["dark"], "[data-theme=\"dark\"]"))
    parts.append(_emit_typography(tokens["typography"]))
    parts.append(_emit_scale("space", tokens["space"]))
    parts.append(_emit_scale("radius", tokens["radius"]))
    parts.append(_emit_scale("stroke", tokens["stroke"]))
    parts.append(
        _emit_shadow_theme(tokens["shadow"]["light"], ":root,\n[data-theme=\"light\"]")
    )
    parts.append(_emit_shadow_theme(tokens["shadow"]["dark"], "[data-theme=\"dark\"]"))
    parts.append(_emit_motion(tokens["motion"]))
    parts.append(_emit_icon(tokens["icon"]))
    parts.append(_emit_legacy_aliases())
    return "\n\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="Path to design-tokens.json (default: %(default)s)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT,
                        help="Output CSS path (default: %(default)s)")
    parser.add_argument("--stdout", action="store_true",
                        help="Write to stdout instead of the output path")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input {args.input} not found", file=sys.stderr)
        return 1

    tokens = json.loads(args.input.read_text())
    css = build(tokens)

    if args.stdout:
        sys.stdout.write(css)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(css)
    print(f"wrote {args.out} ({len(css):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
