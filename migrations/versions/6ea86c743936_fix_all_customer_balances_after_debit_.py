"""fix_all_customer_balances_after_debit_credit_reversal

Revision ID: 6ea86c743936
Revises: b3eae24e42d3
Create Date: 2025-11-19 03:35:24.698254

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '6ea86c743936'
down_revision = 'b3eae24e42d3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    _update_all_customer_balances(bind)


def _update_all_customer_balances(connection):
    try:
        try:
            from utils.customer_balance_updater import update_customer_balance_components
        except Exception:
            print("Error importing customer balance updater")
            return
        
        customers = connection.execute(sa_text("SELECT id FROM customers")).fetchall()
        total_customers = len(customers)
        updated_customers = 0
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
        
        connection.commit()
        try:
            print(f"Updated all customer balances:")
            print(f"  - Customers: {updated_customers}/{total_customers}")
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
