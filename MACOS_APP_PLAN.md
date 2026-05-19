# MACOS_APP_PLAN.md

> Self-contained spec for a native macOS Apple Silicon app built from the existing LocalOCR Extended web project.
> Target: macOS 13 Ventura+, Apple Silicon (M1+). Backend (Flask + SQLite) remains unchanged — macOS app is a native client.
> Each section authored by a specialist agent; downstream agents read and build on earlier sections.

---

## 1. PROJECT INVENTORY
*Authored by: [AGENT 1 — PROJECT ANALYST]*

### 1.1 TECH STACK

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | Vanilla JS / HTML / CSS — no framework, no bundler | Single-file SPA: `src/frontend/index.html` (40,050 lines, embedded JS+CSS). Extra static pages: `features.html`, `features-data.js`. |
| **Backend** | Python 3 + Flask 3.1.0, gunicorn 23.0.0 | App factory in `create_flask_application.py`; 26 registered blueprints; port 8090 default. |
| **Database** | SQLite with WAL mode; SQLAlchemy 2.0.36 ORM; Alembic 1.14.1 migrations (33 versions) | File at `/data/db/localocr_extended.db`. WAL + `PRAGMA foreign_keys=ON` set on every connection. |
| **Auth** | Flask sessions (14-day permanent cookie); Google OAuth via Authlib; FERNET-encrypted secrets; trusted device pairing; QR-share access links; Bearer token fallback | Session cookie: HttpOnly, SameSite=Lax, Secure flag controlled by `SESSION_COOKIE_SECURE` env. |
| **API style** | REST, cookie-authenticated; JSON responses | 216 routes total. No GraphQL. No versioning prefix. |
| **Realtime** | Flask-SocketIO 5.4.1 (limited use); MQTT publish via paho-mqtt 2.1.0 for IoT push events | SocketIO is available but not the primary data channel; MQTT is publish-only from backend. |
| **Storage** | Local filesystem — receipt images at `/data/receipts/<household>/...`; product images via Open Food Facts backfill | No cloud blob storage. All files are Docker-volume-mounted. |
| **Key third-party integrations** | Plaid (bank/card transactions, plaid-python 22.0.0); Telegram Bot (python-telegram-bot 21.10, webhook); Google Generative AI (google-genai ≥1.30.0); OpenAI (openai ≥1.51.0); Anthropic (anthropic ≥0.40.0); Ollama (HTTP, no SDK); OpenRouter (HTTP) | OCR model selection is runtime-switchable per user. |
| **Scheduling** | APScheduler 3.10.4 — daily recommendations + shopping nudge (09:30) + inventory nudge | Started in app factory; skipped in Flask debug reloader parent. |
| **Build tooling** | None — no webpack, vite, or bundler | Raw files served directly. `scripts/deploy_to_prod.sh` handles production deploy. |
| **CSS approach** | Inline CSS + CSS custom properties (variables) | Dark theme palette: `#111113` bg, `#1a1a1e` card, `#3b82f6` accent-blue, `#2fa36b` green, `#f59e0b` amber. Three web fonts loaded from Google Fonts: **Inter** (body), **Manrope** (UI), **Fraunces** (display/hero). |
| **Image processing** | Pillow 11.1.0 — server-side rotation for landscape receipts; qrcode 7.4.2 for QR generation | Client never manipulates images directly. |

---

### 1.2 FULL SCREEN / PAGE INVENTORY

*Source: `src/frontend/features-data.js` (30 features) + sidebar nav items + login/auth screens.*

| # | Route / Nav Target | Page Name | Auth Required | Primary Purpose | Key User Actions |
|---|---|---|---|---|---|
| 1 | `/` (login) | Login / Onboarding | No | Email+password login; Google OAuth; demo entry point | Enter credentials, click Sign In, click Google OAuth, click Try Demo |
| 2 | `/dashboard` | Dashboard | Yes | Household overview: spending tiles, review queue, low-stock alerts, attribution nudge | Navigate to any section, dismiss alerts, tag untagged receipts |
| 3 | `nav('upload')` | OCR Upload | Yes | Upload receipt photo or PDF; AI extracts items and saves to inventory | Pick file (JPEG/PNG/HEIC/PDF), select receipt type, pick AI model, submit |
| 4 | `nav('upload')` → post-OCR | Review and Edit | Yes | Edit any OCR-extracted field before confirming | Edit store, date, total, add/delete line items, rotate photo |
| 5 | Receipt detail → Re-run OCR | Re-run OCR | Yes | Re-process saved receipt with a different AI model; diff view for merge | Pick model, trigger re-run, accept/discard individual new items |
| 6 | `nav('upload')` → Type selector | Receipt Types | Yes | Auto-detect or manually pick receipt type (grocery/restaurant/expense) | Toggle type buttons, observe AI confidence, confirm type selection |
| 7 | `nav('inventory')` | Inventory | Yes | Product catalog with stock levels, categories, price history; auto-updated from receipts | Search, filter by category, edit quantity, view price history, remove product |
| 8 | `nav('shopping')` | Shopping List | Yes | Smart shopping list: add manually, auto-populate from low-stock, QR share | Add items, one-tap low-stock populate, share QR, start Telegram walk |
| 9 | `nav('shopping')` → Recommendations tab | Recommendations | Yes | Low-stock alerts and buy-again suggestions ranked by AI confidence | View ranked list, add to shopping list, dismiss item |
| 10 | `nav('kitchen')` | Kitchen View | Yes | Ingredient-level compact view of stock grouped by category for meal planning | Browse by type (Dairy/Produce/Bakery…), spot low-stock, tap to add to list |
| 11 | `nav('restaurant')` | Restaurant Workspace | Yes | Dedicated workspace for restaurant receipts with dining spend vs budget | Upload restaurant receipt, view visit line items, check budget bar |
| 12 | `nav('restaurant')` → Repeat Orders tab | Repeat Orders | Yes | Most-ordered dishes ranked by frequency with avg price and last-ordered date | View ranked dishes, see average price, last order date |
| 13 | `nav('restaurant')` → Budget card | Dining Budget | Yes | Monthly dining budget card: actual spend vs budget with live progress bar | Set budget amount (in Settings), observe bar color (green/amber/red) |
| 14 | `nav('expenses')` | Expense Tracking | Yes | Log general expense receipts — merchants, amounts, categories | Upload expense receipt, see recent expenses list |
| 15 | `nav('analytics')` → Spending by Category | Category Tagging | Yes | Tag expenses by category; view breakdown, drill into any category | Auto-tag from merchant name, edit tags, drill into category receipts, filter by month |
| 16 | `nav('analytics')` | Expense Analytics | Yes | Spend trends by week/month; merchant frequency chart; category breakdown | Switch weekly/monthly view, view bar chart, check merchant frequency, view category pie |
| 17 | `nav('dashboard')` → Spending tile | Spending by Category | Yes | Dashboard tile: every spend category in one place, expandable drill panel | View all categories ranked, expand Fixed row, drill into receipts, filter by month |
| 18 | `nav('bills')` | Fixed Bills | Yes | Track floor obligations (rent, subscriptions) — paid vs expected, inline rename | Add obligation (name + amount), rename inline, link to Plaid transaction |
| 19 | `nav('accounts')` | Plaid Integration | Yes (admin for linking; shared for viewing) | Sync bank transactions; auto-match to receipts; review staged transactions | Link bank via Plaid OAuth, sync, review matches, confirm or dismiss staged transactions |
| 20 | `nav('analytics')` → Cash tab | Cash Transactions | Yes | Manually log cash spend with no receipt; feeds into spending analytics | Enter amount + description, assign category, back-date, view alongside receipt spend |
| 21 | `nav('restaurant')` → Split tab | Split Bills | Yes | Split restaurant receipts by person — tracks who owes what | Select contacts, set even or custom split, start Telegram Dining Walk |
| 22 | `nav('restaurant')` → Contacts tab | Contacts | Yes | Dining contacts list with per-contact balance and meal history | Add contact by name, view meal history, see running balance |
| 23 | `nav('restaurant')` → Balances tab | Balances and Settle | Yes | Outstanding debt view across all contacts — settle-all with one tap | View net position, settle individual debt or settle-all, view debt history |
| 24 | Telegram `/shopping` | Shopping Walk (Telegram) | Telegram auth | Guided Telegram session — item-by-item confirmation while at the store | /shopping to start, ✅ Got it / ❌ Skip per item, /resume to continue |
| 25 | Telegram `/inventory` | Inventory Walk (Telegram) | Telegram auth | Update inventory quantities via Telegram — bot asks, user replies with count | /inventory to start, type quantity per item, type 'skip' to pass |
| 26 | Telegram `/dining` | Dining Walk (Telegram) | Telegram auth | Split restaurant bill via Telegram — photo the bill, assign items per person | Send receipt photo, bot OCRs, assign each item to person(s) |
| 27 | Telegram auto-sent at 09:30 | Nudges (Telegram) | Telegram auth | Scheduled Telegram reminders — shopping nudge when low-stock items exist | Tap 'Start walk' to begin Shopping Walk, tap 'Later' to dismiss |
| 28 | `/` → login · `nav('settings')` → Members | Auth and Members | Admin for member management | Login, household roles (admin/member), invite flow for new members | Email+password login, create/join household, admin invites/removes members |
| 29 | `nav('contributions')` | Contributions | Yes | Per-member contribution ledger and monthly leaderboard | View monthly leaderboard, drill into member's contribution list |
| 30 | `/` → Try Demo | Demo Mode | No | Read-only guest mode with seeded sample data | Click Try Demo on login, browse full UI, write actions prompt sign-in |
| 31 | `nav('chat')` | AI Chat | Yes (admin in v1) | Natural language questions about spending and inventory | Ask plain-English questions, switch AI model, get answers with context |
| 32 | `nav('medications')` | Medications | Yes | Medication tracking — log medications, track stock, set refill alerts | Add medication (name/dose/frequency), update count, get refill alerts |
| 33 | `/features` | Features Documentation | No (public) | Static documentation page for the 30 features (marketing/onboarding) | Browse feature groups, view per-feature cards with mockups and flow diagrams |
| 34 | `nav('settings')` | Settings | Yes | App configuration: AI models, trusted devices, Telegram webhook, user preferences | Configure AI model, pair device via QR, set Telegram, manage members |
| 35 | `nav('products')` | Products Catalog | Yes | Admin view of all products — review OCR names, bulk edit, backfill images | Search products, resolve OCR review queue, edit name/category, trigger image backfill |
| 36 | `nav('budget')` | Household Budget | Yes | Set and view monthly spending budgets per category | Enter budget amounts per domain, view actual vs budgeted, view change log |

*Total: 36 logical screens (30 feature screens + 6 additional: login, dashboard, settings, features doc page, products catalog, household budget).*

---

### 1.3 DATA MODELS

*Source: `src/backend/initialize_database_schema.py`. 42 tables; grouped by domain.*

#### Authentication & Access (6 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **users** | id, name, email, role (admin/user/service), is_active, password_hash, api_token_hash, session_version, google_sub, google_email, allowed_pages (JSON), allowed_ips (JSON), allow_write, active_ai_model_config_id, avatar_emoji | → purchases, budgets, active_ai_model | Login, Settings, Members, Contributions |
| **trusted_devices** | id, name, scope (shared_household/kitchen_display/read_only), status, token_hash, linked_user_id, created_by_id, allowed_pages (JSON), last_seen_at | → users | Settings → Trusted Devices |
| **device_pairing_sessions** | id, pairing_token_hash, device_name, scope, status (pending/approved/rejected/claimed), approved_by_user_id, trusted_device_id, allowed_pages, expires_at | → users, trusted_devices | Settings → Pair Device |
| **access_links** | id, created_by_id, target_user_id, purpose (shopping_helper/login_qr), token_hash, metadata_json, expires_at, used_at | → users | Shopping List QR share, QR Login |
| **household_members** | id, name, age_group (adult/child), avatar_emoji, created_by_id | → medications | Members, Medications |
| **api_usage** | id, service_name, date, model_config_id, request_count, token_count, estimated_cost_usd, total_latency_ms | → ai_model_configs | Settings → AI Usage |

#### Products & Inventory (5 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **products** | id, name, raw_name, display_name, brand, size, category, barcode, is_regular_use, is_non_product, review_state, expected_shelf_days | → inventory_items, price_history, receipt_items | Inventory, Products Catalog, Shopping List, Kitchen View |
| **inventory** | id, product_id, quantity, location (Fridge/Pantry/Freezer/Cabinet/Bathroom), threshold, manual_low, is_active_window, expires_at, last_purchased_at | → product | Inventory, Kitchen View, Shopping List, Recommendations |
| **inventory_adjustments** | id, product_id, quantity_delta, reason (receipt_window/manual_add/consume/update/delete), user_id, created_at | — | Inventory (audit trail) |
| **category_shelf_life_default** | category (PK), location_default, shelf_life_days | — | Inventory (expiry defaults) |
| **price_history** | id, product_id, store_id, price, date | → product, store | Inventory (price trend chart) |

#### Receipts & Purchases (5 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **purchases** | id, store_id, total_amount, date, domain (grocery/restaurant/expense/household_obligations), transaction_type, user_id, attribution_user_id, attribution_user_ids (JSON), attribution_kind | → store, user, receipt_items | All receipt/spending screens |
| **receipt_items** | id, purchase_id, product_id, quantity, unit_price, size_label, spending_domain, budget_category, extracted_by, attribution_user_id, attribution_user_ids, kind (product/discount/fee/tax/tip/membership…) | → purchase, product | OCR Upload, Review & Edit, Re-run OCR, Analytics |
| **stores** | id, name, location, is_payment_artifact, visibility_override | → purchases, price_history | Receipts, Analytics, Fixed Bills |
| **product_snapshots** | id, product_id, shopping_list_item_id, receipt_item_id, purchase_id, store_id, user_id, source_context, status, image_path, ai_extracted_name, ai_confidence | — | Products Catalog (image backfill) |
| **telegram_receipts** | id, telegram_user_id, message_id, image_path, status, ocr_confidence, receipt_type, raw_ocr_json, purchase_id, file_hash, retry_count | — | Telegram bot flows |

#### Shopping (3 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **shopping_sessions** | id, name, status (active/ready_to_bill/closed), store_hint, estimated_total_snapshot, actual_total_snapshot, created_by_id, closed_at | — | Shopping List |
| **shopping_list_items** | id, product_id, user_id, shopping_session_id, name, quantity, status (open/purchased), source (recommendation/inventory/product/manual), note, preferred_store, manual_estimated_price, actual_price | — | Shopping List, Recommendations |
| **contribution_events** | id, user_id, event_type, subject_type, subject_id, status, points, description, metadata_json | — | Contributions |

#### AI & Chat (3 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **ai_model_configs** | id, name, provider, model_string, price_tier, is_enabled, is_visible, credential_mode, api_key_encrypted (Fernet), base_url, supports_vision, supports_pdf, input_cost_per_million | → users (active_ai_model) | Settings → AI Models, OCR Upload |
| **user_ai_model_access** | id, user_id, model_config_id, unlocked_at, expires_at | — | Settings (per-user model access) |
| **chat_messages** | id, user_id, role (user/assistant), content, tool_trace (JSON), flagged, flag_reason | — | AI Chat |

#### Finance & Bills (7 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **bill_meta** | id, purchase_id (1:1), provider_name, provider_type, provider_id, service_line_id, billing_cycle_month, billing_cycle, planning_month, is_recurring, auto_pay, payment_status, payment_confirmed_at | → purchase, bill_providers, bill_service_lines | Fixed Bills |
| **bill_providers** | id, canonical_name, normalized_key, provider_type_hint, provider_category, is_active | → bill_service_lines, floor_obligations | Fixed Bills |
| **bill_service_lines** | id, provider_id, service_type, account_label, expected_payment_day, typical_amount_min/max, normalized_key | → provider | Fixed Bills, Cash Transactions |
| **cash_transactions** | id, purchase_id, service_line_id, planning_month, transaction_date, amount, payment_method, transfer_reference, snapshot_id, status | — | Cash Transactions |
| **bill_allocations** | id, purchase_id, service_line_id, amount, description | — | Fixed Bills (multi-line allocations) |
| **budget** | id, user_id, month (YYYY-MM), domain, budget_category, budget_amount | → user | Household Budget, Dining Budget |
| **budget_change_log** | id, user_id, month, domain, previous_amount, new_amount, changed_at | — | Household Budget (audit) |

#### Plaid Integration (4 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **plaid_items** | id, user_id, plaid_item_id, institution_id/name, access_token_encrypted (Fernet), transaction_cursor, last_sync_at, status (active/disconnected/login_required), nickname, shared_with_user_ids (JSON) | — | Plaid Integration |
| **plaid_accounts** | id, plaid_item_id, user_id, plaid_account_id, account_name/mask/type/subtype, balance_cents, credit_limit_cents, display_name, owner_label | — | Plaid Integration |
| **plaid_staged_transactions** | id, plaid_item_id, user_id, plaid_transaction_id, amount, transaction_date, merchant_name, suggested_receipt_type, status (ready_to_import/confirmed/dismissed), duplicate_purchase_id | — | Plaid Integration |
| **dedup_dismissals** | id, user_id, purchase_id_low, purchase_id_high | — | Plaid Integration (dedup workflow) |

#### Floor Obligations (1 table)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **floor_obligations** | id, label, expected_monthly_amount, is_active, bill_provider_id | → bill_providers | Fixed Bills |

#### Shared Dining (4 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **dining_contacts** | id, name, phone, email | → shared_participants | Contacts, Split Bills |
| **shared_expenses** | id, purchase_id, total_amount, my_amount, payment_scenario (PAID_ALL/PAID_OWN/OWED), notes | → participants, debts | Split Bills |
| **shared_participants** | id, shared_expense_id, contact_id, ad_hoc_name, is_self, share_amount | → contact | Split Bills, Balances |
| **shared_debts** | id, shared_expense_id, participant_id, direction (THEY_OWE_ME/I_OWE_THEM), amount, settled, settled_at | — | Balances and Settle |

#### Telegram Sessions (3 tables)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **telegram_inventory_session** | chat_id (PK), user_id, status, current_category, item_queue (JSON), cursor, pending_prompt, nudge_muted_until, last_nudge_sent_at | — | Telegram Inventory Walk |
| **telegram_shopping_session** | chat_id (PK), user_id, status, category_queue (JSON), current_category, item_queue, cursor, pending_action, nudge_muted_until, last_nudge_sent_at | — | Telegram Shopping Walk |
| **telegram_split_session** | chat_id (PK), state (JSON) | — | Telegram Dining Walk |

#### Medications (2 tables — already counted under household_members above)

| Entity | Key Fields | Relations | Used On Screens |
|---|---|---|---|
| **medications** | id, name, brand, strength, dosage_form, active_ingredient, age_group, belongs_to, member_id, user_id, barcode, product_id, expiry_date, quantity, unit, low_threshold, rx_number, prescribing_doctor, ai_warnings (JSON), status (active/expired/finished) | → household_members, product | Medications |

*Total: 42 tables confirmed.*

---

### 1.4 API ENDPOINTS

*Grouped by blueprint/handler file. Total: 216+ routes.*

| Group (handler file) | Route count | Auth | Primary Purpose | Used By Screens |
|---|---|---|---|---|
| `manage_authentication.py` (`auth_bp`, `/auth`) | 38 | Mixed (public for login/OAuth, auth for all else) | Login/logout, Google OAuth start/callback/link/unlink, QR login link + redeem, device pairing (start/handoff/status/claim/approve/reject), trusted device CRUD, user CRUD, service accounts, invites, household members list, `/me/stats`, `/config` | Login, Settings (all auth subpanels), Auth and Members |
| `plaid_integration.py` (`plaid_bp`, `/plaid`) | 24 | Yes (admin for link; shared for view) | Plaid Link token create, item exchange, items CRUD, accounts, balance refresh, staged transactions list/confirm/dismiss/bulk, dedup scan, sync trigger, floor obligations via Plaid | Plaid Integration, Fixed Bills |
| `handle_receipt_upload.py` (`receipts_bp`, `/receipts`) | 24 | Yes | Upload receipt (multipart), re-run OCR, get/list receipts, receipt image serve, update receipt fields, delete, mark reviewed, receipt stats | OCR Upload, Review & Edit, Re-run OCR, Receipt Types |
| `calculate_spending_analytics.py` (`analytics_bp`, `/analytics`) | 13 | Yes | Spending by category, Sankey flow, drill-down, spend by person, merchant frequency, timeline, budget vs actual, dedup receipts | Expense Analytics, Spending by Category, Category Tagging, Dashboard |
| `manage_shopping_list.py` (`shopping_list_bp`, `/shopping`) | 14 | Yes | Shopping list items CRUD, session lifecycle (open/close/finalize), auto-populate from recs, QR share token, store-preference bulk update | Shopping List, Recommendations |
| `manage_product_catalog.py` (`products_bp`, `/products`) | 12 | Yes | Product CRUD, search, review queue, bulk rename, category list, barcode lookup | Products Catalog, Inventory, OCR Upload |
| `manage_inventory.py` (`inventory_bp`, `/inventory`) | 12 | Yes | Inventory item CRUD, quantity edit, consume, mark low, bulk update, location update, expiry, kitchen view data | Inventory, Kitchen View |
| `shared_dining_endpoints.py` (`shared_dining_bp`, `/dining`) | 9 | Yes | Shared expense CRUD, participants, debts, settle, contacts CRUD, balances summary | Split Bills, Contacts, Balances |
| `manage_product_snapshots.py` (`product_snapshots_bp`, `/snapshots`) | 8 | Yes | Snapshot CRUD, image upload, AI enrichment trigger, review status update | Products Catalog (snapshot review) |
| `manage_medications.py` (`medications_bp`, `/medications`) | 7 | Yes | Medication CRUD, barcode lookup, household member CRUD for medication context | Medications |
| `manage_image_backfill.py` (`image_backfill_bp`, `/products`) | 7 | Yes (admin) | Trigger product image backfill, status, per-product image fetch | Products Catalog |
| `manage_ai_models.py` (`ai_models_bp` + `admin_ai_models_bp`) | 7 | Yes (admin for admin endpoints) | List/get available models, set active model, admin CRUD for model configs, API key storage (Fernet), usage stats | Settings → AI Models, OCR Upload |
| `handle_floor_obligations.py` (`floor_obligations_bp`, `/obligations`) | 6 | Yes | Floor obligation CRUD, list active, mark paid, link to Plaid | Fixed Bills |
| `manage_household_budget.py` (`budget_bp`, `/budget`) | 5 | Yes | Budget CRUD per domain/month, change log, dining budget card | Household Budget, Dining Budget |
| `manage_cash_transactions.py` (`cash_transactions_bp` + `bill_edit_bp`) | 5 | Yes | Cash transaction CRUD, bill edit endpoint | Cash Transactions, Fixed Bills |
| `manage_household_members.py` (`household_members_bp`, `/household`) | 4 | Yes | Household member (non-auth person) CRUD for medication assignment | Members, Medications |
| `chat_endpoints.py` (`chat_bp`, `/chat`) | 4 | Yes (admin in v1) | Chat message send (SSE streaming), history, clear history, guardrail status | AI Chat |
| `manage_stores_endpoint.py` (`stores_bp`, `/stores`) | 2 | Yes | Store list, store CRUD | Receipts, Fixed Bills |
| `manage_contributions.py` (`contributions_bp`, `/contributions`) | 2 | Yes | Contribution events list, score rules | Contributions |
| `handle_features.py` (`features_bp`, `/features`) | 2 | No (public) | Serve features.html + features-data.js | Features Documentation |
| `manage_kitchen_endpoint.py` (`kitchen_bp`, `/kitchen`) | 1 | Yes | Kitchen view aggregated data endpoint | Kitchen View |
| `handle_telegram_messages.py` (`telegram_bp`, `/telegram`) | 1 | No (webhook secret) | Receive Telegram webhook updates | Telegram Walks, Nudges |
| `generate_recommendations.py` (`recommendations_bp`, `/recommendations`) | 1 | Yes | Low-stock recommendation list | Recommendations |
| `manage_environment_ops.py` (`environment_ops_bp`, `/system`) | 5 | Yes (admin) | Backup list/create/upload/download/verify/restore | Settings → Backup & Restore |

*Note: `extract_receipt_data.py`, `bill_cadence.py`, `plaid_receipt_matcher.py`, `route_ai_inference.py`, `contribution_scores.py`, `shopping_nudge_job.py`, `inventory_nudge_job.py`, and similar files are pure logic/utility — no routes of their own; called by the blueprints above.*

---

### 1.5 STATE MANAGEMENT

**Global state (module-level `let`/`const` in `index.html` JS block, starting ~line 7682):**

The SPA keeps all runtime state as plain JavaScript variables in a single script block. Key state objects:

- `API_BASE` — base URL, seeded from `localStorage.getItem("api_base")` or derived from `window.location.origin`
- `TOKEN` — legacy bearer token from `localStorage` (most auth is now cookie-based)
- `currentUser` — object returned from `/auth/me`; null until authenticated
- `currentAuthContext` — `{ source, trusted_device }` object from `/auth/me`; drives UI gating
- `appConfig` — server config snapshot (module flags, Google OAuth enabled, etc.)
- `householdUsers` — array of household member objects; refreshed on Settings open
- `availableAiModels` / `activeAiModelConfigId` — AI model list + selected model; `activeAiModelConfigId` persisted to `localStorage` with key `active_ai_model_config_id`
- `shoppingListCache` / `inventoryAllItemsCache` — client-side arrays for instant search without round-trips
- `inventoryCategoryFilters` / `productCategoryFilters` — `Set` objects for active filter chips
- `SHOPPING_HELPER_MODE` / `SHOPPING_HELPER_TOKEN` — detect when serving the `/shopping-helper/<token>` QR-share URL
- Numerous page-scoped sort/filter variables (`receiptSort`, `productSort`, `shoppingSort`, `analyticsSort`, etc.)

**Server state (fetch + cookies; no caching library):**

Every page load triggers fresh API calls via `fetch()` using the session cookie. There is no client-side query cache or stale-while-revalidate. When the user navigates to a page, the `nav()` function fires page-specific load functions (e.g. `loadInventory()`, `loadShoppingList()`) which call the REST API and repopulate the DOM. Subsequent navigations re-fetch. Notable exception: `inventoryAllItemsCache` and `shoppingListCache` are populated once and searched client-side to avoid repeated calls during in-page search interactions; they are invalidated on mutation.

**Form state (DOM-driven):**

Forms use standard HTML `<input>`, `<select>`, and `<textarea>` elements. No form library. Validation is inline JavaScript on submit. File uploads use `FormData`. Inline edits (e.g. bill obligation rename) use `contenteditable` or `<input>` with `blur`/`Enter` listeners that call PATCH immediately.

---

### 1.6 AUTHENTICATION FLOW

*Source: `src/backend/manage_authentication.py`*

#### Step-by-step auth resolution (per request, in priority order)

1. **Trusted Device Token header** — If `X-Trusted-Device-Token` header is present, hash it (SHA-256) and look up `trusted_devices.token_hash`. If device is `active` and the linked user is active, authenticate as that user in `trusted_device_token` context. Any failure clears the browser session and returns 401 (no fallback to cookie).

2. **Trusted Device session cookie** — If `session["trusted_device_id"]` is set, load the `TrustedDevice` row. Verify status is `active`, linked user is active, and `session["session_version"]` matches `user.session_version`. On mismatch, clear session and reject.

3. **Browser session cookie** — `session["user_id"]` + `session["auth_source"]` = `"browser_session"`. Verify user is active and session version matches.

4. **Bearer token** — `Authorization: Bearer <token>` header; SHA-256 hash compared to `users.api_token_hash`. Optional IP allowlist check (`allowed_ips` JSON column).

5. **Anonymous** — No credentials; unauthenticated.

#### Login flows

- **Email + password**: POST `/auth/login` with `{ email, password }`. `verify_password()` checks `password_hash` (werkzeug PBKDF2-HMAC) then falls back to `api_token_hash` comparison. On success, `_set_browser_session()` sets a 14-day permanent cookie.

- **Google OAuth**: GET `/auth/oauth/google` initiates Authlib OAuth2 flow with `google_sub` stable user ID. Callback at `/auth/oauth/google/callback` finds or creates a user by `google_sub`. If an invite token is embedded in OAuth state, it is consumed and the user is linked to the inviting household. Session set via `_set_browser_session()`.

- **QR Login**: POST `/auth/qr-login-link` creates a one-time `AccessLink` with purpose `login_qr` (60-minute expiry, stored as SHA-256 hash). GET `/auth/qr-login/<token>` redeems it and sets a browser session. GET `/auth/qr-image` returns a PNG QR code for the current user's login link.

- **Invite flow**: POST `/auth/invites` creates an `AccessLink` with purpose `invite`. GET `/auth/invite/<token>` redirects to frontend; the frontend hits an auth endpoint to consume the token and auto-login the new member.

#### Device pairing flow

1. New device: POST `/auth/device-pairing/start` with `{ device_name, scope }` → generates a 10-minute pairing token; stores `DevicePairingSession` (status=`pending`).
2. Admin browser: GET `/auth/pair-device/<token>` — admin sees pairing request UI.
3. Admin approves: POST `/auth/device-pairing/approve` → creates `TrustedDevice` with a new `token_hash`; updates `DevicePairingSession` status to `approved`.
4. New device polls: GET `/auth/device-pairing/status/<token>` until status = `approved`.
5. New device claims: GET `/auth/device-pairing/claim/<token>` → returns the one-time device token (only deliverable once; status → `claimed`).
6. New device stores token; uses `X-Trusted-Device-Token` header for all future requests.

#### Trusted device scopes

Three scopes gate what a trusted device can do:
- `shared_household` — full read + write access
- `kitchen_display` — read-only view of inventory/kitchen
- `read_only` — all writes rejected by `require_write_access` decorator

#### FERNET-encrypted secrets

`FERNET_SECRET_KEY` env var is used by `route_ai_inference.py` to encrypt/decrypt `ai_model_configs.api_key_encrypted` at rest, and by `plaid_integration.py` to encrypt/decrypt `plaid_items.access_token_encrypted`. Loss of `FERNET_SECRET_KEY` renders all stored AI API keys and Plaid access tokens unrecoverable (key and database must be backed up together).

#### Session security

- Cookie: `HttpOnly=True`, `SameSite=Lax`, `Secure` controlled by `SESSION_COOKIE_SECURE` env (must be `0` on plain-HTTP LAN dev). Lifetime: 14 days (`PERMANENT_SESSION_LIFETIME`).
- `session_version` column on `User` allows server-side session invalidation for all sessions of a user simultaneously (increment version → all existing cookies rejected).

#### Demo mode

Demo mode is **client-side only** — there is no demo user in the database. The frontend detects a `guest_demo` session state set by the login page when the user clicks "Try Demo". All write API calls are intercepted client-side and display a "Demo mode — sign in to save" message without making the actual request. The read calls still hit the real server. [UNCONFIRMED: whether a seeded demo dataset is loaded server-side, or whether the existing household data is displayed; the frontend code suggests it uses real data with write gates only.]

#### Logout

POST `/auth/logout` calls `_clear_auth_session()` which removes `user_id`, `trusted_device_id`, `auth_source`, and `session_version` from the Flask session.

---

### 1.7 BUSINESS RULES & DOMAIN LOGIC

#### 1. Household scoping

**Where**: All backend query functions (e.g. `manage_inventory.py`, `calculate_spending_analytics.py`, `manage_shopping_list.py`)
**What**: There is no `household_id` column. Instead, all data is logically scoped to a single shared household — all authenticated users see all data. Data isolation is at the deployment level (one SQLite per deployment). The `user_id` / `attribution_user_id` columns on purchases and receipt items track *who scanned what* for contribution scoring but do not filter visibility.
**macOS implication**: The macOS app inherits this model — all household members share one view of data. User identity matters for attribution/contribution, not for data access.

#### 2. Roles (admin/member/service)

**Where**: `create_flask_application.py` (`require_auth`, `require_write_access`), `manage_authentication.py` (`is_admin()`)
**What**:
- `admin` role: full access to all endpoints including user management, AI model admin, Plaid linking, service account creation.
- `user` role (also called "member"): read + write to all household data; cannot manage users, AI model configs, or service accounts.
- `service` role: Bearer-token-only accounts for integrations (e.g. smart mirror display). Read-only by default (`allow_write=False`); writes require explicit `allow_write=True`.
- Trusted device `read_only` scope: write operations rejected at `require_write_access` decorator regardless of user role.
**macOS implication**: The macOS app must gate admin-only UI sections (user management, AI model admin, backup/restore) behind a role check from `/auth/me`.

#### 3. OCR retry / re-run model selection

**Where**: `handle_receipt_upload.py`, `extract_receipt_data.py`, `route_ai_inference.py`
**What**: The multi-model OCR pipeline supports Gemini, GPT-4o, Claude Sonnet, and Ollama. User selects the model before or after initial OCR. Re-run OCR applies to a saved receipt: the server re-processes the stored image with the newly selected model and returns a diff. The client shows new vs existing items; the user accepts or discards each new item. Existing items are never auto-deleted by a re-run. Landscape photos are auto-rotated server-side by Pillow.
**macOS implication**: File upload via NSOpenPanel; the diff UI is a key interaction to replicate natively.

#### 4. Receipt → inventory write rules

**Where**: `extract_receipt_data.py` (`classify_line_kind()`), `manage_inventory.py`
**What**: Only receipt items with `kind = "product"` are written to inventory. Items classified as `discount`, `fee`, `tax`, `tip`, `membership`, `shipping`, `deposit`, `service_charge`, `summary`, or `other` are preserved in `receipt_items` for analytics but skipped by inventory writes. Products with `is_non_product=True` (fees, discounts, taxes, membership IDs) are kept in the product catalog for analytics but never surfaced in inventory or kitchen views. Stock quantity increments (or is initialized) when a grocery receipt is confirmed.
**macOS implication**: Inventory list must filter `is_non_product` products. Re-run OCR diff must correctly show which items will affect inventory.

#### 5. Bill projection cadence logic

**Where**: `bill_cadence.py`
**What**: Bills have a `billing_cycle` field: `monthly`, `bimonthly`, `quarterly`, `semiannual`, or `annual`. The `month_matches_billing_cycle(target_month, anchor_month, billing_cycle)` function determines whether a given calendar month is a payment month for a given bill. The interval is computed as months-since-anchor modulo the cycle length. If `interval=1` (monthly), every month matches. Bills are projected/expected only in their matching months.
**macOS implication**: The macOS bills screen must apply the same cadence logic when showing "expected this month" vs "not due this month" for obligations.

#### 6. Plaid match tolerance

**Where**: `plaid_receipt_matcher.py`
**What**: Fuzzy duplicate detection between Plaid staged transactions and existing Purchase rows uses:
- Amount tolerance: |Δamount| ≤ $0.02 (cent-level match, `AMOUNT_EPSILON`)
- Date tolerance: ±3 days (`DATE_WINDOW_DAYS`) to account for authorization vs posting date drift
- Merchant matching: lowercase normalization + punctuation removal + token overlap (min 4 chars) + a hardcoded `MERCHANT_ALIASES` table mapping card descriptors to canonical names (e.g. "claude.ai" → "anthropic", "amzn mktp" → "amazon")
**macOS implication**: This logic lives entirely server-side. The macOS client simply calls `/plaid/staged-transactions/<id>/confirm` and the server runs the match. No client-side matching needed.

#### 7. Contribution event scoring

**Where**: `contribution_scores.py`, called from `manage_inventory.py`, `handle_receipt_upload.py`, `manage_shopping_list.py`
**What**: Contribution points are awarded for specific events via `SCORE_RULES`:
- `receipt_processed`: 5 pts (receipt saved as purchase)
- `ocr_cleanup`: 20 pts (product review resolved with meaningful fix)
- `inventory_low_cleared`: 3 pts (cleared low flag after restock)
- `inventory_location_updated`: 2 pts (moved item to different storage location)
- `shopping_item_added`: 1 pt
- `shopping_item_purchased`: 2 pts
- `low_workflow_validated`: 5 pts (low-stock mark confirmed by shopping activity + later receipt)
- `low_peer_confirmed`: 2 pts (another household member agrees item is low)
- `recommendation_accepted`: [UNCONFIRMED — value not seen in read snippet]
Points accumulate in `contribution_events` table. Monthly leaderboard is derived by summing events in the current calendar month.
**macOS implication**: Contribution events are written server-side automatically; the macOS app only needs to display the leaderboard and per-member history, not compute points.

#### 8. Shopping nudge schedule

**Where**: `shopping_nudge_job.py`, `schedule_daily_recommendations.py` (APScheduler)
**What**: The shopping nudge fires daily at 09:30 via APScheduler. Eligibility criteria: `SHOPPING_NUDGE_ENABLED=true` env, at least `SHOPPING_NUDGE_MIN_RECS` (default 8) low-stock recommendations exist, the chat does not have an active in-progress walk, the chat is not muted (`nudge_muted_until`), and the last nudge was sent more than `NUDGE_GAP_DAYS` (default 3) days ago. The nudge is sent as a Telegram message with "Start walk" / "Later" inline keyboard buttons.
**macOS implication**: The nudge is entirely server-side (APScheduler → Telegram bot). The macOS app does not need to implement scheduling or push. However, the macOS app should provide a way to configure `TELEGRAM_AUTHORIZED_CHAT_IDS` and `SHOPPING_NUDGE_ENABLED` via Settings.

#### 9. Receipt attribution

**Where**: `manage_authentication.py` (serialize_user), `handle_receipt_upload.py`, `extract_receipt_data.py`, `calculate_spending_analytics.py`
**What**: Purchases have `user_id` (who scanned) and `attribution_user_id` / `attribution_user_ids` (JSON array) / `attribution_kind` fields. Attribution can be `"household"` (shared cost), `"personal"` (single user), or `"split"` (custom split). The dashboard shows a nudge if receipts have unset attribution. Analytics supports Spending by Person view (admin-only: exposes per-person totals which reveal household finances; non-admin users see only their own spending).
**macOS implication**: Attribution picker must be preserved. Spending by Person must be admin-gated.

#### 10. Demo mode read-only enforcement

**Where**: `src/frontend/index.html` (client-side) — no server-side demo user
**What**: Demo mode is a client-side-only state. When the user clicks "Try Demo" on the login page, the frontend sets a local flag (`guest_demo`). The `guest-demo-banner` is revealed showing a yellow read-only banner. All write-action buttons display a toast "Demo mode — sign in to save" instead of calling the API. Read endpoints are called normally, showing the current household's real data (or an empty state if the server has no data).
**macOS implication**: The macOS app must implement a demo mode UI gate — probably showing a banner and suppressing write calls. Since there is no server-side demo user, this is purely UI logic.

#### 11. Chat guardrails

**Where**: `chat_guardrails.py`, `chat_endpoints.py`
**What**: Two-pass filter runs synchronously before and after any LLM call:
- **Input blocklist** (`screen_input()`): 14 regex patterns block password queries, credential exfiltration, SQL injection, prompt injection, cross-user data requests, privilege escalation, and PII queries. Returns `(allowed=False, reason)` on match; caller skips LLM call entirely.
- **Output scrubber** (`scrub_output()`): 7 regex patterns detect leaked secrets in LLM output (OpenAI-style keys, Google API keys, AWS access keys, Slack tokens, GitHub tokens, private key PEM blocks, Fernet keys). On match, the entire reply is replaced with a refusal template.
- **Rate limiting**: In-memory sliding-window rate limiter (threading.Lock + deque per user) prevents abuse. [UNCONFIRMED: exact window size and limit not read.]
**macOS implication**: Guardrails run server-side. The macOS app sends the user message to `/chat` and displays the response; no client-side guardrails needed. However, the SSE streaming response must be correctly handled.

---

### 1.8 COMPLEXITY FLAGS FOR DESKTOP PORTING

| Feature | Web Implementation | macOS Challenge | Notes |
|---|---|---|---|
| **OCR file upload** | HTML `<input type="file">` with drag-drop; accepts JPEG, PNG, HEIC, PDF | Native `NSOpenPanel` with allowed file types + file drop from Finder via `NSDraggingDestination` | HEIC is natively supported on macOS; PDF handled server-side |
| **Camera capture** | `getUserMedia` (mobile browsers) | Continuity Camera (macOS 13+) via `AVCaptureDevice`; or skip and rely on file upload since desktop users rarely point cameras at receipts | Continuity Camera is the native equivalent for iPhone-as-webcam on M-series Macs |
| **QR code generation** | Server returns PNG via `/auth/qr-image`; also inline `qrcode.js` in web | `CoreImage.CIQRCodeGenerator` for in-app QR display; image can also be fetched from the same server endpoint | QR images for login and shopping list share — both have server endpoints |
| **QR code scanning** | JS QR lib in browser for scanning shared shopping list QR | `AVFoundation` / `Vision.VNDetectBarcodesRequest` for camera-based scan, OR just open the URL from the QR image directly | Shopping helper QR opens `/shopping-helper/<token>` URL — macOS can open via `NSWorkspace.open()` |
| **WebSocket / SocketIO** | Flask-SocketIO (limited use) | `URLSessionWebSocketTask` or keep as-is via WKWebView passthrough | SocketIO is available but not the primary data channel; if used only for real-time inventory updates, URLSession streaming suffices |
| **MQTT** | Backend publishes only; no client MQTT | No client MQTT needed | IoT push is server-initiated and not surfaced in the client UI |
| **Telegram bot** | Backend handles webhook, conversation state, and APScheduler nudges | macOS app does not need Telegram libs | All Telegram interaction is server-side; macOS app only configures the bot token and chat ID via Settings |
| **Plaid Link SDK** | Plaid Link JS SDK in web (OAuth popup flow) | Plaid Link SDK is iOS-compatible; macOS (Catalyst or native) can use it, OR use `WKWebView` to host the Plaid Link URL | Plaid access token exchange happens server-side; the macOS app only needs to initiate the Link flow and handle the redirect |
| **AI Chat streaming (SSE)** | `fetch()` with `text/event-stream`, chunked response, rendered token-by-token | `URLSession` data task with streaming delegate (`URLSessionDataDelegate.urlSession(_:dataTask:didReceive:)`) or `AsyncBytes` | Flask sends `text/event-stream`; parse `data: <chunk>` lines and append to message view |
| **Sankey chart / Spending drill-down** | Vega-Lite / D3 rendered in `<canvas>` or `<svg>` in the web view | Native `SwiftCharts` (macOS 13+) for bar/line charts; Sankey has no SwiftCharts equivalent — options: custom `Canvas` drawing, embed WebView for this one chart, or use a third-party Swift chart lib | SwiftCharts covers bar, line, area, pie; Sankey requires custom implementation or a web-rendered component |
| **Spending by Category bar charts** | D3 / vanilla canvas | `SwiftCharts.BarChart` — straightforward | Category breakdown is standard horizontal bar chart |
| **Inline rename of fixed-bill obligations** | `contenteditable` or `<input>` with `blur`/`Enter` save-on-blur | `NSTextField` in-place edit with `controlTextDidEndEditing` delegate | Must preserve the exact UX: click label → becomes editable → blur/Return → PATCH |
| **Image rotation for landscape receipts** | Server-side (Pillow); client just uploads | No change needed — the server handles rotation after upload | macOS app uploads the raw file; server rotates as needed |
| **Multi-model OCR model picker** | `<select>` dropdown pre-OCR + model switcher post-OCR | `NSPopUpButton` or SwiftUI `Picker` | Must show all enabled models from `/auth/config` or `/ai-models` |
| **Re-run OCR diff view** | Custom JS diff renderer showing new vs existing items | Custom SwiftUI list view with diff state: new items marked green, unchanged items neutral, removed items strikethrough | This is a key UX feature — the diff view must be faithfully reproduced |
| **Product image backfill (Open Food Facts)** | Admin-triggered via `/products/backfill-images` | No change needed — server-side only; admin can trigger from Settings or CLI | Images are stored on server filesystem and served via the receipts endpoint |
| **Session cookie auth on LAN** | Browser handles cookies automatically | `HTTPCookieStorage.shared` + `URLSession` with `httpCookieStorage` configured; must set `SESSION_COOKIE_SECURE=0` if connecting to HTTP LAN URL | See memory note: plain HTTP cannot receive Secure-flagged cookies; this is a dev/LAN concern |
| **Keychain for secrets** | `localStorage` used for `api_token` and `api_base` | Must use `Keychain Services` (SecItemAdd / SecItemCopyMatching) for any stored credentials — NOT `UserDefaults` | Per constraints: auth tokens, API base URL override must live in Keychain |
| **CSRF / SameSite cookie** | `SameSite=Lax` on cookie; browser enforces same-origin | `URLSession` sends cookies automatically from `HTTPCookieStorage`; no CSRF token needed for same-origin native client | macOS native client is not a browser — CSRF attacks don't apply; cookie jar handles auth transparently |
| **Trusted device pairing QR** | Admin sees QR in browser; new device polls | macOS app shows the QR image (from server PNG endpoint) and polls `/auth/device-pairing/status/<token>` | Pairing token display is the same as the web flow |
| **Demo mode** | Client-side flag; write calls intercepted in JS | SwiftUI must implement the same client-side gate: show demo banner, suppress write API calls | No server-side demo user; gate is entirely in the macOS app UI layer |
| **Backup/restore** | Admin UI in Settings calls `/system/backups/*` | Same REST endpoints; admin macOS UI must have the backup panel | Server runs shell scripts; client just triggers and polls |
| **Google OAuth** | Authlib server-side OAuth2; browser popup/redirect | `ASWebAuthenticationSession` for OAuth redirect flow; the server callback URL must be reachable from the macOS browser context | `ASWebAuthenticationSession` handles the OAuth popup and callback URL interception natively |
| **Contribution leaderboard** | Simple fetch + DOM rendering | SwiftUI `List` with sorted rows; straightforward | No special complexity |
| **Shopping list QR share** | Server generates `AccessLink`; QR displays in browser; helper URL opens in any browser | macOS can display QR (from server PNG endpoint) and open the helper URL in system browser | The helper URL `/shopping-helper/<token>` is a separate read-only web view served by the server |

---

### 1.9 ASSETS INVENTORY

**Fonts:**
The web app loads three Google Fonts families via a `<link>` tag in `index.html` line 34:
- **Inter** (weights 300–700) — body text, UI labels
- **Manrope** (weights 400–800) — UI elements
- **Fraunces** (optical sizes 9–144, weights 600–700) — display/hero headings

CSS variables `--font-display` and `--font-text` map to these families. The design system documentation within the app (line 6143) explicitly mentions "SF Pro Display ≥ 20 px, SF Pro Text < 20 px" as the native equivalent typographic system.

**macOS implication**: The macOS app should use **SF Pro** system fonts (which are already built into macOS) rather than loading Google Fonts. SF Pro Display = `--font-display` (headings), SF Pro Text = `--font-text` (body). No font files need to be bundled.

**Icons:**
- Emoji characters used extensively throughout the UI (e.g. 📸, 🛒, 📦, 💊, 🏅, 🔑)
- Unicode symbols (e.g. ✓, ⚠, ➗, ⚖️)
- A small number of inline SVG icons [UNCONFIRMED: exact SVG inventory not audited]
- No external icon font library (no Font Awesome, no Material Icons)

**macOS implication**: Emoji are fully supported in SwiftUI `Text` and `Image`. SF Symbols can supplement or replace many emoji for a more native feel — this is a design decision for Agent 3 (UI/UX). No icon font license needed.

**Images:**
- Receipt thumbnail images stored at `/data/receipts/<household>/...` on the server; served via the receipts API endpoint (authenticated)
- Product images fetched from **Open Food Facts** and stored on the server filesystem; backfilled by `manage_image_backfill.py`
- QR code PNGs generated on-the-fly by the server (`qrcode` library)
- No custom logo, splash screen, or marketing image assets in the codebase (the `design/` directory contains a UI kit HTML preview but no image files for the app itself) [UNCONFIRMED: design/ directory contents not fully audited]

**macOS implication**: All images are fetched from the Flask server over authenticated HTTP; the macOS app loads them via `URLSession` + `AsyncImage`. The macOS app bundle itself needs no bundled product or receipt images.

**Sounds / Haptics:**
None expected or observed in the codebase.

---

*End of Section 1 — PROJECT INVENTORY*

*Next: Section 2 authored by [AGENT 2 — PRODUCT MANAGER]*

---

## 2. PRODUCT STRATEGY
*Authored by: [AGENT 2 — PRODUCT MANAGER]*

### 2.1 PLATFORM DECISION

**Target**: macOS 13 Ventura+ on Apple Silicon (M1 and newer). This is the minimum OS required to access SwiftCharts (used throughout the Finance and Analytics domain), Continuity Camera (receipt scanning from iPhone), and the modern `NavigationSplitView` / `NavigationStack` APIs that make the 36-screen nav graph manageable without custom routing logic.

**Intel support**: Universal binary is a stretch goal (v1.1). The backend stays on a Linux server; the macOS app is a pure client. There is no architecture-specific code in the app itself, so a universal binary adds only build and CI complexity (lipo, Rosetta test matrix). Intel Macs running macOS 13+ can run the Rosetta 2 arm64 slice without user-visible degradation. Mark Intel as `[STRETCH v1.1]`.

**Distribution**: **Direct / Developer ID (notarized, not Mac App Store)**. Justification drawn from §1.8 complexity flags:

- The app must connect to a user-specified LAN server URL (e.g. `http://192.168.1.10:8090`). Mac App Store sandbox requires App Transport Security exceptions via entitlement; arbitrary LAN HTTP is not approvable without `com.apple.security.network.client` + ATS exception for private IP ranges — technically possible but approval is not guaranteed.
- The app stores the server URL in Keychain (§1.8, §1.6 auth constraint). This is fine on both distribution paths, but Keychain groups are simpler with a non-sandboxed Developer ID build.
- Plaid Link SDK integration (§1.8) requires `ASWebAuthenticationSession` + a callback URL scheme. This works under sandbox, but the Plaid redirect callback must be registered as a URL scheme — a minor friction point App Store review has historically questioned.
- MQTT and Telegram are backend-only (§1.8); they do not require entitlements in the macOS app.
- The target user base is a technical household running a self-hosted Docker stack. They are comfortable with Gatekeeper bypass (right-click → Open) and will not be deterred by App Store absence. Direct distribution via a signed `.dmg` is idiomatic for self-hosted tooling.

**App type**: **Standard windowed app (NSWindowController / SwiftUI WindowGroup) with a menu bar status icon as an enhancement**.

With 36 screens (§1.2) and rich data tables across 8 feature domains, a standard window is the only viable primary container. A menu bar–only app cannot accommodate the OCR diff view, Plaid staging review, spending drill-downs, or the AI Chat panel. The menu bar icon serves as a lightweight companion: quick-add cash transaction, quick-launch OCR upload, and show today's low-stock count badge. It does not replace the main window.

---

### 2.2 FEATURE PARITY MATRIX

*Status key: **FULL PARITY** = native equivalent of web screen, no features dropped. **ENHANCED** = desktop gains meaningful capabilities beyond the web screen. **MERGED** = folded into another native screen (reducing nav complexity). **DEFERRED** = present in web but not in v1.0 macOS. **REMOVED** = no native equivalent planned.*

| # | Screen (from §1.2) | macOS Status | Desktop Variant / Justification |
|---|---|---|---|
| 1 | Login / Onboarding | **FULL PARITY** | Email+password + Google OAuth via `ASWebAuthenticationSession`. QR Login rendered from server PNG endpoint. Keychain stores session cookie jar and server URL per §1.6 constraint. |
| 2 | Dashboard | **ENHANCED** | Three-column `NavigationSplitView`: sidebar (domain nav) + content (tiles/alerts) + detail (drill panel). Spending tiles update on foreground via background fetch. Attribution nudge surfaces as banner. |
| 3 | OCR Upload | **ENHANCED** | `NSOpenPanel` with `allowedContentTypes` [JPEG, PNG, HEIC, PDF]. Drag-from-Finder onto Dock icon or app window both trigger upload flow. Global shortcut ⌃⌘R opens upload from anywhere. Continuity Camera available as source picker option. |
| 4 | Review and Edit | **ENHANCED** | Native table view (`List` with inline `TextField`) for line items. Re-run OCR diff shown with SwiftUI color badges (green = new, amber = changed, neutral = unchanged). Keyboard navigation: Tab through fields, ⌘Return to confirm. |
| 5 | Re-run OCR | **FULL PARITY** | Model picker as `Picker` / `NSPopUpButton`. Diff view preserved (§1.8 flags this as a key interaction). Accept/discard per item with arrow keys + Space. |
| 6 | Receipt Types | **MERGED** | Merged into OCR Upload screen as a segmented control / `Picker` row; not a separate screen. Reduces nav depth. |
| 7 | Inventory | **ENHANCED** | Two-panel split: category sidebar + product list. Keyboard shortcuts: ⌘F to search, ⌥↑/↓ to adjust quantity, ⌘E to edit item. Drag row to reorder. Multi-select for bulk operations. |
| 8 | Shopping List | **ENHANCED** | Native list with checkbox rows (Space to toggle purchased). One-tap low-stock populate preserved. QR share opens native share sheet or copies link. ⌘N adds new item inline. |
| 9 | Recommendations | **MERGED** | Merged as a tab within the Shopping List screen (matches existing web tab pattern from §1.2). |
| 10 | Kitchen View | **FULL PARITY** | Grid layout by category using SwiftUI `LazyVGrid`. Tap item to add to shopping list. Compact view preserved for low-stock at-a-glance use. |
| 11 | Restaurant Workspace | **FULL PARITY** | Tabbed sub-navigation within the Restaurant domain: workspace, repeat orders, split, contacts, balances. |
| 12 | Repeat Orders | **FULL PARITY** | Read-only ranked list. Sortable by frequency, price, recency via column header click. |
| 13 | Dining Budget | **MERGED** | Merged as a card within Restaurant Workspace (matches existing web card pattern). Not a separate screen. |
| 14 | Expense Tracking | **FULL PARITY** | Recent expenses list with drag-from-Finder upload shortcut. |
| 15 | Category Tagging | **ENHANCED** | Auto-tag preserved. Keyboard shortcut ⌘T to open tag editor. Drag-to-reassign category via popover. |
| 16 | Expense Analytics | **ENHANCED** | `SwiftCharts.BarChart` for timeline and merchant frequency. Weekly/monthly toggle as segmented control. Keyboard ←/→ to step through months. |
| 17 | Spending by Category | **ENHANCED** | Native expandable `OutlineGroup` replaces accordion. Sankey chart: rendered in a `WKWebView` component (§1.8 — no SwiftCharts equivalent; web-rendered is the pragmatic choice). |
| 18 | Fixed Bills | **ENHANCED** | `NSTextField` in-place rename for obligation labels (§1.8). Calendar cadence indicator per bill (§1.7 rule 5). ⌘N to add obligation. Space bar to mark paid when row is focused. |
| 19 | Plaid Integration | **FULL PARITY** | `ASWebAuthenticationSession` for Plaid Link OAuth flow. Staged transaction review list with keyboard confirm/dismiss (Return / Delete). Admin-gated per §1.7 rule 2. |
| 20 | Cash Transactions | **FULL PARITY** | Native form with `DatePicker`, category `Picker`, amount `TextField`. |
| 21 | Split Bills | **FULL PARITY** | Contact picker list, amount fields per person, even-split toggle. |
| 22 | Contacts | **FULL PARITY** | Sorted list; tap to view per-contact meal history and running balance. |
| 23 | Balances and Settle | **FULL PARITY** | Debt list with settle-all button. Confirmation sheet before destructive settle. |
| 24 | Shopping Walk (Telegram) | **DEFERRED** | Telegram conversation flows are entirely server-side (§1.8). The macOS app surfaces the walk status (active/idle) and provides a "Start Walk" button that sends `/shopping` via the backend's trigger endpoint, but does not replicate the interactive walk UI — that remains in Telegram. |
| 25 | Inventory Walk (Telegram) | **DEFERRED** | Same rationale as Shopping Walk. Trigger button only. |
| 26 | Dining Walk (Telegram) | **DEFERRED** | Same rationale. Trigger button only. |
| 27 | Nudges (Telegram) | **DEFERRED** | APScheduler nudges are server-side (§1.7 rule 8). The macOS app surfaces nudge configuration (enabled toggle, minimum recs threshold) in Settings. Native Notification Center nudge is a §2.3 desktop-exclusive enhancement, not a parity item. |
| 28 | Auth and Members | **ENHANCED** | Admin-gated role indicator in member list. Invite flow uses `NSPasteboard` copy of invite link + native share sheet. QR login image displayed in popover. |
| 29 | Contributions | **FULL PARITY** | Monthly leaderboard as `List` sorted by points. Per-member drill-in shows event history with timestamps. |
| 30 | Demo Mode | **FULL PARITY** | Client-side gate (§1.7 rule 10). Yellow banner at top of window. All write-action buttons suppressed with inline tooltip "Demo mode — sign in to save". |
| 31 | AI Chat | **ENHANCED** | SSE streaming response via `URLSession` `AsyncBytes` (§1.8). Chat panel opens as a sidebar or floating panel (⌘⌥C). Model picker persisted in Keychain. Admin-gated in v1 per §1.7 rule 2. |
| 32 | Medications | **FULL PARITY** | Medication list with expiry date `DatePicker`, quantity stepper. Barcode lookup via camera (Continuity Camera) or manual entry. Refill alert fires as native Notification Center notification. |
| 33 | Features Documentation | **REMOVED** | This is a marketing/onboarding static HTML page (§1.2). It has no functional equivalent in a native app; onboarding is handled by the first-launch setup flow instead. The URL `features.html` remains accessible in the server's web browser. |
| 34 | Settings | **ENHANCED** | `NSTabView` / SwiftUI `TabView` with panes: Account, AI Models, Trusted Devices, Telegram, Backup & Restore, About. Admin-only panes hidden for non-admin users. Backup/restore calls `/system/backups/*` endpoints. |
| 35 | Products Catalog | **FULL PARITY** | Search + review queue. Admin-gated bulk edit and image backfill trigger. |
| 36 | Household Budget | **FULL PARITY** | Budget entry per domain/month. Change log in expandable section. |

*Summary: FULL PARITY: 20 screens. ENHANCED: 10 screens. MERGED: 3 screens (Receipt Types → OCR Upload; Recommendations → Shopping List; Dining Budget → Restaurant Workspace). DEFERRED: 4 screens (Telegram Walks × 3 + Nudges). REMOVED: 1 screen (Features Documentation page).*

---

### 2.3 DESKTOP-EXCLUSIVE FEATURES

These features do not exist in the web app and are unique to the native macOS experience. They are ordered by priority for v1.0 inclusion.

| # | Feature | Priority | Reason and Implementation Notes |
|---|---|---|---|
| 1 | **Global shortcut ⌃⌘R — Receipt Upload from anywhere** | v1.0 | The single biggest productivity win. A user who just photographed a receipt can trigger OCR upload without switching focus. Registered as a system-wide hotkey via `CGEventTap` or `MASShortcut`-pattern. Opens the main window to OCR Upload if not already open. Most directly competes with the web app's "open browser tab" friction. |
| 2 | **Drag receipt from Finder onto Dock icon or app window** | v1.0 | Native `NSDraggingDestination` on `AppDelegate` + `NSApplicationDelegate.application(_:open:)` for Dock drops. Accepts JPEG, PNG, HEIC, PDF per §1.8 complexity flag. Drops trigger the OCR Upload flow with the file pre-filled. Zero friction for users who manage receipt PDFs in Finder folders. |
| 3 | **Menu bar status icon with quick actions** | v1.0 | A persistent `NSStatusItem` in the macOS menu bar provides always-visible low-stock count badge (e.g. "🛒 8"). Dropdown menu: Quick Add Cash Transaction (inline amount + category entry), Open Receipt Upload, Open Shopping List, Open App. This puts household finance housekeeping one click away without switching to the main window. |
| 4 | **Notification Center — shopping nudge and refill alerts** | v1.0 | The Telegram nudge (§1.7 rule 8, §1.2 screen 27) fires at 09:30 server-side — but only to users with Telegram configured. The macOS app replaces or supplements this with a native `UNUserNotificationCenter` notification at 09:30 local time (delivered even if the server has no Telegram config). Also fires native notifications for medication refill alerts (§1.2 screen 32) and Plaid login-required status. `UNNotificationAction` "Start Walk" deep-links into the Shopping List screen. |
| 5 | **Continuity Camera — scan receipt from iPhone** | v1.0 | macOS 13+ `AVCaptureDevice.DiscoverySession` with `continuityCamera` device type. Appears automatically as a camera source in the OCR Upload model picker when an iPhone is on the same Wi-Fi network. No setup required by the user. Directly replaces the web app's `getUserMedia` mobile capture (§1.8) with a superior quality capture path. |
| 6 | **Multi-window — Inventory + Shopping List side by side** | v1.0 | `Scene` / `WindowGroup` in SwiftUI supports multiple simultaneous windows. Use case: user walks the pantry on MacBook (Inventory window) while maintaining a Shopping List window open on an external display. Implemented as File → New Window (⌘N at app level) with a window type picker. The most common multi-window combination is Inventory + Shopping List; Analytics + Fixed Bills is the second most common. |
| 7 | **Touch ID / Apple Watch unlock for sensitive views** | v1.1 | Plaid accounts panel and Balances & Settle screen contain sensitive financial data. `LocalAuthentication.LAContext.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics)` prompt before opening these views. Shown as an interstitial "Authenticate to view your accounts" sheet. Non-blocking — user can dismiss and the view stays hidden. Adds meaningful privacy protection for shared Macs. |
| 8 | **Native Share sheet for receipt export** | v1.1 | `NSSharingServicePicker` or SwiftUI `.shareLink` on the receipt detail view. Shares the receipt image (PNG served from server) + a formatted expense summary as plain text or PDF. AirDrop to iPhone, email to accountant, Messages to household member are the primary share targets. |
| 9 | **Native Open/Save panels for CSV export** | v1.0 | Expense Analytics and Spending by Category include export actions. Web app forces a browser download. macOS app uses `NSSavePanel` with suggested filename `spending-<YYYY-MM>.csv` and type `public.comma-separated-values-text`. Cleaner than a browser download folder. |
| 10 | **Spotlight integration — index inventory items and receipts** | v1.1 | `CoreSpotlight.CSSearchableItem` with domain identifiers `com.localocr.inventory.<product_id>` and `com.localocr.receipt.<purchase_id>`. Index product names, store names, and receipt dates. Allows "Command-Space → bread → Enter" to jump to the Inventory item for bread. Requires background indexing task on app launch. |
| 11 | **Quick Look extension for receipt images** | v1.1 | A `QLPreviewingController` extension registered for the server-image URL scheme or for locally cached receipt images. Allows Spacebar preview of receipts in the app's receipt list without opening the full edit panel. Lightweight to implement; high perceived value for power users. |
| 12 | **iCloud Drive sync for receipt photos (offline capture queue)** | v1.1 | An offline capture queue in `NSUbiquitousKeyValueStore` or a dedicated iCloud Container: photos taken when the server is unreachable are queued and uploaded when connectivity resumes. This is the one scenario where the self-hosted backend's unavailability (server off, LAN disconnect) would otherwise lose work. Scope-controlled: the queue only stores image files, not any parsed data. |

---

### 2.4 MVP SCOPE — v1.0

The v1.0 minimum-viable experience must deliver two things that the web app cannot: **drag-from-Finder OCR upload** and **native window management** for the household's most-used daily flows. It must not ship without full preservation of all 11 business rules (§1.7).

**Design principle for scope decisions**: If removing a screen would break a §1.7 business rule or leave a user unable to complete a core household management task, it is IN-SCOPE. If it is a power feature, analytics enhancement, or Telegram-specific workflow, it is v1.1+.

#### IN-SCOPE for v1.0 (core screens and features — approximately 16 screens)

| Screen / Feature | Rationale |
|---|---|
| Login / Onboarding (screen 1) | Required to authenticate; Keychain constraint from §1.6. |
| Dashboard (screen 2) | Entry point; surfaces attribution nudge (§1.7 rule 9), low-stock count, spending tiles. |
| OCR Upload (screen 3, enhanced) | Primary desktop win: drag-from-Finder + global shortcut ⌃⌘R. Core user journey anchor. |
| Review and Edit (screen 4) | Inseparable from OCR Upload — same flow step. Required to preserve §1.7 rule 4 (inventory write rules). |
| Re-run OCR (screen 5) | Required per §1.7 rule 3 (OCR retry / model selection). Without it, the user has no recourse for a bad OCR result. |
| Inventory (screen 7, enhanced) | Core household management. Low-stock detection feeds shopping list (§1.7 rule 8). |
| Shopping List (screen 8, enhanced) | Core household management. QR share preserved (serves the phone-based helper). |
| Recommendations (screen 9, merged into Shopping) | Required to trigger low-stock populate (§1.7 rule 8 depends on recommendations). |
| Kitchen View (screen 10) | Fast at-a-glance for meal planning; low implementation cost once inventory is done. |
| Fixed Bills (screen 18, enhanced) | §1.7 rule 5 (bill cadence logic) requires this to be correctly implemented. |
| Plaid Integration (screen 19) | §1.7 rule 6 (Plaid match tolerance) — without this, bank transactions are never reconciled. |
| Cash Transactions (screen 20) | Required to feed spending analytics for cash-paid bills. |
| Auth and Members (screen 28) | Required for household role gating (§1.7 rule 2) and invite flow. |
| Contributions (screen 29) | Required to preserve §1.7 rule 7 (contribution scoring); leaderboard motivates household participation. |
| Demo Mode (screen 30) | Required per §1.7 rule 10 — must not ship without the client-side gate. |
| Settings (screen 34, enhanced) | Required for server URL, AI model config, trusted device pairing, and Telegram config. |
| **Desktop-exclusive v1.0 features** | Global shortcut ⌃⌘R, Drag-from-Finder OCR upload, Menu bar status icon, Notification Center nudges, Continuity Camera, Multi-window, Native CSV Save panel. |

#### OUT-OF-SCOPE — v1.1+

| Screen / Feature | Version | Rationale |
|---|---|---|
| Expense Tracking (screen 14) | v1.1 | Valuable but not on the critical path; web app handles it. |
| Category Tagging (screen 15) | v1.1 | Analytics enhancement; read-side works from web. |
| Expense Analytics (screen 16) | v1.1 | Chart work (SwiftCharts + Sankey) is non-trivial; deferring avoids shipping with a placeholder. |
| Spending by Category (screen 17) | v1.1 | Same chart scope as Analytics. |
| Restaurant Workspace (screen 11) | v1.1 | Dining features are secondary to grocery/finance flows. |
| Repeat Orders (screen 12) | v1.1 | Read-only; no household risk if deferred. |
| Split Bills (screen 21) | v1.1 | Shared dining is a secondary domain. |
| Contacts (screen 22) | v1.1 | Required only once Split Bills lands. |
| Balances and Settle (screen 23) | v1.1 | Required only once Split Bills lands. |
| AI Chat (screen 31) | v1.1 | SSE streaming implementation adds scope; web app fully functional. |
| Medications (screen 32) | v1.1 | Self-contained domain; no dependency on other v1.0 screens. |
| Products Catalog (screen 35) | v1.1 | Admin power feature; web app handles it. |
| Household Budget (screen 36) | v1.1 | Valuable but not on the critical path. |
| Telegram Walk triggers (screens 24–27) | v1.1 | Server-side; trigger buttons are minor; defer until Telegram config in Settings is shipped and tested. |
| Touch ID unlock | v1.1 | Security enhancement; not MVP. |
| Share sheet (receipt export) | v1.1 | Enhancement; web download works. |
| Spotlight integration | v1.1 | Background indexing; deferred to keep v1.0 focused. |
| Quick Look extension | v1.1 | Extension bundle; extra review surface. |
| iCloud offline capture queue | v1.1 | No data loss risk if server is reachable on LAN; defer until offline scenarios are validated. |
| Intel universal binary | v1.1 | Not blocking for the target user base. |
| Features Documentation page (screen 33) | REMOVED | No native equivalent; marketing page stays in web. |

---

### 2.5 USER JOURNEY MAPS — DESKTOP

Four primary user types with critical desktop paths. Each step includes: what the user does → what they see → what keyboard shortcut is available → what error states look like.

---

#### Journey 1: Daily Inventory Walker

**User goal**: See what's low → add to shopping list → done in under 60 seconds.

**Cold launch → low-stock → add to list → quit**

| Step | User action | What they see | Keyboard path | Error states |
|---|---|---|---|---|
| 1 | App cold launch | Splash screen (< 2 sec), then Dashboard with spending tiles and low-stock alert banner | — | If server unreachable: "Cannot connect to [host]" banner with retry button and Settings link |
| 2 | See low-stock count | Dashboard shows "8 items low" badge in Low Stock tile | ⌘1 (if Dashboard is tab 1) | If auth expired: redirected to Login sheet |
| 3 | Navigate to Inventory | Click "View inventory" in tile or click Inventory in sidebar | ⌘2 or sidebar click | — |
| 4 | Scan low items | Inventory list filtered to "Low" by default; items highlighted amber | ⌘F to search; ↑/↓ to move between items | If inventory load fails: "Failed to load inventory" with retry button |
| 5 | Add item to shopping list | Click "+" badge on item row | Select row with ↑/↓, press ⌘L (add to list) | If item is already on list: shows "Already on shopping list" tooltip on the "+" badge |
| 6 | Confirm shopping list count | Menu bar icon badge updates to reflect new item count | ⌘3 to jump to Shopping List | — |
| 7 | Quit | Cmd+Q | The app hides to menu bar (does not terminate); press ⌘Q again or choose Quit from menu bar dropdown to fully quit | — |

**Mouse path**: Dashboard tile → "View Inventory" button → Low filter chip already active → click "+" on row → badge in menu bar updates.

---

#### Journey 2: Receipt Uploader

**User goal**: Upload a receipt PDF from Finder → OCR it → review → confirm → done.

**Three entry paths: drop on Dock, drop in app, ⌘O via File menu**

| Step | User action | What they see | Keyboard path | Error states |
|---|---|---|---|---|
| 1a (Dock drop) | Drag PDF from Finder and drop on Dock icon | App comes to front; OCR Upload panel opens with file pre-filled in drop zone | — | If file type not accepted (e.g. .docx): "Unsupported file type. Accepted: JPEG, PNG, HEIC, PDF" |
| 1b (in-app drop) | Drag PDF from Finder onto the app window | Drop zone highlights with dashed blue border; drop → file name shown in drop zone | — | Same as above |
| 1c (⌘O) | Press ⌃⌘R (global shortcut) or File → Open Receipt (⌘O) | `NSOpenPanel` opens filtered to JPEG/PNG/HEIC/PDF | ⌃⌘R from anywhere | If app is not running: app launches first, then panel opens |
| 2 | Select AI model | `Picker` showing enabled models (fetched from `/ai-models`); default is user's `active_ai_model_config_id` from Keychain | ⌘↑/↓ to change model in picker | If no models enabled: "No AI models configured — go to Settings → AI Models" |
| 3 | Submit | "Run OCR" button; spinner begins; status label shows "Processing with [model name]…" | ⌘Return to submit | If server returns error: OCR error message with model name and raw error string; "Try different model" shortcut button shown |
| 4 | Review OCR result | Review and Edit screen: store, date, total at top; line items list below; receipt photo in right panel (rotated if landscape per §1.7 rule 3) | Tab to move between fields; ⌘Return to confirm | If photo fails to load: broken image placeholder; "Reload photo" button |
| 5 | Edit line items | Click item row to expand inline editor; adjust quantity, price, kind | Tab through fields within row; Esc to cancel edit; Return to save row | If an item has `kind=product` but `product_id` is null: amber warning icon "Product not matched — will be created" |
| 6 | Confirm | "Confirm Receipt" button; receipt saved; inventory incremented per §1.7 rule 4 | ⌘Return | If server returns validation error (e.g. duplicate purchase): "A receipt from [store] on [date] for [amount] already exists — confirm duplicate?" sheet with "Save Anyway" / "Cancel" |
| 7 | Attribution | Attribution picker sheet (§1.7 rule 9): Household / Personal / Split options | ⌘1/2/3 for quick selection | If dismissed without attributing: contribution nudge banner shown on Dashboard next launch |

---

#### Journey 3: Bill Paywatcher

**User goal**: Open app → check which fixed bills are due → mark paid → inline rename → close window.

| Step | User action | What they see | Keyboard path | Error states |
|---|---|---|---|---|
| 1 | Open app or switch to Finance domain | Sidebar shows Finance domain; click "Fixed Bills" entry | ⌘4 (if Finance is tab 4 in sidebar) | If auth expired: Login sheet |
| 2 | View bills | Fixed Bills list showing each obligation, expected amount, payment status (paid/pending/overdue), billing cycle month indicator per §1.7 rule 5 | ↑/↓ to navigate rows | If bills fail to load: "Failed to load bills" with retry |
| 3 | Identify unpaid bill | Unpaid bills shown with amber dot; overdue with red dot | — | — |
| 4 | Mark as paid | Select row with arrow keys or click | Space bar to mark paid (toggle) | If already paid: Space toggles back to unpaid (with confirmation sheet: "Mark [bill] as unpaid?") |
| 5 | Inline rename obligation | Double-click on obligation label | Label becomes an editable `NSTextField`; cursor positioned at end | Return or Tab to save; Esc to cancel | If name conflicts with existing obligation: "An obligation named '[name]' already exists" inline error |
| 6 | Link to Plaid transaction | "Link transaction" button on row | Staged transactions popover showing fuzzy-matched candidates per §1.7 rule 6 | Return to confirm match; Esc to dismiss | If no Plaid match within tolerance: "No matching Plaid transaction found" with manual-confirm option |
| 7 | Close window | ⌘W | Window closes; app continues running in menu bar | ⌘W | — |

---

#### Journey 4: Analyst

**User goal**: Spending by Category → drill into top category → export CSV.

| Step | User action | What they see | Keyboard path | Error states |
|---|---|---|---|---|
| 1 | Open Spending by Category | Click Analytics in sidebar; select "Spending by Category" tab | ⌘5 (if Analytics is tab 5) | If data fails to load: "Failed to load analytics" with retry |
| 2 | View category breakdown | Horizontal bar chart (SwiftCharts) with categories ranked by total spend; current month shown by default | ← / → to step through months; ⌘⌥S to open Sankey (WKWebView panel) | If no data for selected month: "No spending data for [month]" empty state |
| 3 | Drill into a category | Click bar or category row label | Drill-down panel slides in from right (NavigationSplitView detail column): list of receipts in that category, store names, amounts, dates | Return to open drill panel when row is focused | — |
| 4 | Filter by sub-category | Click sub-category chip (e.g. "Grocery", "Restaurant") | Chart filters to show only selected domain's breakdown | ⌘1/2/3 for domain chips | — |
| 5 | Export CSV | "Export" button in toolbar | `NSSavePanel` opens with suggested filename `spending-<YYYY-MM>.csv` and pre-selected Downloads folder | ⌘S while Analytics is active (if no unsaved form changes) | If server CSV endpoint returns error: "Export failed" alert with details; retry button |
| 6 | Open in Numbers / Excel | After save, Finder notification banner "spending-2026-05.csv saved" | Click banner to open file in default CSV app | — | — |

---

### 2.6 ACCEPTANCE CRITERIA — PRODUCT LEVEL

The following criteria are binary pass/fail. All 18 must pass before v1.0 ships.

- [ ] **AC-01** — App launches in < 2 seconds on M1 Mac (cold start), measured from Dock click to Dashboard first render with a warm server.
- [ ] **AC-02** — All 11 business rules from §1.7 are preserved end-to-end: household scoping, role gating, OCR retry, receipt → inventory write rules, bill cadence, Plaid match tolerance, contribution scoring, shopping nudge schedule, receipt attribution, demo mode gate, chat guardrails.
- [ ] **AC-03** — All keyboard shortcuts specified in §2.5 journey maps function correctly (⌃⌘R, ⌘Return, ⌘W, ⌘F, Space to mark paid, arrow navigation in lists).
- [ ] **AC-04** — Dark mode and Light mode both render correctly with no unthemed (white on white or black on black) UI elements; tested by toggling macOS System Preferences appearance with the app running.
- [ ] **AC-05** — App passes notarization via `xcrun notarytool submit` and Gatekeeper quarantine check passes for a clean install on a Mac that has never launched the app.
- [ ] **AC-06** — Auth tokens (session cookie jar, server URL, AI model selection) are stored in Keychain Services via `SecItemAdd` / `SecItemCopyMatching`, never in `UserDefaults` or any plaintext plist.
- [ ] **AC-07** — Drag-from-Finder OCR upload works for all four accepted types (PDF, PNG, JPEG, HEIC) via three entry paths: drop on Dock icon, drop on app window, and `NSOpenPanel` via ⌃⌘R / File → Open Receipt.
- [ ] **AC-08** — Multi-household switching (changing the server URL in Settings) clears the current Keychain session and prompts for re-login, without requiring an app restart.
- [ ] **AC-09** — Background fetch refreshes Plaid staged transactions and inventory data when the app transitions from background to foreground (macOS `NSApplicationDelegate.applicationDidBecomeActive`); stale data is never silently presented.
- [ ] **AC-10** — Notification permission is requested via `UNUserNotificationCenter.requestAuthorization` before any notification is scheduled; if permission is denied, the app does not schedule notifications and shows a one-time banner in Settings with a deep-link to System Settings → Notifications.
- [ ] **AC-11** — VoiceOver navigates every v1.0 screen in a logical reading order; all interactive controls have non-empty `.accessibilityLabel` values; no VoiceOver trap (infinite loop or unreachable close button) exists.
- [ ] **AC-12** — ⌘W closes the current window without quitting the app; the menu bar status icon remains; the app fully quits only on ⌘Q confirmed or Quit from menu bar dropdown.
- [ ] **AC-13** — Demo mode read-only gate is enforced client-side: every write-action button displays "Demo mode — sign in to save" tooltip; no write API call is made from a demo session; the yellow "Demo Mode" banner is visible at all times during the demo session.
- [ ] **AC-14** — Receipt landscape-rotation is handled server-side (Pillow); the macOS app uploads raw files without pre-processing and displays the server-rotated image in the Review and Edit screen without a visible re-render jump.
- [ ] **AC-15** — Re-run OCR diff view correctly marks new items (green), changed items (amber), and unchanged items (neutral); accepting an individual new item calls the correct partial-accept API endpoint without affecting other items.
- [ ] **AC-16** — Attribution picker is shown after every receipt confirmation that lacks attribution; the picker correctly writes `attribution_kind`, `attribution_user_id`, and `attribution_user_ids` per §1.7 rule 9; Spending by Person view is hidden for non-admin users.
- [ ] **AC-17** — Bill cadence logic (§1.7 rule 5) is correctly reflected in the Fixed Bills screen: a quarterly bill shows as "Not due this month" in non-billing months and "Due this month" in billing months, matching the server's `month_matches_billing_cycle()` calculation.
- [ ] **AC-18** — Plaid Link OAuth flow completes via `ASWebAuthenticationSession`; the server-side access token exchange is triggered correctly; the app does not store or log any Plaid access token client-side.

---

*End of Section 2 — PRODUCT STRATEGY*

*Next: Section 3 authored by [AGENT 3 — UI/UX DESIGNER]*

---

## 3. DESIGN SYSTEM & VIEW SPECS
*Authored by: [AGENT 3 — macOS DESIGN LEAD]*

### 3.1 DESIGN TOKENS — macOS ADAPTED

The web app's CSS custom properties (§1.1) are mapped to macOS semantic NSColor / SwiftUI Color equivalents. Hardcoded hex values are used only for brand-specific tokens that have no semantic NSColor equivalent. All tokens support automatic Light/Dark adaptation unless a hex override is specified.

#### Colors

| Token | Light Mode Hex | Dark Mode Hex | NSColor / SwiftUI Semantic | Notes |
|---|---|---|---|---|
| `accent` | `#3b82f6` | `#3b82f6` | `.controlAccentColor` override; user can change in System Settings → Appearance | Brand blue; override the default system accent |
| `background` | `#ffffff` | `#111113` | `.windowBackgroundColor` | Main window canvas; do not hardcode — use NSColor.windowBackgroundColor for system consistency |
| `sidebar-bg` | `#f5f5f7` | `#1a1a1e` | NSVisualEffectView `.sidebar` material | Applies vibrancy behind the NavigationSplitView sidebar column |
| `surface` | `#ffffff` | `#1a1a1e` | `.controlBackgroundColor` | Card, list row, sheet backgrounds |
| `surface2` | `#f2f2f7` | `#222226` | `.quaternarySystemFill` | Nested surface: row hover, input background |
| `border` | `#d2d2d7` | `#2a2a2e` | `.separatorColor` | Dividers, row separators, card outlines |
| `label` | `#1d1d1f` | `#f0f0f0` | `.labelColor` | Primary text |
| `secondary-label` | `#6e6e73` | `#888888` | `.secondaryLabelColor` | Subtitles, metadata rows |
| `tertiary-label` | `#aeaeb2` | `#555555` | `.tertiaryLabelColor` | Placeholder, disabled labels |
| `quaternary-label` | `#c7c7cc` | `#3a3a3c` | `.quaternaryLabelColor` | Watermark text |
| `success` | `#2fa36b` | `#4ade80` | `.systemGreen` | In-stock status, confirmed state |
| `success-dim` | `#edfaf3` | `#162820` | `.systemGreen.opacity(0.12)` | Success background tint (badge, pill background) |
| `warning` | `#f59e0b` | `#fbbf24` | `.systemOrange` | Low-stock, amber alert, overdue bills |
| `warning-dim` | `#fffbeb` | `#1a1500` | `.systemOrange.opacity(0.12)` | Warning background tint |
| `error` | `#ef4444` | `#f87171` | `.systemRed` | Destructive actions, error states |
| `error-dim` | `#fef2f2` | `#2d0a0a` | `.systemRed.opacity(0.12)` | Error background tint |
| `accent-dim` | `#eff6ff` | `#1e3a5f` | `.systemBlue.opacity(0.12)` | Active selection background, focused row tint |
| `receipt-hover` | `#f5f5f7` | `#202024` | `.surface2` | List row highlight on hover |
| `drop-target` | `#eff6ff` | `#1e3a5f` | `.systemBlue.opacity(0.15)` + 2pt dashed `.systemBlue` border | Drop zone active state |
| `low-stock-pill` | `#fff7ed` | `#27190a` | `.systemOrange.opacity(0.15)` | Background of LowStockPill component |
| `paid-bill` | `#ecfdf5` | `#0a2318` | `.systemGreen.opacity(0.12)` | Fixed bill row when paid |
| `unpaid-bill` | `#fffbeb` | `#1a1500` | `.systemOrange.opacity(0.12)` | Fixed bill row when pending |
| `overdue-bill` | `#fef2f2` | `#2d0a0a` | `.systemRed.opacity(0.12)` | Fixed bill row when overdue |

#### Typography

All type uses **SF Pro** (system font); no font file bundling required. Dynamic Type is respected for accessibility (macOS user font size setting).

| Role | Size | Weight | SwiftUI Modifier | Use |
|---|---|---|---|---|
| `largeTitle` | 26pt | Bold | `.font(.largeTitle)` | Screen titles (Login hero, onboarding) |
| `title1` | 22pt | Bold | `.font(.title)` | Section headers in main content area |
| `title2` | 17pt | Semibold | `.font(.title2)` | Card headers, panel titles |
| `title3` | 15pt | Semibold | `.font(.title3)` | Subsection headers, group labels |
| `headline` | 13pt | Semibold | `.font(.headline)` | Column headers, badge labels |
| `body` | 13pt | Regular | `.font(.body)` | Default text, list row primary label |
| `callout` | 12pt | Regular | `.font(.callout)` | Toolbar labels, secondary actions |
| `subheadline` | 11pt | Regular | `.font(.subheadline)` | List row secondary label, metadata |
| `footnote` | 11pt | Regular | `.font(.footnote)` | Status text, timestamps |
| `caption1` | 10pt | Regular | `.font(.caption)` | Pill labels, badge text |
| `caption2` | 10pt | Regular | `.font(.caption2)` | Fine print, version strings |
| `mono-body` | 13pt | Regular | `.font(.body.monospaced())` | Receipt line-item amounts, currency values |
| `mono-caption` | 10pt | Regular | `.font(.caption.monospaced())` | Transaction IDs, token/model stats |

SF Pro Display (used for text ≥ 20pt) and SF Pro Text (< 20pt) are selected automatically by the system via `.font()` modifiers; no manual font selection needed.

#### Spacing

All spacing follows an **8-point grid**. The following named constants are used throughout this spec:

| Name | Value | Use |
|---|---|---|
| `space-1` | 4pt | Internal pill padding, icon-to-label gap |
| `space-2` | 8pt | Row padding (vertical), badge margin |
| `space-3` | 12pt | Card internal padding (compact) |
| `space-4` | 16pt | Card internal padding (standard), section gap |
| `space-5` | 20pt | Section header margin-bottom |
| `space-6` | 24pt | Content region top padding |
| `space-8` | 32pt | Between major sections |
| `space-10` | 40pt | Full-screen top margin |

#### Corner Radius

| Surface | Radius | SwiftUI |
|---|---|---|
| Control (button, text field, picker) | 6pt | `.cornerRadius(6)` |
| Card (GroupBox, panel) | 10pt | `.cornerRadius(10)` |
| Inner pill (badge, tag chip) | 4pt | `.cornerRadius(4)` |
| Sheet (system-managed) | N/A | System default |
| Popover (system-managed) | N/A | System default |
| Drop zone dashed border | 8pt | `.cornerRadius(8)` |

#### Vibrancy and Materials

| Surface | Material | NSVisualEffectView Blending |
|---|---|---|
| Sidebar column | `.sidebar` | `.behindWindow` |
| Popover background | `.popover` | `.behindWindow` |
| Sheet background | `.sheet` | System default |
| Toolbar | `.titlebar` | `.behindWindow` (automatic with SwiftUI toolbar) |
| Menu bar popover | `.menu` | `.behindWindow` |

#### Animation

| Usage | SwiftUI Animation | Accessibility override |
|---|---|---|
| View transition (push/pop in NavigationStack) | `.easeInOut(duration: 0.2)` | `.linear(duration: 0.001)` if `@Environment(\.accessibilityReduceMotion)` |
| Sheet present / dismiss | `.spring(response: 0.35, dampingFraction: 0.85)` | `.linear(duration: 0.001)` |
| List row appear / disappear | `.easeOut(duration: 0.15)` | none (no motion) |
| Popover appear | System default (SwiftUI `.popover`) | System managed |
| Progress indicator | N/A (continuous spin) | Unaffected |
| Skeleton shimmer | Custom `LinearGradient` phase animation, 1.2s loop | Replaced with static gray block |

All animations check `@Environment(\.accessibilityReduceMotion)` and substitute a `.linear(duration: 0.001)` (effectively instant) fallback.

---

### 3.2 WINDOW ARCHITECTURE

Every window is justified by the MVP scope defined in §2.4. Window sizes follow macOS HIG recommendations (minimum 900pt wide for multi-column layouts).

---

**Window: Main Window**

| Property | Value |
|---|---|
| SwiftUI Scene | `WindowGroup` (primary scene) |
| Style mask | `titled`, `resizable`, `miniaturizable`, `closable`, `fullScreenAllowed` |
| Default size | 1200 × 800 pt |
| Minimum size | 900 × 600 pt |
| Maximum size | Unconstrained |
| Size persistence | `setFrameAutosaveName("MainWindow")` — restores size and position across launches |
| Toolbar | Yes — standard NSToolbar; left: sidebar toggle + domain segmented control; center: view title; right: search field + add button |
| Titlebar | Unified titlebar + toolbar (`.windowStyle(.hiddenTitleBar)` with custom toolbar); traffic lights remain visible |
| Sidebar | `NavigationSplitView` with `.sidebar` column; resizable; default 220pt; minimum 180pt; maximum 340pt; uses `NSVisualEffectView .sidebar` material |
| Content split | Primary sidebar / secondary content (list or tiles) / optional tertiary inspector (receipt detail, item detail) |
| Full screen | Supported; sidebar persists in full screen; inspector collapses to floating panel |
| Tab bar | Not used; domain switching via sidebar sections, not window tabs |
| Restoration | `NSWindowRestoration` restores last-open domain and selection on relaunch |

MVP justification: Required as the primary container for all 16 in-scope v1.0 screens (§2.4).

---

**Window: Settings (Preferences)**

| Property | Value |
|---|---|
| SwiftUI Scene | `Settings` scene (automatically managed by SwiftUI; ⌘, opens it) |
| Default size | 560 × 440 pt |
| Minimum / maximum | Fixed (Apple HIG: preferences windows are not resizable) |
| Toolbar | `TabView` with `.tabViewStyle(.automatic)` — renders as macOS tab selector |
| Panes | General, Account, Receipts, Notifications, Advanced (5 tabs — detailed in §3.8) |
| Position | Centered on first open; remembered via `setFrameAutosaveName("PreferencesWindow")` |

MVP justification: Required for server URL, AI model config, trusted devices, and Telegram config (§2.4 Settings row).

---

**Window: Receipt Inspector**

| Property | Value |
|---|---|
| SwiftUI Scene | `WindowGroup` parameterized by `receiptId: Int` |
| Default size | 720 × 680 pt |
| Minimum size | 480 × 400 pt |
| Maximum size | Unconstrained |
| Multi-instance | Yes — multiple Receipt Inspector windows may be open simultaneously (open multiple receipts side-by-side for comparison) |
| Toolbar | Left: model picker (Re-run OCR); right: share button, confirm button |
| Window title | "[Store Name] — [Date]" |
| Persistence | Open inspector IDs stored in `@AppStorage("openReceiptInspectors")` — restored on launch |

MVP justification: The Re-run OCR diff view (§2.4, §1.8) is a key interaction that benefits from a dedicated window when comparing receipts. The parameterized WindowGroup pattern is the SwiftUI-native approach.

---

**Window: OCR Upload Panel**

| Property | Value |
|---|---|
| Type | Modal sheet presented over the Main Window; OR standalone `NSPanel` when invoked from the menu bar icon (no main window) |
| Sheet size | 480 × 420 pt (when presented as sheet, size is content-driven) |
| Panel size | 480 × 420 pt floating panel (NSPanel, non-activating) |
| Entry points | ⌃⌘R global shortcut, File → New Receipt Upload, Drag-from-Finder, Dock icon drop, Menu bar Quick Action |
| Dismissed by | Cancel button, Esc key, successful submit (transitions to Review and Edit) |

MVP justification: Global shortcut ⌃⌘R (§2.3 desktop-exclusive feature #1) requires an upload path even when the main window is not in focus, necessitating both sheet and standalone panel variants.

---

**Window: Plaid Link (OAuth Sheet)**

| Property | Value |
|---|---|
| Type | `ASWebAuthenticationSession` — not a real NSWindow; the system manages the OAuth browser context |
| Initiation | "Link Bank Account" button in Plaid Integration screen → server returns Link URL → `ASWebAuthenticationSession(url:callbackURLScheme:completionHandler:)` |
| Callback scheme | `localocr://plaid-callback` (registered in Info.plist `CFBundleURLTypes`) |
| Dismissal | OAuth flow completes (success or cancel) → callback fires → sheet dismissed |
| Server-side | Access token exchange happens at the server's `/plaid/exchange` endpoint after the callback |

MVP justification: Required for Plaid Integration (§2.4, §2.6 AC-18).

---

**Window: Menu Bar Popover**

| Property | Value |
|---|---|
| Type | `NSPopover` presented from `NSStatusItem` |
| Size | 300 × 360 pt (fixed) |
| Content | Low-stock count badge, Quick Add Cash, Open Receipt Upload, Open App, separator, last-sync timestamp |
| Behavior | `.applicationDefined` (stays open while interacting; closes on click-outside) |
| When main window is closed | Popover is the only UI surface; "Open App" button re-opens the main window |

MVP justification: §2.3 desktop-exclusive feature #3 — menu bar status icon is a v1.0 requirement.

---

**Window: New Cash Transaction (quick-add from menu bar)**

| Property | Value |
|---|---|
| Type | Inline form inside the Menu Bar Popover (not a separate window) |
| Trigger | "Quick Add Cash" button in menu bar popover |
| Fields | Amount (TextField), Description (TextField), Category (Picker), Date (DatePicker, defaults to today) |
| Submission | "Log" button → POST `/cash-transactions` → dismiss popover |
| Alternative | Main window: sheet over content area |

MVP justification: §2.3 desktop-exclusive feature #3 (menu bar quick actions).

---

### 3.3 APPLICATION MENU SPEC

Every menu item is listed with shortcut, action, and enabled-when condition. Items that duplicate the standard macOS AppKit defaults (Undo, Redo, Cut, Copy, Paste, Select All, Services, etc.) are noted as "standard" and inherit AppKit behavior without custom implementation.

---

**LocalOCR Menu (App Menu)**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| About LocalOCR | — | Present standard About panel (app name, version, build, copyright) | Always |
| Preferences… | ⌘, | Open Settings window | Always |
| *(separator)* | | | |
| Services | — | Standard Services submenu | Standard |
| *(separator)* | | | |
| Hide LocalOCR | ⌘H | Standard hide | Always |
| Hide Others | ⌥⌘H | Standard hide others | Always |
| Show All | — | Standard show all | Always |
| *(separator)* | | | |
| Quit LocalOCR | ⌘Q | Standard quit (presents "are you sure?" if upload is in progress) | Always |

---

**File Menu**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| New Receipt Upload… | ⌘N | Open OCR Upload panel (sheet or floating panel per §3.2) | Always (auth required; if unauthenticated, shows login prompt) |
| New Cash Transaction | ⌃⌘N | Open Cash Transaction entry form as sheet over main window | Always (auth required) |
| Open Receipt… | ⌘O | Present `NSOpenPanel` filtered to JPEG, PNG, HEIC, PDF; selected file pre-fills OCR Upload panel | Always |
| Import Receipts from Folder… | ⇧⌘O | Present `NSOpenPanel` in folder-select mode; all accepted files in folder queued for batch OCR | Always |
| *(separator)* | | | |
| Export Spending as CSV… | — | Present `NSSavePanel` with suggested name `spending-<YYYY-MM>.csv`; calls analytics export endpoint | Main window is showing Analytics, Spending by Category, or Fixed Bills screen |
| Print… | ⌘P | Print current content view (receipt detail, spending table) | Current view is printable (Receipt Inspector open, or spending list focused) |
| *(separator)* | | | |
| Close Window | ⌘W | Close frontmost window (does not quit the app; menu bar persists per §2.6 AC-12) | A window is open |

---

**Edit Menu**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Undo | ⌘Z | Standard Undo via `UndoManager` | Undo stack non-empty for focused window |
| Redo | ⇧⌘Z | Standard Redo | Redo stack non-empty |
| *(separator)* | | | |
| Cut | ⌘X | Standard | Text field focused |
| Copy | ⌘C | Standard; additionally: copies selected receipt row as formatted text | Text field focused OR receipt/inventory row selected |
| Paste | ⌘V | Standard | Pasteboard has compatible content |
| Paste and Match Style | ⌥⇧⌘V | Standard | Text field focused |
| Select All | ⌘A | Standard; in list views: selects all rows (multi-select where supported) | Always |
| *(separator)* | | | |
| Find… | ⌘F | Focus the search field in the current view (`.searchable` modifier's field) | Main window is focused |
| Find Next | ⌘G | Select next search result in current list | Search is active |
| Find Previous | ⇧⌘G | Select previous search result | Search is active |
| Use Selection for Find | ⌘E | Standard | Text selected |

---

**View Menu**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Show Sidebar | ⌃⌘S | Toggle `NavigationSplitView` sidebar column visibility | Main window focused |
| Show Inspector | ⌃⌘I | Toggle the trailing detail/inspector panel | Main window focused and a detail-capable screen is shown |
| *(separator)* | | | |
| — Inventory | ⌘1 | Navigate sidebar to Inventory screen | Main window focused, user authenticated |
| — Shopping List | ⌘2 | Navigate to Shopping List | Main window focused, user authenticated |
| — Fixed Bills | ⌘3 | Navigate to Fixed Bills | Main window focused, user authenticated |
| — Plaid Accounts | ⌘4 | Navigate to Plaid Integration | Main window focused, user authenticated |
| — Cash Transactions | ⌘5 | Navigate to Cash Transactions | Main window focused, user authenticated |
| — Dashboard | ⌘0 | Navigate to Dashboard | Main window focused, user authenticated |
| — Contributions | ⌘6 | Navigate to Contributions | Main window focused, user authenticated |
| — Settings | ⌘, | Open Settings window | Always |
| *(separator)* | | | |
| Reload Data | ⌘R | Refetch data for the currently visible screen (calls the screen's load function) | Main window focused |
| *(separator)* | | | |
| Actual Size | ⌘0 (numpad) | Reset any zoom on the receipt photo in Receipt Inspector | Receipt Inspector is open |
| Zoom In | ⌘+ | Zoom in on receipt photo | Receipt Inspector is open |
| Zoom Out | ⌘- | Zoom out on receipt photo | Receipt Inspector is open |
| *(separator)* | | | |
| Enter Full Screen | ⌃⌘F | Standard full screen | Main window focused |

---

**Inventory Menu** (domain-specific; appears when Inventory screen is active)

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Add Item… | ⌥⌘I | Open Add Item sheet | Inventory screen active, write access |
| Edit Selected Item | ⌘E | Open edit sheet for selected inventory row | One row selected |
| *(separator)* | | | |
| Mark as Low Stock | — | Toggle `manual_low` flag on selected item (calls PATCH `/inventory/<id>`) | One row selected, write access |
| Clear Low Stock Flag | — | Clear `manual_low` flag (calls PATCH `/inventory/<id>`) | One or more rows selected with manual_low set |
| *(separator)* | | | |
| View Price History | — | Open price history popover for selected item | One row selected |
| Run Threshold Check Now | — | Trigger server-side low-stock evaluation (calls `/recommendations` refresh) | Admin role, write access |

---

**Shopping Menu** (domain-specific; appears when Shopping List screen is active)

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Add Item to List | ⌘N | Add new item row inline at bottom of list | Shopping List screen active, write access |
| Populate from Low Stock | ⌥⌘P | Calls auto-populate endpoint; adds all low-stock items to list | Write access |
| Mark Selected as Purchased | Space | Toggle checked/unchecked for selected rows | One or more rows selected |
| *(separator)* | | | |
| Share List via QR | ⌘⇧S | Generate and display QR code linking to `/shopping-helper/<token>` | Write access (generates access link) |
| Copy List Link | — | Copy shopping helper URL to clipboard | Active shopping session exists |
| *(separator)* | | | |
| Close Shopping Session | — | Call session close endpoint (prompts confirmation) | Active session exists, write access |

---

**Receipts Menu** (domain-specific; active when Receipt Inspector is open or Receipts context)

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Re-run OCR… | ⌥⌘R | Open model picker and trigger re-run for currently open receipt | Receipt Inspector open |
| Confirm Receipt | ⌘Return | Save current review edits and confirm receipt | Review and Edit panel open, write access |
| *(separator)* | | | |
| Rotate Photo | ⌥⌘T | Rotate receipt photo 90° clockwise (calls rotate endpoint) | Receipt image focused |
| Mark as Reviewed | — | Set receipt status to `reviewed` (no further OCR expected) | Receipt Inspector open, write access |
| Delete Receipt | ⌦ | Delete receipt after confirmation sheet | Receipt Inspector open, admin role |
| *(separator)* | | | |
| Switch AI Model… | — | Open model picker popover | Receipt Inspector open |

---

**Bills Menu** (domain-specific; active when Fixed Bills screen is shown)

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Add Obligation… | ⌘N | Open Add Obligation sheet | Fixed Bills screen active, write access |
| Mark Selected as Paid | Space | Toggle payment status for selected obligation row | One row selected, write access |
| *(separator)* | | | |
| Link to Plaid Transaction | ⌥⌘L | Open Plaid staged-transactions popover for selected bill | One row selected, Plaid linked |
| Generate Projection | — | Call bill_cadence projection endpoint; displays upcoming payments for next 3 months | Admin role |
| *(separator)* | | | |
| Rename Obligation | F2 | Enter inline rename mode for selected obligation label | One row selected, write access |

---

**Window Menu**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| Minimize | ⌘M | Standard minimize to Dock | A window is open |
| Zoom | — | Standard zoom (toggle between default and maximized) | A window is open |
| *(separator)* | | | |
| Main Window | — | Bring Main Window to front (or reopen if closed) | Always |
| *(separator)* | | | |
| Bring All to Front | — | Standard | Always |
| *(separator)* | | | |
| *(Dynamic: open Receipt Inspector windows listed here)* | — | Each open Receipt Inspector: "[Store] — [Date]" brings that window to front | One or more inspectors open |

---

**Help Menu**

| Item | Shortcut | Action | Enabled when |
|---|---|---|---|
| LocalOCR Help | ⌘? | Open in-app help (WKWebView loading `features.html` from server, or bundled HTML fallback) | Always |
| *(separator)* | | | |
| Check for Updates… | — | [STRETCH v1.1] Sparkle updater check | Always |
| *(separator)* | | | |
| Send Feedback… | — | Compose email to support address via `NSSharingService` mail | Always |

---

### 3.4 KEYBOARD SHORTCUTS MASTER LIST

All shortcuts are grouped by scope. Conflicts with macOS system shortcuts are noted. Custom shortcuts registered via `keyboardShortcut()` modifier in SwiftUI or explicit `NSMenuItem` key equivalents.

| Shortcut | Action | Scope | macOS Conflict? |
|---|---|---|---|
| **Global (system-wide, registered via CGEventTap)** | | | |
| ⌃⌘R | Open OCR Upload panel (brings app to front if needed) | System-wide | No |
| **App-global (main menu)** | | | |
| ⌘N | New Receipt Upload (when main window is key) OR Add Item inline (when Inventory / Shopping is focused) | App | No |
| ⌘O | Open file via NSOpenPanel (receipt) | App | No |
| ⇧⌘O | Import receipts from folder | App | Possible (some apps use for Outline) — acceptable |
| ⌘W | Close frontmost window | App | No (standard) |
| ⌘Q | Quit (with in-progress-upload confirmation) | App | No (standard) |
| ⌘, | Open Settings / Preferences | App | No (standard) |
| ⌘H | Hide app | App | No (standard) |
| ⌥⌘H | Hide others | App | No (standard) |
| ⌘Z / ⇧⌘Z | Undo / Redo | App | No (standard) |
| ⌘F | Focus search field in current view | App | No |
| ⌘G / ⇧⌘G | Next / Previous search result | App | No (standard in search context) |
| ⌘R | Reload data for current screen | App | No |
| ⌘P | Print current view | App | No (standard) |
| ⌃⌘F | Enter / exit full screen | App | No (standard) |
| **Navigation** | | | |
| ⌘0 | Navigate to Dashboard | Main window | No |
| ⌘1 | Navigate to Inventory | Main window | No |
| ⌘2 | Navigate to Shopping List | Main window | No |
| ⌘3 | Navigate to Fixed Bills | Main window | No |
| ⌘4 | Navigate to Plaid Accounts | Main window | No |
| ⌘5 | Navigate to Cash Transactions | Main window | No |
| ⌘6 | Navigate to Contributions | Main window | No |
| ⌃⌘S | Toggle sidebar visibility | Main window | No |
| ⌃⌘I | Toggle inspector / detail panel | Main window | No |
| **Receipt Upload / OCR** | | | |
| ⌃⌘R | Open OCR Upload (global, see above) | System | — |
| ⌘Return | Submit / confirm (Run OCR, Confirm Receipt, Save edits) | Upload panel / Review screen | No |
| Esc | Cancel current sheet / panel / in-progress edit | Any sheet | No (standard) |
| ⌥⌘R | Re-run OCR for open receipt | Receipt Inspector | No |
| ⌥⌘T | Rotate receipt photo 90° | Receipt Inspector | No |
| Tab | Move focus to next editable field in Review and Edit | Review screen | No |
| ⇧Tab | Move focus to previous field | Review screen | No |
| **Inventory** | | | |
| ⌥⌘I | Add new inventory item | Inventory screen | No |
| ⌘E | Edit selected inventory item | Inventory screen | No |
| ⌥↑ | Increment quantity of selected item by 1 | Inventory screen | No |
| ⌥↓ | Decrement quantity of selected item by 1 (min 0) | Inventory screen | No |
| ⌘L | Add selected inventory item to shopping list | Inventory screen | No |
| Delete | Prompt to remove selected item from inventory | Inventory screen | No (standard) |
| **Shopping List** | | | |
| ⌘N | Add new item inline at bottom of list | Shopping List | No |
| Space | Toggle checked/unchecked (purchased) for selected item(s) | Shopping List | No |
| ⌥⌘P | Populate list from low-stock items | Shopping List | No |
| ⌘⇧S | Share list via QR | Shopping List | Possible (some apps: Save As) — acceptable |
| Delete | Remove selected item from shopping list (with undo) | Shopping List | No |
| **Fixed Bills** | | | |
| Space | Toggle paid/unpaid for selected bill row | Fixed Bills | No |
| F2 | Enter inline rename for selected obligation label | Fixed Bills | No (F2 is convention for rename) |
| ⌘N | Add new floor obligation | Fixed Bills | No |
| ⌥⌘L | Link selected bill to Plaid transaction | Fixed Bills | No |
| Return | Confirm pending inline edit of obligation name | Fixed Bills inline edit | No |
| Esc | Cancel inline edit | Fixed Bills inline edit | No |
| **Plaid / Finance** | | | |
| Return | Confirm selected staged Plaid transaction | Plaid staged transactions list | No |
| Delete | Dismiss selected staged transaction (with confirm) | Plaid staged transactions list | No |
| ←/→ | Step through months in analytics month picker | Analytics / Spending | No |
| **Lists (universal, any List view)** | | | |
| ↑ / ↓ | Move selection up / down one row | Any List | No |
| ⇧↑ / ⇧↓ | Extend selection (multi-select) | Lists supporting multi-select | No |
| ⌘↑ / ⌘↓ | Jump to first / last item | Any List | No |
| Space | Quick Look (preview) for selected item (§2.3 feature #11 — v1.1) | Lists with previewable items | No |
| Return or ⌘↓ | Open detail / expand selected row | Any List | No |
| ⌘A | Select all rows | Lists supporting multi-select | No |
| **Receipt Inspector** | | | |
| ⌘+ / ⌘- | Zoom photo in / out | Receipt Inspector | No |
| ⌘0 | Reset photo to actual size | Receipt Inspector | Conflicts with Dashboard nav shortcut — Inspector is a separate window, so scope is separate |
| **Export / Save** | | | |
| ⌘S | Export CSV (when Analytics screen focused) | Analytics | No (no unsaved document concept) |
| **Accessibility** | | | |
| ⌃F5 | Move focus to toolbar | Any window | No (standard VoiceOver) |
| ⌃F6 | Move focus to main content | Any window | No (standard) |

---

### 3.5 CONTEXT MENU SPECS

All context menus are implemented via SwiftUI's `.contextMenu {}` modifier on the relevant list row or surface. Destructive items use `.destructive` role (shown in red). Separator placement follows Apple HIG: destructive items always at the bottom after a separator.

---

**Receipt row (in a Receipts list or Dashboard review queue)**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Open Receipt | Open Receipt Inspector for this receipt | — | Default double-click action |
| Re-run OCR… | Open model picker then re-run | — | |
| *(separator)* | | ✓ | |
| Copy Store Name | Copy to clipboard | — | |
| Copy Total Amount | Copy formatted dollar amount | — | |
| *(separator)* | | ✓ | |
| Mark as Reviewed | Set status to reviewed | — | |
| Export Receipt… | NSSavePanel for receipt image PNG | — | |
| *(separator)* | | ✓ | |
| Delete Receipt… | Confirmation sheet → DELETE API | — | `.destructive` role; admin only |

---

**Inventory row**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Edit Item… | Open edit sheet | — | Default double-click action |
| View Price History | Open price history popover | — | |
| *(separator)* | | ✓ | |
| Add to Shopping List | Adds item to active session | — | Disabled if item already on list |
| Mark as Low Stock | Toggle `manual_low=true` | — | |
| Clear Low Stock Flag | Toggle `manual_low=false` | — | Shown only if `manual_low=true` |
| *(separator)* | | ✓ | |
| Set Location… | Location picker popover (Fridge/Pantry/Freezer/etc.) | — | |
| *(separator)* | | ✓ | |
| Remove from Inventory… | Confirmation → DELETE | — | `.destructive` role |

---

**Shopping list item**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Mark as Purchased | Toggle `status=purchased` | — | Also Space shortcut |
| Mark as Not Purchased | Toggle `status=open` | — | Shown only when purchased |
| Edit Note… | Inline note TextField popover | — | |
| *(separator)* | | ✓ | |
| Set Preferred Store… | Store picker popover | — | |
| Set Estimated Price… | Price TextField popover | — | |
| *(separator)* | | ✓ | |
| Remove from List… | DELETE with undo | — | `.destructive` role |

---

**Fixed bill row**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Mark as Paid | Toggle payment status | — | Also Space shortcut |
| Rename… | Enter inline edit mode (same as F2) | — | |
| *(separator)* | | ✓ | |
| Link to Plaid Transaction… | Open staged transactions popover | — | Disabled if Plaid not linked |
| View Payment History | Open payment history detail panel | — | |
| *(separator)* | | ✓ | |
| Delete Obligation… | Confirmation → DELETE | — | `.destructive` role; admin only |

---

**Plaid staged transaction row**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Confirm as [Receipt Type] | Confirm import with auto-detected type | — | Shows detected type (Grocery / Restaurant / Expense) |
| Confirm with Custom Type… | Type picker sheet → confirm | — | |
| *(separator)* | | ✓ | |
| Link to Existing Receipt… | Receipt search sheet | — | |
| Mark as Floor Obligation | Auto-link to matching floor obligation | — | |
| *(separator)* | | ✓ | |
| Dismiss Transaction | Set status = dismissed | — | `.destructive` role |

---

**Sidebar tab / navigation item**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Open in New Window | Open selected domain's screen in a new main window | — | Uses SwiftUI multi-window (§2.3 feature #6) |
| *(separator)* | | ✓ | |
| Reload | Refresh data for this section | — | |

---

**Recipe / product name in Kitchen View**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Add to Shopping List | Adds item | — | |
| View in Inventory | Navigate to Inventory with this item selected | — | |
| *(separator)* | | ✓ | |
| Mark as Low Stock | Toggle `manual_low` | — | |

---

**Receipt line item (in Review and Edit)**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Edit Item | Open inline edit for this line | — | Default double-click |
| Change Kind… | Kind picker popover (product/discount/fee/tax/tip/…) | — | |
| *(separator)* | | ✓ | |
| Remove Item… | Delete line from receipt | — | `.destructive` role; does not affect saved inventory |

---

**Contribution event row**

| Item | Action | Separator | Notes |
|---|---|---|---|
| Copy Event Description | Copy to clipboard | — | |
| View Related Receipt | Open Receipt Inspector for linked purchase | — | Disabled if no purchase link |

---

### 3.6 COMPONENT LIBRARY — macOS NATIVE

Every reusable UI primitive is listed with its SwiftUI or AppKit mapping, customization level, states, hover behavior, and any notable implementation notes.

| Component | Native Equivalent | Custom? | States | Hover Behavior | Notes |
|---|---|---|---|---|---|
| **PrimaryButton** | `Button(.borderedProminent)` | Minimal (brand `accent` tint) | Default, Hover (brightness +5%), Pressed, Disabled (`.opacity(0.5)`) | Background lightens slightly | Use for: Run OCR, Confirm Receipt, Log Cash, Settle All |
| **SecondaryButton** | `Button(.bordered)` | No | Default, Hover, Pressed, Disabled | Border highlights | Use for: Cancel, Edit, Re-run |
| **DestructiveButton** | `Button(.borderedProminent).tint(.red)` | No | Default, Hover, Pressed, Disabled | Red brightens | Use for: Delete Receipt, Remove from Inventory |
| **TextField** | `TextField(.roundedBorder)` | Minimal | Empty, Focused, Filled, Error (red border), Disabled | Focus ring appears | All text inputs; error state adds `.overlay(RoundedRectangle(cornerRadius:6).stroke(.red, lineWidth:1))` |
| **SearchField** | `.searchable(text:)` modifier on parent `List` / `NavigationSplitView` | No | Inactive, Active, Has results, No results | Standard macOS search token focus | Bound to viewModel `searchQuery`; live filtering without API round-trip where cache is available |
| **ListRow** | Custom `HStack` inside SwiftUI `List` with `ForEach` | Yes — brand styling | Default, Selected (`.listRowBackground(accent-dim)`), Hover (`.listRowBackground(receipt-hover)`), Focused (blue ring on Tab focus) | Background tints to `receipt-hover` | Height: 44pt minimum to meet click-target requirement; use `.listRowInsets` for padding |
| **SidebarItem** | `Label` inside `List` with `.listStyle(.sidebar)` | Minimal | Default, Selected, Active (bold label) | Highlight background | Domain icons use SF Symbols; §1.9 permits emoji fallback |
| **Card** | `GroupBox` or `VStack` over `RoundedRectangle(cornerRadius:10).fill(surface)` | Minimal | Default, Hover (subtle shadow increase) | Elevation shadow: 0→2pt | Use for: Dashboard tiles, Dining Budget card, AI model config cards |
| **LowStockPill** | `Capsule().fill(low-stock-pill)` + `Text(caption)` | Yes | In-stock (green), Low (amber), Out (red), Manual-low (amber dashed border) | No hover | Always 22pt tall; use `.font(.caption)` for count text |
| **CategoryChip** | `Label` inside `Capsule` | Yes — colored | Default, Selected (filled), Disabled | Selected state fills with category color | Category chips in Inventory filter bar; not interactive in Kitchen View |
| **DropZone** | Custom `ZStack` with dashed `RoundedRectangle` + `.onDrop(of:delegate:)` | Yes — fully custom | Idle (dashed border, muted), Drag-over (blue dashed border + `drop-target` fill), Invalid type (red dashed) | Animates to active on drag-over | `UniformTypeIdentifiers` types: `public.jpeg`, `public.png`, `org.webmproject.webp` (HEIC = `public.heic`), `com.adobe.pdf` |
| **ReceiptThumbnail** | `AsyncImage` wrapper | Minimal | Loading (shimmer), Loaded, Error (broken-image icon) | No hover effect | Image URL from server `/receipts/<id>/image`; aspect-fit; rounded 6pt corners |
| **SankeyChart** | `WKWebView` loading a local HTML bundle with D3/Vega-Lite | Fully custom web component | Loading (ProgressView), Loaded, Error (retry) | Web-native hover | Per §1.8 complexity flag — no SwiftCharts equivalent; web-rendered is correct; local bundle avoids network dependency |
| **SpendingBarChart** | `SwiftCharts.BarMark` (macOS 13+) | Minimal | Default, Selected bar (accent fill), Animated in | Tooltip on hover via `.chartOverlay` | Horizontal bars for category breakdown; vertical for monthly timeline |
| **ProgressBar** (bill paid-vs-expected) | Custom `ZStack`: background track `Capsule` + filled `Capsule`, animated on value change | Yes | Green (<80%), Amber (80–94%), Red (≥95%) | No hover | Height 8pt; used in Dining Budget card and Household Budget panes |
| **ProgressView** (loading) | `ProgressView()` circular (indeterminate) | No | Spinning, Complete | N/A | Centered in content area during initial load |
| **SkeletonLoader** | Custom `VStack` of `RoundedRectangle` with `LinearGradient` shimmer phase animation | Yes | Animating | N/A | Used for list rows during initial data fetch; fades out when real data arrives via `.transition(.opacity)` |
| **EmptyState** | Custom `VStack(spacing:20)` — SF Symbol icon + `Text` title + `Text` subtitle + `PrimaryButton` CTA | Yes | Default, CTA-hover | CTA button hover | Icon: 48pt SF Symbol; Title: `.title2`; Subtitle: `.body.secondary` |
| **Toast / Notification Banner** | Custom `VStack` overlay anchored to top of content area with `withAnimation` slide-in/out | Yes | Info (accent), Success (success), Warning (warning), Error (error) | No hover | Auto-dismisses after 4 seconds; also has manual close X; not the same as `UNUserNotificationCenter` |
| **InlineEditableCell** | `TextField` that replaces `Text` on double-click (obligations rename, §1.8) | Yes | Display, Editing, Saving, Error | Label underlines on hover to hint editability | On double-click: `.isEditing = true`; on `controlTextDidEndEditing`: send PATCH; on Esc: revert |
| **KeyValueRow** | Custom `HStack` with `Text(key).secondary` + `Spacer()` + `Text(value)` | Yes — minimal | Default | Label secondary hover brightens | Used in receipt detail header (Store, Date, Total) and Plaid transaction detail |
| **Badge** | `.badge()` modifier OR custom `Capsule` with count text | Minimal | Zero (hidden), Non-zero (visible) | No hover | Sidebar items use `.badge(count)` modifier (macOS 13+) |
| **Toggle** | `Toggle(.switchToggleStyle)` | No | On, Off, Disabled, Mixed | Thumb animates | Used for: demo mode gate, nudge enabled, auto-pay flag |
| **Picker** (model selector, category) | `Picker(.menuStyle)` OR `Picker(.segmented)` for ≤4 options | No | Default, Open, Disabled | Arrow cursor | AI model picker uses `.menuStyle`; receipt type picker uses `.segmented` (3–4 options) |
| **Popover** | `.popover(isPresented:arrowEdge:)` | No | Hidden, Visible | N/A | Price history, Plaid link, share QR, location picker |
| **AttributionPicker** | Custom sheet with three `RadioButton`-style options (Household / Personal / Split) + member checkboxes for Split | Yes | Default, Split expanded, Saving | N/A | Required by §1.7 rule 9; presented as sheet after every receipt confirm without attribution |
| **QRCodeView** | `AsyncImage` loading QR PNG from server endpoint `/auth/qr-image` or `/shopping/qr` | Minimal | Loading, Loaded, Error | N/A | Displayed in: Settings (QR login), Shopping List (share QR), Device Pairing |
| **ModelPicker** | `Picker(.menuStyle)` with models from `/ai-models` | Minimal | Default, Loading models, No models (disabled) | Standard picker hover | Shows provider name + model name; active model highlighted; unlocked/locked visual per `user_ai_model_access` |
| **DemoModeBanner** | `HStack` with warning icon + label + "Sign In" button; fixed at top of content area | Yes | Visible (demo mode only) | Sign In button hover | Yellow (`warning-dim` background); dismissable? No — always visible in demo mode per §1.7 rule 10 |

---

### 3.7 VIEW-BY-VIEW DESIGN SPECS

Each view follows the standard template defined in the section header. MVP views confirmed against §2.4 (16 in-scope screens). The order follows the user journey from first launch to daily use.

---

**View 1: Login / Onboarding**

Window: Main Window (before auth, the window shows login content in full; no sidebar)
Navigation path: App launch → first screen if not authenticated; also reached via Settings → Sign Out
Layout pattern: Single-column centered card (no sidebar, no toolbar until authenticated)
Toolbar items: None (traffic lights only; no custom toolbar)
Content structure:
- App icon (128×128 SF Symbol or bundled icon asset) centered at 160pt from top
- App name "LocalOCR Extended" in `.largeTitle`
- Tagline "Your household's smart receipt scanner" in `.body.secondary`
- Divider
- Email `TextField` (`.textFieldStyle(.roundedBorder)`, placeholder "Email address", `textContentType(.emailAddress)`, `keyboardType(.emailAddress)`)
- Password `SecureField` (`.textFieldStyle(.roundedBorder)`, placeholder "Password", `textContentType(.password)`)
- "Sign In" `PrimaryButton` (full width, ⌘Return fires this)
- "Continue with Google" `SecondaryButton` (full width; `Image(systemName:"g.circle.fill")` + "Continue with Google"; launches `ASWebAuthenticationSession`)
- Separator with "or"
- "Try Demo" `Button(.plain)` in `.body.secondary` (no write access gate needed here — sets demo state client-side)
- Server URL field: collapsed by default; "Using server: [host]" in `.caption.secondary` with a "Change" link that expands a server URL `TextField` + "Connect" button (reads from/writes to Keychain)

List behavior: N/A
Empty state: N/A (this IS the empty state)
Loading state: After "Sign In" tap — button shows `ProgressView` inline (replaces label), fields disabled
Error state: Inline error `Text` in `.systemRed` below password field: "Incorrect email or password." (no toast — keep it in-form)
Hover states: Sign In button highlights on hover; Google button border brightens
Drag-and-drop: None
Vibrancy: No (no sidebar; window background = `windowBackgroundColor`)
Dark mode notes: App icon may need both light and dark variants in asset catalog
Accessibility:
- VoiceOver order: App icon → App name → tagline → Email field → Password field → Sign In → Google → Try Demo → Server link
- `accessibilityLabel` on icon button: "LocalOCR Extended app icon"
- Focus ring on all interactive elements
- Return key in Email field moves focus to Password field via `@FocusState`
- Return key in Password field submits (same as Sign In button)
- Minimum click target 44×44pt on all buttons

---

**View 2: Household Selector**

Window: Sheet over Main Window (only shown when user belongs to multiple households — [UNCONFIRMED: the current backend uses a single-deployment household model per §1.7 rule 1; this view is shown if server URL is changed to a new server, requiring re-auth]
Navigation path: Post-login → if multiple households exist (server supports multi-household in future) → household selector; otherwise skipped entirely
Layout pattern: Single-column centered list (modal sheet)
Toolbar items: None (sheet toolbar: title only)
Content structure:
- Sheet title: "Choose Household"
- `List` of household options, each row: household name + member count + last-activity timestamp
- "Cancel" button (dismisses sheet, logs out)
Note: Per §1.7 rule 1, the current backend is single-household scoped. This view is a forward-compatibility stub; in v1.0, the app connects to one server = one household. Show this view only if the server's `/auth/me` response includes a household-selector flag (which currently it does not). Mark as `[DEFERRED — awaiting multi-household backend support]`.

---

**View 3: Dashboard**

Window: Main Window
Navigation path: Root (shown immediately after login; sidebar: "Dashboard" item)
Layout pattern: Three-column `NavigationSplitView`: sidebar (domain nav) + primary content (tiles grid) + optional secondary (drill-down panel, shown when a tile is expanded)
Toolbar items:
- Left: Sidebar toggle (`controlGroup` with `sidebar.left` SF Symbol)
- Center: "Dashboard" title (`.navigationTitle("Dashboard")`)
- Right: Add button (`+`, opens new receipt upload panel), Refresh button (`arrow.clockwise`)

Content structure:
- **DemoModeBanner** (pinned at top, yellow, visible only in demo mode — §1.7 rule 10)
- **Attribution nudge banner** (amber `Card`, visible if any recent receipt has unset attribution — §1.7 rule 9): "3 receipts need attribution → Tag Now" button
- **Tile grid** (2-column `LazyVGrid` with adaptive 280pt minimum columns):
  - *Low Stock tile*: count badge (e.g. "8 items"), item names preview list (top 3), "View Inventory" CTA button
  - *Spending tile (current month)*: total spent `Text` in `.title.monoDigit`, domain breakdown mini bars (Grocery / Dining / Fixed), "View Analytics" CTA
  - *Review Queue tile*: count of receipts with unreviewed status, "Review Now" CTA
  - *Fixed Bills tile*: X paid / Y total this month, unpaid bill names preview, "View Bills" CTA
  - *Plaid Sync tile*: last-sync timestamp, "X staged transactions" badge, "Review" CTA; if `login_required`: amber warning "Bank requires re-auth"
  - *Contributions tile*: current-month leaderboard top-3 names + points, "View All" link

List behavior: N/A (tile grid, not a list)
Empty state: If no household data yet — onboarding card: "Upload your first receipt to get started" with drag-zone illustration
Loading state: Dashboard tiles show `SkeletonLoader` cards (2 per row × 3 rows) while data loads; individual tiles can load independently
Error state: Each tile shows its own error state inline: icon + "Failed to load — Retry" link
Hover states: Tiles elevate (shadow: 0→4pt) on hover; CTA buttons highlight
Drag-and-drop: Accepts PDF/JPEG/PNG/HEIC dropped onto main content area → opens OCR Upload panel with file pre-filled (the entire window is a drop target)
Vibrancy: Sidebar uses `.sidebar` material; main content uses `windowBackgroundColor`
Dark mode notes: Tile backgrounds use `surface` token; ensure sufficient contrast on amber/green status badges
Accessibility:
- VoiceOver: reads tiles in grid order (left to right, top to bottom)
- Each tile announces its live-updating count as an `@Environment` accessibility announcement when data changes
- "Low Stock tile" accessibilityLabel: "Low stock: 8 items. Activate to view inventory."

---

**View 4: OCR Upload**

Window: Main Window (sheet) OR floating NSPanel (from global shortcut / menu bar)
Navigation path: File → New Receipt Upload (⌘N), ⌃⌘R, drag-from-Finder, Dock drop
Layout pattern: Single-column centered form (when sheet); centered panel layout (when NSPanel)
Toolbar items: None (sheet UI; Cancel + action buttons are in the content area)
Content structure:
- **DropZone** (large, center of sheet — approx 280×200pt):
  - Idle state: dashed border, camera icon (`photo.badge.plus` SF Symbol, 40pt), label "Drop a receipt here", subtext "or click to browse"
  - Drag-over: `drop-target` fill + blue dashed border
  - File selected: file icon + filename + file size; "× Remove" link to clear
  - Click action: triggers `NSOpenPanel` with `allowedContentTypes: [.jpeg, .png, .heic, .pdf]`
- **Continuity Camera button** (below drop zone, shown only when Continuity Camera device detected): `Image(systemName: "iphone.rear.camera")` + "Take Photo with iPhone"
- **Receipt Type Picker** (`Picker(.segmented)` with 4 segments: "Auto", "Grocery", "Restaurant", "Expense"); default: "Auto"; type directly affects OCR prompt sent to AI (§1.7 rule 4)
- **AI Model Picker** (`ModelPicker` component, `Picker(.menuStyle)`): shows active user model by default; list from `/ai-models`; picker disabled until file is selected (or allow pre-selection)
- **"Run OCR" PrimaryButton** (full width of form, ⌘Return fires it): disabled until file is selected
- **Progress state** (replaces button while OCR runs): `ProgressView` circular + "Processing with [model name]…" label + "Cancel" link

List behavior: N/A
Empty state: DropZone idle state serves as the empty state
Loading state: Button becomes ProgressView when OCR job is submitted; the full panel remains visible (user cannot interact with the drop zone during processing)
Error state: Toast banner (Error style) above button: "OCR failed: [error message]. Try a different model." with "Re-run" button. Error is model-specific — model picker remains enabled so user can switch.
Hover states: Drop zone border animates to solid on hover (even without a drag); Run OCR button highlights; browse-click cursor changes to hand
Drag-and-drop:
- Accepts: `public.jpeg`, `public.png`, `public.heic`, `com.adobe.pdf`
- Produces: triggers OCR flow with dropped file
Vibrancy: Popover/sheet material (system default)
Dark mode notes: DropZone idle dashed border uses `border` token (2pt dashed); idle background `surface2`
Accessibility:
- DropZone announces: "Receipt drop zone. Drag a JPEG, PNG, HEIC, or PDF here, or activate to open file picker."
- Continuity Camera button: "Take photo with iPhone camera."
- Model picker: "AI model. Currently [model name]."
- Run OCR button: "Run OCR. Processes receipt with [model name]."

---

**View 5: Review and Edit**

Window: Main Window (replaces OCR Upload content within the same sheet, OR opens in Receipt Inspector window if navigating from existing receipt)
Navigation path: OCR Upload → (OCR completes successfully) → Review and Edit; OR: Receipts list → open receipt → Review and Edit mode
Layout pattern: Two-panel horizontal split: left panel (form fields + line items list, ~55% width) | right panel (receipt photo, ~45% width)
Toolbar items:
- Left: Back/Cancel button (returns to upload without saving)
- Center: "Review Receipt" title
- Right: "Confirm Receipt" `PrimaryButton` (⌘Return); "Re-run OCR" `SecondaryButton`

Content structure:
- **Left panel — Header fields** (`VStack(spacing:12)`):
  - `KeyValueRow`: Store name — `InlineEditableTextField` (text field on click, saves to `purchases.store_id` lookup)
  - `KeyValueRow`: Date — `DatePicker` (`.graphical` style on click, `.compact` display)
  - `KeyValueRow`: Total — `TextField` with `.monoDigit` formatting, `$` prefix
  - `KeyValueRow`: Receipt Type — `Picker(.segmented)` (Grocery / Restaurant / Expense)
- **Left panel — Line Items List** (`List` with `ForEach`):
  - Each row: quantity `TextField` (4-char wide) + product name `TextField` (expands) + unit price `TextField` (8-char) + kind `Picker(.menu)` (product/discount/fee/tax/tip/other) + `×` delete button
  - Rows with low OCR confidence: amber `LowStockPill`-style badge "?" on the kind picker; VoiceOver announces "Low confidence"
  - Rows where `kind != product`: secondary label color for name and price (they affect analytics but not inventory per §1.7 rule 4)
  - New-item row at bottom: `+` button or Tab from last field adds a blank row
  - Keyboard: Tab moves between fields within a row; at last field, Tab creates new row; ⌘Return confirms entire receipt
- **Right panel — Receipt photo**:
  - `AsyncImage` loading from server receipt image endpoint; aspect-fit with magnification gesture
  - If landscape: server has already rotated (§1.7 rule 3); no rotation needed client-side
  - "Rotate" button below photo (calls server rotate endpoint): `arrow.clockwise` SF Symbol
  - Zoom: ⌘+ / ⌘-; pinch-to-zoom on trackpad
  - Photo loads with shimmer skeleton while fetching

**Re-run OCR Diff Mode** (triggered from "Re-run OCR" button):
- Line items list transitions to diff view:
  - New items (not in original): green left-border + "NEW" badge in `success` color
  - Changed items (quantity or price differs): amber left-border + "CHANGED" badge
  - Unchanged items: normal appearance
  - Removed items: strikethrough text + "REMOVED" in `.systemRed` (informational only — not auto-deleted per §1.7 rule 3)
- Per-item "Accept" checkbox (green checkmark) and "Discard" (×) button
- "Accept All New" button at top of list
- "Discard All New" button

**Attribution Picker Sheet** (presented as sheet after Confirm Receipt if attribution is not set):
- Title: "Who bought this?"
- Three `RadioButton`-style options: "Whole Household" / "Just Me" / "Split Between Members"
- If "Split": checkboxes for each household member with amount input (even split default)
- "Save Attribution" `PrimaryButton`; "Skip for now" `Button(.plain)` (triggers dashboard nudge next launch)

List behavior:
- Selection: Single row (for editing) — no multi-select
- Row height: Dynamic (expands for kind picker)
- Drag-to-reorder: No
- Context menu: Edit Item, Change Kind, Remove Item (see §3.5)
- Double-click: Opens inline edit (same as clicking any field)
- Keyboard navigation: Tab through fields; ↑/↓ to move between rows

Empty state: If OCR returned 0 items — "No items extracted. Check the receipt photo or try a different model." with Re-run OCR button
Loading state: Right-panel photo shows `SkeletonLoader`; list shows 3–5 skeleton rows
Error state: If save fails — Error toast: "Failed to save receipt. [error]. Retry?"
Hover states: Row highlight on hover; delete `×` button fades in on hover
Drag-and-drop: None in this view
Vibrancy: No
Dark mode notes: Low-confidence amber badges must pass contrast check against `surface` (dark) background
Accessibility:
- Each line item row announces: "[Product name], [quantity], [price], [kind]. Confidence: [high/low]."
- "Accept" checkboxes in diff view announce: "Accept [product name] as new item."

---

**View 6: Re-run OCR (model picker state)**

This view is not a standalone screen — it is the diff mode of View 5 (Review and Edit), invoked by the "Re-run OCR" toolbar button or Receipts menu item. See View 5 above for the full diff mode specification. The model picker appears as a `Popover` anchored to the "Re-run OCR" button before the re-run is submitted.

Model picker popover content:
- Title: "Choose AI Model"
- `List` of available models (from `/ai-models`): model name, provider, `price_tier` badge (Free/Paid), `supports_vision` indicator
- "Re-run with [selected model]" `PrimaryButton`
- Active model highlighted with checkmark

---

**View 7: Inventory**

Window: Main Window
Navigation path: Sidebar → Inventory (⌘1)
Layout pattern: Two-column split within the content area: left = category sidebar (120pt) + right = product list; optional right-side inspector panel for selected item detail
Toolbar items:
- Left: Sidebar toggle (controls the app-level sidebar; the category sidebar is within the view)
- Center: "Inventory" navigation title
- Right: Search (`.searchable`), Add Item button (`+`, ⌥⌘I), Filter menu (`line.3.horizontal.decrease.circle`, opens filter popover)

Content structure:
- **Category sidebar** (left, `List` with `.sidebar` style):
  - "All" row (default selected, shows all products) with total count badge
  - Category rows: Dairy, Produce, Bakery, Frozen, Pantry, Beverages, Meat, Cleaning, Personal Care, Other — each with in-stock count badge
  - Filter chips below list: "Low Stock" toggle chip (amber when active), "Out of Stock" chip (red when active), "Manual Low" chip
- **Product list** (right, `List` with `ForEach`):
  - Each row (`ListRow`, 52pt height):
    - Product image thumbnail (`ReceiptThumbnail`, 36×36pt, rounded 4pt)
    - Product name (`.headline`) + brand/size (`.subheadline.secondary`)
    - Category `CategoryChip`
    - Quantity stepper area: current quantity in `.mono-body`; `−` and `+` micro-buttons (⌥↓/⌥↑ keyboard equivalents); minimum 0
    - `LowStockPill` badge: "Low" (amber, if quantity ≤ threshold OR manual_low) or "Out" (red, if quantity = 0)
    - Last price in `.caption.secondary` with `$` prefix and `.mono` font
    - "Add to List" `+` icon button (fades in on row hover; ⌘L keyboard equivalent)
  - Section headers for category grouping when "All" is selected (collapsible via `DisclosureGroup`)
  - Sort: column header clickable — Name (A→Z), Category, Quantity (high→low), Last Purchased (recent first); default = Category + Name
- **Item detail inspector** (trailing panel, appears when row is selected, 280pt wide):
  - Product name + brand (editable on double-click)
  - Category picker
  - Location picker (Fridge / Pantry / Freezer / Cabinet / Bathroom)
  - Quantity field (editable)
  - Threshold field (low-stock threshold; default from `category_shelf_life_default`)
  - Expiry date picker (optional)
  - Price history mini-chart (`SwiftCharts.LineMark`, last 12 data points) with store labels
  - "Edit in Products Catalog" link (admin only)

List behavior:
- Selection: Single (for inspector); multi-select supported for bulk "Add to List"
- Row height: 52pt fixed
- Swipe actions: Trailing swipe: "Add to List" (accent), "Mark Low" (amber); Leading swipe: none
- Drag-to-reorder: No (sorted by data columns)
- Context menu: See §3.5 Inventory row
- Double-click: Opens item inspector / expands inline edit
- Keyboard: ↑/↓ to navigate; ⌥↑/↓ to adjust quantity; ⌘L to add to list; Delete to remove

Empty state: No items in this category — `EmptyState` component: `shippingbox.circle` SF Symbol, "No items in [category]", "Upload a grocery receipt to populate inventory.", "Upload Receipt" CTA
Loading state: 8 skeleton rows while loading; category sidebar counts show "—" placeholders
Error state: Full-width error banner: "Failed to load inventory. [Retry]"
Hover states: Rows highlight `receipt-hover`; "Add to List" icon fades in; quantity `−`/`+` buttons appear
Drag-and-drop:
- Accepts: Receipt image dropped here opens OCR Upload (window-level drop target)
- Produces: Inventory item row can be dragged onto Shopping List (if both are open in multi-window mode — §2.3 feature #6) to add to list
Vibrancy: Category sidebar uses `sidebar` material
Dark mode notes: `LowStockPill` amber and red must pass WCAG 4.5:1 contrast against `surface` dark
Accessibility:
- Each row: "[Product name], [quantity] in stock, [price] avg. [Low stock / Out of stock]."
- Quantity stepper: "Quantity [n]. Decrement with minus button or Option-Down Arrow. Increment with plus button or Option-Up Arrow."

---

**View 8: Shopping List**

Window: Main Window
Navigation path: Sidebar → Shopping (⌘2); also reachable from Inventory row "Add to List" CTA
Layout pattern: Two-tab layout within the content area (Shopping List tab | Recommendations tab — merged per §2.2); no secondary split panel needed (list is the primary surface)
Toolbar items:
- Left: Sidebar toggle
- Center: "Shopping" navigation title
- Right: Auto-populate button (`bolt.fill`, ⌥⌘P — "Add low-stock items"), Add item button (`+`, ⌘N), QR Share button (`qrcode`, ⌘⇧S)

Content structure:
- **Tab bar** (SwiftUI `Picker(.segmented)` or `TabView` with `.tabViewStyle(.page)`): "List" | "Recommendations"

**Shopping List tab:**
- **Session info bar**: Session name (editable inline) + estimated total + item count + status badge (Open / Ready to Bill)
- **Product list** (`List` with `ForEach`, checkbox-style rows):
  - Each row (44pt):
    - Checkbox toggle (`Toggle` appearance; Space toggles; checked items show strikethrough)
    - Product name (`.headline`; strikethrough when purchased)
    - Source badge (`LowStockPill` variant in accent-dim color): "Low Stock" / "Rec" / "Manual"
    - Quantity (`TextField`, 2-char wide, numeric)
    - Estimated price (`TextField`, optional, currency)
    - Preferred store chip (`CategoryChip`, small)
    - Note icon (shows if note exists; tap = popover to view/edit)
  - Checked (purchased) items grouped at bottom behind "Purchased (N)" disclosure group that starts collapsed
  - Drag-to-reorder: Yes (unchecked items only; dragging a checked item reorders within purchased group)
  - Sort chips above list: "Default" | "Alphabetical" | "Store" | "Source"
- **Add item inline**: clicking `+` toolbar button OR pressing ⌘N inserts a new row at top with cursor in name field; autocomplete from `shoppingListCache` product names

**Recommendations tab:**
- Header: "AI Recommendations" + last-generated timestamp + "Refresh" button
- `List` of recommendations, each row (44pt):
  - Urgency indicator (`LowStockPill`: "Out" red / "Low" amber / "Buy again" accent)
  - Product name (`.headline`)
  - Confidence percentage (`.subheadline.secondary`, monospaced)
  - Stock info: "Stock: 0 · avg every [n] days" (`.caption.secondary`)
  - "Add to List" `PrimaryButton` (compact, accent); fades to "Added ✓" after tap
  - Dismiss icon (`×`, appears on hover; dismisses recommendation for this cycle)

**QR Share Popover** (triggered by QR Share button):
- Displays `QRCodeView` fetched from server
- URL label: `/shopping-helper/<token>` + "Copy Link" button
- Expiry label: "Link expires in [X] hours"
- "Regenerate" link

List behavior:
- Selection: None (checkboxes are the primary interaction, not row selection)
- Row height: 44pt
- Swipe: Trailing: "Remove" (red), "Edit Note" (accent); Leading: none
- Drag-to-reorder: Yes, unchecked items
- Context menu: See §3.5 Shopping list item
- Double-click: Opens note/edit popover
- Keyboard: ↑/↓ to navigate; Space to toggle; Delete to remove; ⌘L is not needed here (already on list)

Empty state (List tab): `cart.circle` SF Symbol, "Your shopping list is empty", "Add items manually or auto-populate from low-stock inventory.", "Add Items" + "Populate from Low Stock" dual CTAs
Empty state (Recommendations tab): `sparkles` SF Symbol, "No recommendations yet", "Upload grocery receipts to build your purchase history.", "Upload Receipt" CTA
Loading state: Skeleton rows (6) while loading; Recommendations tab shows spinner
Error state: Error toast or full-width banner per standard
Hover states: Checkbox animates on hover; Add to List button fades in on rec row hover
Drag-and-drop:
- Accepts: Inventory item rows dragged from Inventory (multi-window use case)
- Produces: Shopping list item rows can be dragged to reorder (handled natively by SwiftUI `List` with `.onMove`)
Vibrancy: Sidebar uses sidebar material; list uses `surface`
Accessibility:
- Checkbox row: "[Product name]. [Purchased / Not purchased]. Source: [source]. Quantity [n]."
- Recommendation row: "[Product name]. Urgency: [Out of stock / Low]. Confidence [n]%. Add to list button."

---

**View 9: Kitchen View**

Window: Main Window
Navigation path: Sidebar → Shopping → "Kitchen" tab (sub-tab alongside List and Recommendations); or sidebar item if a distinct Kitchen View entry is added
Layout pattern: Two-column `LazyVGrid` (adaptive, minimum column 240pt) within the content area; no sidebar split needed
Toolbar items:
- Center: "Kitchen" navigation title
- Right: Refresh button

Content structure:
- **Category grid**: Each cell is a `Card` for one ingredient category (Dairy, Produce, Bakery, Frozen, Pantry, etc.):
  - Card header: Category name (`.title3.semibold`) + category icon (SF Symbol or emoji per §1.9) + total in-stock count badge
  - Card body: `VStack` of ingredient rows, each:
    - Product name (`.body`) + stock quantity
    - Stock indicator: `Text` in `success` color (e.g. "✓ 2") OR `LowStockPill` amber "⚠ 1" or red "✗ 0"
  - Card footer: "Add to Shopping List" `Button(.plain)` (shows popover to pick which item to add, if multiple)
  - Expandable: tap card header to collapse/expand category (via `DisclosureGroup`)
- **Filter bar** above grid: "Show All" | "Low Stock Only" toggle; "Category" multi-select chips

List behavior: N/A (grid layout)
Empty state: `fork.knife.circle` SF Symbol, "Kitchen is empty", "Upload grocery receipts to see what's in stock.", "Upload Receipt" CTA
Loading state: Grid shows 6 skeleton cards (2×3)
Error state: Error toast
Hover states: Cards elevate slightly; item rows highlight; "Add to List" link appears on row hover
Drag-and-drop: None in this view
Vibrancy: No
Accessibility:
- Each category card: "Category: [name]. [N] items. [N] low stock."
- Each ingredient row: "[name], [quantity] in stock."

---

**View 10: Fixed Bills**

Window: Main Window
Navigation path: Sidebar → Fixed Bills (⌘3)
Layout pattern: Single-column list (full content width); optional right-side detail panel for payment history when a bill is selected
Toolbar items:
- Left: Sidebar toggle
- Center: "Fixed Bills" navigation title with current month indicator "May 2026"
- Right: Add Obligation button (⌘N, `plus.circle`), month navigation `<` / `>` arrows

Content structure:
- **Month summary bar**: Expected total vs paid total + `ProgressBar` (green/amber/red per % paid)
  - e.g. "$1,882 paid of $2,200 expected this month (86%)"
- **Bills list** (`List` with `ForEach`):
  - Section "Due This Month" (billing cycle matches current month per §1.7 rule 5)
  - Section "Not Due This Month" (collapsed by default via `DisclosureGroup`)
  - Each row (56pt height):
    - Obligation label — `InlineEditableCell` (double-click or F2 to rename; saves on blur/Return per §1.8)
    - Billing cycle badge (`CategoryChip`: Monthly / Quarterly / Annual)
    - Expected amount (`.mono-body`, right-aligned)
    - Paid amount (`.mono-body`, right-aligned; `success` color if paid, `warning` if partial/unpaid)
    - Status indicator `LowStockPill` variant: "Paid ✓" (success-dim), "Due" (warning-dim), "Overdue ⚠" (error-dim)
    - Row background: `paid-bill` | `unpaid-bill` | `overdue-bill` token
    - Plaid link icon (`link.circle`, small, trailing): accent color if linked, muted if not
- **Add Obligation sheet** (triggered by `+` toolbar or ⌘N):
  - Obligation label `TextField`
  - Expected monthly amount `TextField` with `$` prefix
  - Billing cycle `Picker(.segmented)`: Monthly / Quarterly / Semiannual / Annual
  - Provider lookup `TextField` with autocomplete against `bill_providers` (optional)
  - "Add" `PrimaryButton` + "Cancel"
- **Payment History panel** (trailing, 280pt; shown on row selection):
  - List of past payment records with dates and amounts
  - Plaid match indicator per payment

List behavior:
- Selection: Single row (for history panel)
- Row height: 56pt
- Swipe: Trailing: "Mark Paid" (Space also works), "Link Plaid"
- Drag-to-reorder: No
- Context menu: See §3.5 Fixed bill row
- Double-click action: Enter inline rename mode for label field
- Keyboard: ↑/↓ navigate; Space = toggle paid/unpaid; F2 = rename; Return = confirm rename; Esc = cancel rename

Empty state: `creditcard.circle` SF Symbol, "No floor obligations yet", "Add your recurring bills to track what's due each month.", "Add First Bill" CTA
Loading state: 4 skeleton rows
Error state: Error toast for load failure; inline row error for PATCH failures ("Failed to mark as paid — Retry")
Hover states: Row highlights `receipt-hover`; Plaid link icon brightens; "Mark Paid" swipe hint visible on trailing edge hover
Drag-and-drop: None
Vibrancy: No
Dark mode notes: Row background tokens (`paid-bill`, `unpaid-bill`, `overdue-bill`) must be visible against `surface` in dark mode
Accessibility:
- Each row: "[Obligation name]. Expected [amount]. [Status: Paid/Due/Overdue]. [Billing cycle]."
- Space bar action announces: "Marked as [paid/unpaid]."

---

**View 11: Plaid Integration**

Window: Main Window
Navigation path: Sidebar → Plaid Accounts (⌘4); Admin-gated for linking; shared view for all authenticated users
Layout pattern: Two-section vertical layout: (A) Linked Accounts list + sync controls; (B) Staged Transactions review list below
Toolbar items:
- Center: "Bank Accounts" navigation title
- Right: Sync button (`arrow.triangle.2.circlepath`), Add Account button (admin only, `plus.circle`)

Content structure:
- **Section A — Linked Accounts** (`List` of `plaid_items` with `plaid_accounts` nested):
  - Each `plaid_item` row (56pt):
    - Bank/institution name + nickname (editable)
    - Account mask (e.g. "••••4242")
    - Account type badge (Checking / Savings / Credit)
    - Balance display (`.mono-body`): current balance; credit accounts show available + limit
    - Status badge: "Active ✓" (success) | "Login Required ⚠" (warning, tappable → re-auth via `ASWebAuthenticationSession`) | "Disconnected" (error)
    - Last sync timestamp (`.caption.secondary`)
    - "Sync Now" button (trailing, compact)
  - "Add Bank Account" button (admin only; launches Plaid Link via `ASWebAuthenticationSession` per §2.6 AC-18)
- **Section B — Staged Transactions** (`List` of `plaid_staged_transactions` with `status = ready_to_import`):
  - Section header: "Staged Transactions ([N] pending)" + "Review All" shortcut
  - Each transaction row (52pt):
    - Merchant name (`.headline`)
    - Date (`.subheadline.secondary`)
    - Amount in `.mono-body` (negative = debit)
    - Auto-suggested receipt type `CategoryChip` (Grocery / Restaurant / Expense)
    - Match indicator: "Matched to receipt [store]" (success color) | "Unmatched" (muted)
    - "Confirm" `PrimaryButton` (compact) + "Dismiss" `SecondaryButton`
  - Keyboard: Return = confirm focused row; Delete = dismiss focused row
  - Empty state for staged transactions: "All caught up! No pending transactions."

List behavior:
- Selection: Single row for detail in Staged Transactions; none for Accounts
- Row height: 52–56pt
- Swipe: Staged transactions trailing: "Confirm" (accent), "Dismiss" (gray)
- Drag-to-reorder: No
- Context menu: See §3.5 Plaid staged transaction row
- Double-click: Opens transaction detail popover
- Keyboard: ↑/↓ navigate; Return confirm; Delete dismiss

Empty state (Accounts): `building.columns.circle` SF Symbol, "No bank accounts linked", "Link your bank account to sync transactions automatically." (admin-only CTA: "Link Account"; non-admin: "Ask your household admin to link a bank account")
Loading state: Skeleton rows for both sections
Error state: Per-account error badge if sync fails; inline toast for confirm/dismiss failures
Hover states: Account rows highlight; "Sync Now" button fades in; Staged transaction "Confirm/Dismiss" buttons always visible (not hover-only)
Drag-and-drop: None
Vibrancy: No
Dark mode: Status badges must be readable; `login_required` amber is especially important
Accessibility:
- Account row: "[Bank name] [account type] ending [mask]. Balance [amount]. Status: [Active/Login required]."
- Transaction row: "[Merchant name], [date], [amount]. Suggested type: [type]. [Matched/Unmatched]."

---

**View 12: Cash Transactions**

Window: Main Window
Navigation path: Sidebar → Cash Transactions (⌘5)
Layout pattern: Two-panel: left = entry form (top) + history list (below); no secondary inspector needed
Toolbar items:
- Center: "Cash Transactions" navigation title + month label
- Right: Month navigation `<` / `>`; Export button (`square.and.arrow.up`)

Content structure:
- **Quick-entry form** (Card, top of content area, always visible):
  - Row 1: Amount `TextField` with `$` prefix (`.mono-body`; numeric keyboard type) + Description `TextField` (free text; placeholder "What was this for?")
  - Row 2: Category `Picker(.menuStyle)` (Grocery / Dining / Health / Transport / Shopping / Other) + Date `DatePicker` (`.compact` style, defaults to today)
  - Row 3: "Log Cash Spend" `PrimaryButton` (⌘Return; full width of form)
  - Validation: Amount must be > 0; description required; both validated on submit
- **History list** (`List` with `ForEach`, grouped by month section headers):
  - Each row (44pt):
    - Description (`.headline`)
    - Category `CategoryChip`
    - Date (`.subheadline.secondary`)
    - Amount (`.mono-body`, right-aligned, negative in `error` color to indicate outgoing)
  - Month totals shown in section header (`.title3.mono`)
  - Sort: Newest first (default)

List behavior:
- Selection: Single (shows edit popover for the row)
- Row height: 44pt
- Swipe: Trailing: "Delete" (red)
- Drag-to-reorder: No
- Context menu: "Edit", "Copy Amount", "Delete"
- Double-click: Opens inline edit popover for amount/description/category/date
- Keyboard: ↑/↓ navigate; Delete to delete (with undo); Return to edit

Empty state: `dollarsign.circle` SF Symbol, "No cash transactions this month", "Log cash spend that didn't come with a receipt.", no CTA (form is always visible above)
Loading state: 4 skeleton rows in history list
Error state: Inline error below form on submit failure; toast on delete failure
Hover states: Row highlights; delete swipe hint visible on trailing edge hover; amount in form field validates in real-time (red border if non-numeric)
Drag-and-drop: None
Vibrancy: No
Accessibility:
- Form: "Amount field. Description field. Category picker. Date picker. Log Cash Spend button."
- History row: "[Description], [category], [date], [amount]."

---

**View 13: Spending by Category (Analytics — v1.0 subset)**

Note: Per §2.4 OUT-OF-SCOPE, full Expense Analytics (screen 16, chart-heavy) is deferred to v1.1. However, the Spending by Category dashboard tile (screen 17) and its drill-down panel are in-scope as a v1.0 feature accessible from the Dashboard. The full analytics screen (bar charts, Sankey) is v1.1. This spec covers the v1.0 inline dashboard drill-down only; the full screen spec is provided for v1.1 implementation reference.

Window: Main Window (accessed via Dashboard tile "View Analytics" CTA or ⌘0 → dashboard tile drill-down)
Navigation path: Dashboard → "Spending" tile → expand drill panel (as the NavigationSplitView trailing column)
Layout pattern: Detail panel (trailing column of NavigationSplitView, ~380pt wide) alongside Dashboard tiles
Toolbar items: (panel-level) Month navigation `<` / `>` arrows; "Export CSV" button (⌘S)

Content structure:
- **Month selector**: `<` / `>` arrows + current month label "May 2026"; month steps update all figures
- **Category breakdown list** (`OutlineGroup` for expandable rows — §2.2 enhancement for screen 17):
  - Each category row (48pt):
    - Category name (`.headline`)
    - Horizontal `ProgressBar` (proportional fill relative to highest category)
    - Total amount (`.mono-body`, right-aligned)
    - Percentage of total (`.caption`, muted)
    - Row expands via `DisclosureGroup` to show receipts in that category:
      - Receipt sub-rows: store name + date + amount (Return or click to open Receipt Inspector)
  - Fixed obligations row: "Fixed" label → expands to show individual floor obligations with paid/expected amounts (§1.7 rules 5 and 9: Fixed is a separate row per §2.2)
  - Cash row: "Cash Spend" label → expands to show cash transaction entries
- **Summary row** at bottom: "Total: $[amount] across [N] receipts"

Empty state (for selected month): `chart.bar.xaxis` SF Symbol, "No spending data for [month]", no CTA
Loading state: 5 skeleton rows with bar placeholders
Error state: Error banner "Failed to load analytics. Retry."
Hover states: Category rows highlight; expand arrow appears on hover; receipt sub-rows highlight on hover
Drag-and-drop: None
Vibrancy: No
Accessibility:
- Category row: "[Category name], [amount], [percentage of total]."
- Disclosure expanded: "[Store name], [date], [amount]."

---

**View 14: Settings (Preferences Window)**

Window: Settings window (SwiftUI `Settings` scene, ⌘,)
Navigation path: Any screen → ⌘, or LocalOCR menu → Preferences
Layout pattern: macOS native Settings window with `TabView` (`.automatic` style renders as macOS tab selector)
Toolbar items: Tab selector at top (5 tabs: General, Account, Receipts, Notifications, Advanced)

*(Full pane specifications are in §3.8 — this entry covers the shell and cross-pane behavior.)*

Content structure shell:
- Fixed window size (560 × 440 pt, non-resizable per macOS HIG)
- `TabView` with `.tabViewStyle(.automatic)` — macOS renders this as a segmented tab bar at the top of the window
- Each tab has its own `ScrollView` for overflow content
- "Apply" / "Save" pattern: changes are saved immediately on edit (no explicit Apply button) except for server URL (requires "Connect" to test connectivity)
- Admin-only panes: No pane is hidden for non-admin users; instead, admin-only controls within panes are disabled with a tooltip "Admin access required"

Loading state: Settings window opens instantly; data fetches happen per-tab on first selection
Error state: Per-control inline error (e.g. invalid URL format in Advanced)
Hover states: Standard macOS control hover behavior (system-managed)
Drag-and-drop: None
Vibrancy: None (Settings windows use `windowBackgroundColor` only)
Accessibility: All form controls have VoiceOver labels; tab bar reads as "Settings tabs: General, Account, Receipts, Notifications, Advanced"

---

**View 15: Auth and Members**

Window: Main Window (content area when navigating from sidebar; also accessible from Settings → Account pane)
Navigation path: Sidebar → (if exposed as Settings sub-view) → Members; OR Settings → Account tab → "Manage Members" link
Layout pattern: Single-column list with action controls at top; admin controls gated per §1.7 rule 2
Toolbar items:
- Center: "Members" navigation title
- Right: "Invite Member" button (admin only, `person.badge.plus`)

Content structure:
- **Current user card** (top, Card style):
  - Avatar emoji + name + email
  - Role badge (`.headline`): "Admin" (accent) | "Member" (muted)
  - "Sign Out" `DestructiveButton` (confirmation sheet before clearing Keychain and presenting Login)
  - "QR Login Code" popover button (`qrcode`) — displays `QRCodeView` for current user's login QR (60-min expiry; from `/auth/qr-image`)
- **Household Members list** (`List`):
  - Each row (52pt):
    - Avatar emoji + name (`.headline`) + email (`.subheadline.secondary`)
    - Role badge: "Admin" (accent-dim) | "Member" (muted)
    - "Remove" `DestructiveButton` (admin only; confirmation sheet before DELETE)
  - Admin row (the current user's own row): "That's you" label; no Remove button
- **Household Members (non-auth persons, from `household_members` table)**:
  - Sub-section "Household Members (for medication tracking)":
    - Each row: name + age group (Adult / Child)
    - "Add Household Member" `Button(.plain)` with `+` icon (opens add-person sheet)
- **Trusted Devices section**:
  - Each device row: device name + scope badge + last-seen timestamp + "Revoke" `DestructiveButton`
  - "Pair New Device" button (`plus.circle`) → displays pairing QR + polls status per §1.6 device pairing flow
- **Invite flow** (admin only):
  - "Invite Member" button opens sheet: email TextField + "Send Invite" button (copies invite link to clipboard + opens mail compose via `NSSharingService`)

List behavior:
- Selection: None (no detail view needed for members)
- Row height: 52pt
- Swipe: Trailing: "Revoke" for devices; "Remove" for members (admin only)
- Context menu: "Copy Email", "Remove Member" (admin)

Empty state (no non-auth household members): "Add household members to track medications per person."
Loading state: 3 skeleton rows
Error state: Inline toast for API failures
Hover states: "Remove" button fades in on row hover; "Revoke" button fades in on device row hover
Drag-and-drop: None
Vibrancy: No
Accessibility:
- Member row: "[Name], [email], [role]."
- Device row: "[Device name], [scope]. Last seen [date]."

---

**View 16: Contributions**

Window: Main Window
Navigation path: Sidebar → Contributions (⌘6)
Layout pattern: Two-section vertical: (A) Monthly leaderboard; (B) Per-member event history (shown when a member is selected)
Toolbar items:
- Center: "Contributions" navigation title + month label "May 2026"
- Right: Month navigation `<` / `>` arrows

Content structure:
- **Monthly leaderboard** (top half, `List`):
  - Section header: "May 2026 Leaderboard"
  - Each row (52pt):
    - Rank badge (medal SF Symbols: `medal.fill` gold/silver/bronze for top 3; plain number for rest)
    - Avatar emoji + member name (`.headline`)
    - Points total (`.mono-body`, right-aligned, accent color)
    - Receipt count (`.caption.secondary`)
    - Tap row to expand event history below
- **Event history** (bottom half; shown when a member row is selected — `DisclosureGroup` or `NavigationLink`):
  - Section header: "[Member name]'s contributions this month"
  - Each event row (44pt):
    - Event type label (`.headline`) — e.g. "Receipt Processed", "OCR Cleanup"
    - Points delta (`.mono-body`, `success` color, e.g. "+5")
    - Date/time (`.caption.secondary`)
    - Related receipt or inventory item link (`.caption`, accent color; taps to Receipt Inspector)
  - Points reset note at bottom: "Points reset on June 1."

List behavior:
- Selection: Single member row (to show event history below)
- Row height: 52pt (leaderboard), 44pt (events)
- Swipe: None
- Drag-to-reorder: No
- Context menu: "View event history", "Copy member name"
- Double-click: Navigates to member detail (same as single tap selection)
- Keyboard: ↑/↓ navigate; Return to select and expand history

Empty state (leaderboard): `trophy.circle` SF Symbol, "No contributions yet this month", "Upload receipts to earn points and top the leaderboard.", "Upload Receipt" CTA
Loading state: 3 skeleton rows
Error state: Error toast
Hover states: Row highlights; medal badge brightens
Drag-and-drop: None
Vibrancy: No
Accessibility:
- Leaderboard row: "Rank [n]. [Name]. [Points] points. [N] receipts this month."
- Event row: "[Event type]. [+N] points. [Date]."

---

**View 17: Menu Bar Popover**

Window: NSPopover attached to NSStatusItem (§3.2 Window: Menu Bar Popover)
Navigation path: Menu bar icon click → popover appears
Layout pattern: Fixed 300×360pt popover; vertical stack of sections
Toolbar items: None (popover, no toolbar; has a close "×" button in top-right corner)

Content structure:
- **Header row**: App icon (16pt) + "LocalOCR" label (`.headline`) + close button (`×`, top-right, dismisses popover)
- **Status section** (Card, compact):
  - Low-stock count: "🛒 [N] items low" in warning color (or "All stocked ✓" in success)
  - Last server sync: "Synced [N] min ago" in `.caption.secondary`
- **Quick Actions section**:
  - "Upload Receipt" button (`camera.viewfinder` SF Symbol + label, full-width `SecondaryButton`) — opens OCR Upload panel (detaches from menu bar context)
  - "Open Shopping List" button (`cart` + label, full-width) — brings Main Window to front on Shopping screen
  - "Open App" button (`arrow.up.right.square` + label, full-width) — brings Main Window to front on Dashboard
- **Quick Add Cash** (Card, expandable via disclosure):
  - Collapsed: "Quick Add Cash Transaction" with `chevron.down` icon
  - Expanded: inline form (Amount `TextField` + Description `TextField` + Category `Picker` + "Log" button; ⌘Return submits)
  - On success: brief "Logged ✓" feedback, form collapses
- **Footer**: Server URL (`.caption.secondary`, truncated) + "Settings" link (opens Settings window)

List behavior: N/A
Empty state: N/A (status is always shown)
Loading state: "Refreshing…" spinner in status section for 1–2 sec on popover open while fetching fresh count
Error state: "Cannot reach server" label in error color in status section + "Retry" link
Hover states: Action buttons highlight on hover; "Quick Add Cash" header highlights on hover
Drag-and-drop: Accepts dropped receipt files → opens OCR Upload panel (same behavior as main window drop target)
Vibrancy: `.menu` material (translucent menu-style vibrancy)
Dark mode notes: Popover uses system popover appearance — automatically adapts; do not hardcode background
Accessibility:
- Status: "Low stock: [N] items."
- Action buttons: fully labeled
- Quick Add Cash: "Quick add cash transaction, collapsed. Activate to expand."

---

**View 18: Demo Mode**

Demo mode is a cross-cutting UI state, not a standalone screen. It overlays the existing screen with:
- `DemoModeBanner` (always visible at top of main content area, above all content — amber `warning-dim` background, "👁 Demo Mode — read-only. Sign in to save." label + "Sign In" `PrimaryButton`)
- Write actions gated: all `PrimaryButton` instances that perform write operations are replaced (not hidden) with identically sized buttons that on-tap present a `Toast` ("Demo mode — sign in to save") instead of calling the API
- The entire nav, sidebar, and read actions function normally
- Demo mode is entered by tapping "Try Demo" on the Login view
- Demo mode is exited by tapping "Sign In" in the banner → presents Login view as a sheet
- Per §1.7 rule 10 and §2.6 AC-13: no write API call is ever made from a demo session

---

### 3.8 PREFERENCES WINDOW SPEC

The Preferences window is implemented as a SwiftUI `Settings` scene (⌘,). It uses `TabView` with `.tabViewStyle(.automatic)`, which renders as a macOS-native icon+label tab selector. Window is fixed size 560×440pt (non-resizable per macOS HIG).

Important: Credentials (server URL, session cookie, AI API key selection) are stored in **Keychain Services** (SecItemAdd/SecItemCopyMatching), never in UserDefaults. UserDefaults stores only non-sensitive preferences (appearance, default tab, notification time).

---

**Pane 1: General**

Icon: `gearshape` SF Symbol

| Setting | Control | UserDefaults Key | Default | Notes |
|---|---|---|---|---|
| Appearance | `Picker(.segmented)`: "System" / "Light" / "Dark" | `preferredAppearance` | `"system"` | Written on change; read at launch to set `NSApp.appearance` |
| Default landing tab | `Picker(.menuStyle)`: Dashboard / Inventory / Shopping / Fixed Bills / … | `defaultLandingTab` | `"dashboard"` | Written on change; read at cold launch to navigate to that tab |
| Default OCR model | `ModelPicker` (loads from `/ai-models`; saves model config ID) | `defaultOCRModelConfigId` | `nil` (uses user's `active_ai_model_config_id` from server) | Written on change; model ID also stored in Keychain per §1.8 |
| Show low-stock badge in menu bar | `Toggle` | `menuBarShowLowStock` | `true` | Controls NSStatusItem badge visibility |
| Launch at login | `Toggle` (writes `SMAppService.mainApp.register()`) | — (SMAppService) | `false` | macOS 13+ `SMAppService` API |

---

**Pane 2: Account**

Icon: `person.circle` SF Symbol

Content:
- **Signed-in user card**: Avatar emoji + name + email + role badge (read from `/auth/me`)
- **Server URL field**: `TextField` showing current server URL (from Keychain) + "Change" button → reveals editable field + "Connect" button (tests `/auth/config`; on success writes new URL to Keychain and triggers re-auth)
- **Household**: household name display (read-only from server; no renaming in macOS app v1.0)
- **QR Login Code**: "Show My QR Code" button → popover with `QRCodeView` + expiry label
- **Sign Out**: `DestructiveButton` "Sign Out of [name]" → confirmation sheet → clears Keychain session cookie + cookie storage + navigates to Login
- **Manage Members**: "Open Members" link → opens Members view (View 15) in main window

| Setting | Control | UserDefaults Key | Default | Notes |
|---|---|---|---|---|
| Server URL | `TextField` (Keychain) | — | — | Stored in Keychain: `service: "com.localocr.server_url"` |
| Session cookie | (managed by HTTPCookieStorage + Keychain) | — | — | NOT a user-visible setting; cleared on sign out |

---

**Pane 3: Receipts**

Icon: `doc.text.viewfinder` SF Symbol

| Setting | Control | UserDefaults Key | Default | Notes |
|---|---|---|---|---|
| Auto-rotate landscape receipts | `Toggle` | `autoRotateReceipts` | `true` | Note: rotation is server-side (Pillow per §1.7 rule 3); this toggle controls whether the macOS app sends a rotation hint header |
| Default receipt type | `Picker(.segmented)`: "Auto" / "Grocery" / "Restaurant" / "Expense" | `defaultReceiptType` | `"auto"` | Pre-selects the receipt type picker in OCR Upload |
| Show OCR confirmation before saving | `Toggle` | `requireOCRConfirmation` | `true` | If false, confirmed receipts skip Review and Edit (advanced) |
| Low-confidence item threshold | `Slider` (0–100%) | `lowConfidenceThreshold` | `75` | Items below this confidence percentage are highlighted amber in Review and Edit |
| Attribution prompt | `Picker(.segmented)`: "Always" / "When unset" / "Never" | `attributionPromptBehavior` | `"when_unset"` | Controls when the Attribution Picker sheet (§3.7 View 5) is shown |

---

**Pane 4: Notifications**

Icon: `bell` SF Symbol

| Setting | Control | UserDefaults Key | Default | Notes |
|---|---|---|---|---|
| Shopping nudge enabled | `Toggle` | `shoppingNudgeEnabled` | `true` | If true, schedules daily `UNNotificationRequest` at nudge time |
| Shopping nudge time | `DatePicker` (`.hourAndMinute` components only) | `shoppingNudgeTime` | `09:30` | Time stored as `HH:mm` string; macOS app schedules local notification at this time daily |
| Nudge only when low-stock exists | `Toggle` | `nudgeOnlyWhenLowStock` | `true` | If true, macOS app pre-checks inventory count before scheduling; if 0 low-stock, skips |
| Minimum low-stock items for nudge | `Stepper` (1–20) | `nudgeMinLowStockItems` | `3` | macOS-local threshold (lower than server's `SHOPPING_NUDGE_MIN_RECS=8` is fine) |
| Medication refill alerts | `Toggle` | `medicationRefillAlerts` | `true` | `[DEFERRED — Medications is v1.1; stub the toggle now]` |
| Plaid login-required alert | `Toggle` | `plaidLoginRequiredAlert` | `true` | Fires `UNNotificationRequest` when a Plaid item status changes to `login_required` |

Notification permission banner: If `UNUserNotificationCenter.authorizationStatus == .denied`, shows amber info banner "Notifications are disabled in System Settings." + "Open Notification Settings" button (deep-links to `x-apple.systempreferences:com.apple.preference.notifications`).

---

**Pane 5: Advanced**

Icon: `wrench.and.screwdriver` SF Symbol

| Setting | Control | UserDefaults Key | Default | Notes |
|---|---|---|---|---|
| Server URL (also in Account) | `TextField` | — (Keychain) | — | Repeated here for discoverability; same field as Account pane |
| Debug logging | `Toggle` | `debugLoggingEnabled` | `false` | If true, HTTP request/response bodies are written to a log file in `~/Library/Logs/LocalOCR/` |
| Log level | `Picker(.menuStyle)`: "Error" / "Warning" / "Info" / "Debug" | `logLevel` | `"error"` | Enabled only when debug logging is on |
| Reset local cache | `Button(.bordered)` "Clear Cache" | — | — | Clears `shoppingListCache`, `inventoryAllItemsCache`, URLSession cache; forces fresh fetches |
| Export diagnostic log | `Button(.bordered)` "Export Log…" | — | — | `NSSavePanel` to save the log file |
| Backup & Restore | `Button(.borderedProminent)` "Open Backup Manager…" | — | — | Opens a sheet with full backup/restore UI (admin only): lists backups from `/system/backups`, "Create Backup" button, "Restore" button with confirmation |
| Telegram webhook URL | `TextField` (read-only, from server config) | — | — | Displayed for reference; configure in server `.env` |
| Telegram chat ID | `TextField` | — (server-side config) | — | Admin only; POSTs to server settings endpoint |
| App version | `Text` (read-only) | — | — | "[Version] ([Build]) — [commit hash]" |
| Acknowledgements | `Button(.plain)` "View Open Source Licenses" | — | — | Opens `OSAcknowledgements.plist` / custom HTML view |

---

### 3.9 macOS-NATIVE INTERACTION PATTERNS

This section documents macOS-specific interaction mechanics that apply across multiple views. Each pattern references the views and §1.8 complexity flags that require it.

---

**Drag-and-Drop Within the App**

| Drag source | Drop target | Effect | Views |
|---|---|---|---|
| Shopping list item row | Another row in the same list | Reorder item; calls PATCH `/shopping/<id>` with new position | View 8 (Shopping List) |
| Inventory item row (multi-window) | Shopping List window | Adds item to the active shopping session | View 7 + View 8 (multi-window §2.3 feature #6) |
| Receipt thumbnail (in Receipt Inspector) | Finder / Desktop | Exports receipt image as PNG file via `NSDragOperation.copy` | Receipt Inspector |

Implementation: Shopping list reorder uses SwiftUI `List` with `.onMove(perform:)` modifier + `@State private var items` array. Inventory → Shopping drag uses `itemProvider` on the source row (UTType `com.localocr.inventory-item`) and a custom `onDrop` handler on the Shopping List view. Receipt → Finder drag uses `NSItemProvider` with `loadFileRepresentation(forTypeIdentifier:)`.

---

**Drag from Finder into the App**

Triggered when the user drags a receipt file (PDF, JPEG, PNG, HEIC) from Finder onto any of: the Dock icon, the app window (any screen), or the DropZone in OCR Upload.

Entry points and handling:
1. **Dock icon drop**: `NSApplicationDelegate.application(_:open:)` fires with the file URLs → app comes to front → OCR Upload panel opens with the first file pre-filled
2. **App window drop** (any screen): `ContentView.onDrop(of: supportedTypes, delegate: ReceiptDropDelegate)` intercepts the drop → presents OCR Upload panel as a sheet with file pre-filled
3. **DropZone explicit drop**: Handled by the DropZone component's `.onDrop` modifier (see §3.6 DropZone)

Accepted `UniformTypeIdentifiers`: `[.jpeg, .png, .heic, .pdf]` (`public.jpeg`, `public.png`, `public.heic`, `com.adobe.pdf`).

Multiple files dropped simultaneously: queued in order; OCR Upload panel processes one at a time, advancing to the next after Confirm or Skip.

---

**Drag from App to Finder / Desktop**

The Receipt Inspector supports dragging the receipt photo out of the app to Finder or any drag-accepting target.

Implementation: `Image` or thumbnail in Receipt Inspector implements `onDrag {}` returning an `NSItemProvider` with the receipt image data (fetched from server, cached in memory for the drag operation). The drag preview shows a thumbnail of the receipt image at 50% opacity.

---

**Undo / Redo**

`UndoManager` is scoped per window (each `NSWindow` gets its own `UndoManager` via SwiftUI's `@Environment(\.undoManager)`). Undoable operations:

| Action | What is undone | Scope |
|---|---|---|
| Add item to shopping list | Removes the item from the list (DELETE API call) | Shopping List window |
| Remove item from shopping list | Re-adds the item (POST API call) | Shopping List window |
| Mark shopping item purchased | Toggles back to open | Shopping List window |
| Mark bill paid | Toggles back to unpaid | Fixed Bills window |
| Inline rename of floor obligation | Reverts to previous name (PATCH API call with old value) | Fixed Bills window |
| Log cash transaction | Deletes the transaction (DELETE API call) | Cash Transactions window |

Operations that are NOT undoable (server-initiated or multi-step):
- Confirming a receipt (too many downstream effects on inventory)
- Re-running OCR
- Linking a Plaid transaction
- Settling dining debts
- Signing out

---

**Auto-Save**

The app uses server-side persistence — there is no client-side document model and therefore no auto-save mechanism in the traditional NSDocument sense. Changes are saved to the server immediately on action (blur, Return, button tap). If a network request fails, the UI reverts to the last known server state and shows an error toast. There is no draft/unsaved state except within modal sheets (which are abandoned on Cancel/Esc without any API call).

---

**Toolbar Customization**

Not offered. The toolbar set for each window is curated and fixed. Rationale: the toolbar content is domain-specific and tightly coupled to the screen's actions; offering customization would require maintaining a toolbar item pool that adds complexity without meaningful user benefit for a household app with a small target audience.

---

**Full-Screen Layout**

| Element | Full-Screen Behavior |
|---|---|
| Sidebar | Persists in full screen; accessible via mouse hover at left edge |
| Toolbar | Auto-hides when scrolling; revealed by moving mouse to top |
| Inspector panel | Persists; accessible via ⌃⌘I toggle |
| Menu bar | Auto-hides per macOS full-screen convention; revealed by mouse-to-top |
| Stage Manager | Supported automatically (no special handling required); window continues to function as a Stage Manager tile |
| Menu bar status icon | Persists in full-screen space; popover opens over the full-screen window |

---

**Background Fetch and Foreground Refresh**

Per §2.6 AC-09: when the app transitions from background to foreground (`NSApplicationDelegate.applicationDidBecomeActive`), the app fires a lightweight refresh sequence:

1. GET `/inventory` (for low-stock count in menu bar badge and Dashboard)
2. GET `/plaid/items` (to detect `login_required` status changes)
3. GET `/shopping` (to refresh shopping list state)

Each refresh is gated by a 60-second minimum interval (last-refresh timestamp stored in `@AppStorage`) to avoid hammering the server when the user rapidly cycles between apps.

The refresh fires asynchronously via Swift `async/await` (`Task { await refreshAll() }`); the UI does not block or show a loading state for background refreshes — only the individual view's data is updated when it resolves.

---

**Continuity Camera**

Available on macOS 13+ when an iPhone is on the same Wi-Fi network and satisfies Apple's Continuity Camera requirements.

In the OCR Upload panel (View 4), the Continuity Camera source appears automatically in the source picker alongside "Browse Files" when `AVCaptureDevice.DiscoverySession(deviceTypes: [.continuityCamera], mediaType: .video, position: .back)` returns a non-empty list.

User flow:
1. OCR Upload panel open → source picker shows "iPhone Camera" option
2. User selects "iPhone Camera" → `AVCaptureSession` starts → iPhone camera UI appears on iPhone simultaneously
3. User photographs receipt on iPhone → image transferred to Mac → pre-filled in DropZone → OCR proceeds

No manual pairing or setup required (automatic per macOS 13+ Continuity Camera handshake).

---

**Notification Center Integration**

Implemented via `UNUserNotificationCenter`. The macOS app schedules local notifications — it does not rely on the Telegram nudge (server-side) for macOS delivery.

Permission request: Called once at first launch after login via `UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])`. If denied, a one-time settings banner is shown (per §3.8 Pane 4).

Notification types and `UNNotificationAction` payloads:

| Notification | Trigger | Action buttons | Deep-link |
|---|---|---|---|
| Shopping nudge | Daily at user-configured time (default 09:30); only when low-stock count ≥ min threshold | "View Shopping List" | Opens main window → Shopping List tab |
| Plaid login required | On foreground refresh when `login_required` status detected | "Re-authorize" | Opens main window → Plaid Accounts screen |
| Medication refill alert (v1.1) | When medication quantity ≤ low_threshold | "View Medications" | Opens main window → Medications screen |

All notifications are delivered even when the app is not in the foreground. The app does not use push notifications (APNs) — all notifications are local and scheduled by the app itself.

---

*End of Section 3 — DESIGN SYSTEM & VIEW SPECS*

---

## 4. TECHNICAL ARCHITECTURE
*Authored by: [AGENT 4 — SOLUTIONS ARCHITECT]*

### 4.1 FRAMEWORK DECISION

Three options were evaluated against the concrete constraints established in Sections 1–3.

---

**Option A — Tauri 2** (Rust shell + existing web frontend)

- **Pro**: Produces a very small ARM64 binary (~10–15 MB); native system APIs callable from Rust via `tauri-plugin-*` crates; WKWebView rendering; active macOS support.
- **Con**: The primary advantage of Tauri — frontend reuse — does not apply here. The existing frontend (§1.1) is a 40,050-line monolithic `index.html` with embedded CSS and JavaScript, no module boundaries, no build pipeline (webpack/vite/esbuild), and no component framework. To place it inside Tauri, the build agent would need to either (a) serve the entire raw file from a local asset or embedded webserver, producing a browser-in-a-desktop-window experience with none of the HIG compliance that justifies a native app, or (b) systematically extract its ~180 page-section JS functions, introduce import statements, and rebuild a module-aware SPA — which is a full frontend rewrite of comparable scope to a SwiftUI rewrite. The WKWebView approach also carries scroll-performance risk on long data tables (Inventory with 200+ rows, Receipts list with 100+ entries) because the browser's scroll engine runs off the main thread only when compositing layers, and a monolithic DOM page does not layer-compose cleanly. Furthermore, Tauri's Rust bridge adds implementation surface for every native feature in §2.3 — global hotkeys require `tauri-plugin-global-shortcut`, menu bar requires `tauri-plugin-menu`+`tray-icon`, Continuity Camera requires a custom Rust/Swift FFI, Spotlight indexing requires CoreSpotlight FFI. All of this is extra code between the UI and the platform.
- **Best when**: The existing frontend is a clean React/Vue/Svelte SPA with a build pipeline — NOT this project.

---

**Option B — Electron** (Node.js shell + existing web frontend)

- **Pro**: Same frontend reuse story as Tauri; Node.js ecosystem; relatively large community; well-documented macOS-specific APIs via `@electron/remote`, `shell`, `Menu`, `Tray`, `nativeTheme`.
- **Con**: The same 40,050-line HTML problem as Option A, compounded by a much larger distribution: ~150–200 MB app bundle, ~250 MB RAM idle (Chromium + Node.js + app code), and significantly weaker macOS HIG compliance. Electron apps cannot pass App Store review without major changes (moot for this project, per §2.1, but the ergonomics argument still stands — Chromium does not render SwiftUI-equivalent native controls). The `NSVisualEffectView` sidebar vibrancy, the `NSOpenPanel` file picker animations, the native `DatePicker`, the `List` row recycle — these are all recreated poorly in Chromium or require bridging back to AppKit anyway. Electron also has no Continuity Camera path without a custom Swift/ObjC plugin. Notarization with Electron is possible but requires `--no-sandbox` or a specially structured Electron forge config that has historically caused Gatekeeper issues.
- **Best when**: The project needs deep Node.js ecosystem access or already has a large Electron plugin library invested — not this project.

---

**Option C — SwiftUI + AppKit** (pure native)

- **Pro**: Best-in-class macOS HIG compliance. Native `List`, `NavigationSplitView`, `NSTextField`, `NSOpenPanel`, `NSStatusBar` — all the primitives that §3.6 and §3.7 already specify. Every desktop-exclusive feature in §2.3 (global shortcut, Finder drag, Continuity Camera, Spotlight, Quick Look, Notification Center, Keychain) is a first-party Apple API with no FFI layer. SwiftCharts (macOS 13+) covers the analytics views. PDFKit handles receipt PDFs in the inspector. `CoreImage.CIQRCodeGenerator` handles QR rendering. Scroll performance is native — `List` uses `NSTableView` under the hood and recycled rows; 1,000-row Inventory lists are not a performance problem. The app binary will be approximately 30–50 MB including Swift runtime stubs (arm64 slice only for v1.0 per §2.1). Idle memory: approximately 50–80 MB (measured reference: a SwiftUI + URLSession client with similar data complexity). The existing `NSCookieStorage.shared` / `URLSession` stack natively replicates the browser cookie jar used by the web app (§1.6), with no extra library.
- **Con**: Full rewrite of every screen. Swift is required. Estimated MVP build time: 6–8 weeks for a competent Swift developer executing against the detailed view specs in §3.7 (approximately 500–700 LOC per major view × 16 MVP views + shared infrastructure). The web app's 40,000 lines of JS/CSS cannot be copy-pasted; every screen must be re-implemented from the functional spec.
- **Best when**: A data-heavy app with macOS-native interactions, where the web frontend is not extractable, and where HIG compliance and system integration are first-class requirements — THIS project.

---

**DECISION: Option C — SwiftUI + AppKit (pure native)**

**Justification (linked to prior sections):**

The web frontend (§1.1) is a 40,050-line single-file vanilla JS app with no framework, no module system, and no build pipeline. The core advantage of Tauri/Electron — frontend reuse — is void. Adapting the existing HTML to any webview-based shell would require a substantial refactor that consumes the same engineering effort as a SwiftUI rewrite, while producing an inferior product. Section 3's view-by-view design (§3.7) was already drafted against SwiftUI primitives: `NavigationSplitView`, `List`, `Form`, `ToolbarItem`, `Settings scene`, `GroupBox`, `SwiftCharts`, `WKWebView` (Sankey only). Building against a specification that already speaks SwiftUI eliminates interpretation ambiguity for the build agent.

Every §2.3 desktop-exclusive feature is a first-party SwiftUI or AppKit API with no Rust bridge or Node.js module required:

| §2.3 Feature | Native API | No FFI needed |
|---|---|---|
| Global shortcut ⌃⌘R | `NSEvent.addGlobalMonitorForEvents` | Yes |
| Finder drag-to-Dock | `NSApplicationDelegate.application(_:open:)` | Yes |
| Menu bar status icon | `NSStatusBar.system.statusItem` | Yes |
| Notification Center nudge | `UNUserNotificationCenter` | Yes |
| Continuity Camera | `AVCaptureDeviceDiscoverySession(.continuityCamera)` | Yes |
| Spotlight indexing | `CSSearchableIndex` | Yes |
| Quick Look (v1.1) | `QLPreviewingController` extension | Yes |
| Keychain | `Security` framework / KeychainAccess SPM | Yes |
| Touch ID (v1.1) | `LocalAuthentication.LAContext` | Yes |

Distribution (§2.1) is Developer ID / direct, so App Store sandbox is not a constraint. The Developer ID path with Hardened Runtime and notarization is the standard path for self-hosted tooling targeting technical household operators.

**Language**: Swift 5.10+. Use Swift 6 concurrency (`@MainActor`, `Sendable`, `async/await`) if Xcode 16+ is available; if only Xcode 15 is available, target Swift 5.10 and use `@MainActor` selectively. All new async code must compile with Swift 6 concurrency warnings enabled.

**UI framework**: SwiftUI primary. AppKit interop for the following specific cases only:
- `NSVisualEffectView` — sidebar vibrancy / material
- `NSOpenPanel` / `NSSavePanel` — file open/save dialogs
- `NSEvent.addGlobalMonitorForEvents` — global keyboard shortcut (requires AppKit; SwiftUI has no equivalent)
- `NSStatusBar` + `NSStatusItem` — menu bar item (SwiftUI `.menuBarExtraStyle` introduced in macOS 13 may be used instead; prefer it for simpler implementation)
- `NSPasteboard` — drag-and-drop paste board access beyond `.onDrop`
- `QLPreviewPanel` — Quick Look triggering (v1.1)
- `UndoManager` — accessed via SwiftUI `@Environment(\.undoManager)` where possible, AppKit `NSUndoManager` only for window-scoped registration

**Minimum macOS**: 13.0 Ventura. This unlocks: `NavigationSplitView`, `SwiftCharts`, `Continuity Camera`, `SMAppService` (login item), `.menuBarExtra` scene modifier, `ShareLink`, and `PresentationDetent`. Dropping below 13 would require availability guards on all of these — not justified given the target audience of M-series Mac owners running a self-hosted Docker stack.

**Architecture pattern**: MVVM with `@Observable` (macOS 14+ / Swift 5.9 Observation framework) for new state objects, or `ObservableObject` + `@Published` for macOS 13 compatibility. Because §2.1 sets minimum macOS 13, and the Observation framework requires macOS 14, the build agent must use `ObservableObject` + `@Published` for all state objects and may conditionally adopt `@Observable` behind an `#available(macOS 14, *)` guard only for components that have a macOS 14+ minimum set.

**Xcode**: 15.0+ required (first Xcode with stable `NavigationSplitView` + `SwiftCharts`). 16.0+ recommended (Swift 6 concurrency, improved previews, faster indexing).

---

### 4.2 PROJECT STRUCTURE

Exact directory and file tree the build agent must create. Every folder and file includes a one-line purpose comment. Files marked `[v1.1]` are stubbed in v1.0 (empty Swift file with a `// TODO: v1.1` comment) but are included in the tree so the directory layout is complete and Xcode's group tree does not need restructuring later.

```
LocalOCR.macOS/
├── LocalOCR.xcodeproj/                         # Xcode project; generated by Xcode, NOT hand-edited
│   └── project.pbxproj                         # Xcode build graph; include in version control
├── LocalOCR/                                   # Main app target (com.localocr.macos)
│   │
│   ├── LocalOCRApp.swift                       # @main App struct; WindowGroup + Settings scene composition; URL scheme handler (openURL)
│   ├── Info.plist                              # Bundle ID, display name, NSCameraUsageDescription, CFBundleURLTypes (localocr:// scheme), LSMinimumSystemVersion 13.0
│   ├── LocalOCR.entitlements                   # Hardened Runtime entitlements (see §4.6 for full entry list)
│   │
│   ├── App/
│   │   ├── AppDelegate.swift                   # NSApplicationDelegate; applicationDidBecomeActive (foreground refresh); application(_:open:) for Dock drops; applicationShouldTerminateAfterLastWindowClosed (returns false — app hides to menu bar)
│   │   ├── AppState.swift                      # @MainActor ObservableObject; global auth state, household state, server reachability flag, low-stock count for menu bar badge
│   │   ├── Router.swift                        # Tab/column selection enum; handleURL(_:) for localocr:// deep links; openWindow coordination
│   │   └── Constants.swift                     # UserDefaults key constants, URL scheme host strings, notification category IDs, API path constants that are not view-local
│   │
│   ├── Design/
│   │   ├── DesignTokens.swift                  # Color token extensions on Color matching §3.1 palette (bg, card, border, accent, success, warning, error, muted); dark/light adaptive where needed
│   │   ├── Typography.swift                    # Font role extensions on Font matching §3.1 type scale (display, title1–3, headline, body, subheadline, caption, monoBody); maps to SF Pro automatically
│   │   ├── ButtonStyles.swift                  # PrimaryButtonStyle, SecondaryButtonStyle, DestructiveButtonStyle, GhostButtonStyle conforming to ButtonStyle
│   │   ├── TextFieldStyles.swift               # InlineEditableTextFieldStyle (no border until focused); SearchFieldStyle
│   │   ├── ListRowStyles.swift                 # Standardized 44pt and 52pt row view modifiers; hover highlight; focus ring
│   │   └── Animations.swift                    # Duration + curve constants (easeInOut 0.2s, spring response 0.35); Reduce Motion guard helper
│   │
│   ├── Components/
│   │   ├── Card.swift                          # GroupBox-based container with §3.1 card background; accepts any content via ViewBuilder
│   │   ├── Badge.swift                         # Capsule pill; accepts color + text; used for status labels
│   │   ├── LowStockPill.swift                  # Amber capsule pill with "Low" text; specialized for inventory low-stock indicator
│   │   ├── CategoryChip.swift                  # Rounded-rect category tag; color-coded by domain (Grocery=blue, Restaurant=amber, Expense=green)
│   │   ├── KeyValueRow.swift                   # HStack label-value row used in detail inspectors; label left-aligned .secondary, value right-aligned
│   │   ├── DropZone.swift                      # .onDrop wrapper accepting [.jpeg, .png, .heic, .pdf]; emits dropped file URLs; shows dashed border on hover; used in OCR Upload
│   │   ├── ReceiptThumbnail.swift              # AsyncImage with fallback placeholder; loads from authenticated URL via ImageCache; used in list rows and inspector
│   │   ├── EmptyStateView.swift                # SF Symbol + title + subtitle + optional CTA button; used for empty list states across all views
│   │   ├── SkeletonView.swift                  # Shimmer animated rounded-rect; parametric width/height; used during loading states
│   │   ├── ProgressBarView.swift               # Horizontal bar showing paid-vs-expected (Fixed Bills) or actual-vs-budget (Dining/Household Budget); color-coded green/amber/red by ratio
│   │   ├── Toast.swift                         # Non-modal overlay anchored to top of window; fades in/out; severity: info/success/warning/error; auto-dismisses after 4s
│   │   ├── SankeyWebView.swift                 # WKWebView host loading sankey-template.html; JS bridge injects analytics data; used for Spending by Category Sankey [v1.1]
│   │   ├── InlineEditableCell.swift            # Label that becomes NSTextField on double-click; fires onCommit/onCancel; used in Fixed Bills obligation rename and inline inventory edits
│   │   └── ContextMenuModifiers.swift          # Shared ViewModifier builders for common context menus: receipt row, inventory row, shopping list row, transaction row
│   │
│   ├── Views/
│   │   ├── Auth/
│   │   │   ├── LoginView.swift                 # Email + password form; Google OAuth button (triggers GoogleOAuthSheet); "Try Demo" link; server URL field (shown when no URL stored in UserDefaults)
│   │   │   ├── GoogleOAuthSheet.swift          # ASWebAuthenticationSession wrapper; presents OAuth URL; handles localocr://oauth/callback redirect
│   │   │   └── HouseholdSelectorView.swift     # Post-login screen shown if user belongs to multiple households [UNCONFIRMED: multi-household routing — verify against /auth/me response structure]
│   │   │
│   │   ├── Dashboard/
│   │   │   └── DashboardView.swift             # NavigationSplitView detail pane for Dashboard; spending tiles (Card), low-stock alert banner, attribution nudge; foreground refresh on appear
│   │   │
│   │   ├── Receipts/
│   │   │   ├── OCRUploadView.swift             # Main OCR upload panel: DropZone + NSOpenPanel trigger + Continuity Camera source picker + receipt type segmented control + AI model picker + submit button
│   │   │   ├── ReceiptReviewView.swift         # Post-OCR review form: store/date/total fields + line-item list with inline TextField cells + rotate image button + Confirm/Discard buttons
│   │   │   ├── ReceiptListView.swift           # Paginated receipt list with search, date-range filter, receipt-type filter tabs; ReceiptThumbnail per row
│   │   │   ├── ReceiptInspectorPanel.swift     # Trailing column inspector for selected receipt: full image, all fields, re-run OCR button, drag-out image support
│   │   │   └── RerunOCRView.swift              # Re-run OCR diff: model picker + submit + diff list (new items green, removed items red/strikethrough, unchanged neutral) + accept/discard per-item
│   │   │
│   │   ├── Inventory/
│   │   │   ├── InventoryView.swift             # Two-panel split: category sidebar (List) + product list (List); search (⌘F); ⌥↑/↓ quantity adjust; bulk select; low-stock filter chip
│   │   │   ├── KitchenView.swift               # LazyVGrid grouped by location/category; compact cards per item; tap to add to shopping list
│   │   │   └── ProductDetailSheet.swift        # Sheet: edit product name, category, quantity, location, threshold, expiry; price history chart (SwiftCharts line); delete product
│   │   │
│   │   ├── Shopping/
│   │   │   ├── ShoppingListView.swift          # List with checkbox rows (Space to toggle); tabs: List + Recommendations; ⌘N add inline; low-stock populate button; QR share button
│   │   │   └── ShareQRView.swift               # Displays server-served QR PNG in sheet; copy link button; NSSharingServicePicker for AirDrop/Messages [v1.1 for Share Sheet]
│   │   │
│   │   ├── Finance/
│   │   │   ├── FixedBillsView.swift            # Floor obligations list with InlineEditableCell rename; paid/unpaid toggle (Space); cadence badge; ProgressBarView; ⌘N add; Plaid link button
│   │   │   ├── CashTransactionsView.swift      # Quick-entry form (amount + description + category + DatePicker) + history list grouped by month; ⌘Return to submit
│   │   │   └── PlaidAccountsView.swift         # Accounts section (status badges; Sync Now button) + Staged Transactions list (confirm Return / dismiss Delete); ASWebAuthenticationSession for Link
│   │   │
│   │   ├── Analytics/
│   │   │   ├── SpendingByCategoryView.swift    # OutlineGroup expandable category rows with spend amounts; month navigation; Export CSV via NSSavePanel; Sankey via SankeyWebView [v1.1] [v1.1 full screen]
│   │   │   └── ExpenseAnalyticsView.swift      # SwiftCharts BarChart (weekly/monthly toggle) + merchant frequency list + category breakdown [v1.1]
│   │   │
│   │   ├── Restaurant/
│   │   │   ├── RestaurantWorkspaceView.swift   # Tabbed: Workspace + Repeat Orders + Split Bills + Contacts + Balances; Dining Budget card [v1.1]
│   │   │   ├── SplitBillsView.swift            # Contact multi-picker + amount-per-person fields + even-split toggle [v1.1]
│   │   │   ├── ContactsView.swift              # Dining contacts list with balance summary; add/edit/delete [v1.1]
│   │   │   └── BalancesView.swift              # Net debt list; settle individual or settle-all; confirmation sheet [v1.1]
│   │   │
│   │   ├── Chat/
│   │   │   └── AIChatView.swift                # Chat bubble list + input field + model picker; SSE streaming via URLSession AsyncBytes; admin-gated [v1.1]
│   │   │
│   │   ├── Medications/
│   │   │   └── MedicationsView.swift           # Medication list with quantity stepper and expiry DatePicker; barcode lookup via camera; refill alert badge [v1.1]
│   │   │
│   │   ├── Products/
│   │   │   └── ProductsCatalogView.swift       # Search + review queue; admin bulk edit; image backfill trigger [v1.1]
│   │   │
│   │   ├── Budget/
│   │   │   └── HouseholdBudgetView.swift       # Budget entry per domain/month; change log expandable section [v1.1]
│   │   │
│   │   ├── Contributions/
│   │   │   └── ContributionsView.swift         # Monthly leaderboard (sorted List); per-member drill-in sheet with event history
│   │   │
│   │   ├── Settings/
│   │   │   ├── SettingsView.swift              # Settings scene root; TabView with pane switcher (macOS 13 style: NSTabView equivalent)
│   │   │   ├── GeneralPane.swift               # Server URL field; auto-launch at login toggle (SMAppService); theme (system/light/dark); language (system default only)
│   │   │   ├── AccountPane.swift               # Profile (name, email, role badge); Google OAuth link/unlink; sign out; session info; invite member (admin only)
│   │   │   ├── AIModelsPane.swift              # Active model picker; per-model unlock/lock (admin); API usage stats; Fernet-encrypted keys are server-side — no key entry here
│   │   │   ├── TrustedDevicesPane.swift        # Trusted device list (scope badge, last seen); add device via QR pairing; revoke device
│   │   │   ├── TelegramPane.swift              # Telegram bot token field; webhook URL display; nudge schedule time picker; nudge min-threshold stepper
│   │   │   ├── NotificationsPane.swift         # Notification permission status; enable/disable shopping nudge; nudge time picker (mirrors TelegramPane timing)
│   │   │   ├── BackupPane.swift                # Backup list; create backup; download backup (NSSavePanel); restore (NSOpenPanel + confirmation sheet); admin only
│   │   │   └── AdvancedPane.swift              # Offline queue depth display; cache purge; Spotlight reindex; debug info (app version, build, server version)
│   │   │
│   │   ├── MenuBar/
│   │   │   └── MenuBarPopoverView.swift        # SwiftUI view hosted in NSPopover from MenuBarController; shows low-stock count, quick-add cash form, Open App / Upload Receipt buttons
│   │   │
│   │   └── DemoMode/
│   │       └── DemoModeOverlay.swift           # Persistent yellow banner overlay (§1.7 rule 10); suppresses write API calls when AppState.isDemoMode is true; "Sign In to Save" CTA
│   │
│   ├── Networking/
│   │   ├── APIClient.swift                     # URLSession wrapper; sets base URL from UserDefaults; configures HTTPCookieStorage; attaches User-Agent; JSON encode/decode; centralised error dispatch
│   │   ├── AuthInterceptor.swift               # Detects 401 responses; fires re-auth flow; retries original request once on success; notifies AppState
│   │   ├── Endpoints.swift                     # Typed enum of all API endpoints with path/method/body type; groups match §1.4 blueprint groups
│   │   ├── SSEClient.swift                     # URLSession AsyncBytes wrapper for text/event-stream; parses "data: <chunk>" lines; used by AIChatView for streaming responses
│   │   │
│   │   ├── Models/                             # Codable structs mirroring §1.3 database entities; snake_case JSON ↔ camelCase Swift via JSONDecoder.keyDecodingStrategy
│   │   │   ├── User.swift                      # id, name, email, role, isActive, googleSub, allowedPages, allowWrite, avatarEmoji, activeAiModelConfigId
│   │   │   ├── Household.swift                 # Derived from /auth/me response — householdId, householdName, memberCount; not a direct DB table
│   │   │   ├── Product.swift                   # id, name, rawName, displayName, brand, size, category, barcode, isRegularUse, reviewState, expectedShelfDays
│   │   │   ├── InventoryItem.swift             # id, productId, product (nested), quantity, location, threshold, manualLow, isActiveWindow, expiresAt, lastPurchasedAt
│   │   │   ├── Receipt.swift                   # id, storeId, storeName, totalAmount, date, domain, transactionType, userId, attributionUserId, imageUrl
│   │   │   ├── ReceiptItem.swift               # id, purchaseId, productId, productName, quantity, unitPrice, sizeLabel, spendingDomain, budgetCategory, kind
│   │   │   ├── ShoppingListItem.swift          # id, productId, productName, quantity, status, source, note, manualEstimatedPrice, actualPrice
│   │   │   ├── FixedBill.swift                 # Maps floor_obligations + bill_meta join; label, expectedMonthlyAmount, isActive, paymentStatus, billingCycle
│   │   │   ├── CashTransaction.swift           # id, purchaseId, amount, description, category, transactionDate, planningMonth, paymentMethod
│   │   │   ├── PlaidAccount.swift              # id, plaidItemId, accountName, accountMask, accountType, balanceCents, creditLimitCents, displayName, status (active/loginRequired/disconnected)
│   │   │   ├── PlaidTransaction.swift          # id, merchantName, amount, transactionDate, suggestedReceiptType, status, duplicatePurchaseId
│   │   │   ├── SpendingAnalytics.swift         # SpendingCategory (category, total, receipts), MerchantFrequency (name, count, avgAmount), MonthlyTimeline (month, total)
│   │   │   ├── ChatMessage.swift               # id, userId, role (user/assistant), content, toolTrace, flagged
│   │   │   ├── DiningContact.swift             # id, name, phone, email
│   │   │   ├── SharedExpense.swift             # id, purchaseId, totalAmount, myAmount, paymentScenario, notes
│   │   │   ├── Medication.swift                # id, name, brand, strength, dosageForm, quantity, unit, lowThreshold, expiryDate, memberId, status
│   │   │   ├── ContributionEvent.swift         # id, userId, eventType, subjectType, subjectId, status, points, description
│   │   │   ├── AIModelConfig.swift             # id, name, provider, modelString, priceTier, isEnabled, supportsVision, supportsPdf, inputCostPerMillion
│   │   │   └── HouseholdMember.swift           # id, name, ageGroup, avatarEmoji (household_members table — non-auth persons used for medication assignment)
│   │   │
│   │   ├── KeychainStore.swift                 # SecItemAdd/SecItemCopyMatching wrapper using KeychainAccess SPM; service "com.localocr.macos"; stores: sessionToken (if bearer), oauthRefreshToken; NEVER UserDefaults for credentials
│   │   ├── PreferencesStore.swift              # UserDefaults wrapper for non-sensitive prefs: apiBaseURL, activeAiModelConfigId, lastRefreshTimestamps, nudgeTime, nudgeMinThreshold
│   │   └── ImageCache.swift                    # NSCache<NSString, NSImage> keyed by authenticated URL; TTL 30 min; max 100 items; used by ReceiptThumbnail and product image displays
│   │
│   ├── Native/
│   │   ├── GlobalShortcutManager.swift         # NSEvent.addGlobalMonitorForEvents(matching: .keyDown); registers ⌃⌘R (keyCode 15 = R, modifiers .control + .command); requires Accessibility permission; posts notification to Router
│   │   ├── MenuBarController.swift             # NSStatusBar.system.statusItem(withLength: .variableLength); or SwiftUI .menuBarExtra; hosts MenuBarPopoverView in NSPopover; updates badge from AppState.lowStockCount
│   │   ├── NotificationManager.swift           # UNUserNotificationCenter wrapper; requestAuthorization; scheduleShoppingNudge (UNCalendarNotificationTrigger at user-set time); cancelAllNotifications; handle foreground delivery
│   │   ├── ContinuityCameraHelper.swift        # AVCaptureDeviceDiscoverySession with .continuityCamera; returns Bool isAvailable; captures still image via AVCapturePhotoOutput; delivers NSImage to OCRUploadView
│   │   ├── FileDropHandler.swift               # NSPasteboard itemProvider extraction for UTTypes [.jpeg, .png, .heic, .pdf]; extracts file URLs from drop destinations; validates MIME type
│   │   ├── SpotlightIndexer.swift              # CSSearchableIndex.default(); indexes InventoryItem and Receipt as CSSearchableItem; nightly full reindex via BackgroundFetchScheduler; handles CSSearchableIndexDelegate callbacks [v1.1]
│   │   ├── LoginItemController.swift           # SMAppService.mainApp.register() / .unregister(); maps to GeneralPane auto-launch toggle; macOS 13+ only (SMAppService replaces SMLoginItemSetEnabled)
│   │   ├── DockBadge.swift                     # NSApplication.shared.dockTile.badgeLabel = lowStockCount > 0 ? "\(lowStockCount)" : nil; called by AppState.lowStockCount observer
│   │   └── QuickLookExtension/                 # [v1.1] Separate App Extension target (com.localocr.macos.quicklook); QLPreviewingController for locally-cached receipt images
│   │       └── PreviewProvider.swift           # [v1.1] QLPreviewingController implementation; renders receipt image + metadata as Quick Look preview
│   │
│   ├── Background/
│   │   ├── BackgroundFetchScheduler.swift      # Fires on applicationDidBecomeActive: GET /inventory + /plaid/items + /shopping (60-second minimum interval guard via @AppStorage lastForegroundRefresh); updates AppState
│   │   └── NudgeScheduler.swift                # Reads nudgeTime and nudgeMinThreshold from PreferencesStore; calls NotificationManager.scheduleShoppingNudge; re-schedules on settings change
│   │
│   ├── State/
│   │   ├── AuthState.swift                     # @MainActor ObservableObject; currentUser: User?, isAuthenticated, isDemoMode, authSource; login/logout methods calling APIClient
│   │   ├── HouseholdState.swift                # @MainActor ObservableObject; householdMembers: [HouseholdMember], users: [User]; fetch on login
│   │   ├── ReceiptsState.swift                 # @MainActor ObservableObject; receipts: [Receipt], pendingUpload: URL?; loadReceipts(), uploadReceipt(url:type:modelId:)
│   │   ├── InventoryState.swift                # @MainActor ObservableObject; items: [InventoryItem], categories: [String]; loadInventory(), updateQuantity(id:delta:), lowStockItems computed var
│   │   ├── ShoppingState.swift                 # @MainActor ObservableObject; items: [ShoppingListItem], session: ShoppingSession?; addItem(), togglePurchased(id:), populateFromRecs()
│   │   ├── FinanceState.swift                  # @MainActor ObservableObject; bills: [FixedBill], cashTransactions: [CashTransaction], plaidAccounts: [PlaidAccount], stagedTransactions: [PlaidTransaction]
│   │   ├── ChatState.swift                     # @MainActor ObservableObject; messages: [ChatMessage], isStreaming: Bool; sendMessage(content:), streamResponse(); uses SSEClient [v1.1]
│   │   └── DemoModeGate.swift                  # ViewModifier; wraps write-action handlers to show "Demo mode" alert instead of firing API call when AuthState.isDemoMode == true
│   │
│   └── Resources/
│       ├── Assets.xcassets/                    # AppIcon (1024×1024 and all required sizes); AccentColor (matching §3.1 accent #3b82f6); named colors matching DesignTokens.swift
│       ├── Sounds/                             # Empty for v1.0; reserved for future audio feedback
│       └── HTML/
│           └── sankey-template.html            # Self-contained HTML/JS template for SankeyWebView; expects window.setSankeyData(json) call from Swift WKScriptMessageHandler [v1.1]
│
├── LocalOCRTests/                              # Unit test target (com.localocr.macosTests)
│   ├── APIClientTests.swift                    # URLSession mock tests; endpoint encoding/decoding; error dispatch
│   ├── ModelsTests.swift                       # JSON decode round-trips for all Codable models
│   ├── KeychainStoreTests.swift                # Keychain read/write/delete in a test Keychain service
│   ├── DemoModeGateTests.swift                 # Verify write methods are suppressed in demo mode
│   └── RouterTests.swift                       # URL scheme parsing: localocr:// → correct Router state
│
├── LocalOCRUITests/                            # XCUITest E2E target (com.localocr.macosUITests)
│   ├── LoginFlowTests.swift                    # Email login → Dashboard appears; invalid creds → error shown
│   ├── OCRUploadFlowTests.swift                # Drag file onto DropZone → review view appears; confirm → success toast
│   ├── InventoryFlowTests.swift                # Search → filter → quantity adjust → shopping list addition
│   └── SettingsFlowTests.swift                 # Change server URL → verify new URL stored; Notifications pane toggle
│
├── Packages/
│   └── LocalOCRModels/                         # [OPTIONAL — extract only if Xcode preview isolation requires it] Swift Package with shared Codable models; keeps LocalOCR/ and LocalOCRTests/ decoupled
│       └── Package.swift
│
├── scripts/
│   ├── build-release.sh                        # Wraps xcodebuild archive + exportArchive; outputs LocalOCR.dmg via create-dmg
│   ├── notarize.sh                             # Runs xcrun notarytool + xcrun stapler; reads APPLE_ID / TEAM_ID / APP_SPECIFIC_PASSWORD from environment
│   └── create-dmg.sh                           # Invokes create-dmg tool (npm package or Homebrew) to produce distributable DMG from Release .app
│
├── ExportOptions.plist                         # xcodebuild -exportArchive config: method=developer-id, signingCertificate=Developer ID Application, stripSwiftSymbols=true
└── README.md                                   # Setup: Xcode version, Swift version, how to set API_BASE_URL, how to run tests, how to build release
```

**Top-level folder purposes:**

- `LocalOCR/` — the only app target source. All 100+ Swift files the build agent writes live here. Xcode's file system is mirrored 1:1 by groups in the project navigator — do not create Xcode virtual groups that differ from the folder layout.
- `LocalOCRTests/` — unit tests. Run with `⌘U` or `xcodebuild test`. Must pass before any commit to main.
- `LocalOCRUITests/` — XCUITest integration tests. Run with the `LocalOCR UI Tests` scheme; require a booted macOS target.
- `Packages/` — local Swift Package for model extraction (only create the Package if the test target requires it for preview isolation; otherwise leave empty).
- `scripts/` — CI/CD automation. Do not call these from Xcode directly; they are for terminal / GitHub Actions use.
- `ExportOptions.plist` — required by `xcodebuild -exportArchive`; the build agent must fill in the correct Team ID before the release build works.

**File count (main app target):** approximately 95 Swift source files + 5 test files + 4 UITest files = 104 files total excluding generated and resource files.

---

### 4.3 DEPENDENCY LIST — LOCKED

The project adopts a minimal-dependency philosophy: Apple frameworks first, Swift Package Manager only when the first-party API is demonstrably more complex than a widely-audited community package with a stable interface. Every entry below is locked — the build agent must not add packages not on this list without a documented justification.

#### Swift Package Manager Dependencies

| Package | GitHub URL | Pinned Version | Purpose | Justification for not using Apple API directly |
|---|---|---|---|---|
| **KeychainAccess** | `kishikawakatsuki/KeychainAccess` | `4.2.2` | Keychain read/write/delete for auth tokens and OAuth refresh tokens | Raw `Security` framework requires `CFString` key casts, `SecItemAdd`/`SecItemCopyMatching` boilerplate, and manual `errSecItemNotFound` handling. KeychainAccess reduces this to `keychain["key"] = value` with clear errors. Widely used (12k+ GitHub stars), Swift-native, no transitive dependencies. The alternative `SwiftKeychainWrapper` is also acceptable but KeychainAccess has broader macOS adoption. |
| **Kingfisher** | `onevcat/Kingfisher` | `7.12.0` | Authenticated async image downloading and in-memory + disk cache for receipt thumbnails and product images | `AsyncImage` (SwiftUI built-in) does not support custom `URLRequest` headers, meaning it cannot inject the session cookie required for authenticated image endpoints. `URLSession` + `NSCache` is viable but requires re-implementing download queuing, cancellation, and disk cache eviction. Kingfisher handles all of this with a `.setImage(with:options:)` API and supports custom `ImageDownloader` with auth headers. Version 7.x is the last stable Xcode 15-compatible release before v8's breaking changes. |

**No other SPM dependencies are approved for v1.0.** Specific notes on packages considered and rejected:

- **SwiftSoup** — rejected. OAuth redirect handling via `ASWebAuthenticationSession` uses callback URL interception, not HTML parsing. No HTML scraping is needed.
- **Plaid Link iOS SDK** (`plaid/plaid-link-ios`) — rejected for direct SPM use. The Plaid Link SDK does not have a stable macOS (non-Catalyst) SPM package. The Plaid Link flow must be handled via `ASWebAuthenticationSession` opening the Plaid-hosted Link URL and intercepting the OAuth callback — this is the documented approach for server-side Plaid integrations where the app does not need the native Link SDK UI. The server (§1.4 `plaid_integration.py`) handles token exchange; the macOS app only needs to initiate the browser-based link flow and catch the redirect.
- **Alamofire** — rejected. `URLSession` with `async/await` is sufficient. Alamofire's value is primarily in its request/response pipeline chaining, which is replicated cleanly in `APIClient.swift` with structured concurrency.
- **Charts (third-party)** — rejected. `SwiftCharts` (Apple, macOS 13+) covers all chart types needed in v1.0 (bar, line, area). The Sankey chart is handled by `SankeyWebView` (WKWebView with embedded JS template), which is the correct pragmatic choice — no third-party charting library handles Sankey on macOS natively.
- **MASShortcut / HotKey** — rejected. `NSEvent.addGlobalMonitorForEvents` is the direct AppKit API. A wrapper library adds a dependency for a single 10-line function.
- **Sparkle** — deferred to v1.1. In-app auto-update is not an MVP requirement.

#### Apple Frameworks (No SPM required)

All the following are linked via Xcode target's Framework and Libraries phase — no Package.swift entry needed:

| Framework | Key APIs Used | Used In |
|---|---|---|
| **SwiftUI** | `NavigationSplitView`, `List`, `Form`, `ToolbarItem`, `Settings scene`, `WindowGroup`, `SwiftCharts.Chart`, `.menuBarExtra`, `ShareLink`, `@Environment`, `@ObservedObject`, `@StateObject`, `@AppStorage` | All view files |
| **AppKit** | `NSApplication`, `NSApplicationDelegate`, `NSWindow`, `NSOpenPanel`, `NSSavePanel`, `NSStatusBar`, `NSStatusItem`, `NSPopover`, `NSEvent`, `NSPasteboard`, `NSAlert`, `NSTableView` (indirectly via List), `NSVisualEffectView` (via UIViewRepresentable) | AppDelegate, MenuBarController, GlobalShortcutManager, FileDropHandler, Settings panes |
| **Foundation** | `URLSession`, `URLRequest`, `HTTPCookieStorage`, `HTTPCookie`, `JSONDecoder`/`JSONEncoder`, `UserDefaults`, `NotificationCenter`, `FileManager`, `Data`, `URL` | APIClient, PreferencesStore, all state files |
| **Combine** | `PassthroughSubject`, `CurrentValueSubject`, `sink`, `store(in:)` | AppState refresh pipeline, SSEClient parsing |
| **UserNotifications** | `UNUserNotificationCenter`, `UNNotificationRequest`, `UNCalendarNotificationTrigger`, `UNNotificationAction`, `UNNotificationCategory` | NotificationManager, NudgeScheduler |
| **AVFoundation** | `AVCaptureDevice`, `AVCaptureDeviceDiscoverySession`, `AVCaptureSession`, `AVCapturePhotoOutput`, `AVCaptureDeviceType.continuityCamera` | ContinuityCameraHelper |
| **CoreImage** | `CIQRCodeGenerator` filter for QR code display in ShareQRView (fallback when server endpoint is unreachable) | ShareQRView |
| **CoreSpotlight** | `CSSearchableIndex`, `CSSearchableItem`, `CSSearchableItemAttributeSet` | SpotlightIndexer [v1.1] |
| **PDFKit** | `PDFView`, `PDFDocument` — for rendering PDF receipts in ReceiptInspectorPanel | ReceiptInspectorPanel |
| **QuickLook** | `QLPreviewPanel`, `QLPreviewingController` | QuickLookExtension target [v1.1] |
| **WebKit** | `WKWebView`, `WKWebViewConfiguration`, `WKScriptMessageHandler`, `WKNavigationDelegate` | SankeyWebView, GoogleOAuthSheet |
| **Security** | `SecItemAdd`, `SecItemCopyMatching` (via KeychainAccess) | KeychainStore |
| **LocalAuthentication** | `LAContext.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics)` | Plaid/Balances views [v1.1] |
| **UniformTypeIdentifiers** | `UTType.jpeg`, `.png`, `.heic`, `.pdf` — file type declarations for NSOpenPanel and onDrop | OCRUploadView, DropZone, FileDropHandler |
| **ServiceManagement** | `SMAppService.mainApp.register()` / `.unregister()` | LoginItemController |
| **Charts** | `Chart`, `BarMark`, `LineMark`, `AreaMark`, `RuleMark` | SpendingByCategoryView, ExpenseAnalyticsView [v1.1] |

---

### 4.4 ENVIRONMENT CONFIGURATION

On macOS, secrets belong in the Keychain. `.env` files as runtime configuration do not apply to a native macOS app. The table below defines every configurable value, where it lives, how the build agent initialises it, and how the user sets it.

| Variable / Setting | Purpose | Storage location | Default value | How to set / obtain |
|---|---|---|---|---|
| **API Base URL** | Origin of the Flask server (scheme + host + port) | `UserDefaults` key `"LocalOCR.apiBaseURL"` | `http://localhost:8090` | User types in Settings → General → Server URL field. Validated on save (reachability check via `GET /auth/config`). Written to `UserDefaults` immediately; `APIClient` reads it on every request. |
| **Session cookie** | Flask session authentication | `HTTPCookieStorage.shared` (system cookie jar; persists across app launches automatically) | None (absent until login) | Server sets `Set-Cookie: session=<value>` after successful login. `URLSession` with `.default` configuration automatically stores and re-sends the cookie. No manual management required. |
| **OAuth refresh token** | Google OAuth refresh token (if Google OAuth login used) | Keychain via KeychainAccess; service `"com.localocr.macos"`, key `"oauth.refreshToken"` | None | Set by `AuthState.handleGoogleOAuthCallback()` after the server returns the OAuth session. Used to re-authenticate silently on session expiry. |
| **Active AI model config ID** | Remembers user's last-selected AI model for OCR and Chat | `UserDefaults` key `"LocalOCR.activeAiModelConfigId"` | `nil` (server default used) | User selects in OCR Upload picker or Settings → AI Models pane. Not a secret — UserDefaults is appropriate. |
| **Nudge time (HH:mm)** | Local notification delivery time for shopping nudge | `UserDefaults` key `"LocalOCR.nudgeTime"` | `"09:30"` | User sets in Settings → Notifications pane time picker. `NudgeScheduler` re-schedules on change. |
| **Nudge minimum threshold** | Minimum low-stock count before nudge fires | `UserDefaults` key `"LocalOCR.nudgeMinThreshold"` | `3` | User sets in Settings → Notifications pane stepper. |
| **Last foreground refresh timestamps** | Prevent hammering the server on rapid app switches | `UserDefaults` keys `"LocalOCR.lastInventoryRefresh"`, `"LocalOCR.lastShoppingRefresh"`, `"LocalOCR.lastPlaidRefresh"` (Date values) | `nil` (refresh fires on first activation) | Written by `BackgroundFetchScheduler` after each refresh. |
| **Demo mode flag** | Client-side guest mode gate | `AppState.isDemoMode: Bool` — in-memory only, not persisted | `false` | Set to `true` when user taps "Try Demo" on LoginView. Cleared on sign-in. Never persisted to disk (per §1.7 rule 10: demo mode is session-local only). |
| **Window frame autosave names** | Persist window size and position | `NSWindow.setFrameAutosaveName(_:)` in each WindowGroup | macOS system default | Automatic via `NSWindow`; no manual configuration needed. Each window type uses a distinct autosave name: `"MainWindow"`, `"ReceiptInspector"`, `"OCRUpload"`. |
| **Notification permission** | System-managed UNUserNotificationCenter authorization | System (not app-controlled) | Undetermined until first prompt | Requested once on first Settings → Notifications pane visit via `UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])`. Status displayed in pane. |
| **Accessibility permission** | Required for global keyboard shortcut (NSEvent global monitor) | System (Privacy & Security → Accessibility) | Not granted until user enables | Requested on first use of global shortcut. `GlobalShortcutManager` checks `AXIsProcessTrusted()` before registering; if false, opens `x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility` deep link and shows a one-time in-app alert. |
| **Login item (auto-launch)** | Launch app at login | `SMAppService` — managed by macOS | Off | User toggles in Settings → General → "Launch at Login". |

**`.env.example` — project root** (for documentation only; not read at runtime):

```
# LocalOCR macOS app — local development reference
# These values are NOT loaded from this file at runtime.
# Set API_BASE_URL in the app's Settings → General → Server URL field.
# All secrets are stored in macOS Keychain.

API_BASE_URL=http://localhost:8090
```

**What the build agent must NOT do:**

- Do not read environment variables at app launch via `ProcessInfo.processInfo.environment`. There is no `.env` loader, no launch argument parser for secrets, and no `Dotenv` package.
- Do not store any authentication token, cookie value, or Plaid access token in `UserDefaults`. `UserDefaults` is stored in plaintext on disk and is not encrypted.
- Do not hardcode the API base URL in `APIClient.swift`. The default `http://localhost:8090` must be a fallback in `PreferencesStore`, not a compile-time constant, so that users who self-host on a non-standard port or remote URL do not need to rebuild the app.

---

### 4.5 API INTEGRATION STRATEGY

The macOS app is a pure REST client to the existing Flask backend (§1.4 — 216 routes across 24 blueprint groups). No new backend routes are required for v1.0. This section specifies how `APIClient.swift` is structured, how authentication flows through the request pipeline, and how every error class is handled.

#### Base Configuration

**Base URL**: Read from `PreferencesStore.apiBaseURL` (UserDefaults key `"LocalOCR.apiBaseURL"`, default `http://localhost:8090`) on every request construction. The build agent must not cache the base URL in `APIClient` — the user may change it in Settings while the app is running, and the next request must pick up the new value.

**URLSession configuration**: Use `URLSessionConfiguration.default` (not `.ephemeral`). The `.default` configuration persists `HTTPCookieStorage.shared` across app launches, which is required for the Flask session cookie to survive the app being closed and reopened. Explicitly set:
```swift
configuration.httpCookieAcceptPolicy = .always
configuration.httpShouldSetCookies = true
configuration.httpCookieStorage = HTTPCookieStorage.shared
```

**User-Agent header**: Every request must include:
```
User-Agent: LocalOCR-macOS/1.0.0 (macOS 14.0; arm64)
```
The version string is read from `Bundle.main.infoDictionary["CFBundleShortVersionString"]` and the macOS version from `ProcessInfo.processInfo.operatingSystemVersionString`. This allows server-side identification of macOS client requests in logs.

**JSON encoding/decoding**:
- Decoder: `JSONDecoder()` with `keyDecodingStrategy = .convertFromSnakeCase`. All Flask responses use `snake_case` (e.g. `purchase_id`, `total_amount`); Swift models use `camelCase` (e.g. `purchaseId`, `totalAmount`). The strategy handles this automatically for 95% of cases. Exceptions requiring custom `CodingKeys` (e.g. fields like `is_active_window` → `isActiveWindow`) must be handled with explicit `CodingKeys` enum, not `AnyCodable`.
- Encoder: `JSONEncoder()` with `keyEncodingStrategy = .convertToSnakeCase`. Outgoing POST/PATCH bodies use camelCase in Swift and are automatically snake_cased for the server.
- Date strategy: `decoder.dateDecodingStrategy = .iso8601` — all dates from the server are ISO 8601 strings.

**CSRF**: [UNCONFIRMED — must verify against `manage_authentication.py`]. The Flask app uses `SameSite=Lax` cookies and does not appear to require a CSRF token header for cookie-authenticated requests from native clients. If the build agent discovers a CSRF token requirement (e.g. `X-CSRF-Token` header checked in `require_auth`), the client must fetch the token from a dedicated endpoint (likely `GET /auth/config` which returns `csrf_token` in its response body) and attach it to all mutating requests (POST, PUT, PATCH, DELETE). The `AuthInterceptor` should handle token refresh on `403 Forbidden` with body `{"error": "CSRF token invalid"}`.

#### Request Interceptors (`APIClient` responsibilities)

1. **Base URL injection** — prepend `PreferencesStore.apiBaseURL` to every relative path.
2. **Cookie attachment** — automatic via `URLSession` + `HTTPCookieStorage.shared`; no manual `Cookie:` header construction.
3. **User-Agent** — set on every request.
4. **Content-Type** — JSON requests: `application/json`. Multipart uploads (OCR): `multipart/form-data` with generated boundary. Do not set `Content-Type` on GET requests.
5. **Demo mode gate** — if `AppState.isDemoMode == true`, block all mutating requests (POST/PUT/PATCH/DELETE) at the `APIClient` level before they reach the network. Return a `DemoModeError` immediately. `AuthInterceptor` is bypassed for demo-blocked requests.
6. **Request logging** — in DEBUG builds, log `[API] <METHOD> <path>` with status code. Never log request bodies containing auth tokens or passwords.

#### Authentication Flow Integration

The Flask backend authenticates via session cookie (§1.6, priority 3 — browser session cookie). The macOS app's `URLSession` with `HTTPCookieStorage.shared` handles this automatically. The sequence:

1. App cold launch → `AuthState.checkSession()` fires `GET /auth/me`.
2. If 200: populate `currentUser`, proceed to main UI.
3. If 401: present `LoginView` modally.
4. Login: POST `/auth/login` with `{email, password}` → server sets `Set-Cookie: session=<value>; HttpOnly; SameSite=Lax`. `HTTPCookieStorage.shared` stores it automatically.
5. On subsequent requests: `URLSession` reads from `HTTPCookieStorage.shared` and sends `Cookie: session=<value>` automatically.
6. Session expiry (14 days per §1.6): caught by `AuthInterceptor` on next 401. `AuthInterceptor` removes the stale cookie from `HTTPCookieStorage.shared`, fires `NotificationCenter.default.post(name: .authSessionExpired)`, which `AuthState` observes and uses to present `LoginView` modally without crashing any in-flight views.

**Bearer token fallback** [UNCONFIRMED — the web app stores an `api_token` in `localStorage`; verify if the macOS app should use this path]. The macOS app does NOT use the Bearer token path in v1.0. Cookie auth is sufficient. The Bearer path is available for trusted device pairing (§1.6 step 6), where the device token is stored in Keychain and sent as `X-Trusted-Device-Token` header on every request by a paired display device (e.g. kitchen display). The main user-facing app uses the cookie path.

#### Endpoint Typing (`Endpoints.swift`)

All API paths are defined as a typed enum to prevent raw-string URL construction across the codebase:

```swift
enum Endpoint {
    // Auth
    case me
    case login
    case logout
    case config
    case oauthGoogleStart
    case oauthGoogleCallback

    // Receipts
    case receipts
    case receipt(id: Int64)
    case uploadReceipt
    case rerunOCR(id: Int64)

    // Inventory
    case inventory
    case inventoryItem(id: Int64)
    case updateQuantity(id: Int64)

    // Shopping
    case shoppingList
    case shoppingListItem(id: Int64)
    case populateFromRecs
    case shoppingShareQR

    // Finance
    case floorObligations
    case floorObligation(id: Int64)
    case cashTransactions
    case cashTransaction(id: Int64)
    case plaidItems
    case plaidStagedTransactions
    case confirmStagedTransaction(id: Int64)
    case dismissStagedTransaction(id: Int64)

    // Analytics
    case spendingByCategory
    case sankeyData

    // Contributions
    case contributions

    // Settings / System
    case aiModels
    case activeAiModel
    case backupList
    case createBackup
    case restoreBackup

    // ... all remaining groups per §1.4

    var path: String { /* returns typed path string */ }
    var method: String { /* returns "GET", "POST", etc. */ }
}
```

The build agent must populate `path` and `method` for every case by cross-referencing §1.4. Do not create an `Endpoint` case for any route not used by the macOS app (e.g. Telegram webhook routes, `/features` doc page).

#### Offline Strategy

Per §2.6 AC-09, the app must handle server unreachability gracefully.

**Read-only views** use stale-while-revalidate from a local cache:
- Cache location: `~/Library/Caches/com.localocr.macos/<endpoint-hash>.json`
- ETag-aware: store the `ETag` response header alongside the JSON. On next request, send `If-None-Match: <etag>` — on `304 Not Modified`, serve from cache. On `200 OK`, overwrite cache.
- Cache invalidated: on mutating operation success (POST/PATCH/DELETE to the same domain).
- Maximum stale age: 24 hours. After 24 hours, show an "Offline — showing data from [date]" banner in the view, not a hard error.

**Write operations** when offline queue to a SQLite database:
- Queue location: `~/Library/Application Support/com.localocr.macos/pendingWrites.sqlite`
- Schema: `id INTEGER PRIMARY KEY, endpoint TEXT, method TEXT, body BLOB, created_at DATETIME`
- Drain: `BackgroundFetchScheduler.drainPendingWrites()` fires on `applicationDidBecomeActive` after confirming server reachability. Processes queue in order; on success deletes the row; on failure (non-network error, e.g. 409 Conflict) marks as `failed` and shows a toast.
- Queue depth: shown in Settings → Advanced pane as "N pending writes".
- Maximum queue size: 100 entries. If exceeded, the oldest entries are dropped and a toast is shown: "Some offline actions were discarded — queue was full."

**Network reachability detection**: Use `Network.framework`'s `NWPathMonitor` to detect interface changes. On `.unsatisfied` path, set `AppState.isOffline = true`. On `.satisfied`, set `AppState.isOffline = false` and trigger `BackgroundFetchScheduler`. The top-of-window "Offline" banner in §3.x is keyed to `AppState.isOffline`.

#### Error Handling — Complete Matrix

Every HTTP error class has a defined handling path. The build agent must implement all of these in `APIClient` and `AuthInterceptor`:

| HTTP Status | Cause | Client Action | User-visible outcome |
|---|---|---|---|
| `200 OK` / `201 Created` | Success | Parse body; update state | View updates; success toast for destructive confirmations only |
| `204 No Content` | Delete/settle success | No body to parse; update state | View removes row; brief success toast |
| `304 Not Modified` | ETag cache hit | Serve from cache | View renders immediately with cached data |
| `400 Bad Request` | Malformed request (client bug) | Log error with request details (DEBUG only) | Toast: "Something went wrong — please try again." |
| `401 Unauthorized` | Session expired or missing | `AuthInterceptor`: clear cookie, post `.authSessionExpired` notification, retry after re-login | `LoginView` presented modally; original action retried once on success |
| `403 Forbidden` | Insufficient role or demo-mode enforced server-side | Show NSAlert: "You don't have permission for this action. [server `error.message`]" | NSAlert with "OK". Do not retry. |
| `404 Not Found` | Item deleted by another session | Update state: remove item from list | Empty state or "Item not found" inline message in the view |
| `409 Conflict` | Duplicate action (e.g. already confirmed transaction) | Mark pending write as `conflict` in offline queue | Toast: "This action was already applied." |
| `422 Unprocessable Entity` | Validation failure | Parse `errors` field from response body (Flask-Marshmallow / Flask standard format) | Inline field error messages in the form view that made the request |
| `429 Too Many Requests` | Rate limiting (unlikely on self-hosted instance) | Retry after `Retry-After` header seconds (max 30s); if no header, retry after 10s | Toast: "Server is busy — retrying..." |
| `500 Internal Server Error` | Backend crash | Log error; do not retry automatically | Toast: "Server error — retry in a moment." with a Retry button that fires the original request once |
| `502 Bad Gateway` / `503 Service Unavailable` | nginx / Docker restart in progress | Set `AppState.isOffline = true` temporarily; retry after 5s (once); if still failing, treat as offline | "Offline" banner; queue writes |
| Network timeout (`URLError.timedOut`) | Server unreachable (slow LAN) | Set timeout to 30 seconds for all requests; on timeout, treat as offline | "Offline" banner |
| `URLError.notConnectedToInternet` | No network | Set `AppState.isOffline = true` | "Offline" banner |
| `URLError.serverCertificateUntrusted` | HTTPS with self-signed cert (user may run nginx with self-signed cert) | Show a one-time NSAlert: "The server certificate is not trusted. If you are connecting to your own server, you can allow this connection." with Allow/Cancel. On Allow: add a per-host exception in a `URLSessionDelegate.urlSession(_:didReceive:completionHandler:)`. | NSAlert; if allowed, future requests to the same host bypass cert validation. Log a warning in Console. |

**Note on self-signed TLS**: The target user (self-hosted Docker operator on LAN) may use nginx with a self-signed certificate. The app must not hard-fail on self-signed certificates but must require explicit user consent before bypassing validation. Store the per-host bypass flag in `UserDefaults` key `"LocalOCR.trustedHosts"` as a `[String]` array of hostnames. Never bypass for public IP addresses outside the RFC-1918 ranges (10.x.x.x, 192.168.x.x, 172.16–31.x.x). [UNCONFIRMED: verify if the self-hosted nginx in the production deployment (§1.1, §1.4) uses TLS].

---

### 4.6 NATIVE macOS INTEGRATION PLAN

Each native capability from §2.3 and §3.x is fully specified: the exact API, the Swift file, the triggering condition, the required permission or entitlement, and the graceful fallback when unavailable.

---

**Integration 1: File Open / Save Panels (NSOpenPanel / NSSavePanel)**

| Attribute | Detail |
|---|---|
| API | `NSOpenPanel` (file selection), `NSSavePanel` (export) |
| Swift files | `OCRUploadView.swift` (open), `CashTransactionsView.swift` (export), `SpendingByCategoryView.swift` (export) |
| Trigger — Open | "Browse Files" button in OCRUploadView; ⌘O keyboard shortcut bound to OCR Upload scene |
| Trigger — Save | "Export CSV" button / ⌘S in Spending by Category and Cash Transactions |
| NSOpenPanel config | `allowedContentTypes: [UTType.jpeg, UTType.png, UTType.heic, UTType.pdf]`; `allowsMultipleSelection: true`; `canChooseDirectories: false` |
| NSSavePanel config | `allowedContentTypes: [.commaSeparatedText]`; `nameFieldStringValue: "spending-\(YYYY-MM).csv"` |
| Entitlement | `com.apple.security.files.user-selected.read-write` (if sandboxed — this build is NOT sandboxed per §2.1, so no sandbox entitlement is required; the file system is open). |
| Fallback | N/A — these are Apple APIs; they always work on macOS. |

---

**Integration 2: Notification Center (UNUserNotificationCenter)**

| Attribute | Detail |
|---|---|
| API | `UNUserNotificationCenter.current()`, `UNCalendarNotificationTrigger`, `UNNotificationAction`, `UNNotificationCategory` |
| Swift files | `Native/NotificationManager.swift` (scheduling + delegate), `Background/NudgeScheduler.swift` (settings-driven re-scheduling) |
| Permission request | Called once after first successful login, before first settings visit. `requestAuthorization(options: [.alert, .sound, .badge])`. Status reflected in Settings → Notifications pane. |
| Trigger — Shopping nudge | `UNCalendarNotificationTrigger` with `DateComponents` from `PreferencesStore.nudgeTime` (default 09:30). Only scheduled when `InventoryState.lowStockItems.count >= PreferencesStore.nudgeMinThreshold`. Re-scheduled on settings change or foreground refresh. |
| Trigger — Plaid login required | Fired by `BackgroundFetchScheduler` when a PlaidAccount has `status == .loginRequired`. Uses `UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)` (immediate delivery). Not re-fired on same account until the account status changes back to `.active`. |
| Notification actions | Category `"SHOPPING_NUDGE"` registers two actions: `"VIEW_LIST"` (opens Shopping List via `localocr://shopping`) and `"DISMISS"` (userNotificationCenter(_:didReceive:withCompletionHandler:) marks nudge as dismissed for 24h via `UserDefaults`). |
| UNUserNotificationCenterDelegate | Implemented in `AppDelegate`; `willPresent` returns `.banner` + `.sound` for foreground delivery; `didReceive` routes action identifiers to `Router.handleURL`. |
| Fallback | If permission denied: nudge not scheduled; Settings → Notifications pane shows a yellow banner "Notifications not enabled — open System Settings" with a button opening `x-apple.systempreferences:com.apple.preference.notifications`. |

---

**Integration 3: Global Keyboard Shortcut (⌃⌘R — New Receipt Upload)**

| Attribute | Detail |
|---|---|
| API | `NSEvent.addGlobalMonitorForEvents(matching: .keyDown, handler:)` |
| Swift file | `Native/GlobalShortcutManager.swift` |
| Shortcut | ⌃⌘R — `keyCode: 15`, `modifierFlags: [.control, .command]`. Conflicts checked: no system shortcut uses ⌃⌘R on macOS 13+. |
| Registration | Called from `AppDelegate.applicationDidFinishLaunching` after accessibility permission is confirmed. |
| Permission | Accessibility access (`AXIsProcessTrusted()`). If not granted: show a one-time `NSAlert` with message "LocalOCR needs Accessibility access to register a global shortcut." + "Open System Settings" button (opens `x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility`). Set `UserDefaults` key `"LocalOCR.accessibilityPromptShown" = true` to suppress repeated prompts. |
| On fire | Posts `Notification(name: .globalShortcutReceiptUpload)` to `NotificationCenter.default`. `Router` observes and calls `openWindow(id: "ocr-upload")` — brings main window forward if minimised, or opens OCRUploadView as a sheet if main window is already frontmost. |
| Entitlement | None. Global monitors do not require a special entitlement with Hardened Runtime; they only require the user to grant Accessibility permission. |
| Fallback | In-app ⌘U shortcut (within the main window) still works regardless of global shortcut status. Settings → General shows "Global shortcut ⌃⌘R — Enabled / Disabled" status with a "Grant Access" link. |

---

**Integration 4: Menu Bar Status Item**

| Attribute | Detail |
|---|---|
| API | SwiftUI `.menuBarExtra("LocalOCR", image: "MenuBarIcon")` scene modifier (macOS 13+). This is preferred over `NSStatusBar.system.statusItem` because it integrates with SwiftUI scene lifecycle. If `.menuBarExtra` proves insufficient (e.g. custom NSPopover sizing needed), fall back to `NSStatusBar` in `MenuBarController.swift`. |
| Swift file | `LocalOCRApp.swift` (scene declaration), `Views/MenuBar/MenuBarPopoverView.swift` (content), `Native/MenuBarController.swift` (NSStatusBar fallback) |
| Badge (low-stock count) | `.menuBarExtra` does not natively support a numeric badge. Use a custom image rendered with `NSImage` + `NSAttributedString` badge overlay drawn via `draw(in:)` — updated by `AppState.lowStockCount` observer. Badge is hidden when count is 0. |
| Popover content | `MenuBarPopoverView` shows: current low-stock count tile, quick-add cash transaction form (amount + description + category), divider, "Open LocalOCR" button, "Upload Receipt" button, divider, "Quit" button. |
| Permission | None |
| Toggle | Settings → General → "Show in Menu Bar" toggle. When off: `menuBarExtra` is excluded from the `App` body. The main window `windowShouldClose` behavior changes to terminate rather than hide when the menu bar item is disabled. |
| Fallback | If `.menuBarExtra` API is unavailable (should not happen on macOS 13+), fall back to `NSStatusBar.system.statusItem` in `MenuBarController.swift` with a classic `NSPopover`. |

---

**Integration 5: Keychain (Credential Storage)**

| Attribute | Detail |
|---|---|
| API | `Security` framework via `KeychainAccess` SPM package (§4.3) |
| Swift file | `Networking/KeychainStore.swift` |
| Service identifier | `"com.localocr.macos"` |
| Items stored | `"oauth.refreshToken"` — Google OAuth refresh token (String); `"trustedDevice.token"` — paired device token for kitchen display mode (String, only when app is used as a trusted device) |
| Items NOT stored | Session cookies (live in `HTTPCookieStorage.shared`), API base URL (not sensitive — `UserDefaults`), any server-side secrets (Fernet key, Plaid tokens — these never leave the server) |
| Access control | `kSecAttrAccessibleAfterFirstUnlock` — allows Keychain access after the Mac is unlocked for the first time after boot; this lets background tasks (foreground refresh on wake) read Keychain without requiring the user to first unlock the Mac manually. |
| Entitlement | `com.apple.security.keychain-access-groups` is NOT required for Developer ID builds that only access their own app's items. `KeychainAccess` with `service:` parameter isolates items automatically. |
| Fallback | N/A — Keychain always works on macOS. If `KeychainStore.read` fails (e.g. item not found), return `nil` and treat as unauthenticated. |

---

**Integration 6: Auto-Launch at Login**

| Attribute | Detail |
|---|---|
| API | `ServiceManagement.SMAppService.mainApp` |
| Swift file | `Native/LoginItemController.swift` |
| Registration | `SMAppService.mainApp.register()` — called when user enables "Launch at Login" in Settings → General |
| Unregistration | `SMAppService.mainApp.unregister()` — called when user disables |
| Status check | `SMAppService.mainApp.status` — check on Settings → General pane open to reflect current state |
| macOS requirement | macOS 13+ only — `SMAppService` is the replacement for deprecated `SMLoginItemSetEnabled`. This project targets macOS 13+, so no version guard is needed. |
| Entitlement | None for `SMAppService` with Developer ID builds |
| Fallback | If registration fails (e.g. MDM policy blocks login items), catch the error and show: "Could not register login item. Check System Settings → Login Items for LocalOCR." |

---

**Integration 7: Dock Badge (Low-Stock Count)**

| Attribute | Detail |
|---|---|
| API | `NSApplication.shared.dockTile.badgeLabel` |
| Swift file | `Native/DockBadge.swift` |
| Trigger | `AppState.lowStockCount` `didSet` observer; also called on foreground refresh completion |
| Badge logic | `badgeLabel = lowStockCount > 0 ? "\(lowStockCount)" : nil`. Setting to `nil` removes the badge. |
| Permission | None |
| Fallback | N/A |

---

**Integration 8: Drag-and-Drop from Finder (OCR Upload)**

| Attribute | Detail |
|---|---|
| API | `NSApplicationDelegate.application(_:open:)` for Dock drops; SwiftUI `.onDrop(of:isTargeted:perform:)` for in-window drops; `NSPasteboard` via `FileDropHandler` for drag validation |
| Swift files | `App/AppDelegate.swift` (Dock drop), `Components/DropZone.swift` (in-window drop), `Native/FileDropHandler.swift` (UTType validation and NSItemProvider extraction) |
| Accepted types | `UTType.jpeg` (`public.jpeg`), `UTType.png` (`public.png`), `UTType.heic` (`public.heic`), `UTType.pdf` (`com.adobe.pdf`) |
| Dock drop | `AppDelegate.application(_:open:)` receives `[URL]`; passes first URL to `AppState.pendingUploadURLs`; `Router` observes and opens OCRUploadView with files pre-filled. |
| In-window drop | `DropZone.onDrop` extracts file URLs from `NSItemProvider`; calls the same path as Dock drop for consistency. Drop zone highlights with dashed border animation (§3.6 DropZone) on `.onHover`. |
| Multiple files | If multiple files dropped: queued in `AppState.pendingUploadURLs: [URL]`; OCR Upload view processes one at a time, advancing to next on "Confirm" or "Skip". |
| Validation | `FileDropHandler.validate(_:)` checks UTType conformance. Invalid types (e.g. `.docx`) show a brief toast: "Unsupported file type — please drop a JPEG, PNG, HEIC, or PDF." |
| Permission | None (Developer ID non-sandboxed) |
| Entitlement | `com.apple.security.files.user-selected.read-write` — added to entitlements even though the Developer ID build is non-sandboxed, for future sandbox compatibility and to formally declare the access intent to Gatekeeper. |

---

**Integration 9: URL Scheme / Deep Links**

| Attribute | Detail |
|---|---|
| URL scheme | `localocr://` |
| Registration | `Info.plist` key `CFBundleURLTypes`: array with one entry `{CFBundleURLName: "com.localocr.macos.url", CFBundleURLSchemes: ["localocr"]}` |
| Handler | `LocalOCRApp.swift` `.onOpenURL { url in router.handleURL(url) }` |
| Routes | |
| `localocr://receipt/<id>` | Opens Receipt Inspector panel for the given receipt ID; fetches receipt data from API if not in cache |
| `localocr://upload` | Opens OCR Upload view (brings main window forward if needed) |
| `localocr://shopping` | Opens Shopping List view |
| `localocr://oauth/callback?code=<code>&state=<state>` | Completes Google OAuth flow; `GoogleOAuthSheet` registers as the handler for this host |
| `localocr://inventory/<product_id>` | Opens Inventory view scrolled to the given product [v1.1] |
| Swift file | `App/Router.swift` `handleURL(_:)` — parses `URL.host`, `URL.pathComponents`, and `URL.queryParameters`; dispatches to appropriate scene/view |
| Fallback | Unknown URL scheme paths: show a toast "Unknown link — could not navigate to that screen." |

---

**Integration 10: Continuity Camera (Receipt Scan from iPhone)**

| Attribute | Detail |
|---|---|
| API | `AVCaptureDevice.DiscoverySession(deviceTypes: [.continuityCamera], mediaType: .video, position: .unspecified)` |
| Swift file | `Native/ContinuityCameraHelper.swift` |
| Availability check | `isAvailable: Bool { !discoverySession.devices.isEmpty }` — evaluated on `OCRUploadView` appear. |
| User flow | 1. OCRUploadView appears → `ContinuityCameraHelper.isAvailable` checked. 2. If true: "iPhone Camera" option shown in source picker alongside "Browse Files". 3. User taps "iPhone Camera" → `AVCaptureSession` configured with Continuity Camera device → `AVCapturePhotoOutput.capturePhoto` initiated → iPhone camera UI activates automatically on iPhone screen. 4. User photographs receipt → `AVCapturePhotoCaptureDelegate.photoOutput(_:didFinishProcessingPhoto:)` called with `CMSampleBuffer` → converted to `Data` → passed to OCR upload pipeline as file data (JPEG format). |
| No manual pairing | Continuity Camera handshake is handled automatically by macOS 13 + iOS 16 Handoff. The app does not manage pairing. |
| Info.plist | `NSCameraUsageDescription` key required: `"LocalOCR uses your camera to capture receipt images for OCR processing."` |
| Entitlement | None beyond `NSCameraUsageDescription` for Developer ID builds. |
| Fallback | If `isAvailable == false` (no iPhone nearby, or wrong iOS version): "iPhone Camera" option is hidden entirely from the source picker. User uses file picker or Finder drag. No error shown. |

---

**Integration 11: Spotlight Indexing (Inventory + Receipts)** `[v1.1]`

| Attribute | Detail |
|---|---|
| API | `CoreSpotlight.CSSearchableIndex.default()`, `CSSearchableItem`, `CSSearchableItemAttributeSet` |
| Swift file | `Native/SpotlightIndexer.swift` |
| Indexed content | Inventory items: `domainIdentifier = "com.localocr.inventory"`, `uniqueIdentifier = "inventory.\(item.id)"`, `attributeSet.title = item.product.displayName`, `attributeSet.contentDescription = "\(item.quantity) in \(item.location)"`. Receipts: `domainIdentifier = "com.localocr.receipt"`, `uniqueIdentifier = "receipt.\(receipt.id)"`, `attributeSet.title = receipt.storeName`, `attributeSet.contentDescription = "$\(receipt.totalAmount) on \(receipt.date)"`. |
| Index update triggers | On `InventoryState` or `ReceiptsState` change (delta index); nightly full reindex triggered by `BackgroundFetchScheduler` at 02:00 local time via `UNCalendarNotificationTrigger` (silent notification wakes the app). |
| Spotlight tap | `CSSearchableIndexDelegate.searchableIndex(_:reindexSearchableItemsWithIdentifiers:acknowledgementHandler:)` is implemented. Opening a Spotlight result fires `NSUserActivity` with the `userInfo` dict containing the identifier → `Router.handleUserActivity(_:)` → deep link to receipt or inventory item. |
| Permission | None |
| Entitlement | None for Developer ID |
| Fallback | If `CSSearchableIndex.isIndexingAvailable` returns `false` (should not happen on macOS 13+): skip indexing silently. |

---

**Integration 12: Quick Look Extension (Receipt Preview)** `[v1.1]`

| Attribute | Detail |
|---|---|
| API | `QuickLook.QLPreviewingController` — separate App Extension target |
| Target name | `LocalOCRQuickLook` (bundle ID `com.localocr.macos.quicklook`) |
| Swift file | `Native/QuickLookExtension/PreviewProvider.swift` |
| Supported types | Custom UTType `com.localocr.receipt` declared in both the app target and extension target `Info.plist` |
| Preview content | Renders the receipt image (fetched from server, cached) + a formatted metadata overlay: store name, date, total, line item count |
| Trigger | User selects a receipt row in `ReceiptListView` and presses Space; or Finder Quick Look on a cached `.receipt` file |
| Out of v1.0 | Deferred per §2.4 — extension target adds build complexity and a separate notarization surface. |

---

**Integration 13: Share Sheet (Receipt Export)** `[v1.1]`

| Attribute | Detail |
|---|---|
| API | SwiftUI `ShareLink(item: receiptImage, subject: Text("Receipt"), message: Text(summary))` |
| Swift file | `Views/Receipts/ReceiptInspectorPanel.swift` |
| Share targets | AirDrop (to iPhone for iMessage forward), Mail, Messages |
| Trigger | "Share Receipt" button (toolbar item in Receipt Inspector) |
| Out of v1.0 | Deferred per §2.4. |

---

**App Sandbox and Entitlements (`LocalOCR/LocalOCR.entitlements`)**

This build is **Developer ID distributed, non-sandboxed** (§2.1). The entitlements file is still required for Hardened Runtime (mandatory for notarization).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Hardened Runtime: required for notarization -->
    <key>com.apple.security.cs.allow-jit</key>
    <false/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <false/>

    <!-- Network access: talk to the Flask server -->
    <key>com.apple.security.network.client</key>
    <true/>

    <!-- File access: NSOpenPanel / NSSavePanel / Finder drops -->
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>

    <!-- Camera: Continuity Camera via AVFoundation -->
    <key>com.apple.security.device.camera</key>
    <true/>

    <!-- App Sandbox: NOT enabled for Developer ID direct distribution -->
    <!-- com.apple.security.app-sandbox is intentionally absent -->
</dict>
</plist>
```

**Note on `com.apple.security.cs.disable-library-validation`**: Set to `false`. KeychainAccess and Kingfisher are built from source via SPM and embedded in the app binary — no separately-signed dylibs are loaded at runtime. If a future dependency introduces a separately-signed dylib (e.g. a pre-built framework), this flag must be set to `true` and the dependency reviewed.

**Note on `com.apple.security.cs.allow-jit`**: Set to `false`. WKWebView in the SankeyWebView component uses the JIT-less JavaScript engine when this entitlement is absent. The Sankey chart template uses straightforward D3-based rendering that does not require JIT compilation; performance on arm64 Macs without JIT is acceptable for a static chart render.

---

### 4.7 WINDOW MANAGEMENT IMPLEMENTATION

The app has six distinct window types. Each is fully specified below with its SwiftUI scene, sizing, persistence, and multi-instance rules.

---

**Window 1: Main Window**

| Attribute | Detail |
|---|---|
| SwiftUI scene | `WindowGroup("LocalOCR", id: "main") { ContentView() }` |
| Content view | `ContentView` — root `NavigationSplitView` with sidebar, content column, and optional detail column |
| Default size | `.defaultSize(width: 1200, height: 750)` |
| Minimum size | `.windowResizability(.contentMinSize)` with `ContentView.frame(minWidth: 900, minHeight: 600)` |
| Frame persistence | `NSWindow.setFrameAutosaveName("MainWindow")` — position and size restored across launches |
| Single instance | `WindowGroup` presents one window by default; the build agent must add `.defaultLaunchBehavior(.presented)` and override `applicationShouldHandleReopen(_:hasVisibleWindows:)` in `AppDelegate` to bring the existing window forward on Dock click rather than open a second instance |
| Close behavior | `applicationShouldTerminateAfterLastWindowClosed` returns `false` — app hides to menu bar when main window is closed (standard for apps with a menu bar item). Only ⌘Q or Quit from menu bar truly quits. |
| Commands | `.commands { AppMenuCommands() }` — adds File → New Window, File → Open (⌘O), View → Show Sidebar, View → Show Inspector, Window menu items |

---

**Window 2: Settings**

| Attribute | Detail |
|---|---|
| SwiftUI scene | `Settings { SettingsView() }` (SwiftUI built-in Settings scene — renders as the system Preferences-style window) |
| Access | ⌘, (standard macOS shortcut); LocalOCR menu → Settings |
| Size | Driven by content; minimum `NSSize(width: 680, height: 400)`; tabs switch without resizing (each pane uses `.frame(minHeight: 400)`) |
| Frame persistence | Handled automatically by the `Settings` scene |
| Single instance | Guaranteed by `Settings` scene (macOS enforces one Settings window per app) |
| Tabs | General, Account, AI Models, Trusted Devices, Telegram, Notifications, Backup, Advanced — 8 panes (§3.8) |

---

**Window 3: Receipt Inspector**

| Attribute | Detail |
|---|---|
| SwiftUI scene | `WindowGroup(id: "receipt", for: Int64.self) { $receiptId in ReceiptInspectorPanel(receiptId: receiptId ?? 0) }` |
| Access | Double-click on a receipt row in `ReceiptListView`; URL scheme `localocr://receipt/<id>`; ⌘↩ on selected receipt row |
| Default size | `.defaultSize(width: 800, height: 900)` |
| Minimum size | `minWidth: 640, minHeight: 600` |
| Frame persistence | `NSWindow.setFrameAutosaveName("ReceiptInspector-\(receiptId)")` — each unique receipt ID gets its own autosaved frame, so users who position the inspector on a secondary monitor don't have it reset on reopen |
| Multi-instance | Supported — user can open multiple receipts side by side. Each call to `openWindow(id: "receipt", value: receiptId)` opens a new instance. `WindowGroup` handles distinct instances by value. |
| Close | ⌘W closes the active inspector window; does not affect main window |

---

**Window 4: OCR Upload**

| Attribute | Detail |
|---|---|
| SwiftUI scene | Two modes: (a) as a **sheet** over the main window when triggered from within the app (e.g. toolbar button, ⌘U); (b) as a separate **window** when triggered by global shortcut ⌃⌘R or Finder drop when main window is not frontmost. |
| Sheet mode | `.sheet(isPresented: $showOCRUpload) { OCRUploadView(...) }` attached to `ContentView` |
| Window mode | `WindowGroup(id: "ocr-upload") { OCRUploadView(...) }` with `openWindow(id: "ocr-upload")` called from `GlobalShortcutManager` |
| Default size (window mode) | `.defaultSize(width: 700, height: 600)` |
| Frame persistence | `NSWindow.setFrameAutosaveName("OCRUpload")` (window mode only) |
| Single instance | Both modes: if OCRUploadView is already visible, bring it forward rather than open a second one. `GlobalShortcutManager` checks `NSApp.windows` for an existing OCRUpload window before calling `openWindow`. |
| Close | ⌘W or Esc in sheet mode cancels and dismisses; ⌘W in window mode closes the window. Pending upload URL cleared. |

---

**Window 5: Plaid Link Sheet**

| Attribute | Detail |
|---|---|
| SwiftUI scene | Presented as a sheet over the main window (not a separate window) |
| Content | `ASWebAuthenticationSession` initiated from `PlaidAccountsView`; the Plaid-hosted Link URL opens in the system browser or a `WKWebView` sheet. Redirect to `localocr://oauth/callback` with Plaid's `public_token` query parameter is intercepted by `Router.handleURL`. |
| Size | N/A (ASWebAuthenticationSession manages its own presentation as a Safari-style sheet) |
| Close | User taps "Cancel" in Plaid's UI; `ASWebAuthenticationSession` calls its completion handler with `ASWebAuthenticationSessionError.canceledLogin`. Show a toast "Plaid connection cancelled." |
| Frame persistence | N/A |

---

**Window 6: Menu Bar Popover**

| Attribute | Detail |
|---|---|
| API | SwiftUI `.menuBarExtra` scene or `NSPopover` anchored to `NSStatusItem` in `MenuBarController` |
| Content | `MenuBarPopoverView` |
| Size | Approximately `320 × 340` points; fixed (no resize handle) |
| Behavior | Opens on status item click; closes on click outside or Esc. If main window is visible, clicking "Open LocalOCR" just brings it forward — does not open a second main window. |
| Frame persistence | N/A (popover position is fixed relative to menu bar) |

---

**Cmd+W and Quit Behavior Summary**

| Context | ⌘W behavior | ⌘Q behavior |
|---|---|---|
| Main window focused | Hides the main window (app keeps running; menu bar item persists) | Quits the app (if menu bar is enabled) / quits immediately (if menu bar is disabled) |
| Receipt Inspector focused | Closes that inspector window | Quits app |
| OCR Upload window focused | Closes OCR Upload window (pending upload cleared) | Quits app |
| OCR Upload as sheet focused | Dismisses the sheet (Esc also works) | Quits app |
| Settings focused | Closes Settings window | Quits app |
| Menu bar popover visible | Esc closes popover; ⌘W not intercepted | Quits app |

---

**Stage Manager Compatibility**

No special handling required. All `WindowGroup` windows are standard `NSWindow` instances; macOS Stage Manager treats them as tiles automatically. The main window's minimum size (900 × 600) is large enough to render usefully as a Stage Manager tile. The Receipt Inspector (800 × 900 default) may appear taller than wide in Stage Manager — acceptable; the view scrolls vertically.

---

**Full-Screen Behavior**

All windows support full-screen (`NSWindowCollectionBehaviorFullScreenPrimary` is set automatically by SwiftUI). In full-screen:
- The `NavigationSplitView` sidebar persists; reveals on mouse hover at left edge if auto-hidden by the user.
- The toolbar auto-hides per macOS convention; revealed by mousing to the top edge.
- The Inspector column (Receipt Inspector, if pinned) persists alongside the content column.
- The menu bar status icon persists in its own full-screen Space and can be clicked without exiting full-screen.
- `Settings` and OCR Upload window open in separate Spaces when the main window is full-screen (standard macOS behavior for modal/panel windows).

---

### 4.8 BUILD & DISTRIBUTION PLAN

All commands in this section are exact shell commands the build agent can run verbatim (after substituting `<TEAM_ID>`, `<APPLE_ID>`, etc.). Commands assume working directory is the project root (`LocalOCR.macOS/`).

---

#### Development Builds

**Build (compile only, no run)**:
```sh
xcodebuild \
  -scheme LocalOCR \
  -configuration Debug \
  -destination 'platform=macOS,arch=arm64' \
  build \
  ONLY_ACTIVE_ARCH=YES
```

**Run from terminal** (build + launch):
```sh
xcodebuild \
  -scheme LocalOCR \
  -configuration Debug \
  -destination 'platform=macOS,arch=arm64' \
  build \
  ONLY_ACTIVE_ARCH=YES && \
open "$(xcodebuild -scheme LocalOCR -configuration Debug -showBuildSettings | grep ' BUILT_PRODUCTS_DIR' | awk '{print $3}')/LocalOCR.app"
```

**Recommended**: Use Xcode IDE (⌘R) for development. The `xcodebuild` commands above are for CI and sanity checks only.

**Hot reload**: SwiftUI does not support hot reload in the React/Flutter sense. Use **Xcode Previews** (`#Preview` macros per view) for isolated component iteration — no server connection required for previews. For full end-to-end iteration, use Xcode's run-replace (⌘R while app is running replaces the running binary without a full cold launch on macOS 14+).

**Debug tools**:
- `os.log` framework for structured logging (`Logger(subsystem: "com.localocr.macos", category: "networking")`). Visible in Console.app filtered by subsystem.
- Xcode View Debugger (Debug → View Debugging → Capture View Hierarchy) for SwiftUI layout issues.
- Xcode Memory Graph (Debug → Memory Graph Debugger) for retain cycle detection.
- Instruments → Network (for request timing), Allocations (for memory leaks), Time Profiler (for scroll performance).

---

#### Running Tests

**Unit tests**:
```sh
xcodebuild \
  -scheme LocalOCR \
  -testPlan LocalOCRTests \
  -destination 'platform=macOS,arch=arm64' \
  test
```

**UI tests**:
```sh
xcodebuild \
  -scheme LocalOCR \
  -testPlan LocalOCRUITests \
  -destination 'platform=macOS,arch=arm64' \
  test
```

UI tests require the app to be able to connect to a running Flask server at the configured API base URL (or a mock server). The UI test target should set `API_BASE_URL` via a launch argument processed in `AppDelegate` during `UITESTING` scheme condition.

---

#### Release Build (Apple Silicon arm64)

**Step 1 — Archive**:
```sh
xcodebuild \
  -scheme LocalOCR \
  -configuration Release \
  -destination 'generic/platform=macOS,variant=Mac,arch=arm64' \
  -archivePath ./build/LocalOCR.xcarchive \
  archive \
  CODE_SIGN_IDENTITY="Developer ID Application: <Your Name> (<TEAM_ID>)" \
  DEVELOPMENT_TEAM=<TEAM_ID>
```

**Step 2 — Export**:
```sh
xcodebuild \
  -exportArchive \
  -archivePath ./build/LocalOCR.xcarchive \
  -exportPath ./build/Release \
  -exportOptionsPlist ExportOptions.plist
```

Output: `./build/Release/LocalOCR.app`

**`ExportOptions.plist`** (file at project root):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>developer-id</string>
    <key>teamID</key>
    <string>REPLACE_WITH_TEAM_ID</string>
    <key>signingCertificate</key>
    <string>Developer ID Application</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>stripSwiftSymbols</key>
    <true/>
    <key>uploadSymbols</key>
    <false/>
</dict>
</plist>
```

The build agent must replace `REPLACE_WITH_TEAM_ID` with the actual Apple Developer Team ID before running the export step. The Team ID is a 10-character alphanumeric string found in the Apple Developer portal under Membership.

---

#### Step 3 — Create DMG

Install `create-dmg` (Homebrew):
```sh
brew install create-dmg
```

Run `scripts/create-dmg.sh`:
```sh
#!/bin/bash
set -euo pipefail

APP_PATH="./build/Release/LocalOCR.app"
DMG_PATH="./build/Release/LocalOCR-1.0.0-arm64.dmg"
VOLUME_NAME="LocalOCR"

create-dmg \
  --volname "$VOLUME_NAME" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "LocalOCR.app" 175 190 \
  --hide-extension "LocalOCR.app" \
  --app-drop-link 425 190 \
  "$DMG_PATH" \
  "$APP_PATH"

echo "DMG created: $DMG_PATH"
```

Output: `./build/Release/LocalOCR-1.0.0-arm64.dmg`

---

#### Step 4 — Notarization

Apple requires notarization for Developer ID apps to pass Gatekeeper on end-user Macs.

**Prerequisites**:
- Apple Developer account with Developer ID Application certificate in Keychain
- App-specific password generated at appleid.apple.com (stored in environment, never in code)
- `xcrun notarytool` available (Xcode 13+)

**Notarize** (`scripts/notarize.sh`):
```sh
#!/bin/bash
set -euo pipefail

# Required environment variables:
# APPLE_ID      — your Apple ID email (e.g. dev@example.com)
# TEAM_ID       — 10-char Team ID
# APP_PASSWORD  — app-specific password from appleid.apple.com

DMG_PATH="./build/Release/LocalOCR-1.0.0-arm64.dmg"

echo "Submitting for notarization..."
xcrun notarytool submit "$DMG_PATH" \
  --apple-id "$APPLE_ID" \
  --team-id "$TEAM_ID" \
  --password "$APP_PASSWORD" \
  --wait \
  --timeout 600

echo "Stapling ticket..."
xcrun stapler staple "$DMG_PATH"

echo "Verifying staple..."
xcrun stapler validate "$DMG_PATH"

echo "Notarization complete: $DMG_PATH"
```

Expected notarization time: 2–5 minutes. If `--wait` times out at 600 seconds, run `xcrun notarytool history` to check status and `xcrun notarytool log <submission-id>` for failure details.

**Common notarization failures and fixes**:
- `The binary uses an unsupported cryptographic algorithm` — check that Hardened Runtime is enabled in Xcode target → Signing & Capabilities → Hardened Runtime.
- `Found an embedded script` — if any dependency includes a shell script, it must be removed or the `com.apple.security.cs.disable-library-validation` flag must be evaluated.
- `Invalid signature` — ensure the `.app` is signed before packaging into DMG. Verify with: `codesign --verify --verbose=4 ./build/Release/LocalOCR.app`

---

#### Code Signing Verification

Before submitting for notarization, verify:
```sh
# Verify app signature
codesign --verify --deep --strict --verbose=4 ./build/Release/LocalOCR.app

# Check entitlements match LocalOCR.entitlements
codesign --display --entitlements - ./build/Release/LocalOCR.app

# Verify Hardened Runtime is set
codesign --display --verbose=4 ./build/Release/LocalOCR.app | grep 'flags'
# Expected: flags=0x10000(runtime)  — "runtime" means Hardened Runtime is on
```

---

#### v1.1 Universal Binary (Intel + Apple Silicon)

Deferred per §2.1. When ready:

1. Change `-destination` in archive step to `'generic/platform=macOS'` (drops `arch=arm64`).
2. Verify no `#if arch(arm64)` guards that would exclude Intel — there should be none in the v1.0 codebase since all APIs used (SwiftUI, AppKit, AVFoundation, etc.) are universal.
3. Update `ExportOptions.plist` — no changes needed; `method=developer-id` supports universal binaries.
4. Re-run full archive → export → DMG → notarize pipeline.
5. Update DMG filename to `LocalOCR-1.1.0-universal.dmg`.

Note: Swift Package Manager dependencies (KeychainAccess, Kingfisher) both provide pre-built universal xcframeworks. No manual lipo step is required.

---

#### Auto-Update (Sparkle 2.x) — Deferred to v1.1

Sparkle 2.x (`sparkle-project/Sparkle`, version `2.6.x`) will be added in v1.1 to enable in-app update checks from a hosted `appcast.xml` file. Integration requires:

1. Add `Sparkle` to `Package.swift` dependencies.
2. Call `SPUUpdater` in `AppDelegate` to check for updates on launch (configurable interval).
3. Host `appcast.xml` and the DMG on a public URL (GitHub Releases is suitable).
4. Generate `EdDSA` signing key for the appcast via `./bin/generate_keys` (Sparkle's included tool); store private key securely (not in the repo).
5. Add `SUFeedURL` (appcast URL) and `SUPublicEDKey` (EdDSA public key) to `Info.plist`.

For v1.0: no Sparkle, no `SUFeedURL`. Users check GitHub Releases manually. The About pane shows the current version and a "Check for Updates" link to the Releases page.

---

*End of Section 4 — TECHNICAL ARCHITECTURE*

---

## 5. IMPLEMENTATION SPEC
*Authored by: [AGENT 5 — macOS FRONTEND ENGINEER]*

### 5.1 COMPONENT IMPLEMENTATION SPECS

Each component corresponds to an entry in §3.6 (26 components). File paths follow §4.2 exactly. Every component is a SwiftUI `View` (or `ViewModifier`) unless noted otherwise. All color tokens reference `DesignTokens.swift` (§4.2 `Design/DesignTokens.swift`); all type roles reference `Typography.swift`.

---

**Component: Card**
File: `LocalOCR/Components/Card.swift`

```swift
struct Card<Content: View>: View {
    var padding: CGFloat = 16          // internal padding; override for compact cards
    var cornerRadius: CGFloat = 10     // §3.1 card radius
    @ViewBuilder var content: () -> Content
}
```

Internal state: `@State private var isHovered = false`
Hover state: shadow increases from `0` to `shadowRadius: 4, x: 0, y: 2` via `.animation(.easeOut(duration: 0.15))`; background color shifts from `.surface` to `.surface` (unchanged — elevation is communicated by shadow only)
Focus behavior: Not interactive by default; if wrapped in a `Button`, focus ring appears on the outer container
Keyboard interaction: None (Card is a container, not a button)
Render: `ZStack` → `RoundedRectangle(cornerRadius: cornerRadius).fill(Color.surface)` as background + optional shadow overlay when hovered + `VStack` of content with `.padding(padding)`
Dark mode: `Color.surface` resolves automatically via `DesignTokens` adaptive color
Accessibility:
  - `.accessibilityElement(children: .contain)` — lets VoiceOver traverse children individually
  - No label on the Card itself; child views carry accessibility info
Tests required:
  1. Renders with default padding and corner radius
  2. Shadow increases on hover via `isHovered` state
  3. Content ViewBuilder renders child views
  4. Correct background in light and dark mode via `Color.surface`
  5. VoiceOver children are individually traversable

---

**Component: Badge**
File: `LocalOCR/Components/Badge.swift`

```swift
struct Badge: View {
    let text: String           // label inside the pill
    let color: Color           // background color (e.g. Color.successDim, Color.warningDim)
    let textColor: Color       // foreground text color (e.g. Color.success, Color.warning)
    var fontSize: Font = .caption  // §3.1 caption1 (10pt)
}
```

Internal state: None
Hover state: None
Focus behavior: Not interactive
Keyboard interaction: None
Render: `Text(text)` with `.font(fontSize).foregroundColor(textColor)` padded `.padding(.horizontal, 8).padding(.vertical, 3)` inside `Capsule().fill(color)`
Dark mode: Automatic via token colors
Accessibility:
  - `.accessibilityLabel(text)` — pill text read aloud
  - `.accessibilityAddTraits(.isStaticText)`
Tests required:
  1. Text renders inside a capsule shape
  2. Custom color is applied to background and foreground
  3. Default font is `.caption`
  4. Accessibility label matches `text` parameter
  5. Renders in dark mode without clipping

---

**Component: LowStockPill**
File: `LocalOCR/Components/LowStockPill.swift`

```swift
struct LowStockPill: View {
    enum StockState { case inStock, low, out, manualLow }
    let state: StockState
    let count: Int?    // optional quantity shown inside pill (e.g. "Low 2")
}
```

Internal state: None
Hover state: None
Focus behavior: Not interactive; purely informational
Keyboard interaction: None
Render: Capsule with color and label driven by `state`: `.inStock` → hidden (`.opacity(0)`); `.low` → amber background `Color.warningDim` + amber text "Low"; `.out` → red background `Color.errorDim` + red text "Out"; `.manualLow` → amber background + dashed 1pt border `Color.warning`. Height fixed 22pt. If `count != nil`, appends the count: "Low 2".
Dark mode: Token-driven
Accessibility:
  - `.accessibilityLabel` varies: `"In stock"`, `"Low stock"`, `"Out of stock"`, `"Marked low"`
  - `.accessibilityHint("Check inventory for this item")`
Tests required:
  1. `.inStock` state renders with zero opacity
  2. `.low` state renders amber pill with "Low" text
  3. `.out` state renders red pill with "Out" text
  4. `.manualLow` state renders with dashed border
  5. Accessibility label matches stock state

---

**Component: CategoryChip**
File: `LocalOCR/Components/CategoryChip.swift`

```swift
struct CategoryChip: View {
    let label: String
    var isSelected: Bool = false
    var isInteractive: Bool = true   // false in Kitchen View (non-tappable)
    let action: (() -> Void)?        // nil when isInteractive = false
}
```

Internal state: None (selection managed by parent)
Hover state: When `isInteractive`: border brightens from `Color.border` to `Color.accent` on hover
Focus behavior: Focus ring on chip when `isInteractive = true`; tab-focusable
Keyboard interaction: `Space` or `Return` fires `action` when focused
Render: `Text(label)` inside `RoundedRectangle(cornerRadius: 4)` with 1pt stroke and horizontal padding 8pt / vertical 4pt. When `isSelected`: fill with `Color.accentDim`, stroke `Color.accent`, text `Color.accent`. When not selected: fill clear, stroke `Color.border`, text `Color.secondaryLabel`. Color is domain-driven for category chips (Grocery=blue-tinted, Restaurant=amber, Expense=green); for filter chips use `.accent`.
Dark mode: Token-driven
Accessibility:
  - `.accessibilityLabel(label)`
  - `.accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)` when interactive
  - `.accessibilityAddTraits(.isStaticText)` when not interactive
Tests required:
  1. Selected state fills with accent color
  2. Non-interactive chip has no tap gesture
  3. `action` fires on `Space` key when focused
  4. Accessibility traits include `.isSelected` when selected
  5. Renders correctly in dark mode

---

**Component: KeyValueRow**
File: `LocalOCR/Components/KeyValueRow.swift`

```swift
struct KeyValueRow: View {
    let key: String          // left-side label (secondary color)
    let value: String        // right-side value (primary, monospaced for currency)
    var isCurrency: Bool = false   // if true, value uses .mono-body font
    var valueColor: Color = .primary  // override for success/error states
}
```

Internal state: None
Hover state: None (display only)
Focus behavior: Not focusable by default
Keyboard interaction: None
Render: `HStack` → `Text(key).font(.subheadline).foregroundColor(Color.secondaryLabel)` + `Spacer()` + `Text(value).font(isCurrency ? .monoBody : .body).foregroundColor(valueColor)`. Height 32pt via `.frame(minHeight: 32)`.
Dark mode: Automatic
Accessibility:
  - `.accessibilityElement(children: .combine)` — reads as "[key]: [value]"
  - `.accessibilityLabel("\(key): \(value)")`
Tests required:
  1. Key is secondary color, value is primary
  2. Currency flag applies monospaced font to value
  3. `valueColor` override sets value foreground
  4. Accessibility combines key and value in label
  5. `Spacer()` pushes key and value to opposite edges

---

**Component: DropZone**
File: `LocalOCR/Components/DropZone.swift`

```swift
struct DropZone: View {
    let onFilesDropped: ([URL]) -> Void   // called with validated file URLs
    var isProcessing: Bool = false         // if true, shows spinner, disables drop
    let onBrowse: () -> Void               // called when user clicks to open NSOpenPanel
}
```

Internal state:
- `@State private var isDragOver = false` — true when a valid drag is hovering
- `@State private var isDragInvalid = false` — true when drag is hovering with invalid type
- `@State private var droppedFileName: String? = nil` — name of selected file (after drop or browse)

Hover state: When `isDragOver = true`: background fills with `Color.dropTarget`, border becomes solid 2pt `Color.accent`. When `isDragInvalid = true`: border becomes red 2pt. Transition animated `.easeOut(duration: 0.15)`.
Focus behavior: Focus ring on the entire drop zone when clicked; `Return` triggers `onBrowse()`
Keyboard interaction: `Return` or `Space` fires `onBrowse()`
Render:
- `ZStack` → `RoundedRectangle(cornerRadius: 8)` with dashed stroke (when idle) or solid stroke (when drag-over) + content `VStack`:
  - If no file selected: `Image(systemName: "photo.badge.plus").font(.system(size: 40))` + `Text("Drop a receipt here").font(.headline)` + `Text("or click to browse").font(.subheadline).secondary`
  - If file selected: `Image(systemName: fileIcon).font(.system(size: 32))` + `Text(droppedFileName)` + `Button("× Remove") { droppedFileName = nil }`
  - If `isProcessing`: `ProgressView()` + `Text("Processing…")`
- `.onDrop(of: [.jpeg, .png, .heic, .pdf], isTargeted: $isDragOver)` — `NSItemProvider` extraction via `FileDropHandler`
- `.onTapGesture { onBrowse() }`
Dark mode: `Color.dropTarget` token adapts; dashed border uses `Color.border`
Accessibility:
  - `.accessibilityLabel("Receipt drop zone. Drag a JPEG, PNG, HEIC, or PDF here, or activate to open file picker.")`
  - `.accessibilityHint("Double-tap to open file picker")`
  - `.accessibilityAddTraits(.isButton)`
Tests required:
  1. `isDragOver` state changes dashed border to solid accent border
  2. Invalid file type sets `isDragInvalid` state with red border
  3. `onFilesDropped` called only for valid UTTypes
  4. Tapping fires `onBrowse`
  5. `isProcessing = true` shows ProgressView and disables drop

---

**Component: ReceiptThumbnail**
File: `LocalOCR/Components/ReceiptThumbnail.swift`

```swift
struct ReceiptThumbnail: View {
    let url: URL?               // authenticated server URL; nil shows placeholder
    var size: CGFloat = 36      // both width and height (square); common: 36pt list row, 72pt inspector
    var cornerRadius: CGFloat = 4
}
```

Internal state: Managed by `KFImage` (Kingfisher); `@State private var loadFailed = false`
Hover state: None
Focus behavior: Not interactive
Keyboard interaction: None
Render: `KFImage(url)` from Kingfisher with `.requestModifier(cookieRequestModifier)` (injects session cookie header from `HTTPCookieStorage.shared`) → `.placeholder { shimmerPlaceholder }` (skeleton shimmer per `SkeletonView`) → `.onFailure { _ in loadFailed = true }`. If `loadFailed`: `Image(systemName: "photo.fill").foregroundColor(Color.tertiaryLabel)`. Result clipped to `RoundedRectangle(cornerRadius: cornerRadius).frame(width: size, height: size).aspectRatio(contentMode: .fill)`.
Dark mode: Placeholder uses tertiary label color; loaded image is passthrough
Accessibility:
  - `.accessibilityLabel("Receipt image")`
  - `.accessibilityHint("Double-tap to view full receipt")`
Tests required:
  1. Renders shimmer skeleton when loading
  2. Renders broken-image icon on failure
  3. Image is clipped to rounded rectangle
  4. Size parameter controls width and height
  5. Cookie header is attached to image request

---

**Component: EmptyStateView**
File: `LocalOCR/Components/EmptyStateView.swift`

```swift
struct EmptyStateView: View {
    let systemImage: String         // SF Symbol name (e.g. "cart.circle")
    let title: String
    let subtitle: String
    var ctaLabel: String? = nil     // if nil, no button shown
    var ctaAction: (() -> Void)? = nil
    var secondaryCtaLabel: String? = nil
    var secondaryCtaAction: (() -> Void)? = nil
}
```

Internal state: None
Hover state: CTA button highlights on hover (standard `PrimaryButtonStyle`)
Focus behavior: CTA button is tab-focusable
Keyboard interaction: `Return` on focused CTA fires `ctaAction`
Render: `VStack(spacing: 20)` → `Image(systemName: systemImage).font(.system(size: 48)).foregroundColor(Color.tertiaryLabel)` + `Text(title).font(.title2).fontWeight(.semibold)` + `Text(subtitle).font(.body).foregroundColor(Color.secondaryLabel).multilineTextAlignment(.center)` + (if `ctaLabel`) `PrimaryButton(ctaLabel, action: ctaAction)`. Optional secondary CTA rendered as `SecondaryButton` below.
Dark mode: All token-driven
Accessibility:
  - `VStack.accessibilityElement(children: .combine)`
  - `.accessibilityLabel("\(title). \(subtitle)")`
  - CTA button: `.accessibilityLabel(ctaLabel)`
Tests required:
  1. Renders SF Symbol at 48pt
  2. CTA button is absent when `ctaLabel = nil`
  3. Secondary CTA rendered as SecondaryButton
  4. `ctaAction` fires on button tap
  5. Accessibility label combines title and subtitle

---

**Component: SkeletonView**
File: `LocalOCR/Components/SkeletonView.swift`

```swift
struct SkeletonView: View {
    var width: CGFloat? = nil     // nil = full width
    var height: CGFloat = 14      // default 14pt text-line height
    var cornerRadius: CGFloat = 4
}
```

Internal state: `@State private var phase: CGFloat = 0` — animation phase for shimmer gradient
Hover state: None
Focus behavior: Not focusable
Keyboard interaction: None
Render: `RoundedRectangle(cornerRadius: cornerRadius)` with `LinearGradient` moving left-to-right: `[Color.surface2, Color.border, Color.surface2]`. `.onAppear { withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) { phase = 1 } }`. Width uses `.frame(maxWidth: width ?? .infinity, minHeight: height, maxHeight: height)`. Checks `@Environment(\.accessibilityReduceMotion)` — if true, renders a static `Color.surface2` block with no animation.
Dark mode: Token-driven shimmer colors adapt
Accessibility:
  - `.accessibilityLabel("Loading")`
  - `.accessibilityAddTraits(.updatesFrequently)` — announces to VoiceOver that content is loading
Tests required:
  1. Animation starts on appear (phase changes from 0 to 1)
  2. `accessibilityReduceMotion = true` renders static block without animation
  3. Width clamps to full available width when `width = nil`
  4. Corner radius applied correctly
  5. Accessibility label is "Loading"

---

**Component: ProgressBarView**
File: `LocalOCR/Components/ProgressBarView.swift`

```swift
struct ProgressBarView: View {
    let value: Double        // current value (0.0 – max)
    let maximum: Double      // expected maximum
    var height: CGFloat = 8
    var animate: Bool = true  // animates fill change with spring
}
```

Internal state: `@State private var displayedRatio: Double = 0`
Hover state: None
Focus behavior: Not interactive
Keyboard interaction: None
Render: `ZStack(alignment: .leading)` → track `Capsule().fill(Color.surface2).frame(height: height)` + fill `Capsule().fill(fillColor).frame(width: trackWidth * clampedRatio, height: height)`. Color logic: `ratio < 0.80` → `Color.success`; `ratio < 0.95` → `Color.warning`; else → `Color.error`. On value change: if `animate`, `withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) { displayedRatio = ratio }`.
Dark mode: Token-driven
Accessibility:
  - `.accessibilityValue("\(Int(value)) of \(Int(maximum))")`
  - `.accessibilityLabel("Progress")`
  - `.accessibilityAddTraits(.updatesFrequently)`
Tests required:
  1. Fill color is green when ratio < 0.80
  2. Fill color is amber when 0.80 ≤ ratio < 0.95
  3. Fill color is red when ratio ≥ 0.95
  4. Animated spring transition on value change
  5. Accessibility value reflects numeric values

---

**Component: Toast**
File: `LocalOCR/Components/Toast.swift`

```swift
struct Toast: View {
    enum Severity { case info, success, warning, error }
    let message: String
    let severity: Severity
    var duration: Double = 4.0         // seconds before auto-dismiss
    let onDismiss: () -> Void
}

// Host modifier: adds toast overlay to any view
struct ToastHost: ViewModifier {
    @EnvironmentObject var toastQueue: ToastQueue   // ObservableObject holding queue
}
```

Internal state: `@State private var isVisible = false` — drives `.transition(.move(edge: .top).combined(with: .opacity))`
Hover state: None (dismiss-on-hover would be confusing)
Focus behavior: `×` dismiss button is tab-focusable when visible
Keyboard interaction: `Esc` dismisses active toast (handled in `ToastHost`)
Render: `HStack(spacing: 12)` → severity icon (`circle.fill` tinted) + `Text(message).font(.callout)` + `Spacer()` + `Button("×") { onDismiss() }`. Background: `.padding(12).background(severityBackground).cornerRadius(10).shadow(radius: 4)`. Anchored to `.topTrailing` of the host view with `.padding(.top, 8).padding(.trailing, 16)`. `.onAppear { isVisible = true; scheduleAutoDismiss() }`.
Dark mode: Severity backgrounds use token colors (`info` → accent-dim, `success` → success-dim, `warning` → warning-dim, `error` → error-dim)
Accessibility:
  - `.accessibilityLabel("\(severityLabel): \(message)")`
  - `.accessibilityAddTraits(.isStaticText)`
  - Uses `UIAccessibility.post(notification: .announcement, argument: message)` on appear for immediate VoiceOver reading
Tests required:
  1. Toast appears with slide-from-top transition
  2. Auto-dismisses after `duration` seconds
  3. `×` button calls `onDismiss`
  4. Severity affects background color
  5. VoiceOver announcement posted on appear

---

**Component: SankeyWebView**
File: `LocalOCR/Components/SankeyWebView.swift`

```swift
struct SankeyWebView: NSViewRepresentable {
    let data: SankeyData        // typed struct with nodes + links arrays
    var onError: ((Error) -> Void)? = nil
}
```

Internal state: `@State private var isLoaded = false` (set via `WKNavigationDelegate.webView(_:didFinish:)`)
Hover state: Web-native hover effects within the WKWebView; no SwiftUI hover
Focus behavior: `WKWebView` handles its own focus and keyboard events
Keyboard interaction: Delegated to the embedded web page
Render: `NSViewRepresentable` wrapping `WKWebView`. On load: inject `window.setSankeyData(json)` via `WKWebView.evaluateJavaScript`. While loading: overlay `ProgressView()`. On error: overlay `EmptyStateView` with retry button. The HTML template at `Resources/HTML/sankey-template.html` uses D3 for Sankey rendering and exports `window.setSankeyData(json)` as the injection point. `WKScriptMessageHandler` receives resize events from the web page to update the view's frame.
Dark mode: The HTML template reads `window.matchMedia('(prefers-color-scheme: dark)')` and applies dark palette tokens at the CSS level
Accessibility:
  - `.accessibilityLabel("Spending flow chart")`
  - `.accessibilityHint("Shows how spending flows between categories")`
  - Chart itself is not VoiceOver-traversable (web canvas); companion list view in `SpendingByCategoryView` provides the accessible data table
Tests required:
  1. Loads `sankey-template.html` from app bundle
  2. Injects data via `setSankeyData` on data change
  3. Shows `ProgressView` while loading
  4. Shows error `EmptyStateView` on navigation failure
  5. Respects `prefers-color-scheme` from system appearance

---

**Component: SpendingBarChart**
File: Inline within `SpendingByCategoryView.swift` and `ExpenseAnalyticsView.swift` (not a standalone component — uses SwiftCharts directly)

```swift
// Used inline:
Chart(categories, id: \.name) { category in
    BarMark(
        x: .value("Amount", category.total),
        y: .value("Category", category.name)
    )
    .foregroundStyle(isSelected(category) ? Color.accent : Color.accent.opacity(0.6))
    .annotation(position: .trailing) {
        Text(category.formattedTotal).font(.caption.monospaced())
    }
}
.chartXAxis { ... }
.chartOverlay { proxy in ... }  // hover tooltip
```

Note: This is declared inline in each analytics view, not as a reusable struct, because `SwiftCharts.Chart` data generics make parameterization complex. The pattern is documented here for build consistency.

Accessibility:
  - SwiftCharts generates automatic VoiceOver descriptions: "Category [name], [amount]"
  - Supplement with `.accessibilityChartDescriptor` for a comprehensive chart summary

---

**Component: InlineEditableCell**
File: `LocalOCR/Components/InlineEditableCell.swift`

```swift
struct InlineEditableCell: View {
    @Binding var text: String          // the value being edited
    var placeholder: String = ""
    let onCommit: (String) -> Void     // called with new value on Return or blur
    let onCancel: () -> Void           // called on Esc — reverts to original
    var font: Font = .body
    var isEditing: Bool = false        // parent can force editing mode
}
```

Internal state:
- `@State private var isLocallyEditing = false`
- `@State private var editingText = ""`  — local copy during edit; not committed until `onCommit`
- `@State private var isHovered = false`

Hover state: When `!isLocallyEditing && isHovered`: text gains a subtle underline (`.underline(true, color: .tertiaryLabel)`) hinting it is editable
Focus behavior: When editing: standard `TextField` focus ring; tab moves focus to next element via `@FocusState`
Keyboard interaction: `Return` → calls `onCommit(editingText)` + sets `isLocallyEditing = false`; `Esc` → calls `onCancel()` + restores original text + `isLocallyEditing = false`; `F2` (from parent via `.onKeyPress`) → enters editing mode
Render: When `!isLocallyEditing`: `Text(text).font(font).onHover { isHovered = $0 }.onTapGesture(count: 2) { startEditing() }`. When `isLocallyEditing`: `TextField(placeholder, text: $editingText).font(font).textFieldStyle(.plain).focused($isFocused).onSubmit { onCommit(editingText) }.onKeyPress(.escape) { onCancel(); return .handled }`.
Dark mode: Automatic
Accessibility:
  - Display mode: `.accessibilityLabel(text).accessibilityHint("Double-tap to edit")`
  - Edit mode: `.accessibilityLabel("Editing \(placeholder)")`
Tests required:
  1. Double-tap enters editing mode
  2. Return calls `onCommit` with current edit text
  3. Esc calls `onCancel` and restores original text
  4. Hover shows underline hint
  5. `isLocallyEditing = true` renders TextField, not Text

---

**Component: ContextMenuModifiers**
File: `LocalOCR/Components/ContextMenuModifiers.swift`

Implements reusable `ViewModifier`s for the context menus defined in §3.5. Each modifier attaches a `.contextMenu {}` block to the caller.

```swift
struct ReceiptRowContextMenu: ViewModifier {
    let receipt: Receipt
    let onOpen: () -> Void
    let onRerunOCR: () -> Void
    let onMarkReviewed: () -> Void
    let onDelete: () -> Void   // admin only; caller passes a no-op if not admin
}

struct InventoryRowContextMenu: ViewModifier {
    let item: InventoryItem
    let onEdit: () -> Void
    let onAddToList: () -> Void
    let onMarkLow: () -> Void
    let onSetLocation: () -> Void
    let onRemove: () -> Void
}

struct ShoppingItemContextMenu: ViewModifier {
    let item: ShoppingListItem
    let onTogglePurchased: () -> Void
    let onEditNote: () -> Void
    let onSetStore: () -> Void
    let onRemove: () -> Void
}

struct FixedBillContextMenu: ViewModifier { ... }
struct PlaidTransactionContextMenu: ViewModifier { ... }
```

Each modifier wraps its target view in `.contextMenu { ... }` with items from §3.5. Destructive items use `Button(role: .destructive)`. Separators are inserted per §3.5 specs.

Tests required:
  1. Receipt context menu shows all §3.5 items
  2. Destructive button uses `.destructive` role (renders red on macOS 14+)
  3. Admin-only items absent when non-admin no-op passed
  4. Correct action fires for each item
  5. Context menu appears on right-click

---

**Component: AttributionPicker**
File: `LocalOCR/Components/AttributionPicker.swift` (presented as `.sheet` from `ReceiptReviewView`)

```swift
struct AttributionPicker: View {
    @Binding var selection: AttributionKind    // .household, .personal, .split
    let users: [User]                          // household users for split checkboxes
    @Binding var splitUserIds: [Int64]         // selected user IDs when .split
    let onSave: () -> Void
    let onSkip: () -> Void
}

enum AttributionKind: String, CaseIterable {
    case household, personal, split
}
```

Internal state:
- `@State private var evenSplit = true` — when false, individual amount fields appear

Hover state: Radio-button-style rows highlight on hover
Focus behavior: First option auto-focused on sheet appear; Tab cycles through options
Keyboard interaction: `⌘1/2/3` for quick Household / Personal / Split selection; `⌘Return` fires `onSave`
Render: `VStack(spacing: 16)` → Title "Who bought this?" + three radio rows (each `HStack` with filled/unfilled circle icon + label) + if `.split` selected: member checkboxes with `Toggle` + even-split toggle + "Save Attribution" `PrimaryButton` + "Skip for now" `Button(.plain)`
Dark mode: Automatic
Accessibility:
  - Radio rows: `.accessibilityRole(.radioButton)` + `.accessibilityAddTraits(selection == option ? .isSelected : [])`
  - `.accessibilityLabel("Household — shared cost")` etc.
Tests required:
  1. Three options render as radio-button-style rows
  2. `.split` selection reveals member checkboxes
  3. `⌘Return` fires `onSave`
  4. `onSkip` fires on "Skip for now"
  5. Accessibility role is `.radioButton` on each option

---

**Component: QRCodeView**
File: `LocalOCR/Components/QRCodeView.swift`

```swift
struct QRCodeView: View {
    let endpoint: QREndpoint    // enum: .loginQR, .shoppingShare(sessionToken: String)
    var size: CGFloat = 200
    let onCopyLink: ((URL) -> Void)?
}

enum QREndpoint {
    case loginQR
    case shoppingShare(sessionToken: String)
    var apiPath: String { ... }
}
```

Internal state:
- `@State private var qrImage: NSImage? = nil`
- `@State private var shareURL: URL? = nil`
- `@State private var isLoading = false`
- `@State private var loadError = false`

Hover state: None
Focus behavior: "Copy Link" button is focusable
Keyboard interaction: `⌘C` copies link to clipboard when focused
Render: `VStack(spacing: 12)` → `AsyncImage(url: apiURL)` with loading skeleton + error state + optional "Copy Link" `SecondaryButton` + expiry `Text` in `.caption.secondary`. If server endpoint fails: falls back to `CoreImage.CIQRCodeGenerator` filter to generate QR locally from the known URL pattern.
Dark mode: QR image is black-on-white by default; the `AsyncImage` renders as-is; the CIFilter fallback generates a dark-mode-aware image
Accessibility:
  - `.accessibilityLabel("QR code for \(endpoint.label)")`
  - `.accessibilityHint("Scan with phone to open \(endpoint.label)")`
  - "Copy Link" button: `.accessibilityLabel("Copy QR link to clipboard")`
Tests required:
  1. Fetches QR PNG from correct API path
  2. Falls back to CIFilter on fetch failure
  3. "Copy Link" copies URL to `NSPasteboard`
  4. Shows `SkeletonView` while loading
  5. Accessibility label includes endpoint context

---

**Component: ModelPicker**
File: `LocalOCR/Components/ModelPicker.swift`

```swift
struct ModelPicker: View {
    @Binding var selectedModelId: Int64?    // nil = server default
    let models: [AIModelConfig]             // fetched from /ai-models
    var isDisabled: Bool = false
    var style: PickerStyle = .menu          // .menu or .segmented
}
```

Internal state: None (selection managed via binding)
Hover state: Standard `Picker(.menuStyle)` system hover
Focus behavior: Standard picker focus ring
Keyboard interaction: Standard picker arrow-key navigation when open
Render: `Picker("AI Model", selection: $selectedModelId)` with `ForEach(models)` producing labels: `"\(model.name) (\(model.priceTier))"`. Models where the user lacks access are shown with "(Locked)" suffix and `.disabled(true)`. Active model is highlighted with a checkmark (automatic in `Picker(.menuStyle)`). If `models.isEmpty`: shows disabled picker with label "No models configured".
Dark mode: System picker appearance
Accessibility:
  - `.accessibilityLabel("AI model selector")`
  - Current selection announced: `"Currently [model name]"`
Tests required:
  1. Renders all enabled models from `models` array
  2. Locked models are disabled
  3. `selectedModelId` binding updates on selection
  4. Empty models array shows disabled "No models configured"
  5. Accessibility label is "AI model selector"

---

**Component: DemoModeBanner**
File: `LocalOCR/Components/DemoModeBanner.swift`

```swift
struct DemoModeBanner: View {
    let onSignIn: () -> Void      // called when "Sign In" CTA is tapped
}
```

Internal state: None (banner is always visible in demo mode; no dismiss)
Hover state: "Sign In" button highlights on hover
Focus behavior: "Sign In" button is tab-focusable and keyboard-accessible
Keyboard interaction: `Return` on focused "Sign In" button fires `onSignIn`
Render: `HStack(spacing: 8)` → `Image(systemName: "eye.fill").foregroundColor(Color.warning)` + `Text("Demo Mode — read-only. Sign in to save.").font(.callout).foregroundColor(Color.label)` + `Spacer()` + `PrimaryButton("Sign In", action: onSignIn)`. Background: `Color.warningDim`. Full width, `.padding(.horizontal, 16).padding(.vertical, 8)`. No close button — must remain visible per §1.7 rule 10.
Dark mode: `Color.warningDim` adapts
Accessibility:
  - `.accessibilityLabel("Demo Mode: read only. Sign in to save changes.")`
  - "Sign In" button: `.accessibilityHint("Opens the login screen")`
Tests required:
  1. Always renders when demo mode is active; cannot be dismissed
  2. `onSignIn` fires on button tap and `Return` when focused
  3. Background color is `Color.warningDim`
  4. Eye icon is present
  5. Accessibility label includes full message

---

### 5.2 VIEW IMPLEMENTATION SPECS

Each view follows the same template structure. File paths are from §4.2 exactly. All 16 MVP views plus Menu Bar Popover and Demo Mode overlay are specified below, ordered by the build phase sequence from §5.8.

---

**View: LoginView**
File: `LocalOCR/Views/Auth/LoginView.swift`
Window: Main Window (pre-auth — no sidebar, no toolbar)
Navigation/routing: App launch → `AuthState.state == .unauthenticated` → `RootView` shows `LoginView`. Navigates away when `AuthState.state` changes to `.authenticated` (transition handled by `RootView` state switch).
Window title: "LocalOCR Extended" (static; set via `.navigationTitle` but not shown in pre-auth window mode)
Toolbar implementation: None (traffic lights only)

Data fetching:
- Query key: `"auth.config"` — `GET /auth/config` on appear to populate `appConfig` (Google OAuth enabled flag, demo flag, server version)
- Hook: `@StateObject var auth = AuthState.shared`
- Loading: Sign In button shows inline `ProgressView` replacing label
- Error: Inline red `Text` below password field for 401 errors; Toast for network errors
- Refetch on appear: No — config loaded once on appear

Mutations:
- `login(email:password:)` — trigger: Sign In button tap or `⌘Return`. Optimistic: button disabled, spinner shown. On success: `AuthState.state` set to `.authenticated`. On error: inline error shown below password field. No cache invalidation (auth is stateless from client perspective).
- `startGoogleOAuth()` — trigger: "Continue with Google" button. Opens `GoogleOAuthSheet` as `.sheet`. No optimistic update. On success: sheet dismisses and `AuthState` updates. On error: toast "Google sign-in failed".
- `setDemoMode()` — trigger: "Try Demo" button. Client-side only — sets `AppState.isDemoMode = true` and `AuthState.state = .authenticated` without any API call.

Local state:
- `@State private var email = ""`
- `@State private var password = ""`
- `@State private var isShowingServerField = false` — toggles server URL edit section
- `@State private var serverURLInput = ""` — editable server URL before "Connect"
- `@FocusState private var focusedField: Field?` — enum `.email`, `.password`

Keyboard handlers:
- `Return` in email field: `.submitLabel(.next)` + `focusedField = .password`
- `Return` in password field: fires `login()` (⌘Return also fires login)
- `.onKeyboardShortcut(.return, modifiers: .command)` on Sign In button

Drag-and-drop handlers: None on login view
Context menu: None
Selection state: None

Component tree (ASCII):
```
LoginView
└── VStack (centered, max width 360pt)
    ├── AppIcon (Image, 128×128)
    ├── Text("LocalOCR Extended") [.largeTitle]
    ├── Text(tagline) [.body.secondary]
    ├── Divider
    ├── TextField (email) [focused: .email]
    ├── SecureField (password) [focused: .password]
    ├── PrimaryButton("Sign In") ← ⌘Return
    ├── SecondaryButton("Continue with Google")
    ├── Divider + "or" label
    ├── Button("Try Demo") [.plain]
    ├── DemoModeBanner (hidden unless isDemoMode)
    └── Disclosure(isExpanded: $isShowingServerField)
        ├── Text("Using server: [host]") [.caption.secondary]
        └── [when expanded] TextField(serverURL) + Button("Connect")
```

Business rules encoded:
- §1.7 rule 10: "Try Demo" sets client-side demo mode; no API write calls made
- §1.7 rule 2: Role check happens post-login via `/auth/me`; not gated here
- §1.6 auth: Email+password POST to `/auth/login`; Google OAuth via `ASWebAuthenticationSession`

Tests required:
  1. Loading state shows ProgressView on Sign In button during login call
  2. Invalid credentials show inline error below password field (not a toast)
  3. "Try Demo" sets `isDemoMode = true` without calling `/auth/login`
  4. `⌘Return` in email field moves focus to password; `⌘Return` in password submits
  5. Server URL change validates via `GET /auth/config` before accepting

---

**View: DashboardView**
File: `LocalOCR/Views/Dashboard/DashboardView.swift`
Window: Main Window (primary content column of `NavigationSplitView`)
Navigation/routing: Default destination after login. Reached via sidebar "Dashboard" item or `⌘0`. Router destination `.dashboard`. From this view: tile CTAs navigate via `router.navigate(to:)` to Inventory (`⌘1`), Fixed Bills (`⌘3`), Plaid (`⌘4`), Contributions (`⌘6`).
Window title: `.navigationTitle("Dashboard")`
Toolbar implementation:
- `ToolbarItem(placement: .navigation)` — sidebar toggle (`sidebar.left` SF Symbol)
- `ToolbarItem(placement: .primaryAction)` — `+` button opens OCR Upload sheet; `⌘N`
- `ToolbarItem(placement: .primaryAction)` — refresh button (`arrow.clockwise`); `⌘R`

Data fetching:
- Query key: `"dashboard.summary"` — `GET /analytics/spending-summary` + `GET /inventory?filter=low` + `GET /receipts?status=unreviewed` + `GET /obligations?month=<current>` + `GET /plaid/items` + `GET /contributions?month=<current>` — all in parallel via `async let`
- Hook: `@StateObject var dashboard = DashboardState()` (local to this view — not a global singleton)
- Loading: Six `SkeletonView` cards (2 per row × 3 rows)
- Error: Each tile shows its own inline error + retry (tiles load independently via separate state branches)
- Refetch on appear: Yes — triggered via `BackgroundFetchScheduler` pattern
- Refetch on foreground: Yes — `BackgroundFetchScheduler.onForeground()` refreshes all tile data

Mutations:
- None directly from Dashboard tiles. CTAs navigate to other views.

Local state:
- `@State private var drillPanelTarget: DashboardDrillTarget? = nil` — drives the trailing detail column; nil = no drill panel

Keyboard handlers:
- `⌘R` — triggers data refresh
- `⌘N` — opens OCR Upload panel

Drag-and-drop handlers:
- `.onDrop(of: [.jpeg, .png, .heic, .pdf], isTargeted: $dropTargetActive)` on the main content area — opens OCR Upload sheet with dropped file

Context menu: None (tiles are not individually right-clickable for actions)

Selection state: None (tiles are navigation targets, not selectable items)

Component tree (ASCII):
```
DashboardView
├── DemoModeBanner (if isDemoMode)
├── AttributionNudgeBanner (if unattributed receipts exist)
├── ScrollView
│   └── LazyVGrid(columns: [adaptive(min: 280)])
│       ├── Card [Low Stock Tile]
│       │   ├── Badge (count)
│       │   ├── Text (top 3 item names)
│       │   └── Button("View Inventory") → ⌘1
│       ├── Card [Spending Tile]
│       │   ├── Text(totalSpent) [.mono-body]
│       │   ├── ProgressBarView (per domain)
│       │   └── Button("View Analytics")
│       ├── Card [Review Queue Tile]
│       │   ├── Badge (unreviewed count)
│       │   └── Button("Review Now")
│       ├── Card [Fixed Bills Tile]
│       │   ├── Text("X paid of Y")
│       │   ├── List (unpaid names preview, max 3)
│       │   └── Button("View Bills") → ⌘3
│       ├── Card [Plaid Sync Tile]
│       │   ├── Text (last sync time)
│       │   ├── Badge (staged count)
│       │   └── Button("Review") / Warning if loginRequired
│       └── Card [Contributions Tile]
│           ├── List (top-3 leaderboard rows)
│           └── Button("View All") → ⌘6
└── overlay: dropTargetHighlight (when file dragged over)
```

Business rules encoded:
- §1.7 rule 9: Attribution nudge banner shown when unattributed receipts exist
- §1.7 rule 8: Low-stock count in tile matches `InventoryState.lowStockItems.count`
- §1.7 rule 10: `DemoModeBanner` visible at top

Tests required:
  1. Six `SkeletonView` cards shown during loading
  2. Attribution nudge banner appears when `unattributedCount > 0`
  3. Tile CTA buttons navigate to correct screens
  4. Dropped receipt file opens OCR Upload sheet
  5. `⌘R` triggers data refresh for all tiles

---

**View: OCRUploadView**
File: `LocalOCR/Views/Receipts/OCRUploadView.swift`
Window: Main Window (sheet) OR standalone OCR Upload window (§4.7 Window 4)
Navigation/routing: Entry via `⌃⌘R`, `⌘N`, Finder drop, Dock drop, menu bar Quick Action. On OCR success: transitions to `ReceiptReviewView` (same sheet or new window). On Cancel/`Esc`: sheet dismissed, pending upload URL cleared from `AppState`.
Window title: "New Receipt Upload" (`.navigationTitle`)
Toolbar implementation:
- `ToolbarItem(placement: .cancellationAction)` — "Cancel" button; `Esc`
- `ToolbarItem(placement: .confirmationAction)` — "Run OCR" `PrimaryButton`; `⌘Return`; disabled until file is selected

Data fetching:
- Query key: `"ai.models"` — `GET /ai-models` to populate `ModelPicker`
- Hook: `@StateObject var models = AIModelsState.shared`
- Loading: `ModelPicker` shows "Loading models…" while fetching
- Error: Toast if models fetch fails; "Run OCR" button disabled
- Refetch on appear: No (models rarely change during a session)

Mutations:
- `submitOCR(file:type:modelId:)` — trigger: "Run OCR" button. No optimistic update. Server POSTs multipart to `POST /receipts/upload`. On success: navigate to `ReceiptReviewView` with returned receipt data. On error: Toast with error message + "Try Different Model" shortcut button visible.

Local state:
- `@State private var selectedFileURL: URL? = nil`
- `@State private var receiptType: ReceiptType = .auto`
- `@State private var selectedModelId: Int64? = nil`
- `@State private var isProcessing = false`
- `@State private var ocrError: String? = nil`
- `@State private var continuityAvailable = false` — set on appear from `ContinuityCameraHelper.isAvailable`

Keyboard handlers:
- `⌘Return` — fires `submitOCR` if file selected
- `Esc` — cancels and dismisses

Drag-and-drop handlers:
- `DropZone` component handles `.onDrop(of: [.jpeg, .png, .heic, .pdf])` — sets `selectedFileURL`
- `FileDropHandler.validate` ensures UTType conformance before accepting

Context menu: None
Selection state: None (single-file selection)

Component tree (ASCII):
```
OCRUploadView
└── VStack(spacing: 20, max width: 440pt)
    ├── DropZone(onFilesDropped:, isProcessing:, onBrowse:)
    ├── [if continuityAvailable]
    │   └── Button("Take Photo with iPhone") [.secondary]
    ├── Picker (Receipt Type: Auto/Grocery/Restaurant/Expense) [.segmented]
    ├── ModelPicker($selectedModelId, models:)
    ├── [if !isProcessing]
    │   └── PrimaryButton("Run OCR") ← ⌘Return; disabled if !fileSelected
    └── [if isProcessing]
        ├── ProgressView()
        └── Text("Processing with [model]…") + Button("Cancel")
```

Business rules encoded:
- §1.7 rule 3: Model picker enforces OCR model selection; default from user's active model
- §1.7 rule 4: Receipt type selection (auto/grocery/restaurant/expense) is sent as `domain` to the server; classifies `kind` per server logic

Tests required:
  1. "Run OCR" button disabled until file is selected
  2. `isProcessing = true` shows `ProgressView` and hides "Run OCR" button
  3. OCR error shows Toast with "Try Different Model" button
  4. Continuity Camera button hidden when `continuityAvailable = false`
  5. `ReceiptType.auto` is default selection

---

**View: ReceiptReviewView**
File: `LocalOCR/Views/Receipts/ReceiptReviewView.swift`
Window: Main Window (replaces OCR Upload content) OR Receipt Inspector window
Navigation/routing: Reached from `OCRUploadView` post-OCR or from `ReceiptListView` selection. Navigates away on "Confirm Receipt" (success → Dashboard or previous screen) or "Cancel" (returns to upload or list). Re-run OCR diff triggered inline (no navigation).
Window title: `.navigationTitle(storeName.isEmpty ? "Review Receipt" : storeName)`
Toolbar implementation:
- `ToolbarItem(placement: .cancellationAction)` — "Cancel" `SecondaryButton`
- `ToolbarItem(placement: .primaryAction)` — "Confirm Receipt" `PrimaryButton`; `⌘Return`
- `ToolbarItem(placement: .primaryAction)` — "Re-run OCR" `SecondaryButton`; `⌥⌘R`

Data fetching:
- Query key: `"receipt.\(id)"` — `GET /receipts/<id>` if opened from existing receipt
- Hook: `@StateObject var state = ReceiptReviewState(receipt: receipt)`
- Loading: Right-panel photo skeleton + 3–5 skeleton line-item rows
- Error: Error toast; "Retry" link to re-fetch receipt data
- Refetch on appear: No for new OCR (data comes from upload response); Yes for existing receipt (re-fetch on re-appear after re-run OCR)

Mutations:
- `saveEdits()` — trigger: any field edit blur or `Tab` to next field. Optimistic: field value updates locally. `PATCH /receipts/<id>` with changed fields. On error: field reverts to server value + toast.
- `confirmReceipt()` — trigger: "Confirm Receipt" button. No optimistic update (confirmation has inventory side effects). `POST /receipts/<id>/confirm`. On success: attribution picker sheet presented (§1.7 rule 9), then navigate away. On error: toast.
- `rerunOCR(modelId:)` — trigger: "Re-run OCR" button → model picker popover → "Re-run with [model]" button. Calls `POST /receipts/<id>/rerun-ocr`. Transitions list to diff mode.
- `acceptDiffItem(itemId:)` / `discardDiffItem(itemId:)` — trigger: per-item Accept/Discard in diff mode.

Local state:
- `@State private var isDiffMode = false`
- `@State private var diffItems: [ReceiptItemDiff] = []` — server diff result
- `@State private var editingItemId: Int64? = nil` — which line item is in inline edit
- `@FocusState private var focusedItemField: ItemField?`
- `@State private var isShowingAttributionPicker = false`
- `@State private var photoScale: CGFloat = 1.0` — pinch-to-zoom

Keyboard handlers:
- `Tab` / `⇧Tab` — cycle through editable fields in Review form
- `⌘Return` — confirms receipt
- `⌥⌘R` — opens Re-run OCR model picker popover
- `⌥⌘T` — calls rotate endpoint

Drag-and-drop handlers: None within this view
Context menu: `.receiptLineItemContextMenu` (see §3.5 "Receipt line item")
Selection state: Single line item selection (for inline edit expansion)

Component tree (ASCII):
```
ReceiptReviewView
├── HSplitView (~55% / ~45%)
│   ├── VStack [left panel]
│   │   ├── KeyValueRow (Store, editable via InlineEditableCell)
│   │   ├── KeyValueRow (Date, DatePicker on click)
│   │   ├── KeyValueRow (Total, TextField)
│   │   ├── Picker (Type: segmented)
│   │   └── List [line items]
│   │       └── ForEach(lineItems) { item in
│   │           LineItemRow(item:, isEditing:, isDiffMode:)
│   │               ├── TextField (qty)
│   │               ├── TextField (name)
│   │               ├── TextField (price)
│   │               ├── Picker (kind)
│   │               └── [diff mode] Accept/Discard buttons
│   │       }
│   │       └── Button("+") → add new item
│   └── VStack [right panel]
│       ├── ReceiptThumbnail (full width, pinch-to-zoom)
│       ├── Button("Rotate") [⌥⌘T]
│       └── Zoom controls (⌘+/⌘-)
└── sheet(isPresented: $isShowingAttributionPicker) {
    AttributionPicker(...)
}
```

Business rules encoded:
- §1.7 rule 3: Model picker in re-run sheet; diff view preserves non-auto-deleted behavior
- §1.7 rule 4: Line items with `kind != .product` shown in secondary color (analytics-only items)
- §1.7 rule 9: Attribution picker presented after every confirm without attribution
- §2.6 AC-14: Photo displayed as-is from server (server-rotated); no client-side rotation
- §2.6 AC-15: Diff view uses green (new), amber (changed), neutral (unchanged), strikethrough (removed)

Tests required:
  1. Diff mode: new items show green left-border + "NEW" badge
  2. `confirmReceipt()` presents `AttributionPicker` sheet on success
  3. Inline field edit blurs trigger PATCH to server
  4. `⌥⌘R` opens model picker popover
  5. `kind != .product` rows rendered in secondary label color

---

**View: InventoryView**
File: `LocalOCR/Views/Inventory/InventoryView.swift`
Window: Main Window
Navigation/routing: Sidebar item "Inventory"; `⌘1`. From here: product detail inspector panel opens in trailing column. "Add to Shopping List" navigates to `ShoppingListView` optionally.
Window title: `.navigationTitle("Inventory")`
Toolbar implementation:
- `ToolbarItem(placement: .navigation)` — sidebar toggle
- `ToolbarItem(placement: .primaryAction)` — `⌥⌘I` opens Add Item sheet
- `ToolbarItem(placement: .primaryAction)` — `⌘F` focuses search field
- `ToolbarItem(placement: .primaryAction)` — Filter menu (`line.3.horizontal.decrease.circle`) with Low/Out/Manual filter toggles

Data fetching:
- Query key: `"inventory.all"` — `GET /inventory`
- Hook: `@StateObject var inventory = InventoryState.shared`
- Loading: 8 skeleton list rows; category sidebar counts show "—"
- Error: Full-width error banner with "Retry" link
- Refetch on appear: Yes (once per 60s via `BackgroundFetchScheduler`)
- Refetch on foreground: Yes

Mutations:
- `adjustQuantity(id:delta:)` — trigger: `−`/`+` micro-buttons or `⌥↑`/`⌥↓`. Optimistic: quantity updates immediately in list. `PATCH /inventory/<id>` with delta. UndoManager registration.
- `markLow(id:)` / `clearLow(id:)` — trigger: context menu. `PATCH /inventory/<id>` with `manual_low`.
- `addToShoppingList(id:)` — trigger: `+` row button or `⌘L`. `POST /shopping/items` with product_id.
- `deleteItem(id:)` — trigger: `Delete` key or context menu "Remove". Confirmation sheet required. `DELETE /inventory/<id>`.

Local state:
- `@State private var selectedCategory: String? = nil` — nil = "All"
- `@State private var activeFilters: Set<InventoryFilter> = []` — .low, .out, .manualLow
- `@State private var searchQuery = ""`
- `@State private var selectedItemId: Int64? = nil` — drives trailing detail panel
- `@State private var sortOrder: InventorySortOrder = .category`

Keyboard handlers:
- `⌥↑` / `⌥↓` — adjust selected item quantity +1 / -1
- `⌘L` — add selected item to shopping list
- `⌘E` — open edit sheet for selected item
- `Delete` — prompt to remove selected item
- `↑` / `↓` — move list selection

Drag-and-drop handlers:
- Inventory item rows support `.onDrag` returning `NSItemProvider` with `com.localocr.inventory-item` UTType (for drop onto Shopping List in multi-window mode — §3.9)

Context menu: `.inventoryRowContextMenu` per §3.5
Selection state: Single select for inspector; `⌘A` selects all for bulk "Add to List"

Component tree (ASCII):
```
InventoryView
├── NavigationSplitView
│   ├── [sidebar column ~120pt] List [category sidebar]
│   │   ├── Row("All", count badge)
│   │   └── ForEach(categories) { cat in
│   │       Row(cat, inStockCount badge)
│   │   }
│   │   └── FilterChips (Low/Out/ManualLow toggles)
│   ├── [content column] List [product list]
│   │   └── ForEach(filteredItems) { item in
│   │       InventoryRow(item:)
│   │           ├── ReceiptThumbnail (36×36)
│   │           ├── VStack (name, brand/size)
│   │           ├── CategoryChip
│   │           ├── QuantityStepper (−, count, +)
│   │           ├── LowStockPill
│   │           └── Button("+") [add to list, hover-only]
│   │   }
│   └── [detail column ~280pt, if selectedItemId != nil]
│       └── ProductDetailSheet(item:)
│           ├── InlineEditableCell (name)
│           ├── Picker (category)
│           ├── Picker (location)
│           ├── TextField (quantity)
│           ├── TextField (threshold)
│           ├── DatePicker (expiry, optional)
│           └── Chart [price history, LineMark]
└── .searchable(text: $searchQuery)
```

Business rules encoded:
- §1.7 rule 4: Items with `isNonProduct = true` are filtered out of this list
- §1.7 rule 7: Quantity adjustments create `contribution_events` server-side; client reads them via Contributions screen

Tests required:
  1. "Low" filter chip filters list to items where `manualLow = true` OR `quantity <= threshold`
  2. `⌥↑` increments quantity optimistically; PATCH fires
  3. `⌘L` on selected item calls POST to shopping list
  4. Empty state renders when no items in selected category
  5. `isNonProduct = true` items absent from list

---

**View: ShoppingListView**
File: `LocalOCR/Views/Shopping/ShoppingListView.swift`
Window: Main Window
Navigation/routing: Sidebar "Shopping"; `⌘2`. Sub-navigation via tab bar: "List" tab | "Recommendations" tab | "Kitchen" tab (merged per §2.2).
Window title: `.navigationTitle("Shopping")`
Toolbar implementation:
- `ToolbarItem(placement: .primaryAction)` — `⌘N` adds new item inline
- `ToolbarItem(placement: .primaryAction)` — `⌥⌘P` auto-populates from low-stock
- `ToolbarItem(placement: .primaryAction)` — `⌘⇧S` opens QR share popover

Data fetching:
- Query key: `"shopping.list"` + `"shopping.session"` — `GET /shopping/items` + `GET /shopping/session`
- Recommendations: `"recommendations.list"` — `GET /recommendations`
- Kitchen: `"kitchen.view"` — `GET /kitchen`
- Hook: `@StateObject var shopping = ShoppingState.shared`
- Loading: 6 skeleton rows per tab
- Error: Toast on load failure
- Refetch on appear: Yes

Mutations:
- `addItem(name:)` — trigger: `⌘N` inline row or "Add" in menu. Optimistic: row appears at top. `POST /shopping/items`. UndoManager registration.
- `togglePurchased(id:)` — trigger: checkbox tap or `Space`. Optimistic: row moves to purchased group. `PATCH /shopping/items/<id>` with `status`. UndoManager registration.
- `removeItem(id:)` — trigger: `Delete` or context menu. `DELETE /shopping/items/<id>`. Undo via UndoManager.
- `populateFromLowStock()` — trigger: `⌥⌘P`. No optimistic update. `POST /shopping/auto-populate`. On success: list refreshes.
- `addRecommendationToList(id:)` — trigger: "Add to List" in Recommendations tab. `POST /shopping/items` with product_id from recommendation.
- `dismissRecommendation(id:)` — trigger: `×` dismiss icon. `PATCH /recommendations/<id>` with dismissed flag.

Local state:
- `@State private var selectedTab: ShoppingTab = .list` — .list, .recommendations, .kitchen
- `@State private var isShowingQR = false`
- `@State private var newItemName = ""`
- `@State private var isAddingItem = false`
- `@State private var sortOrder: ShoppingSortOrder = .default`

Keyboard handlers:
- `⌘N` — inserts new inline item row
- `Space` — toggles selected item checked/unchecked
- `⌥⌘P` — triggers auto-populate
- `Delete` — removes selected item

Drag-and-drop handlers:
- `.onDrop(of: [UTType("com.localocr.inventory-item")])` — accepts inventory item dragged from `InventoryView` in multi-window mode; calls `addItem` with product ID
- `.onMove` — list rows reorderable via drag; PATCH `/shopping/items/<id>` with new position

Context menu: `.shoppingItemContextMenu` per §3.5
Selection state: None (no row selection — checkboxes are primary interaction)

Component tree (ASCII):
```
ShoppingListView
├── Picker [tab selector: List / Recommendations / Kitchen] [.segmented]
├── [Tab: List]
│   ├── SessionInfoBar (session name, estimated total, status badge)
│   ├── SortChips (Default/Alphabetical/Store/Source)
│   ├── List
│   │   ├── ForEach(uncheckedItems) { item in
│   │   │   ShoppingItemRow(item:)
│   │   │       ├── Toggle (checkbox)
│   │   │       ├── Text (name) [strikethrough if purchased]
│   │   │       ├── Badge (source: Low/Rec/Manual)
│   │   │       ├── TextField (qty, 2-char)
│   │   │       └── ChipIcons (store, note)
│   │   └── DisclosureGroup("Purchased (\(count))")
│   │       └── ForEach(purchasedItems) { ... }
│   └── [if isAddingItem] InlineNewItemRow
├── [Tab: Recommendations]
│   ├── Header (last generated + Refresh button)
│   └── List
│       └── ForEach(recommendations) { rec in
│           RecommendationRow(rec:)
│               ├── LowStockPill (urgency)
│               ├── Text (name) [.headline]
│               ├── Text (confidence %) [.subheadline.secondary]
│               ├── Text (stock info) [.caption.secondary]
│               ├── PrimaryButton("Add to List") [compact]
│               └── Button("×") [hover-only]
│       }
├── [Tab: Kitchen]
│   └── KitchenView (reused component)
└── popover(isPresented: $isShowingQR) {
    QRCodeView(endpoint: .shoppingShare(...))
}
```

Business rules encoded:
- §1.7 rule 8: "Populate from Low Stock" derives from `InventoryState.lowStockItems`; recommendations sourced from `/recommendations`
- §1.7 rule 7: `addItem` fires `shopping_item_added` contribution event server-side; `togglePurchased` fires `shopping_item_purchased`

Tests required:
  1. `Space` on unchecked item moves it to "Purchased" group
  2. `⌥⌘P` calls `/shopping/auto-populate` and refreshes list
  3. QR popover opens on `⌘⇧S`
  4. Recommendation "Add to List" button fades to "Added ✓" post-tap
  5. Drag from `InventoryView` calls `addItem` with correct product ID

---

**View: KitchenView**
File: `LocalOCR/Views/Inventory/KitchenView.swift`
Window: Main Window (rendered as "Kitchen" sub-tab in `ShoppingListView`)
Navigation/routing: Accessed via "Kitchen" tab in `ShoppingListView`
Window title: Sub-tab title "Kitchen" (tab label)
Toolbar implementation: Refresh button in tab area; no separate toolbar

Data fetching:
- Query key: `"kitchen.view"` — `GET /kitchen`
- Hook: `@StateObject var kitchen = KitchenState()` (shared with `ShoppingState`)
- Loading: 6 skeleton cards (2×3)
- Error: Error toast

Mutations:
- `addToShoppingList(productId:)` — trigger: "Add to Shopping List" card button or item row button. `POST /shopping/items`.

Local state:
- `@State private var showLowStockOnly = false`
- `@State private var selectedCategories: Set<String> = []`

Keyboard handlers: None specific to Kitchen View
Drag-and-drop handlers: None
Context menu: `.kitchenItemContextMenu` per §3.5
Selection state: None

Component tree (ASCII):
```
KitchenView
├── FilterBar
│   ├── Toggle("Low Stock Only")
│   └── CategoryChips (multi-select)
└── ScrollView
    └── LazyVGrid(columns: [adaptive(min: 240)])
        └── ForEach(filteredCategories) { cat in
            Card [Category card]
                ├── HStack [header]
                │   ├── Text(cat.name) [.title3.semibold]
                │   ├── CategoryIcon
                │   └── Badge(inStockCount)
                ├── VStack [ingredient rows]
                │   └── ForEach(cat.items) { item in
                │       HStack
                │           ├── Text(item.name) [.body]
                │           └── LowStockPill / Text(qty) in success color
                │   }
                └── Button("Add to Shopping List") [.plain; small]
        }
```

Business rules encoded:
- §1.7 rule 4: `isNonProduct` items excluded from kitchen view (server filters these)

Tests required:
  1. "Low Stock Only" filter hides categories with no low-stock items
  2. Card collapses via `DisclosureGroup` on category header tap
  3. "Add to Shopping List" calls POST with correct product_id
  4. Grid is 2-column on standard width (≥640pt), 1-column on narrow
  5. Category icons use SF Symbols

---

**View: FixedBillsView**
File: `LocalOCR/Views/Finance/FixedBillsView.swift`
Window: Main Window
Navigation/routing: Sidebar "Fixed Bills"; `⌘3`
Window title: `.navigationTitle("Fixed Bills")`
Toolbar implementation:
- `ToolbarItem(placement: .primaryAction)` — `⌘N` opens Add Obligation sheet
- Month navigation: `ToolbarItem` with `<` / `>` buttons + current month label

Data fetching:
- Query key: `"bills.list.\(currentMonth)"` — `GET /obligations?month=<YYYY-MM>` + `GET /obligations/projection`
- Hook: `@StateObject var finance = FinanceState.shared`
- Loading: 4 skeleton rows
- Error: Error toast

Mutations:
- `togglePaid(id:)` — trigger: `Space` on selected row or "Mark Paid" swipe. Optimistic: row background changes. `PATCH /obligations/<id>` with payment status. UndoManager registration.
- `renameObligation(id:newName:)` — trigger: F2 / double-click on label. Inline edit via `InlineEditableCell`. `PATCH /obligations/<id>` with new label. UndoManager registration.
- `addObligation(form:)` — trigger: "Add Obligation" sheet "Add" button. `POST /obligations`.
- `deleteObligation(id:)` — trigger: context menu "Delete". Confirmation sheet. `DELETE /obligations/<id>`.
- `linkPlaid(obligationId:transactionId:)` — trigger: "Link Transaction" button. `PATCH /obligations/<id>` with plaid_transaction_id.

Local state:
- `@State private var currentMonth: Date = .now.startOfMonth`
- `@State private var selectedBillId: Int64? = nil`
- `@State private var isAddingObligation = false`

Keyboard handlers:
- `Space` — toggles paid/unpaid for selected row
- `F2` — enters inline rename for selected obligation label
- `Return` — confirms inline rename
- `Esc` — cancels inline rename
- `⌘N` — opens Add Obligation sheet

Drag-and-drop handlers: None
Context menu: `.fixedBillContextMenu` per §3.5
Selection state: Single select (for payment history panel)

Component tree (ASCII):
```
FixedBillsView
├── MonthSummaryBar
│   └── ProgressBarView (paid vs expected)
├── List
│   ├── Section("Due This Month")
│   │   └── ForEach(dueThisMonth) { bill in
│   │       BillRow(bill:)
│   │           ├── InlineEditableCell (label, F2 to edit)
│   │           ├── CategoryChip (billing cycle)
│   │           ├── Text(expected) [.mono-body]
│   │           ├── Text(paid) [.mono-body, colored]
│   │           ├── LowStockPill variant (Paid/Due/Overdue)
│   │           └── Image("link.circle") [Plaid status]
│   │   }
│   └── DisclosureGroup("Not Due This Month")
│       └── ForEach(notDueThisMonth) { ... }
├── [if selectedBillId != nil] PaymentHistoryPanel [trailing column]
└── sheet(isPresented: $isAddingObligation) {
    AddObligationForm(...)
}
```

Business rules encoded:
- §1.7 rule 5: Bills shown in "Due This Month" vs "Not Due This Month" sections via server's `month_matches_billing_cycle()` logic — client renders based on server-returned `isDueThisMonth` flag
- §2.6 AC-17: "Not due this month" section is collapsed by default; due bills surfaced prominently

Tests required:
  1. `Space` on focused row optimistically changes background to `paid-bill` token
  2. F2 enters inline rename mode; `Esc` reverts to original name
  3. Quarterly bill shows "Due" in billing months and collapses to "Not Due" in non-billing months
  4. "Add Obligation" sheet submits to `POST /obligations`
  5. Row background tokens: `paid-bill` (green), `unpaid-bill` (amber), `overdue-bill` (red)

---

**View: PlaidAccountsView**
File: `LocalOCR/Views/Finance/PlaidAccountsView.swift`
Window: Main Window
Navigation/routing: Sidebar "Plaid Accounts"; `⌘4`. Admin-gated for linking; shared for viewing.
Window title: `.navigationTitle("Bank Accounts")`
Toolbar implementation:
- `ToolbarItem(placement: .primaryAction)` — Sync button (`arrow.triangle.2.circlepath`); triggers sync
- `ToolbarItem(placement: .primaryAction)` — "Add Account" button (admin only, `plus.circle`); opens Plaid Link

Data fetching:
- Query key: `"plaid.items"` + `"plaid.staged"` — `GET /plaid/items` + `GET /plaid/staged-transactions?status=ready_to_import`
- Hook: `@StateObject var finance = FinanceState.shared`
- Loading: Skeleton for accounts section + skeleton for staged transactions
- Error: Per-account error badge; toast for staged transactions failure

Mutations:
- `syncAccount(itemId:)` — trigger: "Sync Now" per-account button. `POST /plaid/sync`.
- `confirmTransaction(id:)` — trigger: "Confirm" button or `Return` on focused row. `POST /plaid/staged-transactions/<id>/confirm`.
- `dismissTransaction(id:)` — trigger: "Dismiss" button or `Delete` key. `POST /plaid/staged-transactions/<id>/dismiss`. Confirmation required for bulk dismiss.
- `startPlaidLink()` — trigger: "Add Account" button (admin only). Fetches Plaid link token → opens `ASWebAuthenticationSession`. On callback: `POST /plaid/exchange` with public_token.
- `reauthorize(itemId:)` — trigger: "Re-authorize" on login_required account. Fetches new link token for update mode → opens `ASWebAuthenticationSession`.

Local state:
- `@State private var isLinkSessionActive = false`

Keyboard handlers:
- `Return` — confirms selected staged transaction
- `Delete` — dismisses selected staged transaction (with confirmation)
- `↑` / `↓` — navigates staged transactions list

Drag-and-drop handlers: None
Context menu: `.plaidTransactionContextMenu` per §3.5
Selection state: Single select in staged transactions list

Component tree (ASCII):
```
PlaidAccountsView
├── Section A — Linked Accounts
│   └── List [plaidItems]
│       └── ForEach(items) { item in
│           PlaidAccountRow(item:)
│               ├── Text(institutionName + nickname) [.headline]
│               ├── Text(accountMask) [.subheadline.secondary]
│               ├── CategoryChip (accountType)
│               ├── Text(balance) [.mono-body]
│               ├── Badge (status: Active/Login Required/Disconnected)
│               ├── Text(lastSyncAt) [.caption.secondary]
│               └── Button("Sync Now") [compact]
│       }
│   └── [admin only] Button("Add Bank Account")
├── Section B — Staged Transactions
│   ├── SectionHeader("Staged Transactions (\(count))")
│   └── List [stagedTransactions]
│       └── ForEach(transactions) { tx in
│           StagedTransactionRow(tx:)
│               ├── Text(merchantName) [.headline]
│               ├── Text(date) [.subheadline.secondary]
│               ├── Text(amount) [.mono-body]
│               ├── CategoryChip (suggestedType)
│               ├── Text(matchInfo) [success/muted color]
│               ├── PrimaryButton("Confirm") [compact] ← Return
│               └── SecondaryButton("Dismiss")
│       }
└── [ASWebAuthenticationSession active] loading overlay
```

Business rules encoded:
- §1.7 rule 6: Match indicators in staged transactions reflect server fuzzy-match logic (`AMOUNT_EPSILON`, `DATE_WINDOW_DAYS`); client displays result, does not compute
- §1.7 rule 2: "Add Account" button gated by `auth.currentUser.role == .admin`
- §2.6 AC-18: `ASWebAuthenticationSession` handles Plaid Link; no Plaid token stored client-side

Tests required:
  1. Non-admin user sees no "Add Account" button
  2. `Return` on selected staged transaction calls confirm endpoint
  3. `login_required` status badge shows amber "Login Required ⚠" with tappable re-auth action
  4. Sync button triggers `POST /plaid/sync` for correct item ID
  5. Plaid Link callback `localocr://plaid-callback` is intercepted and exchange endpoint called

---

**View: CashTransactionsView**
File: `LocalOCR/Views/Finance/CashTransactionsView.swift`
Window: Main Window
Navigation/routing: Sidebar "Cash Transactions"; `⌘5`
Window title: `.navigationTitle("Cash Transactions")`
Toolbar implementation:
- Month navigation: `ToolbarItem` with `<` / `>` arrows + month label
- `ToolbarItem(placement: .primaryAction)` — Export CSV button (`square.and.arrow.up`)

Data fetching:
- Query key: `"cash.transactions.\(month)"` — `GET /cash-transactions?month=<YYYY-MM>`
- Hook: `@StateObject var finance = FinanceState.shared`
- Loading: 4 skeleton rows in history list
- Error: Inline error below form on submit failure; toast on load failure

Mutations:
- `logTransaction(amount:description:category:date:)` — trigger: "Log Cash Spend" button or `⌘Return`. `POST /cash-transactions`. On success: history list refreshes. UndoManager registration.
- `deleteTransaction(id:)` — trigger: swipe-to-delete or context menu. `DELETE /cash-transactions/<id>`. UndoManager registration.
- `editTransaction(id:form:)` — trigger: row double-click → edit popover. `PATCH /cash-transactions/<id>`.
- `exportCSV()` — trigger: Export button. Calls `GET /analytics/export-csv?month=<YYYY-MM>` → opens `NSSavePanel`.

Local state:
- `@State private var amount = ""`
- `@State private var description = ""`
- `@State private var category: SpendingCategory = .grocery`
- `@State private var transactionDate = Date.now`
- `@State private var currentMonth = Date.now.startOfMonth`
- `@FocusState private var focusedFormField: CashFormField?`

Keyboard handlers:
- `⌘Return` — submits the quick-entry form
- `Tab` — moves between form fields (amount → description → category → date)
- `←` / `→` — steps through months

Drag-and-drop handlers: None
Context menu: "Edit", "Copy Amount", "Delete" (per §3.5)
Selection state: Single row (triggers edit popover)

Component tree (ASCII):
```
CashTransactionsView
├── Card [Quick-entry form, always visible at top]
│   ├── Row 1: TextField(amount, $) + TextField(description)
│   ├── Row 2: Picker(category) + DatePicker(date, .compact)
│   └── Row 3: PrimaryButton("Log Cash Spend") ← ⌘Return
└── List [history, grouped by month]
    └── ForEach(groupedByMonth) { month, transactions in
        Section(header: Text(month + total) [.title3.mono])
        ForEach(transactions) { tx in
            HStack
                ├── Text(tx.description) [.headline]
                ├── CategoryChip
                ├── Text(tx.date) [.subheadline.secondary]
                └── Text(tx.amount) [.mono-body; negative = error color]
        }
    }
```

Business rules encoded:
- §1.7 rule 9: Cash transactions have no attribution; they are excluded from "Spending by Person" totals

Tests required:
  1. Amount field validates as numeric; red border on non-numeric input
  2. `⌘Return` submits form and clears all fields on success
  3. Month stepper updates history list
  4. Export CSV button opens `NSSavePanel` with correct suggested filename
  5. Swipe-to-delete triggers `DELETE /cash-transactions/<id>` with undo registration

---

**View: SpendingByCategoryView** (v1.0 dashboard drill-down subset)
File: `LocalOCR/Views/Analytics/SpendingByCategoryView.swift`
Window: Main Window (trailing detail column of `NavigationSplitView` when accessed from Dashboard tile)
Navigation/routing: Dashboard "Spending" tile → trailing detail column. Also accessible from Analytics section in sidebar (full-screen for v1.1; in v1.0 drill-down panel only).
Window title: None (detail column inherits dashboard title)
Toolbar implementation:
- Month navigation: `<` / `>` arrows + month label
- `ToolbarItem(placement: .primaryAction)` — "Export CSV" button; `⌘S`

Data fetching:
- Query key: `"analytics.spending.\(month)"` — `GET /analytics/spending-by-category?month=<YYYY-MM>`
- Hook: `@StateObject var analytics = AnalyticsState()` (local to this view)
- Loading: 5 skeleton rows with bar placeholders
- Error: Error banner "Failed to load analytics. [Retry]"

Mutations:
- `exportCSV(month:)` — opens `NSSavePanel`; calls `GET /analytics/export-csv?month=<YYYY-MM>`

Local state:
- `@State private var currentMonth = Date.now.startOfMonth`
- `@State private var expandedCategories: Set<String> = []`

Keyboard handlers:
- `←` / `→` — step through months
- `⌘S` — triggers CSV export

Drag-and-drop handlers: None
Context menu: None
Selection state: Category row expansion is the primary interaction (no selection binding)

Component tree (ASCII):
```
SpendingByCategoryView
├── MonthNavigationBar (<, month label, >)
└── List
    ├── ForEach(categories) { cat in
    │   DisclosureGroup(isExpanded: binding(cat.name)) {
    │       [expanded: receipt sub-rows]
    │       ForEach(cat.receipts) { receipt in
    │           HStack(storeName, date, amount) [taps to open Receipt Inspector]
    │       }
    │   } label: {
    │       HStack
    │           ├── Text(cat.name) [.headline]
    │           ├── ProgressBar (proportional to max category)
    │           ├── Text(total) [.mono-body, right-aligned]
    │           └── Text(pct) [.caption, muted]
    │   }
    │ }
    ├── DisclosureGroup("Fixed") → floor obligations
    ├── DisclosureGroup("Cash") → cash transactions
    └── SummaryRow (total across all categories)
```

Business rules encoded:
- §1.7 rule 5: "Fixed" row shows floor obligations with their cadence-filtered amounts
- §1.7 rule 9: Attribution is displayed per receipt but not editable here (edit via `ReceiptReviewView`)

Tests required:
  1. Category row expands to show receipt sub-rows on tap
  2. Month navigation updates all category data
  3. Export CSV calls correct endpoint and opens `NSSavePanel`
  4. "Fixed" row shows bills matching the current billing month
  5. Empty state shows "No spending data for [month]" when no data

---

**View: SettingsView**
File: `LocalOCR/Views/Settings/SettingsView.swift`
Window: Settings window (SwiftUI `Settings` scene, ⌘,)
Navigation/routing: `LocalOCR menu → Preferences` or `⌘,`. Not part of the main `NavigationSplitView`. Opened by the `Settings` scene automatically.
Window title: "LocalOCR Settings" (managed by `Settings` scene)
Toolbar implementation: `TabView` renders as macOS-native tab selector at top of window (icons + labels)

Data fetching: Per-tab on first selection (lazy; no global settings load on open)
Mutations: Each pane handles its own saves (immediate on change, no Apply button)

Local state:
- `@State private var selectedTab: SettingsTab = .general`

Keyboard handlers:
- `⌘W` — closes Settings window
- `⌘,` — re-focuses if already open

Drag-and-drop handlers: None
Context menu: None
Selection state: Tab selection only

Component tree (ASCII):
```
SettingsView (TabView, .tabViewStyle(.automatic))
├── Tab: GeneralPane (gearshape)
├── Tab: AccountPane (person.circle)
├── Tab: AIModelsPane (cpu)
├── Tab: TrustedDevicesPane (lock.fill)
├── Tab: TelegramPane (paperplane.fill)
├── Tab: NotificationsPane (bell.fill)
├── Tab: BackupPane (externaldrive.fill)
└── Tab: AdvancedPane (wrench.and.screwdriver)
```

Business rules encoded:
- §1.7 rule 2: Admin-only controls within each pane are disabled with "Admin access required" tooltip for non-admin users

Tests required:
  1. All 8 tabs render without crashing
  2. `⌘,` opens or focuses the Settings window
  3. Non-admin user sees disabled state on admin-only controls
  4. Settings window is non-resizable (fixed width)
  5. Tab selection persists within the session (not across launches)

---

**View: AuthAndMembersView**
File: `LocalOCR/Views/Auth/AuthAndMembersView.swift` (accessible from main nav or Settings → Account pane)
Window: Main Window (content area) or as sub-view in AccountPane
Navigation/routing: Accessed via Settings → Account → "Manage Members" link. May also be a sidebar item at the admin's discretion.
Window title: `.navigationTitle("Members")`
Toolbar implementation:
- `ToolbarItem(placement: .primaryAction)` — "Invite Member" button (`person.badge.plus`); admin only

Data fetching:
- Query key: `"auth.members"` — `GET /auth/household-members` (auth users) + `GET /household/members` (non-auth household members)
- Hook: `@StateObject var household = HouseholdState.shared`
- Loading: 3 skeleton rows

Mutations:
- `removeMember(userId:)` — trigger: "Remove" button (admin only). Confirmation sheet. `DELETE /auth/users/<id>`.
- `revokeDevice(deviceId:)` — trigger: "Revoke" button. `DELETE /auth/trusted-devices/<id>`.
- `inviteMember(email:)` — trigger: Invite sheet. `POST /auth/invites` → copies invite link to clipboard + opens mail compose.
- `addHouseholdMember(name:ageGroup:)` — trigger: "Add Household Member" button. `POST /household/members`.
- `startDevicePairing()` — trigger: "Pair New Device" button. `POST /auth/device-pairing/start` → display pairing QR + poll status.

Local state:
- `@State private var isShowingInviteSheet = false`
- `@State private var isShowingPairingQR = false`
- `@State private var pairingToken: String? = nil`

Keyboard handlers: None specific
Drag-and-drop handlers: None
Context menu: "Copy Email", "Remove Member" per §3.5
Selection state: None

Component tree (ASCII):
```
AuthAndMembersView
├── Card [current user]
│   ├── HStack (avatar, name, email, role badge)
│   ├── Button("Sign Out") [.destructive]
│   └── Button("QR Login Code") → popover(QRCodeView)
├── List [auth users]
│   └── ForEach(users) { user in
│       MemberRow(user:)
│           ├── HStack (avatar, name, email, role badge)
│           └── [admin, not self] Button("Remove") [.destructive, hover-only]
│   }
│   └── [admin] Button("Invite Member") [.plain]
├── Section [household members — non-auth]
│   └── ForEach(householdMembers)
│   └── Button("Add Household Member")
└── Section [trusted devices]
    └── ForEach(devices) { device in
        HStack (name, scope badge, lastSeen, Button("Revoke"))
    }
    └── Button("Pair New Device") → pairingQR sheet
```

Business rules encoded:
- §1.7 rule 2: "Remove" and "Invite" buttons absent for non-admin users
- §1.7 rule 7: Contribution events are read-only here; leaderboard in ContributionsView

Tests required:
  1. Non-admin sees no "Remove" or "Invite" buttons
  2. "Sign Out" confirmation sheet appears before clearing Keychain
  3. QR Login Code popover loads `QRCodeView` from `/auth/qr-image`
  4. "Pair New Device" initiates pairing flow and shows QR
  5. Device revoke calls `DELETE /auth/trusted-devices/<id>` with confirmation

---

**View: ContributionsView**
File: `LocalOCR/Views/Contributions/ContributionsView.swift`
Window: Main Window
Navigation/routing: Sidebar "Contributions"; `⌘6`
Window title: `.navigationTitle("Contributions")`
Toolbar implementation:
- Month navigation: `<` / `>` arrows + month label

Data fetching:
- Query key: `"contributions.\(month)"` — `GET /contributions?month=<YYYY-MM>`
- Hook: `@StateObject var household = HouseholdState.shared`
- Loading: 3 skeleton rows

Mutations: None (read-only view)

Local state:
- `@State private var currentMonth = Date.now.startOfMonth`
- `@State private var selectedUserId: Int64? = nil` — drives event history disclosure

Keyboard handlers:
- `←` / `→` — step through months
- `↑` / `↓` — navigate leaderboard rows
- `Return` — expand/collapse event history for selected member

Drag-and-drop handlers: None
Context menu: "View event history", "Copy member name"
Selection state: Single member (to show event history below)

Component tree (ASCII):
```
ContributionsView
├── MonthNavigationBar
└── VStack
    ├── SectionHeader("May 2026 Leaderboard")
    └── List [leaderboard]
        └── ForEach(sorted by points) { entry in
            DisclosureGroup(
                isExpanded: isSelected(entry.userId)
            ) {
                [events for this user]
                ForEach(entry.events) { event in
                    HStack
                        ├── Text(event.type) [.headline]
                        ├── Text("+\(event.points)") [.mono-body, success color]
                        ├── Text(event.date) [.caption.secondary]
                        └── Button(relatedItem) [.caption, accent]  // if purchaseId exists
                }
                Text("Points reset on [next month 1].") [.caption.secondary]
            } label: {
                HStack
                    ├── RankBadge (medal SF Symbol or number)
                    ├── Text(avatarEmoji) + Text(name) [.headline]
                    └── Text("\(points) pts") [.mono-body, accent color]
            }
        }
```

Business rules encoded:
- §1.7 rule 7: Points values displayed exactly as computed server-side; client never computes points

Tests required:
  1. Leaderboard sorted by points descending
  2. Top-3 rows show medal SF Symbols (gold/silver/bronze)
  3. Month navigation updates leaderboard
  4. Event history disclosure expands on row selection
  5. Receipt link in event row opens Receipt Inspector on tap

---

**View: MenuBarPopoverView**
File: `LocalOCR/Views/MenuBar/MenuBarPopoverView.swift`
Window: Menu Bar Popover (NSPopover attached to NSStatusItem per §3.2)
Navigation/routing: Menu bar icon click → popover appears. "Open LocalOCR" → brings Main Window to front. "Upload Receipt" → opens `OCRUploadView`. "Open Shopping List" → `router.navigate(to: .shopping)`.
Window title: No title (popover)
Toolbar implementation: None; "×" close button in top-right corner

Data fetching:
- Query key: `"menubar.summary"` — lightweight `GET /inventory?filter=low&count=1` (just count) + last-sync timestamp from `PreferencesStore`
- Hook: `@StateObject var appState = AppState.shared`
- Loading: "Refreshing…" spinner in status section for ~1–2s
- Error: "Cannot reach server" label with "Retry" link

Mutations:
- `logCashTransaction(form:)` — trigger: inline form "Log" button or `⌘Return`. Same `POST /cash-transactions` as `CashTransactionsView`. On success: form collapses, brief "Logged ✓" shown.

Local state:
- `@State private var isQuickAddExpanded = false`
- `@State private var quickAmount = ""`
- `@State private var quickDescription = ""`
- `@State private var quickCategory: SpendingCategory = .grocery`

Keyboard handlers:
- `⌘Return` — submits Quick Add Cash form when expanded
- `Esc` — closes popover

Drag-and-drop handlers:
- Popover accepts dropped receipt files — forwards to `AppState.pendingUploadURLs` + opens OCRUploadView

Context menu: None
Selection state: None

Component tree (ASCII):
```
MenuBarPopoverView (300pt × ~360pt fixed)
├── HStack [header]
│   ├── AppIcon (16pt)
│   ├── Text("LocalOCR") [.headline]
│   └── Button("×") [closes popover]
├── Card [status]
│   ├── Text("🛒 \(lowStockCount) items low") [warning color]
│   └── Text("Synced \(n) min ago") [.caption.secondary]
├── VStack [quick actions]
│   ├── Button("Upload Receipt") [.secondary, full-width]
│   ├── Button("Open Shopping List") [.secondary, full-width]
│   └── Button("Open App") [.secondary, full-width]
├── DisclosureGroup("Quick Add Cash", isExpanded: $isQuickAddExpanded)
│   └── VStack [form]
│       ├── TextField(amount, $)
│       ├── TextField(description)
│       ├── Picker(category, .menuStyle)
│       └── PrimaryButton("Log") ← ⌘Return
└── VStack [footer]
    ├── Text(serverURL) [.caption.secondary, truncated]
    └── Button("Settings") [.plain] → opens Settings window
```

Business rules encoded:
- §1.7 rule 10: If `isDemoMode`, Quick Add Cash form shows "Demo mode — sign in to save" instead of submitting
- §2.3 feature #3: Menu bar status icon low-stock count badge matches `AppState.lowStockCount`

Tests required:
  1. Low-stock count displays correctly from `AppState.lowStockCount`
  2. Quick Add Cash form collapses and shows "Logged ✓" on success
  3. Demo mode prevents form submission
  4. "Open App" brings main window to front without opening second instance
  5. Dropped receipt file triggers OCR Upload flow

---

**View: DemoModeOverlay**
File: `LocalOCR/Views/DemoMode/DemoModeOverlay.swift`
Window: Applies as an overlay on the Main Window content area (not a separate window)
Navigation/routing: Active whenever `AppState.isDemoMode = true`. Exited via "Sign In" CTA → presents `LoginView` as sheet → on successful login `isDemoMode = false`.
Window title: N/A (overlay, not a window)

Data fetching: None
Mutations: None (overlay suppresses mutations — `DemoModeGate` ViewModifier handles this)
Local state: None (state from `@EnvironmentObject var appState: AppState`)

Keyboard handlers:
- `Return` on focused "Sign In" button fires sign-in sheet

Render: `DemoModeBanner` pinned at top of main content area (above all other content). Applied via `.safeAreaInset(edge: .top) { DemoModeBanner(onSignIn: ...) }` on the `MainSplitView` content column.

`DemoModeGate` ViewModifier: wraps every write-action button. When `appState.isDemoMode`:
```swift
struct DemoModeGate: ViewModifier {
    @EnvironmentObject var appState: AppState
    let realAction: () -> Void
    func body(content: Content) -> some View {
        content.simultaneousGesture(TapGesture().onEnded {
            if appState.isDemoMode {
                toastQueue.add(Toast(message: "Demo mode — sign in to save", severity: .warning))
            } else {
                realAction()
            }
        })
    }
}
```

Business rules encoded:
- §1.7 rule 10 (full enforcement): No write API call is ever made from demo mode. `DemoModeGate` is applied to ALL PrimaryButton instances that perform writes. `APIClient` also has a secondary gate: if `isDemoMode` and method is mutating, returns `DemoModeError` immediately.

Tests required:
  1. `DemoModeBanner` is visible in every screen when `isDemoMode = true`
  2. Write-action buttons in `isDemoMode` show toast, do not call API
  3. `APIClient` returns `DemoModeError` for POST/PATCH/DELETE when `isDemoMode`
  4. "Sign In" CTA in banner presents `LoginView` sheet
  5. `isDemoMode` resets to `false` on successful login

---

### 5.3 APIClient + ENDPOINT IMPLEMENTATIONS

All endpoints are typed in `LocalOCR/Networking/Endpoints.swift`. The `APIClient` in `LocalOCR/Networking/APIClient.swift` provides a single generic `request<T: Decodable>(_ endpoint: Endpoint, body: Encodable?, responseType: T.Type) async throws -> T` method that all state files call. Path mappings cross-reference §1.4 blueprint groups.

```swift
// LocalOCR/Networking/Endpoints.swift
enum Endpoint {
    // ─── Authentication (manage_authentication.py) ───
    case me                                          // GET  /auth/me
    case config                                      // GET  /auth/config
    case login                                       // POST /auth/login
    case logout                                      // POST /auth/logout
    case oauthGoogleStart                            // GET  /auth/oauth/google
    case oauthGoogleCallback                         // GET  /auth/oauth/google/callback (server-side redirect; client intercepts via ASWebAuthenticationSession)
    case householdUsers                              // GET  /auth/household-users
    case invites                                     // POST /auth/invites
    case qrImage                                     // GET  /auth/qr-image
    case devicePairingStart                          // POST /auth/device-pairing/start
    case devicePairingStatus(token: String)          // GET  /auth/device-pairing/status/<token>
    case devicePairingClaim(token: String)           // GET  /auth/device-pairing/claim/<token>
    case trustedDevice(id: Int64)                    // DELETE /auth/trusted-devices/<id>
    case trustedDevices                              // GET  /auth/trusted-devices

    // ─── Receipts (handle_receipt_upload.py) ───
    case receipts                                    // GET  /receipts
    case receipt(id: Int64)                          // GET  /receipts/<id>
    case uploadReceipt                               // POST /receipts/upload (multipart)
    case updateReceipt(id: Int64)                    // PATCH /receipts/<id>
    case deleteReceipt(id: Int64)                    // DELETE /receipts/<id>
    case receiptImage(id: Int64)                     // GET  /receipts/<id>/image
    case receiptConfirm(id: Int64)                   // POST /receipts/<id>/confirm
    case receiptMarkReviewed(id: Int64)              // POST /receipts/<id>/mark-reviewed
    case rerunOCR(id: Int64)                         // POST /receipts/<id>/rerun-ocr

    // ─── Inventory (manage_inventory.py + manage_kitchen_endpoint.py) ───
    case inventory                                   // GET  /inventory
    case inventoryItem(id: Int64)                    // GET  /inventory/<id>
    case updateInventoryItem(id: Int64)              // PATCH /inventory/<id>
    case deleteInventoryItem(id: Int64)              // DELETE /inventory/<id>
    case adjustInventoryQuantity(id: Int64)          // POST /inventory/<id>/adjust
    case kitchenView                                 // GET  /kitchen

    // ─── Products (manage_product_catalog.py) ───
    case products                                    // GET  /products
    case product(id: Int64)                          // GET  /products/<id>
    case updateProduct(id: Int64)                    // PATCH /products/<id>
    case productCategories                           // GET  /products/categories

    // ─── Shopping (manage_shopping_list.py) ───
    case shoppingItems                               // GET  /shopping/items
    case shoppingItem(id: Int64)                     // GET  /shopping/items/<id>
    case createShoppingItem                          // POST /shopping/items
    case updateShoppingItem(id: Int64)               // PATCH /shopping/items/<id>
    case deleteShoppingItem(id: Int64)               // DELETE /shopping/items/<id>
    case shoppingAutoPopulate                        // POST /shopping/auto-populate
    case shoppingSession                             // GET  /shopping/session
    case closeShoppingSession                        // POST /shopping/session/close
    case shoppingShareQR                             // GET  /shopping/qr

    // ─── Recommendations (generate_recommendations.py) ───
    case recommendations                             // GET  /recommendations

    // ─── Analytics (calculate_spending_analytics.py) ───
    case spendingByCategory                          // GET  /analytics/spending-by-category
    case spendingAnalytics                           // GET  /analytics/spending
    case sankeyData                                  // GET  /analytics/sankey
    case exportCSV                                   // GET  /analytics/export-csv

    // ─── Finance: Floor Obligations (handle_floor_obligations.py) ───
    case floorObligations                            // GET  /obligations
    case floorObligation(id: Int64)                  // GET  /obligations/<id>
    case createFloorObligation                       // POST /obligations
    case updateFloorObligation(id: Int64)            // PATCH /obligations/<id>
    case deleteFloorObligation(id: Int64)            // DELETE /obligations/<id>
    case markObligationPaid(id: Int64)               // POST /obligations/<id>/mark-paid

    // ─── Finance: Cash Transactions (manage_cash_transactions.py) ───
    case cashTransactions                            // GET  /cash-transactions
    case createCashTransaction                       // POST /cash-transactions
    case updateCashTransaction(id: Int64)            // PATCH /cash-transactions/<id>
    case deleteCashTransaction(id: Int64)            // DELETE /cash-transactions/<id>

    // ─── Finance: Plaid (plaid_integration.py) ───
    case plaidItems                                  // GET  /plaid/items
    case plaidLinkTokenCreate                        // POST /plaid/link-token
    case plaidExchange                               // POST /plaid/exchange
    case plaidSync                                   // POST /plaid/sync
    case plaidStagedTransactions                     // GET  /plaid/staged-transactions
    case confirmStagedTransaction(id: Int64)         // POST /plaid/staged-transactions/<id>/confirm
    case dismissStagedTransaction(id: Int64)         // POST /plaid/staged-transactions/<id>/dismiss

    // ─── Budget (manage_household_budget.py) ───
    case budget                                      // GET  /budget
    case updateBudget                                // POST /budget
    case budgetChangeLog                             // GET  /budget/changelog

    // ─── Contributions (manage_contributions.py) ───
    case contributions                               // GET  /contributions
    case contributionEvents                          // GET  /contributions/events

    // ─── AI Models (manage_ai_models.py) ───
    case aiModels                                    // GET  /ai-models
    case setActiveAiModel                            // POST /ai-models/active
    case aiUsageStats                                // GET  /ai-models/usage

    // ─── Chat (chat_endpoints.py) ───
    case chatMessages                                // GET  /chat/messages
    case sendChatMessage                             // POST /chat/send  (SSE stream via SSEClient)
    case clearChatHistory                            // DELETE /chat/history

    // ─── Household Members (manage_household_members.py) ───
    case householdMembers                            // GET  /household/members
    case createHouseholdMember                       // POST /household/members
    case updateHouseholdMember(id: Int64)            // PATCH /household/members/<id>
    case deleteHouseholdMember(id: Int64)            // DELETE /household/members/<id>

    // ─── Medications (manage_medications.py) ───
    case medications                                 // GET  /medications
    case createMedication                            // POST /medications
    case updateMedication(id: Int64)                 // PATCH /medications/<id>
    case deleteMedication(id: Int64)                 // DELETE /medications/<id>
    case medicationBarcodeLookup(barcode: String)    // GET  /medications/barcode/<barcode>

    // ─── Shared Dining (shared_dining_endpoints.py) ───
    case sharedExpenses                              // GET  /dining/expenses
    case createSharedExpense                         // POST /dining/expenses
    case updateSharedExpense(id: Int64)              // PATCH /dining/expenses/<id>
    case diningContacts                              // GET  /dining/contacts
    case createDiningContact                         // POST /dining/contacts
    case diningBalances                              // GET  /dining/balances
    case settleDebt(id: Int64)                       // POST /dining/debts/<id>/settle

    // ─── System / Backup (manage_environment_ops.py) ───
    case backupList                                  // GET  /system/backups
    case createBackup                                // POST /system/backups
    case downloadBackup(filename: String)            // GET  /system/backups/<filename>
    case restoreBackup                               // POST /system/restore

    // ─── Stores (manage_stores_endpoint.py) ───
    case stores                                      // GET  /stores

    var path: String {
        switch self {
        case .me:                           return "/auth/me"
        case .config:                       return "/auth/config"
        case .login:                        return "/auth/login"
        case .logout:                       return "/auth/logout"
        case .oauthGoogleStart:             return "/auth/oauth/google"
        case .householdUsers:               return "/auth/household-users"
        case .invites:                      return "/auth/invites"
        case .qrImage:                      return "/auth/qr-image"
        case .devicePairingStart:           return "/auth/device-pairing/start"
        case .devicePairingStatus(let t):   return "/auth/device-pairing/status/\(t)"
        case .devicePairingClaim(let t):    return "/auth/device-pairing/claim/\(t)"
        case .trustedDevice(let id):        return "/auth/trusted-devices/\(id)"
        case .trustedDevices:               return "/auth/trusted-devices"
        case .receipts:                     return "/receipts"
        case .receipt(let id):              return "/receipts/\(id)"
        case .uploadReceipt:                return "/receipts/upload"
        case .updateReceipt(let id):        return "/receipts/\(id)"
        case .deleteReceipt(let id):        return "/receipts/\(id)"
        case .receiptImage(let id):         return "/receipts/\(id)/image"
        case .receiptConfirm(let id):       return "/receipts/\(id)/confirm"
        case .receiptMarkReviewed(let id):  return "/receipts/\(id)/mark-reviewed"
        case .rerunOCR(let id):             return "/receipts/\(id)/rerun-ocr"
        case .inventory:                    return "/inventory"
        case .inventoryItem(let id):        return "/inventory/\(id)"
        case .updateInventoryItem(let id):  return "/inventory/\(id)"
        case .deleteInventoryItem(let id):  return "/inventory/\(id)"
        case .adjustInventoryQuantity(let id): return "/inventory/\(id)/adjust"
        case .kitchenView:                  return "/kitchen"
        case .products:                     return "/products"
        case .product(let id):              return "/products/\(id)"
        case .updateProduct(let id):        return "/products/\(id)"
        case .productCategories:            return "/products/categories"
        case .shoppingItems:                return "/shopping/items"
        case .shoppingItem(let id):         return "/shopping/items/\(id)"
        case .createShoppingItem:           return "/shopping/items"
        case .updateShoppingItem(let id):   return "/shopping/items/\(id)"
        case .deleteShoppingItem(let id):   return "/shopping/items/\(id)"
        case .shoppingAutoPopulate:         return "/shopping/auto-populate"
        case .shoppingSession:              return "/shopping/session"
        case .closeShoppingSession:         return "/shopping/session/close"
        case .shoppingShareQR:              return "/shopping/qr"
        case .recommendations:              return "/recommendations"
        case .spendingByCategory:           return "/analytics/spending-by-category"
        case .spendingAnalytics:            return "/analytics/spending"
        case .sankeyData:                   return "/analytics/sankey"
        case .exportCSV:                    return "/analytics/export-csv"
        case .floorObligations:             return "/obligations"
        case .floorObligation(let id):      return "/obligations/\(id)"
        case .createFloorObligation:        return "/obligations"
        case .updateFloorObligation(let id): return "/obligations/\(id)"
        case .deleteFloorObligation(let id): return "/obligations/\(id)"
        case .markObligationPaid(let id):   return "/obligations/\(id)/mark-paid"
        case .cashTransactions:             return "/cash-transactions"
        case .createCashTransaction:        return "/cash-transactions"
        case .updateCashTransaction(let id): return "/cash-transactions/\(id)"
        case .deleteCashTransaction(let id): return "/cash-transactions/\(id)"
        case .plaidItems:                   return "/plaid/items"
        case .plaidLinkTokenCreate:         return "/plaid/link-token"
        case .plaidExchange:                return "/plaid/exchange"
        case .plaidSync:                    return "/plaid/sync"
        case .plaidStagedTransactions:      return "/plaid/staged-transactions"
        case .confirmStagedTransaction(let id): return "/plaid/staged-transactions/\(id)/confirm"
        case .dismissStagedTransaction(let id): return "/plaid/staged-transactions/\(id)/dismiss"
        case .budget:                       return "/budget"
        case .updateBudget:                 return "/budget"
        case .budgetChangeLog:              return "/budget/changelog"
        case .contributions:                return "/contributions"
        case .contributionEvents:           return "/contributions/events"
        case .aiModels:                     return "/ai-models"
        case .setActiveAiModel:             return "/ai-models/active"
        case .aiUsageStats:                 return "/ai-models/usage"
        case .chatMessages:                 return "/chat/messages"
        case .sendChatMessage:              return "/chat/send"
        case .clearChatHistory:             return "/chat/history"
        case .householdMembers:             return "/household/members"
        case .createHouseholdMember:        return "/household/members"
        case .updateHouseholdMember(let id): return "/household/members/\(id)"
        case .deleteHouseholdMember(let id): return "/household/members/\(id)"
        case .medications:                  return "/medications"
        case .createMedication:             return "/medications"
        case .updateMedication(let id):     return "/medications/\(id)"
        case .deleteMedication(let id):     return "/medications/\(id)"
        case .medicationBarcodeLookup(let b): return "/medications/barcode/\(b)"
        case .sharedExpenses:               return "/dining/expenses"
        case .createSharedExpense:          return "/dining/expenses"
        case .updateSharedExpense(let id):  return "/dining/expenses/\(id)"
        case .diningContacts:               return "/dining/contacts"
        case .createDiningContact:          return "/dining/contacts"
        case .diningBalances:               return "/dining/balances"
        case .settleDebt(let id):           return "/dining/debts/\(id)/settle"
        case .backupList:                   return "/system/backups"
        case .createBackup:                 return "/system/backups"
        case .downloadBackup(let f):        return "/system/backups/\(f)"
        case .restoreBackup:                return "/system/restore"
        case .stores:                       return "/stores"
        default:                            return "/"
        }
    }

    var method: String {
        switch self {
        case .login, .logout, .invites, .devicePairingStart, .uploadReceipt,
             .receiptConfirm, .receiptMarkReviewed, .rerunOCR, .shoppingAutoPopulate,
             .closeShoppingSession, .createShoppingItem, .shoppingAutoPopulate,
             .plaidExchange, .plaidSync, .confirmStagedTransaction, .dismissStagedTransaction,
             .plaidLinkTokenCreate, .setActiveAiModel, .sendChatMessage, .createCashTransaction,
             .createFloorObligation, .markObligationPaid, .createHouseholdMember,
             .createMedication, .createSharedExpense, .createDiningContact, .settleDebt,
             .createBackup, .restoreBackup, .adjustInventoryQuantity:
            return "POST"
        case .updateReceipt, .updateInventoryItem, .updateShoppingItem, .updateProduct,
             .updateFloorObligation, .updateCashTransaction, .updateHouseholdMember,
             .updateMedication, .updateSharedExpense, .updateBudget:
            return "PATCH"
        case .deleteReceipt, .deleteInventoryItem, .deleteShoppingItem,
             .deleteFloorObligation, .deleteCashTransaction, .deleteHouseholdMember,
             .deleteMedication, .trustedDevice, .clearChatHistory:
            return "DELETE"
        default:
            return "GET"
        }
    }

    var isMutating: Bool { method != "GET" }
}
```

**Endpoint groups and their consuming views:**

| Group | Endpoints | Primary View Files |
|---|---|---|
| Authentication (`manage_authentication.py`) | `me`, `config`, `login`, `logout`, `oauthGoogleStart`, `householdUsers`, `invites`, `qrImage`, `devicePairing*`, `trustedDevices` | `LoginView`, `AuthAndMembersView`, `SettingsView/AccountPane`, `GoogleOAuthSheet` |
| Receipts (`handle_receipt_upload.py`) | `receipts`, `receipt`, `uploadReceipt`, `updateReceipt`, `deleteReceipt`, `receiptImage`, `receiptConfirm`, `receiptMarkReviewed`, `rerunOCR` | `OCRUploadView`, `ReceiptReviewView`, `ReceiptListView`, `ReceiptInspectorPanel`, `RerunOCRView` |
| Inventory (`manage_inventory.py`) | `inventory`, `inventoryItem`, `updateInventoryItem`, `deleteInventoryItem`, `adjustInventoryQuantity`, `kitchenView` | `InventoryView`, `KitchenView`, `ProductDetailSheet` |
| Products (`manage_product_catalog.py`) | `products`, `product`, `updateProduct`, `productCategories` | `InventoryView` (name resolution), `ProductsCatalogView` [v1.1] |
| Shopping (`manage_shopping_list.py`) | `shoppingItems`, `shoppingItem`, `createShoppingItem`, `updateShoppingItem`, `deleteShoppingItem`, `shoppingAutoPopulate`, `shoppingSession`, `closeShoppingSession`, `shoppingShareQR` | `ShoppingListView`, `ShareQRView` |
| Recommendations (`generate_recommendations.py`) | `recommendations` | `ShoppingListView` (Recommendations tab) |
| Analytics (`calculate_spending_analytics.py`) | `spendingByCategory`, `spendingAnalytics`, `sankeyData`, `exportCSV` | `SpendingByCategoryView`, `DashboardView` (tile data) |
| Floor Obligations (`handle_floor_obligations.py`) | `floorObligations`, `floorObligation`, `createFloorObligation`, `updateFloorObligation`, `deleteFloorObligation`, `markObligationPaid` | `FixedBillsView` |
| Cash Transactions (`manage_cash_transactions.py`) | `cashTransactions`, `createCashTransaction`, `updateCashTransaction`, `deleteCashTransaction` | `CashTransactionsView`, `MenuBarPopoverView` (quick add) |
| Plaid (`plaid_integration.py`) | `plaidItems`, `plaidLinkTokenCreate`, `plaidExchange`, `plaidSync`, `plaidStagedTransactions`, `confirmStagedTransaction`, `dismissStagedTransaction` | `PlaidAccountsView` |
| Budget (`manage_household_budget.py`) | `budget`, `updateBudget`, `budgetChangeLog` | `HouseholdBudgetView` [v1.1] |
| Contributions (`manage_contributions.py`) | `contributions`, `contributionEvents` | `ContributionsView`, `DashboardView` (tile) |
| AI Models (`manage_ai_models.py`) | `aiModels`, `setActiveAiModel`, `aiUsageStats` | `ModelPicker`, `SettingsView/AIModelsPane`, `OCRUploadView` |
| Chat (`chat_endpoints.py`) | `chatMessages`, `sendChatMessage`, `clearChatHistory` | `AIChatView` [v1.1] |
| Household Members (`manage_household_members.py`) | `householdMembers`, `createHouseholdMember`, `updateHouseholdMember`, `deleteHouseholdMember` | `AuthAndMembersView` |
| Medications (`manage_medications.py`) | `medications`, `createMedication`, `updateMedication`, `deleteMedication`, `medicationBarcodeLookup` | `MedicationsView` [v1.1] |
| Shared Dining (`shared_dining_endpoints.py`) | `sharedExpenses`, `createSharedExpense`, `updateSharedExpense`, `diningContacts`, `createDiningContact`, `diningBalances`, `settleDebt` | `SplitBillsView`, `ContactsView`, `BalancesView` [v1.1] |
| System/Backup (`manage_environment_ops.py`) | `backupList`, `createBackup`, `downloadBackup`, `restoreBackup` | `SettingsView/BackupPane` |
| Stores (`manage_stores_endpoint.py`) | `stores` | `ReceiptReviewView` (store lookup autocomplete) |

**`APIClient.swift` core implementation:**

```swift
// LocalOCR/Networking/APIClient.swift
@MainActor
final class APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private init() {
        let config = URLSessionConfiguration.default
        config.httpCookieAcceptPolicy = .always
        config.httpShouldSetCookies = true
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.timeoutIntervalForRequest = 30
        session = URLSession(configuration: config, delegate: AuthInterceptor.shared, delegateQueue: nil)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
    }

    func request<T: Decodable>(
        _ endpoint: Endpoint,
        queryItems: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        responseType: T.Type
    ) async throws -> T {
        guard !AppState.shared.isDemoMode || !endpoint.isMutating else {
            throw APIError.demoModeReadOnly
        }
        let baseURL = PreferencesStore.shared.apiBaseURL
        var components = URLComponents(string: baseURL + endpoint.path)!
        if !queryItems.isEmpty { components.queryItems = queryItems }
        var request = URLRequest(url: components.url!)
        request.httpMethod = endpoint.method
        request.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(body)
        }
        let (data, response) = try await session.data(for: request)
        let httpResponse = response as! HTTPURLResponse
        switch httpResponse.statusCode {
        case 200...299:
            if T.self == EmptyResponse.self {
                return EmptyResponse() as! T
            }
            return try decoder.decode(T.self, from: data)
        case 401:
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden(message: parseErrorMessage(data))
        case 404:
            throw APIError.notFound
        case 422:
            throw APIError.validationFailed(errors: parseValidationErrors(data))
        default:
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: parseErrorMessage(data))
        }
    }

    // Multipart upload for receipt images
    func uploadReceipt(fileURL: URL, receiptType: String, modelId: Int64?) async throws -> Receipt {
        // Builds multipart/form-data body; calls POST /receipts/upload
        // Returns decoded Receipt on success
        fatalError("Implemented in full file — see ReceiptUploadHelper.swift")
    }
}

enum APIError: LocalizedError {
    case unauthorized
    case forbidden(message: String)
    case notFound
    case validationFailed(errors: [String: [String]])
    case serverError(statusCode: Int, message: String)
    case demoModeReadOnly
    case networkError(URLError)
}

struct EmptyResponse: Decodable {}

---

### 5.4 MENU IMPLEMENTATION

File: `LocalOCR/App/LocalOCRApp.swift` — `.commands { AppMenuCommands() }` modifier on the `WindowGroup` scene.

All domain-specific menus (`InventoryMenu`, `ShoppingMenu`, etc.) appear dynamically based on which screen is active. This is implemented via a `@FocusedValue` pattern: each view writes its context to `@FocusedValue(\.activeScreen)` and `AppMenuCommands` reads it to toggle visibility.

```swift
// LocalOCR/App/LocalOCRApp.swift
@main
struct LocalOCRApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState.shared
    @StateObject private var router = Router.shared

    var body: some Scene {
        WindowGroup("LocalOCR", id: "main") {
            RootView()
                .environmentObject(appState)
                .environmentObject(router)
        }
        .commands { AppMenuCommands() }
        .defaultSize(width: 1200, height: 750)

        WindowGroup(id: "receipt", for: Int64.self) { $id in
            ReceiptInspectorPanel(receiptId: id ?? 0)
        }
        .defaultSize(width: 800, height: 900)

        WindowGroup(id: "ocr-upload") {
            OCRUploadView()
        }
        .defaultSize(width: 700, height: 600)

        Settings { SettingsView() }

        MenuBarExtra("LocalOCR", image: "MenuBarIcon") {
            MenuBarPopoverView()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)
    }
}
```

**AppMenuCommands structure (`App/AppMenuCommands.swift`):**

```swift
struct AppMenuCommands: Commands {
    @FocusedValue(\.activeScreen) var activeScreen

    var body: some Commands {
        // LocalOCR Menu — CommandGroup replacecommand(.appInfo) etc. are handled by system
        // File Menu
        CommandGroup(replacing: .newItem) {
            Button("New Receipt Upload…") { Router.shared.openOCRUpload() }
                .keyboardShortcut("n", modifiers: .command)
            Button("New Cash Transaction") { Router.shared.openCashEntry() }
                .keyboardShortcut("n", modifiers: [.control, .command])
            Button("Open Receipt…") { Router.shared.openFilePicker() }
                .keyboardShortcut("o", modifiers: .command)
            Button("Import Receipts from Folder…") { Router.shared.importReceiptsFromFolder() }
                .keyboardShortcut("o", modifiers: [.shift, .command])
            Divider()
            Button("Export Spending as CSV…") { Router.shared.exportCSV() }
                .disabled(activeScreen?.canExportCSV != true)
            Divider()
            Button("Close Window") { NSApp.keyWindow?.close() }
                .keyboardShortcut("w", modifiers: .command)
        }

        // View Menu — Navigation shortcuts
        CommandMenu("View") {
            Button("Show Sidebar") { Router.shared.toggleSidebar() }
                .keyboardShortcut("s", modifiers: [.control, .command])
            Button("Show Inspector") { Router.shared.toggleInspector() }
                .keyboardShortcut("i", modifiers: [.control, .command])
            Divider()
            Button("Inventory") { Router.shared.navigate(to: .inventory) }
                .keyboardShortcut("1", modifiers: .command)
            Button("Shopping List") { Router.shared.navigate(to: .shopping) }
                .keyboardShortcut("2", modifiers: .command)
            Button("Fixed Bills") { Router.shared.navigate(to: .bills) }
                .keyboardShortcut("3", modifiers: .command)
            Button("Plaid Accounts") { Router.shared.navigate(to: .plaid) }
                .keyboardShortcut("4", modifiers: .command)
            Button("Cash Transactions") { Router.shared.navigate(to: .cash) }
                .keyboardShortcut("5", modifiers: .command)
            Button("Dashboard") { Router.shared.navigate(to: .dashboard) }
                .keyboardShortcut("0", modifiers: .command)
            Button("Contributions") { Router.shared.navigate(to: .contributions) }
                .keyboardShortcut("6", modifiers: .command)
            Divider()
            Button("Reload Data") { Router.shared.refreshCurrentScreen() }
                .keyboardShortcut("r", modifiers: .command)
        }

        // Domain-specific menus — visible only when corresponding screen is active
        if activeScreen == .inventory {
            CommandMenu("Inventory") {
                Button("Add Item…") { Router.shared.openAddInventoryItem() }
                    .keyboardShortcut("i", modifiers: [.option, .command])
                Button("Edit Selected Item") { Router.shared.editSelectedInventoryItem() }
                    .keyboardShortcut("e", modifiers: .command)
                    .disabled(Router.shared.selectedInventoryItemId == nil)
                Divider()
                Button("Mark as Low Stock") { Router.shared.markSelectedItemLow() }
                    .disabled(Router.shared.selectedInventoryItemId == nil)
                Button("Clear Low Stock Flag") { Router.shared.clearSelectedItemLow() }
                    .disabled(Router.shared.selectedInventoryItemId == nil)
                Divider()
                Button("View Price History") { Router.shared.showPriceHistory() }
                    .disabled(Router.shared.selectedInventoryItemId == nil)
            }
        }

        if activeScreen == .shopping {
            CommandMenu("Shopping") {
                Button("Add Item to List") { Router.shared.addShoppingItemInline() }
                    .keyboardShortcut("n", modifiers: .command)
                Button("Populate from Low Stock") { Router.shared.populateShoppingFromLowStock() }
                    .keyboardShortcut("p", modifiers: [.option, .command])
                Divider()
                Button("Share List via QR") { Router.shared.showShoppingQR() }
                    .keyboardShortcut("s", modifiers: [.shift, .command])
            }
        }

        if activeScreen == .bills {
            CommandMenu("Bills") {
                Button("Add Obligation…") { Router.shared.openAddObligation() }
                    .keyboardShortcut("n", modifiers: .command)
                Button("Rename Obligation") { Router.shared.renameSelectedObligation() }
                    .keyboardShortcut(.f2)
                    .disabled(Router.shared.selectedBillId == nil)
                Divider()
                Button("Link to Plaid Transaction") { Router.shared.linkBillToPlaid() }
                    .keyboardShortcut("l", modifiers: [.option, .command])
                    .disabled(Router.shared.selectedBillId == nil)
            }
        }

        // Receipt Inspector menu — active when Receipt Inspector window is key
        if activeScreen == .receiptInspector {
            CommandMenu("Receipts") {
                Button("Re-run OCR…") { Router.shared.rerunOCR() }
                    .keyboardShortcut("r", modifiers: [.option, .command])
                Button("Confirm Receipt") { Router.shared.confirmReceipt() }
                    .keyboardShortcut(.return, modifiers: .command)
                Divider()
                Button("Rotate Photo") { Router.shared.rotateReceiptPhoto() }
                    .keyboardShortcut("t", modifiers: [.option, .command])
                Button("Mark as Reviewed") { Router.shared.markReceiptReviewed() }
                Button("Delete Receipt") { Router.shared.deleteCurrentReceipt() }
            }
        }
    }
}
```

**Enabled-when state wiring**: All `Button` instances that depend on selection state or screen context use `.disabled(condition)` where the condition reads from `Router.shared` (a `@StateObject` propagated via `@EnvironmentObject`). The `activeScreen` `@FocusedValue` is written by each view in its `.onAppear` and `.onDisappear` using:

```swift
.focusedSceneValue(\.activeScreen, .inventory)
```

This replaces the domain-specific menu's visibility automatically as the user navigates.

---

### 5.5 KEYBOARD SHORTCUT IMPLEMENTATION

Shortcuts fall into three implementation categories. All 62 shortcuts from §3.4 are mapped below.

**Category A — App-global (defined in `AppMenuCommands` via `Button.keyboardShortcut`):**

| Shortcut | Action | Implementation location |
|---|---|---|
| `⌘N` | New Receipt Upload / Add item inline (context-dependent) | `CommandGroup(replacing: .newItem)` |
| `⌘O` | Open file via NSOpenPanel | `CommandGroup` in File menu |
| `⇧⌘O` | Import from folder | File menu |
| `⌘W` | Close frontmost window | Standard AppKit; no override needed |
| `⌘Q` | Quit | Standard AppKit; override in `AppDelegate.applicationShouldTerminate` if upload in progress |
| `⌘,` | Open Settings | Standard `.settings` command; provided by `Settings` scene |
| `⌘H` / `⌥⌘H` | Hide / Hide Others | Standard AppKit |
| `⌘Z` / `⇧⌘Z` | Undo / Redo | Standard AppKit `UndoManager` |
| `⌘F` | Focus search field | `CommandMenu("Edit")` → `Button("Find…")` posts `Notification(name: .focusSearchField)` |
| `⌘R` | Reload data | View menu `Button("Reload Data")` |
| `⌘P` | Print | `CommandGroup(replacing: .printItem)` |
| `⌃⌘F` | Full screen | Standard AppKit |

**Category B — Navigation (view-bound `Button.keyboardShortcut` in `AppMenuCommands`):**

| Shortcut | Navigation target |
|---|---|
| `⌘0` | Dashboard |
| `⌘1` | Inventory |
| `⌘2` | Shopping List |
| `⌘3` | Fixed Bills |
| `⌘4` | Plaid Accounts |
| `⌘5` | Cash Transactions |
| `⌘6` | Contributions |
| `⌃⌘S` | Toggle sidebar |
| `⌃⌘I` | Toggle inspector panel |

**Category C — View-local (`.keyboardShortcut` on Button/control within the view):**

These are placed directly in the view file — not in `AppMenuCommands` — because they only apply when the view is active. They use SwiftUI's `Button.keyboardShortcut` modifier with `localization: .withoutMirroring` where needed.

| Shortcut | View file | Implementation |
|---|---|---|
| `⌘Return` | `OCRUploadView`, `ReceiptReviewView`, `CashTransactionsView` | `.keyboardShortcut(.return, modifiers: .command)` on primary action button |
| `Esc` | All sheet views | `.keyboardShortcut(.escape)` on Cancel button |
| `⌥⌘R` | `ReceiptReviewView` | `.keyboardShortcut("r", modifiers: [.option, .command])` on Re-run OCR button |
| `⌥⌘T` | `ReceiptReviewView` | `.keyboardShortcut("t", modifiers: [.option, .command])` on Rotate Photo button |
| `⌥⌘I` | `InventoryView` | `.keyboardShortcut("i", modifiers: [.option, .command])` on Add Item button |
| `⌘E` | `InventoryView` | `.keyboardShortcut("e", modifiers: .command)` on Edit button |
| `⌥↑` / `⌥↓` | `InventoryView` | `.onKeyPress(.upArrow, modifiers: .option)` / `.downArrow` on focused row |
| `⌘L` | `InventoryView` | `.keyboardShortcut("l", modifiers: .command)` on Add to List button |
| `Space` | `ShoppingListView`, `FixedBillsView` | `.onKeyPress(.space)` on focused row to toggle state |
| `⌥⌘P` | `ShoppingListView` | `.keyboardShortcut("p", modifiers: [.option, .command])` on Populate button |
| `⌘⇧S` | `ShoppingListView` | `.keyboardShortcut("s", modifiers: [.shift, .command])` on QR Share button |
| `F2` | `FixedBillsView` | `.onKeyPress(.f2)` on selected obligation row → enter rename mode |
| `Return` | `FixedBillsView` inline edit | `InlineEditableCell` `onSubmit` |
| `⌥⌘L` | `FixedBillsView` | `.keyboardShortcut("l", modifiers: [.option, .command])` on Link Plaid button |
| `Return` | `PlaidAccountsView` staged transactions | `.keyboardShortcut(.return)` on Confirm button |
| `Delete` | `PlaidAccountsView` staged transactions | `.onKeyPress(.delete)` → dismiss |
| `←` / `→` | `SpendingByCategoryView`, `ContributionsView`, `CashTransactionsView` | `.onKeyPress(.leftArrow)` / `.rightArrow` on month navigation container |
| `⌘+` / `⌘-` | `ReceiptInspectorPanel` | `.keyboardShortcut("+")` / `.keyboardShortcut("-")` on zoom controls |
| `⌘0` (Inspector) | `ReceiptInspectorPanel` | `.keyboardShortcut("0")` on "Actual Size" button — scoped to Inspector window |
| `⌘S` | `SpendingByCategoryView` | `.keyboardShortcut("s", modifiers: .command)` when analytics is active |

**Category D — System-global (registered via `NSEvent.addGlobalMonitorForEvents`):**

| Shortcut | Implementation | File |
|---|---|---|
| `⌃⌘R` | `NSEvent.addGlobalMonitorForEvents(matching: .keyDown)` checks `keyCode == 15` (R) and modifiers `.control & .command`; posts `Notification(name: .globalShortcutReceiptUpload)` | `Native/GlobalShortcutManager.swift` |

**Conflict prevention notes (cross-checked against macOS 13+ system shortcuts):**

| Shortcut | Potential conflict | Resolution |
|---|---|---|
| `⌘E` | Some apps: "Use Selection for Find" | In our app this is view-scoped to Inventory only; no conflict when Inventory is not active |
| `⇧⌘O` | Some apps: Outline mode | Acceptable; self-hosted tool target audience is unlikely to be affected |
| `⌘⇧S` | Standard: "Save As…" in document apps | Our app has no document model; `⌘⇧S` is intentionally repurposed for QR Share |
| `⌃⌘R` | System: none confirmed on macOS 13+ | Safe; verified against System Settings → Keyboard |
| `F2` | Rare system use | Universally recognized as "rename" on macOS (Finder rename). Safe. |

---

### 5.6 STATE MANAGEMENT

All state objects live in `LocalOCR/State/`. They are `@MainActor` `ObservableObject` singletons (`.shared` pattern) injected into views via `@EnvironmentObject`. Views that need cross-cutting access use `@StateObject var foo = FooState.shared`; views that need only read access use `@EnvironmentObject var foo: FooState`.

---

**AuthState.swift**
```swift
// LocalOCR/State/AuthState.swift
@MainActor
final class AuthState: ObservableObject {
    static let shared = AuthState()

    enum State { case unauthenticated, needsHousehold, authenticated }

    @Published private(set) var state: State = .unauthenticated
    @Published private(set) var currentUser: User?
    @Published private(set) var isAuthenticating = false
    @Published var isDemoMode = false
    @Published var lastError: APIError?

    private let api = APIClient.shared
    private let keychain = KeychainStore()

    func checkSession() async {
        // GET /auth/me; on 200 → state = .authenticated; on 401 → state = .unauthenticated
    }

    func login(email: String, password: String) async throws {
        // POST /auth/login; on success: currentUser set; state = .authenticated
        // On failure: lastError set; throws APIError
    }

    func loginWithGoogle() async throws {
        // Initiates ASWebAuthenticationSession → oauthGoogleStart URL
        // Callback intercepted → POST /auth/oauth/google/callback via router
        // On success: currentUser set; state = .authenticated
    }

    func setDemoMode() {
        isDemoMode = true
        state = .authenticated
    }

    func logout() async {
        // POST /auth/logout; clears HTTPCookieStorage.shared; keychain.delete("oauth.refreshToken")
        // state = .unauthenticated; currentUser = nil; isDemoMode = false
    }

    func refreshSession() async -> Bool {
        // Called by BackgroundFetchScheduler on foreground
        // GET /auth/me; updates currentUser; returns false on 401
    }
}
```

---

**HouseholdState.swift**
```swift
// LocalOCR/State/HouseholdState.swift
@MainActor
final class HouseholdState: ObservableObject {
    static let shared = HouseholdState()

    @Published private(set) var users: [User] = []          // auth users (household)
    @Published private(set) var members: [HouseholdMember] = []  // non-auth household members
    @Published private(set) var trustedDevices: [TrustedDevice] = []

    func loadAll() async { /* GET /auth/household-users + GET /household/members + GET /auth/trusted-devices */ }
    func inviteMember(email: String) async throws { /* POST /auth/invites; returns invite link */ }
    func removeMember(userId: Int64) async throws { /* DELETE /auth/users/<id> */ }
    func revokeDevice(deviceId: Int64) async throws { /* DELETE /auth/trusted-devices/<id> */ }
    func addHouseholdMember(name: String, ageGroup: AgeGroup) async throws { /* POST /household/members */ }
}
```

---

**ReceiptsState.swift**
```swift
// LocalOCR/State/ReceiptsState.swift
@MainActor
final class ReceiptsState: ObservableObject {
    static let shared = ReceiptsState()

    @Published private(set) var receipts: [Receipt] = []
    @Published var pendingUploadURL: URL? = nil
    @Published private(set) var isUploading = false
    @Published private(set) var lastOCRResult: Receipt? = nil

    func loadReceipts(page: Int = 1) async { /* GET /receipts */ }
    func uploadReceipt(fileURL: URL, type: ReceiptType, modelId: Int64?) async throws -> Receipt { /* POST /receipts/upload */ }
    func confirmReceipt(id: Int64, attribution: AttributionPayload) async throws { /* POST /receipts/<id>/confirm */ }
    func rerunOCR(receiptId: Int64, modelId: Int64) async throws -> [ReceiptItemDiff] { /* POST /receipts/<id>/rerun-ocr */ }
    func deleteReceipt(id: Int64) async throws { /* DELETE /receipts/<id> */ }
}
```

---

**InventoryState.swift**
```swift
// LocalOCR/State/InventoryState.swift
@MainActor
final class InventoryState: ObservableObject {
    static let shared = InventoryState()

    @Published private(set) var items: [InventoryItem] = []
    @Published private(set) var categories: [String] = []

    var lowStockItems: [InventoryItem] {
        items.filter { $0.manualLow || ($0.quantity <= $0.threshold) }
    }
    var lowStockCount: Int { lowStockItems.count }

    func loadInventory() async { /* GET /inventory */ }
    func updateQuantity(id: Int64, delta: Int) async throws {
        // Optimistic: update items array locally
        // POST /inventory/<id>/adjust with { delta }
        // On failure: revert local change + toast
    }
    func markLow(id: Int64) async throws { /* PATCH /inventory/<id> with { manual_low: true } */ }
    func clearLow(id: Int64) async throws { /* PATCH /inventory/<id> with { manual_low: false } */ }
    func addToShoppingList(productId: Int64) async throws { /* POST /shopping/items with { product_id } */ }
    func deleteItem(id: Int64) async throws { /* DELETE /inventory/<id> */ }
}
```

---

**ShoppingState.swift**
```swift
// LocalOCR/State/ShoppingState.swift
@MainActor
final class ShoppingState: ObservableObject {
    static let shared = ShoppingState()

    @Published private(set) var items: [ShoppingListItem] = []
    @Published private(set) var session: ShoppingSession? = nil
    @Published private(set) var recommendations: [Recommendation] = []

    var uncheckedItems: [ShoppingListItem] { items.filter { $0.status == .open } }
    var purchasedItems: [ShoppingListItem] { items.filter { $0.status == .purchased } }

    func loadAll() async { /* GET /shopping/items + GET /shopping/session + GET /recommendations */ }
    func addItem(name: String) async throws -> ShoppingListItem {
        // Optimistic: insert at top of items array
        // POST /shopping/items
    }
    func togglePurchased(id: Int64) async throws {
        // Optimistic: flip status in items array
        // PATCH /shopping/items/<id>
    }
    func removeItem(id: Int64) async throws {
        // Optimistic: remove from items array
        // DELETE /shopping/items/<id>
    }
    func populateFromLowStock() async throws { /* POST /shopping/auto-populate */ }
    func addRecommendation(productId: Int64) async throws { /* POST /shopping/items with product_id */ }
    func generateShareQR() async throws -> URL { /* GET /shopping/qr → returns URL */ }
}
```

---

**FinanceState.swift**
```swift
// LocalOCR/State/FinanceState.swift
@MainActor
final class FinanceState: ObservableObject {
    static let shared = FinanceState()

    @Published private(set) var bills: [FixedBill] = []
    @Published private(set) var cashTransactions: [CashTransaction] = []
    @Published private(set) var plaidAccounts: [PlaidAccount] = []
    @Published private(set) var stagedTransactions: [PlaidTransaction] = []

    func loadBills(month: Date) async { /* GET /obligations?month=<YYYY-MM> */ }
    func togglePaid(billId: Int64) async throws {
        // Optimistic: flip payment status in bills array
        // POST /obligations/<id>/mark-paid
    }
    func renameBill(id: Int64, newLabel: String) async throws {
        // Optimistic: update label in bills array
        // PATCH /obligations/<id> with { label: newLabel }
    }
    func addBill(form: ObligationForm) async throws { /* POST /obligations */ }
    func loadCashTransactions(month: Date) async { /* GET /cash-transactions?month=<YYYY-MM> */ }
    func logCashTransaction(form: CashTransactionForm) async throws { /* POST /cash-transactions */ }
    func loadPlaid() async { /* GET /plaid/items + GET /plaid/staged-transactions */ }
    func confirmStagedTransaction(id: Int64) async throws { /* POST /plaid/staged-transactions/<id>/confirm */ }
    func dismissStagedTransaction(id: Int64) async throws { /* POST /plaid/staged-transactions/<id>/dismiss */ }
    func syncPlaid() async { /* POST /plaid/sync */ }
}
```

---

**ChatState.swift** `[v1.1]`
```swift
// LocalOCR/State/ChatState.swift
@MainActor
final class ChatState: ObservableObject {
    static let shared = ChatState()

    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isStreaming = false
    @Published private(set) var streamingBuffer = ""

    func loadHistory() async { /* GET /chat/messages */ }
    func sendMessage(content: String) async throws {
        // Appends user message locally
        // POST /chat/send via SSEClient
        // Streams response tokens into streamingBuffer
        // On complete: moves buffer to messages array
    }
    func clearHistory() async throws { /* DELETE /chat/history */ }
}
```

---

**DemoModeGate.swift**
```swift
// LocalOCR/State/DemoModeGate.swift
// ViewModifier wrapping write-action handlers
struct DemoModeGate: ViewModifier {
    @EnvironmentObject var appState: AppState
    let message: String
    let realAction: () -> Void

    func body(content: Content) -> some View {
        content.simultaneousGesture(
            TapGesture().onEnded {
                if appState.isDemoMode {
                    ToastQueue.shared.add(message: message, severity: .warning)
                } else {
                    realAction()
                }
            }
        )
    }
}

extension View {
    func demoGated(message: String = "Demo mode — sign in to save", action: @escaping () -> Void) -> some View {
        self.modifier(DemoModeGate(message: message, realAction: action))
    }
}
```

---

**UserDefaults keys (`PreferencesStore.swift`):**

```swift
// LocalOCR/Networking/PreferencesStore.swift
final class PreferencesStore {
    static let shared = PreferencesStore()
    private let defaults = UserDefaults.standard

    // Server configuration
    var apiBaseURL: String {
        get { defaults.string(forKey: "LocalOCR.apiBaseURL") ?? "http://localhost:8090" }
        set { defaults.set(newValue, forKey: "LocalOCR.apiBaseURL") }
    }

    // Appearance
    var preferredAppearance: String {  // "system" | "light" | "dark"
        get { defaults.string(forKey: "LocalOCR.appearance") ?? "system" }
        set { defaults.set(newValue, forKey: "LocalOCR.appearance") }
    }

    // Navigation
    var defaultLandingTab: String {    // "dashboard" | "inventory" | "shopping" | "bills" | ...
        get { defaults.string(forKey: "LocalOCR.defaultLandingTab") ?? "dashboard" }
        set { defaults.set(newValue, forKey: "LocalOCR.defaultLandingTab") }
    }

    // OCR defaults
    var defaultOCRModelConfigId: Int64? {
        get { defaults.object(forKey: "LocalOCR.defaultOCRModel") as? Int64 }
        set { defaults.set(newValue, forKey: "LocalOCR.defaultOCRModel") }
    }
    var autoRotateReceipts: Bool {
        get { defaults.bool(forKey: "LocalOCR.autoRotateLandscape") }
        set { defaults.set(newValue, forKey: "LocalOCR.autoRotateLandscape") }
    }
    var defaultReceiptType: String {   // "auto" | "grocery" | "restaurant" | "expense"
        get { defaults.string(forKey: "LocalOCR.defaultReceiptType") ?? "auto" }
        set { defaults.set(newValue, forKey: "LocalOCR.defaultReceiptType") }
    }
    var confirmReceiptBeforeSave: Bool {
        get { defaults.bool(forKey: "LocalOCR.confirmReceiptBeforeSave") }
        set { defaults.set(newValue, forKey: "LocalOCR.confirmReceiptBeforeSave") }
    }

    // Notifications
    var shoppingNudgeEnabled: Bool {
        get { defaults.bool(forKey: "LocalOCR.shoppingNudgeEnabled") }
        set { defaults.set(newValue, forKey: "LocalOCR.shoppingNudgeEnabled") }
    }
    var shoppingNudgeTime: String {    // "HH:mm" format e.g. "09:30"
        get { defaults.string(forKey: "LocalOCR.shoppingNudgeTime") ?? "09:30" }
        set { defaults.set(newValue, forKey: "LocalOCR.shoppingNudgeTime") }
    }
    var nudgeMinThreshold: Int {
        get { defaults.integer(forKey: "LocalOCR.nudgeMinThreshold") > 0
              ? defaults.integer(forKey: "LocalOCR.nudgeMinThreshold") : 3 }
        set { defaults.set(newValue, forKey: "LocalOCR.nudgeMinThreshold") }
    }
    var inventoryAlertsEnabled: Bool {
        get { defaults.bool(forKey: "LocalOCR.inventoryAlertsEnabled") }
        set { defaults.set(newValue, forKey: "LocalOCR.nudgeMinThreshold") }
    }
    var weeklySummaryEnabled: Bool {
        get { defaults.bool(forKey: "LocalOCR.weeklySummaryEnabled") }
        set { defaults.set(newValue, forKey: "LocalOCR.weeklySummaryEnabled") }
    }

    // Menu bar
    var menuBarIconEnabled: Bool {
        get { defaults.object(forKey: "LocalOCR.menuBarIconEnabled") as? Bool ?? true }
        set { defaults.set(newValue, forKey: "LocalOCR.menuBarIconEnabled") }
    }
    var globalShortcutEnabled: Bool {
        get { defaults.object(forKey: "LocalOCR.globalShortcutEnabled") as? Bool ?? true }
        set { defaults.set(newValue, forKey: "LocalOCR.globalShortcutEnabled") }
    }

    // Debug
    var debugLoggingEnabled: Bool {
        get { defaults.bool(forKey: "LocalOCR.debugLoggingEnabled") }
        set { defaults.set(newValue, forKey: "LocalOCR.debugLoggingEnabled") }
    }

    // Refresh timestamps (not sensitive — used to gate background fetches)
    var lastInventoryRefresh: Date? {
        get { defaults.object(forKey: "LocalOCR.lastInventoryRefresh") as? Date }
        set { defaults.set(newValue, forKey: "LocalOCR.lastInventoryRefresh") }
    }
    var lastShoppingRefresh: Date? {
        get { defaults.object(forKey: "LocalOCR.lastShoppingRefresh") as? Date }
        set { defaults.set(newValue, forKey: "LocalOCR.lastShoppingRefresh") }
    }
    var lastPlaidRefresh: Date? {
        get { defaults.object(forKey: "LocalOCR.lastPlaidRefresh") as? Date }
        set { defaults.set(newValue, forKey: "LocalOCR.lastPlaidRefresh") }
    }

    // Window state
    var openReceiptInspectorIds: [Int64] {
        get { defaults.array(forKey: "LocalOCR.openReceiptInspectors") as? [Int64] ?? [] }
        set { defaults.set(newValue, forKey: "LocalOCR.openReceiptInspectors") }
    }
    var spotlightLastIndexed: Date? {
        get { defaults.object(forKey: "LocalOCR.spotlightLastIndexed") as? Date }
        set { defaults.set(newValue, forKey: "LocalOCR.spotlightLastIndexed") }
    }
    var trustedHosts: [String] {       // hostnames with user-approved self-signed cert bypass
        get { defaults.array(forKey: "LocalOCR.trustedHosts") as? [String] ?? [] }
        set { defaults.set(newValue, forKey: "LocalOCR.trustedHosts") }
    }
}
```

**In-memory only (no persistence):**
- `ToastQueue`: live queue of active toasts; populated by `APIClient` error handlers and mutation side-effects; read by `ToastHost` overlay
- `AppState.pendingUploadURLs: [URL]`: queue of files waiting to be submitted to OCR; cleared after each upload
- Streaming chat tokens in `ChatState.streamingBuffer` (until message is complete and moved to `messages`)

---

### 5.7 DESKTOP LAYOUT WRAPPER

File: `LocalOCR/App/RootView.swift`

`RootView` is the root content view of the main `WindowGroup`. It reads `AuthState.state` and switches between authentication flow and the main application shell. It also mounts global overlays that must be visible regardless of which screen is active.

```swift
// LocalOCR/App/RootView.swift
struct RootView: View {
    @EnvironmentObject var auth: AuthState
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var router: Router
    @StateObject private var toastQueue = ToastQueue.shared

    var body: some View {
        Group {
            switch auth.state {
            case .unauthenticated:
                LoginView()
                    .frame(minWidth: 400, minHeight: 500)
            case .needsHousehold:
                HouseholdSelectorView()  // [DEFERRED — see §3.7 View 2]
            case .authenticated:
                MainSplitView()
                    .frame(minWidth: 900, minHeight: 600)
            }
        }
        // Global overlays applied to all states:
        .overlay(alignment: .top) {
            if auth.isDemoMode {
                DemoModeBanner(onSignIn: { router.presentLoginSheet() })
            }
        }
        .overlay(alignment: .topTrailing) {
            ToastHost()
                .environmentObject(toastQueue)
                .padding(.top, auth.isDemoMode ? 44 : 8)  // shift below demo banner
        }
        .sheet(item: $router.activeSheet) { sheet in
            sheetContent(sheet)
        }
        .onOpenURL { url in router.handleURL(url) }
    }

    @ViewBuilder
    private func sheetContent(_ sheet: RouterSheet) -> some View {
        switch sheet {
        case .ocrUpload(let url):    OCRUploadView(initialFileURL: url)
        case .attribution(let id):  AttributionPicker(receiptId: id)
        case .login:                LoginView()
        case .cashEntry:            CashTransactionsView()
        }
    }
}
```

**MainSplitView:**

```swift
// Rendered when auth.state == .authenticated
struct MainSplitView: View {
    @EnvironmentObject var router: Router
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // Sidebar column (~220pt)
            SidebarView()
                .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 340)
        } content: {
            // Content column (primary — fills remaining space minus optional detail)
            destinationView(for: router.activeDestination)
        } detail: {
            // Detail/inspector column (~280pt) — appears when selection is active
            if let detail = router.activeDetailDestination {
                detailView(for: detail)
            } else {
                EmptyStateView(
                    systemImage: "sidebar.right",
                    title: "No selection",
                    subtitle: "Select an item to see details"
                )
            }
        }
        .navigationSplitViewStyle(.balanced)
    }

    @ViewBuilder
    private func destinationView(for destination: RouterDestination) -> some View {
        switch destination {
        case .dashboard:      DashboardView()
        case .inventory:      InventoryView()
        case .shopping:       ShoppingListView()
        case .bills:          FixedBillsView()
        case .plaid:          PlaidAccountsView()
        case .cash:           CashTransactionsView()
        case .contributions:  ContributionsView()
        case .analytics:      SpendingByCategoryView()
        case .members:        AuthAndMembersView()
        }
    }
}
```

**SidebarView** maps to the 8 domain-navigation items from §3.3 (View menu tabs). Each `Label` uses an SF Symbol icon. Sidebar items use `.badge(count)` modifier for live counts (low-stock count on Inventory item, staged-transaction count on Plaid item).

```swift
struct SidebarView: View {
    @EnvironmentObject var router: Router
    @StateObject var inventory = InventoryState.shared
    @StateObject var finance = FinanceState.shared

    var body: some View {
        List(selection: $router.activeDestination) {
            Label("Dashboard", systemImage: "house.fill").tag(RouterDestination.dashboard)
            Label("Inventory", systemImage: "shippingbox.fill").tag(RouterDestination.inventory)
                .badge(inventory.lowStockCount > 0 ? inventory.lowStockCount : nil)
            Label("Shopping", systemImage: "cart.fill").tag(RouterDestination.shopping)
            Label("Fixed Bills", systemImage: "creditcard.fill").tag(RouterDestination.bills)
            Label("Plaid Accounts", systemImage: "building.columns.fill").tag(RouterDestination.plaid)
                .badge(finance.stagedTransactions.count > 0 ? finance.stagedTransactions.count : nil)
            Label("Cash Transactions", systemImage: "dollarsign.circle.fill").tag(RouterDestination.cash)
            Label("Contributions", systemImage: "trophy.fill").tag(RouterDestination.contributions)
            Divider()
            Label("Analytics", systemImage: "chart.bar.fill").tag(RouterDestination.analytics)
            Label("Members", systemImage: "person.2.fill").tag(RouterDestination.members)
        }
        .listStyle(.sidebar)
        .navigationTitle("LocalOCR")
        .contextMenu { SidebarItemContextMenu() }
    }
}
```

---

### 5.8 BUILD ORDER — PHASE PLAN

This is the sequence the build agent must follow. Each checkbox is a discrete, verifiable milestone. Dependencies flow strictly downward — never start a phase until all prior phases pass.

---

**Phase 0 — Prerequisites (human completes before build agent starts):**
- [ ] macOS 13+ machine with Xcode 15.0+ installed (Xcode 16+ recommended for Swift 6 concurrency warnings)
- [ ] Apple Developer account enrolled in Apple Developer Program with Developer ID Application certificate installed in Keychain Access
- [ ] LocalOCR backend running locally at `http://localhost:8090` (Docker Compose project `localocr_extended` started via `docker compose up -d`)
- [ ] Test user account created in backend with at least one household, at least 5 inventory items, and at least one receipt

---

**Phase 1 — Foundation (no UI, no networking; just a compiling project):**
- [ ] Create Xcode project `LocalOCR.macOS`, bundle ID `com.localocr.macos`, deployment target macOS 13.0, Swift 5.10 language version
- [ ] Create `Info.plist` entries: `NSCameraUsageDescription`, `CFBundleURLTypes` (scheme `localocr`), `LSMinimumSystemVersion 13.0`
- [ ] Create `LocalOCR.entitlements` with the four entries from §4.6 (network.client, files.user-selected.read-write, camera, no app-sandbox)
- [ ] Add SPM packages: `KeychainAccess 4.2.2` (kishikawakatsuki/KeychainAccess), `Kingfisher 7.12.0` (onevcat/Kingfisher)
- [ ] Create folder structure exactly matching §4.2 (App, Design, Components, Views/*, Networking/Models, Native, Background, State, Resources)
- [ ] Implement `Design/DesignTokens.swift` with all §3.1 color tokens as `Color` extensions
- [ ] Implement `Design/Typography.swift` with §3.1 type scale as `Font` extensions
- [ ] Implement `Design/Animations.swift` with duration constants and `withReducedMotion` helper
- [ ] Implement `Design/ButtonStyles.swift`, `Design/TextFieldStyles.swift`, `Design/ListRowStyles.swift` — all compile-only stubs at this stage
- [ ] Implement `App/Constants.swift` with UserDefaults key strings, notification category IDs
- [ ] Implement `App/LocalOCRApp.swift` with `@main` struct, `WindowGroup` stub, `.commands { }` stub, `Settings { }` stub
- [ ] Implement `App/AppDelegate.swift` with empty `NSApplicationDelegate` methods (just stubs)
- [ ] Implement `App/Router.swift` with `RouterDestination` enum and empty navigation methods
- [ ] Implement `App/AppState.swift` with `@Published` fields stubbed
- [ ] **Verify**: Project builds with zero errors (`xcodebuild -scheme LocalOCR build`); launches to an empty window

---

**Phase 2 — Design System:**
- [ ] Implement all 26 components from §5.1 with full logic (not stubs):
  - `Card`, `Badge`, `LowStockPill`, `CategoryChip`, `KeyValueRow`
  - `DropZone`, `ReceiptThumbnail`, `EmptyStateView`, `SkeletonView`, `ProgressBarView`
  - `Toast` + `ToastQueue` + `ToastHost`, `InlineEditableCell`, `ContextMenuModifiers`
  - `AttributionPicker`, `QRCodeView`, `ModelPicker`, `DemoModeBanner`
  - `SankeyWebView` (stub with placeholder text — HTML template is `[v1.1]`)
  - `SpendingBarChart` (inline pattern documented; no standalone file needed)
- [ ] Implement `App/RootView.swift` and `MainSplitView` per §5.7
- [ ] Implement `Views/Auth/LoginView.swift` (static — no networking yet; show the form)
- [ ] Implement `SidebarView` inside `MainSplitView`
- [ ] Add Xcode Previews (`#Preview { ... }`) for every component and the LoginView
- [ ] **Verify**: All previews render in both light and dark mode; all hover states work; no VoiceOver traps; skeleton shimmer animation plays; reduce-motion fallback confirmed by toggling System Settings → Accessibility → Reduce Motion

---

**Phase 3 — Networking + Auth:**
- [ ] Implement `Networking/APIClient.swift` with full `request<T>` method, error dispatch per §4.5 matrix, demo-mode gate, User-Agent header
- [ ] Implement `Networking/Endpoints.swift` with all endpoint cases from §5.3 (`path` and `method` computed properties)
- [ ] Implement `Networking/AuthInterceptor.swift` as `URLSessionDelegate` detecting 401 and posting `Notification(name: .authSessionExpired)`
- [ ] Implement `Networking/KeychainStore.swift` wrapping KeychainAccess
- [ ] Implement `Networking/PreferencesStore.swift` with all UserDefaults keys from §5.6
- [ ] Implement `Networking/ImageCache.swift` wrapping Kingfisher with authenticated URL support
- [ ] Implement `State/AuthState.swift` with `checkSession()`, `login()`, `loginWithGoogle()`, `setDemoMode()`, `logout()`
- [ ] Wire `RootView` to `AuthState.state`: unauthenticated → `LoginView`, authenticated → `MainSplitView`
- [ ] Implement `Views/Auth/GoogleOAuthSheet.swift` with `ASWebAuthenticationSession`
- [ ] Add `NotificationCenter` observer in `AuthState` for `.authSessionExpired` → calls `logout()`
- [ ] Implement `BackgroundFetchScheduler.swift` — foreground refresh with 60s minimum gate
- [ ] **Verify**: Login with valid credentials → `MainSplitView` appears; login with invalid credentials → inline error; server URL change in Settings → APIClient picks up new URL on next request; ⌘Q with no upload in progress → app quits immediately

---

**Phase 4 — Core MVP Views (strict dependency order):**
- [ ] `State/InventoryState.swift`, `State/ShoppingState.swift`, `State/FinanceState.swift` — implement all methods
- [ ] `State/HouseholdState.swift`, `State/ReceiptsState.swift` — implement all methods
- [ ] `Views/Dashboard/DashboardView.swift` — tile grid, skeleton loaders, drag-drop target
- [ ] `Views/Inventory/InventoryView.swift` — category sidebar, product list, quantity stepper, low-stock filter
- [ ] `Views/Inventory/KitchenView.swift` — category grid cards
- [ ] `Views/Inventory/ProductDetailSheet.swift` — inspector panel with price history chart
- [ ] `Views/Receipts/OCRUploadView.swift` — DropZone + ContinuityCamera check + model picker + submit
- [ ] `Views/Receipts/ReceiptReviewView.swift` — two-panel layout, line item list, diff mode, attribution picker sheet
- [ ] `Views/Shopping/ShoppingListView.swift` — checkbox list, recommendations tab, kitchen tab, QR share
- [ ] `Views/Finance/FixedBillsView.swift` — obligation list, inline rename, paid toggle, cadence sections
- [ ] `Views/Finance/PlaidAccountsView.swift` — accounts section, staged transactions, ASWebAuthenticationSession flow
- [ ] `Views/Finance/CashTransactionsView.swift` — quick-entry form, history list
- [ ] `Views/Analytics/SpendingByCategoryView.swift` — OutlineGroup categories, month navigation
- [ ] `Views/Auth/AuthAndMembersView.swift` — user list, device list, pairing flow
- [ ] `Views/Contributions/ContributionsView.swift` — leaderboard, event history disclosure
- [ ] `Views/Settings/SettingsView.swift` + all 8 pane files from §4.2
- [ ] `Views/DemoMode/DemoModeOverlay.swift` + `State/DemoModeGate.swift` — full enforcement
- [ ] **Verify**: Walk through §2.5 Journey 1 (Inventory → Shopping List) end-to-end; Journey 2 (OCR Upload → Review → Confirm) end-to-end; Journey 3 (Fixed Bills → Mark Paid) end-to-end

---

**Phase 5 — Native Integrations:**
- [ ] `Native/GlobalShortcutManager.swift` — `NSEvent.addGlobalMonitorForEvents`; accessibility permission prompt; `⌃⌘R` → open OCR Upload
- [ ] `Native/MenuBarController.swift` + `Views/MenuBar/MenuBarPopoverView.swift` — `NSStatusItem` + popover; badge update from `AppState.lowStockCount`
- [ ] `Native/NotificationManager.swift` + `Background/NudgeScheduler.swift` — permission request; shopping nudge scheduling; Plaid login-required notification
- [ ] `Native/DockBadge.swift` — `NSApp.dockTile.badgeLabel` wired to `AppState.lowStockCount`
- [ ] `Native/ContinuityCameraHelper.swift` — availability check; photo capture; delivery to `OCRUploadView`
- [ ] `App/AppDelegate.swift` (full) — `application(_:open:)` for Dock drops; `applicationDidBecomeActive` for foreground refresh; `applicationShouldTerminateAfterLastWindowClosed` returns false
- [ ] `App/AppMenuCommands.swift` — full command structure per §5.4 (all domain-specific menus wired to `@FocusedValue`)
- [ ] `Native/LoginItemController.swift` — `SMAppService` register/unregister
- [ ] `App/Constants.swift` — add URL scheme host strings; verify `localocr://` scheme registered in `Info.plist`
- [ ] `App/Router.swift` (full) — `handleURL(_:)` for all `localocr://` deep links from §4.6
- [ ] All 62 keyboard shortcuts from §5.5 implemented and verified
- [ ] `Native/FileDropHandler.swift` — UTType validation; NSItemProvider extraction
- [ ] **Verify**: ⌃⌘R from another app opens OCR Upload; menu bar icon shows badge count; notification fires at 09:30 (advance system clock to test); Dock badge reflects low-stock count; drag receipt from Finder to Dock icon triggers upload panel; all §3.4 shortcuts active

---

**Phase 6 — Preferences Window:**
- [ ] `Views/Settings/GeneralPane.swift` — appearance picker, landing tab picker, OCR model picker, menu bar toggle, launch-at-login toggle
- [ ] `Views/Settings/AccountPane.swift` — signed-in user card, server URL field, QR login, sign-out, manage members link
- [ ] `Views/Settings/AIModelsPane.swift` — model list, active model picker, unlock/lock (admin), usage stats
- [ ] `Views/Settings/TrustedDevicesPane.swift` — device list, pair new device (QR polling flow)
- [ ] `Views/Settings/TelegramPane.swift` — bot token, webhook URL display, nudge time picker
- [ ] `Views/Settings/NotificationsPane.swift` — permission status banner, nudge toggle, nudge time picker, Plaid alert toggle
- [ ] `Views/Settings/BackupPane.swift` — backup list, create/download/restore; admin-gated
- [ ] `Views/Settings/AdvancedPane.swift` — server URL, debug logging, cache purge, diagnostic log export, app version
- [ ] Wire all `PreferencesStore` bindings from §5.6
- [ ] **Verify**: Change server URL → next API call uses new URL; change nudge time → next foreground refresh re-schedules notification; appearance toggle changes `NSApp.appearance` live; "Launch at Login" toggle registers/unregisters via `SMAppService`

---

**Phase 7 — Polish:**
- [ ] App icon: generate all required sizes from a 1024×1024 source (16, 32, 64, 128, 256, 512, 1024 @1x and @2x) and place in `Assets.xcassets/AppIcon.appiconset`
- [ ] About panel: set `NSApp.orderFrontStandardAboutPanel(options:)` with `NSAboutPanelOptionKey.credits` showing version, build, and copyright
- [ ] Onboarding sheet: shown on first launch only (checked via `PreferencesStore.hasCompletedOnboarding`); walks user through server URL → login → notification permission
- [ ] Empty states for every list view: confirm each view has a correctly configured `EmptyStateView` for the no-data case
- [ ] Skeleton loaders: confirm every view that makes a network request on appear has at least one `SkeletonView` row/card visible during loading
- [ ] VoiceOver audit: run VoiceOver on all 16 MVP views; fix any unlabeled icon buttons or navigation traps; ensure every interactive control has `.accessibilityLabel`
- [ ] Reduce-motion audit: toggle System Settings → Accessibility → Reduce Motion; confirm all animations become instant; skeleton shimmer becomes static
- [ ] Accessibility acceptance criteria per §2.6 AC-11: every v1.0 screen VoiceOver-navigable in logical reading order; no VoiceOver trap exists

---

**Phase 8 — Testing:**
- [ ] `LocalOCRTests/APIClientTests.swift` — mock URLSession; test all HTTP error paths per §4.5 error matrix; test demo-mode gate blocks POST/PATCH/DELETE
- [ ] `LocalOCRTests/ModelsTests.swift` — JSON decode round-trips for all Codable models; verify `convertFromSnakeCase` handles all field names correctly
- [ ] `LocalOCRTests/KeychainStoreTests.swift` — write, read, delete items from test Keychain service; verify nothing stored in UserDefaults
- [ ] `LocalOCRTests/DemoModeGateTests.swift` — `isDemoMode = true` → write actions return `DemoModeError`; `isDemoMode = false` → actions call through normally
- [ ] `LocalOCRTests/RouterTests.swift` — `localocr://receipt/42` → `activeDetailDestination = .receipt(42)`; `localocr://shopping` → `activeDestination = .shopping`; unknown host → toast posted
- [ ] `LocalOCRUITests/LoginFlowTests.swift` — type valid credentials → dashboard appears; type invalid → error text visible below password field
- [ ] `LocalOCRUITests/OCRUploadFlowTests.swift` — drag test PDF onto DropZone → review view appears; confirm → success toast visible
- [ ] `LocalOCRUITests/InventoryFlowTests.swift` — type search query → results filter; press ⌥↑ on selected row → quantity increments; press ⌘L → item added to shopping list
- [ ] `LocalOCRUITests/SettingsFlowTests.swift` — change server URL → verify PreferencesStore updated; toggle notifications → verify `UNUserNotificationCenter` state reflects toggle
- [ ] **Verify**: `xcodebuild test -scheme LocalOCR -testPlan LocalOCRTests` exits 0; all unit and UI tests pass

---

**Phase 9 — Build & Ship:**
- [ ] Run `scripts/build-release.sh` to archive and export `LocalOCR.app` (arm64 only per §2.1)
- [ ] Verify code signing: `codesign --verify --deep --strict --verbose=4 LocalOCR.app`
- [ ] Create DMG via `scripts/create-dmg.sh`
- [ ] Run `scripts/notarize.sh` with valid `APPLE_ID`, `TEAM_ID`, `APP_PASSWORD`; wait for notarization approval
- [ ] Staple ticket: `xcrun stapler staple LocalOCR-1.0.0-arm64.dmg`
- [ ] Verify Gatekeeper: on a clean Mac (or with `xattr -r -d com.apple.quarantine` removed then re-applied), open the DMG and launch the app; confirm no "unverified developer" error
- [ ] Create GitHub release with `LocalOCR-1.0.0-arm64.dmg` as release asset
- [ ] Update `README.md` with installation instructions (download DMG → drag to Applications → launch)
- [ ] Verify all 18 acceptance criteria from §2.6 are ✅ before tagging the release

---

*End of Section 5 — IMPLEMENTATION SPEC*

---

## 6. TEST PLAN
*Authored by: [AGENT 6 — QA ENGINEER]*

### 6.1 TEST MATRIX

Every test run is executed against a specific hardware and OS combination. The matrix below establishes baseline targets, priority tiers, and coverage expectations. P0 configurations gate the merge. P1 configurations gate the v1.0 release tag. P2 is v1.1+.

| Mac Model | Chip | macOS Version | Display | Priority | Coverage |
|---|---|---|---|---|---|
| M1 MacBook Air (2020) | Apple M1 | 13.6 Ventura | Built-in 13.6" Retina (2560×1664) | **P0 — baseline** | Full unit + integration + E2E + accessibility |
| M2 MacBook Pro 14" (2022) | Apple M2 Pro | 14.7 Sonoma | Built-in 14.2" Retina + external 4K monitor | **P0** | Full unit + integration + E2E + performance benchmarks |
| M3 Mac mini (2023) | Apple M3 | 15.0 Sequoia | External 27" 5K display (Thunderbolt) | **P0** | Full unit + integration + E2E + performance benchmarks |
| M4 Mac mini (2024) | Apple M4 | 15.x Sequoia (latest) | External 4K display | **P1** | Smoke: launch + login + inventory + OCR upload |
| M1 Pro MacBook Pro 14" (2021) | Apple M1 Pro | 14.x Sonoma | Built-in notched display (3024×1964) | **P1** | Notch-specific layout + full E2E |
| Intel iMac 2020 (Rosetta 2) | Intel Core i7 + Rosetta 2 | 13.x Ventura | Built-in 27" 5K (5120×2880) | **P2 — v1.1** | Smoke only: launch + login + cold-start timer |

**P0 rationale**: Every P0 machine tests a different generation of Apple Silicon on a different macOS major version. Together they cover: the minimum OS (13 Ventura), the current LTS OS (14 Sonoma), and the latest OS (15 Sequoia). The M1 baseline sets the official performance benchmark for §2.6 AC-01. The M2 Pro validates multi-display layout. The M3 Mac mini tests a headless-server-adjacent use case where the display is entirely external.

**Notch coverage (P1)**: The M1 Pro 14" notched display must receive dedicated testing for: full-screen layout under the notch, menu bar visibility, toolbar item ordering when the notch narrows the menu bar, and the OCR Upload floating panel positioning.

**Intel / Rosetta 2 (P2)**: The Rosetta 2 arm64-on-x86_64 path is officially a v1.1 stretch goal (§2.1). Smoke testing on P2 machines validates that no arm64-specific assembly or SIMD intrinsics were inadvertently compiled in. The test run uses the same arm64 `.app` slice opened under Rosetta 2 (no universal binary in v1.0).

---

### 6.2 UNIT TESTS — COMPONENTS

Framework: **XCTest** (unit test target `LocalOCRTests`). Component tests use `ViewInspector` (swift-view-inspector) for structural assertions where needed, but prefer `XCTest` `@MainActor` host-based rendering with `@testable import LocalOCR` for state inspection. Mock API responses are injected via a `URLProtocol` subclass (`MockURLProtocol`) registered on the test `URLSessionConfiguration`.

Each row below maps directly to the five required tests listed in §5.1 for each component. Test IDs are prefixed `UC-` (Unit Component).

| Component | Test ID | Test Case | Input / Setup | Expected Outcome | Pass Condition |
|---|---|---|---|---|---|
| **Card** | UC-001 | Renders with default padding and corner radius | `Card { Text("Hello") }` | View tree contains `RoundedRectangle` with cornerRadius 10 and padding 16 | View compiles and renders without error; cornerRadius property equals 10 |
| **Card** | UC-002 | Shadow increases on hover | Set `isHovered = true` via simulated `.onHover` | Shadow radius increases from 0 to 4 | `@State isHovered` transition animation is present; shadow modifier value ≠ 0 when hovered |
| **Card** | UC-003 | Content ViewBuilder renders child views | Pass `VStack { Text("A"); Text("B") }` as content | Both `Text("A")` and `Text("B")` appear in rendered tree | ViewInspector finds both Text views as children of Card |
| **Card** | UC-004 | Correct background in light and dark mode | Render Card with `colorScheme: .dark` and `colorScheme: .light` | Background resolves to `Color.surface` in both modes | `Color.surface` has non-nil NSColor representation in both color schemes |
| **Card** | UC-005 | VoiceOver children individually traversable | Card with two Button children | `.accessibilityElement(children: .contain)` set; VoiceOver can reach each child | Accessibility tree has children; Card itself has no blocking `.accessibilityElement(children: .ignore)` |
| **Badge** | UC-006 | Text renders inside a capsule shape | `Badge(text: "New", color: .successDim, textColor: .success)` | Text "New" is visible inside a Capsule background | ViewInspector finds Text "New" inside Capsule fill; text is not clipped |
| **Badge** | UC-007 | Custom color applied to background and foreground | `Badge(text: "!!", color: .warningDim, textColor: .warning)` | Background fills with `warningDim`, text foreground is `warning` | Color properties on capsule fill and text foreground match the passed parameters |
| **Badge** | UC-008 | Default font is `.caption` | `Badge(text: "OK", color: .successDim, textColor: .success)` (no fontSize override) | Text font resolves to `.caption` | Font modifier on Text equals `Font.caption` |
| **Badge** | UC-009 | Accessibility label matches `text` parameter | `Badge(text: "Low", ...)` | `.accessibilityLabel` equals "Low" | `accessibilityLabel` attribute on view equals the `text` parameter string |
| **Badge** | UC-010 | Renders in dark mode without clipping | Render with `.environment(\.colorScheme, .dark)` | Capsule fill and text visible; no frame overflow | View bounds contain all subviews; no negative overflow measured |
| **LowStockPill** | UC-011 | `.inStock` state renders with zero opacity | `LowStockPill(state: .inStock, count: nil)` | View opacity is 0 | `.opacity(0)` modifier present on the view when state is `.inStock` |
| **LowStockPill** | UC-012 | `.low` state renders amber pill with "Low" text | `LowStockPill(state: .low, count: nil)` | Capsule background is `Color.warningDim`; text reads "Low" | Capsule fill color equals `warningDim`; Text content is "Low" |
| **LowStockPill** | UC-013 | `.out` state renders red pill with "Out" text | `LowStockPill(state: .out, count: nil)` | Capsule background is `Color.errorDim`; text reads "Out" | Capsule fill color equals `errorDim`; Text content is "Out" |
| **LowStockPill** | UC-014 | `.manualLow` state renders with dashed border | `LowStockPill(state: .manualLow, count: nil)` | Capsule has a dashed 1pt stroke in `Color.warning` | Overlay or stroke on Capsule uses dashed style; border color is `Color.warning` |
| **LowStockPill** | UC-015 | Accessibility label matches stock state | `LowStockPill(state: .low, count: 2)` | `.accessibilityLabel` is "Low stock" | `accessibilityLabel` attribute resolves to the correct per-state string |
| **CategoryChip** | UC-016 | Selected state fills with accent color | `CategoryChip(label: "Dairy", isSelected: true, isInteractive: true, action: nil)` | Background fill is `Color.accentDim`, stroke is `Color.accent` | Fill and stroke color values match the selected-state tokens from §5.1 |
| **CategoryChip** | UC-017 | Non-interactive chip has no tap gesture | `CategoryChip(label: "Dairy", isSelected: false, isInteractive: false, action: nil)` | Simulated tap fires no callback | `action` is nil; no `onTapGesture` modifier attached when `isInteractive = false` |
| **CategoryChip** | UC-018 | `action` fires on `Space` key when focused | `CategoryChip` with `isInteractive: true` and spy `action` closure | Simulate `.keyPress(.space)` → spy fires once | `action` is called exactly once; no duplicate calls |
| **CategoryChip** | UC-019 | Accessibility traits include `.isSelected` when selected | `CategoryChip(label: "X", isSelected: true, isInteractive: true, action: {})` | Traits include `.isButton` and `.isSelected` | `.accessibilityAddTraits` set includes both `.isButton` and `.isSelected` |
| **CategoryChip** | UC-020 | Renders correctly in dark mode | `CategoryChip` rendered with `.environment(\.colorScheme, .dark)` | Border and label colors resolve to dark-mode token values | No NSColor resolution failure; `Color.border` dark-mode variant has non-nil representation |
| **KeyValueRow** | UC-021 | Key is secondary color, value is primary | `KeyValueRow(key: "Store", value: "Costco")` | Key text foreground is `Color.secondaryLabel`; value foreground is `Color.primary` | Text modifiers on key and value match their respective token colors |
| **KeyValueRow** | UC-022 | Currency flag applies monospaced font to value | `KeyValueRow(key: "Total", value: "$42.50", isCurrency: true)` | Value Text uses `.monoBody` font variant | Font modifier on value Text equals `.monoBody` (body + monospaced) |
| **KeyValueRow** | UC-023 | `valueColor` override sets value foreground | `KeyValueRow(key: "Status", value: "Paid", valueColor: .success)` | Value foreground is `Color.success` | Text foreground color on value equals `Color.success` |
| **KeyValueRow** | UC-024 | Accessibility combines key and value in label | `KeyValueRow(key: "Date", value: "2026-05-19")` | `.accessibilityLabel` equals "Date: 2026-05-19" | `accessibilityElement(children: .combine)` is set; combined label matches expected string |
| **KeyValueRow** | UC-025 | Spacer pushes key and value to opposite edges | `KeyValueRow(key: "A", value: "B")` rendered in 400pt-wide HStack | Key is left-aligned; value is right-aligned | `Spacer()` is present between key and value in the HStack |
| **DropZone** | UC-026 | `isDragOver` changes dashed border to solid accent | Simulate `.onDrop` hover with valid UTType PDF item | Border transitions from dashed to solid `Color.accent` 2pt stroke | `isDragOver` state equals `true`; stroke style is `.solid`; stroke color is `Color.accent` |
| **DropZone** | UC-027 | Invalid file type sets `isDragInvalid` with red border | Simulate `.onDrop` hover with `.docx` UTType (not in accepted list) | Border color is red; `isDragInvalid = true` | `isDragInvalid` state equals `true`; stroke color is `Color.error` |
| **DropZone** | UC-028 | `onFilesDropped` called only for valid UTTypes | Drop `.pdf` file — expect callback; drop `.docx` — expect no callback | Callback fires for PDF; no callback for docx | Spy `onFilesDropped` called exactly once for PDF drop; not called for docx drop |
| **DropZone** | UC-029 | Tapping fires `onBrowse` | Simulate `.onTapGesture` on DropZone | `onBrowse` spy closure is called | Spy `onBrowse` called exactly once |
| **DropZone** | UC-030 | `isProcessing = true` shows ProgressView and disables drop | `DropZone(isProcessing: true, ...)` | `ProgressView` is present in view tree; `.onDrop` handler returns `false` | ViewInspector finds `ProgressView`; drop validation returns false when processing |
| **ReceiptThumbnail** | UC-031 | Renders shimmer skeleton when loading | `ReceiptThumbnail(url: URL(string: "http://localhost:8090/receipts/1/image"))` before response arrives | `SkeletonView` placeholder is visible | ViewInspector finds `SkeletonView` before KFImage resolves |
| **ReceiptThumbnail** | UC-032 | Renders broken-image icon on failure | `ReceiptThumbnail(url: nil)` or inject failing URLSession mock | `Image(systemName: "photo.fill")` visible | `loadFailed` state is `true`; SF Symbol name is "photo.fill" |
| **ReceiptThumbnail** | UC-033 | Image clipped to rounded rectangle | Rendered `ReceiptThumbnail` at default size | Clip shape is `RoundedRectangle(cornerRadius: 4)` | `.clipShape(RoundedRectangle(cornerRadius: 4))` present in view modifier chain |
| **ReceiptThumbnail** | UC-034 | Size parameter controls width and height | `ReceiptThumbnail(url: nil, size: 72)` | Frame is 72×72 pt | `.frame(width: 72, height: 72)` set on the view |
| **ReceiptThumbnail** | UC-035 | Cookie header attached to image request | Inject `MockURLProtocol`; capture request headers | `Cookie:` header or equivalent cookie storage cookie is present | `HTTPCookieStorage.shared` contains a session cookie; URLRequest has `httpShouldHandleCookies = true` |
| **EmptyStateView** | UC-036 | Renders SF Symbol at 48pt | `EmptyStateView(systemImage: "cart.circle", title: "T", subtitle: "S")` | `Image(systemName: "cart.circle")` with 48pt font size present | ViewInspector finds Image with `system(size: 48)` font modifier |
| **EmptyStateView** | UC-037 | CTA button absent when `ctaLabel = nil` | `EmptyStateView(systemImage: "X", title: "T", subtitle: "S", ctaLabel: nil)` | No `PrimaryButton` in view tree | ViewInspector finds no Button child with label-based role |
| **EmptyStateView** | UC-038 | Secondary CTA rendered as SecondaryButton | `EmptyStateView` with both `ctaLabel` and `secondaryCtaLabel` set | Secondary button is present as a `SecondaryButton` (bordered style) | Second Button child in VStack uses `.bordered` button style |
| **EmptyStateView** | UC-039 | `ctaAction` fires on button tap | `EmptyStateView` with spy `ctaAction` | Simulated tap on CTA fires spy | Spy called exactly once on button tap |
| **EmptyStateView** | UC-040 | Accessibility label combines title and subtitle | `EmptyStateView(title: "No items", subtitle: "Upload a receipt")` | `.accessibilityLabel` equals "No items. Upload a receipt" | `accessibilityElement(children: .combine)` set; combined label matches |
| **SkeletonView** | UC-041 | Animation starts on appear | `SkeletonView()` in test host | `phase` changes from 0 to 1 on `.onAppear` | Phase animation fires; `withAnimation` block executed on appear |
| **SkeletonView** | UC-042 | `accessibilityReduceMotion = true` renders static block | `SkeletonView().environment(\.accessibilityReduceMotion, true)` | No gradient animation; static `Color.surface2` fill | `LinearGradient` animation is not active; background is static surface2 |
| **SkeletonView** | UC-043 | Width clamps to full available width when `width = nil` | `SkeletonView(width: nil)` in a 300pt container | Frame `maxWidth = .infinity` | `.frame(maxWidth: .infinity)` in view modifier chain |
| **SkeletonView** | UC-044 | Corner radius applied correctly | `SkeletonView(cornerRadius: 8)` | `RoundedRectangle(cornerRadius: 8)` is the clip/fill shape | Shape cornerRadius equals 8 |
| **SkeletonView** | UC-045 | Accessibility label is "Loading" | `SkeletonView()` | `.accessibilityLabel` equals "Loading" | `accessibilityLabel` attribute equals "Loading" string |
| **ProgressBarView** | UC-046 | Fill color is green when ratio < 0.80 | `ProgressBarView(value: 50, maximum: 100)` (ratio = 0.50) | Fill `Capsule` uses `Color.success` | Fill capsule foreground color equals `Color.success` |
| **ProgressBarView** | UC-047 | Fill color is amber when 0.80 ≤ ratio < 0.95 | `ProgressBarView(value: 88, maximum: 100)` | Fill uses `Color.warning` | Fill capsule foreground color equals `Color.warning` |
| **ProgressBarView** | UC-048 | Fill color is red when ratio ≥ 0.95 | `ProgressBarView(value: 97, maximum: 100)` | Fill uses `Color.error` | Fill capsule foreground color equals `Color.error` |
| **ProgressBarView** | UC-049 | Animated spring transition on value change | `ProgressBarView(value: 20, maximum: 100)` → update to `value: 80` | `displayedRatio` animated via spring from 0.20 to 0.80 | `withAnimation(.spring(...))` block wraps the `displayedRatio` assignment |
| **ProgressBarView** | UC-050 | Accessibility value reflects numeric values | `ProgressBarView(value: 3, maximum: 5)` | `.accessibilityValue` equals "3 of 5" | `accessibilityValue` attribute equals "3 of 5" |
| **Toast** | UC-051 | Toast appears with slide-from-top transition | Present `Toast` via `ToastHost` | View slides in from top; `.transition(.move(edge: .top).combined(with: .opacity))` fires | `isVisible` transitions to `true`; transition modifier is present |
| **Toast** | UC-052 | Auto-dismisses after `duration` seconds | `Toast(message: "X", severity: .info, duration: 0.1, onDismiss: spy)` | `onDismiss` spy fires after ≥ 0.1 seconds | Spy called within 200ms of view appearing; not called before 100ms |
| **Toast** | UC-053 | `×` button calls `onDismiss` | Simulate tap on dismiss button | `onDismiss` spy fires immediately | Spy called once on button tap |
| **Toast** | UC-054 | Severity affects background color | `Toast(severity: .warning, ...)` vs `Toast(severity: .error, ...)` | Warning background is `warningDim`; error background is `errorDim` | Background fill color values differ between severity variants |
| **Toast** | UC-055 | VoiceOver announcement posted on appear | `Toast` appears in view hierarchy | `UIAccessibility.post(notification: .announcement, argument: message)` fires | Notification post call is made with the message string |
| **SankeyWebView** | UC-056 | Loads `sankey-template.html` from app bundle | `SankeyWebView(data: emptySankeyData)` | WKWebView load request uses bundle URL for `sankey-template.html` | URL loaded by WKWebView equals `Bundle.main.url(forResource: "sankey-template", withExtension: "html")` |
| **SankeyWebView** | UC-057 | Injects data via `setSankeyData` on data change | Change `data` binding after initial load | `evaluateJavaScript("window.setSankeyData(…)")` called | JavaScript evaluation is called with non-empty JSON string when `data` changes |
| **SankeyWebView** | UC-058 | Shows `ProgressView` while loading | `SankeyWebView` before `webView(_:didFinish:)` fires | `ProgressView` visible in overlay | `isLoaded = false` until navigation completes; `ProgressView` present when `!isLoaded` |
| **SankeyWebView** | UC-059 | Shows error `EmptyStateView` on navigation failure | Inject `WKNavigationDelegate` error | `EmptyStateView` with retry button replaces chart | `onError` callback fires; `EmptyStateView` is present in view tree |
| **SankeyWebView** | UC-060 | Respects `prefers-color-scheme` from system appearance | Set `.environment(\.colorScheme, .dark)` | WKWebView `customUserAgent` or `appearanceProxy` reflects dark preference | `WKWebView.underPageBackgroundColor` or equivalent dark-mode API is set |
| **InlineEditableCell** | UC-061 | Double-tap enters editing mode | Double-tap `.onTapGesture(count: 2)` on display Text | `isLocallyEditing = true`; TextField replaces Text | `isLocallyEditing` state is `true` after double-tap; `TextField` is present |
| **InlineEditableCell** | UC-062 | Return calls `onCommit` with current edit text | Enter editing mode, type "NewName", press Return | `onCommit("NewName")` fires | Spy `onCommit` called with "NewName" |
| **InlineEditableCell** | UC-063 | Esc calls `onCancel` and restores original text | Enter editing mode, type "NewName", press Esc | `onCancel` fires; `text` binding reverts to original | Spy `onCancel` called; text binding shows original value |
| **InlineEditableCell** | UC-064 | Hover shows underline hint | Simulate `.onHover(true)` while not editing | Text receives `.underline(true, color: .tertiaryLabel)` | Underline modifier is present when `isHovered = true` and `!isLocallyEditing` |
| **InlineEditableCell** | UC-065 | `isLocallyEditing = true` renders TextField, not Text | Force `isEditing: true` via external binding | `TextField` is the root view; `Text` is absent | ViewInspector finds `TextField`; `Text` not present in non-editing path |
| **ContextMenuModifiers** | UC-066 | Receipt context menu shows all §3.5 items | Right-click on view with `.receiptRowContextMenu` | Context menu has 6 items: Open, Re-run OCR, separator, Copy Store, Copy Total, separator, Mark Reviewed, Export, separator, Delete | All §3.5 items found in context menu inspection |
| **ContextMenuModifiers** | UC-067 | Destructive button uses `.destructive` role | Inspect Delete item in receipt context menu | Button role is `.destructive` (red on macOS 14+) | `Button(role: .destructive)` used for destructive items |
| **ContextMenuModifiers** | UC-068 | Admin-only items absent when non-admin no-op passed | Pass empty closure for `onDelete` in non-admin context | Delete item is absent from menu | Context menu item count is one fewer; no "Delete" label found |
| **ContextMenuModifiers** | UC-069 | Correct action fires for each item | Tap each context menu item | Corresponding spy closure fires once per item | Each spy called exactly once on item selection; no cross-firing |
| **ContextMenuModifiers** | UC-070 | Context menu appears on right-click | Simulate right-click (`NSEvent.rightMouseDown`) | Context menu is presented | `contextMenu` modifier is present; simulated right-click triggers presentation |
| **AttributionPicker** | UC-071 | Three options render as radio-button-style rows | `AttributionPicker(selection: .household, users: [], splitUserIds: .constant([]), onSave: {}, onSkip: {})` | Three HStack radio rows present: Household, Personal, Split | Three selectable option rows found in view tree |
| **AttributionPicker** | UC-072 | `.split` selection reveals member checkboxes | Set `selection = .split` | Member checkboxes become visible | Checkboxes present only when `selection == .split` |
| **AttributionPicker** | UC-073 | `⌘Return` fires `onSave` | Bind `⌘Return` shortcut; simulate keypress | `onSave` spy fires | `keyboardShortcut(.return, modifiers: .command)` triggers spy |
| **AttributionPicker** | UC-074 | `onSkip` fires on "Skip for now" | Tap "Skip for now" button | `onSkip` spy fires | Spy called exactly once |
| **AttributionPicker** | UC-075 | Accessibility role is `.radioButton` on each option | Inspect accessibility traits on each option row | Each row has `.accessibilityRole(.radioButton)` | `accessibilityRole` returns `.radioButton` for all three option rows |
| **QRCodeView** | UC-076 | Fetches QR PNG from correct API path | `QRCodeView(endpoint: .loginQR, size: 200, onCopyLink: nil)` with MockURLProtocol | URLRequest URL contains `/auth/qr-image` | Captured request URL path equals `"/auth/qr-image"` |
| **QRCodeView** | UC-077 | Falls back to CIFilter on fetch failure | Inject MockURLProtocol returning 500 | `CIQRCodeGenerator` filter called; QR image rendered locally | `CIFilter(name: "CIQRCodeGenerator")` is invoked; `qrImage` state is non-nil |
| **QRCodeView** | UC-078 | "Copy Link" copies URL to `NSPasteboard` | Tap "Copy Link" button | `NSPasteboard.general.string(forType: .string)` equals the share URL | Pasteboard string matches the QR link URL |
| **QRCodeView** | UC-079 | Shows `SkeletonView` while loading | Before MockURLProtocol responds | `SkeletonView` present in view tree | `isLoading = true`; `SkeletonView` found |
| **QRCodeView** | UC-080 | Accessibility label includes endpoint context | `QRCodeView(endpoint: .loginQR, ...)` | `.accessibilityLabel` contains "login" | Accessibility label string contains "login" |
| **ModelPicker** | UC-081 | Renders all enabled models from `models` array | `ModelPicker(selectedModelId: .constant(nil), models: [m1, m2, m3])` | Three Picker options present | `Picker` has exactly three `ForEach` items |
| **ModelPicker** | UC-082 | Locked models are disabled | Pass model with user lacking access (simulate `isLocked = true`) | Model label contains "(Locked)"; item is `.disabled(true)` | Disabled modifier set on locked model option; label text contains "Locked" |
| **ModelPicker** | UC-083 | `selectedModelId` binding updates on selection | Simulate Picker selection change to `modelId = 5` | Binding value becomes `5` | `selectedModelId` equals `5` after selection |
| **ModelPicker** | UC-084 | Empty models array shows disabled "No models configured" | `ModelPicker(selectedModelId: .constant(nil), models: [])` | Picker shows "No models configured" and is disabled | Picker label is "No models configured"; `.disabled(true)` modifier present |
| **ModelPicker** | UC-085 | Accessibility label is "AI model selector" | Inspect accessibility label | `.accessibilityLabel` equals "AI model selector" | `accessibilityLabel` attribute equals "AI model selector" |
| **DemoModeBanner** | UC-086 | Always renders when demo mode is active; cannot be dismissed | `DemoModeBanner` with `isDemoMode = true`; no close button | No dismiss button present; banner fully visible | ViewInspector finds no dismiss/close button in DemoModeBanner |
| **DemoModeBanner** | UC-087 | `onSignIn` fires on button tap and `Return` when focused | Spy closure for `onSignIn`; simulate button tap and focused Return | Spy fires on each trigger | Spy called once on tap; called once on Return keypress when button focused |
| **DemoModeBanner** | UC-088 | Background color is `Color.warningDim` | Inspect banner background | Background fill equals `Color.warningDim` | Background modifier color matches `warningDim` token |
| **DemoModeBanner** | UC-089 | Eye icon is present | Inspect view tree | `Image(systemName: "eye.fill")` present | SF Symbol name "eye.fill" found in view tree |
| **DemoModeBanner** | UC-090 | Accessibility label includes full message | Inspect accessibility label | Label contains "Demo Mode: read only. Sign in to save changes." | `accessibilityLabel` attribute equals the full expected string |

**Notes on component test infrastructure:**
- All 90 component tests reside in `LocalOCRTests/ComponentTests/` with one file per component (e.g. `CardTests.swift`, `BadgeTests.swift`).
- `MockURLProtocol` is defined in `LocalOCRTests/Helpers/MockURLProtocol.swift` and registered on a test-only `URLSessionConfiguration`.
- State inspection is performed via `@testable import LocalOCR` and reflection on `@State`/`@Binding` variables accessed through the test host view.
- Dark mode tests inject `.environment(\.colorScheme, .dark)` on the test host.
- All component tests are annotated `@MainActor` to avoid Swift concurrency warnings.

---

### 6.3 INTEGRATION TESTS — VIEWS

Framework: **XCTest** with `@MainActor` view hosting + `MockURLProtocol`. Each view test instantiates the full view with injected state objects and a mock API layer. The mock API serves pre-canned JSON fixtures from `LocalOCRTests/Fixtures/`. Test IDs are prefixed `IV-` (Integration View). Source views are from §5.2 (18 views total — 16 MVP views + MenuBarPopoverView + DemoModeOverlay).

| View | Test ID | Scenario | Setup State | User Actions | Expected Result | Pass Condition |
|---|---|---|---|---|---|---|
| **LoginView** | IV-001 | Valid credentials → dashboard | `AuthState.state = .unauthenticated`; mock `/auth/login` returns 200 + cookie; mock `/auth/me` returns user fixture | Populate email + password, tap Sign In | `AuthState.state` transitions to `.authenticated`; `MainSplitView` replaces `LoginView` | `AuthState.currentUser` is non-nil; view tree switches to `MainSplitView` |
| **LoginView** | IV-002 | Invalid credentials show inline error | Mock `/auth/login` returns 401 | Populate email + wrong password, tap Sign In | Red error text visible below password field; no navigation occurs | Error `Text` visible with `.systemRed` foreground; `AuthState.state` remains `.unauthenticated` |
| **LoginView** | IV-003 | "Try Demo" sets demo mode without API call | MockURLProtocol intercepts all requests | Tap "Try Demo" | `AppState.isDemoMode = true`; no network request made | `isDemoMode` is `true`; `MockURLProtocol` recorded zero requests for `/auth/login` |
| **LoginView** | IV-004 | Return in email field moves focus to password | `LoginView` with `@FocusState` bindings | Press Return in email field | Password field becomes focused | `focusedField == .password` after Return keypress in email field |
| **LoginView** | IV-005 | Server URL change validates before accepting | Mock `/auth/config` returns 200 with valid server info | Change server URL to `http://192.168.1.50:8090`; tap Connect | `PreferencesStore.apiBaseURL` updates; success confirmation shown | `PreferencesStore.apiBaseURL` equals new URL; no error toast |
| **DashboardView** | IV-006 | Six skeleton cards shown during loading | `AuthState.state = .authenticated`; MockURLProtocol delays 200ms | Navigate to Dashboard immediately on auth | Six `SkeletonView` cards visible before data arrives | `SkeletonView` count in view tree equals 6 during loading window |
| **DashboardView** | IV-007 | Attribution nudge banner when unattributed receipts exist | Mock `/receipts?status=unreviewed` returns 3 items with `attribution_user_id = null` | Navigate to Dashboard; data loads | Attribution nudge banner visible with count "3 receipts need attribution" | `AttributionNudgeBanner` is present and visible; count label shows 3 |
| **DashboardView** | IV-008 | Tile CTA navigates to correct screen | Mock all dashboard data endpoints; `InventoryState.lowStockCount = 5` | Tap "View Inventory" on Low Stock tile | `Router.activeDestination` becomes `.inventory`; `InventoryView` appears | `router.activeDestination == .inventory` |
| **DashboardView** | IV-009 | Dropped receipt file opens OCR Upload sheet | `DashboardView` rendered; inject `ReceiptDropDelegate` | Simulate drop of `sample-receipt.pdf` onto content area | `OCRUploadView` sheet presented with `selectedFileURL` pre-filled | `OCRUploadView` sheet is visible; `AppState.pendingUploadURL` equals the dropped file URL |
| **DashboardView** | IV-010 | `⌘R` triggers data refresh | Dashboard loaded with initial data; spy on data-fetch methods | Press `⌘R` | All six tile data-fetch methods called | `DashboardState.refresh()` called; `MockURLProtocol` records fresh requests for all six endpoints |
| **OCRUploadView** | IV-011 | Run OCR button disabled until file selected | `OCRUploadView` with no file | No file selected | "Run OCR" button is disabled | Button `.isEnabled` is `false`; `selectedFileURL == nil` |
| **OCRUploadView** | IV-012 | Drop valid PDF enables Run OCR | Drop `sample-receipt.pdf` onto DropZone | File dropped | Button becomes enabled; filename shown in DropZone | `selectedFileURL` is non-nil; button `.isEnabled` is `true` |
| **OCRUploadView** | IV-013 | Model picker shows enabled models | Mock `/ai-models` returns 3 models: Gemini, GPT-4o, Claude | Navigate to OCRUploadView | ModelPicker has 3 options | `ModelPicker.models.count == 3` |
| **OCRUploadView** | IV-014 | OCR success transitions to ReceiptReviewView | Mock `POST /receipts/upload` returns receipt fixture with 5 line items | Select file, choose model, tap "Run OCR" | `ReceiptReviewView` presented with 5 line items | `ReceiptReviewView` is visible; `lineItems.count == 5` |
| **OCRUploadView** | IV-015 | OCR failure shows error toast with model name | Mock `POST /receipts/upload` returns 500 | Submit OCR | Error toast visible with model name in message | Toast with `.error` severity is present; toast message contains model name |
| **ReceiptReviewView** | IV-016 | Line items list populated from OCR result | Inject `ReceiptsState` with 5-item receipt fixture | Navigate to `ReceiptReviewView` | Five line item rows visible | List row count equals 5 |
| **ReceiptReviewView** | IV-017 | Inline edit of line item calls PATCH | Mock `PATCH /receipts/<id>/items/<item_id>`; inject receipt with one editable item | Double-click item name, type new name, press Return | PATCH request sent with updated name | `MockURLProtocol` records PATCH to item endpoint with new name in body |
| **ReceiptReviewView** | IV-018 | Confirm Receipt calls POST confirm endpoint | Mock `POST /receipts/<id>/confirm`; inject reviewed receipt | Tap "Confirm Receipt" | POST fires; AttributionPicker sheet presented | `MockURLProtocol` records POST; `AttributionPicker` sheet visible |
| **ReceiptReviewView** | IV-019 | Diff mode marks new items green, removed items strikethrough | Inject diff with 2 new items, 1 removed item from Re-run OCR | Navigate to diff mode | New items have green badge; removed item has strikethrough | `Badge("NEW")` present on 2 rows; strikethrough modifier on 1 row |
| **ReceiptReviewView** | IV-020 | Attribution picker writes correct fields | Mock `POST /receipts/<id>/attribution`; inject post-confirm flow | Select "Personal" attribution, tap Save | POST body contains `attribution_kind: "personal"` | Request body decoded as `{ attribution_kind: "personal", attribution_user_id: <current user id> }` |
| **InventoryView** | IV-021 | Search filters list by product name | Inject 10 inventory items with varied names | Type "milk" in search field | Only items with "milk" in name visible | Visible row count equals number of items matching "milk" |
| **InventoryView** | IV-022 | Low-stock filter chip shows only low items | Inject items with 3 low-stock (`quantity ≤ threshold`), 7 normal | Tap "Low Stock" filter chip | 3 rows visible | Visible row count equals 3; chip shows selected state |
| **InventoryView** | IV-023 | `⌥↑` increments quantity and calls PATCH | Mock `PATCH /inventory/<id>`; inject item with quantity=2 | Select item row, press `⌥↑` | Quantity shows 3; PATCH fires with `quantity_delta: 1` | Row quantity label equals "3"; `MockURLProtocol` records PATCH with correct body |
| **InventoryView** | IV-024 | `⌘L` adds item to shopping list | Mock `POST /shopping`; inject item | Select inventory row, press `⌘L` | POST fires; toast "Added to shopping list" visible | `MockURLProtocol` records POST to shopping endpoint; success toast present |
| **InventoryView** | IV-025 | Category sidebar filters to correct category | Inject items across 3 categories | Click "Dairy" in category sidebar | Only Dairy items visible in product list | Visible row categories all equal "Dairy" |
| **ShoppingListView** | IV-026 | Checkbox Space toggle marks item purchased | Inject 3 open shopping items; mock `PATCH /shopping/<id>` | Select first row, press Space | Row shows strikethrough; PATCH fires with `status: "purchased"` | Row strikethrough visible; PATCH recorded with `{ status: "purchased" }` |
| **ShoppingListView** | IV-027 | Auto-populate button adds low-stock items | Mock `POST /shopping/populate-from-recs` returning 5 new items | Tap auto-populate button (`⌥⌘P`) | 5 new rows added to list | `ShoppingState.items.count` increases by 5; POST recorded |
| **ShoppingListView** | IV-028 | QR share button shows QR code | Mock `/auth/qr-image` returning PNG data | Tap QR Share button (`⌘⇧S`) | `ShareQRView` sheet presented with QR image | `ShareQRView` is visible; QRCodeView renders |
| **ShoppingListView** | IV-029 | Recommendations tab shows low-stock recommendations | Mock `/recommendations` returning 4 items | Switch to Recommendations tab | 4 recommendation rows visible | Row count equals 4; tab indicator shows "Recommendations" label |
| **ShoppingListView** | IV-030 | `⌘N` adds blank row inline | `ShoppingListView` with empty list | Press `⌘N` | New editable row appears at bottom of list | `ShoppingState.items.count` increases by 1; new row is in edit mode |
| **FixedBillsView** | IV-031 | Bills list loads with paid/unpaid status | Mock `/obligations` returning 3 paid, 2 unpaid | Navigate to Fixed Bills | 5 rows visible; 3 green "Paid", 2 amber "Unpaid" | Row count equals 5; status badges match data |
| **FixedBillsView** | IV-032 | Space toggles bill paid/unpaid | Mock `PATCH /obligations/<id>`; inject 1 unpaid bill | Select unpaid row, press Space | Row switches to "Paid" state; PATCH fires | Row status badge changes to "Paid"; PATCH recorded with `{ payment_status: "paid" }` |
| **FixedBillsView** | IV-033 | F2 enters inline rename | Inject obligation named "Netflix"; mock `PATCH /obligations/<id>` | Select row, press F2 | `InlineEditableCell` enters edit mode for that row | `isLocallyEditing = true` for the selected row |
| **FixedBillsView** | IV-034 | Cadence badge shows "Not due this month" for non-billing months | Inject quarterly bill with last billing month 3 months ago | Navigate to Fixed Bills | Row shows "Not due this month" cadence badge | Cadence badge text matches "Not due this month" per §1.7 rule 5 |
| **FixedBillsView** | IV-035 | `⌘N` opens Add Obligation sheet | `FixedBillsView` loaded | Press `⌘N` | Add Obligation form sheet presented | Sheet with obligation name and amount fields is visible |
| **PlaidAccountsView** | IV-036 | Accounts section shows account rows with status | Mock `/plaid/items` + `/plaid/accounts` returning 2 accounts (1 active, 1 login_required) | Navigate to Plaid Integration | 2 account rows; 1 "Active" badge, 1 amber "Login Required" badge | Account rows count equals 2; badge labels match |
| **PlaidAccountsView** | IV-037 | Return confirms staged transaction | Mock `POST /plaid/staged-transactions/<id>/confirm`; inject 3 staged transactions | Select first staged row, press Return | POST fires; row removed from list | `MockURLProtocol` records POST; `FinanceState.stagedTransactions.count` decreases by 1 |
| **PlaidAccountsView** | IV-038 | Delete dismisses staged transaction with confirmation | Mock `POST /plaid/staged-transactions/<id>/dismiss`; inject 1 staged transaction | Select row, press Delete | Confirmation alert presented | Confirmation sheet visible before dismissal fires |
| **PlaidAccountsView** | IV-039 | "Add Bank Account" hidden for non-admin users | `AuthState.currentUser.role = "user"` | Navigate to Plaid Integration | "Add Bank Account" button absent | Button with label "Add Bank Account" not found in view tree |
| **PlaidAccountsView** | IV-040 | Login-required account shows re-auth CTA | Inject account with `status: .loginRequired` | Navigate to Plaid Integration | Amber badge "Login Required ⚠" with tap-to-reauthenticate action | Badge text contains "Login Required"; tap triggers `ASWebAuthenticationSession` |
| **CashTransactionsView** | IV-041 | Quick-entry form submits on `⌘Return` | Mock `POST /cash-transactions`; inject valid form data | Fill amount "42.50", description "Coffee", press `⌘Return` | POST fires with correct body; success toast visible | POST recorded with `{ amount: 42.50, description: "Coffee" }`; toast present |
| **CashTransactionsView** | IV-042 | Amount validation rejects non-numeric | Leave amount field empty | Tap "Log Cash Spend" | Inline validation error appears on amount field | Error text visible on amount field; POST not fired |
| **CashTransactionsView** | IV-043 | History list groups by month | Mock `/cash-transactions` returning 6 transactions across 3 months | Navigate to Cash Transactions | 3 section headers visible; 6 total rows | Section header count equals 3; total row count equals 6 |
| **CashTransactionsView** | IV-044 | Delete swipe fires with undo | Mock `DELETE /cash-transactions/<id>`; inject 1 transaction | Trailing swipe on row → tap Delete | DELETE fires; undo action available | `MockURLProtocol` records DELETE; `UndoManager` has one undo action |
| **CashTransactionsView** | IV-045 | Month navigation arrows update visible data | Mock 2-month responses; inject May and June data | Press `>` arrow | June transactions appear; May section disappears | Visible section header changes to "June 2026" |
| **SpendingByCategoryView** | IV-046 | Category rows load from analytics endpoint | Mock `/analytics/spending-by-category` returning 5 categories | Navigate to Spending by Category | 5 category rows visible in `OutlineGroup` | `OutlineGroup` root-level row count equals 5 |
| **SpendingByCategoryView** | IV-047 | Month navigation steps through data | Mock `/analytics/spending-by-category` for May and June | Press `>` month arrow | June data loads; "Jun 2026" shown in month label | Month label text equals "Jun 2026"; data refreshes |
| **SpendingByCategoryView** | IV-048 | Export CSV opens NSSavePanel | Mock analytics export endpoint; inject filled state | Tap "Export" / press `⌘S` | `NSSavePanel` presented with suggested filename | `NSSavePanel` visible; `nameFieldStringValue` contains "spending-" prefix |
| **SpendingByCategoryView** | IV-049 | Expanding a category row shows receipt sub-rows | Inject category with 3 receipts | Click expansion disclosure on "Groceries" row | 3 receipt sub-rows appear under Groceries | `DisclosureGroup` or `OutlineGroup` expanded rows count equals 3 |
| **SpendingByCategoryView** | IV-050 | Sankey WebView stub shows loading state (v1.1 placeholder) | `SankeyWebView` with empty data | Navigate to Sankey tab | "Sankey chart will be available in v1.1" placeholder or ProgressView | Placeholder text or ProgressView visible; no crash |
| **ContributionsView** | IV-051 | Leaderboard sorted by monthly points | Mock `/contributions` returning 3 users with 50, 20, 35 points | Navigate to Contributions | Users sorted 50 → 35 → 20 | Row order matches descending point sort |
| **ContributionsView** | IV-052 | Per-member drill-in shows event history | Mock `/contributions?user_id=<id>` returning 5 events | Tap on first leaderboard member | Detail sheet shows 5 event rows for that member | Sheet visible; row count equals 5; user name in sheet title |
| **ContributionsView** | IV-053 | Contribution event types shown with correct points | Mock events with `event_type: "receipt_processed"` (5pts) and `"ocr_cleanup"` (20pts) | Navigate to drill-in view | Points labels show "5 pts" and "20 pts" respectively | Points label text matches SCORE_RULES from §1.7 rule 7 |
| **ContributionsView** | IV-054 | Medal emoji present for top-3 positions | Mock 5 members with distinct points | Navigate to Contributions | Gold 🥇 on rank 1, Silver 🥈 on rank 2, Bronze 🥉 on rank 3 | Medal labels found at correct positions in sorted list |
| **ContributionsView** | IV-055 | Non-current month loads via month picker | Mock `/contributions?month=2026-04` returning April data | Navigate to prior month | April data appears; month label shows "April 2026" | API request includes `month=2026-04`; month label updated |
| **AuthAndMembersView** | IV-056 | Member list shows all household users with roles | Mock `/auth/users` returning 3 users (1 admin, 2 members) | Navigate to Auth and Members | 3 user rows; admin row has "Admin" badge | Row count equals 3; admin badge visible on correct row |
| **AuthAndMembersView** | IV-057 | Admin can invite new member (non-admin cannot) | `role = "admin"`: invite button visible; `role = "user"`: button hidden | Compare both role scenarios | Admin sees "Invite Member" button; member does not | Button visibility differs between roles as expected |
| **AuthAndMembersView** | IV-058 | Trusted devices listed with scope badges | Mock `/auth/trusted-devices` returning 2 devices | Navigate to Trusted Devices section | 2 device rows with scope badges (e.g. "Shared Household") | Row count equals 2; scope badge text matches device scope |
| **AuthAndMembersView** | IV-059 | QR Login code displays from server PNG | Mock `/auth/qr-image` returning valid PNG | Tap "Show My QR Code" | `QRCodeView` popover visible with loaded image | `QRCodeView` popover is visible; image loaded state |
| **AuthAndMembersView** | IV-060 | Sign Out clears Keychain and cookie storage | Mock `/auth/logout`; spy on `KeychainStore.clear()` | Tap "Sign Out"; confirm | `AuthState.state = .unauthenticated`; `HTTPCookieStorage.shared` cookies cleared | `KeychainStore.clear` spy called; `AuthState.state == .unauthenticated` |
| **SettingsView — GeneralPane** | IV-061 | Appearance toggle changes `NSApp.appearance` | `GeneralPane` loaded | Toggle "Dark" appearance | `NSApp.appearance` set to `NSAppearance(named: .darkAqua)` | `NSApp.appearance?.name == .darkAqua` |
| **SettingsView — GeneralPane** | IV-062 | Launch at login toggle calls `SMAppService.register` | `GeneralPane` with `launchAtLogin = false` | Toggle on "Launch at Login" | `SMAppService.mainApp.register()` called | `LoginItemController.isRegistered` becomes `true` |
| **SettingsView — AccountPane** | IV-063 | Server URL change writes new URL to Keychain | Mock `/auth/config` for new URL; spy on `KeychainStore.set` | Change server URL field, tap Connect | `KeychainStore` updated with new URL | `KeychainStore.set` spy called with new URL value |
| **SettingsView — NotificationsPane** | IV-064 | Nudge toggle schedules notification | Mock `UNUserNotificationCenter.requestAuthorization` granted; spy on `UNUserNotificationCenter.add` | Enable shopping nudge toggle | `UNCalendarNotificationTrigger` notification scheduled at 09:30 | `UNUserNotificationCenter.add` spy called with shopping nudge identifier |
| **SettingsView — BackupPane** | IV-065 | Backup list loaded from server | Mock `/system/backups` returning 3 backups | Navigate to Settings → Advanced → Backup | 3 backup rows visible with timestamps | Row count equals 3; backup names from fixture appear |
| **MenuBarPopoverView** | IV-066 | Low-stock count badge shows correct number | `AppState.lowStockCount = 7` | Open menu bar popover | Badge displays "7" | Badge label text equals "7" |
| **MenuBarPopoverView** | IV-067 | "Open App" button brings main window to front | Inject `AppState` with main window closed | Tap "Open App" | `NSApp.mainWindow` receives `makeKeyAndOrderFront` | Window becomes key and visible |
| **MenuBarPopoverView** | IV-068 | Quick-add cash form submits correctly | Mock `POST /cash-transactions`; fill amount + description | Tap "Quick Add Cash", fill fields, tap "Log" | POST fires with correct body; popover closes | POST recorded; popover dismissed |
| **MenuBarPopoverView** | IV-069 | "Upload Receipt" opens OCR Upload panel | `AppState.pendingUploadURL = nil` | Tap "Upload Receipt" | `OCRUploadView` panel opens | `OCRUploadView` is presented as floating NSPanel |
| **MenuBarPopoverView** | IV-070 | Last-sync timestamp shown correctly | `AppState.lastSyncDate = Date() - 300` (5 min ago) | Open menu bar popover | Last sync shows "5 minutes ago" | Timestamp label text contains "5 min" or equivalent relative format |
| **DemoModeOverlay** | IV-071 | Write actions suppressed with toast message | `AppState.isDemoMode = true`; inject write-action trigger | Trigger POST action (e.g. add shopping item) | `DemoModeError` returned; no network request made; toast shown | `MockURLProtocol` records zero POST requests; toast visible |
| **DemoModeOverlay** | IV-072 | Read actions pass through in demo mode | `AppState.isDemoMode = true` | Load inventory (GET request) | GET request fires normally; data loads | `MockURLProtocol` records GET request; inventory list populated |
| **DemoModeOverlay** | IV-073 | Yellow banner visible at all times in demo mode | `AppState.isDemoMode = true` | Navigate between Dashboard, Inventory, Shopping List | `DemoModeBanner` visible on all views | `DemoModeBanner` found in view tree on each navigation target |
| **DemoModeOverlay** | IV-074 | Sign In CTA in banner navigates to LoginView | `AppState.isDemoMode = true`; banner visible | Tap "Sign In" in `DemoModeBanner` | `AuthState.state = .unauthenticated`; `LoginView` presented | `AuthState.state == .unauthenticated`; `LoginView` visible |
| **DemoModeOverlay** | IV-075 | Demo mode disables admin-only UI elements | `AppState.isDemoMode = true`; `AuthState.currentUser.role = "admin"` | Navigate to Auth and Members | Admin actions (Invite, Revoke) disabled or show demo toast | Admin action buttons disabled; demo toast fires on tap |

**Notes on view integration test infrastructure:**
- All view integration tests reside in `LocalOCRTests/ViewTests/` with one file per view (e.g. `LoginViewTests.swift`, `DashboardViewTests.swift`).
- Fixtures in `LocalOCRTests/Fixtures/` (JSON files per endpoint): `auth_me.json`, `inventory_list.json`, `shopping_list.json`, `obligations.json`, `plaid_accounts.json`, `staged_transactions.json`, `cash_transactions.json`, `spending_analytics.json`, `contributions.json`, `receipts_list.json`, `receipt_detail.json`, `ai_models.json`.
- Each test method injects the fixture into `MockURLProtocol.responseMap[endpoint]` before instantiating the view.
- Keyboard shortcut tests use `XCUIElement.typeKey(_:modifierFlags:)` with the app's `XCUIApplication` instance.

---

### 6.4 E2E TEST SCRIPTS

Framework: **XCUITest** — Apple's official UI testing framework for macOS apps. Justification: integrated with Xcode without additional configuration, runs against the actual signed binary, supports accessibility-driven element queries via `XCUIElement` (which aligns with §2.6 AC-11 accessibility requirements), and requires no third-party dependency or external daemon.

E2E tests reside in `LocalOCRUITests/` (the existing XCUITest target `com.localocr.macosUITests`). They connect to a live backend running at `http://localhost:8090` with a seeded test database. The seeded database is populated by `LocalOCRUITests/Helpers/SeedHelper.swift`, which calls the backend's REST API before each test suite to create a deterministic starting state.

**Precondition setup pattern for all E2E tests:**
```
XCTestCase.setUp():
  1. Call SeedHelper.resetHousehold() — truncates dynamic tables; inserts fixture data
  2. Launch XCUIApplication with launchEnvironment["USE_TEST_SERVER"] = "http://localhost:8090"
  3. If test requires authenticated state: call SeedHelper.loginAPIDirectly() to pre-set the cookie
  4. app.launch()
```

---

#### E2E Script 1: Daily Inventory Walker (P0)

**Test file**: `LocalOCRUITests/DailyInventoryWalkerTests.swift`

**Precondition**: Logged-in user; seeded household with 3 low-stock items (`quantity ≤ threshold`), 5 sufficient-stock items. One active shopping session with 0 items.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | `app.launch()` | — | Main window visible; Dashboard appears | `XCTAssert(app.windows["MainWindow"].exists)` |
| 2 | Press `⌘1` | `app.typeKey("1", modifierFlags: .command)` | Inventory tab active | `app.staticTexts["Inventory"].isSelected == true` (navigation title) |
| 3 | Verify 3 low-stock pills visible | `app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Low'"))` | Count = 3 | `XCTAssertEqual(lowPills.count, 3)` |
| 4 | Verify 5 non-low rows present | `app.cells.count - lowStockCells.count` | 5 normal items | `XCTAssertEqual(normalCells.count, 5)` |
| 5 | Right-click first low-stock item | `lowCells.firstMatch.rightClick()` | Context menu appears | `app.menuItems["Add to Shopping List"].exists == true` |
| 6 | Select "Add to Shopping List" | `app.menuItems["Add to Shopping List"].click()` | Toast "Added to shopping list" appears | `app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Added to shopping list'")).firstMatch.waitForExistence(timeout: 3)` |
| 7 | Press `⌘2` | `app.typeKey("2", modifierFlags: .command)` | Shopping List tab active | Navigation title shows "Shopping" |
| 8 | Verify 1 item in shopping list | `app.cells.count` in Shopping List view | Count = 1 | `XCTAssertEqual(app.cells.count, 1)` |
| 9 | Press `⌘Q` | `app.typeKey("q", modifierFlags: .command)` | App quits cleanly | `app.state == .notRunning` within 3 seconds |

**Final assertions**: Verify via direct API call (`SeedHelper.fetchShoppingList()`) that shopping list contains exactly 1 item matching the low-stock product's `product_id`. Verify no pending writes remain in `pendingWrites.sqlite`.

---

#### E2E Script 2: Receipt Uploader (P0)

**Test file**: `LocalOCRUITests/ReceiptUploaderTests.swift`

**Precondition**: Logged-in user; no pending receipts; backend running with Gemini model configured; test fixture `LocalOCRUITests/Fixtures/sample-receipt.pdf` present (a real 2-page grocery receipt PDF).

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Press `⌃⌘R` | `app.typeKey("r", modifierFlags: [.control, .command])` | OCR Upload panel opens | `app.sheets["New Receipt Upload"].waitForExistence(timeout: 2)` |
| 2 | Click "Browse Files" in DropZone | `app.buttons["Browse Files"].click()` | NSOpenPanel opens | `app.sheets.firstMatch.staticTexts["Open"].exists` |
| 3 | Navigate to fixture PDF and open | `openPanel.typeText(fixturePath); openPanel.buttons["Open"].click()` | File pre-filled in DropZone | `app.staticTexts["sample-receipt.pdf"].exists` |
| 4 | Verify model picker shows active model | `app.popUpButtons["AI Model"].firstMatch` | Picker label contains model name | `XCTAssert(modelPicker.value as? String != "")` |
| 5 | Press `⌘Return` (Run OCR) | `app.typeKey(.return, modifierFlags: .command)` | ProgressView visible | `app.progressIndicators.firstMatch.exists` |
| 6 | Wait for OCR completion (≤ 60s) | `app.navigationBars["Review Receipt"].waitForExistence(timeout: 60)` | Review and Edit view appears | `XCTAssert(app.navigationBars["Review Receipt"].exists)` |
| 7 | Verify line items present | `app.cells.count` | At least 3 line items | `XCTAssertGreaterThanOrEqual(app.cells.count, 3)` |
| 8 | Edit first item total | `app.cells.firstMatch.textFields["unit_price"].doubleTap(); app.typeText("12.99")` | Field shows "12.99" | `XCTAssertEqual(app.cells.firstMatch.textFields["unit_price"].value as? String, "12.99")` |
| 9 | Press `⌘Return` (Confirm Receipt) | `app.typeKey(.return, modifierFlags: .command)` | AttributionPicker sheet appears | `app.sheets["Who bought this?"].waitForExistence(timeout: 3)` |
| 10 | Select "Whole Household" | `app.buttons["Whole Household"].click()` | Radio row selected | Selected state on "Whole Household" row |
| 11 | Tap "Save Attribution" | `app.buttons["Save Attribution"].click()` | Receipt list view or Dashboard shown; success toast | `app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Receipt confirmed'")).firstMatch.waitForExistence(timeout: 5)` |

**Final assertions**: `SeedHelper.fetchReceiptsList()` returns at least 1 receipt with total > 0; `SeedHelper.fetchInventory()` shows quantity incremented for at least one item in the receipt.

---

#### E2E Script 3: Bill Pay Watcher (P0)

**Test file**: `LocalOCRUITests/BillPayWatcherTests.swift`

**Precondition**: Logged-in user; seeded with 5 floor obligations for current month: 2 marked paid, 3 unpaid. One obligation named "Netflix". Plaid items seeded with 1 staged transaction matching the first unpaid bill amount ±$0.02.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Press `⌘3` | `app.typeKey("3", modifierFlags: .command)` | Fixed Bills view active | `app.navigationBars["Fixed Bills"].exists` |
| 2 | Verify 5 rows visible | `app.cells.count` | 5 rows | `XCTAssertEqual(app.cells.count, 5)` |
| 3 | Verify 2 green "Paid" badges and 3 amber "Unpaid" | Count badge labels | 2 paid, 3 unpaid | Paid count == 2; unpaid count == 3 |
| 4 | Arrow-down to first unpaid bill | `app.typeKey(.downArrow, modifierFlags: [])` × N | First unpaid row focused | Row highlighted |
| 5 | Press Space to mark paid | `app.typeKey(" ", modifierFlags: [])` | Row status toggles to "Paid" | `app.cells[unpaidIndex].staticTexts["Paid"].waitForExistence(timeout: 2)` |
| 6 | Verify PATCH fired (via SeedHelper) | `SeedHelper.fetchObligations()` | Updated obligation has `payment_status = "paid"` | `obligation.paymentStatus == "paid"` |
| 7 | Double-click "Netflix" row label | `netflixCell.staticTexts["Netflix"].doubleTap()` | Inline text field appears | `netflixCell.textFields.firstMatch.exists` |
| 8 | Clear and type new name | `textField.clearAndTypeText("Netflix Streaming")` | Field shows "Netflix Streaming" | `textField.value as? String == "Netflix Streaming"` |
| 9 | Press Return | `app.typeKey(.return, modifierFlags: [])` | PATCH fires; cell shows "Netflix Streaming" | `netflixCell.staticTexts["Netflix Streaming"].waitForExistence(timeout: 3)` |
| 10 | Press `⌘W` | `app.typeKey("w", modifierFlags: .command)` | Main window closes; app still running in menu bar | `app.windows["MainWindow"].exists == false`; `app.statusBarItems.count > 0` |

**Final assertions**: `SeedHelper.fetchObligations()` confirms: (a) at least 3 obligations have `payment_status = "paid"`, (b) the "Netflix" obligation label is now "Netflix Streaming".

---

#### E2E Script 4: Analyst — Spending by Category + CSV Export (P1)

**Test file**: `LocalOCRUITests/AnalystTests.swift`

**Precondition**: Logged-in admin user; seeded with ≥ 30 receipts across 5 categories (Grocery, Restaurant, Health, Transport, Shopping), current month with meaningful totals.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Press `⌘0` | `app.typeKey("0", modifierFlags: .command)` | Dashboard active | Navigation title "Dashboard" |
| 2 | Click "Spending" tile CTA | `app.buttons["View Analytics"].click()` | Spending by Category panel opens | `app.staticTexts["Spending by Category"].exists` |
| 3 | Verify 5 category rows | `app.outlineRows.count` | 5 root outline rows | `XCTAssertGreaterThanOrEqual(app.outlineRows.count, 5)` |
| 4 | Click `>` month arrow to advance one month | `app.buttons["next month"].click()` | Month label updates | `app.staticTexts.matching(NSPredicate(format: "label CONTAINS '2026'")).firstMatch.exists` |
| 5 | Press `<` to go back | `app.buttons["previous month"].click()` | Returns to current month | Current month label restored |
| 6 | Click "Groceries" outline row disclosure | `app.outlineRows["Groceries"].disclosureTriangles.firstMatch.click()` | Sub-rows appear under Groceries | `app.outlineRows.count > 5` (expanded) |
| 7 | Verify sub-rows are receipt rows | `app.outlineRows["Groceries"].cells.count` | ≥ 1 sub-row | `XCTAssertGreaterThan(subRows.count, 0)` |
| 8 | Press `⌘S` (Export CSV) | `app.typeKey("s", modifierFlags: .command)` | NSSavePanel opens | `app.sheets.firstMatch.waitForExistence(timeout: 2)` |
| 9 | Accept default filename | `app.sheets.firstMatch.buttons["Save"].click()` | File saved; Finder banner notification | `FileManager.default.fileExists(atPath: downloadedPath)` |
| 10 | Verify CSV row count | `SeedHelper.parseCSV(path: downloadedPath).rowCount` | ≥ 30 rows (one per receipt) | `csvRowCount >= 30` |

**Final assertions**: CSV file exists at the saved path; first row is a header row containing "Category"; row count matches seeded receipt count.

---

#### E2E Script 5: OCR Upload via Dock Icon Drop (P0)

**Test file**: `LocalOCRUITests/DockDropTests.swift`

**Precondition**: App running but main window closed (app in menu bar mode). `sample-receipt.pdf` fixture available.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Close main window | `app.windows["MainWindow"].buttons["Close"].click()` | Window closed; status item remains | `app.windows.count == 0` |
| 2 | Drop PDF onto Dock icon | `app.activate()`; use `NSWorkspace.open([receiptURL], withApplicationAt: appURL, configuration: NSWorkspace.OpenConfiguration())` | App opens; OCR Upload panel appears | `app.sheets["New Receipt Upload"].waitForExistence(timeout: 5)` |
| 3 | Verify file pre-filled | `app.staticTexts["sample-receipt.pdf"].exists` | Filename shown in DropZone | `XCTAssert(app.staticTexts["sample-receipt.pdf"].exists)` |
| 4 | Cancel and verify no receipt created | `app.buttons["Cancel"].click()` | Panel dismissed; no receipt in DB | `SeedHelper.fetchReceiptsList().count == 0` |

---

#### E2E Script 6: Deep Link Navigation (P1)

**Test file**: `LocalOCRUITests/DeepLinkTests.swift`

**Precondition**: Logged-in user; seeded receipt with known `purchase_id = 42`; seeded with 3 shopping list items.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Open `localocr://receipt/42` from Terminal | `NSWorkspace.shared.open(URL(string: "localocr://receipt/42")!)` | Receipt Inspector window opens for purchase 42 | `app.windows.matching(NSPredicate(format: "title CONTAINS '42'")).firstMatch.waitForExistence(timeout: 3)` |
| 2 | Verify receipt ID 42 shown | Inspect Inspector window title or content | Title contains store name from fixture | Window title matches expected store+date pattern |
| 3 | Open `localocr://shopping` | `NSWorkspace.shared.open(URL(string: "localocr://shopping")!)` | Main window navigates to Shopping List | `app.navigationBars["Shopping"].waitForExistence(timeout: 2)` |
| 4 | Open `localocr://inventory` | Repeat for inventory link | Main window navigates to Inventory | `app.navigationBars["Inventory"].waitForExistence(timeout: 2)` |
| 5 | Open `localocr://unknown/path` | Trigger unknown deep link | Toast appears: "Unknown action" | Toast with "Unknown" text visible; no crash |

---

#### E2E Script 7: Notification Deep Link → Shopping List (P1)

**Test file**: `LocalOCRUITests/NotificationTests.swift`

**Precondition**: Notification permission granted; shopping nudge enabled; low-stock count ≥ 3.

| Step | XCUITest Action | Element Query | Expected State | Assertion |
|---|---|---|---|---|
| 1 | Trigger nudge notification programmatically | Call `NotificationManager.shared.scheduleShoppingNudge()` with immediate delivery (override to 1-second trigger) | System notification appears in Notification Center | `UNUserNotificationCenter.current().pendingNotificationRequests(completionHandler:)` returns 1 pending |
| 2 | Click "Start Walk" action on notification | Simulate `userNotificationCenter(_:didReceive:)` with `actionIdentifier = "VIEW_LIST"` | App foregrounds to Shopping List | `app.navigationBars["Shopping"].waitForExistence(timeout: 3)` |
| 3 | Verify shopping list is visible | `app.cells.exists` | Shopping list cells present | `XCTAssert(app.cells.firstMatch.exists)` |
| 4 | Dismiss notification with "Dismiss" action | Simulate with `actionIdentifier = "DISMISS"` | No navigation; nudge muted for 24h | `UserDefaults.standard.double(forKey: "nudgeMutedUntil") > Date().timeIntervalSince1970` |

---

### 6.5 macOS-SPECIFIC TEST SCENARIOS

These scenarios address macOS platform behaviors that are outside the scope of standard XCUITest UI flows. Each is linked to a business rule or acceptance criterion from §2.6. Test method prefix: `testMacOS_`.

| # | Scenario | Test Method | How to Test | Expected Result | Pass Condition | Links |
|---|---|---|---|---|---|---|
| 1 | **Cold start launch time < 2.0s** | `testMacOS_ColdStartTime` | Instruments Time Profiler: terminate app, click Dock icon, measure to first interactive Dashboard frame | < 2.0s on M1 baseline | Instruments report `didFinishLaunching` to first UI update ≤ 2000ms | §2.6 AC-01 |
| 2 | **Cold start launch time < 1.2s on M3** | `testMacOS_ColdStartM3` | Same measurement on M3 Mac mini (§6.1 P0) | < 1.2s on M3 | M3 Instruments trace ≤ 1200ms | §2.6 AC-01, §6.6 |
| 3 | **Resume from sleep — token refresh** | `testMacOS_SleepResume` | Put Mac to sleep 30 min; wake; bring app to foreground; measure time to validated UI | Session validated ≤ 500ms; no flash of LoginView | `applicationDidBecomeActive` fires; `GET /auth/me` returns 200; Login sheet does NOT appear; wall clock time from activation to UI ≤ 500ms | §2.6 AC-09 |
| 4 | **Window resize to minimum size** | `testMacOS_MinWindowSize` | Drag main window corner to exactly 900×600pt | No UI elements clipped; sidebar navigable; all toolbar items visible | XCUITest verifies all accessible elements within window bounds; no clipping reported by `XCUIElement.frame.maxX > window.frame.maxX` | §3.2 |
| 5 | **Window full-screen mode** | `testMacOS_FullScreen` | Press `⌃⌘F`; interact with sidebar; move mouse to top | Sidebar persists; toolbar auto-hides; menu bar auto-hides on inactivity | `NSWindow.styleMask.contains(.fullScreen)` true; sidebar element accessible; no notch overlap on notched hardware | §3.9 |
| 6 | **`⌘W` closes window without quitting** | `testMacOS_CmdW` | Press `⌘W` on main window | Window closes; menu bar status item remains; app does not terminate | `app.windows["MainWindow"].exists == false` AND `app.statusBarItems.count > 0` AND `app.state == .runningForeground` | §2.6 AC-12 |
| 7 | **`⌘W` on Receipt Inspector closes only that window** | `testMacOS_CmdW_Inspector` | Open 2 Receipt Inspector windows; press `⌘W` on one | Only the focused Inspector closes; other Inspector and main window remain | Remaining windows count equals 2 (main + 1 inspector) | §3.2 |
| 8 | **`⌘Q` drains pending writes** | `testMacOS_CmdQ_Drain` | Inject 2 pending writes in offline queue; go online; press `⌘Q` | Pending writes flushed before termination; app terminates cleanly | `pendingWrites.sqlite` has 0 rows after app terminates; exit code 0 | §2.6 AC-12, §4.5 |
| 9 | **`⌘Q` with upload in progress shows confirmation** | `testMacOS_CmdQ_UploadInProgress` | Start OCR upload; while `isProcessing = true`, press `⌘Q` | Confirmation alert "Upload in progress — quit anyway?" presented | Alert visible; app does not terminate until user confirms | §3.3 App Menu |
| 10 | **All 62 keyboard shortcuts from §3.4** | `testMacOS_AllKeyboardShortcuts` | XCUITest iterates shortcut table from §3.4; each invoked from the correct scope | Each shortcut fires its documented action | Spy closures or navigation state changes confirm each action; zero shortcuts fail | §3.4 |
| 11 | **⌃⌘R from another app opens upload panel** | `testMacOS_GlobalShortcut` | Launch another app (TextEdit) to foreground; press `⌃⌘R` | LocalOCR comes to front; OCR Upload panel opens | `app.sheets["New Receipt Upload"].waitForExistence(timeout: 3)` from TextEdit process context | §2.3 feature #1 |
| 12 | **Right-click context menus on all 9 surfaces (§3.5)** | `testMacOS_ContextMenus` | XCUITest right-clicks each of 9 surfaces: receipt row, inventory row, shopping item, fixed bill row, Plaid transaction row, sidebar item, Kitchen View item, receipt line item, contribution event row | Correct menu items appear per §3.5 spec | All §3.5 items present; destructive items in red; separators in correct positions | §3.5 |
| 13 | **Dark mode → light mode switch while app running** | `testMacOS_DarkLightSwitch` | Open app in dark mode; go to System Settings → toggle to Light | UI updates within 200ms; no white flash; all token colors swap | Color values on `NSApp.mainWindow` content update; no white rectangle visible; measured transition < 200ms | §2.6 AC-04 |
| 14 | **Light mode → dark mode switch** | `testMacOS_LightDarkSwitch` | Reverse of above | Same; no black flash | Same pass criteria inverted | §2.6 AC-04 |
| 15 | **External display connect** | `testMacOS_ExternalDisplayConnect` | Hot-plug second monitor while app running | Window remains on primary display; layout consistent | Window frame unchanged; no element displacement; sidebar still present | §6.1 (M2 Pro multi-display scenario) |
| 16 | **Window moved to external display** | `testMacOS_MoveToExternalDisplay` | Drag main window to external 4K display | Layout adapts to new DPI; text crisp; no blurriness | Window renders at native resolution on external display; `backingScaleFactor` used correctly | §6.1 |
| 17 | **Notched display — no content under notch** | `testMacOS_NotchedDisplay` | Run on M1 Pro 14" MacBook (§6.1 P1); check full-screen mode | No menu bar item or window content hidden under notch | `NSWindow.contentLayoutRect` excludes notch area; interactive elements within safe area | §6.1 P1 notch scenario |
| 18 | **VoiceOver navigation — complete path per view** | `testMacOS_VoiceOver_AllViews` | Enable VoiceOver (`⌘F5`); traverse all 16 MVP views using VO arrow keys | Every element announced with non-empty label; logical reading order; no VoiceOver trap (infinite loop) | Every XCUIElement has non-empty `accessibilityLabel`; focus never stuck; all interactive elements reachable | §2.6 AC-11, §6.7 |
| 19 | **Accessibility large text — layout does not break** | `testMacOS_LargeText` | System Settings → Display → Text Size → Larger (max setting) | Layout does not break; text truncated only where intentional; no overlapping elements | All list rows within bounds; no `XCUIElement` overlaps sibling; SwiftUI dynamic type responds | §6.7 |
| 20 | **Drag from Finder — PDF** | `testMacOS_FinderDrop_PDF` | Drag `sample-receipt.pdf` from Finder to app window | OCR Upload sheet opens; filename shown | `app.sheets["New Receipt Upload"].exists`; filename label present | §2.6 AC-07 |
| 21 | **Drag from Finder — PNG** | `testMacOS_FinderDrop_PNG` | Drag `sample-receipt.png` from Finder to app window | OCR Upload sheet opens with PNG file | Same assertions for PNG type | §2.6 AC-07 |
| 22 | **Drag from Finder — HEIC** | `testMacOS_FinderDrop_HEIC` | Drag `sample-receipt.heic` from Finder to app window | OCR Upload sheet opens with HEIC file | Same assertions for HEIC type | §2.6 AC-07 |
| 23 | **Drag from Finder — JPEG** | `testMacOS_FinderDrop_JPEG` | Drag `sample-receipt.jpg` from Finder to app window | OCR Upload sheet opens with JPEG file | Same assertions for JPEG type | §2.6 AC-07 |
| 24 | **Drag unsupported file type rejected** | `testMacOS_FinderDrop_Unsupported` | Drag `document.docx` onto app window | Error message "Unsupported file type"; OCR Upload does NOT open with this file | DropZone shows red border; toast with "Unsupported file type" text | §2.6 AC-07 |
| 25 | **Auth tokens in Keychain, not UserDefaults** | `testMacOS_KeychainNotUserDefaults` | After login, inspect `UserDefaults.standard` and `Keychain` | Session cookie / server URL in Keychain; NOT in `UserDefaults` | `UserDefaults.standard.object(forKey: "session_cookie") == nil`; `KeychainStore.get(key: .sessionURL) != nil` | §2.6 AC-06 |
| 26 | **Server URL change clears session and re-prompts** | `testMacOS_ServerURLChange` | Log in; go to Settings → Account; change server URL | Keychain session cleared; `LoginView` presented | `AuthState.state == .unauthenticated` after URL change; Login sheet visible | §2.6 AC-08 |
| 27 | **Background foreground refresh fires on activation** | `testMacOS_ForegroundRefresh` | Spy on `BackgroundFetchScheduler.refresh()`; send app to background; wait 65s; bring to foreground | Refresh fires within 1s of foreground activation | Spy called exactly once ≤ 1000ms after `applicationDidBecomeActive` | §2.6 AC-09, §3.9 |
| 28 | **60-second gate prevents double refresh** | `testMacOS_RefreshGate` | Bring app to foreground twice within 30s | Refresh fires only once | Spy called exactly once for both foreground events within 60s window | §3.9 Background Fetch |
| 29 | **Notification permission request fires after first login** | `testMacOS_NotificationPermissionRequest` | First login (no prior permission request) | `UNUserNotificationCenter.requestAuthorization` called once | Mock `UNUserNotificationCenter` spy records `requestAuthorization` call after `/auth/me` success | §2.6 AC-10, §4.6 |
| 30 | **Notification permission denied → Settings banner** | `testMacOS_NotificationDenied` | Mock `authorizationStatus = .denied` | Yellow banner in Settings → Notifications with deep-link button | Banner visible; "Open Notification Settings" button calls `NSWorkspace.shared.open(x-apple.systempreferences:...)` | §2.6 AC-10 |
| 31 | **Plaid Link OAuth via ASWebAuthenticationSession** | `testMacOS_PlaidOAuth` | Navigate to Plaid; tap "Add Bank Account" (admin) | `ASWebAuthenticationSession` launched with Plaid Link URL | `ASWebAuthenticationSession` initiated; completion handler wired to `/plaid/exchange` endpoint | §2.6 AC-18 |
| 32 | **No Plaid access token stored client-side** | `testMacOS_PlaidNoClientToken` | Complete Plaid Link flow | `Keychain` and `UserDefaults` contain no Plaid access token | `KeychainStore.get(key: .plaidAccessToken)` returns nil; `UserDefaults.standard.object(forKey: "plaid_access_token")` returns nil | §2.6 AC-18 |
| 33 | **Offline banner appears when server unreachable** | `testMacOS_OfflineBanner` | Block all network traffic (using `NWPathMonitor` mock returning `.unsatisfied`) | "Offline" banner appears at top of current view | `app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Offline'")).firstMatch.exists` | §4.5 |
| 34 | **Offline queue accepts writes** | `testMacOS_OfflineQueue` | Set `AppState.isOffline = true`; trigger a shopping list add | Write queued in `pendingWrites.sqlite`; UI updates optimistically | `pendingWrites.sqlite` has 1 row after offline write attempt | §4.5 |
| 35 | **Reconnect drains offline queue** | `testMacOS_ReconnectDrain` | Pre-populate `pendingWrites.sqlite` with 2 entries; restore network | Both writes replayed; `pendingWrites.sqlite` is empty | `MockURLProtocol` receives 2 replayed requests; DB row count drops to 0 | §4.5 |
| 36 | **Demo mode gate blocks all write API calls** | `testMacOS_DemoModeGate` | Set `AppState.isDemoMode = true`; attempt 5 different write actions across different views | No POST/PATCH/DELETE requests made; "Demo mode" toast shown for each | `MockURLProtocol.requestLog` contains zero mutating requests; toast count equals 5 | §1.7 rule 10, §2.6 AC-13 |
| 37 | **Bill cadence "Not due this month" for quarterly bills** | `testMacOS_BillCadenceQuarterly` | Inject quarterly bill with last billing month 2 months ago | Fixed Bills row shows "Not due this month" cadence badge | Cadence badge text equals "Not due this month"; row is not amber | §1.7 rule 5, §2.6 AC-17 |
| 38 | **Bill cadence "Due this month" in billing month** | `testMacOS_BillCadenceDue` | Inject quarterly bill with last billing month 3 months ago (interval = 3 → this month matches) | Fixed Bills row shows "Due this month" cadence badge in amber | Cadence badge text equals "Due this month"; row is amber | §1.7 rule 5, §2.6 AC-17 |
| 39 | **OCR diff view: new items green, changed amber, unchanged neutral** | `testMacOS_OCRDiff` | Inject re-run result with 1 new item, 1 changed item, 1 unchanged item | Correct badge colors on each item type | New item has green "NEW" badge; changed item has amber "CHANGED" badge; unchanged item has no badge | §2.6 AC-15 |
| 40 | **Re-run OCR partial accept calls correct endpoint** | `testMacOS_RerunPartialAccept` | In diff mode, accept only the new item (not the changed item) | `POST /receipts/<id>/items` called for the new item only | `MockURLProtocol` records exactly 1 POST with the new item's data; changed item endpoint not called | §2.6 AC-15 |
| 41 | **Attribution picker mandatory after confirm** | `testMacOS_AttributionMandatory` | Confirm receipt without pre-set attribution | AttributionPicker sheet appears | `AttributionPicker` sheet visible immediately after confirm | §1.7 rule 9, §2.6 AC-16 |
| 42 | **Spending by Person admin-gated** | `testMacOS_SpendingByPersonAdminGate` | Navigate to Spending by Category with `role = "user"` vs `role = "admin"` | "By Person" tab/view hidden for non-admin; visible for admin | "By Person" element absent in user role; present in admin role | §1.7 rule 9, §2.6 AC-16 |
| 43 | **Continuity Camera source appears on OCR Upload** | `testMacOS_ContinuityCamera` | Run on Mac with iPhone on same Wi-Fi; iPhone satisfies Continuity Camera requirements | "Take Photo with iPhone" button visible in OCR Upload panel | `continuityAvailable = true`; button `"Take Photo with iPhone"` exists | §2.3 feature #5 |
| 44 | **Spotlight search results (v1.1)** | `testMacOS_Spotlight` (v1.1) | Index 3 inventory items; search in Spotlight | Results include inventory item names; click opens app to correct row | `CSSearchableIndex` has items with correct `uniqueIdentifier`; app navigates on click | §2.3 feature #10 |
| 45 | **Notarization passes** | `testMacOS_Notarization` | Run `xcrun notarytool submit` on Release .app | Notarization status: "accepted" within 5 min | `xcrun notarytool log` shows "status: Accepted" | §2.6 AC-05 |
| 46 | **Gatekeeper quarantine check** | `testMacOS_Gatekeeper` | Apply quarantine xattr to the .app; attempt to open | No "unverified developer" system dialog | `spctl --assess --verbose LocalOCR.app` exits 0 | §2.6 AC-05 |

---

### 6.6 PERFORMANCE BENCHMARKS

All measurements use **Xcode Instruments** (Time Profiler, Allocations, Energy Log) plus `XCTest.measure {}` blocks for automated regression detection. Baseline measurements are captured on the M1 MacBook Air (§6.1 P0 baseline) and committed to `LocalOCRTests/Baselines/` as `.xcresult` reference data. Any CI build that exceeds a baseline by > 10% fails.

| Metric | Target (M1 baseline) | Target (M3 Mac mini) | Measurement Method | CI Fail Threshold |
|---|---|---|---|---|
| **Cold start: Dock click → first interactive frame** | < 2.0 s | < 1.2 s | `XCTest.measure { app.launch() }`; measure until Dashboard tiles begin rendering | > 10% regression from baseline |
| **Receipt Inspector window open** | < 100 ms | < 60 ms | `measure { app.open(receiptId: 1) }`; measure until Inspector window `exists` | > 10% regression |
| **Inventory list scroll (500 items)** | 60 fps sustained | 60 fps sustained | Instruments Core Animation tool; drag scroll through all 500 rows; capture dropped frame count | > 3 dropped frames per 60-frame window |
| **API response received → UI visible** | < 100 ms | < 80 ms | Mock API with 0ms latency; measure from `URLSession.dataTask.completionHandler` to first `.exists == true` on result element | > 10% regression |
| **Memory: idle (app launched, sitting on Dashboard)** | < 100 MB RSS | < 100 MB RSS | Instruments Allocations; "Dirty Size" of `LocalOCR` process after 30s idle | > 150 MB RSS at idle |
| **Memory: active (all 16 MVP views visited once)** | < 300 MB RSS | < 300 MB RSS | Navigate all 16 MVP views; capture peak RSS | > 400 MB RSS peak |
| **CPU: idle** | < 1% | < 0.5% | Instruments Energy Log; read CPU % after 60s idle on Dashboard | > 2% sustained for 30s idle |
| **CPU: active scroll** | < 8% | < 5% | Instruments Energy Log; measure CPU during 500-item inventory scroll | > 12% sustained scroll |
| **Binary size (stripped Release)** | < 25 MB arm64 | < 25 MB arm64 | `ls -lh` on `.app/Contents/MacOS/LocalOCR` after `strip -x` | > 35 MB stripped binary |
| **DMG file size** | < 30 MB | < 30 MB | `ls -lh LocalOCR-1.0.0-arm64.dmg` | > 50 MB DMG |
| **App icon first paint** | < 50 ms | < 30 ms | Instruments Time Profiler; measure from `applicationDidFinishLaunching` to Dock tile with icon visible | > 100 ms |
| **Sankey chart render (v1.1)** | < 1.5 s | < 1.0 s | `XCTest.measure { sankeyView.waitForRendered() }`; measured from `setSankeyData()` call to `webView(_:didFinish:)` | > 10% regression |
| **Spotlight reindex (v1.1)** | < 5 s for 1000 items + 500 receipts | < 3 s | `XCTest.measure { SpotlightIndexer.shared.reindexAll() }`; measure wall clock | > 8 s |
| **Shopping list search: type "bread" → filter response** | < 50 ms | < 30 ms | `XCTest.measure`; measure from keydown to visible filtered results | > 100 ms |
| **Dashboard foreground refresh (all 6 endpoints)** | < 800 ms wall clock | < 500 ms | Mock API returning immediately; measure `async let` parallel fetch duration | > 1200 ms |
| **Settings window open** | < 80 ms | < 50 ms | Measure from `⌘,` to Settings window `exists` | > 150 ms |

**Measurement protocol:**
1. Run each benchmark 5× and report the **median** value.
2. First run is a warm-up and discarded.
3. Benchmarks run on the physical hardware listed in §6.1 (not in simulator; Simulator performance is not representative).
4. Machine must be plugged in (AC power) and have Spotlight and Siri disabled during measurement to eliminate background noise.
5. Baseline files saved to `LocalOCRTests/Baselines/performance-<YYYY-MM-DD>.json` after each accepted release.

**CI performance gate:**
- GitHub Actions self-hosted runner (M1 Mac mini, §6.8) runs `xcodebuild test -testPlan LocalOCRPerformanceTests` after every PR merge to `main`.
- Test plan `LocalOCRPerformanceTests.xctestplan` includes only the `XCTest.measure {}` blocks.
- If any measurement exceeds baseline × 1.10 (10% regression), the CI step fails with a descriptive message identifying the regressed metric and the measured vs baseline values.

---

### 6.7 ACCESSIBILITY CHECKLIST

This checklist maps directly to §2.6 AC-11 and §6.5 `testMacOS_VoiceOver_AllViews`. Every item must be ✅ before v1.0 ships. The checklist is executed manually during Phase 7 Polish (§5.8) and re-verified by the automated VoiceOver traversal test (`testMacOS_VoiceOver_AllViews`).

#### VoiceOver Navigation

- [ ] **VO-01** — VoiceOver reads all interactive elements in logical reading order on all 16 MVP views (LoginView, DashboardView, OCRUploadView, ReceiptReviewView, InventoryView, KitchenView, ShoppingListView, FixedBillsView, PlaidAccountsView, CashTransactionsView, SpendingByCategoryView, AuthAndMembersView, ContributionsView, SettingsView all panes, MenuBarPopoverView, DemoModeOverlay).
- [ ] **VO-02** — All icon-only buttons have a non-empty `.accessibilityLabel`. Specific targets: toolbar refresh button (`"Refresh data"`), sidebar toggle (`"Toggle sidebar"`), quantity stepper `−` and `+` buttons (`"Decrease quantity"`, `"Increase quantity"`), DropZone browse button (`"Browse files"`), Receipt Inspector close button (`"Close receipt inspector"`).
- [ ] **VO-03** — No VoiceOver trap exists: no view where VO focus loops infinitely without an escape route. Verified by traversing every view with VO Escape (⌃⌥Escape) and confirming a dismiss action is always available.
- [ ] **VO-04** — All list rows announce meaningful content. Each inventory row reads: "[Product name], [quantity] in stock, [stock status — Low/Out/Normal]." Each shopping list row reads: "[Item name], [status — checked/unchecked]." Each fixed bill row reads: "[Bill name], [status — paid/unpaid], [expected amount]."
- [ ] **VO-05** — Modals and sheets announce themselves on presentation. When `AttributionPicker` sheet appears, VO announces "Who bought this? sheet." When `OCRUploadView` sheet opens, VO announces "New Receipt Upload."
- [ ] **VO-06** — VoiceOver rotor includes the "Headings" category on all views that have `.accessibilityAddTraits(.isHeader)` set on section headers. Confirmed by opening VO Rotor (`⌃⌥U`) and selecting "Headings" — all section headers appear.
- [ ] **VO-07** — Focus moves logically from the last element in one section to the first in the next. Specifically: in ReceiptReviewView, Tab through the last line-item field exits the list and reaches the "Confirm Receipt" button (not trapped in the list).
- [ ] **VO-08** — `SkeletonView` placeholder announces "Loading" and does not trap VO focus while the real data loads.

#### Color Contrast

- [ ] **CC-01** — All text meets **WCAG AA 4.5:1** contrast ratio against its background. Tested in both Light Mode and Dark Mode using the macOS Accessibility Inspector (Instruments → Accessibility Inspector → "Color Contrast Calculator"). Tokens tested: `label` on `background`, `secondary-label` on `surface`, `caption` on `low-stock-pill` (amber), "NEW" badge text (green) on `successDim`, "Out" text (red) on `errorDim`.
- [ ] **CC-02** — The `warning` amber color (`#f59e0b` Light / `#fbbf24` Dark) on `warningDim` background passes 4.5:1. Validated for `LowStockPill` and `FixedBillsView` unpaid status badges.
- [ ] **CC-03** — The `success` green (`#2fa36b` Light / `#4ade80` Dark) on `successDim` background passes 4.5:1. Validated for in-stock status badges and confirmed receipt toasts.
- [ ] **CC-04** — The `accent` blue (`#3b82f6`) on `background` (white in light mode) passes 4.5:1 for normal-weight body text. Note: `#3b82f6` on white (#ffffff) is 3.0:1 at 13pt — does NOT pass AA for body text. Mitigation: accent is used only for interactive buttons (which are held to 3.0:1 for large UI components, not text) and border highlights. No informational body text uses accent as its only color. Documented as a known contrast trade-off; non-blocking if accent color is used only for interactive affordances.
- [ ] **CC-05** — Dark mode: `label` (`#f0f0f0`) on `background` (`#111113`) = contrast ratio ≈ 16.7:1. ✅ Passes AAA.
- [ ] **CC-06** — No information conveyed by color alone: the `LowStockPill` also contains the text "Low" or "Out"; the `ProgressBarView` also has a numeric label; paid/unpaid bill rows also show textual status badges. Confirm each status communication has a text fallback.

#### Keyboard-Only Navigation

- [ ] **KB-01** — Tab and Shift+Tab traverse all interactive elements in every view without skipping any control. Tested by closing System Settings → Accessibility → Full Keyboard Access to verify standard Tab focus works.
- [ ] **KB-02** — All 62 keyboard shortcuts in §3.4 are functional and do not conflict with each other within their respective scopes.
- [ ] **KB-03** — Focus ring is visible (3pt blue ring, macOS default accent color) on every focused interactive element. Verified against `DesignTokens.swift` — no custom focus ring suppression.
- [ ] **KB-04** — The `DropZone` is keyboard-accessible: Tab reaches it; Space or Return triggers `NSOpenPanel`. Verified in `OCRUploadView` keyboard navigation path.
- [ ] **KB-05** — The `InlineEditableCell` enters edit mode via F2 (§3.4), via double-click, and via Return when the row is focused. All three paths verified in `FixedBillsView`.

#### Dynamic Type (macOS "Larger Text" Setting)

- [ ] **DT-01** — At System Settings → Accessibility → Display → Text Size "Larger": all list rows expand to accommodate the larger font; no text is clipped within its row bounds.
- [ ] **DT-02** — All `SwiftUI.Font` usages reference the §3.1 type scale constants (e.g. `.font(.body)`, `.font(.caption)`) — never hardcoded point sizes. This ensures Dynamic Type scales automatically.
- [ ] **DT-03** — `InlineEditableCell` (`NSTextField` when editing) inherits the user's text size preference. Confirmed by entering edit mode on an obligation name with Larger Text enabled.
- [ ] **DT-04** — `LowStockPill` and `CategoryChip` labels scale with Dynamic Type; pill height adjusts (minimum 22pt plus additional for larger type); no text overflow.

#### Reduce Motion

- [ ] **RM-01** — `@Environment(\.accessibilityReduceMotion)` is checked in: `SkeletonView` (shimmer disabled), `DashboardView` (tile appear animation disabled), `Toast` (slide-in replaced with fade), `NavigationSplitView` transitions (`.easeInOut(duration: 0.001)` substituted).
- [ ] **RM-02** — `Animations.swift` `withReducedMotion` helper correctly returns `.linear(duration: 0.001)` when `accessibilityReduceMotion == true`. Unit test `AnimationsTests.testReducedMotionFallback` verifies this.
- [ ] **RM-03** — The Sankey chart WKWebView (`SankeyWebView`) checks `window.matchMedia('(prefers-reduced-motion: reduce)')` in the HTML template and disables D3 transition animations accordingly.

#### Reduce Transparency

- [ ] **RT-01** — When System Settings → Accessibility → Display → "Reduce Transparency" is enabled: `NSVisualEffectView` sidebar vibrancy disabled (sidebar renders with solid `Color.sidebarBg`); popover backgrounds rendered as solid fills; no content rendered behind frosted glass that cannot be read without vibrancy.
- [ ] **RT-02** — `@Environment(\.accessibilityReduceTransparency)` checked in `Animations.swift`; sidebar and popover backgrounds swap to solid `Color.surface` when set.

#### Increase Contrast

- [ ] **IC-01** — When System Settings → Accessibility → Display → "Increase Contrast" is enabled: list row borders increase from 0pt (invisible) to 1pt `Color.border`; card outlines become 1pt `Color.border`; `LowStockPill` border becomes 2pt.
- [ ] **IC-02** — `@Environment(\.accessibilityIncreaseContrast)` checked in `ListRowStyles.swift` and `Card.swift`; border width conditional on this environment value.

#### Touch Alternatives for Gestures

- [ ] **TA-01** — All trackpad-gesture interactions (right-click via Control+Click; two-finger scroll) have keyboard alternatives. Right-click context menus are reachable via `⌃F10` (macOS standard context menu key) for keyboard users.
- [ ] **TA-02** — The `DropZone` drag target has a click-to-browse fallback (verified in `DropZone.UC-029`).
- [ ] **TA-03** — Drag-to-reorder in Shopping List has keyboard alternative: rows can be reordered via arrow keys + some explicit reorder command, or users can delete and re-add in desired order. (Note: true drag-to-reorder keyboard alternative requires custom implementation in §5.1 list specs — flag for Phase 7 audit.)

#### Accessibility Labels Audit Checklist (per view)

| View | Required Labels | Status |
|---|---|---|
| LoginView | App icon, Sign In button, Google OAuth button, Try Demo, email field, password field, server URL collapse | [ ] |
| DashboardView | Each tile with content summary, tile CTA buttons, refresh button, sidebar toggle | [ ] |
| OCRUploadView | DropZone, Continuity Camera button, receipt type picker, model picker, Run OCR button | [ ] |
| ReceiptReviewView | Each line item row (name + quantity + price + kind + confidence), Accept/Discard diff buttons, Confirm Receipt, Re-run OCR | [ ] |
| InventoryView | Each product row (name + quantity + status), quantity stepper buttons, category sidebar items, Add to List button | [ ] |
| KitchenView | Each item card (name + location + stock status), Add to List action | [ ] |
| ShoppingListView | Each list item (name + checked/unchecked), auto-populate button, QR share button, session info bar | [ ] |
| FixedBillsView | Each bill row (name + status + amount + cadence), Mark Paid button, Rename action, Plaid link button | [ ] |
| PlaidAccountsView | Each account row (bank + type + balance + status), each staged transaction (merchant + date + amount + type), Confirm button, Dismiss button | [ ] |
| CashTransactionsView | Amount field, description field, category picker, date picker, Log Cash Spend button, each history row | [ ] |
| SpendingByCategoryView | Each category row (name + total), month navigation arrows, Export button, Sankey chart (static description) | [ ] |
| AuthAndMembersView | Each user row (name + role), invite button, QR login button, sign out button, each device row (name + scope + status) | [ ] |
| ContributionsView | Each leaderboard row (name + points + rank), drill-in button, each event row (type + points + date) | [ ] |
| SettingsView | Each pane tab, all form controls per pane per §3.8 | [ ] |
| MenuBarPopoverView | Low-stock count badge, Quick Add Cash fields + button, Open App button, Upload Receipt button | [ ] |
| DemoModeOverlay | Banner message, Sign In button | [ ] |

---

### 6.8 TEST INFRASTRUCTURE

This section defines the complete testing setup: Xcode targets, fixture strategy, mock layer, CI configuration, coverage requirements, and flaky-test policy. It is the implementation spec for Phase 8 (§5.8 Phase 8 — Testing).

---

#### Xcode Test Targets

| Target | Bundle ID | Type | Hosts | Contents |
|---|---|---|---|---|
| `LocalOCRTests` | `com.localocr.macosTests` | Unit | `LocalOCR.app` | `ComponentTests/`, `ViewTests/`, `NetworkingTests/`, `StateTests/`, `HelpersTests/` |
| `LocalOCRUITests` | `com.localocr.macosUITests` | XCUITest | `LocalOCR.app` (live, not in-process) | E2E test scripts from §6.4; macOS-specific scenarios from §6.5 |

**Test plans:**
- `LocalOCRTests.xctestplan` — all unit + integration tests; runs in CI on every PR.
- `LocalOCRUITests.xctestplan` — E2E tests requiring a live backend; runs in CI on every merge to `main`.
- `LocalOCRPerformanceTests.xctestplan` — `XCTest.measure {}` blocks only; runs in CI after merge to `main`.

---

#### Fixtures Directory

`LocalOCRTests/Fixtures/` contains:

| Fixture File | Content | Used By |
|---|---|---|
| `auth_me.json` | `/auth/me` response for an admin user with id=1, name="Test Admin", role="admin" | IV-001 through IV-075; all authenticated view tests |
| `auth_me_member.json` | `/auth/me` response for a non-admin user with role="user" | IV-039, IV-057, IV-065, IV-074 |
| `inventory_list.json` | `/inventory` response with 10 items (3 low-stock) | IV-021 through IV-025; E2E Script 1 |
| `inventory_list_500.json` | `/inventory` response with 500 items (for scroll performance tests) | §6.6 scroll benchmark |
| `shopping_list.json` | `/shopping` response with 3 open items | IV-026 through IV-030; E2E Script 1 |
| `obligations.json` | `/obligations` response with 5 floor obligations (3 paid, 2 unpaid; 1 quarterly) | IV-031 through IV-035; E2E Script 3 |
| `plaid_accounts.json` | `/plaid/accounts` response with 2 accounts (1 active, 1 login_required) | IV-036 through IV-040 |
| `staged_transactions.json` | `/plaid/staged-transactions` response with 3 pending transactions | IV-037, IV-038; E2E Script 3 |
| `cash_transactions.json` | `/cash-transactions` response with 6 transactions across 3 months | IV-041 through IV-045 |
| `spending_analytics.json` | `/analytics/spending-by-category` response with 5 categories | IV-046 through IV-050 |
| `contributions.json` | `/contributions` response with 5 users (points: 50, 35, 20, 15, 5) and per-user event arrays | IV-051 through IV-055 |
| `receipts_list.json` | `/receipts` response with 10 receipts | IV-016 through IV-020; E2E Script 2 |
| `receipt_detail.json` | `/receipts/1` response with 5 line items (mixed kinds); 1 new item in diff response | IV-016 through IV-020; E2E diff tests |
| `ai_models.json` | `/ai-models` response with 3 models: Gemini 2.0 Flash (active), GPT-4o (locked), Claude Sonnet (unlocked) | IV-013, IV-014; all model picker tests |
| `auth_config.json` | `/auth/config` response with Google OAuth enabled, demo flag false | IV-005; LoginView tests |
| `users_list.json` | `/auth/users` response with 3 users (admin + 2 members) | IV-056, IV-057 |
| `trusted_devices.json` | `/auth/trusted-devices` response with 2 devices | IV-058 |
| `backups_list.json` | `/system/backups` response with 3 backup entries | IV-065 |
| `sample-receipt.pdf` | Real 2-page grocery receipt PDF (redacted); used by E2E OCR upload tests | E2E Script 2 |
| `sample-receipt.png` | Same receipt as PNG; used for Finder drop tests | §6.5 scenarios 21–24 |
| `sample-receipt.jpg` | Same receipt as JPEG | §6.5 scenario 23 |
| `sample-receipt.heic` | Same receipt as HEIC | §6.5 scenario 22 |

---

#### Mock API Layer

`LocalOCRTests/Helpers/MockURLProtocol.swift`:

```swift
class MockURLProtocol: URLProtocol {
    static var responseMap: [String: (statusCode: Int, body: Data?)] = [:]
    static var requestLog: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        MockURLProtocol.requestLog.append(request)
        let path = request.url?.path ?? ""
        if let response = MockURLProtocol.responseMap[path] {
            let httpResponse = HTTPURLResponse(url: request.url!, statusCode: response.statusCode, ...)
            client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
            if let body = response.body { client?.urlProtocol(self, didLoad: body) }
        } else {
            client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
        }
        client?.urlProtocolDidFinishLoading(self)
    }
}
```

Usage in test `setUp`:
```swift
let config = URLSessionConfiguration.ephemeral
config.protocolClasses = [MockURLProtocol.self]
APIClient.shared.session = URLSession(configuration: config)
MockURLProtocol.responseMap = [
    "/auth/me": (200, try! Data(contentsOf: fixtureURL("auth_me.json"))),
    "/inventory": (200, try! Data(contentsOf: fixtureURL("inventory_list.json"))),
    // ...
]
MockURLProtocol.requestLog = []
```

---

#### SeedHelper (E2E tests only)

`LocalOCRUITests/Helpers/SeedHelper.swift` connects to the live backend at `http://localhost:8090` and uses the REST API (authenticated as a test admin user via stored service-account bearer token) to set up and tear down test data.

```swift
struct SeedHelper {
    static func resetHousehold() async throws
    // Truncates: inventory, shopping_list_items, floor_obligations, cash_transactions, purchases
    // Inserts fixture data for the current test scenario

    static func loginAPIDirectly() async throws -> HTTPCookie
    // POSTs to /auth/login with test credentials; returns session cookie for XCUITest app launch

    static func fetchInventory() async throws -> [InventoryItem]
    static func fetchShoppingList() async throws -> [ShoppingListItem]
    static func fetchObligations() async throws -> [FixedBill]
    static func fetchReceiptsList() async throws -> [Receipt]
}
```

---

#### CI Configuration

**Runner**: GitHub Actions self-hosted runner running on a physical **M1 Mac mini** (8GB RAM, macOS 15 Sequoia). The runner is registered as a repository secret under `MACOS_RUNNER`.

**Workflow file**: `.github/workflows/test.yml`

```yaml
name: Test
on: [push, pull_request]
jobs:
  unit-tests:
    runs-on: [self-hosted, macOS, ARM64]
    steps:
      - uses: actions/checkout@v4
      - name: Build and test (unit + integration)
        run: |
          xcodebuild test \
            -scheme LocalOCR \
            -testPlan LocalOCRTests \
            -destination 'platform=macOS,arch=arm64' \
            -resultBundlePath TestResults/unit.xcresult \
            CODE_SIGNING_ALLOWED=NO
      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-results
          path: TestResults/unit.xcresult

  e2e-tests:
    runs-on: [self-hosted, macOS, ARM64]
    needs: unit-tests
    services:
      backend:
        image: localocr-extended:latest
        ports: ['8090:8090']
    steps:
      - uses: actions/checkout@v4
      - name: Start backend
        run: docker compose up -d && sleep 10
      - name: Build and test (E2E)
        run: |
          xcodebuild test \
            -scheme LocalOCR \
            -testPlan LocalOCRUITests \
            -destination 'platform=macOS,arch=arm64' \
            -resultBundlePath TestResults/e2e.xcresult
      - name: Stop backend
        run: docker compose down
```

**Code signing for CI**: Unit tests run with `CODE_SIGNING_ALLOWED=NO`. E2E tests require a signed binary to launch correctly; the runner Keychain must have the Developer ID certificate installed. The signing identity is passed via the `DEVELOPMENT_TEAM` Xcode build setting, read from the `APPLE_TEAM_ID` GitHub secret.

---

#### Coverage Requirements

Coverage is measured via `xccov view --report TestResults/unit.xcresult` after each unit test run.

| Folder | Minimum Line Coverage | Rationale |
|---|---|---|
| `Networking/` (APIClient, Endpoints, AuthInterceptor, SSEClient) | **≥ 70%** | Core data path; bugs here affect all features |
| `State/` (AuthState, InventoryState, ShoppingState, FinanceState, etc.) | **≥ 70%** | Business logic layer; state mutations drive UI |
| `Components/` (all 26 components from §5.1) | **≥ 70%** | Already have 90 unit tests (§6.2) which cover the primary paths |
| `Views/` (all view files) | **≥ 50%** | UI-heavy; 75 integration tests (§6.3) cover the main flows |
| `Native/` (GlobalShortcutManager, MenuBarController, etc.) | **≥ 40%** | Platform-integration code is partially untestable without hardware |
| `Background/` (BackgroundFetchScheduler, NudgeScheduler) | **≥ 60%** | Scheduler logic must be tested; timing is mockable |
| `App/` (Router, AppState, AppDelegate) | **≥ 60%** | Routing logic drives all navigation; must be covered |

Folders below their coverage target fail CI with a message: "Coverage for [folder] is [X]%, below required [Y]%."

---

#### Flaky Test Policy

A test is classified as **flaky** if it fails in more than 3 out of 100 consecutive CI runs while the code under test is unchanged.

1. **Detection**: CI reports per-test pass rates in the `xcodebuild` result bundle. Any test with pass rate < 97% over the trailing 100 runs is flagged.
2. **Quarantine**: A flaky test is immediately moved to `LocalOCRTests/Quarantined/` (or `LocalOCRUITests/Quarantined/`) and excluded from the blocking test plan by adding it to a separate `QuarantinedTests.xctestplan` that runs in non-blocking CI mode.
3. **Blocking merge**: No PR may merge if a flaky test in the quarantine list was introduced in that PR (detected by `git blame` on the flaky test file).
4. **Resolution SLA**: Quarantined tests must be fixed or permanently removed within 2 sprints (approximately 4 weeks). After 2 sprints without resolution, the test is deleted and a `TODO` comment documents the missing coverage.
5. **Root causes tracked**: Flakiness root causes are documented in `LocalOCRTests/Quarantined/README.md` — typically: async timing issues (fix with `waitForExistence(timeout:)` on XCUIElement), missing `MockURLProtocol.requestLog` cleanup between tests, or test data ordering assumptions (fix with deterministic seeding).

---

#### Test File Map (complete)

```
LocalOCRTests/
├── ComponentTests/
│   ├── CardTests.swift                     # UC-001–005
│   ├── BadgeTests.swift                    # UC-006–010
│   ├── LowStockPillTests.swift             # UC-011–015
│   ├── CategoryChipTests.swift             # UC-016–020
│   ├── KeyValueRowTests.swift              # UC-021–025
│   ├── DropZoneTests.swift                 # UC-026–030
│   ├── ReceiptThumbnailTests.swift         # UC-031–035
│   ├── EmptyStateViewTests.swift           # UC-036–040
│   ├── SkeletonViewTests.swift             # UC-041–045
│   ├── ProgressBarViewTests.swift          # UC-046–050
│   ├── ToastTests.swift                    # UC-051–055
│   ├── SankeyWebViewTests.swift            # UC-056–060
│   ├── InlineEditableCellTests.swift       # UC-061–065
│   ├── ContextMenuModifiersTests.swift     # UC-066–070
│   ├── AttributionPickerTests.swift        # UC-071–075
│   ├── QRCodeViewTests.swift               # UC-076–080
│   ├── ModelPickerTests.swift              # UC-081–085
│   └── DemoModeBannerTests.swift           # UC-086–090
│
├── ViewTests/
│   ├── LoginViewTests.swift                # IV-001–005
│   ├── DashboardViewTests.swift            # IV-006–010
│   ├── OCRUploadViewTests.swift            # IV-011–015
│   ├── ReceiptReviewViewTests.swift        # IV-016–020
│   ├── InventoryViewTests.swift            # IV-021–025
│   ├── ShoppingListViewTests.swift         # IV-026–030
│   ├── FixedBillsViewTests.swift           # IV-031–035
│   ├── PlaidAccountsViewTests.swift        # IV-036–040
│   ├── CashTransactionsViewTests.swift     # IV-041–045
│   ├── SpendingByCategoryViewTests.swift   # IV-046–050
│   ├── ContributionsViewTests.swift        # IV-051–055
│   ├── AuthAndMembersViewTests.swift       # IV-056–060
│   ├── SettingsViewTests.swift             # IV-061–065
│   ├── MenuBarPopoverViewTests.swift       # IV-066–070
│   └── DemoModeOverlayTests.swift          # IV-071–075
│
├── NetworkingTests/
│   ├── APIClientTests.swift                # §5.8 Phase 8 items; HTTP error matrix §4.5
│   ├── ModelsTests.swift                   # JSON decode round-trips all Codable models
│   ├── KeychainStoreTests.swift            # Keychain read/write/delete; nothing in UserDefaults
│   ├── RouterTests.swift                   # URL scheme parsing: localocr:// deep links
│   └── SSEClientTests.swift               # SSE chunk parsing; streaming model response assembly
│
├── StateTests/
│   ├── AuthStateTests.swift                # login/logout/checkSession; demo mode toggle
│   ├── DemoModeGateTests.swift             # write actions blocked; read actions pass through
│   ├── InventoryStateTests.swift           # lowStockItems computed; updateQuantity optimistic
│   └── ShoppingStateTests.swift           # addItem/togglePurchased/populateFromRecs
│
├── Helpers/
│   ├── MockURLProtocol.swift               # URLProtocol subclass for all HTTP mocking
│   └── XCTestCase+Fixtures.swift           # Helper: `fixtureURL(_ name: String) -> URL`
│
└── Fixtures/
    └── [all .json and sample receipt files listed above]

LocalOCRUITests/
├── DailyInventoryWalkerTests.swift         # E2E Script 1
├── ReceiptUploaderTests.swift              # E2E Script 2
├── BillPayWatcherTests.swift               # E2E Script 3
├── AnalystTests.swift                      # E2E Script 4
├── DockDropTests.swift                     # E2E Script 5
├── DeepLinkTests.swift                     # E2E Script 6
├── NotificationTests.swift                 # E2E Script 7
├── MacOSSpecificTests.swift                # §6.5 scenarios 1–46
├── Helpers/
│   └── SeedHelper.swift                    # Live backend seed/teardown
└── Fixtures/
    ├── sample-receipt.pdf
    ├── sample-receipt.png
    ├── sample-receipt.jpg
    └── sample-receipt.heic
```

---

*End of Section 6 — TEST PLAN*

---

## 7. REVIEW & CONFLICT RESOLUTION

**Author**: Agent 7 — Senior Reviewer  
**Date**: 2026-05-19  
**Review scope**: Full cross-sectional traceability pass across Sections 1–6 (~6,900 lines / ~70 k words). Every conflict raised in §7.1 carries **VETO** status — the plan must not enter Phase 1 implementation until each ✗ row is resolved.

---

### 7.1 CONFLICTS FOUND

Conflicts are facts where two or more sections give materially different, mutually exclusive guidance to a developer. Each row names the canonical source (§A), the contradicting source (§B), the exact discrepancy, the build impact if unresolved, and the required resolution.

#### C-1 — Settings Pane Count and Names (VETO)

| Field | Value |
|-------|-------|
| **§A (canonical candidate)** | §3.2 window catalogue + §3.8 Preferences spec |
| **§B (contradicting)** | §4.7 Window 2 spec + §4.2 file tree + §5.2 SettingsView |
| **Discrepancy** | §3.2/§3.8 define **5 panes**: General, Account, Receipts, Notifications, Advanced. §4.7/§4.2/§5.2 define **8 panes**: General, Account, AI Models, Trusted Devices, Telegram, Notifications, Backup, Advanced. The §3.8 "Receipts" pane has no file in §4.2 (`ReceiptsPane.swift` absent from tree). The 3 panes present in §4.x/§5.x but absent from §3.8 are: AI Models, Trusted Devices, Telegram. |
| **Build impact** | Phase 6 (Preferences Window) developer receives two irreconcilable pane lists. Either 3 panes are built with zero design spec (§3.8 coverage gap) or a "Receipts" pane is built with no file target (§4.2 gap). Either outcome ships incomplete preferences UI. |
| **Resolution required** | Adopt the **8-pane list** from §4.7/§5.2 as authoritative (it was written by the architecture agent with backend knowledge). §3.8 must be extended with design specs for **AI Models**, **Trusted Devices**, and **Telegram** panes, and the "Receipts" pane must either be renamed/mapped to an existing pane or assigned a new file `ReceiptsPane.swift` in §4.2. A §3.8 addendum is sufficient — do not renumber sections. |
| **Status** | ✗ UNRESOLVED |

#### C-2 — Reusable Component Count Mismatch (VETO)

| Field | Value |
|-------|-------|
| **§A (canonical candidate)** | §3.6 header: "26 reusable components" |
| **§B (contradicting)** | §3.6 table body (rows 1–29) + §5.1 implementation list (29 components) |
| **Discrepancy** | The §3.6 table contains **29 named entries**: PrimaryButton, SecondaryButton, DestructiveButton, LoadingButton, SearchBar, FilterChip, FilterChipBar, SortMenu, PaginationBar, ReceiptThumbnail, ReceiptCardView, ItemRowView, ItemBadge, StatusBadge, CategoryIcon, CurrencyField, ConfirmationDialog, ToastView, ToastQueue, EmptyStateView, ErrorBanner, SectionHeader, SidebarBadge, ProgressRing, SankeyChartView, SparklineView, SpendingRingView, DemoModeBanner, ContextMenuModifiers. The header and §5.1 narrative both state "26". Delta = 3. |
| **Build impact** | UC-001 through UC-090 unit tests are scoped to "26 components". The 3 surplus components (whichever are the additions: ContextMenuModifiers, DemoModeBanner, and one of the chart views) have no UC- test IDs assigned. Test matrix is incomplete by ≥3 test blocks. |
| **Resolution required** | Audit the 29 entries and confirm the true count. Update the §3.6 header to match. Assign UC-091 through UC-09N to the unassigned components. §6.1 test table must be updated accordingly. |
| **Status** | ✗ UNRESOLVED |

#### C-3 — PreferencesStore `inventoryAlertsEnabled` Setter Writes Wrong Key (CODE BUG / VETO)

| Field | Value |
|-------|-------|
| **§A (spec intent)** | §5.6 PreferencesStore — `inventoryAlertsEnabled` property controls whether low-stock alerts are shown |
| **§B (contradicting)** | §5.6 PreferencesStore code listing |
| **Discrepancy** | The **getter** reads `"LocalOCR.inventoryAlertsEnabled"` (correct). The **setter** writes to `"LocalOCR.nudgeMinThreshold"` (wrong). This silently overwrites the nudge minimum threshold every time the alerts toggle is changed, and the actual `inventoryAlertsEnabled` key is never written — so the toggle state is never persisted. |
| **Build impact** | Two bugs in one: (1) `inventoryAlertsEnabled` always reads back as `false` after app restart because it was never stored. (2) `nudgeMinThreshold` is corrupted to `0` or `1` (Bool cast to Int) whenever the toggle fires. Inventory nudge job will either never fire or fire on every item. |
| **Exact fix** | Change setter key from `"LocalOCR.nudgeMinThreshold"` to `"LocalOCR.inventoryAlertsEnabled"`. One character-set change in the code listing in §5.6. |
| **Status** | ✗ UNRESOLVED — fix must be applied to §5.6 before Phase 5 implementation |

#### C-4 — CSRF Token Handling Marked Unconfirmed in §4.5

| Field | Value |
|-------|-------|
| **§A (spec)** | §4.5 API integration strategy |
| **§B (contradicting)** | §4.5 inline note: "[UNCONFIRMED — must verify against `manage_authentication.py`]" |
| **Discrepancy** | The plan does not specify whether the macOS APIClient must obtain and attach a CSRF token on mutating requests. The Flask backend uses Flask-WTF or similar CSRF protection on some routes. If CSRF is required, every POST/PUT/DELETE in `Endpoints.swift` that lacks the token will receive 400/403. If CSRF is not required (API routes exempt), then no action needed. The plan ships this question unanswered. |
| **Build impact** | Phase 3 (API integration) will fail for all mutating endpoints if CSRF is required but not implemented. Debugging this mid-phase is expensive. |
| **Resolution required** | Before Phase 1 kickoff: inspect `manage_authentication.py` and the Flask app factory for `csrf.exempt()` or `@csrf.exempt` on API blueprints. Document the finding in §4.5. If CSRF tokens are required, add a `fetchCSRFToken()` step to `APIClient.request()` and a `X-CSRFToken` header injection. |
| **Status** | ✗ UNRESOLVED — prerequisite for Phase 1 |

#### C-5 — Bearer Token Auth Path Unconfirmed in §4.5

| Field | Value |
|-------|-------|
| **§A (spec)** | §4.5 API integration strategy |
| **§B (contradicting)** | §4.5 inline note: "[UNCONFIRMED — the web app stores an `api_token` in `localStorage`; verify if the macOS app should use this path]" |
| **Discrepancy** | §4.5 describes two possible auth paths: (a) session cookie via `HTTPCookieStorage.shared`, and (b) Bearer token via `Authorization: Bearer <api_token>` header. The plan does not commit to either path. The KeychainAccess integration in §4.6 stores "session token" — but it is unclear whether this is a cookie jar backup or a Bearer token string. |
| **Build impact** | If the wrong auth path is implemented in Phase 3, all authenticated requests fail silently (redirected to login rather than 401, because Flask session-based auth returns 302). The entire app integration layer must be rewritten. |
| **Resolution required** | Inspect `manage_authentication.py` for `current_user` resolution — does it check `request.cookies` (session) or `request.headers.get('Authorization')` (Bearer)? Document in §4.5. Update §4.6 Keychain integration description to specify exactly what string is stored. |
| **Status** | ✗ UNRESOLVED — prerequisite for Phase 1 |

---

*§7.1 saved — 5 conflicts documented (C-1 through C-5)*

---

### 7.2 GAPS FOUND

Gaps are missing content — things the plan implies or requires but never specifies. Unlike conflicts, gaps are not contradictions; they are simply absent. Each gap is graded by impact on build fidelity.

| ID | Gap description | Sections affected | Impact | Resolution |
|----|----------------|-------------------|--------|------------|
| **G-1** | **AC-02 / Rule 11 untestable in v1.0** — §2.6 AC-02 states all 11 business rules from §1.7 must be preserved. Rule 11 is "AI chat guardrails (no financial advice, etc.)". AI Chat is explicitly deferred to v1.1 (§2.4). No §6 test covers Rule 11. AC-02 cannot pass for v1.0 as written. | §1.7 R-11, §2.4, §2.6 AC-02, §6 | Medium — AC-02 will fail on paper. Reviewer marking the AC table will see a red cell. | Amend AC-02 to read "all 11 business rules except R-11 (Chat, v1.1)" or create a placeholder test that verifies the chat endpoint returns a non-200 until v1.1 ships. |
| **G-2** | **`weeklySummaryEnabled` referenced but never configured** — §5.6 PreferencesStore defines `weeklySummaryEnabled: Bool` with a UserDefaults key. No preferences pane (in either the §3.8 5-pane or §4.7 8-pane list) exposes a UI toggle for this field. No §6 test exercises it. No backend route is mapped to a weekly summary email/notification. | §5.6, §3.8, §4.7, §6 | Low — dead property; wastes no runtime, but confuses developers and implies unreachable functionality. | Either (a) add a "Weekly Summary" toggle to the Notifications pane spec (§3.8 / §4.7) and assign a UC- test, or (b) remove the property from §5.6 and note it as v1.1. |
| **G-3** | **Multi-window side-by-side scenario has no E2E test** — §2.3 Desktop-Exclusive Feature #6 specifies "Multi-window: Inventory + Shopping List simultaneously in split screen". §4.7 defines the two window types. No E2E script in §6.4 tests opening both windows, populating inventory in one, and observing auto-populate in the other. | §2.3 #6, §4.7, §6.4 | Medium — feature ships untested under E2E automation. First regression will be found by a user. | Add E2E Script 8: `MultiWindowTests.swift` — open Main Window + Shopping List window, run inventory walker in one, assert shopping list updates in other. Add to §6.4 and §6.6 test tree. |
| **G-4** | **IV-019 (diff mode) missing non-deletion assertion** — §1.7 Rule 3: "Existing items are never auto-deleted by a re-run." §5.2 InventoryView diff mode spec correctly shows strikethrough for removed items. IV-019 checks for green (added) and strikethrough (removed) cells but does not assert that the total item count after merge ≥ count before merge (the non-deletion invariant). | §1.7 R-3, §5.2, §6.2 IV-019 | Low — gap in test fidelity; Rule 3 regression can slip through. | Amend IV-019 to add: `XCTAssertGreaterThanOrEqual(postMergeCount, preMergeCount, "Items must never be auto-deleted")`. |
| **G-5** | **No teardown spec for ASWebAuthenticationSession (Google OAuth)** — §4.6 Integration 7 (Google Drive OAuth) and §4.6 Integration 8 (Google Sheets) both use `ASWebAuthenticationSession`. The plan specifies initiating the auth flow but does not specify: (a) where the OAuth callback URL is registered in the entitlements, (b) what happens on cancellation (user closes the browser sheet), (c) token refresh flow. | §4.6 Int-7/8, §5.x | Medium — OAuth flows are notoriously difficult to implement from incomplete specs. Missing cancellation handling leads to hung async tasks. | Extend §4.6 Integration 7/8 with: callback URL format (`localocr://oauth/google`), cancellation handler, and token refresh strategy (store refresh token in Keychain, refresh on 401). |
| **G-6** | **No error recovery path for Plaid Link sheet** — §4.6 Integration 9 uses `ASWebAuthenticationSession` for Plaid Link. The plan specifies success but not: (a) Plaid `EXIT` callback (user cancels), (b) Plaid error codes, (c) what the UI shows on link failure. §5.2 BillsView has a "Link Bank" button but no error state. | §4.6 Int-9, §5.2 BillsView | Medium — Plaid flows have multiple exit reasons; silent failure frustrates users. | Add error state to §5.2 BillsView and §4.6 Int-9: on Plaid EXIT, show ErrorBanner with "Bank link cancelled" + retry button. |
| **G-7** | **Phase 0 prerequisite: Apple Developer Program enrollment not gated** — §5.8 Phase 0 lists prerequisites but does not include "Apple Developer Program membership active ($99/yr)". Without enrollment, `xcodebuild -exportArchive` with Developer ID signing fails at the codesign step. Phase 9 distribution commands will fail silently until enrollment is confirmed. | §5.8 Phase 0, §4.9 | Low (process) — builds fine locally unsigned; only matters at distribution. | Add to §5.8 Phase 0 checklist: "[ ] Apple Developer Program membership confirmed active for chatwithllm@gmail.com". |
| **G-8** | **`localocr://` URL scheme not registered in Info.plist spec** — §5.3 and §4.6 Integration 12 reference the `localocr://` deep link scheme, and E2E Script 6 tests it. §4.2 file tree includes `Info.plist` but §5.x never shows the `CFBundleURLTypes` entry required to register the scheme. Without it, `open localocr://receipt/123` silently does nothing — the app is never launched. | §4.6 Int-12, §5.3, §6.4 Script 6, §4.2 | Medium — E2E Script 6 will always fail unless scheme is registered. | Add to §4.2 or §4.6 Int-12 the required `Info.plist` snippet: `CFBundleURLTypes → CFBundleURLSchemes → localocr`. |
| **G-9** | **No migration plan for existing web users** — §1 and §2 both acknowledge the existing Flask/SQLite production app. The macOS app connects to the same backend. However, no section addresses: (a) what happens to users who have data in the web app and install the macOS app, (b) session conflicts (web tab open + macOS app open simultaneously), (c) multi-device sync (two Macs). | §1, §2, §4.5 | Low (v1.0) — most v1.0 users are likely the solo user described in §1.1. Multi-device is a v1.x concern. | Add a note in §2.5 (or new §2.7): macOS app is additive client; no data migration needed; simultaneous sessions supported by Flask's server-side session store; multi-device out of scope for v1.0. |
| **G-10** | **`SpendingRingView` uses SwiftCharts but §4.3 doesn't list Charts framework as SPM dep** — §3.6 SpendingRingView and §5.1 use `Charts` (SwiftCharts). §4.3 SPM dependencies list only `KeychainAccess` and `Kingfisher`. `Charts` is a first-party Apple framework (macOS 13+) in the SDK — not an SPM package — but it is also not listed in §4.6's "Apple frameworks used". | §3.6, §4.3, §4.6 | Low — developer may forget to add `import Charts` and the framework to the Xcode target. | Add `Charts` to the §4.6 Apple frameworks list. No SPM entry needed. |

---

*§7.2 saved — 10 gaps documented (G-1 through G-10)*

---

### 7.3 macOS-SPECIFIC RISK REGISTER

Risks below are distinct from conflicts and gaps — they are real platform behaviours, Apple policy constraints, or architectural choices that could cause schedule slippage, App Store rejection, or runtime failures specific to macOS. Each risk is scored Likelihood (L) and Impact (I) on a 1–3 scale (1=low, 3=high). Mitigations reference specific sections of the plan.

| ID | Risk | L | I | LxI | Mitigation |
|----|------|---|---|-----|------------|
| **R-01** | **Notarization rejections due to non-sandboxed entitlements** — The plan explicitly omits `com.apple.security.app-sandbox` (§4.6). Apple notarization does **not** require sandbox for Developer ID apps, but it does require Hardened Runtime + stapling. If any entitlement is declared but the binary never exercises it (e.g., camera entitlement if OCR uses a server-side path), Apple's automated scans may flag it. More critically: if any dynamic library or framework linked by SPM packages is not signed or does not have the correct team ID, notarization fails. | 2 | 3 | 6 | (1) Strip any entitlement not exercised in v1.0. (2) Verify all SPM dependency `.framework` products are signed by their publishers. (3) Run `xcrun notarytool submit` on a Phase 2 prototype before Phase 3 begins. Add to §5.8 Phase 2 exit criteria. |
| **R-02** | **`WKWebView` requires `com.apple.security.network.client` entitlement AND allowlisting in macOS 14+ privacy framework** — §3.6 SankeyChartView uses WKWebView to render a local D3/HTML chart. On macOS 14+, WKWebView loading `file://` URLs for local HTML requires `webView(_:decidePolicy:decisionHandler:)` policy to explicitly allow `file://` navigation. Without this, the Sankey chart shows a blank white pane silently. | 2 | 2 | 4 | Add to §5.1 SankeyChartView implementation: `WKNavigationDelegate` with `navigationAction.request.url?.isFileURL` guard and `.allow` policy. Add to §6.1 UC for SankeyChartView: assert chart frame is non-zero after load. |
| **R-03** | **`NavigationSplitView` column collapse on small MacBook screens** — §3.2 specifies minimum window size 1024×768. NavigationSplitView on macOS 13 auto-collapses the sidebar at widths < ~768 px. If a user resizes below 1024 px (possible despite the minimum — NSWindow minimum size is advisory, not enforced by SwiftUI alone), the sidebar vanishes and navigation breaks. | 2 | 2 | 4 | In §5.2 MainSplitView: enforce minimum window size via `NSWindow.setContentMinSize` in the AppDelegate/`onAppear` modifier. Add to §6.5 macOS-specific tests: resize to 900×600 and assert sidebar still visible. |
| **R-04** | **`UserNotifications` + Focus Filters on macOS 13** — §4.6 Integration 1 uses `UNUserNotificationCenter`. On macOS 13+, notifications delivered while the user has a Focus mode active may be silently suppressed. The plan has no handling for `UNNotificationResponse` arriving after Focus ends (deferred delivery). The nudge job (§5.7) fires at 09:30 via APScheduler — if Focus blocks it, the notification is lost, not queued. | 2 | 2 | 4 | Document in §4.6 Int-1: set `UNMutableNotificationContent.interruptionLevel = .timeSensitive` for low-stock nudges (requires user permission for Time Sensitive delivery). Add a fallback: if notification permission is `.denied`, fall back to in-app banner via ToastQueue. |
| **R-05** | **`ServiceManagement` launch-at-login API changed in macOS 13** — §4.6 Integration 6 uses `ServiceManagement` for launch-at-login. The **old** `SMLoginItemSetEnabled` API is deprecated in macOS 13; the **new** `SMAppService.mainApp.register()` API is required on macOS 13+. The plan (§4.6 Int-6) does not specify which API is used. Using the old API compiles but shows a deprecation warning and may not work on macOS 14+. | 3 | 2 | 6 | Update §4.6 Int-6 to explicitly state: use `SMAppService.mainApp.register()` (macOS 13+). Since the minimum deployment target is macOS 13, no availability guard is needed. Remove any reference to `SMLoginItemSetEnabled`. |
| **R-06** | **`@Observable` / `@Bindable` used in §5 code despite macOS 13 minimum** — §4.1 correctly gates `@Observable` behind `@available(macOS 14, *)`. However, §5.2 and §5.6 code listings use `@Published` + `ObservableObject` throughout (correct). Risk: a developer following the §4.1 note may attempt to use `@Observable` for convenience and ship a crash on macOS 13. | 2 | 3 | 6 | Add a lint rule note to §5.8 Phase 1: "SwiftLint rule `no_observable_macro` — ban `@Observable` without availability guard until minimum deployment target is raised to macOS 14." |
| **R-07** | **Backend URL hardcoded to `localhost:5000` in demo mode** — §4.4 environment config shows `DEBUG_BASE_URL = "http://localhost:5000"`. DemoMode (§5.6 DemoModeGate) blocks mutating calls but still issues GET requests to the live backend. If the backend is not running on the review machine (e.g., App Store review — though this is Developer ID, not App Store), the app shows spinners rather than demo data. | 1 | 3 | 3 | Confirm §4.4: demo mode should serve **static fixture JSON** rather than hitting `localhost:5000`. If fixtures are the intent (likely), the `isDemoMode` flag in `APIClient.request()` must intercept GETs too and return fixture data. Clarify in §4.4 and §5.6. |
| **R-08** | **Drag-and-drop from Finder requires `NSItemProvider` async API on macOS 13** — §4.6 Integration 3 (Dock drop target) and §3.x context menus reference drag-drop for receipt upload. On macOS 13, `.onDrop(of:isTargeted:perform:)` with `NSItemProvider.loadObject(ofClass:)` is the correct async path. The plan does not show the `NSItemProvider` call; developers may use the deprecated synchronous `loadItem(forTypeIdentifier:)` which does not work for sandboxed/hardened processes. | 2 | 2 | 4 | Add to §5.1 or §4.6 Int-3 the correct async pattern: `provider.loadFileRepresentation(forTypeIdentifier: UTType.pdf.identifier) { url, error in … }`. |
| **R-09** | **Keychain access group not specified for potential multi-app sharing** — §4.6 Int-5 uses `KeychainAccess` to store credentials. If a companion iOS app or Safari extension is ever planned, the Keychain item must be stored under a shared access group (`kSecAttrAccessGroup`). Without it, data is locked to the single app's Keychain partition and cannot be migrated. | 1 | 2 | 2 | Low priority for v1.0. Document in §4.6 Int-5: access group is `nil` (app-private) in v1.0; set `service = "com.localocr.extended"` consistently to ease future migration. |
| **R-10** | **`CoreSpotlight` indexing privacy — financial data** — §4.6 Int-11 indexes receipt content in Spotlight. Receipt descriptions, vendor names, and amounts are indexed as searchable attributes. On a shared Mac, another user account running Spotlight would not see another user's indexed items (Spotlight index is per-user). However, if the Mac is left unlocked, any logged-in user can run `mdfind "kMDItemContentType == 'com.localocr.receipt'"` and see receipt metadata in plaintext. | 2 | 3 | 6 | Add to §4.6 Int-11: set `CSSearchableItemAttributeSet.isUserActivity = false` and do **not** index `displayName` or `contentDescription` with the full amount. Index only category + date. Add a privacy note to §1.5 or §2.1. |
| **R-11** | **APScheduler running inside macOS app process — app quit kills the job** — §5.7 nudge job uses APScheduler at 09:30. APScheduler runs in the same process as the Flask backend (or in the macOS app process if the scheduler is client-side). If the macOS app is not running at 09:30, the nudge never fires. The plan does not address this. | 3 | 2 | 6 | Clarify in §5.7: the APScheduler instance lives in the **Flask backend** (already deployed, always running). The macOS app merely receives the `UNNotification` pushed by the backend via the `nudge_job` POST to a local notification endpoint. If the backend runs on a server, this works. If backend is `localhost` only, add a fallback: schedule a local `UNCalendarNotificationTrigger` at 09:30 from the macOS app side as backup. |
| **R-12** | **SwiftUI `List` selection binding crashes on macOS 13.0–13.2 with `Optional<Set>`** — Known bug in early macOS 13 releases: `List(selection: $selection)` where `selection` is `Optional<Set<Item.ID>>` triggers a runtime assertion if the selection is set programmatically before the List renders. §5.2 InventoryView and ReceiptsView both use multi-selection Lists. | 2 | 2 | 4 | Add to §5.8 Phase 1: minimum tested OS is macOS 13.3+. Add to §6.1 test matrix P0 hardware: "macOS 13.3 minimum (not 13.0)". Use `.optional` selection binding workaround or initialize selection as `Set<>()` (non-optional) if macOS 13.3+ is confirmed minimum. |

---

*§7.3 saved — 12 risks documented (R-01 through R-12)*

---

### 7.4 HANDOFF CHECKLIST

The following items must all be ✅ before a developer begins Phase 1 (§5.8). Items currently ❌ map to a conflict (C-x) or gap (G-x) that must be resolved first. Items marked ⚠️ are advisory — implementation can begin but the item must be resolved before the phase it blocks.

#### Pre-Phase-1 Gate (must all be ✅ before code is written)

| # | Item | Status | Blocker ref |
|---|------|--------|-------------|
| 1 | §4.5 CSRF token handling confirmed (exempt or required + implemented) | ❌ | C-4 |
| 2 | §4.5 Bearer vs. cookie auth path confirmed and documented | ❌ | C-5 |
| 3 | §3.6 component count corrected and all components have UC- test IDs | ❌ | C-2 |
| 4 | §5.6 `inventoryAlertsEnabled` setter key bug fixed | ❌ | C-3 |
| 5 | Apple Developer Program membership confirmed active | ❌ | G-7 |
| 6 | `localocr://` URL scheme `CFBundleURLTypes` entry added to §4.2 Info.plist spec | ❌ | G-8 |
| 7 | `Charts` framework added to §4.6 Apple frameworks list | ❌ | G-10 |

#### Pre-Phase-6 Gate (Preferences Window — must all be ✅ before Phase 6 begins)

| # | Item | Status | Blocker ref |
|---|------|--------|-------------|
| 8 | §3.8 extended with design specs for AI Models, Trusted Devices, Telegram panes | ❌ | C-1 |
| 9 | §4.2 file tree updated: `ReceiptsPane.swift` added or §3.8 "Receipts" pane mapped to correct file | ❌ | C-1 |
| 10 | `weeklySummaryEnabled` either wired to a UI toggle or removed as v1.1 | ❌ | G-2 |

#### Pre-Phase-8 Gate (Test & QA — must all be ✅ before test phase begins)

| # | Item | Status | Blocker ref |
|---|------|--------|-------------|
| 11 | §6.4 E2E Script 8 (MultiWindowTests.swift) added for §2.3 feature #6 | ❌ | G-3 |
| 12 | IV-019 amended with non-deletion assertion for §1.7 Rule 3 | ❌ | G-4 |
| 13 | AC-02 amended to exclude R-11 (Chat guardrails, v1.1) or placeholder test added | ❌ | G-1 |
| 14 | §6.6 test tree updated to include `MultiWindowTests.swift` | ❌ | G-3 |

#### Advisory (implement during relevant phase, not a hard gate)

| # | Item | Status | Phase | Risk ref |
|---|------|--------|-------|----------|
| 15 | SankeyChartView WKWebView `file://` navigation policy delegate implemented | ⚠️ | Phase 3 | R-02 |
| 16 | NSWindow minimum size enforced in MainSplitView (`setContentMinSize`) | ⚠️ | Phase 2 | R-03 |
| 17 | UNNotification `interruptionLevel = .timeSensitive` set for nudge alerts | ⚠️ | Phase 4 | R-04 |
| 18 | `SMAppService.mainApp.register()` used (not deprecated `SMLoginItemSetEnabled`) | ⚠️ | Phase 4 | R-05 |
| 19 | SwiftLint rule or code comment banning `@Observable` without macOS 14 guard | ⚠️ | Phase 1 | R-06 |
| 20 | Demo mode confirmed to serve static fixture JSON (not live `localhost:5000` GETs) | ⚠️ | Phase 3 | R-07 |
| 21 | Drag-drop uses async `loadFileRepresentation` not deprecated `loadItem` | ⚠️ | Phase 4 | R-08 |
| 22 | Notarization smoke test run on Phase 2 prototype before Phase 3 begins | ⚠️ | Phase 2 | R-01 |
| 23 | CoreSpotlight indexes only category + date (not amount/vendor plaintext) | ⚠️ | Phase 5 | R-10 |
| 24 | APScheduler clarified: backend-side vs. macOS-app-side + local UNCalendarNotificationTrigger fallback documented | ⚠️ | Phase 4 | R-11 |
| 25 | ASWebAuthenticationSession: Google OAuth cancellation + token refresh path documented in §4.6 | ⚠️ | Phase 3 | G-5 |
| 26 | Plaid Link EXIT/error handling documented in §4.6 and §5.2 BillsView | ⚠️ | Phase 3 | G-6 |
| 27 | Test matrix P0 minimum OS noted as macOS 13.3+ (not 13.0) | ⚠️ | Phase 8 | R-12 |

#### Already Verified ✅

| # | Item |
|---|------|
| 28 | §3.3 all 81 menu items have corresponding `AppMenuCommands.swift` entries in §5.4 |
| 29 | §3.4 all 62 keyboard shortcuts have implementations in §5.5 (Categories A/B/C/D) |
| 30 | §3.7 all 18 views have §5.2 counterpart specs (16 MVP + MenuBarPopoverView + DemoModeOverlay) |
| 31 | §4.3 SPM dependencies (KeychainAccess 4.2.2, Kingfisher 7.12.0) pinned to exact version + commit |
| 32 | §6.1 90 UC- tests cover all 26 listed component names in §3.6 table (coverage for 3 surplus components is gapped, see C-2) |
| 33 | §6.2 IV-001 through IV-075 cover all 18 view specs from §3.7 + §5.2 |
| 34 | §6.4 7 E2E scripts cover the 7 named user journey scenarios from §2.4 |
| 35 | §1.7 Rules 1–10 each have explicit test assertions in §6 (Rule 11 excepted, see G-1) |
| 36 | §4.6 Keychain usage confirmed: auth tokens stored in Keychain, NEVER UserDefaults |
| 37 | §4.6 entitlements: `app-sandbox` intentionally absent, Hardened Runtime enabled, rationale documented |
| 38 | §5.3 `Endpoints.swift` enum covers all 216 backend routes identified in §1.6 |
| 39 | §4.7 all 6 window types have implementation specs |
| 40 | §5.8 9 build phases defined with exit criteria |

---

*§7.4 saved — 40 checklist items (7 ❌ hard gates, 13 ⚠️ advisory, 13 ✅ verified)*

---

### 7.5 FINAL CONFIDENCE SCORES

Scores are on a 0–10 scale. 10 = "hand this to a developer with no clarifying questions". Rationale is provided so resolving the open items produces a measurable score improvement.

#### Dimension Scores

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Completeness** | **7.0 / 10** | Sections 1–5 cover an extraordinary breadth: full API inventory (216 routes), complete component library (29 entries), all 18 views with ASCII trees and mutation specs, all 62 shortcuts, all 81 menu items, 9 build phases. Deductions: C-1 (Settings pane split — 3 panes have zero design spec), G-5/G-6 (OAuth/Plaid incomplete paths), G-8 (URL scheme registration absent from Info.plist spec). Resolving C-1 + G-5 + G-6 + G-8 would push this to 8.5. |
| **Buildability** | **6.5 / 10** | The §5 code listings are production-grade Swift and directly usable. Deductions: C-3 (code bug — wrong UserDefaults key ships a silent data corruption), C-4 + C-5 (auth path unconfirmed — the entire networking layer cannot be implemented until resolved), C-1 (Preferences window phase has conflicting instructions). These are not cosmetic — they are load-bearing. Resolving C-3 + C-4 + C-5 alone would push buildability to 8.0. |
| **Testability** | **7.5 / 10** | 90 + 75 + 7 tests is impressive coverage. IV-tests are detailed with XCT assertions. E2E scripts are realistic and runnable. Deductions: C-2 (3 components have no UC- IDs), G-1 (AC-02 / Rule 11 gap), G-3 (no multi-window E2E), G-4 (IV-019 missing non-deletion assertion), R-12 (macOS 13.0–13.2 crash risk in List selection). Resolving these would push testability to 9.0. |
| **Risk Management** | **6.0 / 10** | Section 4 identifies platform choices thoughtfully. Deductions: R-01 (notarization not smoke-tested until Phase 9 — too late), R-05 (wrong ServiceManagement API specified by omission), R-10 (financial data in Spotlight plaintext is a privacy risk), R-11 (APScheduler lifecycle ambiguity). These are real macOS traps that commonly surprise web-to-native migrations. Resolving R-05 + R-10 + R-11 would push this to 7.5. |

#### Overall Score

```
Overall = mean(Completeness, Buildability, Testability, Risk Management)
        = mean(7.0, 6.5, 7.5, 6.0)
        = 6.75 / 10
```

**Rounded: 7 / 10**

The plan is in the "solid draft" tier — it is far better than a skeleton spec and contains genuine engineering depth. It is **not yet in the "ship to developer" tier** because 5 conflicts remain open, 2 of which (C-4, C-5) block the first line of networking code and 1 of which (C-3) is a concrete code bug. Resolving all 7 hard-gate items in §7.4 would push the overall score to approximately **8.5 / 10**, which clears the bar for Phase 1 kickoff.

#### Score After All Resolutions (Projected)

| Dimension | Current | Post-resolution |
|-----------|---------|----------------|
| Completeness | 7.0 | 8.5 |
| Buildability | 6.5 | 8.5 |
| Testability | 7.5 | 9.0 |
| Risk Management | 6.0 | 7.5 |
| **Overall** | **6.75** | **8.4** |

---

### 7.6 SUMMARY

**Review conducted by**: Agent 7 — Senior Reviewer  
**Review date**: 2026-05-19  
**Lines reviewed**: ~6,900 (Sections 1–6)  
**Traceability checkpoints verified**: 10 of 10 specified in brief (§1.7→§2.6→§5.2→§6.3; §2.3→§3.x→§4.6→§5.x; §3.3→§5.4; §3.4→§5.5; §3.6→§5.1; §3.7→§5.2; §4.3→§5.x; §6→§3/§5)

**Conflicts found**: 5 (C-1 through C-5) — all carry VETO status  
**Gaps found**: 10 (G-1 through G-10)  
**macOS-specific risks identified**: 12 (R-01 through R-12)  
**Hard-gate blockers for Phase 1**: 7 items (see §7.4 items 1–7)  
**Advisory items**: 13 items (see §7.4 items 15–27)  
**Items already verified ✅**: 13 items (see §7.4 items 28–40)

**VETO STATUS**: Plan is **VETOED** for Phase 1 kickoff until §7.4 items 1–7 (hard gates) are resolved. The auth path conflicts (C-4, C-5) alone prevent any networking code from being written correctly. The code bug (C-3) would ship a data corruption on day one. The Settings pane conflict (C-1) would cause a Phase 6 rebuild.

**Recommended next action**: Assign a single agent or developer to resolve §7.4 items 1–7 in order. Estimated effort: 2–4 hours of backend inspection (C-4, C-5), 30 minutes of §5.6 fix (C-3), 3–4 hours of §3.8 design spec extension (C-1), 1 hour of count audit and test ID assignment (C-2). Total: ~8 hours. After resolution, re-score and lift VETO.

---

*End of Section 7 — REVIEW & CONFLICT RESOLUTION*  
*End of MACOS_APP_PLAN.md*
