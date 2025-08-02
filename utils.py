# File: garage_manager/utils.py

import base64
import csv
import io
import json
from functools import wraps
from datetime import datetime
from urllib.parse import quote
import qrcode
import redis
import pandas as pd
from flask import abort, current_app, Response, flash
from flask_login import current_user, login_required
from flask_mail import Message
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from extensions import db, mail
from models import Customer

# ==================== Email Notification ====================
def send_email_notification(subject: str, recipients: list, body: str, html: str = None):
    msg = Message(subject=subject, recipients=recipients, body=body, html=html)
    mail.send(msg)

# ==================== Jinja2 Filters ====================
def format_currency(value):
    try:
        return f"{value:,.2f} ₪"
    except Exception:
        return "0.00 ₪"

def format_percent(value):
    try:
        return f"{value:.2f}%"
    except Exception:
        return "0.00%"

# ==================== App Initialization ====================
redis_client = None

def init_app(app):
    global redis_client
    app.jinja_env.filters['format_currency'] = format_currency
    app.jinja_env.filters['format_percent']  = format_percent
    redis_client = redis.StrictRedis.from_url(
        app.config.get('REDIS_URL', 'redis://localhost:6379/0'),
        decode_responses=True
    )

# ==================== QR Code to Base64 ====================
def qr_to_base64(value: str) -> str:
    img = qrcode.make(value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')

# ==================== Recent Notes ====================
def recent_notes(limit: int = 5):
    from .models import Note
    return Note.query.order_by(Note.created_at.desc()).limit(limit).all()

# ==================== WhatsApp via Twilio ====================
def send_whatsapp_message(to_number: str, body: str) -> bool:
    sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER')

    if not all([sid, token, from_number]):
        flash('❌ لم يتم تكوين خدمة واتساب. الرجاء مراجعة إعدادات Twilio.', 'danger')
        return False

    client = Client(sid, token)
    try:
        client.messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}",
            body=body,
        )
        return True
    except TwilioRestException as e:
        flash(f'❌ خطأ أثناء إرسال واتساب: {e.msg}', 'danger')
        return False
# ==================== Excel Report Generation ====================
def generate_excel_report(data, filename: str = 'report.xlsx') -> Response:
    buffer = io.BytesIO()
    df = pd.DataFrame([item.to_dict() for item in data])
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return Response(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
# ==================== Permission Caching ====================
_SUPER_ROLES = {'developer'}

def _fetch_permissions_from_db(user):
    perms = {p.name for p in user.role.permissions.all()} if user.role else set()
    perms |= {p.name for p in user.extra_permissions.all()}
    return perms

def _get_user_permissions(user):
    if not redis_client:
        return _fetch_permissions_from_db(user)
    key = f"user_permissions:{user.id}"
    cached = redis_client.smembers(key)
    if cached:
        return cached
    perms = _fetch_permissions_from_db(user)
    redis_client.delete(key)
    if perms:
        redis_client.sadd(key, *perms)
    redis_client.expire(key, 300)
    return perms

def clear_user_permission_cache(user_id):
    if redis_client:
        redis_client.delete(f"user_permissions:{user_id}")

# ==================== Decorators ====================
def permission_required(permission_name):
    def decorator(f):
        @login_required
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not (current_user.is_authenticated and current_user.has_permission(permission_name)):
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def admin_required(f):
    return permission_required('manage_roles')(f)

def customer_required(f):
    @login_required
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not isinstance(current_user, Customer):
            abort(403)
        if 'place_online_order' not in _get_user_permissions(current_user):
            abort(403)
        return f(*args, **kwargs)
    return wrapper

# ==================== PDF Report Generation ====================
def generate_pdf_report(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table_data = [['ID', 'Name', 'Balance']] + [[str(item.id), item.name, f"{item.balance:,.2f}"] for item in data]
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    doc.build([table])
    buffer.seek(0)
    return Response(
        buffer,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment; filename=report.pdf'}
    )

# ==================== Contacts Export (VCF / CSV / Excel) ====================
def generate_vcf(customers, fields):
    output = []
    for c in customers:
        card = ["BEGIN:VCARD", "VERSION:3.0"]
        if 'name' in fields:    card.append(f"N:{c.name}")
        if 'phone' in fields:   card.append(f"TEL:{c.phone or ''}")
        if 'email' in fields:   card.append(f"EMAIL:{c.email or ''}")
        if 'address' in fields: card.append(f"ADR:{c.address or ''}")
        if 'notes' in fields:   card.append(f"NOTE:{c.notes or ''}")
        card.append("END:VCARD")
        output.append("\n".join(card))
    vcf_data = "\n".join(output)
    filename = 'contacts.vcf'
    disp = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
    return Response(
        vcf_data,
        mimetype='text/vcard',
        headers={'Content-Disposition': disp}
    )

def generate_csv_contacts(customers, fields):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fields)
    for c in customers:
        writer.writerow([getattr(c, f) or '' for f in fields])
    filename = 'contacts.csv'
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

def generate_excel_contacts(customers, fields):
    from openpyxl import Workbook
    stream = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(fields)
    for c in customers:
        ws.append([getattr(c, f) or '' for f in fields])
    wb.save(stream)
    stream.seek(0)
    filename = 'contacts.xlsx'
    return Response(
        stream,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
