"""
Expense handler — natural language expense logging + /undo.

Flow:
  1. User sends a text message (not a command).
  2. Bot checks if it looks like an expense (has an amount).
  3. Calls Gemini to parse → builds a preview card.
  4. Presents inline keyboard: [✅ Save] [✏️ Edit category] [❌ Cancel]
  5. On ✅ → inserts into Supabase `expenses` table.
  6. On ✏️ → shows category selector buttons.
  7. On ❌ → cancels silently.
  8. /undo → deletes the last expense logged in this session.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from bot.handlers.auth import allowed_only
from bot.gemini_client import parse_expense
from bot.supabase_client import supabase
from bot.utils.categories import UI_CATEGORIES, CATEGORY_ICONS
from bot.utils.formatters import build_expense_preview, fmt_inr
from bot.utils.html_renderer import render_expense_card

logger = logging.getLogger(__name__)

# ConversationHandler states
AWAITING_CONFIRM = 1
AWAITING_CATEGORY = 2

# Context keys
_PENDING_KEY = "pending_expense"
_LAST_ID_KEY = "last_expense_id"

# Regex to detect if a message likely contains an amount
_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)?\b\d[\d,]*(?:\.\d{1,2})?\b",
    re.IGNORECASE,
)


def _looks_like_expense(text: str) -> bool:
    """Heuristic: message has at least one number and is not a command."""
    return bool(_AMOUNT_RE.search(text)) and not text.startswith("/")


def _get_billing_month(date_str: str) -> str:
    """Convert YYYY-MM-DD to billing month label (flips on 25th)."""
    _MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    try:
        parts = date_str.split("-")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        if day >= 25:
            month += 1
            if month > 12:
                month = 1
                year += 1
        return f"{_MONTHS[month - 1]} {year}"
    except Exception:
        today = date.today()
        return f"{_MONTHS[today.month - 1]} {today.year}"


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Save", callback_data="expense:save"),
            InlineKeyboardButton("✏️ Change Category", callback_data="expense:edit_cat"),
            InlineKeyboardButton("❌ Cancel", callback_data="expense:cancel"),
        ]
    ])


def _category_keyboard() -> InlineKeyboardMarkup:
    """Show all categories as 2-column button grid."""
    buttons = []
    cats = [c for c in UI_CATEGORIES]  # exclude 'Others' — added at end
    for i in range(0, len(cats), 2):
        row = []
        for cat in cats[i:i + 2]:
            icon = CATEGORY_ICONS.get(cat, "🏷️")
            row.append(InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat:{cat}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Entry point: plain text message ─────────────────────────────────────────

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered for all non-command text messages."""
    # Auth check inline (decorator can't be used on ConversationHandler entry points directly)
    from bot.config import ALLOWED_CHAT_IDS
    chat_id = update.effective_chat.id

    if not ALLOWED_CHAT_IDS:
        await update.effective_message.reply_text(
            f"⚠️ *Auth not configured!*\n\nAdd `ALLOWED_CHAT_ID={chat_id}` to your `.env` and restart.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if chat_id not in ALLOWED_CHAT_IDS:
        return ConversationHandler.END

    text = (update.effective_message.text or "").strip()

    # Route menu button clicks
    if text == "💳 Liquid Balance":
        from bot.handlers.balance import balance_command
        await balance_command(update, context)
        return ConversationHandler.END

    if text == "📊 Monthly Spending":
        from bot.handlers.spending import spending_command
        await spending_command(update, context)
        return ConversationHandler.END

    if text == "📈 Investment Portfolio":
        from bot.handlers.portfolio import portfolio_command
        await portfolio_command(update, context)
        return ConversationHandler.END

    if text == "🌆 Daily Digest":
        from bot.handlers.digest import digest_command
        await digest_command(update, context)
        return ConversationHandler.END

    if not _looks_like_expense(text):
        await update.effective_message.reply_text(
            "💬 I didn't detect an expense in that message.\n\n"
            "Try: _\"spent 350 at Zomato\"_ or tap the menu buttons below.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    thinking_msg = await update.effective_message.reply_text("🧠 Parsing your expense...")

    parsed = await parse_expense(text)

    if "error" in parsed:
        await thinking_msg.edit_text(
            "❓ I couldn't find an amount in your message. Try: `spent 350 at Zomato`",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Store pending expense in user context
    context.user_data[_PENDING_KEY] = parsed

    # Render HTML preview card & convert to PNG image
    _, img_path = render_expense_card(
        amount=parsed["amount"],
        category=parsed["category"],
        merchant=parsed["description"],
        billing_month=_get_billing_month(parsed["date"]),
        date=parsed["date"],
        is_confirmed=False
    )

    preview = build_expense_preview(
        amount=parsed["amount"],
        description=parsed["description"],
        category=parsed["category"],
        date=parsed["date"],
    )

    confidence_note = ""
    if parsed.get("confidence", 1.0) < 0.75:
        confidence_note = "\n\n_⚠️ Low confidence — please verify the category._"

    await thinking_msg.delete()

    if img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await update.effective_message.reply_photo(
                photo=photo_file,
                caption=f"⚡ *Expense Detected*\n{preview}{confidence_note}",
                parse_mode="Markdown",
                reply_markup=_confirm_keyboard(),
            )
    else:
        await update.effective_message.reply_text(
            preview + confidence_note,
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(),
        )
    return AWAITING_CONFIRM


# ── Callback: Save ───────────────────────────────────────────────────────────

async def callback_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed ✅ Save."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get(_PENDING_KEY)
    if not pending:
        await query.edit_message_text("⚠️ Expense data lost. Please try again.")
        return ConversationHandler.END

    month_label = _get_billing_month(pending["date"])

    row = {
        "date": pending["date"],
        "description": pending["description"],
        "amount": pending["amount"],
        "category": pending["category"],
        "month": month_label,
    }

    try:
        res = supabase.table("expenses").insert(row).execute()
        inserted = res.data[0] if res.data else {}
        expense_id = inserted.get("id")
        context.user_data[_LAST_ID_KEY] = expense_id

        await query.edit_message_text(
            f"✅ *Saved!*\n\n"
            f"{fmt_inr(pending['amount'])} · {pending['category']} · {pending['description']}\n\n"
            f"_Use /undo to delete this if you made a mistake._",
            parse_mode="Markdown",
        )

        # Trigger Smart Budget Alerts & Threshold Guards (75% / 90%)
        from bot.utils.budget_guard import check_category_budget_guard
        await check_category_budget_guard(
            category=pending["category"],
            billing_month=month_label,
            context=context,
            bot=context.bot,
            chat_id=update.effective_chat.id
        )
    except Exception as exc:
        logger.exception("Failed to insert expense: %s", exc)
        await query.edit_message_text("❌ Failed to save. Check bot logs.")

    context.user_data.pop(_PENDING_KEY, None)
    return ConversationHandler.END


# ── Callback: Cancel ─────────────────────────────────────────────────────────

async def callback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed ❌ Cancel."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Expense cancelled.")
    context.user_data.pop(_PENDING_KEY, None)
    return ConversationHandler.END


# ── Callback: Edit Category ──────────────────────────────────────────────────

async def callback_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed ✏️ Change Category — show category picker."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📂 *Choose a category:*",
        parse_mode="Markdown",
        reply_markup=_category_keyboard(),
    )
    return AWAITING_CATEGORY


async def callback_set_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User selected a category from the grid."""
    query = update.callback_query
    await query.answer()

    chosen = query.data.split(":", 1)[1]  # e.g. "cat:Eating Out" → "Eating Out"
    pending = context.user_data.get(_PENDING_KEY)

    if not pending:
        await query.edit_message_text("⚠️ Session expired. Please re-enter the expense.")
        return ConversationHandler.END

    pending["category"] = chosen
    context.user_data[_PENDING_KEY] = pending

    preview = build_expense_preview(
        amount=pending["amount"],
        description=pending["description"],
        category=chosen,
        date=pending["date"],
    )

    await query.edit_message_text(
        preview,
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(),
    )
    return AWAITING_CONFIRM


# ── /undo command ─────────────────────────────────────────────────────────────

@allowed_only
async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the last expense inserted in this session."""
    last_id = context.user_data.get(_LAST_ID_KEY)

    if not last_id:
        await update.effective_message.reply_text(
            "⚠️ Nothing to undo — no expense logged in this session yet."
        )
        return

    try:
        supabase.table("expenses").delete().eq("id", last_id).execute()
        context.user_data.pop(_LAST_ID_KEY, None)
        await update.effective_message.reply_text("↩️ *Last expense deleted.*", parse_mode="Markdown")
    except Exception as exc:
        logger.exception("Failed to undo expense %s: %s", last_id, exc)
        await update.effective_message.reply_text("❌ Couldn't delete. Check bot logs.")


# ── ConversationHandler factory ───────────────────────────────────────────────

def build_expense_conversation() -> ConversationHandler:
    """Build and return the ConversationHandler for expense logging."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
        ],
        states={
            AWAITING_CONFIRM: [
                CallbackQueryHandler(callback_save, pattern="^expense:save$"),
                CallbackQueryHandler(callback_edit_category, pattern="^expense:edit_cat$"),
                CallbackQueryHandler(callback_cancel, pattern="^expense:cancel$"),
            ],
            AWAITING_CATEGORY: [
                CallbackQueryHandler(callback_set_category, pattern="^cat:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: (
                u.effective_message.reply_text("❌ Cancelled."),
                ConversationHandler.END,
            )),
        ],
        per_user=True,
        per_chat=True,
    )
