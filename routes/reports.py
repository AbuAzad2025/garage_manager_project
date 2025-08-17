# File: routes/reports.py
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import class_mapper

from models import (
    Expense,
    OnlinePreOrder,
    Sale,
    ServiceRequest,
    Customer,
)
from reports import advanced_report, ar_aging_report, sales_report

reports_bp = Blueprint(
    "reports_bp",
    __name__,
    url_prefix="/reports",
    template_folder="templates/reports",
)

_MODEL_LOOKUP = {
    "Expense": Expense,
    "Shop": OnlinePreOrder,
    "Sale": Sale,
    "Service": ServiceRequest,
    "AR_Aging": Customer,
}

def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

@reports_bp.route("/", methods=["GET"], endpoint="universal")
def universal():
    model_names = list(_MODEL_LOOKUP.keys())
    return render_template("reports/index.html", model_names=model_names)

@reports_bp.route("/custom", methods=["GET"], endpoint="custom")
def custom():
    model_names = list(_MODEL_LOOKUP.keys())
    return render_template("reports/index.html", model_names=model_names)

@reports_bp.route("/dynamic", methods=["POST", "GET"], endpoint="dynamic_report")
def dynamic_report():
    model_names = list(_MODEL_LOOKUP.keys())

    if request.method == "POST":
        model_name = request.form.get("table")
        start_raw = request.form.get("start_date")
        end_raw = request.form.get("end_date")
        start_date = _parse_date(start_raw)
        end_date = _parse_date(end_raw)

        like_filters = {
            k: v
            for k, v in request.form.items()
            if k not in ("table", "date_field", "start_date", "end_date", "csrf_token", "selected_fields")
            and v not in (None, "")
        }

        rpt = advanced_report(
            model=_MODEL_LOOKUP.get(model_name),
            date_field=request.form.get("date_field") or None,
            start_date=start_date,
            end_date=end_date,
            filters=None,
            like_filters=like_filters,
            columns=request.form.getlist("selected_fields"),
            aggregates={"count": ["id"]},
        )
        return render_template(
            "reports/dynamic.html",
            data=rpt.get("data"),
            summary=rpt.get("summary"),
            columns=request.form.getlist("selected_fields"),
            model_names=model_names,
            selected_table=model_name,
            start_date=start_raw,
            end_date=end_raw,
        )

    return render_template(
        "reports/dynamic.html",
        data=None,
        summary=None,
        columns=[],
        model_names=model_names,
        selected_table=model_names[0] if model_names else None,
        start_date="",
        end_date="",
    )

@reports_bp.route("/sales", methods=["GET"])
def sales():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = sales_report(start, end)
    return render_template("reports/sales.html", **rpt)

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
    )

@reports_bp.route("/api/model_fields", methods=["GET"])
def model_fields():
    model_name = request.args.get("model", "").strip()
    if not model_name:
        return jsonify({"models": list(_MODEL_LOOKUP.keys())}), 200

    model = _MODEL_LOOKUP.get(model_name)
    if not model:
        return jsonify({"error": "Unknown model", "models": list(_MODEL_LOOKUP.keys())}), 404

    mapper = class_mapper(model)
    columns = [col.key for col in mapper.columns]
    date_fields = [c for c in columns if "date" in c]
    return jsonify({"columns": columns, "date_fields": date_fields}), 200
