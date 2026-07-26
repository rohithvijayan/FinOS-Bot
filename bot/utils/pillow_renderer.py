"""
pillow_renderer.py — Chrome-free PNG card renderer using Pillow.
Works on Vercel serverless: no libpango, no libgobject, no Chrome required.

Fonts are downloaded from jsDelivr CDN once per cold-start and cached in /tmp.
If download fails, falls back to PIL's built-in bitmap font.
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Canvas & design constants ──────────────────────────────────────────────────
CARD_W = 920          # render at 2× then downscale to 460px (retina-quality)
PAD    = 64           # inner card padding

# Colour palette (all RGB unless noted RGBA)
BG         = (10,  10,  24)
CARD_BG    = (18,  20,  44)
CARD_BG2   = (14,  16,  36)
PURPLE     = (167, 139, 250)
PURPLE_LT  = (196, 181, 253)
TEXT_PRI   = (238, 238, 245)
TEXT_SEC   = (150, 158, 172)
TEXT_MUT   = ( 95, 104, 118)
GREEN      = ( 52, 211, 153)
YELLOW     = (251, 191,  36)
RED        = (239,  68,  68)
TEAL       = ( 45, 212, 191)
BLUE       = ( 96, 165, 250)
ORANGE     = (249, 115,  22)
PINK       = (236,  72, 153)
DIV_COLOR  = ( 34,  36,  62)
CAT_COLORS = [PURPLE, TEAL, BLUE, GREEN, YELLOW, ORANGE, PINK, (167, 243, 208)]

_FONT_CACHE: Optional[dict] = None
_FONT_DIR = Path(tempfile.gettempdir()) / "finos_fonts"

_FONTS_CDN = {
    "NotoSans-Regular": (
        "https://cdn.jsdelivr.net/gh/notofonts/noto-fonts"
        "@main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    ),
    "NotoSans-Bold": (
        "https://cdn.jsdelivr.net/gh/notofonts/noto-fonts"
        "@main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
    ),
}

_SYSTEM_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
]
_SYSTEM_REGULAR = ["NotoSans-Regular.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
_SYSTEM_BOLD    = ["NotoSans-Bold.ttf",    "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]


# ── Font loading ───────────────────────────────────────────────────────────────

def _dl_font(name: str, url: str) -> Optional[Path]:
    dst = _FONT_DIR / f"{name}.ttf"
    if dst.exists():
        return dst
    try:
        _FONT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading font {name}…")
        urllib.request.urlretrieve(url, str(dst))
        logger.info(f"Font {name} downloaded ({dst.stat().st_size // 1024} KB)")
        return dst
    except Exception as exc:
        logger.warning(f"Font download failed ({name}): {exc}")
        return None


def _find_system_font(names: list) -> Optional[Path]:
    for d in _SYSTEM_FONT_DIRS:
        for name in names:
            p = Path(d) / name
            if p.exists():
                return p
    return None


def _ttf(path: Optional[Path], size: int) -> ImageFont.FreeTypeFont:
    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _load_fonts() -> dict:
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE

    reg = (_dl_font("NotoSans-Regular", _FONTS_CDN["NotoSans-Regular"])
           or _find_system_font(_SYSTEM_REGULAR))
    bld = (_dl_font("NotoSans-Bold", _FONTS_CDN["NotoSans-Bold"])
           or _find_system_font(_SYSTEM_BOLD)
           or reg)

    _FONT_CACHE = {
        "sm":     _ttf(reg, 22),
        "body":   _ttf(reg, 28),
        "semi":   _ttf(bld, 28),
        "lg":     _ttf(bld, 36),
        "xl":     _ttf(bld, 54),
        "xxl":    _ttf(bld, 74),
        "header": _ttf(bld, 40),
        "title":  _ttf(bld, 48),
    }
    logger.info("Pillow font cache initialised (reg=%s bld=%s)", reg, bld)
    return _FONT_CACHE


# ── Helpers ────────────────────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "[\U00010000-\U0010FFFF"
    "\U00002600-\U000027BF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF]+",
    flags=re.UNICODE,
)


def _strip(text: str) -> str:
    """Remove emoji for Pillow text rendering (avoids tofu boxes with system fonts)."""
    return _EMOJI_RE.sub("", text).strip()


def _fmt_inr(val: float) -> str:
    if val >= 10_000_000:
        return f"\u20b9{val / 10_000_000:.2f}Cr"
    if val >= 100_000:
        return f"\u20b9{val / 100_000:.1f}L"
    return f"\u20b9{int(val):,}"


def _tw(draw: ImageDraw.Draw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _rr(draw: ImageDraw.Draw, box, radius: int, fill=None, outline=None, width: int = 2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _bar(draw: ImageDraw.Draw, x, y, w, h, pct, color, bg=CARD_BG2, r: int = 8):
    _rr(draw, [x, y, x + w, y + h], r, fill=bg)
    fill_w = max(r * 2, int(w * min(max(float(pct), 0.0), 1.0)))
    _rr(draw, [x, y, x + fill_w, y + h], r, fill=color)


def _divider(draw: ImageDraw.Draw, x1, y, x2):
    draw.line([(x1, y), (x2, y)], fill=DIV_COLOR, width=2)


def _badge(draw: ImageDraw.Draw, x, y, text, bg, fg=TEXT_PRI, font=None):
    f = font or _load_fonts()["sm"]
    pad_x, pad_y = 18, 9
    text = _strip(text)
    tw = _tw(draw, text, f)
    _rr(draw, [x, y, x + tw + pad_x * 2, y + 44], radius=22, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=f, fill=fg)
    return tw + pad_x * 2


def _canvas(height: int) -> tuple[Image.Image, ImageDraw.Draw]:
    img = Image.new("RGB", (CARD_W, height), BG)
    return img, ImageDraw.Draw(img)


def _card_bg(draw: ImageDraw.Draw, canvas_h: int) -> tuple[int, int, int]:
    """Draw card, return (ix, iy, ix2)."""
    m = 40
    _rr(draw, [m, m, CARD_W - m, canvas_h - m],
        radius=44, fill=CARD_BG, outline=(*PURPLE, 70), width=2)
    return m + PAD, m + PAD, CARD_W - m - PAD


def _export(img: Image.Image, content_h: int) -> bytes:
    cropped = img.crop((0, 0, CARD_W, min(content_h, img.height)))
    out = cropped.resize((CARD_W // 2, cropped.height // 2), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ── Public card renderers ──────────────────────────────────────────────────────

def balance_card(
    total_liquid: float,
    accounts: list,
    emergency_target: float = 1_000_000,
    emergency_pct: float = 85,
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        canvas_h = 480 + len(accounts) * 130 + 120
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "Liquid Balance", font=f["header"], fill=PURPLE)
        _badge(draw, ix2 - 180, y + 4, "● Live", bg=(18, 48, 32), fg=GREEN)
        y += 74

        draw.text((ix, y), _fmt_inr(total_liquid), font=f["xxl"], fill=TEXT_PRI)
        y += 104

        # Emergency fund bar
        draw.text((ix, y), "Emergency Fund", font=f["sm"], fill=TEXT_SEC)
        ep_str = f"{emergency_pct:.0f}%"
        draw.text((ix2 - _tw(draw, ep_str, f["sm"]), y), ep_str, font=f["sm"], fill=TEXT_SEC)
        y += 34
        ep_color = GREEN if emergency_pct >= 80 else (YELLOW if emergency_pct >= 50 else RED)
        _bar(draw, ix, y, bw, 16, emergency_pct / 100, ep_color, r=8)
        y += 56
        _divider(draw, ix, y, ix2)
        y += 44

        for acct in accounts:
            # bank_name is the primary label (e.g. "HDFC", "SBI")
            bank  = _strip(acct.get("bank_name") or acct.get("name") or "Bank")
            aname = _strip(acct.get("name") or "")
            bal   = acct.get("balance", 0)
            rate  = acct.get("interest_rate", 0)
            amt_s = _fmt_inr(bal)

            # Bank name (primary, large)
            draw.text((ix, y), bank, font=f["semi"], fill=TEXT_PRI)
            draw.text((ix2 - _tw(draw, amt_s, f["semi"]), y), amt_s, font=f["semi"], fill=PURPLE_LT)
            y += 42
            # Account name + interest rate (subtitle)
            sub_parts = [aname] if aname and aname != bank else []
            if rate:
                sub_parts.append(f"{rate}% p.a.")
            sub = "  ·  ".join(sub_parts) if sub_parts else "Savings Account"
            draw.text((ix, y), sub, font=f["sm"], fill=TEXT_MUT)
            y += 52
            _divider(draw, ix, y, ix2)
            y += 36

        y += 12
        _badge(draw, ix, y, "All systems normal", bg=(18, 48, 32), fg=GREEN)
        y += 80

        return _export(img, y + 50)
    except Exception as exc:
        logger.error("Pillow balance_card: %s", exc, exc_info=True)
        return None


def spending_card(
    month: str,
    total_spent: float,
    categories: list,
    monthly_budget: float = 50_000,
    date_range: str = "",
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        canvas_h = 600 + len(categories) * 116 + 100
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "Monthly Spending", font=f["header"], fill=PURPLE)
        y += 62
        sub = f"{month}  ·  {date_range}" if date_range else month
        draw.text((ix, y), sub, font=f["sm"], fill=TEXT_SEC)
        y += 80

        draw.text((ix, y), _fmt_inr(total_spent), font=f["xxl"], fill=TEXT_PRI)
        y += 96
        draw.text((ix, y), f"of {_fmt_inr(monthly_budget)} budget", font=f["body"], fill=TEXT_SEC)
        y += 58

        pct = total_spent / monthly_budget if monthly_budget else 0
        bar_c = RED if pct > 0.9 else (YELLOW if pct > 0.75 else PURPLE)
        _bar(draw, ix, y, bw, 20, pct, bar_c, r=10)
        lbl = f"{pct * 100:.0f}%"
        draw.text((ix2 - _tw(draw, lbl, f["sm"]), y - 30), lbl, font=f["sm"], fill=bar_c)
        y += 66
        _divider(draw, ix, y, ix2)
        y += 44

        for i, cat in enumerate(categories):
            color = CAT_COLORS[i % len(CAT_COLORS)]
            name  = _strip(cat.get("name", "Other"))
            amt   = cat.get("amount", 0)
            pct_c = amt / total_spent if total_spent else 0
            amt_s = _fmt_inr(amt)

            draw.text((ix, y), name, font=f["semi"], fill=TEXT_PRI)
            draw.text((ix2 - _tw(draw, amt_s, f["semi"]), y), amt_s, font=f["semi"], fill=color)
            y += 48
            _bar(draw, ix + 36, y, bw - 36, 10, pct_c, color, bg=(28, 30, 56), r=5)
            ps = f"{pct_c * 100:.0f}%"
            draw.text((ix2 - _tw(draw, ps, f["sm"]), y - 22), ps, font=f["sm"], fill=TEXT_MUT)
            y += 50
            _divider(draw, ix, y, ix2)
            y += 34

        return _export(img, y + 56)
    except Exception as exc:
        logger.error("Pillow spending_card: %s", exc, exc_info=True)
        return None


def digest_daily_card(
    date: str,
    total_today: float,
    expenses: list,
    daily_target: float = 1600.0,
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        n_exp = min(len(expenses), 8)
        canvas_h = 600 + n_exp * 112 + 100
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "Daily Digest", font=f["header"], fill=PURPLE)
        y += 62
        draw.text((ix, y), date, font=f["sm"], fill=TEXT_SEC)
        y += 80

        pct = total_today / daily_target if daily_target else 0
        status_c = RED if pct > 1.0 else (YELLOW if pct > 0.75 else GREEN)
        draw.text((ix, y), _fmt_inr(total_today), font=f["xxl"], fill=status_c)
        y += 96
        draw.text((ix, y), f"Daily target: {_fmt_inr(daily_target)}", font=f["body"], fill=TEXT_SEC)
        y += 58
        _bar(draw, ix, y, bw, 20, pct, status_c, r=10)
        y += 66
        _divider(draw, ix, y, ix2)
        y += 44

        for exp in expenses[:8]:
            merchant = _strip(exp.get("merchant") or exp.get("description", "Unknown"))
            amt      = exp.get("amount", 0)
            cat      = _strip(exp.get("category", ""))
            time_s   = exp.get("time", "")
            amt_s    = _fmt_inr(amt)

            draw.text((ix, y), merchant, font=f["semi"], fill=TEXT_PRI)
            draw.text((ix2 - _tw(draw, amt_s, f["semi"]), y), amt_s, font=f["semi"], fill=PURPLE_LT)
            y += 44
            sub = f"{cat}  ·  {time_s}".strip(" ·")
            if sub:
                draw.text((ix, y), sub, font=f["sm"], fill=TEXT_MUT)
            y += 50
            _divider(draw, ix, y, ix2)
            y += 34

        return _export(img, y + 56)
    except Exception as exc:
        logger.error("Pillow digest_daily_card: %s", exc, exc_info=True)
        return None


def digest_monthly_card(
    month: str,
    total_spent: float,
    categories: list,
    monthly_budget: float = 50_000,
    total_liquid: float = 0,
    date_range: str = "",
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        n_cat = min(len(categories), 5)
        canvas_h = 680 + n_cat * 116 + 100
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "Monthly Report", font=f["header"], fill=PURPLE)
        y += 62
        sub = f"{month}  ·  {date_range}" if date_range else month
        draw.text((ix, y), sub, font=f["sm"], fill=TEXT_SEC)
        y += 80

        draw.text((ix, y), _fmt_inr(total_spent), font=f["xxl"], fill=TEXT_PRI)
        y += 96
        draw.text((ix, y), f"of {_fmt_inr(monthly_budget)} budget", font=f["body"], fill=TEXT_SEC)
        y += 58

        pct = total_spent / monthly_budget if monthly_budget else 0
        bar_c = RED if pct > 0.9 else (YELLOW if pct > 0.75 else PURPLE)
        _bar(draw, ix, y, bw, 20, pct, bar_c, r=10)
        y += 56

        if total_liquid:
            y += 30
            draw.text((ix, y), f"Liquid balance: {_fmt_inr(total_liquid)}", font=f["body"], fill=TEXT_SEC)
            y += 48

        _divider(draw, ix, y, ix2)
        y += 44

        for i, cat in enumerate(categories[:5]):
            color = CAT_COLORS[i % len(CAT_COLORS)]
            name  = _strip(cat.get("name", "Other"))
            amt   = cat.get("amount", 0)
            pct_c = amt / total_spent if total_spent else 0
            amt_s = _fmt_inr(amt)

            draw.text((ix, y), name, font=f["semi"], fill=TEXT_PRI)
            draw.text((ix2 - _tw(draw, amt_s, f["semi"]), y), amt_s, font=f["semi"], fill=color)
            y += 48
            _bar(draw, ix + 36, y, bw - 36, 10, pct_c, color, bg=(28, 30, 56), r=5)
            y += 50
            _divider(draw, ix, y, ix2)
            y += 34

        return _export(img, y + 56)
    except Exception as exc:
        logger.error("Pillow digest_monthly_card: %s", exc, exc_info=True)
        return None


def expense_card(
    amount: float,
    category: str,
    merchant: str,
    billing_month: str,
    date: str,
    account: Optional[str] = None,
    is_confirmed: bool = False,
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        canvas_h = 760
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        status_text  = "Expense Saved" if is_confirmed else "Confirm Expense"
        status_color = GREEN if is_confirmed else YELLOW
        draw.text((ix, y), status_text, font=f["header"], fill=status_color)
        y += 74

        draw.text((ix, y), _fmt_inr(amount), font=f["xxl"], fill=TEXT_PRI)
        y += 104
        _divider(draw, ix, y, ix2)
        y += 44

        rows = [
            ("Merchant",      _strip(merchant)),
            ("Category",      _strip(category)),
            ("Date",          date),
            ("Billing Month", billing_month),
        ]
        if account:
            rows.append(("Account", _strip(account)))

        for label, value in rows:
            draw.text((ix, y), label, font=f["body"], fill=TEXT_SEC)
            draw.text((ix2 - _tw(draw, value, f["semi"]), y), value, font=f["semi"], fill=TEXT_PRI)
            y += 62
            _divider(draw, ix, y, ix2)
            y += 24

        if is_confirmed:
            y += 24
            _badge(draw, ix, y, "Saved to Supabase", bg=(18, 48, 32), fg=GREEN)

        return _export(img, y + 100)
    except Exception as exc:
        logger.error("Pillow expense_card: %s", exc, exc_info=True)
        return None


def _table_header(draw, ix, y, ix2, f, col_widths: list, labels: list, label_color=TEXT_SEC):
    """Draw column headers for investment table."""
    x = ix
    for i, (label, w) in enumerate(zip(labels, col_widths)):
        if i == 0:
            draw.text((x, y), label, font=f["sm"], fill=label_color)
        else:
            tw = _tw(draw, label, f["sm"])
            draw.text((x + w - tw, y), label, font=f["sm"], fill=label_color)
        x += w
    return y + 36


def _table_row(draw, ix, y, ix2, f, col_widths: list, values: list,
               name_color=TEXT_PRI, val_color=PURPLE_LT, ret_color=None):
    """Draw one investment table row."""
    x = ix
    for i, (val, w) in enumerate(zip(values, col_widths)):
        if i == 0:
            # Name: truncate if too long
            max_chars = w // 14
            truncated = val if len(val) <= max_chars else val[:max_chars - 1] + "…"
            draw.text((x, y), truncated, font=f["sm"], fill=name_color)
        else:
            color = (ret_color if ret_color and i == len(values) - 1 else val_color)
            tw = _tw(draw, str(val), f["sm"])
            draw.text((x + w - tw, y), str(val), font=f["sm"], fill=color)
        x += w
    return y + 44


def portfolio_card(
    total_portfolio: float,
    asset_allocation: list,
    sips: Optional[list] = None,
    bonds: Optional[list] = None,
    growth_pct: str = "2.4",
    total_sip_amount: float = 35_000,
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        sips  = sips  or []
        bonds = bonds or []
        n_rows = len(sips) + len(bonds)
        canvas_h = 600 + len(asset_allocation) * 90 + n_rows * 56 + 300
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "Investment Portfolio", font=f["header"], fill=PURPLE)
        y += 74

        draw.text((ix, y), _fmt_inr(total_portfolio), font=f["xxl"], fill=TEXT_PRI)
        y += 96
        # Clean up growth % — ensure max 2 decimal places
        try:
            g_val = float(growth_pct)
            g_text = f"+{g_val:.2f}% overall return"
        except ValueError:
            g_text = f"+{growth_pct}% overall return"
        draw.text((ix, y), g_text, font=f["body"], fill=GREEN)
        y += 62
        _divider(draw, ix, y, ix2)
        y += 44

        # ── Asset Allocation summary ──────────────────────────────────────────
        draw.text((ix, y), "Asset Allocation", font=f["lg"], fill=TEXT_SEC)
        y += 54

        for i, asset in enumerate(asset_allocation):
            color = CAT_COLORS[i % len(CAT_COLORS)]
            name  = _strip(asset.get("name", "Asset"))
            amt   = asset.get("amount", 0)
            pct   = float(asset.get("pct", 0))
            amt_s = _fmt_inr(amt)
            ps    = f"{pct:.1f}%"

            draw.text((ix, y), name, font=f["semi"], fill=TEXT_PRI)
            # amount + pct on the right
            right_str = f"{amt_s}  {ps}"
            draw.text((ix2 - _tw(draw, right_str, f["semi"]), y), right_str, font=f["semi"], fill=color)
            y += 46
            _bar(draw, ix + 32, y, bw - 32, 12, pct / 100, color, bg=(28, 30, 56), r=6)
            y += 50
            _divider(draw, ix, y, ix2)
            y += 28

        # ── Mutual Funds / SIPs table ─────────────────────────────────────────
        if sips:
            y += 20
            draw.text((ix, y), "Mutual Funds & SIPs", font=f["lg"], fill=TEXT_SEC)
            y += 56

            # Column widths:  Name | Invested | Current | Return
            C = [bw - 370, 120, 120, 130]  # sum = bw
            y = _table_header(draw, ix, y, ix2, f, C,
                              ["Fund", "Invested", "Current", "Return"])
            _divider(draw, ix, y, ix2)
            y += 16

            for sip in sips:
                name  = _strip(sip.get("name", "SIP"))
                inv   = _fmt_inr(float(sip.get("invested", 0)))
                cur   = _fmt_inr(float(sip.get("current_value", 0)))
                ret   = str(sip.get("return_pct", "—"))
                # colour return green/red
                try:
                    ret_f = float(ret.strip("%"))
                    rc = GREEN if ret_f >= 0 else RED
                    ret = f"+{ret_f:.1f}%" if ret_f >= 0 else f"{ret_f:.1f}%"
                except (ValueError, AttributeError):
                    rc = TEXT_SEC

                y = _table_row(draw, ix, y, ix2, f, C, [name, inv, cur, ret],
                               ret_color=rc)
                _divider(draw, ix, y, ix2)
                y += 14

        # ── Bonds table ───────────────────────────────────────────────────────
        if bonds:
            y += 24
            draw.text((ix, y), "Bonds & Debt", font=f["lg"], fill=TEAL)
            y += 56

            CB = [bw - 350, 130, 130, 90]  # Name | Invested | Current | YTM
            y = _table_header(draw, ix, y, ix2, f, CB,
                              ["Bond", "Invested", "Current", "YTM"])
            _divider(draw, ix, y, ix2)
            y += 16

            for bond in bonds:
                name = _strip(bond.get("name", "Bond"))
                inv  = _fmt_inr(float(bond.get("invested", 0)))
                cur  = _fmt_inr(float(bond.get("current_value", 0)))
                ytm  = str(bond.get("ytm", "—"))
                y = _table_row(draw, ix, y, ix2, f, CB, [name, inv, cur, ytm],
                               val_color=TEAL)
                _divider(draw, ix, y, ix2)
                y += 14

        return _export(img, y + 70)
    except Exception as exc:
        logger.error("Pillow portfolio_card: %s", exc, exc_info=True)
        return None


def budget_alert_card(
    category: str,
    amount_spent: float,
    limit_amount: float,
    threshold_level: int,
    billing_month: str,
) -> Optional[bytes]:
    try:
        f = _load_fonts()
        canvas_h = 900
        img, draw = _canvas(canvas_h)

        m = 40
        alert_c  = YELLOW if threshold_level == 75 else RED
        card_fill = (38, 28,  8) if threshold_level == 75 else (38, 10, 10)
        _rr(draw, [m, m, CARD_W - m, canvas_h - m],
            radius=44, fill=card_fill, outline=(*alert_c, 130), width=3)

        ix, iy, ix2 = m + PAD, m + PAD, CARD_W - m - PAD
        bw = ix2 - ix
        y  = iy

        lbl = "Budget Warning" if threshold_level == 75 else "Budget Critical"
        draw.text((ix, y), lbl, font=f["header"], fill=alert_c)
        y += 62
        draw.text((ix, y), billing_month, font=f["sm"], fill=TEXT_SEC)
        y += 90

        draw.text((ix, y), _strip(category), font=f["xxl"], fill=TEXT_PRI)
        y += 104

        pct  = (amount_spent / limit_amount * 100) if limit_amount else 100
        ps   = f"{pct:.0f}% used"
        draw.text((ix, y), ps, font=f["xl"], fill=alert_c)
        y += 84

        _bar(draw, ix, y, bw, 24, pct / 100, alert_c, bg=(40, 40, 40), r=12)
        y += 72
        _divider(draw, ix, y, ix2)
        y += 44

        remaining = limit_amount - amount_spent
        rows = [
            ("Spent",     _fmt_inr(amount_spent),    TEXT_PRI),
            ("Limit",     _fmt_inr(limit_amount),    TEXT_SEC),
            ("Remaining", _fmt_inr(abs(remaining)),  GREEN if remaining > 0 else RED),
        ]
        for label, val, col in rows:
            draw.text((ix, y), label, font=f["body"], fill=TEXT_SEC)
            draw.text((ix2 - _tw(draw, val, f["semi"]), y), val, font=f["semi"], fill=col)
            y += 64

        return _export(img, y + 80)
    except Exception as exc:
        logger.error("Pillow budget_alert_card: %s", exc, exc_info=True)
        return None


def start_card() -> Optional[bytes]:
    try:
        f = _load_fonts()
        canvas_h = 760
        img, draw = _canvas(canvas_h)
        ix, iy, ix2 = _card_bg(draw, canvas_h - 44)
        bw = ix2 - ix

        y = iy
        draw.text((ix, y), "FinOS Bot", font=f["title"], fill=PURPLE_LT)
        y += 80
        draw.text((ix, y), "Personal Finance OS", font=f["lg"], fill=TEXT_SEC)
        y += 90
        _divider(draw, ix, y, ix2)
        y += 50

        features = [
            "Liquid Balance — real-time account overview",
            "Monthly Spending — category breakdown & budget",
            "Investment Portfolio — assets & SIP tracker",
            "Daily Digest — daily spend tracker",
            "AI Expense Entry — natural language input",
            "PDF Import — bank statement parser",
            "Smart Budget Alerts — 75% & 90% guards",
        ]
        for feat in features:
            draw.text((ix, y), feat, font=f["body"], fill=TEXT_PRI)
            y += 58

        return _export(img, y + 80)
    except Exception as exc:
        logger.error("Pillow start_card: %s", exc, exc_info=True)
        return None
