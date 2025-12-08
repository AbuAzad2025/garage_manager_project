import unittest
from app import create_app


class TestWarehousesApiEndpoints(unittest.TestCase):
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

    def test_api_warehouse_info(self):
        r = self.client.get('/warehouses/api/warehouse-info')
        self.assertEqual(r.status_code, 400)
        r2 = self.client.get('/warehouses/api/warehouse-info?id=1')
        self.assertIn(r2.status_code, {200, 404})

    def test_prepare_online_fields(self):
        r = self.client.get('/warehouses/api/prepare_online_fields')
        self.assertEqual(r.status_code, 400)
        r2 = self.client.get('/warehouses/api/prepare_online_fields?warehouse_id=1')
        self.assertIn(r2.status_code, {200, 404})
        if r2.status_code == 200:
            j = r2.get_json(silent=True) or {}
            self.assertIn('schema', j)

    def test_lists_partners_suppliers(self):
        for url in ['/warehouses/api/partners/list', '/warehouses/api/suppliers/list']:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn('application/json', r.headers.get('Content-Type',''))

    def test_product_relations(self):
        for url in ['/warehouses/api/products/1/partners', '/warehouses/api/products/1/suppliers']:
            r = self.client.get(url)
            self.assertIn(r.status_code, {200, 404})


if __name__ == '__main__':
    unittest.main()
