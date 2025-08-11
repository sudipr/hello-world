# Telegram Bot (python-telegram-bot)

A robust Telegram bot implemented in Python using `python-telegram-bot` v21 (async). Includes command menu, utility commands, admin broadcast, JSON persistence of users, per-user rate limiting, welcome messages, non-text filtering, optional webhook mode, and a simple healthcheck server.

## Prerequisites
- Python 3.10+
- A Telegram Bot token from BotFather

## Quick start
1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv || python3 -m venv --without-pip .venv && . .venv/bin/activate && curl -sSLo /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python /tmp/get-pip.py
   . .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. Set environment variables (replace with your values):
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
   export ADMIN_USER_IDS="123456789,987654321"   # optional, comma-separated telegram user IDs
   export DATA_DIR="./data"                      # optional, default ./data
   export BOT_MODE="polling"                     # or "webhook"
   export WEBHOOK_URL="https://example.com/your/path"    # required for webhook
   export WEBHOOK_SECRET="your-secret-token"              # required for webhook
   export PORT=8080                               # webhook listen port (default 8080)
   export HEALTHCHECK_PORT=8081                   # optional; serves /healthz
   ```
3. Run the bot:
   ```bash
   python bot.py
   ```

The bot uses long polling by default. Press Ctrl+C to stop.

## Features
- Command menu: sets `/start`, `/help`, `/ping`, `/about`, `/id`, `/time`, `/broadcast`
- Utilities: `/about`, `/id`, `/time`, `/ping`
- Admin broadcast: `/broadcast <text>` sends to all known users (from persistence)
- Persistence: JSON file at `DATA_DIR/users.json` with basic user fields
- Rate limiting: simple per-user limiter (non-admins) to prevent spam
- Welcome message: greets new chat members
- Non-text filtering: friendly notice for non-text content
- Healthcheck: optional HTTP server responding `OK` at `/healthz`
- Webhook mode: configurable HTTPS URL + secret token

## Webhook mode
Set `BOT_MODE=webhook`, `WEBHOOK_URL` to your public HTTPS endpoint, and `WEBHOOK_SECRET` to a secret token. The bot will listen on `0.0.0.0:$PORT` and register the webhook on startup.

## Docker
1. Build image:
   ```bash
   docker build -t telegram-bot:latest .
   ```
2. Run (polling):
   ```bash
   docker run --rm \
     -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
     -e ADMIN_USER_IDS="$ADMIN_USER_IDS" \
     -e DATA_DIR="/data" \
     -e HEALTHCHECK_PORT="8081" \
     -v $(pwd)/data:/data \
     -p 8081:8081 \
     telegram-bot:latest
   ```
3. Run (webhook):
   ```bash
   docker run --rm \
     -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
     -e BOT_MODE=webhook \
     -e WEBHOOK_URL="$WEBHOOK_URL" \
     -e WEBHOOK_SECRET="$WEBHOOK_SECRET" \
     -e PORT=8080 \
     -p 8080:8080 \
     telegram-bot:latest
   ```

## Notes
- Admin user IDs must be numeric Telegram user IDs, not usernames.
- Broadcast targets only users who have interacted with the bot since it started tracking users (stored in JSON).
- Rate limiting currently exempts admins.

## Troubleshooting
- If the bot does not start, ensure `TELEGRAM_BOT_TOKEN` is set and valid.
- For webhook mode, verify your URL is reachable by Telegram and responds with 200.
- When running in Docker, persist `DATA_DIR` with a volume to retain users.