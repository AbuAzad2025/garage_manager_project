"""
👑 AI Admin Routes - مسارات تحكم المالك بالمساعد
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- إدارة صلاحيات المساعد
- إخفاء/إظهار للمستخدمين
- تحكم كامل من المالك

Created: 2025-11-01
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from models import SystemSettings
from extensions import db
import os
from pathlib import Path
from werkzeug.utils import secure_filename


# Blueprint
ai_admin_bp = Blueprint('ai_admin', __name__, url_prefix='/ai-admin')


# ═══════════════════════════════════════════════════════════════════════════
# 🔒 OWNER ONLY DECORATOR
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# 📋 ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@ai_admin_bp.route('/settings', methods=['GET', 'POST'])
@owner_only
def ai_settings():
    """
    إعدادات المساعد الذكي (للمالك فقط)
    
    يتحكم في:
    - تفعيل/تعطيل المساعد
    - من يرى المساعد (مدراء، موظفين، الكل)
    - صلاحيات التنفيذ
    """
    if request.method == 'POST':
        try:
            # حفظ الإعدادات
            settings = {
                'ai_enabled': request.form.get('ai_enabled') == 'on',
                'ai_visible_to_managers': request.form.get('ai_visible_to_managers') == 'on',
                'ai_visible_to_staff': request.form.get('ai_visible_to_staff') == 'on',
                'ai_visible_to_customers': request.form.get('ai_visible_to_customers') == 'on',
                'ai_can_execute_actions': request.form.get('ai_can_execute_actions') == 'on',
                'ai_realtime_alerts_enabled': request.form.get('ai_realtime_alerts_enabled') == 'on',
                'ai_auto_learning_enabled': request.form.get('ai_auto_learning_enabled') == 'on'
            }
            
            for key, value in settings.items():
                SystemSettings.set_setting(
                    key=key,
                    value=str(value),
                    dtype='boolean',
                    is_public=False
                )
            
            db.session.commit()
            
            flash('✅ تم حفظ إعدادات المساعد الذكي', 'success')
            return redirect(url_for('ai_admin.ai_settings'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}', 'danger')
    
    # GET - عرض الإعدادات الحالية
    current_settings = {
        'ai_enabled': SystemSettings.get_setting('ai_enabled', 'true').lower() == 'true',
        'ai_visible_to_managers': SystemSettings.get_setting('ai_visible_to_managers', 'true').lower() == 'true',
        'ai_visible_to_staff': SystemSettings.get_setting('ai_visible_to_staff', 'false').lower() == 'true',
        'ai_visible_to_customers': SystemSettings.get_setting('ai_visible_to_customers', 'false').lower() == 'true',
        'ai_can_execute_actions': SystemSettings.get_setting('ai_can_execute_actions', 'true').lower() == 'true',
        'ai_realtime_alerts_enabled': SystemSettings.get_setting('ai_realtime_alerts_enabled', 'true').lower() == 'true',
        'ai_auto_learning_enabled': SystemSettings.get_setting('ai_auto_learning_enabled', 'true').lower() == 'true'
    }
    
    return render_template(
        'ai/ai_admin_settings.html',
        settings=current_settings
    )


@ai_admin_bp.route('/toggle-visibility', methods=['POST'])
@owner_only
def toggle_visibility():
    """
    تبديل إظهار/إخفاء المساعد (API)
    
    Body:
        {
            'visible': true/false
        }
    """
    try:
        data = request.get_json()
        visible = data.get('visible', True)
        
        SystemSettings.set_setting('ai_enabled', str(visible), dtype='boolean')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم التحديث',
            'ai_enabled': visible
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/reset-knowledge', methods=['POST'])
@owner_only
def reset_knowledge():
    """
    إعادة بناء قاعدة المعرفة بالكامل - تدريب حقيقي
    
    يقوم بـ:
    1. فحص شامل لقاعدة البيانات (كل الجداول والحقول)
    2. فحص كل الموديلات
    3. فحص كل Routes
    4. فحص كل Forms
    5. فحص كل Templates
    6. تحليل العلاقات
    7. فحص Enums
    8. حفظ المعرفة في JSON
    """
    try:
        from AI.engine.ai_training_engine import get_training_engine
        import threading
        
        engine = get_training_engine()
        
        # فحص إذا كان التدريب يعمل
        status = engine.get_status()
        if status.get('running'):
            return jsonify({
                'success': False,
                'error': 'Training already in progress',
                'status': status
            }), 400
        
        # تشغيل التدريب في thread منفصل
        def run_training():
            engine.run_full_training(force=True)
        
        training_thread = threading.Thread(target=run_training, daemon=True)
        training_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'تم بدء التدريب - جارٍ المعالجة...',
            'status': engine.get_status()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/training-status', methods=['GET'])
@owner_only
def training_status():
    """الحصول على حالة التدريب"""
    try:
        from AI.engine.ai_training_engine import get_training_engine
        
        engine = get_training_engine()
        status = engine.get_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/training-log', methods=['GET'])
@owner_only
def training_log():
    """الحصول على سجل التدريب"""
    try:
        from AI.engine.ai_training_engine import get_training_engine
        
        engine = get_training_engine()
        limit = request.args.get('limit', 50, type=int)
        log = engine.get_training_log(limit=limit)
        
        return jsonify({
            'success': True,
            'log': log
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/daily-reports', methods=['GET'])
@owner_only
def daily_reports():
    """عرض التقارير اليومية"""
    try:
        from pathlib import Path
        import os
        
        reports_dir = 'AI/data/daily_reports'
        
        if not os.path.exists(reports_dir):
            flash('⚠️ لا توجد تقارير يومية بعد', 'info')
            return render_template('ai/daily_reports.html', daily_reports=[])
        
        # قراءة التقارير
        reports = []
        for report_file in sorted(Path(reports_dir).glob('report_*.json'), reverse=True):
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                    reports.append(report_data)
            except Exception:
                pass
        
        return render_template('ai/daily_reports.html', daily_reports=reports[:30])  # آخر 30 تقرير
    
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('ai_admin.ai_settings'))


@ai_admin_bp.route('/evolution-report', methods=['GET'])
@owner_only
def evolution_report():
    """تقرير التطور الذاتي"""
    try:
        from AI.engine.ai_self_evolution import get_evolution_engine
        
        engine = get_evolution_engine()
        report = engine.get_evolution_report()
        suggestions = engine.suggest_improvements()
        
        return render_template(
            'ai/evolution_report.html',
            report=report,
            suggestions=suggestions
        )
    
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('ai_admin.ai_settings'))


@ai_admin_bp.route('/run-code-scan', methods=['POST'])
@owner_only
def run_code_scan():
    try:
        from AI.engine.ai_code_quality_monitor import get_code_monitor
        import threading
        
        def run_scan():
            monitor = get_code_monitor()
            monitor.run_daily_scan()
        
        scan_thread = threading.Thread(target=run_scan, daemon=True)
        scan_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'تم بدء الفحص'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/performance', methods=['GET'])
@owner_only
def performance_report():
    try:
        from AI.engine.ai_performance_tracker import get_performance_tracker
        from AI.engine.ai_self_evolution import get_evolution_engine
        from AI.engine.ai_learning_system import get_learning_system
        
        tracker = get_performance_tracker()
        evolution = get_evolution_engine()
        learning = get_learning_system()
        
        perf_report = tracker.get_performance_report()
        evo_report = evolution.get_evolution_report()
        learning_stats = learning.get_learning_stats()
        
        return render_template(
            'ai/performance_report.html',
            performance=perf_report,
            evolution=evo_report,
            learning=learning_stats
        )
    
    except Exception as e:
        flash(f'خطأ: {str(e)}', 'danger')
        return redirect(url_for('ai_admin.ai_settings'))


@ai_admin_bp.route('/stats-api', methods=['GET'])
@owner_only
def stats_api():
    try:
        from AI.engine.ai_performance_tracker import get_performance_tracker
        from AI.engine.ai_self_evolution import get_evolution_engine
        from AI.engine.ai_learning_system import get_learning_system
        
        tracker = get_performance_tracker()
        evolution = get_evolution_engine()
        learning = get_learning_system()
        
        return jsonify({
            'success': True,
            'performance': tracker.get_performance_report(),
            'evolution': evolution.get_evolution_report(),
            'learning': learning.get_learning_stats()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/advanced-training', methods=['GET'])
@owner_only
def advanced_training():
    """صفحة التدريب المتقدم"""
    return render_template('ai/advanced_training.html')


@ai_admin_bp.route('/command/<command_name>', methods=['POST'])
@owner_only
def execute_command(command_name):
    """تنفيذ أوامر النظام"""
    try:
        from AI.engine.ai_master_controller import get_master_controller
        
        controller = get_master_controller()
        
        params = request.get_json() or {}
        
        result = controller.execute_system_command(command_name, params)
        
        return jsonify({
            'success': result.get('success', True),
            'result': result,
            'error': result.get('error')
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/upload_book', methods=['POST'])
@owner_only
def upload_book():
    """رفع وقراءة كتاب"""
    try:
        if 'book_file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['book_file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        filename = secure_filename(file.filename)
        books_dir = Path('AI/data/books')
        books_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = books_dir / filename
        file.save(file_path)
        
        file_format = 'pdf' if filename.lower().endswith('.pdf') else 'markdown'
        
        from AI.engine.ai_master_controller import get_master_controller
        
        controller = get_master_controller()
        result = controller.execute_system_command('read_book', {
            'file_path': str(file_path),
            'format': file_format
        })
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'title': result.get('title'),
                'chapters': result.get('chapters'),
                'pages': result.get('pages'),
                'key_concepts': result.get('key_concepts'),
                'key_terms': result.get('key_terms')
            })
        else:
            return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/memory_stats', methods=['GET'])
@owner_only
def memory_stats():
    """إحصائيات الذاكرة"""
    try:
        from AI.engine.ai_deep_memory import get_deep_memory
        
        memory = get_deep_memory()
        stats = memory.get_memory_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/system_status', methods=['GET'])
@owner_only
def system_status():
    """حالة النظام"""
    try:
        from AI.engine.ai_master_controller import get_master_controller
        
        controller = get_master_controller()
        status = controller.get_system_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/train-package', methods=['POST'])
@owner_only
def train_package():
    """تدريب باقة متخصصة"""
    try:
        data = request.get_json()
        package_id = data.get('package_id')
        
        from AI.engine.ai_specialized_training import get_specialized_training
        
        trainer = get_specialized_training()
        result = trainer.train_package(package_id)
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'package_name': trainer.training_packages.get(package_id, {}).get('name'),
                'items_learned': result.get('items_learned', 0)
            })
        else:
            return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/train-all-packages', methods=['POST'])
@owner_only
def train_all_packages():
    """تدريب جميع الباقات"""
    try:
        from AI.engine.ai_specialized_training import get_specialized_training
        
        trainer = get_specialized_training()
        result = trainer.train_all_packages()
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_admin_bp.route('/marathon-training', methods=['POST'])
@owner_only
def marathon_training():
    """تدريب ماراثوني شامل"""
    try:
        import threading
        
        def run_marathon():
            from AI.engine.ai_intensive_trainer import get_intensive_trainer
            from AI.engine.ai_specialized_training import get_specialized_training
            from AI.engine.ai_marathon_trainer import get_marathon_trainer
            from AI.engine.ai_heavy_equipment_expert import get_heavy_equipment_expert
            from AI.engine.ai_system_deep_trainer import get_system_deep_trainer
            
            intensive = get_intensive_trainer()
            intensive.start_intensive_training()
            
            specialized = get_specialized_training()
            specialized.train_all_packages()
            
            marathon = get_marathon_trainer()
            marathon.start_marathon_training()
            
            he_expert = get_heavy_equipment_expert()
            he_expert.train_comprehensive()
            
            sys_trainer = get_system_deep_trainer()
            sys_trainer.train_system_comprehensive()
        
        marathon_thread = threading.Thread(target=run_marathon, daemon=True)
        marathon_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Marathon training started in background'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


__all__ = ['ai_admin_bp']

