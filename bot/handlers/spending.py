"""
Spending handler — /spending [Month Year] command.

Usage:
  /spending           → current billing month
  /spending July 2026 → specific month
  /spending July      → current year assumed

Queries `expenses` and `budgets` tables.

NOTE: We do NOT filter by the stored `month` TEXT column because it can be stale
(e.g. expenses entered on the 25th may have the wrong billing month stored).
Instead we fetch the relevant date window and recompute billing month in Python,
exactly matching the web app's getBillingMonth() logic in FinanceContext.tsx.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.auth import allowed_only
from bot.supabase_client import supabase
from bot.utils.formatters import build_spending_message

logger = logging.getLogger(__name__)

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Short month names used in the 'DD-MMM-YYYY' date format stored by the web app
_SHORT_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _current_billing_month() -> str:
    """
    Return the current billing month label (e.g. 'July 2026').
    Billing month flips on the 25th (matching FinanceContext.tsx logic).
    """
    today = date.today()
    day = today.day
    month = today.month
    year = today.year
    if day >= 25:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return f"{_MONTHS[month - 1]} {year}"


def _parse_month_arg(args: list[str]) -> str:
    """Parse optional month/year args from the command, e.g. ['July', '2026']."""
    if not args:
        return _current_billing_month()

    text = " ".join(args).strip().title()
    for month_name in _MONTHS:
        if text.startswith(month_name):
            remainder = text[len(month_name):].strip()
            year = int(remainder) if remainder.isdigit() else date.today().year
            return f"{month_name} {year}"

    return _current_billing_month()


def _parse_expense_date(date_str: str) -> date | None:
    """
    Parse an expense date stored as text.
    Handles both 'DD-MMM-YYYY' (e.g. '25-Jul-2026') and 'YYYY-MM-DD' formats.
    """
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _get_billing_month(expense_date: date) -> str:
    """
    Compute the billing month for a given date.
    Mirrors getBillingMonth() in FinanceContext.tsx exactly:
      - day >= 25 → bumps to next month
    """
    month = expense_date.month
    year = expense_date.year
    if expense_date.day >= 25:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return f"{_MONTHS[month - 1]} {year}"


def _billing_date_window(month_label: str) -> tuple[date, date]:
    """
    Return the (start_date, end_date) for a billing month label.
    Billing window: 25th of the previous calendar month → 24th of this month.
    """
    month_name, year_str = month_label.split()
    month_idx = _MONTHS.index(month_name) + 1  # 1-based
    year = int(year_str)

    # Start: 25th of previous calendar month
    prev_month = month_idx - 1 or 12
    prev_year = year if month_idx > 1 else year - 1
    start = date(prev_year, prev_month, 25)

    # End: 24th of this calendar month
    end = date(year, month_idx, 24)
    return start, end


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler


def get_available_months_list() -> list[str]:
    """Fetch all unique billing months present in Supabase plus current & previous months."""
    months_set = {_current_billing_month()}
    try:
        res = supabase.table("expenses").select("date").execute()
        from bot.handlers.expense import _get_billing_month
        for row in (res.data or []):
            d = row.get("date")
            if d:
                months_set.add(_get_billing_month(d))
    except Exception as exc:
        logger.warning(f"Could not fetch months list from Supabase: {exc}")
    
    # Sort months chronologically descending
    def _month_sort_key(m_str: str):
        try:
            parts = m_str.split()
            return (int(parts[1]), _MONTHS.index(parts[0]) + 1)
        except Exception:
            return (2000, 1)

    return sorted(list(months_set), key=_month_sort_key, reverse=True)


def build_month_picker_keyboard(prefix: str = "spend_month") -> InlineKeyboardMarkup:
    """Build a 2-column grid inline keyboard of available billing months."""
    months = get_available_months_list()
    buttons = []
    for i in range(0, len(months), 2):
        row = []
        for m in months[i:i + 2]:
            row.append(InlineKeyboardButton(f"🗓 {m}", callback_data=f"{prefix}:{m}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def send_spending_report_for_month(update_or_query: Any, month_label: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Core logic to fetch, render, and reply with spending report for a specific billing month."""
    start_date, end_date = _billing_date_window(month_label)

    all_res = supabase.table("expenses").select("*").execute()
    all_expenses = all_res.data or []

    # Filter in Python using getBillingMonth logic and exclude 'Investment' category like web dashboard
    expenses = []
    for exp in all_expenses:
        d = _parse_expense_date(exp.get("date", ""))
        if d and start_date <= d <= end_date and exp.get("category") != "Investment":
            expenses.append(exp)

    # Group expenses by category for HTML renderer
    by_cat: dict[str, float] = {}
    total_sp = 0.0
    for exp in expenses:
        amt = float(exp.get("amount", 0))
        cat = exp.get("category", "Others")
        by_cat[cat] = by_cat.get(cat, 0.0) + amt
        total_sp += amt

    categories_list = sorted([{"name": k, "amount": v} for k, v in by_cat.items()], key=lambda x: x["amount"], reverse=True)

    # Fetch all budgets for comparison
    bud_res = supabase.table("budgets").select("*").execute()
    budgets: dict[str, float] = {
        b["category"]: float(b.get("limit_amount", 0))
        for b in (bud_res.data or [])
    }

    from bot.utils.html_renderer import render_spending_card
    _, img_path = render_spending_card(
        month=month_label,
        total_spent=total_sp,
        categories=categories_list,
        monthly_budget=sum(budgets.values()) if budgets else 50000.0,
        date_range=f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"
    )

    msg = build_spending_message(month_label, expenses, budgets)
    change_month_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗓 Select Billing Month", callback_data="spend_pick:open")]
    ])

    msg_target = getattr(update_or_query, "effective_message", None) or getattr(update_or_query, "message", None)

    if img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await msg_target.reply_photo(
                photo=photo_file,
                caption=f"📊 *Spending Overview — {month_label}*\n🗓 _Cycle: {start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}_",
                parse_mode="Markdown",
                reply_markup=change_month_btn
            )
    else:
        await msg_target.reply_text(msg, parse_mode="Markdown", reply_markup=change_month_btn)


@allowed_only
async def spending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /spending command.
    If no month argument is provided, prompts the user to select a billing cycle first.
    If a month argument is provided (e.g. /spending July 2026), directly renders that month.
    """
    args = context.args or []
    if not args:
        # Prompt user to select billing cycle FIRST before generating template
        kb = build_month_picker_keyboard(prefix="spend_month")
        await update.effective_message.reply_text(
            "📂 *Select a Billing Cycle / Month to view spending summary:*",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    month_label = _parse_month_arg(args)
    await update.effective_message.reply_text(
        f"🔍 Fetching spending for *{month_label}*...", parse_mode="Markdown"
    )

    try:
        await send_spending_report_for_month(update, month_label, context)
    except Exception as exc:
        logger.exception("Failed to fetch spending: %s", exc)
        await update.effective_message.reply_text(
            "❌ Couldn't fetch spending data. Check bot logs."
        )


async def callback_open_month_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback when user taps '🗓 Select Billing Month' button."""
    query = update.callback_query
    await query.answer()
    kb = build_month_picker_keyboard(prefix="spend_month")
    await query.message.reply_text(
        "📂 *Choose a Billing Month:*",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def callback_select_spending_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback when user taps a specific month button, e.g. spend_month:July 2026."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    selected_month = data.split(":", 1)[1] if ":" in data else _current_billing_month()
    
    thinking = await query.message.reply_text(
        f"🧠 Generating spending template card for *{selected_month}*...", parse_mode="Markdown"
    )
    try:
        await send_spending_report_for_month(query, selected_month, context)
        await thinking.delete()
    except Exception as exc:
        logger.exception("Failed to render spending report for %s: %s", selected_month, exc)
        await thinking.edit_text("❌ Couldn't generate spending template for this month.")
