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


@allowed_only
async def spending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /spending command."""
    month_label = _parse_month_arg(context.args or [])
    await update.effective_message.reply_text(
        f"🔍 Fetching spending for *{month_label}*...", parse_mode="Markdown"
    )

    try:
        start_date, end_date = _billing_date_window(month_label)

        # Fetch ALL expenses in the wider date window using both possible date formats.
        # We can't do a DB-level date range filter because dates are stored as TEXT
        # in 'DD-MMM-YYYY' format which doesn't sort lexicographically.
        # Instead: fetch the two calendar months that overlap and filter in Python.
        all_res = supabase.table("expenses").select("*").execute()
        all_expenses = all_res.data or []

        # Filter in Python using the same getBillingMonth logic as the web app
        expenses = []
        for exp in all_expenses:
            d = _parse_expense_date(exp.get("date", ""))
            if d and start_date <= d <= end_date:
                expenses.append(exp)

        # Group expenses by category for HTML renderer
        by_cat: dict[str, float] = {}
        total_sp = 0.0
        for exp in expenses:
            amt = float(exp.get("amount", 0))
            cat = exp.get("category", "Others")
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
            total_sp += amt

        categories_list = [{"name": k, "amount": v} for k, v in by_cat.items()]

        from bot.utils.html_renderer import render_spending_card
        render_spending_card(
            month=month_label,
            total_spent=total_sp,
            categories=categories_list,
            monthly_budget=sum(budgets.values()) if budgets else 50000.0,
            date_range=f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"
        )

        msg = build_spending_message(month_label, expenses, budgets)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Failed to fetch spending: %s", exc)
        await update.effective_message.reply_text(
            "❌ Couldn't fetch spending data. Check bot logs."
        )
