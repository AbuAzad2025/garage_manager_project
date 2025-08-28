# -*- coding: utf-8 -*-
from __future__ import annotations

import logging, sys, json
from datetime import datetime
from flask import g, has_request_context

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
        else:
            record.request_id = "-"
        return True

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for k, v in record.__dict__.items():
            if k.startswith("_"): continue
            if k in ("name","msg","args","levelname","levelno","pathname","filename","module","exc_info",
                     "exc_text","stack_info","lineno","funcName","created","msecs","relativeCreated",
                     "thread","threadName","processName","process","request_id"):
                continue
            try:
                json.dumps({k: v})
                base[k] = v
            except Exception:
                base[k] = str(v)
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)

def setup_logging(app):
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())
    if app.config.get("JSON_LOGS"):
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(request_id)s %(name)s: %(message)s"
        ))
    for lg in (app.logger, logging.getLogger(), logging.getLogger("sqlalchemy.engine")):
        lg.handlers.clear()
        lg.setLevel(level)
        lg.addHandler(handler)
        lg.propagate = False

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
except Exception:
    sentry_sdk = None

def setup_sentry(app):
    dsn = app.config.get("SENTRY_DSN") or ""
    if not dsn or not sentry_sdk:
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0),
        profiles_sample_rate=app.config.get("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
        environment=app.config.get("APP_ENV", "production"),
        release=app.config.get("APP_VERSION") or None,
        send_default_pii=False,
        max_breadcrumbs=100,
    )

import os, sqlite3, glob
from apscheduler.schedulers.background import BackgroundScheduler

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy(session_options={"expire_on_commit": False})
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()

socketio = SocketIO(
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

def _rate_limit_key():
    try:
        from flask_login import current_user
        if getattr(current_user, "is_authenticated", False):
            return f"user:{current_user.get_id()}"
    except Exception:
        pass
    return get_remote_address()

limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[],
)

scheduler = BackgroundScheduler()

@event.listens_for(Engine, "connect")
def _sqlite_pragmas_on_connect(dbapi_connection, connection_record):
    try:
        import sqlite3
        if isinstance(dbapi_connection, sqlite3.Connection):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    except Exception:
        pass

def perform_backup_db(app):
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:///"):
        return
    db_path = uri.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return
    backup_dir = app.config.get("BACKUP_DB_DIR")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    keep_last = app.config.get("BACKUP_KEEP_LAST", 5)
    backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.db")))
    if len(backups) > keep_last:
        for old in backups[:-keep_last]:
            try:
                os.remove(old)
            except Exception:
                pass

def perform_backup_sql(app):
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:///"):
        return
    db_path = uri.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return
    backup_dir = app.config.get("BACKUP_SQL_DIR")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.sql")
    conn = sqlite3.connect(db_path)
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()
    keep_last = app.config.get("BACKUP_KEEP_LAST", 5)
    backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.sql")))
    if len(backups) > keep_last:
        for old in backups[:-keep_last]:
            try:
                os.remove(old)
            except Exception:
                pass

def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = app.config.get("LOGIN_VIEW", "auth.login")
    login_manager.login_message_category = app.config.get("LOGIN_MESSAGE_CATEGORY", "warning")

    csrf.init_app(app)
    mail.init_app(app)

    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE"),
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
        logger=app.config.get("SOCKETIO_LOGGER", False),
        engineio_logger=app.config.get("SOCKETIO_ENGINEIO_LOGGER", False),
        ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 20),
        ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 25),
        max_http_buffer_size=app.config.get("SOCKETIO_MAX_HTTP_BUFFER_SIZE", 100_000_000),
    )

    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    app.config.setdefault("RATELIMIT_EXEMPT_SUPER", True)

    limiter.init_app(app)

    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        if isinstance(default_limit, (list, tuple)):
            limiter.default_limits = [str(x).strip() for x in default_limit if str(x).strip()]
        else:
            parts = [p.strip() for p in str(default_limit).split(";") if p.strip()]
            limiter.default_limits = parts

    if app.config.get("RATELIMIT_EXEMPT_SUPER", True):
        @limiter.request_filter
        def _exempt_super_admin():
            try:
                from flask_login import current_user
                if getattr(current_user, "is_authenticated", False):
                    if getattr(current_user, "is_super_role", False):
                        return True
                    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).strip().lower()
                    if role_name == "super_admin":
                        return True
            except Exception:
                return False
            return False

    scheduler.add_job(lambda: perform_backup_db(app), "interval", seconds=app.config.get("BACKUP_DB_INTERVAL").total_seconds(), id="db_backup", replace_existing=True)
    scheduler.add_job(lambda: perform_backup_sql(app), "interval", seconds=app.config.get("BACKUP_SQL_INTERVAL").total_seconds(), id="sql_backup", replace_existing=True)
    scheduler.start()
