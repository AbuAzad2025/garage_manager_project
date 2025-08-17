import pytest
from flask import url_for
from extensions import db
from models import (
    Supplier, Partner, Warehouse, Product, StockLevel, 
    Shipment, Payment, PaymentEntityType, PaymentDirection, WarehouseType
)

# --- Fixtures ---
@pytest.fixture
def supplier_data():
    return {
        "name": "Unified Supplier",
        "phone": "123456789",
        "identity_number": "1111222233",
        "email": "unified@supplier.com",
        "address": "Test Address",
        "notes": "Unified test",
    }

@pytest.fixture
def partner_data():
    return {
        "name": "Unified Partner",
        "phone_number": "987654321",
        "identity_number": "4444555566",
        "email": "partner@unified.com",
        "address": "Partner Address",
        "notes": "Trusted partner",
    }

# --- Supplier Tests ---
def test_supplier_crud_and_payment(client, supplier_data):
    # Create
    r = client.post(url_for("vendors_bp.suppliers_create"), data=supplier_data, follow_redirects=True)
    assert r.status_code == 200
    assert "تم إضافة المورد بنجاح" in r.data.decode("utf-8")
    s = Supplier.query.filter_by(identity_number="1111222233").first()
    assert s

    # Edit
    supplier_data["name"] = "Supplier Updated"
    r = client.post(url_for("vendors_bp.suppliers_edit", id=s.id), data=supplier_data, follow_redirects=True)
    assert "تم تحديث المورد بنجاح" in r.data.decode("utf-8")

    # List
    r = client.get(url_for("vendors_bp.suppliers_list"))
    assert r.status_code == 200

    # Payment
    payment = Payment(
        supplier_id=s.id,
        total_amount=200,
        entity_type=PaymentEntityType.SUPPLIER.value,
        direction=PaymentDirection.OUTGOING.value,
    )
    db.session.add(payment)
    db.session.commit()
    r = client.get(url_for("vendors_bp.suppliers_payments", id=s.id))
    assert "200" in r.data.decode("utf-8")

    # Delete
    r = client.post(url_for("vendors_bp.suppliers_delete", id=s.id), follow_redirects=True)
    assert "تم حذف المورد بنجاح" in r.data.decode("utf-8")

# --- Partner Tests ---
def test_partner_crud_and_payment(client, partner_data):
    # Create
    r = client.post(url_for("vendors_bp.partners_create"), data=partner_data, follow_redirects=True)
    assert "تم إضافة الشريك بنجاح" in r.data.decode("utf-8")
    p = Partner.query.filter_by(identity_number="4444555566").first()
    assert p

    # Edit
    partner_data["name"] = "Partner Updated"
    r = client.post(url_for("vendors_bp.partners_edit", id=p.id), data=partner_data, follow_redirects=True)
    assert "تم تحديث الشريك بنجاح" in r.data.decode("utf-8")

    # List
    r = client.get(url_for("vendors_bp.partners_list"))
    assert r.status_code == 200

    # Payment
    payment = Payment(
        partner_id=p.id,
        total_amount=300,
        entity_type=PaymentEntityType.PARTNER.value,
        direction=PaymentDirection.OUTGOING.value,
    )
    db.session.add(payment)
    db.session.commit()
    r = client.get(url_for("vendors_bp.partners_payments", id=p.id))
    assert "300" in r.data.decode("utf-8")

    # Delete
    r = client.post(url_for("vendors_bp.partners_delete", id=p.id), follow_redirects=True)
    assert "تم حذف الشريك بنجاح" in r.data.decode("utf-8")

# --- Warehouse & Partner Share Tests ---
def test_warehouse_with_shares(client):
    w = Warehouse(name="Shared WH", warehouse_type=getattr(WarehouseType, "PARTNER", "PARTNER"))
    p = Product(name="Shared Product")
    db.session.add_all([w, p])
    db.session.flush()
    sl = StockLevel(warehouse_id=w.id, product_id=p.id, quantity=10)
    db.session.add(sl)
    db.session.commit()

    partner = Partner(name="Share Partner")
    db.session.add(partner)
    db.session.commit()

    # Empty shares check
    r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w.id))
    assert r.status_code == 200
    assert r.get_json()["success"]

    # Post share
    payload = {
        "shares": [{
            "product_id": p.id,
            "partner_id": partner.id,
            "share_percentage": 25.0,
            "share_amount": 0,
            "notes": "test",
        }]
    }
    r = client.post(url_for("warehouse_bp.partner_shares", warehouse_id=w.id), json=payload)
    assert r.status_code == 200
    assert r.get_json()["success"]

# --- Shipments Basic Interaction ---
def test_shipment_listing_route(client):
    r = client.get(url_for("shipments_bp.shipments"))
    assert r.status_code == 200
