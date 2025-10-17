
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from extensions import db
from models import Role, Permission, AuditLog, User
from forms import RoleForm
import utils

roles_bp = Blueprint("roles", __name__, url_prefix="/roles")


def _get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


def _is_protected_role_name(name: str) -> bool:
    return (name or "").strip().lower() in {"admin", "super_admin", "owner", "developer"}


def _group_permissions():
    """إرجاع الصلاحيات مجمعة حسب module لاستخدامها في القالب."""
    try:
        perms = Permission.query.order_by(Permission.module.asc(), Permission.name.asc()).all()
        grouped = {}
        for p in perms:
            mod = p.module or "أخرى"
            grouped.setdefault(mod, []).append((str(p.id), p.name or p.code or f"perm-{p.id}"))
        return grouped
    except Exception:
        return {}


@roles_bp.route("/", methods=["GET"], endpoint="list_roles")
@login_required
# @permission_required("manage_roles")  # Commented out
def list_roles():
    q = Role.query
    search = (request.args.get("search") or "").strip()
    if search:
        q = q.filter(Role.name.ilike(f"%{search}%"))
    roles = q.order_by(Role.name.asc()).all()
    return render_template("roles/list.html", roles=roles, search=search)


@roles_bp.route("/create", methods=["GET", "POST"], endpoint="create_role")
@login_required
# @permission_required("manage_roles")  # Commented out
def create_role():
    form = RoleForm()
    all_permissions = _group_permissions() or {}

    # لتعبئة الـ choices في الفورم (مطلوب لـ validate_on_submit)
    if all_permissions and isinstance(all_permissions, dict):
        flat_choices = [item for group in all_permissions.values() for item in group]
    else:
        flat_choices = []
    form.permissions.choices = flat_choices

    if form.validate_on_submit():
        try:
            with db.session.begin():
                role = Role(
                    name=form.name.data,
                    description=form.description.data,
                    is_default=form.is_default.data
                )
                ids = [int(x) for x in form.permissions.data] if form.permissions.data else []
                role.permissions = Permission.query.filter(Permission.id.in_(ids)).all()
                db.session.add(role)
                db.session.flush()
                db.session.add(AuditLog(
                    model_name="Role",
                    record_id=role.id,
                    user_id=current_user.id,
                    action="CREATE",
                    old_data="",
                    new_data=f"name={role.name}"
                ))
            clear_role_permission_cache(role.id)
            clear_users_cache_by_role(role.id)
            flash("تم إنشاء الدور بنجاح.", "success")
            return redirect(url_for("roles.list_roles"))
        except IntegrityError:
            db.session.rollback()
            flash("اسم الدور مستخدم بالفعل.", "danger")

    return render_template("roles/form.html", form=form, action="create", all_permissions=all_permissions or {})


@roles_bp.route("/<int:role_id>/edit", methods=["GET", "POST"], endpoint="edit_role")
@login_required
# @permission_required("manage_roles")  # Commented out
def edit_role(role_id):
    role = _get_or_404(Role, role_id)
    is_protected = _is_protected_role_name(role.name)
    form = RoleForm(obj=role)
    all_permissions = _group_permissions()

    # لتعبئة الـ choices
    flat_choices = [item for group in all_permissions.values() for item in group]
    form.permissions.choices = flat_choices

    if request.method == "GET":
        form.permissions.data = [str(p.id) for p in role.permissions]

    if form.validate_on_submit():
        try:
            new_name = form.name.data
            if is_protected and (new_name or "").strip().lower() != (role.name or "").strip().lower():
                flash("لا يمكن تعديل اسم هذا الدور المحمي.", "danger")
                return render_template("roles/form.html", form=form, action="edit", all_permissions=all_permissions)

            old_data = f"name={role.name}"
            with db.session.begin():
                role.name = new_name
                role.description = form.description.data
                role.is_default = form.is_default.data
                if (role.name or "").strip().lower() == "super_admin":
                    role.permissions = Permission.query.all()
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

    return render_template("roles/form.html", form=form, action="edit", all_permissions=all_permissions)


@roles_bp.route("/<int:role_id>/delete", methods=["POST"], endpoint="delete_role")
@login_required
# @permission_required("manage_roles")  # Commented out
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
