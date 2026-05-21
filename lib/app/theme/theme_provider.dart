import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'theme.dart';

class ThemeNotifier extends StateNotifier<String> {
  ThemeNotifier() : super('light') {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString('theme');
    if (stored != null && themeCycle.contains(stored)) {
      state = stored;
    }
  }

  Future<void> setTheme(String name) async {
    if (!themeCycle.contains(name)) return;
    state = name;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme', name);
  }

  Future<void> cycle() async {
    await setTheme(nextTheme(state));
  }
}

final themeProvider =
    StateNotifierProvider<ThemeNotifier, String>((ref) => ThemeNotifier());

final themeModeProvider = Provider<ThemeMode>((ref) {
  return themeModeFor(ref.watch(themeProvider));
});
