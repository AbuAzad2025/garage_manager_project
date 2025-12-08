import unittest
from app import create_app


class TestUrlForAny(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_url_for_any(self):
        with self.app.test_request_context():
            fn = self.app.jinja_env.globals.get('url_for_any')
            self.assertIsNotNone(fn)
            r = fn('health.ping', 'health.live')
            self.assertTrue(isinstance(r, str))


if __name__ == '__main__':
    unittest.main()

