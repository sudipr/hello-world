# Telegram Bot (python-telegram-bot)

A minimal, production-ready Telegram bot implemented in Python using `python-telegram-bot` v21 (async). It supports `/start`, `/help`, `/ping`, echoes text messages, and handles unknown commands gracefully.

## Prerequisites
- Python 3.10+
- A Telegram Bot token from BotFather

## Quick start
1. Clone/open this project directory: `telegram-bot`
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Set your bot token (replace with your actual token):
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

The bot uses long polling by default. Press Ctrl+C to stop.

## Commands
- `/start` — welcome message
- `/help` — brief help
- `/ping` — health check reply with `pong`

Any other text message will be echoed back. Unknown commands receive a friendly notice.

## Configuration
- `TELEGRAM_BOT_TOKEN` (required): Telegram bot token from BotFather

You can use a `.env` file locally (copy `.env.example` to `.env` and export values before running), or set environment variables in your runtime platform.

## Run with Docker
1. Build image:
   ```bash
   docker build -t telegram-bot:latest .
   ```
2. Run container (pass token as env):
   ```bash
   docker run --rm -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" telegram-bot:latest
   ```

## Deploying
For simple deployments, running the Docker image on any VPS/container platform is sufficient. For webhooks, you would need to host an HTTPS endpoint and configure the bot with a public URL. This template uses polling by default for simplicity.

## Development
- Format/lint as you prefer; this template has minimal dependencies.
- The code is in `bot.py`.

## Troubleshooting
- If the bot does not start, ensure `TELEGRAM_BOT_TOKEN` is set and valid.
- Ensure your system time is correct; significant clock skew can cause auth issues.
- Network egress must be allowed to Telegram API.