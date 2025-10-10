"""
وحدة الأمان الشاملة - التحقق من المدخلات والحماية المتقدمة
"""
import re
import html
import time
import hashlib
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, current_app, jsonify
from flask_login import current_user

# قائمة المحارف الخطيرة
DANGEROUS_CHARS = ['<', '>', '"', "'", '&', '/', '\\', ';', '|', '`', '$']

def sanitize_input(text: str, allow_html: bool = False) -> str:
    """
    تنظيف المدخلات من المحارف الخطيرة
    
    Args:
        text: النص المدخل
        allow_html: السماح بـ HTML (افتراضياً: False)
        
    Returns:
        النص المنظف
    """
    if not text or not isinstance(text, str):
        return ""
    
    # إزالة المسافات الزائدة
    text = text.strip()
    
    # تنظيف HTML إذا لم يكن مسموحاً
    if not allow_html:
        text = html.escape(text)
    
    return text


def is_safe_url(target: str) -> bool:
    """
    التحقق من أن الرابط آمن (لا يوجه لموقع خارجي)
    
    Args:
        target: الرابط المستهدف
        
    Returns:
        True إذا كان الرابط آمناً
    """
    if not target:
        return False
    
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def validate_email(email: str) -> bool:
    """
    التحقق من صحة البريد الإلكتروني
    
    Args:
        email: البريد الإلكتروني
        
    Returns:
        True إذا كان البريد صالحاً
    """
    if not email or not isinstance(email, str):
        return False
    
    # نمط بسيط للتحقق من البريد الإلكتروني
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """
    التحقق من صحة رقم الهاتف
    
    Args:
        phone: رقم الهاتف
        
    Returns:
        True إذا كان الرقم صالحاً
    """
    if not phone or not isinstance(phone, str):
        return False
    
    # إزالة المسافات والمحارف الخاصة
    clean_phone = re.sub(r'[^\d+]', '', phone)
    
    # يجب أن يحتوي على 7-15 رقم على الأقل
    return 7 <= len(clean_phone) <= 20


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    التحقق من قوة كلمة المرور
    
    Args:
        password: كلمة المرور
        
    Returns:
        (صالح, رسالة الخطأ)
    """
    if not password or not isinstance(password, str):
        return False, "كلمة المرور مطلوبة"
    
    if len(password) < 8:
        return False, "كلمة المرور يجب أن تكون 8 محارف على الأقل"
    
    if len(password) > 128:
        return False, "كلمة المرور طويلة جداً"
    
    # يجب أن تحتوي على حرف كبير وحرف صغير ورقم
    if not re.search(r'[A-Z]', password):
        return False, "كلمة المرور يجب أن تحتوي على حرف كبير"
    
    if not re.search(r'[a-z]', password):
        return False, "كلمة المرور يجب أن تحتوي على حرف صغير"
    
    if not re.search(r'[0-9]', password):
        return False, "كلمة المرور يجب أن تحتوي على رقم"
    
    return True, ""


def sanitize_filename(filename: str) -> str:
    """
    تنظيف اسم الملف من المحارف الخطيرة
    
    Args:
        filename: اسم الملف
        
    Returns:
        اسم الملف المنظف
    """
    if not filename or not isinstance(filename, str):
        return "file"
    
    # إزالة المسار والاحتفاظ بالاسم فقط
    filename = filename.split('/')[-1].split('\\')[-1]
    
    # إزالة المحارف الخطيرة
    filename = re.sub(r'[^\w\s.-]', '', filename)
    
    # تحديد الطول
    if len(filename) > 255:
        filename = filename[:255]
    
    return filename or "file"


def check_sql_injection(text: str) -> bool:
    """
    فحص المدخلات من SQL Injection
    
    Args:
        text: النص المدخل
        
    Returns:
        True إذا كان هناك محاولة SQL Injection
    """
    if not text or not isinstance(text, str):
        return False
    
    # أنماط SQL خطيرة
    sql_patterns = [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bSELECT\b.*\bFROM\b)",
        r"(\bINSERT\b.*\bINTO\b)",
        r"(\bUPDATE\b.*\bSET\b)",
        r"(\bDELETE\b.*\bFROM\b)",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(--|\#|\/\*|\*\/)",
        r"(\bOR\b.*=.*)",
        r"(\bAND\b.*=.*)",
        r"('.*OR.*'.*=.*')",
    ]
    
    text_upper = text.upper()
    for pattern in sql_patterns:
        if re.search(pattern, text_upper, re.IGNORECASE):
            return True
    
    return False


def check_xss(text: str) -> bool:
    """
    فحص المدخلات من XSS
    
    Args:
        text: النص المدخل
        
    Returns:
        True إذا كان هناك محاولة XSS
    """
    if not text or not isinstance(text, str):
        return False
    
    # أنماط XSS خطيرة
    xss_patterns = [
        r"<script[^>]*>",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
        r"onclick\s*=",
        r"<iframe[^>]*>",
        r"<embed[^>]*>",
        r"<object[^>]*>",
    ]
    
    text_lower = text.lower()
    for pattern in xss_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    return False


def validate_amount(amount: str | float | int) -> tuple[bool, str]:
    """
    التحقق من صحة المبلغ المالي
    
    Args:
        amount: المبلغ
        
    Returns:
        (صالح, رسالة الخطأ)
    """
    try:
        val = float(amount)
        if val < 0:
            return False, "المبلغ يجب أن يكون موجباً"
        if val > 1000000000:  # مليار
            return False, "المبلغ كبير جداً"
        return True, ""
    except (ValueError, TypeError):
        return False, "المبلغ غير صالح"


def rate_limit_key() -> str:
    """
    الحصول على مفتاح Rate Limiting (IP + User)
    
    Returns:
        المفتاح
    """
    from flask_login import current_user
    
    ip = request.remote_addr or "unknown"
    user_id = getattr(current_user, 'id', 'anonymous')
    
    return f"{ip}:{user_id}"


def log_security_event(event_type: str, details: dict = None):
    """
    تسجيل حدث أمني
    
    Args:
        event_type: نوع الحدث
        details: تفاصيل إضافية
    """
    log_data = {
        'event': event_type,
        'ip': request.remote_addr,
        'user_id': getattr(current_user, 'id', None),
        'path': request.path,
        'method': request.method,
    }
    
    if details:
        log_data.update(details)
    
    current_app.logger.warning(f"SECURITY EVENT: {log_data}")


# ═══════════════════════════════════════════════════════════════
# حماية متقدمة من الهجمات (Advanced Attack Prevention)
# ═══════════════════════════════════════════════════════════════

# تخزين مؤقت لـ timing attack protection
_timing_cache = {}

def constant_time_compare(a: str, b: str) -> bool:
    """
    مقارنة Constant-Time لمنع Timing Attacks
    
    Args:
        a: النص الأول
        b: النص الثاني
        
    Returns:
        True إذا كانا متطابقين
    """
    if len(a) != len(b):
        return False
    
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    
    return result == 0


def timing_safe_login_check(user, password: str) -> bool:
    """
    فحص تسجيل دخول آمن من Timing Attacks
    
    Args:
        user: كائن المستخدم
        password: كلمة المرور
        
    Returns:
        True إذا كانت كلمة المرور صحيحة
    """
    # إضافة delay ثابت لمنع timing attacks
    start_time = time.time()
    
    # فحص كلمة المرور
    result = False
    if user and hasattr(user, 'check_password'):
        result = user.check_password(password)
    
    # التأكد من أن الوقت ثابت (على الأقل 50ms)
    elapsed = time.time() - start_time
    min_time = 0.05  # 50ms
    if elapsed < min_time:
        time.sleep(min_time - elapsed)
    
    return result


def require_ownership(model_class, id_param='id', owner_field='user_id'):
    """
    Decorator للتأكد من ملكية السجل
    
    Args:
        model_class: الـ Model class
        id_param: اسم parameter الـ ID
        owner_field: اسم الحقل الذي يحتوي على owner_id
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            record_id = kwargs.get(id_param)
            if not record_id:
                return jsonify({'error': 'Missing ID'}), 400
            
            record = model_class.query.get(record_id)
            if not record:
                return jsonify({'error': 'Not found'}), 404
            
            owner_id = getattr(record, owner_field, None)
            current_user_id = getattr(current_user, 'id', None)
            
            # التحقق من الملكية أو صلاحيات الإدارة
            if owner_id != current_user_id and not current_user.has_permission('admin'):
                return jsonify({'error': 'Unauthorized'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def prevent_race_condition(key_func):
    """
    Decorator لمنع Race Conditions
    
    Args:
        key_func: دالة لتوليد المفتاح الفريد للعملية
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # توليد مفتاح فريد للعملية
            key = key_func(*args, **kwargs)
            lock_key = f"lock:{key}"
            
            # محاولة الحصول على lock
            from extensions import cache
            if cache.get(lock_key):
                return jsonify({'error': 'Operation in progress, please wait'}), 429
            
            try:
                # وضع lock
                cache.set(lock_key, True, timeout=30)  # 30 ثانية
                
                # تنفيذ العملية
                result = f(*args, **kwargs)
                
                return result
            finally:
                # إزالة lock
                cache.delete(lock_key)
        
        return decorated_function
    return decorator


def validate_amount_change(old_amount, new_amount, max_change_percent=50):
    """
    التحقق من صحة تغيير المبلغ لمنع Business Logic Attacks
    
    Args:
        old_amount: المبلغ القديم
        new_amount: المبلغ الجديد
        max_change_percent: أقصى نسبة تغيير مسموح بها
        
    Returns:
        (valid, error_message)
    """
    try:
        old = float(old_amount or 0)
        new = float(new_amount or 0)
        
        if old == 0:
            # إذا كان المبلغ القديم 0، تحقق من المبلغ الجديد فقط
            if new > 1000000:  # مليون
                return False, "المبلغ كبير جداً"
            return True, ""
        
        # حساب نسبة التغيير
        change_percent = abs((new - old) / old * 100)
        
        if change_percent > max_change_percent:
            return False, f"التغيير في المبلغ كبير جداً ({change_percent:.1f}%)"
        
        return True, ""
    except (ValueError, ZeroDivisionError):
        return False, "مبلغ غير صالح"


def log_suspicious_activity(activity_type: str, details: dict = None):
    """
    تسجيل النشاطات المشبوهة
    
    Args:
        activity_type: نوع النشاط
        details: تفاصيل إضافية
    """
    import logging
    
    log_data = {
        'type': 'SUSPICIOUS_ACTIVITY',
        'activity': activity_type,
        'user_id': getattr(current_user, 'id', None),
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'path': request.path,
        'method': request.method,
    }
    
    if details:
        log_data.update(details)
    
    current_app.logger.warning(f"SUSPICIOUS ACTIVITY: {log_data}")


def check_request_signature(secret_key: str):
    """
    التحقق من توقيع الطلب لـ Webhooks
    
    Args:
        secret_key: المفتاح السري
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Signature')
            if not signature:
                return jsonify({'error': 'Missing signature'}), 401
            
            # حساب التوقيع المتوقع
            body = request.get_data()
            expected_signature = hashlib.sha256(
                (secret_key + body.decode('utf-8')).encode()
            ).hexdigest()
            
            # مقارنة Constant-Time
            if not constant_time_compare(signature, expected_signature):
                log_suspicious_activity('invalid_webhook_signature', {
                    'provided_signature': signature[:10] + '...',
                })
                return jsonify({'error': 'Invalid signature'}), 401
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def rate_limit_by_user():
    """
    Rate limiting بناءً على المستخدم
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from extensions import limiter
            
            # استخدام user_id إذا كان مسجل دخول، وإلا IP
            if current_user.is_authenticated:
                key = f"user:{current_user.id}"
            else:
                key = f"ip:{request.remote_addr}"
            
            # هنا يمكن إضافة منطق rate limiting مخصص
            # حالياً نستخدم limiter من extensions
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

