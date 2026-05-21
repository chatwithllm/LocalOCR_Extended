import 'dart:async';

import 'package:dio/dio.dart';
import 'package:logger/logger.dart';

import '../util/logger.dart';

/// Callback fired by [AuthInterceptor] on 401. Implementation should clear
/// session state + cookie jar + redirect to /login. We keep it as a callback so
/// the interceptor stays decoupled from go_router / Riverpod.
typedef OnUnauthorized = FutureOr<void> Function(RequestOptions originalRequest);

/// Plan §4 interceptor 2 — handle 401 -> wipe session + redirect to /login.
/// Does NOT retry the 401'd request (prevents stale-cookie retry loops).
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required this.onUnauthorized});

  final OnUnauthorized onUnauthorized;
  bool _firing = false;

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final status = err.response?.statusCode;
    if (status == 401 && !_firing) {
      _firing = true;
      try {
        await onUnauthorized(err.requestOptions);
      } catch (e) {
        appLogger.w('auth-interceptor onUnauthorized callback failed: $e');
      } finally {
        _firing = false;
      }
    }
    handler.next(err);
  }
}

/// Plan §4 interceptor 3 — structured JSON log, redacted bodies for login /
/// forgot-password paths.
class LoggingInterceptor extends Interceptor {
  LoggingInterceptor({this.enabled = true});

  final bool enabled;
  static const _redactPaths = <String>{
    '/auth/login',
    '/auth/forgot-password',
  };

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (enabled) {
      options.extra['__start_ms'] = DateTime.now().millisecondsSinceEpoch;
      appLogger.d({
        'event': 'request',
        'method': options.method,
        'path': options.path,
      });
    }
    handler.next(options);
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    if (enabled) {
      final start =
          response.requestOptions.extra['__start_ms'] as int?;
      final ms = start == null
          ? null
          : DateTime.now().millisecondsSinceEpoch - start;
      final redacted = _redactPaths.contains(response.requestOptions.path);
      appLogger.i({
        'event': 'response',
        'method': response.requestOptions.method,
        'path': response.requestOptions.path,
        'status': response.statusCode,
        'durationMs': ms,
        if (redacted) 'body': '[redacted]',
      });
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (enabled) {
      final start = err.requestOptions.extra['__start_ms'] as int?;
      final ms = start == null
          ? null
          : DateTime.now().millisecondsSinceEpoch - start;
      appLogger.w({
        'event': 'error',
        'method': err.requestOptions.method,
        'path': err.requestOptions.path,
        'status': err.response?.statusCode,
        'type': err.type.name,
        'durationMs': ms,
      });
    }
    handler.next(err);
  }
}

/// Plan §4 interceptor 4 — retry idempotent verbs on 5xx + network errors only.
/// POST is NEVER retried (would duplicate receipt uploads / cash transactions).
class IdempotentRetryInterceptor extends Interceptor {
  IdempotentRetryInterceptor(this.dio, {Logger? log}) : _log = log ?? appLogger;

  final Dio dio;
  final Logger _log;
  static const _delays = [
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 4),
  ];
  static const _idempotent = {'GET', 'PUT', 'DELETE', 'HEAD'};

  bool _shouldRetry(DioException err) {
    final m = err.requestOptions.method.toUpperCase();
    if (!_idempotent.contains(m)) return false;
    final t = err.type;
    if (t == DioExceptionType.connectionTimeout ||
        t == DioExceptionType.connectionError ||
        t == DioExceptionType.sendTimeout ||
        t == DioExceptionType.receiveTimeout) {
      return true;
    }
    final s = err.response?.statusCode;
    return s != null && s >= 500 && s < 600;
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final attempt = (err.requestOptions.extra['__retry_attempt'] as int?) ?? 0;
    if (attempt >= _delays.length || !_shouldRetry(err)) {
      handler.next(err);
      return;
    }
    final delay = _delays[attempt];
    _log.w('retry attempt=${attempt + 1} path=${err.requestOptions.path} '
        'after=${delay.inSeconds}s');
    await Future<void>.delayed(delay);
    final req = err.requestOptions;
    req.extra['__retry_attempt'] = attempt + 1;
    try {
      final resp = await dio.fetch<dynamic>(req);
      handler.resolve(resp);
    } on DioException catch (e) {
      handler.next(e);
    }
  }
}
