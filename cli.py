from __future__ import annotations

import os
import re
import click
from flask.cli import with_appcontext
from sqlalchemy import func, or_
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
    "view_shop","browse_products","manage_shop",
    "access_api","manage_api",
    "view_notes","manage_notes",
    "view_barcode","manage_barcode",
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
    "manage_shop": "إدارة المتجر",
    "access_api": "الوصول إلى API",
    "manage_api": "إدارة API",
    "view_notes": "عرض الملاحظات",
    "manage_notes": "إدارة الملاحظات",
    "view_barcode": "عرض الباركود",
    "manage_barcode": "إدارة الباركود",
}

ROLE_PERMISSIONS = {
    "admin": {
        "backup_database","manage_permissions","manage_roles","manage_users",
        "manage_customers","manage_service","manage_reports","view_reports",
        "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
        "manage_payments","manage_expenses","view_inventory","warehouse_transfer","view_parts",
        "add_customer","add_supplier","add_partner",
        "manage_sales",
        "access_api","manage_api",
        "view_notes","manage_notes",
        "view_barcode","manage_barcode",
    },
    "staff": {
        "manage_customers","manage_service",
        "view_parts","view_warehouses","view_inventory",
        "view_notes",
    },
    "registered_customer": {
        "place_online_order","view_preorders","view_parts","view_shop","browse_products",
    },
    "mechanic": {
        "manage_service","view_warehouses","view_inventory","view_parts",
    },
}

SUPER_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "azad").strip()
SUPER_EMAIL = (os.getenv("SUPER_ADMIN_EMAIL", "rafideen.ahmadghannam@gmail.com") or "").strip().lower()
SUPER_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "AZ123456")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL", "admin@example.com") or "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ADMIN123")

STAFF_USERNAME = os.getenv("STAFF_USERNAME", "staff").strip()
STAFF_EMAIL = (os.getenv("STAFF_EMAIL", "staff@example.com") or "").strip().lower()
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "STAFF123")

MECH_USERNAME = os.getenv("MECHANIC_USERNAME", "mechanic").strip()
MECH_EMAIL = (os.getenv("MECHANIC_EMAIL", "mechanic@example.com") or "").strip().lower()
MECH_PASSWORD = os.getenv("MECHANIC_PASSWORD", "MECH123")

RC_USERNAME = os.getenv("REGISTERED_CUSTOMER_USERNAME", "customer").strip()
RC_EMAIL = (os.getenv("REGISTERED_CUSTOMER_EMAIL", "customer@example.com") or "").strip().lower()
RC_PASSWORD = os.getenv("REGISTERED_CUSTOMER_PASSWORD", "CUST123")

def _normalize_code(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
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
    if not code_n:
        raise click.ClickException(f"Invalid permission code: {code!r}")
    p = Permission.query.filter(func.lower(Permission.code) == code_n).first()
    if not p:
        p = Permission(code=code_n, name=code_n, name_ar=PERM_ALIASES.get(code_n))
        db.session.add(p)
        db.session.flush()
    else:
        if not p.name or p.name != code_n:
            p.name = code_n
        if not getattr(p, "name_ar", None):
            p.name_ar = PERM_ALIASES.get(code_n)
    return p

def _assign_role_perms(role: Role, desired_codes: set[str], *, reset: bool = False) -> None:
    desired = {_normalize_code(c) for c in desired_codes if _normalize_code(c)}
    if reset:
        role.permissions.clear()
        db.session.flush()
    current = {(p.code or "").lower() for p in role.permissions}
    missing = [_ensure_permission(c) for c in desired if c not in current]
    role.permissions.extend(missing)

def _get_or_create_user(username: str, email: str, password: str, role: Role) -> User:
    q = User.query.filter(
        or_(func.lower(User.email) == email.lower(),
            func.lower(User.username) == username.lower())
    )
    u = q.first()
    if not u:
        u = User(username=username, email=email, is_active=True)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()
    else:
        if not u.is_active:
            u.is_active = True
        if not u.username:
            u.username = username
        if not u.email:
            u.email = email
        if not u.password_hash:
            u.set_password(password)
    u.role = role
    return u

def _is_production() -> bool:
    fe = os.getenv("FLASK_ENV", "").lower()
    env = os.getenv("ENVIRONMENT", "").lower()
    debug = os.getenv("DEBUG", "").lower()
    return (fe == "production") or (env == "production") or (debug not in ("1", "true", "yes"))

@click.command("seed-roles")
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--reset", "reset_roles", is_flag=True)
@with_appcontext
def seed_roles(force: bool, dry_run: bool, reset_roles: bool) -> None:
    if not force and os.getenv("ALLOW_SEED_ROLES") != "1":
        raise click.ClickException("seed-roles disabled. Set ALLOW_SEED_ROLES=1 or use --force.")
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False):
            click.echo("Canceled.")
            return
    if dry_run:
        click.echo(f"- Ensure {len(RESERVED_CODES)} permissions exist")
        click.echo("- Ensure roles: super_admin, admin, staff, registered_customer, mechanic")
        click.echo(f"- Assign role permissions (reset={reset_roles})")
        click.echo(f"- Ensure users:")
        click.echo(f"  super_admin: {SUPER_USERNAME} <{SUPER_EMAIL}>")
        click.echo(f"  admin      : {ADMIN_USERNAME} <{ADMIN_EMAIL}>")
        click.echo(f"  staff      : {STAFF_USERNAME} <{STAFF_EMAIL}>")
        click.echo(f"  mechanic   : {MECH_USERNAME} <{MECH_EMAIL}>")
        click.echo(f"  reg_cust   : {RC_USERNAME} <{RC_EMAIL}>")
        return
    affected_roles: set[int] = set()
    try:
        with db.session.begin():
            for code in sorted(RESERVED_CODES):
                _ensure_permission(code)
            super_admin = _get_or_create_role("super_admin")
            admin = _get_or_create_role("admin")
            staff = _get_or_create_role("staff")
            registered_customer = _get_or_create_role("registered_customer")
            mechanic = _get_or_create_role("mechanic")
            all_perms = Permission.query.all()
            curr_sa = {(p.code or "").lower() for p in super_admin.permissions}
            to_add_sa = [p for p in all_perms if (p.code or "").lower() not in curr_sa]
            if to_add_sa:
                super_admin.permissions.extend(to_add_sa)
                affected_roles.add(super_admin.id)
            _assign_role_perms(admin, ROLE_PERMISSIONS["admin"], reset=reset_roles); affected_roles.add(admin.id)
            _assign_role_perms(staff, ROLE_PERMISSIONS["staff"], reset=reset_roles); affected_roles.add(staff.id)
            _assign_role_perms(registered_customer, ROLE_PERMISSIONS["registered_customer"], reset=reset_roles); affected_roles.add(registered_customer.id)
            _assign_role_perms(mechanic, ROLE_PERMISSIONS["mechanic"], reset=reset_roles); affected_roles.add(mechanic.id)
            _get_or_create_user(SUPER_USERNAME, SUPER_EMAIL, SUPER_PASSWORD, super_admin)
            _get_or_create_user(ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD, admin)
            _get_or_create_user(STAFF_USERNAME, STAFF_EMAIL, STAFF_PASSWORD, staff)
            _get_or_create_user(MECH_USERNAME, MECH_EMAIL, MECH_PASSWORD, mechanic)
            _get_or_create_user(RC_USERNAME, RC_EMAIL, RC_PASSWORD, registered_customer)
        for rid in affected_roles:
            try:
                clear_role_permission_cache(rid)
            except Exception:
                pass
            try:
                clear_users_cache_by_role(rid)
            except Exception:
                pass
        click.echo("OK: roles, permissions, and users synced.")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"Commit failed: {e}") from e

@click.command("seed-palestine")
@with_appcontext
def seed_palestine_cmd():
    from seed_palestine import (
        seed_permissions_roles_users,
        seed_customers,
        seed_suppliers_partners_employees,
        seed_equipment_types_categories_products,
        seed_shipments_stock,
        seed_preorders_sales_invoices_payments,
        seed_service,
        seed_online,
        seed_expenses_and_payables,
        seed_notes,
    )

    users = seed_permissions_roles_users()
    u_owner, u_admin, u_seller, u_mech = users

    customers = seed_customers()
    suppliers, partners, employees = seed_suppliers_partners_employees()
    warehouses, products, et_objs, cats = seed_equipment_types_categories_products(suppliers, partners)

    seed_shipments_stock(warehouses, products)
    seed_preorders_sales_invoices_payments(customers, u_admin, warehouses, products)
    seed_service(customers, u_mech, warehouses, products, partners)
    seed_online(customers, products)
    seed_expenses_and_payables(employees, warehouses, partners, suppliers)
    seed_notes(customers, users)

    click.echo("OK: Palestine demo data seeded.")

def register_cli(app) -> None:
    app.cli.add_command(seed_roles)
    app.cli.add_command(seed_palestine_cmd)
