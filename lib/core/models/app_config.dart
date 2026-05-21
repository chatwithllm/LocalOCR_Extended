/// Mirrors `build_app_config()` at
/// `src/backend/manage_authentication.py:60`. RULE 2.
class AppConfig {
  final String appName;
  final String appSlug;
  final String serviceName;
  final String publicBaseUrlDefault;
  final String requestBaseUrl;
  final AppConfigModules modules;
  final String moduleViewMode;
  final int defaultBackendPort;
  final bool googleOauthEnabled;

  const AppConfig({
    required this.appName,
    required this.appSlug,
    required this.serviceName,
    required this.publicBaseUrlDefault,
    required this.requestBaseUrl,
    required this.modules,
    required this.moduleViewMode,
    required this.defaultBackendPort,
    required this.googleOauthEnabled,
  });

  factory AppConfig.fromJson(Map<String, dynamic> json) => AppConfig(
        appName: (json['app_name'] as String?) ?? 'LocalOCR Extended',
        appSlug: (json['app_slug'] as String?) ?? 'localocr_extended',
        serviceName: (json['service_name'] as String?) ??
            'localocr-extended-backend',
        publicBaseUrlDefault:
            (json['public_base_url_default'] as String?) ?? '',
        requestBaseUrl: (json['request_base_url'] as String?) ?? '',
        modules: AppConfigModules.fromJson(
            (json['modules'] as Map?)?.cast<String, dynamic>() ?? const {}),
        moduleViewMode:
            (json['module_view_mode'] as String?) ?? 'separate',
        defaultBackendPort: ((json['ports'] as Map?)?['default_backend']
                as num?)
                ?.toInt() ??
            8090,
        googleOauthEnabled:
            (json['google_oauth_enabled'] as bool?) ?? false,
      );

  static const AppConfig empty = AppConfig(
    appName: 'LocalOCR Extended',
    appSlug: 'localocr_extended',
    serviceName: 'localocr-extended-backend',
    publicBaseUrlDefault: '',
    requestBaseUrl: '',
    modules: AppConfigModules.empty,
    moduleViewMode: 'separate',
    defaultBackendPort: 8090,
    googleOauthEnabled: false,
  );
}

class AppConfigModules {
  final bool grocery;
  final bool restaurant;
  final bool generalExpense;

  const AppConfigModules({
    required this.grocery,
    required this.restaurant,
    required this.generalExpense,
  });

  factory AppConfigModules.fromJson(Map<String, dynamic> json) =>
      AppConfigModules(
        grocery: (json['grocery'] as bool?) ?? true,
        restaurant: (json['restaurant'] as bool?) ?? false,
        generalExpense: (json['general_expense'] as bool?) ?? true,
      );

  static const AppConfigModules empty = AppConfigModules(
    grocery: true,
    restaurant: false,
    generalExpense: true,
  );
}
