import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router/router.dart';
import 'theme/theme.dart';
import 'theme/theme_provider.dart';

class LocalOcrApp extends ConsumerWidget {
  const LocalOcrApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final mode = ref.watch(themeModeProvider);
    return MaterialApp.router(
      title: 'LocalOCR Extended',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      themeMode: mode,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
    );
  }
}
