"""fix customer balance calculation formula

Revision ID: b3eae24e42d3
Revises: 46df8ed7e7e5
Create Date: 2025-11-19 03:09:52.123456

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = 'b3eae24e42d3'
down_revision = '46df8ed7e7e5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    _fix_customer_balances(bind)


def _fix_customer_balances(connection):
    """إصلاح جميع أرصدة العملاء بالمعادلة الصحيحة"""
    try:
        try:
            from utils.customer_balance_updater import update_customer_balance_components
        except Exception:
            print("Error importing balance updater")
            return
        
        customers = connection.execute(sa_text("SELECT id FROM customers")).fetchall()
        total = len(customers)
        updated = 0
        errors = 0
        
        for (customer_id,) in customers:
            try:
                customer_id_int = int(customer_id)
                update_customer_balance_components(customer_id_int, connection)
                updated += 1
            except Exception as e:
                errors += 1
                try:
                    print(f"Error updating customer {customer_id}: {str(e)}")
                except:
                    pass
                continue
        
        connection.commit()
        try:
            print(f"Fixed customer balances:")
            print(f"  - Updated: {updated}/{total}")
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
