"""
Auth middleware — enforces owner-only access.

The bot silently ignores any message from a chat_id not in ALLOWED_CHAT_IDS.
If ALLOWED_CHAT_IDS is empty (not yet configured), the bot warns the user.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Coroutine

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ALLOWED_CHAT_IDS

logger = logging.getLogger(__name__)


def allowed_only(
    handler: Callable[..., Coroutine[Any, Any, None]]
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Decorator that restricts a handler to ALLOWED_CHAT_IDS."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        user = update.effective_user

        if not ALLOWED_CHAT_IDS:
            # Bot owner hasn't set ALLOWED_CHAT_ID yet — warn them and tell them their ID
            await update.effective_message.reply_text(
                f"⚠️ *Auth not configured!*\n\n"
                f"Set `ALLOWED_CHAT_ID={chat_id}` in your `.env` file and restart the bot.\n\n"
                f"Your Telegram User ID: `{chat_id}`",
                parse_mode="Markdown",
            )
            return

        if chat_id not in ALLOWED_CHAT_IDS:
            logger.warning(
                "Blocked unauthorized access: chat_id=%s user=%s",
                chat_id,
                user.username if user else "unknown",
            )
            # Silently ignore
            return

        await handler(update, context)

    return wrapper
