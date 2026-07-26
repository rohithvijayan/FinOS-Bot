"""
FinOS Telegram Bot — main entry point.

Run with:
    python -m bot.main

Or from the project root:
    python bot/main.py
"""
from __future__ import annotations

import logging
import sys

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

import bot.config as config
from bot.config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS
from bot.handlers.balance import balance_command
from bot.handlers.spending import spending_command
from bot.handlers.portfolio import portfolio_command
from bot.handlers.expense import build_expense_conversation, undo_command
from bot.handlers.auth import allowed_only

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Static command handlers ───────────────────────────────────────────────────

from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Return persistent bottom menu keyboard."""
    kb = [
        [KeyboardButton("💳 Liquid Balance"),       KeyboardButton("📊 Monthly Spending")],
        [KeyboardButton("📈 Investment Portfolio"),  KeyboardButton("🌆 Daily Digest")],
    ]
    if config.ENABLE_COPILOT:
        kb.append([KeyboardButton("🤖 Copilot")])
    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True,
        is_persistent=True
    )


@allowed_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — welcome message."""
    from pathlib import Path
    assets_img = Path(__file__).parent / "Assets" / "StartMessageImage.webp"

    welcome_msg = (
        "*Welcome to FinOS Bot!* 🚀\n\n"
        "Your personal finance assistant — always in your pocket, ready to help you track and optimize your money.\n\n"
        "⚡️ *How to Log an Expense*\n"
        "I understand natural language! Just type it naturally:\n\n"
        "_\"spent 350 at Zomato\"_\n\n"
        "_\"uber 180\"_\n\n"
        "_\"groceries 1500 at DMart\"_\n\n"
        "🛠 *Quick Menu*\n"
        "Tap any button below to manage your finances:"
    )

    if assets_img.exists():
        with open(assets_img, "rb") as photo_file:
            await update.effective_message.reply_photo(
                photo=photo_file,
                caption=welcome_msg,
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard()
            )
    else:
        await update.effective_message.reply_text(
            welcome_msg,
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )


@allowed_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""
    help_msg = (
        "📖 *FinOS Bot — Commands*\n\n"
        "━━━━━ 💸 Expense Logging ━━━━━\n"
        "Just send any message with an amount:\n"
        "  `spent 350 at Zomato`\n"
        "  `uber 180`\n"
        "  `electricity bill 1200`\n\n"
        "━━━━━ 📋 Queries ━━━━━\n"
        "/balance — Liquid savings breakdown\n"
        "/spending — Current month category breakdown\n"
        "/portfolio — Investment overview\n"
        "/digest — Daily & Monthly digest\n\n"
    )
    if config.ENABLE_COPILOT:
        help_msg += (
            "━━━━━ 🤖 AI Copilot ━━━━━\n"
            "/copilot — Chat with your personal finance AI\n"
            "Ask anything: \"Am I on budget?\", \"Which SIP is performing best?\"\n\n"
        )
    help_msg += (
        "━━━━━ 🔧 Other ━━━━━\n"
        "/undo — Delete last logged expense\n"
        "/start — Welcome message\n"
        "/help — This message"
    )
    await update.effective_message.reply_text(
        help_msg,
        parse_mode="Markdown",
    )


# ── App setup ─────────────────────────────────────────────────────────────────

from datetime import time
from bot.handlers.digest import digest_command, scheduled_daily_digest_job, scheduled_monthly_digest_job


async def post_init(application: Application) -> None:
    """Set bot command list visible in Telegram UI and schedule push jobs."""
    commands = [
        BotCommand("start",    "Welcome & quick guide"),
        BotCommand("help",     "Full command reference"),
        BotCommand("balance",  "Liquid savings overview"),
        BotCommand("spending", "Monthly spending breakdown"),
        BotCommand("portfolio","Investment portfolio overview"),
        BotCommand("digest",   "Daily & Monthly Push Intelligence Digest"),
    ]
    if config.ENABLE_COPILOT:
        commands.append(BotCommand("copilot",  "Chat with your personal finance AI Copilot"))
    commands.append(BotCommand("undo",     "Delete last logged expense"))
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered.")

    # Schedule Automated Push Intelligence Jobs
    if application.job_queue:
        # Daily Push Digest at 21:00 (9:00 PM)
        application.job_queue.run_daily(
            scheduled_daily_digest_job,
            time=time(21, 0, 0),
            name="daily_push_digest"
        )
        # Monthly Executive Digest on 24th at 09:00 AM
        application.job_queue.run_monthly(
            scheduled_monthly_digest_job,
            when=time(9, 0, 0),
            day=24,
            name="monthly_push_digest"
        )
        logger.info("🚀 Push Intelligence Job Queue scheduled! (Daily: 21:00, Monthly: 24th 09:00)")

    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "⚠️  ALLOWED_CHAT_ID is not set in .env! "
            "The bot will prompt any user who messages it for their chat ID."
        )
    else:
        logger.info("Allowed chat IDs: %s", ALLOWED_CHAT_IDS)


def main() -> None:
    logger.info("Starting FinOS Bot…")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register the expense conversation (must be before catch-all handlers)
    app.add_handler(build_expense_conversation())

    from telegram.ext import CallbackQueryHandler
    from bot.handlers.spending import callback_open_month_picker, callback_select_spending_month

    # Static commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("spending", spending_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CommandHandler("undo", undo_command))

    from bot.handlers.copilot import (
        copilot_command, copilot_message,
        copilot_quick_prompt, copilot_refresh,
    )

    app.add_handler(CommandHandler("copilot", copilot_command))

    # Inline keyboard callbacks for Copilot quick prompts
    app.add_handler(CallbackQueryHandler(copilot_quick_prompt, pattern="^cop:(budget|portfolio|tips|networth)$"))
    app.add_handler(CallbackQueryHandler(copilot_refresh,      pattern="^cop:refresh$"))

    # PDF Bank Statement Importer Document Handler
    from telegram.ext import filters, MessageHandler
    from bot.handlers.expense import handle_pdf_document, callback_batch_save, callback_batch_cancel

    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_document))

    # Inline Keyboard Callbacks for Month Picker & Batch PDF Save
    app.add_handler(CallbackQueryHandler(callback_open_month_picker, pattern="^spend_pick:open$"))
    app.add_handler(CallbackQueryHandler(callback_select_spending_month, pattern="^spend_month:"))
    app.add_handler(CallbackQueryHandler(callback_batch_save, pattern="^batch:save$"))
    app.add_handler(CallbackQueryHandler(callback_batch_cancel, pattern="^batch:cancel$"))

    logger.info("Starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
