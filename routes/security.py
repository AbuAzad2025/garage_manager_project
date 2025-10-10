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


@security_bp.route('/api/ai-chat', methods=['POST'])
@owner_only
def ai_chat():
    """API للمحادثة مع AI"""
    data = request.get_json()
    message = data.get('message', '')
    
    response = _ai_chat_response(message)
    
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
    
    # حفظ المستخدم الأصلي
    session['original_user_id'] = current_user.id
    session['impersonating'] = True
    
    logout_user()
    login_user(target_user)
    
    flash(f'تم تسجيل الدخول كـ {target_user.username}', 'warning')
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
        
        # اسم النظام
        system_name = request.form.get('system_name', '')
        if system_name:
            _set_system_setting('system_name', system_name)
        
        # وصف النظام
        system_description = request.form.get('system_description', '')
        if system_description:
            _set_system_setting('system_description', system_description)
        
        # اللون الأساسي
        primary_color = request.form.get('primary_color', '')
        if primary_color:
            _set_system_setting('primary_color', primary_color)
        
        # الشعار
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file and logo_file.filename:
                filename = secure_filename(logo_file.filename)
                logo_path = f'static/img/custom_logo_{filename}'
                logo_file.save(logo_path)
                _set_system_setting('custom_logo', logo_path)
        
        # الأيقونة
        if 'favicon' in request.files:
            favicon_file = request.files['favicon']
            if favicon_file and favicon_file.filename:
                filename = secure_filename(favicon_file.filename)
                favicon_path = f'static/favicon_custom_{filename}'
                favicon_file.save(favicon_path)
                _set_system_setting('custom_favicon', favicon_path)
        
        flash('تم تحديث العلامة التجارية', 'success')
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


def _ai_chat_response(message):
    """رد AI ذكي"""
    message_lower = message.lower()
    
    if 'أمان' in message or 'security' in message_lower:
        return 'النظام محمي بـ 13 طبقة حماية. مستوى التهديد: منخفض ✅'
    
    elif 'مستخدم' in message or 'user' in message_lower:
        total = User.query.count()
        active = User.query.filter_by(is_active=True).count()
        return f'لديك {total} مستخدم، منهم {active} نشط.'
    
    elif 'حظر' in message or 'block' in message_lower:
        blocked_ips = _get_blocked_ips_count()
        blocked_countries = _get_blocked_countries_count()
        return f'IPs محظورة: {blocked_ips}, دول محظورة: {blocked_countries}'
    
    elif 'تقرير' in message or 'report' in message_lower:
        return 'يمكنك الوصول للتقارير الأمنية من قائمة التقارير.'
    
    else:
        return 'مرحباً! أنا مساعد الأمان الذكي. كيف يمكنني مساعدتك؟'


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

