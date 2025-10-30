"""
🧪 اختبار دالة استخراج الجهات من القيود المحاسبية
====================================================

هذا ملف اختبار بسيط للتأكد من عمل الدالة الجديدة extract_entity_from_batch()
"""

from app import app, db
from models import GLBatch, Payment, Sale, Customer, Supplier, Partner
from routes.ledger_blueprint import extract_entity_from_batch


def test_extract_entity_from_payment():
    """اختبار استخراج الجهة من الدفعة"""
    with app.app_context():
        # البحث عن أول دفعة في النظام
        payment = Payment.query.first()
        if not payment:
            print("❌ لا توجد دفعات في النظام")
            return
        
        # إنشاء GLBatch وهمي
        batch = GLBatch(
            source_type='PAYMENT',
            source_id=payment.id,
            entity_type=None,
            entity_id=None
        )
        
        # استخراج الجهة
        entity_name, entity_type_ar, entity_id, entity_type_code = extract_entity_from_batch(batch)
        
        print(f"\n✅ اختبار الدفعة #{payment.id}")
        print(f"   📝 اسم الجهة: {entity_name}")
        print(f"   🏷️  نوع الجهة: {entity_type_ar}")
        print(f"   🔢 معرف الجهة: {entity_id}")
        print(f"   💻 كود النوع: {entity_type_code}")
        
        # التحقق من النتيجة
        if payment.customer_id and entity_name != '—':
            print(f"   ✅ نجح: تم استخراج العميل بشكل صحيح")
        elif payment.supplier_id and entity_name != '—':
            print(f"   ✅ نجح: تم استخراج المورد بشكل صحيح")
        elif payment.partner_id and entity_name != '—':
            print(f"   ✅ نجح: تم استخراج الشريك بشكل صحيح")
        else:
            print(f"   ⚠️  تحذير: لم يتم استخراج جهة (قد يكون هذا طبيعياً)")


def test_extract_entity_from_sale():
    """اختبار استخراج الجهة من المبيعات"""
    with app.app_context():
        # البحث عن أول مبيعة في النظام
        sale = Sale.query.first()
        if not sale:
            print("❌ لا توجد مبيعات في النظام")
            return
        
        # إنشاء GLBatch وهمي
        batch = GLBatch(
            source_type='SALE',
            source_id=sale.id,
            entity_type=None,
            entity_id=None
        )
        
        # استخراج الجهة
        entity_name, entity_type_ar, entity_id, entity_type_code = extract_entity_from_batch(batch)
        
        print(f"\n✅ اختبار المبيعات #{sale.id}")
        print(f"   📝 اسم الجهة: {entity_name}")
        print(f"   🏷️  نوع الجهة: {entity_type_ar}")
        print(f"   🔢 معرف الجهة: {entity_id}")
        print(f"   💻 كود النوع: {entity_type_code}")
        
        # التحقق من النتيجة
        if sale.customer_id and entity_name != '—':
            print(f"   ✅ نجح: تم استخراج العميل بشكل صحيح")
            if sale.customer:
                expected_name = sale.customer.name
                if entity_name == expected_name:
                    print(f"   ✅ التطابق: الاسم المستخرج يطابق اسم العميل الفعلي")
                else:
                    print(f"   ❌ خطأ: الاسم المستخرج لا يطابق اسم العميل")
                    print(f"      المتوقع: {expected_name}")
                    print(f"      الفعلي: {entity_name}")
        else:
            print(f"   ⚠️  تحذير: لم يتم استخراج جهة")


def test_extract_entity_with_entity_type():
    """اختبار استخراج الجهة من entity_type و entity_id المباشرة"""
    with app.app_context():
        # البحث عن أول عميل
        customer = Customer.query.first()
        if not customer:
            print("❌ لا يوجد عملاء في النظام")
            return
        
        # إنشاء GLBatch مع entity_type و entity_id
        batch = GLBatch(
            source_type='MANUAL',
            source_id=999,
            entity_type='CUSTOMER',
            entity_id=customer.id
        )
        
        # استخراج الجهة
        entity_name, entity_type_ar, entity_id, entity_type_code = extract_entity_from_batch(batch)
        
        print(f"\n✅ اختبار entity_type المباشر")
        print(f"   📝 اسم الجهة: {entity_name}")
        print(f"   🏷️  نوع الجهة: {entity_type_ar}")
        print(f"   🔢 معرف الجهة: {entity_id}")
        print(f"   💻 كود النوع: {entity_type_code}")
        
        # التحقق من النتيجة
        if entity_name == customer.name:
            print(f"   ✅ نجح: الاسم المستخرج يطابق اسم العميل")
        else:
            print(f"   ❌ خطأ: عدم تطابق الأسماء")


def test_all_entity_types():
    """اختبار جميع أنواع الجهات"""
    with app.app_context():
        print("\n" + "="*60)
        print("🧪 اختبار شامل لجميع أنواع الجهات")
        print("="*60)
        
        # اختبار العملاء
        customer_count = Customer.query.count()
        print(f"\n👥 العملاء: {customer_count}")
        if customer_count > 0:
            test_extract_entity_with_entity_type()
        
        # اختبار الموردين
        supplier_count = Supplier.query.count()
        print(f"\n🚚 الموردين: {supplier_count}")
        if supplier_count > 0:
            supplier = Supplier.query.first()
            batch = GLBatch(
                source_type='MANUAL',
                source_id=999,
                entity_type='SUPPLIER',
                entity_id=supplier.id
            )
            entity_name, entity_type_ar, _, _ = extract_entity_from_batch(batch)
            print(f"   📝 اسم المورد: {entity_name}")
            print(f"   ✅ نجح" if entity_name == supplier.name else "   ❌ فشل")
        
        # اختبار الشركاء
        partner_count = Partner.query.count()
        print(f"\n🤝 الشركاء: {partner_count}")
        if partner_count > 0:
            partner = Partner.query.first()
            batch = GLBatch(
                source_type='MANUAL',
                source_id=999,
                entity_type='PARTNER',
                entity_id=partner.id
            )
            entity_name, entity_type_ar, _, _ = extract_entity_from_batch(batch)
            print(f"   📝 اسم الشريك: {entity_name}")
            print(f"   ✅ نجح" if entity_name == partner.name else "   ❌ فشل")
        
        # اختبار الدفعات
        payment_count = Payment.query.count()
        print(f"\n💰 الدفعات: {payment_count}")
        if payment_count > 0:
            test_extract_entity_from_payment()
        
        # اختبار المبيعات
        sale_count = Sale.query.count()
        print(f"\n🛒 المبيعات: {sale_count}")
        if sale_count > 0:
            test_extract_entity_from_sale()
        
        print("\n" + "="*60)
        print("✅ انتهى الاختبار")
        print("="*60)


if __name__ == '__main__':
    print("""
    🧪 اختبار دالة استخراج الجهات من القيود المحاسبية
    ====================================================
    
    هذا الاختبار يتحقق من:
    ✓ استخراج الجهة من entity_type و entity_id
    ✓ استخراج الجهة من source_type و source_id (PAYMENT)
    ✓ استخراج الجهة من source_type و source_id (SALE)
    ✓ جميع أنواع الجهات (عملاء، موردين، شركاء)
    
    """)
    
    test_all_entity_types()

