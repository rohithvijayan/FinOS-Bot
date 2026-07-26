import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PREVIEWS_DIR = Path(__file__).parent.parent.parent / "previews"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True
)

def _ensure_previews_dir():
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

def render_expense_card(amount, category, merchant, billing_month, date, account=None, is_confirmed=False, save_preview=True) -> str:
    template = env.get_template("expense_card.html")
    html_content = template.render(
        amount=amount,
        category=category,
        merchant=merchant,
        billing_month=billing_month,
        date=date,
        account=account,
        is_confirmed=is_confirmed
    )
    if save_preview:
        _ensure_previews_dir()
        with open(PREVIEWS_DIR / "expense_card.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    return html_content

def render_balance_card(total_liquid, accounts, emergency_target=1000000, emergency_pct=85, save_preview=True) -> str:
    template = env.get_template("balance_card.html")
    html_content = template.render(
        total_liquid=total_liquid,
        accounts=accounts,
        emergency_target=emergency_target,
        emergency_pct=emergency_pct
    )
    if save_preview:
        _ensure_previews_dir()
        with open(PREVIEWS_DIR / "balance_card.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    return html_content

def render_spending_card(month, total_spent, categories, monthly_budget=50000, date_range="25 Jul - 24 Aug", save_preview=True) -> str:
    template = env.get_template("spending_card.html")
    html_content = template.render(
        month=month,
        total_spent=total_spent,
        categories=categories,
        monthly_budget=monthly_budget,
        date_range=date_range
    )
    if save_preview:
        _ensure_previews_dir()
        with open(PREVIEWS_DIR / "spending_card.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    return html_content

def render_portfolio_card(total_portfolio, asset_allocation, sips=None, growth_pct="2.4", total_sip_amount=35000, save_preview=True) -> str:
    template = env.get_template("portfolio_card.html")
    html_content = template.render(
        total_portfolio=total_portfolio,
        asset_allocation=asset_allocation,
        sips=sips or [],
        growth_pct=growth_pct,
        total_sip_amount=total_sip_amount
    )
    if save_preview:
        _ensure_previews_dir()
        with open(PREVIEWS_DIR / "portfolio_card.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    return html_content
