import unittest
from app import create_app


class TestShopPublic(unittest.TestCase):
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

    def test_catalog(self):
        resp = self.client.get('/shop/')
        self.assertEqual(resp.status_code, 200)

    def test_products(self):
        resp = self.client.get('/shop/products')
        self.assertEqual(resp.status_code, 200)

    def test_products_search(self):
        resp = self.client.get('/shop/products?query=abc')
        self.assertEqual(resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
