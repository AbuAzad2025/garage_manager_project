from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import re
from datetime import datetime


class BookReader:
    
    def __init__(self):
        self.books_dir = Path('AI/data/books')
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.memorized_books = {}
        self.book_index = {}
        self._load_index()
    
    def _load_index(self):
        index_file = self.books_dir / 'book_index.json'
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    self.book_index = json.load(f)
            except:
                pass
    
    def _save_index(self):
        index_file = self.books_dir / 'book_index.json'
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(self.book_index, f, ensure_ascii=False, indent=2)
    
    def read_markdown_book(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        
        if not path.exists():
            return {'success': False, 'error': 'File not found'}
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            book_data = {
                'title': path.stem,
                'file': str(path),
                'format': 'markdown',
                'read_date': datetime.now().isoformat(),
                'size': len(content),
                'chapters': [],
                'sections': [],
                'headings': [],
                'content_full': content,
                'key_concepts': []
            }
            
            lines = content.split('\n')
            current_chapter = None
            current_section = None
            
            for line in lines:
                if line.startswith('# '):
                    title = line[2:].strip()
                    current_chapter = {
                        'level': 1,
                        'title': title,
                        'content': []
                    }
                    book_data['chapters'].append(current_chapter)
                    book_data['headings'].append({'level': 1, 'text': title})
                
                elif line.startswith('## '):
                    title = line[3:].strip()
                    current_section = {
                        'level': 2,
                        'title': title,
                        'content': []
                    }
                    book_data['sections'].append(current_section)
                    book_data['headings'].append({'level': 2, 'text': title})
                    
                    if current_chapter:
                        current_chapter['content'].append(current_section)
                
                elif line.startswith('### '):
                    title = line[4:].strip()
                    book_data['headings'].append({'level': 3, 'text': title})
                
                else:
                    if current_section:
                        current_section['content'].append(line)
                    elif current_chapter:
                        current_chapter['content'].append(line)
            
            code_blocks = re.findall(r'```[\s\S]*?```', content)
            book_data['code_examples_count'] = len(code_blocks)
            
            important_patterns = [
                r'\*\*(.+?)\*\*',
                r'__(.+?)__',
                r'> (.+)',
                r'- (.+)'
            ]
            
            for pattern in important_patterns:
                matches = re.findall(pattern, content)
                book_data['key_concepts'].extend(matches[:50])
            
            book_id = f'book_{path.stem}'
            self.memorized_books[book_id] = book_data
            
            self.book_index[book_id] = {
                'title': book_data['title'],
                'file': str(path),
                'format': 'markdown',
                'chapters_count': len(book_data['chapters']),
                'sections_count': len(book_data['sections']),
                'size': book_data['size'],
                'read_date': book_data['read_date']
            }
            
            self._save_index()
            self._save_book_memory(book_id, book_data)
            
            return {
                'success': True,
                'book_id': book_id,
                'title': book_data['title'],
                'chapters': len(book_data['chapters']),
                'sections': len(book_data['sections']),
                'key_concepts': len(book_data['key_concepts'])
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def read_pdf_book(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        
        if not path.exists():
            return {'success': False, 'error': 'File not found'}
        
        try:
            try:
                import PyPDF2
            except ImportError:
                return {
                    'success': False,
                    'error': 'PyPDF2 not installed. Install with: pip install PyPDF2'
                }
            
            book_data = {
                'title': path.stem,
                'file': str(path),
                'format': 'pdf',
                'read_date': datetime.now().isoformat(),
                'pages': [],
                'total_pages': 0,
                'content_full': '',
                'key_terms': []
            }
            
            with open(path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                book_data['total_pages'] = len(pdf_reader.pages)
                
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()
                    
                    book_data['pages'].append({
                        'page_number': page_num,
                        'content': text,
                        'word_count': len(text.split())
                    })
                    
                    book_data['content_full'] += text + '\n'
            
            words = book_data['content_full'].split()
            word_freq = {}
            for word in words:
                clean_word = re.sub(r'[^\w\u0600-\u06FF]', '', word).lower()
                if len(clean_word) > 3:
                    word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
            
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            book_data['key_terms'] = [word for word, freq in sorted_words[:100]]
            
            book_id = f'book_{path.stem}'
            self.memorized_books[book_id] = book_data
            
            self.book_index[book_id] = {
                'title': book_data['title'],
                'file': str(path),
                'format': 'pdf',
                'pages': book_data['total_pages'],
                'size': len(book_data['content_full']),
                'read_date': book_data['read_date']
            }
            
            self._save_index()
            self._save_book_memory(book_id, book_data)
            
            return {
                'success': True,
                'book_id': book_id,
                'title': book_data['title'],
                'pages': book_data['total_pages'],
                'key_terms': len(book_data['key_terms'])
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _save_book_memory(self, book_id: str, book_data: Dict):
        memory_file = self.books_dir / f'{book_id}_memory.json'
        
        memory_data = {k: v for k, v in book_data.items() if k != 'content_full'}
        
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        
        content_file = self.books_dir / f'{book_id}_content.txt'
        with open(content_file, 'w', encoding='utf-8') as f:
            f.write(book_data['content_full'])
    
    def search_in_books(self, query: str) -> List[Dict]:
        results = []
        query_lower = query.lower()
        
        for book_id, book_info in self.book_index.items():
            content_file = self.books_dir / f'{book_id}_content.txt'
            
            if content_file.exists():
                try:
                    with open(content_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if query_lower in content.lower():
                        lines = content.split('\n')
                        matching_lines = [
                            line for line in lines 
                            if query_lower in line.lower()
                        ][:10]
                        
                        results.append({
                            'book_id': book_id,
                            'book_title': book_info['title'],
                            'matches_count': len(matching_lines),
                            'sample_matches': matching_lines[:5]
                        })
                except:
                    pass
        
        return results
    
    def answer_from_books(self, question: str) -> Optional[str]:
        search_results = self.search_in_books(question)
        
        if not search_results:
            return None
        
        answer_parts = []
        answer_parts.append(f"من الكتب المحفوظة ({len(search_results)} مصدر):\n")
        
        for result in search_results[:3]:
            answer_parts.append(f"\n📖 {result['book_title']}:")
            
            for match in result['sample_matches'][:3]:
                clean_match = match.strip()
                if clean_match:
                    answer_parts.append(f"  - {clean_match}")
        
        return '\n'.join(answer_parts)
    
    def get_books_summary(self) -> Dict:
        return {
            'total_books': len(self.book_index),
            'formats': {
                'markdown': sum(1 for b in self.book_index.values() if b['format'] == 'markdown'),
                'pdf': sum(1 for b in self.book_index.values() if b['format'] == 'pdf')
            },
            'books': list(self.book_index.values())
        }


_book_reader = None

def get_book_reader():
    global _book_reader
    if _book_reader is None:
        _book_reader = BookReader()
    return _book_reader


__all__ = ['BookReader', 'get_book_reader']

