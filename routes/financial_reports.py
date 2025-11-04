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
    """قائمة الدخل (P&L Statement) - يدعم HTML وJSON"""
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
        
        # تفاصيل الإيرادات مع أسماء الحسابات
        revenue_details = db.session.query(
            GLEntry.account,
            Account.name,
            func.sum(GLEntry.credit).label('amount')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('4%')
        ).group_by(GLEntry.account, Account.name).all()
        
        # تفاصيل المصروفات مع أسماء الحسابات
        expense_details = db.session.query(
            GLEntry.account,
            Account.name,
            func.sum(GLEntry.debit).label('amount')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('5%')
        ).group_by(GLEntry.account, Account.name).all()
        
        data = {
            'start_date': start_date,
            'end_date': end_date,
            'from_date': start_date,
            'to_date': end_date,
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'gross_profit': gross_profit,
            'operating_expenses': operating_expenses,
            'operating_profit': operating_profit,
            'total_taxes': total_taxes,
            'net_profit': net_profit,
            'is_profit': net_profit >= 0,
            'revenues': revenue_details,
            'expenses': expense_details,
            'revenue_details': revenue_details,
            'expense_details': expense_details
        }
        
        # إذا طلب JSON
        if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
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
                    'revenue': [{'account': r.account, 'name': r.name, 'amount': float(r.amount)} for r in revenue_details],
                    'expenses': [{'account': e.account, 'name': e.name, 'amount': float(e.amount)} for e in expense_details]
                }
            })
        
        # إرجاع HTML template
        return render_template('reports/financial/income_statement.html', **data)
        
    except Exception as e:
        current_app.logger.error(f"خطأ في قائمة الدخل: {str(e)}")
        if request.args.get('format') == 'json':
            return jsonify({'success': False, 'error': str(e)}), 500
        return render_template('errors/500.html', error=str(e)), 500

@financial_reports_bp.route('/balance-sheet')
@owner_only
def balance_sheet():
    """الميزانية العمومية (Balance Sheet) - يدعم HTML وJSON"""
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
        
        # تفاصيل الأصول مع أسماء
        assets_details = db.session.query(
            GLEntry.account,
            Account.name,
            func.sum(GLEntry.debit - GLEntry.credit).label('balance')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            GLEntry.account.like('1%')
        ).group_by(GLEntry.account, Account.name).having(func.sum(GLEntry.debit - GLEntry.credit) != 0).all()
        
        # تفاصيل الخصوم وحقوق الملكية مع أسماء
        liabilities_equity_details = db.session.query(
            GLEntry.account,
            Account.name,
            func.sum(GLEntry.credit - GLEntry.debit).label('balance')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= balance_date,
            or_(GLEntry.account.like('2%'), GLEntry.account.like('3%'))
        ).group_by(GLEntry.account, Account.name).having(func.sum(GLEntry.credit - GLEntry.debit) != 0).all()
        
        total_assets = float(current_assets) + float(fixed_assets)
        total_liabilities_equity = float(current_liabilities) + float(equity)
        is_balanced = abs(total_assets - total_liabilities_equity) < 0.01
        
        data = {
            'balance_date': balance_date,
            'current_assets': float(current_assets),
            'fixed_assets': float(fixed_assets),
            'total_assets': total_assets,
            'current_liabilities': float(current_liabilities),
            'equity': float(equity),
            'total_liabilities_equity': total_liabilities_equity,
            'is_balanced': is_balanced,
            'assets_details': assets_details,
            'liabilities_equity_details': liabilities_equity_details
        }
        
        # إذا طلب JSON
        if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
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
                    'is_balanced': is_balanced
                },
                'details': {
                    'assets': [{'account': a.account, 'name': a.name, 'balance': float(a.balance)} for a in assets_details],
                    'liabilities_equity': [{'account': l.account, 'name': l.name, 'balance': float(l.balance)} for l in liabilities_equity_details]
                }
            })
        
        # إرجاع HTML template
        return render_template('reports/financial/balance_sheet.html', **data)
        
    except Exception as e:
        current_app.logger.error(f"خطأ في الميزانية العمومية: {str(e)}")
        if request.args.get('format') == 'json':
            return jsonify({'success': False, 'error': str(e)}), 500
        return render_template('errors/500.html', error=str(e)), 500

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
        
        data = {
            'start_date': start_date,
            'end_date': end_date,
            'from_date': start_date,
            'to_date': end_date,
            'operating': {
                'inflows': float(operating_cash_in),
                'outflows': float(operating_cash_out),
                'net': net_operating_cash
            },
            'investing': {
                'inflows': float(investing_cash_in),
                'outflows': float(investing_cash_out),
                'net': net_investing_cash
            },
            'financing': {
                'inflows': float(financing_cash_in),
                'outflows': float(financing_cash_out),
                'net': net_financing_cash
            },
            'total_net_cash_flow': net_cash_flow
        }
        
        if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
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
        
        return render_template('reports/financial/cash_flow.html', **data)
        
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


# ========== تبويبات جديدة ==========

@financial_reports_bp.route('/trial-balance')
@owner_only
def trial_balance():
    """📊 ميزان المراجعة (Trial Balance)"""
    try:
        as_of_date = request.args.get('date')
        if not as_of_date:
            as_of_date = date.today()
        else:
            as_of_date = datetime.fromisoformat(as_of_date).date()
        
        # جلب جميع الحسابات مع أرصدتها
        accounts_balance = db.session.query(
            GLEntry.account,
            Account.name,
            Account.type,
            func.sum(GLEntry.debit).label('total_debit'),
            func.sum(GLEntry.credit).label('total_credit')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= as_of_date
        ).group_by(GLEntry.account, Account.name, Account.type).all()
        
        trial_balance_data = []
        total_debits = 0
        total_credits = 0
        
        # قاموس الأوصاف
        account_descriptions = {
            'ASSET': 'ما تملكه الشركة من موارد',
            'LIABILITY': 'ما على الشركة من التزامات',
            'EQUITY': 'حقوق المالك في الشركة',
            'REVENUE': 'الدخل من العمليات',
            'EXPENSE': 'التكاليف والمصروفات'
        }
        
        for acc in accounts_balance:
            debit = float(acc.total_debit or 0)
            credit = float(acc.total_credit or 0)
            net = debit - credit
            
            trial_balance_data.append({
                'account': acc.account,
                'name': acc.name,
                'type': acc.type,
                'description': account_descriptions.get(acc.type, ''),
                'debit': debit,
                'credit': credit,
                'net': net,
                'side': 'DR' if net > 0 else 'CR'
            })
            
            total_debits += debit
            total_credits += credit
        
        is_balanced = abs(total_debits - total_credits) < 0.01
        
        data = {
            'as_of_date': as_of_date,
            'trial_balance_data': trial_balance_data,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'is_balanced': is_balanced
        }
        
        # إذا طلب JSON
        if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
            return jsonify({
                'success': True,
                'report_type': 'trial_balance',
                'as_of_date': as_of_date.isoformat(),
                'rows': trial_balance_data,
                'totals': {
                    'debit': total_debits,
                    'credit': total_credits,
                    'is_balanced': is_balanced
                }
            })
        
        return render_template('reports/financial/trial_balance.html', **data)
        
    except Exception as e:
        current_app.logger.error(f"خطأ في ميزان المراجعة: {str(e)}")
        if request.args.get('format') == 'json':
            return jsonify({'success': False, 'error': str(e)}), 500
        return render_template('errors/500.html', error=str(e)), 500


@financial_reports_bp.route('/aging-report')
@owner_only
def aging_report():
    """📊 تقرير الذمم المعمرة (AR/AP Aging Report)"""
    try:
        report_type = request.args.get('type', 'ar')  # ar=receivables, ap=payables
        today = date.today()
        
        aging_data = []
        
        if report_type == 'ar':
            # ذمم العملاء
            customers = Customer.query.all()
            for customer in customers:
                balance = float(customer.balance or 0)
                if balance < -0.01:  # عليه دين
                    # حساب عمر أقدم معاملة
                    oldest_sale = Sale.query.filter_by(customer_id=customer.id, status='CONFIRMED').order_by(Sale.sale_date).first()
                    age_days = 0
                    if oldest_sale and oldest_sale.sale_date:
                        sale_date = oldest_sale.sale_date if isinstance(oldest_sale.sale_date, date) else oldest_sale.sale_date.date()
                        age_days = (today - sale_date).days
                    
                    # تصنيف حسب العمر
                    if age_days <= 30:
                        category = '0-30'
                    elif age_days <= 60:
                        category = '31-60'
                    elif age_days <= 90:
                        category = '61-90'
                    else:
                        category = '>90'
                    
                    aging_data.append({
                        'id': customer.id,
                        'name': customer.name,
                        'balance': abs(balance),
                        'age_days': age_days,
                        'category': category,
                        'phone': customer.phone or ''
                    })
        else:
            # ذمم الموردين
            suppliers = Supplier.query.all()
            for supplier in suppliers:
                balance = float(supplier.balance or 0)
                if balance > 0.01:  # له علينا
                    aging_data.append({
                        'id': supplier.id,
                        'name': supplier.name,
                        'balance': balance,
                        'age_days': 0,  # يمكن تحسينه
                        'category': '0-30'
                    })
        
        # تجميع حسب الفئة
        aging_summary = {
            '0-30': sum(item['balance'] for item in aging_data if item['category'] == '0-30'),
            '31-60': sum(item['balance'] for item in aging_data if item['category'] == '31-60'),
            '61-90': sum(item['balance'] for item in aging_data if item['category'] == '61-90'),
            '>90': sum(item['balance'] for item in aging_data if item['category'] == '>90')
        }
        
        return jsonify({
            'success': True,
            'report_type': 'aging_report',
            'aging_type': report_type,
            'as_of_date': today.isoformat(),
            'summary': aging_summary,
            'total': sum(aging_summary.values()),
            'details': aging_data
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في تقرير الذمم المعمرة: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@financial_reports_bp.route('/profit-trends')
@owner_only
def profit_trends():
    """📈 اتجاهات الربحية - مقارنة شهرية"""
    try:
        months = int(request.args.get('months', 6))  # آخر 6 أشهر افتراضياً
        today = date.today()
        
        monthly_data = []
        for i in range(months):
            # حساب بداية ونهاية الشهر
            target_date = today - timedelta(days=30 * i)
            month_start = target_date.replace(day=1)
            if target_date.month == 12:
                month_end = date(target_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
            
            # حساب الإيرادات
            revenue = db.session.query(
                func.sum(GLEntry.credit)
            ).join(GLBatch).filter(
                GLBatch.status == 'POSTED',
                GLBatch.posted_at >= month_start,
                GLBatch.posted_at <= month_end,
                GLEntry.account.like('4%')
            ).scalar() or 0
            
            # حساب المصروفات
            expenses = db.session.query(
                func.sum(GLEntry.debit)
            ).join(GLBatch).filter(
                GLBatch.status == 'POSTED',
                GLBatch.posted_at >= month_start,
                GLBatch.posted_at <= month_end,
                GLEntry.account.like('5%')
            ).scalar() or 0
            
            profit = float(revenue) - float(expenses)
            
            monthly_data.append({
                'month': month_start.strftime('%Y-%m'),
                'month_name': month_start.strftime('%B %Y'),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': profit,
                'margin': (profit / float(revenue) * 100) if float(revenue) > 0 else 0
            })
        
        return jsonify({
            'success': True,
            'report_type': 'profit_trends',
            'months': months,
            'data': list(reversed(monthly_data))  # من الأقدم للأحدث
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في اتجاهات الربحية: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@financial_reports_bp.route('/expense-breakdown')
@owner_only
def expense_breakdown():
    """📊 تحليل المصروفات حسب النوع"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            today = date.today()
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = datetime.fromisoformat(start_date).date()
            end_date = datetime.fromisoformat(end_date).date()
        
        # تحليل المصروفات حسب الحساب
        expense_breakdown = db.session.query(
            GLEntry.account,
            Account.name,
            func.sum(GLEntry.debit).label('amount')
        ).join(Account, Account.code == GLEntry.account).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('5%')
        ).group_by(GLEntry.account, Account.name).order_by(func.sum(GLEntry.debit).desc()).all()
        
        total_expenses = sum(float(exp.amount) for exp in expense_breakdown)
        
        breakdown_data = [{
            'account': exp.account,
            'name': exp.name,
            'amount': float(exp.amount),
            'percentage': (float(exp.amount) / total_expenses * 100) if total_expenses > 0 else 0
        } for exp in expense_breakdown]
        
        return jsonify({
            'success': True,
            'report_type': 'expense_breakdown',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_expenses': total_expenses,
            'breakdown': breakdown_data
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في تحليل المصروفات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@financial_reports_bp.route('/revenue-by-source')
@owner_only
def revenue_by_source():
    """📊 تحليل مصادر الإيرادات"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            today = date.today()
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = datetime.fromisoformat(start_date).date()
            end_date = datetime.fromisoformat(end_date).date()
        
        # إيرادات المبيعات
        sales_revenue = db.session.query(
            func.sum(GLEntry.credit)
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account == '4000_SALES'
        ).scalar() or 0
        
        # إيرادات الخدمات
        service_revenue = db.session.query(
            func.sum(GLEntry.credit)
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account == '4100_SERVICE_REVENUE'
        ).scalar() or 0
        
        # إيرادات أخرى
        other_revenue = db.session.query(
            func.sum(GLEntry.credit)
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at >= start_date,
            GLBatch.posted_at <= end_date,
            GLEntry.account.like('4%'),
            GLEntry.account.notin_(['4000_SALES', '4100_SERVICE_REVENUE'])
        ).scalar() or 0
        
        total_revenue = float(sales_revenue) + float(service_revenue) + float(other_revenue)
        
        return jsonify({
            'success': True,
            'report_type': 'revenue_by_source',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_revenue': total_revenue,
            'breakdown': {
                'sales': {
                    'amount': float(sales_revenue),
                    'percentage': (float(sales_revenue) / total_revenue * 100) if total_revenue > 0 else 0
                },
                'services': {
                    'amount': float(service_revenue),
                    'percentage': (float(service_revenue) / total_revenue * 100) if total_revenue > 0 else 0
                },
                'other': {
                    'amount': float(other_revenue),
                    'percentage': (float(other_revenue) / total_revenue * 100) if total_revenue > 0 else 0
                }
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في تحليل مصادر الإيرادات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500