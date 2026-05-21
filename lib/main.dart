import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'core/api/env.dart';
import 'core/providers.dart';
import 'core/util/logger.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  appLogger.i('boot — flavor=${Env.flavor.name} base=${Env.baseUrl}');
  runApp(const ProviderScope(child: _Bootstrap()));
}

/// Boots the cookie jar before the rest of the app reads `apiClientProvider`,
/// then hands off to `LocalOcrApp`. Also performs the silent `/auth/me`
/// session probe at startup so the router can route directly to /dashboard
/// when a persisted cookie is still valid.
class _Bootstrap extends ConsumerStatefulWidget {
  const _Bootstrap();
  @override
  ConsumerState<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends ConsumerState<_Bootstrap> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    await ref.read(cookieJarProvider.future);
    try {
      final me = await ref.read(authRepositoryProvider).me();
      if (me != null) {
        ref.read(sessionProvider.notifier).state =
            Session(user: me.user, appConfig: me.appConfig);
        appLogger.i('loaded 1 session for user=${me.user.id} (resumed)');
      } else {
        appLogger.i('loaded 0 sessions (no persisted cookie)');
      }
    } catch (e) {
      appLogger.w('startup /auth/me failed (likely offline or 401): $e');
    }
    if (mounted) setState(() => _ready = true);
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) {
      return const MaterialApp(
        home: Scaffold(
          body: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    return const LocalOcrApp();
  }
}
