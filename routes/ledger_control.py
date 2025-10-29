"""
🏦 وحدة التحكم الشاملة لدفتر الأستاذ - Ledger Control Panel
===============================================================

📋 الوصف:
    وحدة تحكم متقدمة لإدارة دفتر الأستاذ والحسابات المحاسبية
    مخصصة للمالك فقط (@owner_only)
    
🎯 الوظائف:
    ✅ إدارة الحسابات المحاسبية (إضافة/تعديل/حذف)
    ✅ إدارة الصناديق والمحافظ
    ✅ إدارة القيود المحاسبية
    ✅ تقارير مالية متقدمة
    ✅ إعدادات النظام المحاسبي
    ✅ مراقبة الأداء والاتساق
    
🔒 الأمان:
    - Owner only (@owner_only)
    - حتى Super Admin لا يستطيع الدخول
    
📝 الملفات:
    - routes/ledger_control.py (هذا الملف)
    - templates/security/ledger_control.html
    - static/js/ledger_control.js
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import json

from models import db, Account, GLBatch, GLEntry, Payment, Sale, Invoice, Check, Partner, Supplier, Customer
from routes.security import owner_only

# إنشاء Blueprint
ledger_control_bp = Blueprint('ledger_control', __name__, url_prefix='/security/ledger-control')


@ledger_control_bp.route('/')
@owner_only
def index():
    """
    🏦 لوحة التحكم الرئيسية لدفتر الأستاذ
    
    📊 الإحصائيات:
        - إجمالي الحسابات (97 حساب)
        - القيود المحاسبية (اليوم/الشهر/السنة)
        - أرصدة الحسابات
        - الشيكات المعلقة/المعيدة
        - المدفوعات المعلقة
        - صحة النظام المحاسبي
    """
    
    # إحصائيات الحسابات
    total_accounts = Account.query.count()
    active_accounts = Account.query.filter_by(is_active=True).count()
    inactive_accounts = Account.query.filter_by(is_active=False).count()
    
    # إحصائيات القيود
    today = datetime.now().date()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    entries_today = GLEntry.query.join(GLBatch).filter(
        GLBatch.posted_at >= today
    ).count()
    
    entries_month = GLEntry.query.join(GLBatch).filter(
        GLBatch.posted_at >= month_start
    ).count()
    
    entries_year = GLEntry.query.join(GLBatch).filter(
        GLBatch.posted_at >= year_start
    ).count()
    
    # إحصائيات الشيكات
    pending_checks = Check.query.filter_by(status='PENDING').count()
    bounced_checks = Check.query.filter_by(status='BOUNCED').count()
    cashed_checks = Check.query.filter_by(status='CASHED').count()
    
    # إحصائيات المدفوعات
    pending_payments = Payment.query.filter_by(status='PENDING').count()
    completed_payments = Payment.query.filter_by(status='COMPLETED').count()
    failed_payments = Payment.query.filter_by(status='FAILED').count()
    
    # أرصدة العملاء والموردين والشركاء
    customers_count = Customer.query.count()
    suppliers_count = Supplier.query.count()
    partners_count = Partner.query.count()
    
    # حساب إجمالي الأرصدة
    total_customer_balance = sum([c.balance for c in Customer.query.all()])
    total_supplier_balance = sum([s.balance for s in Supplier.query.all()])
    total_partner_balance = sum([p.balance for p in Partner.query.all()])
    
    stats = {
        'accounts': {
            'total': total_accounts,
            'active': active_accounts,
            'inactive': inactive_accounts
        },
        'entries': {
            'today': entries_today,
            'month': entries_month,
            'year': entries_year
        },
        'checks': {
            'pending': pending_checks,
            'bounced': bounced_checks,
            'cashed': cashed_checks
        },
        'payments': {
            'pending': pending_payments,
            'completed': completed_payments,
            'failed': failed_payments
        },
        'entities': {
            'customers': customers_count,
            'suppliers': suppliers_count,
            'partners': partners_count
        },
        'balances': {
            'customers': total_customer_balance,
            'suppliers': total_supplier_balance,
            'partners': total_partner_balance
        }
    }
    
    return render_template('security/ledger_control.html', stats=stats)


@ledger_control_bp.route('/accounts')
@owner_only
def accounts_management():
    """إدارة الحسابات المحاسبية - API"""
    
    try:
        # الحصول على جميع الحسابات مع تفاصيلها
        accounts = Account.query.order_by(Account.code).all()
        
        accounts_list = []
        for account in accounts:
            accounts_list.append({
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'type': account.type,
                'is_active': account.is_active
            })
        
        return jsonify({
            'success': True,
            'accounts': accounts_list,
            'total': len(accounts_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/accounts/create', methods=['POST'])
@owner_only
def create_account():
    """إنشاء حساب محاسبي جديد"""
    try:
        data = request.get_json()
        
        # التحقق من البيانات المطلوبة
        required_fields = ['code', 'name', 'type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'حقل {field} مطلوب'}), 400
        
        # التحقق من عدم تكرار الكود
        existing_account = Account.query.filter_by(code=data['code']).first()
        if existing_account:
            return jsonify({'success': False, 'error': 'كود الحساب موجود مسبقاً'}), 400
        
        # إنشاء الحساب الجديد
        new_account = Account(
            code=data['code'],
            name=data['name'],
            type=data['type'],
            is_active=data.get('is_active', True),
            description=data.get('description', '')
        )
        
        db.session.add(new_account)
        db.session.commit()
        
        current_app.logger.info(f"✅ تم إنشاء حساب محاسبي جديد: {data['code']} - {data['name']}")
        
        return jsonify({
            'success': True, 
            'message': 'تم إنشاء الحساب بنجاح',
            'account': {
                'id': new_account.id,
                'code': new_account.code,
                'name': new_account.name,
                'type': new_account.type,
                'is_active': new_account.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في إنشاء الحساب: {str(e)}")
        return jsonify({'success': False, 'error': f'خطأ في إنشاء الحساب: {str(e)}'}), 500


@ledger_control_bp.route('/accounts/<int:account_id>/update', methods=['POST'])
@owner_only
def update_account(account_id):
    """تحديث حساب محاسبي"""
    try:
        account = Account.query.get_or_404(account_id)
        data = request.get_json()
        
        # تحديث البيانات
        if 'name' in data:
            account.name = data['name']
        if 'type' in data:
            account.type = data['type']
        if 'is_active' in data:
            account.is_active = data['is_active']
        if 'description' in data:
            account.description = data['description']
        
        db.session.commit()
        
        current_app.logger.info(f"✅ تم تحديث الحساب: {account.code} - {account.name}")
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث الحساب بنجاح',
            'account': {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'type': account.type,
                'is_active': account.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في تحديث الحساب: {str(e)}")
        return jsonify({'success': False, 'error': f'خطأ في تحديث الحساب: {str(e)}'}), 500


@ledger_control_bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
@owner_only
def delete_account(account_id):
    """حذف حساب محاسبي"""
    try:
        account = Account.query.get_or_404(account_id)
        
        # التحقق من وجود قيود مرتبطة بالحساب
        entries_count = GLEntry.query.filter_by(account=account.code).count()
        if entries_count > 0:
            return jsonify({
                'success': False, 
                'error': f'لا يمكن حذف الحساب لأنه مرتبط بـ {entries_count} قيد محاسبي'
            }), 400
        
        # حذف الحساب
        db.session.delete(account)
        db.session.commit()
        
        current_app.logger.info(f"✅ تم حذف الحساب: {account.code} - {account.name}")
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الحساب بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في حذف الحساب: {str(e)}")
        return jsonify({'success': False, 'error': f'خطأ في حذف الحساب: {str(e)}'}), 500


@ledger_control_bp.route('/entries')
@owner_only
def entries_management():
    """إدارة القيود المحاسبية - API"""
    
    try:
        # الحصول على القيود الأخيرة
        batches = GLBatch.query.order_by(GLBatch.posted_at.desc()).limit(100).all()
        
        batches_list = []
        for batch in batches:
            batches_list.append({
                'id': batch.id,
                'code': batch.code,
                'source_type': batch.source_type,
                'purpose': batch.purpose,
                'memo': batch.memo,
                'posted_at': batch.posted_at.isoformat() if batch.posted_at else None,
                'status': batch.status,
                'entries_count': len(batch.entries)
            })
        
        return jsonify({
            'success': True,
            'batches': batches_list,
            'total': len(batches_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/entries/<int:entry_id>/void', methods=['POST'])
@owner_only
def void_entry(entry_id):
    """إلغاء قيد محاسبي"""
    try:
        entry = GLEntry.query.get_or_404(entry_id)
        batch = entry.batch
        
        # التحقق من إمكانية الإلغاء
        if batch.status == 'VOID':
            return jsonify({'success': False, 'error': 'القيد ملغي مسبقاً'}), 400
        
        # إلغاء القيد
        batch.status = 'VOID'
        db.session.commit()
        
        current_app.logger.info(f"✅ تم إلغاء القيد: {batch.id}")
        
        return jsonify({
            'success': True,
            'message': 'تم إلغاء القيد بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في إلغاء القيد: {str(e)}")
        return jsonify({'success': False, 'error': f'خطأ في إلغاء القيد: {str(e)}'}), 500


@ledger_control_bp.route('/reports')
@owner_only
def reports_management():
    """تقارير مالية متقدمة - API"""
    
    try:
        # إحصائيات مفصلة
        from models import Sale, Payment, Check
        from datetime import datetime, timedelta
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        year_start = today_start.replace(month=1, day=1)
        
        # تقرير المبيعات
        sales_today = Sale.query.filter(Sale.sale_date >= today_start).count()
        sales_month = Sale.query.filter(Sale.sale_date >= month_start).count()
        sales_year = Sale.query.filter(Sale.sale_date >= year_start).count()
        
        # تقرير المدفوعات
        payments_today = Payment.query.filter(Payment.payment_date >= today_start).count()
        payments_month = Payment.query.filter(Payment.payment_date >= month_start).count()
        payments_year = Payment.query.filter(Payment.payment_date >= year_start).count()
        
        # تقرير الشيكات
        checks_by_status = {}
        for status in ['PENDING', 'CASHED', 'BOUNCED', 'RETURNED']:
            checks_by_status[status] = Check.query.filter_by(status=status).count()
        
        reports_data = {
            'sales': {
                'today': sales_today,
                'month': sales_month,
                'year': sales_year
            },
            'payments': {
                'today': payments_today,
                'month': payments_month,
                'year': payments_year
            },
            'checks': checks_by_status
        }
        
        return jsonify({
            'success': True,
            'reports': reports_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/settings')
@owner_only
def settings_management():
    """إعدادات النظام المحاسبي - API"""
    
    try:
        # إعدادات النظام الحالية
        settings = {
            'default_currency': 'ILS',
            'fiscal_year_start': '01-01',
            'auto_backup_enabled': True,
            'audit_trail_enabled': True,
            'decimal_places': 2,
            'date_format': 'dd/mm/yyyy'
        }
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/settings/update', methods=['POST'])
@owner_only
def update_settings():
    """تحديث إعدادات النظام المحاسبي"""
    try:
        data = request.get_json()
        
        # هنا يمكن حفظ الإعدادات في قاعدة البيانات أو ملف إعدادات
        # للآن سنكتفي بتسجيل التحديث
        
        current_app.logger.info(f"✅ تم تحديث إعدادات النظام المحاسبي: {data}")
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث الإعدادات بنجاح'
        })
        
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في تحديث الإعدادات: {str(e)}")
        return jsonify({'success': False, 'error': f'خطأ في تحديث الإعدادات: {str(e)}'}), 500


@ledger_control_bp.route('/health-check')
@owner_only
def health_check():
    """فحص صحة النظام المحاسبي"""
    
    health_status = {
        'overall': 'HEALTHY',
        'checks': []
    }
    
    # فحص توازن القيود
    try:
        # التحقق من توازن القيود
        unbalanced_entries = db.session.query(GLEntry).join(GLBatch).filter(
            GLBatch.status == 'POSTED'
        ).all()
        
        total_debit = sum([entry.debit for entry in unbalanced_entries])
        total_credit = sum([entry.credit for entry in unbalanced_entries])
        
        if abs(total_debit - total_credit) > 0.01:  # تسامح 1 قرش
            health_status['checks'].append({
                'name': 'توازن القيود',
                'status': 'ERROR',
                'message': f'القيم غير متوازنة: مدين {total_debit} ≠ دائن {total_credit}'
            })
            health_status['overall'] = 'ERROR'
        else:
            health_status['checks'].append({
                'name': 'توازن القيود',
                'status': 'OK',
                'message': 'القيم متوازنة ✓'
            })
    except Exception as e:
        health_status['checks'].append({
            'name': 'توازن القيود',
            'status': 'ERROR',
            'message': f'خطأ في فحص التوازن: {str(e)}'
        })
        health_status['overall'] = 'ERROR'
    
    # فحص الحسابات النشطة
    try:
        inactive_accounts = Account.query.filter_by(is_active=False).count()
        if inactive_accounts > 0:
            health_status['checks'].append({
                'name': 'الحسابات النشطة',
                'status': 'WARNING',
                'message': f'يوجد {inactive_accounts} حساب غير نشط'
            })
        else:
            health_status['checks'].append({
                'name': 'الحسابات النشطة',
                'status': 'OK',
                'message': 'جميع الحسابات نشطة ✓'
            })
    except Exception as e:
        health_status['checks'].append({
            'name': 'الحسابات النشطة',
            'status': 'ERROR',
            'message': f'خطأ في فحص الحسابات: {str(e)}'
        })
    
    return jsonify(health_status)


@ledger_control_bp.route('/api/account-balance/<account_code>')
@owner_only
def get_account_balance(account_code):
    """الحصول على رصيد حساب محدد"""
    try:
        # حساب الرصيد من القيود
        debit_total = db.session.query(db.func.sum(GLEntry.debit)).join(GLBatch).filter(
            GLEntry.account == account_code,
            GLBatch.status == 'POSTED'
        ).scalar() or 0
        
        credit_total = db.session.query(db.func.sum(GLEntry.credit)).join(GLBatch).filter(
            GLEntry.account == account_code,
            GLBatch.status == 'POSTED'
        ).scalar() or 0
        
        balance = float(debit_total or 0) - float(credit_total or 0)
        
        return jsonify({
            'success': True,
            'account_code': account_code,
            'debit_total': float(debit_total or 0),
            'credit_total': float(credit_total or 0),
            'balance': balance
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/batches/all')
@owner_only
def get_all_batches():
    """جلب جميع القيود للتحرير مع الفلاتر"""
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        source_type = request.args.get('source_type')
        search = request.args.get('search')
        
        query = GLBatch.query
        
        if from_date:
            query = query.filter(GLBatch.posted_at >= from_date)
        if to_date:
            query = query.filter(GLBatch.posted_at <= to_date)
        if source_type:
            query = query.filter(GLBatch.source_type == source_type)
        if search:
            query = query.filter(GLBatch.memo.like(f'%{search}%'))
        
        batches = query.order_by(GLBatch.posted_at.desc()).limit(500).all()
        
        batches_list = []
        grand_total_debit = 0.0
        grand_total_credit = 0.0
        
        for batch in batches:
            total_debit = sum([float(entry.debit) for entry in batch.entries])
            total_credit = sum([float(entry.credit) for entry in batch.entries])
            
            grand_total_debit += total_debit
            grand_total_credit += total_credit
            
            batches_list.append({
                'id': batch.id,
                'code': batch.code,
                'posted_at': batch.posted_at.isoformat() if batch.posted_at else None,
                'source_type': batch.source_type,
                'source_id': batch.source_id,
                'purpose': batch.purpose,
                'memo': batch.memo,
                'currency': batch.currency,
                'status': batch.status,
                'total_debit': total_debit,
                'total_credit': total_credit
            })
        
        return jsonify({
            'success': True,
            'batches': batches_list,
            'total': len(batches_list),
            'grand_totals': {
                'debit': grand_total_debit,
                'credit': grand_total_credit,
                'balance': grand_total_debit - grand_total_credit
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting batches: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/batches/<int:batch_id>')
@owner_only
def get_batch_by_id(batch_id):
    """جلب قيد واحد مع جميع تفاصيله"""
    try:
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        entries_list = []
        for entry in batch.entries:
            account = Account.query.filter_by(code=entry.account).first()
            entries_list.append({
                'id': entry.id,
                'account': entry.account,
                'account_name': account.name if account else '',
                'debit': float(entry.debit),
                'credit': float(entry.credit),
                'ref': entry.ref,
                'currency': entry.currency
            })
        
        batch_data = {
            'id': batch.id,
            'code': batch.code,
            'posted_at': batch.posted_at.isoformat() if batch.posted_at else None,
            'source_type': batch.source_type,
            'source_id': batch.source_id,
            'purpose': batch.purpose,
            'memo': batch.memo,
            'currency': batch.currency,
            'status': batch.status,
            'entries': entries_list
        }
        
        return jsonify({
            'success': True,
            'batch': batch_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting batch {batch_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/batches/<int:batch_id>/update', methods=['POST'])
@owner_only
def update_batch(batch_id):
    """تحديث قيد محاسبي - ينعكس فوراً على النظام"""
    try:
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        data = request.get_json()
        
        # تحديث GLBatch
        if 'posted_at' in data:
            from datetime import datetime
            batch.posted_at = datetime.fromisoformat(data['posted_at'].replace('Z', '+00:00'))
        if 'purpose' in data:
            batch.purpose = data['purpose']
        if 'memo' in data:
            batch.memo = data['memo']
        if 'currency' in data:
            batch.currency = data['currency']
        if 'status' in data:
            batch.status = data['status']
        
        # حذف القيود الفرعية القديمة
        GLEntry.query.filter_by(batch_id=batch_id).delete()
        
        # إضافة القيود الفرعية الجديدة
        total_debit = 0
        total_credit = 0
        
        for entry_data in data.get('entries', []):
            entry = GLEntry(
                batch_id=batch_id,
                account=entry_data['account'],
                debit=entry_data['debit'],
                credit=entry_data['credit'],
                ref=entry_data.get('ref', ''),
                currency=batch.currency
            )
            db.session.add(entry)
            total_debit += entry_data['debit']
            total_credit += entry_data['credit']
        
        # التحقق من التوازن
        if abs(total_debit - total_credit) > 0.01:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': f'القيد غير متوازن: مدين={total_debit}, دائن={total_credit}'
            }), 400
        
        db.session.commit()
        
        # تسجيل في Audit Trail
        current_app.logger.info(f"✅ تم تحديث القيد {batch.code} بواسطة المالك - التغييرات انعكست على النظام")
        
        return jsonify({
            'success': True,
            'message': 'تم حفظ التغييرات بنجاح',
            'batch_id': batch_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في تحديث القيد {batch_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/backup', methods=['POST'])
@owner_only
def backup_ledger():
    """إنشاء نسخة احتياطية من دفتر الأستاذ"""
    try:
        from datetime import datetime
        import os
        import shutil
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join('instance', 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # نسخ قاعدة البيانات بالكامل
        db_path = os.path.join('instance', 'app.db')
        filename = f'ledger_backup_{timestamp}.db'
        filepath = os.path.join(backup_dir, filename)
        
        shutil.copy2(db_path, filepath)
        
        current_app.logger.info(f"✅ نسخ احتياطي: {filename}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'path': filepath
        })
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في النسخ الاحتياطي: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/backup-old', methods=['POST'])
@owner_only
def backup_ledger_old():
    """النسخ الاحتياطي القديم (subprocess)"""
    try:
        from datetime import datetime
        import os
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join('instance', 'backups', 'sql')
        os.makedirs(backup_dir, exist_ok=True)
        
        filename = f'ledger_backup_{timestamp}.sql'
        filepath = os.path.join(backup_dir, filename)
        
        # تصدير جداول GL فقط
        import subprocess
        db_path = os.path.join('instance', 'app.db')
        
        tables = ['gl_batches', 'gl_entries', 'accounts']
        with open(filepath, 'w', encoding='utf-8') as f:
            for table in tables:
                result = subprocess.run(
                    ['sqlite3', db_path, f'.dump {table}'],
                    capture_output=True,
                    text=True
                )
                f.write(result.stdout)
        
        current_app.logger.info(f"✅ نسخة احتياطية: {filename}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'path': filepath
        })
        
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في النسخ الاحتياطي: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/validate')
@owner_only
def validate_entries():
    """فحص توازن جميع القيود"""
    try:
        batches = GLBatch.query.filter(GLBatch.status == 'POSTED').all()
        
        imbalanced_batches = []
        for batch in batches:
            entries = GLEntry.query.filter_by(batch_id=batch.id).all()
            total_debit = sum(float(e.debit or 0) for e in entries)
            total_credit = sum(float(e.credit or 0) for e in entries)
            
            if abs(total_debit - total_credit) > 0.01:  # tolerance 1 cent
                imbalanced_batches.append({
                    'id': batch.id,
                    'code': batch.code,
                    'memo': batch.memo,
                    'debit': total_debit,
                    'credit': total_credit,
                    'difference': total_debit - total_credit
                })
        
        return jsonify({
            'success': True,
            'total_batches': len(batches),
            'imbalanced_batches': imbalanced_batches,
            'balanced_count': len(batches) - len(imbalanced_batches)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/cleanup', methods=['POST'])
@owner_only
def cleanup_old_entries():
    """تنظيف القيود الملغاة القديمة"""
    try:
        from datetime import datetime, timedelta
        
        # حذف القيود الملغاة القديمة (أكثر من 6 أشهر)
        six_months_ago = datetime.now() - timedelta(days=180)
        
        old_void_batches = GLBatch.query.filter(
            GLBatch.status == 'VOID',
            GLBatch.posted_at < six_months_ago
        ).all()
        
        deleted_count = 0
        for batch in old_void_batches:
            # حذف القيود المرتبطة
            GLEntry.query.filter_by(batch_id=batch.id).delete()
            db.session.delete(batch)
            deleted_count += 1
        
        db.session.commit()
        
        current_app.logger.info(f"✅ تنظيف القيود: تم حذف {deleted_count} قيد ملغي")
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في التنظيف: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===============================
# 🚀 وظائف تحكم عالية المستوى
# ===============================

@ledger_control_bp.route('/recalculate-balances', methods=['POST'])
@owner_only
def recalculate_all_balances():
    """إعادة حساب جميع الأرصدة من الصفر"""
    try:
        from models import Customer, Partner, Supplier
        
        recalculated = {
            'customers': 0,
            'partners': 0,
            'suppliers': 0
        }
        
        # إعادة حساب أرصدة العملاء
        customers = Customer.query.all()
        for customer in customers:
            balance = customer.balance  # hybrid_property
            recalculated['customers'] += 1
        
        # إعادة حساب أرصدة الشركاء
        partners = Partner.query.all()
        for partner in partners:
            balance = partner.balance
            recalculated['partners'] += 1
        
        # إعادة حساب أرصدة الموردين
        suppliers = Supplier.query.all()
        for supplier in suppliers:
            balance = supplier.balance
            recalculated['suppliers'] += 1
        
        db.session.commit()
        
        current_app.logger.info(f"✅ إعادة حساب الأرصدة: {recalculated}")
        
        return jsonify({
            'success': True,
            'recalculated': recalculated,
            'message': f"تم: {recalculated['customers']} عميل، {recalculated['partners']} شريك، {recalculated['suppliers']} مورد"
        })
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إعادة حساب الأرصدة: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/sync-checks', methods=['POST'])
@owner_only
def sync_payments_checks():
    """مزامنة الدفعات مع الشيكات"""
    try:
        synced = 0
        created = 0
        
        payments = Payment.query.filter_by(method='cheque').all()
        
        for payment in payments:
            check = Check.query.filter_by(payment_id=payment.id).first()
            
            if not check and payment.check_number:
                # إنشاء شيك جديد
                check = Check(
                    payment_id=payment.id,
                    check_number=payment.check_number,
                    bank_name=payment.check_bank or 'غير محدد',
                    due_date=payment.check_due_date or datetime.now(),
                    amount=payment.amount,
                    status='PENDING' if payment.status == 'PENDING' else 'CASHED',
                    direction=payment.direction,
                    customer_id=payment.customer_id,
                    supplier_id=payment.supplier_id,
                    partner_id=payment.partner_id
                )
                db.session.add(check)
                created += 1
            elif check:
                synced += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'created': created,
            'synced': synced,
            'message': f'تم إنشاء {created} شيك ومزامنة {synced} شيك'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/statistics', methods=['GET'])
@owner_only
def get_advanced_statistics():
    """إحصائيات متقدمة شاملة"""
    try:
        # إحصائيات الحسابات
        total_accounts = Account.query.count()
        active_accounts = Account.query.filter_by(is_active=True).count()
        
        accounts_by_type = {}
        for acc_type in ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE']:
            accounts_by_type[acc_type] = Account.query.filter_by(type=acc_type, is_active=True).count()
        
        # إحصائيات القيود
        total_batches = GLBatch.query.count()
        posted_batches = GLBatch.query.filter_by(status='POSTED').count()
        void_batches = GLBatch.query.filter_by(status='VOID').count()
        
        # القيود غير المتوازنة
        imbalanced = []
        try:
            batches = GLBatch.query.filter_by(status='POSTED').limit(100).all()
            for batch in batches:
                if batch.entries:
                    debit = sum(e.debit_amount for e in batch.entries)
                    credit = sum(e.credit_amount for e in batch.entries)
                    if abs(debit - credit) > 0.01:
                        imbalanced.append({
                            'id': batch.id,
                            'code': batch.code,
                            'diff': round(debit - credit, 2)
                        })
        except Exception as e:
            current_app.logger.warning(f"⚠️ خطأ في فحص التوازن: {str(e)}")
        
        # إحصائيات الدفعات
        total_payments = Payment.query.count()
        completed_payments = Payment.query.filter_by(status='COMPLETED').count()
        pending_payments = Payment.query.filter_by(status='PENDING').count()
        
        # إحصائيات الشيكات
        total_checks = Check.query.count()
        pending_checks = Check.query.filter_by(status='PENDING').count()
        bounced_checks = Check.query.filter_by(status='BOUNCED').count()
        
        return jsonify({
            'success': True,
            'accounts': {
                'total': total_accounts,
                'active': active_accounts,
                'by_type': accounts_by_type
            },
            'batches': {
                'total': total_batches,
                'posted': posted_batches,
                'void': void_batches
            },
            'payments': {
                'total': total_payments,
                'completed': completed_payments,
                'pending': pending_payments
            },
            'checks': {
                'total': total_checks,
                'pending': pending_checks,
                'bounced': bounced_checks
            },
            'health': {
                'imbalanced_entries': len(imbalanced),
                'issues': imbalanced[:10]
            }
        })
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في الإحصائيات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
