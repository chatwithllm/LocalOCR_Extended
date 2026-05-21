/// Environment + base URL resolution.
///
/// Selection order:
///   1. `--dart-define=API_BASE_URL=...` (CI / flavor override)
///   2. `--dart-define=APP_FLAVOR=prod|staging|dev` -> matching default
///   3. Fallback: prod
///
/// Plan §4 — base URL table:
///   prod    : https://extended.npalakurla.com
///   staging : https://staging.npalakurla.com  (verify DNS at build time)
///   dev     : http://10.0.2.2:5001            (Android emulator host loopback)
library;

enum AppFlavor { dev, staging, prod }

class Env {
  Env._();

  static const String _flavorRaw =
      String.fromEnvironment('APP_FLAVOR', defaultValue: 'prod');
  static const String _baseUrlOverride =
      String.fromEnvironment('API_BASE_URL', defaultValue: '');

  static AppFlavor get flavor => switch (_flavorRaw) {
        'dev' => AppFlavor.dev,
        'staging' => AppFlavor.staging,
        _ => AppFlavor.prod,
      };

  static String get baseUrl {
    if (_baseUrlOverride.isNotEmpty) return _baseUrlOverride;
    return switch (flavor) {
      AppFlavor.dev => 'http://10.0.2.2:5001',
      AppFlavor.staging => 'https://staging.npalakurla.com',
      AppFlavor.prod => 'https://extended.npalakurla.com',
    };
  }

  static String get prodWebOrigin => 'https://extended.npalakurla.com';

  static bool get isProd => flavor == AppFlavor.prod;
  static bool get isDev => flavor == AppFlavor.dev;
}
