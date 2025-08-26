# -*- coding: utf-8 -*-
from __future__ import annotations

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
