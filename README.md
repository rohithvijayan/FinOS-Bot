# FinOS Telegram Bot 🤖

A Python Telegram bot that acts as the always-on, zero-friction entry point to your [FinOS](../notionExpenseInvsmnt/finance-os-next) financial data.

## Phase 1 Features

- 💸 **Natural language expense logging** — `"spent 350 at Zomato"` → parsed, previewed, confirmed, saved to Supabase
- ✅ **Confirmation flow** — inline keyboard (Save / Change Category / Cancel) before any write
- ↩️ **Undo** — `/undo` deletes the last logged expense
- 💳 `/balance` — liquid savings breakdown across all accounts
- 🧾 `/spending [Month Year]` — category-level spending breakdown with budget comparison
- 📊 `/portfolio` — full investment overview (SIPs + Bonds)
- 🔐 **Owner-only auth** — all requests gated by `ALLOWED_CHAT_ID` whitelist

---

## Setup

### 1. Prerequisites

- Python 3.11+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Your Telegram User ID (message [@userinfobot](https://t.me/userinfobot))
- A Google Gemini API key

### 2. Install Dependencies

```bash
cd /home/rohithvijayan/Desktop/FinOS-Bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure `.env`

Your `.env` already has the bot token, Gemini key, and Supabase credentials.  
You just need to add your **Telegram User ID**:

```
# Message @userinfobot on Telegram to get your user ID
ALLOWED_CHAT_ID=123456789
```

### 4. Run the Bot

```bash
python -m bot.main
```

You should see:
```
Starting FinOS Bot…
All handlers registered. Starting polling…
```

---

## Usage Examples

| Message | Bot Action |
|---|---|
| `"spent 350 at Zomato"` | Parses → shows preview → saves on confirm |
| `"uber 180"` | Auto-categorizes as Transport |
| `"groceries 1500"` | Auto-categorizes as Groceries |
| `/undo` | Deletes last logged expense |
| `/balance` | Shows all savings accounts |
| `/spending` | This month's spending by category |
| `/spending June 2026` | June spending breakdown |
| `/portfolio` | Investment overview |

---

## Project Structure

```
FinOS-Bot/
├── bot/
│   ├── main.py              # Entry point
│   ├── config.py            # Env vars & constants
│   ├── supabase_client.py   # Supabase singleton
│   ├── gemini_client.py     # NLP expense parser
│   ├── handlers/
│   │   ├── auth.py          # chat_id whitelist decorator
│   │   ├── expense.py       # Expense logging + /undo
│   │   ├── balance.py       # /balance
│   │   ├── spending.py      # /spending
│   │   └── portfolio.py     # /portfolio
│   └── utils/
│       ├── formatters.py    # Message builders, INR formatting
│       └── categories.py    # Category keywords & icons
├── .env                     # Secrets (gitignored)
├── .env.example             # Template
├── requirements.txt
└── README.md
```

---

## Roadmap

- **Phase 2**: Gemini conversational queries, budget alerts, daily/monthly digest cron jobs
- **Phase 3**: Receipt photo parsing (Gemini Vision), goal deposits, month-end smart sweep
- **Phase 4**: SIP NAV alerts, tax-loss harvesting reminders
