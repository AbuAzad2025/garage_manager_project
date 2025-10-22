#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌱 بذور البنية الأساسية فقط
════════════════════════════════════════════════════════════════
ينشئ:
- مستودع من كل نوع
- منتجات متنوعة
- موردين وعملاء مرتبطين
- شركاء
- الفئات والتصنيفات
════════════════════════════════════════════════════════════════
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, '.')

from app import create_app
from extensions import db
from models import *
from sqlalchemy import text

def cleanup():
    """تنظيف البيانات"""
    print("\n🧹 تنظيف...")
    
    tables = [
        "payment_splits", "sale_lines", "invoice_lines", "service_parts", "service_tasks",
        "shipment_items", "shipment_partners", "product_partners", "warehouse_partner_shares",
        "payments", "sales", "invoices", "preorders", "service_requests", "shipments",
        "exchange_transactions", "stock_levels", "expenses", "notes",
        "products", "warehouses", "customers", "suppliers", "partners", "employees",
        "expense_types", "equipment_types", "product_categories", "exchange_rates",
    ]
    
    db.session.execute(text("PRAGMA foreign_keys = OFF"))
    for table in tables:
        try:
            db.session.execute(text(f"DELETE FROM {table}"))
        except:
            pass
    db.session.execute(text("PRAGMA foreign_keys = ON"))
    db.session.commit()
    print("   ✅ تم")

def seed():
    """إضافة البذور"""
    
    print("\n🌱 إضافة البنية الأساسية...\n")
    
    # 1. العملات
    print("💱 العملات...", end=" ")
    for code, name, symbol in [("ILS", "الشيكل", "₪"), ("USD", "الدولار", "$"), ("EUR", "اليورو", "€"), ("JOD", "الدينار", "د.ا")]:
        if not Currency.query.filter_by(code=code).first():
            db.session.add(Currency(code=code, name=name, symbol=symbol, is_active=True))
    db.session.commit()
    print(f"✅ {Currency.query.count()}")
    
    # 2. أسعار الصرف
    print("💱 أسعار الصرف...", end=" ")
    for base, quote, rate in [("USD", "ILS", 3.65), ("EUR", "ILS", 4.10), ("JOD", "ILS", 5.15)]:
        if not ExchangeRate.query.filter_by(base_code=base, quote_code=quote).first():
            db.session.add(ExchangeRate(base_code=base, quote_code=quote, rate=rate, valid_from=datetime.now(timezone.utc), source="MANUAL", is_active=True))
    db.session.commit()
    print(f"✅ {ExchangeRate.query.count()}")
    
    # 3. تصنيفات المنتجات
    print("📁 التصنيفات...", end=" ")
    for name in ["فلاتر", "زيوت", "إطارات", "بطاريات", "قطع محرك", "قطع كهرباء"]:
        if not ProductCategory.query.filter_by(name=name).first():
            db.session.add(ProductCategory(name=name, description=f"تصنيف {name}"))
    db.session.commit()
    print(f"✅ {ProductCategory.query.count()}")
    
    # 4. أنواع المعدات
    print("🚜 أنواع المعدات...", end=" ")
    for name, cat in [("جرافة", "حفر"), ("رافعة شوكية", "رفع"), ("شاحنة ثقيلة", "نقل"), ("خلاطة", "بناء")]:
        if not EquipmentType.query.filter_by(name=name).first():
            db.session.add(EquipmentType(name=name, category=cat))
    db.session.commit()
    print(f"✅ {EquipmentType.query.count()}")
    
    # 5. أنواع المصاريف
    print("💸 أنواع المصاريف...", end=" ")
    for name, desc in [("إيجار", "إيجارات"), ("رواتب", "رواتب"), ("كهرباء وماء", "فواتير"), ("صيانة", "صيانة"), ("مواصلات", "نقل")]:
        if not ExpenseType.query.filter_by(name=name).first():
            db.session.add(ExpenseType(name=name, description=desc))
    db.session.commit()
    print(f"✅ {ExpenseType.query.count()}")
    
    # 6. المستودعات - واحد من كل نوع
    print("🏢 المستودعات...", end=" ")
    warehouses_data = [
        {"name": "المستودع الرئيسي", "warehouse_type": "MAIN", "location": "رام الله", "capacity": 1000},
        {"name": "مستودع القطع", "warehouse_type": "PARTS", "location": "البيرة", "capacity": 500},
        {"name": "مستودع الشراكة", "warehouse_type": "PARTNER", "location": "نابلس", "capacity": 300},
        {"name": "مستودع التبادل", "warehouse_type": "EXCHANGE", "location": "الخليل", "capacity": 400},
        {"name": "المتجر الإلكتروني", "warehouse_type": "ONLINE", "location": "افتراضي", "capacity": 0, "online_is_default": True},
    ]
    for wh_data in warehouses_data:
        if not Warehouse.query.filter_by(name=wh_data["name"]).first():
            db.session.add(Warehouse(**wh_data))
    db.session.commit()
    print(f"✅ {Warehouse.query.count()}")
    
    # 7. الموردون
    print("📦 الموردون...", end=" ")
    suppliers_data = [
        {"name": "مؤسسة القدس للقطع", "phone": "0599111222", "email": "alquds@test.ps", "currency": "ILS", "address": "القدس"},
        {"name": "شركة الأقصى التجارية", "phone": "0599222333", "email": "alaqsa@test.ps", "currency": "ILS", "address": "نابلس"},
        {"name": "Global Parts LLC", "phone": "+971501234567", "email": "global@test.ae", "currency": "USD", "address": "Dubai, UAE"},
    ]
    for sup_data in suppliers_data:
        if not Supplier.query.filter_by(email=sup_data["email"]).first():
            db.session.add(Supplier(**sup_data))
    db.session.commit()
    print(f"✅ {Supplier.query.count()}")
    
    # 8. الشركاء
    print("👥 الشركاء...", end=" ")
    partners_data = [
        {"name": "محمد أحمد", "phone_number": "0597111222", "email": "mohammed@test.ps", "identity_number": "123456789", "share_percentage": Decimal("50"), "currency": "ILS"},
        {"name": "عمر خليل", "phone_number": "0597222333", "email": "omar@test.ps", "identity_number": "987654321", "share_percentage": Decimal("30"), "currency": "ILS"},
        {"name": "سعيد حسن", "phone_number": "0597333444", "email": "saeed@test.ps", "identity_number": "456789123", "share_percentage": Decimal("20"), "currency": "ILS"},
    ]
    for par_data in partners_data:
        if not Partner.query.filter_by(email=par_data["email"]).first():
            db.session.add(Partner(**par_data))
    db.session.commit()
    print(f"✅ {Partner.query.count()}")
    
    # 9. العملاء (النظام سينشئ عميل مرتبط تلقائياً للموردين والشركاء)
    print("👤 العملاء...", end=" ")
    customers_data = [
        {"name": "شركة الإنشاءات الفلسطينية", "phone": "0599444555", "whatsapp": "0599444555", "email": "const.pal@test.ps", "category": "جملة", "currency": "ILS", "credit_limit": Decimal("50000")},
        {"name": "مؤسسة النهضة للمقاولات", "phone": "0599555666", "whatsapp": "0599555666", "email": "nahda@test.ps", "category": "جملة", "currency": "ILS", "credit_limit": Decimal("30000")},
        {"name": "كراج أبو علي", "phone": "0599666777", "whatsapp": "0599666777", "email": "aboali@test.ps", "category": "عادي", "currency": "ILS", "credit_limit": Decimal("10000")},
        {"name": "معدات الشرق", "phone": "0599777888", "whatsapp": "0599777888", "email": "sharq@test.ps", "category": "جملة", "currency": "JOD", "credit_limit": Decimal("20000")},
    ]
    for cust_data in customers_data:
        if not Customer.query.filter_by(email=cust_data["email"]).first():
            db.session.add(Customer(**cust_data))
    db.session.commit()
    print(f"✅ {Customer.query.count()}")
    
    # 10. ربط الموردين بعملاء (للمبيعات لهم)
    print("🔗 ربط موردين بعملاء...", end=" ")
    suppliers = Supplier.query.all()
    customers = Customer.query.all()
    
    # ربط أول مورد بأول عميل
    if len(suppliers) >= 1 and len(customers) >= 1:
        if not suppliers[0].customer_id:
            suppliers[0].customer_id = customers[0].id
    
    # ربط ثاني مورد بثاني عميل
    if len(suppliers) >= 2 and len(customers) >= 2:
        if not suppliers[1].customer_id:
            suppliers[1].customer_id = customers[1].id
    
    db.session.commit()
    print("✅")
    
    # 11. ربط الشركاء بعملاء
    print("🔗 ربط شركاء بعملاء...", end=" ")
    partners = Partner.query.all()
    
    # ربط أول شريك بثالث عميل
    if len(partners) >= 1 and len(customers) >= 3:
        if not partners[0].customer_id:
            partners[0].customer_id = customers[2].id
    
    db.session.commit()
    print("✅")
    
    # 12. الموظفون
    print("👷 الموظفون...", end=" ")
    employees_data = [
        {"name": "أحمد محمود", "position": "فني رئيسي", "phone": "0597777888", "email": "ahmad@test.ps"},
        {"name": "فاطمة حسن", "position": "محاسبة", "phone": "0597888999", "email": "fatima@test.ps"},
        {"name": "خالد سليم", "position": "مندوب مبيعات", "phone": "0597999000", "email": "khaled@test.ps"},
    ]
    for emp_data in employees_data:
        if not Employee.query.filter_by(email=emp_data["email"]).first():
            db.session.add(Employee(**emp_data))
    db.session.commit()
    print(f"✅ {Employee.query.count()}")
    
    # 13. المنتجات - متنوعة حسب المستودعات
    print("📦 المنتجات...", end=" ")
    
    cat_filter = ProductCategory.query.filter_by(name="فلاتر").first()
    cat_oil = ProductCategory.query.filter_by(name="زيوت").first()
    cat_tire = ProductCategory.query.filter_by(name="إطارات").first()
    cat_battery = ProductCategory.query.filter_by(name="بطاريات").first()
    cat_engine = ProductCategory.query.filter_by(name="قطع محرك").first()
    
    # موردين للربط
    sup1 = Supplier.query.first()
    sup2 = Supplier.query.offset(1).first() if Supplier.query.count() > 1 else None
    
    products_data = [
        # منتجات للمستودع الرئيسي
        {"name": "فلتر زيت CAT 1R-0750", "sku": "FLT-CAT-001", "category_id": cat_filter.id if cat_filter else None, 
         "price": Decimal("85"), "purchase_price": Decimal("60"), "unit": "قطعة", "currency": "ILS",
         "supplier_id": sup1.id if sup1 else None, "description": "فلتر زيت أصلي"},
        
        {"name": "زيت Mobil 15W-40 (20L)", "sku": "OIL-MOB-001", "category_id": cat_oil.id if cat_oil else None,
         "price": Decimal("320"), "purchase_price": Decimal("250"), "unit": "علبة", "currency": "ILS",
         "supplier_id": sup1.id if sup1 else None, "description": "زيت محرك للمعدات"},
        
        # منتجات للمستودع الشراكة (بالدولار)
        {"name": "إطار Michelin 24R21", "sku": "TIRE-MICH-001", "category_id": cat_tire.id if cat_tire else None,
         "price": Decimal("1850"), "purchase_price": Decimal("1500"), "unit": "قطعة", "currency": "USD",
         "supplier_id": sup2.id if sup2 else None, "description": "إطار للمعدات الثقيلة"},
        
        {"name": "بطارية VARTA 200Ah", "sku": "BAT-VAR-001", "category_id": cat_battery.id if cat_battery else None,
         "price": Decimal("950"), "purchase_price": Decimal("750"), "unit": "قطعة", "currency": "ILS",
         "supplier_id": sup2.id if sup2 else None, "description": "بطارية ثقيلة"},
        
        # منتجات للتبادل
        {"name": "فلتر هواء Donaldson", "sku": "FLT-DON-001", "category_id": cat_filter.id if cat_filter else None,
         "price": Decimal("120"), "purchase_price": Decimal("85"), "unit": "قطعة", "currency": "ILS",
         "supplier_id": sup1.id if sup1 else None, "description": "فلتر هواء"},
        
        {"name": "محرك CAT C15", "sku": "ENG-CAT-001", "category_id": cat_engine.id if cat_engine else None,
         "price": Decimal("45000"), "purchase_price": Decimal("38000"), "unit": "قطعة", "currency": "USD",
         "supplier_id": sup2.id if sup2 else None, "description": "محرك ديزل كامل"},
    ]
    
    for prod_data in products_data:
        if not Product.query.filter_by(sku=prod_data["sku"]).first():
            db.session.add(Product(**prod_data))
    db.session.commit()
    print(f"✅ {Product.query.count()}")
    
    # 14. ربط المستودعات بالشركاء
    print("🤝 ربط مستودع الشراكة بالشركاء...", end=" ")
    wh_partner = Warehouse.query.filter_by(warehouse_type="PARTNER").first()
    partners = Partner.query.all()
    
    if wh_partner and len(partners) >= 2:
        # ربط المستودع بأول شريكين
        if not wh_partner.partner_id:
            wh_partner.partner_id = partners[0].id  # الشريك الرئيسي
            wh_partner.share_percent = Decimal("100")  # يملك المستودع كاملاً
        db.session.commit()
    print("✅")
    
    # 15. ربط مستودع التبادل بالموردين
    print("🔗 ربط مستودع التبادل بالموردين...", end=" ")
    wh_exchange = Warehouse.query.filter_by(warehouse_type="EXCHANGE").first()
    
    if wh_exchange and sup1:
        if not wh_exchange.supplier_id:
            wh_exchange.supplier_id = sup1.id
        db.session.commit()
    print("✅")
    
    # 16. المخزون - إضافة منتجات لكل مستودع (بسيط)
    print("\n📊 إضافة المخزون لكل مستودع...")
    
    # استخدام SQL مباشرة لتجنب مشاكل autoflush
    warehouses_info = db.session.execute(text("SELECT id, name, warehouse_type FROM warehouses")).fetchall()
    products_info = db.session.execute(text("SELECT id, name FROM products")).fetchall()
    
    if warehouses_info and products_info:
        for wh_id, wh_name, wh_type in warehouses_info:
            count = 0
            
            if wh_type == "MAIN":
                # جميع المنتجات
                for i, (prod_id, prod_name) in enumerate(products_info):
                    qty = [100, 80, 50, 30, 120, 20][i] if i < 6 else 50
                    db.session.execute(text(
                        "INSERT OR IGNORE INTO stock_levels (warehouse_id, product_id, quantity, reserved_quantity) VALUES (:wh, :prod, :qty, 0)"
                    ), {"wh": wh_id, "prod": prod_id, "qty": qty})
                    count += 1
                    
            elif wh_type == "PARTS":
                # القطع الصغيرة فقط
                for prod_id, prod_name in products_info:
                    if any(word in prod_name for word in ["فلتر", "بطارية"]):
                        db.session.execute(text(
                            "INSERT OR IGNORE INTO stock_levels (warehouse_id, product_id, quantity, reserved_quantity) VALUES (:wh, :prod, 200, 0)"
                        ), {"wh": wh_id, "prod": prod_id})
                        count += 1
                        
            elif wh_type == "PARTNER":
                # منتجات كبيرة للشركاء
                for prod_id, prod_name in products_info:
                    if any(word in prod_name for word in ["إطار", "محرك", "بطارية"]):
                        db.session.execute(text(
                            "INSERT OR IGNORE INTO stock_levels (warehouse_id, product_id, quantity, reserved_quantity) VALUES (:wh, :prod, 15, 0)"
                        ), {"wh": wh_id, "prod": prod_id})
                        count += 1
                        
            elif wh_type == "EXCHANGE":
                # أول 4 منتجات للتبادل
                quantities = [25, 40, 10, 30]
                for i, (prod_id, prod_name) in enumerate(products_info[:4]):
                    qty = quantities[i] if i < len(quantities) else 20
                    db.session.execute(text(
                        "INSERT OR IGNORE INTO stock_levels (warehouse_id, product_id, quantity, reserved_quantity) VALUES (:wh, :prod, :qty, 0)"
                    ), {"wh": wh_id, "prod": prod_id, "qty": qty})
                    count += 1
                    
            elif wh_type == "ONLINE":
                # أول 3 منتجات للمتجر
                for prod_id, prod_name in products_info[:3]:
                    db.session.execute(text(
                        "INSERT OR IGNORE INTO stock_levels (warehouse_id, product_id, quantity, reserved_quantity) VALUES (:wh, :prod, 50, 0)"
                    ), {"wh": wh_id, "prod": prod_id})
                    count += 1
            
            if count > 0:
                print(f"   🏢 {wh_name}: ✅ {count} منتج")
        
        db.session.commit()
    
    print("\n" + "="*80)
    print("✅ تم إضافة البنية الأساسية بنجاح!")
    print("="*80)
    
    # ملخص نهائي
    print("\n📊 الملخص النهائي:")
    print(f"   💱 العملات: {Currency.query.count()}")
    print(f"   💱 أسعار الصرف: {ExchangeRate.query.count()}")
    print(f"   📁 تصنيفات المنتجات: {ProductCategory.query.count()}")
    print(f"   🚜 أنواع المعدات: {EquipmentType.query.count()}")
    print(f"   💸 أنواع المصاريف: {ExpenseType.query.count()}")
    print(f"   🏢 المستودعات: {Warehouse.query.count()}")
    print(f"   📦 الموردون: {Supplier.query.count()}")
    print(f"   👥 الشركاء: {Partner.query.count()}")
    print(f"   👤 العملاء: {Customer.query.count()}")
    print(f"   👷 الموظفون: {Employee.query.count()}")
    print(f"   📦 المنتجات: {Product.query.count()}")
    print(f"   📊 المخزون: {StockLevel.query.count()}")
    print(f"   👤 المستخدمون (محفوظ): {User.query.count()}")
    
    print("\n🎯 الآن يمكنك تجربة:")
    print("   - إنشاء مبيعات")
    print("   - إنشاء صيانات")
    print("   - إنشاء حجوزات")
    print("   - إضافة شحنات")
    print("   - إجراء دفعات")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            cleanup()
            seed()
            print("\n🎉 تم بنجاح!")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ خطأ: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

