# App Setup Guide

Use this guide when setting up the project as an actual household app, not as a development environment.

## What You Need

- Docker Desktop or Docker Engine with Compose support
- A Gemini API key
- Optional:
  - Telegram bot token
  - public HTTPS URL for Telegram
  - Home Assistant
  - external Ollama server if you do not want the bundled container

## 1. Clone The App

```bash
git clone https://github.com/chatwithllm/LocalOCR.git
cd LocalOCR
cp .env.example .env
```

## 2. Fill In `.env`

Open `.env` and fill in these first:

```dotenv
INITIAL_ADMIN_TOKEN=replace_with_a_long_random_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=replace_with_a_strong_password
SESSION_SECRET=replace_with_another_long_random_secret
GEMINI_API_KEY=replace_with_your_gemini_api_key
```

Recommended defaults that usually do not need changing:

```dotenv
FLASK_ENV=production
FLASK_PORT=8080
FLASK_DEBUG=0
MQTT_BROKER=mqtt
MQTT_PORT=1883
OLLAMA_ENDPOINT=http://ollama:11434
OLLAMA_MODEL=llava:7b
```

If you run Ollama on another machine, update:

```dotenv
OLLAMA_ENDPOINT=http://192.168.1.50:11434
```

If you use Telegram, also fill in:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_BASE_URL=https://inventory.yourdomain.com
TELEGRAM_WEBHOOK_SECRET=
```

If you use an external MQTT broker instead of the bundled one:

```dotenv
MQTT_BROKER=192.168.1.20
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
```

## 3. Start The App

```bash
docker compose up -d --build
```

Check health:

```bash
curl http://localhost:8080/health
docker compose ps
```

## 4. Pull The Ollama Model

Only needed if you are using the bundled Ollama container.

```bash
docker exec -it grocery-ollama ollama pull llava:7b
```

## 5. Open The App

Open:

```text
http://localhost:8080
```

Log in with:

- email: `INITIAL_ADMIN_EMAIL`
- password: `INITIAL_ADMIN_PASSWORD`

If you leave `INITIAL_ADMIN_PASSWORD` blank, the app falls back to `INITIAL_ADMIN_TOKEN` for the first browser login. Keep `INITIAL_ADMIN_TOKEN` anyway if you want direct API or integration access.

After the first admin login, open `Settings` in the web app and create one account per household member under `Household Users`.
Admins can also edit users, reset passwords, and deactivate accounts from the same screen.
If a household user forgets their password, they can click `Forgot Password?` on the login banner. That creates an admin-visible reset request; it does not create a public self-registration path.

## 6. Optional: Telegram Setup

Telegram only works if your app is exposed through public HTTPS.

After your reverse proxy/domain is working:

```bash
docker compose exec backend python -m src.backend.configure_telegram_webhook set
docker compose exec backend python -m src.backend.configure_telegram_webhook status
```

## 7. Optional: Home Assistant Setup

1. Add the MQTT integration in Home Assistant.
2. Point it to the broker you configured in `.env`.
3. Import:
   - `config/home_assistant_dashboard_config.yaml`
   - `config/home_assistant_automations.yaml`

## 8. Auto-Start On Machine Boot

This app is already configured for Docker restarts:

- `backend`: `restart: unless-stopped`
- `mqtt`: `restart: unless-stopped`
- `ollama`: `restart: unless-stopped`

To make it start automatically after the machine reboots:

1. Make sure Docker itself starts automatically on login/boot.
2. Leave the stack running once with:

```bash
docker compose up -d
```

After that, Docker will restart the containers automatically.

## 9. Day-To-Day Operations

View logs:

```bash
docker compose logs -f backend
docker compose logs -f ollama
docker compose logs -f mqtt
```

Stop:

```bash
docker compose down
```

Update the app:

```bash
git pull
docker compose up -d --build
```

## Notes

- PDF receipt support requires Poppler tools. The Docker image already installs what the app needs.
- Telegram PDF receipt processing is verified working.
- Dense receipts may still need manual review for some product names/categories, but date and total extraction is now much stronger for PDFs.
