"""
Balance handler — /balance command.

Queries the `savings` table and returns a formatted summary of all
liquid accounts with their balances and interest rates.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.auth import allowed_only
from bot.supabase_client import supabase
from bot.utils.formatters import build_balance_message, fmt_inr

logger = logging.getLogger(__name__)


@allowed_only
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance command."""
    await update.effective_message.reply_text("🔍 Fetching your balances...")

    try:
        res = supabase.table("savings").select("*").execute()
        accounts = res.data or []

        # Normalise column names (DB uses snake_case, camelCase on web)
        normalised = [
            {
                "name": a.get("name", "Unknown"),
                "bank_name": a.get("bank_name", ""),
                "balance": float(a.get("balance", 0)),
                "interest_rate": float(a.get("interest_rate", 0)),
            }
            for a in accounts
        ]

        msg = build_balance_message(normalised)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Failed to fetch balance: %s", exc)
        await update.effective_message.reply_text(
            "❌ Couldn't fetch your balance. Check bot logs for details."
        )
