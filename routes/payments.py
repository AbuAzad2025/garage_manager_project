# payments.py - Payments Management Routes
# Location: /garage_manager/routes/payments.py
# Description: Payment processing and management routes

from __future__ import annotations

import re
import uuid
from io import BytesIO
from datetime import date, datetime, time
from decimal import Decimal

from flask import (
    Response,
    abort,
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    session,
    send_file,
    make_response,
)
from extensions import csrf
from flask_login import current_user, login_required
from sqlalchemy import (
    func,
    and_,
    case,
    or_,
    select,
    text as sa_text,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from weasyprint import HTML, CSS

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
    Shipment,
    Supplier,
    SupplierLoanSettlement,
)
from utils import (
    log_audit,
    permission_required,
    update_entity_balance,
    _get_or_404,
    q,
    Q2,
    D,
    is_super,
)
try:
    from acl import super_only
except Exception:
    from functools import wraps
    def super_only(f):
        @wraps(f)
        @login_required
        def _w(*a, **kw):
            if is_super():
                return f(*a, **kw)
            abort(403)
        return _w
# Blueprint definition
payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

_FULL_LOAD_OPTIONS = (
    joinedload(Payment.customer),
    joinedload(Payment.supplier),
    joinedload(Payment.partner),
    joinedload(Payment.sale),
    joinedload(Payment.invoice),
    joinedload(Payment.service),
    joinedload(Payment.preorder),
    joinedload(Payment.shipment),
    joinedload(Payment.loan_settlement),
    joinedload(Payment.splits),
)

def _wants_json() -> bool:
    fmt = (request.args.get("format") or "").lower()
    if fmt in ("json", "1", "true", "yes"):
        return True
    try:
        best = request.accept_mimetypes.best or ""
    except Exception:
        best = ""
    return best == "application/json" or request.path.startswith("/api/")

def _safe_filename_component(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^0-9A-Za-z\u0600-\u06FF\-\._]", "", s)
    return s[:120] or ""

def _ok_not_found(msg: str = "السند غير موجود"):
    if _wants_json():
        return jsonify(error="not_found", message=msg), 200
    html = "<!doctype html><meta charset='utf-8'><title>غير موجود</title><div style='padding:24px;font-family:system-ui,Arial,sans-serif'>" + msg + "</div>"
    return make_response(html, 200)

def _safe_get_payment(payment_id: int, *, all_rels: bool = False) -> Payment | None:
    try:
        opts = _FULL_LOAD_OPTIONS if all_rels else (joinedload(Payment.customer), joinedload(Payment.supplier))
        stmt = select(Payment).options(*opts).where(Payment.id == int(payment_id))
        return db.session.execute(stmt).unique().scalar_one_or_none()
    except Exception:
        return None

def q0(x) -> Decimal:
    return q(x, 0)

def _f2(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0

def _line_total(qty, unit_price, disc_pct, tax_pct):
    qy = int(qty or 0)
    u = _f2(unit_price)
    d = _f2(disc_pct)
    t = _f2(tax_pct)
    gross = qy * u
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

def _sale_info_dict(sale) -> dict | None:
    if not sale:
        return None
    try:
        return {
            "number": getattr(sale, "sale_number", None),
            "date": sale.sale_date.strftime("%Y-%m-%d") if getattr(sale, "sale_date", None) else "-",
            "total": int(q0(getattr(sale, "total_amount", 0) or 0)),
            "paid": int(q0(getattr(sale, "total_paid", 0) or 0)),
            "balance": int(q0(getattr(sale, "balance_due", 0) or 0)),
            "currency": (getattr(sale, "currency", "") or "").upper(),
        }
    except Exception:
        return None

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

def _serialize_split(s):
    return {
        "id": s.id,
        "amount": int(q0(getattr(s, "amount", 0) or 0)),
        "method": (getattr(getattr(s, "method", None), "value", getattr(s, "method", "")) or ""),
        "details": (getattr(s, "details", None) or None),
    }

def _serialize_payment_min(p, *, full=False):
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

def _serialize_payment(p, *, full=False):
    return _serialize_payment_min(p, full=full)

def ensure_currency(cur):
    try:
        from models import ensure_currency as _ensure_ccy
    except Exception:
        _ensure_ccy = None
    if _ensure_ccy:
        return _ensure_ccy(cur)
    return (cur or "ILS").strip().upper()

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
    qtxt = (request.args.get("q") or "").strip()
    limit = min(request.args.get("limit", 8, type=int) or 8, MAX_SEARCH_LIMIT)
    if len(qtxt) < 2:
        return jsonify(results=[])
    like = f"%{qtxt}%"
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
        qdigits = "".join(ch for ch in qtxt if ch.isdigit())
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

@payments_bp.route("/", methods=["GET"], endpoint="index")
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
    base_q = Payment.query.filter(Payment.is_archived == False).filter(*filters)
    pagination = base_q.order_by(Payment.payment_date.desc(), Payment.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # حساب الملخصات بالشيكل
    payments_for_summary = Payment.query.filter(*filters).all()
    total_incoming_ils = 0.0
    total_outgoing_ils = 0.0
    grand_total_ils = 0.0
    
    for payment in payments_for_summary:
        try:
            from models import convert_amount
            if payment.currency == 'ILS':
                converted_amount = float(payment.total_amount)
            else:
                converted_amount = float(convert_amount(payment.total_amount, payment.currency, 'ILS', payment.payment_date))
            
            grand_total_ils += converted_amount
            if payment.direction == PaymentDirection.IN.value:
                total_incoming_ils += converted_amount
            else:
                total_outgoing_ils += converted_amount
        except Exception as e:
            # في حالة فشل التحويل، سجل الخطأ ولا تضف المبلغ بعملة مختلفة
            current_app.logger.error(f"❌ خطأ في تحويل العملة للدفعة #{payment.id}: {str(e)} - تجاهل المبلغ من الإحصائيات")
            # لا نضيف المبلغ لأنه بعملة مختلفة ولا يمكن تحويله
    
    net_total_ils = total_incoming_ils - total_outgoing_ils
    
    if currency_param:
        totals_row = db.session.query(
            func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.IN.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_incoming"),
            func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.OUT.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_outgoing"),
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
        func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.IN.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_incoming"),
        func.coalesce(func.sum(case((and_(Payment.direction == PaymentDirection.OUT.value, Payment.status == PaymentStatus.COMPLETED.value), Payment.total_amount), else_=0)), 0).label("total_outgoing"),
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
        total_paid=total_incoming_ils,
        total_incoming=total_incoming_ils,
        total_outgoing=total_outgoing_ils,
        net_total=net_total_ils,
        grand_total=grand_total_ils,
        totals_by_currency=totals_by_currency
    )

@payments_bp.route("/create", methods=["GET", "POST"], endpoint="create_payment")
@login_required
@permission_required("manage_payments")
def create_payment():
    form = PaymentForm()
    # السماح بجميع الاتجاهات لجميع الجهات عدا المصاريف
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}  # المصاريف فقط صادرة
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
                # ملء entity_id أيضاً
                form.entity_id.data = str(eid)
            if et == "CUSTOMER" and eid:
                c = db.session.get(Customer, int(eid))
                if c:
                    balance = int(q0(getattr(c, "balance", 0) or 0))
                    entity_info = {"type": "customer", "name": c.name, "balance": balance, "currency": getattr(c, "currency", "ILS")}
                    # ملء المبلغ تلقائياً إذا كان هناك رصيد
                    if pre_amount is None and balance > 0:
                        pre_amount = balance
                    if not preset_currency:
                        form.currency.data = getattr(c, "currency", "ILS")
                    # ملء اسم العميل في search field
                    if hasattr(form, 'customer_search'):
                        form.customer_search.data = c.name
            elif et == "SUPPLIER" and eid:
                s = db.session.get(Supplier, int(eid))
                if s:
                    balance = int(q0(getattr(s, "balance", 0) or 0))
                    entity_info = {"type": "supplier", "name": s.name, "balance": balance, "currency": getattr(s, "currency", "ILS")}
                    # ملء المبلغ تلقائياً إذا كان هناك رصيد
                    if pre_amount is None and balance > 0:
                        pre_amount = balance
                    if not preset_currency:
                        form.currency.data = getattr(s, "currency", "ILS")
                    # ملء اسم المورد في search field
                    if hasattr(form, 'supplier_search'):
                        form.supplier_search.data = s.name
            elif et == "PARTNER" and eid:
                p = db.session.get(Partner, int(eid))
                if p:
                    balance = int(q0(getattr(p, "balance", 0) or 0))
                    entity_info = {"type": "partner", "name": p.name, "balance": balance, "currency": getattr(p, "currency", "ILS")}
                    # ملء المبلغ تلقائياً إذا كان هناك رصيد
                    if pre_amount is None and balance > 0:
                        pre_amount = balance
                    if not preset_currency:
                        form.currency.data = getattr(p, "currency", "ILS")
                    # ملء اسم الشريك في search field
                    if hasattr(form, 'partner_search'):
                        form.partner_search.data = p.name
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
            return redirect(url_for(".index"))
        raw_dir = request.form.get("direction")
        if raw_dir:
            form.direction.data = _norm_dir(raw_dir)
        etype = (request.form.get("entity_type") or form.entity_type.data or "").upper()
        # المصاريف دائماً صادرة - يتم التحقق من ذلك في النموذج
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
                sum_splits = _sum_splits_decimal(parsed_splits=parsed_splits)
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
                    # إعادة توليد رقم الدفع باستخدام _ensure_payment_number
                    payment.payment_number = None  # إعادة تعيين
                    _ensure_payment_number(payment)
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
                        
                        # إذا كانت المبيعة من حجز مسبق ومدفوعة بالكامل، نحدث حالة الحجز
                        if sale.preorder_id and sale.balance_due <= 0:
                            po = db.session.get(PreOrder, sale.preorder_id)
                            if po and po.status != "FULFILLED":
                                po.status = PreOrderStatus.FULFILLED.value
                                db.session.add(po)
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
                    # لا نحدث حالة الحجز عند دفع العربون
                    # فقط عند دفع المبيعة المرتبطة بالحجز (انظر payment.sale_id)
                    pass
                db.session.commit()
                
                # إنشاء سجل Check تلقائياً إذا كانت إحدى طرق الدفع شيك
                try:
                    from models import Check
                    for split in payment.splits:
                        method_str = str(split.method).upper()
                        if 'CHECK' in method_str or 'CHEQUE' in method_str:
                            details = split.details or {}
                            if details.get('check_number') and details.get('check_bank'):
                                # تحديد اتجاه الشيك بناءً على اتجاه الدفعة
                                check_direction = payment.direction
                                
                                # إنشاء سجل الشيك
                                check = Check(
                                    check_number=details.get('check_number'),
                                    check_bank=details.get('check_bank'),
                                    check_date=payment.payment_date or datetime.utcnow(),
                                    check_due_date=details.get('check_due_date') or payment.payment_date or datetime.utcnow(),
                                    amount=split.amount,
                                    currency=payment.currency or 'ILS',
                                    direction=check_direction,
                                    status='PENDING',  # حالة افتراضية
                                    # ربط بالجهات
                                    customer_id=payment.customer_id,
                                    supplier_id=payment.supplier_id,
                                    partner_id=payment.partner_id,
                                    # معلومات الربط
                                    reference_number=f"PMT-{payment.id}",
                                    notes=f"شيك من دفعة رقم {payment.payment_number or payment.id}",
                                    # معلومات المستخدم
                                    created_by_id=payment.created_by
                                )
                                db.session.add(check)
                                current_app.logger.info(f"✅ تم إنشاء سجل شيك رقم {check.check_number} من دفعة رقم {payment.id}")
                    
                    db.session.commit()
                except Exception as e:
                    # في حالة فشل إنشاء الشيك، لا نُفشل الدفعة
                    current_app.logger.warning(f"⚠️ فشل إنشاء سجل شيك من دفعة {payment.id}: {str(e)}")
                    db.session.rollback()
                    
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
        return redirect(url_for(".index"))
    return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/expense/<int:exp_id>/create", methods=["GET", "POST"], endpoint="create_expense_payment")
@login_required
@permission_required("manage_payments")
def create_expense_payment(exp_id):
    exp = _get_or_404(Expense, exp_id)
    form = PaymentForm()
    # السماح بجميع الاتجاهات لجميع الجهات عدا المصاريف
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}  # المصاريف فقط صادرة
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
        form.currency.data = ensure_currency((getattr(exp, "currency", "ILS") or "ILS"))
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
        return redirect(url_for(".index"))
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

@payments_bp.route("/<int:payment_id>", methods=["GET"], endpoint="view_payment")
@login_required
@permission_required("manage_payments")
def view_payment(payment_id: int):
    """عرض تفاصيل الدفعة"""
    payment = _safe_get_payment(payment_id, all_rels=True)
    if not payment:
        if _wants_json():
            return jsonify(error="not_found", message="السند غير موجود"), 404
        flash("السند غير موجود", "error")
        return redirect(url_for("payments_bp.index"))
    
    if _wants_json():
        return jsonify(payment=_serialize_payment(payment, full=True))
    
    return render_template("payments/view.html", payment=payment)

@payments_bp.route("/<int:payment_id>/status", methods=["POST"], endpoint="update_payment_status")
@login_required
@permission_required("manage_payments")
@csrf.exempt
def update_payment_status(payment_id: int):
    """تحديث حالة الدفعة"""
    payment = _safe_get_payment(payment_id, all_rels=True)
    if not payment:
        return jsonify(error="not_found", message="السند غير موجود"), 404
    
    # الحصول على الحالة الجديدة من JSON أو form data
    if request.is_json:
        new_status = request.json.get("status")
    else:
        new_status = request.form.get("status")
    
    if not new_status:
        return jsonify(error="missing_status", message="يجب تحديد الحالة الجديدة"), 400
    
    # التحقق من صحة الحالة الجديدة
    valid_statuses = ["COMPLETED", "PENDING", "FAILED", "REFUNDED"]
    if new_status not in valid_statuses:
        return jsonify(error="invalid_status", message="حالة غير صحيحة"), 400
    
    try:
        payment.status = new_status
        db.session.commit()
        
        return jsonify(success=True, message="تم تحديث حالة الدفعة بنجاح", status=new_status)
        
    except Exception as e:
        db.session.rollback()
        return jsonify(error="update_failed", message=str(e)), 500

@payments_bp.route("/<int:payment_id>", methods=["DELETE"], endpoint="delete_payment")
@login_required
@super_only
def delete_payment(payment_id: int):
    payment = _safe_get_payment(payment_id, all_rels=True)
    if not payment:
        return _ok_not_found("السند غير موجود (لا حاجة لإجراء)")
    try:
        with db.session.begin():
            if hasattr(payment, "splits") and payment.splits:
                for sp in list(payment.splits):
                    db.session.delete(sp)
            db.session.delete(payment)
        if _wants_json():
            return jsonify(status="ok", deleted_id=payment_id), 200
        return redirect(url_for(".index"))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("payment.delete_error", extra={"payment_id": payment_id})
        if _wants_json():
            return jsonify(ok=False, error="delete_failed", message=str(e)), 500
        return make_response("<!doctype html><meta charset='utf-8'><div style='padding:24px;font-family:system-ui,Arial,sans-serif'>تعذّر حذف السند</div>", 500)

@payments_bp.route("/<int:payment_id>/receipt", methods=["GET"], endpoint="view_receipt")
@login_required
@permission_required("manage_payments")
def view_receipt(payment_id: int):
    payment = _safe_get_payment(payment_id, all_rels=True)
    if not payment:
        return _ok_not_found()
    sale_info = _sale_info_dict(payment.sale) if getattr(payment, "sale_id", None) else None
    if _wants_json():
        payload = _serialize_payment_min(payment)
        payload["sale_info"] = sale_info
        return jsonify(payment=payload)
    return render_template("payments/receipt.html", payment=payment, now=datetime.utcnow(), sale_info=sale_info)

@payments_bp.route("/<int:payment_id>/receipt/download", methods=["GET"], endpoint="download_receipt")
@login_required
@permission_required("manage_payments")
def download_receipt(payment_id: int):
    payment = _safe_get_payment(payment_id, all_rels=False)
    if not payment:
        return _ok_not_found("السند غير موجود للتنزيل")
    try:
        pdf_bytes = _render_payment_receipt_pdf(payment)
        if not pdf_bytes:
            if _wants_json():
                return jsonify(error="render_error", message="تعذّر توليد PDF"), 500
            return make_response("<!doctype html><meta charset='utf-8'><div style='padding:24px;font-family:system-ui,Arial,sans-serif'>تعذّر توليد PDF</div>", 500)
    except Exception as e:
        current_app.logger.exception("receipt.pdf_error", extra={"payment_id": payment_id})
        if _wants_json():
            return jsonify(error="exception", message=str(e)), 500
        return make_response("<!doctype html><meta charset='utf-8'><div style='padding:24px;font-family:system-ui,Arial,sans-serif'>حصل خطأ أثناء توليد PDF</div>", 500)
    safe_suffix = (getattr(payment, "receipt_number", "") or "").strip() or (getattr(payment, "payment_number", "") or "").strip() or f"{payment_id}_{datetime.utcnow():%Y%m%d}"
    safe_suffix = _safe_filename_component(safe_suffix)
    filename = f"payment_receipt_{safe_suffix or payment_id}.pdf"
    inline = (request.args.get("inline") or "").strip().lower() in ("1", "true", "yes")
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
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Content-Disposition"] = ("inline" if inline else "attachment") + f'; filename="{filename}"'
    return resp

@payments_bp.route("/entity-fields", methods=["GET"], endpoint="entity_fields")
@login_required
@permission_required("manage_payments")
def entity_fields():
    entity_type = (request.args.get("type") or "customer").strip().lower()
    entity_id = request.args.get("entity_id")
    form = PaymentForm()
    # السماح بجميع الاتجاهات لجميع الجهات عدا المصاريف
    form._incoming_entities = set()
    form._outgoing_entities = {"EXPENSE"}  # المصاريف فقط صادرة
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

def _ensure_payment_number(pmt: Payment) -> None:
    if getattr(pmt, "payment_number", None):
        return
    base_dt = getattr(pmt, "payment_date", None) or datetime.utcnow()
    prefix = base_dt.strftime("PMT%Y%m%d")
    
    # استخدام MAX بدلاً من COUNT لتجنب التكرار
    result = db.session.execute(
        sa_text("SELECT payment_number FROM payments WHERE payment_number LIKE :pfx ORDER BY payment_number DESC LIMIT 1"), 
        {"pfx": f"{prefix}-%"}
    ).scalar()
    
    if result:
        try:
            last_num = int(result.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    
    # محاولة إيجاد رقم فريد
    for attempt in range(100):
        candidate = f"{prefix}-{next_num:04d}"
        exists = db.session.execute(
            sa_text("SELECT 1 FROM payments WHERE payment_number = :num LIMIT 1"),
            {"num": candidate}
        ).scalar()
        if not exists:
            pmt.payment_number = candidate
            return
        next_num += 1
    
    # fallback: استخدام timestamp
    import time
    pmt.payment_number = f"{prefix}-{int(time.time() * 1000) % 10000:04d}"

def _sum_splits_decimal(splits=None, parsed_splits=None) -> Decimal:
    seq = parsed_splits if parsed_splits is not None else splits
    total = Decimal("0")
    for s in (seq or []):
        total += q0(getattr(s, "amount", 0))
    return q0(total)




@payments_bp.route("/api/entities/<entity_type>", methods=["GET"], endpoint="get_entities")
@login_required
@permission_required("manage_payments")
def get_entities(entity_type):
    """API للحصول على الجهات حسب النوع مع فلترة ذكية"""
    search = request.args.get("search", "").strip()
    limit = min(int(request.args.get("limit", 20)), 100)
    
    try:
        if entity_type == "CUSTOMER":
            query = Customer.query.filter_by(is_active=True)
            if search:
                query = query.filter(
                    or_(
                        Customer.name.ilike(f"%{search}%"),
                        Customer.phone.ilike(f"%{search}%"),
                        Customer.email.ilike(f"%{search}%")
                    )
                )
            entities = query.order_by(Customer.name).limit(limit).all()
            return jsonify([{
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "display": f"{c.name} - {c.phone}"
            } for c in entities])
            
        elif entity_type == "SUPPLIER":
            query = Supplier.query.filter_by(is_active=True)
            if search:
                query = query.filter(
                    or_(
                        Supplier.name.ilike(f"%{search}%"),
                        Supplier.email.ilike(f"%{search}%")
                    )
                )
            entities = query.order_by(Supplier.name).limit(limit).all()
            return jsonify([{
                "id": s.id,
                "name": s.name,
                "email": s.email,
                "display": f"{s.name} - {s.email}"
            } for s in entities])
            
        elif entity_type == "PARTNER":
            query = Partner.query.filter_by(is_active=True)
            if search:
                query = query.filter(
                    or_(
                        Partner.name.ilike(f"%{search}%"),
                        Partner.email.ilike(f"%{search}%")
                    )
                )
            entities = query.order_by(Partner.name).limit(limit).all()
            return jsonify([{
                "id": p.id,
                "name": p.name,
                "email": p.email,
                "display": f"{p.name} - {p.email}"
            } for p in entities])
            
        elif entity_type == "SALE":
            query = Sale.query.filter_by(status="CONFIRMED")
            if search:
                query = query.join(Customer).filter(
                    or_(
                        Sale.sale_number.ilike(f"%{search}%"),
                        Customer.name.ilike(f"%{search}%")
                    )
                )
            entities = query.order_by(Sale.sale_date.desc()).limit(limit).all()
            return jsonify([{
                "id": s.id,
                "sale_number": s.sale_number,
                "customer_name": s.customer.name if s.customer else "غير محدد",
                "total_amount": float(s.total_amount or 0),
                "display": f"{s.sale_number} - {s.customer.name if s.customer else 'غير محدد'}"
            } for s in entities])
            
        elif entity_type == "INVOICE":
            query = Invoice.query.filter_by(status="UNPAID")
            if search:
                query = query.join(Customer).filter(
                    or_(
                        Invoice.invoice_number.ilike(f"%{search}%"),
                        Customer.name.ilike(f"%{search}%")
                    )
                )
            entities = query.order_by(Invoice.invoice_date.desc()).limit(limit).all()
            return jsonify([{
                "id": i.id,
                "invoice_number": i.invoice_number,
                "customer_name": i.customer.name if i.customer else "غير محدد",
                "total_amount": float(i.total_amount or 0),
                "display": f"{i.invoice_number} - {i.customer.name if i.customer else 'غير محدد'}"
            } for i in entities])
            
        else:
            return jsonify([])
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@payments_bp.route("/search-entities", methods=["GET"], endpoint="search_entities")
@login_required
@permission_required("manage_payments")
def search_entities():
    """البحث الذكي عن الجهات المرتبطة للدفعات"""
    try:
        entity_type = request.args.get("type", "").strip().lower()
        query = request.args.get("q", "").strip()
        
        if not entity_type or not query:
            return jsonify([])
        
        # البحث في العملاء
        if entity_type == "customer":
            customers = Customer.query.filter(
                or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                    Customer.email.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "display": f"{c.name} - {c.phone}" if c.phone else c.name
            } for c in customers])
        
        # البحث في الموردين
        elif entity_type == "supplier":
            suppliers = Supplier.query.filter(
                or_(
                    Supplier.name.ilike(f"%{query}%"),
                    Supplier.contact.ilike(f"%{query}%"),
                    Supplier.phone.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": s.id,
                "name": s.name,
                "contact": s.contact,
                "phone": s.phone,
                "display": f"{s.name} - {s.phone}" if s.phone else s.name
            } for s in suppliers])
        
        # البحث في الشركاء
        elif entity_type == "partner":
            partners = Partner.query.filter(
                or_(
                    Partner.name.ilike(f"%{query}%"),
                    Partner.contact.ilike(f"%{query}%"),
                    Partner.phone.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": p.id,
                "name": p.name,
                "contact": p.contact,
                "phone": p.phone,
                "display": f"{p.name} - {p.phone}" if p.phone else p.name
            } for p in partners])
        
        # البحث في المبيعات
        elif entity_type == "sale":
            sales = Sale.query.join(Customer).filter(
                or_(
                    Sale.sale_number.ilike(f"%{query}%"),
                    Customer.name.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": s.id,
                "sale_number": s.sale_number,
                "customer_name": s.customer.name if s.customer else "غير محدد",
                "total_amount": float(s.total_amount or 0),
                "display": f"{s.sale_number} - {s.customer.name if s.customer else 'غير محدد'}"
            } for s in sales])
        
        # البحث في طلبات الصيانة
        elif entity_type == "service":
            services = ServiceRequest.query.join(Customer).filter(
                or_(
                    ServiceRequest.service_number.ilike(f"%{query}%"),
                    Customer.name.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": s.id,
                "service_number": s.service_number,
                "customer_name": s.customer.name if s.customer else "غير محدد",
                "display": f"{s.service_number} - {s.customer.name if s.customer else 'غير محدد'}"
            } for s in services])
        
        # البحث في الشحنات
        elif entity_type == "shipment":
            shipments = Shipment.query.join(Supplier).filter(
                or_(
                    Shipment.shipment_number.ilike(f"%{query}%"),
                    Supplier.name.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": s.id,
                "shipment_number": s.shipment_number,
                "supplier_name": s.supplier.name if s.supplier else "غير محدد",
                "display": f"{s.shipment_number} - {s.supplier.name if s.supplier else 'غير محدد'}"
            } for s in shipments])
        
        # البحث في النفقات
        elif entity_type == "expense":
            expenses = Expense.query.filter(
                or_(
                    Expense.description.ilike(f"%{query}%"),
                    Expense.reference.ilike(f"%{query}%")
                )
            ).limit(10).all()
            
            return jsonify([{
                "id": e.id,
                "description": e.description,
                "reference": e.reference,
                "amount": float(e.amount or 0),
                "display": f"{e.description} - {e.reference}" if e.reference else e.description
            } for e in expenses])
        
        else:
            return jsonify([])
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== نظام الدفع المتكامل للمتجر =====

@payments_bp.route("/shop/checkout", methods=["POST"], endpoint="shop_checkout")
@login_required
@permission_required("manage_payments")
def shop_checkout():
    """إنشاء طلب دفع للمتجر الإلكتروني"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        # التحقق من البيانات المطلوبة
        required_fields = ["items", "total_amount", "currency"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"حقل {field} مطلوب"}), 400
        
        items = data.get("items", [])
        if not items:
            return jsonify({"error": "لا توجد منتجات في الطلب"}), 400
        
        total_amount = float(data.get("total_amount", 0))
        if total_amount <= 0:
            return jsonify({"error": "المبلغ الإجمالي يجب أن يكون أكبر من صفر"}), 400
        
        currency = data.get("currency", "ILS")
        payment_method = data.get("payment_method", "CASH")
        customer_id = data.get("customer_id")
        
        # إنشاء الدفعة
        payment = Payment(
            entity_type="SHOP_ORDER",
            customer_id=customer_id,
            direction=PaymentDirection.IN.value,
            status=PaymentStatus.PENDING.value,
            payment_date=datetime.utcnow(),
            total_amount=total_amount,
            currency=currency,
            method=payment_method,
            reference=f"طلب متجر #{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            notes=f"دفعة متجر إلكتروني - {len(items)} منتج",
            created_by=current_user.id,
        )
        
        _ensure_payment_number(payment)
        db.session.add(payment)
        db.session.flush()
        
        # إضافة تفاصيل المنتجات
        for item in items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 1)
            unit_price = item.get("unit_price", 0)
            
            if product_id and quantity > 0:
                # يمكن إضافة جدول منفصل لتفاصيل طلبات المتجر
                pass
        
        db.session.commit()
        
        # إرسال إشعار
        try:
            from notifications import notify_order_created
            notify_order_created(payment.id, {
                "type": "shop_order",
                "total_amount": total_amount,
                "currency": currency,
                "items_count": len(items)
            })
        except ImportError:
            pass
        
        return jsonify({
            "success": True,
            "payment_id": payment.id,
            "payment_number": payment.payment_number,
            "total_amount": total_amount,
            "currency": currency,
            "status": payment.status
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@payments_bp.route("/shop/payment-methods", methods=["GET"], endpoint="shop_payment_methods")
@login_required
def shop_payment_methods():
    """الحصول على طرق الدفع المتاحة للمتجر"""
    methods = [
        {
            "id": "CASH",
            "name": "نقدي",
            "description": "دفع نقدي عند الاستلام",
            "icon": "fas fa-money-bill-wave",
            "enabled": True
        },
        {
            "id": "BANK_TRANSFER",
            "name": "تحويل بنكي",
            "description": "تحويل إلى الحساب البنكي",
            "icon": "fas fa-university",
            "enabled": True
        },
        {
            "id": "CREDIT_CARD",
            "name": "بطاقة ائتمان",
            "description": "دفع بالبطاقة الائتمانية",
            "icon": "fas fa-credit-card",
            "enabled": True
        },
        {
            "id": "CHECK",
            "name": "شيك",
            "description": "دفع بشيك",
            "icon": "fas fa-file-invoice",
            "enabled": True
        }
    ]
    
    return jsonify({"payment_methods": methods})


@payments_bp.route("/shop/process-payment", methods=["POST"], endpoint="shop_process_payment")
@login_required
@permission_required("manage_payments")
def shop_process_payment():
    """معالجة الدفع للمتجر"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        payment_id = data.get("payment_id")
        if not payment_id:
            return jsonify({"error": "معرف الدفعة مطلوب"}), 400
        
        payment = db.session.get(Payment, payment_id)
        if not payment:
            return jsonify({"error": "الدفعة غير موجودة"}), 404
        
        if payment.status != PaymentStatus.PENDING.value:
            return jsonify({"error": "الدفعة غير قابلة للمعالجة"}), 400
        
        # تحديث حالة الدفعة
        payment.status = PaymentStatus.COMPLETED.value
        payment.payment_date = datetime.utcnow()
        
        # تحديث رصيد العميل إذا كان موجود
        if payment.customer_id:
            try:
                from utils import update_entity_balance
                update_entity_balance("customer", payment.customer_id)
            except ImportError:
                pass
        
        db.session.commit()
        
        # إرسال إشعار نجاح الدفع
        try:
            from notifications import notify_payment_received
            notify_payment_received(payment.id, float(payment.total_amount), payment.currency)
        except ImportError:
            pass
        
        return jsonify({
            "success": True,
            "message": "تم معالجة الدفعة بنجاح",
            "payment_id": payment.id,
            "status": payment.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@payments_bp.route("/shop/refund", methods=["POST"], endpoint="shop_refund")
@login_required
@permission_required("manage_payments")
def shop_refund():
    """استرداد مبلغ للمتجر"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        payment_id = data.get("payment_id")
        refund_amount = float(data.get("refund_amount", 0))
        reason = data.get("reason", "استرداد")
        
        if not payment_id:
            return jsonify({"error": "معرف الدفعة مطلوب"}), 400
        
        if refund_amount <= 0:
            return jsonify({"error": "مبلغ الاسترداد يجب أن يكون أكبر من صفر"}), 400
        
        original_payment = db.session.get(Payment, payment_id)
        if not original_payment:
            return jsonify({"error": "الدفعة غير موجودة"}), 404
        
        if original_payment.status != PaymentStatus.COMPLETED.value:
            return jsonify({"error": "لا يمكن استرداد دفعة غير مكتملة"}), 400
        
        # إنشاء دفعة استرداد
        refund_payment = Payment(
            entity_type="SHOP_REFUND",
            customer_id=original_payment.customer_id,
            direction=PaymentDirection.OUT.value,
            status=PaymentStatus.COMPLETED.value,
            payment_date=datetime.utcnow(),
            total_amount=refund_amount,
            currency=original_payment.currency,
            method=original_payment.method,
            reference=f"استرداد - {original_payment.payment_number}",
            notes=f"استرداد مبلغ: {reason}",
            created_by=current_user.id,
        )
        
        _ensure_payment_number(refund_payment)
        db.session.add(refund_payment)
        
        # تحديث رصيد العميل
        if original_payment.customer_id:
            try:
                from utils import update_entity_balance
                update_entity_balance("customer", original_payment.customer_id)
            except ImportError:
                pass
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم إنشاء استرداد بنجاح",
            "refund_id": refund_payment.id,
            "refund_amount": refund_amount,
            "currency": original_payment.currency
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@payments_bp.route("/shop/payment-status/<int:payment_id>", methods=["GET"], endpoint="shop_payment_status")
@login_required
def shop_payment_status(payment_id):
    """التحقق من حالة الدفع"""
    try:
        payment = db.session.get(Payment, payment_id)
        if not payment:
            return jsonify({"error": "الدفعة غير موجودة"}), 404
        
        return jsonify({
            "payment_id": payment.id,
            "payment_number": payment.payment_number,
            "status": payment.status,
            "total_amount": float(payment.total_amount),
            "currency": payment.currency,
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "created_at": payment.created_at.isoformat() if payment.created_at else None
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@payments_bp.route("/archive/<int:payment_id>", methods=["POST"])
@login_required
def archive_payment(payment_id):
    print(f"🔍 [PAYMENT ARCHIVE] بدء أرشفة الدفعة رقم: {payment_id}")
    print(f"🔍 [PAYMENT ARCHIVE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    print(f"🔍 [PAYMENT ARCHIVE] البيانات المرسلة: {dict(request.form)}")
    
    try:
        from models import Archive
        
        payment = Payment.query.get_or_404(payment_id)
        print(f"✅ [PAYMENT ARCHIVE] تم العثور على الدفعة: {payment.id}")
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        print(f"📝 [PAYMENT ARCHIVE] سبب الأرشفة: {reason}")
        
        archive = Archive.archive_record(
            record=payment,
            reason=reason,
            user_id=current_user.id
        )
        payment.is_archived = True
        payment.archived_at = datetime.utcnow()
        payment.archived_by = current_user.id
        payment.archive_reason = reason
        db.session.commit()
        flash(f'تم أرشفة الدفعة رقم {payment.id} بنجاح', 'success')
        return redirect(url_for('payments_bp.index'))
        
    except Exception as e:
        print(f"❌ [PAYMENT ARCHIVE] خطأ في أرشفة الدفعة: {str(e)}")
        print(f"❌ [PAYMENT ARCHIVE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [PAYMENT ARCHIVE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في أرشفة الدفعة: {str(e)}', 'error')
        return redirect(url_for('payments_bp.index'))

@payments_bp.route("/restore/<int:payment_id>", methods=["POST"])
@login_required
def restore_payment(payment_id):
    """استعادة دفعة"""
    print(f"🔍 [PAYMENT RESTORE] بدء استعادة الدفعة رقم: {payment_id}")
    print(f"🔍 [PAYMENT RESTORE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    
    try:
        payment = Payment.query.get_or_404(payment_id)
        print(f"✅ [PAYMENT RESTORE] تم العثور على الدفعة: {payment.payment_number}")
        
        if not payment.is_archived:
            flash('الدفعة غير مؤرشفة', 'warning')
            return redirect(url_for('payments_bp.index'))
        
        # البحث عن الأرشيف
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='payments',
            record_id=payment_id
        ).first()
        
        if archive:
            print(f"✅ [PAYMENT RESTORE] تم العثور على الأرشيف: {archive.id}")
            # حذف الأرشيف
            db.session.delete(archive)
            print(f"🗑️ [PAYMENT RESTORE] تم حذف الأرشيف")
        
        # استعادة الدفعة
        print(f"📝 [PAYMENT RESTORE] بدء استعادة الدفعة...")
        payment.is_archived = False
        payment.archived_at = None
        payment.archived_by = None
        payment.archive_reason = None
        db.session.commit()
        print(f"✅ [PAYMENT RESTORE] تم استعادة الدفعة بنجاح")
        
        flash(f'تم استعادة الدفعة رقم {payment_id} بنجاح', 'success')
        print(f"🎉 [PAYMENT RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('payments_bp.index'))
        
    except Exception as e:
        print(f"❌ [PAYMENT RESTORE] خطأ في استعادة الدفعة: {str(e)}")
        print(f"❌ [PAYMENT RESTORE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [PAYMENT RESTORE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في استعادة الدفعة: {str(e)}', 'error')
        return redirect(url_for('payments_bp.index'))
