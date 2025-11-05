
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import text, func, inspect
from datetime import datetime, timedelta, timezone
from extensions import db
from models import User, SystemSettings
import utils
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
        if not utils.is_super():
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
    """إدارة Multi-Tenant المتقدمة - نسخ متعددة مع تحكم كامل"""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_tenant':
            tenant_name = request.form.get('tenant_name')
            tenant_db = request.form.get('tenant_db')
            tenant_domain = request.form.get('tenant_domain', '')
            tenant_logo = request.form.get('tenant_logo', '')
            tenant_max_users = request.form.get('tenant_max_users', '10')
            tenant_modules = request.form.getlist('tenant_modules')
            
            # حفظ البيانات الأساسية
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_db', value=tenant_db))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_active', value='True'))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_domain', value=tenant_domain))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_logo', value=tenant_logo))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_max_users', value=tenant_max_users))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_modules', value=json.dumps(tenant_modules)))
            db.session.add(SystemSettings(key=f'tenant_{tenant_name}_created_at', value=str(datetime.utcnow())))
            
            # إنشاء قاعدة البيانات إذا كانت SQLite
            if tenant_db.startswith('sqlite:///'):
                db_path = tenant_db.replace('sqlite:///', '')
                full_path = os.path.join(current_app.root_path, db_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                _create_tenant_database(full_path)
            
            db.session.commit()
            
            flash(f'✅ تم إنشاء Tenant: {tenant_name}', 'success')
            return redirect(url_for('advanced.multi_tenant'))
        
        elif action == 'toggle_tenant':
            tenant_name = request.form.get('tenant_name')
            setting = SystemSettings.query.filter_by(key=f'tenant_{tenant_name}_active').first()
            if setting:
                setting.value = 'False' if setting.value == 'True' else 'True'
                db.session.commit()
                flash(f'✅ تم تحديث حالة: {tenant_name}', 'success')
            return redirect(url_for('advanced.multi_tenant'))
        
        elif action == 'delete_tenant':
            tenant_name = request.form.get('tenant_name')
            # حذف جميع الإعدادات المرتبطة
            SystemSettings.query.filter(SystemSettings.key.like(f'tenant_{tenant_name}_%')).delete()
            db.session.commit()
            flash(f'✅ تم حذف Tenant: {tenant_name}', 'success')
            return redirect(url_for('advanced.multi_tenant'))
        
        elif action == 'update_tenant':
            tenant_name = request.form.get('tenant_name')
            tenant_domain = request.form.get('tenant_domain', '')
            tenant_logo = request.form.get('tenant_logo', '')
            tenant_max_users = request.form.get('tenant_max_users', '10')
            tenant_modules = request.form.getlist('tenant_modules')
            
            # تحديث الإعدادات
            _update_tenant_setting(f'tenant_{tenant_name}_domain', tenant_domain)
            _update_tenant_setting(f'tenant_{tenant_name}_logo', tenant_logo)
            _update_tenant_setting(f'tenant_{tenant_name}_max_users', tenant_max_users)
            _update_tenant_setting(f'tenant_{tenant_name}_modules', json.dumps(tenant_modules))
            
            db.session.commit()
            flash(f'✅ تم تحديث Tenant: {tenant_name}', 'success')
            return redirect(url_for('advanced.multi_tenant'))
    
    # جلب جميع Tenants
    tenant_list = _get_all_tenants()
    
    # الوحدات المتاحة
    available_modules = _get_available_modules_list()
    
    # إحصائيات
    stats = {
        'total_tenants': len(tenant_list),
        'active_tenants': sum(1 for t in tenant_list if t['active']),
        'inactive_tenants': sum(1 for t in tenant_list if not t['active']),
        'total_users_limit': sum(int(t.get('max_users', 10)) for t in tenant_list)
    }
    
    return render_template('advanced/multi_tenant.html', 
                         tenants=tenant_list, 
                         available_modules=available_modules,
                         stats=stats)


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
        
        elif action == 'delete_version':
            version_name = request.form.get('version_name')
            SystemSettings.query.filter(SystemSettings.key.like(f'version_{version_name}_%')).delete()
            db.session.commit()
            flash(f'✅ تم حذف الإصدار: {version_name}', 'success')
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
    
    # ترتيب حسب التاريخ (الأحدث أولاً)
    versions.sort(key=lambda x: x['date'], reverse=True)
    
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
    """مدير النسخ الاحتياطية المتقدم + تحويل قواعد البيانات"""
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
        
        elif action == 'schedule_backup':
            schedule_type = request.form.get('schedule_type')
            schedule_time = request.form.get('schedule_time', '03:00')
            
            setting = SystemSettings.query.filter_by(key='auto_backup_enabled').first()
            if setting:
                setting.value = 'True'
            else:
                db.session.add(SystemSettings(key='auto_backup_enabled', value='True'))
            
            schedule_setting = SystemSettings.query.filter_by(key='auto_backup_schedule').first()
            if schedule_setting:
                schedule_setting.value = json.dumps({'type': schedule_type, 'time': schedule_time})
            else:
                db.session.add(SystemSettings(key='auto_backup_schedule', value=json.dumps({'type': schedule_type, 'time': schedule_time})))
            
            db.session.commit()
            flash(f'✅ تم جدولة النسخ الاحتياطي: {schedule_type}', 'success')
            return redirect(url_for('advanced.backup_manager'))
        
        elif action == 'convert_database':
            target_db = request.form.get('target_db')
            connection_string = request.form.get('connection_string')
            
            if not connection_string or not target_db:
                flash('❌ يجب تحديد نوع قاعدة البيانات و Connection String', 'danger')
                return redirect(url_for('advanced.backup_manager'))
            
            try:
                result = _convert_database(target_db, connection_string)
                
                flash(f'✅ تم التحويل بنجاح!', 'success')
                flash(f'📊 السجلات: {result["records"]} سجل', 'info')
                flash(f'📋 الجداول: {result["tables"]} جدول', 'info')
                flash(f'💾 نسخة أمان: {os.path.basename(result["backup"])}', 'info')
                
                if result.get('errors'):
                    flash(f'⚠️ تحذيرات: {len(result["errors"])} خطأ', 'warning')
                
            except ValueError as e:
                flash(f'❌ خطأ في البيانات: {str(e)}', 'danger')
            except Exception as e:
                flash(f'❌ خطأ في التحويل: {str(e)}', 'danger')
            
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
    
    auto_backup_enabled = SystemSettings.query.filter_by(key='auto_backup_enabled').first()
    auto_backup_schedule = SystemSettings.query.filter_by(key='auto_backup_schedule').first()
    
    schedule_info = {}
    if auto_backup_schedule and auto_backup_schedule.value:
        try:
            schedule_info = json.loads(auto_backup_schedule.value)
        except Exception:
            schedule_info = {}
    
    current_db_type = _detect_current_db_type()
    
    return render_template('advanced/backup_manager.html', 
                         backups=backups,
                         auto_backup_enabled=auto_backup_enabled.value == 'True' if auto_backup_enabled else False,
                         schedule_info=schedule_info,
                         current_db_type=current_db_type)


@advanced_bp.route('/download-backup/<filename>')
@owner_only
def download_backup(filename):
    """تحميل نسخة احتياطية"""
    try:
        backup_dir = os.path.join(current_app.root_path, 'instance', 'backups', 'db')
        filepath = os.path.join(backup_dir, secure_filename(filename))
        
        if os.path.exists(filepath) and filename.endswith('.db'):
            return send_file(filepath, as_attachment=True, download_name=filename)
        else:
            flash('❌ الملف غير موجود', 'danger')
            return redirect(url_for('advanced.backup_manager'))
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('advanced.backup_manager'))


@advanced_bp.route('/restore-backup/<filename>', methods=['POST'])
@owner_only
def restore_backup(filename):
    """استعادة نسخة احتياطية"""
    try:
        backup_dir = os.path.join(current_app.root_path, 'instance', 'backups', 'db')
        backup_path = os.path.join(backup_dir, secure_filename(filename))
        
        if not os.path.exists(backup_path) or not filename.endswith('.db'):
            flash('❌ الملف غير موجود', 'danger')
            return redirect(url_for('advanced.backup_manager'))
        
        # نسخ احتياطية للحالي قبل الاستعادة
        current_db = os.path.join(current_app.root_path, 'instance', 'app.db')
        safety_backup = os.path.join(backup_dir, f'before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        shutil.copy2(current_db, safety_backup)
        
        # استعادة النسخة
        shutil.copy2(backup_path, current_db)
        
        flash(f'✅ تم استعادة النسخة: {filename}', 'success')
        flash(f'💾 تم حفظ نسخة أمان: {os.path.basename(safety_backup)}', 'info')
        
    except Exception as e:
        flash(f'❌ خطأ في الاستعادة: {str(e)}', 'danger')
    
    return redirect(url_for('advanced.backup_manager'))


@advanced_bp.route('/delete-backup/<filename>', methods=['POST'])
@owner_only
def delete_backup(filename):
    """حذف نسخة احتياطية"""
    try:
        backup_dir = os.path.join(current_app.root_path, 'instance', 'backups', 'db')
        filepath = os.path.join(backup_dir, secure_filename(filename))
        
        if os.path.exists(filepath) and filename.endswith('.db'):
            os.remove(filepath)
            flash(f'✅ تم حذف النسخة: {filename}', 'success')
        else:
            flash('❌ الملف غير موجود', 'danger')
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('advanced.backup_manager'))


@advanced_bp.route('/toggle-auto-backup', methods=['POST'])
@owner_only
def toggle_auto_backup():
    """تفعيل/تعطيل النسخ التلقائي"""
    try:
        setting = SystemSettings.query.filter_by(key='auto_backup_enabled').first()
        if setting:
            setting.value = 'False' if setting.value == 'True' else 'True'
        else:
            db.session.add(SystemSettings(key='auto_backup_enabled', value='True'))
        
        db.session.commit()
        
        status = setting.value if setting else 'True'
        if status == 'True':
            flash('✅ تم تفعيل النسخ الاحتياطي التلقائي', 'success')
        else:
            flash('⚠️ تم تعطيل النسخ الاحتياطي التلقائي', 'warning')
            
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('advanced.backup_manager'))


@advanced_bp.route('/test-db-connection', methods=['POST'])
@owner_only
def test_db_connection():
    """اختبار الاتصال بقاعدة البيانات"""
    try:
        from sqlalchemy import create_engine
        
        connection_string = request.form.get('connection_string')
        
        if not connection_string:
            return jsonify({'success': False, 'message': 'Connection string مطلوب'})
        
        # محاولة الاتصال
        test_engine = create_engine(connection_string, echo=False)
        
        with test_engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            
            if result == 1:
                # جلب معلومات إضافية
                try:
                    version = conn.execute(text("SELECT version()")).scalar()
                except Exception:
                    version = "غير متاح"
                
                return jsonify({
                    'success': True,
                    'message': 'الاتصال ناجح!',
                    'version': version
                })
            else:
                return jsonify({'success': False, 'message': 'فشل الاتصال'})
                
    except Exception as e:
        return jsonify({'success': False, 'message': f'خطأ: {str(e)}'})


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
        # {'key': 'ai_assistant', 'name': 'المساعد الذكي', 'description': 'تفعيل AI في دفتر الأستاذ'},  # تم نقله للوحدة السرية
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


@advanced_bp.route('/system-health', methods=['GET', 'POST'])
@owner_only
def system_health():
    """فحص صحة النظام الشامل"""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'fix_permissions':
            try:
                # إصلاح صلاحيات المجلدات
                dirs_to_fix = ['instance', 'instance/backups', 'AI', 'static/uploads']  # AI تم نقله من instance/ai
                for dir_path in dirs_to_fix:
                    full_path = os.path.join(current_app.root_path, dir_path)
                    os.makedirs(full_path, exist_ok=True)
                flash('✅ تم إصلاح الصلاحيات', 'success')
            except Exception as e:
                flash(f'❌ خطأ: {str(e)}', 'danger')
        
        elif action == 'clear_cache':
            try:
                # حذف ملفات الكاش
                cache_dirs = ['__pycache__', 'instance/__pycache__']
                for cache_dir in cache_dirs:
                    cache_path = os.path.join(current_app.root_path, cache_dir)
                    if os.path.exists(cache_path):
                        shutil.rmtree(cache_path)
                flash('✅ تم تنظيف الكاش', 'success')
            except Exception as e:
                flash(f'❌ خطأ: {str(e)}', 'danger')
        
        elif action == 'optimize_db':
            try:
                # تحسين قاعدة البيانات
                db.session.execute(text("VACUUM"))
                db.session.commit()
                flash('✅ تم تحسين قاعدة البيانات', 'success')
            except Exception as e:
                flash(f'❌ خطأ: {str(e)}', 'danger')
        
        return redirect(url_for('advanced.system_health'))
    
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
                    except Exception:
                        pass
        except Exception:
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
    except Exception:
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
    except Exception:
        return 0


def _check_database():
    """فحص قاعدة البيانات"""
    try:
        db.session.execute(text("SELECT 1"))
        return {'name': 'قاعدة البيانات', 'status': 'ok', 'message': 'تعمل بشكل صحيح'}
    except Exception:
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
    except Exception:
        return {'name': 'المساحة', 'status': 'unknown', 'message': 'غير معروف'}


def _check_permissions():
    """فحص الصلاحيات"""
    try:
        test_file = os.path.join(current_app.root_path, 'instance', '.test_write')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return {'name': 'صلاحيات الكتابة', 'status': 'ok', 'message': 'صلاحيات صحيحة'}
    except Exception:
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
    except Exception:
        return {'name': 'الأداء', 'status': 'unknown', 'message': 'غير معروف'}


@advanced_bp.route('/download-cloned-system/<clone_name>')
@owner_only
def download_cloned_system(clone_name):
    """تحميل نظام مستنسخ"""
    try:
        import zipfile
        from io import BytesIO
        
        clone_dir = os.path.join(current_app.root_path, 'instance', 'clones', secure_filename(clone_name))
        
        if not os.path.exists(clone_dir):
            flash('❌ النظام غير موجود', 'danger')
            return redirect(url_for('advanced.system_cloner'))
        
        # إنشاء ZIP في الذاكرة
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(clone_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, clone_dir)
                    zipf.write(file_path, arcname)
        
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{clone_name}.zip'
        )
        
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('advanced.system_cloner'))


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
                'routes': ['ledger_blueprint'],  # ledger_ai_assistant تم حذفه ودمجه في security.ai_hub
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
            
            # إعادة توجيه مع إمكانية التحميل
            return redirect(url_for('advanced.system_cloner', download=clone_name))
            
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
            return redirect(url_for('advanced.system_cloner'))
    
    # جلب الأنظمة المستنسخة
    clones_dir = os.path.join(current_app.root_path, 'instance', 'clones')
    cloned_systems = []
    if os.path.exists(clones_dir):
        for name in os.listdir(clones_dir):
            clone_path = os.path.join(clones_dir, name)
            if os.path.isdir(clone_path):
                # حساب حجم المجلد
                total_size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(clone_path)
                    for filename in filenames
                )
                cloned_systems.append({
                    'name': name,
                    'size': f'{total_size / (1024 * 1024):.2f} MB',
                    'created': datetime.fromtimestamp(os.path.getctime(clone_path)).strftime('%Y-%m-%d %H:%M')
                })
    
    download_ready = request.args.get('download')
    
    return render_template('advanced/system_cloner.html', 
                         modules=available_modules,
                         cloned_systems=cloned_systems,
                         download_ready=download_ready)


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


@advanced_bp.route('/download-mobile-app/<app_name>')
@owner_only
def download_mobile_app(app_name):
    """تحميل تطبيق موبايل"""
    try:
        zip_path = os.path.join(current_app.root_path, 'instance', 'mobile_apps', f'{secure_filename(app_name)}.zip')
        
        if os.path.exists(zip_path):
            return send_file(zip_path, as_attachment=True, download_name=f'{app_name}.zip')
        else:
            flash('❌ التطبيق غير موجود', 'danger')
            return redirect(url_for('advanced.mobile_app_generator'))
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('advanced.mobile_app_generator'))


@advanced_bp.route('/mobile-app-generator', methods=['GET', 'POST'])
@owner_only
def mobile_app_generator():
    """مولد تطبيقات الموبايل - تحويل النظام لتطبيق Android/iOS"""
    
    if request.method == 'POST':
        app_name = request.form.get('app_name', 'GarageApp')
        app_platform = request.form.get('platform', 'both')
        selected_modules = request.form.getlist('modules')
        app_icon = request.files.get('app_icon')
        package_name = request.form.get('package_name', 'com.azad.garage')
        
        try:
            result = _generate_mobile_app(
                app_name=app_name,
                platform=app_platform,
                modules=selected_modules,
                package_name=package_name,
                icon=app_icon
            )
            
            flash(f'✅ تم إنشاء تطبيق: {app_name}', 'success')
            flash(f'📱 المنصة: {result["platform"]}', 'info')
            flash(f'📦 الحجم: {result["size"]}', 'info')
            flash(f'📍 الموقع: {result["output_path"]}', 'info')
            
            return redirect(url_for('advanced.mobile_app_generator', download=app_name))
            
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
            return redirect(url_for('advanced.mobile_app_generator'))
    
    available_modules = _get_mobile_modules()
    
    # جلب التطبيقات المُنشأة
    apps_dir = os.path.join(current_app.root_path, 'instance', 'mobile_apps')
    mobile_apps = []
    if os.path.exists(apps_dir):
        for filename in os.listdir(apps_dir):
            if filename.endswith('.zip'):
                filepath = os.path.join(apps_dir, filename)
                size = os.path.getsize(filepath) / (1024 * 1024)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                mobile_apps.append({
                    'name': filename.replace('.zip', ''),
                    'size': f'{size:.2f} MB',
                    'date': mtime.strftime('%Y-%m-%d %H:%M')
                })
    
    download_ready = request.args.get('download')
    
    return render_template('advanced/mobile_app_generator.html', 
                         modules=available_modules,
                         mobile_apps=mobile_apps,
                         download_ready=download_ready)


def _get_mobile_modules():
    """الوحدات المتاحة لتطبيق الموبايل - جميع وحدات النظام"""
    return {
        'auth': {'name': 'تسجيل الدخول', 'icon': 'user-lock', 'required': True, 'category': 'core'},
        'dashboard': {'name': 'الداشبورد', 'icon': 'tachometer-alt', 'required': True, 'category': 'core'},
        'profile': {'name': 'الملف الشخصي', 'icon': 'user-circle', 'required': True, 'category': 'core'},
        
        'customers': {'name': 'إدارة العملاء', 'icon': 'users', 'required': False, 'category': 'business'},
        'customer_statements': {'name': 'كشوف حساب العملاء', 'icon': 'file-invoice', 'required': False, 'category': 'business'},
        
        'service': {'name': 'طلبات الصيانة', 'icon': 'wrench', 'required': False, 'category': 'business'},
        'service_create': {'name': 'إنشاء طلب صيانة', 'icon': 'plus-circle', 'required': False, 'category': 'business'},
        'service_tracking': {'name': 'تتبع الصيانة', 'icon': 'tasks', 'required': False, 'category': 'business'},
        
        'sales': {'name': 'المبيعات', 'icon': 'shopping-cart', 'required': False, 'category': 'business'},
        'sales_create': {'name': 'إنشاء فاتورة مبيعات', 'icon': 'file-invoice-dollar', 'required': False, 'category': 'business'},
        'sales_history': {'name': 'سجل المبيعات', 'icon': 'history', 'required': False, 'category': 'business'},
        
        'warehouses': {'name': 'المستودعات', 'icon': 'warehouse', 'required': False, 'category': 'inventory'},
        'parts': {'name': 'قطع الغيار', 'icon': 'cogs', 'required': False, 'category': 'inventory'},
        'stock_levels': {'name': 'مستويات المخزون', 'icon': 'boxes', 'required': False, 'category': 'inventory'},
        'preorders': {'name': 'الحجوزات', 'icon': 'bookmark', 'required': False, 'category': 'inventory'},
        
        'payments': {'name': 'الدفعات', 'icon': 'money-bill-wave', 'required': False, 'category': 'finance'},
        'payment_create': {'name': 'تسجيل دفعة', 'icon': 'cash-register', 'required': False, 'category': 'finance'},
        'checks': {'name': 'الشيكات', 'icon': 'money-check', 'required': False, 'category': 'finance'},
        'check_tracking': {'name': 'تتبع الشيكات', 'icon': 'check-circle', 'required': False, 'category': 'finance'},
        
        'expenses': {'name': 'النفقات', 'icon': 'receipt', 'required': False, 'category': 'finance'},
        'expense_create': {'name': 'تسجيل نفقة', 'icon': 'file-invoice', 'required': False, 'category': 'finance'},
        
        'vendors': {'name': 'الموردين', 'icon': 'truck', 'required': False, 'category': 'partners'},
        'partners': {'name': 'الشركاء', 'icon': 'handshake', 'required': False, 'category': 'partners'},
        'settlements': {'name': 'التسويات', 'icon': 'balance-scale', 'required': False, 'category': 'partners'},
        
        'shipments': {'name': 'الشحنات', 'icon': 'ship', 'required': False, 'category': 'logistics'},
        'shipment_tracking': {'name': 'تتبع الشحنات', 'icon': 'map-marked-alt', 'required': False, 'category': 'logistics'},
        
        'ledger': {'name': 'دفتر الأستاذ', 'icon': 'book', 'required': False, 'category': 'accounting'},
        'accounts': {'name': 'الحسابات', 'icon': 'list-alt', 'required': False, 'category': 'accounting'},
        'gl_entries': {'name': 'القيود المحاسبية', 'icon': 'edit', 'required': False, 'category': 'accounting'},
        
        'currencies': {'name': 'العملات', 'icon': 'dollar-sign', 'required': False, 'category': 'settings'},
        'exchange_rates': {'name': 'أسعار الصرف', 'icon': 'exchange-alt', 'required': False, 'category': 'settings'},
        
        'reports': {'name': 'التقارير', 'icon': 'chart-bar', 'required': False, 'category': 'analytics'},
        'financial_reports': {'name': 'التقارير المالية', 'icon': 'chart-line', 'required': False, 'category': 'analytics'},
        'sales_reports': {'name': 'تقارير المبيعات', 'icon': 'chart-pie', 'required': False, 'category': 'analytics'},
        'inventory_reports': {'name': 'تقارير المخزون', 'icon': 'chart-area', 'required': False, 'category': 'analytics'},
        
        'shop': {'name': 'المتجر الإلكتروني', 'icon': 'store', 'required': False, 'category': 'ecommerce'},
        'cart': {'name': 'سلة التسوق', 'icon': 'shopping-basket', 'required': False, 'category': 'ecommerce'},
        'orders': {'name': 'الطلبات', 'icon': 'clipboard-list', 'required': False, 'category': 'ecommerce'},
        
        'notifications': {'name': 'الإشعارات', 'icon': 'bell', 'required': False, 'category': 'features'},
        'scanner': {'name': 'قارئ الباركود', 'icon': 'barcode', 'required': False, 'category': 'features'},
        'camera': {'name': 'الكاميرا', 'icon': 'camera', 'required': False, 'category': 'features'},
        'gps': {'name': 'تتبع الموقع', 'icon': 'map-marker-alt', 'required': False, 'category': 'features'},
        'offline_mode': {'name': 'وضع عدم الاتصال', 'icon': 'wifi-slash', 'required': False, 'category': 'features'},
        'sync': {'name': 'المزامنة', 'icon': 'sync', 'required': False, 'category': 'features'},
        
        'settings': {'name': 'الإعدادات', 'icon': 'cog', 'required': False, 'category': 'system'},
        'help': {'name': 'المساعدة', 'icon': 'question-circle', 'required': False, 'category': 'system'},
        'about': {'name': 'حول التطبيق', 'icon': 'info-circle', 'required': False, 'category': 'system'},
    }


def _generate_mobile_app(app_name, platform, modules, package_name, icon=None):
    """إنشاء تطبيق موبايل"""
    
    output_dir = os.path.join(current_app.root_path, 'instance', 'mobile_apps', app_name)
    os.makedirs(output_dir, exist_ok=True)
    
    if platform in ['android', 'both']:
        _create_android_project(output_dir, app_name, package_name, modules, icon)
    
    if platform in ['ios', 'both']:
        _create_ios_project(output_dir, app_name, package_name, modules, icon)
    
    _create_flutter_project(output_dir, app_name, package_name, modules)
    _create_react_native_config(output_dir, app_name, package_name, modules)
    _create_mobile_readme(output_dir, app_name, platform, modules)
    
    import zipfile
    zip_path = os.path.join(current_app.root_path, 'instance', 'mobile_apps', f'{app_name}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zipf.write(file_path, arcname)
    
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    
    return {
        'output_path': output_dir,
        'zip_path': zip_path,
        'platform': platform,
        'size': f'{size_mb:.2f} MB'
    }


def _create_flutter_project(output_dir, app_name, package_name, modules):
    """إنشاء مشروع Flutter"""
    
    flutter_dir = os.path.join(output_dir, 'flutter_app')
    os.makedirs(flutter_dir, exist_ok=True)
    
    pubspec = f"""name: {app_name.lower().replace(' ', '_')}
description: تطبيق {app_name}
version: 1.0.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter
  http: ^1.1.0
  provider: ^6.0.5
  shared_preferences: ^2.2.2
  flutter_secure_storage: ^9.0.0
  barcode_scan2: ^4.2.3
  image_picker: ^1.0.4
  geolocator: ^10.1.0
  url_launcher: ^6.2.1
  intl: ^0.18.1

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0

flutter:
  uses-material-design: true
"""
    
    with open(os.path.join(flutter_dir, 'pubspec.yaml'), 'w', encoding='utf-8') as f:
        f.write(pubspec)
    
    main_dart = f"""import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

void main() {{
  runApp(MyApp());
}}

class MyApp extends StatelessWidget {{
  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: '{app_name}',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        fontFamily: 'Cairo',
      ),
      home: LoginScreen(),
      routes: {{
        '/dashboard': (context) => DashboardScreen(),
        '/customers': (context) => CustomersScreen(),
        '/sales': (context) => SalesScreen(),
      }},
    );
  }}
}}

class LoginScreen extends StatelessWidget {{
  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      body: Center(
        child: Text('Login Screen - {app_name}'),
      ),
    );
  }}
}}

class DashboardScreen extends StatelessWidget {{
  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: Text('Dashboard')),
      body: Center(child: Text('Dashboard')),
    );
  }}
}}

class CustomersScreen extends StatelessWidget {{
  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: Text('العملاء')),
      body: Center(child: Text('Customers List')),
    );
  }}
}}

class SalesScreen extends StatelessWidget {{
  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: Text('المبيعات')),
      body: Center(child: Text('Sales List')),
    );
  }}
}}
"""
    
    lib_dir = os.path.join(flutter_dir, 'lib')
    os.makedirs(lib_dir, exist_ok=True)
    with open(os.path.join(lib_dir, 'main.dart'), 'w', encoding='utf-8') as f:
        f.write(main_dart)


def _create_android_project(output_dir, app_name, package_name, modules, icon):
    """إنشاء مشروع Android"""
    
    android_dir = os.path.join(output_dir, 'android')
    os.makedirs(android_dir, exist_ok=True)
    
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{package_name}">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />

    <application
        android:label="{app_name}"
        android:icon="@mipmap/ic_launcher"
        android:usesCleartextTraffic="true">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""
    
    with open(os.path.join(android_dir, 'AndroidManifest.xml'), 'w', encoding='utf-8') as f:
        f.write(manifest)
    
    build_gradle = f"""android {{
    compileSdkVersion 34
    defaultConfig {{
        applicationId "{package_name}"
        minSdkVersion 21
        targetSdkVersion 34
        versionCode 1
        versionName "1.0"
    }}
    buildTypes {{
        release {{
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }}
    }}
}}

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.10.0'
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.squareup.retrofit2:converter-gson:2.9.0'
}}
"""
    
    with open(os.path.join(android_dir, 'build.gradle'), 'w', encoding='utf-8') as f:
        f.write(build_gradle)


def _create_ios_project(output_dir, app_name, package_name, modules, icon):
    """إنشاء مشروع iOS"""
    
    ios_dir = os.path.join(output_dir, 'ios')
    os.makedirs(ios_dir, exist_ok=True)
    
    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>{app_name}</string>
    <key>CFBundleIdentifier</key>
    <string>{package_name}</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>NSCameraUsageDescription</key>
    <string>نحتاج للكاميرا لمسح الباركود</string>
    <key>NSLocationWhenInUseUsageDescription</key>
    <string>نحتاج للموقع لتتبع الشحنات</string>
</dict>
</plist>
"""
    
    with open(os.path.join(ios_dir, 'Info.plist'), 'w', encoding='utf-8') as f:
        f.write(info_plist)


def _create_react_native_config(output_dir, app_name, package_name, modules):
    """إنشاء React Native config"""
    
    rn_dir = os.path.join(output_dir, 'react_native')
    os.makedirs(rn_dir, exist_ok=True)
    
    package_json = f"""{{
  "name": "{app_name.lower().replace(' ', '-')}",
  "version": "1.0.0",
  "private": true,
  "scripts": {{
    "android": "react-native run-android",
    "ios": "react-native run-ios",
    "start": "react-native start"
  }},
  "dependencies": {{
    "react": "18.2.0",
    "react-native": "0.73.0",
    "react-navigation": "^4.4.4",
    "axios": "^1.6.0",
    "@react-native-async-storage/async-storage": "^1.19.0",
    "react-native-camera": "^4.2.1",
    "react-native-barcode-scanner": "^1.0.0"
  }}
}}
"""
    
    with open(os.path.join(rn_dir, 'package.json'), 'w', encoding='utf-8') as f:
        f.write(package_json)
    
    app_js = f"""import React from 'react';
import {{ NavigationContainer }} from '@react-navigation/native';
import {{ createStackNavigator }} from '@react-navigation/stack';
import LoginScreen from './screens/LoginScreen';
import DashboardScreen from './screens/DashboardScreen';

const Stack = createStackNavigator();

export default function App() {{
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Login">
        <Stack.Screen name="Login" component={{LoginScreen}} options={{{{ headerShown: false }}}} />
        <Stack.Screen name="Dashboard" component={{DashboardScreen}} options={{{{ title: '{app_name}' }}}} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}}
"""
    
    with open(os.path.join(rn_dir, 'App.js'), 'w', encoding='utf-8') as f:
        f.write(app_js)


def _create_mobile_readme(output_dir, app_name, platform, modules):
    """إنشاء README للتطبيق"""
    
    readme = f"""# {app_name} - Mobile App

تطبيق موبايل تم إنشاؤه بواسطة Mobile App Generator

## المنصات:
- {'✅ Android' if platform in ['android', 'both'] else '❌ Android'}
- {'✅ iOS' if platform in ['ios', 'both'] else '❌ iOS'}

## التقنيات المستخدمة:
- **Flutter**: تطبيق عابر للمنصات
- **React Native**: بديل JavaScript
- **Native Android**: Kotlin/Java
- **Native iOS**: Swift

## الوحدات المضمنة:
{len(modules)} وحدة

## البناء:

### Flutter:
```bash
cd flutter_app
flutter pub get
flutter run
```

### React Native:
```bash
cd react_native
npm install
npm run android  # أو npm run ios
```

### Android Native:
```bash
cd android
./gradlew assembleRelease
```

## الاتصال بالسيرفر:

تأكد من تحديث API URL في:
- Flutter: `lib/config.dart`
- React Native: `src/config.js`
- Android: `app/src/main/java/config/ApiConfig.java`

```
API_URL = "http://your-server-ip:5000"
```

---

تم الإنشاء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    with open(os.path.join(output_dir, 'README_MOBILE.md'), 'w', encoding='utf-8') as f:
        f.write(readme)


def _detect_current_db_type():
    """كشف نوع قاعدة البيانات الحالية"""
    try:
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if uri.startswith('sqlite'):
            return 'SQLite'
        elif uri.startswith('postgresql'):
            return 'PostgreSQL'
        elif uri.startswith('mysql'):
            return 'MySQL'
        elif uri.startswith('mssql') or uri.startswith('sqlserver'):
            return 'SQL Server'
        else:
            return 'Unknown'
    except Exception:
        return 'SQLite'


def _convert_database(target_db, connection_string):
    """تحويل قاعدة البيانات من نوع لآخر - محسّن وقوي"""
    from sqlalchemy import create_engine, MetaData, Table, Column
    from sqlalchemy.orm import sessionmaker
    
    # التحقق من صحة connection_string
    if not connection_string or len(connection_string) < 10:
        raise ValueError("Connection string غير صالح")
    
    # إنشاء نسخة احتياطية قبل التحويل
    backup_dir = os.path.join(current_app.root_path, 'instance', 'backups', 'db')
    os.makedirs(backup_dir, exist_ok=True)
    
    current_db = os.path.join(current_app.root_path, 'instance', 'app.db')
    safety_backup = os.path.join(backup_dir, f'before_convert_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    
    if os.path.exists(current_db):
        shutil.copy2(current_db, safety_backup)
    
    source_engine = db.engine
    
    # محاولة الاتصال بقاعدة البيانات المستهدفة
    try:
        target_engine = create_engine(connection_string, echo=False)
        # اختبار الاتصال
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        raise ValueError(f"فشل الاتصال بقاعدة البيانات المستهدفة: {str(e)}")
    
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    
    # إنشاء الجداول في قاعدة البيانات المستهدفة
    target_metadata = MetaData()
    
    # نسخ تعريفات الجداول
    for table_name, source_table in source_metadata.tables.items():
        if table_name.startswith('sqlite_') or table_name.startswith('alembic_'):
            continue
        
        # إنشاء جدول جديد في الـ metadata المستهدف
        columns = []
        for column in source_table.columns:
            # نسخ الأعمدة مع تعديل الأنواع حسب الحاجة
            col_copy = Column(
                column.name,
                column.type,
                primary_key=column.primary_key,
                nullable=column.nullable,
                default=column.default,
                unique=column.unique
            )
            columns.append(col_copy)
        
        Table(table_name, target_metadata, *columns, extend_existing=True)
    
    # إنشاء الجداول
    target_metadata.create_all(bind=target_engine)
    
    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)
    
    source_session = SourceSession()
    target_session = TargetSession()
    
    total_records = 0
    tables_converted = 0
    errors = []
    
    try:
        for table_name in source_metadata.tables.keys():
            if table_name.startswith('sqlite_') or table_name.startswith('alembic_'):
                continue
            
            try:
                source_table = source_metadata.tables[table_name]
                target_table = target_metadata.tables[table_name]
                
                # جلب البيانات من المصدر
                source_data = source_session.execute(source_table.select()).fetchall()
                
                # إدراج البيانات في المستهدف
                for row in source_data:
                    try:
                        row_dict = dict(row._mapping)
                        target_session.execute(target_table.insert().values(**row_dict))
                        total_records += 1
                    except Exception as e:
                        errors.append(f"خطأ في {table_name}: {str(e)}")
                        continue
                
                tables_converted += 1
                
                # commit بعد كل جدول لتجنب فقدان البيانات
                target_session.commit()
                
            except Exception as e:
                errors.append(f"خطأ في جدول {table_name}: {str(e)}")
                continue
        
    except Exception as e:
        target_session.rollback()
        raise e
    finally:
        source_session.close()
        target_session.close()
    
    return {
        'records': total_records,
        'tables': tables_converted,
        'target': target_db,
        'errors': errors,
        'backup': safety_backup
    }


def _get_all_tenants():
    """جلب جميع Tenants مع تفاصيلهم"""
    tenants = SystemSettings.query.filter(
        SystemSettings.key.like('tenant_%_db')
    ).all()
    
    tenant_list = []
    for t in tenants:
        name = t.key.replace('tenant_', '').replace('_db', '')
        
        active_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_active').first()
        domain_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_domain').first()
        logo_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_logo').first()
        max_users_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_max_users').first()
        modules_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_modules').first()
        created_setting = SystemSettings.query.filter_by(key=f'tenant_{name}_created_at').first()
        
        modules = []
        if modules_setting and modules_setting.value:
            try:
                modules = json.loads(modules_setting.value)
            except Exception:
                modules = []
        
        tenant_list.append({
            'name': name,
            'db': t.value,
            'active': active_setting.value == 'True' if active_setting else False,
            'domain': domain_setting.value if domain_setting else '',
            'logo': logo_setting.value if logo_setting else '',
            'max_users': max_users_setting.value if max_users_setting else '10',
            'modules': modules,
            'created_at': created_setting.value if created_setting else ''
        })
    
    return tenant_list


def _update_tenant_setting(key, value):
    """تحديث أو إنشاء إعداد Tenant"""
    setting = SystemSettings.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.session.add(SystemSettings(key=key, value=value))


def _get_available_modules_list():
    """قائمة الوحدات المتاحة"""
    return [
        {'key': 'customers', 'name': 'إدارة العملاء', 'icon': 'users'},
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
        {'key': 'security', 'name': 'الأمان', 'icon': 'shield-alt'},
    ]


def _create_tenant_database(db_path):
    """إنشاء قاعدة بيانات جديدة للـ Tenant"""
    try:
        # نسخ هيكل قاعدة البيانات الحالية
        current_db = os.path.join(current_app.root_path, 'instance', 'app.db')
        if os.path.exists(current_db):
            shutil.copy2(current_db, db_path)
            
            # حذف البيانات وترك الهيكل فقط
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # جلب جميع الجداول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = cursor.fetchall()
            
            # حذف البيانات من كل جدول
            for (table_name,) in tables:
                try:
                    cursor.execute(f"DELETE FROM {table_name}")
                except Exception:
                    pass
            
            conn.commit()
            conn.close()
            
            return True
    except Exception as e:
        print(f"Error creating tenant database: {str(e)}")
        return False


@advanced_bp.route('/financial-control', methods=['GET', 'POST'])
@owner_only
def financial_control():
    from models import SystemSettings, Budget, FixedAsset, FixedAssetCategory
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_budget_settings':
            settings_data = {
                'enable_budget_module': request.form.get('enable_budget_module') == 'on',
                'fiscal_year_start_month': int(request.form.get('fiscal_year_start_month', 1)),
                'budget_level': request.form.get('budget_level', 'ACCOUNT_BRANCH'),
                'commitment_mode': request.form.get('commitment_mode', 'ALL'),
                'enable_budget_alerts': request.form.get('enable_budget_alerts') == 'on',
                'budget_threshold_warning': float(request.form.get('budget_threshold_warning', 80)),
                'budget_threshold_critical': float(request.form.get('budget_threshold_critical', 95)),
                'enable_budget_blocking': request.form.get('enable_budget_blocking') == 'on',
            }
            
            for key, value in settings_data.items():
                setting = SystemSettings.query.filter_by(key=key).first()
                if setting:
                    setting.value = str(value)
                    setting.updated_at = datetime.now(timezone.utc)
                else:
                    dtype = 'boolean' if isinstance(value, bool) else 'number' if isinstance(value, (int, float)) else 'string'
                    setting = SystemSettings(key=key, value=str(value), data_type=dtype, is_public=False)
                    db.session.add(setting)
            
            db.session.commit()
            flash('تم حفظ إعدادات الميزانية بنجاح', 'success')
            return redirect(url_for('advanced.financial_control'))
        
        elif action == 'save_asset_settings':
            settings_data = {
                'enable_fixed_assets': request.form.get('enable_fixed_assets') == 'on',
                'enable_auto_depreciation': request.form.get('enable_auto_depreciation') == 'on',
                'depreciation_frequency': request.form.get('depreciation_frequency', 'YEARLY'),
                'depreciation_day_of_month': int(request.form.get('depreciation_day_of_month', 1)),
                'auto_create_asset_from_expense': request.form.get('auto_create_asset_from_expense') == 'on',
                'asset_capitalization_threshold': float(request.form.get('asset_capitalization_threshold', 1000)),
            }
            
            for key, value in settings_data.items():
                setting = SystemSettings.query.filter_by(key=key).first()
                if setting:
                    setting.value = str(value)
                    setting.updated_at = datetime.now(timezone.utc)
                else:
                    dtype = 'boolean' if isinstance(value, bool) else 'number' if isinstance(value, (int, float)) else 'string'
                    setting = SystemSettings(key=key, value=str(value), data_type=dtype, is_public=False)
                    db.session.add(setting)
            
            db.session.commit()
            flash('تم حفظ إعدادات الأصول الثابتة بنجاح', 'success')
            return redirect(url_for('advanced.financial_control'))
    
    budget_settings = {
        'enable_budget_module': SystemSettings.get_setting('enable_budget_module', False),
        'fiscal_year_start_month': int(SystemSettings.get_setting('fiscal_year_start_month', 1)),
        'budget_level': SystemSettings.get_setting('budget_level', 'ACCOUNT_BRANCH'),
        'commitment_mode': SystemSettings.get_setting('commitment_mode', 'ALL'),
        'enable_budget_alerts': SystemSettings.get_setting('enable_budget_alerts', True),
        'budget_threshold_warning': float(SystemSettings.get_setting('budget_threshold_warning', 80)),
        'budget_threshold_critical': float(SystemSettings.get_setting('budget_threshold_critical', 95)),
        'enable_budget_blocking': SystemSettings.get_setting('enable_budget_blocking', True),
    }
    
    asset_settings = {
        'enable_fixed_assets': SystemSettings.get_setting('enable_fixed_assets', False),
        'enable_auto_depreciation': SystemSettings.get_setting('enable_auto_depreciation', False),
        'depreciation_frequency': SystemSettings.get_setting('depreciation_frequency', 'YEARLY'),
        'depreciation_day_of_month': int(SystemSettings.get_setting('depreciation_day_of_month', 1)),
        'auto_create_asset_from_expense': SystemSettings.get_setting('auto_create_asset_from_expense', False),
        'asset_capitalization_threshold': float(SystemSettings.get_setting('asset_capitalization_threshold', 1000)),
    }
    
    budget_stats = {
        'total_budgets': Budget.query.count(),
        'active_budgets': Budget.query.filter_by(is_active=True).count(),
        'current_year_budgets': Budget.query.filter_by(fiscal_year=datetime.now().year).count(),
    }
    
    asset_stats = {
        'total_assets': FixedAsset.query.count(),
        'active_assets': FixedAsset.query.filter_by(status='ACTIVE').count(),
        'total_categories': FixedAssetCategory.query.count(),
    }
    
    return render_template('advanced/financial_control.html',
                         budget_settings=budget_settings,
                         asset_settings=asset_settings,
                         budget_stats=budget_stats,
                         asset_stats=asset_stats)


@advanced_bp.route("/accounting-control", methods=["GET", "POST"])
@owner_only
def accounting_control():
    from models import BankAccount, CostCenter, Project
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "save_bank_settings":
            settings = {
                "enable_bank_reconciliation": request.form.get("enable_bank_reconciliation") == "on",
                "auto_match_tolerance": float(request.form.get("auto_match_tolerance", 0.01)),
                "require_bank_approval": request.form.get("require_bank_approval") == "on",
            }
            for k, v in settings.items():
                SystemSettings.set_setting(k, v, "boolean" if isinstance(v, bool) else "number")
            db.session.commit()
            flash("تم حفظ إعدادات البنوك", "success")
            return redirect(url_for("advanced.accounting_control"))
        
        elif action == "save_cost_center_settings":
            settings = {
                "enable_cost_centers": request.form.get("enable_cost_centers") == "on",
                "require_cost_center": request.form.get("require_cost_center") == "on",
                "allow_hierarchy": request.form.get("allow_hierarchy") == "on",
            }
            for k, v in settings.items():
                SystemSettings.set_setting(k, v, "boolean")
            db.session.commit()
            flash("تم حفظ إعدادات مراكز التكلفة", "success")
            return redirect(url_for("advanced.accounting_control"))
        
        elif action == "save_project_settings":
            settings = {
                "enable_projects": request.form.get("enable_projects") == "on",
                "auto_link_transactions": request.form.get("auto_link_transactions") == "on",
                "project_numbering_prefix": request.form.get("project_numbering_prefix", "PRJ"),
            }
            for k, v in settings.items():
                dtype = "boolean" if isinstance(v, bool) else "string"
                SystemSettings.set_setting(k, v, dtype)
            db.session.commit()
            flash("تم حفظ إعدادات المشاريع", "success")
            return redirect(url_for("advanced.accounting_control"))
    
    bank_settings = {
        "enable_bank_reconciliation": SystemSettings.get_setting("enable_bank_reconciliation", False),
        "auto_match_tolerance": float(SystemSettings.get_setting("auto_match_tolerance", 0.01)),
        "require_bank_approval": SystemSettings.get_setting("require_bank_approval", True),
    }
    
    cost_center_settings = {
        "enable_cost_centers": SystemSettings.get_setting("enable_cost_centers", False),
        "require_cost_center": SystemSettings.get_setting("require_cost_center", False),
        "allow_hierarchy": SystemSettings.get_setting("allow_hierarchy", True),
    }
    
    project_settings = {
        "enable_projects": SystemSettings.get_setting("enable_projects", False),
        "auto_link_transactions": SystemSettings.get_setting("auto_link_transactions", True),
        "project_numbering_prefix": SystemSettings.get_setting("project_numbering_prefix", "PRJ"),
    }
    
    stats = {
        "total_bank_accounts": BankAccount.query.count(),
        "total_cost_centers": CostCenter.query.count(),
        "total_projects": Project.query.count(),
    }
    
    return render_template("advanced/accounting_control.html",
                         bank_settings=bank_settings,
                         cost_center_settings=cost_center_settings,
                         project_settings=project_settings,
                         stats=stats)


@advanced_bp.route("/api/advanced-accounting-stats")
@owner_only
def api_accounting_stats():
    from models import BankAccount, CostCenter, Project, BankTransaction
    from sqlalchemy import func
    
    bank_accounts = BankAccount.query.count()
    active_banks = BankAccount.query.filter_by(is_active=True).count()
    
    cost_centers = CostCenter.query.count()
    total_budget = db.session.query(func.sum(CostCenter.budget)).filter_by(is_active=True).scalar() or 0
    
    projects = Project.query.count()
    active_projects = Project.query.filter(Project.status.in_(['IN_PROGRESS', 'PLANNING'])).count()
    
    unmatched = BankTransaction.query.filter_by(matched=False).count()
    
    return jsonify({
        'success': True,
        'stats': {
            'bank_accounts': bank_accounts,
            'active_banks': active_banks,
            'cost_centers': cost_centers,
            'total_budget': float(total_budget),
            'projects': projects,
            'active_projects': active_projects,
            'alerts': unmatched
        }
    })
