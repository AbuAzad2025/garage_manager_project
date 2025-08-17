import io
import json
import types
import base64
import pytest
from datetime import datetime, date
from flask import Flask
from werkzeug.datastructures import Headers

import utils
from utils import (
    init_app, format_currency, format_percent, format_date, format_datetime,
    yes_no, status_label, qr_to_base64, generate_excel_report, generate_pdf_report,
    generate_vcf, generate_csv_contacts, generate_excel_contacts,
    prepare_payment_form_choices, permission_required, update_entity_balance,
)

from extensions import db
from models import Payment, PaymentSplit, PaymentStatus, PaymentEntityType, PaymentDirection, Customer


class _FakeRedis:
    def __init__(self): self._s = {}
    def smembers(self, k): return self._s.get(k, set())
    def sadd(self, k, *vals): self._s.setdefault(k, set()).update(vals)
    def expire(self, k, secs): return True
    def delete(self, k): self._s.pop(k, None)


@pytest.mark.usefixtures("app")
def test_init_app_and_filters_register(monkeypatch, app):
    # امنع الاتصال الحقيقي بريديـس
    monkeypatch.setattr(utils.redis, "StrictRedis", types.SimpleNamespace(from_url=lambda *_a, **_k: _FakeRedis()))
    init_app(app)
    # الفلاتر مسجلة؟
    j = app.jinja_env.filters
    assert {"format_currency","format_percent","format_date","format_datetime","yes_no","status_label"} <= set(j.keys())
    assert isinstance(utils.redis_client, _FakeRedis)

def test_format_helpers_are_robust():
    assert format_currency("12.5") == "12.50 ₪"
    assert format_currency("x") == "0.00 ₪"
    assert format_percent(7) == "7.00%"
    assert format_percent(None) == "0.00%"
    assert format_date(date(2025,1,1)) == "2025-01-01"
    assert format_date("x") == "-"
    assert format_datetime(datetime(2025,1,1,13,45)) == "2025-01-01 13:45"
    assert format_datetime("x") == ""
    assert yes_no(True) == "نشط" and yes_no(False) == "مؤرشف"
    assert status_label("ACTIVE").startswith("نشط")
    assert status_label("unknown") == "unknown"

def test_qr_to_base64_roundtrip():
    b64 = qr_to_base64("hello")
    raw = base64.b64decode(b64)
    assert len(raw) > 100  # صورة PNG صغيرة

def test_generate_excel_pdf_and_contacts_response_headers(app):
    class Obj: 
        def __init__(self,i): self.id=i; self.name=f"N{i}"; self.balance=10*i
        def to_dict(self): return {"id":self.id,"name":self.name,"balance":self.balance}
    data = [Obj(1), Obj(2)]
    # Excel تقرير عام
    r = generate_excel_report(data, "x.xlsx")
    assert r.mimetype.endswith("sheet")
    assert "attachment; filename=x.xlsx" in r.headers.get("Content-Disposition","")
    assert len(r.get_data()) > 0
    # PDF
    r2 = generate_pdf_report(data)
    assert r2.mimetype == "application/pdf"
    # vCard
    r3 = generate_vcf([Obj(9)], ["name","phone","email"])
    assert r3.mimetype == "text/vcard"
    assert "BEGIN:VCARD" in r3.get_data(as_text=True)
    # CSV
    r4 = generate_csv_contacts([Obj(7)], ["name","balance"])
    assert r4.mimetype == "text/csv"
    assert "name,balance" in r4.get_data(as_text=True)
    # Excel contacts
    r5 = generate_excel_contacts([Obj(3)], ["name"])
    assert r5.mimetype.endswith("sheet")
    assert len(r5.get_data()) > 0

def test_prepare_payment_form_choices_smoke(app):
    class Dummy: pass
    f = Dummy()
    # حقول Select بسيطة
    f.currency=f.method=f.status=f.direction=f.entity_type=types.SimpleNamespace()
    prepare_payment_form_choices(f)
    for fld in ("currency","method","status","direction","entity_type"):
        assert getattr(fld, "choices", None) is None or hasattr(getattr(f, fld), "choices")

@pytest.mark.usefixtures("app")
def test_permission_required_decorator_denies(monkeypatch, app):
    class FakeUser:
        is_authenticated = True
        def has_permission(self, name): return False
    monkeypatch.setattr(utils, "current_user", FakeUser())
    @permission_required("x")
    def _f(): return "ok"
    with app.test_request_context():
        with pytest.raises(Exception) as ei:
            _f()
        # Flask.abort(403) يرفع HTTPException
        assert "403" in str(ei.value)

@pytest.mark.usefixtures("app")
def test_update_entity_balance_happy_path(app):
    with app.app_context():
        c = Customer(name="C1", phone="1", email="c@x")
        db.session.add(c); db.session.commit()
        p = Payment(
            entity_type=PaymentEntityType.CUSTOMER.value,
            customer_id=c.id,
            direction=PaymentDirection.INCOMING.value,
            status=PaymentStatus.COMPLETED.value,
            payment_date=datetime.utcnow(),
            total_amount=100, currency="ILS", method="cash",
        )
        db.session.add(p); db.session.flush()
        db.session.add(PaymentSplit(payment_id=p.id, amount=40, method="cash"))
        db.session.add(PaymentSplit(payment_id=p.id, amount=60, method="cash"))
        db.session.commit()
        total = update_entity_balance("CUSTOMER", c.id)
        assert abs(total - 100.0) < 0.001

def test_send_whatsapp_message_graceful_if_not_configured(monkeypatch, app, client):
    # بدون إعدادات Twilio -> False + فلاش رسالة
    with app.test_request_context("/"):
        r = utils.send_whatsapp_message("+9705xxxx", "hi")
        assert r is False
