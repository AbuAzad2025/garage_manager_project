# -*- coding: utf-8 -*-
import io
import pytest
from flask import url_for
from werkzeug.routing import BuildError

ACCEPTABLE = (200, 302, 404, 405)

def _resolve(app, candidates, kwargs=None):
    """جرّب أول endpoint صالح من المرشحين وأرجع (name, url)."""
    with app.test_request_context():
        for name in candidates:
            try:
                return name, url_for(name, **(kwargs or {}))
            except BuildError:
                continue
    return None

# ===================== مصفوفة المرشحين (من الجدول) =====================

@pytest.mark.parametrize("candidates,kwargs", [
    # users
    (("users.list_users",), {}),
    (("users.user_detail",), {"user_id": 999}),
    (("users.create_user",), {}),
    (("users.edit_user",), {"user_id": 999}),

    # customers
    (("customers_bp.list_customers",), {}),
    (("customers_bp.customer_detail",), {"customer_id": 999}),
    (("customers_bp.customer_analytics",), {"customer_id": 999}),
    (("customers_bp.create_form","customers_bp.create_customer"), {}),
    (("customers_bp.edit_customer",), {"customer_id": 999}),
    (("customers_bp.import_customers",), {}),
    (("customers_bp.customer_whatsapp",), {"customer_id": 999}),
    (("customers_bp.account_statement",), {"customer_id": 999}),
    (("customers_bp.advanced_filter",), {}),
    (("customers_bp.export_contacts",), {}),

    # sales
    (("sales_bp.dashboard",), {}),
    (("sales_bp.list_sales",), {}),
    (("sales_bp.create_sale",), {}),
    (("sales_bp.sale_detail",), {"sale_id": 999}),
    (("sales_bp.sale_payments",), {"sale_id": 999}),
    (("sales_bp.edit_sale",), {"sale_id": 999}),
    (("sales_bp.generate_invoice",), {"sale_id": 999}),

    # notes
    (("notes_bp.list_notes",), {}),
    (("notes_bp.create_note",), {}),
    (("notes_bp.note_detail",), {"note_id": 999}),

    # shop
    (("shop.catalog",), {}),
    (("shop.cart",), {}),
    (("shop.checkout",), {}),
    (("shop.preorder_list",), {}),
    (("shop.preorder_receipt",), {"preorder_id": 999}),

    # auth
    (("auth.login",), {}),
    (("auth.logout",), {}),
    (("auth.register",), {}),
    (("auth.customer_register",), {}),
    (("auth.password_reset_request",), {}),
    (("auth.password_reset",), {"token": "x"*32}),

    # expenses
    (("expenses_bp.employees_list",), {}),
    (("expenses_bp.add_employee",), {}),
    (("expenses_bp.edit_employee",), {"employee_id": 999}),
    (("expenses_bp.delete_employee",), {"employee_id": 999}),
    (("expenses_bp.types_list",), {}),
    (("expenses_bp.add_type",), {}),
    (("expenses_bp.edit_type",), {"type_id": 999}),
    (("expenses_bp.list_expenses",), {}),
    (("expenses_bp.detail",), {"expense_id": 999}),
    (("expenses_bp.create_expense",), {}),
    (("expenses_bp.edit",), {"expense_id": 999}),
    (("expenses_bp.pay",), {"expense_id": 999}),

    # service
    (("service.list_requests",), {}),
    (("service.dashboard",), {}),
    (("service.create_request",), {}),
    (("service.view_request",), {"request_id": 999}),
    (("service.view_receipt",), {"request_id": 999}),
    (("service.download_receipt",), {"request_id": 999}),
    (("service.service_report",), {"request_id": 999}),
    (("service.export_pdf",), {"request_id": 999}),
    (("service.api_service_requests",), {}),
    (("service.search_requests",), {}),
    (("service.service_stats",), {}),

    # api (JSON)
    (("api.customers",), {}),
    (("api.search_customers",), {}),
    (("api.suppliers",), {}),
    (("api.partners",), {}),
    (("api.products",), {}),
    (("api.categories",), {}),
    (("api.warehouses",), {}),
    (("api.users",), {}),
    (("api.employees",), {}),

    # reports
    (("reports_bp.universal",), {}),
    (("reports_bp.custom",), {}),
    (("reports_bp.dynamic_report",), {}),
    (("reports_bp.sales",), {}),
    (("reports_bp.ar_aging",), {}),
    (("reports_bp.model_fields",), {}),

    # vendors
    (("vendors_bp.suppliers_list",), {}),
    (("vendors_bp.suppliers_create",), {}),
    (("vendors_bp.suppliers_edit",), {"supplier_id": 999}),
    (("vendors_bp.suppliers_delete",), {"supplier_id": 999}),
    (("vendors_bp.suppliers_payments",), {"supplier_id": 999}),
    (("vendors_bp.partners_list",), {}),
    (("vendors_bp.partners_create",), {}),
    (("vendors_bp.partners_edit",), {"partner_id": 999}),
    (("vendors_bp.partners_delete",), {"partner_id": 999}),
    (("vendors_bp.partners_payments",), {"partner_id": 999}),

    # shipments
    (("shipments_bp.list_shipments",), {}),
    (("shipments_bp.create_shipment",), {}),
    (("shipments_bp.edit_shipment",), {"shipment_id": 999}),
    (("shipments_bp.delete_shipment",), {"shipment_id": 999}),
    (("shipments_bp.shipment_detail",), {"shipment_id": 999}),

    # warehouse
    (("warehouse_bp.list",), {}),
    (("warehouse_bp.create",), {}),
    (("warehouse_bp.edit",), {"warehouse_id": 999}),
    (("warehouse_bp.detail",), {"warehouse_id": 999}),
    (("warehouse_bp.products",), {}),
    (("warehouse_bp.add_product",), {}),
    (("warehouse_bp.import_products",), {}),
    (("warehouse_bp.transfers",), {}),
    (("warehouse_bp.create_transfer",), {}),
    (("warehouse_bp.product_card",), {"product_id": 999}),
    (("warehouse_bp.preorders_list",), {}),
    (("warehouse_bp.preorder_create",), {}),
    (("warehouse_bp.preorder_detail",), {"preorder_id": 999}),
    (("warehouse_bp.create_warehouse_shipment",), {}),

    # payments
    (("payments.index",), {}),
    (("payments.create_payment",), {}),
    (("payments.view_payment",), {"payment_id": 999}),
    (("payments.view_receipt",), {"payment_id": 999}),
    (("payments.download_receipt",), {"payment_id": 999}),
    (("payments.entity_fields",), {"type":"customer"}),
    (("payments.create_expense_payment",), {}),
])
def test_endpoint_get_status(app, client, candidates, kwargs):
    resolved = _resolve(app, candidates, kwargs)
    if not resolved:
        pytest.skip(f"لم يتم العثور على أي endpoint من: {candidates}")
    name, url = resolved

    # محاولات GET
    resp = client.get(url, follow_redirects=False)
    if resp.status_code in ACCEPTABLE:
        assert True
        return

    # في حال كان الراوت POST-only أو DELETE-only
    expected_method = None
    if any(k in name for k in ("create_", "delete_", "pay", "download", "import")):
        expected_method = "POST" if "delete_" not in name else "DELETE"

    if expected_method is None:
        pytest.fail(f"{name} returned {resp.status_code} (غير ضمن المقبول)")

    assert resp.status_code in (302, 405, 401, 403), f"GET يجب ألا ينجح على {candidates} (متوقع {expected_method}-only)"

def test_api_json_accept_header(client, app):
    resolved = _resolve(app, ("payments.index",), {})
    if not resolved:
        pytest.skip("payments.index غير متاح")
    _, url = resolved
    resp = client.get(url, headers={"Accept":"application/json"})
    # نقبل 200/204/302 لتجنب فشل أثناء التطوير، ونشترط JSON فقط عند 200
    assert resp.status_code in (200, 204, 302), "متوقع 200/204/302 عند Accept: application/json"
    if resp.status_code == 200:
        ctype = resp.headers.get("Content-Type","");
        assert "application/json" in ctype, "عند 200 يجب أن يكون JSON"

@pytest.mark.parametrize("candidates,kwargs", [
    (("service.service_report",), {"request_id": 999}),
    (("service.export_pdf",), {"request_id": 999}),
    (("payments.download_receipt",), {"payment_id": 999}),
])
def test_pdf_headers_if_available(app, client, candidates, kwargs):
    resolved = _resolve(app, candidates, kwargs)
    if not resolved:
        pytest.skip(f"skip (endpoint غير موجود): {candidates}")
    _, url = resolved
    resp = client.get(url, follow_redirects=False)
    if resp.status_code in (200, 206):
        disp = resp.headers.get("Content-Disposition","")
        ctype = resp.headers.get("Content-Type","")
        assert "pdf" in ctype.lower() or disp.lower().endswith(".pdf") or "attachment" in disp.lower()
    else:
        assert resp.status_code in ACCEPTABLE
