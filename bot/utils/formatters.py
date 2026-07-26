"""Formatters — build message strings sent to the user."""
from datetime import datetime
from bot.utils.categories import CATEGORY_ICONS


def fmt_inr(amount: float) -> str:
    """Format a number as Indian rupees with thousand-separators."""
    # Use Indian numbering: 1,00,000 style
    s = f"{abs(amount):,.2f}"
    # Re-format using Indian locale logic
    parts = f"{abs(amount):.2f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) <= 3:
        formatted = integer_part
    else:
        # Last 3 digits, then groups of 2
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        formatted = ",".join(groups) + "," + last3

    sign = "-" if amount < 0 else ""
    return f"{sign}₹{formatted}.{decimal_part}"


def build_expense_preview(amount: float, description: str, category: str, date: str) -> str:
    """Build the confirmation message shown before saving an expense."""
    icon = CATEGORY_ICONS.get(category, "🏷️")
    return (
        f"📝 *Expense Preview*\n\n"
        f"💰 Amount: *{fmt_inr(amount)}*\n"
        f"📌 Category: *{icon} {category}*\n"
        f"🗒️ Description: *{description}*\n"
        f"📅 Date: *{date}*\n\n"
        f"Save this expense?"
    )


def build_balance_message(accounts: list[dict]) -> str:
    """Format savings accounts into a readable balance summary."""
    if not accounts:
        return "💳 No savings accounts found in your FinOS data."

    total = sum(a["balance"] for a in accounts)
    lines = ["💳 *Liquid Balance*\n"]
    for acc in accounts:
        bar = _mini_bar(acc["balance"], total)
        lines.append(
            f"  {bar} *{acc['name']}* ({acc['bank_name']})\n"
            f"      {fmt_inr(acc['balance'])}  •  {acc['interest_rate']}% p.a.\n"
        )
    lines.append(f"\n💵 *Total: {fmt_inr(total)}*")
    return "\n".join(lines)


def build_spending_message(month: str, expenses: list[dict], budgets: dict[str, float]) -> str:
    """Format monthly spending into a category breakdown card."""
    if not expenses:
        return f"🧾 No expenses found for *{month}*."

    total = sum(e["amount"] for e in expenses)

    # Aggregate by category
    by_cat: dict[str, float] = {}
    for e in expenses:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]

    sorted_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)

    lines = [f"🧾 *Spending — {month}*\n", f"Total: *{fmt_inr(total)}*\n"]
    for cat, amt in sorted_cats:
        icon = CATEGORY_ICONS.get(cat, "🏷️")
        pct = (amt / total * 100) if total else 0
        bar = _spend_bar(pct)
        budget_str = ""
        if cat in budgets and budgets[cat] > 0:
            budget_pct = amt / budgets[cat] * 100
            budget_str = f"  [{budget_pct:.0f}% of budget]"
        lines.append(f"{bar} {icon} *{cat}*{budget_str}\n      {fmt_inr(amt)}  ({pct:.1f}%)\n")

    return "\n".join(lines)


def build_portfolio_message(summary: dict, sips: list[dict], bonds: list[dict]) -> str:
    """Format portfolio overview card."""
    lines = ["📊 *Portfolio Overview*\n"]

    if summary:
        gain_sign = "+" if summary.get("total_gain", 0) >= 0 else ""
        lines += [
            f"💰 Invested:      *{fmt_inr(summary['total_invested'])}*",
            f"📈 Current Value: *{fmt_inr(summary['current_value'])}*",
            f"📊 Gain/Loss:     *{gain_sign}{fmt_inr(summary['total_gain'])}* ({summary['return_pct']:.2f}%)",
            f"🔁 Monthly SIP:   *{fmt_inr(summary['monthly_sip'])}*",
            "",
        ]

    if sips:
        lines.append("🏦 *Active SIPs*")
        active = [s for s in sips if str(s.get("active", "")).lower() == "yes"]
        for s in active[:5]:  # show top 5
            gain_sign = "+" if s.get("gain_loss", 0) >= 0 else ""
            lines.append(
                f"  • *{s['name']}*\n"
                f"      Invested: {fmt_inr(s['invested'])}  →  "
                f"Now: {fmt_inr(s['current_value'])}  "
                f"({gain_sign}{fmt_inr(s['gain_loss'])})"
            )
        if len(active) > 5:
            lines.append(f"  _...and {len(active) - 5} more_")
        lines.append("")

    if bonds:
        total_bond_invested = sum(b.get("invested", 0) for b in bonds)
        total_bond_value = sum(b.get("current_value", 0) for b in bonds)
        lines += [
            f"📜 *Bonds*  ({len(bonds)} holdings)",
            f"  Invested: {fmt_inr(total_bond_invested)}  →  Now: {fmt_inr(total_bond_value)}",
        ]

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _mini_bar(value: float, total: float, width: int = 8) -> str:
    pct = value / total if total else 0
    filled = round(pct * width)
    return "█" * filled + "░" * (width - filled)


def _spend_bar(pct: float, width: int = 6) -> str:
    filled = round(min(pct, 100) / 100 * width)
    return "█" * filled + "░" * (width - filled)
