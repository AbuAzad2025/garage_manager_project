#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db

app = create_app()

with app.app_context():
    # sites table
    db.session.execute(db.text("""
    CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_id INTEGER NOT NULL,
        name VARCHAR(120) NOT NULL,
        code VARCHAR(32) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        address VARCHAR(200),
        geo_lat NUMERIC(10, 6),
        geo_lng NUMERIC(10, 6),
        manager_user_id INTEGER,
        notes TEXT,
        is_archived BOOLEAN NOT NULL DEFAULT 0,
        archived_at DATETIME,
        archived_by INTEGER,
        archive_reason VARCHAR(200),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE,
        FOREIGN KEY (manager_user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY (archived_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """))
    
    # user_branches table
    db.session.execute(db.text("""
    CREATE TABLE IF NOT EXISTS user_branches (
        user_id INTEGER NOT NULL,
        branch_id INTEGER NOT NULL,
        is_primary BOOLEAN NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, branch_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
    )
    """))
    
    db.session.commit()
    print('✅ تم إنشاء جداول sites و user_branches')

