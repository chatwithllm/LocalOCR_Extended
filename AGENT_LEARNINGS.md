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
- **`requestAuthorization failed: UNErrorDomain error 1`** — notification permission denied silently on every launch. Should distinguish "denied" from "not determined" and only retry once.
