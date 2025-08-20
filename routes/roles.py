# routes/roles.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Role, Permission, AuditLog
from forms import RoleForm
from utils import permission_required, clear_role_permission_cache, clear_users_cache_by_role

roles_bp = Blueprint('roles', __name__, url_prefix='/roles')


def _get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


@roles_bp.route('/', methods=['GET'], endpoint='list_roles')
@login_required
@permission_required('manage_roles')
def list_roles():
    q = Role.query
    search = request.args.get('search', '')
    if search:
        q = q.filter(Role.name.ilike(f"%{search}%"))
    roles = q.order_by(Role.name).all()
    return render_template('roles/list.html', roles=roles, search=search)


@roles_bp.route('/create', methods=['GET', 'POST'], endpoint='create_role')
@login_required
@permission_required('manage_roles')
def create_role():
    form = RoleForm()
    form.permissions.query = Permission.query.order_by(Permission.name).all()
    if form.validate_on_submit():
        try:
            role = Role(name=form.name.data)
            role.permissions = form.permissions.data
            db.session.add(role)
            db.session.commit()

            clear_role_permission_cache(role.id)
            clear_users_cache_by_role(role.id)

            db.session.add(AuditLog(
                model_name='Role',
                record_id=role.id,
                user_id=current_user.id,
                action='CREATE',
                old_data='',
                new_data=f'name={role.name}'
            ))
            db.session.commit()
            flash('تم إنشاء الدور بنجاح.', 'success')
            return redirect(url_for('roles.list_roles'))
        except IntegrityError:
            db.session.rollback()
            flash('اسم الدور مستخدم بالفعل.', 'danger')
    return render_template('roles/form.html', form=form, action='create')


@roles_bp.route('/<int:role_id>/edit', methods=['GET', 'POST'], endpoint='edit_role')
@login_required
@permission_required('manage_roles')
def edit_role(role_id):
    role = _get_or_404(Role, role_id)
    protected_names = ['admin', 'super_admin']
    is_protected = role.name in protected_names

    form = RoleForm(obj=role)
    form.permissions.query = Permission.query.order_by(Permission.name).all()

    if request.method == 'GET':
        form.permissions.data = role.permissions

    if form.validate_on_submit():
        try:
            if is_protected and form.name.data != role.name:
                flash('لا يمكن تعديل اسم هذا الدور المحمي.', 'danger')
                return render_template('roles/form.html', form=form, action='edit')

            old_data = f"name={role.name}"
            role.name = form.name.data
            role.permissions = form.permissions.data

            db.session.commit()
            clear_role_permission_cache(role.id)
            clear_users_cache_by_role(role.id)

            db.session.add(AuditLog(
                model_name='Role',
                record_id=role.id,
                user_id=current_user.id,
                action='UPDATE',
                old_data=old_data,
                new_data=f'name={role.name}'
            ))
            db.session.commit()

            flash('تم تعديل الدور بنجاح.', 'success')
            return redirect(url_for('roles.list_roles'))

        except IntegrityError:
            db.session.rollback()
            flash('اسم الدور مستخدم بالفعل.', 'danger')

    return render_template('roles/form.html', form=form, action='edit')


@roles_bp.route('/<int:role_id>/delete', methods=['POST'], endpoint='delete_role')
@login_required
@permission_required('manage_roles')
def delete_role(role_id):
    role = _get_or_404(Role, role_id)

    if role.name in ['admin', 'super_admin']:
        flash('لا يمكن حذف هذا الدور.', 'danger')
        return redirect(url_for('roles.list_roles'))

    try:
        old_data = f'name={role.name}'
        db.session.delete(role)
        db.session.commit()

        clear_role_permission_cache(role_id)
        clear_users_cache_by_role(role_id)

        db.session.add(AuditLog(
            model_name='Role',
            record_id=role_id,
            user_id=current_user.id,
            action='DELETE',
            old_data=old_data,
            new_data=''
        ))
        db.session.commit()

        flash('تم حذف الدور.', 'warning')
    except IntegrityError:
        db.session.rollback()
        flash('لا يمكن حذف هذا الدور بسبب ارتباطه ببيانات أخرى.', 'danger')

    return redirect(url_for('roles.list_roles'))
