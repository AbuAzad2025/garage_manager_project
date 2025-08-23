from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, render_template, request, jsonify, flash, Response
from werkzeug.exceptions import BadRequest
from sqlalchemy.orm import class_mapper

from models import (
    Customer,
    Supplier,
    Partner,
    Product,
    Warehouse,
    StockLevel,
    Expense,
    OnlinePreOrder,
    OnlinePayment,
    Sale,
    ServiceRequest,
    Invoice,
    Payment,
    Shipment,
)
from reports import (
    advanced_report,
    ar_aging_report,
    sales_report,
    payment_summary_report,
)

reports_bp = Blueprint(
    "reports_bp",
    __name__,
    url_prefix="/reports",
    template_folder="templates/reports",
)

def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

_MODEL_LOOKUP = {
    "Sale": Sale,
    "Expense": Expense,
    "Invoice": Invoice,
    "Payment": Payment,
    "ServiceRequest": ServiceRequest,
    "OnlinePreOrder": OnlinePreOrder,
    "OnlinePayment": OnlinePayment,
    "Shipment": Shipment,
    "Customer": Customer,
    "Supplier": Supplier,
    "Partner": Partner,
    "Product": Product,
    "Warehouse": Warehouse,
    "StockLevel": StockLevel,
}

_DEFAULT_DATE_FIELD = {
    "Sale": "sale_date",
    "Expense": "date",
    "Invoice": "invoice_date",
    "Payment": "payment_date",
    "ServiceRequest": "received_at",
    "OnlinePreOrder": "created_at",
    "OnlinePayment": "created_at",
    "Shipment": "shipment_date",
    "Customer": "created_at",
    "Supplier": "created_at",
    "Partner": "created_at",
    "Product": "created_at",
    "Warehouse": "created_at",
    "StockLevel": "updated_at",
}

MODEL_LABELS = {
    "Sale": "المبيعات",
    "Expense": "المصاريف",
    "Invoice": "الفواتير",
    "Payment": "المدفوعات",
    "ServiceRequest": "طلبات الصيانة",
    "OnlinePreOrder": "الطلبات المسبقة (أونلاين)",
    "OnlinePayment": "مدفوعات أونلاين",
    "Shipment": "الشحنات",
    "Customer": "العملاء",
    "Supplier": "الموردون",
    "Partner": "الشركاء",
    "Product": "المنتجات",
    "Warehouse": "المستودعات",
    "StockLevel": "المخزون",
}

FIELD_LABELS: Dict[str, str] = {
    "id": "المعرف",
    "sale_number": "رقم الفاتورة",
    "sale_date": "تاريخ البيع",
    "customer_id": "العميل",
    "seller_id": "المندوب",
    "preorder_id": "طلب مسبق",
    "status": "الحالة",
    "payment_status": "حالة الدفع",
    "currency": "العملة",
    "discount_total": "إجمالي الخصم",
    "tax_rate": "نسبة الضريبة",
    "total_amount": "الإجمالي",
    "shipping_cost": "تكلفة الشحن",
    "billing_address": "عنوان الفاتورة",
    "shipping_address": "عنوان الشحن",
    "notes": "ملاحظات",
    "created_at": "تاريخ الإنشاء",
    "updated_at": "آخر تحديث",
    "date": "التاريخ",
    "type_id": "نوع المصروف",
    "amount": "المبلغ",
    "employee_id": "الموظف",
    "warehouse_id": "المستودع",
    "partner_id": "الشريك",
    "desc": "الوصف",
    "is_paid": "مدفوع؟",
    "invoice_date": "تاريخ الفاتورة",
    "total_invoiced": "إجمالي الفواتير",
    "net_balance": "الصافي",
    "total_paid": "المدفوع",
    "balance": "الرصيد",
    "payment_date": "تاريخ الدفع",
    "method": "طريقة الدفع",
    "received_at": "تاريخ الاستلام",
    "priority": "الأولوية",
    "mechanic_id": "الميكانيكي",
    "service_cost": "تكلفة الخدمة",
    "shipment_date": "تاريخ الشحنة",
    "number": "رقم الشحنة",
    "origin": "المنشأ",
    "destination": "الوجهة",
    "carrier": "الناقل",
    "tracking": "رقم التتبع",
    "value_before": "قيمة قبل التكاليف",
    "total_value": "القيمة الإجمالية",
    "product": "المنتج",
    "warehouse": "المستودع",
    "quantity": "الكمية",
    "reserved": "محجوز",
    "available": "المتوفر",
    "min_stock": "الحد الأدنى",
    "max_stock": "الحد الأقصى",
}

def _ensure_model(name: str):
    model = _MODEL_LOOKUP.get(name)
    if not model:
        raise BadRequest("نموذج غير معروف")
    return model

@reports_bp.route("/", methods=["GET"], endpoint="universal")
@reports_bp.route("", methods=["GET"], endpoint="index")
def reports_index():
    return render_template(
        "reports/index.html",
        model_names=list(_MODEL_LOOKUP.keys()),
        defaults=_DEFAULT_DATE_FIELD,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/dynamic", methods=["GET", "POST"])
def dynamic_report():
    model_names = list(_MODEL_LOOKUP.keys())
    if request.method == "POST":
        table = (request.form.get("table") or "").strip()
        selected_fields = request.form.getlist("selected_fields") or []
        date_field = request.form.get("date_field") or None
        start_date = _parse_date(request.form.get("start_date"))
        end_date = _parse_date(request.form.get("end_date"))
        try:
            model = _ensure_model(table)
        except BadRequest as e:
            flash(str(e), "danger")
            return render_template(
                "reports/dynamic.html",
                data=None,
                summary=None,
                columns=[],
                model_names=model_names,
                selected_table=None,
                defaults=_DEFAULT_DATE_FIELD,
                start_date=request.form.get("start_date", ""),
                end_date=request.form.get("end_date", ""),
                FIELD_LABELS=FIELD_LABELS,
                MODEL_LABELS=MODEL_LABELS,
            ), 400
        like_filters = {
            k: v for k, v in request.form.items()
            if k not in {"table", "date_field", "start_date", "end_date", "csrf_token", "selected_fields"}
            and v not in (None, "")
        }
        try:
            rpt = advanced_report(
                model=model,
                date_field=date_field or None,
                start_date=start_date,
                end_date=end_date,
                filters=None,
                like_filters=like_filters or None,
                columns=selected_fields or None,
                aggregates={"count": ["id"]},
            )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "reports/dynamic.html",
                data=None,
                summary=None,
                columns=selected_fields,
                model_names=model_names,
                selected_table=table,
                defaults=_DEFAULT_DATE_FIELD,
                start_date=request.form.get("start_date", ""),
                end_date=request.form.get("end_date", ""),
                FIELD_LABELS=FIELD_LABELS,
                MODEL_LABELS=MODEL_LABELS,
            ), 400
        return render_template(
            "reports/dynamic.html",
            data=rpt.get("data") or [],
            summary=rpt.get("summary") or {},
            columns=selected_fields,
            model_names=model_names,
            selected_table=table,
            defaults=_DEFAULT_DATE_FIELD,
            start_date=request.form.get("start_date", ""),
            end_date=request.form.get("end_date", ""),
            FIELD_LABELS=FIELD_LABELS,
            MODEL_LABELS=MODEL_LABELS,
        )
    return render_template(
        "reports/dynamic.html",
        data=None,
        summary=None,
        columns=[],
        model_names=model_names,
        selected_table=model_names[0] if model_names else None,
        defaults=_DEFAULT_DATE_FIELD,
        start_date="",
        end_date="",
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/sales", methods=["GET"])
def sales():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = sales_report(start, end)
    return render_template(
        "reports/sales.html",
        **rpt,
        start=request.args.get("start",""),
        end=request.args.get("end",""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/payments-summary", methods=["GET"])
def payments_summary():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = payment_summary_report(start, end)
    return render_template(
        "reports/payments.html",
        **rpt,
        start=request.args.get("start",""),
        end=request.args.get("end",""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/ar-aging", methods=["GET"])
def ar_aging():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ar_aging_report(start_date=start, end_date=end)
    return render_template(
        "reports/ar_aging.html",
        data=rpt.get("data", []),
        totals=rpt.get("totals", {}),
        as_of=rpt.get("as_of"),
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/api/model_fields", methods=["GET"])
def model_fields():
    model_name = (request.args.get("model") or "").strip()
    if not model_name:
        return jsonify({"models": list(_MODEL_LOOKUP.keys())}), 200
    model = _MODEL_LOOKUP.get(model_name)
    if not model:
        return jsonify({"error": "Unknown model", "models": list(_MODEL_LOOKUP.keys())}), 404
    mapper = class_mapper(model)
    columns = [col.key for col in mapper.columns]
    lower = {c: c.lower() for c in columns}
    date_fields = [c for c in columns if ("date" in lower[c]) or (lower[c].endswith("_at")) or ("created_at" in lower[c]) or ("updated_at" in lower[c])]
    return jsonify({"columns": columns, "date_fields": date_fields}), 200

@reports_bp.route("/api/dynamic", methods=["POST"])
def api_dynamic():
    payload = request.get_json(silent=True) or {}
    table = payload.get("table")
    model = _ensure_model(table)
    rpt = advanced_report(
        model=model,
        date_field=payload.get("date_field") or None,
        start_date=_parse_date(payload.get("start_date")),
        end_date=_parse_date(payload.get("end_date")),
        filters=payload.get("filters"),
        like_filters=payload.get("like_filters"),
        columns=payload.get("columns"),
        aggregates=payload.get("aggregates"),
    )
    return jsonify(rpt), 200

def _csv_from_rows(rows: List[Dict[str, Any]]):
    if not rows:
        return ""
    import io, csv
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return output.getvalue()

@reports_bp.route("/export/dynamic.csv", methods=["POST"])
def export_dynamic_csv():
    table = request.form.get("table")
    model = _ensure_model(table)
    rpt = advanced_report(
        model=model,
        date_field=request.form.get("date_field") or None,
        start_date=_parse_date(request.form.get("start_date")),
        end_date=_parse_date(request.form.get("end_date")),
        like_filters={
            k: v
            for k, v in request.form.items()
            if k not in ("table", "date_field", "start_date", "end_date", "csrf_token", "selected_fields")
            and v not in (None, "")
        },
        columns=request.form.getlist("selected_fields") or None,
        aggregates={"count": ["id"]},
    )
    csv_text = _csv_from_rows(rpt.get("data") or [])
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=dynamic_report.csv"},
    )

@reports_bp.route("/export/ar_aging.csv", methods=["GET"])
def export_ar_aging_csv():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ar_aging_report(start_date=start, end_date=end)
    rows = []
    for item in rpt.get("data", []):
        row = {
            "customer": item.get("customer"),
            "0-30": item.get("buckets", {}).get("0-30", 0),
            "31-60": item.get("buckets", {}).get("31-60", 0),
            "61-90": item.get("buckets", {}).get("61-90", 0),
            "90+": item.get("buckets", {}).get("90+", 0),
            "total": item.get("balance", 0),
        }
        rows.append(row)
    csv_text = _csv_from_rows(rows)
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ar_aging.csv"},
    )
