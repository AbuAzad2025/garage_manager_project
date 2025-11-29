
import csv
import io
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from functools import wraps

from dateutil.relativedelta import relativedelta
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_, case, exists, and_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, load_only, selectinload, sessionmaker

from extensions import db, quick_wal_checkpoint
from forms import CustomerForm, CustomerImportForm, ExportContactsForm
from models import (
    AuditLog,
    Customer,
    Invoice,
    Payment,
    PaymentStatus,
    Product,
    ProductCategory,
    Sale,
    SaleLine,
    SaleReturn,
    ServiceRequest,
    PreOrder,
    OnlinePreOrder,
    Expense,
    ExpenseType,
)
import utils
from utils import archive_record, restore_record
from utils.balance_calculator import build_customer_balance_view
from sqlalchemy import text as sa_text

customers_bp = Blueprint(
    "customers_bp",
    __name__,
    url_prefix="/customers",
    template_folder="templates/customers",
)


def _recalculate_customer_balance(customer_id):
    from utils.customer_balance_updater import update_customer_balance_components

    SessionFactory = sessionmaker(bind=db.engine)
    session = SessionFactory()
    try:
        update_customer_balance_components(customer_id, session)
        session.commit()
    except Exception as e:
        session.rollback()
        current_app.logger.error(f"خطأ في إعادة حساب رصيد العميل {customer_id}: {e}")
    finally:
        session.close()
def _get_or_404(model, ident, *options):
    if options:
        q = db.session.query(model)
        for opt in options:
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

_last_attempts = {}
def rate_limit(max_attempts=5, window=60):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.utcnow().timestamp()
            attempts = [t for t in _last_attempts.get(ip, []) if now - t < window]
            if len(attempts) >= max_attempts:
                abort(429, "محاولات كثيرة جدًا، حاول لاحقًا.")
            attempts.append(now)
            _last_attempts[ip] = attempts
            return f(*args, **kwargs)
        return wrapper
    return decorator

def _serialize_dates(d):
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}

def _is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"

def log_customer_action(cust, action, old_data=None, new_data=None):
    old_json = json.dumps(old_data, ensure_ascii=False, cls=CustomEncoder) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False, cls=CustomEncoder) if new_data else None
    entry = AuditLog(
        model_name="Customer",
        customer_id=cust.id,
        record_id=cust.id,
        user_id=current_user.id if getattr(current_user, "is_authenticated", False) else None,
        action=action,
        old_data=old_json,
        new_data=new_json,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(entry)
    db.session.flush()

@customers_bp.route("/", methods=["GET"], endpoint="list_customers")
@login_required
def list_customers():
    # عرض جميع العملاء بدون أي فلتر افتراضي على is_archived
    q = Customer.query.options(
        selectinload(Customer.payments).load_only(Payment.id, Payment.total_amount, Payment.payment_date, Payment.status, Payment.direction),
        selectinload(Customer.sales).load_only(Sale.id, Sale.sale_number, Sale.sale_date, Sale.total_amount, Sale.status)
    )

    if name := request.args.get("name"):
        q = q.filter(Customer.name.ilike(f"%{name}%"))
    if phone := request.args.get("phone"):
        q = q.filter(Customer.phone.ilike(f"%{phone}%"))
    if category := request.args.get("category"):
        q = q.filter(Customer.category == category)
    if "is_active" in request.args:
        q = q.filter(Customer.is_active == (request.args.get("is_active") == "1"))

    search_term = request.args.get("q", "").strip()
    if search_term:
        like_pattern = f"%{search_term}%"
        filters = [
            Customer.name.ilike(like_pattern),
            Customer.phone.ilike(like_pattern),
            Customer.whatsapp.ilike(like_pattern),
            Customer.email.ilike(like_pattern),
            Customer.address.ilike(like_pattern),
            Customer.category.ilike(like_pattern),
        ]
        if search_term.isdigit():
            filters.append(Customer.id == int(search_term))
        q = q.filter(or_(*filters))

    print_mode = request.args.get("print") == "1"
    scope_param = request.args.get("scope")
    print_scope = scope_param or ("page" if print_mode else "all")
    range_start = request.args.get("range_start", type=int)
    range_end = request.args.get("range_end", type=int)
    target_page = request.args.get("page_number", type=int)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = 10

    sort = request.args.get("sort", "balance")
    order = request.args.get("order", "asc")
    
    if sort == "balance":
        if order == "asc":
            q = q.order_by(Customer.current_balance.asc().nullslast())
        else:
            q = q.order_by(Customer.current_balance.desc().nullslast())
    elif sort == "name":
        if order == "asc":
            q = q.order_by(Customer.name.asc())
        else:
            q = q.order_by(Customer.name.desc())
    elif sort == "created_at":
        if order == "asc":
            q = q.order_by(Customer.created_at.asc())
        else:
            q = q.order_by(Customer.created_at.desc())
    elif sort == "phone":
        if order == "asc":
            q = q.order_by(Customer.phone.asc().nullslast())
        else:
            q = q.order_by(Customer.phone.desc().nullslast())
    elif sort == "category":
        if order == "asc":
            q = q.order_by(Customer.category.asc().nullslast())
        else:
            q = q.order_by(Customer.category.desc().nullslast())
    else:
        q = q.order_by(Customer.current_balance.asc().nullslast())

    if print_scope not in {"all", "range", "page"}: 
        print_scope = "page" if print_mode else "all"

    def _get_balance_value(customer_obj):
        if hasattr(customer_obj, 'current_balance') and customer_obj.current_balance is not None:
            return float(customer_obj.current_balance)
        return float(getattr(customer_obj, "balance", 0) or 0)

    total_filtered = q.count()
    
    if print_mode:
        if print_scope == "all":
            customers_list = q.limit(10000).all()
            pagination = None
        elif print_scope == "range":
            start_index = max(1, range_start or 1)
            end_index = range_end or total_filtered or start_index
            if end_index < start_index:
                end_index = start_index
            limit_count = end_index - start_index + 1
            customers_list = q.offset(start_index - 1).limit(limit_count).all()
            pagination = None
        else:
            page_number = max(1, target_page or page or 1)
            start_idx = (page_number - 1) * per_page
            customers_list = q.offset(start_idx).limit(per_page).all()
            pagination = None
    else:
        pag = q.paginate(page=page, per_page=per_page, error_out=False)
        customers_list = list(pag.items)
        pagination = pag

    mismatches = []
    for customer in customers_list:
        if hasattr(customer, 'calculated_balance'):
            continue
        balance_val = _get_balance_value(customer)
        try:
            setattr(customer, "calculated_balance", balance_val)
        except Exception:
            pass
        
        stored_balance = float(customer.current_balance or 0)
        if abs(stored_balance - balance_val) > 0.01:
            mismatches.append(customer.id)
    
    if mismatches:
        try:
            from utils.customer_balance_updater import update_customer_balance_components
            from sqlalchemy.orm import sessionmaker
            SessionFactory = sessionmaker(bind=db.engine)
            session = SessionFactory()
            try:
                for customer_id in mismatches[:10]:
                    try:
                        update_customer_balance_components(customer_id, session)
                    except Exception:
                        pass
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()
        except Exception:
            pass

    args = request.args.to_dict(flat=True)
    for key in ["page", "print", "scope", "range_start", "range_end", "page_number", "ajax"]:
        args.pop(key, None)

    total_pages = math.ceil(total_filtered / per_page) if per_page else 1

    summary_query = db.session.query(
        func.count(Customer.id).label('total_customers'),
        func.coalesce(func.sum(Customer.current_balance), 0).label('total_balance'),
        func.coalesce(func.sum(Customer.total_invoiced), 0).label('total_sales'),
        func.coalesce(func.sum(Customer.total_paid), 0).label('total_payments'),
        func.sum(case((Customer.current_balance < 0, 1), else_=0)).label('customers_with_debt'),
        func.sum(case((Customer.current_balance > 0, 1), else_=0)).label('customers_with_credit')
    ).filter(Customer.is_archived.is_(False))

    summary_result = summary_query.first()
    
    total_balance = float(summary_result.total_balance or 0)
    total_sales = float(summary_result.total_sales or 0)
    total_payments = float(summary_result.total_payments or 0)
    customers_with_debt = int(summary_result.customers_with_debt or 0)
    customers_with_credit = int(summary_result.customers_with_credit or 0)
    total_customers_count = int(summary_result.total_customers or 0)

    summary = {
        'total_customers': total_customers_count,
        'total_balance': total_balance,
        'total_sales': total_sales,
        'total_payments': total_payments,
        'customers_with_debt': customers_with_debt,
        'customers_with_credit': customers_with_credit,
        'average_balance': (total_balance / total_customers_count) if total_customers_count > 0 else 0
    }

    if not customers_list and not print_mode:
        flash("⚠️ لا توجد بيانات لعرضها", "info")

    if print_mode:
        if print_scope == "range":
            row_offset = start_index - 1
        elif print_scope == "page":
            row_offset = (page_number - 1) * per_page
        else:
            row_offset = 0
    else:
        row_offset = ((pagination.page - 1) * pagination.per_page) if pagination else 0

    context = {
        "customers": customers_list,
        "pagination": pagination,
        "args": args,
        "summary": summary,
        "print_mode": print_mode,
        "print_scope": print_scope,
        "range_start": range_start or 1,
        "range_end": range_end or (total_filtered if total_filtered else 1),
        "target_page": target_page or page,
        "total_filtered": total_filtered,
        "total_pages": total_pages if total_pages else 1,
        "per_page": per_page,
        "show_actions": not print_mode,
        "row_offset": row_offset,
        "generated_at": datetime.utcnow(),
        "pdf_export": False,
    }

    if _is_ajax() and not print_mode:
        current_sort = request.args.get("sort", "balance")
        current_order = request.args.get("order", "asc")
        table_html = render_template(
            "customers/_table.html",
            customers=customers_list,
            show_actions=True,
            row_offset=row_offset,
            print_mode=False,
            table_id="customersTable",
            current_sort=current_sort,
            current_order=current_order,
        )
        pagination_html = ""
        if pagination:
            pagination_html = render_template_string(
                """
{% if pagination %}
<nav class="mt-3 no-print">
  <ul class="pagination justify-content-center mb-0">
    {% if pagination.has_prev %}
      <li class="page-item">
        <a class="page-link" href="{{ url_for('customers_bp.list_customers', page=pagination.prev_num, **args) }}">السابق</a>
      </li>
    {% endif %}
    {% for p in pagination.iter_pages() %}
      {% if p %}
        <li class="page-item {% if p == pagination.page %}active{% endif %}">
          <a class="page-link" href="{{ url_for('customers_bp.list_customers', page=p, **args) }}">{{ p }}</a>
        </li>
      {% else %}
        <li class="page-item disabled"><span class="page-link">…</span></li>
      {% endif %}
    {% endfor %}
    {% if pagination.has_next %}
      <li class="page-item">
        <a class="page-link" href="{{ url_for('customers_bp.list_customers', page=pagination.next_num, **args) }}">التالي</a>
      </li>
    {% endif %}
  </ul>
</nav>
{% endif %}
                """,
                pagination=pagination,
                args=args,
            )
        return jsonify(
            {
                "table_html": table_html,
                "pagination_html": pagination_html,
                "total_filtered": total_filtered,
                "page": pagination.page if pagination else 1,
                "pages": pagination.pages if pagination else 1,
            }
        )

    if print_mode:
        context["pdf_export"] = True
        try:
            from weasyprint import HTML

            html_output = render_template("customers/list.html", **context)
            pdf_bytes = HTML(string=html_output, base_url=request.url_root).write_pdf()
            filename = f"customers_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf"
            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )
        except Exception as exc:
            current_app.logger.error("customers_print_pdf_error: %s", exc)
            context["pdf_export"] = False

    quick_wal_checkpoint()
    
    return render_template("customers/list.html", **context)


@customers_bp.route("/<int:customer_id>", methods=["GET"], endpoint="customer_detail")
@login_required
def customer_detail(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    balance_breakdown = None
    rights_items = []
    obligations_items = []
    try:
        balance_breakdown = build_customer_balance_view(customer_id, db.session)
    except Exception as exc:
        current_app.logger.warning("customer_balance_breakdown_page_failed: %s", exc)
    if balance_breakdown and balance_breakdown.get("success"):
        rights_items = (balance_breakdown.get("rights") or {}).get("items") or []
        obligations_items = (balance_breakdown.get("obligations") or {}).get("items") or []
    return render_template(
        "customers/detail.html",
        customer=customer,
        balance_breakdown=balance_breakdown,
        balance_rights_items=rights_items,
        balance_obligations_items=obligations_items,
    )


@customers_bp.route("/<int:customer_id>/analytics", methods=["GET"], endpoint="customer_analytics")
@login_required
def customer_analytics(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)

    from utils import D, q0
    from models import convert_amount

    def _f2(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def _line_total(qty, unit_price, disc_pct, tax_pct):
        q = int(qty or 0)
        u = _f2(unit_price)
        d = _f2(disc_pct)
        t = _f2(tax_pct)
        gross = q * u
        if d < 0:
            d = 0.0
        if d > gross:
            d = gross
        disc = d
        taxable = gross - disc
        tax = taxable * (t / 100.0)
        taxable_d = q0(taxable)
        tax_d = q0(tax)
        total_d = q0(taxable_d + tax_d)
        return taxable_d, tax_d, total_d

    def service_grand_total(svc):
        from decimal import Decimal
        grand = Decimal("0")
        for p in (getattr(svc, "parts", None) or []):
            _, _, g = _line_total(p.quantity, p.unit_price, p.discount, p.tax_rate)
            grand += g
        for tsk in (getattr(svc, "tasks", None) or []):
            _, _, g = _line_total(tsk.quantity or 1, tsk.unit_price, tsk.discount, tsk.tax_rate)
            grand += g
        if grand > 0:
            return int(q0(grand))
        return int(q0(getattr(svc, "total_amount", getattr(svc, "total_cost", 0)) or 0))

    invoices = Invoice.query.filter_by(customer_id=customer_id).options(
        load_only(Invoice.id, Invoice.invoice_date, Invoice.total_amount, Invoice.currency, Invoice.cancelled_at)
    ).all()
    sales = Sale.query.filter_by(customer_id=customer_id).options(
        load_only(Sale.id, Sale.sale_date, Sale.total_amount, Sale.currency, Sale.status)
    ).all()
    services = ServiceRequest.query.filter_by(customer_id=customer_id).options(
        load_only(ServiceRequest.id, ServiceRequest.received_at, ServiceRequest.total_amount, ServiceRequest.currency)
    ).all()

    total_invoices = sum((D(inv.total_amount or 0)) for inv in invoices)
    total_sales = sum((D(s.total_amount or 0)) for s in sales)
    total_services = sum((D(service_grand_total(srv))) for srv in services)

    total_purchases = total_invoices + total_sales + total_services
    docs_count = len(invoices) + len(sales) + len(services)
    avg_purchase = (total_purchases / docs_count) if docs_count else D(0)

    payments_direct = Payment.query.filter_by(
        customer_id=customer_id,
        status=PaymentStatus.COMPLETED.value
    ).options(
        load_only(Payment.id, Payment.total_amount, Payment.currency, Payment.payment_date)
    ).all()
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(
        Sale.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).options(
        load_only(Payment.id, Payment.total_amount, Payment.currency, Payment.payment_date)
    ).all()
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(
        Invoice.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).options(
        load_only(Payment.id, Payment.total_amount, Payment.currency, Payment.payment_date)
    ).all()
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(
        ServiceRequest.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).options(
        load_only(Payment.id, Payment.total_amount, Payment.currency, Payment.payment_date)
    ).all()
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(
        PreOrder.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).options(
        load_only(Payment.id, Payment.total_amount, Payment.currency, Payment.payment_date)
    ).all()

    seen = set()
    all_payments = []
    for p in payments_direct + payments_from_sales + payments_from_invoices + payments_from_services + payments_from_preorders:
        if p.id in seen:
            continue
        seen.add(p.id)
        all_payments.append(p)

    total_payments = sum((D(p.total_amount or 0)) for p in all_payments)

    from dateutil.relativedelta import relativedelta
    today = datetime.utcnow()
    months = [(today - relativedelta(months=i)).strftime("%Y-%m") for i in reversed(range(6))]

    pm = {m: D(0) for m in months}
    for inv in invoices:
        if inv.invoice_date:
            m = inv.invoice_date.strftime("%Y-%m")
            if m in pm:
                pm[m] += (D(inv.total_amount or 0))
    for s in sales:
        d = getattr(s, "sale_date", None) or getattr(s, "created_at", None)
        if d:
            m = d.strftime("%Y-%m")
            if m in pm:
                pm[m] += (D(s.total_amount or 0))
    for srv in services:
        d = getattr(srv, "completed_at", None) or getattr(srv, "created_at", None)
        if d:
            m = d.strftime("%Y-%m")
            if m in pm:
                pm[m] += D(service_grand_total(srv))
    purchases_months = [{"month": m, "total": float(pm[m])} for m in months]

    paym = {m: D(0) for m in months}
    for p in all_payments:
        d = getattr(p, "payment_date", None) or getattr(p, "created_at", None)
        if d:
            m = d.strftime("%Y-%m")
            if m in paym:
                paym[m] += (D(p.total_amount or 0))
    payments_months = [{"month": m, "total": float(paym[m])} for m in months]

    return render_template(
        "customers/analytics.html",
        customer=customer,
        total_purchases=total_purchases,
        total_payments=total_payments,
        avg_purchase=avg_purchase,
        purchase_categories=[
            {
                "name": name,
                "count": count,
                "total": total_ils,
                "percentage": (float(total_ils) / float(total_purchases) * 100.0) if total_purchases else 0.0,
            }
            for name, count, total_ils in [
                (
                    cat.name,
                    len(lines_in_cat),
                    float(sum(
                        (lambda line: (
                            Decimal(str(line.quantity or 0)) * Decimal(str(line.unit_price or 0))
                            if line.sale.currency == "ILS"
                            else (
                                convert_amount(
                                    Decimal(str(line.quantity or 0)) * Decimal(str(line.unit_price or 0)),
                                    line.sale.currency, "ILS", line.sale.sale_date
                                ) if line.sale.currency else Decimal('0.00')
                            )
                        ))(line)
                        for line in lines_in_cat
                    ))
                )
                for cat in db.session.query(ProductCategory).all()
                for lines_in_cat in [
                    [
                        line for line in db.session.query(SaleLine).join(Sale).join(Product).filter(
                            Sale.customer_id == customer_id,
                            Product.category_id == cat.id
                        ).all()
                    ]
                ]
                if len(lines_in_cat) > 0
            ]
        ],
        purchases_months=purchases_months,
        payments_months=payments_months,
    )

@customers_bp.route("/create", methods=["GET"], endpoint="create_form")
@login_required
def create_form():
    form = CustomerForm()
    for k in ("name", "phone", "email", "address", "whatsapp", "category", "notes"):
        v = request.args.get(k)
        if v:
            getattr(form, k).data = v
    return_to = request.args.get("return_to") or None
    return render_template("customers/new.html", form=form, return_to=return_to)

@customers_bp.route("/create", methods=["POST"], endpoint="create_customer")
@login_required
def create_customer():
    form = CustomerForm()
    is_ajax = _is_ajax()
    try:
        hdr = {
            "accept": request.headers.get("Accept"),
            "xreq": request.headers.get("X-Requested-With"),
            "ctype": request.headers.get("Content-Type"),
        }
        snap = {
            "name": (request.form.get("name") or "")[:120],
            "phone": (request.form.get("phone") or "")[:50],
            "email": (request.form.get("email") or "")[:120],
            "return_to": (request.form.get("return_to") or "")[:200],
        }
        current_app.logger.info(f"[customers.create] start is_ajax={is_ajax} hdr={hdr} snap={snap}")
    except Exception:
        pass
    if not form.validate_on_submit():
        errs = {k: v for k, v in form.errors.items()}
        try:
            current_app.logger.info(f"[customers.create] validate_failed is_ajax={is_ajax} err_keys={list(errs.keys())}")
        except Exception:
            pass
        if is_ajax:
            return jsonify({"ok": False, "errors": errs, "message": "تحقق من الحقول"}), 400
        if errs:
            msgs = "; ".join(f"{k}: {', '.join(v)}" for k, v in errs.items())
            flash(f"تحقق من الحقول: {msgs}", "warning")
        # إبقاء المستخدم على نفس الصفحة مع عرض الأخطاء دون كود خطأ HTTP
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to"))
    # فحص تكرار الهاتف مسبقًا لتجنّب خطأ قاعدة البيانات
    try:
        import re
        phone_in = (form.phone.data or "").strip()
        s = phone_in
        s = "+" + re.sub(r"\D", "", s[1:]) if s.startswith("+") else re.sub(r"\D", "", s)
        exists_obj = db.session.query(Customer.id).filter(Customer.phone == s).first()
        if exists_obj:
            dup_errs = {"phone": ["هذا الهاتف مستخدم مسبقًا"]}
            if is_ajax:
                return jsonify({"ok": False, "message": "بريد أو هاتف مكرر", "errors": dup_errs, "existing_id": exists_obj.id}), 409
            for k, v in dup_errs.items():
                form.errors.setdefault(k, []).extend(v)
            flash("هذا الهاتف مستخدم مسبقًا", "danger")
            return render_template("customers/new.html", form=form, return_to=request.form.get("return_to"))
    except Exception:
        pass
    cust = Customer(
        name=form.name.data,
        phone=form.phone.data,
        email=form.email.data or None,
        address=form.address.data,
        whatsapp=form.whatsapp.data or form.phone.data,
        category=form.category.data,
        credit_limit=form.credit_limit.data or 0,
        discount_rate=form.discount_rate.data or 0,
        currency=form.currency.data,
        opening_balance=form.opening_balance.data or 0,
        is_active=form.is_active.data,
        is_online=form.is_online.data,
        notes=form.notes.data,
    )
    if getattr(form, "password", None) and form.password.data:
        cust.set_password(form.password.data)
    db.session.add(cust)
    try:
        db.session.flush()
        log_customer_action(cust, "CREATE", None, cust.to_dict() if hasattr(cust, "to_dict") else form.data)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        msg = "بريد أو هاتف مكرر"
        detail = str(getattr(e, "orig", e))
        field_errs = {}
        if "email" in detail.lower():
            field_errs["email"] = ["هذا البريد مستخدم مسبقًا"]
        if "phone" in detail.lower() or "whatsapp" in detail.lower():
            # البحث عن هوية العميل الموجود لإظهار رابط فتحه على الواجهة
            try:
                existing_obj = db.session.query(Customer.id).filter(Customer.phone == cust.phone).first()
                existing_id = existing_obj.id if existing_obj else None
            except Exception:
                existing_id = None
            field_errs["phone"] = ["هذا الهاتف مستخدم مسبقًا"]
        if is_ajax:
            try:
                current_app.logger.info(f"[customers.create] integrity_error detail={detail}")
            except Exception:
                pass
            payload = {"ok": False, "message": msg, "errors": field_errs}
            if existing_id:
                payload["existing_id"] = existing_id
            return jsonify(payload), 409
        flash(f"{msg} (Unique constraint).", "danger")
        # إبقاء المستخدم على نفس الصفحة مع الحفاظ على الإدخالات
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to"))
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("SQLAlchemyError while creating customer")
        if is_ajax:
            return jsonify({"ok": False, "message": f"خطأ أثناء إضافة العميل: {e}"}), 500
        flash(f"❌ خطأ أثناء إضافة العميل: {e}", "danger")
        # إبقاء المستخدم على نفس الصفحة مع عرض الخطأ بشكل ودي
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to"))
    if is_ajax:
        try:
            current_app.logger.info(f"[customers.create] success id={cust.id}")
        except Exception:
            pass
        return jsonify({"ok": True, "id": cust.id, "text": cust.name}), 201
    flash("تم إنشاء العميل بنجاح", "success")
    return_to = request.form.get("return_to") or request.args.get("return_to")
    if return_to:
        return redirect(return_to)
    return redirect(url_for("customers_bp.list_customers"))

@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"], endpoint="edit_customer")
@login_required
def edit_customer(customer_id):
    cust = db.session.get(Customer, customer_id) or abort(404)
    form = CustomerForm(obj=cust)
    if request.method == "POST":
        if form.validate_on_submit():
            old = cust.to_dict() if hasattr(cust, "to_dict") else None
            if getattr(form, "password", None) and form.password.data:
                cust.set_password(form.password.data)
            cust.name = form.name.data
            cust.phone = form.phone.data
            cust.email = form.email.data or None
            cust.address = form.address.data
            cust.whatsapp = form.whatsapp.data or form.phone.data
            cust.category = form.category.data
            cust.credit_limit = form.credit_limit.data or 0
            cust.discount_rate = form.discount_rate.data or 0
            cust.currency = form.currency.data
            cust.opening_balance = form.opening_balance.data or 0
            cust.is_active = bool(form.is_active.data)
            cust.is_online = bool(form.is_online.data)
            cust.notes = form.notes.data
            
            try:
                log_customer_action(cust, "UPDATE", old, cust.to_dict() if hasattr(cust, "to_dict") else None)
                db.session.commit()
                
                db.session.refresh(cust)
            except IntegrityError:
                db.session.rollback()
                flash("بريد أو هاتف مكرر (Unique constraint).", "danger")
                current_app.logger.exception("IntegrityError while editing customer")
                return render_template("customers/edit.html", form=form, customer=cust), 409
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f"❌ خطأ أثناء تعديل العميل: {e}", "danger")
                current_app.logger.exception("SQLAlchemyError while editing customer")
                return render_template("customers/edit.html", form=form, customer=cust), 500
            flash("تم تعديل بيانات العميل", "success")
            return redirect(url_for("customers_bp.customer_detail", customer_id=customer_id))
        current_app.logger.warning("CustomerForm errors (edit): %s", form.errors)
        if form.errors:
            msgs = "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items())
            flash(f"تحقق من الحقول: {msgs}", "warning")
        return render_template("customers/edit.html", form=form, customer=cust), 400
    return render_template("customers/edit.html", form=form, customer=cust)

@customers_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete_customer(id):
    """حذف عادي - يحذف فقط إذا لا توجد معاملات"""
    customer = db.session.get(Customer, id) or abort(404)
    
    has_invoices = db.session.query(Invoice.id).filter_by(customer_id=id).first() is not None
    has_payments = db.session.query(Payment.id).filter_by(customer_id=id).first() is not None
    has_sales = db.session.query(Sale.id).filter_by(customer_id=id).first() is not None
    has_services = db.session.query(ServiceRequest.id).filter_by(customer_id=id).first() is not None
    has_preorders = db.session.query(PreOrder.id).filter_by(customer_id=id).first() is not None
    has_opening_balance = (customer.opening_balance and float(customer.opening_balance) != 0)
    
    if has_invoices or has_payments or has_sales or has_services or has_preorders or has_opening_balance:
        flash("❌ لا يمكن حذف العميل لأنه مرتبط بمعاملات أو له رصيد افتتاحي.", "danger")
        return redirect(url_for("customers_bp.list_customers"))
    
    try:
        name = customer.name
        db.session.delete(customer)
        db.session.commit()
        flash(f"✅ تم حذف العميل: {name}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء الحذف: {e}", "danger")
    
    return redirect(url_for("customers_bp.list_customers"))


@customers_bp.route("/import", methods=["GET", "POST"], endpoint="import_customers")
@login_required
def import_customers():
    form = CustomerImportForm()
    if request.method == "GET" or not form.validate_on_submit():
        return render_template("customers/import.html", form=form)
    file_data = form.csv_file.data.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(file_data))
    count, errors = 0, []
    for i, row in enumerate(reader, 1):
        try:
            name = (row.get("name") or "").strip()
            phone = (row.get("phone") or "").strip()
            email = (row.get("email") or "").strip()
            if not name or not phone or not email:
                raise ValueError("حقول مطلوبة مفقودة: name / phone / email")
            if len(phone) > 20:
                raise ValueError("الهاتف يجب ألا يتجاوز 20 خانة")
            whatsapp = (row.get("whatsapp") or "").strip()
            if len(whatsapp) > 20:
                raise ValueError("واتساب يجب ألا يتجاوز 20 خانة")
            address = (row.get("address") or "").strip()
            if len(address) > 200:
                raise ValueError("العنوان يجب ألا يتجاوز 200 خانة")
            notes = (row.get("notes") or "").strip()
            if len(notes) > 500:
                raise ValueError("الملاحظات يجب ألا تتجاوز 500 خانة")
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                raise ValueError("صيغة البريد الإلكتروني غير صحيحة")
            category = (row.get("category") or "عادي").strip()
            if category not in ("عادي", "فضي", "ذهبي", "مميز"):
                category = "عادي"
            credit_limit_raw = (row.get("credit_limit") or "").strip()
            discount_rate_raw = (row.get("discount_rate") or "").strip()
            credit_limit = float(credit_limit_raw) if credit_limit_raw else 0.0
            if credit_limit < 0:
                raise ValueError("حد الائتمان يجب أن يكون ≥ 0")
            discount_rate = float(discount_rate_raw) if discount_rate_raw else 0.0
            if not (0.0 <= discount_rate <= 100.0):
                raise ValueError("معدل الخصم يجب أن يكون بين 0 و100")
            if Customer.query.filter(or_(Customer.phone == phone, Customer.email == email)).first():
                raise ValueError("هاتف أو بريد مستخدم مسبقًا")
            is_active = str(row.get("is_active", "True")).strip().lower() in ("true", "1", "yes", "y", "on")
            c = Customer(
                name=name,
                phone=phone,
                email=email,
                address=address,
                whatsapp=whatsapp,
                category=category,
                credit_limit=credit_limit,
                discount_rate=discount_rate,
                is_active=is_active,
                notes=notes,
            )
            if row.get("password"):
                c.set_password(row["password"])
            with db.session.begin_nested():
                db.session.add(c)
                db.session.flush()
                log_customer_action(c, "IMPORT", None, row)
                count += 1
        except IntegrityError:
            db.session.rollback()
            errors.append(f"سطر {i}: قيمة مكررة (Unique).")
        except Exception as e:
            db.session.rollback()
            errors.append(f"سطر {i}: {e}")
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        errors.append(f"فشل حفظ الدفعة: {e}")
    flash(f"تم استيراد {count} عميل", "success")
    if errors:
        flash("; ".join(errors), "warning")
    return redirect(url_for("customers_bp.list_customers"))

@customers_bp.route("/<int:customer_id>/send_whatsapp", methods=["GET"], endpoint="customer_whatsapp")
@login_required
@rate_limit(10, 60)
def customer_whatsapp(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    if not c.whatsapp:
        flash("لا يوجد رقم واتساب للعميل", "warning")
        return redirect(url_for("customers_bp.customer_detail", customer_id=customer_id))
    ok, info = utils.send_whatsapp_message(c.whatsapp, f"رصيدك الحالي: {getattr(c, 'balance', 0):,.2f}")
    if ok:
        flash("تم إرسال رسالة واتساب", "success")
    else:
        flash(f"خطأ أثناء إرسال واتساب: {info}", "danger")
    return redirect(url_for("customers_bp.customer_detail", customer_id=customer_id))

@customers_bp.route("/<int:customer_id>/export_vcf", methods=["GET"], endpoint="export_customer_vcf")
@login_required
def export_customer_vcf(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", (c.name or "contact")).strip("_") or "contact"
    vcf = "BEGIN:VCARD\r\nVERSION:3.0\r\n" f"FN:{c.name}\r\n" f"TEL:{c.phone or ''}\r\n" f"EMAIL:{c.email or ''}\r\n" "END:VCARD\r\n"
    return Response(vcf, mimetype="text/vcard; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={safe_name}.vcf"})

@customers_bp.route("/<int:customer_id>/account_statement", methods=["GET"], endpoint="account_statement")
@login_required
def account_statement(customer_id):
    from models import Check, CheckStatus
    
    c = db.session.get(Customer, customer_id) or abort(404)
    db.session.refresh(c)
    
    from datetime import datetime, timedelta
    start_date_arg = request.args.get("start_date")
    end_date_arg = request.args.get("end_date")
    try:
        start_date = datetime.strptime(start_date_arg, "%Y-%m-%d") if start_date_arg else (datetime.now() - timedelta(days=180))
    except Exception:
        start_date = datetime.now() - timedelta(days=180)
    try:
        end_date = datetime.strptime(end_date_arg, "%Y-%m-%d") if end_date_arg else datetime.now()
    except Exception:
        end_date = datetime.now()

    try:
        idx_sql = [
            "CREATE INDEX IF NOT EXISTS idx_payments_customer_date ON payments (customer_id, payment_date)",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status)",
            "CREATE INDEX IF NOT EXISTS idx_sales_customer_date ON sales (customer_id, sale_date)",
            "CREATE INDEX IF NOT EXISTS idx_invoices_customer_date ON invoices (customer_id, invoice_date)",
            "CREATE INDEX IF NOT EXISTS idx_sale_returns_customer ON sale_returns (customer_id)",
            "CREATE INDEX IF NOT EXISTS idx_services_customer_date ON service_requests (customer_id, completed_at)",
            "CREATE INDEX IF NOT EXISTS idx_expenses_customer_date ON expenses (customer_id, date)",
            "CREATE INDEX IF NOT EXISTS idx_checks_payment ON checks (payment_id)",
            "CREATE INDEX IF NOT EXISTS idx_checks_customer_date ON checks (customer_id, check_date)",
            "CREATE INDEX IF NOT EXISTS idx_checks_status ON checks (status)"
        ]
        for sql in idx_sql:
            try:
                db.session.execute(sa_text(sql))
            except Exception:
                pass
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    from utils import D, q0

    def _f2(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def _line_total(qty, unit_price, disc_pct, tax_pct):
        q = int(qty or 0)
        u = _f2(unit_price)
        d = _f2(disc_pct)
        t = _f2(tax_pct)
        gross = q * u
        if d < 0:
            d = 0.0
        if d > gross:
            d = gross
        disc = d
        taxable = gross - disc
        tax = taxable * (t / 100.0)
        taxable_d = q0(taxable)
        tax_d = q0(tax)
        total_d = q0(taxable_d + tax_d)
        return taxable_d, tax_d, total_d

    def service_grand_total(svc):
        grand = Decimal("0")
        for p in (getattr(svc, "parts", None) or []):
            _, _, g = _line_total(p.quantity, p.unit_price, p.discount, p.tax_rate)
            grand += g
        for tsk in (getattr(svc, "tasks", None) or []):
            _, _, g = _line_total(tsk.quantity or 1, tsk.unit_price, tsk.discount, tsk.tax_rate)
            grand += g
        if grand > 0:
            return int(q0(grand))
        return int(q0(getattr(svc, "total_amount", getattr(svc, "total_cost", 0)) or 0))

    entries = []

    invoices = (
        Invoice.query
        .filter(Invoice.customer_id == customer_id)
        .filter(Invoice.invoice_date >= start_date)
        .filter(Invoice.invoice_date <= end_date)
        .order_by(Invoice.invoice_date, Invoice.id)
        .all()
    )
    def generate_statement(entry_type, obj):
        """توليد نص البيان حسب نوع العملية"""
        if entry_type == "INVOICE":
            notes = getattr(obj, 'notes', '') or ''
            items_count = len(getattr(obj, 'items', []))
            return f"فاتورة بيع - {items_count} صنف - {notes[:50]}" if notes else f"فاتورة بيع - {items_count} صنف"
        
        elif entry_type == "SALE":
            notes = getattr(obj, 'notes', '') or ''
            items = getattr(obj, 'lines', [])
            if items and len(items) > 0:
                first_item = items[0]
                product_name = getattr(getattr(first_item, 'product', None), 'name', 'منتج')
                if len(items) > 1:
                    return f"بيع {product_name} و {len(items)-1} منتج آخر"
                return f"بيع {product_name}"
            return f"عملية بيع - {notes[:50]}" if notes else "عملية بيع"
        
        elif entry_type == "SERVICE":
            vehicle = getattr(obj, 'vehicle_model', '') or ''
            plate = getattr(obj, 'vehicle_plate', '') or ''
            desc = getattr(obj, 'description', '') or ''
            if vehicle or plate:
                return f"صيانة {vehicle} {plate} - {desc[:30]}" if desc else f"صيانة {vehicle} {plate}"
            return f"خدمة صيانة - {desc[:50]}" if desc else "خدمة صيانة"
        
        elif entry_type == "PREORDER":
            product = getattr(obj, 'product', None)
            product_name = getattr(product, 'name', '') if product else ''
            qty = getattr(obj, 'quantity', 0)
            notes = getattr(obj, 'notes', '') or ''
            if product_name:
                return f"حجز مسبق: {product_name} (كمية: {qty})"
            return f"حجز مسبق - {notes[:50]}" if notes else "حجز مسبق"
        
        elif entry_type == "SALE_RETURN":
            sale_label = f"بيع #{obj.sale_id}" if getattr(obj, 'sale_id', None) else ''
            reason = getattr(obj, 'reason', '') or getattr(obj, 'notes', '') or ''
            if sale_label and reason:
                return f"مرتجع بيع {sale_label} - {reason[:50]}"
            if sale_label:
                return f"مرتجع بيع {sale_label}"
            if reason:
                return f"مرتجع بيع - {reason[:50]}"
            return "مرتجع بيع"
        
        return ""
    
    for inv in invoices:
        entries.append({
            "date": inv.invoice_date or inv.created_at,
            "type": "INVOICE",
            "ref": inv.invoice_number or f"INV-{inv.id}",
            "statement": generate_statement("INVOICE", inv),
            "debit": D(inv.total_amount or 0),  # الفاتورة = عليه (مدين)
            "credit": D(0),
            "notes": getattr(inv, 'notes', '') or '',
        })

    sales = Sale.query.filter_by(customer_id=customer_id).options(
        joinedload(Sale.lines).load_only(SaleLine.id, SaleLine.quantity, SaleLine.unit_price, SaleLine.line_total, SaleLine.line_receiver, SaleLine.note),
        joinedload(Sale.lines).joinedload(SaleLine.product).load_only(Product.id, Product.name)
    ).filter(Sale.sale_date >= start_date).filter(Sale.sale_date <= end_date).order_by(Sale.sale_date, Sale.id).all()
    
    for s in sales:
        if s.preorder_id:
            preorder = PreOrder.query.get(s.preorder_id)
            if preorder:
                prepaid_amount = D(preorder.prepaid_amount or 0)
                if prepaid_amount > 0:
                    prepaid_payment = Payment.query.filter(
                        Payment.preorder_id == preorder.id,
                        Payment.direction == 'IN',
                        Payment.status.in_(['COMPLETED', 'PENDING']),
                        Payment.sale_id.is_(None)
                    ).first()
                    
                    if prepaid_payment:
                        prepaid_payment.sale_id = s.id
                        if not prepaid_payment.customer_id:
                            prepaid_payment.customer_id = s.customer_id
                        db.session.add(prepaid_payment)
    
    db.session.flush()
    db.session.expire_all()
    
    for s in sales:
        sale_lines = getattr(s, 'lines', []) or []
        items = []
        for line in sale_lines:
            product = getattr(line, 'product', None)
            items.append({
                'name': getattr(product, 'name', 'منتج') if product else 'منتج',
                'quantity': getattr(line, 'quantity', 0),
                'unit_price': D(getattr(line, 'unit_price', 0) or 0),
                'total': D(getattr(line, 'line_total', 0) or 0),
                'receiver': getattr(line, 'line_receiver', None) or '',
                'note': getattr(line, 'note', None) or ''
            })
        
        entries.append({
            "date": getattr(s, "sale_date", None) or getattr(s, "created_at", None),
            "type": "SALE",
            "ref": getattr(s, "sale_number", None) or f"SALE-{s.id}",
            "statement": generate_statement("SALE", s),
            "debit": D(s.total_amount or 0),  # البيع = عليه (مدين)
            "credit": D(0),
            "items": items,  # إضافة البنود المباعة
            "notes": getattr(s, 'notes', '') or '',
            "currency": getattr(s, 'currency', None) or (getattr(c, 'currency', None) or 'ILS'),
        })

    sale_returns = (
        SaleReturn.query
        .filter(SaleReturn.customer_id == customer_id)
        .filter(SaleReturn.status == 'CONFIRMED')
        .filter(SaleReturn.created_at >= start_date)
        .filter(SaleReturn.created_at <= end_date)
        .order_by(SaleReturn.created_at, SaleReturn.id)
        .all()
    )
    for ret in sale_returns:
        entries.append({
            "date": getattr(ret, "created_at", None) or getattr(ret, "updated_at", None),
            "type": "SALE_RETURN",
            "ref": f"RET-{ret.id}",
            "statement": generate_statement("SALE_RETURN", ret),
            "debit": D(0),
            "credit": D(ret.total_amount or 0),
            "notes": ret.reason or ret.notes or '',
            "currency": getattr(ret, 'currency', None) or (getattr(c, 'currency', None) or 'ILS'),
        })

    services = (
        ServiceRequest.query
        .filter(ServiceRequest.customer_id == customer_id)
        .filter(ServiceRequest.completed_at >= start_date)
        .filter(ServiceRequest.completed_at <= end_date)
        .order_by(ServiceRequest.completed_at, ServiceRequest.id)
        .all()
    )
    for srv in services:
        service_total = D(getattr(srv, "total_amount", 0) or 0)
        if service_total <= 0:
            service_total = D(service_grand_total(srv))
        entries.append({
            "date": getattr(srv, "completed_at", None) or getattr(srv, "created_at", None),
            "type": "SERVICE",
            "ref": getattr(srv, "service_number", None) or f"SRV-{srv.id}",
            "statement": generate_statement("SERVICE", srv),
            "debit": service_total,
            "credit": D(0),
            "notes": getattr(srv, 'notes', '') or '',
            "currency": getattr(srv, 'currency', None) or (getattr(c, 'currency', None) or 'ILS'),
        })

    preorders = PreOrder.query.filter(
        PreOrder.customer_id == customer_id,
        PreOrder.status != 'CANCELLED',
        PreOrder.status != 'FULFILLED'
    ).filter(PreOrder.created_at >= start_date).filter(PreOrder.created_at <= end_date).order_by(PreOrder.created_at, PreOrder.id).all()
    
    for pre in preorders:
        prepaid_amount_raw = pre.prepaid_amount
        prepaid_amount = D(prepaid_amount_raw or 0) if prepaid_amount_raw is not None else D(0)
        total_amount = D(pre.total_amount or 0)
        
        preorder_ref = getattr(pre, "order_number", None) or getattr(pre, "reference", None) or f"PRE-{pre.id}"
        
        if total_amount > 0:
            entries.append({
                "date": pre.preorder_date or pre.created_at or datetime.now(),
                "type": "PREORDER",
                "ref": preorder_ref,
                "statement": generate_statement("PREORDER", pre),
                "debit": total_amount,
                "credit": D(0),
                "notes": getattr(pre, 'notes', '') or '',
            })
        
        if prepaid_amount > 0:
            entries.append({
                "date": pre.preorder_date or pre.created_at or datetime.now(),
                "type": "PREPAID",
                "ref": preorder_ref,
                "statement": f"عربون حجز {preorder_ref}",
                "debit": D(0),
                "credit": prepaid_amount,
                "notes": "عربون مدفوع - حق له",
            })

    online_preorders = (
        OnlinePreOrder.query
        .filter(OnlinePreOrder.customer_id == customer_id)
        .filter(OnlinePreOrder.created_at >= start_date)
        .filter(OnlinePreOrder.created_at <= end_date)
        .order_by(OnlinePreOrder.created_at, OnlinePreOrder.id)
        .all()
    )
    for op in online_preorders:
        prepaid_amount = D(op.prepaid_amount or 0)
        total_amount = D(op.total_amount or 0)
        
        entries.append({
            "date": op.created_at,
            "type": "ONLINE_PREORDER",
            "ref": getattr(op, "order_number", None) or f"ONL-{op.id}",
            "statement": f"طلب أونلاين - {getattr(op, 'order_number', None) or f'ONL-{op.id}'}",
            "debit": total_amount,
            "credit": D(0),
            "notes": getattr(op, 'notes', '') or '',
        })
        
        if prepaid_amount > 0:
            entries.append({
                "date": op.created_at,
                "type": "ONLINE_PREPAID",
                "ref": getattr(op, "order_number", None) or f"ONL-{op.id}",
                "statement": f"دفعة مقدمة - طلب أونلاين {getattr(op, 'order_number', None) or f'ONL-{op.id}'}",
                "debit": D(0),
                "credit": prepaid_amount,
                "notes": "دفعة مقدمة - طلب أونلاين",
            })

    # ✅ فلترة الدفعات: COMPLETED + PENDING + الشيكات المرتدة (BOUNCED/FAILED)
    # PENDING: الشيكات المعلقة تُحسب في الرصيد (حسب العرف المحلي)
    # BOUNCED/FAILED: الشيكات المرتدة تظهر لتوثيق عكس القيد
    payment_statuses = ['COMPLETED', 'PENDING', 'BOUNCED', 'FAILED', 'REJECTED']
    
    # ✅ إضافة joinedload(Payment.splits) لجميع استعلامات الدفعات لضمان تحميل splits
    # ✅ البحث عن جميع الدفعات المباشرة للعميل (بما في ذلك entity_type == 'CUSTOMER')
    payments_direct = Payment.query.filter(
        Payment.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    
    payments_direct_filtered = []
    for p in payments_direct:
        if p.preorder_id and not p.sale_id:
            preorder = PreOrder.query.get(p.preorder_id)
            if preorder and preorder.status != 'FULFILLED':
                continue
        payments_direct_filtered.append(p)
    payments_direct = payments_direct_filtered
    
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(
        Sale.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(
        Invoice.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(
        ServiceRequest.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(
        PreOrder.customer_id == customer_id,
        Payment.status.in_(payment_statuses),
        or_(
            PreOrder.status == 'FULFILLED',
            Payment.sale_id.isnot(None)
        )
    ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    
    from models import Expense
    expense_ids_with_customer = [e.id for e in Expense.query.filter(Expense.customer_id == customer_id).all()]
    if expense_ids_with_customer:
        payments_from_expenses = Payment.query.filter(
            Payment.expense_id.isnot(None),
            Payment.status.in_(payment_statuses),
            or_(
                Payment.customer_id == customer_id,
                Payment.expense_id.in_(expense_ids_with_customer)
            )
        ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()
    else:
        payments_from_expenses = Payment.query.filter(
            Payment.expense_id.isnot(None),
            Payment.customer_id == customer_id,
            Payment.status.in_(payment_statuses)
        ).filter(Payment.payment_date >= start_date).filter(Payment.payment_date <= end_date).options(joinedload(Payment.splits)).all()

    seen = set()
    all_payments = []
    for p in payments_direct + payments_from_sales + payments_from_invoices + payments_from_services + payments_from_preorders + payments_from_expenses:
        if p.id in seen:
            continue
        seen.add(p.id)
        all_payments.append(p)

    all_payments.sort(key=lambda x: (getattr(x, "payment_date", None) or getattr(x, "created_at", None) or datetime.min, x.id))
    
    # تتبع الشيكات المعروضة لتجنب التكرار بين الدفعات المختلفة
    # نستخدم dictionary لتخزين أفضل دفعة لكل شيك (الأولوية للشيكات CASHED)
    seen_check_identifiers = {}  # key: (check_number, check_bank, check_due_date), value: (payment_id, has_cashed)
    
    for p in all_payments:
        payment_status = getattr(p, 'status', 'COMPLETED')
        
        checks_related = Check.query.filter(Check.payment_id == p.id).all()
        
        splits = list(getattr(p, 'splits', []) or [])
        if splits:
            for split in splits:
                split_method_val = getattr(split, "method", None)
                if hasattr(split_method_val, "value"):
                    split_method_val = split_method_val.value
                split_method_raw = str(split_method_val or "").lower()
                if 'check' in split_method_raw or 'cheque' in split_method_raw:
                    split_checks = Check.query.filter(
                        or_(
                            Check.reference_number == f"PMT-SPLIT-{split.id}",
                            Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                        )
                    ).all()
                    checks_related.extend(split_checks)
        
        # إزالة الشيكات المكررة بناءً على ID
        seen_check_ids = set()
        unique_checks = []
        for check in checks_related:
            if check.id not in seen_check_ids:
                seen_check_ids.add(check.id)
                unique_checks.append(check)
        checks_related = unique_checks
        
        # إزالة التكرارات الإضافية بناءً على رقم الشيك + البنك + تاريخ الاستحقاق
        # (في حالة وجود شيكات مختلفة بنفس الرقم)
        # الأولوية للشيكات بحالة CASHED أو الحالة الأحدث
        seen_check_keys = {}
        final_checks = []
        
        # ترتيب الشيكات: CASHED أولاً، ثم الحالات الأخرى
        status_priority = {'CASHED': 1, 'RETURNED': 2, 'BOUNCED': 3, 'RESUBMITTED': 4, 'CANCELLED': 5, 'ARCHIVED': 6, 'PENDING': 7}
        
        for check in checks_related:
            check_number = str(check.check_number or '').strip()
            check_bank = str(check.check_bank or '').strip()
            check_due_date_str = str(check.check_due_date or '') if check.check_due_date else ''
            
            # استخراج حالة الشيك
            status_value = getattr(check, 'status', 'PENDING') or 'PENDING'
            if hasattr(status_value, 'value'):
                check_status = str(status_value.value).upper()
            else:
                check_status = str(status_value).upper()
            
            check_key = (check_number, check_bank, check_due_date_str)
            
            # إذا كان رقم الشيك فارغاً، نضيفه دائماً (شيكات بدون رقم)
            if not check_number:
                final_checks.append(check)
            elif check_key not in seen_check_keys:
                # إذا كان المفتاح غير موجود، نضيفه
                seen_check_keys[check_key] = check
                final_checks.append(check)
            else:
                # إذا كان المفتاح موجود، نتحقق من الحالة
                existing_check = seen_check_keys[check_key]
                existing_status_value = getattr(existing_check, 'status', 'PENDING') or 'PENDING'
                if hasattr(existing_status_value, 'value'):
                    existing_status = str(existing_status_value.value).upper()
                else:
                    existing_status = str(existing_status_value).upper()
                
                # إذا كانت الحالة الجديدة أفضل (أولوية أعلى)، نستبدل الشيك القديم
                new_priority = status_priority.get(check_status, 99)
                existing_priority = status_priority.get(existing_status, 99)
                
                if new_priority < existing_priority:
                    # استبدال الشيك القديم بالجديد
                    final_checks.remove(existing_check)
                    seen_check_keys[check_key] = check
                    final_checks.append(check)
        
        checks_related = final_checks
        
        has_returned_check = False
        has_bounced_check = False
        has_pending_check = False
        has_cashed_check = False
        has_resubmitted_check = False
        has_cancelled_check = False
        has_archived_check = False
        has_legal_check = False
        has_settled_check = False
        check_statuses = []
        all_checks_info = []
        
        for check in checks_related:
            # استخراج حالة الشيك بشكل صحيح من enum
            status_value = getattr(check, 'status', 'PENDING') or 'PENDING'
            if hasattr(status_value, 'value'):
                # إذا كان enum، نستخدم .value
                check_status = str(status_value.value).upper()
            else:
                # إذا كان string، نستخدمه مباشرة
                check_status = str(status_value).upper()
            
            check_notes = (getattr(check, 'notes', '') or '').upper()
            is_settled = '[SETTLED=TRUE]' in check_notes or getattr(check, 'is_settled', False)
            is_legal = 'دائرة قانونية' in (getattr(check, 'notes', '') or '') or getattr(check, 'is_legal', False)
            
            check_statuses.append(check_status)
            all_checks_info.append({
                'check_number': check.check_number,
                'check_bank': check.check_bank,
                'check_due_date': check.check_due_date,
                'status': check_status,
                'is_settled': is_settled,
                'is_legal': is_legal,
                'amount': getattr(check, 'amount', 0),
                'currency': getattr(check, 'currency', 'ILS'),
                'notes': getattr(check, 'notes', ''),
            })
            
            if check_status in ['RETURNED', 'BOUNCED']:
                has_returned_check = True
                if check_status == 'BOUNCED':
                    has_bounced_check = True
            elif check_status == 'PENDING':
                has_pending_check = True
            elif check_status == 'CASHED':
                has_cashed_check = True
            elif check_status == 'RESUBMITTED':
                has_resubmitted_check = True
            elif check_status in ['CANCELLED', 'ARCHIVED']:
                has_cancelled_check = True
                if check_status == 'ARCHIVED':
                    has_archived_check = True
            
            if is_legal:
                has_legal_check = True
            if is_settled:
                has_settled_check = True
        
        if checks_related:
            is_bounced = has_returned_check or has_bounced_check
            is_pending = has_pending_check and not is_bounced
        else:
            is_bounced = payment_status in ['BOUNCED', 'FAILED', 'REJECTED']
            is_pending = payment_status == 'PENDING'
        
        # توليد البيان للدفعة - محسّن وواضح
        method_map = {
            'cash': 'نقداً',
            'card': 'بطاقة',
            'cheque': 'شيك',
            'bank': 'تحويل بنكي',
            'online': 'إلكتروني',
        }
        method_value = getattr(p, 'method', 'cash')
        if hasattr(method_value, 'value'):
            method_value = method_value.value
        method_raw = str(method_value).lower()
        
        split_details = []
        if not splits:
            splits = list(getattr(p, 'splits', []) or [])
        if splits:
            unique_methods = set()
            for split in sorted(splits, key=lambda s: getattr(s, "id", 0)):
                split_method_val = getattr(split, "method", None)
                if hasattr(split_method_val, "value"):
                    split_method_val = split_method_val.value
                split_method_raw = str(split_method_val or "").lower()
                if not split_method_raw:
                    split_method_raw = method_raw or "cash"
                unique_methods.add(split_method_raw)
                split_currency = (getattr(split, "currency", None) or getattr(p, "currency", "ILS") or "ILS").upper()
                converted_currency = (getattr(split, "converted_currency", None) or getattr(p, "currency", "ILS") or "ILS").upper()
                split_details.append({
                    "method": method_map.get(split_method_raw, split_method_raw),
                    "method_raw": split_method_raw,
                    "amount": D(getattr(split, "amount", 0) or 0),
                    "currency": split_currency,
                    "fx_rate": getattr(split, "fx_rate_used", None),
                    "fx_rate_source": getattr(split, "fx_rate_source", None),
                    "converted_amount": D(getattr(split, "converted_amount", 0) or 0),
                    "converted_currency": converted_currency,
                })
            if unique_methods:
                if len(unique_methods) == 1:
                    method_raw = next(iter(unique_methods))
                else:
                    method_raw = "mixed"

        method_arabic = method_map.get(method_raw, method_raw if method_raw != "mixed" else "طرق متعددة")
        if method_raw == "mixed":
            method_display = "طرق متعددة"
        else:
            method_display = method_arabic
        
        amount = float(getattr(p, 'total_amount', 0) or 0)
        deliverer_name = getattr(p, 'deliverer_name', None) or ''
        receiver_name = getattr(p, 'receiver_name', None) or ''
        receipt_number = getattr(p, 'receipt_number', None) or getattr(p, 'payment_number', None) or ''
        check_number = getattr(p, 'check_number', None) if method_raw == 'cheque' else None
        check_due_date = getattr(p, 'check_due_date', None) if method_raw == 'cheque' else None
        
        notes = getattr(p, 'notes', '') or ''
        
        check_info = None
        primary_check = None
        if all_checks_info:
            for check_data in all_checks_info:
                if check_data['status'] in ['RETURNED', 'BOUNCED', 'CASHED', 'RESUBMITTED', 'CANCELLED', 'ARCHIVED']:
                    check_info = check_data
                    primary_check = check_data
                    break
            if not check_info and all_checks_info:
                check_info = all_checks_info[0]
                primary_check = all_checks_info[0]
        
        payment_details = {
            'method': method_display,
            'method_raw': method_raw,
            'check_number': check_info['check_number'] if check_info else check_number,
            'check_bank': check_info['check_bank'] if check_info else getattr(p, 'check_bank', None),
            'check_due_date': check_info['check_due_date'] if check_info else check_due_date,
            'card_holder': getattr(p, 'card_holder', None),
            'card_last4': getattr(p, 'card_last4', None),
            'bank_transfer_ref': getattr(p, 'bank_transfer_ref', None),
            'deliverer_name': deliverer_name,
            'receiver_name': receiver_name,
            'status': check_info['status'] if check_info and check_info['status'] in ['RETURNED', 'BOUNCED', 'CASHED', 'RESUBMITTED', 'CANCELLED', 'ARCHIVED'] else payment_status,
            'is_bounced': is_bounced,
            'is_pending': is_pending,
            'is_cashed': has_cashed_check,
            'is_resubmitted': has_resubmitted_check,
            'is_cancelled': has_cancelled_check,
            'is_archived': has_archived_check,
            'is_legal': has_legal_check,
            'is_settled': has_settled_check,
            'splits': split_details,
            'checks_statuses': check_statuses if checks_related else [],
            'all_checks': all_checks_info,
        }
        
        display_check_number = check_info['check_number'] if check_info and check_info.get('check_number') else check_number
        
        if has_legal_check:
            payment_statement = f"⚖️ شيك محوّل للدائرة القانونية - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_LEGAL"
        elif has_settled_check:
            payment_statement = f"✅ شيك مسوّى - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_SETTLED"
        elif is_bounced:
            payment_statement = f"❌ شيك مرفوض - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_BOUNCED"
        elif has_resubmitted_check:
            payment_statement = f"🔄 شيك أعيد للبنك - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_RESUBMITTED"
        elif has_cashed_check:
            payment_statement = f"✅ شيك مسحوب - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_CASHED"
        elif has_cancelled_check or has_archived_check:
            payment_statement = f"🚫 شيك ملغي - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_CANCELLED"
        elif is_pending and method_raw == 'cheque':
            payment_statement = f"⏳ شيك معلق - {method_arabic}"
            if display_check_number:
                payment_statement += f" #{display_check_number}"
            entry_type = "CHECK_PENDING"
        else:
            payment_statement = f"سند قبض - {method_arabic}"
            entry_type = "PAYMENT"
        
        if deliverer_name and not is_bounced and not has_legal_check:
            payment_statement += f" - سلَّم ({deliverer_name})"
        if receiver_name and not is_bounced and not has_legal_check:
            payment_statement += f" - لـيـد ({receiver_name})"
        
        # استخراج Direction value من enum
        direction_value = p.direction.value if hasattr(p.direction, 'value') else str(p.direction)
        is_out = direction_value == 'OUT'  # صادر من الشركة للعميل
        is_in = not is_out  # وارد من العميل للشركة
        
        # حساب debit/credit
        # في محاسبة العملاء:
        # - الدفعة الواردة (IN) = العميل دفع لنا = له (حق له = تقليل ما عليه) = credit (دائن)
        # - الدفعة الصادرة (OUT) = دفعنا للعميل = عليه (التزام عليه = يجب أن يعيد المبلغ) = debit (مدين)
        
        returned_checks_amount = D(0)
        returned_checks_list = []
        
        if splits:
            from models import PaymentMethod
            
            payment_checks = Check.query.filter(Check.payment_id == p.id).all()
            
            split_checks = []
            for split in splits:
                split_method_val = getattr(split, "method", None)
                if hasattr(split_method_val, "value"):
                    split_method_val = split_method_val.value
                split_method_raw = str(split_method_val or "").lower()
                if 'check' in split_method_raw or 'cheque' in split_method_raw:
                    checks_for_split = Check.query.filter(
                        or_(
                            Check.reference_number == f"PMT-SPLIT-{split.id}",
                            Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                        )
                    ).all()
                    split_checks.extend(checks_for_split)
            
            all_checks_for_payment = list(set(payment_checks + split_checks))
            
            returned_check_amounts = {}
            for check in all_checks_for_payment:
                if check.status in ['RETURNED', 'BOUNCED']:
                    if check.reference_number and 'PMT-SPLIT-' in check.reference_number:
                        try:
                            split_id = int(check.reference_number.split('PMT-SPLIT-')[1].split('-')[0])
                            check_amt = D(str(check.amount or 0))
                            if check.currency and check.currency != "ILS":
                                try:
                                    from models import convert_amount
                                    check_amt = convert_amount(check_amt, check.currency, "ILS", check.check_date or p.payment_date)
                                except:
                                    pass
                            returned_check_amounts[split_id] = check_amt
                            returned_checks_list.append({
                                'check': check,
                                'split_id': split_id,
                                'amount': check_amt
                            })
                        except:
                            pass
                    elif check.check_number:
                        for split in splits:
                            split_method_val = getattr(split, "method", None)
                            if hasattr(split_method_val, "value"):
                                split_method_val = split_method_val.value
                            split_method_raw = str(split_method_val or "").lower()
                            if 'check' in split_method_raw or 'cheque' in split_method_raw:
                                split_details = split.details or {}
                                if isinstance(split_details, str):
                                    try:
                                        import json
                                        split_details = json.loads(split_details)
                                    except:
                                        split_details = {}
                                if split_details.get('check_number') == check.check_number:
                                    check_amt = D(str(check.amount or 0))
                                    if check.currency and check.currency != "ILS":
                                        try:
                                            from models import convert_amount
                                            check_amt = convert_amount(check_amt, check.currency, "ILS", check.check_date or p.payment_date)
                                        except:
                                            pass
                                    returned_check_amounts[split.id] = check_amt
                                    returned_checks_list.append({
                                        'check': check,
                                        'split_id': split.id,
                                        'amount': check_amt
                                    })
                                    break
            
            for split in splits:
                if split.id in returned_check_amounts:
                    returned_checks_amount += returned_check_amounts[split.id]
        
        if has_legal_check or has_settled_check:
            debit_val = D(0)
            credit_val = D(0)
        else:
            amount = D(p.total_amount or 0)
            if is_in:
                debit_val = D(0)
                credit_val = amount  # الدفعة الواردة (IN) = له (حق له) = دائن
            else:
                debit_val = amount  # الدفعة الصادرة (OUT) = عليه (التزام عليه) = مدين
                credit_val = D(0)
        
        # التحقق من عدم تكرار نفس الشيك في دفعات مختلفة
        # إذا كان الشيك مرتبط بهذه الدفعة وكان نفس الشيك ظهر في دفعة سابقة، نتخطى هذه الدفعة
        # الأولوية للشيكات بحالة CASHED
        should_skip = False
        has_cashed_in_this_payment = has_cashed_check
        
        if checks_related and len(checks_related) > 0:
            for check in checks_related:
                check_number = str(check.check_number or '').strip()
                check_bank = str(check.check_bank or '').strip()
                check_due_date_str = str(check.check_due_date or '') if check.check_due_date else ''
                
                if check_number:  # فقط إذا كان هناك رقم شيك
                    check_identifier = (check_number, check_bank, check_due_date_str)
                    
                    if check_identifier in seen_check_identifiers:
                        # نفس الشيك ظهر في دفعة سابقة
                        previous_payment_id, previous_has_cashed = seen_check_identifiers[check_identifier]
                        
                        # إذا كانت الدفعة السابقة تحتوي على شيك CASHED، نتخطى هذه الدفعة
                        if previous_has_cashed:
                            should_skip = True
                            current_app.logger.info(f"⚠️ تخطي دفعة {p.id} - الشيك #{check_number} ظهر في دفعة {previous_payment_id} بحالة CASHED")
                            break
                        # إذا كانت هذه الدفعة تحتوي على شيك CASHED والدفعة السابقة لا، نستبدل
                        elif has_cashed_in_this_payment:
                            # نزيل الدفعة السابقة من entries (إذا كانت موجودة)
                            # نبحث عن الدفعة السابقة بطرق مختلفة (PMT-{id} أو payment_number أو receipt_number)
                            previous_payment = next((p2 for p2 in all_payments if p2.id == previous_payment_id), None)
                            if previous_payment:
                                previous_ref = getattr(previous_payment, "payment_number", None) or getattr(previous_payment, "receipt_number", None) or f"PMT-{previous_payment_id}"
                                entries = [e for e in entries if e.get('ref') != previous_ref]
                            seen_check_identifiers[check_identifier] = (p.id, True)
                            current_app.logger.info(f"✅ استبدال دفعة {previous_payment_id} بدفعة {p.id} - الشيك #{check_number} بحالة CASHED")
                        else:
                            # كلا الدفعتين لا تحتويان على CASHED، نتخطى هذه الدفعة (نحتفظ بالأولى)
                            should_skip = True
                            current_app.logger.info(f"⚠️ تخطي دفعة {p.id} - الشيك #{check_number} ظهر في دفعة {previous_payment_id} سابقة")
                            break
                    else:
                        # أول مرة نرى هذا الشيك
                        seen_check_identifiers[check_identifier] = (p.id, has_cashed_in_this_payment)
        
        if not should_skip:
            # ✅ إذا كانت الدفعة لديها splits، نعرض كل split كدفعة منفصلة
            # بدلاً من عرض الدفعة ككل
            if splits and len(splits) > 0:
                # عرض كل split كدفعة منفصلة
                for split in sorted(splits, key=lambda s: getattr(s, "id", 0)):
                    split_method_val = getattr(split, "method", None)
                    if hasattr(split_method_val, "value"):
                        split_method_val = split_method_val.value
                    split_method_raw = str(split_method_val or "").lower()
                    if not split_method_raw:
                        split_method_raw = method_raw or "cash"
                    
                    split_currency = (getattr(split, "currency", None) or getattr(p, "currency", "ILS") or "ILS").upper()
                    converted_currency = (getattr(split, "converted_currency", None) or getattr(p, "currency", "ILS") or "ILS").upper()
                    
                    # حساب المبلغ بالـ ILS
                    split_amount = D(getattr(split, "amount", 0) or 0)
                    split_converted_amount = D(getattr(split, "converted_amount", 0) or 0)
                    
                    # استخدام المبلغ المحول إذا كان موجوداً، وإلا استخدام المبلغ الأصلي
                    if split_converted_amount > 0 and converted_currency == "ILS":
                        split_amount_ils = split_converted_amount
                    else:
                        split_amount_ils = split_amount
                        if split_currency != "ILS":
                            try:
                                from models import convert_amount
                                split_amount_ils = convert_amount(split_amount, split_currency, "ILS", p.payment_date)
                            except:
                                pass
                    
                    # تحديد طريقة الدفع للـ split
                    split_method_arabic = method_map.get(split_method_raw, split_method_raw)
                    
                    # فحص إذا كان Split لديها شيك مرتبط
                    split_check = None
                    split_check_for_return = None
                    split_check_for_pending = None
                    split_check_for_cashed = None
                    split_checks = []
                    if 'check' in split_method_raw or 'cheque' in split_method_raw:
                        split_checks = Check.query.filter(
                            or_(
                                Check.reference_number == f"PMT-SPLIT-{split.id}",
                                Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                            )
                        ).order_by(Check.updated_at.desc().nullslast(), Check.check_date.desc().nullslast(), Check.id.desc()).all()
                    
                    if split_checks:
                        for chk in split_checks:
                            chk_status = str(getattr(chk, 'status', 'PENDING') or 'PENDING').upper()
                            if chk_status in ['RETURNED', 'BOUNCED'] and not split_check_for_return:
                                split_check_for_return = chk
                            if chk_status in ['PENDING', 'RESUBMITTED'] and not split_check_for_pending:
                                split_check_for_pending = chk
                            if chk_status == 'CASHED' and not split_check_for_cashed:
                                split_check_for_cashed = chk
                        split_check = split_check_for_return or split_check_for_pending or split_check_for_cashed or split_checks[0]
                    
                    # تحديد حالة Split
                    split_is_bounced = False
                    split_is_pending = False
                    split_has_cashed = False
                    split_has_returned = False
                    
                    if split_check or split_checks:
                        check_obj_for_flags = split_check_for_return or split_check or split_checks[0]
                        check_status = str(getattr(check_obj_for_flags, 'status', 'PENDING') or 'PENDING').upper()
                        split_has_returned = split_check_for_return is not None
                        split_is_bounced = split_has_returned
                        split_has_cashed = split_check_for_cashed is not None and not split_has_returned
                        split_is_pending = (split_check_for_pending is not None) and not split_has_returned and not split_has_cashed
                    
                    # إنشاء البيان للـ split
                    if split_has_returned:
                        split_statement = f"سند قبض - {split_method_arabic}"
                        if split_check and split_check.check_number:
                            split_statement += f" #{split_check.check_number}"
                        if split_check and split_check.check_bank:
                            split_statement += f" - {split_check.check_bank}"
                        split_statement += " (شيك مرتجع)"
                        split_entry_type = "PAYMENT"
                    elif split_is_pending and ('check' in split_method_raw or 'cheque' in split_method_raw):
                        split_statement = f"⏳ شيك معلق - {split_method_arabic}"
                        if split_check and split_check.check_number:
                            split_statement += f" #{split_check.check_number}"
                        split_entry_type = "CHECK_PENDING"
                    elif split_has_cashed:
                        split_statement = f"✅ شيك مسحوب - {split_method_arabic}"
                        if split_check and split_check.check_number:
                            split_statement += f" #{split_check.check_number}"
                        split_entry_type = "CHECK_CASHED"
                    else:
                        split_statement = f"سند قبض - {split_method_arabic}"
                        split_entry_type = "PAYMENT"
                    
                    if deliverer_name and not split_is_bounced:
                        split_statement += f" - سلَّم ({deliverer_name})"
                    if receiver_name and not split_is_bounced:
                        split_statement += f" - لـيـد ({receiver_name})"
                    
                    # حساب debit/credit للـ split
                    if is_in:
                        split_debit = D(0)
                        split_credit = split_amount_ils  # الدفعة الواردة (IN) = له (حق له) = دائن
                    else:
                        split_debit = split_amount_ils  # الدفعة الصادرة (OUT) = عليه (التزام عليه) = مدين
                        split_credit = D(0)
                    
                    # إنشاء payment_details للـ split
                    split_payment_details = {
                        'method': split_method_arabic,
                        'method_raw': split_method_raw,
                        'check_number': split_check.check_number if split_check else None,
                        'check_bank': split_check.check_bank if split_check else None,
                        'check_due_date': split_check.check_due_date if split_check else None,
                        'deliverer_name': deliverer_name,
                        'receiver_name': receiver_name,
                        'status': split_check.status if split_check else payment_status,
                        'is_bounced': split_is_bounced,
                        'is_pending': split_is_pending,
                        'is_cashed': split_has_cashed,
                        'is_returned': split_has_returned,
                        'splits': [],  # لا splits داخل split
                        'all_checks': [{
                            'check_number': split_check.check_number,
                            'check_bank': split_check.check_bank,
                            'check_due_date': split_check.check_due_date,
                            'status': split_check.status,
                            'amount': float(split_check.amount or 0),
                            'currency': split_check.currency or 'ILS',
                        }] if split_check else [],
                    }
                    
                    # إضافة الـ split كدفعة منفصلة
                    entries.append({
                        "date": getattr(p, "payment_date", None) or getattr(p, "created_at", None),
                        "type": split_entry_type,
                        "ref": f"SPLIT-{split.id}-PMT-{p.id}",
                        "statement": split_statement,
                        "debit": split_debit,
                        "credit": split_credit,
                        "payment_details": split_payment_details,
                        "notes": notes,
                    })
                    
                    if split_has_returned:
                        returned_statement = "إرجاع شيك"
                        if split_check and split_check.check_number:
                            returned_statement += f" #{split_check.check_number}"
                        if split_check and split_check.check_bank:
                            returned_statement += f" - {split_check.check_bank}"
                        
                        returned_details = {
                            'method': 'شيك',
                            'method_raw': 'cheque',
                            'check_number': split_check.check_number if split_check else None,
                            'check_bank': split_check.check_bank if split_check else None,
                            'check_due_date': split_check.check_due_date if split_check else None,
                            'status': str(getattr(split_check, 'status', 'RETURNED') or 'RETURNED'),
                            'is_bounced': True,
                            'is_pending': False,
                            'is_cashed': False,
                            'is_returned': True,
                            'all_checks': [{
                                'check_number': split_check.check_number,
                                'check_bank': split_check.check_bank,
                                'check_due_date': split_check.check_due_date,
                                'status': str(getattr(split_check, 'status', 'RETURNED') or 'RETURNED'),
                                'amount': float(split_check.amount or 0),
                                'currency': split_check.currency or 'ILS',
                            }] if split_check else [],
                        }
                        
                        entries.append({
                            "date": (split_check.check_date if split_check else None) or getattr(p, "payment_date", None) or getattr(p, "created_at", None),
                            "type": "CHECK_RETURNED",
                            "ref": f"SPLIT-RETURN-{split.id}-CHK-{getattr(split_check, 'id', 'NA')}",
                            "statement": returned_statement,
                            "debit": D(0),  # كل الدفعات = له (حق له) = دائن
                            "credit": split_amount_ils,
                            "payment_details": returned_details,
                            "notes": notes,
                        })
            else:
                # ✅ الدفعة بدون splits - نعرضها كالمعتاد
                entries.append({
                    "date": getattr(p, "payment_date", None) or getattr(p, "created_at", None),
                    "type": entry_type,
                    "ref": getattr(p, "payment_number", None) or getattr(p, "receipt_number", None) or f"PMT-{p.id}",
                    "statement": payment_statement,
                    "debit": debit_val,
                    "credit": credit_val,
                    "payment_details": payment_details,
                    "notes": notes,
                })
                
                # إضافة الشيكات المرتدة كقيود منفصلة (للدفعات بدون splits)
                for returned_check_item in returned_checks_list:
                    check = returned_check_item['check']
                    check_amt = returned_check_item['amount']
                    check_status = str(getattr(check, 'status', 'RETURNED') or 'RETURNED').upper()
                    
                    check_statement = f"إرجاع شيك"
                    if check.check_number:
                        check_statement += f" #{check.check_number}"
                    if check.check_bank:
                        check_statement += f" - {check.check_bank}"
                    
                    # الشيك المرتجع = نعيد المبلغ كالتزام عليه (مدين)
                    # في كلتا الحالتين (IN أو OUT)، الشيك المرتجع يزيد ما عليه
                    returned_debit = check_amt  # الشيك المرتجع = عليه (مدين)
                    returned_credit = D(0)
                    
                    entries.append({
                        "date": check.check_date or getattr(p, "payment_date", None) or getattr(p, "created_at", None),
                        "type": "CHECK_RETURNED",
                        "ref": f"CHK-{check.id}",
                        "statement": check_statement,
                        "debit": returned_debit,
                        "credit": returned_credit,
                        "payment_details": {
                            'method': 'شيك',
                            'method_raw': 'cheque',
                        'check_number': check.check_number,
                        'check_bank': check.check_bank,
                        'check_due_date': check.check_due_date,
                        'status': check_status,
                        'is_bounced': True,
                        'is_returned': check_status == 'RETURNED',
                        'is_manual_check': False,
                        'splits': [],
                        'all_checks': [{
                            'check_number': check.check_number,
                            'check_bank': check.check_bank,
                            'check_due_date': check.check_due_date,
                            'status': check_status,
                            'amount': float(check_amt),
                            'currency': check.currency or 'ILS',
                            'notes': check.notes or '',
                        }],
                    },
                    "notes": check.notes or notes or '',
                })

    manual_checks = Check.query.filter(
        Check.customer_id == customer_id,
        Check.payment_id.is_(None)
    ).order_by(Check.check_date, Check.id).all()
    
    for check in manual_checks:
        check_status = str(getattr(check, 'status', 'PENDING') or 'PENDING').upper()
        check_notes = (getattr(check, 'notes', '') or '').upper()
        is_settled = '[SETTLED=TRUE]' in check_notes or getattr(check, 'is_settled', False)
        is_legal = 'دائرة قانونية' in (getattr(check, 'notes', '') or '') or getattr(check, 'is_legal', False)
        is_bounced = check_status in ['RETURNED', 'BOUNCED']
        is_pending = check_status == 'PENDING'
        is_cashed = check_status == 'CASHED'
        is_resubmitted = check_status == 'RESUBMITTED'
        is_cancelled = check_status in ['CANCELLED', 'ARCHIVED']
        is_archived = check_status == 'ARCHIVED'
        
        direction_value = str(getattr(check, 'direction', 'IN') or 'IN')
        is_out = direction_value == 'OUT'
        
        amount = D(check.amount or 0)
        if check.currency and check.currency != "ILS":
            try:
                from models import convert_amount
                amount = convert_amount(amount, check.currency, "ILS", check.check_date or check.created_at)
            except Exception:
                pass
        
        # حساب debit/credit للشيكات اليدوية
        # الشيك الوارد (IN) = العميل دفع لنا = credit (دائن) = تقليل ما عليه
        # الشيك الصادر (OUT) = دفعنا للعميل = debit (مدين) = زيادة ما عليه
        is_in = not is_out
        
        if is_legal or is_settled or is_bounced:
            # الشيكات القانونية/المسوية/المرفوضة لا تؤثر على الرصيد
            debit_val = D(0)
            credit_val = D(0)
        else:
            # الشيك الوارد (IN) = credit (دائن) = تقليل ما عليه
            # الشيك الصادر (OUT) = debit (مدين) = زيادة ما عليه
            debit_val = amount if is_out else D(0)
            credit_val = amount if is_in else D(0)
        
        if is_legal:
            payment_statement = f"⚖️ شيك محوّل للدائرة القانونية يدوي"
            entry_type = "CHECK_LEGAL"
        elif is_settled:
            payment_statement = f"✅ شيك مسوّى يدوي"
            entry_type = "CHECK_SETTLED"
        elif is_bounced:
            payment_statement = f"❌ شيك مرفوض يدوي"
            entry_type = "CHECK_BOUNCED"
        elif is_resubmitted:
            payment_statement = f"🔄 شيك أعيد للبنك يدوي"
            entry_type = "CHECK_RESUBMITTED"
        elif is_cashed:
            payment_statement = f"✅ شيك مسحوب يدوي"
            entry_type = "CHECK_CASHED"
        elif is_cancelled or is_archived:
            payment_statement = f"🚫 شيك ملغي يدوي"
            entry_type = "CHECK_CANCELLED"
        elif is_pending:
            payment_statement = f"⏳ شيك معلق يدوي"
            entry_type = "CHECK_PENDING"
        else:
            payment_statement = f"شيك يدوي"
            entry_type = "PAYMENT"
        
        if check.check_number:
            payment_statement += f" #{check.check_number}"
        if check.check_bank:
            payment_statement += f" - {check.check_bank}"
        
        payment_details = {
            'method': 'شيك',
            'method_raw': 'cheque',
            'check_number': check.check_number,
            'check_bank': check.check_bank,
            'check_due_date': check.check_due_date,
            'status': check_status,
            'is_bounced': is_bounced,
            'is_pending': is_pending,
            'is_cashed': is_cashed,
            'is_resubmitted': is_resubmitted,
            'is_cancelled': is_cancelled,
            'is_archived': is_archived,
            'is_legal': is_legal,
            'is_settled': is_settled,
            'is_manual_check': True,
            'splits': [],
            'all_checks': [{
                'check_number': check.check_number,
                'check_bank': check.check_bank,
                'check_due_date': check.check_due_date,
                'status': check_status,
                'is_settled': is_settled,
                'is_legal': is_legal,
                'amount': float(check.amount or 0),
                'currency': check.currency or 'ILS',
                'notes': check.notes or '',
            }],
        }
        
        entries.append({
            "date": check.check_date or check.created_at,
            "type": entry_type,
            "ref": f"CHK-{check.id}",
            "statement": payment_statement,
            "debit": debit_val,
            "credit": credit_val,
            "payment_details": payment_details,
            "notes": check.notes or "شيك يدوي",
        })

    expenses = Expense.query.filter_by(customer_id=customer_id).order_by(Expense.date, Expense.id).all()
    for exp in expenses:
        amt = D(exp.amount or 0)
        if exp.currency and exp.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, exp.currency, "ILS", exp.date)
            except Exception:
                pass
        
        exp_type_code = None
        if exp.type_id:
            exp_type = ExpenseType.query.filter_by(id=exp.type_id).first()
            if exp_type:
                exp_type_code = (exp_type.code or "").strip().upper()
        
        is_service_expense = (
            exp_type_code in ('PARTNER_EXPENSE', 'SERVICE_EXPENSE') or
            (exp.partner_id and exp.payee_type and exp.payee_type.upper() == "PARTNER") or
            (exp.supplier_id and exp.payee_type and exp.payee_type.upper() == "SUPPLIER")
        )
        
        if is_service_expense:
            statement = f"توريد خدمات لصالحه - {exp_type.name if exp_type else 'مصروف'}"
            entry_type = "SERVICE_EXPENSE"
            debit_val = D(0)
            credit_val = amt
        else:
            statement = f"مصروف / خصم - {exp_type.name if exp_type else 'مصروف'}"
            entry_type = "EXPENSE"
            debit_val = amt  # المصروف = عليه (مدين)
            credit_val = D(0)
        
        entries.append({
            "date": exp.date or exp.created_at,
            "type": entry_type,
            "ref": f"EXP-{exp.id}",
            "statement": statement,
            "debit": debit_val,
            "credit": credit_val,
            "notes": exp.notes or '',
        })

    opening_balance = D(getattr(c, 'opening_balance', 0) or 0)
    # تحويل الرصيد الافتتاحي إلى الشيكل إذا كانت عملة العميل ليست الشيكل
    if getattr(c, 'currency', None) and c.currency != "ILS":
        try:
            from models import convert_amount
            ref_date = start_date or getattr(c, 'created_at', None)
            opening_balance = D(convert_amount(opening_balance, c.currency, "ILS", ref_date))
        except Exception:
            pass
    
    if opening_balance != 0:
        opening_date = c.created_at
        if entries:
            first_entry_date = min((e["date"] for e in entries if e["date"]), default=c.created_at)
            if first_entry_date and first_entry_date < c.created_at:
                opening_date = first_entry_date
        
        opening_entry = {
            "date": opening_date,
            "type": "OPENING_BALANCE",
            "ref": "OB-001",
            "statement": "الرصيد الافتتاحي",
            "debit": abs(opening_balance) if opening_balance < 0 else D(0),  # السالب (عليه) = مدين
            "credit": abs(opening_balance) if opening_balance > 0 else D(0),  # الموجب (له) = دائن
            "notes": "الرصيد السابق قبل بدء النظام",
            "currency": "ILS"
        }
        entries.insert(0, opening_entry)
    
    def sort_key(entry):
        if entry.get("type") == "OPENING_BALANCE":
            return (datetime.min, "")  # الرصيد الافتتاحي دائماً أولاً
        return (entry.get("date") or datetime.min, entry.get("ref") or "")
    
    manual_checks = Check.query.filter(
        Check.payment_id.is_(None),
        Check.customer_id == customer_id,
        ~Check.status.in_([CheckStatus.CANCELLED.value, CheckStatus.ARCHIVED.value])
    ).all()
    
    for check in manual_checks:
        d = check.check_date
        amt = D(check.amount or 0)
        if check.currency and check.currency != "ILS" and amt > 0:
            try:
                from models import convert_amount
                convert_date = d if d else datetime.now()
                amt = convert_amount(amt, check.currency, "ILS", convert_date)
            except Exception as e:
                try:
                    current_app.logger.error(f"Error converting check #{check.id} amount: {e}")
                except Exception:
                    pass
        
        direction_value = check.direction.value if hasattr(check.direction, 'value') else str(check.direction)
        is_out = direction_value == 'OUT'
        check_status = check.status.value if hasattr(check.status, 'value') else str(check.status)
        
        ref = f"شيك #{check.check_number}"
        check_bank = check.check_bank or ''
        check_due_date = check.check_due_date.strftime('%Y-%m-%d') if check.check_due_date else ''
        
        if check_status == CheckStatus.RETURNED.value or check_status == CheckStatus.BOUNCED.value:
            if is_out:
                statement = f"↩️ شيك مرتجع صادر - {check_bank} - {ref}"
                entry_type = "CHECK_BOUNCED"
            else:
                statement = f"↩️ شيك مرتجع وارد - {check_bank} - {ref}"
                entry_type = "CHECK_BOUNCED"
        elif check_status == CheckStatus.PENDING.value:
            statement = f"⏳ شيك معلق - {check_bank} - {ref}"
            entry_type = "CHECK_PENDING"
        elif check_status == CheckStatus.CASHED.value:
            if is_out:
                statement = f"✅ شيك تم صرفه صادر - {check_bank} - {ref}"
            else:
                statement = f"✅ شيك تم صرفه وارد - {check_bank} - {ref}"
            entry_type = "CHECK_CASHED"
        elif check_status == CheckStatus.RESUBMITTED.value:
            statement = f"🔄 شيك معاد للبنك - {check_bank} - {ref}"
            entry_type = "CHECK_RESUBMITTED"
        elif check_status == CheckStatus.ARCHIVED.value:
            statement = f"📦 شيك مؤرشف - {check_bank} - {ref}"
            entry_type = "CHECK_ARCHIVED"
        else:
            if is_out:
                statement = f"شيك صادر - {check_bank} - {ref}"
            else:
                statement = f"شيك وارد - {check_bank} - {ref}"
            entry_type = "CHECK_PENDING" if check_status == CheckStatus.PENDING.value else "PAYMENT"
        
        payment_details = {
            'method': 'شيك',
            'method_raw': 'cheque',
            'check_number': check.check_number,
            'check_bank': check_bank,
            'check_due_date': check_due_date,
            'check_status': check_status,
            'is_check_settled': False,
            'is_check_legal': False,
            'is_check_resubmitted': check_status == CheckStatus.RESUBMITTED.value,
            'is_check_archived': check_status == CheckStatus.ARCHIVED.value,
            'check_notes': check.notes or ''
        }
        
        if is_out:
            entries.append({
                "date": d,
                "type": entry_type,
                "ref": ref,
                "statement": statement,
                "debit": amt,
                "credit": D(0),
                "payment_details": payment_details,
                "notes": check.notes or ''
            })
        else:
            entries.append({
                "date": d,
                "type": entry_type,
                "ref": ref,
                "statement": statement,
                "debit": D(0),
                "credit": amt,
                "payment_details": payment_details,
                "notes": check.notes or ''
            })

    entries.sort(key=sort_key)

    # تحويل جميع القيود إلى الشيكل إذا كانت عملتها ليست الشيكل (ILS)
    try:
        from models import convert_amount
        for e in entries:
            curr = e.get('currency') or 'ILS'
            if curr and curr != 'ILS':
                ref_date = e.get('date')
                e['debit'] = D(convert_amount(D(e.get('debit', 0) or 0), curr, 'ILS', ref_date))
                e['credit'] = D(convert_amount(D(e.get('credit', 0) or 0), curr, 'ILS', ref_date))
                # تحويل بنود البيع إن وجدت
                if e.get('items'):
                    for item in e['items']:
                        item_curr_val = D(item.get('unit_price', 0) or 0)
                        item_total_val = D(item.get('total', 0) or 0)
                        item['unit_price'] = D(convert_amount(item_curr_val, curr, 'ILS', ref_date))
                        item['total'] = D(convert_amount(item_total_val, curr, 'ILS', ref_date))
                e['currency'] = 'ILS'
    except Exception:
        pass

    # ابدأ الرصيد الجاري من قيمة الرصيد الافتتاحي بعد التحويل
    opening_entry_val = None
    for e in entries:
        if e.get("type") == "OPENING_BALANCE":
            opening_entry_val = D(e.get("credit", 0) or 0) - D(e.get("debit", 0) or 0)
            break
    running = opening_entry_val if opening_entry_val is not None else D(0)
    for e in entries:
        if e.get("type") == "OPENING_BALANCE":
            e["balance"] = running
            continue
        running = running + e["credit"] - e["debit"]
        e["balance"] = running

    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)
    
    balance = total_credit - total_debit
    
    if abs(float(balance - running)) > 0.01:
        current_app.logger.warning(
            f"⚠️ عدم تطابق الرصيد في كشف حساب العميل {customer_id}: "
            f"balance_from_totals={balance}, running_balance={running}, "
            f"difference={abs(float(balance - running))}"
        )
    
    db.session.refresh(c)
    current_balance = D(c.current_balance or 0)
    
    final_running_balance = running
    if entries:
        final_running_balance = entries[-1]["balance"]
    
    if abs(float(current_balance - final_running_balance)) > 0.01:
        current_app.logger.warning(
            f"⚠️ عدم تطابق الرصيد في كشف حساب العميل {customer_id}: "
            f"current_balance={current_balance}, calculated_balance={final_running_balance}, "
            f"difference={abs(float(current_balance - final_running_balance))}"
        )
        try:
            from utils.customer_balance_updater import update_customer_balance_components
            from sqlalchemy.orm import sessionmaker
            SessionFactory = sessionmaker(bind=db.engine)
            session = SessionFactory()
            try:
                update_customer_balance_components(customer_id, session)
                session.commit()
                db.session.refresh(c)
                current_balance = D(c.current_balance or 0)
            except Exception as e:
                session.rollback()
                current_app.logger.warning(f"⚠️ تعذر إعادة احتساب رصيد العميل {customer_id}: {e}")
            finally:
                session.close()
        except Exception as e:
            current_app.logger.warning(f"⚠️ تعذر إعادة احتساب رصيد العميل {customer_id}: {e}")

    total_invoices_calc = D('0.00')
    for inv in invoices:
        amt = D(inv.total_amount or 0)
        if inv.currency and inv.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, inv.currency, "ILS", inv.invoice_date)
            except Exception:
                pass
        total_invoices_calc += amt
    
    total_sales_calc = D('0.00')
    for s in sales:
        amt = D(s.total_amount or 0)
        if s.currency and s.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, s.currency, "ILS", s.sale_date)
            except Exception:
                pass
        total_sales_calc += amt

    total_sale_returns_calc = D('0.00')
    for ret in sale_returns:
        amt = D(ret.total_amount or 0)
        if ret.currency and ret.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, ret.currency, "ILS", ret.created_at)
            except Exception:
                pass
        total_sale_returns_calc += amt
    
    total_preorders_calc = D('0.00')
    for pre in preorders:
        amt = D(pre.total_amount or 0)
        if pre.currency and pre.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, pre.currency, "ILS", pre.created_at)
            except Exception:
                pass
        total_preorders_calc += amt
    
    total_online_preorders_calc = D('0.00')
    for op in online_preorders:
        amt = D(op.total_amount or 0)
        if op.currency and op.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, op.currency, "ILS", op.created_at)
            except Exception:
                pass
        total_online_preorders_calc += amt
    
    total_payments_calc = D('0.00')
    for p in all_payments:
        amt = D(p.total_amount or 0)
        if p.currency and p.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, p.currency, "ILS", p.payment_date)
            except Exception:
                pass
        total_payments_calc += amt
    
    # إضافة الشيكات اليدوية إلى إجمالي الدفعات
    for check in manual_checks:
        amt = D(check.amount or 0)
        if check.currency and check.currency != "ILS":
            try:
                from models import convert_amount
                amt = convert_amount(amt, check.currency, "ILS", check.check_date or check.created_at)
            except Exception:
                pass
        total_payments_calc += amt
    
    from utils import money_fmt
    context = {
        "customer": c,
        "ledger_entries": entries,
        "total_invoices": total_invoices_calc,
        "total_sales": total_sales_calc,
        "total_sale_returns": total_sale_returns_calc,
        "total_services": sum(D(service_grand_total(srv)) for srv in services),
        "total_preorders": total_preorders_calc,
        "total_online_preorders": total_online_preorders_calc,
        "total_payments": total_payments_calc,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balance": balance,
        "start_date": start_date,
        "end_date": end_date,
        "money_fmt": money_fmt,
    }
    return render_template("customers/account_statement.html", pdf_export=False, **context)

@customers_bp.route("/advanced_filter", methods=["GET"], endpoint="advanced_filter")
@login_required
def advanced_filter():
    import io, csv
    q = Customer.query

    balance_min = request.args.get("balance_min")
    balance_max = request.args.get("balance_max")
    try:
        if balance_min is not None and balance_min != "":
            q = q.filter(Customer.balance >= float(balance_min))
        if balance_max is not None and balance_max != "":
            q = q.filter(Customer.balance <= float(balance_max))
    except ValueError:
        pass

    if created_at_min := request.args.get("created_at_min"):
        try:
            q = q.filter(Customer.created_at >= datetime.fromisoformat(created_at_min))
        except ValueError:
            pass
    if created_at_max := request.args.get("created_at_max"):
        try:
            q = q.filter(Customer.created_at <= datetime.fromisoformat(created_at_max))
        except ValueError:
            pass

    if last_activity_min := request.args.get("last_activity_min"):
        try:
            q = q.filter(Customer.last_activity >= datetime.fromisoformat(last_activity_min))
        except ValueError:
            pass
    if last_activity_max := request.args.get("last_activity_max"):
        try:
            q = q.filter(Customer.last_activity <= datetime.fromisoformat(last_activity_max))
        except ValueError:
            pass

    if category := request.args.get("category"):
        q = q.filter(Customer.category == category)

    if status := request.args.get("status"):
        if status == "archived" and hasattr(Customer, "is_archived"):
            q = q.filter(Customer.is_archived.is_(True))
        elif status == "not_archived" and hasattr(Customer, "is_archived"):
            q = q.filter(Customer.is_archived.is_(False))
        elif status == "active":
            q = q.filter(Customer.is_active.is_(True))
        elif status == "inactive":
            q = q.filter(Customer.is_active.is_(False))
        elif status == "credit_hold":
            q = q.filter(Customer.balance > Customer.credit_limit)

    pagination = q.order_by(Customer.id.desc()).paginate(
        page=request.args.get("page", 1, type=int),
        per_page=request.args.get("per_page", 20, type=int),
        error_out=False,
    )
    customers = pagination.items

    if request.args.get("format") == "csv":
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(["ID", "Name", "Phone", "Email", "Balance", "Category", "Status"])

        def _status_label(c):
            if hasattr(c, "is_archived") and getattr(c, "is_archived", False):
                return "مؤرشف"
            if not getattr(c, "is_active", True):
                return "غير نشط"
            try:
                bal = float(c.balance or 0)
                lim = float(c.credit_limit or 0)
            except Exception:
                bal, lim = 0.0, 0.0
            if bal > lim:
                return "معلق ائتمانيًا"
            return "نشط"

        for c in customers:
            writer.writerow([c.id, c.name, c.phone, c.email, c.balance, c.category, _status_label(c)])

        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=customers_advanced_filter.csv"},
        )

    return render_template("customers/advanced_filter.html", customers=customers, pagination=pagination)

@customers_bp.route("/export", methods=["GET"], endpoint="export_customers")
@login_required
def export_customers():
    format_type = request.args.get("format", "excel")
    customers = Customer.query.filter(Customer.is_archived == False).limit(10000).all()
    if format_type == "pdf":
        # PDF export not implemented yet
        flash("تصدير PDF غير متاح حالياً. سيتم التصدير إلى Excel", "warning")
        format_type = "excel"
    
    if format_type == "excel":
        # Excel export - return JSON for now
        return jsonify([{
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'email': c.email,
            'currency': c.currency
        } for c in customers])
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'email': c.email
    } for c in customers])

@customers_bp.route("/export/contacts", methods=["GET", "POST"], endpoint="export_contacts")
@login_required
def export_contacts():
    form = ExportContactsForm()
    form.customer_ids.choices = [(c.id, f"{c.name} — {c.phone or ''}") for c in Customer.query.order_by(Customer.name).all()]
    if form.validate_on_submit():
        ids = form.customer_ids.data
        fields = form.fields.data
        fmt = form.format.data
        customers = Customer.query.filter(Customer.id.in_(ids)).all()
        if fmt == "vcf":
            return utils.generate_vcf(customers, fields)
        elif fmt == "csv":
            return utils.generate_csv_contacts(customers, fields)
        else:
            return utils.generate_excel_contacts(customers, fields)
    return render_template("customers/vcf_export.html", form=form, customers=Customer.query.order_by(Customer.name).all())

@customers_bp.route("/archive/<int:customer_id>", methods=["POST"])
@login_required
def archive_customer(customer_id):
    
    try:
        from models import Archive
        
        customer = Customer.query.get_or_404(customer_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(customer, reason, current_user.id)
        flash(f'تم أرشفة العميل {customer.name} بنجاح', 'success')
        return redirect(url_for('customers_bp.list_customers'))
        
    except Exception as e:
        
        db.session.rollback()
        flash(f'خطأ في أرشفة العميل: {str(e)}', 'error')
        return redirect(url_for('customers_bp.list_customers'))

@customers_bp.route('/restore/<int:customer_id>', methods=['POST'])
@login_required
def restore_customer(customer_id):
    
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        if not customer.is_archived:
            flash('العميل غير مؤرشف', 'warning')
            return redirect(url_for('customers_bp.list_customers'))
        
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='customers',
            record_id=customer_id
        ).first()
        
        if archive:
            utils.restore_record(archive.id)
        flash(f'تم استعادة العميل {customer.name} بنجاح', 'success')
        return redirect(url_for('customers_bp.list_customers'))
        
    except Exception as e:
        
        db.session.rollback()
        flash(f'خطأ في استعادة العميل: {str(e)}', 'error')
        return redirect(url_for('customers_bp.list_customers'))
