from app import create_app
from models import Customer, Supplier, Partner, db, Sale, Payment, Invoice, ServiceRequest
from decimal import Decimal
from sqlalchemy import func

app = create_app()
with app.app_context():
    
    print('RECALCULATING ALL BALANCES')
    print('='*70)
    print()
    
    print('CUSTOMERS:')
    customers = Customer.query.all()
    
    for customer in customers:
        invoices = db.session.query(func.sum(Invoice.total_amount)).filter(
            Invoice.customer_id == customer.id,
            Invoice.cancelled_at.is_(None)
        ).scalar() or 0
        
        sales = db.session.query(func.sum(Sale.total_amount)).filter(
            Sale.customer_id == customer.id,
            Sale.status == 'CONFIRMED'
        ).scalar() or 0
        
        services = db.session.query(func.sum(ServiceRequest.total_amount)).filter(
            ServiceRequest.customer_id == customer.id,
            ServiceRequest.status == 'COMPLETED'
        ).scalar() or 0
        
        payments_in = db.session.query(func.sum(Payment.total_amount)).filter(
            Payment.customer_id == customer.id,
            Payment.direction == 'IN',
            Payment.status == 'COMPLETED'
        ).scalar() or 0
        
        payments_out = db.session.query(func.sum(Payment.total_amount)).filter(
            Payment.customer_id == customer.id,
            Payment.direction == 'OUT',
            Payment.status == 'COMPLETED'
        ).scalar() or 0
        
        correct_balance = float(payments_in or 0) - float(payments_out or 0) - float(invoices or 0) - float(sales or 0) - float(services or 0)
        
        old_balance = float(customer.balance or 0)
        customer.balance = correct_balance
        
        print(f'  Customer #{customer.id}: {old_balance:.2f} -> {correct_balance:.2f}')
    
    db.session.commit()
    print(f'  Updated {len(customers)} customers')
    print()
    
    print('SUPPLIERS:')
    suppliers = Supplier.query.all()
    
    for supplier in suppliers:
        from models import Expense
        
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.supplier_id == supplier.id
        ).scalar() or 0
        
        payments_out = db.session.query(func.sum(Payment.total_amount)).filter(
            Payment.supplier_id == supplier.id,
            Payment.direction == 'OUT',
            Payment.status == 'COMPLETED'
        ).scalar() or 0
        
        payments_in = db.session.query(func.sum(Payment.total_amount)).filter(
            Payment.supplier_id == supplier.id,
            Payment.direction == 'IN',
            Payment.status == 'COMPLETED'
        ).scalar() or 0
        
        correct_balance = float(expenses or 0) - float(payments_out or 0) + float(payments_in or 0)
        
        old_balance = float(supplier.balance or 0)
        supplier.balance = correct_balance
        
        print(f'  Supplier #{supplier.id}: {old_balance:.2f} -> {correct_balance:.2f}')
    
    db.session.commit()
    print(f'  Updated {len(suppliers)} suppliers')
    print()
    
    print('='*70)
    print('ALL BALANCES RECALCULATED!')
    print('='*70)

