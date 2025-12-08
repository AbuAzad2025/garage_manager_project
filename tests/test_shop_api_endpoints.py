import unittest
from app import create_app


class TestShopApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_catalog_json(self):
        r = self.client.get('/shop/?format=json')
        self.assertIn(r.status_code, {200})
        self.assertIn('application/json', r.headers.get('Content-Type',''))
        data = r.get_json(silent=True)
        self.assertIsInstance(data, list)

    def test_api_products_json(self):
        r = self.client.get('/shop/api/products')
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/json', r.headers.get('Content-Type',''))
        j = r.get_json(silent=True) or {}
        self.assertIn('data', j)

    def test_api_product_detail_not_found(self):
        r = self.client.get('/shop/api/product/999999')
        self.assertIn(r.status_code, {404, 500})


if __name__ == '__main__':
    unittest.main()
