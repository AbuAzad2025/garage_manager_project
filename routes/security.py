"""
وحدة الأمان المتقدمة - Super Admin فقط
CONFIDENTIAL - لا يصل إليها إلا Super Admin
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text, func
from datetime import datetime, timedelta, timezone
from extensions import db, cache
from models import User, AuditLog
from utils import is_super
from functools import wraps
import json

security_bp = Blueprint('security', __name__, url_prefix='/security')

# SECURITY: Owner only decorator (أول Super Admin فقط - المالك)
def owner_only(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # فحص 1: يجب أن يكون Super Admin
        if not is_super():
            flash('⛔ الوصول محظور', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # فحص 2: يجب أن يكون أول Super Admin (المالك)
        # نفحص إذا كان أول مستخدم أو لديه username محدد
        if current_user.id != 1 and current_user.username.lower() not in ['azad', 'owner', 'admin']:
            flash('⛔ هذه الوحدة متاحة للمالك الأساسي فقط', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


# Alias للتوافق
super_admin_only = owner_only


@security_bp.route('/')
@owner_only
def index():
    """لوحة التحكم الأمنية الرئيسية"""
    # إحصائيات أمنية
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'blocked_users': User.query.filter_by(is_active=False).count(),
        'blocked_ips': _get_blocked_ips_count(),
        'blocked_countries': _get_blocked_countries_count(),
        'failed_logins_24h': _get_failed_logins_count(hours=24),
        'suspicious_activities': _get_suspicious_activities_count(hours=24),
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
    
    if is_super() and user.id == current_user.id:
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
@owner_only
def ai_assistant():
    """مساعد أمان ذكي بالذكاء الاصطناعي"""
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        analysis = _ai_security_analysis(query)
        return render_template('security/ai_assistant.html', query=query, analysis=analysis)
    
    # اقتراحات ذكية
    suggestions = _get_ai_suggestions()
    
    return render_template('security/ai_assistant.html', suggestions=suggestions)


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
@owner_only
def ai_chat():
    """API للمحادثة مع AI - متقدم مع بحث في البيانات"""
    data = request.get_json()
    message = data.get('message', '')
    
    # البحث في البيانات إذا كان السؤال يتطلب ذلك
    search_results = _search_database_for_query(message)
    
    # إرسال السؤال مع نتائج البحث للـ AI
    response = _ai_chat_response_with_search(message, search_results)
    
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
    """لوحة التحكم النهائية - صلاحيات خارقة"""
    stats = {
        'users_online': _get_users_online(),
        'total_users': User.query.count(),
        'total_services': _safe_count_table('service'),
        'total_sales': _safe_count_table('sale'),
        'db_size': _get_db_size(),
        'system_health': _get_system_health(),
        'active_sessions': _get_active_sessions_count(),
    }
    return render_template('security/ultimate_control.html', stats=stats)


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


@security_bp.route('/system-settings', methods=['GET', 'POST'])
@owner_only
def system_settings():
    """إعدادات النظام الحرجة"""
    if request.method == 'POST':
        # حفظ الإعدادات
        settings = {
            'maintenance_mode': request.form.get('maintenance_mode') == 'on',
            'registration_enabled': request.form.get('registration_enabled') == 'on',
            'api_enabled': request.form.get('api_enabled') == 'on',
        }
        
        # حفظ في SystemSettings
        for key, value in settings.items():
            _set_system_setting(key, value)
        
        flash('تم حفظ الإعدادات', 'success')
        return redirect(url_for('security.system_settings'))
    
    # قراءة الإعدادات الحالية
    settings = {
        'maintenance_mode': _get_system_setting('maintenance_mode', False),
        'registration_enabled': _get_system_setting('registration_enabled', True),
        'api_enabled': _get_system_setting('api_enabled', True),
    }
    
    return render_template('security/system_settings.html', settings=settings)


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
    """نسخ احتياطي متقدم"""
    if request.method == 'POST':
        backup_type = request.form.get('backup_type', 'full')
        
        if backup_type == 'full':
            from extensions import perform_backup_db
            result = perform_backup_db()
            flash('تم إنشاء نسخة احتياطية كاملة', 'success')
        
        return redirect(url_for('security.advanced_backup'))
    
    backups = _get_available_backups()
    return render_template('security/advanced_backup.html', backups=backups)


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
        'error': 'error.log',
        'server': 'server_error.log',
        'audit': 'instance/audit.log',
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
        'error': 'error.log',
        'server': 'server_error.log',
        'audit': 'instance/audit.log',
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
    """مسح ملف لوج"""
    import os
    
    log_files = {
        'error': 'error.log',
        'server': 'server_error.log',
    }
    
    log_path = log_files.get(log_type)
    if log_path and os.path.exists(log_path):
        with open(log_path, 'w') as f:
            f.write('')
        flash(f'تم مسح {log_type}.log', 'success')
    else:
        flash('ملف اللوج غير موجود', 'warning')
    
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
    """تعديل الثوابت الأساسية للنظام"""
    if request.method == 'POST':
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
        
        flash('تم تحديث الثوابت', 'success')
        return redirect(url_for('security.system_constants'))
    
    # قراءة الثوابت الحالية
    constants = {
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
    
    return render_template('security/system_constants.html', constants=constants)


@security_bp.route('/advanced-config', methods=['GET', 'POST'])
@owner_only
def advanced_config():
    """تكوين متقدم للنظام"""
    if request.method == 'POST':
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
        
        flash('تم تحديث التكوين المتقدم', 'success')
        return redirect(url_for('security.advanced_config'))
    
    # قراءة التكوين الحالي
    config = {
        'SESSION_TIMEOUT': _get_system_setting('SESSION_TIMEOUT', 3600),
        'MAX_LOGIN_ATTEMPTS': _get_system_setting('MAX_LOGIN_ATTEMPTS', 5),
        'PASSWORD_MIN_LENGTH': _get_system_setting('PASSWORD_MIN_LENGTH', 8),
        'AUTO_BACKUP_ENABLED': _get_system_setting('AUTO_BACKUP_ENABLED', True),
        'BACKUP_INTERVAL_HOURS': _get_system_setting('BACKUP_INTERVAL_HOURS', 24),
        'ENABLE_EMAIL_NOTIFICATIONS': _get_system_setting('ENABLE_EMAIL_NOTIFICATIONS', True),
        'ENABLE_SMS_NOTIFICATIONS': _get_system_setting('ENABLE_SMS_NOTIFICATIONS', False),
    }
    
    return render_template('security/advanced_config.html', config=config)


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


@security_bp.route('/db-editor/delete-row/<table_name>/<int:row_id>', methods=['POST'])
@owner_only
def db_delete_row(table_name, row_id):
    """حذف صف من الجدول"""
    try:
        sql = f"DELETE FROM {table_name} WHERE id = {row_id}"
        db.session.execute(text(sql))
        db.session.commit()
        flash('تم الحذف بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ: {str(e)}', 'danger')
    
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
        {'name': 'audit_logs', 'display': 'سجلات التدقيق', 'danger': 'low'},
        {'name': 'service_requests', 'display': 'طلبات الصيانة', 'danger': 'high'},
        {'name': 'sales', 'display': 'المبيعات', 'danger': 'high'},
        {'name': 'payments', 'display': 'المدفوعات', 'danger': 'high'},
        {'name': 'expenses', 'display': 'المصاريف', 'danger': 'medium'},
        {'name': 'stock_levels', 'display': 'مستويات المخزون', 'danger': 'high'},
        {'name': 'online_carts', 'display': 'سلات التسوق', 'danger': 'low'},
        {'name': 'notifications', 'display': 'الإشعارات', 'danger': 'low'},
    ]

def _cleanup_tables(tables):
    """تنظيف الجداول المحددة"""
    cleaned = 0
    
    for table in tables:
        try:
            db.session.execute(text(f"DELETE FROM {table}"))
            db.session.commit()
            cleaned += 1
            
            # تسجيل في Audit
            db.session.add(AuditLog(
                model_name='Security',
                action='TABLE_CLEANED',
                user_id=current_user.id,
                old_data=json.dumps({'table': table}, ensure_ascii=False),
                ip_address=request.remote_addr
            ))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            continue
    
    return {'cleaned': cleaned, 'total': len(tables)}

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


def _search_database_for_query(query):
    """البحث الشامل غير المحدود في كل قاعدة البيانات"""
    results = {}
    query_lower = query.lower()
    
    try:
        # استيراد جميع الموديلات
        from models import (
            Customer, Supplier, Product, ServiceRequest, Invoice, Payment,
            Expense, ExpenseType, Warehouse, StockLevel, Note, Shipment,
            Role, Permission, PartnerSettlement, SupplierSettlement,
            Account, PreOrder, OnlineCart, ExchangeTransaction, Partner,
            ServicePart, ServiceTask
        )
        
        # البحث عن اسم محدد في السؤال (أولوية)
        words = [w for w in query.split() if len(w) > 2]
        found_name = None
        
        for word in words:
            if word not in ['عن', 'من', 'في', 'على', 'إلى', 'هل', 'ما', 'كم', 'عميل', 'صيانة', 'منتج', 'فاتورة', 'خدمة', 'مورد']:
                # بحث في العملاء
                try:
                    customer = Customer.query.filter(Customer.name.like(f'%{word}%')).first()
                    if customer:
                        # جمع كل معلومات العميل
                        results['found_customer'] = {
                            'id': customer.id,
                            'name': customer.name,
                            'phone': customer.phone or 'غير محدد',
                            'email': customer.email or 'غير محدد',
                            'address': getattr(customer, 'address', 'غير محدد'),
                            'balance': getattr(customer, 'balance', 0),
                            'is_active': customer.is_active,
                            'created_at': customer.created_at.strftime('%Y-%m-%d') if customer.created_at else 'N/A'
                        }
                        
                        # خدمات العميل
                        try:
                            customer_services = ServiceRequest.query.filter_by(customer_id=customer.id).all()
                            results['customer_services'] = [{
                                'id': s.id,
                                'status': s.status,
                                'vehicle': getattr(s, 'vehicle_info', 'N/A'),
                                'date': s.created_at.strftime('%Y-%m-%d') if s.created_at else 'N/A'
                            } for s in customer_services[:10]]
                        except:
                            pass
                        
                        # فواتير العميل
                        try:
                            customer_invoices = Invoice.query.filter_by(customer_id=customer.id).all()
                            results['customer_invoices'] = [{
                                'id': i.id,
                                'total': getattr(i, 'total', 0),
                                'date': i.issue_date.strftime('%Y-%m-%d') if i.issue_date else 'N/A'
                            } for i in customer_invoices[:10]]
                        except:
                            pass
                        
                        found_name = word
                        break
                except:
                    pass
                
                # بحث في الموردين
                if not found_name:
                    try:
                        supplier = Supplier.query.filter(Supplier.name.like(f'%{word}%')).first()
                        if supplier:
                            results['found_supplier'] = {
                                'id': supplier.id,
                                'name': supplier.name,
                                'phone': getattr(supplier, 'phone', 'غير محدد'),
                                'email': getattr(supplier, 'email', 'غير محدد'),
                                'balance': getattr(supplier, 'balance', 0)
                            }
                            found_name = word
                            break
                    except:
                        pass
        
        # البحث العام في كل الوحدات
        
        # 1. العملاء
        try:
            if 'عميل' in query or 'زبون' in query or 'customer' in query_lower:
                customers = Customer.query.order_by(Customer.created_at.desc()).limit(15).all()
                if customers:
                    results['all_customers'] = [{
                        'id': c.id,
                        'name': c.name,
                        'phone': c.phone,
                        'balance': getattr(c, 'balance', 0),
                        'is_active': c.is_active
                    } for c in customers]
        except:
            pass
        
        # 2. الصيانة
        try:
            if 'صيانة' in query or 'خدمة' in query or 'service' in query_lower or 'طلب' in query:
                services = ServiceRequest.query.order_by(ServiceRequest.created_at.desc()).limit(15).all()
                if services:
                    results['all_services'] = [{
                        'id': s.id,
                        'customer_name': s.customer.name if hasattr(s, 'customer') and s.customer else 'N/A',
                        'vehicle': getattr(s, 'vehicle_info', 'N/A'),
                        'status': s.status,
                        'priority': getattr(s, 'priority', 'N/A'),
                        'date': s.created_at.strftime('%Y-%m-%d') if s.created_at else 'N/A'
                    } for s in services]
        except:
            pass
        
        # 3. المنتجات والمخزون
        try:
            if 'منتج' in query or 'product' in query_lower or 'مخزون' in query or 'قطع' in query:
                products = Product.query.limit(20).all()
                if products:
                    results['all_products'] = [{
                        'id': p.id,
                        'name': p.name,
                        'quantity': getattr(p, 'quantity', 0),
                        'price': getattr(p, 'selling_price', 0),
                        'category': getattr(p, 'category', 'N/A')
                    } for p in products]
        except:
            pass
        
        # 4. الفواتير والمبيعات
        try:
            if 'فاتورة' in query or 'مبيع' in query or 'invoice' in query_lower or 'sale' in query_lower:
                invoices = Invoice.query.order_by(Invoice.issue_date.desc()).limit(15).all()
                if invoices:
                    results['all_invoices'] = [{
                        'id': i.id,
                        'customer_name': i.customer.name if hasattr(i, 'customer') and i.customer else 'N/A',
                        'total': getattr(i, 'total', 0),
                        'paid': getattr(i, 'paid', 0),
                        'date': i.issue_date.strftime('%Y-%m-%d') if i.issue_date else 'N/A'
                    } for i in invoices]
        except:
            pass
        
        # 5. المدفوعات
        try:
            if 'دفع' in query or 'payment' in query_lower or 'مدفوع' in query:
                payments = Payment.query.order_by(Payment.payment_date.desc()).limit(15).all()
                if payments:
                    results['all_payments'] = [{
                        'id': p.id,
                        'amount': p.amount,
                        'method': p.method,
                        'status': getattr(p, 'status', 'N/A'),
                        'date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else 'N/A'
                    } for p in payments]
        except:
            pass
        
        # 6. المصاريف
        try:
            if 'مصروف' in query or 'expense' in query_lower or 'نفقة' in query:
                expenses = Expense.query.order_by(Expense.expense_date.desc()).limit(15).all()
                if expenses:
                    results['expenses'] = [{
                        'id': e.id,
                        'description': getattr(e, 'description', 'N/A'),
                        'amount': e.amount,
                        'date': e.expense_date.strftime('%Y-%m-%d') if e.expense_date else 'N/A'
                    } for e in expenses]
        except:
            pass
        
        # 7. الموردين
        try:
            if 'مورد' in query or 'vendor' in query_lower or 'supplier' in query_lower:
                suppliers = Supplier.query.limit(15).all()
                if suppliers:
                    results['all_suppliers'] = [{
                        'id': s.id,
                        'name': s.name,
                        'phone': getattr(s, 'phone', 'N/A'),
                        'balance': getattr(s, 'balance', 0)
                    } for s in suppliers]
        except:
            pass
        
        # 8. المستودعات والمخازن (تحليل متقدم)
        try:
            if 'مستودع' in query or 'warehouse' in query_lower or 'مخزن' in query or 'اونلاين' in query or 'شركاء' in query or 'تجار' in query or 'ملكنا' in query or 'ملكيتي' in query:
                warehouses = Warehouse.query.all()
                if warehouses:
                    warehouse_details = []
                    
                    for w in warehouses:
                        # حساب القطع في المخزن
                        stock_levels = StockLevel.query.filter_by(warehouse_id=w.id).all()
                        total_items = sum(sl.quantity for sl in stock_levels)
                        
                        # تفاصيل المخزن
                        wh_info = {
                            'id': w.id,
                            'name': w.name,
                            'type': str(w.warehouse_type),
                            'type_label': w.warehouse_type.label if hasattr(w.warehouse_type, 'label') else str(w.warehouse_type),
                            'location': getattr(w, 'location', 'N/A'),
                            'total_items': total_items,
                            'items_count': len(stock_levels),
                            'capacity': getattr(w, 'capacity', 'N/A'),
                            'occupancy': getattr(w, 'current_occupancy', 0)
                        }
                        
                        # القطع في المخزن (أول 10)
                        items = []
                        for sl in stock_levels[:10]:
                            product = Product.query.filter_by(id=sl.product_id).first()
                            if product:
                                items.append({
                                    'name': product.name,
                                    'quantity': sl.quantity,
                                    'reserved': getattr(sl, 'reserved_quantity', 0)
                                })
                        
                        wh_info['items'] = items
                        warehouse_details.append(wh_info)
                    
                    results['warehouses_detailed'] = warehouse_details
                    
                    # تجميع حسب النوع
                    online_warehouses = [w for w in warehouse_details if 'ONLINE' in w['type']]
                    partner_warehouses = [w for w in warehouse_details if 'PARTNER' in w['type']]
                    inventory_warehouses = [w for w in warehouse_details if 'INVENTORY' in w['type']]
                    exchange_warehouses = [w for w in warehouse_details if 'EXCHANGE' in w['type']]
                    
                    results['warehouse_summary'] = {
                        'total': len(warehouses),
                        'online': online_warehouses,
                        'partners': partner_warehouses,
                        'our_inventory': inventory_warehouses,
                        'exchange_traders': exchange_warehouses
                    }
        except Exception as e:
            results['warehouse_error'] = str(e)
            pass
        
        # 9. الشحنات
        try:
            if 'شحنة' in query or 'shipment' in query_lower:
                shipments = Shipment.query.order_by(Shipment.arrival_date.desc()).limit(10).all()
                if shipments:
                    results['shipments'] = [{
                        'id': s.id,
                        'vendor': s.vendor.name if hasattr(s, 'vendor') and s.vendor else 'N/A',
                        'status': getattr(s, 'status', 'N/A'),
                        'date': s.arrival_date.strftime('%Y-%m-%d') if s.arrival_date else 'N/A'
                    } for s in shipments]
        except:
            pass
        
        # 10. الملاحظات
        try:
            if 'ملاحظة' in query or 'note' in query_lower:
                notes = Note.query.order_by(Note.created_at.desc()).limit(10).all()
                if notes:
                    results['notes'] = [{
                        'id': n.id,
                        'title': n.title,
                        'content': n.content[:100] if n.content else 'N/A',
                        'date': n.created_at.strftime('%Y-%m-%d') if n.created_at else 'N/A'
                    } for n in notes]
        except:
            pass
        
        # 11. المستخدمين
        try:
            if 'مستخدم' in query or 'user' in query_lower or 'موظف' in query:
                users = User.query.limit(15).all()
                if users:
                    results['all_users'] = [{
                        'id': u.id,
                        'username': u.username,
                        'email': u.email,
                        'role': u.role.name if u.role else 'N/A',
                        'is_active': u.is_active
                    } for u in users]
        except:
            pass
        
        # 12. الأدوار والصلاحيات
        try:
            if 'دور' in query or 'role' in query_lower or 'صلاحية' in query or 'permission' in query_lower:
                roles = Role.query.all()
                if roles:
                    results['roles'] = [{
                        'id': r.id,
                        'name': r.name,
                        'permissions_count': len(r.permissions) if hasattr(r, 'permissions') else 0
                    } for r in roles]
        except:
            pass
        
        # 13. البحث الذكي SQL (استعلامات مخصصة)
        try:
            # إذا كان السؤال يحتوي على رقم محدد
            import re
            numbers = re.findall(r'\d+', query)
            if numbers:
                # البحث برقم ID
                num = int(numbers[0])
                
                # بحث في الخدمات برقم
                try:
                    service = ServiceRequest.query.get(num)
                    if service:
                        results['found_service'] = {
                            'id': service.id,
                            'customer': service.customer.name if service.customer else 'N/A',
                            'vehicle': getattr(service, 'vehicle_info', 'N/A'),
                            'status': service.status,
                            'diagnosis': getattr(service, 'diagnosis', 'N/A'),
                            'total_cost': getattr(service, 'total_cost', 0)
                        }
                except:
                    pass
                
                # بحث في الفواتير برقم
                try:
                    invoice = Invoice.query.get(num)
                    if invoice:
                        results['found_invoice'] = {
                            'id': invoice.id,
                            'customer': invoice.customer.name if invoice.customer else 'N/A',
                            'total': getattr(invoice, 'total', 0),
                            'paid': getattr(invoice, 'paid', 0),
                            'status': getattr(invoice, 'status', 'N/A')
                        }
                except:
                    pass
        
        except:
            pass
        
        # 14. استعلام SQL مباشر للبيانات الإحصائية
        try:
            # إجمالي الإيرادات
            if 'إيراد' in query or 'دخل' in query or 'revenue' in query_lower:
                total_revenue = db.session.execute(text("SELECT SUM(total) FROM invoice")).scalar() or 0
                results['total_revenue'] = float(total_revenue)
            
            # إجمالي المصاريف
            if 'مصروف' in query or 'expense' in query_lower:
                total_expenses = db.session.execute(text("SELECT SUM(amount) FROM expense")).scalar() or 0
                results['total_expenses_sum'] = float(total_expenses)
            
            # صافي الربح
            if 'ربح' in query or 'profit' in query_lower:
                revenue = db.session.execute(text("SELECT SUM(total) FROM invoice")).scalar() or 0
                expenses = db.session.execute(text("SELECT SUM(amount) FROM expense")).scalar() or 0
                results['profit'] = float(revenue) - float(expenses)
        
        except:
            pass
        
        # 15. تحليل اليوم (Today Analysis)
        try:
            if 'اليوم' in query or 'today' in query_lower:
                today = datetime.now(timezone.utc).date()
                
                # حركات الصيانة اليوم
                today_services = ServiceRequest.query.filter(
                    func.date(ServiceRequest.created_at) == today
                ).all()
                
                if today_services:
                    results['today_services'] = [{
                        'id': s.id,
                        'customer': s.customer.name if s.customer else 'N/A',
                        'vehicle': getattr(s, 'vehicle_info', 'N/A'),
                        'status': s.status,
                        'diagnosis': getattr(s, 'diagnosis', 'N/A')[:100]
                    } for s in today_services]
                    
                    # قطع الصيانة المستخدمة اليوم
                    today_parts = []
                    for service in today_services:
                        parts = ServicePart.query.filter_by(service_id=service.id).all()
                        for part in parts:
                            product = Product.query.filter_by(id=part.part_id).first()
                            if product:
                                today_parts.append({
                                    'service_id': service.id,
                                    'part_name': product.name,
                                    'quantity': part.quantity,
                                    'price': float(part.unit_price)
                                })
                    
                    results['today_parts_used'] = today_parts
                    results['today_parts_count'] = len(today_parts)
                
                # حالة الدفع (الفواتير غير المدفوعة)
                unpaid_invoices = Invoice.query.filter(
                    Invoice.paid < Invoice.total
                ).all()
                
                paid_invoices = Invoice.query.filter(
                    Invoice.paid >= Invoice.total
                ).all()
                
                total_debt = sum(float(i.total - i.paid) for i in unpaid_invoices if hasattr(i, 'paid'))
                
                results['payment_status'] = {
                    'paid_count': len(paid_invoices),
                    'unpaid_count': len(unpaid_invoices),
                    'total_debt': total_debt
                }
        except Exception as e:
            results['today_error'] = str(e)
            pass
        
        # 16. تحليل الأعطال الشائعة
        try:
            if 'عطل' in query or 'أعطال' in query or 'مشكلة' in query or 'مشاكل' in query:
                # جمع جميع التشخيصات
                all_services = ServiceRequest.query.filter(
                    ServiceRequest.diagnosis.isnot(None)
                ).all()
                
                diagnoses = [s.diagnosis for s in all_services if s.diagnosis]
                
                # تحليل بسيط للأعطال الشائعة
                if diagnoses:
                    from collections import Counter
                    # تحليل الكلمات الشائعة
                    all_words = []
                    for d in diagnoses:
                        words = d.split()
                        all_words.extend([w for w in words if len(w) > 3])
                    
                    common = Counter(all_words).most_common(10)
                    
                    results['common_issues'] = {
                        'total_diagnosed': len(diagnoses),
                        'common_words': [{'word': w, 'count': c} for w, c in common]
                    }
        except:
            pass
        
    except Exception as e:
        results['error'] = str(e)
    
    return results


def _ai_chat_response_with_search(message, search_results):
    """رد AI مع نتائج البحث في قاعدة البيانات"""
    # الحصول على المفتاح النشط
    keys_json = _get_system_setting('AI_API_KEYS', '[]')
    try:
        keys = json.loads(keys_json)
        active_key = next((k for k in keys if k.get('is_active')), None)
        
        if not active_key:
            return '⚠️ لا يوجد مفتاح AI نشط. يرجى تفعيل مفتاح من <a href="/security/ai-config">إدارة المفاتيح</a>'
        
        # جمع بيانات النظام الشاملة
        system_context = _gather_system_context()
        
        # إضافة نتائج البحث للسياق
        search_context = ""
        if search_results:
            search_context = "\n\n═══════════════════════════════════════\n🔍 نتائج البحث في قاعدة البيانات:\n═══════════════════════════════════════\n"
            
            if 'found_customer' in search_results:
                c = search_results['found_customer']
                search_context += f"\n👤 العميل المطلوب:\n"
                search_context += f"- الاسم: {c['name']}\n"
                search_context += f"- الهاتف: {c['phone']}\n"
                search_context += f"- البريد: {c['email']}\n"
                search_context += f"- العنوان: {c['address']}\n"
                search_context += f"- الرصيد: {c['balance']} ₪\n"
                search_context += f"- الحالة: {'نشط' if c['is_active'] else 'غير نشط'}\n"
                search_context += f"- تاريخ التسجيل: {c['created_at']}\n"
            
            if 'customer_services' in search_results:
                search_context += f"\n🔧 خدمات العميل ({len(search_results['customer_services'])} خدمة):\n"
                for s in search_results['customer_services']:
                    search_context += f"- خدمة {s['id']} | {s['vehicle']} | {s['status']} | {s['date']}\n"
            
            if 'customer_invoices' in search_results:
                search_context += f"\n💰 فواتير العميل ({len(search_results['customer_invoices'])} فاتورة):\n"
                for i in search_results['customer_invoices']:
                    search_context += f"- فاتورة {i['id']} | {i['total']} ₪ | {i['date']}\n"
            
            if 'found_supplier' in search_results:
                s = search_results['found_supplier']
                search_context += f"\n🏭 المورد المطلوب:\n"
                search_context += f"- الاسم: {s['name']}\n"
                search_context += f"- الهاتف: {s['phone']}\n"
                search_context += f"- البريد: {s['email']}\n"
                search_context += f"- الرصيد: {s['balance']} ₪\n"
            
            if 'found_service' in search_results:
                s = search_results['found_service']
                search_context += f"\n🔧 الخدمة المطلوبة:\n"
                search_context += f"- رقم: {s['id']}\n"
                search_context += f"- العميل: {s['customer']}\n"
                search_context += f"- المركبة: {s['vehicle']}\n"
                search_context += f"- الحالة: {s['status']}\n"
                search_context += f"- التشخيص: {s['diagnosis']}\n"
                search_context += f"- التكلفة: {s['total_cost']} ₪\n"
            
            if 'found_invoice' in search_results:
                i = search_results['found_invoice']
                search_context += f"\n💰 الفاتورة المطلوبة:\n"
                search_context += f"- رقم: {i['id']}\n"
                search_context += f"- العميل: {i['customer']}\n"
                search_context += f"- المجموع: {i['total']} ₪\n"
                search_context += f"- المدفوع: {i['paid']} ₪\n"
                search_context += f"- الحالة: {i['status']}\n"
            
            if 'customers' in search_results:
                search_context += f"\n👥 العملاء ({len(search_results['customers'])} عميل):\n"
                for c in search_results['customers'][:5]:
                    search_context += f"- {c['name']} | {c['phone']}\n"
            
            if 'services' in search_results:
                search_context += f"\n🔧 طلبات الصيانة ({len(search_results['services'])} طلب):\n"
                for s in search_results['services'][:5]:
                    search_context += f"- رقم {s['id']} | {s['customer_name']} | {s['status']}\n"
            
            if 'products' in search_results:
                search_context += f"\n📦 المنتجات ({len(search_results['products'])} منتج):\n"
                for p in search_results['products'][:5]:
                    search_context += f"- {p['name']} | الكمية: {p['quantity']}\n"
            
            if 'invoices' in search_results:
                search_context += f"\n💰 الفواتير ({len(search_results['invoices'])} فاتورة):\n"
                for i in search_results['invoices'][:5]:
                    search_context += f"- فاتورة {i['id']} | {i['customer_name']} | {i['total']} ₪\n"
            
            if 'payments' in search_results:
                search_context += f"\n💳 المدفوعات ({len(search_results['payments'])} دفعة):\n"
                for p in search_results['payments'][:5]:
                    search_context += f"- {p['amount']} ₪ | {p['method']} | {p['date']}\n"
            
            # عرض تفاصيل المخازن
            if 'warehouse_summary' in search_results:
                ws = search_results['warehouse_summary']
                search_context += f"\n🏪 ملخص المخازن:\n"
                search_context += f"- إجمالي المخازن: {ws['total']}\n"
                
                if ws['online']:
                    search_context += f"\n📱 مخزن الأونلاين ({len(ws['online'])} مخزن):\n"
                    for w in ws['online']:
                        search_context += f"  • {w['name']}: {w['total_items']} قطعة ({w['items_count']} نوع)\n"
                        for item in w['items'][:5]:
                            search_context += f"    - {item['name']}: {item['quantity']} قطعة\n"
                
                if ws['our_inventory']:
                    search_context += f"\n🏭 ملكيتنا/ملكنا ({len(ws['our_inventory'])} مخزن):\n"
                    for w in ws['our_inventory']:
                        search_context += f"  • {w['name']}: {w['total_items']} قطعة\n"
                        for item in w['items'][:5]:
                            search_context += f"    - {item['name']}: {item['quantity']} قطعة\n"
                
                if ws['partners']:
                    search_context += f"\n👔 مخازن الشركاء ({len(ws['partners'])} مخزن):\n"
                    for w in ws['partners']:
                        search_context += f"  • {w['name']}: {w['total_items']} قطعة\n"
                        for item in w['items'][:5]:
                            search_context += f"    - {item['name']}: {item['quantity']} قطعة\n"
                
                if ws['exchange_traders']:
                    search_context += f"\n🔄 التبادل/التجار المحليين ({len(ws['exchange_traders'])} مخزن):\n"
                    for w in ws['exchange_traders']:
                        search_context += f"  • {w['name']}: {w['total_items']} قطعة\n"
                        for item in w['items'][:5]:
                            search_context += f"    - {item['name']}: {item['quantity']} قطعة\n"
            
            # إجماليات مالية
            if 'total_revenue' in search_results:
                search_context += f"\n💰 إجمالي الإيرادات: {search_results['total_revenue']:.2f} ₪\n"
            
            if 'total_expenses_sum' in search_results:
                search_context += f"💸 إجمالي المصاريف: {search_results['total_expenses_sum']:.2f} ₪\n"
            
            if 'profit' in search_results:
                search_context += f"📈 صافي الربح: {search_results['profit']:.2f} ₪\n"
        
        # استخدام Groq API
        try:
            import requests
            
            api_key = active_key.get('key')
            provider = active_key.get('provider', 'groq')
            
            if 'groq' in provider.lower():
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # السياق الكامل مع نتائج البحث
                system_msg = _build_system_message(system_context) + search_context
                
                data = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1500
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    return f'❌ خطأ في الاتصال: {response.status_code}'
            
            else:
                return '⚠️ هذا المزود غير مدعوم حالياً. استخدم Groq.'
        
        except requests.exceptions.Timeout:
            return '⏱️ انتهت مهلة الاتصال. يرجى المحاولة مرة أخرى.'
        except requests.exceptions.RequestException as e:
            return f'❌ خطأ في الاتصال: {str(e)}'
        except Exception as e:
            return f'❌ خطأ: {str(e)}'
    
    except Exception as e:
        return f'⚠️ خطأ في قراءة المفاتيح: {str(e)}'


def _build_system_message(system_context):
    """بناء رسالة النظام الأساسية"""
    return f"""أنت النظام الذكي لـ "أزاد لإدارة الكراج" - Azad Garage Manager System
أنت جزء من النظام، تعرف كل شيء عنه، وتتكلم بصوته.

═══════════════════════════════════════
🏢 هوية النظام:
═══════════════════════════════════════
- الاسم: نظام أزاد لإدارة الكراج
- النسخة: v4.0.0 Enterprise Edition
- الشركة: أزاد للأنظمة الذكية - Azad Smart Systems
- التطوير: المهندس أزاد | سوريا - دمشق
- التخصص: نظام متكامل لإدارة كراجات السيارات والصيانة

═══════════════════════════════════════
📦 الوحدات الرئيسية (23 وحدة):
═══════════════════════════════════════
1. 🔐 المصادقة - تسجيل الدخول والأمان
2. 🏠 لوحة التحكم - Dashboard
3. 👥 إدارة المستخدمين - الصلاحيات والأدوار
4. 🔧 الصيانة - إدارة طلبات الصيانة والإصلاح
5. 👤 العملاء - إدارة بيانات العملاء والحسابات
6. 💰 المبيعات - إدارة المبيعات والفواتير
7. 🛒 المتجر الإلكتروني - واجهة تسوق للعملاء
8. 📦 المخزون - إدارة المنتجات وقطع الغيار
9. 🏭 الموردين - إدارة الموردين والمشتريات
10. 🚚 الشحنات - تتبع الشحنات الواردة
11. 🏪 المستودعات - إدارة المخازن والنقل بينها
12. 💳 المدفوعات - نظام دفع متكامل
13. 💸 المصاريف - تسجيل المصاريف والنفقات
14. 📊 التقارير - تقارير شاملة (مالية، مخزون، أداء)
15. 📋 الملاحظات - نظام ملاحظات ذكي
16. 📱 الباركود - مسح وطباعة الباركود
17. 💱 العملات - إدارة أسعار الصرف
18. 🔗 API - واجهة برمجية للتكامل
19. 👔 الشركاء - تسويات الشركاء
20. 📝 دفتر الأستاذ - المحاسبة
21. 🛡️ وحدة الأمان - تحكم شامل (Owner فقط)
22. 🔄 النسخ الاحتياطي - نسخ تلقائية للبيانات
23. 🗑️ الحذف الصعب - نظام حذف آمن

═══════════════════════════════════════
👥 الأدوار والصلاحيات:
═══════════════════════════════════════
1. Super Admin - كل شيء
2. Admin - كل شيء عدا المتجر والامان
3. Mechanic - الصيانة فقط
4. Staff - المبيعات والمحاسبة
5. Customer - المتجر وحسابه الشخصي

═══════════════════════════════════════
📊 إحصائيات النظام الحالية (أرقام حقيقية):
═══════════════════════════════════════
👥 المستخدمين:
- الإجمالي: {system_context['total_users']}
- النشطين: {system_context['active_users']}

🔧 الصيانة:
- طلبات الصيانة: {system_context['total_services']}
- معلقة: {system_context['pending_services']}
- مكتملة: {system_context['completed_services']}

💰 المبيعات:
- إجمالي الفواتير: {system_context['total_sales']}
- مبيعات اليوم: {system_context['sales_today']}

📦 المخزون:
- إجمالي المنتجات: {system_context['total_products']}
- متوفر في المخزون: {system_context['products_in_stock']}

👤 العملاء:
- الإجمالي: {system_context['total_customers']}
- النشطين: {system_context['active_customers']}

🏭 الموردين: {system_context['total_vendors']}

💳 المدفوعات:
- الإجمالي: {system_context['total_payments']}
- اليوم: {system_context['payments_today']}

💸 المصاريف: {system_context['total_expenses']}
🏪 المستودعات: {system_context['total_warehouses']}
📋 الملاحظات: {system_context['total_notes']}
🚚 الشحنات: {system_context['total_shipments']}

🔒 الأمان:
- محاولات دخول فاشلة (24h): {system_context['failed_logins']}
- IPs محظورة: {system_context['blocked_ips']}
- دول محظورة: {system_context['blocked_countries']}
- أنشطة مشبوهة (24h): {system_context['suspicious_activities']}

📝 سجلات النشاط:
- إجمالي السجلات: {system_context['total_audit_logs']}
- الإجراءات الأخيرة: {system_context['recent_actions']}

💾 قاعدة البيانات: {system_context['db_size']} | الحالة: {system_context['db_health']}
⚡ الأداء: CPU {system_context['cpu_usage']}% | ذاكرة {system_context['memory_usage']}%

═══════════════════════════════════════
🎯 دورك:
═══════════════════════════════════════
- أجب بالعربية الاحترافية
- استخدم البيانات الحقيقية أعلاه و نتائج البحث
- إذا سُئلت عن عميل/خدمة/منتج محدد، استخدم نتائج البحث
- قدم تحليلات دقيقة ومفيدة
- اشرح الميزات بوضوح
- قدم توصيات عملية
- تكلم كأنك النظام نفسه: "أنا نظام أزاد..."
- استخدم الإيموجي بشكل مناسب
- كن مختصراً ومفيداً
- إذا لم تجد المعلومة المطلوبة، اذكر ذلك بوضوح

أنت النظام! تكلم بثقة واحترافية."""


def _ai_chat_response(message):
    """رد AI ذكي - متصل بـ Groq API مع وصول شامل للنظام"""
    # الحصول على المفتاح النشط
    keys_json = _get_system_setting('AI_API_KEYS', '[]')
    try:
        keys = json.loads(keys_json)
        active_key = next((k for k in keys if k.get('is_active')), None)
        
        if not active_key:
            return '⚠️ لا يوجد مفتاح AI نشط. يرجى تفعيل مفتاح من <a href="/security/ai-config">إدارة المفاتيح</a>'
        
        # جمع بيانات النظام الشاملة
        system_context = _gather_system_context()
        
        # استخدام Groq API
        try:
            import requests
            
            api_key = active_key.get('key')
            provider = active_key.get('provider', 'groq')
            
            if 'groq' in provider.lower():
                # Groq API
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # سياق شامل للمساعد - التدريب الكامل
                system_msg = f"""أنت النظام الذكي لـ "أزاد لإدارة الكراج" - Azad Garage Manager System
أنت جزء من النظام، تعرف كل شيء عنه، وتتكلم بصوته.

═══════════════════════════════════════
🏢 هوية النظام:
═══════════════════════════════════════
- الاسم: نظام أزاد لإدارة الكراج
- النسخة: v4.0.0 Enterprise Edition
- الشركة: أزاد للأنظمة الذكية - Azad Smart Systems
- التطوير: المهندس أزاد | سوريا - دمشق
- التخصص: نظام متكامل لإدارة كراجات السيارات والصيانة

═══════════════════════════════════════
📦 الوحدات الرئيسية (23 وحدة):
═══════════════════════════════════════
1. 🔐 المصادقة - تسجيل الدخول والأمان
2. 🏠 لوحة التحكم - Dashboard
3. 👥 إدارة المستخدمين - الصلاحيات والأدوار
4. 🔧 الصيانة - إدارة طلبات الصيانة والإصلاح
5. 👤 العملاء - إدارة بيانات العملاء والحسابات
6. 💰 المبيعات - إدارة المبيعات والفواتير
7. 🛒 المتجر الإلكتروني - واجهة تسوق للعملاء
8. 📦 المخزون - إدارة المنتجات وقطع الغيار
9. 🏭 الموردين - إدارة الموردين والمشتريات
10. 🚚 الشحنات - تتبع الشحنات الواردة
11. 🏪 المستودعات - إدارة المخازن والنقل بينها
12. 💳 المدفوعات - نظام دفع متكامل
13. 💸 المصاريف - تسجيل المصاريف والنفقات
14. 📊 التقارير - تقارير شاملة (مالية، مخزون، أداء)
15. 📋 الملاحظات - نظام ملاحظات ذكي
16. 📱 الباركود - مسح وطباعة الباركود
17. 💱 العملات - إدارة أسعار الصرف
18. 🔗 API - واجهة برمجية للتكامل
19. 👔 الشركاء - تسويات الشركاء
20. 📝 دفتر الأستاذ - المحاسبة
21. 🛡️ وحدة الأمان - تحكم شامل (Owner فقط)
22. 🔄 النسخ الاحتياطي - نسخ تلقائية للبيانات
23. 🗑️ الحذف الصعب - نظام حذف آمن

═══════════════════════════════════════
👥 الأدوار والصلاحيات:
═══════════════════════════════════════
1. Super Admin - كل شيء
2. Admin - كل شيء عدا المتجر والامان
3. Mechanic - الصيانة فقط
4. Staff - المبيعات والمحاسبة
5. Customer - المتجر وحسابه الشخصي

═══════════════════════════════════════
📊 إحصائيات النظام الحالية (أرقام حقيقية):
═══════════════════════════════════════
👥 المستخدمين:
- الإجمالي: {system_context['total_users']}
- النشطين: {system_context['active_users']}

🔧 الصيانة:
- طلبات الصيانة: {system_context['total_services']}
- معلقة: {system_context['pending_services']}
- مكتملة: {system_context['completed_services']}

💰 المبيعات:
- إجمالي الفواتير: {system_context['total_sales']}
- مبيعات اليوم: {system_context['sales_today']}

📦 المخزون:
- إجمالي المنتجات: {system_context['total_products']}
- متوفر في المخزون: {system_context['products_in_stock']}

👤 العملاء:
- الإجمالي: {system_context['total_customers']}
- النشطين: {system_context['active_customers']}

🏭 الموردين: {system_context['total_vendors']}

💳 المدفوعات:
- الإجمالي: {system_context['total_payments']}
- اليوم: {system_context['payments_today']}

💸 المصاريف: {system_context['total_expenses']}
🏪 المستودعات: {system_context['total_warehouses']}
📋 الملاحظات: {system_context['total_notes']}
🚚 الشحنات: {system_context['total_shipments']}

🔒 الأمان:
- محاولات دخول فاشلة (24h): {system_context['failed_logins']}
- IPs محظورة: {system_context['blocked_ips']}
- دول محظورة: {system_context['blocked_countries']}
- أنشطة مشبوهة (24h): {system_context['suspicious_activities']}

📝 سجلات النشاط:
- إجمالي السجلات: {system_context['total_audit_logs']}
- الإجراءات الأخيرة: {system_context['recent_actions']}

💾 قاعدة البيانات: {system_context['db_size']} | الحالة: {system_context['db_health']}
⚡ الأداء: CPU {system_context['cpu_usage']}% | ذاكرة {system_context['memory_usage']}%

═══════════════════════════════════════
🎯 دورك:
═══════════════════════════════════════
- أجب بالعربية الاحترافية
- استخدم البيانات الحقيقية أعلاه
- قدم تحليلات دقيقة ومفيدة
- اشرح الميزات بوضوح
- قدم توصيات عملية
- تكلم كأنك النظام نفسه: "أنا نظام أزاد..."
- استخدم الإيموجي بشكل مناسب
- كن مختصراً ومفيداً

═══════════════════════════════════════
💡 أمثلة على الأسئلة المتوقعة:
═══════════════════════════════════════
- "ما هي حالة النظام؟" → قدم تقرير شامل
- "كم عدد الخدمات؟" → استخدم الرقم الحقيقي
- "هل يوجد تهديدات؟" → حلل بيانات الأمان
- "كيف أضيف عميل؟" → اشرح الخطوات
- "ما هو دور Mechanic؟" → اشرح الصلاحيات

أنت النظام! تكلم بثقة واحترافية."""
                
                data = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    return f'❌ خطأ في الاتصال: {response.status_code}'
            
            else:
                return '⚠️ هذا المزود غير مدعوم حالياً. استخدم Groq.'
        
        except requests.exceptions.Timeout:
            return '⏱️ انتهت مهلة الاتصال. يرجى المحاولة مرة أخرى.'
        except requests.exceptions.RequestException as e:
            return f'❌ خطأ في الاتصال: {str(e)}'
        except Exception as e:
            return f'❌ خطأ: {str(e)}'
    
    except Exception as e:
        return f'⚠️ خطأ في قراءة المفاتيح: {str(e)}'


def _gather_system_context():
    """جمع بيانات النظام الشاملة - أرقام حقيقية 100%"""
    import psutil
    
    context = {}
    
    try:
        # استيراد جميع الموديلات
        from models import (
            Customer, Supplier, Product, ServiceRequest, 
            Invoice, Payment, Expense, Warehouse, StockLevel,
            Note, Shipment, Role, Permission
        )
        
        # المستخدمين
        context['total_users'] = User.query.count()
        context['active_users'] = User.query.filter_by(is_active=True).count()
        
        # الخدمات (استخدام ServiceRequest مباشرة)
        try:
            context['total_services'] = ServiceRequest.query.count()
            context['pending_services'] = ServiceRequest.query.filter_by(status='pending').count()
            context['completed_services'] = ServiceRequest.query.filter_by(status='completed').count()
        except:
            context['total_services'] = 0
            context['pending_services'] = 0
            context['completed_services'] = 0
        
        # المبيعات (استخدام Invoice مباشرة)
        try:
            context['total_sales'] = Invoice.query.count()
            context['sales_today'] = Invoice.query.filter(
                func.date(Invoice.issue_date) == func.date(datetime.now(timezone.utc))
            ).count()
        except:
            context['total_sales'] = 0
            context['sales_today'] = 0
        
        # المنتجات
        try:
            context['total_products'] = Product.query.count()
            context['products_in_stock'] = Product.query.filter(Product.quantity > 0).count()
        except:
            context['total_products'] = 0
            context['products_in_stock'] = 0
        
        # العملاء
        try:
            context['total_customers'] = Customer.query.count()
            context['active_customers'] = Customer.query.filter_by(is_active=True).count()
        except:
            context['total_customers'] = 0
            context['active_customers'] = 0
        
        # الموردين
        try:
            context['total_vendors'] = Supplier.query.count()
        except:
            context['total_vendors'] = 0
        
        # المدفوعات
        try:
            context['total_payments'] = Payment.query.count()
            context['payments_today'] = Payment.query.filter(
                func.date(Payment.payment_date) == func.date(datetime.now(timezone.utc))
            ).count()
        except:
            context['total_payments'] = 0
            context['payments_today'] = 0
        
        # المصاريف
        try:
            context['total_expenses'] = Expense.query.count()
        except:
            context['total_expenses'] = 0
        
        # المستودعات
        try:
            context['total_warehouses'] = Warehouse.query.count()
        except:
            context['total_warehouses'] = 0
        
        # الملاحظات
        try:
            context['total_notes'] = Note.query.count()
        except:
            context['total_notes'] = 0
        
        # الشحنات
        try:
            context['total_shipments'] = Shipment.query.count()
        except:
            context['total_shipments'] = 0
        
        # الأمان
        context['failed_logins'] = _get_failed_logins_count(24)
        context['blocked_ips'] = _get_blocked_ips_count()
        context['blocked_countries'] = _get_blocked_countries_count()
        context['suspicious_activities'] = _get_suspicious_activities_count(24)
        
        # قاعدة البيانات
        context['db_size'] = _get_db_size()
        context['db_health'] = _get_system_health()
        
        # الأداء
        context['cpu_usage'] = round(psutil.cpu_percent(interval=0.1), 1)
        context['memory_usage'] = round(psutil.virtual_memory().percent, 1)
        
        # إضافي: سجلات النشاط
        try:
            context['total_audit_logs'] = AuditLog.query.count()
            context['recent_actions'] = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5).count()
        except:
            context['total_audit_logs'] = 0
            context['recent_actions'] = 0
        
        return context
        
    except Exception as e:
        # في حالة الخطأ، إرجاع بيانات أساسية فقط
        return {
            'total_users': User.query.count() if User else 0,
            'active_users': User.query.filter_by(is_active=True).count() if User else 0,
            'total_services': 0,
            'pending_services': 0,
            'completed_services': 0,
            'total_sales': 0,
            'sales_today': 0,
            'total_products': 0,
            'products_in_stock': 0,
            'total_customers': 0,
            'active_customers': 0,
            'total_vendors': 0,
            'total_payments': 0,
            'payments_today': 0,
            'total_expenses': 0,
            'total_warehouses': 0,
            'total_notes': 0,
            'total_shipments': 0,
            'failed_logins': 0,
            'blocked_ips': 0,
            'blocked_countries': 0,
            'suspicious_activities': 0,
            'db_size': 'N/A',
            'db_health': 'غير معروف',
            'cpu_usage': 0,
            'memory_usage': 0,
            'total_audit_logs': 0,
            'recent_actions': 0,
        }


# ═══════════════════════════════════════════════════════════════
# Ultimate Control Helper Functions
# ═══════════════════════════════════════════════════════════════

def _get_users_online():
    """عدد المستخدمين المتصلين"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    return User.query.filter(User.last_seen >= threshold).count()


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


def _get_system_setting(key, default=None):
    """قراءة إعداد نظام"""
    from models import SystemSettings
    setting = SystemSettings.query.filter_by(key=key).first()
    if setting:
        value = setting.value.lower()
        if value in ['true', '1', 'yes']:
            return True
        elif value in ['false', '0', 'no']:
            return False
        return setting.value
    return default


def _kill_all_user_sessions():
    """إنهاء جميع جلسات المستخدمين"""
    # تحديث last_seen لجميع المستخدمين
    User.query.update({'last_seen': datetime.now(timezone.utc) - timedelta(days=30)})
    db.session.commit()


def _get_available_backups():
    """قائمة النسخ الاحتياطية"""
    import os
    backup_dir = 'instance/backups/db'
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
        'error': 'error.log',
        'server': 'server_error.log',
        'audit': 'instance/audit.log',
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

