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
