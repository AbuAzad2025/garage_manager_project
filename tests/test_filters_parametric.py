import unittest
from app import create_app


class TestFiltersParametric(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_number_format_cases(self):
        env = self.app.jinja_env
        f = env.filters.get('format_number')
        cases = [0, 1, -1, 1.2345, 123456789, None, 'abc', '12.34', 0.0001, 99999.9999]
        for i in range(100):
            for c in cases:
                with self.subTest(i=i, case=c):
                    s = f(c)
                    self.assertTrue(isinstance(s, str))

    def test_currency_format_cases(self):
        env = self.app.jinja_env
        f = env.filters.get('format_currency')
        cases = [(0, 'ILS'), (1.5, 'USD'), (1234.56, 'EUR'), (-10, 'ILS'), ('abc', 'ILS')]
        for i in range(50):
            for val, cur in cases:
                with self.subTest(i=i, val=val, cur=cur):
                    s = f(val, cur)
                    self.assertTrue(isinstance(s, str))


if __name__ == '__main__':
    unittest.main()

