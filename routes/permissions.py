from flask import Blueprint, flash, redirect, render_template, url_for, request, abort
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from forms import PermissionForm
from models import Permission, User
from utils import permission_required, clear_user_permission_cache

permissions_bp = Blueprint(
    'permissions', __name__, template_folder='templates/permissions'
)

@permissions_bp.route('/', methods=['GET'], endpoint='list')
@login_required
@permission_required('manage_permissions')
def list_permissions():
    permissions = Permission.query.order_by(Permission.name).all()
    return render_template('permissions/list.html', permissions=permissions)

@permissions_bp.route('/create', methods=['GET', 'POST'], endpoint='create')
@login_required
@permission_required('manage_permissions')
def create_permission():
    form = PermissionForm()
    if form.validate_on_submit():
        if Permission.query.filter_by(name=form.name.data).first():
            flash('هذا الإذن موجود بالفعل!', 'danger')
        else:
            try:
                perm = Permission(name=form.name.data)
                db.session.add(perm)
                db.session.commit()

                # مسح كاش صلاحيات جميع المستخدمين
                for (user_id,) in User.query.with_entities(User.id).all():
                    clear_user_permission_cache(user_id)

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
    perm = Permission.query.get_or_404(permission_id)
    form = PermissionForm(obj=perm)
    if form.validate_on_submit():
        try:
            perm.name = form.name.data
            db.session.commit()

            # مسح كاش صلاحيات جميع المستخدمين
            for (user_id,) in User.query.with_entities(User.id).all():
                clear_user_permission_cache(user_id)

            flash('تم تحديث الإذن.', 'success')
            return redirect(url_for('permissions.list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء التحديث: {e}', 'danger')
    return render_template('permissions/form.html', form=form)

@permissions_bp.route('/<int:permission_id>/delete', methods=['POST'], endpoint='delete')
@login_required
@permission_required('manage_permissions')
def delete_permission(permission_id):
    perm = Permission.query.get_or_404(permission_id)
    try:
        db.session.delete(perm)
        db.session.commit()

        # مسح كاش صلاحيات جميع المستخدمين
        for (user_id,) in User.query.with_entities(User.id).all():
            clear_user_permission_cache(user_id)

        flash('تم حذف الإذن.', 'warning')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'لا يمكن الحذف: {e}', 'danger')
    return redirect(url_for('permissions.list'))
