# -*- coding: utf-8 -*-
import os
from datetime import timedelta
from dotenv import load_dotenv

# مهم: StaticPool للاختبارات مع SQLite
try:
    from sqlalchemy.pool import StaticPool
except Exception:
    StaticPool = None  # للإنتاج على قواعد ثانية مش لازم

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))
load_dotenv(os.path.join(basedir, ".env.txt"))

def _bool(v: str, default=False):
    return (v if v is not None else str(default)).lower() in ("true", "1", "yes", "y")

def _sqlite_engine_opts(uri: str, testing: bool):
    """
    خيارات محرك SQLAlchemy الخاصة بـ SQLite لتفادي database is locked.
    - في الاختبارات: StaticPool + check_same_thread=False (اتصال واحد مشترك).
    - خارج الاختبارات: زيادة timeout فقط.
    """
    opts = {"connect_args": {"timeout": 30}}
    if testing and uri.startswith("sqlite"):
        if StaticPool is not None:
            opts["poolclass"] = StaticPool
        opts["connect_args"]["check_same_thread"] = False
    return opts

class Config:
    FLASK_APP = os.environ.get("FLASK_APP", "garage_manager.app:create_app")
    DEBUG = _bool(os.environ.get("DEBUG"), False)

    SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-secret-key" if DEBUG else None)
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in production")

    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))

    _db_uri = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(basedir,'app.db')}"
    if _db_uri.startswith("postgres://"):
        _db_uri = _db_uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = _bool(os.environ.get("SQLALCHEMY_TRACK_MODIFICATIONS"), False)

    # 🔒 خيارات محرك SQLAlchemy (آمنة للإنتاج ومفيدة لـ SQLite)
    SQLALCHEMY_ENGINE_OPTIONS = _sqlite_engine_opts(SQLALCHEMY_DATABASE_URI, testing=False)

    # Cookies / Sessions
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), not DEBUG)
    REMEMBER_COOKIE_DURATION = timedelta(days=int(os.environ.get("REMEMBER_DAYS", "14")))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HOURS", "12")))

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USE_SSL = _bool(os.environ.get("MAIL_USE_SSL"), False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "MyApp <noreply@example.com>")

    # Integrations
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    # Socket.IO
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("SOCKETIO_MESSAGE_QUEUE")

    # CSRF / CORS / Rate limit
    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)
    WTF_CSRF_TIME_LIMIT = None
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per day;50 per hour")

    # App settings
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 10))
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SHOP_PREPAID_RATE = float(os.environ.get("SHOP_PREPAID_RATE", "0.20"))
    SHOP_WAREHOUSE_IDS = None
    SHOP_WAREHOUSE_TYPES = ['MAIN', 'INVENTORY']

    # ✅ طريقة الهاش قابلة للتهيئة (افتراضيًا scrypt في الإنتاج)
    PASSWORD_HASH_METHOD = os.environ.get("PASSWORD_HASH_METHOD", "scrypt")


class TestConfig(Config):
    TESTING = True
    DEBUG = True

    # ✅ استخدم SQLite in-memory مع اتصال مشترك واحد
    # "sqlite://": ذاكرة مشتركة مع StaticPool، أفضل من ":memory:" الافتراضية لكل اتصال.
    SQLALCHEMY_DATABASE_URI = "sqlite://"

    # ✅ عطل CSRF والـ rate limit الافتراضي بالكامل للاختبارات (منع 429)
    WTF_CSRF_ENABLED = False
    RATELIMIT_DEFAULT = ""   # لا حدود افتراضية أثناء التست

    # ✅ تعطيل القيود على تسجيل الدخول/الصلاحيات لو أردتها بالتستات
    LOGIN_DISABLED = True
    PERMISSION_DISABLED = True
    SESSION_COOKIE_SECURE = False

    # ✅ أهم شيء: StaticPool + check_same_thread=False لتفادي database is locked
    _SQLA_OPTS = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if StaticPool is not None:
        _SQLA_OPTS["poolclass"] = StaticPool
    SQLALCHEMY_ENGINE_OPTIONS = _SQLA_OPTS

    # ✅ بالاختبارات استخدم pbkdf2 خفيف تلقائيًا (قابل للضبط عبر البيئة)
    PASSWORD_HASH_METHOD = os.environ.get("TEST_PASSWORD_HASH_METHOD", "pbkdf2:sha256:60000")
