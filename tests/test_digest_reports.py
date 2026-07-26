import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.utils.html_renderer import render_digest_daily_card, render_digest_monthly_card
from bot.handlers.digest import fetch_daily_expenses, fetch_monthly_digest

def test_digest_rendering():
    print("Testing FinOS Push Intelligence Digest Reports...")

    # 1. Daily Digest Card Test
    daily_expenses = [
        {"description": "Zomato Dinner", "category": "Eating Out", "amount": 350.00},
        {"description": "Uber Office", "category": "Transport", "amount": 180.00}
    ]
    daily_html, daily_img = render_digest_daily_card(
        date="26 Jul 2026",
        total_today=530.00,
        expenses=daily_expenses,
        daily_target=1600.00
    )
    assert "Zomato Dinner" in daily_html
    assert daily_img is not None and daily_img.exists()
    print("✅ Daily Digest Card & Image rendered successfully!")

    # 2. Monthly Digest Card Test
    categories_data = [
        {"name": "Eating Out", "amount": 182.00},
        {"name": "Groceries", "amount": 255.00},
        {"name": "Shopping", "amount": 200.00}
    ]
    monthly_html, monthly_img = render_digest_monthly_card(
        month="August 2026",
        total_spent=637.00,
        categories=categories_data,
        monthly_budget=50000.00,
        total_liquid=1245000.00,
        date_range="25 Jul - 24 Aug"
    )
    assert "Executive Monthly Digest" in monthly_html
    assert monthly_img is not None and monthly_img.exists()
    print("✅ Monthly Executive Digest Card & Image rendered successfully!")

if __name__ == "__main__":
    test_digest_rendering()
