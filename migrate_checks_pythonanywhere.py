#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Data Migration: إنشاء سجلات Check من Payments/Splits/Expenses الموجودة
للاستخدام على PythonAnywhere (تشغيل مرة واحدة فقط)
"""

from app import app
from extensions import db
from models import Check, Payment, PaymentSplit, Expense, PaymentMethod, User
from datetime import datetime, date
from sqlalchemy import text

def get_first_user_id():
    """جلب ID أول مستخدم"""
    result = db.session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
    return result if result else 1


def migrate_payments():
    """إنشاء Checks من Payments الموجودة"""
    print("\n📋 جاري معالجة Payments...")
    
    payments = Payment.query.filter(
        Payment.method == PaymentMethod.CHEQUE,
        Payment.check_number.isnot(None),
        Payment.check_number != ''
    ).all()
    
    print(f"   🔍 وجدنا {len(payments)} دفعة بشيك")
    
    created = 0
    skipped = 0
    
    for payment in payments:
        # التحقق من عدم وجود شيك مسبقاً
        existing = Check.query.filter_by(
            reference_number=f"PMT-{payment.id}"
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # التحقق من وجود معلومات الشيك
        if not payment.check_bank or not payment.check_bank.strip():
            skipped += 1
            continue
        
        # تحويل check_due_date
        check_due_date = payment.check_due_date
        if check_due_date and isinstance(check_due_date, date) and not isinstance(check_due_date, datetime):
            check_due_date = datetime.combine(check_due_date, datetime.min.time())
        elif not check_due_date:
            check_due_date = payment.payment_date or datetime.utcnow()
        
        # التحقق من created_by
        created_by_id = payment.created_by
        if not created_by_id or created_by_id == 0:
            created_by_id = get_first_user_id()
        
        # إنشاء الشيك
        try:
            check = Check(
                check_number=payment.check_number.strip(),
                check_bank=payment.check_bank.strip(),
                check_date=payment.payment_date or datetime.utcnow(),
                check_due_date=check_due_date,
                amount=payment.total_amount,
                currency=payment.currency or 'ILS',
                direction=payment.direction,
                status='PENDING',
                customer_id=payment.customer_id,
                supplier_id=payment.supplier_id,
                partner_id=payment.partner_id,
                reference_number=f"PMT-{payment.id}",
                notes=f"شيك من دفعة رقم {payment.payment_number or payment.id}",
                created_by_id=created_by_id
            )
            db.session.add(check)
            created += 1
        except Exception as e:
            print(f"   ⚠️ فشل إنشاء شيك من Payment #{payment.id}: {e}")
            continue
    
    try:
        db.session.commit()
        print(f"   ✅ Payments: تم إنشاء {created} شيك، تخطي {skipped}")
    except Exception as e:
        db.session.rollback()
        print(f"   ❌ خطأ في حفظ Payments: {e}")
        return 0
    
    return created


def migrate_payment_splits():
    """إنشاء Checks من PaymentSplits الموجودة"""
    print("\n📋 جاري معالجة PaymentSplits...")
    
    splits = PaymentSplit.query.filter(
        PaymentSplit.method == PaymentMethod.CHEQUE
    ).all()
    
    print(f"   🔍 وجدنا {len(splits)} دفعة جزئية بشيك")
    
    created = 0
    skipped = 0
    
    for split in splits:
        # التحقق من عدم وجود شيك مسبقاً
        existing = Check.query.filter_by(
            reference_number=f"PMT-SPLIT-{split.id}"
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # جلب معلومات الشيك من details
        details = split.details or {}
        if not isinstance(details, dict):
            try:
                import json
                details = json.loads(details) if isinstance(details, str) else {}
            except:
                details = {}
        
        check_number = (details.get('check_number', '') or '').strip()
        check_bank = (details.get('check_bank', '') or '').strip()
        
        if not check_number or not check_bank:
            skipped += 1
            continue
        
        # جلب معلومات الدفعة الأصلية
        payment = split.payment
        if not payment:
            skipped += 1
            continue
        
        # تحويل check_due_date
        check_due_date_raw = details.get('check_due_date')
        check_due_date = None
        
        if check_due_date_raw:
            try:
                if isinstance(check_due_date_raw, str):
                    check_due_date = datetime.fromisoformat(check_due_date_raw.replace('Z', '+00:00'))
                elif isinstance(check_due_date_raw, datetime):
                    check_due_date = check_due_date_raw
                elif isinstance(check_due_date_raw, date):
                    check_due_date = datetime.combine(check_due_date_raw, datetime.min.time())
            except:
                pass
        
        if not check_due_date:
            check_due_date = payment.payment_date or datetime.utcnow()
        
        # التحقق من created_by
        created_by_id = payment.created_by
        if not created_by_id or created_by_id == 0:
            created_by_id = get_first_user_id()
        
        # إنشاء الشيك
        try:
            check = Check(
                check_number=check_number,
                check_bank=check_bank,
                check_date=payment.payment_date or datetime.utcnow(),
                check_due_date=check_due_date,
                amount=split.amount,
                currency=payment.currency or 'ILS',
                direction=payment.direction,
                status='PENDING',
                customer_id=payment.customer_id,
                supplier_id=payment.supplier_id,
                partner_id=payment.partner_id,
                reference_number=f"PMT-SPLIT-{split.id}",
                notes=f"شيك من دفعة جزئية #{split.id} - دفعة رقم {payment.payment_number}",
                created_by_id=created_by_id
            )
            db.session.add(check)
            created += 1
        except Exception as e:
            print(f"   ⚠️ فشل إنشاء شيك من Split #{split.id}: {e}")
            continue
    
    try:
        db.session.commit()
        print(f"   ✅ PaymentSplits: تم إنشاء {created} شيك، تخطي {skipped}")
    except Exception as e:
        db.session.rollback()
        print(f"   ❌ خطأ في حفظ PaymentSplits: {e}")
        return 0
    
    return created


def migrate_expenses():
    """إنشاء Checks من Expenses الموجودة"""
    print("\n📋 جاري معالجة Expenses...")
    
    expenses = Expense.query.filter(
        Expense.payment_method == 'cheque',
        Expense.check_number.isnot(None),
        Expense.check_number != ''
    ).all()
    
    print(f"   🔍 وجدنا {len(expenses)} مصروف بشيك")
    
    created = 0
    skipped = 0
    
    for expense in expenses:
        # التحقق من عدم وجود شيك مسبقاً
        existing = Check.query.filter_by(
            reference_number=f"EXP-{expense.id}"
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # التحقق من وجود معلومات الشيك
        if not expense.check_bank or not expense.check_bank.strip():
            skipped += 1
            continue
        
        # تحويل check_due_date
        check_due_date = expense.check_due_date
        if check_due_date and isinstance(check_due_date, date) and not isinstance(check_due_date, datetime):
            check_due_date = datetime.combine(check_due_date, datetime.min.time())
        elif not check_due_date:
            check_due_date = expense.date or datetime.utcnow()
        
        # إنشاء الشيك
        try:
            check = Check(
                check_number=expense.check_number.strip(),
                check_bank=expense.check_bank.strip(),
                check_date=expense.date or datetime.utcnow(),
                check_due_date=check_due_date,
                amount=expense.amount,
                currency=expense.currency or 'ILS',
                direction='OUT',
                status='PENDING',
                supplier_id=getattr(expense, 'supplier_id', None),
                partner_id=getattr(expense, 'partner_id', None),
                reference_number=f"EXP-{expense.id}",
                notes=f"شيك من مصروف رقم {expense.id}",
                created_by_id=get_first_user_id()
            )
            db.session.add(check)
            created += 1
        except Exception as e:
            print(f"   ⚠️ فشل إنشاء شيك من Expense #{expense.id}: {e}")
            continue
    
    try:
        db.session.commit()
        print(f"   ✅ Expenses: تم إنشاء {created} شيك، تخطي {skipped}")
    except Exception as e:
        db.session.rollback()
        print(f"   ❌ خطأ في حفظ Expenses: {e}")
        return 0
    
    return created


if __name__ == '__main__':
    with app.app_context():
        print("\n" + "="*70)
        print("🔄 Data Migration: إنشاء Checks من السجلات الموجودة (PythonAnywhere)")
        print("="*70)
        
        # عرض الإحصائيات قبل
        print("\n📊 الإحصائيات قبل Migration:")
        print(f"   - جدول Checks: {Check.query.count()}")
        print(f"   - Payments (شيك): {Payment.query.filter(Payment.method==PaymentMethod.CHEQUE).count()}")
        print(f"   - PaymentSplits (شيك): {PaymentSplit.query.filter(PaymentSplit.method==PaymentMethod.CHEQUE).count()}")
        print(f"   - Expenses (شيك): {Expense.query.filter(Expense.payment_method=='cheque').count()}")
        
        total_created = 0
        
        total_created += migrate_payments()
        total_created += migrate_payment_splits()
        total_created += migrate_expenses()
        
        print("\n" + "="*70)
        print(f"✅ Migration مكتملة: تم إنشاء {total_created} شيك إجمالاً")
        print("="*70)
        
        # إحصائيات بعد
        print("\n📊 الإحصائيات بعد Migration:")
        print(f"   - جدول Checks: {Check.query.count()}")
        print(f"   - Payments (شيك): {Payment.query.filter(Payment.method==PaymentMethod.CHEQUE).count()}")
        print(f"   - PaymentSplits (شيك): {PaymentSplit.query.filter(PaymentSplit.method==PaymentMethod.CHEQUE).count()}")
        print(f"   - Expenses (شيك): {Expense.query.filter(Expense.payment_method=='cheque').count()}")
        
        # عرض بعض الأمثلة
        checks = Check.query.order_by(Check.id.desc()).limit(5).all()
        if checks:
            print("\n📋 آخر 5 شيكات:")
            for c in checks:
                print(f"   - #{c.id}: {c.check_number} - {c.check_bank} - {c.amount} {c.currency} ({c.direction})")
        
        print("\n" + "="*70)
        print("✅ يمكنك الآن حذف هذا السكريبت: rm migrate_checks_pythonanywhere.py")
        print("="*70 + "\n")

