# Graph Report - src  (2026-05-01)

## Corpus Check
- 60 files · ~195,792 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1239 nodes · 5544 edges · 22 communities detected
- Extraction: 36% EXTRACTED · 64% INFERRED · 0% AMBIGUOUS · INFERRED: 3563 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Rationale Comments (Misc Backend)|Rationale Comments (Misc Backend)]]
- [[_COMMUNITY_Contribution Scoring Rationale|Contribution Scoring Rationale]]
- [[_COMMUNITY_Bill Cadence & Budget Categories|Bill Cadence & Budget Categories]]
- [[_COMMUNITY_Inventory & Contribution Logic|Inventory & Contribution Logic]]
- [[_COMMUNITY_Flask App Bootstrap|Flask App Bootstrap]]
- [[_COMMUNITY_Image Backfill & Threshold Checks|Image Backfill & Threshold Checks]]
- [[_COMMUNITY_AI Vision Receipt OCR|AI Vision Receipt OCR]]
- [[_COMMUNITY_Plaid Integration|Plaid Integration]]
- [[_COMMUNITY_Chat Assistant|Chat Assistant]]
- [[_COMMUNITY_Frontend Overscroll Navigation|Frontend: Overscroll Navigation]]
- [[_COMMUNITY_MQTT Event Publishing|MQTT Event Publishing]]
- [[_COMMUNITY_Bill Planning & Cash Transactions|Bill Planning & Cash Transactions]]
- [[_COMMUNITY_Receipt Filename Index|Receipt Filename Index]]
- [[_COMMUNITY_Telegram Message Handler|Telegram Message Handler]]
- [[_COMMUNITY_Backup & Environment Ops|Backup & Environment Ops]]
- [[_COMMUNITY_Product Snapshots|Product Snapshots]]
- [[_COMMUNITY_Telegram Webhook Config|Telegram Webhook Config]]
- [[_COMMUNITY_Frontend Page Pager|Frontend: Page Pager]]
- [[_COMMUNITY_Frontend Upload Result Renderer|Frontend: Upload Result Renderer]]
- [[_COMMUNITY_Store Management|Store Management]]
- [[_COMMUNITY_Kitchen Catalog|Kitchen Catalog]]
- [[_COMMUNITY_Backend Package Init|Backend Package Init]]

## God Nodes (most connected - your core abstractions)
1. `Purchase` - 264 edges
2. `Product` - 249 edges
3. `ReceiptItem` - 218 edges
4. `Store` - 209 edges
5. `User` - 204 edges
6. `TelegramReceipt` - 159 edges
7. `PlaidStagedTransaction` - 143 edges
8. `PriceHistory` - 141 edges
9. `Inventory` - 121 edges
10. `BillMeta` - 110 edges

## Surprising Connections (you probably didn't know these)
- `Helpers for standardizing store names and merging obvious duplicates.  Also expo` --uses--> `Store`  [INFERRED]
  backend/normalize_store_names.py → backend/initialize_database_schema.py
- `Return True when ``name`` looks like a bank/CC artifact, not a store.      Used` --uses--> `Store`  [INFERRED]
  backend/normalize_store_names.py → backend/initialize_database_schema.py
- `Normalize store names into a consistent display form.` --uses--> `Store`  [INFERRED]
  backend/normalize_store_names.py → backend/initialize_database_schema.py
- `Find a store by canonicalized, case-insensitive name.` --uses--> `Store`  [INFERRED]
  backend/normalize_store_names.py → backend/initialize_database_schema.py
- `_save_bill_meta()` --calls--> `derive_planning_month()`  [INFERRED]
  backend/extract_receipt_data.py → backend/bill_planning.py

## Communities

### Community 0 - "Rationale Comments (Misc Backend)"
Cohesion: 0.08
Nodes (193): Helpers for maintaining the app's active inventory window.  Active inventory is, Return the first moment of the previous calendar month., Persist a manual adjustment that should be folded into active inventory., Recompute inventory from recent receipts plus recent manual adjustments., Nightly DB-layer backfill: download images for products with no ProductSnapshot, Products with NO snapshot, referenced by receipt or shopping list,     not attem, For each product: fetch image bytes, persist as ProductSnapshot row,     update, Step 18: Calculate Spending Analytics ====================================== PRO (+185 more)

### Community 1 - "Contribution Scoring Rationale"
Cohesion: 0.11
Nodes (134): Contribution scoring helpers and shared rules., Normalize simple user-facing text for no-op comparisons., Return True only when a text change is meaningfully different., Return contribution-event bonus points for a user., Return not-yet-finalized contribution points for a user., Cancel pending low contributions for a product when the flag is cleared., Finalize low-stock contributions only when shopping + receipt activity confirms, Confirm that a low-stock call was valid, with weaker self-confirm support. (+126 more)

### Community 2 - "Bill Cadence & Budget Categories"
Cohesion: 0.04
Nodes (115): billing_cycle_month_count(), month_matches_billing_cycle(), normalize_billing_cycle(), Return whether target_month belongs to the cadence anchored at anchor_month., default_budget_category_for_spending_domain(), default_budget_category_for_utility(), derive_receipt_budget_defaults(), normalize_budget_category() (+107 more)

### Community 3 - "Inventory & Contribution Logic"
Cohesion: 0.04
Nodes (109): get_active_inventory_cutoff(), rebuild_active_inventory(), record_inventory_adjustment(), award_contribution_event(), cancel_pending_low_event(), confirm_low_peer(), confirm_recommendation_peer(), finalize_recommendation_confirmation() (+101 more)

### Community 4 - "Flask App Bootstrap"
Cohesion: 0.05
Nodes (107): sum_bonus_points(), sum_floating_points(), create_app(), ensure_admin_user(), _get_db(), _is_placeholder_config_value(), Step 3: Setup Flask Backend API ================================ PROMPT Referenc, Decorator to block writes from trusted devices in read-only mode. (+99 more)

### Community 5 - "Image Backfill & Threshold Checks"
Cohesion: 0.03
Nodes (96): backfill_images_for_products(), find_products_needing_images(), _is_meaningful_product(), check_all_thresholds(), Step 15: Add Low-Stock Alert System ===================================== PROMPT, Stop the scheduler gracefully., Start the 5-minute threshold checking scheduler., Check all inventory items against their thresholds.      Runs every 5 minutes vi (+88 more)

### Community 6 - "AI Vision Receipt OCR"
Cohesion: 0.04
Nodes (90): extract_receipt_via_anthropic(), Anthropic vision OCR support for receipt extraction.  Phase 1 keeps this aligned, Extract receipt data from an image using Anthropic vision., _safe_float(), _build_prompt(), _extract_pdf_text(), extract_receipt_summary_via_gemini(), extract_receipt_via_gemini() (+82 more)

### Community 7 - "Plaid Integration"
Cohesion: 0.06
Nodes (71): _build_client(), country_codes_from_strings(), _env_to_host(), get_client(), get_plaid_env_name(), is_plaid_configured(), products_from_strings(), Thin wrapper around the Plaid Python SDK.  All outbound Plaid calls go through t (+63 more)

### Community 8 - "Chat Assistant"
Cohesion: 0.07
Nodes (60): _anthropic_chat(), build_data_context(), _build_provider_chain(), _category_totals(), chat_complete(), _compute_item_insights(), _compute_shopping_activity(), _expand_term_variants() (+52 more)

### Community 9 - "Frontend: Overscroll Navigation"
Cohesion: 0.11
Nodes (36): applyPullVisual(), commitNavigation(), docAtBottom(), docAtTop(), docScrollTop(), endTouch(), ensureBanner(), getAdjacentPage() (+28 more)

### Community 10 - "MQTT Event Publishing"
Cohesion: 0.09
Nodes (29): publish_budget_alert(), _publish_discovery(), publish_inventory_update(), publish_low_stock_alert(), publish_recommendations(), Step 20: Create MQTT Real-Time Sync Handler ====================================, Publish daily recommendations., Publish an inventory state change. (+21 more)

### Community 11 - "Bill Planning & Cash Transactions"
Cohesion: 0.18
Nodes (21): derive_planning_month(), derive_planning_month_for_cash_transaction(), list_bill_providers(), _cleanup_empty_cash_entities(), create_cash_transaction(), default_budget_category_for_personal_service(), delete_cash_transaction(), _find_merge_candidate() (+13 more)

### Community 12 - "Receipt Filename Index"
Cohesion: 0.17
Nodes (19): append_receipt_to_index(), _format_date(), _format_index_line(), _format_money(), format_receipt_label(), index_path(), Human-readable index of stored receipt files.  The receipt files on disk keep th, One column-aligned line; columns are wide enough to look tidy in `less`. (+11 more)

### Community 13 - "Telegram Message Handler"
Cohesion: 0.18
Nodes (18): _answer_callback_query(), _cancel_pending_receipt(), _create_pending_receipt(), download_telegram_file(), _edit_telegram_message(), _handle_callback_query(), _handle_command(), _is_supported_receipt_document() (+10 more)

### Community 14 - "Backup & Environment Ops"
Cohesion: 0.31
Nodes (16): _admin_or_403(), _backups_dir(), create_backup(), download_backup(), _list_backup_entries(), list_backups(), _load_manifest_for_archive(), _manifest_sidecar_path() (+8 more)

### Community 15 - "Product Snapshots"
Cohesion: 0.27
Nodes (15): _derive_snapshot_context(), get_product_snapshot(), get_product_snapshot_image(), _get_snapshot_root(), list_product_snapshots(), list_snapshot_review_queue(), _parse_datetime(), _parse_int() (+7 more)

### Community 16 - "Telegram Webhook Config"
Cohesion: 0.24
Nodes (10): check_webhook_status(), configure_webhook(), delete_webhook(), handle_command(), Step 6: Configure Telegram Bot Webhook ======================================= P, Register webhook URL with Telegram Bot API.      Args:         base_url: Your HT, Check current webhook status via Telegram API., Delete the currently configured Telegram webhook. (+2 more)

### Community 17 - "Frontend: Page Pager"
Cohesion: 0.36
Nodes (8): buildButton(), ensurePager(), getNavIcon(), getNavItemEl(), getPageNavLabel(), getVisibleSidebarPages(), renderAll(), renderPagerFor()

### Community 18 - "Frontend: Upload Result Renderer"
Cohesion: 0.31
Nodes (5): _esc(), _money(), _renderLegacyFallback(), _renderSummaryLine(), _setHtml()

### Community 19 - "Store Management"
Cohesion: 0.22
Nodes (7): classify_store(), list_stores(), Flask blueprint for the Manage Stores Settings panel.  Exposes:   GET  /api/stor, get_store_buckets(), Store visibility bucketing.  Pure ``classify_store`` plus the aggregator ``get_s, Return the bucket ('frequent' | 'low_freq' | 'hidden') for a store.      Order o, Return stores grouped into the three visibility buckets.      Shape:         {

### Community 20 - "Kitchen Catalog"
Cohesion: 0.4
Nodes (4): category_for_product(), get_catalog(), Flask blueprint for the Kitchen View read endpoint.  Exposes:   GET /api/kitchen, get_kitchen_catalog()

### Community 21 - "Backend Package Init"
Cohesion: 1.0
Nodes (1): Grocery Inventory & Savings Management System — Backend Package.  This package c

## Knowledge Gaps
- **105 isolated node(s):** `Step 12: Handle Receipt Image Processing =======================================`, `Save a receipt image with organized directory structure.      Args:         sour`, `Create a compressed thumbnail for Home Assistant UI.`, `Compute SHA-256 hash of a file.`, `Check if an identical image has already been processed.` (+100 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Backend Package Init`** (2 nodes): `__init__.py`, `Grocery Inventory & Savings Management System — Backend Package.  This package c`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Product` connect `Rationale Comments (Misc Backend)` to `Contribution Scoring Rationale`, `Bill Cadence & Budget Categories`, `Inventory & Contribution Logic`, `Image Backfill & Threshold Checks`, `Chat Assistant`, `Product Snapshots`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Why does `Purchase` connect `Rationale Comments (Misc Backend)` to `Contribution Scoring Rationale`, `Bill Cadence & Budget Categories`, `Plaid Integration`, `Chat Assistant`, `Bill Planning & Cash Transactions`, `Store Management`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `User` connect `Contribution Scoring Rationale` to `Rationale Comments (Misc Backend)`, `Chat Assistant`, `Flask App Bootstrap`, `AI Vision Receipt OCR`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Are the 262 inferred relationships involving `Purchase` (e.g. with `Plaid transaction → LocalOCR receipt mapper + deduplication helpers.  Pure funct` and `Return suggested {receipt_type, spending_domain, budget_category, skip} for a st`) actually correct?**
  _`Purchase` has 262 INFERRED edges - model-reasoned connections that need verification._
- **Are the 247 inferred relationships involving `Product` (e.g. with `Shopping list endpoints.` and `Backfill a pending recommendation acceptance event when needed.`) actually correct?**
  _`Product` has 247 INFERRED edges - model-reasoned connections that need verification._
- **Are the 216 inferred relationships involving `ReceiptItem` (e.g. with `Step 11: Implement Hybrid OCR Processor ========================================` and `Return a float for persistence/logging even when OCR returns null/string values.`) actually correct?**
  _`ReceiptItem` has 216 INFERRED edges - model-reasoned connections that need verification._
- **Are the 207 inferred relationships involving `Store` (e.g. with `Shopping list endpoints.` and `Backfill a pending recommendation acceptance event when needed.`) actually correct?**
  _`Store` has 207 INFERRED edges - model-reasoned connections that need verification._