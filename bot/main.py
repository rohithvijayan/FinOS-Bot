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

@allowed_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — welcome message."""
    await update.effective_message.reply_text(
        "👋 *Welcome to FinOS Bot!*\n\n"
        "Your personal finance assistant — always in your pocket.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💸 *Log an expense:*\n"
        "   Just type naturally:\n"
        "   _\"spent 350 at Zomato\"_\n"
        "   _\"uber 180\"_\n"
        "   _\"groceries 1500 at DMart\"_\n\n"
        "📊 *Commands:*\n"
        "   /balance    — Liquid savings overview\n"
        "   /spending   — This month's spending\n"
        "   /portfolio  — Investment overview\n"
        "   /undo       — Delete last expense\n"
        "   /help       — Full command list\n"
        "━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )


@allowed_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""
    await update.effective_message.reply_text(
        "📖 *FinOS Bot — Commands*\n\n"
        "━━━━━ 💸 Expense Logging ━━━━━\n"
        "Just send any message with an amount:\n"
        "  `spent 350 at Zomato`\n"
        "  `uber 180`\n"
        "  `electricity bill 1200`\n"
        "  `groceries 1500`\n\n"
        "The bot will:\n"
        "  1. Parse the amount & category\n"
        "  2. Show a preview card\n"
        "  3. Ask you to confirm before saving\n\n"
        "━━━━━ 📋 Queries ━━━━━\n"
        "/balance — Liquid savings breakdown\n"
        "/spending — Current month category breakdown\n"
        "/spending July 2026 — Specific month\n"
        "/portfolio — Full investment overview\n\n"
        "━━━━━ 🔧 Other ━━━━━\n"
        "/undo — Delete the last logged expense\n"
        "/start — Welcome message\n"
        "/help — This message",
        parse_mode="Markdown",
    )


# ── App setup ─────────────────────────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Set bot command list visible in Telegram UI."""
    commands = [
        BotCommand("start", "Welcome & quick guide"),
        BotCommand("help", "Full command reference"),
        BotCommand("balance", "Liquid savings overview"),
        BotCommand("spending", "Monthly spending breakdown"),
        BotCommand("portfolio", "Investment portfolio overview"),
        BotCommand("undo", "Delete last logged expense"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered.")

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

    # Static commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("spending", spending_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("undo", undo_command))

    logger.info("All handlers registered. Starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
