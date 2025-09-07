# routes/payments.py
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import io
import uuid
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for, session
from flask_login import current_user, login_required
from sqlalchemy import func, text, and_, case, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import PaymentForm
from models import (
    Customer,
    Expense,
    Invoice,
    Partner,
    Payment,
    PaymentDirection,
    PaymentMethod,
    PaymentSplit,
    PaymentStatus,
    PreOrder,
    PreOrderStatus,
    Sale,
    ServiceRequest,
    ServiceStatus,
    Shipment,
    Supplier,
    SupplierLoanSettlement,
)
from utils import log_audit, permission_required, update_entity_balance
from weasyprint import HTML, CSS

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

TWOPLACES = Decimal("0.01")
def D(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

def q2(x) -> Decimal:
    return D(x).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def _ensure_payment_number(pmt: Payment) -> None:
    if getattr(pmt, "payment_number", None):
        return
    base_dt = getattr(pmt, "payment_date", None) or datetime.utcnow()
    prefix = base_dt.strftime("PMT%Y%m%d")
    cnt = db.session.execute(
        text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"),
        {"pfx": f"{prefix}-%"},
    ).scalar() or 0
    pmt.payment_number = f"{prefix}-{cnt + 1:04d}"

def _sum_splits_decimal(splits) -> Decimal:
    total = Decimal("0")
    for s in splits or []:
        total += q2(getattr(s, "amount", 0))  # كل split يُقرب لقرشين أولاً
    return q2(total)

def _validate_splits_total_decimal(target_total, splits):
    if not splits:
        return
    tt = q2(target_total)
    ss = _sum_splits_decimal(splits)
    if tt != ss:
        raise ValueError("splits_mismatch: مجموع التجزئات لا يساوي إجمالي الدفعة (بعد التقريب).")

def _norm_currency(v):
    return (v or "ILS").strip().upper()

def _get_or_404(model, ident, options=None):
    q = db.session.query(model)
    if options:
        for opt in options:
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

def _norm_dir(val):
    if val is None:
        return None
    v = val.value if hasattr(val, "value") else val
    v = str(v).strip().upper()
    if v in ("IN", "INCOMING", "INCOME", "RECEIVE"):
        return "IN"
    if v in ("OUT", "OUTGOING", "PAY", "PAYMENT", "EXPENSE"):
        return "OUT"
    return v

def _dir_to_db(v: str | None):
    vv = _norm_dir(v)
    if vv == "IN":
        return PaymentDirection.INCOMING.value
    if vv == "OUT":
        return PaymentDirection.OUTGOING.value
    return vv

def _clean_details(d: dict | None):
    if not d:
        return None
    cleaned = {}
    for k, v in d.items():
        if v in (None, "", []):
            continue
        if isinstance(v, (date, datetime)):
            cleaned[k] = v.isoformat()
        else:
            cleaned[k] = str(v)
    return cleaned or None

def _val(x):
    return getattr(x, "value", x)

def _coerce_method(v):
    s = (_val(v) or "").strip().lower()
    try:
        return PaymentMethod(s)
    except Exception:
        return PaymentMethod.CASH

def _sync_payment_method_with_splits(pmt: Payment):
    try:
        splits = list(pmt.splits or [])
    except Exception:
        splits = []
    if not splits:
        if not getattr(pmt, "method", None):
            pmt.method = PaymentMethod.CASH
        return
    first = splits[0]
    new_m = getattr(first, "method", None)
    new_m_val = getattr(new_m, "value", new_m)
    if new_m_val and new_m_val != getattr(pmt, "method", None):
        pmt.method = new_m_val

def _wants_json():
    accept = request.headers.get("Accept", "") or ""
    return (
        request.args.get("format") == "json"
        or ("application/json" in accept and "text/html" not in accept)
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

def _render_payment_receipt_pdf(payment: Payment) -> bytes:
    html = render_template("payments/receipt.html", payment=payment, now=datetime.utcnow())
    css_inline = """
    @page { size: A4; margin: 14mm; }
    html, body { direction: rtl; font-family: 'Cairo', 'Noto Naskh Arabic', Arial, sans-serif; font-size: 12px; }
    h1,h2,h3 { margin: 0 0 8px 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 6px 8px; border-bottom: 1px solid #ddd; }
    .muted { color: #666; }
    """
    try:
        return HTML(string=html, base_url=request.url_root).write_pdf(stylesheets=[CSS(string=css_inline)])
    except Exception:
        current_app.logger.exception("payment.receipt_pdf_failed", extra={"payment_id": getattr(payment, "id", None)})
        return HTML(string=html, base_url=request.url_root).write_pdf()

MAX_SEARCH_LIMIT = 25

@payments_bp.route("/entity-search", methods=["GET"])
@login_required
@permission_required("manage_payments")
def entity_search():
    t = (request.args.get("type") or "").strip().upper()
    q = (request.args.get("q") or "").strip()
    limit = min(request.args.get("limit", 8, type=int) or 8, MAX_SEARCH_LIMIT)

    if len(q) < 2:
        return jsonify(results=[])

    like = f"%{q}%"

    def rows_for(model, extra_cols=("phone", "mobile", "email")):
        conds = [getattr(model, "name").ilike(like)]
        for c in extra_cols:
            col = getattr(model, c, None)
            if col is not None:
                conds.append(col.ilike(like))
        return (
            db.session.query(model)
            .filter(or_(*conds))
            .order_by(getattr(model, "name").asc())
            .limit(limit)
            .all()
        )

    results = []
    if t == "CUSTOMER":
        rows = rows_for(Customer)
        results = [{"id": r.id, "label": r.name, "extra": (getattr(r, "phone", "") or getattr(r, "mobile", "") or "")} for r in rows]
    elif t == "SUPPLIER":
        rows = rows_for(Supplier)
        results = [{"id": r.id, "label": r.name, "extra": (getattr(r, "phone", "") or getattr(r, "mobile", "") or "")} for r in rows]
    elif t == "PARTNER":
        rows = rows_for(Partner)
        results = [{"id": r.id, "label": r.name, "extra": ""} for r in rows]
    elif t == "LOAN":
        qdigits = "".join(ch for ch in q if ch.isdigit())
        qry = (
            db.session.query(SupplierLoanSettlement, Supplier.name.label("supplier_name"))
            .join(Supplier, Supplier.id == SupplierLoanSettlement.supplier_id)
        )
        conds = []
        if qdigits:
            try:
                conds.append(SupplierLoanSettlement.id == int(qdigits))
            except Exception:
                pass
        conds.append(Supplier.name.ilike(like))
        rows = (
            qry.filter(or_(*conds))
            .order_by(SupplierLoanSettlement.id.desc())
            .limit(limit)
            .all()
        )
        results = [{"id": r[0].id, "label": f"Loan Settlement #{r[0].id}", "extra": r[1]} for r in rows]
    else:
        results = []

    return jsonify(results=results)

@payments_bp.route("/", methods=["GET"])
@login_required
@permission_required("manage_payments")
def index():
    if not getattr(current_user, "is_authenticated", False):
        return redirect(url_for("auth.login", next=request.full_path))

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    if per_page > 100:
        per_page = 100

    entity_type = (request.args.get("entity_type") or request.args.get("entity") or "").strip().upper()
    status = (request.args.get("status") or "").strip().upper()
    direction = (request.args.get("direction") or "").strip()
    method = (request.args.get("method") or "").strip()
    start_date = (request.args.get("start_date") or request.args.get("start") or "").strip()
    end_date = (request.args.get("end_date") or request.args.get("end") or "").strip()
    entity_id = request.args.get("entity_id", type=int)
    search_q = (request.args.get("q") or "").strip()
    reference_like = (request.args.get("reference") or "").strip()

    filters = []
    if entity_type:
        filters.append(Payment.entity_type == entity_type)
    if status:
        filters.append(Payment.status == status)
    if direction:
        filters.append(Payment.direction == _dir_to_db(direction))

    if method:
        try:
            m = _coerce_method(method)
            mv = getattr(m, "value", m)
            filters.append(Payment.method == mv)
        except Exception:
            filters.append(Payment.method == method)

    def _parse_ymd(s: str | None):
        if not s:
            return None
        try:
            return datetime.strptime(s.strip(), "%Y-%m-%d").date()
        except Exception:
            return None

    sd = _parse_ymd(start_date)
    ed = _parse_ymd(end_date)
    if sd:
        filters.append(Payment.payment_date >= datetime.combine(sd, time.min))
    if ed:
        filters.append(Payment.payment_date <= datetime.combine(ed, time.max))

    if entity_id and entity_type:
        et = entity_type.lower()
        if et == "customer":
            filters.append(Payment.customer_id == entity_id)
        elif et == "supplier":
            filters.append(Payment.supplier_id == entity_id)
        elif et == "partner":
            filters.append(Payment.partner_id == entity_id)
        elif et == "sale":
            filters.append(Payment.sale_id == entity_id)
        elif et == "invoice":
            filters.append(Payment.invoice_id == entity_id)
        elif et == "preorder":
            filters.append(Payment.preorder_id == entity_id)
        elif et == "service":
            filters.append(Payment.service_id == entity_id)
        elif et == "expense":
            filters.append(Payment.expense_id == entity_id)
        elif et == "loan":
            filters.append(Payment.loan_settlement_id == entity_id)
        elif et == "shipment":
            filters.append(Payment.shipment_id == entity_id)

    if search_q:
        like = f"%{search_q}%"
        filters.append(
            or_(
                Payment.payment_number.ilike(like),
                Payment.reference.ilike(like),
                Payment.notes.ilike(like),
            )
        )
    if reference_like:
        filters.append(Payment.reference.ilike(f"%{reference_like}%"))

    base_q = Payment.query.filter(*filters)
    pagination = base_q.order_by(Payment.payment_date.desc(), Payment.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    totals_row = db.session.query(
        func.coalesce(
            func.sum(
                case(
                    (and_(Payment.direction == PaymentDirection.INCOMING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount),
                    else_=0,
                )
            ),
            0,
        ).label("total_incoming"),
        func.coalesce(
            func.sum(
                case(
                    (and_(Payment.direction == PaymentDirection.OUTGOING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount),
                    else_=0,
                )
            ),
            0,
        ).label("total_outgoing"),
        func.coalesce(func.sum(Payment.total_amount), 0).label("grand_total"),
    ).filter(*filters).one()

    total_incoming_d = q2(D(totals_row.total_incoming or 0))
    total_outgoing_d = q2(D(totals_row.total_outgoing or 0))
    net_total_d      = q2(total_incoming_d - total_outgoing_d)
    grand_total_d    = q2(D(totals_row.grand_total or 0))
    total_incoming = float(total_incoming_d)
    total_outgoing = float(total_outgoing_d)
    net_total = float(net_total_d)
    total_paid = total_incoming
    grand_total = float(grand_total_d)

    if _wants_json():
        return jsonify(
            {
                "payments": [p.to_dict() for p in pagination.items],
                "total_pages": pagination.pages,
                "current_page": pagination.page,
                "total_items": pagination.total,
                "totals": {
                    "total_incoming": total_incoming,
                    "total_outgoing": total_outgoing,
                    "net_total": net_total,
                    "grand_total": grand_total,
                    "total_paid": total_paid,
                },
            }
        )

    return render_template(
        "payments/list.html",
        payments=pagination.items,
        pagination=pagination,
        total_paid=total_paid,
        total_incoming=total_incoming,
        total_outgoing=total_outgoing,
        net_total=net_total,
        grand_total=grand_total,
    )

@payments_bp.route("/create", methods=["GET", "POST"], endpoint="create_payment")
@login_required
@permission_required("manage_payments")
def create_payment():
    form = PaymentForm(meta={"csrf": not current_app.testing})
    entity_info = None

    def _fd(f):
        return getattr(f, "data", None) if f is not None else None

    if hasattr(form, "direction"):
        form.direction.choices = [("IN", "وارد"), ("OUT", "صادر"), ("INCOMING", "وارد"), ("OUTGOING", "صادر")]

    if request.method == "GET":
        form.payment_date.data = datetime.utcnow()
        try:
            tokens = session.get("pmt_tokens") or []
            if len(tokens) > 50:
                tokens = tokens[-30:]
            tok = uuid.uuid4().hex
            tokens.append(tok)
            session["pmt_tokens"] = tokens
            if hasattr(form, "request_token"):
                form.request_token.data = tok
        except Exception:
            if hasattr(form, "request_token"):
                form.request_token.data = None

        raw_et = (request.args.get("entity_type") or "").strip().upper()
        if raw_et == "SHIPMENT_CUSTOMS":
            raw_et = "SHIPMENT"
        et = raw_et if hasattr(form, "_entity_field_map") and raw_et in form._entity_field_map else ""
        eid = request.args.get("entity_id")

        pre_amount = D(request.args.get("amount"))
        if pre_amount == Decimal("0"):
            pre_amount = D(request.args.get("total_amount"))

        preset_direction = _norm_dir(request.args.get("direction"))
        preset_method = request.args.get("method")
        preset_currency = request.args.get("currency")
        preset_ref = (request.args.get("reference") or "").strip() or None
        preset_notes = (request.args.get("notes") or "").strip()

        if et:
            form.entity_type.data = et
            if hasattr(form, "_incoming_entities") and et in form._incoming_entities:
                form.direction.data = "IN"
            elif hasattr(form, "_outgoing_entities") and et in form._outgoing_entities:
                form.direction.data = "OUT"
            field_name = form._entity_field_map[et]
            if eid and str(eid).isdigit() and hasattr(form, field_name):
                getattr(form, field_name).data = int(eid)

            if et == "CUSTOMER" and eid:
                c = db.session.get(Customer, int(eid))
                if c:
                    entity_info = {"type": "customer", "name": c.name, "balance": c.balance, "currency": getattr(c, "currency", "ILS")}
                    form.currency.data = getattr(c, "currency", "ILS")
                    if pre_amount is not None:
                        form.total_amount.data = pre_amount
                        form.reference.data = form.reference.data or f"دفعة من العميل {c.name}"

            elif et == "SUPPLIER" and eid:
                s = db.session.get(Supplier, int(eid))
                if s:
                    nb = D(getattr(s, "net_balance", 0) or 0)
                    entity_info = {"type": "supplier", "name": s.name, "balance": nb, "currency": getattr(s, "currency", "ILS")}
                    form.currency.data = getattr(s, "currency", "ILS")
                    if pre_amount is None:
                        pre_amount = abs(nb)
                        if nb > 0:
                            form.direction.data = "OUT"
                        elif nb < 0:
                            form.direction.data = "IN"
                    if pre_amount is not None:
                        form.total_amount.data = pre_amount
                        form.reference.data = form.reference.data or f"تسوية حساب المورد {s.name}"

            elif et == "PARTNER" and eid:
                p = db.session.get(Partner, int(eid))
                if p:
                    nb = D(getattr(p, "net_balance", 0) or 0)
                    entity_info = {"type": "partner", "name": p.name, "balance": nb, "currency": getattr(p, "currency", "ILS")}
                    form.currency.data = getattr(p, "currency", "ILS")
                    if pre_amount is None:
                        pre_amount = abs(nb)
                        if nb > 0:
                            form.direction.data = "OUT"
                        elif nb < 0:
                            form.direction.data = "IN"
                    if pre_amount is not None:
                        form.total_amount.data = pre_amount
                        form.reference.data = form.reference.data or f"تسوية حساب الشريك {p.name}"

            elif et == "SALE" and eid:
                rec = db.session.get(Sale, int(eid))
                if rec:
                    due = D(getattr(rec, "balance_due", 0) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة لبيع {rec.sale_number or rec.id}"
                    form.currency.data = getattr(rec, "currency", form.currency.data)
                    entity_info = {
                        "type": "sale",
                        "number": rec.sale_number,
                        "date": rec.sale_date.strftime("%Y-%m-%d") if rec.sale_date else "",
                        "balance_due": float(getattr(rec, "balance_due", 0) or 0),
                        "total": float(getattr(rec, "total_amount", getattr(rec, "total", 0)) or 0),
                        "paid": float(getattr(rec, "total_paid", 0) or 0),
                        "currency": getattr(rec, "currency", "ILS"),
                    }

            elif et == "INVOICE" and eid:
                rec = db.session.get(Invoice, int(eid))
                if rec:
                    due = D(getattr(rec, "balance_due", 0) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة للفاتورة {rec.invoice_number or rec.id}"
                    form.currency.data = getattr(rec, "currency", form.currency.data)
                    entity_info = {
                        "type": "invoice",
                        "number": rec.invoice_number,
                        "date": rec.invoice_date.strftime("%Y-%m-%d") if rec.invoice_date else "",
                        "balance_due": float(getattr(rec, "balance_due", 0) or 0),
                        "total": float(getattr(rec, "total_amount", 0) or 0),
                        "paid": float(getattr(rec, "total_paid", 0) or 0),
                        "currency": getattr(rec, "currency", "ILS"),
                    }

            elif et == "SERVICE" and eid:
                svc = db.session.get(ServiceRequest, int(eid))
                if svc:
                    due = D(getattr(svc, "balance_due", getattr(svc, "total_cost", 0)) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة صيانة {svc.service_number or svc.id}"
                    entity_info = {
                        "type": "service",
                        "number": svc.service_number,
                        "date": svc.request_date.strftime("%Y-%m-%d") if getattr(svc, "request_date", None) else "",
                        "balance_due": float(getattr(svc, "balance_due", 0) or 0),
                        "total": float(getattr(svc, "total_cost", 0) or 0),
                        "paid": float(getattr(svc, "total_paid", 0) or 0),
                        "currency": getattr(svc, "currency", "ILS") if hasattr(svc, "currency") else "ILS",
                    }

            elif et == "EXPENSE" and eid:
                exp = db.session.get(Expense, int(eid))
                if exp:
                    bal = D(getattr(exp, "balance", getattr(exp, "amount", 0)) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else bal
                    form.direction.data = "OUT"
                    form.reference.data = f"دفع مصروف #{exp.id}"
                    form.currency.data = getattr(exp, "currency", form.currency.data)
                    entity_info = {
                        "type": "expense",
                        "number": f"EXP-{exp.id}",
                        "date": exp.date.strftime("%Y-%m-%d") if getattr(exp, "date", None) else "",
                        "amount": float(getattr(exp, "amount", 0) or 0),
                        "balance": float(getattr(exp, "balance", 0) or 0),
                        "currency": getattr(exp, "currency", "ILS"),
                    }

            elif et == "SHIPMENT" and eid:
                shp = db.session.get(Shipment, int(eid))
                if shp:
                    form.direction.data = "OUT"
                    if pre_amount is not None:
                        form.total_amount.data = pre_amount
                        form.reference.data = form.reference.data or f"دفع جمارك الشحنة {shp.shipment_number or shp.id}"
                    entity_info = {
                        "type": "shipment",
                        "number": shp.shipment_number,
                        "date": shp.shipment_date.strftime("%Y-%m-%d") if shp.shipment_date else "",
                        "destination": getattr(shp, "destination", ""),
                        "currency": getattr(shp, "currency", "USD"),
                    }

            elif et == "PREORDER" and eid:
                po = db.session.get(PreOrder, int(eid))
                if po:
                    form.total_amount.data = pre_amount if pre_amount is not None else D(getattr(po, "prepaid_amount", 0) or 0)
                    form.reference.data = f"دفعة حجز {po.reference or po.id}"
                    entity_info = {
                        "type": "preorder",
                        "number": po.reference,
                        "date": po.created_at.strftime("%Y-%m-%d") if getattr(po, "created_at", None) else "",
                        "currency": "ILS",
                    }
                    form.direction.data = form.direction.data or "IN"

        if preset_currency:
            form.currency.data = (preset_currency or "").upper()
        if preset_method and hasattr(form, "method"):
            try:
                form.method.data = _coerce_method(preset_method).value
            except Exception:
                form.method.data = (preset_method or "").lower()
        if preset_direction:
            form.direction.data = _norm_dir(preset_direction)
        if preset_ref:
            form.reference.data = preset_ref
        if preset_notes and hasattr(form, "notes"):
            form.notes.data = preset_notes
        if pre_amount is not None and not form.total_amount.data:
            form.total_amount.data = pre_amount

        if not form.status.data:
            form.status.data = PaymentStatus.COMPLETED.value

    if request.method == "POST":
        req_tok = (request.form.get("request_token") or "").strip()
        tokens = session.get("pmt_tokens") or []
        if req_tok and (req_tok in tokens):
            tokens = [t for t in tokens if t != req_tok]
            session["pmt_tokens"] = tokens
        else:
            msg = "تم استلام هذه العملية مسبقًا أو انتهت صلاحية الجلسة."
            if _wants_json():
                return jsonify(status="error", message=msg), 409
            flash(msg, "warning")
            return redirect(url_for("payments.index"))

        raw_dir = request.form.get("direction")
        if raw_dir:
            form.direction.data = _norm_dir(raw_dir)

        if not form.validate():
            current_app.logger.warning(
                "payment.validate_failed",
                extra={"event": "payments.validate_failed", "errors": dict(form.errors or {}), "path": request.path},
            )
            if _wants_json():
                return jsonify(status="error", errors=form.errors), 400
            return render_template("payments/form.html", form=form, entity_info=entity_info)

        try:
            etype = (form.entity_type.data or "").upper()
            field_name = getattr(form, "_entity_field_map", {}).get(etype)
            target_id = getattr(form, field_name).data if field_name and hasattr(form, field_name) else None

            if etype and field_name and not target_id:
                msg = "نوع الجهة محدد بدون رقم مرجع."
                if _wants_json():
                    return jsonify(status="error", message=msg), 400
                flash(msg, "danger")
                return render_template("payments/form.html", form=form, entity_info=entity_info)

            parsed_splits = []
            for entry in getattr(form, "splits", []).entries:
                sm = entry.form
                amt_dec = q2(getattr(sm, "amount").data or 0)
                if amt_dec <= 0:
                    continue
                m_raw = (getattr(sm, "method").data or "")
                m_str = str(m_raw).strip().lower()
                details = {}
                for fld in ("check_number", "check_bank", "check_due_date", "card_number", "card_holder", "card_expiry", "bank_transfer_ref"):
                    if hasattr(sm, fld):
                        val = getattr(sm, fld).data
                        if val in (None, "", []):
                            continue
                        if fld == "check_due_date":
                            if isinstance(val, datetime):
                                val = val.isoformat()
                            else:
                                DateT = type(datetime.utcnow().date())
                                if isinstance(val, DateT):
                                    val = val.isoformat()
                            details[fld] = val
                        elif fld == "card_number":
                            num = "".join(ch for ch in str(val) if ch.isdigit())
                            if num:
                                details["card_last4"] = num[-4:]
                        else:
                            details[fld] = val
                details = _clean_details(details)
                parsed_splits.append(PaymentSplit(method=_coerce_method(m_str), amount=amt_dec, details=details))

            tgt_total_dec = D(request.form.get("total_amount") or form.total_amount.data or 0)
            if parsed_splits:
                sum_splits = _sum_splits_decimal(parsed_splits)
                if sum_splits != tgt_total_dec:
                    msg = f"❌ مجموع الدفعات الجزئية لا يساوي المبلغ الكلي. المجموع={float(sum_splits):.2f} المطلوب={float(q2(tgt_total_dec)):.2f}"
                    if _wants_json():
                        return jsonify(status="error", message=msg), 400
                    flash(msg, "danger")
                    return render_template("payments/form.html", form=form, entity_info=entity_info)

            auto_dir = None
            if hasattr(form, "_incoming_entities") and etype in form._incoming_entities:
                auto_dir = "IN"
            elif hasattr(form, "_outgoing_entities") and etype in form._outgoing_entities:
                auto_dir = "OUT"
            direction_val = _norm_dir(form.direction.data or auto_dir)
            direction_db = _dir_to_db(direction_val)

            method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data or "cash")
            notes_raw = (_fd(getattr(form, "note", None)) or _fd(getattr(form, "notes", None)) or "")

            payment = Payment(
                entity_type=etype,
                customer_id=target_id if etype == "CUSTOMER" else None,
                supplier_id=target_id if etype == "SUPPLIER" else None,
                partner_id=target_id if etype == "PARTNER" else None,
                shipment_id=target_id if etype == "SHIPMENT" else None,
                expense_id=target_id if etype == "EXPENSE" else None,
                loan_settlement_id=target_id if etype == "LOAN" else None,
                sale_id=target_id if etype == "SALE" else None,
                invoice_id=target_id if etype == "INVOICE" else None,
                preorder_id=target_id if etype == "PREORDER" else None,
                service_id=target_id if etype == "SERVICE" else None,
                direction=direction_db,
                status=form.status.data or PaymentStatus.COMPLETED.value,
                payment_date=form.payment_date.data,
                total_amount=q2(tgt_total_dec),
                currency=_norm_currency(form.currency.data),
                method=getattr(method_val, "value", method_val),
                reference=(form.reference.data or "").strip() or None,
                receipt_number=(_fd(getattr(form, "receipt_number", None)) or None),
                notes=notes_raw,
                created_by=current_user.id,
            )

            _ensure_payment_number(payment)
            db.session.add(payment)
            db.session.flush()
            for sp in parsed_splits:
                sp.payment_id = payment.id
                db.session.add(sp)
            _sync_payment_method_with_splits(payment)
            db.session.add(payment)

            try:
                db.session.commit()
            except IntegrityError as ie:
                db.session.rollback()
                msg = str(ie).lower()
                fixed = False
                if "payments.payment_number" in msg or "unique constraint failed: payments.payment_number" in msg:
                    base_dt = payment.payment_date or datetime.utcnow()
                    prefix = base_dt.strftime("PMT%Y%m%d")
                    cnt = db.session.execute(text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"), {"pfx": f"{prefix}-%"}).scalar() or 0
                    payment.payment_number = f"{prefix}-{cnt + 1:04d}"
                    fixed = True
                if "payments.method" in msg or "may not be null" in msg:
                    if parsed_splits:
                        payment.method = getattr(parsed_splits[0].method, "value", parsed_splits[0].method)
                    else:
                        payment.method = PaymentMethod.CASH
                    fixed = True
                if fixed:
                    db.session.add(payment)
                    for sp in parsed_splits:
                        sp.payment_id = payment.id
                        db.session.add(sp)
                    db.session.commit()
                else:
                    raise

            try:
                if payment.sale_id:
                    sale = db.session.get(Sale, payment.sale_id)
                    if sale and hasattr(sale, "update_payment_status"):
                        sale.update_payment_status()
                        db.session.add(sale)
                if payment.invoice_id:
                    inv = db.session.get(Invoice, payment.invoice_id)
                    if inv and hasattr(inv, "update_status"):
                        inv.update_status()
                        db.session.add(inv)
                if payment.status == PaymentStatus.COMPLETED.value:
                    if payment.customer_id:
                        update_entity_balance("customer", payment.customer_id)
                    if payment.supplier_id:
                        update_entity_balance("supplier", payment.supplier_id)
                    if payment.partner_id:
                        update_entity_balance("partner", payment.partner_id)
                    if payment.loan_settlement_id:
                        ls = db.session.get(SupplierLoanSettlement, payment.loan_settlement_id)
                        if ls and ls.supplier_id:
                            update_entity_balance("supplier", ls.supplier_id)
                if payment.preorder_id:
                    po = db.session.get(PreOrder, payment.preorder_id)
                    if po and payment.direction == PaymentDirection.INCOMING.value and payment.status == PaymentStatus.COMPLETED.value:
                        if hasattr(PreOrderStatus, "PAID"):
                            try:
                                po.status = PreOrderStatus.PAID.value if hasattr(PreOrderStatus.PAID, "value") else PreOrderStatus.PAID
                                db.session.add(po)
                            except Exception:
                                pass
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()

            log_audit("Payment", payment.id, "CREATE")

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception(
                "payment.create_failed",
                extra={"event": "payments.create.error", "path": request.path},
            )
            if _wants_json():
                return jsonify(status="error", message=str(e)), 400
            flash(f"❌ خطأ في الحفظ: {e}", "danger")
            return render_template("payments/form.html", form=form, entity_info=entity_info)
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify(status="error", message=str(e)), 400
            flash(f"❌ خطأ في الحفظ: {e}", "danger")
            return render_template("payments/form.html", form=form, entity_info=entity_info)

        if _wants_json():
            return jsonify(status="success", payment=payment.to_dict()), 201
        flash("✅ تم تسجيل الدفعة", "success")
        return redirect(url_for("payments.index"))

    return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/expense/<int:exp_id>/create", methods=["GET", "POST"], endpoint="create_expense_payment")
@login_required
@permission_required("manage_payments")
def create_expense_payment(exp_id):
    exp = _get_or_404(Expense, exp_id)
    form = PaymentForm(meta={"csrf": not current_app.testing})
    if hasattr(form, "direction"):
        form.direction.choices = [("IN", "وارد"), ("OUT", "صادر"), ("INCOMING", "وارد"), ("OUTGOING", "صادر")]
    form.entity_type.data = "EXPENSE"
    if hasattr(form, "_entity_field_map") and "EXPENSE" in form._entity_field_map:
        getattr(form, form._entity_field_map["EXPENSE"]).data = exp.id

    entity_info = {
        "type": "expense",
        "number": f"EXP-{exp.id}",
        "date": exp.date.strftime("%Y-%m-%d") if getattr(exp, "date", None) else "",
        "description": exp.description or "",
        "amount": float(q2(D(getattr(exp, "amount", 0) or 0))),
        "currency": getattr(exp, "currency", "ILS"),
    }

    def _clean_details_local(d):
        if not d:
            return None
        out = {}
        DateT = type(datetime.utcnow().date())
        for k, v in d.items():
            if v in (None, "", []):
                continue
            if isinstance(v, (datetime, DateT)):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out or None

    if request.method == "GET":
        form.payment_date.data = datetime.utcnow()
        form.total_amount.data = D(getattr(exp, "amount", 0) or 0)
        form.reference.data = f"دفع مصروف {exp.description or ''}".strip()
        form.direction.data = "OUT"
        form.currency.data = _norm_currency(getattr(exp, "currency", "ILS"))
        if not form.status.data:
            form.status.data = PaymentStatus.COMPLETED.value
        return render_template("payments/form.html", form=form, entity_info=entity_info)

    raw_dir = request.form.get("direction")
    if raw_dir:
        form.direction.data = _norm_dir(raw_dir)

    if not form.validate_on_submit():
        if _wants_json():
            return jsonify(status="error", errors=form.errors), 400
        return render_template("payments/form.html", form=form, entity_info=entity_info)

    try:
        parsed_splits = []
        for entry in getattr(form, "splits", []).entries:
            sm = entry.form
            amt_dec = q2(getattr(sm, "amount").data or 0)
            if amt_dec <= 0:
                continue
            m_raw = getattr(sm, "method").data or ""
            m_str = str(m_raw).strip().lower()
            details = {}
            for fld in ("check_number", "check_bank", "check_due_date", "card_number", "card_holder", "card_expiry", "bank_transfer_ref"):
                if hasattr(sm, fld):
                    val = getattr(sm, fld).data
                    if val in (None, "", []):
                        continue
                    if fld == "check_due_date":
                        if isinstance(val, datetime):
                            val = val.date().isoformat()
                        else:
                            DateT = type(datetime.utcnow().date())
                            if isinstance(val, DateT):
                                val = val.isoformat()
                        details[fld] = val
                    elif fld == "card_number":
                        num = "".join(ch for ch in str(val) if ch.isdigit())
                        if num:
                            details["card_last4"] = num[-4:]
                    else:
                        details[fld] = val
            details = _clean_details_local(details)
            parsed_splits.append(PaymentSplit(method=_coerce_method(m_str), amount=amt_dec, details=details))

        tgt_total_dec = D(request.form.get("total_amount") or form.total_amount.data or 0)
        sum_splits = _sum_splits_decimal(parsed_splits)
        if sum_splits != tgt_total_dec:
            msg = f"❌ مجموع الدفعات الجزئية لا يساوي المبلغ الكلي. المجموع={float(sum_splits):.2f} المطلوب={float(q2(tgt_total_dec)):.2f}"
            if _wants_json():
                return jsonify(status="error", message=msg), 400
            flash(msg, "danger")
            return render_template("payments/form.html", form=form, entity_info=entity_info)

        method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data or "cash")
        notes_raw = (getattr(form, "note", None).data if hasattr(form, "note") else None) or (getattr(form, "notes", None).data if hasattr(form, "notes") else None) or ""

        payment = Payment(
            entity_type="EXPENSE",
            expense_id=exp.id,
            total_amount=q2(tgt_total_dec),
            currency=_norm_currency(form.currency.data or getattr(exp, "currency", "ILS")),
            method=getattr(method_val, "value", method_val),
            direction=_dir_to_db("OUT"),
            status=form.status.data or PaymentStatus.COMPLETED.value,
            payment_date=form.payment_date.data or datetime.utcnow(),
            reference=(form.reference.data or "").strip() or None,
            notes=(notes_raw or "").strip() or None,
            created_by=current_user.id,
        )

        _ensure_payment_number(payment)
        for sp in parsed_splits:
            payment.splits.append(sp)

        db.session.add(payment)
        db.session.commit()
        log_audit("Payment", payment.id, f"CREATE (expense #{exp.id})")

        if _wants_json():
            return jsonify(status="success", payment=payment.to_dict()), 201

        flash("✅ تم تسجيل دفع المصروف بنجاح", "success")
        return redirect(url_for("payments.view_payment", payment_id=payment.id))
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify(status="error", message=str(e)), 400
        flash(f"❌ خطأ أثناء تسجيل الدفع: {e}", "danger")
        return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/<int:payment_id>", methods=["GET"], endpoint="view_payment")
@login_required
@permission_required("manage_payments")
def view_payment(payment_id):
    payment = _get_or_404(
        Payment,
        payment_id,
        options=(
            joinedload(Payment.customer),
            joinedload(Payment.supplier),
            joinedload(Payment.partner),
            joinedload(Payment.shipment),
            joinedload(Payment.expense),
            joinedload(Payment.loan_settlement),
            joinedload(Payment.sale),
            joinedload(Payment.invoice),
            joinedload(Payment.preorder),
            joinedload(Payment.service),
            joinedload(Payment.splits),
        ),
    )
    if _wants_json():
        return jsonify(payment=payment.to_dict())
    return render_template("payments/view.html", payment=payment)

@payments_bp.route("/split/<int:split_id>/delete", methods=["DELETE"], endpoint="delete_split")
@login_required
@permission_required("manage_payments")
def delete_split(split_id):
    split = _get_or_404(PaymentSplit, split_id)
    try:
        payment_id = split.payment_id
        pmt = db.session.get(Payment, payment_id)
        if pmt and pmt.status == PaymentStatus.COMPLETED.value:
            return jsonify(status="error", message="لا يمكن تعديل دفعات سند مكتمل."), 409
        db.session.delete(split)
        db.session.flush()
        if payment_id:
            if pmt is None:
                pmt = db.session.get(Payment, payment_id)
            if pmt is not None:
                _sync_payment_method_with_splits(pmt)
                rem = list(pmt.splits or [])
                if rem:
                    new_total = _sum_splits_decimal(rem)
                    pmt.total_amount = new_total
                db.session.add(pmt)
        db.session.commit()
        current_app.logger.info(
            "payment.split_deleted",
            extra={
                "event": "payments.split.delete",
                "payment_id": payment_id,
                "split_id": split_id,
            },
        )
        return jsonify(status="success")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception(
            "payment.split_delete_failed",
            extra={"event": "payments.split.error", "split_id": split_id},
        )
        return jsonify(status="error", message=str(e)), 400

@payments_bp.route("/<int:payment_id>/receipt", methods=["GET"], endpoint="view_receipt")
@login_required
@permission_required("manage_payments")
def view_receipt(payment_id: int):
    payment = _get_or_404(
        Payment,
        payment_id,
        options=(
            joinedload(Payment.customer),
            joinedload(Payment.supplier),
            joinedload(Payment.partner),
            joinedload(Payment.sale),
            joinedload(Payment.splits),
        ),
    )

    sale_info = None
    if payment.sale_id and payment.sale:
        s = payment.sale
        sale_info = {
            "number": s.sale_number,
            "date": s.sale_date.strftime("%Y-%m-%d") if s.sale_date else "-",
            "total": s.total_amount,
            "paid": s.total_paid,
            "balance": s.balance_due,
            "currency": s.currency,
        }

    if _wants_json():
        payload = payment.to_dict()
        payload["sale_info"] = sale_info
        return jsonify(payment=payload)

    return render_template(
        "payments/receipt.html",
        payment=payment,
        now=datetime.utcnow(),
        sale_info=sale_info,
    )

@payments_bp.route("/<int:payment_id>/receipt/download", methods=["GET"], endpoint="download_receipt")
@login_required
@permission_required("manage_payments")
def download_receipt(payment_id: int):
    payment = _get_or_404(Payment, payment_id)
    pdf_bytes = _render_payment_receipt_pdf(payment)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=payment_receipt_{payment_id}.pdf"},
    )

@payments_bp.route("/entity-fields", methods=["GET"], endpoint="entity_fields")
@login_required
@permission_required("manage_payments")
def entity_fields():
    entity_type = (request.args.get("type") or "customer").strip().lower()
    entity_id = request.args.get("entity_id")

    form = PaymentForm()
    form.entity_type.data = entity_type.upper()

    model_map = {
        "customer": (Customer, "customer_id"),
        "supplier": (Supplier, "supplier_id"),
        "partner": (Partner, "partner_id"),
        "sale": (Sale, "sale_id"),
        "invoice": (Invoice, "invoice_id"),
        "service": (ServiceRequest, "service_id"),
        "shipment": (Shipment, "shipment_id"),
        "expense": (Expense, "expense_id"),
        "preorder": (PreOrder, "preorder_id"),
        "loan": (SupplierLoanSettlement, "loan_settlement_id"),
    }

    if entity_id:
        try:
            eid = int(entity_id)
            model, field_name = model_map.get(entity_type, (None, None))
            if model is not None and db.session.get(model, eid):
                getattr(form, field_name).data = eid
        except (ValueError, TypeError):
            if _wants_json():
                return jsonify(status="error", message="entity_id غير صالح"), 400

    if hasattr(form, "_sync_entity_id_for_render"):
        form._sync_entity_id_for_render()

    return render_template("payments/_entity_fields.html", form=form)

@payments_bp.route("/<int:payment_id>/delete", methods=["POST"], endpoint="delete_payment")
@login_required
@permission_required("manage_payments")
def delete_payment(payment_id):
    payment = db.session.get(Payment, payment_id) or abort(404)
    try:
        if payment.status == PaymentStatus.COMPLETED.value:
            flash("لا يمكن حذف سند مكتمل.", "danger")
            return redirect(url_for("payments.index"))
        db.session.delete(payment)
        db.session.commit()
        log_audit("Payment", payment.id, "DELETE")
        flash("✅ تم حذف السند بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("payments.index"))
