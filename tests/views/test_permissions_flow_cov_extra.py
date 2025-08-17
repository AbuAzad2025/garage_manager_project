# -*- coding: utf-8 -*-
import uuid
import pytest
from flask import url_for
from extensions import db
from models import User, Role, Permission


def _login_admin_with_manage_permissions(client, app):
    """ينشئ/يثبّت إذن manage_permissions ودور admin ومستخدم أدمن، ثم يسجّله دخول."""
    with app.app_context():
        # get-or-create الإذن
        perm = db.session.scalar(db.select(Permission).filter_by(name="manage_permissions"))
        if not perm:
            perm = Permission(name="manage_permissions", description="can manage permissions")
            db.session.add(perm)
            db.session.flush()

        # get-or-create الدور
        role = db.session.scalar(db.select(Role).filter_by(name="admin"))
        if not role:
            role = Role(name="admin", description="admin")
            db.session.add(role)
            db.session.flush()

        # اربط الإذن بالدور إن لم يكن موجودًا
        if perm not in role.permissions:
            role.permissions.append(perm)

        # أنشئ مستخدمًا فريدًا لتفادي UNIQUE
        uname = f"admin_perm_{uuid.uuid4().hex[:6]}"
        user = User(username=uname, email=f"{uname}@example.com")
        user.set_password("P@ssw0rd")
        db.session.add(user)
        db.session.flush()

        # اربطه بالدور واعمَل commit
        user.role = role
        db.session.commit()
        username = user.username

    # نظّف أي جلسة سابقة ثم سجّل دخول الأدمن
    client.post(url_for("auth.logout"), follow_redirects=True)
    client.post(
        url_for("auth.login"),
        data={"username": username, "password": "P@ssw0rd"},
        follow_redirects=True,
    )
    return username


@pytest.mark.usefixtures("app", "client")
def test_permissions_list_page_ok(client, app):
    # نضمن إننا داخلين بأدمن مخوّل (يمنع 403 الفجائي لو تغيّر الحارس مستقبلاً)
    _login_admin_with_manage_permissions(client, app)
    r = client.get(url_for("permissions.list"))
    assert r.status_code == 200


@pytest.mark.usefixtures("app", "client")
def test_permissions_create_and_dedup(client, app):
    _login_admin_with_manage_permissions(client, app)
    name = "manage_discounts"

    # الإنشاء الأول
    r1 = client.post(url_for("permissions.create"), data={"name": name}, follow_redirects=True)
    assert r1.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(Permission).filter_by(name=name)) is not None

    # إعادة المحاولة للتأكد من عدم التكرار (dedup)
    r2 = client.post(url_for("permissions.create"), data={"name": name}, follow_redirects=True)
    assert r2.status_code == 200
    with app.app_context():
        assert db.session.query(Permission).filter_by(name=name).count() == 1
