import pytest
from flask import url_for
from sqlalchemy import or_

from extensions import db
from models import Supplier, Partner

@pytest.fixture
def _suppliers(app):
    with app.app_context():
        # تنظيف محتمل قبل الزرع لتفادي UNIQUE
        db.session.query(Supplier).filter(
            Supplier.identity_number.in_(["ABC123", "XYZ999", "LMN456"])
        ).delete(synchronize_session=False)
        db.session.commit()

        a = Supplier(name="Alpha Beta", is_local=True,  phone="050111", identity_number="ABC123")
        g = Supplier(name="Gamma",      is_local=False, phone="059999", identity_number="XYZ999")
        z = Supplier(name="Zed",        is_local=True,  phone="052222", identity_number="LMN456")
        db.session.add_all([a, g, z])
        db.session.commit()

        # 🔁 ضروري نرجّع الثلاثة للتست
        return a, g, z



@pytest.fixture
def _partners(app):
    with app.app_context():
        phones  = ["056700", "056711"]
        idents  = ["P-111", "P-222"]

        # تنظيف أي بيانات سابقة بنفس القيم لتفادي UNIQUE
        db.session.query(Partner).filter(
            or_(Partner.phone_number.in_(phones),
                Partner.identity_number.in_(idents))
        ).delete(synchronize_session=False)
        db.session.commit()

        p1 = Partner(name="Par One",  phone_number="056700", identity_number="P-111")
        p2 = Partner(name="Bravo Co", phone_number="056711", identity_number="P-222")
        db.session.add_all([p1, p2])
        db.session.commit()

        # مهم: إرجاع العناصر للتست
        return p1, p2


def test_suppliers_search_by_name_phone_identity(client, app, _suppliers):
    a, g, z = _suppliers
    # بالاسم
    resp = client.get(url_for("vendors_bp.suppliers_list", search="Alpha"))
    assert resp.status_code == 200
    assert b"Alpha Beta" in resp.data and b"Gamma" not in resp.data
    # بالهاتف
    resp = client.get(url_for("vendors_bp.suppliers_list", search="059"))
    assert resp.status_code == 200
    assert b"Gamma" in resp.data and b"Alpha Beta" not in resp.data
    # بالهوية
    resp = client.get(url_for("vendors_bp.suppliers_list", search="ABC123"))
    assert resp.status_code == 200
    assert b"Alpha Beta" in resp.data

def test_partners_search_by_name_phone_identity(client, app, _partners):
    p1, p2 = _partners
    # بالاسم
    resp = client.get(url_for("vendors_bp.partners_list", search="Bravo"))
    assert resp.status_code == 200
    assert b"Bravo Co" in resp.data and b"Par One" not in resp.data
    # بالهاتف
    resp = client.get(url_for("vendors_bp.partners_list", search="056700"))
    assert resp.status_code == 200
    assert b"Par One" in resp.data
    # بالهوية
    resp = client.get(url_for("vendors_bp.partners_list", search="P-222"))
    assert resp.status_code == 200
    assert b"Bravo Co" in resp.data
