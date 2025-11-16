from __future__ import annotations

import json

from app import create_app
from models import ExpenseType, db


EXPENSE_ACCOUNTS = {
    "OTHER": "5000_EXPENSES",
    "RENT": "6200_RENT",
    "TELECOM": "6310_TELECOM",
    "CONSULTING": "6405_CONSULTING_FEES",
    "SOFTWARE": "6930_SOFTWARE",
    "INSURANCE": "6700_INSURANCE",
    "SHIP_INSURANCE": "5510_SHIP_INSURANCE",
    "INS_OLD": "6700_INSURANCE",
    "SHIP_STORAGE": "5580_SHIP_STORAGE",
    "SHIP_CLEARANCE": "5550_SHIP_CLEARANCE",
    "TRAINING": "6910_TRAINING",
    "ENTERTAINMENT": "6980_ENTERTAINMENT",
    "MARKETING_OLD": "6920_MARKETING",
    "MARKETING": "6920_MARKETING",
    "SHIP_CUSTOMS": "5520_SHIP_CUSTOMS",
    "BANK_FEES": "6940_BANK_FEES",
    "GOV_FEES": "6800_GOV_FEES",
    "SHIP_PORT_FEES": "5570_SHIP_PORT_FEES",
    "SALARY": "6100_SALARIES",
    "SALARY_OLD_DISABLED": "6100_SALARIES",
    "TRAVEL": "6900_TRAVEL",
    "EMPLOYEE_ADVANCE": "6110_EMPLOYEE_ADVANCES",
    "SHIP_FREIGHT": "5540_SHIP_FREIGHT",
    "MAINTENANCE": "6400_MAINTENANCE",
    "TAX_FEES": "6805_TAXES",
    "SHIP_IMPORT_TAX": "5530_SHIP_IMPORT_TAX",
    "HOSPITALITY": "6950_HOSPITALITY",
    "OFFICE": "6600_OFFICE",
    "OFFICE_OLD": "6600_OFFICE",
    "UTILITIES": "6300_UTILITIES",
    "HOME_EXPENSE": "6960_HOME_EXPENSE",
    "HOME_OLD": "6960_HOME_EXPENSE",
    "OWNERS_EXPENSE": "6970_OWNER_CURRENT",
    "PARTNER_EXPENSE": "5200_PARTNER_EXPENSES",
    "SUPPLIER_EXPENSE": "5100_SUPPLIER_EXPENSES",
    "SHIP_HANDLING": "5560_SHIP_HANDLING",
    "TRANSPORT": "6975_TRANSPORT",
    "FUEL": "6500_FUEL",
    "NONE": "5000_EXPENSES",
}

DEFAULT_EXPENSE = "5000_EXPENSES"
DEFAULT_CASH = "1000_CASH"
DEFAULT_COUNTERPARTY = "2000_AP"

COUNTERPARTY_OVERRIDES = {
    "EMPLOYEE_ADVANCE": "2150_EMPLOYEE_ADVANCES",
    "SALARY": "2150_PAYROLL_CLEARING",
    "SALARY_OLD_DISABLED": "2150_PAYROLL_CLEARING",
    "PARTNER_EXPENSE": "2200_PARTNER_CLEARING",
    "SUPPLIER_EXPENSE": "2000_AP",
    "OWNERS_EXPENSE": "3100_OWNER_CURRENT",
    "HOME_EXPENSE": "3100_OWNER_CURRENT",
    "HOME_OLD": "3100_OWNER_CURRENT",
}

def _load_meta(expense_type: ExpenseType) -> dict:
    meta = expense_type.fields_meta
    if isinstance(meta, dict):
        return dict(meta)
    if isinstance(meta, str) and meta.strip():
        try:
            parsed = json.loads(meta)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def main():
    app = create_app()
    with app.app_context():
        updated = 0

        for et in ExpenseType.query.all():
            meta = _load_meta(et)
            ledger = dict(meta.get("ledger") or {})

            expense_code = EXPENSE_ACCOUNTS.get(et.code or "", DEFAULT_EXPENSE)
            counterparty_code = COUNTERPARTY_OVERRIDES.get(et.code or "", DEFAULT_COUNTERPARTY)

            changed = False

            if ledger.get("expense_account") != expense_code:
                ledger["expense_account"] = expense_code
                changed = True

            if ledger.get("counterparty_account") != counterparty_code:
                ledger["counterparty_account"] = counterparty_code
                changed = True

            if ledger.get("cash_account") != DEFAULT_CASH:
                ledger["cash_account"] = DEFAULT_CASH
                changed = True

            meta["ledger"] = ledger

            desired_behavior = "ON_ACCOUNT"
            if meta.get("payment_behavior") != desired_behavior:
                meta["payment_behavior"] = desired_behavior
                changed = True

            if changed:
                et.fields_meta = meta
                updated += 1

        if updated:
            db.session.commit()
        print(f"Updated {updated} expense types")


if __name__ == "__main__":
    main()

