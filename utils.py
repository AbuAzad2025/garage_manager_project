import base64
import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Callable, Dict, Iterable, List, Optional
import redis
from flask import Response, abort, current_app, flash, make_response, request, jsonify
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy import case, func, select, or_
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

try:
    import qrcode
except Exception:
    qrcode = None

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:
    colors = letter = SimpleDocTemplate = Table = TableStyle = None

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None

from extensions import limiter, db, mail
from models import (
    Payment,
    PaymentSplit,
    PaymentStatus,
    PaymentMethod,
    PaymentDirection,
    PaymentEntityType,
    D,
    q,
)

redis_client: redis.Redis | None = None

_TWOPLACES = Decimal("0.01")

def _D(x):
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

def _q2(x):
    return _D(x).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)

def _q(x):
    return q(x)

def _get_or_404(model, ident, *, load_options=None, pk_name: str = "id"):
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

def search_model(
    model,
    search_fields,
    *,
    label_attr: str = "name",
    value_attr: str = "id",
    extra_filters: list | tuple | None = None,
    limit_default: int = 20,
    serializer=None,
    q_param: str = "q",
    **kwargs,
):
    q = (request.args.get(q_param) or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit") or limit_default), 100))
    except Exception:
        limit = limit_default
    try:
        page = max(1, int(request.args.get("page") or 1))
    except Exception:
        page = 1

    query = db.session.query(model)
    if extra_filters:
        query = query.filter(*extra_filters)

    if q:
        ors = []
        q_low = q.lower()
        for field_name in (search_fields or []):
            col = getattr(model, field_name, None)
            if col is not None:
                ors.append(func.lower(col).like(f"%{q_low}%"))
        if q.isdigit() and hasattr(model, value_attr):
            try:
                ors.append(getattr(model, value_attr) == int(q))
            except Exception:
                pass
        if ors:
            query = query.filter(or_(*ors))

    if hasattr(model, label_attr):
        query = query.order_by(getattr(model, label_attr).asc())
    elif hasattr(model, value_attr):
        query = query.order_by(getattr(model, value_attr).asc())

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()

    def _serialize(obj):
        if serializer:
            d = serializer(obj)
        else:
            d = {
                "id": getattr(obj, value_attr, None),
                "text": getattr(obj, label_attr, None) or str(getattr(obj, value_attr, "")),
            }
        if "name" not in d:
            d["name"] = d.get("text")
        return d

    results = [_serialize(o) for o in items]
    return jsonify({"results": results, "pagination": {"more": (page * limit) < total}})

def _limit(spec: str):
    return limiter.limit(spec)

def _query_limit(default: int = 20, maximum: int = 50) -> int:
    """يعطي limit للـ SQLAlchemy query من ?limit= مع ضبط الحد الأقصى."""
    try:
        limit = int(request.args.get("limit", default))
    except Exception:
        limit = default
    return min(max(limit, 1), maximum)

def init_app(app):
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

    def _acl_ctx():
        def can(code: str) -> bool:
            try:
                return bool(getattr(current_user, "is_authenticated", False) and current_user.has_permission(code))
            except Exception:
                return False
        return dict(
            can=can,
            can_super=lambda: is_super(),
            can_admin=lambda: is_admin(),
        )
    app.context_processor(_acl_ctx)
    _install_acl_cache_listeners()
    _install_accounting_listeners()
from datetime import datetime
from sqlalchemy import select

def send_email_notification(subject, recipients, body, html=None):
    mail.send(Message(subject=subject, recipients=recipients, body=body, html=html))


def _to_e164(msisdn: str) -> str | None:
    raw = (msisdn or "").strip()
    if not raw:
        return None
    if raw.startswith("+"):
        s = "+" + re.sub(r"\D", "", raw[1:])
        digits = re.sub(r"\D", "", s)
        return s if len(digits) >= 7 else None
    s = re.sub(r"\D", "", raw)
    if not s:
        return None
    if s.startswith("00"):
        s = s[2:]
    cc = str(current_app.config.get("TWILIO_DEFAULT_COUNTRY_CODE") or "").lstrip("+")
    if cc:
        if s.startswith("0"):
            s = cc + s[1:]
        elif not s.startswith(cc):
            s = cc + s
    return "+" + s


def send_whatsapp_message(to_number, body) -> tuple[bool, str]:
    sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_WHATSAPP_NUMBER")
    if not all([sid, token, from_number]):
        return (False, "Twilio credentials missing")
    to_e164 = _to_e164(to_number)
    if not to_e164:
        return (False, "Invalid recipient number")
    try:
        msg = Client(sid, token).messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_e164}",
            body=body,
        )
        return (True, msg.sid)
    except TwilioRestException as e:
        code = getattr(e, "code", "")
        msg = getattr(e, "msg", str(e))
        return (False, f"{code} {msg}")
    except Exception as e:
        return (False, str(e))


def format_currency(value):
    try:
        return f"{float(_q2(value)):,.2f} ₪"
    except Exception:
        return "0.00 ₪"


def format_percent(value):
    try:
        return f"{float(_q2(value)):.2f}%"
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
        return ""
    img = qrcode.make(value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _get_id(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if "|" in s:
            s = s.split("|", 1)[0]
        try:
            return int(float(s))
        except Exception:
            return None
    if isinstance(v, dict):
        return _get_id(v.get("id"))
    if isinstance(v, (list, tuple)) and v:
        return _get_id(v[0])
    return None

def _apply_stock_delta(product_id: int, warehouse_id: int, delta: int) -> int:
    from models import StockLevel
    delta = int(delta or 0)
    rec = (
        StockLevel.query
        .filter_by(product_id=product_id, warehouse_id=warehouse_id)
        .with_for_update(read=False)
        .first()
    )
    if rec is None:
        if delta < 0:
            raise ValueError("insufficient stock")
        rec = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0)
        db.session.add(rec)
        db.session.flush()
    new_qty = int(rec.quantity or 0) + delta
    reserved = int(getattr(rec, "reserved_quantity", 0) or 0)
    if new_qty < 0 or new_qty < reserved:
        raise ValueError("insufficient stock")
    rec.quantity = new_qty
    db.session.flush()
    return new_qty


def recent_notes(limit: int = 5):
    from models import Note
    return Note.query.order_by(Note.created_at.desc()).limit(limit).all()


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
                if k.startswith("_"):
                    continue
                v = getattr(item, k, None)
                if callable(v):
                    continue
                if k in ("metadata", "query", "query_class"):
                    continue
                if hasattr(v, "property"):
                    continue
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
            headers={"Content-Disposition": f"attachment; filename=\"{filename.rsplit('.',1)[0]}.csv\""},
        )

    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
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
        headers={"Content-Disposition": "attachment; filename=\"report.pdf\""},
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
            card.append(f"TEL;TYPE=CELL:{phone}")
        if email:
            card.append(f"EMAIL;TYPE=INTERNET:{email}")
        card.append("END:VCARD")
        cards.append("\r\n".join(card))

    payload = ("\r\n".join(cards) + "\r\n").encode("utf-8")
    resp = make_response(payload)
    resp.mimetype = "text/vcard"
    resp.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
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
        headers={"Content-Disposition": "attachment; filename=\"contacts.csv\""},
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
        headers={"Content-Disposition": "attachment; filename=\"contacts.xlsx\""},
    )


_SUPER_ROLES = {"developer", "owner", "super_admin", "super"}

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
    "view_shop": {"view_shop", "browse_products"},
    "browse_products": {"browse_products", "view_shop"},
    "manage_shop": {"manage_shop", "view_shop", "browse_products"}
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


def _csv_set(val):
    if not val:
        return set()
    return {x.strip().lower() for x in str(val).split(",") if x.strip()}


def _match_user(user, ids_csv, emails_csv) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    ids = _csv_set(ids_csv)
    emails = _csv_set(emails_csv)
    if str(getattr(user, "id", "")).lower() in ids:
        return True
    email = (getattr(user, "email", "") or "").lower()
    return email in emails


def is_super() -> bool:
    try:
        if _match_user(
            current_user,
            current_app.config.get("SUPER_USER_IDS"),
            current_app.config.get("SUPER_USER_EMAILS"),
        ):
            return True
    except Exception:
        pass
    try:
        role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
        return role_name in {r.lower() for r in _SUPER_ROLES}
    except Exception:
        return False


def is_admin() -> bool:
    if is_super():
        return True
    try:
        if _match_user(
            current_user,
            current_app.config.get("ADMIN_USER_IDS"),
            current_app.config.get("ADMIN_USER_EMAILS"),
        ):
            return True
    except Exception:
        pass
    try:
        role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
        if role_name == "admin":
            return True
    except Exception:
        pass
    return bool(getattr(current_user, "is_admin", False))


def super_only(f):
    @wraps(f)
    def _w(*args, **kwargs):
        if not is_super():
            abort(403)
        return f(*args, **kwargs)
    return _w


def admin_or_super(f):
    @wraps(f)
    def _w(*args, **kwargs):
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return _w


def permission_required(*permission_names):
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
            if is_super():
                return f(*args, **kwargs)
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
                    if all(current_user.has_permission(p) for p in needed):
                        return f(*args, **kwargs)
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
        pass


def clear_role_permission_cache(role_id: int) -> None:
    if not redis_client:
        return
    try:
        redis_client.delete(f"role_permissions:{role_id}")
    except Exception:
        pass


def clear_users_cache_by_role(role_id: int):
    if not redis_client:
        return
    try:
        from models import User
        ids = [uid for (uid,) in db.session.query(User.id).filter(User.role_id == role_id).all()]
        for uid in ids:
            try:
                redis_client.delete(f"user_permissions:{uid}")
            except Exception:
                pass
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


def _install_acl_cache_listeners():
    try:
        from sqlalchemy import event
        from models import Role, User, role_permissions as _rp, user_permissions as _up
    except Exception:
        return

    def _role_perm_change(target, value, initiator):
        try:
            if getattr(target, "id", None) is not None:
                clear_role_permission_cache(target.id)
                clear_users_cache_by_role(target.id)
        except Exception:
            pass
        return value

    def _user_extra_perm_change(target, value, initiator):
        try:
            if getattr(target, "id", None) is not None:
                clear_user_permission_cache(target.id)
        except Exception:
            pass
        return value

    def _user_role_set(target, value, oldvalue, initiator):
        try:
            if getattr(target, "id", None) is not None:
                clear_user_permission_cache(target.id)
        except Exception:
            pass
        try:
            if getattr(oldvalue, "id", None):
                clear_users_cache_by_role(oldvalue.id)
            if getattr(value, "id", None):
                clear_users_cache_by_role(value.id)
        except Exception:
            pass
        return value

    try:
        event.listen(Role.permissions, "append", _role_perm_change)
        event.listen(Role.permissions, "remove", _role_perm_change)
    except Exception:
        pass

    try:
        event.listen(User.extra_permissions, "append", _user_extra_perm_change)
        event.listen(User.extra_permissions, "remove", _user_extra_perm_change)
        event.listen(User.role, "set", _user_role_set, retval=True)
    except Exception:
        pass


def log_customer_action(cust, action: str, old_data: dict | None = None, new_data: dict | None = None) -> None:
    from models import AuditLog
    old_json = json.dumps(old_data, ensure_ascii=False, default=str) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False, default=str) if new_data else None
    entry = AuditLog(
        created_at=datetime.utcnow(),
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
    db.session.flush()


def _audit(event: str, *, ok: bool = True, user_id=None, customer_id=None, note: str | None = None, extra: dict | None = None) -> None:
    from models import AuditLog
    details_old = {"ok": bool(ok)}
    if note:
        details_old["note"] = str(note)
    record_id = int(customer_id) if customer_id is not None else (int(user_id) if user_id is not None else None)
    old_json = json.dumps(details_old, ensure_ascii=False, default=str) if details_old else None
    new_json = json.dumps(extra, ensure_ascii=False, default=str) if extra else None
    entry = AuditLog(
        created_at=datetime.utcnow(),
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
    db.session.flush()


def log_audit(model_name: str, record_id: int, action: str, old_data: dict | None = None, new_data: dict | None = None):
    from models import AuditLog
    old_json = json.dumps(old_data, ensure_ascii=False, default=str) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False, default=str) if new_data else None
    entry = AuditLog(
        created_at=datetime.utcnow(),
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
    db.session.flush()


_ENUM_AR = {
    "PaymentMethod": {"cash": "نقداً", "bank": "تحويل", "card": "بطاقة", "cheque": "شيك", "online": "إلكتروني"},
    "PaymentStatus": {"PENDING": "قيد الانتظار", "COMPLETED": "مكتملة", "FAILED": "فاشلة", "REFUNDED": "مُرجعة"},
    "PaymentDirection": {"IN": "وارد", "OUT": "صادر"},
    "PaymentEntityType": {
        "CUSTOMER": "عميل", "SUPPLIER": "مورد", "PARTNER": "شريك", "SHIPMENT": "شحنة",
        "EXPENSE": "مصروف", "LOAN": "قرض", "SALE": "بيع", "INVOICE": "فاتورة",
        "PREORDER": "حجز", "SERVICE": "صيانة"
    },
}

def _enum_choices(enum_cls, arabic_labels=True):
    if not arabic_labels:
        return [(e.value, e.value) for e in enum_cls]
    lab = _ENUM_AR.get(enum_cls.__name__, {})
    return [(e.value, lab.get(e.value, e.value)) for e in enum_cls]


def prepare_payment_form_choices(form, *, compat_post: bool = False, arabic_labels: bool = True):
    if hasattr(form, "currency"):
        form.currency.choices = (
            [("ILS", "شيكل"), ("USD", "دولار"), ("EUR", "يورو"), ("JOD", "دينار")]
            if arabic_labels else [("ILS", "ILS"), ("USD", "USD"), ("EUR", "EUR"), ("JOD", "JOD")]
        )
    if hasattr(form, "method"):
        form.method.choices = _enum_choices(PaymentMethod, arabic_labels)
    if hasattr(form, "status"):
        form.status.choices = _enum_choices(PaymentStatus, arabic_labels)
    if hasattr(form, "direction"):
        base = _enum_choices(PaymentDirection, arabic_labels)
        if compat_post:
            extra = [("INCOMING", "وارد" if arabic_labels else "INCOMING"),
                     ("OUTGOING", "صادر" if arabic_labels else "OUTGOING")]
            seen = {v for v, _ in base}
            base += [x for x in extra if x[0] not in seen]
        form.direction.choices = base
    if hasattr(form, "entity_type"):
        form.entity_type.choices = _enum_choices(PaymentEntityType, arabic_labels)


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
    return float(_q2(total))


def customer_required(f):
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

def is_valid_ean13(code: str) -> bool:
    """تحقق من صحة باركود EAN-13"""
    if not code or len(code) != 13 or not code.isdigit():
        return False
    digits = [int(d) for d in code]
    checksum = (10 - ((sum(digits[::2]) + sum(d * 3 for d in digits[1:-1:2])) % 10)) % 10
    return checksum == digits[-1]

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

def _install_accounting_listeners():
    try:
        from sqlalchemy import event
        from sqlalchemy.orm import object_session
        from decimal import Decimal, ROUND_HALF_UP
        from models import Payment, PaymentStatus, Sale, SaleLine
        Q = Decimal("0.01")
    except Exception:
        return

    def _q2(x):
        try:
            return Decimal(str(x or 0)).quantize(Q, rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal("0.00")

    def _recompute_sale_totals(sess, sale_id: int):
        sale = sess.get(Sale, sale_id)
        if not sale:
            return
        total = Decimal("0.00")
        for ln in sale.lines or []:
            q = _q2(ln.quantity)
            p = _q2(ln.unit_price)
            dr = _q2(ln.discount_rate)
            tr = _q2(ln.tax_rate)
            base = (q * p * (Decimal("1") - dr / Decimal("100"))).quantize(Q, rounding=ROUND_HALF_UP)
            line = (base * (Decimal("1") + tr / Decimal("100"))).quantize(Q, rounding=ROUND_HALF_UP)
            total += line
        try:
            sale.total_amount = float(total)
        except Exception:
            pass
        sess.add(sale)

    def _recompute_sale_payments(sess, sale_id: int):
        sale = sess.get(Sale, sale_id)
        if not sale:
            return
        paid = Decimal("0.00")
        for p in sale.payments or []:
            if getattr(p, "status", None) == PaymentStatus.COMPLETED.value:
                paid += _q2(p.total_amount)
        try:
            sale.total_paid = float(paid)
        except Exception:
            pass
        try:
            bal = _q2(sale.total_amount) - _q2(sale.total_paid)
            sale.balance_due = float(bal)
        except Exception:
            pass
        if hasattr(sale, "update_payment_status"):
            try:
                sale.update_payment_status()
            except Exception:
                pass
        sess.add(sale)

    @event.listens_for(Payment, "after_insert")
    @event.listens_for(Payment, "after_update")
    def _pmt_upd(mapper, conn, target):
        sess = object_session(target)
        if not sess or not getattr(target, "sale_id", None):
            return
        _recompute_sale_payments(sess, int(target.sale_id))

    @event.listens_for(Payment, "after_delete")
    def _pmt_del(mapper, conn, target):
        sess = object_session(target)
        if not sess or not getattr(target, "sale_id", None):
            return
        _recompute_sale_payments(sess, int(target.sale_id))

    @event.listens_for(SaleLine, "after_insert")
    @event.listens_for(SaleLine, "after_update")
    @event.listens_for(SaleLine, "after_delete")
    def _line_changed(mapper, conn, target):
        sess = object_session(target)
        if not sess or not getattr(target, "sale_id", None):
            return
        _recompute_sale_totals(sess, int(target.sale_id))

        
