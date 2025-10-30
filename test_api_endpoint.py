"""Test the returns API endpoints"""
from app import app
from flask import json

with app.test_client() as client:
    # Login first (assuming there's a test user)
    with app.app_context():
        from models import User
        user = User.query.first()
        if user:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
        
        # Test get_sale_items
        print("🧪 Testing /returns/api/sale/14/items")
        try:
            response = client.get('/returns/api/sale/14/items')
            print(f"  Status: {response.status_code}")
            if response.status_code == 200:
                data = response.get_json()
                print(f"  ✅ Success: {data.get('success')}")
                print(f"  Items count: {len(data.get('items', []))}")
            else:
                print(f"  ❌ Error: {response.data.decode()[:200]}")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
        
        # Test get_customer_sales  
        print("\n🧪 Testing /returns/api/customer/7/sales")
        try:
            response = client.get('/returns/api/customer/7/sales')
            print(f"  Status: {response.status_code}")
            if response.status_code == 200:
                data = response.get_json()
                print(f"  ✅ Success: {data.get('success')}")
                print(f"  Sales count: {len(data.get('sales', []))}")
            else:
                print(f"  ❌ Error: {response.data.decode()[:200]}")
        except Exception as e:
            print(f"  ❌ Exception: {e}")

