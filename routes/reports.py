# File: routes/reports.py
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List

from flask import Blueprint, render_template, request, jsonify, flash, Response
from sqlalchemy.orm import class_mapper
from werkzeug.exceptions import BadRequest

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
    "AR_Aging": Customer,  # واجهة فقط؛ الحساب الفعلي في ar_aging_report
}


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _ensure_model(name: str):
    model = _MODEL_LOOKUP.get(name)
    if not model:
        raise BadRequest("نموذج غير معروف")
    return model


@reports_bp.route("/", methods=["GET"], endpoint="universal")
@reports_bp.route("/custom", methods=["GET"], endpoint="custom")
def universal():
    model_names = list(_MODEL_LOOKUP.keys())
    return render_template("reports/index.html", model_names=model_names)


@reports_bp.route("/dynamic", methods=["GET", "POST"], endpoint="dynamic_report")
def dynamic_report():
    model_names = list(_MODEL_LOOKUP.keys())

    if request.method == "POST":
        table = request.form.get("table", "").strip()
        date_field = request.form.get("date_field") or None
        start_date = _parse_date(request.form.get("start_date"))
        end_date = _parse_date(request.form.get("end_date"))
        selected_fields = request.form.getlist("selected_fields") or []

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
                start_date=request.form.get("start_date", ""),
                end_date=request.form.get("end_date", ""),
            ), 400

        # build like_filters from remaining fields
        like_filters = {
            k: v
            for k, v in request.form.items()
            if k
            not in (
                "table",
                "date_field",
                "start_date",
                "end_date",
                "csrf_token",
                "selected_fields",
            )
            and v not in (None, "")
        }

        try:
            rpt = advanced_report(
                model=model,
                date_field=date_field,
                start_date=start_date,
                end_date=end_date,
                filters=None,
                like_filters=like_filters,
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
                start_date=request.form.get("start_date", ""),
                end_date=request.form.get("end_date", ""),
            ), 400

        return render_template(
            "reports/dynamic.html",
            data=rpt.get("data"),
            summary=rpt.get("summary"),
            columns=selected_fields,
            model_names=model_names,
            selected_table=table,
            start_date=request.form.get("start_date", ""),
            end_date=request.form.get("end_date", ""),
        )

    # GET
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


# ---------- JSON APIs & CSV Export ----------
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

    # تسطيح البيانات للـ CSV
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
