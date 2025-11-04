from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path
import json


class HeavyEquipmentExpert:
    
    def __init__(self):
        self.knowledge_base = {}
        self.equipment_types = {}
        self.maintenance_procedures = {}
        self.troubleshooting_guides = {}
        
        self.data_dir = Path('AI/data/heavy_equipment')
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def train_comprehensive(self) -> Dict:
        print("[HEAVY EQUIPMENT EXPERT TRAINING - START]")
        print("=" * 80)
        
        total_items = 0
        
        total_items += self._train_equipment_types()
        total_items += self._train_maintenance_fundamentals()
        total_items += self._train_preventive_maintenance()
        total_items += self._train_corrective_maintenance()
        total_items += self._train_diagnostic_techniques()
        total_items += self._train_parts_management()
        total_items += self._train_safety_procedures()
        total_items += self._train_documentation()
        total_items += self._train_cost_management()
        total_items += self._train_scheduling()
        total_items += self._train_tools_equipment()
        total_items += self._train_troubleshooting()
        total_items += self._train_performance_metrics()
        total_items += self._train_regulations_standards()
        total_items += self._train_advanced_topics()
        
        print("=" * 80)
        print(f"[HEAVY EQUIPMENT EXPERT TRAINING - COMPLETE]")
        print(f"Total items learned: {total_items}")
        
        return {
            'success': True,
            'items_learned': total_items,
            'specialties': 15
        }
    
    def _train_equipment_types(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[1/15] Equipment Types & Classifications")
        memory = get_deep_memory()
        items = 0
        
        equipment_categories = {
            'معدات الحفر والتجريف': {
                'الحفارات Excavators': 'معدات حفر وتحميل التربة والصخور',
                'اللوادر Loaders': 'معدات تحميل المواد',
                'البلدوزرات Bulldozers': 'معدات تسوية ودفع التربة',
                'الجرافات Graders': 'معدات تسوية وتشكيل الأسطح'
            },
            'معدات الرفع': {
                'الرافعات Cranes': 'معدات رفع الأحمال الثقيلة',
                'الرافعات الشوكية Forklifts': 'رفع ونقل البضائع',
                'الرافعات البرجية Tower Cranes': 'رفع في المباني العالية'
            },
            'معدات الطرق': {
                'الرصافات Asphalt Pavers': 'رصف الطرق بالإسفلت',
                'الحفارات الأسفلتية Milling Machines': 'إزالة طبقات الإسفلت',
                'الدكاكات Compactors': 'ضغط وتثبيت التربة والإسفلت',
                'خلاطات الإسفلت Asphalt Plants': 'إنتاج خلطة الإسفلت'
            },
            'معدات النقل': {
                'الشاحنات القلابة Dump Trucks': 'نقل المواد السائبة',
                'الناقلات Conveyors': 'نقل المواد المستمر',
                'المقطورات Trailers': 'نقل المعدات والبضائع'
            },
            'معدات التكسير': {
                'الكسارات Crushers': 'تكسير الصخور والخرسانة',
                'المطاحن Mills': 'طحن المواد',
                'الناخلات Screens': 'فصل المواد حسب الحجم'
            }
        }
        
        for category, equipment_list in equipment_categories.items():
            memory.remember_concept(
                f'فئة المعدات: {category}',
                f'تصنيف رئيسي للمعدات الثقيلة',
                examples=list(equipment_list.keys()),
                related=['heavy_equipment', 'maintenance']
            )
            items += 1
            
            for equipment, description in equipment_list.items():
                memory.remember_concept(
                    equipment,
                    description,
                    examples=[],
                    related=[category, 'heavy_equipment']
                )
                items += 1
        
        components = {
            'المحرك Engine': 'مصدر القوة الرئيسي',
            'ناقل الحركة Transmission': 'نقل القوة من المحرك للعجلات',
            'الهيدروليك Hydraulics': 'نظام الضغط الهيدروليكي للحركة',
            'نظام التبريد Cooling System': 'تبريد المحرك',
            'نظام الوقود Fuel System': 'إمداد المحرك بالوقود',
            'نظام الكهرباء Electrical System': 'التحكم والإضاءة',
            'نظام الفرامل Braking System': 'إيقاف الحركة',
            'نظام التعليق Suspension': 'امتصاص الصدمات',
            'الإطارات/الجنازير Tires/Tracks': 'الحركة والثبات',
            'كابينة المشغل Operator Cabin': 'التحكم والقيادة'
        }
        
        for component, description in components.items():
            memory.remember_fact(
                'equipment_component',
                component,
                {'description': description, 'critical': True},
                importance=9
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_maintenance_fundamentals(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[2/15] Maintenance Fundamentals")
        memory = get_deep_memory()
        items = 0
        
        maintenance_types = {
            'الصيانة الوقائية Preventive': 'صيانة منتظمة لمنع الأعطال',
            'الصيانة التنبؤية Predictive': 'صيانة بناءً على مراقبة الأداء',
            'الصيانة التصحيحية Corrective': 'إصلاح بعد حدوث العطل',
            'الصيانة الطارئة Emergency': 'إصلاح فوري لعطل مفاجئ',
            'الصيانة المخططة Scheduled': 'صيانة حسب جدول زمني',
            'الصيانة القائمة على الحالة Condition-based': 'صيانة حسب حالة المعدة'
        }
        
        for mtype, description in maintenance_types.items():
            memory.remember_concept(
                mtype,
                description,
                examples=[],
                related=['maintenance', 'heavy_equipment']
            )
            items += 1
        
        maintenance_levels = {
            'المستوى الأول - يومي': 'فحص بصري، تشحيم، تنظيف',
            'المستوى الثاني - أسبوعي': 'فحص السوائل، الفلاتر، الأحزمة',
            'المستوى الثالث - شهري': 'فحص شامل، استبدال قطع بسيطة',
            'المستوى الرابع - ربع سنوي': 'صيانة متوسطة، فحص دقيق',
            'المستوى الخامس - سنوي': 'صيانة شاملة، إصلاحات كبيرة',
            'الإصلاح الرأسمالي Overhaul': 'تجديد كامل للمعدة'
        }
        
        for level, tasks in maintenance_levels.items():
            memory.remember_procedure(
                f'صيانة {level}',
                tasks.split('، '),
                context={'category': 'maintenance_level'}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_preventive_maintenance(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[3/15] Preventive Maintenance Procedures")
        memory = get_deep_memory()
        items = 0
        
        pm_tasks = {
            'فحص مستوى الزيت': [
                'إيقاف المحرك والانتظار 5 دقائق',
                'سحب عصا القياس وتنظيفها',
                'إعادة إدخالها وسحبها مرة أخرى',
                'التحقق من المستوى بين MIN وMAX',
                'إضافة زيت إذا لزم الأمر'
            ],
            'فحص سائل التبريد': [
                'التحقق من المحرك بارد',
                'فحص مستوى السائل في الخزان',
                'التحقق من لون السائل (أخضر/أحمر)',
                'فحص عدم وجود تسريبات',
                'إضافة سائل بنفس النوع إذا لزم'
            ],
            'فحص الفلاتر': [
                'فلتر الهواء - تنظيف أو استبدال',
                'فلتر الزيت - استبدال مع تغيير الزيت',
                'فلتر الوقود - استبدال كل 500 ساعة',
                'فلتر الهيدروليك - فحص واستبدال',
                'فلتر كابينة - تنظيف أو استبدال'
            ],
            'فحص الأحزمة والخراطيم': [
                'فحص بصري للتشققات',
                'التحقق من الشد المناسب',
                'فحص التآكل أو التلف',
                'استبدال إذا كان هناك علامات ضعف',
                'تسجيل حالة كل حزام'
            ],
            'التشحيم': [
                'تحديد نقاط التشحيم حسب الدليل',
                'تنظيف نقاط التشحيم',
                'استخدام الشحم المناسب',
                'ضخ الشحم حتى يظهر جديد',
                'إزالة الشحم الزائد'
            ]
        }
        
        for task_name, steps in pm_tasks.items():
            memory.remember_procedure(
                f'PM: {task_name}',
                steps,
                context={'category': 'preventive_maintenance', 'critical': True}
            )
            items += 1
        
        pm_intervals = {
            'يومياً (كل 8-10 ساعات)': 'فحص بصري، مستويات، تسريبات',
            '50 ساعة': 'تشحيم، فحص أحزمة',
            '100 ساعة': 'فحص فلاتر، سوائل',
            '250 ساعة': 'تغيير زيت المحرك، فلاتر',
            '500 ساعة': 'فحص شامل، تغيير سوائل',
            '1000 ساعة': 'صيانة كبرى، فحص متقدم',
            '2000 ساعة': 'صيانة رئيسية، إصلاحات'
        }
        
        for interval, tasks in pm_intervals.items():
            memory.remember_fact(
                'pm_interval',
                interval,
                {'tasks': tasks},
                importance=9
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_corrective_maintenance(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[4/15] Corrective Maintenance")
        memory = get_deep_memory()
        items = 0
        
        common_failures = {
            'المحرك لا يعمل': [
                'فحص البطارية والتوصيلات',
                'فحص مفتاح الأمان',
                'فحص الوقود في الخزان',
                'فحص فلتر الوقود',
                'فحص مضخة الوقود',
                'فحص نظام الإشعال'
            ],
            'ارتفاع حرارة المحرك': [
                'فحص مستوى سائل التبريد',
                'فحص المبرد والمروحة',
                'فحص طرمبة الماء',
                'فحص الثرموستات',
                'فحص وجود تسريبات',
                'تنظيف المبرد'
            ],
            'ضعف في القوة': [
                'فحص فلتر الهواء',
                'فحص نظام الوقود',
                'فحص ضغط المحرك',
                'فحص البخاخات',
                'فحص التوربو إن وجد',
                'فحص ناقل الحركة'
            ],
            'تسريب الزيت': [
                'تحديد مصدر التسريب',
                'فحص الجوانات والأوتار',
                'فحص سدادة الزيت',
                'فحص فلتر الزيت',
                'استبدال القطع التالفة',
                'اختبار بعد الإصلاح'
            ]
        }
        
        for failure, diagnosis_steps in common_failures.items():
            memory.remember_procedure(
                f'إصلاح: {failure}',
                diagnosis_steps,
                context={'category': 'corrective_maintenance', 'type': 'troubleshooting'}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_diagnostic_techniques(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[5/15] Diagnostic Techniques")
        memory = get_deep_memory()
        items = 0
        
        diagnostic_methods = {
            'الفحص البصري': 'فحص بالعين للتسريبات، التآكل، التلف',
            'الاستماع': 'الكشف عن الأصوات غير الطبيعية',
            'قياس الضغط': 'فحص ضغط المحرك، الهيدروليك، الإطارات',
            'قياس درجة الحرارة': 'استخدام ثيرمومتر أو كاميرا حرارية',
            'تحليل الاهتزازات': 'كشف عدم التوازن أو التلف',
            'تحليل الزيت': 'فحص مخبري لحالة المحرك',
            'الاختبار الكهربائي': 'فحص الدوائر والبطارية',
            'الفحص بالكمبيوتر': 'قراءة أكواد الأعطال'
        }
        
        for method, description in diagnostic_methods.items():
            memory.remember_concept(
                f'تشخيص: {method}',
                description,
                examples=[],
                related=['diagnostic', 'maintenance']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_parts_management(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[6/15] Parts & Inventory Management")
        memory = get_deep_memory()
        items = 0
        
        parts_categories = {
            'قطع الاستهلاك السريع': 'فلاتر، زيوت، شحوم، أحزمة',
            'قطع الصيانة الدورية': 'فلاتر هواء، بطاريات، إطارات',
            'قطع الأمان الحرجة': 'فرامل، توجيه، إضاءة',
            'قطع الإصلاح الكبرى': 'محركات، ناقل حركة، مضخات'
        }
        
        for category, examples in parts_categories.items():
            memory.remember_concept(
                f'قطع الغيار: {category}',
                examples,
                examples=examples.split('، '),
                related=['parts', 'inventory']
            )
            items += 1
        
        inventory_principles = {
            'ABC Analysis': 'تصنيف القطع حسب الأهمية والقيمة',
            'EOQ': 'كمية الطلب الاقتصادية',
            'Safety Stock': 'مخزون الأمان للطوارئ',
            'Lead Time': 'وقت التوريد',
            'FIFO': 'الوارد أولاً يصرف أولاً',
            'Min-Max Levels': 'الحد الأدنى والأقصى للمخزون'
        }
        
        for principle, description in inventory_principles.items():
            memory.remember_concept(
                principle,
                description,
                examples=[],
                related=['inventory_management']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_safety_procedures(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[7/15] Safety Procedures")
        memory = get_deep_memory()
        items = 0
        
        safety_rules = {
            'LOTO - Lock Out Tag Out': 'عزل مصدر الطاقة قبل الصيانة',
            'معدات الوقاية الشخصية PPE': 'خوذة، نظارات، قفازات، أحذية',
            'منطقة العمل الآمنة': 'تأمين المنطقة ووضع علامات',
            'التعامل مع المواد الخطرة': 'زيوت، وقود، سوائل كيماوية',
            'رفع الأحمال': 'استخدام معدات الرفع المناسبة',
            'العمل تحت المعدة': 'استخدام حوامل آمنة',
            'التعامل مع الكهرباء': 'فصل البطارية، عزل الأسلاك',
            'الإسعافات الأولية': 'توفر صندوق إسعاف، تدريب العاملين'
        }
        
        for rule, description in safety_rules.items():
            memory.remember_procedure(
                f'سلامة: {rule}',
                [description, 'إجراء إلزامي', 'عدم التهاون'],
                context={'category': 'safety', 'priority': 'critical'}
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_documentation(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[8/15] Documentation & Records")
        memory = get_deep_memory()
        items = 0
        
        documents = {
            'سجل الصيانة': 'تسجيل كل عملية صيانة',
            'سجل ساعات التشغيل': 'متابعة ساعات عمل المعدة',
            'سجل الأعطال': 'توثيق الأعطال والإصلاحات',
            'سجل قطع الغيار': 'متابعة القطع المستبدلة',
            'سجل الفحوصات': 'نتائج الفحوصات الدورية',
            'كتيبات المشغل': 'دليل التشغيل والصيانة',
            'مخططات القطع': 'رسومات توضيحية',
            'بطاقة المعدة': 'بيانات المعدة والمواصفات'
        }
        
        for doc, purpose in documents.items():
            memory.remember_fact(
                'documentation',
                doc,
                {'purpose': purpose, 'required': True},
                importance=8
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_cost_management(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[9/15] Maintenance Cost Management")
        memory = get_deep_memory()
        items = 0
        
        cost_components = {
            'تكلفة العمالة': 'أجور الفنيين والمشرفين',
            'تكلفة قطع الغيار': 'قيمة القطع المستبدلة',
            'تكلفة المواد الاستهلاكية': 'زيوت، شحوم، مواد تنظيف',
            'تكلفة الأدوات': 'شراء وصيانة الأدوات',
            'تكلفة التوقف': 'خسارة الإنتاج أثناء العطل',
            'تكلفة الخدمات الخارجية': 'الاستعانة بمقاولين',
            'تكلفة التدريب': 'تدريب الفنيين'
        }
        
        for cost_type, description in cost_components.items():
            memory.remember_concept(
                cost_type,
                description,
                examples=[],
                related=['maintenance_cost', 'budget']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_scheduling(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[10/15] Maintenance Scheduling")
        memory = get_deep_memory()
        items = 0
        
        scheduling_methods = {
            'جدولة حسب الساعات': 'صيانة كل X ساعة تشغيل',
            'جدولة حسب التقويم': 'صيانة شهرية، ربع سنوية، سنوية',
            'جدولة حسب الحالة': 'عند ظهور مؤشرات التآكل',
            'جدولة الطوارئ': 'استجابة فورية للأعطال'
        }
        
        for method, description in scheduling_methods.items():
            memory.remember_concept(
                f'جدولة: {method}',
                description,
                examples=[],
                related=['scheduling', 'planning']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_tools_equipment(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[11/15] Tools & Equipment")
        memory = get_deep_memory()
        items = 0
        
        tools = {
            'أدوات يدوية': 'مفكات، مفاتيح ربط، كماشات',
            'أدوات كهربائية': 'دريل، صاروخ، مطحنة',
            'أدوات قياس': 'مقياس ضغط، ثيرمومتر، ميزان',
            'أدوات رفع': 'رافعة، ونش، جاك',
            'أدوات تشخيص': 'ماسح أعطال، ملتيميتر',
            'معدات اللحام': 'لحام كهربائي، أكسجين'
        }
        
        for tool_category, examples in tools.items():
            memory.remember_concept(
                tool_category,
                examples,
                examples=examples.split('، '),
                related=['tools', 'maintenance']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_troubleshooting(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[12/15] Troubleshooting Guide")
        memory = get_deep_memory()
        items = 0
        
        troubleshooting_steps = [
            '1. جمع المعلومات: متى بدأ العطل؟ ظروف التشغيل؟',
            '2. فحص أولي: فحص بصري، استماع، شم',
            '3. مراجعة السجلات: آخر صيانة؟ أعطال سابقة؟',
            '4. عزل المشكلة: تضييق نطاق البحث',
            '5. الفحص التفصيلي: استخدام أدوات القياس',
            '6. تحديد السبب الجذري: لماذا حدث العطل؟',
            '7. التخطيط للإصلاح: قطع؟ أدوات؟ وقت؟',
            '8. التنفيذ: إصلاح العطل',
            '9. الاختبار: التأكد من زوال العطل',
            '10. التوثيق: تسجيل العطل والإصلاح'
        ]
        
        memory.remember_procedure(
            'منهجية حل المشاكل',
            troubleshooting_steps,
            context={'category': 'troubleshooting', 'systematic': True}
        )
        items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_performance_metrics(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[13/15] Performance Metrics")
        memory = get_deep_memory()
        items = 0
        
        kpis = {
            'MTBF - Mean Time Between Failures': 'متوسط الوقت بين الأعطال',
            'MTTR - Mean Time To Repair': 'متوسط وقت الإصلاح',
            'Availability': 'نسبة جاهزية المعدة',
            'OEE - Overall Equipment Effectiveness': 'الفعالية الإجمالية',
            'Maintenance Cost per Hour': 'تكلفة الصيانة لكل ساعة تشغيل',
            'PM Compliance': 'نسبة الالتزام بالصيانة الوقائية',
            'Parts Inventory Turnover': 'معدل دوران قطع الغيار'
        }
        
        for kpi, description in kpis.items():
            memory.remember_concept(
                kpi,
                description,
                examples=[],
                related=['KPI', 'performance', 'maintenance']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_regulations_standards(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[14/15] Regulations & Standards")
        memory = get_deep_memory()
        items = 0
        
        standards = {
            'ISO 9001': 'إدارة الجودة',
            'ISO 14001': 'الإدارة البيئية',
            'ISO 45001': 'الصحة والسلامة المهنية',
            'ISO 55000': 'إدارة الأصول',
            'OSHA': 'معايير السلامة المهنية',
            'EPA': 'حماية البيئة'
        }
        
        for standard, purpose in standards.items():
            memory.remember_fact(
                'standard',
                standard,
                {'purpose': purpose},
                importance=7
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items
    
    def _train_advanced_topics(self) -> int:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        print("\n[15/15] Advanced Topics")
        memory = get_deep_memory()
        items = 0
        
        advanced = {
            'الصيانة بالاعتماد على الموثوقية RCM': 'استراتيجية صيانة متقدمة',
            'التحسين المستمر Kaizen': 'تطوير عمليات الصيانة',
            'الصيانة الإنتاجية الشاملة TPM': 'إشراك الجميع في الصيانة',
            'التحليل الجذري للأعطال RCA': 'منع تكرار الأعطال',
            'إدارة دورة حياة الأصول': 'من الشراء للتخلص',
            'الصيانة الذكية': 'استخدام IoT والذكاء الصناعي',
            'التوأم الرقمي Digital Twin': 'محاكاة أداء المعدة'
        }
        
        for topic, description in advanced.items():
            memory.remember_concept(
                topic,
                description,
                examples=[],
                related=['advanced_maintenance']
            )
            items += 1
        
        print(f"  Learned: {items} items")
        return items


_heavy_equipment_expert = None

def get_heavy_equipment_expert():
    global _heavy_equipment_expert
    if _heavy_equipment_expert is None:
        _heavy_equipment_expert = HeavyEquipmentExpert()
    return _heavy_equipment_expert


__all__ = ['HeavyEquipmentExpert', 'get_heavy_equipment_expert']

