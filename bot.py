from __future__ import annotations

import logging
import os
from html import escape

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from storage import Storage


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def chat_title(update: Update) -> str | None:
    chat = update.effective_chat
    if not chat:
        return None
    return chat.title or getattr(chat, "full_name", None) or chat.username


def register_chat(update: Update, storage: Storage, *, is_active: bool = True) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return
    storage.upsert_chat(
        chat_id=chat.id,
        chat_type=chat.type,
        title=chat_title(update),
        username=user.username if user else chat.username,
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        is_active=is_active,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    register_chat(update, storage, is_active=True)
    await update.message.reply_html(
        "This chat is now subscribed.\n\n"
        "Commands:\n"
        "/id - show the current chat id\n"
        "/status - show subscription status\n"
        "/stop - stop receiving messages\n"
        "/help - show help"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_chat(update, context.application.bot_data["storage"], is_active=True)
    await update.message.reply_text(
        "This bot receives Telegram messages for Jiayi automations.\n\n"
        "Commands:\n"
        "/start subscribe this chat\n"
        "/id show the current chat id\n"
        "/status show status\n"
        "/stop stop receiving messages"
    )


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_chat(update, context.application.bot_data["storage"], is_active=True)
    chat = update.effective_chat
    await update.message.reply_text(f"TELEGRAM_CHAT_ID={chat.id}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    register_chat(update, storage, is_active=True)
    active_count = len(storage.active_chat_ids())
    await update.message.reply_text(f"This chat is active. Active chat count: {active_count}")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    chat = update.effective_chat
    if chat:
        storage.set_active(chat.id, False)
    await update.message.reply_text("This chat has been disabled. Send /start to enable it again.")


async def record_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    register_chat(update, storage, is_active=True)
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if chat and message:
        storage.save_message(
            chat_id=chat.id,
            user_id=user.id if user else None,
            username=user.username if user else None,
            text=message.text,
        )
    await message.reply_html(
        "Message received.\n\n"
        f"Current chat id: <code>{escape(str(chat.id))}</code>\n"
        "Send /help to see available commands."
    )


def build_application() -> Application:
    load_dotenv()
    token = required_env("TELEGRAM_BOT_TOKEN")
    db_path = os.getenv("SQLITE_DB_PATH", "bot.db")
    storage = Storage(db_path)

    application = Application.builder().token(token).build()
    application.bot_data["storage"] = storage
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", chat_id))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, record_message))
    return application


def main() -> None:
    application = build_application()
    logger.info("Starting Telegram bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
