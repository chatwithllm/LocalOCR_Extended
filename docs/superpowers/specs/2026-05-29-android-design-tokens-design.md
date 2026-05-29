# Android Design Tokens — System-Wide Polish

**Date:** 2026-05-29
**Status:** Draft → Awaiting user review
**Scope:** Flutter Android port (`lib/`)
**Affects:** All 11 shipped features + future features

---

## 1. Problem

The Android Flutter port ships a 6-theme cycle (`light`, `dark`, `clay`, `clay-dark`, `notion`, `notion-dark`) declared in `lib/app/theme/theme.dart:31-38`, but only the first two are backed. The current `AppTheme.light()` / `AppTheme.dark()` (lib/app/theme/theme.dart:9-25) produce `ThemeData` via `ColorScheme.fromSeed(0xFF1F6FEB)` — every Material widget renders blue-Material-3 defaults regardless of which theme name is active. Tokens defined in `design/design-tokens.json` (the project's single source of truth, already consumed by the web SPA via `scripts/build_tokens.py` → `src/frontend/styles/tokens.generated.css`, 674 lines, 6 themes) are not consumed by Flutter at all.

Concrete consequences across the 11 shipped features (`appshell`, `auth`, `balances`, `contacts`, `dashboard`, `expenses`, `inventory`, `medicine`, `products`, `restaurant`, `shopping`):

- Raw `Colors.X` and `Color(0xFF…)` literals scattered through feature code.
- Confidence colors, category colors, glass-nav, overlays — all absent.
- Spacing, radius, shadow, motion, typography — all ad-hoc per file.
- Web tokens evolve (e.g. clay durations differ from light); Android cannot pick up those changes.
- The 4 unbacked themes (`clay`, `clay-dark`, `notion`, `notion-dark`) silently fall through to `nextTheme(…)` returning a name the user sees in UI but which renders identically to `light`.

## 2. Goals

1. **Single source of truth.** `design/design-tokens.json` drives both web CSS and Android Dart. One regen step per token change.
2. **All six themes backed end-to-end.** Each cycle position produces a visually distinct theme (color + typography + per-theme motion timing).
3. **Full token category parity with web.** Color, space, radius, stroke, shadow, motion, typography all consumable from Flutter widgets.
4. **Material 3 ergonomics preserved.** Standard widgets pick up theme via `ColorScheme` + `TextTheme` slots automatically; custom widgets read tokens via a `ThemeExtension`.
5. **Drift is a build error.** CI fails if generated Dart file is out of sync with the JSON source.
6. **Big-bang migration.** All 11 shipped features migrate in a single PR; raw color/spacing/etc. literals lint-forbidden in `lib/features/**` and `lib/app/**` going forward.

## 3. Non-goals

- Redesigning information architecture, layout, or screen flows.
- Introducing a 7th `system` theme (system dark-mode follow).
- Backporting Android typography choices to the web.
- Building a token authoring tool / Figma plugin.
- Animations beyond hooking motion tokens into existing animations.
- Per-feature visual rework (golden tests should accept token-driven visual deltas without redesigning content).

## 4. Architecture

```
design/design-tokens.json   ← single source of truth (existing, untouched)
        │
        ├─→ scripts/build_tokens.py --target css   → src/frontend/styles/tokens.generated.css  (existing flow, untouched)
        └─→ scripts/build_tokens.py --target dart  → lib/app/theme/tokens.generated.dart       (NEW)
                                                                │
                                                                ▼
                            lib/app/theme/theme.dart   ← public API: appThemeDataFor(themeName), appTokensFor(themeName)
                                                                │
                            ┌───────────────────────────────────┴──────────────────────┐
                            ▼                                                          ▼
                ColorScheme slots (Material 3)                            AppTokens ThemeExtension
                brand → primary                                           confidenceHigh/Medium/Low + soft variants
                error → error                                             catGrocery/Restaurant/Utility/PersonalService/Subscription/Other
                surface → surface                                         glassNav, overlay, overlaySoft
                etc.                                                      space0..space16
                                                                          radiusSm..radiusCircle
                                                                          strokeHairline..strokeThick
                                                                          shadowSm/Md/Lg/Glass
                                                                          durationInstant..durationElaborate
                                                                          easeStandard/In/Out/InOut/Spring
                                                                          TextStyle: hero, h4xl..h1xl, bodyEm, body, label, caption, mono
                                                                          fontDisplay, fontText, fontSerif, fontMono (per theme)
```

**CI gate:** `make tokens-check` re-runs the codegen to a tmp directory and `diff`s against the checked-in `tokens.generated.dart`. Non-empty diff → build fail. Same pattern already used (or to be added in parallel) for the CSS target.

## 5. Token taxonomy & Dart shape

Generated file `lib/app/theme/tokens.generated.dart` emits:

- Private constructor per theme: `_lightTokens()`, `_darkTokens()`, `_clayTokens()`, `_clayDarkTokens()`, `_notionTokens()`, `_notionDarkTokens()`.
- Public lookup: `AppTokens appTokensFor(String themeName)` — falls back to `_lightTokens()` for unknown names and emits a `debugPrint` warning in debug builds.
- Public theme builder: `ThemeData appThemeDataFor(String themeName)` that returns a fully wired `ThemeData` (ColorScheme + TextTheme + ThemeExtension).

`AppTokens` shape (full field list):

```dart
class AppTokens extends ThemeExtension<AppTokens> {
  // ── Color ────────────────────────────────────────────────
  final Color brand, brandHover, brandPressed, brandSoft, brandContrast;
  final Color link;
  final Color bg, bgInverse;
  final Color surface, surface2, surface3, surface4, surfaceInverse;
  final Color overlay, overlaySoft, glassNav;
  final Color textPrimary, textSecondary, textMuted, textDisabled, textInverse;
  final Color border, borderStrong, borderBrand, focus;
  final Color success, successSoft;
  final Color warning, warningSoft;
  final Color error, errorSoft, errorHover;
  final Color info, infoSoft;
  final Color confidenceHigh, confidenceMedium, confidenceLow;
  final Color confidenceHighSoft, confidenceMediumSoft, confidenceLowSoft;
  final Color catGrocery, catRestaurant, catUtility, catPersonalService, catSubscription, catOther;

  // ── Space (logical pixels) ───────────────────────────────
  final double space0, space1, space2, space3, space4, space5, space6, space8, space10, space12, space16;

  // ── Radius ───────────────────────────────────────────────
  final double radiusSm, radiusMd, radiusLg, radiusXl, radiusPill, radiusCircle;

  // ── Stroke ───────────────────────────────────────────────
  final double strokeHairline, strokeThin, strokeRegular, strokeThick;

  // ── Shadow ───────────────────────────────────────────────
  final List<BoxShadow> shadowSm, shadowMd, shadowLg, shadowGlass;

  // ── Motion ───────────────────────────────────────────────
  final Duration durationInstant, durationFast, durationBase, durationSlow, durationElaborate;
  final Curve easeStandard, easeIn, easeOut, easeInOut, easeSpring;

  // ── Typography ──────────────────────────────────────────
  final TextStyle hero, h4xl, h3xl, h2xl, h1xl, bodyEm, body, label, caption, mono;

  // ── Font families (per theme) ───────────────────────────
  final String fontDisplay, fontText, fontSerif, fontMono;

  const AppTokens({ /* all fields required, no defaults */ });

  @override
  AppTokens copyWith({ /* every field nullable override */ });

  @override
  AppTokens lerp(ThemeExtension<AppTokens>? other, double t) {
    if (other is! AppTokens) return this;
    return AppTokens(
      brand: Color.lerp(brand, other.brand, t)!,
      // ... all colors via Color.lerp
      space0: lerpDouble(space0, other.space0, t)!,
      // ... all doubles via lerpDouble
      shadowSm: BoxShadow.lerpList(shadowSm, other.shadowSm, t)!,
      durationBase: Duration(milliseconds: lerpDouble(
        durationBase.inMilliseconds.toDouble(),
        other.durationBase.inMilliseconds.toDouble(), t)!.round()),
      easeStandard: t < 0.5 ? easeStandard : other.easeStandard,  // curves snap, no interpolation
      hero: TextStyle.lerp(hero, other.hero, t)!,
      // ...
      fontDisplay: t < 0.5 ? fontDisplay : other.fontDisplay,     // strings snap
      // ...
    );
  }
}
```

### 5.1 Conversion rules (CSS → Dart)

| CSS form | Dart form |
| --- | --- |
| `#rrggbb` | `Color(0xFFrrggbb)` |
| `rgba(r, g, b, a)` | `Color.fromRGBO(r, g, b, a)` |
| `Xrem` | `X * 16.0` (double) |
| `Xpx` | `X.0` (double) |
| `Xms` | `Duration(milliseconds: X)` |
| `cubic-bezier(x1, y1, x2, y2)` | `Cubic(x1, y1, x2, y2)` |
| `0 1px 2px rgba(...)` | `BoxShadow(offset: Offset(0, 1), blurRadius: 2, color: ...)` |
| Multi-layer shadow `a, b, c` | `[BoxShadow(a), BoxShadow(b), BoxShadow(c)]` |

### 5.2 Per-theme overrides

`design-tokens.json` includes per-theme overrides for motion (e.g., clay uses `--duration-base: 280ms`, notion `240ms`, light `200ms`) and typography tracking/line-height. The codegen merges base tokens with each theme's overrides; the generated constructor for that theme receives the resolved final values. Missing per-theme override → fall through to base, which is the existing CSS behaviour.

## 6. Codegen contract

Extend `scripts/build_tokens.py` (currently 215 lines, CSS-only) with a `--target` flag.

### 6.1 CLI

```
python3 scripts/build_tokens.py --target css           # current behaviour (CSS only)
python3 scripts/build_tokens.py --target dart          # NEW — Dart only
python3 scripts/build_tokens.py --target all           # NEW — both
python3 scripts/build_tokens.py --target dart --out lib/app/theme/tokens.generated.dart  # explicit
python3 scripts/build_tokens.py --target dart --stdout                                    # print, no write
```

Default output paths:
- `--target css`: `src/frontend/styles/tokens.generated.css` (unchanged from today).
- `--target dart`: `lib/app/theme/tokens.generated.dart`.

### 6.2 Generated file header

```dart
// AUTO-GENERATED — do not edit.
// Source: design/design-tokens.json
// Regenerate: python3 scripts/build_tokens.py --target dart
//
// To consume: ThemeData td = appThemeDataFor('clay');
// To access tokens directly: AppTokens t = Theme.of(context).extension<AppTokens>()!;
```

### 6.3 Fallback behaviour

If a theme is missing a token entirely (not just a per-theme override), the codegen:
1. Logs a stderr warning: `WARN: theme 'clay' missing token 'color.confidenceLow' — falling back to light`.
2. Emits the light value into the clay constructor.
3. Exit code remains 0 (warning, not error). Hard fail only on JSON parse errors or schema violations.

### 6.4 Font asset declaration sidecar

Codegen also emits `tool/fonts.generated.yaml`, a snippet describing the font assets required by the theme set:

```yaml
# AUTO-GENERATED — do not edit. Source: design/design-tokens.json
flutter:
  fonts:
    - family: Inter
      fonts:
        - asset: assets/fonts/Inter-Regular.ttf
        - asset: assets/fonts/Inter-Medium.ttf
          weight: 500
        - asset: assets/fonts/Inter-SemiBold.ttf
          weight: 600
        - asset: assets/fonts/Inter-Bold.ttf
          weight: 700
    - family: Lora
      fonts:
        - asset: assets/fonts/Lora-Regular.ttf
        - asset: assets/fonts/Lora-Medium.ttf
          weight: 500
        - asset: assets/fonts/Lora-SemiBold.ttf
          weight: 600
        - asset: assets/fonts/Lora-Bold.ttf
          weight: 700
    - family: iAWriterQuattroS
      fonts:
        - asset: assets/fonts/iAWriterQuattroS-Regular.ttf
        - asset: assets/fonts/iAWriterQuattroS-Italic.ttf
          style: italic
        - asset: assets/fonts/iAWriterQuattroS-Bold.ttf
          weight: 700
        - asset: assets/fonts/iAWriterQuattroS-BoldItalic.ttf
          weight: 700
          style: italic
```

A separate `make fonts` step (Python script `scripts/merge_fonts_into_pubspec.py`) reads `tool/fonts.generated.yaml` and rewrites the `flutter.fonts` block of `pubspec.yaml`. This avoids edit-in-place YAML fragility (Dart-side `pubspec.yaml` has more than just fonts; we replace only the `fonts:` sub-block while preserving everything else, using `ruamel.yaml` round-trip mode).

### 6.5 CI integration

Add to `.github/workflows/android-sync.yml` (existing file from f96f011) a pre-build step that re-runs every generator script and asserts no drift:

```yaml
- name: Regenerate tokens and check drift
  run: |
    make tokens-check
```

Makefile target:

```makefile
.PHONY: tokens tokens-check fonts
tokens:
	python3 scripts/build_tokens.py --target all
	python3 scripts/merge_fonts_into_pubspec.py

tokens-check: tokens
	git diff --exit-code -- \
	  src/frontend/styles/tokens.generated.css \
	  lib/app/theme/tokens.generated.dart \
	  tool/fonts.generated.yaml \
	  pubspec.yaml

fonts:
	python3 scripts/merge_fonts_into_pubspec.py
```

`make tokens` regenerates everything. `make tokens-check` regenerates and asserts the working tree is clean for all four generated artifacts (CSS, Dart, fonts sidecar, pubspec). Drift = non-zero exit. PR cannot merge.

## 7. Theme switching & runtime wiring

### 7.1 Provider

Replace `lib/app/theme/theme_provider.dart` (currently 37 lines) with a Riverpod async-initialised notifier:

```dart
// lib/app/theme/theme_provider.dart
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

`nextTheme(String)` and `themeCycle` stay in `theme.dart` (the cycle order is product-level, not generated). `themeModeFor(String)` is **deleted** — no longer needed (see 7.2).

### 7.2 MaterialApp wiring

`main.dart` consumes the provider:

```dart
final themeAsync = ref.watch(themeNameNotifierProvider);
final themeName = themeAsync.valueOrNull ?? 'light';
return MaterialApp.router(
  theme: appThemeDataFor(themeName),
  // No darkTheme override; brightness is baked into each named theme.
  // No themeMode override; we always render the chosen theme as-is.
  routerConfig: ...,
);
```

System dark-mode follow is **off**. The user's explicit cycle choice wins. Rationale: the web SPA behaves the same way and persists `theme` in `localStorage`; we keep parity. A future cycle position `system` may be added but is out of scope here.

### 7.3 Widget access patterns

```dart
// Material slot (auto):
ElevatedButton(onPressed: ..., child: const Text('Save'));
// → renders with primary = token.brand, foreground = token.brandContrast

// Custom token:
final t = Theme.of(context).extension<AppTokens>()!;
Container(
  padding: EdgeInsets.all(t.space3),
  decoration: BoxDecoration(
    color: t.confidenceHighSoft,
    borderRadius: BorderRadius.circular(t.radiusMd),
    boxShadow: t.shadowSm,
    border: Border.all(color: t.border, width: t.strokeRegular),
  ),
  child: Text('98% confidence', style: t.label.copyWith(color: t.confidenceHigh)),
);

// Motion:
AnimatedContainer(duration: t.durationBase, curve: t.easeStandard, ...);

// Convenience extension (lib/app/theme/build_context_x.dart) shipped with the spec:
extension AppTokensX on BuildContext {
  AppTokens get tok => Theme.of(this).extension<AppTokens>()!;
}
// usage: context.tok.space3
```

### 7.4 Migration of `theme.dart`

Final shape of `lib/app/theme/theme.dart` after migration:

```dart
import 'package:flutter/material.dart';

// Generated AppTokens, _lightTokens, ..., appTokensFor, appThemeDataFor.
export 'tokens.generated.dart';

// Hand-written: cycle order is product-level, not generated.
const themeCycle = <String>[
  'light', 'dark', 'clay', 'clay-dark', 'notion', 'notion-dark',
];

String nextTheme(String current) {
  final i = themeCycle.indexOf(current);
  if (i < 0) return themeCycle.first;
  return themeCycle[(i + 1) % themeCycle.length];
}
```

`themeModeFor` deleted. `AppTheme.light()` / `AppTheme.dark()` deleted (callers migrate to `appThemeDataFor`).

## 8. Big-bang migration of 11 features

### 8.1 Forbidden constructs in `lib/features/**` and `lib/app/**` (except `lib/app/theme/`)

Lint-enforced via `custom_lint` rules in `tool/lints/`:

| Rule | Forbids | Use instead |
| --- | --- | --- |
| `no_raw_colors` | `Colors.X`, `Color(0xFF…)`, hex string colors | `context.tok.<color>` or `ColorScheme` slot |
| `no_literal_duration` | `Duration(milliseconds: N)` with literal `N` | `context.tok.duration<role>` |
| `no_literal_curve` | `Curves.X` | `context.tok.ease<role>` |
| `no_literal_spacing` | `EdgeInsets.all(N)`, `.symmetric(...)` with literal numerics | `EdgeInsets.all(context.tok.space<N>)` |
| `no_literal_radius` | `BorderRadius.circular(N)` literal | `BorderRadius.circular(context.tok.radius<role>)` |
| `no_literal_text_style` | `TextStyle(fontSize: ..., fontWeight: ...)` constructed inline | `context.tok.<role>` (then `.copyWith(color: ...)` if needed) |
| `no_literal_shadow` | `BoxShadow(...)` literal | `context.tok.shadow<role>` |

### 8.2 Allowed exceptions

- `Colors.transparent` — semantic null, not a colour choice.
- `Color(0x00000000)` — fully transparent masks for shaders/overlays.
- Inside `lib/app/theme/**` — tokens themselves live here.
- Inside generated files (`*.g.dart`, `*.generated.dart`, `*.freezed.dart`).
- `Duration.zero` — semantic null.
- Inside `test/` — test fixtures may use literals freely.

### 8.3 Migration order (within the PR, atomic per feature)

1. **Commit 1:** Land `tokens.generated.dart`, `theme.dart` rewrite, `theme_provider.dart` rewrite, font assets + licenses, `pubspec.yaml` updates, `BuildContext` extension. Lints **disabled**.
2. **Commits 2–12:** One commit per feature, alphabetical: `appshell` → `auth` → `balances` → `contacts` → `dashboard` → `expenses` → `inventory` → `medicine` → `products` → `restaurant` → `shopping`.
3. **Commit 13:** Enable lints in `analysis_options.yaml`. Add CI `dart run custom_lint` step.

### 8.4 Per-feature golden snapshot harness

Before per-feature migration commit:
- Add golden tests at `test/goldens/<feature>/<screen>.png` for the top 3-5 screens per feature.
- Run with the **current** theme implementation to establish baseline.

After per-feature migration commit:
- Re-run golden tests.
- Visual deltas are **expected** (the whole point is to apply tokens). Acceptable when:
  - Colour deltas align with the token swap (e.g. `Colors.blue` → `t.brand`).
  - Spacing/radius/shadow deltas align with token values.
- Unexpected deltas (e.g. layout shift, missing text) → fix before continuing.
- Updated golden files committed alongside the migration commit.

Golden test infra uses `golden_toolkit` package; baseline run on macOS CI (deterministic font rendering).

### 8.5 Out of scope for migration commits

- Adding new features.
- Refactoring screen architecture / routing.
- Changing Riverpod provider structure beyond the theme provider.
- Re-doing copy / strings / i18n.
- Asset replacement beyond font files.

## 9. Typography & font bundling

### 9.1 Font selection per theme family

| Theme family | Display | Body | Mono | License | Source |
| --- | --- | --- | --- | --- | --- |
| `light`, `dark` | Inter | Inter | JetBrains Mono | SIL OFL 1.1 | rsms.me/inter, jetbrains.com/lp/mono |
| `clay`, `clay-dark` | Lora | Lora | JetBrains Mono | SIL OFL 1.1 | fonts.google.com/specimen/Lora |
| `notion`, `notion-dark` | iA Writer Quattro | iA Writer Quattro | iA Writer Mono | SIL OFL 1.1 | github.com/iaolo/iA-Fonts |

Mono is theme-independent (one bundled mono per theme is overkill; JetBrains Mono works visually for all). Notion theme uses iA Writer Quattro for body, which is itself a quasi-mono proportional, so its mono slot also uses iA Writer Mono for character consistency.

### 9.2 Bundle budget

Target: ≤ 700 KB total font weight added to APK. Subset to Latin + Latin-Extended via `fonttools subset` step in codegen:

```
fonttools subset Inter-Regular.ttf \
  --unicodes="U+0000-024F,U+1E00-1EFF,U+2000-206F,U+2070-209F,U+20A0-20CF,U+2100-214F" \
  --output-file=assets/fonts/Inter-Regular.ttf
```

Run once per font file, checked in (deterministic). Subsetting reduces Inter from ~770KB → ~145KB; Lora ~290KB → ~110KB; iA Writer Quattro ~360KB → ~130KB; JetBrains Mono ~190KB → ~95KB. Total ~480KB across all 13 weight/style variants.

### 9.3 License compliance

`assets/fonts/LICENSES/` contains the verbatim SIL OFL 1.1 license file from each upstream, named `<Family>-OFL.txt`. The app's Settings → About screen surfaces these via a `LicensePage` route (Flutter built-in; loads via `LicenseRegistry.addLicense` registered in `main.dart`).

### 9.4 Material `TextTheme` mapping

`appThemeDataFor` wires the AppTokens text roles into `ThemeData.textTheme`:

| Material slot | AppTokens role |
| --- | --- |
| `displayLarge` | `hero` |
| `displayMedium` | `h4xl` |
| `displaySmall` | `h3xl` |
| `headlineLarge` | `h2xl` |
| `headlineMedium` | `h1xl` |
| `headlineSmall` | `bodyEm` |
| `titleLarge` | `bodyEm` |
| `titleMedium` | `bodyEm` |
| `titleSmall` | `label` |
| `bodyLarge` | `body` |
| `bodyMedium` | `body` |
| `bodySmall` | `caption` |
| `labelLarge` | `label` |
| `labelMedium` | `label` |
| `labelSmall` | `caption` |

Standard Material widgets (`AppBar`, `ListTile`, `Card`, etc.) pick up theme typography automatically through these slots, without per-widget refactoring during migration.

## 10. Testing strategy

| Test layer | What | How |
| --- | --- | --- |
| Unit — codegen | Each CSS construct → Dart construct conversion. | `pytest tests/test_build_tokens_dart.py` against fixture JSON + expected Dart. |
| Unit — fallback | Missing per-theme override falls through. | Same. |
| Unit — Dart | `AppTokens.lerp` returns sane intermediates. | `flutter test test/app/theme/tokens_test.dart`. |
| Unit — Dart | `appTokensFor('unknown')` warns + returns light. | Same. |
| Widget — Dart | Each theme renders a sample widget without throwing. | Parameterised widget test across `themeCycle`. |
| Golden — Dart | 3-5 screens per feature, baseline + post-migration. | `golden_toolkit`, CI on macOS. |
| CI drift | `scripts/build_tokens.py --target all` produces no diff. | Workflow step in `android-sync.yml`. |
| Lint | Forbidden constructs absent in `lib/features/**`, `lib/app/**`. | `dart run custom_lint`. |

## 11. File-level changes summary

**New:**
- `lib/app/theme/tokens.generated.dart` (generated, do not edit by hand)
- `lib/app/theme/build_context_x.dart` (`context.tok` extension)
- `tool/fonts.generated.yaml` (generated)
- `tool/lints/no_raw_colors.dart`, `no_literal_duration.dart`, `no_literal_curve.dart`, `no_literal_spacing.dart`, `no_literal_radius.dart`, `no_literal_text_style.dart`, `no_literal_shadow.dart`
- `scripts/merge_fonts_into_pubspec.py`
- `tests/test_build_tokens_dart.py`
- `test/app/theme/tokens_test.dart`
- `test/goldens/<feature>/*.png` × ~40 files (baseline + post)
- `assets/fonts/Inter-*.ttf`, `Lora-*.ttf`, `iAWriterQuattroS-*.ttf`, `iAWriterMonoS-*.ttf`, `JetBrainsMono-*.ttf`
- `assets/fonts/LICENSES/Inter-OFL.txt`, `Lora-OFL.txt`, `iAWriter-OFL.txt`, `JetBrainsMono-OFL.txt`

**Modified:**
- `scripts/build_tokens.py` — add `--target` flag, Dart emitter, `tool/fonts.generated.yaml` emitter
- `lib/app/theme/theme.dart` — rewrite to slim cycle/nextTheme, re-export generated
- `lib/app/theme/theme_provider.dart` — rewrite to async Riverpod notifier
- `pubspec.yaml` — fonts block (rewritten by `merge_fonts_into_pubspec.py`), `custom_lint` dev dep
- `analysis_options.yaml` — enable custom_lint plugin + rules
- `.github/workflows/android-sync.yml` — add tokens drift check + custom_lint step
- Every Dart file under `lib/features/**` and `lib/app/**` (except `lib/app/theme/`) that uses a forbidden literal — migrate to tokens
- `Makefile` — add `tokens`, `tokens-check`, `fonts` targets
- `.gitignore` — does not change

**Deleted:**
- `AppTheme` class in `lib/app/theme/theme.dart` (replaced by `appThemeDataFor`)
- `themeModeFor` function

## 12. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Big-bang PR is too large to review. | Per-feature atomic commits within the PR; reviewer can review commit-by-commit. Golden diffs annotated. |
| Generated Dart file diff noise on every JSON change. | Generated file is auto-formatted (`dart format`) and stable-ordered; small JSON edits produce small Dart diffs. |
| Font bundle inflates APK. | Subsetting cap (≤700KB total). CI step prints `assets/fonts/` total size on every build; fail if > 800KB. |
| `custom_lint` rules produce false positives in legitimate cases. | Each rule supports `// ignore: no_raw_colors` line-level escape hatch with required justification comment. Code review enforces "ignore" must include a `WHY:` comment. |
| Riverpod async initial state shows wrong theme for one frame. | Bootstrap `SharedPreferences` synchronously in `main()` before `runApp`; pass initial theme into provider override (`ProviderScope(overrides: [...])`). |
| Per-theme font swap causes layout shifts mid-cycle. | `AppTokens.lerp` snaps font family at midpoint (string types do not interpolate); document this UX trade-off. Acceptable for an explicit user-triggered cycle. |
| Web tokens evolve, Android falls behind. | Tokens are now Android's CI dependency. Any web token PR triggers Android drift check; both regen together. |
| Lint disabled→enabled gap allows regressions in commits 2-12 of the migration PR. | Reviewer must re-run `dart run custom_lint` locally between commits or rely on CI to catch on commit 13. Acceptable since the PR is atomic — merge gates on the final state. |

## 13. Open questions

None at draft time. Resolved during brainstorming:
- Single source of truth → Python script extension.
- ColorScheme + ThemeExtension hybrid.
- Big-bang vs strangler → big bang.
- All token categories → yes.
- Per-theme typefaces → Inter / Lora / iA Writer Quattro.

## 14. Out of scope, captured for later

- 7th `system` cycle position to follow system dark mode.
- Token-driven iOS Flutter build (the same generator could emit Swift, but the macOS app is a separate codebase under `LocalOCR.macOS/` and not affected here).
- A11y audit pass on resulting contrast ratios (token authors are responsible; a separate audit phase can verify post-migration).
- Migration of `LocalOCR.macOS/` Swift codebase to consume the same token JSON.
- Figma plugin / token export round-trip.
