from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


SAVE_OK_VALUES = {"OK", "SAVE OK", "SALVO", "LANCADO", "LANÇADO", "SIM", "CONCLUIDO", "CONCLUÍDO"}
GKO_OK_VALUES = {"OK", "GKO OK", "LIBERADO", "SIM", "CONCLUIDO", "CONCLUÍDO"}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    return "".join(char for char in text if not unicodedata.combining(char)).upper()


def normalize_invoice_number(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value))


def carrier_key(value: object) -> str:
    return re.sub(r"\s+", " ", normalize_text(value)).strip()


def status_is_ok(value: object, accepted: set[str]) -> bool:
    return normalize_text(value) in {normalize_text(item) for item in accepted}


def parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_amount(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = re.sub(r"[^0-9,.-]", "", str(value))
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None

