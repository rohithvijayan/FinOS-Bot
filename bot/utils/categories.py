"""
Utility: expense category keyword map + icons.

Mirrors the CATEGORY_ICONS and keyword logic from FinanceContext.tsx in the web app.
Used as fallback when Gemini NLP is unavailable.
"""

CATEGORY_ICONS: dict[str, str] = {
    "Rent": "🏠",
    "Utilities": "🔌",
    "Groceries": "🛒",
    "Eating Out": "🍔",
    "Transport": "🚗",
    "Entertainment": "🎬",
    "Essentials": "📦",
    "Shopping": "🛍️",
    "Self Care": "💅",
    "Investment": "📈",
    "Money Transfer": "💸",
    "Others": "🏷️",
}

UI_CATEGORIES: list[str] = list(CATEGORY_ICONS.keys())

# Keyword → category mapping (lowercase keywords)
KEYWORD_CATEGORY_MAP: dict[str, str] = {
    # Eating Out
    "zomato": "Eating Out",
    "swiggy": "Eating Out",
    "dominos": "Eating Out",
    "pizza": "Eating Out",
    "burger": "Eating Out",
    "cafe": "Eating Out",
    "coffee": "Eating Out",
    "restaurant": "Eating Out",
    "biryani": "Eating Out",
    "hotel": "Eating Out",
    "dine": "Eating Out",
    "lunch": "Eating Out",
    "dinner": "Eating Out",
    "breakfast": "Eating Out",
    "chai": "Eating Out",
    "maggi": "Eating Out",
    "noodles": "Eating Out",
    "food": "Eating Out",
    "meal": "Eating Out",
    "snack": "Eating Out",
    "mcdonalds": "Eating Out",
    "kfc": "Eating Out",
    "subway": "Eating Out",
    "barbeque": "Eating Out",
    "bbq": "Eating Out",

    # Transport
    "uber": "Transport",
    "ola": "Transport",
    "rapido": "Transport",
    "auto": "Transport",
    "cab": "Transport",
    "taxi": "Transport",
    "metro": "Transport",
    "bus": "Transport",
    "train": "Transport",
    "irctc": "Transport",
    "flight": "Transport",
    "petrol": "Transport",
    "fuel": "Transport",
    "diesel": "Transport",
    "toll": "Transport",
    "parking": "Transport",
    "redbus": "Transport",

    # Groceries
    "grocery": "Groceries",
    "groceries": "Groceries",
    "bigbasket": "Groceries",
    "blinkit": "Groceries",
    "zepto": "Groceries",
    "dmart": "Groceries",
    "vegetables": "Groceries",
    "fruits": "Groceries",
    "milk": "Groceries",
    "eggs": "Groceries",
    "supermarket": "Groceries",
    "kirana": "Groceries",

    # Utilities
    "electricity": "Utilities",
    "water": "Utilities",
    "gas": "Utilities",
    "internet": "Utilities",
    "wifi": "Utilities",
    "broadband": "Utilities",
    "recharge": "Utilities",
    "mobile": "Utilities",
    "phone": "Utilities",
    "airtel": "Utilities",
    "jio": "Utilities",
    "vi": "Utilities",
    "bsnl": "Utilities",
    "bill": "Utilities",

    # Rent
    "rent": "Rent",
    "maintenance": "Rent",
    "society": "Rent",

    # Entertainment
    "netflix": "Entertainment",
    "amazon prime": "Entertainment",
    "hotstar": "Entertainment",
    "spotify": "Entertainment",
    "youtube": "Entertainment",
    "prime": "Entertainment",
    "movie": "Entertainment",
    "cinema": "Entertainment",
    "pvr": "Entertainment",
    "inox": "Entertainment",
    "game": "Entertainment",
    "steam": "Entertainment",
    "concert": "Entertainment",
    "event": "Entertainment",
    "subscription": "Entertainment",

    # Shopping
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "ajio": "Shopping",
    "clothes": "Shopping",
    "shirt": "Shopping",
    "shoes": "Shopping",
    "fashion": "Shopping",
    "electronics": "Shopping",
    "gadget": "Shopping",

    # Self Care
    "salon": "Self Care",
    "haircut": "Self Care",
    "gym": "Self Care",
    "medicine": "Self Care",
    "pharmacy": "Self Care",
    "doctor": "Self Care",
    "hospital": "Self Care",
    "spa": "Self Care",
    "grooming": "Self Care",
    "medic": "Self Care",

    # Investment
    "sip": "Investment",
    "mutual fund": "Investment",
    "stock": "Investment",
    "zerodha": "Investment",
    "groww": "Investment",
    "mf": "Investment",
    "invest": "Investment",
    "gold": "Investment",
    "bond": "Investment",

    # Money Transfer
    "transfer": "Money Transfer",
    "upi": "Money Transfer",
    "neft": "Money Transfer",
    "rtgs": "Money Transfer",
    "send": "Money Transfer",
    "gpay": "Money Transfer",
    "phonepay": "Money Transfer",
    "paytm": "Money Transfer",

    # Essentials
    "stationery": "Essentials",
    "book": "Essentials",
    "notebook": "Essentials",
    "pen": "Essentials",
    "cleaning": "Essentials",
    "household": "Essentials",
}


def guess_category(text: str) -> str | None:
    """
    Returns the best-guess category for a text string by scanning for keywords.
    Returns None if no keyword matches.
    """
    lower = text.lower()
    for keyword, category in KEYWORD_CATEGORY_MAP.items():
        if keyword in lower:
            return category
    return None
