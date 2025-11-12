from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import current_user, login_required
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.orm import joinedload
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
def _check_gl_batch_reverse(mapper, connection, target):
    """إنشاء قيد عكسي عند حذف الشيك (أصح محاسبياً)"""
    try:
        if hasattr(target, '_skip_gl_reversal') and target._skip_gl_reversal:
            from sqlalchemy import text as sa_text
            connection.execute(
                sa_text("DELETE FROM gl_batches WHERE source_type = 'CHECK' AND source_id = :cid"),
                {"cid": target.id}
            )
            return
        
        amount = float(target.amount or 0)
        if amount <= 0:
            return
        
        from models import fx_rate, GL_ACCOUNTS, PAYMENT_GL_MAP
        
        amount_ils = amount
        if target.currency and target.currency != 'ILS':
            try:
                rate = fx_rate(target.currency, 'ILS', target.check_date or datetime.utcnow(), raise_on_missing=False)
                if rate and rate > 0:
                    amount_ils = float(amount * float(rate))
            except Exception:
                pass
        
        bank_account = GL_ACCOUNTS.get("BANK", "1010_BANK")
        ar_account = GL_ACCOUNTS.get("AR", "1100_AR")
        
        check_type = getattr(target, 'check_type', 'RECEIVED')
        if check_type == 'RECEIVED':
            entries = [(ar_account, amount_ils, 0), (bank_account, 0, amount_ils)]
        else:
            ap_account = GL_ACCOUNTS.get("AP", "2000_AP")
            entries = [(ap_account, 0, amount_ils), (bank_account, amount_ils, 0)]
        
        from models import _gl_upsert_batch_and_entries
        _gl_upsert_batch_and_entries(
            connection,
            source_type="CHECK_REVERSAL",
            source_id=target.id,
            purpose="REVERSAL",
            currency="ILS",
            memo=f"عكس قيد - حذف شيك #{target.check_number}",
            entries=entries,
            ref=f"REV-CHK-{target.id}",
            entity_type="OTHER",
            entity_id=None
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في عكس قيد الشيك #{target.id}: {e}", file=sys.stderr)


@event.listens_for(Payment, 'before_delete')
def _payment_check_before_delete(mapper, connection, target):
    try:
        if target.method == PaymentMethod.CHEQUE:
            connection.execute(
                GLBatch.__table__.delete().where(
                    (GLBatch.source_type == 'check_payment') & 
                    (GLBatch.source_id == target.id)
                )
            )
    except Exception as e:
        current_app.logger.error(f"خطأ في حذف القيود المحاسبية للدفعة {target.id}: {str(e)}")


@event.listens_for(GLBatch, 'before_delete')
def _glbatch_before_delete(mapper, connection, target):
    """عند حذف قيد محاسبي مرتبط بشيك، إلغاء الشيك تلقائياً"""
    try:
        source_type = target.source_type
        source_id = target.source_id
        
        if source_type == 'check_check':
            connection.execute(
                Check.__table__.update().where(Check.id == source_id).values(
                    status='CANCELLED',
                    notes=Check.notes + '\n⚠️ تم إلغاء الشيك بسبب حذف القيد المحاسبي'
                )
            )
        elif source_type == 'check_payment':
            connection.execute(
                Payment.__table__.update().where(Payment.id == source_id).values(
                    notes=Payment.notes + '\n⚠️ تم إلغاء الشيك بسبب حذف القيد المحاسبي'
                )
            )
    except Exception as e:
        current_app.logger.error(f"خطأ في إلغاء الشيك عند حذف القيد: {str(e)}")


def ensure_check_accounts():
    """التأكد من وجود جميع حسابات دفتر الأستاذ المطلوبة"""
    try:
        required_accounts = [
            ('1000_CASH', 'الصندوق', 'ASSET'),
            ('1010_BANK', 'البنك', 'ASSET'),
            ('1020_CARD_CLEARING', 'بطاقات الائتمان', 'ASSET'),
            ('1100_AR', 'العملاء (ذمم مدينة)', 'ASSET'),
            ('1150_CHEQUES_RECEIVABLE', 'شيكات تحت التحصيل', 'ASSET'),
            ('1205_INV_EXCHANGE', 'المخزون - تبادل', 'ASSET'),
            
            ('2000_AP', 'الموردين (ذمم دائنة)', 'LIABILITY'),
            ('2100_VAT_PAYABLE', 'ضريبة القيمة المضافة', 'LIABILITY'),
            ('2150_CHEQUES_PAYABLE', 'شيكات تحت الدفع', 'LIABILITY'),
            
            ('4000_SALES', 'المبيعات', 'REVENUE'),
            
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
        ensure_check_accounts()
        
        is_incoming = (direction == 'IN')
        amount_decimal = Decimal(str(amount))
        
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
        
        if new_status == 'CASHED':
            if is_incoming:
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
            if is_incoming:
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
        
        for entry in entries:
            db.session.add(entry)
        
        db.session.flush()
        
        current_app.logger.info(f"✅ تم إنشاء قيد محاسبي للشيك {check_id} - Batch: {batch_code}")
        return batch
        
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للشيك {check_id}: {str(e)}")
        db.session.rollback()
        return None

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

GL_ACCOUNTS_CHECKS = {
    'CHEQUES_RECEIVABLE': '1150_CHEQUES_RECEIVABLE',  # شيكات تحت التحصيل (أصول)
    'CHEQUES_PAYABLE': '2150_CHEQUES_PAYABLE',        # شيكات تحت الدفع (خصوم)
    'BANK': '1010_BANK',                               # البنك
    'CASH': '1000_CASH',                               # الصندوق
    'AR': '1100_AR',                                   # العملاء (Accounts Receivable)
    'AP': '2000_AP',                                   # الموردين (Accounts Payable)
}

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
        direction = request.args.get('direction')  # 'in' أو 'out' أو 'all'
        status = request.args.get('status')  # 'pending', 'completed', 'overdue', 'all'
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        source_filter = request.args.get('source')  # 'payment', 'expense', 'manual', 'all'
        
        checks = []
        today = datetime.utcnow().date()
        check_ids = set()  # لتتبع الـ IDs وتجنب التكرار

        current_app.logger.info(f"🔍 get_checks API - بدء الجلب من جميع المصادر...")
        
        if not source_filter or source_filter in ['all', 'payment']:
            parsed_from = None
            parsed_to = None
            if from_date:
                try:
                    parsed_from = datetime.strptime(from_date, '%Y-%m-%d').date()
                except Exception:
                    parsed_from = None
            if to_date:
                try:
                    parsed_to = datetime.strptime(to_date, '%Y-%m-%d').date()
                except Exception:
                    parsed_to = None

            def _extract_manual_status(notes_text: str | None) -> str | None:
                if not notes_text:
                    return None
                try:
                    lines = [ln.strip() for ln in notes_text.splitlines() if ln.strip()]
                except Exception:
                    lines = []
                for line in reversed(lines):
                    if 'حالة الشيك:' not in line:
                        continue
                    label = line.split('حالة الشيك:')[-1].strip()
                    if 'مسحوب' in label:
                        return 'CASHED'
                    if 'مرتجع' in label:
                        return 'RETURNED'
                    if 'ملغي' in label:
                        return 'CANCELLED'
                    if 'أعيد' in label or 'معاد' in label:
                        return 'RESUBMITTED'
                    if 'مؤرشف' in label:
                        return 'CANCELLED'
                return None

            def _status_snapshot(manual_status: str | None, status_value: str | None, due_days: int | None):
                manual = (manual_status or '').upper()
                if manual in {'RETURNED', 'BOUNCED'}:
                    return 'RETURNED', 'مرتجع', 'warning'
                if manual == 'CANCELLED':
                    return 'CANCELLED', 'ملغي', 'secondary'
                if manual == 'RESUBMITTED':
                    return 'RESUBMITTED', 'أعيد للبنك', 'info'
                if manual == 'ARCHIVED':
                    return 'CANCELLED', 'ملغي', 'secondary'
                if manual == 'CASHED':
                    if due_days is not None and due_days > 0:
                        # لم يحِن ميعاد الاستحقاق بعد
                        pass
                    else:
                        return 'CASHED', 'تم الصرف', 'success'

                if due_days is not None:
                    if due_days < 0:
                        return 'OVERDUE', 'متأخر', 'danger'
                    if due_days <= 7:
                        return 'DUE_SOON', 'قريب الاستحقاق', 'warning'
                return 'PENDING', 'معلق', 'info'

            def _resolve_entity(payment):
                if payment.customer:
                    name = payment.customer.name
                    return name, 'عميل', f"/customers/{payment.customer.id}"
                sale = getattr(payment, 'sale', None)
                if sale and getattr(sale, 'customer', None):
                    name = sale.customer.name
                    return name, 'عميل', f"/customers/{sale.customer.id}"
                invoice = getattr(payment, 'invoice', None)
                if invoice and getattr(invoice, 'customer', None):
                    name = invoice.customer.name
                    return name, 'عميل', f"/customers/{invoice.customer.id}"
                preorder = getattr(payment, 'preorder', None)
                if preorder and getattr(preorder, 'customer', None):
                    name = preorder.customer.name
                    return name, 'عميل', f"/customers/{preorder.customer.id}"
                service_request = getattr(payment, 'service', None)
                if service_request and getattr(service_request, 'customer', None):
                    name = service_request.customer.name
                    return name, 'عميل', f"/customers/{service_request.customer.id}"
                if payment.supplier:
                    name = payment.supplier.name
                    return name, 'مورد', f"/vendors/{payment.supplier.id}"
                if payment.partner:
                    name = payment.partner.name
                    return name, 'شريك', f"/partners/{payment.partner.id}"
                return '', '', ''

            def _split_due_date(payment, split):
                details = getattr(split, 'details', {}) or {}
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except Exception:
                        details = {}
                raw_val = details.get('check_due_date') or details.get('due_date')
                if raw_val:
                    try:
                        return datetime.fromisoformat(raw_val).date()
                    except Exception:
                        try:
                            return datetime.strptime(raw_val, '%Y-%m-%d').date()
                        except Exception:
                            return None
                if payment.check_due_date:
                    if isinstance(payment.check_due_date, datetime):
                        return payment.check_due_date.date()
                    return payment.check_due_date
                if payment.payment_date and isinstance(payment.payment_date, datetime):
                    return payment.payment_date.date()
                return None

            payment_query = db.session.query(Payment).options(
                joinedload(Payment.splits),
                joinedload(Payment.customer),
                joinedload(Payment.supplier),
                joinedload(Payment.partner),
                joinedload(Payment.sale),
                joinedload(Payment.invoice),
                joinedload(Payment.preorder),
                joinedload(Payment.service),
            )

            if direction == 'in':
                payment_query = payment_query.filter(Payment.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                payment_query = payment_query.filter(Payment.direction == PaymentDirection.OUT.value)

            if status == 'pending':
                payment_query = payment_query.filter(Payment.status == PaymentStatus.PENDING.value)
            elif status == 'completed':
                payment_query = payment_query.filter(Payment.status == PaymentStatus.COMPLETED.value)
            elif status == 'overdue':
                payment_query = payment_query.filter(
                    and_(
                        Payment.status == PaymentStatus.PENDING.value,
                        Payment.check_due_date < datetime.utcnow()
                    )
                )

            payments = payment_query.filter(
                or_(
                    Payment.method == PaymentMethod.CHEQUE.value,
                    Payment.splits.any(PaymentSplit.method == PaymentMethod.CHEQUE.value)
                )
            ).order_by(
                (Payment.check_due_date.is_(None)).asc(),
                Payment.check_due_date.asc(),
                Payment.payment_date.asc(),
                Payment.id.asc()
            ).all()

            processed_split_count = 0
            for payment in payments:
                entity_name, entity_type, entity_link = _resolve_entity(payment)
                status_value = payment.status.value if hasattr(payment.status, 'value') else str(payment.status or '')
                direction_value = payment.direction.value if hasattr(payment.direction, 'value') else str(payment.direction or '')
                is_incoming = direction_value == PaymentDirection.IN.value

                base_due = None
                if payment.check_due_date:
                    base_due = payment.check_due_date.date() if isinstance(payment.check_due_date, datetime) else payment.check_due_date
                elif payment.payment_date and isinstance(payment.payment_date, datetime):
                    base_due = payment.payment_date.date()

                manual_status = _extract_manual_status(payment.notes)

                if payment.method == PaymentMethod.CHEQUE.value:
                    due_date = base_due or today
                    days_until_due = (due_date - today).days if due_date else None
                    check_status, status_ar, badge_color = _status_snapshot(manual_status, status_value, days_until_due)

                    skip_entry = False
                    if parsed_from and due_date and due_date < parsed_from:
                        skip_entry = True
                    if parsed_to and due_date and due_date > parsed_to:
                        skip_entry = True
                    if status == 'pending' and check_status not in ('PENDING', 'due_soon'):
                        skip_entry = True
                    if status == 'completed' and check_status != 'CASHED':
                        skip_entry = True
                    if status == 'overdue' and check_status != 'OVERDUE':
                        skip_entry = True

                    if not skip_entry:
                        key = f"payment-{payment.id}"
                        if key in check_ids:
                            continue
                        check_ids.add(key)
                        checks.append({
                            'id': payment.id,
                            'type': 'payment',
                            'source': 'دفعة',
                            'source_badge': 'primary',
                            'check_number': payment.check_number or '',
                            'check_bank': payment.check_bank or '',
                            'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                            'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                            'amount': float(payment.total_amount or 0),
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
                            'days_until_due': days_until_due if days_until_due is not None else 0,
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

                for split in payment.splits or []:
                    split_method = getattr(split.method, 'value', split.method)
                    if split_method != PaymentMethod.CHEQUE.value:
                        continue

                    due_date = _split_due_date(payment, split) or today
                    days_until_due = (due_date - today).days if due_date else None
                    check_status, status_ar, badge_color = _status_snapshot(manual_status, status_value, days_until_due)

                    if parsed_from and due_date and due_date < parsed_from:
                        continue
                    if parsed_to and due_date and due_date > parsed_to:
                        continue
                    if status == 'pending' and check_status not in ('PENDING', 'due_soon'):
                        continue
                    if status == 'completed' and check_status != 'CASHED':
                        continue
                    if status == 'overdue' and check_status != 'OVERDUE':
                        continue

                    details = getattr(split, 'details', {}) or {}
                    if isinstance(details, str):
                        try:
                            details = json.loads(details)
                        except Exception:
                            details = {}

                    check_number = details.get('check_number') or getattr(payment, 'check_number', '')
                    check_bank = details.get('check_bank') or getattr(payment, 'check_bank', '')
                    split_currency = (getattr(split, 'currency', None) or getattr(payment, 'currency', 'ILS') or 'ILS').upper()
                    converted_currency = (getattr(split, 'converted_currency', None) or getattr(payment, 'currency', 'ILS') or 'ILS').upper()
                    amount = float(getattr(split, 'amount', 0) or 0)
                    converted_amount = getattr(split, 'converted_amount', None)
                    if converted_amount is not None:
                        converted_amount = float(converted_amount or 0)
                    fx_rate_used = getattr(split, 'fx_rate_used', None)
                    fx_rate_source = getattr(split, 'fx_rate_source', None)
                    fx_rate_timestamp = getattr(split, 'fx_rate_timestamp', None)

                    split_key = f"payment-split-{payment.id}-{getattr(split, 'id', '0')}"
                    if split_key in check_ids:
                        continue
                    check_ids.add(split_key)

                    checks.append({
                        'id': getattr(split, 'id', 0),
                        'payment_id': payment.id,
                        'type': 'payment_split',
                        'source': 'دفعة جزئية',
                        'source_badge': 'info',
                        'check_number': check_number or '',
                        'check_bank': check_bank or '',
                        'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                        'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                        'amount': amount,
                        'currency': split_currency,
                        'converted_amount': converted_amount,
                        'converted_currency': converted_currency,
                        'fx_rate_issue': float(fx_rate_used) if fx_rate_used else None,
                        'fx_rate_issue_source': fx_rate_source,
                        'fx_rate_issue_timestamp': fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if isinstance(fx_rate_timestamp, datetime) else None,
                        'direction': 'وارد' if is_incoming else 'صادر',
                        'direction_en': 'in' if is_incoming else 'out',
                        'is_incoming': is_incoming,
                        'status': check_status,
                        'status_ar': status_ar,
                        'badge_color': badge_color,
                        'days_until_due': days_until_due if days_until_due is not None else 0,
                        'entity_name': entity_name,
                        'entity_type': entity_type,
                        'entity_link': entity_link,
                        'drawer_name': entity_name if not is_incoming else 'شركتنا',
                        'payee_name': 'شركتنا' if not is_incoming else entity_name,
                        'description': f"جزء من سند {'من' if is_incoming else 'إلى'} {entity_name}" + (f" ({entity_type})" if entity_type else ''),
                        'purpose': 'دفعة جزئية',
                        'notes': payment.notes or '',
                        'created_at': payment.payment_date.strftime('%Y-%m-%d %H:%M') if payment.payment_date else '',
                        'receipt_number': payment.receipt_number or '',
                        'reference': payment.receipt_number or ''
                    })
                    processed_split_count += 1

            current_app.logger.info(f"📊 تم تضمين {processed_split_count} شيكات من الدفعات الجزئية")
        
        if not source_filter or source_filter in ['all', 'expense']:
            expense_checks = Expense.query.filter(
                Expense.payment_method == 'cheque'
            )
            
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    expense_checks = expense_checks.filter(Expense.check_due_date >= from_dt)
                except Exception:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    expense_checks = expense_checks.filter(Expense.check_due_date <= to_dt)
                except Exception:
                    pass
            
            for expense in expense_checks.all():
                if not expense.check_due_date:
                    continue
                
                due_date = expense.check_due_date.date() if isinstance(expense.check_due_date, datetime) else expense.check_due_date
                days_until_due = (due_date - today).days
                
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
        
        if not source_filter or source_filter in ['all', 'manual']:
            manual_checks_query = Check.query

            if direction == 'in':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.OUT.value)
            
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
            
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date >= from_dt)
                except Exception:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date <= to_dt)
                except Exception:
                    pass
            
            for check in manual_checks_query.all():
                due_date = None
                if check.check_due_date:
                    if isinstance(check.check_due_date, datetime):
                        due_date = check.check_due_date.date()
                    else:
                        due_date = check.check_due_date
                if not due_date:
                    due_date = today
                days_until_due = (due_date - today).days if due_date else None

                status_value = check.status.value if hasattr(check.status, 'value') else str(check.status or '')
                manual_status = status_value
                check_status, status_ar, badge_color = _status_snapshot(manual_status, status_value, days_until_due)

                entity_name = check.entity_name
                entity_type_code = check.entity_type
                entity_link = ''
                entity_type = ''

                if entity_type_code == 'customer':
                    entity_type = 'عميل'
                    entity_link = f'/customers/{check.entity_id}'
                elif entity_type_code == 'supplier':
                    entity_type = 'مورد'
                    entity_link = f'/vendors/suppliers/{check.entity_id}'
                elif entity_type_code == 'partner':
                    entity_type = 'شريك'
                    entity_link = f'/vendors/partners/{check.entity_id}'
                else:
                    entity_type = 'ساحب' if check.direction == PaymentDirection.IN.value else 'مستفيد'

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
                    'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                    'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                    'amount': float(check.amount or 0),
                    'currency': check.currency or 'ILS',
                    'fx_rate_issue': float(check.fx_rate_issue) if check.fx_rate_issue else None,
                    'fx_rate_issue_source': check.fx_rate_issue_source,
                    'fx_rate_issue_timestamp': check.fx_rate_issue_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_issue_timestamp else None,
                    'fx_rate_cash': float(check.fx_rate_cash) if check.fx_rate_cash else None,
                    'fx_rate_cash_source': check.fx_rate_cash_source,
                    'fx_rate_cash_timestamp': check.fx_rate_cash_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_cash_timestamp else None,
                    'direction': 'وارد' if check.direction == PaymentDirection.IN.value else 'صادر',
                    'direction_en': (check.direction.value if hasattr(check.direction, 'value') else str(check.direction)).lower(),
                    'is_incoming': check.direction == PaymentDirection.IN.value,
                    'status': check_status,
                    'status_ar': status_ar,
                    'badge_color': badge_color,
                    'days_until_due': days_until_due if days_until_due is not None else 0,
                    'entity_name': entity_name,
                    'entity_type': entity_type,
                    'entity_link': entity_link,
                    'notes': check.notes or '',
                    'created_at': check.created_at.strftime('%Y-%m-%d') if check.created_at else '',
                    'receipt_number': check.reference_number or ''
                })
        
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
        
        from decimal import Decimal
        from models import convert_amount
        
        incoming_checks = db.session.query(Payment).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).all()
        
        incoming_total = Decimal('0.00')
        incoming_overdue = 0
        incoming_overdue_amount = Decimal('0.00')
        
        for p in incoming_checks:
            amt = Decimal(str(p.total_amount or 0))
            if p.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            incoming_total += amt_ils
            if p.check_due_date and p.check_due_date < datetime.utcnow():
                incoming_overdue += 1
                incoming_overdue_amount += amt_ils
        
        incoming_total = float(incoming_total)
        incoming_overdue_amount = float(incoming_overdue_amount)
        
        incoming_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).scalar() or 0
        
        outgoing_checks = db.session.query(Payment).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).all()
        
        outgoing_total = Decimal('0.00')
        outgoing_overdue = 0
        outgoing_overdue_amount = Decimal('0.00')
        
        for p in outgoing_checks:
            amt = Decimal(str(p.total_amount or 0))
            if p.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            outgoing_total += amt_ils
            if p.check_due_date and p.check_due_date < datetime.utcnow():
                outgoing_overdue += 1
                outgoing_overdue_amount += amt_ils
        
        outgoing_total = float(outgoing_total)
        outgoing_overdue_amount = float(outgoing_overdue_amount)
        
        outgoing_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).scalar() or 0
        
        expense_checks = db.session.query(Expense).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.isnot(None),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).all()
        
        expense_total = Decimal('0.00')
        expense_overdue = 0
        expense_overdue_amount = Decimal('0.00')
        
        for exp in expense_checks:
            amt = Decimal(str(exp.amount or 0))
            if exp.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, exp.currency, "ILS", exp.date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            expense_total += amt_ils
            if exp.check_due_date and exp.check_due_date < datetime.utcnow():
                expense_overdue += 1
                expense_overdue_amount += amt_ils
        
        expense_total = float(expense_total)
        expense_overdue_amount = float(expense_overdue_amount)
        
        expense_this_week = db.session.query(db.func.count(Expense.id)).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.between(datetime.utcnow(), datetime.combine(week_ahead, datetime.max.time())),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).scalar() or 0
        
        total_outgoing_value = float(outgoing_total or 0) + float(expense_total or 0)
        total_outgoing_overdue = outgoing_overdue + expense_overdue
        total_outgoing_overdue_amount = float(outgoing_overdue_amount or 0) + float(expense_overdue_amount or 0)
        total_outgoing_this_week = outgoing_this_week + expense_this_week
        
        return jsonify({
            'success': True,
            'statistics': {
                'incoming': {
                    'total_amount': float(incoming_total or 0),
                    'overdue_count': incoming_overdue,
                    'overdue_amount': float(incoming_overdue_amount or 0),  # ✅ إضافة المبلغ المتأخر
                    'this_week_count': incoming_this_week
                },
                'outgoing': {
                    'total_amount': total_outgoing_value,
                    'overdue_count': total_outgoing_overdue,
                    'overdue_amount': total_outgoing_overdue_amount,  # ✅ إضافة المبلغ المتأخر
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
        
        notes = check.notes or ''
        lifecycle_events = []
        
        for line in notes.split('\n'):
            if '[' in line and ']' in line:
                lifecycle_events.append({
                    'timestamp': line[line.find('[')+1:line.find(']')],
                    'description': line[line.find(']')+1:].strip()
                })
        
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
        data = request.get_json() or {}
        new_status = data.get('status')  # CASHED, RETURNED, BOUNCED, CANCELLED, RESUBMITTED
        notes = data.get('notes', '')
        
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
                actual_id = int(check_id)
                if Check.query.get(actual_id):
                    check_type = 'check'
                    current_app.logger.info(f"✅ تم التعرف: Check (Manual) ID={actual_id}")
                elif Payment.query.get(actual_id):
                    check_type = 'payment'
                    current_app.logger.info(f"✅ تم التعرف: Payment ID={actual_id}")
                else:
                    check_type = 'check'
                    current_app.logger.warning(f"⚠️  افتراض Check ID={actual_id}")
            else:
                current_app.logger.warning(f"⚠️  check_id غير معروف: {check_id}")
                check_type = 'check'
                actual_id = int(check_id) if check_id.isdigit() else check_id
        else:
            actual_id = int(check_id)
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
        
        allowed_statuses = ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED', 'RESUBMITTED', 'ARCHIVED', 'PENDING']
        if new_status not in allowed_statuses:
            return jsonify({
                'success': False,
                'message': 'حالة غير صالحة'
            }), 400
        
        if check_type == 'payment' or check_type == 'split':
            if check_type == 'split':
                split = PaymentSplit.query.get_or_404(actual_id)
                check = split.payment
            else:
                check = Payment.query.get_or_404(actual_id)
            
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
            
            check.notes = (check.notes or '') + status_note
            
            if new_status == 'CASHED':
                if check.status == PaymentStatus.PENDING:
                    check.status = PaymentStatus.COMPLETED
            elif new_status in ['BOUNCED', 'RETURNED']:
                check.status = PaymentStatus.FAILED
            elif new_status == 'RESUBMITTED':
                check.status = PaymentStatus.PENDING
            elif new_status == 'CANCELLED':
                if check.status == PaymentStatus.PENDING:
                    check.status = PaymentStatus.CANCELLED
            
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
    API للحصول على التنبيهات - محسّن لجلب من جميع المصادر
    """
    try:
        today = datetime.utcnow().date()
        week_ahead = today + timedelta(days=7)
        
        alerts = []
        
        overdue_manual_checks = Check.query.filter(
            and_(
                Check.status == CheckStatus.PENDING.value,
                Check.check_due_date < datetime.utcnow()
            )
        ).all()
        
        for check in overdue_manual_checks:
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            else:
                entity_name = check.drawer_name or check.payee_name or 'غير محدد'
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            days_overdue = (today - check.check_due_date.date()).days
            
            alerts.append({
                'type': 'overdue',
                'severity': 'danger',
                'icon': 'fas fa-exclamation-triangle',
                'title': f'🚨 شيك متأخر {days_overdue} يوم',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - المبلغ: {float(check.amount):,.2f} {check.currency}',
                'link': '/checks',
                'amount': float(check.amount),
                'currency': check.currency,
                'days_overdue': days_overdue,
                'check_number': check.check_number
            })
        
        overdue_payment_checks = Payment.query.filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date < datetime.utcnow(),
                Payment.check_number.isnot(None)
            )
        ).all()
        
        for check in overdue_payment_checks:
            if Check.query.filter_by(reference_number=f'PMT-{check.id}').first():
                continue
            
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            else:
                entity_name = 'غير محدد'
            
            days_overdue = (today - check.check_due_date.date()).days
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            alerts.append({
                'type': 'overdue',
                'severity': 'danger',
                'icon': 'fas fa-exclamation-circle',
                'title': f'🚨 شيك متأخر {days_overdue} يوم',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - المبلغ: {float(check.total_amount or 0):,.2f} {check.currency}',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_overdue,
                'link': f'/checks?id={check.id}'
            })
        
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
            else:
                entity_name = 'غير محدد'
            
            days_until = (check.check_due_date.date() - today).days
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            alerts.append({
                'type': 'due_soon',
                'severity': 'warning',
                'icon': 'fas fa-clock',
                'title': f'⚠️ شيك قريب الاستحقاق',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - يستحق خلال {days_until} يوم - المبلغ: {float(check.total_amount or 0):,.2f} {check.currency}',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_until,
                'link': f'/checks?id={check.id}'
            })
        
        alerts.sort(key=lambda x: (x['type'] != 'overdue', x.get('days', x.get('days_overdue', 0))))
        
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
    
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).all()
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
    
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).all()
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
    
    all_checks_response = get_checks()
    all_checks_data = all_checks_response.get_json()
    all_checks = all_checks_data.get('checks', []) if all_checks_data.get('success') else []
    
    current_app.logger.info(f"📊 التقارير - عدد الشيكات: {len(all_checks)}")
    
    independent_checks = Check.query.all()
    
    stats_by_status = {}
    for check in all_checks:
        status = check.get('status', 'UNKNOWN')
        original_status = status  # للـ logging
        
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
            status = 'CANCELLED'
        elif 'حالة الشيك: مرفوض' in notes:
            status = 'BOUNCED'
        
        if status not in stats_by_status:
            stats_by_status[status] = {'status': status, 'count': 0, 'total_amount': 0}
        stats_by_status[status]['count'] += 1
        stats_by_status[status]['total_amount'] += float(check.get('amount', 0))
    
    current_app.logger.info(f"📊 إحصائيات الحالات: {stats_by_status}")
    current_app.logger.info(f"📊 عدد الحالات المختلفة: {len(stats_by_status)}")
    
    stats_by_status = list(stats_by_status.values())
    
    stats_by_direction = {'IN': {'direction': 'IN', 'count': 0, 'total_amount': 0},
                          'OUT': {'direction': 'OUT', 'count': 0, 'total_amount': 0}}
    
    for check in all_checks:
        direction = 'IN' if check.get('is_incoming') else 'OUT'
        stats_by_direction[direction]['count'] += 1
        stats_by_direction[direction]['total_amount'] += float(check.get('amount', 0))
    
    stats_by_direction = list(stats_by_direction.values())
    
    overdue_checks = []
    due_soon_checks = []
    
    for c in all_checks:
        notes = (c.get('notes', '') or '').lower()
        actual_status = c.get('status', '').upper()
        
        if 'حالة الشيك: مسحوب' in notes:
            continue  # مسحوب - تخطي
        elif 'حالة الشيك: ملغي' in notes or 'حالة الشيك: مؤرشف' in notes:
            continue  # ملغي/مؤرشف - تخطي
        elif 'حالة الشيك: مرتجع' in notes:
            continue  # مرتجع - تخطي
        
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

