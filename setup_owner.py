#!/usr/bin/env python
"""Setup Owner Account - Final Version"""
import sqlite3
import sys
import os
from werkzeug.security import generate_password_hash

# إنشاء المجلد إذا لم يكن موجوداً
os.makedirs('instance', exist_ok=True)
DB_PATH = 'instance/app.db'

def main():
    print("\n" + "="*70)
    print("🔧 إعداد حساب المالك النهائي")
    print("="*70 + "\n")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. إضافة الحقل
    print("1️⃣ إضافة حقل is_system_account...")
    try:
        c.execute("ALTER TABLE users ADD COLUMN is_system_account INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("   ✅ تم إضافة الحقل")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print("   ✅ الحقل موجود مسبقاً")
        else:
            print(f"   ❌ خطأ: {e}")
            sys.exit(1)
    
    # 2. إنشاء الفهرس
    print("\n2️⃣ إنشاء الفهرس...")
    try:
        c.execute("CREATE INDEX ix_users_is_system_account ON users(is_system_account)")
        conn.commit()
        print("   ✅ تم إنشاء الفهرس")
    except sqlite3.OperationalError as e:
        if 'already exists' in str(e).lower():
            print("   ✅ الفهرس موجود مسبقاً")
        else:
            print(f"   ❌ خطأ: {e}")
    
    # 3. فحص دور Super Admin
    print("\n3️⃣ فحص دور Super Admin...")
    c.execute("SELECT id, name FROM roles WHERE name = 'Super Admin' OR name = 'Owner'")
    role = c.fetchone()
    if not role:
        print("   ⚠️  دور Super Admin غير موجود - جاري الإنشاء...")
        # فحص أعمدة الجدول
        c.execute("PRAGMA table_info(roles)")
        role_columns = [r[1] for r in c.fetchall()]
        print(f"      أعمدة roles: {role_columns}")
        
        # بناء الاستعلام حسب الأعمدة الموجودة
        cols = ['name', 'description']
        vals = ['Super Admin', 'صلاحيات كاملة وغير محدودة - Owner Account']
        placeholders = ['?', '?']
        
        if 'name_ar' in role_columns:
            cols.append('name_ar')
            vals.append('المالك الأعلى')
            placeholders.append('?')
        
        if 'is_default' in role_columns:
            cols.append('is_default')
            vals.append(0)
            placeholders.append('?')
        
        query = f"INSERT INTO roles ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        c.execute(query, vals)
        conn.commit()
        
        c.execute("SELECT id FROM roles WHERE name = 'Super Admin'")
        role = c.fetchone()
        print(f"   ✅ تم إنشاء الدور (ID: {role[0]})")
    else:
        print(f"   ✅ الدور موجود (ID: {role[0]})")
    
    role_id = role[0]
    
    # 4. منح جميع الصلاحيات
    print("\n4️⃣ منح جميع الصلاحيات لـ Super Admin...")
    c.execute("SELECT COUNT(*) FROM permissions")
    total_perms = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM role_permissions 
        WHERE role_id = ?
    """, (role_id,))
    current_perms = c.fetchone()[0]
    
    if current_perms < total_perms:
        c.execute("""
            INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
            SELECT ?, id FROM permissions
        """, (role_id,))
        conn.commit()
        print(f"   ✅ تم منح {total_perms} صلاحية")
    else:
        print(f"   ✅ الدور لديه جميع الصلاحيات ({total_perms})")
    
    # 5. فحص/إنشاء حساب المالك
    print("\n5️⃣ إعداد حساب المالك...")
    c.execute("SELECT id, username, email FROM users WHERE username = '__OWNER__'")
    owner = c.fetchone()
    
    if owner:
        print(f"   ✅ الحساب موجود (ID: {owner[0]})")
        print(f"      Username: {owner[1]}")
        print(f"      Email: {owner[2]}")
        
        # تحديث الحساب
        c.execute("""
            UPDATE users 
            SET is_system_account = 1,
                role_id = ?,
                is_active = 1
            WHERE username = '__OWNER__'
        """, (role_id,))
        conn.commit()
        print("   ✅ تم تحديث الحساب")
    else:
        print("   📝 إنشاء حساب المالك...")
        password = "Owner@2025!#SecurePassword"
        password_hash = generate_password_hash(password)
        
        # فحص أعمدة جدول users
        c.execute("PRAGMA table_info(users)")
        user_columns = [r[1] for r in c.fetchall()]
        print(f"      أعمدة users: {user_columns}")
        
        # بناء الاستعلام حسب الأعمدة الموجودة
        cols = ['username', 'email', 'password_hash', 'role_id', 'is_active', 'is_system_account']
        vals = ['__OWNER__', 'owner@azad-systems.local', password_hash, role_id, 1, 1]
        placeholders = ['?', '?', '?', '?', '?', '?']
        
        if 'full_name' in user_columns:
            cols.append('full_name')
            vals.append('System Owner - مالك النظام')
            placeholders.append('?')
        
        if 'full_name_ar' in user_columns:
            cols.append('full_name_ar')
            vals.append('مالك النظام')
            placeholders.append('?')
        
        if 'phone' in user_columns:
            cols.append('phone')
            vals.append('0000000000')
            placeholders.append('?')
        
        if 'created_by' in user_columns:
            cols.append('created_by')
            vals.append(0)
            placeholders.append('?')
        
        query = f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        c.execute(query, vals)
        conn.commit()
        
        c.execute("SELECT id FROM users WHERE username = '__OWNER__'")
        new_owner = c.fetchone()
        
        print(f"   ✅ تم إنشاء الحساب (ID: {new_owner[0]})")
        print(f"\n   📌 معلومات الدخول:")
        print(f"      Username: __OWNER__")
        print(f"      Password: {password}")
        print(f"      Email: owner@azad-systems.local")
    
    # 6. التحقق النهائي
    print("\n6️⃣ التحقق النهائي...")
    c.execute("""
        SELECT u.id, u.username, u.is_system_account, r.name, COUNT(DISTINCT rp.permission_id)
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        WHERE u.username = '__OWNER__'
        GROUP BY u.id
    """)
    result = c.fetchone()
    
    if result:
        print(f"   ✅ الحساب نشط:")
        print(f"      - ID: {result[0]}")
        print(f"      - Username: {result[1]}")
        print(f"      - is_system_account: {result[2]}")
        print(f"      - Role: {result[3]}")
        print(f"      - Permissions: {result[4]}")
    
    conn.close()
    
    print("\n" + "="*70)
    print("✅ الإعداد مكتمل بنجاح!")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()

