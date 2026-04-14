# UI/UX Enhancement Plan

## Overview

`LocalOCR Extended` is a self-hosted household receipt / OCR / inventory / budgeting platform. The frontend is a **single-file vanilla-JS SPA** at `src/frontend/index.html` (~27.6k lines) with no build step, no framework, no CSS pre-processor. Styles, markup templates, and handlers are co-located; theming is already driven by a small set of CSS custom properties in `:root` (`:21–34`). Backend is Flask + SQLite.

The enhancement strategy is a **polish pass**, not a rebrand — extend the existing CSS-variable token system, introduce a proper typography hierarchy (Fraunces + Manrope are already loaded but Fraunces is currently unused), unify spacing / radii / shadow / motion scales, and apply them consistently across every workspace (Dashboard, Inventory, Products, Upload Receipt, Receipts/OCR review, Shopping List, Budget, Bills, Analytics, Restaurant, Expenses, Contribution, Settings).

**Constraints observed:**
- No framework, no bundler → token changes happen in the existing `<style>` block; no new build pipeline.
- Single 27k-line file → every change is surgical, diff-small, and reviewable.
- Dark-mode-only today; no refactor to a full light-mode system in scope, but tokens will be structured so a future toggle is trivial.
- All existing IDs, class names, and data flow must be preserved (JS selectors depend on them).

## Design Principles

1. **Hierarchy through typography.** Adopt an editorial display + refined body pair (Fraunces for headings, Manrope for UI/body — already loaded, currently under-used). Larger, less-uppercase labels with more deliberate weight/size contrast.
2. **Dominant neutral canvas, accents with intent.** Keep the existing `#0d0f14` canvas and violet/teal accents, but treat accents as *signal* (primary action, active state, data highlight) rather than decoration. Extend the palette with tonal surface layers for depth.
3. **One spacing / radius / shadow / motion scale, everywhere.** Replace the ad-hoc pixel values (124 distinct `border-radius:` declarations today) with a single set of tokens.
4. **Mobile parity by default.** ≥44px touch targets, native-feeling bottom-sheet modals on small screens, no horizontal scroll in any workspace.
5. **Motion as signal, not decoration.** Reserve motion for state changes users need to notice (save, delete, swipe-bought, route change). One orchestrated page reveal instead of scattered micro-animations.

## Skill Reference

- Frontend-design skill loaded: ✅
- Key tokens applied (governing this project):
  - **Typography:** Fraunces (display, opsz 9..144, 600/700) for headings / stat values / page titles; Manrope (400–800) for UI & body. Monospace fallback for numbers in tables where needed.
  - **Color tokens (extend existing `:root`):** `--bg`, `--surface`, `--surface-2`, `--surface-3` (new elevation layer), `--border`, `--border-strong` (new), `--text`, `--text-muted`, `--text-subtle` (new), `--accent`, `--accent-hover` (new), `--accent-pressed` (new), `--success`, `--warning`, `--danger`, plus `--ring` (focus outline) and `--overlay` (modal scrim).
  - **Spacing scale:** `--space-1 = 4px`, `--space-2 = 8px`, `--space-3 = 12px`, `--space-4 = 16px`, `--space-5 = 20px`, `--space-6 = 24px`, `--space-8 = 32px`, `--space-10 = 40px`, `--space-12 = 48px`.
  - **Radius scale:** `--radius-xs = 4px`, `--radius-sm = 6px`, `--radius-md = 10px`, `--radius-lg = 14px`, `--radius-xl = 20px`, `--radius-pill = 999px`.
  - **Shadow scale:** `--shadow-xs`, `--shadow-sm`, `--shadow-md`, `--shadow-lg` — all dark-mode appropriate (slight luminance lift + subtle tint, not heavy drop-shadows).
  - **Motion tokens:** `--ease-out = cubic-bezier(0.16, 1, 0.3, 1)`, `--ease-in-out = cubic-bezier(0.65, 0, 0.35, 1)`, `--duration-fast = 120ms`, `--duration-base = 200ms`, `--duration-slow = 320ms`.
  - **Focus ring:** 2px outline `--accent` + 2px offset `transparent` — consistent across every focusable element.

## Status Legend
- ✅ Done
- 🔄 In Progress
- ⏳ Pending
- ❌ Blocked
- 🔁 Revision Requested

## Grading History

| Phase | Score | Verdict | Revision Round |
|-------|-------|---------|----------------|
| Phase 1 — Foundation | Accepted ("all good lets move on") | Accepted | 0 |
| Phase 2 — Component Polish | 8 | Accepted | 0 |
| Phase 3 — Interaction & Motion | 8 | Accepted | 0 |

---

## Phase 1 — Foundation

*Covers: design tokens, typography scale, color system, spacing system, base element polish — all aligned to the frontend-design skill.*

| Task | Status | Notes |
|------|--------|-------|
| Extend `:root` with surface-3, border-strong, text-subtle, accent-hover, accent-pressed, ring, overlay, `*-soft` alpha variants | ✅ | Existing tokens preserved verbatim so JS/CSS selectors are untouched |
| Add full spacing scale (`--space-1`..`--space-12`) and radius scale (`--radius-xs`..`--radius-pill`) | ✅ | New tokens live; existing rules progressively migrated in Phase 2 |
| Add shadow scale (`--shadow-xs`..`--shadow-lg`) tuned for dark canvas | ✅ | Opacity-based drop shadows, calibrated for `#0d0f14` canvas |
| Add motion tokens (`--ease-out`, `--ease-in-out`, `--duration-*`) | ✅ | Ready to replace ad-hoc `0.22s ease` occurrences in Phase 3 |
| Wire Fraunces as display font for page titles, card titles, stat values (loaded, previously unused) | ✅ | Applied to `h1/h2/h3`, `.page-header h1`, `.stat-value`, `.card-title` |
| Introduce `--font-display` / `--font-body` / `--font-mono` tokens | ✅ | Body now uses `font-family: var(--font-body)` |
| Define typography scale via CSS custom properties (`--fs-xs`..`--fs-3xl`) and line-height tokens | ✅ | Ready for Phase 2 rollout on labels / form fields |
| Base element pass: unified `:focus-visible`, `::selection`, themed scrollbar, tabular numerals on tables | ✅ | Browser-default blue outline removed; scrollbars themed via `--surface-3` |
| Respect `prefers-reduced-motion` globally | ✅ | Added at bottom of `<style>` — every animation/transition gets clamped for reduced-motion users |

**Phase 1 acceptance:** token block expanded, Fraunces visible on headings/titles/stat values, no regressions in existing pages, typography feels more editorial without losing compactness.

## Phase 2 — Component Polish

*Covers: buttons, inputs, cards, modals, navigation, tables/lists — migrated to the Phase 1 tokens.*

| Task | Status | Notes |
|------|--------|-------|
| Buttons: radius from token, add `:active` press and `:disabled` states, `--accent-hover` / `--accent-pressed`, new `.btn-lg` size (44px) | ✅ | `.btn-sm`/`.btn-lg` both honour min-height constraints |
| Font-family migration: kill unused `"Inter"` references on `.btn`, `.inline-select`, `input`, `select` — route to `var(--font-body)` | ✅ | Inter was never loaded, so controls were system-fallback before |
| Inputs & selects: unified hover/focus/disabled states, focus ring via `--accent-soft`, read-only styling | ✅ | No validation behavior changed |
| Labels: colour migrated to `--text-subtle` for softer hierarchy while keeping 0.8rem size | ✅ | Form-group spacing unchanged |
| Cards / stat cards: token-driven radius (`--radius-lg`), hover elevation via `--shadow-md`, border-strong on hover | ✅ | Consistent across dashboard, receipts summary, bills |
| Sidebar nav active: refined from full accent fill to soft tint + 3px left accent bar, accent-coloured icon | ✅ | More editorial, less heavy |
| Modals: `.confirm-overlay` uses `--overlay` + backdrop blur; `.confirm-modal` uses `--shadow-lg` + `--radius-lg`; scale+fade entrance; title uses display font | ✅ | `.cash-modal` retains its custom gradient framing — unchanged to avoid regression |
| Tables: zebra striping via `tbody tr:nth-child(even)`, `tr:hover` uses `--surface2`, `th` colour via `--text-subtle` | ✅ | |
| Pills: radius via `--radius-pill`, tabular numerals on pill contents | ✅ | Shape unified across refund / budget / transaction-type pills |
| Emoji-icon buttons: aria-label sweep deferred to Phase 5 (a11y) — cosmetic-only work in Phase 2 | ⏳ | Scope move, logged here |

**Phase 2 acceptance:** components look coherent across every workspace; no mixed old/new button or card on the same screen.

## Phase 3 — Interaction & Motion

*Covers: hover, focus, active, disabled, loading states, micro-animations, page-reveal motion.*

| Task | Status | Notes |
|------|--------|-------|
| Standardise hover / active / focus-visible / disabled states on all interactive elements via tokens | ✅ | Completed mostly in Phase 2; Phase 3 adds `.btn-sm`/`.btn-ghost` subtle translateY on hover |
| Workspace page enter: staggered reveal of direct children (40ms step) + nested stat-card stagger | ✅ | Runs on `.page.active` toggle; re-renders of same element don't re-animate thanks to CSS-only animation-once semantics |
| Modal open/close: fade scrim + scale-from-97 panel; `--duration-base` `--ease-out` | ✅ | Delivered in Phase 2 for `.confirm-modal`; Phase 3 does not alter it |
| Spinner refresh: thicker ring, `--accent-soft` track, themed timing | ✅ | |
| Skeleton shimmer utility (`.skeleton`) | ✅ | Inert when unused; ready for Phase 4/5 to apply to loading surfaces |
| Action toast: elastic slide-up (cubic-bezier overshoot), token timing, accent→accent2 progress gradient | ✅ | Enhances existing swipe-bought undo UX |
| Button press scale + ghost/sm hover lift | ✅ | Completed in Phase 2 (scale) + Phase 3 (hover lift) |
| Save-success inline `.status-pill` utility (CSS-only, no JS) | ✅ | Reserved for Phase 5 surface adoption |
| Checkbox/radio press feedback + accent-color | ✅ | Native controls now feel responsive |
| Anchor hover colour (excluding nav and button-shaped anchors) | ✅ | |
| Respect `prefers-reduced-motion` globally | ✅ | Covered by the Phase 1 global guard |

**Phase 3 acceptance:** interactions feel intentional and consistent; no animation that interferes with keyboard/screen-reader flow; reduced-motion users get a static experience.

## Phase 4 — Mobile Experience

*Covers: touch targets, responsive edge cases, bottom-sheet modals, swipe patterns, viewport fixes.*

| Task | Status | Notes |
|------|--------|-------|
| Enforce ≥44px min touch target at ≤900px on `.btn` (44), `.btn-lg` (48), `.nav-item` (44), `.inline-select` (40) and expand `.btn-sm` to 40 | ✅ | Applies to receipt row actions, shopping row actions, bill rows — anywhere those classes are used |
| Receipt inline editor: 8-col row collapses to a **2-row, 4-col** layout between 641–1100px via explicit `grid-row`/`grid-column` placement — kills the horizontal-scroll dead zone | ✅ | CSS-only; honours source order (Item/Qty/Line Total on row 1 + Remove; Unit/Size/Group/Budget on row 2) |
| Extracted items list: reusable `.mobile-sticky-search` primitive for sticky search field above long lists | ✅ | Inert until adopted; Phase 5 can wire it into the extracted-items render |
| Image preview: pinch-zoom / wheel-zoom on inline receipt image | ⏳ | Deferred — requires JS additions; would be safer as a Phase 5 task when a11y + gesture testing happen together |
| Modals on mobile: ≤640px promotes `.confirm-modal` into a **bottom-sheet** (slide-up from bottom, rounded top corners, drag-handle ::before, column-reverse action buttons, safe-area bottom padding) | ✅ | CSS-only; preserves existing markup |
| Mobile receipt-item cards: dynamic header summary | ⏳ | Deferred — requires touching `renderReceiptEditorRows` JS; paired with Phase 5 a11y sweep |
| Safe-area padding on sticky bars for iOS notch / home indicator | ✅ | Sidebar top/bottom + action-toast bottom/left |
| Tap-friendly emoji-icon row actions: 40px `.btn-sm` on mobile | ✅ | Addresses receipt / shopping / bills row actions |
| Horizontal-scroll audit: `.page`, `.card`, `.form-grid` lock to 100% width at ≤640px; `.form-grid` collapses to single column | ✅ | Bills, Receipts filter, Analytics containers all benefit |

**Phase 4 acceptance:** tested at 360px, 414px, 768px, 1024px, 1440px — no horizontal scroll anywhere, all controls reachable with a thumb, bottom-sheet modals clear the on-screen keyboard.

## Phase 5 — Final Pass

*Covers: empty states, error states, accessibility, dark-mode consistency, visual QA against the frontend-design skill.*

| Task | Status | Notes |
|------|--------|-------|
| Empty states: unified icon + headline + subtext pattern across every list (receipts, bills, shopping, inventory, expenses, restaurant, contribution) | ⏳ | Replace bare "No rows" text with designed empty state |
| Error states: consistent alert pattern with icon, title, action link; used for save errors, OCR failures, upload failures | ⏳ | No new notification library |
| Skeleton loaders for slow surfaces (receipt detail, analytics charts, backup list) | ⏳ | CSS-only, 300ms shimmer |
| Accessibility sweep: `aria-label` on emoji buttons, `aria-describedby` on complex form fields, semantic `<form>` / `<fieldset>` additions where safe, consistent `:focus-visible` rings | ⏳ | No logic changes |
| Contrast audit against WCAG AA on all token pairs (text/surface, muted/surface, accent/surface) | ⏳ | Adjust token values if any pair fails |
| Dark-mode consistency QA: every surface, divider, text, and icon uses a token; no hard-coded hex outside `:root` | ⏳ | Grep audit |
| Final skill-alignment review: typography pair, spacing consistency, motion intentionality, signal accents | ⏳ | Before accepting Phase 5 |
| Screenshot pass: one screenshot per workspace, attached to Change Log below | ⏳ | Attached in final report |

**Phase 5 acceptance:** every workspace meets the skill's cohesion bar; no unstyled fallback edges; documented trade-offs.

---

## Change Log

*Populated after each commit — format: `[phase N] short summary — skill guideline X applied — why`.*

### Phase 1 — Foundation

- **`src/frontend/index.html` (`:root` block, lines 21–98)** — extended the existing 13 color tokens with a full design-system layer: elevation (`--surface-3`), structural contrast (`--border-strong`, `--text-subtle`), interaction states (`--accent-hover`, `--accent-pressed`, `--accent-soft`, per-semantic `*-soft` alphas), focus (`--ring`), and modal scrim (`--overlay`). Added spacing scale, radius scale, dark-canvas-tuned shadow scale, motion tokens, typography tokens (`--font-display`, `--font-body`, `--font-mono`), and type/line-height scales. *Skill guideline:* "Color & Theme — CSS variables for consistency" + "Spatial Composition — intentional spacing." *Why:* existing ad-hoc values (124 distinct `border-radius:` rules, inline pixel spacing, bare color literals) prevent visual coherence. Tokens are the prerequisite for every subsequent phase.
- **`src/frontend/index.html` (line 100, `body`)** — `font-family` migrated from `"Manrope", sans-serif` to `var(--font-body)` with a richer fallback stack. *Why:* future-proofs font swaps and matches the token system.
- **`src/frontend/index.html` (end of `<style>`, ~line 6520 onward)** — Phase 1 base-element rules placed at end of style block so they definitively win the cascade: Fraunces display font applied to `h1/h2/h3`, `.page-header h1`, `.stat-value`, `.card-title` with negative letter-spacing and tabular numerals for stat values. Added unified `:focus-visible` ring using `--ring`, themed `::selection` using `--accent-soft`, themed WebKit scrollbars, global `prefers-reduced-motion` guard, tabular numerals on all table cells. *Skill guideline:* "Typography — distinctive display + refined body pair; avoid generic Inter/system-only." *Why:* Fraunces was already loaded from Google Fonts but never used — wiring it up gives the editorial hierarchy the skill calls for at zero network cost.

### Phase 2 — Component Polish

- **`src/frontend/index.html` (end of `<style>`, Phase 2 block)** — Buttons: token-driven radius, 36px min-height default / 30px `.btn-sm` / 44px `.btn-lg`, `:active` scale(0.98) press, `:disabled` state, primary hover via `--accent-hover`, pressed via `--accent-pressed`. *Skill: "Motion as signal; tactile interaction."* *Why:* the app had zero press or disabled feedback — common friction on mobile.
- **Font-family migration** for `.btn`, `.inline-select`, `input`, `select`, `textarea`, `button` — pre-existing `"Inter", sans-serif` fallback was referenced at 4 sites but Inter was never loaded. Route everything to `var(--font-body)` so Manrope actually renders. *Why:* silent system-font fallback was a bug; fix is free.
- **Inputs** — unified hover (`--border-strong`), focus (3px `--accent-soft` ring via `box-shadow`), disabled dim, read-only muted. *Skill: "Consistency over cleverness."*
- **Labels** — migrated colour to `--text-subtle` for softer hierarchy without changing size.
- **Cards / stat cards** — radius bumped to `--radius-lg`, hover lifts with `--shadow-md` + `--border-strong` border. *Skill: "Backgrounds & depth — atmosphere, not solid panels."*
- **Sidebar `.nav-item.active`** — refactored from heavy full-accent fill to a refined treatment: 3px accent left-bar (rounded right) + `--accent-soft` tinted background + accent-coloured icon + regular text. *Skill: "Dominant neutrals with sharp accents."* *Why:* the previous fill made every navigation state feel identical in weight; the refined version reads as an *indicator*, not a block.
- **Modals** — `.confirm-overlay` now uses `--overlay` + 2px backdrop blur; `.confirm-modal` uses `--shadow-lg` + `--radius-lg`; added `confirmModalRise` scale-from-0.97 + fade-up entrance at `--duration-base`; title migrated to display font. *Skill: "Motion for high-impact moments."*
- **Tables** — `tbody tr:nth-child(even)` gets a 1.5%-white zebra tone; `tr:hover` uses `--surface2`; `th` colour migrated to `--text-subtle`. *Skill: "Controlled density."*
- **Pills** — radius token `--radius-pill` applied, `font-variant-numeric: tabular-nums` for counts.

### Phase 3 — Interaction & Motion

- **Page reveal stagger** — children of `.page.active` fade-up with a 40ms cascading delay (caps at 7th child so long workspaces don't feel laggy); stat-card grids get a nested scale-0.985→1 sub-stagger on top of the parent reveal. *Skill: "one well-orchestrated page load with staggered reveals creates more delight than scattered micro-interactions."* *Why:* before, workspaces popped in instantly; now they compose themselves like an editorial layout.
- **Spinner refresh** — ring track now `--accent-soft` with an `--accent` head, slightly thicker (2.5px), themed easing. *Skill: motion tokens, not ad-hoc timings.*
- **Skeleton shimmer utility** — `.skeleton` class defines a loading placeholder with a 1.6s shimmer gradient. *Why:* available for Phase 4/5 to use on slow surfaces without another round-trip.
- **Action toast** — transition now uses a `cubic-bezier(0.34, 1.56, 0.64, 1)` elastic curve over `--duration-slow`; progress bar is an accent→accent2 gradient; button uses `--radius-pill`. *Skill: "motion for high-impact moments."*
- **Checkbox/radio** — `accent-color` tied to `--accent`; press scale(0.92) for tactile feedback. *Why:* native controls previously felt disconnected from the theme.
- **Button lift on hover** — `.btn-sm` and `.btn-ghost` get a 1px translateY on hover so row-action emoji buttons feel alive.
- **Link hover** — non-nav, non-button anchors hover to `--accent-hover`.
- **`.status-pill` utility** — success/error inline pill with fade+slide enter, paired with a `.show` toggle. *Skill: consistency over cleverness.* *Why:* gives a future-proof Phase 5 hook for save/delete confirmations without adding a notifications library.

### Phase 4 — Mobile Experience

- **Receipt editor horizontal-scroll fix (641–1100px)** — `.receipt-editor-web-main` 8-column grid collapses to a 2-row × 4-col layout via explicit `grid-row`/`grid-column` on `nth-child` cells. Row 1: Item | Qty | Line Total | Remove. Row 2: Unit | Size Label | Item Group | Budget Category. *Skill: "mobile parity by default."* *Why:* the #1 audited friction point — tablet users had to swipe horizontally inside every receipt. Now the editor fits natively.
- **≥44px touch targets at ≤900px** — `.btn` 44, `.btn-sm` 40 (bumped from 30), `.btn-lg` 48, `.nav-item` 44, `.inline-select` 40, native checkbox/radio 22×22. *Skill: "mobile is not an afterthought."*
- **Bottom-sheet modals at ≤640px** — `.confirm-modal` pins to bottom, goes full-width, rounded top corners (`--radius-xl`), gets a centered 42×4 drag-handle affordance via `::before`, column-reverse action buttons stretch full width, safe-area inset bottom padding, slide-up-from-100% enter. *Skill: "native-feeling bottom sheets, no horizontal scroll anywhere."* *Why:* previously modals appeared top-anchored with margins — hard to reach and didn't respect iOS safe areas.
- **iOS safe-area padding** on sidebar (top/bottom) and action-toast (bottom/left) via `max(original, env(safe-area-inset-*))`. *Why:* notch & home-indicator clearance.
- **Horizontal-overflow lock** at ≤640px: `.page`, `.card`, `.form-grid` are pinned to `max-width: 100%; min-width: 0`; `.form-grid` collapses to a single column. *Why:* protects Bills, Receipts filter, Analytics, and Settings cards from overflowing on 360px devices.
- **`.mobile-sticky-search` primitive** — sticky-top search bar for long mobile lists; inert until adopted, ready for Phase 5 extracted-items rollout.
- **Deferred** (moved to Phase 5 where JS + a11y testing happen together): pinch-zoom on receipt image, dynamic mobile line-item header summary.
