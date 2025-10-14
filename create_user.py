# create_user.py - User Creation Utility
# Location: /garage_manager/create_user.py
# Description: Utility script for creating new users

from app import create_app
from models import User, Role
from extensions import db

app = create_app()

with app.app_context():
    admin_role = Role.query.filter_by(name='مدير عام').first()
    if not admin_role:
        admin_role = Role(name='مدير عام', description='مدير عام للنظام')
        db.session.add(admin_role)
        db.session.flush()
    
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
