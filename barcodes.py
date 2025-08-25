import re

def normalize_barcode(code: str) -> str | None:
    if not code:
        return None
    v = re.sub(r"\D+", "", str(code).strip())
    if not v:
        return None
    if len(v) in (12, 13):
        return v.zfill(13)
    return v

def is_valid_ean13(code: str) -> bool:
    if not code or not re.fullmatch(r"\d{13}", code):
        return False
    digits = [int(c) for c in code]
    s = sum((3 if i % 2 else 1) * d for i, d in enumerate(digits[:-1]))
    chk = (10 - (s % 10)) % 10
    return chk == digits[-1]

def validate_barcode(code: str) -> dict:
    normalized = normalize_barcode(code)
    if not normalized:
        return {"valid": False, "normalized": None}
    return {"valid": is_valid_ean13(normalized), "normalized": normalized}
