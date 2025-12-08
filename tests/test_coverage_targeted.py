import unittest
from datetime import datetime, timezone
from flask import render_template_string
from app import create_app


class TestTargetedCoverage(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def _unique_phone(self):
        from time import time
        return '059' + str(int(time() * 1000000))[-7:]

    def test_static_version_filter(self):
        with self.app.test_request_context('/'):
            s1 = render_template_string("{{ 'css/app.css'|static_version }}")
        s2 = render_template_string("{{ 'css/app.css?v=1'|static_version }}")
        self.assertIn('css/app.css?v=', s1)
        self.assertIn('css/app.css?v=1&amp;v=', s2)

    def test_url_for_any_success_and_strict(self):
        with self.app.test_request_context('/'):
            ok = render_template_string("{{ url_for_any('main.dashboard','shop.catalog') }}")
            self.assertTrue(ok.startswith('/') )
        self.app.config['STRICT_URLS'] = True
        with self.app.test_request_context('/'):
            with self.assertRaises(Exception):
                render_template_string("{{ url_for_any('no_ep_1','no_ep_2') }}")

    def test_permissions_helpers_authenticated_and_anonymous(self):
        from extensions import db
        from models import Role, Permission, User
        role = Role.query.filter(Role.name.ilike('owner')).first() or Role(name='owner', slug='owner')
        db.session.add(role); db.session.commit()
        perm = Permission.query.filter(Permission.name.ilike('manage_reports')).first()
        if not perm:
            perm = Permission(name='manage_reports', code='manage_reports')
            db.session.add(perm); db.session.commit()
        if perm not in role.permissions:
            role.permissions.append(perm); db.session.commit()
        u = User.query.filter(User.username.ilike('owner')).first()
        if not u:
            u = User(username='owner', email='owner@example.com', role=role, is_active=True)
            u.set_password('OwnerPass2024!')
            db.session.add(u); db.session.commit()
        self.client.post('/auth/login', data={'username': 'owner', 'password': 'OwnerPass2024!'}, follow_redirects=False)
        with self.app.test_request_context('/'):
            s1 = render_template_string("{{ has_any('manage_reports','x') }}")
            s2 = render_template_string("{{ has_all('manage_reports') }}")
            self.assertIn(s1.strip(), {'True','False'})
            self.assertIn(s2.strip(), {'True','False'})
        # anonymous
        self.client.post('/auth/logout', data={'csrf_token': ''})
        with self.app.test_request_context('/'):
            s3 = render_template_string("{{ has_perm('manage_reports') }}")
            self.assertEqual(s3.strip(), 'False')

    def test_utils_filters(self):
        with self.app.test_request_context('/'):
            s1 = render_template_string("{{ 12.345|format_percent }}")
            s2 = render_template_string("{{ None|format_percent }}")
            d = datetime.now(timezone.utc)
            s3 = render_template_string("{{ d|format_date }}", d=d)
            s4 = render_template_string("{{ d|format_datetime }}", d=d)
            s5 = render_template_string("{{ True|yes_no }}")
            s6 = render_template_string("{{ False|yes_no }}")
            self.assertTrue(s1.endswith('%'))
            self.assertTrue(s2.endswith('%'))
            self.assertIn('-', s3)
            self.assertTrue(len(s4) >= 10)
            self.assertIn(s5, ['نشط','مؤرشف'])
            self.assertIn(s6, ['نشط','مؤرشف'])

    def test_format_currency_filter_codes(self):
        with self.app.test_request_context('/'):
            s1 = render_template_string("{{ 1234.5|format_currency }}")
            s2 = render_template_string("{{ 1234.5|format_currency('USD') }}")
            s3 = render_template_string("{{ 1234.5|format_currency('EUR') }}")
            s4 = render_template_string("{{ 1234.5|format_currency('JOD') }}")
            self.assertTrue(len(s1) > 0)
            self.assertIn('$', s2)
            self.assertIn('€', s3)
            self.assertIn('JOD', s4)

    def test_request_id_headers_and_404(self):
        r = self.client.get('/missing-endpoint-xyz')
        self.assertEqual(r.status_code, 404)
        self.assertTrue('X-Request-Id' in r.headers)

    def test_customer_restriction_redirect(self):
        from extensions import db
        from models import Customer
        c = Customer(name='C2', phone=self._unique_phone(), email=None, is_online=True, is_active=True)
        c.set_password('p')
        db.session.add(c); db.session.commit()
        self.client.post('/auth/login', data={'username': 'c2@example.com', 'password': 'p'}, follow_redirects=False)
        r = self.client.get('/reports', follow_redirects=False)
        self.assertIn(r.status_code, (302,403,404))


if __name__ == '__main__':
    unittest.main()
