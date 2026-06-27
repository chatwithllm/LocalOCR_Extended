import '../../core/errors/app_exception.dart';

/// Returns a concise, user-facing error message from any thrown value.
String friendlyError(Object error) {
  if (error is AppException) return error.message;
  final msg = error.toString();
  // Strip Dart exception type prefix e.g. "Exception: ..."
  if (msg.startsWith('Exception: ')) return msg.substring(11);
  if (msg.startsWith('FormatException: ')) return 'Invalid data format.';
  if (msg.contains('SocketException') || msg.contains('Connection refused')) {
    return 'Could not reach the server. Check your connection.';
  }
  if (msg.contains('TimeoutException') || msg.contains('timed out')) {
    return 'Request timed out. Try again.';
  }
  if (msg.contains('401') || msg.contains('Unauthorized')) {
    return 'Session expired. Please log in again.';
  }
  if (msg.contains('403') || msg.contains('Forbidden')) {
    return 'You don\'t have permission to do that.';
  }
  if (msg.contains('404') || msg.contains('Not found')) {
    return 'The requested item was not found.';
  }
  // Fall back to raw message, but trim type prefix
  return msg.length > 120 ? '${msg.substring(0, 120)}…' : msg;
}
