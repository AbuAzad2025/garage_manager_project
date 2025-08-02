import os
from dotenv import load_dotenv

# الموقع الفعلي للملف داخل الحزمة
basedir = os.path.abspath(os.path.dirname(__file__))

# تحميل متغيرات البيئة من .env و .env.txt
load_dotenv(os.path.join(basedir, ".env"))
load_dotenv(os.path.join(basedir, ".env.txt"))

class Config:
    # نقطة الدخول الافتراضية لتشغيل التطبيق
    FLASK_APP  = os.environ.get("FLASK_APP", "garage_manager.app:create_app")
    FLASK_ENV  = os.environ.get("FLASK_ENV", "production")

    DEBUG      = os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")
    SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-secret-key" if DEBUG else None)
    if not SECRET_KEY:
        raise RuntimeError("Environment variable SECRET_KEY must be set for production")

    # ------ Host & Port (used by run commands) ------
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))

    # ------ Database ------
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") \
        or f"sqlite:///{os.path.join(basedir, 'app.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = os.environ.get(
        "SQLALCHEMY_TRACK_MODIFICATIONS", "False"
    ).lower() in ("true", "1", "yes")

    # ------ Flask-Login ------
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_PROTECTION       = "strong"

    # ------ Mail (Flask-Mail) ------
    MAIL_SERVER         = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT           = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS        = os.environ.get("MAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
    MAIL_USE_SSL        = os.environ.get("MAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER",
        "MyApp <noreply@example.com>"
    )

    # ------ Twilio / WhatsApp ------
    TWILIO_ACCOUNT_SID     = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN      = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")

    # ------ Redis (sessions, cache, Celery broker/backend) ------
    REDIS_URL             = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL     = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    # ------ CSRF Protection ------
    WTF_CSRF_ENABLED    = os.environ.get("WTF_CSRF_ENABLED", "True").lower() in ("true", "1", "yes")
    WTF_CSRF_TIME_LIMIT = None

    # ------ CORS ------
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # ------ Rate Limiting ------
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per day;50 per hour")

    # ------ Pagination ------
    # عدد العناصر في الصفحة الواحدة للتجزئة (pagination)
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 10))

    # ------ Sentry (error tracking) ------
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

    # ------ Logging ------
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
