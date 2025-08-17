# tests/views/test_backup_route_cov.py
# -*- coding: utf-8 -*-
import io
import os
import tempfile
from typing import Iterable

import pytest
from flask import url_for
from werkzeug.security import generate_password_hash

from extensions import db
from models import User, Role, Permission

def _ensure_permissions(names: Iterable[str]) -> None:
    existing = {p.name for p in Permission.query.all()}
    for n in names:
        if n not in existing:
            db.session.add(Permission(name=n, code=n, description=""))
    db.session.commit()

def _make_role(name: str, perm_names: Iterable[str]) -> Role:
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, description=f"{name} role")
        db.session.add(role)
        db.session.flush()
    _ensure_permissions(perm_names)
    perms = Permission.query.filter(Permission.name.in_(list(perm_names))).all()
    role.permissions = perms
    db.session.commit()
    return role

def _make_user(email: str, username: str, password: str, role: Role) -> User:
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email, username=username, role=role)
        u.password_hash = generate_password_hash(password)
        db.session.add(u)
        db.session.commit()
    else:
        u.role = role
        db.session.commit()
    return u

def _login(client, email: str, password: str):
    return client.post(url_for("auth.login"), data={"email": email, "password": password}, follow_redirects=True)

P_BACKUP = "backup_database"
P_RESTORE = "restore_database"

@pytest.fixture
def role_backup_only(app):
    with app.app_context():
        return _make_role("backup_only", [P_BACKUP])

@pytest.fixture
def role_backup_restore(app):
    with app.app_context():
        return _make_role("backup_restore_role", [P_BACKUP, P_RESTORE])

@pytest.fixture
def user_backup(app, role_backup_only):
    with app.app_context():
        return _make_user("backup@example.com", "backup", "pass", role_backup_only)

@pytest.fixture
def user_super_backup_restore(app, role_backup_restore):
    with app.app_context():
        return _make_user("boss@example.com", "boss", "pass", role_backup_restore)

def test_navbar_shows_backup_only_link_when_only_backup_permission(client, app, user_backup):
    with app.app_context():
        _login(client, "backup@example.com", "pass")
        resp = client.get(url_for("main.dashboard"))
        html = resp.get_data(as_text=True)
        assert url_for("main.backup_db") in html
        assert url_for("main.restore_db") not in html

def test_navbar_shows_both_links_when_both_permissions(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        resp = client.get(url_for("main.dashboard"))
        html = resp.get_data(as_text=True)
        assert url_for("main.backup_db") in html
        assert url_for("main.restore_db") in html

def test_backup_db_with_real_sqlite_file_downloads_db(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            old_uri = app.config["SQLALCHEMY_DATABASE_URI"]
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + tmp_db
            resp = client.get(url_for("main.backup_db"))
            assert resp.status_code == 200
            cd = resp.headers.get("Content-Disposition", "")
            assert ".db" in cd or cd.endswith(".db")
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = old_uri
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

def test_backup_db_with_memory_sqlite_sends_sql_dump(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        old_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        try:
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
            resp = client.get(url_for("main.backup_db"))
            assert resp.status_code == 200
            cd = resp.headers.get("Content-Disposition", "")
            assert ".sql" in cd
            data = resp.get_data(as_text=True)
            assert "BEGIN TRANSACTION" in data or "CREATE TABLE" in data
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = old_uri

def test_backup_db_non_sqlite_redirects_with_flash(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        old_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        try:
            app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://user@localhost/dbname"
            resp = client.get(url_for("main.backup_db"), follow_redirects=True)
            assert resp.status_code == 200
            assert "قاعدة البيانات ليست SQLite." in resp.get_data(as_text=True)
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = old_uri

def test_restore_db_get_renders_form(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        resp = client.get(url_for("main.restore_db"))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "<form" in html and 'type="file"' in html

def test_restore_db_post_with_valid_db_replaces_file(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        upload_content = b"SQLite format 3\x00" + b"\x00" * 100
        data = {"db_file": (io.BytesIO(upload_content), "backup.db")}
        old_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        try:
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + tmp_db
            resp = client.post(url_for("main.restore_db"), data=data,
                               content_type="multipart/form-data", follow_redirects=True)
            assert resp.status_code == 200
            page = resp.get_data(as_text=True)
            assert "تمت الاستعادة بنجاح" in page
            assert os.path.getsize(tmp_db) >= len(upload_content)
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = old_uri
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

def test_restore_db_post_rejects_when_not_sqlite(client, app, user_super_backup_restore):
    with app.app_context():
        _login(client, "boss@example.com", "pass")
        old_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        try:
            app.config["SQLALCHEMY_DATABASE_URI"] = "mysql://user@localhost/db"
            data = {"db_file": (io.BytesIO(b"dummy"), "backup.db")}
            resp = client.post(url_for("main.restore_db"), data=data,
                               content_type="multipart/form-data", follow_redirects=True)
            assert resp.status_code == 200
            assert "قاعدة البيانات ليست SQLite." in resp.get_data(as_text=True)
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = old_uri
