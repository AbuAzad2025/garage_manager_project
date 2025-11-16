from __future__ import annotations
import json
from typing import Any
from sqlalchemy import text as sa_text


def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps({}, ensure_ascii=False)


def seed_core_expense_types(db):
    """
    ✅ Bootstrap: أنواع المصاريف الأساسية
    - يعمل مرة واحدة فقط عند أول تشغيل
    - لا يعدل الأنواع الموجودة (يحترم التعديلات اليدوية)
    - يمكن إضافة أنواع جديدة من الواجهة بعد التشغيل
    """
    from models import ExpenseType
    
    base_types = [
        ("SALARY", "رواتب", {"required": ["employee_id", "period"], "optional": ["description"]}),
        ("EMPLOYEE_ADVANCE", "سلفة موظف", {"required": ["employee_id"], "optional": ["period", "description"]}),
        ("RENT", "إيجار", {"required": ["warehouse_id"], "optional": ["period", "beneficiary_name", "description"]}),
        ("UTILITIES", "مرافق", {"required": ["utility_account_id"], "optional": ["period", "description"]}),
        ("MAINTENANCE", "صيانة", {"required": [], "optional": ["warehouse_id", "beneficiary_name", "description"]}),
        ("FUEL", "وقود", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OFFICE", "لوازم مكتبية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("INSURANCE", "تأمين", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("GOV_FEES", "رسوم حكومية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("TRAVEL", "سفر ومهمات", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("TRAINING", "تدريب", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("MARKETING", "تسويق وإعلانات", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("SOFTWARE", "اشتراكات تقنية", {"required": ["period"], "optional": ["beneficiary_name", "description"]}),
        ("BANK_FEES", "رسوم بنكية", {"required": ["beneficiary_name"], "optional": ["description"]}),
        ("HOSPITALITY", "ضيافة", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("HOME_EXPENSE", "مصاريف بيتية", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("OWNERS_EXPENSE", "مصاريف المالكين", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("ENTERTAINMENT", "ترفيه", {"required": [], "optional": ["beneficiary_name", "description"]}),
        ("SHIP_INSURANCE", "تأمين شحنة", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CUSTOMS", "جمارك", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_IMPORT_TAX", "ضريبة استيراد", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_FREIGHT", "شحن", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_CLEARANCE", "تخليص جمركي", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_HANDLING", "مناولة وأرضيات", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_PORT_FEES", "رسوم موانئ", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SHIP_STORAGE", "تخزين مؤقت", {"required": ["shipment_id"], "optional": ["description"]}),
        ("SUPPLIER_EXPENSE", "مصروف مورد", {"required": ["supplier_id"], "optional": ["description", "beneficiary_name"]}),
        ("PARTNER_EXPENSE", "مصروف شريك", {"required": ["partner_id"], "optional": ["description", "beneficiary_name"]}),
        ("OTHER", "أخرى", {"required": [], "optional": ["beneficiary_name", "description"]}),
    ]

    default_gl_map = {
        "SALARY": "6100_SALARIES",
        "EMPLOYEE_ADVANCE": "6110_EMPLOYEE_ADVANCES",
        "RENT": "6200_RENT",
        "UTILITIES": "6300_UTILITIES",
        "MAINTENANCE": "6400_MAINTENANCE",
        "FUEL": "6500_FUEL",
        "OFFICE": "6600_OFFICE",
        "INSURANCE": "6700_INSURANCE",
        "GOV_FEES": "6800_GOV_FEES",
        "TRAVEL": "6900_TRAVEL",
        "TRAINING": "6910_TRAINING",
        "MARKETING": "6920_MARKETING",
        "SOFTWARE": "6930_SOFTWARE",
        "BANK_FEES": "6940_BANK_FEES",
        "HOSPITALITY": "6950_HOSPITALITY",
        "HOME_EXPENSE": "6960_HOME_EXPENSE",
        "OWNERS_EXPENSE": "6970_OWNER_CURRENT",
        "ENTERTAINMENT": "6980_ENTERTAINMENT",
        "SUPPLIER_EXPENSE": "5100_SUPPLIER_EXPENSES",
        "PARTNER_EXPENSE": "5200_PARTNER_EXPENSES",
        "SHIP_INSURANCE": "5510_SHIP_INSURANCE",
        "SHIP_CUSTOMS": "5520_SHIP_CUSTOMS",
        "SHIP_IMPORT_TAX": "5530_SHIP_IMPORT_TAX",
        "SHIP_FREIGHT": "5540_SHIP_FREIGHT",
        "SHIP_CLEARANCE": "5550_SHIP_CLEARANCE",
        "SHIP_HANDLING": "5560_SHIP_HANDLING",
        "SHIP_PORT_FEES": "5570_SHIP_PORT_FEES",
        "SHIP_STORAGE": "5580_SHIP_STORAGE",
        "OTHER": "5000_EXPENSES",
    }

    try:
        conn = db.session.bind
        if conn is None:
            conn = db.session.connection()
        
        try:
            conn.execute(sa_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_types_code ON expense_types (code)"))
        except Exception:
            pass

        added = 0
        skipped = 0
        
        for code, arabic_name, meta in base_types:
            meta = dict(meta or {})
            meta.setdefault("gl_account_code", default_gl_map.get(code))
            meta_json = _json_dumps(meta)

            row = conn.execute(sa_text("SELECT id FROM expense_types WHERE code = :c"), {"c": code}).fetchone()
            
            if row:
                skipped += 1
            else:
                conn.execute(sa_text("INSERT INTO expense_types (name, description, is_active, code, fields_meta) VALUES (:n, :d, 1, :c, :m)"), {"n": arabic_name, "d": arabic_name, "c": code, "m": meta_json})
                added += 1
        
        try:
            db.session.commit()
            if added > 0:
                print(f"✅ Bootstrap: Added {added} new expense types (skipped {skipped} existing)")
        except Exception:
            db.session.rollback()
    except Exception as e:
        from models import ExpenseType
        for code, arabic_name, meta in base_types:
            try:
                meta = dict(meta or {})
                meta.setdefault("gl_account_code", default_gl_map.get(code))
                meta_json = _json_dumps(meta)
                
                existing = ExpenseType.query.filter(ExpenseType.code == code).first()
                if not existing:
                    new_type = ExpenseType(
                        name=arabic_name,
                        description=arabic_name,
                        code=code,
                        fields_meta=meta_json,
                        is_active=True
                    )
                    db.session.add(new_type)
            except Exception:
                pass
        try:
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass


