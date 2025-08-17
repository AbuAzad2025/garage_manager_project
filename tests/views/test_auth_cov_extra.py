import types
import pytest
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import url_for
from werkzeug.exceptions import NotFound
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from extensions import db
from models import User, Role, Permission, Customer
from routes import auth as auth_mod


def create_user(username="u1", email="u1@example.com", password="P@ssw0rd"):
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def create_role_with_perm(role_name="admin", perm_name="manage_users"):
    p = Permission.query.filter_by(name=perm_name).first()
    if not p:
        p = Permission(name=perm_name, description="can manage users")
        db.session.add(p)
        db.session.flush()
    r = Role.query.filter_by(name=role_name).first()
    if not r:
        r = Role(name=role_name, description="admin role")
        db.session.add(r)
        db.session.flush()
    if p not in r.permissions:
        r.permissions.append(p)
    db.session.commit()
    return r, p

def login_session(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True

@pytest.fixture(autouse=True)
def clear_session(client):
    client.post(url_for("auth.logout"), follow_redirects=True)
    with client.session_transaction() as sess:
        sess.clear()

def test__sa_get_or_404_raises_404_for_missing(app):
    with app.app_context():
        with pytest.raises(NotFound):
            auth_mod._sa_get_or_404(User, 99999999)

def test_is_blocked_unblocks_after_window():
    ip = "10.0.0.1"
    now = datetime.utcnow()
    auth_mod.login_attempts_ref[ip] = (auth_mod.MAX_ATTEMPTS, now - auth_mod.BLOCK_TIME - timedelta(seconds=1))
    assert auth_mod.is_blocked(ip) is False
    assert ip not in auth_mod.login_attempts_ref

def test_record_attempt_increments():
    ip = "10.0.0.2"
    auth_mod.login_attempts_ref.pop(ip, None)
    auth_mod.record_attempt(ip)
    attempts, _ = auth_mod.login_attempts_ref[ip]
    assert attempts == 1

def test_login_success_clears_attempts_and_redirects(client, app):
    ip = "127.0.0.1"
    u = create_user(username="login_ok", email="login_ok@example.com", password="pass1234")
    auth_mod.login_attempts_ref[ip] = (2, datetime.utcnow())
    resp = client.post(
        url_for("auth.login"),
        data={"username": u.username, "password": "pass1234"},
        environ_overrides={"REMOTE_ADDR": ip},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert ip not in auth_mod.login_attempts_ref

def test_login_wrong_password_blocks_after_max_attempts(client):
    ip = "127.1.1.9"
    u = create_user(username="blocked", email="blocked@example.com", password="good")
    for _ in range(auth_mod.MAX_ATTEMPTS):
        r = client.post(
            url_for("auth.login"),
            data={"username": u.username, "password": "bad"},
            environ_overrides={"REMOTE_ADDR": ip},
            follow_redirects=False,
        )
        assert r.status_code in (200, 302)
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get(url_for("auth.login"), environ_overrides={"REMOTE_ADDR": ip})
    assert r.status_code == 200
    assert "تم حظر محاولات الدخول" in r.data.decode("utf-8")

def test_login_redirect_if_authenticated_user_direct_call(app):
    u = create_user(username="already_in", email="already_in@example.com")
    with app.test_request_context("/auth/login"):
        class CU:
            is_authenticated = True
            def _get_current_object(self): return u
        orig = auth_mod.current_user
        auth_mod.current_user = CU()
        try:
            resp = auth_mod.login()
            assert hasattr(resp, "location")
            assert resp.location == url_for("main.dashboard")
        finally:
            auth_mod.current_user = orig

def test_login_redirect_if_authenticated_customer_direct_call(app):
    c = Customer(name="cust", email="cust@example.com", phone="059", is_online=True, is_active=True)
    c.set_password("x")
    db.session.add(c)
    db.session.commit()
    with app.test_request_context("/auth/login"):
        class CU:
            is_authenticated = True
            def _get_current_object(self): return c
        orig = auth_mod.current_user
        auth_mod.current_user = CU()
        try:
            resp = auth_mod.login()
            assert hasattr(resp, "location")
            assert resp.location == url_for("shop.catalog")
        finally:
            auth_mod.current_user = orig

def test_logout_requires_login_redirects(client):
    r = client.post(url_for("auth.logout"), follow_redirects=False)
    assert r.status_code in (302, 303)

def test_logout_ok_when_logged_in(client):
    u = create_user(username="lo", email="lo@example.com")
    login_session(client, u)
    r = client.post(url_for("auth.logout"), follow_redirects=False)
    assert r.status_code in (302, 303)
    assert urlparse(r.location).path == url_for("auth.login")

def test_password_reset_request_sends_email_and_handles_exception(client, monkeypatch):
    u = create_user(username="mr", email="mr@example.com")
    class BoomMail:
        def send(self, *a, **k):
            raise RuntimeError("mail down")
    monkeypatch.setattr(auth_mod, "mail", BoomMail())
    r = client.post(url_for("auth.password_reset_request"),
                    data={"email": u.email},
                    follow_redirects=False)
    assert r.status_code in (302, 303)

def test_password_reset_valid_token_post_changes_password(client, app, monkeypatch):
    u = create_user(username="tok", email="tok@example.com")
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = serializer.dumps(u.id, salt="password-reset-salt")
    g = client.get(url_for("auth.password_reset", token=token))
    assert g.status_code == 200
    class DummyForm:
        password = types.SimpleNamespace(data="NEWpass!123")
        def validate_on_submit(self): return True
    monkeypatch.setattr(auth_mod, "PasswordResetForm", lambda *a, **k: DummyForm())
    p = client.post(url_for("auth.password_reset", token=token), data={"password": "NEWpass!123"})
    assert p.status_code in (302, 303)
    db.session.refresh(u)
    assert u.check_password("NEWpass!123")

def test_password_reset_expired_token_redirects(client, monkeypatch, app):
    class DummySer:
        def loads(self, *a, **k): raise SignatureExpired("expired")
    monkeypatch.setattr(auth_mod, "URLSafeTimedSerializer", lambda *a, **k: DummySer())
    r = client.get(url_for("auth.password_reset", token="t"))
    assert r.status_code in (302, 303)
    assert "password_reset_request" in r.location

def test_password_reset_bad_token_redirects(client, monkeypatch, app):
    class DummySer:
        def loads(self, *a, **k): raise BadSignature("bad")
    monkeypatch.setattr(auth_mod, "URLSafeTimedSerializer", lambda *a, **k: DummySer())
    r = client.get(url_for("auth.password_reset", token="t"))
    assert r.status_code in (302, 303)
    assert "password_reset_request" in r.location

def test_register_get_ok_with_permission(client):
    role_admin, _ = create_role_with_perm()
    admin = create_user(username="adminz", email="adminz@example.com", password="A1b2c3d4")
    admin.role = role_admin
    db.session.commit()
    client.post(url_for("auth.login"),
                data={"username": admin.username, "password": "A1b2c3d4"},
                follow_redirects=True)
    r = client.get(url_for("auth.register"))
    assert r.status_code == 200

def test_register_post_success_creates_user_with_non_dev_role(client, monkeypatch):
    role_admin, _ = create_role_with_perm()
    role_worker = Role.query.filter_by(name="worker").first()
    if not role_worker:
        role_worker = Role(name="worker", description="worker")
        db.session.add(role_worker)
        db.session.commit()
    admin = create_user(username="adminx", email="adminx@example.com")
    admin.role = role_admin
    db.session.commit()
    client.post(url_for("auth.login"),
                data={"username": admin.username, "password": "P@ssw0rd"},
                follow_redirects=True)
    class DummyRegForm:
        username = types.SimpleNamespace(data="new_user_ok")
        email    = types.SimpleNamespace(data="new_user_ok@example.com")
        password = types.SimpleNamespace(data="OkPass!234")
        role     = types.SimpleNamespace(data=role_worker.id)
        def validate_on_submit(self): return True
    monkeypatch.setattr(auth_mod, "RegistrationForm", lambda *a, **k: DummyRegForm())
    r = client.post(url_for("auth.register"), data={"username":"irrelevant"})
    assert r.status_code in (302, 303)
    created = User.query.filter_by(email="new_user_ok@example.com").first()
    assert created is not None and created.role_id == role_worker.id

def test_register_block_developer_role(client, monkeypatch):
    role_admin, _ = create_role_with_perm()
    role_dev = Role.query.filter_by(name="Developer").first()
    if not role_dev:
        role_dev = Role(name="Developer", description="blocked")
        db.session.add(role_dev)
        db.session.commit()
    admin = create_user(username="admind", email="admind@example.com")
    admin.role = role_admin
    db.session.commit()
    login_session(client, admin)
    class DummyRegForm:
        username = types.SimpleNamespace(data="x")
        email    = types.SimpleNamespace(data="x@example.com")
        password = types.SimpleNamespace(data="Xx123456!")
        role     = types.SimpleNamespace(data=role_dev.id)
        def validate_on_submit(self): return True
    monkeypatch.setattr(auth_mod, "RegistrationForm", lambda *a, **k: DummyRegForm())
    r = client.post(url_for("auth.register"))
    assert r.status_code in (302, 303)
    assert User.query.filter_by(email="x@example.com").first() is None

def test_register_commit_exception_is_handled(client, monkeypatch):
    role_admin, _ = create_role_with_perm()

    role_worker = Role.query.filter_by(name="worker").first()
    if not role_worker:
        role_worker = Role(name="worker", description="worker")
        db.session.add(role_worker)
        db.session.commit()

    admin = create_user(username="adminc", email="adminc@example.com")
    admin.role = role_admin
    db.session.commit()

    client.post(
        url_for("auth.login"),
        data={"username": admin.username, "password": "P@ssw0rd"},
        follow_redirects=True,
    )

    class DummyRegForm:
        username = types.SimpleNamespace(data="boom")
        email    = types.SimpleNamespace(data="boom@example.com")
        password = types.SimpleNamespace(data="Xx123456!")
        role     = types.SimpleNamespace(data=role_worker.id)
        def validate_on_submit(self): return True

    monkeypatch.setattr(auth_mod, "RegistrationForm", lambda *a, **k: DummyRegForm())

    def boom_commit():
        raise RuntimeError("db down")
    monkeypatch.setattr(auth_mod.db.session, "commit", boom_commit)

    # أهم سطر: نتجاوز رندر القالب الذي يطلب hidden_tag
    monkeypatch.setattr(auth_mod, "render_template", lambda *a, **k: ("", 200))

    r = client.post(url_for("auth.register"))
    assert r.status_code == 200

def test_customer_register_authenticated_user_redirects(client):
    u = create_user(username="logged", email="logged@example.com")

    # تسجيل دخول فعلي بدل login_session
    client.post(
        url_for("auth.login"),
        data={"username": u.username, "password": "P@ssw0rd"},
        follow_redirects=True,
    )

    r = client.get(url_for("auth.customer_register"), follow_redirects=False)
    assert r.status_code in (302, 303)
    assert urlparse(r.location).path == url_for("shop.catalog")

def test_customer_register_post_success_monkeypatched_form(client, monkeypatch):
    class DummyCustomerForm:
        name     = types.SimpleNamespace(data="Ali")
        email    = types.SimpleNamespace(data="ali@example.com")
        phone    = types.SimpleNamespace(data="0590000000")
        whatsapp = types.SimpleNamespace(data="0590000000")
        address  = types.SimpleNamespace(data="Gaza")
        password = types.SimpleNamespace(data="Al1!Al1!")
        def validate_on_submit(self): return True

    monkeypatch.setattr(auth_mod, "CustomerFormOnline", lambda *a, **k: DummyCustomerForm())

    r = client.post(url_for("auth.customer_register"), data={"any": "x"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert urlparse(r.location).path == url_for("shop.catalog")
