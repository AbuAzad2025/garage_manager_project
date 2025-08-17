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
    _expand_perms as _perm_expand,
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
    if isinstance(config_object, dict) and test_config is None:
        test_config = config_object
        config_object = Config

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_object)
    if test_config:
        app.config.update(test_config)

    app.config.setdefault("JSON_AS_ASCII", False)

    app.testing = app.config.get("TESTING", False)
    if app.testing:
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["WTF_CSRF_CHECK_DEFAULT"] = False
        app.config.setdefault("RATELIMIT_ENABLED", False)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    engine_opts = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    connect_args = engine_opts.setdefault("connect_args", {})
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite"):
        connect_args.setdefault("timeout", 30)
        if app.config.get("TESTING"):
            from sqlalchemy.pool import StaticPool
            engine_opts["poolclass"] = StaticPool
            connect_args["check_same_thread"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.anonymous_user = MyAnonymousUser
    try:
        login_manager.session_protection = None
    except Exception:
        pass

    csrf.init_app(app)

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

    utils_init_app(app)
    _init_sentry(app)

    if app.config.get("USE_PROXYFIX"):
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
        except Exception:
            app.logger.warning("ProxyFix not available; set USE_PROXYFIX=False if unused.")

    extra_template_paths = [
        os.path.join(app.root_path, "templates"),
        os.path.join(app.root_path, "routes", "templates"),
    ]
    app.jinja_loader = ChoiceLoader(
        [FileSystemLoader(p) for p in extra_template_paths]
        + ([app.jinja_loader] if app.jinja_loader else [])
    )

    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf)

    def inject_permissions():
        ATTRS = ("code", "name", "slug", "perm", "permission", "value")

        def _collect_user_perms(u):
            perms = set()
            role = getattr(u, "role", None)
            if role is not None:
                rp = getattr(role, "permissions", None)
                if rp:
                    for p in rp:
                        for a in ATTRS:
                            v = getattr(p, a, None)
                            if v:
                                perms.add(str(v).strip().lower())
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
                targets = {c.strip().lower() for c in _perm_expand(code)}
                perms_lower = _collect_user_perms(u)
                return bool(perms_lower & targets)
            except Exception:
                return False

        def has_any(*codes):
            return any(has_perm(c) for c in codes)

        def has_all(*codes):
            return all(has_perm(c) for c in codes)

        return {"has_perm": has_perm, "has_any": has_any, "has_all": has_all}

    app.context_processor(inject_permissions)

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

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*"),
                               "supports_credentials": app.config.get("CORS_SUPPORTS_CREDENTIALS", True)}},
    )

    @login_manager.user_loader
    def load_user(user_id):
        from sqlalchemy.orm import joinedload
        from sqlalchemy import select
        try:
            stmt = (
                select(User)
                .options(joinedload(User.role).joinedload(Role.permissions))
                .where(User.id == int(user_id))
            )
            return db.session.execute(stmt).scalar_one_or_none()
        except Exception:
            return None

    @app.shell_context_processor
    def _ctx():
        return {"db": db, "User": User}

    app.cli.add_command(seed_roles)

    return app


app = create_app()
__all__ = ["app", "db"]

if __name__ == "__main__":
    socketio.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )
