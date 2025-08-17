from flask import Blueprint, flash, redirect, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
import re
from extensions import db
from forms import PermissionForm
from models import Permission, User
from utils import permission_required, clear_user_permission_cache, clear_role_permission_cache

permissions_bp = Blueprint('permissions', __name__, template_folder='templates/permissions')
_RESERVED_CODES = {"backup_database", "restore_database"}

def _get_or_404(model, ident, options=None):
    q = db.session.query(model)
    if options:
        for opt in options:
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

def _normalize_code(s):
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or None

def _unique_violation(name, code, exclude_id=None):
    name_l = (name or "").strip().lower()
    code_l = (code or "").strip().lower() if code else None
    q = Permission.query
    if exclude_id:
        q = q.filter(Permission.id != exclude_id)
    by_name = q.filter(func.lower(Permission.name) == name_l).first()
    if by_name:
        return "هذا الاسم مستخدم بالفعل!"
    if code_l:
        q2 = Permission.query
        if exclude_id:
            q2 = q2.filter(Permission.id != exclude_id)
        by_code = q2.filter(
            Permission.code.isnot(None),
            func.lower(Permission.code) == code_l
        ).first()
        if by_code:
            return "هذا الكود مستخدم بالفعل!"
    return None

def _clear_all_users_cache():
    for (user_id,) in User.query.with_entities(User.id).all():
        clear_user_permission_cache(user_id)

def _clear_roles_cache_for_permission(perm):
    try:
        for r in getattr(perm, "roles", []) or []:
            clear_role_permission_cache(r.id)
    except Exception:
        pass

@permissions_bp.route('/', methods=['GET'], endpoint='list')
@login_required
@permission_required('manage_permissions')
def list_permissions():
    permissions = Permission.query.order_by(func.lower(Permission.name)).all()
    return render_template('permissions/list.html', permissions=permissions)

@permissions_bp.route('/create', methods=['GET', 'POST'], endpoint='create')
@login_required
@permission_required('manage_permissions')
def create_permission():
    form = PermissionForm()
    if form.validate_on_submit():
        code = _normalize_code(getattr(form, "code", None) and form.code.data) or _normalize_code(form.name.data)
        msg = _unique_violation(form.name.data, code)
        if msg:
            flash(msg, 'danger')
        else:
            try:
                perm = Permission(name=form.name.data.strip(), code=code)
                db.session.add(perm)
                db.session.commit()
                _clear_all_users_cache()
                _clear_roles_cache_for_permission(perm)
                flash('تم إضافة الإذن بنجاح.', 'success')
                return redirect(url_for('permissions.list'))
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f'خطأ أثناء الإضافة: {e}', 'danger')
    return render_template('permissions/form.html', form=form)

@permissions_bp.route('/<int:permission_id>/edit', methods=['GET', 'POST'], endpoint='edit')
@login_required
@permission_required('manage_permissions')
def edit_permission(permission_id):
    perm = _get_or_404(Permission, permission_id)
    form = PermissionForm(obj=perm)
    if form.validate_on_submit():
        incoming_code = _normalize_code(getattr(form, "code", None) and form.code.data) or _normalize_code(form.name.data)
        if perm.code in _RESERVED_CODES:
            incoming_code = perm.code
        msg = _unique_violation(form.name.data, incoming_code, exclude_id=perm.id)
        if msg:
            flash(msg, 'danger')
        else:
            try:
                perm.name = form.name.data.strip()
                perm.code = incoming_code
                db.session.commit()
                _clear_all_users_cache()
                _clear_roles_cache_for_permission(perm)
                flash('تم تحديث الإذن.', 'success')
                return redirect(url_for('permissions.list'))
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f'خطأ أثناء التحديث: {e}', 'danger')
    return render_template('permissions/form.html', form=form, perm=perm)

@permissions_bp.route('/<int:permission_id>/delete', methods=['POST'], endpoint='delete')
@login_required
@permission_required('manage_permissions')
def delete_permission(permission_id):
    perm = _get_or_404(Permission, permission_id)
    if (perm.code and perm.code in _RESERVED_CODES) or (perm.name and _normalize_code(perm.name) in _RESERVED_CODES):
        flash('لا يمكن حذف صلاحيات النظام الحرِجة.', 'danger')
        return redirect(url_for('permissions.list'))
    try:
        used_by_roles = bool(getattr(perm, "roles", []) or [])
    except Exception:
        used_by_roles = False
    try:
        used_by_users = perm.users_extra.count() > 0
    except Exception:
        used_by_users = False
    if used_by_roles or used_by_users:
        flash('لا يمكن الحذف: الإذن مرتبط بأدوار/مستخدمين.', 'danger')
        return redirect(url_for('permissions.list'))
    try:
        db.session.delete(perm)
        db.session.commit()
        _clear_all_users_cache()
        _clear_roles_cache_for_permission(perm)
        flash('تم حذف الإذن.', 'warning')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'لا يمكن الحذف: {e}', 'danger')
    return redirect(url_for('permissions.list'))
