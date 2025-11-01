"""
AI Predictive Analytics - تحليلات تنبؤية
التنبؤ بالقطع المطلوبة والأعطال المتكررة
"""

from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import List, Dict, Any
from extensions import db
from sqlalchemy import func, desc


def predict_needed_parts(days_back: int = 90) -> Dict[str, Any]:
    """التنبؤ بالقطع المطلوبة بناءً على الأعطال المتكررة"""
    from models import ServiceRequest, ServicePart, Product
    
    # جمع القطع المستخدمة في الفترة الأخيرة
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    parts_usage = db.session.query(
        Product.name,
        Product.id,
        func.count(ServicePart.id).label('usage_count'),
        func.sum(ServicePart.quantity).label('total_quantity')
    ).join(ServicePart, ServicePart.part_id == Product.id
    ).join(ServiceRequest, ServiceRequest.id == ServicePart.service_id
    ).filter(
        ServiceRequest.received_at >= start_date
    ).group_by(Product.id).order_by(desc('usage_count')).all()
    
    if not parts_usage:
        return {
            'success': False,
            'message': 'لا توجد بيانات كافية للتنبؤ'
        }
    
    # التحليل التنبؤي
    predictions = []
    
    for product_name, product_id, usage_count, total_quantity in parts_usage[:10]:
        # حساب المعدل الشهري
        monthly_rate = (total_quantity or 0) / (days_back / 30)
        
        # التنبؤ للشهر القادم
        predicted_next_month = int(monthly_rate * 1.2)  # + 20% buffer
        
        # فحص المخزون الحالي
        from models import StockLevel
        stock = db.session.query(StockLevel).filter_by(product_id=product_id).first()
        current_stock = stock.quantity if stock else 0
        
        # تحديد الحاجة
        need_to_order = max(0, predicted_next_month - current_stock)
        
        priority = 'عالية' if need_to_order > monthly_rate else 'متوسطة'
        if current_stock < monthly_rate:
            priority = 'عاجلة!'
        
        predictions.append({
            'part_name': product_name,
            'usage_count': usage_count,
            'total_used': total_quantity,
            'monthly_rate': round(monthly_rate, 1),
            'predicted_next_month': predicted_next_month,
            'current_stock': current_stock,
            'need_to_order': need_to_order,
            'priority': priority
        })
    
    return {
        'success': True,
        'period': f'{days_back} يوم',
        'predictions': predictions,
        'top_5': predictions[:5]
    }


def analyze_recurring_failures(days_back: int = 180) -> Dict[str, Any]:
    """تحليل الأعطال المتكررة - للتنبؤ المستقبلي"""
    from models import ServiceRequest
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    # جمع أوصاف المشاكل
    services = db.session.query(ServiceRequest).filter(
        ServiceRequest.received_at >= start_date
    ).all()
    
    if not services:
        return {'success': False, 'message': 'لا توجد بيانات'}
    
    # تحليل الكلمات المفتاحية
    keywords_counter = Counter()
    
    problem_categories = {
        'محرك': 0,
        'فرامل': 0,
        'كهرباء': 0,
        'تعليق': 0,
        'هيدروليك': 0,
        'جنزير': 0
    }
    
    for service in services:
        desc = (service.description or '').lower()
        
        for category in problem_categories.keys():
            if category in desc:
                problem_categories[category] += 1
        
        # استخراج الكلمات
        words = desc.split()
        keywords_counter.update([w for w in words if len(w) > 3])
    
    # أكثر المشاكل تكراراً
    top_categories = sorted(problem_categories.items(), key=lambda x: x[1], reverse=True)
    top_keywords = keywords_counter.most_common(10)
    
    response = f"""📊 **تحليل الأعطال المتكررة ({days_back} يوم):**

🔧 **أكثر فئات الأعطال:**
"""
    for category, count in top_categories[:5]:
        if count > 0:
            percentage = (count / len(services)) * 100
            response += f"  • {category}: {count} مرة ({percentage:.1f}%)\n"
    
    response += "\n🔍 **الكلمات الأكثر تكراراً:**\n"
    for word, count in top_keywords[:5]:
        response += f"  • \"{word}\": {count} مرة\n"
    
    # التنبؤ والتوصية
    top_category = top_categories[0][0] if top_categories[0][1] > 0 else None
    
    if top_category:
        response += f"""
💡 **استنتاجي:**
المشاكل الأكثر هي في **{top_category}**

🎯 **توصيتي التنبؤية:**
"""
        if top_category == 'محرك':
            response += """  • احتفظ بمخزون من: بواجي، فلاتر زيت، فلاتر هواء
  • راجع جودة الزيت المستخدم
  • قدّم باقات صيانة دورية للمحرك
"""
        elif top_category == 'فرامل':
            response += """  • احتفظ بمخزون من: فحمات فرامل، ديسكات
  • قدّم فحص فرامل مجاني
  • ذكّر العملاء بأهمية فحص الفرامل كل 6 أشهر
"""
        elif top_category == 'هيدروليك':
            response += """  • احتفظ بزيت هيدروليك، فلاتر، سيلات
  • فحص دوري للنظام الهيدروليكي
  • تدريب الفنيين على تشخيص الهيدروليك
"""
    
    return response


def predict_maintenance_schedule(vehicle_id: int = None) -> str:
    """التنبؤ بجدول الصيانة المطلوب"""
    # هذه دالة مثال - يمكن تطويرها بناءً على بيانات المركبات
    
    return """📅 **جدول الصيانة المتنبأ به:**

**صيانة دورية كل:**
• 5,000 كم: زيت + فلتر زيت
• 10,000 كم: + فلتر هواء + فحص الفرامل
• 20,000 كم: + فلتر وقود + شمعات
• 40,000 كم: + فلتر مكيف + فحص شامل
• 60,000 كم: + سير توقيت (حسب السيارة)

💡 **توصيتي:** أنشئ نظام تذكير تلقائي للعملاء!
"""

