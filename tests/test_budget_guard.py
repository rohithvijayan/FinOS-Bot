import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.utils.html_renderer import render_budget_alert_card

def test_budget_alert_rendering():
    print("Testing Smart Budget Alerts & Threshold Guards Card Generation...")

    # 1. Test 75% Warning Guard Card
    warn_html, warn_img = render_budget_alert_card(
        category="Eating Out",
        amount_spent=3750.00,
        limit_amount=5000.00,
        threshold_level=75,
        billing_month="August 2026"
    )
    assert "75% Budget Warning" in warn_html
    assert "Eating Out" in warn_html
    assert warn_img is not None and warn_img.exists()
    print("✅ 75% Warning Budget Guard Card & Image rendered successfully!")

    # 2. Test 90% Critical Guard Card
    crit_html, crit_img = render_budget_alert_card(
        category="Shopping",
        amount_spent=4650.00,
        limit_amount=5000.00,
        threshold_level=90,
        billing_month="August 2026"
    )
    assert "90% Critical Budget Cap" in crit_html
    assert "Shopping" in crit_html
    assert crit_img is not None and crit_img.exists()
    print("✅ 90% Critical Budget Guard Card & Image rendered successfully!")

if __name__ == "__main__":
    test_budget_alert_rendering()
