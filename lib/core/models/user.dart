/// Mirrors `serialize_user()` at `src/backend/manage_authentication.py:463`.
/// Every key here was read out of the source dict — RULE 2.
///
/// Dart RULE 18 inversion: every snake_case backend key needs an explicit
/// mapping. We do this in `fromJson` (no `convertFromSnakeCase` in Dart).
class User {
  final int id;
  final String? name;
  final String? email;
  final String? avatarEmoji;
  final String role;
  final bool isActive;
  final bool hasPassword;
  final bool hasApiToken;
  final bool hasGoogle;
  final String? googleEmail;
  final bool passwordResetRequested;
  final String? passwordResetRequestedAt;
  final List<String> allowedPages;
  final bool hasPlaidVisibility;
  final bool allowWrite;
  final List<String> allowedIps;
  final bool isService;
  final String? lastLoginAt;
  final String? currentSessionStartedAt;
  final String? lastLoginUserAgent;
  final String? createdAt;
  final String? updatedAt;

  const User({
    required this.id,
    required this.name,
    required this.email,
    required this.avatarEmoji,
    required this.role,
    required this.isActive,
    required this.hasPassword,
    required this.hasApiToken,
    required this.hasGoogle,
    required this.googleEmail,
    required this.passwordResetRequested,
    required this.passwordResetRequestedAt,
    required this.allowedPages,
    required this.hasPlaidVisibility,
    required this.allowWrite,
    required this.allowedIps,
    required this.isService,
    required this.lastLoginAt,
    required this.currentSessionStartedAt,
    required this.lastLoginUserAgent,
    required this.createdAt,
    required this.updatedAt,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: (json['id'] as num).toInt(),
        name: json['name'] as String?,
        email: json['email'] as String?,
        avatarEmoji: json['avatar_emoji'] as String?,
        role: (json['role'] as String?) ?? 'user',
        isActive: (json['is_active'] as bool?) ?? false,
        hasPassword: (json['has_password'] as bool?) ?? false,
        hasApiToken: (json['has_api_token'] as bool?) ?? false,
        hasGoogle: (json['has_google'] as bool?) ?? false,
        googleEmail: json['google_email'] as String?,
        passwordResetRequested:
            (json['password_reset_requested'] as bool?) ?? false,
        passwordResetRequestedAt:
            json['password_reset_requested_at'] as String?,
        allowedPages: (json['allowed_pages'] as List?)?.cast<String>() ?? const [],
        hasPlaidVisibility: (json['has_plaid_visibility'] as bool?) ?? false,
        allowWrite: (json['allow_write'] as bool?) ?? false,
        allowedIps: (json['allowed_ips'] as List?)?.cast<String>() ?? const [],
        isService: (json['is_service'] as bool?) ?? false,
        lastLoginAt: json['last_login_at'] as String?,
        currentSessionStartedAt: json['current_session_started_at'] as String?,
        lastLoginUserAgent: json['last_login_user_agent'] as String?,
        createdAt: json['created_at'] as String?,
        updatedAt: json['updated_at'] as String?,
      );
}
