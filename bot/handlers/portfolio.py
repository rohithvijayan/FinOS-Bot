"""
Portfolio handler — /portfolio command.

Fetches portfolio_summary, sips, and bonds tables and returns a
formatted investment overview.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.auth import allowed_only
from bot.supabase_client import supabase
from bot.utils.formatters import build_portfolio_message

logger = logging.getLogger(__name__)


@allowed_only
async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /portfolio command."""
    await update.effective_message.reply_text("📊 Fetching your portfolio...")

    try:
        # Portfolio summary (single row with id=1)
        ps_res = supabase.table("portfolio_summary").select("*").eq("id", 1).execute()
        summary_row = ps_res.data[0] if ps_res.data else {}
        summary = {
            "total_invested": float(summary_row.get("total_invested", 0)),
            "current_value": float(summary_row.get("current_value", 0)),
            "total_gain": float(summary_row.get("total_gain", 0)),
            "return_pct": float(summary_row.get("return_pct", 0)),
            "monthly_sip": float(summary_row.get("monthly_sip", 0)),
        } if summary_row else {}

        # SIPs
        sip_res = supabase.table("sips").select("*").execute()
        sips = [
            {
                "name": s.get("name", "Unknown"),
                "active": s.get("active", "No"),
                "invested": float(s.get("invested", 0)),
                "current_value": float(s.get("current_value", 0)),
                "gain_loss": float(s.get("gain_loss", 0)),
                "return_pct": s.get("return_pct", "0%"),
                "monthly_sip": float(s.get("monthly_sip", 0)),
            }
            for s in (sip_res.data or [])
        ]

        # Bonds
        bond_res = supabase.table("bonds").select("*").execute()
        bonds = [
            {
                "name": b.get("name", "Unknown"),
                "invested": float(b.get("invested", 0)),
                "current_value": float(b.get("current_value", 0)),
                "gain_loss": float(b.get("gain_loss", 0)),
                "ytm": b.get("ytm", ""),
                "status": b.get("status", ""),
            }
            for b in (bond_res.data or [])
        ]

        msg = build_portfolio_message(summary, sips, bonds)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Failed to fetch portfolio: %s", exc)
        await update.effective_message.reply_text(
            "❌ Couldn't fetch portfolio data. Check bot logs."
        )
