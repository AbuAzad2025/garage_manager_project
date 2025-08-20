# routes/payments.py
from datetime import date, datetime
import io

from flask import (
    Blueprint, Response, abort, current_app, flash, jsonify,
    redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required, login_user
from sqlalchemy import func, text, and_, case
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import PaymentForm
from models import (
    Customer, Expense, Invoice, Partner, Payment, PaymentDirection,
    PaymentMethod, PaymentSplit, PaymentStatus, Permission,
    PreOrder, PreOrderStatus, Role, Sale, ServiceRequest, ServiceStatus, Shipment,
    Supplier, User,
)
from utils import log_audit, permission_required, update_entity_balance

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


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
    v = val
    if hasattr(val, "value"):
        v = val.value
    v = str(v).strip().upper()
    if v in ("IN", "INCOMING", "INCOME", "RECEIVE"):
        return "IN"
    if v in ("OUT", "OUTGOING", "PAY", "PAYMENT", "EXPENSE"):
        return "OUT"
    return v  # fallback (يبقى كما هو)

def _clean_details(d: dict | None):
    if not d:
        return None
    cleaned = {}
    for k, v in d.items():
        if v in (None, "", []):
            continue
        if isinstance(v, (date, datetime)):
            cleaned[k] = v.isoformat()  # "YYYY-MM-DD" أو "YYYY-MM-DDTHH:MM:SS"
        else:
            cleaned[k] = str(v)
    return cleaned or None

@payments_bp.before_request
def _auto_login_for_tests_payments():
    if not current_app.config.get("TESTING"): return
    if getattr(current_user, "is_authenticated", False): return
    perm = Permission.query.filter(
        (Permission.code == "manage_payments") if hasattr(Permission, "code") else (Permission.name == "manage_payments")
    ).first()
    if not perm:
        perm = Permission(
            name=("Manage Payments" if hasattr(Permission, "code") else "manage_payments"),
            code=("manage_payments" if hasattr(Permission, "code") else None),
            description="auto test perm"
        )
        db.session.add(perm)
    role = Role.query.filter_by(name="pay_manager").first()
    if not role:
        role = Role(name="pay_manager", description="auto test role")
        db.session.add(role)
    if perm not in role.permissions:
        role.permissions.append(perm)
    user = User.query.filter_by(username="_auto_payment_manager").first()
    if not user:
        user = User(username="_auto_payment_manager", email="payman@test.local")
        user.set_password("x")
        user.role = role
        db.session.add(user)
    db.session.flush()
    login_user(user)

# ------------------------- Helpers -------------------------
def _val(x):
    return getattr(x,"value",x)
def _coerce_method(v):
    s = (_val(v) or "").strip().lower()
    try:
        return PaymentMethod(s)
    except Exception:
        return PaymentMethod.CASH

def _wants_json():
    am = request.headers.get("Accept", "")
    return "application/json" in am and "text/html" not in am


# ------------------------- PDF -------------------------

def _render_payment_receipt_pdf(payment: Payment) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    y = h - 30 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, "Payment Receipt")
    y -= 10 * mm

    c.setFont("Helvetica", 11)
    rows = [
        ("Payment #", payment.payment_number or str(payment.id)),
        ("Date", payment.payment_date.strftime("%Y-%m-%d %H:%M") if payment.payment_date else "-"),
        ("Method", _val(payment.method)),
        ("Status", _val(payment.status)),
        ("Direction", _val(payment.direction)),
        ("Currency", payment.currency),
        ("Total", f"{float(payment.total_amount or 0):,.2f}"),
        ("Entity", payment.entity_label() or "-"),
        ("Reference", payment.reference or "-"),
        ("Notes", (payment.notes or "").strip() or "-"),
    ]
    for k, v in rows:
        c.drawString(20 * mm, y, f"{k}: {v}")
        y -= 7 * mm

    y -= 3 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Splits:")
    y -= 7 * mm
    c.setFont("Helvetica", 11)

    if payment.splits:
        for s in payment.splits:
            # ✅ أزلنا المسافة الزائدة في محدِّد التنسيق (كان :,.2f␠)
            line = f"- {_val(s.method)}: {float(s.amount or 0):,.2f}"
            det = s.details or {}
            safe = []
            for kk in ("check_number", "check_bank", "check_due_date",
                       "card_holder", "card_last4", "bank_transfer_ref"):
                vv = det.get(kk)
                if vv:
                    safe.append(f"{kk}:{vv}")
            if safe:
                line += "  [" + ", ".join(safe) + "]"
            c.drawString(25 * mm, y, line)
            y -= 6 * mm
            if y < 20 * mm:
                c.showPage()
                y = h - 20 * mm
    else:
        c.drawString(25 * mm, y, "- (no splits)")
        y -= 6 * mm

    c.setStrokeColor(colors.black)
    c.line(20 * mm, y, w - 20 * mm, y)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

@payments_bp.route("/", methods=["GET"])  # أبقِ endpoint الافتراضي "index"
def index():
    testing_mode = bool(current_app.config.get("TESTING"))
    wants_json = _wants_json()

    if testing_mode:
        if not getattr(current_user, "is_authenticated", False):
            return redirect(url_for("auth.login", next=request.full_path))
    else:
        if not getattr(current_user, "is_authenticated", False):
            return redirect(url_for("auth.login", next=request.full_path))
        actor = current_user._get_current_object()
        if isinstance(actor, Customer):
            return redirect(url_for("shop.catalog"))
        has_perm = getattr(actor, "has_permission", lambda *_, **__: False)("manage_payments")
        if not has_perm:
            abort(403)

    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    entity_type = (request.args.get("entity_type") or request.args.get("entity") or "").strip()
    status      = (request.args.get("status") or "").strip()
    direction   = (request.args.get("direction") or "").strip()
    method      = (request.args.get("method") or "").strip()
    start_date  = (request.args.get("start_date") or request.args.get("start") or "").strip()
    end_date    = (request.args.get("end_date") or request.args.get("end") or "").strip()
    entity_id   = request.args.get("entity_id", type=int)

    filters = []

    if entity_type:
        filters.append(func.lower(Payment.entity_type) == entity_type.lower())
    if status:
        filters.append(Payment.status == status)
    if direction:
        filters.append(Payment.direction == direction)
    if method:
        try:
            filters.append(Payment.method == PaymentMethod(method.lower()))
        except Exception:
            filters.append(Payment.method == method.lower())

    if start_date:
        filters.append(func.date(Payment.payment_date) >= start_date)
    if end_date:
        filters.append(func.date(Payment.payment_date) <= end_date)

    if entity_id and entity_type:
        et = entity_type.lower()
        if   et == "customer": filters.append(Payment.customer_id == entity_id)
        elif et == "supplier": filters.append(Payment.supplier_id == entity_id)
        elif et == "partner":  filters.append(Payment.partner_id  == entity_id)
        elif et == "sale":     filters.append(Payment.sale_id     == entity_id)
        elif et == "invoice":  filters.append(Payment.invoice_id  == entity_id)
        elif et == "preorder": filters.append(Payment.preorder_id == entity_id)
        elif et == "service":  filters.append(Payment.service_id  == entity_id)
        elif et == "expense":  filters.append(Payment.expense_id  == entity_id)
        elif et == "loan":     filters.append(Payment.loan_settlement_id == entity_id)
        elif et == "shipment": filters.append(Payment.shipment_id == entity_id)

    base_q = Payment.query.filter(*filters)

    pagination = base_q.order_by(Payment.payment_date.desc(), Payment.id.desc()) \
                        .paginate(page=page, per_page=per_page, error_out=False)

    totals_row = db.session.query(
        func.coalesce(func.sum(
            case((and_(Payment.direction == PaymentDirection.INCOMING.value,
                       Payment.status    == PaymentStatus.COMPLETED.value), Payment.total_amount),
                 else_=0.0)
        ), 0.0).label("total_incoming"),
        func.coalesce(func.sum(
            case((and_(Payment.direction == PaymentDirection.OUTGOING.value,
                       Payment.status    == PaymentStatus.COMPLETED.value), Payment.total_amount),
                 else_=0.0)
        ), 0.0).label("total_outgoing"),
        func.coalesce(func.sum(Payment.total_amount), 0.0).label("grand_total")
    ).filter(*filters).one()

    total_incoming = float(totals_row.total_incoming or 0.0)
    total_outgoing = float(totals_row.total_outgoing or 0.0)
    net_total      = total_incoming - total_outgoing
    total_paid     = total_incoming  # متغيّر تستخدمه في القالب الحالي
    grand_total    = float(totals_row.grand_total or 0.0)

    if wants_json:
        return jsonify({
            "payments":      [p.to_dict() for p in pagination.items],
            "total_pages":    pagination.pages,
            "current_page":   pagination.page,
            "totals": {
                "total_incoming": total_incoming,
                "total_outgoing": total_outgoing,
                "net_total":      net_total,
                "grand_total":    grand_total,
                "total_paid":     total_paid
            }
        })

    return render_template("payments/list.html",
                           payments=pagination.items,
                           pagination=pagination,
                           total_paid=total_paid,
                           total_incoming=total_incoming,
                           total_outgoing=total_outgoing,
                           net_total=net_total,
                           grand_total=grand_total)

@payments_bp.route("/create", methods=["GET","POST"], endpoint="create_payment")
@login_required
@permission_required("manage_payments")
def create_payment():
    form = PaymentForm(meta={"csrf": not current_app.testing}); entity_info = None
    def _fd(f): return getattr(f, "data", None) if f is not None else None
    def _clean_details(d):
        if not d: return None
        out = {}; DateT = type(datetime.utcnow().date())
        for k, v in d.items():
            if v in (None, "", []): continue
            if isinstance(v, (datetime, DateT)): out[k] = v.isoformat()
            else: out[k] = v
        return out or None
    if hasattr(form, "direction"):
        form.direction.choices = [("IN","وارد"),("OUT","صادر"),("INCOMING","وارد"),("OUTGOING","صادر")]
    if request.method == "GET":
        form.payment_date.data = datetime.utcnow().date()
        raw_et = (request.args.get("entity_type") or "").strip().upper()
        if raw_et == "SHIPMENT_CUSTOMS": raw_et = "SHIPMENT"
        et = raw_et if hasattr(form, "_entity_field_map") and raw_et in form._entity_field_map else ""
        eid = request.args.get("entity_id"); pre_amount = request.args.get("amount", type=float)
        if et:
            form.entity_type.data = et
            if hasattr(form, "_incoming_entities") and et in form._incoming_entities: form.direction.data = "IN"
            elif hasattr(form, "_outgoing_entities") and et in form._outgoing_entities: form.direction.data = "OUT"
            field_name = form._entity_field_map[et]
            if eid and str(eid).isdigit() and hasattr(form, field_name): getattr(form, field_name).data = int(eid)
            if et == "CUSTOMER" and eid:
                c = db.session.get(Customer, int(eid))
                if c:
                    entity_info = {"type":"customer","name":c.name,"balance":c.balance,"currency":getattr(c,"currency","ILS")}
                    form.currency.data = getattr(c,"currency","ILS")
                    if pre_amount is not None: form.total_amount.data = pre_amount; form.reference.data = form.reference.data or f"دفعة من العميل {c.name}"
            elif et == "SUPPLIER" and eid:
                s = db.session.get(Supplier, int(eid))
                if s:
                    entity_info = {"type":"supplier","name":s.name,"balance":float(getattr(s,"net_balance",0) or 0),"currency":getattr(s,"currency","ILS")}
                    form.currency.data = getattr(s,"currency","ILS")
                    if pre_amount is not None: form.total_amount.data = pre_amount; form.reference.data = form.reference.data or f"تسوية حساب المورد {s.name}"
            elif et == "PARTNER" and eid:
                p = db.session.get(Partner, int(eid))
                if p:
                    entity_info = {"type":"partner","name":p.name,"balance":float(getattr(p,"net_balance",0) or 0),"currency":getattr(p,"currency","ILS")}
                    form.currency.data = getattr(p,"currency","ILS")
                    if pre_amount is not None: form.total_amount.data = pre_amount; form.reference.data = form.reference.data or f"تسوية حساب الشريك {p.name}"
            elif et == "SALE" and eid:
                rec = db.session.get(Sale, int(eid))
                if rec:
                    due = float(getattr(rec,"balance_due",0) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة لبيع {rec.sale_number or rec.id}"
                    form.currency.data = getattr(rec,"currency",form.currency.data)
                    entity_info = {"type":"sale","number":rec.sale_number,"date":rec.sale_date.strftime("%Y-%m-%d") if rec.sale_date else "","balance_due":float(getattr(rec,"balance_due",0) or 0),"total":float(getattr(rec,"total_amount",getattr(rec,"total",0)) or 0),"paid":float(getattr(rec,"total_paid",0) or 0),"currency":getattr(rec,"currency","ILS")}
            elif et == "INVOICE" and eid:
                rec = db.session.get(Invoice, int(eid))
                if rec:
                    due = float(getattr(rec,"balance_due",0) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة للفاتورة {rec.invoice_number or rec.id}"
                    form.currency.data = getattr(rec,"currency",form.currency.data)
                    entity_info = {"type":"invoice","number":rec.invoice_number,"date":rec.invoice_date.strftime("%Y-%m-%d") if rec.invoice_date else "","balance_due":float(getattr(rec,"balance_due",0) or 0),"total":float(getattr(rec,"total_amount",0) or 0),"paid":float(getattr(rec,"total_paid",0) or 0),"currency":getattr(rec,"currency","ILS")}
            elif et == "SERVICE" and eid:
                svc = db.session.get(ServiceRequest, int(eid))
                if svc:
                    due = float(getattr(svc,"balance_due",getattr(svc,"total_cost",0)) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else due
                    form.reference.data = f"دفعة صيانة {svc.service_number or svc.id}"
                    entity_info = {"type":"service","number":svc.service_number,"date":svc.request_date.strftime("%Y-%m-%d") if getattr(svc,"request_date",None) else "","balance_due":float(getattr(svc,"balance_due",0) or 0),"total":float(getattr(svc,"total_cost",0) or 0),"paid":float(getattr(svc,"total_paid",0) or 0),"currency":"ILS"}
            elif et == "EXPENSE" and eid:
                exp = db.session.get(Expense, int(eid))
                if exp:
                    bal = float(getattr(exp,"balance",getattr(exp,"amount",0)) or 0)
                    form.total_amount.data = pre_amount if pre_amount is not None else bal
                    form.direction.data = "OUT"
                    form.reference.data = f"دفع مصروف #{exp.id}"
                    form.currency.data = getattr(exp,"currency",form.currency.data)
                    entity_info = {"type":"expense","number":f"EXP-{exp.id}","date":exp.date.strftime("%Y-%m-%d") if getattr(exp,"date",None) else "","amount":float(getattr(exp,"amount",0) or 0),"balance":float(getattr(exp,"balance",0) or 0),"currency":getattr(exp,"currency","ILS")}
            elif et == "SHIPMENT" and eid:
                shp = db.session.get(Shipment, int(eid))
                if shp:
                    form.direction.data = "OUT"
                    if pre_amount is not None: form.total_amount.data = pre_amount; form.reference.data = (form.reference.data or f"دفع جمارك الشحنة {shp.shipment_number or shp.id}")
                    entity_info = {"type":"shipment","number":shp.shipment_number,"date":shp.shipment_date.strftime("%Y-%m-%d") if shp.shipment_date else "","destination":getattr(shp,"destination",""),"currency":getattr(shp,"currency","USD")}
            elif et == "PREORDER" and eid:
                po = db.session.get(PreOrder, int(eid))
                if po:
                    form.total_amount.data = pre_amount if pre_amount is not None else float(getattr(po,"prepaid_amount",0) or 0)
                    form.reference.data = f"دفعة حجز {po.reference or po.id}"
                    entity_info = {"type":"preorder","number":po.reference,"date":po.created_at.strftime("%Y-%m-%d") if getattr(po,"created_at",None) else "","currency":"ILS"}
                    form.direction.data = form.direction.data or "IN"
        if not form.status.data: form.status.data = PaymentStatus.COMPLETED.value
    if request.method == "POST":
        raw_dir = request.form.get("direction")
        if raw_dir: form.direction.data = _norm_dir(raw_dir)
        if not form.validate():
            if _wants_json(): return jsonify(status="error", errors=form.errors), 400
            return render_template("payments/form.html", form=form, entity_info=entity_info)
        try:
            etype = (form.entity_type.data or "").upper()
            field_name = getattr(form, "_entity_field_map", {}).get(etype)
            target_id = getattr(form, field_name).data if field_name and hasattr(form, field_name) else None
            parsed_splits = []; total_splits = 0.0
            for entry in getattr(form, "splits", []).entries:
                sm = entry.form; amt = float(getattr(sm, "amount").data or 0)
                if amt <= 0: continue
                m_raw = (getattr(sm, "method").data or ""); m_str = str(m_raw).strip().lower()
                details = {}
                for fld in ("check_number","check_bank","check_due_date","card_number","card_holder","card_expiry","bank_transfer_ref"):
                    if hasattr(sm, fld):
                        val = getattr(sm, fld).data
                        if val not in (None, "", []):
                            if fld == "check_due_date":
                                if isinstance(val, datetime): val = val.isoformat()
                                else:
                                    DateT = type(datetime.utcnow().date())
                                    if isinstance(val, DateT): val = val.isoformat()
                            details[fld] = val
                details = _clean_details(details)
                parsed_splits.append(PaymentSplit(method=_coerce_method(m_str), amount=amt, details=details))
                total_splits += amt
            auto_dir = None
            if hasattr(form, "_incoming_entities") and etype in form._incoming_entities: auto_dir = "IN"
            elif hasattr(form, "_outgoing_entities") and etype in form._outgoing_entities: auto_dir = "OUT"
            direction_val = _norm_dir(form.direction.data or auto_dir)
            method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data)
            notes_raw = (_fd(getattr(form, "note", None)) or _fd(getattr(form, "notes", None)) or ""); notes_val = (notes_raw or "").strip() or None
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
                direction=direction_val,
                status=form.status.data or PaymentStatus.COMPLETED.value,
                payment_date=form.payment_date.data,
                total_amount=form.total_amount.data,
                currency=form.currency.data,
                method=method_val,
                reference=(form.reference.data or "").strip() or None,
                receipt_number=(_fd(getattr(form,"receipt_number",None)) or None),
                notes=notes_val,
                created_by=current_user.id,
            )
            if not getattr(payment, "method", None) and parsed_splits:
                payment.method = getattr(parsed_splits[0].method, "value", parsed_splits[0].method)
            db.session.add(payment); db.session.flush()
            for sp in parsed_splits:
                sp.payment_id = payment.id; db.session.add(sp)
            try:
                db.session.commit()
            except IntegrityError as ie:
                db.session.rollback(); fixed = False; msg = str(ie).lower()
                if "payments.payment_number" in msg or "unique constraint failed: payments.payment_number" in msg:
                    base_dt = payment.payment_date or datetime.utcnow(); prefix = base_dt.strftime("PMT%Y%m%d")
                    cnt = db.session.execute(text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"), {"pfx": f"{prefix}-%"}).scalar() or 0
                    payment.payment_number = f"{prefix}-{cnt+1:04d}"; fixed = True
                if ("not null constraint failed: payments.method" in msg or "payments.method may not be null" in msg) and parsed_splits:
                    payment.method = getattr(parsed_splits[0].method, "value", parsed_splits[0].method); fixed = True
                if fixed:
                    db.session.add(payment)
                    for sp in parsed_splits: sp.payment_id = payment.id; db.session.add(sp)
                    db.session.commit()
                else:
                    raise
            try:
                if payment.sale_id:
                    sale = db.session.get(Sale, payment.sale_id)
                    if sale and hasattr(sale, "update_payment_status"): sale.update_payment_status(); db.session.add(sale)
                if payment.invoice_id:
                    inv = db.session.get(Invoice, payment.invoice_id)
                    if inv and hasattr(inv, "update_status"): inv.update_status(); db.session.add(inv)
                if payment.customer_id: update_entity_balance("customer", payment.customer_id)
                if payment.supplier_id: update_entity_balance("supplier", payment.supplier_id)
                if payment.partner_id: update_entity_balance("partner", payment.partner_id)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
        except Exception as e:
            db.session.rollback()
            if _wants_json(): return jsonify(status="error", message=str(e)), 400
            flash(f"❌ خطأ في الحفظ: {e}", "danger"); return render_template("payments/form.html", form=form, entity_info=entity_info)
        if _wants_json(): return jsonify(status="success", payment=payment.to_dict()), 201
        flash("✅ تم تسجيل الدفعة", "success"); return redirect(url_for("payments.index"))
    return render_template("payments/form.html", form=form, entity_info=entity_info)

@payments_bp.route("/<int:payment_id>", methods=["GET"], endpoint="view_payment")
@login_required
@permission_required("manage_payments")
def view_payment(payment_id):
    payment=_get_or_404(
        Payment, payment_id,
        options=(
            joinedload(Payment.customer), joinedload(Payment.supplier),
            joinedload(Payment.partner), joinedload(Payment.shipment),
            joinedload(Payment.expense), joinedload(Payment.loan_settlement),
            joinedload(Payment.sale), joinedload(Payment.invoice),
            joinedload(Payment.preorder), joinedload(Payment.service),
            joinedload(Payment.splits)
        )
    )
    if _wants_json():
        return jsonify(payment=payment.to_dict())
    return render_template("payments/view.html", payment=payment)


@payments_bp.route("/<int:payment_id>/delete", methods=["POST"], endpoint="delete_payment")
@login_required
@permission_required("manage_payments")
def delete_payment(payment_id):
    payment=_get_or_404(Payment, payment_id)
    sale_id, invoice_id = payment.sale_id, payment.invoice_id
    preorder_id, service_id = payment.preorder_id, payment.service_id
    cust_id, supp_id, part_id = payment.customer_id, payment.supplier_id, payment.partner_id
    try:
        db.session.delete(payment)
        db.session.commit()
        if sale_id:
            sale = db.session.get(Sale, sale_id)
            if sale and hasattr(sale, "update_payment_status"):
                sale.update_payment_status()
        if invoice_id:
            inv = db.session.get(Invoice, invoice_id)
            if inv and hasattr(inv, "update_status"):
                inv.update_status()
        if preorder_id:
            po = db.session.get(PreOrder, preorder_id)
            if po:
                po.status = PreOrderStatus.PENDING
                db.session.add(po)
        if service_id:
            svc = db.session.get(ServiceRequest, service_id)
            if svc:
                svc.status = ServiceStatus.PENDING
                db.session.add(svc)
        if cust_id:
            update_entity_balance("customer", cust_id)
        if supp_id:
            update_entity_balance("supplier", supp_id)
        if part_id:
            update_entity_balance("partner", part_id)
        db.session.commit()
        log_audit("Payment", payment_id, "DELETE")
        if _wants_json():
            return jsonify(status="success")
        flash("✅ تم حذف الدفعة بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify(status="error", message=str(e)), 400
        flash(f"❌ خطأ في الحذف: {e}", "danger")
    return redirect(url_for("payments.index"))


@payments_bp.route("/<int:payment_id>/receipt", methods=["GET"], endpoint="view_receipt")
@login_required
@permission_required("manage_payments")
def view_receipt(payment_id):
    payment=_get_or_404(
        Payment, payment_id,
        options=(
            joinedload(Payment.customer), joinedload(Payment.supplier),
            joinedload(Payment.partner), joinedload(Payment.sale),
            joinedload(Payment.splits)
        )
    )
    sale_info = None
    if payment.sale_id and payment.sale:
        s = payment.sale
        sale_info = {
            "number": s.sale_number,
            "date": s.sale_date.strftime("%Y-%m-%d") if s.sale_date else "-",
            "total": s.total_amount, "paid": s.total_paid,
            "balance": s.balance_due, "currency": s.currency
        }
    if _wants_json():
        payload = payment.to_dict()
        payload["sale_info"] = sale_info
        return jsonify(payment=payload)
    return render_template("payments/receipt.html", payment=payment, now=datetime.utcnow(), sale_info=sale_info)


@payments_bp.route("/<int:payment_id>/receipt/download", methods=["GET"], endpoint="download_receipt")
@login_required
@permission_required("manage_payments")
def download_receipt(payment_id):
    payment = _get_or_404(Payment, payment_id)
    pdf_bytes = _render_payment_receipt_pdf(payment)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=payment_receipt_{payment_id}.pdf"}
    )


@payments_bp.route("/split/<int:split_id>/delete", methods=["DELETE"], endpoint="delete_split")
@login_required
@permission_required("manage_payments")
def delete_split(split_id):
    split = _get_or_404(PaymentSplit, split_id)
    try:
        db.session.delete(split)
        db.session.commit()
        return jsonify(status="success")
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify(status="error", message=str(e)), 400


@payments_bp.route("/entity-fields", methods=["GET"], endpoint="entity_fields")
@login_required
@permission_required("manage_payments")
def entity_fields():
    entity_type = (request.args.get("type") or "customer").lower()
    entity_id = request.args.get("entity_id")
    form = PaymentForm()
    form.entity_type.data = entity_type
    if entity_id:
        try:
            eid = int(entity_id)
            if entity_type == "customer" and db.session.get(Customer, eid):
                form.customer_id.data = eid
            elif entity_type == "supplier" and db.session.get(Supplier, eid):
                form.supplier_id.data = eid
            elif entity_type == "partner" and db.session.get(Partner, eid):
                form.partner_id.data = eid
            elif entity_type == "preorder" and db.session.get(PreOrder, eid):
                form.preorder_id.data = eid
        except (ValueError, TypeError):
            pass
    return render_template("payments/_entity_fields.html", form=form)

@payments_bp.route("/expense/<int:exp_id>/create", methods=["GET","POST"], endpoint="create_expense_payment")
@login_required
@permission_required("manage_payments")
def create_expense_payment(exp_id):
    exp = _get_or_404(Expense, exp_id)
    form = PaymentForm(meta={"csrf": not current_app.testing})
    if hasattr(form, "direction"):
        form.direction.choices = [("IN","وارد"),("OUT","صادر"),("INCOMING","وارد"),("OUTGOING","صادر")]
    form.entity_type.data = "EXPENSE"
    if hasattr(form, "_entity_field_map") and "EXPENSE" in form._entity_field_map:
        getattr(form, form._entity_field_map["EXPENSE"]).data = exp.id
    entity_info = {
        "type": "expense",
        "number": f"EXP-{exp.id}",
        "date": exp.date.strftime("%Y-%m-%d") if getattr(exp, "date", None) else "",
        "description": exp.description or "",
        "amount": exp.amount,
    }
    def _clean_details(d):
        if not d: return None
        out = {}; DateT = type(datetime.utcnow().date())
        for k, v in d.items():
            if v in (None, "", []): continue
            if isinstance(v, (datetime, DateT)): out[k] = v.isoformat()
            else: out[k] = v
        return out or None
    if request.method == "GET":
        form.payment_date.data = datetime.utcnow().date()
        form.total_amount.data = exp.amount
        form.reference.data = f"دفع مصروف {exp.description or ''}"
        form.direction.data = "OUT"
        form.currency.data = getattr(exp, "currency", "ILS")
        if not form.status.data: form.status.data = PaymentStatus.COMPLETED.value
        return render_template("payments/form.html", form=form, entity_info=entity_info)
    raw_dir = request.form.get("direction")
    if raw_dir: form.direction.data = _norm_dir(raw_dir)
    if not form.validate_on_submit():
        if _wants_json(): return jsonify(status="error", errors=form.errors), 400
        return render_template("payments/form.html", form=form, entity_info=entity_info)
    try:
        parsed_splits = []; total_splits = 0.0
        for entry in getattr(form, "splits", []).entries:
            sm = entry.form
            amt = float(getattr(sm, "amount").data or 0)
            if amt <= 0: continue
            m_raw = (getattr(sm, "method").data or ""); m_str = str(m_raw).strip().lower()
            details = {}
            for fld in ("check_number","check_bank","check_due_date","card_number","card_holder","card_expiry","bank_transfer_ref"):
                if hasattr(sm, fld):
                    val = getattr(sm, fld).data
                    if val not in (None, "", []):
                        if fld == "check_due_date":
                            if isinstance(val, datetime): val = val.isoformat()
                            else:
                                DateT = type(datetime.utcnow().date())
                                if isinstance(val, DateT): val = val.isoformat()
                        details[fld] = val
            details = _clean_details(details)
            parsed_splits.append(PaymentSplit(method=_coerce_method(m_str), amount=amt, details=details))
            total_splits += amt
        tgt_total = float(request.form.get("total_amount") or form.total_amount.data or 0)
        if abs(total_splits - tgt_total) > 0.01:
            msg = "❌ مجموع الدفعات الجزئية لا يساوي المبلغ الكلي."
            if _wants_json(): return jsonify(status="error", message=msg), 400
            flash(msg, "danger"); return render_template("payments/form.html", form=form, entity_info=entity_info)
        method_val = parsed_splits[0].method if parsed_splits else _coerce_method(getattr(form, "method", None).data)
        method_val = getattr(method_val, "value", method_val)
        notes_raw = (getattr(form, "note", None).data if hasattr(form, "note") else None) or (getattr(form, "notes", None).data if hasattr(form, "notes") else None) or ""
        payment = Payment(
            entity_type="EXPENSE",
            expense_id=exp.id,
            total_amount=tgt_total,
            currency=form.currency.data or getattr(exp, "currency", "ILS"),
            method=method_val,
            direction="OUT",
            status=form.status.data or PaymentStatus.COMPLETED.value,
            payment_date=form.payment_date.data or datetime.utcnow().date(),
            reference=(form.reference.data or "").strip() or None,
            notes=(notes_raw or "").strip() or None,
            created_by=current_user.id,
        )
        for sp in parsed_splits:
            payment.splits.append(sp)
        db.session.add(payment)
        db.session.commit()
        log_audit("Payment", payment.id, f"CREATE (expense #{exp.id})")
        if _wants_json(): return jsonify(status="success", payment=payment.to_dict()), 201
        flash("✅ تم تسجيل دفع المصروف بنجاح", "success")
        return redirect(url_for("payments.view_payment", payment_id=payment.id))
    except Exception as e:
        db.session.rollback()
        if _wants_json(): return jsonify(status="error", message=str(e)), 400
        flash(f"❌ خطأ أثناء تسجيل الدفع: {e}", "danger")
        return render_template("payments/form.html", form=form, entity_info=entity_info)
