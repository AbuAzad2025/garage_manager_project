import base64, csv, io, json, re, hashlib, os
from datetime import datetime
from functools import wraps

from flask import Response, abort, current_app, flash, make_response, request
from flask_login import current_user, login_required
from flask_mail import Message
import redis
from sqlalchemy import func, case, select
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

try:
    import qrcode
except Exception:
    qrcode = None

# ReportLab اختياري
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:
    colors = letter = SimpleDocTemplate = Table = TableStyle = None

# تشفير اختياري
try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None

from extensions import db, mail
from models import PaymentStatus, Payment, PaymentSplit

redis_client: redis.Redis | None = None


# ============================== Object fetch helper ==============================

def _get_or_404(model, ident, *, load_options=None, pk_name: str = "id"):
    """أحضر سجلًا وإلا 404. يدعم options وبديل لاسم الـ PK."""
    try:
        if pk_name == "id" and not load_options:
            obj = db.session.get(model, ident)
        else:
            stmt = select(model)
            if load_options:
                stmt = stmt.options(*load_options)
            stmt = stmt.where(getattr(model, pk_name) == ident)
            obj = db.session.execute(stmt).scalar_one_or_none()
    except Exception:
        obj = None
    if obj is None:
        abort(404)
    return obj


# ============================== Bootstrap & Filters ==============================

def init_app(app):
    """تسجيل فلاتر Jinja وتهيئة Redis."""
    global redis_client
    app.jinja_env.filters.update({
        "format_currency": format_currency,
        "format_percent": format_percent,
        "format_date": format_date,
        "format_datetime": format_datetime,
        "yes_no": yes_no,
        "status_label": status_label,
    })
    try:
        rc = redis.StrictRedis.from_url(app.config.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        if getattr(rc, "ping", None):
            rc.ping()
        redis_client = rc
    except Exception:
        redis_client = None


# ============================== Notifications ==============================

def send_email_notification(subject, recipients, body, html=None):
    mail.send(Message(subject=subject, recipients=recipients, body=body, html=html))


def send_whatsapp_message(to_number, body) -> bool:
    sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_WHATSAPP_NUMBER")
    if not all([sid, token, from_number]):
        flash("❌ لم يتم تكوين خدمة واتساب. الرجاء مراجعة إعدادات Twilio.", "danger")
        return False
    try:
        Client(sid, token).messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}",
            body=body,
        )
        return True
    except TwilioRestException as e:
        flash(f"❌ خطأ أثناء إرسال واتساب: {str(e)}", "danger")
        return False


# ============================== Formatters & Helpers ==============================

def format_currency(value):
    try:
        return f"{float(value):,.2f} ₪"
    except Exception:
        return "0.00 ₪"


def format_percent(value):
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "0.00%"


def format_date(value, fmt: str = "%Y-%m-%d"):
    try:
        return value.strftime(fmt) if value else "-"
    except Exception:
        return "-"


def format_datetime(value, fmt: str = "%Y-%m-%d %H:%M"):
    try:
        return value.strftime(fmt) if value else ""
    except Exception:
        return ""


def active_archived(value):
    return "نشط" if value else "مؤرشف"


def yes_no(value):
    return active_archived(value)


def status_label(status):
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
    if not qrcode:
        current_app.logger.warning("qrcode غير متوفر")
        return ""
    img = qrcode.make(value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def recent_notes(limit: int = 5):
    from models import Note
    return Note.query.order_by(Note.created_at.desc()).limit(limit).all()


# ============================== Reports: Excel/PDF/VCF/CSV ==============================

def generate_excel_report(data, filename: str = "report.xlsx") -> Response:
    def _row_to_dict(item):
        if hasattr(item, "to_dict"):
            try:
                return item.to_dict()
            except Exception:
                pass
        if isinstance(item, dict):
            return item
        try:
            cols = {}
            for k in dir(item):
                if k.startswith("_"): continue
                v = getattr(item, k, None)
                if callable(v): continue
                if k in ("metadata", "query", "query_class"): continue
                if hasattr(v, "property"): continue
                cols[k] = v
            return cols
        except Exception:
            return {"value": str(item)}

    rows = [_row_to_dict(x) for x in data]

    try:
        import pandas as pd
    except Exception:
        buf = io.StringIO()
        if rows:
            fieldnames = sorted({k for r in rows for k in r.keys()})
            w = csv.DictWriter(buf, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fieldnames})
        else:
            buf.write("")
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename.rsplit('.',1)[0]}.csv"},
        )

    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def generate_pdf_report(data):
    if not all([colors, letter, SimpleDocTemplate, Table, TableStyle]):
        abort(500, description="ReportLab غير متوفر على الخادم")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table_data = [["ID", "Name", "Balance"]] + [
        [str(item.id), getattr(item, "name", ""), f"{getattr(item, 'balance', 0):,.2f}"]
        for item in data
    ]
    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    doc.build([table])
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"},
    )


def generate_vcf(customers, fields, filename: str = "contacts.vcf"):
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
                if name: break

        phone = ""
        if "phone" in fields:
            for attr in ("phone", "whatsapp", "mobile"):
                phone = _get(attr, "")
                if phone: break

        email = _get("email", "") if "email" in fields else ""

        card = ["BEGIN:VCARD", "VERSION:3.0"]
        if name:
            card.append(f"N:{name}")
            card.append(f"FN:{name}")
        if phone:
            card.append(f"TEL;TYPE=CELL:{phone}")
        if email:
            card.append(f"EMAIL;TYPE=INTERNET:{email}")
        card.append("END:VCARD")
        cards.append("\r\n".join(card))

    payload = ("\r\n".join(cards) + "\r\n").encode("utf-8")
    resp = make_response(payload)
    resp.mimetype = "text/vcard"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def generate_csv_contacts(customers, fields):
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(fields)
    for c in customers:
        w.writerow([getattr(c, f, "") or "" for f in fields])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


def generate_excel_contacts(customers, fields):
    try:
        from openpyxl import Workbook
    except Exception:
        abort(500, description="openpyxl غير متوفر على الخادم")
    stream = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(fields)
    for c in customers:
        ws.append([getattr(c, f, "") or "" for f in fields])
    wb.save(stream)
    stream.seek(0)
    return Response(
        stream.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contacts.xlsx"},
    )


# ============================== Permissions & Caching ==============================

_SUPER_ROLES = {"developer", "owner", "admin", "super_admin"}

_PERMISSION_ALIASES = {
    "view_warehouses": {"view_warehouses", "view_inventory", "manage_inventory", "manage_warehouses"},
    "view_inventory": {"view_inventory", "manage_inventory", "manage_warehouses"},
    "manage_inventory": {"manage_inventory", "manage_warehouses", "manage_stock", "warehouse_transfer"},
    "warehouse_transfer": {"warehouse_transfer", "manage_inventory", "manage_warehouses"},
    "view_parts": {"view_parts", "view_inventory", "manage_inventory"},
    "view_preorders": {"view_preorders", "view_inventory", "manage_inventory"},
    "add_preorder": {"add_preorder", "manage_inventory"},
    "edit_preorder": {"edit_preorder", "manage_inventory"},
    "delete_preorder": {"delete_preorder", "manage_inventory"},
    "add_customer": {"add_customer", "manage_customers"},
    "add_supplier": {"add_supplier", "manage_vendors"},
    "add_partner": {"add_partner", "manage_vendors"},
    "manage_shipments": {"manage_shipments", "manage_inventory", "manage_warehouses"},
    "manage_payments": {"manage_payments", "manage_sales"},
    "backup_database": {"backup_database", "backup", "backup_db", "download_backup", "db_backup"},
    "restore_database": {"restore_database", "restore", "restore_db", "upload_backup", "db_restore"},
}


def _expand_perms(*names):
    expanded = set()
    for n in names:
        if isinstance(n, (list, tuple, set)):
            expanded |= _expand_perms(*n)
        else:
            key = str(n).lower()
            expanded |= _PERMISSION_ALIASES.get(key, {key})
    return expanded


def _iter_rel(rel):
    try:
        return rel.all()
    except Exception:
        return rel or []


def _fetch_permissions_from_db(user):
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
                if isinstance(v, str): return v
                if isinstance(v, (bytes, bytearray)):
                    try: return v.decode("utf-8")
                    except Exception: return v.decode(errors="ignore")
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
    """ديكورتر صلاحيات؛ يدعم OR افتراضيًا و AND عبر PERMISSIONS_REQUIRE_ALL."""
    base_needed = {str(p).strip().lower() for p in permission_names if p}

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                cfg = getattr(current_app, "config", {})
            except Exception:
                cfg = {}
            if cfg.get("PERMISSION_DISABLED") or cfg.get("LOGIN_DISABLED"):
                return f(*args, **kwargs)

            try:
                role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
                if role_name in {r.lower() for r in _SUPER_ROLES}:
                    return f(*args, **kwargs)
            except Exception:
                pass

            if not getattr(current_user, "is_authenticated", False):
                abort(403)

            needed = set(base_needed)
            if needed:
                try:
                    needed = {str(x).lower() for x in _expand_perms(*needed)}
                except Exception:
                    needed = {str(x).lower() for x in needed}

            if not needed:
                return f(*args, **kwargs)

            try:
                user_perms = _get_user_permissions(current_user) or set()
            except Exception:
                user_perms = set()

            require_all = bool(cfg.get("PERMISSIONS_REQUIRE_ALL"))
            allowed = needed.issubset(user_perms) if require_all else bool(user_perms & needed or needed.issubset(user_perms))
            if allowed:
                return f(*args, **kwargs)

            if hasattr(current_user, "has_permission") and callable(getattr(current_user, "has_permission")):
                if require_all:
                    if all(current_user.has_permission(p) for p in needed): return f(*args, **kwargs)
                else:
                    for p in needed:
                        if current_user.has_permission(p):
                            return f(*args, **kwargs)

            if os.environ.get("PERMISSIONS_DEBUG") == "1":
                try:
                    print("\n[PERM DEBUG]")
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
    if not redis_client:
        return
    try:
        redis_client.delete(f"user_permissions:{user_id}")
    except Exception:
        current_app.logger.exception("Failed to clear permission cache for user %s", user_id)


def clear_role_permission_cache(role_id: int) -> None:
    if not redis_client:
        return
    try:
        redis_client.delete(f"role_permissions:{role_id}")
    except Exception:
        current_app.logger.exception("Failed to clear permission cache for role %s", role_id)


def clear_users_cache_by_role(role_id: int):
    if not redis_client:
        return
    try:
        from models import User
        ids = [uid for (uid,) in db.session.query(User.id).filter(User.role_id == role_id).all()]
        for uid in ids:
            try: redis_client.delete(f"user_permissions:{uid}")
            except Exception: pass
    except Exception:
        pass


def get_role_permissions(role) -> set:
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


# ============================== Auditing Helpers ==============================

def log_customer_action(cust, action: str, old_data: dict | None = None, new_data: dict | None = None) -> None:
    from models import AuditLog
    old_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False) if new_data else None
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        model_name="Customer",
        customer_id=cust.id,
        record_id=cust.id,
        user_id=(current_user.id if getattr(current_user, "is_authenticated", False) else None),
        action=action,
        old_data=old_json,
        new_data=new_json,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(entry)
    db.session.commit()

def _audit(event: str, *, ok: bool = True, user_id=None, customer_id=None, note: str | None = None, extra: dict | None = None) -> None:
    try:
        from models import AuditLog
        details_old = {"ok": bool(ok)}
        if note:
            details_old["note"] = str(note)
        record_id = None
        if customer_id is not None:
            record_id = int(customer_id)
        elif user_id is not None:
            record_id = int(user_id)

        old_json = json.dumps(details_old, ensure_ascii=False) if details_old else None
        new_json = json.dumps(extra, ensure_ascii=False) if extra else None

        entry = AuditLog(
            timestamp=datetime.utcnow(),
            model_name="Auth",
            record_id=record_id,
            user_id=(user_id if user_id is not None else (getattr(current_user, "id", None) if getattr(current_user, "is_authenticated", False) else None)),
            action=str(event),
            old_data=old_json,
            new_data=new_json,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        try:
            current_app.logger.warning("audit skipped: event=%s ok=%s note=%s", event, ok, note)
        except Exception:
            pass

def log_audit(model_name: str, record_id: int, action: str, old_data: dict | None = None, new_data: dict | None = None):
    from models import AuditLog
    old_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False) if new_data else None
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        model_name=model_name,
        record_id=record_id,
        user_id=(current_user.id if getattr(current_user, "is_authenticated", False) else None),
        action=action,
        old_data=old_json,
        new_data=new_json,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(entry)
    db.session.commit()


# ============================== Payments & Forms ==============================

def prepare_payment_form_choices(form, *, compat_post: bool = False, arabic_labels: bool = True):
    if hasattr(form, "currency"):
        form.currency.choices = (
            [("ILS", "شيكل"), ("USD", "دولار"), ("EUR", "يورو")]
            if arabic_labels else [("ILS", "ILS"), ("USD", "USD"), ("EUR", "EUR")]
        )
    if hasattr(form, "method"):
        form.method.choices = [
            ("cash",   "نقداً" if arabic_labels else "cash"),
            ("cheque", "شيك"   if arabic_labels else "cheque"),
            ("bank",   "تحويل" if arabic_labels else "bank"),
            ("card",   "بطاقة" if arabic_labels else "card"),
            ("online", "إلكتروني" if arabic_labels else "online"),
        ]
    if hasattr(form, "status"):
        form.status.choices = [
            ("COMPLETED", "مكتملة"       if arabic_labels else "COMPLETED"),
            ("PENDING",   "قيد الانتظار" if arabic_labels else "PENDING"),
            ("FAILED",    "فاشلة"        if arabic_labels else "FAILED"),
            ("REFUNDED",  "مُرجعة"       if arabic_labels else "REFUNDED"),
        ]
    if hasattr(form, "direction"):
        base = [("INCOMING", "وارد" if arabic_labels else "INCOMING"),
                ("OUTGOING", "صادر" if arabic_labels else "OUTGOING")]
        if compat_post:
            base += [("IN", "وارد" if arabic_labels else "IN"),
                     ("OUT", "صادر" if arabic_labels else "OUT")]
        form.direction.choices = base
    if hasattr(form, "entity_type"):
        form.entity_type.choices = [
            ("CUSTOMER", "عميل"),
            ("SUPPLIER", "مورد"),
            ("PARTNER",  "شريك"),
            ("SALE",     "بيع"),
            ("INVOICE",  "فاتورة"),
            ("EXPENSE",  "مصروف"),
            ("SHIPMENT", "شحنة"),
            ("PREORDER", "حجز"),
            ("SERVICE",  "صيانة"),
            ("LOAN",     "تسوية قرض"),
        ]


def update_entity_balance(entity: str, eid: int) -> float:
    entity = entity.upper()
    col = getattr(Payment, f"{entity.lower()}_id")
    total = (
        db.session.query(
            func.coalesce(
                func.sum(
                    case(
                        (Payment.direction.in_(("INCOMING", "IN")), PaymentSplit.amount),
                        else_=-PaymentSplit.amount,
                    )
                ),
                0,
            )
        )
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .filter(
            Payment.entity_type == entity,
            col == eid,
            Payment.status == PaymentStatus.COMPLETED.value,
        )
        .scalar()
        or 0
    )
    try:
        current_app.logger.debug("update_entity_balance(%s, %s) -> %.2f", entity, eid, float(total))
    except Exception:
        pass
    return float(total)


# ============================== Auth Decorators ==============================

def customer_required(f):
    @login_required
    @wraps(f)
    def wrapper(*args, **kwargs):
        from models import Customer
        if not isinstance(current_user, Customer): abort(403)
        if "place_online_order" not in _get_user_permissions(current_user): abort(403)
        return f(*args, **kwargs)
    return wrapper


def testable_login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            if current_app and current_app.config.get("TESTING") and not getattr(current_user, "is_authenticated", False):
                return f(*args, **kwargs)
        except Exception:
            pass
        return login_required(f)(*args, **kwargs)
    return wrapped


# ============================== Card Utilities ==============================

def luhn_check(card_number: str) -> bool:
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
        return (yy > y) or (yy == y and mm >= m)
    except Exception:
        return False


def get_fernet():
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
    f = get_fernet()
    if not f:
        return None
    digits = "".join(ch for ch in (pan or "") if ch.isdigit())
    if not digits:
        return None
    return f.encrypt(digits.encode("utf-8"))


def decrypt_card_number(token: bytes) -> str | None:
    f = get_fernet()
    if not f or not token:
        return None
    try:
        return f.decrypt(token).decode("utf-8")
    except Exception:
        return None


def card_fingerprint(pan: str) -> str | None:
    digits = "".join(ch for ch in (pan or "") if ch.isdigit())
    if not digits:
        return None
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def detect_card_brand(pan: str) -> str:
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
