from sqlalchemy import text as sa_text
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import uuid
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for, session
from flask_login import current_user, login_required
from sqlalchemy import func, text, and_, case, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import PaymentForm
from models import Customer, Expense, Invoice, Partner, Payment, PaymentDirection, PaymentMethod, PaymentSplit, PaymentStatus, PreOrder, PreOrderStatus, Sale, ServiceRequest, Shipment, Supplier, SupplierLoanSettlement
from utils import log_audit, permission_required, update_entity_balance
from weasyprint import HTML, CSS

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

TWOPLACES = Decimal("0.01")
ZERO_PLACES = Decimal("1")

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

def q0(x) -> Decimal:
    return D(x).quantize(ZERO_PLACES, rounding=ROUND_HALF_UP)

def _f2(v):
    try:
        return float(v or 0)
    except:
        return 0.0

def _line_total(qty, unit_price, disc_pct, tax_pct):
    q = int(qty or 0)
    u = _f2(unit_price)
    d = _f2(disc_pct)
    t = _f2(tax_pct)
    gross = q * u
    disc = gross * (d / 100.0)
    taxable = gross - disc
    tax = taxable * (t / 100.0)
    taxable_d = q0(taxable)
    tax_d = q0(tax)
    total_d = q0(taxable_d + tax_d)
    return taxable_d, tax_d, total_d

def _service_totals(svc: ServiceRequest):
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    grand = Decimal("0")
    for p in (getattr(svc, "parts", None) or []):
        s, t, g = _line_total(p.quantity, p.unit_price, p.discount, p.tax_rate)
        subtotal += s
        tax_total += t
        grand += g
    for tsk in (getattr(svc, "tasks", None) or []):
        s, t, g = _line_total(tsk.quantity or 1, tsk.unit_price, tsk.discount, tsk.tax_rate)
        subtotal += s
        tax_total += t
        grand += g
    return int(q0(subtotal)), int(q0(tax_total)), int(q0(grand))

def _ensure_payment_number(pmt: Payment) -> None:
    if getattr(pmt, "payment_number", None):
        return
    base_dt = getattr(pmt, "payment_date", None) or datetime.utcnow()
    prefix = base_dt.strftime("PMT%Y%m%d")
    cnt = db.session.execute(sa_text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"), {"pfx": f"{prefix}-%"}).scalar() or 0
    pmt.payment_number = f"{prefix}-{cnt+1:04d}"

def _sum_splits_decimal(splits) -> Decimal:
    total = Decimal("0")
    for s in splits or []:
        total += q0(getattr(s, "amount", 0))
    return q0(total)

def _norm_currency(v):
    return (v or "ILS").strip().upper()

try:
    from models import ensure_currency as _ensure_ccy
except Exception:
    _ensure_ccy = None

def ensure_currency(cur):
    if _ensure_ccy:
        return _ensure_ccy(cur)
    return (cur or "ILS").strip().upper()

def _get_or_404(model, ident, options=None):
    if options:
        obj = db.session.query(model).options(*options).filter_by(id=ident).first()
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
    s = str(_val(v) or "").strip()
    if not s:
        return PaymentMethod.CASH
    name_up = s.replace("-", "_").upper()
    for m in PaymentMethod:
        if m.name == name_up:
            return m
    for m in PaymentMethod:
        val = str(m.value).strip()
        if val.upper() == name_up or val.lower() == s.lower():
            return m
    return PaymentMethod.CASH

def _sync_payment_method_with_splits(pmt: Payment):
    try:
        splits = list(pmt.splits or [])
    except Exception:
        splits = []
    if not splits:
        if not getattr(pmt, "method", None):
            pmt.method = PaymentMethod.CASH.value
        return
    first = splits[0]
    new_m = getattr(first, "method", None)
    new_m_val = getattr(new_m, "value", new_m)
    if new_m_val and new_m_val != getattr(pmt, "method", None):
        pmt.method = new_m_val

def _wants_json():
    accept = request.headers.get("Accept", "") or ""
    return (request.args.get("format") == "json" or ("application/json" in accept and "text/html" not in accept) or request.headers.get("X-Requested-With") == "XMLHttpRequest")

def _serialize_split(s):
    return {
        "id": s.id,
        "amount": int(q0(getattr(s, "amount", 0) or 0)),
        "method": (getattr(getattr(s, "method", None), "value", getattr(s, "method", "")) or ""),
        "details": (getattr(s, "details", None) or None),
    }

def _serialize_payment(p, *, full=False):
    d = {
        "id": p.id,
        "payment_date": (p.payment_date.isoformat() if getattr(p, "payment_date", None) else None),
        "total_amount": int(q0(getattr(p, "total_amount", 0) or 0)),
        "currency": getattr(p, "currency", "ILS") or "ILS",
        "method": (getattr(getattr(p, "method", None), "value", getattr(p, "method", "")) or ""),
        "direction": (getattr(getattr(p, "direction", None), "value", getattr(p, "direction", "")) or ""),
        "status": (getattr(getattr(p, "status", None), "value", getattr(p, "status", "")) or ""),
        "entity_type": getattr(p, "entity_type", "") or "",
        "entity_display": p.entity_label() if hasattr(p, "entity_label") else (getattr(p, "entity_type", "") or ""),
        "splits": [_serialize_split(s) for s in (list(getattr(p, "splits", []) or []))],
    }
    if full:
        d.update({
            "payment_number": getattr(p, "payment_number", None),
            "receipt_number": getattr(p, "receipt_number", None),
            "reference": getattr(p, "reference", None),
            "notes": getattr(p, "notes", None),
            "customer_id": getattr(p, "customer_id", None),
            "supplier_id": getattr(p, "supplier_id", None),
            "partner_id": getattr(p, "partner_id", None),
            "sale_id": getattr(p, "sale_id", None),
            "invoice_id": getattr(p, "invoice_id", None),
            "service_id": getattr(p, "service_id", None),
            "expense_id": getattr(p, "expense_id", None),
            "preorder_id": getattr(p, "preorder_id", None),
            "shipment_id": getattr(p, "shipment_id", None),
            "loan_settlement_id": getattr(p, "loan_settlement_id", None),
        })
    return d

def _render_payment_receipt_pdf(payment: Payment) -> bytes:
    html = render_template("payments/receipt.html", payment=payment, now=datetime.utcnow())
    css_inline = "@page { size: A4; margin: 14mm; } html, body { direction: rtl; font-family: 'Cairo','Noto Naskh Arabic',Arial,sans-serif; font-size: 12px; } h1,h2,h3 { margin: 0 0 8px 0; } table { width: 100%; border-collapse: collapse; } th, td { padding: 6px 8px; border-bottom: 1px solid #ddd; } .muted { color: #666; }"
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
        return db.session.query(model).filter(or_(*conds)).order_by(getattr(model, "name").asc()).limit(limit).all()
    results = []
    if t == "CUSTOMER":
        rows = rows_for(Customer); results = [{"id": r.id, "label": r.name, "extra": (getattr(r, "phone", "") or getattr(r, "mobile", "") or "")} for r in rows]
    elif t == "SUPPLIER":
        rows = rows_for(Supplier); results = [{"id": r.id, "label": r.name, "extra": (getattr(r, "phone", "") or getattr(r, "mobile", "") or "")} for r in rows]
    elif t == "PARTNER":
        rows = rows_for(Partner); results = [{"id": r.id, "label": r.name, "extra": ""} for r in rows]
    elif t == "LOAN":
        qdigits = "".join(ch for ch in q if ch.isdigit())
        qry = db.session.query(SupplierLoanSettlement, Supplier.name.label("supplier_name")).join(Supplier, Supplier.id == SupplierLoanSettlement.supplier_id)
        conds = []
        if qdigits:
            try:
                conds.append(SupplierLoanSettlement.id == int(qdigits))
            except Exception:
                pass
        conds.append(Supplier.name.ilike(like))
        rows = qry.filter(or_(*conds)).order_by(SupplierLoanSettlement.id.desc()).limit(limit).all()
        results = [{"id": r[0].id, "label": f"Loan Settlement #{r[0].id}", "extra": r[1]} for r in rows]
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
    status = (request.args.get("status") or "").strip()
    direction = (request.args.get("direction") or "").strip()
    method = (request.args.get("method") or "").strip()
    start_date = (request.args.get("start_date") or request.args.get("start") or "").strip()
    end_date = (request.args.get("end_date") or request.args.get("end") or "").strip()
    currency_param = (request.args.get("currency") or "").strip().upper()
    entity_id = request.args.get("entity_id", type=int)
    search_q = (request.args.get("q") or "").strip()
    reference_like = (request.args.get("reference") or "").strip()
    filters = []
    if entity_type:
        filters.append(Payment.entity_type == entity_type)
    if status:
        st_val = status.strip().upper(); mapped = None
        try:
            for s in PaymentStatus:
                if s.name == st_val or str(s.value).strip().upper() == st_val:
                    mapped = s.value
                    break
        except Exception:
            mapped = None
        filters.append(Payment.status == (mapped or st_val))
    if direction:
        filters.append(Payment.direction == _dir_to_db(direction))
    if method:
        try:
            m = _coerce_method(method); mv = getattr(m, "value", m); filters.append(Payment.method == mv)
        except Exception:
            filters.append(Payment.method == method)
    if currency_param:
        filters.append(Payment.currency == ensure_currency(currency_param))
    def _parse_ymd(s: str | None):
        if not s:
            return None
        try:
            return datetime.strptime(s.strip(), "%Y-%m-%d").date()
        except Exception:
            return None
    sd = _parse_ymd(start_date); ed = _parse_ymd(end_date)
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
        filters.append(or_(Payment.payment_number.ilike(like), Payment.reference.ilike(like), Payment.notes.ilike(like)))
    if reference_like:
        filters.append(Payment.reference.ilike(f"%{reference_like}%"))
    base_q = Payment.query.filter(*filters)
    pagination = base_q.order_by(Payment.payment_date.desc(), Payment.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    if currency_param:
        totals_row = db.session.query(
            func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.INCOMING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_incoming"),
            func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.OUTGOING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_outgoing"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("grand_total")
        ).filter(*filters).one()
        total_incoming_d = q0(D(totals_row.total_incoming or 0))
        total_outgoing_d = q0(D(totals_row.total_outgoing or 0))
        net_total_d = q0(total_incoming_d - total_outgoing_d)
        grand_total_d = q0(D(totals_row.grand_total or 0))
        totals_by_currency = {
            ensure_currency(currency_param): {
                "total_incoming": int(total_incoming_d),
                "total_outgoing": int(total_outgoing_d),
                "net_total": int(net_total_d),
                "grand_total": int(grand_total_d),
                "total_paid": int(total_incoming_d),
            }
        }
        if _wants_json():
            return jsonify({
                "payments": [_serialize_payment(p, full=False) for p in pagination.items],
                "total_pages": pagination.pages,
                "current_page": pagination.page,
                "total_items": pagination.total,
                "currency": ensure_currency(currency_param),
                "totals_by_currency": totals_by_currency,
                "totals": totals_by_currency[ensure_currency(currency_param)]
            })
        return render_template(
            "payments/list.html",
            payments=pagination.items,
            pagination=pagination,
            total_paid=int(total_incoming_d),
            total_incoming=int(total_incoming_d),
            total_outgoing=int(total_outgoing_d),
            net_total=int(net_total_d),
            grand_total=int(grand_total_d),
            totals_by_currency=totals_by_currency
        )
    rows = db.session.query(
        Payment.currency.label("ccy"),
        func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.INCOMING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_incoming"),
        func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.OUTGOING.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_outgoing"),
        func.coalesce(func.sum(Payment.total_amount), 0).label("grand_total")
    ).filter(*filters).group_by(Payment.currency).all()
    totals_by_currency = {}
    for r in rows:
        ti = q0(D(r.total_incoming or 0))
        to = q0(D(r.total_outgoing or 0))
        gt = q0(D(r.grand_total or 0))
        totals_by_currency[r.ccy] = {
            "total_incoming": int(ti),
            "total_outgoing": int(to),
            "net_total": int(q0(ti - to)),
            "grand_total": int(gt),
            "total_paid": int(ti)
        }
    if _wants_json():
        return jsonify({
            "payments": [_serialize_payment(p, full=False) for p in pagination.items],
            "total_pages": pagination.pages,
            "current_page": pagination.page,
            "total_items": pagination.total,
            "currency": None,
            "totals_by_currency": totals_by_currency
        })
    return render_template(
        "payments/list.html",
        payments=pagination.items,
        pagination=pagination,
        total_paid=0,
        total_incoming=0,
        total_outgoing=0,
        net_total=0,
        grand_total=0,
        totals_by_currency=totals_by_currency
    )

@payments_bp.route("/create", methods=["GET", "POST"], endpoint="create_payment")
@login_required
@permission_required("manage_payments")
def create_payment():
    form = PaymentForm(meta={"csrf": not current_app.testing})
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}
    entity_info = None
    def _fd(f):
        return getattr(f, "data", None) if f is not None else None
    if request.method == "GET":
        form.payment_date.data = datetime.utcnow()
        try:
            tokens = list(session.get("pmt_tokens") or [])
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
        if pre_amount <= 0:
            pre_amount = D(request.args.get("total_amount"))
        if pre_amount <= 0:
            pre_amount = None
        preset_direction = _norm_dir(request.args.get("direction"))
        preset_method = request.args.get("method")
        preset_currency = request.args.get("currency")
        preset_ref = (request.args.get("reference") or "").strip() or None
        preset_notes = (request.args.get("notes") or "").strip()
        if et:
            form.entity_type.data = et
            field_name = form._entity_field_map[et]
            if eid and str(eid).isdigit() and hasattr(form, field_name):
                getattr(form, field_name).data = int(eid)
            if et == "CUSTOMER" and eid:
                c = db.session.get(Customer, int(eid))
                if c:
                    entity_info = {"type": "customer", "name": c.name, "balance": int(q0(getattr(c, "balance", 0) or 0)), "currency": getattr(c, "currency", "ILS")}
                    if not preset_currency:
                        form.currency.data = getattr(c, "currency", "ILS")
            elif et == "SUPPLIER" and eid:
                s = db.session.get(Supplier, int(eid))
                if s and not preset_currency:
                    form.currency.data = getattr(s, "currency", "ILS")
            elif et == "PARTNER" and eid:
                p = db.session.get(Partner, int(eid))
                if p and not preset_currency:
                    form.currency.data = getattr(p, "currency", "ILS")
            elif et == "SALE" and eid:
                rec = db.session.get(Sale, int(eid))
                if rec:
                    total_i = int(q0(getattr(rec, "total_amount", getattr(rec, "total", 0)) or 0))
                    paid_i = int(q0(getattr(rec, "total_paid", 0) or 0))
                    due_i = int(q0(D(total_i) - D(paid_i)))
                    if pre_amount is None:
                        pre_amount = due_i
                    if not preset_currency:
                        form.currency.data = getattr(rec, "currency", form.currency.data)
                    person = None
                    if getattr(rec, "customer_id", None):
                        cust = db.session.get(Customer, rec.customer_id)
                        if cust:
                            person = {"type": "customer", "id": cust.id, "name": cust.name}
                    entity_info = {"type": "sale","number": rec.sale_number,"date": rec.sale_date.strftime("%Y-%m-%d") if rec.sale_date else "","total": total_i,"paid": paid_i,"balance": due_i,"currency": getattr(rec, "currency", "ILS"),"person": person}
            elif et == "INVOICE" and eid:
                rec = db.session.get(Invoice, int(eid))
                if rec:
                    total_i = int(q0(getattr(rec, "total_amount", 0) or 0))
                    paid_i = int(q0(getattr(rec, "total_paid", 0) or 0))
                    due_i = int(q0(D(total_i) - D(paid_i)))
                    if pre_amount is None:
                        pre_amount = due_i
                    if not preset_currency:
                        form.currency.data = getattr(rec, "currency", form.currency.data)
                    person = None
                    if getattr(rec, "customer_id", None):
                        cust = db.session.get(Customer, rec.customer_id)
                        if cust:
                            person = {"type": "customer", "id": cust.id, "name": cust.name}
                    entity_info = {"type": "invoice","number": rec.invoice_number,"date": rec.invoice_date.strftime("%Y-%m-%d") if rec.invoice_date else "","total": total_i,"paid": paid_i,"balance": due_i,"currency": getattr(rec, "currency", "ILS"),"person": person}
            elif et == "SERVICE" and eid:
                svc = db.session.get(ServiceRequest, int(eid))
                if svc:
                    try:
                        subtotal_i, tax_i, grand_i = _service_totals(svc)
                    except Exception:
                        subtotal_i = int(q0(getattr(svc, "total_cost", 0) or 0))
                        tax_i = 0
                        grand_i = subtotal_i
                    total_paid_i = int(q0(getattr(svc, "total_paid", 0) or 0))
                    due_i = int(q0(D(grand_i) - D(total_paid_i)))
                    if pre_amount is None:
                        pre_amount = due_i
                    person = None
                    if getattr(svc, "customer_id", None):
                        cust = db.session.get(Customer, svc.customer_id)
                        if cust:
                            person = {"type": "customer", "id": cust.id, "name": cust.name}
                    entity_info = {"type": "service","number": svc.service_number,"date": svc.request_date.strftime("%Y-%m-%d") if getattr(svc, "request_date", None) else "","total": int(q0(grand_i)),"paid": total_paid_i,"balance": due_i,"currency": getattr(svc, "currency", "ILS") if hasattr(svc, "currency") else "ILS","person": person}
            elif et == "EXPENSE" and eid:
                exp = db.session.get(Expense, int(eid))
                if exp:
                    bal = D(getattr(exp, "balance", getattr(exp, "amount", 0)) or 0)
                    if pre_amount is None:
                        pre_amount = bal
                    if not preset_currency:
                        form.currency.data = getattr(exp, "currency", form.currency.data)
                    person = None
                    if getattr(exp, "employee", None) and getattr(exp.employee, "name", None):
                        person = {"type": "employee", "id": getattr(exp.employee, "id", None), "name": exp.employee.name}
                    elif getattr(exp, "shipment", None):
                        person = {"type": "shipment", "id": getattr(exp.shipment, "id", None), "name": getattr(exp.shipment, "number", f"شحنة رقم {exp.shipment_id or ''}")}
                    elif getattr(exp, "utility_account", None):
                        ua = exp.utility_account
                        ua_name = ua.alias or ua.provider or f"Utility #{getattr(ua, 'id', '')}"
                        person = {"type": "utility", "id": getattr(ua, "id", None), "name": ua_name}
                    elif getattr(exp, "stock_adjustment", None):
                        sa = exp.stock_adjustment
                        person = {"type": "stock_adjustment", "id": getattr(sa, "id", None), "name": f"Stock Adj #{getattr(sa, 'id', '')}"}
                    else:
                        payee_name = getattr(exp, "payee_name", None) or getattr(exp, "paid_to", None) or ""
                        if payee_name:
                            person = {"type": "payee", "id": None, "name": payee_name}
                    ref_txt = (person and person.get("name")) or getattr(exp, "payee_name", None) or getattr(exp, "paid_to", None) or getattr(exp, "description", None) or f"مصروف #{exp.id}"
                    if not form.reference.data:
                        form.reference.data = f"دفع مصروف {ref_txt}"
                    entity_info = {"type": "expense","number": f"EXP-{exp.id}","date": exp.date.strftime("%Y-%m-%d") if getattr(exp, "date", None) else "","description": exp.description or "","amount": int(q0(getattr(exp, "amount", 0) or 0)),"balance": int(q0(getattr(exp, "balance", 0) or 0)),"currency": getattr(exp, "currency", "ILS"),"type_name": getattr(getattr(exp, "type", None), "name", None),"employee_name": getattr(getattr(exp, "employee", None), "name", None),"person": person}
            elif et == "SHIPMENT" and eid:
                shp = db.session.get(Shipment, int(eid))
                if shp:
                    if hasattr(shp, "currency") and shp.currency and not preset_currency:
                        form.currency.data = shp.currency
                    if pre_amount is None:
                        amt = D(getattr(shp, "customs_due", None) or 0) or D(getattr(shp, "total_due", None) or 0) or D(getattr(shp, "balance", None) or 0) or D(getattr(shp, "total_cost", None) or 0)
                        if amt > 0:
                            pre_amount = amt
                    if not form.reference.data:
                        ref_no = getattr(shp, "shipment_number", None) or shp.id
                        form.reference.data = f"دفع شحنة {ref_no}"
                    person = None
                    supplier_id = getattr(shp, "supplier_id", None)
                    if supplier_id:
                        sup = db.session.get(Supplier, supplier_id)
                        if sup:
                            person = {"type": "supplier", "id": sup.id, "name": sup.name}
                    entity_info = {"type": "shipment","number": getattr(shp, "shipment_number", None),"date": shp.shipment_date.strftime("%Y-%m-%d") if getattr(shp, "shipment_date", None) else "","destination": getattr(shp, "destination", "") or "","currency": getattr(shp, "currency", "USD"),"person": person}
            elif et == "PREORDER" and eid:
                po = db.session.get(PreOrder, int(eid))
                if po:
                    if not preset_currency:
                        form.currency.data = getattr(po, "currency", "ILS")
                    if pre_amount is None:
                        amt = D(getattr(po, "balance_due", None) or 0) or D(getattr(po, "prepaid_amount", None) or 0) or D(getattr(po, "deposit_amount", None) or 0)
                        if amt > 0:
                            pre_amount = amt
                    if not form.reference.data:
                        ref_no = getattr(po, "reference", None) or po.id
                        form.reference.data = f"دفعة حجز {ref_no}"
                    person = None
                    if getattr(po, "customer_id", None):
                        cust = db.session.get(Customer, po.customer_id)
                        if cust:
                            person = {"type": "customer", "id": cust.id, "name": cust.name}
                    entity_info = {"type": "preorder","number": getattr(po, "reference", None),"date": po.created_at.strftime("%Y-%m-%d") if getattr(po, "created_at", None) else "","currency": getattr(po, "currency", "ILS"),"person": person}
        if preset_currency:
            form.currency.data = ensure_currency((preset_currency or "").upper())
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
            form.total_amount.data = int(q0(pre_amount))
        if not form.status.data:
            form.status.data = PaymentStatus.COMPLETED.value
    if request.method == "POST":
        req_tok = (request.form.get("request_token") or "").strip()
        tokens = set(session.get("pmt_tokens") or [])
        if req_tok and (req_tok in tokens):
            tokens.remove(req_tok)
            session["pmt_tokens"] = list(tokens)
        else:
            msg = "تم استلام هذه العملية مسبقًا أو انتهت صلاحية الجلسة."
            if _wants_json():
                return jsonify(status="error", message=msg), 409
            flash(msg, "warning")
            return redirect(url_for("payments.index"))
        raw_dir = request.form.get("direction")
        if raw_dir:
            form.direction.data = _norm_dir(raw_dir)
        etype = (request.form.get("entity_type") or form.entity_type.data or "").upper()
        if etype == "EXPENSE":
            form.direction.data = "OUT"
        form._incoming_entities = set()
        form._outgoing_entities = {"EXPENSE"}
        if not form.validate():
            if _wants_json():
                return jsonify(status="error", errors=form.errors), 400
            return render_template("payments/form.html", form=form, entity_info=None)
        try:
            etype = (form.entity_type.data or "").upper()
            field_name = getattr(form, "_entity_field_map", {}).get(etype)
            target_id = getattr(form, field_name).data if field_name and hasattr(form, field_name) else None
            if etype and field_name and not target_id:
                msg = "نوع الجهة محدد بدون رقم مرجع."
                if _wants_json():
                    return jsonify(status="error", message=msg), 400
                flash(msg, "danger")
                return render_template("payments/form.html", form=form, entity_info=None)
            parsed_splits = []
            for entry in getattr(form, "splits", []).entries:
                sm = entry.form
                amt_dec = q0(getattr(sm, "amount").data or 0)
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
                            if isinstance(val, (datetime, date)):
                                val = val.isoformat()
                            details[fld] = val
                        elif fld == "card_number":
                            num = "".join(ch for ch in str(val) if ch.isdigit())
                            if num:
                                details["card_last4"] = num[-4:]
                        else:
                            details[fld] = val
                details = _clean_details(details)
                parsed_splits.append(PaymentSplit(method=_coerce_method(m_str).value, amount=q0(amt_dec), details=details))
            tgt_total_dec = q0(D(request.form.get("total_amount") or form.total_amount.data or 0))
            if tgt_total_dec <= 0:
                msg = "❌ المبلغ الكلي يجب أن يكون أكبر من صفر."
                if _wants_json():
                    return jsonify(status="error", message=msg), 400
                flash(msg, "danger")
                return render_template("payments/form.html", form=form, entity_info=None)
            if parsed_splits:
                sum_splits = _sum_splits_decimal(parsed_splits)
                if sum_splits != tgt_total_dec:
                    msg = f"❌ مجموع الدفعات الجزئية لا يساوي المبلغ الكلي. المجموع={int(sum_splits)} المطلوب={int(tgt_total_dec)}"
                    if _wants_json():
                        return jsonify(status="error", message=msg), 400
                    flash(msg, "danger")
                    return render_template("payments/form.html", form=form, entity_info=None)
            direction_val = _norm_dir(form.direction.data or request.form.get("direction"))
            if etype == "EXPENSE":
                direction_val = "OUT"
            direction_db = _dir_to_db(direction_val)
            method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data or "cash").value
            notes_raw = (_fd(getattr(form, "note", None)) or _fd(getattr(form, "notes", None)) or "")
            related_customer_id = None
            related_supplier_id = None
            person_name = None
            if etype == "CUSTOMER":
                related_customer_id = target_id
                c = db.session.get(Customer, target_id) if target_id else None
                person_name = getattr(c, "name", None)
            elif etype == "SALE":
                s = db.session.get(Sale, target_id)
                related_customer_id = getattr(s, "customer_id", None) if s else None
                if related_customer_id:
                    c = db.session.get(Customer, related_customer_id)
                    person_name = getattr(c, "name", None)
            elif etype == "INVOICE":
                inv = db.session.get(Invoice, target_id)
                related_customer_id = getattr(inv, "customer_id", None) if inv else None
                if related_customer_id:
                    c = db.session.get(Customer, related_customer_id)
                    person_name = getattr(c, "name", None)
            elif etype == "SERVICE":
                svc = db.session.get(ServiceRequest, target_id)
                related_customer_id = getattr(svc, "customer_id", None) if svc else None
                if related_customer_id:
                    c = db.session.get(Customer, related_customer_id)
                    person_name = getattr(c, "name", None)
            elif etype == "PREORDER":
                po = db.session.get(PreOrder, target_id)
                related_customer_id = getattr(po, "customer_id", None) if po else None
                if related_customer_id:
                    c = db.session.get(Customer, related_customer_id)
                    person_name = getattr(c, "name", None)
            elif etype == "SUPPLIER":
                related_supplier_id = target_id
                s = db.session.get(Supplier, target_id) if target_id else None
                person_name = getattr(s, "name", None)
            elif etype == "SHIPMENT":
                shp = db.session.get(Shipment, target_id)
                related_supplier_id = getattr(shp, "supplier_id", None) if shp else None
                if related_supplier_id:
                    s = db.session.get(Supplier, related_supplier_id)
                    person_name = getattr(s, "name", None)
            ref_text = (form.reference.data or "").strip()
            if not ref_text and person_name:
                if direction_val == "IN":
                    ref_text = f"دفعة واردة من {person_name}"
                else:
                    ref_text = f"دفعة صادرة إلى {person_name}"
            payment = Payment(
                entity_type=etype,
                customer_id=(target_id if etype == "CUSTOMER" else None),
                supplier_id=(target_id if etype == "SUPPLIER" else None),
                partner_id=(target_id if etype == "PARTNER" else None),
                shipment_id=(target_id if etype == "SHIPMENT" else None),
                expense_id=(target_id if etype == "EXPENSE" else None),
                loan_settlement_id=(target_id if etype == "LOAN" else None),
                sale_id=(target_id if etype == "SALE" else None),
                invoice_id=(target_id if etype == "INVOICE" else None),
                preorder_id=(target_id if etype == "PREORDER" else None),
                service_id=(target_id if etype == "SERVICE" else None),
                direction=direction_db,
                status=form.status.data or PaymentStatus.COMPLETED.value,
                payment_date=form.payment_date.data,
                total_amount=q0(tgt_total_dec),
                currency=ensure_currency(form.currency.data),
                method=getattr(method_val, "value", method_val),
                reference=ref_text or None,
                receipt_number=(_fd(getattr(form, "receipt_number", None)) or None),
                notes=notes_raw,
                created_by=getattr(current_user, "id", None),
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
                    cnt = db.session.execute(sa_text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"), {"pfx": f"{prefix}-%"}).scalar() or 0
                    payment.payment_number = f"{prefix}-{cnt+1:04d}"
                    fixed = True
                if "payments.method" in msg or "may not be null" in msg:
                    if parsed_splits:
                        payment.method = getattr(parsed_splits[0].method, "value", str(parsed_splits[0].method))
                    else:
                        payment.method = PaymentMethod.CASH.value
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
                    if related_customer_id:
                        update_entity_balance("customer", related_customer_id)
                    if related_supplier_id:
                        update_entity_balance("supplier", related_supplier_id)
                    if payment.partner_id:
                        update_entity_balance("partner", payment.partner_id)
                    if payment.loan_settlement_id:
                        ls = db.session.get(SupplierLoanSettlement, payment.loan_settlement_id)
                        if ls and ls.supplier_id:
                            update_entity_balance("supplier", ls.supplier_id)
                if payment.preorder_id:
                    po = db.session.get(PreOrder, payment.preorder_id)
                    if po and payment.direction == PaymentDirection.INCOMING.value and payment.status == PaymentStatus.COMPLETED.value:
                        try:
                            if hasattr(PreOrderStatus, "PAID"):
                                po.status = getattr(PreOrderStatus.PAID, "value", PreOrderStatus.PAID)
                            else:
                                po.status = getattr(PreOrderStatus.FULFILLED, "value", PreOrderStatus.FULFILLED)
                            db.session.add(po)
                        except Exception:
                            pass
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
            log_audit("Payment", payment.id, "CREATE")
        except SQLAlchemyError as e:
            db.session.rollback()
            if _wants_json():
                return jsonify(status="error", message=str(e)), 400
            flash(f"❌ خطأ في الحفظ: {e}", "danger")
            return render_template("payments/form.html", form=form, entity_info=None)
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify(status="error", message=str(e)), 400
            flash(f"❌ خطأ في الحفظ: {e}", "danger")
            return render_template("payments/form.html", form=form, entity_info=None)
        if _wants_json():
            return jsonify(status="success", payment=_serialize_payment(payment, full=True)), 201
        flash("✅ تم تسجيل الدفعة", "success")
        return redirect(url_for("payments.index"))
    return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/expense/<int:exp_id>/create", methods=["GET", "POST"], endpoint="create_expense_payment")
@login_required
@permission_required("manage_payments")
def create_expense_payment(exp_id):
    exp = _get_or_404(Expense, exp_id)
    form = PaymentForm(meta={"csrf": not current_app.testing})
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}
    form.entity_type.data = "EXPENSE"
    if hasattr(form, "_entity_field_map") and "EXPENSE" in form._entity_field_map:
        getattr(form, form._entity_field_map["EXPENSE"]).data = exp.id
    entity_info = {"type": "expense","number": f"EXP-{exp.id}","date": exp.date.strftime("%Y-%m-%d") if getattr(exp, "date", None) else "","description": exp.description or "","amount": int(q0(D(getattr(exp, "amount", 0) or 0))),"currency": getattr(exp, "currency", "ILS")}
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
        form.total_amount.data = int(q0(D(getattr(exp, "amount", 0) or 0)))
        form.reference.data = f"دفع مصروف {exp.description or ''}".strip()
        form.direction.data = "OUT"
        form.currency.data = ensure_currency(_norm_currency(getattr(exp, "currency", "ILS")))
        if not form.status.data:
            form.status.data = PaymentStatus.COMPLETED.value
        return render_template("payments/form.html", form=form, entity_info=entity_info)
    raw_dir = request.form.get("direction")
    if raw_dir:
        form.direction.data = _norm_dir(raw_dir)
    form.direction.data = "OUT"
    if not form.validate_on_submit():
        if _wants_json():
            return jsonify(status="error", errors=form.errors), 400
        return render_template("payments/form.html", form=form, entity_info=entity_info)
    try:
        parsed_splits = []
        for entry in getattr(form, "splits", []).entries:
            sm = entry.form
            amt_dec = q0(getattr(sm, "amount").data or 0)
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
                        if isinstance(val, (datetime, date)):
                            val = val.isoformat()
                        details[fld] = val
                    elif fld == "card_number":
                        num = "".join(ch for ch in str(val) if ch.isdigit())
                        if num:
                            details["card_last4"] = num[-4:]
                    else:
                        details[fld] = val
            details = _clean_details_local(details)
            parsed_splits.append(PaymentSplit(method=_coerce_method(m_str).value, amount=q0(amt_dec), details=details))
        tgt_total_dec = q0(D(request.form.get("total_amount") or form.total_amount.data or 0))
        if tgt_total_dec <= 0:
            msg = "❌ المبلغ الكلي يجب أن يكون أكبر من صفر."
            if _wants_json():
                return jsonify(status="error", message=msg), 400
            flash(msg, "danger")
            return render_template("payments/form.html", form=form, entity_info=entity_info)
        sum_splits = _sum_splits_decimal(parsed_splits)
        if sum_splits != tgt_total_dec:
            msg = f"❌ مجموع الدفعات الجزئية لا يساوي المبلغ الكلي. المجموع={int(sum_splits)} المطلوب={int(tgt_total_dec)}"
            if _wants_json():
                return jsonify(status="error", message=msg), 400
            flash(msg, "danger")
            return render_template("payments/form.html", form=form, entity_info=entity_info)
        method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data or "cash").value
        notes_raw = (getattr(form, "note", None).data if hasattr(form, "note") else None) or (getattr(form, "notes", None).data if hasattr(form, "notes") else None) or ""
        payment = Payment(
            entity_type="EXPENSE",
            expense_id=exp.id,
            total_amount=q0(tgt_total_dec),
            currency=ensure_currency(form.currency.data or getattr(exp, "currency", "ILS")),
            method=getattr(method_val, "value", method_val),
            direction=_dir_to_db("OUT"),
            status=form.status.data or PaymentStatus.COMPLETED.value,
            payment_date=form.payment_date.data or datetime.utcnow(),
            reference=(form.reference.data or "").strip() or None,
            notes=(notes_raw or "").strip() or None,
            created_by=getattr(current_user, "id", None),
        )
        _ensure_payment_number(payment)
        for sp in parsed_splits:
            payment.splits.append(sp)
        db.session.add(payment)
        db.session.commit()
        log_audit("Payment", payment.id, f"CREATE (expense #{exp.id})")
        if _wants_json():
            return jsonify(status="success", payment=_serialize_payment(payment, full=True)), 201
        flash("✅ تم تسجيل دفع المصروف بنجاح", "success")
        return redirect(url_for("payments.view_payment", payment_id=payment.id))
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify(status="error", message=str(e)), 400
        flash(f"❌ خطأ أثناء تسجيل الدفع: {e}", "danger")
        return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/split/<int:split_id>/delete", methods=["DELETE"], endpoint="delete_split")
@login_required
@permission_required("manage_payments")
def delete_split(split_id):
    split = _get_or_404(PaymentSplit, split_id)
    try:
        payment_id = split.payment_id
        pmt = db.session.get(Payment, payment_id)
        if pmt and (pmt.status == PaymentStatus.COMPLETED.value or str(getattr(pmt.status, "value", pmt.status)) == "COMPLETED"):
            return jsonify(status="error", message="لا يمكن تعديل دفعات سند مكتمل."), 409
        db.session.delete(split)
        db.session.flush()
        if payment_id:
            if pmt is None:
                pmt = db.session.get(Payment, payment_id)
            if pmt is not None:
                _sync_payment_method_with_splits(pmt)
                rem = list(pmt.splits or [])
                pmt.total_amount = _sum_splits_decimal(rem) if rem else q0(0)
                db.session.add(pmt)
        db.session.commit()
        current_app.logger.info("payment.split_deleted", extra={"event": "payments.split.delete", "payment_id": payment_id, "split_id": split_id})
        return jsonify(status="success")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("payment.split_delete_failed", extra={"event": "payments.split.error", "split_id": split_id})
        return jsonify(status="error", message=str(e)), 400


@payments_bp.route("/<int:payment_id>/delete", methods=["POST"], endpoint="delete_payment")
@login_required
@permission_required("manage_payments")
def delete_payment(payment_id):
    wants_json = _wants_json()
    try:
        payment = _get_or_404(Payment, payment_id, options=(joinedload(Payment.splits),))
        related_customer_id = payment.customer_id or (payment.sale.customer_id if payment.sale_id and payment.sale else None) or (payment.invoice.customer_id if payment.invoice_id and payment.invoice else None) or (payment.service.customer_id if payment.service_id and payment.service else None) or (payment.preorder.customer_id if payment.preorder_id and payment.preorder else None)
        related_supplier_id = payment.supplier_id or (payment.shipment.supplier_id if payment.shipment_id and payment.shipment else None) or (payment.loan_settlement.supplier_id if payment.loan_settlement_id and payment.loan_settlement else None)
        related_partner_id = payment.partner_id
        related_sale_id = payment.sale_id
        related_invoice_id = payment.invoice_id
        related_service_id = payment.service_id
        related_preorder_id = payment.preorder_id
        related_loan_settle = payment.loan_settlement_id
        pid = payment.id
        db.session.delete(payment)
        db.session.flush()
        if related_sale_id:
            s = db.session.get(Sale, related_sale_id)
            if s and hasattr(s, "update_payment_status"):
                s.update_payment_status()
                db.session.add(s)
        if related_invoice_id:
            inv = db.session.get(Invoice, related_invoice_id)
            if inv and hasattr(inv, "update_status"):
                inv.update_status()
                db.session.add(inv)
        db.session.commit()
        try:
            if related_customer_id:
                update_entity_balance("customer", related_customer_id)
            if related_supplier_id:
                update_entity_balance("supplier", related_supplier_id)
            if related_partner_id:
                update_entity_balance("partner", related_partner_id)
            if related_loan_settle:
                ls = db.session.get(SupplierLoanSettlement, related_loan_settle)
                if ls and ls.supplier_id:
                    update_entity_balance("supplier", ls.supplier_id)
        except Exception:
            pass
        log_audit("Payment", pid, "DELETE")
        if wants_json:
            return jsonify(status="success", message="تم حذف السند وتحديث الأرصدة"), 200
        flash("✅ تم حذف السند وتحديث الأرصدة بنجاح", "success")
        return redirect(url_for("payments.index"))
    except SQLAlchemyError as e:
        db.session.rollback()
        if wants_json:
            return jsonify(status="error", message=str(e)), 400
        flash(f"❌ تعذر حذف السند: {e}", "danger")
        return redirect(url_for("payments.view_payment", payment_id=payment_id))

from datetime import datetime
from flask import jsonify, render_template
from sqlalchemy.orm import joinedload

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
            "total": int(q0(s.total_amount)),
            "paid": int(q0(s.total_paid)),
            "balance": int(q0(s.balance_due)),
            "currency": (s.currency or "").upper(),
        }

    if _wants_json():
        payload = _serialize_payment(payment, full=True)
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
    """
    Generate a PDF receipt for a payment and return it as a downloadable (or inline) file.

    Query params:
      - inline=1  → show in browser instead of forcing download
    """
    payment = _get_or_404(
        Payment,
        payment_id,
        options=(joinedload(Payment.customer), joinedload(Payment.supplier)),
    )

    try:
        pdf_bytes = _render_payment_receipt_pdf(payment)  # must return raw bytes
        if not pdf_bytes:
            current_app.logger.error("receipt.pdf_empty", extra={"payment_id": payment_id})
            abort(500, description="PDF render returned empty content.")
    except Exception as e:
        current_app.logger.exception("receipt.pdf_error", extra={"payment_id": payment_id})
        abort(500, description=f"Failed to render receipt PDF: {e}")

    # File name: prefer receipt_number, then payment_number, then fallback to id+date
    safe_suffix = (
        (payment.receipt_number or "").strip()
        or (payment.payment_number or "").strip()
        or f"{payment_id}_{datetime.utcnow():%Y%m%d}"
    )
    # Keep it ASCII-safe for headers
    safe_suffix = "".join(ch for ch in safe_suffix if ch.isalnum() or ch in ("-", "_"))
    filename = f"payment_receipt_{safe_suffix or payment_id}.pdf"

    inline = (request.args.get("inline") or "").strip() in ("1", "true", "yes")
    buf = BytesIO(pdf_bytes)
    buf.seek(0)

    resp = send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=not inline,
        download_name=filename,
        max_age=0,
        conditional=False,
        etag=False,
        last_modified=None,
    )

    # Harden caching behavior
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    # Explicit content disposition for some proxies
    resp.headers["Content-Disposition"] = ("inline" if inline else "attachment") + f'; filename="{filename}"'
    return resp
@payments_bp.route("/entity-fields", methods=["GET"], endpoint="entity_fields")
@login_required
@permission_required("manage_payments")
def entity_fields():
    entity_type = (request.args.get("type") or "customer").strip().lower()
    entity_id = request.args.get("entity_id")
    form = PaymentForm()
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}
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
        "loan": (SupplierLoanSettlement, "loan_settlement_id")
    }
    if entity_id:
        try:
            eid = int(entity_id)
            model, field_name = model_map.get(entity_type, (None, None))
            if model is not None and db.session.get(model, eid):
                getattr(form, field_name).data = eid
        except (ValueError, TypeError):
            if _wants_json():
                return jsonify(status="error", message="رقم الجهة غير صالح"), 400
    if hasattr(form, "_sync_entity_id_for_render"):
        form._sync_entity_id_for_render()
    return render_template("payments/_entity_fields.html", form=form)
