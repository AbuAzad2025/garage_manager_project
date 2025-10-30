"""expense_types_comprehensive_seed

Revision ID: expense_types_seed_002
Revises: employee_enhance_001
Create Date: 2025-10-30 15:00:00.000000

تهجير مخصص لزرع أنواع المصاريف الثابتة مع fields_meta وحسابات دفتر الأستاذ
"""
from alembic import op
import sqlalchemy as sa
import json


revision = 'expense_types_seed_002'
down_revision = 'employee_enhance_001'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # التأكد من وجود الأعمدة code و fields_meta
    try:
        conn.execute(sa.text("SELECT code FROM expense_types LIMIT 1"))
    except Exception:
        # إضافة الأعمدة إن لم تكن موجودة
        with op.batch_alter_table('expense_types', schema=None) as batch_op:
            batch_op.add_column(sa.Column('code', sa.String(length=50), nullable=True))
            try:
                batch_op.add_column(sa.Column('fields_meta', sa.JSON(), nullable=True))
            except Exception:
                batch_op.add_column(sa.Column('fields_meta', sa.Text(), nullable=True))
        
        conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_types_code ON expense_types (code)"))

    # زرع أنواع المصاريف الكاملة
    base_types = [
        # تشغيلية عامة
        ("SALARY", "رواتب", "مصروف رواتب وأجور", {"required": ["employee_id", "period"], "optional": ["description"]}),
        ("RENT", "إيجار", "مصروف إيجار", {"required": ["period"], "optional": ["warehouse_id", "tax_invoice_number", "description"]}),
        ("UTILITIES", "مرافق (كهرباء/ماء/اتصالات)", "مصروف مرافق", {"required": ["period", "utility_account_id"], "optional": ["tax_invoice_number", "description"]}),
        ("MAINTENANCE", "صيانة", "مصروف صيانة", {"required": [], "optional": ["warehouse_id", "stock_adjustment_id", "description"]}),
        ("FUEL", "وقود", "مصروف وقود", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OFFICE", "لوازم مكتبية", "مصروف لوازم مكتبية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("INSURANCE", "تأمين", "مصروف تأمين", {"required": ["period"], "optional": ["beneficiary_name", "tax_invoice_number", "description"]}),
        ("GOV_FEES", "رسوم حكومية/ضرائب", "مصروف رسوم وضرائب", {"required": ["period"], "optional": ["beneficiary_name", "tax_invoice_number", "description"]}),
        ("TRAVEL", "سفر/مهمات", "مصروف سفر", {"required": ["employee_id", "period"], "optional": ["beneficiary_name", "description"]}),
        ("TRAINING", "تدريب", "مصروف تدريب", {"required": [], "optional": ["period", "beneficiary_name", "description"]}),
        ("MARKETING", "تسويق/إعلانات", "مصروف تسويق", {"required": ["beneficiary_name"], "optional": ["period", "description"]}),
        ("SOFTWARE", "اشتراكات تقنية/برمجيات", "مصروف برمجيات", {"required": ["period"], "optional": ["beneficiary_name", "description"]}),
        ("BANK_FEES", "رسوم بنكية", "مصروف رسوم بنكية", {"required": ["beneficiary_name"], "optional": ["description"]}),
        ("OTHER", "أخرى", "مصروفات أخرى", {"required": [], "optional": ["beneficiary_name", "description"]}),

        # سلف وخصومات
        ("EMPLOYEE_ADVANCE", "سلفة موظف", "سلف الموظفين", {"required": ["employee_id"], "optional": ["period", "description"]}),
        ("HOSPITALITY", "ضيافة", "مصروف ضيافة", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("HOME_EXPENSE", "مصاريف بيتية", "مصروفات بيتية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OWNERS_EXPENSE", "مصاريف المالكين", "مصروفات المالكين", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("ENTERTAINMENT", "مصاريف ترفيهية", "مصروف ترفيهي", {"required": [], "optional": ["beneficiary_name", "description"]}),

        # مصاريف الشحنات (shipment_id إلزامي)
        ("SHIP_INSURANCE", "تأمين شحنة", "مصروف تأمين شحن", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CUSTOMS", "جمارك", "مصروف جمارك", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_IMPORT_TAX", "ضريبة استيراد", "مصروف ضرائب استيراد", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_FREIGHT", "شحن (بحري/جوي/بري)", "مصروف شحن", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CLEARANCE", "تخليص جمركي", "مصروف تخليص جمركي", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_HANDLING", "أرضيات/مناولة", "مصروف مناولة/أرضيات", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_PORT_FEES", "رسوم ميناء/مطار", "مصروف رسوم ميناء/مطار", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_STORAGE", "تخزين مؤقت", "مصروف تخزين مؤقت", {"required": ["shipment_id"], "optional": ["description"]}),
    ]

    for code, arabic_name, gl_account, meta in base_types:
        meta_dict = dict(meta or {})
        meta_dict['gl_account_code'] = gl_account
        meta_json = json.dumps(meta_dict, ensure_ascii=False)

        # استخدام INSERT OR REPLACE (SQLite-safe upsert)
        row = conn.execute(sa.text("SELECT id, name FROM expense_types WHERE code = :c OR name = :n"), {"c": code, "n": arabic_name}).fetchone()
        if row:
            conn.execute(sa.text("UPDATE expense_types SET name=:n, description=:d, is_active=1, code=:c, fields_meta=:m WHERE id=:id"), 
                {"n": arabic_name, "d": arabic_name, "c": code, "m": meta_json, "id": row[0]})
        else:
            conn.execute(sa.text("INSERT INTO expense_types (name, description, is_active, code, fields_meta) VALUES (:n, :d, 1, :c, :m)"), 
                {"n": arabic_name, "d": arabic_name, "c": code, "m": meta_json})


def downgrade():
    # إزالة الأنواع المزروعة (اختياري)
    pass

