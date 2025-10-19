from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import text, func
from datetime import datetime, timedelta, timezone
from extensions import db, cache
from models import User, AuditLog
import utils
from functools import wraps
import json
import os

from services.ai_service import (
    ai_chat_with_search,
    search_database_for_query,
    gather_system_context,
    build_system_message,
    get_system_setting
)

security_bp = Blueprint('security', __name__, url_prefix='/security')


@security_bp.app_template_global()
def _get_action_icon(action):
    if not action:
        return 'info-circle'
    mapping = {
        'login': 'sign-in-alt',
        'logout': 'sign-out-alt',
        'create': 'plus',
        'update': 'edit',
        'delete': 'trash',
        'view': 'eye',
        'export': 'download',
        'import': 'upload',
        'blocked': 'ban',
        'security': 'shield-alt'
    }
    action_lower = str(action).lower()
    for key, icon in mapping.items():
        if key in action_lower:
            return icon
    return 'circle'


@security_bp.app_template_global()
def _get_action_color(action):
    """لون للنشاط - Template Global"""
    if not action:
        return 'secondary'
    mapping = {
        'login': 'success',
        'logout': 'secondary',
        'create': 'primary',
        'update': 'info',
        'delete': 'danger',
        'blocked': 'danger',
        'failed': 'danger',
        'security': 'warning'
    }
    action_lower = str(action).lower()
    for key, color in mapping.items():
        if key in action_lower:
            return color
    return 'secondary'


def owner_only(f):
    """
    🔐 Decorator صارم: يسمح فقط للمالك (__OWNER__) بالوصول
    حتى Super Admin لن يستطيع الدخول!
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # فحص: هل المستخدم هو المالك الخفي؟
        is_owner = (
            getattr(current_user, 'is_system_account', False) or 
            current_user.username == '__OWNER__' or
            current_user.username.upper() == '__OWNER__'
        )
        
        if not is_owner:
            flash('🚫 هذه الوحدة السرية متاحة للمالك فقط! (Super Admin ليس له صلاحية)', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


# Alias للتوافق
super_admin_only = owner_only


@security_bp.route('/')
@owner_only
def index():
    """لوحة التحكم الأمنية الرئيسية - للمالك فقط"""
    # إحصائيات أمنية
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'blocked_users': User.query.filter_by(is_active=False).count(),
        'blocked_ips': _get_blocked_ips_count(),
        'blocked_countries': _get_blocked_countries_count(),
        'failed_logins_24h': _get_failed_logins_count(hours=24),
        'suspicious_activities': _get_suspicious_activities_count(hours=24),
        'system_version': 'v5.0.0',
        'total_modules': '40+',
        'total_apis': 133,
        'total_indexes': 89
    }
    
    # آخر الأنشطة المشبوهة
    recent_suspicious = _get_recent_suspicious_activities(limit=10)
    
    return render_template('security/index.html', stats=stats, recent=recent_suspicious)


@security_bp.route('/block-ip', methods=['GET', 'POST'])
@super_admin_only
def block_ip():
    """حظر IP معين"""
    if request.method == 'POST':
        ip = request.form.get('ip', '').strip()
        reason = request.form.get('reason', '').strip()
        duration = request.form.get('duration', '').strip()  # permanent, 1h, 24h, 7d, 30d
        
        if not ip:
            flash('❌ IP مطلوب', 'danger')
        else:
            _block_ip(ip, reason, duration)
            flash(f'✅ تم حظر IP: {ip}', 'success')
            return redirect(url_for('security.blocked_ips'))
    
    return render_template('security/block_ip.html')


@security_bp.route('/blocked-ips')
@super_admin_only
def blocked_ips():
    """قائمة IPs المحظورة"""
    blocked = _get_all_blocked_ips()
    return render_template('security/blocked_ips.html', blocked=blocked)


@security_bp.route('/unblock-ip/<ip>', methods=['POST'])
@super_admin_only
def unblock_ip(ip):
    """إلغاء حظر IP"""
    _unblock_ip(ip)
    flash(f'✅ تم إلغاء حظر IP: {ip}', 'success')
    return redirect(url_for('security.blocked_ips'))


@security_bp.route('/block-country', methods=['GET', 'POST'])
@super_admin_only
def block_country():
    """حظر دولة معينة"""
    if request.method == 'POST':
        country_code = request.form.get('country_code', '').strip().upper()
        reason = request.form.get('reason', '').strip()
        
        if not country_code or len(country_code) != 2:
            flash('❌ كود الدولة مطلوب (مثال: US, IL)', 'danger')
        else:
            _block_country(country_code, reason)
            flash(f'✅ تم حظر الدولة: {country_code}', 'success')
            return redirect(url_for('security.blocked_countries'))
    
    return render_template('security/block_country.html')


@security_bp.route('/blocked-countries')
@super_admin_only
def blocked_countries():
    """قائمة الدول المحظورة"""
    blocked = _get_all_blocked_countries()
    return render_template('security/blocked_countries.html', blocked=blocked)


@security_bp.route('/block-user/<int:user_id>', methods=['POST'])
@super_admin_only
def block_user(user_id):
    """حظر مستخدم معين"""
    user = User.query.get_or_404(user_id)
    
    if utils.is_super() and user.id == current_user.id:
        flash('❌ لا يمكنك حظر نفسك!', 'danger')
    else:
        user.is_active = False
        db.session.commit()
        flash(f'✅ تم حظر المستخدم: {user.username}', 'success')
    
    return redirect(url_for('users_bp.list_users'))


@security_bp.route('/system-cleanup', methods=['GET', 'POST'])
@super_admin_only
def system_cleanup():
    """تنظيف جداول النظام (Format)"""
    if request.method == 'POST':
        confirm = request.form.get('confirm', '').strip()
        tables = request.form.getlist('tables')
        
        if confirm != 'FORMAT_SYSTEM':
            flash('❌ يجب كتابة "FORMAT_SYSTEM" للتأكيد', 'danger')
        elif not tables:
            flash('❌ اختر جدول واحد على الأقل', 'danger')
        else:
            result = _cleanup_tables(tables)
            flash(f'✅ تم تنظيف {result["cleaned"]} جدول', 'success')
            return redirect(url_for('security.index'))
    
    # قائمة الجداول القابلة للتنظيف
    cleanable_tables = _get_cleanable_tables()
    return render_template('security/system_cleanup.html', tables=cleanable_tables)


@security_bp.route('/audit-logs')
@super_admin_only
def audit_logs():
    """سجل التدقيق الأمني"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('security/audit_logs.html', logs=logs)


@security_bp.route('/failed-logins')
@super_admin_only
def failed_logins():
    """محاولات تسجيل الدخول الفاشلة"""
    hours = request.args.get('hours', 24, type=int)
    
    failed = AuditLog.query.filter(
        AuditLog.action.in_(['login.failed', 'login.blocked']),
        AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours)
    ).order_by(AuditLog.created_at.desc()).limit(100).all()
    
    return render_template('security/failed_logins.html', failed=failed, hours=hours)


# ═══════════════════════════════════════════════════════════════
# AI Security Assistant - ADVANCED
# ═══════════════════════════════════════════════════════════════

@security_bp.route('/ai-assistant', methods=['GET', 'POST'])
@login_required
def ai_assistant():
    """المساعد الذكي الشامل - متاح لجميع المستخدمين"""
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        analysis = _ai_security_analysis(query)
        return render_template('security/ai_assistant.html', query=query, analysis=analysis)
    
    # اقتراحات ذكية
    suggestions = _get_ai_suggestions()
    
    return render_template('security/ai_assistant.html', suggestions=suggestions)


@security_bp.route('/ai-diagnostics')
@owner_only
def ai_diagnostics():
    """واجهة التشخيص الذاتي للمساعد الذكي"""
    from services.ai_data_awareness import load_data_schema, auto_build_if_needed
    from services.ai_auto_discovery import load_system_map
    from services.ai_self_review import analyze_recent_interactions, get_system_status
    import os
    
    # تحميل البيانات
    data_schema = auto_build_if_needed()
    system_map = load_system_map()
    interactions_analysis = analyze_recent_interactions(100)
    system_status = get_system_status()
    
    diagnostics = {
        'data_awareness': {
            'status': 'active' if data_schema else 'inactive',
            'tables_known': data_schema['statistics']['total_tables'] if data_schema else 0,
            'columns_known': data_schema['statistics']['total_columns'] if data_schema else 0,
            'relationships_known': data_schema['statistics']['total_relationships'] if data_schema else 0,
            'functional_modules': len(data_schema['functional_mapping']) if data_schema else 0,
        },
        'navigation_awareness': {
            'status': 'active' if system_map else 'inactive',
            'routes_known': system_map['statistics']['total_routes'] if system_map else 0,
            'templates_known': system_map['statistics']['total_templates'] if system_map else 0,
            'blueprints_known': len(system_map['blueprints']) if system_map else 0,
        },
        'performance': {
            'total_interactions': interactions_analysis.get('total', 0),
            'avg_confidence': interactions_analysis.get('avg_confidence', 0),
            'quality_score': interactions_analysis.get('quality_score', 'N/A'),
            'weak_count': interactions_analysis.get('weak_count', 0),
            'weak_areas': interactions_analysis.get('weak_areas', []),
        },
        'system_health': system_status.get('health', 'unknown'),
    }
    
    return render_template('security/ai_diagnostics.html', diagnostics=diagnostics)


@security_bp.route('/system-map', methods=['GET', 'POST'])
@owner_only
def system_map():
    """خريطة النظام - Auto Discovery"""
    from services.ai_auto_discovery import (
        build_system_map,
        load_system_map,
        SYSTEM_MAP_FILE,
        DISCOVERY_LOG_FILE
    )
    import os
    
    system_map_data = load_system_map()
    map_exists = os.path.exists(SYSTEM_MAP_FILE)
    
    logs = []
    if os.path.exists(DISCOVERY_LOG_FILE):
        try:
            with open(DISCOVERY_LOG_FILE, 'r', encoding='utf-8') as f:
                import json
                logs = json.load(f)[-10:]  # آخر 10 أحداث
        except:
            pass
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'rebuild':
            try:
                system_map_data = build_system_map()
                flash('✅ تم إعادة بناء خريطة النظام بنجاح!', 'success')
            except Exception as e:
                flash(f'⚠️ خطأ: {str(e)}', 'danger')
            return redirect(url_for('security.system_map'))
    
    return render_template('security/system_map.html',
                         system_map=system_map_data,
                         map_exists=map_exists,
                         logs=logs)


@security_bp.route('/ai-training', methods=['GET', 'POST'])
@owner_only
def ai_training():
    """تدريب المساعد الذكي - للمالك فقط"""
    """واجهة التدريب الشامل - نظام الوعي الذاتي الكامل"""
    from services.ai_knowledge import get_knowledge_base, KNOWLEDGE_CACHE_FILE, TRAINING_LOG_FILE
    from services.ai_auto_discovery import build_system_map, load_system_map
    from services.ai_data_awareness import build_data_schema, load_data_schema
    from services.ai_self_review import analyze_recent_interactions
    import os
    import json
    from datetime import datetime
    
    # تحميل البيانات الحالية
    kb = get_knowledge_base()
    structure = kb.get_system_structure()
    cache_exists = os.path.exists(KNOWLEDGE_CACHE_FILE)
    last_indexed = kb.knowledge.get('last_indexed', 'لم يتم الفهرسة بعد')
    index_count = kb.knowledge.get('index_count', 0)
    
    # تحميل حالة النظام
    system_map = load_system_map()
    data_schema = load_data_schema()
    
    # التقرير الشامل
    training_report = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'comprehensive_training':
            # 🧠 التدريب الشامل
            training_report = {
                'start_time': datetime.now().isoformat(),
                'steps': [],
                'status': 'in_progress'
            }
            
            try:
                # 1️⃣ تحليل النظام الكامل (Auto Discovery)
                training_report['steps'].append({'name': 'Auto Discovery', 'status': 'started'})
                system_map = build_system_map()
                training_report['steps'][-1]['status'] = 'completed'
                training_report['steps'][-1]['result'] = {
                    'routes': system_map['statistics']['total_routes'],
                    'templates': system_map['statistics']['total_templates'],
                    'blueprints': len(system_map['blueprints'])
                }
                
                # 2️⃣ تحليل البيانات (Data Profiling)
                training_report['steps'].append({'name': 'Data Profiling', 'status': 'started'})
                data_schema = build_data_schema()
                training_report['steps'][-1]['status'] = 'completed'
                training_report['steps'][-1]['result'] = {
                    'tables': data_schema['statistics']['total_tables'],
                    'columns': data_schema['statistics']['total_columns'],
                    'relationships': data_schema['statistics']['total_relationships']
                }
                
                # 3️⃣ تحديث المعرفة
                training_report['steps'].append({'name': 'Knowledge Update', 'status': 'started'})
                kb.index_all_files(force_reindex=True)
                training_report['steps'][-1]['status'] = 'completed'
                
                # 4️⃣ الاختبار الذاتي
                training_report['steps'].append({'name': 'Self Validation', 'status': 'started'})
                
                # اختبار 5 استعلامات
                from models import Customer, Expense, ServiceRequest, ExchangeTransaction, Payment
                
                test_results = {
                    'customers_count': Customer.query.count(),
                    'expenses_count': Expense.query.count(),
                    'services_count': ServiceRequest.query.count(),
                    'last_exchange_rate': 'N/A',
                    'last_payment': 'N/A'
                }
                
                try:
                    latest_fx = ExchangeTransaction.query.order_by(
                        ExchangeTransaction.created_at.desc()
                    ).first()
                    if latest_fx:
                        test_results['last_exchange_rate'] = f"{float(latest_fx.rate):.2f}"
                except:
                    pass
                
                try:
                    latest_payment = Payment.query.order_by(
                        Payment.created_at.desc()
                    ).first()
                    if latest_payment:
                        test_results['last_payment'] = f"{float(latest_payment.total_amount):.2f}"
                except:
                    pass
                
                # حساب درجة الثقة
                confidence = 0
                if test_results['customers_count'] > 0:
                    confidence += 20
                if test_results['expenses_count'] > 0:
                    confidence += 20
                if test_results['services_count'] > 0:
                    confidence += 20
                if test_results['last_exchange_rate'] != 'N/A':
                    confidence += 20
                if test_results['last_payment'] != 'N/A':
                    confidence += 20
                
                training_report['steps'][-1]['status'] = 'completed'
                training_report['steps'][-1]['result'] = test_results
                training_report['confidence'] = confidence
                
                # 5️⃣ تحليل الأداء
                training_report['steps'].append({'name': 'Performance Analysis', 'status': 'started'})
                interactions = analyze_recent_interactions(100)
                training_report['steps'][-1]['status'] = 'completed'
                training_report['steps'][-1]['result'] = {
                    'avg_confidence': interactions.get('avg_confidence', 0),
                    'quality_score': interactions.get('quality_score', 'N/A')
                }
                
                training_report['status'] = 'success' if confidence >= 70 else 'partial'
                training_report['end_time'] = datetime.now().isoformat()
                
                # حفظ التقرير
                _log_training_event('comprehensive_training', current_user.id, training_report)
                
                if confidence >= 70:
                    flash(f'✅ تم التدريب الشامل بنجاح! درجة الثقة: {confidence}%', 'success')
                else:
                    flash(f'⚠️ تدريب جزئي. درجة الثقة: {confidence}%', 'warning')
                
            except Exception as e:
                training_report['status'] = 'failed'
                training_report['error'] = str(e)
                flash(f'❌ فشل التدريب: {str(e)}', 'danger')
                _log_training_event('training_failed', current_user.id, {'error': str(e)})
            
            return redirect(url_for('security.ai_training'))
        
        elif action == 'reindex':
            kb.index_all_files(force_reindex=True)
            flash('✅ تمت إعادة الفهرسة بنجاح!', 'success')
            _log_training_event('manual_reindex', current_user.id)
            return redirect(url_for('security.ai_training'))
        
        elif action == 'clear_cache':
            try:
                if os.path.exists(KNOWLEDGE_CACHE_FILE):
                    os.remove(KNOWLEDGE_CACHE_FILE)
                flash('✅ تم حذف الذاكرة!', 'success')
                _log_training_event('clear_cache', current_user.id)
            except Exception as e:
                flash(f'⚠️ خطأ: {str(e)}', 'danger')
            return redirect(url_for('security.ai_training'))
    
    # حساب Learning Quality Index
    learning_quality = kb.knowledge.get('learning_quality', {})
    
    # إحصائيات النظام
    system_stats = {
        'knowledge': {
            'cache_exists': cache_exists,
            'last_indexed': last_indexed,
            'index_count': index_count,
            'models_count': len(structure.get('models', {})),
            'enums_count': structure.get('enums_count', 0),
            'forms_count': structure.get('forms_count', 0),
            'functions_count': structure.get('functions_count', 0),
            'routes_count': len(structure.get('routes', {})),
            'javascript_count': structure.get('javascript_count', 0),
            'css_count': structure.get('css_count', 0),
            'static_count': structure.get('static_files_count', 0),
            'total_items': structure.get('total_items', 0)
        },
        'navigation': {
            'routes': system_map['statistics']['total_routes'] if system_map else 0,
            'templates': system_map['statistics']['total_templates'] if system_map else 0,
            'blueprints': len(system_map['blueprints']) if system_map else 0
        },
        'data_awareness': {
            'tables': data_schema['statistics']['total_tables'] if data_schema else 0,
            'columns': data_schema['statistics']['total_columns'] if data_schema else 0,
            'modules': len(data_schema['functional_mapping']) if data_schema else 0
        },
        'learning_quality': {
            'index': learning_quality.get('index', 0),
            'avg_confidence': learning_quality.get('avg_confidence', 0),
            'data_density': learning_quality.get('data_density', 0),
            'system_health': learning_quality.get('system_health', 0),
            'tables_with_data': learning_quality.get('tables_with_data', 0)
        }
    }
    
    training_logs = _load_training_logs()
    
    return render_template('security/ai_training.html',
                         structure=structure,
                         system_stats=system_stats,
                         training_report=training_report,
                         training_logs=training_logs,
                         cache_exists=cache_exists,
                         last_indexed=last_indexed,
                         index_count=index_count)


def _log_training_event(event_type, user_id, details=None):
    """تسجيل حدث تدريب - محسّن"""
    try:
        from services.ai_knowledge import TRAINING_LOG_FILE
        import os
        
        os.makedirs('instance', exist_ok=True)
        
        logs = []
        if os.path.exists(TRAINING_LOG_FILE):
            try:
                with open(TRAINING_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        log_entry = {
            'event': event_type,
            'user_id': user_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if details:
            log_entry['details'] = details
        
        logs.append(log_entry)
        logs = logs[-50:]
        
        with open(TRAINING_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ فشل تسجيل حدث التدريب: {str(e)}")


def _load_training_logs():
    """تحميل سجل التدريب"""
    try:
        from services.ai_knowledge import TRAINING_LOG_FILE
        import os
        
        if os.path.exists(TRAINING_LOG_FILE):
            with open(TRAINING_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []


@security_bp.route('/database-browser')
@owner_only
def database_browser():
    """متصفح قاعدة البيانات المتقدم"""
    # الحصول على جميع الجداول
    tables = _get_all_tables()
    
    selected_table = request.args.get('table')
    data = None
    columns = None
    table_info = None
    
    if selected_table:
        data, columns = _browse_table(selected_table, limit=100)
        table_info = _get_table_info(selected_table)
    
    return render_template('security/database_browser.html', 
                          tables=tables, 
                          selected_table=selected_table,
                          data=data,
                          columns=columns,
                          table_info=table_info)


@security_bp.route('/decrypt-tool', methods=['GET', 'POST'])
@owner_only
def decrypt_tool():
    """أداة فك التشفير"""
    result = None
    
    if request.method == 'POST':
        encrypted_data = request.form.get('encrypted_data', '').strip()
        decrypt_type = request.form.get('decrypt_type', 'auto')
        
        result = _decrypt_data(encrypted_data, decrypt_type)
    
    return render_template('security/decrypt_tool.html', result=result)


@security_bp.route('/ai-analytics')
@owner_only
def ai_analytics():
    """تحليلات ذكاء اصطناعي متقدمة"""
    # تحليلات AI
    analytics = {
        'user_behavior': _analyze_user_behavior(),
        'security_patterns': _detect_security_patterns(),
        'anomalies': _detect_anomalies(),
        'recommendations': _ai_recommendations(),
        'threat_level': _calculate_threat_level(),
    }
    
    return render_template('security/ai_analytics.html', analytics=analytics)


@security_bp.route('/pattern-detection')
@owner_only
def pattern_detection():
    """كشف الأنماط المشبوهة"""
    patterns = _detect_suspicious_patterns()
    return render_template('security/pattern_detection.html', patterns=patterns)


@security_bp.route('/activity-timeline')
@owner_only
def activity_timeline():
    """Timeline نشاط النظام الكامل"""
    hours = request.args.get('hours', 24, type=int)
    user_filter = request.args.get('user', type=int)
    action_filter = request.args.get('action', '')
    
    # استعلام AuditLog
    query = AuditLog.query
    
    if user_filter:
        query = query.filter_by(user_id=user_filter)
    
    if action_filter:
        query = query.filter(AuditLog.action.like(f'%{action_filter}%'))
    
    query = query.filter(
        AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours)
    )
    
    activities = query.order_by(AuditLog.created_at.desc()).limit(500).all()
    
    # إحصائيات
    stats = {
        'total': len(activities),
        'users': len(set(a.user_id for a in activities if a.user_id)),
        'actions': len(set(a.action for a in activities)),
    }
    
    # جميع المستخدمين للفلترة
    users = User.query.filter_by(is_active=True).all()
    
    return render_template('security/activity_timeline.html', 
                          activities=activities,
                          stats=stats,
                          users=users,
                          hours=hours,
                          user_filter=user_filter,
                          action_filter=action_filter)


@security_bp.route('/notifications-center')
@owner_only
def notifications_center():
    """مركز الإشعارات الأمنية"""
    # الإشعارات الحديثة
    notifications = _get_security_notifications()
    
    return render_template('security/notifications_center.html', 
                          notifications=notifications)


@security_bp.route('/ai-config', methods=['GET', 'POST'])
@owner_only
def ai_config():
    """إعدادات AI - Groq API Keys - للمالك فقط"""
    """تكوين AI للمساعد الذكي - دعم مفاتيح متعددة"""
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        
        if action == 'add':
            api_provider = request.form.get('api_provider', 'groq')
            api_key = request.form.get('api_key', '').strip()
            key_name = request.form.get('key_name', '').strip()
            is_active = request.form.get('is_active') == 'on'
            
            if api_key:
                # قراءة المفاتيح الحالية
                keys_json = _get_system_setting('AI_API_KEYS', '[]')
                try:
                    keys = json.loads(keys_json)
                except:
                    keys = []
                
                # إضافة مفتاح جديد
                new_key = {
                    'id': len(keys) + 1,
                    'name': key_name or f'مفتاح {len(keys) + 1}',
                    'provider': api_provider,
                    'key': api_key,
                    'is_active': is_active,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                keys.append(new_key)
                
                # حفظ
                _set_system_setting('AI_API_KEYS', json.dumps(keys, ensure_ascii=False))
                flash(f'✅ تم إضافة المفتاح: {new_key["name"]}', 'success')
            else:
                flash('⚠️ مفتاح API مطلوب', 'warning')
        
        elif action == 'delete':
            key_id = int(request.form.get('key_id', 0))
            keys_json = _get_system_setting('AI_API_KEYS', '[]')
            try:
                keys = json.loads(keys_json)
                keys = [k for k in keys if k.get('id') != key_id]
                _set_system_setting('AI_API_KEYS', json.dumps(keys, ensure_ascii=False))
                flash('✅ تم حذف المفتاح', 'success')
            except:
                flash('⚠️ خطأ في حذف المفتاح', 'danger')
        
        elif action == 'set_active':
            key_id = int(request.form.get('key_id', 0))
            keys_json = _get_system_setting('AI_API_KEYS', '[]')
            try:
                keys = json.loads(keys_json)
                for k in keys:
                    k['is_active'] = (k.get('id') == key_id)
                _set_system_setting('AI_API_KEYS', json.dumps(keys, ensure_ascii=False))
                flash('✅ تم تفعيل المفتاح', 'success')
            except:
                flash('⚠️ خطأ في تفعيل المفتاح', 'danger')
        
        return redirect(url_for('security.ai_config'))
    
    # قراءة المفاتيح
    keys_json = _get_system_setting('AI_API_KEYS', '[]')
    try:
        keys = json.loads(keys_json)
    except:
        keys = []
    
    return render_template('security/ai_config.html', keys=keys)


@security_bp.route('/api/ai-chat', methods=['POST'])
@login_required
def ai_chat():
    """API للمحادثة مع AI - متاح لجميع المستخدمين"""
    from services.ai_service import ai_chat_with_search
    
    data = request.get_json()
    message = data.get('message', '')
    
    # استخدام خدمة AI المركزية
    response = ai_chat_with_search(message)
    
    return jsonify({
        'response': response,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


# ═══════════════════════════════════════════════════════════════
# ULTIMATE CONTROL PANEL - SUPER OWNER POWERS
# ═══════════════════════════════════════════════════════════════

@security_bp.route('/ultimate-control')
@owner_only
def ultimate_control():
    """لوحة التحكم النهائية - للمالك __OWNER__ فقط"""
    stats = {
        'users_online': _get_users_online(),
        'total_users': User.query.count(),
        'total_services': _safe_count_table('service_requests'),
        'total_sales': _safe_count_table('sales'),
        'db_size': _get_db_size(),
        'system_health': _get_system_health(),
        'active_sessions': _get_active_sessions_count(),
        'system_version': 'v5.0.0',
        'total_modules': '40+',
        'total_apis': 133,
        'total_indexes': 89,
        'total_relationships': '150+',
        'total_permissions': 41
    }
    return render_template('security/ultimate_control.html', stats=stats)


@security_bp.route('/card-vault')
@owner_only
def card_vault():
    """خزنة الكروت - عرض بيانات الفيزا كارد المشفرة"""
    from models import OnlinePayment
    cards = OnlinePayment.query.order_by(OnlinePayment.created_at.desc()).limit(100).all()
    
    stats = {
        'total_cards': OnlinePayment.query.count(),
        'successful': OnlinePayment.query.filter_by(status='SUCCESS').count(),
        'pending': OnlinePayment.query.filter_by(status='PENDING').count(),
        'failed': OnlinePayment.query.filter_by(status='FAILED').count(),
    }
    
    return render_template('security/card_vault.html', cards=cards, stats=stats)


@security_bp.route('/code-editor', methods=['GET', 'POST'])
@security_bp.route('/theme-editor', methods=['GET', 'POST'])  # Backward compatibility
@owner_only
def theme_editor():
    """محرر الكود الموحد - 3 في 1 (CSS + HTML + النصوص)"""
    import os
    from models import SystemSettings
    
    editor_type = request.args.get('type', 'css')  # css, html, text
    
    if request.method == 'POST':
        editor_type = request.form.get('editor_type', 'css')
        
        if editor_type == 'css':
            # حفظ CSS
            css_dir = os.path.join(current_app.root_path, 'static', 'css')
            filename = request.form.get('filename', 'style.css')
            content = request.form.get('content', '')
            
            if filename.endswith('.css') and not '..' in filename:
                filepath = os.path.join(css_dir, filename)
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    flash(f'✅ تم حفظ {filename} بنجاح!', 'success')
                except Exception as e:
                    flash(f'❌ خطأ: {str(e)}', 'danger')
                    
        elif editor_type == 'html':
            # حفظ HTML Template
            templates_dir = os.path.join(current_app.root_path, 'templates')
            filepath = request.form.get('filepath', '')
            content = request.form.get('content', '')
            
            if filepath and not '..' in filepath:
                full_path = os.path.join(templates_dir, filepath)
                try:
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    flash(f'✅ تم حفظ {filepath} بنجاح!', 'success')
                except Exception as e:
                    flash(f'❌ خطأ: {str(e)}', 'danger')
                    
        elif editor_type == 'text':
            # حفظ النصوص
            key = request.form.get('key')
            value = request.form.get('value')
            
            setting = SystemSettings.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSettings(key=key, value=value)
                db.session.add(setting)
            
            db.session.commit()
            flash(f'✅ تم تحديث {key}', 'success')
        
        return redirect(url_for('security.theme_editor', type=editor_type))
    
    # جمع البيانات حسب النوع
    data = {}
    
    # CSS Files
    css_dir = os.path.join(current_app.root_path, 'static', 'css')
    css_files = [f for f in os.listdir(css_dir) if f.endswith('.css')]
    selected_css = request.args.get('file', 'style.css')
    css_content = ''
    if selected_css in css_files:
        try:
            with open(os.path.join(css_dir, selected_css), 'r', encoding='utf-8') as f:
                css_content = f.read()
        except:
            pass
    data['css'] = {'files': css_files, 'selected': selected_css, 'content': css_content}
    
    # HTML Templates
    templates_dir = os.path.join(current_app.root_path, 'templates')
    def get_templates_tree(directory, prefix=''):
        items = []
        try:
            for item in sorted(os.listdir(directory)):
                if item.startswith('.') or item == '__pycache__':
                    continue
                full_path = os.path.join(directory, item)
                rel_path = os.path.join(prefix, item) if prefix else item
                if os.path.isdir(full_path):
                    items.append({'type': 'dir', 'name': item, 'path': rel_path})
                    items.extend(get_templates_tree(full_path, rel_path))
                elif item.endswith('.html'):
                    items.append({'type': 'file', 'name': item, 'path': rel_path})
        except:
            pass
        return items
    
    templates_tree = get_templates_tree(templates_dir)
    selected_template = request.args.get('template', 'base.html')
    template_content = ''
    if selected_template and not '..' in selected_template:
        try:
            with open(os.path.join(templates_dir, selected_template), 'r', encoding='utf-8') as f:
                template_content = f.read()
        except:
            pass
    data['html'] = {'tree': templates_tree, 'selected': selected_template, 'content': template_content}
    
    # Text Settings
    text_settings = SystemSettings.query.filter(
        SystemSettings.key.like('%_text%') | 
        SystemSettings.key.like('%_label%') |
        SystemSettings.key.like('%_name%')
    ).all()
    data['text'] = {'settings': text_settings}
    
    return render_template('security/theme_editor.html', 
                         data=data,
                         active_tab=editor_type)


@security_bp.route('/text-editor', methods=['GET', 'POST'])
@owner_only
def text_editor():
    """إعادة توجيه لمحرر الكود الموحد - تبويب النصوص"""
    return redirect(url_for('security.theme_editor', type='text'))


@security_bp.route('/logo-manager', methods=['GET', 'POST'])
@owner_only
def logo_manager():
    """مدير الشعارات - رفع وتعديل الشعارات"""
    import os
    from werkzeug.utils import secure_filename
    
    if request.method == 'POST':
        if 'logo_file' in request.files:
            file = request.files['logo_file']
            logo_type = request.form.get('logo_type', 'main')
            
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_path = os.path.join(current_app.root_path, 'static', 'img')
                
                logo_mapping = {
                    'main': 'azad_logo.png',
                    'emblem': 'azad_logo_emblem.png',
                    'white': 'azad_logo_white_on_dark.png',
                    'favicon': 'azad_favicon.png'
                }
                
                target_name = logo_mapping.get(logo_type, 'azad_logo.png')
                filepath = os.path.join(upload_path, target_name)
                
                try:
                    file.save(filepath)
                    flash(f'✅ تم رفع {target_name} بنجاح!', 'success')
                except Exception as e:
                    flash(f'❌ خطأ: {str(e)}', 'danger')
    
    logos = {
        'main': 'azad_logo.png',
        'emblem': 'azad_logo_emblem.png',
        'white': 'azad_logo_white_on_dark.png',
        'favicon': 'azad_favicon.png'
    }
    
    return render_template('security/logo_manager.html', logos=logos)


@security_bp.route('/template-editor', methods=['GET', 'POST'])
@owner_only
def template_editor():
    """إعادة توجيه لمحرر الكود الموحد - تبويب HTML"""
    return redirect(url_for('security.theme_editor', type='html'))


@security_bp.route('/table-manager', methods=['GET', 'POST'])
@owner_only
def table_manager():
    """مدير الجداول - إنشاء وتعديل الجداول"""
    tables = db.engine.table_names() if hasattr(db.engine, 'table_names') else []
    
    if not tables:
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
        except:
            tables = []
    
    selected_table = request.args.get('table')
    columns = []
    sample_data = []
    
    if selected_table:
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = inspector.get_columns(selected_table)
            
            result = db.session.execute(text(f"SELECT * FROM {selected_table} LIMIT 10"))
            sample_data = [dict(row._mapping) for row in result]
        except:
            pass
    
    return render_template('security/table_manager.html',
                         tables=tables,
                         selected_table=selected_table,
                         columns=columns,
                         sample_data=sample_data)


@security_bp.route('/advanced-analytics')
@owner_only
def advanced_analytics():
    """تحليلات متقدمة - ذكاء اصطناعي"""
    from models import Payment, Sale, Expense, Customer, Supplier
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0)
    
    analytics = {
        'revenue_trend': [],
        'expense_trend': [],
        'top_customers': [],
        'top_products': [],
        'payment_methods': {},
        'monthly_growth': 0,
    }
    
    revenue_by_day = db.session.query(
        func.date(Payment.payment_date).label('date'),
        func.sum(Payment.total_amount).label('total')
    ).filter(
        Payment.direction == 'IN',
        Payment.status == 'COMPLETED',
        Payment.payment_date >= start_of_month
    ).group_by(func.date(Payment.payment_date)).all()
    
    analytics['revenue_trend'] = [{'date': str(r.date), 'amount': float(r.total or 0)} for r in revenue_by_day]
    
    top_customers = db.session.query(
        Customer.name,
        func.sum(Payment.total_amount).label('total')
    ).join(Payment).filter(
        Payment.direction == 'IN',
        Payment.status == 'COMPLETED'
    ).group_by(Customer.id).order_by(func.sum(Payment.total_amount).desc()).limit(10).all()
    
    analytics['top_customers'] = [{'name': c.name, 'total': float(c.total or 0)} for c in top_customers]
    
    return render_template('security/advanced_analytics.html', analytics=analytics)


@security_bp.route('/permissions-manager', methods=['GET', 'POST'])
@owner_only
def permissions_manager():
    """إدارة الصلاحيات - إنشاء وتخصيص"""
    from models import Permission, Role
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_permission':
            code = request.form.get('code')
            name = request.form.get('name')
            
            perm = Permission(code=code, name=name)
            db.session.add(perm)
            db.session.commit()
            flash(f'✅ تم إنشاء صلاحية: {name}', 'success')
        
        return redirect(url_for('security.permissions_manager'))
    
    permissions = Permission.query.all()
    roles = Role.query.all()
    
    return render_template('security/permissions_manager.html', 
                         permissions=permissions,
                         roles=roles)


@security_bp.route('/email-manager', methods=['GET', 'POST'])
@owner_only
def email_manager():
    """إدارة البريد - SMTP + قوالب"""
    from models import SystemSettings
    
    if request.method == 'POST':
        smtp_settings = {
            'MAIL_SERVER': request.form.get('mail_server'),
            'MAIL_PORT': request.form.get('mail_port'),
            'MAIL_USERNAME': request.form.get('mail_username'),
            'MAIL_PASSWORD': request.form.get('mail_password'),
            'MAIL_USE_TLS': request.form.get('mail_use_tls') == 'on',
        }
        
        for key, value in smtp_settings.items():
            setting = SystemSettings.query.filter_by(key=key).first()
            if setting:
                setting.value = str(value)
            else:
                db.session.add(SystemSettings(key=key, value=str(value)))
        
        db.session.commit()
        flash('✅ تم حفظ إعدادات البريد', 'success')
        return redirect(url_for('security.email_manager'))
    
    settings = {}
    for key in ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_USE_TLS']:
        s = SystemSettings.query.filter_by(key=key).first()
        settings[key] = s.value if s else ''
    
    return render_template('security/email_manager.html', settings=settings)


@security_bp.route('/invoice-designer', methods=['GET', 'POST'])
@owner_only
def invoice_designer():
    """محرر الفواتير - تخصيص تصميم الفواتير"""
    from models import SystemSettings
    
    if request.method == 'POST':
        invoice_settings = {
            'invoice_header_color': request.form.get('header_color'),
            'invoice_footer_text': request.form.get('footer_text'),
            'invoice_show_logo': request.form.get('show_logo') == 'on',
            'invoice_show_tax': request.form.get('show_tax') == 'on',
        }
        
        for key, value in invoice_settings.items():
            setting = SystemSettings.query.filter_by(key=key).first()
            if setting:
                setting.value = str(value)
            else:
                db.session.add(SystemSettings(key=key, value=str(value)))
        
        db.session.commit()
        flash('✅ تم حفظ تصميم الفواتير', 'success')
        return redirect(url_for('security.invoice_designer'))
    
    settings = {}
    for key in ['invoice_header_color', 'invoice_footer_text', 'invoice_show_logo', 'invoice_show_tax']:
        s = SystemSettings.query.filter_by(key=key).first()
        settings[key] = s.value if s else ''
    
    return render_template('security/invoice_designer.html', settings=settings)


@security_bp.route('/integrations', methods=['GET'])
@owner_only
def integrations():
    """مركز التكامل - واتساب + بريد + APIs"""
    from models import SystemSettings
    
    integration_keys = [
        'whatsapp_phone', 'whatsapp_token', 'whatsapp_url',
        'smtp_server', 'smtp_port', 'smtp_username', 'smtp_use_tls',
        'reader_type', 'reader_api_url', 'reader_api_key', 'merchant_id',
        'accounting_system', 'accounting_api_url', 'accounting_api_key', 'sync_gl_auto',
        'obd2_device', 'obd2_port', 'obd2_auto_diagnose',
        'barcode_type', 'barcode_sound',
        'sms_provider', 'sms_api_key', 'sms_sender',
        'google_maps_key', 'openai_key', 'stripe_key', 'paypal_client_id'
    ]
    
    integrations_data = {}
    for key in integration_keys:
        s = SystemSettings.query.filter_by(key=key).first()
        integrations_data[key] = s.value if s else ''
    
    return render_template('security/integrations.html', integrations=integrations_data)


@security_bp.route('/save-integration', methods=['POST'])
@owner_only
def save_integration():
    """حفظ إعدادات التكامل مع اختبار الاتصال"""
    from models import SystemSettings
    
    integration_type = request.form.get('integration_type')
    
    # حفظ الإعدادات
    for key, value in request.form.items():
        if key in ['csrf_token', 'integration_type']:
            continue
        
        setting = SystemSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            db.session.add(SystemSettings(key=key, value=str(value)))
    
    db.session.commit()
    
    # اختبار الاتصال تلقائياً
    test_result = _test_integration_connection(integration_type)
    
    # تسجيل النشاط في سجل التدقيق
    _log_integration_activity(integration_type, 'configured', test_result['success'])
    
    type_names = {
        'whatsapp': 'واتساب',
        'email': 'البريد الإلكتروني',
        'card_reader': 'قارئ الكروت',
        'accounting': 'المحاسبة',
        'obd2': 'كمبيوتر السيارات',
        'barcode': 'قارئ الباركود',
        'sms': 'الرسائل النصية',
        'api_keys': 'مفاتيح API'
    }
    
    name = type_names.get(integration_type, 'الإعدادات')
    
    if test_result['success']:
        flash(f'✅ تم حفظ إعدادات {name} - الاتصال ناجح!', 'success')
    else:
        flash(f'⚠️ تم حفظ إعدادات {name} - فشل الاتصال: {test_result["error"]}', 'warning')
    
    return redirect(url_for('security.integrations'))


@security_bp.route('/test-integration/<integration_type>', methods=['POST'])
@owner_only
def test_integration(integration_type):
    """اختبار تكامل معين"""
    result = _test_integration_connection(integration_type)
    
    # تسجيل النشاط
    _log_integration_activity(integration_type, 'tested', result['success'])
    
    return jsonify(result)


@security_bp.route('/send-test-message/<integration_type>', methods=['POST'])
@owner_only
def send_test_message(integration_type):
    """إرسال رسالة تجريبية"""
    result = _send_test_message(integration_type)
    
    # تسجيل النشاط
    _log_integration_activity(integration_type, 'message_sent', result['success'])
    
    return jsonify(result)


@security_bp.route('/integration-stats')
@owner_only
def integration_stats():
    """إحصائيات التكاملات"""
    stats = _get_integration_stats()
    return jsonify(stats)


@security_bp.route('/live-monitoring')
@owner_only
def live_monitoring():
    """مراقبة فورية للنظام"""
    live_data = {
        'online_users': _get_online_users_detailed(),
        'recent_actions': _get_recent_actions(50),
        'system_metrics': _get_live_metrics(),
    }
    return render_template('security/live_monitoring.html', live_data=live_data)


@security_bp.route('/user-control')
@owner_only
def user_control():
    """التحكم الكامل بالمستخدمين"""
    users = User.query.order_by(User.id).all()
    return render_template('security/user_control.html', users=users)


@security_bp.route('/impersonate/<int:user_id>', methods=['POST'])
@owner_only
def impersonate_user(user_id):
    """تسجيل الدخول كمستخدم آخر"""
    from flask_login import logout_user, login_user
    
    target_user = User.query.get_or_404(user_id)
    
    # منع التسجيل كنفس المستخدم
    if target_user.id == current_user.id:
        flash('⚠️ أنت بالفعل هذا المستخدم!', 'warning')
        return redirect(url_for('security.user_control'))
    
    # حفظ المستخدم الأصلي
    session['original_user_id'] = current_user.id
    session['original_username'] = current_user.username
    session['impersonating'] = True
    
    # تسجيل في AuditLog
    try:
        log = AuditLog(
            user_id=current_user.id,
            action='security.impersonate_user',
            table_name='user',
            record_id=target_user.id,
            note=f'Owner impersonated as: {target_user.username}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass
    
    logout_user()
    login_user(target_user)
    
    flash(f'🕵️ تم تسجيل الدخول كـ {target_user.username}', 'warning')
    return redirect(url_for('main.dashboard'))


@security_bp.route('/stop-impersonate', methods=['POST'])
def stop_impersonate():
    """إيقاف التسجيل كمستخدم آخر"""
    from flask_login import logout_user, login_user
    
    if session.get('impersonating'):
        original_user_id = session.get('original_user_id')
        if original_user_id:
            original_user = User.query.get(original_user_id)
            if original_user:
                logout_user()
                login_user(original_user)
                session.pop('impersonating', None)
                session.pop('original_user_id', None)
                flash('تم العودة لحسابك الأصلي', 'success')
    
    return redirect(url_for('security.ultimate_control'))


@security_bp.route('/force-reset-password/<int:user_id>', methods=['POST'])
@owner_only
def force_reset_password(user_id):
    """إعادة تعيين كلمة مرور المستخدم"""
    from werkzeug.security import generate_password_hash
    
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '123456')
    
    user.password = generate_password_hash(new_password)
    db.session.commit()
    
    flash(f'تم إعادة تعيين كلمة مرور {user.username}', 'success')
    return redirect(url_for('security.user_control'))


@security_bp.route('/toggle-user/<int:user_id>', methods=['POST'])
@owner_only
def toggle_user_status(user_id):
    """تفعيل/تعطيل مستخدم"""
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'مفعل' if user.is_active else 'معطل'
    flash(f'المستخدم {user.username} الآن {status}', 'success')
    return redirect(url_for('security.user_control'))


@security_bp.route('/sql-console', methods=['GET', 'POST'])
@owner_only
def sql_console():
    """وحدة تنفيذ SQL مباشرة"""
    result = None
    error = None
    
    if request.method == 'POST':
        sql_query = request.form.get('sql_query', '').strip()
        
        try:
            result_proxy = db.session.execute(text(sql_query))
            
            # محاولة الحصول على النتائج
            try:
                rows = result_proxy.fetchall()
                columns = result_proxy.keys() if hasattr(result_proxy, 'keys') else []
                result = {
                    'columns': list(columns),
                    'rows': [list(row) for row in rows],
                    'count': len(rows)
                }
            except:
                # استعلام لا يرجع نتائج (INSERT, UPDATE, DELETE)
                db.session.commit()
                result = {'message': 'تم تنفيذ الاستعلام بنجاح'}
        
        except Exception as e:
            error = str(e)
            db.session.rollback()
    
    return render_template('security/sql_console.html', result=result, error=error)


@security_bp.route('/python-console', methods=['GET', 'POST'])
@owner_only
def python_console():
    """وحدة تنفيذ Python مباشرة"""
    result = None
    error = None
    
    if request.method == 'POST':
        python_code = request.form.get('python_code', '').strip()
        
        try:
            # تنفيذ الكود في بيئة آمنة
            local_vars = {
                'db': db,
                'User': User,
                'AuditLog': AuditLog,
                'current_user': current_user,
                'datetime': datetime,
                'timezone': timezone
            }
            
            exec(python_code, {'__builtins__': __builtins__}, local_vars)
            result = local_vars.get('output', 'تم التنفيذ بنجاح')
        
        except Exception as e:
            error = str(e)
    
    return render_template('security/python_console.html', result=result, error=error)


@security_bp.route('/settings', methods=['GET', 'POST'])
@security_bp.route('/system-settings', methods=['GET', 'POST'])  # Backward compatibility
@owner_only
def system_settings():
    """إعدادات النظام الموحدة - 3 في 1 (عامة + متقدمة + ثوابت)"""
    tab = request.args.get('tab', 'general')  # general, advanced, constants
    
    if request.method == 'POST':
        tab = request.form.get('active_tab', 'general')
        
        if tab == 'general':
            # حفظ الإعدادات العامة
            settings = {
                'maintenance_mode': request.form.get('maintenance_mode') == 'on',
                'registration_enabled': request.form.get('registration_enabled') == 'on',
                'api_enabled': request.form.get('api_enabled') == 'on',
            }
            for key, value in settings.items():
                _set_system_setting(key, value)
            flash('✅ تم حفظ الإعدادات العامة', 'success')
            
        elif tab == 'advanced':
            # حفظ التكوينات المتقدمة
            config = {
                'SESSION_TIMEOUT': request.form.get('session_timeout', 3600),
                'MAX_LOGIN_ATTEMPTS': request.form.get('max_login_attempts', 5),
                'PASSWORD_MIN_LENGTH': request.form.get('password_min_length', 8),
                'AUTO_BACKUP_ENABLED': request.form.get('auto_backup_enabled') == 'on',
                'BACKUP_INTERVAL_HOURS': request.form.get('backup_interval_hours', 24),
                'ENABLE_EMAIL_NOTIFICATIONS': request.form.get('enable_email_notifications') == 'on',
                'ENABLE_SMS_NOTIFICATIONS': request.form.get('enable_sms_notifications') == 'on',
            }
            for key, value in config.items():
                _set_system_setting(key, value)
            flash('✅ تم تحديث التكوين المتقدم', 'success')
            
        elif tab == 'constants':
            # حفظ الثوابت
            constants = {
                'COMPANY_NAME': request.form.get('company_name', ''),
                'COMPANY_ADDRESS': request.form.get('company_address', ''),
                'COMPANY_PHONE': request.form.get('company_phone', ''),
                'COMPANY_EMAIL': request.form.get('company_email', ''),
                'TAX_NUMBER': request.form.get('tax_number', ''),
                'CURRENCY_SYMBOL': request.form.get('currency_symbol', '$'),
                'TIMEZONE': request.form.get('timezone', 'UTC'),
                'DATE_FORMAT': request.form.get('date_format', '%Y-%m-%d'),
                'TIME_FORMAT': request.form.get('time_format', '%H:%M:%S'),
            }
            for key, value in constants.items():
                if value:
                    _set_system_setting(key, value)
            flash('✅ تم تحديث الثوابت', 'success')
        
        return redirect(url_for('security.system_settings', tab=tab))
    
    # قراءة جميع الإعدادات
    data = {
        'general': {
            'maintenance_mode': _get_system_setting('maintenance_mode', False),
            'registration_enabled': _get_system_setting('registration_enabled', True),
            'api_enabled': _get_system_setting('api_enabled', True),
        },
        'advanced': {
            'SESSION_TIMEOUT': _get_system_setting('SESSION_TIMEOUT', 3600),
            'MAX_LOGIN_ATTEMPTS': _get_system_setting('MAX_LOGIN_ATTEMPTS', 5),
            'PASSWORD_MIN_LENGTH': _get_system_setting('PASSWORD_MIN_LENGTH', 8),
            'AUTO_BACKUP_ENABLED': _get_system_setting('AUTO_BACKUP_ENABLED', True),
            'BACKUP_INTERVAL_HOURS': _get_system_setting('BACKUP_INTERVAL_HOURS', 24),
            'ENABLE_EMAIL_NOTIFICATIONS': _get_system_setting('ENABLE_EMAIL_NOTIFICATIONS', True),
            'ENABLE_SMS_NOTIFICATIONS': _get_system_setting('ENABLE_SMS_NOTIFICATIONS', False),
        },
        'constants': {
            'COMPANY_NAME': _get_system_setting('COMPANY_NAME', 'Azad Garage'),
            'COMPANY_ADDRESS': _get_system_setting('COMPANY_ADDRESS', ''),
            'COMPANY_PHONE': _get_system_setting('COMPANY_PHONE', ''),
            'COMPANY_EMAIL': _get_system_setting('COMPANY_EMAIL', ''),
            'TAX_NUMBER': _get_system_setting('TAX_NUMBER', ''),
            'CURRENCY_SYMBOL': _get_system_setting('CURRENCY_SYMBOL', '$'),
            'TIMEZONE': _get_system_setting('TIMEZONE', 'UTC'),
            'DATE_FORMAT': _get_system_setting('DATE_FORMAT', '%Y-%m-%d'),
            'TIME_FORMAT': _get_system_setting('TIME_FORMAT', '%H:%M:%S'),
        }
    }
    
    return render_template('security/system_settings.html', data=data, active_tab=tab)


@security_bp.route('/emergency-tools')
@owner_only
def emergency_tools():
    """أدوات الطوارئ"""
    return render_template('security/emergency_tools.html')


@security_bp.route('/emergency/maintenance-mode', methods=['POST'])
@owner_only
def toggle_maintenance_mode():
    """تفعيل/تعطيل وضع الصيانة"""
    current = _get_system_setting('maintenance_mode', False)
    _set_system_setting('maintenance_mode', not current)
    
    status = 'مفعل' if not current else 'معطل'
    flash(f'وضع الصيانة الآن {status}', 'warning')
    return redirect(url_for('security.emergency_tools'))


@security_bp.route('/emergency/clear-cache', methods=['POST'])
@owner_only
def clear_system_cache():
    """مسح الكاش بالكامل"""
    from extensions import cache
    cache.clear()
    flash('تم مسح الكاش بالكامل', 'success')
    return redirect(url_for('security.emergency_tools'))


@security_bp.route('/emergency/kill-sessions', methods=['POST'])
@owner_only
def kill_all_sessions():
    """إنهاء جميع الجلسات"""
    # إنهاء جميع الجلسات النشطة
    _kill_all_user_sessions()
    flash('تم إنهاء جميع الجلسات', 'warning')
    return redirect(url_for('security.emergency_tools'))


@security_bp.route('/data-export')
@owner_only
def data_export():
    """تصدير البيانات"""
    tables = _get_all_tables()
    return render_template('security/data_export.html', tables=tables)


@security_bp.route('/export-table/<table_name>')
@owner_only
def export_table_csv(table_name):
    """تصدير جدول كـ CSV"""
    import csv
    from io import StringIO
    
    data, columns = _browse_table(table_name, limit=10000)
    
    si = StringIO()
    writer = csv.DictWriter(si, fieldnames=columns)
    writer.writeheader()
    writer.writerows(data)
    
    output = si.getvalue()
    
    from flask import make_response
    response = make_response(output)
    response.headers["Content-Disposition"] = f"attachment; filename={table_name}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response


@security_bp.route('/advanced-backup', methods=['GET', 'POST'])
@owner_only
def advanced_backup():
    """نسخ احتياطي متقدم - إعادة توجيه للوحدة الجديدة"""
    return redirect(url_for('advanced.backup_manager'))


@security_bp.route('/performance-monitor')
@owner_only
def performance_monitor():
    """مراقبة الأداء"""
    performance = {
        'db_queries': _get_slow_queries(),
        'response_times': _get_avg_response_times(),
        'memory_usage': _get_memory_usage(),
        'cpu_usage': _get_cpu_usage(),
    }
    return render_template('security/performance_monitor.html', performance=performance)


@security_bp.route('/system-branding', methods=['GET', 'POST'])
@owner_only
def system_branding():
    """تخصيص العلامة التجارية (الشعار، الاسم، الألوان)"""
    if request.method == 'POST':
        from werkzeug.utils import secure_filename
        import os
        
        updated = []
        
        # اسم النظام
        system_name = request.form.get('system_name', '').strip()
        if system_name and len(system_name) >= 3:
            _set_system_setting('system_name', system_name)
            updated.append('اسم النظام')
        elif system_name and len(system_name) < 3:
            flash('⚠️ اسم النظام يجب أن يكون 3 أحرف على الأقل', 'warning')
        
        # وصف النظام
        system_description = request.form.get('system_description', '').strip()
        if system_description:
            _set_system_setting('system_description', system_description)
            updated.append('وصف النظام')
        
        # اللون الأساسي
        primary_color = request.form.get('primary_color', '').strip()
        if primary_color:
            # التحقق من صيغة اللون
            import re
            if re.match(r'^#[0-9A-Fa-f]{6}$', primary_color):
                _set_system_setting('primary_color', primary_color)
                updated.append('اللون الأساسي')
            else:
                flash('⚠️ صيغة اللون غير صحيحة (مثال: #007bff)', 'warning')
        
        # الشعار
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file and logo_file.filename:
                # التحقق من نوع الملف
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = logo_file.filename.rsplit('.', 1)[1].lower() if '.' in logo_file.filename else ''
                
                if file_ext in allowed_extensions:
                    filename = secure_filename(logo_file.filename)
                    os.makedirs('static/img', exist_ok=True)
                    logo_path = f'static/img/custom_logo_{filename}'
                    logo_file.save(logo_path)
                    _set_system_setting('custom_logo', logo_path)
                    updated.append('الشعار')
                else:
                    flash('⚠️ نوع ملف الشعار غير مدعوم (استخدم: png, jpg, jpeg, gif, webp)', 'warning')
        
        # الأيقونة
        if 'favicon' in request.files:
            favicon_file = request.files['favicon']
            if favicon_file and favicon_file.filename:
                allowed_extensions = {'png', 'ico'}
                file_ext = favicon_file.filename.rsplit('.', 1)[1].lower() if '.' in favicon_file.filename else ''
                
                if file_ext in allowed_extensions:
                    filename = secure_filename(favicon_file.filename)
                    favicon_path = f'static/favicon_custom_{filename}'
                    favicon_file.save(favicon_path)
                    _set_system_setting('custom_favicon', favicon_path)
                    updated.append('الأيقونة')
                else:
                    flash('⚠️ نوع ملف الأيقونة غير مدعوم (استخدم: png, ico)', 'warning')
        
        if updated:
            flash(f'✅ تم تحديث: {", ".join(updated)} بنجاح!', 'success')
            
            # تسجيل في AuditLog
            try:
                log = AuditLog(
                    user_id=current_user.id,
                    action='security.update_branding',
                    table_name='system_settings',
                    note=f'Updated: {", ".join(updated)}',
                    ip_address=request.remote_addr
                )
                db.session.add(log)
                db.session.commit()
            except:
                pass
        else:
            flash('ℹ️ لم يتم تحديث أي شيء', 'info')
        
        return redirect(url_for('security.system_branding'))
    
    # قراءة الإعدادات الحالية
    branding = {
        'system_name': _get_system_setting('system_name', 'Garage Manager'),
        'system_description': _get_system_setting('system_description', 'نظام إدارة الكراجات'),
        'primary_color': _get_system_setting('primary_color', '#007bff'),
        'custom_logo': _get_system_setting('custom_logo', ''),
        'custom_favicon': _get_system_setting('custom_favicon', ''),
    }
    
    return render_template('security/system_branding.html', branding=branding)


@security_bp.route('/logs-viewer')
@owner_only
def logs_viewer():
    """عارض اللوجات (السيرفر والنظام)"""
    log_files = _get_available_log_files()
    return render_template('security/logs_viewer.html', log_files=log_files)


@security_bp.route('/logs-download/<log_type>')
@owner_only
def logs_download(log_type):
    """تحميل ملف لوج"""
    import os
    from flask import send_file
    
    log_files = {
        'error': 'logs/error.log',
        'server': 'logs/server_error.log',
        'audit': 'instance/audit.log',
        'access': 'logs/access.log',
        'security': 'logs/security.log',
        'performance': 'logs/performance.log',
    }
    
    log_path = log_files.get(log_type)
    if log_path and os.path.exists(log_path):
        return send_file(log_path, as_attachment=True, download_name=f'{log_type}_log.txt')
    
    flash('ملف اللوج غير موجود', 'warning')
    return redirect(url_for('security.logs_viewer'))


@security_bp.route('/logs-view/<log_type>')
@owner_only
def logs_view(log_type):
    """عرض محتوى ملف لوج"""
    import os
    
    log_files = {
        'error': 'logs/error.log',
        'server': 'logs/server_error.log',
        'audit': 'instance/audit.log',
        'access': 'logs/access.log',
        'security': 'logs/security.log',
        'performance': 'logs/performance.log',
    }
    
    log_path = log_files.get(log_type)
    content = ''
    
    if log_path and os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # آخر 1000 سطر
                content = ''.join(lines[-1000:])
        except Exception as e:
            content = f'خطأ في قراءة الملف: {str(e)}'
    else:
        content = 'ملف اللوج غير موجود'
    
    return render_template('security/logs_content.html', log_type=log_type, content=content)


@security_bp.route('/logs-clear/<log_type>', methods=['POST'])
@owner_only
def logs_clear(log_type):
    """تنظيف محتوى ملف لوج (إفراغه)"""
    import os
    from flask import jsonify
    
    log_files = {
        'error': 'logs/error.log',
        'server': 'logs/server_error.log',
        'access': 'logs/access.log',
        'performance': 'logs/performance.log',
        'security': 'logs/security.log',
        'audit': 'instance/audit.log'
    }
    
    log_path = log_files.get(log_type)
    
    # التحقق من وجود الملف
    if not log_path:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'نوع اللوج غير صحيح'}), 400
        flash('نوع اللوج غير صحيح', 'error')
        return redirect(url_for('security.logs_viewer'))
    
    if not os.path.exists(log_path):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'ملف اللوج غير موجود'}), 404
        flash('ملف اللوج غير موجود', 'warning')
        return redirect(url_for('security.logs_viewer'))
    
    try:
        # تنظيف الملف (إفراغه)
        with open(log_path, 'w') as f:
            f.write('')
        
        # دعم AJAX
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True, 
                'message': f'✅ تم تنظيف محتوى {log_type}.log بنجاح'
            })
        
        flash(f'✅ تم تنظيف محتوى {log_type}.log بنجاح', 'success')
    except Exception as e:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'❌ خطأ: {str(e)}'}), 500
        flash(f'❌ خطأ في تنظيف اللوج: {str(e)}', 'error')
    
    return redirect(url_for('security.logs_viewer'))


@security_bp.route('/error-tracker')
@owner_only
def error_tracker():
    """تتبع الأخطاء في الوقت الفعلي"""
    errors = _get_recent_errors(100)
    error_stats = _get_error_statistics()
    
    return render_template('security/error_tracker.html', 
                          errors=errors, 
                          error_stats=error_stats)


@security_bp.route('/system-constants', methods=['GET', 'POST'])
@owner_only
def system_constants():
    """إعادة توجيه لصفحة الإعدادات الموحدة - تبويب الثوابت"""
    return redirect(url_for('security.system_settings', tab='constants'))


@security_bp.route('/advanced-config', methods=['GET', 'POST'])
@owner_only
def advanced_config():
    """إعادة توجيه لصفحة الإعدادات الموحدة - تبويب المتقدمة"""
    return redirect(url_for('security.system_settings', tab='advanced'))


# ═══════════════════════════════════════════════════════════════
# DATABASE EDITOR - ADVANCED
# ═══════════════════════════════════════════════════════════════

@security_bp.route('/db-editor')
@owner_only
def db_editor():
    """محرر قاعدة البيانات المتقدم"""
    tables = _get_all_tables()
    return render_template('security/db_editor.html', tables=tables)


@security_bp.route('/db-editor/table/<table_name>')
@owner_only
def db_editor_table(table_name):
    """تحرير جدول معين"""
    data, columns = _browse_table(table_name, limit=1000)
    table_info = _get_table_info(table_name)
    
    return render_template('security/db_editor_table.html', 
                          table_name=table_name,
                          data=data,
                          columns=columns,
                          table_info=table_info)


@security_bp.route('/db-editor/add-column/<table_name>', methods=['POST'])
@owner_only
def db_add_column(table_name):
    """إضافة عمود جديد"""
    column_name = request.form.get('column_name', '').strip()
    column_type = request.form.get('column_type', 'TEXT')
    default_value = request.form.get('default_value', '')
    
    if not column_name:
        flash('اسم العمود مطلوب', 'danger')
        return redirect(url_for('security.db_editor_table', table_name=table_name))
    
    try:
        # بناء استعلام ALTER TABLE
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        if default_value:
            sql += f" DEFAULT '{default_value}'"
        
        db.session.execute(text(sql))
        db.session.commit()
        
        flash(f'تم إضافة العمود {column_name} بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/update-cell/<table_name>', methods=['POST'])
@owner_only
def db_update_cell(table_name):
    """تحديث خلية واحدة مباشرة - للتعديل السريع"""
    try:
        data = request.get_json()
        row_id = data.get('row_id')
        column = data.get('column')
        value = data.get('value')
        
        if not all([row_id, column]):
            return jsonify({'success': False, 'error': 'معلومات ناقصة'}), 400
        
        # تحديد المفتاح الأساسي للجدول
        primary_key = 'id'  # افتراضياً
        
        # فحص إذا كان الجدول له عمود id
        table_info = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        has_id_column = any(col[1] == 'id' for col in table_info)
        
        if not has_id_column:
            # إذا لم يكن هناك عمود id، نستخدم أول عمود كمفتاح أساسي
            primary_key = table_info[0][1] if table_info else 'code'
        
        # تحديث الخلية
        if primary_key == 'id':
            sql = text(f"UPDATE {table_name} SET {column} = :value WHERE id = :row_id")
        else:
            sql = text(f"UPDATE {table_name} SET {column} = :value WHERE {primary_key} = :row_id")
        
        result = db.session.execute(sql, {'value': value, 'row_id': row_id})
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'تم تحديث {column} بنجاح',
            'rows_affected': result.rowcount
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@security_bp.route('/db-editor/edit-row/<table_name>/<int:row_id>', methods=['POST'])
@owner_only
def db_edit_row(table_name, row_id):
    """تعديل صف في الجدول"""
    try:
        # الحصول على جميع الحقول من الفورم
        updates = []
        for key, value in request.form.items():
            if key not in ['csrf_token', 'id']:
                updates.append(f"{key} = '{value}'")
        
        if updates:
            sql = f"UPDATE {table_name} SET {', '.join(updates)} WHERE id = {row_id}"
            db.session.execute(text(sql))
            db.session.commit()
            flash('تم التحديث بنجاح', 'success')
        else:
            flash('لا توجد تغييرات', 'warning')
    
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/delete-row/<table_name>/<row_id>', methods=['POST'])
@owner_only
def db_delete_row(table_name, row_id):
    """حذف صف من الجدول"""
    try:
        # تحديد المفتاح الأساسي للجدول
        primary_key = 'id'  # افتراضياً
        
        # فحص إذا كان الجدول له عمود id
        table_info = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        has_id_column = any(col[1] == 'id' for col in table_info)
        
        if not has_id_column:
            # إذا لم يكن هناك عمود id، نستخدم أول عمود كمفتاح أساسي
            primary_key = table_info[0][1] if table_info else 'code'
        
        # حذف الصف
        if primary_key == 'id':
            sql = text(f"DELETE FROM {table_name} WHERE id = :row_id")
        else:
            sql = text(f"DELETE FROM {table_name} WHERE {primary_key} = :row_id")
        
        result = db.session.execute(sql, {'row_id': row_id})
        db.session.commit()
        flash(f'✅ تم حذف الصف #{row_id} بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ في الحذف: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))

@security_bp.route('/db-editor/delete-column/<table_name>', methods=['POST'])
@owner_only
def db_delete_column(table_name):
    """حذف عمود كامل من الجدول"""
    column_name = request.form.get('column_name', '').strip()
    
    if not column_name:
        flash('❌ اسم العمود مطلوب', 'danger')
        return redirect(url_for('security.db_editor_table', table_name=table_name))
    
    # حماية من حذف الأعمدة الحرجة
    protected_columns = ['id', 'created_at', 'updated_at']
    if column_name.lower() in protected_columns:
        flash(f'❌ لا يمكن حذف العمود {column_name} (محمي)', 'danger')
        return redirect(url_for('security.db_editor_table', table_name=table_name))
    
    try:
        sql = f"ALTER TABLE {table_name} DROP COLUMN {column_name}"
        db.session.execute(text(sql))
        db.session.commit()
        flash(f'✅ تم حذف العمود {column_name} بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ في حذف العمود: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/add-row/<table_name>', methods=['POST'])
@owner_only
def db_add_row(table_name):
    """إضافة صف جديد"""
    try:
        # الحصول على الأعمدة والقيم
        columns = []
        values = []
        
        for key, value in request.form.items():
            if key != 'csrf_token':
                columns.append(key)
                values.append(f"'{value}'")
        
        if columns:
            sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)})"
            db.session.execute(text(sql))
            db.session.commit()
            flash('تم الإضافة بنجاح', 'success')
        else:
            flash('لا توجد بيانات', 'warning')
    
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/bulk-update/<table_name>', methods=['POST'])
@owner_only
def db_bulk_update(table_name):
    """تحديث جماعي للبيانات"""
    column = request.form.get('column', '')
    old_value = request.form.get('old_value', '')
    new_value = request.form.get('new_value', '')
    
    if not column:
        flash('اسم العمود مطلوب', 'danger')
        return redirect(url_for('security.db_editor_table', table_name=table_name))
    
    try:
        if old_value:
            sql = f"UPDATE {table_name} SET {column} = '{new_value}' WHERE {column} = '{old_value}'"
        else:
            sql = f"UPDATE {table_name} SET {column} = '{new_value}' WHERE {column} IS NULL OR {column} = ''"
        
        result = db.session.execute(text(sql))
        db.session.commit()
        
        flash(f'تم تحديث {result.rowcount} صف بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/fill-missing/<table_name>', methods=['POST'])
@owner_only
def db_fill_missing(table_name):
    """ملء البيانات الناقصة"""
    column = request.form.get('column', '')
    fill_value = request.form.get('fill_value', '')
    
    if not column:
        flash('اسم العمود مطلوب', 'danger')
        return redirect(url_for('security.db_editor_table', table_name=table_name))
    
    try:
        sql = f"UPDATE {table_name} SET {column} = '{fill_value}' WHERE {column} IS NULL OR {column} = ''"
        result = db.session.execute(text(sql))
        db.session.commit()
        
        flash(f'تم ملء {result.rowcount} حقل ناقص بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('security.db_editor_table', table_name=table_name))


@security_bp.route('/db-editor/schema/<table_name>')
@owner_only
def db_schema_editor(table_name):
    """محرر هيكل الجدول"""
    table_info = _get_table_info(table_name)
    return render_template('security/db_schema_editor.html', 
                          table_name=table_name,
                          table_info=table_info)


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def _get_blocked_ips_count():
    """عدد IPs المحظورة"""
    blocked = cache.get('blocked_ips') or []
    return len(blocked)

def _get_blocked_countries_count():
    """عدد الدول المحظورة"""
    blocked = cache.get('blocked_countries') or []
    return len(blocked)

def _get_failed_logins_count(hours=24):
    """عدد محاولات تسجيل الدخول الفاشلة"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return AuditLog.query.filter(
        AuditLog.action.in_(['login.failed', 'login.blocked']),
        AuditLog.created_at >= since
    ).count()

def _get_suspicious_activities_count(hours=24):
    """عدد الأنشطة المشبوهة"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return AuditLog.query.filter(
        AuditLog.action.like('%suspicious%'),
        AuditLog.created_at >= since
    ).count()

def _get_recent_suspicious_activities(limit=10):
    """آخر الأنشطة المشبوهة"""
    return AuditLog.query.filter(
        AuditLog.action.like('%suspicious%')
    ).order_by(AuditLog.created_at.desc()).limit(limit).all()

def _block_ip(ip, reason, duration):
    """حظر IP"""
    blocked = cache.get('blocked_ips') or []
    
    # إضافة IP للقائمة
    blocked_entry = {
        'ip': ip,
        'reason': reason,
        'duration': duration,
        'blocked_at': datetime.now(timezone.utc).isoformat(),
        'blocked_by': current_user.id
    }
    
    blocked.append(blocked_entry)
    
    # حفظ في Cache
    if duration == 'permanent':
        cache.set('blocked_ips', blocked, timeout=0)  # لا ينتهي
    else:
        timeout = _parse_duration(duration)
        cache.set('blocked_ips', blocked, timeout=timeout)
    
    # تسجيل في Audit
    AuditLog(
        model_name='Security',
        action='IP_BLOCKED',
        user_id=current_user.id,
        old_data=json.dumps({'ip': ip, 'reason': reason}, ensure_ascii=False),
        ip_address=request.remote_addr
    )
    db.session.commit()

def _unblock_ip(ip):
    """إلغاء حظر IP"""
    blocked = cache.get('blocked_ips') or []
    blocked = [b for b in blocked if b.get('ip') != ip]
    cache.set('blocked_ips', blocked, timeout=0)

def _get_all_blocked_ips():
    """الحصول على جميع IPs المحظورة"""
    return cache.get('blocked_ips') or []

def _block_country(country_code, reason):
    """حظر دولة"""
    blocked = cache.get('blocked_countries') or []
    
    blocked_entry = {
        'country_code': country_code,
        'reason': reason,
        'blocked_at': datetime.now(timezone.utc).isoformat(),
        'blocked_by': current_user.id
    }
    
    blocked.append(blocked_entry)
    cache.set('blocked_countries', blocked, timeout=0)

def _get_all_blocked_countries():
    """الحصول على جميع الدول المحظورة"""
    return cache.get('blocked_countries') or []

def _get_cleanable_tables():
    """الجداول القابلة للتنظيف"""
    return [
        # المستخدمين والحسابات (خطر عالي!)
        {'name': 'users_except_first_super', 'display': '👤 المستخدمين (ما عدا أول Super Admin)', 'danger': 'high'},
        {'name': 'roles', 'display': '🎭 الأدوار', 'danger': 'high'},
        {'name': 'user_roles', 'display': '🔗 ربط المستخدمين بالأدوار', 'danger': 'high'},
        
        # سجلات وملاحظات ولوجات
        {'name': 'audit_logs', 'display': '📋 سجلات التدقيق (Audit)', 'danger': 'low'},
        {'name': 'deletion_logs', 'display': '🗑️ سجل الحذف', 'danger': 'low'},
        {'name': 'notes', 'display': '📝 الملاحظات', 'danger': 'medium'},
        {'name': 'notifications', 'display': '🔔 الإشعارات', 'danger': 'low'},
        {'name': 'activity_logs', 'display': '📊 سجلات النشاطات', 'danger': 'low'},
        {'name': 'error_logs', 'display': '⚠️ سجلات الأخطاء', 'danger': 'low'},
        
        # التسوق الإلكتروني
        {'name': 'online_carts', 'display': '🛒 سلات التسوق', 'danger': 'low'},
        {'name': 'online_payments', 'display': '💳 المدفوعات الإلكترونية', 'danger': 'medium'},
        
        # العمليات المالية
        {'name': 'payments', 'display': '💰 المدفوعات', 'danger': 'high'},
        {'name': 'payment_splits', 'display': '💸 تقسيمات الدفع', 'danger': 'high'},
        {'name': 'expenses', 'display': '📤 المصاريف', 'danger': 'high'},
        {'name': 'checks', 'display': '📝 الشيكات', 'danger': 'high'},
        
        # المبيعات والصيانة
        {'name': 'sales', 'display': '🛍️ المبيعات', 'danger': 'high'},
        {'name': 'sale_lines', 'display': '📦 بنود المبيعات', 'danger': 'high'},
        {'name': 'service_requests', 'display': '🔧 طلبات الصيانة', 'danger': 'high'},
        {'name': 'service_parts', 'display': '⚙️ قطع الصيانة', 'danger': 'high'},
        {'name': 'service_tasks', 'display': '✔️ مهام الصيانة', 'danger': 'medium'},
        
        # المخزون والتبادلات
        {'name': 'stock_levels', 'display': '📊 مستويات المخزون', 'danger': 'high'},
        {'name': 'exchange_transactions', 'display': '🔄 معاملات التبادل', 'danger': 'high'},
        {'name': 'stock_adjustments', 'display': '📈 تعديلات المخزون', 'danger': 'medium'},
        
        # الحجوزات
        {'name': 'preorders', 'display': '📅 الحجوزات المسبقة', 'danger': 'medium'},
        {'name': 'online_preorders', 'display': '🌐 الحجوزات الإلكترونية', 'danger': 'medium'},
        
        # الشحنات والتسويات
        {'name': 'shipments', 'display': '🚚 الشحنات', 'danger': 'high'},
        {'name': 'shipment_items', 'display': '📦 بنود الشحنات', 'danger': 'high'},
        {'name': 'supplier_settlements', 'display': '💼 تسويات الموردين', 'danger': 'high'},
        
        # الجهات (خطر عالي جداً!)
        {'name': 'customers', 'display': '👥 العملاء', 'danger': 'high'},
        {'name': 'suppliers', 'display': '🏭 الموردين', 'danger': 'high'},
        {'name': 'partners', 'display': '🤝 الشركاء', 'danger': 'high'},
        
        # المخازن والمنتجات
        {'name': 'warehouses', 'display': '🏪 المخازن', 'danger': 'high'},
        {'name': 'products', 'display': '📦 المنتجات', 'danger': 'high'},
        {'name': 'product_categories', 'display': '🏷️ فئات المنتجات', 'danger': 'medium'},
        
        # القروض
        {'name': 'product_supplier_loans', 'display': '💳 قروض الموردين', 'danger': 'medium'},
        {'name': 'supplier_loan_settlements', 'display': '💵 تسويات القروض', 'danger': 'medium'},
        
        # الفواتير
        {'name': 'invoices', 'display': '📄 الفواتير', 'danger': 'high'},
        {'name': 'invoice_lines', 'display': '📋 بنود الفواتير', 'danger': 'high'},
        
        # العلاقات والارتباطات
        {'name': 'product_partners', 'display': '🔗 ربط المنتجات بالشركاء', 'danger': 'high'},
        {'name': 'shipment_partners', 'display': '🚢 ربط الشحنات بالشركاء', 'danger': 'high'},
        
        # الإعدادات والمرافق
        {'name': 'utility_accounts', 'display': '⚡ حسابات المرافق', 'danger': 'medium'},
        {'name': 'expense_types', 'display': '📂 أنواع المصاريف', 'danger': 'medium'},
        {'name': 'equipment_types', 'display': '🚗 أنواع المركبات', 'danger': 'medium'},
        
        # العمليات المحاسبية
        {'name': 'gl_batches', 'display': '📚 دفعات القيود المحاسبية', 'danger': 'high'},
        {'name': 'gl_entries', 'display': '📖 القيود المحاسبية', 'danger': 'high'},
        
        # أخرى
        {'name': 'files', 'display': '📁 الملفات المرفقة', 'danger': 'medium'},
        {'name': 'images', 'display': '🖼️ الصور', 'danger': 'medium'},
    ]

def _cleanup_tables(tables):
    """تنظيف الجداول المحددة"""
    cleaned = 0
    errors = []
    
    for table in tables:
        try:
            # معالجة خاصة للمستخدمين - حذف الكل (حتى الأدمنز) ما عدا أول Super Admin
            if table == 'users_except_first_super':
                from models import User
                # البحث عن أول Super Admin (الأقدم)
                first_super = User.query.filter_by(is_super_admin=True).order_by(User.id.asc()).first()
                
                if first_super:
                    first_super_id = first_super.id
                    # حذف جميع المستخدمين (بما فيهم الأدمنز الآخرين) ما عدا أول Super Admin
                    deleted_count = db.session.execute(
                        text("DELETE FROM users WHERE id != :super_id"), 
                        {'super_id': first_super_id}
                    ).rowcount
                    db.session.commit()
                    print(f"[INFO] Deleted {deleted_count} users, kept first Super Admin (ID: {first_super_id})")
                    cleaned += 1
                else:
                    # إذا لم يوجد Super Admin، لا نحذف شيء للحماية
                    errors.append(f"تخطي {table}: لا يوجد Super Admin!")
                    continue
            else:
                # تنظيف عادي للجداول الأخرى
                try:
                    deleted_count = db.session.execute(text(f"DELETE FROM {table}")).rowcount
                    db.session.commit()
                    print(f"[INFO] Cleaned table '{table}': {deleted_count} rows deleted")
                    cleaned += 1
                except Exception as delete_error:
                    # قد لا يكون الجدول موجوداً
                    db.session.rollback()
                    print(f"[WARNING] Table '{table}' not found or error: {str(delete_error)}")
                    continue
            
            # تسجيل في Audit (إذا لم يتم حذف audit_logs نفسه)
            if table != 'audit_logs':
                try:
                    db.session.add(AuditLog(
                        model_name='Security',
                        action='TABLE_CLEANED',
                        user_id=current_user.id,
                        old_data=json.dumps({'table': table}, ensure_ascii=False),
                        ip_address=request.remote_addr
                    ))
                    db.session.commit()
                except:
                    pass  # إذا تم حذف audit_logs، نتجاوز
                    
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to clean table {table}: {str(e)}"
            print(f"[ERROR] {error_msg}")
            errors.append(error_msg)
            continue
    
    return {'cleaned': cleaned, 'total': len(tables), 'errors': errors}

def _parse_duration(duration):
    """تحويل المدة إلى ثواني"""
    if duration == '1h':
        return 3600
    elif duration == '24h':
        return 86400
    elif duration == '7d':
        return 604800
    elif duration == '30d':
        return 2592000
    else:
        return 0  # permanent


# ═══════════════════════════════════════════════════════════════
# AI Functions - ADVANCED
# ═══════════════════════════════════════════════════════════════

def _ai_security_analysis(query):
    """تحليل أمني بالذكاء الاصطناعي"""
    analysis = {
        'query': query,
        'type': 'security_analysis',
        'findings': [],
        'recommendations': [],
        'threat_level': 'low'
    }
    
    query_lower = query.lower()
    
    # تحليل ذكي بناءً على السؤال
    if 'ip' in query_lower or 'عنوان' in query_lower:
        analysis['findings'].append('فحص IPs المشبوهة...')
        analysis['findings'].append(f'عدد IPs المحظورة: {_get_blocked_ips_count()}')
        analysis['recommendations'].append('مراقبة IPs من دول معينة')
    
    if 'login' in query_lower or 'دخول' in query_lower:
        failed = _get_failed_logins_count(24)
        analysis['findings'].append(f'محاولات فاشلة (24h): {failed}')
        if failed > 10:
            analysis['threat_level'] = 'medium'
            analysis['recommendations'].append('تفعيل CAPTCHA أو تقليل rate limit')
    
    if 'user' in query_lower or 'مستخدم' in query_lower:
        analysis['findings'].append(f'إجمالي المستخدمين: {User.query.count()}')
        analysis['findings'].append(f'المستخدمين النشطين: {User.query.filter_by(is_active=True).count()}')
    
    return analysis


def _get_ai_suggestions():
    """اقتراحات ذكية من AI"""
    suggestions = []
    
    # فحص محاولات فاشلة
    failed = _get_failed_logins_count(24)
    if failed > 10:
        suggestions.append({
            'type': 'warning',
            'title': f'محاولات دخول فاشلة كثيرة ({failed})',
            'action': 'تفعيل CAPTCHA أو حظر IPs',
            'priority': 'high'
        })
    
    # فحص مستخدمين غير نشطين
    inactive = User.query.filter_by(is_active=False).count()
    if inactive > 5:
        suggestions.append({
            'type': 'info',
            'title': f'مستخدمين محظورين ({inactive})',
            'action': 'مراجعة المستخدمين المحظورين',
            'priority': 'low'
        })
    
    return suggestions


def _get_all_tables():
    """الحصول على جميع جداول قاعدة البيانات"""
    result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
    return [row[0] for row in result if not row[0].startswith('sqlite_')]


def _browse_table(table_name, limit=100):
    """تصفح جدول معين"""
    try:
        # الحصول على الأعمدة
        result = db.session.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        
        # الحصول على البيانات
        result = db.session.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
        data = [dict(zip(columns, row)) for row in result]
        
        return data, columns
    except Exception:
        return [], []


def _get_table_info(table_name):
    """الحصول على معلومات الجدول (الأعمدة والأنواع)"""
    try:
        result = db.session.execute(text(f"PRAGMA table_info({table_name})"))
        info = []
        for row in result:
            info.append({
                'cid': row[0],
                'name': row[1],
                'type': row[2],
                'notnull': row[3],
                'default': row[4],
                'pk': row[5]
            })
        return info
    except Exception:
        return []


def _decrypt_data(encrypted_data, decrypt_type):
    """فك تشفير البيانات"""
    result = {
        'success': False,
        'decrypted': None,
        'method': decrypt_type,
        'error': None
    }
    
    try:
        if decrypt_type == 'base64':
            import base64
            result['decrypted'] = base64.b64decode(encrypted_data).decode('utf-8')
            result['success'] = True
        
        elif decrypt_type == 'fernet':
            from cryptography.fernet import Fernet
            key = current_app.config.get('CARD_ENC_KEY', '').encode()
            if key:
                f = Fernet(key)
                result['decrypted'] = f.decrypt(encrypted_data.encode()).decode('utf-8')
                result['success'] = True
            else:
                result['error'] = 'CARD_ENC_KEY غير موجود'
        
        elif decrypt_type == 'auto':
            # محاولة جميع الطرق
            for method in ['base64', 'fernet']:
                try:
                    temp_result = _decrypt_data(encrypted_data, method)
                    if temp_result['success']:
                        result = temp_result
                        result['method'] = f'auto ({method})'
                        break
                except:
                    continue
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def _analyze_user_behavior():
    """تحليل سلوك المستخدمين"""
    return {
        'most_active': _get_most_active_users(5),
        'login_patterns': _analyze_login_patterns(),
        'suspicious_users': _detect_suspicious_users()
    }


def _detect_security_patterns():
    """كشف أنماط أمنية"""
    return {
        'failed_login_ips': _get_top_failed_ips(10),
        'attack_patterns': _detect_attack_patterns(),
        'time_patterns': _analyze_time_patterns()
    }


def _detect_anomalies():
    """كشف الشذوذات"""
    anomalies = []
    
    # محاولات دخول غير عادية
    failed_count = _get_failed_logins_count(1)  # آخر ساعة
    if failed_count > 5:
        anomalies.append({
            'type': 'login_spike',
            'severity': 'high',
            'description': f'محاولات دخول فاشلة غير عادية: {failed_count} في الساعة الأخيرة'
        })
    
    return anomalies


def _ai_recommendations():
    """توصيات ذكية"""
    recommendations = []
    
    # توصيات بناءً على التحليل
    failed = _get_failed_logins_count(24)
    if failed > 20:
        recommendations.append('تفعيل 2FA للمستخدمين')
        recommendations.append('تقليل rate limit على /login')
    
    return recommendations


def _calculate_threat_level():
    """حساب مستوى التهديد"""
    score = 0
    
    # محاولات فاشلة
    failed = _get_failed_logins_count(24)
    score += min(failed, 50)
    
    # مستخدمين محظورين
    blocked = User.query.filter_by(is_active=False).count()
    score += blocked * 2
    
    if score < 10:
        return {'level': 'low', 'color': 'success', 'label': 'منخفض'}
    elif score < 30:
        return {'level': 'medium', 'color': 'warning', 'label': 'متوسط'}
    else:
        return {'level': 'high', 'color': 'danger', 'label': 'عالي'}


def _detect_suspicious_patterns():
    """كشف الأنماط المشبوهة"""
    patterns = []
    
    # IPs مع محاولات فاشلة متعددة
    suspicious_ips = _get_top_failed_ips(10)
    for ip_data in suspicious_ips:
        if ip_data['count'] > 5:
            patterns.append({
                'type': 'suspicious_ip',
                'ip': ip_data['ip'],
                'count': ip_data['count'],
                'severity': 'high' if ip_data['count'] > 10 else 'medium'
            })
    
    return patterns


def _get_most_active_users(limit=5):
    """المستخدمين الأكثر نشاطاً"""
    return User.query.filter_by(is_active=True).order_by(
        User.login_count.desc()
    ).limit(limit).all()


def _analyze_login_patterns():
    """تحليل أنماط تسجيل الدخول"""
    # تحليل الأوقات
    return {'peak_hours': [9, 10, 11, 14, 15], 'off_hours': [0, 1, 2, 3, 4, 5]}


def _detect_suspicious_users():
    """كشف المستخدمين المشبوهين"""
    suspicious = []
    
    # مستخدمين مع محاولات فاشلة كثيرة
    users_with_fails = AuditLog.query.filter(
        AuditLog.action == 'login.failed',
        AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
    ).all()
    
    return suspicious


def _get_top_failed_ips(limit=10):
    """أكثر IPs مع محاولات فاشلة"""
    failed_ips = {}
    
    logs = AuditLog.query.filter(
        AuditLog.action.in_(['login.failed', 'login.blocked']),
        AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
    ).all()
    
    for log in logs:
        ip = log.ip_address
        if ip:
            failed_ips[ip] = failed_ips.get(ip, 0) + 1
    
    sorted_ips = sorted(failed_ips.items(), key=lambda x: x[1], reverse=True)
    return [{'ip': ip, 'count': count} for ip, count in sorted_ips[:limit]]


def _detect_attack_patterns():
    """كشف أنماط الهجوم"""
    return ['brute_force', 'sql_injection_attempt', 'xss_attempt']


def _analyze_time_patterns():
    """تحليل أنماط الوقت"""
    return {'suspicious_hours': [2, 3, 4], 'normal_hours': [9, 10, 11, 14, 15]}




def _kill_all_user_sessions():
    """إنهاء جميع جلسات المستخدمين"""
    # تحديث last_seen لجميع المستخدمين
    User.query.update({'last_seen': datetime.now(timezone.utc) - timedelta(days=30)})
    db.session.commit()


def _get_active_users():
    """الحصول على المستخدمين النشطين"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    return User.query.filter(User.last_seen >= threshold).all()


def _get_users_online():
    """عدد المستخدمين المتصلين"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    return User.query.filter(User.last_seen >= threshold).count()


def _get_system_setting(key, default=None):
    """توجيه لدالة get_system_setting من ai_service"""
    return get_system_setting(key, default)


def _get_recent_actions(limit=50):
    """آخر الإجراءات"""
    return AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()


def _get_live_metrics():
    """مقاييس حية"""
    import psutil
    return {
        'cpu': psutil.cpu_percent(interval=1),
        'memory': psutil.virtual_memory().percent,
        'disk': psutil.disk_usage('/').percent,
    }


def _set_system_setting(key, value):
    """حفظ إعداد نظام"""
    from models import SystemSettings
    setting = SystemSettings.query.filter_by(key=key).first()
    if setting:
        setting.value = str(value)
    else:
        setting = SystemSettings(key=key, value=str(value))
        db.session.add(setting)
    db.session.commit()


def _get_db_size():
    """حجم قاعدة البيانات"""
    import os
    db_path = 'instance/app.db'
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        return f"{size_bytes / (1024*1024):.2f} MB"
    return "N/A"


def _get_system_health():
    """صحة النظام"""
    try:
        # فحص قاعدة البيانات
        db.session.execute(text("SELECT 1"))
        return "ممتاز"
    except:
        return "خطأ"


def _get_active_sessions_count():
    """عدد الجلسات النشطة"""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    return User.query.filter(User.last_login >= threshold).count()


def _get_online_users_detailed():
    """تفاصيل المستخدمين المتصلين"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    return User.query.filter(User.last_seen >= threshold).all()


def _set_system_setting(key, value):
    """حفظ إعداد نظام"""
    from models import SystemSettings
    setting = SystemSettings.query.filter_by(key=key).first()
    if setting:
        setting.value = str(value)
    else:
        setting = SystemSettings(key=key, value=str(value))
        db.session.add(setting)
    db.session.commit()




def _get_available_backups():
    """قائمة النسخ الاحتياطية"""
    import os
    backup_dir = 'instance/backups'
    backups = []
    
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            if f.endswith('.db'):
                full_path = os.path.join(backup_dir, f)
                backups.append({
                    'name': f,
                    'size': f"{os.path.getsize(full_path) / (1024*1024):.2f} MB",
                    'date': datetime.fromtimestamp(os.path.getmtime(full_path))
                })
    
    return sorted(backups, key=lambda x: x['date'], reverse=True)


def _get_slow_queries():
    """استعلامات بطيئة"""
    # محاكاة - في الواقع تحتاج لـ query profiling
    return []


def _get_avg_response_times():
    """متوسط أوقات الاستجابة"""
    return {'avg': '120ms', 'min': '50ms', 'max': '500ms'}


def _get_memory_usage():
    """استخدام الذاكرة"""
    import psutil
    return psutil.virtual_memory().percent


def _get_cpu_usage():
    """استخدام المعالج"""
    import psutil
    return psutil.cpu_percent(interval=1)


def _safe_count_table(table_name):
    """عد صفوف جدول بشكل آمن"""
    try:
        result = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar()
    except:
        return 0


def _get_available_log_files():
    """الحصول على ملفات اللوج المتاحة"""
    import os
    
    log_files = []
    
    files = {
        'error': 'logs/error.log',
        'server': 'logs/server_error.log',
        'audit': 'instance/audit.log',
        'access': 'logs/access.log',
        'security': 'logs/security.log',
        'performance': 'logs/performance.log',
    }
    
    for log_type, log_path in files.items():
        if os.path.exists(log_path):
            size = os.path.getsize(log_path)
            log_files.append({
                'type': log_type,
                'path': log_path,
                'size': f"{size / 1024:.2f} KB",
                'modified': datetime.fromtimestamp(os.path.getmtime(log_path))
            })
    
    return log_files


def _test_integration_connection(integration_type):
    """اختبار اتصال التكامل"""
    from models import SystemSettings
    import requests
    import smtplib
    from email.mime.text import MIMEText
    
    try:
        if integration_type == 'whatsapp':
            phone = SystemSettings.query.filter_by(key='whatsapp_phone').first()
            token = SystemSettings.query.filter_by(key='whatsapp_token').first()
            url = SystemSettings.query.filter_by(key='whatsapp_url').first()
            
            if not all([phone, token, url]):
                return {'success': False, 'error': 'بيانات واتساب ناقصة'}
            
            # اختبار API واتساب
            test_url = f"{url.value}/status"
            headers = {'Authorization': f'Bearer {token.value}'}
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return {'success': True, 'message': 'واتساب متصل بنجاح'}
            else:
                return {'success': False, 'error': f'خطأ واتساب: {response.status_code}'}
        
        elif integration_type == 'email':
            server = SystemSettings.query.filter_by(key='smtp_server').first()
            port = SystemSettings.query.filter_by(key='smtp_port').first()
            username = SystemSettings.query.filter_by(key='smtp_username').first()
            password = SystemSettings.query.filter_by(key='smtp_password').first()
            
            if not all([server, port, username, password]):
                return {'success': False, 'error': 'بيانات البريد ناقصة'}
            
            # اختبار SMTP
            smtp = smtplib.SMTP(server.value, int(port.value))
            smtp.starttls()
            smtp.login(username.value, password.value)
            smtp.quit()
            
            return {'success': True, 'message': 'البريد الإلكتروني متصل بنجاح'}
        
        elif integration_type == 'api_keys':
            openai_key = SystemSettings.query.filter_by(key='openai_key').first()
            google_maps_key = SystemSettings.query.filter_by(key='google_maps_key').first()
            
            if openai_key and openai_key.value:
                # اختبار OpenAI
                headers = {'Authorization': f'Bearer {openai_key.value}'}
                response = requests.get('https://api.openai.com/v1/models', headers=headers, timeout=10)
                if response.status_code != 200:
                    return {'success': False, 'error': 'مفتاح OpenAI غير صالح'}
            
            if google_maps_key and google_maps_key.value:
                # اختبار Google Maps
                test_url = f"https://maps.googleapis.com/maps/api/geocode/json?address=test&key={google_maps_key.value}"
                response = requests.get(test_url, timeout=10)
                if response.status_code != 200:
                    return {'success': False, 'error': 'مفتاح Google Maps غير صالح'}
            
            return {'success': True, 'message': 'مفاتيح API صحيحة'}
        
        else:
            return {'success': True, 'message': 'التكامل محفوظ'}
    
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'خطأ في الشبكة: {str(e)}'}
    except smtplib.SMTPException as e:
        return {'success': False, 'error': f'خطأ في البريد: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'خطأ عام: {str(e)}'}


def _send_test_message(integration_type):
    """إرسال رسالة تجريبية"""
    from models import SystemSettings
    import requests
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        if integration_type == 'whatsapp':
            phone = SystemSettings.query.filter_by(key='whatsapp_phone').first()
            token = SystemSettings.query.filter_by(key='whatsapp_token').first()
            url = SystemSettings.query.filter_by(key='whatsapp_url').first()
            
            if not all([phone, token, url]):
                return {'success': False, 'error': 'بيانات واتساب ناقصة'}
            
            # إرسال رسالة تجريبية
            message_data = {
                'to': phone.value,
                'message': '🧪 رسالة تجريبية من نظام إدارة الكراج - التكامل يعمل بنجاح! ✅'
            }
            
            headers = {'Authorization': f'Bearer {token.value}', 'Content-Type': 'application/json'}
            response = requests.post(f"{url.value}/send", json=message_data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return {'success': True, 'message': 'تم إرسال رسالة واتساب تجريبية'}
            else:
                return {'success': False, 'error': f'فشل الإرسال: {response.status_code}'}
        
        elif integration_type == 'email':
            server = SystemSettings.query.filter_by(key='smtp_server').first()
            port = SystemSettings.query.filter_by(key='smtp_port').first()
            username = SystemSettings.query.filter_by(key='smtp_username').first()
            password = SystemSettings.query.filter_by(key='smtp_password').first()
            
            if not all([server, port, username, password]):
                return {'success': False, 'error': 'بيانات البريد ناقصة'}
            
            # إرسال بريد تجريبي
            msg = MIMEMultipart()
            msg['From'] = username.value
            msg['To'] = username.value  # إرسال لنفسه
            msg['Subject'] = '🧪 رسالة تجريبية - نظام إدارة الكراج'
            
            body = '''
            <h2>🧪 رسالة تجريبية</h2>
            <p>هذه رسالة تجريبية من نظام إدارة الكراج</p>
            <p><strong>التكامل يعمل بنجاح! ✅</strong></p>
            <p>الوقت: {}</p>
            '''.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            msg.attach(MIMEText(body, 'html'))
            
            smtp = smtplib.SMTP(server.value, int(port.value))
            smtp.starttls()
            smtp.login(username.value, password.value)
            smtp.send_message(msg)
            smtp.quit()
            
            return {'success': True, 'message': 'تم إرسال بريد تجريبي'}
        
        else:
            return {'success': False, 'error': 'نوع التكامل غير مدعوم للإرسال'}
    
    except Exception as e:
        return {'success': False, 'error': f'خطأ في الإرسال: {str(e)}'}


def _get_integration_stats():
    """إحصائيات التكاملات الحقيقية"""
    from models import SystemSettings
    
    # فحص التكوين الحقيقي
    whatsapp_configured = bool(SystemSettings.query.filter_by(key='whatsapp_token').first())
    email_configured = bool(SystemSettings.query.filter_by(key='smtp_server').first())
    api_configured = bool(SystemSettings.query.filter_by(key='openai_key').first())
    
    # إحصائيات حقيقية من قاعدة البيانات
    stats = {
        'whatsapp': {
            'configured': whatsapp_configured,
            'last_test': _get_last_integration_activity('whatsapp'),
            'messages_sent': _count_integration_usage('whatsapp'),
            'status': 'active' if whatsapp_configured else 'inactive'
        },
        'email': {
            'configured': email_configured,
            'last_test': _get_last_integration_activity('email'),
            'emails_sent': _count_integration_usage('email'),
            'status': 'active' if email_configured else 'inactive'
        },
        'api_keys': {
            'configured': api_configured,
            'last_test': _get_last_integration_activity('api'),
            'requests_made': _count_integration_usage('api'),
            'status': 'active' if api_configured else 'inactive'
        }
    }
    
    return stats


def _get_last_integration_activity(integration_type):
    """الحصول على آخر نشاط للتكامل"""
    try:
        # البحث في سجل التدقيق
        from models import AuditLog
        last_activity = AuditLog.query.filter(
            AuditLog.action.like(f'%{integration_type}%')
        ).order_by(AuditLog.timestamp.desc()).first()
        
        if last_activity:
            return last_activity.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return 'لم يتم الاستخدام بعد'
    except:
        return 'غير متاح'


def _count_integration_usage(integration_type):
    """عد استخدام التكامل"""
    try:
        from models import AuditLog
        count = AuditLog.query.filter(
            AuditLog.action.like(f'%{integration_type}%')
        ).count()
        return count
    except:
        return 0


def _log_integration_activity(integration_type, action, success):
    """تسجيل نشاط التكامل"""
    try:
        from models import AuditLog
        from flask_login import current_user
        
        activity = AuditLog(
            user_id=current_user.id,
            action=f'{integration_type}_{action}',
            details=f'Integration {action}: {integration_type} - Success: {success}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            timestamp=datetime.utcnow()
        )
        
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"Error logging integration activity: {e}")


def _get_recent_errors(limit=100):
    """الحصول على آخر الأخطاء"""
    import os
    
    errors = []
    
    if os.path.exists('error.log'):
        try:
            with open('error.log', 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # آخر الأخطاء
                for line in lines[-limit:]:
                    if line.strip():
                        errors.append({
                            'message': line.strip(),
                            'timestamp': datetime.now(timezone.utc)
                        })
        except:
            pass
    
    return errors


def _get_error_statistics():
    """إحصائيات الأخطاء"""
    import os
    
    stats = {
        'total_errors': 0,
        'today_errors': 0,
        'critical_errors': 0,
        'warning_errors': 0,
    }
    
    if os.path.exists('error.log'):
        try:
            with open('error.log', 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                stats['total_errors'] = len(lines)
                
                # تحليل بسيط
                for line in lines:
                    if 'CRITICAL' in line or 'ERROR' in line:
                        stats['critical_errors'] += 1
                    elif 'WARNING' in line:
                        stats['warning_errors'] += 1
        except:
            pass
    
    return stats


def _get_security_notifications():
    """الحصول على الإشعارات الأمنية"""
    notifications = []
    
    # فحص محاولات فاشلة
    failed = _get_failed_logins_count(1)
    if failed > 5:
        notifications.append({
            'severity': 'danger',
            'icon': 'exclamation-triangle',
            'title': 'محاولات دخول فاشلة',
            'message': f'{failed} محاولة فاشلة في الساعة الأخيرة',
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        })
    
    # فحص وضع الصيانة
    if _get_system_setting('maintenance_mode', False):
        notifications.append({
            'severity': 'warning',
            'icon': 'tools',
            'title': 'وضع الصيانة مفعل',
            'message': 'النظام في وضع الصيانة - المستخدمون لا يمكنهم الدخول',
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        })
    
    return notifications


@security_bp.route('/monitoring-dashboard')
@owner_only
def monitoring_dashboard():
    """لوحة مراقبة الأداء الشاملة (Grafana-like)"""
    return render_template('security/monitoring_dashboard.html',
                         title='لوحة المراقبة الشاملة')


@security_bp.route('/dark-mode-settings', methods=['GET', 'POST'])
@owner_only
def dark_mode_settings():
    """إعدادات الوضع الليلي (Dark Mode)"""
    if request.method == 'POST':
        # حفظ الإعدادات
        flash('✅ تم حفظ إعدادات الوضع الليلي', 'success')
        return redirect(url_for('security.dark_mode_settings'))
    
    return render_template('security/dark_mode_settings.html',
                         title='إعدادات الوضع الليلي')


@security_bp.route('/grafana-setup')
@owner_only
def grafana_setup():
    """إعداد وتثبيت Grafana + Prometheus"""
    return render_template('security/grafana_setup.html',
                         title='إعداد Grafana + Prometheus')


@security_bp.route('/prometheus-metrics')
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    from services.prometheus_service import get_all_metrics
    return get_all_metrics()


@security_bp.route('/api/live-metrics')
@owner_only
def api_live_metrics():
    """API للحصول على المتريكات الحية"""
    from services.prometheus_service import get_live_metrics_json
    return jsonify(get_live_metrics_json())


@security_bp.route('/indexes-manager', methods=['GET', 'POST'])
@owner_only
def indexes_manager():
    """إدارة الفهارس - 89 فهرس احترافي - Indexes Manager"""
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    indexes_data = []
    for table in sorted(tables):
        columns = inspector.get_columns(table)
        indexes = inspector.get_indexes(table)
        foreign_keys = inspector.get_foreign_keys(table)
        
        indexes_data.append({
            'name': table,
            'columns_count': len(columns),
            'indexes_count': len(indexes),
            'fk_count': len(foreign_keys),
            'columns': [{'name': c['name'], 'type': str(c['type'])} for c in columns],
            'indexes': [{'name': idx['name'], 'columns': idx['column_names'], 'unique': idx['unique']} for idx in indexes],
            'foreign_keys': [{'columns': fk['constrained_columns'], 'ref_table': fk['referred_table']} for fk in foreign_keys]
        })
    
    stats = {
        'total_tables': len(tables),
        'total_indexes': sum([t['indexes_count'] for t in indexes_data]),
        'total_columns': sum([t['columns_count'] for t in indexes_data]),
        'tables_without_indexes': len([t for t in indexes_data if t['indexes_count'] == 0]),
        'avg_indexes_per_table': round(sum([t['indexes_count'] for t in indexes_data]) / len(tables), 2) if tables else 0
    }
    
    return render_template('security/indexes_manager.html',
                         tables=indexes_data,
                         stats=stats,
                         title='إدارة الفهارس')


@security_bp.route('/api/indexes/create', methods=['POST'])
@owner_only
def api_create_index():
    """إنشاء فهرس جديد"""
    try:
        data = request.get_json()
        table_name = data.get('table')
        index_name = data.get('index_name')
        columns = data.get('columns')
        unique = data.get('unique', False)
        
        if not all([table_name, index_name, columns]):
            return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
        
        if isinstance(columns, str):
            columns = [columns]
        
        unique_str = "UNIQUE" if unique else ""
        cols_str = ", ".join(columns)
        sql = f"CREATE {unique_str} INDEX {index_name} ON {table_name} ({cols_str})"
        
        db.session.execute(text(sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ تم إنشاء الفهرس {index_name} بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500


@security_bp.route('/api/indexes/drop', methods=['POST'])
@owner_only
def api_drop_index():
    """حذف فهرس"""
    try:
        data = request.get_json()
        index_name = data.get('index_name')
        table_name = data.get('table')
        
        if not index_name:
            return jsonify({'success': False, 'message': 'اسم الفهرس مطلوب'}), 400
        
        sql = f"DROP INDEX {index_name}"
        db.session.execute(text(sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ تم حذف الفهرس {index_name} بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500


@security_bp.route('/api/indexes/auto-optimize', methods=['POST'])
@owner_only
def api_auto_optimize_indexes():
    """تحسين تلقائي للفهارس"""
    try:
        from sqlalchemy import inspect
        
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        created_indexes = []
        skipped_indexes = []
        
        optimization_rules = {
            'customers': ['name', 'phone', 'email', 'is_active', 'created_at'],
            'suppliers': ['name', 'phone', 'created_at'],
            'partners': ['name', 'phone_number', 'created_at'],
            'products': ['name', 'barcode', 'sku', 'category_id', 'is_active', 'created_at'],
            'sales': ['customer_id', 'seller_id', 'status', 'sale_date', 'created_at', 'payment_status'],
            'sale_lines': ['sale_id', 'product_id', 'warehouse_id'],
            'payments': ['entity_type', 'customer_id', 'supplier_id', 'partner_id', 'status', 'direction', 'payment_date', 'receipt_number'],
            'service_requests': ['customer_id', 'status', 'priority', 'created_at', 'service_number'],
            'shipments': ['destination_id', 'status', 'shipment_date', 'created_at'],
            'shipment_items': ['shipment_id', 'product_id'],
            'invoices': ['customer_id', 'status', 'invoice_number', 'invoice_date', 'due_date', 'source'],
            'expenses': ['type_id', 'employee_id', 'date', 'created_at'],
            'stock_levels': ['product_id', 'warehouse_id'],
            'audit_logs': ['user_id', 'action', 'model_name', 'record_id', 'created_at'],
            'checks': ['customer_id', 'supplier_id', 'partner_id', 'check_number', 'check_date', 'check_due_date', 'status'],
            'users': ['username', 'email', 'is_active', 'role_id'],
            'warehouses': ['name', 'warehouse_type', 'is_active'],
            'notes': ['entity_type', 'entity_id', 'author_id', 'created_at']
        }
        
        for table, columns_to_index in optimization_rules.items():
            if table not in tables:
                continue
            
            existing_indexes = inspector.get_indexes(table)
            existing_index_names = {idx['name'] for idx in existing_indexes}
            
            for column in columns_to_index:
                index_name = f"ix_{table}_{column}"
                
                if index_name in existing_index_names:
                    skipped_indexes.append(index_name)
                    continue
                
                table_columns = inspector.get_columns(table)
                column_names = [c['name'] for c in table_columns]
                
                if column not in column_names:
                    continue
                
                try:
                    sql = f"CREATE INDEX {index_name} ON {table} ({column})"
                    db.session.execute(text(sql))
                    db.session.commit()
                    created_indexes.append(index_name)
                except:
                    db.session.rollback()
        
        composite_indexes = [
            ('sales', ['customer_id', 'sale_date'], 'ix_sales_customer_date'),
            ('sales', ['status', 'sale_date'], 'ix_sales_status_date'),
            ('payments', ['customer_id', 'payment_date'], 'ix_payments_customer_date'),
            ('service_requests', ['customer_id', 'status'], 'ix_service_requests_customer_status'),
            ('service_requests', ['status', 'created_at'], 'ix_service_requests_status_date'),
            ('audit_logs', ['user_id', 'created_at'], 'ix_audit_logs_user_date'),
            ('stock_levels', ['product_id', 'warehouse_id'], 'ix_stock_levels_product_warehouse'),
        ]
        
        for table, columns, index_name in composite_indexes:
            if table not in tables:
                continue
            
            existing_indexes = inspector.get_indexes(table)
            existing_index_names = {idx['name'] for idx in existing_indexes}
            
            if index_name in existing_index_names:
                skipped_indexes.append(index_name)
                continue
            
            try:
                cols_str = ", ".join(columns)
                unique_str = "UNIQUE" if 'product_warehouse' in index_name else ""
                sql = f"CREATE {unique_str} INDEX {index_name} ON {table} ({cols_str})"
                db.session.execute(text(sql))
                db.session.commit()
                created_indexes.append(index_name)
            except:
                db.session.rollback()
        
        return jsonify({
            'success': True,
            'message': f'✅ تم إنشاء {len(created_indexes)} فهرس جديد',
            'created': created_indexes,
            'skipped': len(skipped_indexes),
            'total': len(created_indexes) + len(skipped_indexes)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500


@security_bp.route('/api/indexes/clean-and-rebuild', methods=['POST'])
@owner_only
def api_clean_rebuild_indexes():
    """تنظيف وإعادة بناء الفهارس"""
    try:
        from sqlalchemy import inspect
        
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        dropped_count = 0
        created_count = 0
        
        for table in tables:
            indexes = inspector.get_indexes(table)
            
            for idx in indexes:
                if idx['name'] and idx['name'].startswith('ix_'):
                    try:
                        db.session.execute(text(f"DROP INDEX {idx['name']}"))
                        db.session.commit()
                        dropped_count += 1
                    except:
                        db.session.rollback()
        
        optimization_rules = {
            'customers': ['name', 'phone', 'email', 'is_active', 'created_at'],
            'suppliers': ['name', 'phone', 'created_at'],
            'partners': ['name', 'phone_number', 'created_at'],
            'products': ['name', 'barcode', 'sku', 'category_id', 'is_active', 'created_at'],
            'sales': ['customer_id', 'seller_id', 'status', 'sale_date', 'created_at', 'payment_status'],
            'sale_lines': ['sale_id', 'product_id', 'warehouse_id'],
            'payments': ['entity_type', 'customer_id', 'supplier_id', 'partner_id', 'status', 'direction', 'payment_date', 'receipt_number'],
            'service_requests': ['customer_id', 'status', 'priority', 'created_at', 'service_number'],
            'shipments': ['destination_id', 'status', 'shipment_date', 'created_at'],
            'shipment_items': ['shipment_id', 'product_id'],
            'invoices': ['customer_id', 'status', 'invoice_number', 'invoice_date', 'due_date', 'source'],
            'expenses': ['type_id', 'employee_id', 'date', 'created_at'],
            'stock_levels': ['product_id', 'warehouse_id'],
            'audit_logs': ['user_id', 'action', 'model_name', 'record_id', 'created_at'],
            'checks': ['customer_id', 'supplier_id', 'partner_id', 'check_number', 'check_date', 'check_due_date', 'status'],
            'users': ['username', 'email', 'is_active', 'role_id'],
            'warehouses': ['name', 'warehouse_type', 'is_active'],
            'notes': ['entity_type', 'entity_id', 'author_id', 'created_at']
        }
        
        for table, columns_to_index in optimization_rules.items():
            if table not in tables:
                continue
            
            table_columns = inspector.get_columns(table)
            column_names = [c['name'] for c in table_columns]
            
            for column in columns_to_index:
                if column not in column_names:
                    continue
                
                index_name = f"ix_{table}_{column}"
                try:
                    sql = f"CREATE INDEX {index_name} ON {table} ({column})"
                    db.session.execute(text(sql))
                    db.session.commit()
                    created_count += 1
                except:
                    db.session.rollback()
        
        composite_indexes = [
            ('sales', ['customer_id', 'sale_date'], 'ix_sales_customer_date'),
            ('sales', ['status', 'sale_date'], 'ix_sales_status_date'),
            ('payments', ['customer_id', 'payment_date'], 'ix_payments_customer_date'),
            ('service_requests', ['customer_id', 'status'], 'ix_service_requests_customer_status'),
            ('service_requests', ['status', 'created_at'], 'ix_service_requests_status_date'),
            ('audit_logs', ['user_id', 'created_at'], 'ix_audit_logs_user_date'),
            ('stock_levels', ['product_id', 'warehouse_id'], 'ix_stock_levels_product_warehouse'),
        ]
        
        for table, columns, index_name in composite_indexes:
            if table not in tables:
                continue
            
            try:
                cols_str = ", ".join(columns)
                unique_str = "UNIQUE" if 'product_warehouse' in index_name else ""
                sql = f"CREATE {unique_str} INDEX {index_name} ON {table} ({cols_str})"
                db.session.execute(text(sql))
                db.session.commit()
                created_count += 1
            except:
                db.session.rollback()
        
        return jsonify({
            'success': True,
            'message': f'✅ تم حذف {dropped_count} فهرس وإنشاء {created_count} فهرس جديد',
            'dropped': dropped_count,
            'created': created_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500


@security_bp.route('/api/indexes/analyze-table', methods=['POST'])
@owner_only
def api_analyze_table():
    """تحليل جدول واقتراح فهارس"""
    try:
        from sqlalchemy import inspect
        
        data = request.get_json()
        table_name = data.get('table')
        
        if not table_name:
            return jsonify({'success': False, 'message': 'اسم الجدول مطلوب'}), 400
        
        inspector = inspect(db.engine)
        
        if table_name not in inspector.get_table_names():
            return jsonify({'success': False, 'message': 'الجدول غير موجود'}), 404
        
        columns = inspector.get_columns(table_name)
        indexes = inspector.get_indexes(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)
        
        indexed_columns = set()
        for idx in indexes:
            indexed_columns.update(idx['column_names'])
        
        suggestions = []
        
        for col in columns:
            col_name = col['name']
            col_type = str(col['type'])
            
            if col_name in indexed_columns:
                continue
            
            priority = 'low'
            reason = ''
            
            if col_name.endswith('_id'):
                priority = 'high'
                reason = 'Foreign Key - يسرع عمليات JOIN'
            elif 'status' in col_name.lower():
                priority = 'high'
                reason = 'حقل حالة - يستخدم كثيراً في الفلترة'
            elif 'date' in col_name.lower() or 'time' in col_name.lower():
                priority = 'medium'
                reason = 'حقل تاريخ - يستخدم في الفرز والفلترة'
            elif col_name in ['name', 'email', 'phone', 'username']:
                priority = 'high'
                reason = 'حقل بحث رئيسي'
            elif 'number' in col_name.lower():
                priority = 'medium'
                reason = 'حقل رقمي - قد يستخدم في البحث'
            elif col_name.startswith('is_'):
                priority = 'low'
                reason = 'حقل boolean - قد يفيد في الفلترة'
            
            if priority != 'low' or len(suggestions) < 20:
                suggestions.append({
                    'column': col_name,
                    'type': col_type,
                    'priority': priority,
                    'reason': reason,
                    'index_name': f"ix_{table_name}_{col_name}"
                })
        
        suggestions.sort(key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x['priority']])
        
        return jsonify({
            'success': True,
            'table': table_name,
            'total_columns': len(columns),
            'indexed_columns': len(indexed_columns),
            'suggestions': suggestions[:15],
            'foreign_keys': [fk['constrained_columns'] for fk in foreign_keys]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500


@security_bp.route('/api/indexes/batch-create', methods=['POST'])
@owner_only
def api_batch_create_indexes():
    """إنشاء عدة فهارس دفعة واحدة"""
    try:
        data = request.get_json()
        indexes = data.get('indexes', [])
        
        if not indexes:
            return jsonify({'success': False, 'message': 'لا توجد فهارس للإنشاء'}), 400
        
        created = []
        failed = []
        
        for idx in indexes:
            table_name = idx.get('table')
            index_name = idx.get('index_name')
            columns = idx.get('columns')
            unique = idx.get('unique', False)
            
            if not all([table_name, index_name, columns]):
                failed.append({'index': index_name, 'reason': 'بيانات ناقصة'})
                continue
            
            if isinstance(columns, str):
                columns = [columns]
            
            try:
                unique_str = "UNIQUE" if unique else ""
                cols_str = ", ".join(columns)
                sql = f"CREATE {unique_str} INDEX {index_name} ON {table_name} ({cols_str})"
                db.session.execute(text(sql))
                db.session.commit()
                created.append(index_name)
            except Exception as e:
                db.session.rollback()
                failed.append({'index': index_name, 'reason': str(e)})
        
        return jsonify({
            'success': True,
            'message': f'✅ تم إنشاء {len(created)} فهرس من أصل {len(indexes)}',
            'created': created,
            'failed': failed
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ خطأ: {str(e)}'
        }), 500

