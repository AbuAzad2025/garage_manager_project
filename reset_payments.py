# reset_payments.py - Reset Payments Utility
# Location: /garage_manager/reset_payments.py

from app import app, db
from models import Payment, PaymentSplit

with app.app_context():
    print("\n" + "="*80)
    print("حذف الدفعات TEST")
    print("="*80 + "\n")
    
    splits_deleted = db.session.query(PaymentSplit).filter(
        PaymentSplit.payment_id.in_(
            db.session.query(Payment.id).filter(
                Payment.notes.like('%TEST%')
            )
        )
    ).delete(synchronize_session=False)
    
    print(f"✓ حذف {splits_deleted} split")
    
    payments_deleted = db.session.query(Payment).filter(
        Payment.notes.like('%TEST%')
    ).delete(synchronize_session=False)
    
    print(f"✓ حذف {payments_deleted} دفعة")
    
    db.session.commit()
    
    print("\n" + "="*80)
    print("✅ تم حذف جميع الدفعات TEST")
    print("="*80 + "\n")

