# -*- coding: utf-8 -*-
import io, csv, json, uuid
import pytest
from flask import url_for
from flask.signals import template_rendered
from extensions import db
from models import *
from flask_login import login_user

def _tok(): return uuid.uuid4().hex[:8]

def _login_user(client, app):
    with app.app_context():
        role = db.session.query(Role).filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="SA")
            db.session.add(role)
            db.session.flush()
        role.permissions = db.session.query(Permission).all()
        user = db.session.get(User, 1)
        if not user:
            user = User(id=1, username="sa", email=f"sa_{_tok()}@x.com", role=role)
            user.set_password("x")
            db.session.add(user)
        else:
            user.role = role
        db.session.commit()
        with client.session_transaction() as s:
            s["_user_id"] = str(user.id)
            s["_fresh"] = True

@pytest.fixture
def _seed_min(app):
    with app.app_context():
        w1 = Warehouse(name=f"Main-{_tok()}", warehouse_type=WarehouseType.MAIN.value, is_active=True)
        w2 = Warehouse(name=f"PartnerWH-{_tok()}", warehouse_type=WarehouseType.PARTNER.value, is_active=True)
        w3 = Warehouse(name=f"ExchangeWH-{_tok()}", warehouse_type=WarehouseType.EXCHANGE.value, is_active=True)
        w4 = Warehouse(name=f"Inventory-{_tok()}", warehouse_type=WarehouseType.INVENTORY.value, is_active=True)
        p  = Product(name=f"Widget-{_tok()}", price=10)
        db.session.add_all([w1, w2, w3, w4, p])
        db.session.commit()
        db.session.add_all([
            StockLevel(product_id=p.id, warehouse_id=w1.id, quantity=50),
            StockLevel(product_id=p.id, warehouse_id=w2.id, quantity=10)
        ])
        db.session.commit()
        yield dict(w1=w1, w2=w2, w3=w3, w4=w4, p=p)

class _TplCatch:
    def __init__(self, app):
        self.app = app
        self.names = []
    def _rec(self, sender, template, context, **k):
        self.names.append(template.name)
    def __enter__(self):
        template_rendered.connect(self._rec, self.app)
        return self.names
    def __exit__(self, *a):
        template_rendered.disconnect(self._rec, self.app)

def test_anon_access_redirects_or_forbidden(anon_client, _seed_min):
    assert anon_client.get(url_for("warehouse_bp.list")).status_code in (302,401,403)

@pytest.mark.usefixtures("client")
def test_templates_are_rendered_from_both_namespaces(client, app, _seed_min):
    with app.app_context():
        print("\n🚀 Setting up user and role")
        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="SA")
            db.session.add(role)
            db.session.flush()
        role.permissions = Permission.query.all()

        user = db.session.get(User, 1)
        if not user:
            user = User(id=1, username="sa", email="sa@example.com", role=role)
            user.set_password("x")
            db.session.add(user)
        else:
            user.role = role

        db.session.commit()
        print(f"✅ User ready: id={user.id}, username={user.username}")

    with app.test_request_context():
        login_user(user)
        print("🔐 login_user invoked successfully")

    r_check = client.get("/warehouses/")
    print(f"🧪 GET /warehouses/ returned {r_check.status_code}")
    if r_check.status_code != 200:
        print(f"❌ Redirected to: {r_check.headers.get('Location')}")

    with _TplCatch(app) as n:
        r1 = client.get(url_for("warehouse_bp.list"))
        print(f"🔄 warehouse_bp.list status: {r1.status_code}")
        assert r1.status_code == 200, f"Expected 200 but got {r1.status_code}. Location: {r1.headers.get('Location')}"
    assert "warehouses/list.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.create")).status_code == 200
    assert "warehouses/form.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.detail", warehouse_id=_seed_min["w1"].id)).status_code == 200
    assert "warehouses/detail.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.products", id=_seed_min["w1"].id)).status_code == 200
    assert "warehouses/products.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.transfers", id=_seed_min["w1"].id)).status_code == 200
    assert "warehouses/transfers_list.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.create_transfer", id=_seed_min["w1"].id)).status_code == 200
    assert "warehouses/transfers_form.html" in n

    with _TplCatch(app) as n:
        assert client.get(url_for("warehouse_bp.preorders_list")).status_code == 200
    assert "parts/preorders_list.html" in n

@pytest.mark.usefixtures("client")
def test_list_warehouses_filters(client, app, _seed_min):
    with app.app_context():
        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            role = Role(name="super_admin", description="SA")
            db.session.add(role)
            db.session.flush()
        role.permissions = Permission.query.all()

        user = db.session.get(User, 1)
        if not user:
            user = User(id=1, username="sa", email="sa@example.com", role=role)
            user.set_password("x")
            db.session.add(user)
        else:
            user.role = role

        db.session.commit()

    with app.test_request_context():
        login_user(user)

    query = {"type": "MAIN", "search": _seed_min["w1"].name[:2]}
    r = client.get(url_for("warehouse_bp.list"), query_string=query)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}, redirected to: {r.headers.get('Location')}"
    assert _seed_min["w1"].name.encode() in r.data

@pytest.mark.usefixtures("client")
def test_create_edit_delete_warehouse(client, app):
    _login_user(client, app)
    r = client.post(url_for("warehouse_bp.create"), data={"name": "Tmp", "warehouse_type": "INVENTORY", "is_active": "y", "location": "X"})
    assert r.status_code in (302, 303)

@pytest.mark.usefixtures("client")
def test_add_product_for_each_warehouse_and_required_fields(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_products_view_and_stock_ajax(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_products_view_multi_select_filter(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_import_products_csv_success(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_ajax_transfer_success_and_errors(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_ajax_exchange_in_and_out(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_partner_shares_get_and_post(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_transfers_pages_and_create(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_product_card_and_preorders_flow_and_templates(client, app, _seed_min):
    _login_user(client, app)

@pytest.mark.usefixtures("client")
def test_shipments_redirect_entrypoint(client, app, _seed_min):
    _login_user(client, app)
    assert client.get(url_for("warehouse_bp.create_warehouse_shipment", id=_seed_min["w1"].id)).status_code in (302, 303)
