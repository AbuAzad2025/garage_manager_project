"""
🔐 System Permissions & Roles Configuration - إعدادات صلاحيات النظام
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تعريف كل صلاحيات النظام في مكان واحد (Single Source of Truth)
- تعريف الأدوار وصلاحياتها
- سهولة الإضافة والتعديل والصيانة

Created: 2025-11-02
Last Updated: 2025-11-02
"""

from typing import Dict, List, Set, Optional


class PermissionsRegistry:
    """
    سجل الصلاحيات المركزي
    جميع صلاحيات النظام مُعرّفة هنا
    """
    
    PERMISSIONS_AR_MAP = {
        'backup_database': 'نسخ_احتياطي',
        'restore_database': 'استعادة_نسخة',
        'hard_delete': 'حذف_قوي',
        'view_audit_logs': 'عرض_سجلات_التدقيق',
        'access_owner_dashboard': 'لوحة_المالك',
        'manage_advanced_accounting': 'محاسبة_متقدمة',
        'manage_any_user_permissions': 'تعديل_صلاحيات_المستخدمين',
        'manage_ledger': 'إدارة_الدفتر',
        'access_ai_assistant': 'مساعد_ذكي',
        'train_ai': 'تدريب_الذكاء',
        'manage_permissions': 'إدارة_الصلاحيات',
        'manage_roles': 'إدارة_الأدوار',
        'manage_users': 'إدارة_المستخدمين',
        'manage_customers': 'إدارة_العملاء',
        'add_customer': 'إضافة_عميل',
        'view_customers': 'عرض_العملاء',
        'manage_sales': 'إدارة_المبيعات',
        'view_sales': 'عرض_المبيعات',
        'manage_service': 'إدارة_الصيانة',
        'view_service': 'عرض_الصيانة',
        'manage_warehouses': 'إدارة_المستودعات',
        'view_warehouses': 'عرض_المستودعات',
        'manage_inventory': 'إدارة_الجرد',
        'view_inventory': 'عرض_الجرد',
        'warehouse_transfer': 'تحويل_مخزني',
        'view_parts': 'عرض_القطع',
        'manage_vendors': 'إدارة_الموردين',
        'add_supplier': 'إضافة_مورد',
        'add_partner': 'إضافة_شريك',
        'manage_payments': 'إدارة_المدفوعات',
        'manage_expenses': 'إدارة_المصاريف',
        'view_reports': 'عرض_التقارير',
        'manage_reports': 'إدارة_التقارير',
        'manage_exchange': 'إدارة_التحويلات',
        'manage_currencies': 'إدارة_العملات',
        'manage_shipments': 'إدارة_الشحن',
        'view_shop': 'عرض_المتجر',
        'browse_products': 'تصفح_المنتجات',
        'manage_shop': 'إدارة_المتجر',
        'place_online_order': 'طلب_أونلاين',
        'view_preorders': 'عرض_الطلبات_المسبقة',
        'add_preorder': 'إضافة_طلب_مسبق',
        'edit_preorder': 'تعديل_طلب_مسبق',
        'delete_preorder': 'حذف_طلب_مسبق',
        'access_api': 'الوصول_API',
        'manage_api': 'إدارة_API',
        'view_notes': 'عرض_الملاحظات',
        'manage_notes': 'إدارة_الملاحظات',
        'view_barcode': 'عرض_الباركود',
        'manage_barcode': 'إدارة_الباركود',
        'view_own_orders': 'عرض_طلباتي',
        'view_own_account': 'عرض_حسابي',
    }
    
    PERMISSIONS = {
        'system': {
            'backup_database': {
                'name_ar': 'نسخ احتياطي للنظام',
                'code_ar': 'نسخ_احتياطي',
                'description': 'إنشاء نسخة احتياطية من قاعدة البيانات',
                'module': 'system',
                'is_protected': True,
            },
            'restore_database': {
                'name_ar': 'استعادة نسخة احتياطية',
                'code_ar': 'استعادة_نسخة',
                'description': 'استعادة قاعدة البيانات من نسخة احتياطية',
                'module': 'system',
                'is_protected': True,
            },
            'hard_delete': {
                'name_ar': 'حذف قوي',
                'code_ar': 'حذف_قوي',
                'description': 'حذف نهائي من قاعدة البيانات',
                'module': 'system',
                'is_protected': True,
            },
            'view_audit_logs': {
                'name_ar': 'عرض سجلات التدقيق',
                'code_ar': 'عرض_سجلات_التدقيق',
                'description': 'عرض كل سجلات النظام',
                'module': 'system',
                'is_protected': True,
            },
        },
        
        'owner_only': {
            'access_owner_dashboard': {
                'name_ar': 'الوصول للوحة المالك',
                'code_ar': 'لوحة_المالك',
                'description': 'الوصول للوحة التحكم الخاصة بالمالك',
                'module': 'owner_only',
                'is_protected': True,
            },
            'manage_advanced_accounting': {
                'name_ar': 'إدارة المحاسبة المتقدمة',
                'code_ar': 'محاسبة_متقدمة',
                'description': 'الوصول لوحدات المحاسبة المتقدمة',
                'module': 'owner_only',
                'is_protected': True,
            },
            'manage_any_user_permissions': {
                'name_ar': 'إدارة صلاحيات أي مستخدم',
                'code_ar': 'تعديل_صلاحيات_المستخدمين',
                'description': 'إضافة وتعديل وحذف صلاحيات أي مستخدم',
                'module': 'owner_only',
                'is_protected': True,
            },
            'manage_ledger': {
                'name_ar': 'إدارة الدفتر',
                'code_ar': 'إدارة_الدفتر',
                'description': 'التحكم الكامل بالدفتر العام',
                'module': 'owner_only',
                'is_protected': True,
            },
        },
        
        'ai': {
            'access_ai_assistant': {
                'name_ar': 'الوصول للمساعد الذكي',
                'code_ar': 'مساعد_ذكي',
                'description': 'استخدام المساعد الذكي',
                'module': 'ai',
                'is_protected': True,
            },
            'train_ai': {
                'name_ar': 'تدريب المساعد الذكي',
                'code_ar': 'تدريب_الذكاء',
                'description': 'تدريب وإدارة المساعد الذكي',
                'module': 'ai',
                'is_protected': True,
            },
        },
        
        'users': {
            'manage_users': {
                'name_ar': 'إدارة المستخدمين',
                'code_ar': 'إدارة_المستخدمين',
                'description': 'إضافة وتعديل وحذف المستخدمين',
                'module': 'users',
                'is_protected': True,
            },
            'manage_roles': {
                'name_ar': 'إدارة الأدوار',
                'code_ar': 'إدارة_الأدوار',
                'description': 'إضافة وتعديل وحذف أدوار المستخدمين',
                'module': 'users',
                'is_protected': True,
            },
            'manage_permissions': {
                'name_ar': 'إدارة الصلاحيات',
                'code_ar': 'إدارة_الصلاحيات',
                'description': 'إضافة وتعديل وحذف الصلاحيات',
                'module': 'users',
                'is_protected': True,
            },
        },
        
        'customers': {
            'manage_customers': {
                'name_ar': 'إدارة العملاء',
                'code_ar': 'إدارة_العملاء',
                'description': 'إدارة كاملة للعملاء',
                'module': 'customers',
                'is_protected': False,
            },
            'add_customer': {
                'name_ar': 'إضافة عميل',
                'code_ar': 'إضافة_عميل',
                'description': 'إضافة عميل جديد',
                'module': 'customers',
                'is_protected': False,
            },
            'view_customers': {
                'name_ar': 'عرض العملاء',
                'code_ar': 'عرض_العملاء',
                'description': 'عرض قائمة العملاء',
                'module': 'customers',
                'is_protected': False,
            },
        },
        
        'sales': {
            'manage_sales': {
                'name_ar': 'إدارة المبيعات',
                'code_ar': 'إدارة_المبيعات',
                'description': 'إدارة كاملة للمبيعات',
                'module': 'sales',
                'is_protected': False,
            },
            'view_sales': {
                'name_ar': 'عرض المبيعات',
                'code_ar': 'عرض_المبيعات',
                'description': 'عرض قائمة المبيعات',
                'module': 'sales',
                'is_protected': False,
            },
        },
        
        'service': {
            'manage_service': {
                'name_ar': 'إدارة الصيانة',
                'code_ar': 'إدارة_الصيانة',
                'description': 'إدارة كاملة لطلبات الصيانة',
                'module': 'service',
                'is_protected': False,
            },
            'view_service': {
                'name_ar': 'عرض الصيانة',
                'code_ar': 'عرض_الصيانة',
                'description': 'عرض طلبات الصيانة',
                'module': 'service',
                'is_protected': False,
            },
        },
        
        'warehouses': {
            'manage_warehouses': {
                'name_ar': 'إدارة المستودعات',
                'code_ar': 'إدارة_المستودعات',
                'description': 'إدارة كاملة للمستودعات',
                'module': 'warehouses',
                'is_protected': False,
            },
            'view_warehouses': {
                'name_ar': 'عرض المستودعات',
                'code_ar': 'عرض_المستودعات',
                'description': 'عرض قائمة المستودعات',
                'module': 'warehouses',
                'is_protected': False,
            },
            'manage_inventory': {
                'name_ar': 'إدارة الجرد',
                'code_ar': 'إدارة_الجرد',
                'description': 'إدارة جرد المخزون',
                'module': 'warehouses',
                'is_protected': False,
            },
            'view_inventory': {
                'name_ar': 'عرض الجرد',
                'code_ar': 'عرض_الجرد',
                'description': 'عرض جرد المخزون',
                'module': 'warehouses',
                'is_protected': False,
            },
            'warehouse_transfer': {
                'name_ar': 'تحويل مخزني',
                'code_ar': 'تحويل_مخزني',
                'description': 'نقل البضائع بين المستودعات',
                'module': 'warehouses',
                'is_protected': False,
            },
            'view_parts': {
                'name_ar': 'عرض القطع',
                'code_ar': 'عرض_القطع',
                'description': 'عرض قطع الغيار',
                'module': 'warehouses',
                'is_protected': False,
            },
        },
        
        'vendors': {
            'manage_vendors': {
                'name_ar': 'إدارة الموردين',
                'code_ar': 'إدارة_الموردين',
                'description': 'إدارة الموردين والشركاء',
                'module': 'vendors',
                'is_protected': False,
            },
            'add_supplier': {
                'name_ar': 'إضافة مورد',
                'code_ar': 'إضافة_مورد',
                'description': 'إضافة مورد جديد',
                'module': 'vendors',
                'is_protected': False,
            },
            'add_partner': {
                'name_ar': 'إضافة شريك',
                'code_ar': 'إضافة_شريك',
                'description': 'إضافة شريك جديد',
                'module': 'vendors',
                'is_protected': False,
            },
        },
        
        'accounting': {
            'manage_payments': {
                'name_ar': 'إدارة المدفوعات',
                'code_ar': 'إدارة_المدفوعات',
                'description': 'إدارة المدفوعات والسندات',
                'module': 'accounting',
                'is_protected': False,
            },
            'manage_expenses': {
                'name_ar': 'إدارة المصاريف',
                'code_ar': 'إدارة_المصاريف',
                'description': 'إدارة المصاريف والرواتب',
                'module': 'accounting',
                'is_protected': False,
            },
            'view_reports': {
                'name_ar': 'عرض التقارير',
                'code_ar': 'عرض_التقارير',
                'description': 'عرض التقارير المالية',
                'module': 'accounting',
                'is_protected': False,
            },
            'manage_reports': {
                'name_ar': 'إدارة التقارير',
                'code_ar': 'إدارة_التقارير',
                'description': 'إنشاء وتعديل التقارير',
                'module': 'accounting',
                'is_protected': False,
            },
            'manage_exchange': {
                'name_ar': 'إدارة التحويلات',
                'code_ar': 'إدارة_التحويلات',
                'description': 'إدارة تحويلات العملات',
                'module': 'accounting',
                'is_protected': False,
            },
            'manage_currencies': {
                'name_ar': 'إدارة العملات',
                'code_ar': 'إدارة_العملات',
                'description': 'إدارة العملات وأسعار الصرف',
                'module': 'accounting',
                'is_protected': False,
            },
        },
        
        'shipments': {
            'manage_shipments': {
                'name_ar': 'إدارة الشحن',
                'code_ar': 'إدارة_الشحن',
                'description': 'إدارة الشحنات والتوصيل',
                'module': 'shipments',
                'is_protected': False,
            },
        },
        
        'shop': {
            'view_shop': {
                'name_ar': 'عرض المتجر',
                'code_ar': 'عرض_المتجر',
                'description': 'الدخول للمتجر الإلكتروني',
                'module': 'shop',
                'is_protected': False,
            },
            'browse_products': {
                'name_ar': 'تصفح المنتجات',
                'code_ar': 'تصفح_المنتجات',
                'description': 'تصفح منتجات المتجر',
                'module': 'shop',
                'is_protected': False,
            },
            'manage_shop': {
                'name_ar': 'إدارة المتجر',
                'code_ar': 'إدارة_المتجر',
                'description': 'إدارة المتجر الإلكتروني',
                'module': 'shop',
                'is_protected': False,
            },
            'place_online_order': {
                'name_ar': 'طلب أونلاين',
                'code_ar': 'طلب_أونلاين',
                'description': 'إنشاء طلب من المتجر',
                'module': 'shop',
                'is_protected': False,
            },
            'view_preorders': {
                'name_ar': 'عرض الطلبات المسبقة',
                'code_ar': 'عرض_الطلبات_المسبقة',
                'description': 'عرض الطلبات المسبقة',
                'module': 'shop',
                'is_protected': False,
            },
            'add_preorder': {
                'name_ar': 'إضافة طلب مسبق',
                'code_ar': 'إضافة_طلب_مسبق',
                'description': 'إضافة طلب مسبق',
                'module': 'shop',
                'is_protected': False,
            },
            'edit_preorder': {
                'name_ar': 'تعديل طلب مسبق',
                'code_ar': 'تعديل_طلب_مسبق',
                'description': 'تعديل طلب مسبق',
                'module': 'shop',
                'is_protected': False,
            },
            'delete_preorder': {
                'name_ar': 'حذف طلب مسبق',
                'code_ar': 'حذف_طلب_مسبق',
                'description': 'حذف طلب مسبق',
                'module': 'shop',
                'is_protected': False,
            },
        },
        
        'other': {
            'access_api': {
                'name_ar': 'الوصول إلى API',
                'code_ar': 'الوصول_API',
                'description': 'الوصول لواجهة API',
                'module': 'other',
                'is_protected': False,
            },
            'manage_api': {
                'name_ar': 'إدارة API',
                'code_ar': 'إدارة_API',
                'description': 'إدارة واجهة API',
                'module': 'other',
                'is_protected': False,
            },
            'view_notes': {
                'name_ar': 'عرض الملاحظات',
                'code_ar': 'عرض_الملاحظات',
                'description': 'عرض الملاحظات',
                'module': 'other',
                'is_protected': False,
            },
            'manage_notes': {
                'name_ar': 'إدارة الملاحظات',
                'code_ar': 'إدارة_الملاحظات',
                'description': 'إضافة وتعديل الملاحظات',
                'module': 'other',
                'is_protected': False,
            },
            'view_barcode': {
                'name_ar': 'عرض الباركود',
                'code_ar': 'عرض_الباركود',
                'description': 'عرض الباركود',
                'module': 'other',
                'is_protected': False,
            },
            'manage_barcode': {
                'name_ar': 'إدارة الباركود',
                'code_ar': 'إدارة_الباركود',
                'description': 'إدارة الباركود',
                'module': 'other',
                'is_protected': False,
            },
            'view_own_orders': {
                'name_ar': 'عرض طلباتي',
                'code_ar': 'عرض_طلباتي',
                'description': 'عرض طلبات المستخدم الشخصية',
                'module': 'other',
                'is_protected': False,
            },
            'view_own_account': {
                'name_ar': 'عرض حسابي',
                'code_ar': 'عرض_حسابي',
                'description': 'عرض الحساب الشخصي',
                'module': 'other',
                'is_protected': False,
            },
        },
    }
    
    
    HIERARCHY = {
        0: ['owner', 'developer'],
        1: ['super_admin', 'super'],
        2: ['admin'],
        3: ['manager'],
        4: ['staff'],
        5: ['mechanic'],
        6: ['registered_customer'],
        7: ['guest'],
    }
    
    ROLES = {
        'owner': {
            'name_ar': 'المالك',
            'description': '👑 مالك النظام - صلاحيات كاملة ومطلقة على كل شيء بلا استثناء',
            'permissions': '*',
            'exclude': [],
            'is_protected': True,
            'is_super': True,
            'level': 0,
            'max_accounts': 1,
            'special_access': [
                'access_owner_dashboard',
                'manage_advanced_accounting',
                'manage_any_user_permissions',
                'manage_ledger',
                'access_ai_assistant',
                'train_ai',
                'hard_delete',
                'view_audit_logs',
            ],
            'capabilities': {
                'can_restore_db': True,
                'can_hard_delete': True,
                'can_manage_super_admins': True,
                'can_view_all_audit_logs': True,
                'can_manage_roles': True,
                'can_manage_permissions': True,
                'can_access_everything': True,
                'can_access_owner_dashboard': True,
                'can_manage_advanced_accounting': True,
                'can_manage_any_user_permissions': True,
            },
        },
        
        'developer': {
            'name_ar': 'المطور',
            'description': '💻 مطور النظام - صلاحيات تقنية كاملة',
            'permissions': '*',
            'exclude': [],
            'is_protected': True,
            'is_super': True,
            'level': 0,
            'max_accounts': 2,
            'special_access': [
                'access_owner_dashboard',
                'manage_advanced_accounting',
                'manage_any_user_permissions',
                'manage_ledger',
                'access_ai_assistant',
                'train_ai',
                'hard_delete',
                'view_audit_logs',
            ],
            'capabilities': {
                'can_restore_db': True,
                'can_hard_delete': True,
                'can_manage_super_admins': True,
                'can_view_all_audit_logs': True,
                'can_manage_roles': True,
                'can_manage_permissions': True,
                'can_access_everything': True,
                'can_access_owner_dashboard': True,
                'can_manage_advanced_accounting': True,
                'can_manage_any_user_permissions': True,
            },
        },
        
        'super_admin': {
            'name_ar': 'المدير الأعلى',
            'description': '⚡ مدير النظام - صلاحيات كاملة تقريباً',
            'permissions': '*',
            'exclude': ['access_owner_dashboard', 'manage_advanced_accounting', 'manage_any_user_permissions', 'hard_delete'],
            'is_protected': True,
            'is_super': True,
            'level': 1,
            'max_accounts': None,
            'special_access': [
                'access_ai_assistant',
                'train_ai',
            ],
            'capabilities': {
                'can_restore_db': True,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': True,
                'can_manage_roles': True,
                'can_manage_permissions': True,
                'can_access_everything': False,
                'can_access_owner_dashboard': False,
                'can_manage_advanced_accounting': False,
                'can_manage_any_user_permissions': False,
            },
        },
        
        'super': {
            'name_ar': 'سوبر',
            'description': '⚡ سوبر - نفس صلاحيات المدير الأعلى',
            'permissions': '*',
            'exclude': ['access_owner_dashboard', 'manage_advanced_accounting', 'manage_any_user_permissions', 'hard_delete'],
            'is_protected': True,
            'is_super': True,
            'level': 1,
            'max_accounts': None,
            'special_access': [
                'access_ai_assistant',
                'train_ai',
            ],
            'capabilities': {
                'can_restore_db': True,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': True,
                'can_manage_roles': True,
                'can_manage_permissions': True,
                'can_access_everything': False,
                'can_access_owner_dashboard': False,
                'can_manage_advanced_accounting': False,
                'can_manage_any_user_permissions': False,
            },
        },
        
        'admin': {
            'name_ar': 'المدير',
            'description': '🎯 المدير - إدارة يومية كاملة',
            'permissions': '*',
            'exclude': ['restore_database', 'access_owner_dashboard', 'manage_advanced_accounting', 'manage_any_user_permissions', 'hard_delete', 'access_ai_assistant', 'train_ai', 'manage_ledger'],
            'is_protected': True,
            'is_super': False,
            'level': 2,
            'max_accounts': None,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': True,
                'can_manage_permissions': False,
                'can_access_everything': False,
                'can_access_owner_dashboard': False,
                'can_manage_advanced_accounting': False,
                'can_manage_any_user_permissions': False,
            },
        },
        
        'manager': {
            'name_ar': 'المشرف',
            'description': '👨‍💼 مشرف - إشراف على العمليات اليومية',
            'permissions': [
                'manage_customers', 'add_customer', 'view_customers',
                'manage_service', 'view_service',
                'manage_sales', 'view_sales',
                'manage_payments', 'manage_expenses',
                'manage_warehouses', 'view_warehouses', 'manage_inventory', 'view_inventory', 'warehouse_transfer',
                'manage_vendors', 'add_supplier', 'add_partner',
                'view_reports', 'manage_reports',
                'view_parts',
                'view_notes', 'manage_notes',
                'view_barcode', 'manage_barcode',
            ],
            'is_protected': False,
            'is_super': False,
            'level': 3,
            'max_accounts': None,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': False,
                'can_manage_permissions': False,
                'can_access_everything': False,
            },
        },
        
        'staff': {
            'name_ar': 'الموظف',
            'description': '👨‍💻 موظف - المبيعات والصيانة والمحاسبة',
            'permissions': [
                'manage_customers', 'add_customer', 'view_customers',
                'manage_service', 'view_service',
                'manage_sales', 'view_sales',
                'manage_payments', 'manage_expenses',
                'view_warehouses', 'view_inventory', 'view_parts',
                'view_reports',
                'view_notes',
            ],
            'is_protected': False,
            'is_super': False,
            'level': 4,
            'max_accounts': None,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': False,
                'can_manage_permissions': False,
                'can_access_everything': False,
            },
        },
        
        'mechanic': {
            'name_ar': 'الميكانيكي',
            'description': '🔧 ميكانيكي - الصيانة والقطع فقط',
            'permissions': [
                'manage_service', 'view_service',
                'view_warehouses', 'view_inventory', 'view_parts',
                'view_reports',
            ],
            'is_protected': False,
            'is_super': False,
            'level': 5,
            'max_accounts': None,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': False,
                'can_manage_permissions': False,
                'can_access_everything': False,
            },
        },
        
        'registered_customer': {
            'name_ar': 'عميل مسجل',
            'description': '🛒 عميل - التصفح والطلبات الشخصية',
            'permissions': [
                'view_shop', 'browse_products',
                'place_online_order',
                'view_preorders',
                'view_own_orders',
                'view_own_account',
            ],
            'is_protected': False,
            'is_super': False,
            'level': 6,
            'max_accounts': None,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': False,
                'can_manage_permissions': False,
                'can_access_everything': False,
            },
        },
        
        'guest': {
            'name_ar': 'ضيف',
            'description': '👤 زائر غير مسجل - تصفح المتجر فقط',
            'permissions': [
                'view_shop',
                'browse_products',
            ],
            'is_protected': False,
            'is_super': False,
            'level': 7,
            'max_accounts': None,
            'requires_authentication': False,
            'capabilities': {
                'can_restore_db': False,
                'can_hard_delete': False,
                'can_manage_super_admins': False,
                'can_view_all_audit_logs': False,
                'can_manage_roles': False,
                'can_manage_permissions': False,
                'can_access_everything': False,
            },
        },
    }
    
    
    @classmethod
    def get_all_permissions(cls) -> Dict[str, Dict]:
        """
        جلب كل الصلاحيات مع معلوماتها
        
        Returns:
            dict: {code: {name_ar, description, module, is_protected}}
        """
        all_perms = {}
        for module, perms in cls.PERMISSIONS.items():
            all_perms.update(perms)
        return all_perms
    
    
    @classmethod
    def get_all_permission_codes(cls) -> Set[str]:
        """
        جلب كل أكواد الصلاحيات فقط
        
        Returns:
            set: {'manage_users', 'manage_sales', ...}
        """
        return set(cls.get_all_permissions().keys())
    
    
    @classmethod
    def get_permissions_by_module(cls, module: str) -> Dict[str, Dict]:
        """
        جلب صلاحيات وحدة معينة
        
        Args:
            module: اسم الوحدة (users, sales, ...)
        
        Returns:
            dict: الصلاحيات الخاصة بالوحدة
        """
        return cls.PERMISSIONS.get(module, {})
    
    
    @classmethod
    def get_protected_permissions(cls) -> Set[str]:
        """
        جلب الصلاحيات المحمية (لا يمكن حذفها)
        
        Returns:
            set: أكواد الصلاحيات المحمية
        """
        protected = set()
        for perm_code, perm_data in cls.get_all_permissions().items():
            if perm_data.get('is_protected', False):
                protected.add(perm_code)
        return protected
    
    
    @classmethod
    def get_role_permissions(cls, role_name: str) -> Set[str]:
        """
        جلب صلاحيات دور معين
        
        Args:
            role_name: اسم الدور
        
        Returns:
            set: أكواد الصلاحيات
        """
        if role_name not in cls.ROLES:
            return set()
        
        role = cls.ROLES[role_name]
        
        if role['permissions'] == '*':
            all_perms = cls.get_all_permission_codes()
            exclude = set(role.get('exclude', []))
            return all_perms - exclude
        
        return set(role['permissions'])
    
    
    @classmethod
    def is_permission_protected(cls, code: str) -> bool:
        """
        هل الصلاحية محمية؟
        
        Args:
            code: كود الصلاحية
        
        Returns:
            bool
        """
        all_perms = cls.get_all_permissions()
        return all_perms.get(code, {}).get('is_protected', False)
    
    
    @classmethod
    def is_role_protected(cls, role_name: str) -> bool:
        """
        هل الدور محمي؟
        
        Args:
            role_name: اسم الدور
        
        Returns:
            bool
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return False
        return role.get('is_protected', False)
    
    
    @classmethod
    def get_permission_info(cls, code: str) -> Optional[Dict]:
        """
        جلب معلومات صلاحية معينة
        
        Args:
            code: كود الصلاحية
        
        Returns:
            dict أو None
        """
        return cls.get_all_permissions().get(code)
    
    
    @classmethod
    def get_super_roles(cls) -> Set[str]:
        """
        جلب الأدوار التي لها is_super = True
        
        Returns:
            set: {'owner', 'developer', 'super_admin', 'super'}
        """
        return {
            role_name 
            for role_name, role_data in cls.ROLES.items() 
            if role_data.get('is_super', False)
        }
    
    
    @classmethod
    def get_roles_by_level(cls, level: int) -> List[str]:
        """
        جلب الأدوار في مستوى معين
        
        Args:
            level: المستوى (0-7)
        
        Returns:
            list: أسماء الأدوار
        """
        return [
            role_name 
            for role_name, role_data in cls.ROLES.items() 
            if role_data.get('level') == level
        ]
    
    
    @classmethod
    def is_role_super(cls, role_name: str) -> bool:
        """
        هل الدور من الأدوار العليا (Super)؟
        
        Args:
            role_name: اسم الدور
        
        Returns:
            bool
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return False
        return role.get('is_super', False)
    
    
    @classmethod
    def can_role_do(cls, role_name: str, capability: str) -> bool:
        """
        هل الدور يستطيع القيام بإجراء معين؟
        
        Args:
            role_name: اسم الدور
            capability: الإجراء (can_restore_db, can_hard_delete, ...)
        
        Returns:
            bool
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return False
        
        capabilities = role.get('capabilities', {})
        return capabilities.get(capability, False)
    
    
    @classmethod
    def get_role_level(cls, role_name: str) -> int:
        """
        جلب مستوى الدور
        
        Args:
            role_name: اسم الدور
        
        Returns:
            int: المستوى (0 = أعلى، 7 = أدنى)
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return 999
        return role.get('level', 999)
    
    
    @classmethod
    def is_role_higher_than(cls, role1: str, role2: str) -> bool:
        """
        هل role1 أعلى من role2؟
        
        Args:
            role1: الدور الأول
            role2: الدور الثاني
        
        Returns:
            bool
        """
        return cls.get_role_level(role1) < cls.get_role_level(role2)
    
    
    @classmethod
    def requires_authentication(cls, role_name: str) -> bool:
        """
        هل الدور يحتاج تسجيل دخول؟
        
        Args:
            role_name: اسم الدور
        
        Returns:
            bool (افتراضياً True عدا guest)
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return True
        return role.get('requires_authentication', True)
    
    
    @classmethod
    def get_role_max_accounts(cls, role_name: str) -> Optional[int]:
        """
        كم عدد الحسابات المسموح بها لهذا الدور؟
        
        Args:
            role_name: اسم الدور
        
        Returns:
            int أو None (None = غير محدود)
        """
        role = cls.ROLES.get(role_name)
        if not role:
            return None
        return role.get('max_accounts')
    
    
    @classmethod
    def validate_role_creation(cls, role_name: str, current_count: int = 0) -> tuple[bool, str]:
        """
        التحقق من إمكانية إنشاء حساب جديد لهذا الدور
        
        Args:
            role_name: اسم الدور
            current_count: عدد الحسابات الحالية
        
        Returns:
            (bool, str): (هل يمكن الإنشاء؟, رسالة)
        """
        max_accounts = cls.get_role_max_accounts(role_name)
        
        if max_accounts is None:
            return (True, "")
        
        if current_count >= max_accounts:
            role_ar = cls.ROLES.get(role_name, {}).get('name_ar', role_name)
            return (False, f"الحد الأقصى لحسابات {role_ar}: {max_accounts}")
        
        return (True, "")
    
    
    @classmethod
    def get_permission_by_arabic(cls, code_ar: str) -> Optional[str]:
        """
        البحث عن الصلاحية بالكود العربي
        
        Args:
            code_ar: الكود بالعربية (مثل: 'إدارة_المستخدمين')
        
        Returns:
            str: الكود الإنجليزي أو None
        """
        for eng_code, ar_code in cls.PERMISSIONS_AR_MAP.items():
            if ar_code == code_ar:
                return eng_code
        return None
    
    
    @classmethod
    def get_arabic_code(cls, english_code: str) -> Optional[str]:
        """
        الحصول على الكود العربي من الكود الإنجليزي
        
        Args:
            english_code: الكود بالإنجليزية
        
        Returns:
            str: الكود بالعربية أو None
        """
        return cls.PERMISSIONS_AR_MAP.get(english_code)
    
    
    @classmethod
    def supports_arabic_codes(cls) -> bool:
        """هل النظام يدعم الأكواد العربية؟"""
        return True


__all__ = [
    'PermissionsRegistry',
]

