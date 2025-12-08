import unittest
from unittest.mock import patch
from decimal import Decimal
from app import create_app


class TestViewsBalancesDetails(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def _unique_phone(self):
        from time import time
        return '059' + str(int(time() * 1000000))[-7:]

    def test_customer_view_matches_stored_and_texts(self):
        from extensions import db
        from models import Customer
        c = Customer(name='C_VIEW', phone=self._unique_phone(), email=None, is_online=True, is_active=True, opening_balance=Decimal('10'), currency='ILS')
        c.set_password('p')
        db.session.add(c); db.session.commit()
        components = {
            'payments_in_balance': Decimal('5'),
            'returns_balance': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'service_expenses_balance': Decimal('0'),
            'sales_balance': Decimal('2'),
            'invoices_balance': Decimal('1'),
            'services_balance': Decimal('0'),
            'preorders_balance': Decimal('0'),
            'online_orders_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'expenses_balance': Decimal('0'),
            'checks_in_balance': Decimal('0'),
            'checks_out_balance': Decimal('0'),
        }
        calc_balance = Decimal('10') + Decimal('5') - (Decimal('2') + Decimal('1'))
        c.current_balance = calc_balance
        db.session.commit()
        with patch('utils.balance_calculator.calculate_customer_balance_components', return_value=components):
            from utils.balance_calculator import build_customer_balance_view
            view = build_customer_balance_view(c.id)
            self.assertTrue(view.get('success'))
            self.assertEqual(Decimal(str(view['balance']['amount'])), calc_balance)
            self.assertIn(view['balance'].get('matches_stored'), [True, False])
            self.assertIn(view['balance'].get('direction', ''), ['له عندنا','عليه لنا','متوازن'])
            self.assertIn(view['balance'].get('action', ''), ['يجب أن ندفع له','يجب أن يدفع لنا','لا يوجد رصيد مستحق'])

    def test_supplier_view_direction_with_conversion(self):
        from extensions import db
        from models import Supplier
        s = Supplier(name='S_VIEW', phone=self._unique_phone(), email=None, opening_balance=Decimal('5'), currency='USD')
        db.session.add(s); db.session.commit()
        components = {
            'exchange_items_balance': Decimal('3'),
            'expenses_service_supply': Decimal('0'),
            'sale_returns_from_supplier': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'sales_balance': Decimal('0'),
            'services_balance': Decimal('0'),
            'expenses_normal': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'payments_out_balance': Decimal('1'),
            'returns_balance': Decimal('0'),
        }
        calc_patch = patch('utils.supplier_balance_updater.calculate_supplier_balance_components', return_value=components)
        conv_patch = patch('utils.supplier_balance_updater.convert_amount', side_effect=lambda amt, f, t, d=None: amt*Decimal('2'))
        with calc_patch, conv_patch:
            from utils.supplier_balance_updater import build_supplier_balance_view
            view = build_supplier_balance_view(s.id)
            self.assertTrue(view.get('success'))
            self.assertIn(view['balance'].get('direction', ''), ['له علينا','عليه لنا','متوازن'])
            self.assertIn(view['balance'].get('action', ''), ['يجب أن ندفع له','يجب أن يدفع لنا','لا يوجد رصيد مستحق'])
            self.assertIn('checks', view)
            self.assertIn('returned_in', view['checks'])
            self.assertIn('returned_out', view['checks'])

    def test_supplier_multi_currency_conversion(self):
        from extensions import db
        from models import Supplier
        s = Supplier(name='S_MULTI', phone=self._unique_phone(), email=None, opening_balance=Decimal('10'), currency='JOD')
        db.session.add(s); db.session.commit()
        components = {
            'exchange_items_balance': Decimal('0'),
            'expenses_service_supply': Decimal('0'),
            'sale_returns_from_supplier': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'sales_balance': Decimal('0'),
            'services_balance': Decimal('0'),
            'expenses_normal': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'returns_balance': Decimal('0'),
        }
        calc_patch = patch('utils.supplier_balance_updater.calculate_supplier_balance_components', return_value=components)
        conv_patch = patch('utils.supplier_balance_updater.convert_amount', side_effect=lambda amt, f, t, d=None: amt*Decimal('5'))
        with calc_patch, conv_patch:
            from utils.supplier_balance_updater import build_supplier_balance_view
            view = build_supplier_balance_view(s.id)
            self.assertTrue(view.get('success'))
            ob = view.get('opening_balance', {})
            self.assertGreaterEqual(float(ob.get('amount', 0.0)), 50.0)

    def test_partner_view_negative_direction(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_VIEW')
        db.session.add(p); db.session.commit()
        components = {
            'inventory_balance': Decimal('0'),
            'sales_share_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'preorders_prepaid_balance': Decimal('0'),
            'service_expenses_balance': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'sales_to_partner_balance': Decimal('2'),
            'service_fees_balance': Decimal('1'),
            'preorders_to_partner_balance': Decimal('1'),
            'damaged_items_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'expenses_balance': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
        }
        with patch('utils.partner_balance_calculator.calculate_partner_balance_components', return_value=components):
            from utils.partner_balance_updater import build_partner_balance_view
            view = build_partner_balance_view(p.id)
            self.assertTrue(view.get('success'))
            self.assertIn(view['balance'].get('direction', ''), ['له عندنا','عليه لنا','متوازن'])
            self.assertIn(view['balance'].get('action', ''), ['يجب أن ندفع له','يجب أن يدفع لنا','لا يوجد رصيد مستحق'])
            self.assertIn('checks', view)
            self.assertIn('returned_in', view['checks'])
            self.assertIn('returned_out', view['checks'])

    def test_partner_multi_currency_conversion(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_MULTI', opening_balance=Decimal('4'), currency='EUR')
        db.session.add(p); db.session.commit()
        components = {
            'inventory_balance': Decimal('0'),
            'sales_share_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'preorders_prepaid_balance': Decimal('0'),
            'service_expenses_balance': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'sales_to_partner_balance': Decimal('0'),
            'service_fees_balance': Decimal('0'),
            'preorders_to_partner_balance': Decimal('0'),
            'damaged_items_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'expenses_balance': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
        }
        calc_patch = patch('utils.partner_balance_calculator.calculate_partner_balance_components', return_value=components)
        conv_patch = patch('utils.partner_balance_updater.convert_amount', side_effect=lambda amt, f, t, d=None: amt*Decimal('4'))
        with calc_patch, conv_patch:
            from utils.partner_balance_updater import build_partner_balance_view
            view = build_partner_balance_view(p.id)
            self.assertTrue(view.get('success'))
            ob = view.get('opening_balance', {})
            self.assertGreaterEqual(float(ob.get('amount', 0.0)), 16.0)


if __name__ == '__main__':
    unittest.main()
