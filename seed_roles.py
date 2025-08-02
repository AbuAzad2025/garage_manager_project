#!/usr/bin/env python
import sys
from garage_manager.extensions import db, mail
from garage_manager.models import Role, Permission

# الأدوار الافتراضية والصلاحيات المرتبطة بها
DEFAULT_ROLES = {
    'developer': ['*'],
    'manager':   ['manage_*'],
    'mechanic':  ['manage_service'],
    'customer':  ['view_own_records'],
    'anonymous': []
}

def seed_roles():
    for role_name, perms in DEFAULT_ROLES.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name, description=f"Default role: {role_name}")
            db.session.add(role)
            print(f"أنشأ دور: {role_name}")
        # ربط الصلاحيات
        if '*' in perms:
            role.permissions = Permission.query.all()
        else:
            for perm_pattern in perms:
                if perm_pattern.endswith('_*'):
                    prefix = perm_pattern[:-1]
                    matched = Permission.query.filter(Permission.name.like(f"{prefix}%")).all()
                    for p in matched:
                        if p not in role.permissions:
                            role.permissions.append(p)
                else:
                    perm = Permission.query.filter_by(name=perm_pattern).first()
                    if perm and perm not in role.permissions:
                        role.permissions.append(perm)
        db.session.commit()

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        seed_roles()
    print("✅ تم تهيئة الأدوار الافتراضية بنجاح.")
