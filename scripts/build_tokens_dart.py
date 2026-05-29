#!/usr/bin/env python3
"""Compile design/design-tokens.json → Dart `AppTokens` ThemeExtension.

Emits lib/app/theme/tokens.generated.dart. Called via:
    python3 scripts/build_tokens.py --target dart
"""
from __future__ import annotations

import re
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
        if a.startswith("."):
            a = "0" + a
        return f"Color.fromRGBO({r}, {g}, {b}, {a})"
    raise ValueError(f"cannot convert CSS colour to Dart: {value!r}")


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
