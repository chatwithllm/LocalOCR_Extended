# Deployment Guide

## Prerequisites

Before deploying, ensure you have:

- [ ] **Docker Desktop** installed ([download](https://docs.docker.com/desktop/))
- [ ] **Docker Compose** v2+ (included with Docker Desktop)
- [ ] **Google Gemini API key** ([get free key](https://ai.google.dev/))
- [ ] **Telegram Bot token** (optional — create via [@BotFather](https://t.me/botfather))
- [ ] **Home Assistant** instance running locally (for dashboard)
- [ ] **Nginx Proxy Manager** with domain + SSL (only if using Telegram)
- [ ] At least **4GB free RAM** (Ollama needs ~2-4GB)
- [ ] At least **5GB free disk** (Ollama model + receipt images)

---

If you want the shortest operator-friendly path, start with [APP_SETUP_GUIDE.md](APP_SETUP_GUIDE.md). This deployment guide goes a bit deeper.

## Step 1: Clone & Configure

```bash
# Clone the repository
git clone https://github.com/chatwithllm/LocalOCR.git
cd LocalOCR

# Create environment file
cp .env.example .env

# Edit with your values
nano .env  # or vim, code, etc.
```

**Required `.env` values:**
```
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash
INITIAL_ADMIN_TOKEN=generate_a_secure_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=choose_a_strong_password
SESSION_SECRET=generate_another_secure_secret
```

**Useful optional `.env` values:**
```
OLLAMA_ENDPOINT=http://ollama:11434
MQTT_BROKER=mqtt
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
HOME_ASSISTANT_BASE_URL=http://homeassistant.local:8123
```

**Optional (for Telegram):**
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_BASE_URL=https://grocery.yourdomain.com
TELEGRAM_WEBHOOK_SECRET=your_random_secret
```

---

## Step 2: Start Services

```bash
# Start all containers (first run will build + download images)
docker compose up -d --build

# Watch logs
docker compose logs -f

# Verify all services are healthy
docker compose ps
```

If you are running the backend directly instead of Docker, the Flask app now auto-loads `.env` on startup for local development.
PDF receipt support requires `pdftoppm` to be available. The Docker image now installs it automatically; on a local host install Poppler if it is missing.

**Expected output:**
```
NAME               STATUS          PORTS
grocery-backend    Up (healthy)    0.0.0.0:8080->8080/tcp
grocery-mqtt       Up (healthy)    0.0.0.0:1883->1883/tcp
grocery-ollama     Up (healthy)    0.0.0.0:11434->11434/tcp
```

---

## Step 3: Verify Services

```bash
# Backend health check
curl http://localhost:8080/health

# MQTT broker (install mosquitto-clients if needed)
mosquitto_pub -h localhost -t "test" -m "hello"

# Ollama (may take a minute on first start)
curl http://localhost:11434/api/tags
```

---

## Step 4: Pull Ollama Model (First Run Only)

```bash
# Enter ollama container and pull LLaVA model (~2GB download)
docker exec -it grocery-ollama ollama pull llava:7b
```

---

## Step 5: Bootstrap Browser Login

```bash
# Generate secure secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `http://localhost:8080` and sign in with:

- email: `INITIAL_ADMIN_EMAIL`
- password: `INITIAL_ADMIN_PASSWORD`

If `INITIAL_ADMIN_PASSWORD` is blank, the app falls back to `INITIAL_ADMIN_TOKEN` for the first browser login.

---

## Step 6: Test API Token Access

`INITIAL_ADMIN_TOKEN` is still useful for direct API access and integrations.

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8080/auth/me
```

---

## Step 7: Test Receipt Upload

```bash
# Upload a test receipt
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@path/to/receipt.jpg"

# Or upload a PDF receipt
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@path/to/receipt.pdf"
```

---

## Step 8: Configure Home Assistant (Optional)

1. Add MQTT integration in Home Assistant
2. Point to the broker configured in `.env`
3. Import dashboard config from `config/home_assistant_dashboard_config.yaml`
4. Import automations from `config/home_assistant_automations.yaml`

---

## Step 9: Configure Telegram (Optional)

1. Expose the backend through a public HTTPS URL
2. Set `TELEGRAM_WEBHOOK_BASE_URL` and `TELEGRAM_WEBHOOK_SECRET` in `.env`
3. Register the webhook:

```bash
./.venv/bin/python -m src.backend.configure_telegram_webhook set
./.venv/bin/python -m src.backend.configure_telegram_webhook status
```

See [NGINX_PROXY_MANAGER_SETUP.md](NGINX_PROXY_MANAGER_SETUP.md) for proxy routing details.

---

## Maintenance

### Automatic Start After Reboot

The containers already use Docker restart policies. To make the app come back after a machine reboot:

1. Configure Docker Desktop / Docker Engine to start automatically on boot
2. Bring the stack up once:

```bash
docker compose up -d
```

After that, Docker should restart the services automatically unless you explicitly stop them.

### Daily Backup (Automatic)
```bash
# Manual trigger
docker exec grocery-backend /app/scripts/backup_database_and_volumes.sh

# Backups stored in /data/backups/
```

### Restore from Backup
```bash
docker exec grocery-backend /app/scripts/restore_from_backup.sh /data/backups/grocery_backup_20260401.tar.gz
```

### Update
```bash
git pull
cp .env.example .env  # only if setting up on a fresh machine
edit .env             # keep secrets local; never commit them
docker compose up -d --build
```

### Stop
```bash
docker compose down        # Stop containers (data preserved in volumes)
docker compose down -v     # Stop AND delete data (careful!)
```
