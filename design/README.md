# LocalOCR Design System

Apple-inspired design language for **LocalOCR Extended** — a privacy-first, self-hosted OCR and household-expense platform. Cinematic duality (black / light-gray canvases), a single chromatic accent (Apple Blue `#0071e3`), SF Pro optical-sizing typography, and purpose-built tokens for OCR confidence and spend categories.

## Start here

- **`colors_and_type.css`** — authoritative CSS custom properties. Import from every file.
- **`design-tokens.json`** — machine-readable mirror.
- **`Design System inspired by Apple.md`** — the full written spec (philosophy, components, responsive, do/don't).
- **`SKILL.md`** — working rules distilled for fast application.

## Browse locally

The Flask app serves this bundle at `/design/...`. Defaults to the UI kit.

- `http://<host>:8090/design/` → `preview/ui-kit-localocr.html` (three product surfaces)
- `http://<host>:8090/design/preview/components-buttons.html` — any preview card
- `http://<host>:8090/design/marketing/index.html` — marketing hub (Plaid + money-lifecycle animation)
- `http://<host>:8090/design/marketing/landing-a-technical.html` / `landing-b-household.html` / `landing-c-privacy.html` — three hero variants

## Preview index

Each card is a focused 700px specimen that imports the live tokens.

### Colors
- `preview/colors-brand-canvas.html` — brand + canvas scale
- `preview/colors-text-border.html` — text hierarchy + borders
- `preview/colors-semantic.html` — success / warning / error / info
- `preview/colors-confidence.html` — OCR confidence tri-scale
- `preview/colors-category.html` — spend-domain category swatches

### Type
- `preview/type-display.html` — SF Pro Display scale (hero → lg)
- `preview/type-text.html` — SF Pro Text scale (xl → nano)
- `preview/type-mono.html` — SF Mono for raw OCR

### Foundations
- `preview/spacing-scale.html` — 8px base scale
- `preview/radius-scale.html` — 0 → 980px pill
- `preview/shadow-elevation.html` — one soft cast or nothing
- `preview/motion.html` — easings & durations
- `preview/iconography.html` — 1.5px-stroke Lucide family

### Components
- `preview/components-buttons.html` — primary, dark, pill-link, danger
- `preview/components-inputs.html` — text, select, search, error
- `preview/components-badges.html` — semantic / confidence / category
- `preview/components-toast.html` — info, success, warning, error
- `preview/components-dropzone.html` — default / hover / uploading / invalid
- `preview/components-scan-progress.html` — running / retry / success / failed
- `preview/components-receipt-card.html` — receipt tile with confidence

### Extended UI kit
- `preview/ui-kit-localocr.html` — three product surfaces: **Dashboard · Review · Upload**

## The rules, condensed

1. Binary canvas: `#000` for artifact moments, `#f5f5f7` for informational.
2. One accent: `#0071e3` for interactive elements only.
3. Optical-sizing type: Display ≥ 20px, Text < 20px, negative tracking at every size.
4. Confidence triad: `✓ ≥0.85` green, `! 0.60–0.84` orange, `⚠ <0.60` red — **never color alone**.
5. Pill 980px radius for "Learn more" links; 8px radius for CTAs; circle for media controls.
6. One shadow or none (`rgba(0,0,0,0.22) 3px 5px 30px`).
7. No decorative gradients, textures, or borders.
