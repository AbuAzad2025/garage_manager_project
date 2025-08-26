from __future__ import annotations
import os, re, click
from flask.cli import with_appcontext
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models import Role, Permission, User
from utils import clear_role_permission_cache, clear_users_cache_by_role
from werkzeug.security import generate_password_hash

RESERVED_CODES = frozenset({
    "backup_database","restore_database","manage_permissions","manage_roles","manage_users",
    "manage_customers","manage_sales","manage_service","manage_reports","view_reports",
    "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
    "manage_payments","manage_expenses","view_inventory","manage_inventory","warehouse_transfer",
    "view_parts","view_preorders","add_preorder","edit_preorder","delete_preorder",
    "add_customer","add_supplier","add_partner","place_online_order",
    "view_shop","browse_products","manage_shop"
})

PERM_ALIASES = {
    "backup_database": "نسخ احتياطي",
    "restore_database": "استعادة نسخة",
    "manage_permissions": "إدارة الصلاحيات",
    "manage_roles": "إدارة الأدوار",
    "manage_users": "إدارة المستخدمين",
    "manage_customers": "إدارة العملاء",
    "manage_sales": "إدارة المبيعات",
    "manage_service": "إدارة الصيانة",
    "manage_reports": "إدارة التقارير",
    "view_reports": "عرض التقارير",
    "manage_vendors": "إدارة الموردين",
    "manage_shipments": "إدارة الشحن",
    "manage_warehouses": "إدارة المستودعات",
    "view_warehouses": "عرض المستودعات",
    "manage_exchange": "إدارة التحويلات",
    "manage_payments": "إدارة المدفوعات",
    "manage_expenses": "إدارة المصاريف",
    "view_inventory": "عرض الجرد",
    "manage_inventory": "إدارة الجرد",
    "warehouse_transfer": "تحويل مخزني",
    "view_parts": "عرض القطع",
    "view_preorders": "عرض الطلبات المسبقة",
    "add_preorder": "إضافة طلب مسبق",
    "edit_preorder": "تعديل طلب مسبق",
    "delete_preorder": "حذف طلب مسبق",
    "add_customer": "إضافة عميل",
    "add_supplier": "إضافة مورد",
    "add_partner": "إضافة شريك",
    "place_online_order": "طلب أونلاين",
    "view_shop": "عرض المتجر",
    "browse_products": "تصفح المنتجات",
    "manage_shop": "إدارة المتجر"
}

ROLE_PERMISSIONS = {
    "admin": {
        "backup_database","manage_permissions","manage_roles","manage_users",
        "manage_customers","manage_service","manage_reports","view_reports",
        "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
        "manage_payments","manage_expenses","view_inventory","warehouse_transfer","view_parts",
        "add_customer","add_supplier","add_partner"
    },
    "staff": {
        "manage_customers","manage_service",
        "view_parts","view_warehouses","view_inventory"
    },
    "registered_customer": {
        "place_online_order","view_preorders","view_parts","view_shop","browse_products"
    }
}

SUPER_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "azad")
SUPER_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "rafideen.ahmadghannam@gmail.com").strip().lower()
SUPER_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "AZ123456")

def _normalize_code(s: str | None) -> str | None:
    if not s: return None
    s = s.strip().lower()
    s = re.sub(r"[\s\-]+","_",s)
    s = re.sub(r"[^a-z0-9_]+","",s)
    s = re.sub(r"_+","_",s).strip("_")
    return s or None

def _get_or_create_role(name: str) -> Role:
    r = Role.query.filter(func.lower(Role.name) == name.lower()).first()
    if not r:
        r = Role(name=name)
        db.session.add(r)
        db.session.flush()
    return r

def _ensure_permission(code: str) -> Permission:
    code_n = _normalize_code(code)
    p = Permission.query.filter(func.lower(Permission.code) == code_n).first()
    if not p:
        p = Permission(code=code_n, name=PERM_ALIASES.get(code_n, code_n))
        db.session.add(p)
        db.session.flush()
    else:
        if not p.name:
            p.name = PERM_ALIASES.get(code_n, code_n)
    return p

def _get_or_create_super_user(username: str, email: str, password: str, role: Role) -> None:
    u = User.query.filter((User.email == email) | (User.username == username)).first()
    if not u:
        u = User(username=username, email=email, is_active=True)
        try:
            u.set_password(password)
        except Exception:
            u.password_hash = generate_password_hash(password, method="scrypt")
        db.session.add(u)
        db.session.flush()
    u.role = role

@click.command("seed-roles")
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
@with_appcontext
def seed_roles(force: bool, dry_run: bool) -> None:
    if not force and os.getenv("ALLOW_SEED_ROLES") != "1":
        raise click.ClickException("seed-roles disabled. Set ALLOW_SEED_ROLES=1 or use --force.")
    is_prod = (os.getenv("FLASK_ENV") == "production") or (os.getenv("ENVIRONMENT") == "production") or (os.getenv("DEBUG") not in ("1","true","True"))
    if is_prod and not force:
        if not click.confirm("Production environment. Continue?", default=False):
            click.echo("Canceled."); return

    if dry_run:
        click.echo(f" - Ensure {len(RESERVED_CODES)} permissions")
        click.echo(" - Create roles and assign permissions")
        click.echo(f" - Ensure super admin user: {SUPER_USERNAME} <{SUPER_EMAIL}>")
        return

    affected_roles: set[int] = set()

    try:
        for code in sorted(RESERVED_CODES):
            _ensure_permission(code)

        super_admin = _get_or_create_role("super_admin")
        admin = _get_or_create_role("admin")
        staff = _get_or_create_role("staff")
        registered_customer = _get_or_create_role("registered_customer")

        all_perms = Permission.query.all()
        current = {(p.code or "").lower() for p in (super_admin.permissions or [])}
        for p in all_perms:
            if (p.code or "").lower() not in current:
                super_admin.permissions.append(p)
                affected_roles.add(super_admin.id)

        for role_name, perms in ROLE_PERMISSIONS.items():
            role = {"admin": admin, "staff": staff, "registered_customer": registered_customer}[role_name]
            desired = {_normalize_code(c) for c in perms}
            role.permissions.clear()
            for code in desired:
                role.permissions.append(_ensure_permission(code))
            affected_roles.add(role.id)

        _get_or_create_super_user(SUPER_USERNAME, SUPER_EMAIL, SUPER_PASSWORD, super_admin)
        db.session.commit()

    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

    for rid in affected_roles:
        try: clear_role_permission_cache(rid)
        except: pass
        try: clear_users_cache_by_role(rid)
        except: pass

    click.echo("OK: roles, permissions, and super admin synced.")

def register_cli(app) -> None:
    app.cli.add_command(seed_roles)
