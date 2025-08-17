import json
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    abort,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.routing import BuildError

from extensions import db, mail
from forms import (
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RegistrationForm,
    CustomerFormOnline,
)
from models import Customer, Role, User
from utils import permission_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _sa_get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


def _is_safe_url(target: str) -> bool:
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (test_url.scheme in ("http", "https")) and (ref_url.netloc == test_url.netloc)


def _get_client_ip() -> str:
    ip = request.environ.get("REMOTE_ADDR")
    if ip:
        return ip
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for part in xff.split(","):
            p = part.strip()
            if p:
                return p
    for p in (request.access_route or []):
        if p:
            return p
    return request.remote_addr or "0.0.0.0"


def _url_for_any(*endpoints, **values):
    for ep in endpoints:
        try:
            return url_for(ep, **values)
        except BuildError:
            continue
    return url_for("main.dashboard", **values)


def _redirect_back_or(default_endpoint: str, **kwargs):
    nxt = request.args.get("next")
    if nxt and _is_safe_url(nxt):
        return redirect(nxt)
    return redirect(url_for(default_endpoint, **kwargs))


def _redirect_back_or_any(*endpoints, **kwargs):
    nxt = request.args.get("next")
    if nxt and _is_safe_url(nxt):
        return redirect(nxt)
    return redirect(_url_for_any(*endpoints, **kwargs))


def _get_login_identifier(form: LoginForm) -> Optional[str]:
    val = None
    if hasattr(form, "username"):
        val = getattr(form.username, "data", None)
    if not val:
        val = request.form.get("username")
    if not val and hasattr(form, "email"):
        val = getattr(form.email, "data", None)
    if not val:
        val = request.form.get("email")
    return (val or "").strip() or None


login_attempts: dict[str, tuple[int, datetime]] = {}
MAX_ATTEMPTS = 5
BLOCK_TIME = timedelta(minutes=10)


def is_blocked(ip: str) -> bool:
    info = login_attempts.get(ip)
    if not info:
        return False
    attempts, last_time = info
    if attempts >= MAX_ATTEMPTS and datetime.utcnow() - last_time < BLOCK_TIME:
        return True
    if datetime.utcnow() - last_time >= BLOCK_TIME:
        login_attempts.pop(ip, None)
    return False


def record_attempt(ip: str) -> None:
    attempts, _last_time = login_attempts.get(ip, (0, datetime.utcnow()))
    login_attempts[ip] = (attempts + 1, datetime.utcnow())


def clear_attempts(ip: str) -> None:
    login_attempts.pop(ip, None)


def _candidate_ips_for_request() -> set[str]:
    candidates: set[str] = set()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        candidates.update(ip.strip() for ip in xff.split(",") if ip.strip())
    ra = request.environ.get("REMOTE_ADDR")
    if ra:
        candidates.add(ra)
    if request.remote_addr:
        candidates.add(request.remote_addr)
    for ip in (request.access_route or []):
        if ip:
            candidates.add(ip)
    return candidates


def clear_attempts_for_request() -> None:
    for ip in _candidate_ips_for_request():
        login_attempts.pop(ip, None)


def is_blocked_for_request() -> bool:
    for ip in _candidate_ips_for_request():
        if is_blocked(ip):
            return True
    return False


def _audit(kind: str, ok: bool, user_id: Optional[int] = None, note: str = "", customer_id: Optional[int] = None) -> None:
    try:
        from models import AuditLog, Customer, User  # type: ignore

        actor = current_user._get_current_object() if current_user.is_authenticated else None
        if customer_id is None and isinstance(actor, Customer):
            customer_id = actor.id
        if user_id is None and isinstance(actor, User):
            user_id = actor.id

        action_map = {
            "login.success": "CREATE",
            "logout": "DELETE",
            "login.failed": "UPDATE",
            "login.blocked": "UPDATE",
            "user.create": "CREATE",
            "password.reset": "UPDATE",
        }
        action = action_map.get(kind, "UPDATE")
        record_id = user_id or 0

        payload = {"event": kind, "ok": bool(ok), "note": note}

        rec = AuditLog(
            model_name="auth",
            customer_id=customer_id,
            record_id=record_id,
            user_id=user_id,
            action=action,
            old_data=None,
            new_data=json.dumps(payload, ensure_ascii=False),
            ip_address=_get_client_ip(),
            user_agent=request.headers.get("User-Agent", "")[:255],
        )
        db.session.add(rec)
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        finally:
            current_app.logger.info("audit skipped: %r", e)


def send_password_reset_email(user: User) -> None:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = serializer.dumps(user.id, salt="password-reset-salt")
    reset_url = url_for("auth.password_reset", token=token, _external=True)
    msg = Message(
        subject="إعادة تعيين كلمة المرور",
        sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        recipients=[user.email],
        body=(
            f"مرحبًا {user.username},\n\n"
            f"لإعادة تعيين كلمة المرور، اضغط هنا:\n{reset_url}\n\n"
            f"إذا لم تطلب هذا الإجراء، تجاهل الرسالة."
        ),
    )
    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.error("فشل إرسال بريد إعادة التعيين: %s", e)


from sqlalchemy import select

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    ip = _get_client_ip()

    if is_blocked(ip) or is_blocked_for_request():
        form = LoginForm()
        flash("❌ تم حظر محاولات الدخول مؤقتًا، حاول بعد 10 دقائق.", "danger")
        _audit("login.blocked", ok=False, note="blocked window")
        return render_template("auth/login.html", form=form)

    form = LoginForm()

    if request.method == "GET" and current_user.is_authenticated:
        clear_attempts(ip)
        clear_attempts_for_request()

        actor = current_user._get_current_object()
        if isinstance(actor, Customer):
            return _redirect_back_or("shop.catalog")
        return _redirect_back_or("main.dashboard")

    if request.method == "POST":
        identifier = _get_login_identifier(form)
        password = request.form.get("password", "")

        user = None
        if identifier:
            stmt = select(User).where((User.username == identifier) | (User.email == identifier))
            user = db.session.execute(stmt).scalars().first()

        if user and user.check_password(password):
            remember = False
            if hasattr(form, "remember_me"):
                try:
                    remember = bool(getattr(form.remember_me, "data", False))
                except Exception:
                    remember = False

            if current_user.is_authenticated and getattr(current_user, "id", None) != user.id:
                logout_user()

            login_user(user, remember=remember)
            try:
                user.last_login = datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
            clear_attempts(ip)
            clear_attempts_for_request()
            _audit("login.success", ok=True, user_id=user.id)

            actor = user  # المستخدم الحقيقي
            if isinstance(actor, Customer):
                return _redirect_back_or("shop.catalog")
            return _redirect_back_or("main.dashboard")

        record_attempt(ip)
        _audit("login.failed", ok=False, note=f"id={identifier or ''}")
        flash("❌ بيانات الدخول غير صحيحة.", "danger")

    return render_template("auth/login.html", form=form)

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    _audit("logout", ok=True, user_id=getattr(current_user, "id", None))
    logout_user()
    flash("تم تسجيل الخروج بنجاح.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/register", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
def register():
    form = RegistrationForm()
    form.role.choices = [(r.id, r.name) for r in Role.query.order_by(Role.name).all()]

    if form.validate_on_submit():
        selected_role = db.session.get(Role, form.role.data) if form.role.data else None

        if selected_role and selected_role.name.lower() == "developer":
            flash("❌ لا يمكن إنشاء حساب بدور Developer من خلال الواجهة.", "danger")
            return redirect(url_for("users.list_users"))

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        user.role = selected_role
        db.session.add(user)

        try:
            db.session.commit()
            _audit("user.create", ok=True, user_id=user.id, note=f"role={selected_role and selected_role.name}")
            flash("✅ تم إنشاء الحساب الداخلي بنجاح.", "success")
            return redirect(url_for("users.list_users"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("register commit failed: %s", e)
            _audit("user.create", ok=False, note="db commit failed")
            flash(f"❌ خطأ أثناء تسجيل المستخدم: {e}", "danger")

    return render_template("auth/register.html", form=form)

@auth_bp.route("/register/customer", methods=["GET", "POST"])
def customer_register():
    if current_user.is_authenticated and isinstance(current_user._get_current_object(), User):
        flash("أنت مسجل دخول بالفعل.", "info")
        return redirect(url_for("shop.catalog"))  # ✅ تعديل هنا

    form = CustomerFormOnline()
    if form.validate_on_submit():
        customer = Customer(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            whatsapp=form.whatsapp.data,
            address=form.address.data,
            is_online=True,
            is_active=True,
        )
        customer.set_password(form.password.data)
        db.session.add(customer)
        db.session.commit()

        login_user(customer)
        _audit("customer.register", ok=True, customer_id=customer.id)
        flash("✅ تم إنشاء حسابك بنجاح! يمكنك الآن استخدام المتجر.", "success")
        return redirect(url_for("shop.catalog"))  # ✅ تعديل هنا أيضًا

    return render_template("auth/customer_register.html", form=form)

@auth_bp.route("/password_reset_request", methods=["GET", "POST"])
def password_reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)

        flash("📩 إذا كان البريد مسجلاً، ستصلك التعليمات قريبًا.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/password_reset_request.html", form=form)


@auth_bp.route("/password_reset/<token>", methods=["GET", "POST"])
def password_reset(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = PasswordResetForm()
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    try:
        user_id = serializer.loads(token, salt="password-reset-salt", max_age=3600)
    except SignatureExpired:
        flash("⏳ انتهت صلاحية الرابط.", "warning")
        return redirect(url_for("auth.password_reset_request"))
    except BadSignature:
        flash("❌ الرابط غير صالح.", "danger")
        return redirect(url_for("auth.password_reset_request"))

    user = _sa_get_or_404(User, user_id)

    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        _audit("password.reset", ok=True, user_id=user.id)
        flash("✅ تم تحديث كلمة المرور بنجاح.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/password_reset.html", form=form)


login_attempts_ref = login_attempts
