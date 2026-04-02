# Complete Product Specification

> Purpose: this is the single rebuild document for the Grocery Inventory & Savings Management app. A new engineer or agent should be able to reproduce the current app from this document without relying on tribal knowledge.

## 1. Product Summary

The app is a privacy-first household grocery and receipt management system. It accepts receipts from the web app or Telegram, extracts purchase data with AI OCR, stores product and spending history, maintains inventory, generates recommendations, and supports a shared shopping list for future purchases.

Primary goals:
- make receipt capture easy
- reduce duplicate purchases
- track shared household inventory
- surface spending and budget visibility
- preserve full local control over data

Primary runtime:
- Flask app on port `8080`
- SQLite database with WAL mode
- optional MQTT/Home Assistant integration
- optional Telegram bot for receipt ingestion
- optional Ollama/OpenAI fallback OCR

## 2. Core Product Principles

- Local-first: the database and receipt files live locally.
- Multi-user household model: multiple users can log in and share the same data.
- Safe defaults: OCR uncertainty should go to review rather than silently corrupt data.
- Rebuildable runtime: should be deployable by Docker Compose or local Python.
- Explicit provenance: users should be able to trace products back to receipts.
- Canonical naming: products and stores should normalize obvious case-only duplicates.

## 3. User Types

### Admin
- can log in to the web app
- can create household users
- can edit users
- can reset passwords
- can activate/deactivate users
- can use all standard app features

### User
- can log in to the web app
- can upload receipts
- can review receipts
- can manage inventory, products, shopping list, budget, analytics, and recommendations
- cannot manage household users

### Telegram User
- sends photo or PDF receipts to the Telegram bot
- must confirm before OCR begins
- receipt is processed and stored in the same system as web uploads
- future goal: link Telegram user to a local household account automatically

## 4. Navigation Model

Main tabs in the web app:
- Dashboard
- Inventory
- Upload Receipt
- Receipts
- Shopping List
- Budget
- Analytics
- Contribution
- Settings

Expected behavior:
- each tab loads data lazily when opened
- mobile uses off-canvas navigation
- browser auth is required for all data tabs
- Inventory contains a toggle between `Inventory` and `Products`
- Shopping List contains a collapsible `Recommendations` section rather than a separate Recommendations tab
- QR utilities must be hidden from normal navigation and revealed only through the intentional brand-text long-press interaction

## 5. Data Model

Main tables:
- `users`
- `products`
- `stores`
- `inventory`
- `purchases`
- `receipt_items`
- `price_history`
- `budget`
- `telegram_receipts`
- `shopping_list_items`
- `api_usage`

Important relationships:
- one `purchase` belongs to one `store`
- one `purchase` can have many `receipt_items`
- one `receipt_item` points to one `product`
- one `product` can have many `inventory`, `receipt_items`, and `price_history` rows
- one `telegram_receipt` may point to one `purchase`
- one `shopping_list_item` may point to one `product`

## 6. Naming Standards

### Product Names

Rules:
- normalize spaces
- standardize case for OCR-heavy names
- case-only variants must resolve to a single product
- manual rename must support merge into an existing canonical product
- savings/coupon pseudo-lines must never become products
- human-readable display names should be preferred over raw OCR strings in normal UI views

Examples:
- `AVOCADOS` and `Avocados` must become `Avocados`
- `AMUL MILK` and `Amul Milk` must become `Amul Milk`
- `Org Spinach` must become `Organic Spinach`
- `Vine Tomatoes` must become `Vine Tomato`

Restrictions:
- do not aggressively rewrite semantic abbreviations unless intentionally mapped
- do not create a new product if the only difference is case/spacing inside the same category

### Store Names

Rules:
- normalize spaces
- standardize case to one display form
- case-only variants must resolve to a single store

Example:
- `COSTCO WHOLESALE` and `Costco Wholesale` must become `Costco Wholesale`

## 7. Authentication and Access Rules

Current implementation:
- browser login uses Flask session auth
- API/integration access can still use bearer token auth

Required auth endpoints:
- `GET /auth/bootstrap-info`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `GET /auth/users`
- `POST /auth/users`
- `PUT /auth/users/{id}`

Rules:
- all app APIs require auth except Telegram webhook and root/static serving
- bootstrap admin comes from `.env`
- no open self-registration
- forgot-password is request-only, fulfilled by admin
- inactive users cannot log in
- last active admin cannot be removed/demoted

## 8. Receipt Ingestion Workflows

### Web Upload Workflow

1. user opens `Upload Receipt`
2. user uploads image or PDF
3. frontend posts multipart form to `POST /receipts/upload`
4. backend stores the file under receipt storage
5. OCR pipeline runs
6. result becomes:
   - `processed`
   - `review`
   - `failed`
7. frontend shows extracted items and result summary

Supported upload file types:
- `.jpg`
- `.jpeg`
- `.png`
- `.webp`
- `.heic`
- `.pdf`

### Telegram Workflow

1. user sends photo or PDF to the bot
2. bot stores a pending receipt record
3. bot asks whether to process
4. if confirmed, OCR pipeline runs
5. bot replies with success or review guidance
6. receipt appears in the web app under `Receipts`

Rules:
- Telegram callback handling must be enabled
- public HTTPS webhook is required
- Telegram and upload receipts must end up in the same receipt-review system

## 9. OCR Pipeline

OCR order:
- Gemini
- OpenAI fallback
- Ollama fallback

PDF handling:
- render first page image for vision OCR
- also parse PDF text layer for summary fields when possible

Required OCR fields for auto-save:
- `store`
- `date`
- `items`
- `total`

Confidence routing:
- valid + high confidence: `processed`
- valid + medium confidence: `review`
- invalid or missing critical fields: `review`
- total failure: `failed`

Required stored OCR output:
- raw OCR payload for review receipts
- OCR engine used
- confidence
- receipt type

## 10. Receipt Classification Rules

Classes:
- `grocery`
- `retail_items`
- `restaurant`
- `unknown`

Behavior:
- `grocery`: save purchase and update inventory
- `retail_items`: save purchase and update inventory for reference
- `restaurant`: save purchase/receipt history only, do not add to inventory
- `unknown`: keep conservative and route to review/reference unless explicitly approved

## 11. Receipts Tab Specification

Purpose:
- central history and review surface for all uploaded or Telegram receipts

Required functionality:
- list receipts
- open receipt details
- image/PDF preview
- show extracted items
- show OCR engine and confidence
- re-run OCR for review/failed receipts
- approve edited review receipts
- delete unwanted receipts

Required filters:
- store
- purchase date from/to
- upload date from/to
- source
- status

Required summaries:
- total receipts
- receipts by store
- purchases by month

UI rules:
- purchases by month should remain a clean single-row chart on desktop
- receipt jump links from Products must open the selected receipt, not the newest receipt

Deletion rules:
- deleting a processed receipt must also remove linked purchase data and reverse inventory changes from that receipt
- deletion order must avoid foreign key conflicts

## 12. Dashboard Specification

Purpose:
- quick household overview

Required cards:
- total products
- inventory count
- low-stock count
- budget usage
- low-stock alert list
- top recommendations

Rules:
- low-stock widget must use the same inventory source as the Inventory tab
- dashboard must tolerate empty states cleanly

## 13. Inventory Tab Specification

Purpose:
- manage household stock on hand

Required functionality:
- list all inventory items
- add inventory item manually
- consume quantity
- delete inventory item
- search current inventory
- filter by multiple categories
- jump to linked receipts for traceability

Required fields:
- product name
- quantity
- location
- status

Search rules:
- search should filter current list by name, location, quantity, or readable metadata
- no-backend-search requirement; client-side filtering is acceptable

Actions:
- consume one unit
- rename / clean up product name
- update category
- update location
- mark low / clear low
- delete
- add to shopping list

UI rules:
- mobile inventory rows should use a compact two-row layout
- action buttons should live on a single horizontal action strip on phones
- normal UI should prefer normalized/display names and not force raw OCR text as the primary label

## 14. Products Tab Specification

Purpose:
- maintain the reusable product catalog

Implementation note:
- products live inside the Inventory page as a toggle, not as a separate top-level navigation tab

Required functionality:
- list products
- search products
- create product
- delete product
- rename product
- recategorize product
- merge canonical duplicates via rename
- show grouped variants
- show linked receipt shortcuts
- add product to shopping list

Grouping rules:
- group similar items for display, but do not over-collapse semantically different items
- example: `Whole Milk`, `Amul Milk`, `Almond Milk`, `A2 Milk` should not all collapse into one generic milk row

Traceability rules:
- each product variant can show recent linked receipts
- linked receipt labels must use purchase date, not product creation date
- inline cleanup actions should be consistent with the Inventory view
- category list must include at least `apparel` and `grains`

## 15. Shopping List Tab Specification

Purpose:
- hold planned purchases outside of current inventory

Required functionality:
- manual add
- quick find product search
- list open items
- list purchased items
- mark bought
- reopen
- delete
- merge duplicate open items by name/category
- choose preferred store when adding from the Shopping page
- group items by store
- show estimated total cost
- show estimated store stops
- show recommendations in a collapsible section
- show current list in a collapsible section
- show quick find in a collapsible section
- show store-stop summary in a collapsible section

Required fields:
- name
- category
- quantity
- source
- note
- status
- preferred store
- estimated price when available

Allowed sources:
- `manual`
- `inventory`
- `product`
- `recommendation`

Cross-tab actions:
- Recommendations -> add to shopping list
- Inventory -> add item to shopping list
- Products -> add item to shopping list

Safety / recovery rules:
- bought items must remain reopenable so accidental check-offs can be undone
- logged-in users and helper-mode users should both have a recovery path for mistaken `Bought` taps

Helper-share rules:
- there must be a scoped shopping-helper share mode reachable by QR
- helper mode can view the shopping list and mark bought/reopen only
- helper mode must not expose settings, inventory editing, or household management
- helper mode should use a simplified phone-first layout with compact summary stats and minimal item metadata

## 16. Budget Tab Specification

Purpose:
- monthly spend cap management

Required functionality:
- set monthly budget
- view current month status
- show amount spent
- show amount remaining
- show percent used

Rules:
- budget is user-scoped when user-specific budgets exist
- fallback to household/default budget where applicable

## 17. Analytics Tab Specification

Purpose:
- spending visibility and deal tracking

Required functionality:
- spending by period
- deals captured summary
- optional store comparison and price history support

Rules:
- frontend must match backend response shape exactly
- empty states must render gracefully when no data exists

## 18. Recommendations Within Shopping Specification

Purpose:
- surface actionable buying suggestions inside the Shopping workflow rather than as a separate standalone page

Types:
- `deal`
- `seasonal`
- `low_stock` style suggestions may also be represented visually

Required functionality:
- show product
- show message/reason
- show confidence
- add recommended item directly to shopping list
- show when a recommendation is already in the shopping list
- allow a second household user to confirm a recommendation

Rules:
- recommendations are suggestions, not inventory mutations
- adding to shopping list should not mutate inventory directly
- recommendation collaboration points should remain floating until later validation such as purchase completion or equivalent downstream confirmation

## 19. Settings Tab Specification

Purpose:
- operator and household management

Required sections:
- household users
- API token storage
- API base URL
- current signed-in user

Admin-only functionality:
- create users
- edit user profile
- reset password
- activate/deactivate user

## 20. Contribution Specification

Purpose:
- make scoring transparent and reward helpful household/system upkeep

Required functionality:
- show score rules
- show recent contribution history
- show household ranking
- show ways a user can help right now

Rules:
- no-op edits such as case-only renames must not award score
- recommendation and low-stock collaboration should support floating or pending states before final validation
- if a collaborative action is removed before validation, soft points must be reversible
- meaningful cleanup such as renaming, recategorizing, setting location, and validated low-stock/shopping actions should be trackable in the contribution ledger

## 21. Backend API Surface

Core route groups:
- `/auth`
- `/products`
- `/inventory`
- `/receipts`
- `/shopping-list`
- `/budget`
- `/analytics`
- `/recommendations`
- `/telegram`
- `/health`

Minimum required behaviors:
- JSON responses for all API routes
- auth required everywhere except public shell routes/webhook
- stable route shapes so the single-page frontend can rely on them

## 22. Background and Integration Services

### MQTT

Used for:
- low-stock alerts
- recommendations
- Home Assistant updates
- Home Assistant entity discovery via MQTT discovery topics

Current state:
- broker auth via username/password is working
- publish flow is verified for inventory, recommendations, budget alerts, and low-stock alerts
- Home Assistant discovery payloads are published automatically for supported entities

Rules:
- if MQTT auth fails, core web app should still run
- background MQTT startup must only happen in the real serving process, not the Flask debug reloader parent
- retained topics should be used for current-state entities like inventory and recommendations
- non-retained topics should be used for alert-style events where appropriate

Discovery topics to support:
- `homeassistant/sensor/grocery_inventory_{product_id}/config`
- `homeassistant/sensor/grocery_recommendations_count/config`
- `homeassistant/sensor/grocery_budget_alert/config`
- `homeassistant/sensor/grocery_low_stock_alert/config`

### Home Assistant

Purpose:
- household dashboard and automation surface

Current state:
- MQTT transport and Home Assistant-side validation are working
- MQTT discovery support is implemented for core entity types
- YAML/dashboard/automation coverage still needs broader validation and polish
- the web app remains the primary day-to-day runtime, with Home Assistant acting as the real-time household surface

### Telegram

Required for optional mobile receipt ingestion.

Restrictions:
- requires valid bot token
- requires public HTTPS webhook
- callback queries must be enabled

## 23. Deployment Requirements

### Docker

Required:
- `docker-compose.yml`
- backend service
- optional Ollama service
- optional MQTT service
- restart policies

### Local Python

Required:
- `.venv`
- `pip install -r requirements.txt`
- `python -m src.backend.create_flask_application`

### Environment Variables

At minimum:
- `INITIAL_ADMIN_EMAIL`
- `INITIAL_ADMIN_PASSWORD`
- `INITIAL_ADMIN_TOKEN`
- `SESSION_SECRET`
- `GEMINI_API_KEY`

Optional:
- `GEMINI_MODEL`
- `OPENAI_API_KEY`
- `OLLAMA_BASE_URL`
- `MQTT_BROKER`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_CLIENT_ID`
- `MQTT_DISCOVERY_ENABLED`
- `HOME_ASSISTANT_DISCOVERY_PREFIX`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`

## 24. File and Storage Rules

Receipt file storage:
- keep receipts on disk in a dedicated receipts directory
- organize by year/month
- support safe path resolution before serving files

Database rules:
- SQLite with WAL mode
- foreign keys enabled
- runtime-compatible column backfills allowed for dev databases

## 25. Non-Functional Requirements

- mobile-friendly navigation
- clear empty states
- explainable review flow
- no secret values committed to git
- direct links between catalog data and original receipts
- do not lose functionality when Telegram/MQTT are unavailable

## 26. Known Current Restrictions

- Home Assistant dashboard and automation behavior still need broader validation beyond the confirmed MQTT transport/discovery path
- OCR still produces some truncated product labels that need smarter cleanup than case normalization alone
- Telegram-to-local-user linking is not complete
- automated end-to-end coverage is still lighter than manual verification
- when running in Flask debug mode, background services must remain guarded so MQTT and schedulers do not start twice under the reloader

## 27. Build Checklist

An implementation should not be considered complete unless it includes:
- session login and admin-managed users
- receipt upload for images and PDFs
- Telegram confirm-before-process flow
- review/approve receipt workflow
- products with grouping, rename, and receipt traceability
- inventory with search
- shopping list with cross-tab add actions, store grouping, and helper-share QR flow
- receipts filtering and summaries
- budget, analytics, and contribution page
- product/store canonical naming rules
- inline rename and category cleanup from receipts, inventory, and products
- continuity/restart docs

## 28. Acceptance Criteria

The app is complete enough when:
- a new user can log in and use every tab
- a receipt can be uploaded or sent via Telegram and appear in Receipts
- bad OCR names can be corrected in Products
- bad OCR names and categories can be corrected directly from receipt detail too
- duplicate case variants do not appear as separate products/stores
- a user can add suggested items to Shopping List from other tabs
- a helper device can open the shopping helper QR view and mark items bought/reopen them
- clicking a product’s receipt shortcut opens the correct receipt
- someone new can stand up the app from this document plus the repo
