# Feature Documentation Page — Design Spec

## Goal

Build a `/features` page built into the app that documents every feature of LocalOCR Extended at a granular level, with rich visuals. Serves as a personal feature reference — browse feature by feature to rediscover things you've forgotten, or onboard a new household member.

---

## What Is Not Changing

- `src/frontend/index.html` — one minimal change only: add "📖 Features" nav link
- Existing pages, auth system, all existing features
- Database schema

---

## Architecture

Three new files added to the project:

| File | Purpose |
|------|---------|
| `src/backend/handle_features.py` | Flask blueprint, `url_prefix="/features"`. Two routes: `GET /features` → `features.html`; `GET /features/data` → `features-data.js`. Both require `@require_auth`. |
| `src/frontend/features.html` | Self-contained HTML page: own CSS, own JS, sidebar + detail pane layout. Loads feature data via `<script src="/features/data">`. |
| `src/frontend/features-data.js` | Feature data as a JS module (`window.FEATURES_DATA = [...]`). Included via `<script>` tag in `features.html`. |
| `scripts/generate_feature_stubs.py` | One-time utility: reads `docs/superpowers/specs/*.md` + git log → writes initial `features-data.js` stubs for manual refinement. |

Blueprint registered in `create_flask_application.py` alongside existing blueprints.

Nav gets a "📖 Features" link added to the existing sidebar/header nav.

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Nav bar: LocalOCR Extended  …  📖 Features                │
├──────────────┬──────────────────────────────────────────────┤
│  🔍 Search…  │                                              │
│              │  📸  OCR Upload                              │
│  ─ Receipts  │  Upload a photo → AI extracts items → saved  │
│  📸 OCR ←   │                                              │
│  ✏️ Review   │  📍 Nav → Upload (camera icon)               │
│  🔄 Re-run   │                                              │
│              │  ┌──────┐  →  ┌──────┐  →  ┌──────┐  →  ┌──────┐ │
│  ─ Grocery   │  │📷    │     │🤖    │     │✏️    │     │✅    │ │
│  📦 Inventory│  │Upload│     │OCR   │     │Review│     │Saved │ │
│  🛒 Shopping │  └──────┘     └──────┘     └──────┘     └──────┘ │
│  💡 Recs     │                                              │
│              │  [mini UI mockup of the review screen]       │
│  ─ Finance   │                                              │
│  📊 Analytics│  Key interactions (2-column grid)            │
│  📌 Fixed    │                                              │
│  🏦 Plaid    │  💡 Tip: Landscape photos auto-rotated…      │
│  …           │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### Sidebar

- Search input at top — filters feature list live (case-insensitive match on title + tagline)
- Groups with uppercase labels (Receipts, Grocery, Restaurant, Expenses, Finance, Shared Dining, Telegram Bot, Household)
- Active feature highlighted in blue
- Clicking any item loads its detail pane without page reload

### Detail Pane

Each feature entry renders these sections in order:

1. **Header** — large icon + title + tagline + platform badges (Web / Mobile / Telegram)
2. **Where to find it** — breadcrumb-style nav path (e.g., "Nav → 📷 Upload")
3. **Flow diagram** — horizontal boxes with arrows, one box per step, colored to show start/end
4. **Mini UI mockup** — small rendered HTML preview showing what the actual screen looks like
5. **Key interactions** — 2-column grid of what you can do in this feature
6. **Tip box** — amber-bordered callout with gotchas, edge cases, power-user hints (optional — omitted if nothing notable)

---

## Feature Data Schema

`features-data.js` exports `window.FEATURES_DATA` — an array of group objects:

```js
window.FEATURES_DATA = [
  {
    id: "receipts",
    label: "Receipts",
    icon: "📸",
    features: [
      {
        id: "ocr-upload",
        icon: "📸",
        title: "OCR Upload",
        tagline: "Upload a photo → AI extracts all items → you review → saved to inventory",
        platforms: ["Web", "Mobile"],          // shown as colored badges
        where: "Nav bar → camera icon (📷) or tap + on mobile",
        flow: [
          { icon: "📷", label: "Upload",    sub: "photo" },
          { icon: "🤖", label: "AI OCR",    sub: "reads receipt" },
          { icon: "✏️", label: "Review",    sub: "fix errors" },
          { icon: "✅", label: "Confirmed", sub: "→ inventory" }
        ],
        mockup: `...HTML string for mini UI preview...`,
        interactions: [
          "Choose receipt type: auto / grocery / restaurant / expense",
          "Switch AI model per upload (GPT-4o, Gemini, Ollama)",
          "Edit store, date, items, total before confirming",
          "Re-run OCR on already-saved receipts anytime"
        ],
        tip: "Landscape photos auto-rotated before OCR. If items are missing, use Re-run OCR from receipt detail — a different model sometimes catches what the first missed."
      }
    ]
  }
]
```

`mockup` is an HTML string rendered directly into the detail pane inside a styled container. It contains a small faithful replica of the relevant UI screen (dark-themed, same visual language as the app).

---

## Feature Groups and Entries

### 📸 Receipts (4 features)
- **OCR Upload** — photo upload, AI model selection, receipt type, review flow
- **Review & Edit** — editing extracted fields, rotating landscape photos, confirm/reject
- **Re-run OCR** — re-processing saved receipts with a different model
- **Receipt Types** — grocery vs restaurant vs general expense, auto-detect logic

### 🛒 Grocery (4 features)
- **Inventory** — product list, stock levels, categories, product detail
- **Shopping List** — manual add, auto-populate from low stock, QR share for helpers
- **Recommendations** — low-stock alerts, seasonal suggestions, confidence scores
- **Kitchen View** — compact ingredient-level view of what's in stock

### 🍽 Restaurant (3 features)
- **Restaurant Workspace** — restaurant receipts, line items, dining budget card
- **Repeat Orders** — top ordered items with average price, repeat-order estimate
- **Dining Budget** — monthly dining budget card with actual vs budget bar

### 💸 Expenses (3 features)
- **Expense Tracking** — general expense receipts, merchant summary, recent list
- **Category Tagging** — tag expenses by category, category breakdown card
- **Expense Analytics** — spend trends, merchant frequency, category pie

### 📊 Finance (4 features)
- **Spending by Category** — dashboard tile, sankey flow, expandable drill-down per category
- **Fixed Bills** — floor obligations, Selected/Available tabs, paid-vs-expected bars, inline rename
- **Plaid Integration** — bank transaction sync, automatic purchase matching
- **Cash Transactions** — manual cash spend logging

### 🤝 Shared Dining (3 features)
- **Split Bills** — split restaurant receipts by person, debt tracking
- **Contacts** — dining contacts list, per-contact balance
- **Balances & Settle** — outstanding debts view, settle-all action

### 🤖 Telegram Bot (4 features)
- **Shopping Walk** — Telegram-guided shopping session, item-by-item confirmation
- **Inventory Walk** — scan and update inventory quantities via bot
- **Dining Walk** — split a restaurant bill via Telegram conversation
- **Nudges** — scheduled reminders (shopping nudge at 09:30), configurable

### 🏠 Household (5 features)
- **Auth & Members** — login, household roles (admin/member), invite flow
- **Contributions** — who scanned what, contribution ledger, score
- **Demo Mode** — read-only guest mode with seeded sample data
- **AI Chat** — natural language questions about spending and inventory
- **Medications** — medication tracking workspace

**Total: 30 features across 8 groups**

---

## Stub Generator Script

`scripts/generate_feature_stubs.py`:

1. Reads all `docs/superpowers/specs/*.md` files
2. Extracts: first `## Goal` paragraph → tagline; `## ` section names → flow steps
3. Reads `git log --oneline` and matches commit messages to features by keyword
4. Outputs a `features-data.js` skeleton with `title`, `tagline`, `flow` pre-filled
5. Leaves `mockup`, `interactions`, `tip`, `where`, `platforms` as empty stubs for manual fill
6. Prints a checklist of which features were auto-filled vs need manual entry

Script is run once: `python scripts/generate_feature_stubs.py > src/frontend/features-data.js`

After generation, `features-data.js` is manually edited to add mockups and polish descriptions.

---

## Styling

`features.html` is self-contained — it duplicates the app's dark theme CSS variables inline rather than loading `design-system.css`. This keeps the page portable and immune to changes in the main stylesheet.

Color palette matches the app:
- Background: `#111113`
- Surface: `#1a1a1e`
- Border: `#2a2a2e`
- Accent: `#3b82f6`
- Success: `#2fa36b`
- Warning: `#f59e0b`
- Text: `#f0f0f0`
- Muted: `#888`

---

## Files Changed

| File | Change |
|------|--------|
| `src/backend/handle_features.py` | New — blueprint + route |
| `src/frontend/features.html` | New — full self-contained page |
| `src/frontend/features-data.js` | New — feature data (generated + manually polished) |
| `scripts/generate_feature_stubs.py` | New — one-time stub generator |
| `src/backend/create_flask_application.py` | Register `features_bp` |
| `src/frontend/index.html` | Add "📖 Features" link to nav |

---

## Out of Scope

- Auto-updating mockups from live screenshots (static HTML mockups only)
- Search across feature *content* (only title + tagline searched)
- Version history per feature
- Public/unauthenticated access to the features page
- Editing feature content from within the app UI (edit `features-data.js` directly)
