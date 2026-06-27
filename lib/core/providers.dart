import 'package:cookie_jar/cookie_jar.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/api_client.dart';
import 'api/cookie_jar_factory.dart';
import 'auth/auth_repository.dart';
import 'models/app_config.dart';
import 'models/user.dart';
import 'storage/secure_storage.dart';

/// Root DI. All feature repositories `ref.watch` these.

final secureStorageProvider = Provider<SecureStorage>((ref) => SecureStorage());

final cookieJarProvider = FutureProvider<PersistCookieJar>((ref) async {
  return buildCookieJar();
});

/// Callback installed by the router so AuthInterceptor can trigger /login
/// without importing go_router. Set once at app boot.
final unauthorizedSignalProvider =
    StateProvider<int>((ref) => 0); // bumped on any 401

final apiClientProvider = Provider<ApiClient>((ref) {
  final jarAsync = ref.watch(cookieJarProvider);
  final jar = jarAsync.maybeWhen(data: (j) => j, orElse: () => null);
  if (jar == null) {
    throw StateError(
        'apiClientProvider read before cookie jar resolved — ensure '
        'cookieJarProvider has emitted before using apiClientProvider');
  }
  return ApiClient(
    cookieJar: jar,
    onUnauthorized: (_) async {
      // Bump signal; router redirects on the next tick.
      ref.read(unauthorizedSignalProvider.notifier).state++;
      ref.read(sessionProvider.notifier).state = null;
    },
  );
});

/// Session — current logged-in user + app config. `null` means not logged in.
final sessionProvider = StateProvider<Session?>((ref) => null);

/// AppBar actions registered by the current screen. Screens write to this
/// provider in their build method to inject screen-specific icon buttons into
/// the AppShell AppBar, eliminating the need for nested Scaffolds with their
/// own AppBars.
final appShellActionsProvider =
    StateProvider<List<Widget>>((ref) => const []);

class Session {
  final User user;
  final AppConfig appConfig;
  Session({required this.user, required this.appConfig});
}

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(ref.watch(apiClientProvider));
});
