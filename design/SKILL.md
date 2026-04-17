# LocalOCR Design System — Skill

**Purpose.** Guidance for designing LocalOCR Extended, a privacy-first, self-hosted OCR + household-expense platform. Apple-inspired visual DNA, rendered without Apple's brand or product imagery.

## When to use

Invoke this skill when designing any LocalOCR surface — marketing pages, the web app, review flows, settings, installers, mobile wrappers — or any artifact that should read as "part of LocalOCR."

## Starting points

- **Tokens (authoritative):** `colors_and_type.css` at the project root. Import it from every HTML file.
- **Token data:** `design-tokens.json` for programmatic access.
- **Full spec:** `Design System inspired by Apple.md` — read sections 1–7 for philosophy, 4 for components.
- **Preview cards:** `preview/` — small specimens for colors, type, spacing, components.
- **Extended UI kit:** `preview/ui-kit-localocr.html` — three fully-rendered product screens (dashboard, review, upload).

## Core rules

1. **Binary canvas.** Alternate pure black `#000` for artifact / hero moments and light gray `#f5f5f7` for informational surfaces. No third background color.
2. **One accent.** Apple Blue `#0071e3` for interactive elements only. Links use `#0066cc` on light, `#2997ff` on dark.
3. **Optical-sizing typography.** `--font-display` ≥ 20px (SF Pro Display), `--font-text` < 20px (SF Pro Text). Negative tracking at every size.
4. **OCR confidence tri-scale, never color-alone.** Green `✓ ≥0.85`, Orange `! 0.60–0.84`, Red `⚠ <0.60`. Always pair glyph + numeric value with the color.
5. **Pill signature.** 980px radius for "Learn more" / "Shop" style links. 8px radius for primary buttons. Circle (50%) for media controls.
6. **One shadow or none.** `--shadow-1` (`rgba(0,0,0,0.22) 3px 5px 30px`) is the signature lift. Modal/popover escalate to `--shadow-3/4`. Most elements have no shadow.
7. **No decorative gradient, texture, or border.** Borders appear only on inputs and secondary buttons; cards are flat.

## Canonical patterns

- **Primary CTA:** 8px radius, `#0071e3` bg, `#fff` text, 10px×18px padding, SF Pro Text 17px/400.
- **Pill link:** 980px radius, transparent bg, 1px solid `#0066cc` border, `#0066cc` text, 8px×18px padding.
- **Receipt card:** white surface, 8px radius, `--shadow-1`, 3/4 aspect image area with category pill top-left and confidence pill top-right.
- **Field + confidence:** input label row includes a confidence pill `✓ 0.94` inline; low-confidence fields get `border-color: rgba(255,59,48,0.4)` and a red helper line.
- **Toast:** 4px colored left-accent stripe (`info/success/warning/error`), `--shadow-3`, 8px radius, title 17/600 + desc 14/400, optional action link in `#0066cc`.
- **Nav:** `rgba(0,0,0,0.82)` + `backdrop-filter: saturate(180%) blur(20px)` over any section.

## Do

- Quote exact hex values from the CSS custom properties.
- Use tabular numerals (`font-variant-numeric: tabular-nums`) for any editable numeric field.
- Use SF Mono 13px for raw OCR output.
- Keep chromatic spend-category dots desaturated — they are informational, not decorative.

## Don't

- Don't invent new accent hues or secondary brand colors.
- Don't stack multiple shadow layers for "depth." One soft cast is the system.
- Don't introduce rounded rectangles > 16px radius (use 980px pill, or stay ≤ 12px).
- Don't place body text centered — only headlines centre.
- Don't let emoji stand in for iconography — use 1.5px-stroke line icons (Lucide family).
- Don't encode confidence in color alone — always pair with `✓/!/⚠` and a numeric value.

## Quick file map

| Need | File |
| --- | --- |
| Import tokens | `colors_and_type.css` |
| Machine-readable tokens | `design-tokens.json` |
| Deep spec | `Design System inspired by Apple.md` |
| Colors previews | `preview/colors-*.html` |
| Type previews | `preview/type-*.html` |
| Spacing / radius / shadow / motion | `preview/spacing-scale.html`, `radius-scale.html`, `shadow-elevation.html`, `motion.html` |
| Components | `preview/components-*.html` |
| Iconography | `preview/iconography.html` |
| Product surfaces | `preview/ui-kit-localocr.html` |
