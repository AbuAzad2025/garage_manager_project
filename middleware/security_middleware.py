from flask import request, abort, jsonify
from models import SystemSettings
import json


def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    elif request.headers.get("X-Real-IP"):
        ip = request.headers.get("X-Real-IP")
    else:
        ip = request.remote_addr
    return ip


def check_ip_allowed(ip):
    enable_whitelist = SystemSettings.get_setting('enable_ip_whitelist', False)
    enable_blacklist = SystemSettings.get_setting('enable_ip_blacklist', False)
    enable_country_block = SystemSettings.get_setting('enable_country_blocking', False)
    
    if not any([enable_whitelist, enable_blacklist, enable_country_block]):
        return {'allowed': True, 'reason': 'Security checks disabled'}
    
    if enable_blacklist:
        blacklist_raw = SystemSettings.get_setting('ip_blacklist', '[]')
        try:
            blacklist = json.loads(blacklist_raw) if isinstance(blacklist_raw, str) else blacklist_raw
        except Exception:
            blacklist = []
        
        if ip in blacklist:
            return {'allowed': False, 'reason': 'IP في القائمة السوداء'}
    
    if enable_whitelist:
        whitelist_raw = SystemSettings.get_setting('ip_whitelist', '[]')
        try:
            whitelist = json.loads(whitelist_raw) if isinstance(whitelist_raw, str) else whitelist_raw
        except Exception:
            whitelist = []
        
        if ip not in whitelist:
            return {'allowed': False, 'reason': 'IP غير موجود في القائمة البيضاء'}
    
    if enable_country_block:
        try:
            import requests
            response = requests.get(f'http://ip-api.com/json/{ip}?fields=countryCode', timeout=2)
            if response.status_code == 200:
                data = response.json()
                country_code = data.get('countryCode', '')
                
                blocked_countries_raw = SystemSettings.get_setting('blocked_countries', '[]')
                try:
                    blocked_countries = json.loads(blocked_countries_raw) if isinstance(blocked_countries_raw, str) else blocked_countries_raw
                except Exception:
                    blocked_countries = []
                
                if country_code in blocked_countries:
                    return {'allowed': False, 'reason': f'الدولة {country_code} محظورة'}
        except Exception:
            pass
    
    return {'allowed': True, 'reason': 'مسموح'}


def ip_security_middleware():
    if request.endpoint and (
        request.endpoint.startswith('auth.') or 
        request.endpoint.startswith('static') or
        request.endpoint.startswith('security_control.')
    ):
        return None
    
    client_ip = get_client_ip()
    result = check_ip_allowed(client_ip)
    
    if not result['allowed']:
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'error': 'Access Denied',
                'reason': result['reason'],
                'ip': client_ip
            }), 403
        else:
            abort(403)
    
    return None


def init_security_middleware(app):
    @app.before_request
    def check_ip_security():
        return ip_security_middleware()

