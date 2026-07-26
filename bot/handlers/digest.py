"""
Push Intelligence & Digest Reports Handler.

Provides:
- Daily Digest Report (Scheduled 9:00 PM daily + On demand)
- Monthly Executive Digest (Scheduled 24th of month + On demand)
- /digest command
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ALLOWED_CHAT_IDS
from bot.handlers.auth import allowed_only
from bot.supabase_client import supabase
from bot.handlers.spending import _billing_date_window, _parse_expense_date, _parse_month_arg
from bot.utils.html_renderer import render_digest_daily_card, render_digest_monthly_card
from bot.utils.formatters import fmt_inr

logger = logging.getLogger(__name__)


def _get_today_str() -> str:
    return date.today().strftime("%d-%b-%Y")


def fetch_daily_expenses() -> tuple[list[dict], float]:
    """Fetch expenses for today."""
    today_formatted = date.today().strftime("%Y-%m-%d")
    today_alt = date.today().strftime("%d-%b-%Y")
    
    res = supabase.table("expenses").select("*").execute()
    all_expenses = res.data or []
    
    today_list = []
    total_today = 0.0
    for exp in all_expenses:
        d_str = exp.get("date", "")
        cat = exp.get("category", "Others")
        if cat == "Investment":
            continue
        # Match today's date
        if d_str == today_formatted or d_str.lower() == today_alt.lower() or d_str == date.today().strftime("%d-%m-%Y"):
            amt = float(exp.get("amount", 0))
            today_list.append({
                "description": exp.get("description", "Expense"),
                "category": cat,
                "amount": amt
            })
            total_today += amt

    return today_list, total_today


def fetch_monthly_digest(month_label: str) -> tuple[float, list[dict], float, float]:
    """Fetch spending, categories, budget total, and liquid savings for monthly digest."""
    start_date, end_date = _billing_date_window(month_label)
    
    all_res = supabase.table("expenses").select("*").execute()
    all_expenses = all_res.data or []
    
    by_cat: dict[str, float] = {}
    total_spent = 0.0
    for exp in all_expenses:
        d = _parse_expense_date(exp.get("date", ""))
        cat = exp.get("category", "Others")
        if cat == "Investment":
            continue
        if d and start_date <= d <= end_date:
            amt = float(exp.get("amount", 0))
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
            total_spent += amt

    categories_list = sorted([{"name": k, "amount": v} for k, v in by_cat.items()], key=lambda x: x["amount"], reverse=True)

    # Budgets
    bud_res = supabase.table("budgets").select("*").execute()
    total_budget = sum(float(b.get("limit_amount", 0)) for b in (bud_res.data or [])) or 50000.0

    # Savings
    sav_res = supabase.table("savings").select("*").execute()
    total_liquid = sum(float(s.get("balance", 0)) for s in (sav_res.data or [])) or 1245000.0

    return total_spent, categories_list, total_budget, total_liquid


async def send_daily_digest_to_chat(bot, chat_id: int) -> None:
    """Render and send Daily Digest to a chat."""
    today_str = date.today().strftime("%d %b %Y")
    expenses, total_today = fetch_daily_expenses()
    
    _, img_path = render_digest_daily_card(
        date=today_str,
        total_today=total_today,
        expenses=expenses,
        daily_target=1600.0
    )
    
    caption = (
        f"🌆 *FinOS Daily Digest — {today_str}*\n\n"
        f"• *Total Spent Today:* ₹{total_today:,.2f}\n"
        f"• *Transactions:* {len(expenses)}\n\n"
        f"_{'No expenses logged today! 🎉' if not expenses else 'Logged into Supabase & FinOS Dashboard.'}_"
    )

    if img_path and img_path.exists():
        with open(img_path, "rb") as photo:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")


async def send_monthly_digest_to_chat(bot, chat_id: int, month_label: str = None) -> None:
    """Render and send Monthly Executive Digest to a chat."""
    if not month_label:
        today = date.today()
        _MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        month_label = f"{_MONTHS[today.month - 1]} {today.year}"

    start_date, end_date = _billing_date_window(month_label)
    date_range = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"

    total_spent, categories, total_budget, total_liquid = fetch_monthly_digest(month_label)

    _, img_path = render_digest_monthly_card(
        month=month_label,
        total_spent=total_spent,
        categories=categories,
        monthly_budget=total_budget,
        total_liquid=total_liquid,
        date_range=date_range
    )

    caption = (
        f"📊 *FinOS Monthly Executive Digest — {month_label}*\n"
        f"🗓 _Cycle: {date_range}_\n\n"
        f"• *Total Spent:* ₹{total_spent:,.2f} / ₹{total_budget:,.0f} Budget\n"
        f"• *Budget Used:* {((total_spent/total_budget)*100):.1f}%\n"
        f"• *Liquid Reserves:* ₹{total_liquid:,.0f}\n"
    )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    change_month_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗓 Select Billing Month", callback_data="spend_pick:open")]
    ])

    if img_path and img_path.exists():
        with open(img_path, "rb") as photo:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown", reply_markup=change_month_btn)
    else:
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_markup=change_month_btn)


# ── Scheduled Job Queue Callbacks ──────────────────────────────────────────

async def scheduled_daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback for 9:00 PM daily digest."""
    logger.info("Executing scheduled Daily Digest Push...")
    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await send_daily_digest_to_chat(context.bot, chat_id)
        except Exception as exc:
            logger.exception("Failed to send daily digest to chat %s: %s", chat_id, exc)


async def scheduled_monthly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback for monthly executive digest."""
    logger.info("Executing scheduled Monthly Executive Digest Push...")
    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await send_monthly_digest_to_chat(context.bot, chat_id)
        except Exception as exc:
            logger.exception("Failed to send monthly digest to chat %s: %s", chat_id, exc)


# ── /digest Command Handler ───────────────────────────────────────────────

@allowed_only
async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """On-demand /digest command. Usage: /digest [daily|monthly]."""
    args = context.args or []
    subcommand = args[0].lower() if args else "daily"

    if subcommand == "monthly":
        await update.effective_message.reply_text("📊 Generating Monthly Executive Digest...")
        await send_monthly_digest_to_chat(context.bot, update.effective_chat.id)
    else:
        await update.effective_message.reply_text("🌆 Generating Daily Intelligence Digest...")
        await send_daily_digest_to_chat(context.bot, update.effective_chat.id)
