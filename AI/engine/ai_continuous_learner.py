from typing import Dict, List, Any, Set
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import hashlib


class ContinuousLearner:
    
    def __init__(self):
        self.knowledge_base = {}
        self.system_snapshot = {}
        self.changes_detected = []
        self.learning_sessions = []
        self.last_scan_time = None
        self.data_dir = Path('AI/data/continuous_learning')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_knowledge()
    
    def _load_existing_knowledge(self):
        kb_file = self.data_dir / 'knowledge_base.json'
        if kb_file.exists():
            try:
                with open(kb_file, 'r', encoding='utf-8') as f:
                    self.knowledge_base = json.load(f)
            except:
                pass
    
    def start_learning_session(self) -> Dict[str, Any]:
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        session = {
            'id': session_id,
            'start_time': datetime.now().isoformat(),
            'phases': [],
            'discoveries': [],
            'total_items_learned': 0,
            'status': 'running'
        }
        
        session['phases'].append(self._study_database_schema())
        session['phases'].append(self._study_routes_and_endpoints())
        session['phases'].append(self._study_models_and_relationships())
        session['phases'].append(self._study_forms_and_validations())
        session['phases'].append(self._study_business_logic())
        session['phases'].append(self._detect_changes_from_last_session())
        
        for phase in session['phases']:
            session['total_items_learned'] += phase.get('items_learned', 0)
            session['discoveries'].extend(phase.get('discoveries', []))
        
        session['end_time'] = datetime.now().isoformat()
        session['status'] = 'completed'
        
        self.learning_sessions.append(session)
        self._save_session(session)
        self._update_knowledge_base()
        
        return session
    
    def _study_database_schema(self) -> Dict:
        phase = {
            'name': 'Database Schema Study',
            'items_learned': 0,
            'discoveries': [],
            'tables_analyzed': []
        }
        
        try:
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            for table_name in tables:
                table_info = {
                    'name': table_name,
                    'columns': [],
                    'indexes': [],
                    'foreign_keys': [],
                    'primary_keys': []
                }
                
                for col in inspector.get_columns(table_name):
                    table_info['columns'].append({
                        'name': col['name'],
                        'type': str(col['type']),
                        'nullable': col.get('nullable', True),
                        'default': str(col.get('default')) if col.get('default') else None
                    })
                
                for idx in inspector.get_indexes(table_name):
                    table_info['indexes'].append({
                        'name': idx['name'],
                        'columns': idx['column_names'],
                        'unique': idx.get('unique', False)
                    })
                
                for fk in inspector.get_foreign_keys(table_name):
                    table_info['foreign_keys'].append({
                        'constrained_columns': fk['constrained_columns'],
                        'referred_table': fk['referred_table'],
                        'referred_columns': fk['referred_columns']
                    })
                
                pk = inspector.get_pk_constraint(table_name)
                if pk and pk.get('constrained_columns'):
                    table_info['primary_keys'] = pk['constrained_columns']
                
                self.knowledge_base[f'table_{table_name}'] = table_info
                phase['tables_analyzed'].append(table_name)
                phase['items_learned'] += 1
            
            phase['discoveries'].append(f'Analyzed {len(tables)} database tables')
            
        except Exception as e:
            phase['error'] = str(e)
        
        return phase
    
    def _study_routes_and_endpoints(self) -> Dict:
        phase = {
            'name': 'Routes and Endpoints Study',
            'items_learned': 0,
            'discoveries': [],
            'routes_analyzed': []
        }
        
        try:
            from app import app
            
            routes_info = {}
            
            for rule in app.url_map.iter_rules():
                if rule.endpoint != 'static':
                    route_key = f'route_{rule.endpoint}'
                    
                    routes_info[route_key] = {
                        'endpoint': rule.endpoint,
                        'path': str(rule.rule),
                        'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
                        'blueprint': rule.endpoint.split('.')[0] if '.' in rule.endpoint else None
                    }
                    
                    phase['routes_analyzed'].append(rule.endpoint)
                    phase['items_learned'] += 1
            
            self.knowledge_base.update(routes_info)
            phase['discoveries'].append(f'Memorized {len(routes_info)} routes')
            
        except Exception as e:
            phase['error'] = str(e)
        
        return phase
    
    def _study_models_and_relationships(self) -> Dict:
        phase = {
            'name': 'Models and Relationships Study',
            'items_learned': 0,
            'discoveries': [],
            'models_analyzed': []
        }
        
        try:
            from extensions import db
            
            models_info = {}
            
            for mapper in db.Model.registry.mappers:
                model_class = mapper.class_
                model_name = model_class.__name__
                
                model_info = {
                    'name': model_name,
                    'table': model_class.__tablename__ if hasattr(model_class, '__tablename__') else None,
                    'columns': [],
                    'relationships': []
                }
                
                for column in mapper.columns:
                    model_info['columns'].append({
                        'name': column.name,
                        'type': str(column.type),
                        'primary_key': column.primary_key,
                        'nullable': column.nullable,
                        'unique': column.unique
                    })
                
                for rel_name, relationship in mapper.relationships.items():
                    model_info['relationships'].append({
                        'name': rel_name,
                        'target': relationship.entity.class_.__name__,
                        'direction': relationship.direction.name,
                        'uselist': relationship.uselist
                    })
                
                models_info[f'model_{model_name}'] = model_info
                phase['models_analyzed'].append(model_name)
                phase['items_learned'] += 1
            
            self.knowledge_base.update(models_info)
            phase['discoveries'].append(f'Studied {len(models_info)} models with relationships')
            
        except Exception as e:
            phase['error'] = str(e)
        
        return phase
    
    def _study_forms_and_validations(self) -> Dict:
        phase = {
            'name': 'Forms and Validations Study',
            'items_learned': 0,
            'discoveries': [],
            'forms_found': []
        }
        
        try:
            forms_dir = Path('forms')
            if forms_dir.exists():
                for form_file in forms_dir.glob('*.py'):
                    if form_file.name != '__init__.py':
                        form_name = form_file.stem
                        
                        with open(form_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        self.knowledge_base[f'form_{form_name}'] = {
                            'file': str(form_file),
                            'content_hash': hashlib.md5(content.encode()).hexdigest(),
                            'size': len(content),
                            'last_modified': datetime.fromtimestamp(form_file.stat().st_mtime).isoformat()
                        }
                        
                        phase['forms_found'].append(form_name)
                        phase['items_learned'] += 1
                
                phase['discoveries'].append(f'Analyzed {len(phase["forms_found"])} forms')
        
        except Exception as e:
            phase['error'] = str(e)
        
        return phase
    
    def _study_business_logic(self) -> Dict:
        phase = {
            'name': 'Business Logic Study',
            'items_learned': 0,
            'discoveries': [],
            'routes_scanned': []
        }
        
        try:
            routes_dir = Path('routes')
            if routes_dir.exists():
                for route_file in routes_dir.glob('*.py'):
                    if route_file.name != '__init__.py':
                        route_name = route_file.stem
                        
                        with open(route_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        self.knowledge_base[f'business_logic_{route_name}'] = {
                            'file': str(route_file),
                            'content_hash': hashlib.md5(content.encode()).hexdigest(),
                            'size': len(content),
                            'functions_count': content.count('def '),
                            'routes_count': content.count('@'),
                            'last_modified': datetime.fromtimestamp(route_file.stat().st_mtime).isoformat()
                        }
                        
                        phase['routes_scanned'].append(route_name)
                        phase['items_learned'] += 1
                
                phase['discoveries'].append(f'Studied business logic in {len(phase["routes_scanned"])} route files')
        
        except Exception as e:
            phase['error'] = str(e)
        
        return phase
    
    def _detect_changes_from_last_session(self) -> Dict:
        phase = {
            'name': 'Change Detection',
            'items_learned': 0,
            'discoveries': [],
            'changes_found': []
        }
        
        snapshot_file = self.data_dir / 'last_snapshot.json'
        
        if snapshot_file.exists():
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    old_snapshot = json.load(f)
                
                for key, new_value in self.knowledge_base.items():
                    if key not in old_snapshot:
                        phase['changes_found'].append({
                            'type': 'NEW',
                            'key': key,
                            'description': f'New item added: {key}'
                        })
                        phase['items_learned'] += 1
                    
                    elif isinstance(new_value, dict) and isinstance(old_snapshot[key], dict):
                        if new_value.get('content_hash') != old_snapshot[key].get('content_hash'):
                            phase['changes_found'].append({
                                'type': 'MODIFIED',
                                'key': key,
                                'description': f'Item modified: {key}'
                            })
                            phase['items_learned'] += 1
                
                for key in old_snapshot:
                    if key not in self.knowledge_base:
                        phase['changes_found'].append({
                            'type': 'DELETED',
                            'key': key,
                            'description': f'Item removed: {key}'
                        })
                
                if phase['changes_found']:
                    phase['discoveries'].append(f'Detected {len(phase["changes_found"])} changes since last session')
                else:
                    phase['discoveries'].append('No changes detected - system is stable')
            
            except:
                pass
        else:
            phase['discoveries'].append('First learning session - building initial knowledge base')
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(self.knowledge_base, f, ensure_ascii=False, indent=2)
        
        self.changes_detected = phase['changes_found']
        
        return phase
    
    def _save_session(self, session: Dict):
        session_file = self.data_dir / f'session_{session["id"]}.json'
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
    
    def _update_knowledge_base(self):
        kb_file = self.data_dir / 'knowledge_base.json'
        
        with open(kb_file, 'w', encoding='utf-8') as f:
            json.dump(self.knowledge_base, f, ensure_ascii=False, indent=2)
    
    def get_learning_stats(self) -> Dict:
        return {
            'total_knowledge_items': len(self.knowledge_base),
            'total_sessions': len(self.learning_sessions),
            'last_session': self.learning_sessions[-1] if self.learning_sessions else None,
            'recent_changes': self.changes_detected[-20:] if self.changes_detected else []
        }
    
    def search_knowledge(self, query: str) -> List[Dict]:
        results = []
        query_lower = query.lower()
        
        for key, value in self.knowledge_base.items():
            if query_lower in key.lower():
                results.append({
                    'key': key,
                    'value': value,
                    'match_type': 'key'
                })
            elif isinstance(value, dict):
                if any(query_lower in str(v).lower() for v in value.values()):
                    results.append({
                        'key': key,
                        'value': value,
                        'match_type': 'value'
                    })
        
        return results[:50]


_continuous_learner = None

def get_continuous_learner():
    global _continuous_learner
    if _continuous_learner is None:
        _continuous_learner = ContinuousLearner()
    return _continuous_learner


__all__ = ['ContinuousLearner', 'get_continuous_learner']

