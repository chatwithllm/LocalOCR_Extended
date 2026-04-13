# Architecture

## System Overview

This document still contains some legacy grocery-era labels, but the active Extended runtime is now centered on `8090` and the `localocr_extended` data paths.

The Grocery Inventory & Savings Management System is a **local-first, privacy-first** application deployed via Docker Compose on a home server (Mac mini).

```
┌──────────────────────────────────────────────────────────────────┐
│                        External Network                         │
│                                                                  │
│  📱 Telegram ──→ Nginx Proxy Manager ──→ ┐                      │
│                  (HTTPS / SSL)            │                      │
└──────────────────────────────────────────│───────────────────────┘
                                           │
┌──────────────────────────────────────────│───────────────────────┐
│                   Docker Compose Stack   │                      │
│                                          ▼                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Flask Backend (port 8080)                    │    │
│  │                                                          │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │    │
│  │  │  Telegram     │  │  Receipt     │  │  Auth        │   │    │
│  │  │  Webhook      │  │  Upload      │  │  Middleware   │   │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────────┘   │    │
│  │         │                  │                              │    │
│  │         ▼                  ▼                              │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │          Hybrid OCR Processor                     │    │    │
│  │  │   Gemini Vision API ──→ Ollama LLaVA (fallback)  │    │    │
│  │  └────────────────────┬─────────────────────────────┘    │    │
│  │                       │                                   │    │
│  │         ┌─────────────┼─────────────┐                    │    │
│  │         ▼             ▼             ▼                    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐          │    │
│  │  │ Inventory│  │ Product  │  │ Price History │          │    │
│  │  │ Manager  │  │ Catalog  │  │ Tracker      │          │    │
│  │  └────┬─────┘  └──────────┘  └──────┬───────┘          │    │
│  │       │                              │                   │    │
│  │       ▼                              ▼                   │    │
│  │  ┌──────────┐              ┌──────────────────┐         │    │
│  │  │ Low-Stock│              │ Recommendations  │         │    │
│  │  │ Alerts   │              │ Engine           │         │    │
│  │  └────┬─────┘              └────────┬─────────┘         │    │
│  │       │                              │                   │    │
│  │       ▼                              ▼                   │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │              MQTT Publisher                       │    │    │
│  │  └────────────────────┬─────────────────────────────┘    │    │
│  └───────────────────────│──────────────────────────────────┘    │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐    │
│  │          Mosquitto MQTT Broker (port 1883)                │    │
│  └───────────────────────┬──────────────────────────────────┘    │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐    │
│  │                SQLite Database (WAL mode)                 │    │
│  │                /data/db/grocery.db                        │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │          Ollama (port 11434) — LLaVA model               │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│              Home Assistant (External)                           │
│   MQTT Sensors → Dashboard Cards → Mobile App                   │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Receipt Processing Pipeline
1. User sends receipt photo (Telegram or Upload endpoint)
2. Image saved to `/data/receipts/{year}/{month}/`
3. Gemini Vision API extracts data (JSON)
4. If Gemini fails → Ollama LLaVA fallback
5. Validated data stored in `purchases` + `receipt_items` tables
6. Price history updated in `price_history` table
7. Inventory auto-updated
8. MQTT event published → Home Assistant updates in real-time

### Product Snapshot Pipeline
1. User adds a supporting item photo from a shopping row or receipt extracted-item row
2. Image is stored under `/data/product_snapshots/`
3. Snapshot metadata is stored in `product_snapshots`
4. The related shopping item or receipt item exposes that snapshot as its `latest_snapshot`
5. Shopping and receipt review surfaces switch from `Add Photo` to `View Photo`
6. Admins can review pending snapshots from Settings and archive or resolve them into product context

### Real-Time Sync
- Every inventory/alert/recommendation change publishes to MQTT
- Home Assistant subscribes to MQTT topics
- All household devices see updates within <2 seconds

## Component Responsibilities

| Component | File | Responsibility |
|-----------|------|---------------|
| Database | `initialize_database_schema.py` | SQLite + WAL mode + Alembic |
| Flask App | `create_flask_application.py` | HTTP API + auth middleware |
| MQTT | `setup_mqtt_connection.py` | Broker connection + pub/sub |
| Upload | `handle_receipt_upload.py` | Stub upload endpoint |
| Telegram | `handle_telegram_messages.py` | Webhook handler + feedback |
| Gemini OCR | `call_gemini_vision_api.py` | Primary OCR engine |
| Ollama OCR | `call_ollama_vision_api.py` | Fallback OCR engine |
| OCR Orchestrator | `extract_receipt_data.py` | Hybrid fallback logic |
| Image Storage | `save_receipt_images.py` | Save + thumbnail + retention |
| Products | `manage_product_catalog.py` | Product CRUD |
| Product Snapshots | `manage_product_snapshots.py` | Upload, serve, and review supporting item photos |
| Inventory | `manage_inventory.py` | Inventory CRUD + MQTT |
| Alerts | `check_inventory_thresholds.py` | Low-stock detection |
| Recommendations | `generate_recommendations.py` | Deal + seasonal detection |
| Scheduler | `schedule_daily_recommendations.py` | 8 AM daily push |
| Analytics | `calculate_spending_analytics.py` | Spending reports |
| Budget | `manage_household_budget.py` | Budget tracking |
| MQTT Publisher | `publish_mqtt_events.py` | Centralized MQTT publish |

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite + WAL** | Zero config, portable, WAL mode handles ≤5 concurrent household users |
| **Gemini + Ollama hybrid** | Free cloud accuracy + offline fallback, zero cost |
| **MQTT for sync** | Home Assistant native, retained messages survive reconnects |
| **Docker Compose** | Portable, reproducible, everything runs with `docker-compose up` |
| **Bearer token auth** | Simple, stateless, sufficient for local network |
| **Alembic migrations** | Safe schema evolution without manual ALTER TABLE |
| **Scaled confidence** | Raw formulas produced unusable scores; ×5 and ×2.5 multipliers align with 0.40 threshold |
