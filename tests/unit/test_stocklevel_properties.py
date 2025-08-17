import pytest
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Warehouse, Product, StockLevel

def _mk_wh_partner():
    # النوع ممكن يكون Enum أو نص؛ الموديل يتعامل مع الحالتين
    return Warehouse(name="Partner WH", warehouse_type="PARTNER", share_percent=25)

def test_partner_company_share_quantities(app):
    wh = _mk_wh_partner()
    prod = Product(name="Oil Filter")
    sl = StockLevel(product=prod, warehouse=wh, quantity=100, reserved_quantity=5)
    # 25% للشريك
    assert sl.partner_share_quantity == 25
    assert sl.company_share_quantity == 75

def test_stock_status_edges(app):
    wh = _mk_wh_partner()
    prod = Product(name="Brake Pad")
    sl = StockLevel(product=prod, warehouse=wh, quantity=10, min_stock=10, max_stock=20)
    assert sl.status == "تحت الحد الأدنى" or sl.status == "طبيعي"  # عند الحافة مقبول أي تفسير حسب القالب
    sl.quantity = 21
    assert sl.status == "فوق الحد الأقصى"
    sl.quantity = 15
    assert sl.status == "طبيعي"

def test_reserved_quantity_db_check_constraint(client, app):
    wh = _mk_wh_partner()
    prod = Product(name="Belt")
    sl = StockLevel(product=prod, warehouse=wh, quantity=3, reserved_quantity=0)
    db.session.add_all([wh, prod, sl])
    db.session.commit()

    sl.reserved_quantity = -1
    db.session.add(sl)
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
