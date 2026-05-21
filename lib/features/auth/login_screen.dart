import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/env.dart';
import '../../core/auth/auth_repository.dart';
import '../../core/errors/app_exception.dart';
import '../../core/providers.dart';
import '../../core/util/logger.dart';

/// Login screen. Covers registry rows F-101..F-120.
///
/// RULE 1 pre-flight grep (plan §4): every endpoint referenced here was
/// confirmed via `grep -nE "@auth_bp.route" src/backend/manage_authentication.py`.
/// RULE 13 decomposition: device-approval inline card + invite landing
/// overlay + pair-this-device modal are sub-widgets with their own state.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({
    super.key,
    this.nextPath,
    this.inviteToken,
    this.pairDeviceToken,
  });

  final String? nextPath;
  final String? inviteToken;
  final String? pairDeviceToken;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _busy = false;
  String? _error;
  bool _showPass = false;
  bool _googleEnabled = false;
  bool _inviteVisible = false;

  @override
  void initState() {
    super.initState();
    _inviteVisible = (widget.inviteToken ?? '').isNotEmpty;
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    try {
      final repo = ref.read(authRepositoryProvider);
      final info = await repo.bootstrap();
      if (!mounted) return;
      if (info.defaultEmail != null && _emailCtrl.text.isEmpty) {
        _emailCtrl.text = info.defaultEmail!;
      }
      setState(() => _googleEnabled = info.appConfig.googleOauthEnabled);
      appLogger.i('login bootstrap loaded — has_users=${info.hasUsers} '
          'google_oauth=${info.appConfig.googleOauthEnabled}');
    } catch (e) {
      appLogger.w('bootstrap prefill failed: $e');
    }
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _emailCtrl.text.trim();
    final pass = _passCtrl.text;
    if (email.isEmpty || pass.isEmpty) {
      setState(() => _error = 'Email and password are required');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .login(email: email, password: pass);
      ref.read(sessionProvider.notifier).state = Session(
        user: result.user,
        appConfig: result.appConfig,
      );
      appLogger.i('loaded 1 session for user=${result.user.id}');
      if (!mounted) return;
      final next = widget.nextPath ?? '/dashboard';
      context.go(next);
    } on AppException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _forgot() async {
    final email = _emailCtrl.text.trim();
    if (email.isEmpty) {
      setState(() => _error = 'Enter your email first');
      return;
    }
    try {
      await ref.read(authRepositoryProvider).forgotPassword(email);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text(
                'If that account exists, the admin can now see the reset request.')),
      );
    } on AppException catch (e) {
      setState(() => _error = e.message);
    }
  }

  Future<void> _googleSignIn() async {
    // F-105 — deferred per pubspec NOTE (plan §4 / BL-A7): the WebView OAuth
    // capture needs flutter_inappwebview cookie extraction (blocked by AGP 9
    // proguard-android.txt issue) OR flutter_web_auth_2 with a custom-scheme
    // backend redirect. Neither is in pubspec yet. Until then we show a clear
    // message instead of pretending to start the flow.
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
            'Google sign-in is being packaged for Android — coming soon. Use email/password for now.'),
      ),
    );
  }

  Future<void> _openPairingSheet() async {
    setState(() => _error = null);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => const _DevicePairingSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hasPair = (widget.pairDeviceToken ?? '').isNotEmpty;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_inviteVisible)
                    _InviteLandingCard(
                      onGoogle: _googleEnabled ? _googleSignIn : null,
                      onDismiss: () => setState(() => _inviteVisible = false),
                    ),
                  if (_inviteVisible) const SizedBox(height: 16),
                  if (hasPair) ...[
                    _DeviceApprovalInlineCard(
                      pairingToken: widget.pairDeviceToken!,
                    ),
                    const SizedBox(height: 16),
                  ],
                  Card(
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                      side: BorderSide(color: cs.outlineVariant),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('LocalOCR Extended',
                              textAlign: TextAlign.center,
                              style:
                                  Theme.of(context).textTheme.headlineSmall),
                          const SizedBox(height: 4),
                          Text('Sign in to continue',
                              textAlign: TextAlign.center,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(color: cs.outline)),
                          const SizedBox(height: 24),
                          TextField(
                            key: const Key('auth-email-input'),
                            controller: _emailCtrl,
                            autofillHints: const [AutofillHints.username],
                            keyboardType: TextInputType.emailAddress,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'Email or username',
                              prefixIcon: Icon(Icons.person_outline),
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            key: const Key('auth-password-input'),
                            controller: _passCtrl,
                            obscureText: !_showPass,
                            autofillHints: const [AutofillHints.password],
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              border: const OutlineInputBorder(),
                              suffixIcon: IconButton(
                                key: const Key('auth-password-toggle'),
                                tooltip: _showPass
                                    ? 'Hide password'
                                    : 'Show password',
                                icon: Icon(_showPass
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined),
                                onPressed: () => setState(
                                    () => _showPass = !_showPass),
                              ),
                            ),
                          ),
                          if (_error != null) ...[
                            const SizedBox(height: 12),
                            Text(_error!,
                                style: TextStyle(color: cs.error),
                                textAlign: TextAlign.center),
                          ],
                          const SizedBox(height: 16),
                          FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: _busy
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2),
                                  )
                                : const Text('Sign in'),
                          ),
                          const SizedBox(height: 8),
                          TextButton(
                            onPressed: _busy ? null : _forgot,
                            child: const Text('Forgot password?'),
                          ),
                          if (_googleEnabled) ...[
                            const SizedBox(height: 8),
                            OutlinedButton.icon(
                              key: const Key('auth-google-btn'),
                              icon: const Icon(Icons.account_circle_outlined),
                              label: const Text('Continue with Google'),
                              onPressed: _busy ? null : _googleSignIn,
                            ),
                          ],
                          const SizedBox(height: 8),
                          OutlinedButton.icon(
                            icon: const Icon(Icons.phonelink_outlined),
                            label: const Text('Pair this device'),
                            onPressed: _busy ? null : _openPairingSheet,
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// F-109/110/111 — Invite landing overlay. Shown when the route carries an
/// invite token (deep link `${baseUrl}/auth/invite/<token>` or
/// `?invite=<token>` on the SPA). Web parity: `invite-landing` block in
/// `src/frontend/index.html`.
class _InviteLandingCard extends StatelessWidget {
  const _InviteLandingCard({required this.onGoogle, required this.onDismiss});
  final VoidCallback? onGoogle;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      elevation: 0,
      color: cs.secondaryContainer,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'You have been invited',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'Sign in below to accept the invitation and join this household.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                if (onGoogle != null)
                  OutlinedButton.icon(
                    key: const Key('invite-google-btn'),
                    onPressed: onGoogle,
                    icon: const Icon(Icons.account_circle_outlined, size: 18),
                    label: const Text('Continue with Google'),
                  ),
                if (onGoogle != null) const SizedBox(width: 8),
                TextButton(
                  onPressed: onDismiss,
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// F-112..F-119 — Inline device-approval card. Shown when LoginScreen is
/// opened with `?pair_device=<token>` (deep link from the QR landing page
/// `${baseUrl}/auth/pair-device/<token>`). The approve/reject endpoints
/// accept inline admin credentials (see `_get_admin_actor_from_request_payload`
/// in `manage_authentication.py:599`), so an admin can approve without first
/// going through the normal /auth/login flow.
class _DeviceApprovalInlineCard extends ConsumerStatefulWidget {
  const _DeviceApprovalInlineCard({required this.pairingToken});
  final String pairingToken;

  @override
  ConsumerState<_DeviceApprovalInlineCard> createState() =>
      _DeviceApprovalInlineCardState();
}

class _DeviceApprovalInlineCardState
    extends ConsumerState<_DeviceApprovalInlineCard> {
  final _deviceNameCtrl = TextEditingController();
  // F-114 — registry says "select" populated from GET /auth/users, but that
  // endpoint requires admin auth which the Login screen does not yet have.
  // Falling back to a numeric text field (linked_user_id) per RULE 9 / 🔄:
  // verb still satisfied by user picking an id; defaults to the admin actor
  // when empty (backend coalesces).
  final _linkedUserIdCtrl = TextEditingController();
  final _adminEmailCtrl = TextEditingController();
  final _adminPassCtrl = TextEditingController();
  String _scope = 'shared_household';
  bool _busy = false;
  String? _error;
  String? _ok;

  @override
  void dispose() {
    _deviceNameCtrl.dispose();
    _linkedUserIdCtrl.dispose();
    _adminEmailCtrl.dispose();
    _adminPassCtrl.dispose();
    super.dispose();
  }

  Future<void> _act({required bool approve}) async {
    setState(() {
      _busy = true;
      _error = null;
      _ok = null;
    });
    try {
      final repo = ref.read(authRepositoryProvider);
      final email = _adminEmailCtrl.text.trim();
      final pass = _adminPassCtrl.text;
      if (email.isEmpty || pass.isEmpty) {
        setState(() => _error = 'Admin email and password are required');
        return;
      }
      if (approve) {
        int? linkedUserId;
        final idText = _linkedUserIdCtrl.text.trim();
        if (idText.isNotEmpty) {
          linkedUserId = int.tryParse(idText);
          if (linkedUserId == null) {
            setState(() => _error = 'Linked user id must be a number');
            return;
          }
        }
        await repo.devicePairingApprove(
          pairingToken: widget.pairingToken,
          linkedUserId: linkedUserId,
          deviceName: _deviceNameCtrl.text.trim(),
          scope: _scope,
          adminEmail: email,
          adminPassword: pass,
        );
        setState(() => _ok = 'Device approved.');
      } else {
        await repo.devicePairingReject(
          pairingToken: widget.pairingToken,
          adminEmail: email,
          adminPassword: pass,
        );
        setState(() => _ok = 'Device rejected.');
      }
    } on AppException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // F-112 — status pill
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: cs.tertiaryContainer,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text('Device awaiting approval',
                  style: TextStyle(color: cs.onTertiaryContainer)),
            ),
            const SizedBox(height: 12),
            // F-113
            TextField(
              key: const Key('device-approval-inline-name'),
              controller: _deviceNameCtrl,
              decoration: const InputDecoration(
                labelText: 'Device name (optional)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            // F-114
            TextField(
              key: const Key('device-approval-inline-linked-user'),
              controller: _linkedUserIdCtrl,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'Linked user id (optional — defaults to you)',
                border: OutlineInputBorder(),
                helperText:
                    '/auth/users requires admin login; enter id directly here.',
              ),
            ),
            const SizedBox(height: 8),
            // F-115
            DropdownButtonFormField<String>(
              key: const Key('device-approval-inline-scope'),
              initialValue: _scope,
              decoration: const InputDecoration(
                labelText: 'Scope',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(
                    value: 'shared_household',
                    child: Text('Shared household')),
                DropdownMenuItem(
                    value: 'kitchen_display',
                    child: Text('Kitchen display')),
                DropdownMenuItem(
                    value: 'read_only', child: Text('Read only')),
              ],
              onChanged: _busy ? null : (v) => setState(() => _scope = v!),
            ),
            const SizedBox(height: 8),
            // F-116
            TextField(
              key: const Key('device-approval-inline-email'),
              controller: _adminEmailCtrl,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Admin email',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            // F-117
            TextField(
              key: const Key('device-approval-inline-password'),
              controller: _adminPassCtrl,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Admin password',
                border: OutlineInputBorder(),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: cs.error)),
            ],
            if (_ok != null) ...[
              const SizedBox(height: 8),
              Text(_ok!, style: TextStyle(color: cs.primary)),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _busy ? null : () => _act(approve: false),
                    child: const Text('Reject'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed: _busy ? null : () => _act(approve: true),
                    child: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Approve'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// F-107 — Pair-this-device bottom sheet. POSTs `/auth/device-pairing/start`,
/// shows the QR image + pairing URL, polls `/auth/device-pairing/status/<token>`
/// every 2s. When the server reports `approved` or `claimed`, the session
/// cookie has already been set (see `_set_trusted_device_session` at
/// `manage_authentication.py:1134`) and we populate sessionProvider so the
/// router redirects to /dashboard.
class _DevicePairingSheet extends ConsumerStatefulWidget {
  const _DevicePairingSheet();

  @override
  ConsumerState<_DevicePairingSheet> createState() =>
      _DevicePairingSheetState();
}

class _DevicePairingSheetState extends ConsumerState<_DevicePairingSheet> {
  DevicePairingStart? _start;
  String _status = 'starting';
  String? _error;
  Timer? _poll;
  static const _pollEvery = Duration(seconds: 2);
  static const _maxPolls = 150; // 5 minutes at 2s each
  int _polled = 0;

  @override
  void initState() {
    super.initState();
    _kick();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _kick() async {
    try {
      final repo = ref.read(authRepositoryProvider);
      final start = await repo.devicePairingStart(
        deviceName: 'Android Phone',
        scope: 'shared_household',
        currentBaseUrl: Env.baseUrl,
      );
      if (!mounted) return;
      setState(() {
        _start = start;
        _status = start.status ?? 'pending';
      });
      _poll = Timer.periodic(_pollEvery, (_) => _pollOnce());
      appLogger.i('device-pairing started — token=${start.pairingToken.substring(0, 6)}…');
    } on AppException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _pollOnce() async {
    final s = _start;
    if (s == null) return;
    _polled++;
    if (_polled > _maxPolls) {
      _poll?.cancel();
      if (mounted) setState(() => _status = 'expired');
      return;
    }
    try {
      final repo = ref.read(authRepositoryProvider);
      final res = await repo.devicePairingStatus(s.pairingToken);
      if (!mounted) return;
      setState(() => _status = res.status);
      if (res.authenticated && res.user != null) {
        _poll?.cancel();
        ref.read(sessionProvider.notifier).state = Session(
          user: res.user!,
          appConfig: res.appConfig,
        );
        appLogger.i('loaded 1 session for user=${res.user!.id} (paired)');
        if (mounted) {
          Navigator.of(context).pop();
          if (mounted) GoRouter.of(context).go('/dashboard');
        }
        return;
      }
      if (res.isTerminal) {
        _poll?.cancel();
      }
    } catch (e) {
      // Soft-fail individual polls; keep trying until timeout.
      appLogger.w('pairing poll failed (transient): $e');
    }
  }

  Future<void> _copy(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Copied')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = _start;
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: 16 + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Pair this device',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(
              'Scan the QR or open the URL on a logged-in browser to approve '
              'this Android device.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: cs.outline,
                  ),
            ),
            const SizedBox(height: 16),
            if (_error != null)
              Text(_error!, style: TextStyle(color: cs.error))
            else if (s == null)
              const Center(child: CircularProgressIndicator())
            else ...[
              AspectRatio(
                aspectRatio: 1,
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: cs.outlineVariant),
                  ),
                  padding: const EdgeInsets.all(8),
                  child: Image.network(
                    s.qrImageUrl,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Center(
                      child: Icon(Icons.qr_code_2_outlined, size: 96),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              SelectableText(
                s.pairingUrl,
                style: const TextStyle(fontFamily: 'monospace'),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: () => _copy(s.pairingUrl),
                icon: const Icon(Icons.copy_outlined),
                label: const Text('Copy link'),
              ),
              const SizedBox(height: 12),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: cs.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text('Status: $_status',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: cs.onSurface)),
              ),
            ],
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      ),
    );
  }
}
