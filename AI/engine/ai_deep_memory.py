from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from pathlib import Path
import hashlib


class DeepMemory:
    
    def __init__(self):
        self.memory_dir = Path('AI/data/deep_memory')
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.short_term_memory = {}
        self.long_term_memory = {}
        self.semantic_memory = {}
        self.procedural_memory = {}
        self.episodic_memory = []
        
        self._load_all_memories()
    
    def _load_all_memories(self):
        ltm_file = self.memory_dir / 'long_term_memory.json'
        if ltm_file.exists():
            try:
                with open(ltm_file, 'r', encoding='utf-8') as f:
                    self.long_term_memory = json.load(f)
            except Exception:
                pass
        
        sem_file = self.memory_dir / 'semantic_memory.json'
        if sem_file.exists():
            try:
                with open(sem_file, 'r', encoding='utf-8') as f:
                    self.semantic_memory = json.load(f)
            except Exception:
                pass
        
        proc_file = self.memory_dir / 'procedural_memory.json'
        if proc_file.exists():
            try:
                with open(proc_file, 'r', encoding='utf-8') as f:
                    self.procedural_memory = json.load(f)
            except Exception:
                pass
    
    def remember_fact(self, category: str, key: str, value: Any, importance: int = 5):
        memory_id = hashlib.md5(f'{category}_{key}'.encode()).hexdigest()
        
        memory_entry = {
            'id': memory_id,
            'category': category,
            'key': key,
            'value': value,
            'importance': importance,
            'created_at': datetime.now().isoformat(),
            'access_count': 0,
            'last_accessed': None
        }
        
        self.short_term_memory[memory_id] = memory_entry
        
        if importance >= 7:
            self.long_term_memory[memory_id] = memory_entry
            self._save_long_term_memory()
    
    def remember_concept(self, concept: str, definition: str, examples: List[str] = None, related: List[str] = None):
        concept_id = hashlib.md5(concept.encode()).hexdigest()
        
        self.semantic_memory[concept_id] = {
            'concept': concept,
            'definition': definition,
            'examples': examples or [],
            'related_concepts': related or [],
            'created_at': datetime.now().isoformat(),
            'mastery_level': 0
        }
        
        self._save_semantic_memory()
    
    def remember_procedure(self, name: str, steps: List[str], context: Dict = None):
        proc_id = hashlib.md5(name.encode()).hexdigest()
        
        self.procedural_memory[proc_id] = {
            'name': name,
            'steps': steps,
            'context': context or {},
            'times_executed': 0,
            'success_rate': 0.0,
            'created_at': datetime.now().isoformat()
        }
        
        self._save_procedural_memory()
    
    def remember_experience(self, event: str, outcome: str, lessons_learned: List[str]):
        experience = {
            'event': event,
            'outcome': outcome,
            'lessons_learned': lessons_learned,
            'timestamp': datetime.now().isoformat()
        }
        
        self.episodic_memory.append(experience)
        
        if len(self.episodic_memory) > 1000:
            self.episodic_memory = self.episodic_memory[-1000:]
        
        self._save_episodic_memory()
    
    def recall_fact(self, key: str = None, category: str = None) -> Optional[Dict]:
        for memory_id, memory in {**self.long_term_memory, **self.short_term_memory}.items():
            if key and memory['key'] == key:
                memory['access_count'] += 1
                memory['last_accessed'] = datetime.now().isoformat()
                return memory
            
            if category and memory['category'] == category:
                memory['access_count'] += 1
                memory['last_accessed'] = datetime.now().isoformat()
                return memory
        
        return None
    
    def recall_concept(self, concept: str) -> Optional[Dict]:
        concept_lower = concept.lower()
        
        for concept_id, data in self.semantic_memory.items():
            if concept_lower in data['concept'].lower():
                data['mastery_level'] += 1
                self._save_semantic_memory()
                return data
        
        return None
    
    def recall_procedure(self, name: str) -> Optional[Dict]:
        name_lower = name.lower()
        
        for proc_id, proc in self.procedural_memory.items():
            if name_lower in proc['name'].lower():
                proc['times_executed'] += 1
                self._save_procedural_memory()
                return proc
        
        return None
    
    def recall_similar_experiences(self, query: str, limit: int = 5) -> List[Dict]:
        query_lower = query.lower()
        
        similar = []
        for exp in self.episodic_memory:
            if query_lower in exp['event'].lower() or query_lower in exp['outcome'].lower():
                similar.append(exp)
        
        return similar[-limit:]
    
    def consolidate_memory(self):
        consolidated = 0
        
        for mem_id, memory in list(self.short_term_memory.items()):
            if memory['access_count'] >= 3 or memory['importance'] >= 7:
                self.long_term_memory[mem_id] = memory
                consolidated += 1
        
        if consolidated > 0:
            self._save_long_term_memory()
        
        return consolidated
    
    def get_memory_stats(self) -> Dict:
        return {
            'short_term': len(self.short_term_memory),
            'long_term': len(self.long_term_memory),
            'semantic': len(self.semantic_memory),
            'procedural': len(self.procedural_memory),
            'episodic': len(self.episodic_memory),
            'total': (
                len(self.short_term_memory) + 
                len(self.long_term_memory) + 
                len(self.semantic_memory) + 
                len(self.procedural_memory) + 
                len(self.episodic_memory)
            )
        }
    
    def search_all_memories(self, query: str) -> Dict[str, List]:
        query_lower = query.lower()
        
        results = {
            'facts': [],
            'concepts': [],
            'procedures': [],
            'experiences': []
        }
        
        for memory in {**self.long_term_memory, **self.short_term_memory}.values():
            if query_lower in str(memory.get('value', '')).lower() or query_lower in memory.get('key', '').lower():
                results['facts'].append(memory)
        
        for concept in self.semantic_memory.values():
            if query_lower in concept['concept'].lower() or query_lower in concept['definition'].lower():
                results['concepts'].append(concept)
        
        for proc in self.procedural_memory.values():
            if query_lower in proc['name'].lower():
                results['procedures'].append(proc)
        
        for exp in self.episodic_memory:
            if query_lower in exp['event'].lower() or query_lower in exp['outcome'].lower():
                results['experiences'].append(exp)
        
        for key in results:
            results[key] = results[key][:10]
        
        return results
    
    def _save_long_term_memory(self):
        ltm_file = self.memory_dir / 'long_term_memory.json'
        with open(ltm_file, 'w', encoding='utf-8') as f:
            json.dump(self.long_term_memory, f, ensure_ascii=False, indent=2)
    
    def _save_semantic_memory(self):
        sem_file = self.memory_dir / 'semantic_memory.json'
        with open(sem_file, 'w', encoding='utf-8') as f:
            json.dump(self.semantic_memory, f, ensure_ascii=False, indent=2)
    
    def _save_procedural_memory(self):
        proc_file = self.memory_dir / 'procedural_memory.json'
        with open(proc_file, 'w', encoding='utf-8') as f:
            json.dump(self.procedural_memory, f, ensure_ascii=False, indent=2)
    
    def _save_episodic_memory(self):
        ep_file = self.memory_dir / 'episodic_memory.json'
        with open(ep_file, 'w', encoding='utf-8') as f:
            json.dump(self.episodic_memory, f, ensure_ascii=False, indent=2)


_deep_memory = None

def get_deep_memory():
    global _deep_memory
    if _deep_memory is None:
        _deep_memory = DeepMemory()
    return _deep_memory


__all__ = ['DeepMemory', 'get_deep_memory']

