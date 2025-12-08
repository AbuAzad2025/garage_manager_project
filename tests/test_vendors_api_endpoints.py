import unittest
from app import create_app


class TestVendorsApiEndpoints(unittest.TestCase):
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

    def test_suppliers_list_ajax(self):
        r = self.client.get('/vendors/suppliers?ajax=1')
        self.assertEqual(r.status_code, 200)
        j = r.get_json(silent=True) or {}
        self.assertIn('table_html', j)

    def test_partners_list_ajax(self):
        r = self.client.get('/vendors/partners?ajax=1')
        self.assertEqual(r.status_code, 200)
        j = r.get_json(silent=True) or {}
        self.assertIn('table_html', j)

    def test_suppliers_statement_ajax(self):
        r = self.client.get('/vendors/suppliers/1/statement?ajax=1')
        self.assertIn(r.status_code, {200, 404})
        if r.status_code == 200:
            j = r.get_json(silent=True) or {}
            self.assertTrue(j.get('success', False))
            self.assertIn('balance', j)

    def test_partners_statement_ajax(self):
        r = self.client.get('/vendors/partners/1/statement?ajax=1')
        self.assertIn(r.status_code, {200, 404})
        if r.status_code == 200:
            j = r.get_json(silent=True) or {}
            self.assertTrue(j.get('success', False))
            self.assertIn('balance', j)

    def test_smart_settlement_redirects(self):
        for url in [
            '/vendors/suppliers/1/smart-settlement',
            '/vendors/partners/1/smart-settlement',
        ]:
            r = self.client.get(url)
            self.assertIn(r.status_code, {302, 404})

    def test_forms_modal_json(self):
        for url in [
            '/vendors/suppliers/new?modal=1',
            '/vendors/partners/new?modal=1',
        ]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            j = r.get_json(silent=True) or {}
            self.assertTrue(j.get('success', False))
            self.assertIn('html', j)

    def test_delete_archive_restore_basic(self):
        for url, method in [
            ('/vendors/suppliers/1/delete', 'post'),
            ('/vendors/suppliers/archive/1', 'post'),
            ('/vendors/suppliers/restore/1', 'post'),
            ('/vendors/partners/1/delete', 'post'),
            ('/vendors/partners/archive/1', 'post'),
            ('/vendors/partners/restore/1', 'post'),
        ]:
            r = getattr(self.client, method)(url)
            self.assertIn(r.status_code, {302, 404})


if __name__ == '__main__':
    unittest.main()
