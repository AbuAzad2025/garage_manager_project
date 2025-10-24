# أوامر PythonAnywhere - مباشرة

## Bash Console

```bash
cd ~/garage_manager_project/garage_manager
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```

## Python Console

```python
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # payments.receiver_name
    try:
        db.session.execute(text("ALTER TABLE payments ADD COLUMN receiver_name VARCHAR(100)"))
        db.session.commit()
        print("✅ payments.receiver_name")
    except:
        print("✅ payments.receiver_name (موجود)")
        db.session.rollback()
    
    # customers.opening_balance
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"))
        db.session.commit()
        print("✅ customers.opening_balance")
    except:
        print("✅ customers.opening_balance (موجود)")
        db.session.rollback()
    
    # suppliers.opening_balance
    try:
        db.session.execute(text("ALTER TABLE suppliers ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"))
        db.session.commit()
        print("✅ suppliers.opening_balance")
    except:
        print("✅ suppliers.opening_balance (موجود)")
        db.session.rollback()
    
    # partners.opening_balance
    try:
        db.session.execute(text("ALTER TABLE partners ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"))
        db.session.commit()
        print("✅ partners.opening_balance")
    except:
        print("✅ partners.opening_balance (موجود)")
        db.session.rollback()
    
    print("\n✅ تم!")

exit()
```

## Bash Console (إعادة التحميل)

```bash
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

## التحقق

```
https://palkaraj.pythonanywhere.com/
https://palkaraj.pythonanywhere.com/sales/
https://palkaraj.pythonanywhere.com/returns/
```

---

**انتهى.**

