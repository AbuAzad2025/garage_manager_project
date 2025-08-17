import pytest
from uuid import uuid4
from sqlalchemy import text
from extensions import db
from models import Role, User

@pytest.mark.usefixtures("app")
def test_user_before_insert_dedupe_username_and_email(app):
    with app.app_context():
        role = db.session.scalar(db.select(Role).filter_by(name="staff"))
        if not role:
            role = Role(name="staff")
            db.session.add(role)
            db.session.commit()

        base = f"sam_{uuid4().hex[:6]}"
        email1 = f"{base}@example.com"

        db.session.execute(
            text("DELETE FROM users WHERE username LIKE :u OR email LIKE :e"),
            {"u": f"{base}%", "e": f"{base}%@example.com"},
        )
        db.session.commit()

        u1 = User(username=base, email=email1, role=role)
        u1.set_password("x")
        db.session.add(u1)
        db.session.commit()

        u2 = User(username=base, email=email1, role=role)
        u2.set_password("x")
        db.session.add(u2)
        db.session.commit()

        assert u1.username == base
        assert u2.username.startswith(base + "-")
        assert u1.email == email1
        assert u2.email.split("@")[0].startswith(base + "-") and u2.email.endswith("@example.com")
        assert u1.id != u2.id
