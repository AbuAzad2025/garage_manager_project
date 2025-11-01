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
    زرع/تحديث أنواع المصاريف الأساسية دائماً عند الإقلاع (idempotent).
    لا يعتمد على ملفات التهجير؛ آمن للتشغيل عدة مرات.
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
        ("OTHER", "أخرى", {"required": [], "optional": ["beneficiary_name", "description"]}),
    ]

    default_gl_map = {
        "SALARY": "مصروف رواتب وأجور",
        "RENT": "مصروف إيجار",
        "UTILITIES": "مصروف مرافق",
        "MAINTENANCE": "مصروف صيانة",
        "FUEL": "مصروف وقود",
        "OFFICE": "مصروف لوازم مكتبية",
        "INSURANCE": "مصروف تأمين",
        "GOV_FEES": "مصروف رسوم وضرائب",
        "TRAVEL": "مصروف سفر",
        "TRAINING": "مصروف تدريب",
        "MARKETING": "مصروف تسويق",
        "SOFTWARE": "مصروف برمجيات",
        "BANK_FEES": "مصروف رسوم بنكية",
        "OTHER": "مصروفات أخرى",
        "EMPLOYEE_ADVANCE": "سلف الموظفين",
        "HOSPITALITY": "مصروف ضيافة",
        "HOME_EXPENSE": "مصروفات بيتية",
        "OWNERS_EXPENSE": "مصروفات المالكين",
        "ENTERTAINMENT": "مصروف ترفيهي",
        "SHIP_INSURANCE": "مصروف تأمين شحن",
        "SHIP_CUSTOMS": "مصروف جمارك",
        "SHIP_IMPORT_TAX": "مصروف ضرائب استيراد",
        "SHIP_FREIGHT": "مصروف شحن",
        "SHIP_CLEARANCE": "مصروف تخليص جمركي",
        "SHIP_HANDLING": "مصروف مناولة/أرضيات",
        "SHIP_PORT_FEES": "مصروف رسوم ميناء/مطار",
        "SHIP_STORAGE": "مصروف تخزين مؤقت",
    }

    try:
        conn = db.session.bind
        if conn is None:
            conn = db.session.connection()
        
        try:
            conn.execute(sa_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_types_code ON expense_types (code)"))
        except Exception:
            pass

        for code, arabic_name, meta in base_types:
            meta = dict(meta or {})
            meta.setdefault("gl_account_code", default_gl_map.get(code))
            meta_json = _json_dumps(meta)

            row = conn.execute(sa_text("SELECT id FROM expense_types WHERE code = :c OR name = :n"), {"c": code, "n": arabic_name}).fetchone()
            if row:
                conn.execute(sa_text("UPDATE expense_types SET name=:n, is_active=1, fields_meta=:m, code=:c WHERE id=:id"), {"n": arabic_name, "m": meta_json, "c": code, "id": row[0]})
            else:
                conn.execute(sa_text("INSERT INTO expense_types (name, description, is_active, code, fields_meta) VALUES (:n, :d, 1, :c, :m)"), {"n": arabic_name, "d": arabic_name, "c": code, "m": meta_json})
        
        try:
            db.session.commit()
        except:
            db.session.rollback()
    except Exception as e:
        from models import ExpenseType
        for code, arabic_name, meta in base_types:
            try:
                meta = dict(meta or {})
                meta.setdefault("gl_account_code", default_gl_map.get(code))
                meta_json = _json_dumps(meta)
                
                existing = ExpenseType.query.filter((ExpenseType.code == code) | (ExpenseType.name == arabic_name)).first()
                if existing:
                    existing.name = arabic_name
                    existing.fields_meta = meta_json
                    existing.code = code
                    existing.is_active = True
                else:
                    new_type = ExpenseType(
                        name=arabic_name,
                        description=arabic_name,
                        code=code,
                        fields_meta=meta_json,
                        is_active=True
                    )
                    db.session.add(new_type)
            except:
                pass
        try:
            db.session.commit()
        except:
            try:
                db.session.rollback()
            except:
                pass


