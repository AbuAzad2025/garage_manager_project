from __future__ import annotations
import os, re, click
from flask.cli import with_appcontext
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models import Role, Permission
from utils import clear_role_permission_cache, clear_users_cache_by_role

BACKUP_CODE = "backup_database"
RESTORE_CODE = "restore_database"
LEGACY_CODE = "backup_restore"
RESERVED_CODES = frozenset({
    "backup_database","restore_database","manage_permissions","manage_roles","manage_users",
    "manage_customers","manage_sales","manage_service","manage_reports","view_reports",
    "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
    "manage_payments","manage_expenses","view_inventory","manage_inventory","warehouse_transfer",
    "view_parts","view_preorders","add_preorder","edit_preorder","delete_preorder",
    "add_customer","add_supplier","add_partner","place_online_order",
})

ROLE_PERMISSIONS = {
    "admin": {
        "backup_database","manage_permissions","manage_roles","manage_users",
        "manage_customers","manage_sales","manage_service","manage_reports","view_reports",
        "manage_vendors","manage_shipments","manage_warehouses","view_warehouses","manage_exchange",
        "manage_payments","manage_expenses","view_inventory","warehouse_transfer","view_parts",
        "add_customer","add_supplier","add_partner",
    },
    "staff": {
        "manage_customers","manage_sales","manage_service",
        "view_parts","view_warehouses","view_inventory",
    },
    "registered_customer": {
        "place_online_order","view_preorders","view_parts",
    },
}

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

def _find_permission_by_code_or_name(code_or_name: str) -> Permission | None:
    target = _normalize_code(code_or_name) or (code_or_name or "").strip().lower()
    if not target: return None
    p = Permission.query.filter(func.lower(Permission.code) == target).first()
    if p: return p
    return Permission.query.filter(func.lower(Permission.name) == target).first()

def _ensure_permission(code: str) -> Permission:
    code_n = _normalize_code(code)
    if not code_n:
        raise click.ClickException(f"Invalid permission code: {code!r}")
    p = Permission.query.filter(func.lower(Permission.code) == code_n).first()
    if not p:
        p = Permission.query.filter(func.lower(Permission.name) == code_n).first()
    if p:
        if not p.code: p.code = code_n
        if not p.name: p.name = code_n
        return p
    p = Permission(code=code_n, name=code_n)
    db.session.add(p)
    db.session.flush()
    return p

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
            click.echo("Canceled.")
            return

    affected_roles: set[int] = set()
    planned: list[str] = []

    legacy = _find_permission_by_code_or_name(LEGACY_CODE)
    if legacy:
        impacted = sum(1 for r in Role.query.all() if legacy in (r.permissions or []))
        planned.append(f"Remove legacy '{LEGACY_CODE}' ({impacted} roles).")

    planned.append(f"Ensure {len(RESERVED_CODES)} reserved permissions.")
    for rn in ("super_admin","admin","staff","registered_customer"):
        if not Role.query.filter(func.lower(Role.name) == rn).first():
            planned.append(f"Create role '{rn}'.")
    planned.append("Sync permissions for roles.")

    if dry_run:
        if planned:
            click.echo("Planned changes:")
            for m in planned: click.echo(f" - {m}")
        else:
            click.echo("No changes.")
        return

    try:
        with db.session.begin():
            if legacy:
                for r in Role.query.all():
                    if legacy in (r.permissions or []):
                        r.permissions.remove(legacy)
                        affected_roles.add(r.id)
                try:
                    db.session.delete(legacy)
                except Exception:
                    pass

            for code in sorted(RESERVED_CODES):
                _ensure_permission(code)

            super_admin = _get_or_create_role("super_admin")
            admin = _get_or_create_role("admin")
            staff = _get_or_create_role("staff")
            registered_customer = _get_or_create_role("registered_customer")

            all_perms = Permission.query.all()
            current = {(p.code or p.name or "").strip().lower() for p in (super_admin.permissions or [])}
            for p in all_perms:
                key = (p.code or p.name or "").strip().lower()
                if key and key not in current:
                    super_admin.permissions.append(p)
                    affected_roles.add(super_admin.id)

            for role_name, perms in ROLE_PERMISSIONS.items():
                role = {"admin": admin, "staff": staff, "registered_customer": registered_customer}[role_name]
                desired = {_normalize_code(c) for c in perms}
                role.permissions.clear()
                for code in desired:
                    perm = _ensure_permission(code)
                    role.permissions.append(perm)
                affected_roles.add(role.id)

    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"Commit failed: {e}") from e

    for rid in affected_roles:
        try: clear_role_permission_cache(rid)
        except Exception: pass
        try: clear_users_cache_by_role(rid)
        except Exception: pass

    click.echo("OK: roles and permissions synced.")

def register_cli(app) -> None:
    app.cli.add_command(seed_roles)
