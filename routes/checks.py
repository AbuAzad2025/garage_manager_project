
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import current_user, login_required
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, desc, func
from extensions import db
try:
    from extensions import limiter
except ImportError:
    limiter = None
from models import (
    Payment, PaymentSplit, Expense, PaymentMethod, PaymentStatus, PaymentDirection, 
    Check, CheckStatus, Customer, Supplier, Partner, GLBatch, GLEntry, Account
)
import utils
from decimal import Decimal
import json
import uuid

checks_bp = Blueprint('checks', __name__, url_prefix='/checks')


from sqlalchemy import event

@event.listens_for(Check, 'before_delete')
def _check_before_delete(mapper, connection, target):
    try:
        # حذف جميع GLBatch المرتبطة بهذا الشيك
        connection.execute(
            GLBatch.__table__.delete().where(
                (GLBatch.source_type == 'check_check') & 
                (GLBatch.source_id == target.id)
            )
        )
    except Exception as e:
        print(f"❌ خطأ في حذف القيود المحاسبية للشيك {target.id}: {str(e)}")


@event.listens_for(Payment, 'before_delete')
def _payment_check_before_delete(mapper, connection, target):
    try:
        # إذا كانت دفعة شيك، احذف القيود
        if target.method == PaymentMethod.CHEQUE:
            connection.execute(
                GLBatch.__table__.delete().where(
                    (GLBatch.source_type == 'check_payment') & 
                    (GLBatch.source_id == target.id)
                )
            )
    except Exception as e:
        print(f"❌ خطأ في حذف القيود المحاسبية للدفعة {target.id}: {str(e)}")


@event.listens_for(GLBatch, 'before_delete')
def _glbatch_before_delete(mapper, connection, target):
    """عند حذف قيد محاسبي مرتبط بشيك، إلغاء الشيك تلقائياً"""
    try:
        source_type = target.source_type
        source_id = target.source_id
        
        if source_type == 'check_check':
            # إضافة ملاحظة إلغاء للشيك اليدوي
            connection.execute(
                Check.__table__.update().where(Check.id == source_id).values(
                    status='CANCELLED',
                    notes=Check.notes + '\n⚠️ تم إلغاء الشيك بسبب حذف القيد المحاسبي'
                )
            )
        elif source_type == 'check_payment':
            # إضافة ملاحظة إلغاء للدفعة
            connection.execute(
                Payment.__table__.update().where(Payment.id == source_id).values(
                    notes=Payment.notes + '\n⚠️ تم إلغاء الشيك بسبب حذف القيد المحاسبي'
                )
            )
    except Exception as e:
        print(f"❌ خطأ في إلغاء الشيك عند حذف القيد: {str(e)}")


def ensure_check_accounts():
    """التأكد من وجود جميع حسابات دفتر الأستاذ المطلوبة"""
    try:
        required_accounts = [
            # حسابات الأصول
            ('1000_CASH', 'الصندوق', 'ASSET'),
            ('1010_BANK', 'البنك', 'ASSET'),
            ('1020_CARD_CLEARING', 'بطاقات الائتمان', 'ASSET'),
            ('1100_AR', 'العملاء (ذمم مدينة)', 'ASSET'),
            ('1150_CHEQUES_RECEIVABLE', 'شيكات تحت التحصيل', 'ASSET'),
            ('1205_INV_EXCHANGE', 'المخزون - تبادل', 'ASSET'),
            
            # حسابات الخصوم
            ('2000_AP', 'الموردين (ذمم دائنة)', 'LIABILITY'),
            ('2100_VAT_PAYABLE', 'ضريبة القيمة المضافة', 'LIABILITY'),
            ('2150_CHEQUES_PAYABLE', 'شيكات تحت الدفع', 'LIABILITY'),
            
            # حسابات الإيرادات
            ('4000_SALES', 'المبيعات', 'REVENUE'),
            
            # حسابات المصروفات
            ('5000_EXPENSES', 'المصروفات العامة', 'EXPENSE'),
            ('5105_COGS_EXCHANGE', 'تكلفة البضاعة المباعة', 'EXPENSE'),
        ]
        
        for code, name, acc_type in required_accounts:
            existing = Account.query.filter_by(code=code).first()
            if not existing:
                new_account = Account(code=code, name=name, type=acc_type, is_active=True)
                db.session.add(new_account)
                current_app.logger.info(f"✅ تم إنشاء حساب: {code} - {name}")
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إنشاء حسابات دفتر الأستاذ: {str(e)}")
        db.session.rollback()


def create_gl_entry_for_check(check_id, check_type, amount, currency, direction, 
                               new_status, old_status=None, entity_name='', notes=''):
    """
    إنشاء قيد محاسبي عند تغيير حالة الشيك
    
    القيود المحاسبية:
    1. عند استلام شيك من عميل (INCOMING):
       - مدين: شيكات تحت التحصيل (أصل)
       - دائن: العملاء (أصل - تخفيض)
       
    2. عند صرف شيك وارد (CASHED - INCOMING):
       - مدين: البنك (أصل - زيادة)
       - دائن: شيكات تحت التحصيل (أصل - تخفيض)
       
    3. عند إرجاع شيك وارد (RETURNED - INCOMING):
       - مدين: العملاء (أصل - زيادة)
       - دائن: شيكات تحت التحصيل (أصل - تخفيض)
       
    4. عند إعطاء شيك لمورد (OUTGOING):
       - مدين: الموردين (خصم - تخفيض)
       - دائن: شيكات تحت الدفع (خصم - زيادة)
       
    5. عند صرف شيك صادر (CASHED - OUTGOING):
       - مدين: شيكات تحت الدفع (خصم - تخفيض)
       - دائن: البنك (أصل - تخفيض)
       
    6. عند إرجاع شيك صادر (RETURNED - OUTGOING):
       - مدين: شيكات تحت الدفع (خصم - تخفيض)
       - دائن: الموردين (خصم - زيادة)
    """
    try:
        # التأكد من وجود الحسابات
        ensure_check_accounts()
        
        # تحديد نوع القيد بناءً على الحالة والاتجاه
        is_incoming = (direction == 'IN')
        amount_decimal = Decimal(str(amount))
        
        # إنشاء GLBatch
        batch_code = f"CHK-{check_type.upper()}-{check_id}-{uuid.uuid4().hex[:8].upper()}"
        batch = GLBatch(
            code=batch_code,
            source_type=f'check_{check_type}',
            source_id=int(check_id) if str(check_id).replace('-', '').isdigit() else check_id,
            currency=currency or 'ILS',
            status='POSTED',
            memo=f"قيد شيك: {entity_name} - {notes}"
        )
        db.session.add(batch)
        db.session.flush()
        
        entries = []
        
        # القيود حسب الحالة الجديدة
        if new_status == 'CASHED':
            if is_incoming:
                # شيك وارد تم صرفه
                # مدين: البنك | دائن: شيكات تحت التحصيل
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['BANK'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"صرف شيك وارد من {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"صرف شيك وارد من {entity_name}"
                ))
            else:
                # شيك صادر تم صرفه
                # مدين: شيكات تحت الدفع | دائن: البنك
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"صرف شيك صادر إلى {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['BANK'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"صرف شيك صادر إلى {entity_name}"
                ))
                
        elif new_status == 'RETURNED' or new_status == 'BOUNCED':
            if is_incoming:
                # شيك وارد تم إرجاعه
                # مدين: العملاء | دائن: شيكات تحت التحصيل
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['AR'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"إرجاع شيك من {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"إرجاع شيك من {entity_name}"
                ))
            else:
                # شيك صادر تم إرجاعه
                # مدين: شيكات تحت الدفع | دائن: الموردين
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"إرجاع شيك إلى {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['AP'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"إرجاع شيك إلى {entity_name}"
                ))
                
        elif new_status == 'CANCELLED':
            # إلغاء/إتلاف الشيك → عكس القيد الأصلي تماماً
            if is_incoming:
                # إلغاء شيك وارد → إرجاع الدين للعميل
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['AR'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"⛔ إلغاء/إتلاف شيك وارد من {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"⛔ إلغاء/إتلاف شيك وارد من {entity_name}"
                ))
            else:
                # إلغاء شيك صادر → إرجاع الدين للمورد
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                    debit=amount_decimal,
                    credit=0,
                    currency=currency or 'ILS',
                    ref=f"⛔ إلغاء/إتلاف شيك صادر إلى {entity_name}"
                ))
                entries.append(GLEntry(
                    batch_id=batch.id,
                    account=GL_ACCOUNTS_CHECKS['AP'],
                    debit=0,
                    credit=amount_decimal,
                    currency=currency or 'ILS',
                    ref=f"⛔ إلغاء/إتلاف شيك صادر إلى {entity_name}"
                ))
        
        # إضافة القيود
        for entry in entries:
            db.session.add(entry)
        
        db.session.flush()
        
        current_app.logger.info(f"✅ تم إنشاء قيد محاسبي للشيك {check_id} - Batch: {batch_code}")
        return batch
        
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للشيك {check_id}: {str(e)}")
        db.session.rollback()
        return None

# حالات الشيك المخصصة
CHECK_STATUS = {
    'PENDING': {'ar': 'معلق', 'color': 'info', 'icon': 'fa-clock'},
    'CASHED': {'ar': 'تم الصرف', 'color': 'success', 'icon': 'fa-check-circle'},
    'RETURNED': {'ar': 'مرتجع', 'color': 'warning', 'icon': 'fa-undo'},
    'BOUNCED': {'ar': 'مرفوض', 'color': 'danger', 'icon': 'fa-ban'},
    'RESUBMITTED': {'ar': 'أعيد للبنك', 'color': 'primary', 'icon': 'fa-recycle'},
    'CANCELLED': {'ar': 'ملغي', 'color': 'secondary', 'icon': 'fa-times-circle'},
    'ARCHIVED': {'ar': 'مؤرشف', 'color': 'dark', 'icon': 'fa-archive'},
    'OVERDUE': {'ar': 'متأخر', 'color': 'danger', 'icon': 'fa-exclamation-triangle'},
}

# حسابات دفتر الأستاذ للشيكات
GL_ACCOUNTS_CHECKS = {
    'CHEQUES_RECEIVABLE': '1150_CHEQUES_RECEIVABLE',  # شيكات تحت التحصيل (أصول)
    'CHEQUES_PAYABLE': '2150_CHEQUES_PAYABLE',        # شيكات تحت الدفع (خصوم)
    'BANK': '1010_BANK',                               # البنك
    'CASH': '1000_CASH',                               # الصندوق
    'AR': '1100_AR',                                   # العملاء (Accounts Receivable)
    'AP': '2000_AP',                                   # الموردين (Accounts Payable)
}

# دورة حياة الشيك (Life Cycle)
CHECK_LIFECYCLE = {
    'PENDING': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'RETURNED': ['RESUBMITTED', 'CANCELLED'],
    'BOUNCED': ['RESUBMITTED', 'CANCELLED'],
    'RESUBMITTED': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'OVERDUE': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'CASHED': [],  # نهائية
    'CANCELLED': []  # نهائية
}


@checks_bp.route('/')
# @permission_required('view_payments')  # Commented out
def index():
    """صفحة عرض الشيكات"""
    return render_template('checks/index.html')


@checks_bp.route('/api/checks')
@login_required
def get_checks():
    """
    API لجلب الشيكات من جميع المصادر مع الفلاتر
    المصادر: Payment + Expense + Check (اليدوي)
    """
    try:
        # الفلاتر من الـ request
        direction = request.args.get('direction')  # 'in' أو 'out' أو 'all'
        status = request.args.get('status')  # 'pending', 'completed', 'overdue', 'all'
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        source_filter = request.args.get('source')  # 'payment', 'expense', 'manual', 'all'
        
        checks = []
        today = datetime.utcnow().date()
        check_ids = set()  # لتتبع الـ IDs وتجنب التكرار
        
        current_app.logger.info(f"🔍 get_checks API - بدء الجلب من جميع المصادر...")
        
        # 1. جلب الشيكات من Payment (إذا لم يتم فلترتها)
        if not source_filter or source_filter in ['all', 'payment']:
            payment_checks = Payment.query.filter(
                Payment.method == PaymentMethod.CHEQUE.value
            )
            
            # جلب الدفعات التي تحتوي على splits بطريقة شيك
            from models import PaymentSplit
            payment_with_splits = db.session.query(Payment).join(
                PaymentSplit, Payment.id == PaymentSplit.payment_id
            ).filter(
                PaymentSplit.method == PaymentMethod.CHEQUE.value
            )
            
            # فلتر حسب الاتجاه
            if direction == 'in':
                payment_checks = payment_checks.filter(Payment.direction == PaymentDirection.IN.value)
                payment_with_splits = payment_with_splits.filter(Payment.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                payment_checks = payment_checks.filter(Payment.direction == PaymentDirection.OUT.value)
                payment_with_splits = payment_with_splits.filter(Payment.direction == PaymentDirection.OUT.value)
            
            # فلتر حسب الحالة
            if status == 'pending':
                payment_checks = payment_checks.filter(Payment.status == PaymentStatus.PENDING.value)
                payment_with_splits = payment_with_splits.filter(Payment.status == PaymentStatus.PENDING.value)
            elif status == 'completed':
                payment_checks = payment_checks.filter(Payment.status == PaymentStatus.COMPLETED.value)
                payment_with_splits = payment_with_splits.filter(Payment.status == PaymentStatus.COMPLETED.value)
            elif status == 'overdue':
                payment_checks = payment_checks.filter(
                    and_(
                        Payment.status == PaymentStatus.PENDING.value,
                        Payment.check_due_date < datetime.utcnow()
                    )
                )
                payment_with_splits = payment_with_splits.filter(
                    and_(
                        Payment.status == PaymentStatus.PENDING.value,
                        Payment.check_due_date < datetime.utcnow()
                    )
                )
            
            # فلتر حسب التاريخ
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    payment_checks = payment_checks.filter(Payment.check_due_date >= from_dt)
                    payment_with_splits = payment_with_splits.filter(Payment.check_due_date >= from_dt)
                except:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    payment_checks = payment_checks.filter(Payment.check_due_date <= to_dt)
                    payment_with_splits = payment_with_splits.filter(Payment.check_due_date <= to_dt)
                except:
                    pass
            
            # معالجة شيكات Payment العادية (method = cheque)
            for payment in payment_checks.all():
                if not payment.check_due_date:
                    continue
                
                due_date = payment.check_due_date.date() if isinstance(payment.check_due_date, datetime) else payment.check_due_date
                days_until_due = (due_date - today).days
                
                # تحديد الحالة
                if payment.status == PaymentStatus.COMPLETED.value:
                    check_status = 'CASHED'
                    status_ar = 'تم الصرف'
                    badge_color = 'success'
                elif payment.status == PaymentStatus.FAILED.value:
                    notes_lower = (payment.notes or '').lower()
                    if 'مرتجع' in notes_lower or 'returned' in notes_lower:
                        check_status = 'RETURNED'
                        status_ar = 'مرتجع'
                        badge_color = 'warning'
                    else:
                        check_status = 'BOUNCED'
                        status_ar = 'مرفوض'
                        badge_color = 'danger'
                elif payment.status == PaymentStatus.CANCELLED.value:
                    check_status = 'CANCELLED'
                    status_ar = 'ملغي'
                    badge_color = 'secondary'
                elif days_until_due < 0:
                    check_status = 'OVERDUE'
                    status_ar = 'متأخر'
                    badge_color = 'danger'
                elif days_until_due <= 7:
                    check_status = 'due_soon'
                    status_ar = 'قريب الاستحقاق'
                    badge_color = 'warning'
                else:
                    check_status = 'PENDING'
                    status_ar = 'معلق'
                    badge_color = 'info'
                
                # تحديد نوع الشيك
                is_incoming = payment.direction == PaymentDirection.IN.value
                
                # تحديد اسم الجهة والرابط
                entity_name = ''
                entity_link = ''
                entity_type = ''
                if payment.customer:
                    entity_name = payment.customer.name
                    entity_link = f'/customers/{payment.customer.id}'
                    entity_type = 'عميل'
                elif payment.supplier:
                    entity_name = payment.supplier.name
                    entity_link = f'/vendors/{payment.supplier.id}'
                    entity_type = 'مورد'
                elif payment.partner:
                    entity_name = payment.partner.name
                    entity_link = f'/partners/{payment.partner.id}'
                    entity_type = 'شريك'
                
                # تجنب التكرار
                check_key = f"payment-{payment.id}"
                if check_key in check_ids:
                    continue
                check_ids.add(check_key)
                
                checks.append({
                    'id': payment.id,
                    'type': 'payment',
                    'source': 'دفعة',
                    'source_badge': 'primary',
                    'check_number': payment.check_number or '',
                    'check_bank': payment.check_bank or '',
                    'check_due_date': due_date.strftime('%Y-%m-%d'),
                    'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                    'amount': float(payment.total_amount or 0),
                    'currency': payment.currency or 'ILS',
                    'fx_rate_issue': float(payment.fx_rate_used) if payment.fx_rate_used else None,
                    'fx_rate_issue_source': payment.fx_rate_source,
                    'fx_rate_issue_timestamp': payment.fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if payment.fx_rate_timestamp else None,
                    'fx_rate_cash': None,  # المدفوعات ليس لها سعر صرف منفصل للصرف
                    'fx_rate_cash_source': None,
                    'fx_rate_cash_timestamp': None,
                    'direction': 'وارد' if is_incoming else 'صادر',
                    'direction_en': 'in' if is_incoming else 'out',
                    'is_incoming': is_incoming,
                    'status': check_status,
                    'status_ar': status_ar,
                    'badge_color': badge_color,
                    'days_until_due': days_until_due,
                    'entity_name': entity_name,
                    'entity_type': entity_type,
                    'entity_link': entity_link,
                    'drawer_name': entity_name if not is_incoming else 'شركتنا',
                    'payee_name': 'شركتنا' if not is_incoming else entity_name,
                    'description': f"دفعة {'من' if is_incoming else 'إلى'} {entity_name}" + (f" ({entity_type})" if entity_type else ''),
                    'purpose': 'دفعة مالية',
                    'notes': payment.notes or '',
                    'created_at': payment.payment_date.strftime('%Y-%m-%d %H:%M') if payment.payment_date else '',
                    'receipt_number': payment.receipt_number or '',
                    'reference': payment.receipt_number or ''
                })
            
            current_app.logger.info(f"📊 Payments بدون splits: {len(checks)} شيك حتى الآن")
            
            # معالجة الدفعات الجزئية (PaymentSplit)
            # ⚠️ PaymentSplit.method هو enum، نستخدم == PaymentMethod.CHEQUE مباشرة
            payment_splits = PaymentSplit.query.filter(
                PaymentSplit.method == PaymentMethod.CHEQUE
            ).all()
            
            current_app.logger.info(f"📊 PaymentSplits (CHEQUE): {len(payment_splits)}")
            
            for split in payment_splits:
                payment = split.payment
                if not payment:
                    continue
                
                    # استخراج معلومات الشيك من details
                    details = split.details or {}
                    check_number = details.get('check_number', '')
                    check_bank = details.get('check_bank', '')
                    check_due_date_str = details.get('check_due_date', '')
                    
                    if not check_due_date_str:
                        continue
                    
                    try:
                        if isinstance(check_due_date_str, str):
                            check_due_date = datetime.fromisoformat(check_due_date_str).date()
                        elif isinstance(check_due_date_str, datetime):
                            check_due_date = check_due_date_str.date()
                        else:
                            check_due_date = check_due_date_str
                    except:
                        continue
                    
                    days_until_due = (check_due_date - today).days
                    
                    # تحديد الحالة
                    if payment.status == PaymentStatus.COMPLETED.value:
                        check_status = 'CASHED'
                        status_ar = 'تم الصرف'
                        badge_color = 'success'
                    elif payment.status == PaymentStatus.FAILED.value:
                        notes_lower = (payment.notes or '').lower()
                        if 'مرتجع' in notes_lower or 'returned' in notes_lower:
                            check_status = 'RETURNED'
                            status_ar = 'مرتجع'
                            badge_color = 'warning'
                        else:
                            check_status = 'BOUNCED'
                            status_ar = 'مرفوض'
                            badge_color = 'danger'
                    elif payment.status == PaymentStatus.CANCELLED.value:
                        check_status = 'CANCELLED'
                        status_ar = 'ملغي'
                        badge_color = 'secondary'
                    elif days_until_due < 0:
                        check_status = 'OVERDUE'
                        status_ar = 'متأخر'
                        badge_color = 'danger'
                    elif days_until_due <= 7:
                        check_status = 'due_soon'
                        status_ar = 'قريب الاستحقاق'
                        badge_color = 'warning'
                    else:
                        check_status = 'PENDING'
                        status_ar = 'معلق'
                        badge_color = 'info'
                    
                    # تحديد نوع الشيك
                    is_incoming = payment.direction == PaymentDirection.IN.value
                    
                    # ⭐ ربط ذكي بالجهة من الدفعة الأصلية
                    entity_name = ''
                    entity_link = ''
                    entity_type = ''
                    drawer_name = ''
                    payee_name = ''
                    
                    if payment.customer:
                        entity_name = payment.customer.name
                        entity_link = f'/customers/{payment.customer.id}'
                        entity_type = 'عميل'
                        # إذا وارد: العميل هو الساحب، نحن المستفيد
                        if is_incoming:
                            drawer_name = payment.customer.name
                            payee_name = 'شركتنا'
                        else:
                            drawer_name = 'شركتنا'
                            payee_name = payment.customer.name
                            
                    elif payment.supplier:
                        entity_name = payment.supplier.name
                        entity_link = f'/vendors/{payment.supplier.id}'
                        entity_type = 'مورد'
                        # إذا صادر: نحن الساحب، المورد المستفيد
                        if is_incoming:
                            drawer_name = payment.supplier.name
                            payee_name = 'شركتنا'
                        else:
                            drawer_name = 'شركتنا'
                            payee_name = payment.supplier.name
                            
                    elif payment.partner:
                        entity_name = payment.partner.name
                        entity_link = f'/partners/{payment.partner.id}'
                        entity_type = 'شريك'
                        if is_incoming:
                            drawer_name = payment.partner.name
                            payee_name = 'شركتنا'
                        else:
                            drawer_name = 'شركتنا'
                            payee_name = payment.partner.name
                    
                    # تجنب التكرار
                    check_key = f"split-{split.id}"
                    if check_key in check_ids:
                        continue
                    check_ids.add(check_key)
                    
                    checks.append({
                        'id': f"split-{split.id}",
                        'payment_id': payment.id,
                        'split_id': split.id,
                        'type': 'payment_split',
                        'source': 'دفعة جزئية',
                        'source_badge': 'info',
                        'check_number': check_number,
                        'check_bank': check_bank,
                        'check_due_date': check_due_date.strftime('%Y-%m-%d'),
                        'due_date_formatted': check_due_date.strftime('%d/%m/%Y'),
                        'amount': float(split.amount or 0),
                        'currency': payment.currency or 'ILS',
                        'fx_rate_issue': float(payment.fx_rate_used) if payment.fx_rate_used else None,
                        'fx_rate_issue_source': payment.fx_rate_source,
                        'fx_rate_issue_timestamp': payment.fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if payment.fx_rate_timestamp else None,
                        'fx_rate_cash': None,
                        'fx_rate_cash_source': None,
                        'fx_rate_cash_timestamp': None,
                        'direction': 'وارد' if is_incoming else 'صادر',
                        'direction_en': 'in' if is_incoming else 'out',
                        'is_incoming': is_incoming,
                        'status': check_status,
                        'status_ar': status_ar,
                        'badge_color': badge_color,
                        'days_until_due': days_until_due,
                        'entity_name': entity_name,
                        'entity_type': entity_type,
                        'entity_link': entity_link,
                    'drawer_name': drawer_name,
                    'payee_name': payee_name,
                        'notes': payment.notes or '',
                        'created_at': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else '',
                    'receipt_number': payment.payment_number or '',
                    'reference': payment.reference or ''
                    })
        
        # 2. جلب الشيكات من Expense
        if not source_filter or source_filter in ['all', 'expense']:
            expense_checks = Expense.query.filter(
                Expense.payment_method == 'cheque'
            )
        
        if from_date:
            try:
                from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                expense_checks = expense_checks.filter(Expense.check_due_date >= from_dt)
            except:
                pass
        
        if to_date:
            try:
                to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                expense_checks = expense_checks.filter(Expense.check_due_date <= to_dt)
            except:
                pass
            
            # معالجة شيكات Expense
            for expense in expense_checks.all():
                if not expense.check_due_date:
                    continue
                
                due_date = expense.check_due_date.date() if isinstance(expense.check_due_date, datetime) else expense.check_due_date
                days_until_due = (due_date - today).days
                
                # تحديد الحالة (المصروفات دائماً صادرة)
                is_paid = expense.is_paid if hasattr(expense, 'is_paid') else False
                notes_lower = (expense.notes or '').lower()
                
                if is_paid:
                    check_status = 'CASHED'
                    status_ar = 'تم الصرف'
                    badge_color = 'success'
                elif 'مرتجع' in notes_lower or 'returned' in notes_lower:
                    check_status = 'RETURNED'
                    status_ar = 'مرتجع'
                    badge_color = 'warning'
                elif 'مرفوض' in notes_lower or 'bounced' in notes_lower:
                    check_status = 'BOUNCED'
                    status_ar = 'مرفوض'
                    badge_color = 'danger'
                elif 'ملغي' in notes_lower or 'cancelled' in notes_lower:
                    check_status = 'CANCELLED'
                    status_ar = 'ملغي'
                    badge_color = 'secondary'
                elif days_until_due < 0:
                    check_status = 'OVERDUE'
                    status_ar = 'متأخر'
                    badge_color = 'danger'
                elif days_until_due <= 7:
                    check_status = 'due_soon'
                    status_ar = 'قريب الاستحقاق'
                    badge_color = 'warning'
                else:
                    check_status = 'PENDING'
                    status_ar = 'معلق'
                    badge_color = 'info'
                
                # تجنب التكرار
                check_key = f"expense-{expense.id}"
                if check_key in check_ids:
                    continue
                check_ids.add(check_key)
                
                checks.append({
                    'id': expense.id,
                    'type': 'expense',
                    'source': 'مصروف',
                    'source_badge': 'danger',
                    'check_number': expense.check_number or '',
                    'check_bank': expense.check_bank or '',
                    'check_due_date': due_date.strftime('%Y-%m-%d'),
                    'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                    'amount': float(expense.amount or 0),
                    'currency': expense.currency or 'ILS',
                    'fx_rate_issue': float(expense.fx_rate_used) if expense.fx_rate_used else None,
                    'fx_rate_issue_source': expense.fx_rate_source,
                    'fx_rate_issue_timestamp': expense.fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if expense.fx_rate_timestamp else None,
                    'fx_rate_cash': None,
                    'fx_rate_cash_source': None,
                    'fx_rate_cash_timestamp': None,
                    'direction': 'صادر',
                    'direction_en': 'out',
                    'is_incoming': False,
                    'status': check_status,
                    'status_ar': status_ar,
                    'badge_color': badge_color,
                    'days_until_due': days_until_due,
                    'entity_name': expense.paid_to or expense.payee_name or '',
                    'entity_type': 'مصروف',
                    'entity_link': '',
                    'notes': expense.description or '',
                    'created_at': expense.date.strftime('%Y-%m-%d') if expense.date else '',
                    'receipt_number': expense.tax_invoice_number or ''
                })
        
        # 3. جلب الشيكات اليدوية (Independent Checks)
        if not source_filter or source_filter in ['all', 'manual']:
            manual_checks_query = Check.query
            
            # فلتر حسب الاتجاه
            if direction == 'in':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.OUT.value)
            
            # فلتر حسب الحالة
            if status == 'pending':
                manual_checks_query = manual_checks_query.filter(Check.status == CheckStatus.PENDING.value)
            elif status == 'completed':
                manual_checks_query = manual_checks_query.filter(Check.status == CheckStatus.CASHED.value)
            elif status == 'overdue':
                manual_checks_query = manual_checks_query.filter(
                    and_(
                        Check.status == CheckStatus.PENDING.value,
                        Check.check_due_date < datetime.utcnow()
                    )
                )
            
            # فلتر حسب التاريخ
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date >= from_dt)
                except:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date <= to_dt)
                except:
                    pass
            
            # معالجة الشيكات اليدوية
            for check in manual_checks_query.all():
                due_date = check.check_due_date.date() if isinstance(check.check_due_date, datetime) else check.check_due_date
                days_until_due = (due_date - today).days
                
                # تحديد الحالة
                status_info = CHECK_STATUS.get(check.status, {'ar': check.status, 'color': 'secondary'})
                
                # تحديد الجهة
                entity_name = ''
                entity_type = ''
                entity_link = ''
                if check.customer:
                    entity_name = check.customer.name
                    entity_type = 'عميل'
                    entity_link = f'/customers/{check.customer.id}'
                elif check.supplier:
                    entity_name = check.supplier.name
                    entity_type = 'مورد'
                    entity_link = f'/vendors/{check.supplier.id}'
                elif check.partner:
                    entity_name = check.partner.name
                    entity_type = 'شريك'
                    entity_link = f'/partners/{check.partner.id}'
                elif check.direction == PaymentDirection.IN.value:
                    entity_name = check.drawer_name or 'غير محدد'
                    entity_type = 'ساحب'
                else:
                    entity_name = check.payee_name or 'غير محدد'
                    entity_type = 'مستفيد'
                
                # تجنب التكرار
                check_key = f"check-{check.id}"
                if check_key in check_ids:
                    continue
                check_ids.add(check_key)
                
                checks.append({
                    'id': check.id,
                    'type': 'manual',
                    'source': 'يدوي',
                    'source_badge': 'success',
                    'check_number': check.check_number,
                    'check_bank': check.check_bank,
                    'check_due_date': due_date.strftime('%Y-%m-%d'),
                    'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                    'amount': float(check.amount),
                    'currency': check.currency,
                    'fx_rate_issue': float(check.fx_rate_issue) if check.fx_rate_issue else None,
                    'fx_rate_issue_source': check.fx_rate_issue_source,
                    'fx_rate_issue_timestamp': check.fx_rate_issue_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_issue_timestamp else None,
                    'fx_rate_cash': float(check.fx_rate_cash) if check.fx_rate_cash else None,
                    'fx_rate_cash_source': check.fx_rate_cash_source,
                    'fx_rate_cash_timestamp': check.fx_rate_cash_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_cash_timestamp else None,
                    'direction': 'وارد' if check.direction == PaymentDirection.IN.value else 'صادر',
                    'direction_en': check.direction.lower(),
                    'is_incoming': check.direction == PaymentDirection.IN.value,
                    'status': check.status,
                    'status_ar': status_info['ar'],
                    'badge_color': status_info['color'],
                    'days_until_due': days_until_due,
                    'entity_name': entity_name,
                    'entity_type': entity_type,
                    'entity_link': entity_link,
                    'notes': check.notes or '',
                    'created_at': check.created_at.strftime('%Y-%m-%d') if check.created_at else '',
                    'receipt_number': check.reference_number or ''
                })
        
        # ترتيب حسب تاريخ الاستحقاق
        checks.sort(key=lambda x: x['check_due_date'])
        
        return jsonify({
            'success': True,
            'checks': checks,
            'total': len(checks)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching checks: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/statistics')
@login_required
def get_statistics():
    """
    API للحصول على إحصائيات الشيكات
    """
    try:
        today = datetime.utcnow().date()
        week_ahead = today + timedelta(days=7)
        month_ahead = today + timedelta(days=30)
        
        # 1. الشيكات الواردة
        incoming_total = db.session.query(db.func.sum(Payment.total_amount)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).scalar() or 0
        
        incoming_overdue = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date < datetime.utcnow()
            )
        ).scalar() or 0
        
        incoming_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).scalar() or 0
        
        # 2. الشيكات الصادرة (من Payment)
        outgoing_total = db.session.query(db.func.sum(Payment.total_amount)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).scalar() or 0
        
        outgoing_overdue = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date < datetime.utcnow()
            )
        ).scalar() or 0
        
        outgoing_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).scalar() or 0
        
        # 3. الشيكات الصادرة (من Expense)
        expense_total = db.session.query(db.func.sum(Expense.amount)).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.isnot(None),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).scalar() or 0
        
        expense_overdue = db.session.query(db.func.count(Expense.id)).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date < datetime.utcnow(),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).scalar() or 0
        
        expense_this_week = db.session.query(db.func.count(Expense.id)).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time())),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).scalar() or 0
        
        # إجمالي الصادر
        total_outgoing_value = float(outgoing_total or 0) + float(expense_total or 0)
        total_outgoing_overdue = outgoing_overdue + expense_overdue
        total_outgoing_this_week = outgoing_this_week + expense_this_week
        
        return jsonify({
            'success': True,
            'statistics': {
                'incoming': {
                    'total_amount': float(incoming_total or 0),
                    'overdue_count': incoming_overdue,
                    'this_week_count': incoming_this_week
                },
                'outgoing': {
                    'total_amount': total_outgoing_value,
                    'overdue_count': total_outgoing_overdue,
                    'this_week_count': total_outgoing_this_week
                }
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check statistics: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/check-lifecycle/<int:check_id>/<check_type>')
# @permission_required('view_payments')  # Commented out
def get_check_lifecycle(check_id, check_type):
    """
    الحصول على دورة حياة الشيك الكاملة
    """
    try:
        if check_type == 'payment':
            check = Payment.query.get_or_404(check_id)
        else:
            check = Expense.query.get_or_404(check_id)
        
        # استخراج جميع التغييرات من الملاحظات
        notes = check.notes or ''
        lifecycle_events = []
        
        for line in notes.split('\n'):
            if '[' in line and ']' in line:
                lifecycle_events.append({
                    'timestamp': line[line.find('[')+1:line.find(']')],
                    'description': line[line.find(']')+1:].strip()
                })
        
        # إضافة الحدث الأولي (الإنشاء)
        lifecycle_events.insert(0, {
            'timestamp': check.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(check, 'created_at') else 'غير محدد',
            'description': f'إنشاء الشيك رقم {check.check_number or "N/A"} - البنك: {check.check_bank or "N/A"} - المبلغ: {check.amount} {getattr(check, "currency", "ILS")}'
        })
        
        return jsonify({
            'success': True,
            'lifecycle': lifecycle_events,
            'current_status': get_current_check_status(check, check_type)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check lifecycle: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_current_check_status(check, check_type):
    """تحديد الحالة الحالية للشيك"""
    if check_type == 'payment':
        if check.status == PaymentStatus.COMPLETED.value:
            return 'CASHED'
        elif check.status == PaymentStatus.FAILED.value:
            notes_lower = (check.notes or '').lower()
            if 'مرتجع' in notes_lower or 'returned' in notes_lower:
                if 'أعيد' in notes_lower or 'resubmitted' in notes_lower:
                    return 'RESUBMITTED'
                return 'RETURNED'
            return 'BOUNCED'
        elif check.status == PaymentStatus.CANCELLED.value:
            return 'CANCELLED'
        return 'PENDING'
    else:
        is_paid = getattr(check, 'is_paid', False)
        notes_lower = (check.notes or '').lower()
        
        if is_paid:
            return 'CASHED'
        elif 'أعيد' in notes_lower or 'resubmitted' in notes_lower:
            return 'RESUBMITTED'
        elif 'مرتجع' in notes_lower or 'returned' in notes_lower:
            return 'RETURNED'
        elif 'مرفوض' in notes_lower or 'bounced' in notes_lower:
            return 'BOUNCED'
        elif 'ملغي' in notes_lower or 'cancelled' in notes_lower:
            return 'CANCELLED'
        return 'PENDING'


@checks_bp.route('/api/update-status/<check_id>', methods=['POST'])
@login_required
def update_check_status(check_id):
    """
    تحديث حالة الشيك (من جميع المصادر)
    """
    try:
        # الحصول على البيانات من JSON
        data = request.get_json() or {}
        new_status = data.get('status')  # CASHED, RETURNED, BOUNCED, CANCELLED, RESUBMITTED
        notes = data.get('notes', '')
        
        # تحديد نوع الشيك من الـ ID
        check_type = 'check'  # default
        actual_id = check_id
        
        current_app.logger.info(f"🔍 تحليل check_id: {check_id}")
        
        if isinstance(check_id, str):
            if check_id.startswith('split-'):
                check_type = 'split'
                actual_id = int(check_id.replace('split-', ''))
                current_app.logger.info(f"✅ تم التعرف: PaymentSplit ID={actual_id}")
            elif check_id.startswith('expense-'):
                check_type = 'expense'
                actual_id = int(check_id.replace('expense-', ''))
                current_app.logger.info(f"✅ تم التعرف: Expense ID={actual_id}")
            elif check_id.isdigit():
                # رقم فقط - نحتاج لفحص نوعه
                actual_id = int(check_id)
                # نفحص في جميع الجداول
                if Check.query.get(actual_id):
                    check_type = 'check'
                    current_app.logger.info(f"✅ تم التعرف: Check (Manual) ID={actual_id}")
                elif Payment.query.get(actual_id):
                    check_type = 'payment'
                    current_app.logger.info(f"✅ تم التعرف: Payment ID={actual_id}")
                else:
                    # افتراض أنه شيك يدوي
                    check_type = 'check'
                    current_app.logger.warning(f"⚠️  افتراض Check ID={actual_id}")
            else:
                # غير معروف
                current_app.logger.warning(f"⚠️  check_id غير معروف: {check_id}")
                check_type = 'check'
                actual_id = int(check_id) if check_id.isdigit() else check_id
        else:
            actual_id = int(check_id)
            # نفحص النوع
            if Check.query.get(actual_id):
                check_type = 'check'
            elif Payment.query.get(actual_id):
                check_type = 'payment'
            else:
                check_type = 'check'
            current_app.logger.info(f"✅ تم التعرف: {check_type.upper()} ID={actual_id}")
        
        if not new_status:
            return jsonify({
                'success': False,
                'message': 'بيانات ناقصة'
            }), 400
        
        # التحقق من الحالة المسموحة
        allowed_statuses = ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED', 'RESUBMITTED', 'ARCHIVED', 'PENDING']
        if new_status not in allowed_statuses:
            return jsonify({
                'success': False,
                'message': 'حالة غير صالحة'
            }), 400
        
        if check_type == 'payment' or check_type == 'split':
            if check_type == 'split':
                # جلب الدفعة الجزئية
                split = PaymentSplit.query.get_or_404(actual_id)
                check = split.payment
            else:
                check = Payment.query.get_or_404(actual_id)
            
            # إضافة ملاحظة مفصلة بدون تغيير حالة Payment
            # حالة Payment تبقى كما هي، ونسجل فقط حالة الشيك في الملاحظات
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            # إضافة أيقونة حسب الحالة
            status_icons = {
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'RESUBMITTED': '🔁',
                'CANCELLED': '⛔',
                'ARCHIVED': '📦',
                'PENDING': '⏳'
            }
            icon = status_icons.get(new_status, '🔄')
            
            status_note = f"\n[{timestamp}] {icon} حالة الشيك: {CHECK_STATUS[new_status]['ar']}"
            
            if notes:
                status_note += f"\n   💬 {notes}"
            if current_user:
                status_note += f"\n   👤 {current_user.username}"
            
            check.notes = (check.notes or '') + status_note
            
            # تحديث حالة Payment فقط للحالات المهمة
            if new_status == 'CASHED':
                # فقط إذا كانت الحالة الحالية PENDING
                if check.status == PaymentStatus.PENDING:
                    check.status = PaymentStatus.COMPLETED
            elif new_status == 'CANCELLED':
                # فقط إذا كانت الحالة الحالية PENDING
                if check.status == PaymentStatus.PENDING:
                    check.status = PaymentStatus.CANCELLED
            
            # إنشاء قيد محاسبي في دفتر الأستاذ
            try:
                entity_name = ''
                if check.customer:
                    entity_name = check.customer.name
                elif check.supplier:
                    entity_name = check.supplier.name
                elif check.partner:
                    entity_name = check.partner.name
                
                create_gl_entry_for_check(
                    check_id=actual_id,
                    check_type=check_type,
                    amount=float(check.total_amount or 0),
                    currency=check.currency or 'ILS',
                    direction='IN' if check.direction == PaymentDirection.IN else 'OUT',
                    new_status=new_status,
                    entity_name=entity_name,
                    notes=notes or ''
                )
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي: {str(e)}")
            
        elif check_type == 'expense':
            check = Expense.query.get_or_404(actual_id)
            
            # تحديث الملاحظات
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            status_icons = {
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'RESUBMITTED': '🔁',
                'CANCELLED': '⛔',
                'ARCHIVED': '📦'
            }
            icon = status_icons.get(new_status, '🔄')
            
            status_note = f"\n[{timestamp}] {icon} حالة الشيك: {CHECK_STATUS[new_status]['ar']}"
            if notes:
                status_note += f"\n   💬 {notes}"
            if current_user:
                status_note += f"\n   👤 {current_user.username}"
            
            check.notes = (check.notes or '') + status_note
            
            # إنشاء قيد محاسبي
            try:
                entity_name = check.supplier.name if check.supplier else ''
                
                create_gl_entry_for_check(
                    check_id=actual_id,
                    check_type='expense',
                    amount=float(check.amount or 0),
                    currency='ILS',
                    direction='OUT',
                    new_status=new_status,
                    entity_name=entity_name,
                    notes=notes or ''
                )
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للنفقة: {str(e)}")
        
        elif check_type == 'check':
            # شيك يدوي من جدول Check
            manual_check = Check.query.get_or_404(actual_id)
            manual_check.status = new_status
            
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            status_icons = {
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'RESUBMITTED': '🔁',
                'CANCELLED': '⛔',
                'ARCHIVED': '📦',
                'PENDING': '⏳'
            }
            icon = status_icons.get(new_status, '🔄')
            
            status_note = f"\n[{timestamp}] {icon} حالة الشيك: {CHECK_STATUS[new_status]['ar']}"
            if notes:
                status_note += f"\n   💬 {notes}"
            if current_user:
                status_note += f"\n   👤 {current_user.username}"
            
            manual_check.notes = (manual_check.notes or '') + status_note
            
            # إنشاء قيد محاسبي للشيكات اليدوية أيضاً
            try:
                entity_name = ''
                if manual_check.drawer_name:
                    entity_name = manual_check.drawer_name
                elif manual_check.payee_name:
                    entity_name = manual_check.payee_name
                
                create_gl_entry_for_check(
                    check_id=actual_id,
                    check_type='check',
                    amount=float(manual_check.amount or 0),
                    currency=manual_check.currency or 'ILS',
                    direction='IN' if manual_check.direction.value == 'IN' else 'OUT',
                    new_status=new_status,
                    entity_name=entity_name,
                    notes=notes or ''
                )
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للشيك اليدوي: {str(e)}")
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث حالة الشيك بنجاح'
            })
        
        # حفظ التغييرات
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم تحديث حالة الشيك إلى: {CHECK_STATUS[new_status]["ar"]}',
            'new_status': new_status,
            'new_status_ar': CHECK_STATUS[new_status]['ar']
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating check status: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/alerts')
@login_required
def get_alerts():
    """
    API للحصول على التنبيهات
    """
    try:
        today = datetime.utcnow().date()
        week_ahead = today + timedelta(days=7)
        
        alerts = []
        
        # 1. الشيكات المتأخرة
        overdue_checks = Payment.query.filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date < datetime.utcnow()
            )
        ).all()
        
        for check in overdue_checks:
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            
            direction_ar = 'وارد' if check.direction == PaymentDirection.IN.value else 'صادر'
            days_overdue = (today - check.check_due_date.date()).days
            
            alerts.append({
                'type': 'overdue',
                'severity': 'danger',
                'icon': 'fas fa-exclamation-circle',
                'title': f'شيك {direction_ar} متأخر',
                'message': f'شيك رقم {check.check_number} من {entity_name} متأخر {days_overdue} يوم',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_overdue,
                'link': f'/checks?id={check.id}'
            })
        
        # 2. الشيكات المستحقة هذا الأسبوع
        due_soon_checks = Payment.query.filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).all()
        
        for check in due_soon_checks:
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            
            direction_ar = 'وارد' if check.direction == PaymentDirection.IN.value else 'صادر'
            days_until = (check.check_due_date.date() - today).days
            
            alerts.append({
                'type': 'due_soon',
                'severity': 'warning',
                'icon': 'fas fa-clock',
                'title': f'شيك {direction_ar} قريب الاستحقاق',
                'message': f'شيك رقم {check.check_number} من {entity_name} يستحق خلال {days_until} يوم',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_until,
                'link': f'/checks?id={check.id}'
            })
        
        # ترتيب: المتأخر أولاً، ثم حسب تاريخ الاستحقاق
        alerts.sort(key=lambda x: (x['type'] != 'overdue', x['days']))
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'count': len(alerts)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check alerts: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



# ==========================================
# الشيكات المستقلة (Independent Checks)
# ==========================================

@checks_bp.route("/new", methods=["GET", "POST"])
@login_required
# @permission_required("manage_payments")  # Commented out
def add_check():
    """إضافة شيك يدوي جديد"""
    if request.method == "POST":
        try:
            check_number = request.form.get("check_number")
            check_bank = request.form.get("check_bank")
            check_date_str = request.form.get("check_date")
            check_due_date_str = request.form.get("check_due_date")
            amount = Decimal(request.form.get("amount", 0))
            currency = request.form.get("currency", "ILS")
            direction = request.form.get("direction")
            
            drawer_name = request.form.get("drawer_name")
            drawer_phone = request.form.get("drawer_phone")
            drawer_id_number = request.form.get("drawer_id_number")
            drawer_address = request.form.get("drawer_address")
            payee_name = request.form.get("payee_name")
            payee_phone = request.form.get("payee_phone")
            payee_account = request.form.get("payee_account")
            
            notes = request.form.get("notes")
            internal_notes = request.form.get("internal_notes")
            reference_number = request.form.get("reference_number")
            
            customer_id = request.form.get("customer_id") or None
            supplier_id = request.form.get("supplier_id") or None
            partner_id = request.form.get("partner_id") or None
            
            if not check_number or not check_bank or not amount or not direction:
                flash("يرجى ملء جميع الحقول المطلوبة", "danger")
                return redirect(url_for("checks.add_check"))
            
            check_date = datetime.strptime(check_date_str, "%Y-%m-%d") if check_date_str else datetime.utcnow()
            check_due_date = datetime.strptime(check_due_date_str, "%Y-%m-%d") if check_due_date_str else datetime.utcnow()
            
            new_check = Check(
                check_number=check_number,
                check_bank=check_bank,
                check_date=check_date,
                check_due_date=check_due_date,
                amount=amount,
                currency=currency,
                direction=direction,
                status=CheckStatus.PENDING.value,
                drawer_name=drawer_name,
                drawer_phone=drawer_phone,
                drawer_id_number=drawer_id_number,
                drawer_address=drawer_address,
                payee_name=payee_name,
                payee_phone=payee_phone,
                payee_account=payee_account,
                notes=notes,
                internal_notes=internal_notes,
                reference_number=reference_number,
                customer_id=int(customer_id) if customer_id else None,
                supplier_id=int(supplier_id) if supplier_id else None,
                partner_id=int(partner_id) if partner_id else None,
                created_by_id=current_user.id
            )
            
            db.session.add(new_check)
            db.session.commit()
            
            flash(f"تم إضافة الشيك رقم {check_number} بنجاح", "success")
            return redirect(url_for("checks.index"))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding check: {str(e)}")
            flash(f"حدث خطأ أثناء إضافة الشيك: {str(e)}", "danger")
            return redirect(url_for("checks.add_check"))
    
    # جلب العملاء النشطين فقط (is_active=True, is_archived=False)
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).all()
    # جلب الموردين والشركاء (لا يوجد حقل deleted)
    suppliers = Supplier.query.order_by(Supplier.name).all()
    partners = Partner.query.order_by(Partner.name).all()
    
    return render_template("checks/form.html",
                         customers=customers,
                         suppliers=suppliers,
                         partners=partners,
                         check=None,
                         currencies=["ILS", "USD", "EUR", "JOD"])


@checks_bp.route("/edit/<int:check_id>", methods=["GET", "POST"])
@login_required
# @permission_required("manage_payments")  # Commented out
def edit_check(check_id):
    """تعديل شيك"""
    check = Check.query.get_or_404(check_id)
    
    if request.method == "POST":
        try:
            check.check_number = request.form.get("check_number")
            check.check_bank = request.form.get("check_bank")
            check.check_date = datetime.strptime(request.form.get("check_date"), "%Y-%m-%d")
            check.check_due_date = datetime.strptime(request.form.get("check_due_date"), "%Y-%m-%d")
            check.amount = Decimal(request.form.get("amount", 0))
            check.currency = request.form.get("currency", "ILS")
            check.direction = request.form.get("direction")
            
            check.drawer_name = request.form.get("drawer_name")
            check.drawer_phone = request.form.get("drawer_phone")
            check.drawer_id_number = request.form.get("drawer_id_number")
            check.drawer_address = request.form.get("drawer_address")
            check.payee_name = request.form.get("payee_name")
            check.payee_phone = request.form.get("payee_phone")
            check.payee_account = request.form.get("payee_account")
            
            check.notes = request.form.get("notes")
            check.internal_notes = request.form.get("internal_notes")
            check.reference_number = request.form.get("reference_number")
            
            customer_id = request.form.get("customer_id")
            supplier_id = request.form.get("supplier_id")
            partner_id = request.form.get("partner_id")
            
            check.customer_id = int(customer_id) if customer_id else None
            check.supplier_id = int(supplier_id) if supplier_id else None
            check.partner_id = int(partner_id) if partner_id else None
            
            db.session.commit()
            
            flash(f"تم تعديل الشيك رقم {check.check_number} بنجاح", "success")
            return redirect(url_for("checks.check_detail", check_id=check.id))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating check: {str(e)}")
            flash(f"حدث خطأ أثناء تعديل الشيك: {str(e)}", "danger")
    
    # جلب العملاء النشطين فقط (is_active=True, is_archived=False)
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).all()
    # جلب الموردين والشركاء (لا يوجد حقل deleted)
    suppliers = Supplier.query.order_by(Supplier.name).all()
    partners = Partner.query.order_by(Partner.name).all()
    
    return render_template("checks/form.html",
                         check=check,
                         customers=customers,
                         suppliers=suppliers,
                         partners=partners,
                         currencies=["ILS", "USD", "EUR", "JOD"])


@checks_bp.route("/detail/<int:check_id>")
@login_required
# @permission_required("view_payments")  # Commented out
def check_detail(check_id):
    """عرض تفاصيل شيك"""
    check = Check.query.get_or_404(check_id)
    status_history = check.get_status_history()
    
    return render_template("checks/detail.html",
                         check=check,
                         status_history=status_history,
                         CHECK_STATUS=CHECK_STATUS)


@checks_bp.route("/delete/<int:check_id>", methods=["POST"])
@login_required
# @permission_required("manage_payments")  # Commented out
def delete_check(check_id):
    """حذف شيك"""
    try:
        check = Check.query.get_or_404(check_id)
        check_number = check.check_number
        
        db.session.delete(check)
        db.session.commit()
        
        flash(f"تم حذف الشيك رقم {check_number} بنجاح", "success")
        return redirect(url_for("checks.index"))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting check: {str(e)}")
        flash(f"حدث خطأ أثناء حذف الشيك: {str(e)}", "danger")
        return redirect(url_for("checks.index"))


@checks_bp.route("/reports")
@login_required
def reports():
    """صفحة التقارير - من جميع المصادر"""
    today = datetime.utcnow().date()
    
    # جلب جميع الشيكات من API (جميع المصادر)
    all_checks_response = get_checks()
    all_checks_data = all_checks_response.get_json()
    all_checks = all_checks_data.get('checks', []) if all_checks_data.get('success') else []
    
    current_app.logger.info(f"📊 التقارير - عدد الشيكات: {len(all_checks)}")
    
    # الشيكات اليدوية فقط
    independent_checks = Check.query.all()
    
    # إحصائيات حسب الحالة (من جميع المصادر) - بما فيها الحالات من الملاحظات
    stats_by_status = {}
    for check in all_checks:
        status = check.get('status', 'UNKNOWN')
        original_status = status  # للـ logging
        
        # فحص الملاحظات لاكتشاف الحالة الفعلية
        notes = (check.get('notes', '') or '').lower()
        if 'حالة الشيك: مسحوب' in notes or 'حالة الشيك: تم الصرف' in notes:
            status = 'CASHED'
        elif 'حالة الشيك: مرتجع' in notes:
            status = 'RETURNED'
        elif 'حالة الشيك: ملغي' in notes:
            status = 'CANCELLED'
        elif 'حالة الشيك: أعيد للبنك' in notes:
            status = 'RESUBMITTED'
        elif 'حالة الشيك: مؤرشف' in notes:
            status = 'ARCHIVED'
        elif 'حالة الشيك: مرفوض' in notes:
            status = 'BOUNCED'
        
        if status not in stats_by_status:
            stats_by_status[status] = {'status': status, 'count': 0, 'total_amount': 0}
        stats_by_status[status]['count'] += 1
        stats_by_status[status]['total_amount'] += float(check.get('amount', 0))
    
    current_app.logger.info(f"📊 إحصائيات الحالات: {stats_by_status}")
    current_app.logger.info(f"📊 عدد الحالات المختلفة: {len(stats_by_status)}")
    
    # تحويل إلى list
    stats_by_status = list(stats_by_status.values())
    
    # إحصائيات حسب الاتجاه (من جميع المصادر)
    stats_by_direction = {'IN': {'direction': 'IN', 'count': 0, 'total_amount': 0},
                          'OUT': {'direction': 'OUT', 'count': 0, 'total_amount': 0}}
    
    for check in all_checks:
        direction = 'IN' if check.get('is_incoming') else 'OUT'
        stats_by_direction[direction]['count'] += 1
        stats_by_direction[direction]['total_amount'] += float(check.get('amount', 0))
    
    # تحويل إلى list
    stats_by_direction = list(stats_by_direction.values())
    
    # الشيكات المتأخرة (من جميع المصادر)
    overdue_checks = []
    due_soon_checks = []
    
    for c in all_checks:
        notes = (c.get('notes', '') or '').lower()
        actual_status = c.get('status', '').upper()
        
        # فحص الحالة الفعلية
        if 'حالة الشيك: مسحوب' in notes:
            continue  # مسحوب - تخطي
        elif 'حالة الشيك: ملغي' in notes or 'حالة الشيك: مؤرشف' in notes:
            continue  # ملغي/مؤرشف - تخطي
        elif 'حالة الشيك: مرتجع' in notes:
            continue  # مرتجع - تخطي
        
        # الآن نفحص إذا كان متأخر أو قريب
        if actual_status == 'OVERDUE':
            overdue_checks.append(c)
        elif actual_status == 'DUE_SOON':
            due_soon_checks.append(c)
    
    return render_template("checks/reports.html",
                         independent_checks=independent_checks,
                         all_checks=all_checks,
                         stats_by_status=stats_by_status,
                         stats_by_direction=stats_by_direction,
                         overdue_checks=overdue_checks,
                         due_soon_checks=due_soon_checks,
                         CheckStatus=CheckStatus,
                         PaymentDirection=PaymentDirection,
                         CHECK_STATUS=CHECK_STATUS)

