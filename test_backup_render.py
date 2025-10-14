#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار عرض صفحة النسخ الاحتياطي"""

from app import create_app
from flask import url_for
from flask_login import login_user
from models import User

app = create_app()

with app.app_context():
    print("🔍 اختبار عرض المحتوى...")
    print("-" * 60)
    
    user = User.query.filter_by(id=1).first()
    
    with app.test_request_context():
        if user:
            login_user(user)
        
        # قراءة القالب
        import os
        template_path = os.path.join(app.root_path, 'templates', 'advanced', 'backup_manager.html')
        
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # فحص العناصر الأساسية
        checks = {
            'tab-pane backups': 'id="backups"' in content,
            'tab-pane schedule': 'id="schedule"' in content,
            'tab-pane convert': 'id="convert"' in content,
            'active class': 'active show' in content,
            'CSS fix': '.tab-content > .active' in content,
            'jQuery init': '$(document).ready' in content,
            'data-toggle': 'data-toggle="tab"' in content,
            'نسخة احتياطية جديدة': 'نسخة احتياطية جديدة' in content,
            'Connection String': 'Connection String' in content,
        }
        
        print("\n📋 فحص العناصر:")
        for check_name, result in checks.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check_name}")
        
        all_passed = all(checks.values())
        
        # فحص عدد tab-pane
        tab_panes = content.count('class="tab-pane')
        print(f"\n📊 عدد التبويبات: {tab_panes}")
        
        # فحص active tabs
        active_tabs = content.count('active show')
        print(f"📊 عدد التبويبات النشطة: {active_tabs}")
        
        print("\n" + "=" * 60)
        if all_passed and tab_panes == 3 and active_tabs >= 1:
            print("🎉 القالب صحيح ويجب أن يعمل!")
        else:
            print("⚠️ قد توجد مشكلة")

print("\n✅ انتهى الاختبار")

