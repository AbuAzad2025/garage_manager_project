# setup_admin.py - Admin Setup Utility
# Location: /garage_manager/setup_admin.py
# Description: Initial admin user and permissions setup

from typing import List
from sqlalchemy.exc import SQLAlchemyError
from app import create_app
from extensions import db
from models import Permission, Role, User

SUPER_ADMIN_EMAIL = "rafideen.ahmadghannam@gmail.com"
SUPER_ADMIN_USERNAME = "azad"
SUPER_ADMIN_PASSWORD = "AZ123456"

ALL_PERMISSIONS = [
    "manage_users","manage_permissions","manage_roles","manage_customers",
    "manage_sales","manage_service","manage_reports","view_reports",
    "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
    "manage_payments","manage_expenses","backup_database","restore_database",
]
DANGEROUS_PERMS = {"restore_database"}
LEGACY_PERM = "backup_restore"

def _log(msg: str) -> None:
    print(f"[setup_admin] {msg}")

def _get_or_create_permission(name: str, description: str = "") -> Permission:
    q = (Permission.name == name,)
    try:
        q = ((Permission.name == name) | (Permission.code == name),)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = Permission.query.filter(*q).first()
    if not p:
        kwargs = {"name": name, "description": description}
        try:
            kwargs["code"] = name  # type: ignore[attr-defined]
        except Exception:
            pass
        p = Permission(**kwargs)
        db.session.add(p)
    return p

def seed_permissions_if_empty() -> int:
    if Permission.query.count() > 0:
        return 0
    for name in ALL_PERMISSIONS:
        _get_or_create_permission(name)
    db.session.commit()
    return len(ALL_PERMISSIONS)

def migrate_legacy_backup_restore() -> None:
    legacy = Permission.query.filter(
        (Permission.name == LEGACY_PERM)
        if not hasattr(Permission, "code")
        else ((Permission.name == LEGACY_PERM) | (Permission.code == LEGACY_PERM))
    ).first()
    if not legacy:
        return
    p_backup = _get_or_create_permission("backup_database")
    p_restore = _get_or_create_permission("restore_database")
    db.session.flush()
    for r in list(getattr(legacy, "roles", [])):
        if p_backup not in r.permissions:
            r.permissions.append(p_backup)
        if p_restore not in r.permissions:
            r.permissions.append(p_restore)
        if legacy in r.permissions:
            r.permissions.remove(legacy)
    try:
        db.session.delete(legacy)
    except Exception:
        pass
    db.session.commit()

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
    if not role:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()
    _sync_role_permissions(role, perm_names)
    db.session.commit()
    return role

def _attach_role(user: User, role: Role) -> None:
    if hasattr(user, "roles"):
        if role not in user.roles:
            user.roles.append(role)
    elif hasattr(user, "role"):
        user.role = role
    else:
        try:
            user.role = role
        except Exception:
            pass

def ensure_super_admin_user(email: str, username: str, password: str, role: Role) -> None:
    user = User.query.filter((User.email == email) | (User.username == username)).first()
    if not user:
        user = User(username=username, email=email, is_active=True)
        try:
            user.set_password(password)
        except Exception:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(password, method="scrypt")
        db.session.add(user)
        db.session.flush()
    else:
        user.is_active = True
    _attach_role(user, role)
    db.session.commit()

def main() -> None:
    app = create_app()
    with app.app_context():
        try:
            seed_permissions_if_empty()
            existing = {p.name for p in Permission.query.all()}
            missing = [n for n in ALL_PERMISSIONS if n not in existing]
            if missing:
                for n in missing:
                    _get_or_create_permission(n)
                db.session.commit()
            migrate_legacy_backup_restore()
            all_perm_names = [p.name for p in Permission.query.all()]
            super_role = ensure_or_update_role(
                name="super_admin",
                description="Super Administrator with ALL permissions",
                perm_names=all_perm_names,
            )
            admin_perm_names = [n for n in all_perm_names if n not in DANGEROUS_PERMS]
            ensure_or_update_role(
                name="admin",
                description="Administrator (no DB restore permission)",
                perm_names=admin_perm_names,
            )
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
