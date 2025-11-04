"""
AI Master Controller - المتحكم الرئيسي الشامل
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json


class MasterController:
    
    def __init__(self):
        self.subsystems = {}
        self.active_operations = []
        self.system_state = {
            'reasoning_engine': False,
            'experts': {},
            'learning': False,
            'evolution': False,
            'performance': False,
            'auditing': False
        }
        self._initialize_subsystems()
    
    def _initialize_subsystems(self):
        try:
            from AI.engine.ai_reasoning_engine import get_reasoning_engine
            from AI.engine.ai_python_expert import get_python_expert
            from AI.engine.ai_database_expert import get_database_expert
            from AI.engine.ai_web_expert import get_web_expert
            from AI.engine.ai_user_guide_master import get_user_guide_master
            from AI.engine.ai_learning_system import get_learning_system
            from AI.engine.ai_self_evolution import get_evolution_engine
            from AI.engine.ai_performance_tracker import get_performance_tracker
            from AI.engine.ai_accounting_auditor import get_accounting_auditor
            from AI.engine.ai_continuous_learner import get_continuous_learner
            from AI.engine.ai_book_reader import get_book_reader
            from AI.engine.ai_deep_memory import get_deep_memory
            from AI.engine.ai_comprehension_engine import get_comprehension_engine
            
            self.subsystems['reasoning'] = get_reasoning_engine()
            self.subsystems['python_expert'] = get_python_expert()
            self.subsystems['database_expert'] = get_database_expert()
            self.subsystems['web_expert'] = get_web_expert()
            self.subsystems['guide_master'] = get_user_guide_master()
            self.subsystems['learning'] = get_learning_system()
            self.subsystems['evolution'] = get_evolution_engine()
            self.subsystems['performance'] = get_performance_tracker()
            self.subsystems['auditor'] = get_accounting_auditor()
            self.subsystems['continuous_learner'] = get_continuous_learner()
            self.subsystems['book_reader'] = get_book_reader()
            self.subsystems['deep_memory'] = get_deep_memory()
            self.subsystems['comprehension'] = get_comprehension_engine()
            
            self.system_state['reasoning_engine'] = True
            self.system_state['experts'] = {
                'python': True,
                'database': True,
                'web': True,
                'guide': True
            }
            self.system_state['learning'] = True
            self.system_state['evolution'] = True
            self.system_state['performance'] = True
            self.system_state['auditing'] = True
            self.system_state['continuous_learning'] = True
            self.system_state['book_reading'] = True
            self.system_state['deep_memory'] = True
            self.system_state['comprehension'] = True
            
        except Exception as e:
            print(f"Subsystem init error: {e}")
    
    def process_intelligent_query(self, query: str, context: Dict) -> Dict[str, Any]:
        operation_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
        
        operation = {
            'id': operation_id,
            'query': query,
            'start_time': datetime.now(),
            'subsystems_used': [],
            'reasoning_steps': [],
            'confidence_breakdown': {},
            'result': None
        }
        
        try:
            if self.subsystems.get('reasoning'):
                operation['subsystems_used'].append('reasoning')
                
                result = self.subsystems['reasoning'].reason_through_problem(query, context)
                
                if result.get('answer'):
                    operation['result'] = result
                    operation['reasoning_steps'] = result.get('reasoning_steps', [])
                    operation['confidence_breakdown']['reasoning'] = result.get('confidence', 0)
                    
                    if result.get('data_used'):
                        operation['data_accessed'] = result['data_used']
                    
                    self._track_operation(operation)
                    
                    return result
            
            if self.subsystems.get('python_expert') and any(w in query.lower() for w in ['error', 'خطأ', 'python']):
                operation['subsystems_used'].append('python_expert')
                
                result = self.subsystems['python_expert'].analyze_error(query, context.get('code', ''))
                
                if result:
                    operation['result'] = result
                    self._track_operation(operation)
                    
                    return {
                        'answer': self._format_python_error_answer(result),
                        'confidence': 0.9,
                        'sources': ['Python Expert']
                    }
            
            if self.subsystems.get('guide_master'):
                operation['subsystems_used'].append('guide_master')
                
                result = self.subsystems['guide_master'].answer_question(query)
                
                if result and isinstance(result, dict) and result.get('steps'):
                    operation['result'] = result
                    self._track_operation(operation)
                    
                    return {
                        'answer': self._format_guide_answer(result),
                        'confidence': 0.85,
                        'sources': ['User Guide']
                    }
            
            operation['result'] = {'answer': 'لم أتمكن من الإجابة', 'confidence': 0.3}
            self._track_operation(operation)
            
            return operation['result']
        
        except Exception as e:
            operation['error'] = str(e)
            self._track_operation(operation)
            raise
    
    def _format_python_error_answer(self, result: Dict) -> str:
        parts = []
        
        parts.append(f"🐍 نوع الخطأ: {result.get('error_type', 'غير محدد')}")
        parts.append(f"\n📌 السبب: {result.get('cause', '')}")
        
        if result.get('solutions'):
            parts.append('\n✅ الحلول:')
            for i, sol in enumerate(result['solutions'][:5], 1):
                parts.append(f"{i}. {sol}")
        
        if result.get('code_fix'):
            parts.append(f"\n💻 الكود الصحيح:\n```python\n{result['code_fix']}\n```")
        
        if result.get('prevention_tips'):
            parts.append('\n🛡️ الوقاية:')
            for tip in result['prevention_tips'][:3]:
                parts.append(f"  - {tip}")
        
        return '\n'.join(parts)
    
    def _format_guide_answer(self, result: Dict) -> str:
        parts = []
        
        if result.get('topic'):
            parts.append(f"📍 {result['topic']}")
        
        if result.get('description'):
            parts.append(f"\n{result['description']}")
        
        if result.get('route'):
            parts.append(f"\n🔗 المسار: {result['route']}")
        
        if result.get('steps'):
            parts.append('\n📋 الخطوات:')
            for step in result['steps']:
                parts.append(f"  {step}")
        
        if result.get('fields'):
            parts.append('\n📝 الحقول:')
            for field, desc in list(result['fields'].items())[:8]:
                parts.append(f"  • {field}: {desc}")
        
        if result.get('gl_effect'):
            parts.append(f"\n💼 التأثير المحاسبي:\n  {result['gl_effect']}")
        
        if result.get('tips'):
            parts.append('\n💡 نصائح:')
            for tip in result['tips']:
                parts.append(f"  - {tip}")
        
        return '\n'.join(parts)
    
    def _track_operation(self, operation: Dict):
        operation['end_time'] = datetime.now()
        operation['duration'] = (operation['end_time'] - operation['start_time']).total_seconds()
        
        self.active_operations.append(operation)
        
        if len(self.active_operations) > 100:
            self.active_operations = self.active_operations[-100:]
    
    def get_system_status(self) -> Dict:
        return {
            'state': self.system_state,
            'active_operations': len(self.active_operations),
            'recent_operations': self.active_operations[-10:] if self.active_operations else [],
            'subsystems_count': len(self.subsystems),
            'all_operational': all(self.system_state.values())
        }
    
    def execute_system_command(self, command: str, params: Dict = None) -> Dict:
        if params is None:
            params = {}
        
        if command == 'scan_system':
            return self._scan_all_systems()
        
        elif command == 'audit_accounting':
            return self._run_accounting_audit()
        
        elif command == 'optimize_performance':
            return self._optimize_all_systems()
        
        elif command == 'self_diagnose':
            return self._diagnose_system_health()
        
        elif command == 'start_learning_session':
            return self._start_learning_session()
        
        elif command == 'read_book':
            return self._read_book(params.get('file_path'), params.get('format', 'markdown'))
        
        elif command == 'comprehend_concept':
            return self._comprehend_concept(params.get('concept'))
        
        elif command == 'consolidate_memory':
            return self._consolidate_all_memory()
        
        return {'success': False, 'error': 'Unknown command'}
    
    def _scan_all_systems(self) -> Dict:
        scan_results = {
            'timestamp': datetime.now().isoformat(),
            'subsystems': {}
        }
        
        for name, subsystem in self.subsystems.items():
            scan_results['subsystems'][name] = {
                'status': 'operational' if subsystem else 'offline',
                'type': type(subsystem).__name__ if subsystem else None
            }
        
        return {
            'success': True,
            'results': scan_results
        }
    
    def _run_accounting_audit(self) -> Dict:
        if not self.subsystems.get('auditor'):
            return {'success': False, 'error': 'Auditor not available'}
        
        auditor = self.subsystems['auditor']
        summary = auditor.get_audit_summary()
        
        return {
            'success': True,
            'audit_summary': summary
        }
    
    def _optimize_all_systems(self) -> Dict:
        optimizations = []
        
        if self.subsystems.get('performance'):
            perf = self.subsystems['performance'].get_performance_report()
            
            if perf.get('avg_response_time', 0) > 1.0:
                optimizations.append('Response time slow - consider caching')
            
            if perf.get('success_rate', 0) < 80:
                optimizations.append('Success rate low - review reasoning engine')
        
        if self.subsystems.get('evolution'):
            evo = self.subsystems['evolution'].get_evolution_report()
            
            if evo.get('evolution_level', 0) < 3:
                optimizations.append('Evolution level low - needs more training')
        
        return {
            'success': True,
            'optimizations': optimizations
        }
    
    def _diagnose_system_health(self) -> Dict:
        health = {
            'overall': 'healthy',
            'issues': [],
            'warnings': []
        }
        
        for name, active in self.system_state.items():
            if not active:
                health['issues'].append(f'{name} is offline')
                health['overall'] = 'degraded'
        
        if self.subsystems.get('performance'):
            perf = self.subsystems['performance'].get_performance_report()
            
            if perf.get('recent_trend') == 'declining':
                health['warnings'].append('Performance trend is declining')
        
        return health
    
    def _start_learning_session(self) -> Dict:
        if not self.subsystems.get('continuous_learner'):
            return {'success': False, 'error': 'Continuous learner not available'}
        
        learner = self.subsystems['continuous_learner']
        session = learner.start_learning_session()
        
        return {
            'success': True,
            'session': session
        }
    
    def _read_book(self, file_path: str, format: str = 'markdown') -> Dict:
        if not self.subsystems.get('book_reader'):
            return {'success': False, 'error': 'Book reader not available'}
        
        reader = self.subsystems['book_reader']
        
        if format == 'pdf':
            result = reader.read_pdf_book(file_path)
        else:
            result = reader.read_markdown_book(file_path)
        
        return result
    
    def _comprehend_concept(self, concept: str) -> Dict:
        if not self.subsystems.get('comprehension'):
            return {'success': False, 'error': 'Comprehension engine not available'}
        
        comp = self.subsystems['comprehension']
        explanation = comp.explain_fully(concept)
        
        return {
            'success': True,
            'explanation': explanation
        }
    
    def _consolidate_all_memory(self) -> Dict:
        if not self.subsystems.get('deep_memory'):
            return {'success': False, 'error': 'Deep memory not available'}
        
        memory = self.subsystems['deep_memory']
        consolidated = memory.consolidate_memory()
        
        return {
            'success': True,
            'consolidated_items': consolidated,
            'memory_stats': memory.get_memory_stats()
        }


_master_controller = None

def get_master_controller():
    global _master_controller
    if _master_controller is None:
        _master_controller = MasterController()
    return _master_controller


__all__ = ['MasterController', 'get_master_controller']

