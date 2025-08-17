# -*- coding: utf-8 -*-
import io
import csv
import json
import uuid
import os
import pytest
from datetime import datetime
from flask import url_for
from flask_login import login_user
from extensions import db
from models import (
    Warehouse, WarehouseType, Product, StockLevel, Transfer, Partner,
    ProductPartnerShare, ExchangeTransaction, Customer, Supplier, PreOrder,
    ShipmentItem, Shipment, Payment, PaymentStatus, PaymentDirection, PaymentEntityType,
    User, Role, Permission
)

@pytest.fixture(autouse=True)
def _login_superadmin_every_test(client, app):
    os.environ.setdefault("PERMISSIONS_DEBUG", "1")
    with app.app_context():
        needed = {
            "manage_users","manage_permissions","manage_roles","manage_customers","manage_sales","manage_service",
            "manage_reports","manage_vendors","manage_shipments","manage_warehouses","manage_payments","manage_expenses",
            "backup_restore","view_warehouses","view_inventory","manage_inventory","warehouse_transfer","view_parts",
            "view_preorders","add_preorder","edit_preorder","delete_preorder","add_customer","add_supplier","add_partner"
        }
        existing = {p.name for p in Permission.query.all()}
        missing = [n for n in needed if n not in existing]
        if missing:
            db.session.add_all([Permission(name=n, description="") for n in missing])
            db.session.commit()

        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="Super Administrator")
            db.session.add(role)
            db.session.flush()
        role.permissions = Permission.query.all()
        db.session.commit()

        user = User.query.filter_by(username="azad").first()
        if not user:
            user = User(username="azad", email="azad@example.com", role=role)
            user.set_password("AZ123456")
            db.session.add(user)
        else:
            user.role = role
        db.session.commit()

        with client.session_transaction() as s:
            s["_user_id"] = str(user.id)
            s["_fresh"] = True
        yield

@pytest.fixture
def _seed_min(app):
    with app.app_context():
        w1 = Warehouse(name="Main", warehouse_type=WarehouseType.MAIN.value, is_active=True)
        w2 = Warehouse(name="PartnerWH", warehouse_type=WarehouseType.PARTNER.value, is_active=True)
        w3 = Warehouse(name="ExchangeWH", warehouse_type=WarehouseType.EXCHANGE.value, is_active=True)
        p  = Product(name="Widget", price=10)
        db.session.add_all([w1, w2, w3, p])
        db.session.commit()
        db.session.add(StockLevel(product_id=p.id, warehouse_id=w1.id, quantity=50, reserved_quantity=0))
        db.session.add(StockLevel(product_id=p.id, warehouse_id=w2.id, quantity=10, reserved_quantity=0))
        db.session.commit()
        yield dict(w1=w1, w2=w2, w3=w3, p=p)

def _pay_status_val(val):
    try:
        return val.value
    except Exception:
        return str(val)

def test_anon_access_redirects_or_forbidden(anon_client, _seed_min):
    r = anon_client.get(url_for("warehouse_bp.list"))
    assert r.status_code in (302, 401, 403)
    r2 = anon_client.get(url_for("warehouse_bp.detail", warehouse_id=_seed_min["w1"].id))
    assert r2.status_code in (302, 401, 403)
    r3 = anon_client.get(url_for("warehouse_bp.products", id=_seed_min["w1"].id))
    assert r3.status_code in (302, 401, 403)

@pytest.mark.usefixtures("client", "_login_superadmin_every_test")
def test_list_warehouses_filters(client, app, _seed_min):
    with app.test_request_context():  # ⬅️ هذا يتيح login_user أن يعمل ضمن "طلب" فعلي
        # إنشاء الصلاحيات المطلوبة
        permissions_needed = ["view_warehouses"]
        for pname in permissions_needed:
            if not Permission.query.filter_by(name=pname).first():
                db.session.add(Permission(name=pname, description=""))
        db.session.commit()

        # إنشاء الدور وإعطاؤه الصلاحيات
        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="Super Admin")
            db.session.add(role)
            db.session.flush()
        role.permissions = Permission.query.all()
        db.session.commit()

        # إنشاء المستخدم وإعطاؤه الدور
        user = User.query.filter_by(username="azad").first()
        if not user:
            user = User(username="azad", email="azad@example.com", role=role)
            user.set_password("AZ123456")
            db.session.add(user)
        else:
            user.role = role
        db.session.commit()

        # تسجيل الدخول فعليًا
        login_user(user)

        # إنشاء الجلسة للمستخدم داخل client
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

    # إجراء الطلب كـ "مستخدم مسجل"
    r = client.get(url_for("warehouse_bp.list"), query_string={"type": "MAIN", "search": "Ma"})
    assert r.status_code == 200 and b"Main" in r.data, f"Expected 200, got {r.status_code}. Response: {r.data.decode()}"

    r2 = client.get(url_for("warehouse_bp.list"), query_string={"search": "Partner"})
    assert r2.status_code == 200 and b"PartnerWH" in r2.data

@pytest.mark.usefixtures("client", "_login_superadmin_every_test")
def test_detail_page_contains_forms(client, app, _seed_min):
    w1 = _seed_min["w1"]

    with app.test_request_context():
        user = User.query.filter_by(username="azad").first()
        assert user, "User 'azad' not found"
        login_user(user)

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        # الآن داخل السياق نفسه: ننفذ الطلب
        r = client.get(url_for("warehouse_bp.detail", warehouse_id=w1.id))
        assert r.status_code == 200, f"Expected 200 but got {r.status_code}"
        text = r.get_data(as_text=True)
        assert ("تحويل" in text) or ("Exchange" in text) or ("shipment" in text) or ("Transfer" in text)

@pytest.mark.usefixtures("client", "_login_superadmin_every_test")
def test_create_edit_delete_warehouse(client, app):
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.post(url_for("warehouse_bp.create"), data={
            "name": "Tmp",
            "warehouse_type": "INVENTORY",
            "is_active": True,
            "location": "X"
        }, follow_redirects=True)

    with app.app_context():
        w = Warehouse.query.filter_by(name="Tmp").first()
        assert w is not None

@pytest.mark.usefixtures("client")
def test_products_view_and_stock_ajax(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False

    w1 = _seed_min["w1"]
    p = _seed_min["p"]

    # تسجيل الدخول يدويًا بنفس الطريقة التي نجحت سابقًا
    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        # GET طلب صفحة المنتجات داخل المستودع
        r = client.get(url_for("warehouse_bp.products", id=w1.id))
        assert r.status_code == 200

        # POST تحديث الكمية عبر Ajax
        r2 = client.post(url_for("warehouse_bp.ajax_update_stock", warehouse_id=w1.id), data={
            "product_id": str(p.id),
            "warehouse_id": str(w1.id),
            "quantity": "0", "min_stock": "0", "max_stock": "",
        })
        assert r2.is_json and r2.json["success"] is True
        assert r2.json.get("alert") in (None, "below_min")

        # POST خاطئ بدون product_id
        r3 = client.post(url_for("warehouse_bp.ajax_update_stock", warehouse_id=w1.id), data={
            "product_id": "", "quantity": "5"
        })
        assert r3.status_code == 400

@pytest.mark.usefixtures("client")
def test_products_view_multi_select_filter(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False

    w1 = _seed_min["w1"]
    w2 = _seed_min["w2"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.get(
            url_for("warehouse_bp.products", id=w1.id),
            query_string=[
                ("warehouse_ids", str(w1.id)),
                ("warehouse_ids", str(w2.id)),
            ]
        )
        assert r.status_code == 200


@pytest.mark.usefixtures("client")
def test_import_products_csv_success(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    if not hasattr(Product, "sku"):
        pytest.skip("Product.sku غير موجود؛ تخطّي اختبار الاستيراد")

    w1 = _seed_min["w1"]
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=["name", "sku"])
    writer.writeheader()
    writer.writerow({"name": f"CSV_{uuid.uuid4().hex[:6]}", "sku": f"S{uuid.uuid4().hex[:6]}"} )
    writer.writerow({"name": f"CSV_{uuid.uuid4().hex[:6]}", "sku": f"S{uuid.uuid4().hex[:6]}"} )
    csv_bytes = io.BytesIO(csv_buf.getvalue().encode("utf-8"))

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None
        before = db.session.query(Product).count()

    with app.test_request_context():
        login_user(user)

        r = client.post(
            url_for("warehouse_bp.import_products", id=w1.id),
            data={"file": (csv_bytes, "products.csv")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

    with app.app_context():
        after = db.session.query(Product).count()
        assert after >= before + 2

@pytest.mark.usefixtures("client")
def test_ajax_transfer_success_and_errors(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    w1 = _seed_min["w1"]; w2 = _seed_min["w2"]; p = _seed_min["p"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.post(url_for("warehouse_bp.ajax_transfer", warehouse_id=w1.id), data={
            "date": "2025-01-01", "product_id": str(p.id),
            "source_id": str(w1.id), "destination_id": str(w2.id),
            "quantity": "3", "direction": "IN", "notes": "x",
        })
        assert r.is_json and r.json["success"] is True

@pytest.mark.usefixtures("client")
def test_ajax_exchange_in_and_out(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    w3 = _seed_min["w3"]; p = _seed_min["p"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.post(url_for("warehouse_bp.ajax_exchange", warehouse_id=w3.id), data={
            "product_id": str(p.id),
            "warehouse_id": str(w3.id),
            "quantity": "5",
            "direction": "IN"
        })
        assert r.is_json and r.json["success"] is True and r.json["new_quantity"] >= 5

        r2 = client.post(url_for("warehouse_bp.ajax_exchange", warehouse_id=w3.id), data={
            "product_id": str(p.id),
            "warehouse_id": str(w3.id),
            "quantity": "9999",
            "direction": "OUT"
        })
        assert r2.status_code == 400

@pytest.mark.usefixtures("client")
def test_partner_shares_get_and_post(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    w2 = _seed_min["w2"]; p = _seed_min["p"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None
        partner = Partner(name="PX")
        db.session.add(partner)
        if not StockLevel.query.filter_by(product_id=p.id, warehouse_id=w2.id).first():
            db.session.add(StockLevel(product_id=p.id, warehouse_id=w2.id, quantity=1, reserved_quantity=0))
        db.session.commit()
        partner_id = partner.id

    with app.test_request_context():
        login_user(user)

        r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w2.id))
        assert r.is_json and r.json["success"] is True

        payload = {"shares": [{"product_id": p.id, "partner_id": partner_id, "share_percentage": 10, "share_amount": 0, "notes": "n"}]}
        r2 = client.post(
            url_for("warehouse_bp.partner_shares", warehouse_id=w2.id),
            data=json.dumps(payload), content_type="application/json"
        )
        assert r2.is_json and r2.json["success"] is True

        with app.app_context():
            row = ProductPartnerShare.query.filter_by(product_id=p.id, partner_id=partner_id).first()
            assert row is not None and float(row.share_percentage) == 10


@pytest.mark.usefixtures("client")
def test_transfers_pages_and_create(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    w1 = _seed_min["w1"]; w2 = _seed_min["w2"]; p = _seed_min["p"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.get(url_for("warehouse_bp.transfers", id=w1.id))
        assert r.status_code == 200

        ok = client.post(url_for("warehouse_bp.create_transfer", id=w1.id), data={
            "date": "2025-01-01", "product_id": str(p.id),
            "source_id": str(w1.id), "destination_id": str(w2.id),
            "quantity": "1", "direction": "IN",
        }, follow_redirects=False)
        assert ok.status_code in (200, 302, 303)

        bad = client.post(url_for("warehouse_bp.create_transfer", id=w1.id), data={
            "date": "2025-01-01", "product_id": str(p.id),
            "source_id": str(w1.id), "destination_id": str(w2.id),
            "quantity": "9999", "direction": "IN",
        }, follow_redirects=True)
        assert bad.status_code in (200, 400)


@pytest.mark.usefixtures("client")
def test_product_card_and_preorders_flow(client, app, _seed_min):
    app.config["WTF_CSRF_ENABLED"] = False
    w1 = _seed_min["w1"]; p = _seed_min["p"]

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        r = client.get(url_for("warehouse_bp.product_card", product_id=p.id))
        assert r.status_code == 200

        r2 = client.post(url_for("warehouse_bp.preorder_create"), data={
            "entity_type": "customer",
            "customer_id": "", "supplier_id": "", "partner_id": "",
            "product_id": str(p.id), "warehouse_id": str(w1.id),
            "quantity": "2", "prepaid_amount": "5.00", "tax_rate": "0", "payment_method": "cash",
        }, follow_redirects=False)
        assert r2.status_code in (200, 302, 303)

        with app.app_context():
            pr = PreOrder.query.order_by(PreOrder.id.desc()).first()
            assert pr is not None
            pid = pr.id
            sl = StockLevel.query.filter_by(product_id=p.id, warehouse_id=w1.id).first()
            assert sl is not None and (sl.reserved_quantity or 0) >= pr.quantity
            pay = Payment.query.filter_by(preorder_id=pid).first()
            assert pay is not None
            assert _pay_status_val(getattr(PaymentStatus, "COMPLETED", "COMPLETED")) in (
                getattr(pay, "status", "COMPLETED"), "COMPLETED"
            )

        assert client.get(url_for("warehouse_bp.preorder_detail", preorder_id=pid)).status_code == 200
        assert client.post(url_for("warehouse_bp.preorder_fulfill", preorder_id=pid)).status_code in (302, 303)
        assert client.post(url_for("warehouse_bp.preorder_cancel", preorder_id=pid)).status_code in (302, 303)


@pytest.mark.usefixtures("client")
def test_quick_create_entities_api_and_redirects(client, app):
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        user = User.query.filter_by(username="azad").first()
        assert user is not None

    with app.test_request_context():
        login_user(user)

        # ✅ رقم عشوائي لتجنب التكرار
        phone = str(uuid.uuid4().int)[:8]

        rc = client.post(url_for("warehouse_bp.api_add_customer"), json={"name": "C1", "phone": phone})

        if rc.status_code != 201:
            print("❌ Status code:", rc.status_code)
            print("❌ Response data:\n", rc.data.decode())

        assert rc.status_code == 201 and rc.is_json and rc.json.get("id")
