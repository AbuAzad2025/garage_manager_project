import unittest
from app import create_app
from flask import url_for


class TestUrlMap(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_core_endpoints_exist(self):
        rules = {rule.endpoint for rule in self.app.url_map.iter_rules()}
        expected = {
            'health.health_check',
            'health.ping',
            'health.readiness',
            'health.liveness',
            'health.metrics',
            'users_bp.list_users',
            'shop.products',
        }
        self.assertTrue(expected.issubset(rules))

    def test_build_urls(self):
        with self.app.test_request_context():
            url_for('health.ping')
            url_for('health.liveness')


if __name__ == '__main__':
    unittest.main()
