
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
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
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
    ServiceRequest,
    PreOrder,
    OnlinePreOrder,
)
import utils
from utils import archive_record, restore_record  # Import from utils package

customers_bp = Blueprint(
    "customers_bp",
    __name__,
    url_prefix="/customers",
    template_folder="templates/customers",
)
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
# @permission_required("manage_customers")  # Commented out - function not available
def list_customers():
    # استخدام joinedload لتحسين الأداء - فلترة السجلات غير المؤرشفة
    q = Customer.query.filter(Customer.is_archived == False).options(
        joinedload(Customer.payments),
        joinedload(Customer.sales)
    )

    if name := request.args.get("name"):
        q = q.filter(Customer.name.ilike(f"%{name}%"))
    if phone := request.args.get("phone"):
        q = q.filter(Customer.phone.ilike(f"%{phone}%"))
    if category := request.args.get("category"):
        q = q.filter(Customer.category == category)
    if "is_active" in request.args:
        q = q.filter(Customer.is_active == (request.args.get("is_active") == "1"))

    print_mode = request.args.get("print") == "1"
    scope_param = request.args.get("scope")
    print_scope = scope_param or ("page" if print_mode else "all")
    range_start = request.args.get("range_start", type=int)
    range_end = request.args.get("range_end", type=int)
    target_page = request.args.get("page_number", type=int)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(max(1, per_page), 200)

    # ترتيب محسّن
    ordered_query = q.order_by(Customer.created_at.desc())
    total_filtered = ordered_query.count()

    if print_scope not in {"all", "range", "page"}:
        print_scope = "page" if print_mode else "all"

    customers_list = []
    pagination = None

    start_index = 1
    page_number = page

    if print_mode:
        if print_scope == "all":
            customers_list = ordered_query.all()
        elif print_scope == "range":
            start_index = max(1, range_start or 1)
            end_index = range_end or total_filtered or start_index
            if end_index < start_index:
                end_index = start_index
            limit = max(1, end_index - start_index + 1)
            customers_list = ordered_query.offset(start_index - 1).limit(limit).all()
        else:
            page_number = max(1, target_page or page or 1)
            customers_list = ordered_query.offset((page_number - 1) * per_page).limit(per_page).all()
    else:
        pagination = ordered_query.paginate(page=page, per_page=per_page, error_out=False)
        customers_list = pagination.items

    args = request.args.to_dict(flat=True)
    for key in ["page", "print", "scope", "range_start", "range_end", "page_number"]:
        args.pop(key, None)

    total_pages = math.ceil(total_filtered / per_page) if per_page else 1

    active_customers = Customer.query.filter(Customer.is_archived.is_(False)).all()

    total_balance = 0.0
    total_sales = 0.0
    total_payments = 0.0
    customers_with_debt = 0
    customers_with_credit = 0

    for customer in active_customers:
        try:
            balance = float(customer.balance or 0)
            total_balance += balance
            if balance < 0:
                customers_with_debt += 1
            elif balance > 0:
                customers_with_credit += 1
        except Exception:
            continue

        try:
            total_sales += float(customer.total_invoiced or 0)
        except Exception:
            pass

        try:
            total_payments += float(customer.total_paid or 0)
        except Exception:
            pass

    summary = {
        'total_customers': len(active_customers),
        'total_balance': total_balance,
        'total_sales': total_sales,
        'total_payments': total_payments,
        'customers_with_debt': customers_with_debt,
        'customers_with_credit': customers_with_credit,
        'average_balance': (total_balance / len(active_customers)) if active_customers else 0
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

    return render_template("customers/list.html", **context)


@customers_bp.route("/<int:customer_id>", methods=["GET"], endpoint="customer_detail")
@login_required
# @permission_required("manage_customers")  # Commented out - function not available
def customer_detail(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    return render_template("customers/detail.html", customer=customer)


@customers_bp.route("/<int:customer_id>/analytics", methods=["GET"], endpoint="customer_analytics")
@login_required
# @permission_required("manage_customers")  # Commented out - function not available
def customer_analytics(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)

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

    invoices = Invoice.query.filter_by(customer_id=customer_id).all()
    sales = Sale.query.filter_by(customer_id=customer_id).all()
    services = ServiceRequest.query.filter_by(customer_id=customer_id).all()

    total_invoices = sum((D(inv.total_amount or 0)) for inv in invoices)
    total_sales = sum((D(s.total_amount or 0)) for s in sales)
    total_services = sum((D(service_grand_total(srv))) for srv in services)

    total_purchases = total_invoices + total_sales + total_services
    docs_count = len(invoices) + len(sales) + len(services)
    avg_purchase = (total_purchases / docs_count) if docs_count else D(0)

    # ✅ فلترة الدفعات: فقط COMPLETED (استبعاد المحذوفة/الملغاة)
    payments_direct = Payment.query.filter_by(
        customer_id=customer_id,
        status=PaymentStatus.COMPLETED.value
    ).all()
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(
        Sale.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).all()
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(
        Invoice.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).all()
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(
        ServiceRequest.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
    ).all()
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(
        PreOrder.customer_id == customer_id,
        Payment.status == PaymentStatus.COMPLETED.value
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
                "total": total,
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
# @permission_required("manage_customers")  # Commented out - function not available
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
# @permission_required("manage_customers")  # Commented out - function not available
def create_customer():
    form = CustomerForm()
    is_ajax = _is_ajax()
    if not form.validate_on_submit():
        errs = {k: v for k, v in form.errors.items()}
        if is_ajax:
            return jsonify({"ok": False, "errors": errs, "message": "تحقق من الحقول"}), 400
        if errs:
            msgs = "; ".join(f"{k}: {', '.join(v)}" for k, v in errs.items())
            flash(f"تحقق من الحقول: {msgs}", "warning")
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to")), 400
    cust = Customer(
        name=form.name.data,
        phone=form.phone.data,
        email=form.email.data or None,  # تحويل الفارغ إلى None
        address=form.address.data,
        whatsapp=form.whatsapp.data or form.phone.data,  # إذا فارغ، استخدم رقم الهاتف
        category=form.category.data,
        credit_limit=form.credit_limit.data or 0,
        discount_rate=form.discount_rate.data or 0,
        currency=form.currency.data,  # ✅ إضافة العملة
        opening_balance=form.opening_balance.data or 0,  # ✅ إضافة الرصيد الافتتاحي
        is_active=form.is_active.data,
        is_online=form.is_online.data,
        notes=form.notes.data,
    )
    if getattr(form, "password", None) and form.password.data:
        cust.set_password(form.password.data)
    db.session.add(cust)
    db.session.flush()
    try:
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
            field_errs["phone"] = ["هذا الهاتف مستخدم مسبقًا"]
        if is_ajax:
            return jsonify({"ok": False, "message": msg, "errors": field_errs}), 409
        flash(f"{msg} (Unique constraint).", "danger")
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to")), 409
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("SQLAlchemyError while creating customer")
        if is_ajax:
            return jsonify({"ok": False, "message": f"خطأ أثناء إضافة العميل: {e}"}), 500
        flash(f"❌ خطأ أثناء إضافة العميل: {e}", "danger")
        return render_template("customers/new.html", form=form, return_to=request.form.get("return_to")), 500
    if is_ajax:
        return jsonify({"ok": True, "id": cust.id, "text": cust.name}), 201
    flash("تم إنشاء العميل بنجاح", "success")
    return_to = request.form.get("return_to") or request.args.get("return_to")
    if return_to:
        return redirect(return_to)
    return redirect(url_for("customers_bp.list_customers"))

@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"], endpoint="edit_customer")
@login_required
# @permission_required("manage_customers")  # Commented out - function not available
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
            cust.email = form.email.data or None  # تحويل الفارغ إلى None
            cust.address = form.address.data
            cust.whatsapp = form.whatsapp.data or form.phone.data  # إذا فارغ، استخدم رقم الهاتف
            cust.category = form.category.data
            cust.credit_limit = form.credit_limit.data or 0
            cust.discount_rate = form.discount_rate.data or 0
            cust.currency = form.currency.data  # ✅ إضافة العملة
            cust.opening_balance = form.opening_balance.data or 0  # ✅ إضافة الرصيد الافتتاحي
            cust.is_active = bool(form.is_active.data)  # ✅ تحويل صريح لـ bool
            cust.is_online = bool(form.is_online.data)  # ✅ تحويل صريح لـ bool
            cust.notes = form.notes.data
            
            try:
                log_customer_action(cust, "UPDATE", old, cust.to_dict() if hasattr(cust, "to_dict") else None)
                db.session.commit()
                
                # التأكد من الحفظ
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
# @permission_required("manage_customers")  # Commented out - function not available
def delete_customer(id):
    """حذف عادي - يحذف فقط إذا لا توجد معاملات"""
    customer = db.session.get(Customer, id) or abort(404)
    
    # ✅ فحص سريع للعلاقات
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
# @permission_required("manage_customers")  # Commented out - function not available
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
# @permission_required("manage_customers")  # Commented out - function not available
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
# @permission_required("manage_customers")  # Commented out - function not available
def export_customer_vcf(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", (c.name or "contact")).strip("_") or "contact"
    vcf = "BEGIN:VCARD\r\nVERSION:3.0\r\n" f"FN:{c.name}\r\n" f"TEL:{c.phone or ''}\r\n" f"EMAIL:{c.email or ''}\r\n" "END:VCARD\r\n"
    return Response(vcf, mimetype="text/vcard; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={safe_name}.vcf"})

@customers_bp.route("/<int:customer_id>/account_statement", methods=["GET"], endpoint="account_statement")
@login_required
# @permission_required("manage_customers")  # Commented out - function not available
def account_statement(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    
    # ✅ تواريخ الفلترة (افتراضياً: من إنشاء العميل حتى الآن)
    from datetime import datetime, timedelta
    start_date = c.created_at or datetime.now() - timedelta(days=365)
    end_date = datetime.now()

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

    invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(Invoice.invoice_date, Invoice.id).all()
    # دالة مساعدة لتوليد البيان
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
        
        return ""
    
    for inv in invoices:
        entries.append({
            "date": inv.invoice_date or inv.created_at,
            "type": "INVOICE",
            "ref": inv.invoice_number or f"INV-{inv.id}",
            "statement": generate_statement("INVOICE", inv),
            "debit": D(inv.total_amount or 0),
            "credit": D(0),
            "notes": getattr(inv, 'notes', '') or '',
        })

    sales = Sale.query.filter_by(customer_id=customer_id).order_by(Sale.sale_date, Sale.id).all()
    for s in sales:
        # جلب البنود المباعة
        sale_lines = getattr(s, 'lines', []) or []
        items = []
        for line in sale_lines:
            product = getattr(line, 'product', None)
            items.append({
                'name': getattr(product, 'name', 'منتج') if product else 'منتج',
                'quantity': getattr(line, 'quantity', 0),
                'unit_price': D(getattr(line, 'unit_price', 0) or 0),
                'total': D(getattr(line, 'line_total', 0) or 0),
                'receiver': getattr(line, 'line_receiver', None) or '',  # مستلم البند
                'note': getattr(line, 'note', None) or ''  # ملاحظات البند
            })
        
        entries.append({
            "date": getattr(s, "sale_date", None) or getattr(s, "created_at", None),
            "type": "SALE",
            "ref": getattr(s, "sale_number", None) or f"SALE-{s.id}",
            "statement": generate_statement("SALE", s),
            "debit": D(s.total_amount or 0),
            "credit": D(0),
            "items": items,  # إضافة البنود المباعة
            "notes": getattr(s, 'notes', '') or '',
        })

    services = ServiceRequest.query.filter_by(customer_id=customer_id).order_by(ServiceRequest.completed_at, ServiceRequest.id).all()
    for srv in services:
        entries.append({
            "date": getattr(srv, "completed_at", None) or getattr(srv, "created_at", None),
            "type": "SERVICE",
            "ref": getattr(srv, "service_number", None) or f"SRV-{srv.id}",
            "statement": generate_statement("SERVICE", srv),
            "debit": D(service_grand_total(srv)),
            "credit": D(0),
            "notes": getattr(srv, 'notes', '') or '',
        })

    preorders = PreOrder.query.filter_by(customer_id=customer_id).order_by(PreOrder.created_at, PreOrder.id).all()
    for pre in preorders:
        # العربون يُحسب كدفعة واردة (credit) - حق له
        prepaid_amount = D(pre.prepaid_amount or 0)
        total_amount = D(pre.total_amount or 0)
        remaining_amount = total_amount - prepaid_amount
        
        # إضافة الحجز (عليه)
        entries.append({
            "date": pre.created_at,
            "type": "PREORDER",
            "ref": getattr(pre, "order_number", None) or f"PRE-{pre.id}",
            "statement": generate_statement("PREORDER", pre),
            "debit": total_amount,
            "credit": D(0),
            "notes": getattr(pre, 'notes', '') or '',
        })
        
        # إضافة العربون (له) - إذا كان العربون > 0
        if prepaid_amount > 0:
            entries.append({
                "date": pre.created_at,
                "type": "PREPAID",
                "ref": getattr(pre, "order_number", None) or f"PRE-{pre.id}",
                "statement": f"عربون حجز {getattr(pre, 'order_number', None) or f'PRE-{pre.id}'}",
                "debit": D(0),
                "credit": prepaid_amount,
                "notes": "عربون مدفوع - حق له",
            })

    # ✅ فلترة الدفعات: COMPLETED + PENDING + الشيكات المرتدة (BOUNCED/FAILED)
    # PENDING: الشيكات المعلقة تُحسب في الرصيد (حسب العرف المحلي)
    # BOUNCED/FAILED: الشيكات المرتدة تظهر لتوثيق عكس القيد
    payment_statuses = ['COMPLETED', 'PENDING', 'BOUNCED', 'FAILED', 'REJECTED']
    
    payments_direct = Payment.query.filter(
        Payment.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).all()
    
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(
        Sale.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).all()
    
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(
        Invoice.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).all()
    
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(
        ServiceRequest.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).all()
    
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(
        PreOrder.customer_id == customer_id,
        Payment.status.in_(payment_statuses)
    ).all()

    seen = set()
    all_payments = []
    for p in payments_direct + payments_from_sales + payments_from_invoices + payments_from_services + payments_from_preorders:
        if p.id in seen:
            continue
        seen.add(p.id)
        all_payments.append(p)

    all_payments.sort(key=lambda x: (getattr(x, "payment_date", None) or getattr(x, "created_at", None) or datetime.min, x.id))
    for p in all_payments:
        # فحص حالة الدفعة
        payment_status = getattr(p, 'status', 'COMPLETED')
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
        
        # ملاحظات
        notes = getattr(p, 'notes', '') or ''
        
        payment_details = {
            'method': method_display,  # ✅ طريقة الدفع بالعربي أو متعدد
            'method_raw': method_raw,  # القيمة الأصلية للمقارنة في القالب
            'check_number': check_number,
            'check_bank': getattr(p, 'check_bank', None),
            'check_due_date': check_due_date,
            'card_holder': getattr(p, 'card_holder', None),
            'card_last4': getattr(p, 'card_last4', None),
            'bank_transfer_ref': getattr(p, 'bank_transfer_ref', None),
            'deliverer_name': deliverer_name,
            'receiver_name': receiver_name,
            'status': payment_status,
            'is_bounced': is_bounced,
            'is_pending': is_pending,
            'splits': split_details,
        }
        
        # البيان (سيتم بناؤه ديناميكياً في القالب)
        if is_bounced:
            payment_statement = f"❌ شيك مرفوض - {method_arabic}"
            if check_number:
                payment_statement += f" #{check_number}"
        elif is_pending and method_raw == 'cheque':
            payment_statement = f"⏳ شيك معلق - {method_arabic}"
            if check_number:
                payment_statement += f" #{check_number}"
        else:
            payment_statement = f"سند قبض - {method_arabic}"
        if deliverer_name and not is_bounced:
            payment_statement += f" - سلَّم ({deliverer_name})"
        if receiver_name and not is_bounced:
            payment_statement += f" - لـيـد ({receiver_name})"
        
        # ✅ حساب المدين والدائن حسب Direction:
        # IN (من العميل للشركة) → credit (دائن) - يُخفّف دين العميل
        # OUT (من الشركة للعميل) → debit (مدين) - يزيد دين الشركة للعميل
        # الشيكات المرتدة → عكس الاتجاه الأصلي
        entry_type = "CHECK_BOUNCED" if is_bounced else ("CHECK_PENDING" if is_pending and method_raw == 'cheque' else "PAYMENT")
        
        # استخراج Direction value من enum
        direction_value = p.direction.value if hasattr(p.direction, 'value') else str(p.direction)
        is_out = direction_value == 'OUT'  # صادر من الشركة للعميل
        
        # حساب debit/credit
        amount = D(p.total_amount or 0)
        if is_bounced:
            # الشيك المرتد → عكس الاتجاه الأصلي
            debit_val = D(0) if is_out else amount  # إذا كان IN أصلاً → نعكسه لـ debit
            credit_val = amount if is_out else D(0)  # إذا كان OUT أصلاً → نعكسه لـ credit
        else:
            # الدفعة الناجحة/المعلقة → حسب Direction
            debit_val = amount if is_out else D(0)  # OUT → مدين (دفعنا له)
            credit_val = D(0) if is_out else amount  # IN → دائن (دفع لنا)
        
        entries.append({
            "date": getattr(p, "payment_date", None) or getattr(p, "created_at", None),
            "type": entry_type,
            "ref": getattr(p, "payment_number", None) or getattr(p, "receipt_number", None) or f"PMT-{p.id}",
            "statement": payment_statement,
            "debit": debit_val,
            "credit": credit_val,
            "payment_details": payment_details,  # تفاصيل الدفعة
            "notes": notes,
        })

    # إضافة الرصيد الافتتاحي كأول قيد
    opening_balance = D(getattr(c, 'opening_balance', 0) or 0)
    if opening_balance != 0 and c.currency != "ILS":
        try:
            from models import convert_amount
            ref_date = start_date or c.created_at
            opening_balance = convert_amount(opening_balance, c.currency, "ILS", ref_date)
        except Exception:
            pass
    
    if opening_balance != 0:
        # تاريخ الرصيد الافتتاحي: تاريخ إنشاء العميل أو أول معاملة
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
            "debit": abs(opening_balance) if opening_balance < 0 else D(0),  # سالب = عليه لنا = مدين
            "credit": opening_balance if opening_balance > 0 else D(0),  # موجب = له علينا = دائن
            "notes": "الرصيد السابق قبل بدء النظام",
        }
        entries.insert(0, opening_entry)
    
    entries.sort(key=lambda x: (x["date"] or datetime.min, x["ref"]))

    running = D(0)
    for e in entries:
        running += e["debit"] - e["credit"]
        e["balance"] = running

    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)
    balance = total_debit - total_credit  # ✅ الرصيد من كشف الحساب هو الصحيح

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
    
    context = {
        "customer": c,
        "ledger_entries": entries,
        "total_invoices": total_invoices_calc,
        "total_sales": total_sales_calc,
        "total_services": sum(D(service_grand_total(srv)) for srv in services),
        "total_preorders": total_preorders_calc,
        "total_online_preorders": D(0),
        "total_payments": total_payments_calc,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balance": balance,
        "start_date": start_date,
        "end_date": end_date,
    }
    if request.args.get("format") == "pdf":
        try:
            from weasyprint import HTML
            html_output = render_template("customers/account_statement.html", pdf_export=True, **context)
            pdf_bytes = HTML(string=html_output, base_url=request.url_root).write_pdf()
            filename = f"account_statement_{c.id}.pdf"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
            return Response(pdf_bytes, mimetype="application/pdf", headers=headers)
        except Exception as exc:
            current_app.logger.error("account_statement_pdf_error: %s", exc)
            flash("تعذر إنشاء ملف PDF، حاول لاحقاً.", "danger")
    return render_template("customers/account_statement.html", pdf_export=False, **context)

@customers_bp.route("/advanced_filter", methods=["GET"], endpoint="advanced_filter")
@login_required
# @permission_required("manage_customers")  # Commented out - function not available
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
# @permission_required("manage_customers")  # Commented out - function not available
def export_customers():
    format_type = request.args.get("format", "excel")  # Default to excel since PDF generator not implemented
    customers = Customer.query.all()
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
# @permission_required("manage_customers")  # Commented out - function not available
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
# @permission_required("manage_customers")  # Commented out - function not available
def archive_customer(customer_id):
    
    try:
        from models import Archive
        
        customer = Customer.query.get_or_404(customer_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(customer, reason, current_user.id)
        flash(f'تم أرشفة العميل {customer.name} بنجاح', 'success')
        return redirect(url_for('customers_bp.list_customers'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في أرشفة العميل: {str(e)}', 'error')
        return redirect(url_for('customers_bp.list_customers'))

@customers_bp.route('/restore/<int:customer_id>', methods=['POST'])
@login_required
# @permission_required('manage_customers')  # Commented out - function not available
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
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في استعادة العميل: {str(e)}', 'error')
        return redirect(url_for('customers_bp.list_customers'))