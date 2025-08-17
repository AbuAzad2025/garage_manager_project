from __future__ import annotations

import click
from flask.cli import with_appcontext
from sqlalchemy import func

from extensions import db
from models import Role, Permission
from utils import clear_role_permission_cache, clear_users_cache_by_role

BACKUP_CODE = "backup_database"
RESTORE_CODE = "restore_database"
LEGACY_CODE = "backup_restore"


def _get_or_create_role(name: str) -> Role:
    r = Role.query.filter_by(name=name).first()
    if not r:
        r = Role(name=name)
        db.session.add(r)
        db.session.flush()
    return r


def _ensure_permission(code: str, name: str) -> Permission:
    p = Permission.query.filter_by(code=code).first()
    if p:
        if not p.name:
            p.name = name
        return p
    p = Permission.query.filter(func.lower(Permission.name) == name.lower()).first()
    if p:
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
    target = code.strip().lower()
    for p in list(role.permissions):
        if (p.code or "").strip().lower() == target:
            role.permissions.remove(p)
            removed = True
    return removed


@click.command("seed-roles")
@with_appcontext
def seed_roles() -> None:
    affected_roles: set[int] = set()

    p_backup: Permission = _ensure_permission(BACKUP_CODE, "Backup database")
    p_restore: Permission = _ensure_permission(RESTORE_CODE, "Restore database")

    super_admin: Role = _get_or_create_role("super_admin")
    manager: Role = _get_or_create_role("manager")

    legacy = Permission.query.filter_by(code=LEGACY_CODE).first()
    if legacy:
        for r in Role.query.all():
            if legacy in r.permissions:
                r.permissions.remove(legacy)
                affected_roles.add(r.id)
        db.session.delete(legacy)

    if p_backup not in super_admin.permissions:
        super_admin.permissions.append(p_backup)
        affected_roles.add(super_admin.id)
    if p_restore not in super_admin.permissions:
        super_admin.permissions.append(p_restore)
        affected_roles.add(super_admin.id)

    if _remove_perm_from_role(manager, RESTORE_CODE):
        affected_roles.add(manager.id)
    if p_backup not in manager.permissions:
        manager.permissions.append(p_backup)
        affected_roles.add(manager.id)

    try:
        db.session.commit()
    except Exception as e:
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
