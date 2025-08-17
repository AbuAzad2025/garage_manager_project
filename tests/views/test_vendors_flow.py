import datetime as dt
from flask import url_for
from extensions import db
from models import Supplier, Partner, Payment, PaymentEntityType, PaymentDirection, PaymentStatus

_phone_seq = {"i": 0}
def _next_phone(prefix="050"):
    _phone_seq["i"] += 1
    return f"{prefix}{_phone_seq['i']:07d}"

def _mk_supplier(name="Sup A", phone=None):
    s = Supplier(name=name, phone=phone or _next_phone("050"), is_local=True, balance=0)
    db.session.add(s); db.session.commit(); return s

def _mk_partner(name="Partner A"):
    p = Partner(name=name, phone_number=_next_phone("059"), share_percentage=0, balance=0)
    db.session.add(p); db.session.commit(); return p

def _mk_payment_for_supplier(supplier_id, amount=123.45):
    pay = Payment(entity_type=getattr(PaymentEntityType,"SUPPLIER").value if hasattr(PaymentEntityType,"SUPPLIER") else "SUPPLIER", direction=getattr(PaymentDirection,"OUTGOING").value if hasattr(PaymentDirection,"OUTGOING") else "OUTGOING", status=getattr(PaymentStatus,"COMPLETED").value if hasattr(PaymentStatus,"COMPLETED") else "COMPLETED", supplier_id=supplier_id, total_amount=amount, payment_date=dt.datetime.utcnow(), method="cash", currency="ILS")
    db.session.add(pay); db.session.commit(); return pay

def _mk_payment_for_partner(partner_id, amount=77.7):
    pay = Payment(entity_type=getattr(PaymentEntityType,"PARTNER").value if hasattr(PaymentEntityType,"PARTNER") else "PARTNER", direction=getattr(PaymentDirection,"OUTGOING").value if hasattr(PaymentDirection,"OUTGOING") else "OUTGOING", status=getattr(PaymentStatus,"COMPLETED").value if hasattr(PaymentStatus,"COMPLETED") else "COMPLETED", partner_id=partner_id, total_amount=amount, payment_date=dt.datetime.utcnow(), method="cash", currency="ILS")
    db.session.add(pay); db.session.commit(); return pay

def test_suppliers_list_get(client, app):
    _mk_supplier("Sup Alpha", phone=_next_phone("050")); _mk_supplier("Beta Co", phone=_next_phone("050"))
    url = url_for("vendors_bp.suppliers_list", search="Alpha")
    resp = client.get(url)
    assert resp.status_code == 200 and b"Alpha" in resp.data

def test_suppliers_create_edit_delete_flow(client, app):
    resp = client.get(url_for("vendors_bp.suppliers_create")); assert resp.status_code == 200
    resp = client.post(url_for("vendors_bp.suppliers_create"), data={"name":"New Sup","is_local":True,"phone":_next_phone("050")}, follow_redirects=True)
    assert resp.status_code == 200
    sup = Supplier.query.filter_by(name="New Sup").first(); assert sup is not None
    resp = client.get(url_for("vendors_bp.suppliers_edit", id=sup.id)); assert resp.status_code == 200
    resp = client.post(url_for("vendors_bp.suppliers_edit", id=sup.id), data={"name":"New Sup 2","is_local":True,"phone":sup.phone}, follow_redirects=True)
    assert resp.status_code == 200
    assert db.session.get(Supplier, sup.id).name == "New Sup 2"
    _mk_payment_for_supplier(sup.id)
    resp = client.get(url_for("vendors_bp.suppliers_payments", id=sup.id))
    assert resp.status_code == 200 and b"New Sup 2" in resp.data
    resp = client.get(url_for("vendors_bp.suppliers_pay", id=sup.id)); assert resp.status_code in (302, 308)
    resp = client.post(url_for("vendors_bp.suppliers_delete", id=sup.id), follow_redirects=True)
    assert resp.status_code == 200 and db.session.get(Supplier, sup.id) is None

def test_partners_list_and_flow(client, app):
    p = _mk_partner("X Partner")
    resp = client.get(url_for("vendors_bp.partners_list", search="X Part")); assert resp.status_code == 200
    assert client.get(url_for("vendors_bp.partners_create")).status_code == 200
    resp = client.post(url_for("vendors_bp.partners_create"), data={"name":"Y Partner","phone_number":_next_phone("059")}, follow_redirects=True)
    assert resp.status_code == 200
    y = Partner.query.filter_by(name="Y Partner").first(); assert y
    _mk_payment_for_partner(p.id)
    assert client.get(url_for("vendors_bp.partners_edit", id=p.id)).status_code == 200
    assert client.get(url_for("vendors_bp.partners_payments", id=p.id)).status_code == 200
    r = client.get(url_for("vendors_bp.partners_pay", id=p.id)); assert r.status_code in (302, 308)
    r = client.post(url_for("vendors_bp.partners_delete", id=p.id), follow_redirects=True)
    assert r.status_code == 200 and db.session.get(Partner, p.id) is None
