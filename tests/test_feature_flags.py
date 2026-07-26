import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_copilot_feature_flag():
    print("Testing ENABLE_COPILOT Feature Flag...")

    # 1. Test Enabled State
    import bot.config as config
    config.ENABLE_COPILOT = True

    from bot.main import get_main_reply_keyboard
    kb_enabled = get_main_reply_keyboard()
    button_texts_enabled = [btn.text for row in kb_enabled.keyboard for btn in row]
    assert "🤖 Copilot" in button_texts_enabled
    print("✅ ENABLE_COPILOT=True displays Copilot in main reply keyboard.")

    # 2. Test Disabled State
    config.ENABLE_COPILOT = False
    kb_disabled = get_main_reply_keyboard()
    button_texts_disabled = [btn.text for row in kb_disabled.keyboard for btn in row]
    assert "🤖 Copilot" not in button_texts_disabled
    print("✅ ENABLE_COPILOT=False hides Copilot from main reply keyboard.")

    # Reset
    config.ENABLE_COPILOT = True

if __name__ == "__main__":
    test_copilot_feature_flag()
