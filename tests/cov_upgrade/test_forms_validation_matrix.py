import pytest
from datetime import datetime
from werkzeug.datastructures import MultiDict

from forms import splitEntryForm, PaymentForm, InvoiceForm, OnlineCartPaymentForm

def _md(d): return MultiDict(d)

def test_split_entry_validations():
    # شيك ناقص بيانات
    f = splitEntryForm(formdata=_md({"method":"cheque","amount":"10"}), meta={"csrf":False})
    assert f.validate() is False and any("الشيك" in e for e in sum(f.check_number.errors+f.check_bank.errors, []))
    # بطاقة رقم غير صالح
    f2 = splitEntryForm(formdata=_md({"method":"card","amount":"10","card_number":"123","card_expiry":"12/40"}), meta={"csrf":False})
    assert f2.validate() is False and any("غير صالح" in e for e in f2.card_number.errors)
    # بطاقة expiry خطأ
    f3 = splitEntryForm(formdata=_md({"method":"card","amount":"10","card_number":"4111111111111111","card_expiry":"01/20"}), meta={"csrf":False})
    assert f3.validate() is False and any("MM/YY" in e for e in f3.card_expiry.errors)
    # بنك بلا مرجع
    f4 = splitEntryForm(formdata=_md({"method":"bank","amount":"5"}), meta={"csrf":False})
    assert f4.validate() is False and any("مرجع" in e for e in f4.bank_transfer_ref.errors)
    # نقدًا صحيح
    f5 = splitEntryForm(formdata=_md({"method":"cash","amount":"2"}), meta={"csrf":False})
    assert f5.validate() is True

def test_payment_form_core_happy_and_edges(app):
    # طريقة الدفع تُستنتج من splits إذا method فارغ
    form = PaymentForm(formdata=_md({
        "payment_date":"2025-01-02",
        "total_amount":"100.00",
        "currency":"ILS",
        "status":"COMPLETED",
        "direction":"IN",
        "entity_type":"CUSTOMER",
        "customer_id":"1",
        "splits-0-method":"cash",
        "splits-0-amount":"100.00",
        "method":""  # يُملأ تلقائياً
    }), meta={"csrf":False})
    assert form.validate() is True
    assert form.method.data == "cash"

    # مجموع السبلت != الإجمالي
    bad = PaymentForm(formdata=_md({
        "payment_date":"2025-01-02",
        "total_amount":"120.00",
        "currency":"ILS",
        "status":"COMPLETED",
        "direction":"IN",
        "entity_type":"CUSTOMER",
        "customer_id":"1",
        "splits-0-method":"cash",
        "splits-0-amount":"100.00",
    }), meta={"csrf":False})
    assert bad.validate() is False and any("مجموع" in e for e in bad.total_amount.errors)

    # كيان وارد يجب IN
    wrong_dir = PaymentForm(formdata=_md({
        "payment_date":"2025-01-02",
        "total_amount":"50.00",
        "currency":"ILS",
        "status":"COMPLETED",
        "direction":"OUT",
        "entity_type":"CUSTOMER",
        "customer_id":"1",
        "splits-0-method":"cash",
        "splits-0-amount":"50.00",
    }), meta={"csrf":False})
    assert wrong_dir.validate() is False and any("IN" in e for e in wrong_dir.direction.errors)

    # كيان صادر يجب OUT (EXPENSE)
    wrong_dir2 = PaymentForm(formdata=_md({
        "payment_date":"2025-01-02",
        "total_amount":"50.00",
        "currency":"ILS",
        "status":"COMPLETED",
        "direction":"IN",
        "entity_type":"EXPENSE",
        "expense_id":"2",
        "splits-0-method":"cash",
        "splits-0-amount":"50.00",
    }), meta={"csrf":False})
    assert wrong_dir2.validate() is False and any("OUT" in e for e in wrong_dir2.direction.errors)

    # أكثر من مرجع مُحدد
    multi = PaymentForm(formdata=_md({
        "payment_date":"2025-01-02",
        "total_amount":"10.00",
        "currency":"ILS",
        "status":"COMPLETED",
        "direction":"IN",
        "entity_type":"CUSTOMER",
        "customer_id":"1",
        "supplier_id":"2",
        "splits-0-method":"cash",
        "splits-0-amount":"10.00",
    }), meta={"csrf":False})
    assert multi.validate() is False

def test_invoice_form_sources_and_customer_required(app):
    # مرفوض: مصدر SALE بدون sale_id
    bad = InvoiceForm(formdata=_md({
        "source":"SALE","status":"UNPAID","customer_id":"1",
        "total_amount":"10.00",
        "lines-0-description":"x","lines-0-quantity":"1","lines-0-unit_price":"10",
    }), meta={"csrf":False})
    assert bad.validate() is False
    # مقبول: إضافة sale_id
    ok = InvoiceForm(formdata=_md({
        "source":"SALE","status":"UNPAID","customer_id":"1","sale_id":"9",
        "total_amount":"10.00",
        "lines-0-description":"x","lines-0-quantity":"1","lines-0-unit_price":"10",
    }), meta={"csrf":False})
    assert ok.validate() is True

def test_online_cart_payment_card_rules():
    # بطاقة غير صالحة
    f = OnlineCartPaymentForm(formdata=_md({
        "payment_method":"card","card_holder":"A","card_number":"411111111111111","expiry":"01/20","cvv":"123"
    }), meta={"csrf":False})
    assert f.validate() is False
    # بطاقة صحيحة تقريبًا (رقم لُنه صحيح وتاريخ مستقبل)
    f2 = OnlineCartPaymentForm(formdata=_md({
        "payment_method":"card","card_holder":"A","card_number":"4111111111111111","expiry":"12/40","cvv":"123"
    }), meta={"csrf":False})
    assert f2.validate() is True
