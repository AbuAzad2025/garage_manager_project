# -*- coding: utf-8 -*-
import decimal
from utils import format_currency

def test_format_currency_basic_shapes():
    # يقبل int/float/Decimal ويرجع str قابلة للعرض
    out1 = format_currency(0)
    out2 = format_currency(12.5)
    out3 = format_currency(decimal.Decimal("1234.56"))

    for s in (out1, out2, out3):
        assert isinstance(s, str)
        assert any(ch.isdigit() for ch in s)
