# -*- coding: utf-8 -*-
from __future__ import annotations
from sqlalchemy import select, text as sa_text
import click
from datetime import datetime, timedelta
from decimal import Decimal
from random import randint, choice, random
from sqlalchemy import select

from flask.cli import with_appcontext
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from extensions import db
import models as M

SEED_TAG = "SEED-FULL-PS"
D0 = Decimal("0.00")


def q(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Decimal("0.01"))


# اختصارات للـ Enums (إن وُجدت)
PM = getattr(M, "PaymentMethod", None)
PST = getattr(M, "PaymentStatus", None)
PDIR = getattr(M, "PaymentDirection", None)
PET = getattr(M, "PaymentEntityType", None)
IST = getattr(M, "InvoiceStatus", None)
ISO = getattr(M, "InvoiceSource", None)
SST = getattr(M, "SaleStatus", None)
WHT = getattr(M, "WarehouseType", None)
TDIR = getattr(M, "TransferDirection", None)
SVS = getattr(M, "ServiceStatus", None)
SVP = getattr(M, "ServicePriority", None)


def _ev(enum_cls, name, default=None):
    """يعيد القيمة الصحيحة للـ Enum سواء مرّرت الاسم أو القيمة نفسها."""
    if enum_cls is None or isinstance(name, enum_cls):
        return getattr(name, "value", name) if name is not None else default
    try:
        key = str(name or "").upper()
        aliases = {"IN": "INCOMING", "OUT": "OUTGOING", "CHECK": "CHEQUE"}
        key = aliases.get(key, key)
        for m in enum_cls:
            if getattr(m, "value", None) == name:
                return m.value
        for m in enum_cls:
            if m.name.upper() == key:
                return m.value
    except Exception:
        pass
    return default or name


def commit(label="commit"):
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        print(f"[seed:{label}] IntegrityError: {e}")
    except Exception as e:
        db.session.rollback()
        print(f"[seed:{label}] Error: {e}")


def _cols(model):
    try:
        return set(model.__table__.c.keys()) if hasattr(model, "__table__") else set()
    except Exception:
        return set()


def _kw(model, **kwargs):
    cols = _cols(model)
    return {k: v for k, v in kwargs.items() if k in cols}


def _add_note(obj):
    try:
        if hasattr(obj, "notes") and not getattr(obj, "notes", None):
            obj.notes = SEED_TAG
        elif hasattr(obj, "note") and not getattr(obj, "note", None):
            obj.note = SEED_TAG
    except Exception:
        pass


def get_or_create(model, defaults=None, **unique_by):
    cols = _cols(model)
    sanitized = {k: v for k, v in (defaults or {}).items() if k in cols}
    obj = model.query.filter_by(**unique_by).first()
    if obj:
        if sanitized:
            for k, v in sanitized.items():
                if getattr(obj, k, None) in (None, "", 0):
                    setattr(obj, k, v)
        return obj, False
    obj = model(**{**sanitized, **unique_by})
    _add_note(obj)
    db.session.add(obj)
    try:
        db.session.flush()
        return obj, True
    except IntegrityError:
        db.session.rollback()
        obj = model.query.filter_by(**unique_by).first()
        if obj:
            return obj, False
        try:
            obj = model(**unique_by)
            _add_note(obj)
            db.session.add(obj)
            db.session.flush()
            return obj, True
        except IntegrityError:
            db.session.rollback()
            return None, False


# ---------------------- تنظيف بيانات السّيد السابقة ----------------------
def cleanup_previous():
    order = [
        getattr(M, "PaymentSplit", None),
        M.Payment,
        getattr(M, "InvoiceLine", None),
        M.Invoice,
        getattr(M, "SaleLine", None),
        M.Sale,
        getattr(M, "OnlinePreOrderItem", None),
        getattr(M, "OnlinePreOrder", None),
        getattr(M, "OnlineCartItem", None),
        getattr(M, "OnlineCart", None),
        getattr(M, "OnlinePayment", None),
        getattr(M, "ServiceTask", None),
        getattr(M, "ServicePart", None),
        getattr(M, "ServiceRequest", None),
        getattr(M, "PreOrder", None),
        getattr(M, "ShipmentItem", None),
        getattr(M, "Shipment", None),
        getattr(M, "ExchangeTransaction", None),
        getattr(M, "Transfer", None),
        getattr(M, "StockLevel", None),
        M.Product,
        getattr(M, "ProductCategory", None),
        getattr(M, "EquipmentType", None),
        getattr(M, "PartnerSettlement", None),
        getattr(M, "SupplierSettlement", None),
        getattr(M, "Partner", None),
        getattr(M, "Supplier", None),
        getattr(M, "Customer", None),
        getattr(M, "Warehouse", None),
        getattr(M, "Expense", None),
        getattr(M, "ExpenseType", None),
        getattr(M, "Note", None),
    ]
    for model in filter(None, order):
        try:
            if "notes" in _cols(model):
                db.session.query(model).filter(model.notes == SEED_TAG).delete(
                    synchronize_session=False
                )
        except Exception:
            db.session.rollback()
    commit("cleanup")

def _ensure_user_id() -> int:
    """يضمن وجود مستخدم واحد على الأقل ويُرجِع ID صالح للبائع."""
    U = getattr(M, "User", None)
    if not U:
        raise RuntimeError("Model User غير موجود.")
    # جرّب أولًا مستخدمًا موجودًا
    uid = db.session.execute(sa_text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
    if uid:
        return int(uid)
    # لو مفيش، أنشئ واحدًا بسيطًا
    u = U(username="seed_seller", email="seed_seller@example.com", is_active=True, notes=SEED_TAG)
    if hasattr(u, "set_password"):
        u.set_password("password123")
    db.session.add(u)
    db.session.flush()
    return int(u.id)

from sqlalchemy import text as sa_text

def _ensure_customer_id(fallback_customer=None) -> int:
    C = getattr(M, "Customer", None)
    if not C:
        raise RuntimeError("Model Customer غير موجود.")
    if getattr(fallback_customer, "id", None):
        return int(fallback_customer.id)
    cid = db.session.execute(sa_text("SELECT id FROM customers ORDER BY id LIMIT 1")).scalar()
    if cid:
        return int(cid)
    # لو ما في عملاء لأي سبب، أنشئ عميل افتراضي مضمون
    cust = C(
        name="العميل الافتراضي",
        phone="+970599000000",
        whatsapp="+970599000000" if "whatsapp" in C.__table__.c else None,
        email="default@clients.ps",
        address="فلسطين",
        currency="ILS",
        credit_limit=0,
        discount_rate=0,
        is_active=True,
        is_online=False if "is_online" in C.__table__.c else None,
        notes=SEED_TAG,
    )
    db.session.add(cust)
    db.session.flush()
    return int(cust.id)
# ---------------------- موردين/شركاء/موظفين ----------------------
def seed_suppliers_partners_employees():
    suppliers = []
    for row in [
        dict(name="شركة القدس للتجارة", email="qods@supplier.ps", address="القدس"),
        dict(name="مورد غزة الموحد", email="gaza@supplier.ps", address="غزة"),
        dict(name="مجموعة رام الله للمحركات", email="ramallah@supplier.ps", address="رام الله"),
        dict(name="الخليل للصناعات المعدنية", email="hebron@supplier.ps", address="الخليل"),
    ]:
        s, _ = get_or_create(
            M.Supplier,
            name=row["name"],
            defaults=dict(currency="ILS", is_local=True, notes=SEED_TAG, **row),
        )
        suppliers.append(s)

    partners = []
    Partner = getattr(M, "Partner", None)
    if Partner:
        for row in [
            dict(
                name="شريك البيرة للتجارة",
                email="partner.albireh@partner.ps",
                share_percentage=20,
                currency="ILS",
            ),
            dict(
                name="شريك بيت لحم",
                email="bethlehem@partner.ps",
                share_percentage=35,
                currency="ILS",
            ),
        ]:
            p, _ = get_or_create(
                Partner, name=row["name"], defaults=dict(balance=D0, notes=SEED_TAG, **row)
            )
            partners.append(p)

    employees = []
    Employee = getattr(M, "Employee", None)
    if Employee:
        for row in [
            dict(name="كريم البرغوثي", position="فني", email="karim@garage.ps"),
            dict(name="ليان عطية", position="محاسِبة", email="layan@garage.ps"),
        ]:
            e, _ = get_or_create(
                Employee, name=row["name"], defaults=dict(currency="ILS", notes=SEED_TAG, **row)
            )
            employees.append(e)

    commit("suppliers-partners-employees")
    return suppliers, partners, employees


# ---------------------- تصنيفات ومعدات ----------------------
def seed_categories_equipment():
    cats = [
        get_or_create(M.ProductCategory, name=n, defaults=dict(notes=SEED_TAG))[0]
        for n in ["زيوت", "فلاتر", "قطع ميكانيكية", "كهرباء", "إكسسوارات", "إطارات", "بطاريات", "سوائل تبريد", "فرامل"]
    ]
    ets = []
    if getattr(M, "EquipmentType", None):
        for n in ["سيارة ركوب", "شاحنة خفيفة", "فان تجاري", "معدة ثقيلة", "دراجة نارية"]:
            ets.append(get_or_create(M.EquipmentType, name=n, defaults=dict(notes=SEED_TAG))[0])
    commit("categories-equipment")
    return cats, ets


# ---------------------- مخزون ----------------------
def ensure_stock_row(product_id: int, warehouse_id: int):
    prod = db.session.get(M.Product, product_id)
    wh = db.session.get(M.Warehouse, warehouse_id)
    if not prod or not wh:
        raise RuntimeError(
            f"Bad FK: product_id={product_id} or warehouse_id={warehouse_id} not found"
        )

    row = M.StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
    if row:
        return row

    row = M.StockLevel(
        **_kw(M.StockLevel, product_id=product_id, warehouse_id=warehouse_id, quantity=0, reserved_quantity=0)
    )
    _add_note(row)
    db.session.add(row)
    db.session.flush()
    return row


def get_or_create_online_warehouse():
    wt_online = _ev(WHT, "ONLINE", _ev(WHT, "MAIN", None))
    wh = M.Warehouse.query.filter_by(warehouse_type=wt_online, is_active=True).first()
    if not wh:
        wh = M.Warehouse(
            **_kw(
                M.Warehouse,
                name="ONLINE",
                warehouse_type=wt_online,
                is_active=True,
                location="WWW",
            )
        )
        _add_note(wh)
        db.session.add(wh)
        db.session.flush()

    if hasattr(wh, "online_slug") and not getattr(wh, "online_slug", None):
        wh.online_slug = "default"
    if hasattr(wh, "online_is_default"):
        wh.online_is_default = True
    return wh


def ensure_online_stock_level(product_id: int):
    wh = get_or_create_online_warehouse()
    ensure_stock_row(product_id, wh.id)
    return wh.id


def seed_warehouses(suppliers, partners):
    main, _ = get_or_create(
        M.Warehouse,
        name="الرئيسي - رام الله",
        defaults=dict(warehouse_type=_ev(WHT, "MAIN"), location="رام الله", is_active=True, notes=SEED_TAG),
    )
    exchange, _ = get_or_create(
        M.Warehouse,
        name="تبادل - مورد القدس",
        defaults=dict(
            warehouse_type=_ev(WHT, "EXCHANGE"),
            location="القدس",
            is_active=True,
            supplier_id=getattr(suppliers[0], "id", None),
            notes=SEED_TAG,
        ),
    )
    partner, _ = get_or_create(
        M.Warehouse,
        name="شريك - البيرة",
        defaults=dict(
            warehouse_type=_ev(WHT, "PARTNER"),
            location="البيرة",
            is_active=True,
            partner_id=getattr(partners[0], "id", None) if partners else None,
            share_percent=40,
            notes=SEED_TAG,
        ),
    )
    online = get_or_create_online_warehouse()
    db.session.flush()
    commit("warehouses")
    return main, exchange, partner, online


# ---------------------- منتجات ----------------------
def seed_products(cats, ets, suppliers):
    cat = {c.name: c for c in cats}
    et = ets[0] if ets else None
    sup = suppliers[0] if suppliers else None
    base = [
        dict(sku="PS-OIL-5W30", name="زيت محرك 5W-30", brand="Castrol", part_number="5W30-1L", price=35, purchase_price=20, category=cat["زيوت"]),
        dict(sku="PS-FLTR-OP123", name="فلتر زيت OP123", brand="MANN", part_number="OP123", price=25, purchase_price=12, category=cat["فلاتر"]),
        dict(sku="PS-BATT-70AH", name="بطارية 70 أمبير", brand="VARTA", part_number="70AH", price=380, purchase_price=300, category=cat["بطاريات"]),
        dict(sku="PS-BELT-ALT", name="سير دينامو", brand="Gates", part_number="ALT-BELT", price=90, purchase_price=60, category=cat["قطع ميكانيكية"]),
        dict(sku="PS-LAMP-H7", name="لمبة H7 55W", brand="Philips", part_number="H7-55W", price=18, purchase_price=10, category=cat["كهرباء"]),
        dict(sku="PS-WIPER-22", name="مساحات 22 إنش", brand="Bosch", part_number="WIP-22", price=28, purchase_price=16, category=cat["إكسسوارات"]),
    ]
    prods = []
    for r in base:
        d = dict(
            name=r["name"],
            brand=r["brand"],
            part_number=r["part_number"],
            price=r["price"],
            purchase_price=r["purchase_price"],
            category_id=r["category"].id,
            vehicle_type_id=getattr(et, "id", None),
            supplier_id=getattr(sup, "id", None),
            condition=getattr(M, "ProductCondition", None) and M.ProductCondition.NEW or "NEW",
            is_active=True,
            notes=SEED_TAG,
        )
        p, _ = get_or_create(M.Product, sku=r["sku"], defaults=d)
        prods.append(p)

    for i in range(30):
        c = choice(cats)
        e = choice(ets) if ets else None
        s = choice(suppliers) if suppliers else None
        p, _ = get_or_create(
            M.Product,
            sku=f"SKU-AUTO-{i+1:03d}",
            defaults=dict(
                name=f"منتج عام {i+1:03d}",
                brand=choice(["Generic", "OEM", "ProLine"]),
                part_number=f"PN-{i+1:03d}",
                price=randint(10, 400),
                purchase_price=randint(5, 300),
                category_id=c.id,
                vehicle_type_id=getattr(e, "id", None),
                supplier_id=getattr(s, "id", None),
                condition=getattr(M, "ProductCondition", None) and M.ProductCondition.NEW or "NEW",
                is_active=True,
                notes=SEED_TAG,
            ),
        )
        prods.append(p)
        db.session.flush()
    commit("products")
    return prods


# ---------------------- تعبئة المخزون ----------------------
def seed_stock(products, main, exchange, partner, online):
    for p in products:
        for wh, qty in [(main, randint(20, 120)), (choice([exchange, partner, main]), randint(0, 60))]:
            row = ensure_stock_row(p.id, wh.id)
            if (row.quantity or 0) < qty:
                row.quantity = qty
        ensure_online_stock_level(p.id)
        db.session.flush()
    commit("stock")


# ---------------------- شحن/تحويلات ----------------------
def seed_shipments_exchange_transfers(main, exchange, partner, products):
    shp, _ = get_or_create(
        M.Shipment,
        notes=SEED_TAG,
        defaults=dict(
            origin="مرسين",
            destination="رام الله",
            currency="USD",
            shipment_date=datetime.utcnow() - timedelta(days=7),
            expected_arrival=datetime.utcnow() - timedelta(days=1),
            status="IN_TRANSIT",
        ),
    )
    db.session.flush()

    def add_item(prod, qty, cost):
        it = M.ShipmentItem.query.filter_by(
            shipment_id=shp.id, product_id=prod.id, warehouse_id=main.id
        ).first()
        if not it:
            o = M.ShipmentItem(
                **_kw(
                    M.ShipmentItem,
                    shipment_id=shp.id,
                    product_id=prod.id,
                    warehouse_id=main.id,
                    quantity=qty,
                    unit_cost=q(cost),
                )
            )
            _add_note(o)
            db.session.add(o)

    for spec in [
        (products[0], 20, 300),
        (products[1], 60, 30),
        (products[2], 80, 220),
        (products[3], 15, 140),
        (products[4], 40, 180),
    ]:
        add_item(*spec)
    db.session.flush()
    commit("shipment-items")

    if hasattr(shp, "update_status") and callable(getattr(shp, "update_status")):
        shp.update_status("ARRIVED")
    elif hasattr(shp, "status"):
        shp.status = "ARRIVED"
    db.session.flush()
    commit("shipment-arrived")

    if getattr(M, "ExchangeTransaction", None):
        xt = M.ExchangeTransaction(
            **_kw(
                M.ExchangeTransaction,
                product_id=products[1].id,
                warehouse_id=exchange.id,
                quantity=10,
                direction=_ev(TDIR, "IN", "IN"),
                unit_cost=q(11.50),
            )
        )
        _add_note(xt)
        db.session.add(xt)
        db.session.flush()
        commit("exchange-transaction")

    if partner:
        for prod, qty in [(products[1], 10), (products[0], 5), (products[2], 20)]:
            tr = M.Transfer(
                **_kw(
                    M.Transfer,
                    product_id=prod.id,
                    source_id=main.id,
                    destination_id=partner.id,
                    quantity=qty,
                    direction=_ev(TDIR, "OUTGOING", "OUTGOING"),
                    transfer_date=datetime.utcnow(),
                )
            )
            _add_note(tr)
            db.session.add(tr)
        db.session.flush()
        commit("transfers")

# ---------------------- عملاء ----------------------
def seed_customers():
    C = getattr(M, "Customer", None)
    if not C:
        return []

    base = [
        dict(name="محمد بركات", phone="+970599111001", email="m.barakat@clients.ps", address="رام الله - الطيرة"),
        dict(name="أحمد درويش", phone="+970599111002", email="a.darwish@clients.ps", address="البيرة - شارع القدس"),
        dict(name="حسام عويطات", phone="+970599111003", email="h.owaidat@clients.ps", address="نابلس"),
        dict(name="سُهى حمزة", phone="+970569111004", email="suha.hamzeh@clients.ps", address="الخليل"),
        dict(name="زبون نقدي", phone="+970569111005", email="cash@clients.ps", address="عام"),
    ]

    out = []

    def _insert_or_get(**r):
        row = C(
            name=r["name"],
            phone=r["phone"],
            whatsapp=r["phone"] if "whatsapp" in C.__table__.c else None,
            email=r.get("email"),
            address=r.get("address"),
            currency="ILS",
            credit_limit=randint(0, 8000),
            discount_rate=choice([0, 5, 10]),
            is_active=True,
            is_online=False if "is_online" in C.__table__.c else None,
            notes=SEED_TAG,
        )
        db.session.add(row)
        try:
            db.session.flush()
            return row
        except IntegrityError:
            db.session.rollback()
            # موجود مسبقاً (unique على phone/ email..). رجّعه بدل إنشاء جديد
            existing = C.query.filter_by(phone=r["phone"]).first()
            if existing:
                return existing
            # لو التعارض على email فقط، جرّب البحث بالـ email
            if r.get("email"):
                existing = C.query.filter_by(email=r["email"]).first()
                if existing:
                    return existing
            # fallback أخير: عدّل رقم الهاتف وادخله ثانية
            row.phone = f"+97059{randint(1000000,9999999)}"
            db.session.add(row)
            db.session.flush()
            return row

    # العملاء الأساسيون
    for r in base:
        c = _insert_or_get(**r)
        if c:
            out.append(c)

    # عملاء تجريبيون
    for i in range(25):
        nm = f"عميل تجريبي {i+1:02d}"
        em = f"cust{i+1:02d}@clients.ps"
        # توليد رقم قد يتصادم؛ دورتنا تعالج التصادم
        r = dict(name=nm, phone=f"+97059{randint(1000000,9999999)}", email=em, address="فلسطين")
        c = _insert_or_get(**r)
        if c:
            out.append(c)

    commit("customers")

    # فلترة أمان: لا ترجع أي None
    return [c for c in out if c is not None]

# ---------------------- مبيعات/فواتير/مدفوعات ----------------------
def _pick_seller_user_id(mgr_user=None, admin_user=None) -> int:
    """
    يرجّع id يوزر موجود فعليًا لاستخدامه كبائع.
    تفضيل: manager ثم admin إن تم تمريرهم وبالفعل لهم id.
    وإلا يرجع أول User موجود بالقاعدة (id أصغر).
    وإن لم يوجد أي يوزر، ينشئ seed_seller ويستعمله.
    """
    for u in (mgr_user, admin_user):
        if getattr(u, "id", None):
            return int(u.id)

    # أول يوزر فعلي موجود
    u = M.User.query.order_by(M.User.id.asc()).first()
    if u and getattr(u, "id", None):
        return int(u.id)

    # مافيش؟ أنشئ seed_seller مضمون
    u = M.User(username="seed_seller", email="seed_seller@example.com", is_active=True, notes=SEED_TAG)
    if hasattr(u, "set_password"):
        u.set_password("password123")
    db.session.add(u)
    db.session.flush()  # يضمن u.id
    return int(u.id)

def seed_sales_invoices_payments(customers, main, products, employees=None, mgr_user=None, admin_user=None):
    # 1) تأكيد وجود منتج واحد على الأقل
    if not products:
        PC = getattr(M, "ProductCategory", None)
        cat = None
        if PC:
            cat, _ = get_or_create(PC, name="عامة", defaults=dict(notes=SEED_TAG))
        P = getattr(M, "Product", None)
        if P:
            p, _ = get_or_create(
                P, sku="SEED-ITEM-001",
                defaults=dict(
                    name="صنف افتراضي", brand="Generic", part_number="SEED-001",
                    price=Decimal("100.00"), purchase_price=Decimal("70.00"),
                    category_id=getattr(cat, "id", None), is_active=True, notes=SEED_TAG
                ),
            )
            products = [p]
        else:
            # لا يوجد موديل منتجات أصلاً، نخرج بهدوء
            return

    # 2) ضمـان عميل وبائع موجودين فعليًا في DB (حتى لو زلّت خطوات سابقة)
    c_obj = (customers[0] if customers else None)
    customer_id = _ensure_customer_id(c_obj)
    seller_id   = _ensure_user_id()

    has_cust = db.session.execute(sa_text("SELECT 1 FROM customers WHERE id=:i"), {"i": customer_id}).scalar()
    has_user = db.session.execute(sa_text("SELECT 1 FROM users WHERE id=:i"), {"i": seller_id}).scalar()
    assert has_cust, f"FK check: customer_id={customer_id} غير موجود في customers."
    assert has_user, f"FK check: seller_id={seller_id} غير موجود في users."
    # 4) تجهيز منتجات للسطرين الأوليين
    p0 = products[0]
    p1 = products[1] if len(products) > 1 else products[0]

    # 5) إنشاء فاتورة بيع showcase
    s = M.Sale(**_kw(
        M.Sale,
        customer_id=customer_id,
        seller_id=seller_id,
        sale_date=datetime.utcnow() - timedelta(days=1),
        tax_rate=16, discount_total=0, shipping_cost=0,
        currency="ILS",
        status=_ev(SST, "CONFIRMED", "CONFIRMED"),
        notes=SEED_TAG,
    ))
    _add_note(s)
    db.session.add(s)
    db.session.flush()  # لو في FK ناقص، assert أعلاه كان سيكشفه قبل هذا السطر

    # 6) إضافة السطور
    db.session.add(M.SaleLine(**_kw(
        M.SaleLine, sale_id=s.id, product_id=p0.id, warehouse_id=main.id,
        quantity=2, unit_price=p0.price, discount_rate=0, tax_rate=0
    )))
    db.session.add(M.SaleLine(**_kw(
        M.SaleLine, sale_id=s.id, product_id=p1.id, warehouse_id=main.id,
        quantity=1, unit_price=p1.price, discount_rate=0, tax_rate=0
    )))
    db.session.flush()

    # 7) المدفوعات على دفعتين
    total = q(getattr(s, "total_amount", 0) or getattr(s, "total", 0) or (q(p0.price) * 2 + q(p1.price)))
    p1_amt = q(min(total, Decimal("50.00")))
    p2_amt = total - p1_amt

    p1pay = M.Payment(**_kw(
        M.Payment,
        total_amount=p1_amt, currency="ILS", method=_ev(PM, "CASH", "CASH"),
        status=_ev(PST, "COMPLETED", "COMPLETED"),
        direction=_ev(PDIR, "INCOMING", "INCOMING"),
        entity_type=_ev(PET, "SALE", "SALE"),
        sale_id=s.id, payment_date=datetime.utcnow() - timedelta(hours=2),
        notes=SEED_TAG,
    ))
    _add_note(p1pay)
    db.session.add(p1pay)
    db.session.flush()
    if getattr(M, "PaymentSplit", None):
        db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=p1pay.id, method=_ev(PM, "CASH", "CASH"), amount=p1_amt)))

    if p2_amt > 0:
        p2pay = M.Payment(**_kw(
            M.Payment,
            total_amount=p2_amt, currency="ILS", method=_ev(PM, "CARD", "CARD"),
            status=_ev(PST, "COMPLETED", "COMPLETED"),
            direction=_ev(PDIR, "INCOMING", "INCOMING"),
            entity_type=_ev(PET, "SALE", "SALE"),
            sale_id=s.id, payment_date=datetime.utcnow() - timedelta(hours=1),
            reference="VISA 1234", notes=SEED_TAG,
        ))
        _add_note(p2pay)
        db.session.add(p2pay)
        db.session.flush()
        if getattr(M, "PaymentSplit", None):
            db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=p2pay.id, method=_ev(PM, "CARD", "CARD"), amount=p2_amt)))

    commit("showcase-sale-payment")

    # 8) إنشاء مبيعات تاريخية متعددة الأيام
    for d in range(1, 28):
        # اختيار عميل (أو ضمان واحد)
        cust = choice([x for x in (customers or []) if x] or [None])
        cust_id = int(getattr(cust, "id", 0)) or _ensure_customer_id()

        pr = choice(products)
        qty = choice([1, 1, 2, 3])

        s = M.Sale(**_kw(
            M.Sale,
            customer_id=cust_id,
            seller_id=seller_id,  # ← إصلاح اسم المتغير
            sale_date=datetime.utcnow() - timedelta(days=d),
            tax_rate=16, discount_total=0, shipping_cost=0,
            currency="ILS",
            status=_ev(SST, "CONFIRMED", "CONFIRMED"),
            notes=SEED_TAG,
        ))
        db.session.add(s)
        db.session.flush()

        db.session.add(M.SaleLine(**_kw(
            M.SaleLine,
            sale_id=s.id, product_id=pr.id, warehouse_id=main.id,
            quantity=qty, unit_price=pr.price, discount_rate=0, tax_rate=0
        )))
        db.session.flush()

        amt  = q(getattr(s, "total_amount", q(pr.price) * qty))
        meth = choice([_ev(PM, "CASH", "CASH"), _ev(PM, "CARD", "CARD"), _ev(PM, "BANK", "BANK")])

        pay = M.Payment(**_kw(
            M.Payment,
            total_amount=amt, currency="ILS", method=meth, status=_ev(PST, "COMPLETED", "COMPLETED"),
            direction=_ev(PDIR, "INCOMING", "INCOMING"), entity_type=_ev(PET, "SALE", "SALE"),
            sale_id=s.id, payment_date=s.sale_date + timedelta(hours=randint(0, 6)), notes=SEED_TAG,
        ))
        db.session.add(pay)
        db.session.flush()

        if getattr(M, "PaymentSplit", None):
            if random() < 0.3:
                a1 = q(amt * Decimal("0.5")); a2 = amt - a1
                db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=pay.id, method=meth, amount=a1)))
                db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=pay.id, method=_ev(PM, "CASH", "CASH"), amount=a2)))
            else:
                db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=pay.id, method=meth, amount=amt)))

    commit("historic-sales-invoices")
# ---------------------- حجز مسبق ----------------------
def seed_preorder(customers, products, main):
    if not getattr(M, "PreOrder", None) or not customers or not products:
        return
    row = M.PreOrder(
        **_kw(
            M.PreOrder,
            preorder_date=datetime.utcnow(),
            expected_date=datetime.utcnow() + timedelta(days=7),
            customer_id=customers[2].id,
            product_id=products[3].id if len(products) > 3 else products[0].id,
            warehouse_id=main.id,
            quantity=3,
            prepaid_amount=q(60),
            tax_rate=0,
            status="PENDING",
            payment_method=_ev(PM, "CASH", "CASH"),
            currency="ILS",
        )
    )
    _add_note(row)
    db.session.add(row)
    db.session.flush()

    pay = M.Payment(
        **_kw(
            M.Payment,
            total_amount=q(60),
            currency="ILS",
            method=_ev(PM, "CASH", "CASH"),
            status=_ev(PST, "COMPLETED", "COMPLETED"),
            direction=_ev(PDIR, "INCOMING", "INCOMING"),
            entity_type=_ev(PET, "PREORDER", "PREORDER"),
            preorder_id=row.id,
        )
    )
    _add_note(pay)
    db.session.add(pay)
    db.session.flush()

    if getattr(M, "PaymentSplit", None):
        db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=pay.id, method=_ev(PM, "CASH", "CASH"), amount=pay.total_amount)))

    commit("preorder")


# ---------------------- خدمات الورشة ----------------------
def seed_service(customers, products, main, mechanic_user):
    if not getattr(M, "ServiceRequest", None) or not customers or not products:
        return
    sr = M.ServiceRequest(
        **_kw(
            M.ServiceRequest,
            customer_id=customers[3].id if len(customers) > 3 else customers[0].id,
            tax_rate=0,
            discount_total=0,
            currency="ILS",
            status=_ev(SVS, "IN_PROGRESS", "IN_PROGRESS"),
        )
    )
    if hasattr(sr, "mechanic_id") and mechanic_user:
        sr.mechanic_id = mechanic_user.id
    if hasattr(sr, "received_at"):
        sr.received_at = datetime.utcnow() - timedelta(days=1)
    if hasattr(sr, "priority"):
        sr.priority = _ev(SVP, "MEDIUM", "MEDIUM")
    if hasattr(sr, "problem_description"):
        sr.problem_description = "صوت في المحرك"
    if hasattr(sr, "diagnosis"):
        sr.diagnosis = "بحاجة لتبديل فلتر الزيت"

    _add_note(sr)
    db.session.add(sr)
    db.session.flush()

    if getattr(M, "ServicePart", None):
        sp = M.ServicePart(
            **_kw(
                M.ServicePart,
                service_id=sr.id,
                part_id=products[1].id if len(products) > 1 else products[0].id,
                warehouse_id=main.id,
                quantity=1,
                unit_price=products[1].price if len(products) > 1 else products[0].price,
                discount=0,
            )
        )
        _add_note(sp)
        db.session.add(sp)

    if getattr(M, "ServiceTask", None):
        st = M.ServiceTask(
            **_kw(M.ServiceTask, service_id=sr.id, description="أجور عمل", quantity=1, unit_price=q(80), discount=0)
        )
        _add_note(st)
        db.session.add(st)

    db.session.flush()
    recalc = getattr(M, "_recalc_service_request_totals", None)
    if callable(recalc):
        try:
            recalc(sr)
        except Exception:
            pass

    if hasattr(sr, "status"):
        sr.status = _ev(SVS, "COMPLETED", "COMPLETED")

    pay = M.Payment(
        **_kw(
            M.Payment,
            total_amount=q(getattr(sr, "total_amount", getattr(sr, "total", 80))),
            currency="ILS",
            method=_ev(PM, "CASH", "CASH"),
            status=_ev(PST, "COMPLETED", "COMPLETED"),
            direction=_ev(PDIR, "INCOMING", "INCOMING"),
            entity_type=_ev(PET, "SERVICE", "SERVICE"),
            service_id=sr.id,
        )
    )
    _add_note(pay)
    db.session.add(pay)
    db.session.flush()

    if getattr(M, "PaymentSplit", None):
        db.session.add(M.PaymentSplit(**_kw(M.PaymentSplit, payment_id=pay.id, method=_ev(PM, "CASH", "CASH"), amount=pay.total_amount)))

    commit("service")


# ---------------------- أونلاين ----------------------
def seed_online(customers, products):
    if not all(getattr(M, n, None) for n in ["OnlineCart", "OnlinePreOrder", "OnlinePayment"]):
        return
    if not customers or not products:
        return

    cust = customers[4] if len(customers) > 4 else customers[0]
    cart = M.OnlineCart(
        **_kw(M.OnlineCart, customer_id=cust.id, status="ACTIVE", expires_at=datetime.utcnow() + timedelta(days=5))
    )
    _add_note(cart)
    db.session.add(cart)
    db.session.flush()

    if getattr(M, "OnlineCartItem", None):
        db.session.add(
            M.OnlineCartItem(
                **_kw(
                    M.OnlineCartItem,
                    cart_id=cart.id,
                    product_id=products[2].id if len(products) > 2 else products[0].id,
                    quantity=3,
                    price=products[2].price if len(products) > 2 else products[0].price,
                )
            )
        )
        db.session.add(
            M.OnlineCartItem(
                **_kw(
                    M.OnlineCartItem,
                    cart_id=cart.id,
                    product_id=products[1].id if len(products) > 1 else products[0].id,
                    quantity=1,
                    price=products[1].price if len(products) > 1 else products[0].price,
                )
            )
        )
    db.session.flush()

    opr = M.OnlinePreOrder(**_kw(M.OnlinePreOrder, customer_id=cust.id, cart_id=cart.id, status="PENDING", payment_status="PENDING"))
    _add_note(opr)
    db.session.add(opr)
    db.session.flush()

    if getattr(M, "OnlinePreOrderItem", None):
        for ci in getattr(cart, "items", []):
            db.session.add(M.OnlinePreOrderItem(**_kw(M.OnlinePreOrderItem, order_id=opr.id, product_id=ci.product_id, quantity=ci.quantity, price=ci.price)))
    db.session.flush()

    op = M.OnlinePayment(
        **_kw(
            M.OnlinePayment,
            order_id=opr.id,
            amount=getattr(opr, "items_subtotal", q(100)),
            currency="ILS",
            method=_ev(PM, "CARD", "CARD"),
            gateway="stripe",
            status="SUCCESS",
        )
    )
    for k, v in dict(card_last4="4242", card_brand="VISA", card_expiry="12/28", cardholder_name=str(cust.name)).items():
        if hasattr(op, k):
            setattr(op, k, v)
    _add_note(op)
    db.session.add(op)
    commit("online")


# ---------------------- مصاريف ----------------------
def _get_expense_type_id(name: str, desc: str | None = None) -> int:
    """يرجع ID لنوع المصروف ويُنشئه إذا لم يكن موجودًا."""
    ET = getattr(M, "ExpenseType", None)
    if not ET:
        raise RuntimeError("ExpenseType model is required (expenses.type_id is NOT NULL)")
    et, _ = get_or_create(ET, name=name, defaults=dict(description=desc or name, is_active=True, notes=SEED_TAG))
    db.session.flush()
    return int(et.id)

def seed_expenses(employees, warehouses, partners, suppliers):
    # أنشئ/اجلب أنواع المصروفات المطلوبة وأخذ IDs
    types_spec = [
        ("وقود", "ديزل وبنزين"),
        ("كهرباء", "فاتورة شركة الكهرباء"),
        ("ماء", "فاتورة سلطة المياه"),
        ("رواتب", "رواتب موظفين"),
        ("قرطاسية", "مشتريات مكتبية"),
    ]
    type_ids = {nm: _get_expense_type_id(nm, desc) for nm, desc in types_spec}

    # علاقات اختيارية
    emp = employees[0] if (employees and employees[0]) else None
    wh  = warehouses[0] if (warehouses and warehouses[0]) else None
    par = partners[0]  if (partners  and partners[0])  else None

    # مصروف 1: وقود (card)
    e1 = M.Expense(**_kw(
        M.Expense,
        date=datetime.utcnow() - timedelta(days=3),
        amount=350.00,
        currency="ILS",
        type_id=type_ids["وقود"],
        payment_method=_ev(PM, "CARD", "CARD"),   # سيُطبّع لـ "card" في before_insert
        description="وقود سيارات التوصيل",
        notes=SEED_TAG,
        payee_type="OTHER",
    ))
    if hasattr(e1, "employee_id") and emp: e1.employee_id = emp.id
    if hasattr(e1, "warehouse_id") and wh: e1.warehouse_id = wh.id
    _add_note(e1); db.session.add(e1)

    # مصروف 2: كهرباء (bank)
    e2 = M.Expense(**_kw(
        M.Expense,
        date=datetime.utcnow() - timedelta(days=2),
        amount=1250.00,
        currency="ILS",
        type_id=type_ids["كهرباء"],
        payment_method=_ev(PM, "BANK", "BANK"),   # سيُطبّع لـ "bank"
        description="فاتورة كهرباء الشهر",
        notes=SEED_TAG,
        payee_type="OTHER",
    ))
    if hasattr(e2, "warehouse_id") and wh: e2.warehouse_id = wh.id
    if hasattr(e2, "partner_id") and par: e2.partner_id = par.id
    _add_note(e2); db.session.add(e2)

    # مثال ثالث اختياري: ماء (cash)
    e3 = M.Expense(**_kw(
        M.Expense,
        date=datetime.utcnow() - timedelta(days=1),
        amount=210.00,
        currency="ILS",
        type_id=type_ids["ماء"],
        payment_method=_ev(PM, "CASH", "CASH"),   # سيُطبّع لـ "cash"
        description="فاتورة مياه",
        notes=SEED_TAG,
        payee_type="OTHER",
    ))
    if hasattr(e3, "warehouse_id") and wh: e3.warehouse_id = wh.id
    _add_note(e3); db.session.add(e3)

    commit("expenses")

    # دفع المصروف 2 (اختياري كمثال)
    pay1 = M.Payment(**_kw(
        M.Payment,
        total_amount=1250.00,
        method=_ev(PM, "BANK", "BANK"),
        status=_ev(PST, "COMPLETED", "COMPLETED"),
        direction=_ev(PDIR, "OUTGOING", "OUTGOING"),
        entity_type=_ev(PET, "EXPENSE", "EXPENSE"),
        currency="ILS",
        notes=SEED_TAG,
    ))
    if hasattr(pay1, "expense_id"):
        pay1.expense_id = e2.id
    _add_note(pay1); db.session.add(pay1)

    commit("expense-payment")

# ---------------------- ملاحظات ----------------------
def seed_notes(customers, users):
    Note = getattr(M, "Note", None)
    if not Note or not customers:
        return
    c = customers[0]
    u = None
    for x in users:
        if x:
            u = x
            break
    n = Note(
        **_kw(
            Note,
            content="الزبون مداوم كل 3 أشهر. خصم 5% عند تجاوز 1000 شيكل.",
            is_pinned=True,
            priority="HIGH",
        )
    )
    if hasattr(n, "author_id") and u:
        n.author_id = u.id
    if hasattr(n, "entity_type"):
        n.entity_type = "CUSTOMER"
    if hasattr(n, "entity_id"):
        n.entity_id = c.id
    _add_note(n)
    db.session.add(n)
    commit("notes")


# ---------------------- تسويات شركاء/موردين (اختياري) ----------------------
def seed_settlements(partners, suppliers):
    build_partner = getattr(M, "build_partner_settlement_draft", None)
    build_supplier = getattr(M, "build_supplier_settlement_draft", None)
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=90)

    if callable(build_partner) and partners:
        try:
            ps = build_partner(partners[0].id, date_from, date_to, currency="ILS")
        except Exception:
            ps = None
        if ps:
            db.session.add(ps)
    if callable(build_supplier) and suppliers:
        try:
            ss = build_supplier(suppliers[0].id, date_from, date_to, currency="ILS")
        except Exception:
            ss = None
        if ss:
            db.session.add(ss)
    commit("settlements")


def run_seed(full_reset: bool = True):
    if full_reset:
        cleanup_previous()

    def ensure_user(username, email, role_name=None):
        u = M.User.query.filter(
            (M.User.username == username) | (M.User.email == email)
        ).first()
        if not u:
            u = M.User(username=username, email=email, is_active=True, notes_text=SEED_TAG)
            if hasattr(u, "set_password"):
                u.set_password("password123")
            if role_name and hasattr(M, "Role"):
                role = M.Role.query.filter_by(name=role_name).first()
                if role:
                    u.role_id = role.id
            db.session.add(u)
            db.session.flush()
        else:
            if role_name and hasattr(M, "Role") and not getattr(u, "role_id", None):
                role = M.Role.query.filter_by(name=role_name).first()
                if role:
                    u.role_id = role.id
        return u

    admin     = ensure_user("admin", "admin@example.com", role_name="admin")
    mgr       = ensure_user("manager", "manager@example.com", role_name="manager")
    mech      = ensure_user("mechanic", "mechanic@example.com", role_name="mechanic")
    cash      = ensure_user("cashier", "cashier@example.com", role_name="cashier")
    cust_user = ensure_user("customer", "customer@example.com", role_name="customer")

    suppliers, partners, employees = seed_suppliers_partners_employees()
    cats, ets = seed_categories_equipment()
    main, exchange, wpartner, online = seed_warehouses(suppliers, partners)
    products = seed_products(cats, ets, suppliers)
    customers = seed_customers()
    seed_stock(products, main, exchange, wpartner, online)
    seed_shipments_exchange_transfers(main, exchange, wpartner, products)
    seed_sales_invoices_payments(
        customers, main, products,
        employees=employees, mgr_user=mgr, admin_user=admin
    )
    seed_preorder(customers, products, main)
    seed_service(customers, products, main, mech)
    seed_online(customers, products)
    seed_expenses(employees, (main, exchange, wpartner, online), partners, suppliers)
    seed_notes(customers, [admin, mgr, mech, cash, cust_user])
    seed_settlements(partners, suppliers)
    commit("final")

# ---------------------- CLI ----------------------
@click.command("seed-palestine")
@click.option("--reset/--no-reset", default=True)
@with_appcontext
def seed_palestine(reset: bool):
    run_seed(full_reset=reset)
    click.echo("✅ تم توليد بيانات كاملة للنظام (فلسطين).")


@click.command("seed-full-palestine")
@click.option("--no-reset", is_flag=True)
@with_appcontext
def seed_full_palestine(no_reset: bool):
    run_seed(full_reset=not no_reset)
    click.echo("✅ تم توليد بيانات كاملة وواقعية للنظام (فلسطين).")


def init_app(app):
    app.cli.add_command(seed_palestine)
    app.cli.add_command(seed_full_palestine)
