import sys
import json
import asyncio
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Add root directory to sys.path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from bot.config import TELEGRAM_BOT_TOKEN
from bot.handlers.expense import (
    build_expense_conversation,
    handle_pdf_document,
    callback_batch_save,
    callback_batch_cancel
)
from bot.handlers.spending import (
    spending_command,
    callback_open_month_picker,
    callback_select_spending_month
)
from bot.handlers.balance import balance_command
from bot.handlers.portfolio import portfolio_command
from bot.handlers.digest import digest_command
from bot.handlers.expense import undo_command
from bot.main import start_command, help_command, post_init

# Global Application instance for serverless Vercel function
_app_instance = None


def get_telegram_app() -> Application:
    global _app_instance
    if _app_instance is None:
        _app_instance = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .build()
        )
        from bot.handlers.copilot import (
            copilot_command, copilot_quick_prompt, copilot_refresh,
        )
        _app_instance.add_handler(build_expense_conversation())
        _app_instance.add_handler(CommandHandler("start", start_command))
        _app_instance.add_handler(CommandHandler("help", help_command))
        _app_instance.add_handler(CommandHandler("balance", balance_command))
        _app_instance.add_handler(CommandHandler("spending", spending_command))
        _app_instance.add_handler(CommandHandler("portfolio", portfolio_command))
        _app_instance.add_handler(CommandHandler("digest", digest_command))
        _app_instance.add_handler(CommandHandler("undo", undo_command))
        _app_instance.add_handler(CommandHandler("copilot", copilot_command))
        _app_instance.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_document))
        _app_instance.add_handler(CallbackQueryHandler(copilot_quick_prompt, pattern="^cop:(budget|portfolio|tips|networth)$"))
        _app_instance.add_handler(CallbackQueryHandler(copilot_refresh,      pattern="^cop:refresh$"))
        _app_instance.add_handler(CallbackQueryHandler(callback_open_month_picker, pattern="^spend_pick:open$"))
        _app_instance.add_handler(CallbackQueryHandler(callback_select_spending_month, pattern="^spend_month:"))
        _app_instance.add_handler(CallbackQueryHandler(callback_batch_save, pattern="^batch:save$"))
        _app_instance.add_handler(CallbackQueryHandler(callback_batch_cancel, pattern="^batch:cancel$"))
    return _app_instance


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        response = {
            "status": "online",
            "service": "FinOS Telegram Bot Serverless API",
            "message": "Send Telegram webhooks to this endpoint via POST."
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            update_data = json.loads(post_data.decode("utf-8"))
            app = get_telegram_app()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def process():
                await app.initialize()
                await app.start()
                update = Update.de_json(update_data, app.bot)
                await app.process_update(update)
                await app.stop()
                await app.shutdown()

            loop.run_until_complete(process())
            loop.close()

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
