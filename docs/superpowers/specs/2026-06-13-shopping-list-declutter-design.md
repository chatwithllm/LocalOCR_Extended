# Shopping List Tab Declutter — Plan / Shop Modes

**Date:** 2026-06-13
**Status:** Approved (design), pending implementation plan
**Scope:** Frontend only — the `#page-shopping` view in `src/frontend/index.html` (markup + its JS/CSS). No backend, API, or data-model changes.

## Problem

The Shopping List tab stacks nine blocks vertically before reaching the list the
user values:

1. Title + `🔍`/`✨` header icon toggles
2. Helper-intro text (`#shopping-helper-intro`)
3. Active-trip session banner (`#shopping-session-banner`)
4. Stats pills — Open / Estimate / Close (`#shopping-stats-row`)
5. "Add Item Manually" card (`#shop-manual-card`)
6. Quick Find card (`#shopping-quick-find-card`)
7. Recommendations card (`#shopping-recommendations-card`)
8. **Current List — grouped by store** (`#shopping-current-list-card`)
9. Past Trips (`#shopping-past-trips-card`)

Four separate discovery/entry surfaces (4–7) plus duplicate toggles push the
store-grouped list far down the page. The list and its store-grouping are good
and stay unchanged; everything around them is cluttered.

User-confirmed usage: uses Quick Find, Manual add, and the session banner;
does **not** rely on Recommendations or Past Trips; stats pills can shrink.
Uses the tab roughly equally for **home planning** and **in-store check-off**.

## Solution: two modes behind a segmented control

A segmented control (`🛒 Shop | ✏ Plan`) sits directly under the title and
replaces the `🔍`/`✨` header icon toggles. The list and a slim stats row appear
in **both** modes; entry tools and recommendations appear only in Plan.

### Default behavior
- On tab open: **smart default** — show **Plan** when the current list has zero
  open items, otherwise show **Shop**.
- The active mode is held in a module-level `shoppingMode` variable. It persists
  while navigating within the running SPA, but is **not** written to
  `localStorage`: every fresh page load re-applies the smart default rather than
  restoring a stale mode.

### Shop mode (in-store check-off)
- **Slim stats row** — `Open · Estimate · Done` as small chips (not the large
  pills). Tapping **Open** or **Done** filters the list, preserving today's
  `setShoppingListView('open'|'purchased')` behavior.
- **Session banner** — shown only when a trip is active (unchanged condition).
- **Current List** — store-grouped, with large tap targets for checking items
  off. Rendering logic and store-grouping (`#shopping-table-body`,
  `shoppingStoreGroupKey`) are **unchanged**.
- **Past Trips** — collapsed accordion at the bottom.
- No Quick Find / Manual / Recommendations visible.

### Plan mode (building the list)
- **Add bar** — a single row combining: `🔍 search` (Quick Find,
  `#shop-quick-search`), `🏬 store` selector (`#shop-preferred-store`),
  `＋ manual`, and `📷 photo` identify. The manual-add form
  (`#shop-manual-card` contents) opens **inline** when `＋` is tapped, rather
  than living as a permanent stacked card.
- **Recommendations** — present in Plan only (`#shopping-recs-body`,
  `loadRecs`).
- **Slim stats** — `Open · Estimate` (filtering optional here).
- **Current List** — same store-grouped list, with per-row edit/delete so the
  user sees what's already added while planning.
- **Past Trips** — collapsed accordion at the bottom.

## What changes vs. what stays

**Removed / folded in:**
- `🔍`/`✨` header icon toggles (`#shopping-quick-header-toggle`,
  `#shopping-recommendations-toggle`) → replaced by the segmented control.
- Helper-intro block as a permanent element → its guidance moves into the
  relevant empty states.
- The four always-stacked cards (stats pills, manual card, Quick Find card,
  Recommendations card) → re-homed by mode; no longer all rendered at once.

**Unchanged (explicit non-goals):**
- List rendering, store-grouping, sort chips (A / Z / $), check-off, item
  CRUD, and all shopping API calls (`shoppingApi`).
- Backend, schema, and every other tab.
- The set of capabilities: Quick Find, Manual add, photo identify,
  Recommendations, stats filtering, session banner, and Past Trips all remain
  reachable — only their placement changes.

## Implementation surface (for the plan)

- **Markup:** restructure `#page-shopping` (currently `src/frontend/index.html`
  lines ~3197–3509) into: header + segmented control; a Shop-mode container; a
  Plan-mode container; shared list + Past Trips.
- **State/JS:** add `shoppingMode` ('shop' | 'plan') with a `setShoppingMode()`
  that toggles container visibility and re-runs the existing render; compute the
  smart default from open-item count after the list loads; keep
  `setShoppingListView`, `setShoppingSort`, `toggleManualShoppingForm`,
  `loadRecs`, and Past Trips toggling working against their new homes.
- **CSS:** segmented-control styles; slim stats-chip row (replacing
  `.shopping-summary-pill`); mode show/hide; inline manual-form treatment.

## Success criteria

1. Opening the tab shows the segmented control; smart default lands on Plan when
   the list is empty, Shop otherwise.
2. Shop mode shows only: slim stats (with working Open/Done filter), session
   banner (when active), store-grouped list with large tap targets, collapsed
   Past Trips. No entry tools or recommendations visible.
3. Plan mode shows: add bar (search + store + manual ＋ + photo), inline manual
   form on ＋, Recommendations, slim stats, the editable store-grouped list,
   collapsed Past Trips.
4. Switching modes does not reload data or lose list state.
5. Store-grouped list rendering, sorting, and check-off behave exactly as before.
6. No backend/API/schema changes; no regressions in other tabs.

## Open micro-decisions (resolved defaults)
- Manual add opens **inline** (not a bottom sheet).
- Past Trips remains a **collapsed accordion** (not moved to a `⋯` menu).
