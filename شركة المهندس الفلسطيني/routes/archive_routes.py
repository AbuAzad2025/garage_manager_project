
from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Archive, Shipment, Check

archive_routes_bp = Blueprint('archive_routes', __name__)

@archive_routes_bp.route("/shipments/archive/<int:shipment_id>", methods=["POST"])
@login_required
def archive_shipment(shipment_id):
    
    try:
        shipment = Shipment.query.get_or_404(shipment_id)
        print(f"✅ [SHIPMENT ARCHIVE] تم العثور على الشحنة: {shipment.id}")
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        print(f"📝 [SHIPMENT ARCHIVE] سبب الأرشفة: {reason}")
        
        archive = Archive.archive_record(
            record=shipment,
            reason=reason,
            user_id=current_user.id
        )
        from datetime import datetime
        shipment.is_archived = True
        shipment.archived_at = datetime.utcnow()
        shipment.archived_by = current_user.id
        shipment.archive_reason = reason
        db.session.commit()
        flash(f'تم أرشفة الشحنة رقم {shipment.id} بنجاح', 'success')
        return redirect(url_for('shipments_bp.list_shipments'))
        
    except Exception as e:
        print(f"❌ [SHIPMENT ARCHIVE] خطأ في أرشفة الشحنة: {str(e)}")
        print(f"❌ [SHIPMENT ARCHIVE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [SHIPMENT ARCHIVE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في أرشفة الشحنة: {str(e)}', 'error')
        return redirect(url_for('shipments_bp.list_shipments'))

@archive_routes_bp.route("/checks/archive/<int:check_id>", methods=["POST"])
@login_required
def archive_check(check_id):
    
    try:
        check = Check.query.get_or_404(check_id)
        print(f"✅ [CHECK ARCHIVE] تم العثور على الشيك: {check.id}")
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        print(f"📝 [CHECK ARCHIVE] سبب الأرشفة: {reason}")
        
        archive = Archive.archive_record(
            record=check,
            reason=reason,
            user_id=current_user.id
        )
        from datetime import datetime
        check.is_archived = True
        check.archived_at = datetime.utcnow()
        check.archived_by = current_user.id
        check.archive_reason = reason
        db.session.commit()
        flash(f'تم أرشفة الشيك رقم {check.id} بنجاح', 'success')
        return redirect(url_for('checks.index'))
        
    except Exception as e:
        print(f"❌ [CHECK ARCHIVE] خطأ في أرشفة الشيك: {str(e)}")
        print(f"❌ [CHECK ARCHIVE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [CHECK ARCHIVE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في أرشفة الشيك: {str(e)}', 'error')
        return redirect(url_for('checks.index'))
