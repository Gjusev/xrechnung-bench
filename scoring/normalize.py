"""Value normalization for exact-match scoring.

Discipline carried over from Gjusev/locale-invoice-check: Decimal-based
amount comparison with a +-0.01 tolerance, dates normalized to ISO 8601,
IBANs/VAT ids stripped of spaces and uppercased, names casefolded.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT_TOLERANCE = Decimal("0.01")


def to_decimal(value) -> Decimal | None:
    """Parse a number-ish string; accept German (1.234,56) and EN (1,234.56)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    s = s.replace("EUR", "").replace("€", "").strip()
    neg = s.startswith("-")
    s = s.lstrip("+-")
    if s.count(",") == 1 and s.count(".") <= 1 and "," == s[-3:-2]:
        # German format 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    elif s.count(",") > 1 and "." not in s:
        s = s.replace(",", "")  # thousands-only commas
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


def amounts_equal(a, b, tolerance=AMOUNT_TOLERANCE) -> bool:
    da, db = to_decimal(a), to_decimal(b)
    if da is None or db is None:
        return da is None and db is None
    return abs(da - db) <= tolerance


def normalize_date(value) -> str | None:
    """Normalize to ISO YYYY-MM-DD. Accepts ISO and German DD.MM.YYYY."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y%m%d", "%d. %B %Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def normalize_iban(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().replace(" ", "").replace("-", "").upper()
    return s or None


def normalize_vat_id(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().replace(" ", "").upper()
    return s or None


def normalize_text(value) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s.casefold() or None


def normalize_code(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def normalize_number(value) -> str | None:
    """Quantities/rates: compare numerically, render canonically."""
    d = to_decimal(value)
    if d is None:
        return None
    return str(d.normalize())
