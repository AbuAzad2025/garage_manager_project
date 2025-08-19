"""
Utility helpers for Garage Manager:
- Jinja filters (currency/percent/date formatting, status labels)
- Notifications (email, WhatsApp via Twilio)
- Reports/exports (PDF, Excel, CSV, VCF)
- Permissions helpers with Redis caching
- Audit logging utilities
"""

import base64
import csv
import io
import json
from datetime import datetime
from functools import wraps

from flask import Response, abort, current_app, flash, make_response, request
from flask_login import current_user, login_required
from flask_mail import Message
import pandas as pd
import qrcode
import redis
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from sqlalchemy import func
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from extensions import db, mail
from models import PaymentStatus, Payment, PaymentSplit

# ==== Card helpers (Luhn / Expiry / Encryption) ====
import re
import hashlib
from datetime import datetime
from flask import current_app

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None

redis_client: redis.Redis | None = None


def init_app(app):
    """Register Jinja filters and initialize Redis from app config."""
    global redis_client
    app.jinja_env.filters["format_currency"] = format_currency
    app.jinja_env.filters["format_percent"] = format_percent
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["yes_no"] = yes_no
    app.jinja_env.filters["status_label"] = status_label
    redis_client = redis.StrictRedis.from_url(
        app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def send_email_notification(
    subject: str,
    recipients: list[str],
    body: str,
    html: str | None = None,
):
    """Send email using Flask-Mail."""
    msg = Message(subject=subject, recipients=recipients, body=body, html=html)
    mail.send(msg)


def format_currency(value):
    """Format numeric value as currency with ILS symbol."""
    try:
        return f"{float(value):,.2f} ₪"
    except Exception:
        return "0.00 ₪"


def format_percent(value):
    """Format numeric value as percent with 2 decimals."""
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "0.00%"


def format_date(value, fmt: str = "%Y-%m-%d"):
    """Format a date; return '-' if invalid/empty."""
    try:
        return value.strftime(fmt) if value else "-"
    except Exception:
        return "-"


def format_datetime(value, fmt: str = "%Y-%m-%d %H:%M"):
    """Format a datetime; return '' if invalid/empty."""
    try:
        return value.strftime(fmt) if value else ""
    except Exception:
        return ""


def yes_no(value):
    """Arabic yes/no label used across templates."""
    return "نشط" if value else "مؤرشف"


def status_label(status):
    """Map internal status to Arabic label."""
    m = {
        "active": "نشط",
        "inactive": "غير نشط",
        "credit_hold": "معلق ائتمانيًا",
        "pending": "قيد الانتظار",
        "completed": "مكتمل",
        "failed": "فشل",
    }
    return m.get(str(status).lower(), str(status))


def qr_to_base64(value: str) -> str:
    """Create QR for value and return as base64 PNG."""
    img = qrcode.make(value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def recent_notes(limit: int = 5):
    """Return latest notes."""
    from models import Note

    return Note.query.order_by(Note.created_at.desc()).limit(limit).all()


def send_whatsapp_message(to_number: str, body: str) -> bool:
    """Send WhatsApp message through Twilio."""
    sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_WHATSAPP_NUMBER")

    if not all([sid, token, from_number]):
        flash("❌ لم يتم تكوين خدمة واتساب. الرجاء مراجعة إعدادات Twilio.", "danger")
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
        flash(f"❌ خطأ أثناء إرسال واتساب: {e.msg}", "danger")
        return False


def generate_excel_report(data, filename: str = "report.xlsx") -> Response:
    """Export iterable of dict/obj to Excel and return as Flask Response."""
    buffer = io.BytesIO()
    rows = [
        item.to_dict() if hasattr(item, "to_dict") else dict(item)
        for item in data
    ]
    pd.DataFrame(rows).to_excel(buffer, index=False)
    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


_SUPER_ROLES = {"developer", "owner", "admin", "super_admin"}

_PERMISSION_ALIASES = {
    "view_warehouses": {
        "view_warehouses",
        "view_inventory",
        "manage_inventory",
        "manage_warehouses",
    },
    "view_inventory": {
        "view_inventory",
        "manage_inventory",
        "manage_warehouses",
    },
    "manage_inventory": {
        "manage_inventory",
        "manage_warehouses",
        "manage_stock",
        "warehouse_transfer",
    },
    "warehouse_transfer": {
        "warehouse_transfer",
        "manage_inventory",
        "manage_warehouses",
    },
    "view_parts": {"view_parts", "view_inventory", "manage_inventory"},
    "view_preorders": {"view_preorders", "view_inventory", "manage_inventory"},
    "add_preorder": {"add_preorder", "manage_inventory"},
    "edit_preorder": {"edit_preorder", "manage_inventory"},
    "delete_preorder": {"delete_preorder", "manage_inventory"},
    "add_customer": {"add_customer", "manage_customers"},
    "add_supplier": {"add_supplier", "manage_vendors"},
    "add_partner": {"add_partner", "manage_vendors"},
    "manage_shipments": {
        "manage_shipments",
        "manage_inventory",
        "manage_warehouses",
    },
    "manage_payments": {"manage_payments", "manage_sales"},
    "backup_database": {
        "backup_database",
        "backup",
        "backup_db",
        "download_backup",
        "db_backup",
    },
    "restore_database": {
        "restore_database",
        "restore",
        "restore_db",
        "upload_backup",
        "db_restore",
    },
}


def _expand_perms(*names):
    """Expand aliases to concrete permission codes."""
    expanded = set()
    for n in names:
        if isinstance(n, (list, tuple, set)):
            expanded |= _expand_perms(*n)
        else:
            key = str(n).lower()
            expanded |= _PERMISSION_ALIASES.get(key, {key})
    return expanded


def _iter_rel(rel):
    """Safely iterate relationship-like objects."""
    try:
        return rel.all()
    except Exception:
        return rel or []


def _fetch_permissions_from_db(user):
    """Collect permissions from role and extra_permissions."""
    perms = set()

    if getattr(user, "role", None):
        try:
            perms |= get_role_permissions(user.role)
        except Exception:
            for p in _iter_rel(user.role.permissions):
                name = getattr(p, "name", None) or getattr(p, "code", None)
                if name:
                    perms.add(str(name).lower())

    extra_rel = getattr(user, "extra_permissions", None)
    if extra_rel is not None:
        for p in _iter_rel(extra_rel):
            name = getattr(p, "name", None) or getattr(p, "code", None)
            if name:
                perms.add(str(name).lower())

    return perms


def _get_user_permissions(user):
    """Get user permissions with Redis cache."""
    if not user:
        return set()

    key = f"user_permissions:{user.id}"
    rc = redis_client

    if rc:
        try:
            cached = rc.smembers(key)
        except Exception:
            cached = None

        if cached:

            def _to_text(v):
                if isinstance(v, str):
                    return v
                if isinstance(v, (bytes, bytearray)):
                    try:
                        return v.decode("utf-8")
                    except Exception:
                        return v.decode(errors="ignore")
                return str(v)

            return {_to_text(x).lower() for x in cached}

    perms = _fetch_permissions_from_db(user)

    try:
        if rc:
            rc.delete(key)
            if perms:
                rc.sadd(key, *list(perms))
            rc.expire(key, 300)
    except Exception:
        pass

    return perms


def permission_required(*permission_names):
    """Decorator that enforces permissions (supports aliases and super roles)."""
    base_needed = {str(p).strip().lower() for p in permission_names if p}

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Bypass if disabled globally (e.g., tests/tools)
            try:
                from flask import current_app as _ca

                cfg = getattr(_ca, "config", {})
            except Exception:
                cfg = {}

            if cfg.get("PERMISSION_DISABLED") or cfg.get("LOGIN_DISABLED"):
                return f(*args, **kwargs)

            # Super roles bypass
            try:
                role_name = str(
                    getattr(getattr(current_user, "role", None), "name", "")
                ).lower()
                if role_name in {r.lower() for r in _SUPER_ROLES}:
                    return f(*args, **kwargs)
            except Exception:
                pass

            # Must be authenticated
            if not getattr(current_user, "is_authenticated", False):
                abort(403)

            # Expand aliases
            needed = set(base_needed)
            if needed:
                try:
                    expanded = _expand_perms(*needed)
                    needed = {str(x).lower() for x in expanded}
                except Exception:
                    needed = {str(x).lower() for x in needed}

            if not needed:
                return f(*args, **kwargs)

            # Resolve user perms
            try:
                user_perms = _get_user_permissions(current_user) or set()
            except Exception:
                user_perms = set()

            # Allow if any overlap or subset (keeps legacy behavior)
            if needed.issubset(user_perms) or (user_perms & needed):
                return f(*args, **kwargs)

            # Fallback to model method if provided
            if hasattr(current_user, "has_permission") and callable(
                getattr(current_user, "has_permission")
            ):
                for p in needed:
                    if current_user.has_permission(p):
                        return f(*args, **kwargs)

            # Optional debug
            import os

            if os.environ.get("PERMISSIONS_DEBUG") == "1":
                try:
                    from flask import request as _req

                    print("\n[PERM DEBUG]")
                    print(f"Endpoint: {_req.endpoint}")
                    print(
                        "User Role:",
                        getattr(getattr(current_user, "role", None), "name", None),
                    )
                    print(f"Needed Perms: {sorted(needed)}")
                    print(f"User Perms: {sorted(user_perms)}")
                    print(f"Intersection: {user_perms & needed}")
                    print(f"Has all needed: {needed.issubset(user_perms)}")
                except Exception:
                    pass

            abort(403)

        return wrapped

    return decorator


def clear_user_permission_cache(user_id: int) -> None:
    """Clear cached permissions for a specific user."""
    if not redis_client:
        return
    try:
        redis_client.delete(f"user_permissions:{user_id}")
    except Exception:
        current_app.logger.exception(
            "Failed to clear permission cache for user %s", user_id
        )


def clear_role_permission_cache(role_id: int) -> None:
    """Clear cached permissions for a specific role."""
    if not redis_client:
        return
    try:
        redis_client.delete(f"role_permissions:{role_id}")
    except Exception:
        current_app.logger.exception(
            "Failed to clear permission cache for role %s", role_id
        )


def clear_users_cache_by_role(role_id: int):
    """Clear permission cache for all users having the given role."""
    if not redis_client:
        return

    try:
        from models import User

        ids = [
            uid
            for (uid,) in db.session.query(User.id)
            .filter(User.role_id == role_id)
            .all()
        ]
        for uid in ids:
            try:
                redis_client.delete(f"user_permissions:{uid}")
            except Exception:
                pass
    except Exception:
        pass


def get_role_permissions(role) -> set:
    """Get role permissions with Redis cache."""
    if not role:
        return set()

    key = f"role_permissions:{role.id}"
    rc = redis_client

    if rc:
        try:
            cached = rc.smembers(key)
            if cached:
                return {str(x).lower() for x in cached}
        except Exception:
            pass

    perms = set()
    for p in _iter_rel(getattr(role, "permissions", [])):
        name = getattr(p, "name", None) or getattr(p, "code", None)
        if name:
            perms.add(str(name).lower())

    try:
        if rc:
            rc.delete(key)
            if perms:
                rc.sadd(key, *list(perms))
            rc.expire(key, 300)
    except Exception:
        pass

    return perms


def log_customer_action(
    cust,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    """Write customer audit log entry."""
    from models import AuditLog

    old_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False) if new_data else None

    entry = AuditLog(
        timestamp=datetime.utcnow(),
        model_name="Customer",
        customer_id=cust.id,
        record_id=cust.id,
        user_id=(
            current_user.id
            if getattr(current_user, "is_authenticated", False)
            else None
        ),
        action=action,
        old_data=old_json,
        new_data=new_json,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(entry)
    db.session.commit()


def log_audit(
    model_name: str,
    record_id: int,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
):
    """Write generic audit log entry."""
    from models import AuditLog

    old_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False) if new_data else None

    entry = AuditLog(
        timestamp=datetime.utcnow(),
        model_name=model_name,
        record_id=record_id,
        user_id=(
            current_user.id
            if getattr(current_user, "is_authenticated", False)
            else None
        ),
        action=action,
        old_data=old_json,
        new_data=new_json,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(entry)
    db.session.commit()


def prepare_payment_form_choices(form):
    """Populate common Payment form choices."""
    form.currency.choices = [("ILS", "ILS"), ("USD", "USD"), ("EUR", "EUR")]
    form.method.choices = [
        ("cash", "cash"),
        ("cheque", "cheque"),
        ("bank", "bank"),
        ("card", "card"),
        ("online", "online"),
    ]
    form.status.choices = [
        ("PENDING", "PENDING"),
        ("COMPLETED", "COMPLETED"),
        ("REFUNDED", "REFUNDED"),
    ]
    form.direction.choices = [("IN", "IN"), ("OUT", "OUT")]
    form.entity_type.choices = [
        ("CUSTOMER", "CUSTOMER"),
        ("SUPPLIER", "SUPPLIER"),
        ("PARTNER", "PARTNER"),
        ("SALE", "SALE"),
        ("INVOICE", "INVOICE"),
        ("EXPENSE", "EXPENSE"),
        ("SHIPMENT", "SHIPMENT"),
        ("PREORDER", "PREORDER"),
        ("SERVICE", "SERVICE"),
        ("LOAN", "LOAN"),
    ]


def update_entity_balance(entity: str, eid: int) -> float:
    """Sum completed splits for an entity and return as float."""
    total_paid = (
        db.session.query(func.coalesce(func.sum(PaymentSplit.amount), 0))
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .filter(
            Payment.entity_type == entity.upper(),
            getattr(Payment, f"{entity.lower()}_id") == eid,
            Payment.status == PaymentStatus.COMPLETED.value,
        )
        .scalar()
        or 0
    )

    try:
        current_app.logger.debug(
            "update_entity_balance(%s, %s) -> %.2f", entity, eid, float(total_paid)
        )
    except Exception:
        pass

    return float(total_paid)


def customer_required(f):
    """Require current_user to be a Customer and have place_online_order perm."""
    @login_required
    @wraps(f)
    def wrapper(*args, **kwargs):
        from models import Customer

        if not isinstance(current_user, Customer):
            abort(403)
        if "place_online_order" not in _get_user_permissions(current_user):
            abort(403)
        return f(*args, **kwargs)

    return wrapper


def generate_pdf_report(data):
    """Generate a simple tabular PDF report."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    table_data = [["ID", "Name", "Balance"]] + [
        [str(item.id), item.name, f"{getattr(item, 'balance', 0):,.2f}"]
        for item in data
    ]

    table = Table(table_data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    doc.build([table])
    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"},
    )


def generate_vcf(customers, fields, filename: str = "contacts.vcf"):
    """Generate VCF cards for selected customer fields."""
    cards = []

    for c in customers:

        def _get(attr, default=""):
            try:
                v = getattr(c, attr, default)
                return v if v is not None else default
            except Exception:
                return default

        name = ""
        if "name" in fields:
            for attr in ("name", "full_name", "username"):
                name = _get(attr, "")
                if name:
                    break

        phone = ""
        if "phone" in fields:
            for attr in ("phone", "whatsapp", "mobile"):
                phone = _get(attr, "")
                if phone:
                    break

        email = _get("email", "") if "email" in fields else ""

        card = ["BEGIN:VCARD", "VERSION:3.0"]
        if name:
            card.append(f"N:{name}")
            card.append(f"FN:{name}")
        if phone:
            card.append(f"TEL:{phone}")
        if email:
            card.append(f"EMAIL:{email}")
        card.append("END:VCARD")

        cards.append("\r\n".join(card))

    payload = ("\r\n".join(cards) + "\r\n").encode("utf-8")
    resp = make_response(payload)
    resp.mimetype = "text/vcard"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def generate_csv_contacts(customers, fields):
    """Generate CSV for selected customer fields."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(fields)

    for c in customers:
        w.writerow([getattr(c, f) or "" for f in fields])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


def generate_excel_contacts(customers, fields):
    """Generate Excel for selected customer fields."""
    from openpyxl import Workbook

    stream = io.BytesIO()
    wb = Workbook()
    ws = wb.active

    ws.append(fields)
    for c in customers:
        ws.append([getattr(c, f) or "" for f in fields])

    wb.save(stream)
    stream.seek(0)

    return Response(
        stream.getvalue(),
        mimetype=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": "attachment; filename=contacts.xlsx"},
    )

def luhn_check(card_number: str) -> bool:
    """تحقق Luhn لرقم البطاقة (digits only)."""
    if not card_number:
        return False
    digits = "".join(ch for ch in card_number if ch.isdigit())
    if not digits:
        return False
    s, alt = 0, False
    for d in digits[::-1]:
        n = ord(d) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return (s % 10) == 0

def is_valid_expiry_mm_yy(s: str) -> bool:
    """تحقق من MM/YY وأنه في الحاضر/المستقبل (UTC)."""
    if not s or not re.match(r"^\d{2}/\d{2}$", s):
        return False
    mm_str, yy_str = s.split("/")
    try:
        mm = int(mm_str)
        yy = int("20" + yy_str)
        if not (1 <= mm <= 12):
            return False
        now = datetime.utcnow()
        y, m = now.year, now.month
        # نعتبر الشهر الحالي صالح
        return (yy > y) or (yy == y and mm >= m)
    except Exception:
        return False

def get_fernet():
    """أرجع كائن Fernet بناءً على CARD_ENC_KEY من الإعدادات. قد يرجع None."""
    key = current_app.config.get("CARD_ENC_KEY")
    if not key or Fernet is None:
        return None
    if isinstance(key, str):
        key = key.encode("utf-8")
    try:
        return Fernet(key)
    except Exception:
        return None

def encrypt_card_number(pan: str) -> bytes | None:
    """شفر رقم البطاقة (PAN). يرجع None إن لم يكن التشفير مفعّل."""
    f = get_fernet()
    if not f:
        return None
    digits = "".join(ch for ch in (pan or "") if ch.isdigit())
    if not digits:
        return None
    return f.encrypt(digits.encode("utf-8"))

def decrypt_card_number(token: bytes) -> str | None:
    """فك تشفير PAN. يرجع None إن لم يكن التشفير مفعّل/فشل."""
    f = get_fernet()
    if not f or not token:
        return None
    try:
        return f.decrypt(token).decode("utf-8")
    except Exception:
        return None

def card_fingerprint(pan: str) -> str | None:
    """بصمة SHA-256 لرقم البطاقة (لا تتطلب فك تشفير لاحقًا)."""
    digits = "".join(ch for ch in (pan or "") if ch.isdigit())
    if not digits:
        return None
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()

def detect_card_brand(pan: str) -> str:
    """كشف ماركة البطاقة بشكل مبسط."""
    digits = "".join(ch for ch in (pan or "") if ch.isdigit())
    if not digits:
        return "UNKNOWN"
    if digits.startswith("4"):
        return "VISA"
    i2 = int(digits[:2]) if len(digits) >= 2 else -1
    i4 = int(digits[:4]) if len(digits) >= 4 else -1
    if 51 <= i2 <= 55 or (2221 <= i4 <= 2720):
        return "MASTERCARD"
    if i2 in (34, 37):
        return "AMEX"
    return "UNKNOWN"

def testable_login_required(f):
    """
    Like flask_login.login_required but allows access in TESTING mode
    when current_user is not authenticated. Keeps production behavior.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            if (
                current_app
                and current_app.config.get("TESTING")
                and not getattr(current_user, "is_authenticated", False)
            ):
                return f(*args, **kwargs)
        except Exception:
            pass
        return login_required(f)(*args, **kwargs)

    return wrapped
