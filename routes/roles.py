from flask import Blueprint, flash, redirect, render_template, request, url_for, abort
from flask_login import login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import RoleForm
from models import Permission, Role, User
from utils import permission_required, clear_user_permission_cache

roles_bp = Blueprint(
    'roles',
    __name__,
    template_folder='templates/roles'
)

@roles_bp.route('/', methods=['GET'], endpoint='list')
@login_required
@permission_required('manage_roles')
def list():
    roles = (
        Role.query
            .options(joinedload(Role.permissions))
            .order_by(Role.name)
            .all()
    )
    return render_template('roles/list.html', roles=roles)

@roles_bp.route('/create', methods=['GET', 'POST'], endpoint='create')
@login_required
@permission_required('manage_roles')
def create():
    form = RoleForm()
    all_permissions = Permission.query.order_by(Permission.name).all()
    if form.validate_on_submit():
        try:
            role = Role(
                name=form.name.data,
                description=form.description.data
            )
            selected = Permission.query.filter(
                Permission.id.in_(form.permissions.data)
            ).all()
            role.permissions = selected
            db.session.add(role)
            db.session.commit()

            # مسح كاش صلاحيات جميع المستخدمين
            for (user_id,) in User.query.with_entities(User.id).all():
                clear_user_permission_cache(user_id)

            flash('تم إضافة الدور بنجاح.', 'success')
            return redirect(url_for('roles.list'))
        except IntegrityError:
            db.session.rollback()
            flash('اسم الدور مستخدم.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء الإضافة: {e}', 'danger')
    return render_template(
        'roles/form.html',
        form=form,
        role_id=None,
        all_permissions=all_permissions
    )

@roles_bp.route('/<int:role_id>/edit', methods=['GET', 'POST'], endpoint='edit')
@login_required
@permission_required('manage_roles')
def edit(role_id):
    role = Role.query.get_or_404(role_id)
    form = RoleForm(obj=role)
    all_permissions = Permission.query.order_by(Permission.name).all()
    if request.method == 'GET':
        form.permissions.data = [p.id for p in role.permissions]
    if form.validate_on_submit():
        try:
            role.name = form.name.data
            role.description = form.description.data
            selected = Permission.query.filter(
                Permission.id.in_(form.permissions.data)
            ).all()
            role.permissions = selected
            db.session.commit()

            # مسح كاش صلاحيات جميع المستخدمين
            for (user_id,) in User.query.with_entities(User.id).all():
                clear_user_permission_cache(user_id)

            flash('تم تحديث الدور.', 'success')
            return redirect(url_for('roles.list'))
        except IntegrityError:
            db.session.rollback()
            flash('اسم الدور مستخدم.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء التحديث: {e}', 'danger')
    return render_template(
        'roles/form.html',
        form=form,
        role_id=role_id,
        all_permissions=all_permissions
    )

@roles_bp.route('/<int:role_id>/delete', methods=['POST'], endpoint='delete')
@login_required
@permission_required('manage_roles')
def delete(role_id):
    role = Role.query.get_or_404(role_id)
    # منع حذف الأدوار الأساسية
    if role.name.lower() in ['developer', 'manager']:
        flash('❌ لا يمكن حذف دور أساسي للنظام.', 'danger')
        return redirect(url_for('roles.list'))
    if request.method != 'POST':
        abort(405)
    try:
        db.session.delete(role)
        db.session.commit()

        # مسح كاش صلاحيات جميع المستخدمين
        for (user_id,) in User.query.with_entities(User.id).all():
            clear_user_permission_cache(user_id)

        flash('تم حذف الدور.', 'warning')
    except IntegrityError:
        db.session.rollback()
        flash('لا يمكن حذف الدور لارتباطه بمستخدمين أو صلاحيات.', 'danger')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'خطأ أثناء الحذف: {e}', 'danger')
    return redirect(url_for('roles.list'))
