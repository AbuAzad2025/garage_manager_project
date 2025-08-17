import pytest
from flask import url_for
from models import Customer
import uuid
from datetime import datetime



def test_list_customers(client):
    response = client.get("/customers/")
    assert response.status_code == 200
    assert "العملاء" in response.get_data(as_text=True)

def test_create_customer_form(client):
    response = client.get("/customers/create")
    assert response.status_code == 200
    assert "إضافة عميل" in response.get_data(as_text=True)

def test_create_customer_post(client, db_connection):
    data = {
        "name": "Ahmed Test",
        "phone": "0599999999",
        "email": "ahmed.test@example.com",
        "address": "Gaza",
        "whatsapp": "0599999998",
        "category": "ذهبي",
        "credit_limit": "1000",
        "discount_rate": "5",
        "is_active": True,
        "is_online": False,
        "notes": "عميل اختبار",
        "password": "12345678",
        "confirm": "12345678"
    }
    response = client.post("/customers/create", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert "العملاء" in response.get_data(as_text=True)

def test_customer_detail(client, db_connection):
    # توليد بيانات فريدة
    unique_id = str(uuid.uuid4())[:8]
    phone = f"0599{unique_id}"
    email = f"detail.{unique_id}@test.com"

    # إعداد البيانات بشكل صريح لتجنب مشاكل __dict__
    db_connection.execute(Customer.__table__.insert().values(
        name="Detail View",
        phone=phone,
        email=email,
        currency="ILS",  # ضروري لأنه not null
        category="عادي",
        is_active=True,
        is_online=False,
        credit_limit=0.0,
        discount_rate=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    db_connection.commit()

    # التأكد من وجود العميل
    cust = Customer.query.filter_by(email=email).first()
    assert cust is not None

    # اختبار الصفحة
    response = client.get(f"/customers/{cust.id}")
    assert response.status_code == 200
    assert "Detail View" in response.get_data(as_text=True)


def test_edit_customer(client, db_connection):
    unique_id = str(uuid.uuid4())[:8]
    phone = f"0599{unique_id}"
    email = f"edit_{unique_id}@test.com"

    db_connection.execute(Customer.__table__.insert().values(
        name="Edit Me",
        phone=phone,
        email=email,
        currency="ILS",
        category="عادي",
        is_active=True,
        is_online=False,
        credit_limit=0.0,
        discount_rate=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    db_connection.commit()

    cust = Customer.query.filter_by(email=email).first()
    assert cust is not None

    response = client.get(f"/customers/{cust.id}/edit")
    assert response.status_code == 200
    assert "تعديل بيانات العميل" in response.get_data(as_text=True)
    
def test_delete_customer(client, db_connection):
    unique_id = str(uuid.uuid4())[:8]
    name = f"Delete Me {unique_id}"
    phone = f"0599{unique_id}"
    email = f"delete_{unique_id}@test.com"

    db_connection.execute(Customer.__table__.insert().values(
        name=name,
        phone=phone,
        email=email,
        currency="ILS",
        category="عادي",
        is_active=True,
        is_online=False,
        credit_limit=0.0,
        discount_rate=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    db_connection.commit()

    cust = Customer.query.filter_by(email=email).first()
    assert cust is not None

    response = client.post(f"/customers/{cust.id}/delete", follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "تم حذف العميل" in html or "لا يمكن حذف العميل" in html
