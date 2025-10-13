# app.py - Main Application Entry Point
# Location: /garage_manager/app.py
# Description: Flask application factory and main configuration

import os
import uuid
import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, timezone
from flask import Flask, url_for, request, current_app, render_template, g, redirect
from werkzeug.routing import BuildError
from flask_cors import CORS
from flask_login import AnonymousUserMixin, current_user
from jinja2 import ChoiceLoader, FileSystemLoader
from sqlalchemy import event

from config import Config, ensure_runtime_dirs, assert_production_sanity
from extensions import db, migrate, login_manager, socketio, mail, csrf, limiter, setup_logging, setup_sentry
from extensions import init_extensions
from utils import (
    qr_to_base64,
    format_currency,
    format_percent,
    format_date,
    format_datetime,
    yes_no,
    init_app as utils_init_app,
    _expand_perms as _perm_expand,
    is_super,
)
from models import User, Role, Permission, Customer
from acl import attach_acl

from routes.auth import auth_bp
from routes.main import main_bp
from routes.users import users_bp
from routes.service import service_bp
from routes.customers import customers_bp
from routes.sales import sales_bp
from routes.notes import notes_bp
from routes.report_routes import reports_bp
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
from routes.partner_settlements import partner_settlements_bp
from routes.supplier_settlements import supplier_settlements_bp
from routes.ledger_blueprint import ledger_bp
from routes.ledger_ai_assistant import ai_assistant_bp
from routes.barcode_scanner import barcode_scanner_bp
from routes.currencies import currencies_bp
from routes.hard_delete import hard_delete_bp
from routes.user_guide import user_guide_bp
from routes.other_systems import other_systems_bp
from routes.pricing import pricing_bp
from routes.checks import checks_bp
from routes.health import health_bp
from routes.security import security_bp


class MyAnonymousUser(AnonymousUserMixin):
    def has_permission(self, perm_name):
        return False


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
            return db.session.execute(stmt).unique().scalar_one_or_none()
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
    app.config.setdefault("NUMBER_DECIMALS", 2)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    ensure_runtime_dirs(config_object)
    assert_production_sanity(config_object)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    app.config.setdefault("SUPER_USER_EMAILS", os.getenv("SUPER_USER_EMAILS", ""))
    app.config.setdefault("SUPER_USER_IDS", os.getenv("SUPER_USER_IDS", ""))
    app.config.setdefault("ADMIN_USER_EMAILS", os.getenv("ADMIN_USER_EMAILS", ""))
    app.config.setdefault("ADMIN_USER_IDS", os.getenv("ADMIN_USER_IDS", ""))
    app.config.setdefault("PERMISSIONS_REQUIRE_ALL", False)

    engine_opts = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    connect_args = engine_opts.setdefault("connect_args", {})
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    engine_opts.setdefault("pool_pre_ping", True)
    engine_opts.setdefault("pool_recycle", 1800)
    # ⚡ Performance: Optimize connection pooling
    engine_opts.setdefault("pool_size", 10)
    engine_opts.setdefault("max_overflow", 20)
    if uri.startswith("sqlite"):
        connect_args.setdefault("timeout", 30)
    else:
        connect_args.pop("timeout", None)
        if uri.startswith(("postgresql", "postgresql+psycopg2")):
            connect_args.setdefault("connect_timeout", int(os.getenv("DB_CONNECT_TIMEOUT", "10")))
        elif uri.startswith(("mysql", "mysql+pymysql", "mysql+mysqldb")):
            connect_args.setdefault("connect_timeout", int(os.getenv("DB_CONNECT_TIMEOUT", "10")))

    setup_logging(app)
    setup_sentry(app)

    init_extensions(app)
    utils_init_app(app)
    
    csrf.exempt(ledger_bp)
    
    from routes.security import security_bp
    csrf.exempt(security_bp)
    
    @app.template_global()
    def _get_action_icon(action):
        if not action:
            return 'info-circle'
        mapping = {
            'login': 'sign-in-alt', 'logout': 'sign-out-alt',
            'create': 'plus', 'update': 'edit', 'delete': 'trash',
            'view': 'eye', 'export': 'download', 'import': 'upload',
            'blocked': 'ban', 'security': 'shield-alt'
        }
        action_lower = str(action).lower()
        for key, icon in mapping.items():
            if key in action_lower:
                return icon
        return 'circle'
    
    @app.template_global()
    def _get_action_color(action):
        if not action:
            return 'secondary'
        mapping = {
            'login': 'success', 'logout': 'secondary',
            'create': 'primary', 'update': 'info', 'delete': 'danger',
            'blocked': 'danger', 'failed': 'danger', 'security': 'warning'
        }
        action_lower = str(action).lower()
        for key, color in mapping.items():
            if key in action_lower:
                return color
        return 'secondary'

    @event.listens_for(db.session.__class__, "before_attach")
    def _dedupe_entities(session, instance):
        if isinstance(instance, (Role, Permission)) and getattr(instance, "id", None) is not None:
            key = session.identity_key(instance.__class__, (instance.id,))
            existing = session.identity_map.get(key)
            if existing is not None and existing is not instance:
                session.expunge(existing)

    login_manager.login_view = "auth.login"
    login_manager.anonymous_user = MyAnonymousUser
    try:
        login_manager.session_protection = None
    except Exception:
        pass

    os.environ.setdefault("PERMISSIONS_DEBUG", "0")
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("engineio").setLevel(logging.WARNING)
    logging.getLogger("socketio").setLevel(logging.WARNING)
    logging.getLogger("weasyprint").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    app.logger.setLevel(logging.INFO)

    if app.config.get("SERVER_NAME"):
        from urllib.parse import urlparse
        def _relative_url_for(self, endpoint, **values):
            rv = Flask.url_for(self, endpoint, **values)
            if not values.get("_external"):
                parsed = urlparse(rv)
                rv = parsed.path + ("?" + parsed.query if parsed.query else "")
            return rv
        app.url_for = _relative_url_for.__get__(app, Flask)

    extra_template_paths = [
        os.path.join(app.root_path, "templates"),
        os.path.join(app.root_path, "routes", "templates"),
    ]
    app.jinja_loader = ChoiceLoader(
        [FileSystemLoader(p) for p in extra_template_paths]
        + ([app.jinja_loader] if app.jinja_loader else [])
    )

    def _two_dec(v, digits=None, grouping=True):
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError, TypeError):
            d = Decimal("0")
        digits = digits or app.config.get("NUMBER_DECIMALS", 2)
        q = (Decimal("1") / (Decimal("10") ** digits))
        d = d.quantize(q, rounding=ROUND_HALF_UP)
        if grouping:
            return f"{d:,.{digits}f}"
        return f"{d:.{digits}f}"

    def _safe_number_format(v, digits=None):
        return _two_dec(v, digits=digits or app.config.get("NUMBER_DECIMALS", 2), grouping=True)

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

    @app.context_processor
    def inject_common():
        return {"current_app": current_app, "get_unique_flashes": get_unique_flashes}

    @app.context_processor
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
                iterable = up.all() if hasattr(up, "all") else up
                for p in iterable:
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
                if is_super():
                    return True
                u = current_user
                if not getattr(u, "is_authenticated", False):
                    return False
                targets = {c.strip().lower() for c in _perm_expand(code)}
                perms_lower = _collect_user_perms(u)
                return bool(perms_lower & targets)
            except Exception:
                return False

        def has_any(*codes):
            if is_super():
                return True
            return any(has_perm(c) for c in codes)

        def has_all(*codes):
            if is_super():
                return True
            return all(has_perm(c) for c in codes)

        return {"has_perm": has_perm, "has_any": has_any, "has_all": has_all}

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

    app.jinja_env.filters["qr_to_base64"] = qr_to_base64
    app.jinja_env.filters["format_currency"] = format_currency
    app.jinja_env.filters["format_percent"] = format_percent
    app.jinja_env.filters["yes_no"] = yes_no
    app.jinja_env.filters["number_format"] = _safe_number_format
    app.jinja_env.filters["format_number"] = _safe_number_format
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["two_dec"] = _two_dec

    from utils import format_currency_in_ils, get_entity_balance_in_ils
    app.jinja_env.filters["format_currency_in_ils"] = format_currency_in_ils
    app.jinja_env.globals["get_entity_balance_in_ils"] = get_entity_balance_in_ils
    app.jinja_env.globals["url_for_any"] = url_for_any
    app.jinja_env.globals["now"] = lambda: datetime.now(timezone.utc)

    attach_acl(
        shop_bp,
        read_perm="view_shop",
        write_perm="manage_shop",
        public_read=True,
        exempt_prefixes=[
            "/shop/admin",
            "/shop/webhook",
            "/shop/cart",
            "/shop/cart/add",
            "/shop/cart/update",
            "/shop/cart/item",
            "/shop/cart/remove",
            "/shop/checkout",
            "/shop/order",
        ]
    )

    attach_acl(users_bp, read_perm="manage_users", write_perm="manage_users")
    attach_acl(customers_bp, read_perm="manage_customers", write_perm="manage_customers")
    attach_acl(vendors_bp, read_perm="manage_vendors", write_perm="manage_vendors")
    attach_acl(shipments_bp, read_perm="manage_shipments", write_perm="manage_shipments")
    attach_acl(warehouse_bp, read_perm="view_warehouses", write_perm="manage_warehouses")
    attach_acl(payments_bp, read_perm="manage_payments", write_perm="manage_payments")
    attach_acl(expenses_bp, read_perm="manage_expenses", write_perm="manage_expenses")
    attach_acl(sales_bp, read_perm="manage_sales", write_perm="manage_sales")
    attach_acl(service_bp, read_perm="manage_service", write_perm="manage_service")
    attach_acl(reports_bp, read_perm="view_reports", write_perm="manage_reports")
    attach_acl(roles_bp, read_perm="manage_roles", write_perm="manage_roles")
    attach_acl(permissions_bp, read_perm="manage_permissions", write_perm="manage_permissions")
    attach_acl(parts_bp, read_perm="view_parts", write_perm="manage_inventory")
    attach_acl(admin_reports_bp, read_perm="view_reports", write_perm="manage_reports")
    attach_acl(main_bp, read_perm=None, write_perm=None)
    attach_acl(partner_settlements_bp, read_perm="manage_vendors", write_perm="manage_vendors")
    attach_acl(supplier_settlements_bp, read_perm="manage_vendors", write_perm="manage_vendors")
    attach_acl(api_bp, read_perm="access_api", write_perm="manage_api")
    attach_acl(notes_bp, read_perm="view_notes", write_perm="manage_notes")
    attach_acl(bp_barcode, read_perm="view_parts", write_perm=None)
    attach_acl(ledger_bp, read_perm="manage_ledger", write_perm="manage_ledger")
    attach_acl(currencies_bp, read_perm="manage_currencies", write_perm="manage_currencies")
    attach_acl(barcode_scanner_bp, read_perm="scan_barcode", write_perm=None)
    attach_acl(hard_delete_bp, read_perm="manage_system", write_perm="manage_system")
    attach_acl(checks_bp, read_perm="view_payments", write_perm="manage_payments")
    
    BLUEPRINTS = [
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
        partner_settlements_bp,
        supplier_settlements_bp,
        api_bp,
        ledger_bp,
        currencies_bp,
        hard_delete_bp,
        barcode_scanner_bp,
        ai_assistant_bp,
        user_guide_bp,
        other_systems_bp,
        pricing_bp,
        checks_bp,
        health_bp,
        security_bp,
    ]
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config.get("CORS_ORIGINS", ["http://localhost:5000"]),
                "supports_credentials": app.config.get("CORS_SUPPORTS_CREDENTIALS", True),
                "allow_headers": ["Content-Type", "Authorization", "X-CSRF-TOKEN"],
                "methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "max_age": 3600,
            }
        },
    )
    
    @app.after_request
    def security_headers(response):
        # حماية من XSS
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if not app.config.get('DEBUG'):
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://code.jquery.com https://cdn.datatables.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdn.datatables.net; "
                "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "connect-src 'self';"
            )
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        response.headers.pop('Server', None)
        response.headers.pop('X-Powered-By', None)
        
        if request.path.startswith('/auth/') or request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif request.path.startswith('/static/'):
            # ⚡ Performance: Cache static files for 1 year
            response.cache_control.max_age = 31536000
            response.cache_control.public = True
        return response

    
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
        return {"shop_is_super_admin": is_super()}

    @app.before_request
    def _touch_last_seen():
        if getattr(current_user, "is_authenticated", False):
            try:
                ls = getattr(current_user, "last_seen", None)
                if (not ls) or (datetime.now(timezone.utc) - ls).total_seconds() > 60:
                    current_user.last_seen = datetime.now(timezone.utc)
                    db.session.commit()
            except Exception:
                db.session.rollback()

    @app.before_request
    def _attach_request_id():
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex

    @app.after_request
    def _emit_request_id(resp):
        rid = getattr(g, "request_id", None)
        if rid:
            resp.headers["X-Request-Id"] = rid
        return resp

    @app.after_request
    def _access_log(resp):
        try:
            app.logger.info(
                "access",
                extra={
                    "event": "http.access",
                    "method": request.method,
                    "path": request.path,
                    "status": resp.status_code,
                    "remote_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                },
            )
        except Exception:
            pass
        return resp

    @app.errorhandler(500)
    def _err_500(e):
        app.logger.exception("unhandled", extra={"event": "app.error", "path": request.path})
        return render_template("errors/500.html"), 500

    @app.before_request
    def restrict_customer_from_admin():
        if getattr(current_user, "is_authenticated", False):
            role_slug = getattr(getattr(current_user, "role", None), "slug", None)
            if role_slug == "customer":
                allowed_paths = ("/shop", "/static", "/auth/logout")
                if not any(request.path.startswith(p) for p in allowed_paths):
                    return redirect("/shop")

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

    @app.context_processor
    def inject_system_settings():
        """حقن إعدادات النظام في جميع القوالب"""
        try:
            from models import SystemSettings
            def _get_setting(key, default=None):
                try:
                    setting = SystemSettings.query.filter_by(key=key).first()
                    if setting:
                        value = setting.value.lower() if setting.value else ''
                        if value in ['true', '1', 'yes']:
                            return True
                        elif value in ['false', '0', 'no']:
                            return False
                        return setting.value
                    return default
                except:
                    return default
            
            settings = {
                'system_name': _get_setting('system_name', 'Garage Manager'),
                'company_name': _get_setting('COMPANY_NAME', 'Azad Garage'),
                'custom_logo': _get_setting('custom_logo', ''),
                'custom_favicon': _get_setting('custom_favicon', ''),
                'primary_color': _get_setting('primary_color', '#007bff'),
                'COMPANY_ADDRESS': _get_setting('COMPANY_ADDRESS', ''),
                'COMPANY_PHONE': _get_setting('COMPANY_PHONE', ''),
                'COMPANY_EMAIL': _get_setting('COMPANY_EMAIL', ''),
                'TAX_NUMBER': _get_setting('TAX_NUMBER', ''),
                'CURRENCY_SYMBOL': _get_setting('CURRENCY_SYMBOL', '$'),
                'TIMEZONE': _get_setting('TIMEZONE', 'UTC'),
            }
            return dict(system_settings=settings)
        except:
            return dict(system_settings={})
    
    @app.before_request
    def check_maintenance_mode():
        """فحص وضع الصيانة - المنطق المحسّن"""
        if request.path.startswith('/static/'):
            return None
        
        if request.path.startswith('/auth/'):
            return None
        
        if not current_user.is_authenticated:
            return None
        
        try:
            from models import SystemSettings
            setting = SystemSettings.query.filter_by(key='maintenance_mode').first()
            if not setting or setting.value.lower() not in ['true', '1', 'yes']:
                return None
        except:
            return None
        
        try:
            if (current_user.id == 1 or 
                current_user.username.lower() in ['azad', 'owner', 'admin'] or
                is_super()):
                return None
        except:
            pass
        
        return render_template('maintenance.html'), 503

    from cli import register_cli
    register_cli(app)


    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    app = create_app()
