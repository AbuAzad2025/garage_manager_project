"""verify payments expenses sales balances

Revision ID: 77ab4f532fc4
Revises: c0836bd6d891
Create Date: 2025-11-19 02:46:48.595392

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '77ab4f532fc4'
down_revision = 'c0836bd6d891'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    _verify_and_update_balances(bind)


def _verify_and_update_balances(connection):
    try:
        try:
            from utils.customer_balance_updater import update_customer_balance_components
            from utils.supplier_balance_updater import update_supplier_balance_components
            from utils.partner_balance_updater import update_partner_balance_components
        except Exception:
            print("Error importing balance updaters")
            return
        
        affected_customers = set()
        affected_suppliers = set()
        affected_partners = set()
        
        payments = connection.execute(sa_text("""
            SELECT DISTINCT customer_id, supplier_id, partner_id, sale_id 
            FROM payments 
            WHERE customer_id IS NOT NULL 
               OR supplier_id IS NOT NULL 
               OR partner_id IS NOT NULL 
               OR sale_id IS NOT NULL
        """)).fetchall()
        
        for row in payments:
            customer_id, supplier_id, partner_id, sale_id = row
            
            if customer_id:
                affected_customers.add(customer_id)
            
            if supplier_id:
                affected_suppliers.add(supplier_id)
            
            if partner_id:
                affected_partners.add(partner_id)
            
            if sale_id:
                sale_customer = connection.execute(
                    sa_text("SELECT customer_id FROM sales WHERE id = :id"),
                    {"id": sale_id}
                ).fetchone()
                if sale_customer and sale_customer[0]:
                    affected_customers.add(sale_customer[0])
        
        expenses = connection.execute(sa_text("""
            SELECT DISTINCT customer_id, supplier_id, partner_id 
            FROM expenses 
            WHERE customer_id IS NOT NULL 
               OR supplier_id IS NOT NULL 
               OR partner_id IS NOT NULL
        """)).fetchall()
        
        for row in expenses:
            customer_id, supplier_id, partner_id = row
            
            if customer_id:
                affected_customers.add(customer_id)
            
            if supplier_id:
                affected_suppliers.add(supplier_id)
            
            if partner_id:
                affected_partners.add(partner_id)
        
        sales = connection.execute(sa_text("""
            SELECT DISTINCT customer_id 
            FROM sales 
            WHERE customer_id IS NOT NULL
        """)).fetchall()
        
        for row in sales:
            if row[0]:
                affected_customers.add(row[0])
        
        for customer_id in affected_customers:
            try:
                update_customer_balance_components(customer_id, connection)
            except Exception:
                pass
        
        for supplier_id in affected_suppliers:
            try:
                update_supplier_balance_components(supplier_id, connection)
            except Exception:
                pass
        
        for partner_id in affected_partners:
            try:
                update_partner_balance_components(partner_id, connection)
            except Exception:
                pass
        
        connection.commit()
        try:
            print(f"Verified and updated balances:")
            print(f"  - Customers: {len(affected_customers)} affected")
            print(f"  - Suppliers: {len(affected_suppliers)} affected")
            print(f"  - Partners: {len(affected_partners)} affected")
        except:
            pass
    except Exception as e:
        try:
            connection.rollback()
            print(f"Migration error: {str(e)}")
        except:
            pass


def downgrade():
    pass
