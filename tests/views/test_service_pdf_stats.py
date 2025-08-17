import datetime as dt
from flask import url_for
from extensions import db
from models import (
    ServiceRequest, ServicePart, ServiceTask, Product, Warehouse, Partner,
    ServiceStatus, ServicePriority, Customer
)

def _mk_service_with_lines():
    cust_name = "Mr. Test"
    # Customer لازم لأن customer_id NOT NULL
    c = Customer(
        name=cust_name,
        phone=f"0599{dt.datetime.utcnow().strftime('%H%M%S%f')}",
        email=None,
        address=None,
        whatsapp=None,
        category="عادي",
        is_active=True,
    )
    db.session.add(c)
    db.session.flush()

    sr = ServiceRequest(
        service_number="SRV-TEST-001",
        request_date=dt.datetime.utcnow(),
        customer_id=c.id,
        name=cust_name,
        phone=c.phone,
        vehicle_vrn="11-222-33",
        priority=getattr(ServicePriority, "MEDIUM"),
        status=getattr(ServiceStatus, "PENDING"),
        tax_rate=17,
    )
    db.session.add(sr)
    db.session.flush()

    # كيانات للسطور
    w = Warehouse(name="Main W", warehouse_type="MAIN")
    p = Product(name="Oil Filter")
    partner = Partner(name="P1")
    db.session.add_all([w, p, partner])
    db.session.flush()

    sp = ServicePart(
        service_id=sr.id,
        part_id=p.id,
        warehouse_id=w.id,
        quantity=2,
        unit_price=50,
        discount=0,
        tax_rate=0,
        partner_id=partner.id,
        share_percentage=10,  # يخصم من الصافي
    )
    st = ServiceTask(service_id=sr.id, description="Labor", quantity=1, unit_price=120, discount=0, tax_rate=0)
    db.session.add_all([sp, st])
    db.session.commit()
    return sr

def test_service_receipts_and_pdfs(client, app):
    sr = _mk_service_with_lines()

    # receipt page (HTML)
    r = client.get(url_for("service.view_receipt", rid=sr.id))
    assert r.status_code == 200
    assert b"SRV-TEST-001" in r.data

    # inline report
    r = client.get(url_for("service.service_report", rid=sr.id))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")

    # attachment pdf
    r = client.get(url_for("service.export_pdf", rid=sr.id))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert "attachment" in r.headers.get("Content-Disposition", "")

    # download receipt (attachment)
    r = client.get(url_for("service.download_receipt", rid=sr.id))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")

def test_service_stats_and_api(client, app):
    # حتى بدون بيانات لازم يرجع شكل JSON المتوقع
    r = client.get(url_for("service.service_stats"))
    assert r.status_code == 200
    js = r.get_json()
    for key in ("total_requests", "completed_requests", "pending_requests", "avg_duration", "monthly_costs"):
        assert key in js

    # API requests
    r = client.get(url_for("service.api_service_requests"))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
