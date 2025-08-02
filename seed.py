from from modelsextensions import db, mail
from from models import Role, Permission, User
from from models import clear_user_permission_cache

def seed_roles_permissions():
    """
    يزرع الصلاحيات والأدوار الافتراضية في قاعدة البيانات:
      - Developer: جميع الصلاحيات
      - Manager: إدارة المبيعات + تقارير + عملاء + مدفوعات + نسخ احتياطي
      - Mechanic: الصيانة فقط
      - RegisteredCustomer: حجز المنتجات أونلاين
      - AnonymousCustomer: عرض الكتالوج فقط
    """
    # قائمة الصلاحيات الجديدة
    permissions = [
        'manage_sales',
        'manage_service',
        'manage_roles',
        'manage_permissions',
        'manage_users',           # ← أضفنا هذه الصلاحية
        'view_reports',
        'backup_database',
        'restore_database',
        'manage_customers',
        'manage_payments',
        'place_online_order',     # للعملاء المسجلين
        'view_online_catalog'     # للزوار
    ]

    # إنشاء أو تحديث كل صلاحية
    for name in permissions:
        p = Permission.query.filter_by(name=name).first()
        if not p:
            p = Permission(name=name)
            db.session.add(p)
    db.session.commit()

    # تعريف الأدوار وربطها بالصلاحيات
    roles_def = {
        'Developer': permissions,
        'Manager': [
            'manage_sales',
            'view_reports',
            'manage_customers',
            'manage_payments',
            'backup_database',
            'manage_users'      # ← منح المدير صلاحية إدارة المستخدمين
        ],
        'Mechanic': ['manage_service'],
        'RegisteredCustomer': ['place_online_order'],
        'AnonymousCustomer': ['view_online_catalog']
    }

    for role_name, perms in roles_def.items():
        r = Role.query.filter_by(name=role_name).first()
        if not r:
            r = Role(name=role_name, description=f"Seeded role: {role_name}")
            db.session.add(r)
            db.session.flush()
        r.permissions = Permission.query.filter(Permission.name.in_(perms)).all()

    db.session.commit()

    # مسح كاش صلاحيات جميع المستخدمين لتعكس التغييرات فوراً
    for (user_id,) in User.query.with_entities(User.id).all():
        clear_user_permission_cache(user_id)

if __name__ == '__main__':
    # لتشغيل الزرع يدوياً: python seed.py
    from app import create_app
    app = create_app()
    with app.app_context():
        seed_roles_permissions()
    print("Seeding and cache cleared: Done.")
