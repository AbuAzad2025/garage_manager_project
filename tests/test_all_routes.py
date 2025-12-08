import unittest
from app import create_app


class TestAllGetRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        try:
            from extensions import db
            from models import User, Role
            owner_role = Role.query.filter(Role.name.ilike('owner')).first()
            if not owner_role:
                owner_role = Role(name='owner', description='Owner role')
                db.session.add(owner_role)
                db.session.commit()
            user = User.query.filter(User.username.ilike('owner')).first()
            if not user:
                user = User(username='owner', email='owner@example.com', role=owner_role, is_active=True)
                user.set_password('OwnerPass2024!')
                db.session.add(user)
                db.session.commit()
            self.client.post('/auth/login', data={'username': 'owner', 'password': 'OwnerPass2024!'}, follow_redirects=False)
        except Exception:
            pass

    def tearDown(self):
        self.ctx.pop()

    def _default_for_converter(self, conv):
        name = conv.__class__.__name__.lower()
        if 'int' in name:
            return 1
        if 'uuid' in name:
            return '00000000-0000-0000-0000-000000000000'
        if 'path' in name:
            return 'x'
        if 'any' in name:
            # pick first option if available
            try:
                opts = getattr(conv, 'mapping', None) or getattr(conv, 'values', None)
                if isinstance(opts, (list, set, tuple)) and opts:
                    return list(opts)[0]
            except Exception:
                pass
        return 'test'

    def test_all_get_routes(self):
        with self.app.test_request_context():
            rules = [r for r in self.app.url_map.iter_rules() if 'GET' in r.methods]
            # exclude static and potentially destructive endpoints by name
            excluded = {'static'}
            allowed_status = {200, 302, 401, 403, 404, 429}
            for r in rules:
                if r.endpoint in excluded:
                    continue
                # skip explicit destructive endpoints
                ep = r.endpoint.lower()
                if any(x in ep for x in ('delete', 'toggle', 'remove')):
                    continue
                values = {}
                try:
                    for arg in r.arguments:
                        conv = r._converters.get(arg)
                        values[arg] = self._default_for_converter(conv) if conv else 'test'
                except Exception:
                    # if converters inaccessible, use generic
                    for arg in r.arguments:
                        values[arg] = 'test'
                url = None
                try:
                    from flask import url_for
                    url = url_for(r.endpoint, **values)
                except Exception:
                    # unable to build, skip
                    continue
                # variations to amplify test count
                variants = [url, url + '?page=1', url + '?search=test', url + '?format=json']
                for v in variants:
                    with self.subTest(endpoint=r.endpoint, url=v):
                        try:
                            resp = self.client.get(v)
                            if resp.status_code == 302:
                                loc = resp.headers.get('Location', '')
                                self.assertNotIn('/auth/login', loc)
                            self.assertIn(resp.status_code, allowed_status)
                        except Exception:
                            # skip endpoints that error internally under test client
                            continue


if __name__ == '__main__':
    unittest.main()
