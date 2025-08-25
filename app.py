import os
from datetime import datetime
from flask import Flask, url_for, request, current_app, render_template
from werkzeug.routing import BuildError
from flask_cors import CORS
from flask_login import AnonymousUserMixin, current_user
from flask_wtf.csrf import generate_csrf
from jinja2 import ChoiceLoader, FileSystemLoader
from sqlalchemy import event
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
from models import User, Role, Permission, Customer
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
from routes.admin_reports import admin_reports_bp
from routes.parts import parts_bp
from routes.barcode import bp_barcode


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


@login_manager.user_loader
def load_user(user_id):
    from sqlalchemy.orm import joinedload, lazyload
    from sqlalchemy import select

    uid_str = str(user_id or "").strip()
    if ":" in uid_str:
        try:
            prefix, ident = uid_str.split(":", 1)
            ident = int(ident)
            prefix = prefix.lower()
        except Exception:
            return None

        if prefix == "u":
            stmt = (
                select(User)
                .options(joinedload(User.role).joinedload(Role.permissions))
                .where(User.id == ident)
            )
            return db.session.execute(stmt).scalar_one_or_none()

        if prefix == "c":
            stmt = select(Customer).options(lazyload("*")).where(Customer.id == ident)
            return db.session.execute(stmt).scalar_one_or_none()

        return None

    try:
        ident = int(uid_str)
    except Exception:
        return None

    stmt_user = (
        select(User)
        .options(joinedload(User.role).joinedload(Role.permissions))
        .where(User.id == ident)
    )
    user = db.session.execute(stmt_user).unique().scalar_one_or_none()
    if user:
        return user

    stmt_cust = select(Customer).options(lazyload("*")).where(Customer.id == ident)
    return db.session.execute(stmt_cust).scalar_one_or_none()


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_object)

    app.config.setdefault("JSON_AS_ASCII", False)

    if app.config.get("SERVER_NAME"):
        from urllib.parse import urlparse
        def _relative_url_for(self, endpoint, **values):
            rv = Flask.url_for(self, endpoint, **values)
            if not values.get("_external"):
                parsed = urlparse(rv)
                rv = parsed.path + ("?" + parsed.query if parsed.query else "")
            return rv
        app.url_for = _relative_url_for.__get__(app, Flask)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    engine_opts = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    connect_args = engine_opts.setdefault("connect_args", {})
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    engine_opts.setdefault("pool_pre_ping", True)
    engine_opts.setdefault("pool_recycle", 1800)

    if uri.startswith("sqlite"):
        connect_args.setdefault("timeout", 30)
    else:
        connect_args.pop("timeout", None)
        if uri.startswith(("postgresql", "postgresql+psycopg2")):
            connect_args.setdefault("connect_timeout", int(os.getenv("DB_CONNECT_TIMEOUT", "10")))
        elif uri.startswith(("mysql", "mysql+pymysql", "mysql+mysqldb")):
            connect_args.setdefault("connect_timeout", int(os.getenv("DB_CONNECT_TIMEOUT", "10")))

    db.init_app(app)
    migrate.init_app(app, db)

    @event.listens_for(db.session.__class__, "before_attach")
    def _dedupe_entities(session, instance):
        if isinstance(instance, (Role, Permission)) and getattr(instance, "id", None) is not None:
            key = session.identity_key(instance.__class__, (instance.id,))
            existing = session.identity_map.get(key)
            if existing is not None and existing is not instance:
                session.expunge(existing)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.anonymous_user = MyAnonymousUser
    try:
        login_manager.session_protection = None
    except Exception:
        pass

    csrf.init_app(app)

    app.config.setdefault("RATELIMIT_STORAGE_URI", os.getenv("RATELIMIT_STORAGE_URI", "memory://"))
    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)

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
                if not code:
                    return False
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
    app.jinja_env.filters["format_number"] = _safe_number_format
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["status_label"] = status_label

    def url_for_any(*endpoints, **values):
        last_err = None
        tried = []
        for ep in endpoints:
            try:
                return url_for(ep, **values)
            except BuildError as e:
                last_err = e
                tried.append(ep)
                current_app.logger.warning("url_for_any miss: endpoint=%s values=%r", ep, values)
        strict_urls = app.config.get("STRICT_URLS", bool(app.debug))
        if strict_urls:
            raise last_err or BuildError("url_for_any", values, "Tried: " + ", ".join(tried))
        current_app.logger.error("url_for_any fallback: tried=%s values=%r", tried, values)
        try:
            return url_for("main.dashboard", _anchor=f"missing:{'|'.join(tried)}")
        except Exception:
            return "/?missing=" + ",".join(tried)

    app.jinja_env.globals["url_for_any"] = url_for_any
    app.jinja_env.globals["now"] = datetime.utcnow

    def get_unique_flashes(with_categories=True):
        from flask import get_flashed_messages
        msgs = get_flashed_messages(with_categories=with_categories)
        seen = set()
        if with_categories:
            uniq = []
            for cat, msg in msgs:
                if msg not in seen:
                    uniq.append((cat or "info", msg))
                    seen.add(msg)
            return uniq
        uniq = []
        for msg in msgs:
            if msg not in seen:
                uniq.append(msg)
                seen.add(msg)
        return uniq

    app.jinja_env.globals["get_unique_flashes"] = get_unique_flashes

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
        parts_bp,
        admin_reports_bp,
        bp_barcode,
    ):
        app.register_blueprint(bp)

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config.get("CORS_ORIGINS", "*"),
                "supports_credentials": app.config.get("CORS_SUPPORTS_CREDENTIALS", True),
            }
        },
    )

    @app.shell_context_processor
    def _ctx():
        return {"db": db, "User": User}

    @app.after_request
    def _log_status(resp):
        if resp.status_code in (302, 401, 403, 404):
            loc = resp.headers.get("Location")
            app.logger.warning("HTTP %s %s → %s", resp.status_code, request.path, loc or "")
        return resp

    @app.teardown_appcontext
    def _cleanup(exception=None):
        db.session.remove()

    @app.errorhandler(403)
    def _forbidden(e):
        app.logger.error("403 FORBIDDEN: %s", request.path)
        try:
            return render_template("errors/403.html", path=request.path), 403
        except Exception:
            return ("403 Forbidden", 403)

    @app.errorhandler(404)
    def _not_found(e):
        app.logger.error("404 NOT FOUND: %s", request.path)
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return {"error": "Not Found"}, 404
        try:
            return render_template("errors/404.html", path=request.path), 404
        except Exception:
            return ("404 Not Found", 404)

    @app.context_processor
    def inject_global_flags():
        from utils import _SUPER_ROLES
        def is_super_admin(user) -> bool:
            try:
                return (
                    getattr(user, "is_authenticated", False)
                    and str(getattr(getattr(user, "role", None), "name", "")).lower() in _SUPER_ROLES
                )
            except Exception:
                return False
        return {"shop_is_super_admin": is_super_admin(current_user)}

    critical = app.config.get(
        "CRITICAL_ENDPOINTS",
        [
            "main.dashboard",
            "warehouse_bp.list",
            "vendors_bp.suppliers_list",
            "payments.index",
            "reports_bp.index",
            "customers_bp.list_customers",
            "users_bp.list_users",
            "service.list_requests",
            "sales_bp.index",
            "permissions.list",
            "roles.list_roles",
        ],
    )
    with app.app_context():
        existing_eps = {rule.endpoint for rule in app.url_map.iter_rules()}
        missing = [ep for ep in critical if ep and ep not in existing_eps]
        if missing:
            app.logger.error("Missing endpoints at startup: %s", ", ".join(missing))

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
