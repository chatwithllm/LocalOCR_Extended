# Product Requirements Document (PRD)
## Grocery Inventory & Savings Management System

**Document Version:** 1.0  
**Created:** 2026-04-01  
**Status:** Approved for Implementation  
**Product Owner:** User  
**Technical Lead:** Planning Agent  

---

## 1. Executive Summary

**Problem:** Households struggle with grocery management—they overspend, buy duplicates, miss sales, and have no visibility into spending patterns. Multiple family members shop independently without shared inventory awareness.

**Solution:** Build a **privacy-first, local-first grocery management system** that:
- Automatically processes receipts via **Telegram bot** (primary) or Home Assistant (backup)
- Extracts receipt data using **hybrid OCR** (Google Gemini + Ollama fallback)
- Maintains **real-time shared inventory** across all household devices (MQTT sync)
- Delivers **smart recommendations** (price deals + seasonal/recurring items)
- Provides **spending analytics** (budget tracking, price trends, savings quantification)
- Provides a full **web app** for dashboard, receipts, shopping, inventory, and household collaboration
- Leverages **Home Assistant + MQTT** as an optional real-time integration layer
- Secures browser access with **session-based household login** and keeps tokens for integrations
- Ensures **100% data portability** (Docker Compose, backup/restore)
- Maintains **zero ongoing costs** (free Gemini tier + self-hosted services)

**Target Users:** Multi-person households (2-4 people) seeking to optimize grocery spending and reduce food waste.

---

## 2. Goals & Success Metrics

### Primary Goals
1. **Eliminate manual receipt entry** — OCR extracts >95% of receipt data automatically
2. **Enable real-time household collaboration** — All members see shared inventory, sync <2 sec
3. **Increase savings awareness** — Users identify deals & optimize purchases, target 15%+ annual savings
4. **Guarantee data portability** — Zero vendor lock-in, deployable on any machine/environment
5. **Achieve zero cloud costs** — Leverage free Gemini tier + self-hosted solutions

### Success Metrics
- **Adoption:** >80% of household grocery purchases captured within 2 months
- **OCR Accuracy:** 90%+ extraction accuracy (items, quantities, prices)
- **Sync Latency:** <2 seconds from action to all devices
- **User Engagement:** 60%+ weekly interaction with recommendations
- **Financial Impact:** Users report 10-20% monthly grocery savings

---

## 3. Feature Requirements

### 3.1 Receipt Management

**Feature:** Multi-Channel Receipt Ingestion & Hybrid OCR Processing

**Channels:**
1. **Telegram Bot (Primary)**
   - User sends receipt photo anytime, anywhere
   - Bot confirms: "✅ Processed: $X.XX at Store | Y items"
   - Bot sends error feedback: "❌ Could not process receipt. Saved for manual review."
   - Works from any device with Telegram
   - **Prerequisite:** Requires internet connection + Nginx Proxy Manager with a domain and valid SSL certificate already configured

2. **Home Assistant Upload (Secondary)**
   - Dashboard upload button for home network
   - Instant local processing
   - No internet exposure

3. **Stub Upload Endpoint (Development & Fallback)**
   - `POST /receipts/upload` accepts image file directly
   - Enables testing OCR → inventory pipeline without Telegram/Nginx/SSL
   - Also used by Home Assistant upload button
   - Same processing pipeline as Telegram path

4. **Email (Optional, Phase 2)**
   - Forward receipts to processing inbox
   - Auto-processed every 30 minutes

**OCR Technology:**
- **Primary:** Google Gemini Vision API (free tier: 60 req/min, 1.5M tokens/day)
  - Accuracy: 90%+
  - Speed: 2-3 seconds per receipt
- **Fallback:** Ollama + LLaVA (self-hosted, local)
  - Accuracy: 85%+
  - Speed: 5-15 seconds per receipt
  - Triggers when Gemini rate-limited or errors

**Extraction Output:**
- Store name & location
- Transaction date & time
- Items list: product name, quantity, unit price, category
- Total amount
- OCR confidence score (flag <80% for manual review)

**Manual Review Queue:**
- Receipts with confidence <80% stored for user verification
- User reviews & corrects via Home Assistant
- Corrected data used to improve recommendations
- Telegram user notified: "⚠️ Low confidence — please review in Home Assistant"
- If both OCR engines fail, Telegram user notified: "❌ Could not process receipt. Saved for manual review."

---

### 3.2 Inventory Management

**Feature:** Real-Time Multi-User Inventory Tracking

**Core Functionality:**
- View current active household inventory (recent rolling window)
- Add items manually or auto-add from processed receipts
- Decrease quantity when consuming items
- Track location: Fridge, Pantry, Freezer, Cabinet
- See which family member updated each item (audit trail)
- Real-time sync across devices (MQTT)
- Jump from inventory/product rows back to linked receipts for traceability
- Clean up product names and categories inline from inventory, products, or receipt detail

**Low-Stock Alerts:**
- Per-product threshold (e.g., milk < 0.5L, eggs < 6)
- Alert delivery: MQTT topic → Home Assistant notification
- Repeat every 24 hours until threshold met
- Example: "🔔 Milk running low (0.3L remaining)"

**Product Information:**
- Product name, category, barcode (optional)
- Average price (for recommendations)
- Store availability
- Purchase frequency (calculated from history)
- Human-readable display names should be preferred over raw OCR text in user-facing views

---

### 3.3 Smart Recommendations

**Feature:** Proactive & Reactive Purchase Recommendations

**Recommendation Types:**

1. **Price Deals**
   - Triggers when: current_price < average_price * 0.9 (i.e., ≥10% discount)
   - Confidence: `min((avg_price - current_price) / avg_price * 5, 1.0)` — scaled so a 20% discount = 1.0 confidence
   - Example: "💰 Milk on sale! Usually $3.80, now $3.20 at Whole Foods" (confidence: 0.79)
   - Minimum 3 historical price points required

2. **Seasonal/Recurring**
   - Triggers when: (today - last_purchase) > (avg_frequency * 1.2)
   - Confidence: `min((days_since_last / avg_frequency - 1.0) * 2.5, 1.0)` — scaled so 40%+ overdue = 1.0 confidence
   - Example: "🛒 You usually buy milk every 5 days. It's been 6 days—time to restock?" (confidence: 0.50)
   - Minimum 3 purchase dates required for pattern detection

**Delivery Modes:**
- **Proactive:** Daily push at 8 AM (configurable) via MQTT → Home Assistant
- **Reactive:** User reviews recommendations inside the web app shopping workflow

**Confidence Threshold:** Only show recommendations ≥0.40 confidence (scaled formulas mean 0.40 ≈ a meaningful signal)

**Workflow update:**
- Recommendations are part of the Shopping page, not a separate standalone workflow
- Users can add a recommendation to shopping
- Other household members can confirm the recommendation
- Scoring stays floating until later validation such as purchase completion

---

### 3.4 Spending Analytics & Budget Tracking

**Feature:** Comprehensive Spending Visibility

**Analytics Dimensions:**
- **Time Period:** Daily, weekly, monthly, yearly
- **Category:** By product category, store, family member
- **Metrics:**
  - Total spent (e.g., "$485.32 in March")
  - Average price per unit (e.g., "Milk: avg $3.65/L")
  - Number of purchases
  - Price trends (min/max over time)
  - Deals captured (savings from discounts identified)

**Budget Tracking:**
- Set monthly grocery budget (e.g., $600)
- Track actual spending vs budget
- Alert at 80% threshold: "⚠️ Budget alert: 82% spent ($492 of $600)"
- Show % remaining

**Savings Calculation:**
- Per receipt: (avg_historical_price - actual_price) * quantity = savings
- Monthly total deals captured
- Example: "You saved $23.45 this month on deals!"

**Store Comparison:**
- Track same product prices across stores
- Identify cheapest option per item
- Historical price comparison

---

### 3.5 Home Assistant Integration

**Feature:** Unified Household Dashboard

**Dashboard / Web App Components:**

1. **Inventory Card**
   - Grid/list view of all products
   - Show: product name, quantity, location
   - Actions: Click for details, button to consume, edit quantity

2. **Recommendations Card**
   - Daily suggestions (deals + seasonal)
   - Show reason, estimated price, store
   - Add to shopping list or confirm collaborative shopping actions

3. **Receipts Review**
   - Browse processed/review/failed receipts
   - Preview image/PDF
   - Rename or recategorize extracted items inline
   - Reprocess or approve review receipts

4. **Shopping Workspace**
   - Current list, quick find, store grouping, estimated stops
   - Embedded recommendations
   - Recovery flow for accidentally bought items via `Reopen`

5. **Contribution Page**
   - Explain scoring rules
   - Show recent contribution events
   - Suggest ways users can help improve the system

6. **Alerts Card**
   - Low-stock warnings
   - Budget status
   - System notifications

7. **Analytics Card**
   - Spending trends (line chart)
   - Budget vs actual (progress bar)
   - Price history per product
   - Monthly spending summary

5. **Add Item Card**
   - Search existing products
   - Manual entry form
   - Quick add (frequent items)

**Interactions:**
- Click product → view price history, store options, recommendation reason
- Button "Consume" → decrease quantity by 1
- Button "Buy More" → increase quantity by preset amount
- Swipe/edit → modify quantity directly
- Mobile responsive (works on iOS/Android Home Assistant apps)

**Real-Time Updates:**
- MQTT subscription keeps dashboard live
- Changes by other family members appear <2 sec

---

### 3.6 Multi-User Collaboration

**Feature:** Household Member Management

**User Roles:**
- **Admin:** Manage settings, budgets, member permissions, review household/user cleanup work
- **User:** View & update inventory, shopping, receipts, and recommendations

**Collaboration Features:**
- Shared inventory (all members see same data)
- Audit trail (track who updated each item, when)
- User attribution (e.g., "Added by Sarah, 2 hours ago")
- Optional notifications (family member actions)

**Authentication:**
- Browser login uses Flask session auth
- Bearer-token authentication remains available for integrations and automation
- All Flask API endpoints require valid auth except `/telegram/webhook` and static/root serving
- Per-user preferences include profile/avatar and collapsible workspace layout choices
- Future-friendly for Home Assistant auth integration, but not required for current app

---

## 4. Technical Requirements

### 4.1 Architecture

- **Backend:** Flask API (Python, port 8080, local Mac mini)
- **Database:** SQLite with **WAL mode enabled** (portable, zero config, supports concurrent readers + single writer without locking issues)
- **Migrations:** Alembic for schema versioning (supports safe schema evolution post-launch)
- **Real-Time Sync:** MQTT Broker (Mosquitto, local)
- **OCR:** Gemini Vision API (cloud) + Ollama (local fallback)
- **Rate-Limit Tracking:** Gemini API usage counters persisted to SQLite (survive restarts)
- **Frontend:** Standalone web UI served by Flask, with optional Home Assistant + MQTT integration
- **Reverse Proxy:** Nginx Proxy Manager (**prerequisite** — must be running with domain + SSL before deployment)
- **Deployment:** Docker Compose (backend + DB + MQTT + Ollama) — **set up first in Phase 1** so all development happens inside containers from day one

### 4.2 Data Schema

**Core Tables:**
- `users` (id, name, email, role, api_token_hash, password_hash, avatar, created_at)
- `products` (id, name, raw_name, display_name, category, brand, size, review_state, created_at)
- `inventory` (id, product_id, quantity, location, last_updated, updated_by)
- `purchases` (id, store_id, total_amount, date, user_id)
- `receipt_items` (id, purchase_id, product_id, quantity, unit_price, extracted_by)
- `price_history` (id, product_id, store_id, price, date)
- `stores` (id, name, location)
- `budget` (id, user_id, month, budget_amount)
- `telegram_receipts` (id, telegram_user_id, message_id, status, ocr_confidence)
- `shopping_list_items` (id, product_id, name, quantity, preferred_store, source, status)
- `contribution_events` (id, user_id, event_type, status, points, reference_type, reference_id)
- `access_links` (id, token_hash, scope, expires_at, redeemed_at)
- `api_usage` (id, service_name, date, request_count, token_count)
- `alembic_version` (version_num) — managed by Alembic migration tool

### 4.3 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/telegram/webhook` | POST | Receive receipt from Telegram |
| `/receipts/upload` | POST | Upload receipt via Home Assistant |
| `/receipts/{id}` | GET | Retrieve receipt details |
| `/receipts/{id}/approve` | POST | Approve edited review receipt |
| `/products` | GET, POST | List/create products |
| `/products/{id}` | PUT | Rename / recategorize / clean up product |
| `/inventory` | GET | View current inventory |
| `/inventory/add-item` | POST | Add item to inventory |
| `/inventory/{id}/consume` | PUT | Decrease quantity |
| `/shopping-list` | GET, POST | Shopping list workspace |
| `/shopping-list/share/{token}` | GET | Helper-mode shared shopping data |
| `/recommendations` | GET | Get recommendations (proactive/reactive) |
| `/analytics/spending` | GET | Get spending analytics |
| `/analytics/budget` | GET | Get budget status |
| `/budget/set-monthly` | POST | Set monthly budget |

---

## 5. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| **System Availability** | 99.5% (local network only) |
| **OCR Processing Latency** | <3 sec (Gemini), <15 sec (Ollama) |
| **MQTT Sync Latency** | <2 seconds |
| **API Response Time** | <500 ms |
| **API Authentication** | Browser session or valid integration token |
| **OCR Accuracy** | 90%+ |
| **Data Calculation Accuracy** | 100% (exact match to manual calculation) |
| **Backup Frequency** | Daily automated |
| **Data Portability** | Restore from backup <5 minutes |
| **Receipt Image Retention** | 12 months (configurable), auto-cleanup of older images |
| **Maximum Supported** | 5 household members, 1000 products |
| **Monthly Cost** | $0 (free Gemini tier + self-hosted) |

---

## 6. Out of Scope (v1)

- ❌ Native mobile app
- ❌ Cloud backup (local backup only)
- ❌ Dietary/nutritional filtering
- ❌ Barcode scanning (manual + OCR only)
- ❌ Multi-location household (single household only)
- ❌ Meal planning
- ❌ Supplier/wholesale pricing
- ❌ ML-based purchase forecasting (seasonal patterns only)
- ❌ Third-party grocery APIs (Instacart, Amazon Fresh)
- ❌ PostgreSQL (SQLite with WAL mode sufficient for v1 household scale)

---

## 7. Acceptance Criteria

**Receipt Processing:**
- ✅ Telegram upload → processed <3 sec
- ✅ Stub upload endpoint (`POST /receipts/upload`) → same pipeline works without Telegram
- ✅ Bot confirmation sent with store, date, item count
- ✅ Gemini OCR 90%+ accuracy (5 manual receipt tests)
- ✅ Ollama fallback succeeds when Gemini rate-limited
- ✅ Low confidence (<80%) flagged for manual review
- ✅ Inventory auto-updates from processed receipt

**Inventory Management:**
- ✅ Add item → appears in all users' Home Assistant within 2 sec
- ✅ Multi-user actions (3+ simultaneous) → no data conflicts
- ✅ Low-stock alert triggered & delivered correctly
- ✅ Audit trail shows user & timestamp for each change

**Recommendations / Shopping:**
- ✅ Daily recommendations generated & pushed at 8 AM
- ✅ Deals correctly identified (>10% discount detection)
- ✅ Seasonal patterns recognized (recurring items detected)
- ✅ Recommendations available inside the Shopping workflow
- ✅ Shared shopping helper QR can show open items and mark them bought/reopen them

**Analytics:**
- ✅ Monthly spending calculated accurately (<$1 variance)
- ✅ Price trends display min/max/avg correctly
- ✅ Budget vs actual shows % spent accurately
- ✅ Savings quantified correctly (vs manual calculation)

**Web UI / Household Collaboration:**
- ✅ Dashboard loads <2 sec
- ✅ Inventory/products/receipts/shopping are usable from the standalone web app
- ✅ Click actions responsive (<500 ms)
- ✅ Mobile responsive, including compact shopping-helper and inventory mobile layouts

**Deployment:**
- ✅ Docker Compose stack created in Phase 1 (development runs inside containers from day one)
- ✅ Docker stack starts <2 min
- ✅ Backup created daily automatically
- ✅ Restore from backup recovers all data
- ✅ System functions on different machine after restore
- ✅ Offline operation (changes queued, sync on reconnect)

---

## 8. Assumptions & Constraints

**Assumptions:**
- User has Home Assistant instance running locally
- User has MQTT broker available
- **Nginx Proxy Manager already running** with a registered domain and valid SSL certificate (required for Telegram webhook HTTPS)
- Google Gemini API key obtained (free tier)
- Receipt images are clear & readable
- Household connected to local network
- Python 3.9+ available on Mac mini

**Constraints:**
- Gemini free tier limited (60 req/min, 1.5M tokens/day—sufficient for household). Usage tracked and persisted to DB.
- Ollama model size (~2-4GB—requires space on Mac mini)
- SQLite with WAL mode (supports concurrent reads, single writer — sufficient for ≤5 household members)
- MQTT restricted to local network (no cloud sync)
- No standalone web UI or mobile app (Home Assistant app used instead)
- Single household only (not multi-property)
- Receipt images retained for 12 months by default (configurable) to manage disk usage

---

## 9. Success Criteria & Rollout

**MVP Release Criteria:**
- All core features implemented (Phases 1-6)
- Docker Compose stack established from Phase 1 (not bolted on at the end)
- Gemini + Ollama hybrid OCR working with fallback
- Stub upload endpoint enables testing without Telegram dependency
- MQTT real-time sync verified <2 sec
- Home Assistant dashboard functional
- 5 end-to-end tests passed
- Documentation complete

**Phased Rollout:**
- **Phase 1:** Docker-first foundation — all infrastructure inside containers from day one (1 week)
- **Phase 2:** Deploy on Mac mini with stub upload testing, then add Telegram (1 week)
- **Phase 3:** Onboard household members (real usage, 1-2 weeks)
- **Phase 4:** Feedback & iterate (v1.1 improvements, ongoing)
- **Phase 5:** Enhancement (custom Lovelace card, v1.5, optional)

> **💡 Note on parallelism:** Phases 4 (Inventory), 5 (Recommendations), and 6 (Analytics) are independent data consumers. They can be developed in parallel once Phase 3 (OCR) is complete.

---
