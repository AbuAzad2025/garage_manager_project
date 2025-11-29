
import csv
import io
import json
import re
import unicodedata
from datetime import datetime, date as _date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from flask import Blueprint, flash, redirect, render_template, render_template_string, abort, request, url_for, Response, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import or_, and_, func
from flask_wtf.csrf import generate_csrf
from urllib.parse import urlencode

from extensions import db
from forms import EmployeeForm, ExpenseTypeForm, ExpenseForm
from models import (
    Employee,
    ExpenseType,
    Expense,
    Shipment,
    UtilityAccount,
    StockAdjustment,
    Partner,
    Warehouse,
    Supplier,
    Customer,
    Payment,
    PaymentDirection,
    PaymentMethod,
    PaymentStatus,
    PaymentEntityType,
    ensure_currency,
    Branch,
)
import utils
from utils import D, q0, archive_record, restore_record
from routes.payments import _ensure_payment_number
from routes.checks import create_check_record

expenses_bp = Blueprint(
    "expenses_bp",
    __name__,
    url_prefix="/expenses",
    template_folder="templates/expenses",
)

DEFAULT_TYPE_META_BY_CODE = {
    "COMMUNICATION": {
        "required": ["period", "telecom_phone_number", "telecom_service_type"],
        "optional": ["utility_account_id", "beneficiary_name", "supplier_id"],
    },
    "COMMUNICATIONS": {
        "required": ["period", "telecom_phone_number", "telecom_service_type"],
        "optional": ["utility_account_id", "beneficiary_name", "supplier_id"],
    },
    "INSURANCE": {
        "required": ["insurance_company_name", "insurance_company_address"],
        "optional": ["insurance_company_phone"],
    },
    "MARKETING": {
        "required": ["period", "marketing_company_name", "marketing_company_address", "marketing_coverage_details"],
        "optional": [],
    },
    "MARKETING_OLD": {
        "required": ["period", "marketing_company_name", "marketing_company_address", "marketing_coverage_details"],
        "optional": [],
    },
    "BANK_FEES": {
        "required": ["bank_fee_bank_name", "bank_fee_notes"],
        "optional": [],
    },
    "GOV_FEES": {
        "required": ["gov_fee_entity_name", "gov_fee_entity_address", "gov_fee_notes"],
        "optional": [],
    },
    "SHIP_PORT_FEES": {
        "required": ["port_fee_port_name", "port_fee_notes"],
        "optional": [],
    },
    "TRAVEL": {
        "required": ["travel_destination", "travel_reason", "travel_notes"],
        "optional": [],
    },
    "SHIP_FREIGHT": {
        "required": ["shipping_company_name", "shipping_notes"],
        "optional": [],
    },
    "MAINTENANCE": {
        "required": ["maintenance_provider_name", "maintenance_provider_address", "maintenance_notes"],
        "optional": [],
    },
}

DEFAULT_TYPE_META_BY_NAME_SUBSTRING = {
    "اتصال": {
        "required": ["period", "telecom_phone_number", "telecom_service_type"],
        "optional": ["utility_account_id", "beneficiary_name", "supplier_id"],
    },
    "تأمين": {
        "required": ["insurance_company_name", "insurance_company_address"],
        "optional": ["insurance_company_phone"],
    },
    "تسويق": {
        "required": ["period", "marketing_company_name", "marketing_company_address", "marketing_coverage_details"],
        "optional": [],
    },
    "رسوم بنكية": {
        "required": ["bank_fee_bank_name", "bank_fee_notes"],
        "optional": [],
    },
    "رسوم حكومية": {
        "required": ["gov_fee_entity_name", "gov_fee_entity_address", "gov_fee_notes"],
        "optional": [],
    },
    "رسوم موانئ": {
        "required": ["port_fee_port_name", "port_fee_notes"],
        "optional": [],
    },
    "سفر": {
        "required": ["travel_destination", "travel_reason", "travel_notes"],
        "optional": [],
    },
    "شحن": {
        "required": ["shipping_company_name", "shipping_notes"],
        "optional": [],
    },
    "صيانة": {
        "required": ["maintenance_provider_name", "maintenance_provider_address", "maintenance_notes"],
        "optional": [],
    },
}


def _merge_type_meta(exp_type: ExpenseType) -> dict:
    base_meta = exp_type.fields_meta or {}
    merged = dict(base_meta) if isinstance(base_meta, dict) else {}

    code = (exp_type.code or "").strip().upper()
    name = (exp_type.name or "").strip()

    defaults = {}
    if code in DEFAULT_TYPE_META_BY_CODE:
        defaults = DEFAULT_TYPE_META_BY_CODE[code]
    else:
        for key, meta in DEFAULT_TYPE_META_BY_NAME_SUBSTRING.items():
            if key in name:
                defaults = meta
                break

    def _merge_list(key):
        default_vals = defaults.get(key) if isinstance(defaults, dict) else None
        result = set()
        if isinstance(default_vals, (list, tuple, set)):
            result.update(default_vals)
        current_vals = merged.get(key)
        if isinstance(current_vals, (list, tuple, set)):
            result.update(current_vals)
        return sorted(result)

    merged["required"] = _merge_list("required")
    merged["optional"] = _merge_list("optional")

    return merged


def _payment_method_choices():
    return [{"value": m.value, "label": m.label} for m in PaymentMethod]


def _serialize_expense_payments(expense: Expense):
    items = []
    for payment in getattr(expense, "payments", []) or []:
        items.append({
            "id": payment.id,
            "number": payment.payment_number or f"#{payment.id}",
            "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
            "amount": float(q0(payment.total_amount or 0)),
            "currency": payment.currency or expense.currency or "ILS",
            "status": getattr(payment, "status", "") or "",
            "method": getattr(payment, "method", "") or "",
        })
    return items


DETAIL_FIELDS = [
    "check_number",
    "check_bank",
    "check_due_date",
    "bank_transfer_ref",
    "bank_name",
    "account_number",
    "account_holder",
    "card_number",
    "card_holder",
    "card_expiry",
    "online_gateway",
    "online_ref",
]
DATE_DETAIL_FIELDS = {"check_due_date"}


def _parse_partial_payments_payload(raw_payload, default_date, default_currency):
    entries = []
    if not raw_payload:
        return entries
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        return entries
    if not isinstance(payload, list):
        return entries

    if isinstance(default_date, datetime):
        base_date = default_date
    elif isinstance(default_date, _date):
        base_date = datetime.combine(default_date, datetime.min.time())
    else:
        base_date = datetime.utcnow()

    for row in payload:
        if not isinstance(row, dict):
            continue
        amount = D(str(row.get("amount") or 0))
        if amount <= 0:
            continue
        method_raw = (row.get("method") or PaymentMethod.CASH.value).strip().lower()
        method_value = method_raw if method_raw in {m.value for m in PaymentMethod} else PaymentMethod.CASH.value
        date_str = (row.get("date") or "").strip()
        try:
            payment_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else base_date
        except ValueError:
            payment_date = base_date
        reference = (row.get("reference") or "").strip()
        notes = (row.get("notes") or "").strip()
        currency_code = ensure_currency(row.get("currency"), default_currency)
        detail_payload = {}
        for field in DETAIL_FIELDS:
            raw_val = row.get(field)
            if raw_val in (None, "", []):
                continue
            if field in DATE_DETAIL_FIELDS:
                try:
                    detail_payload[field] = datetime.strptime(str(raw_val).strip(), "%Y-%m-%d")
                except ValueError:
                    continue
            else:
                detail_payload[field] = str(raw_val).strip()
        entries.append({
            "amount": amount.quantize(Decimal("0.01")),
            "method": method_value,
            "payment_date": payment_date,
            "reference": reference,
            "notes": notes,
            "currency": currency_code,
            "details": detail_payload,
        })
    return entries


def _create_partial_payments(expense: Expense, entries):
    if not entries:
        return []
    base_currency = (expense.currency or "ILS").upper()
    total_new = sum((entry["amount"] for entry in entries if entry["currency"] == base_currency), D("0"))
    existing_paid = D(str(expense.total_paid or 0))
    total_amount = D(str(expense.amount or 0))
    if total_new + existing_paid - total_amount > D("0.01"):
        raise ValueError("الدفعات المدخلة تتجاوز المبلغ الكلي للمصروف.")

    created = []
    for entry in entries:
        expense_ref = f"مصروف #{expense.id}"
        if expense.description:
            expense_ref += f" - {expense.description}"
        elif expense.type and expense.type.name:
            expense_ref += f" - {expense.type.name}"
        
        reference_text = entry.get("reference", "").strip()
        if not reference_text:
            reference_text = expense_ref
        elif expense_ref not in reference_text:
            reference_text = f"{expense_ref} | {reference_text}"
        
        notes_text = entry.get("notes", "").strip()
        if not notes_text and expense.description:
            notes_text = expense.description
        
        payment = Payment(
            payment_date=entry["payment_date"],
            total_amount=entry["amount"],
            currency=entry["currency"],
            method=entry["method"],
            status=PaymentStatus.COMPLETED.value,
            direction=PaymentDirection.OUT.value,
            entity_type=PaymentEntityType.EXPENSE.value,
            expense_id=expense.id,
            reference=reference_text or None,
            notes=notes_text or None,
            receiver_name=expense.payee_name or expense.paid_to or expense.beneficiary_name,
            created_by=current_user.id if current_user.is_authenticated else None,
        )
        for field, value in (entry.get("details") or {}).items():
            try:
                setattr(payment, field, value)
            except Exception:
                continue
        _ensure_payment_number(payment)
        db.session.add(payment)
        created.append(payment)
    return created


def _default_expense_branch_id():
    branch = (
        Branch.query.filter(Branch.is_active.is_(True))
        .order_by(Branch.id.asc())
        .first()
    )
    return branch.id if branch else None


def _render_expense_form(
    form,
    *,
    is_edit,
    types_meta,
    types_list,
    expense=None,
    service_mode=False,
    service_supplier=None,
    service_partner=None,
    supplier_service_type_id=None,
    partner_service_type_id=None,
):
    existing_payments = _serialize_expense_payments(expense) if expense else []
    existing_paid_amount = float(q0(getattr(expense, "total_paid", 0) or 0)) if expense else 0.0
    currency_choices = []
    try:
        for code, label in getattr(form.currency, "choices", []):
            currency_choices.append({"code": code, "label": label})
    except Exception:
        currency_choices = [{"code": "ILS", "label": "ILS"}]
    return render_template(
        "expenses/expense_form.html",
        form=form,
        is_edit=is_edit,
        types_meta=types_meta,
        _types=types_list,
        payment_method_choices=_payment_method_choices(),
        existing_payments=existing_payments,
        existing_paid_amount=existing_paid_amount,
        currency_choices=currency_choices,
        service_mode=service_mode,
        service_supplier=service_supplier,
        service_partner=service_partner,
        supplier_service_type_id=supplier_service_type_id,
        partner_service_type_id=partner_service_type_id,
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

def _to_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, _date):
        return datetime.combine(value, datetime.min.time())
    return None

def _parse_date_arg(arg_name: str):
    raw = (request.args.get(arg_name) or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None

def _int_arg(name):
    v = (request.args.get(name) or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None

def _page_arg():
    raw = (request.args.get("page") or "").strip()
    if not raw:
        return 1
    try:
        page = int(raw)
    except Exception:
        return 1
    return page if page > 0 else 1

def _build_page_url(page_num: int | None):
    params = request.args.to_dict(flat=False)
    params.pop("page", None)
    if page_num and page_num > 1:
        params["page"] = [str(page_num)]
    query_parts = []
    for key, values in params.items():
        if isinstance(values, (list, tuple)):
            iterable = values
        else:
            iterable = [values]
        for value in iterable:
            if value in (None, ""):
                continue
            query_parts.append((key, value))
    qs = urlencode(query_parts, doseq=True)
    base_path = request.path
    return f"{base_path}?{qs}" if qs else base_path

def _pagination_payload(pagination):
    if not pagination:
        return None
    page = pagination.page
    pages = pagination.pages or 1
    window = 2
    start = max(1, page - window)
    end = min(pages, page + window)
    items = []
    for num in range(start, end + 1):
        items.append(
            {
                "page": num,
                "url": _build_page_url(num),
                "current": num == page,
            }
        )
    return {
        "page": page,
        "pages": pages,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "has_prev": pagination.has_prev,
        "has_next": pagination.has_next,
        "prev_page": pagination.prev_num if pagination.has_prev else None,
        "next_page": pagination.next_num if pagination.has_next else None,
        "prev_url": _build_page_url(pagination.prev_num) if pagination.has_prev else None,
        "next_url": _build_page_url(pagination.next_num) if pagination.has_next else None,
        "first_page": 1 if pages else None,
        "first_url": _build_page_url(1) if pages else None,
        "last_page": pages if pages else None,
        "last_url": _build_page_url(pages) if pages else None,
        "show_first_gap": start > 1,
        "show_last_gap": end < pages,
        "window": items,
    }

def _normalize_entity_text(value: str) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", text)


class LegacyEntityResolver:
    def __init__(self, min_length: int = 3):
        self.min_length = max(1, int(min_length or 1))
        self.lookup = {}
        self.ambiguous = set()
        self.fields = ("payee_name", "paid_to", "beneficiary_name", "disbursed_by")
        self._prepare()

    def _prepare(self):
        sources = [
            ("SUPPLIER", "المورد", "supplier", "supplier_id", Supplier),
            ("PARTNER", "الشريك", "partner", "partner_id", Partner),
            ("CUSTOMER", "العميل", "customer", "customer_id", Customer),
            ("EMPLOYEE", "الموظف", "employee", "employee_id", Employee),
        ]
        for kind, label, chip, field_name, model in sources:
            rows = db.session.query(model.id, model.name).all()
            for ident, name in rows:
                token = _normalize_entity_text(name)
                if not token or len(token) < self.min_length:
                    continue
                payload = {
                    "type": kind,
                    "label": label,
                    "chip": chip,
                    "field": field_name,
                    "id": ident,
                    "name": name,
                }
                self._register(token, payload)

    def _register(self, token, payload):
        if token in self.ambiguous:
            return
        if token in self.lookup:
            self.lookup.pop(token, None)
            self.ambiguous.add(token)
            return
        self.lookup[token] = payload

    def guess(self, expense):
        if not expense:
            return None
        if any(
            getattr(expense, field, None)
            for field in ("supplier_id", "partner_id", "customer_id", "employee_id")
        ):
            return None
        for field in self.fields:
            raw = getattr(expense, field, None)
            token = _normalize_entity_text(raw)
            if not token or len(token) < self.min_length:
                continue
            if token in self.ambiguous:
                continue
            payload = self.lookup.get(token)
            if not payload:
                continue
            result = dict(payload)
            result["guessed"] = True
            result["source_field"] = field
            result["source_value"] = raw
            return result
        return None

    def annotate(self, expenses):
        if not expenses:
            return 0
        count = 0
        for expense in expenses:
            if getattr(expense, "smart_entity_guess", None):
                continue
            guess = self.guess(expense)
            if guess:
                expense.smart_entity_guess = guess
                count += 1
        return count

def _base_query_with_filters(include_relations=True):
    show_archived = request.args.get("show_archived", "").strip().lower() in ("1", "true", "yes")
    q = Expense.query
    if not show_archived:
        q = q.filter(Expense.is_archived == False)
    if include_relations:
        q = q.options(
            selectinload(Expense.type),
            selectinload(Expense.branch),
            selectinload(Expense.employee),
            selectinload(Expense.customer),
            selectinload(Expense.partner),
            selectinload(Expense.supplier),
            selectinload(Expense.utility_account),
            selectinload(Expense.shipment),
            selectinload(Expense.payments),
        )
    from models import Branch, ExpenseType
    q = (
        q.outerjoin(ExpenseType, Expense.type_id == ExpenseType.id)
        .outerjoin(Branch, Expense.branch_id == Branch.id)
        .outerjoin(Employee, Expense.employee_id == Employee.id)
        .outerjoin(Shipment, Expense.shipment_id == Shipment.id)
        .outerjoin(UtilityAccount, Expense.utility_account_id == UtilityAccount.id)
    )

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Expense.description.ilike(like),
                Expense.paid_to.ilike(like),
                Expense.payee_name.ilike(like),
                Expense.tax_invoice_number.ilike(like),
                Employee.name.ilike(like),
                Shipment.number.ilike(like),
                UtilityAccount.alias.ilike(like),
                UtilityAccount.provider.ilike(like),
            )
        )

    start_d = _parse_date_arg("start")
    end_d = _parse_date_arg("end")
    if start_d or end_d:
        conds = []
        if start_d:
            conds.append(Expense.date >= datetime.combine(start_d, datetime.min.time()))
        if end_d:
            conds.append(Expense.date <= datetime.combine(end_d, datetime.max.time()))
        q = q.filter(and_(*conds))

    type_id = _int_arg("type_id")
    if type_id:
        q = q.filter(Expense.type_id == type_id)

    employee_id = _int_arg("employee_id")
    if employee_id:
        q = q.filter(Expense.employee_id == employee_id)

    shipment_id = _int_arg("shipment_id")
    if shipment_id:
        q = q.filter(Expense.shipment_id == shipment_id)

    utility_id = _int_arg("utility_account_id")
    if utility_id:
        q = q.filter(Expense.utility_account_id == utility_id)

    stock_adj_id = _int_arg("stock_adjustment_id")
    if stock_adj_id:
        q = q.filter(Expense.stock_adjustment_id == stock_adj_id)

    payee_type = (request.args.get("payee_type") or "").strip().upper()
    if payee_type:
        q = q.filter(Expense.payee_type == payee_type)

    q = q.order_by(Expense.date.desc(), Expense.id.desc())
    return q, {
        "q": search,
        "start": start_d,
        "end": end_d,
        "type_id": type_id,
        "employee_id": employee_id,
        "shipment_id": shipment_id,
        "utility_account_id": utility_id,
        "stock_adjustment_id": stock_adj_id,
        "payee_type": payee_type or None,
        "show_archived": show_archived,
    }

def _csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(("=", "+", "-", "@")) else s

@expenses_bp.route("/employees", methods=["GET"], endpoint="employees_list")
@login_required
def employees_list():
    employees = Employee.query.order_by(Employee.name).all()
    return render_template("expenses/employees_list.html", employees=employees)

@expenses_bp.route("/employees/add", methods=["GET", "POST"], endpoint="add_employee")
@login_required
def add_employee():
    form = EmployeeForm()
    try:
        from models import Branch, Site
        form.branch_id.choices = [(b.id, f"{b.code} - {b.name}") for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all()]
        form.site_id.choices = [(0, '-- بدون موقع --')] + [
            (s.id, f"{s.code} - {s.name}") for s in Site.query.filter_by(is_active=True).order_by(Site.name).all()
        ]
    except Exception:
        form.branch_id.choices = []
        form.site_id.choices = [(0, '-- بدون موقع --')]
    if form.validate_on_submit():
        e = Employee()
        form.populate_obj(e)
        db.session.add(e)
        try:
            db.session.commit()
            flash("✅ تمت إضافة الموظف بنجاح", "success")
            return redirect(url_for("expenses_bp.employees_list"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة الموظف: {err}", "danger")
    return render_template("expenses/employee_form.html", form=form, is_edit=False)

@expenses_bp.route("/employees/edit/<int:emp_id>", methods=["GET", "POST"], endpoint="edit_employee")
@login_required
def edit_employee(emp_id):
    e = _get_or_404(Employee, emp_id)
    form = EmployeeForm(obj=e)
    try:
        from models import Branch, Site
        form.branch_id.choices = [(b.id, f"{b.code} - {b.name}") for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all()]
        form.site_id.choices = [(0, '-- بدون موقع --')] + [
            (s.id, f"{s.code} - {s.name}") for s in Site.query.filter_by(is_active=True).order_by(Site.name).all()
        ]
    except Exception:
        form.branch_id.choices = []
        form.site_id.choices = [(0, '-- بدون موقع --')]
    if form.validate_on_submit():
        form.populate_obj(e)
        try:
            db.session.commit()
            flash("✅ تم تعديل الموظف", "success")
            return redirect(url_for("expenses_bp.employees_list"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل الموظف: {err}", "danger")
    return render_template("expenses/employee_form.html", form=form, is_edit=True)

@expenses_bp.route("/employees/<int:emp_id>/statement", methods=["GET"], endpoint="employee_statement")
@login_required
def employee_statement(emp_id):
    """كشف حساب الموظف: السلف، الخصومات، الرواتب، الرصيد"""
    from models import EmployeeDeduction, EmployeeAdvanceInstallment, ExpenseType
    
    e = _get_or_404(Employee, emp_id, joinedload(Employee.branch), joinedload(Employee.site))
    
    advance_type = ExpenseType.query.filter_by(code='EMPLOYEE_ADVANCE').first()
    advances = []
    if advance_type:
        advances = Expense.query.filter_by(employee_id=emp_id, type_id=advance_type.id).order_by(Expense.date.desc()).all()
        for adv in advances:
            adv.installments = EmployeeAdvanceInstallment.query.filter_by(advance_expense_id=adv.id).order_by(EmployeeAdvanceInstallment.installment_number).all()
    
    deductions = EmployeeDeduction.query.filter_by(employee_id=emp_id).order_by(EmployeeDeduction.start_date.desc()).all()
    
    salary_type = ExpenseType.query.filter_by(code='SALARY').first()
    salaries = []
    if salary_type:
        salaries = Expense.query.filter_by(employee_id=emp_id, type_id=salary_type.id).order_by(Expense.date.desc()).all()
    
    return render_template(
        "expenses/employee_statement.html",
        employee=e,
        advances=advances,
        deductions=deductions,
        salaries=salaries,
    )


@expenses_bp.route("/employees/<int:emp_id>/installments-due", methods=["GET"], endpoint="get_installments_due")
@login_required
def get_installments_due(emp_id):
    """API: جلب الأقساط المستحقة في شهر معين"""
    from models import EmployeeAdvanceInstallment
    from flask import jsonify
    from calendar import monthrange
    
    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))
    
    period_start = _date(year, month, 1)
    if month == 12:
        period_end = _date(year, 12, 31)
    else:
        last_day = monthrange(year, month)[1]
        period_end = _date(year, month, last_day)
    
    installments = EmployeeAdvanceInstallment.query.filter(
        EmployeeAdvanceInstallment.employee_id == emp_id,
        EmployeeAdvanceInstallment.paid == False,
        EmployeeAdvanceInstallment.due_date >= period_start,
        EmployeeAdvanceInstallment.due_date <= period_end
    ).all()
    
    total = sum(float(inst.amount or 0) for inst in installments)
    
    return jsonify({
        'installments': [{
            'id': inst.id,
            'installment_number': inst.installment_number,
            'total_installments': inst.total_installments,
            'amount': float(inst.amount or 0),
            'due_date': inst.due_date.strftime('%Y-%m-%d') if inst.due_date else '',
            'currency': inst.currency
        } for inst in installments],
        'total': round(total, 2),
        'count': len(installments)
    })


@expenses_bp.route("/employees/<int:emp_id>/generate-salary", methods=["POST"], endpoint="generate_salary")
@login_required
def generate_salary(emp_id):
    """توليد راتب شهري تلقائياً مع دعم الدفع الجزئي"""
    from models import ExpenseType, EmployeeAdvanceInstallment
    from datetime import date, datetime
    from decimal import Decimal
    
    employee = _get_or_404(Employee, emp_id)
    
    # Get form data
    month = int(request.form.get('month', date.today().month))
    year = int(request.form.get('year', date.today().year))
    
    if year < 1900 or year > 2100:
        year = date.today().year
    
    base_salary = Decimal(request.form.get('base_salary', employee.salary))
    payment_method = request.form.get('payment_method', 'BANK_TRANSFER')
    payment_date = request.form.get('payment_date', date.today().isoformat())
    notes = request.form.get('notes', '')
    
    check_number = request.form.get('check_number', '').strip()
    check_bank = request.form.get('check_bank', '').strip()
    check_due_date = request.form.get('check_due_date', '')
    check_payee = request.form.get('check_payee', employee.name).strip()
    bank_transfer_ref = request.form.get('transfer_reference', '').strip()
    bank_name = request.form.get('bank_name', '').strip()
    account_number = request.form.get('account_number', '').strip()
    account_holder = request.form.get('account_holder', employee.name).strip()
    payment_details = request.form.get('payment_details', '').strip()
    
    monthly_deductions = Decimal(str(employee.total_deductions))
    social_insurance_emp = Decimal(str(employee.social_insurance_employee_amount))
    income_tax = Decimal(str(employee.income_tax_amount))
    
    net_salary_before_advances = base_salary - monthly_deductions - social_insurance_emp - income_tax
    
    period_start = _date(year, month, 1)
    if month == 12:
        period_end = _date(year, 12, 31)
    else:
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        period_end = _date(year, month, last_day)
    
    installments_due = EmployeeAdvanceInstallment.query.filter(
        EmployeeAdvanceInstallment.employee_id == emp_id,
        EmployeeAdvanceInstallment.paid == False,
        EmployeeAdvanceInstallment.due_date >= period_start,
        EmployeeAdvanceInstallment.due_date <= period_end
    ).all()
    
    total_installments_amount = sum(Decimal(str(inst.amount or 0)) for inst in installments_due)
    
    net_salary = net_salary_before_advances - total_installments_amount
    
    actual_payment = Decimal(request.form.get('actual_payment', net_salary))
    remaining_balance = net_salary - actual_payment
    
    if actual_payment > net_salary:
        flash(f"❌ المبلغ المدفوع ({actual_payment}) أكبر من الراتب الصافي ({net_salary})", "danger")
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id))
    
    if actual_payment < 0:
        flash("❌ المبلغ المدفوع لا يمكن أن يكون سالباً", "danger")
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id))
    
    
    salary_type = ExpenseType.query.filter_by(code='SALARY').first()
    if not salary_type:
        flash("❌ نوع المصروف 'SALARY' غير موجود في النظام", "danger")
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id))
    
    existing_salary = Expense.query.filter(
        Expense.employee_id == emp_id,
        Expense.type_id == salary_type.id,
        Expense.period_start == period_start
    ).first()
    
    if existing_salary:
        flash(f"⚠️ راتب شهر {month}/{year} موجود مسبقاً للموظف {employee.name}", "warning")
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id))
    
    payment_percentage = (actual_payment / net_salary * 100) if net_salary > 0 else 0
    
    detailed_notes = f"""الراتب الأساسي: {base_salary} {employee.currency}
الخصومات الشهرية: -{monthly_deductions} {employee.currency}
التأمينات (حصة الموظف): -{social_insurance_emp} {employee.currency}
ضريبة الدخل: -{income_tax} {employee.currency}
─────────────────
الراتب بعد الاستقطاعات: {net_salary_before_advances} {employee.currency}"""
    
    if total_installments_amount > 0:
        detailed_notes += f"""
أقساط السلف المستحقة ({len(installments_due)} قسط): -{total_installments_amount} {employee.currency}"""
        for inst in installments_due:
            detailed_notes += f"\n  - قسط {inst.installment_number}/{inst.total_installments}: {inst.amount} {employee.currency}"
    
    detailed_notes += f"""
─────────────────
الراتب الصافي النهائي: {net_salary} {employee.currency}
المبلغ المدفوع فعلياً: {actual_payment} {employee.currency} ({payment_percentage:.1f}%)"""
    
    if remaining_balance > 0:
        detailed_notes += f"""
المبلغ المتبقي (دين على الشركة): {remaining_balance} {employee.currency}

⚠️ دفع جزئي - يجب متابعة المبلغ المتبقي في كشف حساب الموظف"""
    
    if notes:
        detailed_notes += f"\n\nملاحظات إضافية: {notes}"
    
    salary_expense = Expense(
        date=datetime.strptime(payment_date, '%Y-%m-%d').date(),
        amount=net_salary,
        currency=employee.currency,
        type_id=salary_type.id,
        employee_id=emp_id,
        branch_id=employee.branch_id,
        site_id=employee.site_id,
        period_start=period_start,
        period_end=period_end,
        payment_method=payment_method.upper(),
        description=f"راتب شهر {month}/{year} - {employee.name}" + (f" (دفع جزئي {payment_percentage:.0f}%)" if remaining_balance > 0 else ""),
        notes=detailed_notes,
        paid_to=employee.name,
        beneficiary_name=employee.name,
        payee_type='EMPLOYEE',
        payee_entity_id=emp_id,
        payee_name=employee.name,
        check_number=check_number if check_number else None,
        check_bank=check_bank if check_bank else None,
        check_due_date=datetime.strptime(check_due_date, '%Y-%m-%d').date() if check_due_date else None,
        check_payee=check_payee if check_payee else None,
        bank_transfer_ref=bank_transfer_ref if bank_transfer_ref else None,
        bank_name=bank_name if bank_name else None,
        account_number=account_number if account_number else None,
        account_holder=account_holder if account_holder else None
    )
    
    try:
        db.session.add(salary_expense)
        db.session.flush()
        
        salary_payment = None
        if actual_payment > 0:
            from models import Payment
            payment_notes = f"دفع {'جزئي' if remaining_balance > 0 else 'كامل'} للراتب"
            if payment_method.upper() == 'CHECK' and check_number:
                payment_notes += f" - شيك رقم {check_number}"
            elif payment_method.upper() == 'BANK_TRANSFER' and transfer_reference:
                payment_notes += f" - معاملة رقم {transfer_reference}"
            
            payment = Payment(
                payment_date=datetime.strptime(payment_date, '%Y-%m-%d'),
                total_amount=actual_payment,
                currency=employee.currency,
                direction='OUT',
                method=payment_method.upper(),
                entity_type='EXPENSE',
                expense_id=salary_expense.id,
                reference=f"دفع راتب {month}/{year} - {employee.name}",
                notes=payment_notes,
                created_by=current_user.id if current_user.is_authenticated else None
            )
            db.session.add(payment)
            salary_payment = payment
        
        for inst in installments_due:
            inst.paid = True
            inst.paid_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
            inst.paid_in_salary_expense_id = salary_expense.id
            db.session.add(inst)
        
        if installments_due:
            current_app.logger.info(f"✅ تم تحديث {len(installments_due)} قسط سلف للموظف {employee.name}")
        
        if (
            salary_payment
            and payment_method.upper() == 'CHECK'
            and check_number
            and check_bank
        ):
            db.session.flush()
            check_date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
            check_due_obj = datetime.strptime(check_due_date, '%Y-%m-%d') if check_due_date else check_date_obj
            create_check_record(
                payment=salary_payment,
                amount=actual_payment,
                check_number=check_number,
                check_bank=check_bank,
                check_date=check_date_obj,
                check_due_date=check_due_obj,
                direction='OUT',
                currency=employee.currency or 'ILS',
                reference_number=f"SALARY-{salary_expense.id}",
                notes=f"شيك راتب {month}/{year} - {employee.name}",
                payee_name=check_payee or employee.name,
                created_by_id=current_user.id if current_user.is_authenticated else None
            )
        
        db.session.commit()
        
        success_msg = f"✅ <strong>تم توليد وحفظ راتب شهر {month}/{year} بنجاح</strong><br><br>"
        success_msg += f"👤 الموظف: <strong>{employee.name}</strong><br>"
        success_msg += f"💰 الراتب الصافي الكامل: <strong>{net_salary} {employee.currency}</strong><br>"
        success_msg += f"💵 المدفوع فعلياً: <strong>{actual_payment} {employee.currency}</strong> ({payment_percentage:.0f}%)<br>"
        
        if total_installments_amount > 0:
            success_msg += f"📋 تم خصم <strong>{len(installments_due)} قسط سلف</strong> بقيمة {total_installments_amount} {employee.currency}<br>"
        
        if remaining_balance > 0:
            success_msg += f"<br>⚠️ المبلغ المتبقي (دين على الشركة): <strong class='text-danger'>{remaining_balance} {employee.currency}</strong>"
        
        if payment_method.upper() == 'CHECK' and check_number:
            success_msg += f"<br>📝 تم إنشاء سجل شيك رقم: <strong>{check_number}</strong> - البنك: {check_bank}"
        elif payment_method.upper() == 'BANK_TRANSFER' and bank_transfer_ref:
            success_msg += f"<br>🏦 رقم معاملة التحويل: <strong>{bank_transfer_ref}</strong>"
        
        flash(success_msg, "success")
        
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id, receipt_id=salary_expense.id))
        
    except Exception as err:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في توليد الراتب: {err}")
        flash(f"❌ خطأ في توليد الراتب: {err}", "danger")
        return redirect(url_for('expenses_bp.employee_statement', emp_id=emp_id))


@expenses_bp.route("/salary-receipt/<int:salary_exp_id>", methods=["GET"], endpoint="salary_receipt")
@login_required
def salary_receipt(salary_exp_id):
    """إيصال راتب قابل للطباعة - A4 Format"""
    from models import EmployeeDeduction, EmployeeAdvanceInstallment, ExpenseType, SystemSettings
    from datetime import date
    
    salary_expense = _get_or_404(Expense, salary_exp_id, joinedload(Expense.employee), joinedload(Expense.employee, Employee.branch))
    
    if not salary_expense.employee:
        flash("❌ المصروف غير مرتبط بموظف", "danger")
        return redirect(url_for("expenses_bp.list_expenses"))
    
    employee = salary_expense.employee
    
    sal_date = salary_expense.date.date() if isinstance(salary_expense.date, datetime) else salary_expense.date
    deductions = EmployeeDeduction.query.filter(
        EmployeeDeduction.employee_id == employee.id,
        EmployeeDeduction.is_active == True,
        EmployeeDeduction.start_date <= sal_date,
        or_(EmployeeDeduction.end_date.is_(None), EmployeeDeduction.end_date >= sal_date)
    ).all()
    
    installments_due = []
    if salary_expense.period_start:
        month_start = salary_expense.period_start
        month_end = salary_expense.period_end or month_start
        installments_due = EmployeeAdvanceInstallment.query.filter(
            EmployeeAdvanceInstallment.employee_id == employee.id,
            EmployeeAdvanceInstallment.paid == False,
            EmployeeAdvanceInstallment.due_date >= month_start,
            EmployeeAdvanceInstallment.due_date <= month_end
        ).all()
    
    company_info = {
        'name': SystemSettings.get_setting('COMPANY_NAME', ''),
        'address': SystemSettings.get_setting('COMPANY_ADDRESS', ''),
        'phone': SystemSettings.get_setting('COMPANY_PHONE', ''),
        'email': SystemSettings.get_setting('COMPANY_EMAIL', ''),
        'tax_number': SystemSettings.get_setting('TAX_NUMBER', ''),
    }
    
    return render_template(
        "expenses/salary_receipt.html",
        employee=employee,
        salary_expense=salary_expense,
        deductions=deductions,
        installments_due=installments_due,
        company_info=company_info,
    )

@expenses_bp.route("/employees/delete/<int:emp_id>", methods=["POST"], endpoint="delete_employee")
@login_required
def delete_employee(emp_id):
    e = _get_or_404(Employee, emp_id)
    if Expense.query.filter_by(employee_id=emp_id).first():
        flash("❌ لا يمكن حذف الموظف؛ مرتبط بمصاريف.", "danger")
    else:
        try:
            db.session.delete(e)
            db.session.commit()
            flash("✅ تم حذف الموظف", "success")
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في حذف الموظف: {err}", "danger")
    return redirect(url_for("expenses_bp.employees_list"))

@expenses_bp.route("/types", methods=["GET"], endpoint="types_list")
@login_required
def types_list():
    types = ExpenseType.query.order_by(ExpenseType.name).all()
    return render_template("expenses/types_list.html", types=types)

@expenses_bp.route("/types/add", methods=["GET", "POST"], endpoint="add_type")
@login_required
def add_type():
    form = ExpenseTypeForm()
    if form.validate_on_submit():
        t = ExpenseType()
        form.apply_to(t)
        db.session.add(t)
        try:
            db.session.commit()
            flash("✅ تمت إضافة نوع المصروف", "success")
            return redirect(url_for("expenses_bp.types_list"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة النوع: {err}", "danger")
    return render_template("expenses/type_form.html", form=form, is_edit=False)

@expenses_bp.route("/types/edit/<int:type_id>", methods=["GET", "POST"], endpoint="edit_type")
@login_required
def edit_type(type_id):
    t = _get_or_404(ExpenseType, type_id)
    form = ExpenseTypeForm(obj=t)
    if form.validate_on_submit():
        form.apply_to(t)
        try:
            db.session.commit()
            flash("✅ تم تعديل النوع", "success")
            return redirect(url_for("expenses_bp.types_list"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل النوع: {err}", "danger")
    return render_template("expenses/type_form.html", form=form, is_edit=True)

@expenses_bp.route("/types/delete/<int:type_id>", methods=["POST"], endpoint="delete_type")
@login_required
def delete_type(type_id):
    t = _get_or_404(ExpenseType, type_id)
    if Expense.query.filter_by(type_id=type_id).first():
        flash("❌ لا يمكن حذف النوع؛ مرتبط بمصاريف.", "danger")
    else:
        try:
            db.session.delete(t)
            db.session.commit()
            flash("✅ تم حذف النوع", "success")
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في حذف النوع: {err}", "danger")
    return redirect(url_for("expenses_bp.types_list"))

@expenses_bp.route("/", methods=["GET"], endpoint="list_expenses")
@login_required
def index():
    query, filt = _base_query_with_filters()
    latest_expense = query.first()
    page = _page_arg()
    per_page = current_app.config.get("EXPENSES_PER_PAGE", 10)
    try:
        per_page = int(per_page)
    except Exception:
        per_page = 10
    if per_page <= 0:
        per_page = 10
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    expenses = pagination.items
    if not latest_expense and expenses:
        latest_expense = expenses[0]
    resolver = LegacyEntityResolver()
    resolver.annotate(expenses)
    
    from models import fx_rate
    
    rate_cache = {}

    def _convert_to_ils(value, currency, dt):
        if value in (None, ""):
            return 0.0
        val = float(value or 0)
        if not val:
            return 0.0
        curr = (currency or "").upper()
        if curr in ("", "ILS"):
            return val
        if isinstance(dt, datetime):
            key_dt = dt.date()
        elif isinstance(dt, _date):
            key_dt = dt
        else:
            key_dt = None
        key = (curr, key_dt)
        rate = rate_cache.get(key)
        if rate is None:
            try:
                rate = fx_rate(curr, "ILS", dt, raise_on_missing=False)
            except Exception:
                rate = None
            rate_cache[key] = rate
        if rate and rate > 0:
            return val * float(rate)
        return val

    summary_query, _ = _base_query_with_filters(include_relations=False)
    summary_query = summary_query.with_entities(
        Expense.amount,
        Expense.currency,
        Expense.date,
        Expense.total_paid,
        Expense.type_id,
    )
    type_lookup = {t.id: t.name for t in ExpenseType.query.with_entities(ExpenseType.id, ExpenseType.name).all()}
    total_expenses = 0.0
    total_paid = 0.0
    total_balance = 0.0
    expenses_by_type = {}
    expenses_by_currency = {}
    for amount_value, currency_value, exp_date_value, paid_value, type_id_value in summary_query.yield_per(500):
        amount_ils = _convert_to_ils(amount_value, currency_value, exp_date_value)
        paid_ils = _convert_to_ils(paid_value, currency_value, exp_date_value)
        total_expenses += amount_ils
        total_paid += paid_ils
        total_balance += amount_ils - paid_ils
        type_name = type_lookup.get(type_id_value, 'غير مصنف')
        type_entry = expenses_by_type.setdefault(type_name, {'count': 0, 'amount': 0})
        type_entry['count'] += 1
        type_entry['amount'] += amount_ils
        currency_key = currency_value or 'ILS'
        currency_entry = expenses_by_currency.setdefault(currency_key, {'count': 0, 'amount': 0, 'amount_ils': 0})
        currency_entry['count'] += 1
        currency_entry['amount'] += float(amount_value or 0)
        currency_entry['amount_ils'] += amount_ils
    
    expenses_by_type_sorted = sorted(expenses_by_type.items(), key=lambda x: x[1]['amount'], reverse=True)
    total_records = pagination.total
    average_expense = total_expenses / total_records if total_records > 0 else 0
    
    summary = {
        'total_expenses': total_expenses,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'expenses_count': total_records,
        'average_expense': average_expense,
        'expenses_by_type': expenses_by_type_sorted,
        'expenses_by_currency': expenses_by_currency,
        'payment_percentage': (total_paid / total_expenses * 100) if total_expenses > 0 else 0,
        'latest_expense': latest_expense,
    }
    
    pagination_data = _pagination_payload(pagination)
    
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.args.get("ajax") == "1"
        or request.accept_mimetypes.best == "application/json"
    )
    if is_ajax:
        try:
            csrf_value = generate_csrf()
            table_html = render_template_string(
                """
{% macro type_details(expense) %}
{% set code = (expense.type.code if expense.type else '')|upper %}
{% set ns = namespace(items=[]) %}
{% if code == 'RENT' %}
  {% if expense.rent_property_address %}{% set ns.items = ns.items + ['عنوان: ' ~ expense.rent_property_address] %}{% endif %}
  {% if expense.rent_property_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.rent_property_notes] %}{% endif %}
{% elif code == 'SOFTWARE' %}
  {% if expense.tech_provider_name %}{% set ns.items = ns.items + ['المزود: ' ~ expense.tech_provider_name] %}{% endif %}
  {% if expense.tech_provider_address %}{% set ns.items = ns.items + ['العنوان: ' ~ expense.tech_provider_address] %}{% endif %}
  {% if expense.tech_provider_phone %}{% set ns.items = ns.items + ['الهاتف: ' ~ expense.tech_provider_phone] %}{% endif %}
  {% if expense.tech_subscription_id %}{% set ns.items = ns.items + ['معرف: ' ~ expense.tech_subscription_id] %}{% endif %}
{% elif code == 'SHIP_STORAGE' %}
  {% if expense.storage_property_address %}{% set ns.items = ns.items + ['الموقع: ' ~ expense.storage_property_address] %}{% endif %}
  {% if expense.storage_expected_days is not none %}{% set ns.items = ns.items + ['المدة: ' ~ expense.storage_expected_days ~ ' يوم'] %}{% endif %}
  {% if expense.storage_start_date %}{% set ns.items = ns.items + ['البداية: ' ~ expense.storage_start_date|format_date] %}{% endif %}
  {% if expense.storage_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.storage_notes] %}{% endif %}
{% elif code in ['SHIP_CLEARANCE','SHIP_CUSTOMS'] %}
  {% if expense.customs_origin %}{% set ns.items = ns.items + ['المنشأ: ' ~ expense.customs_origin] %}{% endif %}
  {% if expense.customs_port_name %}{% set ns.items = ns.items + ['الميناء: ' ~ expense.customs_port_name] %}{% endif %}
  {% if expense.customs_arrival_date %}{% set ns.items = ns.items + ['الوصول: ' ~ expense.customs_arrival_date|format_date] %}{% endif %}
  {% if expense.customs_departure_date %}{% set ns.items = ns.items + ['الخروج: ' ~ expense.customs_departure_date|format_date] %}{% endif %}
  {% if expense.customs_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.customs_notes] %}{% endif %}
{% elif code == 'TRAINING' %}
  {% if expense.training_company_name %}{% set ns.items = ns.items + ['الجهة: ' ~ expense.training_company_name] %}{% endif %}
  {% if expense.training_location %}{% set ns.items = ns.items + ['المكان: ' ~ expense.training_location] %}{% endif %}
  {% if expense.training_duration_days is not none %}{% set ns.items = ns.items + ['المدة: ' ~ expense.training_duration_days ~ ' يوم'] %}{% endif %}
  {% if expense.training_participants_count is not none %}{% set ns.items = ns.items + ['عدد الأفراد: ' ~ expense.training_participants_count] %}{% endif %}
  {% if expense.training_notes %}{% set ns.items = ns.items + ['ملاحظات: ' ~ expense.training_notes] %}{% endif %}
{% elif code == 'ENTERTAINMENT' %}
  {% if expense.entertainment_duration_days is not none %}{% set ns.items = ns.items + ['المدة: ' ~ expense.entertainment_duration_days ~ ' يوم'] %}{% endif %}
  {% if expense.entertainment_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.entertainment_notes] %}{% endif %}
{% elif code == 'BANK_FEES' %}
  {% if expense.bank_fee_bank_name %}{% set ns.items = ns.items + ['البنك: ' ~ expense.bank_fee_bank_name] %}{% endif %}
  {% if expense.bank_fee_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.bank_fee_reference] %}{% endif %}
  {% if expense.bank_fee_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.bank_fee_notes] %}{% endif %}
{% elif code == 'GOV_FEES' %}
  {% if expense.gov_fee_entity_name %}{% set ns.items = ns.items + ['الجهة: ' ~ expense.gov_fee_entity_name] %}{% endif %}
  {% if expense.gov_fee_entity_address %}{% set ns.items = ns.items + ['العنوان: ' ~ expense.gov_fee_entity_address] %}{% endif %}
  {% if expense.gov_fee_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.gov_fee_notes] %}{% endif %}
{% elif code == 'SHIP_PORT_FEES' %}
  {% if expense.port_fee_port_name %}{% set ns.items = ns.items + ['الميناء: ' ~ expense.port_fee_port_name] %}{% endif %}
  {% if expense.port_fee_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.port_fee_reference] %}{% endif %}
  {% if expense.port_fee_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.port_fee_notes] %}{% endif %}
{% elif code == 'SALARY' %}
  {% if expense.period_start and expense.period_end %}{% set ns.items = ns.items + ['الفترة: ' ~ expense.period_start|format_date ~ ' - ' ~ expense.period_end|format_date] %}{% endif %}
  {% if expense.salary_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.salary_reference] %}{% endif %}
  {% if expense.salary_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.salary_notes] %}{% endif %}
{% elif code == 'TRAVEL' %}
  {% if expense.travel_destination %}{% set ns.items = ns.items + ['الوجهة: ' ~ expense.travel_destination] %}{% endif %}
  {% if expense.travel_reason %}{% set ns.items = ns.items + ['الهدف: ' ~ expense.travel_reason] %}{% endif %}
  {% if expense.travel_start_date %}{% set ns.items = ns.items + ['البداية: ' ~ expense.travel_start_date|format_date] %}{% endif %}
  {% if expense.travel_duration_days is not none %}{% set ns.items = ns.items + ['المدة: ' ~ expense.travel_duration_days ~ ' يوم'] %}{% endif %}
  {% if expense.travel_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.travel_notes] %}{% endif %}
{% elif code == 'EMPLOYEE_ADVANCE' %}
  {% if expense.employee_advance_period %}{% set ns.items = ns.items + ['الفترة: ' ~ expense.employee_advance_period] %}{% endif %}
  {% if expense.employee_advance_reason %}{% set ns.items = ns.items + ['السبب: ' ~ expense.employee_advance_reason] %}{% endif %}
  {% if expense.employee_advance_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.employee_advance_notes] %}{% endif %}
{% elif code == 'SHIP_FREIGHT' %}
  {% if expense.shipping_company_name %}{% set ns.items = ns.items + ['الشركة: ' ~ expense.shipping_company_name] %}{% endif %}
  {% if expense.shipping_date %}{% set ns.items = ns.items + ['التاريخ: ' ~ expense.shipping_date|format_date] %}{% endif %}
  {% if expense.shipping_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.shipping_reference] %}{% endif %}
  {% if expense.shipping_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.shipping_notes] %}{% endif %}
  {% if expense.shipping_mode %}{% set ns.items = ns.items + ['الوسيلة: ' ~ expense.shipping_mode] %}{% endif %}
{% elif code == 'MAINTENANCE' %}
  {% if expense.maintenance_provider_name %}{% set ns.items = ns.items + ['الجهة: ' ~ expense.maintenance_provider_name] %}{% endif %}
  {% if expense.maintenance_details %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.maintenance_details] %}{% endif %}
  {% if expense.maintenance_completion_date %}{% set ns.items = ns.items + ['الإنجاز: ' ~ expense.maintenance_completion_date|format_date] %}{% endif %}
{% elif code == 'SHIP_IMPORT_TAX' %}
  {% if expense.import_tax_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.import_tax_reference] %}{% endif %}
  {% if expense.import_tax_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.import_tax_notes] %}{% endif %}
{% elif code == 'HOSPITALITY' %}
  {% if expense.hospitality_type %}{% set ns.items = ns.items + ['النوع: ' ~ expense.hospitality_type] %}{% endif %}
  {% if expense.hospitality_location %}{% set ns.items = ns.items + ['المكان: ' ~ expense.hospitality_location] %}{% endif %}
  {% if expense.hospitality_attendees %}{% set ns.items = ns.items + ['الحضور: ' ~ expense.hospitality_attendees] %}{% endif %}
  {% if expense.hospitality_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.hospitality_notes] %}{% endif %}
{% elif code == 'TELECOM' or code == '' and expense.telecom_phone_number %}
  {% if expense.telecom_phone_number %}{% set ns.items = ns.items + ['الهاتف: ' ~ expense.telecom_phone_number] %}{% endif %}
  {% if expense.telecom_service_type %}{% set ns.items = ns.items + ['الخدمة: ' ~ expense.telecom_service_type] %}{% endif %}
  {% if expense.telecom_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.telecom_notes] %}{% endif %}
{% elif code in ['INSURANCE','INS_OLD','SHIP_INSURANCE'] %}
  {% if expense.insurance_company_name %}{% set ns.items = ns.items + ['الشركة: ' ~ expense.insurance_company_name] %}{% endif %}
  {% if expense.insurance_company_address %}{% set ns.items = ns.items + ['العنوان: ' ~ expense.insurance_company_address] %}{% endif %}
  {% if expense.insurance_company_phone %}{% set ns.items = ns.items + ['الهاتف: ' ~ expense.insurance_company_phone] %}{% endif %}
  {% if expense.insurance_policy_number %}{% set ns.items = ns.items + ['وثيقة: ' ~ expense.insurance_policy_number] %}{% endif %}
  {% if expense.insurance_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.insurance_notes] %}{% endif %}
{% elif code in ['OFFICE','OFFICE_OLD'] %}
  {% if expense.office_supplier_name %}{% set ns.items = ns.items + ['المورد: ' ~ expense.office_supplier_name] %}{% endif %}
  {% if expense.office_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.office_notes] %}{% endif %}
  {% if expense.office_purchase_reference %}{% set ns.items = ns.items + ['مرجع: ' ~ expense.office_purchase_reference] %}{% endif %}
{% elif code in ['HOME_EXPENSE','HOME_OLD'] %}
  {% if expense.home_address %}{% set ns.items = ns.items + ['العنوان: ' ~ expense.home_address] %}{% endif %}
  {% if expense.home_owner_name %}{% set ns.items = ns.items + ['المالك: ' ~ expense.home_owner_name] %}{% endif %}
  {% if expense.home_relation_to_company %}{% set ns.items = ns.items + ['العلاقة: ' ~ expense.home_relation_to_company] %}{% endif %}
  {% if expense.home_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.home_notes] %}{% endif %}
{% elif code == 'PARTNER_EXPENSE' %}
  {% if expense.partner and expense.partner.name %}{% set ns.items = ns.items + ['الشريك: ' ~ expense.partner.name] %}{% endif %}
  {% if expense.partner_expense_reason %}{% set ns.items = ns.items + ['السبب: ' ~ expense.partner_expense_reason] %}{% endif %}
  {% if expense.partner_expense_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.partner_expense_notes] %}{% endif %}
{% elif code == 'SUPPLIER_EXPENSE' %}
  {% if expense.supplier and expense.supplier.name %}{% set ns.items = ns.items + ['المورد: ' ~ expense.supplier.name] %}{% endif %}
  {% if expense.supplier_expense_reason %}{% set ns.items = ns.items + ['السبب: ' ~ expense.supplier_expense_reason] %}{% endif %}
  {% if expense.supplier_expense_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.supplier_expense_notes] %}{% endif %}
{% elif code == 'SHIP_HANDLING' %}
  {% if expense.handling_quantity is not none %}{% set ns.items = ns.items + ['الكمية: ' ~ expense.handling_quantity] %}{% endif %}
  {% if expense.handling_unit %}{% set ns.items = ns.items + ['الوحدة: ' ~ expense.handling_unit] %}{% endif %}
  {% if expense.handling_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.handling_notes] %}{% endif %}
{% elif code == 'FUEL' %}
  {% if expense.fuel_vehicle_number %}{% set ns.items = ns.items + ['المركبة: ' ~ expense.fuel_vehicle_number] %}{% endif %}
  {% if expense.fuel_driver_name %}{% set ns.items = ns.items + ['السائق: ' ~ expense.fuel_driver_name] %}{% endif %}
  {% if expense.fuel_usage_type %}{% set ns.items = ns.items + ['الغرض: ' ~ expense.fuel_usage_type] %}{% endif %}
  {% if expense.fuel_volume is not none %}{% set ns.items = ns.items + ['الكمية: ' ~ expense.fuel_volume] %}{% endif %}
  {% if expense.fuel_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.fuel_notes] %}{% endif %}
{% elif code == 'TRANSPORT' %}
  {% if expense.transport_beneficiary_name %}{% set ns.items = ns.items + ['المستفيد: ' ~ expense.transport_beneficiary_name] %}{% endif %}
  {% if expense.transport_reason %}{% set ns.items = ns.items + ['السبب: ' ~ expense.transport_reason] %}{% endif %}
  {% if expense.transport_usage_type %}{% set ns.items = ns.items + ['التصنيف: ' ~ expense.transport_usage_type] %}{% endif %}
  {% if expense.transport_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.transport_notes] %}{% endif %}
{% elif code == 'CONSULTING' %}
  {% if expense.legal_company_name %}{% set ns.items = ns.items + ['الشركة: ' ~ expense.legal_company_name] %}{% endif %}
  {% if expense.legal_company_address %}{% set ns.items = ns.items + ['العنوان: ' ~ expense.legal_company_address] %}{% endif %}
  {% if expense.legal_case_number %}{% set ns.items = ns.items + ['رقم القضية: ' ~ expense.legal_case_number] %}{% endif %}
  {% if expense.legal_case_type %}{% set ns.items = ns.items + ['نوع القضية: ' ~ expense.legal_case_type] %}{% endif %}
  {% if expense.legal_case_notes %}{% set ns.items = ns.items + ['تفاصيل: ' ~ expense.legal_case_notes] %}{% endif %}
{% endif %}
{% if not ns.items %}
  {% if expense.description %}{% set ns.items = ns.items + [expense.description] %}{% endif %}
  {% if expense.notes %}{% set ns.items = ns.items + [expense.notes] %}{% endif %}
{% endif %}
{{ ', '.join(ns.items) if ns.items else '—' }}
{% endmacro %}
<table id="expenses-table" class="table table-striped table-bordered align-middle table-sticky">
  <thead class="table-primary text-center">
    <tr>
      <th>التاريخ</th>
      <th>النوع</th>
      <th>تفاصيل النوع</th>
      <th>الجهة</th>
      <th>المبلغ</th>
      <th>العملة</th>
      <th>طريقة الدفع</th>
      <th>المدفوع</th>
      <th>الحالة</th>
      <th style="width:170px" data-sortable="false">إجراءات</th>
    </tr>
  </thead>
  <tbody>
    {% for e in expenses %}
    {% set pt = e.payee_type or '' %}
    <tr>
      <td class="text-nowrap" data-sort-value="{{ e.date.isoformat() if e.date else '' }}">{{ e.date|format_date }}</td>
      <td>{{ e.type.name if e.type else '—' }}</td>
      <td class="text-truncate" style="max-width:260px">{{ type_details(e) }}</td>
      <td class="text-truncate" style="max-width:200px">
        {% if pt == 'EMPLOYEE' %}<span class="payee-chip payee-chip--employee">موظّف</span>
        {% elif pt == 'UTILITY' %}<span class="payee-chip payee-chip--utility">مرفق</span>
        {% elif pt %}<span class="payee-chip payee-chip--other">أخرى</span>{% endif %}
        <span class="fw-bold text-dark">{{ e.payee_name or e.paid_to or (e.employee.name if e.employee else '—') }}</span>
      </td>
      <td class="fw-bold text-end" data-sort-value="{{ e.amount or 0 }}">
        {{ e.amount|number_format(2) }}
      </td>
      <td class="text-center"><span class="badge badge-secondary">{{ e.currency or 'ILS' }}</span></td>
      <td class="text-nowrap">{{ e.payment_method or '—' }}</td>
      <td class="text-end" data-sort-value="{{ e.total_paid or 0 }}">{{ (e.total_paid or 0)|float|round(2)|number_format(2) }}</td>
      <td class="text-center" data-sort-value="{{ 0 if e.is_paid else (e.balance or 0) }}">
        {% if e.is_paid %}
          <span class="badge bg-success">مدفوع بالكامل</span>
        {% else %}
          <div class="fw-bold text-danger">{{ (e.balance or 0)|float|round(2)|number_format(2) }}</div>
        {% endif %}
      </td>
      <td class="text-nowrap text-center">
        <div class="btn-group">
          <a href="{{ url_for('expenses_bp.detail', exp_id=e.id) }}" class="btn btn-sm btn-info" title="تفاصيل"><i class="fas fa-eye"></i></a>
          {% if current_user.has_permission('manage_expenses') %}
            <a href="{{ url_for('expenses_bp.edit', exp_id=e.id) }}" class="btn btn-sm btn-warning" title="تعديل"><i class="fas fa-edit"></i></a>
            {% if e.is_archived %}
            <button type="button" class="btn btn-action-restore btn-action-sm" title="استعادة" onclick="restoreExpense({{ e.id }})">
              <i class="fas fa-undo"></i>
            </button>
            {% else %}
            <button type="button" class="btn btn-action-archive btn-action-sm" title="أرشفة" onclick="archiveExpense({{ e.id }})">
              <i class="fas fa-archive"></i>
            </button>
            {% endif %}
            <form method="post" action="{{ url_for('expenses_bp.delete', exp_id=e.id) }}" onsubmit="return confirm('حذف المصروف؟');" class="d-inline">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <button class="btn btn-sm btn-danger" title="حذف عادي"><i class="fas fa-trash"></i></button>
            </form>
            
          {% endif %}
          {% if current_user.has_permission('manage_payments') and not e.is_paid and e.balance and e.balance > 0 %}
            <a href="{{ url_for('expenses_bp.pay', exp_id=e.id) }}" class="btn btn-sm btn-outline-success" title="دفع ({{ '%.2f'|format(e.balance) }} ₪)"><i class="fas fa-money-bill-wave"></i></a>
          {% endif %}
        </div>
      </td>
    </tr>
    {% endfor %}
  </tbody>
  <tfoot>
    {# … نفس الإجماليات … #}
  </tfoot>
</table>
            """,
            expenses=expenses,
            current_user=current_user,
            csrf_token=csrf_value,
        )
            summary_html = render_template_string(
                """
<div id="expenses-summary-wrapper">
{% if summary %}
  <div class="summary-cards mb-4 no-print">
    <div class="summary-card summary-card--total">
      <div class="summary-card__row">
        <div>
          <h6>💰 إجمالي النفقات</h6>
          <h3>{{ "{:,.2f}".format(summary.total_expenses) }} ₪</h3>
          <small>{{ summary.expenses_count }} مصروف</small>
        </div>
        <i class="fas fa-receipt summary-card__icon"></i>
      </div>
    </div>
    <div class="summary-card summary-card--count">
      <div class="summary-card__row">
        <div>
          <h6>🧾 عدد المصاريف</h6>
          <h3>{{ summary.expenses_count }}</h3>
          <small>ضمن التصفية الحالية</small>
        </div>
        <i class="fas fa-list-ol summary-card__icon"></i>
      </div>
    </div>
    <div class="summary-card summary-card--average">
      <div class="summary-card__row">
        <div>
          <h6>📊 متوسط المصروف</h6>
          <h3>{{ "{:,.2f}".format(summary.average_expense) }} ₪</h3>
          <small>لكل مصروف</small>
        </div>
        <i class="fas fa-chart-line summary-card__icon"></i>
      </div>
    </div>
    {% set latest = summary.latest_expense %}
    <div class="summary-card summary-card--latest">
      <div class="summary-card__row">
        <div>
          <h6>🆕 آخر مصروف</h6>
          {% if latest %}
          <h3>{{ latest.amount|number_format(2) }} {{ latest.currency or 'ILS' }}</h3>
          <small>{{ latest.date|format_date }} — {{ latest.type.name if latest.type else 'غير مصنف' }}</small>
          {% else %}
          <h3>—</h3>
          <small>لا يوجد بيانات</small>
          {% endif %}
        </div>
        <i class="fas fa-clock summary-card__icon"></i>
      </div>
      {% if latest %}
      <div class="latest-meta">
        <div class="fw-semibold">{{ latest.payee_name or latest.paid_to or 'غير محدد' }}</div>
        <div class="text-uppercase">{{ latest.payment_method or '—' }}</div>
      </div>
      {% endif %}
    </div>
  </div>

  <div class="row mb-4 no-print">
    <div class="col-md-6">
      <div class="card">
        <div class="card-header bg-primary text-white">
          <h5 class="mb-0">📊 التصنيف حسب النوع</h5>
        </div>
        <div class="card-body">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>النوع</th>
                <th>العدد</th>
                <th>المبلغ (₪)</th>
                <th>النسبة</th>
              </tr>
            </thead>
            <tbody>
              {% for type_name, data in summary.expenses_by_type[:5] %}
              <tr>
                <td><strong>{{ type_name }}</strong></td>
                <td>{{ data.count }}</td>
                <td>{{ "{:,.2f}".format(data.amount) }}</td>
                <td>
                  {% set percentage = (data.amount / summary.total_expenses * 100) if summary.total_expenses > 0 else 0 %}
                  <div class="progress" style="height: 20px;">
                    <div class="progress-bar bg-danger" role="progressbar" style="width: {{ percentage }}%">
                      {{ "{:.1f}".format(percentage) }}%
                    </div>
                  </div>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-md-6">
      <div class="card">
        <div class="card-header bg-info text-white">
          <h5 class="mb-0">💱 التصنيف حسب العملة</h5>
        </div>
        <div class="card-body">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>العملة</th>
                <th>العدد</th>
                <th>المبلغ الأصلي</th>
                <th>بالشيقل</th>
              </tr>
            </thead>
            <tbody>
              {% for currency, data in summary.expenses_by_currency.items() %}
              <tr>
                <td><strong>{{ currency }}</strong></td>
                <td>{{ data.count }}</td>
                <td>{{ "{:,.2f}".format(data.amount) }}</td>
                <td>{{ "{:,.2f}".format(data.amount_ils) }} ₪</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
{% endif %}
            </div>
                """,
                summary=summary,
            )
        except Exception as exc:
            current_app.logger.exception("Expenses AJAX rendering failed: %s", exc)
            return jsonify({"error": str(exc)}), 500
        else:
            return jsonify(
                {
                    "table_html": table_html,
                    "summary_html": summary_html,
                    "total_filtered": pagination.total,
                    "pagination": pagination_data,
                }
            )
    
    return render_template(
        "expenses/expenses_list.html",
        expenses=expenses,
        search=filt["q"],
        start=filt["start"],
        end=filt["end"],
        type_id=filt["type_id"],
        employee_id=filt["employee_id"],
        shipment_id=filt["shipment_id"],
        utility_account_id=filt["utility_account_id"],
        stock_adjustment_id=filt["stock_adjustment_id"],
        payee_type=filt["payee_type"],
        show_archived=filt["show_archived"],
        summary=summary,
        pagination=pagination,
        pagination_data=pagination_data,
    )

@expenses_bp.route("/<int:exp_id>", methods=["GET"], endpoint="detail")
@login_required
def detail(exp_id):
    exp = _get_or_404(
        Expense,
        exp_id,
        joinedload(Expense.type),
        joinedload(Expense.employee),
        joinedload(Expense.customer),
        joinedload(Expense.shipment),
        joinedload(Expense.utility_account),
        joinedload(Expense.stock_adjustment),
        joinedload(Expense.payments)
        .joinedload(Payment.splits),
    )

    def _coerce_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, _date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            v = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(v)
            except Exception:
                return None
        return None

    def _method_label(value):
        method_key = value.value if hasattr(value, "value") else value
        mapping = {
            "CASH": "نقد",
            "CHEQUE": "شيك",
            "CARD": "بطاقة",
            "BANK": "تحويل بنكي",
            "ONLINE": "دفع إلكتروني",
        }
        return mapping.get((method_key or "").upper(), method_key or "غير محدد")

    payment_rows = []
    method_labels = []
    for p in exp.payments or []:
        payment_method = _method_label(p.method)
        # ✅ إذا كانت الدفعة لديها splits، نعرض كل split كدفعة منفصلة
        if p.splits:
            for split in sorted(p.splits, key=lambda s: getattr(s, "id", 0)):
                details = split.details or {}
                if isinstance(details, str):
                    try:
                        import json
                        details = json.loads(details)
                    except:
                        details = {}
                check_number = details.get("check_number") or p.check_number
                check_bank = details.get("check_bank") or p.check_bank
                check_due = details.get("check_due_date") or p.check_due_date
                method_label = _method_label(split.method)
                method_labels.append(method_label)
                
                # ✅ جلب معلومات الشيك المرتبط بـ split (إن وجد)
                split_check = None
                split_check_status = None
                if 'check' in (str(split.method) or '').lower() or 'cheque' in (str(split.method) or '').lower():
                    from models import Check
                    from sqlalchemy import or_
                    split_checks = Check.query.filter(
                        or_(
                            Check.reference_number == f"PMT-SPLIT-{split.id}",
                            Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                        )
                    ).all()
                    if split_checks:
                        split_check = split_checks[0]
                        split_check_status = str(getattr(split_check, 'status', 'PENDING') or 'PENDING')
                        # استخدام معلومات الشيك من Check record إذا كانت متوفرة
                        if not check_number:
                            check_number = split_check.check_number
                        if not check_bank:
                            check_bank = split_check.check_bank
                        if not check_due:
                            check_due = split_check.check_due_date
                
                # ✅ حساب المبلغ المحول للـ ILS
                split_amount = split.amount or 0
                split_converted_amount = split.converted_amount or 0
                split_currency = split.currency or p.currency or "ILS"
                converted_currency = split.converted_currency or p.currency or "ILS"
                
                # استخدام المبلغ المحول إذا كان موجوداً
                if split_converted_amount > 0 and converted_currency == "ILS":
                    amount_to_display = split_converted_amount
                else:
                    amount_to_display = split_amount
                
                payment_rows.append(
                    {
                        "date": p.payment_date,
                        "amount": amount_to_display,
                        "currency": split_currency,
                        "converted_amount": split_converted_amount if converted_currency == "ILS" else None,
                        "converted_currency": converted_currency,
                        "status": split_check_status if split_check_status else p.status,
                        "number": f"SPLIT-{split.id}-PMT-{p.payment_number or p.id}",  # ✅ رقم يميز كل split
                        "payment_id": p.id,
                        "split_id": split.id,  # ✅ إضافة split_id لتمييز كل split
                        "method": method_label,
                        "check_number": check_number,
                        "check_bank": check_bank,
                        "check_due_date": _coerce_datetime(check_due),
                        "is_split": True,  # ✅ علامة أن هذا split
                        "check_status": split_check_status,  # ✅ حالة الشيك المرتبط
                    }
                )
        else:
            # ✅ الدفعة بدون splits - نعرضها كالمعتاد
            method_labels.append(payment_method)
            payment_rows.append(
                {
                    "date": p.payment_date,
                    "amount": p.total_amount,
                    "currency": p.currency,
                    "status": p.status,
                    "number": p.payment_number or p.id,
                    "payment_id": p.id,
                    "split_id": None,  # ✅ بدون split
                    "method": payment_method,
                    "check_number": p.check_number,
                    "check_bank": p.check_bank,
                    "check_due_date": _coerce_datetime(p.check_due_date),
                    "is_split": False,  # ✅ علامة أن هذا ليس split
                }
            )

    payment_rows.sort(key=lambda row: row["date"] or datetime.min)
    methods_summary = ", ".join(dict.fromkeys(m for m in method_labels if m))

    return render_template("expenses/detail.html", expense=exp, payment_rows=payment_rows, payment_methods_summary=methods_summary)

@expenses_bp.route("/add", methods=["GET", "POST"], endpoint="create_expense")
@login_required
def add():
    from models import Branch, Site
    
    raw_mode = (request.args.get("mode") or request.form.get("service_mode") or "").strip().lower()
    supplier_service_mode = raw_mode == "supplier_service"
    partner_service_mode = raw_mode == "partner_service"
    prefill_supplier_id = request.args.get("supplier_id", type=int)
    if prefill_supplier_id is None:
        try:
            prefill_supplier_id = int((request.form.get("prefill_supplier_id") or "").strip() or 0) or None
        except (TypeError, ValueError, AttributeError):
            prefill_supplier_id = None
    service_supplier = Supplier.query.get(prefill_supplier_id) if prefill_supplier_id else None
    prefill_partner_id = request.args.get("partner_id", type=int)
    if prefill_partner_id is None:
        try:
            prefill_partner_id = int((request.form.get("prefill_partner_id") or "").strip() or 0) or None
        except (TypeError, ValueError, AttributeError):
            prefill_partner_id = None
    service_partner = Partner.query.get(prefill_partner_id) if prefill_partner_id else None

    form = ExpenseForm()
    _types = ExpenseType.query.filter_by(is_active=True).order_by(ExpenseType.name).all()
    types_list = [{'id': t.id, 'name': t.name, 'code': t.code, 'fields_meta': t.fields_meta} for t in _types]
    form.type_id.choices = [(t.id, t.name) for t in _types]
    supplier_service_type_id = None
    partner_service_type_id = None
    if supplier_service_mode:
        supplier_service_type_id = next(
            (t["id"] for t in types_list if (t.get("code") or "").upper() == "SUPPLIER_EXPENSE"),
            None,
        )
        if supplier_service_type_id:
            form.type_id.data = supplier_service_type_id
    if partner_service_mode:
        partner_service_type_id = next(
            (t["id"] for t in types_list if (t.get("code") or "").upper() == "PARTNER_EXPENSE"),
            None,
        )
        if partner_service_type_id:
            form.type_id.data = partner_service_type_id
    try:
        form.branch_id.choices = [(b.id, f"{b.code} - {b.name}") for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all()]
        form.site_id.choices = [(0, '-- بدون موقع --')] + [
            (s.id, f"{s.code} - {s.name}") for s in Site.query.filter_by(is_active=True).order_by(Site.name).all()
        ]
    except Exception:
        form.branch_id.choices = []
        form.site_id.choices = [(0, '-- بدون موقع --')]
    form.employee_id.choices = [(0, '-- اختر موظفاً --')] + [(e.id, e.name) for e in Employee.query.order_by(Employee.name).limit(200).all()]
    form.utility_account_id.choices = [(0, '-- اختر حساب --')] + [(u.id, f"{u.provider} - {u.account_no or u.alias or u.utility_type}") for u in UtilityAccount.query.filter_by(is_active=True).order_by(UtilityAccount.provider).limit(100).all()]
    form.warehouse_id.choices = [(0, '-- اختر مستودع --')] + [(w.id, w.name) for w in Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).limit(100).all()]
    form.partner_id.choices = [(0, '-- اختر شريك --')] + [(p.id, p.name) for p in Partner.query.filter_by(is_archived=False).order_by(Partner.name).limit(100).all()]
    form.supplier_id.choices = [(0, '-- اختر مورد --')] + [(s.id, s.name) for s in Supplier.query.filter_by(is_archived=False).order_by(Supplier.name).limit(100).all()]
    if service_supplier and all(choice_id != service_supplier.id for choice_id, _ in form.supplier_id.choices):
        form.supplier_id.choices.append((service_supplier.id, f"✓ {service_supplier.name}"))
    if service_supplier:
        form.supplier_id.data = service_supplier.id
    if service_partner and all(choice_id != service_partner.id for choice_id, _ in form.partner_id.choices):
        form.partner_id.choices.append((service_partner.id, f"✓ {service_partner.name}"))
    if service_partner:
        form.partner_id.data = service_partner.id
    customers_query = Customer.query
    if hasattr(Customer, 'is_archived'):
        customers_query = customers_query.filter_by(is_archived=False)
    customers = customers_query.order_by(Customer.name).limit(100).all()
    form.customer_id.choices = [(0, '-- اختر عميل --')] + [(c.id, c.name) for c in customers]
    form.shipment_id.choices = [(0, '-- اختر شحنة --')] + [(s.id, f"شحنة #{s.id}") for s in Shipment.query.order_by(Shipment.id.desc()).limit(50).all()]
    form.stock_adjustment_id.choices = [(0, '-- اختر تسوية --')] + [(sa.id, f"تسوية #{sa.id}") for sa in StockAdjustment.query.order_by(StockAdjustment.id.desc()).limit(50).all()]
    
    types_meta = {t.id: _merge_type_meta(t) for t in _types}
    render_kwargs = {
        "service_mode": supplier_service_mode or partner_service_mode,
        "service_supplier": service_supplier,
        "service_partner": service_partner,
        "supplier_service_type_id": supplier_service_type_id,
        "partner_service_type_id": partner_service_type_id,
    }

    if form.validate_on_submit():
        exp = Expense()
        if hasattr(form, "apply_to"):
            form.apply_to(exp)
        else:
            form.populate_obj(exp)
            if hasattr(form, "date"):
                dt = _to_datetime(form.date.data)
                if dt:
                    exp.date = dt
            
            if not exp.branch_id or exp.branch_id == 0:
                flash("⚠️ يرجى اختيار الفرع من القائمة", "warning")
                return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs)
            
            if not exp.amount or exp.amount <= 0:
                flash("⚠️ يرجى إدخال مبلغ المصروف", "warning")
                return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs)
            
            if not exp.disbursed_by or exp.disbursed_by.strip() == '':
                flash("⚠️ يرجى إدخال اسم الشخص الذي سلم المال", "warning")
                return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs)
            
            if not getattr(form.employee_id, "data", None) or form.employee_id.data == 0:
                exp.employee_id = None
            if not getattr(form, "utility_account_id", None) or form.utility_account_id.data == 0:
                exp.utility_account_id = None
            if not getattr(form, "warehouse_id", None) or form.warehouse_id.data == 0:
                exp.warehouse_id = None
            if not getattr(form, "shipment_id", None) or form.shipment_id.data == 0:
                exp.shipment_id = None
            if not getattr(form, "stock_adjustment_id", None) or form.stock_adjustment_id.data == 0:
                exp.stock_adjustment_id = None

        partial_payload_raw = request.form.get("partial_payments_payload")
        partial_entries = _parse_partial_payments_payload(
            partial_payload_raw,
            form.date.data or datetime.utcnow(),
            (form.currency.data or exp.currency or "ILS"),
        )

        try:
            etype = ExpenseType.query.get(int(form.type_id.data)) if getattr(form, 'type_id', None) else None
            meta = (etype.fields_meta or {}) if etype else {}
            required = set((meta.get('required') or []))
            missing = []
            def _is_empty(v):
                return v in (None, '', 0, '0')
            if 'employee_id' in required and _is_empty(exp.employee_id):
                missing.append('الموظف')
            if 'period' in required and _is_empty(exp.period_start) and _is_empty(exp.period_end):
                missing.append('الفترة')
            if 'utility_account_id' in required and _is_empty(exp.utility_account_id):
                missing.append('حساب المرفق')
            if 'warehouse_id' in required and _is_empty(exp.warehouse_id):
                missing.append('المستودع')
            if 'shipment_id' in required and _is_empty(exp.shipment_id):
                missing.append('رقم الشحنة')
            if 'beneficiary_name' in required and _is_empty(exp.beneficiary_name):
                missing.append('الجهة/الغرض')

            if missing:
                errs = '، '.join(missing)
                flash(f"❌ حقول إلزامية مفقودة: {errs}", 'danger')
                raise ValueError('missing required fields')
        except Exception:
            return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs), 400
        try:
            etype = ExpenseType.query.get(exp.type_id) if exp.type_id else None
            if etype and etype.code == 'SALARY' and exp.employee_id:
                emp = Employee.query.get(exp.employee_id)
                if emp:
                    suggested_net = float(emp.net_salary or 0)
                    if abs(float(exp.amount) - float(emp.salary or 0)) < 0.01:
                        exp.amount = suggested_net
                        current_app.logger.info(f"✅ تم تعديل راتب الموظف #{emp.id} تلقائياً للصافي: {suggested_net}")
        except Exception as e:
            current_app.logger.warning(f"⚠️ فشل حساب الراتب الصافي التلقائي: {e}")
        
        db.session.add(exp)
        db.session.flush()
        try:
            _create_partial_payments(exp, partial_entries)
        except ValueError as perr:
            db.session.rollback()
            flash(str(perr), "danger")
            return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs)
        
        try:
            db.session.commit()
            flash("✅ تمت إضافة المصروف بنجاح", "success")
            
            try:
                from models import EmployeeAdvanceInstallment
                from dateutil.relativedelta import relativedelta
                
                etype = ExpenseType.query.get(exp.type_id) if exp.type_id else None
                if etype and etype.code == 'EMPLOYEE_ADVANCE' and exp.employee_id:
                    installments_count = int(getattr(form, 'installments_count', None).data or 1)
                    if installments_count > 1:
                        installment_amt = float(exp.amount) / installments_count
                        start_month = exp.date.date() if isinstance(exp.date, datetime) else exp.date
                        for i in range(1, installments_count + 1):
                            due = start_month + relativedelta(months=i)
                            inst = EmployeeAdvanceInstallment(
                                employee_id=exp.employee_id,
                                advance_expense_id=exp.id,
                                installment_number=i,
                                total_installments=installments_count,
                                amount=installment_amt,
                                currency=exp.currency,
                                due_date=due,
                                paid=False,
                            )
                            db.session.add(inst)
                        db.session.commit()
                        current_app.logger.info(f"✅ أقساط السلفة {exp.id}: {installments_count} قسط")
            except Exception as e:
                current_app.logger.error(f"❌ فشل إنشاء أقساط السلفة: {e}")
            
            try:
                from models import EmployeeDeduction
                create_ded = getattr(form, 'create_deduction', None)
                if create_ded and create_ded.data and exp.employee_id:
                    ded = EmployeeDeduction(
                        employee_id=exp.employee_id,
                        deduction_type=etype.name if etype else 'أخرى',
                        amount=exp.amount,
                        currency=exp.currency,
                        start_date=exp.date.date() if isinstance(exp.date, datetime) else exp.date,
                        end_date=exp.period_end if exp.period_end else None,
                        is_active=True,
                        notes=exp.description or '',
                        expense_id=exp.id,
                    )
                    db.session.add(ded)
                    db.session.commit()
                    current_app.logger.info(f"✅ خصم شهري لموظف {exp.employee_id} من مصروف {exp.id}")
            except Exception as e:
                current_app.logger.error(f"❌ فشل إنشاء خصم شهري: {e}")
            
            try:
                if exp.payment_method and exp.payment_method.lower() in ['check', 'cheque']:
                    check_number = (exp.check_number or '').strip()
                    check_bank = (exp.check_bank or '').strip()
                    if not check_number or not check_bank:
                        current_app.logger.warning(f"⚠️ مصروف {exp.id} بطريقة شيك لكن بدون رقم شيك أو بنك")
                    else:
                        check_due = exp.check_due_date or exp.date or datetime.utcnow()
                        _, created = create_check_record(
                            amount=exp.amount,
                            check_number=check_number,
                            check_bank=check_bank,
                            check_date=exp.date or datetime.utcnow(),
                            check_due_date=check_due,
                            currency=exp.currency or 'ILS',
                            direction='OUT',
                            customer_id=getattr(exp, 'customer_id', None),
                            supplier_id=getattr(exp, 'supplier_id', None),
                            partner_id=getattr(exp, 'partner_id', None),
                            reference_number=f"EXP-{exp.id}",
                            notes=f"شيك من مصروف رقم {exp.id} - {exp.description[:50] if exp.description else 'مصروف'}",
                            payee_name=exp.payee_name or exp.paid_to or exp.beneficiary_name,
                            created_by_id=current_user.id if current_user.is_authenticated else None,
                            status='PENDING'
                        )
                        if created:
                            db.session.commit()
                            current_app.logger.info(f"✅ تم إنشاء سجل شيك من مصروف رقم {exp.id}")
            except Exception as e:
                current_app.logger.error(f"❌ فشل إنشاء سجل شيك من مصروف {exp.id}: {str(e)}")
                db.session.commit()
            
            return redirect(url_for("expenses_bp.list_expenses"))
        except Exception as err:
            db.session.rollback()
            error_msg = str(err).lower()
            
            if "foreign key mismatch" in error_msg:
                flash("⚠️ يوجد خطأ في إعدادات قاعدة البيانات - يرجى التواصل مع الدعم الفني", "warning")
                current_app.logger.error(f"Foreign key mismatch في المصروفات: {err}")
            elif "foreign key" in error_msg:
                flash("❌ خطأ في ربط البيانات - يرجى التأكد من اختيار جميع الحقول المطلوبة", "danger")
            elif "not null" in error_msg or "cannot be null" in error_msg:
                flash("❌ يرجى تعبئة جميع الحقول الإلزامية (الفرع، المبلغ، التاريخ)", "danger")
            elif "unique" in error_msg:
                flash("❌ هذا المصروف مسجل مسبقاً", "danger")
            elif "null identity key" in error_msg:
                flash("❌ خطأ في حفظ البيانات - يرجى المحاولة مرة أخرى", "danger")
                current_app.logger.error(f"NULL identity key في المصروف: {err}")
            else:
                flash("❌ حدث خطأ غير متوقع - يرجى المحاولة مرة أخرى أو التواصل مع الدعم", "danger")
            
            current_app.logger.error(f"خطأ في إضافة مصروف: {err}")
    
    return _render_expense_form(form, is_edit=False, types_meta=types_meta, types_list=types_list, **render_kwargs)


@expenses_bp.route("/quick-supplier-service", methods=["POST"], endpoint="quick_supplier_service")
@login_required
def quick_supplier_service():
    if not request.is_json:
        return jsonify({"success": False, "message": "payload_required"}), 400
    data = request.get_json(silent=True) or {}
    supplier_id = data.get("supplier_id")
    try:
        supplier_id = int(supplier_id or 0)
    except (TypeError, ValueError):
        supplier_id = 0
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({"success": False, "message": "supplier_not_found"}), 404
    amount = D(str(data.get("amount") or 0))
    if amount <= 0:
        return jsonify({"success": False, "message": "invalid_amount"}), 400
    currency = ensure_currency(data.get("currency"), supplier.currency or "ILS")
    description = (data.get("description") or "").strip()
    branch_id = data.get("branch_id")
    try:
        branch_id = int(branch_id or 0)
    except (TypeError, ValueError):
        branch_id = 0
    if not branch_id:
        branch_id = _default_expense_branch_id()
    branch = Branch.query.get(branch_id) if branch_id else None
    if not branch:
        return jsonify({"success": False, "message": "branch_not_found"}), 400
    supplier_type = (
        ExpenseType.query.filter(func.upper(ExpenseType.code) == "SUPPLIER_EXPENSE")
        .order_by(ExpenseType.id.asc())
        .first()
    )
    if not supplier_type:
        return jsonify({"success": False, "message": "supplier_type_missing"}), 400
    exp = Expense()
    exp.date = datetime.utcnow()
    exp.amount = amount
    exp.currency = currency
    exp.branch_id = branch.id
    exp.type_id = supplier_type.id
    exp.supplier_id = supplier.id
    exp.payee_type = "SUPPLIER"
    exp.payee_entity_id = supplier.id
    exp.payee_name = supplier.name
    exp.beneficiary_name = supplier.name
    exp.paid_to = supplier.name
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "name", None) or getattr(current_user, "username", None) or "المحاسب"
    exp.disbursed_by = user_name
    exp.description = description or "فاتورة خدمة"
    exp.notes = description or None
    exp.payment_method = "cash"
    exp.payment_details = None
    db.session.add(exp)
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "expense_id": exp.id,
            "expense_url": url_for("expenses_bp.edit", exp_id=exp.id),
            "amount": float(amount),
            "currency": currency,
            "supplier_name": supplier.name,
        }
    )


@expenses_bp.route("/quick-supplier-service/pay", methods=["POST"], endpoint="quick_supplier_service_pay")
@login_required
def quick_supplier_service_pay():
    if not request.is_json:
        return jsonify({"success": False, "message": "payload_required"}), 400
    data = request.get_json(silent=True) or {}
    expense_id = data.get("expense_id")
    try:
        expense_id = int(expense_id or 0)
    except (TypeError, ValueError):
        expense_id = 0
    expense = Expense.query.get(expense_id)
    if not expense:
        return jsonify({"success": False, "message": "expense_not_found"}), 404
    amount = D(str(data.get("amount") or 0))
    if amount <= 0:
        return jsonify({"success": False, "message": "invalid_amount"}), 400
    currency = ensure_currency(data.get("currency"), expense.currency or "ILS")
    if currency != (expense.currency or "ILS"):
        return jsonify({"success": False, "message": "currency_mismatch"}), 400
    method_raw = (data.get("method") or "cash").strip().lower()
    allowed_methods = {m.value for m in PaymentMethod}
    if method_raw not in allowed_methods:
        return jsonify({"success": False, "message": "invalid_method"}), 400
    reference = (data.get("reference") or "").strip()
    notes = (data.get("notes") or "").strip()
    entries = [
        {
            "amount": amount.quantize(Decimal("0.01")),
            "method": method_raw,
            "payment_date": datetime.utcnow(),
            "reference": reference,
            "notes": notes,
            "currency": currency,
            "details": {},
        }
    ]
    try:
        _create_partial_payments(expense, entries)
        db.session.commit()
    except ValueError as err:
        db.session.rollback()
        return jsonify({"success": False, "message": str(err) or "payment_error"}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "payment_error"}), 400
    return jsonify(
        {
            "success": True,
            "expense_id": expense.id,
            "expense_url": url_for("expenses_bp.edit", exp_id=expense.id),
        }
    )


@expenses_bp.route("/quick-partner-service", methods=["POST"], endpoint="quick_partner_service")
@login_required
def quick_partner_service():
    if not request.is_json:
        return jsonify({"success": False, "message": "payload_required"}), 400
    data = request.get_json(silent=True) or {}
    partner_id = data.get("partner_id")
    try:
        partner_id = int(partner_id or 0)
    except (TypeError, ValueError):
        partner_id = 0
    partner = Partner.query.get(partner_id)
    if not partner:
        return jsonify({"success": False, "message": "partner_not_found"}), 404
    amount = D(str(data.get("amount") or 0))
    if amount <= 0:
        return jsonify({"success": False, "message": "invalid_amount"}), 400
    currency = ensure_currency(data.get("currency"), partner.currency or "ILS")
    description = (data.get("description") or "").strip()
    branch_id = data.get("branch_id")
    try:
        branch_id = int(branch_id or 0)
    except (TypeError, ValueError):
        branch_id = 0
    if not branch_id:
        branch_id = _default_expense_branch_id()
    branch = Branch.query.get(branch_id) if branch_id else None
    if not branch:
        return jsonify({"success": False, "message": "branch_not_found"}), 400
    partner_type = (
        ExpenseType.query.filter(func.upper(ExpenseType.code) == "PARTNER_EXPENSE")
        .order_by(ExpenseType.id.asc())
        .first()
    )
    if not partner_type:
        return jsonify({"success": False, "message": "partner_type_missing"}), 400
    exp = Expense()
    exp.date = datetime.utcnow()
    exp.amount = amount
    exp.currency = currency
    exp.branch_id = branch.id
    exp.type_id = partner_type.id
    exp.partner_id = partner.id
    exp.payee_type = "PARTNER"
    exp.payee_entity_id = partner.id
    exp.payee_name = partner.name
    exp.beneficiary_name = partner.name
    exp.paid_to = partner.name
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "name", None) or getattr(current_user, "username", None) or "المحاسب"
    exp.disbursed_by = user_name
    exp.description = description or "فاتورة خدمة شريك"
    exp.notes = description or None
    exp.payment_method = "cash"
    exp.payment_details = None
    db.session.add(exp)
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "expense_id": exp.id,
            "expense_url": url_for("expenses_bp.edit", exp_id=exp.id),
            "amount": float(amount),
            "currency": currency,
            "partner_name": partner.name,
        }
    )


@expenses_bp.route("/quick-partner-service/pay", methods=["POST"], endpoint="quick_partner_service_pay")
@login_required
def quick_partner_service_pay():
    if not request.is_json:
        return jsonify({"success": False, "message": "payload_required"}), 400
    data = request.get_json(silent=True) or {}
    expense_id = data.get("expense_id")
    try:
        expense_id = int(expense_id or 0)
    except (TypeError, ValueError):
        expense_id = 0
    expense = Expense.query.get(expense_id)
    if not expense:
        return jsonify({"success": False, "message": "expense_not_found"}), 404
    amount = D(str(data.get("amount") or 0))
    if amount <= 0:
        return jsonify({"success": False, "message": "invalid_amount"}), 400
    currency = ensure_currency(data.get("currency"), expense.currency or "ILS")
    if currency != (expense.currency or "ILS"):
        return jsonify({"success": False, "message": "currency_mismatch"}), 400
    method_raw = (data.get("method") or "cash").strip().lower()
    allowed_methods = {m.value for m in PaymentMethod}
    if method_raw not in allowed_methods:
        return jsonify({"success": False, "message": "invalid_method"}), 400
    reference = (data.get("reference") or "").strip()
    notes = (data.get("notes") or "").strip()
    entries = [
        {
            "amount": amount.quantize(Decimal("0.01")),
            "method": method_raw,
            "payment_date": datetime.utcnow(),
            "reference": reference,
            "notes": notes,
            "currency": currency,
            "details": {},
        }
    ]
    try:
        _create_partial_payments(expense, entries)
        db.session.commit()
    except ValueError as err:
        db.session.rollback()
        return jsonify({"success": False, "message": str(err) or "payment_error"}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "payment_error"}), 400
    return jsonify(
        {
            "success": True,
            "expense_id": expense.id,
            "expense_url": url_for("expenses_bp.edit", exp_id=expense.id),
        }
    )

@expenses_bp.route("/edit/<int:exp_id>", methods=["GET", "POST"], endpoint="edit")
@login_required
def edit(exp_id):
    from models import Branch, Site
    
    exp = _get_or_404(Expense, exp_id)
    form = ExpenseForm(obj=exp)
    
    _types = ExpenseType.query.order_by(ExpenseType.name).all()
    types_list = [{'id': t.id, 'name': t.name, 'code': t.code, 'fields_meta': t.fields_meta} for t in _types]
    form.type_id.choices = [(t.id, t.name) for t in _types]
    types_meta = {t.id: _merge_type_meta(t) for t in _types}
    
    employees = Employee.query.order_by(Employee.name).limit(200).all()
    form.employee_id.choices = [(0, '-- اختر موظفاً --')]
    if exp.employee_id and exp.employee and exp.employee not in employees:
        form.employee_id.choices.append((exp.employee.id, f"✓ {exp.employee.name}"))
    form.employee_id.choices += [(e.id, e.name) for e in employees]
    
    utilities = UtilityAccount.query.filter_by(is_active=True).order_by(UtilityAccount.provider).limit(100).all()
    form.utility_account_id.choices = [(0, '-- اختر حساب --')]
    if exp.utility_account_id and exp.utility_account and exp.utility_account not in utilities:
        form.utility_account_id.choices.append((exp.utility_account.id, f"✓ {exp.utility_account.provider} - {exp.utility_account.account_no or exp.utility_account.alias}"))
    form.utility_account_id.choices += [(u.id, f"{u.provider} - {u.account_no or u.alias or u.utility_type}") for u in utilities]
    
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).limit(100).all()
    form.warehouse_id.choices = [(0, '-- اختر مستودع --')]
    if exp.warehouse_id and exp.warehouse and exp.warehouse not in warehouses:
        form.warehouse_id.choices.append((exp.warehouse.id, f"✓ {exp.warehouse.name}"))
    form.warehouse_id.choices += [(w.id, w.name) for w in warehouses]
    
    shipments = Shipment.query.order_by(Shipment.id.desc()).limit(50).all()
    form.shipment_id.choices = [(0, '-- اختر شحنة --')]
    if exp.shipment_id and exp.shipment and exp.shipment not in shipments:
        form.shipment_id.choices.append((exp.shipment.id, f"✓ شحنة #{exp.shipment.id}"))
    form.shipment_id.choices += [(s.id, f"شحنة #{s.id}") for s in shipments]
    
    partners = Partner.query.filter_by(is_archived=False).order_by(Partner.name).limit(100).all()
    form.partner_id.choices = [(0, '-- اختر شريك --')]
    if exp.partner_id and exp.partner and exp.partner not in partners:
        form.partner_id.choices.append((exp.partner.id, f"✓ {exp.partner.name}"))
    form.partner_id.choices += [(p.id, p.name) for p in partners]
    
    suppliers = Supplier.query.filter_by(is_archived=False).order_by(Supplier.name).limit(100).all()
    form.supplier_id.choices = [(0, '-- اختر مورد --')]
    if exp.supplier_id and exp.supplier and exp.supplier not in suppliers:
        form.supplier_id.choices.append((exp.supplier.id, f"✓ {exp.supplier.name}"))
    form.supplier_id.choices += [(s.id, s.name) for s in suppliers]
    
    customers_query = Customer.query
    if hasattr(Customer, 'is_archived'):
        customers_query = customers_query.filter_by(is_archived=False)
    customers = customers_query.order_by(Customer.name).limit(100).all()
    form.customer_id.choices = [(0, '-- اختر عميل --')]
    current_customer_id = exp.customer_id or (exp.payee_entity_id if getattr(exp, 'payee_type', '').upper() == 'CUSTOMER' else None)
    if current_customer_id:
        if exp.customer_id and exp.customer and exp.customer not in customers:
            form.customer_id.choices.append((exp.customer.id, f"✓ {exp.customer.name}"))
        elif not any(c.id == current_customer_id for c in customers):
            form.customer_id.choices.append((current_customer_id, f"✓ {exp.payee_name or f'عميل #{current_customer_id}'}"))
        form.customer_id.data = current_customer_id
    form.customer_id.choices += [(c.id, c.name) for c in customers]
    
    adjustments = StockAdjustment.query.order_by(StockAdjustment.id.desc()).limit(50).all()
    form.stock_adjustment_id.choices = [(0, '-- اختر تسوية --')]
    if exp.stock_adjustment_id and exp.stock_adjustment and exp.stock_adjustment not in adjustments:
        form.stock_adjustment_id.choices.append((exp.stock_adjustment.id, f"✓ تسوية #{exp.stock_adjustment.id}"))
    form.stock_adjustment_id.choices += [(sa.id, f"تسوية #{sa.id}") for sa in adjustments]
    
    if form.validate_on_submit():
        partial_payload_raw = request.form.get("partial_payments_payload")
        partial_entries = _parse_partial_payments_payload(
            partial_payload_raw,
            form.date.data or exp.date or datetime.utcnow(),
            form.currency.data or exp.currency or "ILS",
        )
        if hasattr(form, "apply_to"):
            form.apply_to(exp)
        else:
            form.populate_obj(exp)
            if hasattr(form, "date"):
                dt = _to_datetime(form.date.data)
                if dt:
                    exp.date = dt
            if not getattr(form, "employee_id", None) or not form.employee_id.data or form.employee_id.data == 0:
                exp.employee_id = None
            if not getattr(form, "utility_account_id", None) or form.utility_account_id.data == 0:
                exp.utility_account_id = None
            if not getattr(form, "warehouse_id", None) or form.warehouse_id.data == 0:
                exp.warehouse_id = None
            if not getattr(form, "shipment_id", None) or form.shipment_id.data == 0:
                exp.shipment_id = None
            if not getattr(form, "partner_id", None) or form.partner_id.data == 0:
                exp.partner_id = None
            if not getattr(form, "stock_adjustment_id", None) or form.stock_adjustment_id.data == 0:
                exp.stock_adjustment_id = None
        try:
            db.session.flush()
            _create_partial_payments(exp, partial_entries)
            db.session.commit()
            flash("✅ تم تعديل المصروف", "success")
            return redirect(url_for("expenses_bp.list_expenses"))
        except ValueError as perr:
            db.session.rollback()
            flash(str(perr), "danger")
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل المصروف: {err}", "danger")
    
    return _render_expense_form(form, is_edit=True, types_meta=types_meta, types_list=types_list, expense=exp)

@expenses_bp.route("/delete/<int:exp_id>", methods=["POST"], endpoint="delete")
@login_required
def delete(exp_id):
    exp = _get_or_404(Expense, exp_id)
    
    try:
        db.session.delete(exp)
        db.session.commit()
        flash("✅ تم حذف المصروف", "success")
    except SQLAlchemyError as err:
        db.session.rollback()
        flash(f"❌ خطأ في حذف المصروف: {err}", "danger")
    return redirect(url_for("expenses_bp.list_expenses"))

@expenses_bp.route("/<int:exp_id>/pay", methods=["GET"], endpoint="pay")
@login_required
def pay(exp_id):
    """إعادة توجيه لإنشاء دفعة للنفقة مع البيانات الكاملة"""
    exp = _get_or_404(Expense, exp_id)
    
    amount_src = getattr(exp, "balance", None)
    if amount_src is None:
        amount_src = getattr(exp, "amount", 0)
    amount = int(q0(amount_src))
    
    payee = exp.payee_name or (exp.employee.name if exp.employee else None) or 'غير محدد'
    expense_type = exp.type.name if exp.type else 'مصروف'
    expense_ref = exp.tax_invoice_number or f'EXP-{exp.id}'
    
    reference = f'دفع {expense_type} لـ {payee} - {expense_ref}'
    notes = f'دفع نفقة: {exp.description or expense_type} - المستفيد: {payee}'
    
    if exp.employee:
        notes += f' - موظف: {exp.employee.name}'
    
    return redirect(
        url_for(
            "payments.create_payment",
            entity_type="EXPENSE",
            entity_id=exp.id,
            direction="OUT",
            amount=amount,
            currency=(exp.currency or "ILS").upper(),
            reference=reference,
            notes=notes
        )
    )

@expenses_bp.route("/export", methods=["GET"], endpoint="export")
@login_required
def export_csv():
    query, _ = _base_query_with_filters()
    rows = query.limit(50000).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "التاريخ",
            "النوع",
            "نوع المستفيد",
            "المستفيد",
            "الموظف",
            "الشحنة",
            "حساب مرفق",
            "تسوية مخزون",
            "بداية الفترة",
            "نهاية الفترة",
            "المبلغ",
            "العملة",
            "طريقة الدفع",
            "الوصف",
            "ملاحظات",
            "رقم الفاتورة",
            "مدفوع",
            "الرصيد",
        ]
    )
    for e in rows:
        writer.writerow(
            [
                e.id,
                e.date.isoformat() if e.date else "",
                _csv_safe(e.type.name if e.type else ""),
                _csv_safe(e.payee_type or ""),
                _csv_safe(e.payee_name or e.paid_to or ""),
                _csv_safe(e.employee.name if e.employee else ""),
                _csv_safe(e.shipment.number if getattr(e, "shipment", None) else ""),
                _csv_safe((e.utility_account.alias if e.utility_account and e.utility_account.alias else (e.utility_account.provider if e.utility_account else ""))),
                _csv_safe(e.stock_adjustment_id if getattr(e, "stock_adjustment_id", None) else ""),
                e.period_start.isoformat() if getattr(e, "period_start", None) else "",
                e.period_end.isoformat() if getattr(e, "period_end", None) else "",
                int(q0(getattr(e, "amount", 0) or 0)),
                _csv_safe((e.currency or "").upper()),
                _csv_safe(e.payment_method or ""),
                _csv_safe(e.description),
                _csv_safe(e.notes),
                _csv_safe(e.tax_invoice_number),
                int(q0(getattr(e, "total_paid", 0) or 0)),
                int(q0(getattr(e, "balance", 0) or 0)),
            ]
        )
    csv_data = output.getvalue()
    filename = f"expenses_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@expenses_bp.route("/print", methods=["GET"], endpoint="print_list")
@login_required
def print_list():
    query, filt = _base_query_with_filters()
    rows = query.limit(50000).all()
    total_amount = int(q0(sum(D(getattr(e, "amount", 0) or 0) for e in rows)))
    total_paid = int(q0(sum(D(getattr(e, "total_paid", 0) or 0) for e in rows)))
    total_balance = int(q0(sum(D(getattr(e, "balance", 0) or 0) for e in rows)))
    return render_template(
        "expenses/expenses_print.html",
        expenses=rows,
        search=filt["q"],
        start=filt["start"],
        end=filt["end"],
        total_amount=total_amount,
        total_paid=total_paid,
        total_balance=total_balance,
        generated_at=datetime.utcnow(),
    )

@expenses_bp.route("/archive/<int:expense_id>", methods=["POST"])
@login_required
def archive_expense(expense_id):
    
    try:
        from models import Archive
        
        expense = Expense.query.get_or_404(expense_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(expense, reason, current_user.id)
        flash(f'تم أرشفة النفقة رقم {expense.id} بنجاح', 'success')
        return redirect(url_for('expenses_bp.list_expenses'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في أرشفة النفقة: {str(e)}', 'error')
        return redirect(url_for('expenses_bp.list_expenses'))

@expenses_bp.route('/restore/<int:expense_id>', methods=['POST'])
@login_required
def restore_expense(expense_id):
    """استعادة نفقة"""
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        if not expense.is_archived:
            flash('النفقة غير مؤرشفة', 'warning')
            return redirect(url_for('expenses_bp.list_expenses'))
        
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='expenses',
            record_id=expense_id
        ).first()
        
        if archive:
            utils.restore_record(archive.id)
        
        flash(f'تم استعادة النفقة رقم {expense_id} بنجاح', 'success')
        return redirect(url_for('expenses_bp.list_expenses'))
        
    except Exception as e:
        
        db.session.rollback()
        flash(f'خطأ في استعادة النفقة: {str(e)}', 'error')
        return redirect(url_for('expenses_bp.list_expenses'))


@expenses_bp.route("/payroll/monthly", methods=["GET"], endpoint="payroll_monthly")
@login_required
def payroll_monthly():
    from models import ExpenseType, EmployeeDeduction, EmployeeAdvanceInstallment
    from calendar import monthrange
    from decimal import Decimal
    
    today = datetime.now()
    month = int(request.args.get('month', today.month))
    year = int(request.args.get('year', today.year))
    
    employees = Employee.query.order_by(Employee.name).all()
    
    payroll_data = []
    
    for emp in employees:
        base_salary = Decimal(str(emp.salary or 0))
        deductions = Decimal(str(emp.total_deductions or 0))
        social_ins = Decimal(str(emp.social_insurance_employee_amount or 0))
        income_tax = Decimal(str(emp.income_tax_amount or 0))
        
        period_start = _date(year, month, 1)
        last_day = monthrange(year, month)[1]
        period_end = _date(year, month, last_day)
        
        installments = EmployeeAdvanceInstallment.query.filter(
            EmployeeAdvanceInstallment.employee_id == emp.id,
            EmployeeAdvanceInstallment.paid == False,
            EmployeeAdvanceInstallment.due_date >= period_start,
            EmployeeAdvanceInstallment.due_date <= period_end
        ).all()
        
        advances_total = sum(Decimal(str(inst.amount or 0)) for inst in installments)
        
        net_salary = base_salary - deductions - social_ins - income_tax - advances_total
        
        salary_type = ExpenseType.query.filter_by(code='SALARY').first()
        already_paid = False
        if salary_type:
            from sqlalchemy import extract as sql_extract
            existing = Expense.query.filter(
                Expense.employee_id == emp.id,
                Expense.type_id == salary_type.id,
                sql_extract('month', Expense.date) == month,
                sql_extract('year', Expense.date) == year
            ).first()
            if existing:
                already_paid = True
        
        payroll_data.append({
            'employee': emp,
            'base_salary': float(base_salary),
            'deductions': float(deductions),
            'social_insurance': float(social_ins),
            'income_tax': float(income_tax),
            'advances': float(advances_total),
            'net_salary': float(net_salary),
            'already_paid': already_paid
        })
    
    total_base = sum(d['base_salary'] for d in payroll_data)
    total_deductions = sum(d['deductions'] for d in payroll_data)
    total_advances = sum(d['advances'] for d in payroll_data)
    total_net = sum(d['net_salary'] for d in payroll_data)
    
    summary = {
        'total_base': total_base,
        'total_deductions': total_deductions,
        'total_advances': total_advances,
        'total_net': total_net,
        'employee_count': len(payroll_data)
    }
    
    return render_template(
        "expenses/payroll_monthly.html",
        payroll_data=payroll_data,
        summary=summary,
        month=month,
        year=year
    )


@expenses_bp.route("/payroll/generate-all", methods=["POST"], endpoint="generate_all_salaries")
@login_required
def generate_all_salaries():
    from models import ExpenseType, EmployeeAdvanceInstallment
    from calendar import monthrange
    from decimal import Decimal
    
    today = datetime.now()
    month = int(request.form.get('month', today.month))
    year = int(request.form.get('year', today.year))
    payment_date = request.form.get('payment_date', today.date().isoformat())
    
    employees = Employee.query.order_by(Employee.name).limit(1000).all()
    
    salary_type = ExpenseType.query.filter_by(code='SALARY').first()
    if not salary_type:
        flash('نوع النفقة SALARY غير موجود', 'danger')
        return redirect(url_for('expenses_bp.payroll_monthly'))
    
    success_count = 0
    error_count = 0
    
    for emp in employees:
        try:
            from sqlalchemy import extract as sql_extract
            existing = Expense.query.filter(
                Expense.employee_id == emp.id,
                Expense.type_id == salary_type.id,
                sql_extract('month', Expense.date) == month,
                sql_extract('year', Expense.date) == year
            ).first()
            
            if existing:
                continue
            
            base_salary = Decimal(str(emp.salary or 0))
            deductions = Decimal(str(emp.total_deductions or 0))
            social_ins = Decimal(str(emp.social_insurance_employee_amount or 0))
            income_tax = Decimal(str(emp.income_tax_amount or 0))
            
            period_start = _date(year, month, 1)
            last_day = monthrange(year, month)[1]
            period_end = _date(year, month, last_day)
            
            installments = EmployeeAdvanceInstallment.query.filter(
                EmployeeAdvanceInstallment.employee_id == emp.id,
                EmployeeAdvanceInstallment.paid == False,
                EmployeeAdvanceInstallment.due_date >= period_start,
                EmployeeAdvanceInstallment.due_date <= period_end
            ).all()
            
            advances_total = sum(Decimal(str(inst.amount or 0)) for inst in installments)
            net_salary = base_salary - deductions - social_ins - income_tax - advances_total
            
            if net_salary <= 0:
                error_count += 1
                continue
            
            if not emp.branch_id:
                error_count += 1
                current_app.logger.warning(f"❌ موظف {emp.name} ليس لديه branch_id")
                continue
            
            new_expense = Expense(
                type_id=salary_type.id,
                employee_id=emp.id,
                amount=float(net_salary),
                date=datetime.strptime(payment_date, '%Y-%m-%d').date() if payment_date else datetime.now().date(),
                description=f'راتب {month}/{year} - {emp.name}',
                payment_method='bank',
                branch_id=emp.branch_id,
                site_id=emp.site_id
            )
            
            db.session.add(new_expense)
            
            for inst in installments:
                inst.paid = True
                inst.paid_at = datetime.now()
            
            success_count += 1
            
        except Exception as e:
            error_count += 1
            db.session.rollback()
            current_app.logger.error(f"❌ خطأ في توليد راتب {emp.name}: {str(e)}")
            continue
    
    try:
        if success_count > 0:
            db.session.commit()
            flash(f'تم توليد {success_count} راتب بنجاح', 'success')
        
        if error_count > 0:
            flash(f'فشل توليد {error_count} راتب', 'warning')
    except Exception as commit_error:
        db.session.rollback()
        flash(f'خطأ في حفظ البيانات: {str(commit_error)}', 'danger')
    
    return redirect(url_for('expenses_bp.payroll_monthly', month=month, year=year))


@expenses_bp.route("/payroll/summary", methods=["GET"], endpoint="payroll_summary")
@login_required
def payroll_summary():
    from models import ExpenseType
    from decimal import Decimal
    from sqlalchemy import extract as sql_extract
    
    year = int(request.args.get('year', datetime.now().year))
    
    salary_type = ExpenseType.query.filter_by(code='SALARY').first()
    
    monthly_data = []
    
    for month in range(1, 13):
        if salary_type:
            salaries = Expense.query.filter(
                Expense.type_id == salary_type.id,
                sql_extract('month', Expense.date) == month,
                sql_extract('year', Expense.date) == year
            ).all()
            
            total_paid = sum(Decimal(str(s.amount or 0)) for s in salaries)
            emp_count = len(set(s.employee_id for s in salaries))
        else:
            total_paid = Decimal('0')
            emp_count = 0
        
        monthly_data.append({
            'month': month,
            'total_paid': float(total_paid),
            'employee_count': emp_count
        })
    
    year_total = sum(m['total_paid'] for m in monthly_data)
    avg_monthly = year_total / 12 if year_total > 0 else 0
    
    summary = {
        'year_total': year_total,
        'avg_monthly': avg_monthly,
        'months_paid': sum(1 for m in monthly_data if m['total_paid'] > 0)
    }
    
    return render_template(
        "expenses/payroll_summary.html",
        monthly_data=monthly_data,
        summary=summary,
        year=year
    )
