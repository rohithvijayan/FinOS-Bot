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

        tot_val = summary.get("current_value", 0) or sum(s.get("current_value", 0) for s in sips) + sum(b.get("current_value", 0) for b in bonds)
        sip_tot = summary.get("monthly_sip", 0) or sum(s.get("monthly_sip", 0) for s in sips if s.get("active") == "Yes")
        asset_alloc = [
            {"name": "Mutual Funds & SIPs", "amount": sum(s.get("current_value", 0) for s in sips), "pct": round(sum(s.get("current_value", 0) for s in sips) / tot_val * 100, 1) if tot_val > 0 else 0},
            {"name": "Bonds & Debt", "amount": sum(b.get("current_value", 0) for b in bonds), "pct": round(sum(b.get("current_value", 0) for b in bonds) / tot_val * 100, 1) if tot_val > 0 else 0}
        ]
        # Full SIP rows for table (name | invested | current_value | return_pct | monthly_sip)
        sip_rows = [
            {
                "name":          s.get("name", "SIP"),
                "invested":      s.get("invested", 0),
                "current_value": s.get("current_value", 0),
                "return_pct":    s.get("return_pct", "0%"),
                "monthly_sip":   s.get("monthly_sip", 0),
                "amount":        s.get("amount", s.get("monthly_sip", 0)),
            }
            for s in sips
        ]
        # Full bond rows for table (name | invested | current_value | ytm)
        bond_rows = [
            {
                "name":          b.get("name", "Bond"),
                "invested":      b.get("invested", 0),
                "current_value": b.get("current_value", 0),
                "ytm":           b.get("ytm", ""),
            }
            for b in bonds
        ]

        growth_pct_rounded = round(float(summary.get("return_pct", 0) or 0), 2)

        from bot.utils.html_renderer import render_portfolio_card
        _, img_path = render_portfolio_card(
            total_portfolio=tot_val,
            asset_allocation=asset_alloc,
            sips=sip_rows,
            bonds=bond_rows,
            growth_pct=str(growth_pct_rounded),
            total_sip_amount=sip_tot
        )

        msg = build_portfolio_message(summary, sips, bonds)
        if img_path and img_path.exists():
            with open(img_path, "rb") as photo_file:
                await update.effective_message.reply_photo(
                    photo=photo_file,
                    caption="📈 *Net Worth & Investment Portfolio*",
                    parse_mode="Markdown"
                )
        else:
            await update.effective_message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Failed to fetch portfolio: %s", exc)
        await update.effective_message.reply_text(
            "❌ Couldn't fetch portfolio data. Check bot logs."
        )
