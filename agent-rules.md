# Agent Rules — Locked In From Production Incidents
# Source: AGENT_LEARNINGS.md (LocalOCR macOS build)
# Status: BINDING — every rule here was locked in by a real incident.
# An agent that violates these rules will reproduce the exact bug that created the rule.
#
# READ THIS FILE AT THE START OF EVERY SESSION.
# Treat every rule as a hard constraint, not a suggestion.

---

## RULE 0 — What "Done" Means

`xcodebuild build` returning SUCCEEDED is **compile proof only**.
It is **not** done. Done means all of the following are true:

- [ ] Pre-flight bash checks passed (Rule 1) before client code was written
- [ ] Every ❌ registry row for this screen is closed (Rule 5)
- [ ] Release build succeeded with zero errors
- [ ] App reinstalled, launched, logs tailed (Rule 6)
- [ ] Zero failure log lines found (Rule 6, failure conditions)
- [ ] "loaded N <thing>" line found for every new endpoint within 5s of launch

If any of those is not true → NOT done. Debug, fix, repeat. Do not report done.

---

## RULE 1 — Pre-Flight Before Writing ANY Endpoint Client Code

Run ALL FOUR of these before writing a single Codable struct, Endpoint enum case, or
service function. If any returns zero matches → STOP and ask. Do not guess.

```bash
# 1. Confirm the route exists + HTTP method
grep -nE "@.*\.route" src/backend/<blueprint_file>.py | grep -i "<feature>"

# 2. Confirm the url_prefix on the blueprint
grep -n "Blueprint(" src/backend/<blueprint_file>.py

# 3. Read the EXACT JSON shape returned
grep -n "return jsonify" src/backend/<blueprint_file>.py
# Then read the full function to see what keys are in the dict

# 4. Confirm what the web frontend sends/expects for this SAME endpoint
grep -n "fetch\|api(" src/frontend/index.html | grep -i "<feature>"
```

**Why each check exists:**
- Check 1: I-3 — agent invented plausible paths that didn't match reality
- Check 2: I-3 — url_prefix + route path = full URL. Missing prefix = 404
- Check 3: I-2, I-5 — backend wraps lists in envelopes; client decoded bare arrays → empty screens
- Check 4: I-4 — `/spending` and `/spending-by-category` are different endpoints with different shapes

---

## RULE 2 — Mirror Backend JSON Verbatim

Before writing any Codable struct or response model:
1. Run Check 3 from Rule 1 to find `return jsonify({...})`
2. Read the full dict — note every key name exactly as spelled
3. If the backend returns `{"inventory": [...], "count": N}` → write a wrapper struct
4. If the backend returns flat fields (`product_name`, `category`) → do NOT nest them

```swift
// ❌ Wrong — assumed nested (I-5)
struct InventoryItem: Codable {
    let product: Product     // backend emits flat product_name, not nested
}

// ✅ Correct — mirrors backend exactly
struct InventoryItem: Codable {
    let productName: String
    let category: String
    enum CodingKeys: String, CodingKey {
        case productName = "product_name"
        case category
    }
}

// ❌ Wrong — assumed bare array (I-2)
let items = try decoder.decode([InventoryItem].self, from: data)

// ✅ Correct — matches actual envelope
struct InventoryListResponse: Codable {
    let inventory: [InventoryItem]
    let count: Int
}
let response = try decoder.decode(InventoryListResponse.self, from: data)
let items = response.inventory
```

**Rule:** Reality > opinion. Mirror the backend schema verbatim, even if it would be "cleaner" to nest.

---

## RULE 3 — Swift Concurrency: Banned Patterns

### BANNED: `async let _ = foo()`

```swift
// ❌ NEVER — discarded child task is cancelled when parent scope exits (I-6)
async let _ = loadInventory()
async let _ = loadReceipts()
```

**Why:** `async let _ =` creates a child task but `_ =` discards the binding. The child is
never awaited, so when the parent function returns, Swift cancels all unawaited children.
`URLSession.data(for:)` throws `CancellationError` ~2 ms after start. All endpoints
show "cancelled" in logs. All screens show empty data. The build looks correct.

### CORRECT: `withTaskGroup` for parallel fan-out

```swift
// ✅ Always use this for parallel data fetches
await withTaskGroup(of: Void.self) { group in
    group.addTask { @MainActor in await self.loadInventory() }
    group.addTask { @MainActor in await self.loadReceipts() }
    group.addTask { @MainActor in await self.loadShopping() }
}
```

### BANNED: `.task { await heavyWork() }` for data fetches

```swift
// ❌ NEVER for heavy fetches — cancelled on view identity change (I-7)
.task { await self.refreshAll() }
```

**Why:** SwiftUI's `.task` modifier cancels its closure when the view's body re-evaluates
with a different identity. Heavy `@Published` traffic → frequent re-evaluations →
frequent cancellations → same "cancelled" symptom as I-6.

### CORRECT: `.onAppear` + `Task.detached` for heavy fetches

```swift
// ✅ Survives re-renders — use for any data fetch fan-out
.onAppear {
    Task.detached(priority: .userInitiated) {
        await self.refreshAll()
    }
}

// ✅ .task is fine for short, idempotent, view-bound work only (≤500 ms)
.task { await initSession() }
```

### CORRECT: Catch cancellation politely

```swift
do {
    try await api.request(...)
} catch is CancellationError {
    return  // user-driven cancel, ignore silently
} catch {
    let ns = error as NSError
    if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled {
        return  // URLSession cancel, ignore silently
    }
    logger.error("\(error.localizedDescription, privacy: .public)")
}
```

---

## RULE 4 — Match the Web's Exact Endpoint

When porting any web visual to macOS, grep `index.html` for the exact fetch URL
the web uses for that feature before writing any Swift:

```bash
grep -n "fetch\|api(" src/frontend/index.html | grep -i "<feature name>"
```

Two endpoints with similar names are NOT interchangeable:
- `/analytics/spending` ≠ `/analytics/spending-by-category` (I-4)
- Different response shapes, different query params, different data

**Rule:** If the web uses `/analytics/spending-by-category?month=YYYY-MM&limit=50`,
the Swift endpoint must use the EXACT same path and query params.

---

## RULE 5 — Registry Workflow (Every Screen, No Exceptions)

```
Step 1 — Pull the rows before touching the view file
  awk '/Screen: <name>/,/^---/' FEATURE_PARITY_REGISTRY.md

Step 2 — Count the ❌ rows. This is your task list.

Step 3 — Implement every ❌ row.
  Annotate sections: // MARK: - F-NNN ... F-MMM <feature group>

Step 4 — BEFORE marking any row ✅ — verb check (Rule 9):
  Re-read the row's UI Element and feature description.
  Extract every action verb: button, toggle, expand, collapse, swipe,
  tap, navigate, edit, drag, sort, filter, delete, submit.
  Verify the Swift implementation supports each verb interactively.

  | Row says       | Impl MUST be                      | NOT acceptable       |
  | button         | Button { } label: { }             | Text, HStack, Image  |
  | toggle/expand  | @State var + Button that mutates  | static display       |
  | swipe action   | .swipeActions { Button }          | none                 |
  | tap/navigate   | NavigationLink or Button { nav() }| Text                 |
  | persisted      | UserDefaults write + read on init | @State only          |

  If the row says "button" and impl is Text → mark ❌, fix, re-verify.

Step 5 — Run post-build validation (Rule 6).

Step 6 — Update registry statuses:
  ❌ → ✅  (implemented AND all verbs verified interactively)
  ❌ → 🔄  (adapted for desktop — add note in macOS Impl column)
  ❌ → 🚫  (explicitly out of scope — must justify in column)

Step 7 — Report:
  ✅ <ScreenName> — N implemented, M adapted, K out-of-scope, 0 ❌ remaining
```

**No screen is done while it has ❌ rows.**
**No row gets ✅ without passing the verb check (Step 4).**

---

## RULE 6 — Post-Build Self-Validation (Run Before Every "Done" Claim)

```bash
# Step 1: Release build
cd LocalOCR.macOS && xcodebuild -scheme LocalOCR -configuration Release \
  -derivedDataPath ./DerivedData \
  -destination 'platform=macOS,arch=arm64' build \
  2>&1 | grep -E "error:|\*\* BUILD"

# Step 2: Reinstall + launch
pkill -x LocalOCR; sleep 1
rm -rf /Applications/LocalOCR.app
cp -R ./DerivedData/Build/Products/Release/LocalOCR.app /Applications/
xattr -dr com.apple.quarantine /Applications/LocalOCR.app
open -a /Applications/LocalOCR.app

# Step 3: Wait + grab logs
sleep 6
/usr/bin/log show --last 30s \
  --predicate 'subsystem == "com.localocr.extended"' \
  --info --debug 2>&1 | tail -80
```

### Failure conditions — any of these = NOT done

| Log pattern | Meaning | Rule to apply |
|-------------|---------|--------------|
| `cancelled` (> 1 instance) | Task cancellation cascade | Rule 3 — fix concurrency pattern |
| `failed:` | Runtime error | Read the full error, find root cause |
| `401` or `403` | Auth not attached or token revoked | Check APIClient header injection |
| `decode` or `DecodingError` | Response shape mismatch | Rule 2 — re-read jsonify, fix Codable |
| `404` | Wrong URL path | Rule 1 Check 1 — grep blueprint |
| No `loaded N <thing>` for new screen | Endpoint never returned data | Run Rule 1 pre-flight, check wrapper |

If any failure condition → debug, fix, re-run from Step 1. Never skip to "done".

---

## RULE 7 — Anti-Patterns (Never Do These)

| Anti-pattern | Why it fails | Correct pattern |
|---|---|---|
| `async let _ = foo()` | Child task cancelled on scope exit | `withTaskGroup` |
| `.task { await heavyWork() }` | Cancelled on view re-render | `.onAppear { Task.detached { ... } }` |
| Invent endpoint paths from plan | Backend doesn't match the plan | Rule 1 — grep blueprint first |
| Decode `[T]` as bare array | Backend wraps in `{"key": [...]}` | Wrapper struct, decode wrapper |
| `xcodebuild build` = "done" | Compile ≠ runtime | Rule 6 — tail log show |
| "Standard CRUD / all fields" | Misses sub-fields, modals, states | Atomic registry — one row per element |
| Skip pre-flight to save time | Guarantees wrong path/shape | Rule 1 — no exceptions |
| Read plan for endpoint path | Plan can be wrong | Read blueprint + grep index.html |
| Log system-rejection as `.warning` and retry next launch | Pollutes logs, breaks Rule 6 validation | Rule 10 — latch in UserDefaults, log at `.info` |

---

## RULE 8 — Open Scars (Watch These, Add Rule When Pattern Confirms)

These have happened once but not yet ruled. Next incident locks in the rule.

- **PROD count 0 on `/products`** — returns `{total}` but some sessions return nothing.
  Watch: is it a session scope issue or a query parameter issue?

- **Receipts Processed sparkline empty** — `/analytics/spending?period=daily&months=1`
  returns empty `spending_by_period`. Confirm: backend bug vs wrong query params.

- ~~**`UNErrorDomain error 1` on every launch**~~ — **PROMOTED TO RULE 10 (I-10)**.

When any of these hits a second time → promote to a numbered Rule here.

---

## RULE 9 — Registry ✅ Requires Verb Verification, Not Visual Rendering

**Source: I-9** — F-028 and F-038 marked ✅ because the badge rendered. Both rows said
"button / toggle `toggleDashboardSection`". Both implementations were static `Text` views.
Clicking did nothing. User had to report it.

**The mistake:** "the badge is rendered" ≠ "the row is implemented".
A registry row describes BEHAVIOR, not appearance.

### Before marking ANY row ✅ — run this check:

1. Re-read the full row text — extract every action verb:
   `button` `toggle` `expand` `collapse` `swipe` `drag` `tap` `navigate`
   `open` `dismiss` `select` `sort` `filter` `edit` `delete` `submit`

2. For each verb found — verify the Swift implementation matches:

| Row says | Implementation MUST be | NOT acceptable |
|----------|------------------------|----------------|
| button | `Button { } label: { }` | `Text`, `HStack`, `Image` |
| toggle / expand / collapse | state var + `Button` that mutates it | static display |
| swipe action | `.swipeActions { Button }` | none |
| tap / navigate | `NavigationLink` or `Button { navigate() }` | `Text` |
| drag | `.draggable` or `onDrag` | static view |
| edit inline | `TextField` or edit mode | `Text` |

3. If the row says "button" and the impl is a `Text` → mark ❌, fix, then re-verify.

4. Persistence: if the row says "persisted" or "remembers" → verify UserDefaults/Keychain
   write + read. A state var that resets on relaunch is not ✅.

### The rule in one sentence:
**A registry-status update is a claim. Be ready to demo every verb in the row
interactively. If you cannot demo it, it is ❌.**

### Updated anti-pattern for section 3:
| Mark ✅ because "it renders" | Rendering ≠ behavior — re-read verbs, verify interactivity |

---

## RULE 10 — System Capability Errors Must Latch, Not Repeat

**Source: I-10** — `UNUserNotificationCenter.requestAuthorization` threw `UNErrorDomain code 1` on every launch (unsigned builds can't request notification permission). The code logged `.warning` every time. Errors accumulated in Console.app and broke Rule 6 validation (Rule 6 says "ZERO `failed:` log lines" — but a baseline rejection that re-fires every launch makes that check meaningless).

### The mistake pattern

```swift
// ❌ Wrong — keeps calling, keeps logging .warning forever
do {
    _ = try await center.requestAuthorization(options: [.alert])
} catch {
    logger.warning("requestAuthorization failed: \(error.localizedDescription)")
}
```

The error is the **environment** saying "this capability isn't available in this build."
It is not a caller bug. Retrying gains nothing; logging it as `.warning` poisons the log.

### The correct pattern

```swift
// ✅ Latch the rejection in UserDefaults, log at .info, skip future attempts
let rejectionKey = "App.notificationRequestRejected"
if UserDefaults.standard.bool(forKey: rejectionKey) { return }

do {
    _ = try await center.requestAuthorization(options: [.alert])
    UserDefaults.standard.removeObject(forKey: rejectionKey)   // clear on success
} catch let error as NSError {
    if error.domain == "UNErrorDomain", error.code == 1 {
        UserDefaults.standard.set(true, forKey: rejectionKey)
        logger.info("notifications unavailable in this build — silenced for future launches")
        return
    }
    logger.warning("\(error.localizedDescription)")
}
```

### Categorize errors before logging

| Error kind | Behavior | Log level |
|-----------|----------|-----------|
| **Transient** (network blip, timeout) | Retry next time | `.warning` |
| **Caller bug** (wrong payload, missing field) | Fix the call site | `.error` |
| **Environmental capability** (unsigned, no entitlement, hardware missing) | Latch in UserDefaults; skip future launches | `.info` |
| **Cancellation** (user-driven, view re-render) | Silent return | `.debug` or none (Rule 3) |

### Rule of thumb

If the SAME error fires on EVERY launch and retrying changes nothing, it's an **environmental capability error**. Latch it. Don't retry. Don't pollute the log.

### Compliance check before merge

```bash
# After 5+ launches, the same error pattern should appear AT MOST once.
/usr/bin/log show --last 10m --predicate 'subsystem == "<bundle>"' --info --debug | \
  grep -cE "failed:|UNErrorDomain"
# If count > 1 for the same error pattern → Rule 10 violated.
```

---

## LEARNING LOOP — Every Incident Updates Both Files Immediately

When you append a new incident to AGENT_LEARNINGS.md, you MUST in the same commit:

### Step 1 — Add the incident to AGENT_LEARNINGS.md (§2)
Follow the exact format of I-1 through I-9:
```
### I-N: <short symptom title>
- **Symptom**: [what the user saw]
- **Root cause**: [why it happened]
- **User prompt that exposed it**: > "[exact words]"
- **Fix**: [what was changed]
- **Rule locked in**: **[the rule, bold]**
```

### Step 2 — Add RULE N to agent-rules.md immediately after
```
## RULE N — <title matching I-N>

**Source: I-N** — <one-line summary of the mistake>

[Rule content — at minimum:]
- What went wrong (the mistake pattern)
- Why it fails
- The correct pattern with code example if applicable
- How to verify compliance before marking ✅
```

### Step 3 — Add the anti-pattern to the Rule 7 table
Add one row:
| <what the agent did wrong> | <why it fails> | <correct pattern> |

### Step 4 — Update Rule 0 Done criteria if the new rule adds a new gate
If the new rule requires a new verification step before "done", add it to the
Rule 0 checklist.

### Step 5 — Commit both files together
```bash
git add AGENT_LEARNINGS.md agent-rules.md
git commit -m "learning: I-N locked in — <symptom title>"
```

---

### How the two files relate

| File | Location | Who writes | When |
|------|----------|-----------|------|
| `AGENT_LEARNINGS.md` | project root | Agent | Every incident |
| `agent-rules.md` (project) | project root | Agent | Every incident (same commit) |
| `agent-rules.md` (skill) | `/mnt/skills/user/native-app-builder/references/` | Read-only — updated when user installs new skill version | Periodically |

The **project-level `agent-rules.md`** is the live version during a build.
The **skill-level `agent-rules.md`** is the baseline for a new project.

### Session start — which file to read

```bash
# Always prefer the project-level version if it exists (it has newer rules)
[ -f agent-rules.md ] && echo "Using project agent-rules.md" \
  || echo "Falling back to skill references"
```

In the session start prompt:
  Read agent-rules.md from the project root.
  If it does not exist, read /mnt/skills/user/native-app-builder/references/agent-rules.md.
  The project version always takes precedence — it has rules the skill may not have yet.

### When to sync back to the skill

After each build phase (or when the user asks), the user brings agent-rules.md and
AGENT_LEARNINGS.md to Claude.ai. Claude updates the skill and repackages. The new
skill version becomes the baseline for the next project — carrying all rules forward.

This means every new app you build starts with the full institutional memory of every
previous app. Mistakes that cost hours on project 1 never appear on project 2.


## SESSION START CHECKLIST

At the start of every build session, before writing a single line:

- [ ] Read FEATURE_PARITY_REGISTRY.md — know the screen queue
- [ ] Read MACOS_APP_PLAN.md §7.4 (or VETO_RESOLUTION_PATCH.md) — confirm no open gates
- [ ] Read this file (agent-rules.md) — all rules are active this session
- [ ] Confirm PROD_BASE_URL is set and reachable: `curl -s -o /dev/null -w "%{http_code}" $PROD_BASE_URL/auth/me`
- [ ] Confirm you know the test credentials for post-build log validation
