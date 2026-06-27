import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router/router.dart';
import 'theme/tokens.generated.dart';
import 'theme/theme_provider.dart';

class LocalOcrApp extends ConsumerWidget {
  const LocalOcrApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final themeName = ref.watch(themeProvider);
    final themeData = appThemeDataFor(themeName).copyWith(
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    );
    return MaterialApp.router(
      title: 'LocalOCR Extended',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      theme: themeData,
      themeMode: ThemeMode.light,
    );
  }
}
