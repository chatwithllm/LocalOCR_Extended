# LocalOCR Landing Page Rebrand — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **HARNESS:** This build runs gated under web-app-builder. Every task: read `agent-rules.md` first, pass adapted done-gate (below), update `landing_build_status.json` after the task.

**Goal:** Replace the marketing landing page at `design/marketing/index.html` (served by Flask at `/`) with a completely new design that shares nothing visually with the current editorial light-minimal style.

**Architecture:** One self-contained static HTML file (embedded CSS + small vanilla JS), matching the existing variant-file pattern in `design/marketing/`. Fonts self-hosted as woff2 under `design/marketing/fonts/` (on-brand: "0 trackers" means no Google Fonts CDN). No framework, no build step.

**Tech Stack:** HTML5, embedded CSS (custom properties), vanilla JS (IntersectionObserver reveals, marquee), self-hosted woff2 fonts.

---

## Design Contract — "RECEIPT-PUNK NIGHT MARKET"

The current design is: white paper background, near-black ink, single Apple-blue accent, Fraunces italic serif display + Manrope body, flat, no shadows, refined editorial spec-sheet. **The new design must be its opposite on every axis:**

| Axis | Current (FORBIDDEN) | New (REQUIRED) |
|---|---|---|
| Theme | light, white `#fff` | dark warm espresso `#171210` |
| Accent | one cool blue `#0071e3` | hot tangerine `#ff5c1f` + acid lime `#c8f135`, cream text `#f4ead8` |
| Shape | flat, hairline rules | chunky 3px borders, HARD offset shadows (`8px 8px 0`), zero blur |
| Type | Fraunces serif italic + Manrope | Archivo Black (display, uppercase, huge) + Archivo (body) + Space Mono (receipt/labels) |
| Layout | symmetric editorial columns | rotated stickers, overlapping blocks, diagonal marquee tickers, grid-breaking |
| Motion | subtle fade/scan | thermal-receipt print animation, scrolling tickers, stamp-slam reveals |
| Voice | calm spec-sheet | loud manifesto ("THE CLOUD IS JUST SOMEONE ELSE'S COMPUTER.") |

### Design tokens (exact)

```css
:root {
  --bg: #171210;          /* espresso */
  --bg-2: #211a15;        /* panel */
  --ink: #f4ead8;         /* cream text */
  --muted: #a8957c;
  --hot: #ff5c1f;         /* tangerine */
  --acid: #c8f135;        /* lime */
  --paper: #f7f1e3;       /* receipt paper (light blocks on dark) */
  --paper-ink: #1d1813;   /* text on paper */
  --border: #f4ead8;      /* chunky borders use cream */
  --shadow: 8px 8px 0 rgba(0,0,0,.55);
  --shadow-hot: 8px 8px 0 #ff5c1f;
}
```

### Fonts (self-hosted, Task 2)

- **Archivo Black** 400 — display. **Archivo** 400/600 — body. **Space Mono** 400/700 — mono.
- Files live in `design/marketing/fonts/*.woff2`, declared via `@font-face` in the page `<style>` with `font-display: swap` and full local fallback stacks (`Impact/Arial Black` for display, `Helvetica` body, `Menlo` mono) so the page still reads if fonts 404.

### Copy deck (final copy — use verbatim)

- Topbar brand: `LOCALOCR` in a tilted cream box; right side: `GitHub`, `Docs`, `Open the app →` (links: `https://github.com/chatwithllm/LocalOCR_Extended`, `/app`)
- Kicker badges: `SELF-HOSTED` `MIT LICENSE` `0 TRACKERS` `RUNS ON YOUR BOX`
- H1 (stacked, each line its own block, middle line on paper bg, slight alternating rotation):
  `YOUR RECEIPTS.` / `YOUR HARDWARE.` / `NOBODY ELSE'S BUSINESS.`
- Lede: "LocalOCR eats crumpled receipts and spits out inventory, budgets, bills, and price history — on a box you own. No SaaS. No subscription. No phone-home."
- CTA primary (mono, paper block, hard shadow): `$ docker compose up -d` · CTA secondary (outline): `See how it works ↓`
- Hero visual: thermal receipt printing out of a dark slot — lines appear one by one (CSS animation), zigzag torn bottom edge (clip-path), receipt lists real-ish items then `TOTAL DATA SENT TO SAAS ... $0.00` and barcode strip.
- Marquee ticker (between sections, diagonal −2°): `OAT MILK $4.29 ✓ · PAPER TOWELS $11.99 ✓ · COFFEE BEANS $14.50 ✓ · PARSED ON YOUR HARDWARE · NO CLOUD WAS CONSULTED ·` (repeats)
- 3 steps (numbered stamps): `01 SNAP IT` — "JPG, PNG, HEIC, PDF. Phone, Telegram bot, or drag-and-drop." / `02 PARSE IT` — "Four OCR models in a fallback chain. Cheapest one that clears 95% confidence wins." / `03 OWN IT` — "Line items land in SQLite on your disk. Inventory, budgets, and price history update themselves."
- Manifesto section (huge type on paper block): `THE CLOUD IS JUST SOMEONE ELSE'S COMPUTER.` + paragraph: "Every receipt is a record of how you live. LocalOCR keeps that record where it belongs — on hardware you control. Open source, MIT licensed, audit every line."
- Feature sticker-grid (8 tilted cards): Inventory autopilot / Shopping list that groups by store / Bills & forecasting / Price history & store wars / Household ledger / Telegram bot intake / Home Assistant + MQTT / QR device pairing. One-line description each.
- OCR pipeline lineup (4 fighter cards): `GEMINI 2.5 FLASH — fast & cheap` / `GPT-4-MINI — reliable backup` / `OLLAMA LLAVA — 100% LOCAL` (acid `LOCAL` badge) / `CLAUDE VISION — heavy fallback`. Caption: "You pick the roster. Ollama means receipts never leave your LAN."
- Price block: giant `$0/MO` `FOREVER` + line "Self-hosted. You pay your own electricity and the OCR pennies you choose to spend."
- Install section styled as a receipt (paper, mono):
  `git clone https://github.com/chatwithllm/LocalOCR_Extended.git` / `cp .env.example .env  # add your keys` / `docker compose up -d --build` then `TOTAL ... $0.00` / `THANK YOU FOR OWNING YOUR DATA` + barcode.
- FAQ (4 items, chunky `<details>`): Does it work offline? (Yes with Ollama) / What hardware? (Anything that runs Docker — ARM64 + x86_64, a Pi or a NAS) / Is my data really mine? (SQLite file on your disk; backups are local tarballs) / What does OCR cost? (Your choice; Gemini pennies, Ollama free)
- Footer: brand + "Scan today. Own forever." + links (GitHub, Docs, `/app`) + `MIT · no trackers · no analytics · view source, literally`
- `<title>`: `LocalOCR — Your receipts. Your hardware. Nobody else's business.` + meta description + OG tags (no external image required; `og:title`/`og:description`).

### Behavior

- Scroll-reveal: sections slide/stamp in via IntersectionObserver adding `.in` class; **must respect `prefers-reduced-motion: reduce`** (no transforms/animations).
- Marquee: pure CSS `@keyframes` translateX loop, duplicated content for seamlessness; paused under reduced-motion.
- Receipt print: CSS-only staggered `animation-delay` line reveals.
- No console errors. No external requests except self-hosted assets (check Network: only same-origin).
- Responsive: 960px and 600px breakpoints; stacked H1 scales via `clamp()`; sticker grid → 2col → 1col; tickers stay.

---

## Adapted done-gate (static marketing page)

- [ ] `[client]` Page served over HTTP renders all sections (screenshot desktop 1440w + mobile 390w, eyeballed by agent).
- [ ] `[client]` Zero browser console errors during load + scroll.
- [ ] `[client]` Every link href verified to resolve (GitHub URL well-formed, `/app` route exists in Flask, in-page anchors exist).
- [ ] `[client]` No external-origin requests (fonts self-hosted) — grep HTML for `http` in `src=`/`href=` of assets.
- [ ] `[client]` `prefers-reduced-motion` honored (media query present and disabling animation/transform).
- [ ] `[all]` Old design preserved (variant file or git history confirmed) before overwrite.
- [ ] `[all]` Commit + `landing_build_status.json` updated.

---

### Task 1: Pre-flight — Flask serving reality + variant preservation

**Files:** none modified (read-only recon)

- [ ] **Step 1: Find how Flask serves `/` and marketing assets** (agent-rules RULE 1 — never assume routes)

```bash
grep -rnE "design/marketing|send_from_directory|@app.route\('/'\)|landing" src/backend/*.py | head -30
```

Record: which function serves `/`, whether sibling files (e.g. `_site.css`, `fonts/*.woff2`) in `design/marketing/` are reachable, and at what URL path. If fonts subdirectory would NOT be served, the serving route must be confirmed to handle subpaths — if not, fonts get inlined as base64 in Task 2 instead.

- [ ] **Step 2: Check old index.html is preserved in a variant**

```bash
cmp -s design/marketing/index.html design/marketing/landing-d-meridian.html && echo IDENTICAL || echo DIFFERS
```

If DIFFERS: `cp design/marketing/index.html design/marketing/landing-e-prior.html` and commit that copy first.

- [ ] **Step 3: Update `landing_build_status.json`** (task done, findings in log)

### Task 2: Self-host fonts

**Files:**
- Create: `design/marketing/fonts/archivo-black-400.woff2`, `archivo-400.woff2`, `archivo-600.woff2`, `space-mono-400.woff2`, `space-mono-700.woff2`

- [ ] **Step 1: Download woff2 from Google Fonts API** (one-time fetch at build time; the shipped page makes zero external calls)

```bash
mkdir -p design/marketing/fonts && cd design/marketing/fonts
UA="Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36"
for spec in "Archivo+Black:400:archivo-black-400" "Archivo:400:archivo-400" "Archivo:600:archivo-600" "Space+Mono:400:space-mono-400" "Space+Mono:700:space-mono-700"; do
  fam="${spec%%:*}"; rest="${spec#*:}"; wght="${rest%%:*}"; out="${rest#*:}"
  url=$(curl -s -A "$UA" "https://fonts.googleapis.com/css2?family=${fam}:wght@${wght}&display=swap" | grep -o 'https://[^)]*\.woff2' | head -1)
  curl -s -o "${out}.woff2" "$url" && echo "OK ${out}"
done
ls -la
```

Expected: 5 woff2 files, each >10KB. (Archivo Black ignores the wght axis — single weight; the css2 query still resolves.)

- [ ] **Step 2: Verify files are valid woff2**

```bash
file design/marketing/fonts/*.woff2   # each: "Web Open Font Format (Version 2)"
```

If any download fails → fallback: use `https://fonts.bunny.net/css?family=...` same procedure; if still failing, STOP and log incident.

- [ ] **Step 3: Commit**

```bash
git add design/marketing/fonts && git commit -m "feat(landing): self-host Archivo + Space Mono woff2 (zero external requests)"
```

### Task 3: New page — skeleton, tokens, topbar, hero + receipt animation

**Files:**
- Create: `design/marketing/index-new.html` (built standalone; swapped into place in Task 7)

- [ ] Step 1: Write document skeleton: doctype, meta/OG per copy deck, `@font-face` (5 faces, paths `fonts/...woff2`, `font-display: swap`), `:root` tokens exactly as Design Contract, base resets, `::selection { background: var(--hot); color: var(--bg); }`, focus-visible outlines in `--acid`.
- [ ] Step 2: Topbar per copy deck (tilted brand box, chunky bottom border) + kicker badges row.
- [ ] Step 3: Hero: stacked 3-line H1 (alternating ±1.2° rotation, middle line paper-on-dark), lede, both CTAs with hard shadows + hover translate(-2px,-2px)/grow-shadow, thermal receipt visual with staggered print animation, torn zigzag bottom (`clip-path` polygon), barcode strip (repeating-linear-gradient).
- [ ] Step 4: First marquee ticker (CSS keyframes, duplicated span, −2° rotate).
- [ ] Step 5: Smoke: `python3 -m http.server 8077` already running at project root → load `http://127.0.0.1:8077/design/marketing/index-new.html`, screenshot, verify hero renders, fonts load (Network tab / no 404 in server log), zero console errors.
- [ ] Step 6: Commit + update `landing_build_status.json`.

### Task 4: Sections — 3 steps, manifesto, feature sticker-grid, pipeline lineup

**Files:** Modify: `design/marketing/index-new.html`

- [ ] Step 1: 3-step section with oversized stamp numerals (`01/02/03` in Archivo Black, hot/acid alternating), copy per deck.
- [ ] Step 2: Manifesto block (paper bg, huge clamp() type, hard shadow, slight rotation).
- [ ] Step 3: Feature sticker-grid — 8 cards, alternating tilts (±1–2°), chunky borders, hover straighten + shadow-hot.
- [ ] Step 4: OCR pipeline lineup — 4 fighter cards, `LOCAL` acid badge on Ollama, caption per deck. Second ticker after.
- [ ] Step 5: Smoke (same as Task 3 Step 5) + commit + status update.

### Task 5: Sections — price, install receipt, FAQ, footer + JS reveals

**Files:** Modify: `design/marketing/index-new.html`

- [ ] Step 1: `$0/MO FOREVER` price block per deck.
- [ ] Step 2: Install section as paper receipt (mono, dashed separators, `TOTAL ... $0.00`, `THANK YOU FOR OWNING YOUR DATA`, barcode, torn edges).
- [ ] Step 3: FAQ — 4 chunky `<details>` with rotated `+` marker; footer per deck.
- [ ] Step 4: Vanilla JS: IntersectionObserver adds `.in` (stamp-slam reveal: scale 1.04→1 + fade); guard `matchMedia('(prefers-reduced-motion: reduce)')` → skip observer AND CSS `@media (prefers-reduced-motion: reduce)` kills marquee/print animations.
- [ ] Step 5: Smoke + commit + status update.

### Task 6: Responsive + polish pass

**Files:** Modify: `design/marketing/index-new.html`

- [ ] Step 1: Breakpoints 960/600: grid collapses (8→2→1 cols), H1 `clamp()` verified at 390w, topbar collapses to brand + single CTA, receipt visual scales.
- [ ] Step 2: Pass: consistent spacing scale, all interactive elements ≥44px tap targets, color contrast (cream on espresso ≈ 12:1, paper-ink on paper ≈ 14:1 — verify hot-on-dark used only for large/bold text).
- [ ] Step 3: Screenshot 1440w + 390w; fix anything broken. Commit + status update.

### Task 7: Swap into place + full done-gate + ship

**Files:**
- Modify: `design/marketing/index.html` (replaced by index-new.html content)
- Delete: `design/marketing/index-new.html`

- [ ] Step 1: `mv design/marketing/index-new.html design/marketing/index.html`
- [ ] Step 2: Run FULL adapted done-gate (top of plan) over HTTP serve. External-origin grep:

```bash
grep -nE '(src|href)="https?://' design/marketing/index.html  # only expected: GitHub repo links (navigation, not assets)
```

- [ ] Step 3: If Flask runnable locally without secrets → boot and `curl -s localhost:8090/ | head -5` to confirm new page at `/`; if not runnable, verify by reading the serving route that it statically maps to `design/marketing/index.html` (Task 1 findings) and log "verified by route-read, not live boot".
- [ ] Step 4: Final commit; update `landing_build_status.json` (all phases done); append any incidents to `AGENT_LEARNINGS.md` per learning loop.

---

## Self-review notes

- Spec coverage: design-opposite contract ✓, copy deck complete ✓, fonts self-hosted ✓, serving/wiring pre-flight ✓, old design preservation ✓, LAN dashboard already live (outside plan) ✓.
- Types/consistency: single HTML file — token names used consistently across tasks (`--hot`, `--acid`, `--paper`).
- No placeholders: copy deck is verbatim-final; visual construction steps name exact techniques (clip-path zigzag, repeating-linear-gradient barcode, IntersectionObserver `.in`).
