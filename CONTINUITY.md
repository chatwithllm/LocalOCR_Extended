# CONTINUITY.md — Project Restart & Resume Guide

> **Purpose:** If you need to restart this project from scratch, resume after a break,
> or hand it off to someone else — this document has everything you need.

> **Current status note:** The original planning checklist below is no longer the best source of truth for runtime status. For the latest verified working state and restart handoff, read [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) first. For the full rebuild-grade product definition, read [docs/COMPLETE_PRODUCT_SPEC.md](docs/COMPLETE_PRODUCT_SPEC.md).

---

## 1. Current Continuity Snapshot

### Completed

- Flask backend is running and serving the web app on port `8080`
- Local browser login is implemented with Flask sessions
- Admins can now create household users from the web app
- Admins can now edit users, reset passwords, and activate/deactivate accounts
- Existing users can now request password help from the login screen
- Bearer-token authentication is still in place for app APIs and integrations
- Direct receipt upload is implemented and working for images and PDFs
- Gemini OCR is implemented, migrated to `google-genai`, and working
- Gemini OCR now augments PDF receipts with the PDF text layer to recover summary fields like date, subtotal, tax, total, and time
- OCR fallback chain exists: Gemini → OpenAI → Ollama
- Docker Compose is the primary intended runtime, with restart policies already configured for backend, MQTT, and Ollama
- Product, inventory, analytics, budget, and recommendations endpoints are implemented
- Shopping list endpoints and web tab are implemented
- Web app tabs are implemented for dashboard, inventory, products, upload, receipts, shopping list, budget, analytics, recommendations, and settings
- Mobile navigation now uses an off-canvas menu instead of a permanently fixed sidebar
- Receipt review/history is implemented in the web app, including extracted items plus image/PDF preview
- Review receipts can persist raw OCR output, be reprocessed, and be approved from the web app
- Product names are now normalized on save, and obvious case-only duplicates are merged
- Store names are now normalized on save, and obvious case-only duplicates are merged
- Products now show linked receipt shortcuts that jump directly to the selected receipt in the Receipts tab
- Inventory tab now has live client-side search
- Telegram webhook handler is implemented
- Telegram confirmation step is implemented before OCR begins
- Telegram webhook registration/status helper is implemented
- Public HTTPS endpoint `https://inventory.npalakurla.net/telegram/webhook` is reachable
- Telegram webhook is registered for the current bot

### Verified Working

- `GET /health`
- web app served at `/` and `/dashboard`
- bootstrap auth flow:
  `GET /auth/bootstrap-info` → `POST /auth/login` → `GET /auth/me`
- admin household user flow:
  `GET /auth/users` → `POST /auth/users`
- admin account maintenance flow:
  `PUT /auth/users/{id}` for profile updates, password resets, and activation changes
- forgot-password flow:
  `POST /auth/forgot-password` raises an admin-visible reset request for existing users only
- mobile web layout:
  iPhone-sized screens now use a top bar + slide-out menu so content is not hidden behind the sidebar
- Products tab: list, search, create, delete
- Products tab: grouped catalog view, rename/merge, linked receipt shortcuts
- Inventory tab: list, add, consume, delete, search
- Budget tab: set and read status
- Analytics tab: loads and matches backend response shape
- Recommendations tab: loads correctly
- Shopping List tab: manual add, open/purchased status, delete
- Add to Shopping List actions work from recommendations, products, and inventory
- Upload Receipt tab: authenticated upload and OCR result rendering for images and PDFs
- Receipts tab: receipt list, receipt detail, stored image preview, PDF viewer, review approval tools
- Gemini OCR: direct smoke test and live upload path
- Telegram bot token: valid
- Telegram webhook: registered successfully
- End-to-end Telegram PDF receipt flow:
  send PDF → bot asks for confirmation → process → Gemini extracts store/date/total/items → receipt saves as processed purchase
- Verified sample Telegram PDF result:
  `COSTCO WHOLESALE`, date `2026-03-30`, total `478.42`, `36` receipt items, classified as `grocery`
- MQTT broker auth is working with configured username/password credentials
- MQTT publish smoke tests succeeded for inventory, recommendations, budget alerts, and low-stock alerts
- Home Assistant-side MQTT validation completed successfully
- Home Assistant MQTT discovery payloads are now published for inventory, recommendation count, budget alerts, and low-stock alerts
- Flask debug mode is now guarded so MQTT and schedulers only start in the real serving process, not the reloader parent

### Pending / Not Fully Validated

- End-to-end Telegram photo upload validation from the real bot chat
- Home Assistant dashboard/automation validation
- Low-stock alert validation
- Daily recommendation scheduler validation
- Backup/restore validation on a clean machine
- Docker-first fresh-machine validation after the latest changes
- Automated test coverage refresh
- Alembic migration workflow

---

## 2. What This System Does (30-Second Summary)

A **self-hosted grocery management system** that:
- Processes receipt photos via OCR (Gemini AI + Ollama fallback)
- Maintains shared household inventory with real-time sync
- Detects deals and recurring purchase patterns
- Tracks spending and budgets
- Runs entirely locally via Docker Compose — zero cloud costs

**Input:** Receipt photos (via Telegram or direct upload)
**Output:** Structured inventory, recommendations, and spending analytics
**UI:** Home Assistant dashboard (MQTT-connected)

---

## 3. Architecture at a Glance

```
Telegram / Upload → Flask API (port 8080) → Gemini / Ollama OCR
                         │
               ┌─────────┼─────────┐
               ▼         ▼         ▼
          Inventory  Analytics  Recommendations
               │         │         │
               └─────────┼─────────┘
                         ▼
               MQTT (port 1883) → Home Assistant
                         │
               SQLite DB (WAL mode)
```

**Stack:** Python 3.11, Flask, SQLAlchemy, SQLite, Mosquitto MQTT, Docker Compose
**See:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details

---

## 4. File Map

Every file in the project and what it does:

### Root Files
| File | Purpose |
|------|---------|
| `PRD.md` | Product requirements — the "what" and "why" |
| `PROMPT.md` | Implementation guide (24 steps) — the "how" |
| `CONTINUITY.md` | This file — restart/resume guide |
| `docs/IMPLEMENTATION_STATUS.md` | Current verified status + restart handoff |
| `README.md` | Quick start and project overview |
| `docs/APP_SETUP_GUIDE.md` | Operator-friendly first-run app setup |
| `docker-compose.yml` | Service orchestration (backend, MQTT, Ollama) |
| `Dockerfile` | Backend container image definition |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `.gitignore` | Git ignore rules |

### Backend Modules (`src/backend/`)
| File | PROMPT Step | Status |
|------|-------------|--------|
| `__init__.py` | — | ✅ Done |
| `initialize_database_schema.py` | Step 2 | ✅ Schema defined |
| `create_flask_application.py` | Step 3 | ✅ App factory created |
| `manage_authentication.py` | Phase 1 auth | ✅ Session login + bootstrap auth endpoints |
| `manage_authentication.py` | Phase 2 auth | ✅ Admin user list/create endpoints |
| `manage_authentication.py` | Phase 3 auth | ✅ Admin user update/reset/deactivate endpoint |
| `manage_authentication.py` | Password recovery | ✅ Existing-user reset-request endpoint |
| `setup_mqtt_connection.py` | Step 4 | ✅ Client singleton |
| `handle_receipt_upload.py` | Step 5 | ✅ Upload endpoint working (images + PDFs) |
| `configure_telegram_webhook.py` | Step 6 | ✅ Webhook registration/status helper working |
| `handle_telegram_messages.py` | Step 8 | ✅ Webhook handler working (photos, PDFs, confirm/cancel) |
| `call_gemini_vision_api.py` | Step 9 | ✅ Working via `google-genai` with PDF text-layer enrichment |
| `call_ollama_vision_api.py` | Step 10 | 🟡 Fallback implemented, not recently re-validated |
| `extract_receipt_data.py` | Step 11 | ✅ Hybrid OCR pipeline working (includes PDF preprocessing + review workflow) |
| `save_receipt_images.py` | Step 12 | 🟡 Storage helper exists; not the primary reviewed path |
| `manage_product_catalog.py` | Step 13 | ✅ CRUD working |
| `manage_shopping_list.py` | Shopping list | ✅ Shopping list API working |
| `manage_inventory.py` | Step 14 | ✅ CRUD working |
| `normalize_product_names.py` | Catalog cleanup | ✅ Product name canonicalization + duplicate merge helpers |
| `normalize_store_names.py` | Store cleanup | ✅ Store name canonicalization + duplicate merge helpers |
| `check_inventory_thresholds.py` | Step 15 | 🟡 Partial / not fully validated |
| `generate_recommendations.py` | Step 16 | 🟡 Endpoint working, needs richer data validation |
| `schedule_daily_recommendations.py` | Step 17 | 🟡 Scheduler present, not fully validated |
| `calculate_spending_analytics.py` | Step 18 | ✅ Endpoints working |
| `manage_household_budget.py` | Step 19 | ✅ Endpoints working |
| `publish_mqtt_events.py` | Step 20 | ✅ Publish functions |

### Config Files (`config/`)
| File | Purpose |
|------|---------|
| `mosquitto/mosquitto.conf` | MQTT broker configuration |
| `home_assistant_dashboard_config.yaml` | HA dashboard (stub) |
| `home_assistant_automations.yaml` | HA automations (stub) |

### Scripts (`scripts/`)
| File | Purpose |
|------|---------|
| `backup_database_and_volumes.sh` | Daily backup script |
| `restore_from_backup.sh` | Restore from backup archive |

### Tests (`tests/`)
| File | Purpose |
|------|---------|
| `test_full_receipt_flow.py` | E2E test stubs (10 scenarios) |

### Documentation (`docs/`)
| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | System diagram + design decisions |
| `API_REFERENCE.md` | All endpoints, auth, MQTT topics |
| `COMPLETE_PRODUCT_SPEC.md` | Full rebuild-grade app spec for tabs, workflows, rules, and implementation |
| `DEPLOYMENT_GUIDE.md` | Zero-to-running setup steps |
| `IMPLEMENTATION_STATUS.md` | Current working state, restart handoff, and next steps |
| `NGINX_PROXY_MANAGER_SETUP.md` | Telegram webhook routing |

---

## 5. Phase Checklist — Progress Tracker

Use this to track implementation progress. Check off items as you go.

### Phase 1: Foundation & Infrastructure
- [x] Step 1: Docker Compose stack (`docker-compose.yml`, `Dockerfile`)
- [x] Step 2: Database schema (`initialize_database_schema.py` — models defined)
- [x] Step 3: Flask app (`create_flask_application.py` — app factory + auth)
- [x] Browser login for the bootstrap admin (`/auth/login`, session cookie, `/auth/me`)
- [x] Admin can create household users from the web app
- [x] Admin can edit users, reset passwords, and activate/deactivate accounts
- [x] Existing users can request password resets without opening self-registration
- [x] Step 4: MQTT connection (`setup_mqtt_connection.py` — client ready)
- [x] Step 5: Upload endpoint (`handle_receipt_upload.py` — authenticated and working)
- [x] PDF receipts supported through upload endpoint
- [x] Wire blueprints into Flask app
- [ ] Run `alembic init` and create initial migration
- [ ] Test `docker-compose up` end-to-end
- [ ] Link Telegram chats to local accounts
- [ ] Add self-service password change flow for logged-in users

### Phase 2: Telegram Integration
- [x] Step 6: Configure Telegram webhook helper
- [x] Step 7: Setup public webhook route
- [x] Step 8: Implement Telegram webhook handler
- [ ] Test: Send real Telegram photo → receive confirmation and review in web app
- [x] Test: Send real Telegram PDF → receive confirmation and save in web app

### Phase 3: Hybrid OCR System
- [x] Step 9: Implement Gemini Vision API call
- [x] Step 10: Implement Ollama LLaVA fallback call
- [x] Step 11: Wire hybrid fallback logic
- [x] Step 12: Implement image storage + retention
- [x] Test: Upload receipt → verify extracted JSON
- [x] PDF preprocessing path implemented for OCR
- [x] PDF text-layer parsing implemented for summary fields

### Phase 4: Inventory Management *(parallel OK)*
- [x] Step 13: Implement product CRUD
- [x] Step 14: Implement inventory tracking + MQTT publish
- [x] Inventory search in the web app
- [ ] Step 15: Implement low-stock alerts
- [x] Test: Add/consume items
- [x] Verify MQTT events in Home Assistant or broker consumer

### Phase 5: Smart Recommendations *(parallel OK)*
- [x] Step 16: Implement recommendation engine
- [x] Add direct "Add to Shopping List" action from recommendations
- [ ] Step 17: Fully validate daily push scheduler
- [ ] Test: Seed price data → verify deal detection

### Phase 6: Analytics & Spending *(parallel OK)*
- [x] Step 18: Implement spending analytics
- [x] Step 19: Implement budget management
- [ ] Test: Seed purchases → verify spending calculations

### Phase 7: Home Assistant
- [x] Step 20: Wire MQTT publisher to all modules
- [ ] Step 21: Build HA dashboard YAML
- [ ] Step 22: Create HA automations
- [ ] Test: Change inventory → see HA update

### Phase 7.5: Receipt Review UX
- [x] Add receipts history endpoints
- [x] Add receipt image serving
- [x] Add Receipts tab in web app
- [x] Add review reprocess + approve actions
- [x] Add product-to-receipt jump links that preserve the clicked receipt selection
- [x] Test: Open receipt details and image in browser
- [x] Test: Approve a review receipt from the web app

### Phase 7.6: Shopping List & Data Cleanup
- [x] Add shopping list DB table + API
- [x] Add Shopping List tab in web app
- [x] Add manual shopping-list item creation
- [x] Add direct add-to-shopping-list actions from inventory, products, and recommendations
- [x] Canonicalize product names on save and merge case-only duplicates in live data
- [x] Canonicalize store names on save and merge case-only duplicates in live data
- [ ] Add richer OCR cleanup rules for truncated names like `Tbrush` / `HBO W/Almnds`

### Phase 8: Backup & Portability
- [ ] Step 23: Test backup script
- [ ] Step 23: Test restore script on clean machine
- [ ] Setup cron job for daily backups

### Phase 9: Testing & Validation
- [ ] Step 24: Run E2E tests
- [ ] All 10 test scenarios passing
- [ ] Documentation review complete

---

## 6. How to Resume from Any Point

### Fresh start (new machine)
```bash
git clone https://github.com/chatwithllm/LocalOCR.git
cd LocalOCR
cp .env.example .env
# Edit .env with your keys
docker-compose up -d
# Check Phase Checklist above for what to implement next
```

### Resuming after a break
1. Read `docs/IMPLEMENTATION_STATUS.md`
2. Read `docs/COMPLETE_PRODUCT_SPEC.md`
3. Read this file (`CONTINUITY.md`)
4. Check the "Completed / Verified Working / Pending" snapshot at the top of this file
5. Check the Phase Checklist (section 5) for current progress
6. Open `PROMPT.md` and find the next unchecked step
7. Each step has: file path, what to do, key considerations, testing
8. Implement, test, check off

### Handing off to someone
1. Share this repo
2. Point them to `docs/IMPLEMENTATION_STATUS.md` first
3. Then point them to `docs/COMPLETE_PRODUCT_SPEC.md`
4. Then point them to `CONTINUITY.md`
5. `PRD.md` explains the original product goals and `PROMPT.md` explains the original implementation plan
6. The continuity snapshot and phase checklist show the current state

---

## 7. Key Decisions Log

Decisions made during planning — context for anyone picking this up:

| # | Decision | Rationale | Alternatives Considered |
|---|----------|-----------|------------------------|
| 1 | **SQLite + WAL mode** over PostgreSQL | Zero config, portable, WAL handles ≤5 concurrent users | PostgreSQL (overkill for household scale) |
| 2 | **Gemini + Ollama hybrid** OCR | Free cloud accuracy + offline fallback | Tesseract (poor receipt accuracy), Gemini only (no offline) |
| 3 | **Scaled confidence formulas** (×5, ×2.5) | Raw formulas produced scores too low for the 0.70 threshold | Lower threshold to 0.10 (too noisy) |
| 4 | **0.40 confidence threshold** | After scaling, 0.40 ≈ a ~8% discount (deals) or 16% overdue (seasonal) | 0.70 (missed too many signals), 0.20 (too noisy) |
| 5 | **Bearer token auth** | Simple, stateless, no session management | OAuth2 (overkill), basic auth (less flexible) |
| 6 | **Docker-first development** (Phase 1) | Prevents "works on my machine" issues at deployment | Docker at end (Phase 8, caused integration issues) |
| 7 | **Stub upload endpoint** | Enables OCR testing without Telegram/Nginx/SSL | Wait for Telegram setup (blocked testing) |
| 8 | **MQTT for real-time sync** | Home Assistant native integration | WebSockets (not HA native), polling (too slow) |
| 9 | **Alembic migrations** | Safe schema changes post-launch | Manual ALTER TABLE (fragile, error-prone) |
| 10 | **12-month image retention** | Balance storage vs audit trail | Keep forever (disk growth), 6 months (too short) |
| 11 | **Phases 4-6 parallelizable** | Independent data consumers, enables parallel development | Sequential (slower, unnecessary dependency) |
| 12 | **Receipt review in web app** | Telegram/upload flows need an inspectable history and image preview | Terminal-only review, Home Assistant-only review |
| 13 | **Telegram webhook secret support** | Adds a simple authenticity check for webhook requests | Open webhook endpoint without shared secret |
| 14 | **Gemini model made configurable** | Avoid hard-coded retired model names and simplify future upgrades | Hard-coded model string in code |
| 15 | **Guard background services in Flask debug** | Prevent MQTT and schedulers from starting twice under the Werkzeug reloader | Let both processes start integrations and fight over broker/scheduler state |

---

## 8. Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | ✅ | — | Google Gemini Vision API key |
| `GEMINI_MODEL` | ❌ | `gemini-2.5-flash` | Gemini model name used by OCR |
| `TELEGRAM_BOT_TOKEN` | ❌ | — | Telegram bot token (only for Phase 2) |
| `TELEGRAM_WEBHOOK_BASE_URL` | ❌ | — | Public HTTPS base URL used for Telegram webhook registration |
| `TELEGRAM_WEBHOOK_SECRET` | ❌ | — | Shared secret validated on incoming Telegram webhook requests |
| `MQTT_BROKER` | ❌ | `mqtt` | MQTT broker hostname |
| `MQTT_PORT` | ❌ | `1883` | MQTT broker port |
| `FLASK_PORT` | ❌ | `8080` | Flask API port |
| `FLASK_ENV` | ❌ | `development` | Flask environment |
| `DATABASE_URL` | ❌ | `sqlite:////data/db/grocery.db` | SQLAlchemy DB URL |
| `OLLAMA_ENDPOINT` | ❌ | `http://ollama:11434` | Ollama API endpoint |
| `RECOMMENDATION_TIME` | ❌ | `08:00` | Daily recommendation push time |
| `RECEIPT_RETENTION_MONTHS` | ❌ | `12` | Image retention period |
| `INITIAL_ADMIN_TOKEN` | ✅ | — | First-run admin token |

---

## 9. Known Gotchas

1. **SQLite WAL mode must be set on EVERY connection** — use `event.listen(engine, "connect", ...)` in SQLAlchemy, not a one-time PRAGMA
2. **Ollama first start is slow** — model download (~2GB) happens on first `ollama pull`
3. **Gemini 429 errors** — trigger Ollama fallback, don't retry Gemini immediately
4. **MQTT retain flag** — set to True for inventory state so Home Assistant sees last state on reconnect
5. **Telegram webhook timeout** — must respond within 30 seconds or Telegram retries
6. **Docker Compose `mqtt` service name** — use `mqtt` not `localhost` when connecting from backend container
7. **SQLite database path** — must be on a Docker volume (`/data/db/`), not inside the container filesystem
8. **Telegram works only with public HTTPS** — a valid local bot token is not enough by itself
9. **Receipt review depends on stored image paths** — keep receipt storage under the configured receipts root
10. **PDF OCR depends on `pdftoppm`** — Docker installs it, but local non-Docker setups need Poppler installed

---

## 10. Useful Commands

```bash
# Start everything
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f mqtt

# Rebuild after code changes
docker-compose build backend && docker-compose up -d backend

# Run tests
docker exec grocery-backend pytest tests/ -v

# Database shell
docker exec grocery-backend python -c "from src.backend.initialize_database_schema import *; print('Schema OK')"

# MQTT test publish
docker exec grocery-mqtt mosquitto_pub -t "test" -m "hello"

# Ollama model status
docker exec grocery-ollama ollama list

# Telegram webhook status
./.venv/bin/python -m src.backend.configure_telegram_webhook status

# Register Telegram webhook
./.venv/bin/python -m src.backend.configure_telegram_webhook set --base-url https://inventory.npalakurla.net

# Backup
docker exec grocery-backend bash /app/scripts/backup_database_and_volumes.sh
```
