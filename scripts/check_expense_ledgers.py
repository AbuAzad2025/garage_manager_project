from __future__ import annotations

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from decimal import Decimal
from sqlalchemy import func, select, and_, or_
from sqlalchemy.orm import joinedload

from app import create_app
from models import (
    Expense, ExpenseType, GLBatch, GLEntry, Account,
    db, q
)


def get_expense_entity_info(expense: Expense) -> tuple[str | None, int | None, str]:
    if expense.customer_id:
        return ("CUSTOMER", expense.customer_id, f"عميل #{expense.customer_id}")
    if expense.supplier_id:
        return ("SUPPLIER", expense.supplier_id, f"مورد #{expense.supplier_id}")
    if expense.partner_id:
        return ("PARTNER", expense.partner_id, f"شريك #{expense.partner_id}")
    if expense.employee_id:
        return ("EMPLOYEE", expense.employee_id, f"موظف #{expense.employee_id}")
    
    payee_type = (expense.payee_type or "").upper()
    payee_entity_id = expense.payee_entity_id
    if payee_type in {"SUPPLIER", "PARTNER", "CUSTOMER", "EMPLOYEE"} and payee_entity_id:
        try:
            return (payee_type, int(payee_entity_id), f"{payee_type} #{payee_entity_id}")
        except (TypeError, ValueError):
            pass
    
    return (None, None, "غير محدد")


def check_expense_ledgers():
    app = create_app()
    with app.app_context():
        print("=" * 80)
        print("فحص المصاريف وتقييداتها في دفتر الأستاذ")
        print("=" * 80)
        print()
        
        all_expenses = Expense.query.filter(
            Expense.is_archived.is_(False)
        ).order_by(Expense.id.asc()).all()
        
        total_expenses = len(all_expenses)
        print(f"إجمالي المصاريف النشطة: {total_expenses}")
        print()
        
        issues = {
            "no_ledger": [],
            "unbalanced": [],
            "wrong_accounts": [],
            "wrong_entity": [],
            "amount_mismatch": [],
            "multiple_batches": [],
            "inactive_accounts": [],
        }
        
        expense_type_cache = {}
        account_cache = {}
        
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
            ).options(joinedload(GLBatch.entries)).all()
            
            if not batches:
                issues["no_ledger"].append({
                    "expense_id": exp_id,
                    "amount": exp_amount,
                    "date": expense.date,
                    "type_id": expense.type_id,
                    "description": expense.description or expense.payee_name or "",
                })
                continue
            
            if len(batches) > 1:
                issues["multiple_batches"].append({
                    "expense_id": exp_id,
                    "batch_count": len(batches),
                    "batch_ids": [b.id for b in batches],
                })
            
            for batch in batches:
                entries = batch.entries
                if not entries:
                    issues["no_ledger"].append({
                        "expense_id": exp_id,
                        "amount": exp_amount,
                        "batch_id": batch.id,
                        "issue": "batch بدون entries",
                    })
                    continue
                
                total_debit = sum(float(q(e.debit or 0)) for e in entries)
                total_credit = sum(float(q(e.credit or 0)) for e in entries)
                
                if abs(total_debit - total_credit) > 0.01:
                    issues["unbalanced"].append({
                        "expense_id": exp_id,
                        "batch_id": batch.id,
                        "debit": total_debit,
                        "credit": total_credit,
                        "difference": abs(total_debit - total_credit),
                    })
                
                expected_entity_type, expected_entity_id, entity_desc = get_expense_entity_info(expense)
                
                if batch.entity_type != expected_entity_type or batch.entity_id != expected_entity_id:
                    issues["wrong_entity"].append({
                        "expense_id": exp_id,
                        "batch_id": batch.id,
                        "expected": (expected_entity_type, expected_entity_id),
                        "actual": (batch.entity_type, batch.entity_id),
                        "entity_desc": entity_desc,
                    })
                
                for entry in entries:
                    account_code = entry.account
                    
                    if account_code not in account_cache:
                        account = Account.query.filter(Account.code == account_code).first()
                        account_cache[account_code] = account
                    else:
                        account = account_cache[account_code]
                    
                    if not account:
                        issues["wrong_accounts"].append({
                            "expense_id": exp_id,
                            "batch_id": batch.id,
                            "entry_id": entry.id,
                            "account": account_code,
                            "issue": "حساب غير موجود",
                        })
                    elif not account.is_active:
                        issues["inactive_accounts"].append({
                            "expense_id": exp_id,
                            "batch_id": batch.id,
                            "entry_id": entry.id,
                            "account": account_code,
                            "account_name": account.name,
                        })
                
                expense_account = None
                counterparty_account = None
                expense_debit = 0.0
                expense_credit = 0.0
                counterparty_debit = 0.0
                counterparty_credit = 0.0
                
                for entry in entries:
                    account_code = entry.account
                    debit = float(q(entry.debit or 0))
                    credit = float(q(entry.credit or 0))
                    
                    if account_code.startswith("5") or account_code.startswith("6"):
                        expense_account = account_code
                        expense_debit += debit
                        expense_credit += credit
                    elif account_code.startswith("1") or account_code.startswith("2"):
                        counterparty_account = account_code
                        counterparty_debit += debit
                        counterparty_credit += credit
                
                if expense.type_id not in expense_type_cache:
                    exp_type = db.session.get(ExpenseType, expense.type_id)
                    expense_type_cache[expense.type_id] = exp_type
                else:
                    exp_type = expense_type_cache[expense.type_id]
                
                if exp_type:
                    import json
                    meta = exp_type.fields_meta
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except:
                            meta = {}
                    ledger = meta.get("ledger", {}) if isinstance(meta, dict) else {}
                    expected_expense_account = ledger.get("expense_account") or "5000_EXPENSES"
                    
                    if expense_account and expense_account != expected_expense_account:
                        issues["wrong_accounts"].append({
                            "expense_id": exp_id,
                            "batch_id": batch.id,
                            "account": expense_account,
                            "expected": expected_expense_account,
                            "expense_type": exp_type.name,
                            "issue": "حساب مصروف غير متطابق مع نوع المصروف",
                        })
        
        print("=" * 80)
        print("نتائج الفحص:")
        print("=" * 80)
        print()
        
        print(f"✅ المصاريف بدون قيود في دفتر الأستاذ: {len(issues['no_ledger'])}")
        if issues["no_ledger"]:
            print("   المصاريف:")
            for item in issues["no_ledger"][:10]:
                print(f"   - مصروف #{item['expense_id']}: {item.get('amount', 0):.2f} ₪ - {item.get('description', '')[:50]}")
            if len(issues["no_ledger"]) > 10:
                print(f"   ... و {len(issues['no_ledger']) - 10} مصروفات أخرى")
        print()
        
        print(f"⚠️  القيود غير المتوازنة: {len(issues['unbalanced'])}")
        if issues["unbalanced"]:
            for item in issues["unbalanced"][:5]:
                print(f"   - مصروف #{item['expense_id']}, batch #{item['batch_id']}: فرق {item['difference']:.2f} ₪")
        print()
        
        print(f"⚠️  حسابات غير صحيحة أو غير موجودة: {len(issues['wrong_accounts'])}")
        if issues["wrong_accounts"]:
            for item in issues["wrong_accounts"][:5]:
                print(f"   - مصروف #{item['expense_id']}, batch #{item['batch_id']}: {item.get('issue', '')} - {item.get('account', '')}")
        print()
        
        print(f"⚠️  حسابات غير نشطة: {len(issues['inactive_accounts'])}")
        if issues["inactive_accounts"]:
            for item in issues["inactive_accounts"][:5]:
                print(f"   - مصروف #{item['expense_id']}, batch #{item['batch_id']}: {item['account']} ({item.get('account_name', '')})")
        print()
        
        print(f"⚠️  entity_type/entity_id غير صحيح: {len(issues['wrong_entity'])}")
        if issues["wrong_entity"]:
            for item in issues["wrong_entity"][:5]:
                print(f"   - مصروف #{item['expense_id']}, batch #{item['batch_id']}: متوقع {item['expected']}, فعلي {item['actual']}")
        print()
        
        print(f"⚠️  مصاريف لها أكثر من batch: {len(issues['multiple_batches'])}")
        if issues["multiple_batches"]:
            for item in issues["multiple_batches"][:5]:
                print(f"   - مصروف #{item['expense_id']}: {item['batch_count']} batches")
        print()
        
        total_issues = sum(len(v) for v in issues.values())
        print("=" * 80)
        print(f"إجمالي المشاكل المكتشفة: {total_issues}")
        print("=" * 80)
        
        if total_issues == 0:
            print()
            print("✅ جميع المصاريف مقيدة بشكل صحيح في دفتر الأستاذ!")
        
        return issues


if __name__ == "__main__":
    check_expense_ledgers()

