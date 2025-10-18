"""
AI Diagnostic Engine - محرك التشخيص الذكي
تشخيص الأعطال كخبير ميكانيكي
"""

from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from extensions import db


# ====================================================================
# التشخيص الذكي بناءً على الأعراض
# ====================================================================

def smart_diagnose(symptoms: str) -> Dict[str, Any]:
    """تشخيص ذكي شامل - كأنك ميكانيكي خبير"""
    from services.ai_mechanical_knowledge import diagnose_problem, COMMON_PROBLEMS
    
    # تحليل الأعراض
    symptoms_list = symptoms.lower().split()
    
    # تشخيص أولي
    diagnosis = diagnose_problem(symptoms_list)
    
    if not diagnosis['diagnosis']:
        return {
            'success': False,
            'message': 'لم أستطع تحديد المشكلة بدقة. أعطني تفاصيل أكثر:',
            'questions': [
                '• ما هو الصوت بالضبط؟ (صرير، طقطقة، احتكاك)',
                '• متى تحدث المشكلة؟ (عند التشغيل، أثناء القيادة، عند الفرملة)',
                '• هل توجد لمبات تحذير مضاءة؟',
                '• هل يوجد دخان؟ ما لونه؟'
            ]
        }
    
    top_problem = diagnosis['diagnosis'][0]
    problem_data = top_problem['data']
    
    response = f"""🔍 **التشخيص الذكي:**

🎯 **المشكلة المحتملة:** {problem_data['name_ar']}
📊 **مستوى الثقة:** {diagnosis['confidence']}

⚠️ **الأعراض المطابقة:**
"""
    for symptom in problem_data.get('symptoms', [])[:3]:
        response += f"  ✓ {symptom}\n"
    
    response += "\n🔬 **الأسباب المحتملة:**\n"
    for cause in problem_data.get('possible_causes', [])[:5]:
        response += f"  • {cause}\n"
    
    response += "\n🔧 **خطوات التشخيص المطلوبة:**\n"
    for step in problem_data.get('diagnosis_steps', []):
        response += f"  {step}\n"
    
    response += "\n✅ **الحلول المقترحة:**\n"
    for idx, solution in enumerate(problem_data.get('solutions', []), 1):
        response += f"  {idx}. {solution}\n"
    
    if problem_data.get('parts_needed'):
        response += "\n📦 **القطع المطلوبة:**\n"
        for part in problem_data['parts_needed']:
            response += f"  • {part}\n"
    
    if problem_data.get('emergency'):
        response += f"\n🚨 **تحذير عاجل:**\n{problem_data['emergency']}\n"
    
    # توصيات إضافية
    response += "\n💡 **توصيتي كميكانيكي:**\n"
    if 'engine' in problem_data.get('name_en', '').lower():
        response += "  • ابدأ بالفحوصات الأرخص أولاً (فلاتر، سوائل)\n"
        response += "  • لا تهمل الصيانة الدورية - الوقاية أرخص من العلاج\n"
    
    return {
        'success': True,
        'response': response,
        'problem': problem_data['name_ar'],
        'parts_needed': problem_data.get('parts_needed', [])
    }


# ====================================================================
# التشخيص المتقدم للمعدات الثقيلة
# ====================================================================

def diagnose_heavy_equipment(equipment_type: str, symptoms: str) -> str:
    """تشخيص متخصص للمعدات الثقيلة"""
    from services.ai_mechanical_knowledge import HEAVY_EQUIPMENT_KNOWLEDGE
    
    equipment_type_lower = equipment_type.lower()
    symptoms_lower = symptoms.lower()
    
    equipment_data = None
    if 'حفار' in equipment_type_lower or 'excavator' in equipment_type_lower:
        equipment_data = HEAVY_EQUIPMENT_KNOWLEDGE.get('excavator')
    elif 'لودر' in equipment_type_lower or 'loader' in equipment_type_lower:
        equipment_data = HEAVY_EQUIPMENT_KNOWLEDGE.get('loader')
    
    if not equipment_data:
        return f"❌ نوع المعدة غير معروف: {equipment_type}"
    
    response = f"""🏗️ **تشخيص {equipment_data['name_ar']}:**

📋 **الأعراض:** {symptoms}

"""
    
    # تحليل الأعراض حسب النظام
    if 'بطء' in symptoms_lower or 'ضعيف' in symptoms_lower or 'slow' in symptoms_lower:
        if equipment_data['name_en'] == 'Excavator':
            response += """🔍 **تشخيصي:**

المشكلة غالباً في **النظام الهيدروليكي**:

🔧 **خطوات الفحص:**
1. افحص مستوى زيت الهيدروليك
2. افحص الفلتر (مسدود؟)
3. قِس ضغط النظام (يجب أن يكون 250-350 bar)
4. افحص التسريبات الخارجية
5. افحص حرارة الزيت (لا يتجاوز 80 درجة)

✅ **الحلول المحتملة:**
  1. أضف زيت إن ناقص
  2. بدل الفلتر (50-200₪)
  3. نظّف الصمامات
  4. بدل المضخة إن متآكلة (3,000-15,000₪)

⚠️ لا تشغل المعدة بزيت ناقص - تلف كارثي!
"""
    elif 'انحراف' in symptoms_lower or 'deviation' in symptoms_lower:
        response += """🔍 **تشخيصي:**

المشكلة في **الجنزير أو محرك الدوران**:

🔧 **خطوات الفحص:**
1. افحص توتر الجنزير (Tension)
2. افحص تآكل الأسنان
3. افحص محرك الدوران (Travel Motor)
4. افحص الفرامل

✅ **الحلول:**
  1. اضبط توتر الجنزير
  2. بدل الحلقات المتآكلة (150-500₪/حلقة)
  3. صلّح محرك الدوران
"""
    
    return response


# ====================================================================
# فحص القطع من المستودع
# ====================================================================

def check_part_in_inventory(part_identifier: str) -> dict:
    """فحص قطعة في المخزون - بالاسم أو الرقم"""
    from models import Product, StockLevel
    from services.ai_parts_database import search_part_by_name, search_part_by_number, explain_part_function
    
    # البحث في قاعدة المعرفة أولاً
    knowledge_result = search_part_by_name(part_identifier)
    if not knowledge_result['results']:
        knowledge_result = search_part_by_number(part_identifier)
    
    # البحث في المخزون الفعلي
    db_product = Product.query.filter(
        (Product.name.ilike(f'%{part_identifier}%')) |
        (Product.sku.ilike(f'%{part_identifier}%')) |
        (Product.barcode.ilike(f'%{part_identifier}%'))
    ).first()
    
    response = ""
    
    # معلومات من قاعدة المعرفة
    if knowledge_result.get('results'):
        part_info = knowledge_result['results'][0]['info']
        response += f"""📚 **معلومات القطعة من قاعدة المعرفة:**

🔧 **{part_info['name_ar']}**
📝 الوظيفة: {part_info.get('function', 'N/A')}

🚗 **تركب على:**
"""
        for fit in part_info.get('fits', []):
            response += f"  • {fit}\n"
        
        if part_info.get('replacement_interval'):
            response += f"\n🔄 فترة التبديل: {part_info['replacement_interval']}\n"
    
    # معلومات من المخزون الفعلي
    if db_product:
        stock = db.session.query(StockLevel).filter_by(product_id=db_product.id).first()
        
        response += f"""
💾 **حالة المخزون:**
• الاسم: {db_product.name}
• SKU: {db_product.sku or 'N/A'}
• الكمية المتوفرة: {stock.quantity if stock else 0}
• السعر: {db_product.price or 0}₪
"""
        
        if stock and stock.quantity < (db_product.min_stock_level or 10):
            response += f"\n⚠️ **تحذير:** الكمية أقل من الحد الأدنى ({db_product.min_stock_level})!"
    else:
        response += "\n\n⚠️ **القطعة غير موجودة في المخزون حالياً**"
    
    return {
        'found': bool(knowledge_result.get('results') or db_product),
        'response': response if response else f"❌ لم أجد معلومات عن \"{part_identifier}\""
    }

