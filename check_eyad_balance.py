from app import create_app, db
from models import Customer

app = create_app()
with app.app_context():
    eyad = Customer.query.filter_by(id=2).first()
    
    print("=" * 80)
    print(f"العميل: {eyad.name}")
    print("=" * 80)
    print(f"الرصيد من الموديل (customer.balance): {eyad.balance:,.2f}")
    print(f"الرصيد الافتتاحي (opening_balance): {eyad.opening_balance:,.2f}")
    print("=" * 80)

