import asyncio
import logging
import os
import sys
from typing import Final

from telegram import Update
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


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "Hi! I'm your bot.\n\n"
            "Commands:\n"
            "- /help — show help\n"
            "- /ping — health check"
        ),
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "I can echo your messages and respond to a few commands.\n\n"
            "Available commands:\n"
            "- /start — welcome\n"
            "- /help — this help\n"
            "- /ping — health check"
        ),
    )


async def handle_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="pong")


async def handle_text_echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    text = update.message.text or ""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I didn't understand that command. Try /help",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Error while handling update: %s", update)


async def run() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Export it and retry.")
        sys.exit(1)

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("ping", handle_ping))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_echo))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))

    application.add_error_handler(on_error)

    logger.info("Starting bot with long polling...")

    # Drop any pending updates on start; ensures clean startup
    await application.initialize()
    await application.start()

    # Run polling until Ctrl+C
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        await application.run_polling(close_loop=False, allowed_updates=Update.ALL_TYPES)
    finally:
        logger.info("Shutting down bot...")
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass