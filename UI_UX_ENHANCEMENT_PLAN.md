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
| (populated after each phase review) | | | |

---

## Phase 1 — Foundation

*Covers: design tokens, typography scale, color system, spacing system, base element polish — all aligned to the frontend-design skill.*

| Task | Status | Notes |
|------|--------|-------|
| Extend `:root` with surface-3, border-strong, text-subtle, accent-hover, accent-pressed, ring, overlay | ⏳ | Keep existing token names untouched to avoid JS breakage |
| Add full spacing scale (`--space-1`..`--space-12`) and radius scale (`--radius-xs`..`--radius-pill`) | ⏳ | New tokens; existing rules progressively migrated in Phase 2 |
| Add shadow scale (`--shadow-xs`..`--shadow-lg`) tuned for dark canvas | ⏳ | Luminance-lift approach, not heavy drops |
| Add motion tokens (`--ease-out`, `--ease-in-out`, `--duration-*`) | ⏳ | Replace ad-hoc `0.22s ease` occurrences in Phase 3 |
| Wire Fraunces as display font for page titles, card titles, stat values (currently loaded but unused) | ⏳ | `font-family: "Fraunces", Georgia, serif;` applied only to `h1`, `h2`, `.stat-value`, `.page-title`, `.card-title` |
| Introduce `--font-display` / `--font-body` / `--font-mono` tokens and use via CSS var | ⏳ | Future-proofs font swaps |
| Define typography scale via CSS custom properties (`--fs-xs`..`--fs-3xl`) and line-height tokens | ⏳ | Replace sub-0.8rem uppercase labels (currently 0.74rem) with min 0.8rem non-uppercase or uppercase w/ letter-spacing |
| Base element pass: `body`, `h1`–`h6`, `p`, `a`, `hr`, `::selection`, scrollbar | ⏳ | Consistent colors; accessible `::selection` on accent |
| Re-theme default focus outline to `--ring` tokens on all focusable tags (`:focus-visible` selector) | ⏳ | Kill browser-default blue outlines; ensure a11y |

**Phase 1 acceptance:** token block expanded, Fraunces visible on headings/titles/stat values, no regressions in existing pages, typography feels more editorial without losing compactness.

## Phase 2 — Component Polish

*Covers: buttons, inputs, cards, modals, navigation, tables/lists — migrated to the Phase 1 tokens.*

| Task | Status | Notes |
|------|--------|-------|
| Buttons: unify `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-lg` to token-driven padding / radius / weight | ⏳ | Min-height 36px desktop / 44px mobile |
| Inputs & selects: unified height, padding, border, focus ring; consistent disabled styling | ⏳ | Phase 2 does *not* alter form validation behavior |
| `.form-group` / `.form-grid`: consistent label size, spacing, helper-text slot | ⏳ | Labels promoted from 0.74rem to `--fs-sm` (0.82rem), sentence-case |
| Cards / stat cards / summary tiles: unify padding, radius, border, hover elevation | ⏳ | Same visual language across dashboard, receipts summary, bills, analytics |
| Sidebar & nav-item: refresh active state (subtle left accent bar instead of full fill), improve hover | ⏳ | Keep existing selectors |
| Modals / overlays: unified `.confirm-modal` base — scrim uses `--overlay`, panel uses `--surface-2`, radius `--radius-lg`, `--shadow-lg` | ⏳ | Applies to all 6+ overlays (`confirm-overlay`, `image-lightbox-overlay`, `manual-entry-overlay`, `cash-transaction-overlay`, `bill-provider-detail-overlay`, `device-pairing-overlay`, `secret-qr-overlay`) |
| Tables / list rows: zebra tone via `--surface-2`, consistent row height, truncation rules | ⏳ | Receipts table + extracted items + shopping rows |
| Pills / badges / chips (refund pill, budget chips, transaction type): one token-driven family | ⏳ | Shapes and contrast ratios consistent |
| Emoji-icon buttons: pair each with `aria-label`, adopt consistent circular button frame | ⏳ | Does not change symbols |

**Phase 2 acceptance:** components look coherent across every workspace; no mixed old/new button or card on the same screen.

## Phase 3 — Interaction & Motion

*Covers: hover, focus, active, disabled, loading states, micro-animations, page-reveal motion.*

| Task | Status | Notes |
|------|--------|-------|
| Standardise hover / active / focus-visible / disabled states on all interactive elements via tokens | ⏳ | Replace ad-hoc `:hover` rules that use bare color literals |
| Workspace page enter: staggered reveal of stat cards / header (`animation-delay` children) — once per route, not on every re-render | ⏳ | `@media (prefers-reduced-motion: reduce)` respected |
| Modal open/close: fade scrim + scale-from-95 panel; 200ms `--ease-out` | ⏳ | Replaces abrupt appearance |
| Loading spinners: align to accent; skeleton rows for receipt/extracted-items loads | ⏳ | Skeleton is a thin polish over existing spinner usage |
| Swipe-bought undo toast: slide-up from bottom with elastic ease, auto-dismiss progress bar | ⏳ | Non-destructive enhancement of existing behavior |
| Button press: subtle scale(0.98) + color darken via `--accent-pressed` | ⏳ | Feels tactile on mobile |
| Save-success / delete confirmations: brief inline status pill with fade-out instead of silent success | ⏳ | No new notification library; CSS + class toggle |
| Respect `prefers-reduced-motion` globally | ⏳ | Wrap motion tokens in a reduced-motion media query |

**Phase 3 acceptance:** interactions feel intentional and consistent; no animation that interferes with keyboard/screen-reader flow; reduced-motion users get a static experience.

## Phase 4 — Mobile Experience

*Covers: touch targets, responsive edge cases, bottom-sheet modals, swipe patterns, viewport fixes.*

| Task | Status | Notes |
|------|--------|-------|
| Enforce ≥44px min touch target on every `.btn`, `.nav-item`, inline row action, inline select | ⏳ | Includes receipt row actions, shopping row actions, bill rows |
| Receipt inline editor: split 8-column desktop line-item row into 2 stacked rows below 1480px to kill horizontal scroll | ⏳ | CSS-only; highest-impact item from prior audit |
| Extracted items list: add sticky search/filter field on mobile (no-op on desktop if width allows) | ⏳ | Long receipts (50+ items) become usable |
| Image preview: allow pinch-zoom / wheel-zoom on inline receipt image (no lightbox detour required) | ⏳ | Small JS addition, non-breaking |
| Modals on mobile: promote to bottom-sheet (slide up from bottom, rounded top corners, drag handle) when viewport ≤640px | ⏳ | Keeps existing `.confirm-modal` HTML; CSS-only rule change |
| Mobile receipt-item cards: dynamic header summary (item name + total) instead of "Item 1/2/3" | ⏳ | Small JS change within existing render function |
| Safe-area padding (`env(safe-area-inset-*)`) on sticky bars for iOS notch | ⏳ | Hits sidebar, sticky action strips, bottom-sheet modals |
| Tap-friendly emoji-icon row actions: min 44×44, consistent spacing between them | ⏳ | Addresses receipt / shopping / bills action rows |
| Horizontal-scroll audit: Bills planning panel, Receipts filter panel, Analytics charts on small screens | ⏳ | Fix overflow cases |

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
