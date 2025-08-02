# File: routes/auth.py

from datetime import datetime, timedelta
import uuid

from flask import (
    Blueprint, current_app, flash,
    redirect, render_template, request, url_for
)
from flask_login import (
    current_user, login_required,
    login_user, logout_user
)
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db, mail

from forms import (
    LoginForm, PasswordResetForm,
    PasswordResetRequestForm,
    RegistrationForm, CustomerFormOnline
)
from models import Customer, Role, User
from utils import permission_required   # <— صححنا الاستيراد من utils

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ========== 🛡️ نظام منع المحاولات المتكررة ==========
login_attempts = {}
MAX_ATTEMPTS = 5
BLOCK_TIME = timedelta(minutes=10)

def is_blocked(ip):
    info = login_attempts.get(ip)
    if not info:
        return False
    attempts, last_time = info
    if attempts >= MAX_ATTEMPTS and datetime.utcnow() - last_time < BLOCK_TIME:
        return True
    elif datetime.utcnow() - last_time >= BLOCK_TIME:
        login_attempts.pop(ip, None)
    return False

def record_attempt(ip):
    attempts, last_time = login_attempts.get(ip, (0, datetime.utcnow()))
    login_attempts[ip] = (attempts + 1, datetime.utcnow())

# ========== 📧 إرسال بريد إعادة تعيين ==========
def send_password_reset_email(user):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(user.id, salt='password-reset-salt')
    reset_url = url_for('auth.password_reset', token=token, _external=True)
    msg = Message(
        subject="إعادة تعيين كلمة المرور",
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[user.email]
    )
    msg.body = (
        f"مرحبًا {user.username},\n\n"
        f"لإعادة تعيين كلمة المرور، اضغط هنا:\n{reset_url}\n\n"
        "إذا لم تطلب هذا الإجراء، تجاهل الرسالة."
    )
    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f"فشل إرسال بريد إعادة التعيين: {e}")

# ========== 🔑 تسجيل الدخول ==========
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # إعادة توجيه حسب الدور
        if isinstance(current_user, Customer):
            return redirect(url_for('shop.catalog'))
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    ip = request.remote_addr

    if is_blocked(ip):
        flash('❌ تم حظر محاولات الدخول مؤقتًا، حاول بعد 10 دقائق.', 'danger')
        return render_template('auth/login.html', form=form)

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            login_attempts.pop(ip, None)  # إعادة تعيين المحاولات
            next_page = request.args.get('next') or url_for('main.dashboard')
            return redirect(next_page)
        record_attempt(ip)
        flash('❌ بيانات الدخول غير صحيحة.', 'danger')

    return render_template('auth/login.html', form=form)

# ========== 🔐 تسجيل الخروج ==========
@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('auth.login'))

# ========== 👤 تسجيل مستخدم داخلي ==========
@auth_bp.route('/register', methods=['GET', 'POST'])
@login_required
@permission_required('manage_users')
def register():
    form = RegistrationForm()
    # ملء خيارات SelectField بالدور
    form.role.choices = [(r.id, r.name) for r in Role.query.order_by(Role.name).all()]

    if form.validate_on_submit():
        selected_role = Role.query.get(form.role.data)
        if selected_role.name.lower() == 'developer':
            flash('❌ لا يمكن إنشاء حساب بدور Developer من خلال الواجهة.', 'danger')
            return redirect(url_for('users.list_users'))

        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.set_password(form.password.data)
        user.role = selected_role

        db.session.add(user)
        try:
            db.session.commit()
            flash('✅ تم إنشاء الحساب الداخلي بنجاح.', 'success')
            return redirect(url_for('users.list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء تسجيل المستخدم: {e}', 'danger')

    return render_template('auth/register.html', form=form)

# ========== 🛒 تسجيل عميل أونلاين ==========
@auth_bp.route('/register/customer', methods=['GET', 'POST'])
def customer_register():
    if current_user.is_authenticated and isinstance(current_user, User):
        flash('أنت مسجل دخول بالفعل.', 'info')
        return redirect(url_for('shop.catalog'))

    form = CustomerFormOnline()
    if form.validate_on_submit():
        customer = Customer(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            whatsapp=form.whatsapp.data,
            address=form.address.data,
            is_online=True,
            is_active=True
        )
        customer.set_password(form.password.data)
        db.session.add(customer)
        db.session.commit()
        login_user(customer)
        flash('✅ تم إنشاء حسابك بنجاح! يمكنك الآن استخدام المتجر.', 'success')
        return redirect(url_for('shop.catalog'))

    return render_template('auth/customer_register.html', form=form)

# ========== 🔄 طلب إعادة تعيين ==========
@auth_bp.route('/password_reset_request', methods=['GET', 'POST'])
def password_reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('📩 إذا كان البريد مسجلاً، ستصلك التعليمات قريبًا.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/password_reset_request.html', form=form)

# ========== 🔁 إعادة التعيين ==========
@auth_bp.route('/password_reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = PasswordResetForm()
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except SignatureExpired:
        flash('⏳ انتهت صلاحية الرابط.', 'warning')
        return redirect(url_for('auth.password_reset_request'))
    except BadSignature:
        flash('❌ الرابط غير صالح.', 'danger')
        return redirect(url_for('auth.password_reset_request'))

    user = User.query.get_or_404(user_id)
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('✅ تم تحديث كلمة المرور بنجاح.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/password_reset.html', form=form)
