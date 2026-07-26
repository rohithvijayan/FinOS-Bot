"""
Smart Budget Alerts & Threshold Guards.

Evaluates category spending against Supabase budget caps whenever an expense is saved.
Triggers high-impact visual PNG alert photo cards for:
- 75% Warning Guard (⚠️ Gold Alert)
- 90% Critical Guard (🚨 Coral Red Alert)
"""
from __future__ import annotations

import logging
from typing import Any
from bot.supabase_client import supabase
from bot.handlers.spending import _billing_date_window, _parse_expense_date
from bot.utils.html_renderer import render_budget_alert_card

logger = logging.getLogger(__name__)


async def check_category_budget_guard(
    category: str,
    billing_month: str,
    context: Any,
    bot: Any,
    chat_id: int
) -> bool:
    """
    Evaluates category spending for the current billing cycle against Supabase budget limits.
    Pushes an alert photo card if 75% or 90% threshold is crossed for the first time in this cycle.
    Returns True if an alert was triggered, False otherwise.
    """
    if category == "Investment":
        return False

    try:
        # 1. Fetch budget limit for this category
        bud_res = supabase.table("budgets").select("*").eq("category", category).execute()
        if not bud_res.data:
            # Fallback: check general categories limit
            return False

        limit_amount = float(bud_res.data[0].get("limit_amount", 0))
        if limit_amount <= 0:
            return False

        # 2. Fetch total spent for this category in the current billing cycle
        start_date, end_date = _billing_date_window(billing_month)
        all_res = supabase.table("expenses").select("*").eq("category", category).execute()
        all_exp = all_res.data or []

        category_spent = 0.0
        for exp in all_exp:
            d = _parse_expense_date(exp.get("date", ""))
            if d and start_date <= d <= end_date:
                category_spent += float(exp.get("amount", 0))

        if category_spent <= 0:
            return False

        pct_used = (category_spent / limit_amount) * 100.0

        # 3. Check alert tracking cache (stored in bot_data or dictionary)
        bot_data = getattr(context, "bot_data", {}) if context else {}
        triggered = bot_data.setdefault("triggered_alerts", set())

        key_75 = f"{billing_month}:{category}:75"
        key_90 = f"{billing_month}:{category}:90"

        threshold_to_trigger = None
        if pct_used >= 90.0 and key_90 not in triggered:
            threshold_to_trigger = 90
            triggered.add(key_90)
            triggered.add(key_75)  # Suppress lower threshold if jumped straight to 90%
        elif pct_used >= 75.0 and key_75 not in triggered:
            threshold_to_trigger = 75
            triggered.add(key_75)

        if not threshold_to_trigger:
            return False

        logger.info(
            "🚨 Budget Guard Triggered! Category=%s, Spent=%.2f, Limit=%.2f, Pct=%.1f%%, Level=%d",
            category, category_spent, limit_amount, pct_used, threshold_to_trigger
        )

        # 4. Render alert card image
        _, img_path = render_budget_alert_card(
            category=category,
            amount_spent=category_spent,
            limit_amount=limit_amount,
            threshold_level=threshold_to_trigger,
            billing_month=billing_month
        )

        remaining = limit_amount - category_spent
        if threshold_to_trigger == 90:
            caption = (
                f"🚨 *BUDGET CRITICAL GUARD — {category.upper()}*\n"
                f"⚠️ Spending has reached *{pct_used:.1f}%* of your monthly budget limit!\n\n"
                f"• *Spent:* ₹{category_spent:,.2f} / ₹{limit_amount:,.0f}\n"
                f"• *Buffer Remaining:* ₹{remaining:,.2f}"
            )
        else:
            caption = (
                f"⚠️ *BUDGET WARNING GUARD — {category.upper()}*\n"
                f"Notice: You have used *{pct_used:.1f}%* of your monthly category limit.\n\n"
                f"• *Spent:* ₹{category_spent:,.2f} / ₹{limit_amount:,.0f}\n"
                f"• *Buffer Remaining:* ₹{remaining:,.2f}"
            )

        if img_path and img_path.exists():
            with open(img_path, "rb") as photo:
                await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")

        return True

    except Exception as exc:
        logger.exception("Error checking budget guard for %s: %s", category, exc)
        return False
