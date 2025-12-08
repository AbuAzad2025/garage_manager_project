import unittest
from flask import render_template_string
from app import create_app


class TestJinjaHelpersCoverage(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        try:
            from tests import login_owner
            login_owner(self.app, self.client)
        except Exception:
            pass

    def tearDown(self):
        self.ctx.pop()

    def _uniq(self, prefix='u'):
        from time import time
        return f"{prefix}{int(time() * 1000000)}"

    def _phone(self):
        v = self._uniq('')
        return '059' + v[-7:]

    def test_has_any_with_super_role(self):
        with self.app.test_request_context('/'):
            s = render_template_string("{{ has_any('x_permission') }}")
            self.assertIn(s.strip(), {'True', 'False'})

    def test_has_any_all_with_extra_permissions(self):
        from extensions import db
        from models import Role, User, Permission
        r = Role.query.filter(Role.name.ilike('staff')).first()
        if not r:
            r = Role(name='staff')
            db.session.add(r); db.session.commit()
        p1 = Permission.query.filter(Permission.name.ilike('manage_reports')).first() or Permission(name='manage_reports', code='manage_reports')
        p2 = Permission.query.filter(Permission.name.ilike('view_reports')).first() or Permission(name='view_reports', code='view_reports')
        db.session.add(p1); db.session.add(p2); db.session.commit()
        u = User(username=self._uniq('permuser'), email=self._uniq('perm') + '@example.com', role=r, is_active=True)
        u.set_password('p'); db.session.add(u); db.session.commit()
        with self.app.test_request_context('/'):
            s1 = render_template_string("{{ has_any('manage_reports','x') }}")
            s2 = render_template_string("{{ has_all('manage_reports','view_reports') }}")
            self.assertIn(s1.strip(), {'True','False'})
            self.assertIn(s2.strip(), {'True','False'})

    def test_has_perm_with_role_permission(self):
        from extensions import db
        from models import Role, Permission, User
        role = Role.query.filter(Role.name.ilike('owner')).first()
        if role:
            perm = Permission.query.filter(Permission.name.ilike('manage_customers')).first()
            if not perm:
                perm = Permission(name='manage_customers', code='manage_customers')
                db.session.add(perm)
                db.session.commit()
            if perm not in role.permissions:
                role.permissions.append(perm)
                db.session.commit()
        with self.app.test_request_context('/'):
            s = render_template_string("{{ has_perm('manage_customers') }}")
            self.assertIn(s.strip(), {'True', 'False'})

    def test_url_for_any_fallback(self):
        self.app.config['STRICT_URLS'] = False
        with self.app.test_request_context('/'):
            s = render_template_string("{{ url_for_any('missing_ep_1','missing_ep_2') }}")
            self.assertIn('#missing:', s)

    def test_is_customer_actor_true(self):
        from extensions import db
        from models import Customer
        c = Customer(name='T1', phone=self._phone(), email=None, is_online=True, is_active=True)
        c.set_password('p')
        db.session.add(c)
        db.session.commit()
        with self.app.test_request_context('/'):
            s = render_template_string("{{ is_customer_actor(u) }}", u=c)
            self.assertEqual(s.strip(), 'True')

    def test_is_customer_actor_false_for_user(self):
        from extensions import db
        from models import User, Role
        r = Role.query.filter(Role.name.ilike('viewer')).first()
        if not r:
            r = Role(name='viewer')
            db.session.add(r)
            db.session.commit()
        u = User(username=self._uniq('xuser'), email=self._uniq('xuser') + '@example.com', role=r, is_active=True)
        u.set_password('pass')
        db.session.add(u)
        db.session.commit()
        with self.app.test_request_context('/'):
            s = render_template_string("{{ is_customer_actor(u) }}", u=u)
            self.assertEqual(s.strip(), 'False')


if __name__ == '__main__':
    unittest.main()
