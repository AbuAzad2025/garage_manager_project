# -*- coding: utf-8 -*-
from __future__ import annotations

# Flask extensions
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# -----------------------------------------------------------------------------
# Core extensions singletons
# -----------------------------------------------------------------------------
# مهم: نمنع Expire للخصائص بعد commit لتفادي DetachedInstanceError على الكائنات
db = SQLAlchemy(session_options={"expire_on_commit": False})
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()

# SocketIO: يمكن تخصيص async_mode و message_queue من Config
socketio = SocketIO(
    cors_allowed_origins="*",
    logger=False,          # غيّرها True عند الحاجة للتصحيح
    engineio_logger=False  # غيّرها True عند الحاجة للتصحيح
)

# Limiter بدون حدود افتراضية هنا — نضبطها داخل create_app/init_extensions حسب الإعدادات
# سيستخدم key_func = get_remote_address افتراضيًا
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]  # يمكن ضبطها لاحقًا من Config عبر RATELIMIT_DEFAULT
)

# -----------------------------------------------------------------------------
# SQLite pragmas to reduce 'database is locked' in tests/dev (no-op for non-SQLite)
# -----------------------------------------------------------------------------
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def _sqlite_pragmas_on_connect(dbapi_connection, connection_record):
    """
    تُطبّق فقط على اتصالات SQLite. آمنة للإنتاج لأنها تتجاهل المحركات الأخرى.
    تهدف لتقليل 'database is locked' خلال التطوير/الاختبارات.
    """
    try:
        import sqlite3
        if isinstance(dbapi_connection, sqlite3.Connection):
            cur = dbapi_connection.cursor()
            # انتظر لغاية 30 ثانية قبل رمي 'database is locked'
            cur.execute("PRAGMA busy_timeout=30000")
            # وضع سجل المعاملات للحد من تعارض القراءة/الكتابة
            cur.execute("PRAGMA journal_mode=WAL")
            # توازن بين الأداء والمتانة
            cur.execute("PRAGMA synchronous=NORMAL")
            # تفعيل المفاتيح الأجنبية
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    except Exception:
        # لا نعطّل التطبيق إذا فشلت البراغمات
        pass


# -----------------------------------------------------------------------------
# Unified init function (يمكن استدعاؤها داخل create_app)
# -----------------------------------------------------------------------------
def init_extensions(app):
    """
    تهيئة كل الإكستنشنز وربطها بالتطبيق.
    تُقرأ الإعدادات الإنتاجية من app.config إذا كانت متوفّرة.
    """

    # --- SQLAlchemy / Alembic ---
    db.init_app(app)
    migrate.init_app(app, db)

    # --- Login ---
    login_manager.init_app(app)
    # صفحة تسجيل الدخول الافتراضية (لـ @login_required)
    login_manager.login_view = app.config.get("LOGIN_VIEW", "auth.login")
    login_manager.login_message_category = app.config.get("LOGIN_MESSAGE_CATEGORY", "warning")

    # --- CSRF/Mail ---
    csrf.init_app(app)
    mail.init_app(app)

    # --- Socket.IO ---
    # يمكن ضبط async_mode: "eventlet" / "gevent" / "threading" / None (auto)
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE"),  # اتركها None للاكتشاف التلقائي
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),  # مثل: "redis://localhost:6379/0"
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
        logger=app.config.get("SOCKETIO_LOGGER", False),
        engineio_logger=app.config.get("SOCKETIO_ENGINEIO_LOGGER", False),
        ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 20),
        ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 25),
        max_http_buffer_size=app.config.get("SOCKETIO_MAX_HTTP_BUFFER_SIZE", 100_000_000),
    )

    # --- Rate Limiter ---
    # يدعم Flask-Limiter قراءة الإعدادات من config تلقائيًا مثل:
    # RATELIMIT_STORAGE_URI (مثال: "redis://localhost:6379/3")
    # RATELIMIT_DEFAULT (مثال: "200/hour;50/minute")
    # RATELIMIT_HEADERS_ENABLED (افتراضيًا False، نفعّله هنا لتيسير المراقبة)
    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)
    limiter.init_app(app)

    # ضبط حدود افتراضية لو وُجدت في config
    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        # يمكن أن تكون سلسلة واحدة أو قائمة من السلاسل
        if isinstance(default_limit, (list, tuple)):
            limiter.default_limits = list(default_limit)
        else:
            limiter.default_limits = [str(default_limit)]

    # ملاحظات:
    # - لو تستخدم Redis أو غيره للتخزين، اضبط:
    #   app.config["RATELIMIT_STORAGE_URI"] = "redis://:password@host:6379/0"
    # - يمكنك استخدام ديكوراتور @limiter.limit("10/minute") على الراوتات الحساسة.

    # أي ضبط إضافي عام
    # مثال: تمكين/تعطيل تتبّع الأخطاء بإرسال رؤوس محدّدة
    if app.config.get("TESTING"):
        # أثناء الاختبار، من المفيد إطفاء بعض السلوكيات الثقيلة
        pass
