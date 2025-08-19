# -*- coding: utf-8 -*-
import os
from datetime import timedelta
from dotenv import load_dotenv

try:
    from sqlalchemy.pool import StaticPool
except Exception:
    StaticPool = None

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))
load_dotenv(os.path.join(basedir, ".env.txt"))

def _bool(v: str, default=False):
    return (v if v is not None else str(default)).lower() in ("true", "1", "yes", "y")

def _sqlite_engine_opts(uri: str, testing: bool):
    opts = {"connect_args": {"timeout": 30}}
    if testing and uri.startswith("sqlite"):
        if StaticPool is not None:
            opts["poolclass"] = StaticPool
        opts["connect_args"]["check_same_thread"] = False
    return opts

def _int(env_name: str, default: int):
    try:
        return int(os.environ.get(env_name, str(default)))
    except Exception:
        return default

def _float(env_name: str, default: float):
    try:
        return float(os.environ.get(env_name, str(default)))
    except Exception:
        return default

class Config:
    FLASK_APP = os.environ.get("FLASK_APP", "garage_manager.app:create_app")
    DEBUG = _bool(os.environ.get("DEBUG"), False)
    SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-secret-key" if DEBUG else None)
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in production")
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = _int("PORT", 5000)

    _db_uri = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(basedir,'app.db')}"
    if _db_uri.startswith("postgres://"):
        _db_uri = _db_uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = _bool(os.environ.get("SQLALCHEMY_TRACK_MODIFICATIONS"), False)
    SQLALCHEMY_ENGINE_OPTIONS = _sqlite_engine_opts(SQLALCHEMY_DATABASE_URI, testing=False)
    SQLALCHEMY_ENGINE_OPTIONS.setdefault("pool_pre_ping", True)
    SQLALCHEMY_ENGINE_OPTIONS.setdefault("pool_recycle", 1800)

    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), not DEBUG)
    REMEMBER_COOKIE_DURATION = timedelta(days=_int("REMEMBER_DAYS", 14))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_HOURS", 12))
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "gm_session")

    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 32) * 1024 * 1024

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USE_SSL = _bool(os.environ.get("MAIL_USE_SSL"), False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "MyApp <noreply@example.com>")

    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("SOCKETIO_MESSAGE_QUEUE")
    SOCKETIO_CORS_ORIGINS = os.environ.get("SOCKETIO_CORS_ORIGINS", "*")
    SOCKETIO_PING_TIMEOUT = _int("SOCKETIO_PING_TIMEOUT", 20)
    SOCKETIO_PING_INTERVAL = _int("SOCKETIO_PING_INTERVAL", 25)
    SOCKETIO_MAX_HTTP_BUFFER_SIZE = _int("SOCKETIO_MAX_HTTP_BUFFER_SIZE", 100_000_000)

    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)
    WTF_CSRF_TIME_LIMIT = None

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    CORS_SUPPORTS_CREDENTIALS = _bool(os.environ.get("CORS_SUPPORTS_CREDENTIALS"), True)

    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per day;50 per hour")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = _bool(os.environ.get("RATELIMIT_HEADERS_ENABLED"), True)

    ITEMS_PER_PAGE = _int("ITEMS_PER_PAGE", 10)
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
    SENTRY_TRACES = _float("SENTRY_TRACES", 0.0)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SHOP_PREPAID_RATE = _float("SHOP_PREPAID_RATE", 0.20)
    SHOP_WAREHOUSE_IDS = None
    SHOP_WAREHOUSE_TYPES = ['MAIN', 'INVENTORY']

    USE_PROXYFIX = _bool(os.environ.get("USE_PROXYFIX"), False)
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https" if not DEBUG else "http")
    DEV_EMAIL = os.environ.get("DEV_EMAIL", "rafideen.ahmadghannam@gmail.com")

    PASSWORD_HASH_METHOD = os.environ.get("PASSWORD_HASH_METHOD", "scrypt")

    CARD_ENC_KEY = os.environ.get("CARD_ENC_KEY", "")
    DEFAULT_PRODUCT_IMAGE = os.environ.get("DEFAULT_PRODUCT_IMAGE", "products/default.png")

class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_DEFAULT = ""
    SESSION_COOKIE_SECURE = False
    LOGIN_DISABLED = True
    PERMISSION_DISABLED = True
    MAIL_SUPPRESS_SEND = True
    _SQLA_OPTS = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if StaticPool is not None:
        _SQLA_OPTS["poolclass"] = StaticPool
    SQLALCHEMY_ENGINE_OPTIONS = _SQLA_OPTS
    PASSWORD_HASH_METHOD = os.environ.get("TEST_PASSWORD_HASH_METHOD", "pbkdf2:sha256:60000")
