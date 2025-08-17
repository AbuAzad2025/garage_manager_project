# cli.py
"""
أوامر CLI لمزامنة الأدوار والصلاحيات الخاصة بالنسخ/الاستعادة.
- يثبت صلاحيتين رسميتين: backup_database و restore_database
- يزيل الصلاحية القديمة (إن وُجدت): backup_restore من كل الأدوار ثم يحذفها
- يمنح super_admin الصلاحيتين
- يمنح manager صلاحية النسخ فقط ويمنع عنه الاستعادة
"""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from extensions import db
from models import Role, Permission


BACKUP_CODE: str = "backup_database"
RESTORE_CODE: str = "restore_database"
LEGACY_CODE: str = "backup_restore"  # لإصدارات قديمة إن وُجدت


def _get_or_create(model, **kw):
    """إحضار سجل أو إنشاؤه إن لم يوجد (idempotent)."""
    obj = model.query.filter_by(**kw).first()
    if not obj:
        obj = model(**kw)
        db.session.add(obj)
        # flush لضمان وجود id قبل إدارة العلاقات
        db.session.flush()
    return obj


def _ensure_permission(code: str, name: str) -> Permission:
    """تثبيت صلاحية بالرمز والاسم."""
    p: Permission = _get_or_create(Permission, code=code)
    if not getattr(p, "name", None):
        p.name = name
    return p


def _remove_perm_from_role(role: Role, code: str) -> None:
    """إزالة صلاحية برمز محدد من دور معيّن (آمنة على التكرار)."""
    for p in list(role.permissions):
        if getattr(p, "code", None) == code:
            role.permissions.remove(p)


@click.command("seed-roles")
@with_appcontext
def seed_roles() -> None:
    """
    مزامنة الأدوار والصلاحيات الأساسية الخاصة بالنسخ/الاستعادة.
    للتشغيل:
        flask seed-roles
    """
    # 1) الصلاحيات الرسمية
    p_backup: Permission = _ensure_permission(BACKUP_CODE, "Backup database")
    p_restore: Permission = _ensure_permission(RESTORE_CODE, "Restore database")

    # 2) الأدوار الأساسية
    super_admin: Role = _get_or_create(Role, name="super_admin")
    manager: Role = _get_or_create(Role, name="manager")

    # 3) تنظيف الصلاحية القديمة (إن وُجدت)
    legacy = Permission.query.filter_by(code=LEGACY_CODE).first()
    if legacy:
        for r in Role.query.all():
            _remove_perm_from_role(r, LEGACY_CODE)
        db.session.delete(legacy)

    # 4) super_admin: يمتلك النسخ والاستعادة
    if p_backup not in super_admin.permissions:
        super_admin.permissions.append(p_backup)
    if p_restore not in super_admin.permissions:
        super_admin.permissions.append(p_restore)

    # 5) manager: يمتلك النسخ فقط، وتُزال منه الاستعادة إن تسرّبت
    _remove_perm_from_role(manager, RESTORE_CODE)
    if p_backup not in manager.permissions:
        manager.permissions.append(p_backup)

    # 6) حفظ
    try:
        db.session.commit()
    except Exception as e:  # نظافة عند الخطأ
        db.session.rollback()
        raise click.ClickException(f"فشل الحفظ: {e}") from e

    click.echo("✅ Seed done: roles & permissions synchronized.")


# اختيارية: تسهيل التسجيل من create_app()
def register_cli(app) -> None:
    """استدعِها من create_app لتسجيل الأوامر بسهولة."""
    app.cli.add_command(seed_roles)
