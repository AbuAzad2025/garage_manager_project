# File: routes/expenses.py

import json
from datetime import datetime

from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for, abort
)
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from extensions import db, mail
from forms import EmployeeForm, ExpenseTypeForm, ExpenseForm
from models import (
    Employee, ExpenseType, Expense,
    Warehouse, Partner, AuditLog, Payment
)
from utils import permission_required

expenses_bp = Blueprint(
    'expenses',
    __name__,
    url_prefix='/expenses',
    template_folder='../templates/expenses'
)

def log_expense_action(exp: Expense, action: str, old_data=None, new_data=None):
    """سجل أحداث إنشاء/تعديل/حذف مصروف."""
    entry = AuditLog(
        model_name   = 'Expense',
        record_id    = exp.id,
        user_id      = current_user.id,
        action       = action,
        old_data     = json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data     = json.dumps(new_data, ensure_ascii=False) if new_data else None,
        timestamp    = datetime.utcnow()
    )
    db.session.add(entry)
    db.session.commit()

# ── إدارة الموظفين ─────────────────────────────────────────────────

@expenses_bp.route('/employees')
@login_required
@permission_required('manage_expenses')
def employees_list():
    employees = Employee.query.order_by(Employee.name).all()
    return render_template('expenses/employees_list.html', employees=employees)

@expenses_bp.route('/employees/add', methods=['GET','POST'])
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
            flash("✅ تمت إضافة الموظف.", "success")
            return redirect(url_for('expenses.employees_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة الموظف: {err}", "danger")
    return render_template('expenses/employee_form.html', form=form, is_edit=False)

@expenses_bp.route('/employees/edit/<int:emp_id>', methods=['GET','POST'])
@login_required
@permission_required('manage_expenses')
def edit_employee(emp_id):
    e = Employee.query.get_or_404(emp_id)
    form = EmployeeForm(obj=e)
    if form.validate_on_submit():
        form.populate_obj(e)
        try:
            db.session.commit()
            flash("✅ تم تعديل الموظف.", "success")
            return redirect(url_for('expenses.employees_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل الموظف: {err}", "danger")
    return render_template('expenses/employee_form.html', form=form, is_edit=True)

@expenses_bp.route('/employees/delete/<int:emp_id>', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def delete_employee(emp_id):
    e = Employee.query.get_or_404(emp_id)
    if Expense.query.filter_by(employee_id=emp_id).first():
        flash("❌ لا يمكن حذف الموظف؛ مرتبط بمصاريف.", "danger")
    else:
        try:
            db.session.delete(e)
            db.session.commit()
            flash("✅ تم حذف الموظف.", "success")
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في حذف الموظف: {err}", "danger")
    return redirect(url_for('expenses.employees_list'))

# ── إدارة أنواع المصاريف ────────────────────────────────────────────

@expenses_bp.route('/types')
@login_required
@permission_required('manage_expenses')
def types_list():
    types = ExpenseType.query.order_by(ExpenseType.name).all()
    return render_template('expenses/types_list.html', types=types)

@expenses_bp.route('/types/add', methods=['GET','POST'])
@login_required
@permission_required('manage_expenses')
def add_type():
    form = ExpenseTypeForm()
    if form.validate_on_submit():
        t = ExpenseType()
        form.populate_obj(t)
        db.session.add(t)
        try:
            db.session.commit()
            flash("✅ تمت إضافة نوع المصروف.", "success")
            return redirect(url_for('expenses.types_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة النوع: {err}", "danger")
    return render_template('expenses/type_form.html', form=form, is_edit=False)

@expenses_bp.route('/types/edit/<int:type_id>', methods=['GET','POST'])
@login_required
@permission_required('manage_expenses')
def edit_type(type_id):
    t = ExpenseType.query.get_or_404(type_id)
    form = ExpenseTypeForm(obj=t)
    if form.validate_on_submit():
        form.populate_obj(t)
        try:
            db.session.commit()
            flash("✅ تم تعديل النوع.", "success")
            return redirect(url_for('expenses.types_list'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل النوع: {err}", "danger")
    return render_template('expenses/type_form.html', form=form, is_edit=True)

@expenses_bp.route('/types/delete/<int:type_id>', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def delete_type(type_id):
    t = ExpenseType.query.get_or_404(type_id)
    if Expense.query.filter_by(type_id=type_id).first():
        flash("❌ لا يمكن حذف النوع؛ مرتبط بمصاريف.", "danger")
    else:
        try:
            db.session.delete(t)
            db.session.commit()
            flash("✅ تم حذف النوع.", "success")
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في حذف النوع: {err}", "danger")
    return redirect(url_for('expenses.types_list'))

# ── إدارة المصاريف ─────────────────────────────────────────────────

@expenses_bp.route('/')
@login_required
@permission_required('manage_expenses')
def index():
    # فلترة بسيطة بالـ query params (اختياري)
    q = request.args.get('q', '').strip()
    query = Expense.query
    if q:
        query = query.filter(Expense.description.ilike(f'%{q}%'))
    expenses = query.order_by(Expense.date.desc()).all()
    return render_template('expenses/expenses_list.html', expenses=expenses, search=q)

@expenses_bp.route('/<int:exp_id>')
@login_required
@permission_required('manage_expenses')
def detail(exp_id):
    exp = Expense.query.get_or_404(exp_id)
    payments = Payment.query.filter_by(expense_id=exp_id).order_by(Payment.payment_date.desc()).all()
    return render_template(
        'expenses/detail.html',
        expense=exp,
        payments=payments
    )

@expenses_bp.route('/add', methods=['GET','POST'])
@login_required
@permission_required('manage_expenses')
def add():
    form = ExpenseForm()
    # تعبئة الحقول
    form.type_id.choices      = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
    form.employee_id.choices  = [(0,'---')] + [(e.id, e.name) for e in Employee.query.order_by(Employee.name).all()]

    if form.validate_on_submit():
        exp = Expense()
        form.populate_obj(exp)
        if form.employee_id.data == 0:
            exp.employee_id = None
        if form.warehouse_id.data:
            exp.warehouse_id = form.warehouse_id.data.id
        if form.partner_id.data:
            exp.partner_id = form.partner_id.data.id
        db.session.add(exp)
        try:
            db.session.commit()
            log_expense_action(exp, 'add', None, {
                'amount': exp.amount,
                'type':   exp.type_id,
                'date':   exp.date.isoformat()
            })
            flash("✅ تمت إضافة المصروف.", "success")
            return redirect(url_for('expenses.index'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في إضافة المصروف: {err}", "danger")
    return render_template('expenses/expense_form.html', form=form, is_edit=False)

@expenses_bp.route('/edit/<int:exp_id>', methods=['GET','POST'])
@login_required
@permission_required('manage_expenses')
def edit(exp_id):
    exp = Expense.query.get_or_404(exp_id)
    old_data = {
        'amount': exp.amount,
        'type':   exp.type_id,
        'date':   exp.date.isoformat()
    }
    form = ExpenseForm(obj=exp)
    form.type_id.choices      = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
    form.employee_id.choices  = [(0,'---')] + [(e.id, e.name) for e in Employee.query.order_by(Employee.name).all()]

    if form.validate_on_submit():
        form.populate_obj(exp)
        if form.employee_id.data == 0:
            exp.employee_id = None
        if form.warehouse_id.data:
            exp.warehouse_id = form.warehouse_id.data.id
        else:
            exp.warehouse_id = None
        if form.partner_id.data:
            exp.partner_id = form.partner_id.data.id
        else:
            exp.partner_id = None

        try:
            db.session.commit()
            log_expense_action(exp, 'edit', old_data, {
                'amount': exp.amount,
                'type':   exp.type_id,
                'date':   exp.date.isoformat()
            })
            flash("✅ تم تعديل المصروف.", "success")
            return redirect(url_for('expenses.index'))
        except SQLAlchemyError as err:
            db.session.rollback()
            flash(f"❌ خطأ في تعديل المصروف: {err}", "danger")

    if exp.employee_id is None:
        form.employee_id.data = 0
    return render_template('expenses/expense_form.html', form=form, is_edit=True)

@expenses_bp.route('/delete/<int:exp_id>', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def delete(exp_id):
    exp = Expense.query.get_or_404(exp_id)
    old_data = {
        'amount': exp.amount,
        'type':   exp.type_id,
        'date':   exp.date.isoformat()
    }
    try:
        db.session.delete(exp)
        db.session.commit()
        log_expense_action(exp, 'delete', old_data, None)
        flash("✅ تم حذف المصروف.", "warning")
    except SQLAlchemyError as err:
        db.session.rollback()
        flash(f"❌ خطأ في حذف المصروف: {err}", "danger")
    return redirect(url_for('expenses.index'))

@expenses_bp.route('/<int:exp_id>/pay', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def pay(exp_id):
    """إعادة توجيه إلى وحدة الدفع الموحد."""
    return redirect(url_for(
        'payments.create_payment',
        entity_type='expense',
        entity_id=exp_id
    ))
