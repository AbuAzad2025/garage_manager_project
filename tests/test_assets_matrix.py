# -*- coding: utf-8 -*-
import os
import re
import pytest

# ========= خريطة القوالب ↔ JS/CSS حسب الجدول =========

TEMPLATE_JS = {
    # shop
    "shop/catalog.html":       ["static/js/shop.js"],
    "shop/pay_online.html":    ["static/js/shop.js"],
    "shop/cart.html":          ["static/js/shop.js"],

    # payments
    "payments/list.html":      ["static/js/payments.js"],
    "payments/form.html":      ["static/js/payment_form.js"],

    # reports (ربط reporting.js كما اتفقنا)
    "reports/index.html":              ["static/js/reporting.js"],
    "reports/sales.html":              ["static/js/reporting.js"],
    "reports/dynamic.html":            ["static/js/reporting.js"],
    "reports/dynamic_report.html":     ["static/js/reporting.js"],

    # service
    "service/list.html":       ["static/js/service.js"],
    "service/new.html":        ["static/js/service.js"],
    "service/view.html":       ["static/js/service.js"],

    # sales
    "sales/list.html":         ["static/js/sales.js"],
    "sales/form.html":         ["static/js/sales.js"],

    # customers
    "customers/list.html":     ["static/js/customers.js"],
    "customers/detail.html":   ["static/js/customers.js"],
    "customers/new.html":      ["static/js/customers.js"],
    "customers/edit.html":     ["static/js/customers.js"],
    "customers/advanced_filter.html": ["static/js/customers.js"],
    "customers/account_statement.html": ["static/js/customers.js"],

    # shipments
    "warehouses/shipments.html":     ["static/js/shipments.js"],
    "warehouses/shipment_form.html": ["static/js/shipments.js"],

    # warehouse
    "warehouses/products.html":      ["static/js/warehouses.js"],
    "warehouses/transfers_form.html":["static/js/warehouses.js"],
    "warehouses/transfers_list.html":["static/js/warehouses.js"],
    "parts/preorders_list.html":     ["static/js/warehouses.js"],
    "parts/preorder_form.html":      ["static/js/warehouses.js"],
    "parts/preorder_detail.html":    ["static/js/warehouses.js"],

    # expenses (إضافة ربط للـ JS)
    "expenses/expenses_list.html":   ["static/js/expenses.js"],
    "expenses/expense_form.html":    ["static/js/expenses.js"],

    # vendors (suppliers/partners)
    "vendors/suppliers/list.html":   ["static/js/vendors.js"],
    "vendors/partners/list.html":    ["static/js/vendors.js"],

    # عام عبر الـ layout
    "base.html":                ["static/js/app.js"],
}

TEMPLATE_CSS = {
    "base.html":                ["static/css/style.css"],  # + AdminLTE/Plugins عام
    "shop/catalog.html":        ["static/css/shop.css"],
    "shop/pay_online.html":     ["static/css/shop.css"],

    "sales/list.html":          ["static/css/sales.css"],
    "sales/form.html":          ["static/css/sales.css"],

    "service/list.html":        ["static/css/service.css"],
    "service/view.html":        ["static/css/service.css", "static/css/print.css"],  # للطباعة إن وُجد إيصال
    "service/receipt.html":     ["static/css/print.css"],

    "reports/index.html":       ["static/css/reporting.css"],
    "reports/sales.html":       ["static/css/reporting.css"],
    # ملاحظة mismatch: dynamic_report.html مقابل dynamic.html — سنختبر كلاهما:
    "reports/dynamic.html":         ["static/css/reporting.css"],
    "reports/dynamic_report.html":  ["static/css/reporting.css"],

    "warehouses/shipments.html":    ["static/css/shipments.css"],
    "warehouses/shipment_form.html":["static/css/shipments.css"],

    "warehouses/products.html":     ["static/css/warehouses.css"],
    "warehouses/transfers_form.html":["static/css/warehouses.css"],
    "warehouses/transfers_list.html":["static/css/warehouses.css"],
}

# ========= أدوات لقراءة القوالب من Jinja loader دون رندر =========

def _get_template_source(app, template_name):
    """أرجع سورس القالب من jinja_loader إن وُجد، وإلا None."""
    try:
        source, _, _ = app.jinja_loader.get_source(app.jinja_env, template_name)
        return source
    except Exception:
        return None

def _assert_any_in(source, needles, filelabel):
    missing = [n for n in needles if (n not in source)]
    assert not missing, f"مفقود في {filelabel}: {missing}"

# ========= تحقّق من وجود ملفات الأصول (JS/CSS) في مجلد static =========

@pytest.mark.parametrize("path", [
    # JS
    "static/js/app.js",
    "static/js/shop.js",
    "static/js/payments.js",
    "static/js/payment_form.js",
    "static/js/vendors.js",
    "static/js/expenses.js",
    "static/js/service.js",
    "static/js/sales.js",
    "static/js/customers.js",
    "static/js/shipments.js",
    "static/js/warehouses.js",
    "static/js/reporting.js",

    # CSS
    "static/css/style.css",
    "static/css/shop.css",
    "static/css/sales.css",
    "static/css/service.css",
    "static/css/print.css",
    "static/css/reporting.css",
    "static/css/shipments.css",
    "static/css/warehouses.css",
])
def test_assets_files_exist_on_disk(app, path):
    full = os.path.join(app.root_path, path)
    assert os.path.exists(full), f"Asset مفقود: {path}"

# ========= تحقّق من تضمين JS في القوالب المحددة =========

@pytest.mark.parametrize("template,js_list", sorted(TEMPLATE_JS.items()))
def test_templates_include_js(app, template, js_list):
    src = _get_template_source(app, template)
    if src is None:
        pytest.skip(f"القالب غير موجود: {template}")
    # نبحث عن أي من الطرق الشائعة للإدراج (url_for أو مسار مباشر)
    for js in js_list:
        ok_patterns = [
            js,  # مسار مباشر
            "url_for('static', filename='%s')" % js.split("static/")[-1],
            "url_for(\"static\", filename=\"%s\")" % js.split("static/")[-1],
        ]
        assert any(p in src for p in ok_patterns), f"JS {js} غير مضمَّن في {template}"

# ========= تحقّق من تضمين CSS في القوالب المحددة =========

@pytest.mark.parametrize("template,css_list", sorted(TEMPLATE_CSS.items()))
def test_templates_include_css(app, template, css_list):
    src = _get_template_source(app, template)
    if src is None:
        pytest.skip(f"القالب غير موجود: {template}")
    for css in css_list:
        ok_patterns = [
            css,
            "url_for('static', filename='%s')" % css.split("static/")[-1],
            "url_for(\"static\", filename=\"%s\")" % css.split("static/")[-1],
        ]
        assert any(p in src for p in ok_patterns), f"CSS {css} غير مضمَّن في {template}"

# ========= تحقّق سريع على mismatch التقارير =========

def test_reports_dynamic_template_exists(app):
    has_dynamic = _get_template_source(app, "reports/dynamic.html") is not None
    has_dynamic_report = _get_template_source(app, "reports/dynamic_report.html") is not None
    assert has_dynamic or has_dynamic_report, (
        "يجب توفير واحد على الأقل من: reports/dynamic.html أو reports/dynamic_report.html"
    )
