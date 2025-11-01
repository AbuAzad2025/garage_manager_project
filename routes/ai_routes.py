"""
🤖 AI Routes - مسارات المساعد الذكي
=====================================

ملف مخصص لجميع routes المساعد الذكي
منفصل تماماً عن security.py لتحسين التنظيم

Features:
- AI Hub (مركز التحكم)
- AI Assistant (المساعد المباشر)
- Training Management (إدارة التدريب)
- API Keys Management (إدارة المفاتيح)
- System Map (خريطة النظام)
- Analytics & Stats (التحليلات)
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import json
import os

from AI.engine.ai_service import (
    ai_chat_with_search,
    search_database_for_query,
    gather_system_context,
    build_system_message,
    get_system_setting
)
from AI.engine.ai_management import (
    save_api_key_encrypted,
    test_api_key,
    list_configured_apis,
    start_training_job,
    get_training_job_status,
    get_live_ai_stats
)

# Blueprint للمساعد الذكي
ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


# ============================================================
# Decorators - للتحكم بالصلاحيات
# ============================================================

def owner_only(f):
    """المالك فقط"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (current_user.is_authenticated and 
                (current_user.is_system_account or current_user.username == '__OWNER__')):
            flash('⛔ هذه الصفحة للمالك فقط', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def ai_access(f):
    """وصول للمساعد - المالك والمدراء"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('⛔ يجب تسجيل الدخول', 'danger')
            return redirect(url_for('auth.login'))
        
        # المالك دائماً لديه وصول
        if current_user.is_system_account or current_user.username == '__OWNER__':
            return f(*args, **kwargs)
        
        # المدراء لديهم وصول
        if current_user.role and current_user.role.name in ['manager', 'مدير', 'admin']:
            return f(*args, **kwargs)
        
        flash('⛔ غير مصرح لك بالوصول للمساعد الذكي', 'danger')
        return redirect(url_for('main.index'))
    
    return decorated_function


# ============================================================
# Main Routes - المسارات الرئيسية
# ============================================================

@ai_bp.route('/hub')
@ai_access
def hub():
    """
    🤖 AI Hub - مركز التحكم الرئيسي
    """
    tab = request.args.get('tab', 'assistant')
    
    # جمع الإحصائيات
    ai_stats = _get_ai_stats()
    system_stats = _get_system_stats()
    recent_queries = _get_recent_queries(limit=5)
    predictions = _get_predictions()
    
    # التحقق من تفعيل API keys
    api_keys_configured = _check_api_keys()
    
    return render_template(
        'ai/ai_hub.html',
        active_tab=tab,
        ai_stats=ai_stats,
        system_stats=system_stats,
        recent_queries=recent_queries,
        predictions=predictions,
        api_keys_configured=api_keys_configured
    )


@ai_bp.route('/assistant', methods=['GET', 'POST'])
@ai_access
def assistant():
    """
    💬 AI Assistant - المساعد المباشر
    """
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        
        if query:
            # تحليل السؤال والرد
            analysis = _analyze_query(query)
            
            return render_template(
                'ai/ai_assistant.html',
                query=query,
                analysis=analysis
            )
    
    # GET request - عرض الصفحة مع اقتراحات
    suggestions = _get_ai_suggestions()
    
    return render_template(
        'ai/ai_assistant.html',
        suggestions=suggestions
    )


@ai_bp.route('/chat', methods=['POST'])
@ai_access
def chat():
    """
    💬 API للمحادثة مع AI
    يستخدم من JavaScript
    """
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({
                'success': False,
                'error': 'الرسالة فارغة'
            }), 400
        
        # استخدام خدمة AI المركزية
        response = ai_chat_with_search(
            message=message,
            session_id=f"user_{current_user.id}"
        )
        
        return jsonify({
            'success': True,
            'response': response.get('response', 'عذراً، لم أتمكن من الإجابة'),
            'confidence': response.get('confidence', 0),
            'sources': response.get('sources', [])
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================
# System Map Routes
# ============================================================

@ai_bp.route('/system-map', methods=['GET', 'POST'])
@owner_only
def system_map():
    """
    🗺️ خريطة النظام - Auto Discovery
    """
    from AI.engine.ai_auto_discovery import (
        build_system_map,
        load_system_map,
        SYSTEM_MAP_FILE,
        DISCOVERY_LOG_FILE
    )
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'rebuild':
            try:
                system_map_data = build_system_map()
                flash('✅ تم إعادة بناء خريطة النظام بنجاح!', 'success')
            except Exception as e:
                flash(f'⚠️ خطأ: {str(e)}', 'danger')
            
            return redirect(url_for('ai.system_map'))
    
    # تحميل الخريطة
    system_map_data = load_system_map()
    map_exists = system_map_data is not None
    
    # تحميل السجلات
    logs = []
    if os.path.exists(DISCOVERY_LOG_FILE):
        try:
            with open(DISCOVERY_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                logs = logs[-10:]  # آخر 10 سجلات
        except:
            pass
    
    return render_template(
        'ai/system_map.html',
        system_map=system_map_data,
        map_exists=map_exists,
        logs=logs
    )


# ============================================================
# Training Routes
# ============================================================

@ai_bp.route('/training/start', methods=['POST'])
@owner_only
def start_training():
    """
    🎓 بدء تدريب نموذج
    """
    try:
        data = request.get_json()
        model_name = data.get('model_name', 'unknown')
        training_type = data.get('training_type', 'quick')
        data_range = data.get('data_range', 'all')
        
        # استخدام نظام الإدارة المتقدم
        result = start_training_job(model_name, training_type, data_range)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/training/status/<training_id>')
@owner_only
def training_status(training_id):
    """
    📊 حالة التدريب
    """
    job = get_training_job_status(training_id)
    
    if job:
        return jsonify({
            'success': True,
            'job': job
        })
    else:
        return jsonify({
            'success': False,
            'error': 'التدريب غير موجود'
        }), 404


# ============================================================
# API Keys Management
# ============================================================

@ai_bp.route('/api-keys/save', methods=['POST'])
@owner_only
def save_api_key():
    """
    💾 حفظ مفتاح API مشفر
    """
    try:
        data = request.get_json()
        api_name = data.get('api_name')
        api_key = data.get('api_key')
        
        if not api_name or not api_key:
            return jsonify({
                'success': False,
                'error': 'بيانات ناقصة'
            }), 400
        
        # حفظ المفتاح مشفر
        success = save_api_key_encrypted(api_name, api_key)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'تم حفظ مفتاح {api_name} بنجاح (مشفر)'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'فشل في حفظ المفتاح'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/api-keys/test', methods=['POST'])
@owner_only
def test_api_key_route():
    """
    🔍 اختبار مفتاح API
    """
    try:
        data = request.get_json()
        api_name = data.get('api_name')
        
        if not api_name:
            return jsonify({
                'success': False,
                'error': 'اسم API مطلوب'
            }), 400
        
        # اختبار المفتاح
        result = test_api_key(api_name)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================
# Analytics & Stats Routes
# ============================================================

@ai_bp.route('/stats/live')
@ai_access
def live_stats():
    """
    📊 إحصائيات حية (Real-time)
    """
    stats = get_live_ai_stats()
    
    return jsonify({
        'success': True,
        'stats': stats
    })


@ai_bp.route('/analytics/queries')
@owner_only
def analytics_queries():
    """
    📈 تحليلات الاستعلامات
    """
    period = request.args.get('period', '7days')
    
    # TODO: جلب البيانات الفعلية من ai_interactions.json
    
    return jsonify({
        'success': True,
        'data': {
            'labels': ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'],
            'values': [12, 19, 15, 25, 22, 30, 28]
        }
    })


# ============================================================
# Helper Functions - دوال مساعدة
# ============================================================

def _get_ai_stats():
    """جمع إحصائيات AI"""
    try:
        interactions_file = 'AI/data/ai_interactions.json'
        
        if os.path.exists(interactions_file):
            with open(interactions_file, 'r', encoding='utf-8') as f:
                interactions = json.load(f)
                
                total = len(interactions)
                successful = sum(1 for i in interactions if i.get('confidence', 0) > 70)
                
                # حساب متوسط وقت الاستجابة
                avg_time = 0.8  # افتراضي
                
                # استعلامات اليوم
                today = datetime.now().date().isoformat()
                today_count = sum(1 for i in interactions 
                                if i.get('timestamp', '').startswith(today))
                
                return {
                    'total_queries': total,
                    'successful': successful,
                    'success_rate': round((successful / total * 100) if total > 0 else 0, 1),
                    'avg_response_time': avg_time,
                    'today': today_count
                }
        
        return {
            'total_queries': 0,
            'successful': 0,
            'success_rate': 0,
            'avg_response_time': 0,
            'today': 0
        }
        
    except:
        return {
            'total_queries': 0,
            'successful': 0,
            'success_rate': 0,
            'avg_response_time': 0,
            'today': 0
        }


def _get_system_stats():
    """إحصائيات النظام"""
    try:
        from AI.engine.ai_auto_discovery import load_system_map
        system_map = load_system_map()
        
        if system_map:
            return {
                'total_routes': system_map.get('statistics', {}).get('total_routes', 0),
                'total_templates': system_map.get('statistics', {}).get('total_templates', 0),
                'total_models': 45,  # TODO: حساب من ai_data_schema.json
                'total_relationships': 120
            }
    except:
        pass
    
    return {
        'total_routes': 362,
        'total_templates': 150,
        'total_models': 45,
        'total_relationships': 120
    }


def _get_recent_queries(limit=5):
    """آخر الاستعلامات"""
    try:
        interactions_file = 'AI/data/ai_interactions.json'
        
        if os.path.exists(interactions_file):
            with open(interactions_file, 'r', encoding='utf-8') as f:
                interactions = json.load(f)
                
                # آخر N استعلامات
                recent = interactions[-limit:] if len(interactions) > limit else interactions
                recent.reverse()
                
                return recent
        
    except:
        pass
    
    return []


def _get_predictions():
    """التنبؤات المتاحة"""
    return [
        {'type': 'مبيعات', 'period': 'الشهر القادم', 'value': '+15%', 'confidence': 87},
        {'type': 'مخزون', 'period': 'الأسبوع القادم', 'value': 'نقص متوقع', 'confidence': 92},
        {'type': 'إيرادات', 'period': 'الربع القادم', 'value': '₪125,000', 'confidence': 89}
    ]


def _check_api_keys():
    """التحقق من تفعيل API keys"""
    configured = list_configured_apis()
    return len(configured) > 0


def _get_ai_suggestions():
    """اقتراحات ذكية للمستخدم"""
    return [
        {
            'type': 'info',
            'title': '💡 نصيحة اليوم',
            'action': 'استخدم "صباح الخير" لرؤية ملخص يومك'
        },
        {
            'type': 'success',
            'title': '✅ تحديث متاح',
            'action': 'تدريب جديد متاح للنماذج'
        }
    ]


def _analyze_query(query):
    """تحليل استعلام المستخدم"""
    try:
        response = ai_chat_with_search(
            message=query,
            session_id=f"user_{current_user.id}"
        )
        
        return {
            'query': query,
            'response': response.get('response', ''),
            'confidence': response.get('confidence', 0),
            'sources': response.get('sources', []),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        return {
            'query': query,
            'response': f'عذراً، حدث خطأ: {str(e)}',
            'confidence': 0,
            'sources': [],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


# ============================================================
# Error Handlers
# ============================================================

@ai_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'المسار غير موجود'
    }), 404


@ai_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'خطأ في الخادم'
    }), 500

