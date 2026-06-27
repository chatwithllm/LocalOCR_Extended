# UX/UI Audit — LocalOCR Extended (Flutter)

**Audited:** 2026-06-26  
**Auditor role:** Principal Product Designer / Accessibility Expert  
**Scope:** All implemented screens in `lib/features/`  
**Stack:** Flutter/Dart, Material 3, Riverpod, go_router, 6-theme design token system

---

## Project Understanding

LocalOCR Extended is a household management app covering inventory, shopping, medicine, expenses, balances, dining, and contacts. Primary users are household admins and members on Android phones; tablet/wide-screen layout is secondary. The design system is unusually mature — 122 tokens across 6 themes (light, dark, clay, clay-dark, notion, notion-dark) auto-generated from JSON.

---

## FINDINGS

---

### UX-001

**Severity:** Critical  
**Confidence:** High

**Location:**  
- `lib/features/appshell/app_shell.dart`  
- `lib/features/inventory/presentation/inventory_screen.dart`  
- `lib/features/shopping/presentation/shopping_screen.dart`  
- `lib/features/medicine/presentation/medicine_screen.dart`  
- `lib/features/balances/presentation/balances_screen.dart`

**Problem**  
Four feature screens create their own `Scaffold(appBar: AppBar(...))` while already being children of the `AppShell` `Scaffold`. This renders two visible AppBars stacked vertically on every affected screen — the outer AppShell AppBar (with theme toggle and account button) plus the inner screen AppBar (with refresh button). Each AppBar is ~56dp tall, consuming ~112dp of vertical space on mobile before any content appears. The `DashboardScreen` does not have a nested Scaffold, so it shows only one AppBar.

**Evidence**  
`app_shell.dart:57–98` — AppShell wraps child in `Scaffold(appBar: AppBar(title: Text(title), actions: [...]))`.  
`inventory_screen.dart:50–60` — `InventoryScreen.build()` returns `Scaffold(appBar: AppBar(title: const Text('Inventory'), actions: [IconButton(...)]))`.  
Same pattern in `shopping_screen.dart:52–61`, `medicine_screen.dart:56–79`, `balances_screen.dart:35–45`.

**UX Principle Violated**  
Nielsen #8 — Aesthetic and Minimalist Design. WCAG 2.4.1 — Bypass Blocks (double chrome wastes reachable space). iOS HIG and Material 3 Navigation both prescribe a single persistent app bar per screen.

**Recommendation**  
Choose one authoritative AppBar per screen. Preferred approach: keep the AppShell AppBar for identity (app name, account, theme toggle) and move per-screen actions (refresh, add, members) into the AppShell `actions` list by reading them from a screen-level provider or callback. Alternatively, remove the AppShell AppBar and let each screen own its AppBar with all required actions added manually.

**Implementation Guidance**  
Option A (preferred — least refactor): Remove `appBar:` from the four nested Scaffolds (`InventoryScreen`, `ShoppingScreen`, `MedicineScreen`, `BalancesScreen`). Move each screen's actions into the AppShell `actions` list. Since actions differ per screen, introduce a `screenActionsProvider` that each screen can populate:

```dart
// In AppShell:
final actions = ref.watch(appShellActionsProvider);
AppBar(
  title: Text(title),
  actions: [
    ...actions,
    IconButton(tooltip: 'Switch theme', ...),
    IconButton(tooltip: 'Account', ...),
  ],
)

// In InventoryScreen.initState (or ConsumerStatefulWidget.didChangeDependencies):
ref.read(appShellActionsProvider.notifier).state = [
  IconButton(tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: ...)
];
```

Option B: Drop AppShell AppBar entirely. Each screen owns its full AppBar. The account/theme buttons move to a persistent icon inside each screen's AppBar or into the NavigationDrawer header.

**Dependencies:** None (self-contained shell + screen refactor).

**Expected User Impact:** Recovers ~56dp of vertical content space on every affected screen. Eliminates visual redundancy that makes the app look broken on first launch.

---

### UX-002

**Severity:** Critical  
**Confidence:** High

**Location:**  
- `lib/features/medicine/presentation/medicine_screen.dart:394–428`

**Problem**  
The medicine tile action row (Edit, Done, Delete) explicitly removes all minimum touch target constraints via `padding: EdgeInsets.zero` and `constraints: const BoxConstraints()` on `IconButton`. The icon size is 18dp. With zero padding and no BoxConstraints minimum, the actual tappable area is exactly 18×18dp — well below the 48×48dp Material Design minimum, 44×44pt Apple HIG minimum, and WCAG 2.5.5 44×44 CSS-pixel target size requirement. On small phones these buttons become practically untappable.

**Evidence**  
`medicine_screen.dart:394–401`:
```dart
IconButton(
  tooltip: 'Edit',
  iconSize: 18,
  visualDensity: VisualDensity.compact,
  padding: EdgeInsets.zero,
  constraints: const BoxConstraints(),  // removes ALL minimums
  icon: const Icon(Icons.edit_outlined),
  onPressed: () => _openEditSheet(context, med),
),
```
Same pattern on the delete button at lines 416–426.

**UX Principle Violated**  
WCAG 2.5.5 Target Size (AA). Material Design Touch Target Guidelines (48×48dp minimum). Apple HIG (44pt minimum). Fitts's Law — tiny targets on small screens with three buttons competing for 44dp of tile footer space.

**Recommendation**  
Remove `padding: EdgeInsets.zero` and `constraints: const BoxConstraints()`. Use `visualDensity: VisualDensity.compact` alone to reduce size while preserving the framework's minimum touch target guarantee (default `BoxConstraints(minWidth: 48, minHeight: 48)`). Reduce `iconSize` to 20 (not 18) so the icon remains legible at compact density.

**Implementation Guidance**  
In `_MedTile.build()` edit button (line 394) and delete button (line 416):

```dart
// Remove these two lines from both IconButtons:
padding: EdgeInsets.zero,
constraints: const BoxConstraints(),

// Keep (or set):
iconSize: 20,
visualDensity: VisualDensity.compact,
```

The `TextButton.icon` for "Done" at line 404 uses `minimumSize: const Size(0, 32)` which is also below spec. Change to `minimumSize: const Size(44, 44)`.

**Dependencies:** None.

**Expected User Impact:** Eliminates the most common cause of "missed taps" in the medicine cabinet grid, especially critical because the Delete button is the most dangerous action in the tile and the smallest target.

---

### UX-003

**Severity:** Critical  
**Confidence:** High

**Location:**  
- `lib/features/shopping/presentation/shopping_screen.dart:521–528`

**Problem**  
The shopping list Delete button (`_delete`) calls the API directly with no confirmation dialog. When quantity reaches 0 via the `−1` button, `_decrement` also calls `_delete` silently. There is no undo. Users routinely misfire delete on scrollable lists with small buttons, especially with three icon buttons (`−1`, `bought`, `delete`) packed side-by-side in a 36dp-wide row. By contrast, the Medicine and Balances screens both show `AlertDialog` before destructive operations.

**Evidence**  
`shopping_screen.dart:521–528`:
```dart
Future<void> _delete(BuildContext context, WidgetRef ref) async {
  try {
    await ref.read(shoppingRepositoryProvider).delete(item.id);
    ref.invalidate(shoppingListProvider);
  } catch (e) {
    _toast(context, 'Could not delete: $e', isError: true);
  }
}
```
No `showDialog` call. `_decrement` at line 494–506 calls `_delete` when `newQty <= 0`.

**UX Principle Violated**  
Nielsen #5 — Error Prevention. Nielsen #3 — User Control and Freedom (no undo). Material 3 Destructive Action pattern requires confirmation.

**Recommendation**  
Option A (confirmation dialog): Show `AlertDialog` before deleting, matching the Medicine pattern.  
Option B (snackbar with undo — preferred for quick recovery): Delete immediately but show a SnackBar with an "Undo" action that re-creates the item within a time window. This is faster to dismiss for intentional deletes while providing recovery.

**Implementation Guidance — Option B:**

```dart
Future<void> _delete(BuildContext context, WidgetRef ref) async {
  final item = this.item; // capture before async gap
  try {
    await ref.read(shoppingRepositoryProvider).delete(item.id);
    ref.invalidate(shoppingListProvider);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('"${item.title}" removed'),
        action: SnackBarAction(
          label: 'Undo',
          onPressed: () async {
            await ref.read(shoppingRepositoryProvider).create(
              name: item.title,
              category: item.category,
              quantity: item.quantity,
              // restore other fields
            );
            ref.invalidate(shoppingListProvider);
          },
        ),
        duration: const Duration(seconds: 5),
      ),
    );
  } catch (e) {
    _toast(context, 'Could not delete: $e', isError: true);
  }
}
```

For the `_decrement` path, show a SnackBar like: `'"Milk" removed (reached 0)'` with Undo.

**Dependencies:** Shopping repository must support re-create from the deleted item's fields.

**Expected User Impact:** Eliminates accidental data loss for the most actively used screen in the app. Shopping is the primary daily-use screen.

---

### UX-004

**Severity:** Critical  
**Confidence:** High

**Location:**  
- `lib/features/appshell/app_shell.dart:82–96`

**Problem**  
A prominent `FloatingActionButton` with chat bubble icon is visible on every screen in the app and opens a modal bottom sheet containing only the text "Chat coming soon". This is a permanently broken affordance — it signals an important action, invites a tap, and delivers nothing. Users will tap it multiple times (especially new users), erode trust in the app's reliability, and potentially confuse the FAB position with legitimate screen-level FABs (e.g., "Add item" on Shopping or Inventory).

**Evidence**  
`app_shell.dart:82–96`:
```dart
floatingActionButton: FloatingActionButton(
  tooltip: 'Chat',
  onPressed: () {
    showModalBottomSheet(
      ...
      builder: (_) => const SizedBox(
        height: 480,
        child: Center(child: Text('Chat coming soon')),
      ),
    );
  },
  child: const Icon(Icons.chat_bubble_outline),
),
```

**UX Principle Violated**  
Nielsen #1 — Visibility of System Status. Nielsen #10 — Help and Documentation. Jakob's Law — users expect actionable controls to work. Material 3 FAB guidelines state FABs should represent the most important action on a screen — a disabled feature placeholder violates this.

**Recommendation**  
Remove the FAB entirely until Chat is implemented. Do not display placeholder features as primary-action affordances. When Chat is ready, add the FAB back per-screen only where it's the primary action, or add it as a persistent bottom navigation item.

**Implementation Guidance**  
In `app_shell.dart`, delete lines 82–96:
```dart
// Remove this entire block:
floatingActionButton: FloatingActionButton(
  tooltip: 'Chat',
  onPressed: () { ... },
  child: const Icon(Icons.chat_bubble_outline),
),
```

**Dependencies:** None. Add FAB back when Chat feature ships.

**Expected User Impact:** Removes a trust-eroding dead end. Clears 56×56dp of screen space (bottom-right) that currently obscures content on all screens.

---

### UX-005

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/appshell/nav_destinations.dart`  
- `lib/app/router/router.dart`

**Problem**  
The navigation drawer has 19 items. 10 of these route to `PlaceholderScreen` (Upload, Receipts, Kitchen, Budget, Bills, Accounts, Analytics, Contributions, Features, Settings). When a user selects any of these, they see a construction icon and a title. This presents a navigation structure that is 53% non-functional. Beyond the placeholder problem, 19 items exceeds Miller's Law's practical working-memory limit (7 ± 2 items). Users cannot quickly scan and select destinations.

**Evidence**  
`nav_destinations.dart:12–33` — 19 `NavDest` entries.  
`router.dart` — Budget, Bills, Accounts, Analytics, Contributions, Features, Settings, Upload, Receipts (list), Kitchen all route to `PlaceholderScreen(...)`.

**UX Principle Violated**  
Miller's Law (cognitive load limit). Nielsen #9 — Help Users Recognize, Diagnose, and Recover from Errors (showing items users cannot use creates false affordances). Progressive disclosure principle.

**Recommendation**  
Immediately: Hide all placeholder destinations from the drawer. Add them back individually when their screens are implemented. This reduces visible items from 19 to 9 (Dashboard, Inventory, Products, Medicine, Shopping, Restaurant, Balances, Contacts, Expenses).

Long-term: Group related destinations. Suggested groupings:
- **Home:** Dashboard  
- **Household:** Inventory, Products, Medicine, Kitchen  
- **Finance:** Shopping, Expenses, Restaurant, Balances, Budget, Bills, Accounts  
- **Social:** Contacts, Contributions  
- **System:** Upload, Analytics, Features, Settings

**Implementation Guidance**  

Step 1 — Add `isImplemented` flag to `NavDest`:
```dart
class NavDest {
  final String id;
  final String path;
  final String label;
  final IconData icon;
  final bool isImplemented; // ADD
  const NavDest(this.id, this.path, this.label, this.icon, {this.isImplemented = false});
}
```

Step 2 — Mark implemented destinations:
```dart
const drawerDestinations = <NavDest>[
  NavDest('dashboard', '/dashboard', 'Dashboard', Icons.dashboard_outlined, isImplemented: true),
  NavDest('inventory', '/inventory', 'Inventory', Icons.kitchen_outlined, isImplemented: true),
  NavDest('products', '/products', 'Products', Icons.shopping_bag_outlined, isImplemented: true),
  NavDest('medicine', '/medicine', 'Medicine', Icons.medication_outlined, isImplemented: true),
  NavDest('shopping', '/shopping', 'Shopping', Icons.shopping_cart_outlined, isImplemented: true),
  NavDest('restaurant', '/restaurant', 'Restaurant', Icons.restaurant_outlined, isImplemented: true),
  NavDest('balances', '/balances', 'Balances', Icons.account_balance_outlined, isImplemented: true),
  NavDest('contacts', '/contacts', 'Contacts', Icons.group_outlined, isImplemented: true),
  NavDest('expenses', '/expenses', 'Expenses', Icons.payments_outlined, isImplemented: true),
  // All others default to isImplemented: false — hidden until built
  NavDest('upload', '/upload', 'Upload', Icons.add_a_photo_outlined),
  ...
];
```

Step 3 — Filter in `AppShell`:
```dart
final destinations = drawerDestinations.where((d) {
  if (!d.isImplemented) return false; // ADD THIS LINE
  if (d.id == 'restaurant' && modules != null && !modules.restaurant) return false;
  return true;
}).toList();
```

**Dependencies:** None.

**Expected User Impact:** Drawer becomes scannable (~9 items vs 19). Eliminates all dead-end navigation. Reduces user frustration significantly on first use.

---

### UX-006

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:714–742`

**Problem**  
Inventory tiles support swipe-right (−1 quantity) and swipe-left (mark used up) gestures, but there is no discoverability mechanism. The swipe backgrounds only appear during the swipe itself. New users have no indication these gestures exist. Swipe-right for "decrement" and swipe-left for "used up" are also counter-intuitive: the most common Android/Material pattern is swipe-left for destructive/primary action and swipe-right for secondary/archive action. The current implementation reverses this.

**Evidence**  
`inventory_screen.dart:714–742`:
```dart
Dismissible(
  background: Container(  // swipe-right background
    color: th.colorScheme.secondaryContainer,
    alignment: Alignment.centerLeft,
    child: const Icon(Icons.remove_circle_outline),
  ),
  secondaryBackground: Container(  // swipe-left background  
    color: th.colorScheme.errorContainer,
    alignment: Alignment.centerRight,
    child: const Icon(Icons.check_circle_outline),  // used-up
  ),
  confirmDismiss: (dir) async {
    if (dir == DismissDirection.startToEnd) { // swipe-right → −1
```

**UX Principle Violated**  
Nielsen #6 — Recognition Rather Than Recall (hidden gestures require recall). Platform convention (Material Design swipe patterns). Jakob's Law — swipe-left-to-archive/act is the dominant mobile convention (Gmail, iOS Mail, Google Tasks).

**Recommendation**  
1. Add a one-time "hint" animation on first load that briefly reveals the swipe backgrounds (partial swipe animation, then snap back). Use `SharedPreferences` key `'inventory_swipe_hint_shown'` to show only once.  
2. Add a tooltip or help text below the filter bar on first run: "Swipe right to use one, swipe left to mark used up."  
3. Fix the swipe direction convention: swap so swipe-left = primary action (−1 decrement) and swipe-right = secondary (mark used up). Alternatively both directions trigger the same "quick action" popup.

**Implementation Guidance — Hint animation:**
```dart
class _InventoryTile extends ConsumerWidget {
  // Add key for AnimationController in parent state
}
// In _InventoryScreenState.initState(), check SharedPreferences:
final prefs = await SharedPreferences.getInstance();
if (!prefs.getBool('inventory_swipe_hint_shown') ?? false) {
  // Trigger a brief partial-swipe animation on the first tile
  // after list loads, then mark as shown
  prefs.setBool('inventory_swipe_hint_shown', true);
}
```

**Dependencies:** `shared_preferences` (already in pubspec).

**Expected User Impact:** Swipe shortcuts are discovered vs remaining hidden for most users. Correct convention mapping reduces mis-swipes.

---

### UX-007

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/balances/presentation/balances_screen.dart:105–107`  
- `lib/features/dashboard/presentation/dashboard_screen.dart:455–461`  
- `lib/features/medicine/presentation/medicine_screen.dart:303–307, 348`  
- `lib/features/shopping/presentation/shopping_screen.dart:444–445, 477`

**Problem**  
Multiple screens use hard-coded color literals that bypass the design token system (`AppTokens`). This breaks the theme contract: these colors do not adapt between the 6 themes. On dark themes, `Colors.green` (WCAG contrast ~2.3:1 on dark surface) and `Colors.redAccent` (variable) may fail WCAG 1.4.3 contrast. `const Color(0xFF66BB6A)` and `const Color(0xFFE57373)` are particularly risky on clay/notion themes whose surfaces differ significantly from Material defaults.

**Evidence**  
- `balances_screen.dart:105–107`: `const Color(0xFF66BB6A)` for "owes you" direction  
- `dashboard_screen.dart:455–461`: `Colors.redAccent` (increase) and `Colors.green` (decrease) for spending delta  
- `medicine_screen.dart:303–307`: `const Color(0xFFE57373)` (expired), `const Color(0xFFFFB74D)` (low)  
- `medicine_screen.dart:348`: `const _Pill(text: 'Low', color: Color(0xFFFFB74D))`  
- `shopping_screen.dart:444–445`: `Colors.grey` for purchased item text and subtitle  
- `shopping_screen.dart:477`: `const Color(0xFF66BB6A)` for "Mark bought" icon

**UX Principle Violated**  
WCAG 1.4.3 — Contrast (Minimum). Design system consistency (tokens exist for exactly this purpose — `AppTokens.success`, `AppTokens.error`, `AppTokens.warning`, `AppTokens.textMuted`).

**Recommendation**  
Replace all hard-coded color literals with `AppTokens` values accessed via `Theme.of(context).extension<AppTokens>()!`.

**Implementation Guidance**  

In each file, get tokens once:
```dart
final t = Theme.of(context).extension<AppTokens>()!;
```

Replace literals:
| Hard-coded | Replace with |
|---|---|
| `const Color(0xFF66BB6A)` | `t.success` |
| `const Color(0xFFE57373)` | `t.error` |
| `const Color(0xFFFFB74D)` | `t.warning` |
| `Colors.redAccent` | `t.error` |
| `Colors.green` | `t.success` |
| `Colors.grey` | `t.textMuted` |

For medicine tile border accent:
```dart
// Old:
final accent = isExpired ? const Color(0xFFE57373) : isLow ? const Color(0xFFFFB74D) : null;
// New:
final tokens = Theme.of(context).extension<AppTokens>()!;
final accent = isExpired ? tokens.error : isLow ? tokens.warning : null;
```

For medicine `_Pill` widget, update its `color` parameter to accept `Color` and pass `t.warningSoft` with `t.warning` text.

**Dependencies:** `AppTokens` class already exists in `lib/app/theme/tokens.generated.dart`.

**Expected User Impact:** Semantic colors now adapt to all 6 themes. Clay and Notion themes show appropriate contrast.

---

### UX-008

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/auth/login_screen.dart:481–484`

**Problem**  
The Device Approval inline card exposes an API endpoint path as `helperText` in a user-facing form field:
```
'/auth/users requires admin login; enter id directly here.'
```
This is a developer implementation note surfaced to all users who see the Device Approval card. It reveals internal architecture, API routes, and the reason a field is limited — none of which are relevant to an admin completing device approval.

**Evidence**  
`login_screen.dart:481–484`:
```dart
decoration: const InputDecoration(
  labelText: 'Linked user id (optional — defaults to you)',
  border: OutlineInputBorder(),
  helperText: '/auth/users requires admin login; enter id directly here.',
),
```

**UX Principle Violated**  
Nielsen #4 — Consistency and Standards (non-user language in UI). Security consideration (revealing internal API structure).

**Recommendation**  
Replace the helperText with user-meaningful guidance:
```dart
helperText: 'Optional. Leave blank to link to your account.',
```

**Implementation Guidance**  
In `login_screen.dart` line 483, change:
```dart
// Remove:
helperText: '/auth/users requires admin login; enter id directly here.',
// Add:
helperText: 'Optional — leave blank to link to your account.',
```

**Dependencies:** None.

**Expected User Impact:** Removes internal implementation detail from user-facing UI. Improves professionalism.

---

### UX-009

**Severity:** High  
**Confidence:** High

**Location:**  
Multiple screens — inventory, shopping, medicine, balances, contacts, dashboard, auth

**Problem**  
Error messages throughout the app expose raw Dart exception strings to users. `SnackBar(content: Text('Add failed: $e'))` where `$e` might be a DioException with stack fragments, a socket timeout with internal hostnames, or an AppException with raw API response bodies. This is both a poor UX and a mild information leak.

**Evidence**  
- `inventory_screen.dart:529`: `SnackBar(content: Text('Add failed: $e'))`  
- `shopping_screen.dart:337`: `_toast('Could not add: $e', isError: true)`  
- `dashboard_screen.dart:75`: `Text('$error')` (error view)  
- `medicine_screen.dart:458`: `SnackBar(content: Text('Failed: $e'))`  
- `balances_screen.dart:170`: `SnackBar(content: Text('Settle failed: $e'))`

**UX Principle Violated**  
Nielsen #9 — Help Users Recognize, Diagnose, and Recover from Errors (messages should be plain language with suggestions, not technical codes). Security hygiene.

**Recommendation**  
Route all errors through `AppException.message` (already defined in `lib/core/errors/app_exception.dart`). Add a utility `_friendlyError(dynamic e)` function that extracts the message or returns a generic string.

**Implementation Guidance**  

Add to `lib/core/errors/app_exception.dart` (or a new `lib/core/util/error_ui.dart`):
```dart
String friendlyError(dynamic e) {
  if (e is AppException) return e.message;
  // Avoid leaking internal exception class names or stack traces
  return 'Something went wrong. Please try again.';
}
```

Replace all `'$e'` and `'$error'` in SnackBars and error views with `friendlyError(e)`:
```dart
// Shopping _save():
_toast('Could not add item. Please try again.', isError: true);
// or with friendly message:
_toast(friendlyError(e), isError: true);
```

For the Dashboard error view, replace:
```dart
Text('$error', ...)
// With:
Text(friendlyError(error), ...)
```

**Dependencies:** `AppException` already exists.

**Expected User Impact:** Users see plain-language error messages. No internal paths, class names, or API details leak into the UI.

---

### UX-010

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/dashboard/presentation/dashboard_screen.dart:635–696`

**Problem**  
The `_Sparkline` custom chart (receipts activity) uses `CustomPainter` with no semantic annotation. Screen readers receive no information about the chart's content, axes, trends, or values. The chart is the only data visualization in the app, and it displays receipt processing activity — meaningful data for household admins.

**Evidence**  
`dashboard_screen.dart:635–659` — `_Sparkline` renders via `CustomPaint` painter. No `Semantics` widget wraps it. No `semanticsBuilder` on `CustomPaint`.

**UX Principle Violated**  
WCAG 1.1.1 — Non-text Content (all non-text content must have a text alternative). WCAG 4.1.2 — Name, Role, Value.

**Recommendation**  
Wrap `_Sparkline` in a `Semantics` widget that describes the chart data textually. For a sparkline, the most useful description is the trend direction and total count.

**Implementation Guidance**  
In `_ReceiptsActivityCard.build()`, wrap the `SizedBox` containing `_Sparkline`:

```dart
// Compute description before widget tree:
final total = activity.total;
final buckets = activity.buckets;
final trend = buckets.length >= 2
    ? (buckets.last.count > buckets.first.count ? 'increasing' : 'decreasing')
    : 'stable';

// Wrap sparkline:
Semantics(
  label: 'Receipts activity chart. $total receipts total. Trend is $trend.',
  excludeSemantics: true, // prevent child CustomPainter from adding conflicting nodes
  child: SizedBox(
    height: 80,
    child: _Sparkline(activity: activity),
  ),
),
```

**Dependencies:** None.

**Expected User Impact:** Screen reader users can access receipt activity data. WCAG 1.1.1 compliance.

---

### UX-011

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/appshell/app_shell.dart:74–81`

**Problem**  
In wide layout (≥840dp), the `NavigationDrawer` widget is placed inside a `Row` as a persistent side panel. `NavigationDrawer` is designed for temporary/modal drawer use — it includes elevation, scrim handling, and internal padding optimized for overlay presentation. When used as an inline panel, it renders with excessive top padding (`fromLTRB(28, 16, 16, 10)` plus NavigationDrawer's internal padding) and the wrong visual elevation treatment for a persistent rail. The result is a side panel that looks like a floating modal dialog stuck to the left edge.

**Evidence**  
`app_shell.dart:74–81`:
```dart
body: wide
    ? Row(
        children: [
          SizedBox(width: 280, child: drawerBody), // NavigationDrawer used as inline panel
          Expanded(child: child),
        ],
      )
    : child,
```

**UX Principle Violated**  
Material 3 Navigation Drawer spec — `NavigationDrawer` is a modal pattern. `NavigationRail` is the correct widget for persistent side navigation on medium/wide breakpoints.

**Recommendation**  
Replace the wide-layout `NavigationDrawer` with a `NavigationRail` on medium screens (840–1200dp) and optionally a full `NavigationDrawer`-style panel on large screens (>1200dp). The `NavigationRail` provides the correct persistent-rail semantics, label placement, and visual treatment.

**Implementation Guidance**  

```dart
// In AppShell, replace the wide body Row:
body: wide
    ? Row(
        children: [
          NavigationRail(
            selectedIndex: activeIndex >= 0 ? activeIndex : 0,
            onDestinationSelected: (i) => context.go(destinations[i].path),
            labelType: NavigationRailLabelType.all,
            leading: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                session?.appConfig.appName ?? 'LocalOCR',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ),
            destinations: [
              for (final d in destinations)
                NavigationRailDestination(
                  icon: Icon(d.icon),
                  label: Text(d.label),
                ),
            ],
          ),
          const VerticalDivider(thickness: 1, width: 1),
          Expanded(child: child),
        ],
      )
    : child,
```

Remove the `Navigator.of(context).pop()` call from `drawerBody.onDestinationSelected` — it is not needed on `NavigationRail` (no modal to close) and may interfere with go_router navigation.

**Dependencies:** None (NavigationRail is in Flutter Material library).

**Expected User Impact:** Wide-screen users see an appropriate persistent side navigation that follows Material 3 specifications. Eliminates the floating-drawer-stuck-on-left visual artifact.

---

### UX-012

**Severity:** High  
**Confidence:** High

**Location:**  
- `lib/features/appshell/app_shell.dart:35–38`

**Problem**  
`NavigationDrawer.onDestinationSelected` always calls `Navigator.of(context).pop()` before navigating. On narrow screens (drawer is modal), this correctly closes the drawer. On wide screens (drawer is inside a `Row` as an inline panel), there is no modal drawer to pop — the `pop()` call either does nothing or pops from the go_router navigation stack, depending on whether any route is on the stack. If a route is on the stack (e.g., a modal opened on a detail screen), selecting a nav destination would unintentionally close that modal first.

**Evidence**  
`app_shell.dart:35–38`:
```dart
onDestinationSelected: (i) {
  Navigator.of(context).pop(); // Called unconditionally in all layouts
  context.go(destinations[i].path);
},
```

**UX Principle Violated**  
Nielsen #1 — Visibility of System Status (unexpected route pops are invisible to users). Predictability.

**Recommendation**  
Make the `pop()` conditional on the layout:

```dart
onDestinationSelected: (i) {
  if (!wide) Navigator.of(context).pop(); // Only pop modal drawer on narrow
  context.go(destinations[i].path);
},
```

Pass `wide` into the `drawerBody` or use a layout check inside `onDestinationSelected`.

**Implementation Guidance**  

In `app_shell.dart`, the `drawerBody` is built before knowing `wide`. Move `onDestinationSelected` to reference `wide` from the closure:

```dart
final drawerBody = NavigationDrawer(
  selectedIndex: activeIndex >= 0 ? activeIndex : 0,
  onDestinationSelected: (i) {
    if (!wide) Navigator.of(context).pop(); // Only close modal drawer
    context.go(destinations[i].path);
  },
  ...
);
```

Since `drawerBody` is built inside `build()` where `wide` is in scope, this closure captures `wide` correctly.

**Dependencies:** Fix UX-011 first — if replacing NavigationDrawer with NavigationRail for wide layout, this issue resolves automatically (NavigationRail doesn't call pop).

**Expected User Impact:** Eliminates accidental modal/route dismissal when navigating on wide screens.

---

### UX-013

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/auth/login_screen.dart:505–520`

**Problem**  
The Device Approval inline card has an Admin password field (`obscureText: true`) with no visibility toggle. The main login form (directly below) has a visibility toggle on its password field. Admins entering credentials in the device approval flow cannot verify what they've typed, increasing input errors and failed approvals.

**Evidence**  
`login_screen.dart:506–519`:
```dart
TextField(
  key: const Key('device-approval-inline-password'),
  controller: _adminPassCtrl,
  obscureText: true,  // no toggle provided
  decoration: const InputDecoration(
    labelText: 'Admin password',
    border: OutlineInputBorder(),
  ),
),
```
Compare with login form at line 222–234 which has the `suffixIcon: IconButton(...)` toggle.

**UX Principle Violated**  
Consistency and Standards (Nielsen #4). WCAG 2.5.3 implies users should be able to verify secure input.

**Recommendation**  
Add a stateful show/hide password toggle identical to the main login form's pattern. Add `bool _showAdminPass = false` to `_DeviceApprovalInlineCardState` and update the field.

**Implementation Guidance**  
In `_DeviceApprovalInlineCardState`, add:
```dart
bool _showAdminPass = false;
```

Update the admin password field (line 506–519):
```dart
TextField(
  key: const Key('device-approval-inline-password'),
  controller: _adminPassCtrl,
  obscureText: !_showAdminPass,
  decoration: InputDecoration(
    labelText: 'Admin password',
    border: const OutlineInputBorder(),
    suffixIcon: IconButton(
      tooltip: _showAdminPass ? 'Hide password' : 'Show password',
      icon: Icon(_showAdminPass ? Icons.visibility_off_outlined : Icons.visibility_outlined),
      onPressed: () => setState(() => _showAdminPass = !_showAdminPass),
    ),
  ),
),
```

**Dependencies:** None.

**Expected User Impact:** Admin can verify password before submitting approval, reducing failed approvals.

---

### UX-014

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/shopping/presentation/shopping_screen.dart:44`  
- `lib/features/balances/presentation/balances_screen.dart:26`

**Problem**  
Currency is hard-coded as USD throughout the app: `NumberFormat.simpleCurrency(name: 'USD')`. The app is a general household management app with no indication it's US-only. International households using this app (or self-hosted instances) cannot use meaningful currency formatting. This also affects the Dashboard's spending display (`'\$${spending.total.toStringAsFixed(2)}'` at `dashboard_screen.dart:396`) and Expenses screen.

**Evidence**  
`shopping_screen.dart:44`: `final _money = NumberFormat.simpleCurrency(name: 'USD');`  
`balances_screen.dart:26`: `final _money = NumberFormat.simpleCurrency(name: 'USD');`  
`dashboard_screen.dart:396`: `'\$${spending.total.toStringAsFixed(2)}'` (manual dollar sign)

**UX Principle Violated**  
Internationalization best practice. Respect for user locale.

**Recommendation**  
Pull currency configuration from `appConfig` (already loaded in `sessionProvider`). Fall back to device locale currency. Add a `currency` field to `AppConfig` model (or read from existing config).

**Implementation Guidance**  

Step 1 — Check if `AppConfig` has a currency field. If not, add to `app_config.dart`:
```dart
final String currency; // e.g., 'USD', 'EUR', 'GBP'
```

Step 2 — Create a shared currency formatter provider:
```dart
// In lib/core/providers.dart or a new currency_provider.dart:
final currencyFormatterProvider = Provider<NumberFormat>((ref) {
  final currency = ref.watch(sessionProvider)?.appConfig.currency ?? 'USD';
  return NumberFormat.simpleCurrency(name: currency);
});
```

Step 3 — Replace module-level `final _money = NumberFormat.simpleCurrency(name: 'USD')` with `ref.watch(currencyFormatterProvider)` in ConsumerWidgets. For `StatelessWidget`s that use `_money`, convert to `ConsumerWidget`.

**Dependencies:** Requires backend to surface currency in `/auth/bootstrap` or `/auth/me` response.

**Expected User Impact:** International households see correct currency symbols. App is usable globally.

---

### UX-015

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:562–582`

**Problem**  
The inventory search `TextField` uses `hintText: 'Search inventory'` but no `labelText`. Flutter's `hintText` is only visible when the field is empty and unfocused or empty and focused. Once a user types a query, both the placeholder and the field context disappear. Screen readers announce a focused empty field by its `labelText`; without it, the field is announced with no accessible name. On population, screen readers lose the field purpose entirely.

**Evidence**  
`inventory_screen.dart:568–571`:
```dart
decoration: InputDecoration(
  hintText: 'Search inventory',
  prefixIcon: const Icon(Icons.search),
  border: const OutlineInputBorder(),
  isDense: true,
```
No `labelText` present. `semanticsLabel` not set.

**UX Principle Violated**  
WCAG 1.3.1 — Info and Relationships. WCAG 3.3.2 — Labels or Instructions. Material 3 text field spec requires a visible label for persistent field identification.

**Recommendation**  
Add `labelText: 'Search'` alongside `hintText`. The label floats above when focused/filled, providing persistent context. Alternatively, set a `Semantics` wrapper with a label.

**Implementation Guidance**  
```dart
decoration: InputDecoration(
  labelText: 'Search inventory', // ADD
  hintText: 'Type to filter',    // Make hint complementary, not duplicative
  prefixIcon: const Icon(Icons.search),
  border: const OutlineInputBorder(),
  isDense: true,
  ...
),
```

Apply the same pattern to the Products search field (likely same issue).

**Dependencies:** None.

**Expected User Impact:** Screen readers announce field purpose when focused. Sighted users see floating label when field is populated.

---

### UX-016

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:362–413`  
- `lib/features/shopping/presentation/shopping_screen.dart:228–300`  
- `lib/features/auth/login_screen.dart:205–234`

**Problem**  
Form fields use inconsistent `InputDecoration` borders across screens:
- Login: explicit `border: const OutlineInputBorder()` — outlined style
- Inventory AddCard: no `border:` specified — uses theme default (underline in many themes)
- Shopping AddCard: no `border:` on name field (line 233), but uses `isDense: true`

This means the same app presents both outlined and underline-style text fields depending on which screen you're on, and what the active theme defaults to. In the notion and clay themes, theme defaults may differ further.

**Evidence**  
`login_screen.dart:209`: `border: const OutlineInputBorder()`  
`inventory_screen.dart:367–371`: `InputDecoration(labelText: 'Product name', prefixIcon: Icon(...))` — no border  
`shopping_screen.dart:232–236`: `InputDecoration(labelText: 'Name *', hintText: ..., isDense: true)` — no border

**UX Principle Violated**  
Nielsen #4 — Consistency and Standards. Material 3 text field guidelines — choose one style per app (outlined or filled) and apply consistently.

**Recommendation**  
Standardize on `OutlineInputBorder` (already used in login and device-pairing forms). Add `border: const OutlineInputBorder()` to all text fields and `DropdownButtonFormField` instances that don't currently specify it. Alternatively, set the default `InputDecorationTheme` in the app theme to use outlined style globally, so individual fields inherit it automatically.

**Implementation Guidance — Theme-level fix (preferred):**  
In `lib/app/theme/theme.dart` where `ThemeData` is built:
```dart
inputDecorationTheme: const InputDecorationTheme(
  border: OutlineInputBorder(),
  filled: false,
),
```

This applies to all text fields that don't override `border:`, eliminating the need to touch individual screens.

**Dependencies:** The design token file may already configure `InputDecorationTheme` — verify before adding duplicate.

**Expected User Impact:** Consistent form appearance across all screens regardless of active theme.

---

### UX-017

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:121–132`  
- `lib/features/shopping/presentation/shopping_screen.dart:378–384`  
- `lib/features/balances/presentation/balances_screen.dart:72–80`  
- `lib/features/medicine/presentation/medicine_screen.dart:134–147`

**Problem**  
Empty states across the app are inconsistent in voice, format, and utility:
- Inventory: `'No inventory rows match these filters.'` — neutral, no next action
- Shopping: `'Nothing to shop for. Add an item above.'` — directive, references UI location
- Balances: `'No outstanding balances — all settled! 🎉'` — celebratory, emoji
- Medicine: `'No medications. Tap + Add Medication to get started.'` — directive, no icon

None of the empty states include an icon. Most lack a clear action button. The voice varies from neutral to celebratory with no consistent pattern.

**UX Principle Violated**  
Nielsen #4 — Consistency and Standards. Empty state design pattern (icon + label + optional action).

**Recommendation**  
Standardize all empty states on a 3-part pattern: **icon + message + optional CTA button**. Tone should be contextual (celebratory for settled balances is correct) but structure must be consistent.

**Implementation Guidance**  
Create a shared `EmptyStateView` widget in `lib/features/shared/`:

```dart
class EmptyStateView extends StatelessWidget {
  const EmptyStateView({
    super.key,
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
  });
  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: th.colorScheme.outline),
            const SizedBox(height: 12),
            Text(message,
                textAlign: TextAlign.center,
                style: th.textTheme.bodyMedium?.copyWith(
                  color: th.colorScheme.onSurfaceVariant,
                )),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 16),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}
```

Replace ad-hoc empty states with `EmptyStateView(icon: ..., message: ..., onAction: ...)`.

**Dependencies:** None.

**Expected User Impact:** Consistent empty states with clear next actions reduce user confusion.

---

### UX-018

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:589–648`

**Problem**  
The inventory filters bar mixes bare `DropdownButton` (no InputDecoration/border, smaller hit targets) with Material `FilterChip`. `DropdownButton` renders without visual chrome in a `Wrap` alongside `FilterChip` which has pill styling. The result is a controls row where filter dropdowns and filter chips have completely different visual styles, heights, and touch behaviors. Additionally, bare `DropdownButton` lacks an accessible label — screen readers can read the current value but not the field purpose.

**Evidence**  
`inventory_screen.dart:589–648`: Mix of `DropdownButton<String?>` (location filter, group-by, sort) and `FilterChip` (show-empty). `DropdownButton` has no `decoration` container.

**UX Principle Violated**  
Nielsen #4 — Consistency and Standards. WCAG 1.3.1 — accessible name for controls.

**Recommendation**  
Replace bare `DropdownButton` in the filters bar with `DropdownButtonFormField` wrapped in `InputDecoration(labelText: ...)` OR switch all filter controls to `ChoiceChip`s in a horizontal scroll row (matching the pattern used in `_ReceiptsActivityCard` grain selector). The chip approach is more mobile-friendly and already used in the shopping summary pills.

**Implementation Guidance — Chip approach for Location filter:**
```dart
// Replace DropdownButton location filter with chips:
SingleChildScrollView(
  scrollDirection: Axis.horizontal,
  child: Row(
    children: [
      for (final loc in [null, 'Pantry', 'Fridge', 'Freezer', 'Cabinet', 'Bathroom', 'Laundry'])
        Padding(
          padding: const EdgeInsets.only(right: 4),
          child: ChoiceChip(
            label: Text(loc ?? 'All'),
            selected: filters.location == loc,
            onSelected: (_) => notifier.state = filters.copyWith(location: loc),
          ),
        ),
    ],
  ),
),
```

If dropdown is retained, wrap in explicit `InputDecoration`:
```dart
DropdownButtonFormField<String?>(
  value: filters.location,
  decoration: const InputDecoration(labelText: 'Location', isDense: true, border: OutlineInputBorder()),
  items: [...],
  onChanged: (v) => notifier.state = filters.copyWith(location: v),
)
```

**Dependencies:** None.

**Expected User Impact:** Consistent filter controls with accessible labels. More compact mobile layout.

---

### UX-019

**Severity:** Medium  
**Confidence:** Medium

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:728–742`

**Problem**  
Inventory swipe directions may conflict with user expectations and have no undo:
- Swipe right (startToEnd) → decrement quantity (−1) — non-destructive
- Swipe left (endToStart) → mark as used up — semi-destructive (sets qty to 0)

The most common mobile pattern (Gmail, iOS Mail, Todoist, Google Keep) uses swipe-left as the primary action lane and swipe-right as secondary/archive. Having "mark used up" on the left makes it harder to trigger accidentally (good), but the lack of any undo mechanism means a mistaken swipe-left silently zeros the item. There's no snackbar for the used-up swipe either.

**Evidence**  
`inventory_screen.dart:733–742`: Both `confirmDismiss` branches return `false` (tile stays) and show success snackbars via `_wrap()`. No undo action is offered.

**UX Principle Violated**  
Nielsen #3 — User Control and Freedom. Error prevention.

**Recommendation**  
Add undo action to both swipe gesture success snackbars. The `_wrap()` helper currently shows a simple SnackBar; replace it with a SnackBar with undo action:

**Implementation Guidance**  

Replace the `_wrap` method:
```dart
Future<void> _wrapWithUndo({
  required BuildContext context,
  required Future<void> Function() action,
  required Future<void> Function() undoAction,
  required String successMessage,
}) async {
  try {
    await action();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(successMessage),
        action: SnackBarAction(
          label: 'Undo',
          onPressed: () async {
            await undoAction();
            ref.invalidate(inventoryListProvider);
          },
        ),
        duration: const Duration(seconds: 4),
      ),
    );
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(friendlyError(e))),
      );
    }
  }
}
```

This requires the inventory repository to expose inverse operations (increment qty, restore from used-up). Check if backend supports these.

**Dependencies:** Backend must support undo operations for inventory quantity and used-up status.

**Expected User Impact:** Accidental swipes are recoverable. Reduces anxiety around using swipe gestures.

---

### UX-020

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/shopping/presentation/shopping_screen.dart:123`

**Problem**  
The shopping session start date is displayed by slicing a raw string: `session.startedAt!.substring(0, 10)`. This is fragile (will crash if the string is shorter than 10 characters), locale-insensitive (always shows ISO format YYYY-MM-DD regardless of user locale), and unreadable (numbers with no month name).

**Evidence**  
`shopping_screen.dart:123`:
```dart
Text(session.startedAt!.substring(0, 10),
    style: const TextStyle(fontSize: 11, color: Colors.grey)),
```

**UX Principle Violated**  
Internationalization (dates should be formatted per locale). Defensive programming.

**Recommendation**  
Parse the ISO string with `DateTime.parse()` and format with `DateFormat.MMMd()` for a readable, locale-aware date like "Jun 15".

**Implementation Guidance**  
```dart
// Replace:
Text(session.startedAt!.substring(0, 10), ...)
// With:
Text(
  DateFormat.MMMd().format(DateTime.parse(session.startedAt!)),
  style: const TextStyle(fontSize: 11, color: Colors.grey),
),
```

`intl` package (`DateFormat`) is already imported in `shopping_screen.dart` line 10.

**Dependencies:** None. `intl` already in pubspec.

**Expected User Impact:** Readable dates like "Jun 15" instead of "2026-06-15". Locale-correct for international users.

---

### UX-021

**Severity:** Medium  
**Confidence:** High

**Location:**  
- `lib/features/dashboard/presentation/dashboard_screen.dart:329–360` (`_StatTile`)  
- `lib/features/dashboard/presentation/dashboard_screen.dart:900–923` (`_Card`)  
- `lib/features/dashboard/presentation/dashboard_screen.dart:208–246` (`_LeaderboardRow`)

**Problem**  
The `_Card` component is an `InkWell`-wrapped `Material` that accepts an `onTap` callback. When tapped, it navigates to another screen. However, it lacks `Semantics(button: true, label: ...)` — screen readers announce its contents as text but not as an interactive button with a navigation destination. Similarly, `_LeaderboardRow` uses bare `InkWell` with no semantic role. `_StatTile` shows a number and label but a screen reader user cannot know it's tappable or where it leads.

**Evidence**  
`dashboard_screen.dart:900–923`:
```dart
class _Card extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Material(
      color: ...,
      borderRadius: ...,
      child: InkWell(
        onTap: onTap,  // no semantics wrapper
        ...
```

`_StatTile` at line 329 wraps in `_Card(onTap: onTap)` without a `tooltip` or `Semantics` label.

**UX Principle Violated**  
WCAG 4.1.2 — Name, Role, Value. WCAG 2.4.4 — Link Purpose (In Context).

**Recommendation**  
Add `Semantics` to `_Card` when `onTap` is non-null. Add `tooltip` to `_StatTile` for pointer users.

**Implementation Guidance**  

Update `_Card.build()`:
```dart
child: Semantics(
  button: onTap != null,
  child: InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(12),
    child: Padding(padding: padding, child: child),
  ),
),
```

Update `_StatTile` to pass a semantic label to `_Card`:
```dart
// Add label parameter to _Card:
final String? semanticLabel;
// In _Card.build():
child: Semantics(
  button: onTap != null,
  label: semanticLabel,
  child: InkWell(...),
),
// In _StatTile:
_Card(
  semanticLabel: 'Navigate to $label screen',
  onTap: onTap,
  ...
)
```

For `_LeaderboardRow`:
```dart
return Semantics(
  button: true,
  label: '${entry.name}, rank #${entry.rank}, ${entry.points} points. Tap to view contributions.',
  child: InkWell(onTap: ..., child: ...),
);
```

**Dependencies:** None.

**Expected User Impact:** Screen reader users can navigate the dashboard with full context.

---

### UX-022

**Severity:** Low  
**Confidence:** High

**Location:**  
- `lib/features/inventory/presentation/inventory_screen.dart:728–742`

**Problem**  
Swipe gestures on inventory tiles have no haptic feedback. On Android, standard swipe-to-action patterns (Gmail swipe-to-archive, Todoist swipe-to-complete) provide haptic confirmation when the swipe threshold is crossed. Without it, the action feels uncertain, especially when the tile re-appears instead of animating away (because `confirmDismiss` returns `false`).

**UX Principle Violated**  
Apple HIG and Material Motion — haptic feedback reinforces gesture completion.

**Recommendation**  
Add `HapticFeedback.mediumImpact()` on successful gesture action inside `confirmDismiss`.

**Implementation Guidance**  
```dart
confirmDismiss: (dir) async {
  if (dir == DismissDirection.startToEnd) {
    HapticFeedback.mediumImpact(); // ADD
    await _wrap(context, () => repo.consume(item.id), 'Decremented ${item.productName}');
    ref.invalidate(inventoryListProvider);
  } else if (dir == DismissDirection.endToStart) {
    HapticFeedback.heavyImpact(); // ADD — heavier for more significant action
    await _wrap(context, () => repo.markUsedUp(item.productId), 'Marked ${item.productName} used up');
    ref.invalidate(inventoryListProvider);
  }
  return false;
},
```

Import: `import 'package:flutter/services.dart';` (already imported in some files).

**Dependencies:** None. Requires `flutter/services.dart`.

**Expected User Impact:** Swipe gestures feel responsive and tactile. Reduces "did that work?" uncertainty.

---

### UX-023

**Severity:** Low  
**Confidence:** Medium

**Location:**  
- `lib/features/appshell/app_shell.dart:82–96`  
- All screens with content near bottom

**Problem**  
The AppShell FAB (`floatingActionButton`) renders at a fixed bottom-right position on every screen. On the Inventory screen, content has `SizedBox(height: 32)` at the bottom — but the FAB is 56dp tall + 16dp margin = 72dp from the bottom edge. The content bottom padding (32dp) is insufficient to prevent the FAB from overlapping the last list item. This is less critical given UX-004 recommends removing the FAB, but if the FAB is retained for a future feature, this padding must be corrected.

**UX Principle Violated**  
Material 3 FAB placement — content must be padded to avoid overlap.

**Recommendation**  
If FAB is retained in the future, either: (a) set `floatingActionButtonLocation: FloatingActionButtonLocation.endContained` to embed it in a bottom app bar, or (b) add 88dp bottom padding to all scrollable content. The simplest fix: set `body` with a `SafeArea(bottom: false)` and `ListView(padding: EdgeInsets.only(bottom: 88))`.

**Dependencies:** UX-004 (remove FAB first — this issue is moot until FAB is re-added).

---

### UX-024

**Severity:** Low  
**Confidence:** High

**Location:**  
- All screens with `Scaffold(body: asyncList.when(loading: ..., error: ..., data: ...))`

**Problem**  
Loading states across all screens use a bare `CircularProgressIndicator()` centered on the full screen body. There is no skeleton screen, no shimmer animation, and no timeout fallback. On slow network connections (the primary use case for a local server app), users see an indefinite spinner with no indication of progress or whether the load failed silently.

**UX Principle Violated**  
Nielsen #1 — Visibility of System Status. Material Design Progress Indicators (prefer determinate or skeleton for known-structure content).

**Recommendation**  
For screens whose content structure is known (Inventory, Shopping, Dashboard), add skeleton placeholder cards that match the real content layout. This is a polish-phase improvement — not blocking.

For immediate fix: add a timeout to the loading state that transitions to the error view after 30 seconds:

```dart
// In each AsyncValue.when loading branch:
loading: () => const Center(
  child: Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      CircularProgressIndicator(),
      SizedBox(height: 12),
      Text('Loading...', style: TextStyle(color: Colors.grey)),
    ],
  ),
),
```

**Dependencies:** None for the immediate text addition. Skeleton screens require design work.

**Expected User Impact:** Users understand the app is loading, not frozen.

---

## IMPLEMENTATION ROADMAP

### Phase 1 — Critical Usability Blockers

| ID | Issue | Est. Effort |
|---|---|---|
| UX-004 | Remove FAB "Chat coming soon" dead end | 5 min |
| UX-001 | Resolve nested Scaffold double AppBar | 2–4 hrs |
| UX-003 | Add undo/confirmation to shopping delete | 1 hr |
| UX-002 | Fix medicine tile touch target sizes | 15 min |

### Phase 2 — Accessibility

| ID | Issue | Est. Effort |
|---|---|---|
| UX-010 | Add Semantics to sparkline chart | 30 min |
| UX-015 | Add labelText to search fields | 15 min |
| UX-021 | Add Semantics to tappable cards | 1 hr |
| UX-002 | Touch target fix (listed in Phase 1) | — |

### Phase 3 — Consistency

| ID | Issue | Est. Effort |
|---|---|---|
| UX-007 | Replace hard-coded colors with AppTokens | 1 hr |
| UX-016 | Standardize InputDecoration borders | 30 min |
| UX-017 | Standardize empty states | 2 hrs |
| UX-013 | Add password toggle to DeviceApproval | 15 min |
| UX-020 | Fix date display in session banner | 10 min |
| UX-009 | Replace raw error messages | 1 hr |
| UX-008 | Remove API path from helper text | 5 min |

### Phase 4 — Design System

| ID | Issue | Est. Effort |
|---|---|---|
| UX-005 | Hide placeholder nav destinations | 30 min |
| UX-011 | Replace wide NavigationDrawer with NavigationRail | 2 hrs |
| UX-012 | Fix conditional Navigator.pop() in nav | 15 min |
| UX-018 | Standardize filter controls | 1 hr |
| UX-014 | Configurable currency | 2–4 hrs |

### Phase 5 — Polish

| ID | Issue | Est. Effort |
|---|---|---|
| UX-006 | Swipe gesture discovery hint | 1 hr |
| UX-019 | Add undo to swipe gestures | 2 hrs |
| UX-022 | Add haptic feedback to swipes | 15 min |
| UX-023 | FAB content overlap padding | 15 min |
| UX-024 | Improve loading states | 2–4 hrs |

---

## Summary Statistics

| Severity | Count |
|---|---|
| Critical | 4 |
| High | 8 |
| Medium | 10 |
| Low | 3 |
| **Total** | **25** |

**Quick wins (< 30 min each, high impact):**  
UX-004 (remove dead FAB), UX-008 (remove API path from helperText), UX-013 (password toggle), UX-020 (date format), UX-002 (touch targets), UX-022 (haptic feedback).

**Highest ROI (significant impact, moderate effort):**  
UX-001 (double AppBar — most visually jarring bug), UX-005 (hide placeholder nav), UX-007 (token colors), UX-003 (delete confirmation/undo).
