from datetime import datetime
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, abort
from flask_login import current_user, login_required
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from extensions import db
from forms import NoteForm
from models import Note
from utils import permission_required

notes_bp = Blueprint('notes_bp', __name__, url_prefix='/notes', template_folder='templates/notes')

def _get_or_404(model, ident, options=None):
    q = db.session.query(model)
    if options:
        for opt in options: q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None: abort(404)
    return obj

ENTITY_TYPES = [
    ('', '-- اختر --'),
    ('CUSTOMER', 'عميل'),
    ('SALE', 'بيع'),
    ('PRODUCT', 'منتج'),
    ('SUPPLIER', 'مورد'),
    ('PARTNER', 'شريك'),
    ('INVOICE', 'فاتورة'),
    ('SHIPMENT', 'شحنة'),
    ('SERVICE', 'صيانة'),
    ('USER', 'مستخدم'),
    ('OTHER', 'أخرى')
]

@notes_bp.route('/', methods=['GET'], endpoint='list_notes')
@login_required
@permission_required('view_notes')
def list_notes():
    etype = request.args.get('entity_type'); eid = request.args.get('entity_id', type=int); pinned = request.args.get('is_pinned'); prio = request.args.get('priority')
    q = Note.query.options(joinedload(Note.author))
    fs = []
    if etype: fs.append(Note.entity_type == etype)
    if eid: fs.append(Note.entity_id == eid)
    if pinned in ('0','1'): fs.append(Note.is_pinned == (pinned == '1'))
    if prio: fs.append(Note.priority == prio)
    if fs: q = q.filter(and_(*fs))
    q = q.order_by(Note.created_at.desc())
    page = request.args.get('page', 1, type=int); per_page = request.args.get('per_page', 20, type=int)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    notes = pagination.items
    if request.args.get('format') == 'json' or request.is_json:
        data = [{
            'id': n.id,
            'content': n.content,
            'author': n.author.username,
            'entity_type': n.entity_type,
            'entity_id': n.entity_id,
            'is_pinned': n.is_pinned,
            'priority': n.priority,
            'created_at': n.created_at.isoformat()
        } for n in notes]
        return jsonify({'data': data,'meta': {'page': pagination.page,'per_page': pagination.per_page,'total': pagination.total,'pages': pagination.pages}})
    form = NoteForm(); form.entity_type.choices = ENTITY_TYPES
    return render_template('notes/list.html', notes=notes, pagination=pagination, filters={'entity_type': etype,'entity_id': eid,'is_pinned': pinned,'priority': prio}, form=form, entity_choices=ENTITY_TYPES)

@notes_bp.route('/new', methods=['GET','POST'], endpoint='create_note')
@login_required
@permission_required('add_notes')
def create_note():
    form = NoteForm(); form.entity_type.choices = ENTITY_TYPES
    if request.method == 'GET':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('notes/_form.html', form=form, entity_choices=ENTITY_TYPES)
        return redirect(url_for('notes_bp.list_notes'))
    if not form.validate_on_submit():
        errors = {f: errs[0] for f, errs in form.errors.items()}
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, errors=errors), 400
        flash('فشل إضافة الملاحظة: ' + ', '.join(errors.values()), 'danger')
        return redirect(url_for('notes_bp.list_notes'))
    note = Note(content=form.content.data, author_id=current_user.id, entity_type=form.entity_type.data or None, entity_id=form.entity_id.data or None, is_pinned=form.is_pinned.data, priority=form.priority.data, created_at=datetime.utcnow())
    db.session.add(note)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        msg = str(e)
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, error=msg), 500
        flash(f'خطأ أثناء الحفظ: {msg}', 'danger')
        return redirect(url_for('notes_bp.list_notes'))
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True,'note': {'id': note.id,'content': note.content,'author': current_user.username,'entity_type': note.entity_type,'entity_id': note.entity_id,'is_pinned': note.is_pinned,'priority': note.priority,'created_at': note.created_at.strftime('%Y-%m-%d %H:%M')}}), 201
    flash('تم إضافة الملاحظة بنجاح.', 'success'); return redirect(url_for('notes_bp.list_notes'))

@notes_bp.route('/<int:note_id>', methods=['GET'], endpoint='note_detail')
@login_required
@permission_required('view_notes')
def note_detail(note_id):
    note = _get_or_404(Note, note_id)
    return render_template('notes/detail.html', note=note)
