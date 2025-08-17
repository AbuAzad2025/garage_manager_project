# -*- coding: utf-8 -*-
import os
from datetime import datetime
from flask import Flask, url_for
from werkzeug.routing import BuildError
from flask_cors import CORS
from flask_login import AnonymousUserMixin, current_user
from flask_wtf.csrf import generate_csrf
from jinja2 import ChoiceLoader, FileSystemLoader

from config import Config
from extensions import db, migrate, login_manager, socketio, mail, csrf, limiter
from utils import (
    qr_to_base64,
    format_currency,
    format_percent,
    format_date,
    format_datetime,
    yes_no,
    status_label,
    init_app as utils_init_app,
)
from cli import seed_roles

from routes.auth import auth_bp
from routes.main import main_bp
from routes.users import users_bp
from routes.service import service_bp
from routes.customers import customers_bp
from routes.sales import sales_bp
from routes.notes import notes_bp
from routes.reports import reports_bp
from routes.shop import shop_bp
from routes.expenses import expenses_bp
from routes.vendors import vendors_bp
from routes.shipments import shipments_bp
from routes.warehouses import warehouse_bp
from routes.payments import payments_bp
from routes.permissions import permissions_bp
from routes.roles import roles_bp
from routes.api import bp as api_bp

from models import User, Role


class MyAnonymousUser(AnonymousUserMixin):
    def has_permission(self, perm_name):
        return False


def _init_sentry(app: Flask) -> None:
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.0")),
        )
        app.logger.info("Sentry initialized.")
    except ImportError:
        app.logger.warning("Sentry SDK not installed; skipping Sentry init.")


def create_app(config_object=Config, test_config=None) -> Flask:
    # allow passing a dict as test config
    if isinstance(config_object, dict) and test_config is None:
        test_config = config_object
        config_object = Config

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_object)
    if test_config:
        app.config.update(test_config)

    # ensure Arabic JSON ok
    app.config.setdefault("JSON_AS_ASCII", False)

    # testing flags
    app.testing = app.config.get("TESTING", False)
    if app.testing:
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["WTF_CSRF_CHECK_DEFAULT"] = False
        app.config.setdefault("RATELIMIT_ENABLED", False)

    # .env (optional)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    # SQLAlchemy engine tuning (esp. sqlite in tests)
    engine_opts = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    connect_args = engine_opts.setdefault("connect_args", {})
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite"):
        connect_args.setdefault("timeout", 30)
        if app.config.get("TESTING"):
            from sqlalchemy.pool import StaticPool

            engine_opts["poolclass"] = StaticPool
            connect_args["check_same_thread"] = False

    # init extensions
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.anonymous_user = MyAnonymousUser
    try:
        # some versions expose this
        login_manager.session_protection = None
    except Exception:
        pass

    csrf.init_app(app)

    # rate limit
    app.config.setdefault("RATELIMIT_STORAGE_URI", os.getenv("RATELIMIT_STORAGE_URI", "memory://"))
    if app.config.get("TESTING"):
        app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        limiter.default_limits = [default_limit]

    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
    )
    mail.init_app(app)

    # project utils
    utils_init_app(app)

    # sentry (optional)
    _init_sentry(app)

    # proxy fix (optional)
    if app.config.get("USE_PROXYFIX"):
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix

            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
        except Exception:
            app.logger.warning("ProxyFix not available; set USE_PROXYFIX=False if unused.")

    # Template loaders (allow extra folder)
    extra_template_paths = [
        os.path.join(app.root_path, "templates"),
        os.path.join(app.root_path, "routes", "templates"),
    ]
    app.jinja_loader = ChoiceLoader(
        [FileSystemLoader(p) for p in extra_template_paths]
        + ([app.jinja_loader] if app.jinja_loader else [])
    )

    # ---- Context processors (ALL inside create_app) ----
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf)

    # single authoritative `has_perm` with alias support
    def inject_permissions():
        alias_map = {
            "backup_database": {"backup_database", "backup", "backup_db", "download_backup", "db_backup"},
            "restore_database": {"restore_database", "restore", "restore_db", "upload_backup", "db_restore"},
        }
        ATTRS = ("code", "name", "slug", "perm", "permission", "value")

        def _collect_user_perms(u):
            perms = set()

            # from role
            role = getattr(u, "role", None)
            if role is not None:
                rp = getattr(role, "permissions", None)
                if rp:
                    for p in rp:
                        for a in ATTRS:
                            v = getattr(p, a, None)
                            if v:
                                perms.add(str(v).strip().lower())

            # from user direct / extras
            up = getattr(u, "permissions", None) or getattr(u, "extra_permissions", None)
            if up:
                for p in up:
                    if isinstance(p, str):
                        perms.add(p.strip().lower())
                    else:
                        for a in ATTRS:
                            v = getattr(p, a, None)
                            if v:
                                perms.add(str(v).strip().lower())
            return perms

        def has_perm(code: str) -> bool:
            try:
                u = current_user
                if not getattr(u, "is_authenticated", False):
                    return False

                target = (code or "").strip().lower()
                # expand asked code to known aliases (support both names in templates/tests)
                targets = alias_map.get(target, {target})

                perms_lower = _collect_user_perms(u)

                # if any alias of the asked code is present in user perms, allow
                return any(t in perms_lower for t in targets)
            except Exception:
                return False

        return {"has_perm": has_perm}

    app.context_processor(inject_permissions)
    # ---- End context processors ----

    # Jinja filters & globals
    def _safe_number_format(v, digits=2):
        try:
            return f"{float(v):,.{digits}f}"
        except (TypeError, ValueError):
            return f"{0:,.{digits}f}"

    app.jinja_env.filters["qr_to_base64"] = qr_to_base64
    app.jinja_env.filters["format_currency"] = format_currency
    app.jinja_env.filters["format_percent"] = format_percent
    app.jinja_env.filters["yes_no"] = yes_no
    app.jinja_env.filters["number_format"] = _safe_number_format
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["status_label"] = status_label

    def url_for_any(*endpoints, **values):
        for ep in endpoints:
            try:
                return url_for(ep, **values)
            except BuildError:
                continue
        return "#"

    app.jinja_env.globals["url_for_any"] = url_for_any
    app.jinja_env.globals["now"] = datetime.utcnow

    # blueprints
    for bp in (
        api_bp,
        auth_bp,
        main_bp,
        users_bp,
        service_bp,
        customers_bp,
        sales_bp,
        notes_bp,
        reports_bp,
        shop_bp,
        expenses_bp,
        vendors_bp,
        shipments_bp,
        warehouse_bp,
        payments_bp,
        permissions_bp,
        roles_bp,
    ):
        app.register_blueprint(bp)

    # CORS for API
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*"),
                               "supports_credentials": app.config.get("CORS_SUPPORTS_CREDENTIALS", True)}},
    )

    # login loader
    @login_manager.user_loader
    def load_user(user_id):
        from sqlalchemy.orm import joinedload

        try:
            return db.session.get(
                User,
                int(user_id),
                options=[joinedload(User.role).joinedload(Role.permissions)],
            )
        except Exception:
            return None

    # shell ctx
    @app.shell_context_processor
    def _ctx():
        return {"db": db, "User": User}

    # CLI
    app.cli.add_command(seed_roles)

    return app


# create the app instance for WSGI/pytest imports
app = create_app()
__all__ = ["app", "db"]

if __name__ == "__main__":
    socketio.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )
