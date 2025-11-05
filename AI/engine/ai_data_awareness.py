

import os
import json
from datetime import datetime
from pathlib import Path
from sqlalchemy import inspect
from sqlalchemy.orm import class_mapper

DATA_SCHEMA_FILE = 'AI/data/ai_data_schema.json'
LEARNING_LOG_FILE = 'AI/data/ai_learning_log.json'

def discover_all_models():
    try:
        from models import (
            User, Customer, Supplier, Product, ServiceRequest, Invoice, Payment,
            Warehouse, StockLevel, Note, Shipment, AuditLog, Role, Permission,
            ExchangeTransaction, Expense, ExpenseType, Account, Partner,
            PartnerSettlement, SupplierSettlement, PreOrder, OnlineCart,
            ServicePart, ServiceTask, Currency, ProductRating, SystemSettings
        )
        
        models = [
            User, Customer, Supplier, Product, ServiceRequest, Invoice, Payment,
            Warehouse, StockLevel, Note, Shipment, AuditLog, Role, Permission,
            ExchangeTransaction, Expense, ExpenseType, Account, Partner,
            PartnerSettlement, SupplierSettlement, PreOrder, OnlineCart,
            ServicePart, ServiceTask, Currency, ProductRating, SystemSettings
        ]
        
        return models
    
    except Exception as e:
        pass  # خطأ محتمل
        return []

def analyze_model_structure(model):
    """تحليل بنية نموذج واحد"""
    try:
        mapper = class_mapper(model)
        columns = []
        relationships = []
        
        # تحليل الأعمدة
        for column in mapper.columns:
            col_info = {
                'name': column.name,
                'type': str(column.type),
                'nullable': column.nullable,
                'primary_key': column.primary_key,
                'foreign_key': len(column.foreign_keys) > 0,
            }
            columns.append(col_info)
        
        # تحليل العلاقات
        for rel in mapper.relationships:
            rel_info = {
                'name': rel.key,
                'target': rel.mapper.class_.__name__,
                'uselist': rel.uselist,  # Many or One
                'type': 'one-to-many' if rel.uselist else 'many-to-one'
            }
            relationships.append(rel_info)
        
        return {
            'table_name': mapper.local_table.name,
            'class_name': model.__name__,
            'columns_count': len(columns),
            'columns': columns,
            'relationships_count': len(relationships),
            'relationships': relationships,
        }
    
    except Exception as e:
        return {
            'table_name': 'unknown',
            'class_name': model.__name__ if hasattr(model, '__name__') else 'unknown',
            'error': str(e)
        }

def build_functional_mapping():
    """بناء خريطة الوعي الوظيفي"""
    return {
        'الصيانة': {
            'models': ['ServiceRequest', 'ServicePart', 'ServiceTask'],
            'primary_table': 'service_request',
            'purpose': 'إدارة طلبات الصيانة وقطع الغيار والمهام',
            'keywords': ['صيانة', 'إصلاح', 'عطل', 'تشخيص', 'workshop', 'service']
        },
        'النفقات': {
            'models': ['Expense', 'ExpenseType'],
            'primary_table': 'expense',
            'purpose': 'تتبع المصاريف والنفقات',
            'keywords': ['نفقة', 'مصروف', 'مصاريف', 'expense']
        },
        'المحاسبة': {
            'models': ['Account', 'ExchangeTransaction'],
            'primary_table': 'account',
            'purpose': 'إدارة دفتر الأستاذ والحسابات',
            'keywords': ['دفتر', 'حساب', 'محاسبة', 'ledger', 'accounting']
        },
        'المتجر': {
            'models': ['Product', 'OnlineCart', 'PreOrder', 'ProductRating'],
            'primary_table': 'product',
            'purpose': 'المبيعات والمتجر الإلكتروني',
            'keywords': ['متجر', 'منتج', 'طلب', 'سلة', 'shop', 'store', 'product']
        },
        'المبيعات': {
            'models': ['Invoice', 'Payment'],
            'primary_table': 'invoice',
            'purpose': 'إدارة الفواتير والمدفوعات',
            'keywords': ['فاتورة', 'دفع', 'مبيعات', 'invoice', 'payment', 'sales']
        },
        'العملاء': {
            'models': ['Customer'],
            'primary_table': 'customer',
            'purpose': 'إدارة بيانات العملاء',
            'keywords': ['عميل', 'زبون', 'customer', 'client']
        },
        'الموردين': {
            'models': ['Supplier', 'SupplierSettlement'],
            'primary_table': 'supplier',
            'purpose': 'إدارة الموردين والمشتريات',
            'keywords': ['مورد', 'شراء', 'supplier', 'vendor']
        },
        'المخازن': {
            'models': ['Warehouse', 'StockLevel', 'Shipment'],
            'primary_table': 'warehouse',
            'purpose': 'إدارة المخزون والشحنات',
            'keywords': ['مخزن', 'مخزون', 'شحنة', 'warehouse', 'stock', 'inventory']
        },
        'الشركاء': {
            'models': ['Partner', 'PartnerSettlement'],
            'primary_table': 'partner',
            'purpose': 'إدارة الشراكات والتسويات',
            'keywords': ['شريك', 'شراكة', 'تسوية', 'partner', 'settlement']
        },
        'الضرائب والعملات': {
            'models': ['ExchangeTransaction', 'Currency'],
            'primary_table': 'exchange_transaction',
            'purpose': 'إدارة أسعار الصرف والضرائب',
            'keywords': ['ضريبة', 'صرف', 'عملة', 'دولار', 'tax', 'exchange', 'currency']
        },
        'المستخدمين والأمان': {
            'models': ['User', 'Role', 'Permission', 'AuditLog'],
            'primary_table': 'user',
            'purpose': 'إدارة المستخدمين والصلاحيات',
            'keywords': ['مستخدم', 'صلاحية', 'دور', 'user', 'role', 'permission', 'audit']
        },
        'الملاحظات': {
            'models': ['Note'],
            'primary_table': 'note',
            'purpose': 'إدارة الملاحظات والمذكرات',
            'keywords': ['ملاحظة', 'مذكرة', 'note']
        }
    }

def build_language_mapping():
    """بناء خريطة الترجمة اللغوية"""
    return {
        'مبيعات': ['sales', 'invoice', 'payment'],
        'دفتر': ['ledger', 'account'],
        'نفقات': ['expense', 'expenses'],
        'ضرائب': ['tax', 'vat'],
        'سعر الدولار': ['exchange', 'usd', 'ils'],
        'عملاء': ['customer', 'client'],
        'موردين': ['supplier', 'vendor'],
        'متجر': ['shop', 'store', 'product'],
        'صيانة': ['service', 'workshop', 'repair'],
        'مخازن': ['warehouse', 'inventory', 'stock'],
        'شركاء': ['partner', 'partnership'],
    }

def build_data_schema():
    """بناء خريطة البيانات الكاملة"""

    models = discover_all_models()

    schema = {
        'generated_at': datetime.now().isoformat(),
        'models_count': len(models),
        'models': {},
        'functional_mapping': build_functional_mapping(),
        'language_mapping': build_language_mapping(),
        'statistics': {
            'total_tables': 0,
            'total_columns': 0,
            'total_relationships': 0,
        }
    }
    
    total_columns = 0
    total_relationships = 0
    
    for model in models:
        analysis = analyze_model_structure(model)
        
        if 'error' not in analysis:
            schema['models'][model.__name__] = analysis
            total_columns += analysis['columns_count']
            total_relationships += analysis['relationships_count']
    
    schema['statistics']['total_tables'] = len(schema['models'])
    schema['statistics']['total_columns'] = total_columns
    schema['statistics']['total_relationships'] = total_relationships
    
    save_data_schema(schema)
    log_learning_event('schema_built', len(models))


    return schema

def save_data_schema(schema):
    """حفظ خريطة البيانات"""
    try:
        os.makedirs('AI/data', exist_ok=True)
        
        with open(DATA_SCHEMA_FILE, 'w', encoding='utf-8') as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)

    except Exception as e:
        pass  # خطأ محتمل

def load_data_schema():
    """تحميل خريطة البيانات"""
    try:
        if os.path.exists(DATA_SCHEMA_FILE):
            with open(DATA_SCHEMA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:

            return None
    
    except Exception as e:
        pass  # خطأ محتمل
        return None

def log_learning_event(event_type, details):
    """تسجيل حدث التعلم"""
    try:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'details': details,
        }
        
        logs = []
        if os.path.exists(LEARNING_LOG_FILE):
            with open(LEARNING_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        logs = logs[-100:]  # آخر 100 حدث
        
        with open(LEARNING_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    except Exception as e:
        pass  # خطأ محتمل

def find_model_by_keyword(keyword):
    """البحث الذكي عن نموذج حسب كلمة مفتاحية - محسّن"""
    schema = load_data_schema()
    
    if not schema or not schema.get('models'):
        return None
    
    keyword_lower = keyword.lower()
    
    # خريطة الكلمات المرادفة
    model_synonyms = {
        'عميل': ['customer', 'client'],
        'مورد': ['supplier', 'vendor', 'partner'],
        'منتج': ['product', 'part'],
        'صيانة': ['service', 'servicerequest'],
        'فاتورة': ['invoice', 'sale'],
        'دفعة': ['payment'],
        'مخزن': ['warehouse', 'stock'],
        'مستخدم': ['user'],
        'دور': ['role'],
        'صلاحية': ['permission'],
        'نفقة': ['expense'],
        'شيك': ['check'],
        'ملاحظة': ['note'],
        'شحنة': ['shipment'],
        'عملة': ['currency', 'exchange'],
    }
    
    # جمع الكلمات للبحث
    search_terms = [keyword_lower]
    for ar_word, en_synonyms in model_synonyms.items():
        if ar_word in keyword_lower:
            search_terms.extend(en_synonyms)
        for syn in en_synonyms:
            if syn in keyword_lower:
                search_terms.append(ar_word)
                break
    
    best_match = None
    highest_score = 0
    
    # البحث المباشر في أسماء النماذج
    for model_name, model_data in schema['models'].items():
        score = 0
        for term in search_terms:
            if term in model_name.lower():
                score += 15
            if term in model_data.get('table_name', '').lower():
                score += 10
            # البحث في أسماء الأعمدة
            for col in model_data.get('columns', []):
                if term in col.get('name', '').lower():
                    score += 2
        
        if score > highest_score:
            highest_score = score
            best_match = {
                'name': model_name,
                'table_name': model_data.get('table_name'),
                'description': f'نموذج {model_name} - يحتوي على {len(model_data.get("columns", []))} حقل',
                'columns': model_data.get('columns', []),
                'relationships': [rel.get('name', '') for rel in model_data.get('relationships', [])],
                'score': score
            }
    
    # البحث في الخريطة الوظيفية
    for module_name, module_data in schema.get('functional_mapping', {}).items():
        if any(k in keyword_lower for k in module_data.get('keywords', [])):
            if not best_match or highest_score < 5:
                best_match = {
                    'module': module_name,
                    'models': module_data.get('models', []),
                    'purpose': module_data.get('purpose', ''),
                    'description': f'وحدة {module_name}'
                }
    
    return {'model': best_match, 'keyword': keyword} if best_match else None

def auto_build_if_needed():
    """بناء الخريطة إذا لزم الأمر"""
    if not os.path.exists(DATA_SCHEMA_FILE):

        return build_data_schema()
    
    # فحص إذا كانت الخريطة قديمة (أكثر من 7 أيام)
    try:
        file_time = os.path.getmtime(DATA_SCHEMA_FILE)
        age_days = (datetime.now().timestamp() - file_time) / (3600 * 24)
        
        if age_days > 7:
            return build_data_schema()
    
    except Exception:
        pass
    
    return load_data_schema()

if __name__ == '__main__':

    schema = build_data_schema()
