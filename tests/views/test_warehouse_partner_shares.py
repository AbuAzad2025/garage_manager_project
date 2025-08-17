from flask import url_for
from extensions import db
from models import Warehouse, WarehouseType, Product, StockLevel, Partner

def _mk_warehouse_with_product():
    w = Warehouse(name="W-Partner", warehouse_type=getattr(WarehouseType, "PARTNER").value if hasattr(WarehouseType, "PARTNER") else "PARTNER")
    p = Product(name="Brake Pad")
    db.session.add_all([w, p])
    db.session.flush()
    sl = StockLevel(warehouse_id=w.id, product_id=p.id, quantity=10, reserved_quantity=0)
    db.session.add(sl)
    db.session.commit()
    return w, p

def test_partner_shares_get_and_post(client, app):
    w, p = _mk_warehouse_with_product()
    partner = Partner(name="Share P")
    db.session.add(partner)
    db.session.commit()

    # GET shares (مبدئياً فاضي)
    r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w.id))
    assert r.status_code == 200
    js = r.get_json()
    assert js["success"] is True
    assert isinstance(js["shares"], list)

    # POST shares (ينشئ تعريفات شراكة للمنتجات الموجودة في المستودع)
    payload = {
        "shares": [
            {
                "product_id": p.id,
                "partner_id": partner.id,
                "share_percentage": 25.0,
                "share_amount": 0,
                "notes": "test",
            }
        ]
    }
    r = client.post(url_for("warehouse_bp.partner_shares", warehouse_id=w.id), json=payload)
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # GET مرة ثانية نتأكد ما انهار شيء
    r = client.get(url_for("warehouse_bp.partner_shares", warehouse_id=w.id))
    assert r.status_code == 200
