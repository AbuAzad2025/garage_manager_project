#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص شامل لجميع Event Listeners في النظام
"""

import os
import re
from collections import defaultdict

def check_js_event_listeners(filepath):
    """فحص JavaScript Event Listeners"""
    listeners = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Patterns for different event listener types
        patterns = [
            # addEventListener
            (r"addEventListener\(['\"](\w+)['\"]", "addEventListener"),
            # jQuery on()
            (r"\$\([^)]+\)\.on\(['\"](\w+)['\"]", "jQuery.on"),
            # jQuery click(), submit(), etc
            (r"\$\([^)]+\)\.(click|submit|change|keyup|keydown|focus|blur|hover)\(", "jQuery.method"),
            # onclick, onsubmit attributes in HTML
            (r"on(click|submit|change|keyup|keydown|load|focus|blur)=", "inline"),
            # document.getElementById(...).onclick
            (r"\.on(click|submit|change|keyup|keydown|load|focus|blur)\s*=", "property"),
        ]
        
        for pattern, listener_type in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                event_name = match.group(1) if match.lastindex else 'unknown'
                listeners.append({
                    'event': event_name,
                    'type': listener_type,
                    'file': os.path.basename(filepath)
                })
    
    except Exception as e:
        pass
    
    return listeners

def check_python_signals(filepath):
    """فحص Python Event Listeners (Signals)"""
    signals = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # SQLAlchemy event listeners
        patterns = [
            (r"@event\.listens_for\(([^)]+)\)", "SQLAlchemy event.listens_for"),
            (r"event\.listen\(([^)]+)\)", "SQLAlchemy event.listen"),
            (r"@(\w+)\.listens_for\(", "SQLAlchemy model event"),
            # Flask signals
            (r"(\w+_signal)\.connect\(", "Flask signal.connect"),
            (r"@(\w+_signal)\.connect_via\(", "Flask signal decorator"),
        ]
        
        for pattern, signal_type in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                target = match.group(1) if match.lastindex else 'unknown'
                signals.append({
                    'target': target,
                    'type': signal_type,
                    'file': os.path.basename(filepath)
                })
    
    except Exception as e:
        pass
    
    return signals

def check_template_event_handlers(filepath):
    """فحص Event Handlers في Templates"""
    handlers = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inline event handlers
        pattern = r'on(click|submit|change|keyup|keydown|load|focus|blur|mouseenter|mouseleave)=["\']([^"\']+)["\']'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        
        for match in matches:
            event_name = match.group(1)
            handler_code = match.group(2)[:50]  # First 50 chars
            handlers.append({
                'event': event_name,
                'handler': handler_code,
                'file': os.path.basename(filepath)
            })
    
    except Exception as e:
        pass
    
    return handlers

def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║       🎧 فحص شامل لجميع Event Listeners في النظام       ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")
    
    # JavaScript Event Listeners
    print("📂 فحص JavaScript Event Listeners...")
    print("━" * 60)
    
    js_listeners = []
    js_dir = 'static/js'
    
    if os.path.exists(js_dir):
        for filename in os.listdir(js_dir):
            if filename.endswith('.js'):
                filepath = os.path.join(js_dir, filename)
                listeners = check_js_event_listeners(filepath)
                if listeners:
                    print(f"✅ {filename:<30} → {len(listeners):>3} listeners")
                    js_listeners.extend(listeners)
    
    # Check base.html for inline listeners
    if os.path.exists('templates/base.html'):
        listeners = check_js_event_listeners('templates/base.html')
        if listeners:
            print(f"✅ {'base.html':<30} → {len(listeners):>3} listeners")
            js_listeners.extend(listeners)
    
    print(f"\n📊 إجمالي JS Listeners: {len(js_listeners)}\n")
    
    # Python Event Listeners
    print("📂 فحص Python Event Listeners (Signals)...")
    print("━" * 60)
    
    py_signals = []
    
    # Check models.py
    if os.path.exists('models.py'):
        signals = check_python_signals('models.py')
        if signals:
            print(f"✅ {'models.py':<30} → {len(signals):>3} signals")
            py_signals.extend(signals)
    
    # Check routes
    routes_dir = 'routes'
    if os.path.exists(routes_dir):
        for filename in os.listdir(routes_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(routes_dir, filename)
                signals = check_python_signals(filepath)
                if signals:
                    print(f"✅ {filename:<30} → {len(signals):>3} signals")
                    py_signals.extend(signals)
    
    print(f"\n📊 إجمالي Python Signals: {len(py_signals)}\n")
    
    # Template Event Handlers
    print("📂 فحص Template Event Handlers...")
    print("━" * 60)
    
    template_handlers = []
    templates_dir = 'templates'
    
    if os.path.exists(templates_dir):
        count = 0
        for root, dirs, files in os.walk(templates_dir):
            for filename in files:
                if filename.endswith('.html'):
                    filepath = os.path.join(root, filename)
                    handlers = check_template_event_handlers(filepath)
                    if handlers:
                        count += 1
                        template_handlers.extend(handlers)
        
        print(f"✅ تم فحص {count} ملف HTML")
        print(f"📊 إجمالي Template Handlers: {len(template_handlers)}\n")
    
    # تحليل JS Events
    print("📈 تحليل JavaScript Events:")
    print("━" * 60)
    
    js_events_count = defaultdict(int)
    for listener in js_listeners:
        js_events_count[listener['event']] += 1
    
    top_events = sorted(js_events_count.items(), key=lambda x: x[1], reverse=True)[:10]
    for event, count in top_events:
        print(f"  {event:<20} × {count}")
    
    # تحليل Event Types
    print("\n📊 أنواع Event Listeners:")
    print("━" * 60)
    
    listener_types = defaultdict(int)
    for listener in js_listeners:
        listener_types[listener['type']] += 1
    
    for ltype, count in sorted(listener_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ltype:<30} × {count}")
    
    # تحليل Template Events
    if template_handlers:
        print("\n📊 Template Inline Handlers (Top 10):")
        print("━" * 60)
        
        template_events = defaultdict(int)
        for handler in template_handlers:
            template_events[handler['event']] += 1
        
        top_template = sorted(template_events.items(), key=lambda x: x[1], reverse=True)[:10]
        for event, count in top_template:
            print(f"  on{event:<18} × {count}")
    
    # فحص Potential Issues
    print("\n⚠️  فحص المشاكل المحتملة:")
    print("━" * 60)
    
    issues = []
    
    # Check for too many inline handlers in templates
    if len(template_handlers) > 50:
        issues.append(f"⚠️  عدد كبير من inline handlers في templates ({len(template_handlers)})")
        issues.append("   → يُفضل نقلها إلى ملفات JS منفصلة")
    
    # Check for addEventListener without removeEventListener
    addEventListener_count = sum(1 for l in js_listeners if l['type'] == 'addEventListener')
    if addEventListener_count > 100:
        issues.append(f"⚠️  عدد كبير من addEventListener ({addEventListener_count})")
        issues.append("   → تأكد من استخدام removeEventListener لمنع memory leaks")
    
    if not issues:
        print("✅ لا توجد مشاكل ظاهرة")
    else:
        for issue in issues:
            print(issue)
    
    # Best Practices
    print("\n💡 توصيات Best Practices:")
    print("━" * 60)
    
    recommendations = []
    
    # Event Delegation
    if len(template_handlers) > 30:
        recommendations.append("✨ استخدم Event Delegation لتقليل عدد الـ handlers")
    
    # Separate concerns
    if len(template_handlers) > 20:
        recommendations.append("✨ انقل inline handlers من templates إلى ملفات JS")
    
    # Memory management
    if addEventListener_count > 50:
        recommendations.append("✨ تأكد من cleanup للـ event listeners عند إزالة العناصر")
    
    # jQuery modernization
    jquery_methods = sum(1 for l in js_listeners if 'jQuery' in l['type'])
    if jquery_methods > 50:
        recommendations.append("✨ فكر في استخدام vanilla JavaScript بدلاً من jQuery")
    
    if recommendations:
        for rec in recommendations:
            print(rec)
    else:
        print("✅ النظام يتبع best practices")
    
    # حفظ التقرير
    report_file = 'EVENT_LISTENERS_REPORT.txt'
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("  تقرير شامل لجميع Event Listeners في النظام\n")
            f.write("═" * 70 + "\n\n")
            
            f.write(f"JavaScript Listeners: {len(js_listeners)}\n")
            f.write(f"Python Signals: {len(py_signals)}\n")
            f.write(f"Template Handlers: {len(template_handlers)}\n\n")
            
            f.write("━" * 70 + "\n")
            f.write("JavaScript Events (Top 20):\n")
            f.write("━" * 70 + "\n\n")
            
            for event, count in top_events:
                f.write(f"  {event:<25} × {count}\n")
            
            f.write("\n" + "━" * 70 + "\n")
            f.write("JavaScript Files:\n")
            f.write("━" * 70 + "\n\n")
            
            files_count = defaultdict(int)
            for listener in js_listeners:
                files_count[listener['file']] += 1
            
            for file, count in sorted(files_count.items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {file:<40} → {count:>3} listeners\n")
        
        print(f"\n💾 تم حفظ التقرير المفصل في: {report_file}")
        
    except Exception as e:
        print(f"\n❌ خطأ في حفظ التقرير: {e}")
    
    print("\n" + "═" * 60)
    print("✅ اكتمل الفحص بنجاح")
    print("═" * 60)

if __name__ == '__main__':
    main()

