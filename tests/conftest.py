# -*- coding: utf-8 -*-
# tests/conftest.py
import os
import sys
import uuid
import pytest
from sqlalchemy import event

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models import Permission, Role, User

try:
    from models import Customer, Supplier, Partner, Warehouse, Product
except Exception:
    Customer = Supplier = Partner = Warehouse = Product = None

SUPER_ADMIN_EMAIL = "rafideen.ahmadghannam@gmail.com"
SUPER_ADMIN_USERNAME = "azad"
SUPER_ADMIN_PASSWORD = "AZ123456"

ALL_PERMISSIONS = [
    'manage_users','manage_permissions','manage_roles','manage_customers','manage_sales','manage_service',
    'manage_reports','manage_vendors','manage_shipments','manage_warehouses','manage_payments','manage_expenses',
    'backup_restore','view_warehouses','view_inventory','manage_inventory','warehouse_transfer','view_parts',
    'view_preorders','add_preorder','edit_preorder','delete_preorder','add_customer','add_supplier','add_partner',
]

def _u_email(p="user"): return f"{p}_{uuid.uuid4().hex[:8]}@test.com"
def _u_phone(p="0599"): return f"{p}{uuid.uuid4().hex[:6]}"
def _u_barcode(n=12): return str(uuid.uuid4().int)[:n]

# -------------------- App fixture --------------------
@pytest.fixture(scope='session')
def app():
    cfg = {
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'WTF_CSRF_ENABLED': False,
        'PROPAGATE_EXCEPTIONS': True,
        'LOGIN_DISABLED': False,
        'PERMISSION_DISABLED': False,
    }
    application = create_app(cfg)

    # اختياري: تجاوز Auth/Perms لمسارات /api فقط أثناء الاختبار
    @application.before_request
    def _test_only_bypass_for_api():
        from flask import request, g, current_app
        if current_app.config.get("TESTING") and request.path.startswith("/api/"):
            g._orig_login_disabled = current_app.config.get("LOGIN_DISABLED", False)
            g._orig_perm_disabled = current_app.config.get("PERMISSION_DISABLED", False)
            current_app.config["LOGIN_DISABLED"] = True
            current_app.config["PERMISSION_DISABLED"] = True

    @application.after_request
    def _test_only_restore_for_api(response):
        from flask import request, g, current_app
        if current_app.config.get("TESTING") and request.path.startswith("/api/"):
            current_app.config["LOGIN_DISABLED"] = getattr(g, "_orig_login_disabled", False)
            current_app.config["PERMISSION_DISABLED"] = getattr(g, "_orig_perm_disabled", False)
        return response

    return application

# -------------------- Helpers --------------------
def _get_or_create(model, **kwargs):
    obj = model.query.filter_by(**kwargs).first()
    if not obj:
        obj = model(**kwargs)
        db.session.add(obj)
        db.session.flush()
    return obj

def _attach_role_to_user(user: User, role: Role):
    """
    يدعم الحالتين:
    - علاقة واحدة: user.role
    - علاقات متعددة: user.roles (قائمة)
    """
    if hasattr(user, "roles"):
        if role not in user.roles:
            user.roles.append(role)
    elif hasattr(user, "role"):
        user.role = role
    else:
        # fallback (لو عندك user.role_id)
        try:
            user.role = role
        except Exception:
            pass

def _collect_user_permissions(user: User):
    """
    يجمع الصلاحيات من كل الأدوار (إن وُجدت) أو من العلاقة المباشرة user.permissions.
    """
    names = set()
    if hasattr(user, "permissions") and user.permissions:
        names |= {p.name.lower() for p in user.permissions}
    if hasattr(user, "roles") and user.roles:
        for r in user.roles:
            if getattr(r, "permissions", None):
                names |= {p.name.lower() for p in r.permissions}
    elif hasattr(user, "role") and getattr(user, "role", None):
        if getattr(user.role, "permissions", None):
            names |= {p.name.lower() for p in user.role.permissions}
    return names

# -------------------- Seed (session) --------------------
@pytest.fixture(scope='session', autouse=True)
def seed_minimal(app):
    with app.app_context():
        # أنشئ جميع الصلاحيات المطلوبة
        existing = {p.name for p in Permission.query.all()}
        missing = [name for name in ALL_PERMISSIONS if name not in existing]
        for name in missing:
            db.session.add(Permission(name=name, description=''))
        db.session.flush()

        # أنشئ أو اجلب super_admin واربط له جميع الصلاحيات
        super_role = Role.query.filter_by(name='super_admin').first()
        if not super_role:
            super_role = Role(name='super_admin', description='Super Administrator')
            db.session.add(super_role)
            db.session.flush()
        all_perms = Permission.query.all()
        # تأكد أن كل الصلاحيات مربوطة بالدور
        for p in all_perms:
            if p not in super_role.permissions:
                super_role.permissions.append(p)
        db.session.flush()

        # أنشئ/حدّث المستخدم
        user = User.query.filter((User.email == SUPER_ADMIN_EMAIL) | (User.username == SUPER_ADMIN_USERNAME)).first()
        if not user:
            user = User(username=SUPER_ADMIN_USERNAME, email=SUPER_ADMIN_EMAIL, is_active=True)
            try:
                user.set_password(SUPER_ADMIN_PASSWORD)  # إن وُجدت
            except Exception:
                from werkzeug.security import generate_password_hash
                user.password_hash = generate_password_hash(SUPER_ADMIN_PASSWORD, method="scrypt")
            db.session.add(user)
            db.session.flush()
        else:
            user.is_active = True

        # اربط الدور بالمستخدم (يدعم roles/role)
        _attach_role_to_user(user, super_role)
        db.session.flush()

        # ازرع بيانات بسيطة
        seeds = []
        if Customer and not Customer.query.first():
            seeds.append(Customer(name="Test Customer", phone=_u_phone(), email=_u_email("cust")))
        if Supplier and not Supplier.query.first():
            seeds.append(Supplier(name="Test Supplier", phone=_u_phone(), email=_u_email("supp")))
        if Partner and not Partner.query.first():
            seeds.append(Partner(name="Test Partner", phone_number=_u_phone(), email=_u_email("part")))
        if Warehouse and not Warehouse.query.first():
            seeds.append(Warehouse(name="Main Warehouse"))
        if Product and not Product.query.first():
            try:
                seeds.append(Product(name="Test Product", barcode=_u_barcode(), price=0))
            except TypeError:
                try:
                    seeds.append(Product(name="Test Product", barcode=_u_barcode()))
                except TypeError:
                    seeds.append(Product(name="Test Product"))
        if seeds:
            db.session.add_all(seeds)

        db.session.commit()

        # اختياري: مزامنة كاش/رديس لصلاحيات المستخدم
        try:
            from utils import clear_user_permission_cache, _get_user_permissions, redis_client
            try:
                clear_user_permission_cache(user.id)
            except Exception:
                pass
            try:
                _ = _get_user_permissions(user)
            except Exception:
                pass
            try:
                if redis_client:
                    key = f"user_permissions:{user.id}"
                    perms = _collect_user_permissions(user)
                    redis_client.delete(key)
                    if perms:
                        redis_client.sadd(key, *list(perms))
                    redis_client.expire(key, 300)
            except Exception:
                pass
        except Exception:
            pass

# -------------------- DB transaction/savepoint per test --------------------
@pytest.fixture(scope='session')
def db_connection(app):
    ctx = app.app_context()
    ctx.push()
    try:
        conn = db.engine.connect()
        trans = conn.begin()
        db.session.remove()
        db.session.bind = conn

        @pytest.fixture(autouse=True)
        def _savepoint_each_test():
            nested = conn.begin_nested()

            @event.listens_for(db.session, "after_transaction_end")
            def _restart_savepoint(sess, txn):
                if txn.nested and not txn._parent.nested:
                    try:
                        conn.begin_nested()
                    except Exception:
                        pass

            try:
                yield
            finally:
                nested.rollback()
                db.session.expunge_all()

        try:
            yield conn
        finally:
            db.session.remove()
            trans.rollback()
            conn.close()
    finally:
        ctx.pop()

# -------------------- Clients --------------------
@pytest.fixture
def anon_client(app, db_connection):
    return app.test_client()

@pytest.fixture
def client(app, db_connection, seed_minimal):
    """
    عميل مُسجّل دخول بسوبر أدمن قبل كل Test.
    """
    c = app.test_client()
    with app.app_context():
        user = User.query.filter_by(username=SUPER_ADMIN_USERNAME).first()
        assert user is not None, "Super admin user was not created in seed_minimal"

        # حقن جلسة flask-login
        with c.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        # (اختياري) مزامنة كاش/رديس لصلاحيات المستخدم بعد كل تهيئة
        try:
            from utils import _get_user_permissions, clear_user_permission_cache, redis_client
            try:
                clear_user_permission_cache(user.id)
            except Exception:
                pass
            try:
                _ = _get_user_permissions(user)
            except Exception:
                pass
            try:
                if redis_client:
                    key = f"user_permissions:{user.id}"
                    perms = _collect_user_permissions(user)
                    redis_client.delete(key)
                    if perms:
                        redis_client.sadd(key, *list(perms))
                    redis_client.expire(key, 300)
            except Exception:
                pass
        except Exception:
            pass

    return c
