import os
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

import tempfile

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PREVIEWS_DIR = Path(tempfile.gettempdir()) / "finos_previews"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True
)

def _ensure_previews_dir():
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

def _html_to_png_weasyprint(html_path: Path, img_path: Path, size=(460, 620)) -> bool:
    """Render HTML → PDF via WeasyPrint, then PDF → PNG via pdf2image (no Chrome needed)."""
    try:
        from weasyprint import HTML as WeasyHTML
        from pdf2image import convert_from_bytes

        width_px, height_px = size
        # WeasyPrint uses CSS page sizing (1px ≈ 0.75pt, 96dpi default)
        # We set the page size to match our card width
        css_override = f"@page {{ margin:0; size:{width_px}px {height_px}px; }}"
        from weasyprint import CSS

        html_str = html_path.read_text(encoding="utf-8")
        pdf_bytes = WeasyHTML(string=html_str, base_url=str(html_path.parent)).write_pdf(
            stylesheets=[CSS(string=css_override)]
        )
        images = convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=1)
        if images:
            # Crop/resize to desired output dimensions
            img = images[0]
            target_w = width_px * 2  # dpi=150 → 150/72 * px ≈ 2x
            img = img.resize((target_w, int(img.height * target_w / img.width)))
            img.save(str(img_path), "PNG", optimize=True)
            logger.info(f"WeasyPrint rendered {img_path.name} ({img_path.stat().st_size // 1024} KB)")
            return True
        return False
    except Exception as exc:
        logger.warning(f"WeasyPrint rendering failed: {exc}")
        return False


def _html_to_png_html2image(html_path: Path, img_path: Path, size=(460, 620)) -> bool:
    """Fallback: render HTML → PNG via html2image (requires Chrome/Chromium)."""
    try:
        from html2image import Html2Image
        chrome_path = os.getenv("CHROME_BIN") or os.getenv("BROWSER_PATH")
        kwargs = {"output_path": str(img_path.parent)}
        if chrome_path:
            kwargs["browser_executable"] = chrome_path
        hti = Html2Image(**kwargs)
        hti.screenshot(html_file=str(html_path), save_as=img_path.name, size=size)
        return img_path.exists()
    except Exception as exc:
        logger.warning(f"html2image rendering failed: {exc}")
        return False


def html_to_image(html_file_name: str, img_file_name: str, size=(460, 620)) -> Path | None:
    """Convert a generated HTML file in PREVIEWS_DIR to a PNG card image.
    
    Tries WeasyPrint (no Chrome required) first, then falls back to html2image.
    """
    _ensure_previews_dir()
    html_path = PREVIEWS_DIR / html_file_name
    if not html_path.exists():
        return None
    img_path = PREVIEWS_DIR / img_file_name

    # Primary: WeasyPrint (works on Vercel serverless, no Chrome needed)
    if _html_to_png_weasyprint(html_path, img_path, size):
        return img_path

    # Fallback: html2image (requires Chrome, works on local/Docker)
    if _html_to_png_html2image(html_path, img_path, size):
        return img_path

    logger.warning(f"All rendering backends failed for {html_file_name}")
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
