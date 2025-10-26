#!/usr/bin/env python3.10
# -*- coding: utf-8 -*-
"""
فحص أرصدة العملاء على PythonAnywhere
"""
from app import create_app, db
from models import Customer

app = create_app()
with app.app_context():
    print("=" * 80)
    print("فحص أرصدة العملاء على PythonAnywhere")
    print("=" * 80)
    print()
    
    customers = Customer.query.order_by(Customer.id).all()
    
    for c in customers:
        balance = c.balance
        print(f"ID: {c.id}")
        print(f"الاسم: {c.name}")
        print(f"الرصيد: {balance:,.2f}")
        print(f"الرصيد الافتتاحي: {c.opening_balance:,.2f}")
        print("-" * 80)

