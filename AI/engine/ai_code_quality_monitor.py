"""
🔍 AI Code Quality Monitor - مراقب جودة الكود والأخطاء
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- فحص الكود البرمجي
- اكتشاف الأخطاء المحتملة
- اكتشاف الـ code smells
- اكتشاف الثغرات الأمنية
- إنشاء تقارير يومية
- اقتراح تحسينات

Created: 2025-11-01
Version: Code Monitor 1.0 - GENIUS LEVEL
"""

import os
import re
import ast
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from sqlalchemy import inspect, text
from extensions import db


# ═══════════════════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

DAILY_REPORTS_DIR = 'AI/data/daily_reports'
CODE_ISSUES_LOG = 'AI/data/code_issues.json'
QUALITY_METRICS = 'AI/data/quality_metrics.json'


# ═══════════════════════════════════════════════════════════════════════════
# 🔍 CODE QUALITY MONITOR
# ═══════════════════════════════════════════════════════════════════════════

class CodeQualityMonitor:
    """
    مراقب جودة الكود - عبقري
    
    القدرات:
    1. فحص Python code
    2. اكتشاف SQL injection
    3. اكتشاف XSS vulnerabilities
    4. اكتشاف code smells
    5. فحص database integrity
    6. إنشاء تقارير يومية تلقائية
    """
    
    def __init__(self):
        self.base_path = Path('.')
        self.issues = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': [],
            'info': []
        }
        self.quality_score = 100.0
        self.scan_timestamp = None
    
    def run_daily_scan(self) -> Dict[str, Any]:
        """
        فحص يومي شامل
        
        Returns:
            تقرير كامل بكل الأخطاء والتحسينات
        """
        print("[SCAN] Starting daily code quality scan...")
        self.scan_timestamp = datetime.now()
        
        # 1. فحص Python files
        print("[SCAN] Scanning Python files...")
        self._scan_python_files()
        
        # 2. فحص SQL queries
        print("[SCAN] Scanning SQL queries...")
        self._scan_sql_queries()
        
        # 3. فحص database integrity
        print("[SCAN] Checking database integrity...")
        self._check_database_integrity()
        
        # 4. فحص security vulnerabilities
        print("[SCAN] Checking security...")
        self._check_security_issues()
        
        # 5. فحص performance issues
        print("[SCAN] Checking performance...")
        self._check_performance_issues()
        
        # 6. حساب نقاط الجودة
        self._calculate_quality_score()
        
        # 7. إنشاء التقرير
        report = self._generate_daily_report()
        
        # 8. حفظ التقرير
        self._save_daily_report(report)
        
        # 9. حفظ المشاكل
        self._save_issues()
        
        print(f"[OK] Scan completed - Quality Score: {self.quality_score}/100")
        print(f"[OK] Issues: {len(self.issues['critical'])} critical, "
              f"{len(self.issues['high'])} high, "
              f"{len(self.issues['medium'])} medium")
        
        return report
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🐍 PYTHON CODE SCANNING
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_python_files(self):
        """فحص ملفات Python"""
        for py_file in self.base_path.rglob('*.py'):
            # تجاهل venv و migrations
            if 'venv' in str(py_file) or 'migrations' in str(py_file):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # فحص أنماط خطرة
                self._check_dangerous_patterns(py_file, content)
                
                # فحص code smells
                self._check_code_smells(py_file, content)
                
                # فحص syntax errors
                self._check_syntax_errors(py_file, content)
                
                # فحص imports
                self._check_imports(py_file, content)
            
            except Exception as e:
                self._add_issue('low', f"Could not scan {py_file}: {e}", str(py_file))
    
    def _check_dangerous_patterns(self, file_path: Path, content: str):
        """فحص أنماط خطرة"""
        dangerous_patterns = [
            # SQL Injection
            (r'execute\(["\'].*%s.*["\']\s*%', 'SQL Injection risk - use parameterized queries'),
            (r'execute\(["\'].*\+.*["\']\)', 'SQL Injection risk - string concatenation'),
            (r'raw_sql\s*=.*\+', 'SQL Injection risk in raw SQL'),
            
            # Command Injection
            (r'os\.system\(.*\+', 'Command injection risk'),
            (r'subprocess\.call\(.*\+', 'Command injection risk'),
            
            # XSS
            (r'render_template_string\(.*\+', 'XSS risk - avoid string concatenation in templates'),
            (r'Markup\(.*\+', 'XSS risk'),
            
            # Hardcoded secrets
            (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password detected'),
            (r'api_key\s*=\s*["\'][^"\']+["\']', 'Hardcoded API key detected'),
            (r'secret\s*=\s*["\'][^"\']+["\']', 'Hardcoded secret detected'),
            
            # Eval usage
            (r'\beval\s*\(', 'Dangerous use of eval()'),
            (r'\bexec\s*\(', 'Dangerous use of exec()'),
            
            # Pickle
            (r'pickle\.loads?\(', 'Pickle usage - security risk'),
        ]
        
        for pattern, message in dangerous_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                
                self._add_issue(
                    'critical',
                    f"{message}",
                    f"{file_path}:{line_num}",
                    {
                        'pattern': pattern,
                        'matched_text': match.group()[:100]
                    }
                )
    
    def _check_code_smells(self, file_path: Path, content: str):
        """فحص code smells"""
        lines = content.split('\n')
        
        # 1. Long functions (> 50 lines)
        function_pattern = r'^def\s+(\w+)\s*\('
        
        current_function = None
        function_start = 0
        
        for i, line in enumerate(lines):
            match = re.match(function_pattern, line)
            
            if match:
                # حفظ الدالة السابقة
                if current_function and (i - function_start) > 50:
                    self._add_issue(
                        'medium',
                        f"Function '{current_function}' is too long ({i - function_start} lines)",
                        f"{file_path}:{function_start}"
                    )
                
                current_function = match.group(1)
                function_start = i + 1
        
        # 2. TODO/FIXME comments
        for i, line in enumerate(lines):
            if 'TODO' in line or 'FIXME' in line:
                self._add_issue(
                    'low',
                    f"Unresolved TODO/FIXME comment",
                    f"{file_path}:{i+1}",
                    {'line': line.strip()}
                )
        
        # 3. Print statements (should use logging)
        for i, line in enumerate(lines):
            if re.search(r'\bprint\s*\(', line) and 'logger' not in content[:content.find(line)]:
                self._add_issue(
                    'low',
                    "Using print() instead of logging",
                    f"{file_path}:{i+1}"
                )
        
        # 4. Bare except
        for i, line in enumerate(lines):
            if re.match(r'\s*except\s*:', line):
                self._add_issue(
                    'medium',
                    "Bare except clause - should specify exception type",
                    f"{file_path}:{i+1}"
                )
    
    def _check_syntax_errors(self, file_path: Path, content: str):
        """فحص syntax errors"""
        try:
            ast.parse(content)
        except SyntaxError as e:
            self._add_issue(
                'critical',
                f"Syntax error: {e.msg}",
                f"{file_path}:{e.lineno}"
            )
    
    def _check_imports(self, file_path: Path, content: str):
        """فحص الـ imports"""
        # Unused imports (تحليل بسيط)
        import_pattern = r'^import\s+(\w+)|^from\s+(\w+)\s+import'
        
        imports = []
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1) or match.group(2)
            imports.append(module)
        
        # فحص إذا كان الـ import مستخدم
        for module in imports:
            if content.count(module) == 1:  # مذكور مرة واحدة فقط (في الـ import نفسه)
                self._add_issue(
                    'low',
                    f"Possibly unused import: {module}",
                    str(file_path)
                )
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🗄️ SQL QUERIES SCANNING
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_sql_queries(self):
        """فحص استعلامات SQL"""
        # فحص ملفات Python للبحث عن queries
        for py_file in self.base_path.rglob('*.py'):
            if 'venv' in str(py_file) or 'migrations' in str(py_file):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # البحث عن db.session.execute
                execute_pattern = r'db\.session\.execute\s*\(["\'](.+?)["\']\s*(?:,|\))'
                
                for match in re.finditer(execute_pattern, content, re.DOTALL):
                    query = match.group(1)
                    line_num = content[:match.start()].count('\n') + 1
                    
                    # فحص إذا كان Query خطر
                    if '%' in query or '+' in query:
                        self._add_issue(
                            'high',
                            "SQL query uses string formatting - SQL injection risk",
                            f"{py_file}:{line_num}",
                            {'query': query[:200]}
                        )
            
            except Exception as e:
                pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🗄️ DATABASE INTEGRITY
    # ═══════════════════════════════════════════════════════════════════════
    
    def _check_database_integrity(self):
        """فحص سلامة قاعدة البيانات"""
        try:
            inspector = inspect(db.engine)
            
            # 1. فحص الجداول الفارغة
            for table_name in inspector.get_table_names():
                try:
                    result = db.session.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    ).scalar()
                    
                    # إذا كان جدول مهم وفارغ
                    important_tables = ['users', 'system_settings', 'roles']
                    
                    if table_name in important_tables and result == 0:
                        self._add_issue(
                            'high',
                            f"Important table '{table_name}' is empty",
                            'database'
                        )
                
                except Exception as e:
                    pass
            
            # 2. فحص Foreign Keys
            for table_name in inspector.get_table_names():
                fks = inspector.get_foreign_keys(table_name)
                
                for fk in fks:
                    # التحقق من وجود orphaned records
                    self._check_orphaned_records(table_name, fk)
        
        except Exception as e:
            self._add_issue(
                'medium',
                f"Could not check database integrity: {e}",
                'database'
            )
    
    def _check_orphaned_records(self, table_name: str, fk: Dict):
        """فحص سجلات يتيمة (orphaned records)"""
        try:
            constrained_cols = fk.get('constrained_columns', [])
            referred_table = fk.get('referred_table')
            referred_cols = fk.get('referred_columns', [])
            
            if not constrained_cols or not referred_table or not referred_cols:
                return
            
            # Query للبحث عن orphaned records
            query = f"""
                SELECT COUNT(*)
                FROM {table_name} t
                WHERE t.{constrained_cols[0]} IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM {referred_table} r
                    WHERE r.{referred_cols[0]} = t.{constrained_cols[0]}
                )
            """
            
            count = db.session.execute(text(query)).scalar()
            
            if count > 0:
                self._add_issue(
                    'medium',
                    f"Found {count} orphaned records in '{table_name}' "
                    f"(FK to '{referred_table}')",
                    'database'
                )
        
        except Exception as e:
            pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔒 SECURITY CHECKS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _check_security_issues(self):
        """فحص المشاكل الأمنية"""
        # 1. فحص CSRF protection في forms
        for py_file in self.base_path.rglob('forms.py'):
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # البحث عن forms بدون CSRF
                if 'class Meta' not in content or 'csrf = False' in content:
                    self._add_issue(
                        'high',
                        "Form might be missing CSRF protection",
                        str(py_file)
                    )
            except Exception:
                pass
        
        # 2. فحص session security
        app_file = self.base_path / 'app.py'
        if app_file.exists():
            try:
                content = app_file.read_text(encoding='utf-8')
                
                if 'SESSION_COOKIE_SECURE' not in content:
                    self._add_issue(
                        'medium',
                        "SESSION_COOKIE_SECURE not configured",
                        'app.py'
                    )
                
                if 'SESSION_COOKIE_HTTPONLY' not in content:
                    self._add_issue(
                        'medium',
                        "SESSION_COOKIE_HTTPONLY not configured",
                        'app.py'
                    )
            except Exception:
                pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # ⚡ PERFORMANCE CHECKS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _check_performance_issues(self):
        """فحص مشاكل الأداء"""
        # 1. N+1 queries pattern
        for py_file in self.base_path.rglob('*.py'):
            if 'venv' in str(py_file):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # البحث عن for loop مع query
                pattern = r'for\s+\w+\s+in\s+.*:\s*\n.*\.query\.'
                
                matches = list(re.finditer(pattern, content, re.MULTILINE))
                
                for match in matches:
                    line_num = content[:match.start()].count('\n') + 1
                    
                    self._add_issue(
                        'medium',
                        "Possible N+1 query pattern detected",
                        f"{py_file}:{line_num}"
                    )
            except Exception:
                pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📊 QUALITY SCORE
    # ═══════════════════════════════════════════════════════════════════════
    
    def _calculate_quality_score(self):
        """حساب نقاط الجودة"""
        score = 100.0
        
        # خصم حسب شدة المشاكل
        score -= len(self.issues['critical']) * 10
        score -= len(self.issues['high']) * 5
        score -= len(self.issues['medium']) * 2
        score -= len(self.issues['low']) * 0.5
        
        self.quality_score = max(0.0, score)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📋 REPORTING
    # ═══════════════════════════════════════════════════════════════════════
    
    def _generate_daily_report(self) -> Dict[str, Any]:
        """إنشاء التقرير اليومي"""
        total_issues = sum(len(issues) for issues in self.issues.values())
        
        report = {
            'date': self.scan_timestamp.strftime('%Y-%m-%d'),
            'timestamp': self.scan_timestamp.isoformat(),
            'quality_score': round(self.quality_score, 2),
            'total_issues': total_issues,
            'issues_by_severity': {
                severity: len(issues)
                for severity, issues in self.issues.items()
            },
            'issues': self.issues,
            'summary': self._generate_summary(),
            'recommendations': self._generate_recommendations()
        }
        
        return report
    
    def _generate_summary(self) -> str:
        """إنشاء ملخص"""
        total = sum(len(issues) for issues in self.issues.values())
        
        if self.quality_score >= 90:
            grade = "🏆 ممتاز"
        elif self.quality_score >= 80:
            grade = "🟢 جيد جداً"
        elif self.quality_score >= 70:
            grade = "🟡 جيد"
        elif self.quality_score >= 60:
            grade = "🟠 مقبول"
        else:
            grade = "🔴 يحتاج تحسين"
        
        summary = f"""
📊 تقرير فحص الكود اليومي - {self.scan_timestamp.strftime('%Y-%m-%d')}

📈 النتيجة: {self.quality_score:.1f}/100 - {grade}

🔍 المشاكل المكتشفة:
  - 🔴 حرجة: {len(self.issues['critical'])}
  - 🟠 عالية: {len(self.issues['high'])}
  - 🟡 متوسطة: {len(self.issues['medium'])}
  - 🟢 منخفضة: {len(self.issues['low'])}
  - ℹ️ معلومات: {len(self.issues['info'])}

📊 الإجمالي: {total} مشكلة
"""
        
        return summary.strip()
    
    def _generate_recommendations(self) -> List[str]:
        """إنشاء توصيات"""
        recommendations = []
        
        if len(self.issues['critical']) > 0:
            recommendations.append(
                f"⚠️ عالج {len(self.issues['critical'])} مشكلة حرجة فوراً"
            )
        
        if len(self.issues['high']) > 5:
            recommendations.append(
                f"📌 {len(self.issues['high'])} مشكلة عالية الأهمية تحتاج معالجة"
            )
        
        if self.quality_score < 70:
            recommendations.append(
                "💡 النقاط منخفضة - يُنصح بمراجعة شاملة للكود"
            )
        
        # توصيات محددة حسب نوع المشاكل
        security_issues = sum(
            1 for issue in self.issues['critical'] + self.issues['high']
            if 'injection' in issue['message'].lower() or 
               'xss' in issue['message'].lower() or
               'security' in issue['message'].lower()
        )
        
        if security_issues > 0:
            recommendations.append(
                f"🔒 {security_issues} مشكلة أمنية - أولوية قصوى"
            )
        
        return recommendations
    
    # ═══════════════════════════════════════════════════════════════════════
    # 💾 SAVE
    # ═══════════════════════════════════════════════════════════════════════
    
    def _add_issue(self, severity: str, message: str, location: str, 
                   extra: Dict = None):
        """إضافة مشكلة"""
        issue = {
            'severity': severity,
            'message': message,
            'location': location,
            'timestamp': datetime.now().isoformat()
        }
        
        if extra:
            issue['extra'] = extra
        
        self.issues[severity].append(issue)
    
    def _save_daily_report(self, report: Dict):
        """حفظ التقرير اليومي"""
        try:
            os.makedirs(DAILY_REPORTS_DIR, exist_ok=True)
            
            filename = f"report_{self.scan_timestamp.strftime('%Y-%m-%d')}.json"
            filepath = os.path.join(DAILY_REPORTS_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            # حفظ أيضاً نسخة نصية
            text_filename = f"report_{self.scan_timestamp.strftime('%Y-%m-%d')}.txt"
            text_filepath = os.path.join(DAILY_REPORTS_DIR, text_filename)
            
            with open(text_filepath, 'w', encoding='utf-8') as f:
                f.write(report['summary'])
                f.write('\n\n' + '='*70 + '\n\n')
                
                for recommendation in report['recommendations']:
                    f.write(f"{recommendation}\n")
        
        except Exception as e:
            print(f"[ERROR] Error saving daily report: {e}")
    
    def _save_issues(self):
        """حفظ المشاكل"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open(CODE_ISSUES_LOG, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': self.scan_timestamp.isoformat(),
                    'quality_score': self.quality_score,
                    'issues': self.issues
                }, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"[ERROR] Error saving issues: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_code_monitor = None

def get_code_monitor() -> CodeQualityMonitor:
    """الحصول على مراقب الكود (Singleton)"""
    global _code_monitor
    
    if _code_monitor is None:
        _code_monitor = CodeQualityMonitor()
    
    return _code_monitor


__all__ = [
    'CodeQualityMonitor',
    'get_code_monitor'
]

