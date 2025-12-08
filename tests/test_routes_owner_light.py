import unittest
from app import create_app


class TestRoutesOwnerLight(unittest.TestCase):
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

    def test_sample_get_routes(self):
        targets = [
            '/', '/dashboard', '/user-guide', '/notes',
            '/shop', '/shop/catalog', '/shop/categories', '/shop/search',
            '/customers', '/vendors', '/warehouses', '/payments', '/expenses', '/service', '/reports', '/branches'
        ]
        available = {r.rule for r in self.app.url_map.iter_rules() if 'GET' in r.methods}
        urls = [u for u in targets if u in available]
        allowed = {200, 302, 403, 404}
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.get(url)
                if resp.status_code == 302:
                    loc = resp.headers.get('Location', '')
                    self.assertNotIn('/auth/login', loc)
                self.assertIn(resp.status_code, allowed)

    def test_json_endpoints_owner(self):
        available = {r.rule for r in self.app.url_map.iter_rules() if 'GET' in r.methods}
        targets = ['/automated-backup-status', '/advanced/api/performance/stats']
        urls = [u for u in targets if u in available]
        for url in urls:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertIn(r.status_code, {200, 403})
                if r.status_code == 200:
                    ct = r.headers.get('Content-Type','')
                    self.assertIn('application/json', ct)

    def test_maintenance_mode_for_non_owner(self):
        from extensions import db
        from models import User, Role, SystemSettings
        r = Role.query.filter(Role.name.ilike('viewer')).first() or Role(name='viewer')
        db.session.add(r); db.session.commit()
        u = User.query.filter(User.username.ilike('viewer_test')).first()
        if not u:
            u = User(username='viewer_test', email='viewer_test@example.com', role=r, is_active=True)
            u.set_password('pass')
            db.session.add(u); db.session.commit()
        setting = SystemSettings.query.filter_by(key='maintenance_mode').first()
        if not setting:
            SystemSettings.set_setting('maintenance_mode', 'True', 'Maintenance mode', data_type='bool', is_public=False)
        else:
            setting.value = 'True'
            db.session.commit()
        self.client.post('/auth/login', data={'username': 'viewer_test', 'password': 'pass'}, follow_redirects=False)
        r = self.client.get('/dashboard')
        self.assertEqual(r.status_code, 503)
        # Turn off maintenance
        setting = SystemSettings.query.filter_by(key='maintenance_mode').first()
        setting.value = 'False'
        db.session.commit()

    def test_maintenance_mode_owner_bypass(self):
        from extensions import db
        from models import SystemSettings
        setting = SystemSettings.query.filter_by(key='maintenance_mode').first()
        if not setting:
            SystemSettings.set_setting('maintenance_mode', 'True', 'Maintenance mode', data_type='bool', is_public=False)
        else:
            setting.value = 'True'
            db.session.commit()
        try:
            from tests import login_owner
            login_owner(self.app, self.client)
        except Exception:
            pass
        r = self.client.get('/dashboard')
        self.assertNotEqual(r.status_code, 503)
        # Turn off maintenance
        setting = SystemSettings.query.filter_by(key='maintenance_mode').first()
        setting.value = 'False'
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
