#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بذور شاملة لنظام إدارة المرآب
تشمل: عملاء، موردين، شركاء، منتجات، مستودعات، شحنات، دفعات، نفقات، صيانة
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from random import randint, choice, random
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app import create_app
from extensions import db
import models as M

app = create_app()

def q(x) -> Decimal:
    """تحويل إلى Decimal مع دقة عشريتين"""
    try:
        return Decimal(str(x or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")

def get_or_create(model, **kwargs):
    """إنشاء أو جلب سجل موجود"""
    try:
        instance = model.query.filter_by(**kwargs).first()
        if instance:
            return instance
        instance = model(**kwargs)
        db.session.add(instance)
        db.session.flush()
        return instance
    except IntegrityError:
        db.session.rollback()
        return model.query.filter_by(**kwargs).first()

def seed_comprehensive_data():
    """زرع بذور شاملة للنظام"""
    
    with app.app_context():
        print("🌱 بدء زرع البذور الشاملة...")
        
        # 1. إنشاء الأدوار والصلاحيات
        print("📋 إنشاء الأدوار والصلاحيات...")
        
        # الأدوار
        roles_data = [
            {"name": "مدير عام", "description": "مدير عام للنظام"},
            {"name": "مدير مبيعات", "description": "مدير قسم المبيعات"},
            {"name": "مدير صيانة", "description": "مدير قسم الصيانة"},
            {"name": "مدير مستودع", "description": "مدير المستودعات"},
            {"name": "محاسب", "description": "محاسب النظام"},
            {"name": "موظف مبيعات", "description": "موظف مبيعات"},
            {"name": "فني صيانة", "description": "فني صيانة"},
            {"name": "موظف مستودع", "description": "موظف مستودع"},
        ]
        
        for role_data in roles_data:
            get_or_create(M.Role, **role_data)
        
        # الصلاحيات
        permissions_data = [
            {"name": "view_dashboard", "description": "عرض لوحة التحكم"},
            {"name": "manage_users", "description": "إدارة المستخدمين"},
            {"name": "manage_customers", "description": "إدارة العملاء"},
            {"name": "manage_suppliers", "description": "إدارة الموردين"},
            {"name": "manage_partners", "description": "إدارة الشركاء"},
            {"name": "manage_products", "description": "إدارة المنتجات"},
            {"name": "manage_warehouses", "description": "إدارة المستودعات"},
            {"name": "manage_sales", "description": "إدارة المبيعات"},
            {"name": "manage_payments", "description": "إدارة المدفوعات"},
            {"name": "manage_service", "description": "إدارة الصيانة"},
            {"name": "manage_shipments", "description": "إدارة الشحنات"},
            {"name": "manage_expenses", "description": "إدارة النفقات"},
            {"name": "view_reports", "description": "عرض التقارير"},
            {"name": "manage_currencies", "description": "إدارة العملات"},
        ]
        
        for perm_data in permissions_data:
            get_or_create(M.Permission, **perm_data)
        
        # 2. إنشاء المستخدمين
        print("👥 إنشاء المستخدمين...")
        
        users_data = [
            {
                "username": "admin",
                "email": "admin@garage.ps",
                "password": "admin123",
                "role_name": "مدير عام",
                "is_active": True
            },
            {
                "username": "sales_manager",
                "email": "sales@garage.ps", 
                "password": "sales123",
                "role_name": "مدير مبيعات",
                "is_active": True
            },
            {
                "username": "service_manager",
                "email": "service@garage.ps",
                "password": "service123", 
                "role_name": "مدير صيانة",
                "is_active": True
            },
            {
                "username": "warehouse_manager",
                "email": "warehouse@garage.ps",
                "password": "warehouse123",
                "role_name": "مدير مستودع", 
                "is_active": True
            },
            {
                "username": "accountant",
                "email": "accountant@garage.ps",
                "password": "accountant123",
                "role_name": "محاسب",
                "is_active": True
            }
        ]
        
        for user_data in users_data:
            role = M.Role.query.filter_by(name=user_data["role_name"]).first()
            if role:
                user = get_or_create(M.User, username=user_data["username"])
                user.email = user_data["email"]
                user.set_password(user_data["password"])
                user.role_id = role.id
                user.is_active = user_data["is_active"]
        
        # 3. إنشاء العملاء
        print("👤 إنشاء العملاء...")
        
        customers_data = [
            {
                "name": "أحمد محمد أبو بكر",
                "phone": "0599123456",
                "whatsapp": "0599123456", 
                "email": "ahmed@example.com",
                "address": "رام الله - حي الطيرة",
                "category": "VIP",
                "credit_limit": q(5000),
                "discount_rate": q(10),
                "currency": "ILS"
            },
            {
                "name": "فاطمة علي حسن",
                "phone": "0598765432",
                "whatsapp": "0598765432",
                "email": "fatima@example.com", 
                "address": "البيرة - شارع القدس",
                "category": "عادي",
                "credit_limit": q(2000),
                "discount_rate": q(5),
                "currency": "ILS"
            },
            {
                "name": "محمد سعد الدين",
                "phone": "0598111222",
                "whatsapp": "0598111222",
                "email": "mohammed@example.com",
                "address": "نابلس - حي الشهداء", 
                "category": "مميز",
                "credit_limit": q(3000),
                "discount_rate": q(7),
                "currency": "ILS"
            },
            {
                "name": "سارة أحمد خليل",
                "phone": "0598333444",
                "whatsapp": "0598333444",
                "email": "sara@example.com",
                "address": "جنين - حي النصر",
                "category": "عادي", 
                "credit_limit": q(1500),
                "discount_rate": q(3),
                "currency": "ILS"
            },
            {
                "name": "خالد محمود عثمان",
                "phone": "0598555666",
                "whatsapp": "0598555666",
                "email": "khalid@example.com",
                "address": "طولكرم - شارع الجامعة",
                "category": "VIP",
                "credit_limit": q(8000),
                "discount_rate": q(15),
                "currency": "USD"
            }
        ]
        
        for customer_data in customers_data:
            get_or_create(M.Customer, **customer_data)
        
        # 4. إنشاء الموردين
        print("🏭 إنشاء الموردين...")
        
        suppliers_data = [
            {
                "name": "شركة قطع غيار الشرق الأوسط",
                "phone": "022345678",
                "whatsapp": "0599000111",
                "email": "info@eastparts.ps",
                "address": "رام الله - المنطقة الصناعية",
                "contact_person": "محمود أبو ريان",
                "credit_limit": q(10000),
                "payment_terms": "30 يوم",
                "currency": "ILS"
            },
            {
                "name": "مؤسسة الإلكترونيات الحديثة",
                "phone": "022345679", 
                "whatsapp": "0599000222",
                "email": "sales@modernelectronics.ps",
                "address": "نابلس - شارع الجامعة",
                "contact_person": "سامي النتشة",
                "credit_limit": q(15000),
                "payment_terms": "45 يوم",
                "currency": "USD"
            },
            {
                "name": "شركة الإطارات والبطاريات",
                "phone": "022345680",
                "whatsapp": "0599000333", 
                "email": "tires@batteries.ps",
                "address": "الخليل - المنطقة الصناعية",
                "contact_person": "عبد الرحمن الشريف",
                "credit_limit": q(20000),
                "payment_terms": "60 يوم",
                "currency": "ILS"
            }
        ]
        
        for supplier_data in suppliers_data:
            get_or_create(M.Supplier, **supplier_data)
        
        # 5. إنشاء الشركاء
        print("🤝 إنشاء الشركاء...")
        
        partners_data = [
            {
                "name": "شركة النقل السريع",
                "phone": "022345681",
                "whatsapp": "0599000444",
                "email": "shipping@fasttransport.ps", 
                "address": "رام الله - شارع المطار",
                "contact_person": "أحمد الشامي",
                "commission_rate": q(5),
                "currency": "ILS"
            },
            {
                "name": "مؤسسة الخدمات التقنية",
                "phone": "022345682",
                "whatsapp": "0599000555",
                "email": "tech@services.ps",
                "address": "البيرة - حي الصناعة",
                "contact_person": "محمد التميمي", 
                "commission_rate": q(7),
                "currency": "ILS"
            }
        ]
        
        for partner_data in partners_data:
            get_or_create(M.Partner, **partner_data)
        
        # 6. إنشاء المستودعات
        print("🏪 إنشاء المستودعات...")
        
        warehouses_data = [
            {
                "name": "المستودع الرئيسي",
                "location": "رام الله - المنطقة الصناعية",
                "warehouse_type": "MAIN",
                "capacity": 1000,
                "manager_name": "أحمد المستودع"
            },
            {
                "name": "مستودع قطع الغيار",
                "location": "نابلس - شارع الجامعة", 
                "warehouse_type": "PARTS",
                "capacity": 500,
                "manager_name": "محمد القطع"
            },
            {
                "name": "مستودع الإطارات",
                "location": "الخليل - المنطقة الصناعية",
                "warehouse_type": "TIRES", 
                "capacity": 300,
                "manager_name": "سامي الإطارات"
            }
        ]
        
        for warehouse_data in warehouses_data:
            get_or_create(M.Warehouse, **warehouse_data)
        
        # 7. إنشاء المنتجات
        print("📦 إنشاء المنتجات...")
        
        products_data = [
            {
                "name": "إطار ميشلان 205/55R16",
                "sku": "MIC-205-55-16",
                "barcode": "1234567890123",
                "category": "إطارات",
                "brand": "ميشلان",
                "unit": "قطعة",
                "cost_price": q(450),
                "selling_price": q(600),
                "currency": "ILS",
                "min_stock": 10,
                "max_stock": 100
            },
            {
                "name": "بطارية أوبتيما 12V 55Ah",
                "sku": "OPT-12V-55AH", 
                "barcode": "1234567890124",
                "category": "بطاريات",
                "brand": "أوبتيما",
                "unit": "قطعة",
                "cost_price": q(800),
                "selling_price": q(1200),
                "currency": "ILS",
                "min_stock": 5,
                "max_stock": 50
            },
            {
                "name": "فلتر زيت مان 712/75",
                "sku": "MAN-712-75",
                "barcode": "1234567890125", 
                "category": "فلاتر",
                "brand": "مان",
                "unit": "قطعة",
                "cost_price": q(120),
                "selling_price": q(180),
                "currency": "ILS",
                "min_stock": 20,
                "max_stock": 200
            },
            {
                "name": "شمعات إشعال NGK BKR6E",
                "sku": "NGK-BKR6E",
                "barcode": "1234567890126",
                "category": "شمعات إشعال", 
                "brand": "NGK",
                "unit": "قطعة",
                "cost_price": q(25),
                "selling_price": q(40),
                "currency": "ILS",
                "min_stock": 50,
                "max_stock": 500
            },
            {
                "name": "زيت محرك 5W-30 4L",
                "sku": "OIL-5W30-4L",
                "barcode": "1234567890127",
                "category": "زيوت",
                "brand": "كاسترول",
                "unit": "زجاجة",
                "cost_price": q(150),
                "selling_price": q(220),
                "currency": "ILS", 
                "min_stock": 30,
                "max_stock": 300
            }
        ]
        
        for product_data in products_data:
            get_or_create(M.Product, **product_data)
        
        # 8. إنشاء الشحنات
        print("🚚 إنشاء الشحنات...")
        
        shipments_data = [
            {
                "tracking_number": "SH001",
                "supplier_name": "شركة قطع غيار الشرق الأوسط",
                "partner_name": "شركة النقل السريع",
                "status": "PENDING",
                "priority": "NORMAL",
                "delivery_method": "STANDARD",
                "total_cost": q(5000),
                "weight": q(100),
                "package_count": 5,
                "notes": "شحنة قطع غيار متنوعة"
            },
            {
                "tracking_number": "SH002", 
                "supplier_name": "مؤسسة الإلكترونيات الحديثة",
                "partner_name": "مؤسسة الخدمات التقنية",
                "status": "IN_TRANSIT",
                "priority": "HIGH",
                "delivery_method": "EXPRESS",
                "total_cost": q(8000),
                "weight": q(150),
                "package_count": 8,
                "notes": "شحنة إلكترونيات وأجهزة"
            }
        ]
        
        for shipment_data in shipments_data:
            get_or_create(M.Shipment, **shipment_data)
        
        # 9. إنشاء النفقات
        print("💰 إنشاء النفقات...")
        
        expense_types_data = [
            {"name": "إيجار", "description": "إيجار المحل والمستودعات"},
            {"name": "رواتب", "description": "رواتب الموظفين"},
            {"name": "كهرباء", "description": "فاتورة الكهرباء"},
            {"name": "ماء", "description": "فاتورة الماء"},
            {"name": "إنترنت", "description": "فاتورة الإنترنت"},
            {"name": "صيانة", "description": "صيانة المعدات والأجهزة"},
            {"name": "نقل", "description": "تكاليف النقل والشحن"},
            {"name": "تسويق", "description": "تكاليف التسويق والإعلان"}
        ]
        
        for expense_type_data in expense_types_data:
            get_or_create(M.ExpenseType, **expense_type_data)
        
        # إنشاء نفقات عينة
        expenses_data = [
            {
                "expense_type_name": "إيجار",
                "amount": q(3000),
                "currency": "ILS",
                "description": "إيجار المحل الرئيسي - شهر أكتوبر",
                "date": datetime.now() - timedelta(days=5)
            },
            {
                "expense_type_name": "رواتب", 
                "amount": q(15000),
                "currency": "ILS",
                "description": "رواتب الموظفين - شهر أكتوبر",
                "date": datetime.now() - timedelta(days=3)
            },
            {
                "expense_type_name": "كهرباء",
                "amount": q(800),
                "currency": "ILS", 
                "description": "فاتورة الكهرباء - أكتوبر",
                "date": datetime.now() - timedelta(days=2)
            }
        ]
        
        for expense_data in expenses_data:
            expense_type = M.ExpenseType.query.filter_by(name=expense_data["expense_type_name"]).first()
            if expense_type:
                expense_data["expense_type_id"] = expense_type.id
                del expense_data["expense_type_name"]
                get_or_create(M.Expense, **expense_data)
        
        # 10. إنشاء المبيعات
        print("🛒 إنشاء المبيعات...")
        
        sales_data = [
            {
                "customer_name": "أحمد محمد أبو بكر",
                "status": "COMPLETED",
                "total_amount": q(1200),
                "currency": "ILS",
                "discount_amount": q(120),
                "notes": "بيع إطار وبطارية"
            },
            {
                "customer_name": "فاطمة علي حسن",
                "status": "COMPLETED", 
                "total_amount": q(800),
                "currency": "ILS",
                "discount_amount": q(40),
                "notes": "بيع زيت وفلاتر"
            }
        ]
        
        for sale_data in sales_data:
            customer = M.Customer.query.filter_by(name=sale_data["customer_name"]).first()
            if customer:
                sale_data["customer_id"] = customer.id
                del sale_data["customer_name"]
                get_or_create(M.Sale, **sale_data)
        
        # 11. إنشاء المدفوعات
        print("💳 إنشاء المدفوعات...")
        
        payments_data = [
            {
                "entity_type": "CUSTOMER",
                "entity_name": "أحمد محمد أبو بكر",
                "amount": q(1000),
                "currency": "ILS",
                "method": "CASH",
                "direction": "IN",
                "status": "COMPLETED",
                "notes": "دفعة نقدية من العميل"
            },
            {
                "entity_type": "SUPPLIER",
                "entity_name": "شركة قطع غيار الشرق الأوسط", 
                "amount": q(3000),
                "currency": "ILS",
                "method": "BANK_TRANSFER",
                "direction": "OUT",
                "status": "COMPLETED",
                "notes": "دفعة للمورد"
            }
        ]
        
        for payment_data in payments_data:
            get_or_create(M.Payment, **payment_data)
        
        # 12. إنشاء طلبات الصيانة
        print("🔧 إنشاء طلبات الصيانة...")
        
        service_requests_data = [
            {
                "customer_name": "أحمد محمد أبو بكر",
                "vehicle_info": "تويوتا كورولا 2020",
                "description": "تغيير زيت وتصفية",
                "status": "COMPLETED",
                "priority": "NORMAL",
                "estimated_cost": q(300),
                "currency": "ILS"
            },
            {
                "customer_name": "فاطمة علي حسن",
                "vehicle_info": "هيونداي إلنترا 2019", 
                "description": "إصلاح مكابح",
                "status": "IN_PROGRESS",
                "priority": "HIGH",
                "estimated_cost": q(500),
                "currency": "ILS"
            }
        ]
        
        for service_data in service_requests_data:
            customer = M.Customer.query.filter_by(name=service_data["customer_name"]).first()
            if customer:
                service_data["customer_id"] = customer.id
                del service_data["customer_name"]
                get_or_create(M.ServiceRequest, **service_data)
        
        # حفظ التغييرات
        try:
            db.session.commit()
            print("✅ تم حفظ جميع البيانات بنجاح!")
        except Exception as e:
            db.session.rollback()
            print(f"❌ خطأ في حفظ البيانات: {e}")
        
        print("\n🎉 تم الانتهاء من زرع البذور الشاملة!")
        print("📊 ملخص البيانات المضافة:")
        print(f"- المستخدمين: {M.User.query.count()}")
        print(f"- العملاء: {M.Customer.query.count()}")
        print(f"- الموردين: {M.Supplier.query.count()}")
        print(f"- الشركاء: {M.Partner.query.count()}")
        print(f"- المنتجات: {M.Product.query.count()}")
        print(f"- المستودعات: {M.Warehouse.query.count()}")
        print(f"- الشحنات: {M.Shipment.query.count()}")
        print(f"- النفقات: {M.Expense.query.count()}")
        print(f"- المبيعات: {M.Sale.query.count()}")
        print(f"- المدفوعات: {M.Payment.query.count()}")
        print(f"- طلبات الصيانة: {M.ServiceRequest.query.count()}")
        
        # إضافة شيكات تجريبية
        print("\n🏦 إنشاء شيكات تجريبية...")
        
        # التأكد من وجود عملاء وموردين
        customers_list = M.Customer.query.filter_by(deleted=False).limit(5).all()
        suppliers_list = M.Supplier.query.filter_by(deleted=False).limit(5).all()
        
        # الشيكات اليدوية
        checks_data = [
            {
                'check_number': '100001',
                'check_bank': 'بنك فلسطين',
                'check_date': datetime.utcnow() - timedelta(days=10),
                'check_due_date': datetime.utcnow() + timedelta(days=30),
                'amount': q('5000.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.IN.value,
                'status': M.CheckStatus.PENDING.value,
                'drawer_name': 'محمد أحمد عبد الله',
                'drawer_phone': '0599123456',
                'drawer_id_number': '123456789',
                'payee_name': 'شركة أزاد للأنظمة الذكية',
                'payee_phone': '0562150193',
                'notes': 'شيك دفعة أولى لصيانة السيارة',
                'reference_number': 'REF-001',
                'customer_id': customers_list[0].id if customers_list else None,
                'created_by_id': 1
            },
            {
                'check_number': '100002',
                'check_bank': 'بنك القدس',
                'check_date': datetime.utcnow() - timedelta(days=60),
                'check_due_date': datetime.utcnow() - timedelta(days=10),
                'amount': q('3500.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.OUT.value,
                'status': M.CheckStatus.PENDING.value,
                'drawer_name': 'شركة أزاد',
                'payee_name': 'شركة الأمل لقطع الغيار',
                'payee_phone': '0599654321',
                'payee_account': 'ACC-2024-001',
                'notes': 'دفعة لمورد قطع غيار',
                'internal_notes': 'يجب المتابعة - الشيك متأخر',
                'reference_number': 'REF-002',
                'supplier_id': suppliers_list[0].id if suppliers_list else None,
                'created_by_id': 1
            },
            {
                'check_number': '100003',
                'check_bank': 'بنك الوطني',
                'check_date': datetime.utcnow() - timedelta(days=90),
                'check_due_date': datetime.utcnow() - timedelta(days=60),
                'amount': q('8500.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.IN.value,
                'status': M.CheckStatus.CASHED.value,
                'drawer_name': 'علي حسن محمود',
                'drawer_phone': '0599777888',
                'payee_name': 'شركة أزاد',
                'notes': 'شيك دفعة كاملة - تم الصرف',
                'status_history': '[{"timestamp": "' + datetime.utcnow().isoformat() + '", "old_status": "PENDING", "new_status": "CASHED", "reason": "تم صرف الشيك بنجاح", "user": "admin"}]',
                'customer_id': customers_list[1].id if len(customers_list) > 1 else None,
                'created_by_id': 1
            },
            {
                'check_number': '100004',
                'check_bank': 'بنك الاستثمار الفلسطيني',
                'check_date': datetime.utcnow() - timedelta(days=30),
                'check_due_date': datetime.utcnow() + timedelta(days=5),
                'amount': q('2500.00'),
                'currency': 'USD',
                'direction': M.PaymentDirection.IN.value,
                'status': M.CheckStatus.PENDING.value,
                'drawer_name': 'خالد فارس',
                'drawer_phone': '0599111222',
                'drawer_id_number': '987654321',
                'payee_name': 'شركة أزاد',
                'notes': 'شيك يستحق قريباً (خلال 5 أيام)',
                'reference_number': 'REF-004',
                'customer_id': customers_list[2].id if len(customers_list) > 2 else None,
                'created_by_id': 1
            },
            {
                'check_number': '100005',
                'check_bank': 'بنك القاهرة عمان',
                'check_date': datetime.utcnow() - timedelta(days=45),
                'check_due_date': datetime.utcnow() - timedelta(days=30),
                'amount': q('4200.00'),
                'currency': 'JOD',
                'direction': M.PaymentDirection.OUT.value,
                'status': M.CheckStatus.RETURNED.value,
                'drawer_name': 'شركة أزاد',
                'payee_name': 'مؤسسة النور التجارية',
                'payee_phone': '0599888999',
                'notes': 'شيك مرتجع - سيتم إعادة تقديمه',
                'internal_notes': 'تم التواصل مع الجهة - سيتم التسوية قريباً',
                'status_history': '[{"timestamp": "' + (datetime.utcnow() - timedelta(days=5)).isoformat() + '", "old_status": "PENDING", "new_status": "RETURNED", "reason": "رصيد غير كافي", "user": "admin"}]',
                'supplier_id': suppliers_list[1].id if len(suppliers_list) > 1 else None,
                'created_by_id': 1
            },
            {
                'check_number': '100006',
                'check_bank': 'بنك الأردن',
                'check_date': datetime.utcnow(),
                'check_due_date': datetime.utcnow() + timedelta(days=60),
                'amount': q('15000.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.IN.value,
                'status': M.CheckStatus.PENDING.value,
                'drawer_name': 'شركة الفجر للتجارة',
                'drawer_phone': '0599333444',
                'drawer_id_number': '456789123',
                'drawer_address': 'رام الله - شارع الماصيون',
                'payee_name': 'شركة أزاد',
                'notes': 'شيك دفعة كبيرة - يستحق بعد شهرين',
                'reference_number': 'REF-006',
                'customer_id': customers_list[3].id if len(customers_list) > 3 else None,
                'created_by_id': 1
            },
            {
                'check_number': '100007',
                'check_bank': 'بنك فلسطين - فرع البيرة',
                'check_date': datetime.utcnow() - timedelta(days=20),
                'check_due_date': datetime.utcnow() + timedelta(days=15),
                'amount': q('1800.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.OUT.value,
                'status': M.CheckStatus.PENDING.value,
                'drawer_name': 'شركة أزاد',
                'payee_name': 'مكتب المحاماة القانوني',
                'payee_phone': '0599555666',
                'payee_account': 'ACC-2024-100',
                'notes': 'رسوم قانونية - يستحق خلال 15 يوم',
                'internal_notes': 'خدمات استشارية قانونية',
                'created_by_id': 1
            },
            {
                'check_number': '100008',
                'check_bank': 'بنك القدس - فرع رام الله',
                'check_date': datetime.utcnow() - timedelta(days=100),
                'check_due_date': datetime.utcnow() - timedelta(days=50),
                'amount': q('6700.00'),
                'currency': 'ILS',
                'direction': M.PaymentDirection.IN.value,
                'status': M.CheckStatus.BOUNCED.value,
                'drawer_name': 'ياسر محمد علي',
                'drawer_phone': '0599222333',
                'drawer_id_number': '789456123',
                'payee_name': 'شركة أزاد',
                'notes': 'شيك مرفوض - حساب مغلق',
                'internal_notes': 'تم التواصل مع العميل - لم يستجب',
                'status_history': '[{"timestamp": "' + (datetime.utcnow() - timedelta(days=50)).isoformat() + '", "old_status": "PENDING", "new_status": "BOUNCED", "reason": "حساب مغلق", "user": "admin"}]',
                'customer_id': customers_list[4].id if len(customers_list) > 4 else None,
                'created_by_id': 1
            }
        ]
        
        for check_data in checks_data:
            try:
                existing = M.Check.query.filter_by(check_number=check_data['check_number']).first()
                if not existing:
                    check = M.Check(**check_data)
                    db.session.add(check)
                    print(f"  ✅ تم إضافة الشيك: {check_data['check_number']} - {check_data['check_bank']}")
            except Exception as e:
                print(f"  ⚠️ خطأ في إضافة الشيك {check_data['check_number']}: {str(e)}")
        
        db.session.commit()
        print(f"✅ تم إضافة {M.Check.query.count()} شيكاً يدوياً")
        print(f"- الشيكات: {M.Check.query.count()}")

if __name__ == "__main__":
    seed_comprehensive_data()
