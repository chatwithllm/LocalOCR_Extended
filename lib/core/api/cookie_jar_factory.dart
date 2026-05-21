import 'dart:io';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:path_provider/path_provider.dart';

/// Build a [PersistCookieJar] backed by `<appdir>/.cookies/` (plan §4).
///
/// `ignoreExpires: false` — Flask session cookies are short-lived and we want
/// the jar to honor expiry. Host-only + SameSite=Lax is honored natively.
Future<PersistCookieJar> buildCookieJar() async {
  final dir = await getApplicationDocumentsDirectory();
  final cookiesPath = '${dir.path}${Platform.pathSeparator}.cookies';
  return PersistCookieJar(
    ignoreExpires: false,
    storage: FileStorage(cookiesPath),
  );
}
