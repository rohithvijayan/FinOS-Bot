import os
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PREVIEWS_DIR = Path(__file__).parent.parent.parent / "previews"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True
)

def _ensure_previews_dir():
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

def html_to_image(html_file_name: str, img_file_name: str, size=(460, 620)) -> Path | None:
    """Convert a generated HTML file in PREVIEWS_DIR to a PNG card image."""
    try:
        from html2image import Html2Image
        _ensure_previews_dir()
        html_path = PREVIEWS_DIR / html_file_name
        if not html_path.exists():
            return None
        
        hti = Html2Image(output_path=str(PREVIEWS_DIR))
        hti.screenshot(html_file=str(html_path), save_as=img_file_name, size=size)
        img_path = PREVIEWS_DIR / img_file_name
        return img_path if img_path.exists() else None
    except Exception as exc:
        logger.warning(f"Could not generate PNG image card via html2image: {exc}")
        return None

def render_expense_card(amount, category, merchant, billing_month, date, account=None, is_confirmed=False, save_preview=True) -> tuple[str, Path | None]:
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
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "expense_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        img_path = html_to_image("expense_card.html", "expense_card.png", size=(460, 520))
    return html_content, img_path

def render_balance_card(total_liquid, accounts, emergency_target=1000000, emergency_pct=85, save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("balance_card.html")
    html_content = template.render(
        total_liquid=total_liquid,
        accounts=accounts,
        emergency_target=emergency_target,
        emergency_pct=emergency_pct
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "balance_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        height = max(500, 360 + len(accounts) * 70)
        img_path = html_to_image("balance_card.html", "balance_card.png", size=(460, height))
    return html_content, img_path

def render_spending_card(month, total_spent, categories, monthly_budget=50000, date_range="25 Jul - 24 Aug", save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("spending_card.html")
    html_content = template.render(
        month=month,
        total_spent=total_spent,
        categories=categories,
        monthly_budget=monthly_budget,
        date_range=date_range
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "spending_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        height = max(520, 380 + len(categories) * 75)
        img_path = html_to_image("spending_card.html", "spending_card.png", size=(460, height))
    return html_content, img_path

def render_portfolio_card(total_portfolio, asset_allocation, sips=None, growth_pct="2.4", total_sip_amount=35000, save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("portfolio_card.html")
    html_content = template.render(
        total_portfolio=total_portfolio,
        asset_allocation=asset_allocation,
        sips=sips or [],
        growth_pct=growth_pct,
        total_sip_amount=total_sip_amount
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "portfolio_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        height = max(560, 400 + len(asset_allocation) * 65 + len(sips or []) * 35)
        img_path = html_to_image("portfolio_card.html", "portfolio_card.png", size=(460, height))
    return html_content, img_path

def render_start_card(save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("start_card.html")
    html_content = template.render()
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "start_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        img_path = html_to_image("start_card.html", "start_card.png", size=(460, 560))
    return html_content, img_path

def render_digest_daily_card(date: str, total_today: float, expenses: list[dict], daily_target=1600.0, save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("digest_daily_card.html")
    html_content = template.render(
        date=date,
        total_today=total_today,
        expenses=expenses,
        daily_target=daily_target
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "digest_daily_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        height = max(500, 360 + len(expenses) * 60)
        img_path = html_to_image("digest_daily_card.html", "digest_daily_card.png", size=(460, height))
    return html_content, img_path

def render_digest_monthly_card(month: str, total_spent: float, categories: list[dict], monthly_budget=50000.0, total_liquid=1245000.0, date_range="25 Jul - 24 Aug", save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("digest_monthly_card.html")
    top_cat = categories[0]["name"] if categories else "General"
    html_content = template.render(
        month=month,
        total_spent=total_spent,
        categories=categories,
        monthly_budget=monthly_budget,
        total_liquid=total_liquid,
        top_category=top_cat,
        date_range=date_range
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "digest_monthly_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        height = max(540, 420 + min(len(categories), 4) * 60)
        img_path = html_to_image("digest_monthly_card.html", "digest_monthly_card.png", size=(460, height))
    return html_content, img_path

def render_budget_alert_card(category: str, amount_spent: float, limit_amount: float, threshold_level: int, billing_month: str, save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("budget_alert_card.html")
    pct_used = (amount_spent / limit_amount * 100) if limit_amount > 0 else 100.0
    remaining = limit_amount - amount_spent
    html_content = template.render(
        category=category,
        amount_spent=amount_spent,
        limit_amount=limit_amount,
        pct_used=pct_used,
        threshold_level=threshold_level,
        billing_month=billing_month,
        remaining=remaining
    )
    img_path = None
    if save_preview:
        _ensure_previews_dir()
        html_file = PREVIEWS_DIR / "budget_alert_card.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        img_path = html_to_image("budget_alert_card.html", "budget_alert_card.png", size=(460, 500))
    return html_content, img_path
