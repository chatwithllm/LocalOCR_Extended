# 🛒 Grocery Inventory & Savings Management System

A **privacy-first, local-first** grocery management system for households. Upload receipts, track inventory across devices, get smart recommendations, and monitor spending — all self-hosted with zero ongoing costs.

This repo is set up to run like an app via Docker Compose, not just as a developer sandbox.

## ✨ Features

- **📸 Receipt OCR** — Send a photo or PDF via Telegram or upload directly. Hybrid OCR (Gemini + Ollama fallback) extracts items automatically.
- **📦 Real-Time Inventory** — Shared household inventory synced across all devices via MQTT in <2 seconds.
- **💡 Smart Recommendations** — Detects price deals (≥10% discount) and recurring purchase patterns.
- **📊 Spending Analytics** — Budget tracking, price trends, savings quantification, store comparison.
- **🏠 Home Assistant Dashboard** — Unified view with inventory, alerts, recommendations, and analytics cards.
- **👤 Household Login** — Browser users sign in with local email/password accounts, while API tokens remain available for integrations.
- **🏠 Household User Management** — The bootstrap admin can create separate accounts for each household member from the web app.
- **🛡️ Admin Controls** — Admins can edit users, reset passwords, and deactivate accounts without losing the last admin login.
- **🔐 Forgot Password Flow** — Existing users can request a reset from the login screen, and the admin can fulfill it from Settings.
- **📱 Mobile-Friendly Navigation** — Smaller screens now use a compact top bar and slide-out menu instead of a fixed sidebar.
- **🔒 Privacy-First** — All data stays on your local network. SQLite database, Docker deployment, full backup/restore.

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd "Inventory Management"

# 2. Configure environment
cp .env.example .env
# Edit .env with your Gemini API key, bootstrap admin email/password, API token, Telegram bot token, etc.

# 3. Start all services
docker compose up -d --build

# 4. Verify services are running
curl http://localhost:8080/health     # Backend
curl http://localhost:11434/api/tags  # Ollama

# 5. Sign in to the web app
# Open http://localhost:8080 and log in with:
#   email: INITIAL_ADMIN_EMAIL
#   password: INITIAL_ADMIN_PASSWORD
# If INITIAL_ADMIN_PASSWORD is blank, the first browser login falls back to INITIAL_ADMIN_TOKEN.

# 6. Upload a test receipt by API token
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@path/to/receipt.jpg"

# PDF receipts work too
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@path/to/receipt.pdf"
```

For a guided "fill in the placeholders and launch the app" setup, read [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md).

For a current handoff snapshot of what is finished and what still needs work, see [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## 📁 Project Structure

```
├── PRD.md                    # Product requirements
├── PROMPT.md                 # Implementation guide (24 steps)
├── CONTINUITY.md             # Restart & resume documentation
├── docker-compose.yml        # Service orchestration
├── Dockerfile                # Backend container
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── src/backend/              # Flask API (18 modules)
├── config/                   # MQTT, Home Assistant configs
├── scripts/                  # Backup & restore scripts
├── tests/                    # End-to-end tests
├── docs/                     # Architecture, API, deployment guides
└── alembic/                  # Database migrations
```

## 🏗️ Architecture

```
📱 Telegram / Upload ──→ Flask API (port 8080) ──→ Gemini / Ollama OCR
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
               Inventory  Analytics  Recommendations
                    │         │         │
                    └─────────┼─────────┘
                              ▼
                    MQTT (port 1883) ──→ Home Assistant
```

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [PRD.md](PRD.md) | Product requirements & acceptance criteria |
| [PROMPT.md](PROMPT.md) | 24-step implementation guide |
| [CONTINUITY.md](CONTINUITY.md) | Restart/resume project from any point |
| [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md) | App-style first-run setup guide |
| [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | Current working status + restart handoff |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture details |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | API endpoint documentation |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Step-by-step deployment |

## 🔧 Tech Stack

- **Backend:** Python 3.11 + Flask
- **Database:** SQLite (WAL mode) + Alembic migrations
- **OCR:** Google Gemini Vision API + Ollama LLaVA (fallback)
- **Real-Time:** MQTT (Mosquitto)
- **Frontend:** Home Assistant YAML dashboard
- **Deployment:** Docker Compose
- **Cost:** $0/month (free Gemini tier + self-hosted)

## Auto-Start

The Docker services use `restart: unless-stopped`, so once the stack has been started successfully and Docker itself is configured to launch on boot, the app comes back automatically after a machine restart.

## 📄 License

Private project. All rights reserved.
