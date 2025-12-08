import unittest
from app import create_app


class TestJinjaEnv(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_filters_exist(self):
        env = self.app.jinja_env
        self.assertIn('format_number', env.filters)
        self.assertIn('format_currency', env.filters)
        self.assertIn('format_date', env.filters)

    def test_static_version_filter(self):
        f = self.app.jinja_env.filters.get('static_version')
        self.assertIsNotNone(f)
        res = f('static/css/app.css')
        self.assertTrue(isinstance(res, str))


if __name__ == '__main__':
    unittest.main()

