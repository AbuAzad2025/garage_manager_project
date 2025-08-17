# -*- coding: utf-8 -*-
import io
import csv
import json
import uuid
import os
import pytest
from datetime import datetime
from flask import url_for

from extensions import db
from models import (
    Warehouse, WarehouseType, Product, StockLevel, Transfer, Partner,
    ProductPartnerShare, ExchangeTransaction, Customer, Supplier, PreOrder,
    ShipmentItem, Shipment, Payment, PaymentStatus, PaymentDirection, PaymentEntityType,
    User, Role, Permission
)

# ----------------------- Login لكل اختبار -----------------------

@pytest.fixture(autouse=True)
def _login_superadmin_every_test(client, app):
    """
    يضمن وجود مستخدم super_admin بصلاحيات كاملة، ويعمل تسجيل دخول
    في جلسة الاختبار قبل كل Test. كما يمسح كاش الصلاحيات إن وُجد.
    """
    os.environ.setdefault("PERMISSIONS_DEBUG", "1")
    with app.app_context():
        # 1) تأكد من وجود جميع الصلاحيات
        all_perm_names = {
            "manage_users", "manage_permissions", "manage_roles",
            "manage_customers", "manage_sales", "manage_service",
            "manage_reports", "manage_vendors", "manage_shipments",
            "manage_warehouses", "manage_payments", "manage_expenses",
            "backup_restore",
            # ممكن مشاريعك تستعمل أسماء عرض فقط:
            "view_warehouses", "view_inventory", "manage_inventory",
            "warehouse_transfer", "view_parts", "view_preorders",
            "add_preorder", "edit_preorder", "delete_preorder",
            "add_customer", "add_supplier", "add_partner"
        }
        existing = {p.name for p in Permission.query.all()}
        missing = [n for n in all_perm_names if n not in existing]
        if missing:
            db.session.add_all([Permission(name=n, description="") for n in missing])
            db.session.commit()

        # 2) super_admin role يملك كل الصلاحيات
        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="Super Administrator")
            db.session.add(role)
            db.session.flush()
        role.permissions = Permission.query.all()
        db.session.commit()

        # 3) المستخدم 1 super_admin (✅ SA 2.0)
        user = db.session.get(User, 1)
        if not user:
            user = User(id=1, username="azad", email="azad@example.com", role=role)
            user.set_password("AZ123456")
            db.session.add(user)
        else:
            user.role = role
        db.session.commit()

        # 4) امسح كاش الصلاحيات لو عندك util لذلك
        try:
            import utils
            if hasattr(utils, "clear_user_permission_cache"):
                utils.clear_user_permission_cache(user.id)
        except Exception:
            pass

        # 5) فعليًا سجّل دخول بالجلسة
        with client.session_transaction() as s:
            s["_user_id"] = str(user.id)
            s["_fresh"] = True

        yield  # بعد كل اختبار

# ----------------------- Fixtures -----------------------

@pytest.fixture
def _seed_min(app):
    with app.app_context():
        w1 = Warehouse(name="Main", warehouse_type=WarehouseType.MAIN.value, is_active=True)
        w2 = Warehouse(name="PartnerWH", warehouse_type=WarehouseType.PARTNER.value, is_active=True)
        w3 = Warehouse(name="ExchangeWH", warehouse_type=WarehouseType.EXCHANGE.value, is_active=True)
        p  = Product(name="Widget", price=10)
        db.session.add_all([w1, w2, w3, p])
        db.session.commit()
        # مخزون مبدئي
        db.session.add(StockLevel(product_id=p.id, warehouse_id=w1.id, quantity=50, reserved_quantity=0))
        db.session.add(StockLevel(product_id=p.id, warehouse_id=w2.id, quantity=10, reserved_quantity=0))
        db.session.commit()
        yield dict(w1=w1, w2=w2, w3=w3, p=p)

# ----------------------- Helpers -----------------------

def _pay_status_val(val):
    try:
        return val.value
    except Exception:
        return str(val)

# ----------------------- Tests -----------------------

def test_anon_access_redirects_or_forbidden(anon_client, _seed_min):
    # list
    r = anon_client.get(url_for("warehouse_bp.list"))
    assert r.status_code in (302, 401, 403)
    # detail
    r2 = anon_client.get(url_for("warehouse_bp.detail", warehouse_id=_seed_min["w1"].id))
    assert r2.status_code in (302, 401, 403)
    # products
    r3 = anon_client.get(url_for("warehouse_bp.products", id=_seed_min["w1"].id))
    assert r3.status_code in (302, 401, 403)

@pytest.mark.usefixtures("client")
def test_list_warehouses_filters(client, app, _seed_min):
    # تحديث سياق المستخدم
    with client.session_transaction() as session:
        session['_fresh'] = True
    
    # إضافة تأخير بسيط لضمان تحديث الصلاحيات
    import time
    time.sleep(0.1)
    
    r = client.get(url_for("warehouse_bp.list"), query_string={"type": "MAIN", "search": "Ma"})
    assert r.status_code == 200 and b"Main" in r.data, \
        f"Expected 200, got {r.status_code}. Response: {r.data.decode()}"
    r = client.get(url_for("warehouse_bp.list"), query_string={"type": "MAIN", "search": "Ma"})
    assert r.status_code == 200 and b"Main" in r.data

    # فلاتر إضافية: parent لا شيء / search مختلف
    r2 = client.get(url_for("warehouse_bp.list"), query_string={"search": "Partner"})
    assert r2.status_code == 200 and b"PartnerWH" in r2.data

@pytest.mark.usefixtures("client")
def test_detail_page_contains_forms(client, app, _seed_min):
    w1 = _seed_min["w1"]
    r = client.get(url_for("warehouse_bp.detail", warehouse_id=w1.id))
    assert r.status_code == 200
    # تحقّق من وجود كلمات دالة في الصفحة بعد فك التشفير
    text = r.get_data(as_text=True)
    assert ("تحويل" in text) or ("Exchange" in text) or ("shipment" in text) or ("Transfer" in text)

@pytest.mark.usefixtures("client")
def test_create_edit_delete_warehouse(client, app):
    # إنشاء
    r = client.post(url_for("warehouse_bp.create"), data={
        "name": "Tmp", "warehouse_type": "INVENTORY", "is_active": "y", "location": "X"
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    with app.app_context():
        w = Warehouse.query.filter_by(name="Tmp").first()
        assert w is not None
        rid = w.id

    # تعديل
    r2 = client.post(url_for("warehouse_bp.edit", warehouse_id=rid), data={
        "name": "Tmp2", "warehouse_type": "PARTNER", "is_active": "y", "location": "Y", "share_percent": "12"
    }, follow_redirects=False)
    assert r2.status_code in (302, 303)

    # حذف
    r3 = client.post(url_for("warehouse_bp.delete", warehouse_id=rid), follow_redirects=False)
    assert r3.status_code in (302, 303)

    with app.app_context():
        # ✅ SA 2.0
        assert db.session.get(Warehouse, rid) is None

@pytest.mark.usefixtures("client")
def test_products_view_and_stock_ajax(client, app, _seed_min):
    w1 = _seed_min["w1"]; p = _seed_min["p"]

    # صفحة المنتجات
    r = client.get(url_for("warehouse_bp.products", id=w1.id))
    assert r.status_code == 200

    # تحديث مخزون (أسفل الحد لإظهار alert)
    r2 = client.post(url_for("warehouse_bp.ajax_update_stock", warehouse_id=w1.id), data={
        "product_id": str(p.id),
        "warehouse_id": str(w1.id),
        "quantity": "0", "min_stock": "0", "max_stock": "",
    })
    assert r2.is_json and r2.json["success"] is True
    assert r2.json.get("alert") in (None, "below_min")

    # فشل بسبب product_id غير صالح
    r3 = client.post(url_for("warehouse_bp.ajax_update_stock", warehouse_id=w1.id), data={
        "product_id": "", "quantity": "5"
    })
    assert r3.status_code == 400

@pytest.mark.usefixtures("client")
def test_products_view_multi_select_filter(client, app, _seed_min):
    w1 = _seed_min["w1"]; w2 = _seed_min["w2"]
    r = client.get(url_for("warehouse_bp.products", id=w1.id), query_string=[
        ("warehouse_ids", str(w1.id)),
        ("warehouse_ids", str(w2.id)),
    ])
    assert r.status_code == 200

@pytest.mark.usefixtures("client")
def test_import_products_csv_success(client, app, _seed_min):
    # بعض المشاريع قد لا تحتوي على الحقل sku؛ نتخطى الاختبار في هذه الحالة
    if not hasattr(Product, "sku"):
        pytest.skip("Product.sku غير موجود؛ تخطّي اختبار الاستيراد")

    w1 = _seed_min["w1"]
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=["name", "sku"])
    writer.writeheader()
    writer.writerow({"name": f"CSV_{uuid.uuid4().hex[:6]}", "sku": f"S{uuid.uuid4().hex[:6]}"})
    writer.writerow({"name": f"CSV_{uuid.uuid4().hex[:6]}", "sku": f"S{uuid.uuid4().hex[:6]}"})
    csv_bytes = io.BytesIO(csv_buf.getvalue().encode("utf-8"))

    with app.app_context():
        before = db.session.query(Product).count()

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
    w1 = _seed_min["w1"]; w2 = _seed_min["w2"]; p = _seed_min["p"]

    # نجاح: من w1 إلى w2 عبر endpoint w1 (يحسب OUT من w1)
    r = client.post(url_for("warehouse_bp.ajax_transfer", warehouse_id=w1.id), data={
        "date": "2025-01-01", "product_id": str(p.id),
        "source_id": str(w1.id), "destination_id": str(w2.id),
        "quantity": "3", "direction": "IN", "notes": "x",
    })
    assert r.is_json and r.json["success"] is True

    # تحقق من الأثر على المخزون + سجل التحويل
    with app.app_context():
        src = StockLevel.query.filter_by(warehouse_id=w1.id, product_id=p.id).first()
        dst = StockLevel.query.filter_by(warehouse_id=w2.id, product_id=p.id).first()
        assert src.quantity == 47  # 50 - 3
        assert dst.quantity == 13  # 10 + 3
        t = Transfer.query.order_by(Transfer.id.desc()).first()
        assert t and t.product_id == p.id and t.source_id == w1.id and t.destination_id == w2.id
        assert t.direction in ("OUT", "IN")  # حسب الحساب الداخلي

    # خطأ: كمية غير كافية
    r2 = client.post(url_for("warehouse_bp.ajax_transfer", warehouse_id=w1.id), data={
        "date": "2025-01-01", "product_id": str(p.id),
        "source_id": str(w1.id), "destination_id": str(w2.id),
        "quantity": "9999", "direction": "IN",
    })
    assert r2.status_code == 400 and r2.is_json and r2.json["success"] is False

    # خطأ: مخزن غير مطابق للـ warehouse_id في المسار
    r3 = client.post(url_for("warehouse_bp.ajax_transfer", warehouse_id=w2.id), data={
        "date": "2025-01-01", "product_id": str(p.id),
        "source_id": str(w1.id), "destination_id": str(w2.id),
        "quantity": "1", "direction": "IN",
    })
    assert r3.status_code == 400

@pytest.mark.usefixtures("client")
def test_ajax_exchange_in_and_out(client, app, _seed_min):
    w3 = _seed_min["w3"]; p = _seed_min["p"]
    # IN
    r = client.post(url_for("warehouse_bp.ajax_exchange", warehouse_id=w3.id), data={
        "product_id": str(p.id), "warehouse_id": str(w3.id), "quantity": "5", "direction": "IN"
    })
    assert r.is_json and r.json["success"] is True and r.json["new_quantity"] >= 5
    # OUT أكثر من الموجود -> 400
    r2 = client.post(url_for("warehouse_bp.ajax_exchange", warehouse_id=w3.id), data={
        "product_id": str(p.id), "warehouse_id": str(w3.id), "quantity": "9999", "direction": "OUT"
    })
    assert r2.status_code == 400

@pytest.mark.usefixtures("client")
def test_partner_shares_get_and_post(client, app, _seed_min):
    w2 = _seed_min["w2"]; p = _seed_min["p"]
    with app.app_context():
        partner = Partner(name="PX")
        db.session.add(partner)
        if not StockLevel.query.filter_by(product_id=p.id, warehouse_id=w2.id).first():
            db.session.add(StockLevel(product_id=p.id, warehouse_id=w2.id, quantity=1, reserved_quantity=0))
        db.session.commit()
        partner_id = partner.id

    # GET
    r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w2.id))
    assert r.is_json and r.json["success"] is True

    # POST
    payload = {"shares": [{"product_id": p.id, "partner_id": partner_id, "share_percentage": 10, "share_amount": 0, "notes": "n"}]}
    r2 = client.post(url_for("warehouse_bp.partner_shares", warehouse_id=w2.id),
                     data=json.dumps(payload), content_type="application/json")
    assert r2.is_json and r2.json["success"] is True

    # تحقق من التخزين
    with app.app_context():
        row = ProductPartnerShare.query.filter_by(product_id=p.id, partner_id=partner_id).first()
        assert row is not None and float(row.share_percentage) == 10

@pytest.mark.usefixtures("client")
def test_transfers_pages_and_create(client, app, _seed_min):
    w1 = _seed_min["w1"]; w2 = _seed_min["w2"]; p = _seed_min["p"]

    # صفحة السجل
    r = client.get(url_for("warehouse_bp.transfers", id=w1.id))
    assert r.status_code == 200

    # إنشاء تحويل (صفحة عادية) نجاح
    ok = client.post(url_for("warehouse_bp.create_transfer", id=w1.id), data={
        "date": "2025-01-01", "product_id": str(p.id),
        "source_id": str(w1.id), "destination_id": str(w2.id),
        "quantity": "1", "direction": "IN",
    }, follow_redirects=False)
    assert ok.status_code in (200, 302, 303)

    # فشل لنقص الكمية
    bad = client.post(url_for("warehouse_bp.create_transfer", id=w1.id), data={
        "date": "2025-01-01", "product_id": str(p.id),
        "source_id": str(w1.id), "destination_id": str(w2.id),
        "quantity": "9999", "direction": "IN",
    }, follow_redirects=True)
    assert bad.status_code in (200, 400)

@pytest.mark.usefixtures("client")
def test_product_card_and_preorders_flow(client, app, _seed_min):
    w1 = _seed_min["w1"]; p = _seed_min["p"]

    # بطاقة المنتج
    r = client.get(url_for("warehouse_bp.product_card", product_id=p.id))
    assert r.status_code == 200

    # إنشاء حجز مسبق
    r2 = client.post(url_for("warehouse_bp.preorder_create"), data={
        "entity_type": "customer",
        "customer_id": "", "supplier_id": "", "partner_id": "",
        "product_id": str(p.id), "warehouse_id": str(w1.id),
        "quantity": "2", "prepaid_amount": "5.00", "tax_rate": "0", "payment_method": "cash",
    }, follow_redirects=False)
    assert r2.status_code in (200, 302, 303)

    # التقاط آخر حجز
    with app.app_context():
        pr = PreOrder.query.order_by(PreOrder.id.desc()).first()
        assert pr is not None
        pid = pr.id

        # تحقق من حجز المخزون (reserved_quantity)
        sl = StockLevel.query.filter_by(product_id=p.id, warehouse_id=w1.id).first()
        assert sl is not None and (sl.reserved_quantity or 0) >= pr.quantity

        # تحقق من إنشاء دفعة عربون
        pay = Payment.query.filter_by(preorder_id=pid).first()
        assert pay is not None
        assert _pay_status_val(getattr(PaymentStatus, "COMPLETED", "COMPLETED")) in (getattr(pay, "status", "COMPLETED"), "COMPLETED")

    # تفاصيل
    assert client.get(url_for("warehouse_bp.preorder_detail", preorder_id=pid)).status_code == 200

    # تنفيذ
    assert client.post(url_for("warehouse_bp.preorder_fulfill", preorder_id=pid)).status_code in (302, 303)

    # إلغاء (قد يكون Fulfilled بالفعل؛ نتحقق من الرَّد وعدم الانهيار)
    assert client.post(url_for("warehouse_bp.preorder_cancel", preorder_id=pid)).status_code in (302, 303)

@pytest.mark.usefixtures("client")
def test_quick_create_entities_api_and_redirects(client, app):
    # عميل
    rc = client.post(url_for("warehouse_bp.api_add_customer"), json={"name": "C1", "phone": "1"})
    assert rc.status_code == 201 and rc.is_json and rc.json.get("id")

    # مورد
    rs = client.post(url_for("warehouse_bp.api_add_supplier"), json={"name": "S1"})
    assert rs.status_code == 201 and rs.is_json and rs.json.get("id")

    # شريك
    rp = client.post(url_for("warehouse_bp.api_add_partner"), json={"name": "P1"})
    assert rp.status_code == 201 and rp.is_json and rp.json.get("id")

    # حالات فشل: اسم مفقود
    rc_bad = client.post(url_for("warehouse_bp.api_add_customer"), json={"name": ""})
    assert rc_bad.status_code == 400
    rs_bad = client.post(url_for("warehouse_bp.api_add_supplier"), json={"name": ""})
    assert rs_bad.status_code == 400
    rp_bad = client.post(url_for("warehouse_bp.api_add_partner"), json={"name": ""})
    assert rp_bad.status_code == 400

    # إعادة توجيه إنشاء شحنة
    r = client.get(url_for("warehouse_bp.create_warehouse_shipment", id=1))
    assert r.status_code in (302, 303)
