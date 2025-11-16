"""
🔐 AI Permissions & Access Control - صلاحيات المساعد الذكي
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- إدارة صلاحيات المساعد الذكي
- التحكم في من يرى المساعد
- صلاحيات تنفيذ العمليات

Created: 2025-11-01
"""

import json
from typing import Dict, List, Any, Optional
from flask import current_app
from models import SystemSettings


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 AI PERMISSIONS - صلاحيات المساعد
# ═══════════════════════════════════════════════════════════════════════════

AI_CAPABILITIES = {
    "data_access": {
        "read_customers": True,
        "read_suppliers": True,
        "read_products": True,
        "read_sales": True,
        "read_payments": True,
        "read_expenses": True,
        "read_gl": True,
        "read_services": True,
        "read_inventory": True,
        "read_reports": True,
        "read_users": True,  # للمالك فقط
        "read_settings": True,  # للمالك فقط
        "read_audit": True  # للمالك فقط
    },
    
    "data_write": {
        "create_customer": True,
        "create_supplier": True,
        "create_product": True,
        "create_sale": True,
        "create_payment": True,
        "create_expense": True,
        "create_service": True,
        "create_warehouse": True,
        "adjust_stock": True,
        "transfer_stock": True,
        "create_invoice": True
    },
    
    "data_modify": {
        "update_customer": True,
        "update_supplier": True,
        "update_product": True,
        "update_sale": False,  # خطير - ممنوع
        "update_payment": False,  # خطير - ممنوع
        "update_gl": False,  # خطير جداً - ممنوع
        "delete_any": False  # الحذف ممنوع كلياً
    },
    
    "ai_features": {
        "chat": True,
        "realtime_alerts": True,
        "auto_learning": True,
        "suggestions": True,
        "analysis": True,
        "reports": True,
        "predictions": True,
        "training": True  # للمالك فقط
    }
}


def get_ai_permission_setting(key: str, default: Any = None) -> Any:
    """
    الحصول على إعداد صلاحية المساعد
    
    Args:
        key: مفتاح الإعداد (ai_enabled, ai_visible_to_staff, etc.)
        default: القيمة الافتراضية
    
    Returns:
        قيمة الإعداد
    """
    try:
        setting = SystemSettings.query.filter_by(key=key).first()
        
        if setting:
            value = setting.value
            dtype = setting.data_type or 'string'
            if dtype == 'boolean':
                if isinstance(value, str):
                    return value.lower() in ['true', '1', 'yes', 'on']
                return bool(value)
            if dtype in ['integer', 'number']:
                try:
                    return int(value) if dtype == 'integer' else float(value)
                except (TypeError, ValueError):
                    return default
            if dtype == 'json':
                try:
                    return json.loads(value)
                except Exception:
                    return default
            return value
        
        return default
    
    except Exception as e:
        return default


def is_ai_enabled() -> bool:
    """هل المساعد مفعّل في النظام؟"""
    return get_ai_permission_setting('ai_enabled', True)


def is_ai_visible_to_role(role_name: str) -> bool:
    """
    هل المساعد ظاهر لهذا الدور؟
    
    Args:
        role_name: اسم الدور (owner, manager, admin, staff, etc.)
    
    Returns:
        True/False
    """
    # المالك دائماً يرى
    if role_name in ['owner', '__OWNER__']:
        return True
    
    # فحص الإعدادات
    if role_name in ['manager', 'مدير', 'admin']:
        return get_ai_permission_setting('ai_visible_to_managers', True)
    
    if role_name in ['staff', 'موظف']:
        return get_ai_permission_setting('ai_visible_to_staff', False)
    
    # افتراضياً: ممنوع
    return False


def can_ai_execute_action(action_type: str, user_role: str) -> bool:
    """
    هل المساعد يستطيع تنفيذ هذا الإجراء لهذا المستخدم؟
    
    Args:
        action_type: نوع الإجراء (add_customer, create_payment, etc.)
        user_role: دور المستخدم
    
    Returns:
        True/False
    """
    # المالك: كل شيء
    if user_role in ['owner', '__OWNER__']:
        return True
    
    # المدراء: معظم الأشياء
    if user_role in ['manager', 'مدير', 'admin']:
        # ممنوع: تعديل GL، حذف، تعديل دفعات
        forbidden = ['update_gl', 'delete_', 'update_payment']
        
        if any(f in action_type for f in forbidden):
            return False
        
        return True
    
    # الموظفين: محدود
    if user_role in ['staff', 'موظف']:
        # مسموح فقط: قراءة + إضافة بسيطة
        allowed = ['add_customer', 'create_service', 'add_product']
        
        return action_type in allowed
    
    # افتراضياً: ممنوع
    return False


def get_ai_access_level(user) -> str:
    """
    الحصول على مستوى الوصول للمساعد
    
    Returns:
        'full' | 'limited' | 'readonly' | 'none'
    """
    if not user or not user.is_authenticated:
        return 'none'
    
    # المالك: وصول كامل
    if user.is_system_account or user.username == '__OWNER__':
        return 'full'
    
    # فحص إذا كان المساعد مخفي
    if not is_ai_enabled():
        return 'none'
    
    # حسب الدور
    role_name = user.role.name if user.role else 'guest'
    
    if is_ai_visible_to_role(role_name):
        if role_name in ['manager', 'مدير', 'admin']:
            return 'limited'  # قراءة + بعض الكتابة
        else:
            return 'readonly'  # قراءة فقط
    
    return 'none'


__all__ = [
    'AI_CAPABILITIES',
    'get_ai_permission_setting',
    'is_ai_enabled',
    'is_ai_visible_to_role',
    'can_ai_execute_action',
    'get_ai_access_level'
]

