# cli.py - Command Line Interface
# Location: /garage_manager/cli.py
# Description: Command line tools and utilities

from __future__ import annotations

import json, os, re, uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import click
from flask.cli import with_appcontext
from sqlalchemy import func, or_, select, text as sa_text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from utils import clear_role_permission_cache, clear_users_cache_by_role, get_entity_balance_in_ils, validate_currency_consistency
from permissions_config.permissions import PermissionsRegistry
from models import (
    Account, AuditLog, Customer, Employee, ExchangeTransaction, Expense, ExpenseType, GLBatch, GLEntry, GL_ACCOUNTS,
    Invoice, Note, OnlineCart, OnlineCartItem, OnlinePayment, OnlinePreOrder, OnlinePreOrderItem,
    PartnerSettlement, Payment, PaymentDirection, PaymentEntityType, PaymentMethod, PaymentStatus, Permission,
    PreOrder, Product, Role, ServicePart, ServiceRequest, ServiceStatus, ServiceTask,
    Shipment, ShipmentItem, StockAdjustment, StockAdjustmentItem, StockLevel, Supplier,
    SupplierSettlement, Transfer, TransferDirection, Warehouse, _gl_upsert_batch_and_entries,
    build_partner_settlement_draft, build_supplier_settlement_draft, User,
)

RESERVED_CODES = PermissionsRegistry.get_protected_permissions()

def _get_perm_name_ar(code: str) -> str:
    perm_info = PermissionsRegistry.get_permission_info(code)
    return perm_info.get('name_ar', code) if perm_info else code

def _parse_dt(val: str | None, end: bool = False):
    """تحويل التاريخ من نص إلى datetime"""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.strip())
        if end:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except Exception:
        return None

ROLE_PERMISSIONS = {
    role_name: PermissionsRegistry.get_role_permissions(role_name)
    for role_name in PermissionsRegistry.ROLES.keys()
    if role_name not in ['owner', 'developer', 'super_admin', 'super']
}

SUPER_USERNAME = os.getenv("SUPER_ADMIN_USERNAME","azad").strip()
SUPER_EMAIL = (os.getenv("SUPER_ADMIN_EMAIL","rafideen.ahmadghannam@gmail.com") or "").strip().lower()
SUPER_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD","AZ123456")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME","admin").strip()
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL","admin@example.com") or "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD","ADMIN123")
STAFF_USERNAME = os.getenv("STAFF_USERNAME","staff").strip()
STAFF_EMAIL = (os.getenv("STAFF_EMAIL","staff@example.com") or "").strip().lower()
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD","STAFF123")
MECH_USERNAME = os.getenv("MECHANIC_USERNAME","mechanic").strip()
MECH_EMAIL = (os.getenv("MECHANIC_EMAIL","mechanic@example.com") or "").strip().lower()
MECH_PASSWORD = os.getenv("MECHANIC_PASSWORD","MECH123")
RC_USERNAME = os.getenv("REGISTERED_CUSTOMER_USERNAME","customer").strip()
RC_EMAIL = (os.getenv("REGISTERED_CUSTOMER_EMAIL","customer@example.com") or "").strip().lower()
RC_PASSWORD = os.getenv("REGISTERED_CUSTOMER_PASSWORD","CUST123")

def _normalize_code(s: str | None) -> str | None:
    if not s: return None
    s = re.sub(r"_+","_",re.sub(r"[^a-z0-9_]+","",re.sub(r"[\s\-]+","_",s.strip().lower()))).strip("_")
    return s or None

def _D(x):
    try: return Decimal(str(x))
    except Exception: return Decimal("0")
def _Q2(x): return _D(x).quantize(Decimal("0.01"), ROUND_HALF_UP)

def _clean_role_perms(role: Role) -> None:
    if getattr(role, "permissions", None) is None:
        role.permissions = []
        return
    role.permissions[:] = [p for p in role.permissions if isinstance(p, Permission)]
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
    if p:
        p.name = p.name or code_n
        perm_info = PermissionsRegistry.get_permission_info(code_n)
        if perm_info:
            p.name_ar = p.name_ar or perm_info.get('name_ar')
            p.module = p.module or perm_info.get('module')
            p.description = p.description or perm_info.get('description')
            p.is_protected = perm_info.get('is_protected', False)
        return p
    try:
        perm_info = PermissionsRegistry.get_permission_info(code_n)
        p = Permission(
            code=code_n,
            name=code_n,
            name_ar=perm_info.get('name_ar') if perm_info else None,
            module=perm_info.get('module') if perm_info else None,
            description=perm_info.get('description') if perm_info else None,
            is_protected=perm_info.get('is_protected', False) if perm_info else False
        )
        db.session.add(p)
        db.session.flush()
        return p
    except IntegrityError:
        db.session.rollback()
        p = Permission.query.filter(func.lower(Permission.code) == code_n).first()
        if not p:
            raise
        return p

def _assign_role_perms(role: Role, desired_codes: set[str], *, reset: bool = False) -> None:
    if not isinstance(role, Role):
        return
    desired = {(_normalize_code(c) or "").lower() for c in (desired_codes or set())}
    desired.discard("")
    if getattr(role, "permissions", None) is None:
        role.permissions = []
    else:
        role.permissions[:] = [p for p in role.permissions if isinstance(p, Permission)]
    if reset:
        role.permissions.clear()
        db.session.flush()
    current = {(p.code or "").lower() for p in role.permissions}
    missing = desired - current
    if not missing:
        return
    to_add: list[Permission] = []
    for code in sorted(missing):
        perm = _ensure_permission(code)
        if isinstance(perm, Permission):
            to_add.append(perm)
    if to_add:
        role.permissions.extend(to_add)
        db.session.flush()

def _norm_email(s: str) -> str:
    return (s or "").strip().lower()

def _norm_user(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())

def _get_or_create_user(username: str, email: str, password: str, role: Role) -> User:
    uname, mail = _norm_user(username), _norm_email(email)
    if not uname or not mail:
        raise click.ClickException("username/email required")
    u = User.query.filter(or_(func.lower(User.email) == mail, func.lower(User.username) == uname)).first()
    if u:
        u.is_active = True if u.is_active is not True else u.is_active
        u.username = u.username or uname
        u.email = u.email or mail
        if not u.password_hash and password:
            u.set_password(password)
        u.role = role
        return u
    try:
        u = User(username=uname, email=mail, is_active=True, role=role)
        if password:
            u.set_password(password)
        db.session.add(u)
        db.session.flush()
        return u
    except IntegrityError:
        db.session.rollback()
        u = User.query.filter(or_(func.lower(User.email) == mail, func.lower(User.username) == uname)).first()
        if not u:
            raise
        if not u.role:
            u.role = role
        return u

def _is_production() -> bool:
    fe = os.getenv("FLASK_ENV","").lower(); env = os.getenv("ENVIRONMENT","").lower(); debug = os.getenv("DEBUG","").lower()
    return (fe=="production") or (env=="production") or (debug not in ("1","true","yes"))

def _ensure_schema_ready(): db.session.execute(select(1))

def _begin():
    try: db.session.rollback()
    except Exception: pass
    return db.session.begin()

@click.command("create-superadmin")
@click.option("--username", required=True)
@click.option("--password", required=True)
@click.option("--email", default=None)
@with_appcontext
def create_superadmin(username, password, email):
    s = db.session
    if not email:
        email = f"{username}@local"
    r = Role.query.filter_by(name="super_admin").one_or_none()
    if not r:
        r = Role(name="super_admin")
        s.add(r)
        s.flush()
    u = User.query.filter((User.username==username)|(User.email==email)).one_or_none()
    if not u:
        u = User(username=username, email=email)
        u.set_password(password)
        u.role = r
        s.add(u)
        s.flush()
    else:
        u.username = username
        u.email = email
        u.role = r
        u.set_password(password)
    s.commit()
    click.echo(f"✅ super_admin '{username}' created or updated.")

@click.command("seed-roles")
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--reset", "reset_roles", is_flag=True)
@click.option("--allow-default-passwords", is_flag=True)
@with_appcontext
def seed_roles(force: bool, dry_run: bool, reset_roles: bool, allow_default_passwords: bool) -> None:
    if not force and os.getenv("ALLOW_SEED_ROLES") != "1":
        raise click.ClickException("seed-roles disabled. Set ALLOW_SEED_ROLES=1 or use --force.")
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False):
            click.echo("Canceled.")
            return
    if _is_production() and not allow_default_passwords:
        weak = {"AZ123456", "ADMIN123", "STAFF123", "MECH123", "CUST123"}
        if any(p in weak for p in (SUPER_PASSWORD, ADMIN_PASSWORD, STAFF_PASSWORD, MECH_PASSWORD, RC_PASSWORD)):
            raise click.ClickException("Refusing to seed weak default passwords in production. Use --allow-default-passwords to override.")

    try:
        _ensure_schema_ready()
    except click.ClickException:
        raise
    except Exception:
        pass

    if dry_run:
        click.echo(f"- Ensure {len(RESERVED_CODES)} permissions exist")
        click.echo("- Ensure roles: super_admin, admin, staff, registered_customer, mechanic")
        click.echo(f"- Assign role permissions (reset={reset_roles})")
        click.echo("- Ensure users:")
        click.echo(f"  super_admin: {SUPER_USERNAME} <{SUPER_EMAIL}>")
        click.echo(f"  admin      : {ADMIN_USERNAME} <{ADMIN_EMAIL}>")
        click.echo(f"  staff      : {STAFF_USERNAME} <{STAFF_EMAIL}>")
        click.echo(f"  mechanic   : {MECH_USERNAME} <{MECH_EMAIL}>")
        click.echo(f"  reg_cust   : {RC_USERNAME} <{RC_EMAIL}>")
        return

    affected_roles: set[int] = set()
    try:
        with _begin():
            for code in sorted(RESERVED_CODES):
                _ensure_permission(code)

            owner_role = _get_or_create_role("owner")
            developer_role = _get_or_create_role("developer")
            super_admin = _get_or_create_role("super_admin")
            super_role = _get_or_create_role("super")
            admin = _get_or_create_role("admin")
            manager = _get_or_create_role("manager")
            staff = _get_or_create_role("staff")
            mechanic = _get_or_create_role("mechanic")
            registered_customer = _get_or_create_role("registered_customer")
            guest_role = _get_or_create_role("guest")

            all_perms = [p for p in Permission.query.all() if isinstance(p, Permission)]
            
            for super_role_obj in [owner_role, developer_role, super_admin, super_role]:
                if getattr(super_role_obj, "permissions", None) is None:
                    super_role_obj.permissions = []
                else:
                    super_role_obj.permissions[:] = [p for p in super_role_obj.permissions if isinstance(p, Permission)]
                curr = {(p.code or "").lower() for p in super_role_obj.permissions}
                for p in all_perms:
                    if (p.code or "").lower() not in curr:
                        super_role_obj.permissions.append(p)
                db.session.flush()
                if super_role_obj.id is not None:
                    affected_roles.add(super_role_obj.id)

            if 'admin' in ROLE_PERMISSIONS:
                _assign_role_perms(admin, ROLE_PERMISSIONS['admin'], reset=reset_roles)
                if admin.id is not None:
                    affected_roles.add(admin.id)
            
            if 'manager' in ROLE_PERMISSIONS:
                _assign_role_perms(manager, ROLE_PERMISSIONS['manager'], reset=reset_roles)
                if manager.id is not None:
                    affected_roles.add(manager.id)
            
            if 'staff' in ROLE_PERMISSIONS:
                _assign_role_perms(staff, ROLE_PERMISSIONS['staff'], reset=reset_roles)
                if staff.id is not None:
                    affected_roles.add(staff.id)
            
            if 'mechanic' in ROLE_PERMISSIONS:
                _assign_role_perms(mechanic, ROLE_PERMISSIONS['mechanic'], reset=reset_roles)
                if mechanic.id is not None:
                    affected_roles.add(mechanic.id)
            
            if 'registered_customer' in ROLE_PERMISSIONS:
                _assign_role_perms(registered_customer, ROLE_PERMISSIONS['registered_customer'], reset=reset_roles)
                if registered_customer.id is not None:
                    affected_roles.add(registered_customer.id)
            
            if 'guest' in ROLE_PERMISSIONS:
                _assign_role_perms(guest_role, ROLE_PERMISSIONS['guest'], reset=reset_roles)
                if guest_role.id is not None:
                    affected_roles.add(guest_role.id)

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
    except IntegrityError as e:
        db.session.rollback()
        raise click.ClickException(f"Constraint/unique violation: {getattr(e, 'orig', e)}") from e
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"DB error: {e.__class__.__name__}: {e}") from e

@click.command("sync-permissions")
@click.option("--dry-run", is_flag=True)
@with_appcontext
def sync_permissions(dry_run: bool) -> None:
    desired=set(RESERVED_CODES)
    if dry_run: click.echo(f"Would ensure {len(desired)} permissions exist"); return
    try:
        with _begin():
            for code in sorted(desired): _ensure_permission(code)
        click.echo("OK: permissions synced.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("list-permissions")
@click.option("--q", default="")
@with_appcontext
def list_permissions(q: str) -> None:
    s=(q or "").strip().lower()
    qy=Permission.query
    if s: qy=qy.filter(or_(func.lower(Permission.code).contains(s), func.lower(Permission.name_ar).contains(s)))
    for p in qy.order_by(Permission.code).all(): click.echo(f"{p.id:>3}  {p.code:<30}  {p.name_ar or ''}")

@click.command("list-roles")
@with_appcontext
def list_roles() -> None:
    for r in Role.query.order_by(Role.name).all():
        cnt=len(r.permissions or [])
        click.echo(f"{r.id:>3}  {r.name:<25} perms={cnt}")

@click.command("role-add-perms")
@click.argument("role_name", nargs=1)
@click.argument("codes", nargs=-1)
@click.option("--reset", is_flag=True)
@with_appcontext
def role_add_perms(role_name: str, codes: tuple[str, ...], reset: bool) -> None:
    if not role_name:
        raise click.ClickException("role_name is required")
    if not codes and not reset:
        raise click.ClickException("provide at least one permission code or use --reset")
    try:
        with _begin():
            r = _get_or_create_role(role_name)
            _assign_role_perms(r, set(codes), reset=reset)
        clear_role_permission_cache(r.id)
        clear_users_cache_by_role(r.id)
        click.echo(f"OK: role {role_name} updated.")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"Commit failed: {e}") from e

@click.command("create-role")
@click.option("--codes", default="")
@click.argument("name", nargs=1)
@with_appcontext
def create_role(name: str, codes: str) -> None:
    desired={c.strip() for c in (codes or "").split(",") if c.strip()}
    try:
        with _begin():
            r=_get_or_create_role(name)
            if desired: _assign_role_perms(r, desired, reset=False)
        clear_role_permission_cache(r.id); click.echo(f"OK: role {name} created/updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("export-rbac")
@with_appcontext
def export_rbac() -> None:
    data=[]
    for r in Role.query.order_by(Role.name).all():
        perms=sorted([(p.code or "") for p in r.permissions or []])
        data.append({"role":r.name,"permissions":perms})
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))

@click.command("create-user")
@click.argument("username")
@click.argument("email")
@click.argument("password")
@click.option("--role", "role_name", default="staff")
@with_appcontext
def create_user(username: str, email: str, password: str, role_name: str) -> None:
    try:
        with _begin():
            r=_get_or_create_role(role_name); _get_or_create_user(username,email,password,r)
        click.echo("OK: user created/updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("user-set-password")
@click.argument("identifier")
@click.argument("password")
@with_appcontext
def user_set_password(identifier: str, password: str) -> None:
    u=User.query.filter(or_(func.lower(User.email)==identifier.lower(), func.lower(User.username)==identifier.lower())).first()
    if not u: raise click.ClickException("User not found")
    try:
        with _begin(): u.set_password(password)
        click.echo("OK: password updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("user-activate")
@click.argument("identifier")
@click.option("--active/--inactive", default=True)
@with_appcontext
def user_activate(identifier: str, active: bool) -> None:
    u=User.query.filter(or_(func.lower(User.email)==identifier.lower(), func.lower(User.username)==identifier.lower())).first()
    if not u: raise click.ClickException("User not found")
    try:
        with _begin(): u.is_active=bool(active)
        click.echo(f"OK: user {'activated' if active else 'deactivated'}.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("user-assign-role")
@click.argument("identifier")
@click.argument("role_name")
@with_appcontext
def user_assign_role(identifier: str, role_name: str) -> None:
    u=User.query.filter(or_(func.lower(User.email)==identifier.lower(), func.lower(User.username)==identifier.lower())).first()
    if not u: raise click.ClickException("User not found")
    try:
        with _begin():
            r=_get_or_create_role(role_name); u.role=r
        clear_users_cache_by_role(r.id); click.echo("OK: user role updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("list-users")
@click.option("--q", default="")
@click.option("--role", "role_name", default="")
@with_appcontext
def list_users(q: str, role_name: str) -> None:
    s=(q or "").strip().lower(); qy=User.query
    if s: qy=qy.filter(or_(func.lower(User.username).contains(s), func.lower(User.email).contains(s)))
    if role_name.strip(): qy=qy.join(Role).filter(func.lower(Role.name)==role_name.strip().lower())
    for u in qy.order_by(User.id).all():
        rn=u.role.name if u.role else "-"
        click.echo(f"{u.id:>3}  {u.username:<20}  {u.email:<30}  role={rn:<18}  active={bool(u.is_active)}")

@click.command("list-customers")
@click.option("--q", default="")
@click.option("--limit", type=int, default=100)
@with_appcontext
def list_customers(q: str, limit: int):
    s=(q or "").strip().lower(); qy=Customer.query
    if s:
        like=f"%{s}%"
        qy=qy.filter(or_(func.lower(Customer.name).like(like), func.lower(Customer.phone).like(like), func.lower(Customer.email).like(like), func.lower(Customer.whatsapp).like(like)))
    rows=qy.order_by(Customer.id.asc()).limit(limit).all()
    for c in rows: click.echo(f"{c.id:>3}  {c.name:<25}  phone={c.phone or '-':<15}  email={c.email or '-':<28}  balance={getattr(c,'balance',0)}")

@click.command("seed-expense-types")
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--deactivate-missing", is_flag=True)
@with_appcontext
def seed_expense_types(force: bool, dry_run: bool, deactivate_missing: bool) -> None:
    if not force and os.getenv("ALLOW_SEED_EXPENSE_TYPES")!="1": raise click.ClickException("seed-expense-types disabled. Set ALLOW_SEED_EXPENSE_TYPES=1 or use --force.")
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False): click.echo("Canceled."); return
    base_types=[("رواتب","مصروف رواتب وأجور",True),("كهرباء","فواتير كهرباء",True),("مياه","فواتير مياه",True),("جمارك","رسوم جمركية",True),("تالف","توالف/هدر مخزون",True),("استخدام داخلي","استهلاك داخلي للمخزون",True),("متفرقات","مصروفات أخرى",True)]
    if dry_run:
        click.echo("Would ensure these expense types exist/active:");
        for n,d,a in base_types: click.echo(f"- {n} ({'active' if a else 'inactive'})")
        if deactivate_missing: click.echo("Would deactivate missing types not in the list."); return
    try:
        with _begin():
            wanted_names=set()
            for name,desc,active in base_types:
                wanted_names.add(name.lower())
                ex=ExpenseType.query.filter(func.lower(ExpenseType.name)==name.lower()).first()
                if not ex: ex=ExpenseType(name=name, description=desc, is_active=bool(active)); db.session.add(ex)
                else:
                    if desc: ex.description=desc
                    ex.is_active=bool(active)
            if deactivate_missing:
                others=ExpenseType.query.filter(func.lower(ExpenseType.name).notin_(wanted_names)).all()
                for ex in others:
                    if ex.is_active: ex.is_active=False
        click.echo("OK: expense types seeded.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("seed-employees")
@click.option("--force", is_flag=True)
@with_appcontext
def seed_employees(force: bool) -> None:
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False):
            click.echo("Canceled.")
            return
    base = [
        ("أحمد", "محاسب", 3500),
        ("ليلى", "أمينة مستودع", 3200),
        ("خالد", "مندوب مبيعات", 3000),
        ("سوسن", "موارد بشرية", 2800),
    ]
    try:
        with _begin():
            for name, position, salary in base:
                row = Employee.query.filter(func.lower(Employee.name) == name.lower()).first()
                if not row:
                    db.session.add(Employee(name=name, position=position, salary=_Q2(salary), currency="ILS"))
                else:
                    if not row.position:
                        row.position = position
                    if not row.salary:
                        row.salary = _Q2(salary)
        click.echo("OK: employees seeded.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

def _get_expense_type_id(name: str) -> int:
    ex = ExpenseType.query.filter(func.lower(ExpenseType.name) == name.strip().lower()).first()
    if not ex:
        ex = ExpenseType(name=name.strip(), description=name.strip(), is_active=True)
        db.session.add(ex)
        db.session.flush()
    return int(ex.id)

@click.command("seed-salaries")
@click.option("--months", type=int, default=6)
@click.option("--start", type=str, default="")
@with_appcontext
def seed_salaries(months: int, start: str) -> None:
    from datetime import date, timedelta
    # تحديد أول يوم من الشهر لبداية الفترة
    today = date.today()
    if start:
        try:
            y, m = [int(x) for x in start.split("-")[:2]]
            start_date = date(y, m, 1)
        except Exception:
            start_date = date(today.year, today.month, 1)
    else:
        start_date = date(today.year, today.month, 1)
    salary_type_id = _get_expense_type_id("رواتب")
    emps = Employee.query.order_by(Employee.id).all()
    if not emps:
        click.echo("No employees. Run: flask seed-employees")
        return
    try:
        with _begin():
            for i in range(months):
                # حساب تاريخ هذا الشهر بالإزاحة العكسية i
                year = start_date.year
                month = start_date.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                payday = date(year, month, 25)
                for emp in emps:
                    amt = _Q2(emp.salary or 0)
                    ex = Expense(
                        date=payday,
                        amount=amt,
                        currency="ILS",
                        type_id=salary_type_id,
                        employee_id=emp.id,
                        payee_type="EMPLOYEE",
                        payee_entity_id=emp.id,
                        payee_name=emp.name,
                        payment_method="cash",
                        description=f"راتب شهر {month:02d}-{year} للموظف {emp.name}",
                        notes=None,
                    )
                    db.session.add(ex)
        click.echo(f"OK: salaries seeded for {len(emps)} employees x {months} months.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("seed-expenses-demo")
@with_appcontext
def seed_expenses_demo() -> None:
    from datetime import datetime, timedelta
    et_electric = _get_expense_type_id("كهرباء")
    et_water = _get_expense_type_id("مياه")
    et_misc = _get_expense_type_id("متفرقات")
    base = [
        (et_electric, 1200.00, "فاتورة كهرباء شهرية"),
        (et_water, 450.00, "فاتورة مياه شهرية"),
        (et_misc, 300.00, "قرطاسية ومستلزمات"),
    ]
    now = datetime.utcnow()
    try:
        with _begin():
            for idx, (tid, amount, desc) in enumerate(base):
                ex = Expense(
                    date=now - timedelta(days=idx * 7),
                    amount=_Q2(amount),
                    currency="ILS",
                    type_id=tid,
                    payee_type="OTHER",
                    payment_method="cash",
                    description=desc,
                )
                db.session.add(ex)
        click.echo("OK: demo expenses seeded.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("seed-branches")
@click.option("--force", is_flag=True)
@with_appcontext
def seed_branches(force: bool) -> None:
    """إنشاء الفرع الرئيسي الافتراضي"""
    from models import Branch
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False):
            click.echo("Canceled.")
            return
    try:
        with _begin():
            # التحقق من وجود الفرع الرئيسي
            main_branch = Branch.query.filter(func.lower(Branch.code) == 'main').first()
            if not main_branch:
                main_branch = Branch(
                    code='MAIN',
                    name='الفرع الرئيسي',
                    is_active=True,
                    currency='ILS',
                    timezone='Asia/Jerusalem'
                )
                db.session.add(main_branch)
                click.echo("✅ Created main branch")
            else:
                click.echo("ℹ️  Main branch already exists")
        click.echo("OK: branches seeded.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("expense-type")
@click.option("--name", required=True)
@click.option("--desc", default="")
@click.option("--active/--inactive", default=True)
@with_appcontext
def expense_type_cmd(name: str, desc: str, active: bool) -> None:
    try:
        with _begin():
            ex=ExpenseType.query.filter(func.lower(ExpenseType.name)==name.strip().lower()).first()
            if not ex: ex=ExpenseType(name=name.strip(), description=(desc or "").strip(), is_active=bool(active)); db.session.add(ex)
            else:
                ex.description=(desc or ex.description or "").strip(); ex.is_active=bool(active)
        click.echo("OK: expense type created/updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(f"Commit failed: {e}") from e

@click.command("seed-palestine")
@click.option("--reset", is_flag=True)
@with_appcontext
def seed_palestine_cmd(reset: bool):
    try:
        from seed_palestine import seed_palestine as _seed_cmd
    except Exception as e:
        raise click.ClickException(f"تعذّر استيراد seed_palestine.py: {e}")
    cb=getattr(_seed_cmd,"callback",None)
    if callable(cb): return cb(reset=reset)
    return _seed_cmd(reset=reset)

@click.command("seed-all")
@click.option("--force", is_flag=True)
@click.option("--reset-roles", is_flag=True)
@click.option("--deactivate-missing-expense-types", is_flag=True)
@with_appcontext
def seed_all(force: bool, reset_roles: bool, deactivate_missing_expense_types: bool) -> None:
    if _is_production() and not force:
        if not click.confirm("Production environment detected. Continue?", default=False):
            click.echo("Canceled.")
            return
    try:
        with _begin():
            for code in sorted(RESERVED_CODES):
                _ensure_permission(code)

            owner_role = _get_or_create_role("owner")
            developer_role = _get_or_create_role("developer")
            super_admin = _get_or_create_role("super_admin")
            super_role = _get_or_create_role("super")
            admin = _get_or_create_role("admin")
            manager = _get_or_create_role("manager")
            staff = _get_or_create_role("staff")
            mechanic = _get_or_create_role("mechanic")
            registered_customer = _get_or_create_role("registered_customer")
            guest_role = _get_or_create_role("guest")

            all_perms = [p for p in Permission.query.all() if isinstance(p, Permission)]
            
            for super_role_obj in [owner_role, developer_role, super_admin, super_role]:
                if getattr(super_role_obj, "permissions", None) is None:
                    super_role_obj.permissions = []
                else:
                    super_role_obj.permissions[:] = [p for p in super_role_obj.permissions if isinstance(p, Permission)]
                curr = {(p.code or "").lower() for p in super_role_obj.permissions}
                for p in all_perms:
                    if (p.code or "").lower() not in curr:
                        super_role_obj.permissions.append(p)
                db.session.flush()

            if 'admin' in ROLE_PERMISSIONS:
                _assign_role_perms(admin, ROLE_PERMISSIONS['admin'], reset=reset_roles)
            if 'manager' in ROLE_PERMISSIONS:
                _assign_role_perms(manager, ROLE_PERMISSIONS['manager'], reset=reset_roles)
            if 'staff' in ROLE_PERMISSIONS:
                _assign_role_perms(staff, ROLE_PERMISSIONS['staff'], reset=reset_roles)
            if 'mechanic' in ROLE_PERMISSIONS:
                _assign_role_perms(mechanic, ROLE_PERMISSIONS['mechanic'], reset=reset_roles)
            if 'registered_customer' in ROLE_PERMISSIONS:
                _assign_role_perms(registered_customer, ROLE_PERMISSIONS['registered_customer'], reset=reset_roles)
            if 'guest' in ROLE_PERMISSIONS:
                _assign_role_perms(guest_role, ROLE_PERMISSIONS['guest'], reset=reset_roles)

            _get_or_create_user(SUPER_USERNAME, SUPER_EMAIL, SUPER_PASSWORD, super_admin)
            _get_or_create_user(ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD, admin)
            _get_or_create_user(STAFF_USERNAME, STAFF_EMAIL, STAFF_PASSWORD, staff)
            _get_or_create_user(MECH_USERNAME, MECH_EMAIL, MECH_PASSWORD, mechanic)
            _get_or_create_user(RC_USERNAME, RC_EMAIL, RC_PASSWORD, registered_customer)

            for r in Role.query.all():
                try:
                    clear_role_permission_cache(r.id)
                    clear_users_cache_by_role(r.id)
                except Exception:
                    pass

            base_types = [
                ("رواتب", "مصروف رواتب وأجور", True),
                ("كهرباء", "فواتير كهرباء", True),
                ("مياه", "فواتير مياه", True),
                ("جمارك", "رسوم جمركية", True),
                ("تالف", "توالف/هدر مخزون", True),
                ("استخدام داخلي", "استهلاك داخلي للمخزون", True),
                ("متفرقات", "مصروفات أخرى", True),
            ]
            wanted_names = set()
            for name, desc, active in base_types:
                wanted_names.add(name.lower())
                ex = ExpenseType.query.filter(func.lower(ExpenseType.name) == name.lower()).first()
                if not ex:
                    db.session.add(ExpenseType(name=name, description=desc, is_active=bool(active)))
                else:
                    ex.description = desc
                    ex.is_active = bool(active)
            if deactivate_missing_expense_types:
                others = ExpenseType.query.filter(func.lower(ExpenseType.name).notin_(wanted_names)).all()
                for ex in others:
                    ex.is_active = False

        click.echo("✔ OK: seed-all completed.")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"Commit failed: {e}") from e

@click.command("clear-rbac-caches")
@with_appcontext
def clear_rbac_caches() -> None:
    for r in Role.query.all():
        try: clear_role_permission_cache(r.id); clear_users_cache_by_role(r.id)
        except Exception: pass
    click.echo("OK: RBAC caches cleared.")

@click.command("wh-create")
@click.option("--name", required=True)
@click.option("--type", "wtype", default="MAIN")
@click.option("--location", default="")
@click.option("--supplier-id", type=int)
@click.option("--partner-id", type=int)
@click.option("--share-percent", type=float, default=0.0)
@click.option("--online-slug", default="")
@click.option("--online-default/--no-online-default", default=False)
@with_appcontext
def wh_create(name, wtype, location, supplier_id, partner_id, share_percent, online_slug, online_default):
    try:
        with _begin():
            w=Warehouse(name=name.strip(), warehouse_type=wtype.strip().upper(), location=location or None, supplier_id=supplier_id, partner_id=partner_id, share_percent=share_percent or 0, online_slug=(online_slug or None), online_is_default=bool(online_default))
            db.session.add(w)
        click.echo(f"OK: warehouse {w.id} created.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("wh-list")
@click.option("--active", type=bool)
@click.option("--type", "wtype", default="")
@with_appcontext
def wh_list(active, wtype):
    q=Warehouse.query
    if active is not None: q=q.filter(Warehouse.is_active==bool(active))
    if wtype: q=q.filter(Warehouse.warehouse_type==wtype.strip().upper())
    for w in q.order_by(Warehouse.id).all():
        click.echo(f"{w.id:>3}  {w.name:<25} type={getattr(w.warehouse_type,'value',w.warehouse_type)} active={w.is_active} partner={w.partner_id or '-'} supplier={w.supplier_id or '-'}")

@click.command("wh-stock")
@click.option("--warehouse-id", type=int, required=True)
@click.option("--q", default="")
@with_appcontext
def wh_stock(warehouse_id: int, q: str):
    qry = (
        db.session.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(StockLevel.warehouse_id == warehouse_id)
    )
    s = (q or "").strip()
    if s:
        ss = f"%{s.lower()}%"
        qry = qry.filter(
            or_(
                func.lower(Product.name).like(ss),
                func.lower(Product.sku).like(ss),
                func.lower(Product.part_number).like(ss),
                func.lower(Product.brand).like(ss),
            )
        )
    for lvl, prod in qry.order_by(Product.name).all():
        click.echo(
            f"P{prod.id:<5} {prod.name[:40]:<40} "
            f"qty={lvl.quantity:<6} reserved={lvl.reserved_quantity:<6} "
            f"avail={lvl.available_quantity:<6} status={lvl.status}"
        )

@click.command("product-create")
@click.option("--name", required=True)
@click.option("--price", type=float, default=0)
@click.option("--brand", default="")
@click.option("--part-number", default="")
@click.option("--sku", default="")
@click.option("--barcode", default="")
@click.option("--tax-rate", type=float, default=0)
@with_appcontext
def product_create(name, price, brand, part_number, sku, barcode, tax_rate):
    try:
        with _begin():
            p=Product(name=name.strip(), price=_Q2(price), selling_price=_Q2(price), brand=brand or None, part_number=part_number or None, sku=sku or None, barcode=barcode or None, tax_rate=_Q2(tax_rate))
            db.session.add(p)
        click.echo(f"OK: product {p.id} created.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("product-find")
@click.option("--q", default="")
@click.option("--barcode", default="")
@click.option("--limit", type=int, default=50)
@with_appcontext
def product_find(q: str, barcode: str, limit: int):
    qry = Product.query
    if barcode.strip():
        qry = qry.filter(Product.barcode == barcode.strip())
    else:
        s = (q or "").strip().lower()
        if s:
            ss = f"%{s}%"
            qry = qry.filter(
                or_(
                    func.lower(Product.name).like(ss),
                    func.lower(Product.brand).like(ss),
                    func.lower(Product.part_number).like(ss),
                    func.lower(Product.sku).like(ss),
                )
            )
    rows = qry.order_by(Product.id.desc()).limit(limit).all()
    for p in rows:
        click.echo(
            f"{p.id:>4}  {p.name[:50]:<50} price={float(p.price or 0):.2f} "
            f"brand={p.brand or '-'} part={p.part_number or '-'} sku={p.sku or '-'}"
        )

@click.command("product-stock")
@click.option("--product-id", type=int, required=True)
@with_appcontext
def product_stock(product_id: int):
    lvls=StockLevel.query.filter(StockLevel.product_id==product_id).all()
    if not lvls: click.echo("No stock rows."); return
    for lvl in lvls:
        w=db.session.get(Warehouse, lvl.warehouse_id)
        click.echo(f"WH{lvl.warehouse_id:<4} {w.name if w else '-':<25} qty={lvl.quantity:<6} reserved={lvl.reserved_quantity:<6} avail={lvl.available_quantity:<6}")

@click.command("product-set-price")
@click.option("--product-id", type=int, required=True)
@click.option("--price", type=float, required=True)
@with_appcontext
def product_set_price(product_id: int, price: float):
    p=db.session.get(Product, product_id)
    if not p: raise click.ClickException("Product not found")
    try:
        with _begin(): p.price=_Q2(price); p.selling_price=_Q2(price)
        click.echo("OK: price updated.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-transfer")
@click.option("--product-id", type=int, required=True)
@click.option("--source-id", type=int, required=True)
@click.option("--destination-id", type=int, required=True)
@click.option("--qty", type=int, required=True)
@click.option("--ref", default="")
@click.option("--notes", default="")
@with_appcontext
def stock_transfer(product_id, source_id, destination_id, qty, ref, notes):
    try:
        with _begin():
            t=Transfer(reference=ref or None, product_id=product_id, source_id=source_id, destination_id=destination_id, quantity=int(qty), direction=TransferDirection.OUTGOING.value, notes=notes or None)
            db.session.add(t)
        click.echo(f"OK: transfer {t.reference} saved.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-exchange")
@click.option("--product-id", type=int, required=True)
@click.option("--warehouse-id", type=int, required=True)
@click.option("--direction", type=click.Choice(["IN","OUT","ADJUSTMENT"], case_sensitive=False), required=True)
@click.option("--qty", type=int, required=True)
@click.option("--unit-cost", type=float, default=0.0)
@click.option("--notes", default="")
@with_appcontext
def stock_exchange(product_id, warehouse_id, direction, qty, unit_cost, notes):
    try:
        with _begin():
            tx=ExchangeTransaction(product_id=product_id, warehouse_id=warehouse_id, direction=direction.upper(), quantity=int(qty), unit_cost=_Q2(unit_cost) if unit_cost else None, notes=notes or None)
            db.session.add(tx)
        click.echo(f"OK: exchange tx #{tx.id} saved.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-reserve")
@click.option("--product-id", type=int, required=True)
@click.option("--warehouse-id", type=int, required=True)
@click.option("--qty", type=int, required=True)
@with_appcontext
def stock_reserve(product_id, warehouse_id, qty):
    row=db.session.execute(select(StockLevel).where(StockLevel.product_id==product_id, StockLevel.warehouse_id==warehouse_id)).scalar_one_or_none()
    if not row: raise click.ClickException("Stock row not found")
    if row.available_quantity < qty: raise click.ClickException("Insufficient available quantity")
    try:
        with _begin(): row.reserved_quantity=int(row.reserved_quantity or 0)+int(qty)
        click.echo("OK: reserved.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-unreserve")
@click.option("--product-id", type=int, required=True)
@click.option("--warehouse-id", type=int, required=True)
@click.option("--qty", type=int, required=True)
@with_appcontext
def stock_unreserve(product_id, warehouse_id, qty):
    row=db.session.execute(select(StockLevel).where(StockLevel.product_id==product_id, StockLevel.warehouse_id==warehouse_id)).scalar_one_or_none()
    if not row: raise click.ClickException("Stock row not found")
    newv=int(row.reserved_quantity or 0)-int(qty)
    if newv < 0: newv=0
    try:
        with _begin(): row.reserved_quantity=newv
        click.echo("OK: unreserved.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("shipment-create")
@click.option("--destination-id", type=int, required=True)
@click.option("--currency", default="USD")
@click.option("--date", "sdate", default="")
@click.option("--items-json", "items_json", required=True)
@click.option("--status", default="DRAFT")
@with_appcontext
def shipment_create(destination_id, currency, sdate, items_json, status):
    try_load=items_json.strip()
    if os.path.exists(try_load):
        with open(try_load,"r",encoding="utf-8") as f: items=json.load(f)
    else:
        items=json.loads(try_load)
    try:
        with _begin():
            sh=Shipment(destination_id=destination_id, currency=currency.upper(), date=_parse_dt(sdate) if sdate else datetime.utcnow(), status=status.strip().upper())
            db.session.add(sh); db.session.flush()
            for it in items:
                db.session.add(ShipmentItem(shipment_id=sh.id, product_id=int(it["product_id"]), warehouse_id=int(it.get("warehouse_id") or destination_id), quantity=int(it["quantity"]), unit_cost=_Q2(it.get("unit_cost",0)), notes=it.get("notes")))
        click.echo(f"OK: shipment {sh.shipment_number or sh.number} created.")
    except Exception as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("shipment-status")
@click.option("--shipment-id", type=int, required=True)
@click.option("--status", type=click.Choice(["DRAFT","IN_TRANSIT","ARRIVED","CANCELLED","CREATED"], case_sensitive=False), required=True)
@with_appcontext
def shipment_status(shipment_id: int, status: str):
    sh=db.session.get(Shipment, shipment_id)
    if not sh: raise click.ClickException("Shipment not found")
    try:
        with _begin(): sh.update_status(status.upper())
        click.echo(f"OK: shipment {shipment_id} -> {status.upper()}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("supplier-settlement-draft")
@click.option("--supplier-id", type=int, required=True)
@click.option("--from", "date_from", required=True)
@click.option("--to", "date_to", required=True)
@click.option("--currency", default="ILS")
@click.option("--mode", type=click.Choice(["ON_RECEIPT","ON_CONSUME"], case_sensitive=False))
@with_appcontext
def supplier_settlement_draft(supplier_id, date_from, date_to, currency, mode):
    df=_parse_dt(date_from); dt=_parse_dt(date_to)
    ss=build_supplier_settlement_draft(supplier_id, df, dt, currency=currency, mode=mode)
    try:
        with _begin(): db.session.add(ss)
        click.echo(f"OK: supplier settlement {ss.code} draft with {len(ss.lines or [])} lines, due={float(ss.total_due or 0):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("supplier-settlement-confirm")
@click.option("--id", "settlement_id", type=int, required=True)
@with_appcontext
def supplier_settlement_confirm(settlement_id: int):
    ss=db.session.get(SupplierSettlement, settlement_id)
    if not ss: raise click.ClickException("Settlement not found")
    try:
        with _begin(): ss.mark_confirmed()
        click.echo(f"OK: supplier settlement {ss.code} confirmed.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("partner-settlement-draft")
@click.option("--partner-id", type=int, required=True)
@click.option("--from", "date_from", required=True)
@click.option("--to", "date_to", required=True)
@click.option("--currency", default="ILS")
@with_appcontext
def partner_settlement_draft(partner_id, date_from, date_to, currency):
    df=_parse_dt(date_from); dt=_parse_dt(date_to)
    ps=build_partner_settlement_draft(partner_id, df, dt, currency=currency)
    try:
        with _begin(): db.session.add(ps)
        click.echo(f"OK: partner settlement {ps.code} draft with {len(ps.lines or [])} lines, due={float(ps.total_due or 0):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("partner-settlement-confirm")
@click.option("--id", "settlement_id", type=int, required=True)
@with_appcontext
def partner_settlement_confirm(settlement_id: int):
    ps=db.session.get(PartnerSettlement, settlement_id)
    if not ps: raise click.ClickException("Settlement not found")
    try:
        with _begin(): ps.mark_confirmed()
        click.echo(f"OK: partner settlement {ps.code} confirmed.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

def _method_enum(v: str): return getattr(PaymentMethod, v.upper()).value if v else PaymentMethod.CASH.value
def _status_enum(v: str): return getattr(PaymentStatus, v.upper()).value if v else PaymentStatus.PENDING.value
def _direction_enum(v: str): return getattr(PaymentDirection, v.upper()).value if v else PaymentDirection.IN.value
def _entity_enum(v: str): return getattr(PaymentEntityType, v.upper()).value if v else PaymentEntityType.CUSTOMER.value

@click.command("payment-create")
@click.option("--direction", default="IN", type=click.Choice(["IN", "OUT"], case_sensitive=False))
@click.option("--entity-type", "entity_type", required=True, type=click.Choice([e.value for e in PaymentEntityType], case_sensitive=False))
@click.option("--target-id", type=int, required=True)
@click.option("--amount", type=float, required=True)
@click.option("--method", default="CASH", type=click.Choice([e.value for e in PaymentMethod], case_sensitive=False))
@click.option("--status", default="COMPLETED", type=click.Choice([e.value for e in PaymentStatus], case_sensitive=False))
@click.option("--currency", default="ILS")
@click.option("--reference", default="")
@click.option("--notes", default="")
@with_appcontext
def payment_create(direction, entity_type, target_id, amount, method, status, currency, reference, notes):
    fields = {
        PaymentEntityType.CUSTOMER.value: "customer_id",
        PaymentEntityType.SUPPLIER.value: "supplier_id",
        PaymentEntityType.PARTNER.value: "partner_id",
        PaymentEntityType.SHIPMENT.value: "shipment_id",
        PaymentEntityType.EXPENSE.value: "expense_id",
        PaymentEntityType.LOAN.value: "loan_settlement_id",
        PaymentEntityType.SALE.value: "sale_id",
        PaymentEntityType.INVOICE.value: "invoice_id",
        PaymentEntityType.PREORDER.value: "preorder_id",
        PaymentEntityType.SERVICE.value: "service_id",
    }
    fk = fields.get(entity_type)
    if not fk:
        raise click.ClickException(f"Unsupported entity-type: {entity_type}")
    try:
        with _begin():
            entity_kwargs = {fk: int(target_id)}
            
            if entity_type == PaymentEntityType.SALE.value and target_id:
                sale = db.session.get(Sale, int(target_id))
                if sale and sale.customer_id:
                    entity_kwargs['customer_id'] = sale.customer_id
            elif entity_type == PaymentEntityType.INVOICE.value and target_id:
                invoice = db.session.get(Invoice, int(target_id))
                if invoice and invoice.customer_id:
                    entity_kwargs['customer_id'] = invoice.customer_id
            elif entity_type == PaymentEntityType.SERVICE.value and target_id:
                service = db.session.get(ServiceRequest, int(target_id))
                if service and service.customer_id:
                    entity_kwargs['customer_id'] = service.customer_id
            elif entity_type == PaymentEntityType.PREORDER.value and target_id:
                preorder = db.session.get(PreOrder, int(target_id))
                if preorder and preorder.customer_id:
                    entity_kwargs['customer_id'] = preorder.customer_id
            elif entity_type == PaymentEntityType.SHIPMENT.value and target_id:
                shipment = db.session.get(Shipment, int(target_id))
                if shipment:
                    if shipment.supplier_id:
                        entity_kwargs['supplier_id'] = shipment.supplier_id
                    if shipment.partner_id:
                        entity_kwargs['partner_id'] = shipment.partner_id
            elif entity_type == PaymentEntityType.EXPENSE.value and target_id:
                expense = db.session.get(Expense, int(target_id))
                if expense:
                    if expense.supplier_id:
                        entity_kwargs['supplier_id'] = expense.supplier_id
                    if expense.partner_id:
                        entity_kwargs['partner_id'] = expense.partner_id
            elif entity_type == PaymentEntityType.LOAN.value and target_id:
                from models import SupplierLoanSettlement
                loan = db.session.get(SupplierLoanSettlement, int(target_id))
                if loan and loan.supplier_id:
                    entity_kwargs['supplier_id'] = loan.supplier_id
            
            p = Payment(
                total_amount=_Q2(amount),
                method=_method_enum(method),
                status=_status_enum(status),
                direction=_direction_enum(direction),
                entity_type=_entity_enum(entity_type),
                currency=currency.upper(),
                reference=reference or None,
                notes=notes or None,
                **entity_kwargs,
            )
            db.session.add(p)
        click.echo(f"OK: payment {p.payment_number} created for {entity_type}={target_id} amount={float(p.total_amount):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(str(e)) from e

@click.command("payment-list")
@click.option("--status", default="")
@click.option("--direction", default="")
@click.option("--entity-type", default="")
@click.option("--limit", type=int, default=100)
@with_appcontext
def payment_list(status, direction, entity_type, limit):
    q=Payment.query
    if status.strip(): q=q.filter(Payment.status==status.strip().upper())
    if direction.strip(): q=q.filter(Payment.direction==direction.strip().upper())
    if entity_type.strip(): q=q.filter(Payment.entity_type==entity_type.strip().upper())
    for p in q.order_by(Payment.id.desc()).limit(limit).all():
        click.echo(f"{p.id:>5} {p.payment_number:<16} {p.payment_date} {getattr(p,'entity_type',''):<10} amt={float(p.total_amount):.2f} {getattr(p,'status','')} {getattr(p,'direction','')} -> {p.entity_label()}")

@click.command("invoice-list")
@click.option("--status", default="")
@click.option("--customer-id", type=int)
@click.option("--limit", type=int, default=100)
@with_appcontext
def invoice_list(status, customer_id, limit):
    q=Invoice.query
    if status.strip(): q=q.filter(Invoice.status==status.strip().upper())
    if customer_id: q=q.filter(Invoice.customer_id==int(customer_id))
    for inv in q.order_by(Invoice.id.desc()).limit(limit).all():
        click.echo(f"{inv.id:>5} {inv.invoice_number or '-':<14} cust={inv.customer_id or '-':<5} total={float(inv.total_amount or 0):.2f} paid={float(inv.total_paid):.2f} due={float(inv.balance_due):.2f} status={inv.status}")

@click.command("invoice-update-status")
@click.option("--id", "invoice_id", type=int, required=True)
@with_appcontext
def invoice_update_status(invoice_id: int):
    inv=db.session.get(Invoice, invoice_id)
    if not inv: raise click.ClickException("Invoice not found")
    try:
        with _begin(): inv.update_status()
        click.echo(f"OK: invoice {invoice_id} status -> {inv.status}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("preorder-create")
@click.option("--product-id", type=int, required=True)
@click.option("--warehouse-id", type=int, required=True)
@click.option("--quantity", type=int, required=True)
@click.option("--customer-id", type=int)
@click.option("--supplier-id", type=int)
@click.option("--partner-id", type=int)
@click.option("--prepaid", type=float, default=0.0)
@click.option("--tax-rate", type=float, default=0.0)
@click.option("--method", default="CASH", type=click.Choice([e.value for e in PaymentMethod], case_sensitive=False))
@with_appcontext
def preorder_create(product_id, warehouse_id, quantity, customer_id, supplier_id, partner_id, prepaid, tax_rate, method):
    if not any([customer_id, supplier_id, partner_id]):
        raise click.ClickException("One of customer-id/supplier-id/partner-id is required")
    try:
        with _begin():
            po = PreOrder(
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=int(quantity),
                customer_id=customer_id,
                supplier_id=supplier_id,
                partner_id=partner_id,
                prepaid_amount=_Q2(prepaid),
                tax_rate=_Q2(tax_rate),
                payment_method=getattr(PaymentMethod, method.upper()).value,
            )
            db.session.add(po)
            db.session.flush()
            if _Q2(prepaid) > 0:
                fk = None
                etype = None
                if customer_id:
                    fk, etype = "customer_id", PaymentEntityType.CUSTOMER.value
                elif supplier_id:
                    fk, etype = "supplier_id", PaymentEntityType.SUPPLIER.value
                elif partner_id:
                    fk, etype = "partner_id", PaymentEntityType.PARTNER.value
                if fk and etype:
                    p = Payment(
                        total_amount=_Q2(prepaid),
                        method=getattr(PaymentMethod, method.upper()).value,
                        status=PaymentStatus.COMPLETED.value,
                        direction=PaymentDirection.IN.value,
                        entity_type=etype,
                        preorder_id=po.id,
                        currency="ILS",
                        reference=f"PreOrder:{po.reference}",
                        **{fk: (customer_id or supplier_id or partner_id)},
                    )
                    db.session.add(p)
        click.echo(f"OK: preorder {po.reference} created.")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(str(e)) from e
@click.command("sr-create")
@click.option("--customer-id", type=int, required=True)
@click.option("--tax-rate", type=float, default=0.0)
@click.option("--discount-total", type=float, default=0.0)
@click.option("--currency", type=str, default="ILS")
@click.option("--status", type=click.Choice([e.value for e in ServiceStatus]), default=ServiceStatus.PENDING.value)
@click.option("--notes", type=str, default=None)
@with_appcontext
def sr_create(customer_id, tax_rate, discount_total, currency, status, notes):
    sr=ServiceRequest(customer_id=customer_id, tax_rate=_Q2(tax_rate), discount_total=_Q2(discount_total), currency=(currency or "ILS").upper(), status=status, notes=notes)
    try:
        with _begin(): db.session.add(sr)
        click.echo(f"OK: service {sr.service_number} created.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("sr-add-part")
@click.option("--service-id", type=int, required=True)
@click.option("--product-id", type=int, required=True)
@click.option("--warehouse-id", type=int, required=True)
@click.option("--quantity", type=int, required=True)
@click.option("--unit-price", type=str, required=True)
@click.option("--discount", type=str, default="0")
@click.option("--tax-rate", type=str, default="0")
@click.option("--partner-id", type=int, default=None)
@click.option("--share-percentage", type=str, default="0")
@click.option("--note", type=str, default=None)
@click.option("--notes", type=str, default=None)
@with_appcontext
def sr_add_part(service_id, product_id, warehouse_id, quantity, unit_price, discount, tax_rate, partner_id, share_percentage, note, notes):
    sr=db.session.get(ServiceRequest, service_id)
    if not sr: raise click.ClickException("ServiceRequest not found")
    part=ServicePart(service_id=sr.id, part_id=product_id, warehouse_id=warehouse_id, quantity=int(quantity), unit_price=_Q2(unit_price), discount=_Q2(discount), tax_rate=_Q2(tax_rate), partner_id=partner_id, share_percentage=_Q2(share_percentage), note=note, notes=notes)
    try:
        with _begin(): db.session.add(part)
        click.echo(f"OK: part {part.id} added to service {sr.service_number or sr.id}.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("sr-add-task")
@click.option("--service-id", type=int, required=True)
@click.option("--description", type=str, required=True)
@click.option("--quantity", type=int, default=1)
@click.option("--unit-price", type=str, required=True)
@click.option("--discount", type=str, default="0")
@click.option("--tax-rate", type=str, default="0")
@click.option("--partner-id", type=int, default=None)
@click.option("--share-percentage", type=str, default="0")
@click.option("--note", type=str, default=None)
@with_appcontext
def sr_add_task(service_id, description, quantity, unit_price, discount, tax_rate, partner_id, share_percentage, note):
    sr=db.session.get(ServiceRequest, service_id)
    if not sr: raise click.ClickException("ServiceRequest not found")
    task=ServiceTask(service_id=sr.id, description=description, quantity=int(quantity), unit_price=_Q2(unit_price), discount=_Q2(discount), tax_rate=_Q2(tax_rate), partner_id=partner_id, share_percentage=_Q2(share_percentage), note=note)
    try:
        with _begin(): db.session.add(task)
        click.echo(f"OK: task {task.id} added to service {sr.service_number or sr.id}.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("sr-recalc")
@click.option("--service-id", type=int, required=True)
@with_appcontext
def sr_recalc(service_id):
    sr = db.session.get(ServiceRequest, service_id)
    if not sr:
        raise click.ClickException("ServiceRequest not found")
    try:
        with _begin():
            sr.updated_at = datetime.utcnow()
            sr.recalc_totals()
        click.echo(f"OK: recalc -> total={float(sr.total_amount or 0):.2f} parts={float(sr.parts_total or 0):.2f} labor={float(sr.labor_total or 0):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(str(e)) from e

@click.command("sr-set-status")
@click.option("--service-id", type=int, required=True)
@click.option("--status", type=click.Choice([e.value for e in ServiceStatus]), required=True)
@click.option("--post-gl/--no-post-gl", default=False)
@with_appcontext
def sr_set_status(service_id, status, post_gl):
    sr = db.session.get(ServiceRequest, service_id)
    if not sr:
        raise click.ClickException("ServiceRequest not found")
    prev = sr.status
    try:
        with _begin():
            sr.status = status
        if post_gl and status == ServiceStatus.COMPLETED.value:
            parts = _D(getattr(sr, "parts_total", 0) or 0)
            labor = _D(getattr(sr, "labor_total", 0) or 0)
            discount = _D(getattr(sr, "discount_total", 0) or 0)
            tax_rate = _D(getattr(sr, "tax_rate", 0) or 0)
            base = parts + labor - discount
            if base < 0:
                base = Decimal("0.00")
            tax = base * (tax_rate / Decimal("100"))
            total = base + tax
            entries = []
            if "AR" in GL_ACCOUNTS:
                entries.append((GL_ACCOUNTS["AR"], float(_Q2(total)), 0.0))
            if "VAT" in GL_ACCOUNTS:
                entries.append((GL_ACCOUNTS["VAT"], 0.0, float(_Q2(tax))))
            if "REV" in GL_ACCOUNTS:
                entries.append((GL_ACCOUNTS["REV"], 0.0, float(_Q2(total - tax))))
            if entries:
                _gl_upsert_batch_and_entries(
                    db.session.connection(),
                    source_type="SERVICE",
                    source_id=sr.id,
                    purpose="SERVICE_COMPLETE",
                    currency=(sr.currency or "ILS").upper(),
                    memo=f"Service {sr.service_number or sr.id} completed",
                    entries=entries,
                    ref=str(sr.service_number or sr.id),
                    entity_type="CUSTOMER",
                    entity_id=sr.customer_id,
                )
        click.echo(f"OK: service {service_id} {prev} -> {status}")
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(str(e)) from e

@click.command("sr-show")
@click.option("--service-id", type=int, required=True)
@with_appcontext
def sr_show(service_id):
    sr=db.session.get(ServiceRequest, service_id)
    if not sr: raise click.ClickException("ServiceRequest not found")
    data={"id":sr.id,"service_number":sr.service_number,"customer_id":sr.customer_id,"status":getattr(sr.status,"value",sr.status),"parts_total":float(sr.parts_total or 0),"labor_total":float(sr.labor_total or 0),"discount_total":float(sr.discount_total or 0),"tax_rate":float(sr.tax_rate or 0),"total_amount":float(sr.total_amount or 0),"currency":sr.currency,"completed_at":sr.completed_at.isoformat() if getattr(sr,"completed_at",None) else None,"parts":[p.to_dict() for p in (sr.parts or [])],"tasks":[t.to_dict() for t in (sr.tasks or [])]}
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))

@click.command("cart-create")
@click.option("--customer-id", type=int, default=None)
@click.option("--session-id", type=str, default=None)
@with_appcontext
def cart_create(customer_id, session_id):
    cart=OnlineCart(customer_id=customer_id, session_id=session_id)
    try:
        with _begin(): db.session.add(cart)
        click.echo(f"OK: cart {cart.cart_id} created.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("cart-add-item")
@click.option("--cart-id", type=int, required=True)
@click.option("--product-id", type=int, required=True)
@click.option("--quantity", type=int, default=1)
@click.option("--price", type=str, required=True)
@with_appcontext
def cart_add_item(cart_id, product_id, quantity, price):
    cart=db.session.get(OnlineCart, cart_id)
    if not cart: raise click.ClickException("Cart not found")
    item=OnlineCartItem(cart_id=cart.id, product_id=product_id, quantity=int(quantity), price=_Q2(price))
    try:
        with _begin(): db.session.add(item)
        click.echo(f"OK: item {item.id} added. subtotal={cart.subtotal} count={cart.item_count}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("order-from-cart")
@click.option("--cart-id", type=int, required=True)
@click.option("--customer-id", type=int, required=True)
@click.option("--warehouse-id", type=int, default=None)
@with_appcontext
def order_from_cart(cart_id, customer_id, warehouse_id):
    cart=db.session.get(OnlineCart, cart_id)
    if not cart: raise click.ClickException("Cart not found")
    order=OnlinePreOrder(customer_id=customer_id, cart_id=cart.id, warehouse_id=warehouse_id)
    try:
        with _begin():
            db.session.add(order); db.session.flush()
            for it in (cart.items or []):
                db.session.add(OnlinePreOrderItem(order_id=order.id, product_id=it.product_id, quantity=it.quantity, price=it.price))
            order.update_totals_and_status()
        click.echo(f"OK: order {order.order_number} total={float(order.total_amount or 0):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("order-set-status")
@click.option("--order-id", type=int, required=True)
@click.option("--status", type=click.Choice(["PENDING","CONFIRMED","FULFILLED","CANCELLED"]), required=True)
@with_appcontext
def order_set_status(order_id, status):
    order=db.session.get(OnlinePreOrder, order_id)
    if not order: raise click.ClickException("Order not found")
    prev=order.status
    try:
        with _begin(): order.status=status
        click.echo(f"OK: order {order_id} {prev} -> {status} total={float(order.total_amount or 0):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("order-add-item")
@click.option("--order-id", type=int, required=True)
@click.option("--product-id", type=int, required=True)
@click.option("--quantity", type=int, default=1)
@click.option("--price", type=str, required=True)
@with_appcontext
def order_add_item(order_id, product_id, quantity, price):
    order=db.session.get(OnlinePreOrder, order_id)
    if not order: raise click.ClickException("Order not found")
    it=OnlinePreOrderItem(order_id=order.id, product_id=product_id, quantity=int(quantity), price=_Q2(price))
    try:
        with _begin(): db.session.add(it); order.update_totals_and_status()
        click.echo(f"OK: item {it.id} added. order_total={float(order.total_amount or 0):.2f} payment_status={order.payment_status}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("onlinepay-create")
@click.option("--order-id", type=int, required=True)
@click.option("--amount", type=str, required=True)
@click.option("--currency", type=str, default="ILS")
@click.option("--method", type=str, default=None)
@click.option("--gateway", type=str, default=None)
@click.option("--status", type=click.Choice(["PENDING","SUCCESS","FAILED","REFUNDED"]), default="PENDING")
@click.option("--card-pan", type=str, default=None)
@click.option("--card-holder", type=str, default=None)
@click.option("--card-expiry", type=str, default=None)
@with_appcontext
def onlinepay_create(order_id, amount, currency, method, gateway, status, card_pan, card_holder, card_expiry):
    order=db.session.get(OnlinePreOrder, order_id)
    if not order: raise click.ClickException("Order not found")
    p=OnlinePayment(order_id=order.id, amount=_Q2(amount), currency=(currency or "ILS").upper(), method=method, gateway=gateway, status=status)
    if card_pan or card_holder or card_expiry: p.set_card_details(card_pan, card_holder, card_expiry, validate=True)
    p.payment_ref=f"OP-{uuid.uuid4().hex[:10].upper()}"
    try:
        with _begin(): db.session.add(p); db.session.flush(); order.update_totals_and_status()
        click.echo(f"OK: payment {p.payment_ref} status={p.status} balance_due={order.balance_due}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("onlinepay-decrypt-card")
@click.option("--payment-id", type=int, required=True)
@with_appcontext
def onlinepay_decrypt_card(payment_id):
    p=db.session.get(OnlinePayment, payment_id)
    if not p: raise click.ClickException("Payment not found")
    num=p.decrypt_card_number(); click.echo(num or "")

@click.command("expense-create")
@click.option("--amount", type=str, required=True)
@click.option("--type-id", type=int, required=True)
@click.option("--currency", type=str, default="ILS")
@click.option("--payee-type", type=click.Choice(["EMPLOYEE","SUPPLIER","UTILITY","OTHER"]), default="OTHER")
@click.option("--payee-entity-id", type=int, default=None)
@click.option("--payee-name", type=str, default=None)
@click.option("--payment-method", type=click.Choice(["cash","cheque","bank","card","online","other"]), default="cash")
@click.option("--description", type=str, default=None)
@click.option("--notes", type=str, default=None)
@with_appcontext
def expense_create(amount, type_id, currency, payee_type, payee_entity_id, payee_name, payment_method, description, notes):
    ex=Expense(amount=_Q2(amount), type_id=type_id, currency=(currency or "ILS").upper(), payee_type=payee_type, payee_entity_id=payee_entity_id, payee_name=payee_name, payment_method=payment_method, description=description, notes=notes, date=datetime.utcnow())
    try:
        with _begin(): db.session.add(ex)
        click.echo(f"OK: expense {ex.id} amount={float(ex.amount):.2f} balance={ex.balance:.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("expense-pay")
@click.option("--expense-id", type=int, required=True)
@click.option("--amount", type=str, required=True)
@click.option("--method", type=click.Choice(["cash","cheque","bank","card","online","other"]), default="cash")
@click.option("--currency", type=str, default="ILS")
@with_appcontext
def expense_pay(expense_id, amount, method, currency):
    ex=db.session.get(Expense, expense_id)
    if not ex: raise click.ClickException("Expense not found")
    amt=_Q2(amount)
    p=Payment(direction=PaymentDirection.OUT.value, entity_type=PaymentEntityType.EXPENSE.value, expense_id=ex.id, supplier_id=getattr(ex, 'supplier_id', None), partner_id=getattr(ex, 'partner_id', None), total_amount=amt, currency=(currency or "ILS").upper(), method=method.lower(), status=PaymentStatus.COMPLETED.value, reference=f"EXP-{ex.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    try:
        with _begin(): db.session.add(p)
        click.echo(f"OK: expense paid. payment_id={p.id} balance={ex.balance:.2f} is_paid={ex.is_paid}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-adjustment-create")
@click.option("--warehouse-id", type=int, required=True)
@click.option("--reason", type=click.Choice(["DAMAGED","STORE_USE"]), required=True)
@click.option("--notes", type=str, default=None)
@with_appcontext
def stock_adjustment_create(warehouse_id, reason, notes):
    adj=StockAdjustment(warehouse_id=warehouse_id, reason=reason, notes=notes)
    try:
        with _begin(): db.session.add(adj)
        click.echo(f"OK: adjustment {adj.id} created.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-adjustment-add-item")
@click.option("--adjustment-id", type=int, required=True)
@click.option("--product-id", type=int, required=True)
@click.option("--quantity", type=int, required=True)
@click.option("--unit-cost", type=str, required=True)
@with_appcontext
def stock_adjustment_add_item(adjustment_id, product_id, quantity, unit_cost):
    adj=db.session.get(StockAdjustment, adjustment_id)
    if not adj: raise click.ClickException("Adjustment not found")
    it=StockAdjustmentItem(adjustment_id=adj.id, product_id=product_id, quantity=int(quantity), unit_cost=_Q2(unit_cost))
    try:
        with _begin():
            db.session.add(it); db.session.flush()
            total=Decimal("0")
            for x in (adj.items or []): total += _D(x.quantity or 0)*_D(x.unit_cost or 0)
            adj.total_cost=_Q2(total)
        click.echo(f"OK: item {it.id} added. total_cost={float(adj.total_cost):.2f}")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("stock-adjustment-finalize")
@click.option("--adjustment-id", type=int, required=True)
@click.option("--expense-type-id", type=int, required=True)
@with_appcontext
def stock_adjustment_finalize(adjustment_id, expense_type_id):
    adj=db.session.get(StockAdjustment, adjustment_id)
    if not adj: raise click.ClickException("Adjustment not found")
    if float(adj.total_cost or 0) <= 0: raise click.ClickException("No total_cost to finalize")
    ex=Expense(amount=_Q2(adj.total_cost or 0), type_id=expense_type_id, currency="ILS", stock_adjustment_id=adj.id, description=f"Stock Adjustment {adj.reason} #{adj.id}", date=datetime.utcnow(), payment_method="other")
    try:
        with _begin(): db.session.add(ex)
        click.echo(f"OK: expense {ex.id} created for adjustment.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("gl-seed-accounts")
@with_appcontext
def gl_seed_accounts():
    created, updated = [], []
    mapping=[("1100_AR","Accounts Receivable"),("4000_SALES","Sales Revenue"),("2100_VAT_PAYABLE","VAT Payable"),("1000_CASH","Cash on Hand"),("1010_BANK","Bank"),("1020_CARD_CLEARING","Card Clearing"),("2000_AP","Accounts Payable"),("5000_EXPENSES","Expenses"),("1205_INV_EXCHANGE","Inventory Exchange"),("5105_COGS_EXCHANGE","COGS Exchange")]
    with _begin():
        for code,name in mapping:
            acc=db.session.query(Account).filter_by(code=code).one_or_none()
            if acc:
                if (acc.is_active!=True) or (acc.name!=name):
                    acc.name=name; acc.is_active=True; updated.append(code)
            else:
                acc=Account(code=code, name=name, type=("ASSET" if code.startswith(("1","12")) else "LIABILITY" if code.startswith("2") else "REVENUE" if code.startswith("4") else "EXPENSE"), is_active=True)
                db.session.add(acc); created.append(code)
    click.echo(json.dumps({"created":created,"updated":updated}, ensure_ascii=False))

@click.command("gl-batches")
@click.option("--limit", type=int, default=20)
@with_appcontext
def gl_list_batches(limit):
    rows=(db.session.query(GLBatch).order_by(GLBatch.created_at.desc()).limit(limit).all())
    out=[{"id":r.id,"code":r.code,"status":getattr(r.status,"value",r.status),"source":f"{r.source_type}:{r.source_id}","purpose":r.purpose,"currency":r.currency,"posted_at":r.posted_at} for r in rows]
    click.echo(json.dumps(out, default=str, ensure_ascii=False))

@click.command("gl-entries")
@click.option("--batch-id", type=int, required=True)
@with_appcontext
def gl_list_entries(batch_id):
    rows=(db.session.query(GLEntry).filter(GLEntry.batch_id==batch_id).order_by(GLEntry.id.asc()).all())
    out=[{"id":e.id,"account":e.account,"debit":float(e.debit or 0),"credit":float(e.credit or 0),"currency":e.currency,"ref":e.ref} for e in rows]
    click.echo(json.dumps(out, ensure_ascii=False))

@click.command("note-add")
@click.option("--entity-type", type=str, required=True)
@click.option("--entity-id", type=str, required=True)
@click.option("--content", type=str, required=True)
@click.option("--priority", type=click.Choice(["LOW","MEDIUM","HIGH","URGENT"]), default="MEDIUM")
@click.option("--pin/--no-pin", default=False)
@with_appcontext
def note_add(entity_type, entity_id, content, priority, pin):
    n=Note(entity_type=entity_type.strip().upper(), entity_id=str(entity_id), content=content.strip(), priority=priority, is_pinned=bool(pin))
    try:
        with _begin(): db.session.add(n)
        click.echo(f"OK: note {n.id} added.")
    except SQLAlchemyError as e:
        db.session.rollback(); raise click.ClickException(str(e)) from e

@click.command("note-list")
@click.option("--entity-type", type=str, required=True)
@click.option("--entity-id", type=str, required=True)
@with_appcontext
def note_list(entity_type, entity_id):
    rows=(db.session.query(Note).filter(Note.entity_type==entity_type.strip().upper(), Note.entity_id==str(entity_id)).order_by(Note.is_pinned.desc(), Note.created_at.desc()).all())
    out=[r.to_dict() for r in rows]
    click.echo(json.dumps(out, ensure_ascii=False, default=str))

@click.command("audit-tail")
@click.option("--limit", type=int, default=50)
@with_appcontext
def audit_tail(limit):
    rows=(db.session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all())
    out=[{"id":r.id,"time":r.created_at.isoformat() if r.created_at else None,"model":r.model_name,"record_id":r.record_id,"action":r.action,"user_id":r.user_id,"customer_id":r.customer_id,"ip":r.ip_address} for r in rows]
    click.echo(json.dumps(out, ensure_ascii=False))

@click.command("currency-balance")
@click.option("--entity-type", type=str, required=True, help="نوع الكيان (CUSTOMER, SUPPLIER, PARTNER)")
@click.option("--entity-id", type=int, required=True, help="معرف الكيان")
@with_appcontext
def currency_balance(entity_type, entity_id):
    """حساب رصيد الكيان بالشيكل"""
    try:
        balance = get_entity_balance_in_ils(entity_type.upper(), entity_id)
        click.echo(f"الرصيد بالشيكل: {balance:,.2f} شيكل")
    except Exception as e:
        click.echo(f"خطأ: {e}")

@click.command("currency-validate")
@click.option("--entity-type", type=str, required=True, help="نوع الكيان (CUSTOMER, SUPPLIER, PARTNER)")
@click.option("--entity-id", type=int, required=True, help="معرف الكيان")
@with_appcontext
def currency_validate(entity_type, entity_id):
    """التحقق من اتساق العملات"""
    try:
        result = validate_currency_consistency(entity_type.upper(), entity_id)
        if result['is_consistent']:
            click.echo("✅ الحسابات متسقة")
        else:
            click.echo("❌ الحسابات غير متسقة")
            click.echo(f"الرصيد الجديد: {result['new_balance']:,.2f}")
            click.echo(f"الرصيد القديم: {result['old_balance']:,.2f}")
            click.echo(f"الفرق: {result['difference']:,.2f}")
    except Exception as e:
        click.echo(f"خطأ: {e}")

@click.command("currency-report")
@click.option("--entity-type", type=str, required=True, help="نوع الكيان (CUSTOMER, SUPPLIER, PARTNER)")
@with_appcontext
def currency_report(entity_type):
    """تقرير الأرصدة بالشيكل"""
    try:
        from reports import customer_balance_report_ils, supplier_balance_report_ils, partner_balance_report_ils

        if entity_type.upper() == "CUSTOMER":
            report = customer_balance_report_ils()
        elif entity_type.upper() == "SUPPLIER":
            report = supplier_balance_report_ils()
        elif entity_type.upper() == "PARTNER":
            report = partner_balance_report_ils()
        else:
            click.echo("نوع الكيان غير مدعوم")
            return

        if 'error' in report:
            click.echo(f"خطأ: {report['error']}")
            return

        click.echo(f"إجمالي الأرصدة: {report['formatted_total']}")

        # تحديد نوع الكيان والبيانات المناسبة
        if entity_type.upper() == 'CUSTOMER':
            count_key = 'total_customers'
            entities_key = 'customers'
            name_key = 'customer_name'
        elif entity_type.upper() == 'SUPPLIER':
            count_key = 'total_suppliers'
            entities_key = 'suppliers'
            name_key = 'supplier_name'
        else:  # PARTNER
            count_key = 'total_partners'
            entities_key = 'partners'
            name_key = 'partner_name'

        click.echo(f"عدد الكيانات: {report[count_key]}")

        # عرض تفاصيل أول 10 كيانات
        entities = report[entities_key]
        for entity in entities[:10]:
            name = entity[name_key]
            balance = entity['formatted_balance']
            click.echo(f"- {name}: {balance}")

        if len(entities) > 10:
            click.echo(f"... و {len(entities) - 10} كيان آخر")

    except Exception as e:
        click.echo(f"خطأ: {e}")

@click.command("currency-health")
@with_appcontext
def currency_health():
    """فحص صحة نظام العملات مع السيرفرات العالمية"""
    try:
        from models import Currency, ExchangeRate, fx_rate, convert_amount, get_fx_rate_with_fallback
        from datetime import datetime

        click.echo("=== فحص صحة نظام العملات ===")
        click.echo()

        # فحص العملات النشطة
        active_currencies = Currency.query.filter_by(is_active=True).count()
        click.echo(f"✅ العملات النشطة: {active_currencies}")

        # فحص أسعار الصرف
        total_rates = ExchangeRate.query.filter_by(is_active=True).count()
        click.echo(f"✅ أسعار الصرف: {total_rates}")

        # فحص سعر صرف تجريبي مع معلومات المصدر
        try:
            rate_info = get_fx_rate_with_fallback("USD", "ILS")
            if rate_info['success']:
                source_text = "محلي" if rate_info['source'] == "local" else "عالمي"
                click.echo(f"✅ سعر USD/ILS: {rate_info['rate']} (مصدر: {source_text})")
            else:
                click.echo(f"❌ خطأ في سعر USD/ILS: {rate_info.get('error', 'غير معروف')}")
        except Exception as e:
            click.echo(f"❌ خطأ في سعر USD/ILS: {e}")

        # فحص تحويل تجريبي
        try:
            converted = convert_amount(100, "USD", "ILS")
            click.echo(f"✅ تحويل 100 USD إلى ILS: {converted}")
        except Exception as e:
            click.echo(f"❌ خطأ في التحويل: {e}")

        click.echo()
        click.echo("🎉 فحص النظام مكتمل!")

    except Exception as e:
        click.echo(f"خطأ: {e}")

@click.command("currency-update")
@with_appcontext
def currency_update():
    """تحديث أسعار الصرف من السيرفرات العالمية"""
    try:
        from models import auto_update_missing_rates

        click.echo("=== تحديث أسعار الصرف ===")
        click.echo()

        result = auto_update_missing_rates()

        if result['success']:
            click.echo(f"✅ {result['message']}")
            click.echo(f"📊 تم تحديث {result['updated_rates']} سعر صرف")
        else:
            click.echo(f"❌ {result['message']}")
            if 'error' in result:
                click.echo(f"🔍 تفاصيل الخطأ: {result['error']}")

    except Exception as e:
        click.echo(f"خطأ: {e}")

@click.command("currency-test")
@click.option("--base", type=str, default="USD", help="العملة الأساسية")
@click.option("--quote", type=str, default="ILS", help="العملة المقابلة")
@with_appcontext
def currency_test(base, quote):
    """اختبار سعر الصرف مع معلومات المصدر"""
    try:
        from models import get_fx_rate_with_fallback, convert_amount

        click.echo(f"=== اختبار سعر الصرف {base}/{quote} ===")
        click.echo()

        # اختبار الحصول على السعر
        rate_info = get_fx_rate_with_fallback(base, quote)

        if rate_info['success']:
            source_text = "محلي (مدخل من الادمن)" if rate_info['source'] == "local" else "عالمي (من السيرفرات)"
            click.echo(f"✅ السعر: {rate_info['rate']}")
            click.echo(f"📡 المصدر: {source_text}")
            click.echo(f"⏰ الوقت: {rate_info['timestamp']}")

            # اختبار التحويل
            try:
                converted = convert_amount(100, base, quote)
                click.echo(f"💰 تحويل 100 {base} = {converted} {quote}")
            except Exception as e:
                click.echo(f"❌ خطأ في التحويل: {e}")
        else:
            click.echo(f"❌ فشل في الحصول على السعر: {rate_info.get('error', 'غير معروف')}")

    except Exception as e:
        click.echo(f"خطأ: {e}")

        # التحقق من الموردين
        suppliers = db.session.query(Supplier).all()
        click.echo(f"عدد الموردين: {len(suppliers)}")

        click.echo("✅ نظام العملات يعمل بشكل طبيعي")

    except Exception as e:
        click.echo(f"❌ خطأ في النظام: {e}")

@click.command('create-superadmin', help="إنشاء مستخدم Super Admin")
@with_appcontext
def create_superadmin():
    """إنشاء مستخدم Super Admin بصلاحيات كاملة"""
    from werkzeug.security import generate_password_hash

    email = click.prompt("البريد الإلكتروني", type=str)
    username = click.prompt("اسم المستخدم", type=str)
    password = click.prompt("كلمة المرور", type=str, hide_input=True)
    password_confirm = click.prompt("تأكيد كلمة المرور", type=str, hide_input=True)

    if password != password_confirm:
        click.echo(click.style("كلمة المرور غير متطابقة", fg="red"))
        return

    # التحقق من وجود المستخدم
    if User.query.filter_by(email=email).first():
        click.echo(click.style(f"المستخدم {email} موجود بالفعل", fg="yellow"))
        return

    # البحث عن دور Super Admin أو إنشاؤه
    super_role = Role.query.filter_by(slug="super_admin").first()
    if not super_role:
        super_role = Role(
            name="Super Admin",
            slug="super_admin",
            description="صلاحيات كاملة للنظام"
        )
        db.session.add(super_role)
        db.session.flush()

    # إنشاء المستخدم
    user = User(
        email=email,
        username=username,
        password_hash=generate_password_hash(password),
        role_id=super_role.id,
        is_active=True,
        email_confirmed=True
    )

    try:
        db.session.add(user)
        db.session.commit()
        click.echo(click.style(f"✅ تم إنشاء مستخدم Super Admin: {email}", fg="green"))
    except Exception as e:
        db.session.rollback()
        click.echo(click.style(f"❌ خطأ: {str(e)}", fg="red"))

@click.command('optimize-db', help="تحسين أداء قاعدة البيانات")
@with_appcontext
def optimize_db():
    """تحسين أداء قاعدة البيانات بإنشاء الفهارس وتحليل الجداول"""
    try:
        from sqlalchemy import text

        # قائمة الفهارس الموصى بها
        recommended_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)",
            "CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)",
            "CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)",
            "CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date)",
            "CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id)",
            "CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date)",
            "CREATE INDEX IF NOT EXISTS idx_payments_entity ON payments(entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_service_customer ON service_requests(customer_id)",
            "CREATE INDEX IF NOT EXISTS idx_service_status ON service_requests(status)",
        ]

        created = 0
        for idx_sql in recommended_indexes:
            try:
                db.session.execute(text(idx_sql))
                created += 1
            except Exception:
                pass

        db.session.commit()

        # تحليل قاعدة البيانات
        try:
            db.session.execute(text("ANALYZE"))
            db.session.commit()
        except Exception:
            pass

        click.echo(click.style(f"✅ اكتمل تحسين قاعدة البيانات: تم إنشاء {created} فهرس", fg="green"))
    except Exception as e:
        click.echo(click.style(f"❌ خطأ: {str(e)}", fg="red"))

@click.command("workflow-check-timeouts")
@with_appcontext
def workflow_check_timeouts():
    """فحص حالات الـ Workflows المتأخرة وتنفيذ التصعيد وفق القواعد المعرفة."""
    try:
        from services.workflow_engine import WorkflowEngine
        WorkflowEngine.check_timeouts()
        click.echo("✅ تم فحص الـ Workflows المتأخرة وتنفيذ التصعيد (إن وجد)")
    except Exception as e:
        click.echo(click.style(f"❌ خطأ أثناء فحص الـ Workflows: {str(e)}", fg="red"))

def register_cli(app) -> None:
    commands=[
        seed_roles, sync_permissions, list_permissions, list_roles, role_add_perms, create_role, export_rbac,
        create_user, user_set_password, user_activate, user_assign_role, list_users, list_customers,
        seed_expense_types, expense_type_cmd, seed_palestine_cmd, seed_all, clear_rbac_caches,
        wh_create, wh_list, wh_stock, product_create, product_find, product_stock, product_set_price,
        stock_transfer, stock_exchange, stock_reserve, stock_unreserve, shipment_create, shipment_status,
        supplier_settlement_draft, supplier_settlement_confirm, partner_settlement_draft, partner_settlement_confirm,
        payment_create, payment_list, invoice_list, invoice_update_status, preorder_create,
        sr_create, sr_add_part, sr_add_task, sr_recalc, sr_set_status, sr_show, 
        cart_create, cart_add_item, order_from_cart, order_set_status, order_add_item,
        onlinepay_create, onlinepay_decrypt_card, expense_create, expense_pay,
        stock_adjustment_create, stock_adjustment_add_item, stock_adjustment_finalize,
        gl_seed_accounts, gl_list_batches, gl_list_entries,
        note_add, note_list, audit_tail,
        currency_balance, currency_validate, currency_report, currency_health, currency_update, currency_test,
        create_superadmin,
        optimize_db,
        seed_employees, seed_salaries, seed_expenses_demo, seed_branches,
        workflow_check_timeouts
    ]
    for cmd in commands: app.cli.add_command(cmd)
