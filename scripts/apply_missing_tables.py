#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""تطبيق الجداول المفقودة"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db

app = create_app()

with app.app_context():
    with open('scripts/create_missing_tables.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]
    
    for stmt in statements:
        if stmt and 'SELECT' not in stmt.upper():
            try:
                db.session.execute(db.text(stmt))
            except Exception as e:
                print(f"⚠️ {e}")
    
    db.session.commit()
    print('✅ تم تنفيذ SQL بنجاح')

