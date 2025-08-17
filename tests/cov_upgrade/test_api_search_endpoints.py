import pytest
from flask import url_for
from extensions import db
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
)

@pytest.fixture
def _seed_api(app):
    with app.app_context():
        c = Customer(name="Cust A", phone="1", email="a@x")
        s = Supplier(name="Supp A")
        pr= Partner(name="Part A")
        pc= ProductCategory(name="Cat A")
        p = Product(name="Prod A", sku="A1", price=1)
        w = Warehouse(name="W A", warehouse_type="MAIN", is_active=True)
        u = User(username="uapi", email="u@x"); u.set_password("x")
        e = Employee(name="Emp A")
        inv = Invoice(customer_id=1, total_amount=1, status="UNPAID")
        svc = ServiceRequest(customer_id=1, vehicle_vrn="XYZ")
        stl = SupplierLoanSettlement(supplier_id=1, settled_price=10)
        pay = Payment(total_amount=1, currency="ILS", status="PENDING", direction="IN", entity_type="CUSTOMER", customer_id=1)
        db.session.add_all([c,s,pr,pc,p,w,u,e,inv,svc,stl,pay]); db.session.commit()
        yield

@pytest.mark.usefixtures("client", "_seed_api")
def test_api_search_endpoints_matrix(client):
    # كل اندبوينت مع q أو بدونه
    eps = [
        ("api.customers", {"q":"Cust"}), ("api.search_customers", {"q":""}),
        ("api.suppliers", {"q":"Supp"}), ("api.partners", {"q":"Part"}),
        ("api.products", {"q":"Prod"}), ("api.search_products", {"q":"A1"}),
        ("api.categories", {"q":"Cat"}),
        ("api.warehouses", {"q":"W"}), ("api.search_warehouses", {}),
        ("api.users", {"q":"u@"}),
        ("api.employees", {"q":"Emp"}),
        ("api.equipment_types", {"q":""}),
        ("api.invoices", {"q":"INV"}),
        ("api.services", {"q":"SVC"}),
        ("api.loan_settlements", {"q":"1"}),
        ("api.search_payments", {"q":""}),
    ]
    for ep, q in eps:
        r = client.get(url_for(ep), query_string=q)
        assert r.status_code == 200 and r.is_json
        # الشكل العام لخيارات select2
        data = r.get_json()
        assert isinstance(data, list) or isinstance(data, dict)
