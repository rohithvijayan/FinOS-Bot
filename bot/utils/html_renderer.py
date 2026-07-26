"""
html_renderer.py — Card image generation for FinOS Bot.

Rendering priority (per card):
  1. Pillow renderer  — pure Python, zero system deps, works on Vercel
  2. WeasyPrint       — HTML→PDF→PNG (needs libpango; works on Debian/Docker)
  3. html2image       — HTML→PNG via headless Chrome (needs Chrome binary)
  4. None             — caller sends formatted text fallback instead
"""
import os
import logging
import tempfile
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PREVIEWS_DIR  = Path(tempfile.gettempdir()) / "finos_previews"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def _ensure_previews_dir():
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)


# ── HTML → Image fallback pipeline (WeasyPrint → html2image) ─────────────────

def _weasyprint_render(html_path: Path, img_path: Path, size=(460, 620)) -> bool:
    try:
        from weasyprint import HTML as WeasyHTML, CSS
        from pdf2image import convert_from_bytes
        w, h = size
        css  = CSS(string=f"@page {{margin:0;size:{w}px {h}px;}}")
        pdf  = WeasyHTML(string=html_path.read_text(encoding="utf-8"),
                         base_url=str(html_path.parent)).write_pdf(stylesheets=[css])
        imgs = convert_from_bytes(pdf, dpi=150, first_page=1, last_page=1)
        if imgs:
            i = imgs[0]
            tw = w * 2
            i.resize((tw, int(i.height * tw / i.width))).save(str(img_path), "PNG")
            return True
    except Exception as exc:
        logger.warning("WeasyPrint: %s", exc)
    return False


def _html2image_render(html_path: Path, img_path: Path, size=(460, 620)) -> bool:
    try:
        from html2image import Html2Image
        chrome = os.getenv("CHROME_BIN") or os.getenv("BROWSER_PATH")
        kw = {"output_path": str(img_path.parent)}
        if chrome:
            kw["browser_executable"] = chrome
        hti = Html2Image(**kw)
        hti.screenshot(html_file=str(html_path), save_as=img_path.name, size=size)
        return img_path.exists()
    except Exception as exc:
        logger.warning("html2image: %s", exc)
    return False


def _html_to_image(html_file: str, img_file: str, size=(460, 620)) -> Path | None:
    _ensure_previews_dir()
    hp = PREVIEWS_DIR / html_file
    if not hp.exists():
        return None
    ip = PREVIEWS_DIR / img_file
    if _weasyprint_render(hp, ip, size) or _html2image_render(hp, ip, size):
        return ip
    logger.warning("All HTML→image backends failed for %s", html_file)
    return None


def _save_html(name: str, html: str) -> Path:
    _ensure_previews_dir()
    p = PREVIEWS_DIR / name
    p.write_text(html, encoding="utf-8")
    return p


def _pil_bytes_to_path(img_bytes: bytes | None, img_file: str) -> Path | None:
    if not img_bytes:
        return None
    _ensure_previews_dir()
    p = PREVIEWS_DIR / img_file
    p.write_bytes(img_bytes)
    return p


# ── Public render functions ────────────────────────────────────────────────────

def render_expense_card(
    amount, category, merchant, billing_month, date,
    account=None, is_confirmed=False, save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("expense_card.html")
    html = template.render(
        amount=amount, category=category, merchant=merchant,
        billing_month=billing_month, date=date,
        account=account, is_confirmed=is_confirmed,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import expense_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(amount=amount, category=category, merchant=merchant,
                 billing_month=billing_month, date=date,
                 account=account, is_confirmed=is_confirmed),
            "expense_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow expense_card: %s", exc)

    # 2. HTML pipeline
    _save_html("expense_card.html", html)
    return html, _html_to_image("expense_card.html", "expense_card.png", size=(460, 520))


def render_balance_card(
    total_liquid, accounts,
    emergency_target=1_000_000, emergency_pct=85,
    save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("balance_card.html")
    html = template.render(
        total_liquid=total_liquid, accounts=accounts,
        emergency_target=emergency_target, emergency_pct=emergency_pct,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import balance_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(total_liquid=total_liquid, accounts=accounts,
                 emergency_target=emergency_target, emergency_pct=emergency_pct),
            "balance_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow balance_card: %s", exc)

    # 2. HTML pipeline
    _save_html("balance_card.html", html)
    h = max(500, 360 + len(accounts) * 70)
    return html, _html_to_image("balance_card.html", "balance_card.png", size=(460, h))


def render_spending_card(
    month, total_spent, categories,
    monthly_budget=50_000, date_range="25 Jul - 24 Aug",
    save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("spending_card.html")
    html = template.render(
        month=month, total_spent=total_spent, categories=categories,
        monthly_budget=monthly_budget, date_range=date_range,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import spending_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(month=month, total_spent=total_spent, categories=categories,
                 monthly_budget=monthly_budget, date_range=date_range),
            "spending_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow spending_card: %s", exc)

    # 2. HTML pipeline
    _save_html("spending_card.html", html)
    h = max(520, 380 + len(categories) * 75)
    return html, _html_to_image("spending_card.html", "spending_card.png", size=(460, h))


def render_portfolio_card(
    total_portfolio, asset_allocation,
    sips=None, growth_pct="2.4", total_sip_amount=35_000,
    save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("portfolio_card.html")
    html = template.render(
        total_portfolio=total_portfolio, asset_allocation=asset_allocation,
        sips=sips or [], growth_pct=growth_pct, total_sip_amount=total_sip_amount,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import portfolio_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(total_portfolio=total_portfolio, asset_allocation=asset_allocation,
                 sips=sips, growth_pct=growth_pct, total_sip_amount=total_sip_amount),
            "portfolio_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow portfolio_card: %s", exc)

    # 2. HTML pipeline
    _save_html("portfolio_card.html", html)
    h = max(560, 400 + len(asset_allocation) * 65 + len(sips or []) * 35)
    return html, _html_to_image("portfolio_card.html", "portfolio_card.png", size=(460, h))


def render_start_card(save_preview=True) -> tuple[str, Path | None]:
    template = env.get_template("start_card.html")
    html = template.render()
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import start_card as _pil
        img_path = _pil_bytes_to_path(_pil(), "start_card.png")
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow start_card: %s", exc)

    # 2. HTML pipeline
    _save_html("start_card.html", html)
    return html, _html_to_image("start_card.html", "start_card.png", size=(460, 560))


def render_digest_daily_card(
    date: str, total_today: float, expenses: list,
    daily_target=1600.0, save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("digest_daily_card.html")
    html = template.render(
        date=date, total_today=total_today,
        expenses=expenses, daily_target=daily_target,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import digest_daily_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(date=date, total_today=total_today,
                 expenses=expenses, daily_target=daily_target),
            "digest_daily_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow digest_daily_card: %s", exc)

    # 2. HTML pipeline
    _save_html("digest_daily_card.html", html)
    h = max(500, 360 + len(expenses) * 60)
    return html, _html_to_image("digest_daily_card.html", "digest_daily_card.png", size=(460, h))


def render_digest_monthly_card(
    month: str, total_spent: float, categories: list,
    monthly_budget=50_000, total_liquid=1_245_000, date_range="25 Jul - 24 Aug",
    save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("digest_monthly_card.html")
    top_cat  = categories[0]["name"] if categories else "General"
    html = template.render(
        month=month, total_spent=total_spent, categories=categories,
        monthly_budget=monthly_budget, total_liquid=total_liquid,
        top_category=top_cat, date_range=date_range,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import digest_monthly_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(month=month, total_spent=total_spent, categories=categories,
                 monthly_budget=monthly_budget, total_liquid=total_liquid,
                 date_range=date_range),
            "digest_monthly_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow digest_monthly_card: %s", exc)

    # 2. HTML pipeline
    _save_html("digest_monthly_card.html", html)
    h = max(540, 420 + min(len(categories), 4) * 60)
    return html, _html_to_image("digest_monthly_card.html", "digest_monthly_card.png", size=(460, h))


def render_budget_alert_card(
    category: str, amount_spent: float, limit_amount: float,
    threshold_level: int, billing_month: str,
    save_preview=True,
) -> tuple[str, Path | None]:
    template = env.get_template("budget_alert_card.html")
    pct_used  = (amount_spent / limit_amount * 100) if limit_amount > 0 else 100.0
    remaining = limit_amount - amount_spent
    html = template.render(
        category=category, amount_spent=amount_spent, limit_amount=limit_amount,
        pct_used=pct_used, threshold_level=threshold_level,
        billing_month=billing_month, remaining=remaining,
    )
    if not save_preview:
        return html, None

    # 1. Pillow
    try:
        from bot.utils.pillow_renderer import budget_alert_card as _pil
        img_path = _pil_bytes_to_path(
            _pil(category=category, amount_spent=amount_spent,
                 limit_amount=limit_amount, threshold_level=threshold_level,
                 billing_month=billing_month),
            "budget_alert_card.png",
        )
        if img_path:
            return html, img_path
    except Exception as exc:
        logger.warning("Pillow budget_alert_card: %s", exc)

    # 2. HTML pipeline
    _save_html("budget_alert_card.html", html)
    return html, _html_to_image("budget_alert_card.html", "budget_alert_card.png", size=(460, 500))
