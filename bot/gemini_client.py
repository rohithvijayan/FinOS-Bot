"""
Gemini client — parses natural language expense descriptions into structured data.

If Gemini is unavailable (no key / quota), falls back to local keyword + regex parsing.
"""
from __future__ import annotations

import json
import re
import logging
from datetime import date

import google.generativeai as genai

from bot.config import GEMINI_API_KEY, GEMINI_MODEL
from bot.utils.categories import UI_CATEGORIES, guess_category

logger = logging.getLogger(__name__)

# Initialise Gemini if we have a key
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None
    logger.warning("GEMINI_API_KEY not set — falling back to regex parser.")


_SYSTEM_PROMPT = """\
You are a personal finance assistant. Extract expense details from the user's message.

Available categories (use EXACTLY one of these):
{categories}

Respond ONLY with a valid JSON object in this exact format:
{{
  "amount": <number>,
  "description": "<short description, max 40 chars>",
  "category": "<one of the categories above>",
  "confidence": <0.0 to 1.0>
}}

Rules:
- amount must be a positive number (no currency symbol)
- If the message mentions a merchant/place, use it as the description
- If the category is unclear, pick "Others"
- confidence: 1.0 = certain, 0.5 = guessed
- If no amount is found, return {{"error": "no_amount"}}
""".format(categories="\n".join(f"  - {c}" for c in UI_CATEGORIES))


async def parse_expense(text: str) -> dict:
    """
    Parse a natural language message into an expense dict.

    Returns:
        {
            "amount": float,
            "description": str,
            "category": str,
            "confidence": float,
            "date": str  (today, YYYY-MM-DD)
        }
        or {"error": "no_amount"} if no amount detected.
    """
    today = date.today().strftime("%Y-%m-%d")

    if _model:
        try:
            result = await _model.generate_content_async(
                f"{_SYSTEM_PROMPT}\n\nUser message: {text}"
            )
            raw = result.text.strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if "error" in parsed:
                return parsed
            parsed["date"] = today
            return parsed
        except Exception as exc:
            logger.warning("Gemini parse failed (%s), falling back to regex.", exc)

    # ── Fallback: regex + keyword lookup ────────────────────────────────────
    return _regex_parse(text, today)


def _regex_parse(text: str, today: str) -> dict:
    """Simple regex-based parser used when Gemini is unavailable."""
    # Look for amounts: 350, 1,200, 1200.50, ₹350, rs 350, inr 350
    amount_pattern = re.compile(
        r"(?:₹|rs\.?\s*|inr\s*)?(\d[\d,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )
    matches = amount_pattern.findall(text)
    if not matches:
        return {"error": "no_amount"}

    # Take the first (usually the only) numeric value
    amount_str = matches[0].replace(",", "")
    try:
        amount = float(amount_str)
    except ValueError:
        return {"error": "no_amount"}

    category = guess_category(text) or "Others"
    # Build description from the text with the amount stripped
    description = re.sub(r"(?:₹|rs\.?\s*|inr\s*)?\d[\d,]*(?:\.\d{1,2})?", "", text, flags=re.IGNORECASE)
    description = re.sub(r"\b(spent|paid|bought|purchased|on|at|for|in|from)\b", "", description, flags=re.IGNORECASE)
    description = " ".join(description.split()).strip().title() or "Expense"

    return {
        "amount": amount,
        "description": description[:40] or "Expense",
        "category": category,
        "confidence": 0.6,
        "date": today,
    }
