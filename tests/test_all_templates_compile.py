# -*- coding: utf-8 -*-
import os
import re
import pytest
from jinja2 import TemplateSyntaxError

# =====================================================================
# قائمة القوالب الكاملة (من الجدول) — لا نريد أي قالب يفلت
# =====================================================================
TEMPLATES = sorted(set([
    # users
    "users/list.html",
    "users/detail.html",
    "users/_form.html",
    "users/form.html",

    # customers
    "customers/list.html",
    "customers/detail.html",
    "customers/analytics.html",
    "customers/new.html",
    "customers/edit.html",
    "customers/import.html",
    "customers/account_statement.html",
    "customers/advanced_filter.html",
    "customers/vcf_export.html",

    # sales
    "sales/dashboard.html",
    "sales/list.html",
    "sales/form.html",
    "sales/detail.html",
    "sales/payments.html",
    "sales/receipt.html",

    # notes
    "notes/list.html",
    "notes/_form.html",
    "notes/detail.html",

    # shop
    "shop/catalog.html",
    "shop/pay_online.html",
    "shop/cart.html",
    "shop/preorder_list.html",
    "shop/preorder_receipt.html",

    # auth
    "auth/login.html",
    "auth/register.html",
    "auth/customer_register.html",
    "auth/password_reset_request.html",
    "auth/password_reset.html",

    # expenses
    "expenses/employees_list.html",
    "expenses/employee_form.html",
    "expenses/types_list.html",
    "expenses/type_form.html",
    "expenses/expenses_list.html",
    "expenses/detail.html",
    "expenses/expense_form.html",

    # service
    "service/list.html",
    "service/dashboard.html",
    "service/new.html",
    "service/view.html",
    "service/receipt.html",

    # api — لا قوالب

    # main
    "dashboard.html",
    "restore_db.html",

    # reports
    "reports/index.html",
    "reports/sales.html",
    "reports/ar_aging.html",
    # mismatch المحتمل:
    "reports/dynamic.html",
    "reports/dynamic_report.html",

    # vendors
    "vendors/suppliers/list.html",
    "vendors/suppliers/form.html",
    "vendors/partners/list.html",
    "vendors/partners/form.html",
    "payments/list.html",

    # shipments
    "warehouses/shipments.html",
    "warehouses/shipment_form.html",
    "warehouses/shipment_detail.html",

    # warehouse
    "warehouses/list.html",
    "warehouses/form.html",
    "warehouses/detail.html",
    "warehouses/products.html",
    "warehouses/add_product.html",
    "warehouses/import_products.html",
    "warehouses/transfers_list.html",
    "warehouses/transfers_form.html",
    "parts/card.html",
    "parts/preorders_list.html",
    "parts/preorder_form.html",
    "parts/preorder_detail.html",

    # payments
    "payments/list.html",
    "payments/form.html",
    "payments/view.html",
    "payments/receipt.html",
    "payments/_entity_fields.html",

    # permissions / roles
    "permissions/list.html",
    "permissions/form.html",
    "roles/list.html",
    "roles/form.html",

    # base/layout (لإحكام الربط العام)
    "base.html",
]))

# =====================================================================
# أدوات
# =====================================================================

INCLUDE_RE = re.compile(r"""{%\s*(?:include|extends)\s*['"]([^'"]+)['"]\s*%}""")

def _get_template_source(app, name):
    """أعد سورس القالب من jinja_loader، أو None إن لم يوجد."""
    try:
        src, _, _ = app.jinja_loader.get_source(app.jinja_env, name)
        return src
    except Exception:
        return None

def _list_includes(src):
    """أعد كل الأهداف داخل include/extends في القالب المعطى."""
    return [m.group(1).strip() for m in INCLUDE_RE.finditer(src or "")]

DEPRECATED_TEMPLATES = {"sales/payments.html"}  # أُلغي بعد الدفع الموحّد
TEMPLATES = [t for t in TEMPLATES if t not in DEPRECATED_TEMPLATES]
DEPRECATED_TEMPLATES.add("users/_form.html")
TEMPLATES = [t for t in TEMPLATES if t not in DEPRECATED_TEMPLATES]

@pytest.mark.parametrize("tpl", [t for t in TEMPLATES if t not in DEPRECATED_TEMPLATES])
def test_template_exists(app, tpl):
    """القالب يجب أن يكون موجودًا في jinja_loader."""
    src = _get_template_source(app, tpl)
    if src is None:
        pytest.fail(f"القالب غير موجود: {tpl}")

@pytest.mark.parametrize("tpl", TEMPLATES)
def test_template_compiles(app, tpl):
    """تحليل Jinja للـ AST للتأكد من عدم وجود أخطاء صياغة."""
    src = _get_template_source(app, tpl)
    if src is None:
        pytest.fail(f"القالب غير موجود: {tpl}")
    try:
        app.jinja_env.parse(src)
    except TemplateSyntaxError as e:
        pytest.fail(f"Syntax error في {tpl}: {e}")

@pytest.mark.parametrize("tpl", TEMPLATES)
def test_template_includes_and_extends_exist(app, tpl):
    """أي include/extends داخل القالب يجب أن يشير لقالب موجود."""
    src = _get_template_source(app, tpl)
    if src is None:
        pytest.fail(f"القالب غير موجود: {tpl}")
    targets = _list_includes(src)
    for target in targets:
        # نتسامح مع وجود كلا الاسمين في التقارير (واحد يكفي)
        if target in ("reports/dynamic.html", "reports/dynamic_report.html"):
            # لا شيء؛ سيتم التحقق كملف بمفرده أيضًا
            pass
        t_src = _get_template_source(app, target)
        assert t_src is not None, f"{tpl} يشير إلى قالب غير موجود عبر include/extends: {target}"

def test_reports_dynamic_one_of_two_exists(app):
    """تحقق صريح للـ mismatch؛ وجود واحد يكفي لتجاوز الاختبار."""
    has_dynamic = _get_template_source(app, "reports/dynamic.html") is not None
    has_dynamic_report = _get_template_source(app, "reports/dynamic_report.html") is not None
    assert has_dynamic or has_dynamic_report, (
        "يجب توفير واحد على الأقل من: reports/dynamic.html أو reports/dynamic_report.html"
    )
