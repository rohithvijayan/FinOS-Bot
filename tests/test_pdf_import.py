import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.utils.pdf_parser import _local_regex_statement_parser, _normalize_date_str

def test_date_normalization():
    print("Testing Date Normalization...")
    assert _normalize_date_str("10 Jul '26 • UPI") == "10-Jul-2026"
    assert _normalize_date_str("07 Jun, 2026") == "07-Jun-2026"
    assert _normalize_date_str("04 Jul 26") == "04-Jul-2026"
    print("✅ Date Normalization passed!")

def test_local_slice_statement_parser():
    print("Testing Slice Statement Parser...")
    sample_slice_text = """
Statement summary
Spends ₹1,566.06
Refunds & repayments ₹2.00
11 JUN - 10 JUL

Spends
Vi Prepaid
10 Jul '26 • UPI
₹26

Zomato
10 Jul '26 • UPI
₹87.75

Pick n
8 Jul '26 • UPI
₹70

Refunds & repayments
Amazon
6 Jul '26
₹2
"""
    parsed = _local_regex_statement_parser(sample_slice_text)
    assert len(parsed) == 3
    assert parsed[0]["description"] == "Vi Prepaid"
    assert parsed[0]["amount"] == 26.0
    assert parsed[0]["category"] == "Utilities"
    
    assert parsed[1]["description"] == "Zomato"
    assert parsed[1]["amount"] == 87.75
    assert parsed[1]["category"] == "Eating Out"

    print("✅ Slice Statement Parsing passed!")

if __name__ == "__main__":
    test_date_normalization()
    test_local_slice_statement_parser()
