"""
🌐 AI Web Expert - خبير HTML, CSS, JavaScript
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تحليل وتحسين HTML
- تحليل وتحسين CSS
- تحليل وتحسين JavaScript
- اكتشاف مشاكل Accessibility
- اكتشاف مشاكل Performance
- Security في Frontend

Created: 2025-11-01
Version: Web Expert 1.0 - MASTER LEVEL
"""

from typing import Dict, List, Any, Optional
import re


# ═══════════════════════════════════════════════════════════════════════════
# 🌐 WEB EXPERT ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class WebExpert:
    """
    خبير تطوير ويب عبقري
    
    القدرات:
    1. HTML Expert - تحليل وتحسين
    2. CSS Expert - optimization
    3. JavaScript Expert - debugging & optimization
    4. Accessibility Expert (a11y)
    5. Performance Expert
    6. Security Expert (XSS, CSRF)
    """
    
    def __init__(self):
        self.html_best_practices = self._load_html_best_practices()
        self.js_best_practices = self._load_js_best_practices()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📄 HTML EXPERT
    # ═══════════════════════════════════════════════════════════════════════
    
    def analyze_html(self, html_content: str) -> Dict[str, Any]:
        """تحليل HTML"""
        analysis = {
            'issues': [],
            'accessibility_score': 100,
            'seo_score': 100,
            'performance_score': 100,
            'recommendations': []
        }
        
        # فحص DOCTYPE
        if not html_content.strip().startswith('<!DOCTYPE'):
            analysis['issues'].append({
                'type': 'missing_doctype',
                'severity': 'medium',
                'message': 'لا يوجد DOCTYPE',
                'fix': 'أضف <!DOCTYPE html> في البداية'
            })
            analysis['seo_score'] -= 5
        
        # فحص <html lang="">
        if 'lang=' not in html_content[:200]:
            analysis['issues'].append({
                'type': 'missing_lang',
                'severity': 'medium',
                'message': 'لا يوجد lang attribute في <html>',
                'fix': '<html lang="ar"> أو lang="en"'
            })
            analysis['accessibility_score'] -= 10
        
        # فحص <title>
        if '<title>' not in html_content.lower():
            analysis['issues'].append({
                'type': 'missing_title',
                'severity': 'high',
                'message': 'لا يوجد <title>',
                'fix': 'أضف <title>اسم الصفحة</title> في <head>'
            })
            analysis['seo_score'] -= 20
        
        # فحص alt في images
        img_without_alt = len(re.findall(r'<img\s+(?![^>]*alt=)[^>]*>', html_content))
        if img_without_alt > 0:
            analysis['issues'].append({
                'type': 'missing_alt',
                'severity': 'high',
                'message': f'{img_without_alt} صورة بدون alt',
                'fix': 'أضف alt="وصف الصورة" لكل <img>'
            })
            analysis['accessibility_score'] -= img_without_alt * 5
        
        # فحص inline styles
        inline_styles_count = html_content.count('style=')
        if inline_styles_count > 5:
            analysis['recommendations'].append(
                f'هناك {inline_styles_count} inline style - استخدم CSS خارجي'
            )
            analysis['performance_score'] -= 5
        
        # فحص semantic HTML
        if '<div' in html_content and '<section' not in html_content:
            analysis['recommendations'].append(
                'استخدم semantic HTML: <section>, <article>, <nav>, <header>, <footer>'
            )
        
        # فحص ARIA labels للعناصر التفاعلية
        buttons = len(re.findall(r'<button[^>]*>', html_content))
        aria_labels = len(re.findall(r'aria-label=', html_content))
        
        if buttons > aria_labels + 2:
            analysis['recommendations'].append(
                'أضف aria-label للـ buttons بدون نص واضح'
            )
        
        # فحص form accessibility
        if '<form' in html_content:
            inputs = len(re.findall(r'<input[^>]*>', html_content))
            labels = len(re.findall(r'<label[^>]*>', html_content))
            
            if inputs > labels:
                analysis['issues'].append({
                    'type': 'missing_labels',
                    'severity': 'high',
                    'message': f'{inputs - labels} input بدون <label>',
                    'fix': 'أضف <label> لكل input'
                })
                analysis['accessibility_score'] -= 15
        
        return analysis
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎨 CSS EXPERT
    # ═══════════════════════════════════════════════════════════════════════
    
    def analyze_css(self, css_content: str) -> Dict[str, Any]:
        """تحليل CSS"""
        analysis = {
            'issues': [],
            'performance_tips': [],
            'organization_tips': []
        }
        
        # فحص !important
        important_count = css_content.count('!important')
        if important_count > 5:
            analysis['issues'].append({
                'type': 'too_many_important',
                'severity': 'medium',
                'message': f'{important_count} استخدام لـ !important',
                'fix': 'تجنب !important - استخدم specificity أفضل'
            })
        
        # فحص IDs في selectors
        id_selectors = len(re.findall(r'#\w+\s*{', css_content))
        if id_selectors > 10:
            analysis['organization_tips'].append(
                f'{id_selectors} selector باستخدام ID - استخدم classes للتكرار'
            )
        
        # فحص vendor prefixes غير ضرورية
        if '-webkit-' in css_content or '-moz-' in css_content:
            analysis['performance_tips'].append(
                'استخدم autoprefixer بدلاً من كتابة vendor prefixes يدوياً'
            )
        
        # فحص colors غير متسقة
        colors = re.findall(r'#[0-9a-fA-F]{3,6}', css_content)
        if len(set(colors)) > 20:
            analysis['organization_tips'].append(
                f'{len(set(colors))} لون مختلف - استخدم CSS variables للألوان'
            )
        
        # فحص font sizes غير متسقة
        font_sizes = re.findall(r'font-size:\s*(\d+(?:\.\d+)?(?:px|rem|em))', css_content)
        if len(set(font_sizes)) > 10:
            analysis['organization_tips'].append(
                'أحجام خطوط كثيرة - استخدم type scale محدد'
            )
        
        return analysis
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📜 JAVASCRIPT EXPERT
    # ═══════════════════════════════════════════════════════════════════════
    
    def analyze_javascript(self, js_content: str) -> Dict[str, Any]:
        """تحليل JavaScript"""
        analysis = {
            'issues': [],
            'performance_tips': [],
            'security_tips': [],
            'modern_js_tips': []
        }
        
        # فحص var (قديم)
        var_count = len(re.findall(r'\bvar\s+\w+', js_content))
        if var_count > 0:
            analysis['modern_js_tips'].append(
                f'{var_count} استخدام لـ var - استخدم let/const بدلاً منها'
            )
        
        # فحص eval (خطر أمني)
        if 'eval(' in js_content:
            analysis['security_tips'].append({
                'type': 'dangerous_eval',
                'severity': 'critical',
                'message': 'استخدام eval() - خطر أمني كبير',
                'fix': 'تجنب eval() تماماً - استخدم بدائل آمنة'
            })
        
        # فحص innerHTML (XSS risk)
        if 'innerHTML' in js_content and '+' in js_content:
            analysis['security_tips'].append({
                'type': 'xss_risk',
                'severity': 'high',
                'message': 'استخدام innerHTML مع string concatenation',
                'fix': 'استخدم textContent أو sanitize البيانات'
            })
        
        # فحص == بدل ===
        loose_equality = len(re.findall(r'[^=!]=[^=]', js_content))
        if loose_equality > 3:
            analysis['issues'].append({
                'type': 'loose_equality',
                'severity': 'medium',
                'message': 'استخدام == بدل ===',
                'fix': 'استخدم === و !== للمقارنة الصارمة'
            })
        
        # فحص global variables
        if re.search(r'^\s*var\s+\w+\s*=', js_content, re.MULTILINE):
            analysis['modern_js_tips'].append(
                'تجنب global variables - استخدم modules أو IIFE'
            )
        
        # فحص callback hell
        callback_depth = self._detect_callback_hell(js_content)
        if callback_depth > 3:
            analysis['modern_js_tips'].append(
                f'Callback hell detected (depth: {callback_depth}) - استخدم Promises أو async/await'
            )
        
        # فحص console.log في production
        console_count = js_content.count('console.log')
        if console_count > 5:
            analysis['performance_tips'].append(
                f'{console_count} console.log - احذفها في production'
            )
        
        # فحص عدم استخدام strict mode
        if "'use strict'" not in js_content and '"use strict"' not in js_content:
            analysis['modern_js_tips'].append(
                'أضف "use strict"; في بداية الملف'
            )
        
        # فحص arrow functions
        if 'function(' in js_content and '=>' not in js_content:
            analysis['modern_js_tips'].append(
                'استخدم arrow functions: () => {} عندما مناسب'
            )
        
        return analysis
    
    def _detect_callback_hell(self, js_content: str) -> int:
        """اكتشاف عمق callback hell"""
        # حساب عمق الـ callbacks المتداخلة
        max_depth = 0
        current_depth = 0
        
        for char in js_content:
            if char == '{':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char == '}':
                current_depth -= 1
        
        return max_depth // 3  # تقريبي
    
    def suggest_js_refactoring(self, old_js: str) -> Dict[str, str]:
        """اقتراح إعادة كتابة JS بشكل أفضل"""
        suggestions = {}
        
        # تحويل var لـ const/let
        if 'var ' in old_js:
            suggestions['var_to_const'] = old_js.replace('var ', 'const ')
        
        # تحويل callbacks لـ async/await
        if '.then(' in old_js:
            suggestions['use_async_await'] = '''
// بدلاً من:
fetch(url)
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error(error));

// استخدم:
async function fetchData() {
  try {
    const response = await fetch(url);
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}
            '''
        
        return suggestions
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔒 SECURITY EXPERT
    # ═══════════════════════════════════════════════════════════════════════
    
    def check_security(self, code: str, code_type: str) -> List[Dict]:
        """فحص أمني شامل"""
        security_issues = []
        
        if code_type == 'html':
            # فحص XSS
            if '{{' in code and '|safe' in code:
                security_issues.append({
                    'type': 'xss_risk',
                    'severity': 'critical',
                    'message': 'استخدام |safe في Jinja2 - خطر XSS',
                    'fix': 'احذف |safe أو استخدم |escape'
                })
            
            # فحص CSRF
            if '<form' in code and 'csrf_token' not in code:
                security_issues.append({
                    'type': 'missing_csrf',
                    'severity': 'high',
                    'message': 'Form بدون CSRF token',
                    'fix': 'أضف {{ csrf_token() }} داخل الفورم'
                })
        
        elif code_type == 'javascript':
            # فحص localStorage للبيانات الحساسة
            if 'localStorage' in code and ('password' in code or 'token' in code):
                security_issues.append({
                    'type': 'sensitive_data_in_localstorage',
                    'severity': 'high',
                    'message': 'تخزين بيانات حساسة في localStorage',
                    'fix': 'استخدم httpOnly cookies أو sessionStorage'
                })
        
        return security_issues
    
    def _load_html_best_practices(self) -> List[str]:
        """تحميل أفضل ممارسات HTML"""
        return [
            'استخدم semantic HTML5 elements',
            'أضف alt لكل صورة',
            'استخدم <label> لكل <input>',
            'أضف lang attribute',
            'استخدم proper heading hierarchy (h1->h6)',
            'تجنب inline styles',
            'استخدم ARIA attributes عند الحاجة'
        ]
    
    def _load_js_best_practices(self) -> List[str]:
        """تحميل أفضل ممارسات JavaScript"""
        return [
            'استخدم const/let بدلاً من var',
            'استخدم === بدلاً من ==',
            'استخدم async/await بدلاً من callbacks',
            'تجنب eval()',
            'استخدم strict mode',
            'استخدم arrow functions',
            'استخدم template literals',
            'استخدم destructuring',
            'استخدم modules (import/export)',
            'احذف console.log في production'
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_web_expert = None

def get_web_expert() -> WebExpert:
    """الحصول على خبير Web (Singleton)"""
    global _web_expert
    
    if _web_expert is None:
        _web_expert = WebExpert()
    
    return _web_expert


__all__ = [
    'WebExpert',
    'get_web_expert'
]

