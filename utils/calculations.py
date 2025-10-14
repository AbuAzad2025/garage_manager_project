# calculations.py - Unified Calculation Functions
# Location: /garage_manager/utils/calculations.py
# Description: Centralized calculation and decimal handling functions

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Constants
TWOPLACES = Decimal("0.01")
ZERO_PLACES = Decimal("1")

def D(x):
    """
    Convert any value to Decimal safely
    Handles None, strings, numbers, and existing Decimals
    """
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

def q0(x):
    """
    Round to zero decimal places (whole numbers)
    """
    return D(x).quantize(ZERO_PLACES, rounding=ROUND_HALF_UP)

def q2(x):
    """
    Round to two decimal places (currency precision)
    """
    return D(x).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def _q2(x):
    """
    Round to two decimal places and return as float
    For backward compatibility with existing code
    """
    return float(q2(x))

def money_fmt(value):
    """
    Format decimal value as currency string
    """
    v = value if isinstance(value, Decimal) else D(value or 0)
    return f"{v:,.2f}"

def line_total_decimal(qty, unit_price, discount_rate):
    """
    Calculate line total with quantity, unit price, and discount
    Returns Decimal with proper rounding
    """
    q = D(qty)
    p = D(unit_price)
    dr = D(discount_rate or 0)
    one = Decimal("1")
    hundred = Decimal("100")
    total = q * p * (one - dr / hundred)
    return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def safe_divide(numerator, denominator, default=Decimal("0")):
    """
    Safe division that handles zero denominator
    """
    num = D(numerator)
    den = D(denominator)
    if den == 0:
        return D(default)
    return (num / den).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def calculate_percentage(part, total):
    """
    Calculate percentage safely
    """
    if D(total) == 0:
        return Decimal("0")
    return (D(part) / D(total) * 100).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
