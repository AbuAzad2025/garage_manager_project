from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import SystemSettings
import json
from datetime import datetime, timezone
from functools import wraps
from routes.advanced_control import _log_owner_action

security_control_bp = Blueprint('security_control', __name__, url_prefix='/advanced')


def owner_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يجب تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        if not (current_user.role and current_user.role.name == 'Owner'):
            flash('هذه الصفحة مخصصة للمالك فقط', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@security_control_bp.route('/security-control', methods=['GET', 'POST'])
@login_required
@owner_only
def security_control():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_ip_settings':
            enable_ip_whitelist = request.form.get('enable_ip_whitelist') == 'on'
            enable_ip_blacklist = request.form.get('enable_ip_blacklist') == 'on'
            enable_country_blocking = request.form.get('enable_country_blocking') == 'on'
            
            whitelist_ips = request.form.get('whitelist_ips', '').strip()
            blacklist_ips = request.form.get('blacklist_ips', '').strip()
            blocked_countries = request.form.getlist('blocked_countries')
            
            whitelist_list = [ip.strip() for ip in whitelist_ips.split('\n') if ip.strip()]
            blacklist_list = [ip.strip() for ip in blacklist_ips.split('\n') if ip.strip()]
            
            SystemSettings.set_setting('enable_ip_whitelist', enable_ip_whitelist, 'boolean')
            SystemSettings.set_setting('enable_ip_blacklist', enable_ip_blacklist, 'boolean')
            SystemSettings.set_setting('enable_country_blocking', enable_country_blocking, 'boolean')
            
            SystemSettings.set_setting('ip_whitelist', json.dumps(whitelist_list), 'json')
            SystemSettings.set_setting('ip_blacklist', json.dumps(blacklist_list), 'json')
            SystemSettings.set_setting('blocked_countries', json.dumps(blocked_countries), 'json')
            _log_owner_action('security.ip_settings', 'update', {
                'whitelist_count': len(whitelist_list),
                'blacklist_count': len(blacklist_list),
                'countries': len(blocked_countries),
            })
            
            db.session.commit()
            
            flash('تم حفظ إعدادات الأمان بنجاح', 'success')
            return redirect(url_for('security_control.security_control'))
        
        elif action == 'test_ip':
            test_ip = request.form.get('test_ip', '').strip()
            if test_ip:
                from utils import check_ip_allowed
                result = check_ip_allowed(test_ip)
                return jsonify({
                    'allowed': result['allowed'],
                    'reason': result['reason'],
                    'ip': test_ip
                })
    
    enable_whitelist = SystemSettings.get_setting('enable_ip_whitelist', False)
    enable_blacklist = SystemSettings.get_setting('enable_ip_blacklist', False)
    enable_country_block = SystemSettings.get_setting('enable_country_blocking', False)
    
    whitelist_raw = SystemSettings.get_setting('ip_whitelist', '[]')
    blacklist_raw = SystemSettings.get_setting('ip_blacklist', '[]')
    blocked_countries_raw = SystemSettings.get_setting('blocked_countries', '[]')
    
    try:
        whitelist = json.loads(whitelist_raw) if isinstance(whitelist_raw, str) else whitelist_raw
    except Exception:
        whitelist = []
    
    try:
        blacklist = json.loads(blacklist_raw) if isinstance(blacklist_raw, str) else blacklist_raw
    except Exception:
        blacklist = []
    
    try:
        blocked_countries = json.loads(blocked_countries_raw) if isinstance(blocked_countries_raw, str) else blocked_countries_raw
    except Exception:
        blocked_countries = []
    
    all_countries = [
        {'code': 'IL', 'name': 'إسرائيل'},
        {'code': 'US', 'name': 'الولايات المتحدة'},
        {'code': 'GB', 'name': 'المملكة المتحدة'},
        {'code': 'RU', 'name': 'روسيا'},
        {'code': 'CN', 'name': 'الصين'},
        {'code': 'IN', 'name': 'الهند'},
        {'code': 'BR', 'name': 'البرازيل'},
        {'code': 'ZA', 'name': 'جنوب أفريقيا'},
        {'code': 'EG', 'name': 'مصر'},
        {'code': 'SA', 'name': 'السعودية'},
        {'code': 'AE', 'name': 'الإمارات'},
        {'code': 'JO', 'name': 'الأردن'},
        {'code': 'LB', 'name': 'لبنان'},
        {'code': 'SY', 'name': 'سوريا'},
        {'code': 'IQ', 'name': 'العراق'},
        {'code': 'TR', 'name': 'تركيا'},
        {'code': 'IR', 'name': 'إيران'},
        {'code': 'PK', 'name': 'باكستان'},
        {'code': 'AF', 'name': 'أفغانستان'},
        {'code': 'YE', 'name': 'اليمن'},
    ]
    
    stats = {
        'whitelist_count': len(whitelist),
        'blacklist_count': len(blacklist),
        'blocked_countries_count': len(blocked_countries),
    }
    
    return render_template('advanced/security_control.html',
                         enable_whitelist=enable_whitelist,
                         enable_blacklist=enable_blacklist,
                         enable_country_block=enable_country_block,
                         whitelist=whitelist,
                         blacklist=blacklist,
                         blocked_countries=blocked_countries,
                         all_countries=all_countries,
                         stats=stats)


@security_control_bp.route('/api/check-ip/<ip>')
@login_required
@owner_only
def api_check_ip(ip):
    from utils import check_ip_allowed
    result = check_ip_allowed(ip)
    if not result.get('allowed'):
        SystemSettings.set_setting('security_last_denied', {
            'ip': ip,
            'reason': result.get('reason'),
            'time': datetime.now(timezone.utc).isoformat()
        }, data_type='json')
    _log_owner_action('security.api_check', ip, result)
    return jsonify(result)

