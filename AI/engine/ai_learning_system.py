"""
AI Learning System - نظام التعلم الحقيقي
"""

from typing import Dict, List, Any, Optional
import json
import os
from datetime import datetime
from collections import defaultdict


class LearningSystem:
    
    def __init__(self):
        self.learned_responses = {}
        self.error_corrections = {}
        self.pattern_library = defaultdict(list)
        self.performance_data = []
        self._load_learned_data()
    
    def _load_learned_data(self):
        learned_file = 'AI/data/learned_responses.json'
        if os.path.exists(learned_file):
            try:
                with open(learned_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.learned_responses = data.get('responses', {})
                    self.error_corrections = data.get('corrections', {})
                    self.pattern_library = defaultdict(list, data.get('patterns', {}))
            except Exception:
                pass
    
    def learn_from_interaction(self, query: str, response: str, feedback: str = None):
        query_normalized = self._normalize_query(query)
        
        if query_normalized not in self.learned_responses:
            self.learned_responses[query_normalized] = {
                'responses': [],
                'best_response': None,
                'count': 0,
                'success_count': 0
            }
        
        self.learned_responses[query_normalized]['responses'].append({
            'response': response,
            'timestamp': datetime.now().isoformat(),
            'feedback': feedback
        })
        
        self.learned_responses[query_normalized]['count'] += 1
        
        if feedback == 'positive' or feedback is None:
            self.learned_responses[query_normalized]['success_count'] += 1
            self.learned_responses[query_normalized]['best_response'] = response
        
        self._extract_patterns(query, response)
        self._save_learned_data()
    
    def learn_error_correction(self, error_type: str, solution: str):
        if error_type not in self.error_corrections:
            self.error_corrections[error_type] = []
        
        self.error_corrections[error_type].append({
            'solution': solution,
            'timestamp': datetime.now().isoformat(),
            'use_count': 0
        })
        
        self._save_learned_data()
    
    def get_learned_response(self, query: str) -> Optional[str]:
        query_normalized = self._normalize_query(query)
        
        if query_normalized in self.learned_responses:
            learned = self.learned_responses[query_normalized]
            if learned.get('best_response'):
                learned['count'] += 1
                return learned['best_response']
        
        similar = self._find_similar_learned(query_normalized)
        if similar:
            return similar
        
        return None
    
    def _normalize_query(self, query: str) -> str:
        q = query.lower().strip()
        q = ' '.join(q.split())
        return q
    
    def _extract_patterns(self, query: str, response: str):
        q_lower = query.lower()
        
        if 'كيف' in q_lower and 'خطوات' in response.lower():
            self.pattern_library['how_to_questions'].append({
                'query_pattern': 'كيف + [action]',
                'response_pattern': 'step_by_step',
                'example': query[:100]
            })
        
        if 'رصيد' in q_lower and '₪' in response:
            self.pattern_library['balance_queries'].append({
                'query_pattern': 'رصيد + [entity]',
                'response_pattern': 'balance_with_currency',
                'example': query[:100]
            })
    
    def _find_similar_learned(self, query_normalized: str) -> Optional[str]:
        for learned_q, data in self.learned_responses.items():
            similarity = self._calculate_similarity(query_normalized, learned_q)
            if similarity > 0.8:
                return data.get('best_response')
        return None
    
    def _calculate_similarity(self, q1: str, q2: str) -> float:
        words1 = set(q1.split())
        words2 = set(q2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def _save_learned_data(self):
        try:
            os.makedirs('AI/data', exist_ok=True)
            learned_file = 'AI/data/learned_responses.json'
            
            with open(learned_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'responses': self.learned_responses,
                    'corrections': self.error_corrections,
                    'patterns': dict(self.pattern_library),
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving learned data: {e}")
    
    def get_learning_stats(self) -> Dict:
        return {
            'total_learned_queries': len(self.learned_responses),
            'total_corrections': sum(len(corr) for corr in self.error_corrections.values()),
            'total_patterns': sum(len(patterns) for patterns in self.pattern_library.values()),
            'success_rate': self._calculate_success_rate()
        }
    
    def _calculate_success_rate(self) -> float:
        if not self.learned_responses:
            return 0.0
        
        total_success = sum(
            data.get('success_count', 0) 
            for data in self.learned_responses.values()
        )
        total_count = sum(
            data.get('count', 0) 
            for data in self.learned_responses.values()
        )
        
        if total_count == 0:
            return 0.0
        
        return (total_success / total_count) * 100


_learning_system = None

def get_learning_system():
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem()
    return _learning_system


__all__ = ['LearningSystem', 'get_learning_system']

