"""drop unique on suppliers.phone & service_requests.service_number

Revision ID: 9b2e3cfa7a10
Revises: 48a32db2d856
Create Date: 2025-08-12 16:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b2e3cfa7a10'
down_revision = '48a32db2d856'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # SQLite يحتاج rebuild للجداول لإزالة UNIQUE
    if dialect == "sqlite":
        # احتياط: نظّف أي tmp قديم
        op.execute("DROP TABLE IF EXISTS _alembic_tmp_suppliers")
        op.execute("DROP TABLE IF EXISTS _alembic_tmp_service_requests")
        op.execute("PRAGMA foreign_keys=OFF")

        # ===== suppliers (إزالة UNIQUE عن phone، والإبقاء على UNIQUE email/identity_number) =====
        op.create_table(
            "_suppliers_new",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("is_local", sa.Boolean(), nullable=True),
            sa.Column("identity_number", sa.String(100), nullable=True),
            sa.Column("contact", sa.String(200), nullable=True),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(120), nullable=True),
            sa.Column("address", sa.String(200), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("balance", sa.Numeric(12, 2), nullable=True),
            sa.Column("payment_terms", sa.String(50), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False, server_default="ILS"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("identity_number", name="uq_suppliers_identity_number"),
            sa.UniqueConstraint("email", name="uq_suppliers_email"),
        )

        op.execute("""
            INSERT INTO _suppliers_new
                (id, name, is_local, identity_number, contact, phone, email, address, notes, balance, payment_terms, currency, created_at, updated_at)
            SELECT
                id, name, is_local, identity_number, contact, phone, email, address, notes, balance, payment_terms, currency, created_at, updated_at
            FROM suppliers
        """)

        op.drop_table("suppliers")
        op.rename_table("_suppliers_new", "suppliers")

        # ===== service_requests (إزالة UNIQUE عن service_number) =====
        op.create_table(
            "_service_requests_new",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_number", sa.String(50), nullable=True),  # removed UNIQUE
            sa.Column("request_date", sa.DateTime(), nullable=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("mechanic_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("vehicle_vrn", sa.String(50), nullable=False),
            sa.Column("vehicle_type_id", sa.Integer(), sa.ForeignKey("equipment_types.id")),
            sa.Column("vehicle_model", sa.String(100)),
            sa.Column("chassis_number", sa.String(100)),
            sa.Column("problem_description", sa.Text()),
            sa.Column("engineer_notes", sa.Text()),
            sa.Column("diagnosis", sa.Text()),
            sa.Column("solution", sa.Text()),
            sa.Column("status", sa.Enum(
                "PENDING", "DIAGNOSIS", "IN_PROGRESS", "COMPLETED", "CANCELLED", "ON_HOLD",
                name="service_status"
            ), nullable=True),
            sa.Column("priority", sa.Enum(
                "LOW", "MEDIUM", "HIGH", "URGENT",
                name="service_priority"
            ), nullable=True),
            sa.Column("estimated_duration", sa.Integer()),
            sa.Column("actual_duration", sa.Integer()),
            sa.Column("estimated_cost", sa.Numeric(12, 2)),
            sa.Column("total_cost", sa.Numeric(12, 2)),
            sa.Column("tax_rate", sa.Numeric(5, 2)),
            sa.Column("start_time", sa.DateTime()),
            sa.Column("end_time", sa.DateTime()),
            sa.Column("name", sa.String(100)),
            sa.Column("phone", sa.String(20)),
            sa.Column("email", sa.String(100)),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

        op.execute("""
            INSERT INTO _service_requests_new
                (id, service_number, request_date, customer_id, mechanic_id, vehicle_vrn, vehicle_type_id, vehicle_model, chassis_number,
                 problem_description, engineer_notes, diagnosis, solution, status, priority, estimated_duration, actual_duration,
                 estimated_cost, total_cost, tax_rate, start_time, end_time, name, phone, email, created_at, updated_at)
            SELECT
                id, service_number, request_date, customer_id, mechanic_id, vehicle_vrn, vehicle_type_id, vehicle_model, chassis_number,
                problem_description, engineer_notes, diagnosis, solution, status, priority, estimated_duration, actual_duration,
                estimated_cost, total_cost, tax_rate, start_time, end_time, name, phone, email, created_at, updated_at
            FROM service_requests
        """)

        op.drop_table("service_requests")
        op.rename_table("_service_requests_new", "service_requests")

        op.execute("PRAGMA foreign_keys=ON")

    else:
        # لغير SQLite: إسقاط القيود مباشرةً بالأسماء (عدّل الأسماء حسب ما عندك)
        # suppliers: drop UNIQUE on phone
        try:
            op.drop_constraint("uq_suppliers_phone", "suppliers", type_="unique")
        except Exception:
            pass  # في حال كان بدون اسم

        # service_requests: drop UNIQUE on service_number
        try:
            op.drop_constraint("uq_service_requests_service_number", "service_requests", type_="unique")
        except Exception:
            pass


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute("PRAGMA foreign_keys=OFF")

        # ارجاع UNIQUE(phone) في suppliers
        op.create_table(
            "_suppliers_old",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("is_local", sa.Boolean(), nullable=True),
            sa.Column("identity_number", sa.String(100), nullable=True),
            sa.Column("contact", sa.String(200), nullable=True),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(120), nullable=True),
            sa.Column("address", sa.String(200), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("balance", sa.Numeric(12, 2), nullable=True),
            sa.Column("payment_terms", sa.String(50), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False, server_default="ILS"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("identity_number", name="uq_suppliers_identity_number"),
            sa.UniqueConstraint("email", name="uq_suppliers_email"),
            sa.UniqueConstraint("phone", name="uq_suppliers_phone"),
        )
        op.execute("""
            INSERT INTO _suppliers_old
                (id, name, is_local, identity_number, contact, phone, email, address, notes, balance, payment_terms, currency, created_at, updated_at)
            SELECT
                id, name, is_local, identity_number, contact, phone, email, address, notes, balance, payment_terms, currency, created_at, updated_at
            FROM suppliers
        """)
        op.drop_table("suppliers")
        op.rename_table("_suppliers_old", "suppliers")

        # ارجاع UNIQUE(service_number) في service_requests
        op.create_table(
            "_service_requests_old",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_number", sa.String(50), nullable=True, unique=True),
            sa.Column("request_date", sa.DateTime(), nullable=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("mechanic_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("vehicle_vrn", sa.String(50), nullable=False),
            sa.Column("vehicle_type_id", sa.Integer(), sa.ForeignKey("equipment_types.id")),
            sa.Column("vehicle_model", sa.String(100)),
            sa.Column("chassis_number", sa.String(100)),
            sa.Column("problem_description", sa.Text()),
            sa.Column("engineer_notes", sa.Text()),
            sa.Column("diagnosis", sa.Text()),
            sa.Column("solution", sa.Text()),
            sa.Column("status", sa.Enum(
                "PENDING", "DIAGNOSIS", "IN_PROGRESS", "COMPLETED", "CANCELLED", "ON_HOLD",
                name="service_status"
            ), nullable=True),
            sa.Column("priority", sa.Enum(
                "LOW", "MEDIUM", "HIGH", "URGENT",
                name="service_priority"
            ), nullable=True),
            sa.Column("estimated_duration", sa.Integer()),
            sa.Column("actual_duration", sa.Integer()),
            sa.Column("estimated_cost", sa.Numeric(12, 2)),
            sa.Column("total_cost", sa.Numeric(12, 2)),
            sa.Column("tax_rate", sa.Numeric(5, 2)),
            sa.Column("start_time", sa.DateTime()),
            sa.Column("end_time", sa.DateTime()),
            sa.Column("name", sa.String(100)),
            sa.Column("phone", sa.String(20)),
            sa.Column("email", sa.String(100)),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
        op.execute("""
            INSERT INTO _service_requests_old
                (id, service_number, request_date, customer_id, mechanic_id, vehicle_vrn, vehicle_type_id, vehicle_model, chassis_number,
                 problem_description, engineer_notes, diagnosis, solution, status, priority, estimated_duration, actual_duration,
                 estimated_cost, total_cost, tax_rate, start_time, end_time, name, phone, email, created_at, updated_at)
            SELECT
                id, service_number, request_date, customer_id, mechanic_id, vehicle_vrn, vehicle_type_id, vehicle_model, chassis_number,
                problem_description, engineer_notes, diagnosis, solution, status, priority, estimated_duration, actual_duration,
                estimated_cost, total_cost, tax_rate, start_time, end_time, name, phone, email, created_at, updated_at
            FROM service_requests
        """)
        op.drop_table("service_requests")
        op.rename_table("_service_requests_old", "service_requests")

        op.execute("PRAGMA foreign_keys=ON")

    else:
        # لغير SQLite: أعد إضافة القيود
        op.create_unique_constraint("uq_suppliers_phone", "suppliers", ["phone"])
        op.create_unique_constraint("uq_service_requests_service_number", "service_requests", ["service_number"])
