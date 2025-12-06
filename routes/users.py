
import json
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, abort, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import UserForm
from models import Permission, Role, User, AuditLog, Customer
import utils

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

def _is_super_admin_user(user: User) -> bool:
    try:
        return bool(user.role and (user.role.name or "").strip().lower() == "super_admin")
    except Exception:
        return False

@users_bp.route("/profile", methods=["GET"], endpoint="profile")
@login_required
def profile():
    return render_template("users/profile.html", user=current_user)

@users_bp.route("/edit-profile", methods=["GET", "POST"], endpoint="edit_profile")
@login_required
def edit_profile():
    """تعديل الملف الشخصي للمستخدم الحالي"""
    from flask_wtf import FlaskForm
    from wtforms import StringField, SubmitField
    from wtforms.validators import DataRequired, Email, Length, Optional
    
    class EditProfileForm(FlaskForm):
        username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=3, max=50)])
        email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
        submit = SubmitField('حفظ التعديلات')
    
    form = EditProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        try:
            current_user.username = form.username.data
            current_user.email = form.email.data
            db.session.commit()
            flash("✅ تم تحديث الملف الشخصي بنجاح", "success")
            return redirect(url_for("users_bp.profile"))
        except IntegrityError:
            db.session.rollback()
            flash("❌ اسم المستخدم أو البريد مستخدم بالفعل", "danger")
    
    return render_template("users/edit_profile.html", form=form)

@users_bp.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@login_required
def change_password():
    """تغيير كلمة المرور للمستخدم الحالي"""
    from flask_wtf import FlaskForm
    from wtforms import PasswordField, SubmitField
    from wtforms.validators import DataRequired, Length, EqualTo, Regexp
    
    class ChangePasswordForm(FlaskForm):
        current_password = PasswordField('كلمة المرور الحالية', validators=[DataRequired()])
        new_password = PasswordField('كلمة المرور الجديدة', validators=[
            DataRequired(), 
            Length(min=8, max=128, message='كلمة المرور يجب أن تكون 8 أحرف على الأقل'),
            Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)|(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&#])|(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])', 
                   message='كلمة المرور يجب أن تحتوي على: أحرف وأرقام، أو أحرف ورموز خاصة')
        ])
        confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('new_password', message='كلمات المرور غير متطابقة')])
        submit = SubmitField('تغيير كلمة المرور')
    
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # التحقق من كلمة المرور الحالية
        if not current_user.check_password(form.current_password.data):
            flash("❌ كلمة المرور الحالية غير صحيحة", "danger")
        else:
            # تحديث كلمة المرور
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("✅ تم تغيير كلمة المرور بنجاح", "success")
            return redirect(url_for("users_bp.profile"))
    
    return render_template("users/change_password.html", form=form)

@users_bp.route("/", methods=["GET"], endpoint="list_users")
@login_required
def list_users():
    # استثناء حسابات النظام المخفية
    q = User.query.filter(User.is_system_account == False).options(joinedload(User.role))
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
                    "is_active": bool(u.is_active),
                    "created_at": (u.created_at.isoformat() if getattr(u, "created_at", None) else None),
                    "last_login": (u.last_login.isoformat() if getattr(u, "last_login", None) else None),
                    "last_seen": (u.last_seen.isoformat() if getattr(u, "last_seen", None) else None),
                    "last_login_ip": getattr(u, "last_login_ip", None),
                    "login_count": getattr(u, "login_count", None),
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


@users_bp.route("/registered-customers", methods=["GET"], endpoint="registered_customers")
@login_required
def registered_customers():
    q = Customer.query
    q = q.filter(Customer.is_online == True)
    term = (request.args.get("search") or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(
            (Customer.name.ilike(like)) |
            (Customer.phone.ilike(like)) |
            (Customer.email.ilike(like))
        )
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(Customer.name).paginate(page=page, per_page=per_page, error_out=False)
    customers = pagination.items
    if request.args.get("format") == "json" or request.is_json:
        return jsonify({
            "data": [
                {
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "email": c.email,
                    "is_active": bool(c.is_active),
                    "is_online": bool(c.is_online),
                    "created_at": (c.created_at.isoformat() if getattr(c, "created_at", None) else None),
                }
                for c in customers
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
    return render_template("users/registered_customers.html", customers=customers, pagination=pagination, search=term, args=args)

@users_bp.route("/<int:user_id>", methods=["GET"], endpoint="user_detail")
@login_required
def user_detail(user_id):
    user = _get_or_404(User, user_id, options=[joinedload(User.role)])
    return render_template("users/detail.html", user=user)

@users_bp.route("/api", methods=["GET"], endpoint="api_users")
@login_required
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
def create_user():
    form = UserForm()
    all_permissions = Permission.query.order_by(Permission.name).all()
    selected_perm_ids = []
    if form.validate_on_submit():
        try:
            selected_perm_ids = [
                int(x) for x in request.form.getlist("extra_permissions") if str(x).isdigit()
            ]

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

            if selected_perm_ids:
                user.extra_permissions = Permission.query.filter(
                    Permission.id.in_(selected_perm_ids)
                ).all()

            db.session.add(AuditLog(
                model_name="User",
                record_id=user.id,
                user_id=current_user.id,
                action="CREATE",
                old_data="",
                new_data=f"username={user.username}"
            ))

            db.session.commit()
            # clear_user_permission_cache(user.id)  # Commented out - function not available

            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(id=user.id, username=user.username), 201

            flash("تم إضافة المستخدم بنجاح.", "success")
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
def edit_user(user_id):
    user = _get_or_404(User, user_id)
    if _is_super_admin_user(user):
        flash("❌ لا يمكن تعديل مستخدم super_admin.", "danger")
        return redirect(url_for("users_bp.list_users"))

    form = UserForm(obj=user)
    all_permissions = Permission.query.order_by(Permission.name).all()
    selected_perm_ids = [p.id for p in user.extra_permissions.all()]

    if request.method == "GET":
        form.role_id.data = user.role_id
        form.is_active.data = bool(user.is_active)

    if form.validate_on_submit():
        try:
            selected_perm_ids = [
                int(x) for x in request.form.getlist("extra_permissions") if str(x).isdigit()
            ]
            old_data = f"{user.username},{user.email}"

            user.username = form.username.data
            user.email = form.email.data
            user.role_id = form.role_id.data
            user.is_active = bool(form.is_active.data)

            if form.password.data:
                user.set_password(form.password.data)

            user.extra_permissions = Permission.query.filter(
                Permission.id.in_(selected_perm_ids)
            ).all() if selected_perm_ids else []

            db.session.add(AuditLog(
                model_name="User",
                record_id=user.id,
                user_id=current_user.id,
                action="UPDATE",
                old_data=old_data,
                new_data=f"username={user.username}"
            ))

            db.session.commit()
            # clear_user_permission_cache(user.id)  # Commented out - function not available

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
def delete_user(user_id):
    user = _get_or_404(User, user_id)
    
    # حماية حسابات النظام من الحذف
    if getattr(user, 'is_system_account', False) or user.username == '__OWNER__':
        flash("❌ لا يمكن حذف حساب النظام المحمي!", "danger")
        return redirect(url_for("users_bp.list_users"))
    if _is_super_admin_user(user):
        flash("❌ لا يمكن حذف مستخدم super_admin.", "danger")
        return redirect(url_for("users_bp.list_users"))
    if user.id == current_user.id:
        flash("❌ لا يمكن حذف حسابك الحالي.", "danger")
        return redirect(url_for("users_bp.list_users"))
    if user.email == current_app.config.get("DEV_EMAIL", "rafideen.ahmadghannam@gmail.com"):
        flash("❌ لا يمكن حذف حساب المطور الأساسي.", "danger")
        return redirect(url_for("users_bp.list_users"))

    try:
        old_data = f"{user.username},{user.email}"

        user.extra_permissions = []
        db.session.flush()
        db.session.delete(user)

        db.session.add(AuditLog(
            model_name="User",
            record_id=user_id,
            user_id=current_user.id,
            action="DELETE",
            old_data=old_data,
            new_data=""
        ))

        db.session.commit()
        # clear_user_permission_cache(user_id)  # Commented out - function not available
        flash("تم حذف المستخدم.", "warning")

    except IntegrityError:
        db.session.rollback()
        flash("لا يمكن حذف المستخدم لوجود معاملات مرتبطة به.", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء الحذف: {e}", "danger")

    return redirect(url_for("users_bp.list_users"))
