#!/usr/bin/env python3
"""Compile design/design-tokens.json → CSS custom properties (Apple-inspired).

Emits a single CSS file (default: src/frontend/styles/tokens.generated.css)
that is inlined into the SPA's <style> block on deploy.

Usage:
    python3 scripts/build_tokens.py                  # write default output
    python3 scripts/build_tokens.py --stdout         # print to stdout
    python3 scripts/build_tokens.py --out path.css   # custom output path
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "design" / "design-tokens.json"
DEFAULT_OUTPUT = REPO_ROOT / "src" / "frontend" / "styles" / "tokens.generated.css"


def _var(name: str, value: str, indent: str = "  ") -> str:
    return f"{indent}--{name}: {value};"


def _emit_color_block(colors: dict, selector: str) -> str:
    lines = [f"{selector} {{"]
    for key, value in colors.items():
        lines.append(_var(f"color-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_shadow_block(shadows: dict, selector: str = ":root") -> str:
    lines = [f"{selector} {{"]
    for level, value in shadows.items():
        lines.append(_var(f"shadow-{level}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_typography(typography: dict) -> str:
    lines = [":root {"]
    fam = typography["font-family"]
    lines.append(_var("font-display", fam["display"]))
    lines.append(_var("font-text", fam["text"]))
    lines.append(_var("font-mono", fam["mono"]))
    for step, spec in typography["scale"].items():
        lines.append(_var(f"font-{step}", spec["size"]))
        lines.append(_var(f"font-{step}-weight", str(spec["weight"])))
        lines.append(_var(f"font-{step}-lh", str(spec["lh"])))
        lines.append(_var(f"font-{step}-tracking", spec["tracking"]))
    lines.append("}")
    return "\n".join(lines)


def _emit_scale(prefix: str, scale: dict, selector: str = ":root") -> str:
    lines = [f"{selector} {{"]
    for key, value in scale.items():
        lines.append(_var(f"{prefix}-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_motion(motion: dict) -> str:
    lines = [":root {"]
    for key, value in motion["duration"].items():
        lines.append(_var(f"duration-{key}", value))
    for key, value in motion["ease"].items():
        lines.append(_var(f"ease-{key}", value))
    lines.append("}")
    return "\n".join(lines)


def _emit_legacy_aliases() -> str:
    """Map historical CSS variable names to the new Apple-inspired tokens."""
    aliases = [
        ("bg",              "var(--color-bg)"),
        ("surface",         "var(--color-surface)"),
        ("surface2",        "var(--color-surface-2)"),
        ("surface-3",       "var(--color-surface-3)"),
        ("border",          "var(--color-border)"),
        ("border-strong",   "var(--color-border-strong)"),
        ("text",            "var(--color-text-primary)"),
        ("text-subtle",     "var(--color-text-secondary)"),
        ("muted",           "var(--color-text-muted)"),
        ("accent",          "var(--color-brand)"),
        ("accent-hover",    "var(--color-brand-hover)"),
        ("accent-pressed",  "var(--color-brand-pressed)"),
        ("accent-soft",     "var(--color-brand-soft)"),
        ("accent2",         "var(--color-success)"),
        ("accent3",         "var(--color-error)"),
        ("success",         "var(--color-success)"),
        ("success-soft",    "var(--color-success-soft)"),
        ("warning",         "var(--color-warning)"),
        ("warning-soft",    "var(--color-warning-soft)"),
        ("danger",          "var(--color-error)"),
        ("danger-soft",     "var(--color-error-soft)"),
        ("ring",            "var(--color-focus)"),
        ("overlay",         "var(--color-overlay)"),
        ("font-body",       "var(--font-text)"),
        ("fs-xs",           "var(--font-xs)"),
        ("fs-sm",           "var(--font-sm)"),
        ("fs-base",         "var(--font-sm)"),
        ("fs-md",           "var(--font-body)"),
        ("fs-lg",           "var(--font-md)"),
        ("fs-xl",           "var(--font-xl)"),
        ("fs-2xl",          "var(--font-2xl)"),
        ("fs-3xl",          "var(--font-3xl)"),
        ("lh-tight",        "1.14"),
        ("lh-snug",         "1.24"),
        ("lh-base",         "1.47"),
        ("radius-xs",       "var(--radius-xs)"),
        ("radius-sm",       "var(--radius-sm)"),
        ("radius-md",       "var(--radius-md)"),
        ("radius-lg",       "var(--radius-lg)"),
        ("radius-xl",       "var(--radius-xl)"),
        ("radius-pill",     "var(--radius-pill)"),
        ("shadow-xs",       "var(--shadow-1)"),
        ("shadow-sm",       "var(--shadow-1)"),
        ("shadow-md",       "var(--shadow-2)"),
        ("shadow-lg",       "var(--shadow-3)"),
    ]
    lines = [":root {"]
    for name, expr in aliases:
        lines.append(_var(name, expr))
    lines.append("}")
    return "\n".join(lines)


def _emit_theme_override(theme_name: str, theme: dict) -> str:
    """Emit a `[data-theme=<name>]` block that overrides any Apple tokens the
    theme touches: colors, radius, shadow, motion durations/eases, and
    per-step typography tracking. Each theme only has to declare what
    differs; everything else inherits from `:root`.
    """
    selector = f":root[data-theme=\"{theme_name}\"]"
    lines = [f"{selector} {{"]

    for key, value in theme.get("color", {}).items():
        lines.append(_var(f"color-{key}", value))

    for key, value in theme.get("radius", {}).items():
        lines.append(_var(f"radius-{key}", value))

    for level, value in theme.get("shadow", {}).items():
        lines.append(_var(f"shadow-{level}", value))

    for key, value in theme.get("duration", {}).items():
        lines.append(_var(f"duration-{key}", value))

    for key, value in theme.get("ease", {}).items():
        lines.append(_var(f"ease-{key}", value))

    for step, tracking in theme.get("typography-tracking", {}).items():
        lines.append(_var(f"font-{step}-tracking", tracking))

    lines.append("}")
    return "\n".join(lines)


def build(tokens: dict) -> str:
    parts: list[str] = [
        "/* AUTO-GENERATED — do not edit.\n"
        " * Source: design/design-tokens.json\n"
        " * Regenerate with: python3 scripts/build_tokens.py\n"
        " */",
        _emit_color_block(tokens["color"]["light"], ":root,\n:root[data-theme=\"light\"]"),
        _emit_color_block(tokens["color"]["dark"], ":root[data-theme=\"dark\"]"),
        _emit_typography(tokens["typography"]),
        _emit_scale("space", tokens["space"]),
        _emit_scale("radius", tokens["radius"]),
        _emit_scale("stroke", tokens["stroke"]),
        _emit_scale("icon", tokens["icon"]),
        _emit_shadow_block(tokens["shadow"]),
        _emit_motion(tokens["motion"]),
        _emit_legacy_aliases(),
    ]

    # Opt-in themes (Clay, etc.) are emitted after the Apple base so their
    # [data-theme="<name>"] selectors cascade on top.
    for theme_name, theme in tokens.get("themes", {}).items():
        parts.append(_emit_theme_override(theme_name, theme))

    return "\n\n".join(parts) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--stdout", action="store_true")
    args = p.parse_args()

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
