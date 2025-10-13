# routes/advanced_control.py
# Location: /garage_manager/routes/advanced_control.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import text, func, inspect
from datetime import datetime, timedelta
from extensions import db
from models import User, SystemSettings
from utils import is_super
from functools import wraps
import os
import json
import sqlite3
import shutil
from werkzeug.utils import secure_filename

advanced_bp = Blueprint('advanced', __name__, url_prefix='/advanced')

def owner_only(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not is_super():
            flash('⛔ الوصول محظور', 'danger')
            return redirect(url_for('main.dashboard'))
        if current_user.id != 1 and current_user.username.lower() not in ['azad', 'owner', 'admin']:
            flash('⛔ هذه الوحدة متاحة للمالك الأساسي فقط', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@advanced_bp.route('/db-merger', methods=['GET', 'POST'])
@owner_only
def db_merger():
    """معالج قواعد البيانات - دمج ذكي"""
    if request.method == 'POST':
        if 'db_file' not in request.files:
            flash('❌ لم يتم رفع ملف', 'danger')
            return redirect(url_for('advanced.db_merger'))
        
        file = request.files['db_file']
        if not file.filename.endswith('.db'):
            flash('❌ يجب أن يكون ملف .db', 'danger')
            return redirect(url_for('advanced.db_merger'))
        
        merge_mode = request.form.get('merge_mode', 'smart')
        
        try:
            temp_path = os.path.join(current_app.root_path, 'instance', 'temp_merge.db')
            file.save(temp_path)
            
            result = _merge_databases(temp_path, merge_mode)
            
            os.remove(temp_path)
            
            flash(f'✅ تم الدمج بنجاح! {result["added"]} سجل مضاف', 'success')
            return redirect(url_for('advanced.db_merger'))
            
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
            return redirect(url_for('advanced.db_merger'))
    
    stats = {
        'current_db_size': _get_db_size(),
        'total_tables': len(db.metadata.tables),
        'total_records': _count_all_records()
    }
    
    return render_template('advanced/db_merger.html', stats=stats)


@advanced_bp.route('/multi-tenant', methods=['GET', 'POST'])
@owner_only
def multi_tenant():
    """إدارة Multi-Tenant - نسخ متعددة"""
    tenants = SystemSettings.query.filter(
        SystemSettings.key.like('tenant_%')
    ).all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_tenant':
            tenant_name = request.form.get('tenant_name')
            tenant_db = request.form.get('tenant_db')
            
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_db', value=tenant_db))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_active', value='True'))
            db.session.commit()
            
            flash(f'✅ تم إنشاء Tenant: {tenant_name}', 'success')
            return redirect(url_for('advanced.multi_tenant'))
    
    tenant_list = []
    processed = set()
    for t in tenants:
        if '_db' in t.key:
            name = t.key.replace('tenant_', '').replace('_db', '')
            if name not in processed:
                active_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_active').first()
                tenant_list.append({
                    'name': name,
                    'db': t.value,
                    'active': active_setting.value == 'True' if active_setting else False
                })
                processed.add(name)
    
    return render_template('advanced/multi_tenant.html', tenants=tenant_list)


@advanced_bp.route('/dashboard-links', methods=['GET', 'POST'])
@owner_only
def dashboard_links():
    """إدارة روابط الداشبورد - إخفاء/إظهار"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'toggle_link':
            link_key = request.form.get('link_key')
            visible = request.form.get('visible') == 'on'
            
            setting = SystemSettings.query.filter_by(key=f'dashboard_link_{link_key}').first()
            if setting:
                setting.value = str(visible)
            else:
                db.session.add(SystemSettings(key=f'dashboard_link_{link_key}', value=str(visible)))
            
            db.session.commit()
            flash(f'✅ تم تحديث: {link_key}', 'success')
            return redirect(url_for('advanced.dashboard_links'))
    
    available_links = [
        {'key': 'customers', 'name': 'العملاء', 'icon': 'users'},
        {'key': 'service', 'name': 'الصيانة', 'icon': 'wrench'},
        {'key': 'sales', 'name': 'المبيعات', 'icon': 'shopping-cart'},
        {'key': 'warehouses', 'name': 'المستودعات', 'icon': 'warehouse'},
        {'key': 'vendors', 'name': 'الموردين', 'icon': 'truck'},
        {'key': 'partners', 'name': 'الشركاء', 'icon': 'handshake'},
        {'key': 'shipments', 'name': 'الشحنات', 'icon': 'ship'},
        {'key': 'payments', 'name': 'الدفعات', 'icon': 'money-bill-wave'},
        {'key': 'checks', 'name': 'الشيكات', 'icon': 'money-check'},
        {'key': 'expenses', 'name': 'النفقات', 'icon': 'receipt'},
        {'key': 'ledger', 'name': 'دفتر الأستاذ', 'icon': 'book'},
        {'key': 'currencies', 'name': 'العملات', 'icon': 'dollar-sign'},
        {'key': 'reports', 'name': 'التقارير', 'icon': 'chart-bar'},
        {'key': 'shop', 'name': 'المتجر', 'icon': 'store'},
    ]
    
    for link in available_links:
        setting = SystemSettings.query.filter_by(key=f'dashboard_link_{link["key"]}').first()
        link['visible'] = setting.value == 'True' if setting else True
    
    return render_template('advanced/dashboard_links.html', links=available_links)


@advanced_bp.route('/version-control', methods=['GET', 'POST'])
@owner_only
def version_control():
    """إدارة النسخ والإصدارات"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_version':
            version_name = request.form.get('version_name')
            version_notes = request.form.get('version_notes')
            
            db.session.add(SystemSettings(key=f'version_{version_name}_date', value=str(datetime.utcnow())))
            db.session.add(SystemSettings(key=f'version_{version_name}_notes', value=version_notes))
            db.session.commit()
            
            flash(f'✅ تم إنشاء إصدار: {version_name}', 'success')
            return redirect(url_for('advanced.version_control'))
    
    versions = []
    version_settings = SystemSettings.query.filter(
        SystemSettings.key.like('version_%_date')
    ).all()
    
    for v in version_settings:
        name = v.key.replace('version_', '').replace('_date', '')
        notes_setting = SystemSettings.query.filter_by(key=f'version_{name}_notes').first()
        versions.append({
            'name': name,
            'date': v.value,
            'notes': notes_setting.value if notes_setting else ''
        })
    
    return render_template('advanced/version_control.html', versions=versions)


@advanced_bp.route('/licensing', methods=['GET', 'POST'])
@owner_only
def licensing():
    """إدارة التراخيص والتفعيل"""
    if request.method == 'POST':
        license_key = request.form.get('license_key')
        client_name = request.form.get('client_name')
        expiry_date = request.form.get('expiry_date')
        max_users = request.form.get('max_users')
        
        license_data = {
            'key': license_key,
            'client': client_name,
            'expiry': expiry_date,
            'max_users': max_users,
            'activated_at': str(datetime.utcnow())
        }
        
        setting = SystemSettings.query.filter_by(key='license_info').first()
        if setting:
            setting.value = json.dumps(license_data)
        else:
            db.session.add(SystemSettings(key='license_info', value=json.dumps(license_data)))
        
        db.session.commit()
        flash('✅ تم تفعيل الترخيص', 'success')
        return redirect(url_for('advanced.licensing'))
    
    license_setting = SystemSettings.query.filter_by(key='license_info').first()
    license_info = json.loads(license_setting.value) if license_setting and license_setting.value else {}
    
    return render_template('advanced/licensing.html', license=license_info)


@advanced_bp.route('/module-manager', methods=['GET', 'POST'])
@owner_only
def module_manager():
    """مدير الوحدات - تفعيل/تعطيل"""
    if request.method == 'POST':
        module_key = request.form.get('module_key')
        enabled = request.form.get('enabled') == 'on'
        
        setting = SystemSettings.query.filter_by(key=f'module_{module_key}_enabled').first()
        if setting:
            setting.value = str(enabled)
        else:
            db.session.add(SystemSettings(key=f'module_{module_key}_enabled', value=str(enabled)))
        
        db.session.commit()
        flash(f'✅ تم تحديث: {module_key}', 'success')
        return redirect(url_for('advanced.module_manager'))
    
    modules = [
        {'key': 'customers', 'name': 'إدارة العملاء', 'icon': 'users', 'color': 'primary'},
        {'key': 'service', 'name': 'الصيانة', 'icon': 'wrench', 'color': 'success'},
        {'key': 'sales', 'name': 'المبيعات', 'icon': 'shopping-cart', 'color': 'info'},
        {'key': 'warehouses', 'name': 'المستودعات', 'icon': 'warehouse', 'color': 'warning'},
        {'key': 'vendors', 'name': 'الموردين', 'icon': 'truck', 'color': 'secondary'},
        {'key': 'partners', 'name': 'الشركاء', 'icon': 'handshake', 'color': 'success'},
        {'key': 'shipments', 'name': 'الشحنات', 'icon': 'ship', 'color': 'info'},
        {'key': 'payments', 'name': 'الدفعات', 'icon': 'money-bill-wave', 'color': 'success'},
        {'key': 'checks', 'name': 'الشيكات', 'icon': 'money-check', 'color': 'warning'},
        {'key': 'expenses', 'name': 'النفقات', 'icon': 'receipt', 'color': 'danger'},
        {'key': 'ledger', 'name': 'دفتر الأستاذ', 'icon': 'book', 'color': 'dark'},
        {'key': 'shop', 'name': 'المتجر الإلكتروني', 'icon': 'store', 'color': 'primary'},
        {'key': 'reports', 'name': 'التقارير', 'icon': 'chart-bar', 'color': 'info'},
    ]
    
    for module in modules:
        setting = SystemSettings.query.filter_by(key=f'module_{module["key"]}_enabled').first()
        module['enabled'] = setting.value == 'True' if setting else True
    
    return render_template('advanced/module_manager.html', modules=modules)


@advanced_bp.route('/backup-manager', methods=['GET', 'POST'])
@owner_only
def backup_manager():
    """مدير النسخ الاحتياطية المتقدم"""
    backup_dir = os.path.join(current_app.root_path, 'instance', 'backups', 'db')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_backup':
            backup_name = request.form.get('backup_name') or f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            
            try:
                os.makedirs(backup_dir, exist_ok=True)
                db_path = os.path.join(current_app.root_path, 'instance', 'app.db')
                backup_path = os.path.join(backup_dir, f'{backup_name}.db')
                
                shutil.copy2(db_path, backup_path)
                
                flash(f'✅ تم إنشاء نسخة احتياطية: {backup_name}', 'success')
            except Exception as e:
                flash(f'❌ خطأ: {str(e)}', 'danger')
            
            return redirect(url_for('advanced.backup_manager'))
    
    backups = []
    if os.path.exists(backup_dir):
        for filename in sorted(os.listdir(backup_dir), reverse=True):
            if filename.endswith('.db'):
                filepath = os.path.join(backup_dir, filename)
                size = os.path.getsize(filepath) / (1024 * 1024)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                backups.append({
                    'name': filename,
                    'size': f'{size:.2f} MB',
                    'date': mtime.strftime('%Y-%m-%d %H:%M')
                })
    
    return render_template('advanced/backup_manager.html', backups=backups)


@advanced_bp.route('/api-generator', methods=['GET', 'POST'])
@owner_only
def api_generator():
    """مولد API تلقائي"""
    if request.method == 'POST':
        table_name = request.form.get('table_name')
        endpoints = request.form.getlist('endpoints')
        
        flash(f'✅ تم إنشاء API لـ {table_name}', 'success')
        return redirect(url_for('advanced.api_generator'))
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    return render_template('advanced/api_generator.html', tables=tables)


@advanced_bp.route('/feature-flags', methods=['GET', 'POST'])
@owner_only
def feature_flags():
    """إدارة Feature Flags"""
    if request.method == 'POST':
        flag_key = request.form.get('flag_key')
        enabled = request.form.get('enabled') == 'on'
        
        setting = SystemSettings.query.filter_by(key=f'feature_{flag_key}').first()
        if setting:
            setting.value = str(enabled)
        else:
            db.session.add(SystemSettings(key=f'feature_{flag_key}', value=str(enabled)))
        
        db.session.commit()
        flash(f'✅ تم تحديث: {flag_key}', 'success')
        return redirect(url_for('advanced.feature_flags'))
    
    flags = [
        {'key': 'ai_assistant', 'name': 'المساعد الذكي', 'description': 'تفعيل AI في دفتر الأستاذ'},
        {'key': 'auto_backup', 'name': 'نسخ احتياطي تلقائي', 'description': 'نسخ يومية تلقائية'},
        {'key': 'email_notifications', 'name': 'إشعارات البريد', 'description': 'إرسال تنبيهات بالبريد'},
        {'key': 'whatsapp_notifications', 'name': 'إشعارات واتساب', 'description': 'إرسال رسائل واتساب'},
        {'key': 'dark_mode', 'name': 'الوضع الداكن', 'description': 'تفعيل الثيم الداكن'},
        {'key': 'advanced_search', 'name': 'البحث المتقدم', 'description': 'بحث ذكي بالذكاء الاصطناعي'},
        {'key': 'auto_gl_sync', 'name': 'مزامنة GL تلقائية', 'description': 'مزامنة دفتر الأستاذ تلقائياً'},
        {'key': 'barcode_scanner', 'name': 'قارئ الباركود', 'description': 'تفعيل مسح الباركود'},
        {'key': 'online_shop', 'name': 'المتجر الإلكتروني', 'description': 'تفعيل المتجر'},
        {'key': 'multi_currency', 'name': 'عملات متعددة', 'description': 'دعم عملات متعددة'},
    ]
    
    for flag in flags:
        setting = SystemSettings.query.filter_by(key=f'feature_{flag["key"]}').first()
        flag['enabled'] = setting.value == 'True' if setting else False
    
    return render_template('advanced/feature_flags.html', flags=flags)


@advanced_bp.route('/system-health', methods=['GET'])
@owner_only
def system_health():
    """فحص صحة النظام الشامل"""
    health_checks = []
    
    health_checks.append(_check_database())
    health_checks.append(_check_disk_space())
    health_checks.append(_check_permissions())
    health_checks.append(_check_integrations())
    health_checks.append(_check_performance())
    
    overall_health = sum(1 for c in health_checks if c['status'] == 'ok') / len(health_checks) * 100
    
    return render_template('advanced/system_health.html', 
                         checks=health_checks,
                         overall=overall_health)


def _merge_databases(source_db_path, mode='smart'):
    """دمج قاعدة بيانات خارجية مع الحالية"""
    conn_source = sqlite3.connect(source_db_path)
    conn_target = sqlite3.connect(os.path.join(current_app.root_path, 'instance', 'app.db'))
    
    cursor_source = conn_source.cursor()
    cursor_target = conn_target.cursor()
    
    tables = cursor_source.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    
    added_count = 0
    
    for (table_name,) in tables:
        if table_name.startswith('sqlite_'):
            continue
        
        try:
            rows = cursor_source.execute(f"SELECT * FROM {table_name}").fetchall()
            
            if mode == 'smart':
                for row in rows:
                    try:
                        placeholders = ','.join(['?' for _ in row])
                        cursor_target.execute(f"INSERT OR IGNORE INTO {table_name} VALUES ({placeholders})", row)
                        added_count += cursor_target.rowcount
                    except:
                        pass
        except:
            pass
    
    conn_target.commit()
    conn_source.close()
    conn_target.close()
    
    return {'added': added_count}


def _get_db_size():
    """حجم قاعدة البيانات"""
    try:
        db_path = os.path.join(current_app.root_path, 'instance', 'app.db')
        size = os.path.getsize(db_path) / (1024 * 1024)
        return f'{size:.2f} MB'
    except:
        return 'N/A'


def _count_all_records():
    """عدد جميع السجلات"""
    try:
        total = 0
        inspector = inspect(db.engine)
        for table in inspector.get_table_names():
            count = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            total += count
        return total
    except:
        return 0


def _check_database():
    """فحص قاعدة البيانات"""
    try:
        db.session.execute(text("SELECT 1"))
        return {'name': 'قاعدة البيانات', 'status': 'ok', 'message': 'تعمل بشكل صحيح'}
    except:
        return {'name': 'قاعدة البيانات', 'status': 'error', 'message': 'خطأ في الاتصال'}


def _check_disk_space():
    """فحص المساحة"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(current_app.root_path)
        free_gb = free / (1024**3)
        if free_gb < 1:
            return {'name': 'المساحة', 'status': 'warning', 'message': f'متبقي {free_gb:.2f} GB'}
        return {'name': 'المساحة', 'status': 'ok', 'message': f'متبقي {free_gb:.2f} GB'}
    except:
        return {'name': 'المساحة', 'status': 'unknown', 'message': 'غير معروف'}


def _check_permissions():
    """فحص الصلاحيات"""
    try:
        test_file = os.path.join(current_app.root_path, 'instance', '.test_write')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return {'name': 'صلاحيات الكتابة', 'status': 'ok', 'message': 'صلاحيات صحيحة'}
    except:
        return {'name': 'صلاحيات الكتابة', 'status': 'error', 'message': 'لا توجد صلاحيات'}


def _check_integrations():
    """فحص التكاملات"""
    integrations_count = SystemSettings.query.filter(
        (SystemSettings.key.like('whatsapp_%')) |
        (SystemSettings.key.like('smtp_%')) |
        (SystemSettings.key.like('reader_%'))
    ).count()
    
    if integrations_count > 0:
        return {'name': 'التكاملات', 'status': 'ok', 'message': f'{integrations_count} تكامل مفعل'}
    return {'name': 'التكاملات', 'status': 'warning', 'message': 'لا توجد تكاملات'}


def _check_performance():
    """فحص الأداء"""
    try:
        start = datetime.now()
        db.session.execute(text("SELECT COUNT(*) FROM users"))
        elapsed = (datetime.now() - start).total_seconds() * 1000
        
        if elapsed < 100:
            return {'name': 'الأداء', 'status': 'ok', 'message': f'{elapsed:.0f}ms'}
        elif elapsed < 500:
            return {'name': 'الأداء', 'status': 'warning', 'message': f'{elapsed:.0f}ms'}
        else:
            return {'name': 'الأداء', 'status': 'error', 'message': f'{elapsed:.0f}ms بطيء'}
    except:
        return {'name': 'الأداء', 'status': 'unknown', 'message': 'غير معروف'}


@advanced_bp.route('/system-cloner', methods=['GET', 'POST'])
@owner_only
def system_cloner():
    """مولد الأنظمة المخصصة - استنساخ ذكي للمزايا المختارة"""
    
    available_modules = {
        'core': {
            'name': 'النواة الأساسية',
            'description': 'المستخدمين + الصلاحيات + الإعدادات',
            'required': True,
            'files': {
                'models': ['User', 'Role', 'Permission', 'SystemSettings'],
                'routes': ['auth', 'main', 'users', 'roles', 'permissions'],
                'templates': ['base.html', 'dashboard.html', 'auth/*', 'users/*'],
                'static': ['css/style.css', 'js/app.js']
            }
        },
        'customers': {
            'name': 'إدارة العملاء',
            'description': 'العملاء + كشوف الحساب',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Customer'],
                'routes': ['customers'],
                'templates': ['customers/*'],
                'static': []
            }
        },
        'sales': {
            'name': 'المبيعات',
            'description': 'فواتير المبيعات + الأصناف',
            'required': False,
            'dependencies': ['core', 'customers'],
            'files': {
                'models': ['Sale', 'SaleLine', 'Product'],
                'routes': ['sales'],
                'templates': ['sales/*'],
                'static': ['css/sales.css']
            }
        },
        'service': {
            'name': 'الصيانة',
            'description': 'طلبات الصيانة + القطع',
            'required': False,
            'dependencies': ['core', 'customers'],
            'files': {
                'models': ['ServiceRequest', 'ServicePart', 'ServiceTask'],
                'routes': ['service'],
                'templates': ['service/*'],
                'static': ['css/service.css']
            }
        },
        'warehouses': {
            'name': 'المستودعات',
            'description': 'المخزون + الحجوزات',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Warehouse', 'StockLevel', 'PreOrder'],
                'routes': ['warehouses', 'parts'],
                'templates': ['warehouses/*', 'parts/*'],
                'static': ['css/warehouses.css']
            }
        },
        'payments': {
            'name': 'الدفعات',
            'description': 'الدفعات + الشيكات',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Payment', 'PaymentSplit', 'Check'],
                'routes': ['payments', 'checks'],
                'templates': ['payments/*', 'checks/*'],
                'static': []
            }
        },
        'expenses': {
            'name': 'النفقات',
            'description': 'المصروفات + الموظفين',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Expense', 'ExpenseType', 'Employee'],
                'routes': ['expenses'],
                'templates': ['expenses/*'],
                'static': []
            }
        },
        'vendors': {
            'name': 'الموردين والشركاء',
            'description': 'الموردين + الشركاء + التسويات',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Supplier', 'Partner', 'SupplierSettlement', 'PartnerSettlement'],
                'routes': ['vendors', 'supplier_settlements', 'partner_settlements'],
                'templates': ['vendors/*'],
                'static': []
            }
        },
        'shipments': {
            'name': 'الشحنات',
            'description': 'الشحنات + البنود',
            'required': False,
            'dependencies': ['core', 'warehouses', 'vendors'],
            'files': {
                'models': ['Shipment', 'ShipmentItem', 'ShipmentPartner'],
                'routes': ['shipments'],
                'templates': ['shipments/*'],
                'static': ['css/shipments.css']
            }
        },
        'ledger': {
            'name': 'دفتر الأستاذ',
            'description': 'المحاسبة + القيود',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['GLBatch', 'GLEntry', 'Account'],
                'routes': ['ledger_blueprint', 'ledger_ai_assistant'],
                'templates': ['ledger/*'],
                'static': []
            }
        },
        'shop': {
            'name': 'المتجر الإلكتروني',
            'description': 'المتجر + السلة + الطلبات',
            'required': False,
            'dependencies': ['core', 'customers', 'sales', 'warehouses'],
            'files': {
                'models': ['OnlineCart', 'OnlineCartItem', 'OnlinePreOrder', 'OnlinePayment'],
                'routes': ['shop'],
                'templates': ['shop/*'],
                'static': ['css/shop.css']
            }
        },
        'reports': {
            'name': 'التقارير',
            'description': 'تقارير شاملة',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': [],
                'routes': ['report_routes', 'admin_reports'],
                'templates': ['reports/*', 'admin/reports/*'],
                'static': ['css/reporting.css']
            }
        },
        'currencies': {
            'name': 'العملات',
            'description': 'أسعار الصرف',
            'required': False,
            'dependencies': ['core'],
            'files': {
                'models': ['Currency', 'ExchangeRate'],
                'routes': ['currencies'],
                'templates': ['currencies/*'],
                'static': []
            }
        },
    }
    
    if request.method == 'POST':
        selected_modules = request.form.getlist('modules')
        clone_name = request.form.get('clone_name', 'custom_system')
        
        try:
            result = _clone_system(selected_modules, clone_name, available_modules)
            
            flash(f'✅ تم إنشاء النظام المخصص: {clone_name}', 'success')
            flash(f'📦 الملفات: {result["files_count"]} ملف', 'info')
            flash(f'📍 الموقع: {result["output_path"]}', 'info')
            
            return redirect(url_for('advanced.system_cloner'))
            
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
            return redirect(url_for('advanced.system_cloner'))
    
    return render_template('advanced/system_cloner.html', modules=available_modules)


def _clone_system(selected_modules, clone_name, available_modules):
    """استنساخ النظام بالمزايا المختارة"""
    
    modules_to_clone = set(selected_modules)
    modules_to_clone.add('core')
    
    for module_key in list(modules_to_clone):
        module = available_modules.get(module_key)
        if module and 'dependencies' in module:
            modules_to_clone.update(module['dependencies'])
    
    output_dir = os.path.join(current_app.root_path, 'instance', 'clones', clone_name)
    os.makedirs(output_dir, exist_ok=True)
    
    files_copied = 0
    
    for module_key in modules_to_clone:
        module = available_modules.get(module_key)
        if not module:
            continue
        
        files = module.get('files', {})
        
        for route in files.get('routes', []):
            src = os.path.join(current_app.root_path, 'routes', f'{route}.py')
            if os.path.exists(src):
                dst_dir = os.path.join(output_dir, 'routes')
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, os.path.join(dst_dir, f'{route}.py'))
                files_copied += 1
        
        for template_pattern in files.get('templates', []):
            if '*' in template_pattern:
                folder = template_pattern.replace('/*', '')
                src_dir = os.path.join(current_app.root_path, 'templates', folder)
                if os.path.exists(src_dir):
                    dst_dir = os.path.join(output_dir, 'templates', folder)
                    os.makedirs(dst_dir, exist_ok=True)
                    for file in os.listdir(src_dir):
                        if file.endswith('.html'):
                            shutil.copy2(
                                os.path.join(src_dir, file),
                                os.path.join(dst_dir, file)
                            )
                            files_copied += 1
            else:
                src = os.path.join(current_app.root_path, 'templates', template_pattern)
                if os.path.exists(src):
                    dst_dir = os.path.join(output_dir, 'templates')
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(src, os.path.join(dst_dir, os.path.basename(template_pattern)))
                    files_copied += 1
        
        for static_file in files.get('static', []):
            src = os.path.join(current_app.root_path, 'static', static_file)
            if os.path.exists(src):
                dst_dir = os.path.join(output_dir, 'static', os.path.dirname(static_file))
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, os.path.join(dst_dir, os.path.basename(static_file)))
                files_copied += 1
    
    _create_custom_models_file(output_dir, modules_to_clone, available_modules)
    _create_custom_app_file(output_dir, modules_to_clone)
    _create_requirements_file(output_dir)
    _create_readme_file(output_dir, clone_name, modules_to_clone, available_modules)
    
    files_copied += 4
    
    return {
        'output_path': output_dir,
        'files_count': files_copied,
        'modules': list(modules_to_clone)
    }


def _create_custom_models_file(output_dir, selected_modules, available_modules):
    """إنشاء ملف models.py مخصص"""
    
    models_content = """# models.py - Custom System Models
# Generated by System Cloner

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from decimal import Decimal

db = SQLAlchemy()

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditMixin:
    created_by_id = Column(Integer, ForeignKey('users.id'))
    updated_by_id = Column(Integer, ForeignKey('users.id'))

"""
    
    models_to_include = set()
    for module_key in selected_modules:
        module = available_modules.get(module_key)
        if module and 'files' in module:
            models_to_include.update(module['files'].get('models', []))
    
    models_content += f"\n# Selected Models: {', '.join(models_to_include)}\n"
    models_content += "# Note: Extract actual model definitions from main models.py\n\n"
    
    with open(os.path.join(output_dir, 'models.py'), 'w', encoding='utf-8') as f:
        f.write(models_content)


def _create_custom_app_file(output_dir, selected_modules):
    """إنشاء ملف app.py مخصص"""
    
    app_content = f"""# app.py - Custom System
# Generated by System Cloner
# Modules: {', '.join(selected_modules)}

from flask import Flask
from flask_login import LoginManager
from extensions import db, migrate, csrf
from models import User

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-this-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
"""
    
    for module in selected_modules:
        if module != 'core':
            app_content += f"    from routes.{module} import {module}_bp\n"
            app_content += f"    app.register_blueprint({module}_bp)\n"
    
    app_content += """
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
"""
    
    with open(os.path.join(output_dir, 'app.py'), 'w', encoding='utf-8') as f:
        f.write(app_content)


def _create_requirements_file(output_dir):
    """إنشاء requirements.txt"""
    
    requirements = """Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Migrate==4.0.5
Flask-WTF==1.2.1
WTForms==3.1.1
"""
    
    with open(os.path.join(output_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
        f.write(requirements)


def _create_readme_file(output_dir, clone_name, selected_modules, available_modules):
    """إنشاء README.md"""
    
    readme = f"""# {clone_name}

نظام مخصص تم إنشاؤه بواسطة System Cloner

## الوحدات المضمنة:

"""
    
    for module_key in selected_modules:
        module = available_modules.get(module_key)
        if module:
            readme += f"- **{module['name']}**: {module['description']}\n"
    
    readme += """

## التثبيت:

```bash
pip install -r requirements.txt
flask db upgrade
python app.py
```

## الوصول:

```
http://localhost:5000
Username: admin
Password: admin123
```

---

تم الإنشاء: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(os.path.join(output_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
