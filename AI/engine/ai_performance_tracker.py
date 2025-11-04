"""
AI Performance Tracker - تتبع الأداء والتحسين المستمر
"""

from typing import Dict, List, Any
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict


class PerformanceTracker:
    
    def __init__(self):
        self.metrics = {
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'avg_confidence': 0.0,
            'avg_response_time': 0.0,
            'queries_by_type': defaultdict(int),
            'errors_by_type': defaultdict(int),
            'expert_usage': defaultdict(int)
        }
        self.performance_log = []
        self._load_metrics()
    
    def _load_metrics(self):
        metrics_file = 'AI/data/performance_metrics.json'
        if os.path.exists(metrics_file):
            try:
                with open(metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.metrics = data.get('metrics', self.metrics)
                    self.performance_log = data.get('log', [])[-1000:]
            except:
                pass
    
    def record_query(self, query: str, response: Dict, execution_time: float):
        self.metrics['total_queries'] += 1
        
        if response.get('answer'):
            self.metrics['successful_queries'] += 1
        else:
            self.metrics['failed_queries'] += 1
        
        confidence = response.get('confidence', 0.0)
        
        total = self.metrics['total_queries']
        old_avg = self.metrics['avg_confidence']
        self.metrics['avg_confidence'] = ((old_avg * (total - 1)) + confidence) / total
        
        old_time = self.metrics['avg_response_time']
        self.metrics['avg_response_time'] = ((old_time * (total - 1)) + execution_time) / total
        
        query_type = self._classify_query(query)
        self.metrics['queries_by_type'][query_type] += 1
        
        if response.get('sources'):
            for source in response['sources']:
                self.metrics['expert_usage'][source] += 1
        
        self.performance_log.append({
            'timestamp': datetime.now().isoformat(),
            'query_type': query_type,
            'confidence': confidence,
            'execution_time': execution_time,
            'success': bool(response.get('answer'))
        })
        
        self._save_metrics()
    
    def _classify_query(self, query: str) -> str:
        q = query.lower()
        
        if any(w in q for w in ['error', 'خطأ', 'bug']):
            return 'debug'
        if any(w in q for w in ['كيف', 'how', 'steps']):
            return 'tutorial'
        if any(w in q for w in ['رصيد', 'balance']):
            return 'balance_query'
        if any(w in q for w in ['أضف', 'add', 'create']):
            return 'action'
        
        return 'general'
    
    def _save_metrics(self):
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open('AI/data/performance_metrics.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'metrics': dict(self.metrics),
                    'log': self.performance_log[-1000:],
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def get_performance_report(self) -> Dict:
        success_rate = 0
        if self.metrics['total_queries'] > 0:
            success_rate = (self.metrics['successful_queries'] / self.metrics['total_queries']) * 100
        
        return {
            'total_queries': self.metrics['total_queries'],
            'success_rate': round(success_rate, 2),
            'avg_confidence': round(self.metrics['avg_confidence'] * 100, 2),
            'avg_response_time': round(self.metrics['avg_response_time'], 3),
            'top_query_types': dict(sorted(
                self.metrics['queries_by_type'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]),
            'expert_usage': dict(self.metrics['expert_usage']),
            'recent_trend': self._calculate_trend()
        }
    
    def _calculate_trend(self) -> str:
        if len(self.performance_log) < 20:
            return 'insufficient_data'
        
        recent_success = sum(
            1 for p in self.performance_log[-10:]
            if p.get('success')
        ) / 10
        
        older_success = sum(
            1 for p in self.performance_log[-20:-10]
            if p.get('success')
        ) / 10
        
        if recent_success > older_success + 0.1:
            return 'improving'
        elif recent_success < older_success - 0.1:
            return 'declining'
        else:
            return 'stable'


_performance_tracker = None

def get_performance_tracker():
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()
    return _performance_tracker


__all__ = ['PerformanceTracker', 'get_performance_tracker']

