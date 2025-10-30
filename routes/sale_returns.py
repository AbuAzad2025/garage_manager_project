"""
نظام المرتجعات (Sale Returns)
إدارة مرتجعات البيع بشكل كامل مع إرجاع المخزون
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func, desc
from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models import (
    SaleReturn, SaleReturnLine, Sale, SaleLine,
    Customer, Product, Warehouse, User, AuditLog
)
from forms import SaleReturnForm, SaleReturnLineForm
from utils import permission_required

# إنشاء Blueprint
returns_bp = Blueprint('returns', __name__, url_prefix='/returns')


@returns_bp.route('/')
@login_required
def list_returns():
    """قائمة جميع المرتجعات"""
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Filters
    status = request.args.get('status', '')
    customer_id = request.args.get('customer_id', 0, type=int)
    search = request.args.get('search', '').strip()
    
    # Build query
    query = SaleReturn.query
    
    # Apply filters
    if status and status in ['DRAFT', 'CONFIRMED', 'CANCELLED']:
        query = query.filter_by(status=status)
    
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    
    if search:
        query = query.join(Customer).filter(
            or_(
                SaleReturn.reason.ilike(f'%{search}%'),
                SaleReturn.notes.ilike(f'%{search}%'),
                Customer.name.ilike(f'%{search}%')
            )
        )
    
    # Sort and paginate
    query = query.order_by(desc(SaleReturn.created_at))
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get all customers for filter
    customers = Customer.query.filter_by(is_archived=False).order_by(Customer.name).all()
    
    return render_template(
        'sale_returns/list.html',
        pagination=pagination,
        returns=pagination.items,
        customers=customers,
        current_status=status,
        current_customer=customer_id,
        search_term=search
    )


@returns_bp.route('/create', methods=['GET', 'POST'])
@returns_bp.route('/create/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def create_return(sale_id=None):
    """إنشاء مرتجع جديد"""
    
    form = SaleReturnForm()
    sale = None
    
    # إذا تم تمرير sale_id، حمل بيانات البيع
    if sale_id:
        sale = Sale.query.get_or_404(sale_id)
        
        if request.method == 'GET':
            form.sale_id.data = sale.id
            form.customer_id.data = sale.customer_id
            form.warehouse_id.data = sale.warehouse_id
            form.currency.data = sale.currency or 'ILS'
    
    # تهيئة افتراضي للمخزن من الإعدادات إذا لم يكن هناك بيع محدد
    if request.method == 'GET' and not sale_id and not (form.warehouse_id.data):
        try:
            from models import SystemSettings
            returns_wh = SystemSettings.get_setting('returns_warehouse_id', None)
            if returns_wh:
                form.warehouse_id.data = int(returns_wh)
        except Exception:
            pass

    if form.validate_on_submit():
        try:
            # إنشاء المرتجع
            sale_return = SaleReturn(
                sale_id=form.sale_id.data if form.sale_id.data else None,
                customer_id=form.customer_id.data,
                warehouse_id=form.warehouse_id.data if form.warehouse_id.data else None,
                reason=form.reason.data.strip(),
                notes=form.notes.data.strip() if form.notes.data else None,
                currency=form.currency.data,
                status=form.status.data or 'DRAFT'
            )
            
            db.session.add(sale_return)
            db.session.flush()
            
            # إضافة السطور
            for line_data in form.lines.data:
                if line_data.get('product_id') and line_data.get('quantity'):
                    line = SaleReturnLine(
                        sale_return_id=sale_return.id,
                        product_id=line_data['product_id'],
                        warehouse_id=line_data.get('warehouse_id') or sale_return.warehouse_id,
                        quantity=line_data['quantity'],
                        unit_price=line_data.get('unit_price', 0),
                        condition=line_data.get('condition', 'GOOD') or 'GOOD',
                        notes=line_data.get('notes', '').strip() or None
                    )
                    db.session.add(line)
            
            db.session.commit()
            
            # Audit log
            try:
                audit = AuditLog(
                    model_name='SaleReturn',
                    record_id=sale_return.id,
                    action='CREATE',
                    user_id=current_user.id if current_user.is_authenticated else None
                )
                db.session.add(audit)
                db.session.commit()
            except Exception:
                pass  # لا نريد أن يفشل الحفظ بسبب الـ audit log
            
            flash('تم إنشاء المرتجع بنجاح', 'success')
            return redirect(url_for('returns.view_return', return_id=sale_return.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في إنشاء المرتجع: {str(e)}', 'danger')
    
    # تحضير choices للـ template
    products = Product.query.filter_by(is_active=True).order_by(Product.name).limit(500).all()
    product_choices = [(p.id, f"{p.name} ({p.barcode or 'بدون باركود'})") for p in products]
    
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()
    warehouse_choices = [(w.id, w.name) for w in warehouses]
    
    return render_template(
        'sale_returns/form.html',
        form=form,
        sale=sale,
        product_choices=product_choices,
        warehouse_choices=warehouse_choices,
        title='إنشاء مرتجع جديد'
    )


@returns_bp.route('/<int:return_id>')
@login_required
def view_return(return_id):
    """عرض تفاصيل مرتجع"""
    
    sale_return = SaleReturn.query.get_or_404(return_id)
    
    return render_template(
        'sale_returns/detail.html',
        sale_return=sale_return
    )


@returns_bp.route('/<int:return_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_return(return_id):
    """تعديل مرتجع"""
    
    sale_return = SaleReturn.query.get_or_404(return_id)
    
    # لا يمكن تعديل المرتجعات المؤكدة
    if sale_return.status == 'CONFIRMED':
        flash('لا يمكن تعديل مرتجع مؤكد', 'warning')
        return redirect(url_for('returns.view_return', return_id=return_id))
    
    form = SaleReturnForm(obj=sale_return)
    
    if request.method == 'GET':
        # تحميل السطور
        form.lines.entries.clear()
        for line in sale_return.lines:
            line_form = SaleReturnLineForm()
            line_form.id.data = line.id
            line_form.product_id.data = line.product_id
            line_form.warehouse_id.data = line.warehouse_id
            line_form.quantity.data = line.quantity
            line_form.unit_price.data = line.unit_price
            line_form.notes.data = line.notes
            form.lines.append_entry(line_form)
    
    if form.validate_on_submit():
        try:
            # تحديث البيانات الأساسية
            sale_return.sale_id = form.sale_id.data if form.sale_id.data else None
            sale_return.customer_id = form.customer_id.data
            sale_return.warehouse_id = form.warehouse_id.data if form.warehouse_id.data else None
            sale_return.reason = form.reason.data.strip()
            sale_return.notes = form.notes.data.strip() if form.notes.data else None
            sale_return.currency = form.currency.data
            sale_return.status = form.status.data
            
            # حذف السطور القديمة
            for line in sale_return.lines:
                db.session.delete(line)
            
            # إضافة السطور الجديدة
            for line_data in form.lines.data:
                if line_data.get('product_id') and line_data.get('quantity'):
                    line = SaleReturnLine(
                        sale_return_id=sale_return.id,
                        product_id=line_data['product_id'],
                        warehouse_id=line_data.get('warehouse_id') or sale_return.warehouse_id,
                        quantity=line_data['quantity'],
                        unit_price=line_data.get('unit_price', 0),
                        notes=line_data.get('notes', '').strip() or None
                    )
                    db.session.add(line)
            
            db.session.commit()
            
            # Audit log
            try:
                audit = AuditLog(
                    model_name='SaleReturn',
                    record_id=sale_return.id,
                    action='UPDATE',
                    user_id=current_user.id if current_user.is_authenticated else None
                )
                db.session.add(audit)
                db.session.commit()
            except Exception:
                pass
            
            flash('تم تحديث المرتجع بنجاح', 'success')
            return redirect(url_for('returns.view_return', return_id=return_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تحديث المرتجع: {str(e)}', 'danger')
    
    # تحضير choices للـ template
    products = Product.query.filter_by(is_active=True).order_by(Product.name).limit(500).all()
    product_choices = [(p.id, f"{p.name} ({p.barcode or 'بدون باركود'})") for p in products]
    
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()
    warehouse_choices = [(w.id, w.name) for w in warehouses]
    
    return render_template(
        'sale_returns/form.html',
        form=form,
        sale_return=sale_return,
        product_choices=product_choices,
        warehouse_choices=warehouse_choices,
        title='تعديل مرتجع'
    )


@returns_bp.route('/<int:return_id>/confirm', methods=['POST'])
@login_required
def confirm_return(return_id):
    """تأكيد المرتجع"""
    
    sale_return = SaleReturn.query.get_or_404(return_id)
    
    if sale_return.status == 'CONFIRMED':
        flash('المرتجع مؤكد مسبقاً', 'info')
        return redirect(url_for('returns.view_return', return_id=return_id))
    
    if sale_return.status == 'CANCELLED':
        flash('لا يمكن تأكيد مرتجع ملغي', 'warning')
        return redirect(url_for('returns.view_return', return_id=return_id))
    
    try:
        sale_return.status = 'CONFIRMED'
        db.session.commit()
        
        # Audit log
        try:
            audit = AuditLog(
                model_name='SaleReturn',
                record_id=sale_return.id,
                action='CONFIRM',
                user_id=current_user.id if current_user.is_authenticated else None
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            pass
        
        flash('تم تأكيد المرتجع بنجاح. تم إرجاع المخزون.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في تأكيد المرتجع: {str(e)}', 'danger')
    
    return redirect(url_for('returns.view_return', return_id=return_id))


@returns_bp.route('/<int:return_id>/cancel', methods=['POST'])
@login_required
def cancel_return(return_id):
    """إلغاء المرتجع"""
    
    sale_return = SaleReturn.query.get_or_404(return_id)
    
    if sale_return.status == 'CANCELLED':
        flash('المرتجع ملغي مسبقاً', 'info')
        return redirect(url_for('returns.view_return', return_id=return_id))
    
    try:
        # إذا كان مؤكداً، نحتاج لعكس المخزون
        if sale_return.status == 'CONFIRMED':
            # حذف السطور سيعكس المخزون تلقائياً عبر events
            for line in sale_return.lines[:]:
                db.session.delete(line)
        
        sale_return.status = 'CANCELLED'
        db.session.commit()
        
        # Audit log
        try:
            audit = AuditLog(
                model_name='SaleReturn',
                record_id=sale_return.id,
                action='CANCEL',
                user_id=current_user.id if current_user.is_authenticated else None
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            pass
        
        flash('تم إلغاء المرتجع بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في إلغاء المرتجع: {str(e)}', 'danger')
    
    return redirect(url_for('returns.view_return', return_id=return_id))


@returns_bp.route('/<int:return_id>/delete', methods=['POST'])
@login_required
def delete_return(return_id):
    """حذف المرتجع"""
    
    sale_return = SaleReturn.query.get_or_404(return_id)
    
    # فقط المسودات يمكن حذفها
    if sale_return.status != 'DRAFT':
        flash('لا يمكن حذف مرتجع مؤكد أو ملغي. استخدم الإلغاء بدلاً من ذلك.', 'warning')
        return redirect(url_for('returns.view_return', return_id=return_id))
    
    try:
        # Audit log قبل الحذف
        try:
            audit = AuditLog(
                model_name='SaleReturn',
                record_id=sale_return.id,
                action='DELETE',
                user_id=current_user.id if current_user.is_authenticated else None
            )
            db.session.add(audit)
            db.session.flush()
        except Exception:
            pass
        
        db.session.delete(sale_return)
        db.session.commit()
        
        flash('تم حذف المرتجع بنجاح', 'success')
        return redirect(url_for('returns.list_returns'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في حذف المرتجع: {str(e)}', 'danger')
        return redirect(url_for('returns.view_return', return_id=return_id))


# ============================================================================
# API Endpoints
# ============================================================================

@returns_bp.route('/api/sale/<int:sale_id>/items')
@login_required
def get_sale_items(sale_id):
    """الحصول على بنود البيع لتسهيل إنشاء المرتجع"""
    try:
        sale = Sale.query.get_or_404(sale_id)

        # احسب الكمية المتاحة للإرجاع = كمية البيع - مجموع المرتجعات المؤكدة
        confirmed_returns = (
            db.session.query(
                SaleReturnLine.product_id, 
                func.coalesce(func.sum(SaleReturnLine.quantity), 0).label('returned_qty')
            )
            .join(SaleReturn, SaleReturnLine.sale_return_id == SaleReturn.id)
            .filter(
                SaleReturn.sale_id == sale.id, 
                SaleReturn.status == 'CONFIRMED'
            )
            .group_by(SaleReturnLine.product_id)
            .all()
        )
        
        # تحويل لـ dict
        product_id_to_returned = {int(pid): int(qty or 0) for pid, qty in confirmed_returns}

        # بناء قائمة المنتجات
        items = []
        for line in (sale.lines or []):
            original_qty = int(line.quantity or 0)
            returned_qty = product_id_to_returned.get(line.product_id, 0)
            available_qty = max(0, original_qty - returned_qty)
            
            items.append({
                'product_id': line.product_id,
                'product_name': line.product.name if line.product else 'غير معروف',
                'quantity': original_qty,
                'unit_price': float(line.unit_price or 0),
                'warehouse_id': line.warehouse_id,
                'returned_quantity': returned_qty,
                'returnable_quantity': available_qty
            })

        # جلب المخزن من أول سطر (أو None)
        first_warehouse_id = items[0]['warehouse_id'] if items else None
        
        return jsonify({
            'success': True,
            'sale_id': sale.id,
            'customer_id': sale.customer_id,
            'warehouse_id': first_warehouse_id,
            'currency': sale.currency or 'ILS',
            'items': items
        })
        
    except Exception as e:
        import traceback
        print(f"❌ Error in get_sale_items for sale_id={sale_id}: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@returns_bp.route('/api/customer/<int:customer_id>/sales')
@login_required
def get_customer_sales(customer_id: int):
    """إرجاع آخر المبيعات المؤكدة لعميل محدد لتصفية قائمة الفواتير في المرتجع"""
    try:
        sales = (
            Sale.query
            .filter_by(customer_id=customer_id, status='CONFIRMED')
            .order_by(Sale.id.desc())
            .limit(100)
            .all()
        )
        data = []
        for s in sales:
            # جلب المخزن من أول سطر بيع
            first_wh = None
            if s.lines and len(s.lines) > 0:
                first_wh = s.lines[0].warehouse_id
            
            data.append({
                'id': s.id,
                'date': (s.created_at.strftime('%Y-%m-%d') if getattr(s, 'created_at', None) else ''),
                'warehouse_id': first_wh,
                'currency': s.currency or 'ILS'
            })
        return jsonify({'success': True, 'sales': data})
    except Exception as e:
        print(f"❌ Error in get_customer_sales: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

