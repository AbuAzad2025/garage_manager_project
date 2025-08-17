import pytest
import uuid
from flask import url_for
from extensions import db
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
)

@pytest.fixture
def _seed_api(app):
    with app.app_context():
        tok = uuid.uuid4().hex[:8]
        c = Customer(name=f"Cust A {tok}", phone=f"9{int(uuid.uuid4().int % 10**9):09d}", email=f"a{tok}@x")
        s = Supplier(name=f"Supp A {tok}")
        pr = Partner(name=f"Part A {tok}")
        pc = ProductCategory(name=f"Cat A {tok}")
        p = Product(name=f"Prod A {tok}", sku=f"A1-{tok}", price=1)
        w = Warehouse(name=f"W A {tok}", warehouse_type="MAIN", is_active=True)
        u = User(username=f"uapi_{tok}", email=f"u{tok}@x"); u.set_password("x")
        e = Employee(name=f"Emp A {tok}")
        db.session.add_all([c, s, pr, pc, p, w, u, e]); db.session.flush()
        inv = Invoice(customer_id=c.id, total_amount=1, status="UNPAID")
        svc = ServiceRequest(customer_id=c.id, vehicle_vrn="XYZ")
        stl = SupplierLoanSettlement(supplier_id=s.id, settled_price=10)
        pay = Payment(total_amount=1, currency="ILS", status="PENDING", direction="IN", entity_type="CUSTOMER", customer_id=c.id)
        db.session.add_all([inv, svc, stl, pay]); db.session.commit()
        yield

@pytest.mark.usefixtures("client", "_seed_api")
def test_api_search_endpoints_matrix(client):
    eps = [
        ("api.customers", {"q": "Cust"}), ("api.search_customers", {"q": ""}),
        ("api.suppliers", {"q": "Supp"}), ("api.partners", {"q": "Part"}),
        ("api.products", {"q": "Prod"}), ("api.search_products", {"q": "A1"}),
        ("api.categories", {"q": "Cat"}),
        ("api.warehouses", {"q": "W"}), ("api.search_warehouses", {}),
        ("api.users", {"q": "u@"}),
        ("api.employees", {"q": "Emp"}),
        ("api.equipment_types", {"q": ""}),
        ("api.invoices", {"q": "INV"}),
        ("api.services", {"q": "SVC"}),
        ("api.loan_settlements", {"q": "1"}),
        ("api.search_payments", {"q": ""}),
    ]
    for ep, q in eps:
        r = client.get(url_for(ep), query_string=q)
        assert r.status_code == 200 and r.is_json
        data = r.get_json()
        assert isinstance(data, list) or isinstance(data, dict)
