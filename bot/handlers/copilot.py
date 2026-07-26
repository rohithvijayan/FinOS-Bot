"""
copilot.py — FinOS AI Copilot handler.

/copilot or the 🤖 Copilot menu button activates an interactive AI assistant
powered by Gemini. It pulls live data from Supabase (expenses, savings, SIPs,
bonds, budgets) and answers natural language questions about the user's finances.

Supports multi-turn conversation within a session — the bot keeps chat history
until the user sends /done or is idle for 10 minutes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot.handlers.auth import allowed_only
from bot.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

COPILOT_CHAT_STATE = "copilot_active"
_HISTORY_KEY = "_copilot_history"
_MAX_TURNS    = 20   # max conversation turns before auto-reset


# ── Context builder ────────────────────────────────────────────────────────────

async def _build_financial_context() -> str:
    """Pull live data from Supabase and build a rich context string for Gemini."""
    from bot.supabase_client import supabase

    lines: list[str] = [
        f"=== FinOS — User Financial Data Snapshot ===",
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p IST')}",
        "",
    ]

    # Savings / Liquid accounts
    try:
        savings = supabase.table("savings").select("*").execute().data or []
        total_liq = sum(float(a.get("balance", 0)) for a in savings)
        lines.append(f"## Liquid Accounts (Total: ₹{total_liq:,.0f})")
        for a in savings:
            lines.append(
                f"  - {a.get('bank_name', a.get('name','?'))}: ₹{float(a.get('balance',0)):,.0f}"
                f"  ({a.get('interest_rate', '')}% p.a.)"
            )
        lines.append("")
    except Exception as e:
        lines.append(f"## Liquid Accounts: unavailable ({e})\n")

    # Current month expenses
    try:
        now = datetime.now()
        # Billing month format used in app (e.g. "July 2026")
        billing_month = now.strftime("%B %Y")
        exp = (
            supabase.table("expenses")
            .select("*")
            .ilike("billing_month", f"%{billing_month}%")
            .execute()
            .data or []
        )
        total_spent = sum(float(e.get("amount", 0)) for e in exp)
        lines.append(f"## Expenses — {billing_month} (Total: ₹{total_spent:,.0f})")
        # Group by category
        cat_totals: dict[str, float] = {}
        for e in exp:
            cat = e.get("category", "Other")
            cat_totals[cat] = cat_totals.get(cat, 0) + float(e.get("amount", 0))
        for cat, amt in sorted(cat_totals.items(), key=lambda x: -x[1]):
            lines.append(f"  - {cat}: ₹{amt:,.0f}")
        lines.append(f"  ({len(exp)} transactions)")
        lines.append("")
    except Exception as e:
        lines.append(f"## Expenses: unavailable ({e})\n")

    # Budgets
    try:
        budgets = supabase.table("budgets").select("*").execute().data or []
        if budgets:
            lines.append("## Monthly Budgets")
            for b in budgets:
                cat   = b.get("category", "?")
                limit = float(b.get("limit_amount", 0))
                lines.append(f"  - {cat}: ₹{limit:,.0f}/month")
            lines.append("")
    except Exception as e:
        lines.append(f"## Budgets: unavailable ({e})\n")

    # Portfolio summary
    try:
        ps = supabase.table("portfolio_summary").select("*").eq("id", 1).execute().data
        if ps:
            p = ps[0]
            lines.append("## Portfolio Summary")
            lines.append(f"  - Total Invested: ₹{float(p.get('total_invested',0)):,.0f}")
            lines.append(f"  - Current Value:  ₹{float(p.get('current_value',0)):,.0f}")
            lines.append(f"  - Total Gain:     ₹{float(p.get('total_gain',0)):,.0f}")
            lines.append(f"  - Overall Return: {p.get('return_pct',0)}%")
            lines.append(f"  - Monthly SIP:    ₹{float(p.get('monthly_sip',0)):,.0f}")
            lines.append("")
    except Exception as e:
        lines.append(f"## Portfolio Summary: unavailable ({e})\n")

    # SIPs
    try:
        sips = supabase.table("sips").select("*").execute().data or []
        if sips:
            lines.append("## Mutual Funds / SIPs")
            for s in sips:
                lines.append(
                    f"  - {s.get('name','?')}: Invested ₹{float(s.get('invested',0)):,.0f}"
                    f" | Current ₹{float(s.get('current_value',0)):,.0f}"
                    f" | Return {s.get('return_pct','?')}"
                    f" | SIP ₹{float(s.get('monthly_sip',0)):,.0f}/mo"
                    f" | Active: {s.get('active','?')}"
                )
            lines.append("")
    except Exception as e:
        lines.append(f"## SIPs: unavailable ({e})\n")

    # Bonds
    try:
        bonds = supabase.table("bonds").select("*").execute().data or []
        if bonds:
            lines.append("## Bonds & Debt")
            for b in bonds:
                lines.append(
                    f"  - {b.get('name','?')}: Invested ₹{float(b.get('invested',0)):,.0f}"
                    f" | Current ₹{float(b.get('current_value',0)):,.0f}"
                    f" | YTM {b.get('ytm','?')}"
                    f" | Status: {b.get('status','?')}"
                )
            lines.append("")
    except Exception as e:
        lines.append(f"## Bonds: unavailable ({e})\n")

    return "\n".join(lines)


def _build_system_prompt(financial_context: str) -> str:
    return f"""You are FinOS Copilot — a sharp, concise personal finance AI assistant embedded in a Telegram bot.

You have access to the user's complete real-time financial data below. Use it to answer questions accurately.

RULES:
- Be concise. Telegram messages should be short and scannable.
- Use ₹ for Indian Rupee amounts with Indian number formatting (₹1,23,456).
- Use markdown formatting: *bold* for key figures, _italic_ for labels.
- Give specific, actionable insights — not generic financial advice.
- If asked about trends, calculate them from the data provided.
- If the data is insufficient to answer, say so clearly.
- Never make up numbers. Only use data from the snapshot below.
- When relevant, proactively mention observations (e.g., overspending in a category).
- Keep responses under 350 words unless the user explicitly asks for a detailed report.

{financial_context}
"""


# ── Gemini call ────────────────────────────────────────────────────────────────

async def _ask_gemini(system_prompt: str, history: list[dict], user_msg: str) -> str:
    """Send conversation to Gemini and return the assistant reply."""
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API key not configured. Set `GEMINI_API_KEY` in your `.env`."

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system_prompt,
        )

        # Build chat history for multi-turn
        chat = model.start_chat(history=history)
        resp = await chat.send_message_async(user_msg)
        return resp.text

    except Exception as exc:
        logger.error("Gemini copilot error: %s", exc, exc_info=True)
        return f"❌ Gemini error: {exc}"


# ── Handlers ───────────────────────────────────────────────────────────────────

@allowed_only
async def copilot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate the FinOS Copilot assistant."""
    thinking = await update.effective_message.reply_text("🤖 Loading your financial data...")

    try:
        financial_ctx = await _build_financial_context()
        context.user_data["_copilot_system"] = _build_system_prompt(financial_ctx)
        context.user_data[_HISTORY_KEY] = []

        # Send welcome with quick-prompt suggestions
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 How's my budget?",    callback_data="cop:budget")],
            [InlineKeyboardButton("📈 Portfolio health?",  callback_data="cop:portfolio")],
            [InlineKeyboardButton("💡 Financial tips",     callback_data="cop:tips")],
            [InlineKeyboardButton("🔢 Net worth breakdown", callback_data="cop:networth")],
        ])

        await thinking.edit_text(
            "🤖 *FinOS Copilot* is ready!\n\n"
            "I've loaded your live financial data. Ask me anything — expenses, investments, budget health, savings tips.\n\n"
            "Quick prompts below, or just type your question:\n"
            "_(Type /done to exit Copilot mode)_",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.error("Copilot init error: %s", exc)
        await thinking.edit_text("❌ Failed to load financial data. Try again.")


@allowed_only
async def copilot_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a user's question to the Copilot (non-command text while copilot active)."""
    text = (update.effective_message.text or "").strip()

    system_prompt = context.user_data.get("_copilot_system")
    if not system_prompt:
        # Copilot not initialized — re-init silently
        await copilot_command(update, context)
        return

    history: list[dict] = context.user_data.get(_HISTORY_KEY, [])

    # Auto-reset after max turns
    if len(history) >= _MAX_TURNS * 2:
        history = []
        context.user_data[_HISTORY_KEY] = []

    thinking = await update.effective_message.reply_text("🧠 Thinking...")

    reply = await _ask_gemini(system_prompt, history, text)

    # Update history (Gemini SDK format: role + parts)
    history.append({"role": "user",  "parts": [text]})
    history.append({"role": "model", "parts": [reply]})
    context.user_data[_HISTORY_KEY] = history

    await thinking.edit_text(reply, parse_mode="Markdown")


async def copilot_quick_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quick-prompt inline button taps."""
    query = update.callback_query
    await query.answer()

    prompts = {
        "cop:budget":    "How am I doing on my budget this month? Which categories am I overspending on?",
        "cop:portfolio": "Give me a health check on my investment portfolio. Am I diversified enough?",
        "cop:tips":      "Based on my spending and savings, give me 3 specific financial tips I can action this week.",
        "cop:networth":  "Break down my net worth: liquid savings + portfolio (SIPs + bonds). What's the total?",
    }

    user_q = prompts.get(query.data)
    if not user_q:
        return

    # Inject the question as if the user typed it
    system_prompt = context.user_data.get("_copilot_system")
    if not system_prompt:
        # Re-init
        financial_ctx = await _build_financial_context()
        system_prompt = _build_system_prompt(financial_ctx)
        context.user_data["_copilot_system"] = system_prompt
        context.user_data[_HISTORY_KEY] = []

    history: list[dict] = context.user_data.get(_HISTORY_KEY, [])

    await query.edit_message_text(
        f"🤖 *FinOS Copilot*\n\n_{user_q}_\n\n🧠 Thinking...",
        parse_mode="Markdown",
    )

    reply = await _ask_gemini(system_prompt, history, user_q)

    history.append({"role": "user",  "parts": [user_q]})
    history.append({"role": "model", "parts": [reply]})
    context.user_data[_HISTORY_KEY] = history

    # Add a follow-up keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh data & ask again", callback_data="cop:refresh")],
    ])
    await query.edit_message_text(
        f"🤖 *FinOS Copilot*\n\n{reply}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def copilot_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh Supabase data and reset the conversation."""
    query = update.callback_query
    await query.answer("Refreshing data...")
    await query.edit_message_text("🔄 Refreshing your financial data...")

    financial_ctx = await _build_financial_context()
    context.user_data["_copilot_system"] = _build_system_prompt(financial_ctx)
    context.user_data[_HISTORY_KEY] = []

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 How's my budget?",     callback_data="cop:budget")],
        [InlineKeyboardButton("📈 Portfolio health?",   callback_data="cop:portfolio")],
        [InlineKeyboardButton("💡 Financial tips",      callback_data="cop:tips")],
        [InlineKeyboardButton("🔢 Net worth breakdown", callback_data="cop:networth")],
    ])
    await query.edit_message_text(
        "✅ *Data refreshed!* FinOS Copilot is ready with the latest numbers.\n\n"
        "Ask me anything or tap a quick prompt:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
