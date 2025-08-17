import pytest
import uuid
from flask import url_for
from models import Role, Permission, db

@pytest.mark.usefixtures("client")
def test_roles_flow_full_coverage(client, app):
    with app.app_context():
        # أسماء ديناميكية لتجنب التكرار
        base_name = f"Role_{uuid.uuid4().hex[:6]}"
        mod_name = f"Modified_{uuid.uuid4().hex[:6]}"
        dup_name = f"Dup_{uuid.uuid4().hex[:6]}"

        # 1. زيارة صفحة الأدوار
        resp = client.get(url_for("roles.list_roles"))
        assert resp.status_code == 200
        assert "إدارة الأدوار" in resp.get_data(as_text=True)

        # 2. إنشاء دور جديد بدون صلاحيات
        resp = client.post(
            url_for("roles.create_role"),
            data={
                "name": base_name,
                "description": "Test description",
                "permissions": []
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "تم إنشاء الدور بنجاح" in resp.get_data(as_text=True) or "تم إنشاء الدور بنجاح." in resp.get_data(as_text=True)

        role = Role.query.filter_by(name=base_name).first()
        assert role is not None
        assert len(role.permissions) == 0

        # 3. محاولة إنشاء نفس الدور (تكرار)
        resp = client.post(
            url_for("roles.create_role"),
            data={
                "name": base_name,
                "description": "Duplicate try",
                "permissions": []
            },
            follow_redirects=True,
        )
        assert "اسم الدور مستخدم بالفعل" in resp.get_data(as_text=True)

        # 4. تعديل الدور وإضافة صلاحية واحدة
        perm = Permission.query.filter_by(name="manage_roles").first()
        assert perm is not None

        resp = client.post(
            url_for("roles.edit_role", role_id=role.id),
            data={
                "name": mod_name,
                "description": "Updated description",
                "permissions": [str(perm.id)]
            },
            follow_redirects=True,
        )
        assert "تم تعديل الدور بنجاح" in resp.get_data(as_text=True) or "تم تعديل الدور بنجاح." in resp.get_data(as_text=True)

        updated = db.session.get(Role, role.id)
        assert updated.name == mod_name
        assert perm in updated.permissions

        # 5. تعديل إلى اسم موجود مسبقًا
        dup = Role(name=dup_name)
        db.session.add(dup)
        db.session.commit()

        resp = client.post(
            url_for("roles.edit_role", role_id=updated.id),
            data={
                "name": dup_name,
                "description": "Trying to duplicate",
                "permissions": []
            },
            follow_redirects=True,
        )
        assert "اسم الدور مستخدم بالفعل" in resp.get_data(as_text=True)

        # 6. حذف الدور غير المحمي
        resp = client.post(
            url_for("roles.delete_role", role_id=updated.id),
            follow_redirects=True
        )
        assert "تم حذف الدور" in resp.get_data(as_text=True) or "تم حذف الدور." in resp.get_data(as_text=True)
        assert db.session.get(Role, updated.id) is None

        # 7. محاولة حذف دور محمي
        protected = Role.query.filter(Role.name.in_(["admin", "super_admin"])).first()
        if not protected:
            protected = Role(name="admin")
            db.session.add(protected)
            db.session.commit()

        resp = client.post(
            url_for("roles.delete_role", role_id=protected.id),
            follow_redirects=True
        )
        assert "لا يمكن حذف هذا الدور" in resp.get_data(as_text=True) or "لا يمكن حذف هذا الدور." in resp.get_data(as_text=True)
