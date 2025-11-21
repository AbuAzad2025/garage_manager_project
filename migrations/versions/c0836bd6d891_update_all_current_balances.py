"""update all current balances

Revision ID: c0836bd6d891
Revises: 27aa48fed23c
Create Date: 2025-11-19 02:44:15.295567

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = 'c0836bd6d891'
down_revision = '27aa48fed23c'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    _update_all_balances(bind)


def _update_all_balances(connection):
    try:
        try:
            from utils.customer_balance_updater import update_customer_balance_components
            from utils.supplier_balance_updater import update_supplier_balance_components
            from utils.partner_balance_updater import update_partner_balance_components
        except Exception:
            print("Error importing balance updaters")
            return
        
        customers = connection.execute(sa_text("SELECT id FROM customers")).fetchall()
        suppliers = connection.execute(sa_text("SELECT id FROM suppliers")).fetchall()
        partners = connection.execute(sa_text("SELECT id FROM partners")).fetchall()
        
        total_customers = len(customers)
        total_suppliers = len(suppliers)
        total_partners = len(partners)
        
        updated_customers = 0
        updated_suppliers = 0
        updated_partners = 0
        errors = 0
        
        for (customer_id,) in customers:
            try:
                customer_id_int = int(customer_id)
                update_customer_balance_components(customer_id_int, connection)
                updated_customers += 1
            except Exception as e:
                errors += 1
                try:
                    print(f"Error updating customer {customer_id}: {str(e)}")
                except:
                    pass
                continue
        
        for (supplier_id,) in suppliers:
            try:
                supplier_id_int = int(supplier_id)
                update_supplier_balance_components(supplier_id_int, connection)
                updated_suppliers += 1
            except Exception as e:
                errors += 1
                try:
                    print(f"Error updating supplier {supplier_id}: {str(e)}")
                except:
                    pass
                continue
        
        for (partner_id,) in partners:
            try:
                partner_id_int = int(partner_id)
                update_partner_balance_components(partner_id_int, connection)
                updated_partners += 1
            except Exception as e:
                errors += 1
                try:
                    print(f"Error updating partner {partner_id}: {str(e)}")
                except:
                    pass
                continue
        
        connection.commit()
        try:
            print(f"Updated all current balances:")
            print(f"  - Customers: {updated_customers}/{total_customers}")
            print(f"  - Suppliers: {updated_suppliers}/{total_suppliers}")
            print(f"  - Partners: {updated_partners}/{total_partners}")
            if errors > 0:
                print(f"  - Errors: {errors}")
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
