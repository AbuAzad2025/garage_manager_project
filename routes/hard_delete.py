
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf

from services.hard_delete_service import HardDeleteService, DeletionConfirmationService
from models import DeletionLog, DeletionType, DeletionStatus, db
from sqlalchemy.orm import joinedload
import utils
from routes.vendors import vendors_bp

hard_delete_bp = Blueprint("hard_delete_bp", __name__, url_prefix="/hard-delete")








# تم إزالة route التأكيد بالكود - الحذف أصبح مباشر


@hard_delete_bp.route("/logs")
@login_required
def deletion_logs():
    """سجل عمليات الحذف"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    
    query = db.session.query(DeletionLog).options(
        joinedload(DeletionLog.deleted_by_user),
        joinedload(DeletionLog.restored_by_user)
    )
    
    # فلترة
    status = request.args.get("status")
    if status:
        query = query.filter(DeletionLog.status == status)
    
    deletion_type = request.args.get("type")
    if deletion_type:
        query = query.filter(DeletionLog.deletion_type == deletion_type)
    
    # ترتيب
    query = query.order_by(DeletionLog.created_at.desc())
    
    # صفحة
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        "hard_delete/logs.html",
        pagination=pagination,
        status=status,
        deletion_type=deletion_type
    )


@hard_delete_bp.route("/restore/<int:deletion_id>", methods=["GET", "POST"])
@login_required
def restore_deletion(deletion_id):
    """استعادة عملية حذف"""
    deletion_log = db.session.get(DeletionLog, deletion_id)
    if not deletion_log:
        flash("سجل الحذف غير موجود", "error")
        return redirect(url_for("hard_delete_bp.deletion_logs"))
    
    if not deletion_log.can_restore:
        flash("لا يمكن استعادة هذا الحذف", "error")
        return redirect(url_for("hard_delete_bp.deletion_logs"))
    
    if request.method == "GET":
        return render_template(
            "hard_delete/confirm_restore.html",
            deletion_log=deletion_log,
        )
    
    elif request.method == "POST":
        if request.form.get("confirm") == "yes":
            notes = request.form.get("notes", "").strip()
            
            hard_delete_service = HardDeleteService()
            result = hard_delete_service.restore_deletion(deletion_id, current_user.id, notes)
            
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
            
            return redirect(url_for("hard_delete_bp.deletion_logs"))
        else:
            flash("تم إلغاء عملية الاستعادة", "info")
            return redirect(url_for("hard_delete_bp.deletion_logs"))


@hard_delete_bp.route("/api/delete-customer/<int:customer_id>", methods=["POST"])
@login_required
def api_delete_customer(customer_id):
    """API لحذف العميل"""
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip()
    
    if not reason:
        return jsonify({"success": False, "error": "يجب إدخال سبب الحذف"}), 400
    
    hard_delete_service = HardDeleteService()
    result = hard_delete_service.delete_customer(customer_id, current_user.id, reason)
    
    return jsonify(result)


 




@hard_delete_bp.route("/supplier/<int:supplier_id>", methods=["GET", "POST"]) 
@login_required
def delete_supplier(supplier_id):
    """حذف قوي للمورد مع التأكيد"""
    if request.method == "GET":
        # عرض صفحة التأكيد
        from models import Supplier
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            flash("المورد غير موجود", "error")
            return redirect(url_for("vendors_bp.suppliers_list"))
        
        # جمع المعلومات المرتبطة
        from models import Payment, ExchangeTransaction
        payments_count = db.session.query(Payment).filter_by(supplier_id=supplier_id).count()
        # Shipment لا يحتوي على supplier_id، استخدم ExchangeTransaction بدلاً منه
        purchases_count = db.session.query(ExchangeTransaction).filter_by(supplier_id=supplier_id).count()
        
        return render_template(
            "hard_delete/confirm_supplier.html",
            supplier=supplier,
            payments_count=payments_count,
            purchases_count=purchases_count
        )
    
    elif request.method == "POST":
        # تنفيذ الحذف
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("يجب إدخال سبب الحذف", "error")
            from models import Supplier, Payment, Expense
            supplier = db.session.get(Supplier, supplier_id)
            return render_template(
                "hard_delete/confirm_supplier.html",
                supplier=supplier,
                payments_count=db.session.query(Payment).filter_by(supplier_id=supplier_id).count(),
                purchases_count=db.session.query(Expense).filter_by(payee_type='SUPPLIER', payee_entity_id=supplier_id).count(),
                error="يجب إدخال سبب الحذف"
            )
        
        # تنفيذ الحذف مباشرة
        hard_delete_service = HardDeleteService()
        result = hard_delete_service.delete_supplier(supplier_id, current_user.id, reason)
        
        if result.get("success"):
            flash("تم حذف المورد بنجاح", "success")
            return redirect(url_for("vendors_bp.suppliers_list"))
        else:
            flash(f"فشل في حذف المورد: {result.get('error', 'خطأ غير معروف')}", "error")
            from models import Supplier, Payment, Expense
            supplier = db.session.get(Supplier, supplier_id)
            return render_template(
                "hard_delete/confirm_supplier.html",
                supplier=supplier,
                payments_count=db.session.query(Payment).filter_by(supplier_id=supplier_id).count(),
                purchases_count=db.session.query(Expense).filter_by(payee_type='SUPPLIER', payee_entity_id=supplier_id).count(),
                error=result.get('error')
            )


@hard_delete_bp.route("/partner/<int:partner_id>", methods=["GET", "POST"]) 
@login_required
def delete_partner(partner_id):
    """حذف قوي للشريك مع التأكيد"""
    if request.method == "GET":
        # عرض صفحة التأكيد
        from models import Partner
        partner = db.session.get(Partner, partner_id)
        if not partner:
            flash("الشريك غير موجود", "error")
            return redirect(url_for("vendors_bp.partners_list"))
        
        # جمع المعلومات المرتبطة
        from models import Payment, Sale
        payments_count = db.session.query(Payment).filter_by(partner_id=partner_id).count()
        sales_count = db.session.query(Sale).filter_by(customer_id=partner_id).count()
        
        return render_template(
            "hard_delete/confirm_partner.html",
            partner=partner,
            payments_count=payments_count,
            sales_count=sales_count
        )
    
    elif request.method == "POST":
        # تنفيذ الحذف
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("يجب إدخال سبب الحذف", "error")
            from models import Partner, Payment
            return render_template(
                "hard_delete/confirm_partner.html",
                partner=db.session.get(Partner, partner_id),
                payments_count=db.session.query(Payment).filter_by(partner_id=partner_id).count(),
                sales_count=0,
                error="يجب إدخال سبب الحذف"
            )
        
        # تنفيذ الحذف مباشرة
        hard_delete_service = HardDeleteService()
        result = hard_delete_service.delete_partner(partner_id, current_user.id, reason)
        
        if result.get("success"):
            flash("تم حذف الشريك بنجاح", "success")
            return redirect(url_for("vendors_bp.partners_list"))
        else:
            flash(f"فشل في حذف الشريك: {result.get('error', 'خطأ غير معروف')}", "error")
            from models import Partner, Payment
            return render_template(
                "hard_delete/confirm_partner.html",
                partner=db.session.get(Partner, partner_id),
                payments_count=db.session.query(Payment).filter_by(partner_id=partner_id).count(),
                sales_count=0,
                error=result.get('error')
            )


 




@hard_delete_bp.route("/expense/<int:expense_id>", methods=["GET", "POST"]) 
@login_required
def delete_expense(expense_id):
    """حذف قوي للمصروف مع التأكيد"""
    if request.method == "GET":
        # عرض صفحة التأكيد
        from models import Expense
        expense = db.session.get(Expense, expense_id)
        if not expense:
            flash("المصروف غير موجود", "error")
            return redirect(url_for("expenses_bp.list_expenses"))
        
        return render_template(
            "hard_delete/confirm_expense.html",
            expense=expense,
        )
    
    elif request.method == "POST":
        # تنفيذ الحذف
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("يجب إدخال سبب الحذف", "error")
            from models import Expense
            expense = db.session.get(Expense, expense_id)
            return render_template(
                "hard_delete/confirm_expense.html",
                expense=expense,
                error="يجب إدخال سبب الحذف"
            )
        
        # تنفيذ الحذف مباشرة
        hard_delete_service = HardDeleteService()
        result = hard_delete_service.delete_expense(expense_id, current_user.id, reason)
        
        if result.get("success"):
            flash("تم حذف المصروف بنجاح", "success")
            return redirect(url_for("expenses_bp.list_expenses"))
        else:
            flash(f"فشل في حذف المصروف: {result.get('error', 'خطأ غير معروف')}", "error")
            from models import Expense
            expense = db.session.get(Expense, expense_id)
            return render_template(
                "hard_delete/confirm_expense.html",
                expense=expense,
                error=result.get('error')
            )





@hard_delete_bp.route("/api/restore/<int:deletion_id>", methods=["POST"]) 
@login_required
def api_restore_deletion(deletion_id):
    """API لاستعادة الحذف"""
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "").strip()
    
    hard_delete_service = HardDeleteService()
    result = hard_delete_service.restore_deletion(deletion_id, current_user.id, notes)
    
    return jsonify(result)


@hard_delete_bp.route("/check/<int:check_id>", methods=["GET", "POST"]) 
@login_required
def delete_check(check_id):
    """حذف قوي للشيك"""
    from models import Check
    
    if request.method == "GET":
        check = db.session.get(Check, check_id)
        if not check:
            flash("الشيك غير موجود", "error")
            return redirect(url_for("checks.index"))
        
        return render_template("hard_delete/confirm_check.html", check=check)
    
    elif request.method == "POST":
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("يجب إدخال سبب الحذف", "error")
            check = db.session.get(Check, check_id)
            return render_template("hard_delete/confirm_check.html", check=check, error="يجب إدخال سبب الحذف")
        
        hard_delete_service = HardDeleteService()
        result = hard_delete_service.delete_check(check_id, current_user.id, reason)
        
        if result.get("success"):
            flash(f"✅ {result.get('message')} - يمكن الاستعادة من سجل الحذف القوي", "success")
            return redirect(url_for("checks.index"))
        else:
            flash(f"❌ {result.get('error')}", "error")
            check = db.session.get(Check, check_id)
            return render_template("hard_delete/confirm_check.html", check=check, error=result.get('error'))

@hard_delete_bp.route("/service/<int:service_id>", methods=["GET", "POST"], endpoint="hard_delete_service")
@login_required
def hard_delete_service(service_id):
    """حذف قوي لطلب صيانة"""
    from models import ServiceRequest
    
    service = ServiceRequest.query.get_or_404(service_id)
    
    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("يجب تحديد سبب الحذف", "error")
            return render_template("hard_delete/delete_service.html", service=service)
        
        hard_delete_service = HardDeleteService()
        result = hard_delete_service.delete_service(service_id, current_user.id, reason)
        
        if result.get("success"):
            flash("✅ تم حذف طلب الصيانة بنجاح - تم إرجاع قطع الغيار للمخزون", "success")
            return redirect(url_for("service.list_requests"))
        else:
            flash(f"❌ فشل في حذف طلب الصيانة: {result.get('error', 'خطأ غير معروف')}", "error")
            return render_template("hard_delete/delete_service.html", service=service)
    
    return render_template("hard_delete/delete_service.html", service=service)
