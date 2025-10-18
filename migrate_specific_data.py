#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
📦 استخراج بيانات محددة من الباك أب
نقل: القطع، المستودعات، الزبائن، الصيانة فقط
"""

import sqlite3
import os
from datetime import datetime


class DataMigrator:
    """مُهاجر البيانات"""
    
    def __init__(self, backup_file, target_db='instance/app.db'):
        self.backup_file = backup_file
        self.target_db = target_db
        self.stats = {
            'customers': 0,
            'products': 0,
            'warehouses': 0,
            'service_requests': 0,
            'stock_levels': 0,
            'errors': []
        }
    
    def connect_backup(self):
        """الاتصال بالباك أب"""
        if not os.path.exists(self.backup_file):
            print(f"❌ ملف الباك أب غير موجود: {self.backup_file}")
            return None
        
        return sqlite3.connect(self.backup_file)
    
    def connect_target(self):
        """الاتصال بقاعدة البيانات الحالية"""
        return sqlite3.connect(self.target_db)
    
    def migrate_customers(self, backup_conn, target_conn):
        """نقل الزبائن"""
        print("\n" + "="*60)
        print("👥 نقل الزبائن (Customers)...")
        print("="*60)
        
        try:
            # قراءة من الباك أب
            cursor = backup_conn.cursor()
            cursor.execute("""
                SELECT name, phone, email, address, city, notes, 
                       is_active, category, credit_limit, created_at
                FROM customer
            """)
            
            customers = cursor.fetchall()
            
            if not customers:
                print("⚠️  لا يوجد زبائن في الباك أب")
                return
            
            # الإدراج في القاعدة الحالية
            target_cursor = target_conn.cursor()
            
            for customer in customers:
                try:
                    # فحص إذا كان موجوداً (حسب الاسم)
                    target_cursor.execute(
                        "SELECT id FROM customer WHERE name = ?",
                        (customer[0],)
                    )
                    
                    if target_cursor.fetchone():
                        print(f"  ⏭️  {customer[0]} - موجود مسبقاً (تخطي)")
                        continue
                    
                    # إدراج زبون جديد
                    target_cursor.execute("""
                        INSERT INTO customer 
                        (name, phone, email, address, city, notes, 
                         is_active, category, credit_limit, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, customer)
                    
                    self.stats['customers'] += 1
                    print(f"  ✅ {customer[0]}")
                    
                except Exception as e:
                    print(f"  ❌ خطأ في {customer[0]}: {str(e)}")
                    self.stats['errors'].append(f"Customer {customer[0]}: {str(e)}")
            
            target_conn.commit()
            print(f"\n✅ تم نقل {self.stats['customers']} زبون")
            
        except Exception as e:
            print(f"❌ خطأ عام في نقل الزبائن: {str(e)}")
            self.stats['errors'].append(f"Customers: {str(e)}")
    
    def migrate_products(self, backup_conn, target_conn):
        """نقل القطع"""
        print("\n" + "="*60)
        print("🔩 نقل القطع (Products)...")
        print("="*60)
        
        try:
            cursor = backup_conn.cursor()
            cursor.execute("""
                SELECT name, sku, barcode, description, price, cost,
                       min_stock_level, category, unit, is_active, created_at
                FROM product
            """)
            
            products = cursor.fetchall()
            
            if not products:
                print("⚠️  لا يوجد قطع في الباك أب")
                return
            
            target_cursor = target_conn.cursor()
            
            for product in products:
                try:
                    # فحص إذا كان موجوداً (حسب الاسم أو SKU)
                    target_cursor.execute(
                        "SELECT id FROM product WHERE name = ? OR sku = ?",
                        (product[0], product[1])
                    )
                    
                    if target_cursor.fetchone():
                        print(f"  ⏭️  {product[0]} - موجود مسبقاً (تخطي)")
                        continue
                    
                    # إدراج منتج جديد
                    target_cursor.execute("""
                        INSERT INTO product 
                        (name, sku, barcode, description, price, cost,
                         min_stock_level, category, unit, is_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, product)
                    
                    self.stats['products'] += 1
                    print(f"  ✅ {product[0]}")
                    
                except Exception as e:
                    print(f"  ❌ خطأ في {product[0]}: {str(e)[:50]}")
                    self.stats['errors'].append(f"Product {product[0]}: {str(e)[:50]}")
            
            target_conn.commit()
            print(f"\n✅ تم نقل {self.stats['products']} منتج")
            
        except Exception as e:
            print(f"❌ خطأ عام في نقل القطع: {str(e)}")
            self.stats['errors'].append(f"Products: {str(e)}")
    
    def migrate_warehouses(self, backup_conn, target_conn):
        """نقل المستودعات"""
        print("\n" + "="*60)
        print("🏢 نقل المستودعات (Warehouses)...")
        print("="*60)
        
        try:
            cursor = backup_conn.cursor()
            cursor.execute("""
                SELECT name, warehouse_type, location, description, 
                       is_active, created_at
                FROM warehouse
            """)
            
            warehouses = cursor.fetchall()
            
            if not warehouses:
                print("⚠️  لا يوجد مستودعات في الباك أب")
                return
            
            target_cursor = target_conn.cursor()
            
            for warehouse in warehouses:
                try:
                    # فحص إذا كان موجوداً
                    target_cursor.execute(
                        "SELECT id FROM warehouse WHERE name = ?",
                        (warehouse[0],)
                    )
                    
                    if target_cursor.fetchone():
                        print(f"  ⏭️  {warehouse[0]} - موجود مسبقاً (تخطي)")
                        continue
                    
                    # إدراج مستودع جديد
                    target_cursor.execute("""
                        INSERT INTO warehouse 
                        (name, warehouse_type, location, description, 
                         is_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, warehouse)
                    
                    self.stats['warehouses'] += 1
                    print(f"  ✅ {warehouse[0]}")
                    
                except Exception as e:
                    print(f"  ❌ خطأ في {warehouse[0]}: {str(e)[:50]}")
                    self.stats['errors'].append(f"Warehouse {warehouse[0]}: {str(e)[:50]}")
            
            target_conn.commit()
            print(f"\n✅ تم نقل {self.stats['warehouses']} مستودع")
            
        except Exception as e:
            print(f"❌ خطأ عام في نقل المستودعات: {str(e)}")
            self.stats['errors'].append(f"Warehouses: {str(e)}")
    
    def migrate_service_requests(self, backup_conn, target_conn):
        """نقل طلبات الصيانة"""
        print("\n" + "="*60)
        print("🔧 نقل طلبات الصيانة (Service Requests)...")
        print("="*60)
        
        try:
            cursor = backup_conn.cursor()
            cursor.execute("""
                SELECT customer_id, vehicle_model, vehicle_vrn, vehicle_vin,
                       vehicle_year, problem_description, diagnosis,
                       status, total_cost, created_at
                FROM service_request
            """)
            
            services = cursor.fetchall()
            
            if not services:
                print("⚠️  لا يوجد طلبات صيانة في الباك أب")
                return
            
            target_cursor = target_conn.cursor()
            
            for service in services:
                try:
                    # فحص إذا كان customer_id موجود في القاعدة الحالية
                    customer_id = service[0]
                    if customer_id:
                        target_cursor.execute(
                            "SELECT id FROM customer WHERE id = ?",
                            (customer_id,)
                        )
                        if not target_cursor.fetchone():
                            print(f"  ⏭️  طلب صيانة - عميل #{customer_id} غير موجود (تخطي)")
                            continue
                    
                    # إدراج طلب صيانة
                    target_cursor.execute("""
                        INSERT INTO service_request 
                        (customer_id, vehicle_model, vehicle_vrn, vehicle_vin,
                         vehicle_year, problem_description, diagnosis,
                         status, total_cost, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, service)
                    
                    self.stats['service_requests'] += 1
                    print(f"  ✅ طلب صيانة - {service[1] or 'N/A'} ({service[7]})")
                    
                except Exception as e:
                    print(f"  ❌ خطأ في طلب صيانة: {str(e)[:50]}")
                    self.stats['errors'].append(f"ServiceRequest: {str(e)[:50]}")
            
            target_conn.commit()
            print(f"\n✅ تم نقل {self.stats['service_requests']} طلب صيانة")
            
        except Exception as e:
            print(f"❌ خطأ عام في نقل الصيانة: {str(e)}")
            self.stats['errors'].append(f"ServiceRequests: {str(e)}")
    
    def migrate_stock_levels(self, backup_conn, target_conn):
        """نقل مستويات المخزون"""
        print("\n" + "="*60)
        print("📊 نقل مستويات المخزون (Stock Levels)...")
        print("="*60)
        
        try:
            cursor = backup_conn.cursor()
            cursor.execute("""
                SELECT product_id, warehouse_id, quantity, 
                       reserved_quantity, created_at
                FROM stock_level
            """)
            
            stocks = cursor.fetchall()
            
            if not stocks:
                print("⚠️  لا يوجد مخزون في الباك أب")
                return
            
            target_cursor = target_conn.cursor()
            
            for stock in stocks:
                try:
                    product_id = stock[0]
                    warehouse_id = stock[1]
                    
                    # فحص وجود المنتج والمستودع
                    target_cursor.execute(
                        "SELECT id FROM product WHERE id = ?",
                        (product_id,)
                    )
                    if not target_cursor.fetchone():
                        continue
                    
                    target_cursor.execute(
                        "SELECT id FROM warehouse WHERE id = ?",
                        (warehouse_id,)
                    )
                    if not target_cursor.fetchone():
                        continue
                    
                    # فحص إذا كان موجوداً
                    target_cursor.execute(
                        "SELECT id FROM stock_level WHERE product_id = ? AND warehouse_id = ?",
                        (product_id, warehouse_id)
                    )
                    
                    if target_cursor.fetchone():
                        # تحديث الكمية
                        target_cursor.execute("""
                            UPDATE stock_level 
                            SET quantity = quantity + ?, 
                                reserved_quantity = reserved_quantity + ?
                            WHERE product_id = ? AND warehouse_id = ?
                        """, (stock[2], stock[3], product_id, warehouse_id))
                        print(f"  🔄 منتج #{product_id} - مستودع #{warehouse_id} - تحديث")
                    else:
                        # إدراج جديد
                        target_cursor.execute("""
                            INSERT INTO stock_level 
                            (product_id, warehouse_id, quantity, 
                             reserved_quantity, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, stock)
                        print(f"  ✅ منتج #{product_id} - مستودع #{warehouse_id}")
                    
                    self.stats['stock_levels'] += 1
                    
                except Exception as e:
                    continue
            
            target_conn.commit()
            print(f"\n✅ تم معالجة {self.stats['stock_levels']} مستوى مخزون")
            
        except Exception as e:
            print(f"❌ خطأ عام في نقل المخزون: {str(e)}")
    
    def generate_report(self):
        """إنشاء تقرير النقل"""
        print("\n" + "="*60)
        print("📊 تقرير النقل النهائي")
        print("="*60)
        
        print(f"\n✅ تم النقل بنجاح:")
        print(f"  • الزبائن: {self.stats['customers']}")
        print(f"  • القطع: {self.stats['products']}")
        print(f"  • المستودعات: {self.stats['warehouses']}")
        print(f"  • طلبات الصيانة: {self.stats['service_requests']}")
        print(f"  • مستويات المخزون: {self.stats['stock_levels']}")
        
        if self.stats['errors']:
            print(f"\n⚠️  الأخطاء ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:
                print(f"  • {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... و {len(self.stats['errors']) - 10} أخطاء أخرى")
        
        # حفظ التقرير
        report = f"""# تقرير نقل البيانات

**التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**من:** {self.backup_file}
**إلى:** {self.target_db}

## النتائج

- **الزبائن:** {self.stats['customers']}
- **القطع:** {self.stats['products']}
- **المستودعات:** {self.stats['warehouses']}
- **طلبات الصيانة:** {self.stats['service_requests']}
- **مستويات المخزون:** {self.stats['stock_levels']}
- **الأخطاء:** {len(self.stats['errors'])}

## الأخطاء

"""
        if self.stats['errors']:
            for error in self.stats['errors']:
                report += f"- {error}\n"
        else:
            report += "✅ لا توجد أخطاء!\n"
        
        with open('MIGRATION_REPORT.md', 'w', encoding='utf-8') as f:
            f.write(report)
        
        print("\n💾 تم حفظ التقرير في: MIGRATION_REPORT.md")
    
    def migrate_all(self):
        """نقل جميع البيانات المحددة"""
        print("\n" + "="*60)
        print("🚀 بدء نقل البيانات من الباك أب")
        print("="*60)
        print(f"من: {self.backup_file}")
        print(f"إلى: {self.target_db}")
        
        # الاتصال
        backup_conn = self.connect_backup()
        if not backup_conn:
            return
        
        target_conn = self.connect_target()
        
        # نقل البيانات بالترتيب
        self.migrate_customers(backup_conn, target_conn)
        self.migrate_products(backup_conn, target_conn)
        self.migrate_warehouses(backup_conn, target_conn)
        self.migrate_stock_levels(backup_conn, target_conn)
        self.migrate_service_requests(backup_conn, target_conn)
        
        # إغلاق الاتصالات
        backup_conn.close()
        target_conn.close()
        
        # التقرير النهائي
        self.generate_report()
        
        print("\n" + "="*60)
        print("✅ اكتملت عملية النقل!")
        print("="*60)


def main():
    """النقطة الرئيسية"""
    print("\n" + "="*60)
    print("📦 استخراج بيانات من الباك أب")
    print("="*60)
    
    # البحث عن ملف الباك أب
    backup_file = 'backup_20251018_120631.db'
    
    if not os.path.exists(backup_file):
        print(f"\n❌ ملف الباك أب غير موجود: {backup_file}")
        print("\nالملفات المتاحة:")
        import glob
        backups = glob.glob('*.db') + glob.glob('instance/*.db')
        for b in backups:
            size = os.path.getsize(b) / (1024*1024)
            print(f"  • {b} ({size:.2f} MB)")
        
        print("\n💡 استخدام:")
        print("  migrator = DataMigrator('اسم_الملف.db')")
        return
    
    print(f"\n✅ تم العثور على الباك أب: {backup_file}")
    print(f"📊 الحجم: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")
    
    # تأكيد
    print("\n⚠️  ستتم العملية التالية:")
    print("  1. قراءة البيانات من الباك أب")
    print("  2. نقل: الزبائن، القطع، المستودعات، الصيانة")
    print("  3. تخطي البيانات الموجودة مسبقاً")
    print("  4. إضافة البيانات الجديدة فقط")
    
    response = input("\n✋ هل تريد المتابعة؟ (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y', 'نعم']:
        print("\n❌ تم الإلغاء")
        return
    
    # بدء النقل
    migrator = DataMigrator(backup_file)
    migrator.migrate_all()


if __name__ == '__main__':
    main()

