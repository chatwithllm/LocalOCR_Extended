import 'dart:async';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:flutter/foundation.dart';

import '../errors/app_exception.dart';
import '../util/logger.dart';
import 'env.dart';
import 'interceptors.dart';

/// Single dio instance wrapper. Plan §4.
///
/// Order of interceptors matters:
///   1. CookieManager   — read/write `Cookie` and `Set-Cookie`
///   2. AuthInterceptor — react to 401 after cookies have been written
///   3. LoggingInterceptor (debug only)
///   4. IdempotentRetryInterceptor
class ApiClient {
  ApiClient({
    required this.cookieJar,
    required OnUnauthorized onUnauthorized,
  }) : dio = Dio(
          BaseOptions(
            baseUrl: Env.baseUrl,
            contentType: 'application/json',
            responseType: ResponseType.json,
            followRedirects: true,
            maxRedirects: 5,
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 30),
            sendTimeout: const Duration(seconds: 60),
            validateStatus: (s) => s != null && s < 400,
          ),
        ) {
    dio.interceptors.add(CookieManager(cookieJar));
    dio.interceptors.add(AuthInterceptor(onUnauthorized: onUnauthorized));
    dio.interceptors.add(LoggingInterceptor(enabled: kDebugMode || !Env.isProd));
    dio.interceptors.add(IdempotentRetryInterceptor(dio));
  }

  final Dio dio;
  final PersistCookieJar cookieJar;

  Future<T> get<T>(String path,
      {Map<String, dynamic>? query, Options? options}) async {
    return _run<T>(
        () => dio.get<dynamic>(path, queryParameters: query, options: options));
  }

  Future<T> post<T>(String path,
      {Object? body, Map<String, dynamic>? query, Options? options}) async {
    return _run<T>(() => dio.post<dynamic>(path,
        data: body, queryParameters: query, options: options));
  }

  Future<T> put<T>(String path,
      {Object? body, Map<String, dynamic>? query, Options? options}) async {
    return _run<T>(() => dio.put<dynamic>(path,
        data: body, queryParameters: query, options: options));
  }

  Future<T> patch<T>(String path,
      {Object? body, Map<String, dynamic>? query, Options? options}) async {
    return _run<T>(() => dio.patch<dynamic>(path,
        data: body, queryParameters: query, options: options));
  }

  Future<T> delete<T>(String path,
      {Object? body, Map<String, dynamic>? query, Options? options}) async {
    return _run<T>(() => dio.delete<dynamic>(path,
        data: body, queryParameters: query, options: options));
  }

  Future<T> _run<T>(Future<Response<dynamic>> Function() send) async {
    try {
      final r = await send();
      return r.data as T;
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  AppException _wrap(DioException e) {
    final code = e.response?.statusCode;
    final msg = _extractMessage(e);
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return TimeoutAppException(msg, cause: e);
      case DioExceptionType.cancel:
        return CancelledException(msg, cause: e);
      case DioExceptionType.connectionError:
        return NetworkException(msg, cause: e);
      case DioExceptionType.badCertificate:
      case DioExceptionType.unknown:
      case DioExceptionType.badResponse:
        break;
    }
    if (code == 401) return UnauthorizedException(msg, cause: e);
    if (code == 403) return ForbiddenException(msg, cause: e);
    if (code == 404) return NotFoundException(msg, cause: e);
    if (code == 409) return ConflictException(msg, cause: e);
    if (code != null && code >= 500) {
      return ServerException(msg, statusCode: code, cause: e);
    }
    return ApiException(msg, statusCode: code, cause: e);
  }

  String _extractMessage(DioException e) {
    final body = e.response?.data;
    if (body is Map && body['error'] is String) return body['error'] as String;
    if (body is Map && body['message'] is String) {
      return body['message'] as String;
    }
    return e.message ?? e.toString();
  }
}

/// First-launch diagnostic — write the raw `Set-Cookie` header from
/// `/auth/login` to a debug log so we can confirm Flask's session cookie scope
/// (plan §4 — V-1 RESOLVED first-launch verification task).
void logRawSetCookie(Response response) {
  final headers = response.headers.map['set-cookie'];
  if (headers == null) return;
  appLogger.i('set-cookie raw: $headers');
}
