import pytest
from datetime import date
from werkzeug.datastructures import MultiDict
from forms import PaymentForm

def _mk_form(formdata):
    return PaymentForm(formdata=MultiDict(formdata), meta={"csrf": False})

@pytest.mark.usefixtures("app")
def test_payment_form_valid_customer_incoming(app):
    form = _mk_form({
        "payment_date": "2025-01-02",
        "total_amount": "100.00",
        "currency": "ILS",
        "status": "COMPLETED",
        "direction": "IN",
        "entity_type": "CUSTOMER",
        "customer_id": "1",
        "splits-0-method": "cash",
        "splits-0-amount": "100.00",
    })
    assert form.validate() is True

@pytest.mark.usefixtures("app")
def test_payment_form_requires_out_for_expense(app):
    form = _mk_form({
        "payment_date": "2025-01-02",
        "total_amount": "50.00",
        "currency": "ILS",
        "status": "COMPLETED",
        "direction": "IN",
        "entity_type": "EXPENSE",
        "expense_id": "1",
        "splits-0-method": "cash",
        "splits-0-amount": "50.00",
    })
    assert form.validate() is False
    assert any("OUT" in e or "OUT" in "".join(form.direction.errors) for e in form.direction.errors)

@pytest.mark.usefixtures("app")
def test_payment_form_splits_sum_mismatch(app):
    form = _mk_form({
        "payment_date": "2025-01-02",
        "total_amount": "120.00",
        "currency": "ILS",
        "status": "COMPLETED",
        "direction": "IN",
        "entity_type": "CUSTOMER",
        "customer_id": "1",
        "splits-0-method": "cash",
        "splits-0-amount": "100.00",
    })
    assert form.validate() is False
    assert any("مجموع الدفعات الجزئية" in e for e in form.total_amount.errors)
