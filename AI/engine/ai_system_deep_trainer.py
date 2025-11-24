from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path
import json


class SystemDeepTrainer:
    
    def __init__(self):
        self.data_dir = Path('AI/data/system_deep_training')
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def train_system_comprehensive(self) -> Dict:
        print("[SYSTEM DEEP TRAINING - START]")
        print("=" * 80)
        print("Training on EVERY aspect of the system...")
        
        total_items = 0
        
        total_items += self._train_database_complete()
        total_items += self._train_models_relationships()
        total_items += self._train_every_route()
        total_items += self._train_every_form()
        total_items += self._train_every_template()
        total_items += self._train_business_workflows()
        total_items += self._train_accounting_integration()
        total_items += self._train_gl_system()
        total_items += self._train_inventory_system()
        total_items += self._train_sales_system()
        total_items += self._train_purchase_system()
        total_items += self._train_payment_system()
        total_items += self._train_customer_management()
        total_items += self._train_vehicle_management()
        total_items += self._train_service_maintenance()
        total_items += self._train_reporting_system()
        total_items += self._train_user_permissions()
        total_items += self._train_system_settings()
        total_items += self._train_integrations()
        total_items += self._train_error_handling()
        total_items += self._train_checks_system()
        total_items += self._train_vendors_suppliers()
        total_items += self._train_partners_system()
        total_items += self._train_products_system()
        total_items += self._train_owner_module()
        total_items += self._train_remaining_modules()
        total_items += self._train_sale_returns()
        total_items += self._train_balances_api()
        total_items += self._train_hard_delete()
        total_items += self._train_security_expenses()
        total_items += self._train_other_systems()
        total_items += self._train_user_guide()
        total_items += self._train_barcode_scanner()
        total_items += self._train_ai_modules()
        total_items += self._train_health_module()
        total_items += self._train_archive_modules()
        
        print("=" * 80)
        print(f"[SYSTEM DEEP TRAINING - COMPLETE]")
        print(f"Total items learned: {total_items}")
        
        return {
            'success': True,
            'items_learned': total_items,
            'modules': 36
        }
    
    def _train_database_complete(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        from flask import has_app_context
        
        print("\n[1/36] Complete Database Structure")
        memory = get_deep_memory()
        items = 0
        
        try:
            if not has_app_context():
                print("  Warning: No app context, skipping database scan")
                return 0
                
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            for table in tables:
                columns = inspector.get_columns(table)
                fks = inspector.get_foreign_keys(table)
                pk = inspector.get_pk_constraint(table)
                
                table_info = {
                    'name': table,
                    'columns': [c['name'] for c in columns],
                    'column_count': len(columns),
                    'has_pk': bool(pk and pk.get('constrained_columns')),
                    'fk_count': len(fks)
                }
                
                memory.remember_concept(
                    f'جدول: {table}',
                    f'جدول في قاعدة البيانات يحتوي على {len(columns)} عمود',
                    examples=table_info['columns'][:5],
                    related=['database', 'garage_system']
                )
                items += 1
                
                for col in columns:
                    col_detail = f"{table}.{col['name']}: {col['type']}"
                    memory.remember_fact(
                        'db_column',
                        col_detail,
                        {
                            'table': table,
                            'name': col['name'],
                            'type': str(col['type']),
                            'nullable': col.get('nullable', True)
                        },
                        importance=7
                    )
                    items += 1
                
                for fk in fks:
                    fk_detail = f"{table} → {fk['referred_table']}"
                    memory.remember_fact(
                        'db_relationship',
                        fk_detail,
                        {
                            'from_table': table,
                            'to_table': fk['referred_table'],
                            'columns': fk['constrained_columns']
                        },
                        importance=8
                    )
                    items += 1
            
            print(f"  Tables analyzed: {len(tables)}")
        
        except Exception as e:
            print(f"  Error: {e}")
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_models_relationships(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[2/20] All Models & Relationships")
        memory = get_deep_memory()
        items = 0
        
        try:
            from extensions import db
            
            for mapper in db.Model.registry.mappers:
                model_class = mapper.class_
                model_name = model_class.__name__
                
                relationships = {}
                for rel_name, relationship in mapper.relationships.items():
                    relationships[rel_name] = {
                        'target': relationship.entity.class_.__name__,
                        'direction': relationship.direction.name,
                        'uselist': relationship.uselist
                    }
                
                memory.remember_concept(
                    f'Model: {model_name}',
                    f'نموذج بيانات في النظام',
                    examples=list(relationships.keys()),
                    related=['models', 'database']
                )
                items += 1
                
                for rel_name, rel_info in relationships.items():
                    memory.remember_fact(
                        'model_relationship',
                        f'{model_name}.{rel_name}',
                        rel_info,
                        importance=8
                    )
                    items += 1
            
            print(f"  Models analyzed: {len(list(db.Model.registry.mappers))}")
        
        except Exception as e:
            print(f"  Error: {e}")
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_every_route(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[3/20] Every Route & Endpoint")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app
            
            if not has_app_context():
                print("  Warning: No app context, skipping routes scan")
                return 0
            
            routes_by_module = {}
            
            for rule in current_app.url_map.iter_rules():
                if rule.endpoint != 'static':
                    endpoint_parts = rule.endpoint.split('.')
                    module = endpoint_parts[0] if len(endpoint_parts) > 1 else 'main'
                    
                    if module not in routes_by_module:
                        routes_by_module[module] = []
                    
                    routes_by_module[module].append({
                        'path': str(rule.rule),
                        'endpoint': rule.endpoint,
                        'methods': list(rule.methods - {'HEAD', 'OPTIONS'})
                    })
                    
                    memory.remember_procedure(
                        f'Route: {rule.endpoint}',
                        [
                            f'المسار: {rule.rule}',
                            f'الوحدة: {module}',
                            f'الطرق: {", ".join(rule.methods - {"HEAD", "OPTIONS"})}'
                        ],
                        context={'module': module, 'path': str(rule.rule)}
                    )
                    items += 1
            
            for module, routes in routes_by_module.items():
                memory.remember_concept(
                    f'Module: {module}',
                    f'وحدة في النظام تحتوي على {len(routes)} مسار',
                    examples=[r['path'] for r in routes[:5]],
                    related=['routes', 'system_modules']
                )
                items += 1
            
            print(f"  Routes learned: {sum(len(r) for r in routes_by_module.values())}")
        
        except Exception as e:
            print(f"  Error: {e}")
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_every_form(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[4/20] All Forms & Validations")
        memory = get_deep_memory()
        items = 0
        
        forms_dir = Path('forms')
        if forms_dir.exists():
            for form_file in forms_dir.glob('*.py'):
                if form_file.name != '__init__.py':
                    try:
                        with open(form_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        import re
                        classes = re.findall(r'class\s+(\w+Form)\s*\(', content)
                        
                        for form_class in classes:
                            memory.remember_concept(
                                f'Form: {form_class}',
                                f'نموذج إدخال في ملف {form_file.name}',
                                examples=[],
                                related=['forms', 'validation']
                            )
                            items += 1
                    
                    except Exception:
                        pass
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_every_template(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[5/20] All Templates")
        memory = get_deep_memory()
        items = 0
        
        templates_dir = Path('templates')
        if templates_dir.exists():
            for template_file in templates_dir.rglob('*.html'):
                template_path = str(template_file.relative_to(templates_dir))
                
                memory.remember_fact(
                    'template',
                    template_path,
                    {'path': template_path, 'exists': True},
                    importance=6
                )
                items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_business_workflows(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[6/20] Business Workflows")
        memory = get_deep_memory()
        items = 0
        
        workflows = {
            'عملية البيع الكاملة': [
                '1. إضافة أو اختيار العميل',
                '2. إنشاء فاتورة بيع جديدة',
                '3. إضافة المنتجات والكميات',
                '4. تطبيق الخصم إن وجد',
                '5. حساب VAT تلقائياً (16%)',
                '6. حفظ الفاتورة',
                '7. إنشاء قيد محاسبي تلقائي',
                '8. تحديث رصيد العميل',
                '9. خصم الكميات من المخزون',
                '10. طباعة الفاتورة'
            ],
            'عملية الشراء الكاملة': [
                '1. اختيار المورد',
                '2. إنشاء أمر شراء',
                '3. تحديد المنتجات والكميات',
                '4. تحديد السعر',
                '5. حساب VAT',
                '6. حفظ أمر الشراء',
                '7. إنشاء قيد محاسبي',
                '8. تحديث رصيد المورد',
                '9. إضافة الكميات للمخزون',
                '10. استلام البضاعة'
            ],
            'عملية تسجيل دفعة': [
                '1. اختيار العميل أو المورد',
                '2. تحديد نوع الدفعة (IN/OUT)',
                '3. إدخال المبلغ',
                '4. اختيار طريقة الدفع',
                '5. إضافة ملاحظات',
                '6. حفظ الدفعة',
                '7. إنشاء قيد محاسبي',
                '8. تحديث الرصيد فوراً',
                '9. طباعة السند'
            ],
            'عملية الصيانة': [
                '1. استقبال السيارة',
                '2. تسجيل بيانات السيارة',
                '3. فحص أولي',
                '4. تحديد الأعطال والخدمات',
                '5. إعداد تقدير التكلفة',
                '6. موافقة العميل',
                '7. بدء العمل',
                '8. طلب قطع الغيار',
                '9. إتمام الصيانة',
                '10. الفحص النهائي',
                '11. إصدار فاتورة',
                '12. تسليم السيارة'
            ]
        }
        
        for workflow_name, steps in workflows.items():
            memory.remember_procedure(
                workflow_name,
                steps,
                context={'category': 'business_workflow', 'critical': True}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_accounting_integration(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[7/20] Accounting Integration")
        memory = get_deep_memory()
        items = 0
        
        accounting_flows = {
            'بيع → قيد': 'عند حفظ بيع: مدين ذمم العملاء، دائن المبيعات + VAT',
            'شراء → قيد': 'عند حفظ شراء: مدين المشتريات + VAT، دائن ذمم الموردين',
            'دفعة من عميل → قيد': 'مدين الصندوق/البنك، دائن ذمم العملاء',
            'دفعة لمورد → قيد': 'مدين ذمم الموردين، دائن الصندوق/البنك',
            'مصروف → قيد': 'مدين حساب المصروف، دائن الصندوق/البنك',
            'خدمة → قيد': 'مدين ذمم العملاء، دائن الخدمات + VAT'
        }
        
        for flow, description in accounting_flows.items():
            memory.remember_procedure(
                f'تكامل محاسبي: {flow}',
                [description, 'تلقائي', 'فوري'],
                context={'accounting_integration': True}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_gl_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[8/20] General Ledger System")
        memory = get_deep_memory()
        items = 0
        
        gl_concepts = {
            'دليل الحسابات': 'شجرة منظمة لكل الحسابات',
            'القيد المحاسبي': 'تسجيل المعاملة المالية',
            'دفتر اليومية': 'تسجيل زمني للقيود',
            'دفتر الأستاذ': 'تجميع حسب الحساب',
            'ميزان المراجعة': 'قائمة الأرصدة',
            'الميزانية': 'الأصول = الخصوم + الملكية',
            'قائمة الدخل': 'الإيرادات - المصروفات'
        }
        
        for concept, definition in gl_concepts.items():
            memory.remember_concept(
                concept,
                definition,
                examples=[],
                related=['GL', 'accounting']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_inventory_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[9/20] Inventory Management System")
        memory = get_deep_memory()
        items = 0
        
        inventory_operations = {
            'إضافة منتج': 'تسجيل منتج جديد في النظام',
            'استقبال بضاعة': 'زيادة المخزون بعد الشراء',
            'بيع منتج': 'تخفيض المخزون',
            'تحويل بين مخازن': 'نقل الكمية من مخزن لآخر',
            'تسوية مخزون': 'تصحيح الفرق بين الفعلي والدفتري',
            'جرد المخزون': 'العد الفعلي',
            'إعادة طلب': 'عند وصول الحد الأدنى'
        }
        
        for operation, description in inventory_operations.items():
            memory.remember_procedure(
                f'مخزون: {operation}',
                [description],
                context={'inventory': True}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_sales_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[10/20] Sales System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            sales_routes = []
            for rule in app.url_map.iter_rules():
                if 'sales' in rule.endpoint.lower() or '/sales' in rule.rule:
                    sales_routes.append({
                        'path': rule.rule,
                        'endpoint': rule.endpoint,
                        'methods': list(rule.methods - {'HEAD', 'OPTIONS'})
                    })
                    
                    memory.remember_procedure(
                        f'Sales Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}', f'الطرق: {", ".join(rule.methods - {"HEAD", "OPTIONS"})}'],
                        context={'module': 'sales', 'category': 'sales_operations'}
                    )
                    items += 1
            
            sales_file = Path('routes/sales.py')
            if sales_file.exists():
                with open(sales_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('sales_function', func, {'file': 'routes/sales.py'}, importance=7)
                        items += 1
            
            from models import Sale, SaleLine, Invoice
            from extensions import db
            
            sale_columns = [col.name for col in Sale.__table__.columns]
            memory.remember_concept('Sale Model', 'نموذج البيع', examples=sale_columns[:10], related=['sales', 'invoice'])
            items += 1
            
            print(f"  Routes analyzed: {len(sales_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_purchase_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[11/20] Purchase System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            
            vendors_routes = []
            for rule in app.url_map.iter_rules():
                if 'vendor' in rule.endpoint.lower() or '/vendors' in rule.rule or 'purchase' in rule.endpoint.lower():
                    vendors_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Purchase Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'purchases', 'category': 'purchase_operations'}
                    )
                    items += 1
            
            vendors_file = Path('routes/vendors.py')
            if vendors_file.exists():
                import re
                with open(vendors_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('purchase_function', func, {'file': 'routes/vendors.py'}, importance=7)
                        items += 1
            
            print(f"  Routes analyzed: {len(vendors_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_payment_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[12/20] Payment System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            payment_routes = []
            for rule in app.url_map.iter_rules():
                if 'payment' in rule.endpoint.lower() or '/payments' in rule.rule:
                    payment_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Payment Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'payments', 'category': 'payment_operations'}
                    )
                    items += 1
            
            payment_file = Path('routes/payments.py')
            if payment_file.exists():
                with open(payment_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('payment_function', func, {'file': 'routes/payments.py'}, importance=8)
                        items += 1
            
            from models import Payment
            payment_types = ['IN', 'OUT']
            memory.remember_concept('Payment Types', 'أنواع الدفعات', examples=payment_types, related=['payments', 'accounting'])
            items += 1
            
            print(f"  Routes analyzed: {len(payment_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_customer_management(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[13/20] Customer Management - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            customer_routes = []
            for rule in app.url_map.iter_rules():
                if 'customer' in rule.endpoint.lower() or '/customers' in rule.rule:
                    customer_routes.append(rule.rule)
                    items += 1
            
            customers_file = Path('routes/customers.py')
            if customers_file.exists():
                with open(customers_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_procedure(
                            f'Customer Function: {func}',
                            [f'في ملف customers.py'],
                            context={'module': 'customers'}
                        )
                        items += 1
            
            from models import Customer
            customer_columns = [col.name for col in Customer.__table__.columns]
            memory.remember_concept('Customer Model', 'نموذج العميل', examples=customer_columns[:10], related=['customers', 'CRM'])
            items += 1
            
            print(f"  Routes analyzed: {len(customer_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_vehicle_management(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[14/20] Vehicle Management - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            vehicle_tables = [t for t in inspector.get_table_names() if 'vehicle' in t.lower() or 'car' in t.lower()]
            
            for table in vehicle_tables:
                columns = inspector.get_columns(table)
                memory.remember_concept(
                    f'Vehicle Table: {table}',
                    f'جدول المركبات - {len(columns)} عمود',
                    examples=[c['name'] for c in columns[:5]],
                    related=['vehicles', 'service']
                )
                items += 1
            
            service_file = Path('routes/service.py')
            if service_file.exists():
                import re
                with open(service_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                vehicle_functions = re.findall(r'def\s+(\w+.*?vehicle.*?)\(', content, re.I)
                for func in vehicle_functions:
                    memory.remember_fact('vehicle_function', func, {'file': 'routes/service.py'}, importance=7)
                    items += 1
            
            print(f"  Tables analyzed: {len(vehicle_tables)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_service_maintenance(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[15/20] Service & Maintenance Module - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            service_routes = []
            for rule in app.url_map.iter_rules():
                if 'service' in rule.endpoint.lower() or '/service' in rule.rule:
                    service_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Service Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'service', 'category': 'maintenance'}
                    )
                    items += 1
            
            service_file = Path('routes/service.py')
            if service_file.exists():
                with open(service_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('service_function', func, {'file': 'routes/service.py'}, importance=8)
                        items += 1
            
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            service_tables = [t for t in inspector.get_table_names() if 'service' in t.lower() or 'request' in t.lower()]
            
            for table in service_tables:
                memory.remember_concept(f'Service Table: {table}', f'جدول الخدمات', examples=[], related=['service', 'maintenance'])
                items += 1
            
            print(f"  Routes analyzed: {len(service_routes)}")
            print(f"  Tables analyzed: {len(service_tables)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_reporting_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[16/20] Reporting System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            
            report_routes = []
            for rule in app.url_map.iter_rules():
                if 'report' in rule.endpoint.lower() or '/report' in rule.rule:
                    report_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Report Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'reports', 'category': 'reporting'}
                    )
                    items += 1
            
            report_files = [
                Path('routes/report_routes.py'),
                Path('routes/admin_reports.py'),
                Path('routes/financial_reports.py')
            ]
            
            for report_file in report_files:
                if report_file.exists():
                    import re
                    with open(report_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_fact('report_function', func, {'file': str(report_file)}, importance=8)
                            items += 1
            
            print(f"  Routes analyzed: {len(report_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_user_permissions(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[17/20] User & Permissions - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            auth_routes = []
            for rule in app.url_map.iter_rules():
                if 'auth' in rule.endpoint.lower() or 'user' in rule.endpoint.lower() or 'permission' in rule.endpoint.lower() or 'role' in rule.endpoint.lower():
                    auth_routes.append(rule.rule)
                    items += 1
            
            auth_files = [
                Path('routes/auth.py'),
                Path('routes/users.py'),
                Path('routes/permissions.py'),
                Path('routes/roles.py')
            ]
            
            for auth_file in auth_files:
                if auth_file.exists():
                    with open(auth_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'Auth Function: {func}',
                                [f'في ملف {auth_file.name}'],
                                context={'module': 'auth', 'category': 'security'}
                            )
                            items += 1
            
            from models import User, Role, Permission
            memory.remember_concept('User Model', 'نموذج المستخدم', examples=['username', 'email', 'role_id'], related=['users', 'auth'])
            items += 1
            
            print(f"  Routes analyzed: {len(auth_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_system_settings(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[18/20] System Settings - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from extensions import db
            from models import SystemSettings
            
            settings = SystemSettings.query.all()
            for setting in settings[:50]:
                memory.remember_fact(
                    'system_setting',
                    f'{setting.key} = {setting.value}',
                    {'key': setting.key, 'value': setting.value, 'type': setting.type},
                    importance=7
                )
                items += 1
            
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            for rule in app.url_map.iter_rules():
                if 'setting' in rule.endpoint.lower() or 'config' in rule.endpoint.lower():
                    memory.remember_procedure(
                        f'Setting Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'settings'}
                    )
                    items += 1
            
            print(f"  Settings analyzed: {len(settings)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_integrations(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[19/20] System Integrations - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            
            api_routes = []
            for rule in app.url_map.iter_rules():
                if '/api' in rule.rule:
                    api_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'API Endpoint: {rule.endpoint}',
                        [f'المسار: {rule.rule}', f'الطرق: {", ".join(rule.methods - {"HEAD", "OPTIONS"})}'],
                        context={'module': 'api', 'category': 'integration'}
                    )
                    items += 1
            
            api_file = Path('routes/api.py')
            if api_file.exists():
                import re
                with open(api_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                api_functions = re.findall(r'@.*?route.*?\ndef\s+(\w+)\(', content, re.DOTALL)
                for func in api_functions:
                    memory.remember_fact('api_endpoint', func, {'file': 'routes/api.py'}, importance=7)
                    items += 1
            
            print(f"  API routes analyzed: {len(api_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_error_handling(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[20/20] Error Handling & Validation - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from extensions import db
            from models import AuditLog
            
            error_logs = AuditLog.query.filter(AuditLog.action.like('%ERROR%') | AuditLog.action.like('%error%')).limit(100).all()
            
            error_patterns = {}
            for log in error_logs:
                if log.details:
                    error_type = log.action.split('_')[0] if '_' in log.action else 'GENERAL'
                    if error_type not in error_patterns:
                        error_patterns[error_type] = []
                    error_patterns[error_type].append(log.details[:100])
            
            for error_type, patterns in error_patterns.items():
                memory.remember_procedure(
                    f'Error Pattern: {error_type}',
                    patterns[:5],
                    context={'category': 'error_handling', 'severity': 'warning'}
                )
                items += 1
            
            import re
            utils_file = Path('utils/__init__.py')
            if utils_file.exists():
                with open(utils_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                validation_functions = re.findall(r'def\s+(validate_\w+)\(', content)
                for func in validation_functions:
                    memory.remember_fact('validation_function', func, {'file': 'utils/__init__.py'}, importance=8)
                    items += 1
            
            print(f"  Error patterns analyzed: {len(error_patterns)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_checks_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[21/26] Checks System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            checks_routes = []
            for rule in app.url_map.iter_rules():
                if 'check' in rule.endpoint.lower() or '/checks' in rule.rule:
                    checks_routes.append({
                        'path': rule.rule,
                        'endpoint': rule.endpoint,
                        'methods': list(rule.methods - {'HEAD', 'OPTIONS'})
                    })
                    
                    memory.remember_procedure(
                        f'Check Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}', f'الطرق: {", ".join(rule.methods - {"HEAD", "OPTIONS"})}'],
                        context={'module': 'checks', 'category': 'financial_operations'}
                    )
                    items += 1
            
            checks_file = Path('routes/checks.py')
            if checks_file.exists():
                with open(checks_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('check_function', func, {'file': 'routes/checks.py'}, importance=9)
                        items += 1
                
                check_statuses = re.findall(r"['\"](PENDING|CASHED|RETURNED|BOUNCED|RESUBMITTED|CANCELLED|ARCHIVED|OVERDUE)['\"]", content)
                for status in set(check_statuses):
                    memory.remember_concept(f'Check Status: {status}', f'حالة الشيك: {status}', examples=[], related=['checks', 'status'])
                    items += 1
            
            from models import Check, CheckStatus
            from extensions import db
            
            check_columns = [col.name for col in Check.__table__.columns]
            memory.remember_concept('Check Model', 'نموذج الشيك', examples=check_columns[:15], related=['checks', 'payments', 'financial'])
            items += 1
            
            check_lifecycle = {
                'PENDING': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
                'RETURNED': ['RESUBMITTED', 'CANCELLED'],
                'BOUNCED': ['RESUBMITTED', 'CANCELLED'],
                'RESUBMITTED': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
                'OVERDUE': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
                'CASHED': [],
                'CANCELLED': ['RETURNED', 'PENDING', 'RESUBMITTED']
            }
            
            for status, transitions in check_lifecycle.items():
                memory.remember_procedure(
                    f'Check Lifecycle: {status}',
                    [f'يمكن التحويل إلى: {", ".join(transitions)}'] if transitions else ['حالة نهائية'],
                    context={'category': 'check_lifecycle', 'status': status}
                )
                items += 1
            
            print(f"  Routes analyzed: {len(checks_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_vendors_suppliers(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[22/26] Vendors & Suppliers System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            vendor_routes = []
            for rule in app.url_map.iter_rules():
                if 'vendor' in rule.endpoint.lower() or 'supplier' in rule.endpoint.lower() or '/vendors' in rule.rule:
                    vendor_routes.append(rule.rule)
                    items += 1
            
            vendors_file = Path('routes/vendors.py')
            if vendors_file.exists():
                with open(vendors_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_procedure(
                            f'Vendor Function: {func}',
                            [f'في ملف vendors.py'],
                            context={'module': 'vendors', 'category': 'supplier_management'}
                        )
                        items += 1
            
            from models import Supplier, SupplierSettlement, SupplierSettlementLine
            from extensions import db
            
            supplier_columns = [col.name for col in Supplier.__table__.columns]
            memory.remember_concept('Supplier Model', 'نموذج المورد', examples=supplier_columns[:10], related=['suppliers', 'vendors', 'purchases'])
            items += 1
            
            settlement_columns = [col.name for col in SupplierSettlement.__table__.columns]
            memory.remember_concept('Supplier Settlement', 'تسوية المورد', examples=settlement_columns[:8], related=['suppliers', 'accounting'])
            items += 1
            
            supplier_settlement_file = Path('routes/supplier_settlements.py')
            if supplier_settlement_file.exists():
                with open(supplier_settlement_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('supplier_settlement_function', func, {'file': 'routes/supplier_settlements.py'}, importance=8)
                        items += 1
            
            print(f"  Routes analyzed: {len(vendor_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_partners_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[23/26] Partners System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            partner_routes = []
            for rule in app.url_map.iter_rules():
                if 'partner' in rule.endpoint.lower() or '/partners' in rule.rule:
                    partner_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Partner Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'partners', 'category': 'partner_management'}
                    )
                    items += 1
            
            partner_files = [
                Path('routes/partner_settlements.py'),
                Path('utils/partner_balance_calculator.py'),
                Path('utils/partner_balance_updater.py')
            ]
            
            for partner_file in partner_files:
                if partner_file.exists():
                    with open(partner_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_fact('partner_function', func, {'file': str(partner_file)}, importance=8)
                            items += 1
            
            from models import Partner, PartnerSettlement, PartnerSettlementLine, WarehousePartnerShare, ProductPartner
            from extensions import db
            
            partner_columns = [col.name for col in Partner.__table__.columns]
            memory.remember_concept('Partner Model', 'نموذج الشريك', examples=partner_columns[:10], related=['partners', 'shares', 'settlements'])
            items += 1
            
            settlement_columns = [col.name for col in PartnerSettlement.__table__.columns]
            memory.remember_concept('Partner Settlement', 'تسوية الشريك', examples=settlement_columns[:8], related=['partners', 'accounting'])
            items += 1
            
            share_columns = [col.name for col in WarehousePartnerShare.__table__.columns]
            memory.remember_concept('Partner Share', 'حصة الشريك', examples=share_columns, related=['partners', 'warehouses', 'products'])
            items += 1
            
            print(f"  Routes analyzed: {len(partner_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_products_system(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[24/26] Products System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            product_routes = []
            for rule in app.url_map.iter_rules():
                if 'product' in rule.endpoint.lower() or '/products' in rule.rule or '/parts' in rule.rule:
                    product_routes.append(rule.rule)
                    items += 1
            
            product_files = [
                Path('routes/parts.py'),
                Path('routes/shop.py')
            ]
            
            for product_file in product_files:
                if product_file.exists():
                    with open(product_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'Product Function: {func}',
                                [f'في ملف {product_file.name}'],
                                context={'module': 'products', 'category': 'product_management'}
                            )
                            items += 1
            
            from models import Product, ProductCategory, ProductRating, ProductSupplierLoan
            from extensions import db
            
            product_columns = [col.name for col in Product.__table__.columns]
            memory.remember_concept('Product Model', 'نموذج المنتج', examples=product_columns[:15], related=['products', 'inventory', 'sales'])
            items += 1
            
            category_columns = [col.name for col in ProductCategory.__table__.columns]
            memory.remember_concept('Product Category', 'فئة المنتج', examples=category_columns, related=['products', 'categories'])
            items += 1
            
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            product_tables = [t for t in inspector.get_table_names() if 'product' in t.lower()]
            
            for table in product_tables:
                columns = inspector.get_columns(table)
                memory.remember_concept(
                    f'Product Table: {table}',
                    f'جدول المنتجات - {len(columns)} عمود',
                    examples=[c['name'] for c in columns[:5]],
                    related=['products']
                )
                items += 1
            
            print(f"  Routes analyzed: {len(product_routes)}")
            print(f"  Tables analyzed: {len(product_tables)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_owner_module(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[25/26] Owner Module - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            owner_routes = []
            for rule in app.url_map.iter_rules():
                if 'owner' in rule.endpoint.lower() or 'advanced' in rule.endpoint.lower() or 'security' in rule.endpoint.lower() and 'control' in rule.endpoint.lower():
                    owner_routes.append({
                        'path': rule.rule,
                        'endpoint': rule.endpoint
                    })
                    
                    memory.remember_procedure(
                        f'Owner Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}', 'مخصص للمالك فقط'],
                        context={'module': 'owner', 'category': 'owner_only', 'security': 'high'}
                    )
                    items += 1
            
            owner_files = [
                Path('routes/advanced_control.py'),
                Path('routes/security_control.py'),
                Path('routes/security.py')
            ]
            
            for owner_file in owner_files:
                if owner_file.exists():
                    with open(owner_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    owner_only_decorators = len(re.findall(r'@owner_only', content))
                    memory.remember_fact('owner_function_count', str(owner_file.name), {'count': owner_only_decorators}, importance=9)
                    items += 1
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'Owner Function: {func}',
                                [f'في ملف {owner_file.name}'],
                                context={'module': 'owner', 'security': 'high'}
                            )
                            items += 1
            
            owner_decorator_pattern = r'def\s+owner_only\('
            memory.remember_concept('Owner Only Decorator', 'ديكوراتور للمالك فقط', examples=['@owner_only'], related=['security', 'owner', 'permissions'])
            items += 1
            
            print(f"  Routes analyzed: {len(owner_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_remaining_modules(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[26/26] Remaining Modules - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            remaining_modules = {
                'warehouses': Path('routes/warehouses.py'),
                'branches': Path('routes/branches.py'),
                'expenses': Path('routes/expenses.py'),
                'shipments': Path('routes/shipments.py'),
                'ledger': Path('routes/ledger_blueprint.py'),
                'ledger_control': Path('routes/ledger_control.py'),
                'financial_reports': Path('routes/financial_reports.py'),
                'accounting_docs': Path('routes/accounting_docs.py'),
                'accounting_validation': Path('routes/accounting_validation.py'),
                'currencies': Path('routes/currencies.py'),
                'bank': Path('routes/bank.py'),
                'notes': Path('routes/notes.py'),
                'workflows': Path('routes/workflows.py'),
                'projects': Path('routes/projects.py'),
                'assets': Path('routes/assets.py'),
                'budgets': Path('routes/budgets.py'),
                'cost_centers': Path('routes/cost_centers.py'),
                'recurring_invoices': Path('routes/recurring_invoices.py'),
                'pricing': Path('routes/pricing.py'),
                'engineering': Path('routes/engineering.py'),
                'barcode': Path('routes/barcode.py'),
                'archive': Path('routes/archive.py')
            }
            
            for module_name, module_file in remaining_modules.items():
                if module_file.exists():
                    with open(module_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'{module_name.title()} Function: {func}',
                                [f'في ملف {module_file.name}'],
                                context={'module': module_name}
                            )
                            items += 1
                    
                    routes_count = len(re.findall(r'@.*?\.route\(', content))
                    memory.remember_concept(
                        f'Module: {module_name}',
                        f'وحدة {module_name} - {routes_count} route',
                        examples=[f for f in functions[:5] if not f.startswith('_')],
                        related=[module_name, 'system_modules']
                    )
                    items += 1
            
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            all_tables = inspector.get_table_names()
            
            trained_tables = set()
            for module_name in remaining_modules.keys():
                for table in all_tables:
                    if module_name[:-1] in table.lower() or module_name in table.lower():
                        if table not in trained_tables:
                            columns = inspector.get_columns(table)
                            memory.remember_concept(
                                f'Table: {table}',
                                f'جدول {table} - {len(columns)} عمود',
                                examples=[c['name'] for c in columns[:5]],
                                related=[module_name, 'database']
                            )
                            trained_tables.add(table)
                            items += 1
            
            print(f"  Modules analyzed: {len(remaining_modules)}")
            print(f"  Tables analyzed: {len(trained_tables)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_sale_returns(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[27/36] Sale Returns System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            returns_routes = []
            for rule in app.url_map.iter_rules():
                if 'return' in rule.endpoint.lower() or '/returns' in rule.rule:
                    returns_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Return Route: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'sale_returns', 'category': 'sales_operations'}
                    )
                    items += 1
            
            returns_file = Path('routes/sale_returns.py')
            if returns_file.exists():
                with open(returns_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('return_function', func, {'file': 'routes/sale_returns.py'}, importance=8)
                        items += 1
            
            from models import SaleReturn, SaleReturnLine
            return_columns = [col.name for col in SaleReturn.__table__.columns]
            memory.remember_concept('SaleReturn Model', 'نموذج مرتجع البيع', examples=return_columns[:10], related=['sales', 'returns', 'inventory'])
            items += 1
            
            print(f"  Routes analyzed: {len(returns_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_balances_api(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[28/36] Balances API - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            balances_routes = []
            for rule in app.url_map.iter_rules():
                if 'balance' in rule.endpoint.lower() or '/balances' in rule.rule:
                    balances_routes.append(rule.rule)
                    items += 1
            
            balances_file = Path('routes/balances_api.py')
            if balances_file.exists():
                with open(balances_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('balance_api_function', func, {'file': 'routes/balances_api.py'}, importance=8)
                        items += 1
            
            print(f"  Routes analyzed: {len(balances_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_hard_delete(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[29/36] Hard Delete System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            hard_delete_routes = []
            for rule in app.url_map.iter_rules():
                if 'hard_delete' in rule.endpoint.lower() or 'hard-delete' in rule.rule:
                    hard_delete_routes.append(rule.rule)
                    items += 1
            
            hard_delete_file = Path('routes/hard_delete.py')
            if hard_delete_file.exists():
                with open(hard_delete_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_procedure(
                            f'Hard Delete: {func}',
                            [f'حذف دائم في {hard_delete_file.name}'],
                            context={'module': 'hard_delete', 'category': 'dangerous_operation', 'security': 'high'}
                        )
                        items += 1
            
            hard_delete_service = Path('services/hard_delete_service.py')
            if hard_delete_service.exists():
                with open(hard_delete_service, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                classes = re.findall(r'class\s+(\w+)', content)
                for cls in classes:
                    memory.remember_concept(f'Hard Delete Service: {cls}', f'خدمة الحذف الدائم', examples=[], related=['hard_delete', 'security'])
                    items += 1
            
            print(f"  Routes analyzed: {len(hard_delete_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_security_expenses(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[30/36] Security Expenses - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            security_expenses_routes = []
            for rule in app.url_map.iter_rules():
                if 'security_expenses' in rule.endpoint.lower() or 'security-expenses' in rule.rule:
                    security_expenses_routes.append(rule.rule)
                    items += 1
            
            security_expenses_file = Path('routes/security_expenses.py')
            if security_expenses_file.exists():
                with open(security_expenses_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('security_expense_function', func, {'file': 'routes/security_expenses.py'}, importance=7)
                        items += 1
            
            print(f"  Routes analyzed: {len(security_expenses_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_other_systems(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[31/36] Other Systems - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            other_systems_routes = []
            for rule in app.url_map.iter_rules():
                if 'other_systems' in rule.endpoint.lower() or 'other-systems' in rule.rule:
                    other_systems_routes.append(rule.rule)
                    items += 1
            
            other_systems_file = Path('routes/other_systems.py')
            if other_systems_file.exists():
                with open(other_systems_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('other_system_function', func, {'file': 'routes/other_systems.py'}, importance=6)
                        items += 1
            
            print(f"  Routes analyzed: {len(other_systems_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_user_guide(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[32/36] User Guide System - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            user_guide_routes = []
            for rule in app.url_map.iter_rules():
                if 'user_guide' in rule.endpoint.lower() or 'user-guide' in rule.rule or 'guide' in rule.endpoint.lower():
                    user_guide_routes.append(rule.rule)
                    items += 1
            
            user_guide_file = Path('routes/user_guide.py')
            if user_guide_file.exists():
                with open(user_guide_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_procedure(
                            f'User Guide: {func}',
                            [f'دليل المستخدم في {user_guide_file.name}'],
                            context={'module': 'user_guide', 'category': 'documentation'}
                        )
                        items += 1
            
            print(f"  Routes analyzed: {len(user_guide_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_barcode_scanner(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[33/36] Barcode Scanner - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            barcode_routes = []
            for rule in app.url_map.iter_rules():
                if 'barcode' in rule.endpoint.lower() or '/barcode' in rule.rule:
                    barcode_routes.append(rule.rule)
                    items += 1
            
            barcode_files = [
                Path('routes/barcode.py'),
                Path('routes/barcode_scanner.py')
            ]
            
            for barcode_file in barcode_files:
                if barcode_file.exists():
                    with open(barcode_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_fact('barcode_function', func, {'file': str(barcode_file)}, importance=7)
                            items += 1
            
            print(f"  Routes analyzed: {len(barcode_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_ai_modules(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[34/36] AI Modules - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            ai_routes = []
            for rule in app.url_map.iter_rules():
                if 'ai' in rule.endpoint.lower() or '/ai' in rule.rule:
                    ai_routes.append(rule.rule)
                    items += 1
            
            ai_files = [
                Path('routes/ai_routes.py'),
                Path('routes/ai_admin.py')
            ]
            
            for ai_file in ai_files:
                if ai_file.exists():
                    with open(ai_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'AI Function: {func}',
                                [f'في ملف {ai_file.name}'],
                                context={'module': 'ai', 'category': 'ai_operations'}
                            )
                            items += 1
            
            ai_engine_dir = Path('AI/engine')
            if ai_engine_dir.exists():
                ai_engine_files = list(ai_engine_dir.glob('*.py'))
                for ai_file in ai_engine_files:
                    if ai_file.name != '__init__.py':
                        memory.remember_concept(f'AI Engine: {ai_file.stem}', f'محرك AI في {ai_file.name}', examples=[], related=['ai', 'engine'])
                        items += 1
            
            print(f"  Routes analyzed: {len(ai_routes)}")
            print(f"  Engine files: {len(ai_engine_files) if ai_engine_dir.exists() else 0}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_health_module(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[35/36] Health Module - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            health_routes = []
            for rule in app.url_map.iter_rules():
                if 'health' in rule.endpoint.lower() or '/health' in rule.rule:
                    health_routes.append(rule.rule)
                    
                    memory.remember_procedure(
                        f'Health Check: {rule.endpoint}',
                        [f'المسار: {rule.rule}'],
                        context={'module': 'health', 'category': 'monitoring'}
                    )
                    items += 1
            
            health_file = Path('routes/health.py')
            if health_file.exists():
                with open(health_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                functions = re.findall(r'def\s+(\w+)\(', content)
                for func in functions:
                    if not func.startswith('_'):
                        memory.remember_fact('health_function', func, {'file': 'routes/health.py'}, importance=7)
                        items += 1
            
            print(f"  Routes analyzed: {len(health_routes)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items
    
    def _train_archive_modules(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[36/36] Archive Modules - Complete Analysis")
        memory = get_deep_memory()
        items = 0
        
        try:
            from flask import has_app_context, current_app as app
            if not has_app_context():
                print("  Warning: No app context")
                return 0
            import re
            
            archive_routes = []
            for rule in app.url_map.iter_rules():
                if 'archive' in rule.endpoint.lower() or '/archive' in rule.rule:
                    archive_routes.append(rule.rule)
                    items += 1
            
            archive_files = [
                Path('routes/archive.py'),
                Path('routes/archive_routes.py')
            ]
            
            for archive_file in archive_files:
                if archive_file.exists():
                    with open(archive_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    functions = re.findall(r'def\s+(\w+)\(', content)
                    for func in functions:
                        if not func.startswith('_'):
                            memory.remember_procedure(
                                f'Archive Function: {func}',
                                [f'في ملف {archive_file.name}'],
                                context={'module': 'archive', 'category': 'data_management'}
                            )
                            items += 1
            
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            archive_tables = [t for t in inspector.get_table_names() if 'archive' in t.lower()]
            
            for table in archive_tables:
                memory.remember_concept(f'Archive Table: {table}', f'جدول الأرشيف', examples=[], related=['archive', 'data_management'])
                items += 1
            
            print(f"  Routes analyzed: {len(archive_routes)}")
            print(f"  Tables analyzed: {len(archive_tables)}")
            print(f"  Learned: {items} items")
        except Exception as e:
            print(f"  Error: {e}")
        
        return items


_system_deep_trainer = None

def get_system_deep_trainer():
    global _system_deep_trainer
    if _system_deep_trainer is None:
        _system_deep_trainer = SystemDeepTrainer()
    return _system_deep_trainer


__all__ = ['SystemDeepTrainer', 'get_system_deep_trainer']

