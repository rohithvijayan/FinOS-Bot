import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.utils.html_renderer import (
    render_expense_card,
    render_balance_card,
    render_spending_card,
    render_portfolio_card
)

def test_render_all_templates():
    print("Testing FinOS HTML Card Templates Generation...")

    # 1. Expense Card Test
    expense_html = render_expense_card(
        amount=350.00,
        category="Eating Out",
        merchant="Zomato",
        billing_month="August 2026",
        date="26-Jul-2026",
        account="HDFC Credit Card",
        is_confirmed=False
    )
    assert "Zomato" in expense_html
    assert "350.00" in expense_html
    print("✅ Expense Confirmation Card rendered successfully!")

    # 2. Balance Card Test
    accounts_data = [
        {"name": "HDFC Savings Account", "type": "Primary Bank", "balance": 450000.00},
        {"name": "ICICI Direct Account", "type": "Secondary Bank", "balance": 295000.00},
        {"name": "Emergency Cash Fund", "type": "Liquid Buffer", "balance": 500000.00}
    ]
    balance_html = render_balance_card(
        total_liquid=1245000.00,
        accounts=accounts_data,
        emergency_target=1500000.00,
        emergency_pct=83
    )
    assert "1,245,000.00" in balance_html
    assert "HDFC Savings Account" in balance_html
    print("✅ Balance Overview Card rendered successfully!")

    # 3. Monthly Spending Card Test (matching exact billing month cutoff rule)
    categories_data = [
        {"name": "Eating Out", "amount": 182.00},
        {"name": "Groceries", "amount": 255.00},
        {"name": "Shopping", "amount": 200.00}
    ]
    spending_html = render_spending_card(
        month="August 2026",
        total_spent=637.00,
        categories=categories_data,
        monthly_budget=50000.00,
        date_range="25 Jul - 24 Aug"
    )
    assert "637.00" in spending_html
    assert "August 2026" in spending_html
    print("✅ Monthly Spending Card rendered successfully!")

    # 4. Investment Portfolio Card Test
    asset_allocation = [
        {"name": "Mutual Funds", "amount": 2850000.00, "pct": 59.1},
        {"name": "Indian Direct Equities", "amount": 1240500.00, "pct": 25.7},
        {"name": "Sovereign Gold Bonds", "amount": 730000.00, "pct": 15.2}
    ]
    sips_data = [
        {"name": "Parag Parikh Flexi Cap", "amount": 15000.00},
        {"name": "Mirae Asset Large Cap", "amount": 10000.00},
        {"name": "Nippon India Small Cap", "amount": 10000.00}
    ]
    portfolio_html = render_portfolio_card(
        total_portfolio=4820500.00,
        asset_allocation=asset_allocation,
        sips=sips_data,
        growth_pct="2.4",
        total_sip_amount=35000.00
    )
    assert "4,820,500.00" in portfolio_html
    assert "Parag Parikh Flexi Cap" in portfolio_html
    print("✅ Investment Portfolio Card rendered successfully!")

if __name__ == "__main__":
    test_render_all_templates()
