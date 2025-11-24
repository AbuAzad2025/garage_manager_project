"""add supplier service_expenses_balance column

Revision ID: 20251123_supplier_service_expenses
Revises: 20251121_cleanup_duplicate_indexes
Create Date: 2025-11-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '20251123_supplier_service_expenses'
down_revision = '20251121_cleanup_duplicate_indexes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("suppliers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    if "service_expenses_balance" not in columns:
        if is_sqlite:
            op.execute('ALTER TABLE suppliers ADD COLUMN service_expenses_balance NUMERIC(12, 2) NOT NULL DEFAULT 0')
        else:
            op.add_column(
                "suppliers",
                sa.Column(
                    "service_expenses_balance",
                    sa.Numeric(12, 2),
                    nullable=False,
                    server_default=sa_text("0"),
                    comment="رصيد مصروفات توريد الخدمة (تُضاف)"
                )
            )
        
        _calculate_service_expenses_balances(bind)


def _calculate_service_expenses_balances(connection):
    try:
        import sys
        import os
        import importlib.util
        from decimal import Decimal
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        suppliers = connection.execute(sa_text("SELECT id FROM suppliers")).fetchall()
        
        for (supplier_id,) in suppliers:
            try:
                supplier_id_int = int(supplier_id)
                
                utils_path = os.path.join(base_dir, 'utils', 'supplier_balance_updater.py')
                if not os.path.exists(utils_path):
                    continue
                
                spec = importlib.util.spec_from_file_location("supplier_balance_updater", utils_path)
                supplier_balance_updater_module = importlib.util.module_from_spec(spec)
                sys.modules["supplier_balance_updater"] = supplier_balance_updater_module
                spec.loader.exec_module(supplier_balance_updater_module)
                
                calculate_supplier_balance_components = supplier_balance_updater_module.calculate_supplier_balance_components
                
                models_path = os.path.join(base_dir, 'models.py')
                if os.path.exists(models_path):
                    spec = importlib.util.spec_from_file_location("models", models_path)
                    models_module = importlib.util.module_from_spec(spec)
                    sys.modules["models"] = models_module
                    spec.loader.exec_module(models_module)
                    db = models_module.db
                else:
                    continue
                
                with db.session.begin():
                    components = calculate_supplier_balance_components(supplier_id_int, db.session)
                    if components:
                        service_expenses = Decimal(str(components.get('expenses_service_supply', 0) or 0))
                        connection.execute(
                            sa_text("UPDATE suppliers SET service_expenses_balance = :val WHERE id = :id"),
                            {"id": supplier_id_int, "val": float(service_expenses)}
                        )
            except Exception as e:
                try:
                    print(f"Error updating supplier {supplier_id} service_expenses_balance: {str(e)}")
                except:
                    pass
                continue
        
        connection.commit()
    except Exception as e:
        try:
            connection.rollback()
            print(f"Migration error: {str(e)}")
        except:
            pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("suppliers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    if "service_expenses_balance" in columns:
        if is_sqlite:
            with op.batch_alter_table("suppliers") as batch_op:
                batch_op.drop_column("service_expenses_balance")
        else:
            op.drop_column("suppliers", "service_expenses_balance")

