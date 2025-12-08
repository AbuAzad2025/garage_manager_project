import unittest
from app import create_app
from flask_login import AnonymousUserMixin


class TestPermissions(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_has_perm_anonymous(self):
        with self.app.test_request_context():
            ctx = {}
            self.app.update_template_context(ctx)
            self.assertIn('has_perm', ctx)
            res = ctx['has_perm']('manage_users')
            self.assertIsInstance(res, bool)


if __name__ == '__main__':
    unittest.main()
