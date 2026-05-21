import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../models/app_config.dart';
import '../models/user.dart';

/// Auth repository — login, logout, session, bootstrap, device pairing, OAuth.
/// Mirrors backend JSON shapes from `src/backend/manage_authentication.py`
/// (RULE 2: every key here was read out of the source's `jsonify(...)` site).
class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  Future<LoginResult> login({required String email, required String password}) async {
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.authLogin,
      body: {'email': email, 'password': password},
    );
    final userMap = (data['user'] as Map).cast<String, dynamic>();
    final appCfg = (data['app_config'] as Map?)?.cast<String, dynamic>();
    return LoginResult(
      user: User.fromJson(userMap),
      appConfig: appCfg == null ? AppConfig.empty : AppConfig.fromJson(appCfg),
    );
  }

  Future<MeResult?> me() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.authMe);
    if (data['authenticated'] != true) return null;
    final userMap = (data['user'] as Map).cast<String, dynamic>();
    final appCfg = (data['app_config'] as Map?)?.cast<String, dynamic>();
    return MeResult(
      user: User.fromJson(userMap),
      appConfig: appCfg == null ? AppConfig.empty : AppConfig.fromJson(appCfg),
    );
  }

  Future<void> logout() async {
    await _api.post<Map<String, dynamic>>(Endpoints.authLogout);
  }

  Future<BootstrapInfo> bootstrap() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.authBootstrapInfo);
    return BootstrapInfo(
      defaultEmail: data['default_email'] as String?,
      hasUsers: (data['has_users'] as bool?) ?? false,
      appConfig: AppConfig.fromJson(
          (data['app_config'] as Map?)?.cast<String, dynamic>() ?? const {}),
    );
  }

  Future<AppConfig> appConfig() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.authAppConfig);
    return AppConfig.fromJson(data);
  }

  Future<void> forgotPassword(String email) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.authForgotPassword,
      body: {'email': email},
    );
  }

  Future<bool> googleOauthEnabled() async {
    try {
      final data = await _api.get<Map<String, dynamic>>(
        Endpoints.authOauthGoogleStatus,
      );
      return (data['enabled'] as bool?) ?? false;
    } catch (_) {
      return false;
    }
  }

  /// Start a device-pairing session (F-107). Backend source:
  /// `manage_authentication.py:978` — returns pairing_token, pairing_url,
  /// qr_image_url, expires_at, device_name, scope, status, allowed_pages.
  Future<DevicePairingStart> devicePairingStart({
    String? deviceName,
    String? scope,
    String? currentBaseUrl,
  }) async {
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.authDevicePairingStart,
      body: {
        if (deviceName != null && deviceName.isNotEmpty) 'device_name': deviceName,
        if (scope != null && scope.isNotEmpty) 'scope': scope,
        if (currentBaseUrl != null && currentBaseUrl.isNotEmpty)
          'current_base_url': currentBaseUrl,
      },
    );
    return DevicePairingStart(
      pairingToken: data['pairing_token'] as String,
      pairingUrl: data['pairing_url'] as String,
      qrImageUrl: data['qr_image_url'] as String,
      expiresAt: data['expires_at'] as String?,
      deviceName: data['device_name'] as String?,
      scope: data['scope'] as String?,
      status: data['status'] as String?,
    );
  }

  /// Poll pairing status (F-112 polling target). Backend source:
  /// `manage_authentication.py:1112`. May return statuses:
  /// `pending|approved|claimed|rejected|expired|error`. When `approved` or
  /// `claimed`, the server has already set our session cookie via
  /// `_set_trusted_device_session(...)` and the response includes `user` +
  /// `app_config`.
  Future<DevicePairingStatus> devicePairingStatus(String token) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.authDevicePairingStatus(token),
    );
    final status = (data['status'] as String?) ?? 'unknown';
    final authenticated = (data['authenticated'] as bool?) ?? false;
    User? user;
    AppConfig appCfg = AppConfig.empty;
    if (authenticated) {
      final userMap = (data['user'] as Map?)?.cast<String, dynamic>();
      if (userMap != null) user = User.fromJson(userMap);
      final cfgMap = (data['app_config'] as Map?)?.cast<String, dynamic>();
      if (cfgMap != null) appCfg = AppConfig.fromJson(cfgMap);
    }
    return DevicePairingStatus(
      status: status,
      authenticated: authenticated,
      user: user,
      appConfig: appCfg,
      errorMessage: data['error'] as String?,
    );
  }

  /// Approve a pairing request (F-119). Backend source:
  /// `manage_authentication.py:1203`. Accepts admin creds inline via
  /// `admin_email` + `admin_password` (see `_get_admin_actor_from_request_payload`).
  Future<void> devicePairingApprove({
    required String pairingToken,
    int? linkedUserId,
    String? deviceName,
    String? scope,
    String? adminEmail,
    String? adminPassword,
  }) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.authDevicePairingApprove,
      body: {
        'pairing_token': pairingToken,
        if (linkedUserId != null) 'linked_user_id': linkedUserId,
        if (deviceName != null && deviceName.isNotEmpty) 'device_name': deviceName,
        if (scope != null && scope.isNotEmpty) 'scope': scope,
        if (adminEmail != null && adminEmail.isNotEmpty) 'admin_email': adminEmail,
        if (adminPassword != null && adminPassword.isNotEmpty)
          'admin_password': adminPassword,
      },
    );
  }

  /// Reject a pairing request (F-118). Backend source:
  /// `manage_authentication.py:1317`. Same admin-auth shape as approve.
  Future<void> devicePairingReject({
    required String pairingToken,
    String? adminEmail,
    String? adminPassword,
  }) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.authDevicePairingReject,
      body: {
        'pairing_token': pairingToken,
        if (adminEmail != null && adminEmail.isNotEmpty) 'admin_email': adminEmail,
        if (adminPassword != null && adminPassword.isNotEmpty)
          'admin_password': adminPassword,
      },
    );
  }
}

class LoginResult {
  final User user;
  final AppConfig appConfig;
  LoginResult({required this.user, required this.appConfig});
}

class MeResult {
  final User user;
  final AppConfig appConfig;
  MeResult({required this.user, required this.appConfig});
}

class BootstrapInfo {
  final String? defaultEmail;
  final bool hasUsers;
  final AppConfig appConfig;
  BootstrapInfo(
      {required this.defaultEmail,
      required this.hasUsers,
      required this.appConfig});
}

/// POST /auth/device-pairing/start response shape — mirrors
/// `manage_authentication.py:1006`.
class DevicePairingStart {
  final String pairingToken;
  final String pairingUrl;
  final String qrImageUrl;
  final String? expiresAt;
  final String? deviceName;
  final String? scope;
  final String? status;
  DevicePairingStart({
    required this.pairingToken,
    required this.pairingUrl,
    required this.qrImageUrl,
    required this.expiresAt,
    required this.deviceName,
    required this.scope,
    required this.status,
  });
}

/// GET /auth/device-pairing/status/<token> response shape — mirrors
/// `manage_authentication.py:1117`/`:1136`/`:1153`/`:1166`.
class DevicePairingStatus {
  final String status;
  final bool authenticated;
  final User? user;
  final AppConfig appConfig;
  final String? errorMessage;
  DevicePairingStatus({
    required this.status,
    required this.authenticated,
    required this.user,
    required this.appConfig,
    required this.errorMessage,
  });

  bool get isTerminal =>
      status == 'approved' || status == 'claimed' || status == 'rejected' ||
      status == 'expired' || status == 'error';
}
