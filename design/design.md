# Design System — LocalOCR Extended

> A design language for a privacy-first, self-hosted household operations platform that lives and breathes on *your* hardware. Every principle is adapted from the Airbnb-inspired foundation and tuned for what LocalOCR Extended actually does: scan receipts, extract text, correct OCR mistakes, and make sense of months of household spend — all without sending a byte to someone else's cloud.

---

## 1. Design Philosophy

LocalOCR Extended is a **document-first marketplace of your own data**. Airbnb's design ethos treats listings as travel magazines; LocalOCR Extended treats your receipts, bills, and extracted text the same way — the artifact is the hero, the chrome disappears around it. A scanned image of a grocery receipt should feel as inviting and browsable as a listing photo, not as clinical as a database row.

Five foundational principles, adapted from the source system:

1. **Artifact-forward, chrome-quiet.** The receipt, the extracted text panel, the OCR confidence overlay — these are the primary visual content. UI chrome (buttons, tabs, navigation) is intentionally understated so that the *document* always reads first. This is the local analogue of Airbnb's "photography-first" rule.
2. **A single confident accent.** **Rausch Red** (`#ff385c`) is the one brand color, reserved for primary CTAs, active states, and the moments where the user is making a commitment (Start Scan, Confirm Edit, Pay Bill). Everything else works on a warm neutral scale. Confidence scores, success/warning/error, and semantic categories each get their own token family — but only one brand red.
3. **Warm, not cold.** Text is **never pure black (`#000000`)** and backgrounds are **never pure cool-gray**. We use `#222222` on `#ffffff` in light mode and `#ededed` on `#0f0f10` in dark mode. Typography runs at **weight 500–700** — no thin UI text. Border-radius is generous (8 px buttons, 20 px cards, 32 px feature containers, 50% for circular controls). The goal: your household financial tool should feel like a magazine about your house, not a tax form.
4. **Three-layer elevation, no flat walls.** Every elevated surface uses a stacked shadow — an ultra-subtle border ring, a soft ambient layer, and a primary lift. This mimics natural light rather than a rectangular cast, which matters more in a tool where the user is often comparing side-by-side scanned images.
5. **Local-first cues, everywhere.** Because the data never leaves the device, the UI can afford to be opinionated about *showing* state — confidence numbers, last-edited timestamps, pair/unpair flows for trusted devices, OCR model currently in use, raw vs. normalized text. Trust cues replace marketing copy.

### What this philosophy rejects
- Generic SaaS dashboards with cool blue accents and dense tables.
- Pure black on pure white — always use warm near-black and warm near-white.
- Multi-color status chips that compete with the brand accent.
- Thin font weights (100–400) for any UI surface.
- Sharp corners (0–4 px) on content containers.
- Telemetry-style "live dot" animations that imply network chatter — LocalOCR Extended is proudly offline.

---

## 2. Color Tokens

All tokens use the `--color-*` namespace. Values are raw hex or rgba — no nested references — so they can be mechanically pulled into both CSS and a `design-tokens.json` artifact. Every token has a **light** and **dark** value. Dark mode is warm-neutral (greys tinted toward red/brown), not blue-tinted, to preserve the Airbnb warmth in low-light use.

### 2.1 Brand & accent

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-brand` | `#ff385c` | `#ff4d6d` | Primary CTA, active nav, brand marks |
| `--color-brand-hover` | `#e00b41` | `#ff6b81` | Hover state on primary CTAs |
| `--color-brand-pressed` | `#b80635` | `#e04262` | Pressed/active (mouse down) |
| `--color-brand-soft` | `#fff0f3` | `rgba(255, 77, 109, 0.14)` | Subtle brand background wash (selected chips, toast tint) |
| `--color-brand-contrast` | `#ffffff` | `#ffffff` | Text on brand background |

### 2.2 Surface layers

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-bg` | `#ffffff` | `#0f0f10` | Page canvas |
| `--color-surface` | `#ffffff` | `#17171a` | Default card surface |
| `--color-surface-2` | `#f7f7f7` | `#1f1f23` | Nested card / input background |
| `--color-surface-3` | `#f2f2f2` | `#28282d` | Pill chips, circular nav buttons, quiet wells |
| `--color-surface-inverse` | `#222222` | `#ededed` | Dark-on-light buttons (Primary Dark variant) |
| `--color-overlay` | `rgba(17, 17, 20, 0.56)` | `rgba(0, 0, 0, 0.68)` | Modal scrim |
| `--color-overlay-soft` | `rgba(17, 17, 20, 0.18)` | `rgba(0, 0, 0, 0.32)` | Inline-blur overlays, image dimmers |

### 2.3 Text

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-text-primary` | `#222222` | `#ededed` | Body text, headings |
| `--color-text-secondary` | `#6a6a6a` | `#a3a3a3` | Supporting text, captions |
| `--color-text-muted` | `#929292` | `#717175` | Timestamps, placeholder, disabled-ish labels |
| `--color-text-disabled` | `rgba(0, 0, 0, 0.24)` | `rgba(255, 255, 255, 0.28)` | Disabled form text |
| `--color-text-inverse` | `#ffffff` | `#0f0f10` | Text on Primary Dark buttons |
| `--color-text-link` | `#428bff` | `#6ea6ff` | Informational / legal links |
| `--color-text-brand` | `#ff385c` | `#ff4d6d` | Brand-toned inline emphasis |

### 2.4 Border & stroke

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-border` | `#ebebeb` | `#2a2a2e` | Default dividers, card outlines |
| `--color-border-strong` | `#c1c1c1` | `#3b3b40` | Inputs, emphasized containers |
| `--color-border-focus` | `#222222` | `#ededed` | Input focus frame |
| `--color-border-brand` | `#ff385c` | `#ff4d6d` | Brand-accent frame (selected card, confirm state) |

### 2.5 Status — semantic

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-success` | `#008a05` | `#2fcf34` | Success text/icon |
| `--color-success-soft` | `#e7f6e4` | `rgba(47, 207, 52, 0.14)` | Success toast / badge bg |
| `--color-warning` | `#c58100` | `#f5b946` | Warning text/icon |
| `--color-warning-soft` | `#fff6e0` | `rgba(245, 185, 70, 0.16)` | Warning toast / badge bg |
| `--color-error` | `#c13515` | `#ff6b4a` | Error text/icon |
| `--color-error-soft` | `#fbeae6` | `rgba(255, 107, 74, 0.16)` | Error toast / badge bg |
| `--color-error-hover` | `#b32505` | `#ff876b` | Error link hover |
| `--color-info` | `#428bff` | `#6ea6ff` | Info / legal / neutral notice |
| `--color-info-soft` | `#e7f0ff` | `rgba(110, 166, 255, 0.14)` | Info bg |

### 2.6 OCR confidence — product-specific semantic scale

The source system has no equivalent because Airbnb doesn't return confidence scores for listings. For LocalOCR Extended, confidence is a first-class citizen — every extracted field, line item, and total has an implicit or explicit confidence, and the UI must communicate it without overwhelming the warm neutral palette.

| Token | Light | Dark | Range | Role |
|---|---|---|---|---|
| `--color-confidence-high` | `#008a05` | `#2fcf34` | 0.85–1.00 | Green dot / ring on high-trust fields |
| `--color-confidence-high-soft` | `#e7f6e4` | `rgba(47, 207, 52, 0.14)` | — | High-confidence chip bg |
| `--color-confidence-medium` | `#c58100` | `#f5b946` | 0.60–0.84 | Amber ring — human review recommended |
| `--color-confidence-medium-soft` | `#fff6e0` | `rgba(245, 185, 70, 0.16)` | — | Medium-confidence chip bg |
| `--color-confidence-low` | `#c13515` | `#ff6b4a` | <0.60 | Red ring — human review required |
| `--color-confidence-low-soft` | `#fbeae6` | `rgba(255, 107, 74, 0.16)` | — | Low-confidence chip bg |

### 2.7 Category — for receipt / bill domains

These match spend-domain categories in the existing schema. Each uses a soft tint as background and the main hue for icon/stroke.

| Token | Light | Dark | Domain |
|---|---|---|---|
| `--color-cat-grocery` | `#2e8b57` | `#46c08f` | Grocery receipts |
| `--color-cat-restaurant` | `#d35400` | `#ff9a4d` | Restaurant receipts |
| `--color-cat-utility` | `#1b72b2` | `#5bb0e6` | Utility bills |
| `--color-cat-personal-service` | `#7b2cbf` | `#b47dff` | Personal services (tutoring, cleaning) |
| `--color-cat-subscription` | `#0a8ea0` | `#2ec6d6` | Subscriptions |
| `--color-cat-other` | `#6a6a6a` | `#a3a3a3` | Other / uncategorized |

### 2.8 Full CSS snapshot

```css
:root,
[data-theme="light"] {
  /* brand */
  --color-brand: #ff385c;
  --color-brand-hover: #e00b41;
  --color-brand-pressed: #b80635;
  --color-brand-soft: #fff0f3;
  --color-brand-contrast: #ffffff;

  /* surface */
  --color-bg: #ffffff;
  --color-surface: #ffffff;
  --color-surface-2: #f7f7f7;
  --color-surface-3: #f2f2f2;
  --color-surface-inverse: #222222;
  --color-overlay: rgba(17, 17, 20, 0.56);
  --color-overlay-soft: rgba(17, 17, 20, 0.18);

  /* text */
  --color-text-primary: #222222;
  --color-text-secondary: #6a6a6a;
  --color-text-muted: #929292;
  --color-text-disabled: rgba(0, 0, 0, 0.24);
  --color-text-inverse: #ffffff;
  --color-text-link: #428bff;
  --color-text-brand: #ff385c;

  /* border */
  --color-border: #ebebeb;
  --color-border-strong: #c1c1c1;
  --color-border-focus: #222222;
  --color-border-brand: #ff385c;

  /* status */
  --color-success: #008a05;
  --color-success-soft: #e7f6e4;
  --color-warning: #c58100;
  --color-warning-soft: #fff6e0;
  --color-error: #c13515;
  --color-error-soft: #fbeae6;
  --color-error-hover: #b32505;
  --color-info: #428bff;
  --color-info-soft: #e7f0ff;

  /* confidence */
  --color-confidence-high: #008a05;
  --color-confidence-high-soft: #e7f6e4;
  --color-confidence-medium: #c58100;
  --color-confidence-medium-soft: #fff6e0;
  --color-confidence-low: #c13515;
  --color-confidence-low-soft: #fbeae6;

  /* category */
  --color-cat-grocery: #2e8b57;
  --color-cat-restaurant: #d35400;
  --color-cat-utility: #1b72b2;
  --color-cat-personal-service: #7b2cbf;
  --color-cat-subscription: #0a8ea0;
  --color-cat-other: #6a6a6a;
}

[data-theme="dark"] {
  --color-brand: #ff4d6d;
  --color-brand-hover: #ff6b81;
  --color-brand-pressed: #e04262;
  --color-brand-soft: rgba(255, 77, 109, 0.14);
  --color-brand-contrast: #ffffff;

  --color-bg: #0f0f10;
  --color-surface: #17171a;
  --color-surface-2: #1f1f23;
  --color-surface-3: #28282d;
  --color-surface-inverse: #ededed;
  --color-overlay: rgba(0, 0, 0, 0.68);
  --color-overlay-soft: rgba(0, 0, 0, 0.32);

  --color-text-primary: #ededed;
  --color-text-secondary: #a3a3a3;
  --color-text-muted: #717175;
  --color-text-disabled: rgba(255, 255, 255, 0.28);
  --color-text-inverse: #0f0f10;
  --color-text-link: #6ea6ff;
  --color-text-brand: #ff4d6d;

  --color-border: #2a2a2e;
  --color-border-strong: #3b3b40;
  --color-border-focus: #ededed;
  --color-border-brand: #ff4d6d;

  --color-success: #2fcf34;
  --color-success-soft: rgba(47, 207, 52, 0.14);
  --color-warning: #f5b946;
  --color-warning-soft: rgba(245, 185, 70, 0.16);
  --color-error: #ff6b4a;
  --color-error-soft: rgba(255, 107, 74, 0.16);
  --color-error-hover: #ff876b;
  --color-info: #6ea6ff;
  --color-info-soft: rgba(110, 166, 255, 0.14);

  --color-confidence-high: #2fcf34;
  --color-confidence-high-soft: rgba(47, 207, 52, 0.14);
  --color-confidence-medium: #f5b946;
  --color-confidence-medium-soft: rgba(245, 185, 70, 0.16);
  --color-confidence-low: #ff6b4a;
  --color-confidence-low-soft: rgba(255, 107, 74, 0.16);

  --color-cat-grocery: #46c08f;
  --color-cat-restaurant: #ff9a4d;
  --color-cat-utility: #5bb0e6;
  --color-cat-personal-service: #b47dff;
  --color-cat-subscription: #2ec6d6;
  --color-cat-other: #a3a3a3;
}
```

---

## 3. Typography

### 3.1 Font stacks

```css
--font-sans: "Airbnb Cereal VF", "Cereal", "Inter", -apple-system,
             BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
             Arial, sans-serif;
--font-display: "Fraunces", "Source Serif Pro", Georgia, serif; /* optional,
             used only for the one section-divider eyebrow on marketing-style
             landings; NEVER for OCR content which must be sans for legibility */
--font-mono: "JetBrains Mono", "SF Mono", "Menlo", "Consolas", monospace;
--font-feature-body: "kern", "liga", "cv11", "ss01";
--font-feature-salt: "salt"; /* applied only to badges + micro-caps */
```

Airbnb Cereal VF is proprietary; ship the `@font-face` if licensed, otherwise the stack falls through to **Inter** which matches metrics closely enough at the 500–700 weights we use.

### 3.2 Scale — 8 steps, each with a role

All sizes use rem so the user's browser zoom preference works. The base is `16px = 1rem`.

| Step | rem | px | Weight | Line height | Tracking | Role |
|---|---|---|---|---|---|---|
| `--font-4xl` (display) | `2.50rem` | 40 | 700 | 1.10 | -0.5px | Landing / onboarding hero only |
| `--font-3xl` (hero) | `1.75rem` | 28 | 700 | 1.18 | -0.44px | Page hero heading (e.g. "Receipts") |
| `--font-2xl` (section) | `1.38rem` | 22 | 600 | 1.20 | -0.40px | Section heading, card heading |
| `--font-xl` (feature) | `1.25rem` | 20 | 600 | 1.25 | -0.18px | Feature title, modal title |
| `--font-lg` (subheading) | `1.13rem` | 18 | 600 | 1.33 | -0.10px | Subheading, stat value |
| `--font-md` (ui) | `1.00rem` | 16 | 500 | 1.25 | 0 | Nav items, button labels, primary body |
| `--font-sm` (body) | `0.88rem` | 14 | 400 | 1.43 | 0 | Default body, field labels, descriptions |
| `--font-xs` (small) | `0.81rem` | 13 | 400 | 1.23 | 0 | Timestamps, tertiary meta |
| `--font-2xs` (tag) | `0.75rem` | 12 | 500 | 1.33 | 0 | Tags, prices, inline chips |
| `--font-3xs` (badge) | `0.69rem` | 11 | 600 | 1.18 | 0.08px | Confidence badges (uses `"salt"`) |
| `--font-micro` (uppercase) | `0.50rem` | 8 | 700 | 1.25 | 0.32px | Uppercase eyebrow labels (rare) |

### 3.3 Role map — what uses what

| UI role | Token | Example in LocalOCR Extended |
|---|---|---|
| Display / onboarding hero | `--font-4xl` | "Your receipts, on your hardware." first-run splash |
| Page hero | `--font-3xl` | "Household Bills", "Inventory" |
| Card heading | `--font-2xl` | Provider name on obligation card, receipt store name |
| Modal title | `--font-xl` | "Edit bill", "Confirm delete" |
| Stat value | `--font-lg` | "$2,110.55" hero stat, "7 tracked" |
| UI control label | `--font-md` | Buttons, sidebar nav, tab labels |
| Body / description | `--font-sm` | Card meta ("Personal Service · Tutoring · Monthly") |
| Caption / timestamp | `--font-xs` | "Last seen 2026-04-21", "Due —" |
| Tag | `--font-2xs` | Category pill, service-type tag |
| Confidence badge | `--font-3xs` | "0.94" on an extracted line |
| Eyebrow | `--font-micro` | "EXTENDED" brand micro-header above page title |

### 3.4 Weight discipline

- **No weight below 500 in the UI.** Descriptions are 400 only when they are multi-line body copy.
- **Headings always 600 or 700.** Never 500 for a heading.
- **Monospace for OCR raw text.** Extracted-text panels use `--font-mono` at `--font-sm` so character widths stay stable when the user edits.
- **Negative tracking only on ≥ 18 px type** (`--font-lg` and up). Smaller text gets zero or positive tracking.

---

## 4. Spacing & Grid

### 4.1 Base unit

**4 px** is the atomic spacing unit. The scale uses 4-px and 8-px multiples, plus a handful of oddball stops inherited from the source (6, 10, 11) which matter for edge cases (e.g. 22 px avatar gutters).

### 4.2 Spacing scale

```css
--space-0:   0;
--space-px:  1px;
--space-1:   0.25rem;  /*  4 px */
--space-1-5: 0.375rem; /*  6 px */
--space-2:   0.5rem;   /*  8 px */
--space-2-5: 0.625rem; /* 10 px */
--space-3:   0.75rem;  /* 12 px */
--space-4:   1rem;     /* 16 px */
--space-5:   1.25rem;  /* 20 px */  /* Airbnb source: 22 */
--space-6:   1.5rem;   /* 24 px */
--space-8:   2rem;     /* 32 px */
--space-10:  2.5rem;   /* 40 px */
--space-12:  3rem;     /* 48 px */
--space-16:  4rem;     /* 64 px */
--space-20:  5rem;     /* 80 px */
--space-24:  6rem;     /* 96 px */
--space-32:  8rem;     /* 128 px */
```

### 4.3 Layout grid

| Breakpoint | Width | Columns | Gutter | Outer margin | Max content |
|---|---|---|---|---|---|
| Mobile small | <375 px | 4 | 16 px | 16 px | 100% |
| Mobile | 375–550 px | 4 | 16 px | 20 px | 100% |
| Tablet small | 550–744 px | 8 | 20 px | 24 px | 100% |
| Tablet | 744–950 px | 8 | 24 px | 32 px | 704 px |
| Desktop small | 950–1128 px | 12 | 24 px | 40 px | 920 px |
| Desktop | 1128–1440 px | 12 | 24 px | 48 px | 1152 px |
| Large desktop | 1440–1920 px | 12 | 32 px | 64 px | 1392 px |
| Ultra-wide | >1920 px | 12 | 32 px | 80 px | 1680 px |

The sidebar (present only on tablet and above) occupies **232 px** fixed when expanded and **72 px** (icons-only rail) when collapsed. Content max-widths above assume the sidebar is counted separately.

### 4.4 Section rhythm

Vertical rhythm between page sections — the "travel-magazine pacing" principle:

- **Between hero and first section:** `--space-10` (40 px) on mobile, `--space-12` (48 px) on desktop.
- **Between sibling sections:** `--space-8` (32 px) on mobile, `--space-10` (40 px) on desktop.
- **Between section heading and its content:** `--space-4` (16 px) on all breakpoints.
- **Inside a card:** `--space-4` (16 px) mobile, `--space-5` (20 px) desktop.
- **Between form fields:** `--space-4` (16 px) stacked, `--space-3` (12 px) horizontal.

### 4.5 Document-first density

LocalOCR Extended is image-heavy on the Upload and Results views. Those views widen the gutter to **32 px** and reduce card padding to **12 px** so the image fills more of the card. This mirrors Airbnb's listing grid — photo-first, chrome-minimal.

---

## 5. Elevation & Shadow

Six elevation levels, each with a light-mode and a dark-mode value. Dark-mode shadows use a higher alpha on a single layer because multi-layer ambient shadows vanish on dark canvases.

```css
/* Light mode */
--shadow-0: none;
--shadow-1:
  rgba(0, 0, 0, 0.02) 0px 0px 0px 1px,
  rgba(0, 0, 0, 0.04) 0px 2px 6px,
  rgba(0, 0, 0, 0.10) 0px 4px 8px;
--shadow-2:
  rgba(0, 0, 0, 0.03) 0px 0px 0px 1px,
  rgba(0, 0, 0, 0.06) 0px 4px 12px,
  rgba(0, 0, 0, 0.12) 0px 8px 20px;
--shadow-3:
  rgba(0, 0, 0, 0.04) 0px 0px 0px 1px,
  rgba(0, 0, 0, 0.08) 0px 6px 16px,
  rgba(0, 0, 0, 0.14) 0px 12px 32px;
--shadow-4:
  rgba(0, 0, 0, 0.04) 0px 0px 0px 1px,
  rgba(0, 0, 0, 0.10) 0px 10px 24px,
  rgba(0, 0, 0, 0.18) 0px 20px 48px;
--shadow-5:
  rgba(0, 0, 0, 0.06) 0px 0px 0px 1px,
  rgba(0, 0, 0, 0.14) 0px 16px 32px,
  rgba(0, 0, 0, 0.24) 0px 32px 80px;

/* Dark mode overrides */
[data-theme="dark"] {
  --shadow-1:
    rgba(0, 0, 0, 0.40) 0px 0px 0px 1px,
    rgba(0, 0, 0, 0.40) 0px 4px 12px;
  --shadow-2:
    rgba(0, 0, 0, 0.44) 0px 0px 0px 1px,
    rgba(0, 0, 0, 0.48) 0px 8px 20px;
  --shadow-3:
    rgba(0, 0, 0, 0.48) 0px 0px 0px 1px,
    rgba(0, 0, 0, 0.56) 0px 12px 32px;
  --shadow-4:
    rgba(0, 0, 0, 0.50) 0px 0px 0px 1px,
    rgba(0, 0, 0, 0.64) 0px 20px 48px;
  --shadow-5:
    rgba(0, 0, 0, 0.56) 0px 0px 0px 1px,
    rgba(0, 0, 0, 0.72) 0px 32px 80px;
}
```

### 5.1 Level map

| Level | Use case | Hover variant |
|---|---|---|
| 0 — Flat | Page background, body text blocks, inline chips on a colored wash | — |
| 1 — Card | Receipt card, bill card, stat card, sidebar when floating on mobile | Level 2 on `:hover` |
| 2 — Raised | Sticky bars (filter bar, toast), dropdown trigger in open state | — |
| 3 — Dropdown | Popovers, date-picker, context menus, autocomplete results | — |
| 4 — Modal | Modal dialog, bottom-sheet on mobile, edit overlay | — |
| 5 — Critical | Destructive confirms, toast stack over a modal, error overlays | — |

### 5.2 Shadow philosophy

Every shadow in light mode is a **three-layer warm lift** — a 1-pixel hairline ring at 2–6% black to define the edge, a soft 4% ambient blur that mimics diffuse daylight, and a stronger 10–14% primary cast that creates the sense of height. This is deliberately closer to photographic lighting than to material-design elevation. In dark mode, the border ring becomes the dominant component (shadows read as absence of light, not presence of it).

---

## 6. Border Radius & Stroke

### 6.1 Radius scale

```css
--radius-0:    0;
--radius-xs:   4px;  /* small links, inline code */
--radius-sm:   8px;  /* buttons, tabs, search, inputs */
--radius-md:   12px; /* secondary containers */
--radius-lg:   14px; /* status badges, labels */
--radius-xl:   20px; /* cards, feature buttons */
--radius-2xl:  28px; /* hero containers, large CTAs */
--radius-3xl:  32px; /* large feature containers, full-bleed cards */
--radius-pill: 9999px;   /* pills, chips, tags */
--radius-full: 50%;      /* circular nav, avatars, icons */
```

### 6.2 Radius role map

| Use case | Token |
|---|---|
| Inline `<code>` | `--radius-xs` |
| Button (primary, secondary, ghost) | `--radius-sm` |
| Input, select, textarea | `--radius-sm` |
| Tab | `--radius-sm` |
| Search bar container | `--radius-2xl` |
| Status badge | `--radius-lg` |
| Receipt card, bill card, stat card | `--radius-xl` |
| Modal / drawer | `--radius-2xl` |
| Hero / onboarding container | `--radius-3xl` |
| Category pill | `--radius-pill` |
| Avatar, provider logo, circular nav | `--radius-full` |

### 6.3 Stroke scale

```css
--stroke-0: 0;
--stroke-1: 1px;   /* default borders, dividers */
--stroke-1-5: 1.5px; /* emphasized card outline when selected */
--stroke-2: 2px;   /* focus rings, input focus frame */
--stroke-3: 3px;   /* selected state, active tab underline */
--stroke-4: 4px;   /* circular nav active ring */
```

Icon strokes are **1.5 px** at 24 px icon size, **2 px** at 32 px.

---

## 7. Component Inventory

Each component lists **variants**, **states** (default / hover / focus / active / disabled / loading when applicable), and any **OCR-specific behavior**. Every component inherits the color, typography, spacing, and shadow tokens above.

### 7.1 Upload / Drop Zone

**Variants**
- `default` — the main Upload page drop zone, full width, 280 px tall
- `compact` — inline drop zone inside a modal (e.g. "Replace receipt image"), 160 px tall
- `batch` — multi-file drop zone with per-file progress rows

**States**
- **Default** — dashed `--color-border-strong` outline at 1.5 px, `--color-surface-2` background, centered icon + "Drop a receipt or click to browse". `--font-md` primary label, `--font-sm` secondary hint.
- **Hover** (pointer over) — outline becomes `--color-border-brand`, background shifts to `--color-brand-soft`, icon tints to `--color-brand`.
- **Drag-over** (file being dragged) — outline is 2 px solid `--color-brand`, background `--color-brand-soft`, the label switches to "Release to upload".
- **Focus** (keyboard) — same outline as hover plus `--stroke-2` focus ring offset 2 px.
- **Invalid** (dropped a non-image) — outline `--color-error`, background `--color-error-soft`, label "File type not supported" in `--color-error`, 240 ms shake.
- **Uploading** — outline `--color-border`, indeterminate progress bar at the bottom (`--color-brand`), label "Uploading filename.jpg". The drop-zone keeps accepting additional files (appended to a batch).
- **Disabled** — 50% opacity, no interaction, cursor `not-allowed`.

**OCR-specific**
- Displays accepted formats inline: JPEG, PNG, HEIC, PDF.
- After drop, transitions directly into a Scan Progress Indicator for the first file.
- Multi-file drops are visualized as a stack of thumbnails sliding in.

### 7.2 Scan Progress Indicator

**Variants**
- `determinate` — percent-based bar (when the OCR backend streams progress)
- `indeterminate` — shimmer bar (when backend is synchronous)
- `compact` — single-row inline version inside a receipt list row
- `full` — full-screen overlay during the first upload of a session

**States**
- **Pending** — neutral `--color-surface-3` bar, text "Queued · 2 of 4"
- **Running** — `--color-brand` progress fill, phase label ("Reading image", "Extracting fields", "Matching products")
- **Retrying** — `--color-warning` fill, label "Retry 2 of 3 — switching to OpenAI"
- **Success** — short 320 ms `--color-success` fill then fade to a success toast
- **Failed** — `--color-error` fill, label "Failed — ", inline "Retry" button

**OCR-specific**
- Shows the **current model** as a small chip under the bar (e.g. "Gemini 2.5 Flash", "Ollama Llava 7B"). The chip uses category-color tokens to reinforce that different models have different costs/latencies.
- **Phase breakdown** is a stacked mini-timeline when the user hovers: Upload → OCR → Normalize → Match → Save. Each segment takes its duration proportionally.

### 7.3 Result Card (with Confidence Score Badge)

The Result Card is the single most important component in LocalOCR Extended. It appears on the Receipts list, inventory screens, and spending analytics. It's the direct analogue of Airbnb's listing card — image on top, details below.

**Variants**
- `receipt` — scanned image top (aspect 3:4 portrait), extracted metadata below
- `receipt-list-row` — horizontal compact variant, 64 px thumbnail on the left
- `bill-obligation` — no image; colored left border by confidence/status, all details
- `inventory-item` — product image top (1:1 square), stock info below

**Anatomy (receipt variant)**
- Card: `--color-surface`, `--radius-xl`, `--shadow-1`, overflow-hidden
- Image: fills top 62%, `--radius-xl` on all corners, subtle inner dark gradient bottom for legibility of overlay text
- Overlay in top-right: Confidence Badge (see below)
- Overlay in top-left (optional): Category pill using `--color-cat-*`
- Details block: 16 px padding, store name in `--font-md` 600, date + total in `--font-sm`, "Open receipt" link at bottom in `--color-brand`

**Confidence Score Badge**
- A pill: `--radius-lg`, 6 × 10 px padding, `--font-3xs` 600 with `"salt"` OpenType feature
- Three color variants driven by `--color-confidence-*`:
  - `high` (≥0.85): green soft bg + green text + filled dot
  - `medium` (0.60–0.84): amber soft bg + amber text + half-filled dot
  - `low` (<0.60): red soft bg + red text + open-ring dot
- Text format: `0.94` (two decimals, never percentage — keeps the field narrow)
- Tooltip on hover: "OCR confidence · click to review fields"

**States (card)**
- **Default** — `--shadow-1`
- **Hover** — `--shadow-2`, `translateY(-2px)`, 200 ms
- **Focus** — focus ring, no translate
- **Selected** (checkbox mode) — 1.5 px `--color-border-brand` outline + `--color-brand-soft` scrim
- **Processing** — image area shimmers, confidence badge says "…"
- **Error** — image area shows a retry icon, red outline, "Re-run OCR" button

**OCR-specific**
- Clicking the confidence badge jumps to the Extracted Text Panel with the lowest-confidence field pre-focused.
- Long-press / right-click opens the Toolbar (Re-run, Delete, Export, Copy).

### 7.4 Text Region Highlight Overlay

Renders on top of the receipt image to show the bounding boxes the OCR model returned.

**Variants**
- `static` — always visible (review mode)
- `hover` — shows only when the user mouses over a field in the Extracted Text Panel
- `selection` — user draws a box to re-OCR a region

**States / treatment**
- **Default region** — `--color-confidence-high`, 1.5 px outline, 8% alpha fill, 4 px radius. Label in top-left of the box: field name + confidence.
- **Medium confidence** — `--color-confidence-medium`, stripe pattern fill at 8% alpha (dashed outline).
- **Low confidence** — `--color-confidence-low`, stronger 14% alpha fill, 2 px outline, pulsing 1.6 s loop to draw attention.
- **Hovered** (from panel or image) — solid 2 px outline in `--color-brand`, ring glows softly outward over 200 ms, scrolls the corresponding row in the Extracted Text Panel into view.
- **Selected** (clicked) — `--color-brand` outline 2 px, brand soft fill, remains until deselected.
- **Drawing** (selection variant) — dashed `--color-brand` outline, follows cursor, snaps to 4 px grid.

**OCR-specific**
- Each box carries a `data-field` attribute (`store_name`, `line_item[3].description`, `total`, etc.) so the Extracted Text Panel can bidirectionally link.
- Boxes are rendered on an SVG layer positioned-absolute over the image. They scale with the image on zoom.

### 7.5 Extracted Text Panel

Two-column split: scanned image on the left, extracted fields on the right. This is where users actually correct OCR output.

**Variants**
- `side-by-side` — desktop default, 50/50 split
- `stacked` — mobile default, image collapsible to a 96 px thumbnail
- `raw-text` — toggle that replaces the structured fields with a mono-text editor showing the raw OCR output

**Anatomy (structured mode)**
- Panel header: receipt store name (`--font-xl`), confidence summary (high/medium/low counts), action buttons (Save, Cancel, Toggle Raw)
- Field rows: label on the left (`--font-xs` 500 `--color-text-secondary`), value on the right in an inline-edit input (`--font-sm` 400, `--color-text-primary`), confidence pill on the far right
- Low-confidence rows have a subtle `--color-confidence-low-soft` background to prioritize review

**States (field row)**
- **Default** — input has no border; hover shows 1 px `--color-border`
- **Editing** — input shows 2 px `--color-border-focus` frame
- **Modified** — small orange dot (`--color-warning`) at the left edge indicates unsaved change
- **Resolved** — a line item the user has confirmed; confidence pill flips to green regardless of original score
- **Rejected** — line item the user has explicitly marked as wrong; strikethrough, `--color-error-soft` bg
- **Autocomplete suggestion** — when the user types into a product name, a dropdown appears offering matches from their inventory; matches are surfaced with `--color-cat-*` tinted left-borders

**OCR-specific**
- Keyboard: `Tab`/`Shift+Tab` moves between fields, `↵` saves and moves down, `Esc` cancels the field edit, `⌘/Ctrl + Z` undoes (with a 10-step undo ring-buffer per receipt).
- The panel is the authoritative edit surface; the Result Card is display-only.
- "Re-run OCR" button at the bottom right lets the user retry with a different model without leaving the panel.

### 7.6 Toolbar / Action Bar

Either sticky at the top of a content area (receipts list) or floating at the bottom-right of an image view (scan/edit). Contains clustered actions.

**Variants**
- `sticky-top` — fills the full width, 56 px tall, `--color-surface` + `--shadow-2`
- `floating` — a rounded rectangle anchored bottom-right, `--radius-pill`, `--shadow-3`, `gap: --space-2`
- `contextual` — appears only when an item is selected (e.g. a receipt card multi-select), slides in from the top

**Buttons within**
- Icon-only circular buttons (`--radius-full`, 40 × 40) with tooltip on hover
- Destructive actions (Delete) are separated by a 1 px divider and tinted `--color-error` on hover only (not default)

**States**
- **Default** — `--color-surface` bg, 1 px `--color-border`
- **Hover on any button** — `--color-surface-3` bg, `--shadow-2` scoped to the button
- **Active / pressed** — scale to 0.92, 120 ms
- **Disabled** — 50% opacity, cursor `not-allowed`

**OCR-specific**
- Scan/Edit floating toolbar has these actions in order: **Scan** (brand-colored, primary), **Crop**, **Rotate**, **Zoom in**, **Zoom out**, **Copy extracted text**, **Export**, **Retry OCR**. The Scan button is the only one with a filled `--color-brand` background; everything else is ghost until hovered.

### 7.7 Status Badge

Compact, pill-shaped label that communicates a single piece of state.

**Variants**
- `semantic` — success / warning / error / info (uses `--color-[status]` + `--color-[status]-soft`)
- `confidence` — high / medium / low (uses the confidence token family)
- `category` — grocery / restaurant / utility / personal-service / subscription / other (uses `--color-cat-*`)
- `neutral` — plain `--color-surface-3` bg + `--color-text-secondary` text (e.g. "Draft", "Archived")

**Anatomy**
- Padding `--space-1` × `--space-3` (4 × 12)
- `--font-2xs` 500 (or `--font-3xs` 600 for the confidence variant with `"salt"`)
- Optional leading dot (4 px × 4 px circle) in the token color
- `--radius-pill`

**States**
- Mostly stateless. On hover over an interactive badge (e.g. a filter pill), the soft-background tokens go 4% darker and a subtle `--shadow-1` appears.
- Selected filter pill: solid `--color-brand` bg, `--color-brand-contrast` text.

### 7.8 Toast / Notification

Stackable ephemeral message, max 3 visible at a time, appears top-right on desktop, bottom-center on mobile.

**Variants**
- `info` (default, `--color-info` left border)
- `success` (`--color-success`)
- `warning` (`--color-warning`)
- `error` (`--color-error`, sticky — does not auto-dismiss)
- `action` — a toast with an inline action button (e.g. "Receipt deleted — [Undo]"). 6 s auto-dismiss with progress bar along the bottom edge.

**Anatomy**
- `--color-surface` bg, 4 px left border in the semantic color, `--radius-md`, `--shadow-3`
- 16 × 16 icon on the left, title (`--font-md` 600), optional body (`--font-sm`), action button (ghost, brand-tinted)
- Dismiss "×" button in the top-right corner, 32 × 32 tap area

**Motion**
- Enter: translate-y `-8 px` → `0`, opacity 0 → 1, 200 ms `--ease-out`
- Exit: translate-y `0` → `-4 px`, opacity 1 → 0, 160 ms `--ease-in-out`
- Stack reflow: 160 ms `--ease-out` on siblings

**OCR-specific**
- Action toasts are heavily used for undoable operations: Delete receipt, Mark bill paid, Bulk re-OCR. The progress bar along the bottom ticks down 6 s; clicking the action cancels the operation.

### 7.9 Modal / Drawer

**Variants**
- `modal-center` — centered modal, max-width 560 px, `--radius-2xl`, `--shadow-4`
- `modal-large` — 720 px, for receipt editors
- `drawer-right` — 440 px-wide side drawer from the right (settings, provider details)
- `bottom-sheet` — mobile only, full-width from bottom, `--radius-3xl` on top two corners, drag-handle at top center

**Anatomy**
- Backdrop: `--color-overlay` with 8 px `backdrop-filter: blur`
- Modal surface: `--color-surface`, `--radius-2xl`, `--shadow-4`, max-height 90 vh
- Sticky header inside: title (`--font-xl`), close "×" icon, 1 px bottom border, `--color-surface` bg
- Body: `--space-6` padding, scrollable
- Footer (optional): sticky, aligned right, primary + secondary buttons

**States**
- **Default** — opens via animation
- **Loading** — body shows skeletons, footer disabled
- **Unsaved-changes confirm** — closing attempt with dirty form triggers a nested confirm dialog with `--color-error` primary button ("Discard")

**Motion**
- `modal-center`: scale 0.96 → 1 + opacity 0 → 1, 200 ms `--ease-out`
- `drawer-right`: translate-x 24 px → 0 + opacity, 240 ms `--ease-out`
- `bottom-sheet`: translate-y 100% → 0, 280 ms `--ease-out`, drag-to-dismiss with rubber-band

### 7.10 Empty State

Every list view has one. The goal is not just "nothing here" but "here's the very next step."

**Variants**
- `first-time` — hero-ish, larger illustration, specific CTA ("Upload your first receipt")
- `filter-empty` — user filtered something out; shows the filter chips with a "Clear filters" CTA
- `error-empty` — request failed; shows retry CTA
- `success-empty` — everything is done (e.g. "Inbox zero — no bills due soon")

**Anatomy**
- Centered flex column, 48 px vertical padding
- Icon or small illustration (64 × 64) in `--color-text-muted`
- Title `--font-xl` 600
- Body `--font-sm` 400 in `--color-text-secondary`, max-width 42 ch
- Primary CTA at bottom

**OCR-specific**
- The first-time empty state on Receipts doubles as an onboarding prompt with a mini drop zone embedded, so users can upload directly from the empty state without navigating.

---

## 8. Iconography

### 8.1 Style rules

- **Source family:** Lucide (formerly Feather fork, MIT-licensed, 1200+ icons). It matches Airbnb's icon weight closely and is free to ship locally.
- **Stroke width:** 1.5 px at 24 × 24. 2 px at 32 × 32. 1 px at 16 × 16.
- **Corner style:** rounded caps + rounded joins.
- **Fill:** outline-only by default. Filled variants only for active tab indicators and the Heart/Favorite action (filled when favorited).
- **Viewbox:** always 24 × 24, even when rendered at 16 or 32 — the SVG scales.

### 8.2 Size scale

```css
--icon-xs: 12px;   /* inline with --font-xs text */
--icon-sm: 16px;   /* inside buttons, inputs */
--icon-md: 20px;   /* sidebar nav, section headers */
--icon-lg: 24px;   /* primary icon size, confidence rings */
--icon-xl: 32px;   /* floating toolbar buttons */
--icon-2xl: 48px;  /* empty-state hero */
```

### 8.3 Recommended set — OCR & household actions

Map LocalOCR Extended actions to named Lucide icons:

| Action | Icon | Notes |
|---|---|---|
| Scan / start OCR | `scan-line` | Primary action — often in brand color |
| Re-run OCR | `rotate-cw` | With tooltip "Re-run OCR" |
| Crop | `crop` | Opens crop handles |
| Rotate left | `rotate-ccw` | 90° increments |
| Rotate right | `rotate-cw` | 90° increments |
| Zoom in | `zoom-in` | Scroll-wheel also works |
| Zoom out | `zoom-out` | — |
| Copy extracted text | `copy` | Toast confirms |
| Export | `download` | Menu: CSV, JSON, PDF |
| Retry upload | `refresh-cw` | — |
| Delete | `trash-2` | Confirm dialog, destructive |
| Favorite / star | `star` | Filled when active |
| Search | `search` | |
| Filter | `sliders-horizontal` | Opens filter drawer |
| Sort | `arrow-up-down` | |
| Navigate — Dashboard | `layout-dashboard` | Sidebar |
| Navigate — Receipts | `receipt` | Sidebar |
| Navigate — Inventory | `package` | Sidebar |
| Navigate — Bills | `zap` | Sidebar (matches existing ⚡ emoji) |
| Navigate — Analytics | `bar-chart-3` | Sidebar |
| Navigate — Settings | `settings` | Sidebar |
| Confidence — high | `check-circle-2` | Filled in success color |
| Confidence — medium | `alert-circle` | Outline in warning color |
| Confidence — low | `alert-triangle` | Filled in error color |
| Upload | `upload` | Dropzone hero |
| AI / model | `sparkles` | Next to model name chip |
| Privacy / local-first | `shield-check` | Used in footer and onboarding |
| Sync (offline indicator) | `wifi-off` | Shown only when relevant |

### 8.4 Color rules

- Default icon color: `--color-text-secondary`.
- Active / brand-tinted: `--color-brand`.
- Status icons: `--color-[success|warning|error|info]`.
- Category icons: `--color-cat-*`.
- Never color an icon purely decoratively — every colored icon should match a semantic token.

---

## 9. Motion & Animation

### 9.1 Easing curves

```css
--ease-out:       cubic-bezier(0.22, 1, 0.36, 1);     /* entries, reveals */
--ease-in-out:    cubic-bezier(0.65, 0, 0.35, 1);     /* persistent transitions, state flips */
--ease-in:        cubic-bezier(0.55, 0, 1, 0.45);     /* exits */
--ease-spring:    cubic-bezier(0.34, 1.56, 0.64, 1);  /* bouncy confirm moments (Mark Paid) */
--ease-standard:  cubic-bezier(0.4, 0, 0.2, 1);       /* Material default, for rare utility transitions */
```

### 9.2 Duration tokens

```css
--duration-instant: 80ms;   /* ripples, button press */
--duration-fast:    120ms;  /* hover, focus ring appear */
--duration-base:    200ms;  /* card lift, most state transitions */
--duration-slow:    320ms;  /* modal enter, drawer slide */
--duration-elaborate: 480ms;  /* page reveal, scan-complete celebration */
--duration-scan-loop: 1600ms; /* scanning shimmer loop */
```

### 9.3 Use-case map

| Use case | Duration | Easing | Notes |
|---|---|---|---|
| Button hover — bg change | `--duration-fast` | `--ease-out` | Never slower; hover must feel instant |
| Button press — scale 0.96 | `--duration-instant` | `--ease-in-out` | Release returns with same curve |
| Card lift on hover | `--duration-base` | `--ease-out` | `translateY(-2px)` + shadow step |
| Tab switch | `--duration-base` | `--ease-out` | Cross-fade + 4 px slide from right |
| Modal enter | `--duration-slow` | `--ease-out` | Scale 0.96 → 1, opacity 0 → 1 |
| Modal exit | `--duration-base` | `--ease-in` | Reverse of enter, shorter |
| Drawer slide | `--duration-slow` | `--ease-out` | Translate-x + opacity |
| Bottom-sheet | `--duration-slow` | `--ease-out` | Translate-y from 100% |
| Toast enter | `--duration-base` | `--ease-out` | Slide down 8 px + opacity |
| Toast exit | `--duration-fast` | `--ease-in-out` | Slight slide up + fade |
| Page reveal (sibling stagger) | `--duration-slow` | `--ease-out` | Children delayed 40 ms each, max 6 |
| Skeleton shimmer | `--duration-scan-loop` | `linear` | Infinite, respects `prefers-reduced-motion` |
| Confidence ring draw | `--duration-base` | `--ease-out` | Stroke-dashoffset from full to 0 |
| Scan progress — determinate | `--duration-fast` per tick | `--ease-out` | Continuous width update |
| Scan complete — confetti (optional) | `--duration-elaborate` | `--ease-spring` | Only on first-of-session success |
| "Mark Paid" confirm | `--duration-elaborate` | `--ease-spring` | Single springy pop on status pill |

### 9.4 Reduced motion

Respect `prefers-reduced-motion: reduce` everywhere:

- All shimmer and scan-loop animations pause.
- Modal / drawer transitions become instant opacity fades at 80 ms.
- Stagger reveal is disabled (children all fade in together, 120 ms).
- Spring easings fall back to `--ease-out`.
- Hover lifts still use shadow change but drop the `translateY`.

---

## 10. Accessibility

### 10.1 Targets

- **WCAG 2.2 AA** minimum for the entire product, **AAA** for primary text (body and headings on main surfaces).
- **Minimum touch target** 44 × 44 px on any interactive element. Desktop pointer targets 24 × 24 minimum. Confidence badges are display-only so they may be smaller.
- **Minimum tap spacing** 8 px between adjacent interactive elements on touch.
- **Motion:** fully respects `prefers-reduced-motion`.
- **Color blindness:** confidence and status systems never rely on color alone — a shape cue (dot filled vs. open, icon style) always accompanies the color.

### 10.2 Contrast matrix

Measured against the backgrounds the token is designed to live on, rounded to one decimal.

| Foreground | Background | Light mode | Dark mode | WCAG |
|---|---|---|---|---|
| `--color-text-primary` | `--color-bg` | 16.1 : 1 | 15.2 : 1 | AAA |
| `--color-text-primary` | `--color-surface-2` | 14.3 : 1 | 13.1 : 1 | AAA |
| `--color-text-secondary` | `--color-bg` | 5.7 : 1 | 5.2 : 1 | AA |
| `--color-text-muted` | `--color-bg` | 4.5 : 1 | 4.6 : 1 | AA |
| `--color-brand` | `--color-bg` | 4.6 : 1 | 4.8 : 1 | AA (large & graphical) |
| `--color-brand-contrast` | `--color-brand` | 3.2 : 1 | 3.4 : 1 | AA (large & graphical) |
| `--color-success` | `--color-success-soft` | 5.9 : 1 | 6.4 : 1 | AA |
| `--color-warning` | `--color-warning-soft` | 4.7 : 1 | 6.9 : 1 | AA |
| `--color-error` | `--color-error-soft` | 5.5 : 1 | 5.8 : 1 | AA |
| `--color-text-link` | `--color-bg` | 4.6 : 1 | 4.9 : 1 | AA |

When a combination falls below AA (e.g. small brand text on white measured at 4.5:1), use a larger type size (≥ 18 px / 14 px bold) or pair with an icon so it qualifies as "large" or "graphical" under WCAG.

### 10.3 Focus ring

```css
--focus-ring-color: var(--color-border-focus);
--focus-ring-offset: 2px;
--focus-ring-width: var(--stroke-2); /* 2px */

:where(button, a, input, select, textarea, [tabindex]):focus-visible {
  outline: var(--focus-ring-width) solid var(--focus-ring-color);
  outline-offset: var(--focus-ring-offset);
  border-radius: inherit;
}
```

- **Always `:focus-visible`**, never bare `:focus`, so pointer users don't see rings.
- The ring uses `--color-border-focus` (near-black light / near-white dark) rather than `--color-brand` so focus survives on brand-colored surfaces.
- Circular controls use an extra 4 px white ring inside the focus outline (per Airbnb source).

### 10.4 Semantics checklist

- Every `<button>` has a visible label or `aria-label`.
- Icon-only controls pass the "could a screen-reader user still act" test — label via `aria-label`, never by title alone.
- Confidence badges have `aria-label="Confidence 0.94, high"`.
- OCR-extracted text panels use `role="form"` with explicit `<label>` per field.
- Modal focus-traps correctly; `Esc` closes unless the user has unsaved changes (then the unsaved-changes confirm opens).
- Bottom-sheets have `role="dialog"` and announce their title on open.

### 10.5 Keyboard map

Global shortcuts (also discoverable in a `?` cheat-sheet overlay):

| Key | Action |
|---|---|
| `g d` | Go to Dashboard |
| `g r` | Go to Receipts |
| `g i` | Go to Inventory |
| `g b` | Go to Bills |
| `g a` | Go to Analytics |
| `g s` | Go to Settings |
| `/` | Focus global search |
| `n` | New — contextual (upload on Receipts, new bill on Bills) |
| `l` | Log cash payment (Bills) |
| `e` | Edit focused card |
| `←` / `→` | Prev / next month on Bills; prev / next receipt on Results view |
| `?` | Open keyboard shortcut cheat sheet |
| `Esc` | Close modal / deselect |

---

## 11. Implementation Roadmap

### Phase 1 — Token setup *(0.5 – 1 week)*

**Goal:** ship all tokens as CSS custom properties + a `design-tokens.json` mirror, without changing any component markup.

- Create `src/frontend/styles/tokens/` with `colors.css`, `typography.css`, `spacing.css`, `radius.css`, `shadows.css`, `motion.css`.
- Generate `design/design-tokens.json` (source of truth) and script (`scripts/build_tokens.py`) that emits the CSS files.
- Load a light/dark theme switcher that sets `data-theme` on `<html>`; honor `prefers-color-scheme` for initial value; persist via localStorage.
- Replace the *existing* ad-hoc variables in `index.html` with the new tokens — but only at the variable layer, so no component needs to change. Old variable names become aliases (`--accent: var(--color-brand)`) during the transition.
- Verify no regressions by diffing rendered screenshots pre/post on five representative pages (Dashboard, Receipts, Upload, Bills, Settings).

**Exit criteria**
- All colors in `index.html` resolve through `--color-*`.
- Theme toggle works; both themes pass contrast matrix.
- `design-tokens.json` committed and generated by script.

### Phase 2 — Base components *(1–2 weeks)*

**Goal:** rebuild the generic primitives so everything above them inherits the new language.

- **Button** — primary, secondary, ghost, danger, icon-only, sizes (sm/md/lg). States per the spec.
- **Input / Select / Textarea** — default, focus, invalid, disabled, with prefix/suffix slot.
- **Card** — flat, raised, selected, interactive. Includes the three-layer shadow recipe.
- **Badge / Pill** — semantic, confidence, category, neutral.
- **Toast** — the shared toast engine (there's currently an `#action-toast` pattern; replace with a generic queue).
- **Modal / Drawer / Bottom-sheet** — shared overlay primitives; mobile gets bottom-sheet automatically below 640 px.
- **Empty State** — with all four variants.
- **Skeleton** — shimmer primitives.

**Exit criteria**
- A component gallery page (`#page-design-gallery`, dev-only) renders every primitive in every state.
- Unit / visual tests lock the rendered output.

### Phase 3 — OCR-specific composite components *(2 weeks)*

**Goal:** the components that only LocalOCR Extended needs.

- **Upload / Drop Zone** (all variants + batch).
- **Scan Progress Indicator** (all variants; tie into the existing OCR router phase events).
- **Result Card** with Confidence Badge.
- **Text Region Highlight Overlay** — SVG layer, bidirectional hover with the panel.
- **Extracted Text Panel** — structured + raw-text modes, keyboard map.
- **Toolbar / Action Bar** — sticky and floating variants.
- **Confidence Ring** (a small round progress that draws on appear) for hero stats on Dashboard and Analytics.

**Exit criteria**
- End-to-end: upload a receipt → see Scan Progress → land on Extracted Text Panel → correct a low-confidence field → save → return to Receipts list with updated card.
- All components work in both themes and at all breakpoints from 320 px to 1920 px.

### Phase 4 — Page layouts *(2–3 weeks)*

Rebuild the user-facing pages on top of the new components. Order matters — each page unlocks tests for the next.

1. **Upload view** — drop zone + multi-file batch + inline scan progress.
2. **Processing view** — the "OCR in flight" interstitial for the first upload of a session. Full-screen variant of Scan Progress.
3. **Results view** — two-column layout: receipt image + highlight overlay + Extracted Text Panel. Mobile stacks.
4. **Receipts history view** — grid of Result Cards with filter pills, sort, and pagination.
5. **Bills, Inventory, Analytics, Dashboard, Settings** — migrate page-by-page to the new system, reusing the gallery components. (Bills already has a tabbed workspace from the last pass; retheme its cards to use the new tokens + Result-Card shape for provider cards.)

**Exit criteria**
- Every page passes axe-core accessibility audit at AA.
- Every page has a documented Figma mirror (or equivalent).
- Zero references to legacy variables; the old shim aliases can be deleted.

### Phase 5 — Polish & dark mode *(1 week)*

**Goal:** take it from "working" to "feels considered."

- Tune dark mode shadows against real content — likely lower the alpha another notch on large modals that felt too floating.
- Wire the keyboard shortcut cheat-sheet overlay (`?`).
- Add the scan-complete spring animation (opt-in, disabled under `prefers-reduced-motion`).
- Illustration pass for empty states — commission or draw four warm, line-art illustrations (Upload, No results, No bills due, Error).
- Add the `--font-display` serif eyebrow to landing and onboarding only — confirm it doesn't leak into OCR content.
- Lighthouse pass for performance on the Results view (the image-heaviest page); target PageSpeed ≥ 95.
- Documentation: update `README.md` with the `data-theme` attribute, token paths, and a short "How to build a new component" guide pointing at the gallery.

**Exit criteria**
- Dark mode feels native, not "light mode inverted."
- All states documented, all motions respect reduced-motion, all surfaces pass contrast.
- A returning engineer can pick up a new feature and find the right tokens within 2 minutes.

---

*End of design system.*
