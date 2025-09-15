import os
from datetime import timedelta
from dotenv import load_dotenv
import logging

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, "instance")
os.makedirs(instance_dir, exist_ok=True)

load_dotenv(os.path.join(basedir, ".env"))
load_dotenv(os.path.join(basedir, ".env.txt"))


def _bool(v: str, default=False):
    return (v if v is not None else str(default)).lower() in ("true", "1", "yes", "y")


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


def _csv_int(env_name: str):
    raw = os.environ.get(env_name, "")
    vals = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            vals.append(int(x))
        except Exception:
            continue
    return vals or None


def _csv_str(env_name: str, default_list):
    raw = os.environ.get(env_name, "")
    vals = [x.strip() for x in raw.split(",") if x.strip()]
    return vals or list(default_list)


class Config:
    FLASK_APP = os.environ.get("FLASK_APP", "garage_manager.app:create_app")
    DEBUG = _bool(os.environ.get("DEBUG"), False)
    SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-secret-key" if DEBUG else None)
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in production")
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = _int("PORT", 5000)
    _db_uri = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(instance_dir, 'app.db')}"
    if _db_uri.startswith("postgres://"):
        _db_uri = _db_uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = _bool(os.environ.get("SQLALCHEMY_TRACK_MODIFICATIONS"), False)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30},
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    SQLALCHEMY_ECHO = False
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), not DEBUG)
    REMEMBER_COOKIE_DURATION = timedelta(days=_int("REMEMBER_DAYS", 14))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_HOURS", 12))
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "gm_session")
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 16) * 1024 * 1024
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
    SHOP_PREPAID_RATE = _float("SHOP_PREPAID_RATE", 0.20)
    SHOP_WAREHOUSE_IDS = _csv_int("SHOP_WAREHOUSE_IDS")
    SHOP_WAREHOUSE_TYPES = _csv_str("SHOP_WAREHOUSE_TYPES", ["MAIN", "INVENTORY"])
    USE_PROXYFIX = _bool(os.environ.get("USE_PROXYFIX"), False)
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https" if not DEBUG else "http")
    DEV_EMAIL = os.environ.get("DEV_EMAIL", "rafideen.ahmadghannam@gmail.com")
    PASSWORD_HASH_METHOD = os.environ.get("PASSWORD_HASH_METHOD", "scrypt")
    CARD_ENC_KEY = os.environ.get("CARD_ENC_KEY", "")
    REVEAL_PAN_ENABLED = _bool(os.environ.get("REVEAL_PAN_ENABLED"), False)
    DEFAULT_PRODUCT_IMAGE = os.environ.get("DEFAULT_PRODUCT_IMAGE", "products/default.png")
    SUPER_USER_EMAILS = os.environ.get("SUPER_USER_EMAILS", "")
    SUPER_USER_IDS = os.environ.get("SUPER_USER_IDS", "")
    ADMIN_USER_EMAILS = os.environ.get("ADMIN_USER_EMAILS", "")
    ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "")
    PERMISSIONS_REQUIRE_ALL = _bool(os.environ.get("PERMISSIONS_REQUIRE_ALL"), False)
    BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(instance_dir, "backups"))
    BACKUP_DB_DIR = os.path.join(BACKUP_DIR, "db")
    BACKUP_SQL_DIR = os.path.join(BACKUP_DIR, "sql")
    BACKUP_KEEP_LAST = _int("BACKUP_KEEP_LAST", 5)
    BACKUP_DB_INTERVAL = timedelta(hours=1)
    BACKUP_SQL_INTERVAL = timedelta(hours=24)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    JSON_LOGS = _bool(os.environ.get("JSON_LOGS"), False)
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))
    APP_VERSION = os.environ.get("APP_VERSION", None)
    APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "production"))
    IMPORT_TMP_DIR = os.environ.get("IMPORT_TMP_DIR") or os.path.join(instance_dir, "imports")
    IMPORT_REPORT_DIR = os.environ.get("IMPORT_REPORT_DIR") or os.path.join(instance_dir, "imports", "reports")
    ONLINE_GATEWAY_DEFAULT = (os.environ.get("ONLINE_GATEWAY_DEFAULT") or "blooprint").lower()
    BLOOPRINT_WEBHOOK_SECRET = os.environ.get("BLOOPRINT_WEBHOOK_SECRET", "")


logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
