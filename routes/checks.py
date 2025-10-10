# -*- coding: utf-8 -*-
"""
نظام إدارة الشيكات الصادرة والواردة
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import current_user
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from extensions import db
from models import Payment, Expense, PaymentMethod, PaymentStatus, PaymentDirection
from utils import permission_required
from decimal import Decimal

checks_bp = Blueprint('checks', __name__, url_prefix='/checks')

# حالات الشيك المخصصة
CHECK_STATUS = {
    'PENDING': {'ar': 'معلق', 'color': 'info', 'icon': 'fa-clock'},
    'CASHED': {'ar': 'تم الصرف', 'color': 'success', 'icon': 'fa-check-circle'},
    'RETURNED': {'ar': 'مرتجع', 'color': 'warning', 'icon': 'fa-undo'},
    'BOUNCED': {'ar': 'مرفوض', 'color': 'danger', 'icon': 'fa-ban'},
    'RESUBMITTED': {'ar': 'أعيد للبنك', 'color': 'primary', 'icon': 'fa-recycle'},
    'CANCELLED': {'ar': 'ملغي', 'color': 'secondary', 'icon': 'fa-times-circle'},
    'OVERDUE': {'ar': 'متأخر', 'color': 'danger', 'icon': 'fa-exclamation-triangle'},
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
@permission_required('view_payments')
def index():
    """صفحة عرض الشيكات"""
    return render_template('checks/index.html')


@checks_bp.route('/api/checks')
@permission_required('view_payments')
def get_checks():
    """
    API لجلب الشيكات مع الفلاتر
    """
    try:
        # الفلاتر من الـ request
        direction = request.args.get('direction')  # 'in' أو 'out' أو 'all'
        status = request.args.get('status')  # 'pending', 'completed', 'overdue', 'all'
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # 1. جلب الشيكات من Payment
        payment_checks = Payment.query.filter(
            Payment.method == PaymentMethod.CHEQUE.value
        )
        
        # فلتر حسب الاتجاه
        if direction == 'in':
            payment_checks = payment_checks.filter(Payment.direction == PaymentDirection.IN.value)
        elif direction == 'out':
            payment_checks = payment_checks.filter(Payment.direction == PaymentDirection.OUT.value)
        
        # فلتر حسب الحالة
        today = datetime.utcnow().date()
        if status == 'pending':
            payment_checks = payment_checks.filter(Payment.status == PaymentStatus.PENDING.value)
        elif status == 'completed':
            payment_checks = payment_checks.filter(Payment.status == PaymentStatus.COMPLETED.value)
        elif status == 'overdue':
            payment_checks = payment_checks.filter(
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
            except:
                pass
        
        if to_date:
            try:
                to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                payment_checks = payment_checks.filter(Payment.check_due_date <= to_dt)
            except:
                pass
        
        # 2. جلب الشيكات من Expense
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
        
        # تجميع النتائج
        checks = []
        
        # معالجة شيكات Payment
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
                # التحقق من الملاحظات لمعرفة إذا كان مرتجع أو مرفوض
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
            
            # تحديد اسم الجهة
            entity_name = ''
            entity_link = ''
            if payment.customer:
                entity_name = payment.customer.name
                entity_link = f'/customers/{payment.customer.id}'
            elif payment.supplier:
                entity_name = payment.supplier.name
                entity_link = f'/vendors/{payment.supplier.id}'
            elif payment.partner:
                entity_name = payment.partner.name
                entity_link = f'/partners/{payment.partner.id}'
            
            checks.append({
                'id': payment.id,
                'type': 'payment',
                'source': 'دفعة',
                'check_number': payment.check_number or '',
                'check_bank': payment.check_bank or '',
                'check_due_date': due_date.strftime('%Y-%m-%d'),
                'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                'amount': float(payment.amount or 0),
                'currency': payment.currency or 'ILS',
                'direction': 'وارد' if is_incoming else 'صادر',
                'direction_en': 'in' if is_incoming else 'out',
                'is_incoming': is_incoming,
                'status': check_status,
                'status_ar': status_ar,
                'badge_color': badge_color,
                'days_until_due': days_until_due,
                'entity_name': entity_name,
                'entity_link': entity_link,
                'notes': payment.notes or '',
                'created_at': payment.created_at.strftime('%Y-%m-%d') if payment.created_at else '',
                'receipt_number': payment.receipt_number or ''
            })
        
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
            
            checks.append({
                'id': expense.id,
                'type': 'expense',
                'source': 'مصروف',
                'check_number': expense.check_number or '',
                'check_bank': expense.check_bank or '',
                'check_due_date': due_date.strftime('%Y-%m-%d'),
                'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                'amount': float(expense.amount or 0),
                'currency': expense.currency or 'ILS',
                'direction': 'صادر',
                'direction_en': 'out',
                'is_incoming': False,
                'status': check_status,
                'status_ar': status_ar,
                'badge_color': badge_color,
                'days_until_due': days_until_due,
                'entity_name': expense.paid_to or expense.payee_name or '',
                'entity_link': '',
                'notes': expense.description or '',
                'created_at': expense.date.strftime('%Y-%m-%d') if expense.date else '',
                'receipt_number': expense.reference or ''
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
@permission_required('view_payments')
def get_statistics():
    """
    API للحصول على إحصائيات الشيكات
    """
    try:
        today = datetime.utcnow().date()
        week_ahead = today + timedelta(days=7)
        month_ahead = today + timedelta(days=30)
        
        # 1. الشيكات الواردة
        incoming_total = db.session.query(db.func.sum(Payment.amount)).filter(
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
        outgoing_total = db.session.query(db.func.sum(Payment.amount)).filter(
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
@permission_required('view_payments')
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


@checks_bp.route('/api/update-status/<int:check_id>', methods=['POST'])
@permission_required('manage_payments')
def update_check_status(check_id):
    """
    تحديث حالة الشيك
    """
    try:
        check_type = request.form.get('type')  # 'payment' or 'expense'
        new_status = request.form.get('status')  # CASHED, RETURNED, BOUNCED, CANCELLED, RESUBMITTED
        notes = request.form.get('notes', '')
        
        if not check_type or not new_status:
            return jsonify({
                'success': False,
                'error': 'بيانات ناقصة'
            }), 400
        
        # التحقق من الحالة المسموحة
        if new_status not in CHECK_STATUS:
            return jsonify({
                'success': False,
                'error': 'حالة غير صالحة'
            }), 400
        
        if check_type == 'payment':
            check = Payment.query.get_or_404(check_id)
            
            # تحديث الحالة
            if new_status == 'CASHED':
                check.status = PaymentStatus.COMPLETED
            elif new_status == 'CANCELLED':
                check.status = PaymentStatus.CANCELLED
            elif new_status in ['RETURNED', 'BOUNCED', 'RESUBMITTED']:
                if new_status == 'RESUBMITTED':
                    check.status = PaymentStatus.PENDING  # إعادته لحالة الانتظار
                else:
                    check.status = PaymentStatus.FAILED
            
            # إضافة ملاحظة مفصلة
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            status_note = f"\n[{timestamp}] 🔄 تغيير الحالة إلى: {CHECK_STATUS[new_status]['ar']}"
            
            # إضافة أيقونة حسب الحالة
            status_icons = {
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'RESUBMITTED': '🔁',
                'CANCELLED': '⛔'
            }
            if new_status in status_icons:
                status_note = status_note.replace('🔄', status_icons[new_status])
            
            if notes:
                status_note += f"\n   💬 ملاحظة: {notes}"
            if current_user:
                status_note += f"\n   👤 المستخدم: {current_user.username}"
            
            check.notes = (check.notes or '') + status_note
            
        elif check_type == 'expense':
            check = Expense.query.get_or_404(check_id)
            
            # تحديث الحالة (Expense ليس لديه status field مثل Payment)
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            # إضافة أيقونة حسب الحالة
            status_icons = {
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'RESUBMITTED': '🔁',
                'CANCELLED': '⛔'
            }
            icon = status_icons.get(new_status, '🔄')
            
            status_note = f"\n[{timestamp}] {icon} تغيير الحالة إلى: {CHECK_STATUS[new_status]['ar']}"
            if notes:
                status_note += f"\n   💬 ملاحظة: {notes}"
            if current_user:
                status_note += f"\n   👤 المستخدم: {current_user.username}"
            
            check.notes = (check.notes or '') + status_note
            
            # إذا تم الصرف، نضع is_paid = True
            if new_status == 'CASHED':
                if hasattr(check, 'is_paid'):
                    check.is_paid = True
            # إذا أعيد للبنك، نتأكد أنه غير مدفوع
            elif new_status == 'RESUBMITTED':
                if hasattr(check, 'is_paid'):
                    check.is_paid = False
        
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
@permission_required('view_payments')
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
                'amount': float(check.amount or 0),
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
                'amount': float(check.amount or 0),
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

