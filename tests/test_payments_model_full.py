
# -*- coding: utf-8 -*-
import re
import pytest
from datetime import datetime, date
from extensions import db
import models as M
from uuid import uuid4

pytestmark = pytest.mark.usefixtures("app")


def _mk_customer():
    u = uuid4().hex[:8]
    c = M.Customer(name=f"ACME-{u}", phone=f"000{u}", email=f"acme{u}@example.com", currency="USD")
    db.session.add(c); db.session.commit()
    return c

def test_payment_total_amount_positive_constraint():
    with pytest.raises(Exception):
        p = M.Payment(
            payment_date=datetime.utcnow(),
            total_amount=0,  # violates ck_payment_positive
            currency="ILS",
            method=M.PaymentMethod.CASH.value,
            status=M.PaymentStatus.PENDING.value,
            direction=M.PaymentDirection.INCOMING.value,
            entity_type=M.PaymentEntityType.CUSTOMER.value
        )
        db.session.add(p); db.session.commit()
    db.session.rollback()

def test_payment_enum_coercion_and_to_dict_roundtrip():
    c = _mk_customer()
    p = M.Payment(
        payment_date=datetime(2025, 1, 1),
        total_amount=123.45,
        currency="USD",
        method="cash",  # string is fine (validator coerces)
        status=M.PaymentStatus.PENDING,  # enum is fine
        direction="IN",
        entity_type="CUSTOMER",
        customer_id=c.id,
        reference="ref-1",
    )
    db.session.add(p); db.session.commit()
    # Ensure values are stored/serialized as expected
    data = p.to_dict()
    assert data["currency"] == "USD"
    assert data["total_amount"] == pytest.approx(123.45)
    assert data["method"] in ("cash", M.PaymentMethod.CASH.value)
    assert data["status"] in ("PENDING", M.PaymentStatus.PENDING.value)
    assert data["direction"] in ("IN", M.PaymentDirection.INCOMING.value)
    assert data["entity_type"] == "CUSTOMER"

def test_payment_status_transitions_valid_and_invalid():
    p = M.Payment(
        payment_date=datetime.utcnow(),
        total_amount=50,
        currency="ILS",
        method="cash",
        status=M.PaymentStatus.PENDING.value,
        direction="IN",
        entity_type="CUSTOMER"
    )
    db.session.add(p); db.session.commit()

    # valid: PENDING -> COMPLETED -> REFUNDED
    p.status = M.PaymentStatus.COMPLETED.value
    db.session.add(p); db.session.commit()
    p.status = M.PaymentStatus.REFUNDED.value
    db.session.add(p); db.session.commit()

    # invalid transitions should raise ValueError at assignment (validator)
    with pytest.raises(ValueError):
        p.status = M.PaymentStatus.PENDING.value  # cannot go back from REFUNDED

def test_payment_before_insert_generates_number_and_fallback_method_from_splits():
    # Create payment with no explicit method but with a split -> method falls back to split's method
    p = M.Payment(
        payment_date=datetime.utcnow(),
        total_amount=80,
        currency="ILS",
        status=M.PaymentStatus.COMPLETED.value,
        direction=M.PaymentDirection.INCOMING.value,
        entity_type="CUSTOMER"
    )
    db.session.add(p); db.session.flush()
    sp = M.PaymentSplit(payment_id=p.id, amount=80, method=M.PaymentMethod.BANK.value, details={"bank_transfer_ref":"X"})
    db.session.add(sp); db.session.commit()

    # After commit, payment_number assigned and method inferred
    assert p.payment_number and p.payment_number.startswith("PMT")
    # e.g. PMT2025xxxx-0001
    assert re.match(r"^PMT\d{8}-\d{4}$", p.payment_number) is not None
    assert p.method in (M.PaymentMethod.BANK, M.PaymentMethod.BANK.value)

def test_payment_entity_label_customer():
    c = _mk_customer()
    p = M.Payment(
        payment_date=datetime.utcnow(),
        total_amount=10,
        currency="USD",
        method="cash",
        status="COMPLETED",
        direction="IN",
        entity_type="CUSTOMER",
        customer_id=c.id
    )
    db.session.add(p); db.session.commit()
    assert "ACME" in (p.entity_label() or "")

