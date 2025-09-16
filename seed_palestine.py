from __future__ import annotations
import click
from datetime import datetime, timedelta
from decimal import Decimal
from flask.cli import with_appcontext
from extensions import db
from models import (
    Customer, Supplier, Partner,
    Warehouse, WarehouseType,
    ProductCategory, EquipmentType, Product, StockLevel,
    Transfer, ExchangeTransaction, TransferDirection,
    PreOrder, Sale, SaleLine,
    Invoice, InvoiceLine,
    Payment, PaymentMethod, PaymentStatus, PaymentDirection, PaymentEntityType,
    Shipment, ShipmentItem,
    PartnerSettlement, SupplierSettlement,
)
try:
    from models import ServiceRequest, ServiceStatus, ServicePriority
    HAVE_SERVICE = True
except Exception:
    HAVE_SERVICE = False
try:
    from models import get_or_create_online_warehouse, ensure_online_stock_level
except Exception:
    def get_or_create_online_warehouse():
        wh = Warehouse.query.filter_by(warehouse_type=WarehouseType.ONLINE.value, is_active=True).first()
        if not wh:
            wh = Warehouse(name="ONLINE", warehouse_type=WarehouseType.ONLINE.value, is_active=True)
            db.session.add(wh); db.session.commit()
        return wh
    def ensure_online_stock_level(product_id: int):
        wh = get_or_create_online_warehouse()
        if not StockLevel.query.filter_by(product_id=product_id, warehouse_id=wh.id).first():
            db.session.add(StockLevel(product_id=product_id, warehouse_id=wh.id, quantity=0))
            db.session.flush()
        return wh.id
def _pick_user_id() -> int | None:
    try:
        from models import User
        u = User.query.order_by(User.id.asc()).first()
        return getattr(u, "id", None)
    except Exception:
        return None
SEED_TAG = "SEED-PS"
def _q(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Decimal("0.01"))
def _get_or_create(model, defaults=None, **kwargs):
    obj = model.query.filter_by(**kwargs).first()
    if obj:
        if defaults:
            for k, v in defaults.items():
                if getattr(obj, k, None) in (None, "", 0):
                    setattr(obj, k, v)
        return obj, False
    params = dict(kwargs)
    if defaults:
        params.update(defaults)
    obj = model(**params)
    db.session.add(obj)
    return obj, True
def _ensure_categories():
    names = ["زيوت", "فلاتر", "قطع ميكانيكية", "كهرباء", "إكسسوارات", "إطارات", "بطاريات"]
    out = []
    for n in names:
        c, _ = _get_or_create(ProductCategory, name=n)
        out.append(c)
    return out
def _ensure_equipment_types():
    names = ["سيارة ركوب", "شاحنة خفيفة", "فان تجاري", "معدة ثقيلة"]
    out = []
    for n in names:
        et, _ = _get_or_create(EquipmentType, name=n)
        out.append(et)
    return out
def _ensure_suppliers():
    data = [
        dict(name="شركة القدس للتجارة", is_local=True, email="qods@supplier.ps", currency="ILS", notes=SEED_TAG),
        dict(name="مورد غزة الموحد", is_local=True, email="gaza@supplier.ps", currency="ILS", notes=SEED_TAG),
        dict(name="مجموعة رام الله للمحركات", is_local=True, email="ramallah@supplier.ps", currency="ILS", notes=SEED_TAG),
        dict(name="الخليل للصناعات المعدنية", is_local=True, email="hebron@supplier.ps", currency="ILS", notes=SEED_TAG),
        dict(name="نابلس أوتو سبير بارتس", is_local=True, email="nablus@supplier.ps", currency="ILS", notes=SEED_TAG),
    ]
    out = []
    for row in data:
        s, _ = _get_or_create(Supplier, name=row["name"], defaults=row)
        out.append(s)
    return out
def _ensure_partners():
    data = [
        dict(name="شريك البيرة للتجارة", email="partner.albireh@partner.ps", share_percentage=20, currency="ILS", balance=0, notes=SEED_TAG),
        dict(name="شريك بيت لحم", email="bethlehem@partner.ps", share_percentage=35, currency="ILS", balance=0, notes=SEED_TAG),
        dict(name="شريك جنين", email="jenin@partner.ps", share_percentage=40, currency="ILS", balance=0, notes=SEED_TAG),
    ]
    out = []
    for row in data:
        p, _ = _get_or_create(Partner, name=row["name"], defaults=row)
        out.append(p)
    return out
def _ensure_warehouses(suppliers, partners):
    main, _ = _get_or_create(
        Warehouse, name="الرئيسي - رام الله",
        defaults=dict(warehouse_type=WarehouseType.MAIN.value, location="رام الله", is_active=True, notes=SEED_TAG)
    )
    exch_supplier = suppliers[0] if suppliers else None
    exchange, _ = _get_or_create(
        Warehouse, name="تبادل - مورد القدس",
        defaults=dict(warehouse_type=WarehouseType.EXCHANGE.value, location="القدس", is_active=True, supplier_id=getattr(exch_supplier, "id", None), notes=SEED_TAG)
    )
    partner = partners[0] if partners else None
    w_partner, _ = _get_or_create(
        Warehouse, name="شريك - البيرة",
        defaults=dict(warehouse_type=WarehouseType.PARTNER.value, location="البيرة", is_active=True, partner_id=getattr(partner, "id", None), share_percent=40, notes=SEED_TAG)
    )
    online = get_or_create_online_warehouse()
    if not getattr(online, "online_slug", None):
        online.online_slug = "default"
        online.online_is_default = True
    return main, exchange, w_partner, online
def _ensure_customers():
    data = [
        dict(name="محمد بركات", phone="+970599111001", whatsapp="+970599111001", email="m.barakat@test.ps", address="رام الله", currency="ILS", credit_limit=5000, discount_rate=5, notes=SEED_TAG),
        dict(name="أحمد درويش", phone="+970599111002", whatsapp="+970599111002", email="a.darwish@test.ps", address="البيرة", currency="ILS", credit_limit=3000, discount_rate=0, notes=SEED_TAG),
        dict(name="حسام عويضات", phone="+970599111003", whatsapp="+970599111003", email="h.owaidat@test.ps", address="نابلس", currency="ILS", credit_limit=8000, discount_rate=10, notes=SEED_TAG),
        dict(name="سهى حمزة", phone="+970569111004", whatsapp="+970569111004", email="suha.hamzeh@test.ps", address="الخليل", currency="ILS", credit_limit=0, discount_rate=0, notes=SEED_TAG),
        dict(name="زبون نقدي", phone="+970569111005", whatsapp="+970569111005", email="cash@test.ps", address="عام", currency="ILS", credit_limit=0, discount_rate=0, notes=SEED_TAG, category="عادي"),
    ]
    out = []
    for row in data:
        c, _ = _get_or_create(Customer, phone=row["phone"], defaults=row)
        out.append(c)
    return out
def _ensure_products(categories, equipment_types, suppliers):
    cat_map = {c.name: c for c in categories}
    et = equipment_types[0] if equipment_types else None
    sup = suppliers[0] if suppliers else None
    rows = [
        dict(sku="PS-OIL-5W30", name="زيت محرك 5W-30", brand="Castrol", part_number="5W30-1L", price=35, purchase_price=20, category=cat_map["زيوت"]),
        dict(sku="PS-FLTR-OP123", name="فلتر زيت OP123", brand="MANN", part_number="OP123", price=25, purchase_price=12, category=cat_map["فلاتر"]),
        dict(sku="PS-BATT-70AH", name="بطارية 70 أمبير", brand="VARTA", part_number="70AH", price=380, purchase_price=300, category=cat_map["بطاريات"]),
        dict(sku="PS-BELT-ALT", name="سير دينامو", brand="Gates", part_number="ALT-BELT", price=90, purchase_price=60, category=cat_map["قطع ميكانيكية"]),
        dict(sku="PS-LAMP-H7", name="لمبة H7 55W", brand="Philips", part_number="H7-55W", price=18, purchase_price=10, category=cat_map["كهرباء"]),
        dict(sku="PS-WIPER-22", name="مساحات 22 إنش", brand="Bosch", part_number="WIP-22", price=28, purchase_price=16, category=cat_map["إكسسوارات"]),
    ]
    out = []
    for r in rows:
        defaults = dict(
            name=r["name"], brand=r["brand"], part_number=r["part_number"],
            price=r["price"], purchase_price=r["purchase_price"],
            category_id=r["category"].id, vehicle_type_id=getattr(et, "id", None),
            supplier_id=getattr(sup, "id", None),
            condition="NEW", is_active=True, notes=SEED_TAG
        )
        p, _ = _get_or_create(Product, sku=r["sku"], defaults=defaults)
        out.append(p)
    return out
def _ensure_stock(products, main, exchange, partner, online):
    pack = [
        (products[0], main, 60), (products[0], partner, 20),
        (products[1], main, 40), (products[1], exchange, 25),
        (products[2], main, 10),
        (products[3], main, 30), (products[3], partner, 10),
        (products[4], main, 50),
        (products[5], main, 35),
    ]
    for prod, wh, qty in pack:
        row = StockLevel.query.filter_by(product_id=prod.id, warehouse_id=wh.id).first()
        if not row:
            db.session.add(StockLevel(product_id=prod.id, warehouse_id=wh.id, quantity=qty, reserved_quantity=0))
        else:
            if (row.quantity or 0) < qty:
                row.quantity = qty
    for p in products:
        ensure_online_stock_level(p.id)
def _make_transfer(products, main, partner, seller_id):
    t = Transfer(
        product_id=products[0].id,
        source_id=main.id,
        destination_id=partner.id,
        quantity=5,
        direction=TransferDirection.OUTGOING.value if hasattr(TransferDirection, "OUTGOING") else "OUTGOING",
        notes=SEED_TAG,
        user_id=seller_id
    )
    db.session.add(t)
def _make_exchange_purchase(products, exchange):
    xt = ExchangeTransaction(
        product_id=products[1].id,
        warehouse_id=exchange.id,
        quantity=10,
        direction="IN",
        unit_cost=Decimal("11.50"),
        notes=SEED_TAG
    )
    db.session.add(xt)
def _make_shipment(products, main):
    shp = Shipment(
        date=datetime.utcnow() - timedelta(days=3),
        destination_id=main.id,
        status="DRAFT",
        currency="USD",
        notes=SEED_TAG
    )
    db.session.add(shp); db.session.flush()
    items = [
        ShipmentItem(shipment_id=shp.id, product_id=products[4].id, warehouse_id=main.id, quantity=40, unit_cost=Decimal("7.20")),
        ShipmentItem(shipment_id=shp.id, product_id=products[5].id, warehouse_id=main.id, quantity=25, unit_cost=Decimal("12.00")),
    ]
    db.session.add_all(items)
    db.session.flush()
    shp.status = "ARRIVED"
def _make_sale_and_payment(customers, products, main, seller_id):
    c = customers[0]
    sale = Sale(
        customer_id=c.id,
        seller_id=seller_id or 1,
        sale_date=datetime.utcnow() - timedelta(days=1),
        tax_rate=16, discount_total=0, shipping_cost=0,
        currency="ILS",
        status="DRAFT",
        notes=SEED_TAG
    )
    db.session.add(sale); db.session.flush()
    l1 = SaleLine(sale_id=sale.id, product_id=products[0].id, warehouse_id=main.id, quantity=2, unit_price=products[0].price, discount_rate=0, tax_rate=0)
    l2 = SaleLine(sale_id=sale.id, product_id=products[1].id, warehouse_id=main.id, quantity=1, unit_price=products[1].price, discount_rate=0, tax_rate=0)
    db.session.add_all([l1, l2]); db.session.flush()
    sale.status = "CONFIRMED"
    db.session.flush()
    pay1 = Payment(
        total_amount=Decimal("50.00"),
        currency="ILS",
        method=PaymentMethod.CASH.value,
        status=PaymentStatus.COMPLETED.value,
        direction=PaymentDirection.INCOMING.value,
        entity_type=PaymentEntityType.SALE.value,
        sale_id=sale.id,
        notes=SEED_TAG
    )
    db.session.add(pay1); db.session.flush()
    remain = Decimal(str(sale.total_amount or 0)) - Decimal("50.00")
    if remain > 0:
        pay2 = Payment(
            total_amount=remain,
            currency="ILS",
            method=PaymentMethod.CARD.value,
            status=PaymentStatus.COMPLETED.value,
            direction=PaymentDirection.INCOMING.value,
            entity_type=PaymentEntityType.SALE.value,
            sale_id=sale.id,
            notes=SEED_TAG
        )
        db.session.add(pay2)
def _make_invoice_and_payment(customers, products):
    c = customers[1]
    inv = Invoice(
        customer_id=c.id,
        currency="ILS",
        invoice_date=datetime.utcnow() - timedelta(days=2),
        due_date=datetime.utcnow() + timedelta(days=5),
        source="MANUAL",
        status="UNPAID",
        total_amount=0, tax_amount=0, discount_amount=0,
        notes=SEED_TAG
    )
    db.session.add(inv); db.session.flush()
    lines = [
        InvoiceLine(invoice_id=inv.id, description="أجرة فحص عام", quantity=1, unit_price=Decimal("50.00"), tax_rate=0, discount=0),
        InvoiceLine(invoice_id=inv.id, product_id=products[2].id, description="بطارية 70 أمبير", quantity=1, unit_price=products[2].price, tax_rate=0, discount=0),
    ]
    db.session.add_all(lines); db.session.flush()
    pay = Payment(
        total_amount=Decimal("100.00"),
        currency="ILS",
        method=PaymentMethod.BANK.value,
        status=PaymentStatus.COMPLETED.value,
        direction=PaymentDirection.INCOMING.value,
        entity_type=PaymentEntityType.INVOICE.value,
        invoice_id=inv.id,
        notes=SEED_TAG
    )
    db.session.add(pay)
def _make_preorder(customers, products, main):
    pr = PreOrder(
        preorder_date=datetime.utcnow(),
        expected_date=datetime.utcnow() + timedelta(days=7),
        customer_id=customers[2].id,
        product_id=products[3].id,
        warehouse_id=main.id,
        quantity=3,
        prepaid_amount=Decimal("60.00"),
        tax_rate=0,
        status="PENDING",
        payment_method=PaymentMethod.CASH.value,
        notes=SEED_TAG
    )
    db.session.add(pr); db.session.flush()
    pay = Payment(
        total_amount=Decimal("60.00"),
        currency="ILS",
        method=PaymentMethod.CASH.value,
        status=PaymentStatus.COMPLETED.value,
        direction=PaymentDirection.INCOMING.value,
        entity_type=PaymentEntityType.PREORDER.value,
        preorder_id=pr.id,
        notes=SEED_TAG
    )
    db.session.add(pay)
def _maybe_make_service(customers, products, main, mechanic_id):
    if not HAVE_SERVICE or mechanic_id is None:
        return
    sr = ServiceRequest(
        customer_id=customers[3].id,
        tax_rate=0,
        discount_total=0,
        currency="ILS",
        status=ServiceStatus.IN_PROGRESS.value,
        notes=SEED_TAG
    )
    if hasattr(sr, "mechanic_id"):
        sr.mechanic_id = mechanic_id
    if hasattr(sr, "consume_stock"):
        sr.consume_stock = True
    if hasattr(sr, "received_at"):
        sr.received_at = datetime.utcnow() - timedelta(days=1)
    if hasattr(sr, "priority"):
        sr.priority = getattr(ServicePriority, "MEDIUM").value if hasattr(ServicePriority, "MEDIUM") else getattr(ServicePriority, list(ServicePriority)[0].name).value
    if hasattr(sr, "problem_description"):
        sr.problem_description = "صوت في المحرك"
    if hasattr(sr, "diagnosis"):
        sr.diagnosis = "بحاجة لتبديل فلتر الزيت"
    db.session.add(sr)
    db.session.flush()
    from models import ServicePart, ServiceTask
    sp = ServicePart(
        service_id=sr.id,
        part_id=products[1].id,
        warehouse_id=main.id,
        quantity=1,
        unit_price=products[1].price,
        discount=0,
        note=SEED_TAG,
    )
    st = ServiceTask(
        service_id=sr.id,
        description="أجور عمل",
        quantity=1,
        unit_price=Decimal("80.00"),
        discount=0,
        note=SEED_TAG,
    )
    db.session.add_all([sp, st])
    db.session.flush()
    try:
        from models import _recalc_service_request_totals
        _recalc_service_request_totals(sr)
    except Exception:
        pass
    sr.status = ServiceStatus.COMPLETED.value
    pay = Payment(
        total_amount=Decimal(str(sr.total_amount or 0)),
        currency="ILS",
        method=PaymentMethod.CASH.value,
        status=PaymentStatus.COMPLETED.value,
        direction=PaymentDirection.INCOMING.value,
        entity_type=PaymentEntityType.SERVICE.value,
        service_id=sr.id,
        notes=SEED_TAG,
    )
    db.session.add(pay)
def _make_settlements(partners, suppliers):
    try:
        from models import build_partner_settlement_draft, build_supplier_settlement_draft
    except Exception:
        return
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=90)
    if partners:
        ps = build_partner_settlement_draft(partners[0].id, date_from, date_to, currency="ILS")
        db.session.add(ps)
    if suppliers:
        ss = build_supplier_settlement_draft(suppliers[0].id, date_from, date_to, currency="ILS")
        db.session.add(ss)
def _cleanup_previous():
    for model, field in [
        (Payment, Payment.notes),
        (InvoiceLine, None),
        (Invoice, Invoice.notes),
        (SaleLine, None),
        (Sale, Sale.notes),
        (PreOrder, PreOrder.notes),
        (ExchangeTransaction, ExchangeTransaction.notes),
        (ShipmentItem, None),
        (Shipment, Shipment.notes),
        (StockLevel, None),
        (Product, Product.notes),
        (ProductCategory, None),
        (EquipmentType, None),
        (Warehouse, Warehouse.notes),
        (Partner, Partner.notes),
        (Supplier, Supplier.notes),
        (Customer, Customer.notes),
    ]:
        try:
            if field is not None:
                db.session.query(model).filter(field == SEED_TAG).delete(synchronize_session=False)
            else:
                if model is SaleLine:
                    sub = db.session.query(Sale.id).filter(Sale.notes == SEED_TAG).subquery()
                    db.session.query(SaleLine).filter(SaleLine.sale_id.in_(sub)).delete(synchronize_session=False)
                elif model is InvoiceLine:
                    sub = db.session.query(Invoice.id).filter(Invoice.notes == SEED_TAG).subquery()
                    db.session.query(InvoiceLine).filter(InvoiceLine.invoice_id.in_(sub)).delete(synchronize_session=False)
                elif model is StockLevel:
                    subp = db.session.query(Product.id).filter(Product.notes == SEED_TAG).subquery()
                    db.session.query(StockLevel).filter(StockLevel.product_id.in_(subp)).delete(synchronize_session=False)
                elif model is ShipmentItem:
                    sub = db.session.query(Shipment.id).filter(Shipment.notes == SEED_TAG).subquery()
                    db.session.query(ShipmentItem).filter(ShipmentItem.shipment_id.in_(sub)).delete(synchronize_session=False)
                else:
                    pass
        except Exception:
            db.session.rollback()
@click.command("seed-palestine")
@click.option("--reset", is_flag=True)
@with_appcontext
def seed_palestine(reset: bool):
    if reset:
        _cleanup_previous()
        db.session.commit()
    seller_id = _pick_user_id()
    mechanic_id = seller_id
    cats = _ensure_categories()
    ets = _ensure_equipment_types()
    suppliers = _ensure_suppliers()
    partners = _ensure_partners()
    main, exchange, wpartner, online = _ensure_warehouses(suppliers, partners)
    customers = _ensure_customers()
    products = _ensure_products(cats, ets, suppliers)
    db.session.flush()
    _ensure_stock(products, main, exchange, wpartner, online)
    _make_transfer(products, main, wpartner, seller_id)
    _make_exchange_purchase(products, exchange)
    _make_shipment(products, main)
    _make_sale_and_payment(customers, products, main, seller_id)
    _make_invoice_and_payment(customers, products)
    _make_preorder(customers, products, main)
    _maybe_make_service(customers, products, main, mechanic_id)
    _make_settlements(partners, suppliers)
    db.session.commit()
    click.echo("تم إدخال بيانات الاختبار الفلسطينية بنجاح.")
def init_app(app):
    app.cli.add_command(seed_palestine)
