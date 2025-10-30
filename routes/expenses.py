
import csv
import io
from datetime import datetime, date as _date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from flask import Blueprint, flash, redirect, render_template, abort, request, url_for, Response, current_app
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_

from extensions import db
from forms import EmployeeForm, ExpenseTypeForm, ExpenseForm
from models import Employee, ExpenseType, Expense, Shipment, UtilityAccount, StockAdjustment, Partner, Warehouse
import utils
from utils import D, q0, archive_record, restore_record

expenses_bp = Blueprint(
    "expenses_bp",
    __name__,
    url_prefix="/expenses",
    template_folder="templates/expenses",
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

def _base_query_with_filters():
    q = (
        Expense.query.filter(Expense.is_archived == False).options(
            joinedload(Expense.type),
            joinedload(Expense.employee),
            joinedload(Expense.shipment),
            joinedload(Expense.utility_account),
            joinedload(Expense.stock_adjustment),
        )
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
    }

def _csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(("=", "+", "-", "@")) else s

@expenses_bp.route("/employees", methods=["GET"], endpoint="employees_list")
@login_required
# @permission_required("manage_expenses")  # Commented out
def employees_list():
    employees = Employee.query.order_by(Employee.name).all()
    return render_template("expenses/employees_list.html", employees=employees)

@expenses_bp.route("/employees/add", methods=["GET", "POST"], endpoint="add_employee")
@login_required
# @permission_required("manage_expenses")  # Commented out
def add_employee():
    form = EmployeeForm()
    # فروع ومواقع
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
# @permission_required("manage_expenses")  # Commented out
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
    
    # السلف
    advance_type = ExpenseType.query.filter_by(code='EMPLOYEE_ADVANCE').first()
    advances = []
    if advance_type:
        advances = Expense.query.filter_by(employee_id=emp_id, type_id=advance_type.id).order_by(Expense.date.desc()).all()
        # إضافة الأقساط لكل سلفة
        for adv in advances:
            adv.installments = EmployeeAdvanceInstallment.query.filter_by(advance_expense_id=adv.id).order_by(EmployeeAdvanceInstallment.installment_number).all()
    
    # الخصومات الشهرية
    deductions = EmployeeDeduction.query.filter_by(employee_id=emp_id).order_by(EmployeeDeduction.start_date.desc()).all()
    
    # الرواتب المدفوعة
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


@expenses_bp.route("/salary-receipt/<int:salary_exp_id>", methods=["GET"], endpoint="salary_receipt")
@login_required
def salary_receipt(salary_exp_id):
    """إيصال راتب قابل للطباعة - A4 Format"""
    from models import EmployeeDeduction, EmployeeAdvanceInstallment, ExpenseType
    from datetime import date
    
    salary_expense = _get_or_404(Expense, salary_exp_id, joinedload(Expense.employee), joinedload(Expense.employee, Employee.branch))
    
    if not salary_expense.employee:
        flash("❌ المصروف غير مرتبط بموظف", "danger")
        return redirect(url_for("expenses_bp.list_expenses"))
    
    employee = salary_expense.employee
    
    # الخصومات النشطة في تاريخ الراتب
    sal_date = salary_expense.date.date() if isinstance(salary_expense.date, datetime) else salary_expense.date
    deductions = EmployeeDeduction.query.filter(
        EmployeeDeduction.employee_id == employee.id,
        EmployeeDeduction.is_active == True,
        EmployeeDeduction.start_date <= sal_date,
        or_(EmployeeDeduction.end_date.is_(None), EmployeeDeduction.end_date >= sal_date)
    ).all()
    
    # الأقساط المستحقة في شهر الراتب
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
    
    return render_template(
        "expenses/salary_receipt.html",
        employee=employee,
        salary_expense=salary_expense,
        deductions=deductions,
        installments_due=installments_due,
    )

@expenses_bp.route("/employees/delete/<int:emp_id>", methods=["POST"], endpoint="delete_employee")
@login_required
# @permission_required("manage_expenses")  # Commented out
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
# @permission_required("manage_expenses")  # Commented out
def types_list():
    types = ExpenseType.query.order_by(ExpenseType.name).all()
    return render_template("expenses/types_list.html", types=types)

@expenses_bp.route("/types/add", methods=["GET", "POST"], endpoint="add_type")
@login_required
# @permission_required("manage_expenses")  # Commented out
def add_type():
    form = ExpenseTypeForm()
    if form.validate_on_submit():
        t = ExpenseType(
            name=(form.name.data or "").strip(),
            description=(form.description.data or None),
            is_active=bool(getattr(form, "is_active", None) and form.is_active.data),
        )
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
# @permission_required("manage_expenses")  # Commented out
def edit_type(type_id):
    t = _get_or_404(ExpenseType, type_id)
    form = ExpenseTypeForm(obj=t)
    if form.validate_on_submit():
        t.name = (form.name.data or "").strip()
        t.description = (form.description.data or None)
        if hasattr(form, "is_active"):
            t.is_active = bool(form.is_active.data)
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
# @permission_required("manage_expenses")  # Commented out
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
# @permission_required("manage_expenses")  # Commented out
def index():
    query, filt = _base_query_with_filters()
    expenses = query.all()
    
    # حساب الملخصات الحقيقية مع تحويل العملات
    from models import fx_rate
    
    total_expenses = 0.0
    total_paid = 0.0
    total_balance = 0.0
    expenses_by_type = {}
    expenses_by_currency = {}
    
    for expense in expenses:
        # تحويل للشيقل
        amount = float(expense.amount or 0)
        if expense.currency and expense.currency != 'ILS':
            try:
                rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                if rate > 0:
                    amount = float(amount * float(rate))
                else:
                    current_app.logger.warning(f"⚠️ سعر صرف مفقود: {expense.currency}/ILS للمصروف #{expense.id} - استخدام المبلغ الأصلي")
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في تحويل العملة للمصروف #{expense.id}: {str(e)}")
        
        total_expenses += amount
        
        # حساب المدفوع والرصيد
        paid = float(expense.total_paid or 0)
        if expense.currency and expense.currency != 'ILS':
            try:
                rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                if rate > 0:
                    paid = float(paid * float(rate))
                else:
                    current_app.logger.warning(f"⚠️ سعر صرف مفقود لحساب المدفوع للمصروف #{expense.id}")
            except Exception as e:
                current_app.logger.error(f"❌ خطأ في تحويل العملة للمدفوع للمصروف #{expense.id}: {str(e)}")
        
        total_paid += paid
        balance = amount - paid
        total_balance += balance
        
        # تصنيف حسب النوع
        expense_type = expense.type.name if expense.type else 'غير مصنف'
        if expense_type not in expenses_by_type:
            expenses_by_type[expense_type] = {'count': 0, 'amount': 0}
        expenses_by_type[expense_type]['count'] += 1
        expenses_by_type[expense_type]['amount'] += amount
        
        # تصنيف حسب العملة
        currency = expense.currency or 'ILS'
        if currency not in expenses_by_currency:
            expenses_by_currency[currency] = {'count': 0, 'amount': 0, 'amount_ils': 0}
        expenses_by_currency[currency]['count'] += 1
        expenses_by_currency[currency]['amount'] += float(expense.amount or 0)
        expenses_by_currency[currency]['amount_ils'] += amount
    
    # ترتيب حسب الأكبر
    expenses_by_type_sorted = sorted(expenses_by_type.items(), key=lambda x: x[1]['amount'], reverse=True)
    
    summary = {
        'total_expenses': total_expenses,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'expenses_count': len(expenses),
        'average_expense': total_expenses / len(expenses) if len(expenses) > 0 else 0,
        'expenses_by_type': expenses_by_type_sorted,
        'expenses_by_currency': expenses_by_currency,
        'payment_percentage': (total_paid / total_expenses * 100) if total_expenses > 0 else 0
    }
    
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
        summary=summary,
    )

@expenses_bp.route("/<int:exp_id>", methods=["GET"], endpoint="detail")
@login_required
# @permission_required("manage_expenses")  # Commented out
def detail(exp_id):
    exp = _get_or_404(
        Expense,
        exp_id,
        joinedload(Expense.type),
        joinedload(Expense.employee),
        joinedload(Expense.shipment),
        joinedload(Expense.utility_account),
        joinedload(Expense.stock_adjustment),
    )
    return render_template("expenses/detail.html", expense=exp)

@expenses_bp.route("/add", methods=["GET", "POST"], endpoint="create_expense")
@login_required
# @permission_required("manage_expenses")  # Commented out
def add():
    from models import Branch, Site
    
    form = ExpenseForm()
    # ✅ ملء جميع القوائم المنسدلة
    _types = ExpenseType.query.filter_by(is_active=True).order_by(ExpenseType.name).all()
    form.type_id.choices = [(t.id, t.name) for t in _types]
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
    form.shipment_id.choices = [(0, '-- اختر شحنة --')] + [(s.id, f"شحنة #{s.id}") for s in Shipment.query.order_by(Shipment.id.desc()).limit(50).all()]
    form.stock_adjustment_id.choices = [(0, '-- اختر تسوية --')] + [(sa.id, f"تسوية #{sa.id}") for sa in StockAdjustment.query.order_by(StockAdjustment.id.desc()).limit(50).all()]
    
    # تمرير ميتاداتا الحقول إلى القالب ليتحكم بما يظهر ويُلزم
    types_meta = {t.id: (t.fields_meta or {}) for t in _types}

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
            # ✅ تحويل 0 إلى None للحقول الاختيارية
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

        # ✅ تحقق خادمي حسب نوع المصروف: الحقول الإلزامية من fields_meta
        try:
            etype = ExpenseType.query.get(int(form.type_id.data)) if getattr(form, 'type_id', None) else None
            meta = (etype.fields_meta or {}) if etype else {}
            required = set((meta.get('required') or []))
            missing = []
            # خرائط المفاتيح إلى قيم الكائن exp بعد populate
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
            # في حال فشل التحليل نعيد النموذج للمستخدم
            return render_template(
                "expenses/expense_form.html",
                form=form,
                is_edit=False,
            ), 400
        # ✅ حساب تلقائي للراتب الصافي (قبل الحفظ)
        try:
            etype = ExpenseType.query.get(exp.type_id) if exp.type_id else None
            if etype and etype.code == 'SALARY' and exp.employee_id:
                emp = Employee.query.get(exp.employee_id)
                if emp:
                    # حساب الصافي: الراتب الأساسي - الخصومات الشهرية
                    suggested_net = float(emp.net_salary or 0)
                    # إن كان المبلغ المُدخل يساوي الأساسي، نعدله للصافي تلقائياً
                    if abs(float(exp.amount) - float(emp.salary or 0)) < 0.01:
                        exp.amount = suggested_net
                        current_app.logger.info(f"✅ تم تعديل راتب الموظف #{emp.id} تلقائياً للصافي: {suggested_net}")
        except Exception as e:
            current_app.logger.warning(f"⚠️ فشل حساب الراتب الصافي التلقائي: {e}")
        
        db.session.add(exp)
        try:
            db.session.commit()
            
            # ✅ معالجة ذكية للسلف: إنشاء أقساط إن طُلب
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
            
            # ✅ معالجة ذكية: إنشاء خصم شهري تلقائي إن طُلب
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
            
            # ✅ إنشاء سجل Check تلقائياً إذا كانت طريقة الدفع شيك
            try:
                from models import Check
                from flask_login import current_user
                
                if exp.payment_method and exp.payment_method.lower() in ['check', 'cheque']:
                    check_number = (exp.check_number or '').strip()
                    check_bank = (exp.check_bank or '').strip()
                    
                    if not check_number or not check_bank:
                        current_app.logger.warning(f"⚠️ مصروف {exp.id} بطريقة شيك لكن بدون رقم شيك أو بنك")
                    else:
                        # تحويل check_due_date من date إلى datetime إذا لزم الأمر
                        check_due_date = exp.check_due_date
                        if check_due_date and isinstance(check_due_date, date) and not isinstance(check_due_date, datetime):
                            check_due_date = datetime.combine(check_due_date, datetime.min.time())
                        elif not check_due_date:
                            check_due_date = exp.date or datetime.utcnow()
                        
                        # إنشاء سجل الشيك
                        check = Check(
                            check_number=check_number,
                            check_bank=check_bank,
                            check_date=exp.date or datetime.utcnow(),
                            check_due_date=check_due_date,
                            amount=exp.amount,
                            currency=exp.currency or 'ILS',
                            direction='OUT',  # المصروفات دائماً صادرة
                            status='PENDING',
                            supplier_id=getattr(exp, 'supplier_id', None),
                            partner_id=getattr(exp, 'partner_id', None),
                            reference_number=f"EXP-{exp.id}",
                            notes=f"شيك من مصروف رقم {exp.id} - {exp.description[:50] if exp.description else 'مصروف'}",
                            payee_name=exp.payee_name or exp.paid_to or exp.beneficiary_name,
                            created_by_id=current_user.id if current_user.is_authenticated else None
                        )
                        db.session.add(check)
                        db.session.commit()
                        current_app.logger.info(f"✅ تم إنشاء سجل شيك رقم {check.check_number} من مصروف رقم {exp.id}")
            except Exception as e:
                # في حالة فشل إنشاء الشيك، لا نُفشل المصروف
                current_app.logger.error(f"❌ فشل إنشاء سجل شيك من مصروف {exp.id}: {str(e)}")
                import traceback
                current_app.logger.error(traceback.format_exc())
                # لا نعمل rollback لأن المصروف تم حفظه مسبقاً
                # إعادة commit للمصروف فقط
                db.session.commit()
            
            flash("✅ تمت إضافة المصروف", "success")
            return redirect(url_for("expenses_bp.list_expenses"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة المصروف: {err}", "danger")
    
    # تمرير metadata للقالب
    types_list = [{'id': t.id, 'name': t.name, 'code': t.code, 'fields_meta': t.fields_meta} for t in _types]
    return render_template("expenses/expense_form.html", 
                         form=form, 
                         is_edit=False,
                         types_meta=types_meta,
                         _types=types_list)

@expenses_bp.route("/edit/<int:exp_id>", methods=["GET", "POST"], endpoint="edit")
@login_required
# @permission_required("manage_expenses")  # Commented out
def edit(exp_id):
    from models import Branch, Site
    
    exp = _get_or_404(Expense, exp_id)
    form = ExpenseForm(obj=exp)
    
    # ✅ ملء جميع القوائم المنسدلة
    _types = ExpenseType.query.order_by(ExpenseType.name).all()
    form.type_id.choices = [(t.id, t.name) for t in _types]
    types_meta = {t.id: (t.fields_meta or {}) for t in _types}
    
    # ✅ الموظفين (مع إضافة الموظف الحالي إذا لم يكن في القائمة)
    employees = Employee.query.order_by(Employee.name).limit(200).all()
    form.employee_id.choices = [(0, '-- اختر موظفاً --')]
    if exp.employee_id and exp.employee and exp.employee not in employees:
        form.employee_id.choices.append((exp.employee.id, f"✓ {exp.employee.name}"))
    form.employee_id.choices += [(e.id, e.name) for e in employees]
    
    # ✅ حسابات المرافق (مع إضافة الحساب الحالي)
    utilities = UtilityAccount.query.filter_by(is_active=True).order_by(UtilityAccount.provider).limit(100).all()
    form.utility_account_id.choices = [(0, '-- اختر حساب --')]
    if exp.utility_account_id and exp.utility_account and exp.utility_account not in utilities:
        form.utility_account_id.choices.append((exp.utility_account.id, f"✓ {exp.utility_account.provider} - {exp.utility_account.account_no or exp.utility_account.alias}"))
    form.utility_account_id.choices += [(u.id, f"{u.provider} - {u.account_no or u.alias or u.utility_type}") for u in utilities]
    
    # ✅ المستودعات (مع إضافة المستودع الحالي)
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).limit(100).all()
    form.warehouse_id.choices = [(0, '-- اختر مستودع --')]
    if exp.warehouse_id and exp.warehouse and exp.warehouse not in warehouses:
        form.warehouse_id.choices.append((exp.warehouse.id, f"✓ {exp.warehouse.name}"))
    form.warehouse_id.choices += [(w.id, w.name) for w in warehouses]
    
    # ✅ الشحنات (مع إضافة الشحنة الحالية)
    shipments = Shipment.query.order_by(Shipment.id.desc()).limit(50).all()
    form.shipment_id.choices = [(0, '-- اختر شحنة --')]
    if exp.shipment_id and exp.shipment and exp.shipment not in shipments:
        form.shipment_id.choices.append((exp.shipment.id, f"✓ شحنة #{exp.shipment.id}"))
    form.shipment_id.choices += [(s.id, f"شحنة #{s.id}") for s in shipments]
    
    # ✅ الشركاء (مع إضافة الشريك الحالي)
    partners = Partner.query.filter_by(is_archived=False).order_by(Partner.name).limit(100).all()
    form.partner_id.choices = [(0, '-- اختر شريك --')]
    if exp.partner_id and exp.partner and exp.partner not in partners:
        form.partner_id.choices.append((exp.partner.id, f"✓ {exp.partner.name}"))
    form.partner_id.choices += [(p.id, p.name) for p in partners]
    
    # ✅ تسويات المخزون (مع إضافة التسوية الحالية)
    adjustments = StockAdjustment.query.order_by(StockAdjustment.id.desc()).limit(50).all()
    form.stock_adjustment_id.choices = [(0, '-- اختر تسوية --')]
    if exp.stock_adjustment_id and exp.stock_adjustment and exp.stock_adjustment not in adjustments:
        form.stock_adjustment_id.choices.append((exp.stock_adjustment.id, f"✓ تسوية #{exp.stock_adjustment.id}"))
    form.stock_adjustment_id.choices += [(sa.id, f"تسوية #{sa.id}") for sa in adjustments]
    
    if form.validate_on_submit():
        if hasattr(form, "apply_to"):
            form.apply_to(exp)
        else:
            form.populate_obj(exp)
            if hasattr(form, "date"):
                dt = _to_datetime(form.date.data)
                if dt:
                    exp.date = dt
            # ✅ تحويل 0 إلى None للحقول الاختيارية
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
            db.session.commit()
            flash("✅ تم تعديل المصروف", "success")
            return redirect(url_for("expenses_bp.list_expenses"))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل المصروف: {err}", "danger")
    
    # تمرير metadata للقالب
    types_list = [{'id': t.id, 'name': t.name, 'code': t.code, 'fields_meta': t.fields_meta} for t in _types]
    return render_template("expenses/expense_form.html", 
                         form=form, 
                         is_edit=True,
                         types_meta=types_meta,
                         _types=types_list)

@expenses_bp.route("/delete/<int:exp_id>", methods=["POST"], endpoint="delete")
@login_required
# @permission_required("manage_expenses")  # Commented out
def delete(exp_id):
    exp = _get_or_404(Expense, exp_id)
    try:
        db.session.delete(exp)
        db.session.commit()
        flash("✅ تم حذف المصروف", "warning")
    except SQLAlchemyError as err:
        db.session.rollback()
        flash(f"❌ خطأ في حذف المصروف: {err}", "danger")
    return redirect(url_for("expenses_bp.list_expenses"))

@expenses_bp.route("/<int:exp_id>/pay", methods=["GET"], endpoint="pay")
@login_required
# @permission_required("manage_expenses")  # Commented out
def pay(exp_id):
    """إعادة توجيه لإنشاء دفعة للنفقة مع البيانات الكاملة"""
    exp = _get_or_404(Expense, exp_id)
    
    # حساب المبلغ
    amount_src = getattr(exp, "balance", None)
    if amount_src is None:
        amount_src = getattr(exp, "amount", 0)
    amount = int(q0(amount_src))
    
    # تجهيز المرجع والملاحظات
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
# @permission_required("manage_expenses")  # Commented out
def export_csv():
    query, _ = _base_query_with_filters()
    rows = query.all()
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
# @permission_required("manage_expenses")  # Commented out
def print_list():
    query, filt = _base_query_with_filters()
    rows = query.all()
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
# @permission_required("manage_expenses")  # Commented out
def archive_expense(expense_id):
    
    try:
        from models import Archive
        
        expense = Expense.query.get_or_404(expense_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(expense, reason, current_user.id)
        flash(f'تم أرشفة النفقة رقم {expense.id} بنجاح', 'success')
        return redirect(url_for('expenses_bp.list_expenses'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في أرشفة النفقة: {str(e)}', 'error')
        return redirect(url_for('expenses_bp.list_expenses'))

@expenses_bp.route('/restore/<int:expense_id>', methods=['POST'])
@login_required
# @permission_required('manage_expenses')  # Commented out
def restore_expense(expense_id):
    """استعادة نفقة"""
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        if not expense.is_archived:
            flash('النفقة غير مؤرشفة', 'warning')
            return redirect(url_for('expenses_bp.list_expenses'))
        
        # البحث عن الأرشيف
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='expenses',
            record_id=expense_id
        ).first()
        
        if archive:
            utils.restore_record(archive.id)
        
        flash(f'تم استعادة النفقة رقم {expense_id} بنجاح', 'success')
        print(f"🎉 [EXPENSE RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('expenses_bp.list_expenses'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في استعادة النفقة: {str(e)}', 'error')
        return redirect(url_for('expenses_bp.list_expenses'))
