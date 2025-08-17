# -*- coding: utf-8 -*-
import pytest
from flask import url_for
from werkzeug.routing import BuildError
from werkzeug.security import generate_password_hash
from extensions import db
from models import User, Role, Permission, Supplier, Partner, Product, Warehouse, StockLevel, Payment, PaymentEntityType, PaymentDirection, WarehouseType

_REQUIRED_PERMS = {
    "manage_vendors", "add_supplier", "add_partner",
    "manage_inventory", "view_inventory", "view_parts",
    "manage_warehouses", "view_warehouses", "warehouse_transfer",
    "manage_shipments", "manage_payments",
}

def _get_or_create(model, **kw):
    obj = model.query.filter_by(**kw).first()
    if not obj:
        obj = model(**kw)
        db.session.add(obj)
        db.session.flush()
    return obj

def _attach_role(user: User, role: Role):
    if hasattr(user, "roles") and role not in user.roles:
        user.roles.append(role)
    elif hasattr(user, "role"):
        user.role = role
    else:
        try: user.role = role
        except: pass

def _ensure_user_with_perms():
    perms = [_get_or_create(Permission, name=n) for n in _REQUIRED_PERMS]
    role = _get_or_create(Role, name="super_admin")
    for p in perms:
        if p not in role.permissions: role.permissions.append(p)
    user = User.query.filter_by(username="azad").first()
    if not user:
        user = User(username="azad", email="azad@example.com", is_active=True)
        try: user.set_password("AZ123456")
        except: user.password_hash = generate_password_hash("AZ123456", method="scrypt")
        db.session.add(user); db.session.flush()
    else: user.is_active = True
    _attach_role(user, role); db.session.commit(); return user

def _resolve_login_url(app):
    candidates = ["auth.login", "auth_bp.login", "login"]
    with app.app_context():
        for ep in candidates:
            try: return url_for(ep)
            except BuildError: continue
    raise RuntimeError("لم يتم العثور على endpoint لتسجيل الدخول")

def _login_form_variants():
    yield {"username": "azad", "password": "AZ123456"}
    yield {"email": "azad@example.com", "password": "AZ123456"}
    yield {"login": "azad", "password": "AZ123456"}
    yield {"username": "azad", "email": "azad@example.com", "password": "AZ123456"}

@pytest.fixture(autouse=True)
def _real_login_every_test(client, app):
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        _ensure_user_with_perms()
        login_url = _resolve_login_url(app)
    ok = False
    for data in _login_form_variants():
        resp = client.post(login_url, data=data, follow_redirects=True)
        if "تسجيل دخول" not in resp.data.decode("utf-8"):
            ok = True; break
    assert ok, "فشل تسجيل الدخول الفعلي"

@pytest.fixture
def supplier_data():
    return {
        "name": "Full Supplier", "phone": "123456",
        "identity_number": "SUP-001", "email": "sup@example.com",
        "address": "Supplier St", "notes": "Main supplier",
    }

@pytest.fixture
def partner_data():
    return {
        "name": "Full Partner", "phone_number": "7891011",
        "identity_number": "PART-001", "email": "part@example.com",
        "address": "Partner Ave", "notes": "Reliable partner",
    }

@pytest.fixture
def spare_part_data():
    return {
        "name": "Air Filter", "sku": "AF-789", "barcode": "1112233445566",
        "category": "Filters", "unit": "Piece",
        "purchase_price": 20.0, "selling_price": 30.0, "notes": "Used in trucks"
    }

@pytest.fixture
def warehouse():
    w = Warehouse(name="Central WH", warehouse_type=getattr(WarehouseType, "MAIN", "MAIN"))
    db.session.add(w); db.session.commit(); return w

def test_supplier_crud_and_payment(client, supplier_data):
    r = client.post(url_for("vendors_bp.suppliers_create"), data=supplier_data, follow_redirects=True)
    print("CREATE SUPPLIER PAGE:\n", r.data.decode("utf-8"))
    assert "تم إضافة المورد بنجاح" in r.data.decode("utf-8")

    s = Supplier.query.filter_by(identity_number="SUP-001").first(); assert s
    supplier_data["name"] = "Updated Supplier"

    r = client.post(url_for("vendors_bp.suppliers_edit", id=s.id), data=supplier_data, follow_redirects=True)
    print("EDIT SUPPLIER PAGE:\n", r.data.decode("utf-8"))
    assert "تم تحديث المورد بنجاح" in r.data.decode("utf-8")

    r = client.get(url_for("vendors_bp.suppliers_list"))
    print("SUPPLIER LIST PAGE:\n", r.data.decode("utf-8"))
    assert r.status_code == 200

    payment = Payment(
        supplier_id=s.id, total_amount=100,
        entity_type=PaymentEntityType.SUPPLIER.value,
        direction=PaymentDirection.OUTGOING.value,
    )
    db.session.add(payment); db.session.commit()

    r = client.get(url_for("vendors_bp.suppliers_payments", id=s.id))
    print("SUPPLIER PAYMENTS PAGE:\n", r.data.decode("utf-8"))
    assert "100" in r.data.decode("utf-8")

    r = client.post(url_for("vendors_bp.suppliers_delete", id=s.id), follow_redirects=True)
    print("DELETE SUPPLIER PAGE:\n", r.data.decode("utf-8"))
    assert "تم حذف المورد بنجاح" in r.data.decode("utf-8")

def test_partner_crud_and_payment(client, partner_data):
    r = client.post(url_for("vendors_bp.partners_create"), data=partner_data, follow_redirects=True)
    print("CREATE PARTNER:\n", r.data.decode("utf-8"))
    assert "تم إضافة الشريك بنجاح" in r.data.decode("utf-8")

    p = Partner.query.filter_by(identity_number="PART-001").first(); assert p
    partner_data["name"] = "Updated Partner"

    r = client.post(url_for("vendors_bp.partners_edit", id=p.id), data=partner_data, follow_redirects=True)
    print("EDIT PARTNER:\n", r.data.decode("utf-8"))
    assert "تم تحديث الشريك بنجاح" in r.data.decode("utf-8")

    r = client.get(url_for("vendors_bp.partners_list"))
    print("PARTNER LIST:\n", r.data.decode("utf-8"))
    assert r.status_code == 200

    payment = Payment(
        partner_id=p.id, total_amount=150,
        entity_type=PaymentEntityType.PARTNER.value,
        direction=PaymentDirection.OUTGOING.value,
    )
    db.session.add(payment); db.session.commit()

    r = client.get(url_for("vendors_bp.partners_payments", id=p.id))
    print("PARTNER PAYMENTS:\n", r.data.decode("utf-8"))
    assert "150" in r.data.decode("utf-8")

    r = client.post(url_for("vendors_bp.partners_delete", id=p.id), follow_redirects=True)
    print("DELETE PARTNER:\n", r.data.decode("utf-8"))
    assert "تم حذف الشريك بنجاح" in r.data.decode("utf-8")

def test_part_crud_and_stock(client, spare_part_data, warehouse):
    r = client.post(url_for("parts_bp.parts_create"), data=spare_part_data, follow_redirects=True)
    print("CREATE PART:\n", r.data.decode("utf-8"))
    assert "تم إضافة القطعة بنجاح" in r.data.decode("utf-8")

    p = Product.query.filter_by(sku="AF-789").first(); assert p
    spare_part_data["name"] = "Updated Filter"

    r = client.post(url_for("parts_bp.parts_edit", id=p.id), data=spare_part_data, follow_redirects=True)
    print("EDIT PART:\n", r.data.decode("utf-8"))
    assert "تم تحديث القطعة بنجاح" in r.data.decode("utf-8")

    r = client.get(url_for("parts_bp.parts_list"))
    print("PART LIST:\n", r.data.decode("utf-8"))
    assert r.status_code == 200

    sl = StockLevel(warehouse_id=warehouse.id, product_id=p.id, quantity=15, reserved_quantity=2)
    db.session.add(sl); db.session.commit()

    r = client.get(url_for("parts_bp.stock_levels", id=p.id))
    print("STOCK LEVEL PAGE:\n", r.data.decode("utf-8"))
    assert "Central WH" in r.data.decode("utf-8") and "15" in r.data.decode("utf-8")

    r = client.post(url_for("parts_bp.parts_delete", id=p.id), follow_redirects=True)
    print("DELETE PART:\n", r.data.decode("utf-8"))
    assert "تم حذف القطعة بنجاح" in r.data.decode("utf-8")

def test_warehouse_with_partner_shares(client):
    w = Warehouse(name="Shared WH", warehouse_type=getattr(WarehouseType, "PARTNER", "PARTNER"))
    p = Product(name="Brake Disc")
    db.session.add_all([w, p]); db.session.flush()
    db.session.add(StockLevel(warehouse_id=w.id, product_id=p.id, quantity=10)); db.session.commit()
    partner = Partner(name="Share Partner"); db.session.add(partner); db.session.commit()

    r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w.id))
    print("GET SHARES:\n", r.get_json())
    assert r.get_json()["success"]

    payload = {"shares": [{
        "product_id": p.id, "partner_id": partner.id,
        "share_percentage": 25.0, "share_amount": 0, "notes": "auto"
    }]}
    r = client.post(url_for("warehouse_bp.partner_shares", warehouse_id=w.id), json=payload)
    print("POST SHARES:\n", r.get_json())
    assert r.status_code == 200 and r.get_json()["success"]

def test_shipments_entry_point(client):
    r = client.get(url_for("shipments_bp.shipments"))
    print("SHIPMENTS PAGE:\n", r.data.decode("utf-8"))
    assert r.status_code == 200
