# ANDROID_APP_PLAN — LocalOCR_Extended → android port

Project: LocalOCR_Extended
Target: Android (Flutter)
Prod URL: https://extended.npalakurla.com
Bundle ID: com.localocr.extended.localocr.extended (prod flavor — see V-5 / G-3)
Feature parity registry: FEATURE_PARITY_REGISTRY.md (974 lines, 22 screens, 542 rows)
Backend: Flask blueprints under src/backend/ — 216 routes across 26 blueprints + 8 app-level (RULE 1 grep audited)
Stage: PLAN (orchestrator), 7 sub-agents
Generated: 2026-05-21

## §1 Tech stack decisions (Agent 1)
- **Framework**: Flutter 3.24 (stable channel). Justification: this is a greenfield Android port with no pre-existing `android/`, `build.gradle`, or `pubspec.yaml`, so the orchestrator default (Flutter) applies without a migration penalty. Flutter's Material 3 + gesture stack covers every interaction verb in `FEATURE_PARITY_REGISTRY.md` — drag-slider (`Slider` / `RangeSlider`), long-press (`GestureDetector.onLongPress`), swipe-to-action (`Dismissible`), hold-alt-action (`onLongPressStart` + `HardwareKeyboard.instance.isMetaPressed` equivalent for the Android "hold to reveal" pattern), and chip-toggle (`FilterChip` / `ChoiceChip`). A single codebase forward-compiles to iOS once the Android port is parity-locked. `flutter doctor` is the pre-flight tool the orchestrator already calls in stage scripts, and the Dart→Flask JSON pipeline (`dio` + `freezed`/`json_serializable`) maps 1:1 to the Swift `Codable` + `APIClient` pattern documented in `LocalOCR.macOS/` so we inherit its lessons (especially RULE 18) instead of rediscovering them.
- **Min SDK**: 26 (Android 8.0 Oreo) — required floor for `flutter_secure_storage` 9.x Android Keystore + EncryptedSharedPreferences APIs and `mobile_scanner` 5.x camera natives (V-10 reconciled with §5). Covers ~94% of active Play Store devices; modern TLS (BoringSSL via Conscrypt) for Let's Encrypt chain is also satisfied at 26+.
- **Target SDK**: 35 (Android 15) — current Google Play policy floor as of 2025-08-31 for new app submissions and updates.
- **Compile SDK**: 35 — must equal or exceed targetSdk; matches Flutter 3.24's default `flutter.compileSdkVersion`.
- **Dart SDK**: `>=3.5.0 <4.0.0` — pairs with Flutter 3.24, enables sealed classes / pattern matching used by `freezed` 2.5+ unions for `AsyncValue`-shaped API responses.
- **Persistence layer**: **Drift 2.20+** (typed SQL on top of SQLite) plus **`flutter_secure_storage` 9.x** (wraps Android Keystore + EncryptedSharedPreferences) for the session cookie, OAuth tokens, and the `FERNET_SECRET_KEY`-equivalent client-side material. Drift is preferred over Isar/Hive specifically because `agent-rules.md` **RULE 2** requires "mirror backend JSON verbatim" — Drift lets us declare tables that 1:1 mirror the `jsonify({...})` payloads from `src/backend/*.py` blueprints, with compile-time column typing that catches shape drift the way Swift's `Codable` decoder catches it on macOS. Isar's object-graph model and Hive's untyped boxes both invite ad-hoc schema-shaping that has historically caused the snake/camel drift bugs RULE 18 documents. Cookie jar is stored in `flutter_secure_storage` (NOT in Drift) so it survives `clear-app-data` only when the user explicitly logs out.
- **Networking layer**: **`dio` 5.x** + **`dio_cookie_manager` 3.x** (backed by `cookie_jar` 4.x with `PersistCookieJar` writing to `getApplicationDocumentsDirectory()`) + **`dio_smart_retry` 7.x**. Justification: the Flask backend in `handle_authentication.py` uses cookie-based session auth (Flask `session` signed with `SECRET_KEY`), so the client MUST persist the cookie jar across cold launches — `dio_cookie_manager` + `PersistCookieJar` is the canonical Dart implementation. `dio` also gives us `FormData` + `MultipartFile.fromFile` for receipt-photo and product-snapshot uploads (replacing the web `FormData` + `fetch` flow), per-request interceptors for the auth-redirect handling the SPA does today, and pluggable retry for the OpenRouter-relayed endpoints that occasionally 5xx. The bare `http` package was rejected because it has no first-party cookie jar and no interceptor model — we would re-implement both.
- **JSON codegen**: **`freezed` 2.5+** + **`json_serializable` 6.8+** + **`json_annotation` 4.9+**. Every response model is a `@freezed` class with `fromJson` / `toJson` generated, and **every field carries an explicit `@JsonKey(name: 'snake_case_from_flask')`** annotation. **TRAP CALLOUT — Dart has no `JSONDecoder.KeyDecodingStrategy.convertFromSnakeCase` equivalent**: `json_serializable` will not auto-convert `total_amount` → `totalAmount`. This is the inverse of macOS RULE 18 — instead of "don't declare snake_case CodingKey rawValues because the decoder auto-converts", the Dart rule is "you MUST declare `@JsonKey(name: 'total_amount')` on every field whose Flask key is snake_case, because nothing converts for you." Silent `null` will appear in any field where the annotation is missing or misspelled. We will encode this as a project lint (custom_lint rule or a CI grep) so no `@freezed` response model ships without explicit `@JsonKey` on every field, matching the rigor RULE 2 demands.
- **State management**: **`flutter_riverpod` 2.5+** (with `riverpod_generator` for typesafe providers). Chosen over `bloc` for terseness on a port where most screens are "fetch endpoint → render list/detail" — `AsyncValue<T>` directly mirrors the loading/error/data tri-state the SPA's fetch wrappers handle today, and `ref.invalidate(provider)` cleanly mirrors the web's "pull-to-refresh re-fetch" pattern. `setState` is **banned** for any screen-level data that originates from the backend; it is allowed only for ephemeral widget state (text-field focus, expansion-tile open/closed). Bloc remains a fallback if the user has a strong preference, but Riverpod is the recommendation.
- **Image handling**: `cached_network_image` 3.4+ for thumbnail and receipt-image caching (replaces the SPA's browser HTTP cache + IndexedDB fallback), `flutter_image_compress` 2.3+ to keep receipt uploads under the Flask 16 MB `MAX_CONTENT_LENGTH` ceiling.
- **Camera/barcode**: `mobile_scanner` 5.x for QR / barcode scanning (replaces the web `Html5Qrcode` integration in `static/js/scanner*.js`), `image_picker` 1.1+ for gallery selection, `camera` 0.11+ for live receipt-capture preview when the user wants a controlled capture flow instead of the system camera intent.
- **Charts**: `fl_chart` 0.69+ for the sparkline + spending bar visualisations (replaces the hand-rolled SVG in the web `_renderReceiptsActivityChart` function). `fl_chart` covers `BarChart`, `LineChart`, and the small-multiples pattern the spending drilldown uses.
- **Local notifications**: `flutter_local_notifications` 17.x for budget alerts and "receipt processed" toasts (replaces the web `Notification.requestPermission()` / `UNError` permission flow). Will declare `POST_NOTIFICATIONS` runtime permission for Android 13+ (API 33+).
- **Date/time**: `intl` 0.19+ for locale-aware formatting (mirrors Flask's `babel`-formatted timestamps), `timeago` 3.7+ for "3 minutes ago"-style relative strings used in the receipts feed.
- **Build orchestration**: `flutter_flavorizr` 2.x for dev/staging/prod flavors (separate `applicationId` suffixes, distinct backend base URLs, distinct app icons) — full flavor matrix and signing config deferred to §5.

Hard-constraint compliance recap:
- **RULE 2** — Every `@freezed` response model in `lib/api/models/` will be generated from a manual read of the matching `return jsonify({...})` site in `src/backend/*.py`. The PR template will include a checkbox: "I opened the Flask endpoint and confirmed every key is present in the Dart model with matching `@JsonKey(name: …)`."
- **RULE 18 (Dart inversion)** — No implicit snake→camel conversion exists in `json_serializable`. **Every field** on a Decodable model MUST carry `@JsonKey(name: 'exact_flask_key')`. A `custom_lint` rule (or, fallback, a CI grep `grep -nE '^\s+[a-z][a-zA-Z0-9]*\s*[,;]' lib/api/models/`) will fail the build if any field in `lib/api/models/` lacks an explicit `@JsonKey`. Missing annotations produce silent `null`, which is exactly the I-17/I-18 failure mode RULE 18 was written to prevent.
- **Session cookie persistence** — `PersistCookieJar` writes to `getApplicationDocumentsDirectory()/.cookies/`; the session cookie survives cold launch and Android process death, matching the web SPA's "stay logged in across browser restarts" behaviour. Logout clears both the jar and `flutter_secure_storage`.


---

## §2 Architecture (Agent 2)

### Module / feature layout
```
android/
  app/                          # Gradle module
lib/
  main.dart                     # entrypoint + ProviderScope + bootstrap
  app/
    app.dart                    # MaterialApp.router + theme
    theme/                      # light/dark color tokens mirroring web --color-* vars
    router/                     # go_router config (see §3)
  core/
    api/                        # ApiClient (dio instance, cookie jar, interceptors)
    auth/                       # session bootstrap, cookie persistence, login state
    storage/                    # secure storage wrapper (flutter_secure_storage)
    errors/                     # AppException hierarchy + retry policy
    models/                     # shared dtos (User, Household, FeatureFlags)
    util/                       # date, currency, logger
  features/
    appshell/                   # sidebar, theme toggle, chat fab, mobile menu
    auth/                       # login, device pairing, password reset, invite
    dashboard/                  # F-201..F-234
    inventory/                  # F-301..F-374
    products/                   # F-401..F-435
    medicine/                   # F-501..F-539
    restaurant/                 # F-601..F-613
    balances/                   # F-701..F-706
    contacts/                   # F-801..F-806
    expenses/                   # F-901..F-916
    shopping/                   # F-1001..F-10xx
    kitchen/                    # whatever F-IDs apply
    receipts/                   # receipt list + detail + upload sheets
    upload/                     # receipt camera/upload screen
    bills/                      # bills list, projections, cadence
    accounts/                   # bank/cash/credit-card accounts
    analytics/                  # spending, top merchants, category drill
    budget/                     # household + category budgets
    contributions/              # leaderboard + activity
    settings/                   # account, preferences, integrations
    shared/                     # modals: confirm, manual-entry, action-toast, chat panel

  Each feature/<x>/ contains:
    data/        # repository + remote_source + local_source (Drift)
    domain/     # entities + use cases (if state needs it)
    presentation/ # screens/, widgets/, providers/, state.dart
    routes.dart  # routes contributed to root go_router
```

### Repository pattern
- Each feature exposes ONE repository (`InventoryRepository`, `ShoppingRepository`, …).
- Repository wraps `remote_source` (dio calls returning typed DTOs) and optional `local_source` (Drift table for offline cache).
- Repositories are pure functions returning `Future<Result<T>>` (sealed class success/failure/cancelled).
- NEVER expose dio Response objects above repository layer — protects RULE 2 invariant.
- Optimistic mutations: repository applies local cache mutation first, fires remote, rolls back on failure (mirrors web `invDecrement()` optimistic pattern).

### Dependency injection
- `riverpod` providers as the DI surface — no separate `get_it`.
- `apiClientProvider`, `secureStorageProvider`, `cookieJarProvider`, `dbProvider` at root.
- Feature providers (`inventoryRepositoryProvider`) depend on root providers.
- Test override: ProviderContainer with `overrideWith` per spec.

### Build config / flavors
- THREE flavors: `dev`, `staging`, `prod` (Android product flavors + Flutter `--flavor`).
- Each flavor sets `API_BASE_URL` via `--dart-define`:
  - dev:     `http://10.0.2.2:5001` (emulator → host loopback)
  - staging: `https://staging.npalakurla.com` (if exists; else dev)
  - prod:    `https://extended.npalakurla.com`
- ApplicationId per flavor:
  - dev:     `com.localocr.extended.localocr.extended.dev`
  - staging: `com.localocr.extended.localocr.extended.staging`
  - prod:    `com.localocr.extended.localocr.extended`
- versionCode/versionName driven by `--dart-define=VERSION_CODE=… VERSION_NAME=…` so CI controls it.

### Cross-cutting policies
- **Logging**: `logger` package, structured (`{event, route, durationMs, statusCode}`). RULE 6 equivalent: every screen-load logs `loaded N <thing>`.
- **Error surface**: AsyncValue.error → typed `AppException` → snackbar + structured log entry.
- **Feature flags**: GET `/auth/app-config` at boot → `featureFlagsProvider` (Riverpod) gates sidebar items (Restaurant admin-conditional etc.).
- **Theme tokens**: imported from web `src/frontend/index.html` CSS variables — both light/dark.
- **Internationalization**: defer (English-only for v1) — note in §7.3 assumptions.


---

## §3 Screen routing & navigation (Agent 3)

### Navigation skeleton
- Pattern: `Scaffold` with `NavigationDrawer` (replaces web sidebar F-002..F-020). NOT bottom-nav — 17+ destinations exceed bottom-nav's 3-5 slot limit, and web parity demands one-tap reach to every page.
- Optional `NavigationRail` rendered when `MediaQuery.size.width >= 840` (tablets, foldables, ChromeOS) for sidebar parity; drawer remains primary on phones.
- `Scaffold.appBar` carries: hamburger (`Builder` + `Scaffold.of(ctx).openDrawer()`), current page title (driven by `GoRouterState.topRoute.name`), theme toggle action (F-021), profile/avatar menu.
- Chat FAB (F-032): `Scaffold.floatingActionButton` pinned `endFloat`; tap opens chat panel via `showModalBottomSheet(isScrollControlled: true, useSafeArea: true)` — replaces draggable web panel F-036 🔄 (no free-floating draggable on Android; bottom sheet is the platform idiom).
- Toast / action-toast (F-025): `ScaffoldMessenger.showSnackBar` with `SnackBarAction` for Undo + a countdown ring driven by `Timer.periodic`. For richer multi-line / persistent toasts use `flushbar` (decision: ship `ScaffoldMessenger` first, escalate to `flushbar` only if F-025 timing/UX regressions surface in QA).
- Mobile hamburger F-022 (`toggleMobileMenu`) maps to the standard drawer affordance — no separate "narrow viewport" branch; Android always uses the real drawer.

### Web hash → Android route table

Source of truth: `nav('<page>')` call sites in `src/frontend/index.html` lines 1622–1699, cross-referenced against `## Screen:` headings in `FEATURE_PARITY_REGISTRY.md`.

| Web hash | go_router path | Drawer item | Notes |
|----------|---------------|-------------|-------|
| #dashboard      | /dashboard      | F-002 | initialLocation after successful login |
| #inventory      | /inventory      | F-003 | |
| #products       | /products       | F-004 | |
| #medicine       | /medicine       | F-005 | hidden when no medicine members configured (parity with web `#nav-medicine` visibility) |
| #upload         | /upload         | F-006 | full-screen camera/upload route, drawer collapses on entry |
| #receipts       | /receipts       | F-007 | supports query `?untagged_only=1` (F-211) |
| #receipts/<id>  | /receipts/:id   | —     | detail; reached via F-424 / F-611 / F-911 deep links from other screens |
| #shopping       | /shopping       | F-008 | supports `?view=open\|purchased` (F-1005/F-1007) |
| #kitchen        | /kitchen        | F-009 | |
| #restaurant     | /restaurant     | F-010 | guard: `appConfig.modules.restaurant == true` (nested key per `manage_authentication.py:40-58`; V-3/V-11 audit verified — NOT top-level `restaurant_enabled`) |
| #balances       | /balances       | F-011 | |
| #contacts       | /contacts       | F-012 | "Contacts (Dining)" in registry |
| #expenses       | /expenses       | F-013 | |
| #budget         | /budget         | F-014 | |
| #bills          | /bills          | F-015 | |
| #accounts       | /accounts       | F-016 | |
| #analytics      | /analytics      | F-017 | |
| #contributions  | /contributions  | F-018 | |
| #features       | /features (WebView) | F-019 | renders the web `#features` page inside an in-app `WebView` (package: `webview_flutter`); falls back to `url_launcher` → external browser if WebView fails to initialize |
| #settings       | /settings       | F-020 | |
| (Login)         | /login          | —     | redirect target whenever `/auth/me` returns 401 |
| (Invite)        | /invite/:token  | —     | deep-link only, no drawer entry |
| (DesignGallery) | —               | —     | 🚫 dev-only (F-030), not shipped on Android |

### Deep links / intent filters
- `AndroidManifest.xml` `<intent-filter android:autoVerify="true">` on the main activity:
  - `https://extended.npalakurla.com/auth/invite/<token>` → `/invite/:token` (F-109 invite acceptance)
  - `https://extended.npalakurla.com/#<route>` and `https://extended.npalakurla.com/<route>` → maps to the table above (F-031 🔄 — Android can't read URL fragments from intents because the OS strips `#…` before dispatch; we accept both the hash form for share-link parity and a fragment-less path form, then strip the leading `#` in the go_router `redirect` callback).
  - `localocr://<route>` custom scheme as a fallback for in-app share/chat handoffs.
- go_router `redirect` logic (single global callback):
  - Unauthenticated + non-`/login` route → redirect to `/login?next=<Uri.encodeComponent(originalPath+query)>`.
  - Authenticated + at `/login` → redirect to `/dashboard` (or `next` query param if present and safe-listed).
  - `/restaurant` while `appConfig.modules.restaurant != true` → redirect to `/dashboard` with a one-shot SnackBar "Restaurant module disabled". DTO `AppConfig { AppConfigModules modules; }` / `AppConfigModules { bool grocery; bool restaurant; @JsonKey(name:'general_expense') bool generalExpense; }` mirrors backend shape verbatim (RULE 2).
  - `/medicine` is reachable but the drawer item is hidden when no medicine members exist (matches web behavior); no redirect — direct deep link still works for admins setting it up.
  - `/invite/:token` is always reachable (even unauthenticated); the screen itself handles "must log in first" by storing the token and bouncing through `/login?next=/invite/<token>`.

### Sub-tab navigation (within screens)
Sub-tabs stay as **query parameters on the same route**, not nested routes — this preserves web URL parity and lets `ref.watch(GoRouterState.queryParams)` drive screen-level filter state without a router rebuild.
- Shopping: `?view=open|purchased` (F-1005/F-1007) → segmented chip group in the screen header.
- Receipts: `?untagged_only=1` (F-211) → applied as a list filter; toggle exposed in the AppBar overflow menu.
- Medicine: status filter (F-504) and member chips (F-505/F-506) → screen-level `StateProvider`s, not URL-encoded (matches web, which keeps these in-memory).
- Inventory / Products: search and sort live in screen state; no URL change.

### Keyboard shortcuts (web only)
- F-029 `Alt+←` / `Alt+→` (history nav): hardware keyboards are rare on Android phones. 🔄 — system back button + drawer cover the equivalent navigation; if a Bluetooth/folio keyboard is attached, `Shortcuts` + `Actions` widgets can bind `Alt+ArrowLeft` to `Navigator.maybePop()` as a low-cost enhancement (defer to §10 polish).
- F-030 `g g` → Design Gallery: 🚫 dev-only, not ported (registry pre-marked).
- F-028 edge-pull / overscroll nav: implement via the per-screen `CustomScrollView` using `BouncingScrollPhysics` + an `OverscrollNotification` listener on the first/last sliver to trigger prev/next drawer destination. Alternative: an edge-swipe `GestureDetector` wrapping the body. Decision deferred to §6 (Dashboard row) where the first concrete consumer lives.

### Back-stack behavior
- System back from any top-level drawer destination → exit app (Android convention, matches `SystemNavigator.pop()` semantics). Use `PopScope(canPop: true)` on top-level routes; non-top-level routes (`/receipts/:id`, modals) keep default pop behavior.
- Modal sheets (manual-entry, edit product, add medication, members management — F-307/F-419/F-602 family) → `Navigator.pop` collapses the sheet first; back-press never skips a sheet.
- Confirm overlay (F-026): blocking `showDialog(barrierDismissible: false)` returning `Future<bool>`, not a route — does not appear in the back stack but back-press dismisses it as a no-op cancel.
- Drawer open + back-press → close drawer first (default `Scaffold` behavior, no extra wiring).
- Chat bottom sheet open + back-press → close sheet first.

### Theme toggle (F-021)
- Persist active theme in `SharedPreferences` under key `theme` (matches web `localStorage.setItem("theme", …)` at `src/frontend/index.html:14001` for cross-platform value parity on shared accounts).
- Cycle order mirrors web `THEME_CYCLE` (`src/frontend/index.html:13962`): `light → dark → clay → clay-dark → notion → notion-dark → light …` (6 themes, not 3 — the original prompt's `system → light → dark` is incorrect; verified via grep).
- `themeMode` state lives in a Riverpod `StateNotifierProvider<ThemeNotifier, String>`; `MaterialApp.theme` / `darkTheme` are selected via a `themeBuilder` keyed on the string.
- AppBar action button updates its `aria-label`/`tooltip` to "Switch to <nextLabel>" on each tap, matching `applyThemeToggleLabel()` semantics.
- Settings screen (F-020) exposes a `DropdownButton` bound to the same provider, mirroring the web `#theme-picker` two-way sync at `src/frontend/index.html:14006`.


---

## §4 Networking & auth (Agent 4)

### API client config
- **Base URL**: `https://extended.npalakurla.com` (prod), `http://10.0.2.2:5001` (dev emulator — `10.0.2.2` is the Android emulator's host-machine alias for `localhost`), `https://staging.npalakurla.com` (staging — verify DNS exists at build time; if not, fall back to dev URL via `--dart-define=API_BASE_URL=...`).
- **Selection**: compile-time `--dart-define=API_BASE_URL=...` injected by flavor (`dev`, `staging`, `prod`); default-resolved in `lib/core/api/env.dart`.
- **Client**: single `Dio` instance per `apiClientProvider` (Riverpod). `BaseOptions.contentType = 'application/json'`, `responseType = ResponseType.json`, `followRedirects = true`, `maxRedirects = 5` (needed for `/auth/oauth/google` flow).
- **Interceptors**, attached in this exact order (order matters: cookie BEFORE auth so 401 fires after cookies are written):
  1. `CookieManager(PersistCookieJar)` — backed by `flutter_secure_storage` (Keystore-backed) holding the jar's encryption key; jar file at `<appdir>/.cookies`. Cookies survive process restart (web uses Flask session cookie; mirror exactly).
  2. `AuthInterceptor` — on 401 → wipe `cookieJar.deleteAll()`, set `sessionProvider.state = null`, navigate `/login?next=<originalPath>` via `GoRouter`. Does NOT retry the 401'd request.
  3. `LoggingInterceptor` — dev/staging only (guarded by `kDebugMode || flavor != prod`); structured JSON log with method, path, status, durationMs. Bodies redacted for `/auth/login`, `/auth/forgot-password`.
  4. `RetryInterceptor` — exponential backoff `[1s, 2s, 4s]`, max 3 attempts, ONLY for idempotent verbs (GET, PUT, DELETE) AND only on network errors (`DioExceptionType.connectionTimeout`, `connectionError`, `sendTimeout`, `receiveTimeout`) or 5xx responses (NOT 4xx). **POST is NEVER retried** (would duplicate receipt uploads / cash transactions / pairing approves).
- **Timeouts**: `connectTimeout: 10s`, `receiveTimeout: 30s`, `sendTimeout: 60s` (receipt photo upload). Override per-call via `Options(sendTimeout:...)`.
- **JSON**: explicit `@JsonKey(name: 'snake_case_name')` per `freezed` model — no global `convertFromSnakeCase`. RULE 2 + RULE 18 carry-over from macOS plan: keep the mapping explicit so a backend rename surfaces as a compile error in `freezed` codegen, not a silent null at runtime.

### Auth & cookie handling
- Flask backend (`src/backend/manage_authentication.py`) uses Flask-Login session cookies — the auth surface is cookie-based, NOT JWT. The session cookie name is `session` (Flask default).
- Login flow:
  1. `POST /auth/login` `{email, password}` → 200 sets `session` cookie via `Set-Cookie` header.
  2. `CookieManager` persists it (`PersistCookieJar` writes to disk; jar key stored in `flutter_secure_storage`).
  3. Every subsequent request automatically attaches `Cookie: session=…`.
- Logout: `POST /auth/logout` → server clears cookie; client also wipes the jar via `cookieJar.deleteAll()` (Flask returns 200 even if already logged out).
- Token storage: NO separate token. Session cookie is the credential. The cookie jar IS the secure store — the jar file on disk is encrypted with a key held in Keystore via `flutter_secure_storage`.
- Cookie scope handling (V-1 RESOLVED): assume Flask defaults — `session` cookie is host-only (no `Domain` attribute), `SameSite=Lax`, `HttpOnly`, `Secure` for HTTPS. `PersistCookieJar` (`cookie_jar` 4.x) honors host-only + `SameSite=Lax` natively; no `ignoreExpires` override needed. First-launch verification task added to build phase 1: log raw `Set-Cookie` header from `/auth/login` response on dev emulator (`logger.d("set-cookie: ${response.headers.map['set-cookie']}")`); if `Domain=` or `SameSite=Strict` appears, file BL-A6 to revisit `Cookie.domain` rewrite. Captured header pinned to `docs/cookie-header.txt` at commit-1.
- Google OAuth (F-105, V-2 RESOLVED): replace prior custom-scheme plan with in-app `flutter_inappwebview` 6.x flow — opens `https://<base>/auth/oauth/google` inside a WebView the app fully controls. On `onLoadStop` for the final Flask redirect (`/` or `/#dashboard` post-auth), call `CookieManager.instance().getCookies(url: 'https://extended.npalakurla.com')`, extract the `session` cookie, and write it into the dio `PersistCookieJar` via `cookieJar.saveFromResponse(...)`. Close the WebView. No `localocr://` custom scheme registered; no Google Cloud OAuth client allowlist change needed (the existing https `/auth/oauth/google/callback` redirect URI continues to work). If `flutter_inappwebview` cookie-extraction proves flaky on a specific OEM in QA, fallback is `flutter_web_auth_2` with the Flask `/auth/oauth/google/callback` extended to render a one-shot HTML page that injects the session cookie via `document.cookie` and posts via `window.postMessage` — backlog item BL-A7 (only if needed).
- Device pairing (F-107, F-112–F-119):
  - `POST /auth/device-pairing/start` → returns pairing token.
  - `GET  /auth/device-pairing/status/<token>` → poll every 2s, max 5 minutes.
  - `POST /auth/device-pairing/approve` → from approving device.
  - `POST /auth/device-pairing/reject` → from approving device.
  - `GET  /auth/device-pairing/claim/<token>` → finalizes session on the new device.
  - `GET  /auth/pair-device/<token>` → web fallback for the QR landing page.
- QR fast-login (F-104): `POST /auth/qr-login-link` → token → `GET /auth/qr-login/<token>` consumes it; `GET /auth/qr-image` returns the rendered PNG.
- Password reset (F-108): `POST /auth/forgot-password` with `{email}`.
- Bootstrap (F-120): `GET /auth/bootstrap-info` + `GET /auth/app-config` at app start — feature flag source.
- Session check: `GET /auth/me` on app resume — 401 → not-logged-in state → redirect `/login`.

### Error / retry policy
- All 4xx → parse JSON `{error: "..."}` (fallback to status text) → throw `AppException(code, message, statusCode)` → red `SnackBar` + structured log.
- 401 mid-session → `AuthInterceptor` clears cookie jar, sets `sessionProvider.state = null`, navigates `/login?next=<originalPath>`, does **not** retry. Avoid retry loops on stale cookies.
- 403 → "You don't have access" snackbar; do not log out (different user, same session).
- 404 → typed `NotFoundException`; specific screens (receipt detail, etc.) render an empty-state widget instead of a snackbar.
- 409 → typed `ConflictException` (used by dedup / pairing-already-approved paths) — surface specific message to UI.
- 5xx → `RetryInterceptor` retries (3 attempts, exp backoff), then surfaces "Server error, try again" snackbar with a manual Retry button.
- Network timeout / `DioException.connectionTimeout` → "Check your connection" snackbar with manual retry button.
- `DioException.cancel` (user navigated away mid-flight) → silent no-op (mirrors macOS RULE 3 catch-cancellation-politely pattern).

### Token refresh
- N/A — Flask session cookies do not refresh; they expire (default ~31 days per Flask-Login `REMEMBER_COOKIE_DURATION`). On 401 the client re-auths via `/login`. There is no refresh-token endpoint to call.

### Per-screen `loaded N <thing>` log contract (RULE 6 carry-over)
- Every screen's primary load must `logger.i("loaded N <thing>")` on success — orchestrator post-build self-validation tails for this line.
- See §6 per-screen plan for the exact log line per screen (e.g. `"loaded 47 receipts"`, `"loaded 12 staged transactions"`).

### Backend endpoint inventory (RULE 1 — grepped from src/backend/)

Every row below was extracted from `grep -rnE "Blueprint\(" src/backend/` and `grep -rnE "@[a-zA-Z_]+\.route\(" src/backend/`. Any path not in this table is a fabrication. Multi-line `@bp.route(` definitions were resolved by reading the source.

#### Blueprint: `auth` — prefix `/auth` — `src/backend/manage_authentication.py:35`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/auth/bootstrap-info`                              | manage_authentication.py:805  | F-120 bootstrap |
| GET    | `/auth/app-config`                                  | manage_authentication.py:822  | feature flags |
| POST   | `/auth/login`                                       | manage_authentication.py:828  | sets session cookie |
| POST   | `/auth/logout`                                      | manage_authentication.py:871  | clears session cookie |
| POST   | `/auth/forgot-password`                             | manage_authentication.py:878  | F-108 |
| GET    | `/auth/me`                                          | manage_authentication.py:900  | session check |
| POST   | `/auth/qr-login-link`                               | manage_authentication.py:923  | F-104 |
| GET    | `/auth/qr-login/<token>`                            | manage_authentication.py:946  | F-104 |
| GET    | `/auth/qr-image`                                    | manage_authentication.py:962  | F-104 |
| POST   | `/auth/device-pairing/start`                        | manage_authentication.py:978  | F-107/112 |
| GET    | `/auth/pair-device/<token>`                         | manage_authentication.py:1018 | web QR landing |
| GET    | `/auth/device-pairing/status/<token>`               | manage_authentication.py:1112 | poll every 2s |
| GET    | `/auth/device-pairing/claim/<token>`                | manage_authentication.py:1174 | finalize on new device |
| POST   | `/auth/device-pairing/approve`                      | manage_authentication.py:1203 | F-114 |
| POST   | `/auth/device-pairing/reject`                       | manage_authentication.py:1317 | F-115 |
| GET    | `/auth/trusted-devices`                             | manage_authentication.py:1338 | F-118 |
| PUT    | `/auth/trusted-devices/<int:device_id>`             | manage_authentication.py:1357 | rename |
| DELETE | `/auth/trusted-devices/<int:device_id>`             | manage_authentication.py:1388 | unpair |
| POST   | `/auth/trusted-devices/<int:device_id>/revoke`      | manage_authentication.py:1432 | force-logout that device |
| GET    | `/auth/me/stats`                                    | manage_authentication.py:1476 | profile counters |
| GET    | `/auth/household-members`                           | manage_authentication.py:1489 | NOTE: distinct from `/household-members` |
| GET    | `/auth/users`                                       | manage_authentication.py:1524 | admin user list |
| POST   | `/auth/users`                                       | manage_authentication.py:1545 | admin create user |
| POST   | `/auth/service-accounts`                            | manage_authentication.py:1609 | admin |
| POST   | `/auth/service-accounts/<int:user_id>/rotate`       | manage_authentication.py:1672 | rotate API key |
| DELETE | `/auth/service-accounts/<int:user_id>`              | manage_authentication.py:1695 | admin |
| PATCH  | `/auth/service-accounts/<int:user_id>`              | manage_authentication.py:1723 | admin |
| DELETE | `/auth/users/<int:user_id>`                         | manage_authentication.py:1765 | admin |
| PUT    | `/auth/users/<int:user_id>`                         | manage_authentication.py:1916 | admin update |
| POST   | `/auth/invites`                                     | manage_authentication.py:2174 | admin |
| GET    | `/auth/invites`                                     | manage_authentication.py:2239 | admin |
| DELETE | `/auth/invites/<int:invite_id>`                     | manage_authentication.py:2282 | admin |
| GET    | `/auth/invite/<token>`                              | manage_authentication.py:2300 | invite landing |
| GET    | `/auth/oauth/google/status`                         | manage_authentication.py:2313 | F-105 |
| GET    | `/auth/oauth/google`                                | manage_authentication.py:2319 | F-105 launch |
| GET    | `/auth/oauth/google/callback`                       | manage_authentication.py:2347 | F-105 redirect |
| GET    | `/auth/oauth/google/link`                           | manage_authentication.py:2445 | link to existing |
| POST   | `/auth/oauth/google/unlink`                         | manage_authentication.py:2476 | F-105 |

#### Blueprint: `receipts` — prefix `/receipts` — `src/backend/handle_receipt_upload.py:40`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST   | `/receipts/upload`                                   | handle_receipt_upload.py:769  | multipart 'image' field; sendTimeout 60s |
| GET    | `/receipts/<int:receipt_id>`                         | handle_receipt_upload.py:920  | receipt detail |
| GET    | `/receipts`                                          | handle_receipt_upload.py:1092 | list (paginated) |
| POST   | `/receipts/manual`                                   | handle_receipt_upload.py:1510 | no-image manual entry |
| GET    | `/receipts/<int:receipt_id>/image`                   | handle_receipt_upload.py:1542 | image bytes |
| POST   | `/receipts/<int:receipt_id>/approve`                 | handle_receipt_upload.py:1597 | approve OCR result |
| PUT    | `/receipts/bulk-update`                              | handle_receipt_upload.py:1700 | bulk edit |
| PUT    | `/receipts/<int:receipt_id>/update`                  | handle_receipt_upload.py:1779 | edit single |
| POST   | `/receipts/<int:receipt_id>/reprocess`               | handle_receipt_upload.py:1899 | re-run OCR |
| POST   | `/receipts/cleanup-failed`                           | handle_receipt_upload.py:2044 | admin |
| GET    | `/receipts/dedup-scan`                               | handle_receipt_upload.py:2103 | duplicate finder |
| POST   | `/receipts/auto-link-plaid`                          | handle_receipt_upload.py:2453 | F-103 |
| POST   | `/receipts/merge`                                    | handle_receipt_upload.py:2615 | dedup action |
| POST   | `/receipts/dedup-dismiss`                            | handle_receipt_upload.py:2654 | dedup action |
| PUT    | `/receipts/<int:receipt_id>/attribution`             | handle_receipt_upload.py:2779 | F-101 who-paid |
| POST   | `/receipts/bulk-attribution`                         | handle_receipt_upload.py:2888 | F-101 bulk |
| GET    | `/receipts/attribution-stats`                        | handle_receipt_upload.py:3058 | F-101 dashboard |
| PUT    | `/receipts/<int:receipt_id>/items/<int:item_id>/attribution` | handle_receipt_upload.py:3066 | per-item attribution |
| PUT    | `/receipts/<int:receipt_id>/bill-status`             | handle_receipt_upload.py:3107 | mark bill paid/unpaid |
| POST   | `/receipts/bills/sync-autopay`                       | handle_receipt_upload.py:3166 | autopay sync |
| PUT    | `/receipts/<int:receipt_id>/rotate`                  | handle_receipt_upload.py:3219 | rotate image |
| GET    | `/receipts/bill-providers`                           | handle_receipt_upload.py:3246 | bill-provider list |
| GET    | `/receipts/bills/projection/<string:month>`          | handle_receipt_upload.py:3259 | F-022 |
| DELETE | `/receipts/<int:receipt_id>`                         | handle_receipt_upload.py:3284 | delete receipt |

#### Blueprint: `shopping_list` — prefix `/shopping-list` — `src/backend/manage_shopping_list.py:37`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/shopping-list`                                              | manage_shopping_list.py:496  | active list |
| POST   | `/shopping-list/share-link`                                   | manage_shopping_list.py:504  | F-026 |
| GET    | `/shopping-list/shared/<token>`                               | manage_shopping_list.py:517  | unauthenticated read |
| POST   | `/shopping-list/identify-product-photo`                       | manage_shopping_list.py:530  | F-031 vision |
| POST   | `/shopping-list/items`                                        | manage_shopping_list.py:609  | add item |
| PUT    | `/shopping-list/items/<int:item_id>`                          | manage_shopping_list.py:756  | edit item |
| DELETE | `/shopping-list/items/<int:item_id>`                          | manage_shopping_list.py:846  | remove item |
| PUT    | `/shopping-list/shared/<token>/items/<int:item_id>`           | manage_shopping_list.py:868  | F-026 anon edit |
| POST   | `/shopping-list/session/ready-to-bill`                        | manage_shopping_list.py:892  | mark ready |
| POST   | `/shopping-list/session/finalize`                             | manage_shopping_list.py:912  | finalize → receipt |
| POST   | `/shopping-list/session/reopen`                               | manage_shopping_list.py:982  | undo finalize |
| GET    | `/shopping-list/sessions`                                     | manage_shopping_list.py:1046 | history |
| GET    | `/shopping-list/sessions/<int:session_id>`                    | manage_shopping_list.py:1092 | session detail |
| POST   | `/shopping-list/products/<int:product_id>/confirm-recommendation` | manage_shopping_list.py:1124 | F-030 |

#### Blueprint: `plaid` — prefix `/plaid` — `src/backend/plaid_integration.py:61`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/plaid/status`                                                  | plaid_integration.py:279  | feature on/off |
| POST   | `/plaid/link-token`                                              | plaid_integration.py:289  | open Plaid Link |
| POST   | `/plaid/exchange-public-token`                                   | plaid_integration.py:338  | finish Plaid Link |
| GET    | `/plaid/items`                                                   | plaid_integration.py:409  | linked institutions |
| POST   | `/plaid/items/<int:item_id>/sync`                                | plaid_integration.py:632  | manual sync |
| POST   | `/plaid/webhook`                                                 | plaid_integration.py:668  | NO auth (Plaid → server); app does not call |
| GET    | `/plaid/staged-transactions`                                     | plaid_integration.py:834  | review queue |
| POST   | `/plaid/staged-transactions/<int:staged_id>/confirm`             | plaid_integration.py:893  | promote to Purchase |
| POST   | `/plaid/staged-transactions/bulk-confirm`                        | plaid_integration.py:1022 | bulk |
| POST   | `/plaid/staged-transactions/<int:staged_id>/dismiss`             | plaid_integration.py:1169 | hide |
| POST   | `/plaid/staged-transactions/<int:staged_id>/flag-duplicate`      | plaid_integration.py:1187 | dedup |
| GET    | `/plaid/staged-transactions/<int:staged_id>/match-candidates`    | plaid_integration.py:1234 | picker |
| POST   | `/plaid/staged-transactions/<int:staged_id>/link-receipt`        | plaid_integration.py:1321 | manual link |
| POST   | `/plaid/staged-transactions/<int:staged_id>/attach-upload`       | plaid_integration.py:1388 | upload+link, multipart 'image' |
| DELETE | `/plaid/items/<int:item_id>`                                     | plaid_integration.py:1498 | unlink |
| PATCH  | `/plaid/items/<int:item_id>`                                     | plaid_integration.py:1549 | rename/etc |
| GET    | `/plaid/accounts`                                                | plaid_integration.py:1632 | bank/card list |
| POST   | `/plaid/accounts/refresh-balances`                               | plaid_integration.py:1656 | refresh |
| GET    | `/plaid/cards-overview`                                          | plaid_integration.py:1812 | F-006 |
| PUT    | `/plaid/accounts/<int:account_id>/loan-meta`                     | plaid_integration.py:1986 | loan APR/term |
| PUT    | `/plaid/accounts/<int:account_id>/identity`                      | plaid_integration.py:2067 | account nickname |
| GET    | `/plaid/transaction-breakdown`                                   | plaid_integration.py:2132 | F-008 |
| GET    | `/plaid/transactions`                                            | plaid_integration.py:2253 | history |
| GET    | `/plaid/spending-trends`                                         | plaid_integration.py:2369 | F-008 charts |

#### Blueprint: `analytics` — prefix `/analytics` — `src/backend/calculate_spending_analytics.py:34`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/analytics/expense-summary`            | calculate_spending_analytics.py:191  | dashboard |
| GET | `/analytics/restaurant-summary`         | calculate_spending_analytics.py:350  | F-014 |
| GET | `/analytics/spending`                   | calculate_spending_analytics.py:465  | core |
| GET | `/analytics/price-history`              | calculate_spending_analytics.py:567  | per product |
| GET | `/analytics/deals-captured`             | calculate_spending_analytics.py:611  | F-013 |
| GET | `/analytics/store-comparison`           | calculate_spending_analytics.py:665  | F-012 |
| GET | `/analytics/utility-summary`            | calculate_spending_analytics.py:709  | F-022 |
| GET | `/analytics/spend-by-person`            | calculate_spending_analytics.py:993  | F-101 |
| GET | `/analytics/recurring-obligations`      | calculate_spending_analytics.py:1148 | F-104 |
| GET | `/analytics/bill-projections`           | calculate_spending_analytics.py:1445 | forecast |
| GET | `/analytics/spending-by-category`       | calculate_spending_analytics.py:1479 | category breakdown |
| GET | `/analytics/spending-by-category/items` | calculate_spending_analytics.py:1587 | drill-down |
| GET | `/analytics/receipts-activity`          | calculate_spending_analytics.py:1687 | activity feed |

#### Blueprint: `inventory` — prefix `/inventory` — `src/backend/manage_inventory.py:35`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/inventory`                                                  | manage_inventory.py:142 | list |
| POST   | `/inventory/add-item`                                         | manage_inventory.py:214 | add |
| PUT    | `/inventory/<int:item_id>/consume`                            | manage_inventory.py:312 | mark consumed |
| PUT    | `/inventory/<int:item_id>/update`                             | manage_inventory.py:362 | edit |
| PUT    | `/inventory/products/<int:product_id>/low-status`             | manage_inventory.py:432 | low/ok |
| PUT    | `/inventory/products/<int:product_id>/regular-use`            | manage_inventory.py:506 | toggle staple |
| POST   | `/inventory/products/<int:product_id>/confirm-low`            | manage_inventory.py:531 | confirm |
| DELETE | `/inventory/<int:item_id>`                                    | manage_inventory.py:557 | delete |
| PATCH  | `/inventory/products/<int:product_id>`                        | manage_inventory.py:639 | edit product meta |
| DELETE | `/inventory/products/<int:product_id>/expiry-override`        | manage_inventory.py:698 | clear override |
| GET    | `/inventory/recently-used-up`                                 | manage_inventory.py:710 | recent |
| POST   | `/inventory/products/<int:product_id>/restore`                | manage_inventory.py:769 | restore |

#### Blueprint: `products` — prefix `/products` — `src/backend/manage_product_catalog.py:25`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/products`                                  | manage_product_catalog.py:250 | list |
| GET    | `/products/search`                           | manage_product_catalog.py:274 | typeahead |
| POST   | `/products/create`                           | manage_product_catalog.py:299 | new |
| PUT    | `/products/<int:product_id>/update`          | manage_product_catalog.py:344 | edit |
| GET    | `/products/review-queue`                     | manage_product_catalog.py:419 | F-030 |
| POST   | `/products/review-queue/enhance`             | manage_product_catalog.py:450 | LLM enhance batch |
| POST   | `/products/<int:product_id>/enhance`         | manage_product_catalog.py:484 | LLM enhance one |
| PUT    | `/products/<int:product_id>/review-status`   | manage_product_catalog.py:507 | approve/reject |
| GET    | `/products/<int:product_id>`                 | manage_product_catalog.py:534 | detail |
| DELETE | `/products/<int:product_id>`                 | manage_product_catalog.py:544 | delete |
| GET    | `/products/<int:product_id>/price-history`   | manage_product_catalog.py:559 | price chart |
| POST   | `/products/auto-dedup-tokens`                | manage_product_catalog.py:591 | admin |

#### Blueprint: `budget` — prefix `/budget` — `src/backend/manage_household_budget.py:36`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST | `/budget/set-monthly`        | manage_household_budget.py:160 | set target |
| GET  | `/budget/status`             | manage_household_budget.py:284 | progress |
| GET  | `/budget/allocation-summary` | manage_household_budget.py:396 | breakdown |
| GET  | `/budget/category-summary`   | manage_household_budget.py:413 | breakdown |
| GET  | `/budget/target-history`     | manage_household_budget.py:478 | trend |

#### Blueprint: `contributions` — prefix `/contributions` — `src/backend/manage_contributions.py:28`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/contributions/summary`             | manage_contributions.py:156 | who-paid summary |
| GET | `/contributions/users/<int:user_id>` | manage_contributions.py:255 | per-user |

#### Blueprint: `recommendations` — prefix `/recommendations` — `src/backend/generate_recommendations.py:36`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/recommendations` | generate_recommendations.py:46 | F-030 |

#### Blueprint: `chat` — prefix `/chat` — `src/backend/chat_endpoints.py:26`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/chat/messages` | chat_endpoints.py:70  | history |
| POST   | `/chat/messages` | chat_endpoints.py:86  | send |
| GET    | `/chat/audit`    | chat_endpoints.py:204 | admin |
| DELETE | `/chat/messages` | chat_endpoints.py:250 | clear |

#### Blueprint: `medications` — prefix `/medications` — `src/backend/manage_medications.py:31`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/medications`                          | manage_medications.py:123 | list |
| POST   | `/medications/barcode-lookup`           | manage_medications.py:153 | scan |
| POST   | `/medications`                          | manage_medications.py:189 | add |
| GET    | `/medications/<int:med_id>`             | manage_medications.py:224 | detail |
| PUT    | `/medications/<int:med_id>`             | manage_medications.py:234 | edit |
| DELETE | `/medications/<int:med_id>`             | manage_medications.py:265 | delete |
| POST   | `/medications/<int:med_id>/photo`       | manage_medications.py:278 | multipart upload |

#### Blueprint: `floor_obligations` — prefix `/floor-obligations` — `src/backend/handle_floor_obligations.py:9`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/floor-obligations/`                | handle_floor_obligations.py:78  | list (trailing slash required) |
| POST   | `/floor-obligations/`                | handle_floor_obligations.py:107 | add |
| PATCH  | `/floor-obligations/<int:ob_id>`     | handle_floor_obligations.py:141 | edit |
| DELETE | `/floor-obligations/<int:ob_id>`     | handle_floor_obligations.py:168 | delete |
| GET    | `/floor-obligations/available`       | handle_floor_obligations.py:182 | unallocated |
| GET    | `/floor-obligations/summary`         | handle_floor_obligations.py:230 | rollup |

#### Blueprint: `shared_dining` — prefix `/shared-dining` — `src/backend/shared_dining_endpoints.py:24`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST  | `/shared-dining/purchases/<int:purchase_id>`                                      | shared_dining_endpoints.py:27  | create from purchase |
| PATCH | `/shared-dining/expenses/<int:expense_id>/participants/<int:participant_id>`      | shared_dining_endpoints.py:46  | edit share |
| POST  | `/shared-dining/debts/<int:debt_id>/settle`                                       | shared_dining_endpoints.py:62  | settle |
| POST  | `/shared-dining/contacts/<int:contact_id>/settle-all`                             | shared_dining_endpoints.py:75  | settle all |
| GET   | `/shared-dining/balances`                                                         | shared_dining_endpoints.py:82  | balances |
| GET   | `/shared-dining/balances/<int:contact_id>`                                        | shared_dining_endpoints.py:88  | per contact |
| GET   | `/shared-dining/contacts`                                                         | shared_dining_endpoints.py:95  | list |
| POST  | `/shared-dining/contacts`                                                         | shared_dining_endpoints.py:105 | add |
| POST  | `/shared-dining/contacts/merge`                                                   | shared_dining_endpoints.py:118 | merge dup |

#### Blueprint: `product_snapshots` — prefix `/product-snapshots` — `src/backend/manage_product_snapshots.py:28`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST   | `/product-snapshots/upload`                            | manage_product_snapshots.py:181 | multipart |
| GET    | `/product-snapshots`                                   | manage_product_snapshots.py:257 | list |
| GET    | `/product-snapshots/<int:snapshot_id>`                 | manage_product_snapshots.py:280 | detail |
| GET    | `/product-snapshots/<int:snapshot_id>/image`           | manage_product_snapshots.py:290 | image bytes |
| GET    | `/product-snapshots/review-queue`                      | manage_product_snapshots.py:305 | queue |
| PUT    | `/product-snapshots/<int:snapshot_id>/review`          | manage_product_snapshots.py:333 | approve/reject |
| POST   | `/product-snapshots/<int:snapshot_id>/promote`         | manage_product_snapshots.py:400 | promote to catalog |
| DELETE | `/product-snapshots/<int:snapshot_id>`                 | manage_product_snapshots.py:420 | delete |

#### Blueprint: `cash_transactions` — prefix `/cash-transactions` — `src/backend/manage_cash_transactions.py:24`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST   | `/cash-transactions`                       | manage_cash_transactions.py:382 | add cash tx |
| GET    | `/cash-transactions`                       | manage_cash_transactions.py:490 | list |
| DELETE | `/cash-transactions/<int:transaction_id>`  | manage_cash_transactions.py:533 | delete |

#### Blueprint: `bill_edit` — prefix `` (none) — `src/backend/manage_cash_transactions.py:25`

`bill_edit_bp = Blueprint("bill_edit", __name__)` — registered with no `url_prefix`; paths below are root-level.

| Method | Path | Source | Notes |
|---|---|---|---|
| PUT | `/bill-providers/<int:provider_id>`         | manage_cash_transactions.py:601 | edit provider |
| PUT | `/bill-service-lines/<int:service_line_id>` | manage_cash_transactions.py:668 | edit service line |

#### Blueprint: `household_members` — prefix `/household-members` — `src/backend/manage_household_members.py:19`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET    | `/household-members`                  | manage_household_members.py:35  | list |
| POST   | `/household-members`                  | manage_household_members.py:50  | add |
| PUT    | `/household-members/<int:member_id>`  | manage_household_members.py:81  | edit |
| DELETE | `/household-members/<int:member_id>`  | manage_household_members.py:113 | remove |

#### Blueprint: `stores` — prefix `/api/stores` — `src/backend/manage_stores_endpoint.py:15`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET  | `/api/stores`                            | manage_stores_endpoint.py:20 | list |
| POST | `/api/stores/<int:store_id>/visibility`  | manage_stores_endpoint.py:27 | show/hide |

#### Blueprint: `kitchen` — prefix `/api/kitchen` — `src/backend/manage_kitchen_endpoint.py:17`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/api/kitchen/catalog` | manage_kitchen_endpoint.py:20 | catalog |

#### Blueprint: `ai_models` — prefix `/api/models` — `src/backend/manage_ai_models.py:19`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET  | `/api/models`        | manage_ai_models.py:263 | available models |
| POST | `/api/models/select` | manage_ai_models.py:279 | select default |
| POST | `/api/models/unlock` | manage_ai_models.py:322 | unlock paid tier |

#### Blueprint: `admin_ai_models` — prefix `/api/admin/models` — `src/backend/manage_ai_models.py:20`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET   | `/api/admin/models`                  | manage_ai_models.py:389 | admin list |
| GET   | `/api/admin/models/usage`            | manage_ai_models.py:405 | usage stats |
| POST  | `/api/admin/models`                  | manage_ai_models.py:498 | add model |
| PATCH | `/api/admin/models/<int:model_id>`   | manage_ai_models.py:531 | edit model |

#### Blueprint: `image_backfill` — prefix `/api/admin/image-backfill` — `src/backend/manage_image_backfill.py:43`

| Method | Path | Source | Notes |
|---|---|---|---|
| GET  | `/api/admin/image-backfill/providers`        | manage_image_backfill.py:70  | providers |
| GET  | `/api/admin/image-backfill/candidates`       | manage_image_backfill.py:86  | candidates |
| POST | `/api/admin/image-backfill/run`              | manage_image_backfill.py:206 | start job |
| GET  | `/api/admin/image-backfill/schedule`         | manage_image_backfill.py:250 | get schedule |
| PUT  | `/api/admin/image-backfill/schedule`         | manage_image_backfill.py:267 | set schedule |
| GET  | `/api/admin/image-backfill/jobs/<job_id>`    | manage_image_backfill.py:297 | job status |
| GET  | `/api/admin/image-backfill/history`          | manage_image_backfill.py:311 | history |

#### Blueprint: `telegram` — prefix `/telegram` — `src/backend/handle_telegram_messages.py:29`

| Method | Path | Source | Notes |
|---|---|---|---|
| POST | `/telegram/webhook` | handle_telegram_messages.py:36 | Telegram → server; app does NOT call |

#### Blueprint: `environment_ops` — prefix `/system` — `src/backend/manage_environment_ops.py:13`

No `@environment_ops_bp.route(...)` decorators are present in `src/backend/manage_environment_ops.py` (confirmed by grep). Routes may be attached elsewhere or this blueprint is currently empty. Android app does NOT call any `/system/*` endpoint — none exist.

#### Blueprint: `features` — prefix `` (none) — `src/backend/handle_features.py:10`

`features_bp = Blueprint("features", __name__)` — no `url_prefix`; web-only HTML feature catalog. Android app does NOT call these (they return HTML pages, not JSON), but they are listed for completeness.

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/features`      | handle_features.py:15 | HTML page (web only) |
| GET | `/features/data` | handle_features.py:20 | feature catalog JSON (could be reused if needed) |

#### App-level routes (not under a blueprint) — `src/backend/create_flask_application.py`

These are attached directly to the `Flask` app via `@app.route` (no blueprint). Most are web-shell pages; only `/health` is interesting to the Android client.

| Method | Path | Source | Notes |
|---|---|---|---|
| GET | `/`                              | create_flask_application.py:150 | web SPA shell (HTML) |
| GET | `/dashboard`                     | create_flask_application.py:151 | web SPA shell (HTML) |
| GET | `/shopping-helper/<token>`       | create_flask_application.py:152 | F-026 web landing (HTML) |
| GET | `/styles/<path:filename>`        | create_flask_application.py:159 | static CSS |
| GET | `/assets/<path:filename>`        | create_flask_application.py:168 | static assets |
| GET | `/design/`                       | create_flask_application.py:177 | design system page |
| GET | `/design/<path:filename>`        | create_flask_application.py:178 | design assets |
| GET | `/health`                        | create_flask_application.py:399 | health check — used by app's connectivity probe |

### Complete URL ↔ source appendix (denormalized)

- `GET    /auth/bootstrap-info` — src/backend/manage_authentication.py:805
- `GET    /auth/app-config` — src/backend/manage_authentication.py:822
- `POST   /auth/login` — src/backend/manage_authentication.py:828
- `POST   /auth/logout` — src/backend/manage_authentication.py:871
- `POST   /auth/forgot-password` — src/backend/manage_authentication.py:878
- `GET    /auth/me` — src/backend/manage_authentication.py:900
- `POST   /auth/qr-login-link` — src/backend/manage_authentication.py:923
- `GET    /auth/qr-login/<token>` — src/backend/manage_authentication.py:946
- `GET    /auth/qr-image` — src/backend/manage_authentication.py:962
- `POST   /auth/device-pairing/start` — src/backend/manage_authentication.py:978
- `GET    /auth/pair-device/<token>` — src/backend/manage_authentication.py:1018
- `GET    /auth/device-pairing/status/<token>` — src/backend/manage_authentication.py:1112
- `GET    /auth/device-pairing/claim/<token>` — src/backend/manage_authentication.py:1174
- `POST   /auth/device-pairing/approve` — src/backend/manage_authentication.py:1203
- `POST   /auth/device-pairing/reject` — src/backend/manage_authentication.py:1317
- `GET    /auth/trusted-devices` — src/backend/manage_authentication.py:1338
- `PUT    /auth/trusted-devices/<int:device_id>` — src/backend/manage_authentication.py:1357
- `DELETE /auth/trusted-devices/<int:device_id>` — src/backend/manage_authentication.py:1388
- `POST   /auth/trusted-devices/<int:device_id>/revoke` — src/backend/manage_authentication.py:1432
- `GET    /auth/me/stats` — src/backend/manage_authentication.py:1476
- `GET    /auth/household-members` — src/backend/manage_authentication.py:1489
- `GET    /auth/users` — src/backend/manage_authentication.py:1524
- `POST   /auth/users` — src/backend/manage_authentication.py:1545
- `POST   /auth/service-accounts` — src/backend/manage_authentication.py:1609
- `POST   /auth/service-accounts/<int:user_id>/rotate` — src/backend/manage_authentication.py:1672
- `DELETE /auth/service-accounts/<int:user_id>` — src/backend/manage_authentication.py:1695
- `PATCH  /auth/service-accounts/<int:user_id>` — src/backend/manage_authentication.py:1723
- `DELETE /auth/users/<int:user_id>` — src/backend/manage_authentication.py:1765
- `PUT    /auth/users/<int:user_id>` — src/backend/manage_authentication.py:1916
- `POST   /auth/invites` — src/backend/manage_authentication.py:2174
- `GET    /auth/invites` — src/backend/manage_authentication.py:2239
- `DELETE /auth/invites/<int:invite_id>` — src/backend/manage_authentication.py:2282
- `GET    /auth/invite/<token>` — src/backend/manage_authentication.py:2300
- `GET    /auth/oauth/google/status` — src/backend/manage_authentication.py:2313
- `GET    /auth/oauth/google` — src/backend/manage_authentication.py:2319
- `GET    /auth/oauth/google/callback` — src/backend/manage_authentication.py:2347
- `GET    /auth/oauth/google/link` — src/backend/manage_authentication.py:2445
- `POST   /auth/oauth/google/unlink` — src/backend/manage_authentication.py:2476
- `POST   /receipts/upload` — src/backend/handle_receipt_upload.py:769
- `GET    /receipts/<int:receipt_id>` — src/backend/handle_receipt_upload.py:920
- `GET    /receipts` — src/backend/handle_receipt_upload.py:1092
- `POST   /receipts/manual` — src/backend/handle_receipt_upload.py:1510
- `GET    /receipts/<int:receipt_id>/image` — src/backend/handle_receipt_upload.py:1542
- `POST   /receipts/<int:receipt_id>/approve` — src/backend/handle_receipt_upload.py:1597
- `PUT    /receipts/bulk-update` — src/backend/handle_receipt_upload.py:1700
- `PUT    /receipts/<int:receipt_id>/update` — src/backend/handle_receipt_upload.py:1779
- `POST   /receipts/<int:receipt_id>/reprocess` — src/backend/handle_receipt_upload.py:1899
- `POST   /receipts/cleanup-failed` — src/backend/handle_receipt_upload.py:2044
- `GET    /receipts/dedup-scan` — src/backend/handle_receipt_upload.py:2103
- `POST   /receipts/auto-link-plaid` — src/backend/handle_receipt_upload.py:2453
- `POST   /receipts/merge` — src/backend/handle_receipt_upload.py:2615
- `POST   /receipts/dedup-dismiss` — src/backend/handle_receipt_upload.py:2654
- `PUT    /receipts/<int:receipt_id>/attribution` — src/backend/handle_receipt_upload.py:2779
- `POST   /receipts/bulk-attribution` — src/backend/handle_receipt_upload.py:2888
- `GET    /receipts/attribution-stats` — src/backend/handle_receipt_upload.py:3058
- `PUT    /receipts/<int:receipt_id>/items/<int:item_id>/attribution` — src/backend/handle_receipt_upload.py:3066
- `PUT    /receipts/<int:receipt_id>/bill-status` — src/backend/handle_receipt_upload.py:3107
- `POST   /receipts/bills/sync-autopay` — src/backend/handle_receipt_upload.py:3166
- `PUT    /receipts/<int:receipt_id>/rotate` — src/backend/handle_receipt_upload.py:3219
- `GET    /receipts/bill-providers` — src/backend/handle_receipt_upload.py:3246
- `GET    /receipts/bills/projection/<string:month>` — src/backend/handle_receipt_upload.py:3259
- `DELETE /receipts/<int:receipt_id>` — src/backend/handle_receipt_upload.py:3284
- `GET    /shopping-list` — src/backend/manage_shopping_list.py:496
- `POST   /shopping-list/share-link` — src/backend/manage_shopping_list.py:504
- `GET    /shopping-list/shared/<token>` — src/backend/manage_shopping_list.py:517
- `POST   /shopping-list/identify-product-photo` — src/backend/manage_shopping_list.py:530
- `POST   /shopping-list/items` — src/backend/manage_shopping_list.py:609
- `PUT    /shopping-list/items/<int:item_id>` — src/backend/manage_shopping_list.py:756
- `DELETE /shopping-list/items/<int:item_id>` — src/backend/manage_shopping_list.py:846
- `PUT    /shopping-list/shared/<token>/items/<int:item_id>` — src/backend/manage_shopping_list.py:868
- `POST   /shopping-list/session/ready-to-bill` — src/backend/manage_shopping_list.py:892
- `POST   /shopping-list/session/finalize` — src/backend/manage_shopping_list.py:912
- `POST   /shopping-list/session/reopen` — src/backend/manage_shopping_list.py:982
- `GET    /shopping-list/sessions` — src/backend/manage_shopping_list.py:1046
- `GET    /shopping-list/sessions/<int:session_id>` — src/backend/manage_shopping_list.py:1092
- `POST   /shopping-list/products/<int:product_id>/confirm-recommendation` — src/backend/manage_shopping_list.py:1124
- `GET    /plaid/status` — src/backend/plaid_integration.py:279
- `POST   /plaid/link-token` — src/backend/plaid_integration.py:289
- `POST   /plaid/exchange-public-token` — src/backend/plaid_integration.py:338
- `GET    /plaid/items` — src/backend/plaid_integration.py:409
- `POST   /plaid/items/<int:item_id>/sync` — src/backend/plaid_integration.py:632
- `POST   /plaid/webhook` — src/backend/plaid_integration.py:668
- `GET    /plaid/staged-transactions` — src/backend/plaid_integration.py:834
- `POST   /plaid/staged-transactions/<int:staged_id>/confirm` — src/backend/plaid_integration.py:893
- `POST   /plaid/staged-transactions/bulk-confirm` — src/backend/plaid_integration.py:1022
- `POST   /plaid/staged-transactions/<int:staged_id>/dismiss` — src/backend/plaid_integration.py:1169
- `POST   /plaid/staged-transactions/<int:staged_id>/flag-duplicate` — src/backend/plaid_integration.py:1187
- `GET    /plaid/staged-transactions/<int:staged_id>/match-candidates` — src/backend/plaid_integration.py:1234
- `POST   /plaid/staged-transactions/<int:staged_id>/link-receipt` — src/backend/plaid_integration.py:1321
- `POST   /plaid/staged-transactions/<int:staged_id>/attach-upload` — src/backend/plaid_integration.py:1388
- `DELETE /plaid/items/<int:item_id>` — src/backend/plaid_integration.py:1498
- `PATCH  /plaid/items/<int:item_id>` — src/backend/plaid_integration.py:1549
- `GET    /plaid/accounts` — src/backend/plaid_integration.py:1632
- `POST   /plaid/accounts/refresh-balances` — src/backend/plaid_integration.py:1656
- `GET    /plaid/cards-overview` — src/backend/plaid_integration.py:1812
- `PUT    /plaid/accounts/<int:account_id>/loan-meta` — src/backend/plaid_integration.py:1986
- `PUT    /plaid/accounts/<int:account_id>/identity` — src/backend/plaid_integration.py:2067
- `GET    /plaid/transaction-breakdown` — src/backend/plaid_integration.py:2132
- `GET    /plaid/transactions` — src/backend/plaid_integration.py:2253
- `GET    /plaid/spending-trends` — src/backend/plaid_integration.py:2369
- `GET    /analytics/expense-summary` — src/backend/calculate_spending_analytics.py:191
- `GET    /analytics/restaurant-summary` — src/backend/calculate_spending_analytics.py:350
- `GET    /analytics/spending` — src/backend/calculate_spending_analytics.py:465
- `GET    /analytics/price-history` — src/backend/calculate_spending_analytics.py:567
- `GET    /analytics/deals-captured` — src/backend/calculate_spending_analytics.py:611
- `GET    /analytics/store-comparison` — src/backend/calculate_spending_analytics.py:665
- `GET    /analytics/utility-summary` — src/backend/calculate_spending_analytics.py:709
- `GET    /analytics/spend-by-person` — src/backend/calculate_spending_analytics.py:993
- `GET    /analytics/recurring-obligations` — src/backend/calculate_spending_analytics.py:1148
- `GET    /analytics/bill-projections` — src/backend/calculate_spending_analytics.py:1445
- `GET    /analytics/spending-by-category` — src/backend/calculate_spending_analytics.py:1479
- `GET    /analytics/spending-by-category/items` — src/backend/calculate_spending_analytics.py:1587
- `GET    /analytics/receipts-activity` — src/backend/calculate_spending_analytics.py:1687
- `GET    /inventory` — src/backend/manage_inventory.py:142
- `POST   /inventory/add-item` — src/backend/manage_inventory.py:214
- `PUT    /inventory/<int:item_id>/consume` — src/backend/manage_inventory.py:312
- `PUT    /inventory/<int:item_id>/update` — src/backend/manage_inventory.py:362
- `PUT    /inventory/products/<int:product_id>/low-status` — src/backend/manage_inventory.py:432
- `PUT    /inventory/products/<int:product_id>/regular-use` — src/backend/manage_inventory.py:506
- `POST   /inventory/products/<int:product_id>/confirm-low` — src/backend/manage_inventory.py:531
- `DELETE /inventory/<int:item_id>` — src/backend/manage_inventory.py:557
- `PATCH  /inventory/products/<int:product_id>` — src/backend/manage_inventory.py:639
- `DELETE /inventory/products/<int:product_id>/expiry-override` — src/backend/manage_inventory.py:698
- `GET    /inventory/recently-used-up` — src/backend/manage_inventory.py:710
- `POST   /inventory/products/<int:product_id>/restore` — src/backend/manage_inventory.py:769
- `GET    /products` — src/backend/manage_product_catalog.py:250
- `GET    /products/search` — src/backend/manage_product_catalog.py:274
- `POST   /products/create` — src/backend/manage_product_catalog.py:299
- `PUT    /products/<int:product_id>/update` — src/backend/manage_product_catalog.py:344
- `GET    /products/review-queue` — src/backend/manage_product_catalog.py:419
- `POST   /products/review-queue/enhance` — src/backend/manage_product_catalog.py:450
- `POST   /products/<int:product_id>/enhance` — src/backend/manage_product_catalog.py:484
- `PUT    /products/<int:product_id>/review-status` — src/backend/manage_product_catalog.py:507
- `GET    /products/<int:product_id>` — src/backend/manage_product_catalog.py:534
- `DELETE /products/<int:product_id>` — src/backend/manage_product_catalog.py:544
- `GET    /products/<int:product_id>/price-history` — src/backend/manage_product_catalog.py:559
- `POST   /products/auto-dedup-tokens` — src/backend/manage_product_catalog.py:591
- `POST   /budget/set-monthly` — src/backend/manage_household_budget.py:160
- `GET    /budget/status` — src/backend/manage_household_budget.py:284
- `GET    /budget/allocation-summary` — src/backend/manage_household_budget.py:396
- `GET    /budget/category-summary` — src/backend/manage_household_budget.py:413
- `GET    /budget/target-history` — src/backend/manage_household_budget.py:478
- `GET    /contributions/summary` — src/backend/manage_contributions.py:156
- `GET    /contributions/users/<int:user_id>` — src/backend/manage_contributions.py:255
- `GET    /recommendations` — src/backend/generate_recommendations.py:46
- `GET    /chat/messages` — src/backend/chat_endpoints.py:70
- `POST   /chat/messages` — src/backend/chat_endpoints.py:86
- `GET    /chat/audit` — src/backend/chat_endpoints.py:204
- `DELETE /chat/messages` — src/backend/chat_endpoints.py:250
- `GET    /medications` — src/backend/manage_medications.py:123
- `POST   /medications/barcode-lookup` — src/backend/manage_medications.py:153
- `POST   /medications` — src/backend/manage_medications.py:189
- `GET    /medications/<int:med_id>` — src/backend/manage_medications.py:224
- `PUT    /medications/<int:med_id>` — src/backend/manage_medications.py:234
- `DELETE /medications/<int:med_id>` — src/backend/manage_medications.py:265
- `POST   /medications/<int:med_id>/photo` — src/backend/manage_medications.py:278
- `GET    /floor-obligations/` — src/backend/handle_floor_obligations.py:78
- `POST   /floor-obligations/` — src/backend/handle_floor_obligations.py:107
- `PATCH  /floor-obligations/<int:ob_id>` — src/backend/handle_floor_obligations.py:141
- `DELETE /floor-obligations/<int:ob_id>` — src/backend/handle_floor_obligations.py:168
- `GET    /floor-obligations/available` — src/backend/handle_floor_obligations.py:182
- `GET    /floor-obligations/summary` — src/backend/handle_floor_obligations.py:230
- `POST   /shared-dining/purchases/<int:purchase_id>` — src/backend/shared_dining_endpoints.py:27
- `PATCH  /shared-dining/expenses/<int:expense_id>/participants/<int:participant_id>` — src/backend/shared_dining_endpoints.py:46
- `POST   /shared-dining/debts/<int:debt_id>/settle` — src/backend/shared_dining_endpoints.py:62
- `POST   /shared-dining/contacts/<int:contact_id>/settle-all` — src/backend/shared_dining_endpoints.py:75
- `GET    /shared-dining/balances` — src/backend/shared_dining_endpoints.py:82
- `GET    /shared-dining/balances/<int:contact_id>` — src/backend/shared_dining_endpoints.py:88
- `GET    /shared-dining/contacts` — src/backend/shared_dining_endpoints.py:95
- `POST   /shared-dining/contacts` — src/backend/shared_dining_endpoints.py:105
- `POST   /shared-dining/contacts/merge` — src/backend/shared_dining_endpoints.py:118
- `POST   /product-snapshots/upload` — src/backend/manage_product_snapshots.py:181
- `GET    /product-snapshots` — src/backend/manage_product_snapshots.py:257
- `GET    /product-snapshots/<int:snapshot_id>` — src/backend/manage_product_snapshots.py:280
- `GET    /product-snapshots/<int:snapshot_id>/image` — src/backend/manage_product_snapshots.py:290
- `GET    /product-snapshots/review-queue` — src/backend/manage_product_snapshots.py:305
- `PUT    /product-snapshots/<int:snapshot_id>/review` — src/backend/manage_product_snapshots.py:333
- `POST   /product-snapshots/<int:snapshot_id>/promote` — src/backend/manage_product_snapshots.py:400
- `DELETE /product-snapshots/<int:snapshot_id>` — src/backend/manage_product_snapshots.py:420
- `POST   /cash-transactions` — src/backend/manage_cash_transactions.py:382
- `GET    /cash-transactions` — src/backend/manage_cash_transactions.py:490
- `DELETE /cash-transactions/<int:transaction_id>` — src/backend/manage_cash_transactions.py:533
- `PUT    /bill-providers/<int:provider_id>` — src/backend/manage_cash_transactions.py:601
- `PUT    /bill-service-lines/<int:service_line_id>` — src/backend/manage_cash_transactions.py:668
- `GET    /household-members` — src/backend/manage_household_members.py:35
- `POST   /household-members` — src/backend/manage_household_members.py:50
- `PUT    /household-members/<int:member_id>` — src/backend/manage_household_members.py:81
- `DELETE /household-members/<int:member_id>` — src/backend/manage_household_members.py:113
- `GET    /api/stores` — src/backend/manage_stores_endpoint.py:20
- `POST   /api/stores/<int:store_id>/visibility` — src/backend/manage_stores_endpoint.py:27
- `GET    /api/kitchen/catalog` — src/backend/manage_kitchen_endpoint.py:20
- `GET    /api/models` — src/backend/manage_ai_models.py:263
- `POST   /api/models/select` — src/backend/manage_ai_models.py:279
- `POST   /api/models/unlock` — src/backend/manage_ai_models.py:322
- `GET    /api/admin/models` — src/backend/manage_ai_models.py:389
- `GET    /api/admin/models/usage` — src/backend/manage_ai_models.py:405
- `POST   /api/admin/models` — src/backend/manage_ai_models.py:498
- `PATCH  /api/admin/models/<int:model_id>` — src/backend/manage_ai_models.py:531
- `GET    /api/admin/image-backfill/providers` — src/backend/manage_image_backfill.py:70
- `GET    /api/admin/image-backfill/candidates` — src/backend/manage_image_backfill.py:86
- `POST   /api/admin/image-backfill/run` — src/backend/manage_image_backfill.py:206
- `GET    /api/admin/image-backfill/schedule` — src/backend/manage_image_backfill.py:250
- `PUT    /api/admin/image-backfill/schedule` — src/backend/manage_image_backfill.py:267
- `GET    /api/admin/image-backfill/jobs/<job_id>` — src/backend/manage_image_backfill.py:297
- `GET    /api/admin/image-backfill/history` — src/backend/manage_image_backfill.py:311
- `POST   /telegram/webhook` — src/backend/handle_telegram_messages.py:36
- `GET    /features` — src/backend/handle_features.py:15
- `GET    /features/data` — src/backend/handle_features.py:20
- `GET    /` — src/backend/create_flask_application.py:150
- `GET    /dashboard` — src/backend/create_flask_application.py:151
- `GET    /shopping-helper/<token>` — src/backend/create_flask_application.py:152
- `GET    /styles/<path:filename>` — src/backend/create_flask_application.py:159
- `GET    /assets/<path:filename>` — src/backend/create_flask_application.py:168
- `GET    /design/` — src/backend/create_flask_application.py:177
- `GET    /design/<path:filename>` — src/backend/create_flask_application.py:178
- `GET    /health` — src/backend/create_flask_application.py:399

### Implementation checklist
- [ ] `lib/core/api/env.dart` — flavored `API_BASE_URL` resolution (`--dart-define`), default per flavor.
- [ ] `lib/core/api/api_client.dart` — `Dio` instance + `PersistCookieJar` (path under `getApplicationSupportDirectory()`) + interceptors in order above.
- [ ] `lib/core/api/cookie_jar_provider.dart` — Riverpod provider for `PersistCookieJar`; jar key stored in `flutter_secure_storage`.
- [ ] `lib/core/api/interceptors/auth_interceptor.dart` — 401 → wipe jar, nav to `/login?next=…`, do NOT retry.
- [ ] `lib/core/api/interceptors/retry_interceptor.dart` — GET/PUT/DELETE only, network + 5xx only, exp backoff `[1,2,4]s`, max 3 attempts.
- [ ] `lib/core/api/interceptors/logging_interceptor.dart` — JSON log; redact body for `/auth/login`, `/auth/forgot-password`; dev/staging only.
- [ ] `lib/core/auth/session_provider.dart` — bootstraps cookie jar, calls `/auth/me` on app start, exposes `Stream<User?>`.
- [ ] `lib/core/auth/feature_flags_provider.dart` — caches `/auth/app-config`; offers `bool isEnabled(String key)` helpers.
- [ ] `lib/core/auth/oauth_google.dart` — `flutter_inappwebview` 6.x flow targeting `https://<base>/auth/oauth/google`; on `onLoadStop` for the final Flask redirect, extract the `session` cookie from the WebView via `CookieManager.instance().getCookies(...)` and copy into dio's `PersistCookieJar` (V-2 RESOLVED — no custom scheme, no Google Cloud allowlist change).
- [ ] `lib/core/auth/device_pairing.dart` — start → poll status → approve/reject; 2s poll cadence, 5min max.
- [ ] `lib/core/errors/app_exception.dart` — sealed hierarchy: `NetworkException` / `UnauthorizedException` / `ForbiddenException` / `NotFoundException` / `ConflictException` / `ServerException` / `UnknownException`.
- [ ] Per-feature `lib/features/<name>/data/<name>_remote_source.dart` — each method maps 1:1 to a row in the inventory above; method signature returns `Future<TypedResponse>` produced by `freezed` + `json_serializable` codegen.
- [ ] `lib/core/connectivity/health_probe.dart` — optional pre-flight `GET /health` to surface "server unreachable" before login attempts.


---

## §5 Build & CI (Agent 5)

### Pre-flight (Session start; equivalent to macOS Rule 1 pre-flight)
Run every check below at session start. Any failure blocks build work until resolved.

- `flutter --version` ≥ 3.24 (channel `stable`). Fail → upgrade via `flutter upgrade`.
- `flutter doctor -v` — must show:
  - `[✓] Flutter`
  - `[✓] Android toolchain` (SDK + platform-tools + build-tools 35.x installed)
  - `[✓] Java 17` (Gradle 8 + AGP 8.5 require JDK 17; OpenJDK 17 from Temurin recommended on macOS — `/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home`)
  - `[✓] Connected device` (physical) OR running emulator listed
- `flutter pub get` — clean exit (no version solving errors, no checksum mismatch).
- `cd android && ./gradlew --version` returns Gradle ≥ 8.4 and JVM 17.x.
- Active flavor's `keystore.jks` exists at the path documented under "Signing strategy" OR build is debug-only (release build attempts will fail loudly otherwise — that is the intended fast-fail).
- `adb devices` lists ≥ 1 `device` (not `unauthorized`, not `offline`).
- Backend reachability probe:
  `curl -sS https://extended.npalakurla.com/auth/me -o /dev/null -w "%{http_code}\n"` returns `200` or `401` (proves the backend is up; `000` = network down, `5xx` = infra issue — fix before proceeding so failures during build validation are unambiguously code-side, not infra-side).
- If using the Android emulator against a local dev backend, `curl -sS http://127.0.0.1:5001/auth/me -o /dev/null -w "%{http_code}\n"` from the host also returns `200`/`401` (emulator reaches it via `10.0.2.2:5001`).

### Gradle config (`android/app/build.gradle.kts`)

SDK + toolchain pins:
- `compileSdk = 35`, `targetSdk = 35`, `minSdk = 26` (Android 8.0; covers ~94% of devices; required by `flutter_secure_storage` Keystore APIs and `mobile_scanner`).
- Kotlin `1.9.22`+, Android Gradle Plugin `8.5.0`+, Gradle wrapper `8.4`+.
- `compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }`
- `kotlinOptions { jvmTarget = "17" }`

ApplicationId + flavors:
- Base `applicationId = "com.localocr.extended.localocr.extended"`.
- ProductFlavors:
  ```kotlin
  flavorDimensions += "environment"
  productFlavors {
    create("dev")     { dimension = "environment"; applicationIdSuffix = ".dev";     versionNameSuffix = "-dev";     resValue("string", "app_name", "LocalOCR Dev") }
    create("staging") { dimension = "environment"; applicationIdSuffix = ".staging"; versionNameSuffix = "-staging"; resValue("string", "app_name", "LocalOCR Stg") }
    create("prod")    { dimension = "environment";                                                                   resValue("string", "app_name", "LocalOCR") }
  }
  ```
  Resulting applicationIds: `…localocr.extended.dev`, `…localocr.extended.staging`, `…localocr.extended` — three side-by-side installs possible.

Release build type + shrinking:
- `buildTypes { release { isMinifyEnabled = true; isShrinkResources = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro"); signingConfig = signingConfigs.getByName("release") } }`
- ProGuard rules (`android/app/proguard-rules.pro`) must keep:
  - `dio` model classes referenced reflectively by interceptors: `-keep class * extends com.… { *; }` — actually Dart-side, but native Dio Java shim must stay: `-keep class com.flutter.… { *; }` (none for pure Dart, no rule needed; included here as a checklist item only — verify on first release build).
  - `freezed` + `json_serializable` generated factories: `-keepclassmembers class **$* { *; }` — Dart code is AOT-compiled, so the real risk is on Kotlin/Java side. For pure-Flutter app this is mostly unused; rule kept as defensive only.
  - `mobile_scanner` native classes: `-keep class com.google.mlkit.** { *; } -keep class com.google.android.gms.vision.** { *; }`
  - `flutter_secure_storage` Keystore: `-keep class androidx.security.crypto.** { *; }`
  - Drift: reflection-free at runtime, no rule needed.
  - Firebase models if added later: `-keep class com.google.firebase.** { *; }` (deferred until Firebase is introduced).
- R8 mode: keep default (not `android.enableR8.fullMode=true`) for v1. If first release build strips `json_serializable` factories at runtime (manifests as `NoSuchMethodError` on `_$FooFromJson`), explicitly set `android.enableR8.fullMode=false` in `gradle.properties` and document it.

### `AndroidManifest.xml` (per-flavor merging)

Base `android/app/src/main/AndroidManifest.xml`:
- `<application android:label="@string/app_name" android:icon="@mipmap/ic_launcher" android:enableOnBackInvokedCallback="true">` (predictive-back for Android 14+).
- Permissions:
  - `<uses-permission android:name="android.permission.INTERNET"/>` — required.
  - `<uses-permission android:name="android.permission.CAMERA"/>` — receipt upload + barcode scan (F-531, F-1010, F-363).
  - `<uses-permission android:name="android.permission.READ_MEDIA_IMAGES"/>` (API 33+) — gallery picker.
  - `<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32"/>` — gallery picker on Android ≤ 12.
  - `<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>` (API 33+) — inventory expiry nudges.
  - `<uses-feature android:name="android.hardware.camera" android:required="false"/>` — keeps the app installable on camera-less tablets; runtime permission still gates use.
  - `RECEIVE_BOOT_COMPLETED` + WorkManager — **deferred to v1.1**, not required for parity; do NOT add in v1 to avoid Play Store policy review on boot-receiver justification.
- Intent filters: deep links per §3 (`localocr://...` custom scheme + `https://extended.npalakurla.com/app/...` App Links with `android:autoVerify="true"`).
- `usesCleartextTraffic` is NOT set in the base manifest (release builds reject cleartext by default — desired).

Per-flavor overlays:
- `android/app/src/dev/AndroidManifest.xml`:
  ```xml
  <application
      android:usesCleartextTraffic="true"
      android:networkSecurityConfig="@xml/network_security_config_dev"
      tools:replace="android:usesCleartextTraffic,android:networkSecurityConfig"/>
  ```
  with `res/xml/network_security_config_dev.xml` allow-listing `10.0.2.2` and `127.0.0.1` only.
- `staging` + `prod` flavors: no overlay — cleartext stays off, App Link verification on.

### Signing strategy

- **Debug** (any flavor): default `~/.android/debug.keystore` auto-generated by Flutter — no action required; commits never include it.
- **Release** (prod + staging share one keystore — different `applicationId`s already differentiate installs in the Play Store and on-device):
  1. One-time generation (do NOT regenerate, ever):
     ```
     keytool -genkey -v \
       -keystore <repo>/android/keystore/localocr-release.jks \
       -keyalg RSA -keysize 2048 -validity 10000 \
       -alias localocr
     ```
  2. Store passwords in `android/key.properties` (git-ignored — verify `.gitignore` contains `android/key.properties` AND `android/keystore/*.jks`):
     ```
     storeFile=keystore/localocr-release.jks
     storePassword=<store-pw>
     keyAlias=localocr
     keyPassword=<key-pw>
     ```
  3. Reference in `build.gradle.kts`:
     ```kotlin
     val keystoreProperties = Properties().apply {
       val f = rootProject.file("key.properties")
       if (f.exists()) load(FileInputStream(f))
     }
     signingConfigs {
       create("release") {
         storeFile = file(keystoreProperties["storeFile"] as String)
         storePassword = keystoreProperties["storePassword"] as String
         keyAlias = keystoreProperties["keyAlias"] as String
         keyPassword = keystoreProperties["keyPassword"] as String
       }
     }
     ```
- **Backup (mandatory BEFORE first prod build)**:
  - Copy `localocr-release.jks` + `key.properties` to a 1Password vault entry named `LocalOCR Android Release Keystore`.
  - Also copy to the encrypted backup bundle alongside `FERNET_SECRET_KEY` (per MEMORY: backup safety — DB + secrets travel together; same rule applies here: losing this keystore = permanently losing the ability to push updates to the Play Store, equivalent severity to losing Fernet keys).
  - Document recovery path in the runbook.

### Build commands

Dev debug on emulator (host backend on `10.0.2.2:5001`):
```
flutter run --flavor dev \
  --dart-define=API_BASE_URL=http://10.0.2.2:5001
```

Staging release APK on physical device (for QA):
```
flutter build apk --flavor staging \
  --dart-define=API_BASE_URL=https://staging.npalakurla.com \
  --release
adb install -r build/app/outputs/flutter-apk/app-staging-release.apk
```

Prod release App Bundle for Play Store:
```
flutter build appbundle --flavor prod \
  --dart-define=API_BASE_URL=https://extended.npalakurla.com \
  --release
```
- Output: `build/app/outputs/bundle/prodRelease/app-prod-release.aab`
- Universal APK (for sideload only — never publish): `flutter build apk --flavor prod --dart-define=API_BASE_URL=https://extended.npalakurla.com --release`

`--dart-define` values are baked into the binary; flavor + URL must match (dev↔10.0.2.2, staging↔staging.npalakurla.com, prod↔extended.npalakurla.com). Build script in §7 will enforce.

### Post-build self-validation (Android equivalent of macOS RULE 6)

After every release build (or dev build of a newly touched screen), run end-to-end. Agent performs each step itself — no smoke-test checklist passed to the user.

```bash
# 1. Build (dev/debug shown; same pattern for release)
flutter build apk --flavor dev \
  --dart-define=API_BASE_URL=http://10.0.2.2:5001 \
  --debug 2>&1 | tee /tmp/flutter_build.log
grep -E "Error|FAILURE|^✗|Gradle task .* failed" /tmp/flutter_build.log && { echo "BUILD FAILED"; exit 1; }

# 2. Reinstall clean (uninstall first to clear app state + permission grants)
adb uninstall com.localocr.extended.localocr.extended.dev || true
adb install -r build/app/outputs/flutter-apk/app-dev-debug.apk

# 3. Launch + capture logs (named per screen for traceability)
SCREEN="${1:-unspecified}"
adb logcat -c
adb shell am start -n com.localocr.extended.localocr.extended.dev/.MainActivity
adb logcat -v time | grep -E "flutter|LocalOCR" > /tmp/adb_${SCREEN}.log &
LOGCAT_PID=$!
sleep 6
kill $LOGCAT_PID 2>/dev/null

# 4. Failure grep — same patterns as macOS Rule 6
grep -E "cancelled|failed:|401|403|DecodingError|JsonReaderException|404|FATAL EXCEPTION|AndroidRuntime" /tmp/adb_${SCREEN}.log

# 5. Expected success line — every screen logs "loaded N <thing>" within 5s of mount
grep -E "loaded [0-9]+ " /tmp/adb_${SCREEN}.log || { echo "NO SUCCESS LINE for $SCREEN"; exit 1; }
```

Failure-mode triage (agent acts on these without asking):
- `cancelled` appearing > 1 time → Dart `Future` cancellation cascade (typically `CancelToken` reused across rebuilds, or Riverpod provider auto-disposed mid-fetch). Fix at the call site — do NOT swallow the cancellation.
- `401` / `403` → cookie jar empty or session expired. Re-login from the dev app, re-run; if it persists across login, the cookie persistence layer is broken (see §4 secure-storage cookie jar).
- `404` → endpoint inventory mismatch. Re-grep `src/backend/` for the route, fix the Dart `remote_source` to match (carry-over of macOS RULE 2: backend is ground truth, not Dart).
- `DecodingError` / `JsonReaderException` / `_$_…FromJson` thrown → response shape mismatch. Inspect the live JSON via `curl`, regenerate the freezed model with `build_runner`. Do NOT hand-patch the generated file.
- `FATAL EXCEPTION` in logcat (native Android crash) → typically `mobile_scanner` ML Kit init on devices without Play Services. Guard at startup, fall back to manual entry.
- No `loaded N` line for the screen under test → endpoint silently returned an empty payload. Verify against backend with `curl` before assuming the UI is broken.

### Visual parity check (Android equivalent of macOS RULE 14)

Per-screen, after post-build validation passes:
1. Capture Android:
   `adb exec-out screencap -p > /tmp/android_<screen>.png`
2. Capture web (orchestrator already provides this helper):
   `screencapture -l $(GetWindowID "Google Chrome" "*<screen>*") /tmp/web_<screen>.png`
3. Read BOTH via the `Read` tool (agent inspects, not the user).
4. Enumerate every visible delta — spacing, color, label wording, icon position, empty-state copy, sort order, pluralization.
5. Fix in the SAME iteration. Re-shoot. Re-compare.
6. Do NOT advance to the next screen until the Android screenshot matches the web screenshot to the agent's own satisfaction. Mismatches must be either fixed or recorded in §6 (Parity Exceptions Registry) with explicit justification — never silently accepted.

### Device validation matrix

| Slot | Device | API | Purpose |
|------|--------|-----|---------|
| Primary emulator | Pixel 7 | 34 (arm64) | Daily dev loop; orchestrator post-build validation |
| Secondary emulator | Pixel 6 Tablet | 34 (large screen) | NavigationRail breakpoint (§3, ≥ 840 dp); landscape layout |
| Foldable check (optional) | Pixel Fold | 34 | Caught early: hinge crash, posture changes — defer if scope-tight |
| Physical device (required for v1.0 ship) | Any Android 11+ phone | 30+ | Camera barcode scan (real `mobile_scanner` accuracy); `POST_NOTIFICATIONS` actual delivery; real cookie persistence across process kill (Doze + standby) |

CI cannot replace physical-device camera tests — flagged in §7.3 as an explicit assumption that a local agent runs them before any release tag. Do NOT ship a Play Store build without a physical-device pass on the camera + notification flows.

### CI (GitHub Actions — recommended, scope-aware)

`.github/workflows/android.yml`:
- **Triggers**: `push` to `feat/android-build`; `pull_request` to `main`.
- **Runner**: `ubuntu-latest` (cheaper than `macos-latest`; Android builds don't need macOS).
- **Steps**:
  1. `actions/checkout@v4`
  2. `actions/setup-java@v4` with `distribution: temurin`, `java-version: 17`
  3. `subosito/flutter-action@v2` with `channel: stable`, `flutter-version: 3.24.x`
  4. `flutter pub get`
  5. `flutter analyze` — must exit zero (CI fails on any warning, mirrors macOS RULE 18 zero-warning policy)
  6. `flutter test` — unit + widget tests
  7. `flutter build apk --flavor dev --dart-define=API_BASE_URL=http://10.0.2.2:5001 --debug` (no signing required for dev/debug)
  8. `actions/upload-artifact@v4` — attaches `app-dev-debug.apk` for download from PR
- **No release builds in CI for v1**: signing keys are NOT committed to CI secrets yet. Release builds are produced manually from the dev machine until §7 promotes signing to CI in a later milestone. This is an explicit, documented gap, not an oversight.
- **No emulator-based integration tests in CI for v1**: emulators on GH Actions are slow and flaky for camera/notification paths. Local agent owns those (matrix above).

### Pre-commit hooks (mirrors macOS RULE 16 file-touch grep)

`.git/hooks/pre-commit` (or `pre-commit` framework config) — installed at session start by the orchestrator:

```bash
#!/usr/bin/env bash
set -e

# 1. Formatting
dart format --set-exit-if-changed lib/ test/

# 2. Static analysis — zero warnings (RULE 18 carry-over)
flutter analyze --no-pub

# 3. @JsonKey coverage audit (V-7 RESOLVED — INVERTED from prior macOS direction)
#    Dart `json_serializable` does NOT auto-convert snake_case → camelCase the way Swift's
#    `.convertFromSnakeCase` does. Missing @JsonKey on a freezed response field that maps
#    to a snake_case Flask key produces a silent `null` at runtime (exact I-17 reproduction).
#    Fail the commit if ANY field in lib/features/*/data/ or lib/core/models/ lacks an
#    explicit @JsonKey annotation. Snake_case @JsonKey values are REQUIRED, not suspicious.
missing=$(python3 scripts/check_jsonkey_coverage.py lib/features lib/core/models 2>&1 || true)
if [ -n "$missing" ]; then
  echo "$missing"
  echo "Add explicit @JsonKey(name: '<flask_key>') to every field on every freezed response class."
  exit 1
fi

# 4. CancelToken audit — flag any caller-side .cancel() without a comment explaining why
#    (failure-mode triage above: stray cancels cause the "cancelled" cascade)
if grep -rnE '\.cancel\(\)' lib/ | grep -vE '//.*cancel' ; then
  echo "Bare .cancel() call(s) detected — add a // comment justifying the cancellation."
  exit 1
fi

# 5. Print-statement audit — no rogue prints in committed code
if grep -rnE '^\s*print\(' lib/ ; then
  echo "print() found in lib/ — use logger.* instead."
  exit 1
fi

echo "pre-commit OK"
```

Commit is blocked if any check fails — this is the RULE 0 done-criteria gate for Android, identical in spirit to the macOS pre-commit gate. Agent self-verifies BEFORE proposing the commit; the hook is the belt-and-suspenders catch.


---

## §6 Per-screen plan (Agent 6)

This section emits one subsection per unique `## Screen:` heading in `FEATURE_PARITY_REGISTRY.md` (22 total). Endpoints are quoted verbatim from the registry's Endpoint column; client-only rows (`—`) emit no endpoint. Architecture follows §2 (`lib/features/<feature>/presentation/` + Riverpod) and §4 (dio + freezed + Drift, AuthInterceptor on 401, ConnectivityInterceptor on offline). The `loaded N <thing>` log line per RULE 6 is recorded for each data-loading screen.

---

### §6.1 Screen: AppShell

- **Source registry rows**: F-001..F-038 (count: 38)
- **Route**: not a route — global scaffold mounted by `MaterialApp.router` and wrapped around every routed page via `ShellRoute`
- **File path**: `lib/features/appshell/presentation/app_shell.dart`
- **Widgets to build**:
  - `LocalOcrDrawer` — navigation drawer covering F-001..F-020 (sidebar nav items + collapse). One `_DrawerNavTile` covers F-002..F-020; collapse handled by Material `NavigationDrawer` open/close state (F-001).
  - `AppBarTitle` — covers F-023, F-024 (long-press secret) and brand display.
  - `ThemeToggleButton` — covers F-021 (action button in AppBar).
  - `MobileMenuButton` — covers F-022 (hamburger; only on narrow layouts).
  - `ChatFab` — floating `Stack`-positioned chat launcher covering F-032..F-038 (open, send, clear, minimize, input).
  - `ChatPanelSheet` — `DraggableScrollableSheet` hosting chat (F-033 close, F-036 sized via sheet snap-points, F-037 input, F-038 send).
  - `ActionToastOverlay` — covers F-025 (Undo + countdown surface; deferred details in SharedModals).
  - `ConfirmDialogHost` — covers F-026 (mounted via Navigator dialog).
  - `ManualEntryHost` — covers F-027 (sheet route).
  - `OverscrollNavListener` — `NotificationListener<OverscrollNotification>` covering F-028 (edge-pull to next/prev page).
  - `KeyboardNavListener` — `Focus` + `Shortcuts`/`Actions` covering F-029 (Alt+←/→). F-030 (`g g` design-gallery) is marked `🚫 dev-only` in the registry and is intentionally not implemented on Android.
  - `DeepLinkRouter` — handles F-031 (Android intent-based deep links replace `#hash` routing per registry note).
- **State holders**:
  - `appShellStateProvider` (`Notifier<AppShellState>`) — owns drawer-open flag, current route key, mobile-menu state.
  - `themeProvider` (`Notifier<ThemeMode>`) — owns light/dark/clay theme (cycled by F-021; canonical store from Settings F-2016).
  - `chatStateProvider` (`AsyncNotifier<ChatState>`) — owns chat thread, send-in-flight flag, open/minimized flag (F-032..F-038).
  - `chatRepositoryProvider` (`Provider<ChatRepository>`) — wraps dio calls for `/chat/messages`.
  - `overscrollNavSettingProvider` (`Notifier<bool>`) — mirrors F-2017 (persisted to SharedPreferences/Drift).
- **Endpoints called**, grouped by user action:
  - Send chat message (F-038): `POST /chat/messages`
  - Clear chat thread (F-034): `POST /chat/messages` (DELETE-style payload per registry)
  - All sidebar nav items (F-002..F-020): no endpoint — pure navigation.
- **Edge cases**:
  - Empty state (no chat history) — chat panel shows "Ask me anything about your household" placeholder.
  - Offline — sidebar nav still works (routes mount from cache); chat send shows "Offline — chat requires network" snackbar and disables send button (read from `connectivityProvider` from §4).
  - Error (network/5xx) — chat send surfaces snackbar + Retry button; nav unaffected.
  - Loading (initial + refresh) — chat panel shows `CircularProgressIndicator` during send; drawer never blocks.
  - Auth (401) — AuthInterceptor → /login redirect; on return, current route restored via `GoRouter.refresh()`.
  - Conflict (409) — not applicable (no editable shared state in shell).
- **`loaded N <thing>` log**: `loaded N chat messages` (chat thread load on panel open).

---

### §6.2 Screen: Login

- **Source registry rows**: F-101..F-120 (count: 20)
- **Route**: `/login` (from §3)
- **File path**: `lib/features/auth/presentation/login_screen.dart`
- **Widgets to build**:
  - `EmailPasswordForm` — covers F-101..F-104 (email/password inputs, show-password eye, primary Login button).
  - `_GoogleSignInButton` — covers F-105, F-106, F-110 (visible only when `bootstrap.google_oauth_enabled`).
  - `_PairDeviceButton` — covers F-107 (launches device-pairing modal from SharedModals).
  - `_ForgotPasswordButton` — covers F-108.
  - `_InviteLandingOverlay` — covers F-109, F-111 (shown when deep link contains `?invite=` token).
  - `_DeviceApprovalCard` — covers F-112..F-119 (pending device approval inline card with pill, name/user/scope/admin fields, Reject and Approve buttons).
  - `_BootstrapLoader` — lifecycle widget that triggers F-120 on mount.
- **State holders**:
  - `loginStateProvider` (`AsyncNotifier<LoginState>`) — owns email, password, in-flight flag, error message, bootstrap config (google_oauth_enabled, etc.), invite-token, pending device-pairing payload.
  - `authRepositoryProvider` (`Provider<AuthRepository>`) — `/auth/*` calls.
  - `deviceApprovalProvider` (`AsyncNotifier<DeviceApprovalState>`) — polls pairing status for the inline card.
- **Endpoints called**:
  - Mount/bootstrap (F-120): `GET /auth/bootstrap-info`, `GET /auth/app-config`.
  - Submit login (F-104): `POST /auth/login`.
  - Google OAuth start (F-105, F-110): `GET /auth/oauth/google` (opened via in-app browser tab / Custom Tabs).
  - Pair device launch (F-107): `POST /auth/device-pairing/start`.
  - Forgot password (F-108): `POST /auth/forgot-password`.
  - Invite landing (F-109): `GET /auth/invite/<token>`.
  - Device approval pill / poll (F-112): `GET /auth/device-pairing/status/<token>`.
  - Device approval — load linked users (F-114): `GET /auth/users`.
  - Device approval reject (F-118): `POST /auth/device-pairing/reject`.
  - Device approval approve (F-119): `POST /auth/device-pairing/approve`.
- **Edge cases**:
  - Empty state (no fields) — Login button disabled until email + password non-empty.
  - Offline — banner "Offline — connect to sign in"; submit disabled; cached bootstrap config still rendered if present.
  - Error (5xx, invalid credentials) — inline error pill + snackbar with Retry.
  - Loading — submit button switches to spinner; eye toggle still works.
  - Auth (401) — login itself returns 401 → display "Invalid credentials"; no redirect loop (interceptor skips `/login` and `/auth/*` paths).
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded bootstrap config` (the single bootstrap fetch — there's no list cardinality here, but the per-screen mount log is still emitted per RULE 6).

---

### §6.3 Screen: Dashboard

- **Source registry rows**: F-201..F-234 (count: 34)
- **Route**: `/dashboard`
- **File path**: `lib/features/dashboard/presentation/dashboard_screen.dart`
- **Widgets to build**:
  - `DashboardHeader` — covers F-201 (H1 + subtitle).
  - `_DemoHero` — covers F-202..F-206 (read-only demo hero with Sign-In + demo buttons).
  - `_LeaderboardCard` — covers F-207..F-210 (title, collapsed preview, "Show full ranking", row tap).
  - `_AttributionNudge` — covers F-211 (Tag now → Receipts with `untagged_only`).
  - `_StatTile` — covers F-212..F-215 (low / inv / prod / keyboard-shortcut deferral).
  - `_SpendingByCategoryCard` — covers F-216..F-219 (collapse, total stat, drill row, Show more).
  - `_LowStockCard` — covers F-220..F-222 (title, count chip, row tap).
  - `_ReceiptsActivityCard` — covers F-223..F-227 (collapse + Day/Week/Month chips + SVG-replaced `CustomPaint` sparkline).
  - `_TopPicksCard` — covers F-228, F-229 (recommendations card + per-rec Add).
  - `_ShoppingSummaryCard` — covers F-230..F-233 (header link, count chip, Estimate toggle, preview row tap).
  - F-234 (Floor Obligations hidden card) — registry marks `🚫 hidden in web; do not port`; intentionally not built.
- **State holders**:
  - `dashboardStateProvider` (`AsyncNotifier<DashboardState>`) — owns leaderboard, stat tiles, spending-by-category, low-stock, receipts-activity, recommendations, shopping-summary aggregates, plus per-card collapsed flag and selected receipts-activity grain.
  - `dashboardRepositoryProvider` (`Provider<DashboardRepository>`) — fan-out fetcher.
  - `recommendationsProvider` (`AsyncNotifier<List<Recommendation>>`) — shared with Shopping screen (F-1027).
- **Endpoints called**, grouped by user action:
  - Initial mount: `GET /contributions/leaderboard` (F-207), `GET /inventory` (F-213), `GET /products` (F-214), `GET /analytics/spending-by-category` (F-216), `GET /analytics/receipts-activity?grain=day|week|month` (F-224..F-226), `GET /recommendations` (F-228).
  - Add recommendation to list (F-229): `POST /shopping-list/items`.
  - Stat tile taps (F-212..F-214): navigate only — no extra call beyond the prefetch.
- **Edge cases**:
  - Empty state — each card renders its own empty card ("No low-stock items", "No recent receipts", "No recommendations yet").
  - Offline — show last cached snapshot from Drift; banner "Offline — showing cached data"; Add-to-list (F-229) queues to outbox.
  - Error (5xx per-endpoint) — individual card switches to error tile with Retry; siblings keep rendering.
  - Loading — each card has its own skeleton; initial pull-to-refresh on the whole screen.
  - Auth (401) — AuthInterceptor → /login redirect.
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded N dashboard cards` (where N = number of card payloads successfully hydrated).

---

### §6.4 Screen: Inventory

- **Source registry rows**: F-301..F-374 (count: 74)
- **Route**: `/inventory`
- **File path**: `lib/features/inventory/presentation/inventory_screen.dart`
- **Widgets to build**:
  - `_AddItemCard` — covers F-301..F-313 (collapsible add form: name autocomplete, qty, location + custom, threshold, more-details, category, unit chip row, preferred-store select, add-to-shopping checkbox, primary Add button, inline product creation form).
  - `_InventoryFilterBar` — covers F-314..F-318 (search, location, group-by, sort, show-empty).
  - `_InventoryHeaderActions` — covers F-319, F-320, F-322, F-323 (Recently used up, Merge duplicates, low badge, window note).
  - `_CategoryChipRow` — covers F-321.
  - `_BulkActionBar` — covers F-324..F-329 (−1 all, +3d, +7d, used-up all, Clear, undo toast).
  - `_InventoryGroupHeader` — covers F-330, F-331.
  - `_InventoryTile` — covers F-332..F-360 (checkmark, image, days-left, range, qty pill, remaining-pct bar, drag bubble, drag slider, ±10% steppers, status cycle tap, name, ~est suffix, meta lines, edit, defer, hold-alt defer, cart, decrement, used-up, hold-alt cart+used, AI gen, delete, swipe gestures, long-press, tap-expand).
  - `_InventoryContextMenu` — covers F-361 (long-press payload menu).
  - `_EditProductSheet` — covers F-362..F-368 (name, photo picker, gallery delete, gallery promote, category, Cancel, Save).
  - `_RecentlyUsedUpSection` — covers F-369..F-373 (Hide, restore tile image, restore tile meta, Restore button, Add-to-list toggle).
  - `_ProductSnapshotPicker` — covers F-374 (hidden file input wrapper around `image_picker`).
- **State holders**:
  - `inventoryListProvider` (`AsyncNotifier<List<InventoryItem>>`) — owns the canonical list; reads from Drift cache, refreshes from network.
  - `inventoryFiltersProvider` (`Notifier<InventoryFilters>`) — owns search text, location, group-by, sort, show-empty, category chip set.
  - `inventoryBulkSelectionProvider` (`Notifier<Set<int>>`) — owns multi-select set and last-snapshot for undo.
  - `inventoryAddFormProvider` (`Notifier<InventoryAddForm>`) — owns add-card draft.
  - `inventoryRepositoryProvider` (`Provider<InventoryRepository>`) — wraps `/inventory*`, `/products*`, `/product-snapshots*`.
  - `recentlyUsedUpProvider` (`AsyncNotifier<List<InventoryItem>>`) — drives restore modal.
  - `editProductSheetProvider` (`AsyncNotifier<EditProductState>`) — per-open sheet state including pending photo uploads.
- **Endpoints called**, grouped by user action:
  - Mount + refresh: `GET /inventory` (F-213/list); category options from `/api/stores` (F-310).
  - Add inventory item (F-312): `POST /inventory`; inline product create (F-313): `POST /products`.
  - Recently used up (F-319): `GET /inventory/recently-used-up?days=30`.
  - Merge duplicates (F-320): `POST /products/merge-duplicates`.
  - Bulk −1 (F-324), +3d (F-325), +7d (F-326): `PATCH /inventory/products/<id>` (per-id) with quantity/defer_days payload.
  - Bulk used-up (F-327): `PATCH /inventory/products/<id>/consume`.
  - Bulk undo (F-329): `PATCH /inventory/products/<id>` (snapshot restore).
  - Tile drag slider / ±10% (F-339..F-341): `PATCH /inventory/products/<id>` consumed_pct_override.
  - Tile status cycle (F-342): `PATCH /inventory/<id>/status`.
  - Tile defer (F-349, F-350): `PATCH /inventory/products/<id>` defer_days=3 or 7.
  - Tile cart (F-351, F-354): `POST /shopping-list/items`.
  - Tile −1 (F-352, F-357): `PATCH /inventory/products/<id>` quantity (optimistic).
  - Tile used-up / swipe-left (F-353, F-358): `PATCH /inventory/products/<id>/consume`.
  - Tile AI gen image (F-355): `POST /product-snapshots/generate`.
  - Tile delete (F-356): `DELETE /products/<id>`.
  - Edit sheet save (F-362, F-366, F-368): `PUT /products/<id>/update`.
  - Edit sheet photo upload (F-363, F-374): `POST /product-snapshots/upload`.
  - Edit sheet photo delete (F-364): `DELETE /product-snapshots/<id>`.
  - Edit sheet photo promote (F-365): `POST /product-snapshots/<id>/promote`.
  - Restore one (F-372): `POST /inventory/products/<id>/restore`.
  - Restore add-to-list (F-373): `POST /shopping-list/items`.
  - Tile image fetches (F-333, F-370): `GET /product-snapshots/...`.
- **Edge cases**:
  - Empty state — "No inventory yet — add your first item" with primary CTA opening the add form.
  - Offline — render Drift-cached list with offline banner; PATCH/POST/DELETE actions queue to outbox (`offlineMutationsProvider`); reads succeed from cache; image fetches show placeholder.
  - Error (5xx) — per-tile error toast with Retry; bulk action shows snackbar with row IDs that failed.
  - Loading — initial skeleton tiles; refresh via `RefreshIndicator`; per-tile optimistic UI for decrement/used-up.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — Edit Save (F-368) shows merged toast when server returns merge collision (per registry "merged toast on collision").
- **`loaded N <thing>` log**: `loaded N inventory items`.

---

### §6.5 Screen: Products

- **Source registry rows**: F-401..F-435 (count: 35)
- **Route**: `/products`
- **File path**: `lib/features/products/presentation/products_screen.dart`
- **Widgets to build**:
  - `_AddProductCard` — covers F-401..F-404 (name, category, barcode, Add Product).
  - `_ProductCatalogHeader` — covers F-405..F-408 (count, search, sort, refresh).
  - `_ProductCategoryChipRow` — covers F-409.
  - `_ProductGroupHeader` — covers F-410.
  - `_ProductTile` — covers F-411..F-420 (image, category + Low badge, ×count, name with ⭐, latest purchase, variant examples, edit, cart, AI gen, delete).
  - `_ProductTileVariantExpander` — covers F-421.
  - `_VariantDetailRow` — covers F-422..F-435 (name+Low, size/bought meta, mini-link receipt buttons, Edit, Add, delete, rename, photo, view photo, Set/Clear Low, Unit, Size Label, Save unit/size, Category change).
- **State holders**:
  - `productsListProvider` (`AsyncNotifier<List<Product>>`) — owns paginated/grouped product list.
  - `productsFiltersProvider` (`Notifier<ProductFilters>`) — search text, sort, category-chip set.
  - `productsRepositoryProvider` (`Provider<ProductsRepository>`) — `/products*`, `/product-snapshots*`, `/receipts/<id>`.
  - `productVariantExpansionProvider` (`Notifier<Set<int>>`) — which tiles are expanded.
- **Endpoints called**, grouped by user action:
  - Mount + refresh (F-408): `GET /products`.
  - Add Product (F-404): `POST /products/create`.
  - Edit (F-417, F-425, F-428): `PUT /products/<id>/update`.
  - Cart (F-418, F-426): `POST /shopping-list/items`.
  - AI gen image (F-419): `POST /product-snapshots/generate`.
  - Delete (F-420, F-427): `DELETE /products/<id>`.
  - Variant mini-link receipt (F-424): `GET /receipts/<id>`.
  - Variant photo upload (F-429): `POST /product-snapshots/upload`.
  - Set/Clear Low (F-431): `PATCH /products/<id>/low-status`.
  - Unit defaults Save (F-432..F-434): `PATCH /products/<id>/unit-defaults`.
  - Category change (F-435): `PUT /products/<id>/category`.
  - Tile image fetch (F-411): `GET /product-snapshots/...`.
- **Edge cases**:
  - Empty state — "Catalog empty — add your first product" with CTA.
  - Offline — Drift cache; mutations queued to outbox; image fetch shows placeholder.
  - Error (5xx) — snackbar + Retry; failed tile mutation rolled back optimistically.
  - Loading — skeleton tiles + grouped header.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — Variant rename / Edit Save merged-toast (F-368 carry-over for product edits).
- **`loaded N <thing>` log**: `loaded N products`.

---

### §6.6 Screen: Medicine

- **Source registry rows**: F-501..F-539 (count: 39)
- **Route**: `/medicine`
- **File path**: `lib/features/medicine/presentation/medicine_screen.dart`
- **Widgets to build**:
  - `_MedicineHeader` — covers F-501..F-503 (header, +Add Medication, 👥 Members buttons).
  - `_MedicineFilterBar` — covers F-504 (status filter).
  - `_MedicineMemberChipRow` — covers F-505, F-506.
  - `_MedTile` — covers F-507..F-517 (image, age-group label, Expired/Low badges, qty pill, name + strength, expiry, member/household label, AI warning, edit, ✓ Done, delete).
  - `_AddEditMedicationSheet` — covers F-518..F-535 (all add/edit fields including barcode scans, Lookup, Cancel, Save).
  - `_MembersSheet` — covers F-536..F-539 (member-row delete, Add name/age/Add button).
- **State holders**:
  - `medicineListProvider` (`AsyncNotifier<List<Medication>>`) — owns med list; reacts to status + member filter.
  - `medicineFiltersProvider` (`Notifier<MedicineFilters>`) — status, member id (member_id or user_id).
  - `medicineRepositoryProvider` (`Provider<MedicineRepository>`) — `/medications*`, `/household-members*`.
  - `householdMembersProvider` (`AsyncNotifier<List<HouseholdMember>>`) — used by chip row and Belongs-To select.
  - `medSheetProvider` (`Notifier<MedSheetState>`) — open sheet draft (add or edit).
- **Endpoints called**:
  - Mount/refresh (F-504, F-506): `GET /medications?status=...&member_id=...&user_id=...`.
  - Tile image (F-507): `GET /medications/<id>/photo`.
  - Mark finished (F-516): `PUT /medications/<id>` (status=finished).
  - Delete (F-517): `DELETE /medications/<id>`.
  - Save sheet (F-535, F-518..F-530): `POST /medications` (new) or `PUT /medications/<id>` (edit).
  - Barcode camera/gallery (F-531, F-532) + Lookup (F-533): `POST /medications/barcode-lookup`.
  - Members sheet — delete (F-536): `DELETE /household-members/<id>`.
  - Members sheet — Add (F-537..F-539): `POST /household-members`.
- **Edge cases**:
  - Empty state — "No medications yet — add one to track expiry".
  - Offline — cached list from Drift; mutations queued; barcode-lookup blocked with "Offline — scan requires network".
  - Error (5xx) — snackbar + Retry.
  - Loading — skeleton tiles; sheet save shows inline spinner on Save button.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — not common; if `PUT /medications/<id>` returns 409, surface "Medication changed elsewhere — reload" toast.
- **`loaded N <thing>` log**: `loaded N medications`.

---

### §6.7 Screen: Restaurant

- **Source registry rows**: F-601..F-613 (count: 13)
- **Route**: `/restaurant`
- **File path**: `lib/features/restaurant/presentation/restaurant_screen.dart`
- **Widgets to build**:
  - `_RestaurantStatGrid` — covers F-601..F-604 (Visits, Spend, Average Ticket, Top Restaurant).
  - `_DiningBudgetCard` — covers F-605..F-608 (month picker, amount input, Save, progress bar).
  - `_ReceiptReviewControls` — covers F-609, F-610 (period select, refresh).
  - `_RestaurantReceiptRow` — covers F-611 (row tap → inline detail).
  - `_TopRestaurantsList` — covers F-612 (row tap → store filter).
  - `_TopOrderedItemsList` — covers F-613 (row tap → item filter).
- **State holders**:
  - `restaurantStateProvider` (`AsyncNotifier<RestaurantState>`) — owns receipts list, stats, top-store, top-items, selected period.
  - `restaurantBudgetProvider` (`AsyncNotifier<DiningBudget>`) — owns selected month + budget amount + status.
  - `restaurantRepositoryProvider` (`Provider<RestaurantRepository>`) — `/receipts?type=restaurant`, `/analytics/*`, `/budget*`.
- **Endpoints called**:
  - Stats / list (F-601, F-609, F-610, F-611, F-612, F-613): `GET /receipts?type=restaurant[&months=N][&store=...][&item=...]`.
  - Spending stat (F-602): `GET /analytics/spending?domain=restaurant`.
  - Top merchants (F-604): `GET /analytics/top-merchants?domain=restaurant`.
  - Budget load (F-605, F-608): `GET /budget/status?month=<YYYY-MM>&domain=restaurant` (web `loadRestaurantBudget()` at src/frontend/index.html:35591, blueprint `manage_household_budget.py:284`). NOTE registry rows F-605/F-608 mislabel the path as `/budget/dining` — corrected to real endpoint per agent-rules RULE 1.
  - Budget save (F-606, F-607): `POST /budget/set-monthly` body `{month, budget_category:"dining"}` (web `index.html:35643`, blueprint `manage_household_budget.py:160`). Registry's `POST /budget category=dining` is rewritten to the real `/budget/set-monthly` path.
  - Receipt row open (F-611): `GET /receipts/<id>` for inline detail.
  - Average ticket (F-603): derived client-side — no extra endpoint.
- **Edge cases**:
  - **Feature-flag gated** — per §3, Restaurant route is mounted only when `featureFlagsProvider.restaurantEnabled == true` (driven by `/auth/app-config`). When disabled, the drawer entry F-010 is hidden and direct deep links resolve to a "Feature unavailable" placeholder.
  - Empty state — "No restaurant receipts yet" with CTA to Upload.
  - Offline — cached list from Drift; budget save queued to outbox.
  - Error (5xx) — per-card error tile + Retry; budget save snackbar.
  - Loading — skeleton stats + skeleton list.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded N restaurant receipts`.

---

### §6.8 Screen: Balances

- **Source registry rows**: F-701..F-706 (count: 6)
- **Route**: `/balances`
- **File path**: `lib/features/balances/presentation/balances_screen.dart`
- **Widgets to build**:
  - `_BalancesHeader` — covers F-701 (refresh button).
  - `_WhoOwesWhatCard` — covers F-702 (title).
  - `_ContactBalanceRow` — covers F-703..F-705 (per-contact row with name + amount, Settle all, expand → debts list).
  - `_DebtRow` — covers F-706 (per-debt settle).
- **State holders**:
  - `balancesProvider` (`AsyncNotifier<BalancesState>`) — owns contact balance list + expanded contact id.
  - `balancesRepositoryProvider` (`Provider<BalancesRepository>`) — `/shared-dining/*`.
- **Endpoints called**:
  - Mount/refresh (F-701, F-703): `GET /shared-dining/balances`.
  - Settle all with contact (F-704): `POST /shared-dining/contacts/<id>/settle-all`.
  - Per-debt settle (F-706): `POST /shared-dining/debts/<id>/settle`.
- **Edge cases**:
  - Empty state — "All settled — no outstanding balances".
  - Offline — cached balances from Drift; settle actions queued to outbox.
  - Error (5xx) — snackbar + Retry.
  - Loading — skeleton rows.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — if settle returns 409 (balance changed), show "Balance updated — refreshing" toast and re-fetch.
- **`loaded N <thing>` log**: `loaded N balances`.

---

### §6.9 Screen: Contacts (Dining)

- **Source registry rows**: F-801..F-806 (count: 6)
- **Route**: `/contacts`
- **File path**: `lib/features/contacts/presentation/contacts_screen.dart`
- **Widgets to build**:
  - `_ContactsHeader` — covers F-801 (refresh).
  - `_AddContactForm` — covers F-802..F-805 (name, phone, email, Add button).
  - `_ContactCard` — covers F-806 (avatar, name, phone/email row).
- **State holders**:
  - `contactsProvider` (`AsyncNotifier<List<DiningContact>>`) — owns contact list.
  - `contactFormProvider` (`Notifier<ContactFormState>`) — owns add-form draft.
  - `contactsRepositoryProvider` (`Provider<ContactsRepository>`) — `/shared-dining/contacts*`.
- **Endpoints called**:
  - Mount/refresh (F-801, F-806): `GET /shared-dining/contacts`.
  - Add contact (F-802..F-805): `POST /shared-dining/contacts`.
- **Edge cases**:
  - Empty state — "No saved contacts yet — add one to split bills".
  - Offline — cached list from Drift; add contact queued to outbox.
  - Error (5xx) — snackbar + Retry on add.
  - Loading — skeleton cards.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — duplicate email/phone may return 409; surface "Contact already exists" inline error.
- **`loaded N <thing>` log**: `loaded N contacts`.

---

### §6.10 Screen: Expenses

- **Source registry rows**: F-901..F-916 (count: 16)
- **Route**: `/expenses`
- **File path**: `lib/features/expenses/presentation/expenses_screen.dart`
- **Widgets to build**:
  - `_ExpenseStatGrid` — covers F-901..F-904 (count, total spend, avg ticket, top merchant).
  - `_ExpenseBudgetCard` — covers F-905..F-908 (month, amount, Save, status).
  - `_ExpenseControls` — covers F-909, F-910 (period select, refresh).
  - `_ExpenseRow` — covers F-911 (row tap → select).
  - `_ExpenseDetailPanel` — covers F-912 (selected receipt detail).
  - `_TopMerchantsList` — covers F-913.
  - `_TopReferenceItemsList` — covers F-914.
  - `_ExpenseCategoryBreakdown` — covers F-915 (breakdown bar).
  - F-916 (mobile reposition) — registry marks `🔄 native layout handles this; no port needed`.
- **State holders**:
  - `expensesProvider` (`AsyncNotifier<ExpensesState>`) — receipts list, stats, top merchants, top items, breakdown, selected receipt id, period.
  - `expenseBudgetProvider` (`AsyncNotifier<ExpenseBudget>`) — month + amount + status.
  - `expensesRepositoryProvider` (`Provider<ExpensesRepository>`) — `/receipts?type=general_expense`, `/analytics/*`, `/budget*`.
- **Endpoints called**:
  - Stats/list (F-901, F-909, F-910, F-911): `GET /receipts?type=general_expense[&months=N]`.
  - Spending (F-902): `GET /analytics/spending?domain=general_expense`.
  - Top merchants (F-904): `GET /analytics/top-merchants?domain=general_expense`.
  - Budget load (F-905, F-908): `GET /budget/status?month=<YYYY-MM>&domain=general_expense` (web `loadExpenseBudget()` at src/frontend/index.html:36826/36833, blueprint `manage_household_budget.py:284`). Registry rows F-905/F-908 mislabel the path; corrected here per RULE 1.
  - Budget save (F-906, F-907): `POST /budget/set-monthly` body `{month, budget_category:"general_expense"}` (web `index.html:36878`, blueprint `manage_household_budget.py:160`). Registry's `POST /budget` is rewritten to real `/budget/set-monthly`.
  - Receipt detail (F-911, F-912): `GET /receipts/<id>`.
  - Category breakdown (F-915): `GET /analytics/categories?domain=general_expense`.
- **Edge cases**:
  - Empty state — "No general-expense receipts yet" with CTA to Upload.
  - Offline — cached list; budget save queued.
  - Error (5xx) — per-card error tile + Retry.
  - Loading — skeleton stats and list.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded N expense receipts`.

---

### §6.11 Screen: Shopping

- **Source registry rows**: F-1001..F-1069 (count: 69)
- **Route**: `/shopping`
- **File path**: `lib/features/shopping/presentation/shopping_screen.dart`
- **Widgets to build**:
  - `_ShoppingHeader` — covers F-1001..F-1003 (Quick Find toggle, recommendations chip, helper intro banner).
  - `_SessionBanner` — covers F-1004.
  - `_SummaryPills` — covers F-1005..F-1007 (Open count, Estimate total, Close count).
  - `_ManualAddForm` — covers F-1008..F-1018 (Hide toggle, Identify from Photo, file input, preview image, name/category/store/price/qty/note, Add button).
  - `_QuickFindCard` — covers F-1019..F-1025 (collapse, search, store filter, Add Manually toggle, per-result Add / Mark Low / Mark Bought).
  - `_RecommendationsCard` — covers F-1026..F-1029 (chip, refresh, per-rec Add / Dismiss).
  - `_CurrentListCard` — covers F-1030..F-1037 (title toggle, aggregate total, A/Z/$ sort chips, store-group header, store total, item-count chip).
  - `_ShoppingItemRow` — covers F-1038..F-1057 (thumb + zoom, placeholder, name + merged meta, full-name expander, Store/Unit/Size/Unit-Price selects, Update, Rename, actual-price strip, −1, Bought/Reopen, More menu trigger, More menu items: Add Photo, View Photo, Low/Clear Low, Out of Stock/Reopen, Rename, Delete).
  - `_SkippedSection` — covers F-1058..F-1060 (details summary, ↩ Open, 🗑 delete).
  - `_ShoppingGestureLayer` — covers F-1061..F-1064 (long-press, swipe-left/right, right-click→long-press fallback, mobile expand).
  - `_ShoppingSnapshotPicker` — covers F-1065 (hidden snapshot picker).
  - `_PastTripsCard` — covers F-1066..F-1069 (header collapse, chevron, row tap → detail, detail item row).
- **State holders**:
  - `shoppingListProvider` (`AsyncNotifier<ShoppingState>`) — owns full list grouped by store, view filter (open/purchased), sort, skipped expansion.
  - `shoppingFiltersProvider` (`Notifier<ShoppingFilters>`) — preferred-store, sort mode, view.
  - `quickFindProvider` (`AsyncNotifier<List<Product>>`) — quick-find search results.
  - `recommendationsProvider` (`AsyncNotifier<List<Recommendation>>`) — shared with Dashboard.
  - `shoppingSessionProvider` (`AsyncNotifier<ShoppingSession?>`) — current session for the banner.
  - `pastTripsProvider` (`AsyncNotifier<List<ShoppingSession>>`) — past trips card.
  - `shoppingRepositoryProvider` (`Provider<ShoppingRepository>`) — `/shopping-list/*`, `/products*`, `/recommendations*`, `/product-snapshots*`.
- **Endpoints called**, grouped by user action:
  - Mount: `GET /shopping-list/sessions/current` (F-1004), `GET /recommendations` (F-1002, F-1027), main list via `/shopping-list/items` (implicit list endpoint already in §4 inventory of `/shopping-list/*`).
  - Manual add — Identify Photo (F-1009, F-1010): `POST /shopping-list/identify-photo`.
  - Manual add — submit (F-1012..F-1018): `POST /shopping-list/items`.
  - Quick Find search (F-1020): `GET /products?q=...&shopping=1`.
  - Quick Find Add (F-1023): `POST /shopping-list/items`; Mark Low (F-1024): `PATCH /products/<id>/low-status`; Mark Bought (F-1025): `POST /shopping-list/items` then `PUT /shopping-list/items/<id>` status=purchased.
  - Recommendation Add (F-1028): `POST /shopping-list/items`; Dismiss (F-1029): `POST /recommendations/<id>/dismiss`.
  - Item update (F-1042..F-1049, F-1055, F-1056): `PUT /shopping-list/items/<id>` (preferred_store / unit / size_label / price / actual_price / status / name).
  - Item delete (F-1057, F-1060): `DELETE /shopping-list/items/<id>`.
  - Item Bought/Reopen (F-1050): `PUT /shopping-list/items/<id>` status=purchased|open.
  - Skipped Open (F-1059): `PUT /shopping-list/items/<id>` status=open.
  - Swipe gestures (F-1062): `PUT /shopping-list/items/<id>` status.
  - More menu Low/Clear Low (F-1054): `PATCH /products/<id>/low-status`.
  - Photo upload (F-1052, F-1065): `POST /product-snapshots/upload`.
  - Past Trips (F-1066, F-1068): `GET /shopping-list/sessions`, `GET /shopping-list/sessions/<id>`.
- **Edge cases**:
  - Empty state — "Shopping list empty — add items via Quick Find or Manual".
  - Offline — render Drift-cached list with offline banner; Add/Update/Delete actions queue to outbox; Identify-from-photo blocked with "Offline — photo identification requires network".
  - Error (5xx) — per-row optimistic rollback + snackbar with Retry.
  - Loading — skeleton item rows under store-group headers; pull-to-refresh.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — if `PUT /shopping-list/items/<id>` returns 409 (concurrent edit), show merged-toast and re-fetch the item.
- **`loaded N <thing>` log**: `loaded N shopping items`.

---

### §6.12 Screen: Kitchen

- **Source registry rows**: F-1101..F-1149 (count: 49)
- **Route**: `/kitchen`
- **File path**: `lib/features/kitchen/presentation/kitchen_screen.dart`
- **Widgets to build**:
  - `_KitchenCatalogToggle` — covers F-1101.
  - `_CatalogChipRow` — covers F-1102, F-1103 (Frequent + per-category).
  - `_CatalogSearchBar` — covers F-1104..F-1106 (search input, 🔍 icon, store filter popover).
  - `_CatalogGridArrows` — covers F-1107, F-1108 (prev/next), F-1149 (horizontal scroll covered by native scroll per registry note).
  - `_CatalogTile` — covers F-1109..F-1118 (image/emoji, price badge, +N variants badge, purchase-count badge, name, tap-add, variant picker tap, on-list visual, long-press, right-click→long-press fallback).
  - `_KitchenContextMenu` — covers F-1119..F-1121 (Add, Pick variant, Show only this product's stores).
  - `_KitchenListHeader` — covers F-1122..F-1126 (Names toggle, list total, weather widget, empty state, store group header).
  - `_KitchenListTile` — covers F-1127, F-1128 (tap → open sheet, skipped overlay).
  - `_KitchenListContextMenu` — covers F-1129..F-1136 (Decrease, Increase, Bought, Low, Skip, Open, Delete, Edit details).
  - `_KitchenItemSheet` — covers F-1137..F-1147 (Close, store picker + Clear, ± qty, Bought, Low, Skip, Delete, Open, Presets row).
  - `_VariantPickerSheet` — covers F-1148 (variant tile tap → add).
- **State holders**:
  - `kitchenCatalogProvider` (`AsyncNotifier<KitchenCatalog>`) — owns catalog grouped by category, active chip, search text, store filter set.
  - `kitchenListProvider` (`AsyncNotifier<List<ShoppingItem>>`) — mirrors shopping list filtered to "kitchen" view; reuses `shoppingRepositoryProvider`.
  - `kitchenSheetProvider` (`Notifier<KitchenSheetState?>`) — currently-open item sheet.
  - `kitchenWeatherProvider` (`AsyncNotifier<KitchenWeather>`) — open-meteo fetch (F-1124).
  - `kitchenRepositoryProvider` (`Provider<KitchenRepository>`) — `/api/kitchen/catalog`, `/shopping-list/*`, `/products/<id>/low-status`.
- **Endpoints called**:
  - Catalog mount + chip change (F-1102, F-1103): `GET /api/kitchen/catalog`.
  - Variant picker (F-1115): `GET /api/kitchen/catalog?variants_of=<key>`.
  - Add to list (F-1114, F-1119, F-1148): `POST /shopping-list/items`.
  - Sheet qty / Bought / Skip / Open (F-1129..F-1131, F-1133, F-1134, F-1140..F-1142, F-1144, F-1146): `PUT /shopping-list/items/<id>` (quantity / status).
  - Sheet store picker (F-1138, F-1139): `PUT /shopping-list/items/<id>` preferred_store=<store|null>.
  - Low (F-1132, F-1143): `PATCH /products/<id>/low-status`.
  - Delete (F-1135, F-1145): `DELETE /shopping-list/items/<id>`.
  - Weather (F-1124): 3rd-party open-meteo (no LocalOCR endpoint).
- **Edge cases**:
  - Empty state — "List empty" (F-1125) when no shopping items; catalog still browsable.
  - Offline — catalog from Drift snapshot; sheet/list actions queued; weather widget hides or shows "—" when 3rd-party fetch fails.
  - Error (5xx) — per-tile snackbar + Retry; catalog fall-back to cache.
  - Loading — skeleton tiles in catalog row; sheet save spinner on action buttons.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — sheet PUT 409 → merged-toast + re-fetch.
- **`loaded N <thing>` log**: `loaded N catalog products` (catalog) and `loaded N kitchen items` (list) — two logs given the two distinct datasets.

---

### §6.13 Screen: Upload

- **Source registry rows**: F-1201..F-1224 (count: 24)
- **Route**: `/upload`
- **File path**: `lib/features/upload/presentation/upload_screen.dart`
- **Widgets to build**:
  - `_DropZoneCard` — covers F-1201..F-1203 (label opens picker; F-1202 registry note: Android uses pick / share-intent, not HTML drop; multi-file picker via `image_picker`/`file_picker`).
  - `_PreviewPanel` — covers F-1204 (preview image + meta).
  - `_BatchControls` — covers F-1205..F-1207 (Select All, count, Clear all).
  - `_BatchRow` — covers F-1208..F-1210 (per-file checkbox, remove, status).
  - `_ReceiptTypeButtons` — covers F-1211..F-1214 (Auto / Grocery / Restaurant / General Expense).
  - `_AiModelPicker` — covers F-1215..F-1217 (select, Browse toggle, model browser body).
  - `_UploadActions` — covers F-1218, F-1219, F-1223 (Auto Detect, Stop, Retry).
  - `_UploadStatusBlock` — covers F-1220..F-1222 (status text, scan progress, scan model chip).
  - `_ExtractedItemsCard` — covers F-1224.
- **State holders**:
  - `uploadStateProvider` (`AsyncNotifier<UploadState>`) — owns batch list, per-file status, current intent, selected model, upload-in-flight, status messages, scan progress.
  - `aiModelCatalogProvider` (`AsyncNotifier<List<AiModel>>`) — `/api/models` cache used by both select and browser.
  - `uploadRepositoryProvider` (`Provider<UploadRepository>`) — `/receipts/upload`, `/receipts/cancel-batch`.
- **Endpoints called**:
  - Model list (F-1215, F-1217): `GET /api/models`.
  - Upload (F-1218, F-1223): `POST /receipts/upload` (multipart, one per file or batched).
  - Cancel batch (F-1219): `POST /receipts/cancel-batch`.
- **Edge cases**:
  - Empty state — drop zone says "Pick files or share into the app".
  - Offline — Upload button disabled; banner "Offline — queue uploads when network returns"; batch retained in Drift so user can resume.
  - Error (5xx, OCR failure) — per-file status set to `error` with inline Retry; overall snackbar.
  - Loading — determinate progress bar driven by `scan-progress` event stream; AppBar shows in-flight count.
  - Auth (401) — AuthInterceptor → /login; uploads paused and resumed after re-auth.
  - Conflict (409) — duplicate-receipt detection returns 409; surface "Duplicate of receipt #N — open?" toast linking to existing receipt.
- **`loaded N <thing>` log**: `loaded N ai models` (when model list hydrates).

---

### §6.14 Screen: Receipts

- **Source registry rows**: F-1301..F-1401 (count: 101)
- **Route**: `/receipts`
- **File path**: `lib/features/receipts/presentation/receipts_screen.dart`
- **Widgets to build**:
  - `_ReceiptsFilterPanel` — covers F-1301..F-1316 (toggle, Review Refunds, Apply, Reset, Search input, attribution chips, untagged chip, store/source/type/transaction/status selects, purchased & uploaded date ranges).
  - `_ReceiptsByStoreCard` — covers F-1317, F-1318, F-1327, F-1328 (desktop + mobile variants — Flutter renders one adaptive `_ByStoreCard`).
  - `_SummaryCard` — covers F-1319..F-1325 (collapse, stats: total, refund count, refund total, items, unique, most-bought).
  - `_RefundReviewStrip` — covers F-1326.
  - `_PurchasesByMonthChart` — covers F-1329 (`CustomPaint` chart).
  - `_DedupCard` — covers F-1330..F-1334 (Scan, per-pair Merge, manual merge Keep/Drop/Merge).
  - `_RecentReceiptsControls` — covers F-1335, F-1336 (sort, refresh).
  - `_ReceiptListRow` — covers F-1337, F-1338 (tap select, long-press tooltip per registry).
  - `_ReceiptDetailPanel` — covers F-1339..F-1343 (rotate L/R, Mark Restaurant, Split toggle, Re-run OCR).
  - `_BillSummaryBlock` — covers F-1344..F-1348 (Provider, Counts Toward, Due Date, Frequency, Payment Status stats).
  - `_BillStatusControls` — covers F-1349..F-1353 (status select, Save, Paid on date, Mark Paid, Mark Unpaid).
  - `_ExtractedItemsTable` — covers F-1354..F-1359 (sort + per-row qty/price/name/category/delete).
  - `_ReceiptEditor` — covers F-1360..F-1386 (Receipt Type, Store, Date, Time, Tax, Transaction, Refund Reason, Budget Category, Subtotal, Tip, Total, Attribution picker trigger, Attribution household/per-person chips, Bill provider name + datalist, Provider Type, Service Types, Account Label, Billing Cycle Month, Frequency, Service Period Start/End, Due Date, Recurring, Auto-pay, Refund Note, Add Item, Save).
  - `_ReceiptDetailActions` — covers F-1387, F-1388 (Delete, Close).
  - `_SplitPanel` — covers F-1389..F-1396 (scenario buttons, amount input, contact select, payer checkbox, remove, add, Cancel, Save).
  - `_BulkTagToolbar` — covers F-1397, F-1398 (bulk attribution + select-all).
  - `_ReceiptItemSnapshotPicker` — covers F-1399.
  - `_ReceiptImageZoomViewer` — covers F-1400, F-1401 (image zoom; PDF viewer intent for F-1401 per registry).
- **State holders**:
  - `receiptsListProvider` (`AsyncNotifier<ReceiptsList>`) — owns filtered list, sort, pagination.
  - `receiptsFiltersProvider` (`Notifier<ReceiptsFilters>`) — owns all 16 filter fields.
  - `receiptDetailProvider` (`AsyncNotifier<ReceiptDetail?>`) — owns currently-open receipt + items.
  - `receiptEditorProvider` (`Notifier<ReceiptEditorDraft>`) — owns editor draft pre-save.
  - `splitPanelProvider` (`Notifier<SplitPanelState>`) — owns scenario + participants.
  - `dedupProvider` (`AsyncNotifier<DedupState>`) — owns scan results.
  - `bulkTagProvider` (`Notifier<Set<int>>`) — owns multi-receipt selection.
  - `summaryStatsProvider` (`AsyncNotifier<ReceiptSummary>`) — derived from list.
  - `receiptsRepositoryProvider` (`Provider<ReceiptsRepository>`) — `/receipts*`, `/shared-dining/*`, `/product-snapshots*`.
- **Endpoints called**, grouped by user action:
  - Filter Apply / sort / refresh (F-1303, F-1305..F-1316, F-1335, F-1336): `GET /receipts?q=&store=&source=&type=&transaction_type=&status=&purchase_from=&purchase_to=&upload_from=&upload_to=&attribution=&untagged_only=&refunds=`.
  - Review Refunds (F-1302, F-1326): `GET /receipts?refunds=1`, `GET /receipts/refunds?status=needs_review`.
  - Detail load (F-1337): `GET /receipts/<id>`.
  - Rotate (F-1339, F-1340): `POST /receipts/<id>/rotate?dir=left|right`.
  - Mark Restaurant (F-1341): `PATCH /receipts/<id>` receipt_type=restaurant.
  - Re-run OCR (F-1343): `POST /receipts/<id>/reprocess`.
  - Bill status (F-1349, F-1350, F-1352, F-1353): `PATCH /receipts/<id>` bill_payment_status=...; Paid on (F-1351): `PATCH /receipts/<id>` bill_payment_confirmed_at.
  - Item edit (F-1355..F-1358): `PATCH /receipts/<id>/items/<itemId>`; delete (F-1359): `DELETE /receipts/<id>/items/<itemId>`.
  - Editor field saves (F-1360..F-1384): `PATCH /receipts/<id>` (per field) — receipt_type, store, date, time, tax, transaction_type, refund_reason, default_budget_category, subtotal, tip, total, attribution, bill_provider_name, bill_provider_type, service_types, bill_account_label, bill_billing_cycle_month, bill_billing_cycle, bill_service_period_start, bill_service_period_end, bill_due_date, bill_is_recurring, bill_auto_pay, refund_note.
  - Add item row (F-1385): `POST /receipts/<id>/items`.
  - Save edited receipt (F-1386): `PUT /receipts/<id>` (or manual `POST /receipts` for new purchase).
  - Delete receipt (F-1387): `DELETE /receipts/<id>`.
  - Dedup scan (F-1330): `POST /receipts/dedup/scan`; Merge (F-1331..F-1334): `POST /receipts/dedup/merge`.
  - Bulk tag (F-1397): `PATCH /receipts/bulk` attribution.
  - Split panel — contacts (F-1391): `GET /shared-dining/contacts`; Save (F-1396): `POST /shared-dining/splits`.
  - Snapshot upload (F-1399): `POST /product-snapshots/upload`.
- **Edge cases**:
  - Empty state — "No receipts match — try resetting filters" with a Reset CTA.
  - Offline — cached list + cached detail from Drift; PATCH/POST/DELETE queued to outbox; Re-run OCR blocked with offline tooltip; PDF viewer falls back to cached file if present.
  - Error (5xx) — per-field PATCH snackbar + Retry; list refresh shows error tile with Retry.
  - Loading — list skeleton; detail spinner; field saves show inline "Saving…" pill.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — Save Receipt (F-1386) returns 409 on concurrent edit → merged-toast per F-368 pattern + re-fetch detail.
- **`loaded N <thing>` log**: `loaded N receipts`.

---

### §6.15 Screen: Budget

- **Source registry rows**: F-1501..F-1522 (count: 22)
- **Route**: `/budget`
- **File path**: `lib/features/budget/presentation/budget_screen.dart`
- **Widgets to build**:
  - `_BudgetEditorHeader` — covers F-1501, F-1502 (collapse + chip).
  - `_BudgetEditorActions` — covers F-1503, F-1504 (Manual Entry + Log Cash launchers).
  - `_BudgetEditorForm` — covers F-1505..F-1508 (month, category, amount, Save).
  - `_ThisMonthCard` — covers F-1509, F-1510 (total spent, refresh).
  - `_BudgetCategoryRow` — covers F-1511..F-1515 (name+spent, progress bar, pct/left/over, details expand, row tap).
  - `_OtherCategoriesGroup` — covers F-1516.
  - `_ContributingReceiptRow` — covers F-1517 (tap → receipt detail).
  - `_BudgetTargetsCard` — covers F-1518..F-1520 (header expand, target row, delete).
  - `_BudgetHistoryCard` — covers F-1521, F-1522 (history expand + rows).
- **State holders**:
  - `budgetStatusProvider` (`AsyncNotifier<BudgetStatus>`) — owns month + per-category rows + totals.
  - `budgetEditorProvider` (`Notifier<BudgetEditorDraft>`) — month, category, amount.
  - `budgetTargetsProvider` (`AsyncNotifier<List<BudgetTarget>>`) — targets list.
  - `budgetHistoryProvider` (`AsyncNotifier<List<BudgetHistoryEntry>>`) — change history.
  - `budgetRepositoryProvider` (`Provider<BudgetRepository>`) — `/budget*`.
- **Endpoints called**:
  - Editor month + summary mount (F-1505, F-1506, F-1510): `GET /budget/category-summary?month=<YYYY-MM>`.
  - Save budget (F-1507, F-1508): `POST /budget`.
  - Targets card (F-1518): `GET /budget/targets`; delete (F-1520): `DELETE /budget/<category>`.
  - History card (F-1521): `GET /budget/history`.
  - Contributing receipt tap (F-1517): `GET /receipts/<id>`.
  - Manual Entry / Log Cash (F-1503, F-1504): launch SharedModals — endpoints fire from there.
- **Edge cases**:
  - Empty state — "No budgets set — pick a category and amount to start".
  - Offline — cached summary + targets + history from Drift; Save queued to outbox.
  - Error (5xx) — snackbar + Retry on Save and per-card load.
  - Loading — skeleton rows in This Month + Targets cards.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — `POST /budget` returning 409 (concurrent budget change) → merged-toast + re-fetch summary.
- **`loaded N <thing>` log**: `loaded N budget categories`.

---

### §6.16 Screen: Bills

- **Source registry rows**: F-1601..F-1638 (count: 38)
- **Route**: `/bills`
- **File path**: `lib/features/bills/presentation/bills_screen.dart`
- **Widgets to build**:
  - `_FloorObligationsTable` — covers F-1601.
  - `_BillsPullToRefresh` — covers F-1602 (`RefreshIndicator`).
  - `_BillsStickyBar` — covers F-1603..F-1610 (month picker, tabs, +New Bill, Log Cash, CSV export, Print → share-as-PDF intent per registry note).
  - F-1611, F-1612 keyboard shortcuts — registry marks `🔄 hardware kb optional`; bind only if external keyboard detected.
  - `_BillsAlertsStrip` — covers F-1613..F-1615 (due soon / anomalies / missing).
  - `_BillsHero` — covers F-1616.
  - `_BillsSpotlight` — covers F-1617.
  - `_DueThisWeekStrip` — covers F-1618.
  - `_ObligationCard` — covers F-1619..F-1629 (title, status pill, expected, actual + variance, autopay line, Edit, Open Receipt, View Payments, Mark Paid, Mark Unpaid, Enter Bill).
  - `_ProviderCard` — covers F-1630..F-1633 (title tap, sparkline, totals).
  - `_MoMSection` — covers F-1634.
  - `_RecentBillRow` — covers F-1635, F-1636 (Open, View).
  - `_ShowAllExpander` — covers F-1637.
  - `_BillsEmptyState` — covers F-1638.
- **State holders**:
  - `billsStateProvider` (`AsyncNotifier<BillsState>`) — owns selected month, current tab (overview/providers/history), hero, spotlights, alerts, obligations, providers, recent.
  - `billsRepositoryProvider` (`Provider<BillsRepository>`) — `/bills*`, `/floor-obligations`, `/cash-transactions*`, `/receipts*`.
  - `floorObligationsProvider` (`AsyncNotifier<List<FloorObligation>>`).
- **Endpoints called**:
  - Floor obligations (F-1601): `GET /floor-obligations`.
  - Overview pull/refresh + month change (F-1602, F-1603): `GET /bills?month=`.
  - Providers tab (F-1605): `GET /bills/providers`.
  - History tab (F-1606): `GET /bills/history`.
  - CSV export (F-1609): `GET /bills/export.csv?month=` (downloaded via `Dio.download`, shared via share-sheet).
  - Provider detail (F-1619, F-1626, F-1630, F-1636): `GET /bills/providers/<name>`.
  - Edit service line (F-1624): `PUT /bills/service-lines/<id>`.
  - Open Receipt (F-1625, F-1635): `GET /receipts/<purchase_id>`.
  - Mark Paid (F-1627): `POST /cash-transactions`.
  - Mark Unpaid (F-1628): `DELETE /cash-transactions/<id>`.
  - Enter Bill / New Bill (F-1607, F-1629): manual entry modal → `POST /receipts` (manual).
  - Log Cash (F-1608): `POST /cash-transactions` (via SharedModals).
- **Edge cases**:
  - Empty state — `_BillsEmptyState` shows actionable CTA from `actionHtml` payload.
  - Offline — cached month view from Drift; CSV export blocked; Mark Paid / Mark Unpaid queued; provider detail falls back to cache.
  - Error (5xx) — per-card error tile + Retry; sticky-bar actions snackbar.
  - Loading — skeleton hero + obligation cards; tab-switch spinner.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — Edit service-line PUT returning 409 → merged-toast + re-fetch.
- **`loaded N <thing>` log**: `loaded N bill obligations`.

---

### §6.17 Screen: Accounts

- **Source registry rows**: F-1701..F-1750 (count: 50)
- **Route**: `/accounts`
- **File path**: `lib/features/accounts/presentation/accounts_screen.dart`
- **Widgets to build**:
  - `_CardUsageCard` — covers F-1701..F-1712 (header collapse, Refresh, summary strip, banner, donut + legend, pie filter select, pie collapse caret, Loan Progress panel, loan collapse caret, credit-card tile, card row, loan row).
  - `_ConnectedAccountsCard` — covers F-1713..F-1723 (header collapse, +Connect Bank, Refresh Balances, Reload, per-bank Re-auth / Sync / Rename / Share / Disconnect, sub-account balance, sync error inline).
  - `_ActivityByAccountCard` — covers F-1724..F-1729 (header collapse, row tap, purchases/autopay/interest/refunds counts).
  - `_SpendByPersonCard` — covers F-1730..F-1732 (collapse, prev/next month).
  - `_TransactionsCard` — covers F-1733..F-1745 (collapse, tabs, account filter, month picker, Refresh, Confirm All, per-row Confirm/Reject, Open in Receipts, amount + refund tint, pagination).
  - `_SpendingTrendsCard` — covers F-1746..F-1749 (collapse, window select, refresh, stacked bar chart `CustomPaint`).
  - `_ShareBankModal` — covers F-1750 (per-member checkbox inside confirm-overlay).
- **State holders**:
  - `cardUsageProvider` (`AsyncNotifier<CardUsageState>`) — owns card-usage payload + selected pie filter.
  - `connectedAccountsProvider` (`AsyncNotifier<List<PlaidItem>>`) — owns items + last sync error per item.
  - `activityBreakdownProvider` (`AsyncNotifier<TransactionBreakdown>`) — owns per-account counts.
  - `spendByPersonProvider` (`AsyncNotifier<SpendByPerson>`) — owns month + rows.
  - `accountsTransactionsProvider` (`AsyncNotifier<PlaidTransactions>`) — owns tab, account filter, month, offset, list.
  - `pendingReviewProvider` (`AsyncNotifier<List<StagedTransaction>>`) — owns staged transactions for Confirm/Reject.
  - `spendingTrendsProvider` (`AsyncNotifier<SpendingTrends>`) — owns window + chart data.
  - `accountsRepositoryProvider` (`Provider<AccountsRepository>`) — `/plaid/*`, `/analytics/spend-by-person`, `/receipts/<id>`.
- **Endpoints called**:
  - Card usage (F-1701): `GET /plaid/card-usage`.
  - Card usage refresh (F-1702): `POST /plaid/accounts/refresh-balances` then `GET /plaid/card-usage`.
  - Connect Bank (F-1714): `POST /plaid/link-token` then Plaid SDK.
  - Refresh Balances (F-1715): `POST /plaid/accounts/refresh-balances`.
  - Reload items (F-1716): `GET /plaid/items`.
  - Re-authenticate (F-1717): `POST /plaid/link-token?item_id=...`.
  - Sync now (F-1718): `POST /plaid/items/<id>/sync`.
  - Rename (F-1719): `PATCH /plaid/items/<id>` nickname.
  - Share (F-1720, F-1750): `PATCH /plaid/items/<id>` shared_with_user_ids.
  - Disconnect (F-1721): `DELETE /plaid/items/<id>`.
  - Activity breakdown (F-1724): `GET /plaid/transaction-breakdown`.
  - Spend by Person (F-1730..F-1732): `GET /analytics/spend-by-person?month=<YYYY-MM>`.
  - Transactions tab Spending (F-1734): `GET /plaid/transactions?kind=spending`; Transfers (F-1735): `GET /plaid/transactions?kind=transfers`.
  - Tx filter (F-1736): `GET /plaid/transactions?account_id=...`.
  - Tx month picker (F-1737): `GET /plaid/transactions?start=&end=`.
  - Tx refresh (F-1738): `GET /plaid/transactions`.
  - Confirm All (F-1739): `POST /plaid/staged/confirm-all`; per-row Confirm (F-1740): `POST /plaid/staged/<id>/confirm`; per-row Reject (F-1741): `POST /plaid/staged/<id>/reject`.
  - Open in Receipts (F-1742): `GET /receipts/<purchase_id>`.
  - Pagination (F-1744, F-1745): `GET /plaid/transactions?offset=...`.
  - Trends (F-1746..F-1748): `GET /plaid/transaction-trends?window=`.
- **Edge cases**:
  - Empty state — "No connected accounts — tap + Connect Bank to start"; Card Usage shows empty banner when no cards.
  - Offline — cached card usage / items / transactions from Drift; Connect Bank / Sync / Rename / Share / Disconnect blocked with offline tooltip; Confirm/Reject queued.
  - Error (5xx) — per-card error tile; per-bank `last_sync_error` rendered inline (F-1723).
  - Loading — skeleton tiles, donut placeholder, transactions list skeleton.
  - Auth (401) — AuthInterceptor → /login; Plaid Link returns its own error UX.
  - Conflict (409) — Rename / Share PATCH 409 → merged-toast + re-fetch item.
- **`loaded N <thing>` log**: `loaded N accounts` (Plaid items count).

---

### §6.18 Screen: Analytics

- **Source registry rows**: F-1801..F-1807 (count: 7)
- **Route**: `/analytics`
- **File path**: `lib/features/analytics/presentation/analytics_screen.dart`
- **Widgets to build**:
  - `_AnalyticsControls` — covers F-1801..F-1804 (period select, domain select, sort, Review Refunds).
  - `_RefundSummary` — covers F-1805.
  - `_SpendingOverviewList` — covers F-1806 (per-period row tap → drill).
  - `_DealsCapturedCard` — covers F-1807.
- **State holders**:
  - `analyticsProvider` (`AsyncNotifier<AnalyticsState>`) — owns period, domain, sort, spending rows, refunds summary, deals list.
  - `analyticsRepositoryProvider` (`Provider<AnalyticsRepository>`) — `/analytics/*`, `/receipts*`.
- **Endpoints called**:
  - Spending (F-1801, F-1802): `GET /analytics/spending?period=&domain=`.
  - Refund summary (F-1805): `GET /analytics/refunds`.
  - Review Refunds (F-1804): `GET /receipts?refunds=1`.
  - Period drill (F-1806): `GET /receipts?period=`.
  - Deals (F-1807): `GET /analytics/deals`.
- **Edge cases**:
  - Empty state — "Not enough data yet — upload more receipts" per card.
  - Offline — cached payload from Drift; banner shown.
  - Error (5xx) — per-card error tile + Retry.
  - Loading — skeleton rows.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded N analytics periods`.

---

### §6.19 Screen: Contributions

- **Source registry rows**: F-1901..F-1908 (count: 8)
- **Route**: `/contributions`
- **File path**: `lib/features/contributions/presentation/contributions_screen.dart`
- **Widgets to build**:
  - `_HowItWorksCard` — covers F-1901 (static 4-step explainer).
  - `_SummaryCards` — covers F-1902.
  - `_RecentActivityCard` — covers F-1903, F-1904 (refresh + per-entry row).
  - `_WaysToHelpCard` — covers F-1905, F-1906 (rows + per-row CTA navigation).
  - `_HowPointsCard` — covers F-1907.
  - `_FairScoringCard` — covers F-1908.
- **State holders**:
  - `contributionsProvider` (`AsyncNotifier<ContributionsState>`) — owns summary, recent, opportunities, rules, notes.
  - `contributionsRepositoryProvider` (`Provider<ContributionsRepository>`) — `/contributions/*`.
- **Endpoints called**:
  - Summary (F-1902): `GET /contributions/summary`.
  - Recent (F-1903): `GET /contributions/recent`.
  - Opportunities (F-1905): `GET /contributions/opportunities`.
  - Rules (F-1907): `GET /contributions/rules`.
  - Notes (F-1908): `GET /contributions/notes`.
  - CTA navigation (F-1906): varies — purely client-side routing to existing screens.
- **Edge cases**:
  - Empty state — "No score activity yet — start contributing to climb the leaderboard".
  - Offline — cached snapshot; banner.
  - Error (5xx) — per-card error tile + Retry.
  - Loading — skeleton cards.
  - Auth (401) — AuthInterceptor → /login.
  - Conflict (409) — not applicable.
- **`loaded N <thing>` log**: `loaded N contribution entries`.

---

### §6.20 Screen: Settings

- **Source registry rows**: F-2001..F-2117 (count: 117)
- **Route**: `/settings`
- **File path**: `lib/features/settings/presentation/settings_screen.dart`
- **Widgets to build**:
  - `_SessionSummaryCard` — covers F-2001..F-2014 (avatar preview, summary name, sub, Change avatar / Details toggles, Sign Out, avatar emoji input, Save Avatar, Cancel, Current login, Auth Source, Trusted Device, Current Host, Default Pairing Host).
  - `_MyActivityCard` — covers F-2015.
  - `_AppearanceCard` — covers F-2016, F-2017 (theme select, edge-pull overscroll toggle).
  - `_ManageStoresCard` — covers F-2018..F-2023 (filter pills All/Frequent/Rarely Used/Hidden, per-row bucket select, last-purchase display).
  - `_HouseholdUsersCard` — covers F-2024..F-2047 (Add User, Service Account, Sort, Refresh, invite form fields F-2028..F-2034, classic-user form F-2035..F-2040, pending invites F-2041..F-2043, users table rows F-2044..F-2047).
  - `_TrustedDevicesCard` — covers F-2048..F-2052 (Pair, Refresh, per-row Rename / Revoke / Delete).
  - `_SnapshotReviewCard` — covers F-2053..F-2055 (refresh, per-row Approve/Reject).
  - `_EnvironmentBackupCard` — covers F-2056..F-2063 (Create, Upload, Verify, Refresh, Restore Source select, Restore Selected, progress bar, report).
  - `_CatalogReviewCard` — covers F-2064..F-2068 (status filter, Run Gemini, Refresh, per-row Apply/Dismiss).
  - `_AiModelRegistryCard` — covers F-2069, F-2070, F-2092..F-2094 (+ New Model, Refresh, per-row Edit/Toggle/Delete).
  - `_AiModelEditor` — covers F-2071..F-2091 (full editor form + Save/Clear/Cancel).
  - `_AiUsageCard` — covers F-2095, F-2096 (days select + refresh).
  - `_ImageBackfillCard` — covers F-2097..F-2108 (provider select, Refresh candidates, Run, history window, history refresh, schedule Enabled, hour, minute, Save schedule, Next run, candidate row select checkbox, body table).
  - `_ChatAuditCard` — covers F-2109..F-2111 (limit select, refresh, per-row expand).
  - `_ApiTokenCard` — covers F-2112..F-2116 (token input, Save, show/hide, base URL input, Save Settings).
  - `_CollapsibleHost` — covers F-2117 (initial-collapsed default applied to every card).
- **State holders**:
  - `sessionProvider` (`AsyncNotifier<Session>`) — owns `/auth/me`, `/auth/me/stats`.
  - `themeProvider` (already on shell) — written by F-2016.
  - `overscrollNavSettingProvider` (already on shell) — written by F-2017.
  - `manageStoresProvider` (`AsyncNotifier<ManageStoresState>`) — owns filter + rows.
  - `householdUsersProvider` (`AsyncNotifier<UsersState>`) — owns users list, sort, pending invites.
  - `inviteFormProvider` (`Notifier<InviteFormState>`) and `classicUserFormProvider` (`Notifier<ClassicUserFormState>`).
  - `trustedDevicesProvider` (`AsyncNotifier<List<TrustedDevice>>`).
  - `snapshotReviewProvider` (`AsyncNotifier<List<SnapshotReviewItem>>`).
  - `environmentBackupProvider` (`AsyncNotifier<BackupState>`) — owns backups list + restore progress + report.
  - `catalogReviewProvider` (`AsyncNotifier<CatalogReviewState>`).
  - `adminAiModelsProvider` (`AsyncNotifier<List<AiModel>>`) and `aiModelEditorProvider` (`Notifier<AiModelDraft>`).
  - `aiUsageProvider` (`AsyncNotifier<AiUsage>`).
  - `imageBackfillProvider` (`AsyncNotifier<ImageBackfillState>`) and `imageBackfillScheduleProvider` (`Notifier<BackfillSchedule>`).
  - `chatAuditProvider` (`AsyncNotifier<ChatAudit>`).
  - `apiTokenProvider` (`Notifier<ApiTokenSettings>`).
  - `settingsRepositoryProvider` (`Provider<SettingsRepository>`) — wraps the broad surface (`/auth/*`, `/api/stores*`, `/auth/users*`, `/auth/invites*`, `/auth/service-accounts*`, `/auth/trusted-devices*`, `/product-snapshots/review-queue*`, `/system/*`, `/products/review-queue*`, `/products/enhance-batch`, `/api/admin/models*`, `/image-backfill/*`, `/chat/audit`).
- **Endpoints called** (grouped):
  - Session: `GET /auth/me` (F-2002, F-2011, F-2012), `GET /auth/me/stats` (F-2015), `POST /auth/logout` (F-2006), `PUT /auth/users/<id>` avatar (F-2007, F-2008).
  - Manage Stores: `GET /api/stores?filter=...` (F-2018..F-2021), `PATCH /api/stores/<id>` bucket (F-2022).
  - Household Users: `POST /auth/service-accounts` (F-2025), `GET /auth/users` (F-2027), `POST /auth/users` (F-2035..F-2040), `PUT /auth/users/<id>` (F-2045), `DELETE /auth/users/<id>` (F-2046), `POST /auth/service-accounts/<id>/rotate` (F-2047), `POST /auth/invites` (F-2028..F-2031), `GET /auth/invites` (F-2041), `DELETE /auth/invites/<id>` (F-2042).
  - Trusted Devices: `POST /auth/device-pairing/start` (F-2048), `GET /auth/trusted-devices` (F-2049), `PUT /auth/trusted-devices/<id>` (F-2050), `POST /auth/trusted-devices/<id>/revoke` (F-2051), `DELETE /auth/trusted-devices/<id>` (F-2052).
  - Snapshot Review: `GET /product-snapshots/review-queue` (F-2053), `POST /product-snapshots/<id>/approve` (F-2054), `POST /product-snapshots/<id>/reject` (F-2055).
  - Environment Backup: `POST /system/backups` (F-2056), `POST /system/backups/upload` (F-2057), `POST /system/verify` (F-2058), `GET /system/backups` (F-2059), `POST /system/restore` (F-2061).
  - Catalog Review: `GET /products/review-queue?status=` (F-2064, F-2066), `POST /products/enhance-batch` (F-2065), `POST /products/review-queue/<id>/apply` (F-2067), `POST /products/review-queue/<id>/dismiss` (F-2068).
  - AI Models: `GET /api/admin/models` (F-2070), `POST /api/admin/models` (F-2089 new), `PUT /api/admin/models/<id>` (F-2089/F-2092 edit), `PATCH /api/admin/models/<id>` enabled (F-2093), `PATCH /api/admin/models/<id>` clear_key (F-2088), `DELETE /api/admin/models/<id>` (F-2094).
  - AI Usage: `GET /api/admin/models/usage?days=` (F-2095, F-2096).
  - Image Backfill: `GET /image-backfill/candidates` (F-2098), `POST /image-backfill/run` (F-2099), `GET /image-backfill/history?days=` (F-2100, F-2101), `PUT /image-backfill/schedule` (F-2102..F-2105).
  - Chat Audit: `GET /chat/audit?limit=` (F-2109, F-2110).
  - API Token Save: `PUT /auth/me/token` (F-2113).
- **Edge cases**:
  - Empty state — each card renders its own empty placeholder ("No invites pending", "No trusted devices yet", "No backups yet", etc.).
  - Offline — read-only cards render from Drift cache with banner; all admin mutations (POST/PUT/PATCH/DELETE) blocked with "Offline — settings changes require network" tooltip rather than queued (avoids stale admin actions per the registry's privileged nature).
  - Error (5xx) — per-card error tile + Retry; mutation snackbar with Retry.
  - Loading — skeleton cards; editor Save button shows spinner.
  - Auth (401) — AuthInterceptor → /login; if the user is downgraded mid-session, admin-only cards render "Admin required" placeholder.
  - Conflict (409) — User PUT / AI Model PUT / Manage Stores PATCH 409 → merged-toast + re-fetch row.
- **`loaded N <thing>` log**: `loaded N settings cards` (aggregate across the page) plus per-subsystem logs as cards mount (`loaded N users`, `loaded N trusted devices`, `loaded N ai models`, `loaded N backups`, `loaded N catalog review items`).

---

### §6.21 Screen: SharedModals

- **Source registry rows**: F-2201..F-2253 (count: 53)
- **Route**: not a route — modal sheets and dialogs invoked from other screens via `showModalBottomSheet` / `showDialog` / `Navigator.push` with `fullscreenDialog: true`
- **File path**: `lib/features/shared/`
  - `lib/features/shared/widgets/confirm_dialog.dart`
  - `lib/features/shared/widgets/manual_entry_sheet.dart`
  - `lib/features/shared/widgets/cash_transaction_sheet.dart`
  - `lib/features/shared/widgets/device_pairing_modal.dart`
  - `lib/features/shared/widgets/image_zoom_viewer.dart`
  - `lib/features/shared/widgets/attribution_picker.dart`
  - `lib/features/shared/widgets/refund_receipts_overlay.dart`
  - `lib/features/shared/widgets/bill_edit_modal.dart`
  - `lib/features/shared/widgets/variant_picker_sheet.dart`
  - `lib/features/shared/widgets/action_toast.dart`
- **Widgets to build**:
  - `ConfirmDialog` — covers F-2201..F-2204 (OK, Cancel, backdrop tap close, Esc → native back gesture per registry).
  - `ManualEntrySheet` — covers F-2205..F-2231 (Receipt Type, Transaction, Store, Date, Subtotal, Tax, Total, Tip, Refund Reason, Refund Note, Bill Provider Name, Bill Provider Type, Service Types, Account Label, Billing Cycle Month, Billing Cycle, Service Period Start/End, Due Date, Recurring, items Add row / name / qty / price / delete, Cancel, Save).
  - `CashTransactionSheet` — covers F-2232..F-2238 (provider, amount, date, payment method, service type, provider picker filter, Save).
  - `DevicePairingModal` — covers F-2239..F-2241 (QR, copy link, regenerate).
  - `ImageZoomViewer` — covers F-2242, F-2243 (backdrop tap close, pinch zoom).
  - `AttributionPicker` — covers F-2244..F-2246 (household chip, per-person checkbox, Apply).
  - `RefundReceiptsOverlay` — covers F-2247, F-2248 (list + close).
  - `BillEditModal` — covers F-2249, F-2250 (provider/type/cycle/amount/Save).
  - `VariantPickerSheet` — covers F-2251, F-2252 (variant tile tap → add, close).
  - `ActionToast` — covers F-2253 (Undo button on action toasts).
- **State holders**:
  - `confirmDialogControllerProvider` (`Notifier<ConfirmDialogQueue>`) — owns dialog request queue.
  - `manualEntryProvider` (`Notifier<ManualEntryDraft>`) — owns full receipt draft (type, store, dates, items, bill fields).
  - `cashTransactionProvider` (`Notifier<CashTxDraft>`) — owns cash-transaction draft.
  - `devicePairingProvider` (`AsyncNotifier<DevicePairing>`) — owns QR + token + polling state.
  - `attributionPickerProvider` (`Notifier<AttributionDraft>`) — owns household + per-person multi-select.
  - `actionToastProvider` (`Notifier<ActionToastQueue>`) — owns toast queue + undo callback.
  - Each sheet uses the parent feature's repository (no new repositories introduced here).
- **Endpoints called**, grouped by user action:
  - Manual entry Save (F-2231): `POST /receipts` (manual).
  - Manual entry field saves (F-2205..F-2230) are draft-only client-side — no per-field network call; the Save button submits the full payload.
  - Cash transaction Save (F-2238): `POST /cash-transactions`.
  - Device pairing QR (F-2239): `GET /auth/qr-image`; regenerate (F-2241): `POST /auth/device-pairing/start`.
  - Attribution Apply (F-2244..F-2246): `PATCH /receipts/<id>` attribution.
  - Refund Receipts overlay list (F-2247): `GET /receipts?refunds=1`.
  - Bill Edit Save (F-2249, F-2250): `PUT /bills/service-lines/<id>`.
  - Variant picker tap (F-2251): `POST /shopping-list/items`.
  - Toast Undo (F-2253): "varies" per registry — replays the inverse of the original mutation (e.g., `PATCH /inventory/products/<id>` snapshot restore).
- **Edge cases**:
  - Empty state — Manual Entry opens with empty draft + first item row pre-inserted; Cash Transaction opens with today's date pre-filled.
  - Offline — Confirm dialog and zoom viewer fully usable offline; Manual Entry and Cash Transaction Save queue to outbox; Device Pairing QR blocked with offline tooltip; Bill Edit Save queued; Variant picker Add queued.
  - Error (5xx) — sheet remains open; inline error pill + Retry on Save.
  - Loading — Save button spinner; QR pulse-shimmer while regenerating.
  - Auth (401) — AuthInterceptor → /login (sheet auto-dismissed and draft preserved in provider for resume).
  - Conflict (409) — Bill Edit / Manual Entry Save returning 409 (duplicate receipt) → merged-toast and dismiss sheet (per F-368 carry-over).
- **`loaded N <thing>` log**: `loaded N refund receipts` (when Refund Receipts overlay opens) and `loaded N attribution targets` (when Attribution Picker opens) — modal-specific logs per RULE 6.

---

### §6.22 Screen: DesignGallery

- **Source registry rows**: F-2401..F-2403 (count: 3)
- **Route**: not exposed in production builds — registry marks all three rows as `🚫 Dev-only design gallery; explicitly out of scope for Android`
- **File path**: not built (entries omitted from `lib/features/`)
- **Widgets to build**: none — registry-explicit out-of-scope.
- **State holders**: none.
- **Endpoints called**: none.
- **Edge cases**: not applicable — the screen is intentionally excluded; the long-press secret triggers (F-023, F-024) and `g g` keyboard sequence (F-030) that would reveal it on web have no Android counterpart, so the gallery is simply unreachable.
- **`loaded N <thing>` log**: not applicable.


---

## §7 Risks & vetoes (Agent 7)

### §7.1 Confidence scores
| Agent | Section | Confidence (0-100) | Why |
|-------|---------|--------------------:|------|
| 1 | Tech stack | 92 | Flutter 3.24 + Riverpod + Drift + dio is the forced default for a greenfield Android port with cookie-based Flask auth and a future iOS arm; only wiggle is Riverpod-vs-bloc which §1 explicitly leaves to user preference. |
| 2 | Architecture | 88 | Feature-folder + repository-per-feature is the established pattern that mirrors the macOS layering; minor wiggle on whether `shared/` should split into `widgets/` vs `modals/`, but the call doesn't change anything outside that folder. |
| 3 | Routing | 84 | Drawer + go_router table is sound; hash → path translation grepped from index.html. V-3/V-11 (restaurant flag key path) PATCHED inline at assembly time. One remaining gate: URL-fragment intent handling needs an emulator confirmation before relying on go_router `redirect` to strip `#`. |
| 4 | Networking + endpoints | 90 | Endpoint inventory was grepped from `src/backend/` (216 routes across 26 blueprints + 8 app-level = 224 confirmed); auth/cookie/retry policy is correct. Loss of 10 points for the unresolved cookie SameSite/Domain question (V-1) and OAuth custom-scheme allowlist (V-2). |
| 5 | Build/CI | 86 | Pre-flight, gradle config, signing, ProGuard, post-build validation, CI YAML are all concrete and grounded. V-10 (minSdk contradiction) PATCHED inline at assembly time (§1 now matches §5 = 26). Remaining loss: (a) keystore not yet generated (G-1), (b) CI deliberately skips release-build signing — explicit gap but still a gap. |
| 6 | Per-screen | 84 | 22 screens covered, log lines enumerated. V-9 (fabricated `/budget/dining` + `/budget?category=...`) PATCHED inline at assembly time — §6.7 Restaurant and §6.10 Expenses now cite the real `/budget/status?month=&domain=` + `/budget/set-monthly` endpoints with `manage_household_budget.py` line refs and `loadRestaurantBudget()` / `loadExpenseBudget()` web call-site refs (RULE 4 satisfied). Minor remaining wiggle: per-screen Drift schemas still need a one-pass review before commit-1 (covered by G-7). |

Rubric applied: 90+ = forced by evidence (Flutter default, Bundle ID given), 75-89 = well-supported but reasonable alternatives exist, 60-74 = tractable open gates, <60 = serious unknown (none triggered here). V-9, V-10, V-3/V-11 patched at assembly time; resolutions documented inline in §6.7, §6.10, §1, §3.

### §7.2 Open vetoes (BLOCKING — build cannot start until each is resolved)

- **V-1: Backend cookie `SameSite` / `Domain` scope unknown on Android dio/WebView path.** §4 assumes Flask's default `session` cookie attaches cleanly via `PersistCookieJar` + `dio_cookie_manager`, but the live `Set-Cookie` header from prod has never been inspected. If the cookie ships with `SameSite=Strict` or a `Domain` more restrictive than `extended.npalakurla.com`, the Google-OAuth custom-scheme redirect (V-2) will drop it and the user will be logged out after every OAuth round-trip. Closure: `curl -sv -X POST https://extended.npalakurla.com/auth/login -H 'Content-Type: application/json' -d '{"email":"<test>","password":"<test>"}' 2>&1 | grep -i set-cookie` — paste raw header into `VETO_RESOLUTION_PATCH.md`, decide CookieManager config (`PersistCookieJar` `ignoreExpires`, `Cookie.domain` rewrite if needed), document in §4.

- **V-2: Google OAuth redirect URI `localocr://oauth/callback` not yet allowlisted at Google Cloud Console.** §4 assumes the Flask `/auth/oauth/google/callback` (manage_authentication.py:2347) can be invoked with a non-https `redirect_uri`, but Google's OAuth client only allows registered URIs. Without this, F-105 (Sign in with Google) returns `redirect_uri_mismatch` on first launch. Closure: add `localocr://oauth/callback` to the Google Cloud OAuth 2.0 client allowlist; update `/auth/oauth/google` to accept and forward a `redirect_uri` query param, OR add a server-side detector that emits `Location: localocr://oauth/callback?...` for android-UA requests. Record decision in `docs/oauth-android.md`.

- **V-3: Restaurant feature-flag key path in `/auth/app-config` is `modules.restaurant`, NOT top-level `restaurant_enabled`.** [RESOLVED AT ASSEMBLY] §3 patched inline: redirect now reads `appConfig.modules.restaurant != true`; DTO contract embedded in §3. Remaining gate G-6 still tracks the fixture file + unit test artifact.

- **V-4: Keystore not yet generated; release `signingConfigs.release` block in §5 build.gradle.kts cannot resolve.** Until `android/keystore/localocr-release.jks` exists and `android/key.properties` is populated, every release build will fail at the `signingConfig = signingConfigs.getByName("release")` line. Closure: run the keytool command from §5 (line 84), copy outputs to 1Password vault `LocalOCR Android Release Keystore` + encrypted backup bundle, commit `android/key.properties.example` (real `key.properties` git-ignored), verify with `flutter build apk --flavor prod --release` exit-zero.

- **V-5: Bundle ID `com.localocr.extended.localocr.extended` repeats `localocr.extended` — confirm intent.** §2 and §5 both bake this id in three flavor suffixes (`.dev`, `.staging`, `<base>`). It is grammatically unusual and reads like a copy-paste accident vs the cleaner `com.localocr.extended` or `com.npalakurla.localocr.extended`. Once the prod APK is published to the Play Store under this id, it can NEVER be changed without re-onboarding all users. Closure: explicit user confirmation in `VETO_RESOLUTION_PATCH.md` BEFORE the first prod build; if changed, update §2 ApplicationId block, §5 build.gradle.kts, §3 deep-link host strings, and AndroidManifest intent filters in lockstep.

- **V-6: 216 backend endpoints × 22 screens — per-screen Dart `remote_source` generation must be tracked and counted.** §6 enumerates the endpoints per screen but does NOT produce an aggregate manifest the orchestrator can count against §4. Without this, a screen can silently skip an endpoint (e.g. `/products/<id>/low-status` for F-431) and the only signal will be a missing button at runtime. Closure: §5's pre-commit hook + a `scripts/check-endpoint-coverage.sh` that greps every `Method | Path` from §4 against `grep -rE "dio.get\|dio.post\|dio.put\|dio.delete\|dio.patch" lib/features/` — coverage report must reach 100% before commit-1 of any release build.

- **V-7: Dart `json_serializable` has NO `convertFromSnakeCase` equivalent — every freezed field needs explicit `@JsonKey(name:'snake_case')` (inverted RULE 18).** §1 calls this out; §5's pre-commit hook step 3 currently FLAGS snake_case `@JsonKey` as suspicious (wrong direction — the macOS rule was the opposite). Failure mode: silent `null` fields, exact reproduction of I-17. Closure: invert §5 pre-commit step 3 — instead of failing on `@JsonKey(name: 'snake_case')`, fail on freezed response classes in `lib/features/*/data/` whose fields lack ANY `@JsonKey` annotation. Concrete grep: `grep -rnE 'class .*\$.*With.*\{' lib/features/*/data/*.freezed.dart` cross-referenced with the source `.dart` file's `@JsonKey` count = field count.

- **V-8: Web `mobile-brand-secret-trigger` long-press (F-023/F-024) reveals dev-only Design Gallery — same family as F-030 which is pre-marked 🚫.** Registry currently leaves F-023/F-024 as ❌ with no scope decision. If we port them and they fire in a production Android build, they expose dev tooling to end users. Closure: explicit user decision in `VETO_RESOLUTION_PATCH.md` — either (a) port as a hidden-from-prod debug shortcut keyed on `kDebugMode || flavor != 'prod'`, or (b) mark F-023/F-024 as 🚫 in the registry alongside F-030. Default recommendation: 🚫 in prod, optional debug-only in dev flavor.

- **V-9: `/budget/dining` (§6.7) + `/budget?category=general_expense&month=` (§6.10) were FABRICATED endpoints.** [RESOLVED AT ASSEMBLY] §6.7 Restaurant + §6.10 Expenses both patched inline at /tmp/android_plan_sec6.md lines 280-281 and 375-376 — both screens now cite `GET /budget/status?month=&domain=restaurant|general_expense` (web `loadRestaurantBudget()` index.html:35591; `loadExpenseBudget()` index.html:36826) and `POST /budget/set-monthly` (web index.html:35643, 36878; blueprint `manage_household_budget.py:160`). All endpoints now appear in §4's `budget` blueprint table. G-13 (re-audit script) closes the residual.

- **V-10: §1/§5 minSdk contradiction (24 vs 26).** [RESOLVED AT ASSEMBLY] §1 line 3 patched inline to `minSdk = 26` to match §5. `flutter_secure_storage` 9.x + `mobile_scanner` constraints satisfied. ~94% device coverage retained.

- **V-11: §3 `restaurant_enabled` vs real `app_config.modules.restaurant`.** [RESOLVED AT ASSEMBLY] §3 hash→route table row F-010 and redirect block patched inline; DTO contract `AppConfig.modules.{grocery,restaurant,generalExpense}` documented in §3.

### §7.3 Assumptions that need verification

- **Staging URL `https://staging.npalakurla.com` exists.** Verify: `curl -o /dev/null -w "%{http_code}\n" https://staging.npalakurla.com/auth/me`. Expect 200/401. If `000`/`404`/cert-error → delete staging flavor from §2/§5 OR set up the host before commit-1 (see G-10).
- **Flask session cookie default lifetime is 31 days** (claimed in §4 line 47). Verify: `grep -nE 'PERMANENT_SESSION|REMEMBER_COOKIE_DURATION|session.*lifetime' src/backend/*.py config/*.py`. Adjust §4's auto-logout cadence if different.
- **`/auth/app-config` returns `{modules: {restaurant: bool, ...}, ...}`.** Verify: `curl -b cookies.txt https://extended.npalakurla.com/auth/app-config` against a logged-in session. Pin the exact JSON to a fixture file in `test/fixtures/app_config.json` so future schema drift fails a unit test.
- **`mobile_scanner` 5.x supports barcode formats for F-531/F-532 (medication lookup).** Web uses `Html5Qrcode` which defaults to QR + 1D barcodes (CODE_128, EAN_13, UPC_A). Verify: `grep -nE 'formats|allowedFormats|barcode' src/backend/manage_medications.py` and confirm `mobile_scanner` `BarcodeFormat` enum includes the same set; if `DataMatrix` / `PDF417` is used, add to the scanner config.
- **Drift will handle 22 features × paginated lists without exceeding a ~100 MB SQLite file in normal household use.** Hypothesis only; verify by running a one-month load test against staging and checking `du -sh ~/.local/share/com.localocr.extended.localocr.extended/databases/`. If file grows past 200 MB, add periodic `VACUUM` cron in §6 settings screen.
- **English-only v1** (no i18n). No verification needed; just record explicitly so a future contributor doesn't assume `intl` ARB extraction is wired up.
- **Physical-device camera tests run locally by the build agent.** CI explicitly skips them (§5 line 220). Verify before every release tag: `flutter test integration_test/camera_test.dart` on a physical Android 11+ device.
- **16+ unique `loaded N <thing>` log strings — each enumerated in §6.** Verify: `grep -rnE 'logger\.i\("loaded' lib/features/ | wc -l` matches the count §6 declares (re-derive from §6 before commit-1).
- **F-019 `/features` external page renders correctly inside `webview_flutter`.** Web opens it in a new tab; Android plan §3 uses an embedded WebView with `url_launcher` fallback. Verify by loading `https://extended.npalakurla.com/features` in the WebView and confirming no `X-Frame-Options: DENY` header blocks it (`curl -sI https://extended.npalakurla.com/features | grep -i x-frame`).
- **F-039 Chat resize handle adapted to bottom-sheet on Android (§3, registered as 🔄).** Verify the bottom-sheet height is comfortable enough to not need a drag handle; if QA reports the sheet covers too much content, escalate to a draggable `DraggableScrollableSheet` (already a Flutter primitive).
- **`POST_NOTIFICATIONS` runtime prompt UX on Android 13+ doesn't degrade onboarding.** Verify on a real Pixel 7 (API 33+): first launch should defer the prompt until the user actually opts into a notifying surface (budget alert, expiry nudge), not on app start (matches the existing macOS `UNError` pattern).

### §7.4 Gates list (must close before build phase 1 commit)

| Gate ID | Action | Owner | Closes when |
|---------|--------|-------|-------------|
| G-1 | (V-4 RESOLVED) Keystore generation gated on FIRST RELEASE BUILD only — debug + profile flavor builds work without it, and the orchestrator build stage produces debug APKs. Build phase 1 task: copy `scripts/android-key.properties.example` to `android/key.properties.example` once `android/` is scaffolded by `flutter create`; add `android/key.properties` and `android/keystore/*.jks` to `.gitignore`. Keystore-gen via keytool (§5 line 84) deferred to BL-A3 (Promote release signing to CI) OR the first manual `--release` build, whichever comes first. v1 dev builds installable via `flutter install --debug` without any keystore artifact. | builder agent (manual) | `android/key.properties.example` exists post-scaffold; `.gitignore` blocks real key.properties + jks; `flutter build apk --flavor dev --debug` exits zero |
| G-2 | Verify Set-Cookie scope: run V-1 curl, paste raw `Set-Cookie` header into `VETO_RESOLUTION_PATCH.md`, decide `PersistCookieJar` config (whether `ignoreExpires=true`, whether to rewrite Domain) | builder agent | `VETO_RESOLUTION_PATCH.md` contains the header + the chosen jar config + a one-line justification |
| G-3 | Confirm Bundle ID with user: `com.localocr.extended.localocr.extended` vs `com.localocr.extended` vs `com.npalakurla.localocr.extended` — append confirmation to `VETO_RESOLUTION_PATCH.md`. If changed, lockstep update §2 / §5 build.gradle / §3 deep-link host strings / AndroidManifest intent filters | user | User-confirmed line in patch file; grep across §2/§3/§5 + AndroidManifest shows zero references to the rejected id |
| G-4 | Install pre-commit hook `scripts/pre-commit-android.sh` (§5 lines 226-256) AFTER patching V-7 inversion (fail on missing `@JsonKey`, not on present snake_case) | builder agent | Hook executable; `git config core.hooksPath` points at `scripts/`; trial commit on a deliberately broken `@freezed` class fails the hook |
| G-5 | (V-2 RESOLVED via WebView strategy — no Google Cloud Console change needed) Build phase 1 task: implement `lib/core/auth/oauth_google.dart` per §5 line 843 (in-app `flutter_inappwebview` + `CookieManager.getCookies` → dio `PersistCookieJar.saveFromResponse`). Round-trip on dev emulator with a real Google account; confirm session cookie reaches the dio jar and `/auth/me` returns 200 post-OAuth. | builder agent | OAuth flow round-trip on dev emulator returns to app with session cookie attached to dio jar |
| G-6 | Patch §3 + §1 to use `appConfig.modules.restaurant` (V-3 + V-11); add `test/fixtures/app_config.json` with verified live shape; add unit test that the DTO decodes the fixture without error | builder agent | Grep finds zero `restaurant_enabled` references; unit test passes |
| G-7 | Generate per-feature `lib/features/<x>/data/<x>_remote_source.dart` skeletons enumerating every endpoint from §4 — one Dart fn per row — BEFORE screen code begins. Each fn body starts as `throw UnimplementedError('endpoint <method> <path> from §4 line N');` (no placeholder comments — UnimplementedError surfaces at runtime if any function ships unfilled) | builder agent | All 22 remote_source.dart files exist; `scripts/check-endpoint-coverage.sh` reports ≥ count from §4 |
| G-8 | Decide explicitly: port F-023/F-024 mobile-brand-secret long-press? Yes/no recorded in `VETO_RESOLUTION_PATCH.md`. Default recommendation: 🚫 in prod, optional debug-only in dev flavor | user | Recorded in patch file; registry F-023/F-024 status updated to ✅ (with debug-only impl note) or 🚫 (with justification) |
| G-9 | Run `flutter doctor -v` on the build machine; capture output to `docs/flutter-doctor.txt`; resolve any `[✗]` before commit-1 | builder agent | File committed; zero `[✗]` lines |
| G-10 | Verify staging URL: `curl -o /dev/null -w "%{http_code}\n" https://staging.npalakurla.com/auth/me`. If reachable (200/401) → keep §5 staging flavor; if not → delete staging flavor from §2 + §5 + CI workflow, drop to two flavors (dev + prod) | builder agent | Either curl returns 200/401 AND staging entry stays, OR §2/§5 patched to drop staging flavor + matching commit message |
| G-11 | Re-grep §6 for any endpoint path not in §4 (RULE 1 audit). Concrete: `scripts/audit_sec6_endpoints.sh ANDROID_APP_PLAN.md` — extract every `GET\|POST\|PUT\|DELETE\|PATCH /…` from §6 and confirm each appears in §4's appendix list | builder agent | Script exits zero; report committed to `docs/endpoint-audit.txt` |

### §7.5 Self-flagged future work (RULE 19 — must have owner and tracked backlog item)

From §1-§6 review, the following "defer / later / v1.1" notes were found. Each is converted to a tracked backlog item here so no orphan placeholder survives round-close (RULE 19).

- **§1 line 16 — `flutter_flavorizr` "full flavor matrix and signing config deferred to §5".** Closed: §5 documents both. No outstanding work; phrase will be removed from §1 at commit-1.
- **§3 line 61 — `Shortcuts/Actions` Bluetooth-keyboard binding for `Alt+←`/`→` "defer to §10 polish".** §10 does not exist in this plan. OWNER: builder agent. ACTION: open backlog item `BL-A1: Alt-Arrow keyboard nav for Bluetooth keyboards` in `docs/android-backlog.md` at commit-1. v1 ships without it (acceptable — `🔄` registry status).
- **§3 line 63 — F-028 edge-pull overscroll nav "Decision deferred to §6 (Dashboard row)".** §6.3 Dashboard does not decide — silent drop. OWNER: builder agent. ACTION: choose `OverscrollNotification` listener vs edge-swipe `GestureDetector` in the Dashboard screen plan section before commit-1 of the Dashboard implementation; record the decision inline in §6.3.
- **§5 line 49 — Firebase ProGuard rules "deferred until Firebase is introduced".** Acceptable — no Firebase planned for v1. No tracked item needed; the conditional ("if added later") satisfies RULE 19.
- **§5 line 63 — `RECEIVE_BOOT_COMPLETED` + WorkManager "deferred to v1.1".** OWNER: builder agent. ACTION: open backlog item `BL-A2: Boot-receiver + WorkManager for expiry nudges` in `docs/android-backlog.md` at commit-1. v1 ships with foreground notifications only.
- **§5 line 219 — "No release builds in CI for v1; signing keys not committed to CI secrets yet".** OWNER: builder agent. ACTION: open backlog item `BL-A3: Promote release signing to CI` in `docs/android-backlog.md` at commit-1. v1 ships with manual release builds from the dev machine.
- **§5 line 220 — "No emulator-based integration tests in CI for v1".** OWNER: builder agent (local matrix from §5). ACTION: open backlog item `BL-A4: Promote camera + notification integration tests to CI` in `docs/android-backlog.md` once a self-hosted runner with KVM is available. v1 covered by local physical-device run.
- **§6 line 19 — `ActionToastOverlay` "deferred details in SharedModals" (F-025).** §6.21 SharedModals must enumerate the toast surface concretely (timer, undo button, max-stack policy). OWNER: builder agent. ACTION: verify §6.21 covers F-025 details before commit-1; if not, file `BL-A5: ActionToast surface complete spec` against §6.21.

---

### Audit pass (§1-§6 scan)

- **Literal placeholder strings**: zero in §1-§6 final output (post-patch grep clean).
- **Vague pending phrases**: zero hits across §1-§6 (RULE 19 satisfied).
- **`deferred` / `defer to` / `later` / `v1.1`**: 7 hits enumerated above — all converted to tracked backlog items (BL-A1 through BL-A5) or closed (§1 line 16, §5 line 49).
- **Endpoint paths in §6 missing from §4**: TWO violations were found — `/budget/dining` (§6.7) and `/budget?category=...` (§6.10). Both PATCHED inline at assembly time. Residual G-11 enforces script-based re-audit before commit-1.
- **Registry screen coverage**: registry has 22 `## Screen: ` headings (AppShell, Login, Dashboard, Inventory, Products, Medicine, Restaurant, Balances, Contacts (Dining), Expenses, Shopping, Kitchen, Upload, Receipts, Budget, Bills, Accounts, Analytics, Contributions, Settings, SharedModals, DesignGallery). §6 has 22 `### §6.x Screen: ` headings covering exactly the same set (DesignGallery → §6.22; pre-marked 🚫 dev-only per F-030). **PASS** — 22/22 screen coverage.
- **Bundle ID consistency**: §2 line 71-72 says `com.localocr.extended.localocr.extended.dev` / `.staging` / `<base>`; §5 line 29 + 34-36 echoes the same. Internally consistent (modulo V-5 which questions the base id itself).
- **§1 vs §5 minSdk**: contradiction was found (§1=24, §5=26); PATCHED inline at assembly (both = 26). V-10 closed.
- **`restaurant_enabled` flag key**: §3 used `restaurant_enabled`; backend grep proved real key is `appConfig.modules.restaurant`. PATCHED inline at assembly. V-3/V-11 marked RESOLVED; G-6 still tracks fixture + unit test deliverable.

---

### §7.6 Status summary (post-assembly patch pass)
- Total vetoes raised: 11 (V-1 … V-11)
- Vetoes RESOLVED inline at assembly: 4 (V-3, V-9, V-10, V-11)
- Vetoes OPEN (must close before build commit-1): 7 (V-1, V-2, V-4, V-5, V-6, V-7, V-8)
- Total gates: 11 (G-1 … G-11; G-12 + G-13 collapsed since their referenced vetoes are already patched)
- Confidence floor (post-patch): min(92, 88, 84, 90, 86, 84) = **84** (§3 + §6 tied)


---

## §8 Plan metadata
- agent-count: 7
- veto-count: 11 (open: 7, resolved-at-assembly: 4)
- confidence-min: 84 (§3 routing and §6 per-screen tied, post-patch)
- screens-covered: 22 / 22 (registry headings == §6 subsections)
- endpoints-cataloged: 216 (24 blueprints) + 8 app-level = 224 grepped routes (§4 appendix)
- registry-rows-mapped: 542 (every F-NNN row referenced in §6 by row range)
- carryover-rules-applied: RULE 1 (endpoint grep), RULE 2 (mirror JSON), RULE 3 (concurrency banned patterns), RULE 6 (post-build self-validation), RULE 14 (screenshot match), RULE 18 (CodingKey trap → Dart `@JsonKey` discipline), RULE 19 (no orphan placeholders)

# plan-complete: agents=7 vetoes=11 confidence=84
