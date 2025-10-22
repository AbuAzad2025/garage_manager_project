#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""فحص شامل للمخزون في كل المستودعات"""

from app import create_app
from extensions import db
from models import StockLevel, Product, Warehouse
from sqlalchemy import func

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("📊 فحص شامل للمخزون في كل المستودعات")
    print("="*80)
    
    # 1. عدد المستودعات
    warehouses = Warehouse.query.all()
    print(f"\n📦 عدد المستودعات: {len(warehouses)}")
    for wh in warehouses:
        print(f"   - {wh.name} (ID: {wh.id}) - نوع: {wh.warehouse_type}")
    
    # 2. إجمالي المخزون لكل مستودع
    print("\n" + "="*80)
    print("📊 المخزون في كل مستودع:")
    print("="*80)
    
    total_all_warehouses = 0.0
    total_qty_all = 0
    
    for wh in warehouses:
        stock_in_wh = (
            db.session.query(
                Product.id,
                Product.name,
                Product.price,
                Product.currency,
                StockLevel.quantity
            )
            .join(StockLevel, StockLevel.product_id == Product.id)
            .filter(StockLevel.warehouse_id == wh.id)
            .filter(StockLevel.quantity > 0)
            .all()
        )
        
        wh_total = 0.0
        wh_qty = 0
        
        print(f"\n🏪 {wh.name} (ID: {wh.id}):")
        print("-" * 80)
        
        if not stock_in_wh:
            print("   ❌ لا يوجد مخزون")
            continue
        
        for row in stock_in_wh:
            qty = float(row.quantity or 0)
            price = float(row.price or 0)
            value = qty * price
            
            wh_total += value
            wh_qty += int(qty)
            
            print(f"   - {row.name}: {qty} × {price} {row.currency} = {value:.2f}")
        
        print(f"\n   💰 إجمالي {wh.name}: {wh_total:,.2f} ({wh_qty} قطعة)")
        total_all_warehouses += wh_total
        total_qty_all += wh_qty
    
    # 3. المخزون المجمّع (كما في الدفتر)
    print("\n" + "="*80)
    print("📊 المخزون المجمّع (GROUP BY - كما في الدفتر):")
    print("="*80)
    
    stock_summary = (
        db.session.query(
            Product.id,
            Product.name,
            Product.price,
            Product.currency,
            func.sum(StockLevel.quantity).label('total_qty')
        )
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(StockLevel.quantity > 0)
        .group_by(Product.id, Product.name, Product.price, Product.currency)
        .all()
    )
    
    total_grouped = 0.0
    total_qty_grouped = 0
    
    for row in stock_summary:
        qty = float(row.total_qty or 0)
        price = float(row.price or 0)
        value = qty * price
        
        total_grouped += value
        total_qty_grouped += int(qty)
        
        print(f"   - {row.name}: {qty} × {price} {row.currency} = {value:,.2f}")
    
    print("\n" + "="*80)
    print("📊 النتائج:")
    print("="*80)
    print(f"\n1️⃣ المجموع من كل مستودع منفصل: {total_all_warehouses:,.2f} ₪ ({total_qty_all} قطعة)")
    print(f"2️⃣ المجموع من GROUP BY (الدفتر): {total_grouped:,.2f} ₪ ({total_qty_grouped} قطعة)")
    
    if abs(total_all_warehouses - total_grouped) < 0.01:
        print(f"\n✅ الأرقام متطابقة! الحساب صحيح 100%")
    else:
        print(f"\n⚠️  فيه فرق: {abs(total_all_warehouses - total_grouped):,.2f} ₪")
    
    print("\n" + "="*80 + "\n")

