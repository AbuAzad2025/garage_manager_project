# routes/archive.py - Archive Management Routes
# Location: /garage_manager/routes/archive.py
# Description: Archive management routes for the garage management system

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_, desc, and_
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import json

from extensions import db
from models import Archive, ServiceRequest, Payment, Sale, Customer, Product, Expense, Check, Supplier, Partner
from utils import permission_required, super_only

archive_bp = Blueprint('archive', __name__, url_prefix='/archive')

@archive_bp.route('/')
@login_required
@permission_required('manage_archive')
def index():
    total_archives = Archive.query.count()
    type_stats = db.session.query(
        Archive.record_type,
        func.count(Archive.id).label('count')
    ).group_by(Archive.record_type).all()
    current_month = datetime.now().replace(day=1)
    monthly_archives = Archive.query.filter(
        Archive.archived_at >= current_month
    ).count()
    recent_archives = Archive.query.order_by(desc(Archive.archived_at)).limit(10).all()
    
    return render_template('archive/index.html',
                         total_archives=total_archives,
                         type_stats=type_stats,
                         monthly_archives=monthly_archives,
                         recent_archives=recent_archives)

@archive_bp.route('/search', methods=['GET', 'POST'])
@login_required
@permission_required('manage_archive')
def search():
    """البحث في الأرشيفات"""
    # form = ArchiveSearchForm()
    archives = []
    
    if request.method == 'POST':
        query = Archive.query
        
        # فلترة حسب نوع السجل
        record_type = request.form.get('record_type')
        if record_type:
            query = query.filter(Archive.record_type == record_type)
        
        # فلترة حسب التاريخ
        date_from = request.form.get('date_from')
        if date_from:
            query = query.filter(Archive.archived_at >= date_from)
        
        date_to = request.form.get('date_to')
        if date_to:
            query = query.filter(Archive.archived_at <= date_to)
        
        # البحث في البيانات
        search_term = request.form.get('search_term')
        if search_term:
            search_term = f"%{search_term}%"
            query = query.filter(
                or_(
                    Archive.archived_data.ilike(search_term),
                    Archive.archive_reason.ilike(search_term)
                )
            )
        
        archives = query.order_by(desc(Archive.archived_at)).all()
    
    return render_template('archive/search.html', archives=archives)

@archive_bp.route('/bulk-archive', methods=['GET', 'POST'])
@login_required
@super_only
def bulk_archive():
    """الأرشفة الجماعية"""
    # form = BulkArchiveForm()
    
    if request.method == 'POST':
        try:
            # تحديد الجدول المناسب
            model_map = {
                'service_requests': ServiceRequest,
                'payments': Payment,
                'sales': Sale,
                'expenses': Expense,
                'checks': Check
            }
            
            record_type = request.form.get('record_type')
            model_class = model_map.get(record_type)
            if not model_class:
                flash('نوع السجل غير مدعوم', 'error')
                return redirect(url_for('archive.bulk_archive'))
            
            # البحث عن السجلات المؤهلة للأرشفة
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            reason = request.form.get('reason')
            
            query = model_class.query.filter(
                and_(
                    model_class.created_at >= date_from,
                    model_class.created_at <= date_to
                )
            )
            
            records = query.all()
            archived_count = 0
            
            for record in records:
                # أرشفة السجل
                archive = Archive.archive_record(
                    record=record,
                    reason=reason,
                    user_id=current_user.id
                )
                
                # حذف السجل الأصلي
                db.session.delete(record)
                archived_count += 1
            
            db.session.commit()
            
            flash(f'تم أرشفة {archived_count} سجل بنجاح', 'success')
            return redirect(url_for('archive.index'))
            
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ في الأرشفة الجماعية: {str(e)}', 'error')
    
    return render_template('archive/bulk_archive.html')

@archive_bp.route('/view/<int:archive_id>')
@login_required
@permission_required('manage_archive')
def view_archive(archive_id):
    """عرض تفاصيل الأرشيف"""
    archive = Archive.query.get_or_404(archive_id)
    
    # تحليل البيانات المؤرشفة
    try:
        archived_data = json.loads(archive.archived_data)
    except:
        archived_data = {}
    
    return render_template('archive/view.html', archive=archive, archived_data=archived_data)

@archive_bp.route('/restore/<int:archive_id>', methods=['GET', 'POST'])
@login_required
@super_only
def restore_archive(archive_id):
    """استعادة الأرشيف"""
    archive = Archive.query.get_or_404(archive_id)
    print(f"🔍 [RESTORE] بدء استعادة الأرشيف رقم: {archive_id}")
    print(f"🔍 [RESTORE] نوع السجل: {archive.record_type}")
    print(f"🔍 [RESTORE] معرف السجل: {archive.record_id}")
    
    if request.method == 'POST':
        try:
            # تحديد الجدول المناسب
            model_map = {
                'service_requests': ServiceRequest,
                'payments': Payment,
                'sales': Sale,
                'expenses': Expense,
                'checks': Check,
                'customers': Customer,
                'suppliers': Supplier,
                'partners': Partner
            }
            
            model_class = model_map.get(archive.record_type)
            if not model_class:
                flash('نوع السجل غير مدعوم للاستعادة', 'error')
                return redirect(url_for('archive.view_archive', archive_id=archive_id))
            
            # البحث عن السجل الأصلي (يجب أن يكون موجوداً مع is_archived=True)
            original_record = model_class.query.get(archive.record_id)
            
            if original_record:
                print(f"✅ [RESTORE] تم العثور على السجل الأصلي: {original_record.id}")
                
                # استعادة السجل (إلغاء الأرشفة)
                original_record.is_archived = False
                original_record.archived_at = None
                original_record.archived_by = None
                original_record.archive_reason = None
                
                print(f"📝 [RESTORE] تم تحديث حالة السجل إلى غير مؤرشف")
                
                # حذف الأرشيف
                db.session.delete(archive)
                print(f"🗑️ [RESTORE] تم حذف الأرشيف")
                
                db.session.commit()
                print(f"✅ [RESTORE] تم حفظ التغييرات بنجاح")
                
                flash(f'تم استعادة السجل رقم {archive.record_id} بنجاح', 'success')
                return redirect(url_for('archive.index'))
            else:
                print(f"❌ [RESTORE] السجل الأصلي غير موجود - إنشاء سجل جديد")
                
                # تحليل البيانات المؤرشفة
                archived_data = json.loads(archive.archived_data)
                
                # إنشاء السجل الجديد
                new_record = model_class()
                
                # تعبئة البيانات
                for key, value in archived_data.items():
                    if hasattr(new_record, key) and key not in ['id', 'is_archived', 'archived_at', 'archived_by', 'archive_reason']:
                        setattr(new_record, key, value)
                
                # إضافة السجل الجديد
                db.session.add(new_record)
                db.session.flush()  # للحصول على ID الجديد
                print(f"✅ [RESTORE] تم إنشاء سجل جديد برقم: {new_record.id}")
                
                # حذف الأرشيف
                db.session.delete(archive)
                db.session.commit()
                
                flash(f'تم استعادة السجل كسجل جديد برقم {new_record.id}', 'success')
                return redirect(url_for('archive.index'))
            
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"❌ [RESTORE] خطأ في استعادة السجل: {str(e)}")
            flash(f'خطأ في استعادة السجل: {str(e)}', 'error')
        except Exception as e:
            db.session.rollback()
            print(f"❌ [RESTORE] خطأ عام في استعادة السجل: {str(e)}")
            flash(f'خطأ في استعادة السجل: {str(e)}', 'error')
    
    return render_template('archive/restore.html', archive=archive)

@archive_bp.route('/delete/<int:archive_id>', methods=['POST'])
@login_required
@super_only
def delete_archive(archive_id):
    """حذف الأرشيف نهائياً"""
    archive = Archive.query.get_or_404(archive_id)
    
    try:
        db.session.delete(archive)
        db.session.commit()
        flash('تم حذف الأرشيف نهائياً', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'خطأ في حذف الأرشيف: {str(e)}', 'error')
    
    return redirect(url_for('archive.index'))

@archive_bp.route('/export')
@login_required
@permission_required('manage_archive')
def export_archives():
    """تصدير الأرشيفات"""
    # يمكن تطوير هذا لاحقاً لتصدير الأرشيفات
    flash('ميزة التصدير قيد التطوير', 'info')
    return redirect(url_for('archive.index'))

# دوال مساعدة للأرشفة
def archive_service_request(service_id, reason=None):
    """أرشفة طلب صيانة"""
    service = ServiceRequest.query.get(service_id)
    if service:
        archive = Archive.archive_record(service, reason)
        db.session.delete(service)
        db.session.commit()
        return archive
    return None

def archive_payment(payment_id, reason=None):
    """أرشفة دفعة"""
    payment = Payment.query.get(payment_id)
    if payment:
        archive = Archive.archive_record(payment, reason)
        db.session.delete(payment)
        db.session.commit()
        return archive
    return None

def archive_sale(sale_id, reason=None):
    """أرشفة مبيعة"""
    sale = Sale.query.get(sale_id)
    if sale:
        archive = Archive.archive_record(sale, reason)
        db.session.delete(sale)
        db.session.commit()
        return archive
    return None

def archive_expense(expense_id, reason=None):
    """أرشفة نفقة"""
    expense = Expense.query.get(expense_id)
    if expense:
        archive = Archive.archive_record(expense, reason)
        db.session.delete(expense)
        db.session.commit()
        return archive
    return None

def archive_check(check_id, reason=None):
    """أرشفة شيك"""
    check = Check.query.get(check_id)
    if check:
        archive = Archive.archive_record(check, reason)
        db.session.delete(check)
        db.session.commit()
        return archive
    return None
