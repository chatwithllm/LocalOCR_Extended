# Design System Inspired by Notion — LocalOCR_Extended

A warm, paper-like, minimal design system for **LocalOCR_Extended**, adapted from Notion's visual language. This document is the single authoritative reference for tokens, typography, components, and layout across every workspace in the app: Dashboard, Inventory (with Products toggle), Budget, Upload Receipt, Receipts, Shopping List, Analytics, Restaurant, Expenses, Contribution, and Settings.

Use this doc together with `DARK_REDESIGN.md` — `DARK_REDESIGN.md` is the integration *prompt* (role, scope, questions, checklist); this file is the design *spec* being integrated.

---

## 1. Why Notion's Language Fits LocalOCR_Extended

LocalOCR_Extended is a household receipt, inventory, and expense platform that runs across three distinct environments:

- **Desktop browsers** — household members doing receipt correction, analytics review, budget management
- **Phones** — shopping helper QR flow, uploads from the aisle, quick inventory checks
- **Shared household screens** — fridge tablets and kitchen displays paired via trusted-device QR, running in Shared Household / Kitchen Display / Read Only scopes

The app is fundamentally a **reading and correcting** tool — receipts, line items, inventory rows, shopping lists, contribution history, analytics. Notion's aesthetic is built around long-form reading and structured content, which is exactly our shape. Warm neutrals, whisper borders, and layered-but-restrained shadows give us:

- **Receipt imagery that feels like paper on paper** — the warm white background (`#f6f5f4`) frames a receipt photo the way a tabletop frames a printed receipt
- **Dense data that stays calm** — inventory rows, line items, and analytics tables never feel cramped, because whitespace and whisper borders do the separation work
- **A shared visual language across three domains** — Grocery, Restaurant, and General Expense read as distinct through iconography and badge tinting without introducing new palettes
- **A kitchen display that doesn't glow in the dark** — Notion's high-contrast near-black-on-white scales up beautifully to 10ft-viewable fridge screens without being harsh

---

## 2. Visual Theme & Atmosphere

**Warm paper, not cold glass.** Page canvas is pure white (`#ffffff`); text is near-black (`rgba(0,0,0,0.95)`), never pure black. Warm grays (`#f6f5f4`, `#31302e`, `#615d59`, `#a39e98`) carry yellow-brown undertones. The app should feel like quality paper — approachable, tactile, calm.

**Whispers, not walls.** Borders are `1px solid rgba(0,0,0,0.1)` throughout. Shadows stack 4–5 layers with individual opacity never exceeding 0.05. Depth is felt, not seen.

**NotionInter as the backbone.** A modified Inter with aggressive negative letter-spacing at display sizes. Four weights (400 / 500 / 600 / 700) carry the full hierarchy. OpenType features `"lnum"` and `"locl"` on larger text.

**Notion Blue (`#0075de`) is the only saturated color in core UI chrome.** Reserved for primary CTAs (Upload, Save correction, Pair device) and links. Domain differentiation, status, and semantic states lean on pill badges and icons — never on accent-color swaps.

**Key characteristics at a glance:**
- NotionInter with negative letter-spacing at display sizes (-2.125px at 64px)
- Warm neutral palette with yellow-brown undertones
- Near-black text via `rgba(0,0,0,0.95)`
- Ultra-thin borders: `1px solid rgba(0,0,0,0.1)`
- Multi-layer shadow stacks with sub-0.05 opacity
- Notion Blue (`#0075de`) as the singular accent
- Pill badges (9999px radius) with tinted backgrounds for status and domain
- 8px base spacing unit with an organic, non-rigid scale

---

## 3. Color Palette & Roles

### Primary
| Token | Value | Usage |
|:------|:------|:------|
| `--color-text` | `rgba(0,0,0,0.95)` | Primary text, headings, receipt line items |
| `--color-bg` | `#ffffff` | Page canvas, card surface, modal surface |
| `--color-accent` | `#0075de` | Primary CTA, link, focus, active nav item |

### Brand Secondary
| Token | Value | Usage |
|:------|:------|:------|
| `--color-accent-active` | `#005bab` | CTA pressed state |
| `--color-navy` | `#213183` | Rare emphasis, dark feature sections (e.g. Kitchen Display header) |

### Warm Neutral Scale
| Token | Value | Usage |
|:------|:------|:------|
| `--color-surface-warm` | `#f6f5f4` | Alternating section bg, Receipts list bg, empty-state surface |
| `--color-surface-dark` | `#31302e` | Kitchen Display optional dark mode, dark feature panels |
| `--color-text-secondary` | `#615d59` | Descriptions, metadata, timestamps, "Last seen 3 days ago" |
| `--color-text-muted` | `#a39e98` | Placeholders, disabled states, empty-list captions |
| `--color-border` | `rgba(0,0,0,0.1)` | Every whisper border |

### Semantic Accents (use sparingly, always paired with icon + label)
| Token | Value | Product Usage |
|:------|:------|:---------------|
| `--color-teal` | `#2a9d99` | Successful OCR parse indicator, backup success |
| `--color-green` | `#1aae39` | Purchased ✓, item in stock, budget under-target |
| `--color-orange` | `#dd5b00` | Low-stock indicator, budget approaching target, OCR needs review |
| `--color-pink` | `#ff64c8` | Contribution scoreboard highlight, "streak" decorations |
| `--color-purple` | `#391c57` | Admin-only surfaces, premium feature hints |
| `--color-brown` | `#523410` | Grocery domain badge tint (warm, earthy) |

### Domain Badges (pill backgrounds, high readability)
| Domain | Bg | Text | Icon |
|:-------|:---|:-----|:-----|
| Grocery | `#fef5e7` | `#8a5a00` | shopping basket |
| Restaurant | `#fde8f0` | `#a0216e` | utensils |
| General Expense | `#edf2fb` | `#2a4a99` | receipt |

These domain tints are **pill-only**. Cards, sections, and chrome stay neutral — the badge is the signal.

### Interactive
| Token | Value | Usage |
|:------|:------|:------|
| `--color-link` | `#0075de` | Text links, inline receipt references |
| `--color-link-dark` | `#62aef0` | Links on dark surfaces (Kitchen Display, dark panels) |
| `--color-focus` | `#097fe8` | Focus ring on every interactive element |
| `--color-badge-info-bg` | `#f2f9ff` | "New", "Manual entry", "OCR reviewed" pill bg |
| `--color-badge-info-text` | `#097fe8` | Pill text on info badge |

### Shadows & Depth
```
--shadow-card:
  rgba(0,0,0,0.04) 0px 4px 18px,
  rgba(0,0,0,0.027) 0px 2.025px 7.84688px,
  rgba(0,0,0,0.02) 0px 0.8px 2.925px,
  rgba(0,0,0,0.01) 0px 0.175px 1.04062px;

--shadow-deep:
  rgba(0,0,0,0.01) 0px 1px 3px,
  rgba(0,0,0,0.02) 0px 3px 7px,
  rgba(0,0,0,0.02) 0px 7px 15px,
  rgba(0,0,0,0.04) 0px 14px 28px,
  rgba(0,0,0,0.05) 0px 23px 52px;

--border-whisper: 1px solid rgba(0,0,0,0.1);
```

---

## 4. Typography

### Font Stack
```
NotionInter, Inter, -apple-system, system-ui, "Segoe UI", Helvetica,
"Apple Color Emoji", Arial, "Segoe UI Emoji", "Segoe UI Symbol"
```
OpenType features `"lnum"` and `"locl"` enabled on text ≥20px.

### Hierarchy

| Role | Size | Weight | Line Height | Letter Spacing | LocalOCR Usage |
|:-----|:-----|:-------|:------------|:---------------|:---------------|
| Display Hero | 64px | 700 | 1.00 | -2.125px | Guest demo hero ("Track every receipt") |
| Display Secondary | 54px | 700 | 1.04 | -1.875px | Dashboard greeting ("Good evening, Sam") |
| Section Heading | 48px | 700 | 1.00 | -1.5px | Workspace titles ("Inventory", "Receipts") |
| Sub-heading Large | 40px | 700 | 1.50 | normal | Metric displays ("$4,213 this month") |
| Sub-heading | 26px | 700 | 1.23 | -0.625px | Card headers, receipt store name |
| Card Title | 22px | 700 | 1.27 | -0.25px | Stat cards, feature cards, inventory groups |
| Body Large | 20px | 600 | 1.40 | -0.125px | Lead copy, budget summary |
| Body | 16px | 400 | 1.50 | normal | Line items, receipt detail, descriptions |
| Body Medium | 16px | 500 | 1.50 | normal | Nav items, active UI text |
| Body Semibold | 16px | 600 | 1.50 | normal | Table headers, strong labels |
| Nav / Button | 15px | 600 | 1.33 | normal | Sidebar nav, button labels |
| Caption | 14px | 500 | 1.43 | normal | Metadata, timestamps |
| Caption Light | 14px | 400 | 1.43 | normal | Descriptions beneath metrics |
| Badge | 12px | 600 | 1.33 | 0.125px | Pill badges (domain, status, "Manual") |
| Micro Label | 12px | 400 | 1.33 | 0.125px | Receipt IDs, "Last updated 2m ago" |

### Numerics (LocalOCR-specific)
Prices, quantities, and budget figures use **lining numerals** (`"lnum"` on). Totals in receipt line items, analytics columns, and budget cards should feel like ledger entries — aligned, regular, readable. Use `font-variant-numeric: tabular-nums` on any numeric column to preserve alignment across rows.

### Principles
- **Compression at scale.** -2.125px at 64px relaxes progressively to -0.625px at 26px, normal at 16px.
- **Four-weight system.** 400 (read) / 500 (interact) / 600 (emphasize) / 700 (announce).
- **Tight display, relaxed body.** Line height moves from 1.00 at display to 1.50 at body.
- **Badges use positive tracking.** 12px badge text is the only positive letter-spacing (0.125px) in the system.

---

## 5. Component Stylings

### Buttons

**Primary (Upload, Save correction, Pair device, Confirm)**
- Background: `#0075de`
- Text: `#ffffff`, 15px / weight 600
- Padding: 8px 16px
- Radius: 4px
- Hover: background → `#005bab`
- Active: `scale(0.98)`
- Focus: `2px solid #097fe8` outline + `--shadow-card`

**Secondary (Cancel, Re-run OCR, Rotate, Mark as Restaurant)**
- Background: `rgba(0,0,0,0.05)`
- Text: near-black, 15px / weight 600
- Padding: 8px 16px
- Radius: 4px
- Hover: background → `rgba(0,0,0,0.08)`
- Active: `scale(0.98)`

**Ghost / Link (inline "Open receipt", "View details")**
- Background: transparent
- Text: `rgba(0,0,0,0.95)` or `--color-link` for true links
- Hover: underline
- Active: no transform

**Destructive (Revoke trusted device, Delete draft — confirmation only)**
- Background: `#ffffff`
- Text: `#c4002b`
- Border: `1px solid #f0c4cc`
- Hover: background → `#fdf2f4`
- Used **only inside confirm modals**, never as a top-level button

### Pill Badges

**Status (Manual entry, OCR reviewed, New, Live)**
- Background: `#f2f9ff` / Text: `#097fe8`
- 4px 8px padding, 9999px radius, 12px / weight 600, 0.125px tracking

**Domain (Grocery / Restaurant / General Expense)**
- See domain table in §3 — always paired with a small icon

**Trusted-device scope (Shared Household / Kitchen Display / Read Only)**
- Neutral: `rgba(0,0,0,0.05)` bg, `#615d59` text
- Read Only variant: adds a lock icon

**Contribution streak / rank**
- `#fde8f0` bg, `#a0216e` text — sparing use, only on Contribution and Dashboard ranking surfaces

### Cards & Containers

**Standard card (stat cards, receipt list items, inventory rows-as-cards on mobile)**
- Background: `#ffffff`
- Border: `--border-whisper`
- Radius: 12px
- Shadow: `--shadow-card`
- Padding: 16px (compact) / 24px (default) / 32px (featured)
- Hover (when clickable): shadow intensifies to `--shadow-deep`, no lift, no border color change

**Featured / hero card (Dashboard household ranking, guest demo hero)**
- Radius: 16px
- Shadow: `--shadow-deep`
- Optional warm white (`#f6f5f4`) interior for alternation

**Receipt image card**
- Image fills top half with 12px 12px 0 0 radius
- Image has internal `1px solid rgba(0,0,0,0.1)` border so it reads as a framed photo
- Body below is 16px padding, white background

**Empty state**
- Background: `#f6f5f4` (warm white)
- Large icon at top (64px, `#a39e98`)
- Title at 22px / weight 700
- Body at 16px / `#615d59`
- CTA as primary or secondary button

### Form Inputs

**Text input, select, textarea**
- Background: `#ffffff`
- Border: `1px solid #dddddd`
- Radius: 4px
- Padding: 6px 10px
- Text: `rgba(0,0,0,0.9)`, 16px / weight 400
- Placeholder: `#a39e98`
- Focus: border → `#097fe8`, 2px outer ring at `rgba(9,127,232,0.2)`

**Receipt correction editor specifics**
- Numeric inputs (subtotal, tax, tip, total): right-aligned, tabular-nums
- Line-item rows use a 3-column grid (name / qty / price) with 8px gaps
- Store name input uses Body Large (20px / 600)
- Date picker inherits input styling — never introduce custom popover chrome

**Eye-toggle password field**
- Icon button sits inside the input, right edge, 32px hit target
- Resets to hidden after successful login (per existing product behavior)

### Navigation

**Left sidebar (desktop, signed-in)**
- Width: 240px, collapsible (the app already remembers this choice — preserve it)
- Background: `#ffffff`, right edge: `--border-whisper`
- Nav items: 15px / weight 500, 8px 12px padding, 5px radius
- Active item: background `rgba(0,117,222,0.08)`, text `--color-accent`, weight 600
- Hover: background `rgba(0,0,0,0.04)`

**Top nav (guest, public)**
- Logo left, centered workspace pills, "Sign in" primary button right
- 64px tall, white background, bottom `--border-whisper`

**Mobile**
- Hamburger top-right, full-width dropdown, `#ffffff` bg
- Each item is a 48px-tall row for touch comfort
- Bottom of the panel: Upload Receipt CTA as primary button

**Page header magnifier (mobile Inventory / Shopping)**
- Icon-only ghost button in the top bar
- Tapping reveals an input that slides in, focus-trapped

### Data Surfaces

**Inventory / Shopping / Receipts list rows**
- Background: `#ffffff`, alternating rows get `#fafaf9` (a half-step warmer than pure white)
- Whisper border between rows
- 12px 16px padding
- Hover: row background → `rgba(0,0,0,0.03)`
- Long-press (mobile Dashboard ranking): row expands in-place with 200ms ease-out, reveal chevron rotates

**Budget cards (Dashboard)**
- Label: saved target (e.g. "Grocery · $800 target") — 14px / 500 / `#615d59`
- Value: current spend (e.g. "$612 used") — 40px / 700
- Progress bar: 6px tall, `rgba(0,0,0,0.06)` track, `--color-accent` fill
- Approaching target (≥80%): fill color → `--color-orange`
- Over target: fill color → `#c4002b`

**Analytics charts**
- Gridlines: `rgba(0,0,0,0.06)`
- Axis labels: 12px / 500 / `#615d59`
- Primary series: `--color-accent`
- Comparison series: `#615d59` or `#a39e98`
- Never use more than 3 colors in a single chart

**Trust / QR / device management (Settings)**
- Device cards: 12px radius, warm-white interior
- Scope badges on the right
- Rename / Revoke as ghost buttons; Revoke opens a confirm modal with the destructive variant

---

## 6. Layout Principles

### Spacing
Base unit: 8px. Allowed values: **2, 4, 8, 12, 16, 24, 32, 48, 64, 80, 120** (px). Use fractional values (5.6, 6.4) only for optical adjustment inside a component, never at layout scale.

### Grid & Container
- Max content width: 1200px
- Workspace shell: left sidebar (240px) + content area with 32px horizontal padding (desktop), 16px (mobile)
- Dashboard grid: 12-column, cards span 3 / 4 / 6 / 12
- Receipts list: single-column at <768px, two-column at ≥1080px (list left, detail right)
- Upload Receipt: centered single column, max 640px

### Whitespace Philosophy
- **Generous vertical rhythm.** 64–120px between major sections on public / guest pages; 32–48px in authenticated workspaces where density matters.
- **Warm alternation.** Alternate white (`#ffffff`) and warm white (`#f6f5f4`) section backgrounds on long pages (guest demo, Analytics, Contribution).
- **Content-first density.** Authenticated workspaces prioritize scannable rows over airy spacing — 12–16px row padding, whisper dividers. Public / guest pages breathe.

### Border Radius
| Scale | Radius | Usage |
|:------|:-------|:------|
| Micro | 4px | Buttons, inputs, checkboxes |
| Subtle | 5px | Nav items, dropdown items |
| Standard | 8px | Small cards, inline blocks |
| Comfortable | 12px | Default cards, receipt image frames |
| Large | 16px | Featured / hero cards, modals |
| Full | 9999px | Pill badges, avatars-as-badges |
| Circle | 100% | User avatars, tab indicators |

---

## 7. Depth & Elevation

| Level | Treatment | Use |
|:------|:----------|:----|
| 0 — Flat | No shadow, no border | Body copy, plain text blocks |
| 1 — Whisper | `--border-whisper` only | Dividers, table rows, nav edges |
| 2 — Soft card | `--shadow-card` + whisper border | Standard cards, stat cards, list items |
| 3 — Deep card | `--shadow-deep` + whisper border | Receipt detail panel, modals, Dashboard hero |
| 4 — Focus | `2px solid --color-focus` outline | Keyboard focus on every interactive element |

Shadows accumulate from many low-opacity layers so elements feel **embedded in the page**, not floating above it. Never use a single hard shadow.

---

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|:-----|:------|:------------|
| Mobile Small | <400px | Single column, 12px padding, Upload CTA pinned to footer |
| Mobile | 400–600px | Standard mobile, stacked cards |
| Tablet Small | 600–768px | 2-col grids begin |
| Tablet | 768–1080px | Full card grids, sidebar can collapse |
| Desktop Small | 1080–1200px | Standard desktop, sidebar persistent |
| Desktop | 1200–1440px | Full layout, 1200px max |
| Large Desktop | >1440px | Centered, generous margins |

### Environment-specific variants
- **Kitchen Display (`layout_kitchen.html`)**
  - Base type size scales 1.25× (body becomes 20px)
  - Interactive elements disabled by default; touch zones, when enabled, are ≥56px
  - Prefer `--color-surface-dark` (`#31302e`) bg with `#f5f5f4` text for nighttime glanceability if the household prefers; otherwise default white
  - Animations reduced or disabled (see §10)
- **Read Only scope**
  - All CTAs render as disabled ghost buttons with tooltip "Read only — pair a full-access device to edit"
- **Guest demo**
  - Persistent top banner: `#f2f9ff` bg, 14px / 500 text "You're viewing sample data — sign in to save receipts"
  - All save / edit buttons render as primary but open the sign-in modal instead of submitting

### Touch Targets
- Buttons: min 40px tall, 44px on mobile
- Row-level tap targets (inventory rows, receipt list items): min 48px tall on mobile
- Icon-only buttons (rotate, magnifier, eye-toggle, revoke): 32×32px minimum, 40×40px on mobile

### Collapsing Strategy
- Display hero: 64px → 40px → 26px, letter-spacing scales proportionally
- Sidebar: persistent → collapsible → hamburger
- Receipts two-column (list + detail) → single column with back nav
- Inventory grouped rows: 4 columns → 2 → 1
- Analytics charts: maintain aspect ratio, legend moves below on <768px
- Section spacing: 80–120px → 48px on mobile

---

## 9. Accessibility & States

### Focus
- Every interactive element gets a visible `2px solid --color-focus` ring, 2px offset
- Focus rings survive on dark Kitchen Display surfaces — use `--color-link-dark` (`#62aef0`) variant
- Keyboard tab order matches visual reading order in every workspace

### Contrast
| Pairing | Ratio | Status |
|:--------|:------|:-------|
| `rgba(0,0,0,0.95)` on `#ffffff` | ~18:1 | AAA ✓ |
| `#615d59` on `#ffffff` | ~5.5:1 | AA ✓ |
| `#0075de` on `#ffffff` | ~4.6:1 | AA (large text) ✓ |
| `#097fe8` on `#f2f9ff` | ~4.5:1 | AA (large text) ✓ |
| `#ededef` on `#31302e` (Kitchen Display dark) | ~11:1 | AAA ✓ |

### States
- **Default** — base styling
- **Hover** — text color shift OR background shift, never both; buttons use `scale(1.02)` max
- **Active / Pressed** — `scale(0.98)` on buttons, darker bg variant
- **Focus** — blue outline ring (see above)
- **Disabled** — `#a39e98` text, `rgba(0,0,0,0.03)` bg, `cursor: not-allowed`
- **Loading** — inline spinner (16px, `--color-accent`), never replace the whole surface with a skeleton unless the wait exceeds 400ms

### Color independence
Never rely on color alone for meaning. Budget state uses icon + label + color. Domain uses icon + label + tint. OCR status uses icon + label + tint. Screen readers get the label; colorblind users get the icon.

---

## 10. Motion

- **Standard transition:** 200ms, `cubic-bezier(0.2, 0, 0, 1)` (ease-out)
- **Hover transitions:** 150ms
- **Entrance / modal:** 240ms, expo-out `cubic-bezier(0.16, 1, 0.3, 1)`
- **Long-press reveal (mobile ranking):** 200ms reveal, 160ms collapse
- **Movements are tiny** — ≤4px translate, `scale(0.98)`–`scale(1.02)`, never bouncy
- **`prefers-reduced-motion: reduce`** — disable entrance animations, long-press reveal transitions, and any decorative motion on Kitchen Display. Keep focus ring and hover color transitions (they're functional feedback, not decoration).

---

## 11. LocalOCR-Specific Patterns

### Receipt correction editor
The most-used authenticated surface. Treat the receipt image as hero content, the editor as an unobtrusive working surface.

- Image panel left, editor right on desktop; image on top, editor below on mobile
- Image: framed with whisper border inside a 12px card, rotate controls as ghost icon buttons in the top-right corner
- Editor inputs: 16px body, 6px padding, numeric fields right-aligned with tabular-nums
- Line item table: sticky header row, add-row button as a ghost "+ Add line" below
- Save button (primary) and Cancel (secondary) in a sticky footer strip with whisper top border
- "Re-run OCR" and "Mark as restaurant" as secondary buttons with icon + label
- Corrected state: small pill badge at top "OCR reviewed · 2m ago" (`#f2f9ff` bg, `#097fe8` text)

### OCR feedback (Upload Receipt)
- Intent picker: 4 pill buttons (Auto / Grocery / Restaurant / General Expense), 9999px radius, selected state uses `--color-accent` bg + white text
- Upload drop zone: 16px radius, 2px dashed `#dddddd` border, warm-white bg, icon + prompt centered
- Processing state: inline progress with OCR step labels ("Parsing image…", "Extracting line items…") — keep text calm, never alarm
- Multi-candidate restaurant assist: show candidates as 3 small cards side-by-side, each with a confidence badge, clicking one prefills the editor

### Dashboard household ranking
- Top-three row: cards with warm-white background, large position number (40px / 700), avatar, name, contribution score
- Long-press (mobile) reveals the full leaderboard inline — use `--shadow-deep` on the expanded panel
- Streak / achievement pills use `#fde8f0` bg, `#a0216e` text (pink variant), sparingly

### Trusted device management (Settings)
- Each device as a 12px-radius card with whisper border
- Device icon (fridge / tablet / phone) + name + scope badge + last-seen timestamp
- Actions (rename / scope / revoke) as ghost buttons in the card footer
- Revoke opens a confirm modal with destructive-variant button — never revoke in-place

### Three-domain differentiation
Grocery, Restaurant, General Expense are differentiated exclusively through:
1. Pill badge tint + icon (on receipt rows, analytics legends, budget cards)
2. Workspace-specific empty states with domain illustration
3. Section labels in section headings

Never re-skin cards, change accent colors, or reflow layouts by domain.

### Guest demo marking
A 40px-tall banner across the top of every page:
```
bg: #f2f9ff
text: "You're viewing sample data. Sign in to save receipts." (14px / 500 / #097fe8)
right: "Sign in" primary button
```
Plus every save / submit button in guest mode opens sign-in instead of submitting.

### MQTT / Home Assistant readouts
Render as developer-tool strips: monospace font (system mono fallback), `#f6f5f4` bg, 12px / 500, small green dot for "live", small gray dot for "disconnected". These are the only surfaces that break NotionInter — intentionally, to signal they are infrastructure, not content.

---

## 12. Agent Prompt Guide

### Quick reference
- Primary CTA: Notion Blue (`#0075de`)
- Background: Pure White (`#ffffff`)
- Alt background: Warm White (`#f6f5f4`)
- Text: Near-Black (`rgba(0,0,0,0.95)`)
- Secondary text: Warm Gray 500 (`#615d59`)
- Muted text: Warm Gray 300 (`#a39e98`)
- Border: `1px solid rgba(0,0,0,0.1)`
- Focus: Focus Blue (`#097fe8`)

### Example prompts for this codebase

**Workspace shell**
> "Build a workspace shell in `src/templates/layouts/authenticated.html`. White bg, 240px left sidebar with whisper right border, collapsible (persist state — the app already remembers this). Nav items 15px NotionInter weight 500, 8px 12px padding, 5px radius. Active item bg `rgba(0,117,222,0.08)`, text `#0075de`, weight 600. Top-right: user avatar, notification bell (ghost icon button), Upload Receipt primary button."

**Receipt correction editor**
> "Build the receipt correction panel. Two-column on ≥1080px, stacked on mobile. Left: receipt image in a 12px-radius card with whisper border, rotate-left/rotate-right ghost icon buttons top-right. Right: structured editor — store name input at 20px / weight 600, date picker, subtotal/tax/tip/total as right-aligned tabular-nums inputs, line-item table with sticky header. Sticky footer with Cancel (secondary) and Save (primary). Include a small 'OCR reviewed · 2m ago' pill (`#f2f9ff` bg, `#097fe8` text, 9999px radius, 12px weight 600) at the top of the editor."

**Stat card**
> "Stat card for the Dashboard. White bg, whisper border, 12px radius, `--shadow-card`. 24px padding. Label at top: 14px / 500 / `#615d59`. Value: 40px / 700 / near-black, tabular-nums. Optional trend below: 14px / 500, green `#1aae39` for positive, orange `#dd5b00` for attention."

**Pill badge partial**
> "Create `partials/badge.html` accepting `variant` (info / grocery / restaurant / expense / scope / streak) and `label`. All variants are 9999px radius, 4px 8px padding, 12px NotionInter weight 600, 0.125px letter-spacing. Info: `#f2f9ff` bg `#097fe8` text. Grocery: `#fef5e7` / `#8a5a00` with basket icon. Restaurant: `#fde8f0` / `#a0216e` with utensils icon. Expense: `#edf2fb` / `#2a4a99` with receipt icon."

**Empty state**
> "Build an empty-state partial. `#f6f5f4` bg, 16px radius, 48px padding, centered content. 64px icon in `#a39e98`, title 22px / weight 700, body 16px / `#615d59`, optional primary CTA. Used in empty Inventory, empty Shopping List, and the guest-mode hero."

### Iteration rules
1. Warm neutrals only — grays have yellow-brown undertones, never blue-gray
2. Letter-spacing scales with size — -2.125px at 64px, normal at 16px
3. Four weights: 400 / 500 / 600 / 700
4. Borders are whispers: `1px solid rgba(0,0,0,0.1)` — never heavier
5. Shadows always 4–5 layers, individual opacity ≤0.05
6. Warm white (`#f6f5f4`) alternation for visual rhythm on long pages
7. Pill badges (9999px) for status/domain/scope, 4px radius for buttons and inputs
8. Notion Blue (`#0075de`) is the only saturated color in core chrome — use sparingly for CTAs and links
9. Three-domain differentiation through badges + icons, never through palette swaps
10. Kitchen Display is a layout variant, not a new design language — same tokens, bigger type, less motion

---

## 13. Anti-Patterns (What to Avoid)

1. **Cold blue-gray neutrals.** If a gray looks like iOS system gray, it's wrong. Warm yellow-brown undertone is the tell.
2. **Pure black text.** Always `rgba(0,0,0,0.95)`.
3. **Heavy borders or single hard shadows.** Whisper-only borders, multi-layer shadows only.
4. **Accent color for decoration.** Blue is for CTAs, links, focus, and active nav — that's it.
5. **Domain-specific layouts or palettes.** Grocery/Restaurant/Expense share chrome and tokens. Differentiation is badge + icon.
6. **Bouncy or large-movement animations.** Keep transforms under 4px and scale between 0.98–1.02.
7. **Drop shadows on receipt images.** The whisper border is the frame. Shadows compete with the receipt's own visual weight.
8. **Re-skinning Kitchen Display as a different product.** It's the same app, bigger and calmer.
9. **Mixing destructive styling into primary flows.** Revoke/Delete live only in confirmation modals.
10. **Replacing NotionInter anywhere except MQTT/HA readouts.** Those are developer readouts; everything else is content.

---

## 14. Relationship to Other Docs

- **`DARK_REDESIGN.md`** — the integration *prompt* (role, discovery questions, implementation plan, checklist). This is a **separate design exploration**; only one should be active at a time. Pick this Notion-inspired system OR the Linear dark system — do not blend.
- **`PRD.md`** — product scope and workflows. This design doc dresses those workflows; it doesn't change them.
- **`docs/COMPLETE_PRODUCT_SPEC.md`** — feature-level behavior. Design must respect all behavioral contracts there.
- **`CONTINUITY.md`** — handoff and session context for agents picking up the work.

When in doubt, behavior beats aesthetics. Never regress `/data/receipts`, trusted-device tokens, MQTT topics, guest-mode enforcement, or admin-only controls for the sake of visual cohesion.
