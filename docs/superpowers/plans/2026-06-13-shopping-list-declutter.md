# Shopping List Tab Declutter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 9-block stacked Shopping List tab with a `🛒 Shop | ✏ Plan` segmented view that keeps the store-grouped list + slim stats in both modes and moves entry tools + recommendations into Plan, with a smart default (Plan when the list is empty, else Shop).

**Architecture:** Pure frontend change in the single-file vanilla-JS SPA `src/frontend/index.html`. We restructure the `#page-shopping` markup into a header (with a segmented control) plus two mode containers and a shared list/past-trips region, add a `shoppingMode` state variable with a `setShoppingMode()` switcher, and compute the smart default at the end of the existing `loadShoppingList()`. No backend, API, schema, or list-rendering-logic changes — `renderShoppingListTable()`, `setShoppingListView()`, `loadRecs()`, `renderShoppingSessionBanner()`, and `loadShoppingPastTrips()` are reused as-is and only re-parented in the DOM.

**Tech Stack:** HTML + CSS + vanilla JavaScript inside `src/frontend/index.html`. No test framework exists for this SPA (the repo's `tests/` are Python/backend only), so each task is verified by loading the app in a browser against an explicit checklist rather than automated JS tests. **Do not add a JS test framework** — that is an out-of-scope dependency.

---

## How to run the app for verification

The backend serves the SPA. From the repo root:

```bash
docker compose up -d backend     # serves on http://localhost:8090
# OR, if running locally without Docker, the project's normal Flask launch on :8090
```

Open `http://localhost:8090`, log in, and click the **Shopping** tab. If the list
is empty, add one or two items first (via Plan mode's add bar) so both
modes can be exercised. After each task, hard-refresh (Cmd/Ctrl-Shift-R) to pick
up the edited `index.html`.

## File structure

- **Modify only:** `src/frontend/index.html`
  - CSS block (top `<style>`): add segmented-control, slim-stats-chip, and mode-container styles.
  - Markup: `#page-shopping` region, currently lines ~3197–3509.
  - JS: shopping state vars near line ~8056 (`shoppingListView`), `loadShoppingList()` at ~29679, and a new `setShoppingMode()` near the other shopping helpers (~10170).

No new files. No other tab is touched.

---

### Task 1: Add CSS for the segmented control, slim stats, and mode containers

**Files:**
- Modify: `src/frontend/index.html` (top `<style>` block — append near the other `.shopping-*` rules)

- [ ] **Step 1: Find an anchor in the stylesheet**

Run: `grep -n "shopping-summary-strip\|shopping-summary-pill" src/frontend/index.html | head`
Note the line of the existing `.shopping-summary-strip` rule — insert the new CSS immediately after that rule block so the shopping styles stay together.

- [ ] **Step 2: Add the new CSS**

Insert this block right after the existing `.shopping-summary-*` rules:

```css
/* --- Shopping tab: Plan/Shop segmented modes --- */
.shopping-mode-switch {
  display: flex;
  border: 1px solid var(--border, #30363d);
  border-radius: 8px;
  overflow: hidden;
  margin: 10px 0 12px;
}
.shopping-mode-switch button {
  flex: 1;
  background: transparent;
  border: 0;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
  color: var(--text-muted, #8b949e);
  cursor: pointer;
}
.shopping-mode-switch button.is-active {
  background: var(--accent, #1f6feb);
  color: #fff;
  font-weight: 600;
}
/* slim stats chips (replace big pills) */
.shopping-stats-slim {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.shopping-stats-slim .chip {
  border: 1px solid var(--border, #30363d);
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--text-muted, #8b949e);
  background: transparent;
  cursor: default;
}
.shopping-stats-slim button.chip { cursor: pointer; }
.shopping-stats-slim button.chip.is-active {
  border-color: var(--accent, #1f6feb);
  color: var(--accent-fg, #79c0ff);
}
/* mode containers */
.shopping-mode-pane[hidden] { display: none !important; }
/* unified add bar (Plan mode) */
.shopping-add-bar {
  display: flex;
  gap: 6px;
  align-items: center;
  border: 1px solid var(--border, #30363d);
  border-radius: 8px;
  padding: 6px;
  margin-bottom: 12px;
}
.shopping-add-bar input.shopping-add-search { flex: 1; min-width: 0; }
```

- [ ] **Step 3: Verify it loads with no console errors**

Hard-refresh `http://localhost:8090`, open DevTools console. Expected: no CSS parse warnings; page renders unchanged so far (markup not yet using these classes).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "style(shopping): add CSS for Plan/Shop segmented modes"
```

---

### Task 2: Add the segmented control + mode panes to the markup

**Files:**
- Modify: `src/frontend/index.html` — `#page-shopping` region (~3197–3509)

**Approach:** Wrap the existing inner blocks into two `.shopping-mode-pane` containers without deleting any element (so existing JS that targets their IDs keeps working). The Current List and Past Trips cards move OUT of both panes into a shared region so they show in both modes.

- [ ] **Step 1: Replace the header action buttons with the segmented control**

Find (`~3204–3224`) the `<div class="shopping-page-actions">…</div>` containing `#shopping-quick-header-toggle` and `#shopping-recommendations-toggle`. Replace that entire `shopping-page-actions` div with nothing (remove it), and immediately after the `</div>` that closes `.page-header`, insert:

```html
<div class="shopping-mode-switch" id="shopping-mode-switch" role="tablist">
  <button type="button" id="shopping-mode-shop" class="is-active"
          onclick="setShoppingMode('shop', true)" role="tab">🛒 Shop</button>
  <button type="button" id="shopping-mode-plan"
          onclick="setShoppingMode('plan', true)" role="tab">✏ Plan</button>
</div>
```

- [ ] **Step 2: Wrap the entry/discovery blocks into the Plan pane**

Wrap these existing siblings — `#shopping-helper-intro`, `#shop-manual-card`,
`#shopping-quick-find-card`, `#shopping-recommendations-card` — in a single
container. Insert `<div class="shopping-mode-pane" id="shopping-pane-plan" hidden>`
immediately before `#shopping-helper-intro` and the closing `</div>`
immediately after `#shopping-recommendations-card`'s closing tag.

- [ ] **Step 3: Add the unified add bar at the top of the Plan pane**

Immediately inside `#shopping-pane-plan` (before `#shopping-helper-intro`), add:

```html
<div class="shopping-add-bar">
  <input id="shop-quick-search" class="shopping-add-search"
         placeholder="🔍 Add item…"
         onfocus="handleShoppingQuickFindFocus()"
         onblur="handleShoppingQuickFindBlur()"
         oninput="searchShoppingQuickFind()"
         onkeydown="handleShoppingQuickFindKey(event)" />
  <select id="shop-preferred-store" class="shopping-quick-store"></select>
  <button type="button" class="btn btn-ghost btn-sm"
          onclick="toggleManualShoppingForm()">＋</button>
  <button type="button" class="btn btn-ghost btn-sm"
          onclick="triggerShopIdentifyPhoto()">📷</button>
</div>
```

Then DELETE the now-duplicated controls inside the old `#shopping-quick-find-card`
header (the `#shop-quick-search`, `#shop-preferred-store`, manual toggle, and
collapse button at ~3348–3378) so only one of each ID exists. Keep the
`#shop-quick-results` body. (The `📷` button reuses the existing
`triggerShopIdentifyPhoto()` and its hidden `#shop-identify-input`, which lives
inside `#shop-manual-card`.)

> NOTE: an element ID must be unique. After this step, `grep -c 'id="shop-quick-search"' src/frontend/index.html` MUST return `1`. Same for `id="shop-preferred-store"`.

- [ ] **Step 4: Wrap the stats strip into the Shop pane and add a slim variant**

Move `#shopping-stats-row` (the `.shopping-summary-strip`, ~3233–3261) so it is
the first child of a new `<div class="shopping-mode-pane" id="shopping-pane-shop">`
container, and move `#shopping-session-banner` (~3228) in just after it. Replace
the three big `.shopping-summary-pill` elements' wrapper class `shopping-summary-strip`
with `shopping-stats-slim`, and convert each pill to a chip:

```html
<div class="shopping-stats-slim" id="shopping-stats-row">
  <button type="button" class="chip" id="shopping-pill-open"
          onclick="setShoppingListView('open')">Open <span id="shop-open-count-main">0</span></button>
  <span class="chip" id="shopping-pill-estimate">Est <span id="shop-estimated-total-main">$0.00</span></span>
  <button type="button" class="chip" id="shopping-pill-purchased"
          onclick="setShoppingListView('purchased')">Done <span id="shop-purchased-count-main">0</span></button>
</div>
```

- [ ] **Step 5: Leave Current List + Past Trips as shared (outside both panes)**

Ensure `#shopping-current-list-card` and `#shopping-past-trips-card` sit AFTER
`</div>` of `#shopping-pane-shop` and are NOT inside either pane, so they render
in both modes. The Plan pane (`#shopping-pane-plan`) and Shop pane
(`#shopping-pane-shop`) both close before these two cards.

- [ ] **Step 6: Verify structure renders**

Hard-refresh. Expected: segmented control shows under the title; the page no
longer shows the old `🔍`/`✨` icons; Current List + Past Trips visible. (Mode
toggling not wired yet — both panes may show; that's fixed in Task 3.) No console
errors. Confirm ID uniqueness:

Run: `grep -c 'id="shop-quick-search"' src/frontend/index.html`
Expected: `1`

- [ ] **Step 7: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(shopping): segmented Plan/Shop panes in markup, unified add bar, slim stats"
```

---

### Task 3: Wire `shoppingMode` state, switcher, and smart default

**Files:**
- Modify: `src/frontend/index.html` — JS near `shoppingListView` (~8056) and `loadShoppingList()` (~29679); add `setShoppingMode()` near `setShoppingListView` (~10170)

- [ ] **Step 1: Add the mode state variables**

Find the `let shoppingListView = (() => {` block (~8056). Immediately before it, add:

```javascript
// Shopping tab mode: 'shop' (check-off) | 'plan' (entry). In-memory only —
// every fresh load re-applies the smart default (see applyShoppingSmartDefault).
let shoppingMode = "shop";
let shoppingModeUserSet = false; // true once the user taps the segmented control
```

- [ ] **Step 2: Add `setShoppingMode()` and `applyShoppingSmartDefault()`**

Immediately after the `setShoppingListView` function (find its closing `}` near
~10200), add:

```javascript
function setShoppingMode(mode, fromUser = false) {
  shoppingMode = mode === "plan" ? "plan" : "shop";
  if (fromUser) shoppingModeUserSet = true;
  const shopPane = document.getElementById("shopping-pane-shop");
  const planPane = document.getElementById("shopping-pane-plan");
  if (shopPane) shopPane.hidden = shoppingMode !== "shop";
  if (planPane) planPane.hidden = shoppingMode !== "plan";
  document
    .getElementById("shopping-mode-shop")
    ?.classList.toggle("is-active", shoppingMode === "shop");
  document
    .getElementById("shopping-mode-plan")
    ?.classList.toggle("is-active", shoppingMode === "plan");
}

function applyShoppingSmartDefault(openCount) {
  // Only choose automatically until the user makes an explicit choice this session.
  if (shoppingModeUserSet) {
    setShoppingMode(shoppingMode);
    return;
  }
  setShoppingMode(Number(openCount) > 0 ? "shop" : "plan");
}
```

- [ ] **Step 3: Call the smart default at the end of `loadShoppingList()`**

In `loadShoppingList()` (~29679), the body ends with `renderShoppingQuickResults();`
on line ~29711. Add immediately after it (still inside the function):

```javascript
        applyShoppingSmartDefault(data.open_count ?? 0);
```

- [ ] **Step 4: Verify mode switching + smart default**

Hard-refresh on a NON-empty list. Expected: lands in **Shop** mode — add bar and
recommendations hidden, stats chips + list visible. Tap **✏ Plan** → add bar,
recommendations appear; tap **🛒 Shop** → they hide again. Now mark every item
done (or use an empty list) and hard-refresh. Expected: lands in **Plan** mode.
No console errors.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(shopping): shoppingMode state, segmented switcher, smart default"
```

---

### Task 4: Confirm the slim stats filter still drives the list view

**Files:**
- Modify: `src/frontend/index.html` — `setShoppingListView()` (~10170) and `updateShoppingListViewPills()`

**Why:** `setShoppingListView`/`updateShoppingListViewPills` toggle an `is-active`
class on `#shopping-pill-open` / `#shopping-pill-purchased`. Those IDs still
exist (now chips), so behavior should carry over — this task verifies and fixes
any class mismatch.

- [ ] **Step 1: Inspect the pill-update code**

Run: `grep -n "updateShoppingListViewPills" src/frontend/index.html`
Open that function. Confirm it toggles `is-active` on `#shopping-pill-open` and
`#shopping-pill-purchased`. The `.shopping-stats-slim button.chip.is-active` CSS
from Task 1 styles that state, so no code change is needed if the IDs match.

- [ ] **Step 2: If it references removed classes, update them**

If the function adds/removes a class other than `is-active` (e.g. a pill-specific
class that no longer exists), change those lines to toggle only `is-active`. Show
the edit you make here. If it already uses `is-active`, make no change.

- [ ] **Step 3: Verify filtering**

In Shop mode, tap **Open** chip → list shows only open items, chip gets the active
outline. Tap **Done** chip → list shows purchased items. Confirm the estimate chip
is non-interactive (a `<span>`, no pointer cursor).

- [ ] **Step 4: Commit (only if a change was made)**

```bash
git add src/frontend/index.html
git commit -m "fix(shopping): slim stats chips drive Open/Done list filter"
```

---

### Task 5: Inline manual form in Plan + remove dead helper/intro chrome

**Files:**
- Modify: `src/frontend/index.html` — `toggleManualShoppingForm()` (~27204), `#shopping-helper-intro` usage

- [ ] **Step 1: Confirm the manual form toggles inline within Plan**

The `＋` button in the add bar calls `toggleManualShoppingForm()`, which shows
`#shop-manual-card`. Since `#shop-manual-card` now lives inside
`#shopping-pane-plan`, it appears inline in Plan mode. Hard-refresh, go to Plan,
tap `＋`. Expected: the manual-add form (photo identify + Name/Category/Store/
Price/Qty/Note + "Add to Shopping List") expands inline; tapping `＋` or "Hide"
collapses it.

- [ ] **Step 2: Neutralize the now-orphaned helper-intro if it injects content**

Run: `grep -n "shopping-helper-intro" src/frontend/index.html`
If JS writes guidance into `#shopping-helper-intro`, leave the element (now inside
Plan pane) — it is harmless and only shows in Plan. If it is never populated,
delete the empty `<div id="shopping-helper-intro"></div>` to drop dead markup.
Show which case applied.

- [ ] **Step 3: Verify no duplicate/dead toggles remain**

Run: `grep -n "shopping-quick-header-toggle\|shopping-recommendations-toggle" src/frontend/index.html`
Expected: **no matches** (the old header icon toggles were removed in Task 2). If
any JS still references those IDs, it will no-op via `?.` — confirm no console
errors on load and on tab open.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "chore(shopping): inline manual add in Plan, drop dead header chrome"
```

---

### Task 6: Full manual verification pass against the spec

**Files:** none (verification only)

- [ ] **Step 1: Smart default**

Empty/all-done list → tab opens in **Plan**. Non-empty open list → opens in **Shop**.

- [ ] **Step 2: Shop mode contents**

Only visible: segmented control, slim stats chips (Open/Est/Done) with working
Open/Done filter, session banner *when a trip is active*, store-grouped Current
List, collapsed Past Trips. No search/store/＋/photo, no Recommendations.

- [ ] **Step 3: Plan mode contents**

Visible: add bar (🔍 search + 🏬 store + ＋ + 📷), inline manual form on ＋,
Recommendations, slim stats, the editable store-grouped Current List, collapsed
Past Trips.

- [ ] **Step 4: No data reload / state loss on switch**

Toggle Shop↔Plan several times. The list does not refetch or re-flash, sort
selection persists, and check states persist.

- [ ] **Step 5: List behavior unchanged**

Store grouping, A/Z/$ sort chips, check-off, add, edit, delete all behave as
before. Confirm against the spec's success criteria 1–6.

- [ ] **Step 6: Regression sweep**

Open every other tab once (Kitchen, Receipts, Budget, etc.) — no console errors,
no layout breakage from the CSS additions.

- [ ] **Step 7: Final commit / branch ready for PR**

```bash
git add -A
git commit -m "test(shopping): manual verification pass — declutter complete" --allow-empty
```

---

## Notes for the implementer
- One ID per element. After Task 2, `#shop-quick-search` and `#shop-preferred-store` must each appear exactly once.
- Reuse existing functions verbatim — do not rewrite `renderShoppingListTable`, `setShoppingListView`, `loadRecs`, `renderShoppingSessionBanner`, or `loadShoppingPastTrips`. Only their DOM parent changes.
- `var(--accent…)` fallbacks are provided in case the theme tokens differ; if the project defines accent tokens, prefer those names (check the `:root` block).
- No backend, API, or schema edits. No JS test framework. If something seems to need one, stop and raise it.
