# routes/expenses.py
# -*- coding: utf-8 -*-
import csv
import io
import json
from datetime import datetime, date as _date
from flask import Blueprint, flash, redirect, render_template, abort, request, url_for, Response
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_

from extensions import db
from forms import EmployeeForm, ExpenseTypeForm, ExpenseForm
from models import Employee, ExpenseType, Expense, AuditLog
from utils import permission_required

expenses_bp = Blueprint(
    'expenses_bp',
    __name__,
    url_prefix='/expenses',
    template_folder='templates/expenses'
)

# -------------------- Helpers --------------------
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

def log_expense_action(exp: Expense, action: str, old_data=None, new_data=None):
    if not getattr(exp, "id", None):
        db.session.flush()
    entry = AuditLog(
        model_name='Expense',
        record_id=exp.id,
        user_id=getattr(current_user, "id", None),
        action=action,
        old_data=json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data=json.dumps(new_data, ensure_ascii=False) if new_data else None,
    )
    db.session.add(entry)
    db.session.flush()

def _to_datetime(value):
    """حوّل DateField (date) إلى datetime (00:00:00)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, _date):
        return datetime.combine(value, datetime.min.time())
    return None

def _parse_date_arg(arg_name: str):
    """اقرأ باراميتر تاريخ بصيغة YYYY-MM-DD وأعد كائن date أو None."""
    raw = (request.args.get(arg_name) or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None

def _base_query_with_filters():
    """كوّن الاستعلام الأساسي مع تحميل العلاقات وتطبيق فلاتر q/start/end."""
    q = Expense.query.options(
        joinedload(Expense.type),
        joinedload(Expense.employee),
    )

    search = (request.args.get('q') or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Expense.description.ilike(like),
                Expense.paid_to.ilike(like),
                Expense.tax_invoice_number.ilike(like),
            )
        )

    start_d = _parse_date_arg("start")  # YYYY-MM-DD
    end_d   = _parse_date_arg("end")    # YYYY-MM-DD
    if start_d or end_d:
        conds = []
        if start_d:
            conds.append(Expense.date >= datetime.combine(start_d, datetime.min.time()))
        if end_d:
            conds.append(Expense.date <= datetime.combine(end_d, datetime.max.time()))
        q = q.filter(and_(*conds))

    q = q.order_by(Expense.date.desc(), Expense.id.desc())
    return q, {"q": search, "start": start_d, "end": end_d}

# -------------------- Employees --------------------
@expenses_bp.route('/employees', methods=['GET'], endpoint='employees_list')
@login_required
@permission_required('manage_expenses')
def employees_list():
    employees = Employee.query.order_by(Employee.name).all()
    return render_template('expenses/employees_list.html', employees=employees)

@expenses_bp.route('/employees/add', methods=['GET', 'POST'], endpoint='add_employee')
@login_required
@permission_required('manage_expenses')
def add_employee():
    form = EmployeeForm()
    if form.validate_on_submit():
        e = Employee()
        form.populate_obj(e)
        db.session.add(e)
        try:
            db.session.commit()
            flash("✅ تمت إضافة الموظف", "success")
            return redirect(url_for('expenses_bp.employees_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة الموظف: {err}", "danger")
    return render_template('expenses/employee_form.html', form=form, is_edit=False)

@expenses_bp.route('/employees/edit/<int:emp_id>', methods=['GET', 'POST'], endpoint='edit_employee')
@login_required
@permission_required('manage_expenses')
def edit_employee(emp_id):
    e = _get_or_404(Employee, emp_id)
    form = EmployeeForm(obj=e)
    if form.validate_on_submit():
        form.populate_obj(e)
        try:
            db.session.commit()
            flash("✅ تم تعديل الموظف", "success")
            return redirect(url_for('expenses_bp.employees_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل الموظف: {err}", "danger")
    return render_template('expenses/employee_form.html', form=form, is_edit=True)

@expenses_bp.route('/employees/delete/<int:emp_id>', methods=['POST'], endpoint='delete_employee')
@login_required
@permission_required('manage_expenses')
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
    return redirect(url_for('expenses_bp.employees_list'))

# -------------------- Expense Types --------------------
@expenses_bp.route('/types', methods=['GET'], endpoint='types_list')
@login_required
@permission_required('manage_expenses')
def types_list():
    types = ExpenseType.query.order_by(ExpenseType.name).all()
    return render_template('expenses/types_list.html', types=types)

@expenses_bp.route('/types/add', methods=['GET', 'POST'], endpoint='add_type')
@login_required
@permission_required('manage_expenses')
def add_type():
    form = ExpenseTypeForm()
    if form.validate_on_submit():
        # تجنب populate_obj حتى لا يعيّن form.id -> model.id
        t = ExpenseType(
            name=(form.name.data or "").strip(),
            description=(form.description.data or None),
            is_active=bool(getattr(form, "is_active", None) and form.is_active.data),
        )
        # تأكيد أن id غير مضبوط من أي حقل
        t.id = None
        db.session.add(t)
        try:
            db.session.commit()
            flash("✅ تمت إضافة نوع المصروف", "success")
            return redirect(url_for('expenses_bp.types_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة النوع: {err}", "danger")
    return render_template('expenses/type_form.html', form=form, is_edit=False)

@expenses_bp.route('/types/edit/<int:type_id>', methods=['GET', 'POST'], endpoint='edit_type')
@login_required
@permission_required('manage_expenses')
def edit_type(type_id):
    t = _get_or_404(ExpenseType, type_id)
    form = ExpenseTypeForm(obj=t)
    if form.validate_on_submit():
        # نحدّث الحقول يدويًا ونتجاهل id مهما أرسله النموذج
        t.name = (form.name.data or "").strip()
        t.description = (form.description.data or None)
        if hasattr(form, "is_active"):
            t.is_active = bool(form.is_active.data)
        try:
            db.session.commit()
            flash("✅ تم تعديل النوع", "success")
            return redirect(url_for('expenses_bp.types_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل النوع: {err}", "danger")
    return render_template('expenses/type_form.html', form=form, is_edit=True)

@expenses_bp.route('/types/delete/<int:type_id>', methods=['POST'], endpoint='delete_type')
@login_required
@permission_required('manage_expenses')
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
    return redirect(url_for('expenses_bp.types_list'))

# -------------------- Expenses --------------------
@expenses_bp.route('/', methods=['GET'], endpoint='list_expenses')
@login_required
@permission_required('manage_expenses')
def index():
    query, filt = _base_query_with_filters()
    expenses = query.all()
    return render_template('expenses/expenses_list.html', expenses=expenses, search=filt["q"], start=filt["start"], end=filt["end"])

@expenses_bp.route('/<int:exp_id>', methods=['GET'], endpoint='detail')
@login_required
@permission_required('manage_expenses')
def detail(exp_id):
    exp = _get_or_404(
        Expense,
        exp_id,
        joinedload(Expense.type),
        joinedload(Expense.employee),
    )
    return render_template('expenses/detail.html', expense=exp)

@expenses_bp.route('/add', methods=['GET', 'POST'], endpoint='create_expense')
@login_required
@permission_required('manage_expenses')
def add():
    form = ExpenseForm()
    form.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
    if form.validate_on_submit():
        exp = Expense()
        form.populate_obj(exp)
        # تصحيح التاريخ إن كان DateField
        if hasattr(form, "date"):
            dt = _to_datetime(form.date.data)
            if dt:
                exp.date = dt
        # الموظف اختياري
        if not getattr(form.employee_id, "data", None):
            exp.employee_id = None
        db.session.add(exp)
        try:
            db.session.flush()
            log_expense_action(exp, 'add', None, {
                'amount': str(exp.amount),
                'type': exp.type_id,
                'date': exp.date.isoformat() if exp.date else None
            })
            db.session.commit()
            flash("✅ تمت إضافة المصروف", "success")
            return redirect(url_for('expenses_bp.list_expenses'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة المصروف: {err}", "danger")
    return render_template('expenses/expense_form.html', form=form, is_edit=False)

@expenses_bp.route('/edit/<int:exp_id>', methods=['GET', 'POST'], endpoint='edit')
@login_required
@permission_required('manage_expenses')
def edit(exp_id):
    exp = _get_or_404(Expense, exp_id)
    old_data = {
        'amount': str(exp.amount),
        'type': exp.type_id,
        'date': exp.date.isoformat() if exp.date else None
    }
    form = ExpenseForm(obj=exp)
    form.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
    if form.validate_on_submit():
        form.populate_obj(exp)
        # تصحيح التاريخ إن كان DateField
        if hasattr(form, "date"):
            dt = _to_datetime(form.date.data)
            if dt:
                exp.date = dt
        if not getattr(form, "employee_id", None) or not form.employee_id.data:
            exp.employee_id = None
        try:
            db.session.flush()
            log_expense_action(exp, 'edit', old_data, {
                'amount': str(exp.amount),
                'type': exp.type_id,
                'date': exp.date.isoformat() if exp.date else None
            })
            db.session.commit()
            flash("✅ تم تعديل المصروف", "success")
            return redirect(url_for('expenses_bp.list_expenses'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل المصروف: {err}", "danger")
    return render_template('expenses/expense_form.html', form=form, is_edit=True)

@expenses_bp.route('/delete/<int:exp_id>', methods=['POST'], endpoint='delete')
@login_required
@permission_required('manage_expenses')
def delete(exp_id):
    exp = _get_or_404(Expense, exp_id)
    old_data = {
        'amount': str(exp.amount),
        'type': exp.type_id,
        'date': exp.date.isoformat() if exp.date else None
    }
    try:
        log_expense_action(exp, 'delete', old_data, None)
        db.session.delete(exp)
        db.session.commit()
        flash("✅ تم حذف المصروف", "warning")
    except SQLAlchemyError as err:
        db.session.rollback()
        flash(f"❌ خطأ في حذف المصروف: {err}", "danger")
    return redirect(url_for('expenses_bp.list_expenses'))

@expenses_bp.route('/<int:exp_id>/pay', methods=['GET'], endpoint='pay')
@login_required
@permission_required('manage_expenses')
def pay(exp_id):
    return redirect(url_for('payments.create_payment', entity_type='EXPENSE', entity_id=exp_id))

# -------------------- Export & Print --------------------
@expenses_bp.route('/export', methods=['GET'], endpoint='export')
@login_required
@permission_required('manage_expenses')
def export_csv():
    """تصدير المصاريف المتطابقة مع الفلاتر إلى CSV (يفتح في إكسل)."""
    query, _ = _base_query_with_filters()
    rows = query.all()

    output = io.StringIO()
    output.write("\ufeff")  # BOM لدعم العربية في Excel
    writer = csv.writer(output)
    writer.writerow([
        "ID","التاريخ","النوع","الموظف","الجهة","المبلغ","العملة","طريقة الدفع","الوصف","ملاحظات","رقم الفاتورة",
    ])
    for e in rows:
        writer.writerow([
            e.id,
            e.date.isoformat() if e.date else "",
            (e.type.name if e.type else ""),
            (e.employee.name if e.employee else ""),
            (e.paid_to or ""),
            float(e.amount or 0),
            e.currency or "",
            e.payment_method or "",
            e.description or "",
            e.notes or "",
            e.tax_invoice_number or "",
        ])

    csv_data = output.getvalue()
    filename = f"expenses_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@expenses_bp.route('/print', methods=['GET'], endpoint='print_list')
@login_required
@permission_required('manage_expenses')
def print_list():
    """عرض للطباعة بنفس فلاتر القائمة، مع مجموع المبالغ."""
    query, filt = _base_query_with_filters()
    rows = query.all()
    total_amount = sum(float(e.amount or 0) for e in rows)
    return render_template(
        "expenses/expenses_print.html",
        expenses=rows,
        search=filt["q"],
        start=filt["start"],
        end=filt["end"],
        total_amount=total_amount,
        generated_at=datetime.utcnow(),
    )
