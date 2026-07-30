"""
PDF Bank & Credit Card Statement Parser.

Extracts text from uploaded PDF statement files using pypdf and pdfplumber,
and parses debit transactions into structured FinOS expense objects.
"""
from __future__ import annotations

import io
import json
import re
import logging
from datetime import datetime, date
from typing import Any

import pypdf
import google.generativeai as genai

from bot.config import GEMINI_API_KEY, GEMINI_MODEL
from bot.utils.categories import UI_CATEGORIES, guess_category
from bot.handlers.spending import _get_billing_month, _SHORT_MONTHS, _parse_expense_date

logger = logging.getLogger(__name__)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract full text from PDF file bytes using pypdf."""
    text_chunks = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_chunks.append(t)
    except Exception as exc:
        logger.error("pypdf extraction failed: %s", exc)

    full_text = "\n".join(text_chunks).strip()
    if not full_text:
        # Fallback to pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_chunks.append(t)
            full_text = "\n".join(text_chunks).strip()
        except Exception as exc:
            logger.error("pdfplumber extraction failed: %s", exc)

    return full_text


_BULK_PARSER_PROMPT = """\
You are a precision personal finance parser.
Analyze the following bank statement / credit card statement text and extract ALL OUTGOING SPENDS / DEBIT TRANSACTIONS.

CRITICAL RULES:
1. IGNORE incoming credits, "Received from" entries, refunds, summary headers (e.g. "Total amount due", "GST details", "Statement summary").
2. EXTRACT ONLY actual spends / outgoing debit transactions.
3. Available Categories (Choose EXACTLY ONE):
{categories}

4. Format dates as "DD-MMM-YYYY" (e.g., "10-Jul-2026", "07-Jun-2026", "04-Jul-2026"). If year is 26, use 2026.
5. Respond ONLY with a valid JSON array of objects:
[
  {{
    "amount": <number, absolute positive float (no negative signs)>,
    "description": "<merchant or payee name, max 40 chars>",
    "category": "<one of available categories>",
    "date": "<DD-MMM-YYYY format>"
  }}
]
""".format(categories="\n".join(f"  - {c}" for c in UI_CATEGORIES))


async def parse_pdf_statement_transactions(pdf_text: str) -> list[dict[str, Any]]:
    """
    Parse PDF statement text into a list of expense dictionaries.
    Uses Gemini API if available, with robust local regex parser fallback.
    """
    if not pdf_text or not pdf_text.strip():
        return []

    if _model:
        try:
            res = await _model.generate_content_async(
                f"{_BULK_PARSER_PROMPT}\n\nBank Statement Text:\n{pdf_text}"
            )
            raw = res.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed_list = json.loads(raw)
            
            validated = []
            for item in parsed_list:
                amt = abs(float(item.get("amount", 0)))
                desc = str(item.get("description", "Expense")).strip()
                cat = str(item.get("category", "Others")).strip()
                dt_str = str(item.get("date", "")).strip()

                if amt == 0:
                    continue
                if cat not in UI_CATEGORIES:
                    cat = guess_category(desc) or "Others"
                
                dt_fmt = _normalize_date_str(dt_str)
                d_obj = _parse_expense_date(dt_fmt) or date.today()
                month_label = _get_billing_month(d_obj)
                
                validated.append({
                    "amount": amt,
                    "description": desc[:40],
                    "category": cat,
                    "date": dt_fmt,
                    "month": month_label
                })
            return validated

        except Exception as exc:
            logger.warning("Gemini bulk PDF parse failed (%s), using local statement parser.", exc)

    return _local_regex_statement_parser(pdf_text)


def _normalize_date_str(d_str: str) -> str:
    """Normalize various date formats ('10 Jul '26', '07 Jun, 2026', '2026-07-10') to 'DD-MMM-YYYY'."""
    d_str = d_str.replace("•", "").replace("UPI", "").replace("Card", "").replace(",", " ").strip()
    
    # Try parsing '10 Jul 26' or '10 Jul 2026'
    m1 = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+['\s]?(\d{2,4})", d_str)
    if m1:
        day, mon, yr = m1.groups()
        if len(yr) == 2:
            yr = "20" + yr
        mon_title = mon.capitalize()[:3]
        return f"{int(day):02d}-{mon_title}-{yr}"

    # Try parsing '2026-07-10'
    m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", d_str)
    if m2:
        yr, mo, da = m2.groups()
        mon_title = _SHORT_MONTHS[int(mo) - 1]
        return f"{int(da):02d}-{mon_title}-{yr}"

    return date.today().strftime("%d-%b-%Y")


def _local_regex_statement_parser(text: str) -> list[dict[str, Any]]:
    """Local fallback parser for statement text (handles Slice & Google Pay patterns)."""
    results = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Skip lines until Spends or Transaction details section
    in_spends_section = True
    in_refunds_section = False

    for i, line in enumerate(lines):
        if "Refunds & repayments" in line or "Received from" in line:
            in_refunds_section = True
            continue
        if "Spends" in line and not "Statement summary" in line:
            in_refunds_section = False
            in_spends_section = True
            continue
        if in_refunds_section:
            continue

        amt_match = re.search(r"₹\s*([\d,]+(?:\.\d{1,2})?)", line)
        neg_match = re.search(r"(?:^|\s)-\s*([\d,]+(?:\.\d{2}))(?:\s|$)", line)
        
        amt = 0.0
        if amt_match:
            amt = float(amt_match.group(1).replace(",", ""))
        elif neg_match:
            amt = float(neg_match.group(1).replace(",", ""))

        if amt > 0:
            desc = "Expense"
            dt_str = date.today().strftime("%d-%b-%Y")

            if neg_match:
                # Tabular pattern: look for merchant at the start of line or previous line
                prefix = line[:neg_match.start()].strip()
                prefix = re.sub(r"(?i)\b(HSBC|HDFC|ICICI|SBI|AXIS|SLICE|BANK|CREDIT|CARD|RUPAY|VISA|MASTERCARD)\b.*", "", prefix).strip()
                if prefix and len(prefix) > 2 and not prefix.isdigit():
                    desc = prefix
                else:
                    if i > 0:
                        prev = lines[i-1]
                        prev = re.sub(r"(?i)\b(HSBC|HDFC|ICICI|SBI|AXIS|SLICE|BANK|CREDIT|CARD|RUPAY|VISA|MASTERCARD)\b.*", "", prev).strip()
                        if prev and len(prev) > 2:
                            desc = prev
                
                # Find date in context
                context_lines = lines[max(0, i - 3):i+2]
                for cline in reversed(context_lines):
                    if re.search(r"\d{1,2}\s+[A-Za-z]{3}", cline) or re.search(r"\d{4}-\d{2}-\d{2}", cline):
                        dt_str = _normalize_date_str(cline)
                        break
            else:
                for k in range(max(0, i - 3), i):
                    prev_line = lines[k]
                    if re.search(r"\d{1,2}\s+[A-Za-z]{3}", prev_line):
                        dt_str = _normalize_date_str(prev_line)
                    elif not re.search(r"₹|UPI|Card|Spends|Summary", prev_line) and len(prev_line) < 35:
                        desc = prev_line

            if desc not in ["Total amount due", "Spends", "Earned", "Min amount due"]:
                cat = guess_category(desc) or "Others"
                d_obj = _parse_expense_date(dt_str) or date.today()
                month_label = _get_billing_month(d_obj)

                results.append({
                    "amount": amt,
                    "description": desc[:40],
                    "category": cat,
                    "date": dt_str,
                    "month": month_label
                })

    return results
