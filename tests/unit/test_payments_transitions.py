# tests/unit/test_payments_transitions.py
# -*- coding: utf-8 -*-
import pytest
from extensions import db
import models as M

_HAS = hasattr(M, "Payment") and hasattr(M, "PaymentStatus")

ALLOWED = {
    ("PENDING","COMPLETED"),
    ("COMPLETED","REFUNDED"),
}
FORBIDDEN = {
    ("PENDING","REFUNDED"),
    ("FAILED","COMPLETED"),
    ("REFUNDED","COMPLETED"),
}

def _make_min_payment():
    p = M.Payment()

    # أقل قيم لازمة عشان يمرّ INSERT
    if hasattr(p, "total_amount") and (getattr(p, "total_amount", None) in (None, 0)):
        p.total_amount = 1

    if hasattr(p, "amount") and (getattr(p, "amount", None) in (None, 0)):
        p.amount = 1

    # method مطلوب: خذ أول قيمة من Enum إن وُجد، وإلا FALLBACK لسلسلة 'CASH'
    if hasattr(p, "method") and (getattr(p, "method", None) in (None, "")):
        if hasattr(M, "PaymentMethod"):
            p.method = list(M.PaymentMethod)[0]   # enum member
            # أو لو عمودك يتوقع النص بدل enum member:
            # p.method = list(M.PaymentMethod)[0].value
        else:
            p.method = "CASH"

    return p

@pytest.mark.skipif(not _HAS, reason="Payment/Status not found")
@pytest.mark.parametrize("src,dst", sorted(ALLOWED))
def test_payment_status_allowed_transitions(app, src, dst):
    with app.app_context():
        p = _make_min_payment()
        p.status = getattr(M.PaymentStatus, src)
        db.session.add(p); db.session.commit()
        p.status = getattr(M.PaymentStatus, dst)
        db.session.commit()

@pytest.mark.skipif(not _HAS, reason="Payment/Status not found")
@pytest.mark.parametrize("src,dst", sorted(FORBIDDEN))
def test_payment_status_forbidden_transitions(app, src, dst):
    with app.app_context():
        p = _make_min_payment()
        p.status = getattr(M.PaymentStatus, src)
        db.session.add(p); db.session.commit()

        try:
            # قد يرمي هنا بسبب validator (وقت الإسناد)
            p.status = getattr(M.PaymentStatus, dst)
        except Exception:
            db.session.rollback()
        else:
            # أو يرمي عند الكومِت بسبب قواعد أخرى
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

