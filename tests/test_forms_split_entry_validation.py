
# -*- coding: utf-8 -*-
import pytest
from werkzeug.datastructures import MultiDict
from forms import splitEntryForm

def _mk_form(data):
    # FlaskForm needs a formdata object; CSRF is disabled by default in tests
    return splitEntryForm(formdata=MultiDict(data))

def test_cheque_requires_full_details():
    frm = _mk_form({
        "method": "cheque",
        "amount": "10.00",
        # Missing check_number/check_bank/check_due_date
    })
    ok = frm.validate()
    assert not ok
    assert any("يجب إدخال بيانات الشيك" in e for e in frm.check_number.errors + frm.check_bank.errors + frm.check_due_date.errors)

def test_bank_requires_reference():
    frm = _mk_form({
        "method": "bank",
        "amount": "5.00",
        # Missing bank_transfer_ref
    })
    ok = frm.validate()
    assert not ok
    assert any("أدخل مرجع التحويل البنكي" in e for e in frm.bank_transfer_ref.errors)
