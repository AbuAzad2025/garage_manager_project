from __future__ import annotations

import os
import click
from flask.cli import with_appcontext
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Role, Permission
from utils import clear_role_permission_cache, clear_users_cache_by_role

BACKUP_CODE = "backup_database"
RESTORE_CODE = "restore_database"
LEGACY_CODE = "backup_restore"


def _get_or_create_role(name: str) -> Role:
    r = Role.query.filter(func.lower(Role.name) == name.lower()).first()
    if not r:
        r = Role(name=name)
        db.session.add(r)
        db.session.flush()
    return r


def _find_permission(code: str) -> Permission | None:
    p = Permission.query.filter_by(code=code).first()
    if p:
        return p
    return Permission.query.filter(func.lower(Permission.name) == code.lower()).first()


def _ensure_permission(code: str, name: str) -> Permission:
    p = _find_permission(code)
    if p:
        if not p.code:
            p.code = code
        if not p.name:
            p.name = name
        return p
    p = Permission(code=code, name=name)
    db.session.add(p)
    db.session.flush()
    return p


def _remove_perm_from_role(role: Role, code: str) -> bool:
    removed = False
    target = (code or "").strip().lower()
    for p in list(role.permissions or []):
        if (p.code or p.name or "").strip().lower() == target:
            role.permissions.remove(p)
            removed = True
    return removed


@click.command("seed-roles")
@click.option("--force", is_flag=True, help="تجاوز فحص البيئة والتأكيد.")
@click.option("--dry-run", is_flag=True, help="اعرض التغييرات بدون تنفيذ.")
@with_appcontext
def seed_roles(force: bool, dry_run: bool) -> None:
    if not force and os.getenv("ALLOW_SEED_ROLES") != "1":
        raise click.ClickException("الأمر seed-roles مُعطّل. فعّل ALLOW_SEED_ROLES=1 أو استخدم --force.")

    is_prod = (os.getenv("FLASK_ENV") == "production") or (os.getenv("ENVIRONMENT") == "production") or (os.getenv("DEBUG") not in ("1", "true", "True"))
    if is_prod and not force:
        if not click.confirm("أنت في بيئة إنتاج. هل تريد المتابعة؟", default=False):
            click.echo("تم الإلغاء.")
            return

    affected_roles: set[int] = set()

    p_backup: Permission = _ensure_permission(BACKUP_CODE, "Backup database")
    p_restore: Permission = _ensure_permission(RESTORE_CODE, "Restore database")

    super_admin: Role = _get_or_create_role("super_admin")
    manager: Role = _get_or_create_role("manager")

    legacy = _find_permission(LEGACY_CODE)
    legacy_used_by = []
    if legacy:
        for r in Role.query.all():
            if legacy in (r.permissions or []):
                legacy_used_by.append(r.id)

    planned_msgs = []

    if legacy:
        planned_msgs.append(f"سيتم إزالة صلاحية legacy '{LEGACY_CODE}' واستبدالها ({len(legacy_used_by)} دور متأثر).")

    if p_backup not in (super_admin.permissions or []):
        planned_msgs.append("إضافة backup_database إلى super_admin.")
    if p_restore not in (super_admin.permissions or []):
        planned_msgs.append("إضافة restore_database إلى super_admin.")

    if any(_remove_perm_from_role(manager, RESTORE_CODE) for _ in [0]):
        planned_msgs.append("إزالة restore_database من manager.")
    if p_backup not in (manager.permissions or []):
        planned_msgs.append("إضافة backup_database إلى manager.")

    if dry_run:
        if planned_msgs:
            click.echo("التغييرات المخطط لها:")
            for m in planned_msgs:
                click.echo(f" - {m}")
        else:
            click.echo("لا توجد تغييرات مطلوبة. كل شيء متزامن.")
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

            if p_backup not in (super_admin.permissions or []):
                super_admin.permissions.append(p_backup)
                affected_roles.add(super_admin.id)
            if p_restore not in (super_admin.permissions or []):
                super_admin.permissions.append(p_restore)
                affected_roles.add(super_admin.id)

            if _remove_perm_from_role(manager, RESTORE_CODE):
                affected_roles.add(manager.id)
            if p_backup not in (manager.permissions or []):
                manager.permissions.append(p_backup)
                affected_roles.add(manager.id)
    except SQLAlchemyError as e:
        db.session.rollback()
        raise click.ClickException(f"فشل الحفظ: {e}") from e

    for rid in affected_roles:
        try:
            clear_role_permission_cache(rid)
        except Exception:
            pass
        try:
            clear_users_cache_by_role(rid)
        except Exception:
            pass

    click.echo("✅ Seed done: roles & permissions synchronized.")


def register_cli(app) -> None:
    app.cli.add_command(seed_roles)
