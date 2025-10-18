"""
AI Parts Database - قاعدة بيانات قطع الغيار الشاملة
معرفة تفصيلية بكل قطعة: الاسم، الرقم، الفئة، التوافق، الاستخدام
"""

# ====================================================================
# قاعدة بيانات قطع الغيار - شاملة ومفصلة
# ====================================================================

PARTS_KNOWLEDGE = {
    # ========== قطع المحرك ==========
    'engine_parts': {
        'name': 'قطع المحرك',
        'parts': {
            'oil_filter': {
                'name_ar': 'فلتر زيت',
                'name_en': 'Oil Filter',
                'common_numbers': ['OC90', 'W920/21', 'HU925/4X'],
                'fits': [
                    'معظم السيارات الخفيفة',
                    'بعض المعدات الثقيلة الصغيرة'
                ],
                'function': 'تصفية الزيت من الشوائب لحماية المحرك',
                'replacement_interval': 'كل 5,000-10,000 كم أو 6 أشهر',
                'symptoms_when_bad': [
                    'صوت طقطقة من المحرك',
                    'ضغط زيت منخفض',
                    'زيت أسود جداً'
                ],
                'price_range': '15-50₪ حسب النوع'
            },
            'spark_plugs': {
                'name_ar': 'بواجي / شمعات الاحتراق',
                'name_en': 'Spark Plugs',
                'common_numbers': ['NGK BKR6E', 'DENSO K20TT', 'BOSCH FR7DC+'],
                'fits': [
                    'محركات بنزين فقط (ليس ديزل)',
                    'سيارات خفيفة ومتوسطة'
                ],
                'function': 'إشعال خليط البنزين والهواء',
                'replacement_interval': 'كل 30,000-100,000 كم حسب النوع',
                'symptoms_when_bad': [
                    'تقطيع في المحرك',
                    'صعوبة التشغيل',
                    'زيادة استهلاك الوقود',
                    'ضعف في العزم'
                ],
                'types': {
                    'copper': 'نحاس - عادي، رخيص، كل 30,000 كم',
                    'platinum': 'بلاتينيوم - أفضل، غالٍ، كل 60,000 كم',
                    'iridium': 'إيريديوم - ممتاز، أغلى، كل 100,000 كم'
                },
                'price_range': '10-40₪ للبوجية حسب النوع'
            },
            'timing_belt': {
                'name_ar': 'سير التوقيت / سير الكاتينة',
                'name_en': 'Timing Belt',
                'common_numbers': ['CT1149', 'TB295', 'GATES 5591XS'],
                'fits': [
                    'محركات بنزين وديزل',
                    'سيارات محددة (ليس كل السيارات)'
                ],
                'function': 'مزامنة حركة عمود الكرنك وعمود الكامات',
                'replacement_interval': 'كل 60,000-100,000 كم أو 5 سنوات (أيهما أقرب)',
                'symptoms_when_bad': [
                    'صوت صرير من المحرك',
                    'اهتزاز غير طبيعي',
                    'عدم انتظام الدوران'
                ],
                'critical_note': '⚠️ إذا انقطع السير أثناء الدوران، قد يتلف المحرك كاملاً! (محركات Interference)',
                'replacement_cost': '300-800₪ شامل العمالة',
                'replace_with_it': [
                    'مضخة الماء (Water Pump)',
                    'رولمان السير',
                    'سير المكيف (إن وجد)'
                ]
            },
            'engine_oil': {
                'name_ar': 'زيت المحرك',
                'name_en': 'Engine Oil',
                'types': {
                    'mineral': 'معدني - عادي، رخيص، كل 3,000-5,000 كم',
                    'semi_synthetic': 'نصف تخليقي - جيد، متوسط، كل 5,000-7,500 كم',
                    'full_synthetic': 'تخليقي كامل - ممتاز، غالٍ، كل 7,500-15,000 كم'
                },
                'viscosity': {
                    '5W-30': 'مناخ بارد ومعتدل - الأكثر شيوعاً',
                    '10W-40': 'مناخ حار - سيارات قديمة',
                    '0W-20': 'سيارات حديثة - موفر للوقود',
                    '15W-40': 'ديزل ومعدات ثقيلة'
                },
                'how_to_choose': [
                    '1. راجع دليل السيارة (Owner Manual)',
                    '2. انظر لمناخ المنطقة',
                    '3. عمر المحرك (قديم يحتاج لزوجة أعلى)',
                    '4. نوع القيادة (شاقة → تخليقي)'
                ]
            }
        }
    },
    
    # ========== قطع نظام الفرامل ==========
    'brake_parts': {
        'name': 'قطع الفرامل',
        'parts': {
            'brake_pads': {
                'name_ar': 'فحمات الفرامل / تيل الفرامل',
                'name_en': 'Brake Pads',
                'common_numbers': ['DB1234', 'BP2156', 'TRW GDB1234'],
                'fits': 'حسب موديل السيارة - يختلف لكل سيارة',
                'function': 'الاحتكاك لإيقاف السيارة',
                'replacement_interval': 'كل 30,000-70,000 كم حسب نوع القيادة',
                'symptoms_when_bad': [
                    'صوت صرير عند الفرملة',
                    'اهتزاز في الفرامل',
                    'مسافة توقف أطول',
                    'لمبة الفرامل تولع'
                ],
                'types': {
                    'organic': 'عضوي - هادئ، يتآكل أسرع',
                    'semi_metallic': 'نصف معدني - الأكثر شيوعاً',
                    'ceramic': 'سيراميك - ممتاز، غالٍ، قليل الغبار'
                },
                'installation_notes': [
                    'افحص الديسكات (قد تحتاج تجليخ أو تبديل)',
                    'غيّر زيت الفرامل كل سنتين',
                    'نظّف الكليبرات',
                    'test drive بعد التركيب'
                ]
            },
            'brake_discs': {
                'name_ar': 'ديسكات الفرامل / أقراص الفرامل',
                'name_en': 'Brake Discs/Rotors',
                'function': 'السطح الذي تحتك به الفحمات',
                'replacement_interval': 'كل 60,000-120,000 كم أو عند التآكل',
                'symptoms_when_bad': [
                    'اهتزاز شديد في الفرامل',
                    'أخاديد واضحة على السطح',
                    'سُمك أقل من الحد الأدنى',
                    'صوت احتكاك معدني'
                ],
                'inspection': [
                    'قِس السُمك (Thickness) - يجب أن يكون فوق الحد الأدنى',
                    'افحص السطح (مستوٍ أم متموج)',
                    'تحقق من عدم وجود شقوق (Cracks)'
                ],
                'cost': '150-400₪ للقرص'
            }
        }
    },
    
    # ========== قطع نظام التعليق ==========
    'suspension_parts': {
        'name': 'قطع التعليق',
        'parts': {
            'shock_absorbers': {
                'name_ar': 'مساعدين / ممتصات الصدمات',
                'name_en': 'Shock Absorbers',
                'function': 'امتصاص الصدمات وتوفير راحة القيادة',
                'types': {
                    'hydraulic': 'هيدروليك - عادي',
                    'gas': 'غاز - أفضل أداء',
                    'adjustable': 'قابل للتعديل - سيارات رياضية'
                },
                'symptoms_when_bad': [
                    'ارتداد زائد بعد المطب',
                    'تآكل غير منتظم للإطارات',
                    'انحراف السيارة',
                    'تسرب زيت من المساعد'
                ],
                'replacement_interval': 'كل 80,000-150,000 كم'
            }
        }
    },
    
    # ========== المعدات الثقيلة - قطع خاصة ==========
    'heavy_equipment_parts': {
        'name': 'قطع المعدات الثقيلة',
        'parts': {
            'hydraulic_pump': {
                'name_ar': 'مضخة هيدروليك',
                'name_en': 'Hydraulic Pump',
                'fits': [
                    'حفارات (Excavators)',
                    'لوادر (Loaders)',
                    'رافعات شوكية (Forklifts)',
                    'جريدرات (Graders)'
                ],
                'function': 'ضخ الزيت الهيدروليكي لتشغيل الأذرع والأنظمة',
                'symptoms_when_bad': [
                    'بطء في حركة الأذرع',
                    'صوت صفير من المضخة',
                    'ارتفاع حرارة الزيت الهيدروليكي',
                    'تسرب زيت',
                    'عدم الاستجابة للأوامر'
                ],
                'diagnostics': [
                    'فحص ضغط النظام (Pressure Test)',
                    'فحص التسريبات',
                    'فحص فلتر الهيدروليك',
                    'فحص مستوى الزيت'
                ],
                'common_brands': ['BOSCH', 'REXROTH', 'PARKER', 'SAUER-DANFOSS'],
                'price_range': '3,000-15,000₪ حسب الحجم',
                'critical': '⚠️ قطعة حرجة - توقف كامل للمعدة عند التلف!'
            },
            'track_link': {
                'name_ar': 'حلقة جنزير / سلسلة',
                'name_en': 'Track Link',
                'fits': [
                    'حفارات بجنزير',
                    'بلدوزرات',
                    'جريدرات'
                ],
                'function': 'حركة المعدة',
                'wear_signs': [
                    'تآكل في الأسنان',
                    'شقوق في المعدن',
                    'استطالة السلسلة'
                ],
                'replacement_interval': 'حسب ساعات العمل وطبيعة الأرض',
                'price_range': '150-500₪ للحلقة'
            }
        }
    }
}


# ====================================================================
# التوافق - أي قطعة لأي معدة
# ====================================================================

COMPATIBILITY_DATABASE = {
    'oil_filter_OC90': {
        'fits_vehicles': [
            'Toyota Corolla 2000-2010',
            'Honda Civic 2001-2005',
            'Nissan Sunny 2005-2012',
            'معظم السيارات اليابانية 1.6-2.0L'
        ],
        'alternative_numbers': ['W920/21', 'MANN W920/21', 'FRAM PH3593A']
    },
    
    'brake_pad_DB1234': {
        'fits_vehicles': [
            'Mercedes Sprinter 2006+',
            'VW Crafter 2006+',
            'بعض معدات CAT الصغيرة'
        ],
        'front_or_rear': 'أمامي',
        'note': 'تأكد من رقم الشاسيه (VIN) قبل الطلب'
    }
}


# ====================================================================
# دوال البحث الذكي عن القطع
# ====================================================================

def search_part_by_name(part_name: str) -> dict:
    """البحث عن قطعة بالاسم"""
    part_name_lower = part_name.lower()
    results = []
    
    for category_key, category_data in PARTS_KNOWLEDGE.items():
        for part_key, part_info in category_data.get('parts', {}).items():
            if (part_name_lower in part_info.get('name_ar', '').lower() or
                part_name_lower in part_info.get('name_en', '').lower()):
                results.append({
                    'category': category_data['name'],
                    'part_key': part_key,
                    'info': part_info
                })
    
    return {'query': part_name, 'results': results}


def search_part_by_number(part_number: str) -> dict:
    """البحث عن قطعة بالرقم"""
    part_number_upper = part_number.upper()
    
    for category_key, category_data in PARTS_KNOWLEDGE.items():
        for part_key, part_info in category_data.get('parts', {}).items():
            numbers = part_info.get('common_numbers', [])
            if any(part_number_upper in num.upper() for num in numbers):
                return {
                    'found': True,
                    'category': category_data['name'],
                    'part_key': part_key,
                    'info': part_info
                }
    
    # البحث في قاعدة التوافق
    if part_number_upper in [key.split('_')[-1] for key in COMPATIBILITY_DATABASE.keys()]:
        for compat_key, compat_data in COMPATIBILITY_DATABASE.items():
            if part_number_upper in compat_key.upper():
                return {
                    'found': True,
                    'compatibility': compat_data
                }
    
    return {'found': False, 'query': part_number}


def get_parts_for_vehicle(vehicle_model: str) -> list:
    """الحصول على القطع المناسبة لسيارة/معدة"""
    vehicle_lower = vehicle_model.lower()
    matching_parts = []
    
    for compat_key, compat_data in COMPATIBILITY_DATABASE.items():
        fits = compat_data.get('fits_vehicles', [])
        for fit in fits:
            if vehicle_lower in fit.lower():
                matching_parts.append({
                    'part_number': compat_key,
                    'fits': compat_data
                })
    
    return matching_parts


def explain_part_function(part_name: str) -> str:
    """شرح وظيفة قطعة بالتفصيل"""
    search_result = search_part_by_name(part_name)
    
    if search_result['results']:
        part_info = search_result['results'][0]['info']
        
        explanation = f"""🔧 **{part_info['name_ar']} ({part_info['name_en']})**

📝 **الوظيفة:**
{part_info.get('function', 'N/A')}

📦 **يركب على:**
"""
        for fit in part_info.get('fits', []):
            explanation += f"  • {fit}\n"
        
        if part_info.get('symptoms_when_bad'):
            explanation += "\n⚠️ **علامات التلف:**\n"
            for symptom in part_info['symptoms_when_bad']:
                explanation += f"  • {symptom}\n"
        
        if part_info.get('replacement_interval'):
            explanation += f"\n🔄 **فترة التبديل:** {part_info['replacement_interval']}\n"
        
        if part_info.get('price_range'):
            explanation += f"\n💰 **السعر المتوقع:** {part_info['price_range']}\n"
        
        return explanation
    
    return f"❌ لم أجد معلومات عن \"{part_name}\" - حاول اسم آخر أو رقم القطعة"

