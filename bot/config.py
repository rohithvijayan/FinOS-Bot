"""
Configuration — loads .env and exposes all constants used across the bot.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

# Comma-separated list of allowed Telegram user IDs (integers)
_raw_ids = os.getenv("ALLOWED_CHAT_ID", "")
ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip()) for cid in _raw_ids.split(",") if cid.strip().lstrip("-").isdigit()
}

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]  # service-role key

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.0-flash"
