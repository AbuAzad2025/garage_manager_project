"""
Seed file for the provided models.py (Garage in Ramallah, Palestine)
-----------------------------------------------------------------------------
- Idempotent: re-runnable without breaking unique constraints (get-or-create)
- Palestinian names/phones/emails/addresses; commercial-flavored data
- Seeds: permissions/roles/users, customers, suppliers, partners, employees,
         equipment types, product categories, products, warehouses, stock,
         shipments (arrive -> stock up), transfers, preorders, sales+invoices,
         payments (in/out, cash/bank/card/online), services (parts/tasks),
         online (cart, preorder, payment), expense types & expenses, notes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from extensions import db
import models as M
from models import (
    PaymentMethod,
    PaymentStatus,
    PaymentDirection,
    PaymentEntityType,
    InvoiceStatus,
    SaleStatus,
    ServiceStatus,
    ServicePriority,
    WarehouseType,
    TransferDirection,
)

# ----------------------------- helpers ------------------------------------

def q(x) -> Decimal:
    try:
        return Decimal(str(x or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def commit(label: str = "commit"):
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        print(f"[seed] IntegrityError during {label}: {e}")
    except Exception as e:
        db.session.rollback()
        print(f"[seed] Error during {label}: {e}")


def get_or_create(model, defaults: dict | None = None, **unique_by):
    obj = model.query.filter_by(**unique_by).first()
    if obj:
        if defaults:
            for k, v in defaults.items():
                if getattr(obj, k, None) in (None, "", 0):
                    setattr(obj, k, v)
        return obj, False
    obj = model(**{**(defaults or {}), **unique_by})
    db.session.add(obj)
    try:
        db.session.flush()
        return obj, True
    except IntegrityError:
        db.session.rollback()
        obj = model.query.filter_by(**unique_by).first()
        return obj, False


def ensure_stock_row(product_id: int, warehouse_id: int):
    row = M.StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
    if row:
        return row
    row = M.StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0, reserved_quantity=0)
    db.session.add(row)
    db.session.flush()
    return row

# ----------------------------- seeders ------------------------------------

def seed_permissions_roles_users():
    p_admin, _ = get_or_create(M.Permission, code="admin", defaults={"name": "Admin"})
    p_sales, _ = get_or_create(M.Permission, code="sales", defaults={"name": "Sales"})
    p_service, _ = get_or_create(M.Permission, code="service", defaults={"name": "Service"})

    owner, _ = get_or_create(M.Role, name="owner", defaults={"description": "Owner", "is_default": False})
    admin, _ = get_or_create(M.Role, name="admin", defaults={"description": "Administrator", "is_default": False})
    seller, _ = get_or_create(M.Role, name="seller", defaults={"description": "Sales", "is_default": False})
    mechanic_role, _ = get_or_create(M.Role, name="mechanic", defaults={"description": "Mechanic", "is_default": False})

    for r in (owner, admin, seller, mechanic_role):
        if p_admin not in r.permissions:
            r.permissions.append(p_admin)
    commit("roles-perms")

    def ensure_user(username, email, role, password):
        user = M.User.query.filter_by(username=username).first()
        if not user:
            user = M.User(username=username, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        return user

    u_owner   = ensure_user("ahmad",    "ahmad@garage.ps",   owner,   "ahmad123")
    u_admin   = ensure_user("admin",    "admin@garage.ps",   admin,   "admin123")
    u_seller  = ensure_user("mohammad", "mohammad@garage.ps", seller, "seller123")
    u_mech    = ensure_user("bilal",    "bilal@garage.ps",   mechanic_role, "mechanic123")

    commit("users")
    return u_owner, u_admin, u_seller, u_mech


def seed_customers():
    customers_data = [
        {"name": "محمد دراغمة", "phone": "059-2000101", "email": "m.daragmeh@clients.ps", "address": "رام الله - الطيرة"},
        {"name": "ليان بركات",  "phone": "059-2000102", "email": "l.barkat@clients.ps",  "address": "رام الله - الماصيون"},
        {"name": "علاء حمد",    "phone": "059-2000103", "email": "alaa.hamad@clients.ps", "address": "البيرة - شارع القدس"},
        {"name": "آية قعدان",   "phone": "059-2000104", "email": "aya.qadan@clients.ps",  "address": "بيتونيا - المنطقة الصناعية"},
        {"name": "أحمد زهران",  "phone": "059-2000105", "email": "ahmad.zahran@clients.ps","address": "رام الله - الإرسال"},
        {"name": "تمارا منصور", "phone": "059-2000106", "email": "tamara.mansour@clients.ps","address": "بيرزيت"},
        {"name": "قصي أبو حسن", "phone": "059-2000107", "email": "q.abu-hasan@clients.ps", "address": "رام الله - أم الشرايط"},
        {"name": "هبة السكسك",  "phone": "059-2000108", "email": "hiba.saksak@clients.ps", "address": "الطيرة"},
        {"name": "نادر صوافطة", "phone": "059-2000109", "email": "nader.swafteh@clients.ps","address": "البيرة"},
        {"name": "فراس عطوان",  "phone": "059-2000110", "email": "feras.atwan@clients.ps", "address": "رام الله"},
    ]
    out = []
    for c in customers_data:
        cust, _ = get_or_create(
            M.Customer,
            name=c["name"],
            defaults={
                "phone": c["phone"],
                "whatsapp": c["phone"],
                "email": c["email"],
                "address": c["address"],
                "category": "عادي",
                "is_active": True,
                "is_online": True,
                "currency": "ILS",
                "discount_rate": 0,
                "credit_limit": 0,
            },
        )
        out.append(cust)
    commit("customers")
    return out


def seed_suppliers_partners_employees():
    suppliers_data = [
        {"name": "شركة القدس للمحركات", "email": "qods@suppliers.ps", "address": "القدس"},
        {"name": "الشرفا أوتو بارس",   "email": "shurafa@suppliers.ps", "address": "نابلس"},
        {"name": "رام الله للزيوت",    "email": "ramoil@suppliers.ps",  "address": "رام الله"},
    ]
    suppliers = []
    for s in suppliers_data:
        sup, _ = get_or_create(M.Supplier, name=s["name"], defaults={
            "email": s["email"],
            "address": s["address"],
            "is_local": True,
            "currency": "ILS",
        })
        suppliers.append(sup)

    partners_data = [
        {"name": "شريك تداول البيرة", "email": "partner.bireh@partners.ps", "phone_number": "059-3000101", "address": "البيرة"},
        {"name": "شريك بيتونيا",     "email": "partner.bitunia@partners.ps", "phone_number": "059-3000102", "address": "بيتونيا"},
    ]
    partners = []
    for i, p in enumerate(partners_data, start=1):
        partner, _ = get_or_create(M.Partner, name=p["name"], defaults={
            "email": p["email"],
            "phone_number": p["phone_number"],
            "address": p["address"],
            "identity_number": f"PRT-{1000+i}",
            "currency": "ILS",
            "share_percentage": 0,
        })
        partners.append(partner)

    employees_data = [
        {"name": "كريم البرغوثي", "position": "فني",    "email": "karim@garage.ps"},
        {"name": "ليان عطية",     "position": "محاسبة", "email": "layan@garage.ps"},
    ]
    employees = []
    for e in employees_data:
        emp, _ = get_or_create(M.Employee, name=e["name"], defaults={
            "position": e["position"],
            "email": e["email"],
            "currency": "ILS",
        })
        employees.append(emp)

    commit("suppliers-partners-employees")
    return suppliers, partners, employees


def seed_equipment_types_categories_products(suppliers, partners):
    veh_types = [
        ("هيونداي أكسنت", "ACCENT"),
        ("كيا ريو", "RIO"),
        ("تويوتا كورولا", "COROLLA"),
        ("بيجو بارتنر", "PARTNER"),
    ]
    et_objs = []
    for name, model_no in veh_types:
        et, _ = get_or_create(M.EquipmentType, name=name, defaults={"model_number": model_no})
        et_objs.append(et)

    cat_names = ["قطع كهرباء", "فلاتر", "زيوت", "هياكل", "إطارات"]
    cats = []
    for cn in cat_names:
        cat, _ = get_or_create(M.ProductCategory, name=cn)
        cats.append(cat)

    wh_main, _ = get_or_create(M.Warehouse, name="المستودع الرئيسي - رام الله", defaults={
        "warehouse_type": WarehouseType.MAIN,
        "location": "رام الله - الصناعية",
        "is_active": True,
        "capacity": 10000,
    })
    wh_showroom, _ = get_or_create(M.Warehouse, name="صالة العرض - رام الله", defaults={
        "warehouse_type": WarehouseType.INVENTORY,
        "location": "رام الله - الإرسال",
        "is_active": True,
        "capacity": 2000,
    })
    wh_partner, _ = get_or_create(M.Warehouse, name="مخزن الشريك - البيرة", defaults={
        "warehouse_type": WarehouseType.PARTNER,
        "location": "البيرة - المنطقة الصناعية",
        "is_active": True,
        "capacity": 4000,
        "share_percent": 40,
    })
    if partners:
        wh_partner.partner = partners[0]

    commit("warehouses")

    products_spec = [
        {
            "sku": "EL-ACC-001", "name": "دينامو هيونداي أكسنت", "price": 420.00,
            "brand": "Hyundai", "category": "قطع كهرباء", "unit": "قطعة",
            "supplier_general": suppliers[0], "vehicle_type": et_objs[0],
            "serial_no": "SN-ACC-0001", "barcode": "6290000000010",
        },
        {
            "sku": "FLT-COR-001", "name": "فلتر هواء كورولا", "price": 55.00,
            "brand": "Toyota", "category": "فلاتر", "unit": "قطعة",
            "supplier_general": suppliers[1], "vehicle_type": et_objs[2],
            "serial_no": "SN-COR-0001", "barcode": "6290000000027",
        },
        {
            "sku": "OIL-5W30-1L", "name": "زيت محرك 5W30 - 1 لتر", "price": 35.00,
            "brand": "Total", "category": "زيوت", "unit": "لتر",
            "supplier_general": suppliers[2], "vehicle_type": None,
            "serial_no": "SN-OIL-0001", "barcode": "6290000000034",
        },
        {
            "sku": "BRK-RIO-SET", "name": "طقم بريك كيا ريو", "price": 190.00,
            "brand": "Kia", "category": "هياكل", "unit": "طقم",
            "supplier_general": suppliers[1], "vehicle_type": et_objs[1],
            "serial_no": "SN-RIO-0001", "barcode": "6290000000041",
        },
        {
            "sku": "TIR-195-65R15", "name": "إطار 195/65R15", "price": 260.00,
            "brand": "Roadstone", "category": "إطارات", "unit": "إطار",
            "supplier_general": suppliers[0], "vehicle_type": None,
            "serial_no": "SN-TIR-0001", "barcode": "6290000000058",
        },
    ]
    prod_objs = []
    for spec in products_spec:
        defaults = {
            "name": spec["name"],
            "price": spec["price"],
            "selling_price": spec["price"],
            "brand": spec["brand"],
            "category_name": spec["category"],
            "unit": spec["unit"],
            "supplier_general": spec["supplier_general"],
            "vehicle_type": spec["vehicle_type"],
            "is_active": True,
        }
        prod, _ = get_or_create(M.Product, sku=spec["sku"], defaults=defaults)
        if not prod.serial_no:
            prod.serial_no = spec["serial_no"]
        if not prod.barcode:
            prod.barcode = spec["barcode"]
        prod_objs.append(prod)
    commit("products")

    return (wh_main, wh_showroom, wh_partner), prod_objs, et_objs, cats

def seed_shipments_stock(warehouses, products):
    wh_main, wh_show, wh_partner = warehouses

    shp = M.Shipment.query.filter_by(destination_id=wh_main.id).first()
    if not shp:
        shp = M.Shipment(
            origin="مرسين - تركيا",
            destination="رام الله",
            destination_warehouse=wh_main,
            status="IN_TRANSIT",
            currency="USD",
            shipment_date=datetime.utcnow() - timedelta(days=7),
            expected_arrival=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(shp)
        db.session.flush()

    def add_item(shipment, product, warehouse, qty, unit_cost):
        exists = M.ShipmentItem.query.filter_by(
            shipment_id=shipment.id, product_id=product.id, warehouse_id=warehouse.id
        ).first()
        if exists:
            return exists
        it = M.ShipmentItem(
            shipment=shipment,
            product=product,
            warehouse=warehouse,
            quantity=qty,
            unit_cost=unit_cost,
        )
        db.session.add(it)
        db.session.flush()
        return it

    add_item(shp, products[0], wh_main, qty=20, unit_cost=300)
    add_item(shp, products[1], wh_main, qty=60, unit_cost=30)
    add_item(shp, products[2], wh_main, qty=120, unit_cost=20)
    add_item(shp, products[3], wh_main, qty=15, unit_cost=140)
    add_item(shp, products[4], wh_main, qty=40, unit_cost=180)
    commit("shipment-items")

    shp.update_status("ARRIVED")
    commit("shipment-arrival")

    def transfer(prod, src, dst, qty):
        ensure_stock_row(prod.id, dst.id)
        tr = M.Transfer(
            reference=None,
            product_id=prod.id,
            source_id=src.id,
            destination_id=dst.id,
            quantity=qty,
            direction=TransferDirection.OUT,
            transfer_date=datetime.utcnow(),
        )
        db.session.add(tr)
        db.session.flush()
        return tr

    transfer(products[1], wh_main, wh_show, 10)
    transfer(products[0], wh_main, wh_partner, 5)
    transfer(products[2], wh_main, wh_partner, 20)
    commit("transfers")


def seed_preorders_sales_invoices_payments(customers, seller_user, warehouses, products):
    wh_main, wh_show, wh_partner = warehouses
    c1, c2 = customers[0], customers[1]

    po, _ = get_or_create(M.PreOrder, reference=None, defaults={
        "customer": c1,
        "product": products[0],
        "warehouse": wh_partner,
        "quantity": 2,
        "prepaid_amount": 100,
        "tax_rate": 0,
        "status": "PENDING",
        "notes": "حجز دينامو للغد",
    })
    db.session.flush()

    p_po = M.Payment(
        total_amount=100,
        method=PaymentMethod.CASH,
        status=PaymentStatus.COMPLETED,
        direction=PaymentDirection.INCOMING,
        entity_type=PaymentEntityType.PREORDER,
        currency="ILS",
        preorder_id=po.id,
        reference="دفعة مقدمة - حجز"
    )
    db.session.add(p_po)

    sale = M.Sale(
        customer=c2,
        seller=seller_user,
        tax_rate=0,
        discount_total=0,
        currency="ILS",
        shipping_cost=0,
        notes="مبيع من صالة العرض",
        status=SaleStatus.DRAFT,
    )
    db.session.add(sale)
    db.session.flush()

    lines = [
        (products[1], wh_show, 2),
        (products[2], wh_show, 4),
    ]
    for prod, wh, qty in lines:
        db.session.add(M.SaleLine(
            sale=sale,
            product=prod,
            warehouse=wh,
            quantity=qty,
            unit_price=prod.price,
            discount_rate=0,
            tax_rate=0,
        ))
    db.session.flush()

    sale.status = SaleStatus.CONFIRMED
    commit("sale-lines-confirmed")

    pay_total = sale.total
    pay = M.Payment(
        total_amount=pay_total,
        method=PaymentMethod.CARD,
        status=PaymentStatus.COMPLETED,
        direction=PaymentDirection.INCOMING,
        entity_type=PaymentEntityType.SALE,
        currency="ILS",
        sale_id=sale.id,
        reference="دفع عبر البطاقة",
    )
    split = M.PaymentSplit(payment=pay, method=PaymentMethod.CARD.value,
                           amount=pay_total, details={"last4": "4242", "brand": "VISA"})
    db.session.add(pay)
    db.session.add(split)
    commit("sale-payment")

    inv = M.Invoice(
        customer=c2,
        sale=sale,
        source=M.InvoiceSource.SALE,
        status=M.InvoiceStatus.UNPAID,
        currency="ILS",
        notes="فاتورة بيع من الصالة",
    )
    db.session.add(inv)
    db.session.flush()

    for sl in sale.lines:
        db.session.add(M.InvoiceLine(
            invoice=inv,
            description=sl.product.name,
            quantity=sl.quantity,
            unit_price=sl.unit_price,
            tax_rate=sl.tax_rate,
            discount=sl.discount_rate,
            product=sl.product,
        ))
    commit("invoice-lines")

    inv_pay = M.Payment(
        total_amount=float(inv.total_amount),
        method=PaymentMethod.CASH,
        status=PaymentStatus.COMPLETED,
        direction=PaymentDirection.INCOMING,
        entity_type=PaymentEntityType.INVOICE,
        currency="ILS",
        invoice_id=inv.id,
        reference="تسديد فاتورة",
    )
    db.session.add(inv_pay)
    commit("invoice-payment")


def seed_service(customers, mechanic_user, warehouses, products, partners):
    wh_main, wh_show, wh_partner = warehouses
    cust = customers[2]

    sr = M.ServiceRequest(
        customer=cust,
        mechanic=mechanic_user,
        vehicle_type=products[0].vehicle_type,
        status=ServiceStatus.IN_PROGRESS,
        priority=ServicePriority.HIGH,
        problem_description="صوت في الدينامو عند التشغيل",
        notes="دخول الصيانة - فحص سريع",
        tax_rate=0,
        discount_total=0,
    )
    db.session.add(sr)
    db.session.flush()

    sp = M.ServicePart(
        request=sr,
        part=products[0],
        warehouse=wh_partner,
        quantity=1,
        unit_price=products[0].price,
        discount=0,
        tax_rate=0,
        note="تركيب دينامو مستعمل جيد",
        partner=partners[0],
        share_percentage=40,
    )
    db.session.add(sp)

    task = M.ServiceTask(
        request=sr,
        description="أجرة صيانة كهرباء",
        quantity=1,
        unit_price=120,
        discount=0,
        tax_rate=0,
        partner=None,
        share_percentage=0,
    )
    db.session.add(task)
    commit("service parts+tasks")

    sr.status = ServiceStatus.COMPLETED
    commit("service-completed")

    pay = M.Payment(
        total_amount=float(sr.total),
        method=PaymentMethod.BANK,
        status=PaymentStatus.COMPLETED,
        direction=PaymentDirection.INCOMING,
        entity_type=PaymentEntityType.SERVICE,
        currency="ILS",
        service_id=sr.id,
        reference="تحويل بنكي مقابل صيانة",
    )
    db.session.add(pay)
    commit("service-payment")


def seed_online(customers, products):
    cust = customers[3]

    cart = M.OnlineCart(customer=cust, status="ACTIVE", expires_at=datetime.utcnow() + timedelta(days=5))
    db.session.add(cart)
    db.session.flush()

    items = [(products[2], 3), (products[1], 1)]
    for prod, qty in items:
        db.session.add(M.OnlineCartItem(cart=cart, product=prod, quantity=qty, price=prod.price))
    commit("online-cart-items")

    opr = M.OnlinePreOrder(customer=cust, cart=cart, status="PENDING", payment_status="PENDING")
    db.session.add(opr)
    db.session.flush()

    for ci in cart.items:
        db.session.add(M.OnlinePreOrderItem(order=opr, product=ci.product, quantity=ci.quantity, price=ci.price))
    commit("online-preorder-items")

    op = M.OnlinePayment(order=opr, amount=opr.items_subtotal, currency="ILS",
                         method=PaymentMethod.CARD.value, gateway="stripe", status="SUCCESS")
    op.card_last4 = "4242"
    op.card_brand = "VISA"
    op.card_expiry = "12/28"
    op.cardholder_name = f"{cust.name}"
    db.session.add(op)
    commit("online-payment")


def seed_expenses_and_payables(employees, warehouses, partners, suppliers):
    e_types = [
        ("وقود", "ديزل وبنزين"),
        ("كهرباء", "فاتورة شركة الكهرباء"),
        ("ماء", "فاتورة سلطة المياه"),
        ("رواتب", "رواتب موظفين"),
        ("قرطاسية", "مشتريات مكتبية"),
    ]
    et_objs = []
    for name, desc in e_types:
        et, _ = get_or_create(M.ExpenseType, name=name, defaults={"description": desc})
        et_objs.append(et)

    emp = employees[0]
    wh = warehouses[0]
    par = partners[0]

    exp1 = M.Expense(
        date=datetime.utcnow() - timedelta(days=3),
        amount=350.00, currency="ILS",
        type=et_objs[0], employee=emp, warehouse=wh,
        payment_method=PaymentMethod.CARD.value,
        card_holder=emp.name, card_expiry="11/27", card_number="1234",
        description="وقود سيارات التوصيل",
    )
    exp2 = M.Expense(
        date=datetime.utcnow() - timedelta(days=2),
        amount=1250.00, currency="ILS",
        type=et_objs[1], warehouse=wh, partner=par,
        payment_method=PaymentMethod.BANK.value,
        bank_transfer_ref="TRX-ELC-2025-001",
        description="فاتورة كهرباء الشهر",
    )
    db.session.add_all([exp1, exp2])
    commit("expenses")

    pay1 = M.Payment(
        total_amount=1250.00, method=PaymentMethod.BANK,
        status=PaymentStatus.COMPLETED, direction=PaymentDirection.OUTGOING,
        entity_type=PaymentEntityType.EXPENSE, currency="ILS", expense_id=exp2.id,
        reference="سداد كهرباء",
    )
    db.session.add(pay1)

    sup = suppliers[0]
    settle = M.SupplierLoanSettlement(supplier=sup, settled_price=800.00, notes="تسوية دفعة قطع على الحساب")
    db.session.add(settle)
    db.session.flush()

    p_settle = settle.build_payment(status=PaymentStatus.COMPLETED, method=PaymentMethod.BANK)
    db.session.add(p_settle)
    commit("expense+loan payments")


def seed_notes(customers, users):
    c = customers[0]
    u = users[0]
    note = M.Note(content="الزبون مداوم على الصيانة كل ٣ أشهر. اعملوا خصم ٥٪ إذا كانت الفاتورة فوق ١٠٠٠ شيكل.",
                  author=u, entity_type="CUSTOMER", entity_id=c.id, is_pinned=True, priority="HIGH")
    db.session.add(note)
    commit("notes")
