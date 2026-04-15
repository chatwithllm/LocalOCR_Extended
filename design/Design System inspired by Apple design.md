# Design System — LocalOCR Extended

> An Apple-inspired design language for a privacy-first, self-hosted household operations tool. Every principle is adapted from Apple's web design foundation and tuned for what LocalOCR Extended actually does: scan receipts, extract text, correct OCR mistakes, and make sense of months of household spend — on your own hardware. The interface retreats until the scanned document is the only thing the eye lands on.

---

## 1. Design Philosophy

LocalOCR Extended in the Apple language is **reverence for the artifact**. Where Apple puts the iPhone on a stage of pure black and steps back, we put the receipt on the same stage and do the same. The product isn't a phone — it's a scanned document with extracted text, a confidence score, and a running ledger of months of spend. The interface's job is to vanish around it.

Six foundational principles, adapted from the source system:

1. **Cinematic duality.** The app alternates between two canvas colors: **pure black (`#000000`)** for immersive, artifact-focused moments (Upload, Processing, Results view) and **light gray (`#f5f5f7`)** for informational moments (History, Bills, Settings). The color change is the visual equivalent of a scene cut. Never mid-gray, never gradients.
2. **A single chromatic accent.** **Apple Blue (`#0071e3`)** is the one interactive color. Used sparingly for primary CTAs (Scan, Save, Pay), focus rings, and inline links. Everything else is black, white, or a warm neutral. A page with ten blue elements means something is wrong.
3. **Typography as discipline.** **SF Pro Display** for anything ≥ 20 px, **SF Pro Text** for anything < 20 px. Negative letter-spacing at every size (-0.28 px at 56 px, -0.374 px at 17 px, -0.224 px at 14 px, -0.12 px at 12 px). Headline line-heights compress to 1.07; body opens to 1.47. No thin weights. No heavy weights. Weights 400 and 600 carry 90 % of the UI.
4. **Chrome retreats; the artifact advances.** No borders. No textures. No gradients. Shadow is either a single soft diffused cast (`3px 5px 30px / 0.22 alpha`) or nothing. The receipt photo, the extracted-text panel, and the confidence readout do all the visual talking.
5. **Glass for overlays, solid for surfaces.** The sticky navigation uses `rgba(0,0,0,0.8)` with `backdrop-filter: saturate(180%) blur(20px)` — a dark translucent pane floating above the scrolling content. Cards, modals, and buttons are solid; the only glass in the system is the nav and occasionally bottom sheets on mobile.
6. **Pill CTAs, rectangular everything else.** The signature "Learn more" / "Shop" link uses a **980 px border-radius** to produce a soft capsule. Buttons, cards, inputs, and modals stay in the 8–12 px range. The pill is reserved — it marks *action*, not ornament.

### What this philosophy rejects

- **Multi-color accent systems.** Success, warning, and error keep their semantic hues (green / amber / red) but they are not ornamental — they only surface when their state applies.
- **Heavy shadows or stacked depth layers.** One soft shadow or none. Everything else reads as cheap.
- **Wide letter-spacing.** SF Pro is engineered to run tight; opening the tracking makes it look foreign.
- **Thin (100–300) or ultra-bold (800–900) weights.** The scale is 400 → 600, occasionally 700.
- **Opaque navigation.** The glass blur is non-negotiable — without it, the "floating above content" feel is lost.
- **Textures, patterns, gradients.** Solid colors only. If a surface needs differentiation, change its hex value by a few percent, not its texture.

---

## 2. Color Tokens

All tokens use the `--color-*` namespace. Values are raw hex or rgba — no nested references — so they can be mechanically pulled into a `design-tokens.json` artifact.

### 2.1 Brand & accent

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-brand` | `#0071e3` | `#0a84ff` | Primary CTA background, focus ring, inline emphasis |
| `--color-brand-hover` | `#0077ed` | `#1f8fff` | CTA hover brighten |
| `--color-brand-pressed` | `#006edb` | `#0071e3` | CTA active / pressed |
| `--color-brand-soft` | `rgba(0, 113, 227, 0.10)` | `rgba(10, 132, 255, 0.16)` | Selected-chip wash, subtle brand tint |
| `--color-brand-contrast` | `#ffffff` | `#ffffff` | Text on brand background |
| `--color-link` | `#0066cc` | `#2997ff` | Inline text links (`0066cc` for light, `2997ff` for dark per Apple's dual-link system) |

### 2.2 Surface — the binary canvas

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-bg` | `#f5f5f7` | `#000000` | Default canvas |
| `--color-bg-inverse` | `#000000` | `#f5f5f7` | Contrasting hero canvas for cinematic scene cuts |
| `--color-surface` | `#ffffff` | `#1d1d1f` | Elevated card / input surface on default canvas |
| `--color-surface-2` | `#fafafc` | `#272729` | Hoverable card / search field |
| `--color-surface-3` | `#ededf2` | `#28282a` | Pressed / active surface |
| `--color-surface-4` | `#f5f5f7` | `#2a2a2d` | Deepest raised variant for modals on the inverse canvas |
| `--color-surface-inverse` | `#1d1d1f` | `#f5f5f7` | Primary Dark button, inverse card on inverse canvas |

### 2.3 Overlay

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-overlay` | `rgba(0, 0, 0, 0.48)` | `rgba(0, 0, 0, 0.72)` | Modal scrim |
| `--color-overlay-soft` | `rgba(210, 210, 215, 0.64)` | `rgba(58, 58, 60, 0.72)` | Image dimmer, media-control bg |
| `--color-glass-nav` | `rgba(0, 0, 0, 0.8)` | `rgba(0, 0, 0, 0.8)` | Sticky nav background behind the backdrop-filter |

### 2.4 Text

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-text-primary` | `#1d1d1f` | `#f5f5f7` | Body, headings |
| `--color-text-secondary` | `rgba(0, 0, 0, 0.8)` | `rgba(245, 245, 247, 0.86)` | Supporting text, nav items on the opposite canvas |
| `--color-text-muted` | `rgba(0, 0, 0, 0.56)` | `rgba(245, 245, 247, 0.56)` | Captions, timestamps, placeholder-adjacent |
| `--color-text-disabled` | `rgba(0, 0, 0, 0.48)` | `rgba(245, 245, 247, 0.40)` | Disabled form text, carousel controls |
| `--color-text-inverse` | `#ffffff` | `#1d1d1f` | Text on Primary Dark / `--color-bg-inverse` |

### 2.5 Border & stroke

Apple uses borders sparingly — primarily for focus rings and a handful of filter chips. Surface separation comes from background contrast, not strokes.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-border` | `rgba(0, 0, 0, 0.12)` | `rgba(255, 255, 255, 0.12)` | Default hairline when genuinely needed |
| `--color-border-strong` | `rgba(0, 0, 0, 0.22)` | `rgba(255, 255, 255, 0.22)` | Emphasized frame (rare) |
| `--color-border-brand` | `#0071e3` | `#0a84ff` | Brand-accent frame — "Learn more" pill, selected state |
| `--color-focus` | `#0071e3` | `#0a84ff` | Focus-visible outline (mandatory 2 px) |

### 2.6 Status — semantic

| Token | Light | Dark | Role |
|---|---|---|---|
| `--color-success` | `#00b74a` | `#30d158` | Success text/icon |
| `--color-success-soft` | `rgba(0, 183, 74, 0.12)` | `rgba(48, 209, 88, 0.22)` | Success toast / badge bg |
| `--color-warning` | `#ff9500` | `#ff9f0a` | Warning text/icon |
| `--color-warning-soft` | `rgba(255, 149, 0, 0.14)` | `rgba(255, 159, 10, 0.22)` | Warning toast / badge bg |
| `--color-error` | `#ff3b30` | `#ff453a` | Error text/icon |
| `--color-error-soft` | `rgba(255, 59, 48, 0.12)` | `rgba(255, 69, 58, 0.20)` | Error toast / badge bg |
| `--color-error-hover` | `#d70015` | `#ff6961` | Error link hover |
| `--color-info` | `#007aff` | `#2997ff` | Info / neutral notice |
| `--color-info-soft` | `rgba(0, 122, 255, 0.10)` | `rgba(41, 151, 255, 0.18)` | Info bg |

### 2.7 OCR confidence — product-specific

Apple's source system has no equivalent. LocalOCR Extended renders every extracted field with a confidence score; the UI must communicate the bucket at a glance without adding a fourth "accent color" to the palette.

| Token | Light | Dark | Range |
|---|---|---|---|
| `--color-confidence-high` | `#00b74a` | `#30d158` | ≥ 0.85 |
| `--color-confidence-medium` | `#ff9500` | `#ff9f0a` | 0.60–0.84 |
| `--color-confidence-low` | `#ff3b30` | `#ff453a` | < 0.60 |
| `--color-confidence-high-soft` | `rgba(0, 183, 74, 0.12)` | `rgba(48, 209, 88, 0.22)` | — |
| `--color-confidence-medium-soft` | `rgba(255, 149, 0, 0.14)` | `rgba(255, 159, 10, 0.22)` | — |
| `--color-confidence-low-soft` | `rgba(255, 59, 48, 0.12)` | `rgba(255, 69, 58, 0.20)` | — |

### 2.8 Category — receipt / spend domain

Desaturated category hues so they fit the black/white/blue discipline.

| Token | Light | Dark | Domain |
|---|---|---|---|
| `--color-cat-grocery` | `#34a36b` | `#4cc488` | Grocery |
| `--color-cat-restaurant` | `#d37c2b` | `#e09255` | Restaurant |
| `--color-cat-utility` | `#3a7cbd` | `#5b9ddc` | Utility bills |
| `--color-cat-personal-service` | `#8450b8` | `#a27ad0` | Personal services |
| `--color-cat-subscription` | `#2a8a95` | `#4fb3bd` | Subscriptions |
| `--color-cat-other` | `rgba(0, 0, 0, 0.56)` | `rgba(245, 245, 247, 0.56)` | Other / uncategorized |

### 2.9 Full CSS snapshot

```css
:root,
[data-theme="light"] {
  --color-brand: #0071e3;
  --color-brand-hover: #0077ed;
  --color-brand-pressed: #006edb;
  --color-brand-soft: rgba(0, 113, 227, 0.10);
  --color-brand-contrast: #ffffff;
  --color-link: #0066cc;

  --color-bg: #f5f5f7;
  --color-bg-inverse: #000000;
  --color-surface: #ffffff;
  --color-surface-2: #fafafc;
  --color-surface-3: #ededf2;
  --color-surface-4: #f5f5f7;
  --color-surface-inverse: #1d1d1f;

  --color-overlay: rgba(0, 0, 0, 0.48);
  --color-overlay-soft: rgba(210, 210, 215, 0.64);
  --color-glass-nav: rgba(0, 0, 0, 0.8);

  --color-text-primary: #1d1d1f;
  --color-text-secondary: rgba(0, 0, 0, 0.8);
  --color-text-muted: rgba(0, 0, 0, 0.56);
  --color-text-disabled: rgba(0, 0, 0, 0.48);
  --color-text-inverse: #ffffff;

  --color-border: rgba(0, 0, 0, 0.12);
  --color-border-strong: rgba(0, 0, 0, 0.22);
  --color-border-brand: #0071e3;
  --color-focus: #0071e3;

  --color-success: #00b74a;
  --color-success-soft: rgba(0, 183, 74, 0.12);
  --color-warning: #ff9500;
  --color-warning-soft: rgba(255, 149, 0, 0.14);
  --color-error: #ff3b30;
  --color-error-soft: rgba(255, 59, 48, 0.12);
  --color-error-hover: #d70015;
  --color-info: #007aff;
  --color-info-soft: rgba(0, 122, 255, 0.10);

  --color-confidence-high: #00b74a;
  --color-confidence-medium: #ff9500;
  --color-confidence-low: #ff3b30;
  --color-confidence-high-soft: rgba(0, 183, 74, 0.12);
  --color-confidence-medium-soft: rgba(255, 149, 0, 0.14);
  --color-confidence-low-soft: rgba(255, 59, 48, 0.12);

  --color-cat-grocery: #34a36b;
  --color-cat-restaurant: #d37c2b;
  --color-cat-utility: #3a7cbd;
  --color-cat-personal-service: #8450b8;
  --color-cat-subscription: #2a8a95;
  --color-cat-other: rgba(0, 0, 0, 0.56);
}

[data-theme="dark"] {
  --color-brand: #0a84ff;
  --color-brand-hover: #1f8fff;
  --color-brand-pressed: #0071e3;
  --color-brand-soft: rgba(10, 132, 255, 0.16);
  --color-brand-contrast: #ffffff;
  --color-link: #2997ff;

  --color-bg: #000000;
  --color-bg-inverse: #f5f5f7;
  --color-surface: #1d1d1f;
  --color-surface-2: #272729;
  --color-surface-3: #28282a;
  --color-surface-4: #2a2a2d;
  --color-surface-inverse: #f5f5f7;

  --color-overlay: rgba(0, 0, 0, 0.72);
  --color-overlay-soft: rgba(58, 58, 60, 0.72);
  --color-glass-nav: rgba(0, 0, 0, 0.8);

  --color-text-primary: #f5f5f7;
  --color-text-secondary: rgba(245, 245, 247, 0.86);
  --color-text-muted: rgba(245, 245, 247, 0.56);
  --color-text-disabled: rgba(245, 245, 247, 0.40);
  --color-text-inverse: #1d1d1f;

  --color-border: rgba(255, 255, 255, 0.12);
  --color-border-strong: rgba(255, 255, 255, 0.22);
  --color-border-brand: #0a84ff;
  --color-focus: #0a84ff;

  --color-success: #30d158;
  --color-success-soft: rgba(48, 209, 88, 0.22);
  --color-warning: #ff9f0a;
  --color-warning-soft: rgba(255, 159, 10, 0.22);
  --color-error: #ff453a;
  --color-error-soft: rgba(255, 69, 58, 0.20);
  --color-error-hover: #ff6961;
  --color-info: #2997ff;
  --color-info-soft: rgba(41, 151, 255, 0.18);

  --color-confidence-high: #30d158;
  --color-confidence-medium: #ff9f0a;
  --color-confidence-low: #ff453a;
  --color-confidence-high-soft: rgba(48, 209, 88, 0.22);
  --color-confidence-medium-soft: rgba(255, 159, 10, 0.22);
  --color-confidence-low-soft: rgba(255, 69, 58, 0.20);

  --color-cat-grocery: #4cc488;
  --color-cat-restaurant: #e09255;
  --color-cat-utility: #5b9ddc;
  --color-cat-personal-service: #a27ad0;
  --color-cat-subscription: #4fb3bd;
  --color-cat-other: rgba(245, 245, 247, 0.56);
}
```

---

## 3. Typography

### 3.1 Font stacks

```css
--font-display: "SF Pro Display", "SF Pro Icons", -apple-system,
                BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial,
                sans-serif;
--font-text:    "SF Pro Text", "SF Pro Icons", -apple-system,
                BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial,
                sans-serif;
--font-mono:    "SF Mono", "Menlo", "Consolas", monospace;
--font-feature-body: "kern", "liga";
```

SF Pro is Apple's proprietary family with optical sizing built in. **Use `--font-display` at ≥ 20 px and `--font-text` at < 20 px.** The `-apple-system` fallback resolves to the OS's system font automatically on Apple platforms, so users there get SF Pro natively without a download. Non-Apple systems fall back through Helvetica Neue → Arial.

### 3.2 Scale — 13 steps, each with a role

All sizes use rem so the user's browser zoom works. The base is `16px = 1rem`.

| Step | rem | px | Weight | Line height | Tracking | Role |
|---|---|---|---|---|---|---|
| `--font-hero` | `3.50rem` | 56 | 600 | 1.07 | -0.28px | Product / hero headline (Display) |
| `--font-4xl` | `2.50rem` | 40 | 600 | 1.10 | -0.40px | Section heading (Display) |
| `--font-3xl` | `2.13rem` | 34 | 600 | 1.18 | -0.374px | Page hero heading (Text) |
| `--font-2xl` | `1.75rem` | 28 | 400 | 1.14 | 0.196px | Card / tile heading (Display) |
| `--font-xl` | `1.50rem` | 24 | 300 | 1.50 | 0 | Sub-nav, subtitle light (Text) |
| `--font-lg` | `1.31rem` | 21 | 700 | 1.19 | 0.231px | Card title bold (Display) |
| `--font-lg-reg` | `1.31rem` | 21 | 400 | 1.19 | 0.231px | Card title regular (Display) |
| `--font-md` | `1.13rem` | 18 | 300 | 1.00 | 0 | Large button / light label (Text) |
| `--font-body` | `1.06rem` | 17 | 400 | 1.47 | -0.374px | Primary body (Text) |
| `--font-body-em` | `1.06rem` | 17 | 600 | 1.24 | -0.374px | Emphasized body / control label (Text) |
| `--font-sm` | `0.88rem` | 14 | 400 | 1.43 | -0.224px | Link, caption (Text) |
| `--font-sm-em` | `0.88rem` | 14 | 600 | 1.29 | -0.224px | Emphasized caption (Text) |
| `--font-xs` | `0.75rem` | 12 | 400 | 1.33 | -0.12px | Fine print, footnote (Text) |
| `--font-xs-em` | `0.75rem` | 12 | 600 | 1.33 | -0.12px | Bold fine print (Text) |
| `--font-nano` | `0.63rem` | 10 | 400 | 1.47 | -0.08px | Legal text, smallest size (Text) |

### 3.3 Role map — what uses what

| UI role | Token | Example in LocalOCR Extended |
|---|---|---|
| Product hero | `--font-hero` | "Your receipts, on your hardware." (onboarding splash) |
| Page hero | `--font-4xl` | "Receipts", "Household Bills" |
| Section heading | `--font-3xl` | "Recurring obligations" on the Bills page |
| Card heading | `--font-2xl` | Provider name on a result card, store name on a receipt card |
| Sub-nav / subtitle | `--font-xl` | "Select a receipt to inspect the extracted items and image." |
| Card title bold | `--font-lg` | Stat card values |
| Card title reg | `--font-lg-reg` | Secondary card headings |
| Large button | `--font-md` | Nothing today; available for special CTAs |
| Body | `--font-body` | Form field values, descriptions, default body |
| Body emphasis | `--font-body-em` | Control labels, primary CTA text |
| Link / caption | `--font-sm` | "Learn more →" inline links, meta lines |
| Caption emphasis | `--font-sm-em` | Badge labels, status pills |
| Footnote | `--font-xs` | Timestamps, "Last seen 2026-04-21" |
| Footnote emphasis | `--font-xs-em` | Confidence badges |
| Legal | `--font-nano` | Privacy note at the bottom of Upload, license footer |

### 3.4 Discipline rules

- **Optical sizing is non-negotiable.** Always use `--font-display` for ≥ 20 px, `--font-text` (and thus every `--font-*` token below `--font-md` in the table above) for < 20 px. Mixing produces a "wrong font" feeling at boundaries.
- **Negative tracking everywhere.** Even body text runs at -0.374 px, not 0. Buttons lose tracking because their line-height stretches wide.
- **Weight 400 and 600 carry the UI.** 300 for large decorative text only. 700 for rare bold card titles. 800–900 is forbidden.
- **Line-height compresses as size grows.** 1.07 at the hero, 1.10 at a section heading, 1.14 at a card title — opposite of most systems that open line-height at larger sizes. This produces Apple's signature compressed, billboard-like headlines.
- **Mono for OCR raw text.** `--font-mono` at `--font-body` size in the Extracted Text Panel's Raw Text mode so character widths stay stable while editing.

---

## 4. Spacing & Grid

### 4.1 Base unit

**8 px** is the spacing atom. A secondary 2-px sub-grid handles typographic and icon alignment where 8-px isn't fine enough (Apple's own spacing scale famously sprinkles 2, 3, 5, 6, 7, 9, 10, 11 px stops between the major 8-px multiples).

### 4.2 Spacing scale

```css
--space-0:   0;
--space-0-5: 0.125rem; /*  2 px */
--space-1:   0.25rem;  /*  4 px */
--space-1-5: 0.375rem; /*  6 px */
--space-2:   0.5rem;   /*  8 px */
--space-3:   0.75rem;  /* 12 px */
--space-4:   1rem;     /* 16 px */
--space-5:   1.25rem;  /* 20 px */
--space-6:   1.5rem;   /* 24 px */
--space-8:   2rem;     /* 32 px */
--space-10:  2.5rem;   /* 40 px */
--space-12:  3rem;     /* 48 px */
--space-16:  4rem;     /* 64 px */
--space-20:  5rem;     /* 80 px */
--space-24:  6rem;     /* 96 px */
--space-32:  8rem;     /* 128 px */
--space-40: 10rem;     /* 160 px */
--space-48: 12rem;     /* 192 px */
```

### 4.3 Layout grid

| Breakpoint | Width | Columns | Gutter | Outer margin | Max content |
|---|---|---|---|---|---|
| Small mobile | < 360 px | 4 | 12 px | 16 px | 100 % |
| Mobile | 360–480 px | 4 | 16 px | 20 px | 100 % |
| Mobile large | 480–640 px | 4 | 16 px | 24 px | 100 % |
| Tablet small | 640–834 px | 6 | 20 px | 32 px | 600 px |
| Tablet | 834–1024 px | 8 | 24 px | 40 px | 800 px |
| Desktop small | 1024–1070 px | 12 | 24 px | 48 px | 980 px |
| Desktop | 1070–1440 px | 12 | 24 px | 64 px | 980 px |
| Large desktop | > 1440 px | 12 | 32 px | auto | 1280 px |

**The signature 980 px maximum content width** is the same number that the pill CTA radius uses — it's Apple's recurring dimensional theme. Wider screens center the 980 px column with growing outer margins.

Sidebar (primary nav on desktop): **224 px** expanded, **72 px** collapsed rail. On mobile it becomes a full-screen overlay menu, same as Apple's own nav.

### 4.4 Section rhythm — "scene cuts"

Apple alternates background colors between sections, not just spacing. LocalOCR Extended does the same on hero/landing/onboarding and in dedicated moments (Processing view, Results view):

- **Sibling section spacing:** `--space-20` (80 px) on desktop, `--space-12` (48 px) on mobile.
- **Full-bleed immersive section height:** minimum `90vh` on desktop; natural height on mobile.
- **Card internal padding:** `--space-6` (24 px) standard, `--space-8` (32 px) on feature cards, `--space-4` (16 px) on compact list cards.
- **Form field stack:** `--space-4` (16 px) between fields.
- **Grid gap for result cards:** `--space-5` (20 px) desktop, `--space-4` (16 px) mobile.

### 4.5 Compression within, expansion between

Inside a text block: tight letter-spacing, tight line-heights, dense information. Between blocks: generous whitespace, often a full viewport height on hero sections. This tension is what makes Apple's layouts read as "cinematic" — the eye rests, then focuses, then rests.

---

## 5. Elevation & Shadow

### 5.1 Five levels

Apple's shadow system is famously restrained. The canonical card shadow is a *single* soft cast; everything beyond that comes from color and glass, not shadow stacking.

```css
--shadow-0:       none;
--shadow-1:       rgba(0, 0, 0, 0.22) 3px 5px 30px 0px;   /* The Apple card shadow. */
--shadow-2:       rgba(0, 0, 0, 0.14) 0px 6px 20px 0px,
                  rgba(0, 0, 0, 0.06) 0px 2px 4px 0px;    /* Hover lift */
--shadow-3:       rgba(0, 0, 0, 0.18) 0px 12px 32px 0px,
                  rgba(0, 0, 0, 0.08) 0px 4px 8px 0px;    /* Dropdown / popover */
--shadow-4:       rgba(0, 0, 0, 0.24) 0px 24px 48px 0px,
                  rgba(0, 0, 0, 0.10) 0px 8px 16px 0px;   /* Modal */
--shadow-5:       rgba(0, 0, 0, 0.32) 0px 40px 80px 0px,
                  rgba(0, 0, 0, 0.14) 0px 12px 24px 0px;  /* Critical / bottom-sheet */
```

### 5.2 Level → use map

| Level | Treatment | Use |
|---|---|---|
| 0 — Flat | No shadow | Page background, text blocks, navigation (uses glass, not shadow) |
| 1 — Card | `--shadow-1` (the Apple card) | Result cards, stat cards, receipt thumbnails, scan-progress card |
| 2 — Hover | `--shadow-2` | Hoverable card lift, button-with-shadow hover |
| 3 — Popover | `--shadow-3` | Dropdowns, date pickers, autocomplete, tooltips |
| 4 — Modal | `--shadow-4` | Modals, drawers, cheat-sheet overlay |
| 5 — Critical | `--shadow-5` | Destructive confirms, toast stack over a modal |

### 5.3 Glass (translucent depth)

The navigation's glass effect is not a shadow but a *vibrancy layer*:

```css
background-color: var(--color-glass-nav);       /* rgba(0, 0, 0, 0.8) */
backdrop-filter: saturate(180%) blur(20px);
-webkit-backdrop-filter: saturate(180%) blur(20px);
```

This is reserved for:
- **Sticky top nav** on every page
- **Toolbar — floating variant** when it anchors over content
- **Bottom sheet backdrop** on mobile modals

Glass shall not appear on cards, buttons, or panels. Solid surfaces for everything else.

### 5.4 Dark-mode shadow behavior

On the `#000000` canvas, shadows are mostly invisible — depth in dark mode comes from the `#1d1d1f → #272729 → #28282a → #2a2a2d` micro-tint ladder. The same shadow tokens apply (slightly increased alpha values under `[data-theme="dark"]` above) but their role is reduced; surface color does most of the heavy lifting.

---

## 6. Border Radius & Stroke

### 6.1 Radius scale

Apple's radius discipline is rigid: small containers in the 5–12 px range, rare 980 px pills on specific CTAs, and 50 % circles on media controls. Everything else feels "off-brand."

```css
--radius-0:    0;
--radius-xs:   5px;    /* small link tags, inline code */
--radius-sm:   8px;    /* buttons, product cards, standard containers */
--radius-md:   11px;   /* search / filter chips */
--radius-lg:   12px;   /* feature panels, lifestyle image containers */
--radius-xl:   16px;   /* modals on mobile, bottom sheets (top corners) */
--radius-pill: 980px;  /* "Learn more", "Shop", primary inline CTA — the signature Apple shape */
--radius-full: 50%;    /* media controls, avatars, circular icon wells */
```

### 6.2 Role map

| Use case | Token |
|---|---|
| Inline code, small tag | `--radius-xs` |
| Button (primary, secondary, ghost, danger, icon) | `--radius-sm` |
| Input, select, textarea | `--radius-sm` |
| Card (list item, compact) | `--radius-sm` |
| Receipt card, result card | `--radius-sm` |
| Search / filter pill-ish chip | `--radius-md` |
| Feature card, image container, lifestyle panel | `--radius-lg` |
| Modal (centered) | `--radius-lg` |
| Bottom sheet (top corners only) | `--radius-xl` |
| **"Learn more" / "Shop" pill CTA** | `--radius-pill` |
| Avatar, media control, circular icon button | `--radius-full` |

### 6.3 Stroke scale

Borders are rare. When used, they're hairlines.

```css
--stroke-0:  0;
--stroke-1:  1px;    /* default hairline (rare) */
--stroke-2:  2px;    /* focus ring (mandatory) */
--stroke-3:  3px;    /* filter / search chip outline */
```

Icon strokes: **1.5 px** at 24 px, **1.75 px** at 32 px. Apple's SF Symbols run thinner than most icon systems; match that weight with a Lucide + custom tweak if shipping Lucide as the substitute.

---

## 7. Component Inventory

Each component lists **variants**, **states**, and **OCR-specific behavior**. Every component inherits color, typography, spacing, and shadow tokens above.

### 7.1 Upload / Drop Zone

**Variants**
- `default` — full-width, 320 px tall on desktop, 240 px on mobile
- `compact` — inline "Replace receipt image" slot, 160 px
- `batch` — horizontal row rendered per file during multi-upload
- `hero` — full-viewport-height variant for the empty-state Upload page (cinematic scene)

**States**
- **Default** — `--color-surface`, `--shadow-0`, dashed `--stroke-1 rgba(0,0,0,0.22)` outline, centered icon + label + hint.
- **Hover** — outline thickens to `--stroke-2 --color-border-brand`, background tints to `--color-brand-soft`, icon + label turn `--color-brand`.
- **Drag-over** — outline `--stroke-2 --color-brand`, background `--color-brand-soft`, label switches to "Release to upload".
- **Focus** — same outline as hover plus `--stroke-2 --color-focus` at 2 px offset.
- **Invalid** — outline `--color-error`, background `--color-error-soft`, label in `--color-error`, 240 ms shake.
- **Uploading** — outline `--color-border`, inline determinate progress bar at the bottom (`--color-brand`), label `"Uploading filename.jpg"`.
- **Disabled** — opacity 0.5, cursor `not-allowed`.

**OCR-specific**
- Accepted formats (JPEG, PNG, HEIC, PDF) inline.
- After drop: transition directly into the Scan Progress Indicator in the same footprint.
- Multi-file drops: visualized as a stack of thumbnails falling in.

### 7.2 Scan Progress Indicator

**Variants**
- `determinate` — percent bar
- `indeterminate` — shimmer bar (when backend is synchronous)
- `compact` — single-row inline version inside a receipt row
- `full` — full-screen processing interstitial on top of `--color-bg-inverse` for the cinematic handoff

**States**
- **Pending** — `--color-surface-3` bar, label "Queued · 2 of 4".
- **Running** — `--color-brand` fill bar; phase label reads "Reading image", "Extracting fields", "Matching products".
- **Retrying** — `--color-warning` fill, label "Retry 2 of 3 — switching to OpenAI".
- **Success** — `--shadow-1` pulses once, `--color-success` fill, label fades to a success toast.
- **Failed** — `--color-error` fill, label `"Failed — <reason>"`, inline Retry button.

**OCR-specific**
- Current model chip beneath the bar (e.g. "Gemini 2.5 Flash", "Ollama Llava 7B") using `--color-cat-*` tints to reinforce different latency/cost profiles.
- Phase breakdown hover: Upload → OCR → Normalize → Match → Save. Segments sized proportionally.

### 7.3 Result Card (with Confidence Score Badge)

The single most important component. Apple's "product tile" is LocalOCR's "receipt card" — image on top, details below. The Confidence Badge sits in the top-right overlay, echoing Apple's "New" or "Pro" ribbons on product tiles.

**Variants**
- `receipt` — scanned image top (3:4 portrait), metadata below
- `receipt-list-row` — horizontal compact variant, 80 px thumbnail on the left
- `bill-obligation` — no image; colored left accent by confidence/status
- `inventory-item` — product image top (1:1 square), stock info below

**Anatomy (receipt variant)**
- Card: `--color-surface`, `--radius-sm`, `--shadow-1`, overflow-hidden.
- Image area: top 62 %, subtle inner dark gradient at the bottom for overlay legibility.
- Top-right overlay: **Confidence Badge** (see below).
- Top-left overlay (optional): Category pill using `--color-cat-*` + `--radius-pill`.
- Body: `--space-4` padding, store name in `--font-2xl`, date + total in `--font-sm`, "Open receipt →" link in `--color-link`.

**Confidence Score Badge**
- Pill: `--radius-pill`, `0 --space-2` padding, `--font-xs-em` with `font-variant-numeric: tabular-nums`.
- Three variants driven by `--color-confidence-*`:
  - `high` (≥ 0.85): success soft bg + success text + ✓ glyph
  - `medium` (0.60–0.84): warning soft bg + warning text + ! glyph
  - `low` (< 0.60): error soft bg + error text + ⚠ glyph
- Format: `0.94` (two decimals, never percentage).
- Tooltip: "OCR confidence · tap to review fields".

**States (card)**
- **Default** — `--shadow-1`
- **Hover** — `--shadow-2`, `translateY(-2px)`, 200 ms ease-out
- **Focus** — 2 px `--color-focus` outline, 2 px offset
- **Selected (checkbox mode)** — 2 px `--color-border-brand` outline + `--color-brand-soft` scrim
- **Processing** — image area shimmers, confidence badge reads "…"
- **Error** — image area shows a retry icon, red accent outline, "Re-run OCR" button

**OCR-specific**
- Clicking the confidence badge jumps to the Extracted Text Panel with the lowest-confidence field pre-focused.
- Long-press / right-click opens the toolbar (Re-run, Delete, Export, Copy).

### 7.4 Text Region Highlight Overlay

SVG overlay on top of the receipt image showing the OCR bounding boxes.

**Variants**
- `static` — always visible (review mode)
- `hover` — only when a matching field is hovered in the panel
- `selection` — user draws a box to re-OCR a region

**States**
- **Default region** — 1.5 px outline in `--color-confidence-high`, 8 % alpha fill, `--radius-xs`. Top-left caption: field name + confidence score.
- **Medium** — 1.5 px `--color-confidence-medium`, 10 % alpha fill.
- **Low** — 2 px `--color-confidence-low`, 14 % alpha fill, 1.6 s pulse loop (respects reduced-motion).
- **Hovered** — outline thickens to 2 px `--color-brand`, 200 ms soft glow outward, panel scrolls the paired row into view.
- **Selected** — `--color-brand` outline 2 px, brand soft fill, persists until deselected.
- **Drawing** — dashed `--color-brand` outline, snaps to 4 px grid.

**OCR-specific**
- Each box carries `data-field="store_name"`, `data-field="line_item[3].description"`, etc. Bidirectional link with the Extracted Text Panel.
- Scale with the image on zoom via SVG `viewBox`.

### 7.5 Extracted Text Panel

Two-column split: scanned image on the left, extracted fields on the right.

**Variants**
- `side-by-side` — desktop default, 50/50 split
- `stacked` — mobile default, image collapses to a 96 px thumbnail
- `raw-text` — toggle that replaces structured fields with a `--font-mono` textarea showing the raw OCR output

**Anatomy (structured mode)**
- Panel header: store name (`--font-2xl`), confidence summary, action buttons (Save, Cancel, Toggle Raw).
- Field rows: label left (`--font-sm` secondary), value middle (inline-edit input, `--font-body`), confidence pill right.
- Low-confidence rows get a subtle `--color-confidence-low-soft` background to prioritize review.

**States (field row)**
- **Default** — no border; hover reveals a 1 px `--color-border` hairline
- **Editing** — 2 px `--color-focus` frame
- **Modified** — 6 px `--color-warning` dot at the left edge indicating unsaved
- **Resolved** — confidence pill forced to green regardless of original score
- **Rejected** — strikethrough + `--color-error-soft` background
- **Autocomplete** — dropdown appears with inventory matches, each tinted by `--color-cat-*`

**OCR-specific**
- Keyboard map: `Tab` / `Shift+Tab` moves fields, `↵` saves + advances, `Esc` cancels, `⌘/Ctrl+Z` undoes (10-step ring buffer).
- "Re-run OCR" button in the header to retry with a different model without leaving the panel.

### 7.6 Toolbar / Action Bar

**Variants**
- `sticky-top` — fills width, 56 px tall, `--color-surface` + `--shadow-2`
- `floating` — glass rectangle anchored bottom-right, `--color-glass-nav` backdrop with blur, `--radius-pill`
- `contextual` — slides in from the top when items are selected

**Buttons within**
- Icon-only circular, `--radius-full`, 40 × 40.
- Destructive actions (Delete) separated by a 1 px divider, tinted `--color-error` on hover.

**States**
- **Default** — `--color-surface` bg, `--stroke-1 --color-border`
- **Hover (button)** — `--color-surface-3` bg, scoped `--shadow-2`
- **Active / pressed** — `scale(0.92)`, 120 ms
- **Disabled** — opacity 0.5, `cursor: not-allowed`

**OCR-specific**
- Floating variant on Scan / Edit view: **Scan** (brand-filled primary) · Crop · Rotate · Zoom in · Zoom out · Copy extracted text · Export · Retry OCR. The Scan button is the only one with a filled `--color-brand` background; everything else is ghost until hovered.

### 7.7 Status Badge

**Variants**
- `semantic` — success / warning / error / info
- `confidence` — high / medium / low
- `category` — grocery / restaurant / utility / personal-service / subscription / other
- `neutral` — `--color-surface-3` bg, `--color-text-secondary` text

**Anatomy**
- Padding `--space-1` × `--space-3`
- `--font-xs-em`
- Optional leading 4 × 4 dot (circular) in the token color
- `--radius-pill`

### 7.8 Toast / Notification

Stackable, max 3 visible, top-right on desktop, bottom-center on mobile.

**Variants**
- `info` (default `--color-info` left bar)
- `success` (`--color-success`)
- `warning` (`--color-warning`)
- `error` (`--color-error`, sticky — does not auto-dismiss)
- `action` — inline action button ("Receipt deleted — [Undo]"). 6 s auto-dismiss with a progress bar along the bottom.

**Anatomy**
- `--color-surface` bg, 4 px left border in the semantic color, `--radius-sm`, `--shadow-3`.
- 16 × 16 icon, title in `--font-body-em`, body in `--font-sm`, action button ghost-styled in `--color-link`.
- Dismiss "×" top-right, 32 × 32 tap area.

**Motion**
- Enter: translate-y `-8px → 0`, opacity `0 → 1`, 240 ms ease-out.
- Exit: translate-y `0 → -4px`, opacity fade, 180 ms.
- Stack reflow: 200 ms ease-out on siblings.

### 7.9 Modal / Drawer

**Variants**
- `modal-center` — centered, max-width 560 px, `--radius-lg`, `--shadow-4`
- `modal-large` — 720 px (receipt editors)
- `drawer-right` — 440 px side drawer
- `bottom-sheet` — mobile only, full-width from bottom, `--radius-xl` top corners, drag-handle

**Anatomy**
- Backdrop: `--color-overlay` with 8 px `backdrop-filter: blur`.
- Surface: `--color-surface`, `--radius-lg`, `--shadow-4`, max-height 90 vh.
- Sticky header inside: title in `--font-xl`, close "×" icon, 1 px bottom `--color-border`, `--color-surface` bg.
- Body: `--space-6` padding, scrollable.
- Footer (optional): sticky, right-aligned button cluster.

**Motion**
- `modal-center`: scale `0.96 → 1` + opacity `0 → 1`, 240 ms ease-out.
- `drawer-right`: translate-x `24px → 0` + opacity, 280 ms ease-out.
- `bottom-sheet`: translate-y `100% → 0`, 320 ms ease-out, drag-to-dismiss with rubber-band.

### 7.10 Empty State

**Variants**
- `first-time` — hero-ish, larger illustration, specific CTA ("Upload your first receipt")
- `filter-empty` — shows filter chips with a "Clear filters" CTA
- `error-empty` — retry CTA
- `success-empty` — "Inbox zero — no bills due soon"

**Anatomy**
- Centered flex column, 48 px vertical padding
- Icon / monochrome line illustration (64 × 64), `--color-text-muted`
- Title `--font-lg-reg`
- Body `--font-sm` in `--color-text-secondary`, max-width 42 ch
- Primary CTA: pill (`--radius-pill`) link or a standard 8-px-radius button

**OCR-specific**
- First-time empty state on Receipts doubles as onboarding with a mini drop zone embedded.

---

## 8. Iconography

### 8.1 Style rules

- **Source family:** SF Symbols when the user's platform supports them (native Apple devices). For the web build, use **Lucide** with a thinned stroke (1.5 px at 24 px) to approximate SF Symbols' feel.
- **Stroke width:** 1.5 px at 24 × 24; 1.75 px at 32 × 32; 1 px at 16 × 16.
- **Corner style:** rounded caps + rounded joins.
- **Fill:** outline by default. Filled variants only for active tab indicators and the Favorite heart.
- **Viewbox:** 24 × 24 baseline; scale via SVG.

### 8.2 Size scale

```css
--icon-xs: 12px;   /* inline with --font-xs */
--icon-sm: 16px;   /* inside buttons, inputs */
--icon-md: 20px;   /* sidebar nav, section headers */
--icon-lg: 24px;   /* primary icon size */
--icon-xl: 32px;   /* floating toolbar buttons */
--icon-2xl: 48px;  /* empty-state hero */
--icon-3xl: 64px;  /* empty-state line illustration */
```

### 8.3 Recommended set

| Action | SF Symbol (native) | Lucide (web) | Notes |
|---|---|---|---|
| Scan / start OCR | `doc.viewfinder` | `scan-line` | Primary — often brand-colored |
| Re-run OCR | `arrow.clockwise` | `rotate-cw` | Tooltip "Re-run OCR" |
| Crop | `crop` | `crop` | Opens crop handles |
| Rotate left | `rotate.left` | `rotate-ccw` | 90° increments |
| Rotate right | `rotate.right` | `rotate-cw` | 90° increments |
| Zoom in | `plus.magnifyingglass` | `zoom-in` | Scroll-wheel also works |
| Zoom out | `minus.magnifyingglass` | `zoom-out` | |
| Copy extracted text | `doc.on.doc` | `copy` | Toast confirms |
| Export | `square.and.arrow.up` | `share` / `download` | Menu: CSV, JSON, PDF |
| Retry upload | `arrow.counterclockwise` | `refresh-cw` | |
| Delete | `trash` | `trash-2` | Confirm dialog |
| Favorite / star | `star` / `star.fill` | `star` | Filled when active |
| Search | `magnifyingglass` | `search` | |
| Filter | `line.3.horizontal.decrease` | `sliders-horizontal` | Opens filter drawer |
| Sort | `arrow.up.arrow.down` | `arrow-up-down` | |
| Nav — Dashboard | `house` | `home` | Sidebar |
| Nav — Receipts | `doc.text` | `receipt` | Sidebar |
| Nav — Inventory | `shippingbox` | `package` | Sidebar |
| Nav — Bills | `bolt` | `zap` | Sidebar (matches existing ⚡ emoji) |
| Nav — Analytics | `chart.bar` | `bar-chart-3` | Sidebar |
| Nav — Settings | `gearshape` | `settings` | Sidebar |
| Confidence — high | `checkmark.circle.fill` | `check-circle-2` | Filled success |
| Confidence — medium | `exclamationmark.circle` | `alert-circle` | Outline warning |
| Confidence — low | `exclamationmark.triangle.fill` | `alert-triangle` | Filled error |
| Upload | `arrow.up.doc` | `upload` | Dropzone hero |
| AI / model | `sparkles` | `sparkles` | Next to model chip |
| Privacy / local-first | `lock.shield` | `shield-check` | Footer + onboarding |
| Sync offline | `wifi.slash` | `wifi-off` | Relevant-only indicator |

### 8.4 Color rules

- Default icon color: `--color-text-secondary`.
- Active / brand-tinted: `--color-brand`.
- Status icons: `--color-[success|warning|error|info]`.
- Category icons: `--color-cat-*`.
- No decorative-only colors. Every colored icon maps to a semantic token.

---

## 9. Motion & Animation

### 9.1 Easing curves

```css
--ease-out:       cubic-bezier(0.25, 1, 0.5, 1);        /* Apple standard entries */
--ease-in-out:    cubic-bezier(0.42, 0, 0.58, 1);       /* state flips */
--ease-in:        cubic-bezier(0.4, 0, 1, 1);           /* exits */
--ease-spring:    cubic-bezier(0.32, 0.72, 0, 1);       /* iOS-style spring */
--ease-standard:  cubic-bezier(0.25, 0.1, 0.25, 1);     /* rare utility transitions */
```

The named `--ease-spring` approximates iOS's default spring response. Use for confirm moments (Mark Paid, Scan Complete), never for continuous animation.

### 9.2 Duration tokens

```css
--duration-instant:   100ms;  /* press feedback */
--duration-fast:      150ms;  /* hover, focus */
--duration-base:      240ms;  /* default state transitions */
--duration-slow:      320ms;  /* modal enter, drawer slide */
--duration-elaborate: 480ms;  /* page reveal, scene cut */
--duration-scan-loop: 1600ms; /* scanning shimmer */
```

### 9.3 Use-case map

| Use case | Duration | Easing | Notes |
|---|---|---|---|
| Button hover | `--duration-fast` | `--ease-out` | background / border change |
| Button press | `--duration-instant` | `--ease-in-out` | `scale(0.98)`; release returns on same curve |
| Card lift on hover | `--duration-base` | `--ease-out` | `translateY(-2px)` + shadow step |
| Tab switch | `--duration-base` | `--ease-out` | cross-fade + 4 px slide |
| Modal enter | `--duration-slow` | `--ease-out` | scale + opacity |
| Modal exit | `--duration-base` | `--ease-in` | reverse of enter, shorter |
| Drawer slide | `--duration-slow` | `--ease-out` | translate-x + opacity |
| Bottom-sheet | `--duration-slow` | `--ease-out` | translate-y from 100% |
| Toast enter | `--duration-base` | `--ease-out` | slide + opacity |
| Toast exit | `--duration-fast` | `--ease-in-out` | slight slide up + fade |
| Page reveal (scene cut) | `--duration-elaborate` | `--ease-out` | fade + 8 px translate, children stagger 40 ms |
| Skeleton shimmer | `--duration-scan-loop` | `linear` | infinite, respects reduced-motion |
| Confidence ring draw | `--duration-base` | `--ease-out` | `stroke-dashoffset` |
| Scan progress tick | `--duration-fast` per tick | `--ease-out` | determinate width update |
| Scan complete | `--duration-elaborate` | `--ease-spring` | one-shot, only on first-of-session success |
| "Mark Paid" confirm | `--duration-elaborate` | `--ease-spring` | one-shot pop on status pill |

### 9.4 Reduced motion

Respect `prefers-reduced-motion: reduce` everywhere:

- Shimmer and scan-loop animations pause.
- Modal / drawer transitions become instant opacity fades at 100 ms.
- Stagger reveal disabled (children fade together at 120 ms).
- Spring easings fall back to `--ease-out`.
- Hover lifts keep the shadow change but drop the `translateY`.

---

## 10. Accessibility

### 10.1 Targets

- **WCAG 2.2 AA** minimum product-wide; **AAA** for primary body text.
- **Touch target minimum 44 × 44 px** on any interactive element. Desktop pointer targets 24 × 24 minimum. Confidence badges are display-only so they may be smaller.
- **Minimum tap spacing 8 px** between adjacent interactive elements on touch.
- **Motion:** respects `prefers-reduced-motion`.
- **Color blindness:** confidence and status never rely on color alone — a shape cue (✓ / ! / ⚠ glyph) or pattern (filled vs. outline) accompanies the color.

### 10.2 Contrast matrix

Measured against the background the token is designed to sit on, rounded to one decimal.

| Foreground | Background | Light | Dark | WCAG |
|---|---|---|---|---|
| `--color-text-primary` | `--color-bg` | 16.3 : 1 | 19.9 : 1 | AAA |
| `--color-text-primary` | `--color-surface` | 18.6 : 1 | 14.8 : 1 | AAA |
| `--color-text-secondary` | `--color-bg` | 11.3 : 1 | 14.5 : 1 | AAA |
| `--color-text-muted` | `--color-bg` | 7.6 : 1 | 7.5 : 1 | AAA |
| `--color-brand` | `--color-bg` | 4.7 : 1 | 5.0 : 1 | AA (large & graphical) |
| `--color-brand-contrast` | `--color-brand` | 4.6 : 1 | 4.4 : 1 | AA (large & graphical) |
| `--color-success` | `--color-success-soft` | 5.4 : 1 | 6.0 : 1 | AA |
| `--color-warning` | `--color-warning-soft` | 4.5 : 1 | 6.8 : 1 | AA |
| `--color-error` | `--color-error-soft` | 5.2 : 1 | 5.9 : 1 | AA |
| `--color-link` | `--color-bg` | 5.8 : 1 | 5.4 : 1 | AA |

Where a combination falls below AA for small text, size up to ≥ 18 px / 14 px bold (the WCAG "large text" threshold) or pair with an icon (graphical exception).

### 10.3 Focus ring

```css
--focus-ring-color:  var(--color-focus);
--focus-ring-width:  2px;
--focus-ring-offset: 2px;

:where(button, a, input, select, textarea, [tabindex]):focus-visible {
  outline: var(--focus-ring-width) solid var(--focus-ring-color);
  outline-offset: var(--focus-ring-offset);
  border-radius: inherit;
}
```

- **Always `:focus-visible`**, never bare `:focus`.
- Ring uses `--color-focus` (Apple Blue) — sits against both the light and dark canvas with adequate contrast.
- On pill CTAs (`--radius-pill`), the ring follows the capsule — `border-radius: inherit` handles this automatically.
- On filled brand buttons, thicken the ring to 3 px + 3 px offset so it survives the blue fill.

### 10.4 Semantics checklist

- Every `<button>` has a visible label or `aria-label`.
- Icon-only controls pass the screen-reader test: `aria-label` present.
- Confidence badges carry `aria-label="Confidence 0.94, high"`.
- OCR text panels use `role="form"` with explicit `<label>` per field.
- Modals focus-trap correctly; `Esc` closes (unless unsaved changes, then the discard-confirm opens).
- Bottom sheets have `role="dialog"` and announce their title on open.
- Nav glass preserves text contrast — never apply blur behind text that could then sit on a low-contrast image.

### 10.5 Keyboard shortcuts

Global, discoverable via a `?` cheat-sheet overlay:

| Key | Action |
|---|---|
| `g d` | Dashboard |
| `g r` | Receipts |
| `g i` | Inventory |
| `g u` | Upload |
| `g p` | Shopping list |
| `g b` | Bills |
| `g x` | Expenses |
| `g a` | Analytics |
| `g s` | Settings |
| `g g` | Design gallery |
| `/` | Focus global search |
| `n` | New (contextual) |
| `l` | Log cash (Bills) |
| `e` | Edit focused card |
| `←` / `→` | Prev / next (month on Bills, receipt on Results) |
| `?` | Open cheat sheet |
| `Esc` | Close modal |

---

## 11. Implementation Roadmap

### Phase 1 — Token setup *(0.5–1 week)*

- Create `design/design-tokens.json` as the source of truth (mirror §2 / §3 / §4 / §5 / §6 / §9 tables).
- Add `scripts/build_tokens.py` that reads the JSON and emits `src/frontend/styles/tokens.generated.css`.
- Load `data-theme` on `<html>` from `localStorage["theme"]` or `prefers-color-scheme`. **Default to light** — Apple's binary canvas treats light gray as the base and the app can alternate via `--color-bg-inverse`.
- Paste the `:root` + `[data-theme="dark"]` blocks from §2.9 into the app's global stylesheet, replacing the pre-tokenization declarations.
- Legacy variable names (`--accent`, `--bg`, `--text`, `--muted`, etc.) become aliases that resolve to the new tokens so downstream component CSS keeps working.
- **Warning:** the canvas changes globally (navy → `#f5f5f7` light / `#000000` dark) and the accent flips to Apple Blue. Expect a substantial visual shift everywhere.

**Exit criteria**
- Every color / shadow / radius / spacing / motion value resolves through a `--*` token.
- Theme toggle works; both themes pass the contrast matrix in §10.2.
- `design-tokens.json` committed and buildable by the script.

### Phase 2 — Base components *(1–2 weeks)*

Rebuild the generic primitives.

- **Button** — primary (blue filled), secondary (dark filled), ghost, danger, tonal, pill-link, icon-only. Sizes `sm` / `md` / `lg`. States default / hover / active (scale 0.98) / focus / disabled / loading.
- **Input / Select / Textarea** — `--color-surface` bg, 1 px `--color-border` frame, `--radius-sm`, focus gets `--color-focus` 2 px outline at 2 px offset. Invalid gets `--color-error` frame.
- **Card** — flat / raised (single `--shadow-1`) / selected (brand outline) / interactive (hover lift to `--shadow-2`).
- **Badge / Pill** — semantic / confidence / category / neutral.
- **Toast** — shared queue; left bar + surface + shadow-3.
- **Modal / Drawer / Bottom-sheet** — overlay primitives; mobile auto-swaps to bottom-sheet below 640 px.
- **Empty State** — four variants.
- **Skeleton** — shimmer primitives.

Ship a **Design Gallery** at `#page-design-gallery` (dev-only) rendering every primitive in every state.

### Phase 3 — OCR composite components *(2 weeks)*

- **Drop Zone** — dashed-outline basin, hover / dragover / invalid / uploading / disabled states, plus compact + batch-row variants.
- **Scan Progress** — determinate / indeterminate / compact / full-screen variants. Model chip. Phase breakdown.
- **Result Card** + **Confidence Score Badge** — image-first tile with confidence overlay.
- **Text Region Highlight Overlay** — SVG layer, bidirectional hover linking with the panel.
- **Extracted Text Panel** — structured + raw modes, inline-edit field rows with confidence pills, modified-dot treatment.
- **Toolbar / Action Bar** — sticky-top and floating (glass) variants.
- **Confidence Ring** — small SVG dial for dashboard stats and inline inline summaries.

**Exit criteria**
- End-to-end: upload a receipt → Scan Progress → Extracted Text Panel → correct a low-confidence field → save → return to Receipts list with the updated card.

### Phase 4 — Page layouts *(2–3 weeks)*

Rebuild user-facing pages.

1. **Onboarding / Upload view** — full-viewport hero with the drop zone and a pill CTA ("Scan receipt" in brand blue). Uses `--color-bg-inverse` (black) for cinematic contrast before the first upload.
2. **Processing view** — full-screen interstitial with the scan progress in `full` variant, on `--color-bg-inverse`.
3. **Results view** — side-by-side image + Extracted Text Panel; mobile stacks. Image well on `--color-surface` with `--shadow-1`.
4. **Receipts history view** — grid of Result Cards, filter pill strip at the top, pagination. Alternates black / light-gray section backgrounds when the user scrolls into dedicated filter groups or empty states.
5. **Bills / Inventory / Analytics / Dashboard / Settings** — migrate page-by-page to the primitive library; Bills adopts the tabbed + sticky-filter pattern.

**Exit criteria**
- Every page passes axe-core AA.
- Zero references to legacy tokens; alias shim can be retired.

### Phase 5 — Polish & dark mode *(1 week)*

- Tune dark-mode surface-ladder micro-tints against real content (the `#1d1d1f → #2a2a2d` stops may need ±1 % adjustments depending on which components end up adjacent).
- Wire the keyboard cheat-sheet overlay (`?`).
- Add the scan-complete and Mark-Paid spring animations (only the two confirm moments — keep them scarce).
- Monochrome line-illustrations for the four empty-state variants (SF Symbols-style line art, `--color-text-muted` stroke, consistent line weight).
- Lighthouse pass on Results view; target ≥ 95 performance + ≥ 95 accessibility.
- README updated with `design/Design System inspired by Apple design.md`, the token generator, the cheat sheet, and the "writing a new component" rule of thumb.

**Exit criteria**
- Dark mode feels native, not "light inverted."
- All states documented, all motions respect reduced-motion, all surfaces contrast-verified.
- Engineers can pick up a new feature and find the right tokens within 2 minutes.

---

*End of design system.*
