"""تغيير الخصم من نسبة مئوية إلى مبلغ صحيح

Revision ID: discount_to_amount_001
Revises: 5ee38733531c
Create Date: 2025-10-30 12:25:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'discount_to_amount_001'
down_revision = '5ee38733531c'
branch_labels = None
depends_on = None


def upgrade():
    # ServicePart: تغيير discount من Numeric(5,2) نسبة إلى Numeric(12,2) مبلغ
    with op.batch_alter_table('service_parts', schema=None) as batch_op:
        # حذف القيد القديم
        batch_op.drop_constraint('chk_service_part_discount_range', type_='check')
        # تغيير نوع العمود
        batch_op.alter_column('discount',
                            type_=sa.Numeric(12, 2),
                            existing_type=sa.Numeric(5, 2),
                            nullable=False,
                            server_default=sa.text('0'))
        # إضافة قيد جديد (مبلغ غير سالب)
        batch_op.create_check_constraint('chk_service_part_discount_positive', 'discount >= 0')
    
    # ServiceTask: تغيير discount من Numeric(5,2) نسبة إلى Numeric(12,2) مبلغ
    with op.batch_alter_table('service_tasks', schema=None) as batch_op:
        # حذف القيد القديم
        batch_op.drop_constraint('chk_service_task_discount_range', type_='check')
        # تغيير نوع العمود
        batch_op.alter_column('discount',
                            type_=sa.Numeric(12, 2),
                            existing_type=sa.Numeric(5, 2),
                            nullable=False,
                            server_default=sa.text('0'))
        # إضافة قيد جديد (مبلغ غير سالب)
        batch_op.create_check_constraint('chk_service_task_discount_positive', 'discount >= 0')


def downgrade():
    # العودة للنسبة المئوية
    with op.batch_alter_table('service_tasks', schema=None) as batch_op:
        batch_op.drop_constraint('chk_service_task_discount_positive', type_='check')
        batch_op.alter_column('discount',
                            type_=sa.Numeric(5, 2),
                            existing_type=sa.Numeric(12, 2))
        batch_op.create_check_constraint('chk_service_task_discount_range', 'discount >= 0 AND discount <= 100')
    
    with op.batch_alter_table('service_parts', schema=None) as batch_op:
        batch_op.drop_constraint('chk_service_part_discount_positive', type_='check')
        batch_op.alter_column('discount',
                            type_=sa.Numeric(5, 2),
                            existing_type=sa.Numeric(12, 2))
        batch_op.create_check_constraint('chk_service_part_discount_range', 'discount >= 0 AND discount <= 100')

