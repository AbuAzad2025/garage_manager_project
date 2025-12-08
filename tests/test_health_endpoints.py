import unittest
from app import create_app


class TestHealthEndpoints(unittest.TestCase):
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

    def test_ping(self):
        resp = self.client.get('/health/ping')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')

    def test_liveness(self):
        resp = self.client.get('/health/live')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'alive')

    def test_status_endpoint(self):
        resp = self.client.get('/health/status')
        self.assertIn(resp.status_code, (200, 503))
        data = resp.get_json()
        self.assertIn(data.get('status'), ('healthy', 'degraded', 'unhealthy'))


if __name__ == '__main__':
    unittest.main()
