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
        if a.startswith("."):
            a = "0" + a
        return f"Color.fromRGBO({r}, {g}, {b}, {a})"
    raise ValueError(f"cannot convert CSS colour to Dart: {value!r}")


_REM_RE = re.compile(r"^([0-9]*\.?[0-9]+)rem$")
_PX_RE = re.compile(r"^(-?[0-9]*\.?[0-9]+)px$")


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


def _parse_shadow_layer(layer: str) -> str:
    """Convert one shadow layer (either color-first or offset-first form) to Dart."""
    layer = layer.strip()
    if layer.startswith("inset ") or " inset " in f" {layer} ":
        raise ValueError(f"inset shadows not supported by Flutter BoxShadow: {layer!r}")
    # Split into color part and the four offsets. Color is either rgba(...) or #hex.
    color_match = re.search(r"(rgba?\([^)]*\)|#[0-9a-fA-F]{6})", layer)
    if not color_match:
        raise ValueError(f"shadow layer missing colour: {layer!r}")
    color_expr = css_color_to_dart(color_match.group(1))
    # Remove the colour, then split the remainder into numeric tokens.
    rest = (layer[: color_match.start()] + " " + layer[color_match.end():]).strip()
    nums = re.findall(r"-?[0-9.]+px|\b0\b", rest)
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
            try:
                v_dart = css_color_to_dart(v)
            except ValueError as e:
                # Tokens.json may contain colours the Dart converter can't
                # represent (e.g. 8-hex rgba shorthand). Fall back to black and
                # warn so drift check (Task 34) surfaces it.
                v_dart = "Color(0xFF000000) /* UNCONVERTIBLE token */"
                print(
                    f"WARN: theme {theme_name!r} color.{json_key}={v!r} unconvertible "
                    f"({e}); using black",
                    file=sys.stderr,
                )
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
        # Special case: "full" is "50%" in JSON, meaning fully round. Emit double.infinity
        # so BorderRadius.circular(double.infinity) renders as a pill / circle.
        if k == "full":
            lines.append(f"  {name}: double.infinity,")
        else:
            lines.append(f"  {name}: {css_scalar_to_dart(radius_src[k])},")
    # Stroke
    for k in _STROKE_KEYS:
        name = "stroke" + dart_field_name(k).lstrip("v")
        lines.append(f"  {name}: {css_scalar_to_dart(tokens['stroke'][k])},")
    # Shadows (theme may override). Some themes (clay, clay-dark) use CSS inset
    # shadows for the "punched-in highlight" effect, which Flutter BoxShadow cannot
    # represent. Catch the ValueError per-shadow and fall back to an empty list with
    # a stderr warning — drift check (Task 34) will surface this so it isn't lost.
    shadow_src = {**tokens["shadow"], **tokens.get("themes", {}).get(theme_name, {}).get("shadow", {})}
    for k in _SHADOW_KEYS:
        name = "shadow" + dart_field_name(k).lstrip("v")
        try:
            shadow_dart = css_shadow_to_dart(shadow_src[k])
        except ValueError as e:
            print(
                f"WARN: theme {theme_name!r} shadow.{k} unrepresentable in Flutter "
                f"({e}); emitting empty shadow list",
                file=sys.stderr,
            )
            shadow_dart = "<BoxShadow>[]"
        lines.append(f"  {name}: {shadow_dart},")
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
