# warehouses.py - Warehouse Management Routes
# Location: /garage_manager/routes/warehouses.py
# Description: Warehouse and inventory management routes

import csv
import io
import json
import os
import re
import uuid
import time
import random
import hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    send_file,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_, delete as sa_delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import joinedload

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    from PIL import Image
except Exception:
    Image = None

from extensions import db, csrf
from utils import _get_or_404, permission_required, format_currency
from forms import (
    ExchangeTransactionForm,
    ExchangeVendorForm,
    ImportForm,
    PartnerShareForm,
    PreOrderForm,
    ProductForm,
    ProductPartnerShareForm,
    ShipmentForm,
    StockLevelForm,
    TransferForm,
)
from models import (
    Customer,
    ExchangeTransaction,
    Partner,
    Payment,
    PaymentDirection,
    PaymentEntityType,
    PaymentStatus,
    PreOrder,
    PreOrderStatus,
    Product,
    ProductPartnerShare,
    Shipment,
    ShipmentItem,
    StockLevel,
    Supplier,
    Transfer,
    Warehouse,
    WarehousePartnerShare,
    WarehouseType,
    ImportRun,
    ProductCategory,
)

warehouse_bp = Blueprint("warehouse_bp", __name__, url_prefix="/warehouses")


IMPORT_TMP_DIR_KEY = "IMPORT_TMP_DIR"
IMPORT_REPORT_DIR_KEY = "IMPORT_REPORT_DIR"

HEADER_ALIASES = {
    "الاسم": "name",
    "رقم القطعة": "part_number",
    "الماركة": "brand",
    "الاسم التجاري": "commercial_name",
    "رقم الشاصي": "chassis_number",
    "الرقم التسلسلي": "serial_no",
    "الباركود": "barcode",
    "الوحدة": "unit",
    "اسم الفئة": "category_name",
    "سعر الشراء": "purchase_price",
    "سعر البيع": "selling_price",
    "التكلفة قبل الشحن": "cost_before_shipping",
    "التكلفة بعد الشحن": "cost_after_shipping",
    "سعر الوحدة قبل الضريبة": "unit_price_before_tax",
    "السعر": "price",
    "السعر الأساسي": "price",
    "السعر الأدنى": "min_price",
    "السعر الأعلى": "max_price",
    "نسبة الضريبة": "tax_rate",
    "الحد الأدنى": "min_qty",
    "نقطة إعادة الطلب": "reorder_point",
    "بلد المنشأ": "origin_country",
    "مدة الضمان": "warranty_period",
    "الوزن": "weight",
    "الأبعاد": "dimensions",
    "ملاحظات": "notes",
    "الكمية": "quantity",
    "سعر المتجر الإلكتروني": "online_price",
    "صورة المتجر الإلكتروني": "online_image",
    "name": "name",
    "brand": "brand",
    "part_number": "part_number",
    "part-number": "part_number",
    "part no": "part_number",
    "partno": "part_number",
    "sku": "sku",
    "code": "sku",
    "commercial_name": "commercial_name",
    "chassis_number": "chassis_number",
    "serial_no": "serial_no",
    "barcode": "barcode",
    "unit": "unit",
    "category_name": "category_name",
    "purchase_price": "purchase_price",
    "cost": "purchase_price",
    "selling_price": "selling_price",
    "sell": "selling_price",
    "cost_before_shipping": "cost_before_shipping",
    "cost_after_shipping": "cost_after_shipping",
    "unit_price_before_tax": "unit_price_before_tax",
    "price": "price",
    "min_price": "min_price",
    "max_price": "max_price",
    "tax_rate": "tax_rate",
    "min_qty": "min_qty",
    "reorder_point": "reorder_point",
    "origin_country": "origin_country",
    "warranty_period": "warranty_period",
    "weight": "weight",
    "dimensions": "dimensions",
    "notes": "notes",
    "quantity": "quantity",
    "qty": "quantity",
    "online_price": "online_price",
    "online image": "online_image",
    "online_image": "online_image",
}

REQUIRED_MIN = {"name"}
DEFAULTS = {"condition": "NEW", "is_active": True}

NUMERIC_FIELDS = {
    "purchase_price",
    "selling_price",
    "cost_before_shipping",
    "cost_after_shipping",
    "unit_price_before_tax",
    "price",
    "min_price",
    "max_price",
    "tax_rate",
    "weight",
    "online_price",
}
INT_FIELDS = {"min_qty", "reorder_point", "warranty_period", "quantity"}
_CURRENCY_RE = re.compile(r"[\s\$\£\€\¥\₺\₪\﷼\₽\₹\₩\₴\₦\₫\฿]+")


def _json_default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _tmp_dir():
    root = current_app.config.get(IMPORT_TMP_DIR_KEY) or os.path.join(current_app.instance_path, "imports")
    os.makedirs(root, exist_ok=True)
    return root


def _report_dir():
    root = current_app.config.get(IMPORT_REPORT_DIR_KEY) or os.path.join(current_app.instance_path, "imports", "reports")
    os.makedirs(root, exist_ok=True)
    return root


def _save_tmp_payload(payload: dict) -> str:
    key = uuid.uuid4().hex
    path = os.path.join(_tmp_dir(), f"{key}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=_json_default)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return key


def _write_tmp_payload(key: str, payload: dict) -> None:
    path = os.path.join(_tmp_dir(), f"{key}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=_json_default)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_tmp_payload(key: str) -> dict | None:
    path = os.path.join(_tmp_dir(), f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _normalize_header(h: str) -> str:
    if not h:
        return ""
    s = str(h).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    return HEADER_ALIASES.get(s, s)


def _clean_numeric(v):
    if v in (None, "", "None"):
        return None
    if isinstance(v, (int, float, Decimal)):
        try:
            return Decimal(str(v))
        except Exception:
            return None
    s = str(v)
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")
    s = s.translate(trans)
    s = _CURRENCY_RE.sub("", s).replace(",", "").strip()
    try:
        return Decimal(s)
    except Exception:
        return None

def _clean_int(v):
    if v in (None, "", "None"):
        return None
    try:
        return int(float(str(v).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))))
    except Exception:
        return None


def _read_rows_from_csv(file_storage) -> list[dict]:
    file_storage.stream.seek(0)
    raw = file_storage.stream.read()
    for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError("تعذر قراءة الملف: ترميز غير مدعوم.")

    stream = io.StringIO(text, newline=None)
    reader = csv.DictReader(stream)
    rows = []
    for raw in reader:
        row = {}
        for k, v in (raw or {}).items():
            nk = _normalize_header(k)
            row[nk] = (v if isinstance(v, str) else str(v)) if v is not None else None
        rows.append(row)
    return rows


def _read_rows_from_xlsx(file_storage) -> list[dict]:
    if not openpyxl:
        raise RuntimeError("XLSX غير مدعوم: الرجاء تثبيت openpyxl أو ارفع CSV.")
    file_storage.stream.seek(0)
    wb = openpyxl.load_workbook(file_storage.stream, data_only=True, read_only=True)
    ws = wb.active
    headers = []
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [_normalize_header(x if x is not None else "") for x in row]
            continue
        obj = {}
        for j, cell in enumerate(row):
            key = headers[j] if j < len(headers) else f"col_{j}"
            obj[key] = cell
        rows.append(obj)
    return rows


def _read_uploaded_rows(file_storage) -> list[dict]:
    filename = secure_filename(file_storage.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".xlsx":
        return _read_rows_from_xlsx(file_storage)
    if ext == ".xls":
        raise RuntimeError("صيغة .xls غير مدعومة. الرجاء رفع .xlsx أو .csv.")
    return _read_rows_from_csv(file_storage)


def _normalize_row_types(r: dict) -> dict:
    out = dict(r or {})
    for f in NUMERIC_FIELDS:
        if f in out:
            out[f] = _clean_numeric(out.get(f))
    for f in INT_FIELDS:
        if f in out:
            out[f] = _clean_int(out.get(f))
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = v.strip()
    if not out.get("sku") and out.get("part_number"):
        out["sku"] = str(out["part_number"]).strip()
    if out.get("price") is None:
        out["price"] = out.get("selling_price") if out.get("selling_price") is not None else Decimal("0")
    for k, v in DEFAULTS.items():
        out.setdefault(k, v)
    return out

@warehouse_bp.route("/api/warehouse-info", methods=["GET"], endpoint="api_warehouse_info")
@login_required
def api_warehouse_info():
    wid = request.args.get("id", type=int)
    if not wid:
        return jsonify({"error": "id_required"}), 400
    w = Warehouse.query.filter_by(id=wid).first()
    if not w:
        return jsonify({"error": "not_found"}), 404
    wt = getattr(w.warehouse_type, "value", w.warehouse_type)
    wt = str(wt).upper() if wt else ""
    return jsonify({
        "id": w.id,
        "name": w.name,
        "type": wt,
        "is_online": (wt == "ONLINE"),
        "online_slug": getattr(w, "online_slug", None),
        "online_is_default": bool(getattr(w, "online_is_default", False))
    })

@warehouse_bp.route("/api/upload_product_image", methods=["POST"], endpoint="api_upload_product_image")
@login_required
@permission_required("manage_inventory")
def api_upload_product_image():
    file = request.files.get("file")
    if not file or not getattr(file, "filename", ""):
        return jsonify({"ok": False, "error": "no_file"}), 400

    # فحص الامتداد
    filename = secure_filename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    if ext not in allowed_exts:
        return jsonify({"ok": False, "error": "unsupported_type"}), 400

    # فحص MIME
    allowed_mimes = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
    if file.mimetype not in allowed_mimes:
        return jsonify({"ok": False, "error": "unsupported_type"}), 400

    try:
        sub = _safe_subdir(request.form.get("subdir"))
        max_side = request.form.get("max_side", type=int) or 1200
        quality = request.form.get("quality", type=int) or 82
        out = _save_image_file(
            file,
            subdir=sub or "products",
            max_side=max_side,
            quality=quality,
            return_meta=True,
        )
        return jsonify(
            {
                "ok": True,
                "url": out["url"],
                "thumb_url": out.get("thumb_url"),
                "width": out.get("width"),
                "height": out.get("height"),
                "format": out.get("format"),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _in_chunks(items, size=500):
    it = list(items)
    for i in range(0, len(it), size):
        yield it[i : i + size]
        
@warehouse_bp.route("/api/prepare_online_fields", methods=["GET"], endpoint="api_prepare_online_fields")
@login_required
def api_prepare_online_fields():
    wid = request.args.get("warehouse_id", type=int)
    if not wid:
        return jsonify({"ok": False, "error": "warehouse_id_required"}), 400
    w = Warehouse.query.filter_by(id=wid).first()
    if not w:
        return jsonify({"ok": False, "error": "not_found"}), 404
    wt = getattr(w.warehouse_type, "value", w.warehouse_type)
    is_online = str(wt).upper() == "ONLINE"
    schema = {
        "base_fields": ["name", "sku", "brand", "part_number",
                        "price", "selling_price", "purchase_price",
                        "category_name", "quantity"],  # توحيد مع ما يستخدمه الاستيراد
        "extra_fields": [],
        "is_online": is_online
    }
    if is_online:
        schema["extra_fields"] = ["online_name", "online_price", "online_image"]
    return jsonify({"ok": True, "schema": schema})

@warehouse_bp.route("/api/apply_online_defaults", methods=["POST"], endpoint="api_apply_online_defaults")
@login_required
@permission_required("manage_inventory")
def api_apply_online_defaults():
    data = request.get_json(silent=True) or {}
    price = data.get("price")
    selling = data.get("selling_price")
    online_price = data.get("online_price")
    def _d(v):
        try:
            if v in (None, "", "None"):
                return None
            return float(v)
        except Exception:
            return None
    pr = _d(price)
    sp = _d(selling)
    op = _d(online_price)
    if op is None:
        op = sp if sp is not None else pr
    return jsonify({"ok": True, "online_price": op})

def _analyze(rows: list[dict]) -> dict:
    total = len(rows)
    missing_required = []
    warnings = []

    skus = {
        str((r.get("sku") or "")).strip().upper()
        for r in rows
        if str((r.get("sku") or "")).strip()
    }
    parts = {
        str((r.get("part_number") or "")).strip().upper()
        for r in rows
        if str((r.get("part_number") or "")).strip()
    }

    existing_by_sku = {}
    existing_by_part = {}

    if skus:
        for chunk in _in_chunks(list(skus)):
            for pid, sku_up in (
                db.session.query(Product.id, func.upper(Product.sku))
                .filter(func.upper(Product.sku).in_(chunk))
                .all()
            ):
                existing_by_sku[(sku_up or "")] = pid

    if parts:
        for chunk in _in_chunks(list(parts)):
            for pid, pn_up in (
                db.session.query(Product.id, func.upper(Product.part_number))
                .filter(func.upper(Product.part_number).in_(chunk))
                .all()
            ):
                existing_by_part[(pn_up or "")] = pid

    normalized = []
    for idx, r in enumerate(rows, start=1):
        nr = _normalize_row_types(r)
        if not (nr.get("name") or "").strip():
            missing_required.append(idx)
        soft = []
        if nr.get("price") is None and nr.get("selling_price") is None:
            soft.append("لا يوجد سعر")
        if not (nr.get("sku") or "") and (nr.get("part_number") or ""):
            soft.append("لا يوجد SKU")
        if not (nr.get("brand") or ""):
            soft.append("لا توجد ماركة")

        key_sku = str(nr.get("sku") or "").strip().upper()
        key_part = str(nr.get("part_number") or "").strip().upper()
        match_id = None
        match_key = None
        if key_sku and key_sku in existing_by_sku:
            match_id = existing_by_sku[key_sku]
            match_key = "sku"
        elif key_part and key_part in existing_by_part:
            match_id = existing_by_part[key_part]
            match_key = "part_number"

        normalized.append(
            {
                "rownum": idx,
                "data": nr,
                "match": {"product_id": match_id, "key": match_key},
                "soft_warnings": soft,
            }
        )
        if soft:
            warnings.append({"row": idx, "issues": soft})

    report = {
        "total": total,
        "missing_required_rows": missing_required,
        "warnings": warnings,
        "matches": sum(1 for n in normalized if n["match"]["product_id"]),
        "new_items": sum(1 for n in normalized if not n["match"]["product_id"]),
    }
    return {"normalized": normalized, "report": report}

def _save_import_report_csv(rows: list[dict], *, filename_hint: str) -> str:
    cols = [
        "action",
        "strategy",
        "sku",
        "name",
        "product_id",
        "qty_added",
        "stock_before",
        "stock_after",
        "purchase_price",
        "selling_price",
        "min_price",
        "max_price",
        "tax_rate",
        "note",
    ]
    path = os.path.join(_report_dir(), f"{filename_hint}.csv")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows or []:
            w.writerow({k: r.get(k) for k in cols})
    os.replace(tmp, path)
    return path


def _uploads_root():
    base = current_app.config.get("PRODUCT_UPLOAD_DIR")
    if base:
        os.makedirs(base, exist_ok=True)
        return base
    root = os.path.join(current_app.root_path, "static", "uploads", "products")
    os.makedirs(root, exist_ok=True)
    return root


def _uploads_url_base(subdir: str | None = None):
    base = current_app.config.get("PRODUCT_UPLOAD_URL_PATH", "/static/uploads/products")
    if subdir:
        sub = subdir.strip("/")
        return f"{base}/{sub}"
    return base

def _safe_subdir(s: str | None) -> str:
    """
    تنظّف اسم المجلد الفرعي وتمنع أي صعود للمسار أو مسار مطلق.
    """
    s = (s or "products").strip().strip("/").replace("\\", "/")
    s = os.path.normpath(s)
    if s.startswith(("..", "/")):
        return "products"
    return s

def _allowed_image(filename: str) -> bool:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _unique_name(ext: str) -> str:
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"


def _save_image_file(
    fstorage,
    *,
    subdir: str = "products",
    prefer_webp: bool = True,
    max_side: int = 1200,
    thumb_side: int = 400,
    quality: int = 82,
    return_meta: bool = False,
) -> tuple[str, str] | dict:
    if not Image:
        raise RuntimeError("الصور غير مدعومة على الخادم: الرجاء تثبيت Pillow (PIL).")

    name = secure_filename(fstorage.filename or "")
    in_ext = os.path.splitext(name)[1].lower() or ".jpg"

    base_root = _uploads_root()
    subdir = _safe_subdir(subdir)
    root = os.path.join(base_root, subdir) if subdir else base_root
    os.makedirs(root, exist_ok=True)

    from PIL import ImageOps, UnidentifiedImageError
    try:
        Image.MAX_IMAGE_PIXELS = 24_000_000
        fstorage.stream.seek(0)
        img = Image.open(fstorage.stream)
        img = ImageOps.exif_transpose(img)

        has_alpha = (img.mode in ("RGBA", "LA")) or ("transparency" in getattr(img, "info", {}))
        if not has_alpha:
            img = img.convert("RGB")

        w, h = img.size
        scale = min(1.0, float(max_side) / float(max(w, h) or 1))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        out_ext = ".webp" if prefer_webp else in_ext
        main_name = _unique_name(out_ext)
        main_path = os.path.join(root, main_name)

        if out_ext == ".webp":
            img.save(main_path, quality=quality, method=6)
        elif out_ext == ".png":
            img.save(main_path, optimize=True)
        else:
            if has_alpha:
                img = img.convert("RGB")
            img.save(main_path, quality=quality, optimize=True)

        tw, th = img.size
        tscale = min(1.0, float(thumb_side) / float(max(tw, th) or 1))
        timg = img.resize((int(tw * tscale), int(th * tscale)), Image.LANCZOS) if tscale < 1.0 else img.copy()
        t_name = _unique_name(out_ext)
        t_path = os.path.join(root, t_name)
        if out_ext == ".webp":
            timg.save(t_path, quality=max(1, min(quality, 95) - 2), method=6)
        elif out_ext == ".png":
            timg.save(t_path, optimize=True)
        else:
            timg.save(t_path, quality=max(1, min(quality, 95) - 2), optimize=True)

        base = _uploads_url_base(subdir)
        if return_meta:
            return {
                "url": f"{base}/{main_name}",
                "thumb_url": f"{base}/{t_name}",
                "width": tw,
                "height": th,
                "format": "WEBP" if out_ext == ".webp" else ("PNG" if out_ext == ".png" else "JPEG"),
            }
        return f"{base}/{main_name}", f"{base}/{t_name}"
    except UnidentifiedImageError as e:
        raise RuntimeError("ملف الصورة غير صالح") from e
    except Exception as e:
        raise RuntimeError("تعذر معالجة الصورة") from e

@warehouse_bp.app_context_processor
def _inject_utils():
    labels = {
        "warehouse_type": {"MAIN": "المستودع الرئيسي", "PARTNER": "مستودع شريك", "EXCHANGE": "مستودع تبادل", "TEMP": "مستودع مؤقت", "OUTLET": "منفذ بيع", "ONLINE": "مستودع أونلاين"},
        "transfer_direction": {"IN": "وارد", "OUT": "صادر", "ADJUSTMENT": "تسوية"},
        "preorder_status": {"PENDING": "قيد الانتظار", "CONFIRMED": "مؤكد", "FULFILLED": "تم التنفيذ", "CANCELLED": "ملغى"},
    }

    def ar_label(category, key):
        if key is None:
            return ""
        k = getattr(key, "value", key)
        k = str(k)
        return labels.get(category, {}).get(k, k)

    quick = [
        {"title": "كشف المخزون", "endpoint": "warehouse_bp.inventory_summary", "icon": "fa-table"},
        {"title": "إنشاء مستودع", "endpoint": "warehouse_bp.create", "icon": "fa-plus"},
        {"title": "الحجوزات", "endpoint": "warehouse_bp.preorders_list", "icon": "fa-clipboard-list"},
    ]
    return dict(format_currency=format_currency, ar_label=ar_label, AR_LABELS=labels, warehouses_quick_actions=quick)


def _ensure_category_id(name: str | None) -> int | None:
    if not name:
        return None
    cat = db.session.query(ProductCategory).filter(func.lower(ProductCategory.name) == name.strip().lower()).first()
    if not cat:
        cat = ProductCategory(name=name.strip())
        db.session.add(cat)
        db.session.flush()
    return cat.id


def _is_online_wh(w: Warehouse) -> bool:
    wt = getattr(w.warehouse_type, "value", str(w.warehouse_type or "")).upper()
    return wt == "ONLINE"


@warehouse_bp.route("/", methods=["GET"], endpoint="list")
@login_required
@permission_required("view_warehouses")
def list_warehouses():
    q = Warehouse.query
    type_ = (request.args.get("type") or "").strip()
    if type_:
        q = q.filter(Warehouse.warehouse_type == type_.upper())
    parent = request.args.get("parent")
    if parent and str(parent).isdigit():
        q = q.filter(Warehouse.parent_id == int(parent))
    active = request.args.get("active")
    if active in ("0", "1"):
        q = q.filter(Warehouse.is_active == (active == "1"))
    has_partner = request.args.get("has_partner")
    if has_partner in ("0", "1"):
        if has_partner == "1":
            q = q.filter(Warehouse.partner_id.isnot(None))
        else:
            q = q.filter(Warehouse.partner_id.is_(None))
    search = (request.args.get("search") or "").strip()
    if search:
        q = q.filter(Warehouse.name.ilike(f"%{search}%"))
    order = (request.args.get("order") or "name").lower()
    if order == "type":
        q = q.order_by(Warehouse.warehouse_type.asc(), Warehouse.name.asc())
    elif order == "created":
        q = q.order_by(Warehouse.id.desc())
    else:
        q = q.order_by(Warehouse.name.asc())
    warehouses = q.all()
    if request.is_json or (request.args.get("format") or "").lower() == "json":
        labels = {
            "MAIN": "المستودع الرئيسي",
            "PARTNER": "مستودع شريك",
            "EXCHANGE": "مستودع تبادل",
            "TEMP": "مستودع مؤقت",
            "OUTLET": "منفذ بيع",
            "INVENTORY": "مخزون",
            "ONLINE": "مستودع أونلاين",
        }
        data = []
        for w in warehouses:
            wt = getattr(w.warehouse_type, "value", w.warehouse_type)
            wt = str(wt) if wt is not None else ""
            data.append(
                {
                    "id": w.id,
                    "name": w.name,
                    "warehouse_type": wt,
                    "warehouse_type_label": labels.get(wt, wt),
                    "parent_id": w.parent_id,
                    "partner_id": w.partner_id,
                    "is_active": bool(w.is_active),
                    "capacity": w.capacity,
                    "location": w.location,
                    "online_slug": getattr(w, "online_slug", None),
                    "online_is_default": bool(getattr(w, "online_is_default", False)),
                }
            )
        return jsonify({"data": data})
    return render_template(
        "warehouses/list.html",
        warehouses=warehouses,
        filter_type=type_ or "",
        parent=parent or "",
        search=search,
        active=active or "",
        has_partner=has_partner or "",
        order=order,
    )


@warehouse_bp.route("/create", methods=["GET", "POST"], endpoint="create")
@login_required
@permission_required("manage_warehouses")
def create_warehouse():
    from forms import WarehouseForm

    def _to_int(v):
        try:
            return int(str(getattr(v, "id", v)).strip())
        except Exception:
            return None

    form = WarehouseForm()
    if form.validate_on_submit():
        wh_type = (form.warehouse_type.data or "").strip().upper()
        w = Warehouse(
            name=(form.name.data or "").strip(),
            warehouse_type=wh_type,
            location=((form.location.data or "").strip() or None),
            parent_id=_to_int(form.parent_id.data),
            partner_id=_to_int(form.partner_id.data),
            supplier_id=_to_int(form.supplier_id.data),
            share_percent=form.share_percent.data if wh_type == "PARTNER" else 0,
            capacity=form.capacity.data,
            is_active=True if form.is_active.data is None else bool(form.is_active.data),
            notes=(form.notes.data or "").strip() or None,
        )
        if hasattr(w, "online_slug"):
            w.online_slug = (form.online_slug.data or "").strip() or None
        if hasattr(w, "online_is_default"):
            w.online_is_default = bool(form.online_is_default.data)
        db.session.add(w)
        try:
            db.session.commit()
            flash("تم إنشاء المستودع بنجاح", "success")
            return redirect(url_for("warehouse_bp.list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"حدث خطأ أثناء إنشاء المستودع: {e.__class__.__name__}", "danger")

    if request.method == "POST" and form.errors:
        for field, errs in form.errors.items():
            for err in errs:
                flash(f"{field}: {err}", "danger")

    return render_template("warehouses/form.html", form=form)


@warehouse_bp.route("/<int:warehouse_id>/edit", methods=["GET", "POST"], endpoint="edit")
@login_required
@permission_required("manage_warehouses")
def edit_warehouse(warehouse_id):
    from forms import WarehouseForm

    def _to_int(v):
        try:
            return int(str(getattr(v, "id", v)).strip())
        except Exception:
            return None

    w = _get_or_404(Warehouse, warehouse_id)
    form = WarehouseForm(obj=w)

    if form.validate_on_submit():
        w.name = (form.name.data or "").strip()
        w.warehouse_type = (form.warehouse_type.data or "").strip().upper()
        w.location = (form.location.data or "").strip() or None
        w.capacity = form.capacity.data
        w.is_active = bool(form.is_active.data)
        w.parent_id = _to_int(form.parent_id.data)
        w.partner_id = _to_int(form.partner_id.data)
        w.supplier_id = _to_int(form.supplier_id.data)
        w.share_percent = form.share_percent.data if w.warehouse_type == "PARTNER" else 0
        w.notes = (form.notes.data or "").strip() or None
        if hasattr(w, "online_slug"):
            w.online_slug = (form.online_slug.data or "").strip() or None
        if hasattr(w, "online_is_default"):
            w.online_is_default = bool(form.online_is_default.data)
        try:
            db.session.commit()
            flash("تم تحديث بيانات المستودع", "success")
            return redirect(url_for("warehouse_bp.list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"حدث خطأ: {e}", "danger")

    return render_template("warehouses/form.html", form=form, warehouse=w)


@warehouse_bp.route("/<int:warehouse_id>/delete", methods=["POST"], endpoint="delete")
@login_required
@permission_required("manage_warehouses")
def delete_warehouse(warehouse_id):
    _get_or_404(Warehouse, warehouse_id)
    try:
        db.session.execute(sa_delete(Warehouse).where(Warehouse.id == warehouse_id))
        db.session.commit()
        db.session.expire_all()
        flash("تم حذف المستودع", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("warehouse_bp.list"))


@warehouse_bp.route("/<int:warehouse_id>", methods=["GET"], endpoint="detail")
@login_required
@permission_required("view_warehouses", "view_inventory", "manage_inventory")
def warehouse_detail(warehouse_id):
    w = _get_or_404(Warehouse, warehouse_id)
    stock_levels = (
        StockLevel.query.filter_by(warehouse_id=warehouse_id)
        .options(joinedload(StockLevel.product))
        .all()
    )
    transfers_in = Transfer.query.filter_by(destination_id=warehouse_id).all()
    transfers_out = Transfer.query.filter_by(source_id=warehouse_id).all()
    return render_template(
        "warehouses/detail.html",
        warehouse=w,
        stock_levels=stock_levels,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        stock_form=StockLevelForm(),
        transfer_form=TransferForm(),
        exchange_form=ExchangeTransactionForm(),
        share_form=ProductPartnerShareForm(),
        shipment_form=ShipmentForm(),
    )


@warehouse_bp.route("/goto/warehouse-products", methods=["GET"], endpoint="goto_warehouse_products")
@login_required
@permission_required("view_inventory")
def goto_warehouse_products():
    wid = request.args.get("id", type=int)
    if not wid:
        flash("أدخل رقم المستودع.", "warning")
        return redirect(url_for("warehouse_bp.list"))
    return redirect(url_for("warehouse_bp.products", id=wid))


@warehouse_bp.route("/goto/product-card", methods=["GET"], endpoint="goto_product_card")
@login_required
@permission_required("view_parts")
def goto_product_card():
    pid = request.args.get("id", type=int)
    if not pid:
        flash("أدخل رقم القطعة.", "warning")
        return redirect(url_for("warehouse_bp.list"))
    return redirect(url_for("warehouse_bp.product_card", product_id=pid))


@warehouse_bp.route("/inventory", methods=["GET"], endpoint="inventory_summary")
@login_required
@permission_required("view_inventory")
def inventory_summary():
    search = (request.args.get("q") or "").strip()
    selected_ids = request.args.getlist("warehouse_ids", type=int)
    if not selected_ids:
        selected_ids = [w.id for w in Warehouse.query.order_by(Warehouse.name).all()]

    whs = Warehouse.query.filter(Warehouse.id.in_(selected_ids)).order_by(Warehouse.name.asc()).all()
    wh_ids = [w.id for w in whs]

    if wh_ids:
        q = (
            db.session.query(StockLevel)
            .join(Product, StockLevel.product_id == Product.id)
            .filter(StockLevel.warehouse_id.in_(wh_ids))
            .options(joinedload(StockLevel.product))
            .order_by(Product.name.asc())
        )
        if search:
            like = f"%{search}%"
            q = q.filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.part_number.ilike(like)))
        rows = q.all()
    else:
        rows = []

    pivot = {}
    for sl in rows:
        pid = sl.product_id
        p = sl.product
        if pid not in pivot:
            pivot[pid] = {"product": p, "by": {wid: {"on": 0, "res": 0} for wid in wh_ids}, "total": 0}
        on = int(sl.quantity or 0)
        res = int(getattr(sl, "reserved_quantity", 0) or 0)
        pivot[pid]["by"][sl.warehouse_id] = {"on": on, "res": res}
        pivot[pid]["total"] += on

    rows_data = sorted(pivot.values(), key=lambda d: (d["product"].name or "").lower())

    if (request.args.get("export") or "").lower() == "csv":
        si = io.StringIO()
        writer = csv.writer(si)
        header = ["ID", "القطعة", "SKU"] + [w.name for w in whs] + ["الإجمالي"]
        writer.writerow(header)
        for r in rows_data:
            p = r["product"]
            sku = getattr(p, "sku", "") or ""
            line = [str(getattr(p, "id", "") or ""), (p.name or ""), sku]
            for wid in wh_ids:
                line.append(str(r["by"][wid]["on"] if wid in r["by"] else 0))
            line.append(str(r["total"]))
            writer.writerow(line)
        output = si.getvalue().encode("utf-8-sig")
        return Response(
            output,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=inventory_summary.csv"},
        )

    return render_template(
        "warehouses/inventory_summary.html",
        warehouses=whs,
        rows=rows_data,
        selected_ids=wh_ids,
        search=search,
    )


@warehouse_bp.route("/<int:id>/products", methods=["GET"], endpoint="products")
@login_required
@permission_required("view_inventory")
def products(id):
    base_warehouse = _get_or_404(Warehouse, id)
    all_whs = Warehouse.query.order_by(Warehouse.name).all()
    selected_ids = request.args.getlist("warehouse_ids", type=int) or [id]
    selected_ids = sorted(set(selected_ids))
    whs = [w for w in all_whs if w.id in selected_ids]
    wh_ids = [w.id for w in whs] or [id]

    search = (request.args.get("q") or "").strip()
    q = (
        db.session.query(StockLevel)
        .join(Product, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id.in_(wh_ids))
        .options(joinedload(StockLevel.product))
        .order_by(Product.name.asc())
    )
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.part_number.ilike(like),
                Product.brand.ilike(like),
            )
        )

    rows = q.all()
    pivot = {}
    for sl in rows:
        pid = sl.product_id
        p = sl.product
        if pid not in pivot:
            pivot[pid] = {"product": p, "by": {wid: {"on": 0, "res": 0} for wid in wh_ids}, "total": 0}
        on = int(sl.quantity or 0)
        res = int(getattr(sl, "reserved_quantity", 0) or 0)
        pivot[pid]["by"][sl.warehouse_id] = {"on": on, "res": res}
        pivot[pid]["total"] += on

    rows_data = sorted(pivot.values(), key=lambda d: (d["product"].name or "").lower())

    if request.is_json or (request.args.get("format") or "").lower() == "json":
        def _f(x):
            try:
                return float(x) if x is not None else None
            except Exception:
                return None

        out = []
        for r in rows_data:
            p = r["product"]
            active_qty = r["by"].get(base_warehouse.id, {}).get("on", 0)
            out.append(
                {
                    "id": p.id,
                    "sku": p.sku,
                    "part_number": p.part_number,
                    "name": p.name,
                    "brand": p.brand,
                    "purchase_price": _f(getattr(p, "purchase_price", None)),
                    "selling_price": _f(getattr(p, "selling_price", None)),
                    "price": _f(getattr(p, "price", None)),
                    "online_price": _f(getattr(p, "online_price", None)),
                    "quantity": int(active_qty or 0),
                    "total_quantity": int(r["total"] or 0),
                }
            )
        return jsonify({"data": out, "warehouse_id": base_warehouse.id})

    return render_template(
        "warehouses/products.html",
        warehouse=base_warehouse,
        warehouses=all_whs,
        selected_ids=wh_ids,
        whs=whs,
        rows=rows_data,
        search=search,
        active_warehouse_id=base_warehouse.id,
        active_warehouse=base_warehouse,
        warehouse_id=base_warehouse.id,
    )

@warehouse_bp.route("/<int:warehouse_id>/transfer", methods=["POST"], endpoint="transfer_inline")
@login_required
@csrf.exempt
@permission_required("manage_inventory", "manage_warehouses", "warehouse_transfer")
def transfer_inline(warehouse_id):
    data = request.get_json(silent=True) or request.form or {}

    def _i(v, d=None):
        try:
            return int(float(v)) if v not in (None, "", "None") else d
        except Exception:
            return d

    pid = _i(data.get("product_id"))
    sid = _i(data.get("source_id")) or warehouse_id
    did = _i(data.get("destination_id"))
    qty = _i(data.get("quantity"), 0)
    notes = (data.get("notes") or "").strip() or None

    if not (pid and sid and did and qty and qty > 0) or sid == did:
        return jsonify({"success": False, "error": "invalid"}), 400
    if sid != warehouse_id:
        return jsonify({"success": False, "error": "warehouse_mismatch"}), 400

    try:
        _lock_stock_rows([(pid, sid), (pid, did)])

        src = StockLevel.query.filter_by(warehouse_id=sid, product_id=pid).with_for_update(nowait=False).first()
        if not src:
            src = StockLevel(warehouse_id=sid, product_id=pid, quantity=0, reserved_quantity=0)
            db.session.add(src)
            db.session.flush()

        available = int((src.quantity or 0) - (src.reserved_quantity or 0))
        if available < qty:
            return jsonify({"success": False, "error": "insufficient_stock", "available": max(available, 0)}), 400
        src.quantity = int(src.quantity or 0) - qty

        dst = StockLevel.query.filter_by(warehouse_id=did, product_id=pid).with_for_update(nowait=False).first()
        if not dst:
            dst = StockLevel(warehouse_id=did, product_id=pid, quantity=0, reserved_quantity=0)
            db.session.add(dst)
            db.session.flush()
        dst.quantity = int(dst.quantity or 0) + qty

        t = Transfer(
            product_id=pid,
            source_id=sid,
            destination_id=did,
            quantity=qty,
            direction="OUT",
            user_id=getattr(current_user, "id", None),
            notes=notes,
        )
        db.session.add(t)
        db.session.commit()

        return jsonify({
            "success": True,
            "transfer_id": t.id,
            "source_onhand": int(src.quantity or 0),
            "destination_onhand": int(dst.quantity or 0),
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

@warehouse_bp.route("/<int:warehouse_id>/products/<int:product_id>", methods=["POST", "PATCH"], endpoint="update_product_inline")
@login_required
@permission_required("manage_inventory")
def update_product_inline(warehouse_id, product_id):
    _get_or_404(Warehouse, warehouse_id)
    p = _get_or_404(Product, product_id)
    payload = request.get_json(silent=True) or {}

    allowed_product_fields = {
        "name","sku","part_number","brand",
        "purchase_price","selling_price","price","min_price","max_price","tax_rate",
        "unit","origin_country","warranty_period",
        "is_active","online_price","online_name","online_image",
    }
    decimal_fields = {"purchase_price","selling_price","price","min_price","max_price","tax_rate","online_price"}
    int_fields = {"warranty_period"}

    updates = {}
    for k, v in payload.items():
        if k in allowed_product_fields:
            if k in decimal_fields:
                try:
                    updates[k] = Decimal(str(v)) if v not in (None, "", "None") else None
                except (InvalidOperation, ValueError):
                    return jsonify({"ok": False, "error": f"invalid_decimal:{k}"}), 400
            elif k in int_fields:
                try:
                    updates[k] = int(v) if v not in (None, "", "None") else None
                except Exception:
                    return jsonify({"ok": False, "error": f"invalid_int:{k}"}), 400
            else:
                updates[k] = (str(v).strip() if v is not None else None)

    for k, v in updates.items():
        setattr(p, k, v)

    qty_set = False
    sl = None
    if "quantity" in payload or "reserved_quantity" in payload:
        sl = StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=product_id).one_or_none()
        if not sl:
            sl = StockLevel(warehouse_id=warehouse_id, product_id=product_id, quantity=0, reserved_quantity=0)
            db.session.add(sl)

        if "quantity" in payload:
            try:
                qv = int(float(payload.get("quantity") if payload.get("quantity") is not None else 0))
                sl.quantity = max(0, qv)
                qty_set = True
            except Exception:
                return jsonify({"ok": False, "error": "invalid_int:quantity"}), 400

        if "reserved_quantity" in payload:
            try:
                rv = int(float(payload.get("reserved_quantity") if payload.get("reserved_quantity") is not None else 0))
                rv = max(0, rv)
                if sl.quantity is not None:
                    rv = min(rv, int(sl.quantity or 0))
                sl.reserved_quantity = rv
            except Exception:
                return jsonify({"ok": False, "error": "invalid_int:reserved_quantity"}), 400

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "db_error"}), 500

    if sl:
        active_qty = int(sl.quantity or 0)
    else:
        sl2 = StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=product_id).one_or_none()
        active_qty = int(getattr(sl2, "quantity", 0) or 0) if sl2 else 0

    total_qty = (
        db.session.query(func.coalesce(func.sum(StockLevel.quantity), 0))
        .filter(StockLevel.product_id == product_id)
        .scalar()
    )

    def _f(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    return jsonify(
        {
            "ok": True,
            "product": {
                "id": p.id,
                "sku": p.sku,
                "part_number": p.part_number,
                "name": p.name,
                "brand": p.brand,
                "purchase_price": _f(getattr(p, "purchase_price", None)),
                "selling_price": _f(getattr(p, "selling_price", None)),
                "price": _f(getattr(p, "price", None)),
                "online_price": _f(getattr(p, "online_price", None)),
                "online_image": getattr(p, "online_image", None),
            },
            "quantity": active_qty if qty_set or sl else None,
            "total_quantity": int(total_qty or 0),
        }
    )

@warehouse_bp.get("/<int:warehouse_id>/preview")
@login_required
@permission_required("view_inventory")
def preview_inventory(warehouse_id: int):
    warehouse = _get_or_404(Warehouse, warehouse_id)
    rows = (
        db.session.query(
            Product.id.label("product_id"),
            Product.sku,
            Product.part_number,
            Product.name,
            Product.brand,
            Product.purchase_price,
            Product.selling_price,
            func.coalesce(func.sum(StockLevel.quantity), 0).label("quantity"),
        )
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id == warehouse.id)
        .group_by(
            Product.id,
            Product.sku,
            Product.part_number,
            Product.name,
            Product.brand,
            Product.purchase_price,
            Product.selling_price,
        )
        .order_by(Product.name.asc())
        .all()
    )
    return render_template("warehouses/preview_inventory.html", warehouse=warehouse, rows=rows)


@warehouse_bp.route("/<int:id>/add-product", methods=["GET", "POST"], endpoint="add_product")
@login_required
@permission_required("manage_inventory")
def add_product(id):
    log = current_app.logger
    warehouse = _get_or_404(Warehouse, id)

    product_form = ProductForm()
    stock_form = StockLevelForm(meta={"csrf": False})

    wtype_raw = getattr(warehouse.warehouse_type, "value", str(warehouse.warehouse_type))
    wtype = (wtype_raw or "").upper()
    is_partner = (wtype == "PARTNER")
    is_exchange = (wtype == "EXCHANGE")
    is_online = (wtype == "ONLINE")

    partners_forms = [ProductPartnerShareForm()] if is_partner else []
    exchange_vendors_forms = [ExchangeVendorForm()] if is_exchange else []

    if not stock_form.warehouse_id.data:
        try:
            stock_form.warehouse_id.process(None, warehouse.id)
        except Exception:
            stock_form.warehouse_id.data = warehouse.id

    def _to_int(v):
        try:
            return int(str(v).strip())
        except Exception:
            return None

    def _to_dec(v):
        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
        if v in (None, ""): return None
        s = str(v).replace(",", "").strip()
        try:
            return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return None

    if request.method == "POST":
        if product_form.category_id.data:
            cat = db.session.get(ProductCategory, int(product_form.category_id.data))
            if not cat:
                flash("الفئة المختارة غير موجودة.", "danger")
                return render_template(
                    "warehouses/add_product.html",
                    product_form=product_form,
                    stock_form=stock_form,
                    warehouse=warehouse,
                    partners_forms=partners_forms,
                    exchange_vendors_forms=exchange_vendors_forms,
                    wtype=wtype,
                    is_online=is_online,
                ), 400

        if not product_form.validate_on_submit():
            flash("تعذّر حفظ المنتج. تأكّد من الحقول المطلوبة.", "danger")
            return render_template(
                "warehouses/add_product.html",
                product_form=product_form,
                stock_form=stock_form,
                warehouse=warehouse,
                partners_forms=partners_forms,
                exchange_vendors_forms=exchange_vendors_forms,
                wtype=wtype,
                is_online=is_online,
            ), 400

        try:
            with db.session.begin_nested():
                product = product_form.apply_to(Product())
                if not product.category_id and product.category_name:
                    product.category_id = _ensure_category_id(product.category_name)
                db.session.add(product)
                db.session.flush()

                if is_online:
                    upfile = request.files.get("online_image_file") or request.files.get("image_file") or request.files.get("image")
                    if upfile and getattr(upfile, "filename", "") and _allowed_image(upfile.filename):
                        url, thumb = _save_image_file(upfile)
                        product.online_image = url or product.online_image or None
                        if not product.image:
                            product.image = url
                    elif product.online_image in (None, "", "None") and (product_form.online_image.data or "").strip():
                        product.online_image = (product_form.online_image.data or "").strip()
                else:
                    upfile = request.files.get("image_file") or request.files.get("image")
                    if upfile and getattr(upfile, "filename", "") and _allowed_image(upfile.filename):
                        url, thumb = _save_image_file(upfile)
                        product.image = url or product.image or None

                try:
                    stock_form.product_id.process(None, product.id)
                except Exception:
                    stock_form.product_id.data = product.id
                if hasattr(stock_form, "warehouse_id") and not stock_form.warehouse_id.data:
                    try:
                        stock_form.warehouse_id.process(None, warehouse.id)
                    except Exception:
                        stock_form.warehouse_id.data = warehouse.id

                if not stock_form.validate():
                    raise ValueError(f"Stock form invalid: {stock_form.errors}")

                init_qty = max(int(stock_form.quantity.data or 0), 0)
                init_res = max(int(stock_form.reserved_quantity.data or 0), 0)

                sl = StockLevel.query.filter_by(
                    warehouse_id=stock_form.warehouse_id.data, product_id=product.id
                ).first()
                if not sl:
                    sl = StockLevel(
                        warehouse_id=stock_form.warehouse_id.data,
                        product=product,
                        quantity=0,
                        reserved_quantity=0,
                    )
                    db.session.add(sl)

                sl.quantity = (sl.quantity or 0) + init_qty
                sl.reserved_quantity = init_res
                sl.min_stock = stock_form.min_stock.data or None
                sl.max_stock = stock_form.max_stock.data or None

                if is_partner:
                    p_ids  = request.form.getlist("partner_id")
                    p_perc = request.form.getlist("share_percentage")
                    p_amt  = request.form.getlist("share_amount")
                    p_note = request.form.getlist("notes")

                    rows = []
                    for pid, perc, amt, note in zip(p_ids, p_perc, p_amt, p_note):
                        pid_i = _to_int(pid)
                        perc_d = _to_dec(perc) or Decimal("0.00")
                        amt_d = _to_dec(amt) or Decimal("0.00")
                        if pid_i and (perc_d > 0 or amt_d > 0):
                            rows.append((pid_i, perc_d, amt_d, (note or "").strip() or None))

                    if not rows:
                        raise ValueError("يرجى إضافة شريك واحد على الأقل مع نسبة أو قيمة مساهمة.")

                    if all(r[1] > 0 and r[2] == 0 for r in rows):
                        total_perc = sum((r[1] for r in rows), Decimal("0.00"))
                        if total_perc > Decimal("100.00") + Decimal("0.0001"):
                            raise ValueError("مجموع نسب الشركاء يتجاوز 100%.")

                    for pid_i, perc_d, amt_d, note in rows:
                        db.session.add(
                            ProductPartnerShare(
                                product=product,
                                partner_id=pid_i,
                                share_percentage=float(perc_d) if perc_d > 0 else 0.0,
                                share_amount=float(amt_d) if amt_d > 0 else 0.0,
                                notes=note,
                            )
                        )

                elif is_exchange:
                    s_ids  = request.form.getlist("supplier_id")
                    v_phone = request.form.getlist("vendor_phone")
                    v_paid  = request.form.getlist("vendor_paid")
                    v_price = request.form.getlist("vendor_price")

                    rows = []
                    for sid, phone, paid, price in zip(s_ids, v_phone, v_paid, v_price):
                        sid_i = _to_int(sid)
                        paid_d = _to_dec(paid)
                        price_d = _to_dec(price)
                        if sid_i or phone or paid_d or price_d:
                            rows.append((sid_i, (phone or "").strip() or None, paid_d, price_d))

                    if not rows or not any(r[0] for r in rows):
                        raise ValueError("يرجى إضافة مورد واحد على الأقل لمستودع التبادل.")

                    for sid_i, phone, paid_d, price_d in rows:
                        note_parts = []
                        if sid_i:
                            sup = db.session.get(Supplier, sid_i)
                            note_parts.append(f"SupplierID:{sid_i}({sup.name if sup else ''})")
                        if phone: note_parts.append(f"phone:{phone}")
                        if paid_d is not None: note_parts.append(f"paid:{paid_d}")
                        if price_d is not None: note_parts.append(f"price:{price_d}")

                        db.session.add(
                            ExchangeTransaction(
                                product=product,
                                warehouse_id=warehouse.id,
                                partner_id=None,
                                quantity=init_qty,
                                unit_cost=float(price_d) if price_d is not None else None,
                                is_priced=bool(price_d is not None and price_d > 0),
                                direction="IN",
                                notes=" | ".join(note_parts) if note_parts else None,
                            )
                        )

            db.session.commit()
            if is_online and (product.online_price is None or product.online_price == 0):
                flash("تمت إضافة القطعة، تنبيه: سعر المتجر الإلكتروني غير محدد.", "warning")
            elif is_online and not (product.online_image or product.image):
                flash("تمت إضافة القطعة، تنبيه: لا توجد صورة للمتجر الإلكتروني.", "warning")
            else:
                flash("تمت إضافة القطعة بنجاح", "success")
            return redirect(url_for("warehouse_bp.products", id=warehouse.id))

        except ValueError as ve:
            db.session.rollback()
            flash(str(ve), "danger")
        except Exception as e:
            db.session.rollback()
            log.exception("add_product:exception")
            flash(f"فشل حفظ المنتج: {e}", "danger")

    return render_template(
        "warehouses/add_product.html",
        product_form=product_form,
        stock_form=stock_form,
        warehouse=warehouse,
        partners_forms=partners_forms,
        exchange_vendors_forms=exchange_vendors_forms,
        wtype=wtype,
        is_online=is_online,
    )


@warehouse_bp.route("/<int:id>/import", methods=["GET", "POST"], endpoint="import_products")
@login_required
@permission_required("manage_inventory")
def import_products(id):
    w = _get_or_404(Warehouse, id)
    form = ImportForm()
    if request.method == "GET":
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    file_obj = request.files.get("file") or getattr(getattr(form, "file", None), "data", None)
    if not file_obj or not getattr(file_obj, "filename", ""):
        flash("لم يتم اختيار ملف.", "warning")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    filename = secure_filename(file_obj.filename or "")
    ext = filename.rsplit('.', 1)[-1].lower()
    allowed_exts = {"csv", "xlsx"}
    if ext not in allowed_exts:
        flash("صيغة الملف غير مدعومة. الرجاء استخدام CSV أو XLSX.", "danger")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    file_obj.seek(0, os.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > 5 * 1024 * 1024:
        flash("حجم الملف يتجاوز الحد المسموح (5MB).", "danger")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    head = file_obj.read(2)
    file_obj.seek(0)
    if head == b"MZ":
        flash("الملف يحتوي على محتوى غير آمن.", "danger")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    try:
        blob = file_obj.read()
        file_obj.seek(0)
        file_sha256 = hashlib.sha256(blob).hexdigest()
    except Exception:
        file_sha256 = None

    try:
        rows = _read_uploaded_rows(file_obj)
    except RuntimeError as e:
        flash(str(e), "danger")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)
    except Exception:
        flash("تعذر قراءة الملف. الرجاء استخدام CSV أو XLSX صحيح.", "danger")
        return render_template("warehouses/import_products.html", form=form, warehouse=w)

    analysis = _analyze(rows)
    payload = {
        "warehouse_id": w.id,
        "filename": filename or f"upload_{uuid.uuid4().hex}",
        "file_sha256": file_sha256,
        "strategy": getattr(form, "duplicate_strategy", None).data if hasattr(form, "duplicate_strategy") else "skip",
        "dry_run": bool(getattr(form, "dry_run", None).data) if hasattr(form, "dry_run") else True,
        "continue_after_warnings": bool(getattr(form, "continue_after_warnings", None).data) if hasattr(form, "continue_after_warnings") else False,
        "created_by": getattr(current_user, "id", None),
        "created_at": datetime.utcnow().isoformat(),
        "analysis": analysis,
    }
    key = _save_tmp_payload(payload)

    rpt = analysis.get("report", {})
    if rpt.get("missing_required_rows") and not payload["continue_after_warnings"]:
        flash(f"هناك صفوف بدون اسم (إجباري): {len(rpt['missing_required_rows'])} صف. يمكنك تعديل الملف وإعادة الرفع، أو متابعة المعاينة.", "warning")

    return redirect(url_for("warehouse_bp.import_preview", id=w.id, token=key))

@warehouse_bp.route("/<int:warehouse_id>/preview/update", methods=["POST"], endpoint="preview_update")
@login_required
@permission_required("manage_inventory")
def preview_update(warehouse_id: int):
    w = _get_or_404(Warehouse, warehouse_id)
    data = request.get_json(silent=True) or {}
    pid = data.get("product_id")
    field = (data.get("field") or "").strip()
    raw_value = data.get("value")

    if not pid or not field:
        return jsonify({"ok": False, "message": "بيانات غير مكتملة"}), 400

    p = db.session.get(Product, int(pid))
    if not p:
        return jsonify({"ok": False, "message": "المنتج غير موجود"}), 404

    numeric_fields = {"price", "purchase_price", "selling_price", "min_price", "max_price", "tax_rate", "weight", "cost_before_shipping", "cost_after_shipping", "unit_price_before_tax", "online_price"}
    int_fields = {"min_qty", "reorder_point", "warranty_period"}

    def as_decimal(v):
        return _clean_numeric(v)

    def as_int(v):
        return _clean_int(v)

    def _exists(col, val):
        if val in (None, "", "None"):
            return False
        q = db.session.query(Product.id).filter(Product.id != p.id, col == val).first()
        return q is not None

    clean_value = None
    row_total = None

    try:
        if field == "quantity":
            qty = as_int(raw_value)
            if qty is None or qty < 0:
                return jsonify({"ok": False, "message": "قيمة الكمية غير صالحة"}), 400
            sl = StockLevel.query.filter_by(warehouse_id=w.id, product_id=p.id).first()
            if not sl:
                sl = StockLevel(warehouse_id=w.id, product_id=p.id, quantity=0, reserved_quantity=0)
                db.session.add(sl)
            sl.quantity = qty
            clean_value = qty

        elif field in numeric_fields:
            dv = as_decimal(raw_value)
            if dv is None:
                return jsonify({"ok": False, "message": "قيمة رقمية غير صالحة"}), 400
            setattr(p, field, dv)
            clean_value = str(dv)

        elif field in int_fields:
            iv = as_int(raw_value)
            setattr(p, field, iv)
            clean_value = iv if iv is not None else ""

        elif field in {"sku", "part_number", "name", "brand", "commercial_name", "unit", "barcode", "category_name", "dimensions", "image", "online_image", "origin_country", "chassis_number", "serial_no"}:
            sv = (str(raw_value or "").strip() or None)
            if field == "barcode" and sv and _exists(Product.barcode, sv):
                db.session.rollback()
                return jsonify({"ok": False, "message": "الباركود مستخدم بالفعل"}), 400
            if field == "sku" and sv and _exists(Product.sku, sv):
                db.session.rollback()
                return jsonify({"ok": False, "message": "SKU مستخدم بالفعل"}), 400
            if field == "serial_no" and sv and _exists(Product.serial_no, sv):
                db.session.rollback()
                return jsonify({"ok": False, "message": "الرقم التسلسلي مستخدم بالفعل"}), 400
            setattr(p, field, sv)
            clean_value = sv or ""

        else:
            return jsonify({"ok": False, "message": "حقل غير مدعوم"}), 400

        db.session.commit()

        sl_cur = StockLevel.query.filter_by(warehouse_id=w.id, product_id=p.id).first()
        q = int(getattr(sl_cur, "quantity", 0) or 0)
        sp = Decimal(str(getattr(p, "selling_price", 0) or 0))
        row_total = float(sp * q)

        return jsonify({"ok": True, "clean_value": clean_value, "row_total": row_total})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "message": str(e)}), 500


@warehouse_bp.route("/<int:id>/import/preview", methods=["GET", "POST"], endpoint="import_preview")
@login_required
@permission_required("manage_inventory")
def import_preview(id):
    w = _get_or_404(Warehouse, id)
    token = request.args.get("token") or request.form.get("token")
    payload = _load_tmp_payload(token) if token else None

    if not payload or payload.get("warehouse_id") != w.id:
        flash("جلسة المعاينة غير صالحة أو انتهت.", "danger")
        return redirect(url_for("warehouse_bp.import_products", id=w.id))

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        if action == "commit":
            return redirect(url_for("warehouse_bp.import_commit", id=w.id, token=token))

        rows_json = request.form.get("rows_json")
        if rows_json:
            try:
                obj = json.loads(rows_json)
                edited = obj.get("normalized") or obj.get("rows") or []
                raw_rows = [(r.get("data") if isinstance(r, dict) else r) for r in edited]
                payload["analysis"] = _analyze(raw_rows)
                _write_tmp_payload(token, payload)
                flash("تم حفظ تعديلات المعاينة.", "success")
            except:
                flash("تعذر حفظ التعديلات.", "danger")

        return redirect(url_for("warehouse_bp.import_preview", id=w.id, token=token))

    analysis = payload.get("analysis") or {}
    rows = analysis.get("normalized") or []
    report = analysis.get("report") or {
        "total": 0,
        "missing_required_rows": [],
        "warnings": [],
        "matches": 0,
        "new_items": 0
    }

    return render_template(
        "warehouses/import_preview.html",
        warehouse=w,
        token=token,
        rows=rows,
        report=report,
        strategy=payload.get("strategy", "skip"),
        dry_run=payload.get("dry_run", True),
    )

@warehouse_bp.route("/<int:id>/import/commit", methods=["POST"], endpoint="import_commit")
@login_required
@permission_required("manage_inventory")
def import_commit(id):
    w = _get_or_404(Warehouse, id)
    token = request.form.get("token") or request.args.get("token")
    payload = _load_tmp_payload(token) if token else None
    if not payload or payload.get("warehouse_id") != w.id:
        flash("جلسة الترحيل غير صالحة.", "danger")
        return redirect(url_for("warehouse_bp.import_products", id=w.id))

    def _parse_bool(v):
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

    try:
        rows_json = request.form.get("rows_json")
        if rows_json:
            try:
                obj = json.loads(rows_json)
                raw_rows = [
                    r.get("data") if isinstance(r, dict) else r
                    for r in (obj.get("normalized") or obj.get("rows") or [])
                ]
                analysis = _analyze(raw_rows)
            except:
                analysis = payload.get("analysis") or {}
        else:
            analysis = payload.get("analysis") or {}

        rows = analysis.get("normalized") or []
        strategy = (
            (request.form.get("strategy") or payload.get("strategy") or "skip")
            .strip()
            .lower()
        )
        dry_run = _parse_bool(
            request.form.get("dry_run") or payload.get("dry_run", True)
        )

        inserted = updated = skipped = errors = 0
        t0 = time.perf_counter()
        report_rows = []

        # === Preload existing unique fields ===
        all_skus = set()
        all_barcodes = set()
        all_serials = set()
        for item in rows:
            d = item.get("data") or {}
            if d.get("sku"):
                all_skus.add(d["sku"].strip().upper())
            if d.get("part_number"):
                all_skus.add(str(d["part_number"]).strip().upper())
            if d.get("barcode"):
                all_barcodes.add(d["barcode"].strip())
            if d.get("serial_no"):
                all_serials.add(d["serial_no"].strip().upper())

        existing_skus = {
            (s or "").upper(): pid
            for pid, s in db.session.query(Product.id, Product.sku)
            .filter(Product.sku.isnot(None))
            .all()
        }
        existing_barcodes = {
            b: pid
            for pid, b in db.session.query(Product.id, Product.barcode)
            .filter(Product.barcode.isnot(None))
            .all()
        }
        existing_serials = {
            (s or "").upper(): pid
            for pid, s in db.session.query(Product.id, Product.serial_no)
            .filter(Product.serial_no.isnot(None))
            .all()
        }

        for item in rows:
            data = dict(item.get("data") or {})
            name = (data.get("name") or "").strip()
            if not name:
                skipped += 1
                report_rows.append(
                    {
                        "action": "skip",
                        "strategy": strategy,
                        "sku": data.get("sku") or "",
                        "name": "",
                        "product_id": "",
                        "qty_added": 0,
                        "stock_before": 0,
                        "stock_after": 0,
                        "purchase_price": 0,
                        "selling_price": 0,
                        "min_price": 0,
                        "max_price": 0,
                        "tax_rate": 0,
                        "note": "missing_name",
                    }
                )
                continue

            sku = (data.get("sku") or "").strip().upper()
            if not sku and data.get("part_number"):
                sku = str(data["part_number"]).strip().upper()

            def _dv(k, d=None):
                v = data.get(k)
                if v in (None, "", "None"):
                    return d
                try:
                    return Decimal(str(v))
                except:
                    return d

            def _iv(k):
                try:
                    v = data.get(k)
                    return int(float(v)) if v not in (None, "", "None") else None
                except:
                    return None

            price = _dv("price")
            selling_price = _dv("selling_price", price)
            purchase_price = _dv("purchase_price")
            online_price = _dv("online_price")
            qty = max(_iv("quantity") or 0, 0)

            pid = item.get("match", {}).get("product_id")
            p = db.session.get(Product, pid) if pid else None

            effective_action = None
            before_qty = after_qty = 0

            if p is None:
                duplicate = False
                for field, lookup, store in (
                    ("sku", sku, existing_skus),
                    ("barcode", (data.get("barcode") or "").strip(), existing_barcodes),
                    ("serial_no", (data.get("serial_no") or "").strip().upper(), existing_serials),
                ):
                    if lookup and lookup in store:
                        errors += 1
                        report_rows.append(
                            {
                                "action": "skip",
                                "strategy": strategy,
                                "sku": data.get("sku") or "",
                                "name": name,
                                "product_id": "",
                                "qty_added": 0,
                                "stock_before": 0,
                                "stock_after": 0,
                                "purchase_price": 0,
                                "selling_price": 0,
                                "min_price": 0,
                                "max_price": 0,
                                "tax_rate": 0,
                                "note": f"duplicate_{field}",
                            }
                        )
                        duplicate = True
                        break
                if duplicate:
                    continue

                p = Product(
                    name=name,
                    sku=sku or None,
                    part_number=data.get("part_number") or None,
                    brand=data.get("brand") or None,
                    commercial_name=data.get("commercial_name") or None,
                    chassis_number=data.get("chassis_number") or None,
                    serial_no=data.get("serial_no") or None,
                    barcode=data.get("barcode") or None,
                    unit=data.get("unit") or None,
                    category_name=data.get("category_name") or None,
                    price=price or 0,
                    selling_price=selling_price or (price or 0),
                    purchase_price=purchase_price or 0,
                    cost_before_shipping=_dv("cost_before_shipping", 0),
                    cost_after_shipping=_dv("cost_after_shipping", 0),
                    unit_price_before_tax=_dv("unit_price_before_tax", 0),
                    min_price=_dv("min_price"),
                    max_price=_dv("max_price"),
                    tax_rate=_dv("tax_rate", 0),
                    min_qty=_iv("min_qty") or 0,
                    reorder_point=_iv("reorder_point"),
                    condition=data.get("condition") or "NEW",
                    origin_country=data.get("origin_country") or None,
                    warranty_period=_iv("warranty_period"),
                    weight=_dv("weight"),
                    dimensions=data.get("dimensions") or None,
                    image=data.get("image") or None,
                    online_price=online_price,
                    online_image=data.get("online_image") or None,
                    is_active=True,
                    is_digital=False,
                    is_exchange=False,
                )
                db.session.add(p)
                db.session.flush()
                if not p.category_id and p.category_name:
                    p.category_id = _ensure_category_id(p.category_name)
                inserted += 1
                effective_action = "insert"
            else:
                if strategy == "skip":
                    skipped += 1
                    effective_action = "skip"
                elif strategy in ("update_product", "stock_only"):
                    if strategy == "update_product":
                        dup_conflict = False
                        for fld, lookup, store in (
                            ("sku", sku, existing_skus),
                            ("barcode", (data.get("barcode") or "").strip(), existing_barcodes),
                            ("serial_no", (data.get("serial_no") or "").strip().upper(), existing_serials),
                        ):
                            if lookup and lookup in store and store[lookup] != p.id:
                                errors += 1
                                report_rows.append(
                                    {
                                        "action": "skip",
                                        "strategy": strategy,
                                        "sku": data.get("sku") or "",
                                        "name": name,
                                        "product_id": p.id,
                                        "qty_added": 0,
                                        "stock_before": 0,
                                        "stock_after": 0,
                                        "purchase_price": float(purchase_price or 0),
                                        "selling_price": float(selling_price or 0),
                                        "min_price": float(_dv("min_price") or 0),
                                        "max_price": float(_dv("max_price") or 0),
                                        "tax_rate": float(_dv("tax_rate", 0)),
                                        "note": f"duplicate_{fld}_update",
                                    }
                                )
                                dup_conflict = True
                                break
                        if dup_conflict:
                            continue
                        p.name = name or p.name
                        p.brand = data.get("brand") or p.brand
                        p.part_number = data.get("part_number") or p.part_number
                        p.sku = sku or p.sku
                        if price is not None:
                            p.price = price
                        if selling_price is not None:
                            p.selling_price = selling_price
                        if purchase_price is not None:
                            p.purchase_price = purchase_price
                        if online_price is not None:
                            p.online_price = online_price
                        p.min_price = _dv("min_price", p.min_price)
                        p.max_price = _dv("max_price", p.max_price)
                        p.tax_rate = _dv("tax_rate", p.tax_rate)
                        p.unit = data.get("unit") or p.unit
                        p.category_name = data.get("category_name") or p.category_name
                        if not p.category_id and p.category_name:
                            p.category_id = _ensure_category_id(p.category_name)
                    updated += 1
                    effective_action = "update"

            if effective_action != "skip":
                if qty > 0:
                    sl = StockLevel.query.filter_by(
                        warehouse_id=w.id, product_id=p.id
                    ).first()
                    before_qty = int(sl.quantity or 0) if sl else 0
                    if not sl:
                        sl = StockLevel(
                            warehouse_id=w.id,
                            product_id=p.id,
                            quantity=0,
                            reserved_quantity=0,
                        )
                        db.session.add(sl)
                    sl.quantity = before_qty + qty
                    after_qty = int(sl.quantity or 0)
                else:
                    sl = StockLevel.query.filter_by(
                        warehouse_id=w.id, product_id=p.id
                    ).first()
                    before_qty = after_qty = int(sl.quantity or 0) if sl else 0

            report_rows.append(
                {
                    "action": effective_action or "skip",
                    "strategy": strategy,
                    "sku": sku,
                    "name": name,
                    "product_id": p.id if p else "",
                    "qty_added": qty if effective_action != "skip" else 0,
                    "stock_before": before_qty,
                    "stock_after": after_qty,
                    "purchase_price": float(purchase_price or 0),
                    "selling_price": float(selling_price or 0),
                    "min_price": float(_dv("min_price") or 0),
                    "max_price": float(_dv("max_price") or 0),
                    "tax_rate": float(_dv("tax_rate", 0)),
                    "note": item.get("note") or "",
                }
            )

        duration_ms = int((time.perf_counter() - t0) * 1000)

        if dry_run:
            db.session.rollback()
            try:
                db.session.add(
                    ImportRun(
                        warehouse_id=w.id,
                        user_id=current_user.id,
                        filename=payload.get("filename"),
                        file_sha256=payload.get("file_sha256"),
                        dry_run=True,
                        inserted=inserted,
                        updated=updated,
                        skipped=skipped,
                        errors=errors,
                        duration_ms=duration_ms,
                        notes="dry_run",
                        meta={"token": token},
                    )
                )
                db.session.commit()
            except:
                db.session.rollback()
            flash(
                f"فحص فقط: جديد={inserted}, تحديث={updated}, متجاهل={skipped}, أخطاء={errors}",
                "info",
            )
        else:
            db.session.commit()
            path = _save_import_report_csv(
                report_rows,
                filename_hint=f"wh{w.id}_{token or uuid.uuid4().hex}_{int(time.time())}",
            )
            try:
                db.session.add(
                    ImportRun(
                        warehouse_id=w.id,
                        user_id=current_user.id,
                        filename=payload.get("filename"),
                        file_sha256=payload.get("file_sha256"),
                        dry_run=False,
                        inserted=inserted,
                        updated=updated,
                        skipped=skipped,
                        errors=errors,
                        duration_ms=duration_ms,
                        report_path=path,
                        meta={"token": token, "rows": len(report_rows)},
                    )
                )
                db.session.commit()
            except:
                db.session.rollback()
            flash(
                f"تم الترحيل: جديد={inserted}, تحديث={updated}, متجاهل={skipped}, أخطاء={errors}",
                "success",
            )
    except Exception as e:
        db.session.rollback()
        flash(f"فشل الترحيل: {e}", "danger")

    return redirect(url_for("warehouse_bp.detail", warehouse_id=w.id))

@warehouse_bp.route("/<int:warehouse_id>/stock", methods=["POST"], endpoint="ajax_update_stock")
@login_required
@permission_required("manage_inventory")
def ajax_update_stock(warehouse_id):
    data = request.get_json(silent=True) or request.form

    def _to_int(v, default=None):
        try:
            if v in (None, "", "None"):
                return default
            return int(float(v))
        except Exception:
            return default

    def _resolve_product_id():
        pid = _to_int(data.get("product_id"))
        if pid:
            return pid
        ref = (data.get("product_ref") or data.get("barcode") or "").strip()
        if not ref:
            return None
        q = (
            db.session.query(Product.id)
            .filter(
                or_(
                    func.lower(Product.sku) == ref.lower(),
                    func.lower(Product.part_number) == ref.lower(),
                    Product.barcode == ref,
                )
            )
            .first()
        )
        return q[0] if q else None

    pid = _resolve_product_id()
    if pid is None:
        return jsonify({"success": False, "code": "INVALID_PRODUCT", "errors": {"product_id": "required_or_unresolvable"}}), 400

    quantity  = _to_int(data.get("quantity"), 0)
    min_stock = _to_int(data.get("min_stock"))
    max_stock = _to_int(data.get("max_stock"))

    sl = (
        StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=pid)
        .with_for_update(nowait=False)
        .first()
    )
    if not sl:
        sl = StockLevel(warehouse_id=warehouse_id, product_id=pid, quantity=0, reserved_quantity=0)
        db.session.add(sl)

    sl.quantity = max(0, quantity if quantity is not None else int(sl.quantity or 0))
    if min_stock is not None:
        sl.min_stock = max(0, min_stock)
    if max_stock is not None:
        sl.max_stock = max(0, max_stock)

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "code": "DB_ERROR", "error": str(e)}), 500

    alert = "BELOW_MIN" if int(sl.quantity or 0) <= int(sl.min_stock or 0) else "OK"
    p = db.session.get(Product, pid)
    w = db.session.get(Warehouse, warehouse_id)
    warnings = []
    if _is_online_wh(w):
        if getattr(p, "online_price", None) in (None, 0, Decimal("0")):
            warnings.append("missing_online_price")
        if not (getattr(p, "online_image", None) or getattr(p, "image", None)):
            warnings.append("missing_online_image")

    return jsonify({
        "success": True,
        "code": "UPDATED",
        "data": {
            "warehouse_id": warehouse_id,
            "product": {"id": p.id, "name": p.name, "sku": p.sku, "part_number": p.part_number, "barcode": p.barcode},
            "on_hand": int(sl.quantity or 0),
            "reserved": int(getattr(sl, "reserved_quantity", 0) or 0),
            "min_stock": int(sl.min_stock or 0),
            "max_stock": int(sl.max_stock or 0),
            "alert": alert,
            "warnings": warnings,
            "partner_share": getattr(sl, "partner_share_quantity", None),
            "company_share": getattr(sl, "company_share_quantity", None),
        }
    }), 200

@warehouse_bp.route("/<int:warehouse_id>/transfer", methods=["POST"], endpoint="ajax_transfer")
@login_required
@permission_required("manage_inventory", "manage_warehouses", "warehouse_transfer")
def ajax_transfer(warehouse_id):
    data = request.get_json(silent=True) or request.form
    def _i(name):
        v = data.get(name)
        try:
            return int(v) if v is not None and str(v).strip() != "" else None
        except Exception:
            return None
    pid = _i("product_id")
    sid = _i("source_id")
    did = _i("destination_id")
    try:
        qty = int(float(data.get("quantity", 0)))
    except Exception:
        qty = 0
    ds = (data.get("date") or "").strip()
    try:
        tdate = datetime.fromisoformat(ds) if ds else datetime.utcnow()
    except Exception:
        tdate = datetime.utcnow()
    notes = (data.get("notes") or "").strip() or None
    if not (pid and sid and did and qty > 0) or sid == did:
        return jsonify({"success": False, "errors": {"form": "invalid"}}), 400
    if sid != warehouse_id:
        return jsonify({"success": False, "errors": {"warehouse": "mismatch"}}), 400
    try:
        with db.session.begin():
            src = (StockLevel.query.filter_by(warehouse_id=sid, product_id=pid).with_for_update(nowait=False).first())
            if not src:
                src = StockLevel(warehouse_id=sid, product_id=pid, quantity=0, reserved_quantity=0)
                db.session.add(src); db.session.flush()
            available = int((src.quantity or 0) - (src.reserved_quantity or 0))
            if available < qty:
                raise ValueError("insufficient_stock")
            src.quantity = int(src.quantity or 0) - qty
            dst = (StockLevel.query.filter_by(warehouse_id=did, product_id=pid).with_for_update(nowait=False).first())
            if not dst:
                dst = StockLevel(warehouse_id=did, product_id=pid, quantity=0, reserved_quantity=0)
                db.session.add(dst); db.session.flush()
            dst.quantity = int(dst.quantity or 0) + qty
            t = Transfer(transfer_date=tdate, product_id=pid, source_id=sid, destination_id=did,
                         quantity=qty, direction="OUT", notes=notes, user_id=getattr(current_user, "id", None))
            db.session.add(t)
        return jsonify({"success": True, "transfer_id": t.id,
                        "direction": "OUT",
                        "source_onhand": int(src.quantity or 0),
                        "destination_onhand": int(dst.quantity or 0)}), 200
    except ValueError as ve:
        db.session.rollback()
        if str(ve) == "insufficient_stock":
            return jsonify({"success": False, "error": "insufficient_stock"}), 400
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

@warehouse_bp.route("/<int:warehouse_id>/exchange", methods=["POST"], endpoint="ajax_exchange")
@login_required
@permission_required("manage_inventory")
def ajax_exchange(warehouse_id):
    data = request.form if request.form else (request.get_json(silent=True) or {})
    def _i(k, d=None):
        try:
            v = data.get(k); return int(v) if v not in (None, "", "None") else d
        except: return d
    def _qty(v):
        try: return int(float(v))
        except: return 0
    def _f(v):
        try: return float(v) if v not in (None, "", "None") else None
        except: return None
    pid = _i("product_id")
    partner_id = _i("partner_id")
    qty = _qty(data.get("quantity"))
    direction = (data.get("direction") or "").upper()
    unit_cost = _f(data.get("unit_cost"))
    notes = data.get("notes") or None
    if not (pid and qty > 0 and direction in ("IN", "OUT", "ADJUSTMENT")):
        return jsonify({"success": False, "errors": {"form": "invalid"}}), 400
    try:
        with db.session.begin():
            ex = ExchangeTransaction(product_id=pid, warehouse_id=warehouse_id, partner_id=partner_id,
                                     quantity=qty, direction=direction, unit_cost=unit_cost,
                                     is_priced=bool(unit_cost is not None), notes=notes)
            db.session.add(ex)
            sl = (StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=pid)
                  .with_for_update(nowait=False).first())
            if not sl:
                sl = StockLevel(warehouse_id=warehouse_id, product_id=pid, quantity=0, reserved_quantity=0)
                db.session.add(sl); db.session.flush()
            if direction == "OUT":
                available = int((sl.quantity or 0) - (sl.reserved_quantity or 0))
                if available < qty: raise ValueError("insufficient_stock")
                sl.quantity = int(sl.quantity or 0) - qty
            elif direction == "IN":
                sl.quantity = int(sl.quantity or 0) + qty
            elif direction == "ADJUSTMENT":
                sl.quantity = max(0, int(sl.quantity or 0) + qty)
        return jsonify({"success": True, "new_quantity": int(sl.quantity or 0)}), 200
    except ValueError as ve:
        db.session.rollback()
        if str(ve) == "insufficient_stock":
            return jsonify({"success": False, "error": "insufficient_stock"}), 400
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

@warehouse_bp.route("/<int:warehouse_id>/partner-shares", methods=["GET", "POST"], endpoint="partner_shares")
@login_required
@permission_required("manage_inventory")
def partner_shares(warehouse_id):
    if request.method == "GET":
        try:
            wps = (WarehousePartnerShare.query.join(Product, WarehousePartnerShare.product_id == Product.id)
                   .filter(WarehousePartnerShare.warehouse_id == warehouse_id).all())
        except Exception:
            wps = []
        rows = wps or (ProductPartnerShare.query.join(Product)
                       .join(StockLevel, StockLevel.product_id == ProductPartnerShare.product_id)
                       .filter(StockLevel.warehouse_id == warehouse_id).all())
        data = []
        for s in rows:
            partner = getattr(s, "partner", None)
            product = getattr(s, "product", None)
            pct = float(getattr(s, "share_percentage", getattr(s, "share_percent", 0)) or 0)
            amt = float(getattr(s, "share_amount", 0) or 0)
            data.append({"id": getattr(s, "id", None),
                         "product": product.name if product else None,
                         "partner": partner.name if partner else None,
                         "share_percentage": pct, "share_amount": amt,
                         "notes": s.notes or ""})
        return jsonify({"success": True, "shares": data}), 200
    payload = request.get_json(silent=True) or {}
    updates = payload.get("shares", [])
    if not isinstance(updates, list):
        return jsonify({"success": False, "error": "invalid_payload"}), 400
    try:
        valid_products = {sl.product_id for sl in StockLevel.query.filter_by(warehouse_id=warehouse_id).all()}
        for item in updates:
            pid = item.get("product_id"); prt = item.get("partner_id")
            if not (isinstance(pid, int) and isinstance(prt, int)): continue
            if valid_products and pid not in valid_products: continue
            pct = float(item.get("share_percentage", item.get("share_percent", 0)) or 0)
            try: amt = float(item.get("share_amount", 0) or 0)
            except Exception: amt = 0.0
            notes = (item.get("notes") or "").strip() or None
            row = WarehousePartnerShare.query.filter_by(warehouse_id=warehouse_id, product_id=pid, partner_id=prt).first()
            if row:
                row.share_percentage = pct; row.share_amount = amt; row.notes = notes
            else:
                db.session.add(WarehousePartnerShare(warehouse_id=warehouse_id, product_id=pid,
                                                     partner_id=prt, share_percentage=pct,
                                                     share_amount=amt, notes=notes))
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@warehouse_bp.route("/<int:id>/transfers", methods=["GET"], endpoint="transfers")
@login_required
@permission_required("view_inventory")
def list_transfers(id):
    warehouse = _get_or_404(Warehouse, id)
    transfers = Transfer.query.filter(or_(Transfer.source_id == id, Transfer.destination_id == id)).order_by(Transfer.transfer_date.desc()).all()
    return render_template("warehouses/transfers_list.html", warehouse=warehouse, transfers=transfers)


@warehouse_bp.route("/<int:id>/transfers/create", methods=["GET", "POST"], endpoint="create_transfer")
@login_required
@permission_required("manage_inventory")
def create_transfer(id=None):
    wid = id
    warehouse = _get_or_404(Warehouse, wid)
    form = TransferForm()

    def respond_error(msg, code=400):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return jsonify(ok=False, error=msg), code
        flash(msg, "danger")
        return render_template("warehouses/transfers_form.html", warehouse=warehouse, form=form), code

    def respond_ok(redirect_to):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return jsonify(ok=True, message="تم إضافة التحويل بنجاح", redirect=redirect_to)
        flash("تم إضافة التحويل بنجاح", "success")
        return redirect(redirect_to)

    if form.validate_on_submit():
        t = form.apply_to(Transfer())
        t.user_id = current_user.id
        if not t.product_id:
            return respond_error("اختر الصنف المطلوب تحويله.")
        if not t.source_id or not t.destination_id:
            return respond_error("يجب اختيار كل من المستودع المصدِر والمستودع الوجهة.")
        if int(t.quantity or 0) <= 0:
            return respond_error("الكمية يجب أن تكون رقمًا موجبًا أكبر من صفر.")
        if int(t.source_id) == int(t.destination_id):
            return respond_error("لا يمكن التحويل إلى نفس المستودع. اختر مستودعًا مختلفًا.")
        try:
            with db.session.begin():
                src = StockLevel.query.filter_by(warehouse_id=t.source_id, product_id=t.product_id).with_for_update(nowait=False).first()
                if not src:
                    src = StockLevel(warehouse_id=t.source_id, product_id=t.product_id, quantity=0, reserved_quantity=0)
                    db.session.add(src)
                    db.session.flush()
                available = int((src.quantity or 0) - (src.reserved_quantity or 0))
                req_qty = int(t.quantity or 0)
                if available < req_qty:
                    return respond_error(f"الكمية غير كافية في المستودع المصدِر. المتاح: {available}، المطلوب: {req_qty}.")
                dst = StockLevel.query.filter_by(warehouse_id=t.destination_id, product_id=t.product_id).with_for_update(nowait=False).first()
                if not dst:
                    dst = StockLevel(warehouse_id=t.destination_id, product_id=t.product_id, quantity=0, reserved_quantity=0)
                    db.session.add(dst)
                    db.session.flush()
                src.quantity = available - req_qty
                dst.quantity = int(dst.quantity or 0) + req_qty
                db.session.add(t)
            return respond_ok(url_for("warehouse_bp.transfers", id=wid))
        except IntegrityError:
            db.session.rollback()
            return respond_error("خطأ مرجعي في قاعدة البيانات (IntegrityError). تأكد من صحة اختيارك للمستودعات والصنف.")
        except Exception as e:
            db.session.rollback()
            return respond_error(f"حدث خطأ غير متوقع أثناء إضافة التحويل: {e}")

    if request.method == "POST" and form.errors:
        msgs = []
        for field, errs in form.errors.items():
            for err in errs:
                msgs.append(err)
        if msgs:
            return respond_error("؛ ".join(msgs))

    return render_template("warehouses/transfers_form.html", warehouse=warehouse, form=form)

@warehouse_bp.route("/parts/<int:product_id>", methods=["GET"], endpoint="product_card")
@login_required
@permission_required("view_parts")
def product_card(product_id):
    part = Product.query.options(
        joinedload(Product.supplier_international),
        joinedload(Product.supplier_local),
        joinedload(Product.supplier_general),
        joinedload(Product.vehicle_type),
        joinedload(Product.category),
    ).filter_by(id=product_id).first()
    if part is None:
        abort(404)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    stock = []
    for w in warehouses:
        lvl = StockLevel.query.filter_by(product_id=part.id, warehouse_id=w.id).first()
        qty = (lvl.quantity or 0) if lvl else 0
        res = getattr(lvl, "reserved_quantity", 0) if lvl else 0
        stock.append({"warehouse": w, "on_hand": qty, "reserved": res, "virtual_available": qty - res})
    transfers = Transfer.query.filter_by(product_id=part.id).options(joinedload(Transfer.source_warehouse), joinedload(Transfer.destination_warehouse)).order_by(Transfer.transfer_date.desc()).all()
    exchanges = ExchangeTransaction.query.filter_by(product_id=part.id).options(joinedload(ExchangeTransaction.partner)).order_by(getattr(ExchangeTransaction, "created_at", ExchangeTransaction.id).desc()).all()
    shipments = ShipmentItem.query.filter_by(product_id=part.id).join(Shipment).options(joinedload(ShipmentItem.shipment), joinedload(ShipmentItem.warehouse)).order_by(func.coalesce(Shipment.actual_arrival, Shipment.expected_arrival, Shipment.shipment_date).desc()).all()
    return render_template("parts/card.html", part=part, stock=stock, transfers=transfers, exchanges=exchanges, shipments=shipments)


@warehouse_bp.route("/preorders", methods=["GET"], endpoint="preorders_list")
@login_required
@permission_required("view_preorders")
def preorders_list():
    q = (PreOrder.query.options(
            joinedload(PreOrder.customer),
            joinedload(PreOrder.supplier),
            joinedload(PreOrder.partner),
            joinedload(PreOrder.product),
            joinedload(PreOrder.warehouse)
        ))
    status = (request.args.get("status") or "").strip()
    code = (request.args.get("code") or "").strip()
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    if status:
        q = q.filter(PreOrder.status == status)
    if code:
        q = q.filter(PreOrder.reference.ilike(f"%{code}%"))
    try:
        if df:
            q = q.filter(PreOrder.created_at >= datetime.fromisoformat(df))
        if dt:
            q = q.filter(PreOrder.created_at <= datetime.fromisoformat(dt))
    except ValueError:
        pass
    q = q.order_by(PreOrder.created_at.desc())
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    preorders = pagination.items
    wants_json = (request.args.get("format") == "json") or ("application/json" in request.headers.get("Accept", ""))
    if wants_json:
        def _entity_info(p):
            if p.customer_id:
                return "customer", (p.customer.name if p.customer else None)
            if p.supplier_id:
                return "supplier", (p.supplier.name if p.supplier else None)
            if p.partner_id:
                return "partner", (p.partner.name if p.partner else None)
            return None, None
        data = []
        for p in preorders:
            etype, ename = _entity_info(p)
            data.append(
                {
                    "id": p.id,
                    "code": p.reference,
                    "entity_type": etype,
                    "entity_name": ename,
                    "product": p.product.name if p.product else None,
                    "warehouse": p.warehouse.name if p.warehouse else None,
                    "quantity": int(p.quantity or 0),
                    "prepaid_amount": float(p.prepaid_amount or 0),
                    "status": p.status,
                    "status_label": _inject_utils()["ar_label"]("preorder_status", p.status),
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
            )
        return jsonify({"data": data, "meta": {"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total, "pages": pagination.pages}})
    return render_template("parts/preorders_list.html", preorders=preorders, pagination=pagination, filters={"status": status or None, "code": code or None, "date_from": df or None, "date_to": dt or None})


@warehouse_bp.route("/preorders/create", methods=["GET", "POST"], endpoint="preorder_create")
@login_required
@permission_required("add_preorder")
def preorder_create():
    form = PreOrderForm()

    def _gen_ref():
        base = datetime.utcnow().strftime("PR%Y%m%d")
        for _ in range(10):
            code = f"{base}-{str(random.randint(0, 9999)).zfill(4)}"
            if not db.session.query(PreOrder.id).filter_by(reference=code).first():
                return code
        return uuid.uuid4().hex[:10].upper()

    if form.validate_on_submit():
        customer_id = int(form.customer_id.data)
        product_id = int(form.product_id.data)
        warehouse_id = int(form.warehouse_id.data)
        qty = int(form.quantity.data or 1)
        prepaid = float(form.prepaid_amount.data or 0)
        tax = float(form.tax_rate.data or 0)

        user_ref = (form.reference.data or "").strip()
        # لا نتحقق من التكرار هنا، سنعتمد على IntegrityError لاحقاً
        code = user_ref or _gen_ref()

        preorder = PreOrder(
            reference=code,
            preorder_date=form.preorder_date.data or datetime.utcnow(),
            expected_date=form.expected_date.data or None,
            customer_id=customer_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=qty,
            prepaid_amount=prepaid,
            tax_rate=tax,
            status=form.status.data,
            notes=form.notes.data or None,
            payment_method=form.payment_method.data or "cash",
        )
        db.session.add(preorder)
        db.session.flush()

        sl = StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).with_for_update(nowait=False).first()
        if not sl:
            sl = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0, reserved_quantity=0)
            db.session.add(sl)
            db.session.flush()
        
        # التحقق من الكمية المتاحة
        available = int(sl.quantity or 0) - int(sl.reserved_quantity or 0)
        if available < qty:
            flash(f"الكمية المتاحة ({available}) غير كافية! الكمية المطلوبة: {qty}", "danger")
            return render_template("parts/preorder_form.html", form=form), 200
        
        sl.reserved_quantity = int(sl.reserved_quantity or 0) + int(qty)


        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            # إعادة حجز الكمية بعد rollback
            sl = StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
            if not sl:
                sl = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0, reserved_quantity=0)
                db.session.add(sl)
                db.session.flush()
            
            # التحقق من الكمية المتاحة
            available = int(sl.quantity or 0) - int(sl.reserved_quantity or 0)
            if available < qty:
                flash(f"الكمية المتاحة ({available}) غير كافية! الكمية المطلوبة: {qty}", "danger")
                return render_template("parts/preorder_form.html", form=form), 200
            
            sl.reserved_quantity = int(sl.reserved_quantity or 0) + int(qty)
            
            if "preorders.reference" in str(e).lower() and not user_ref:
                # المرجع التلقائي مكرر، نولد مرجع جديد
                preorder.reference = _gen_ref()
                db.session.add(preorder)
                try:
                    db.session.commit()
                except SQLAlchemyError as ee:
                    db.session.rollback()
                    flash(f"تعذر حفظ الحجز: {getattr(ee, 'orig', ee)}", "danger")
                    return render_template("parts/preorder_form.html", form=form), 200
            else:
                flash("مرجع الحجز مستخدم مسبقًا. غيّر المرجع أو اتركه فارغًا ليُولَّد تلقائيًا.", "danger")
                return render_template("parts/preorder_form.html", form=form), 200
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"تعذر حفظ الحجز: {getattr(e, 'orig', e)}", "danger")
            return render_template("parts/preorder_form.html", form=form), 200

        if prepaid > 0:
            pay = Payment(
                entity_type=(PaymentEntityType.PREORDER.value if hasattr(PaymentEntityType, "PREORDER") else "PREORDER"),
                preorder_id=preorder.id,
                direction=PaymentDirection.IN.value,
                status=PaymentStatus.COMPLETED.value,
                payment_date=datetime.utcnow(),
                total_amount=prepaid,
                currency="ILS",
                method=form.payment_method.data or "cash",
                reference=f"Preorder {preorder.reference}",
                notes=f"دفعة عربون لحجز {preorder.product.name if preorder.product else ''} (كود: {preorder.reference})",
            )
            db.session.add(pay)
            try:
                db.session.commit()
                flash("تم إنشاء الحجز وتسجيل العربون", "success")
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f"تم إنشاء الحجز، لكن تعذر تسجيل الدفعة: {getattr(e, 'orig', e)}", "warning")
        else:
            flash("تم إنشاء الحجز بنجاح", "success")

        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))

    elif request.method == "POST":
        flash("فشل إنشاء الحجز. تحقق من الحقول المطلوبة.", "danger")

    return render_template("parts/preorder_form.html", form=form)


@warehouse_bp.route("/preorders/<int:preorder_id>", methods=["GET"], endpoint="preorder_detail")
@login_required
@permission_required("view_preorders")
def preorder_detail(preorder_id):
    preorder = PreOrder.query.options(
        joinedload(PreOrder.customer),
        joinedload(PreOrder.supplier),
        joinedload(PreOrder.partner),
        joinedload(PreOrder.product),
        joinedload(PreOrder.warehouse),
        joinedload(PreOrder.payments),
    ).filter_by(id=preorder_id).first()
    if preorder is None:
        abort(404)
    return render_template("parts/preorder_detail.html", preorder=preorder)


@warehouse_bp.route("/preorders/<int:preorder_id>/convert-to-sale", methods=["POST"], endpoint="preorder_convert_to_sale")
@login_required
@permission_required("create_sale")
def preorder_convert_to_sale(preorder_id):
    """تحويل الحجز المسبق إلى مبيعة وتوجيه للدفع"""
    from models import Sale, SaleLine, SaleStatus
    
    preorder = _get_or_404(PreOrder, preorder_id)
    
    if preorder.status in ("CANCELLED", "FULFILLED"):
        flash("لا يمكن تحويل حجز ملغي أو منفذ مسبقاً!", "danger")
        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))
    
    try:
        # حساب المبالغ
        qty = int(preorder.quantity or 0)
        unit_price = float(preorder.product.price or 0) if preorder.product else 0
        tax_rate = float(preorder.tax_rate or 0)
        prepaid = float(preorder.prepaid_amount or 0)
        
        subtotal = qty * unit_price
        total_with_tax = subtotal * (1 + tax_rate / 100)
        balance_due = max(0, total_with_tax - prepaid)
        
        # إنشاء المبيعة
        sale = Sale(
            customer_id=preorder.customer_id,
            seller_id=current_user.id,
            sale_date=datetime.utcnow(),
            preorder_id=preorder.id,
            status=SaleStatus.CONFIRMED.value,
            currency=preorder.currency or "ILS",
            tax_rate=tax_rate,
            total_amount=total_with_tax,
            total_paid=prepaid,  # العربون المدفوع مسبقاً
            balance_due=balance_due,
            notes=f"تحويل من حجز مسبق {preorder.reference or preorder.id}"
        )
        db.session.add(sale)
        db.session.flush()
        
        # إنشاء بند المبيعة
        sale_line = SaleLine(
            sale_id=sale.id,
            product_id=preorder.product_id,
            warehouse_id=preorder.warehouse_id,
            quantity=qty,
            unit_price=unit_price,
            tax_rate=tax_rate,
            discount_rate=0
        )
        db.session.add(sale_line)
        
        # تحديث StockLevel
        sl = StockLevel.query.filter_by(
            product_id=preorder.product_id, 
            warehouse_id=preorder.warehouse_id
        ).with_for_update(nowait=False).first()
        
        if not sl:
            flash("لا يوجد مخزون لهذا المنتج في المستودع!", "danger")
            db.session.rollback()
            return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))
        
        # تقليل reserved_quantity
        sl.reserved_quantity = max(int(sl.reserved_quantity or 0) - qty, 0)
        
        # تقليل quantity (شحن البضاعة)
        available = int(sl.quantity or 0)
        if available < qty:
            flash(f"الكمية المتاحة ({available}) غير كافية! المطلوب: {qty}", "danger")
            db.session.rollback()
            return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))
        
        sl.quantity = available - qty
        
        # تحديث حالة الحجز
        preorder.status = "FULFILLED"
        
        db.session.commit()
        
        flash(f"✅ تم تحويل الحجز إلى مبيعة #{sale.id}!", "success")
        
        # التوجيه للدفع الموحد إذا كان هناك رصيد متبقي
        if balance_due > 0:
            return redirect(url_for('payments.create_payment',
                                  entity_type='SALE',
                                  entity_id=sale.id,
                                  amount=balance_due,
                                  currency=sale.currency,
                                  reference=f'دفع مبيعة {sale.sale_number or sale.id}',
                                  customer_id=sale.customer_id))
        else:
            return redirect(url_for('sales_bp.sale_detail', id=sale.id))
            
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"خطأ في إنشاء المبيعة: {str(e)}", "danger")
        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))


@warehouse_bp.route("/preorders/<int:preorder_id>/fulfill", methods=["POST"], endpoint="preorder_fulfill")
@login_required
@permission_required("edit_preorder")
def preorder_fulfill(preorder_id):
    """تنفيذ الحجز القديم - سيتم إزالته لاحقاً"""
    preorder = _get_or_404(PreOrder, preorder_id)
    if preorder.status != "FULFILLED":
        try:
            preorder.status = "FULFILLED"
            sl = StockLevel.query.filter_by(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id).with_for_update(nowait=False).first()
            if not sl:
                sl = StockLevel(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id, quantity=0, reserved_quantity=0)
                db.session.add(sl)
                db.session.flush()
            qty = int(preorder.quantity or 0)
            sl.reserved_quantity = max(int(sl.reserved_quantity or 0) - qty, 0)
            available = int(sl.quantity or 0)
            if available < qty:
                db.session.rollback()
                flash("لا توجد كمية كافية لتنفيذ الحجز", "danger")
                return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))
            sl.quantity = available - qty
            db.session.commit()
            flash("تم تنفيذ الحجز وشحن الكمية", "success")
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"فشل تنفيذ الحجز: {e}", "danger")
    else:
        flash("هذا الحجز تم تنفيذه مسبقاً", "info")
    return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))


@warehouse_bp.route("/preorders/<int:preorder_id>/cancel", methods=["POST"], endpoint="preorder_cancel")
@login_required
@permission_required("delete_preorder")
def preorder_cancel(preorder_id):
    preorder = _get_or_404(PreOrder, preorder_id)
    ref = preorder.reference or str(preorder.id)
    if preorder.status in ("CANCELLED", "FULFILLED"):
        flash("لا يمكن إلغاء هذا الحجز", "warning")
        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))
    try:
        sl = StockLevel.query.filter_by(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id).with_for_update(nowait=False).first()
        if sl:
            sl.reserved_quantity = max(int(sl.reserved_quantity or 0) - int(preorder.quantity or 0), 0)
        refunded_val = getattr(PaymentStatus, "REFUNDED", "REFUNDED")
        refunded_val = refunded_val.value if hasattr(refunded_val, "value") else refunded_val
        for pay in preorder.payments:
            if hasattr(pay, "status"):
                pay.status = refunded_val
            pay.notes = f"استرداد عربون الحجز {ref}"
        preorder.status = "CANCELLED"
        db.session.commit()
        flash("تم إلغاء الحجز واسترداد العربون", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("حدث خطأ أثناء إلغاء الحجز", "danger")
    return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))


@warehouse_bp.route("/<int:warehouse_id>/pay", methods=["POST"], endpoint="pay_warehouse")
@login_required
@permission_required("manage_payments")
def pay_warehouse(warehouse_id):
    amount = request.form.get("amount", type=float)
    if not amount or amount <= 0:
        flash("قيمة غير صالحة", "danger")
        return redirect(url_for("warehouse_bp.detail", warehouse_id=warehouse_id))
    return redirect(url_for("payments.create_payment", entity_type="SUPPLIER", entity_id=warehouse_id, amount=amount))


@warehouse_bp.route("/api/add_customer", methods=["POST"], endpoint="api_add_customer")
@login_required
@permission_required("add_customer")
def api_add_customer():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم العميل مطلوب"}), 400
    cust = Customer(name=name, phone=data.get("phone"), email=data.get("email"), address=data.get("address"), whatsapp=data.get("whatsapp"), category=data.get("category", "عادي"), is_active=True)
    db.session.add(cust)
    try:
        db.session.commit()
        return jsonify({"id": cust.id, "name": cust.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/api/add_supplier", methods=["POST"], endpoint="api_add_supplier")
@login_required
@permission_required("add_supplier")
def api_add_supplier():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم المورد مطلوب"}), 400
    sup = Supplier(name=name, is_local=data.get("is_local", True), identity_number=data.get("identity_number"), contact=data.get("contact"), phone=data.get("phone"), address=data.get("address"), notes=data.get("notes"), balance=0)
    db.session.add(sup)
    try:
        db.session.commit()
        return jsonify({"id": sup.id, "name": sup.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/api/add_partner", methods=["POST"], endpoint="api_add_partner")
@login_required
@permission_required("add_partner")
def api_add_partner():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الشريك مطلوب"}), 400
    p = Partner(name=name, contact_info=data.get("contact_info"), identity_number=data.get("identity_number"), phone_number=data.get("phone_number"), address=data.get("address"), balance=0, share_percentage=data.get("share_percentage", 0))
    db.session.add(p)
    try:
        db.session.commit()
        return jsonify({"id": p.id, "name": p.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/<int:id>/shipments/create", methods=["GET"], endpoint="create_warehouse_shipment")
@login_required
@permission_required("manage_inventory")
def create_warehouse_shipment(id):
    return redirect(url_for("shipments_bp.create_shipment", destination_id=id))


@warehouse_bp.route("/<int:id>/imports", methods=["GET"], endpoint="import_runs")
@login_required
@permission_required("manage_inventory", "view_inventory", "manage_warehouses")
def list_import_runs(id):
    w = _get_or_404(Warehouse, id)
    q = ImportRun.query.filter_by(warehouse_id=w.id).order_by(ImportRun.created_at.desc())
    runs = q.all()
    if (request.args.get("format") or "").lower() == "json":
        return jsonify([
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": r.user_id,
                "filename": r.filename,
                "file_sha256": r.file_sha256,
                "dry_run": bool(r.dry_run),
                "inserted": r.inserted,
                "updated": r.updated,
                "skipped": r.skipped,
                "errors": r.errors,
                "duration_ms": r.duration_ms,
                "report_path": r.report_path,
            }
            for r in runs
        ])
    return render_template("warehouses/import_runs.html", warehouse=w, runs=runs)

@warehouse_bp.route("/imports/<int:run_id>/download", methods=["GET"], endpoint="import_run_download")
@login_required
@permission_required("manage_inventory", "view_inventory", "manage_warehouses")
def download_import_run(run_id: int):
    ir = _get_or_404(ImportRun, run_id)
    if not ir.report_path or not os.path.exists(ir.report_path):
        abort(404)
    rp = os.path.realpath(ir.report_path)
    reports_root = os.path.realpath(_report_dir()) + os.sep
    if not rp.startswith(reports_root):
        abort(403)

    dl = os.path.basename(ir.report_path) if ir.filename in (None, "", "None") else f"{os.path.splitext(ir.filename)[0]}_report.csv"
    return send_file(ir.report_path, as_attachment=True, download_name=dl, mimetype="text/csv; charset=utf-8")
