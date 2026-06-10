# Agent Learnings — LocalOCR macOS Build

> Living document. Capture every incident where the user had to step in
> with a corrective prompt or a manual validation step. Each entry locks
> in a rule so the same class of mistake doesn't recur.
>
> Goal: drive the user-as-QA-burden toward zero. Build agents should
> self-verify before claiming a task is done.

---

## 1. Why this file exists

During the macOS build, the user has had to repeatedly:
- Take screenshots of broken UI to surface bugs that should have been caught by the agent
- Open Console.app and paste logs that the agent should have grabbed itself
- Point out endpoint path mismatches that the agent should have grepped before writing decoders
- Re-prompt to push, install, or run unit tests that should be part of every commit cycle
- Validate that the registry-driven workflow was actually being followed

Each round-trip costs ~5 minutes of human time. Across a 50-row dashboard build that's 30+ interventions. **The agent should hit zero of those by validating itself before reporting done.**

This file is the institutional memory. Future agents read it on session start (or via skill) and treat its rules as binding.

---

## 2. Incidents — what went wrong + what fixed it

### I-1: Plan claimed 30 features; reality was 894 atomic items
- **Symptom**: After 8 phases of "implementation complete", screens still missing sub-tabs, modals, inline editors, loading/empty/error states.
- **Root cause**: The 7-agent plan synthesized features at the **screen** level. Each "screen" was treated as one bullet. Real web frontend has ~50 atomic features per screen.
- **User prompt that exposed it**:
  > "i want our app to feel and have all the functionalities of web we should not miss any of it"
- **Fix**: Built `FEATURE_PARITY_REGISTRY.md` — 894 atomic rows. Workflow rule locked in:
  > Before implementing any screen → `grep "Screen: <name>" FEATURE_PARITY_REGISTRY.md` → implement every ❌ → mark ✅ / 🔄 → report counts.
- **Rule locked in**: **No screen is "done" until its registry rows are all closed.** Audit before plan, not after.

---

### I-2: Backend wraps lists in envelopes; client decoded bare arrays
- **Symptom**: After prod login: Inventory empty, Receipts empty, Shopping empty, Bills empty.
- **Root cause**: Client expected `[InventoryItem]` direct array. Backend returns `{"inventory": [...], "count": N}`. JSONDecoder silently fails → catch returns nothing → state shows empty.
- **User prompt that exposed it**:
  > "i logged into app with production url, why is there no data available?"
- **Fix**: Added wrapper response types (`InventoryListResponse`, `ReceiptsListResponse`, `ShoppingListResponse`, `ObligationsListResponse`). Updated state managers to decode wrappers then extract arrays.
- **Rule locked in**: **Read the actual `return jsonify({...})` Python code before writing any Codable struct.** Mirror the wrapper key exactly.

---

### I-3: Endpoint paths invented from plan instead of grepped from backend
- **Symptom**: Shopping list endpoint hit `/shopping`, but backend prefix is `/shopping-list`. Inventory mutations used POST `/<id>/adjust`, but backend uses PUT `/<id>/consume`. Receipt confirm called `/<id>/confirm`, backend uses `/<id>/approve`. Bills mark-paid called a path that doesn't exist.
- **Root cause**: Plan made up plausible-looking paths. Agent didn't cross-reference against the actual blueprint routes.
- **User prompt that exposed it**: same as I-2 (no data).
- **Fix**: Grep every blueprint:
  ```sh
  grep -E "@.*\.route|Blueprint\(" src/backend/<file>.py
  ```
  Use the literal `url_prefix` + route path. Methods come from the `methods=[...]` list.
- **Rule locked in**: **Every `Endpoint` enum case must have a Bash command pinned to it that proves the path exists.** No path may be invented.

---

### I-4: Analytics endpoint wrong — `/spending` ≠ `/spending-by-category`
- **Symptom**: Dashboard "Spending by Category" card empty.
- **Root cause**: Web uses `/analytics/spending-by-category?month=YYYY-MM&limit=50`. Agent used `/analytics/spending` (a different rollup endpoint).
- **User prompt that exposed it**:
  > "why is that it did not populate spending by category? i am using prod url"
- **Fix**: For any web visual we're reproducing, grep `index.html` for the literal fetch URL:
  ```sh
  grep -n "fetch\|api(" src/frontend/index.html | grep -i "<feature>"
  ```
- **Rule locked in**: **Match the web's exact endpoint when porting a web visual.** Two endpoints with similar names are not interchangeable.

---

### I-5: Schema field naming — flat vs nested
- **Symptom**: Inventory items decoded with `nil` product names because client expected nested `product: Product?` but backend emits flat `product_name`, `category`, `brand`, etc.
- **Root cause**: Plan assumed normalized nested schemas because that's "good API design". Backend chose flat for ease of use.
- **Fix**: Inspect a concrete JSON payload (curl or browser DevTools) before designing the model. Mirror the exact shape.
- **Rule locked in**: **Reality > opinion. Mirror the backend schema verbatim**, even if it would be "cleaner" to nest.

---

### I-6: `async let _ = foo()` cancellation bug
- **Symptom**: Dashboard endpoints all logging "cancelled" every ~200 ms in an infinite loop. No data ever appeared. PROD=0, Spending empty, Receipts Processed empty.
- **Root cause**: `async let _ = foo()` in Swift Concurrency creates a child task but the `_ =` discards the binding. The child is never explicitly awaited, so when the parent function returns, the children are cancelled. `URLSession.data(for:)` throws `CancellationError` ~2 ms after start.
- **User prompts that exposed it**:
  > "still nope spending by category is empty"
  > "did hard refresh, no luck, quit app, signed out, signed in no luck"
- **Diagnosis tool**: `log show --last 30s --predicate 'subsystem == "com.localocr.extended"' --info --debug` — showed the cancel cascade.
- **Fix**:
  ```swift
  await withTaskGroup(of: Void.self) { group in
      group.addTask { @MainActor in await self.loadLeaderboard() }
      group.addTask { @MainActor in await self.loadSpendingByCategory() }
      // ...
  }
  ```
- **Rule locked in**: **NEVER write `async let _ =`.** For parallel: `withTaskGroup`. For sequential: explicit `await` chain. For fire-and-forget from a SwiftUI view: `Task.detached(priority: .userInitiated)` — NOT `.task { ... }` which auto-cancels on view-identity change.

---

### I-7: `.task` modifier auto-cancels on view re-render
- **Symptom**: Same "cancelled" symptom but spread across all four state managers (inventory, shopping, finance, dashboard).
- **Root cause**: SwiftUI's `.task { await refreshAll() }` cancels its closure when the view's body re-evaluates with a different identity. Heavy `@Published` traffic triggered frequent re-evals → frequent cancellations.
- **Fix**: Switch to `.onAppear { Task.detached(priority: .userInitiated) { await … } }`. Detached tasks aren't tied to view lifecycle.
- **Rule locked in**: **Reserve `.task` for short, idempotent, view-bound work (≤500 ms).** For any data fetch fan-out, use detached.

---

### I-10: Recurring red error on every launch — system-rejected API treated as caller error
- **Symptom**: `requestAuthorization failed: The operation couldn't be completed. (UNErrorDomain error 1.)` fired on every launch. The error count grew with every reinstall, polluting Console.app and obscuring real errors during log validation (Rule 6).
- **Root cause**: Unsigned macOS builds cannot request notification permission — the system rejects `UNUserNotificationCenter.requestAuthorization` with `UNError code 1` (`notificationsNotAllowed`) BEFORE prompting the user. `authorizationStatus` stays `.notDetermined` forever, so the `guard` in `requestAuthorizationIfNeeded` keeps letting the call through on every launch. The code logged at `.warning` level — a system-environment limitation surfaced as if it were a caller bug.
- **Promoted from §10**: had been on the open-scar list for 3+ sessions before being locked in.
- **User prompt that exposed it**:
  > "promote UNErrorDomain first"
- **Fix**: latch the rejection in UserDefaults (`LocalOCR.notificationRequestRejected`). On `UNErrorDomain 1`, set the flag, log at `.info`, and skip the call on every subsequent launch until the binary is signed or the user clears the flag. A successful prompt clears the flag.
- **Rule locked in**: **When a system framework rejects a call with a code that means "the environment forbids this", don't log it as an error and don't retry every launch. Latch the rejection in UserDefaults, log at .info, gate the next attempt behind a state change.** Generalize: distinguish *transient caller errors* (retry next time) from *environmental capability errors* (latch + don't retry).

---

### I-14: Fix-agent touched a file but left a pre-existing RULE 3 violation in place
- **Symptom**: AUDIT_A2 grep `async let _ = ` returned 4 live matches in `Views/Dashboard/DashboardView.swift:82-85` inside `refreshAll()` (called from the Dashboard toolbar refresh Button at line 52). The exact I-6 cancellation pattern was sitting in production code on the same branch where the fix-agent had just committed FIX-027 (`549ca94 fix: FIX-027 — Dashboard untagged-nudge`) and FIX-047 (`9b621fa fix: FIX-047 — Dashboard spending row expand`) — both touching the very same file.
- **Root cause**: Fix-agent treats each FIX as a surgical patch limited to the spec's named lines. When it edits a file, it does not re-grep the rest of the file for active RULE violations. The pre-existing `async let _ = ` block dated back to `fb205a0 (feat(macos): rich Dashboard)` and survived every later edit because no FIX spec mentioned it. Worse, the same codebase has comments in `InventoryState.swift:10,628`, `ReceiptsState.swift:307`, and `AppMenuCommands.swift:93` that explicitly warn against this exact pattern — proof that the agent *knows* the rule but only applies it to net-new code.
- **User prompt that exposed it**: (caught by AUDIT_A2 regression grep before the user saw a "cancelled" cascade — Rule 6 working as intended)
- **Fix**: `refreshAll()` needs to be rewritten as `withTaskGroup` (per `agent-rules.md` Rule 3 correct pattern). Pending a separate FIX commit; AUDIT_A2 logs it as CA2-R-001.
- **Rule locked in**: **When a fix-agent edits any file, before committing it must run the active rule-grep pass on the *entire* file (not just the touched lines) and remediate any live RULE violation it finds. Pre-existing violations in a touched file are the fix-agent's responsibility — silence about a known anti-pattern in a touched file is a regression.** Generalize: every time you write to a file, treat the whole file as your problem, not just the diff hunk.

---

### I-13: SwiftUI ViewBuilder infinite recursion via same-shape sub-data → EXC_BAD_ACCESS stack overflow
- **Symptom**: Accounts → Card Usage section crashed on first render with `EXC_BAD_ACCESS (KERN_PROTECTION_FAILURE)` and "Thread stack size exceeded due to excessive recursion" in the crash report (`~/Library/Logs/DiagnosticReports/LocalOCR-...ips`). Log show was clean — all 3 endpoints reported `loaded N` lines before the crash. xcodebuild was green. Crash fired the moment SwiftUI started laying out the credit-card group with at least one owner-tagged account.
- **Root cause**: `CardGroupView` detected `anyOwner = group.accounts.contains { ... ownerLabel non-empty }`. When true, it iterated owner sub-groups and rendered each as an `OwnerSubgroup`. `OwnerSubgroup` then called back into `CardGroupView` with the sub-group's accounts — which all shared the same `owner_label`, so `anyOwner` re-evaluated to `true` and the recursion never bottomed out. SwiftUI's ViewBuilder isn't tail-call optimized and AttributeGraph happily expanded the tree until the thread stack guard page tripped.
- **User prompt that exposed it**: (caught by self-audit — Rule 6 reinstall-and-driveable check spotted the crash before user saw a broken screen; no user prompt required)
- **Fix**: Inline the chip-strip + tile-grid body directly inside `OwnerSubgroup` instead of re-entering `CardGroupView`. Same code, no recursion. Build green, app stable, 6 items / 13 sub-accounts / 12 cards-overview loaded — Card Usage section renders correctly with two owner sub-groups visible.
- **Rule locked in**: **A SwiftUI view that conditionally branches on a property of its data and renders a sub-view of the same type with the same property pattern is recursive — assume infinite recursion until proven otherwise.** Either (a) pass a depth/flag parameter that suppresses the branch on the recursive call, or (b) inline the leaf-shape body in the wrapping view so the recursion bottoms out. Symptoms are misleading: clean compile, clean log, then `EXC_BAD_ACCESS` deep inside `SwiftUICore`/`AttributeGraph` frames. Check `~/Library/Logs/DiagnosticReports/<app>*.ips` for "excessive recursion" when SwiftUI crashes mid-layout.

---

### I-12: Kingfisher image cookies never shared — in-place URLSessionConfiguration mutation is silently ignored
- **Symptom**: After F-145 was implemented (per-row product snapshot via Kingfisher) and the build looked correct, side-by-side with the web app showed **every** mac row falling back to the initials chip — even for items whose backend payload included `latest_snapshot.image_url`. Backend `curl` with the same session cookie returned the JPEGs fine (HTTP 200). The Receipts tab also showed only placeholders, proving the bug was global to Kingfisher, not specific to inventory.
- **Root cause**: `ImageCache.configureSharedCookies()` was written as three in-place mutations on `KingfisherManager.shared.downloader.sessionConfiguration` (`httpCookieAcceptPolicy`, `httpShouldSetCookies`, `httpCookieStorage`). `URLSession` snapshots its `URLSessionConfiguration` at session-creation time — Kingfisher creates its downloader session lazily on first image load, and from that moment onward later in-place writes to the captured config object do nothing. Cookies stayed in Kingfisher's private cookie jar (empty), so requests went out unauthenticated, the server returned 401, and KFImage fell through to the `placeholder` view forever.
- **User prompt that exposed it**: (caught by self-audit during the Rule 11 screenshot diff against the web app, before user had to step in — Rule 11 working as intended)
- **Fix**: Build a *fresh* `URLSessionConfiguration`, populate it with the shared cookie jar + the same cache/timeout knobs APIClient uses, then assign the whole `sessionConfiguration` property in one shot. Kingfisher's property setter rebuilds the session, so the new cookie storage actually takes effect. Verified by reinstalling, re-screenshotting Inventory, and confirming real product photos render for the rows the backend reports as having snapshots — and the initials chip still appears for rows whose backend response carries `latest_snapshot: null`.
- **Rule locked in**: **`URLSession` captures its `URLSessionConfiguration` at session-creation time — mutating sub-properties of an already-attached config does nothing. Always build a fresh config locally, set every knob you care about, and assign the whole property in a single statement (or pass it into `URLSession(configuration:)` before the session is ever used).** Anti-pattern: `KingfisherManager.shared.downloader.sessionConfiguration.httpCookieStorage = HTTPCookieStorage.shared`. Correct: `let cfg = URLSessionConfiguration.default; cfg.httpCookieStorage = HTTPCookieStorage.shared; KingfisherManager.shared.downloader.sessionConfiguration = cfg`. Generalize: any framework that exposes a `sessionConfiguration` property is presumed to back it with a setter that rebuilds the session — go through the setter, not the captured object's sub-fields.

---

### I-11: Coarse registry rows hide visible web behaviors that never get their own ❌
- **Symptom**: Inventory screen passed RULE 9 verb-check (all F-100..F-144 marked ✅/🔄/🚫). User opened it side-by-side with the web and found three visible features missing: per-tile product photos, per-tile +3d defer button, and "N expiring soon" tail on every section header. None of these had a dedicated registry row — they were rolled up inside F-132 "Inventory tile groups container (Rendered by `renderInventory()`)" and F-133 "Inventory tile — consume action (inline)".
- **Root cause**: The deep-audit registry treats one DOM function call as one row. `renderInventory()` and `_invBuildTile()` each render half a dozen sub-elements (image, status pill, defer button, expiry tag, etc.), but the registry only enumerates them when they have their own `id=` or are referenced by name in JS. Anything assembled inline by the renderer is invisible to the registry — and therefore invisible to RULE 9. The agent dutifully checked every verb that appeared in a row; the missing rows had no verbs to check.
- **User prompt that exposed it**:
  > "Product images missing on every inventory card / 'defer' button missing from row actions / Expiring count missing from section headers"
- **Fix**:
  1. Added F-145 (per-tile product snapshot image), F-146 (per-tile defer), F-147 (group-header expiring count) to FEATURE_PARITY_REGISTRY.md.
  2. Implemented Kingfisher-backed `ProductSnapshotThumb`, "+3d / ⌥+7d" Button in `InventoryRow`, and `groupHeader(title:rows:)` with `InventoryState.expiringSoonCount` (threshold matches web's `_invClassifyExpiry`: `daysLeft <= 3`).
  3. New rows added 2026-05-19 with explicit justification linking back to this incident.
- **Rule locked in**: **Before marking a parent "renderX()" row ✅, do a literal pixel-diff against the running web app — open both apps side by side, screenshot each section, and itemize every visible element in the web that the mac is missing. Every missing element becomes its own F-row first; only then verb-check.** The implicit promise of a registry row labelled "Rendered by `renderFoo()`" is "all of foo's outputs are visible here" — that promise can't be kept without an explicit per-element audit.

---

### I-9: Marked registry rows ✅ without verifying the actual behavior
- **Symptom**: Registry F-028 "Low Stock count badge button" and F-038 "Top Picks count badge button" were both marked ✅ (implemented). But the badges were just static `Text` views — clicking did nothing.
- **Root cause**: I implemented "the badge is rendered" and assumed that met the row. The row's literal description includes "button" and "toggle `toggleDashboardSection`". I marked ✅ without re-reading the row's verb.
- **User prompt that exposed it**:
  > "these tiles expand and collapse on clicking number on web app, why is that we did not find that feature?"
- **Fix**: Each tile header now has `onBadgeTap` closure. Badge renders as a `Button` that toggles per-tile `*TileCollapsed` state on `DashboardState`, persisted to UserDefaults. Tile body conditionally hides when collapsed.
- **Rule locked in**: **When marking a registry row ✅, re-read the row's verbs (button, toggle, expand, swipe, drag) and verify the implementation supports each verb interactively.** If the row says "button" and the impl is a Text, that's ❌ not ✅. A registry-status update is a claim — be ready to demo every claim.

---

### I-8: Validation entirely user-driven
- **Symptom**: After every change, the agent said "build verified" but the actual on-screen result was broken. User had to relaunch, screenshot, and report.
- **Root cause**: The agent's "verification" was `xcodebuild build` returning SUCCEEDED. That only proves the code compiles, not that it works at runtime.
- **Fix**: After every Release build + reinstall, the agent should:
  1. `pkill LocalOCR; sleep 1; open /Applications/LocalOCR.app; sleep 5`
  2. `log show --last 30s --predicate 'subsystem == "com.localocr.extended"'`
  3. Grep for "cancelled", "failed", "401", "decode" errors → fail fast if found
  4. For each newly-added endpoint, search for the expected "loaded N entries" success log
  5. Only THEN claim done
- **Rule locked in**: **`** BUILD SUCCEEDED **` is necessary, not sufficient. Always tail the runtime log.**

---

## 3. Anti-patterns — never do these

| Anti-pattern | Why it fails | Correct pattern |
|---|---|---|
| `async let _ = foo()` | Discarded child task gets cancelled when parent returns | `withTaskGroup` or explicit `await` |
| `.task { await heavyWork() }` | Cancelled on view identity change | `.onAppear { Task.detached { await heavyWork() } }` |
| Invent endpoint paths from a plan | Backend doesn't match the plan | `grep -E "@.*\.route" src/backend/*.py` first |
| Decode `[T]` as bare array | Backend wraps in `{"key": [...]}` | Add wrapper struct, decode wrapper |
| `xcodebuild build` = "done" | Compile success ≠ runtime success | Tail `log show` after launch + scan for errors |
| "Standard CRUD" / "all fields" in plan | Misses sub-fields, modals, edge states | Atomic registry: one row per pixel |
| User-driven screenshot validation | Slow, error-prone, breaks flow | Self-validate via logs + assertions |

---

## 4. Required pre-flight before writing client code for ANY new endpoint

```sh
# 1. Confirm the route exists + capture method
grep -nE "@.*\.route" src/backend/<blueprint_file>.py | grep -i "<feature>"

# 2. Confirm the url_prefix on the blueprint
grep -n "Blueprint(" src/backend/<blueprint_file>.py

# 3. Read the actual JSON shape returned (find the `return jsonify(...)`)
grep -n "return jsonify" src/backend/<blueprint_file>.py

# 4. Confirm what the web frontend sends/expects for the SAME endpoint
grep -n "fetch\|api(" src/frontend/index.html | grep -i "<feature>"
```

If any of those return zero matches, **stop and ask**. Don't guess.

---

## 5. Required post-build self-validation (run before every "done" claim)

```sh
# 1. Release build
cd LocalOCR.macOS && xcodebuild -scheme LocalOCR -configuration Release \
  -derivedDataPath ./DerivedData -destination 'platform=macOS,arch=arm64' build \
  2>&1 | grep -E "error:|\*\* BUILD"

# 2. Reinstall + launch
pkill -x LocalOCR; sleep 1
rm -rf /Applications/LocalOCR.app
cp -R ./DerivedData/Build/Products/Release/LocalOCR.app /Applications/
xattr -dr com.apple.quarantine /Applications/LocalOCR.app
open -a /Applications/LocalOCR.app

# 3. Wait + grab logs
sleep 6
/usr/bin/log show --last 30s \
  --predicate 'subsystem == "com.localocr.extended"' \
  --info --debug 2>&1 | tail -50
```

**Failure conditions** that mean NOT done:
- Any line containing `cancelled` (more than one initial-race entry is a bug)
- Any line containing `failed:`
- Any line containing `401` or `403` or `decode`
- For a screen you just added: no `loaded N <thing>` line within 5 seconds of launch

If any failure condition is hit → debug, fix, repeat. Do not report done.

---

## 6. Registry-driven screen workflow (always)

For each screen on the build queue:

```
1. Pull the rows
   awk '/Screen: <name>/,/^---/' FEATURE_PARITY_REGISTRY.md

2. Enumerate the IDs (F-NNN). Count them.

3. Implement every ❌ row in the SwiftUI view.
   Annotate sections with // MARK: - F-NNN ... F-MMM <feature group>

4. Build, run, log-validate per §5.

5. Update statuses in registry via python script:
   ❌ → ✅ (parity) | 🔄 (adapted, with note in macOS Impl column)
              | 🚫 (out of scope, must justify)

6. Update AUDIT STATUS table at bottom of registry.

7. Report exactly:
   ✅ <ScreenName> complete — N implemented, M adapted, K skipped, 0 ❌

8. Commit, push, reinstall.
```

If at any step ❌ rows remain unconsidered → not done.

---

## 7. Swift-specific concurrency rules (locked in by I-6, I-7)

### Parallel fan-out
```swift
// ✅ Correct
await withTaskGroup(of: Void.self) { group in
    group.addTask { @MainActor in await self.loadA() }
    group.addTask { @MainActor in await self.loadB() }
    group.addTask { @MainActor in await self.loadC() }
}

// ❌ Broken — children get cancelled on scope exit
async let _ = loadA()
async let _ = loadB()
```

### View-bound work
```swift
// ❌ Wrong for heavy data fetches — cancels on view re-render
.task { await refreshAll() }

// ✅ Right for short, idempotent setup
.task { await initSession() }

// ✅ Right for heavy fetches — survives re-renders
.onAppear {
    Task.detached(priority: .userInitiated) { await refreshAll() }
}
```

### Catching cancellation politely
```swift
do {
    try await api.request(...)
} catch is CancellationError {
    return                                // user-driven, ignore
} catch {
    let ns = error as NSError
    if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled {
        return                            // session cancel, ignore
    }
    // real error
    logger.error("\(error.localizedDescription, privacy: .public)")
}
```

---

## 8. How to make this agentic — zero-human-validation targets

The user has been doing the role of "verify each build looks right on screen". Goal: agent does this itself.

| Today's manual step | Tomorrow's automated step |
|---|---|
| User screenshots + reports issue | Agent runs `screencapture -x /tmp/check.png` + analyses via Read tool (image) |
| User opens Console.app to find errors | Agent runs `log show` with predicate after every build |
| User says "no data, look at log" | Agent self-checks `log show` and surfaces issues without prompting |
| User says "did you check the actual backend route" | Agent runs the §4 pre-flight grep every time |
| User says "you missed F-022, the show-more button" | Agent runs the §6 registry workflow before any view edit |
| User says "build succeeded but it's broken" | Agent runs §5 post-build validation before claiming done |

The skill to extract from this file:
- **Name**: `localocr-build-validate`
- **Triggers**: any commit on `feat/macos-*` branch, any `xcodebuild build` invocation
- **Steps**: §4 pre-flight + §5 post-build + §6 registry + §7 concurrency rules
- **Failure behavior**: do not claim done; report the specific failure condition + the log line that proves it

---

## 9. Update protocol

Every time the user has to:
- Say "did you check…"
- Say "still broken…"
- Take a screenshot to expose something the agent should have known
- Repeat themselves

…add a new entry to §2 as `I-N: <symptom>` with root cause, fix, and the rule it locks in. The corrective prompt is part of the institutional memory.

Append-only. Never delete entries — past mistakes are the reason the rule exists.

---

## 10. Current open scars (things not yet ruled out)

These are gaps not yet promoted to rules because they need one more incident to confirm the pattern:

- **PROD count still 0 sometimes** — `/products` returns `{total}` but in some sessions returns nothing. Suspect a session/scope issue. Watch for the next time it fails and capture the request/response then.
- **Receipts Processed sparkline often empty** — `/analytics/spending?period=daily&months=1` returns empty `spending_by_period` even when receipts exist. Need to confirm whether this is a backend bug (no receipts in the current daily buckets) or a client query issue.
- **(Promoted to I-10)** ~~`requestAuthorization failed: UNErrorDomain error 1`~~ — locked in as RULE 10 (system-environment capability errors must latch in UserDefaults, not retry every launch).


### I-15: Visual audit run aborted by synthetic-click events routed to loginwindow when screen was locked
- **Symptom**: Mid-way through AUDIT_B2 the system auto-locked. Quartz `CGEventCreateMouseEvent` clicks at known sub-tab pixel coordinates and `osascript "tell System Events to click at {x,y}"` both began returning `window Login of application process loginwindow` instead of reaching LocalOCR. App was still frontmost per `frontmost is true`, screen-captures by window-id still worked, and **menu-bar AX actions** (`tell menu bar item "View"`) **still fired** — so the audit could keep navigating menu-driven tabs but had to fall back to code-only verification for Accounts / Analytics / Budget / Contribution (no menu items, sidebar-click required).
- **Root cause**: When `CGSessionCopyCurrentDictionary()` reports `CGSSessionScreenIsLocked == True`, the HID event tap on `kCGHIDEventTap` is captured by the system loginwindow process, regardless of what app `set frontmost to true` reports. Menu-bar items dispatch through Accessibility (`AXPressAction`), not synthetic mouse events, so they continue to work — which makes the failure mode silent: the audit appears to be navigating until it hits a tab that requires a real click.
- **User prompt that exposed it**: (caught by self-diagnosis — `python3 -c "from Quartz import CGSessionCopyCurrentDictionary; print(CGSessionCopyCurrentDictionary().get('CGSSessionScreenIsLocked'))"` returned `True` after multiple clicks failed to navigate)
- **Fix**: Audit scripts must run `CGSessionCopyCurrentDictionary` as the first action and abort with a clear message if the screen is locked. Long-running audits should also re-check every N captures. Better: ensure the test machine has its lock-screen timeout extended for the audit duration (or runs unlocked from the start).
- **Rule locked in**: **Before any visual-audit run that uses synthetic mouse events, check `CGSSessionScreenIsLocked` and abort early if `True`. Menu-bar AX actions still fire — so a half-coverage audit is the worst outcome, because partial captures look complete. Either run fully unlocked or fail fast.**

---

### I-16: Web reference window lost its authenticated session on `tell active tab reload`
- **Symptom**: AUDIT_B2 attempted to refresh the Chrome window holding the authoritative web reference (logged-in Admin profile, dark theme, extended.npalakurla.com) and every subsequent screenshot returned the logged-out shell (light theme, blank page). `localStorage.theme=dark` was set programmatically but not honored on subsequent loads. Round-1 captures (`/tmp/web_*.png`) had to be reused as the authoritative reference for the second round.
- **Root cause**: The web app's session cookie was not `HttpOnly` + `Secure` + same-site on the test domain at the time of the audit, or the auth cookie scope did not survive a hard reload triggered from outside the page. Bigger issue: AUDIT_B2 method explicitly says "re-screenshot both apps" — the agent did the reload by reflex without first proving the session would survive. The single `tell active tab to reload` cost the entire web-side comparison capability for the run.
- **User prompt that exposed it**: (caught by self-diagnosis — Chrome screenshot reverted to the pre-login marketing surface, confirmed via `execute javascript "document.body.className"` returning empty class set)
- **Fix**: Round 2 reused Round 1 web captures as the authoritative reference, since AUDIT_B descriptions were written against those exact images and the fixes target those documented states. Going forward, audit scripts must (a) snapshot the web window's current state by image+URL+localStorage *before* any navigation, (b) navigate via SPA `nav()` / `location.hash = "#<page>"` only, never via `reload`, (c) abort if a JS probe shows the session is gone.
- **Rule locked in**: **Never `reload` an authoritative web-reference window during an audit. SPA route changes must use the in-page `nav()` / hash assignment. If a forced reload is unavoidable, re-authenticate before continuing the run. Treat the authenticated web window as fragile single-shot state.**

---

## Fix Phase Learnings — 2026-05-20
Fixes executed: 58
New incidents logged: [I-15, I-16]
New rules added: [RULE 16, RULE 17]
Completed: 16:50:41 (FIX run); AUDIT_B2 verification appended at 17:10

---

### I-17: `keyDecodingStrategy = .convertFromSnakeCase` + explicit snake_case CodingKey rawValues → silent decode failure
- **Symptom**: FIX-V2-016 wired `/analytics/receipts-activity` and on first launch every fetch failed with `Decode failure for /analytics/receipts-activity: The data couldn't be read because it is missing.` Stats stayed empty even though backend returned a valid `{grain, count, buckets, total, total_amount}` payload. No 4xx / 5xx in the log — only the decoder error.
- **Root cause**: `APIClient.request` sets `decoder.keyDecodingStrategy = .convertFromSnakeCase`. The strategy converts incoming JSON keys to camelCase BEFORE looking them up against your CodingKey rawValues. My `ReceiptsActivityResponse` declared `enum CodingKeys: String, CodingKey { ...; case totalAmount = "total_amount" }`. The decoder converted `"total_amount"` → `"totalAmount"`, then searched CodingKeys for rawValue `"totalAmount"` — and found only `"total_amount"`. Lookup failed → property missing → whole decode fails.
- **User prompt that exposed it**: (caught by self-diagnosis via Rule 6 `log show` — decoder failure surfaced before the user saw the empty chart)
- **Fix**: Drop the explicit CodingKey for `totalAmount` and let the snake_case strategy do the work — the property name `totalAmount` already matches the converted JSON key. Verified by re-running: `loaded 30 receipts-activity buckets (grain=day, total=262)`. Also remediated `SpendingDrillItem` in the same file which had the exact same pattern (six snake_case CodingKey rawValues) and would have failed the moment a user clicked spending drill-down with non-empty data.
- **Rule locked in**: **When the decoder uses `.convertFromSnakeCase`, NEVER declare `case fooBar = "foo_bar"` CodingKey rawValues — the strategy converts JSON keys to camelCase before lookup, so snake_case rawValues never match.** Either rely on the strategy + property name matching (preferred), or — if you must declare CodingKeys for a subset of properties — use camelCase rawValues. Encodable-only request body structs are unaffected (encode path doesn't run the snake_case strategy). Audit existing Decodable structs in `Endpoints.swift` for this anti-pattern; this batch fixed `ReceiptsActivityResponse` (new) and `SpendingDrillItem` (pre-existing) — broader audit pending. Generalize: when a JSONDecoder strategy mutates keys, explicit CodingKey rawValues must be in the POST-strategy form.

---

## Fix Phase Learnings — 2026-05-20 (Batch 4)
Fixes executed: 4 (FIX-V2-016..019)
New incidents logged: [I-17]
New rules added: [RULE 18]
Completed: BATCH_4

## Fix Phase Learnings — Round 2 — 2026-05-20
Fixes executed: 19
New incidents logged: ['I-17']
New rules added: ['RULE 18']
Errors: []
Completed: 19:32:31

---

### I-18: Self-flagged "broader audit pending" in I-17 was dropped at round close — ProductRenameResponse survived as a live RULE 18 trap
- **Symptom**: AUDIT_A3 grep `'case [a-z]+[A-Z]\w* *= *"[a-z]+_'` against `Endpoints.swift` returned a live Decodable trap on `ProductRenameResponse` (lines 2009-2010: `case displayName = "display_name"` + `case mergedInto = "merged_into"`). APIClient runs `keyDecodingStrategy = .convertFromSnakeCase` (`APIClient.swift:56,157`) → the strategy converts the JSON keys to camelCase BEFORE matching against rawValues → snake_case rawValues never match → both properties silently decoded as `nil`. Callers at `InventoryState.swift:494`, `ReceiptsState.swift:610,638` consume the response for the rename-merge toast, so the toast was reporting `displayName=nil` / `mergedInto=nil` for every rename — silent UX break, no error in `log show`.
- **Root cause**: When the agent locked in RULE 18 in this same round, the I-17 incident entry literally said "Audit existing Decodable structs in `Endpoints.swift` for this anti-pattern; this batch fixed `ReceiptsActivityResponse` (new) and `SpendingDrillItem` (pre-existing) — broader audit pending." The "broader audit pending" line was written by the agent itself as a self-flag, then the round closed without anyone running the broader audit. The fix-agent in Round 2 touched `Endpoints.swift` (FIX-V2-016 added `ReceiptsActivityResponse` etc.) but RULE 16's "touched-file full re-grep before commit" pass did not pick up the trap because the agent had already added RULE 18 in the same batch and only remediated the two structs named in the I-17 entry.
- **User prompt that exposed it**: (caught by AUDIT_A3 regression scan before user saw the broken toast — RULE 16 + RULE 18 + audit working as intended, but only because the auditor was the next agent in the loop)
- **Fix**: Drop the explicit CodingKeys on `ProductRenameResponse` (CA3-R-001 remediation). Strategy + property names now do the work. Verified: `grep -nE 'case [a-z]+[A-Z]\w* *= *"[a-z]+_' LocalOCR.macOS/LocalOCR/Networking/Endpoints.swift` returns only Encodable-body matches; the lone Decodable trap is gone.
- **Rule locked in**: **Any "broader audit pending" / "TODO follow-up" / "next-batch cleanup" note an agent writes into AGENT_LEARNINGS.md, agent-rules.md, or a commit message must be closed in the SAME commit/round that creates the note — OR converted into a tracked todo with an owner. Self-flagged future work that lacks an owner is treated as a regression by the next audit.** Generalize: when you find a problem broader than your fix spec and write down "we'll do the rest later", you don't have a follow-up — you have a half-finished fix. Finish it in the same commit, or open a tracked task with an explicit owner before round-close.

---

## Fix Phase Learnings — 2026-05-20
Fixes executed: 7
New incidents logged: []
New rules added: []
Completed: 22:45:30

### I-LANDING-1: Google Fonts css2 `head -1` grabs a non-latin subset
- **Build**: landing rebrand (2026-06-10), self-hosting woff2
- **Symptom**: downloaded woff2 files were 4–6KB (cyrillic/vietnamese subset = missing latin glyphs → fallback font would render silently)
- **Catch**: size sanity check before commit (latin subsets are 9–15KB)
- **Fix**: parse the css2 response for the `/* latin */` block and take ITS url, not the first url in the file
- **Rule**: when self-hosting from fonts.googleapis.com/css2, always extract per-subset; verify with `file *.woff2` AND a size floor; smoke-render the page and confirm the font actually paints (screenshot, not assumption).
