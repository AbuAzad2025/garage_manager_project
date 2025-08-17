# -*- coding: utf-8 -*-
import io
from datetime import date
import pytest
from flask import url_for
from sqlalchemy import text as sqltext

from extensions import db
import models as M

def _login_admin(client, app):
    from models import Role, User
    with app.app_context():
        role = Role.query.filter_by(name='super_admin').first()
        if not role:
            role = Role(name='super_admin', description='full access')
        user = User.query.filter_by(username='pay_admin_full').first()
        if not user:
            user = User(username='pay_admin_full', email='pay_admin_full@test.local')
            user.set_password('x')
            user.role = role
        db.session.add_all([role, user]); db.session.commit()
    client.post(url_for('auth.login'), data={'username':'pay_admin_full','password':'x'})

def _mk_customer():
    n = (M.Customer.query.count() or 0) + 1
    c = M.Customer(
        name=f"John Doe {n}",
        phone=f"123{n:03d}",
        email=f"jd{n}@example.com",
        currency="ILS"
    )
    db.session.add(c); db.session.commit()
    return c

def _mk_sale(customer):
    from models import User
    seller = User.query.filter_by(username='pay_admin_full').first()
    assert seller is not None, "seller user must exist (call _login_admin first)"

    n = (M.Sale.query.count() or 0) + 1
    s = M.Sale(
        customer_id=customer.id,
        seller_id=seller.id,            # ✅ NOT NULL في الموديل
        sale_number=f"S-{100 + n}",
        sale_date=date(2025, 1, 2),
        currency="ILS",
        status=M.SaleStatus.CONFIRMED.value
    )
    db.session.add(s); db.session.commit()

    # 🔧 للاختبار فقط: ثبت إجمالي البيع 200 لاستيعاب دفعة 200
    db.session.execute(
        sqltext("UPDATE sales SET total_amount = :amt WHERE id = :id"),
        {"amt": 200.0, "id": s.id}
    )
    db.session.commit()
    db.session.refresh(s)
    return s

def _mk_expense():
    # أنشئ نوع مصروف صالح حتى لا نفشل بقيود FK/NOT NULL
    t = M.ExpenseType.query.first()
    if not t:
        t = M.ExpenseType(name="Misc", description="created by tests")
        db.session.add(t)
        db.session.flush()

    e = M.Expense(
        amount=50, description="Fuel", currency="ILS",
        type_id=t.id,              # مهم
        payment_method="cash",     # دفاعي (سكيمات قديمة)
    )
    db.session.add(e); db.session.commit()
    return e



@pytest.mark.usefixtures("app")
def test_create_payment_json_success_customer(client, app):
    _login_admin(client, app)
    c = _mk_customer()

    payload = {
        'entity_type': 'CUSTOMER',
        'customer_id': str(c.id),
        'payment_date': '2025-01-01',
        'total_amount': '100.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'IN',
        'splits-0-method': 'cash',
        'splits-0-amount': '100.00',
    }
    resp = client.post(url_for('payments.create_payment'),
                       data=payload,
                       headers={'Accept':'application/json'})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['status'] == 'success'
    p = M.Payment.query.order_by(M.Payment.id.desc()).first()
    assert p is not None and p.customer_id == c.id and float(p.total_amount) == 100.0
    assert p.splits and float(p.splits[0].amount) == 100.0

@pytest.mark.usefixtures("app")
def test_create_payment_split_sum_mismatch_gives_400(client, app):
    _login_admin(client, app)
    c = _mk_customer()
    payload = {
        'entity_type': 'CUSTOMER',
        'customer_id': str(c.id),
        'payment_date': '2025-01-01',
        'total_amount': '150.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'IN',
        'splits-0-method': 'cash',
        'splits-0-amount': '100.00',  # مجموع السبلِت لا يساوي الإجمالي
    }
    resp = client.post(url_for('payments.create_payment'),
                       data=payload,
                       headers={'Accept':'application/json'})
    assert resp.status_code == 400
    j = resp.get_json()
    assert j['status'] == 'error'

@pytest.mark.usefixtures("app")
def test_view_payment_json_and_delete_split(client, app):
    _login_admin(client, app)
    c = _mk_customer()
    # دفعة فيها split بنكي يتطلب مرجع
    payload = {
        'entity_type': 'CUSTOMER',
        'customer_id': str(c.id),
        'payment_date': '2025-01-01',
        'total_amount': '120.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'IN',
        'splits-0-method': 'cash',
        'splits-0-amount': '100.00',
        'splits-1-method': 'bank',
        'splits-1-amount': '20.00',
        'splits-1-bank_transfer_ref': 'REF123456',
    }
    resp = client.post(url_for('payments.create_payment'), data=payload, headers={'Accept':'application/json'})
    assert resp.status_code == 201
    pid = resp.get_json()['payment']['id']

    # عرض JSON
    resp2 = client.get(url_for('payments.view_payment', payment_id=pid), headers={'Accept':'application/json'})
    assert resp2.status_code == 200
    j = resp2.get_json()
    assert j['payment']['id'] == pid
    assert len(j['payment']['splits']) == 2

    # حذف split الثاني
    with app.app_context():
        split_rows = M.PaymentSplit.query.filter_by(payment_id=pid).order_by(M.PaymentSplit.id.asc()).all()
        assert len(split_rows) == 2
        split_id = split_rows[1].id

    resp3 = client.delete(url_for('payments.delete_split', split_id=split_id), headers={'Accept':'application/json'})
    assert resp3.status_code == 200 and resp3.get_json()['status'] == 'success'

    # تأكيد الحذف
    resp4 = client.get(url_for('payments.view_payment', payment_id=pid), headers={'Accept':'application/json'})
    assert len(resp4.get_json()['payment']['splits']) == 1

@pytest.mark.usefixtures("app")
def test_view_and_download_receipt_routes(client, app):
    _login_admin(client, app)
    c = _mk_customer()
    s = _mk_sale(c)

    # إنشاء الدفع عبر الإندبوينت (وليس موديل مباشر)
    payload = {
        'entity_type': 'SALE',
        'sale_id': str(s.id),
        'payment_date': '2025-01-03',
        'total_amount': '200.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'IN',
        'splits-0-method': 'cash',
        'splits-0-amount': '200.00',
    }
    resp = client.post(url_for('payments.create_payment'), data=payload, headers={'Accept':'application/json'})
    assert resp.status_code == 201
    pid = resp.get_json()['payment']['id']

    # JSON للإيصال + sale_info
    rj = client.get(url_for('payments.view_receipt', payment_id=pid), headers={'Accept':'application/json'})
    assert rj.status_code == 200
    rec = rj.get_json()['payment']
    assert rec['sale_info'] and rec['sale_info']['number'] == s.sale_number

    # تنزيل PDF
    pdf = client.get(url_for('payments.download_receipt', payment_id=pid))
    assert pdf.status_code == 200
    assert pdf.headers.get('Content-Type') == 'application/pdf'
    assert len(pdf.data) > 100

@pytest.mark.usefixtures("app")
def test_entity_fields_partial_and_expense_shortcut(client, app):
    _login_admin(client, app)
    c = _mk_customer()
    e = _mk_expense()

    # partials للكيانات
    for t, eid in (("customer", c.id), ("supplier", 0), ("partner", 0), ("preorder", 0)):
        resp = client.get(url_for('payments.entity_fields', type=t, entity_id=eid))
        assert resp.status_code == 200

    # GET تهيئة دفع مصروف
    r = client.get(url_for('payments.create_expense_payment', exp_id=e.id))
    assert r.status_code == 200

    # POST دفع مصروف: مجموع السبلت == المبلغ
    payload = {
        'entity_type': 'EXPENSE',
        'expense_id': str(e.id),
        'payment_date': '2025-01-05',
        'total_amount': '50.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'OUT',
        'splits-0-method': 'cash',
        'splits-0-amount': '50.00',
    }
    resp2 = client.post(url_for('payments.create_expense_payment', exp_id=e.id),
                        data=payload, headers={'Accept':'application/json'})
    assert resp2.status_code == 201
    pp = resp2.get_json()['payment']
    assert pp['direction'] in ("OUT", M.PaymentDirection.OUTGOING.value)
    assert pp['entity_type'] == "EXPENSE"

@pytest.mark.usefixtures("app")
def test_delete_payment_json(client, app):
    _login_admin(client, app)
    c = _mk_customer()
    payload = {
        'entity_type': 'CUSTOMER',
        'customer_id': str(c.id),
        'payment_date': '2025-01-06',
        'total_amount': '10.00',
        'currency': 'ILS',
        'status': 'COMPLETED',
        'direction': 'IN',
        'splits-0-method': 'cash',
        'splits-0-amount': '10.00',
    }
    resp = client.post(url_for('payments.create_payment'), data=payload, headers={'Accept':'application/json'})
    pid = resp.get_json()['payment']['id']

    delr = client.post(url_for('payments.delete_payment', payment_id=pid), headers={'Accept':'application/json'})
    assert delr.status_code == 200
    assert delr.get_json()['status'] == 'success'
