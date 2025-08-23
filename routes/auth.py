import json
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request,
    url_for, abort
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from extensions import db, mail
from forms import (
    LoginForm, CustomerFormOnline,
    CustomerPasswordResetForm, CustomerPasswordResetRequestForm
)
from models import Customer, User
from utils import _audit

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

def _sa_get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

def _is_safe_url(target: str) -> bool:
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc)

def _get_client_ip() -> str:
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

login_attempts: dict[tuple[str, str], tuple[int, datetime]] = {}
MAX_ATTEMPTS = 5
BLOCK_TIME = timedelta(minutes=10)

def _norm_ident(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def is_blocked(ip: str, identifier: Optional[str]) -> bool:
    key = (ip, _norm_ident(identifier))
    info = login_attempts.get(key)
    if not info:
        return False
    attempts, last_time = info
    if attempts >= MAX_ATTEMPTS and datetime.utcnow() - last_time < BLOCK_TIME:
        return True
    if datetime.utcnow() - last_time >= BLOCK_TIME:
        login_attempts.pop(key, None)
    return False

def record_attempt(ip: str, identifier: Optional[str]) -> None:
    key = (ip, _norm_ident(identifier))
    attempts, _last_time = login_attempts.get(key, (0, datetime.utcnow()))
    login_attempts[key] = (attempts + 1, datetime.utcnow())

def clear_attempts(ip: str, identifier: Optional[str]) -> None:
    login_attempts.pop((ip, _norm_ident(identifier)), None)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    ip = _get_client_ip()
    form = LoginForm()

    if request.method == "GET" and current_user.is_authenticated:
        clear_attempts(ip, getattr(current_user, "email", None) or getattr(current_user, "username", None))
        actor = current_user._get_current_object()
        return _redirect_back_or("shop.catalog" if isinstance(actor, Customer) else "main.dashboard")

    identifier = _get_login_identifier(form)

    if is_blocked(ip, identifier):
        flash("❌ تم حظر محاولات الدخول مؤقتًا، حاول بعد 10 دقائق.", "danger")
        _audit("login.blocked", ok=False, note="blocked window")
        return render_template("auth/login.html", form=form)

    if request.method == "POST":
        password = request.form.get("password", "") or ""
        user = None
        customer = None

        if identifier:
            stmt = select(User).where((User.username == identifier) | (User.email == identifier))
            user = db.session.execute(stmt).scalars().first()
            if not user:
                customer = Customer.query.filter(
                    (Customer.email == identifier) | (Customer.phone == identifier) | (Customer.name == identifier)
                ).first()

        if user and user.check_password(password):
            remember = bool(getattr(form, "remember_me", None) and getattr(form.remember_me, "data", False))
            if current_user.is_authenticated and getattr(current_user, "id", None) != user.id:
                logout_user()
            login_user(user, remember=remember)
            try:
                user.last_login = datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
            clear_attempts(ip, identifier)
            _audit("login.success", ok=True, user_id=user.id)
            return _redirect_back_or("main.dashboard")

        if customer and customer.check_password(password) and customer.is_online and customer.is_active:
            remember = bool(getattr(form, "remember_me", None) and getattr(form.remember_me, "data", False))
            if current_user.is_authenticated and getattr(current_user, "id", None) != customer.id:
                logout_user()
            login_user(customer, remember=remember)
            clear_attempts(ip, identifier)
            _audit("login.success.customer", ok=True, customer_id=customer.id)
            return _redirect_back_or("shop.catalog")

        record_attempt(ip, identifier)
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

@auth_bp.route("/register/customer", methods=["GET", "POST"])
def customer_register():
    if current_user.is_authenticated:
        return redirect(url_for("shop.catalog"))
    form = CustomerFormOnline()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
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
        login_user(customer)
        _audit("customer.register", ok=True, customer_id=customer.id)
        flash("✅ تم إنشاء حسابك بنجاح! يمكنك الآن استخدام المتجر.", "success")
        return redirect(url_for("shop.catalog"))
    return render_template("auth/customer_register.html", form=form)

@auth_bp.route("/customer_password_reset_request", methods=["GET", "POST"])
def customer_password_reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("shop.catalog"))
    form = CustomerPasswordResetRequestForm()
    if form.validate_on_submit():
        customer = Customer.query.filter_by(email=form.email.data, is_active=True, is_online=True).first()
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
