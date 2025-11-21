"""add customer balance columns

Revision ID: 20251118_customer_balance_cols
Revises: 20251118_perf_order_by
Create Date: 2025-11-18 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from decimal import Decimal


revision = '20251118_customer_balance_cols'
down_revision = '20251118_pagination_perf'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("customers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        ("current_balance", sa.Numeric(12, 2), True),
        ("sales_balance", sa.Numeric(12, 2), False),
        ("returns_balance", sa.Numeric(12, 2), False),
        ("invoices_balance", sa.Numeric(12, 2), False),
        ("services_balance", sa.Numeric(12, 2), False),
        ("preorders_balance", sa.Numeric(12, 2), False),
        ("online_orders_balance", sa.Numeric(12, 2), False),
        ("payments_in_balance", sa.Numeric(12, 2), False),
        ("payments_out_balance", sa.Numeric(12, 2), False),
        ("checks_in_balance", sa.Numeric(12, 2), False),
        ("checks_out_balance", sa.Numeric(12, 2), False),
        ("returned_checks_in_balance", sa.Numeric(12, 2), False),
        ("returned_checks_out_balance", sa.Numeric(12, 2), False),
        ("expenses_balance", sa.Numeric(12, 2), False),
        ("service_expenses_balance", sa.Numeric(12, 2), False),
    ]
    
    if is_sqlite:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.execute(f'ALTER TABLE customers ADD COLUMN {col_name} NUMERIC(12, 2) NOT NULL DEFAULT 0')
        
        indexes = {idx["name"] for idx in inspector.get_indexes("customers")}
        if "ix_customers_current_balance" not in indexes:
            op.execute('CREATE INDEX IF NOT EXISTS ix_customers_current_balance ON customers (current_balance)')
    else:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.add_column("customers", sa.Column(col_name, col_type, nullable=False, server_default=sa.text("0")))
        
        indexes = {idx["name"] for idx in inspector.get_indexes("customers")}
        if "ix_customers_current_balance" not in indexes:
            op.create_index("ix_customers_current_balance", "customers", ["current_balance"])
    
    _calculate_initial_balances(bind)


def _calculate_initial_balances(connection):
    """حساب القيم الأولية للأرصدة من البيانات الموجودة"""
    try:
        import sys
        import os
        import importlib.util
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        balance_calc_path = os.path.join(base_dir, 'utils', 'balance_calculator.py')
        
        if not os.path.exists(balance_calc_path):
            return
        
        spec = importlib.util.spec_from_file_location("balance_calculator", balance_calc_path)
        balance_module = importlib.util.module_from_spec(spec)
        sys.modules["balance_calculator"] = balance_module
        spec.loader.exec_module(balance_module)
        
        calculate_customer_balance_components = balance_module.calculate_customer_balance_components
        from decimal import Decimal
        
        customers = connection.execute(sa.text("SELECT id FROM customers")).fetchall()
        total = len(customers)
        updated = 0
        
        for (customer_id,) in customers:
            try:
                components = calculate_customer_balance_components(customer_id, connection)
                if not components:
                    continue
                
                customer = connection.execute(
                    sa.text("SELECT opening_balance, currency FROM customers WHERE id = :id"),
                    {"id": customer_id}
                ).fetchone()
                
                opening_balance = Decimal('0.00')
                customer_currency = "ILS"
                if customer:
                    opening_balance = Decimal(str(customer[0] or 0))
                    customer_currency = customer[1] if len(customer) > 1 and customer[1] else "ILS"
                
                # تحويل opening_balance إلى ILS إذا كانت عملة العميل ليست ILS
                if customer_currency and customer_currency != "ILS":
                    try:
                        # استيراد convert_amount من models
                        if "models" in sys.modules:
                            models_module = sys.modules["models"]
                        else:
                            models_path = os.path.join(base_dir, 'models.py')
                            if os.path.exists(models_path):
                                spec = importlib.util.spec_from_file_location("models", models_path)
                                models_module = importlib.util.module_from_spec(spec)
                                sys.modules["models"] = models_module
                                spec.loader.exec_module(models_module)
                            else:
                                models_module = None
                        
                        if models_module and hasattr(models_module, 'convert_amount'):
                            opening_balance = models_module.convert_amount(opening_balance, customer_currency, "ILS")
                    except Exception:
                        pass  # استخدم القيمة الأصلية إذا فشل التحويل
                
                current_balance = (
                    opening_balance +
                    Decimal(str(components.get('payments_in_balance', 0) or 0)) -
                    (Decimal(str(components.get('sales_balance', 0) or 0)) +
                     Decimal(str(components.get('invoices_balance', 0) or 0)) +
                     Decimal(str(components.get('services_balance', 0) or 0)) +
                     Decimal(str(components.get('preorders_balance', 0) or 0)) +
                     Decimal(str(components.get('online_orders_balance', 0) or 0))) +
                    Decimal(str(components.get('returns_balance', 0) or 0)) -
                    Decimal(str(components.get('payments_out_balance', 0) or 0)) -
                    Decimal(str(components.get('returned_checks_in_balance', 0) or 0)) +
                    Decimal(str(components.get('returned_checks_out_balance', 0) or 0)) -
                    Decimal(str(components.get('expenses_balance', 0) or 0)) +
                    Decimal(str(components.get('service_expenses_balance', 0) or 0))
                )
                
                connection.execute(
                    sa.text("""
                        UPDATE customers SET
                            sales_balance = :sales,
                            returns_balance = :returns,
                            invoices_balance = :invoices,
                            services_balance = :services,
                            preorders_balance = :preorders,
                            online_orders_balance = :online_orders,
                            payments_in_balance = :payments_in,
                            payments_out_balance = :payments_out,
                            checks_in_balance = :checks_in,
                            checks_out_balance = :checks_out,
                            returned_checks_in_balance = :returned_checks_in,
                            returned_checks_out_balance = :returned_checks_out,
                            expenses_balance = :expenses,
                            service_expenses_balance = :service_expenses,
                            current_balance = :current_balance
                        WHERE id = :id
                    """),
                    {
                        "id": customer_id,
                        "sales": float(components.get('sales_balance', 0)),
                        "returns": float(components.get('returns_balance', 0)),
                        "invoices": float(components.get('invoices_balance', 0)),
                        "services": float(components.get('services_balance', 0)),
                        "preorders": float(components.get('preorders_balance', 0)),
                        "online_orders": float(components.get('online_orders_balance', 0)),
                        "payments_in": float(components.get('payments_in_balance', 0)),
                        "payments_out": float(components.get('payments_out_balance', 0)),
                        "checks_in": float(components.get('checks_in_balance', 0)),
                        "checks_out": float(components.get('checks_out_balance', 0)),
                        "returned_checks_in": float(components.get('returned_checks_in_balance', 0)),
                        "returned_checks_out": float(components.get('returned_checks_out_balance', 0)),
                        "expenses": float(components.get('expenses_balance', 0)),
                        "service_expenses": float(components.get('service_expenses_balance', 0)),
                        "current_balance": float(current_balance)
                    }
                )
                updated += 1
            except Exception:
                continue
        
        connection.commit()
    except Exception:
        try:
            connection.rollback()
        except:
            pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("customers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        "current_balance",
        "sales_balance",
        "returns_balance",
        "invoices_balance",
        "services_balance",
        "preorders_balance",
        "online_orders_balance",
        "payments_in_balance",
        "payments_out_balance",
        "checks_in_balance",
        "checks_out_balance",
        "returned_checks_in_balance",
        "returned_checks_out_balance",
        "expenses_balance",
        "service_expenses_balance"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("customers") as batch_op:
            indexes = {idx["name"] for idx in inspector.get_indexes("customers")}
            if "ix_customers_current_balance" in indexes:
                batch_op.drop_index("ix_customers_current_balance")
            
            for col_name in balance_columns:
                if col_name in columns:
                    batch_op.drop_column(col_name)
    else:
        indexes = {idx["name"] for idx in inspector.get_indexes("customers")}
        if "ix_customers_current_balance" in indexes:
            op.drop_index("ix_customers_current_balance", table_name="customers")
        
        for col_name in balance_columns:
            if col_name in columns:
                op.drop_column("customers", col_name)

