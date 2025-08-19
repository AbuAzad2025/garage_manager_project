from alembic import op
import sqlalchemy as sa

revision = '20250818_add_card_fields_to_online_payments'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('online_payments', sa.Column('card_last4', sa.String(length=10), nullable=True))
    op.add_column('online_payments', sa.Column('card_encrypted', sa.LargeBinary(), nullable=True))
    op.add_column('online_payments', sa.Column('card_brand', sa.String(length=20), nullable=True))
    op.add_column('online_payments', sa.Column('card_expiry', sa.String(length=7), nullable=True))
    op.add_column('online_payments', sa.Column('cardholder_name', sa.String(length=100), nullable=True))
    op.add_column('online_payments', sa.Column('card_fingerprint_sha256', sa.String(length=64), nullable=True))
    op.create_index('ix_online_payments_card_last4', 'online_payments', ['card_last4'], unique=False)
    op.create_index('ix_online_payments_card_brand', 'online_payments', ['card_brand'], unique=False)
    op.create_index('ix_online_payments_card_fingerprint', 'online_payments', ['card_fingerprint_sha256'], unique=False)
    op.create_index('ix_online_payments_created_at', 'online_payments', ['created_at'], unique=False)

def downgrade():
    op.drop_index('ix_online_payments_created_at', table_name='online_payments')
    op.drop_index('ix_online_payments_card_fingerprint', table_name='online_payments')
    op.drop_index('ix_online_payments_card_brand', table_name='online_payments')
    op.drop_index('ix_online_payments_card_last4', table_name='online_payments')
    op.drop_column('online_payments', 'card_fingerprint_sha256')
    op.drop_column('online_payments', 'cardholder_name')
    op.drop_column('online_payments', 'card_expiry')
    op.drop_column('online_payments', 'card_brand')
    op.drop_column('online_payments', 'card_encrypted')
    op.drop_column('online_payments', 'card_last4')
