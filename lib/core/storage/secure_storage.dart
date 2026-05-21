import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keystore-backed secure storage wrapper.
///
/// Used for: cookie-jar encryption key, OAuth artifacts, anything that must
/// survive process death but never appear in plain SharedPreferences.
class SecureStorage {
  SecureStorage({FlutterSecureStorage? raw})
      : _raw = raw ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(
                encryptedSharedPreferences: true,
              ),
            );

  final FlutterSecureStorage _raw;

  Future<String?> read(String key) => _raw.read(key: key);
  Future<void> write(String key, String value) =>
      _raw.write(key: key, value: value);
  Future<void> delete(String key) => _raw.delete(key: key);
  Future<void> clearAll() => _raw.deleteAll();
}
