#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
إنشاء حساب المالك
Create Owner Account
"""

from extensions import db
from app import app
from models import User, Role

print('')
print('╔══════════════════════════════════════════════════════════════╗')
print('║           🔐 إنشاء حساب المالك                            ║')
print('╚══════════════════════════════════════════════════════════════╝')
print('')

with app.app_context():
    try:
        # البحث عن دور المالك
        owner_role = Role.query.filter_by(name='Owner').first()
        if not owner_role:
            print('⚠️  دور Owner غير موجود!')
            print('💡 يرجى التأكد من إنشاء الأدوار أولاً')
            exit(1)
        
        # البحث عن حساب المالك الموجود
        existing_owner = User.query.filter_by(username='owner').first()
        
        if existing_owner:
            print('✅ حساب المالك موجود مسبقاً!')
            print('')
            print('📋 معلومات الدخول:')
            print('─' * 62)
            print(f'  👤 اسم المستخدم: owner')
            print(f'  🔑 كلمة المرور: OwnerPass2024!')
            print('─' * 62)
            print('')
            print('⚠️  ملاحظة: إذا نسيت كلمة المرور، يمكنك تغييرها من لوحة التحكم')
        else:
            # إنشاء حساب جديد
            owner = User(
                username='owner',
                email='owner@system.local',
                role_id=owner_role.id,
                is_active=True,
                is_system_account=True
            )
            owner.set_password('OwnerPass2024!')
            
            db.session.add(owner)
            db.session.commit()
            
            print('✅ تم إنشاء حساب المالك بنجاح!')
            print('')
            print('📋 معلومات الدخول:')
            print('═' * 62)
            print(f'  👤 اسم المستخدم: owner')
            print(f'  🔑 كلمة المرور: OwnerPass2024!')
            print('═' * 62)
            print('')
            print('⚠️  مهم جداً: غيّر كلمة المرور فوراً بعد تسجيل الدخول!')
            print('')
            print('🔒 الحماية:')
            print('  • محمي من الحذف')
            print('  • محمي من التعديل')
            print('  • مخفي من القوائم')
            print('  • صلاحيات كاملة (41 صلاحية)')
        
        print('')
        print('🌐 الوصول إلى النظام:')
        print('  http://localhost:5000')
        print('')
        
    except Exception as e:
        db.session.rollback()
        print(f'❌ خطأ: {str(e)}')
        import traceback
        traceback.print_exc()

