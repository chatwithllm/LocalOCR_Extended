# FEATURE_PARITY_REGISTRY — Android port

Atomic registry of every interactive UI element in the web app (`src/frontend/index.html`)
mapped to its action verb, backend endpoint, and the planned Android implementation.

Convention
- Verbs: `text-input` `password-input` `number-input` `date-input` `month-input` `file-pick`
  `select` `checkbox` `button` `nav-button` `nav-tap` `tap` `tap-link` `tap-toggle`
  `toggle-collapse` `long-press` `swipe-left` `swipe-right` `drag-slider`
  `hold-alt-action` `hover-popup` `right-click-menu` `keyboard-shortcut`
  `modifier-click` `chip-toggle` `details-summary` `pull-to-refresh`
- Endpoints mirror the backend `url_prefix` exactly (RULE 1/2). `—` = client-only or
  third-party.
- Status: all rows ❌ (not implemented on Android). 🔄/🚫 require a written
  justification in the **Android Impl** column.

Sidebar / global chrome are listed under **Screen: AppShell**. Modals & sheets shared
across screens are under **Screen: SharedModals**.

## Screen: AppShell
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-001 | AppShell | Sidebar collapse button (`‹`) | button | — | `handleSidebarCollapse()` toggles `.collapsed` class | — | ❌ |
| F-002 | AppShell | Sidebar Dashboard item | nav-button | — | `nav('dashboard')` | — | ❌ |
| F-003 | AppShell | Sidebar Inventory item | nav-button | — | `nav('inventory')` | — | ❌ |
| F-004 | AppShell | Sidebar Products item | nav-button | — | `nav('products')` | — | ❌ |
| F-005 | AppShell | Sidebar Medicine item | nav-button | — | `nav('medicine')` | — | ❌ |
| F-006 | AppShell | Sidebar Upload Receipt item | nav-button | — | `nav('upload')` | — | ❌ |
| F-007 | AppShell | Sidebar Receipts item | nav-button | — | `nav('receipts')` | — | ❌ |
| F-008 | AppShell | Sidebar Shopping List item | nav-button | — | `nav('shopping')` | — | ❌ |
| F-009 | AppShell | Sidebar Kitchen item | nav-button | — | `nav('kitchen')` | — | ❌ |
| F-010 | AppShell | Sidebar Restaurant item (admin-conditional) | nav-button | — | `nav('restaurant')` | — | ❌ |
| F-011 | AppShell | Sidebar Balances item | nav-button | — | `nav('balances')` | — | ❌ |
| F-012 | AppShell | Sidebar Contacts item | nav-button | — | `nav('contacts')` | — | ❌ |
| F-013 | AppShell | Sidebar Expenses item | nav-button | — | `nav('expenses')` | — | ❌ |
| F-014 | AppShell | Sidebar Budget item | nav-button | — | `nav('budget')` | — | ❌ |
| F-015 | AppShell | Sidebar Bills item | nav-button | — | `nav('bills')` | — | ❌ |
| F-016 | AppShell | Sidebar Accounts item | nav-button | — | `nav('accounts')` | — | ❌ |
| F-017 | AppShell | Sidebar Analytics item | nav-button | — | `nav('analytics')` | — | ❌ |
| F-018 | AppShell | Sidebar Contribution item | nav-button | — | `nav('contributions')` | — | ❌ |
| F-019 | AppShell | Sidebar Features (external) | button | — | `window.open('/features','_blank')` opens new tab; on Android open in webview/browser | — | ❌ |
| F-020 | AppShell | Sidebar Settings item | nav-button | — | `nav('settings')` | — | ❌ |
| F-021 | AppShell | Theme toggle (☀️/🌙) | button | — | `toggleTheme()` cycles light/dark | — | ❌ |
| F-022 | AppShell | Mobile menu hamburger (`☰`) | button | — | `toggleMobileMenu()` | — | ❌ |
| F-023 | AppShell | Mobile brand title (long-press secret) | long-press | — | `mobile-brand-secret-trigger` reveals design gallery | 🚫 prod (dev-flavor debug-only); guarded by `kDebugMode && flavor == 'dev'` so production users cannot reveal the design gallery. F-030 (Design Gallery target) is already 🚫; secret trigger follows. V-8 RESOLVED via §7.2 default recommendation. | 🚫 |
| F-024 | AppShell | Brand title (desktop secret) | long-press | — | `brand-secret-trigger` reveals design gallery | 🚫 prod (dev-flavor debug-only); same guard as F-023. V-8 RESOLVED via §7.2 default recommendation. | 🚫 |
| F-025 | AppShell | Toast / action-toast surface | tap | — | `action-toast` shows Undo + countdown | — | ❌ |
| F-026 | AppShell | Confirm dialog overlay (`confirm-overlay`) | button | — | Shared yes/no modal driven by `askForConfirmation()` | — | ❌ |
| F-027 | AppShell | Manual entry overlay (`manual-entry-overlay`) | button | — | Shared modal for cash/bill manual entry | — | ❌ |
| F-028 | AppShell | Edge-pull overscroll nav gesture | swipe-up/swipe-down | — | `setOverscrollNavEnabled` setting; pulls past top/bottom to jump pages | — | ❌ |
| F-029 | AppShell | Alt+← / Alt+→ keyboard nav | keyboard-shortcut | — | Jump previous/next sidebar page | — | ❌ |
| F-030 | AppShell | `g g` keyboard sequence → Design Gallery | keyboard-shortcut | — | Dev-only | — | 🚫 dev-only gallery; out of scope for Android |
| F-031 | AppShell | URL hash routing (#dashboard, #inventory, …) | nav-tap | — | `location.hash` drives `nav()` | — | 🔄 Android uses deep-link intents instead of hashes — equivalent behavior |
| F-032 | AppShell | Chat FAB (`chat-fab`) | button | — | Floating assistant button | — | ❌ |
| F-033 | AppShell | Chat panel close (X) | button | — | Hides `chat-panel` | — | ❌ |
| F-034 | AppShell | Chat clear conversation (`chat-clear-btn`) | button | POST `/chat/messages` (DELETE-style)| Clears `_renderChatThread()` | — | ❌ |
| F-035 | AppShell | Chat minimize (`chat-minimize-btn`) | button | — | Collapse chat panel | — | ❌ |
| F-036 | AppShell | Chat resize handle | drag | — | `chat-panel-resize-handle` | — | 🔄 Android uses full-screen / sheet sizing instead of drag handle |
| F-037 | AppShell | Chat input field | text-input | — | `chat-input` | — | ❌ |
| F-038 | AppShell | Chat send button | button | POST `/chat/messages` | `chat-send-btn` | — | ❌ |

## Screen: Login
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-101 | Login | Email field (`auth-email-input`) | text-input | — | `<input type=text placeholder=Email>` | `TextField` w/ `Key('auth-email-input')`, AutofillHints.username | ✅ |
| F-102 | Login | Password field (`auth-password-input`) | password-input | — | `<input type=password>` | `TextField obscureText` w/ `Key('auth-password-input')`, AutofillHints.password | ✅ |
| F-103 | Login | Show-password eye (`auth-password-toggle`) | button | — | `toggleLoginPasswordVisibility()` flips input type | `IconButton` toggles `_showPass` setState; key `auth-password-toggle` | ✅ |
| F-104 | Login | Login button | button | POST `/auth/login` | `login()` posts JSON `{email,password}` | `FilledButton` → `AuthRepository.login()` → sessionProvider; appLogger `loaded 1 session` | ✅ |
| F-105 | Login | "Sign in with Google" anchor (`auth-google-btn`) | tap-link | GET `/auth/oauth/google` | Visible only when google_oauth_enabled | 🔄 deferred per pubspec NOTE — WebView OAuth cookie capture needs `flutter_inappwebview` (blocked by AGP 9 proguard-android.txt) or `flutter_web_auth_2` fallback (plan §4 BL-A7). Button rendered when bootstrap reports `googleOauthEnabled=true` and currently surfaces a "coming soon" SnackBar. | 🔄 |
| F-106 | Login | Google button hover shadow | hover-popup | — | inline `onmouseover`/`onmouseout` | — | 🔄 desktop hover; Android tap ripple equivalent |
| F-107 | Login | "Pair This Device" button | button | POST `/auth/device-pairing/start` | `openDevicePairingModal()` opens device pairing modal | `OutlinedButton` → `showModalBottomSheet` → `_DevicePairingSheet` posts /auth/device-pairing/start + Timer.periodic polls /auth/device-pairing/status every 2s, terminates on approved/claimed/rejected/expired | ✅ |
| F-108 | Login | "Forgot Password?" button | button | POST `/auth/forgot-password` | `requestPasswordReset()` | `TextButton` → `AuthRepository.forgotPassword(email)` + SnackBar confirmation | ✅ |
| F-109 | Login | Invite landing overlay (`invite-landing`) | button | GET `/auth/invite/<token>` | Shown when `?invite=...` in URL | `_InviteLandingCard` shown above Sign-in card when `LoginScreen.inviteToken` non-empty (router maps `/invite/:token` and `/login?invite=...`) | ✅ |
| F-110 | Login | Invite landing "Sign in with Google" | tap-link | GET `/auth/oauth/google` | `invite-google-btn` | 🔄 same defer as F-105 — button renders inside `_InviteLandingCard` with key `invite-google-btn` and shows the same SnackBar. Will reuse the F-105 webview once unblocked. | 🔄 |
| F-111 | Login | Invite landing Dismiss button | button | — | Hides overlay | `TextButton('Dismiss')` flips `_inviteVisible=false` via setState | ✅ |
| F-112 | Login | Device-approval inline card title pill | tap | GET `/auth/device-pairing/status/<token>` | Status pill (`person-modal-pill confirmed`) | `Container` "Device awaiting approval" pill at top of `_DeviceApprovalInlineCard`; live status polled within `_DevicePairingSheet` mirror path | ✅ |
| F-113 | Login | Device-approval Device Name input | text-input | — | `device-approval-inline-name` | `TextField` key `device-approval-inline-name` feeding `devicePairingApprove(deviceName:)` | ✅ |
| F-114 | Login | Device-approval Linked User select | select | GET `/auth/users` | `device-approval-inline-linked-user` | 🔄 numeric `TextField` fallback (key `device-approval-inline-linked-user`) — `/auth/users` requires admin auth which Login screen lacks; backend coalesces empty → admin actor id. Once admin is logged in elsewhere this can upgrade to a populated dropdown. | 🔄 |
| F-115 | Login | Device-approval Scope select | select | — | shared_household / kitchen_display / read_only | `DropdownButtonFormField` key `device-approval-inline-scope` with three fixed scopes | ✅ |
| F-116 | Login | Device-approval Admin Email input | text-input | — | `device-approval-inline-email` | `TextField` key `device-approval-inline-email` feeding `admin_email` body field | ✅ |
| F-117 | Login | Device-approval Admin Password input | password-input | — | `device-approval-inline-password` | `TextField obscureText` key `device-approval-inline-password` feeding `admin_password` body field | ✅ |
| F-118 | Login | Device-approval Reject button | button | POST `/auth/device-pairing/reject` | `rejectPendingDevicePairing()` | `OutlinedButton('Reject')` → `AuthRepository.devicePairingReject(...)` | ✅ |
| F-119 | Login | Device-approval Approve button | button | POST `/auth/device-pairing/approve` | `approvePendingDevicePairing()` | `FilledButton('Approve')` → `AuthRepository.devicePairingApprove(...)` w/ optional linked_user_id + scope + device_name | ✅ |
| F-120 | Login | Bootstrap-info fetch on mount | (lifecycle) | GET `/auth/bootstrap-info` + GET `/auth/app-config` | Decides which auth options to show | `_bootstrap()` in `initState` calls `AuthRepository.bootstrap()`, prefills default_email, drives `_googleEnabled` flag; appLogger `login bootstrap loaded` | ✅ |
---

## Screen: Dashboard
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-201 | Dashboard | Page header H1 + subtitle | display | — | "Dashboard / Your household system at a glance" | `_DashboardHeader` — "Dashboard" headline + "Your household system at a glance" subtitle; key `dashboard-h1` | ✅ |
| F-202 | Dashboard | Demo hero "Sign In" button | button | — | `focusLogin()` (read-only demo mode only) | 🔄 demo hero unreachable on Android — router redirects unauthenticated users straight to `/login` before dashboard mounts. No anonymous/demo state on Android v1; logged-in users see the real cards instead. | 🔄 |
| F-203 | Dashboard | Demo hero "Shopping Demo" button | button | — | `goToPage('shopping')` | 🔄 same demo-hero reason as F-202 | 🔄 |
| F-204 | Dashboard | Demo hero "Restaurant Demo" button | button | — | `goToPage('restaurant')` | 🔄 same demo-hero reason as F-202 | 🔄 |
| F-205 | Dashboard | Demo hero "Grocery / Restaurant / Expenses" mini cards | display | — | Three static cards | 🔄 same demo-hero reason as F-202 | 🔄 |
| F-206 | Dashboard | Demo read-only note | display | — | Static text | 🔄 same demo-hero reason as F-202 | 🔄 |
| F-207 | Dashboard | Leaderboard title (`dashboard-leaderboard-title`) | display | GET `/contributions/summary` | `renderLeaderboard()` (V-fix: web also calls `/contributions/summary`, not `/contributions/leaderboard` — confirmed at `index.html:11618`) | `_LeaderboardCard` Row with `Icons.emoji_events_outlined` + "Household contributions" title; key `dashboard-leaderboard-title` | ✅ |
| F-208 | Dashboard | Leaderboard collapsed preview surface | tap | — | `handleLeaderboardSurfaceTap()` | `InkWell` wrapping top-3 rows in `_LeaderboardCard`; tap toggles `dashboardSectionExpandedProvider('leaderboard')`; key `dashboard-leaderboard-preview` | ✅ |
| F-209 | Dashboard | Leaderboard "Show full ranking" button | button | — | `toggleLeaderboard()` | `TextButton` "Show full ranking" / "Collapse" toggling expanded provider; key `dashboard-leaderboard-toggle` | ✅ |
| F-210 | Dashboard | Leaderboard full list row tap | tap | — | per-row navigate | `_LeaderboardRow` `InkWell.onTap` → `GoRouter.go('/contributions')` | ✅ |
| F-211 | Dashboard | Attribution nudge "Tag now →" link | tap | — | `navToReceiptsUntagged()` → Receipts screen with `untagged_only` filter | `_AttributionNudge` shows when `activity.total > 0`; `TextButton "Tag now →"` → `GoRouter.go('/receipts?untagged_only=1')` | ✅ |
| F-212 | Dashboard | Low stat tile (`stat-low-inline`) | tap | — | `openDashboardStat('low-stock')` → Inventory low_first | `_StatTile` key `stat-low-inline`; tap → `GoRouter.go('/inventory?group_by=low_first')` | ✅ |
| F-213 | Dashboard | Inv stat tile (`stat-inv-inline`) | tap | GET `/inventory` | `openDashboardStat('inventory')` | `_StatTile` key `stat-inv-inline`; tap → `GoRouter.go('/inventory')`; count from `InventoryStats.itemCount` | ✅ |
| F-214 | Dashboard | Prod stat tile (`stat-products-inline`) | tap | GET `/products` | `openDashboardStat('products')` | `_StatTile` key `stat-products-inline`; tap → `GoRouter.go('/products')`; total from `ProductsStats.total` | ✅ |
| F-215 | Dashboard | Dashboard stat tile Enter/Space keyboard | keyboard-shortcut | — | `handleDashboardStatKey()` | — | 🔄 hardware-keyboard rare on Android; touch covers verb |
| F-216 | Dashboard | Spending-by-Category title (collapse toggle) | tap-toggle | GET `/analytics/spending-by-category` | `toggleDashboardSpendingCard()` | `_SpendingByCategoryCard` `InkWell` header toggles `dashboardSectionExpandedProvider('spending')`; key `dashboard-spending-toggle` | ✅ |
| F-217 | Dashboard | Spending-by-Category total inline stat | display | — | `dashboard-spending-total` | `Text` in `_SpendingByCategoryCard` header showing `$X.XX`; key `dashboard-spending-total` | ✅ |
| F-218 | Dashboard | Spending-by-Category row tap → drill panel | tap | — | `_renderSpendingDrillPanel(category)` | `_SpendingRow` `InkWell.onTap` → `GoRouter.go('/analytics?category=…')` | ✅ |
| F-219 | Dashboard | Spending-by-Category "Show more" toggle button | button | — | `toggleDashboardSpendingMore()` | `TextButton` "Show more / Show less" bound to `dashboardSpendingMoreProvider`; shows when categories > 6; key `dashboard-spending-more` | ✅ |
| F-220 | Dashboard | Low Stock card title | display | — | "⚠️ Low Stock" | `Text("⚠️  Low Stock")` in `_LowStockCard` header | ✅ |
| F-221 | Dashboard | Low Stock count chip | tap-toggle | — | `toggleDashboardSection('low-stock')` | `Container` chip in `_LowStockCard` header; entire row InkWell toggles `dashboardSectionExpandedProvider('low-stock')`; key `dashboard-low-chip` | ✅ |
| F-222 | Dashboard | Low Stock list row tap | tap | — | Opens inventory item / Add to shopping | "Open Inventory to triage →" `InkWell` → `GoRouter.go('/inventory?group_by=low_first')`; per-item rows live on Inventory screen | ✅ |
| F-223 | Dashboard | Receipts Processed card title (collapse) | tap-toggle | — | `toggleDashboardSection('receipts-activity')` | `_ReceiptsActivityCard` `InkWell` header toggles `dashboardSectionExpandedProvider('activity')` | ✅ |
| F-224 | Dashboard | Receipts Processed grain Day button | chip-toggle | GET `/analytics/receipts-activity?grain=day` | `setReceiptsActivityGrain('day')` | `ChoiceChip` "Day" key `activity-grain-day` bound to `receiptsActivityGrainProvider`; auto-refetches via `dashboardStateProvider` | ✅ |
| F-225 | Dashboard | Receipts Processed grain Week button | chip-toggle | GET `/analytics/receipts-activity?grain=week` | `setReceiptsActivityGrain('week')` | `ChoiceChip` "Week" key `activity-grain-week` | ✅ |
| F-226 | Dashboard | Receipts Processed grain Month button | chip-toggle | GET `/analytics/receipts-activity?grain=month` | `setReceiptsActivityGrain('month')` | `ChoiceChip` "Month" key `activity-grain-month` | ✅ |
| F-227 | Dashboard | Receipts Processed chart body | display | — | `_renderReceiptsActivityChart()` SVG sparkline | `_Sparkline` → `CustomPaint(_SparkPainter)` drawing line over `activity.buckets` counts | ✅ |
| F-228 | Dashboard | Top Picks (recommendations) card | tap-toggle | GET `/recommendations` | `toggleDashboardSection('recommendations')`; `loadRecs('dash-recs')` | `_TopPicksCard` `InkWell` header toggles `dashboardSectionExpandedProvider('recs')` | ✅ |
| F-229 | Dashboard | Top Picks row Add-to-list button | button | POST `/shopping-list/items` | per-rec action | `IconButton` `Icons.add_shopping_cart` per `_RecRow`; key `rec-add-<id>`; → `DashboardRepository.addRecommendationToList` → POST `/shopping-list/items` with SnackBar feedback | ✅ |
| F-230 | Dashboard | Shopping List summary card title (link) | tap | — | `openDashboardStat('shopping')` | `_ShoppingSummaryCard` header `InkWell.onTap` → `GoRouter.go('/shopping')`; key `dashboard-shopping-title` | ✅ |
| F-231 | Dashboard | Shopping List header count chip | display | — | `dash-shopping-header-count` | `Container` chip showing `shopping.openCount`; key `dash-shopping-header-count` | ✅ |
| F-232 | Dashboard | Shopping List Estimate button | tap-toggle | — | `toggleDashboardShoppingPreview()` reveals preview list | `TextButton` "Estimate / Hide preview" toggling `dashboardShoppingPreviewExpandedProvider`; key `dashboard-shopping-preview-toggle` | ✅ |
| F-233 | Dashboard | Shopping List preview row tap | tap | — | navigate to shopping with item highlighted | `ListTile.onTap` → `GoRouter.go('/shopping?item_id=…')` | ✅ |
| F-234 | Dashboard | Floor Obligations hidden card | display | — | Hidden shell — superseded by Spending by Category | — | 🚫 hidden in web; do not port |
---

## Screen: Inventory
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-301 | Inventory | Add Item card "Hide" toggle | button | — | `toggleInventoryAddCard()` | — | ❌ |
| F-302 | Inventory | Product Name input (`inv-name`) | text-input | — | `handleInventoryAddNameInput()` autocomplete | — | ❌ |
| F-303 | Inventory | Quantity input (`inv-qty`) | number-input | — | min 0 step 0.1 | — | ❌ |
| F-304 | Inventory | Location select (`inv-loc`) | select | — | Pantry/Fridge/Freezer/Cabinet/Laundry/Custom | — | ❌ |
| F-305 | Inventory | Custom location input | text-input | — | shown when `Custom…` selected | — | ❌ |
| F-306 | Inventory | Low-Stock Threshold input | number-input | — | `inv-thresh` | — | ❌ |
| F-307 | Inventory | "More details" toggle | button | — | `toggleInventoryAddDetails()` | — | ❌ |
| F-308 | Inventory | Category select | select | — | populated by `renderInventoryManualCategoryOptionTags` | — | ❌ |
| F-309 | Inventory | Unit chip row | chip-toggle | — | `inv-unit-chip-row` (each/lb/oz/ml/...); persists hidden `inv-unit` | — | ❌ |
| F-310 | Inventory | Preferred Store select | select | GET `/api/stores` | `inv-preferred-store` | — | ❌ |
| F-311 | Inventory | "Add to shopping too" checkbox | checkbox | — | `inv-add-to-shopping` | — | ❌ |
| F-312 | Inventory | "➕ Add to Inventory" button | button | POST `/inventory` | `addInventoryItem()` | — | ❌ |
| F-313 | Inventory | Inline product creation form (shared) | text-input + select + button | POST `/products` | `add-prod-form-shared` (hidden when not needed) | — | ❌ |
| F-314 | Inventory | Inventory search input (`inventory-search`) | text-input | — | filters local cache | — | ❌ |
| F-315 | Inventory | Location filter select | select | — | All / Fridge / Freezer / Pantry / Cabinet / Bathroom | — | ❌ |
| F-316 | Inventory | Group-by select (`inventory-group-by`) | select | — | low_first / domain / location | — | ❌ |
| F-317 | Inventory | Sort select | select | — | expiry / name / qty | — | ❌ |
| F-318 | Inventory | "Show empty" checkbox | checkbox | — | `inventory-show-empty` | — | ❌ |
| F-319 | Inventory | "↻ Recently used up" button | button | GET `/inventory/recently-used-up?days=30` | `invOpenRestoreModal()` | — | ❌ |
| F-320 | Inventory | "🔗 Merge duplicates" button | button | POST `/products/merge-duplicates` | `findDuplicateProducts()` | — | ❌ |
| F-321 | Inventory | Category chip row (`inv-category-chips`) | chip-toggle | — | `renderInvCategoryChips()` toggles `invCategoryFilters` set | — | ❌ |
| F-322 | Inventory | Low badge (`inv-low-badge`) | display | — | "N running low" pill in header | — | ❌ |
| F-323 | Inventory | Inventory window note | display | — | `inv-window-note` | — | ❌ |
| F-324 | Inventory | Bulk-bar "−1 all" button | button | PATCH `/inventory/products/<id>` (per-id) | `invBulkDecrement()` | — | ❌ |
| F-325 | Inventory | Bulk-bar "+3d all" button | button | PATCH `/inventory/products/<id>` defer_days=3 | `invBulkDefer(3)` | — | ❌ |
| F-326 | Inventory | Bulk-bar "+7d all" button | button | PATCH `/inventory/products/<id>` defer_days=7 | `invBulkDefer(7)` | — | ❌ |
| F-327 | Inventory | Bulk-bar "✓ Used up all" button | button | PATCH `/inventory/products/<id>/consume` | `invBulkUsedUp()` (sheet with optional shopping-add) | — | ❌ |
| F-328 | Inventory | Bulk-bar Clear button | button | — | `invBulkClear()` | — | ❌ |
| F-329 | Inventory | Bulk-bar undo toast | button | PATCH (snapshot restore) | `invUndoBulk()` 5s grace | — | ❌ |
| F-330 | Inventory | Group header label (emoji + name + count) | display | — | `_invBuildGroup()` head row | — | ❌ |
| F-331 | Inventory | Group "expiring soon" inline count | display | — | shown when ≥1 item exp-soon | — | ❌ |
| F-332 | Inventory | Tile checkmark badge (selection visual) | display | — | `inv-tile-checkmark` CSS-driven on `.selected` | — | ❌ |
| F-333 | Inventory | Tile product image (admin only) | display | GET `/product-snapshots/...` | `inv-tile-img` cache-busted | — | ❌ |
| F-334 | Inventory | Tile days-left label | display | — | "Nd left" / "EXPIRED Nd ago" / "no expiry" | — | ❌ |
| F-335 | Inventory | Tile MM/DD → MM/DD range (mobile) | display | — | `inv-tile-range` with user/defer tags | — | ❌ |
| F-336 | Inventory | Tile quantity pill (×N unit) | display | — | `inv-tile-qty` | — | ❌ |
| F-337 | Inventory | Tile remaining-pct fill bar | display | — | CSS ::before behind name row, `--remaining-pct` | — | ❌ |
| F-338 | Inventory | Tile drag bubble (% readout) | display | — | `inv-drag-bubble` shown while dragging | — | ❌ |
| F-339 | Inventory | Tile drag handle (% slider) | drag-slider | PATCH `/inventory/products/<id>` consumed_pct_override | `inv-drag-handle` role=slider | — | ❌ |
| F-340 | Inventory | Tile −10% stepper button | button | PATCH `/inventory/products/<id>` consumed_pct_override | `_applyStep(-10)` | — | ❌ |
| F-341 | Inventory | Tile +10% stepper button | button | PATCH `/inventory/products/<id>` consumed_pct_override | `_applyStep(10)` | — | ❌ |
| F-342 | Inventory | Tile title row tap (status cycle) | tap | PATCH `/inventory/<id>/status` | `_invCycleStatus(id, status)` | — | ❌ |
| F-343 | Inventory | Tile name display | display | — | `inv-tile-name` | — | ❌ |
| F-344 | Inventory | Tile `~est` suffix | display | — | When expiry estimated | — | ❌ |
| F-345 | Inventory | Tile meta: 📅 Bought | display | — | `last_purchased_at` | — | ❌ |
| F-346 | Inventory | Tile meta: 🍂 Expires + user/defer tag | display | — | `expires_at` with source badge | — | ❌ |
| F-347 | Inventory | Tile meta: 💊 medication link | display | — | when product is linked to a medication | — | ❌ |
| F-348 | Inventory | Tile ✎ edit button | button | — | opens `editProductDetails()` sheet | — | ❌ |
| F-349 | Inventory | Tile +3d defer button | button | PATCH `/inventory/products/<id>` defer_days=3 | `invDefer(id,3)` | — | ❌ |
| F-350 | Inventory | Tile +3d hold → +7d alt action | hold-alt-action | PATCH `/inventory/products/<id>` defer_days=7 | `_invAttachButtonHold` 500ms | — | ❌ |
| F-351 | Inventory | Tile 🛒 cart button | button | POST `/shopping-list/items` | `invAddToShoppingList()` | — | ❌ |
| F-352 | Inventory | Tile −1 decrement button | button | PATCH `/inventory/products/<id>` quantity | `invDecrement()` optimistic | — | ❌ |
| F-353 | Inventory | Tile ✓ used-up / clear-low button | button | PATCH `/inventory/products/<id>/consume` (or clear-low) | smart based on `is_low/manual_low` | — | ❌ |
| F-354 | Inventory | Tile ✓ hold → cart + used alt action | hold-alt-action | POST `/shopping-list/items` + PATCH consume | `_invAttachButtonHold` | — | ❌ |
| F-355 | Inventory | Tile ✨ AI gen image (admin, no image) | button | POST `/product-snapshots/generate` | `invGenerateTileImage()` | — | ❌ |
| F-356 | Inventory | Tile 🗑 delete (only in variants) | button | DELETE `/products/<id>` | per-row danger | — | ❌ |
| F-357 | Inventory | Tile swipe-right → −1 | swipe-right | PATCH `/inventory/products/<id>` quantity | mobile gesture | — | ❌ |
| F-358 | Inventory | Tile swipe-left → used-up | swipe-left | PATCH `/inventory/products/<id>/consume` | mobile gesture | — | ❌ |
| F-359 | Inventory | Tile long-press → enter selection | long-press | — | 500ms; vibrates 40ms | — | ❌ |
| F-360 | Inventory | Tile tap (mobile) → expand details | tap | — | `.expanded` toggle when not in selection mode | — | ❌ |
| F-361 | Inventory | Tile right-click context menu (long-press payload) | right-click-menu | — | `invHandleContextMenu(event, payload)` | — | 🔄 Android long-press already covers this; right-click absent |
| F-362 | Inventory | Edit product sheet — Name field | text-input | PUT `/products/<id>/update` | `editProductDetails()` modal | — | ❌ |
| F-363 | Inventory | Edit product sheet — 📷 photo picker | file-pick | POST `/product-snapshots/upload` | inline file input | — | ❌ |
| F-364 | Inventory | Edit product sheet — photo gallery delete (×) | button | DELETE `/product-snapshots/<id>` | per-thumbnail | — | ❌ |
| F-365 | Inventory | Edit product sheet — photo gallery promote (tap thumb) | tap | POST `/product-snapshots/<id>/promote` | tap non-primary thumb | — | ❌ |
| F-366 | Inventory | Edit product sheet — Category select | select | PUT `/products/<id>/update` | category picker | — | ❌ |
| F-367 | Inventory | Edit product sheet — Cancel button | button | — | `close(null)` | — | ❌ |
| F-368 | Inventory | Edit product sheet — Save button | button | PUT `/products/<id>/update` | merged toast on collision | — | ❌ |
| F-369 | Inventory | Recently-used-up section "Hide" | button | — | `invCloseRestoreModal()` | — | ❌ |
| F-370 | Inventory | Restore tile image (admin only) | display | — | `_invBuildRestoreTile()` | — | ❌ |
| F-371 | Inventory | Restore tile date / qty / name / category | display | — | static meta | — | ❌ |
| F-372 | Inventory | Restore tile ↻ Restore button | button | POST `/inventory/products/<id>/restore` | `_invRestoreOne()` | — | ❌ |
| F-373 | Inventory | Restore tile 🛒 "Add to list" / "On list" toggle | button | POST `/shopping-list/items` | `_invRestoreAddToList()` | — | ❌ |
| F-374 | Inventory | Product snapshot file input (hidden) | file-pick | POST `/product-snapshots/upload` | `uploadProductSnapshotFromPicker()` | — | ❌ |
---

## Screen: Products
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-401 | Products | Add Product — Name input (`prod-name`) | text-input | — | `createProduct()` payload | — | ❌ |
| F-402 | Products | Add Product — Category select (`prod-cat`) | select | — | 12 fixed options | — | ❌ |
| F-403 | Products | Add Product — Barcode input (`prod-barcode`) | text-input | — | optional UPC | — | ❌ |
| F-404 | Products | Add Product — "➕ Add Product" button | button | POST `/products/create` | `createProduct()` | — | ❌ |
| F-405 | Products | Catalog count (`prod-count`) | display | — | total products | — | ❌ |
| F-406 | Products | Catalog search (`prod-search`) | text-input | — | `searchProducts()` debounce 300ms | — | ❌ |
| F-407 | Products | Catalog sort select | select | — | `setProductSort()` name_asc/category_asc/variants_desc/recent_desc | — | ❌ |
| F-408 | Products | Catalog refresh button (🔄) | button | GET `/products` | `loadProducts()` | — | ❌ |
| F-409 | Products | Category chip row (`prod-category-chips`) | chip-toggle | — | `renderProductCategoryChips()` | — | ❌ |
| F-410 | Products | Group header (🏷️ Category · N products) | display | — | `renderProductTiles()` group | — | ❌ |
| F-411 | Products | Product tile image (admin only) | display | GET `/product-snapshots/...` | snap-driven | — | ❌ |
| F-412 | Products | Product tile category label + Low badge | display | — | head row | — | ❌ |
| F-413 | Products | Product tile ×count pill | display | — | variants count | — | ❌ |
| F-414 | Products | Product tile name (⭐ regular-use prefix) | display | — | `is_regular_use` adds star | — | ❌ |
| F-415 | Products | Product tile latest purchase 📅 | display | — | `latestPurchase` | — | ❌ |
| F-416 | Products | Product tile variant examples line | display | — | first 2 examples + `…` | — | ❌ |
| F-417 | Products | Product tile ✎ edit button | button | PUT `/products/<id>/update` | `editProductDetails()` | — | ❌ |
| F-418 | Products | Product tile 🛒 add-to-list | button | POST `/shopping-list/items` | `quickAddToShoppingList()` | — | ❌ |
| F-419 | Products | Product tile ✨ AI generate image (admin/no image) | button | POST `/product-snapshots/generate` | `invGenerateTileImage()` | — | ❌ |
| F-420 | Products | Product tile 🗑 delete | button | DELETE `/products/<id>` | confirm dialog | — | ❌ |
| F-421 | Products | Product tile ▾ N expand (variants > 1) | tap-toggle | — | `_toggleProductVariants()` | — | ❌ |
| F-422 | Products | Variant detail row name + Low badge | display | — | inline detail | — | ❌ |
| F-423 | Products | Variant detail row size / bought meta | display | — | `default_size_label`, `last_purchase_date` | — | ❌ |
| F-424 | Products | Variant detail "mini-link" receipt buttons | tap | GET `/receipts/<id>` | `openReceiptDetail()` | — | ❌ |
| F-425 | Products | Variant detail ✎ Edit button | button | PUT `/products/<id>/update` | `editProductDetails()` | — | ❌ |
| F-426 | Products | Variant detail 🛒 Add | button | POST `/shopping-list/items` | `quickAddToShoppingList()` | — | ❌ |
| F-427 | Products | Variant detail 🗑 delete | button | DELETE `/products/<id>` | per-variant | — | ❌ |
| F-428 | Products | Variant rename ✏️ button | button | PUT `/products/<id>/update` | `renameProduct()` text prompt | — | ❌ |
| F-429 | Products | Variant 📷 photo button | file-pick | POST `/product-snapshots/upload` | `selectProductSnapshotFile()` | — | ❌ |
| F-430 | Products | Variant 🖼 view photo | tap | — | `openProductSnapshot()` zoom overlay | — | ❌ |
| F-431 | Products | Variant Set Low / Clear Low button | button | PATCH `/products/<id>/low-status` | `setProductLowStatus()` | — | ❌ |
| F-432 | Products | Variant Unit select | select | PATCH `/products/<id>/unit-defaults` | inline select | — | ❌ |
| F-433 | Products | Variant Size Label input | text-input | PATCH `/products/<id>/unit-defaults` | `updateProductUnitDefaults()` | — | ❌ |
| F-434 | Products | Variant Save (unit/size) button | button | PATCH `/products/<id>/unit-defaults` | | — | ❌ |
| F-435 | Products | Variant Category change select | select | PUT `/products/<id>/category` | `updateProductCategory()` | — | ❌ |
---

## Screen: Medicine
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-501 | Medicine | Page header (H1 + subtitle) | display | — | static | — | ❌ |
| F-502 | Medicine | "+ Add Medication" button | button | — | `openAddMedicationSheet()` | — | ❌ |
| F-503 | Medicine | "👥 Members" button | button | — | `openMembersSheet()` | — | ❌ |
| F-504 | Medicine | Filter status select | select | GET `/medications?status=...` | active / all / expired / finished | — | ❌ |
| F-505 | Medicine | Member chip "All" | chip-toggle | — | `__medicineMemberFilter=null` | — | ❌ |
| F-506 | Medicine | Member chip per person/user/household | chip-toggle | GET `/medications?member_id=...|user_id=...` | `_renderMedicineMemberChips()` | — | ❌ |
| F-507 | Medicine | Med tile image (admin only) | display | GET `/medications/<id>/photo` | `_buildMedTile()` | — | ❌ |
| F-508 | Medicine | Med tile age-group label | display | — | 👶 / 🧑 / 👪 | — | ❌ |
| F-509 | Medicine | Med tile Expired / Low badge | display | — | `is_expired` / `is_low` | — | ❌ |
| F-510 | Medicine | Med tile ×qty pill | display | — | with unit suffix when ≠count | — | ❌ |
| F-511 | Medicine | Med tile name + strength | display | — | "Name · strength" | — | ❌ |
| F-512 | Medicine | Med tile 🍂 Exp date | display | — | `expiry_date` | — | ❌ |
| F-513 | Medicine | Med tile member/household label | display | — | shows belongs-to person or 🏠 Household | — | ❌ |
| F-514 | Medicine | Med tile ⚠️ AI warning line | display | — | `ai_warnings[0]` | — | ❌ |
| F-515 | Medicine | Med tile ✎ edit button | button | — | `openEditMedicationSheet(med)` | — | ❌ |
| F-516 | Medicine | Med tile ✓ Done button (active only) | button | PUT `/medications/<id>` status=finished | `_medMarkFinished()` | — | ❌ |
| F-517 | Medicine | Med tile 🗑 delete button | button | DELETE `/medications/<id>` | `_medDelete()` confirm | — | ❌ |
| F-518 | Medicine | Add/Edit sheet — name * | text-input | POST/PUT `/medications` | required | — | ❌ |
| F-519 | Medicine | Add/Edit sheet — active ingredient | text-input | POST/PUT `/medications` | — | — | ❌ |
| F-520 | Medicine | Add/Edit sheet — brand | text-input | POST/PUT `/medications` | — | — | ❌ |
| F-521 | Medicine | Add/Edit sheet — strength | text-input | POST/PUT `/medications` | — | — | ❌ |
| F-522 | Medicine | Add/Edit sheet — dosage form select | select | POST/PUT `/medications` | tablet/capsule/liquid/cream/spray/patch/other | — | ❌ |
| F-523 | Medicine | Add/Edit sheet — age group select | select | POST/PUT `/medications` | both/adult/child | — | ❌ |
| F-524 | Medicine | Add/Edit sheet — Belongs To select | select | POST/PUT `/medications` user_id/member_id | household + people | — | ❌ |
| F-525 | Medicine | Add/Edit sheet — quantity number | number-input | POST/PUT `/medications` | — | — | ❌ |
| F-526 | Medicine | Add/Edit sheet — unit select | select | POST/PUT `/medications` | tablets/capsules/ml/oz/count/doses | — | ❌ |
| F-527 | Medicine | Add/Edit sheet — expiry date | date-input | POST/PUT `/medications` | — | — | ❌ |
| F-528 | Medicine | Add/Edit sheet — manufacture date | date-input | POST/PUT `/medications` | — | — | ❌ |
| F-529 | Medicine | Add/Edit sheet — barcode | text-input | POST/PUT `/medications` | — | — | ❌ |
| F-530 | Medicine | Add/Edit sheet — notes | text-input | POST/PUT `/medications` | — | — | ❌ |
| F-531 | Medicine | Add sheet — 📷 Camera scan | file-pick | POST `/medications/barcode-lookup` | `_handleScanFile()` Html5Qrcode | — | ❌ |
| F-532 | Medicine | Add sheet — 🖼 Gallery scan | file-pick | POST `/medications/barcode-lookup` | gallery image | — | ❌ |
| F-533 | Medicine | Add sheet — 🔍 Lookup button | button | POST `/medications/barcode-lookup` | by name | — | ❌ |
| F-534 | Medicine | Add/Edit sheet — Cancel | button | — | close | — | ❌ |
| F-535 | Medicine | Add/Edit sheet — Save | button | POST/PUT `/medications` | `loadMedicineCabinet()` | — | ❌ |
| F-536 | Medicine | Members sheet — member row delete 🗑 | button | DELETE `/household-members/<id>` | confirm | — | ❌ |
| F-537 | Medicine | Members sheet — Add name input | text-input | POST `/household-members` | — | — | ❌ |
| F-538 | Medicine | Members sheet — Add age select | select | POST `/household-members` | Adult/Child | — | ❌ |
| F-539 | Medicine | Members sheet — Add button | button | POST `/household-members` | `__medicineMembers.push` + rerender | — | ❌ |
---

## Screen: Restaurant
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-601 | Restaurant | Stat — Visits count | display | GET `/receipts?type=restaurant` | `restaurant-visit-count` | — | ❌ |
| F-602 | Restaurant | Stat — Dining Spend | display | GET `/analytics/spending?domain=restaurant` | `restaurant-total-spend` | — | ❌ |
| F-603 | Restaurant | Stat — Average Ticket | display | derived | `restaurant-average-ticket` | — | ❌ |
| F-604 | Restaurant | Stat — Top Restaurant | display | GET `/analytics/top-merchants?domain=restaurant` | `restaurant-top-store` | — | ❌ |
| F-605 | Restaurant | Dining Budget — month picker | month-input | GET `/budget/status?month=&domain=restaurant` | `loadRestaurantBudget()` (V-9 RESOLVED — endpoint corrected from fabricated `/budget/dining`; real endpoint per `manage_household_budget.py:284`) | — | ❌ |
| F-606 | Restaurant | Dining Budget — amount input | number-input | POST `/budget` category=dining | `restaurant-budget-amount` | — | ❌ |
| F-607 | Restaurant | Dining Budget — Save button | button | POST `/budget` category=dining | `saveRestaurantBudget()` | — | ❌ |
| F-608 | Restaurant | Dining Budget status (progress bar) | display | GET `/budget/status?month=&domain=restaurant` | `restaurant-budget-status` (V-9 RESOLVED — `domain=restaurant` not `category=dining`; backend takes `domain` param per `manage_household_budget.py:284`) | — | ❌ |
| F-609 | Restaurant | Receipt Review period select | select | GET `/receipts?type=restaurant&months=N` | 3/6/12 months | — | ❌ |
| F-610 | Restaurant | Receipt Review refresh 🔄 button | button | GET `/receipts?type=restaurant` | `loadRestaurant()` | — | ❌ |
| F-611 | Restaurant | Restaurant body — receipt row tap | tap | GET `/receipts/<id>` | inline detail | — | ❌ |
| F-612 | Restaurant | Top Restaurants list row tap | tap | GET `/receipts?store=...` | filter receipts to store | — | ❌ |
| F-613 | Restaurant | Top Ordered Items row tap | tap | GET `/receipts?item=...` | filter | — | ❌ |
---

## Screen: Balances
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-701 | Balances | Page header refresh 🔄 | button | GET `/shared-dining/balances` | `loadBalances()` | — | ❌ |
| F-702 | Balances | "Who Owes What" card title | display | — | static | — | ❌ |
| F-703 | Balances | Per-contact balance row (name, owed/owes amount) | display | GET `/shared-dining/balances` | `balances-body` | — | ❌ |
| F-704 | Balances | Per-contact "Settle all" button | button | POST `/shared-dining/contacts/<id>/settle-all` | `settleAllWithContact()` confirm | — | ❌ |
| F-705 | Balances | Per-contact expand → underlying debts list | tap-toggle | — | individual debt rows | — | ❌ |
| F-706 | Balances | Per-debt row settle button | button | POST `/shared-dining/debts/<id>/settle` | per-debt | — | ❌ |
---

## Screen: Contacts (Dining)
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-801 | Contacts | Page header refresh 🔄 | button | GET `/shared-dining/contacts` | `loadContacts()` | — | ❌ |
| F-802 | Contacts | Add Contact — Name input * | text-input | POST `/shared-dining/contacts` | required | — | ❌ |
| F-803 | Contacts | Add Contact — Phone input | text-input | POST `/shared-dining/contacts` | tel | — | ❌ |
| F-804 | Contacts | Add Contact — Email input | text-input | POST `/shared-dining/contacts` | email | — | ❌ |
| F-805 | Contacts | Add Contact "Add Contact" button | button | POST `/shared-dining/contacts` | `saveContact()` | — | ❌ |
| F-806 | Contacts | Saved Contacts list row (avatar, name, phone/email) | display | GET `/shared-dining/contacts` | per-card | — | ❌ |
---

## Screen: Expenses
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-901 | Expenses | Stat — Expense Receipts count | display | GET `/receipts?type=general_expense` | `expense-receipt-count` | — | ❌ |
| F-902 | Expenses | Stat — Total Spend | display | GET `/analytics/spending?domain=general_expense` | `expense-total-spend` | — | ❌ |
| F-903 | Expenses | Stat — Average Ticket | display | derived | `expense-average-ticket` | — | ❌ |
| F-904 | Expenses | Stat — Top Merchant | display | GET `/analytics/top-merchants?domain=general_expense` | `expense-top-store` | — | ❌ |
| F-905 | Expenses | Expense Budget — month picker | month-input | GET `/budget/status?month=&domain=general_expense` | `loadExpenseBudget()` (V-9 RESOLVED — endpoint corrected from fabricated `/budget?category=…`; real endpoint per `manage_household_budget.py:284`) | — | ❌ |
| F-906 | Expenses | Expense Budget — amount input | number-input | POST `/budget` | `expense-budget-amount` | — | ❌ |
| F-907 | Expenses | Expense Budget — Save | button | POST `/budget` | `saveExpenseBudget()` | — | ❌ |
| F-908 | Expenses | Expense Budget status | display | GET `/budget/status?category=general_expense` | progress bar | — | ❌ |
| F-909 | Expenses | Period select | select | GET `/receipts?type=general_expense&months=N` | 3/6/12 | — | ❌ |
| F-910 | Expenses | Expenses refresh 🔄 | button | GET `/receipts?type=general_expense` | `loadExpenses()` | — | ❌ |
| F-911 | Expenses | Expenses list row tap → select | tap | GET `/receipts/<id>` | sets `expense-detail-body` | — | ❌ |
| F-912 | Expenses | Selected receipt detail panel | display | GET `/receipts/<id>` | `renderExpenseReceiptDetail()` | — | ❌ |
| F-913 | Expenses | Top Merchants row tap | tap | filter | `expense-top-merchants` | — | ❌ |
| F-914 | Expenses | Top Reference Items row tap | tap | filter | `expense-top-items` | — | ❌ |
| F-915 | Expenses | Expense Categories breakdown bar | display | GET `/analytics/categories?domain=general_expense` | `expense-category-breakdown` | — | ❌ |
| F-916 | Expenses | Selected receipt — mobile reposition | (layout) | — | `repositionExpenseDetailForMobile()` | — | 🔄 native layout handles this; no port needed |
---

## Screen: Shopping
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1001 | Shopping | Page header — Quick Find toggle (🔍) | button | — | `toggleShoppingSection('quick-find')` | — | ❌ |
| F-1002 | Shopping | Page header — Recommendations chip ✨ + count | tap-toggle | GET `/recommendations` | `toggleShoppingSection('recommendations')` | — | ❌ |
| F-1003 | Shopping | Helper intro banner | display | — | `shopping-helper-intro` (kitchen helper mode) | — | ❌ |
| F-1004 | Shopping | Session banner card | display | GET `/shopping-list/sessions/current` | `renderShoppingSessionBanner()` | — | ❌ |
| F-1005 | Shopping | Summary pill — Open count | button | — | `setShoppingListView('open')` | — | ❌ |
| F-1006 | Shopping | Summary pill — Estimate total | display | — | `shop-estimated-total-main` | — | ❌ |
| F-1007 | Shopping | Summary pill — Close count | button | — | `setShoppingListView('purchased')` | — | ❌ |
| F-1008 | Shopping | Manual add — "Hide" toggle | button | — | `toggleManualShoppingForm(false)` | — | ❌ |
| F-1009 | Shopping | Manual add — "Identify from Photo" button | button | POST `/shopping-list/identify-photo` | `triggerShopIdentifyPhoto()` | — | ❌ |
| F-1010 | Shopping | Manual add — file input (camera capture) | file-pick | POST `/shopping-list/identify-photo` | `handleShopIdentifyPhoto()` | — | ❌ |
| F-1011 | Shopping | Manual add — identified preview image | display | — | `shop-identify-preview` | — | ❌ |
| F-1012 | Shopping | Manual add — Name input | text-input | POST `/shopping-list/items` | `shop-name` | — | ❌ |
| F-1013 | Shopping | Manual add — Category select | select | POST `/shopping-list/items` | populated by category options | — | ❌ |
| F-1014 | Shopping | Manual add — Preferred Store select | select | POST `/shopping-list/items` | `shop-manual-store` | — | ❌ |
| F-1015 | Shopping | Manual add — Estimate Price input | number-input | POST `/shopping-list/items` | `shop-manual-price` | — | ❌ |
| F-1016 | Shopping | Manual add — Quantity input | number-input | POST `/shopping-list/items` | `shop-qty` | — | ❌ |
| F-1017 | Shopping | Manual add — Note input | text-input | POST `/shopping-list/items` | `shop-note` | — | ❌ |
| F-1018 | Shopping | Manual add — "➕ Add to Shopping List" | button | POST `/shopping-list/items` | `createShoppingItem()` | — | ❌ |
| F-1019 | Shopping | Quick Find — Collapse toggle | button | — | `toggleShoppingSection('quick-find')` | — | ❌ |
| F-1020 | Shopping | Quick Find — search input | text-input | GET `/products?q=...&shopping=1` | `searchShoppingQuickFind()` | — | ❌ |
| F-1021 | Shopping | Quick Find — Preferred Store select | select | — | `shop-preferred-store` | — | ❌ |
| F-1022 | Shopping | Quick Find — "Add Manually" toggle | button | — | `toggleManualShoppingForm()` | — | ❌ |
| F-1023 | Shopping | Quick Find results — per-result Add to list | button | POST `/shopping-list/items` | `quickAddToShoppingList()` | — | ❌ |
| F-1024 | Shopping | Quick Find results — per-result Mark Low | button | PATCH `/products/<id>/low-status` | `setProductLowStatus()` | — | ❌ |
| F-1025 | Shopping | Quick Find results — per-result Mark Bought | button | POST `/shopping-list/items` then PATCH purchased | `quickAddBoughtShoppingItem()` | — | ❌ |
| F-1026 | Shopping | Recommendations summary chip + count | button | — | `toggleShoppingSection('recommendations')` | — | ❌ |
| F-1027 | Shopping | Recommendations refresh button | button | GET `/recommendations` | `loadRecs('shopping-recs-body')` | — | ❌ |
| F-1028 | Shopping | Recommendation row — Add | button | POST `/shopping-list/items` | per-rec | — | ❌ |
| F-1029 | Shopping | Recommendation row — Dismiss | button | POST `/recommendations/<id>/dismiss` | per-rec | — | ❌ |
| F-1030 | Shopping | Current List — title toggle | button | — | `toggleShoppingSection('current-list')` | — | ❌ |
| F-1031 | Shopping | Current List — aggregate total | display | — | `shopping-current-list-total` | — | ❌ |
| F-1032 | Shopping | Current List — Sort A chip | button | — | `setShoppingSort('name_asc')` | — | ❌ |
| F-1033 | Shopping | Current List — Sort Z chip | button | — | `setShoppingSort('name_desc')` | — | ❌ |
| F-1034 | Shopping | Current List — Sort $ chip (toggle asc/desc) | button | — | `toggleShoppingPriceSort()` | — | ❌ |
| F-1035 | Shopping | Store group header tap (collapse) | tap-toggle | — | `toggleShoppingStoreGroup()` | — | ❌ |
| F-1036 | Shopping | Store group store-total display | display | — | `storeEstimateForItems()` | — | ❌ |
| F-1037 | Shopping | Store group item-count chip | button | — | toggle group | — | ❌ |
| F-1038 | Shopping | List item — product thumbnail tap (zoom) | tap | — | `openShoppingSnapshot()` | — | ❌ |
| F-1039 | Shopping | List item — placeholder 📷 thumb | display | — | when no snapshot | — | ❌ |
| F-1040 | Shopping | List item — name + merged-count meta | display | — | `formatShoppingDisplayName()` | — | ❌ |
| F-1041 | Shopping | List item — full-name expander | display | — | `expandedFullName` | — | ❌ |
| F-1042 | Shopping | List item — Store select | select | PUT `/shopping-list/items/<id>` preferred_store | `updateShoppingPreferredStoreGroup()` | — | ❌ |
| F-1043 | Shopping | List item — Unit select | select | PUT `/shopping-list/items/<id>` unit | inline | — | ❌ |
| F-1044 | Shopping | List item — Size Label input | text-input | PUT `/shopping-list/items/<id>` size_label | inline | — | ❌ |
| F-1045 | Shopping | List item — Unit Price input | number-input | PUT `/shopping-list/items/<id>` price | inline | — | ❌ |
| F-1046 | Shopping | List item — Update button | button | PUT `/shopping-list/items/<id>` | `updateShoppingGroupDetails()` | — | ❌ |
| F-1047 | Shopping | List item — Rename button | button | PUT `/shopping-list/items/<id>` name | `renameShoppingDisplayItem()` | — | ❌ |
| F-1048 | Shopping | List item — Actual price strip | number-input | PUT `/shopping-list/items/<id>` actual_price | `renderShoppingActualPriceField()` | — | ❌ |
| F-1049 | Shopping | List item — −1 button | button | PUT `/shopping-list/items/<id>` quantity | `decreaseShoppingGroupQuantity()` | — | ❌ |
| F-1050 | Shopping | List item — Bought/Reopen toggle button | button | PUT `/shopping-list/items/<id>` status=purchased/open | `toggleShoppingGroupItems()` | — | ❌ |
| F-1051 | Shopping | List item — "More" menu trigger | button | — | `toggleShoppingMoreMenu()` | — | ❌ |
| F-1052 | Shopping | More menu — Add Photo | file-pick | POST `/product-snapshots/upload` | `selectShoppingSnapshotFile()` | — | ❌ |
| F-1053 | Shopping | More menu — View Photo | tap | — | `openShoppingSnapshot()` | — | ❌ |
| F-1054 | Shopping | More menu — Low / Clear Low | button | PATCH `/products/<id>/low-status` | `setProductLowStatus()` | — | ❌ |
| F-1055 | Shopping | More menu — Out of Stock / Reopen | button | PUT `/shopping-list/items/<id>` status=out_of_stock/open | `toggleShoppingGroupItems()` | — | ❌ |
| F-1056 | Shopping | More menu — Rename | button | PUT `/shopping-list/items/<id>` name | | — | ❌ |
| F-1057 | Shopping | More menu — Delete | button | DELETE `/shopping-list/items/<id>` | `deleteShoppingGroupItems()` | — | ❌ |
| F-1058 | Shopping | Skipped group <details> summary | details-summary | — | "Skipped (N)" expander | — | ❌ |
| F-1059 | Shopping | Skipped row — ↩ Open | button | PUT `/shopping-list/items/<id>` status=open | `toggleShoppingItem()` | — | ❌ |
| F-1060 | Shopping | Skipped row — 🗑 delete | button | DELETE `/shopping-list/items/<id>` | `deleteShoppingItem()` | — | ❌ |
| F-1061 | Shopping | List row — touchstart long-press | long-press | — | `shoppingLongPressStart()` → context menu | — | ❌ |
| F-1062 | Shopping | List row — touchstart swipe | swipe-left/right | PUT `/shopping-list/items/<id>` status | `startShoppingSwipe/moveShoppingSwipe/endShoppingSwipe` | — | ❌ |
| F-1063 | Shopping | List row — right-click context menu | right-click-menu | — | `shoppingHandleContextMenu()` | — | 🔄 long-press covers verb on Android |
| F-1064 | Shopping | Mobile item tap to expand | tap | — | `toggleShoppingMobileItem()` | — | ❌ |
| F-1065 | Shopping | File input — shopping snapshot picker | file-pick | POST `/product-snapshots/upload` | `uploadShoppingSnapshotFromPicker()` | — | ❌ |
| F-1066 | Shopping | Past Trips card header (collapse) | tap-toggle | GET `/shopping-list/sessions` | `toggleShoppingPastTrips()` | — | ❌ |
| F-1067 | Shopping | Past Trips chevron | display | — | rotation indicator | — | ❌ |
| F-1068 | Shopping | Past trip row tap (detail) | tap | GET `/shopping-list/sessions/<id>` | `renderPastTripDetail()` | — | ❌ |
| F-1069 | Shopping | Past trip detail item row | display | — | per item bought in trip | — | ❌ |
---

## Screen: Kitchen
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1101 | Kitchen | Catalog "🛒 Browse products" toggle | button | — | `toggleKitchenCatalog()` | — | ❌ |
| F-1102 | Kitchen | Catalog chip — ⭐ Frequent | chip-toggle | GET `/api/kitchen/catalog` | `kitchenSetActiveCategory('frequent')` | — | ❌ |
| F-1103 | Kitchen | Catalog chip — per category | chip-toggle | GET `/api/kitchen/catalog` | `kitchenSetActiveCategory(c)` | — | ❌ |
| F-1104 | Kitchen | Catalog search input | text-input | — | `onKitchenSearchInput()` | — | ❌ |
| F-1105 | Kitchen | Catalog search 🔍 icon | tap | — | `toggleKitchenSearchPopover(true)` | — | ❌ |
| F-1106 | Kitchen | Catalog search popover — store filter chips | chip-toggle | — | `renderKitchenStoreFilter()` | — | ❌ |
| F-1107 | Kitchen | Catalog grid prev arrow ‹ | button | — | `kitchenGridScrollBy(-1)` | — | ❌ |
| F-1108 | Kitchen | Catalog grid next arrow › | button | — | `kitchenGridScrollBy(1)` | — | ❌ |
| F-1109 | Kitchen | Catalog tile (image or emoji) | display | — | image_url or `kitchenEmojiForProduct()` | — | ❌ |
| F-1110 | Kitchen | Catalog tile price badge | display | — | `latest_unit_price` | — | ❌ |
| F-1111 | Kitchen | Catalog tile +N variants badge | display | — | `_variant_count > 1` | — | ❌ |
| F-1112 | Kitchen | Catalog tile purchase-count badge (Nx) | display | — | `purchase_count` last 90d | — | ❌ |
| F-1113 | Kitchen | Catalog tile name display | display | — | `t.name` | — | ❌ |
| F-1114 | Kitchen | Catalog tile tap → add to list | tap | POST `/shopping-list/items` | `addProductToList(productId, name, category)` | — | ❌ |
| F-1115 | Kitchen | Catalog tile tap (variants > 1) → variant picker | tap | GET `/api/kitchen/catalog?variants_of=...` | `_kitchenOpenVariantPickerForKey()` | — | ❌ |
| F-1116 | Kitchen | Catalog tile already-on-list visual | display | — | `.on-list` class | — | ❌ |
| F-1117 | Kitchen | Catalog tile long-press → context menu | long-press | — | `_kitchenWireLongPress()` 900ms | — | ❌ |
| F-1118 | Kitchen | Catalog tile right-click → ctx menu | right-click-menu | — | suppressed by `contextmenu` handler that opens menu | — | 🔄 long-press covers; right-click absent on Android |
| F-1119 | Kitchen | Context menu — Add to list | button | POST `/shopping-list/items` | `addProductToList()` | — | ❌ |
| F-1120 | Kitchen | Context menu — Pick variant (N) | button | — | `_kitchenOpenVariantPickerForKey()` | — | ❌ |
| F-1121 | Kitchen | Context menu — Show only this product's stores | button | — | `kitchenSetStoreFilterTo()` | — | ❌ |
| F-1122 | Kitchen | Names toggle 🏷️ button | button | — | `toggleKitchenNames()` | — | ❌ |
| F-1123 | Kitchen | List total display | display | — | aggregate of unit_price × qty | — | ❌ |
| F-1124 | Kitchen | Weather widget (current weather) | display | open-meteo (3rd-party) | `loadKitchenWeather()` IP geo → temp + code emoji | — | 🔄 Android can use system location/forecast or keep 3rd-party fetch |
| F-1125 | Kitchen | Empty state ("list empty") | display | — | `kitchen-empty` | — | ❌ |
| F-1126 | Kitchen | List store group header (store + count + total) | display | — | `renderKitchenList()` group | — | ❌ |
| F-1127 | Kitchen | List item tile tap → open sheet | tap | — | `openKitchenSheet(itemId)` | — | ❌ |
| F-1128 | Kitchen | List tile skipped overlay | display | — | `.skipped` class | — | ❌ |
| F-1129 | Kitchen | List item context menu — Decrease qty | button | PUT `/shopping-list/items/<id>` | `kitchenSheetSetQty(-1)` | — | ❌ |
| F-1130 | Kitchen | List item context menu — Increase qty | button | PUT `/shopping-list/items/<id>` | `kitchenSheetSetQty(1)` | — | ❌ |
| F-1131 | Kitchen | List item context menu — Bought | button | PUT `/shopping-list/items/<id>` status=purchased | `kitchenSheetAction('bought')` | — | ❌ |
| F-1132 | Kitchen | List item context menu — Low | button | PATCH `/products/<id>/low-status` | `kitchenSheetAction('low')` | — | ❌ |
| F-1133 | Kitchen | List item context menu — Skip | button | PUT `/shopping-list/items/<id>` status=skipped | `kitchenSheetAction('skipped')` | — | ❌ |
| F-1134 | Kitchen | List item context menu — Open (skipped only) | button | PUT `/shopping-list/items/<id>` status=open | `kitchenSheetAction('open')` | — | ❌ |
| F-1135 | Kitchen | List item context menu — Delete | button | DELETE `/shopping-list/items/<id>` | `kitchenSheetAction('delete')` | — | ❌ |
| F-1136 | Kitchen | List item context menu — Edit details… | button | — | `openKitchenSheet(itemId)` | — | ❌ |
| F-1137 | Kitchen | Item sheet — Close button | button | — | `closeKitchenSheet()` | — | ❌ |
| F-1138 | Kitchen | Item sheet — Store picker | button | PUT `/shopping-list/items/<id>` preferred_store | `pickKitchenStore()` | — | ❌ |
| F-1139 | Kitchen | Item sheet — Store picker Clear | button | PUT `/shopping-list/items/<id>` preferred_store=null | `pickKitchenStore('')` | — | ❌ |
| F-1140 | Kitchen | Item sheet — − qty button | button | PUT `/shopping-list/items/<id>` quantity | `kitchenSheetSetQty(-1)` | — | ❌ |
| F-1141 | Kitchen | Item sheet — + qty button | button | PUT `/shopping-list/items/<id>` quantity | `kitchenSheetSetQty(1)` | — | ❌ |
| F-1142 | Kitchen | Item sheet — ✓ Bought button | button | PUT `/shopping-list/items/<id>` status=purchased | `kitchenSheetAction('bought')` | — | ❌ |
| F-1143 | Kitchen | Item sheet — 📝 Low button | button | PATCH `/products/<id>/low-status` | | — | ❌ |
| F-1144 | Kitchen | Item sheet — ⏭ Skip button | button | PUT `/shopping-list/items/<id>` status=skipped | | — | ❌ |
| F-1145 | Kitchen | Item sheet — 🗑 Delete button | button | DELETE `/shopping-list/items/<id>` | | — | ❌ |
| F-1146 | Kitchen | Item sheet — ↩ Open (skipped) button | button | PUT `/shopping-list/items/<id>` status=open | | — | ❌ |
| F-1147 | Kitchen | Item sheet — Presets row | tap | — | `kitchen-presets` quick-pick presets | — | ❌ |
| F-1148 | Kitchen | Variant picker sheet — variant tile tap | tap | POST `/shopping-list/items` | `_kitchenAddVariant()` | — | ❌ |
| F-1149 | Kitchen | Catalog grid mousewheel horizontal scroll | scroll | — | `_kitchenWireGridWheel()` | — | 🔄 native horizontal scroll on Android handles this |
---

## Screen: Upload
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1201 | Upload | Drop zone label | file-pick | — | click opens file dialog | — | ❌ |
| F-1202 | Upload | Drop zone drag-and-drop area | drop | — | files dropped onto zone | — | 🔄 Android uses pick / share intent rather than HTML drop |
| F-1203 | Upload | File input (multiple) | file-pick | — | `accept=image/*,.pdf,application/pdf` | — | ❌ |
| F-1204 | Upload | Preview image / meta | display | — | `preview-img` + `preview-meta` | — | ❌ |
| F-1205 | Upload | Batch — Select All checkbox | checkbox | — | `toggleSelectAllBatch()` | — | ❌ |
| F-1206 | Upload | Batch — file count display | display | — | `batch-controls__count` | — | ❌ |
| F-1207 | Upload | Batch — Clear all button | button | — | `clearBatch()` | — | ❌ |
| F-1208 | Upload | Batch list row — per-file checkbox | checkbox | — | per-batch | — | ❌ |
| F-1209 | Upload | Batch list row — per-file remove | button | — | `removeBatchEntry()` | — | ❌ |
| F-1210 | Upload | Batch list row — per-file status | display | — | pending/processing/done/error | — | ❌ |
| F-1211 | Upload | Receipt type button — Auto | button | — | `setUploadIntent('auto')` | — | ❌ |
| F-1212 | Upload | Receipt type button — Grocery | button | — | `setUploadIntent('grocery')` | — | ❌ |
| F-1213 | Upload | Receipt type button — Restaurant | button | — | `setUploadIntent('restaurant')` | — | ❌ |
| F-1214 | Upload | Receipt type button — General Expense | button | — | `setUploadIntent('general_expense')` | — | ❌ |
| F-1215 | Upload | OCR model select | select | GET `/api/models` | `changeAiModelSelection()` | — | ❌ |
| F-1216 | Upload | "Browse" model toggle | button | — | `toggleAiModelBrowser()` | — | ❌ |
| F-1217 | Upload | Model browser body | display | GET `/api/models` | `renderAiModelBrowser()` | — | ❌ |
| F-1218 | Upload | "🚀 Auto Detect Receipt" upload button | button | POST `/receipts/upload` | `uploadReceipt()` | — | ❌ |
| F-1219 | Upload | "✕ Stop" button | button | POST `/receipts/cancel-batch` | `requestBatchStop()` | — | ❌ |
| F-1220 | Upload | Upload status text | display | — | `upload-status` | — | ❌ |
| F-1221 | Upload | Scan progress bar (phase + meta) | display | — | `scan-progress` indeterminate/determinate | — | ❌ |
| F-1222 | Upload | Scan model chip | display | — | `upload-scan-model` | — | ❌ |
| F-1223 | Upload | Scan retry button | button | POST `/receipts/upload` | `uploadReceipt()` | — | ❌ |
| F-1224 | Upload | Extracted Items card body | display | — | `ocr-result` populated post-upload | — | ❌ |
---

## Screen: Receipts
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1301 | Receipts | Filters 🧰 toggle | button | — | `toggleReceiptFilters()` | — | ❌ |
| F-1302 | Receipts | Filter "Review Refunds" button | button | GET `/receipts?refunds=1` | `openRefundReceipts()` | — | ❌ |
| F-1303 | Receipts | Filter "Apply" button | button | GET `/receipts?...` | `loadReceipts()` | — | ❌ |
| F-1304 | Receipts | Filter "Reset" button | button | — | `resetReceiptFilters()` | — | ❌ |
| F-1305 | Receipts | Filter Search input | text-input | GET `/receipts?q=...` | `onReceiptSearchInput()` debounce | — | ❌ |
| F-1306 | Receipts | Attribution chip row | chip-toggle | GET `/receipts?attribution=` | `renderReceiptAttributionFilterChips()` | — | ❌ |
| F-1307 | Receipts | "🏷 Untagged only" filter chip | chip-toggle | GET `/receipts?untagged_only=1` | `toggleReceiptsUntaggedFilter()` | — | ❌ |
| F-1308 | Receipts | Store filter select | select | GET `/receipts?store=` | `receipt-filter-store` | — | ❌ |
| F-1309 | Receipts | Source filter select | select | GET `/receipts?source=` | upload/telegram | — | ❌ |
| F-1310 | Receipts | Receipt Type filter select | select | GET `/receipts?type=` | grocery/restaurant/expense/bill/event/unknown | — | ❌ |
| F-1311 | Receipts | Transaction filter select | select | GET `/receipts?transaction_type=` | purchase/refund | — | ❌ |
| F-1312 | Receipts | Status filter select | select | GET `/receipts?status=` | review/processed/failed/pending | — | ❌ |
| F-1313 | Receipts | Purchased from date | date-input | GET `/receipts?purchase_from=` | — | — | ❌ |
| F-1314 | Receipts | Purchased to date | date-input | GET `/receipts?purchase_to=` | — | — | ❌ |
| F-1315 | Receipts | Uploaded from date | date-input | GET `/receipts?upload_from=` | — | — | ❌ |
| F-1316 | Receipts | Uploaded to date | date-input | GET `/receipts?upload_to=` | — | — | ❌ |
| F-1317 | Receipts | Receipts-By-Store desktop sort | select | — | `setReceiptStoreSort()` count_desc/store_asc | — | ❌ |
| F-1318 | Receipts | Receipts-By-Store desktop list row tap | tap | — | filter to that store | — | ❌ |
| F-1319 | Receipts | Summary section card title (collapse) | tap-toggle | — | `toggleReceiptsSummary()` | — | ❌ |
| F-1320 | Receipts | Stat — Total Receipts | display | derived | `receipt-total-count` | — | ❌ |
| F-1321 | Receipts | Stat — Refund Receipts | display | derived | `receipt-refund-count` | — | ❌ |
| F-1322 | Receipts | Stat — Refund Total | display | derived | `receipt-refund-total` | — | ❌ |
| F-1323 | Receipts | Stat — Total Items | display | derived | `receipt-total-items` | — | ❌ |
| F-1324 | Receipts | Stat — Unique Items | display | derived | `receipt-unique-items` | — | ❌ |
| F-1325 | Receipts | Stat — Most Bought Items | display | derived | `receipt-most-bought-count` + list | — | ❌ |
| F-1326 | Receipts | Refund review strip | display | GET `/receipts/refunds?status=needs_review` | `renderReceiptRefundReviewStrip()` | — | ❌ |
| F-1327 | Receipts | Receipts-By-Store mobile select sort | select | — | `setReceiptStoreSort()` | — | ❌ |
| F-1328 | Receipts | Receipts-By-Store mobile list row tap | tap | — | filter to store | — | ❌ |
| F-1329 | Receipts | Purchases By Month chart | display | derived | `receipt-summary-months` | — | ❌ |
| F-1330 | Receipts | Dedup scan button | button | POST `/receipts/dedup/scan` | `runDedupScan()` | — | ❌ |
| F-1331 | Receipts | Dedup pair Merge button | button | POST `/receipts/dedup/merge` | per pair (auto-detected) | — | ❌ |
| F-1332 | Receipts | Manual merge — Keep ID input | number-input | POST `/receipts/dedup/merge` | `manualMergeReceipts()` | — | ❌ |
| F-1333 | Receipts | Manual merge — Drop ID input | number-input | POST `/receipts/dedup/merge` | | — | ❌ |
| F-1334 | Receipts | Manual merge — Merge button | button | POST `/receipts/dedup/merge` | | — | ❌ |
| F-1335 | Receipts | Recent Receipts — sort select | select | — | `setReceiptSort()` date/total/store/status | — | ❌ |
| F-1336 | Receipts | Recent Receipts — refresh 🔄 | button | GET `/receipts` | `loadReceipts()` | — | ❌ |
| F-1337 | Receipts | Receipt list row tap → select / inline | tap | GET `/receipts/<id>` | `viewReceipt(id)` | — | ❌ |
| F-1338 | Receipts | Receipt list row — hover shows ID tooltip | hover-popup | — | mentioned in dedup helper | — | 🔄 Android long-press shows tooltip equivalent |
| F-1339 | Receipts | Receipt detail — image rotate left | button | POST `/receipts/<id>/rotate?dir=left` | `rotateReceipt()` | — | ❌ |
| F-1340 | Receipts | Receipt detail — image rotate right | button | POST `/receipts/<id>/rotate?dir=right` | `rotateReceipt()` | — | ❌ |
| F-1341 | Receipts | Receipt detail — Mark as Restaurant | button | PATCH `/receipts/<id>` receipt_type=restaurant | `markReceiptEditorAsRestaurant()` | — | ❌ |
| F-1342 | Receipts | Receipt detail — 💸 Split Receipt toggle | button | — | `toggleSplitPanel()` reveals split UI | — | ❌ |
| F-1343 | Receipts | Receipt detail — Re-run OCR | button | POST `/receipts/<id>/reprocess` | `reprocessReceipt()` | — | ❌ |
| F-1344 | Receipts | Bill summary — Provider stat | display | — | derived | — | ❌ |
| F-1345 | Receipts | Bill summary — Counts Toward stat | display | — | `bill_planning_month` | — | ❌ |
| F-1346 | Receipts | Bill summary — Due Date stat | display | — | `bill_due_date` | — | ❌ |
| F-1347 | Receipts | Bill summary — Frequency stat | display | — | `bill_billing_cycle` | — | ❌ |
| F-1348 | Receipts | Bill summary — Payment Status stat | display | — | `bill_payment_status` | — | ❌ |
| F-1349 | Receipts | Bill — Change status select | select | PATCH `/receipts/<id>` bill_payment_status | `updateReceiptBillStatus()` | — | ❌ |
| F-1350 | Receipts | Bill — Save status button | button | PATCH `/receipts/<id>` bill_payment_status | | — | ❌ |
| F-1351 | Receipts | Bill — Paid on date input | date-input | PATCH `/receipts/<id>` bill_payment_confirmed_at | | — | ❌ |
| F-1352 | Receipts | Bill — Mark Paid button | button | PATCH `/receipts/<id>` bill_payment_status=paid | `quickSetReceiptBillStatus(id,'paid')` | — | ❌ |
| F-1353 | Receipts | Bill — Mark Unpaid button | button | PATCH `/receipts/<id>` bill_payment_status=upcoming | `quickSetReceiptBillStatus(id,'upcoming')` | — | ❌ |
| F-1354 | Receipts | Extracted Items — item sort select | select | — | `setReceiptItemSort()` name/qty/price | — | ❌ |
| F-1355 | Receipts | Extracted Items row — quantity input | number-input | PATCH `/receipts/<id>/items/<itemId>` | inline | — | ❌ |
| F-1356 | Receipts | Extracted Items row — unit price input | number-input | PATCH `/receipts/<id>/items/<itemId>` | inline | — | ❌ |
| F-1357 | Receipts | Extracted Items row — name input | text-input | PATCH `/receipts/<id>/items/<itemId>` | inline | — | ❌ |
| F-1358 | Receipts | Extracted Items row — category select | select | PATCH `/receipts/<id>/items/<itemId>` | inline | — | ❌ |
| F-1359 | Receipts | Extracted Items row — delete button | button | DELETE `/receipts/<id>/items/<itemId>` | inline | — | ❌ |
| F-1360 | Receipts | Editor — Receipt Type select | select | PATCH `/receipts/<id>` receipt_type | `handleReceiptEditorTypeChange()` | — | ❌ |
| F-1361 | Receipts | Editor — Store input | text-input | PATCH `/receipts/<id>` store | | — | ❌ |
| F-1362 | Receipts | Editor — Date input | date-input | PATCH `/receipts/<id>` date | | — | ❌ |
| F-1363 | Receipts | Editor — Time input | text-input | PATCH `/receipts/<id>` time | | — | ❌ |
| F-1364 | Receipts | Editor — Tax input | number-input | PATCH `/receipts/<id>` tax | | — | ❌ |
| F-1365 | Receipts | Editor — Transaction select | select | PATCH `/receipts/<id>` transaction_type | purchase/refund | — | ❌ |
| F-1366 | Receipts | Editor — Refund Reason select | select | PATCH `/receipts/<id>` refund_reason | shown when refund | — | ❌ |
| F-1367 | Receipts | Editor — Budget Category select | select | PATCH `/receipts/<id>` default_budget_category | | — | ❌ |
| F-1368 | Receipts | Editor — Subtotal input | number-input | PATCH `/receipts/<id>` subtotal | | — | ❌ |
| F-1369 | Receipts | Editor — Tip input | number-input | PATCH `/receipts/<id>` tip | | — | ❌ |
| F-1370 | Receipts | Editor — Total input | number-input | PATCH `/receipts/<id>` total | | — | ❌ |
| F-1371 | Receipts | Editor — Attribution picker trigger | button | — | `toggleAttributionPicker()` | — | ❌ |
| F-1372 | Receipts | Editor — Attribution picker household / per-person | chip-toggle | PATCH `/receipts/<id>` attribution | multi-select | — | ❌ |
| F-1373 | Receipts | Editor — Bill Provider Name input + datalist | text-input | PATCH `/receipts/<id>` bill_provider_name | `handleReceiptProviderNameLookup()` | — | ❌ |
| F-1374 | Receipts | Editor — Bill Provider Type select | select | PATCH `/receipts/<id>` bill_provider_type | electricity/water/etc | — | ❌ |
| F-1375 | Receipts | Editor — Service Types checklist | checkbox | PATCH `/receipts/<id>` service_types | `renderBillServiceTypeChecklist()` | — | ❌ |
| F-1376 | Receipts | Editor — Account Label input | text-input | PATCH `/receipts/<id>` bill_account_label | | — | ❌ |
| F-1377 | Receipts | Editor — Billing Cycle Month month-input | month-input | PATCH `/receipts/<id>` bill_billing_cycle_month | | — | ❌ |
| F-1378 | Receipts | Editor — Bill Frequency select | select | PATCH `/receipts/<id>` bill_billing_cycle | | — | ❌ |
| F-1379 | Receipts | Editor — Service Period Start date | date-input | PATCH `/receipts/<id>` bill_service_period_start | | — | ❌ |
| F-1380 | Receipts | Editor — Service Period End date | date-input | PATCH `/receipts/<id>` bill_service_period_end | | — | ❌ |
| F-1381 | Receipts | Editor — Due Date date | date-input | PATCH `/receipts/<id>` bill_due_date | | — | ❌ |
| F-1382 | Receipts | Editor — Recurring bill checkbox | checkbox | PATCH `/receipts/<id>` bill_is_recurring | | — | ❌ |
| F-1383 | Receipts | Editor — Auto-pay checkbox | checkbox | PATCH `/receipts/<id>` bill_auto_pay | | — | ❌ |
| F-1384 | Receipts | Editor — Refund Note input | text-input | PATCH `/receipts/<id>` refund_note | | — | ❌ |
| F-1385 | Receipts | Editor — Add Item row button | button | POST `/receipts/<id>/items` | `addReceiptEditorRow()` | — | ❌ |
| F-1386 | Receipts | Editor — Save / Update Receipt button | button | PUT `/receipts/<id>` (or POST as purchase) | `saveEditedReceipt()` | — | ❌ |
| F-1387 | Receipts | Detail — Delete Receipt button | button | DELETE `/receipts/<id>` | `deleteReceipt()` confirm | — | ❌ |
| F-1388 | Receipts | Detail — inline Close Receipt | button | — | `toggleReceiptDetail()` | — | ❌ |
| F-1389 | Receipts | Split panel — scenario buttons | button | — | `_spSetScenario()` PAID_ALL / PAID_OWN / OWED | — | ❌ |
| F-1390 | Receipts | Split panel — participant amount input | number-input | — | `_spSetAmt()` | — | ❌ |
| F-1391 | Receipts | Split panel — participant contact select | select | GET `/shared-dining/contacts` | `_spSetContact()` | — | ❌ |
| F-1392 | Receipts | Split panel — payer checkbox | checkbox | — | `_spSetPayer()` (OWED only) | — | ❌ |
| F-1393 | Receipts | Split panel — remove participant button | button | — | `_spRemove()` | — | ❌ |
| F-1394 | Receipts | Split panel — "+ Add person" button | button | — | `_spAdd()` | — | ❌ |
| F-1395 | Receipts | Split panel — Cancel | button | — | `_spCancel()` | — | ❌ |
| F-1396 | Receipts | Split panel — Save Split button | button | POST `/shared-dining/splits` | `_spSave()` | — | ❌ |
| F-1397 | Receipts | Bulk-tag toolbar (multi-receipt) | button | PATCH `/receipts/bulk` attribution | `_renderReceiptsBulkTagToolbar()` | — | ❌ |
| F-1398 | Receipts | Bulk-bar select-all checkbox | checkbox | — | toggles all visible receipts | — | ❌ |
| F-1399 | Receipts | Receipt item snapshot file input | file-pick | POST `/product-snapshots/upload` | `uploadReceiptItemSnapshotFromPicker()` | — | ❌ |
| F-1400 | Receipts | Receipt image zoom (tap thumb) | tap | — | opens zoom overlay | — | ❌ |
| F-1401 | Receipts | Receipt PDF "Open PDF in new tab" link | tap-link | — | iframe + anchor | — | 🔄 Android opens PDF viewer intent |
---

## Screen: Budget
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1501 | Budget | Editor header collapse | tap-toggle | — | `toggleBudgetEditor()` | — | ❌ |
| F-1502 | Budget | Editor — ⚙ Budget chip | button | — | `toggleBudgetEditor(true)` | — | ❌ |
| F-1503 | Budget | Editor — ✍️ Manual Entry button | button | — | `openManualEntryModal()` | — | ❌ |
| F-1504 | Budget | Editor — 💸 Log Cash button | button | — | `openCashTransactionModal()` | — | ❌ |
| F-1505 | Budget | Editor — Month input | month-input | GET `/budget/category-summary?month=` | `loadBudgetStatus()` | — | ❌ |
| F-1506 | Budget | Editor — Budget Category select | select | GET `/budget/category-summary` | `loadBudgetEditorDefaults()` | — | ❌ |
| F-1507 | Budget | Editor — Budget $ input | number-input | POST `/budget` | `budget-amt` | — | ❌ |
| F-1508 | Budget | Editor — Save Budget button | button | POST `/budget` | `setBudget()` | — | ❌ |
| F-1509 | Budget | This Month total spent | display | — | `budget-total-spent` | — | ❌ |
| F-1510 | Budget | This Month refresh 🔄 | button | GET `/budget/category-summary` | `loadBudgetStatus()` | — | ❌ |
| F-1511 | Budget | Active category row — name + spent | display | — | `renderBudgetStatusRow()` | — | ❌ |
| F-1512 | Budget | Active category row — progress bar | display | — | `cls`: ok/warn/danger | — | ❌ |
| F-1513 | Budget | Active category row — pct / left/over | display | — | summary line | — | ❌ |
| F-1514 | Budget | Active category row — details expand | details-summary | — | `<details>` revealing contributing receipts | — | ❌ |
| F-1515 | Budget | Active category row tap | tap | — | `syncBudgetCategorySelection()` syncs editor select | — | ❌ |
| F-1516 | Budget | Other Categories <details> summary | details-summary | — | inactive group expand | — | ❌ |
| F-1517 | Budget | Contributing receipt row tap | tap | GET `/receipts/<id>` | `renderCompactReceiptRows()` | — | ❌ |
| F-1518 | Budget | Current Budget Targets — header expand | tap-toggle | GET `/budget/targets` | `toggleBudgetSection('budget-targets-shell')` | — | ❌ |
| F-1519 | Budget | Budget target row — display | display | — | `renderBudgetTargetRows()` | — | ❌ |
| F-1520 | Budget | Budget target row — delete | button | DELETE `/budget/<category>` | per-row | — | ❌ |
| F-1521 | Budget | Budget Change History expand | tap-toggle | GET `/budget/history` | `toggleBudgetSection('budget-history-shell')` | — | ❌ |
| F-1522 | Budget | Budget history row | display | — | `renderBudgetHistoryRows()` | — | ❌ |
---

## Screen: Bills
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1601 | Bills | Floor obligations section table | display | GET `/floor-obligations` | `_renderFloorWidget()` | — | ❌ |
| F-1602 | Bills | Bills pull-to-refresh indicator | pull-to-refresh | GET `/bills?month=...` | `bills-ptr` with spinner | — | ❌ |
| F-1603 | Bills | Sticky bar — month picker | month-input | GET `/bills?month=` | `bills-filter-month` | — | ❌ |
| F-1604 | Bills | Bills tab — Overview | nav-tap | — | `setBillsTab('overview')` | — | ❌ |
| F-1605 | Bills | Bills tab — Providers | nav-tap | GET `/bills/providers` | `setBillsTab('providers')` | — | ❌ |
| F-1606 | Bills | Bills tab — History | nav-tap | GET `/bills/history` | `setBillsTab('history')` | — | ❌ |
| F-1607 | Bills | Sticky bar — ＋ New Bill button | button | — | `openManualEntryModal('household_bill')` | — | ❌ |
| F-1608 | Bills | Sticky bar — 💸 Log Cash button | button | — | `openCashTransactionModal()` | — | ❌ |
| F-1609 | Bills | Sticky bar — ⬇ CSV export | button | GET `/bills/export.csv?month=` | `exportBillsCsv()` | — | ❌ |
| F-1610 | Bills | Sticky bar — 🖨 Print | button | — | `window.print()` | — | 🔄 Android uses share-as-PDF intent |
| F-1611 | Bills | Bills keyboard shortcut: `n` → New Bill | keyboard-shortcut | — | mentioned in title | — | 🔄 hardware kb optional |
| F-1612 | Bills | Bills keyboard shortcut: `l` → Log Cash | keyboard-shortcut | — | mentioned in title | — | 🔄 hardware kb optional |
| F-1613 | Bills | Alerts strip — due soon | display | derived | `renderBillsAlerts()` | — | ❌ |
| F-1614 | Bills | Alerts strip — anomalies | display | derived | per-bill anomaly | — | ❌ |
| F-1615 | Bills | Alerts strip — missing | display | derived | missing recurring | — | ❌ |
| F-1616 | Bills | Hero card | display | derived | `renderBillsHero()` | — | ❌ |
| F-1617 | Bills | Spotlight container | display | derived | `bills-spotlight-container` | — | ❌ |
| F-1618 | Bills | Due This Week strip | display | derived | `renderDueThisWeekStrip()` | — | ❌ |
| F-1619 | Bills | Obligation card — title tap (provider detail) | button | GET `/bills/providers/<name>` | `openBillProviderDetail()` | — | ❌ |
| F-1620 | Bills | Obligation card — status pill | display | — | overdue / due-soon / paid / autopay | — | ❌ |
| F-1621 | Bills | Obligation card — Expected stat | display | — | `expected_amount` | — | ❌ |
| F-1622 | Bills | Obligation card — Actual stat + variance | display | — | `actual_amount` | — | ❌ |
| F-1623 | Bills | Obligation card — autopay line | display | — | "Paid via autopay on …" | — | ❌ |
| F-1624 | Bills | Obligation card — ✎ Edit button | button | PUT `/bills/service-lines/<id>` | `openBillEditModal()` | — | ❌ |
| F-1625 | Bills | Obligation card — Open Receipt | button | GET `/receipts/<purchase_id>` | `jumpToReceipt()` | — | ❌ |
| F-1626 | Bills | Obligation card — View Payments (personal service) | button | GET `/bills/providers/<name>` | `openBillProviderDetail()` | — | ❌ |
| F-1627 | Bills | Obligation card — Mark Paid (personal) | button | POST `/cash-transactions` | `openCashTransactionModal(...)` | — | ❌ |
| F-1628 | Bills | Obligation card — Mark Unpaid (personal) | button | DELETE `/cash-transactions/<id>` | `markBillUnpaid()` | — | ❌ |
| F-1629 | Bills | Obligation card — Enter Bill (overdue) | button | POST `/receipts` (manual) | `openManualEntryModalFromEncoded()` | — | ❌ |
| F-1630 | Bills | Provider card — title tap → provider detail | button | GET `/bills/providers/<name>` | `openBillProviderDetail()` | — | ❌ |
| F-1631 | Bills | Provider card — sparkline | display | — | `buildSparkPath()` SVG | — | ❌ |
| F-1632 | Bills | Provider card — 12-Month Total | display | — | `provider.total` | — | ❌ |
| F-1633 | Bills | Provider card — Avg / Month | display | — | `provider.average_monthly` | — | ❌ |
| F-1634 | Bills | MoM section — month row + bar | display | — | `renderMoMSection()` | — | ❌ |
| F-1635 | Bills | Recent bill row — Open button | button | GET `/receipts/<purchase_id>` | `jumpToReceipt()` | — | ❌ |
| F-1636 | Bills | Recent bill row — View button (cash) | button | GET `/bills/providers/<name>` | `openBillProviderDetail()` | — | ❌ |
| F-1637 | Bills | Bills "Show all N" expander | button | — | `expandBillsSection()` | — | ❌ |
| F-1638 | Bills | Bills empty-state action button | button | — | `renderBillsEmpty()` actionHtml passthrough | — | ❌ |
---

## Screen: Accounts
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1701 | Accounts | Card Usage header tap (collapse) | tap-toggle | GET `/plaid/card-usage` | `toggleAccountsSection('card-usage-card')` | — | ❌ |
| F-1702 | Accounts | Card Usage — ↻ Refresh button | button | POST `/plaid/accounts/refresh-balances` then GET card-usage | `refreshCardUsage()` | — | ❌ |
| F-1703 | Accounts | Card Usage — summary strip | display | derived | `card-usage-summary` | — | ❌ |
| F-1704 | Accounts | Card Usage — banner | display | derived | `card-usage-banner` warning | — | ❌ |
| F-1705 | Accounts | Card Usage — Spend by Category donut + legend | display | derived | `_renderCardUsagePie()` | — | ❌ |
| F-1706 | Accounts | Card Usage — pie panel filter select | select | — | `_onCardUsageFilterChange()` | — | ❌ |
| F-1707 | Accounts | Card Usage — pie panel collapse caret | button | — | `_cuTogglePanel('card-usage-pie-panel')` | — | ❌ |
| F-1708 | Accounts | Card Usage — Loan Progress panel | display | derived | `_renderLoanProgressPanel()` | — | ❌ |
| F-1709 | Accounts | Card Usage — loan panel collapse caret | button | — | `_cuTogglePanel('card-usage-loans-panel')` | — | ❌ |
| F-1710 | Accounts | Card Usage — credit card tile (image / name / util ring) | display | — | `_renderCreditCardTile()` | — | ❌ |
| F-1711 | Accounts | Card Usage — card row (per account) | display | — | `_renderCardRow()` | — | ❌ |
| F-1712 | Accounts | Card Usage — loan row | display | — | `_renderLoanRow()` mini-donut | — | ❌ |
| F-1713 | Accounts | Connected Accounts header tap (collapse) | tap-toggle | — | `toggleAccountsSection('accounts-connections-card')` | — | ❌ |
| F-1714 | Accounts | Connected Accounts — ＋ Connect Bank button | button | POST `/plaid/link-token` then SDK | `openPlaidLink()` | — | ❌ |
| F-1715 | Accounts | Connected Accounts — 💵 Refresh Balances | button | POST `/plaid/accounts/refresh-balances` | `refreshPlaidBalances()` | — | ❌ |
| F-1716 | Accounts | Connected Accounts — 🔄 Reload button | button | GET `/plaid/items` | `loadConnectedAccounts()` | — | ❌ |
| F-1717 | Accounts | Connected Accounts — per-bank Re-authenticate | button | POST `/plaid/link-token?item_id=...` | `openPlaidLink(itemId)` | — | ❌ |
| F-1718 | Accounts | Connected Accounts — per-bank Sync Now (admin) | button | POST `/plaid/items/<id>/sync` | `syncPlaidItem()` | — | ❌ |
| F-1719 | Accounts | Connected Accounts — per-bank Rename | button | PATCH `/plaid/items/<id>` nickname | `renamePlaidItem()` prompt | — | ❌ |
| F-1720 | Accounts | Connected Accounts — per-bank Share… (admin) | button | PATCH `/plaid/items/<id>` shared_with_user_ids | `sharePlaidItem()` confirm modal | — | ❌ |
| F-1721 | Accounts | Connected Accounts — per-bank Disconnect | button | DELETE `/plaid/items/<id>` | `disconnectPlaidItem()` confirm | — | ❌ |
| F-1722 | Accounts | Connected Accounts — sub-account row balance | display | — | `formatBalanceCents()` | — | ❌ |
| F-1723 | Accounts | Connected Accounts — sync error inline | display | — | `last_sync_error` | — | ❌ |
| F-1724 | Accounts | Activity by Account header tap (collapse) | tap-toggle | GET `/plaid/transaction-breakdown` | `toggleAccountsSection('accounts-breakdown-card')` | — | ❌ |
| F-1725 | Accounts | Activity by Account — per-account row tap (filter) | tap | — | `pickAccountsBreakdownRow()` | — | ❌ |
| F-1726 | Accounts | Activity row — 💳 purchases count | display | — | counts.purchase | — | ❌ |
| F-1727 | Accounts | Activity row — ⚡ autopay count | display | — | counts.autopay | — | ❌ |
| F-1728 | Accounts | Activity row — 💰 interest count | display | — | counts.interest | — | ❌ |
| F-1729 | Accounts | Activity row — ↩ refunds count | display | — | counts.refund | — | ❌ |
| F-1730 | Accounts | Spend by Person header tap (collapse) | tap-toggle | GET `/analytics/spend-by-person` | `toggleAccountsSection('dash-spend-by-person-card')` | — | ❌ |
| F-1731 | Accounts | Spend by Person ‹ prev month | button | GET `/analytics/spend-by-person?month=` | `shiftSpendByPersonMonth(-1)` | — | ❌ |
| F-1732 | Accounts | Spend by Person › next month | button | GET `/analytics/spend-by-person?month=` | `shiftSpendByPersonMonth(1)` | — | ❌ |
| F-1733 | Accounts | Transactions header tap (collapse) | tap-toggle | — | `toggleAccountsSection('accounts-transactions-card')` | — | ❌ |
| F-1734 | Accounts | Transactions tab — All spending | nav-tap | GET `/plaid/transactions?kind=spending` | `setAccountsTransactionsTab('spending')` | — | ❌ |
| F-1735 | Accounts | Transactions tab — Transfers & bills | nav-tap | GET `/plaid/transactions?kind=transfers` | `setAccountsTransactionsTab('transfers')` | — | ❌ |
| F-1736 | Accounts | Transactions — account filter select | select | GET `/plaid/transactions?account_id=` | `resetAccountsTxOffsetAndReload()` | — | ❌ |
| F-1737 | Accounts | Transactions — month picker | month-input | GET `/plaid/transactions?start=&end=` | `resetAccountsTxOffsetAndReload()` | — | ❌ |
| F-1738 | Accounts | Transactions — 🔄 Refresh | button | GET `/plaid/transactions` | `loadPlaidTransactionsList()` | — | ❌ |
| F-1739 | Accounts | Pending review — Confirm All | button | POST `/plaid/staged/confirm-all` | `confirmAllPlaidStaged()` | — | ❌ |
| F-1740 | Accounts | Pending review — per-row Confirm | button | POST `/plaid/staged/<id>/confirm` | per row in `accounts-review-body` | — | ❌ |
| F-1741 | Accounts | Pending review — per-row Reject | button | POST `/plaid/staged/<id>/reject` | per row | — | ❌ |
| F-1742 | Accounts | Transaction row — Open in Receipts | button | GET `/receipts/<purchase_id>` | `jumpToReceipt()` | — | ❌ |
| F-1743 | Accounts | Transaction row — amount + refund tint | display | — | red vs default | — | ❌ |
| F-1744 | Accounts | Pagination ← Prev | button | GET `/plaid/transactions?offset=...` | `changeAccountsTxPage(-1)` | — | ❌ |
| F-1745 | Accounts | Pagination Next → | button | GET `/plaid/transactions?offset=...` | `changeAccountsTxPage(1)` | — | ❌ |
| F-1746 | Accounts | Spending Trends header tap (collapse) | tap-toggle | GET `/plaid/transaction-trends` | `toggleAccountsSection('accounts-trends-card')` | — | ❌ |
| F-1747 | Accounts | Trends — window select (3/6/12) | select | GET `/plaid/transaction-trends?window=` | `loadPlaidSpendingTrends()` | — | ❌ |
| F-1748 | Accounts | Trends — 🔄 refresh button | button | GET `/plaid/transaction-trends` | `loadPlaidSpendingTrends()` | — | ❌ |
| F-1749 | Accounts | Trends — stacked bar chart | display | — | `renderSpendingTrendsChart()` | — | ❌ |
| F-1750 | Accounts | Share-bank modal — per-member checkbox | checkbox | PATCH `/plaid/items/<id>` shared_with_user_ids | inside confirm-overlay | — | ❌ |
---

## Screen: Analytics
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1801 | Analytics | Period select (monthly/weekly) | select | GET `/analytics/spending?period=` | `loadAnalytics()` | — | ❌ |
| F-1802 | Analytics | Domain select (grocery/restaurant/expense/all) | select | GET `/analytics/spending?domain=` | `loadAnalytics()` | — | ❌ |
| F-1803 | Analytics | Sort select (period/total/count) | select | — | `setAnalyticsSort()` | — | ❌ |
| F-1804 | Analytics | "Review Refunds" button | button | GET `/receipts?refunds=1` | `openRefundReceipts()` | — | ❌ |
| F-1805 | Analytics | Refund summary inline | display | GET `/analytics/refunds` | `renderAnalyticsRefundSummary()` | — | ❌ |
| F-1806 | Analytics | Spending Overview body — per-period row tap | tap | GET `/receipts?period=` | drill into period | — | ❌ |
| F-1807 | Analytics | Deals Captured card body | display | GET `/analytics/deals` | `deals-body` | — | ❌ |
---

## Screen: Contributions
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-1901 | Contributions | "How Low-Stock Validation Works" steps | display | — | static 4-step explainer | — | ❌ |
| F-1902 | Contributions | Summary cards grid | display | GET `/contributions/summary` | `contrib-summary-cards` | — | ❌ |
| F-1903 | Contributions | Recent Score Activity — refresh 🔄 | button | GET `/contributions/recent` | `loadContributions()` | — | ❌ |
| F-1904 | Contributions | Recent Score Activity — list row | display | — | per entry | — | ❌ |
| F-1905 | Contributions | Ways To Help — list row | display | GET `/contributions/opportunities` | `contrib-opportunities` | — | ❌ |
| F-1906 | Contributions | Ways To Help — per-row CTA tap | tap | varies | navigates to suggested action | — | ❌ |
| F-1907 | Contributions | How Points Are Earned list | display | GET `/contributions/rules` | `contrib-rules` | — | ❌ |
| F-1908 | Contributions | Fair Scoring Rules list | display | GET `/contributions/notes` | `contrib-notes` | — | ❌ |
---

## Screen: Settings
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-2001 | Settings | Session avatar bubble preview | display | — | `settings-avatar-preview` | — | ❌ |
| F-2002 | Settings | Session summary name | display | GET `/auth/me` | `session-summary-name` | — | ❌ |
| F-2003 | Settings | Session summary sub | display | — | `session-summary-sub` | — | ❌ |
| F-2004 | Settings | "✏️ Change avatar" toggle | button | — | `toggleSessionAvatar()` | — | ❌ |
| F-2005 | Settings | "▼ Details" toggle | button | — | `toggleSessionDetails()` | — | ❌ |
| F-2006 | Settings | "Sign Out" button | button | POST `/auth/logout` | `logout()` | — | ❌ |
| F-2007 | Settings | Avatar emoji input | text-input | PUT `/auth/users/<id>` avatar | `settings-avatar` maxlength 4 | — | ❌ |
| F-2008 | Settings | "Save Avatar" button | button | PUT `/auth/users/<id>` avatar | `saveMyAvatar()` | — | ❌ |
| F-2009 | Settings | Avatar editor Cancel | button | — | `toggleSessionAvatar()` | — | ❌ |
| F-2010 | Settings | Session details — Current login | display | — | `settings-user` disabled | — | ❌ |
| F-2011 | Settings | Session details — Auth Source | display | GET `/auth/me` | `settings-auth-source` | — | ❌ |
| F-2012 | Settings | Session details — Trusted Device | display | GET `/auth/me` | `settings-auth-device` | — | ❌ |
| F-2013 | Settings | Session details — Current Host | display | — | `settings-current-host` | — | ❌ |
| F-2014 | Settings | Session details — Default Pairing Host | display | — | `settings-pairing-host` | — | ❌ |
| F-2015 | Settings | My Activity body | display | GET `/auth/me/stats` | `renderMyActivityCard()` | — | ❌ |
| F-2016 | Settings | Theme picker select | select | — | `setTheme()` light/dark/clay/clay-dark/notion/notion-dark | — | ❌ |
| F-2017 | Settings | Edge-pull overscroll toggle | checkbox | — | `setOverscrollNavEnabled()` localStorage persisted | — | ❌ |
| F-2018 | Settings | Manage Stores — filter pill: All | chip-toggle | GET `/api/stores?filter=all` | `setManageStoresFilter('all')` | — | ❌ |
| F-2019 | Settings | Manage Stores — filter pill: Frequent | chip-toggle | GET `/api/stores?filter=frequent` | `setManageStoresFilter('frequent')` | — | ❌ |
| F-2020 | Settings | Manage Stores — filter pill: Rarely Used | chip-toggle | GET `/api/stores?filter=low_freq` | `setManageStoresFilter('low_freq')` | — | ❌ |
| F-2021 | Settings | Manage Stores — filter pill: Hidden | chip-toggle | GET `/api/stores?filter=hidden` | `setManageStoresFilter('hidden')` | — | ❌ |
| F-2022 | Settings | Manage Stores — per-row bucket select | select | PATCH `/api/stores/<id>` bucket | `renderManageStoresTable()` | — | ❌ |
| F-2023 | Settings | Manage Stores — per-row last-purchase display | display | — | recency | — | ❌ |
| F-2024 | Settings | Household Users — "+ Add User" | button | — | `openHouseholdUserForm()` (admin) | — | ❌ |
| F-2025 | Settings | Household Users — "+ Service Account" | button | POST `/auth/service-accounts` | `openServiceAccountForm()` (admin) | — | ❌ |
| F-2026 | Settings | Household Users — Sort select | select | — | `setUsersSort()` name/role/status/created | — | ❌ |
| F-2027 | Settings | Household Users — Refresh 🔄 | button | GET `/auth/users` | `loadUsers()` | — | ❌ |
| F-2028 | Settings | Invite — Email input | text-input | POST `/auth/invites` | `invite-email` | — | ❌ |
| F-2029 | Settings | Invite — Name input | text-input | POST `/auth/invites` | `invite-name` | — | ❌ |
| F-2030 | Settings | Invite — Role select | select | POST `/auth/invites` | user / admin | — | ❌ |
| F-2031 | Settings | Invite — Send Invite Link button | button | POST `/auth/invites` | `createInvite()` | — | ❌ |
| F-2032 | Settings | Invite — Cancel button | button | — | `hideHouseholdUserForm()` | — | ❌ |
| F-2033 | Settings | Invite — Result link readonly input | display | — | `invite-result-url` | — | ❌ |
| F-2034 | Settings | Invite — Copy link button | button | — | `copyInviteLink()` | — | ❌ |
| F-2035 | Settings | Classic user — Name input | text-input | POST `/auth/users` | `user-name` | — | ❌ |
| F-2036 | Settings | Classic user — Email input | text-input | POST `/auth/users` | `user-email` | — | ❌ |
| F-2037 | Settings | Classic user — Password input | password-input | POST `/auth/users` | `user-password` | — | ❌ |
| F-2038 | Settings | Classic user — Avatar input | text-input | POST `/auth/users` | `user-avatar` | — | ❌ |
| F-2039 | Settings | Classic user — Role select | select | POST `/auth/users` | user/admin | — | ❌ |
| F-2040 | Settings | Classic user — Add button | button | POST `/auth/users` | `createUser()` | — | ❌ |
| F-2041 | Settings | Pending invites — list rows | display | GET `/auth/invites` | `pending-invites-body` | — | ❌ |
| F-2042 | Settings | Pending invite — Revoke | button | DELETE `/auth/invites/<id>` | per-row | — | ❌ |
| F-2043 | Settings | Pending invite — Copy link | button | — | per-row | — | ❌ |
| F-2044 | Settings | Users table row — role badge | display | — | per row | — | ❌ |
| F-2045 | Settings | Users table row — Edit | button | PUT `/auth/users/<id>` | per row | — | ❌ |
| F-2046 | Settings | Users table row — Delete | button | DELETE `/auth/users/<id>` | per row | — | ❌ |
| F-2047 | Settings | Users table row — Rotate (service account) | button | POST `/auth/service-accounts/<id>/rotate` | per row | — | ❌ |
| F-2048 | Settings | Trusted Devices — "Pair New Device" | button | POST `/auth/device-pairing/start` | `openDevicePairingModal()` | — | ❌ |
| F-2049 | Settings | Trusted Devices — Refresh 🔄 | button | GET `/auth/trusted-devices` | `loadTrustedDevices()` | — | ❌ |
| F-2050 | Settings | Trusted Devices row — Rename | button | PUT `/auth/trusted-devices/<id>` | per-row | — | ❌ |
| F-2051 | Settings | Trusted Devices row — Revoke | button | POST `/auth/trusted-devices/<id>/revoke` | per-row | — | ❌ |
| F-2052 | Settings | Trusted Devices row — Delete | button | DELETE `/auth/trusted-devices/<id>` | per-row | — | ❌ |
| F-2053 | Settings | Snapshot Review refresh 🔄 | button | GET `/product-snapshots/review-queue` | `loadSnapshotReviewQueue()` | — | ❌ |
| F-2054 | Settings | Snapshot Review row — Approve | button | POST `/product-snapshots/<id>/approve` | per-row | — | ❌ |
| F-2055 | Settings | Snapshot Review row — Reject | button | POST `/product-snapshots/<id>/reject` | per-row | — | ❌ |
| F-2056 | Settings | Environment Backup — Create | button | POST `/system/backups` | `createEnvironmentBackup()` | — | ❌ |
| F-2057 | Settings | Environment Backup — Upload | file-pick | POST `/system/backups/upload` | `triggerEnvironmentBackupUpload()` | — | ❌ |
| F-2058 | Settings | Environment Backup — Verify | button | POST `/system/verify` | `verifyEnvironmentBackup()` | — | ❌ |
| F-2059 | Settings | Environment Backup — Refresh 🔄 | button | GET `/system/backups` | `loadEnvironmentBackups()` | — | ❌ |
| F-2060 | Settings | Environment Backup — Restore Source select | select | — | `environment-backup-select` | — | ❌ |
| F-2061 | Settings | Environment Backup — Restore Selected button | button | POST `/system/restore` | `openEnvironmentRestoreModal()` | — | ❌ |
| F-2062 | Settings | Environment Backup — progress bar | display | — | `renderEnvironmentRestoreProgress()` | — | ❌ |
| F-2063 | Settings | Environment Backup — report | display | — | `renderEnvironmentReport()` | — | ❌ |
| F-2064 | Settings | Catalog Review — status filter select | select | GET `/products/review-queue?status=` | `loadReviewQueue()` | — | ❌ |
| F-2065 | Settings | Catalog Review — ✨ Run Gemini | button | POST `/products/enhance-batch` | `runBulkEnhancement()` | — | ❌ |
| F-2066 | Settings | Catalog Review — Refresh 🔄 | button | GET `/products/review-queue` | `loadReviewQueue()` | — | ❌ |
| F-2067 | Settings | Catalog Review row — Apply | button | POST `/products/review-queue/<id>/apply` | per-row | — | ❌ |
| F-2068 | Settings | Catalog Review row — Dismiss | button | POST `/products/review-queue/<id>/dismiss` | per-row | — | ❌ |
| F-2069 | Settings | AI Model Registry — "+ New Model" | button | — | `openAdminAiModelEditorForNew()` | — | ❌ |
| F-2070 | Settings | AI Model Registry — Refresh 🔄 | button | GET `/api/admin/models` | `loadAdminAiModels()` | — | ❌ |
| F-2071 | Settings | Model editor — Name input | text-input | POST/PUT `/api/admin/models` | `admin-ai-model-name` | — | ❌ |
| F-2072 | Settings | Model editor — Provider select | select | POST/PUT `/api/admin/models` | gemini/openai/openrouter/ollama/anthropic | — | ❌ |
| F-2073 | Settings | Model editor — Model String input | text-input | POST/PUT `/api/admin/models` | provider-native id | — | ❌ |
| F-2074 | Settings | Model editor — Price Tier select | select | POST/PUT `/api/admin/models` | free/premium/pro/enterprise | — | ❌ |
| F-2075 | Settings | Model editor — Credential Mode select | select | POST/PUT `/api/admin/models` | env / stored_key / no_key_required | — | ❌ |
| F-2076 | Settings | Model editor — Base URL input | text-input | POST/PUT `/api/admin/models` | optional | — | ❌ |
| F-2077 | Settings | Model editor — Description input | text-input | POST/PUT `/api/admin/models` | label | — | ❌ |
| F-2078 | Settings | Model editor — Stored API Key input | password-input | POST/PUT `/api/admin/models` | `handleAdminAiModelKeyInput()` | — | ❌ |
| F-2079 | Settings | Model editor — Sort Order input | number-input | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2080 | Settings | Model editor — Input $ / 1M Tokens | number-input | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2081 | Settings | Model editor — Output $ / 1M Tokens | number-input | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2082 | Settings | Model editor — Enabled checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2083 | Settings | Model editor — Visible checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2084 | Settings | Model editor — Vision checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2085 | Settings | Model editor — PDF checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2086 | Settings | Model editor — JSON checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2087 | Settings | Model editor — Image Input checkbox | checkbox | POST/PUT `/api/admin/models` | — | — | ❌ |
| F-2088 | Settings | Model editor — Clear stored key checkbox | checkbox | PATCH `/api/admin/models/<id>` clear_key | — | — | ❌ |
| F-2089 | Settings | Model editor — Save | button | POST/PUT `/api/admin/models` | `saveAdminAiModel()` | — | ❌ |
| F-2090 | Settings | Model editor — Clear | button | — | `resetAdminAiModelForm()` | — | ❌ |
| F-2091 | Settings | Model editor — Cancel | button | — | `hideAdminAiModelEditor()` | — | ❌ |
| F-2092 | Settings | AI Models row — Edit | button | PUT `/api/admin/models/<id>` | `renderAdminAiModels()` | — | ❌ |
| F-2093 | Settings | AI Models row — Toggle enabled | button | PATCH `/api/admin/models/<id>` enabled | per-row | — | ❌ |
| F-2094 | Settings | AI Models row — Delete | button | DELETE `/api/admin/models/<id>` | per-row | — | ❌ |
| F-2095 | Settings | AI Usage — days select | select | GET `/api/admin/models/usage?days=` | `loadAdminAiUsage()` | — | ❌ |
| F-2096 | Settings | AI Usage refresh 🔄 | button | GET `/api/admin/models/usage` | `loadAdminAiUsage()` | — | ❌ |
| F-2097 | Settings | Image Backfill — provider select | select | — | auto/gemini/openai | — | ❌ |
| F-2098 | Settings | Image Backfill — Refresh candidates | button | GET `/image-backfill/candidates` | `loadImageBackfillCandidates()` | — | ❌ |
| F-2099 | Settings | Image Backfill — Run | button | POST `/image-backfill/run` | `runImageBackfill()` | — | ❌ |
| F-2100 | Settings | Image Backfill — history window select | select | GET `/image-backfill/history?days=` | `loadImageBackfillHistory()` | — | ❌ |
| F-2101 | Settings | Image Backfill — history refresh | button | GET `/image-backfill/history` | | — | ❌ |
| F-2102 | Settings | Image Backfill — schedule Enabled checkbox | checkbox | PUT `/image-backfill/schedule` | inline | — | ❌ |
| F-2103 | Settings | Image Backfill — schedule hour input | number-input | PUT `/image-backfill/schedule` | 0-23 | — | ❌ |
| F-2104 | Settings | Image Backfill — schedule minute input | number-input | PUT `/image-backfill/schedule` | 0-59 | — | ❌ |
| F-2105 | Settings | Image Backfill — 💾 Save schedule | button | PUT `/image-backfill/schedule` | `saveImageBackfillSchedule()` | — | ❌ |
| F-2106 | Settings | Image Backfill — Next run display | display | — | `renderImageBackfillNextRun()` | — | ❌ |
| F-2107 | Settings | Image Backfill — candidate row select checkbox | checkbox | — | toggle for batch run | — | ❌ |
| F-2108 | Settings | Image Backfill — body table | display | — | `renderImageBackfillCandidates()` | — | ❌ |
| F-2109 | Settings | Chat Audit — limit select | select | GET `/chat/audit?limit=` | `loadChatAudit()` | — | ❌ |
| F-2110 | Settings | Chat Audit refresh 🔄 | button | GET `/chat/audit` | `loadChatAudit()` | — | ❌ |
| F-2111 | Settings | Chat Audit body — per-row tap (expand prompt) | tap-toggle | — | per-row | — | ❌ |
| F-2112 | Settings | API Token input (password) | password-input | — | `settings-token` | — | ❌ |
| F-2113 | Settings | API Token Save button | button | PUT `/auth/me/token` | `saveToken()` | — | ❌ |
| F-2114 | Settings | API Token show/hide 👁 | button | — | `toggleTokenVis()` | — | ❌ |
| F-2115 | Settings | API Base URL input | text-input | — | `settings-url` | — | ❌ |
| F-2116 | Settings | "✅ Save Settings" button | button | — | `saveSettings()` writes to localStorage | — | ❌ |
| F-2117 | Settings | Settings card collapse-by-default | tap-toggle | — | `applySettingsCollapsibles()` | — | ❌ |
---

## Screen: SharedModals
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-2201 | SharedModals | Confirm overlay — OK button | button | — | `confirm-ok` | — | ❌ |
| F-2202 | SharedModals | Confirm overlay — Cancel button | button | — | `confirm-cancel` | — | ❌ |
| F-2203 | SharedModals | Confirm overlay — backdrop tap close | tap | — | overlay click | — | ❌ |
| F-2204 | SharedModals | Confirm overlay — Esc keyboard close | keyboard-shortcut | — | document.onkeydown | — | 🔄 native back gesture covers verb |
| F-2205 | SharedModals | Manual entry overlay — Receipt Type select | select | POST `/receipts` (manual) | `manual-entry-type` | — | ❌ |
| F-2206 | SharedModals | Manual entry — Transaction select | select | POST `/receipts` | purchase/refund | — | ❌ |
| F-2207 | SharedModals | Manual entry — Store input | text-input | POST `/receipts` | `manual-entry-store` | — | ❌ |
| F-2208 | SharedModals | Manual entry — Date input | date-input | POST `/receipts` | `manual-entry-date` | — | ❌ |
| F-2209 | SharedModals | Manual entry — Subtotal input | number-input | POST `/receipts` | `manual-entry-subtotal` | — | ❌ |
| F-2210 | SharedModals | Manual entry — Tax input | number-input | POST `/receipts` | `manual-entry-tax` | — | ❌ |
| F-2211 | SharedModals | Manual entry — Total input | number-input | POST `/receipts` | `manual-entry-total` | — | ❌ |
| F-2212 | SharedModals | Manual entry — Tip input | number-input | POST `/receipts` | `manual-entry-tip` | — | ❌ |
| F-2213 | SharedModals | Manual entry — Refund Reason select | select | POST `/receipts` | inside refund fields | — | ❌ |
| F-2214 | SharedModals | Manual entry — Refund Note input | text-input | POST `/receipts` | `manual-entry-refund-note-text` | — | ❌ |
| F-2215 | SharedModals | Manual entry — Bill Provider Name input | text-input | POST `/receipts` | `manual-entry-bill-provider-name` | — | ❌ |
| F-2216 | SharedModals | Manual entry — Bill Provider Type select | select | POST `/receipts` | `manual-entry-bill-provider-type` | — | ❌ |
| F-2217 | SharedModals | Manual entry — Service Types checkboxes | checkbox | POST `/receipts` | `manual-entry-bill-service-types` | — | ❌ |
| F-2218 | SharedModals | Manual entry — Account Label input | text-input | POST `/receipts` | `manual-entry-bill-account-label` | — | ❌ |
| F-2219 | SharedModals | Manual entry — Billing Cycle Month month-input | month-input | POST `/receipts` | `manual-entry-bill-billing-cycle-month` | — | ❌ |
| F-2220 | SharedModals | Manual entry — Billing Cycle select | select | POST `/receipts` | `manual-entry-bill-billing-cycle` | — | ❌ |
| F-2221 | SharedModals | Manual entry — Service Period Start date | date-input | POST `/receipts` | `manual-entry-bill-service-period-start` | — | ❌ |
| F-2222 | SharedModals | Manual entry — Service Period End date | date-input | POST `/receipts` | `manual-entry-bill-service-period-end` | — | ❌ |
| F-2223 | SharedModals | Manual entry — Due Date date | date-input | POST `/receipts` | `manual-entry-bill-due-date` | — | ❌ |
| F-2224 | SharedModals | Manual entry — Recurring checkbox | checkbox | POST `/receipts` | `manual-entry-bill-is-recurring` | — | ❌ |
| F-2225 | SharedModals | Manual entry — items table — Add row | button | — | `addManualEntryItemRow()` | — | ❌ |
| F-2226 | SharedModals | Manual entry — item name input | text-input | POST `/receipts` | per row | — | ❌ |
| F-2227 | SharedModals | Manual entry — item qty input | number-input | POST `/receipts` | per row | — | ❌ |
| F-2228 | SharedModals | Manual entry — item price input | number-input | POST `/receipts` | per row | — | ❌ |
| F-2229 | SharedModals | Manual entry — item delete | button | — | per row | — | ❌ |
| F-2230 | SharedModals | Manual entry — Cancel | button | — | `manual-entry-cancel` | — | ❌ |
| F-2231 | SharedModals | Manual entry — Save | button | POST `/receipts` (manual) | `manual-entry-save` | — | ❌ |
| F-2232 | SharedModals | Cash transaction modal — provider input | text-input | POST `/cash-transactions` | with datalist | — | ❌ |
| F-2233 | SharedModals | Cash transaction modal — amount | number-input | POST `/cash-transactions` | — | — | ❌ |
| F-2234 | SharedModals | Cash transaction modal — date | date-input | POST `/cash-transactions` | — | — | ❌ |
| F-2235 | SharedModals | Cash transaction modal — payment method select | select | POST `/cash-transactions` | `renderCashPaymentMethodOptions()` | — | ❌ |
| F-2236 | SharedModals | Cash transaction modal — service type select | select | POST `/cash-transactions` | `renderCashServiceTypeOptions()` | — | ❌ |
| F-2237 | SharedModals | Cash transaction modal — provider picker filter | text-input | — | `renderCashProviderPicker()` | — | ❌ |
| F-2238 | SharedModals | Cash transaction modal — Save | button | POST `/cash-transactions` | submits | — | ❌ |
| F-2239 | SharedModals | Device pairing modal — generated QR image | display | GET `/auth/qr-image` | `device-pairing-modal` | — | ❌ |
| F-2240 | SharedModals | Device pairing modal — copy link button | button | — | clipboard | — | ❌ |
| F-2241 | SharedModals | Device pairing modal — refresh / regenerate token | button | POST `/auth/device-pairing/start` | per-modal | — | ❌ |
| F-2242 | SharedModals | Image zoom overlay — close on backdrop tap | tap | — | `openProductSnapshot()` / `openShoppingSnapshot()` | — | ❌ |
| F-2243 | SharedModals | Image zoom overlay — pinch zoom | gesture | — | mobile gesture (web uses inline scale) | — | 🔄 Android pinch-zoom native viewer |
| F-2244 | SharedModals | Attribution picker — household chip | chip-toggle | PATCH `/receipts/<id>` attribution | `toggleAttributionPicker()` | — | ❌ |
| F-2245 | SharedModals | Attribution picker — per-person checkbox | checkbox | PATCH `/receipts/<id>` attribution | multi-select shared | — | ❌ |
| F-2246 | SharedModals | Attribution picker — Apply | button | PATCH `/receipts/<id>` attribution | persist | — | ❌ |
| F-2247 | SharedModals | Refund Receipts overlay — list rows | display | GET `/receipts?refunds=1` | `openRefundReceipts()` | — | ❌ |
| F-2248 | SharedModals | Refund Receipts overlay — close button | button | — | per-modal | — | ❌ |
| F-2249 | SharedModals | Bill edit modal — fields (provider/type/cycle/amount/...) | text/select/number/date | PUT `/bills/service-lines/<id>` | `openBillEditModal()` | — | ❌ |
| F-2250 | SharedModals | Bill edit modal — Save | button | PUT `/bills/service-lines/<id>` | submits | — | ❌ |
| F-2251 | SharedModals | Variant picker (kitchen) — variant tile tap | tap | POST `/shopping-list/items` | per-variant | — | ❌ |
| F-2252 | SharedModals | Variant picker — close | button | — | per-modal | — | ❌ |
| F-2253 | SharedModals | Toast — undo button | button | varies | `_invShowUndoToast` | — | ❌ |
---

## Screen: DesignGallery
---
| Row ID | Screen | UI Element | Action / Verb | Endpoint | Web Impl Notes | Android Impl | Status |
|--------|--------|-----------|---------------|----------|----------------|--------------|--------|
| F-2401 | DesignGallery | Apple swatch grid | display | — | `renderAppleGallerySwatches()` | — | 🚫 Dev-only design gallery; explicitly out of scope for Android |
| F-2402 | DesignGallery | Clay swatch grid | display | — | `renderClayGallery()` | — | 🚫 Dev-only |
| F-2403 | DesignGallery | Theme picker preview cards | tap | — | live preview | — | 🚫 Dev-only |
---

# audit-complete: rows=822 screens=22
