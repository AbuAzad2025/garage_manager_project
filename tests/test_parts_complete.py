import pytest
from flask import url_for
from extensions import db
from models import Product, Warehouse, StockLevel, WarehouseType
from werkzeug.datastructures import MultiDict

# --- Fixtures ---
@pytest.fixture
def spare_part_data():
    return {
        "name": "Oil Filter",
        "sku": "OF-123",
        "barcode": "1234567890123",
        "category": "Filters",
        "unit": "Piece",
        "purchase_price": 10.5,
        "selling_price": 15.0,
        "notes": "Engine use"
    }

# --- Create Warehouse fixture ---
@pytest.fixture
def warehouse():
    w = Warehouse(name="Main WH", warehouse_type=getattr(WarehouseType, "MAIN", "MAIN"))
    db.session.add(w)
    db.session.commit()
    return w

# --- Spare Part Tests ---
def test_create_part(client, spare_part_data):
    r = client.post(url_for("parts_bp.parts_create"), data=spare_part_data, follow_redirects=True)
    assert r.status_code == 200
    assert "تم إضافة القطعة بنجاح" in r.data.decode("utf-8")

    p = Product.query.filter_by(sku="OF-123").first()
    assert p is not None
    assert p.name == "Oil Filter"

def test_create_part_missing_required(client):
    data = {"name": ""}  # missing required fields
    r = client.post(url_for("parts_bp.parts_create"), data=data, follow_redirects=True)
    assert r.status_code == 200
    decoded = r.data.decode("utf-8")
    assert "هذا الحقل مطلوب" in decoded or "خطأ" in decoded

def test_edit_part(client, spare_part_data):
    p = Product(**spare_part_data)
    db.session.add(p)
    db.session.commit()

    updated = spare_part_data.copy()
    updated["name"] = "Updated Filter"
    r = client.post(url_for("parts_bp.parts_edit", id=p.id), data=updated, follow_redirects=True)
    assert r.status_code == 200
    assert "تم تحديث القطعة بنجاح" in r.data.decode("utf-8")

    p = Product.query.get(p.id)
    assert p.name == "Updated Filter"

def test_list_parts(client):
    r = client.get(url_for("parts_bp.parts_list"))
    assert r.status_code == 200
    assert "القطع" in r.data.decode("utf-8")

def test_part_stock_view(client, warehouse, spare_part_data):
    p = Product(**spare_part_data)
    db.session.add(p)
    db.session.flush()

    sl = StockLevel(warehouse_id=warehouse.id, product_id=p.id, quantity=20, reserved_quantity=5)
    db.session.add(sl)
    db.session.commit()

    r = client.get(url_for("parts_bp.stock_levels", id=p.id))
    assert r.status_code == 200
    decoded = r.data.decode("utf-8")
    assert "Main WH" in decoded
    assert "20" in decoded or "المخزون" in decoded

def test_delete_part(client, spare_part_data):
    p = Product(**spare_part_data)
    db.session.add(p)
    db.session.commit()

    r = client.post(url_for("parts_bp.parts_delete", id=p.id), follow_redirects=True)
    assert r.status_code == 200
    assert "تم حذف القطعة بنجاح" in r.data.decode("utf-8")
    assert Product.query.get(p.id) is None
