import asyncio
import json
import logging
import os
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Dict, Final, Optional, Set

from telegram import BotCommand, Update, User
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


LOG_LEVEL: Final[int] = logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("telegram-bot")


# -----------------------------
# Configuration
# -----------------------------
@dataclass(frozen=True)
class Config:
    token: str
    admin_user_ids: Set[int]
    data_dir: str
    users_db_path: str
    bot_mode: str  # "polling" or "webhook"
    webhook_url: Optional[str]
    webhook_secret: Optional[str]
    webhook_port: int
    healthcheck_port: Optional[int]


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Export it and retry.")
        sys.exit(1)

    admin_env = os.getenv("ADMIN_USER_IDS", "").strip()
    admin_user_ids: Set[int] = set()
    if admin_env:
        for part in admin_env.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                admin_user_ids.add(int(part))
            except ValueError:
                logger.warning("Ignoring non-integer ADMIN_USER_IDS entry: %s", part)

    data_dir = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
    users_db_path = os.path.join(data_dir, "users.json")

    bot_mode = os.getenv("BOT_MODE", "polling").strip().lower()
    webhook_url = os.getenv("WEBHOOK_URL")
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    webhook_port = int(os.getenv("PORT", "8080"))

    healthcheck_port_env = os.getenv("HEALTHCHECK_PORT", "")
    healthcheck_port = int(healthcheck_port_env) if healthcheck_port_env else None

    return Config(
        token=token,
        admin_user_ids=admin_user_ids,
        data_dir=data_dir,
        users_db_path=users_db_path,
        bot_mode=bot_mode,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        webhook_port=webhook_port,
        healthcheck_port=healthcheck_port,
    )


# -----------------------------
# Persistence (JSON)
# -----------------------------
class UserStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._users: Dict[str, Dict] = {}

    async def load(self) -> None:
        async with self._lock:
            try:
                if os.path.exists(self._path):
                    with open(self._path, "r", encoding="utf-8") as f:
                        self._users = json.load(f)
                else:
                    self._users = {}
            except Exception:
                logger.exception("Failed to load users DB; starting with empty store")
                self._users = {}

    async def save(self) -> None:
        async with self._lock:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                tmp_path = f"{self._path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._users, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self._path)
            except Exception:
                logger.exception("Failed to save users DB")

    async def upsert_user(self, user: User) -> None:
        async with self._lock:
            key = str(user.id)
            record = self._users.get(key) or {}
            record.update(
                {
                    "id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_bot": user.is_bot,
                    "language_code": getattr(user, "language_code", None),
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "message_count": int(record.get("message_count", 0)) + 1,
                }
            )
            self._users[key] = record
        await self.save()

    async def all_user_ids(self) -> Set[int]:
        async with self._lock:
            return {int(k) for k in self._users.keys()}


# -----------------------------
# Rate Limiting (simple token bucket)
# -----------------------------
class RateLimiter:
    def __init__(self, max_events: int, per_seconds: float) -> None:
        self.max_events = max_events
        self.per_seconds = per_seconds
        self._user_to_events: Dict[int, deque] = {}

    def is_allowed(self, user_id: int) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        dq = self._user_to_events.setdefault(user_id, deque())
        # Drop old events
        while dq and (now - dq[0]) > self.per_seconds:
            dq.popleft()
        if len(dq) >= self.max_events:
            return False
        dq.append(now)
        return True


# -----------------------------
# Healthcheck Server (optional)
# -----------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # type: ignore[override]
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:  # mute default logging
        return


def start_healthcheck_server(port: int) -> Thread:
    def run_server() -> None:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        try:
            server.serve_forever()
        except Exception:
            pass
        finally:
            server.server_close()

    thread = Thread(target=run_server, name=f"healthcheck:{port}", daemon=True)
    thread.start()
    logger.info("Healthcheck server running on :%d/healthz", port)
    return thread


# -----------------------------
# Handlers
# -----------------------------
rate_limiter = RateLimiter(max_events=5, per_seconds=10.0)
user_store: Optional[UserStore] = None
config: Optional[Config] = None


def is_admin(user_id: Optional[int]) -> bool:
    if user_id is None or config is None:
        return False
    return user_id in config.admin_user_ids


async def record_user_activity(update: Update) -> None:
    global user_store
    if not user_store:
        return
    user = update.effective_user
    if user:
        await user_store.upsert_user(user)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "Hi! I'm your bot.\n\n"
            "Commands:\n"
            "- /help — show help\n"
            "- /ping — health check\n"
            "- /about — about this bot\n"
            "- /id — show your user and chat id\n"
            "- /time — show server time"
        ),
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "I can echo your messages and respond to commands.\n\n"
            "Available commands:\n"
            "- /start — welcome\n"
            "- /help — this help\n"
            "- /ping — health check\n"
            "- /about — about this bot\n"
            "- /id — your id\n"
            "- /time — server time\n"
            "- /broadcast <text> — admin only"
        ),
    )


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    text = (
        "<b>Telegram Bot</b>\n"
        "Built with python-telegram-bot v21."
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode=ParseMode.HTML)


async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    user = update.effective_user
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Your ID: {user.id if user else 'unknown'}\nChat ID: {update.effective_chat.id}",
    )


async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    now = datetime.now(timezone.utc)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Server time (UTC): {now.isoformat()}")


async def handle_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="pong")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin(user_id):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Unauthorized: admin only")
        return

    args_text = (" ".join(context.args)).strip() if context.args else ""
    if not args_text:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /broadcast <text>")
        return

    global user_store
    target_ids: Set[int] = set()
    if user_store:
        target_ids = await user_store.all_user_ids()
    if not target_ids:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No known users to broadcast to yet.")
        return

    sent = 0
    failed = 0
    for uid in sorted(target_ids):
        try:
            await context.bot.send_message(chat_id=uid, text=args_text)
            sent += 1
        except Exception as e:
            logger.warning("Broadcast to %s failed: %s", uid, e)
            failed += 1
            continue
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Broadcast done. Sent: {sent}, Failed: {failed}")


async def handle_text_echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.message or not update.effective_chat:
        return
    user = update.effective_user
    if user and not is_admin(user.id):
        if not rate_limiter.is_allowed(user.id):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Slow down, please.")
            return
    text = update.message.text or ""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    user = update.effective_user
    if user and not is_admin(user.id):
        if not rate_limiter.is_allowed(user.id):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Slow down, please.")
            return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I didn't understand that command. Try /help",
    )


async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await record_user_activity(update)
    if not update.effective_chat:
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Please send text messages.")


async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat or not update.message:
        return
    for member in update.message.new_chat_members:
        name = member.first_name or (member.username or "there")
        await context.bot.send_message(chat_id=chat.id, text=f"Welcome, {name}! 👋")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Error while handling update: %s", update)


async def set_bot_commands(application: Application) -> None:
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help"),
        BotCommand("ping", "Health check"),
        BotCommand("about", "About this bot"),
        BotCommand("id", "Show your ID"),
        BotCommand("time", "Server time"),
        BotCommand("broadcast", "Admin: broadcast a message"),
    ]
    await application.bot.set_my_commands(commands)


async def run_polling(application: Application) -> None:
    logger.info("Starting bot with long polling...")
    await application.initialize()
    await application.start()
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        await application.run_polling(close_loop=False, allowed_updates=Update.ALL_TYPES)
    finally:
        logger.info("Shutting down bot...")
        await application.stop()
        await application.shutdown()


async def run_webhook(application: Application, cfg: Config) -> None:
    if not cfg.webhook_url or not cfg.webhook_secret:
        logger.error("WEBHOOK_URL and WEBHOOK_SECRET must be set for webhook mode")
        sys.exit(1)
    logger.info(
        "Starting webhook on 0.0.0.0:%d with URL %s",
        cfg.webhook_port,
        cfg.webhook_url,
    )
    await application.initialize()
    await application.start()
    try:
        await application.bot.set_webhook(url=cfg.webhook_url, secret_token=cfg.webhook_secret, drop_pending_updates=True)
        await application.run_webhook(
            listen="0.0.0.0",
            port=cfg.webhook_port,
            url_path="",  # full URL provided above
            secret_token=cfg.webhook_secret,
            close_loop=False,
            allowed_updates=Update.ALL_TYPES,
        )
    finally:
        logger.info("Shutting down webhook...")
        await application.stop()
        await application.shutdown()


async def run() -> None:
    global user_store, config
    config = load_config()

    # Prepare persistence
    os.makedirs(config.data_dir, exist_ok=True)
    user_store = UserStore(config.users_db_path)
    await user_store.load()

    # Optional healthcheck server
    if config.healthcheck_port:
        start_healthcheck_server(config.healthcheck_port)

    application = Application.builder().token(config.token).build()

    # Set slash commands
    await set_bot_commands(application)

    # Handlers
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("ping", handle_ping))
    application.add_handler(CommandHandler("about", handle_about))
    application.add_handler(CommandHandler("id", handle_id))
    application.add_handler(CommandHandler("time", handle_time))
    application.add_handler(CommandHandler("broadcast", handle_broadcast))

    # Welcome messages for new chat members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))

    # Text echo and non-text filter
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_echo))
    application.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, handle_non_text))

    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))

    application.add_error_handler(on_error)

    if config.bot_mode == "webhook":
        await run_webhook(application, config)
    else:
        await run_polling(application)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass