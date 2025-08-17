
# -*- coding: utf-8 -*-
import pytest, inspect
import models as M

HAS_INVOICE = hasattr(M, "Invoice")
@pytest.mark.skipif(not HAS_INVOICE, reason="Invoice model not found")
def test_invoice_has_status_field():
    inv = M.Invoice()
    assert hasattr(inv, "status"), "Invoice.status مفقود"
