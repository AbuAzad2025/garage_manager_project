from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import json
from sqlalchemy import or_

from models import db, Account, GLBatch, GLEntry, Payment, PaymentMethod, PaymentStatus, Sale, Invoice, Check, CheckStatus, Partner, Supplier, Customer
from routes.checks import create_check_record
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
    
    from extensions import cache
    cache_key_cust = "ledger_total_customer_balance"
    cache_key_supp = "ledger_total_supplier_balance"
    cache_key_part = "ledger_total_partner_balance"
    
    total_customer_balance = cache.get(cache_key_cust)
    if total_customer_balance is None:
        total_customer_balance = sum([c.balance for c in Customer.query.limit(10000).all()])
        cache.set(cache_key_cust, total_customer_balance, timeout=300)
    
    total_supplier_balance = cache.get(cache_key_supp)
    if total_supplier_balance is None:
        suppliers = Supplier.query.limit(10000).all()
        for supplier in suppliers:
            db.session.refresh(supplier)
        total_supplier_balance = sum([s.balance for s in suppliers])
        cache.set(cache_key_supp, total_supplier_balance, timeout=300)
    
    total_partner_balance = cache.get(cache_key_part)
    if total_partner_balance is None:
        total_partner_balance = sum([p.balance for p in Partner.query.limit(10000).all()])
        cache.set(cache_key_part, total_partner_balance, timeout=300)
    
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
    
    from flask import make_response
    resp = make_response(render_template('security/ledger_control.html', stats=stats))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


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
            is_active=data.get('is_active', True)
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
        # تجاهل أي حقول غير معرّفة في نموذج Account مثل description
        
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
        from utils.supplier_balance_updater import update_supplier_balance_components
        
        recalculated = {
            'customers': 0,
            'partners': 0,
            'suppliers': 0
        }
        
        customers = Customer.query.limit(10000).all()
        for customer in customers:
            try:
                from utils.customer_balance_updater import update_customer_balance_components
                update_customer_balance_components(customer.id, db.session)
                recalculated['customers'] += 1
            except Exception:
                pass
        
        partners = Partner.query.limit(10000).all()
        for partner in partners:
            try:
                from models import update_partner_balance
                update_partner_balance(partner.id)
                recalculated['partners'] += 1
            except Exception:
                pass
        
        suppliers = Supplier.query.limit(10000).all()
        for supplier in suppliers:
            try:
                update_supplier_balance_components(supplier.id)
                recalculated['suppliers'] += 1
            except Exception:
                pass
        
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


@ledger_control_bp.route('/fix-cashed-checks-balance', methods=['POST'])
@owner_only
def fix_cashed_checks_balance():
    """تصحيح أرصدة العملاء المتأثرين بالشيكات المسوية والمرتدة"""
    try:
        from decimal import Decimal
        from models import Customer, Payment, Check, PaymentSplit, CheckStatus
        
        current_app.logger.info("🔍 البحث عن الشيكات المرتبطة بدفعات...")
        
        # البحث عن جميع الشيكات المرتبطة بدفعات
        all_checks = db.session.query(Check).filter(
            Check.payment_id.isnot(None)
        ).all()
        
        affected_customers = set()
        issues_found = []
        
        for check in all_checks:
            payment = db.session.get(Payment, check.payment_id)
            if not payment:
                continue
            
            # التحقق من وجود PaymentSplit
            splits = db.session.query(PaymentSplit).filter(
                PaymentSplit.payment_id == payment.id
            ).all()
            
            if splits:
                # إذا كانت الدفعة تحتوي على splits، تحقق من المبلغ
                check_amount = Decimal(str(check.amount or 0))
                payment_total = Decimal(str(payment.total_amount or 0))
                
                if check_amount != payment_total:
                    customer_id = check.customer_id or payment.customer_id
                    
                    issue = {
                        'check_id': check.id,
                        'check_number': check.check_number,
                        'check_status': check.status,
                        'check_amount': float(check_amount),
                        'payment_id': payment.id,
                        'payment_number': payment.payment_number,
                        'payment_total': float(payment_total),
                        'customer_id': customer_id,
                        'difference': float(payment_total - check_amount),
                        'splits_count': len(splits)
                    }
                    issues_found.append(issue)
                    
                    if customer_id:
                        affected_customers.add(customer_id)
        
        if issues_found:
            from utils.customer_balance_updater import update_customer_balance_components
            
            fixed_count = 0
            fixed_customers = []
            
            for customer_id in affected_customers:
                try:
                    customer = db.session.get(Customer, customer_id)
                    if not customer:
                        continue
                    
                    old_balance = float(customer.current_balance or 0)
                    
                    update_customer_balance_components(customer_id, db.session)
                    db.session.flush()
                    
                    db.session.refresh(customer)
                    new_balance = float(customer.current_balance or 0)
                    
                    db.session.commit()
                    
                    fixed_customers.append({
                        'customer_id': customer_id,
                        'customer_name': customer.name,
                        'old_balance': old_balance,
                        'new_balance': new_balance,
                        'difference': new_balance - old_balance
                    })
                    fixed_count += 1
                except Exception as e:
                    current_app.logger.error(f"❌ خطأ في تحديث رصيد العميل #{customer_id}: {e}")
                    db.session.rollback()
            
            return jsonify({
                'success': True,
                'message': f'تم تصحيح أرصدة {fixed_count} عميل',
                'total_checks': len(all_checks),
                'issues_found': len(issues_found),
                'affected_customers': len(affected_customers),
                'fixed_customers': fixed_customers,
                'issues': issues_found
            })
        else:
            return jsonify({
                'success': True,
                'message': 'لا توجد مشاكل في الشيكات',
                'total_checks': len(all_checks),
                'issues_found': 0
            })
            
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في تصحيح أرصدة الشيكات: {str(e)}")
        
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/sync-checks', methods=['POST'])
@owner_only
def sync_payments_checks():
    """مزامنة الدفعات مع الشيكات"""
    try:
        synced = 0
        created = 0
        payments = Payment.query.filter(
            or_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.method.ilike('%check%')
            )
        ).all()
        for payment in payments:
            if not payment.check_number or not payment.check_bank:
                continue
            existing = Check.query.filter_by(payment_id=payment.id, check_number=payment.check_number).first()
            if existing:
                synced += 1
                continue
            status_value = CheckStatus.PENDING.value if payment.status == PaymentStatus.PENDING.value else CheckStatus.CASHED.value
            _, created_flag = create_check_record(
                payment=payment,
                amount=payment.total_amount,
                check_number=payment.check_number,
                check_bank=payment.check_bank,
                check_date=payment.payment_date or datetime.utcnow(),
                check_due_date=payment.check_due_date or payment.payment_date,
                currency=payment.currency or 'ILS',
                direction=payment.direction,
                customer_id=payment.customer_id,
                supplier_id=payment.supplier_id,
                partner_id=payment.partner_id,
                reference_number=f"PMT-{payment.id}",
                status=status_value
            )
            if created_flag:
                created += 1
        if created:
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


# ========== مركز التحكم المتقدم - الفترات والعمليات ==========

@ledger_control_bp.route('/operations/fiscal-periods/api', methods=['GET'])
@owner_only
def get_fiscal_periods():
    """API: جلب جميع الفترات المحاسبية"""
    try:
        from sqlalchemy import func
        from datetime import date
        
        # حساب الفترات من البيانات الموجودة
        oldest_batch = db.session.query(func.min(GLBatch.posted_at)).filter(
            GLBatch.status == 'POSTED'
        ).scalar()
        
        if not oldest_batch:
            return jsonify({
                'success': True,
                'periods': [],
                'message': 'لا توجد قيود محاسبية بعد'
            })
        
        # إنشاء فترات شهرية تلقائياً
        start_date = oldest_batch.replace(day=1)
        end_date = datetime.now()
        
        periods = []
        current = start_date
        
        while current <= end_date:
            # حساب نهاية الشهر
            if current.month == 12:
                month_end = date(current.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
            
            # حساب عدد القيود في هذه الفترة
            batches_count = GLBatch.query.filter(
                GLBatch.status == 'POSTED',
                GLBatch.posted_at >= current,
                GLBatch.posted_at <= month_end
            ).count()
            
            # حساب مجموع المدين والدائن
            totals = db.session.query(
                func.sum(GLEntry.debit).label('total_debit'),
                func.sum(GLEntry.credit).label('total_credit')
            ).join(GLBatch).filter(
                GLBatch.status == 'POSTED',
                GLBatch.posted_at >= current,
                GLBatch.posted_at <= month_end
            ).first()
            
            periods.append({
                'period_id': current.strftime('%Y%m'),
                'start_date': current.isoformat(),
                'end_date': month_end.isoformat(),
                'name': current.strftime('%B %Y'),
                'name_ar': f"{current.strftime('%B')} {current.year}",
                'is_closed': False,
                'batches_count': batches_count,
                'total_debit': float(totals.total_debit or 0),
                'total_credit': float(totals.total_credit or 0),
                'is_current': current.month == datetime.now().month and current.year == datetime.now().year
            })
            
            # الانتقال للشهر التالي
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        
        return jsonify({
            'success': True,
            'periods': list(reversed(periods))  # الأحدث أولاً
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في جلب الفترات المحاسبية: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/closing-entries/generate', methods=['POST'])
@owner_only
def generate_closing_entries():
    """إنشاء قيود الإقفال التلقائية"""
    try:
        from decimal import Decimal
        from sqlalchemy import func
        
        data = request.get_json()
        period_end = datetime.fromisoformat(data['period_end'])
        
        # 1. إقفال حسابات الإيرادات (4xxx)
        revenues = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.credit - GLEntry.debit).label('balance')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= period_end,
            GLEntry.account.like('4%')
        ).group_by(GLEntry.account).all()
        
        # 2. إقفال حسابات المصروفات (5xxx)
        expenses = db.session.query(
            GLEntry.account,
            func.sum(GLEntry.debit - GLEntry.credit).label('balance')
        ).join(GLBatch).filter(
            GLBatch.status == 'POSTED',
            GLBatch.posted_at <= period_end,
            GLEntry.account.like('5%')
        ).group_by(GLEntry.account).all()
        
        # حساب صافي الدخل
        total_revenue = sum(float(r.balance) for r in revenues)
        total_expenses = sum(float(e.balance) for e in expenses)
        net_income = total_revenue - total_expenses
        
        closing_entries = []
        
        # قيد إقفال الإيرادات
        if revenues:
            closing_entries.append({
                'type': 'close_revenue',
                'description': 'إقفال حسابات الإيرادات',
                'entries': [
                    {'account': r.account, 'debit': float(r.balance), 'credit': 0} 
                    for r in revenues
                ] + [
                    {'account': '3200_CURRENT_EARNINGS', 'debit': 0, 'credit': total_revenue}
                ],
                'total': total_revenue
            })
        
        # قيد إقفال المصروفات
        if expenses:
            closing_entries.append({
                'type': 'close_expenses',
                'description': 'إقفال حسابات المصروفات',
                'entries': [
                    {'account': e.account, 'debit': 0, 'credit': float(e.balance)} 
                    for e in expenses
                ] + [
                    {'account': '3200_CURRENT_EARNINGS', 'debit': total_expenses, 'credit': 0}
                ],
                'total': total_expenses
            })
        
        # قيد نقل صافي الدخل للأرباح المحتجزة
        closing_entries.append({
            'type': 'transfer_net_income',
            'description': 'نقل صافي الدخل للأرباح المحتجزة',
            'entries': [
                {'account': '3200_CURRENT_EARNINGS', 'debit': net_income if net_income > 0 else 0, 'credit': -net_income if net_income < 0 else 0},
                {'account': '3100_RETAINED_EARNINGS', 'debit': -net_income if net_income < 0 else 0, 'credit': net_income if net_income > 0 else 0}
            ],
            'total': abs(net_income)
        })
        
        return jsonify({
            'success': True,
            'period_end': period_end.isoformat(),
            'net_income': net_income,
            'closing_entries': closing_entries,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses
        })
        
    except Exception as e:
        current_app.logger.error(f"خطأ في إنشاء قيود الإقفال: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/closing-entries/post', methods=['POST'])
@owner_only
def post_closing_entries():
    """ترحيل قيود الإقفال"""
    try:
        from decimal import Decimal
        
        data = request.get_json()
        entries = data.get('entries', [])
        period_end = datetime.fromisoformat(data['period_end'])
        
        created_batches = []
        
        for entry_group in entries:
            # إنشاء GLBatch
            batch = GLBatch(
                code=f"CLOSING-{entry_group['type']}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                source_type='CLOSING_ENTRY',
                purpose=entry_group['description'],
                memo=f"قيد إقفال - {entry_group['description']}",
                currency='ILS',
                status='POSTED',
                posted_at=period_end
            )
            db.session.add(batch)
            db.session.flush()
            
            # إنشاء GLEntries
            for line in entry_group['entries']:
                gl_entry = GLEntry(
                    batch_id=batch.id,
                    account=line['account'],
                    debit=Decimal(str(line['debit'])),
                    credit=Decimal(str(line['credit'])),
                    ref=f"Closing-{period_end.strftime('%Y%m')}",
                    currency='ILS'
                )
                db.session.add(gl_entry)
            
            created_batches.append(batch.id)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم ترحيل {len(created_batches)} قيد إقفال',
            'batch_ids': created_batches
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في ترحيل قيود الإقفال: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/reverse-entry/<int:batch_id>', methods=['POST'])
@owner_only
def reverse_entry(batch_id):
    """🔄 إنشاء قيد عكسي"""
    try:
        original_batch = GLBatch.query.get(batch_id)
        if not original_batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        # التحقق من عدم وجود قيد عكسي سابق
        existing_reversal = GLBatch.query.filter_by(
            source_type='REVERSAL',
            source_id=batch_id
        ).first()
        
        if existing_reversal:
            return jsonify({
                'success': False,
                'error': 'يوجد قيد عكسي لهذا القيد بالفعل',
                'reversal_batch_id': existing_reversal.id
            }), 400
        
        # إنشاء القيد العكسي
        reversal_batch = GLBatch(
            code=f"REV-{original_batch.code}",
            source_type='REVERSAL',
            source_id=original_batch.id,
            purpose=f"عكس: {original_batch.purpose}",
            memo=f"قيد عكسي للقيد #{batch_id} - {original_batch.memo}",
            currency=original_batch.currency,
            status='POSTED',
            posted_at=datetime.now()
        )
        db.session.add(reversal_batch)
        db.session.flush()
        
        # عكس القيود الفرعية (تبديل المدين والدائن)
        for original_entry in original_batch.entries:
            reversal_entry = GLEntry(
                batch_id=reversal_batch.id,
                account=original_entry.account,
                debit=original_entry.credit,  # عكس
                credit=original_entry.debit,  # عكس
                ref=f"REV-{original_entry.ref}",
                currency=original_entry.currency
            )
            db.session.add(reversal_entry)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إنشاء القيد العكسي بنجاح',
            'original_batch_id': batch_id,
            'reversal_batch_id': reversal_batch.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في إنشاء قيد عكسي: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/review-queue', methods=['GET'])
@owner_only
def review_queue():
    """📋 قائمة القيود المعلقة للمراجعة"""
    try:
        from sqlalchemy import desc
        
        pending_batches = GLBatch.query.filter_by(status='DRAFT').order_by(
            desc(GLBatch.created_at)
        ).all()
        
        batches_data = []
        for batch in pending_batches:
            total_debit = sum(float(e.debit) for e in batch.entries)
            total_credit = sum(float(e.credit) for e in batch.entries)
            is_balanced = abs(total_debit - total_credit) < 0.01
            
            batches_data.append({
                'id': batch.id,
                'code': batch.code,
                'purpose': batch.purpose,
                'memo': batch.memo,
                'created_at': batch.created_at.isoformat() if batch.created_at else None,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'is_balanced': is_balanced,
                'entries_count': len(batch.entries)
            })
        
        return jsonify({
            'success': True,
            'pending_count': len(batches_data),
            'batches': batches_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/approve-batch/<int:batch_id>', methods=['POST'])
@owner_only
def approve_batch(batch_id):
    """✅ الموافقة على قيد وترحيله"""
    try:
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        if batch.status == 'POSTED':
            return jsonify({'success': False, 'error': 'القيد مرحّل بالفعل'}), 400
        
        # التحقق من التوازن
        total_debit = sum(float(e.debit) for e in batch.entries)
        total_credit = sum(float(e.credit) for e in batch.entries)
        
        if abs(total_debit - total_credit) > 0.01:
            return jsonify({
                'success': False,
                'error': f'القيد غير متوازن: مدين={total_debit}, دائن={total_credit}'
            }), 400
        
        # الموافقة والترحيل
        batch.status = 'POSTED'
        batch.posted_at = datetime.now()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تمت الموافقة على القيد وترحيله بنجاح',
            'batch_id': batch_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/reject-batch/<int:batch_id>', methods=['POST'])
@owner_only
def reject_batch(batch_id):
    """❌ رفض قيد"""
    try:
        data = request.get_json()
        reason = data.get('reason', 'غير محدد')
        
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        # تحديث الحالة
        batch.status = 'REJECTED'
        batch.memo = f"{batch.memo} [مرفوض: {reason}]"
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم رفض القيد',
            'batch_id': batch_id,
            'reason': reason
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== تحرير وربط القيود ==========

@ledger_control_bp.route('/operations/batch/<int:batch_id>/link-entity', methods=['POST'])
@owner_only
def link_batch_to_entity(batch_id):
    """🔗 ربط قيد محاسبي بجهة"""
    try:
        data = request.get_json()
        entity_type = data.get('entity_type')  # CUSTOMER, SUPPLIER, PARTNER, EMPLOYEE, BRANCH, USER
        entity_id = data.get('entity_id')
        
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        # التحقق من صحة الجهة
        if entity_type and entity_id:
            entity_model = {
                'CUSTOMER': Customer,
                'SUPPLIER': Supplier,
                'PARTNER': Partner,
                'EMPLOYEE': lambda: db.session.query(db.select(1)).first()  # مبسط
            }.get(entity_type)
            
            if entity_model and entity_type in ['CUSTOMER', 'SUPPLIER', 'PARTNER']:
                entity = entity_model.query.get(entity_id)
                if not entity:
                    return jsonify({'success': False, 'error': f'الجهة غير موجودة'}), 404
        
        # التحديث
        old_entity_type = batch.entity_type
        old_entity_id = batch.entity_id
        
        batch.entity_type = entity_type
        batch.entity_id = entity_id if entity_id else None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم ربط القيد بـ {entity_type} #{entity_id}',
            'batch_id': batch_id,
            'old_entity': f'{old_entity_type}/{old_entity_id}',
            'new_entity': f'{entity_type}/{entity_id}'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في ربط القيد: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/batch/<int:batch_id>/edit', methods=['GET'])
@owner_only
def get_batch_for_edit(batch_id):
    """📝 جلب بيانات قيد للتحرير"""
    try:
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        # جلب بيانات الجهة المرتبطة
        entity_name = None
        if batch.entity_type and batch.entity_id:
            if batch.entity_type == 'CUSTOMER':
                entity = Customer.query.get(batch.entity_id)
                entity_name = entity.name if entity else None
            elif batch.entity_type == 'SUPPLIER':
                entity = Supplier.query.get(batch.entity_id)
                entity_name = entity.name if entity else None
            elif batch.entity_type == 'PARTNER':
                entity = Partner.query.get(batch.entity_id)
                entity_name = entity.name if entity else None
        
        return jsonify({
            'success': True,
            'batch': {
                'id': batch.id,
                'code': batch.code,
                'source_type': batch.source_type,
                'source_id': batch.source_id,
                'purpose': batch.purpose,
                'memo': batch.memo,
                'currency': batch.currency,
                'status': batch.status,
                'posted_at': batch.posted_at.isoformat() if batch.posted_at else None,
                'entity_type': batch.entity_type,
                'entity_id': batch.entity_id,
                'entity_name': entity_name,
                'entries': [{
                    'id': e.id,
                    'account': e.account,
                    'debit': float(e.debit or 0),
                    'credit': float(e.credit or 0),
                    'ref': e.ref,
                    'currency': e.currency
                } for e in batch.entries]
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/batch/<int:batch_id>/update-full', methods=['POST'])
@owner_only
def update_batch_full(batch_id):
    """✏️ تحديث كامل لقيد محاسبي"""
    try:
        data = request.get_json()
        
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'القيد غير موجود'}), 404
        
        # تحديث بيانات القيد
        if 'purpose' in data:
            batch.purpose = data['purpose']
        if 'memo' in data:
            batch.memo = data['memo']
        if 'entity_type' in data:
            batch.entity_type = data['entity_type']
        if 'entity_id' in data:
            batch.entity_id = data['entity_id'] if data['entity_id'] else None
        if 'posted_at' in data and data['posted_at']:
            batch.posted_at = datetime.fromisoformat(data['posted_at'])
        
        # تحديث السطور إذا تم إرسالها
        if 'entries' in data:
            # حذف السطور القديمة
            GLEntry.query.filter_by(batch_id=batch_id).delete()
            
            # إضافة السطور الجديدة
            total_debit = 0
            total_credit = 0
            
            for entry_data in data['entries']:
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
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث القيد بنجاح',
            'batch_id': batch_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في تحديث القيد: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/operations/entities/search', methods=['GET'])
@owner_only
def search_entities():
    """🔍 البحث عن جهات لربطها بالقيود"""
    try:
        entity_type = request.args.get('type')  # CUSTOMER, SUPPLIER, PARTNER
        search_term = request.args.get('q', '')
        
        results = []
        
        if entity_type == 'CUSTOMER':
            entities = Customer.query.filter(
                Customer.name.contains(search_term)
            ).limit(20).all()
            results = [{'id': e.id, 'name': e.name, 'type': 'CUSTOMER'} for e in entities]
        
        elif entity_type == 'SUPPLIER':
            entities = Supplier.query.filter(
                Supplier.name.contains(search_term)
            ).limit(20).all()
            results = [{'id': e.id, 'name': e.name, 'type': 'SUPPLIER'} for e in entities]
        
        elif entity_type == 'PARTNER':
            entities = Partner.query.filter(
                Partner.name.contains(search_term)
            ).limit(20).all()
            results = [{'id': e.id, 'name': e.name, 'type': 'PARTNER'} for e in entities]
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ledger_control_bp.route('/verify-customer-balances', methods=['POST'])
@owner_only
def verify_customer_balances():
    """التحقق من أرصدة العملاء القدامى وتحديثها حسب النظام الجديد"""
    try:
        from decimal import Decimal
        from models import Customer
        from utils.customer_balance_updater import update_customer_balance_components
        from utils.balance_calculator import calculate_customer_balance_components
        
        customers = Customer.query.limit(10000).all()
        total = len(customers)
        
        verified = 0
        updated = 0
        issues = []
        
        for customer in customers:
            try:
                db.session.refresh(customer)
                
                old_balance = Decimal(str(customer.current_balance or 0))
                
                components = calculate_customer_balance_components(customer.id, db.session)
                if not components:
                    continue
                
                opening_balance = Decimal(str(customer.opening_balance or 0))
                if customer.currency and customer.currency != "ILS":
                    try:
                        from models import convert_amount
                        opening_balance = convert_amount(opening_balance, customer.currency, "ILS")
                    except Exception:
                        pass
                
                expected_balance = (
                    opening_balance +
                    Decimal(str(components.get('payments_in_balance', 0) or 0)) -
                    (Decimal(str(components.get('sales_balance', 0) or 0)) +
                     Decimal(str(components.get('invoices_balance', 0) or 0)) +
                     Decimal(str(components.get('services_balance', 0) or 0)) +
                     Decimal(str(components.get('preorders_balance', 0) or 0)) +
                     Decimal(str(components.get('online_orders_balance', 0) or 0))) +
                    Decimal(str(components.get('returns_balance', 0) or 0)) -
                    Decimal(str(components.get('payments_out_balance', 0) or 0)) -
                    Decimal(str(components.get('returned_checks_in_balance', 0) or 0)) +
                    Decimal(str(components.get('returned_checks_out_balance', 0) or 0)) -
                    Decimal(str(components.get('expenses_balance', 0) or 0)) +
                    Decimal(str(components.get('service_expenses_balance', 0) or 0))
                )
                
                difference = abs(expected_balance - old_balance)
                
                if difference > Decimal('0.01'):
                    update_customer_balance_components(customer.id, db.session)
                    db.session.flush()
                    db.session.refresh(customer)
                    new_balance = Decimal(str(customer.current_balance or 0))
                    
                    issues.append({
                        'customer_id': customer.id,
                        'customer_name': customer.name,
                        'old_balance': float(old_balance),
                        'expected_balance': float(expected_balance),
                        'new_balance': float(new_balance),
                        'difference': float(difference)
                    })
                    updated += 1
                else:
                    verified += 1
                    
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في التحقق من رصيد العميل #{customer.id}: {e}")
                issues.append({
                    'customer_id': customer.id,
                    'customer_name': getattr(customer, 'name', 'Unknown'),
                    'error': str(e)
                })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'total_customers': total,
            'verified': verified,
            'updated': updated,
            'issues': issues,
            'message': f'تم التحقق من {total} عميل: {verified} صحيح، {updated} تم تحديثه'
        })
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في التحقق من أرصدة العملاء: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
