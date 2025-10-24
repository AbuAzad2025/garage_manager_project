#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص عميق ودقيق للنظام قبل التطوير
"""

import os
import re
from collections import defaultdict
import json

class DeepSystemAnalyzer:
    def __init__(self):
        self.models = {}
        self.routes = defaultdict(list)
        self.templates = []
        self.forms = {}
        self.database_usage = defaultdict(list)
        self.warnings = []
        self.safe_to_implement = []
        self.not_safe = []
        
    def analyze_models_in_detail(self):
        """فحص دقيق جداً لكل Model"""
        print("=" * 80)
        print("1️⃣  فحص Models بالتفصيل الدقيق")
        print("=" * 80 + "\n")
        
        if not os.path.exists('models.py'):
            return
        
        with open('models.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # استخراج كل Models
        model_pattern = r'class\s+(\w+)\s*\([^)]*db\.Model[^)]*\):'
        models = re.findall(model_pattern, content)
        
        print(f"إجمالي Models: {len(models)}\n")
        
        for model in models:
            # استخراج تفاصيل Model
            model_section = self._extract_model_section(content, model)
            
            # فحص الحقول
            fields = re.findall(r'(\w+)\s*=\s*db\.(Column|relationship)', model_section)
            
            # فحص relationships
            relationships = re.findall(r'db\.relationship\(["\'](\w+)["\']', model_section)
            
            # فحص foreign keys
            foreign_keys = re.findall(r'db\.ForeignKey\(["\']([^"\']+)["\']', model_section)
            
            self.models[model] = {
                'fields': len(fields),
                'relationships': relationships,
                'foreign_keys': foreign_keys,
                'defined': True
            }
        
        # فحص استخدام Models
        self._check_model_usage()
        
        return models
    
    def _extract_model_section(self, content, model_name):
        """استخراج قسم Model من الكود"""
        pattern = rf'class {model_name}\(.*?\):(.*?)(?=class\s|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else ""
    
    def _check_model_usage(self):
        """فحص استخدام كل Model في النظام"""
        print("فحص استخدام Models في Routes...\n")
        
        routes_dir = 'routes'
        if not os.path.exists(routes_dir):
            return
        
        for model_name in self.models.keys():
            used_in = []
            
            for file in os.listdir(routes_dir):
                if not file.endswith('.py'):
                    continue
                
                filepath = os.path.join(routes_dir, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # فحص استخدام Model
                    if f'{model_name}.query' in content or f'from models import.*{model_name}' in content:
                        used_in.append(file)
                except:
                    pass
            
            self.database_usage[model_name] = used_in
    
    def analyze_wip_models(self):
        """تحليل Models قيد التطوير"""
        print("\n" + "=" * 80)
        print("2️⃣  تحليل Models قيد التطوير")
        print("=" * 80 + "\n")
        
        wip_models = [
            'CustomerLoyalty', 'CustomerLoyaltyPoints',
            'SaleReturn', 'SaleReturnLine',
            'GLBatch', 'GLEntry',
            'SupplierSettlement', 'SupplierSettlementLine',
            'PartnerSettlement', 'PartnerSettlementLine',
            'ProductRating', 'ProductRatingHelpful',
            'ProductSupplierLoan', 'StockAdjustmentItem',
            'ShipmentPartner', 'OnlinePreOrderItem',
            'ServiceTask', 'InvoiceLine', 'AuthAudit'
        ]
        
        for model in wip_models:
            if model in self.models:
                usage = self.database_usage.get(model, [])
                
                print(f"📦 {model}:")
                print(f"   Defined: ✅ Yes")
                print(f"   Fields: {self.models[model]['fields']}")
                print(f"   Relationships: {len(self.models[model]['relationships'])}")
                print(f"   Foreign Keys: {len(self.models[model]['foreign_keys'])}")
                print(f"   Used in routes: {len(usage)} files")
                
                if usage:
                    print(f"   Files: {', '.join(usage[:3])}")
                
                # تحديد إذا كان آمن للتطوير
                if len(usage) == 0:
                    print(f"   ⚠️  غير مستخدم - يمكن تطويره بأمان")
                    self.safe_to_implement.append({
                        'model': model,
                        'type': 'model',
                        'reason': 'غير مستخدم حالياً'
                    })
                elif len(usage) > 0:
                    print(f"   ❌ مستخدم - يحتاج حذر شديد")
                    self.not_safe.append({
                        'model': model,
                        'type': 'model',
                        'reason': f'مستخدم في {len(usage)} ملف'
                    })
                
                print()
            else:
                print(f"❌ {model}: غير موجود في models.py")
                self.safe_to_implement.append({
                    'model': model,
                    'type': 'model',
                    'reason': 'غير موجود - يمكن إنشاؤه'
                })
                print()
    
    def check_routes_for_features(self):
        """فحص Routes للميزات قيد التطوير"""
        print("\n" + "=" * 80)
        print("3️⃣  فحص Routes للميزات قيد التطوير")
        print("=" * 80 + "\n")
        
        features_to_check = [
            ('loyalty', 'نظام الولاء'),
            ('return', 'نظام المرتجعات'),
            ('gl_batch', 'محاسبة GL'),
            ('settlement', 'التسويات'),
            ('rating', 'التقييمات')
        ]
        
        routes_dir = 'routes'
        if not os.path.exists(routes_dir):
            return
        
        for keyword, feature_name in features_to_check:
            found = False
            files = []
            
            for file in os.listdir(routes_dir):
                if not file.endswith('.py'):
                    continue
                
                filepath = os.path.join(routes_dir, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if keyword in content.lower():
                        found = True
                        files.append(file)
                except:
                    pass
            
            print(f"🔍 {feature_name} ({keyword}):")
            if found:
                print(f"   ✅ موجود في: {', '.join(files)}")
                print(f"   ⚠️  يحتاج فحص دقيق قبل التعديل")
            else:
                print(f"   ❌ غير موجود")
                print(f"   ✅ آمن للتطوير")
                self.safe_to_implement.append({
                    'model': feature_name,
                    'type': 'route',
                    'reason': 'لا يوجد routes حالية'
                })
            print()
    
    def check_templates_for_features(self):
        """فحص Templates للميزات قيد التطوير"""
        print("\n" + "=" * 80)
        print("4️⃣  فحص Templates للميزات قيد التطوير")
        print("=" * 80 + "\n")
        
        features = [
            ('loyalty', 'الولاء'),
            ('return', 'المرتجعات'),
            ('rating', 'التقييمات'),
            ('settlement', 'التسويات')
        ]
        
        templates_dir = 'templates'
        if not os.path.exists(templates_dir):
            return
        
        for keyword, feature_name in features:
            found_templates = []
            
            for root, dirs, files in os.walk(templates_dir):
                for file in files:
                    if keyword in file.lower() or keyword in root.lower():
                        rel_path = os.path.relpath(os.path.join(root, file), templates_dir)
                        found_templates.append(rel_path)
            
            print(f"📄 {feature_name}:")
            if found_templates:
                print(f"   ✅ Templates موجودة: {len(found_templates)}")
                for tmpl in found_templates[:3]:
                    print(f"      - {tmpl}")
                print(f"   ⚠️  يحتاج فحص دقيق")
            else:
                print(f"   ❌ لا توجد templates")
                print(f"   ✅ آمن للتطوير")
            print()
    
    def check_database_tables(self):
        """فحص جداول قاعدة البيانات الفعلية"""
        print("\n" + "=" * 80)
        print("5️⃣  فحص جداول قاعدة البيانات")
        print("=" * 80 + "\n")
        
        # فحص ملف قاعدة البيانات
        db_files = ['instance/garage.db', 'garage.db', 'database.db']
        
        for db_file in db_files:
            if os.path.exists(db_file):
                print(f"✅ قاعدة البيانات موجودة: {db_file}")
                print(f"   الحجم: {os.path.getsize(db_file) / 1024:.2f} KB")
                print(f"\n   ⚠️  يجب فحص الجداول الموجودة قبل إضافة جديدة")
                break
        else:
            print("❌ لم يتم العثور على ملف قاعدة البيانات")
    
    def generate_safety_report(self):
        """توليد تقرير السلامة"""
        print("\n" + "=" * 80)
        print("📊 تقرير السلامة للتطوير")
        print("=" * 80 + "\n")
        
        print(f"✅ آمن للتطوير: {len(self.safe_to_implement)} عنصر")
        print(f"⚠️  يحتاج حذر: {len(self.not_safe)} عنصر\n")
        
        if self.safe_to_implement:
            print("=" * 80)
            print("✅ العناصر الآمنة للتطوير:")
            print("=" * 80)
            for item in self.safe_to_implement[:10]:
                print(f"   • {item['model']} ({item['type']}): {item['reason']}")
            
            if len(self.safe_to_implement) > 10:
                print(f"   ... و {len(self.safe_to_implement) - 10} عنصر آخر")
        
        if self.not_safe:
            print("\n" + "=" * 80)
            print("⚠️  العناصر التي تحتاج حذر:")
            print("=" * 80)
            for item in self.not_safe[:10]:
                print(f"   • {item['model']} ({item['type']}): {item['reason']}")
        
        # حفظ التقرير
        report = {
            'safe_to_implement': self.safe_to_implement,
            'not_safe': self.not_safe,
            'total_models': len(self.models),
            'recommendations': self._generate_recommendations()
        }
        
        with open('SAFETY_ANALYSIS.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 80)
        print("💾 تم حفظ التقرير في: SAFETY_ANALYSIS.json")
        print("=" * 80)
    
    def _generate_recommendations(self):
        """توليد توصيات التطوير"""
        recommendations = []
        
        # توصيات بناءً على التحليل
        if len(self.safe_to_implement) > 0:
            recommendations.append("يمكن البدء بالعناصر الآمنة أولاً")
        
        if len(self.not_safe) > 0:
            recommendations.append("العناصر المستخدمة تحتاج اختبار مكثف")
        
        recommendations.append("يُفضل إنشاء backup قبل أي تطوير")
        recommendations.append("اختبار كل feature على حدة قبل دمجه")
        
        return recommendations
    
    def run_full_analysis(self):
        """تشغيل التحليل الكامل"""
        print("\n" + "=" * 80)
        print("🔍 تحليل عميق للنظام قبل التطوير")
        print("=" * 80 + "\n")
        
        self.analyze_models_in_detail()
        self.analyze_wip_models()
        self.check_routes_for_features()
        self.check_templates_for_features()
        self.check_database_tables()
        self.generate_safety_report()
        
        print("\n" + "=" * 80)
        print("✅ انتهى التحليل")
        print("=" * 80)

if __name__ == '__main__':
    analyzer = DeepSystemAnalyzer()
    analyzer.run_full_analysis()

