# -*- coding: utf-8 -*-
import pytest
from flask import url_for
from extensions import db
from models import User, Role

@pytest.mark.usefixtures("app", "client")
def test_users_list_page_ok(client):
    r = client.get(url_for("users.list_users"))
    assert r.status_code == 200

@pytest.mark.usefixtures("app", "client")
def test_users_detail_and_edit_pages_render(client, app):
    with app.app_context():
        role = Role(name="staff") if not db.session.scalar(db.select(Role).filter_by(name="staff")) else db.session.scalar(db.select(Role).filter_by(name="staff"))
        if role.id is None:
            db.session.add(role)
            db.session.commit()

        u = User(username="cov_user", email="cov_user@example.com", role=role)
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        uid = u.id

    r1 = client.get(url_for("users.user_detail", user_id=uid))
    assert r1.status_code == 200

    r2 = client.get(url_for("users.edit_user", user_id=uid))
    assert r2.status_code == 200
