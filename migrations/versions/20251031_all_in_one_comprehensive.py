"""تهجير شامل واحد - جميع التحديثات الأخيرة
ALL-IN-ONE Comprehensive Migration

Revision ID: all_in_one_20251031
Revises: 
Create Date: 2025-10-31 09:15:00.000000

يشمل جميع التحديثات:
- نظام الفروع والمواقع
- تحسينات الموظفين (خصومات، سلف، تاريخ تعيين)
- أنواع المصاريف الشاملة
- نظام SaaS
- تحسينات المستودعات والمرتجعات
"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers
revision = 'all_in_one_20251031'
down_revision = None  # مستقل - لا يعتمد على أي تهجير سابق
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    print("=" * 80)
    print("🚀 تطبيق التهجير الشامل")
    print("=" * 80)
    
    # ═══════════════════════════════════════════════════════════════
    # 1) إنشاء جدول الفروع (branches)
    # ═══════════════════════════════════════════════════════════════
    print("\n1️⃣ إنشاء جدول الفروع...")
    
    try:
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
            sa.Column('manager_employee_id', sa.Integer(), nullable=True, index=True),
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
            sa.ForeignKeyConstraint(['manager_employee_id'], ['employees.id'], name='fk_branches_manager_employee', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['archived_by'], ['users.id'], name='fk_branches_archived_by', ondelete='SET NULL'),
        )
        print("   ✓ branches")
    except Exception as e:
        print(f"   ⏩ branches ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 2) إنشاء جدول المواقع (sites)
    # ═══════════════════════════════════════════════════════════════
    print("\n2️⃣ إنشاء جدول المواقع...")
    
    try:
        op.create_table(
            'sites',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=False, index=True),
            sa.Column('name', sa.String(length=120), nullable=False, index=True),
            sa.Column('code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
            sa.Column('address', sa.String(length=200), nullable=True),
            sa.Column('city', sa.String(length=100), nullable=True),
            sa.Column('geo_lat', sa.Numeric(10, 6), nullable=True),
            sa.Column('geo_lng', sa.Numeric(10, 6), nullable=True),
            sa.Column('manager_user_id', sa.Integer(), nullable=True, index=True),
            sa.Column('manager_employee_id', sa.Integer(), nullable=True, index=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column('archived_at', sa.DateTime(), nullable=True, index=True),
            sa.Column('archived_by', sa.Integer(), nullable=True, index=True),
            sa.Column('archive_reason', sa.String(length=200), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
            sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_sites_branch', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['manager_user_id'], ['users.id'], name='fk_sites_manager_user', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['manager_employee_id'], ['employees.id'], name='fk_sites_manager_employee', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['archived_by'], ['users.id'], name='fk_sites_archived_by', ondelete='SET NULL'),
        )
        print("   ✓ sites")
    except Exception as e:
        print(f"   ⏩ sites ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 3) إنشاء جدول ربط المستخدمين بالفروع (user_branches)
    # ═══════════════════════════════════════════════════════════════
    print("\n3️⃣ إنشاء جدول user_branches...")
    
    try:
        op.create_table(
            'user_branches',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False, index=True),
            sa.Column('branch_id', sa.Integer(), nullable=False, index=True),
            sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column('can_manage', sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_branches_user', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_user_branches_branch', ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'branch_id', name='uq_user_branch'),
        )
        print("   ✓ user_branches")
    except Exception as e:
        print(f"   ⏩ user_branches ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 4) إنشاء جدول خصومات الموظفين (employee_deductions)
    # ═══════════════════════════════════════════════════════════════
    print("\n4️⃣ إنشاء جدول خصومات الموظفين...")
    
    try:
        op.create_table(
            'employee_deductions',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False, index=True),
            sa.Column('deduction_type', sa.String(length=50), nullable=False, index=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
            sa.Column('start_date', sa.Date(), nullable=False, index=True),
            sa.Column('end_date', sa.Date(), nullable=True, index=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('expense_id', sa.Integer(), nullable=True, index=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_deductions_employee', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name='fk_deductions_expense', ondelete='SET NULL'),
        )
        print("   ✓ employee_deductions")
    except Exception as e:
        print(f"   ⏩ employee_deductions ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 5) إنشاء جدول سلف الموظفين (employee_advances)
    # ═══════════════════════════════════════════════════════════════
    print("\n5️⃣ إنشاء جدول سلف الموظفين...")
    
    try:
        op.create_table(
            'employee_advances',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False, index=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
            sa.Column('advance_date', sa.Date(), nullable=False, index=True),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('total_installments', sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column('installments_paid', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('fully_paid', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('expense_id', sa.Integer(), nullable=True, index=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_advances_employee', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name='fk_advances_expense', ondelete='SET NULL'),
        )
        print("   ✓ employee_advances")
    except Exception as e:
        print(f"   ⏩ employee_advances ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 6) إنشاء جدول أقساط السلف (employee_advance_installments)
    # ═══════════════════════════════════════════════════════════════
    print("\n6️⃣ إنشاء جدول أقساط السلف...")
    
    try:
        op.create_table(
            'employee_advance_installments',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False, index=True),
            sa.Column('advance_expense_id', sa.Integer(), nullable=False, index=True),
            sa.Column('installment_number', sa.Integer(), nullable=False),
            sa.Column('total_installments', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
            sa.Column('due_date', sa.Date(), nullable=False, index=True),
            sa.Column('paid', sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column('paid_date', sa.Date(), nullable=True),
            sa.Column('salary_expense_id', sa.Integer(), nullable=True, index=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_installments_employee', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['advance_expense_id'], ['expenses.id'], name='fk_installments_advance', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['salary_expense_id'], ['expenses.id'], name='fk_installments_salary', ondelete='SET NULL'),
        )
        print("   ✓ employee_advance_installments")
    except Exception as e:
        print(f"   ⏩ employee_advance_installments ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 7) إضافة أعمدة للجداول الموجودة
    # ═══════════════════════════════════════════════════════════════
    print("\n7️⃣ إضافة أعمدة جديدة للجداول الموجودة...")
    
    # إضافة code و fields_meta لجدول expense_types
    try:
        op.add_column('expense_types', sa.Column('code', sa.String(length=50), nullable=True))
        op.create_index('ix_expense_types_code', 'expense_types', ['code'], unique=True)
        print("   ✓ expense_types.code")
    except Exception as e:
        print(f"   ⏩ expense_types.code ({e})")
    
    try:
        op.add_column('expense_types', sa.Column('fields_meta', sa.Text(), nullable=True))
        print("   ✓ expense_types.fields_meta")
    except Exception as e:
        print(f"   ⏩ expense_types.fields_meta ({e})")
    
    # إضافة branch_id و site_id للموظفين
    try:
        op.add_column('employees', sa.Column('branch_id', sa.Integer(), nullable=True, index=True))
        op.create_foreign_key('fk_employees_branch', 'employees', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
        print("   ✓ employees.branch_id")
    except Exception as e:
        print(f"   ⏩ employees.branch_id ({e})")
    
    try:
        op.add_column('employees', sa.Column('site_id', sa.Integer(), nullable=True, index=True))
        op.create_foreign_key('fk_employees_site', 'employees', 'sites', ['site_id'], ['id'], ondelete='SET NULL')
        print("   ✓ employees.site_id")
    except Exception as e:
        print(f"   ⏩ employees.site_id ({e})")
    
    # إضافة hire_date للموظفين
    try:
        op.add_column('employees', sa.Column('hire_date', sa.Date(), nullable=True, index=True))
        print("   ✓ employees.hire_date")
    except Exception as e:
        print(f"   ⏩ employees.hire_date ({e})")
    
    # إضافة branch_id و site_id للمصاريف
    try:
        op.add_column('expenses', sa.Column('branch_id', sa.Integer(), nullable=True, index=True))
        op.create_foreign_key('fk_expenses_branch', 'expenses', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
        print("   ✓ expenses.branch_id")
    except Exception as e:
        print(f"   ⏩ expenses.branch_id ({e})")
    
    try:
        op.add_column('expenses', sa.Column('site_id', sa.Integer(), nullable=True, index=True))
        op.create_foreign_key('fk_expenses_site', 'expenses', 'sites', ['site_id'], ['id'], ondelete='SET NULL')
        print("   ✓ expenses.site_id")
    except Exception as e:
        print(f"   ⏩ expenses.site_id ({e})")
    
    # إضافة branch_id للمستودعات
    try:
        op.add_column('warehouses', sa.Column('branch_id', sa.Integer(), nullable=True, index=True))
        op.create_foreign_key('fk_warehouses_branch', 'warehouses', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
        print("   ✓ warehouses.branch_id")
    except Exception as e:
        print(f"   ⏩ warehouses.branch_id ({e})")
    
    # إضافة condition لـ sale_return_lines
    try:
        op.add_column('sale_return_lines', sa.Column('condition', sa.String(length=20), nullable=True, server_default=sa.text("'good'"), index=True))
        print("   ✓ sale_return_lines.condition")
    except Exception as e:
        print(f"   ⏩ sale_return_lines.condition ({e})")
    
    # إضافة liability_party لـ sale_return_lines
    try:
        op.add_column('sale_return_lines', sa.Column('liability_party', sa.String(length=20), nullable=True, index=True))
        print("   ✓ sale_return_lines.liability_party")
    except Exception as e:
        print(f"   ⏩ sale_return_lines.liability_party ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 8) إنشاء فرع رئيسي إذا لم يكن موجود
    # ═══════════════════════════════════════════════════════════════
    print("\n8️⃣ إنشاء الفرع الرئيسي...")
    
    try:
        result = conn.execute(sa.text("SELECT COUNT(*) FROM branches")).fetchone()
        if result and result[0] == 0:
            conn.execute(sa.text("""
                INSERT INTO branches (name, code, is_active, currency, is_archived, created_at, updated_at)
                VALUES ('الفرع الرئيسي', 'MAIN', 1, 'ILS', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            branch_id = conn.execute(sa.text("SELECT last_insert_rowid()")).fetchone()[0]
            print(f"   ✓ تم إنشاء الفرع الرئيسي (ID: {branch_id})")
            
            # ربط المصاريف والمستودعات بالفرع
            conn.execute(sa.text(f"UPDATE expenses SET branch_id = {branch_id} WHERE branch_id IS NULL"))
            conn.execute(sa.text(f"UPDATE warehouses SET branch_id = {branch_id} WHERE branch_id IS NULL"))
            conn.execute(sa.text(f"UPDATE employees SET branch_id = {branch_id} WHERE branch_id IS NULL"))
            print(f"   ✓ ربط البيانات بالفرع الرئيسي")
        else:
            print("   ⏩ يوجد فروع مسبقاً")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # 9) زرع أنواع المصاريف
    # ═══════════════════════════════════════════════════════════════
    print("\n9️⃣ زرع أنواع المصاريف...")
    
    base_types = [
        ("SALARY", "رواتب", "مصروف رواتب وأجور", {"required": ["employee_id", "period"], "optional": ["description"]}),
        ("EMPLOYEE_ADVANCE", "سلفة موظف", "سلف الموظفين", {"required": ["employee_id"], "optional": ["period", "description"]}),
        ("RENT", "إيجار", "مصروف إيجار", {"required": ["warehouse_id"], "optional": ["period", "beneficiary_name", "description"]}),
        ("UTILITIES", "مرافق", "مصروف مرافق", {"required": ["utility_account_id"], "optional": ["period", "description"]}),
        ("MAINTENANCE", "صيانة", "مصروف صيانة", {"required": [], "optional": ["warehouse_id", "beneficiary_name", "description"]}),
        ("FUEL", "وقود", "مصروف وقود", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OFFICE", "لوازم مكتبية", "مصروف لوازم مكتبية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("INSURANCE", "تأمين", "مصروف تأمين", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("GOV_FEES", "رسوم حكومية", "مصروف رسوم وضرائب", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("TRAVEL", "سفر ومهمات", "مصروف سفر", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("TRAINING", "تدريب", "مصروف تدريب", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("MARKETING", "تسويق وإعلانات", "مصروف تسويق", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("SOFTWARE", "اشتراكات تقنية", "مصروف برمجيات", {"required": ["period"], "optional": ["beneficiary_name", "description"]}),
        ("BANK_FEES", "رسوم بنكية", "مصروف رسوم بنكية", {"required": ["beneficiary_name"], "optional": ["description"]}),
        ("HOSPITALITY", "ضيافة", "مصروف ضيافة", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("HOME_EXPENSE", "مصاريف بيتية", "مصروفات بيتية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OWNERS_EXPENSE", "مصاريف المالكين", "مصروفات المالكين", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("ENTERTAINMENT", "ترفيه", "مصروف ترفيهي", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("SHIP_INSURANCE", "تأمين شحنة", "مصروف تأمين شحن", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CUSTOMS", "جمارك", "مصروف جمارك", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_IMPORT_TAX", "ضريبة استيراد", "مصروف ضرائب استيراد", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_FREIGHT", "شحن", "مصروف شحن", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CLEARANCE", "تخليص جمركي", "مصروف تخليص جمركي", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_HANDLING", "مناولة وأرضيات", "مصروف مناولة/أرضيات", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_PORT_FEES", "رسوم موانئ", "مصروف رسوم ميناء/مطار", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_STORAGE", "تخزين مؤقت", "مصروف تخزين مؤقت", {"required": ["shipment_id"], "optional": ["description"]}),
        ("OTHER", "أخرى", "مصروفات أخرى", {"required": [], "optional": ["beneficiary_name", "description"]}),
    ]
    
    seeded = 0
    for code, arabic_name, gl_account, fields in base_types:
        try:
            meta = {"gl_account_code": gl_account}
            meta.update(fields)
            meta_json = json.dumps(meta, ensure_ascii=False)
            
            row = conn.execute(sa.text("SELECT id FROM expense_types WHERE code = :c"), {"c": code}).fetchone()
            if not row:
                conn.execute(sa.text("""
                    INSERT INTO expense_types (name, description, is_active, code, fields_meta)
                    VALUES (:n, :d, 1, :c, :m)
                """), {"n": arabic_name, "d": arabic_name, "c": code, "m": meta_json})
                seeded += 1
            else:
                conn.execute(sa.text("""
                    UPDATE expense_types 
                    SET fields_meta = :m, code = :c, description = :d
                    WHERE id = :id
                """), {"m": meta_json, "c": code, "d": arabic_name, "id": row[0]})
        except:
            pass
    
    print(f"   ✓ تم زرع {seeded} نوع جديد وتحديث الأنواع الموجودة")
    
    # ═══════════════════════════════════════════════════════════════
    # 10) إنشاء جداول SaaS (مطابقة للـ Models)
    # ═══════════════════════════════════════════════════════════════
    print("\n🔟 إنشاء جداول SaaS...")
    
    try:
        op.create_table(
            'saas_plans',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('price_monthly', sa.Numeric(10, 2), nullable=False),
            sa.Column('price_yearly', sa.Numeric(10, 2), nullable=True),
            sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'USD'")),
            sa.Column('max_users', sa.Integer(), nullable=True),
            sa.Column('max_invoices', sa.Integer(), nullable=True),
            sa.Column('storage_gb', sa.Integer(), nullable=True),
            sa.Column('features', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column('is_popular', sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column('sort_order', sa.Integer(), nullable=True, server_default=sa.text("0")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        print("   ✓ saas_plans")
    except Exception as e:
        print(f"   ⏩ saas_plans ({e})")
    
    try:
        op.create_table(
            'saas_subscriptions',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False, index=True),
            sa.Column('plan_id', sa.Integer(), nullable=False, index=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'trial'")),
            sa.Column('start_date', sa.DateTime(), nullable=False),
            sa.Column('end_date', sa.DateTime(), nullable=True),
            sa.Column('trial_end_date', sa.DateTime(), nullable=True),
            sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_by', sa.Integer(), nullable=True),
            sa.Column('cancellation_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name='fk_subscriptions_customer', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['plan_id'], ['saas_plans.id'], name='fk_subscriptions_plan', ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], name='fk_subscriptions_cancelled_by', ondelete='SET NULL'),
        )
        print("   ✓ saas_subscriptions")
    except Exception as e:
        print(f"   ⏩ saas_subscriptions ({e})")
    
    try:
        op.create_table(
            'saas_invoices',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('invoice_number', sa.String(length=50), nullable=False, unique=True, index=True),
            sa.Column('subscription_id', sa.Integer(), nullable=False, index=True),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'USD'")),
            sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
            sa.Column('due_date', sa.DateTime(), nullable=True),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.Column('payment_method', sa.String(length=50), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['subscription_id'], ['saas_subscriptions.id'], name='fk_invoices_subscription', ondelete='CASCADE'),
        )
        print("   ✓ saas_invoices")
    except Exception as e:
        print(f"   ⏩ saas_invoices ({e})")
    
    # ═══════════════════════════════════════════════════════════════
    # 11) إنشاء Indexes إضافية للأداء
    # ═══════════════════════════════════════════════════════════════
    print("\n1️⃣1️⃣ إنشاء Indexes للأداء...")
    
    # Indexes للجداول الجديدة
    indexes_to_create = [
        ("ix_branches_code", "branches", ["code"]),
        ("ix_branches_name", "branches", ["name"]),
        ("ix_sites_code", "sites", ["code"]),
        ("ix_sites_name", "sites", ["name"]),
        ("ix_user_branches_user_id", "user_branches", ["user_id"]),
        ("ix_user_branches_branch_id", "user_branches", ["branch_id"]),
        ("ix_employee_deductions_deduction_type", "employee_deductions", ["deduction_type"]),
        ("ix_employee_deductions_is_active", "employee_deductions", ["is_active"]),
        ("ix_employee_advances_fully_paid", "employee_advances", ["fully_paid"]),
        ("ix_employee_advance_installments_due_date", "employee_advance_installments", ["due_date"]),
        ("ix_employee_advance_installments_paid", "employee_advance_installments", ["paid"]),
    ]
    
    created = 0
    for idx_name, table, columns in indexes_to_create:
        try:
            conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({', '.join(columns)})"))
            created += 1
        except:
            pass
    
    print(f"   ✓ تم إنشاء/التحقق من {created} index")
    
    print("\n" + "=" * 80)
    print("✅ تم تطبيق التهجير الشامل بنجاح!")
    print("=" * 80)


def downgrade():
    """عكس التهجير"""
    print("⚠️  Downgrade غير مدعوم لهذا التهجير الشامل")
    pass

