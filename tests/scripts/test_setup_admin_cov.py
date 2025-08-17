# -*- coding: utf-8 -*-
import uuid
import pytest

from extensions import db
from models import Permission, Role, User

# نستورد الدوال والثوابت من السكربت نفسه
import setup_admin as SA


def _names(q):
    """ارجع مجموعة أسماء الصلاحيات لدور معيّن."""
    return {p.name for p in q.permissions or []}


@pytest.mark.usefixtures("db_connection")  # يعتمد على conftest تبعك
class TestSetupAdmin:

    def test_seed_permissions_if_empty_seeds_exactly_script_list(self, app):
        """لو جدول Permission فاضي → يزرع ALL_PERMISSIONS ويعيد العدد بدقّة."""
        with app.app_context():
            # امسح ربط الأدوار أولاً لتفادي قيود FK
            for r in Role.query.all():
                r.permissions = []
            db.session.flush()

            # امسح الصلاحيات بالكامل
            Permission.query.delete()
            db.session.commit()
            assert Permission.query.count() == 0

            seeded = SA.seed_permissions_if_empty()
            assert seeded == len(SA.ALL_PERMISSIONS)

            # تَحقّق أنّ الأسماء نفسها بالضبط
            got = {p.name for p in Permission.query.all()}
            assert got == set(SA.ALL_PERMISSIONS)

            # نداء ثانٍ لا يزرع شيئًا (idempotent)
            seeded_again = SA.seed_permissions_if_empty()
            assert seeded_again == 0

    def test_ensure_or_update_role_creates_and_syncs_and_idempotent(self, app):
        """إنشاء دور بصلاحيات محددة، ثم مزامنته لقائمة أخرى، ثم التأكد من idempotency."""
        with app.app_context():
            # تأكد الصلاحيات موجودة
            if Permission.query.count() == 0:
                SA.seed_permissions_if_empty()

            # قائمة آمنة (بدون صلاحيات خطرة)
            all_perm_names = [p.name for p in Permission.query.all()]
            desired_initial = [n for n in all_perm_names if n not in SA.DANGEROUS_PERMS][:5]  # أي 5 صلاحيات

            role = SA.ensure_or_update_role(
                name="admin_test",
                description="Admin for tests",
                perm_names=desired_initial,
            )
            db.session.refresh(role)
            assert _names(role) == set(desired_initial)

            # غيّر القائمة → لازم تتزامن
            desired_changed = [n for n in all_perm_names if n not in SA.DANGEROUS_PERMS][:7]
            role2 = SA.ensure_or_update_role(
                name="admin_test",
                description="Admin for tests",
                perm_names=desired_changed,
            )
            db.session.refresh(role2)
            assert role2.id == role.id
            assert _names(role2) == set(desired_changed)

            # نداء ثالث بنفس القائمة → بدون تغيير
            before = sorted(p.id for p in role2.permissions)
            role3 = SA.ensure_or_update_role("admin_test", "Admin for tests", desired_changed)
            after = sorted(p.id for p in role3.permissions)
            assert before == after

    def test_ensure_super_admin_user_create_and_then_update_role(self, app):
        """عند عدم وجود المستخدم → يُنشأ. وإذا موجود بدور مختلف → يُحدّث للدور الممرّر."""
        with app.app_context():
            # تأكد الصلاحيات
            if Permission.query.count() == 0:
                SA.seed_permissions_if_empty()

            # أنشئ دورين
            super_role = SA.ensure_or_update_role(
                name="super_admin_test",
                description="ALL perms",
                perm_names=[p.name for p in Permission.query.all()],
            )
            limited = SA.ensure_or_update_role(
                name="limited_admin_test",
                description="limited",
                perm_names=[p.name for p in Permission.query.limit(3).all()],
            )

            # بيانات مستخدم اختبارية (ما نستخدم الثوابت من السكربت)
            email = f"sa_{uuid.uuid4().hex[:8]}@test.local"
            uname = f"user_{uuid.uuid4().hex[:8]}"
            pwd = "pass12345"

            # إنشاء أول مرة
            SA.ensure_super_admin_user(email=email, username=uname, password=pwd, role=limited)
            u = User.query.filter_by(email=email).first()
            assert u is not None
            assert u.role_id == limited.id

            # تحديث الدور إلى super
            SA.ensure_super_admin_user(email=email, username=uname, password=pwd, role=super_role)
            u2 = User.query.filter_by(email=email).first()
            assert u2 is not None
            assert u2.role_id == super_role.id

    def test_roles_permissions_consistent_after_main_steps_without_running_main(self, app):
        """
        نغطي التسلسل المنطقي للـmain بدون إنشاء تطبيق جديد:
        - التأكد من وجود كل الصلاحيات المطلوبة
        - super_admin يملك الكل
        - admin بدون الصلاحيات الخطرة
        """
        with app.app_context():
            SA.seed_permissions_if_empty()
            all_perm_names = [p.name for p in Permission.query.all()]

            super_role = SA.ensure_or_update_role(
                name="super_admin",
                description="Super Administrator with ALL permissions",
                perm_names=all_perm_names,
            )
            admin_perm_names = [n for n in all_perm_names if n not in SA.DANGEROUS_PERMS]
            admin_role = SA.ensure_or_update_role(
                name="admin",
                description="Administrator without DB restore permissions",
                perm_names=admin_perm_names,
            )

            assert _names(super_role) == set(all_perm_names)
            assert set(SA.DANGEROUS_PERMS).issubset(_names(super_role))
            assert set(SA.DANGEROUS_PERMS).isdisjoint(_names(admin_role))
