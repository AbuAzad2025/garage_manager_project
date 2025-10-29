"""
🔍 وحدة التحقق والمراجعة المحاسبية - Accounting Validation Module
================================================================

📋 الوصف:
    أدوات التحقق من صحة النظام المحاسبي وفحص التوازن
    
🎯 الوظائف:
    ✅ فحص توازن القيود المحاسبية
    ✅ التحقق من صحة الأرصدة
    ✅ فحص الاتساق بين الجداول
    ✅ تقارير المراجعة الدورية
    
🔒 الأمان:
    - Owner only (@owner_only)
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_, text
import json

from models import (
    db, Account, GLBatch, GLEntry, Customer, Supplier, Partner,
    Sale, Payment, Expense, Invoice, ServiceRequest, Check
)
from routes.security import owner_only

# إنشاء Blueprint
accounting_validation_bp = Blueprint('accounting_validation', __name__, url_prefix='/validation/accounting')

@accounting_validation_bp.route('/')
@owner_only
def index():
    """لوحة التحقق المحاسبي الرئيسية"""
    return render_template('validation/accounting/index.html')

@accounting_validation_bp.route('/balance-check')
@owner_only
def balance_check():
    """فحص توازن القيود المحاسبية"""
    try:
        # فحص جميع القيود المؤكدة
        batches = db.session.query(GLBatch).filter(
            GLBatch.status == 'POSTED'
        ).all()
        
        unbalanced_batches = []
        total_batches = len(batches)
        
        for batch in batches:
            total_debit = sum(float(entry.debit) for entry in batch.entries)
            total_credit = sum(float(entry.credit) for entry in batch.entries)
            difference = abs(total_debit - total_credit)
            
            if difference > 0.01:  # تسامح 1 قرش
                unbalanced_batches.append({
                    'batch_id': batch.id,
                    'batch_code': batch.code,
                    'source_type': batch.source_type,
                    'source_id': batch.source_id,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'difference': difference,
                    'posted_at': batch.posted_at.isoformat() if batch.posted_at else None
                })
        
        return jsonify({
            'success': True,
            'check_type': 'balance_check',
            'summary': {
                'total_batches': total_batches,
                'unbalanced_batches': len(unbalanced_batches),
                'balance_status': 'BALANCED' if len(unbalanced_batches) == 0 else 'UNBALANCED'
            },
            'unbalanced_batches': unbalanced_batches
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في فحص التوازن: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@accounting_validation_bp.route('/account-consistency')
@owner_only
def account_consistency():
    """فحص اتساق الحسابات"""
    try:
        # فحص الحسابات المستخدمة في GL
        used_accounts = db.session.query(GLEntry.account).distinct().all()
        used_account_codes = [acc.account for acc in used_accounts]
        
        # فحص الحسابات الموجودة في جدول accounts
        existing_accounts = db.session.query(Account.code).all()
        existing_account_codes = [acc.code for acc in existing_accounts]
        
        # حسابات مستخدمة لكن غير موجودة
        missing_accounts = set(used_account_codes) - set(existing_account_codes)
        
        # حسابات موجودة لكن غير مستخدمة
        unused_accounts = set(existing_account_codes) - set(used_account_codes)
        
        # حسابات غير نشطة لكن مستخدمة
        inactive_used_accounts = db.session.query(Account.code).filter(
            Account.code.in_(used_account_codes),
            Account.is_active == False
        ).all()
        inactive_used_codes = [acc.code for acc in inactive_used_accounts]
        
        return jsonify({
            'success': True,
            'check_type': 'account_consistency',
            'summary': {
                'total_used_accounts': len(used_account_codes),
                'total_existing_accounts': len(existing_account_codes),
                'missing_accounts_count': len(missing_accounts),
                'unused_accounts_count': len(unused_accounts),
                'inactive_used_count': len(inactive_used_codes)
            },
            'issues': {
                'missing_accounts': list(missing_accounts),
                'unused_accounts': list(unused_accounts),
                'inactive_used_accounts': inactive_used_codes
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في فحص اتساق الحسابات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@accounting_validation_bp.route('/entity-balance-verification')
@owner_only
def entity_balance_verification():
    """التحقق من صحة أرصدة الكيانات"""
    try:
        verification_results = []
        
        # فحص أرصدة العملاء
        customers = Customer.query.limit(10).all()  # عينة من العملاء
        for customer in customers:
            try:
                # حساب الرصيد من GL
                gl_debit = db.session.query(func.sum(GLEntry.debit)).join(GLBatch).filter(
                    GLBatch.status == 'POSTED',
                    GLEntry.account == '1100_AR',
                    GLBatch.entity_type == 'CUSTOMER',
                    GLBatch.entity_id == customer.id
                ).scalar() or 0
                
                gl_credit = db.session.query(func.sum(GLEntry.credit)).join(GLBatch).filter(
                    GLBatch.status == 'POSTED',
                    GLEntry.account == '1100_AR',
                    GLBatch.entity_type == 'CUSTOMER',
                    GLBatch.entity_id == customer.id
                ).scalar() or 0
                
                gl_balance = float(gl_debit) - float(gl_credit)
                model_balance = float(customer.balance)
                difference = abs(gl_balance - model_balance)
                
                verification_results.append({
                    'entity_type': 'CUSTOMER',
                    'entity_id': customer.id,
                    'entity_name': customer.name,
                    'gl_balance': gl_balance,
                    'model_balance': model_balance,
                    'difference': difference,
                    'status': 'CONSISTENT' if difference < 0.01 else 'INCONSISTENT'
                })
            except Exception as e:
                verification_results.append({
                    'entity_type': 'CUSTOMER',
                    'entity_id': customer.id,
                    'entity_name': customer.name,
                    'error': str(e),
                    'status': 'ERROR'
                })
        
        return jsonify({
            'success': True,
            'check_type': 'entity_balance_verification',
            'verification_results': verification_results,
            'summary': {
                'total_checked': len(verification_results),
                'consistent': len([r for r in verification_results if r.get('status') == 'CONSISTENT']),
                'inconsistent': len([r for r in verification_results if r.get('status') == 'INCONSISTENT']),
                'errors': len([r for r in verification_results if r.get('status') == 'ERROR'])
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في التحقق من أرصدة الكيانات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@accounting_validation_bp.route('/transaction-integrity')
@owner_only
def transaction_integrity():
    """فحص تكامل المعاملات"""
    try:
        integrity_results = []
        
        # فحص المبيعات المؤكدة بدون GL
        sales_without_gl = db.session.query(Sale).filter(
            Sale.status == 'CONFIRMED'
        ).all()
        
        sales_missing_gl = []
        for sale in sales_without_gl:
            gl_batch = db.session.query(GLBatch).filter(
                GLBatch.source_type == 'SALE',
                GLBatch.source_id == sale.id,
                GLBatch.status == 'POSTED'
            ).first()
            
            if not gl_batch:
                sales_missing_gl.append({
                    'sale_id': sale.id,
                    'sale_number': sale.sale_number,
                    'total_amount': float(sale.total_amount),
                    'sale_date': sale.sale_date.isoformat() if sale.sale_date else None
                })
        
        # فحص المدفوعات المكتملة بدون GL
        payments_without_gl = db.session.query(Payment).filter(
            Payment.status == 'COMPLETED'
        ).all()
        
        payments_missing_gl = []
        for payment in payments_without_gl:
            gl_batch = db.session.query(GLBatch).filter(
                GLBatch.source_type == 'PAYMENT',
                GLBatch.source_id == payment.id,
                GLBatch.status == 'POSTED'
            ).first()
            
            if not gl_batch:
                payments_missing_gl.append({
                    'payment_id': payment.id,
                    'payment_number': payment.payment_number,
                    'total_amount': float(payment.total_amount),
                    'payment_date': payment.payment_date.isoformat() if payment.payment_date else None
                })
        
        integrity_results.append({
            'check': 'المبيعات المؤكدة بدون GL',
            'count': len(sales_missing_gl),
            'status': 'PASS' if len(sales_missing_gl) == 0 else 'FAIL',
            'details': sales_missing_gl
        })
        
        integrity_results.append({
            'check': 'المدفوعات المكتملة بدون GL',
            'count': len(payments_missing_gl),
            'status': 'PASS' if len(payments_missing_gl) == 0 else 'FAIL',
            'details': payments_missing_gl
        })
        
        return jsonify({
            'success': True,
            'check_type': 'transaction_integrity',
            'integrity_results': integrity_results,
            'overall_status': 'HEALTHY' if all(r['status'] == 'PASS' for r in integrity_results) else 'NEEDS_ATTENTION'
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في فحص تكامل المعاملات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@accounting_validation_bp.route('/periodic-audit')
@owner_only
def periodic_audit():
    """مراجعة دورية شاملة"""
    try:
        audit_date = request.args.get('date')
        if not audit_date:
            audit_date = date.today()
        else:
            audit_date = datetime.fromisoformat(audit_date).date()
        
        audit_results = []
        
        # إحصائيات عامة
        total_accounts = Account.query.count()
        active_accounts = Account.query.filter_by(is_active=True).count()
        total_gl_batches = GLBatch.query.count()
        posted_batches = GLBatch.query.filter_by(status='POSTED').count()
        total_gl_entries = GLEntry.query.count()
        
        # إحصائيات المعاملات
        total_sales = Sale.query.filter(Sale.created_at <= audit_date).count()
        confirmed_sales = Sale.query.filter(
            Sale.status == 'CONFIRMED',
            Sale.created_at <= audit_date
        ).count()
        
        total_payments = Payment.query.filter(Payment.created_at <= audit_date).count()
        completed_payments = Payment.query.filter(
            Payment.status == 'COMPLETED',
            Payment.created_at <= audit_date
        ).count()
        
        # إحصائيات الأرصدة
        customers_count = Customer.query.count()
        suppliers_count = Supplier.query.count()
        partners_count = Partner.query.count()
        
        audit_results.append({
            'category': 'الحسابات المحاسبية',
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'inactive_accounts': total_accounts - active_accounts
        })
        
        audit_results.append({
            'category': 'القيود المحاسبية',
            'total_batches': total_gl_batches,
            'posted_batches': posted_batches,
            'draft_batches': total_gl_batches - posted_batches,
            'total_entries': total_gl_entries
        })
        
        audit_results.append({
            'category': 'المعاملات',
            'total_sales': total_sales,
            'confirmed_sales': confirmed_sales,
            'total_payments': total_payments,
            'completed_payments': completed_payments
        })
        
        audit_results.append({
            'category': 'الكيانات',
            'customers': customers_count,
            'suppliers': suppliers_count,
            'partners': partners_count
        })
        
        return jsonify({
            'success': True,
            'check_type': 'periodic_audit',
            'audit_date': audit_date.isoformat(),
            'audit_results': audit_results,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في المراجعة الدورية: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@accounting_validation_bp.route('/fix-unbalanced-batches')
@owner_only
def fix_unbalanced_batches():
    """إصلاح القيود غير المتوازنة"""
    try:
        # العثور على القيود غير المتوازنة
        batches = db.session.query(GLBatch).filter(
            GLBatch.status == 'POSTED'
        ).all()
        
        fixed_batches = []
        unfixable_batches = []
        
        for batch in batches:
            total_debit = sum(float(entry.debit) for entry in batch.entries)
            total_credit = sum(float(entry.credit) for entry in batch.entries)
            difference = total_debit - total_credit
            
            if abs(difference) > 0.01:
                # محاولة الإصلاح التلقائي
                if len(batch.entries) >= 2:
                    # إضافة قيد تصحيح
                    correction_account = '9999_CORRECTION'
                    
                    # التحقق من وجود حساب التصحيح
                    correction_acc = Account.query.filter_by(code=correction_account).first()
                    if not correction_acc:
                        correction_acc = Account(
                            code=correction_account,
                            name='حساب التصحيح',
                            type='EXPENSE',
                            is_active=True
                        )
                        db.session.add(correction_acc)
                    
                    if difference > 0:
                        # المدين أكبر من الدائن - إضافة دائن
                        correction_entry = GLEntry(
                            batch_id=batch.id,
                            account=correction_account,
                            debit=0,
                            credit=abs(difference),
                            currency='ILS',
                            ref=f'تصحيح توازن {batch.code}'
                        )
                    else:
                        # الدائن أكبر من المدين - إضافة مدين
                        correction_entry = GLEntry(
                            batch_id=batch.id,
                            account=correction_account,
                            debit=abs(difference),
                            credit=0,
                            currency='ILS',
                            ref=f'تصحيح توازن {batch.code}'
                        )
                    
                    db.session.add(correction_entry)
                    fixed_batches.append({
                        'batch_id': batch.id,
                        'batch_code': batch.code,
                        'difference': difference,
                        'correction_amount': abs(difference)
                    })
                else:
                    unfixable_batches.append({
                        'batch_id': batch.id,
                        'batch_code': batch.code,
                        'difference': difference,
                        'reason': 'عدد القيود أقل من 2'
                    })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'action': 'fix_unbalanced_batches',
            'summary': {
                'fixed_batches': len(fixed_batches),
                'unfixable_batches': len(unfixable_batches)
            },
            'fixed_batches': fixed_batches,
            'unfixable_batches': unfixable_batches
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في إصلاح القيود غير المتوازنة: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
