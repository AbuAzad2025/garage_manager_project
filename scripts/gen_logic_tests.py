# scripts/gen_logic_tests.py
import os, sys, json, re, importlib, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts"
MODELS_SNAPSHOT = ART / "models_snapshot.json"
DOMAIN_SIGS     = ART / "domain_signatures.json"
BUSINESS_RULES  = ART / "business_rules.md"

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def mod_try(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

def has_model(models_mod, cls):
    return hasattr(models_mod, cls)

def find_table(meta, name):
    for t in meta.get("tables", []):
        if t["table"].lower() == name.lower():
            return t
    return None

def table_has_check(table, pattern):
    if not table: return False
    for ck in table.get("checks", []):
        if re.search(pattern, ck.get("sqltext",""), re.I):
            return True
    return False

def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def main():
    models_snapshot = load_json(MODELS_SNAPSHOT)
    domain_sigs     = load_json(DOMAIN_SIGS)
    rules_md        = BUSINESS_RULES.read_text(encoding="utf-8") if BUSINESS_RULES.exists() else ""

    # محاولة استيراد أساس المشروع
    app_mod = mod_try("app") or mod_try("wsgi") or mod_try("application") or mod_try("garage_manager.app")
    if not app_mod or not hasattr(app_mod, "create_app"):
        raise SystemExit("create_app غير موجود. تأكد من وجوده بأحد app/wsgi/application.")

    extensions = mod_try("extensions") or mod_try("garage_manager.extensions")
    if not extensions or not hasattr(extensions, "db"):
        raise SystemExit("extensions.db غير موجود.")

    models_mod = mod_try("models") or mod_try("garage_manager.models")
    if not models_mod:
        raise SystemExit("لم أستطع استيراد models.")

    # تتبّع وجود بعض الجداول/الموديلات
    t_payments   = find_table(models_snapshot, "payments")
    t_stocklevel = find_table(models_snapshot, "stocklevels") or find_table(models_snapshot, "stock_level") or find_table(models_snapshot, "stock_levels")
    t_invoices   = find_table(models_snapshot, "invoices")

    wants_payment_positive = table_has_check(t_payments, r"amount\s*>\s*0")
    wants_no_negative_stock = table_has_check(t_stocklevel, r"quantity\s*>=?\s*0|quantity\s*>=\s*0")

    # ====== 1) اختبارات الدفع ======
    test_payments = f'''
    # -*- coding: utf-8 -*-
    import pytest
    from extensions import db
    import models as M

    _HAS_PAYMENT = hasattr(M, "Payment")

    @pytest.mark.skipif(not _HAS_PAYMENT, reason="Payment model not found")
    def test_payment_amount_must_be_positive(app):
        {"assert " + str(wants_payment_positive) if t_payments else "pytest.skip('payments table not in snapshot')"}
        if not {str(bool(wants_payment_positive))}:
            pytest.skip("no DB check for positive amount; rule not enforced at DB level")
        with app.app_context():
            p = M.Payment()
            # حاول نجعل القيمة صفر/سالب ونتوقع فشل عند commit
            p.amount = 0
            try:
                db.session.add(p); db.session.commit()
            except Exception:
                db.session.rollback()
            else:
                db.session.rollback()
                pytest.fail("Expected error on non-positive amount")
    '''

    # ====== 2) اختبارات المخزون ======
    test_stock = f'''
    # -*- coding: utf-8 -*-
    import pytest
    from extensions import db
    import models as M

    _HAS_STOCK = hasattr(M, "StockLevel") and hasattr(M, "Product") and hasattr(M, "Warehouse")

    @pytest.mark.skipif(not _HAS_STOCK, reason="Stock models not found")
    def test_no_negative_stock_allowed(app):
        {"assert " + str(bool(t_stocklevel)) if t_stocklevel else "pytest.skip('stock table not in snapshot')"}
        with app.app_context():
            prod = M.Product(name="__tprod__")
            wh   = M.Warehouse(name="__twh__")
            db.session.add_all([prod, wh]); db.session.commit()
            sl = M.StockLevel(product_id=prod.id, warehouse_id=wh.id, quantity=0)
            db.session.add(sl); db.session.commit()
            sl.quantity = -1
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            else:
                db.session.rollback()
                {"pytest.fail('Expected error on negative stock')" if wants_no_negative_stock else "pytest.skip('No DB-level check for negative stock')"}
    '''

    # ====== 3) اختبارات الفواتير (تغيّر الحالة) — سكيبت إذا غير متاح ======
    test_invoices = '''
    # -*- coding: utf-8 -*-
    import pytest, inspect
    import models as M

    HAS_INVOICE = hasattr(M, "Invoice")
    @pytest.mark.skipif(not HAS_INVOICE, reason="Invoice model not found")
    def test_invoice_has_status_field():
        inv = M.Invoice()
        assert hasattr(inv, "status"), "Invoice.status مفقود"
    '''

    # ====== 4) تقارير الأعمار — إن وجد دالة ======
    has_age_bucket = "reports" in domain_sigs and "functions" in domain_sigs.get("reports", {}) and any(f.get("name") == "age_bucket" for f in domain_sigs["reports"]["functions"])
    test_reports = f'''
    # -*- coding: utf-8 -*-
    import pytest
    {"from reports import age_bucket" if has_age_bucket else ""}
    @pytest.mark.skipif({str(not has_age_bucket)}, reason="age_bucket غير موجود")
    def test_age_bucket_edges():
        # مثال بسيط: فقط يتأكد أن الدالة تُرجع سترينغ
        assert isinstance(age_bucket(0), str)
    '''

    out_dir = ROOT / "tests" / "unit"
    write(out_dir / "test_payments_logic.py", textwrap.dedent(test_payments))
    write(out_dir / "test_stock_logic.py",    textwrap.dedent(test_stock))
    write(out_dir / "test_invoices_logic.py", textwrap.dedent(test_invoices))
    write(out_dir / "test_reports_logic.py",  textwrap.dedent(test_reports))

    print("✅ Generated tests in", out_dir)

if __name__ == "__main__":
    main()
