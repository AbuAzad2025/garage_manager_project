import json
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, abort, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import UserForm
from models import Permission, Role, User, AuditLog
from utils import permission_required, clear_user_permission_cache

users_bp = Blueprint("users_bp", __name__, url_prefix="/users", template_folder="templates/users")

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

@users_bp.route("/profile", methods=["GET"], endpoint="profile")
@login_required
def profile():
    return render_template("users/profile.html", user=current_user)

@users_bp.route("/", methods=["GET"], endpoint="list_users")
@login_required
@permission_required("manage_users")
def list_users():
    q = User.query.options(joinedload(User.role))
    term = request.args.get("search", "")
    if term:
        like = f"%{term}%"
        q = q.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(User.username).paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items
    if request.args.get("format") == "json" or request.is_json:
        return jsonify({
            "data": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "role": (u.role.name if u.role else None),
                    "extra_permissions": [p.name for p in u.extra_permissions.all()]
                }
                for u in users
            ],
            "meta": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev
            }
        })
    args = request.args.to_dict(flat=True)
    args.pop("page", None)
    return render_template("users/list.html", users=users, pagination=pagination, search=term, args=args)

@users_bp.route("/<int:user_id>", methods=["GET"], endpoint="user_detail")
@login_required
@permission_required("manage_users")
def user_detail(user_id):
    user = _get_or_404(User, user_id)
    return render_template("users/detail.html", user=user)

@users_bp.route("/api", methods=["GET"], endpoint="api_users")
@login_required
@permission_required("manage_users")
def api_users():
    q = User.query
    term = request.args.get("q", "")
    if term:
        q = q.filter(User.username.ilike(f"%{term}%"))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(User.username).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "results": [{"id": u.id, "text": u.username} for u in pagination.items],
        "pagination": {"more": pagination.has_next}
    })

@users_bp.route("/create", methods=["GET", "POST"], endpoint="create_user")
@login_required
@permission_required("manage_users")
def create_user():
    form = UserForm()
    all_permissions = Permission.query.order_by(Permission.name).all()
    selected_perm_ids = []

    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role_id=form.role_id.data,
                is_active=bool(form.is_active.data),
            )
            if form.password.data:
                user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            selected_perm_ids = [int(x) for x in request.form.getlist("extra_permissions") if str(x).isdigit()]
            if selected_perm_ids:
                user.extra_permissions = Permission.query.filter(Permission.id.in_(selected_perm_ids)).all()
            db.session.commit()
            clear_user_permission_cache(user.id)
            db.session.add(AuditLog(model_name="User", record_id=user.id, user_id=current_user.id, action="CREATE", old_data="", new_data=f"username={user.username}"))
            db.session.commit()
            flash("تم إضافة المستخدم بنجاح.", "success")
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(id=user.id, username=user.username), 201
            return redirect(url_for("users_bp.list_users"))
        except IntegrityError:
            db.session.rollback()
            flash("اسم المستخدم أو البريد الإلكتروني مستخدم.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"خطأ أثناء الإضافة: {e}", "danger")

    return render_template(
        "users/form.html",
        form=form,
        action="create",
        user_id=None,
        all_permissions=all_permissions,
        selected_perm_ids=selected_perm_ids,
    )

@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"], endpoint="edit_user")
@login_required
@permission_required("manage_users")
def edit_user(user_id):
    user = _get_or_404(User, user_id)
    form = UserForm(obj=user)
    all_permissions = Permission.query.order_by(Permission.name).all()
    selected_perm_ids = [p.id for p in user.extra_permissions.all()]

    if request.method == "GET":
        form.role_id.data = user.role_id
        form.is_active.data = bool(user.is_active)

    if form.validate_on_submit():
        try:
            old_data = f"{user.username},{user.email}"
            user.username = form.username.data
            user.email = form.email.data
            user.role_id = form.role_id.data
            user.is_active = bool(form.is_active.data)
            if form.password.data:
                user.set_password(form.password.data)
            selected_perm_ids = [int(x) for x in request.form.getlist("extra_permissions") if str(x).isdigit()]
            user.extra_permissions = Permission.query.filter(Permission.id.in_(selected_perm_ids)).all() if selected_perm_ids else []
            db.session.commit()
            clear_user_permission_cache(user.id)
            db.session.add(AuditLog(model_name="User", record_id=user.id, user_id=current_user.id, action="UPDATE", old_data=old_data, new_data=f"username={user.username}"))
            db.session.commit()
            flash("تم تحديث المستخدم.", "success")
            return redirect(url_for("users_bp.list_users"))
        except IntegrityError:
            db.session.rollback()
            flash("لا يمكن استخدام هذا البريد/الاسم.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"خطأ أثناء التحديث: {e}", "danger")

    return render_template(
        "users/form.html",
        form=form,
        action="edit",
        user_id=user_id,
        all_permissions=all_permissions,
        selected_perm_ids=selected_perm_ids,
    )

@users_bp.route("/<int:user_id>/delete", methods=["POST"], endpoint="delete_user")
@login_required
@permission_required("manage_users")
def delete_user(user_id):
    user = _get_or_404(User, user_id)
    if user.email == current_app.config.get("DEV_EMAIL", "rafideen.ahmadghannam@gmail.com"):
        flash("❌ لا يمكن حذف حساب المطور الأساسي.", "danger")
        return redirect(url_for("users_bp.list_users"))
    try:
        old_data = f"{user.username},{user.email}"
        user.extra_permissions = []
        db.session.flush()
        db.session.delete(user)
        db.session.commit()
        clear_user_permission_cache(user_id)
        db.session.add(AuditLog(model_name="User", record_id=user_id, user_id=current_user.id, action="DELETE", old_data=old_data, new_data=""))
        db.session.commit()
        flash("تم حذف المستخدم.", "warning")
    except IntegrityError:
        db.session.rollback()
        flash("لا يمكن حذف المستخدم لوجود معاملات مرتبطة به.", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("users_bp.list_users"))

@users_bp.route("/register", methods=["GET"])
@login_required
@permission_required("manage_users")
def internal_register():
    form = UserForm()
    all_permissions = Permission.query.order_by(Permission.name).all()
    return render_template(
        "users/form.html",
        form=form,
        action="create",
        user_id=None,
        all_permissions=all_permissions,
        selected_perm_ids=[],
    )
