#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from app import create_app
from models import User, Role
from extensions import db

app = create_app()

with app.app_context():
    # إنشاء دور مدير عام
    admin_role = Role.query.filter_by(name='مدير عام').first()
    if not admin_role:
        admin_role = Role(name='مدير عام', description='مدير عام للنظام')
        db.session.add(admin_role)
        db.session.flush()
    
    # إنشاء مستخدم ازاد
    user = User.query.filter_by(username='ازاد').first()
    if not user:
        user = User(
            username='ازاد',
            email='azad@garage.ps',
            role_id=admin_role.id,
            is_active=True
        )
        user.set_password('AZ123456')
        db.session.add(user)
        db.session.commit()
        print('✅ تم إنشاء المستخدم ازاد بنجاح!')
    else:
        print('⚠️ المستخدم ازاد موجود بالفعل!')
