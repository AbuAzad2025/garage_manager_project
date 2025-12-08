import unittest
from app import create_app


class TestHealthMore(unittest.TestCase):
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

    def test_ready_endpoint(self):
        resp = self.client.get('/health/ready')
        self.assertIn(resp.status_code, (200, 503))

    def test_metrics_endpoint(self):
        resp = self.client.get('/health/metrics')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('process', data)
        self.assertIn('system', data)


if __name__ == '__main__':
    unittest.main()
