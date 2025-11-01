"""Merge multiple heads

Revision ID: a2a78189d13c
Revises: 20251031_installment, 900e81a536d2
Create Date: 2025-10-31 23:44:38.616058

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a78189d13c'
down_revision = ('20251031_installment', '900e81a536d2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
