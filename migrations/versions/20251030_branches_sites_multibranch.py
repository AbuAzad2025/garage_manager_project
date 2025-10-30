"""branches_and_sites_multibranch

Revision ID: branches_sites_001
Revises: a8e34bc7e6bf
Create Date: 2025-10-30 10:00:00.000000

إضافة إدارة الفروع والمواقع وربطها مع الموظفين والنفقات والمستودعات
يشمل: جداول branches, sites, user_branches + أعمدة branch_id/site_id
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'branches_sites_001'
down_revision = 'a8e34bc7e6bf'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ═══════════════════════════════════════════════════════════════
    # 1) Create branches table
    # ═══════════════════════════════════════════════════════════════
    op.create_table(
        'branches',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False, index=True),
        sa.Column('code', sa.String(length=32), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column('address', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('geo_lat', sa.Numeric(10, 6), nullable=True),
        sa.Column('geo_lng', sa.Numeric(10, 6), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('manager_user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('timezone', sa.String(length=64), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column('tax_id', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True, index=True),
        sa.Column('archived_by', sa.Integer(), nullable=True, index=True),
        sa.Column('archive_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.ForeignKeyConstraint(['manager_user_id'], ['users.id'], name='fk_branches_manager_user', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['archived_by'], ['users.id'], name='fk_branches_archived_by', ondelete='SET NULL'),
    )

    # Index يُنشأ تلقائياً من Column(index=True)

    # Insert main branch seed
    conn.execute(sa.text("""
        INSERT INTO branches (name, code, is_active, currency)
        VALUES ('الفرع الرئيسي', 'MAIN', 1, 'ILS')
    """))

    # Get inserted main branch id (SQLite/Postgres compatible)
    main_branch_id = conn.execute(sa.text("SELECT id FROM branches WHERE code = 'MAIN' LIMIT 1")).scalar()

    # ═══════════════════════════════════════════════════════════════
    # 2) Create sites table
    # ═══════════════════════════════════════════════════════════════
    op.create_table(
        'sites',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False, index=True),
        sa.Column('name', sa.String(length=120), nullable=False, index=True),
        sa.Column('code', sa.String(length=32), nullable=False, index=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column('address', sa.String(length=200), nullable=True),
        sa.Column('geo_lat', sa.Numeric(10, 6), nullable=True),
        sa.Column('geo_lng', sa.Numeric(10, 6), nullable=True),
        sa.Column('manager_user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True, index=True),
        sa.Column('archived_by', sa.Integer(), nullable=True, index=True),
        sa.Column('archive_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_sites_branch', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_user_id'], ['users.id'], name='fk_sites_manager_user', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['archived_by'], ['users.id'], name='fk_sites_archived_by', ondelete='SET NULL'),
        sa.UniqueConstraint('branch_id', 'code', name='uq_sites_branch_code'),
        sa.UniqueConstraint('branch_id', 'name', name='uq_sites_branch_name'),
    )

    # ═══════════════════════════════════════════════════════════════
    # 3) Map users to branches (for permissions scoping)
    # ═══════════════════════════════════════════════════════════════
    op.create_table(
        'user_branches',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_branches_user', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_user_branches_branch', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'branch_id', name='pk_user_branches'),
    )
    op.create_index('ix_user_branches_user', 'user_branches', ['user_id'], unique=False)
    op.create_index('ix_user_branches_branch', 'user_branches', ['branch_id'], unique=False)

    # ═══════════════════════════════════════════════════════════════
    # 4) Add branch/site references to employees, expenses, warehouses
    #    - Backfill existing rows to MAIN branch
    #    - Set NOT NULL where required using batch_alter for SQLite safety
    # ═══════════════════════════════════════════════════════════════

    # Employees: add columns
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('site_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_employees_branch_id', ['branch_id'], unique=False)
        batch_op.create_index('ix_employees_site_id', ['site_id'], unique=False)
        batch_op.create_foreign_key('fk_employees_branch', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_employees_site', 'sites', ['site_id'], ['id'], ondelete='SET NULL')

    # Expenses: add columns
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('site_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_expenses_branch_id', ['branch_id'], unique=False)
        batch_op.create_index('ix_expenses_site_id', ['site_id'], unique=False)
        batch_op.create_foreign_key('fk_expenses_branch', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_expenses_site', 'sites', ['site_id'], ['id'], ondelete='SET NULL')

    # Warehouses: add optional branch_id (لربط المخزون بفرع)
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_warehouses_branch_id', ['branch_id'], unique=False)
        batch_op.create_foreign_key('fk_warehouses_branch', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')

    # Backfill existing rows to main branch
    if main_branch_id:
        conn.execute(sa.text("UPDATE employees SET branch_id = :bid WHERE branch_id IS NULL"), dict(bid=main_branch_id))
        conn.execute(sa.text("UPDATE expenses SET branch_id = :bid WHERE branch_id IS NULL"), dict(bid=main_branch_id))
        conn.execute(sa.text("UPDATE warehouses SET branch_id = COALESCE(branch_id, :bid)"), dict(bid=main_branch_id))

    # Set NOT NULL for required fields (branch on expenses and employees)
    # SQLite-safe with recreate='always'
    with op.batch_alter_table('employees', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('expenses', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Integer(), nullable=False)

    # ═══════════════════════════════════════════════════════════════
    # 5) Helpful composite indexes for reporting
    # ═══════════════════════════════════════════════════════════════
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_expenses_branch_date ON expenses (branch_id, date)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_employees_branch_name ON employees (branch_id, name)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sites_branch_active ON sites (branch_id, is_active)"))


def downgrade():
    conn = op.get_bind()

    # Drop composite indexes
    op.execute(sa.text("DROP INDEX IF EXISTS ix_expenses_branch_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_employees_branch_name"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_sites_branch_active"))

    # Revert NOT NULL on branch_id
    with op.batch_alter_table('expenses', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table('employees', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Integer(), nullable=True)

    # Remove added FKs and columns
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_warehouses_branch', type_='foreignkey')
        batch_op.drop_index('ix_warehouses_branch_id')
        batch_op.drop_column('branch_id')

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_expenses_site', type_='foreignkey')
        batch_op.drop_constraint('fk_expenses_branch', type_='foreignkey')
        batch_op.drop_index('ix_expenses_site_id')
        batch_op.drop_index('ix_expenses_branch_id')
        batch_op.drop_column('site_id')
        batch_op.drop_column('branch_id')

    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_constraint('fk_employees_site', type_='foreignkey')
        batch_op.drop_constraint('fk_employees_branch', type_='foreignkey')
        batch_op.drop_index('ix_employees_site_id')
        batch_op.drop_index('ix_employees_branch_id')
        batch_op.drop_column('site_id')
        batch_op.drop_column('branch_id')

    # Drop user_branches
    op.drop_index('ix_user_branches_branch', table_name='user_branches')
    op.drop_index('ix_user_branches_user', table_name='user_branches')
    op.drop_table('user_branches')

    # Drop sites then branches
    op.drop_table('sites')
    op.drop_index('ix_branches_name', table_name='branches')
    op.drop_table('branches')


