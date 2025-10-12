#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
بذور شاملة كاملة لنظام إدارة الكراج
Complete Comprehensive Seeds for Garage Management System
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
import random

# إضافة مسار المشروع
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import (
    # الموردين والشركاء
    Supplier, Partner,
    
    # المنتجات والفئات
    Product, ProductCategory, EquipmentType,
    
    # المستودعات والمخزون
    Warehouse, WarehouseType, StockLevel, ExchangeTransaction,
    
    # العملاء
    Customer,
    
    # المبيعات
    Sale, SaleLine, SaleStatus,
    
    # الدفعات
    Payment, PaymentStatus, PaymentDirection, PaymentMethod,
    
    # الصيانة
    ServiceRequest, ServicePart, ServiceStatus,
    
    # الشحنات
    Shipment, ShipmentStatus,
    
    # النفقات
    Expense,
    
    # العملات
    Currency, ExchangeRate,
    
    # المستخدمين
    User, Role,
)


def init_db():
    """تهيئة قاعدة البيانات"""
    with app.app_context():
        print("🔧 تهيئة قاعدة البيانات...")
        db.create_all()
        print("✅ تم تهيئة قاعدة البيانات")


def seed_users():
    """إضافة مستخدمين"""
    print("\n👥 إضافة مستخدمين...")
    
    # التحقق من وجود دور admin
    admin_role = db.session.query(Role).filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin', description='مدير النظام')
        db.session.add(admin_role)
        db.session.commit()
    
    # إضافة مستخدم تجريبي
    test_user = db.session.query(User).filter_by(username='test_admin').first()
    if not test_user:
        test_user = User(
            username='test_admin',
            email='test@garage.local',
            is_active=True
        )
        test_user.set_password('test123')
        db.session.add(test_user)
        db.session.commit()
        print("✅ تم إضافة مستخدم: test_admin / test123")
    else:
        print("ℹ️  المستخدم test_admin موجود مسبقاً")
    
    return test_user


def seed_currencies():
    """إضافة العملات وأسعار الصرف"""
    print("\n💱 إضافة العملات وأسعار الصرف...")
    
    currencies_data = [
        {"code": "ILS", "name": "شيكل إسرائيلي", "symbol": "₪", "is_active": True},
        {"code": "USD", "name": "دولار أمريكي", "symbol": "$", "is_active": True},
        {"code": "EUR", "name": "يورو", "symbol": "€", "is_active": True},
        {"code": "JOD", "name": "دينار أردني", "symbol": "JD", "is_active": True},
        {"code": "AED", "name": "درهم إماراتي", "symbol": "د.إ", "is_active": True},
    ]
    
    for curr_data in currencies_data:
        curr = db.session.query(Currency).filter_by(code=curr_data["code"]).first()
        if not curr:
            curr = Currency(**curr_data)
            db.session.add(curr)
    
    db.session.commit()
    
    # أسعار الصرف يدوية (محلية)
    exchange_rates = [
        {"base": "USD", "quote": "ILS", "rate": Decimal("3.65")},
        {"base": "EUR", "quote": "ILS", "rate": Decimal("4.05")},
        {"base": "JOD", "quote": "ILS", "rate": Decimal("5.15")},
        {"base": "AED", "quote": "ILS", "rate": Decimal("0.99")},
    ]
    
    for rate_data in exchange_rates:
        existing = db.session.query(ExchangeRate).filter_by(
            base_code=rate_data["base"],
            quote_code=rate_data["quote"]
        ).first()
        
        if not existing:
            rate = ExchangeRate(
                base_code=rate_data["base"],
                quote_code=rate_data["quote"],
                rate=rate_data["rate"],
                valid_from=datetime.utcnow(),
                is_manual=True
            )
            db.session.add(rate)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(currencies_data)} عملات و {len(exchange_rates)} سعر صرف")


def seed_suppliers():
    """إضافة موردين متنوعين"""
    print("\n🏢 إضافة موردين...")
    
    suppliers_data = [
        {"name": "شركة الأجزاء الذهبية TEST", "phone": "0599111222", "email": "golden-test@parts.ps", "currency": "ILS", 
         "address": "رام الله - البيرة", "contact": "أحمد محمود", "notes": "[TEST] مورد محلي رئيسي"},
        
        {"name": "مورد القطع الأمريكية TEST", "phone": "0597222333", "email": "usa-test@parts.com", "currency": "USD", 
         "address": "نيويورك - الولايات المتحدة", "contact": "John Smith", "notes": "[TEST] مورد أمريكي"},
        
        {"name": "المورد الأوروبي للزيوت TEST", "phone": "0598333444", "email": "euro-test@oils.de", "currency": "EUR", 
         "address": "برلين - ألمانيا", "contact": "Hans Mueller", "notes": "[TEST] مورد ألماني"},
        
        {"name": "مورد الإطارات الأردني TEST", "phone": "0596444555", "email": "jordan-test@tires.jo", "currency": "JOD", 
         "address": "عمان - الأردن", "contact": "خالد العمري", "notes": "[TEST] مورد أردني"},
        
        {"name": "مورد القطع الإماراتي TEST", "phone": "0595555666", "email": "uae-test@parts.ae", "currency": "AED", 
         "address": "دبي - الإمارات", "contact": "سالم المزروعي", "notes": "[TEST] مورد إماراتي"},
    ]
    
    suppliers = []
    for data in suppliers_data:
        existing = db.session.query(Supplier).filter_by(email=data["email"]).first()
        if existing:
            suppliers.append(existing)
        else:
            supplier = Supplier(**data, balance=Decimal('0'))
            db.session.add(supplier)
            suppliers.append(supplier)
    
    db.session.commit()
    print(f"✅ تم إضافة/تحديث {len(suppliers)} موردين بعملات مختلفة")
    return suppliers


def seed_partners():
    """إضافة شركاء"""
    print("\n🤝 إضافة شركاء...")
    
    partners_data = [
        {"name": "شريك محمد أحمد TEST", "phone_number": "0591111222", "email": "mohammad-test@partner.ps", 
         "share_percentage": Decimal('30'), "currency": "ILS", "notes": "[TEST] شريك رئيسي 30%"},
        
        {"name": "شريك خالد سعيد TEST", "phone_number": "0592222333", "email": "khaled-test@partner.ps", 
         "share_percentage": Decimal('25'), "currency": "ILS", "notes": "[TEST] شريك 25%"},
        
        {"name": "شريك سامر يوسف TEST", "phone_number": "0593333444", "email": "samer-test@partner.ps", 
         "share_percentage": Decimal('20'), "currency": "USD", "notes": "[TEST] شريك بالدولار 20%"},
        
        {"name": "شريك عمر حسن TEST", "phone_number": "0594444555", "email": "omar-test@partner.ps", 
         "share_percentage": Decimal('15'), "currency": "ILS", "notes": "[TEST] شريك 15%"},
    ]
    
    partners = []
    for data in partners_data:
        existing = db.session.query(Partner).filter_by(email=data["email"]).first()
        if existing:
            partners.append(existing)
        else:
            partner = Partner(**data, balance=Decimal('0'))
            db.session.add(partner)
            partners.append(partner)
    
    db.session.commit()
    print(f"✅ تم إضافة/تحديث {len(partners)} شركاء")
    return partners


def seed_customers():
    """إضافة عملاء"""
    print("\n👤 إضافة عملاء...")
    
    customers_data = [
        {"name": "عميل أحمد محمود TEST", "phone": "0599888777", "whatsapp": "0599888777", "email": "ahmad-test@customer.ps", 
         "address": "رام الله", "category": "VIP"},
        
        {"name": "عميل سامي حسن TEST", "phone": "0598777666", "whatsapp": "0598777666", "email": "sami-test@customer.ps", 
         "address": "نابلس", "category": "عادي"},
        
        {"name": "عميل كريم علي TEST", "phone": "0597666555", "whatsapp": "0597666555", "email": "karim-test@customer.ps", 
         "address": "الخليل", "category": "عادي"},
        
        {"name": "عميل ياسر خالد TEST", "phone": "0596555444", "whatsapp": "0596555444", "email": "yaser-test@customer.ps", 
         "address": "بيت لحم", "category": "عادي"},
        
        {"name": "عميل نبيل سعيد TEST", "phone": "0595444333", "whatsapp": "0595444333", "email": "nabil-test@customer.ps", 
         "address": "جنين", "category": "VIP"},
    ]
    
    customers = []
    for data in customers_data:
        existing = db.session.query(Customer).filter_by(email=data["email"]).first()
        if existing:
            customers.append(existing)
        else:
            customer = Customer(**data, notes="[TEST] عميل تجريبي")
            db.session.add(customer)
            customers.append(customer)
    
    db.session.commit()
    print(f"✅ تم إضافة/تحديث {len(customers)} عملاء")
    return customers


def seed_categories_and_equipment():
    """إضافة فئات المنتجات وأنواع المركبات"""
    print("\n📁 إضافة فئات المنتجات...")
    
    # فئات المنتجات
    categories_data = [
        {"name": "قطع محرك TEST", "description": "قطع غيار المحرك"},
        {"name": "قطع فرامل TEST", "description": "نظام الفرامل"},
        {"name": "زيوت وفلاتر TEST", "description": "زيوت التشحيم والفلاتر"},
        {"name": "إطارات TEST", "description": "الإطارات والعجلات"},
        {"name": "كهرباء TEST", "description": "النظام الكهربائي"},
        {"name": "تعليق TEST", "description": "نظام التعليق"},
        {"name": "تكييف TEST", "description": "نظام التكييف"},
        {"name": "عادم TEST", "description": "نظام العادم"},
    ]
    
    categories = []
    for data in categories_data:
        existing = db.session.query(ProductCategory).filter_by(name=data["name"]).first()
        if not existing:
            cat = ProductCategory(**data)
            db.session.add(cat)
            categories.append(cat)
        else:
            categories.append(existing)
    
    db.session.commit()
    
    # أنواع المركبات
    equipment_types = ["سيدان TEST", "SUV TEST", "شاحنة صغيرة TEST", "باص TEST", "دراجة نارية TEST"]
    eq_types = []
    for eq_name in equipment_types:
        existing = db.session.query(EquipmentType).filter_by(name=eq_name).first()
        if not existing:
            eq = EquipmentType(name=eq_name)
            db.session.add(eq)
            eq_types.append(eq)
        else:
            eq_types.append(existing)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(categories)} فئات و {len(eq_types)} نوع مركبة")
    return categories, eq_types


def seed_products(suppliers, categories):
    """إضافة قطع غيار متنوعة"""
    print("\n🔧 إضافة قطع غيار...")
    
    products_data = [
        # قطع محرك (8 قطع)
        {"name": "فلتر زيت محرك", "sku": "ENG-FL-001", "purchase": 25, "sale": 45, "cat": 0},
        {"name": "سير توقيت", "sku": "ENG-TM-002", "purchase": 120, "sale": 180, "cat": 0},
        {"name": "بواجي (طقم 4)", "sku": "ENG-SP-003", "purchase": 60, "sale": 95, "cat": 0},
        {"name": "طرمبة ماء", "sku": "ENG-WP-004", "purchase": 150, "sale": 240, "cat": 0},
        {"name": "حساس أكسجين", "sku": "ENG-O2-005", "purchase": 180, "sale": 280, "cat": 0},
        {"name": "كويلات (طقم)", "sku": "ENG-CO-006", "purchase": 220, "sale": 350, "cat": 0},
        {"name": "فلتر هواء", "sku": "ENG-AF-007", "purchase": 35, "sale": 60, "cat": 0},
        {"name": "ثرموستات", "sku": "ENG-TH-008", "purchase": 45, "sale": 75, "cat": 0},
        
        # قطع فرامل (6 قطع)
        {"name": "فحمات فرامل أمامية", "sku": "BRK-FP-001", "purchase": 85, "sale": 150, "cat": 1},
        {"name": "فحمات فرامل خلفية", "sku": "BRK-RP-002", "purchase": 75, "sale": 130, "cat": 1},
        {"name": "ديسك فرامل أمامي", "sku": "BRK-FD-003", "purchase": 110, "sale": 180, "cat": 1},
        {"name": "ديسك فرامل خلفي", "sku": "BRK-RD-004", "purchase": 95, "sale": 160, "cat": 1},
        {"name": "سلندر فرامل", "sku": "BRK-MC-005", "purchase": 140, "sale": 220, "cat": 1},
        {"name": "خرطوم فرامل", "sku": "BRK-HO-006", "purchase": 25, "sale": 45, "cat": 1},
        
        # زيوت وفلاتر (7 قطع)
        {"name": "زيت محرك 5W-30 (4 لتر)", "sku": "OIL-EN-001", "purchase": 45, "sale": 75, "cat": 2},
        {"name": "زيت محرك 10W-40 (4 لتر)", "sku": "OIL-EN-002", "purchase": 42, "sale": 70, "cat": 2},
        {"name": "زيت جير أوتوماتيك", "sku": "OIL-TR-003", "purchase": 55, "sale": 90, "cat": 2},
        {"name": "سائل فرامل DOT4", "sku": "OIL-BR-004", "purchase": 18, "sale": 30, "cat": 2},
        {"name": "سائل تبريد", "sku": "OIL-CO-005", "purchase": 22, "sale": 38, "cat": 2},
        {"name": "فلتر بنزين", "sku": "OIL-FF-006", "purchase": 28, "sale": 50, "cat": 2},
        {"name": "فلتر ديزل", "sku": "OIL-DF-007", "purchase": 32, "sale": 55, "cat": 2},
        
        # إطارات (5 قطع)
        {"name": "إطار 205/55 R16", "sku": "TIRE-001", "purchase": 280, "sale": 420, "cat": 3},
        {"name": "إطار 195/65 R15", "sku": "TIRE-002", "purchase": 250, "sale": 380, "cat": 3},
        {"name": "إطار 215/60 R17", "sku": "TIRE-003", "purchase": 320, "sale": 480, "cat": 3},
        {"name": "إطار 185/70 R14", "sku": "TIRE-004", "purchase": 220, "sale": 340, "cat": 3},
        {"name": "إطار 225/45 R18", "sku": "TIRE-005", "purchase": 380, "sale": 560, "cat": 3},
        
        # كهرباء (6 قطع)
        {"name": "بطارية 70 أمبير", "sku": "ELEC-BAT-001", "purchase": 320, "sale": 480, "cat": 4},
        {"name": "بطارية 55 أمبير", "sku": "ELEC-BAT-002", "purchase": 280, "sale": 420, "cat": 4},
        {"name": "دينمو", "sku": "ELEC-ALT-003", "purchase": 450, "sale": 680, "cat": 4},
        {"name": "سلف", "sku": "ELEC-STR-004", "purchase": 380, "sale": 580, "cat": 4},
        {"name": "لمبات LED (طقم)", "sku": "ELEC-LED-005", "purchase": 45, "sale": 75, "cat": 4},
        {"name": "فيوزات (علبة)", "sku": "ELEC-FUS-006", "purchase": 15, "sale": 28, "cat": 4},
        
        # تعليق (4 قطع)
        {"name": "مساعد أمامي", "sku": "SUSP-FS-001", "purchase": 280, "sale": 420, "cat": 5},
        {"name": "مساعد خلفي", "sku": "SUSP-RS-002", "purchase": 260, "sale": 390, "cat": 5},
        {"name": "مقص أمامي", "sku": "SUSP-CA-003", "purchase": 180, "sale": 280, "cat": 5},
        {"name": "جلدة مقص", "sku": "SUSP-BB-004", "purchase": 35, "sale": 60, "cat": 5},
    ]
    
    products = []
    for data in products_data:
        cat_idx = data.pop("cat")
        purchase = data.pop("purchase")
        sale = data.pop("sale")
        
        product = Product(
            **data,
            category_id=categories[cat_idx].id,
            supplier_id=suppliers[random.randint(0, len(suppliers)-1)].id,
            purchase_price=Decimal(str(purchase)),
            selling_price=Decimal(str(sale)),
            price=Decimal(str(sale)),
            barcode=f"BAR{random.randint(100000, 999999)}",
            notes="[TEST] قطعة تجريبية"
        )
        db.session.add(product)
        products.append(product)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(products)} قطعة غيار")
    return products


def seed_warehouses(suppliers, partners):
    """إضافة المستودعات الأربعة المطلوبة"""
    print("\n🏭 إضافة المستودعات الأربعة...")
    
    warehouses = []
    
    existing = db.session.query(Warehouse).filter_by(name="المستودع العام TEST").first()
    if not existing:
        main_wh = Warehouse(
            name="المستودع العام TEST",
            warehouse_type=WarehouseType.MAIN.value,
            location="الطابق الأول",
            capacity=10000,
            notes="[TEST] المستودع العام"
        )
        db.session.add(main_wh)
        warehouses.append(main_wh)
    else:
        warehouses.append(existing)
    
    existing = db.session.query(Warehouse).filter_by(name="مستودع أونلاين TEST").first()
    if not existing:
        online_wh = Warehouse(
            name="مستودع أونلاين TEST",
            warehouse_type=WarehouseType.ONLINE.value,
            location="قسم الأونلاين",
            capacity=5000,
            online_is_default=True,
            notes="[TEST] مستودع أونلاين"
        )
        db.session.add(online_wh)
        warehouses.append(online_wh)
    else:
        warehouses.append(existing)
    
    for idx, supplier in enumerate(suppliers):
        wh_name = f"تبادل {supplier.name}"
        existing = db.session.query(Warehouse).filter_by(name=wh_name).first()
        if not existing:
            wh = Warehouse(
                name=wh_name,
                warehouse_type=WarehouseType.EXCHANGE.value,
                supplier_id=supplier.id,
                location=f"تبادل {idx+1}",
                capacity=2000,
                notes=f"[TEST] تبادل {supplier.name}"
            )
            db.session.add(wh)
            warehouses.append(wh)
        else:
            warehouses.append(existing)
    
    for idx, partner in enumerate(partners):
        wh_name = f"شراكة {partner.name}"
        existing = db.session.query(Warehouse).filter_by(name=wh_name).first()
        if not existing:
            wh = Warehouse(
                name=wh_name,
                warehouse_type=WarehouseType.PARTNER.value,
                partner_id=partner.id,
                share_percent=partner.share_percentage,
                location=f"شراكة {idx+1}",
                capacity=3000,
                notes=f"[TEST] شراكة {partner.name}"
            )
            db.session.add(wh)
            warehouses.append(wh)
        else:
            warehouses.append(existing)
    
    db.session.commit()
    print(f"✅ تم إضافة/تحديث {len(warehouses)} مستودع")
    return warehouses


def seed_exchange_transactions(suppliers, products, warehouses):
    """إضافة معاملات تبادل من الموردين"""
    print("\n📦 إضافة معاملات التبادل...")
    
    exchange_whs = [wh for wh in warehouses if wh.warehouse_type == WarehouseType.EXCHANGE.value]
    
    transactions = []
    base_date = datetime.utcnow()
    
    for wh in exchange_whs:
        supplier = wh.supplier
        print(f"  → مستودع {wh.name}...")
        
        # إضافة 15-25 معاملة لكل مستودع تبادل
        num_txs = random.randint(15, 25)
        
        for i in range(num_txs):
            product = random.choice(products)
            quantity = random.randint(5, 30)
            
            # 70% مسعّرة، 30% غير مسعّرة (للاختبار)
            is_priced = random.random() > 0.3
            unit_cost = product.purchase_price if is_priced else None
            
            # فقط واردة (IN) - لتجنب مشاكل الكمية
            direction = 'IN'
            
            # تواريخ متنوعة خلال آخر 90 يوم
            days_ago = random.randint(1, 90)
            tx_date = base_date - timedelta(days=days_ago)
            
            tx = ExchangeTransaction(
                warehouse_id=wh.id,
                product_id=product.id,
                quantity=quantity,
                unit_cost=unit_cost,
                direction=direction,
                is_priced=is_priced,
                created_at=tx_date,
                notes=f"[TEST] {direction} - {'مسعّر' if is_priced else 'غير مسعّر'}"
            )
            db.session.add(tx)
            transactions.append(tx)
            
            # تحديث المخزون
            if direction == 'IN':
                stock = db.session.query(StockLevel).filter_by(
                    warehouse_id=wh.id, product_id=product.id
                ).first()
                
                if not stock:
                    stock = StockLevel(warehouse_id=wh.id, product_id=product.id, quantity=0)
                    db.session.add(stock)
                
                stock.quantity += quantity
    
    db.session.commit()
    print(f"✅ تم إضافة {len(transactions)} معاملة تبادل")
    return transactions


def seed_partner_stock(partners, products, warehouses):
    """إضافة مخزون للشركاء"""
    print("\n📊 إضافة مخزون الشركاء...")
    
    partner_whs = [wh for wh in warehouses if wh.warehouse_type == WarehouseType.PARTNER.value]
    
    stocks = []
    for wh in partner_whs:
        print(f"  → مستودع {wh.name}...")
        
        # إضافة 15-25 قطعة لكل شريك
        num_products = random.randint(15, 25)
        selected_products = random.sample(products, min(num_products, len(products)))
        
        for product in selected_products:
            quantity = random.randint(10, 80)
            
            stock = StockLevel(
                warehouse_id=wh.id,
                product_id=product.id,
                quantity=quantity
            )
            db.session.add(stock)
            stocks.append(stock)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(stocks)} صنف مخزون للشركاء")
    return stocks


def seed_sales(customers, partners, products, warehouses):
    """إضافة مبيعات متنوعة"""
    print("\n💰 إضافة مبيعات...")
    
    partner_whs = [wh for wh in warehouses if wh.warehouse_type == WarehouseType.PARTNER.value]
    main_whs = [wh for wh in warehouses if wh.warehouse_type == WarehouseType.MAIN.value]
    
    seller = db.session.query(User).filter_by(username='test_admin').first()
    seller_id = seller.id if seller else 1
    
    sales = []
    base_date = datetime.utcnow()
    
    # مبيعات من مستودعات الشركاء (2 عمليات)
    print("  → مبيعات من مستودعات الشركاء...")
    for i in range(2):
        wh = random.choice(partner_whs)
        partner = wh.partner
        customer = random.choice(customers)
        
        days_ago = random.randint(1, 60)
        sale_date = base_date - timedelta(days=days_ago)
        
        # عملات متنوعة
        currency = random.choice(["ILS", "USD", "EUR", "JOD"])
        
        sale = Sale(
            customer_id=customer.id,
            seller_id=seller_id,
            sale_date=sale_date,
            currency=currency,
            status=SaleStatus.CONFIRMED.value,
            notes=f"[TEST] بيع من مستودع {partner.name}"
        )
        db.session.add(sale)
        db.session.flush()
        
        # إضافة 1-5 سطور
        num_lines = random.randint(1, 5)
        for _ in range(num_lines):
            product = random.choice(products)
            quantity = random.randint(1, 5)
            unit_price = product.selling_price or product.price or Decimal('100')
            line_total = Decimal(str(quantity)) * unit_price
            
            line = SaleLine(
                sale_id=sale.id,
                product_id=product.id,
                warehouse_id=wh.id,
                quantity=quantity,
                unit_price=unit_price,
                note="[TEST] سطر بيع من شراكة"
            )
            db.session.add(line)
        
        sales.append(sale)
    
    # مبيعات من المستودع الرئيسي (2 عمليات)
    print("  → مبيعات من المستودع الرئيسي...")
    for i in range(2):
        wh = random.choice(main_whs)
        customer = random.choice(customers)
        
        days_ago = random.randint(1, 60)
        sale_date = base_date - timedelta(days=days_ago)
        
        sale = Sale(
            customer_id=customer.id,
            seller_id=seller_id,
            sale_date=sale_date,
            currency="ILS",
            status=SaleStatus.CONFIRMED.value,
            notes="[TEST] بيع من المستودع الرئيسي"
        )
        db.session.add(sale)
        db.session.flush()
        
        num_lines = random.randint(2, 6)
        for _ in range(num_lines):
            product = random.choice(products)
            quantity = random.randint(1, 4)
            unit_price = product.selling_price or product.price or Decimal('100')
            line_total = Decimal(str(quantity)) * unit_price
            
            line = SaleLine(
                sale_id=sale.id,
                product_id=product.id,
                warehouse_id=wh.id,
                quantity=quantity,
                unit_price=unit_price,
                note="[TEST] سطر بيع عادي"
            )
            db.session.add(line)
        
        sales.append(sale)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(sales)} عملية بيع (30 من شركاء + 20 عادية)")
    return sales


def seed_sales_to_suppliers(suppliers):
    """إضافة مبيعات للموردين (اشتروا منا)"""
    print("\n🛒 إضافة مبيعات للموردين...")
    
    seller = db.session.query(User).filter_by(username='test_admin').first()
    seller_id = seller.id if seller else 1
    
    sales = []
    payments = []
    base_date = datetime.utcnow()
    
    for idx, supplier in enumerate(suppliers[:4]):  # 4 موردين
        # كل مورد له 2-3 عمليات شراء
        num_sales = random.randint(2, 3)
        
        for i in range(num_sales):
            days_ago = random.randint(10, 80)
            sale_date = base_date - timedelta(days=days_ago)
            
            amount = Decimal(str(random.randint(300, 1500)))
            
            # استخدام أول عميل كعميل افتراضي للموردين
            first_customer = db.session.query(Customer).first()
            
            sale = Sale(
                customer_id=first_customer.id,
                seller_id=seller_id,
                sale_date=sale_date,
                currency=supplier.currency,
                status=SaleStatus.DRAFT.value,
                notes=f"[TEST] بيع للمورد {supplier.name}"
            )
            db.session.add(sale)
            db.session.flush()
            sales.append(sale)
            
            # دفعة مرتبطة بالمورد (وليس بالبيع)
            payment = Payment(
                supplier_id=supplier.id,
                direction=PaymentDirection.IN.value,
                method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value]),
                status=PaymentStatus.COMPLETED.value,
                total_amount=amount,
                currency=supplier.currency,
                payment_date=sale_date,
                reference=f"SUP-SALE-PAY-{len(payments)+1}",
                notes=f"[TEST] دفعة من المورد {supplier.name} مقابل بيع {sale.sale_number}"
            )
            db.session.add(payment)
            payments.append(payment)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(sales)} مبيعات للموردين مع {len(payments)} دفعة")
    return sales, payments


def seed_services(customers, suppliers):
    """إضافة طلبات صيانة"""
    print("\n🔧 إضافة طلبات صيانة...")
    
    services = []
    service_payments = []
    
    try:
        base_date = datetime.utcnow()
        
        vehicle_models = ["تويوتا كامري", "هونداي إلنترا", "كيا سيراتو", "مازدا 3", "فولكسفاغن باسات"]
        
        print("  → صيانة للعملاء...")
        for i in range(1):  # صيانة واحدة فقط
            customer = random.choice(customers)
            days_ago = random.randint(1, 90)
            received_date = base_date - timedelta(days=days_ago)
            
            service = ServiceRequest(
                customer_id=customer.id,
                vehicle_vrn=f"{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(10,99)}",
                vehicle_model=random.choice(vehicle_models),
                received_at=received_date,
                description=f"[TEST] صيانة {random.choice(['دورية', 'طارئة', 'شاملة'])} - {random.choice(['فحص شامل', 'تغيير زيت', 'فحص فرامل', 'صيانة محرك'])}",
                problem_description=f"[TEST] مشكلة في {random.choice(['المحرك', 'الفرامل', 'التعليق', 'الكهرباء'])}",
                status=random.choice([ServiceStatus.COMPLETED.value, ServiceStatus.IN_PROGRESS.value]),
                notes="[TEST] طلب صيانة تجريبي"
            )
            db.session.add(service)
            services.append(service)
        
        db.session.commit()
        
        print("  → صيانة للموردين...")
        # استخدام أول عميل كممثل للموردين (ServiceRequest يتطلب customer_id)
        first_customer = customers[0] if customers else None
        if not first_customer:
            print("⚠️ لا يوجد عملاء، تخطي صيانة الموردين")
            return services, service_payments
            
        for idx, supplier in enumerate(suppliers[:1]):  # مورد واحد فقط
            days_ago = random.randint(10, 70)
            service_date = base_date - timedelta(days=days_ago)
            
            amount = Decimal(str(random.randint(250, 800)))
            
            service = ServiceRequest(
                customer_id=first_customer.id,  # ServiceRequest يتطلب customer_id
                vehicle_vrn=f"SUP-{idx+1}",
                vehicle_model="مركبة المورد",
                received_at=service_date,
                description=f"[TEST] صيانة لمركبة المورد {supplier.name}",
                problem_description=f"صيانة دورية لمركبة {supplier.name}",
                status=ServiceStatus.COMPLETED.value,
                notes=f"[TEST] صيانة قدمناها للمورد {supplier.name}"
            )
            db.session.add(service)
            db.session.flush()
            services.append(service)
            
            # دفعة مرتبطة
            payment = Payment(
                supplier_id=supplier.id,
                service_id=service.id,
                direction=PaymentDirection.IN.value,
                method=PaymentMethod.CASH.value,
                status=PaymentStatus.COMPLETED.value,
                total_amount=amount,
                currency=supplier.currency,
                payment_date=service_date,
                reference=f"SRV-SUP-PAY-{idx+1}",
                notes=f"[TEST] دفعة صيانة من المورد {supplier.name}"
            )
            db.session.add(payment)
            service_payments.append(payment)
    
        db.session.commit()
        print(f"✅ تم إضافة {len(services)} طلب صيانة ({len(service_payments)} للموردين)")
    except Exception as e:
        print(f"⚠️ تخطي الصيانة بسبب: {str(e)[:100]}")
        db.session.rollback()
    
    return services, service_payments


def seed_payments(suppliers, partners, customers):
    """إضافة دفعات متنوعة"""
    print("\n💳 إضافة دفعات نقدية مباشرة...")
    
    payments = []
    base_date = datetime.utcnow()
    
    # دفعات للموردين (OUT) - 2 دفعات
    print("  → دفعات للموردين...")
    for i in range(2):
        supplier = random.choice(suppliers)
        days_ago = random.randint(5, 85)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            supplier_id=supplier.id,
            direction=PaymentDirection.OUT.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value, PaymentMethod.CHEQUE.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(500, 3000))),
            currency=supplier.currency,
            payment_date=pay_date,
            reference=f"PAY-SUP-{i+1:04d}",
            notes="[TEST] دفعة نقدية مباشرة للمورد"
        )
        db.session.add(payment)
        payments.append(payment)
    
    # دفعات للشركاء (OUT) - 2 دفعات
    print("  → دفعات للشركاء...")
    for i in range(2):
        partner = random.choice(partners)
        days_ago = random.randint(5, 75)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            partner_id=partner.id,
            direction=PaymentDirection.OUT.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(400, 2500))),
            currency=partner.currency,
            payment_date=pay_date,
            reference=f"PAY-PART-{i+1:04d}",
            notes="[TEST] دفعة نقدية مباشرة للشريك"
        )
        db.session.add(payment)
        payments.append(payment)
    
    # دفعات من الموردين (IN) - 2 دفعات (حالات مديونية المورد لنا)
    print("  → دفعات من الموردين (وارد)...")
    for i in range(2):
        supplier = random.choice(suppliers)
        days_ago = random.randint(5, 70)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            supplier_id=supplier.id,
            direction=PaymentDirection.IN.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(300, 2000))),
            currency=supplier.currency,
            payment_date=pay_date,
            reference=f"PAY-SUP-IN-{i+1:04d}",
            notes="[TEST] دفعة وارد من المورد (مديونية)"
        )
        db.session.add(payment)
        payments.append(payment)
    
    # دفعات من الشركاء (IN) - 2 دفعات (حالات مديونية الشريك لنا)
    print("  → دفعات من الشركاء (وارد)...")
    for i in range(2):
        partner = random.choice(partners)
        days_ago = random.randint(5, 65)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            partner_id=partner.id,
            direction=PaymentDirection.IN.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(250, 1800))),
            currency=partner.currency,
            payment_date=pay_date,
            reference=f"PAY-PART-IN-{i+1:04d}",
            notes="[TEST] دفعة وارد من الشريك (مديونية)"
        )
        db.session.add(payment)
        payments.append(payment)
    
    # دفعات من العملاء (IN) - 2 دفعة
    print("  → دفعات من العملاء...")
    for i in range(2):
        customer = random.choice(customers)
        days_ago = random.randint(1, 60)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            customer_id=customer.id,
            direction=PaymentDirection.IN.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.CARD.value, PaymentMethod.BANK.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(200, 1500))),
            currency="ILS",
            payment_date=pay_date,
            reference=f"PAY-CUST-{i+1:04d}",
            notes="[TEST] دفعة من عميل"
        )
        db.session.add(payment)
        payments.append(payment)
    
    # دفعات للعملاء (OUT) - 2 دفعات (مرتجعات أو رد أموال)
    print("  → دفعات للعملاء (مرتجعات)...")
    for i in range(2):
        customer = random.choice(customers)
        days_ago = random.randint(2, 50)
        pay_date = base_date - timedelta(days=days_ago)
        
        payment = Payment(
            customer_id=customer.id,
            direction=PaymentDirection.OUT.value,
            method=random.choice([PaymentMethod.CASH.value, PaymentMethod.BANK.value]),
            status=PaymentStatus.COMPLETED.value,
            total_amount=Decimal(str(random.randint(100, 800))),
            currency="ILS",
            payment_date=pay_date,
            reference=f"REFUND-CUST-{i+1:04d}",
            notes="[TEST] رد مبلغ للعميل (مرتجع)"
        )
        db.session.add(payment)
        payments.append(payment)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(payments)} دفعة (10 للموردين صادر + 6 من موردين وارد + 8 للشركاء صادر + 5 من شركاء وارد + 15 من عملاء + 4 للعملاء)")
    return payments


def seed_cheque_payments(suppliers, partners):
    """إضافة دفعات بشيكات"""
    print("\n📜 إضافة دفعات بشيكات...")
    
    cheques = []
    base_date = datetime.utcnow()
    
    # شيكات للموردين
    for i in range(5):
        supplier = random.choice(suppliers)
        days_ago = random.randint(10, 60)
        pay_date = base_date - timedelta(days=days_ago)
        due_date = pay_date + timedelta(days=random.randint(30, 90))
        
        cheque = Payment(
            supplier_id=supplier.id,
            direction=PaymentDirection.OUT.value,
            method=PaymentMethod.CHEQUE.value,
            status=random.choice([PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value]),
            total_amount=Decimal(str(random.randint(1000, 5000))),
            currency=supplier.currency,
            payment_date=pay_date,
            reference=f"CHQ-SUP-{i+1:04d}",
            notes=f"[TEST] شيك للمورد - رقم الشيك: {random.randint(100000, 999999)}"
        )
        db.session.add(cheque)
        cheques.append(cheque)
    
    # شيكات للشركاء
    for i in range(3):
        partner = random.choice(partners)
        days_ago = random.randint(10, 50)
        pay_date = base_date - timedelta(days=days_ago)
        
        cheque = Payment(
            partner_id=partner.id,
            direction=PaymentDirection.OUT.value,
            method=PaymentMethod.CHEQUE.value,
            status=random.choice([PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value]),
            total_amount=Decimal(str(random.randint(800, 3000))),
            currency=partner.currency,
            payment_date=pay_date,
            reference=f"CHQ-PART-{i+1:04d}",
            notes=f"[TEST] شيك للشريك - رقم الشيك: {random.randint(100000, 999999)}"
        )
        db.session.add(cheque)
        cheques.append(cheque)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(cheques)} دفعة بشيك")
    return cheques


def seed_expenses(suppliers, partners):
    """إضافة مصروفات متنوعة"""
    print("\n📝 إضافة مصروفات...")
    
    expenses = []
    base_date = datetime.utcnow()
    
    expense_categories = ["رواتب", "إيجار", "كهرباء", "ماء", "صيانة", "وقود", "متنوعة"]
    
    # مصروفات عامة (2 مصروف فقط)
    print("  → مصروفات عامة...")
    for i in range(2):
        days_ago = random.randint(1, 90)
        expense_date = base_date - timedelta(days=days_ago)
        
        expense = Expense(
            description=f"[TEST] {random.choice(expense_categories)} - {random.choice(['شهري', 'طارئ', 'دوري'])}",
            amount=Decimal(str(random.randint(200, 2000))),
            currency="ILS",
            date=expense_date,
            category=random.choice(expense_categories),
            payee_type="OTHER",
            payee_name=f"جهة خارجية {i+1}",
            notes="[TEST] مصروف تجريبي عام"
        )
        db.session.add(expense)
        expenses.append(expense)
    
    # مصروفات على الشركاء (6 مصروفات)
    print("  → مصروفات على الشركاء...")
    for i in range(6):
        partner = random.choice(partners)
        days_ago = random.randint(5, 70)
        expense_date = base_date - timedelta(days=days_ago)
        
        expense = Expense(
            description=f"[TEST] مصروف على الشريك {partner.name}",
            amount=Decimal(str(random.randint(100, 800))),
            currency="ILS",
            date=expense_date,
            category="متنوعة",
            payee_type="PARTNER",
            payee_entity_id=partner.id,
            payee_name=partner.name,
            notes="[TEST] مصروف مخصوم من حصة الشريك"
        )
        db.session.add(expense)
        expenses.append(expense)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(expenses)} مصروف (15 عامة + 6 على شركاء)")
    return expenses


def seed_shipments(suppliers):
    """إضافة شحنات"""
    print("\n🚚 إضافة شحنات...")
    
    shipments = []
    base_date = datetime.utcnow()
    
    for i in range(8):
        supplier = random.choice(suppliers)
        days_ago = random.randint(5, 60)
        ship_date = base_date - timedelta(days=days_ago)
        arrival_date = ship_date + timedelta(days=random.randint(3, 15))
        
        shipment = Shipment(
            shipment_number=f"SHIP-{i+1:05d}",
            supplier_id=supplier.id,
            shipment_date=ship_date,
            expected_arrival=arrival_date,
            actual_arrival=arrival_date if random.random() > 0.3 else None,
            status=random.choice([ShipmentStatus.DELIVERED.value, ShipmentStatus.IN_TRANSIT.value, ShipmentStatus.PENDING.value]),
            total_cost=Decimal(str(random.randint(2000, 10000))),
            currency=supplier.currency,
            tracking_number=f"TRACK{random.randint(100000, 999999)}",
            notes=f"[TEST] شحنة من {supplier.name}"
        )
        db.session.add(shipment)
        shipments.append(shipment)
    
    db.session.commit()
    print(f"✅ تم إضافة {len(shipments)} شحنة")
    return shipments


def display_summary():
    """عرض ملخص شامل للبيانات"""
    print("\n" + "="*80)
    print("📊 ملخص البيانات المضافة:")
    print("="*80)
    
    suppliers = db.session.query(Supplier).all()
    partners = db.session.query(Partner).all()
    customers = db.session.query(Customer).all()
    products = db.session.query(Product).all()
    warehouses = db.session.query(Warehouse).all()
    
    print(f"\n👥 الجهات:")
    print(f"  - موردين: {len(suppliers)}")
    print(f"  - شركاء: {len(partners)}")
    print(f"  - عملاء: {len(customers)}")
    
    print(f"\n📦 المخزون:")
    print(f"  - فئات: {db.session.query(ProductCategory).count()}")
    print(f"  - قطع غيار: {len(products)}")
    print(f"  - مستودعات: {len(warehouses)}")
    
    wh_by_type = {}
    for wh in warehouses:
        wh_type = wh.warehouse_type
        wh_by_type[wh_type] = wh_by_type.get(wh_type, 0) + 1
    
    print(f"\n🏭 تفاصيل المستودعات:")
    for wh_type, count in wh_by_type.items():
        print(f"  - {wh_type}: {count}")
    
    print(f"\n💰 المعاملات المالية:")
    print(f"  - مبيعات: {db.session.query(Sale).count()}")
    print(f"  - دفعات: {db.session.query(Payment).count()}")
    print(f"  - مصروفات: {db.session.query(Expense).count()}")
    print(f"  - شحنات: {db.session.query(Shipment).count()}")
    
    print(f"\n🔧 الصيانة:")
    print(f"  - طلبات صيانة: {db.session.query(ServiceRequest).count()}")
    
    print(f"\n📦 معاملات المستودعات:")
    print(f"  - معاملات تبادل: {db.session.query(ExchangeTransaction).count()}")
    print(f"  - مستويات مخزون: {db.session.query(StockLevel).count()}")
    
    # تفاصيل القطع غير المسعّرة
    unpriced = db.session.query(ExchangeTransaction).filter_by(is_priced=False).count()
    print(f"\n⚠️  قطع غير مسعّرة: {unpriced} (للاختبار)")
    
    # تفاصيل العملات
    print(f"\n💱 العملات المستخدمة:")
    currencies = db.session.query(Currency).filter_by(is_active=True).all()
    for curr in currencies:
        print(f"  - {curr.code}: {curr.name} ({curr.symbol})")
    
    print(f"\n📈 أسعار الصرف:")
    rates = db.session.query(ExchangeRate).all()
    for rate in rates:
        print(f"  - {rate.base_code}/{rate.quote_code}: {float(rate.rate):.4f}")
    
    print("\n" + "="*80)
    print("✅ البذور جاهزة للاختبار!")
    print("="*80)
    
    print("\n🎯 خطوات الاختبار:")
    print("1. شغّل السيرفر: python app.py")
    print("2. افتح المتصفح: http://localhost:5000")
    print("3. سجّل دخول: test_admin / test123")
    print("4. اذهب إلى قائمة الموردين واضغط 'تسوية ذكية'")
    print("5. اذهب إلى قائمة الشركاء واضغط 'تسوية ذكية'")
    print("\n" + "="*80)


def run_all_seeds():
    """تشغيل جميع البذور"""
    print("\n" + "="*80)
    print("بدء إضافة البذور الشاملة الكاملة للنظام")
    print("Starting Complete Comprehensive System Seeds")
    print("="*80 + "\n")
    
    with app.app_context():
        try:
            # 1. المستخدمين
            users = seed_users()
            
            # 2. العملات وأسعار الصرف
            seed_currencies()
            
            # 3. الموردين والشركاء
            suppliers = seed_suppliers()
            partners = seed_partners()
            
            # 4. العملاء
            customers = seed_customers()
            
            # 5. الفئات والقطع
            categories, equipment_types = seed_categories_and_equipment()
            products = seed_products(suppliers, categories)
            
            # 6. المستودعات الأربعة + مستودعات الموردين والشركاء
            warehouses = seed_warehouses(suppliers, partners)
            
            # 7. معاملات التبادل (قطع من الموردين)
            exchange_txs = seed_exchange_transactions(suppliers, products, warehouses)
            
            # 8. مخزون الشركاء
            partner_stocks = seed_partner_stock(partners, products, warehouses)
            
            # 9. المبيعات (من شركاء ومن المستودع الرئيسي)
            sales = seed_sales(customers, partners, products, warehouses)
            
            # 10. مبيعات للموردين (اشتروا منا)
            sup_sales, sup_sale_pays = seed_sales_to_suppliers(suppliers)
            
            # 11. الصيانة (للعملاء وللموردين)
            services, srv_pays = seed_services(customers, suppliers)
            
            # 12. دفعات نقدية متنوعة
            payments = seed_payments(suppliers, partners, customers)
            
            # 13. دفعات بشيكات
            cheques = seed_cheque_payments(suppliers, partners)
            
            # 14. مصروفات
            expenses = seed_expenses(suppliers, partners)
            
            # 15. شحنات
            shipments = seed_shipments(suppliers)
            
            # عرض الملخص
            display_summary()
            
            print("\n✅ اكتملت جميع البذور بنجاح! 🎉")
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ أثناء إضافة البذور: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False


if __name__ == "__main__":
    print("\n" + "🚀"*40)
    print("نظام إدارة الكراج - البذور الشاملة")
    print("Garage Manager - Complete Seeds")
    print("🚀"*40 + "\n")
    
    # تهيئة قاعدة البيانات
    init_db()
    
    # تشغيل جميع البذور
    success = run_all_seeds()
    
    if success:
        print("\n✅ العملية اكتملت بنجاح!")
        sys.exit(0)
    else:
        print("\n❌ فشلت العملية!")
        sys.exit(1)

