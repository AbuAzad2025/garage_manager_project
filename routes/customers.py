# customers.py - Customer Management Routes
# Location: /garage_manager/routes/customers.py
# Description: Customer management and operations routes

import csv
import io
import json
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
    Product,
    ProductCategory,
    Sale,
    SaleLine,
    ServiceRequest,
    PreOrder,
    OnlinePreOrder,
)
from utils import (
    generate_csv_contacts,
    generate_excel_contacts,
    generate_excel_report,
    generate_pdf_report,
    generate_vcf,
    permission_required,
    send_whatsapp_message,
)

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
@permission_required("manage_customers")
def list_customers():
    # استخدام joinedload لتحسين الأداء
    q = Customer.query.options(
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
    
    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(max(1, per_page), 200)
    
    # ترتيب محسّن
    pagination = q.order_by(Customer.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    args = request.args.to_dict(flat=True)
    args.pop("page", None)
    
    # حساب الملخصات الإجمالية لجميع العملاء
    all_customers = Customer.query.all()
    
    total_balance = 0.0
    total_sales = 0.0
    total_payments = 0.0
    customers_with_debt = 0
    customers_with_credit = 0
    
    for customer in all_customers:
        try:
            from models import fx_rate
            from decimal import Decimal
            
            # حساب المبيعات - تحويل كل عملية للشيقل
            sales = Sale.query.filter(Sale.customer_id == customer.id).all()
            sales_total = 0.0
            for s in sales:
                amount = float(s.total_amount or 0)
                if s.currency and s.currency != 'ILS':
                    try:
                        from decimal import Decimal
                        rate = fx_rate(s.currency, 'ILS', s.sale_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            print(f"⚠️ WARNING: سعر صرف مفقود لـ {s.currency}/ILS في المبيعات #{s.id}")
                    except ValueError as ve:
                        print(f"⚠️ ERROR: {str(ve)} - Sale #{s.id}")
                    except Exception as e:
                        print(f"⚠️ ERROR: خطأ في تحويل العملة للمبيعات #{s.id}: {str(e)}")
                sales_total += amount
            
            # حساب الدفعات - استخدام fx_rate_used
            payments = Payment.query.filter(
                Payment.customer_id == customer.id,
                Payment.direction == 'incoming'
            ).all()
            payments_total = 0.0
            for p in payments:
                amount = float(p.total_amount or 0)
                if p.fx_rate_used:
                    amount *= float(p.fx_rate_used)
                elif p.currency and p.currency != 'ILS':
                    try:
                        rate = fx_rate(p.currency, 'ILS', p.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * rate)
                        else:
                            print(f"⚠️ WARNING: سعر صرف مفقود لـ {p.currency}/ILS في الدفعة #{p.id}")
                    except ValueError as ve:
                        print(f"⚠️ ERROR: {str(ve)} - Payment #{p.id}")
                    except Exception as e:
                        print(f"⚠️ ERROR: خطأ في تحويل العملة للدفعة #{p.id}: {str(e)}")
                payments_total += amount
            
            balance = sales_total - payments_total
            
            total_sales += float(sales_total)
            total_payments += float(payments_total)
            total_balance += balance
            
            if balance > 0:
                customers_with_debt += 1
            elif balance < 0:
                customers_with_credit += 1
                
        except Exception as e:
            print(f"Error calculating customer {customer.id} balance: {str(e)}")
            pass
    
    summary = {
        'total_customers': len(all_customers),
        'total_balance': total_balance,
        'total_sales': total_sales,
        'total_payments': total_payments,
        'customers_with_debt': customers_with_debt,
        'customers_with_credit': customers_with_credit,
        'average_balance': total_balance / len(all_customers) if all_customers else 0
    }
    
    if not pagination.items:
        flash("⚠️ لا توجد بيانات لعرضها", "info")
    return render_template("customers/list.html", customers=pagination.items, pagination=pagination, args=args, summary=summary)


@customers_bp.route("/<int:customer_id>", methods=["GET"], endpoint="customer_detail")
@login_required
@permission_required("manage_customers")
def customer_detail(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    return render_template("customers/detail.html", customer=customer)


@customers_bp.route("/<int:customer_id>/analytics", methods=["GET"], endpoint="customer_analytics")
@login_required
@permission_required("manage_customers")
def customer_analytics(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)

    def D(x):
        from decimal import Decimal
        if x is None:
            return Decimal("0")
        if isinstance(x, Decimal):
            return x
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal("0")

    def q0(x):
        from decimal import Decimal
        return D(x).quantize(Decimal("1"))

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
        disc = gross * (d / 100.0)
        taxable = gross - disc
        tax = taxable * (t / 100.0)
        from decimal import Decimal
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

    payments_direct = Payment.query.filter_by(customer_id=customer_id).all()
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(Sale.customer_id == customer_id).all()
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(Invoice.customer_id == customer_id).all()
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(ServiceRequest.customer_id == customer_id).all()
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(PreOrder.customer_id == customer_id).all()

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
                "percentage": (float(total) / float(total_purchases) * 100.0) if total_purchases else 0.0,
            }
            for name, count, total in db.session.query(
                ProductCategory.name.label("name"),
                func.count(SaleLine.id).label("count"),
                func.sum(SaleLine.quantity * SaleLine.unit_price).label("total"),
            )
            .select_from(SaleLine)
            .join(Sale, Sale.id == SaleLine.sale_id)
            .join(Product, Product.id == SaleLine.product_id)
            .join(ProductCategory, ProductCategory.id == Product.category_id)
            .filter(Sale.customer_id == customer_id)
            .group_by(ProductCategory.name)
            .all()
        ],
        purchases_months=purchases_months,
        payments_months=payments_months,
    )

@customers_bp.route("/create", methods=["GET"], endpoint="create_form")
@login_required
@permission_required("manage_customers")
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
@permission_required("manage_customers")
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
        email=form.email.data,
        address=form.address.data,
        whatsapp=form.whatsapp.data,
        category=form.category.data,
        credit_limit=form.credit_limit.data or 0,
        discount_rate=form.discount_rate.data or 0,
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
@permission_required("manage_customers")
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
            cust.email = form.email.data
            cust.address = form.address.data
            cust.whatsapp = form.whatsapp.data
            cust.category = form.category.data
            cust.credit_limit = form.credit_limit.data or 0
            cust.discount_rate = form.discount_rate.data or 0
            cust.is_active = form.is_active.data
            cust.is_online = form.is_online.data
            cust.notes = form.notes.data
            try:
                log_customer_action(cust, "UPDATE", old, cust.to_dict() if hasattr(cust, "to_dict") else None)
                db.session.commit()
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
@permission_required("manage_customers")
def delete_customer(id):
    customer = db.session.get(Customer, id) or abort(404)
    has_invoices = db.session.query(Invoice.id).filter_by(customer_id=id).first() is not None
    has_payments = db.session.query(Payment.id).filter_by(customer_id=id).first() is not None
    bal = Decimal(str(getattr(customer, "balance", 0) or 0))
    if has_invoices or has_payments or bal != Decimal("0"):
        flash("لا يمكن حذف العميل لأنه مرتبط بحركات مالية أو رصيده غير صفري.", "danger")
        return redirect(url_for("customers_bp.list_customers"))
    try:
        db.session.delete(customer)
        db.session.commit()
        flash("تم حذف العميل", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء حذف العميل: {e}", "danger")
    return redirect(url_for("customers_bp.list_customers"))

@customers_bp.route("/import", methods=["GET", "POST"], endpoint="import_customers")
@login_required
@permission_required("manage_customers")
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
@permission_required("manage_customers")
@rate_limit(10, 60)
def customer_whatsapp(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    if not c.whatsapp:
        flash("لا يوجد رقم واتساب للعميل", "warning")
        return redirect(url_for("customers_bp.customer_detail", customer_id=customer_id))
    ok, info = send_whatsapp_message(c.whatsapp, f"رصيدك الحالي: {getattr(c, 'balance', 0):,.2f}")
    if ok:
        flash("تم إرسال رسالة واتساب", "success")
    else:
        flash(f"خطأ أثناء إرسال واتساب: {info}", "danger")
    return redirect(url_for("customers_bp.customer_detail", customer_id=customer_id))

@customers_bp.route("/<int:customer_id>/export_vcf", methods=["GET"], endpoint="export_customer_vcf")
@login_required
@permission_required("manage_customers")
def export_customer_vcf(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", (c.name or "contact")).strip("_") or "contact"
    vcf = "BEGIN:VCARD\r\nVERSION:3.0\r\n" f"FN:{c.name}\r\n" f"TEL:{c.phone or ''}\r\n" f"EMAIL:{c.email or ''}\r\n" "END:VCARD\r\n"
    return Response(vcf, mimetype="text/vcard; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={safe_name}.vcf"})

@customers_bp.route("/<int:customer_id>/account_statement", methods=["GET"], endpoint="account_statement")
@login_required
@permission_required("manage_customers")
def account_statement(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)

    TWOPLACES = Decimal("0.01")
    ZERO_PLACES = Decimal("1")

    def D(x):
        if x is None:
            return Decimal("0")
        if isinstance(x, Decimal):
            return x
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal("0")

    def q0(x):
        return D(x).quantize(ZERO_PLACES)

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
        disc = gross * (d / 100.0)
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
        })

    sales = Sale.query.filter_by(customer_id=customer_id).order_by(Sale.sale_date, Sale.id).all()
    for s in sales:
        entries.append({
            "date": getattr(s, "sale_date", None) or getattr(s, "created_at", None),
            "type": "SALE",
            "ref": getattr(s, "sale_number", None) or f"SALE-{s.id}",
            "statement": generate_statement("SALE", s),
            "debit": D(s.total_amount or 0),
            "credit": D(0),
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
        })

    preorders = PreOrder.query.filter_by(customer_id=customer_id).order_by(PreOrder.created_at, PreOrder.id).all()
    for pre in preorders:
        entries.append({
            "date": pre.created_at,
            "type": "PREORDER",
            "ref": getattr(pre, "order_number", None) or f"PRE-{pre.id}",
            "statement": generate_statement("PREORDER", pre),
            "debit": D(pre.total_amount or 0),
            "credit": D(0),
        })

    payments_direct = Payment.query.filter_by(customer_id=customer_id).all()
    payments_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(Sale.customer_id == customer_id).all()
    payments_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(Invoice.customer_id == customer_id).all()
    payments_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(ServiceRequest.customer_id == customer_id).all()
    payments_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(PreOrder.customer_id == customer_id).all()

    seen = set()
    all_payments = []
    for p in payments_direct + payments_from_sales + payments_from_invoices + payments_from_services + payments_from_preorders:
        if p.id in seen:
            continue
        seen.add(p.id)
        all_payments.append(p)

    all_payments.sort(key=lambda x: (getattr(x, "payment_date", None) or getattr(x, "created_at", None) or datetime.min, x.id))
    for p in all_payments:
        # توليد البيان للدفعة
        payment_method = getattr(p, 'payment_method', 'نقداً')
        notes = getattr(p, 'notes', '') or ''
        
        # معرفة مصدر الدفعة
        payment_statement = f"سداد {payment_method}"
        if getattr(p, 'sale_id', None):
            payment_statement += f" - بيع رقم {getattr(p.sale, 'sale_number', p.sale_id) if hasattr(p, 'sale') else p.sale_id}"
        elif getattr(p, 'invoice_id', None):
            payment_statement += f" - فاتورة رقم {getattr(p.invoice, 'invoice_number', p.invoice_id) if hasattr(p, 'invoice') else p.invoice_id}"
        elif getattr(p, 'service_id', None):
            payment_statement += f" - صيانة رقم {getattr(p.service, 'service_number', p.service_id) if hasattr(p, 'service') else p.service_id}"
        
        if notes:
            payment_statement += f" - {notes[:30]}"
        
        entries.append({
            "date": getattr(p, "payment_date", None) or getattr(p, "created_at", None),
            "type": "PAYMENT",
            "ref": getattr(p, "payment_number", None) or getattr(p, "receipt_number", None) or f"PMT-{p.id}",
            "statement": payment_statement,
            "debit": D(0),
            "credit": D(p.total_amount or 0),
        })

    entries.sort(key=lambda x: (x["date"] or datetime.min, x["ref"]))

    running = D(0)
    for e in entries:
        running += e["debit"] - e["credit"]
        e["balance"] = running

    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)
    balance = total_debit - total_credit

    return render_template(
        "customers/account_statement.html",
        customer=c,
        ledger_entries=entries,
        total_invoices=sum(D(inv.total_amount or 0) for inv in invoices),
        total_sales=sum(D(s.total_amount or 0) for s in sales),
        total_services=sum(D(service_grand_total(srv)) for srv in services),
        total_preorders=sum(D(pre.total_amount or 0) for pre in preorders),
        total_online_preorders=D(0),
        total_payments=sum(D(p.total_amount or 0) for p in all_payments),
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance,
    )

@customers_bp.route("/advanced_filter", methods=["GET"], endpoint="advanced_filter")
@login_required
@permission_required("manage_customers")
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
@permission_required("manage_customers")
def export_customers():
    format_type = request.args.get("format", "pdf")
    customers = Customer.query.all()
    if format_type == "pdf":
        return generate_pdf_report(customers)
    elif format_type == "excel":
        return generate_excel_report(customers)
    return jsonify([c.to_dict() for c in customers])

@customers_bp.route("/export/contacts", methods=["GET", "POST"], endpoint="export_contacts")
@login_required
@permission_required("manage_customers")
def export_contacts():
    form = ExportContactsForm()
    form.customer_ids.choices = [(c.id, f"{c.name} — {c.phone or ''}") for c in Customer.query.order_by(Customer.name).all()]
    if form.validate_on_submit():
        ids = form.customer_ids.data
        fields = form.fields.data
        fmt = form.format.data
        customers = Customer.query.filter(Customer.id.in_(ids)).all()
        if fmt == "vcf":
            return generate_vcf(customers, fields)
        elif fmt == "csv":
            return generate_csv_contacts(customers, fields)
        else:
            return generate_excel_contacts(customers, fields)
    return render_template("customers/vcf_export.html", form=form, customers=Customer.query.order_by(Customer.name).all())
