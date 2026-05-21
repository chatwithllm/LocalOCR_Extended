/// Typed exception hierarchy for the API layer (plan §4 — error / retry policy).
sealed class AppException implements Exception {
  final String message;
  final int? statusCode;
  final Object? cause;

  const AppException(this.message, {this.statusCode, this.cause});

  @override
  String toString() => '$runtimeType($statusCode): $message';
}

class NetworkException extends AppException {
  const NetworkException(super.message, {super.cause}) : super(statusCode: null);
}

class TimeoutAppException extends AppException {
  const TimeoutAppException(super.message, {super.cause})
      : super(statusCode: null);
}

class CancelledException extends AppException {
  const CancelledException(super.message, {super.cause})
      : super(statusCode: null);
}

class UnauthorizedException extends AppException {
  const UnauthorizedException(super.message, {super.cause})
      : super(statusCode: 401);
}

class ForbiddenException extends AppException {
  const ForbiddenException(super.message, {super.cause})
      : super(statusCode: 403);
}

class NotFoundException extends AppException {
  const NotFoundException(super.message, {super.cause})
      : super(statusCode: 404);
}

class ConflictException extends AppException {
  const ConflictException(super.message, {super.cause})
      : super(statusCode: 409);
}

class ServerException extends AppException {
  const ServerException(super.message, {super.statusCode, super.cause});
}

class ApiException extends AppException {
  const ApiException(super.message, {super.statusCode, super.cause});
}
