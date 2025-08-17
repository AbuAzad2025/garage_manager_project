import pytest
import uuid
from flask import url_for
from models import Role, Permission, db


def _login_admin(client, app):
    from models import User, Role, Permission
    from extensions import db
    from flask import url_for

    with app.app_context():
        print("🚀 إعداد المستخدم والدور والصلاحية...")

        perm = Permission.query.filter_by(name="manage_roles").first()
        if not perm:
            print("🛠️ إنشاء الصلاحية 'manage_roles'")
            perm = Permission(name="manage_roles", code="manage_roles", description="صلاحية إدارة الأدوار")
            db.session.add(perm)
            db.session.commit()
        else:
            print("✅ الصلاحية موجودة")

        role = Role.query.filter_by(name="super_admin").first()
        if not role:
            print("🛠️ إنشاء الدور 'super_admin'")
            role = Role(name="super_admin", description="صلاحيات كاملة")
            db.session.add(role)
            db.session.commit()
        else:
            print("✅ الدور موجود")

        if perm not in role.permissions:
            print("🔗 ربط الصلاحية بالدور")
            role.permissions.append(perm)
            db.session.add(role)
            db.session.commit()
        else:
            print("✅ الصلاحية مربوطة بالفعل بالدور")

        user = User.query.filter_by(username="test_admin").first()
        if not user:
            print("🛠️ إنشاء المستخدم 'test_admin'")
            user = User(username="test_admin", email="test_admin@test.local")
            user.set_password("x")
            user.role = role
            db.session.add(user)
            db.session.commit()
        else:
            print("✅ المستخدم موجود")

    print("🔐 محاولة تسجيل الدخول...")
    resp = client.post(
        url_for("auth.login"),
        data={"username": "test_admin", "password": "x"},
        follow_redirects=True
    )

    print("📥 رمز الاستجابة بعد تسجيل الدخول:", resp.status_code)
    print("📍 موقع الرد (redirect):", resp.location if resp.status_code == 302 else "لا يوجد")
    print("📃 بداية الرد:", resp.get_data(as_text=True)[:300])

    assert resp.status_code == 200
    assert "تسجيل الدخول" not in resp.get_data(as_text=True)
    print("✅ تم تسجيل الدخول بنجاح")


@pytest.mark.usefixtures("client")
def test_roles_flow_full_coverage(client, app):
    _login_admin(client, app)

    base_name = f"Role_{uuid.uuid4().hex[:6]}"
    mod_name = f"Modified_{uuid.uuid4().hex[:6]}"
    dup_name = f"Dup_{uuid.uuid4().hex[:6]}"

    # GET /roles/
    resp = client.get(url_for("roles.list_roles"))
    if resp.status_code == 302:
        print("🔁 Redirect from /roles/:", resp.location)
        print("🔁 Body preview:", resp.get_data(as_text=True)[:300])
    assert resp.status_code == 200
    assert "إدارة الأدوار" in resp.get_data(as_text=True)

    # GET /roles/create
    resp = client.get(url_for("roles.create_role"))
    if resp.status_code == 302:
        print("🔁 Redirect from /roles/create:", resp.location)
    assert resp.status_code == 200
    assert "اسم الدور" in resp.get_data(as_text=True)

    # POST /roles/create
    resp = client.post(
        url_for("roles.create_role"),
        data={"name": base_name, "description": "وصف تجريبي", "permissions": []},
        follow_redirects=True,
    )
    if resp.status_code == 302:
        print("🔁 Redirect after create:", resp.location)
    assert resp.status_code == 200
    assert "تم إنشاء الدور بنجاح" in resp.get_data(as_text=True)

    with app.app_context():
        role = Role.query.filter_by(name=base_name).first()
        assert role is not None
        assert len(role.permissions) == 0
        role_id = role.id

    # POST /roles/create مكرر
    resp = client.post(
        url_for("roles.create_role"),
        data={"name": base_name, "description": "مكرر", "permissions": []},
        follow_redirects=True,
    )
    assert "اسم الدور مستخدم بالفعل" in resp.get_data(as_text=True)

    # GET /roles/<id>/edit
    resp = client.get(url_for("roles.edit_role", role_id=role_id))
    if resp.status_code == 302:
        print("🔁 Redirect from /roles/<id>/edit:", resp.location)
    assert resp.status_code == 200
    assert "اسم الدور" in resp.get_data(as_text=True)

    # POST /roles/<id>/edit مع صلاحية واحدة
    with app.app_context():
        perm = Permission.query.filter_by(name="manage_roles").first()
        assert perm is not None
        perm_id = perm.id

    resp = client.post(
        url_for("roles.edit_role", role_id=role_id),
        data={
            "name": mod_name,
            "description": "تعديل",
            "permissions": [str(perm_id)],
        },
        follow_redirects=True,
    )
    assert "تم تعديل الدور بنجاح" in resp.get_data(as_text=True)

    with app.app_context():
        updated = db.session.get(Role, role_id)
        assert updated.name == mod_name
        perm_obj = db.session.get(Permission, perm_id)
        assert perm_obj in updated.permissions

        # إنشاء دور باسم مكرر لاختبار التعديل إلى اسم موجود
        dup = Role(name=dup_name)
        db.session.add(dup)
        db.session.commit()
        dup_id = dup.id
        print("🆕 تم إنشاء دور للاختبار المكرر:", dup_id, dup_name)

    resp = client.post(
        url_for("roles.edit_role", role_id=role_id),
        data={"name": dup_name, "description": "مكرر", "permissions": []},
        follow_redirects=True,
    )
    assert "اسم الدور مستخدم بالفعل" in resp.get_data(as_text=True)

    # حذف الدور غير المحمي
    resp = client.post(
        url_for("roles.delete_role", role_id=role_id),
        follow_redirects=True,
    )
    if resp.status_code == 302:
        print("🔁 Redirect after delete:", resp.location)
    assert "تم حذف الدور" in resp.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Role, role_id) is None

        # إنشاء دور محمي ومحاولة حذفه
        protected = Role.query.filter(Role.name.in_(["admin", "super_admin"])).first()
        if not protected:
            protected = Role(name="admin")
            db.session.add(protected)
            db.session.commit()
        protected_id = protected.id
        print("🛡️ دور محمي للاختبار:", protected_id, protected.name)

    resp = client.post(
        url_for("roles.delete_role", role_id=protected_id),
        follow_redirects=True,
    )
    assert "لا يمكن حذف هذا الدور" in resp.get_data(as_text=True)
