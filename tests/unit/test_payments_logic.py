# -*- coding: utf-8 -*-
import pytest
from extensions import db
import models as M

_HAS_PAYMENT = hasattr(M, "Payment")

@pytest.mark.skipif(not _HAS_PAYMENT, reason="Payment model not found")
def test_payment_amount_must_be_positive(app):
    """يجب رفض المبالغ غير الموجبة (0 أو سالب) عند الحفظ."""
    with app.app_context():
        for bad in (0, -1):
            p = M.Payment()
            p.amount = bad
            db.session.add(p)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()
