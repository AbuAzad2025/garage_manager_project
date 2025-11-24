"""update_customer_balances_after_preorder_logic_change

Revision ID: 713f206338a2
Revises: 20251121_cleanup_duplicate_indexes
Create Date: 2025-11-23 22:13:37.708707

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text as sa_text


# revision identifiers, used by Alembic.
revision = '713f206338a2'
down_revision = '20251121_cleanup_duplicate_indexes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    _update_all_customer_balances(bind)


def _update_all_customer_balances(connection):
    """تحديث جميع أرصدة العملاء بعد تغيير منطق حساب العربونات من الحجوزات المسبقة"""
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
                if updated_customers % 100 == 0:
                    connection.commit()
                    print(f"Updated {updated_customers}/{total_customers} customers...")
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
