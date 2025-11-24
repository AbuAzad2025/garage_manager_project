"""merge supplier service expenses and customer balances heads

Revision ID: 86dd195d861b
Revises: 20251123_supplier_service_expenses, 713f206338a2
Create Date: 2025-11-24 00:43:16.773297

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86dd195d861b'
down_revision = ('20251123_supplier_service_expenses', '713f206338a2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
