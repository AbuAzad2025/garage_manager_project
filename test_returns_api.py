"""Test script to check returns API"""
from app import app, db
from models import Sale, SaleReturnLine

with app.app_context():
    # Check if condition column exists
    print("✅ SaleReturnLine columns:")
    for col in SaleReturnLine.__table__.columns:
        print(f"  - {col.name}: {col.type}")
    
    # Test a simple query
    print("\n✅ Testing Sale query:")
    sale = Sale.query.first()
    if sale:
        print(f"  Found sale #{sale.id}")
        print(f"  Lines count: {len(sale.lines or [])}")
    else:
        print("  No sales found")

