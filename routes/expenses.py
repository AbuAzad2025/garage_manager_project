# -*- coding: utf-8 -*-
import json
from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, abort, request, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

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
        user_id=current_user.id,
        action=action,
        old_data=json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data=json.dumps(new_data, ensure_ascii=False) if new_data else None,
        timestamp=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.flush()

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
        t = ExpenseType()
        form.populate_obj(t)
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
        form.populate_obj(t)
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

@expenses_bp.route('/', methods=['GET'], endpoint='list_expenses')
@login_required
@permission_required('manage_expenses')
def index():
    q = request.args.get('q', '').strip()
    query = Expense.query
    if q:
        query = query.filter(Expense.description.ilike(f'%{q}%'))
    expenses = query.order_by(Expense.date.desc()).all()
    return render_template('expenses/expenses_list.html', expenses=expenses, search=q)

@expenses_bp.route('/<int:exp_id>', methods=['GET'], endpoint='detail')
@login_required
@permission_required('manage_expenses')
def detail(exp_id):
    exp = _get_or_404(Expense, exp_id)
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
        if not form.employee_id.data: exp.employee_id = None
        if not form.warehouse_id.data: exp.warehouse_id = None
        if not form.partner_id.data:   exp.partner_id = None
        db.session.add(exp)
        try:
            db.session.flush()
            log_expense_action(exp, 'add', None, {'amount': str(exp.amount), 'type': exp.type_id, 'date': exp.date.isoformat()})
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
    old_data = {'amount': str(exp.amount), 'type': exp.type_id, 'date': exp.date.isoformat()}
    form = ExpenseForm(obj=exp)
    form.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
    if form.validate_on_submit():
        form.populate_obj(exp)
        if not form.employee_id.data: exp.employee_id = None
        if not form.warehouse_id.data: exp.warehouse_id = None
        if not form.partner_id.data:   exp.partner_id = None
        try:
            db.session.flush()
            log_expense_action(exp, 'edit', old_data, {'amount': str(exp.amount), 'type': exp.type_id, 'date': exp.date.isoformat()})
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
    old_data = {'amount': str(exp.amount), 'type': exp.type_id, 'date': exp.date.isoformat()}
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
