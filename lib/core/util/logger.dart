import 'package:flutter/foundation.dart';
import 'package:logger/logger.dart';

/// Structured logger used by every screen + repository per RULE 6 carry-over.
///
/// Pattern: `logger.i("loaded N <thing>")` on every primary screen load so
/// `adb logcat` validation can grep for it.
final Logger appLogger = Logger(
  level: kReleaseMode ? Level.info : Level.debug,
  printer: PrettyPrinter(
    methodCount: 0,
    errorMethodCount: 5,
    lineLength: 100,
    colors: false,
    printEmojis: false,
    dateTimeFormat: DateTimeFormat.onlyTimeAndSinceStart,
  ),
);
