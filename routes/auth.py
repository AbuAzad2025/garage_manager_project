from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urljoin

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, abort
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select, func

from extensions import db, limiter, mail
from forms import LoginForm, CustomerFormOnline, CustomerPasswordResetForm, CustomerPasswordResetRequestForm
from models import Customer, User
from utils import _audit, redis_client as _redis


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _sa_get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


def _is_safe_url(target: str) -> bool:
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def _get_client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    return request.remote_addr or "0.0.0.0"


def _redirect_back_or(default_endpoint: str, **kwargs):
    nxt = request.args.get("next")
    if nxt and _is_safe_url(nxt):
        return redirect(nxt)
    return redirect(url_for(default_endpoint, **kwargs))


def _get_login_identifier(form: LoginForm) -> Optional[str]:
    val = (getattr(form, "username", None) and form.username.data) or request.form.get("username") or request.form.get("email")
    val = (val or "").strip()
    return val or None


MAX_ATTEMPTS = 5
BLOCK_TIME = timedelta(minutes=10)
_login_attempts_mem: dict[tuple[str, str], tuple[int, datetime]] = {}


def _norm_ident(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _la_key(ip: str, identifier: Optional[str]) -> str:
    return f"auth:login_attempts:{ip}:{_norm_ident(identifier)}"


def is_blocked(ip: str, identifier: Optional[str]) -> bool:
    try:
        if _redis:
            key = _la_key(ip, identifier)
            val = _redis.get(key)
            if val is None:
                return False
            try:
                attempts = int(val)
            except Exception:
                attempts = 0
            return attempts >= MAX_ATTEMPTS
    except Exception:
        pass
    key_mem = (ip, _norm_ident(identifier))
    info = _login_attempts_mem.get(key_mem)
    if not info:
        return False
    attempts, last_time = info
    now = datetime.utcnow()
    if attempts >= MAX_ATTEMPTS and now - last_time < BLOCK_TIME:
        return True
    if now - last_time >= BLOCK_TIME:
        _login_attempts_mem.pop(key_mem, None)
    return False


def record_attempt(ip: str, identifier: Optional[str]) -> None:
    try:
        if _redis:
            key = _la_key(ip, identifier)
            pipe = _redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, int(BLOCK_TIME.total_seconds()))
            pipe.execute()
            return
    except Exception:
        pass
    key_mem = (ip, _norm_ident(identifier))
    attempts, _last_time = _login_attempts_mem.get(key_mem, (0, datetime.utcnow()))
    _login_attempts_mem[key_mem] = (attempts + 1, datetime.utcnow())


def clear_attempts(ip: str, identifier: Optional[str]) -> None:
    try:
        if _redis:
            _redis.delete(_la_key(ip, identifier))
    except Exception:
        pass
    _login_attempts_mem.pop((ip, _norm_ident(identifier)), None)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute;100/hour;1000/day")
def login():
    ip = _get_client_ip()
    form = LoginForm()
    needs_fresh = request.args.get("fresh") == "1"
    has_next = bool(request.args.get("next"))

    if request.method == "GET":
        if current_user.is_authenticated and not needs_fresh and not has_next:
            clear_attempts(ip, getattr(current_user, "email", None) or getattr(current_user, "username", None))
            actor = current_user._get_current_object()
            return _redirect_back_or("shop.catalog" if isinstance(actor, Customer) else "main.dashboard")
        return render_template("auth/login.html", form=form)

    identifier = _get_login_identifier(form)
    if is_blocked(ip, identifier):
        flash("❌ تم حظر محاولات الدخول مؤقتًا، حاول بعد 10 دقائق.", "danger")
        _audit("login.blocked", ok=False, note="blocked window")
        return render_template("auth/login.html", form=form)

    password = request.form.get("password", "") or ""
    user = None
    customer = None

    if identifier:
        ident_l = identifier.lower()
        stmt = select(User).where((func.lower(User.username) == ident_l) | (func.lower(User.email) == ident_l))
        user = db.session.execute(stmt).scalars().first()
        if not user:
            customer = Customer.query.filter(
                (func.lower(Customer.email) == ident_l) | (Customer.phone == identifier) | (Customer.name == identifier)
            ).first()

    if user and user.check_password(password) and bool(getattr(user, "is_active", True)):
        remember = bool(getattr(form, "remember_me", None) and getattr(form.remember_me, "data", False))
        if current_user.is_authenticated and getattr(current_user, "id", None) != user.id:
            logout_user()
        login_user(user, remember=remember, fresh=True)
        try:
            user.last_login = datetime.utcnow()
            user.last_login_ip = ip
            user.login_count = (getattr(user, "login_count", 0) or 0) + 1
            db.session.commit()
        except Exception:
            db.session.rollback()
        clear_attempts(ip, identifier)
        _audit("login.success", ok=True, user_id=user.id, note=f"ip={ip}")
        return _redirect_back_or("main.dashboard")

    if customer and customer.check_password(password) and customer.is_online and customer.is_active:
        remember = bool(getattr(form, "remember_me", None) and getattr(form.remember_me, "data", False))
        if current_user.is_authenticated and getattr(current_user, "id", None) != customer.id:
            logout_user()
        login_user(customer, remember=remember, fresh=True)
        clear_attempts(ip, identifier)
        _audit("login.success.customer", ok=True, customer_id=customer.id, note=f"ip={ip}")
        return _redirect_back_or("shop.catalog")

    record_attempt(ip, identifier)
    _audit("login.failed", ok=False, note=f"id={identifier or ''}; ip={ip}")
    flash("❌ بيانات الدخول غير صحيحة.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    _audit("logout", ok=True, user_id=getattr(current_user, "id", None))
    logout_user()
    flash("تم تسجيل الخروج بنجاح.", "info")
    resp = redirect(url_for("auth.login", fresh=1))
    rc_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
    rc_domain = current_app.config.get("REMEMBER_COOKIE_DOMAIN", None)
    rc_path = current_app.config.get("REMEMBER_COOKIE_PATH", "/")
    resp.delete_cookie(rc_name, domain=rc_domain, path=rc_path)
    resp.delete_cookie(rc_name, domain=None, path=rc_path)
    return resp


@auth_bp.route("/register/customer", methods=["GET", "POST"])
@limiter.limit("12/hour")
def customer_register():
    if current_user.is_authenticated:
        return redirect(url_for("shop.catalog"))
    form = CustomerFormOnline()
    if form.validate_on_submit():
        existing_user = User.query.filter(func.lower(User.email) == (form.email.data or "").strip().lower()).first()
        if existing_user:
            flash("❌ هذا البريد الإلكتروني مستخدم من قبل مستخدم داخلي. الرجاء استخدام بريد آخر.", "danger")
            return render_template("auth/customer_register.html", form=form)
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
        login_user(customer, fresh=True)
        _audit("customer.register", ok=True, customer_id=customer.id)
        flash("✅ تم إنشاء حسابك بنجاح! يمكنك الآن استخدام المتجر.", "success")
        return redirect(url_for("shop.catalog"))
    return render_template("auth/customer_register.html", form=form)


@auth_bp.route("/customer_password_reset_request", methods=["GET", "POST"])
@limiter.limit("5/minute;30/hour")
def customer_password_reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("shop.catalog"))
    form = CustomerPasswordResetRequestForm()
    if form.validate_on_submit():
        customer = Customer.query.filter(
            func.lower(Customer.email) == (form.email.data or "").strip().lower(),
            Customer.is_active.is_(True),
            Customer.is_online.is_(True),
        ).first()
        if customer:
            send_customer_password_reset_email(customer)
        flash("📩 إذا كان البريد مسجلاً، ستصلك التعليمات قريبًا.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/customer_password_reset_request.html", form=form)


@auth_bp.route("/customer_password_reset/<token>", methods=["GET", "POST"])
def customer_password_reset(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("shop.catalog"))
    form = CustomerPasswordResetForm()
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        customer_id = serializer.loads(token, salt="customer-password-reset-salt", max_age=3600)
    except SignatureExpired:
        flash("⏳ انتهت صلاحية الرابط.", "warning")
        return redirect(url_for("auth.customer_password_reset_request"))
    except BadSignature:
        flash("❌ الرابط غير صالح.", "danger")
        return redirect(url_for("auth.customer_password_reset_request"))
    customer = _sa_get_or_404(Customer, customer_id)
    if form.validate_on_submit():
        customer.set_password(form.password.data)
        db.session.commit()
        _audit("customer.password_reset", ok=True, customer_id=customer.id)
        flash("✅ تم تحديث كلمة المرور بنجاح.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/customer_password_reset.html", form=form, token=token)


def send_customer_password_reset_email(customer: Customer):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = serializer.dumps(customer.id, salt="customer-password-reset-salt")
    reset_url = url_for("auth.customer_password_reset", token=token, _external=True)
    body = render_template("emails/customer_password_reset.txt", reset_url=reset_url, name=customer.name)
    html = render_template("emails/customer_password_reset.html", reset_url=reset_url, name=customer.name)
    msg = Message("رابط إعادة تعيين كلمة المرور", recipients=[customer.email], body=body, html=html)
    mail.send(msg)
