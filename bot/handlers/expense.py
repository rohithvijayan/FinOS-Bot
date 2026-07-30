"""
Expense handler — natural language expense logging + /undo.

Flow:
  1. User sends a text message (not a command).
  2. Bot checks if it looks like an expense (has an amount).
  3. Calls Gemini to parse → builds a preview card.
  4. Auto-saves to Supabase `expenses` table immediately!
  5. Presents inline keyboard: [✏️ Change Category] [❌ Undo]
  6. On ✏️ → shows category selector buttons.
  7. On ❌ → deletes the expense from Supabase.
  8. /undo → deletes the last expense logged.
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
    MessageHandler,
    CommandHandler,
    filters,
)

from bot.handlers.auth import allowed_only
from bot.config import ENABLE_COPILOT
from bot.gemini_client import parse_expense
from bot.supabase_client import supabase
from bot.utils.categories import UI_CATEGORIES, CATEGORY_ICONS
from bot.utils.formatters import build_expense_preview, fmt_inr
from bot.utils.html_renderer import render_expense_card

logger = logging.getLogger(__name__)

# Context keys
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


def _confirm_keyboard(expense_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Change Category", callback_data=f"exp:edit:{expense_id}"),
            InlineKeyboardButton("❌ Undo", callback_data=f"exp:undo:{expense_id}"),
        ]
    ])


def _category_keyboard(expense_id: str) -> InlineKeyboardMarkup:
    """Show all categories as 2-column button grid."""
    buttons = []
    cats = [c for c in UI_CATEGORIES]  # exclude 'Others' — added at end
    for i in range(0, len(cats), 2):
        row = []
        for cat in cats[i:i + 2]:
            icon = CATEGORY_ICONS.get(cat, "🏷️")
            row.append(InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat:{expense_id}:{cat}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Entry point: plain text message ─────────────────────────────────────────

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered for all non-command text messages."""
    # Auth check inline
    from bot.config import ALLOWED_CHAT_IDS
    chat_id = update.effective_chat.id

    if not ALLOWED_CHAT_IDS:
        await update.effective_message.reply_text(
            f"⚠️ *Auth not configured!*\n\nAdd `ALLOWED_CHAT_ID={chat_id}` to your `.env` and restart.",
            parse_mode="Markdown",
        )
        return

    if chat_id not in ALLOWED_CHAT_IDS:
        return

    text = (update.effective_message.text or "").strip()

    # Route menu button clicks
    if text == "💳 Liquid Balance":
        from bot.handlers.balance import balance_command
        await balance_command(update, context)
        return

    if text == "📊 Monthly Spending":
        from bot.handlers.spending import spending_command
        await spending_command(update, context)
        return

    if text == "📈 Investment Portfolio":
        from bot.handlers.portfolio import portfolio_command
        await portfolio_command(update, context)
        return

    if text == "🌆 Daily Digest":
        from bot.handlers.digest import digest_command
        await digest_command(update, context)
        return

    if text == "🤖 Copilot":
        if not ENABLE_COPILOT:
            await update.effective_message.reply_text("⚠️ The AI Copilot feature is currently disabled.")
            return
        from bot.handlers.copilot import copilot_command
        await copilot_command(update, context)
        return

    # If Copilot session is active, route all non-expense text to the AI
    if ENABLE_COPILOT and context.user_data.get("_copilot_system"):
        from bot.handlers.copilot import copilot_message
        await copilot_message(update, context)
        return

    if not _looks_like_expense(text):
        fallback = "💬 I didn't detect an expense in that message.\n\nTry: _\"spent 350 at Zomato\"_"
        if ENABLE_COPILOT:
            fallback += " or tap *🤖 Copilot* to chat with your finance AI."
        await update.effective_message.reply_text(
            fallback,
            parse_mode="Markdown",
        )
        return

    thinking_msg = await update.effective_message.reply_text("🧠 Parsing your expense...")

    parsed = await parse_expense(text)

    if "error" in parsed:
        await thinking_msg.edit_text(
            "❓ I couldn't find an amount in your message. Try: `spent 350 at Zomato`",
            parse_mode="Markdown",
        )
        return

    month_label = _get_billing_month(parsed["date"])
    row = {
        "date": parsed["date"],
        "description": parsed["description"],
        "amount": parsed["amount"],
        "category": parsed["category"],
        "month": month_label,
    }

    try:
        res = supabase.table("expenses").insert(row).execute()
        inserted = res.data[0] if res.data else {}
        expense_id = inserted.get("id")
        context.user_data[_LAST_ID_KEY] = expense_id
    except Exception as exc:
        logger.exception("Failed to insert expense: %s", exc)
        await thinking_msg.edit_text("❌ Failed to save expense. Check bot logs.")
        return

    # Render HTML preview card & convert to PNG image
    _, img_path = render_expense_card(
        amount=parsed["amount"],
        category=parsed["category"],
        merchant=parsed["description"],
        billing_month=month_label,
        date=parsed["date"],
        is_confirmed=True
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

    reply_markup = _confirm_keyboard(expense_id)

    if img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await update.effective_message.reply_photo(
                photo=photo_file,
                caption=f"✅ *Auto-Saved*\n{preview}{confidence_note}",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
    else:
        await update.effective_message.reply_text(
            f"✅ *Auto-Saved*\n{preview}{confidence_note}",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    # Trigger Smart Budget Alerts & Threshold Guards
    from bot.utils.budget_guard import check_category_budget_guard
    await check_category_budget_guard(
        category=parsed["category"],
        billing_month=month_label,
        context=context,
        bot=context.bot,
        chat_id=update.effective_chat.id
    )


# ── Callback: Undo ───────────────────────────────────────────────────────────

async def callback_undo_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed ❌ Undo."""
    query = update.callback_query
    await query.answer()
    
    expense_id = query.data.split(":")[2]
    
    try:
        supabase.table("expenses").delete().eq("id", expense_id).execute()
        await query.edit_message_caption(
            caption="❌ *Expense deleted.*",
            parse_mode="Markdown",
        )
    except Exception as exc:
        # If it's a text message without photo
        try:
            await query.edit_message_text(
                "❌ *Expense deleted.*",
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ── Callback: Edit Category ──────────────────────────────────────────────────

async def callback_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed ✏️ Change Category — show category picker."""
    query = update.callback_query
    await query.answer()
    
    expense_id = query.data.split(":")[2]
    
    try:
        await query.edit_message_reply_markup(
            reply_markup=_category_keyboard(expense_id)
        )
    except Exception:
        pass


async def callback_set_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User selected a category from the grid."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    expense_id = parts[1]
    chosen = parts[2]
    
    try:
        supabase.table("expenses").update({"category": chosen}).eq("id", expense_id).execute()
        
        # We don't re-render the image to save time/bandwidth, just update the caption
        caption = f"✅ *Category updated to {chosen}!*"
        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="Markdown",
                reply_markup=_confirm_keyboard(expense_id)
            )
        except Exception:
            await query.edit_message_text(
                caption,
                parse_mode="Markdown",
                reply_markup=_confirm_keyboard(expense_id)
            )
    except Exception as exc:
        logger.exception("Failed to update category: %s", exc)


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


# ── PDF Bank Statement Import Handler ───────────────────────────────────────

_PENDING_BATCH_KEY = "pending_batch_expenses"

@allowed_only
async def handle_pdf_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered when user uploads a PDF Bank/Credit Card Statement."""
    doc = update.effective_message.document
    if not doc or not doc.mime_type == "application/pdf":
        return

    thinking = await update.effective_message.reply_text(
        f"📄 *Processing PDF Statement:* `{doc.file_name}`...\n"
        f"🧠 Extracting debit expenses & classifying categories...",
        parse_mode="Markdown"
    )

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await tg_file.download_as_bytearray()

        from bot.utils.pdf_parser import extract_text_from_pdf_bytes, parse_pdf_statement_transactions
        pdf_text = extract_text_from_pdf_bytes(bytes(pdf_bytes))

        if not pdf_text:
            await thinking.edit_text("❌ Could not extract text from this PDF file. It may be password protected or a scanned image.")
            return

        parsed_items = await parse_pdf_statement_transactions(pdf_text)
        if not parsed_items:
            await thinking.edit_text("ℹ️ No debit expenses detected in this statement.")
            return

        # Deduplication check against existing Supabase expenses
        all_res = supabase.table("expenses").select("date, amount, description").execute()
        existing_set = set()
        for e in (all_res.data or []):
            existing_set.add((str(e.get("date")), float(e.get("amount", 0)), str(e.get("description")).lower()))

        new_items = []
        skipped_count = 0
        for item in parsed_items:
            key = (str(item["date"]), float(item["amount"]), str(item["description"]).lower())
            if key in existing_set:
                skipped_count += 1
            else:
                new_items.append(item)

        if not new_items:
            await thinking.edit_text(
                f"ℹ️ All {len(parsed_items)} transactions in `{doc.file_name}` are already present in your database."
            )
            return

        total_amount = sum(i["amount"] for i in new_items)

        # Store in pending batch
        context.user_data[_PENDING_BATCH_KEY] = new_items

        lines = [
            f"📄 *Bank Statement Parsed:* `{doc.file_name}`\n",
            f"⚡ *{len(new_items)} New Debit Expenses Found* (Total: {fmt_inr(total_amount)})",
            f"_{skipped_count} existing transactions skipped_\n" if skipped_count > 0 else "",
            "*Itemized Breakdown:*",
        ]

        for i, item in enumerate(new_items[:12], 1):
            lines.append(f"{i}. `{item['date']}` · *{item['description']}* · {fmt_inr(item['amount'])} ({item['category']})")

        if len(new_items) > 12:
            lines.append(f"_...and {len(new_items) - 12} more transactions_")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Batch Save {len(new_items)} Items to Supabase", callback_data="batch:save")],
            [InlineKeyboardButton("❌ Cancel Import", callback_data="batch:cancel")]
        ])

        await thinking.delete()
        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=kb
        )

    except Exception as exc:
        logger.exception("Failed to process PDF statement: %s", exc)
        await thinking.edit_text("❌ Error processing PDF statement. Check bot logs.")


async def callback_batch_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed ✅ Batch Save for PDF import."""
    query = update.callback_query
    await query.answer()

    batch_items = context.user_data.get(_PENDING_BATCH_KEY)
    if not batch_items:
        await query.edit_message_text("⚠️ Batch data lost or expired. Please re-upload the PDF.")
        return

    try:
        rows_to_insert = [
            {
                "date": item["date"],
                "description": item["description"],
                "amount": item["amount"],
                "category": item["category"],
                "month": item["month"],
            }
            for item in batch_items
        ]

        res = supabase.table("expenses").insert(rows_to_insert).execute()
        count = len(res.data) if res.data else len(rows_to_insert)
        total_amt = sum(item["amount"] for item in batch_items)

        await query.edit_message_text(
            f"🎉 *Batch Import Complete!*\n\n"
            f"✅ Successfully inserted *{count} transactions* (Total: {fmt_inr(total_amt)}) into Supabase!\n\n"
            f"_Your FinOS dashboard and monthly spending totals are updated._",
            parse_mode="Markdown"
        )
    except Exception as exc:
        logger.exception("Failed batch insert to Supabase: %s", exc)
        await query.edit_message_text("❌ Failed batch save to database. Check bot logs.")

    context.user_data.pop(_PENDING_BATCH_KEY, None)


async def callback_batch_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed ❌ Cancel Import."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Batch PDF import cancelled.")
    context.user_data.pop(_PENDING_BATCH_KEY, None)


# ── Handler Registration ──────────────────────────────────────────────────

def get_expense_handlers() -> list:
    """Return all handlers for expense logging."""
    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
        CallbackQueryHandler(callback_edit_category, pattern="^exp:edit:"),
        CallbackQueryHandler(callback_undo_expense, pattern="^exp:undo:"),
        CallbackQueryHandler(callback_set_category, pattern="^cat:"),
    ]
