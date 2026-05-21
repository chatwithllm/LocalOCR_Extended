import 'package:flutter/material.dart';

/// Theme tokens. Will be filled in from web `--color-*` CSS variables in a
/// later phase. For now ship Material 3 light/dark defaults to unblock the
/// scaffold.
class AppTheme {
  AppTheme._();

  static ThemeData light() => ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1F6FEB),
          brightness: Brightness.light,
        ),
      );

  static ThemeData dark() => ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1F6FEB),
          brightness: Brightness.dark,
        ),
      );
}

/// Web theme cycle from `src/frontend/index.html:13962`:
///   light → dark → clay → clay-dark → notion → notion-dark → light …
/// Plan §3 — persist active theme in SharedPreferences under key `theme`.
const themeCycle = <String>[
  'light',
  'dark',
  'clay',
  'clay-dark',
  'notion',
  'notion-dark',
];

ThemeMode themeModeFor(String name) {
  switch (name) {
    case 'dark':
    case 'clay-dark':
    case 'notion-dark':
      return ThemeMode.dark;
    default:
      return ThemeMode.light;
  }
}

String nextTheme(String current) {
  final i = themeCycle.indexOf(current);
  if (i < 0) return themeCycle.first;
  return themeCycle[(i + 1) % themeCycle.length];
}
