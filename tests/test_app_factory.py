import unittest
from app import create_app


class TestAppFactory(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_app_created(self):
        self.assertIsNotNone(self.app)
        self.assertTrue(hasattr(self.app, 'blueprints'))

    def test_health_blueprint_registered(self):
        self.assertIn('health', self.app.blueprints)

    def test_users_blueprint_registered(self):
        self.assertIn('users_bp', self.app.blueprints)


if __name__ == '__main__':
    unittest.main()

