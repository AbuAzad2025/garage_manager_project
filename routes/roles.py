# routes/roles.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from extensions import db
from models import Role, Permission, AuditLog, User
from forms import RoleForm
from utils import permission_required, clear_role_permission_cache, clear_users_cache_by_role, super_only

roles_bp = Blueprint("roles", __name__, url_prefix="/roles")

@roles_bp.before_request
@super_only
def _guard_roles():
    pass

def _get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

def _is_protected_role_name(name: str) -> bool:
    return (name or "").strip().lower() in {"admin", "super_admin", "owner", "developer"}

@roles_bp.route("/", methods=["GET"], endpoint="list_roles")
@login_required
@permission_required("manage_roles")
def list_roles():
    q = Role.query
    search = (request.args.get("search") or "").strip()
    if search:
        q = q.filter(Role.name.ilike(f"%{search}%"))
    roles = q.order_by(Role.name.asc()).all()
    return render_template("roles/list.html", roles=roles, search=search)

@roles_bp.route("/create", methods=["GET", "POST"], endpoint="create_role")
@login_required
@permission_required("manage_roles")
def create_role():
    form = RoleForm()
    try:
        if hasattr(form.permissions, "query_factory"):
            form.permissions.query_factory = lambda: Permission.query.order_by(Permission.name.asc()).all()
        else:
            perms = Permission.query.order_by(Permission.name.asc()).all()
            form.permissions.choices = [(str(p.id), p.name or p.code or f"perm-{p.id}") for p in perms]
    except Exception:
        pass
    if form.validate_on_submit():
        try:
            with db.session.begin():
                role = Role(name=form.name.data)
                if hasattr(form.permissions, "data") and form.permissions.data:
                    if isinstance(form.permissions.data[0], Permission):
                        role.permissions = form.permissions.data
                    else:
                        ids = [int(x) for x in form.permissions.data]
                        role.permissions = Permission.query.filter(Permission.id.in_(ids)).all()
                db.session.add(role)
                db.session.add(AuditLog(
                    model_name="Role",
                    record_id=None,
                    user_id=current_user.id,
                    action="CREATE",
                    old_data="",
                    new_data=f"name={role.name}"
                ))
                db.session.flush()
                db.session.query(AuditLog).filter(
                    AuditLog.model_name == "Role",
                    AuditLog.record_id.is_(None),
                    AuditLog.action == "CREATE"
                ).update({AuditLog.record_id: role.id}, synchronize_session=False)
            clear_role_permission_cache(role.id)
            clear_users_cache_by_role(role.id)
            flash("تم إنشاء الدور بنجاح.", "success")
            return redirect(url_for("roles.list_roles"))
        except IntegrityError:
            db.session.rollback()
            flash("اسم الدور مستخدم بالفعل.", "danger")
    return render_template("roles/form.html", form=form, action="create")

@roles_bp.route("/<int:role_id>/edit", methods=["GET", "POST"], endpoint="edit_role")
@login_required
@permission_required("manage_roles")
def edit_role(role_id):
    role = _get_or_404(Role, role_id)
    is_protected = _is_protected_role_name(role.name)
    form = RoleForm(obj=role)
    try:
        if hasattr(form.permissions, "query_factory"):
            form.permissions.query_factory = lambda: Permission.query.order_by(Permission.name.asc()).all()
        else:
            perms = Permission.query.order_by(Permission.name.asc()).all()
            form.permissions.choices = [(str(p.id), p.name or p.code or f"perm-{p.id}") for p in perms]
            if request.method == "GET":
                form.permissions.data = [str(p.id) for p in role.permissions]
    except Exception:
        pass
    if form.validate_on_submit():
        try:
            new_name = form.name.data
            if is_protected and (new_name or "").strip().lower() != (role.name or "").strip().lower():
                flash("لا يمكن تعديل اسم هذا الدور المحمي.", "danger")
                return render_template("roles/form.html", form=form, action="edit")
            old_data = f"name={role.name}"
            with db.session.begin():
                role.name = new_name
                if (role.name or "").strip().lower() == "super_admin":
                    role.permissions = Permission.query.all()
                else:
                    if hasattr(form.permissions, "data") and form.permissions.data is not None:
                        if isinstance(form.permissions.data, list) and form.permissions.data and isinstance(form.permissions.data[0], Permission):
                            role.permissions = form.permissions.data
                        else:
                            ids = [int(x) for x in form.permissions.data] if form.permissions.data else []
                            role.permissions = Permission.query.filter(Permission.id.in_(ids)).all()
                db.session.add(AuditLog(
                    model_name="Role",
                    record_id=role.id,
                    user_id=current_user.id,
                    action="UPDATE",
                    old_data=old_data,
                    new_data=f"name={role.name}"
                ))
            clear_role_permission_cache(role.id)
            clear_users_cache_by_role(role.id)
            flash("تم تعديل الدور بنجاح.", "success")
            return redirect(url_for("roles.list_roles"))
        except IntegrityError:
            db.session.rollback()
            flash("اسم الدور مستخدم بالفعل.", "danger")
    return render_template("roles/form.html", form=form, action="edit")

@roles_bp.route("/<int:role_id>/delete", methods=["POST"], endpoint="delete_role")
@login_required
@permission_required("manage_roles")
def delete_role(role_id):
    role = _get_or_404(Role, role_id)
    if (role.name or "").strip().lower() == "super_admin":
        flash("لا يمكن حذف الدور super_admin إطلاقاً.", "danger")
        return redirect(url_for("roles.list_roles"))
    if _is_protected_role_name(role.name):
        flash("لا يمكن حذف هذا الدور المحمي.", "danger")
        return redirect(url_for("roles.list_roles"))
    assigned_count = db.session.query(func.count(User.id)).filter(User.role_id == role.id).scalar() or 0
    if assigned_count > 0:
        flash("لا يمكن حذف هذا الدور لوجود مستخدمين مرتبطين به.", "danger")
        return redirect(url_for("roles.list_roles"))
    try:
        old_data = f"name={role.name}"
        with db.session.begin():
            db.session.delete(role)
            db.session.add(AuditLog(
                model_name="Role",
                record_id=role_id,
                user_id=current_user.id,
                action="DELETE",
                old_data=old_data,
                new_data=""
            ))
        clear_role_permission_cache(role_id)
        clear_users_cache_by_role(role_id)
        flash("تم حذف الدور.", "warning")
    except IntegrityError:
        db.session.rollback()
        flash("لا يمكن حذف هذا الدور بسبب ارتباطه ببيانات أخرى.", "danger")
    return redirect(url_for("roles.list_roles"))
