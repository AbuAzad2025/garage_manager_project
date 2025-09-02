# barcodes.py
import re

def compute_ean13_check_digit(code12: str) -> int:
    if not re.fullmatch(r"\d{12}", code12):
        raise ValueError("EAN-13 base must be exactly 12 digits")
    s = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(code12))
    return (10 - (s % 10)) % 10

def normalize_barcode(code: str) -> str | None:
    """
    - ينزع أي رموز غير رقمية
    - 12 رقم  -> يُرجِع 13 بعد إضافة check digit
    - 13 رقم  -> يُرجِعها كما هي
    - غير ذلك -> None
    """
    if not code:
        return None
    v = re.sub(r"\D+", "", str(code).strip())
    if not v:
        return None
    if len(v) == 12:
        return v + str(compute_ean13_check_digit(v))
    if len(v) == 13:
        return v
    return None

def is_valid_ean13(code: str) -> bool:
    v = re.sub(r"\D+", "", str(code).strip())
    if not re.fullmatch(r"\d{13}", v):
        return False
    return int(v[-1]) == compute_ean13_check_digit(v[:-1])

def validate_barcode(code: str) -> dict:
    """
    return:
      {"valid": bool, "normalized": str|None, "suggested": str|None}
    """
    raw = re.sub(r"\D+", "", str(code or "").strip())
    if not raw:
        return {"valid": False, "normalized": None, "suggested": None}
    if len(raw) == 12:
        normalized = raw + str(compute_ean13_check_digit(raw))
        return {"valid": True, "normalized": normalized, "suggested": None}
    if len(raw) == 13:
        ok = is_valid_ean13(raw)
        suggested = raw[:-1] + str(compute_ean13_check_digit(raw[:-1])) if not ok else None
        return {"valid": ok, "normalized": raw, "suggested": suggested}
    return {"valid": False, "normalized": None, "suggested": None}
