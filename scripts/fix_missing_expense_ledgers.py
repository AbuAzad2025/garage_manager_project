from __future__ import annotations

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app import create_app
from models import (
    Expense, ExpenseType, GLBatch, GLEntry, Account,
    db, q, _expense_type_ledger_settings, _expense_entity_pair,
    _gl_upsert_batch_and_entries, GL_ACCOUNTS, fx_rate
)
from datetime import datetime, timezone


def fix_missing_expense_ledgers(dry_run=True):
    app = create_app()
    with app.app_context():
        print("=" * 80)
        print("إصلاح المصاريف بدون قيود في دفتر الأستاذ")
        print("=" * 80)
        print()
        
        if dry_run:
            print("⚠️  وضع التجربة - لن يتم حفظ التغييرات")
        else:
            print("✅ وضع الإصلاح - سيتم حفظ التغييرات")
        print()
        
        all_expenses = Expense.query.filter(
            Expense.is_archived.is_(False)
        ).order_by(Expense.id.asc()).all()
        
        expenses_without_ledger = []
        
        for expense in all_expenses:
            exp_id = expense.id
            exp_amount = float(q(expense.amount or 0))
            
            if exp_amount <= 0:
                continue
            
            batches = GLBatch.query.filter(
                and_(
                    GLBatch.source_type == "EXPENSE",
                    GLBatch.source_id == exp_id,
                    GLBatch.purpose == "ACCRUAL"
                )
            ).all()
            
            if not batches:
                expenses_without_ledger.append(expense)
        
        print(f"عدد المصاريف بدون قيود: {len(expenses_without_ledger)}")
        print()
        
        if not expenses_without_ledger:
            print("✅ جميع المصاريف مقيدة بشكل صحيح!")
            return
        
        fixed_count = 0
        error_count = 0
        
        connection = db.session.connection()
        
        for expense in expenses_without_ledger:
            try:
                exp_id = expense.id
                exp_amount = float(q(expense.amount or 0))
                
                if exp_amount <= 0:
                    continue
                
                ledger = _expense_type_ledger_settings(connection, expense.type_id)
                expense_account = ledger.get("expense_account") or GL_ACCOUNTS.get("EXP", "5000_EXPENSES")
                counterparty_account = ledger.get("counterparty_account") or GL_ACCOUNTS.get("AP", "2000_AP")
                
                if ledger.get("behavior") == "IMMEDIATE" and not ledger.get("counterparty_account"):
                    counterparty_account = ledger.get("cash_account") or counterparty_account or GL_ACCOUNTS.get("CASH", "1000_CASH")
                
                if not expense_account or not counterparty_account:
                    print(f"⚠️  مصروف #{exp_id}: حسابات غير محددة - expense: {expense_account}, counterparty: {counterparty_account}")
                    error_count += 1
                    continue
                
                amount_ils = exp_amount
                posting_currency = "ILS"
                original_currency = (expense.currency or "ILS").upper()
                
                if original_currency != "ILS":
                    try:
                        rate = fx_rate(original_currency, "ILS", expense.date or datetime.now(timezone.utc), raise_on_missing=False)
                        if rate and rate > 0:
                            amount_ils = float(exp_amount * float(rate))
                    except Exception:
                        pass
                
                exp_type_code = None
                try:
                    if expense.type_id:
                        exp_type_row = connection.execute(
                            select(ExpenseType.code).where(ExpenseType.id == expense.type_id)
                        ).scalar_one_or_none()
                        exp_type_code = (exp_type_row or "").strip().upper() if exp_type_row else None
                except Exception:
                    pass
                
                is_supplier_service = (
                    exp_type_code == "SUPPLIER_EXPENSE" or
                    (expense.supplier_id and (expense.payee_type or "").upper() == "SUPPLIER")
                )
                is_partner_service = (
                    exp_type_code == "PARTNER_EXPENSE" or
                    (expense.partner_id and (expense.payee_type or "").upper() == "PARTNER")
                )
                
                if is_supplier_service or is_partner_service:
                    entries = [
                        (counterparty_account, amount_ils, 0.0),
                        (expense_account, 0.0, amount_ils),
                    ]
                    memo_type = "توريد خدمة"
                else:
                    entries = [
                        (expense_account, amount_ils, 0.0),
                        (counterparty_account, 0.0, amount_ils),
                    ]
                    memo_type = "مصروف"
                
                entity_type, entity_id = _expense_entity_pair(expense)
                
                if not dry_run:
                    _gl_upsert_batch_and_entries(
                        connection,
                        source_type="EXPENSE",
                        source_id=expense.id,
                        purpose="ACCRUAL",
                        currency=posting_currency,
                        memo=f"قيد {memo_type} #{expense.id}",
                        entries=entries,
                        ref=f"EXP-{expense.id}",
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )
                
                print(f"{'✅' if not dry_run else '🔍'} مصروف #{exp_id}: {exp_amount:.2f} ₪ - {memo_type} - {expense_account} / {counterparty_account}")
                fixed_count += 1
                
            except Exception as e:
                print(f"❌ خطأ في مصروف #{expense.id}: {e}")
                error_count += 1
        
        print()
        print("=" * 80)
        print(f"تم معالجة {fixed_count} مصروف")
        if error_count > 0:
            print(f"❌ {error_count} أخطاء")
        print("=" * 80)
        
        if not dry_run and fixed_count > 0:
            try:
                db.session.commit()
                print()
                print("✅ تم حفظ التغييرات بنجاح!")
            except Exception as e:
                db.session.rollback()
                print()
                print(f"❌ خطأ في حفظ التغييرات: {e}")
        
        return {
            "fixed": fixed_count,
            "errors": error_count,
            "total": len(expenses_without_ledger)
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="إصلاح المصاريف بدون قيود في دفتر الأستاذ")
    parser.add_argument("--apply", action="store_true", help="تطبيق التغييرات (بدون هذا الخيار سيكون dry-run)")
    args = parser.parse_args()
    
    fix_missing_expense_ledgers(dry_run=not args.apply)

