import unittest
from unittest.mock import patch
from time import time
from decimal import Decimal
from app import create_app


class TestUtilsBalancesSmoke(unittest.TestCase):
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
        return '059' + str(int(time() * 1000000))[-7:]

    def test_build_customer_balance_view_monkeypatched(self):
        from extensions import db
        from models import Customer
        c = Customer(name='C_BAL', phone=self._unique_phone(), email=None, is_online=True, is_active=True)
        c.set_password('p')
        db.session.add(c); db.session.commit()
        components = {
            'payments_in_balance': Decimal('10'),
            'returns_balance': Decimal('2'),
            'returned_checks_out_balance': Decimal('0'),
            'service_expenses_balance': Decimal('0'),
            'sales_balance': Decimal('5'),
            'invoices_balance': Decimal('1'),
            'services_balance': Decimal('1'),
            'preorders_balance': Decimal('0'),
            'online_orders_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'expenses_balance': Decimal('0'),
            'checks_in_balance': Decimal('0'),
            'checks_out_balance': Decimal('0'),
        }
        with patch('utils.balance_calculator.calculate_customer_balance_components', return_value=components):
            from utils.balance_calculator import build_customer_balance_view
            view = build_customer_balance_view(c.id)
            self.assertTrue(view.get('success'))
            self.assertIn('rights', view)
            self.assertIn('obligations', view)

    def test_update_customer_balance_components_monkeypatched(self):
        from extensions import db
        from models import Customer
        c = Customer(name='C_UPD', phone=self._unique_phone(), email=None, is_online=True, is_active=True)
        c.set_password('p')
        db.session.add(c); db.session.commit()
        components = {
            'sales_balance': Decimal('7'),
            'returns_balance': Decimal('1'),
            'invoices_balance': Decimal('0'),
            'services_balance': Decimal('1'),
            'preorders_balance': Decimal('0'),
            'online_orders_balance': Decimal('0'),
            'payments_in_balance': Decimal('3'),
            'payments_out_balance': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'expenses_balance': Decimal('0'),
        }
        with patch('utils.balance_calculator.calculate_customer_balance_components', return_value=components):
            from utils.customer_balance_updater import update_customer_balance_components
            update_customer_balance_components(c.id)
            db.session.refresh(c)
            self.assertIsInstance(float(c.current_balance or 0), float)

    def test_build_supplier_balance_view_monkeypatched(self):
        from extensions import db
        from models import Supplier
        s = Supplier(name='S_BAL', phone=self._unique_phone(), email=None, currency='USD', opening_balance=Decimal('10'))
        db.session.add(s); db.session.commit()
        components = {
            'exchange_items_balance': Decimal('10'),
            'expenses_service_supply': Decimal('2'),
            'sale_returns_from_supplier': Decimal('0'),
            'returned_checks_out_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'sales_balance': Decimal('5'),
            'services_balance': Decimal('1'),
            'expenses_normal': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'returns_balance': Decimal('0'),
        }
        calc_patch = patch('utils.supplier_balance_updater.calculate_supplier_balance_components', return_value=components)
        conv_patch = patch('utils.supplier_balance_updater.convert_amount', side_effect=lambda amt, f, t, d=None: amt*Decimal('2'))
        with calc_patch, conv_patch:
            from utils.supplier_balance_updater import build_supplier_balance_view
            view = build_supplier_balance_view(s.id)
            self.assertTrue(view.get('success'))
            self.assertIn('rights', view)
            self.assertIn('obligations', view)
            ob = view.get('opening_balance', {})
            self.assertGreater(float(ob.get('amount', 0.0)), 10.0)

    def test_update_supplier_balance_components_monkeypatched(self):
        from extensions import db
        from models import Supplier
        s = Supplier(name='S_UPD', phone=self._unique_phone(), email=None)
        db.session.add(s); db.session.commit()
        components = {
            'exchange_items_balance': Decimal('1'),
            'expenses_service_supply': Decimal('1'),
            'sale_returns_from_supplier': Decimal('1'),
            'returned_checks_out_balance': Decimal('0'),
            'payments_in_balance': Decimal('0'),
            'sales_balance': Decimal('0'),
            'services_balance': Decimal('0'),
            'expenses_normal': Decimal('0'),
            'returned_checks_in_balance': Decimal('0'),
            'payments_out_balance': Decimal('0'),
            'returns_balance': Decimal('0'),
        }
        with patch('utils.supplier_balance_updater.calculate_supplier_balance_components', return_value=components):
            from utils.supplier_balance_updater import update_supplier_balance_components
            update_supplier_balance_components(s.id, session=db.session)
            db.session.refresh(s)
            self.assertGreaterEqual(float(s.current_balance or 0), 0.0)

    def test_build_partner_balance_view_monkeypatched(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_BAL', opening_balance=Decimal('3'), currency='USD')
        db.session.add(p); db.session.commit()
        components = {
            'inventory_balance': Decimal('3'),
            'sales_share_balance': Decimal('2'),
            'payments_in_balance': Decimal('1'),
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
        conv_patch = patch('utils.partner_balance_updater.convert_amount', side_effect=lambda amt, f, t, d=None: amt*Decimal('2'))
        with calc_patch, conv_patch:
            from utils.partner_balance_updater import build_partner_balance_view
            view = build_partner_balance_view(p.id)
            self.assertTrue(view.get('success'))
            self.assertIn('rights', view)
            self.assertIn('obligations', view)
            ob = view.get('opening_balance', {})
            self.assertGreater(float(ob.get('amount', 0.0)), 3.0)

    def test_update_partner_balance_components_monkeypatched(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_UPD')
        db.session.add(p); db.session.commit()
        components = {
            'inventory_balance': Decimal('1'),
            'sales_share_balance': Decimal('1'),
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
        with patch('utils.partner_balance_calculator.calculate_partner_balance_components', return_value=components):
            from utils.partner_balance_updater import update_partner_balance_components
            update_partner_balance_components(p.id, session=db.session)
            db.session.refresh(p)
            self.assertIsInstance(float(p.current_balance or 0), float)


if __name__ == '__main__':
    unittest.main()
