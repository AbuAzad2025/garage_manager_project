#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List
from sqlalchemy.exc import SQLAlchemyError
from app import create_app
from extensions import db
from models import Permission, Role, User

# ===== super admin creds (بدّلها بالإنتاج) =====
SUPER_ADMIN_EMAIL = "rafideen.ahmadghannam@gmail.com"
SUPER_ADMIN_USERNAME = "azad"
SUPER_ADMIN_PASSWORD = "AZ123456"

# ===== الأذونات الرسمية =====
ALL_PERMISSIONS = [
    # إدارة أساسية
    "manage_users",
    "manage_permissions",
    "manage_roles",
    "manage_customers",

    # مبيعات/خدمة/تقارير
    "manage_sales",
    "manage_service",
    "manage_reports",
    "view_reports",        # مضافة لدعم شروط القوالب في الداشبورد

    # موردين/شحن/مخازن
    "manage_vendors",
    "manage_shipments",
    "manage_warehouses",
    "view_warehouses",     # مضافة لدعم شرط النافبار
    "manage_exchange",     # مضافة لدعم كرت "التبادل" في الداشبورد

    # دفعات/مصاريف
    "manage_payments",
    "manage_expenses",

    # نسخ احتياطي/استعادة (جديدة بدل backup_restore)
    "backup_database",
    "restore_database",
]

# إذونات حساسة
DANGEROUS_PERMS = {"restore_database"}  # الاستعادة فقط

LEGACY_PERM = "backup_restore"  # سنحوّلها للجديدة إن وُجدت

def _log(msg: str) -> None:
    print(f"[setup_admin] {msg}")

def _get_or_create_permission(name: str, description: str = "") -> Permission:
    p = Permission.query.filter((Permission.name == name) | (Permission.code == name)).first()
    if not p:
        p = Permission(name=name, code=name, description=description)
        db.session.add(p)
    return p

def seed_permissions_if_empty() -> int:
    count = Permission.query.count()
    if count > 0:
        _log(f"Permissions already present ({count}).")
        return 0
    for name in ALL_PERMISSIONS:
        _get_or_create_permission(name)
    db.session.commit()
    _log(f"Seeded {len(ALL_PERMISSIONS)} permissions.")
    return len(ALL_PERMISSIONS)

def migrate_legacy_backup_restore() -> None:
    """حوّل إذن backup_restore القديم إلى الإذنين الجديدين."""
    legacy = Permission.query.filter(
        (Permission.name == LEGACY_PERM) | (Permission.code == LEGACY_PERM)
    ).first()
    if not legacy:
        return
    # تأكد من وجود الجديدين
    p_backup = _get_or_create_permission("backup_database")
    p_restore = _get_or_create_permission("restore_database")
    db.session.flush()

    # أي دور يملك legacy، أعطه الاثنين
    roles = list(legacy.roles)  # backref
    for r in roles:
        if p_backup not in r.permissions:
            r.permissions.append(p_backup)
        if p_restore not in r.permissions:
            r.permissions.append(p_restore)
        # ويمكنك إزالة legacy من الدور:
        if legacy in r.permissions:
            r.permissions.remove(legacy)

    # إزالة الإذن القديم نهائيًا (اختياري)
    try:
        db.session.delete(legacy)
    except Exception:
        pass
    db.session.commit()
    _log("Migrated legacy 'backup_restore' to 'backup_database' + 'restore_database' and removed it.")

def _sync_role_permissions(role: Role, desired_names: List[str]) -> bool:
    existing = {p.name for p in (role.permissions or [])}
    desired = set(desired_names)
    if existing == desired:
        return False
    perms = Permission.query.filter(Permission.name.in_(desired)).all()
    role.permissions = perms
    return True

def ensure_or_update_role(name: str, description: str, perm_names: List[str]) -> Role:
    role = Role.query.filter_by(name=name).first()
    created = False
    if not role:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()
        created = True
    changed = _sync_role_permissions(role, perm_names)
    db.session.commit()
    if created and not perm_names:
        _log(f"Role '{name}' created with 0 permissions.")
    elif created:
        _log(f"Role '{name}' created with {len(perm_names)} permissions.")
    elif changed:
        _log(f"Role '{name}' permissions synchronized to {len(perm_names)}.")
    else:
        _log(f"Role '{name}' already up-to-date.")
    return role

def ensure_super_admin_user(email: str, username: str, password: str, role: Role) -> None:
    user = User.query.filter_by(email=email).first()
    if user:
        if user.role_id != role.id:
            user.role = role
            db.session.commit()
            _log(f"User '{user.username}' exists — role set to '{role.name}'.")
        else:
            _log(f"User '{user.username}' already exists with role '{role.name}'.")
        return
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _log(f"Super-admin user '{username}' created.")

def main() -> None:
    app = create_app()
    with app.app_context():
        try:
            # 1) أنشئ كل الأذونات (لو أول مرة)
            seeded = seed_permissions_if_empty()
            # 2) تأكد من إضافة أي أذونات ناقصة لاحقًا
            existing = {p.name for p in Permission.query.all()}
            missing = [n for n in ALL_PERMISSIONS if n not in existing]
            if missing:
                for n in missing:
                    _get_or_create_permission(n)
                db.session.commit()
                _log(f"Added missing permissions: {', '.join(missing)}")

            # 3) هجرة الإذن القديم backup_restore (إن وُجد)
            migrate_legacy_backup_restore()

            # 4) أعد تحميل كل الأذونات بعد الهجرة
            all_perm_names = [p.name for p in Permission.query.all()]

            # 5) super_admin = كل شيء
            super_role = ensure_or_update_role(
                name="super_admin",
                description="Super Administrator with ALL permissions",
                perm_names=all_perm_names,
            )

            # 6) admin = كل شيء ما عدا الاستعادة الحسّاسة
            admin_perm_names = [n for n in all_perm_names if n not in DANGEROUS_PERMS]
            ensure_or_update_role(
                name="admin",
                description="Administrator (no DB restore permission)",
                perm_names=admin_perm_names,
            )

            # 7) تأكيد إنشاء المستخدم السوبر
            ensure_super_admin_user(
                email=SUPER_ADMIN_EMAIL,
                username=SUPER_ADMIN_USERNAME,
                password=SUPER_ADMIN_PASSWORD,
                role=super_role,
            )
            _log("Done.")
        except SQLAlchemyError as e:
            db.session.rollback()
            _log(f"DB ERROR: {e}")
            raise
        except Exception as e:
            db.session.rollback()
            _log(f"UNEXPECTED ERROR: {e}")
            raise

if __name__ == "__main__":
    main()
