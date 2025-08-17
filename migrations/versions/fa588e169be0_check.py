"""no-op: ignore noisy autogenerate on SQLite"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fa588e169be0'
down_revision = '26929e840ac7'
branch_labels = None
depends_on = None


def upgrade():
    # Intentionally do nothing.
    pass


def downgrade():
    # Intentionally do nothing.
    pass
