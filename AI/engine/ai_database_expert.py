"""
🗄️ AI Database Expert - خبير قواعد البيانات
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تحسين استعلامات SQL
- اكتشاف مشاكل الأداء
- اقتراح indexes
- تحليل database schema
- Query optimization

Created: 2025-11-01
Version: Database Expert 1.0 - MASTER LEVEL
"""

from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import inspect, text
from extensions import db
import re


# ═══════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE EXPERT ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseExpert:
    """
    خبير قواعد بيانات عبقري
    
    القدرات:
    1. تحليل وتحسين SQL queries
    2. اكتشاف N+1 problems
    3. اقتراح indexes
    4. تحليل performance
    5. Database design review
    6. Migration suggestions
    """
    
    def __init__(self):
        self.common_patterns = self._load_common_patterns()
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        تحليل استعلام SQL
        
        Args:
            query: استعلام SQL
        
        Returns:
            تحليل شامل مع اقتراحات
        """
        analysis = {
            'query': query,
            'issues': [],
            'performance_score': 100,
            'suggestions': [],
            'optimized_query': None,
            'estimated_complexity': 'O(1)'
        }
        
        # فحص SELECT *
        if 'SELECT *' in query.upper():
            analysis['issues'].append({
                'type': 'bad_practice',
                'severity': 'medium',
                'message': 'استخدام SELECT * - حدد الأعمدة المطلوبة فقط',
                'fix': 'استبدل * بأسماء الأعمدة المحددة'
            })
            analysis['performance_score'] -= 10
        
        # فحص عدم وجود WHERE
        if 'WHERE' not in query.upper() and 'SELECT' in query.upper():
            analysis['issues'].append({
                'type': 'missing_where',
                'severity': 'high',
                'message': 'لا يوجد WHERE clause - قد يعيد جميع السجلات',
                'fix': 'أضف WHERE لتحديد السجلات المطلوبة'
            })
            analysis['performance_score'] -= 20
            analysis['estimated_complexity'] = 'O(n) - Full table scan'
        
        # فحص عدم وجود LIMIT
        if 'LIMIT' not in query.upper() and 'SELECT' in query.upper():
            analysis['suggestions'].append(
                'أضف LIMIT للحد من عدد النتائج المعادة'
            )
        
        # فحص JOIN performance
        join_count = query.upper().count('JOIN')
        if join_count > 3:
            analysis['issues'].append({
                'type': 'many_joins',
                'severity': 'medium',
                'message': f'عدد كبير من JOINs ({join_count}) - قد يؤثر على الأداء',
                'fix': 'فكر في إعادة تصميم القاموس أو استخدام subqueries'
            })
            analysis['performance_score'] -= (join_count - 3) * 5
        
        # فحص استخدام LIKE %...%
        if re.search(r"LIKE\s+['\"]%.*%['\"]", query, re.IGNORECASE):
            analysis['issues'].append({
                'type': 'slow_like',
                'severity': 'high',
                'message': 'LIKE %...% بطيء جداً - لا يستخدم index',
                'fix': 'استخدم Full-Text Search أو ابدأ النمط بحرف ثابت'
            })
            analysis['performance_score'] -= 25
        
        # فحص OR في WHERE
        or_count = len(re.findall(r'\bOR\b', query, re.IGNORECASE))
        if or_count > 2:
            analysis['suggestions'].append(
                f'عدد كبير من OR ({or_count}) - فكر في استخدام IN بدلاً منها'
            )
        
        # فحص Subqueries
        if 'SELECT' in query[10:]:  # subquery
            analysis['suggestions'].append(
                'استخدام subquery - تأكد من أنه الحل الأمثل (فكر في JOIN)'
            )
        
        return analysis
    
    def suggest_index(self, table_name: str, query_pattern: str) -> List[Dict]:
        """اقتراح indexes"""
        suggestions = []
        
        # استخراج أعمدة WHERE
        where_match = re.search(r'WHERE\s+(\w+)', query_pattern, re.IGNORECASE)
        if where_match:
            column = where_match.group(1)
            suggestions.append({
                'type': 'single_column_index',
                'table': table_name,
                'columns': [column],
                'sql': f'CREATE INDEX idx_{table_name}_{column} ON {table_name}({column});',
                'reason': f'لتسريع WHERE {column}'
            })
        
        # استخراج أعمدة JOIN
        join_matches = re.findall(r'JOIN\s+\w+\s+ON\s+\w+\.(\w+)', query_pattern, re.IGNORECASE)
        for column in join_matches:
            suggestions.append({
                'type': 'foreign_key_index',
                'table': table_name,
                'columns': [column],
                'sql': f'CREATE INDEX idx_{table_name}_{column}_fk ON {table_name}({column});',
                'reason': f'لتسريع JOIN على {column}'
            })
        
        return suggestions
    
    def detect_n_plus_one(self, code_context: str) -> Optional[Dict]:
        """اكتشاف N+1 problem"""
        # نمط: for loop مع query داخلها
        pattern = r'for\s+\w+\s+in\s+.*:\s*\n.*\.query\.'
        
        if re.search(pattern, code_context, re.MULTILINE):
            return {
                'detected': True,
                'issue': 'N+1 Query Problem',
                'explanation': '''
يتم تنفيذ query منفصل لكل عنصر في الـ loop.

مثال المشكلة:
```python
customers = Customer.query.all()  # 1 query
for customer in customers:
    sales = customer.sales  # N queries (واحد لكل customer)
```

الحل:
```python
# استخدم joinedload أو subqueryload
from sqlalchemy.orm import joinedload

customers = Customer.query.options(
    joinedload(Customer.sales)
).all()  # 1 query فقط

for customer in customers:
    sales = customer.sales  # لا توجد queries إضافية
```
                ''',
                'solution': 'استخدم eager loading: joinedload() أو subqueryload()'
            }
        
        return None
    
    def analyze_schema(self, table_name: str) -> Dict[str, Any]:
        """تحليل schema الجدول"""
        try:
            inspector = inspect(db.engine)
            
            # الأعمدة
            columns = inspector.get_columns(table_name)
            
            # Foreign Keys
            fks = inspector.get_foreign_keys(table_name)
            
            # Indexes
            indexes = inspector.get_indexes(table_name)
            
            analysis = {
                'table_name': table_name,
                'total_columns': len(columns),
                'total_fks': len(fks),
                'total_indexes': len(indexes),
                'issues': [],
                'recommendations': []
            }
            
            # فحص: جدول بدون primary key
            pk = inspector.get_pk_constraint(table_name)
            if not pk.get('constrained_columns'):
                analysis['issues'].append({
                    'type': 'no_primary_key',
                    'severity': 'critical',
                    'message': 'الجدول لا يحتوي على Primary Key'
                })
            
            # فحص: FK بدون index
            fk_columns = set()
            for fk in fks:
                for col in fk.get('constrained_columns', []):
                    fk_columns.add(col)
            
            indexed_columns = set()
            for idx in indexes:
                for col in idx.get('column_names', []):
                    indexed_columns.add(col)
            
            unindexed_fks = fk_columns - indexed_columns
            if unindexed_fks:
                analysis['recommendations'].append({
                    'type': 'add_fk_indexes',
                    'message': f'أضف indexes على FK: {", ".join(unindexed_fks)}'
                })
            
            # فحص: عدد كبير من الأعمدة
            if len(columns) > 30:
                analysis['recommendations'].append({
                    'type': 'normalize_table',
                    'message': f'الجدول يحتوي على {len(columns)} عمود - فكر في normalization'
                })
            
            # فحص: أعمدة nullable كثيرة
            nullable_count = sum(1 for col in columns if col.get('nullable', True))
            if nullable_count > len(columns) * 0.7:
                analysis['recommendations'].append({
                    'type': 'reduce_nullables',
                    'message': f'{nullable_count} عمود nullable - فكر في قيم افتراضية'
                })
            
            return analysis
        
        except Exception as e:
            return {'error': str(e)}
    
    def suggest_query_optimization(self, slow_query: str) -> Dict[str, Any]:
        """اقتراح تحسينات للاستعلام البطيء"""
        optimizations = []
        optimized = slow_query
        
        # 1. استبدال SELECT *
        if 'SELECT *' in optimized.upper():
            optimizations.append({
                'type': 'specific_columns',
                'before': 'SELECT *',
                'after': 'SELECT column1, column2, ...',
                'benefit': 'تقليل البيانات المنقولة'
            })
        
        # 2. إضافة LIMIT
        if 'LIMIT' not in optimized.upper():
            optimizations.append({
                'type': 'add_limit',
                'before': optimized,
                'after': optimized + ' LIMIT 100',
                'benefit': 'تحديد عدد النتائج'
            })
        
        # 3. استخدام EXISTS بدل COUNT
        if 'COUNT(*)' in optimized.upper() and 'WHERE' in optimized.upper():
            optimizations.append({
                'type': 'use_exists',
                'before': 'SELECT COUNT(*) FROM table WHERE condition',
                'after': 'SELECT EXISTS(SELECT 1 FROM table WHERE condition LIMIT 1)',
                'benefit': 'EXISTS أسرع للتحقق من الوجود'
            })
        
        # 4. استخدام IN بدل OR
        or_count = len(re.findall(r'\bOR\b', optimized, re.IGNORECASE))
        if or_count > 2:
            optimizations.append({
                'type': 'use_in',
                'before': 'WHERE col = 1 OR col = 2 OR col = 3',
                'after': 'WHERE col IN (1, 2, 3)',
                'benefit': 'IN أوضح وأسرع'
            })
        
        return {
            'original_query': slow_query,
            'optimizations': optimizations,
            'estimated_improvement': f'{len(optimizations) * 15}%'
        }
    
    def _load_common_patterns(self) -> Dict:
        """تحميل الأنماط الشائعة"""
        return {
            'slow_patterns': [
                r'SELECT \* FROM',
                r'LIKE ["\']%.*%["\']',
                r'OR.*OR.*OR'
            ],
            'good_patterns': [
                r'SELECT \w+, \w+ FROM',
                r'WHERE.*LIMIT',
                r'.*INDEX'
            ]
        }


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_db_expert = None

def get_database_expert() -> DatabaseExpert:
    """الحصول على خبير Database (Singleton)"""
    global _db_expert
    
    if _db_expert is None:
        _db_expert = DatabaseExpert()
    
    return _db_expert


__all__ = [
    'DatabaseExpert',
    'get_database_expert'
]

