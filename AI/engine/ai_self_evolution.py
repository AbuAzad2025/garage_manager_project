"""
🧬 AI Self-Evolution Engine - محرك التطور الذاتي
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تطور ذاتي مستمر
- التعلم من الأخطاء
- تحسين الأداء تلقائياً
- اكتشاف نقاط الضعف
- تطوير استراتيجيات جديدة

Created: 2025-11-01
Version: Evolution 1.0 - GENIUS LEVEL
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
import re


# ═══════════════════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

EVOLUTION_LOG = 'AI/data/evolution_log.json'
ERROR_LEARNING_LOG = 'AI/data/error_learning.json'
PERFORMANCE_METRICS = 'AI/data/performance_metrics.json'
KNOWLEDGE_GAPS = 'AI/data/knowledge_gaps.json'


# ═══════════════════════════════════════════════════════════════════════════
# 🧬 SELF EVOLUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class SelfEvolutionEngine:
    """
    محرك التطور الذاتي
    
    القدرات:
    1. تحليل الأداء الذاتي
    2. اكتشاف نقاط الضعف
    3. التعلم من الأخطاء
    4. تطوير استراتيجيات جديدة
    5. تحسين الإجابات
    6. قياس الثقة
    """
    
    def __init__(self):
        self.performance_history = []
        self.error_patterns = {}
        self.knowledge_gaps = []
        self.evolution_metrics = {
            'total_interactions': 0,
            'successful_responses': 0,
            'failed_responses': 0,
            'average_confidence': 0.0,
            'learning_rate': 0.0,
            'evolution_level': 1
        }
        self.load_state()
    
    def load_state(self):
        """تحميل حالة التطور"""
        try:
            if os.path.exists(PERFORMANCE_METRICS):
                with open(PERFORMANCE_METRICS, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.evolution_metrics = data.get('metrics', self.evolution_metrics)
                    self.performance_history = data.get('history', [])
        except Exception:
            pass
    
    def save_state(self):
        """حفظ حالة التطور"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open(PERFORMANCE_METRICS, 'w', encoding='utf-8') as f:
                json.dump({
                    'metrics': self.evolution_metrics,
                    'history': self.performance_history[-1000:],  # آخر 1000
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Error saving evolution state: {e}")
    
    def record_interaction(self, query: str, response: Dict, success: bool, 
                          confidence: float, execution_time: float):
        """
        تسجيل تفاعل مع المستخدم
        
        Args:
            query: السؤال
            response: الرد
            success: نجح أم فشل
            confidence: مستوى الثقة (0-1)
            execution_time: وقت التنفيذ بالثواني
        """
        # تحديث الإحصائيات
        self.evolution_metrics['total_interactions'] += 1
        
        if success:
            self.evolution_metrics['successful_responses'] += 1
        else:
            self.evolution_metrics['failed_responses'] += 1
        
        # تحديث متوسط الثقة
        old_avg = self.evolution_metrics['average_confidence']
        total = self.evolution_metrics['total_interactions']
        new_avg = ((old_avg * (total - 1)) + confidence) / total
        self.evolution_metrics['average_confidence'] = round(new_avg, 4)
        
        # حساب معدل التعلم
        if len(self.performance_history) >= 100:
            recent_success_rate = sum(
                1 for p in self.performance_history[-100:] 
                if p.get('success')
            ) / 100
            
            old_success_rate = sum(
                1 for p in self.performance_history[-200:-100] 
                if p.get('success')
            ) / 100 if len(self.performance_history) >= 200 else 0.5
            
            self.evolution_metrics['learning_rate'] = round(
                (recent_success_rate - old_success_rate) * 100, 2
            )
        
        # تحديث مستوى التطور
        success_rate = (
            self.evolution_metrics['successful_responses'] / 
            self.evolution_metrics['total_interactions']
        )
        
        if success_rate >= 0.95 and self.evolution_metrics['average_confidence'] >= 0.85:
            self.evolution_metrics['evolution_level'] = 5  # عبقري
        elif success_rate >= 0.90 and self.evolution_metrics['average_confidence'] >= 0.75:
            self.evolution_metrics['evolution_level'] = 4  # خبير
        elif success_rate >= 0.80 and self.evolution_metrics['average_confidence'] >= 0.65:
            self.evolution_metrics['evolution_level'] = 3  # متقدم
        elif success_rate >= 0.70:
            self.evolution_metrics['evolution_level'] = 2  # متوسط
        else:
            self.evolution_metrics['evolution_level'] = 1  # مبتدئ
        
        # تسجيل في التاريخ
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'query': query[:200],  # أول 200 حرف
            'success': success,
            'confidence': confidence,
            'execution_time': execution_time,
            'response_length': len(str(response))
        })
        
        # حفظ
        self.save_state()
        
        # تحليل إذا كان فشل
        if not success:
            self.analyze_failure(query, response)
    
    def analyze_failure(self, query: str, response: Dict):
        """
        تحليل الفشل والتعلم منه
        
        Args:
            query: السؤال الذي فشل
            response: الرد الذي كان خاطئاً
        """
        try:
            # تحليل نمط الخطأ
            error_type = self._categorize_error(query, response)
            
            # تسجيل في error patterns
            if error_type not in self.error_patterns:
                self.error_patterns[error_type] = {
                    'count': 0,
                    'examples': [],
                    'learned': False
                }
            
            self.error_patterns[error_type]['count'] += 1
            self.error_patterns[error_type]['examples'].append({
                'query': query[:200],
                'timestamp': datetime.now().isoformat()
            })
            
            # الاحتفاظ بآخر 10 أمثلة
            self.error_patterns[error_type]['examples'] = \
                self.error_patterns[error_type]['examples'][-10:]
            
            # حفظ في ERROR_LEARNING_LOG
            self._save_error_learning()
            
            # اكتشاف فجوة معرفية
            knowledge_gap = self._detect_knowledge_gap(query, error_type)
            if knowledge_gap:
                self.knowledge_gaps.append(knowledge_gap)
                self._save_knowledge_gaps()
        
        except Exception as e:
            print(f"[ERROR] Error analyzing failure: {e}")
    
    def _categorize_error(self, query: str, response: Dict) -> str:
        """تصنيف نوع الخطأ"""
        query_lower = query.lower()
        
        # أنواع الأخطاء
        if any(word in query_lower for word in ['رصيد', 'حساب', 'مبلغ', 'balance']):
            return 'accounting_error'
        
        if any(word in query_lower for word in ['عميل', 'مورد', 'شريك', 'customer', 'supplier']):
            return 'entity_error'
        
        if any(word in query_lower for word in ['مخزون', 'منتج', 'قطعة', 'stock', 'product']):
            return 'inventory_error'
        
        if any(word in query_lower for word in ['قيد', 'محاسبي', 'دفتر', 'gl', 'ledger']):
            return 'gl_error'
        
        if any(word in query_lower for word in ['ضريبة', 'vat', 'tax']):
            return 'tax_error'
        
        return 'unknown_error'
    
    def _detect_knowledge_gap(self, query: str, error_type: str) -> Optional[Dict]:
        """اكتشاف فجوة معرفية"""
        # تحليل السؤال لاكتشاف ما ينقص المساعد
        
        gap = {
            'timestamp': datetime.now().isoformat(),
            'query': query[:200],
            'error_type': error_type,
            'gap_description': '',
            'priority': 'medium'
        }
        
        # تحديد الفجوة
        if error_type == 'accounting_error':
            gap['gap_description'] = 'نقص في المعرفة المحاسبية لهذا النوع من العمليات'
            gap['priority'] = 'high'
        
        elif error_type == 'tax_error':
            gap['gap_description'] = 'نقص في المعرفة الضريبية'
            gap['priority'] = 'high'
        
        elif error_type == 'gl_error':
            gap['gap_description'] = 'نقص في فهم القيود المحاسبية'
            gap['priority'] = 'critical'
        
        else:
            gap['gap_description'] = 'فجوة معرفية غير محددة'
            gap['priority'] = 'low'
        
        return gap
    
    def _save_error_learning(self):
        """حفظ التعلم من الأخطاء"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open(ERROR_LEARNING_LOG, 'w', encoding='utf-8') as f:
                json.dump({
                    'error_patterns': self.error_patterns,
                    'total_errors': sum(p['count'] for p in self.error_patterns.values()),
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Error saving error learning: {e}")
    
    def _save_knowledge_gaps(self):
        """حفظ فجوات المعرفة"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open(KNOWLEDGE_GAPS, 'w', encoding='utf-8') as f:
                json.dump({
                    'gaps': self.knowledge_gaps[-100:],  # آخر 100
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Error saving knowledge gaps: {e}")
    
    def get_evolution_report(self) -> Dict[str, Any]:
        """الحصول على تقرير التطور"""
        success_rate = 0
        if self.evolution_metrics['total_interactions'] > 0:
            success_rate = (
                self.evolution_metrics['successful_responses'] / 
                self.evolution_metrics['total_interactions']
            ) * 100
        
        level_names = {
            1: '🟡 مبتدئ',
            2: '🟠 متوسط',
            3: '🔵 متقدم',
            4: '🟣 خبير',
            5: '🏆 عبقري'
        }
        
        return {
            'evolution_level': self.evolution_metrics['evolution_level'],
            'evolution_level_name': level_names.get(
                self.evolution_metrics['evolution_level'], 'غير محدد'
            ),
            'total_interactions': self.evolution_metrics['total_interactions'],
            'success_rate': round(success_rate, 2),
            'average_confidence': round(
                self.evolution_metrics['average_confidence'] * 100, 2
            ),
            'learning_rate': self.evolution_metrics['learning_rate'],
            'total_errors': sum(p['count'] for p in self.error_patterns.values()),
            'error_types': len(self.error_patterns),
            'knowledge_gaps': len(self.knowledge_gaps),
            'recent_performance': self._get_recent_performance()
        }
    
    def _get_recent_performance(self) -> Dict:
        """أداء الـ 24 ساعة الأخيرة"""
        if not self.performance_history:
            return {
                'interactions': 0,
                'success_rate': 0,
                'avg_confidence': 0,
                'avg_response_time': 0
            }
        
        # آخر 24 ساعة
        cutoff = datetime.now() - timedelta(hours=24)
        
        recent = [
            p for p in self.performance_history
            if datetime.fromisoformat(p['timestamp']) >= cutoff
        ]
        
        if not recent:
            return {
                'interactions': 0,
                'success_rate': 0,
                'avg_confidence': 0,
                'avg_response_time': 0
            }
        
        success_count = sum(1 for p in recent if p.get('success'))
        avg_confidence = sum(p.get('confidence', 0) for p in recent) / len(recent)
        avg_time = sum(p.get('execution_time', 0) for p in recent) / len(recent)
        
        return {
            'interactions': len(recent),
            'success_rate': round((success_count / len(recent)) * 100, 2),
            'avg_confidence': round(avg_confidence * 100, 2),
            'avg_response_time': round(avg_time, 3)
        }
    
    def suggest_improvements(self) -> List[str]:
        """اقتراح تحسينات بناءً على التعلم"""
        suggestions = []
        
        # تحليل الأخطاء الشائعة
        if self.error_patterns:
            most_common = sorted(
                self.error_patterns.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )[:3]
            
            for error_type, data in most_common:
                if data['count'] >= 5 and not data.get('learned'):
                    suggestions.append(
                        f"تحسين المعرفة في: {error_type} ({data['count']} أخطاء)"
                    )
        
        # تحليل فجوات المعرفة
        critical_gaps = [
            g for g in self.knowledge_gaps
            if g.get('priority') == 'critical'
        ]
        
        if len(critical_gaps) >= 3:
            suggestions.append(
                f"هناك {len(critical_gaps)} فجوة معرفية حرجة تحتاج معالجة"
            )
        
        # تحليل الأداء
        if self.evolution_metrics['average_confidence'] < 0.7:
            suggestions.append(
                "مستوى الثقة منخفض - يحتاج تدريب إضافي"
            )
        
        if self.evolution_metrics['learning_rate'] < 0:
            suggestions.append(
                "معدل التعلم سلبي - يحتاج مراجعة الاستراتيجية"
            )
        
        return suggestions


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_evolution_engine = None

def get_evolution_engine() -> SelfEvolutionEngine:
    """الحصول على محرك التطور (Singleton)"""
    global _evolution_engine
    
    if _evolution_engine is None:
        _evolution_engine = SelfEvolutionEngine()
    
    return _evolution_engine


__all__ = [
    'SelfEvolutionEngine',
    'get_evolution_engine'
]

