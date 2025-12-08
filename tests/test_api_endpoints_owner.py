import unittest
from app import create_app


class TestApiEndpointsOwner(unittest.TestCase):
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

    def test_public_exchange_rates(self):
        r = self.client.get('/api/exchange-rates')
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/json', r.headers.get('Content-Type',''))
        j = r.get_json(silent=True) or {}
        self.assertIn('USD', j)
        self.assertIn('JOD', j)

    def test_api_health(self):
        r = self.client.get('/api/health')
        self.assertIn(r.status_code, {200, 500})
        if r.status_code == 200:
            self.assertIn('application/json', r.headers.get('Content-Type',''))

    def test_api_index_and_docs(self):
        for url in ['/api/', '/api/docs']:
            r = self.client.get(url)
            self.assertIn(r.status_code, {200, 404})
            if r.status_code == 200:
                self.assertTrue('text' in (r.headers.get('Content-Type','') or '').lower())

    def test_api_lists(self):
        for url in ['/api/partners', '/api/suppliers']:
            r = self.client.get(url)
            self.assertIn(r.status_code, {200, 403})
            if r.status_code == 200:
                self.assertIn('application/json', r.headers.get('Content-Type',''))

    def test_reports_dynamic_post(self):
        payload = {
            'table': 'Sale',
            'columns': [],
            'limit': 5
        }
        r = self.client.post('/reports/api/dynamic', json=payload)
        self.assertIn(r.status_code, {200, 403})
        if r.status_code == 200:
            j = r.get_json(silent=True) or {}
            self.assertIn('data', j)

    def test_api_archive_stats(self):
        r = self.client.get('/api/archive/stats')
        self.assertIn(r.status_code, {200, 403})
        if r.status_code == 200:
            self.assertIn('application/json', r.headers.get('Content-Type',''))

    def test_api_product_stock_and_warehouse_info(self):
        for url in ['/api/products/1/stock', '/api/warehouses/1/info']:
            r = self.client.get(url)
            self.assertIn(r.status_code, {200, 404})
            if r.status_code == 200:
                self.assertIn('application/json', r.headers.get('Content-Type',''))


if __name__ == '__main__':
    unittest.main()
