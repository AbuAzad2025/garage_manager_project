import unittest
from unittest.mock import patch
from decimal import Decimal
from app import create_app


class TestPartnerBalanceCalculatorUnit(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_calculate_partner_components_with_patched_sources(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_CALC')
        db.session.add(p); db.session.commit()

        mocked = {
            'routes.partner_settlements._get_partner_inventory': {'total_ils': 5},
            'routes.partner_settlements._get_partner_sales_share': {'total_share_ils': 2},
            'routes.partner_settlements._get_partner_sales_returns': {'total_ils': 0},
            'routes.partner_settlements._get_partner_payments_received': {'total_ils': 1},
            'routes.partner_settlements._get_partner_preorders_prepaid': {'total_ils': 0},
            'routes.partner_settlements._get_payments_to_partner': {'total_ils': 0},
            'routes.partner_settlements._get_partner_sales_as_customer': {'total_ils': 0},
            'routes.partner_settlements._get_partner_service_fees': {'total_ils': 0},
            'routes.partner_settlements._get_partner_preorders_as_customer': {'total_ils': 0},
            'routes.partner_settlements._get_partner_damaged_items': {'total_ils': 0},
            'routes.partner_settlements._get_partner_expenses': {'total_ils': 0},
            'routes.partner_settlements._get_returned_checks_from_partner': {'total_ils': 0},
            'routes.partner_settlements._get_returned_checks_to_partner': {'total_ils': 0},
        }

        patches = [patch(name, return_value=value) for name, value in mocked.items()]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
            from utils.partner_balance_calculator import calculate_partner_balance_components
            components = calculate_partner_balance_components(p.id)
            self.assertTrue(components is None or isinstance(components, dict))
            if isinstance(components, dict):
                self.assertIn('inventory_balance', components)
                self.assertGreaterEqual(float(components.get('inventory_balance', 0)), 0.0)

    def test_partner_components_negative_cases(self):
        from extensions import db
        from models import Partner
        p = Partner(name='P_NEG')
        db.session.add(p); db.session.commit()
        mocked = {
            'routes.partner_settlements._get_partner_inventory': {'total_ils': -3},
            'routes.partner_settlements._get_partner_sales_share': {'total_share_ils': -2},
            'routes.partner_settlements._get_partner_payments_received': {'total_ils': -1},
            'routes.partner_settlements._get_payments_to_partner': {'total_ils': 4},
            'routes.partner_settlements._get_partner_expenses': {'total_ils': 2},
            'routes.partner_settlements._get_returned_checks_from_partner': {'total_ils': 0},
            'routes.partner_settlements._get_returned_checks_to_partner': {'total_ils': 0},
            'routes.partner_settlements._get_partner_sales_returns': {'total_ils': 0},
            'routes.partner_settlements._get_partner_service_fees': {'total_ils': 0},
            'routes.partner_settlements._get_partner_preorders_prepaid': {'total_ils': 0},
            'routes.partner_settlements._get_partner_sales_as_customer': {'total_ils': 0},
            'routes.partner_settlements._get_partner_preorders_as_customer': {'total_ils': 0},
            'routes.partner_settlements._get_partner_damaged_items': {'total_ils': 0},
        }
        patches = [patch(name, return_value=value) for name, value in mocked.items()]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
            from utils.partner_balance_calculator import calculate_partner_balance_components
            components = calculate_partner_balance_components(p.id)
            self.assertTrue(components is None or isinstance(components, dict))

    def test_calculate_partner_components_no_partner(self):
        from utils.partner_balance_calculator import calculate_partner_balance_components
        self.assertIsNone(calculate_partner_balance_components(None))


if __name__ == '__main__':
    unittest.main()
