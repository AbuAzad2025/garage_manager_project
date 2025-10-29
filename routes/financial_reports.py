"""
🏦 وحدة التقارير المالية الأساسية - Financial Reports Module
===============================================================

📋 الوصف:
    تقارير مالية احترافية: قائمة الدخل، الميزانية العمومية، التدفق النقدي
    
🎯 التقارير:
    ✅ قائمة الدخل (P&L Statement)
    ✅ الميزانية العمومية (Balance Sheet)  
    ✅ قائمة التدفق النقدي (Cash Flow Statement)
    ✅ تقرير الأرصدة المجمعة
    
🔒 الأمان:
    - Owner only (@owner_only)
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
import json

from models import (
    db, Account, GLBatch, GLEntry, Customer, Supplier, Partner,
    Sale, Payment, Expense, Invoice, ServiceRequest
)
from routes.security import owner_only

# إنشاء Blueprint
financial_reports_bp = Blueprint('financial_reports', __name__, url_prefix='/reports/financial')

@financial_reports_bp.route('/')
@owner_only
def index():
    """لوحة التقارير المالية الرئيسية"""
    return render_template('reports/financial/index.html')

@financial_reports_bp.route('/income-statement')
@owner_only
def income_statement():
    """قائمة الدخل (P&L Statement)"""
    try:
        # معاملات التاريخ
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            # افتراضي: الشهر الحالي
            today = date.today()
            start_date = today.replace(day=1)
            end_date = today
        
        # تحويل التواريخ
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date).date()
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date).date()
        
        # حساب الإيرادات من GL
        revenue_query = db.session.query(
            func.sum(GLEntry.credit).label('total_revenue')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('4%')  # حسابات الإيرادات
        ).scalar() or 0
        
        # حساب تكلفة البضاعة المباعة
        cogs_query = db.session.query(
            func.sum(GLEntry.debit).label('total_cogs')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('51%')  # حسابات COGS
        ).scalar() or 0
        
        # حساب المصروفات التشغيلية
        expenses_query = db.session.query(
            func.sum(GLEntry.debit).label('total_expenses')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('5%')  # حسابات المصروفات
        ).scalar() or 0
        
        # حساب الضرائب
        taxes_query = db.session.query(
            func.sum(GLEntry.debit).label('total_taxes')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('21%')  # حسابات الضرائب
        ).scalar() or 0
        
        # الحسابات
        total_revenue = float(revenue_query)
        total_cogs = float(cogs_query)
        gross_profit = total_revenue - total_cogs
        operating_expenses = float(expenses_query)
        operating_profit = gross_profit - operating_expenses
        total_taxes = float(taxes_query)
        net_profit = operating_profit - total_taxes
        
        # تفاصيل الإيرادات
        revenue_details = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.credit).label('amount')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('4%')
        ).group_by(GLEntry.account).all()
        
        # تفاصيل المصروفات
        expense_details = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.debit).label('amount')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('5%')
        ).group_by(GLEntry.account).all()
        
        return jsonify({
            'success': True,
            'report_type': 'income_statement',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_revenue': total_revenue,
                'total_cogs': total_cogs,
                'gross_profit': gross_profit,
                'operating_expenses': operating_expenses,
                'operating_profit': operating_profit,
                'total_taxes': total_taxes,
                'net_profit': net_profit
            },
            'details': {
                'revenue': [{'account': r.account, 'amount': float(r.amount)} for r in revenue_details],
                'expenses': [{'account': e.account, 'amount': float(e.amount)} for e in expense_details]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في قائمة الدخل: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@financial_reports_bp.route('/balance-sheet')
@owner_only
def balance_sheet():
    """الميزانية العمومية (Balance Sheet)"""
    try:
        # تاريخ الميزانية
        balance_date = request.args.get('date')
        if not balance_date:
            balance_date = date.today()
        else:
            balance_date = datetime.fromisoformat(balance_date).date()
        
        # الأصول المتداولة
        current_assets = db.session.query(
            func.sum(GLEntry.debit - GLEntry.credit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('1%')  # الأصول المتداولة
        ).scalar() or 0
        
        # الأصول الثابتة
        fixed_assets = db.session.query(
            func.sum(GLEntry.debit - GLEntry.credit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('15%')  # الأصول الثابتة
        ).scalar() or 0
        
        # الخصوم المتداولة
        current_liabilities = db.session.query(
            func.sum(GLEntry.credit - GLEntry.debit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('2%')  # الخصوم المتداولة
        ).scalar() or 0
        
        # حقوق الملكية
        equity = db.session.query(
            func.sum(GLEntry.credit - GLEntry.debit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('3%')  # حقوق الملكية
        ).scalar() or 0
        
        # تفاصيل الأصول
        assets_details = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.debit - GLEntry.credit).label('balance')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('1%')
        ).group_by(GLEntry.account).all()
        
        # تفاصيل الخصوم وحقوق الملكية
        liabilities_equity_details = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.credit - GLEntry.debit).label('balance')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            or_(GLEntry.account.like('2%'), GLEntry.account.like('3%'))
        ).group_by(GLEntry.account).all()
        
        total_assets = float(current_assets) + float(fixed_assets)
        total_liabilities_equity = float(current_liabilities) + float(equity)
        
        return jsonify({
            'success': True,
            'report_type': 'balance_sheet',
            'balance_date': balance_date.isoformat(),
            'summary': {
                'current_assets': float(current_assets),
                'fixed_assets': float(fixed_assets),
                'total_assets': total_assets,
                'current_liabilities': float(current_liabilities),
                'equity': float(equity),
                'total_liabilities_equity': total_liabilities_equity,
                'is_balanced': abs(total_assets - total_liabilities_equity) < 0.01
            },
            'details': {
                'assets': [{'account': a.account, 'balance': float(a.balance)} for a in assets_details],
                'liabilities_equity': [{'account': l.account, 'balance': float(l.balance)} for l in liabilities_equity_details]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في الميزانية العمومية: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@financial_reports_bp.route('/cash-flow')
@owner_only
def cash_flow():
    """قائمة التدفق النقدي (Cash Flow Statement)"""
    try:
        # معاملات التاريخ
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            # افتراضي: الشهر الحالي
            today = date.today()
            start_date = today.replace(day=1)
            end_date = today
        
        # تحويل التواريخ
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date).date()
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date).date()
        
        # التدفق النقدي من العمليات
        operating_cash_in = db.session.query(
            func.sum(GLEntry.debit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),  # النقدية
                GLEntry.account.like('1010%'),  # البنك
                GLEntry.account.like('1020%')   # البطاقات
            ),
            GLBatch.source_type.in_(['PAYMENT', 'SALE'])
        ).scalar() or 0
        
        operating_cash_out = db.session.query(
            func.sum(GLEntry.credit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),  # النقدية
                GLEntry.account.like('1010%'),  # البنك
                GLEntry.account.like('1020%')   # البطاقات
            ),
            GLBatch.source_type.in_(['EXPENSE', 'PAYMENT'])
        ).scalar() or 0
        
        # التدفق النقدي من الاستثمارات
        investing_cash_in = db.session.query(
            func.sum(GLEntry.debit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),
                GLEntry.account.like('1010%'),
                GLEntry.account.like('1020%')
            ),
            GLBatch.source_type.in_(['ASSET_SALE', 'INVESTMENT'])
        ).scalar() or 0
        
        investing_cash_out = db.session.query(
            func.sum(GLEntry.credit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),
                GLEntry.account.like('1010%'),
                GLEntry.account.like('1020%')
            ),
            GLBatch.source_type.in_(['ASSET_PURCHASE', 'INVESTMENT'])
        ).scalar() or 0
        
        # التدفق النقدي من التمويل
        financing_cash_in = db.session.query(
            func.sum(GLEntry.debit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),
                GLEntry.account.like('1010%'),
                GLEntry.account.like('1020%')
            ),
            GLBatch.source_type.in_(['LOAN', 'CAPITAL'])
        ).scalar() or 0
        
        financing_cash_out = db.session.query(
            func.sum(GLEntry.credit).label('total')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            or_(
                GLEntry.account.like('1000%'),
                GLEntry.account.like('1010%'),
                GLEntry.account.like('1020%')
            ),
            GLBatch.source_type.in_(['LOAN_PAYMENT', 'DIVIDEND'])
        ).scalar() or 0
        
        # الحسابات
        net_operating_cash = float(operating_cash_in) - float(operating_cash_out)
        net_investing_cash = float(investing_cash_in) - float(investing_cash_out)
        net_financing_cash = float(financing_cash_in) - float(financing_cash_out)
        net_cash_flow = net_operating_cash + net_investing_cash + net_financing_cash
        
        return jsonify({
            'success': True,
            'report_type': 'cash_flow',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'operating_cash_in': float(operating_cash_in),
                'operating_cash_out': float(operating_cash_out),
                'net_operating_cash': net_operating_cash,
                'investing_cash_in': float(investing_cash_in),
                'investing_cash_out': float(investing_cash_out),
                'net_investing_cash': net_investing_cash,
                'financing_cash_in': float(financing_cash_in),
                'financing_cash_out': float(financing_cash_out),
                'net_financing_cash': net_financing_cash,
                'net_cash_flow': net_cash_flow
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في التدفق النقدي: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@financial_reports_bp.route('/balances-summary')
@owner_only
def balances_summary():
    """تقرير الأرصدة المجمعة"""
    try:
        # أرصدة العملاء
        customers = Customer.query.all()
        customer_balances = []
        total_customer_balance = 0
        
        for customer in customers:
            balance = customer.balance  # استخدام المنطق الموجود
            customer_balances.append({
                'id': customer.id,
                'name': customer.name,
                'balance': float(balance),
                'currency': customer.currency
            })
            total_customer_balance += float(balance)
        
        # أرصدة الموردين
        suppliers = Supplier.query.all()
        supplier_balances = []
        total_supplier_balance = 0
        
        for supplier in suppliers:
            balance = supplier.balance  # استخدام المنطق الموجود
            supplier_balances.append({
                'id': supplier.id,
                'name': supplier.name,
                'balance': float(balance),
                'currency': supplier.currency
            })
            total_supplier_balance += float(balance)
        
        # أرصدة الشركاء
        partners = Partner.query.all()
        partner_balances = []
        total_partner_balance = 0
        
        for partner in partners:
            balance = partner.balance  # استخدام المنطق الموجود
            partner_balances.append({
                'id': partner.id,
                'name': partner.name,
                'balance': float(balance),
                'currency': partner.currency
            })
            total_partner_balance += float(balance)
        
        return jsonify({
            'success': True,
            'report_type': 'balances_summary',
            'summary': {
                'total_customer_balance': total_customer_balance,
                'total_supplier_balance': total_supplier_balance,
                'total_partner_balance': total_partner_balance,
                'net_position': total_customer_balance - total_supplier_balance - total_partner_balance
            },
            'details': {
                'customers': customer_balances,
                'suppliers': supplier_balances,
                'partners': partner_balances
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في تقرير الأرصدة: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@financial_reports_bp.route('/validation')
@owner_only
def validation_report():
    """تقرير التحقق من صحة النظام المحاسبي"""
    try:
        validation_results = []
        
        # فحص توازن القيود
        unbalanced_batches = db.session.query(GLBatch).filter(
            GLBatch.status == 'POSTED'
        ).all()
        
        unbalanced_count = 0
        for batch in unbalanced_batches:
            total_debit = sum(entry.debit for entry in batch.entries)
            total_credit = sum(entry.credit for entry in batch.entries)
            if abs(total_debit - total_credit) > 0.01:
                unbalanced_count += 1
        
        validation_results.append({
            'check': 'توازن القيود المحاسبية',
            'status': 'PASS' if unbalanced_count == 0 else 'FAIL',
            'details': f'عدد القيود غير المتوازنة: {unbalanced_count}',
            'count': unbalanced_count
        })
        
        # فحص الحسابات النشطة
        inactive_accounts = Account.query.filter_by(is_active=False).count()
        validation_results.append({
            'check': 'الحسابات النشطة',
            'status': 'PASS' if inactive_accounts == 0 else 'WARNING',
            'details': f'عدد الحسابات غير النشطة: {inactive_accounts}',
            'count': inactive_accounts
        })
        
        # فحص المدفوعات المعلقة
        pending_payments = Payment.query.filter_by(status='PENDING').count()
        validation_results.append({
            'check': 'المدفوعات المعلقة',
            'status': 'INFO',
            'details': f'عدد المدفوعات المعلقة: {pending_payments}',
            'count': pending_payments
        })
        
        # فحص الشيكات المعلقة
        from models import Check
        pending_checks = Check.query.filter_by(status='PENDING').count()
        validation_results.append({
            'check': 'الشيكات المعلقة',
            'status': 'INFO',
            'details': f'عدد الشيكات المعلقة: {pending_checks}',
            'count': pending_checks
        })
        
        return jsonify({
            'success': True,
            'report_type': 'validation',
            'validation_results': validation_results,
            'overall_status': 'HEALTHY' if all(r['status'] in ['PASS', 'INFO'] for r in validation_results) else 'NEEDS_ATTENTION'
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في تقرير التحقق: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
