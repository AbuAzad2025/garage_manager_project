"""merge heads (card_fields + fa588e169be0)

Revision ID: fa0239daf95a
Revises: fa588e169be0, 20250818_add_card_fields_to_online_payments
Create Date: 2025-08-18 15:33:51.940993

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa0239daf95a'
down_revision = ('fa588e169be0', '20250818_add_card_fields_to_online_payments')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
