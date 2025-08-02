#!/usr/bin/env python3
# File: setup_admin.py

from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from extensions import db, mail
from models import Permission, Role, User

# بيانات السوبر أدمن الثابتة
SUPER_ADMIN_EMAIL = "rafideen.ahmadghannam@gmail.com"
SUPER_ADMIN_USERNAME = "azad"
SUPER_ADMIN_PASSWORD = "AZ123456"

def ensure_role(name: str, description: str, perm_names: list[str]):
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()
        # جلب الصلاحيات المطلوبة بحسب الأسماء المعطاة
        perms = Permission.query.filter(Permission.name.in_(perm_names)).all()
        role.permissions = perms
        db.session.commit()
        print(f"Created role '{name}' with {len(perms)} permissions.")
    else:
        print(f"Role '{name}' already exists.")
    return role

def main():
    """
    Script to create 'super_admin' and 'admin' roles with appropriate permissions,
    then creates a super-admin user with static credentials.
    """
    app = create_app()
    with app.app_context():
        # جلب كل أسماء الصلاحيات المتاحة في القاعدة:
        all_perm_names = [p.name for p in Permission.query.all()]

        # 1) أنشئ دور super_admin بجميع الصلاحيات:
        super_perms = all_perm_names.copy()
        super_role = ensure_role(
            name='super_admin',
            description='Super Administrator with ALL permissions',
            perm_names=super_perms
        )

        # 2) أنشئ دور admin بكل الصلاحيات عدا استعادة DB:
        admin_perms = [n for n in all_perm_names if n != 'restore_database']
        admin_role = ensure_role(
            name='admin',
            description='Administrator without restore_database permission',
            perm_names=admin_perms
        )

        # 3) تحقق من وجود السوبر-أدمن بالفعل
        email = SUPER_ADMIN_EMAIL
        username = SUPER_ADMIN_USERNAME
        pwd = SUPER_ADMIN_PASSWORD

        if User.query.filter_by(email=email).first():
            print(f"User with email '{email}' already exists. Exiting.")
            return

        if User.query.filter_by(username=username).first():
            print(f"User with username '{username}' already exists. Exiting.")
            return

        # 4) إنشاء مستخدم super_admin
        user = User(username=username, email=email, role=super_role)
        user.set_password(pwd)
        db.session.add(user)
        db.session.commit()
        print(f"Super-admin user '{username}' ({email}) created successfully.")

if __name__ == '__main__':
    main()
