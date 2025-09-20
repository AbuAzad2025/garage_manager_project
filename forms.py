from __future__ import annotations
import os
import re
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import pytz
from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from wtforms import (
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    FieldList,
    FormField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

try:
    from wtforms.fields import DateTimeLocalField
except Exception:
    from wtforms import DateTimeField as _WTFormsDateTimeField

    class DateTimeLocalField(_WTFormsDateTimeField):
        def __init__(self, label=None, validators=None, format="%Y-%m-%dT%H:%M", **kwargs):
            kwargs = dict(kwargs or {})
            rk = dict(kwargs.get("render_kw") or {})
            rk.setdefault("type", "datetime-local")
            rk.setdefault("step", "60")
            kwargs["render_kw"] = rk
            super().__init__(label, validators or [], format=format, **kwargs)

from models import (
    User,
    Employee,
    Customer,
    Supplier,
    Partner,
    Warehouse,
    Product,
    ProductCategory,
    StockLevel,
    StockAdjustment,
    Transfer,
    PreOrder,
    Payment,
    ProductCondition,
    Account,
    AccountType,
    WarehouseType,
    PaymentEntityType,
    PaymentDirection,
    PaymentStatus,
    PaymentMethod,
    PreOrderStatus,
    Invoice,
    InvoiceSource,
    InvoiceStatus,
    normalize_barcode,
    SaleStatus,
    PaymentProgress,
    Role,
    ExpenseType,
    UtilityAccount,
    Sale,
    SaleLine,
    ShipmentItem,
    ShipmentPartner,
    GLBatch,
    GLEntry,
    SupplierSettlementStatus,
    SupplierSettlementMode,
    PartnerSettlementStatus,
    ServicePriority,
    ServiceStatus,
)

from utils import (
    luhn_check,
    is_valid_expiry_mm_yy,
    prepare_payment_form_choices,
    D,
)

from validators import Unique
from barcodes import validate_barcode

CURRENCY_CHOICES = [
    ("ILS", "شيكل"),
    ("USD", "دولار"),
    ("EUR", "يورو"),
    ("JOD", "دينار"),
]
CENT = Decimal("0.01")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

class StrippedStringField(StringField):
    """حقل StringField يزيل الفراغات تلقائيًا عند الإدخال."""
    def process_formdata(self, valuelist):
        super().process_formdata(valuelist)
        if isinstance(self.data, str):
            self.data = self.data.strip()

class MoneyField(DecimalField):
    """
    حقل مبالغ مالية:
    - يحوّل القيمة فور معالجة الإدخال إلى Decimal بخانتين (ROUND_HALF_UP).
    - يقلّل اختلافات التقريب ويمنع فروقات مجموعات الدفعات.
    """
    def process_formdata(self, valuelist):
        super().process_formdata(valuelist)
        if self.data is not None:
            try:
                self.data = Q2(self.data)
            except Exception:
                self.data = None

def Q2(x):
    try:
        return (Decimal(str(x))).quantize(CENT, ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def to_int(v):
    try:
        s = ("" if v is None else str(v)).translate(_AR_DIGITS)
        s = s.replace("٫", ".").replace("٬", "").replace(",", "").strip()
        return int(s) if s else None
    except Exception:
        return None


def to_dec(v):
    if v in (None, ""):
        return None
    s = str(v).translate(_AR_DIGITS).replace("٫", ".").replace("٬", "").replace(",", "").strip()
    try:
        return Decimal(s)
    except Exception:
        return None

class PaymentDetailsMixin:
    def _validate_card_payload(self, number, holder, expiry):
        num_raw = re.sub(r"\D+", "", number or "")
        if not (num_raw and num_raw.isdigit() and luhn_check(num_raw)):
            raise ValidationError("❌ رقم البطاقة غير صالح")
        if not (holder or "").strip():
            raise ValidationError("❌ أدخل اسم حامل البطاقة")
        if not is_valid_expiry_mm_yy((expiry or "").strip()):
            raise ValidationError("❌ تاريخ الانتهاء غير صالح (MM/YY)")
        return num_raw[-4:]

    def _validate_cheque(self, number, bank, due_date, op_date=None):
        if not (number or "").strip():
            raise ValidationError("❌ أدخل رقم الشيك")
        if not (bank or "").strip():
            raise ValidationError("❌ أدخل اسم البنك")
        if not due_date:
            raise ValidationError("❌ أدخل تاريخ الاستحقاق")
        if op_date:
            base = op_date.date() if isinstance(op_date, datetime) else op_date
            if hasattr(due_date, "toordinal") and due_date < base:
                raise ValidationError("❌ تاريخ الاستحقاق لا يمكن أن يسبق تاريخ العملية")

    def _validate_bank(self, transfer_ref):
        if not (transfer_ref or "").strip():
            raise ValidationError("❌ أدخل مرجع التحويل البنكي")

    def _validate_online(self, gateway, ref):
        if not (gateway or "").strip():
            raise ValidationError("❌ أدخل بوابة الدفع")
        if not (ref or "").strip():
            raise ValidationError("❌ أدخل مرجع العملية")

    def build_payment_details_json(self, method, **kw):
        m = (method or 'OTHER').strip().upper()
        details = {'type': m}
        if m == 'CHEQUE':
            details.update({
                'number': kw.get('check_number'),
                'bank': kw.get('check_bank'),
                'due_date': kw.get('check_due_date').isoformat() if kw.get('check_due_date') else None
            })
        elif m == 'BANK':
            details.update({'transfer_ref': kw.get('bank_transfer_ref')})
        elif m == 'CARD':
            last4 = kw.get('card_last4')
            details.update({
                'holder': kw.get('card_holder'),
                'number_masked': f"•••• •••• •••• {last4 or ''}",
                'expiry': kw.get('card_expiry'),
                'brand': kw.get('card_brand'),
            })
        elif m == 'ONLINE':
            details.update({'gateway': kw.get('online_gateway'), 'ref': kw.get('online_ref')})
        if kw.get('extra'):
            details['extra'] = kw['extra']
        return json.dumps({k: v for k, v in details.items() if v}, ensure_ascii=False)

class AjaxSelectField(SelectField):
    def __init__(
        self,
        label=None,
        validators=None,
        endpoint=None,
        get_label="name",
        allow_blank=False,
        coerce=int,
        **kwargs,
    ):
        kwargs.pop("choices", None)
        kwargs.setdefault("validate_choice", False)
        super().__init__(label, validators=validators or [], coerce=coerce, choices=[], **kwargs)
        self.endpoint = endpoint
        self.get_label = get_label
        self.allow_blank = allow_blank

    def pre_validate(self, form):
        if getattr(self, "allow_blank", False) and self.data in (None, "", "None", 0):
            return
        try:
            v = int(self.data) if self.data is not None else None
            if v is None or v <= 0:
                raise ValidationError("قيمة غير صالحة.")
        except Exception:
            raise ValidationError("قيمة غير صالحة.")

    def process_formdata(self, valuelist):
        if not valuelist:
            self.data = None
            return
        v = (valuelist[0] or "").strip().translate(_AR_DIGITS)
        if self.allow_blank:
            lv = v.lower()
            if lv in ("", "none", "null", "0"):
                self.data = None
                return
        try:
            self.data = self.coerce(v)
        except Exception:
            self.data = v

    def process_data(self, value):
        if value in (None, "", "None"):
            self.data = None
            return
        raw = getattr(value, "id", value)
        try:
            self.data = self.coerce(raw)
        except Exception:
            self.data = raw


class AjaxSelectMultipleField(SelectMultipleField):
    def __init__(self, label=None, validators=None, endpoint=None, get_label="name", coerce=int, **kwargs):
        kwargs.pop("choices", None)
        kwargs.setdefault("validate_choice", False)
        super().__init__(label, validators=validators or [], coerce=coerce, choices=[], **kwargs)
        self.endpoint = endpoint
        self.get_label = get_label

    def pre_validate(self, form):
        pass

    def process_formdata(self, valuelist):
        out = []
        for v in (valuelist or []):
            s = (v or "").strip().translate(_AR_DIGITS)
            if not s:
                continue
            lv = s.lower()
            if lv in ("", "none", "null", "0"):
                continue
            try:
                out.append(self.coerce(s))
            except Exception:
                out.append(s)
        self.data = out

    def process_data(self, value):
        if not value:
            self.data = []
            return
        seq = value if isinstance(value, (list, tuple, set)) else [value]
        out = []
        for v in seq:
            raw = getattr(v, "id", v)
            try:
                out.append(self.coerce(raw))
            except Exception:
                out.append(raw)
        self.data = out


try:
    from wtforms_sqlalchemy.fields import QuerySelectField  
except Exception:
    class QuerySelectField(SelectField):
        def __init__(self, label=None, validators=None, query_factory=None, get_label=None, allow_blank=False, blank_text="—", **kwargs):
            kwargs.pop("choices", None)
            kwargs.setdefault("validate_choice", False)
            super().__init__(label, validators=validators or [], choices=[], **kwargs)
            self.query_factory = query_factory or (lambda: [])
            self.get_label = get_label
            self.allow_blank = allow_blank
            self.blank_text = blank_text
            self._obj_map = {}
            self._refresh_choices()

        def _refresh_choices(self):
            self._obj_map = {}
            choices = []
            if self.allow_blank:
                choices.append(("", self.blank_text))
            for obj in (self.query_factory() or []):
                oid = getattr(obj, "id", obj)
                label = self.get_label(obj) if callable(self.get_label) else (getattr(obj, self.get_label, None) if self.get_label else None)
                if label is None:
                    label = getattr(obj, "name", str(obj))
                sid = str(oid)
                choices.append((sid, str(label)))
                self._obj_map[sid] = obj
            self.choices = choices

        def process_formdata(self, valuelist):
            self._refresh_choices()
            if not valuelist:
                self.data = None
                return
            v = (valuelist[0] or "").strip()
            lv = v.lower()
            if self.allow_blank and lv in ("", "none", "null"):
                self.data = None
                return
            self.data = self._obj_map.get(v)

        def process_data(self, value):
            self._refresh_choices()
            if value in (None, "", "None"):
                self.data = None
                return
            self.data = value if hasattr(value, "id") else self._obj_map.get(str(value))

        def pre_validate(self, form):
            if getattr(self, "allow_blank", False) and self.data in (None, "", "None", 0):
                return
            if self.data is None:
                raise ValidationError("قيمة غير صالحة.")
            if hasattr(self.data, "id"):
                sid = str(getattr(self.data, "id"))
                if sid not in self._obj_map:
                    raise ValidationError("قيمة غير صالحة.")
            else:
                if str(self.data) not in self._obj_map:
                    raise ValidationError("قيمة غير صالحة.")

def normalize_phone(raw):
    if not raw:
        return ""
    s = str(raw).translate(_AR_DIGITS)
    return re.sub(r"\D+", "", s)[:20]


def normalize_email(raw):
    return (raw or "").strip().lower()


def unique_email_validator(model, field_name="email", allow_null=False, case_insensitive=True):
    def _validator(form, field):
        val = (field.data or "").strip()
        if not val:
            if allow_null:
                return
            raise ValidationError("هذا الحقل مطلوب")
        col = getattr(model, field_name)
        qy = model.query
        qy = qy.filter(func.lower(col) == val.lower()) if case_insensitive else qy.filter(col == val)
        current_id = None
        for attr in ("id", "obj_id"):
            f = getattr(form, attr, None)
            if f and getattr(f, "data", None):
                try:
                    current_id = int(f.data)
                    break
                except Exception:
                    pass
        if current_id:
            qy = qy.filter(model.id != current_id)
        if qy.first():
            raise ValidationError("هذا البريد مستخدم بالفعل.")
    return _validator


def only_digits(s):
    return re.sub(r"\D", "", s or "")


def enum_choices(enum_cls, labels_map=None, include_blank=True, blank="— اختر —"):
    labels_map = labels_map or {}
    data = [(m.value, labels_map.get(m.value, m.value)) for m in enum_cls]
    return ([("", blank)] + data) if include_blank else data

PRIORITY_LABELS = {
    ServicePriority.LOW.value: "منخفضة",
    ServicePriority.MEDIUM.value: "متوسطة",
    ServicePriority.HIGH.value: "مرتفعة",
    ServicePriority.URGENT.value: "عاجلة",
}

STATUS_LABELS_AR = {
    ServiceStatus.PENDING.value: "قيد الاستلام",
    ServiceStatus.DIAGNOSIS.value: "تشخيص",
    ServiceStatus.IN_PROGRESS.value: "قيد التنفيذ",
    ServiceStatus.COMPLETED.value: "مكتملة",
    ServiceStatus.CANCELLED.value: "ملغاة",
    ServiceStatus.ON_HOLD.value: "مؤجلة",
}

SERVICE_PRIORITY_CHOICES = enum_choices(
    ServicePriority,
    labels_map=PRIORITY_LABELS,
    include_blank=True,
    blank="— اختر —",
)

SERVICE_STATUS_CHOICES = enum_choices(
    ServiceStatus,
    labels_map=STATUS_LABELS_AR,
    include_blank=True,
    blank="— اختر —",
)

class UnifiedDateTimeField(DateTimeField):
    def __init__(self, label=None, validators=None, format="%Y-%m-%d %H:%M", formats=None, output_format=None, **kwargs):
        if formats is not None:
            fmt_list = list(formats) if isinstance(formats, (list, tuple)) else [formats]
        elif isinstance(format, (list, tuple)):
            fmt_list = list(format)
            format = fmt_list[0] if fmt_list else "%Y-%m-%d %H:%M"
        else:
            fmt_list = [format or "%Y-%m-%d %H:%M"]
        super().__init__(label, validators, format=format, **kwargs)
        self.formats = fmt_list
        self.output_format = output_format or format

    def _value(self):
        if self.raw_data:
            return " ".join([v for v in self.raw_data if v])
        if isinstance(self.data, datetime):
            try:
                return self.data.strftime(self.output_format)
            except Exception:
                return self.data.strftime(self.format)
        return ""

    def process_formdata(self, valuelist):
        if not valuelist:
            self.data = None; return
        s = " ".join(v for v in valuelist if v).replace("T"," ").strip()
        for fmt in self.formats:
            try:
                self.data = datetime.strptime(s, fmt); return
            except Exception:
                pass
        if s.startswith("ts:"):
            try:
                self.data = datetime.fromtimestamp(float(s[3:])); return
            except Exception:
                pass
        self.data = None
        raise ValidationError(self.gettext("صيغة التاريخ/الوقت غير صحيحة"))
class UnifiedDateField(DateField):
    def __init__(self, label=None, validators=None, format="%Y-%m-%d", formats=None, output_format=None, **kwargs):
        if formats is not None:
            fmt_list = list(formats) if isinstance(formats, (list, tuple)) else [formats]
        elif isinstance(format, (list, tuple)):
            fmt_list = list(format)
            format = fmt_list[0] if fmt_list else "%Y-%m-%d"
        else:
            fmt_list = [format or "%Y-%m-%d"]
        super().__init__(label, validators, format=format, **kwargs)
        self.formats = fmt_list
        self.output_format = output_format or format

    def _value(self):
        if self.raw_data:
            return " ".join([v for v in self.raw_data if v])
        if self.data:
            try:
                return self.data.strftime(self.output_format)
            except Exception:
                return self.data.strftime(self.format)
        return ""

    def process_formdata(self, valuelist):
        if not valuelist:
            self.data = None
            return
        s = " ".join(v for v in valuelist if v).replace("T", " ").strip()
        for fmt in self.formats:
            try:
                self.data = datetime.strptime(s, fmt).date()
                return
            except Exception:
                pass
        if s.startswith("ts:"):
            try:
                self.data = datetime.fromtimestamp(float(s[3:])).date()
                return
            except Exception:
                pass
        self.data = None
        raise ValidationError(self.gettext("صيغة التاريخ غير صحيحة"))
    
class ProductImportForm(FlaskForm):
    csv_file = FileField("CSV", validators=[DataRequired(), FileAllowed(["csv"], "CSV فقط")])
    submit = SubmitField("استيراد المنتجات")


class TransferImportForm(FlaskForm):
    csv_file = FileField("CSV", validators=[DataRequired(), FileAllowed(["csv"], "CSV فقط")])
    submit = SubmitField("استيراد التحويلات")


class RestoreForm(FlaskForm):
    db_file = FileField("نسخة .db", validators=[DataRequired(message="اختر ملف .db"), FileAllowed(["db"], "ملف db فقط")])
    submit = SubmitField("استعادة النسخة")

class TransferForm(FlaskForm):
    id = HiddenField()
    reference = StringField("المرجع", validators=[Optional(), Length(max=50)])
    product_id = AjaxSelectField("الصنف", endpoint="api.search_products", get_label="name", validators=[DataRequired()])
    source_id = AjaxSelectField("المخزن المصدر", endpoint="api.search_warehouses", get_label="name", validators=[DataRequired()])
    destination_id = AjaxSelectField("المخزن الوجهة", endpoint="api.search_warehouses", get_label="name", validators=[DataRequired()])
    quantity = IntegerField("الكمية", validators=[DataRequired(), NumberRange(min=1)])
    direction = SelectField("الاتجاه", choices=[("IN", "إدخال"), ("OUT", "إخراج"), ("ADJUSTMENT", "تسوية")], validators=[DataRequired()], coerce=str)
    transfer_date = UnifiedDateTimeField("تاريخ التحويل", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"], validators=[Optional()])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("حفظ")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        src = to_int(self.source_id.data)
        dst = to_int(self.destination_id.data)
        if src and dst and src == dst:
            self.destination_id.errors.append("يجب اختيار مخزن مختلف عن المصدر.")
            return False
        pid = to_int(self.product_id.data)
        qty = to_int(self.quantity.data) or 0
        if pid and src and qty:
            try:
                from models import StockLevel
                sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=src).first()
                avail = (sl.quantity if sl else 0) - getattr(sl, "reserved_quantity", 0)
                if qty > max(avail, 0):
                    self.quantity.errors.append("الكمية غير كافية في المخزن المصدر.")
                    return False
            except Exception as e:
                current_app.logger.warning("Stock check failed (pid=%s, wid=%s): %s", pid, src, e)
        return True

    def apply_to(self, t):
        t.reference = (self.reference.data or "").strip() or t.reference
        t.product_id = to_int(self.product_id.data)
        t.source_id = to_int(self.source_id.data)
        t.destination_id = to_int(self.destination_id.data)
        t.quantity = to_int(self.quantity.data) or 1
        t.direction = (self.direction.data or "").upper()
        t.transfer_date = self.transfer_date.data or datetime.utcnow()
        t.notes = (self.notes.data or "").strip() or None
        return t


class SettlementRangeForm(FlaskForm):
    start = DateField("من", validators=[Optional()])
    end = DateField("إلى", validators=[Optional()])
    submit = SubmitField("عرض")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start.data and self.end.data and self.start.data > self.end.data:
            self.end.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        return True

class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3, 50)])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')
    submit = SubmitField('تسجيل الدخول')


class RegistrationForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3, 50)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    role = QuerySelectField('الدور', query_factory=lambda: Role.query.order_by(Role.name).all(), get_label='name', allow_blank=False)
    submit = SubmitField('تسجيل')

    def validate_username(self, field):
        u = (field.data or '').strip()
        if User.query.filter(User.username == u).first():
            raise ValidationError("اسم المستخدم مستخدم بالفعل.")

    def validate_email(self, field):
        e = (field.data or '').strip().lower()
        if User.query.filter(User.email == e).first():
            raise ValidationError("البريد الإلكتروني مستخدم بالفعل.")
        field.data = e


class PasswordResetForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('تحديث')


class PasswordResetRequestForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField('إرسال رابط إعادة')

    def validate_email(self, field):
        field.data = (field.data or '').strip().lower()

class UserForm(FlaskForm):
    username = StrippedStringField('اسم المستخدم', validators=[DataRequired(), Length(min=3, max=50)])
    email = StrippedStringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    role_id = SelectField('الدور', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('نشِط')
    password = PasswordField('كلمة المرور الجديدة', validators=[Optional(), Length(min=6, max=128)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[Optional(), EqualTo('password', message='يجب أن تتطابق كلمتا المرور')])
    last_login = DateTimeField('آخر تسجيل دخول', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'readonly': True, 'disabled': True})
    last_seen = DateTimeField('آخر ظهور', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'readonly': True, 'disabled': True})
    last_login_ip = StringField('آخر IP', render_kw={'readonly': True, 'disabled': True})
    login_count = StringField('عدد تسجيلات الدخول', render_kw={'readonly': True, 'disabled': True})
    submit = SubmitField('حفظ')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role_id.choices = [(r.id, r.name) for r in Role.query.order_by(Role.name).all()]
        try:
            from flask import request
            self._editing_user_id = request.view_args.get('user_id')
        except Exception:
            self._editing_user_id = None
        if hasattr(self, "_obj") and self._obj:
            self.last_login.data = getattr(self._obj, "last_login", None)
            self.last_seen.data = getattr(self._obj, "last_seen", None)
            self.last_login_ip.data = getattr(self._obj, "last_login_ip", "") or ""
            self.login_count.data = str(getattr(self._obj, "login_count", "") or "")

    def validate_username(self, field):
        name = (field.data or '').strip()
        qry = User.query.filter(User.username == name)
        if getattr(self, "_editing_user_id", None):
            qry = qry.filter(User.id != self._editing_user_id)
        if qry.first():
            raise ValidationError("اسم المستخدم مستخدم بالفعل.")

    def validate_email(self, field):
        email_l = (field.data or '').strip().lower()
        qry = User.query.filter(User.email == email_l)
        if getattr(self, "_editing_user_id", None):
            qry = qry.filter(User.id != self._editing_user_id)
        if qry.first():
            raise ValidationError("البريد الإلكتروني مستخدم بالفعل.")
        field.data = email_l

    def apply_to(self, user: User) -> User:
        user.username = (self.username.data or '').strip()
        user.email = (self.email.data or '').strip().lower()
        user.role_id = self.role_id.data
        user.is_active = bool(self.is_active.data)
        if self.password.data:
            user.set_password(self.password.data)
        return user

class RoleForm(FlaskForm):
    id = HiddenField()
    name = StringField('اسم الدور', validators=[DataRequired(), Length(max=50)])
    description = StringField('الوصف', validators=[Optional(), Length(max=200)])
    is_default = BooleanField('افتراضي')
    permissions = SelectMultipleField('الصلاحيات', choices=[], coerce=str)
    submit = SubmitField('حفظ')

    def validate_name(self, field):
        s = (field.data or '').strip()
        field.data = s
        qry = Role.query.filter(Role.name == s)
        if self.id.data and str(self.id.data).strip().isdigit():
            qry = qry.filter(Role.id != int(self.id.data))
        if qry.first():
            raise ValidationError("الاسم مستخدم بالفعل.")


class PermissionForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    name_ar = StringField('الاسم بالعربية', validators=[Optional(), Length(max=120)])
    code = StringField('الكود', validators=[Optional(), Length(max=100)])
    module = StringField('الوحدة', validators=[Optional(), Length(max=50)])
    aliases = TextAreaField('أسماء بديلة (مفصولة بفواصل)', validators=[Optional(), Length(max=500)])
    is_protected = BooleanField('محمي')
    description = StringField('الوصف', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ')

    def validate_name(self, field):
        field.data = (field.data or '').strip()

    def validate_code(self, field):
        s = (field.data or '').strip().lower()
        if s:
            s = re.sub(r"[\s\-]+", "_", s)
            s = re.sub(r"[^a-z0-9_]+", "", s)
            s = re.sub(r"_+", "_", s).strip("_")
        field.data = s

class CustomerForm(FlaskForm):
    id = HiddenField()
    name = StrippedStringField('اسم العميل', validators=[DataRequired(message="هذا الحقل مطلوب"), Length(max=100)])
    phone = StrippedStringField('الهاتف', validators=[DataRequired(message="الهاتف مطلوب"), Length(max=20, message="أقصى طول 20 رقم"), Unique(Customer, "phone", message="رقم الهاتف مستخدم مسبقًا", case_insensitive=False, normalizer=normalize_phone)])
    email = StrippedStringField('البريد الإلكتروني', validators=[DataRequired(message="هذا الحقل مطلوب"), Email(message="صيغة البريد غير صحيحة"), Length(max=120), Unique(Customer, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StrippedStringField('العنوان', validators=[Optional(), Length(max=200, message="أقصى طول 200 حرف")])
    whatsapp = StrippedStringField('واتساب', validators=[Optional(), Length(max=20, message="أقصى طول 20 رقم")])
    category = SelectField('تصنيف العميل', choices=[('عادي','عادي'),('ذهبي','ذهبي'),('بلاتيني','بلاتيني')], default='عادي')
    credit_limit = DecimalField('حد الائتمان', places=2, validators=[Optional(), NumberRange(min=0, message="يجب أن يكون ≥ 0")])
    discount_rate = DecimalField('معدل الخصم (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100, message="بين 0 و100")])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired(message='العملة مطلوبة')])
    is_active = BooleanField('نشط', default=True)
    is_online = BooleanField('عميل أونلاين', default=False)
    is_archived = BooleanField('مؤرشف', default=False)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500, message="أقصى طول 500 حرف")])
    password = PasswordField('كلمة المرور', validators=[Optional(), Length(min=6, message="الحد الأدنى 6 أحرف")])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[Optional(), EqualTo('password', message='يجب أن تتطابق كلمتا المرور')])
    submit = SubmitField('حفظ العميل')

    def validate_password(self, field):
        is_create = not (self.id.data and str(self.id.data).strip().isdigit())
        if is_create and not (field.data and str(field.data).strip()):
            raise ValidationError("كلمة المرور مطلوبة عند إنشاء عميل جديد")

    def validate_phone(self, field):
        field.data = normalize_phone(field.data)
        if not field.data:
            raise ValidationError("الهاتف مطلوب")

    def validate_email(self, field):
        field.data = normalize_email(field.data)

    def validate_whatsapp(self, field):
        val = normalize_phone(field.data)
        field.data = val or normalize_phone(self.phone.data)

    def validate_category(self, field):
        if (field.data or '') not in {'عادي','ذهبي','بلاتيني'}:
            raise ValidationError('قيمة غير صالحة لتصنيف العميل')

    def apply_to(self, customer: Customer) -> Customer:
        customer.name = (self.name.data or "").strip()
        customer.phone = normalize_phone(self.phone.data)
        customer.whatsapp = normalize_phone(self.whatsapp.data or self.phone.data)
        customer.email = normalize_email(self.email.data)
        customer.address = (self.address.data or "").strip() or None
        customer.category = self.category.data
        customer.currency = (self.currency.data or 'ILS').upper()
        customer.is_active = bool(self.is_active.data)
        customer.is_online = bool(self.is_online.data)
        customer.is_archived = bool(self.is_archived.data)
        customer.notes = (self.notes.data or "").strip() or None
        customer.credit_limit = self.credit_limit.data or Decimal("0")
        customer.discount_rate = self.discount_rate.data or Decimal("0")
        if self.password.data:
            customer.set_password(self.password.data)
        return customer

class CustomerImportForm(FlaskForm):
    csv_file = FileField('CSV', validators=[DataRequired(), FileAllowed(['csv'], 'CSV فقط')])
    submit = SubmitField('استيراد')

class ProductSupplierLoanForm(FlaskForm):
    id = HiddenField()
    product_id = AjaxSelectField("المنتج", endpoint="api.search_products", get_label="name", coerce=int, validators=[DataRequired()])
    supplier_id = AjaxSelectField("المورد", endpoint="api.search_suppliers", get_label="name", coerce=int, validators=[DataRequired()])
    loan_value = MoneyField("قيمة القرض", validators=[Optional(), NumberRange(min=0)])
    deferred_price = MoneyField("السعر المؤجل", validators=[Optional(), NumberRange(min=0)])
    is_settled = BooleanField("تمت التسوية؟")
    partner_share_quantity = IntegerField("كمية حصة الشريك", validators=[Optional(), NumberRange(min=0)])
    partner_share_value = MoneyField("قيمة حصة الشريك", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("حفظ")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok: return False
        if self.is_settled.data and (self.deferred_price.data is None or str(self.deferred_price.data).strip() in ("", "0", "0.0")):
            self.deferred_price.errors.append("❌ عند تحديد التسوية يجب إدخال السعر المؤجل.")
            ok = False
        return ok

class SupplierForm(FlaskForm):
    id = HiddenField(filters=[lambda v: int(v) if v and str(v).strip().isdigit() else None])
    name = StrippedStringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    is_local = BooleanField('محلي؟')
    identity_number = StrippedStringField('رقم الهوية/الملف الضريبي', validators=[Optional(), Length(max=100)])
    contact = StrippedStringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    phone = StrippedStringField('رقم الجوال', validators=[Optional(), Length(max=20), Unique(Supplier, "phone", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StrippedStringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120), Unique(Supplier, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StrippedStringField('العنوان', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    balance = MoneyField('الرصيد الافتتاحي', validators=[Optional(), NumberRange(min=0)])
    payment_terms = StrippedStringField('شروط الدفع', validators=[Optional(), Length(max=50)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit = SubmitField('حفظ المورد')

    def validate_phone(self, field):
        if field.data:
            field.data = normalize_phone(field.data)

    def validate_email(self, field):
        if field.data:
            field.data = normalize_email(field.data)

    def apply_to(self, supplier: Supplier) -> Supplier:
        supplier.name = (self.name.data or '').strip()
        supplier.is_local = bool(self.is_local.data)
        supplier.identity_number = (self.identity_number.data or '').strip() or None
        supplier.contact = (self.contact.data or '').strip() or None
        supplier.phone = normalize_phone(self.phone.data)
        supplier.email = normalize_email(self.email.data) or None
        supplier.address = (self.address.data or '').strip() or None
        supplier.notes = (self.notes.data or '').strip() or None
        supplier.balance = self.balance.data or Decimal('0')
        supplier.payment_terms = (self.payment_terms.data or '').strip() or None
        supplier.currency = (self.currency.data or 'ILS').upper()
        return supplier

class PartnerForm(FlaskForm):
    id = HiddenField(filters=[lambda v: int(v) if v and str(v).strip().isdigit() else None])
    name = StrippedStringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    contact_info = StrippedStringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    identity_number = StrippedStringField('رقم الهوية', validators=[Optional(), Length(max=100)])
    phone_number = StrippedStringField('رقم الجوال', validators=[Optional(), Length(max=20), Unique(Partner, "phone_number", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StrippedStringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120), Unique(Partner, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StrippedStringField('العنوان', validators=[Optional(), Length(max=200)])
    balance = MoneyField('الرصيد', validators=[Optional(), NumberRange(min=0)])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ الشريك')

    def validate_phone_number(self, field):
        if field.data:
            field.data = normalize_phone(field.data)

    def validate_email(self, field):
        if field.data:
            field.data = normalize_email(field.data)

    def apply_to(self, partner: Partner) -> Partner:
        partner.name = (self.name.data or '').strip()
        partner.contact_info = (self.contact_info.data or '').strip() or None
        partner.identity_number = (self.identity_number.data or '').strip() or None
        partner.phone_number = normalize_phone(self.phone_number.data)
        partner.email = normalize_email(self.email.data) or None
        partner.address = (self.address.data or '').strip() or None
        partner.balance = self.balance.data or Decimal('0')
        partner.share_percentage = self.share_percentage.data or Decimal('0')
        partner.currency = (self.currency.data or 'ILS').upper()
        partner.notes = (self.notes.data or '').strip() or None
        return partner

class QuickSupplierForm(FlaskForm):
    name = StrippedStringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    phone = StrippedStringField('رقم الجوال', validators=[Optional(), Length(max=20), Unique(Supplier, "phone", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StrippedStringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120), Unique(Supplier, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    submit = SubmitField('إضافة سريعة')

    def validate_phone(self, field):
        if field.data:
            field.data = normalize_phone(field.data)

    def validate_email(self, field):
        if field.data:
            field.data = normalize_email(field.data)


class QuickPartnerForm(FlaskForm):
    name = StrippedStringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    phone = StrippedStringField('رقم الجوال', validators=[Optional(), Length(max=20), Unique(Partner, "phone_number", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StrippedStringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120), Unique(Partner, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    submit = SubmitField('إضافة سريعة')

    def validate_phone(self, field):
        if field.data:
            field.data = normalize_phone(field.data)

    def validate_email(self, field):
        if field.data:
            field.data = normalize_email(field.data)

class BaseServicePartForm(FlaskForm):
    part_id = AjaxSelectField('القطعة', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('الخصم (%)', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة (%)', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StringField('ملاحظة', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ')

class PaymentAllocationForm(FlaskForm):
    class Meta:
        csrf = False

    payment_id = IntegerField(validators=[Optional()])
    invoice_ids = AjaxSelectMultipleField(endpoint='api.search_invoices', get_label='invoice_number', validators=[Optional()])
    service_ids = AjaxSelectMultipleField(endpoint='api.search_services', get_label='service_number', validators=[Optional()])
    expense_ids = AjaxSelectMultipleField(endpoint='api.search_expenses', get_label='id', validators=[Optional()])
    shipment_ids = AjaxSelectMultipleField(endpoint='api.search_shipments', get_label='shipment_number', validators=[Optional()])
    allocation_amounts = FieldList(MoneyField(validators=[Optional(), NumberRange(min=0.01)]), min_entries=1)
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('توزيع')

    def validate(self, **kwargs):
        ok = super().validate(**kwargs)
        invoices = self.invoice_ids.data or []
        services = self.service_ids.data or []
        expenses = self.expense_ids.data or []
        shipments = self.shipment_ids.data or []
        targets = len(invoices) + len(services) + len(expenses) + len(shipments)
        amounts = [fld.data for fld in self.allocation_amounts if fld.data is not None]
        if targets == 0:
            self.invoice_ids.errors.append('❌ اختر عنصرًا واحدًا على الأقل للتسوية.')
            ok = False
        if not amounts or any((a or 0) <= 0 for a in amounts):
            self.allocation_amounts.errors.append('❌ كل مبالغ التوزيع يجب أن تكون > 0.')
            ok = False
        if targets and len(amounts) != targets:
            self.allocation_amounts.errors.append('❌ عدد مبالغ التوزيع يجب أن يساوي عدد العناصر المحددة.')
            ok = False
        return ok

METHOD_LABELS_AR = {
    'CASH':'نقدي','CARD':'بطاقة','BANK':'تحويل','CHEQUE':'شيك','ONLINE':'إلكتروني'
}

class SupplierSettlementLineForm(FlaskForm):
    id = HiddenField()
    settlement_id = HiddenField()
    source_type = StringField("نوع المصدر", validators=[Optional(), Length(max=30)])
    source_id = IntegerField("المعرف", validators=[Optional()])
    description = StringField("الوصف", validators=[Optional(), Length(max=255)])
    product_id = AjaxSelectField("المنتج", coerce=int, allow_blank=True)
    quantity = DecimalField("الكمية", places=3, validators=[Optional(), NumberRange(min=0)])
    unit_price = MoneyField("سعر الوحدة", validators=[Optional(), NumberRange(min=0)])
    gross_amount = MoneyField("الإجمالي", validators=[Optional(), NumberRange(min=0)])
    needs_pricing = BooleanField("يحتاج تسعير")
    cost_source = StringField("مصدر الكلفة", validators=[Optional(), Length(max=20)])


class SupplierSettlementForm(FlaskForm):
    id = HiddenField()
    code = StringField("الرمز", validators=[Optional(), Length(max=40)])
    supplier_id = AjaxSelectField("المورد", endpoint="api.search_suppliers", get_label="name", validators=[DataRequired()])
    from_date = UnifiedDateTimeField("من تاريخ", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%M","%Y-%m-%dT%H:%M"], default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    to_date = UnifiedDateTimeField("إلى تاريخ", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%M","%Y-%m-%dT%H:%M"], default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    currency = SelectField("العملة", choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    status = SelectField("الحالة", choices=[(s.value, s.value) for s in SupplierSettlementStatus], default=SupplierSettlementStatus.DRAFT.value, validators=[DataRequired()])
    mode = SelectField("الوضع", choices=[(m.value, m.value) for m in SupplierSettlementMode], default=SupplierSettlementMode.ON_RECEIPT.value, validators=[DataRequired()])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=500)])
    total_gross = MoneyField("الإجمالي", validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True, "tabindex": "-1"})
    total_due = MoneyField("المستحق", validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True, "tabindex": "-1"})
    lines = FieldList(FormField(SupplierSettlementLineForm), min_entries=1)
    submit = SubmitField("حفظ")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok:
            return False
        if self.from_date.data and self.to_date.data and self.from_date.data > self.to_date.data:
            self.to_date.errors.append("❌ تاريخ النهاية يجب أن يكون بعد البداية.")
            ok = False
        nonempty = False
        for row in self.lines:
            f = row.form
            try:
                q = Decimal(str(f.quantity.data or "0"))
                p = Decimal(str(f.unit_price.data or "0"))
                g = Decimal(str(f.gross_amount.data or "0"))
                if q > 0 or p > 0 or g > 0:
                    nonempty = True
                    break
            except Exception:
                continue
        if not nonempty:
            self.lines.errors.append("❌ أضف بندًا واحدًا على الأقل بقيمة.")
            ok = False
        if self.status.data == SupplierSettlementStatus.CONFIRMED.value:
            for row in self.lines:
                if row.form.needs_pricing.data:
                    row.form.needs_pricing.errors.append("❌ لا يمكن تأكيد التسوية وبند يحتاج تسعير.")
                    ok = False
        return ok

    def apply_to(self, ss):
        ss.code = (self.code.data or "").strip() or ss.code
        ss.supplier_id = int(self.supplier_id.data) if self.supplier_id.data else None
        ss.from_date = self.from_date.data
        ss.to_date = self.to_date.data
        ss.currency = (self.currency.data or "ILS").upper()
        ss.status = (self.status.data or SupplierSettlementStatus.DRAFT.value)
        ss.mode = (self.mode.data or SupplierSettlementMode.ON_RECEIPT.value)
        ss.notes = (self.notes.data or "").strip() or None
        ss.total_gross = self.total_gross.data or Decimal("0")
        ss.total_due = self.total_due.data or Decimal("0")
        return ss


class SupplierLoanSettlementForm(FlaskForm):
    id = HiddenField()
    loan_id = AjaxSelectField("قرض المورّد", endpoint="api.search_product_supplier_loans", get_label="label", coerce=int, allow_blank=True)
    supplier_id = AjaxSelectField("المورّد", endpoint="api.search_suppliers", get_label="name", coerce=int, allow_blank=True)
    settled_price = MoneyField("السعر المُسوّى", validators=[DataRequired(), NumberRange(min=0)])
    settlement_date = UnifiedDateTimeField("تاريخ التسوية", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%M","%Y-%m-%dT%H:%M"], default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("حفظ")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok:
            return False
        if not self.loan_id.data and not self.supplier_id.data:
            msg = "❌ اختر قرضًا أو مورّدًا واحدًا على الأقل."
            self.loan_id.errors.append(msg)
            self.supplier_id.errors.append(msg)
            ok = False
        try:
            if self.loan_id.data and self.supplier_id.data:
                loan = ProductSupplierLoan.query.get(int(self.loan_id.data))
                if loan and loan.supplier_id and int(self.supplier_id.data) != int(loan.supplier_id):
                    self.supplier_id.errors.append("❌ المورّد لا يطابق قرض المورّد المحدّد.")
                    ok = False
        except Exception:
            pass
        return ok

    def apply_to(self, sls):
        sls.loan_id = int(self.loan_id.data) if self.loan_id.data else None
        sls.supplier_id = int(self.supplier_id.data) if self.supplier_id.data else None
        sls.settled_price = self.settled_price.data or Decimal("0")
        sls.settlement_date = self.settlement_date.data
        sls.notes = (self.notes.data or "").strip() or None
        return sls


class RefundForm(FlaskForm):
    original_payment_id = IntegerField(validators=[DataRequired()])
    refund_amount = MoneyField(validators=[DataRequired(), NumberRange(min=0.01)])
    reason = TextAreaField(validators=[Optional(), Length(max=500)])
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('إرجاع')


class PartnerSettlementLineForm(FlaskForm):
    id = HiddenField()
    settlement_id = HiddenField()
    source_type = StringField("نوع المصدر", validators=[Optional(), Length(max=30)])
    source_id = IntegerField("المعرف", validators=[Optional()])
    description = StringField("الوصف", validators=[Optional(), Length(max=255)])
    product_id = AjaxSelectField("المنتج", coerce=int, allow_blank=True)
    warehouse_id = AjaxSelectField("المستودع", coerce=int, allow_blank=True)
    quantity = DecimalField("الكمية", places=3, validators=[Optional(), NumberRange(min=0)])
    unit_price = MoneyField("سعر الوحدة", validators=[Optional(), NumberRange(min=0)])
    gross_amount = MoneyField("الإجمالي", validators=[Optional(), NumberRange(min=0)])
    share_percent = DecimalField("نسبة الشريك %", places=3, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount = MoneyField("حصة الشريك", validators=[Optional(), NumberRange(min=0)])


class PartnerSettlementForm(FlaskForm):
    partner_id = AjaxSelectField("الشريك", endpoint="api.search_partners", get_label="name", validators=[DataRequired()])
    from_date = UnifiedDateTimeField("من تاريخ", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%م","%Y-%m-%dT%H:%M"], default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    to_date = UnifiedDateTimeField("إلى تاريخ", format="%Y-%m-%d %H:%M", formats=["%Y-%m-%d %H:%م","%Y-%m-%dT%H:%M"], default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    currency = SelectField("العملة", choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    status = SelectField("الحالة", choices=[(s.value, s.value) for s in PartnerSettlementStatus], default=PartnerSettlementStatus.DRAFT.value, validators=[DataRequired()])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=500)])
    lines = FieldList(FormField(PartnerSettlementLineForm), min_entries=1)
    submit = SubmitField("حفظ التسوية")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok:
            return False
        if self.from_date.data and self.to_date.data and self.from_date.data > self.to_date.data:
            self.to_date.errors.append("❌ تاريخ النهاية يجب أن يكون بعد البداية.")
            ok = False
        total_share = Decimal("0.00")
        nonempty = False
        for entry in self.lines:
            fm = entry.form
            try:
                qty = Decimal(str(fm.quantity.data or "0"))
                price = Decimal(str(fm.unit_price.data or "0"))
                share = Decimal(str(fm.share_amount.data or "0"))
                if qty > 0 or price > 0 or share > 0:
                    nonempty = True
                total_share += share
            except Exception:
                pass
        if not nonempty:
            self.lines.errors.append("❌ أضف عنصر واحد على الأقل للتسوية.")
            ok = False
        if total_share < 0:
            self.lines.errors.append("❌ مجموع حصص الشركاء غير صحيح.")
            ok = False
        return ok

    def apply_to(self, ps):
        ps.partner_id = int(self.partner_id.data) if self.partner_id.data else None
        ps.from_date = self.from_date.data
        ps.to_date = self.to_date.data
        ps.currency = (self.currency.data or "ILS").upper()
        ps.status = (self.status.data or PartnerSettlementStatus.DRAFT.value)
        ps.notes = (self.notes.data or "").strip() or None
        return ps
    
class BulkPaymentForm(FlaskForm):
    payer_type = SelectField(choices=[('customer','عميل'),('partner','شريك'),('supplier','مورد')], validators=[DataRequired()], coerce=str)
    payer_search = StringField(validators=[Optional(), Length(max=100)])
    payer_id = HiddenField(validators=[DataRequired()])
    total_amount = MoneyField(validators=[DataRequired(), NumberRange(min=0.01)])
    allocations = FieldList(FormField(PaymentAllocationForm), min_entries=1)
    method = SelectField(choices=enum_choices(PaymentMethod, labels_map=METHOD_LABELS_AR, include_blank=True, blank='— اختر الطريقة —'), validators=[DataRequired()], coerce=str, default='', validate_choice=False)
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()], coerce=str)
    submit = SubmitField('حفظ الدفعة')

    def validate(self, **kwargs):
        ok = super().validate(**kwargs)
        try:
            total = Decimal(str(self.total_amount.data or "0"))
        except Exception:
            total = Decimal("0.00")
        sum_alloc = Decimal("0.00")
        nonempty = False
        for entry in self.allocations:
            fm = entry.form
            for fld in getattr(fm, 'allocation_amounts', []):
                val = fld.data or 0
                try:
                    v = Decimal(str(fld.data or "0"))
                except Exception:
                    v = Decimal("0")    
                if v > 0:
                    nonempty = True
                    sum_alloc += v
            if (self.payer_type.data or '').lower() == 'supplier':
                if getattr(fm, 'service_ids', None) and (fm.service_ids.data or []):
                    fm.service_ids.errors.append('❌ لا يمكن تسوية خدمات العميل ضمن تسوية مورد.')
                    ok = False
        if not nonempty:
            self.allocations.errors.append('❌ أضف عنصر توزيع واحدًا على الأقل.')
            ok = False
        if Q2(sum_alloc) != Q2(total):
            self.total_amount.errors.append('❌ مجموع مبالغ التوزيع يجب أن يساوي المبلغ الكلي.')
            ok = False
        pid = (self.payer_id.data or '').strip()
        if not pid.isdigit() or int(pid) <= 0:
            self.payer_id.errors.append('❌ اختر الدافع بشكل صحيح.')
            ok = False
        return ok

class LoanSettlementPaymentForm(FlaskForm):
    settlement_id = AjaxSelectField(endpoint='api.search_loan_settlements', get_label='id', validators=[DataRequired()])
    amount = MoneyField(validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField(
        choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod],
        validators=[DataRequired()],
        coerce=str,
        default='',
    )
    reference = StringField(validators=[Optional(), Length(max=100)])
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('دفع')


class SplitEntryForm(PaymentDetailsMixin, FlaskForm):
    class Meta: csrf=False
    method=SelectField(validators=[Optional()],default='',coerce=str,validate_choice=False)
    amount=MoneyField(validators=[Optional()],default=Decimal('0.00'))
    check_number=StringField(validators=[Optional(),Length(max=100)])
    check_bank=StringField(validators=[Optional(),Length(max=100)])
    check_due_date=DateField(format='%Y-%m-%d',validators=[Optional()])
    card_number=StringField(validators=[Optional(),Length(max=100)])
    card_holder=StringField(validators=[Optional(),Length(max=100)])
    card_expiry=StringField(validators=[Optional(),Length(max=10)])
    bank_transfer_ref=StringField(validators=[Optional(),Length(max=100)])
    online_gateway=StringField(validators=[Optional(),Length(max=100)])
    online_ref=StringField(validators=[Optional(),Length(max=100)])
    def validate(self,**kwargs):
        base_ok=super().validate(**kwargs)
        m=(self.method.data or '').strip().upper()
        amt_val=self.amount.data if self.amount.data is not None else Decimal('0.00')
        if amt_val<=0:
            details_filled=any([(self.check_number.data or '').strip(),(self.check_bank.data or '').strip(),bool(self.check_due_date.data),(self.card_number.data or '').strip(),(self.card_holder.data or '').strip(),(self.card_expiry.data or '').strip(),(self.bank_transfer_ref.data or '').strip(),(self.online_gateway.data or '').strip(),(self.online_ref.data or '').strip()])
            if m or details_filled:
                self.amount.errors.append('❌ أدخل مبلغًا أكبر من صفر لهذه الدفعة.')
                return False
            return base_ok
        if not m:
            self.method.errors.append('❌ اختر طريقة الدفع.')
            return False
        try:
            if m in {'CHEQUE','CHECK'}: self._validate_cheque(self.check_number.data,self.check_bank.data,self.check_due_date.data)
            elif m in {'BANK','TRANSFER','WIRE'}: self._validate_bank(self.bank_transfer_ref.data)
            elif m=='CARD':
                last4=self._validate_card_payload(self.card_number.data,self.card_holder.data,self.card_expiry.data)
                self.card_number.data=last4
            elif m=='ONLINE': self._validate_online(self.online_gateway.data,self.online_ref.data)
        except ValidationError as e:
            self.method.errors.append(str(e)); return False
        return base_ok


class PaymentForm(PaymentDetailsMixin, FlaskForm):
    id=HiddenField()
    payment_number=StringField(validators=[Optional(),Length(max=50),Unique(lambda:Payment,'payment_number',message='رقم الدفعة مستخدم بالفعل.',case_insensitive=True,normalizer=lambda v:(v or '').strip().upper())])
    payment_date=UnifiedDateTimeField('تاريخ الدفع',format='%Y-%m-%d %H:%M',formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'],default=datetime.utcnow,validators=[DataRequired()],render_kw={'type':'datetime-local','step':'60'})
    subtotal=MoneyField(validators=[Optional(),NumberRange(min=0)])
    tax_rate=DecimalField(places=2,validators=[Optional(),NumberRange(min=0)])
    tax_amount=MoneyField(validators=[Optional(),NumberRange(min=0)])
    total_amount=MoneyField(validators=[DataRequired(),NumberRange(min=0.01)])
    currency=SelectField(validators=[DataRequired()],choices=[('ILS','شيكل'),('USD','دولار'),('EUR','يورو'),('JOD','دينار')],default='ILS')
    method=SelectField(validators=[Optional()],coerce=str,validate_choice=False)
    status=SelectField(validators=[DataRequired()],coerce=str,validate_choice=False)
    direction=SelectField(validators=[DataRequired()],coerce=str,validate_choice=False)
    entity_type=SelectField(validators=[DataRequired()],coerce=str,validate_choice=False)
    entity_id=HiddenField(validators=[Optional()])
    customer_search=StringField(validators=[Optional(),Length(max=100)]); customer_id=HiddenField()
    supplier_search=StringField(validators=[Optional(),Length(max=100)]); supplier_id=HiddenField()
    partner_search=StringField(validators=[Optional(),Length(max=100)]); partner_id=HiddenField()
    shipment_search=StringField(validators=[Optional(),Length(max=100)]); shipment_id=HiddenField()
    expense_search=StringField(validators=[Optional(),Length(max=100)]); expense_id=HiddenField()
    loan_settlement_search=StringField(validators=[Optional(),Length(max=100)]); loan_settlement_id=HiddenField()
    sale_search=StringField(validators=[Optional(),Length(max=100)]); sale_id=HiddenField()
    invoice_search=StringField(validators=[Optional(),Length(max=100)]); invoice_id=HiddenField()
    preorder_search=StringField(validators=[Optional(),Length(max=100)]); preorder_id=HiddenField()
    service_search=StringField(validators=[Optional(),Length(max=100)]); service_id=HiddenField()
    receipt_number=StringField(validators=[Optional(),Length(max=50),Unique(lambda:Payment,'receipt_number',message='رقم الإيصال مستخدم بالفعل.',case_insensitive=True,normalizer=lambda v:(v or '').strip().upper())])
    reference=StringField(validators=[Optional(),Length(max=100)])
    check_number=StringField(validators=[Optional(),Length(max=100)])
    check_bank=StringField(validators=[Optional(),Length(max=100)])
    check_due_date=DateField(format='%Y-%m-%d',validators=[Optional()])
    card_number=StringField(validators=[Optional(),Length(max=100)])
    card_holder=StringField(validators=[Optional(),Length(max=100)])
    card_expiry=StringField(validators=[Optional(),Length(max=10)])
    card_cvv=StringField(validators=[Optional(),Length(min=3,max=4)])
    request_token=HiddenField(validators=[Optional()])
    bank_transfer_ref=StringField(validators=[Optional(),Length(max=100)])
    online_gateway=StringField(validators=[Optional(),Length(max=100)])
    online_ref=StringField(validators=[Optional(),Length(max=100)])
    created_by=HiddenField()
    splits=FieldList(FormField(SplitEntryForm),min_entries=1,max_entries=3)
    notes=TextAreaField(validators=[Optional(),Length(max=500)])
    submit=SubmitField('💾 حفظ الدفعة')
    _entity_field_map={'CUSTOMER':'customer_id','SUPPLIER':'supplier_id','PARTNER':'partner_id','SHIPMENT':'shipment_id','EXPENSE':'expense_id','LOAN':'loan_settlement_id','SALE':'sale_id','INVOICE':'invoice_id','PREORDER':'preorder_id','SERVICE':'service_id'}
    _incoming_entities={'CUSTOMER','SALE','INVOICE','PREORDER','SERVICE'}
    _outgoing_entities={'SUPPLIER','PARTNER','SHIPMENT','EXPENSE','LOAN'}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        prepare_payment_form_choices(self)
        if not self.splits.entries: self.splits.append_entry()
        try:
            for entry in self.splits:
                entry.form.method.choices=self.method.choices
                entry.form.method.validate_choice=False
        except Exception: pass
        et=(self.entity_type.data or '').upper(); d=(self.direction.data or '').upper()
        if et and d not in {'IN','OUT'}:
            if et in self._incoming_entities: self.direction.data='IN'
            elif et in self._outgoing_entities: self.direction.data='OUT'
        self._sync_entity_id_for_render()
    def _nz(self,v):
        if v is None: return ''
        if isinstance(v,str): return v.strip()
        return str(v)
    def _get_entity_ids(self):
        return {'customer_id':self.customer_id.data,'supplier_id':self.supplier_id.data,'partner_id':self.partner_id.data,'shipment_id':self.shipment_id.data,'expense_id':self.expense_id.data,'loan_settlement_id':self.loan_settlement_id.data,'sale_id':self.sale_id.data,'invoice_id':self.invoice_id.data,'preorder_id':self.preorder_id.data,'service_id':self.service_id.data}
    @staticmethod
    def _norm_dir(val):
        if val is None: return None
        v=val.value if hasattr(val,'value') else val; v=str(v).strip().upper()
        if v in ('IN','INCOMING','INCOME','RECEIVE'): return 'IN'
        if v in ('OUT','OUTGOING','PAY','PAYMENT','EXPENSE'): return 'OUT'
        return v
    @classmethod
    def _dir_to_db(cls,v):
        vv=cls._norm_dir(v)
        if vv=='IN': return 'INCOMING'
        if vv=='OUT': return 'OUTGOING'
        return vv
    def _sync_entity_id_for_render(self):
        et=(self.entity_type.data or '').upper(); fn=self._entity_field_map.get(et)
        if fn:
            raw=getattr(self,fn).data
            self.entity_id.data='' if raw is None else (raw if isinstance(raw,str) else str(raw))
        else: self.entity_id.data=''
    def _push_entity_id_to_specific(self):
        et=(self.entity_type.data or '').upper(); fn=self._entity_field_map.get(et)
        if not fn: return
        rid=self._nz(self.entity_id.data)
        if rid:
            for k in self._get_entity_ids().keys(): setattr(getattr(self,k),'data',rid if k==fn else '')
    @staticmethod
    def to_int_any(s): return to_int(s)
    def validate(self,extra_validators=None):
        if not (self.method.data or '').strip() and getattr(self,'splits',None):
            for entry in self.splits:
                f=entry.form; amt=f.amount.data if f.amount.data is not None else Decimal('0.00'); mv=(getattr(f,'method').data or '').strip()
                if amt>0 and mv: self.method.data=mv; break
        self._push_entity_id_to_specific()
        if not super().validate(extra_validators=extra_validators): return False
        pos_amounts=[]; used=set()
        for s in self.splits:
            amt=s.form.amount.data if s.form.amount.data is not None else Decimal('0.00')
            if amt>0:
                pos_amounts.append(amt)
                mv=(s.form.method.data or '').strip().upper()
                if mv: used.add(mv)
        if not pos_amounts:
            self.splits.errors.append('❌ يجب إدخال دفعة جزئية واحدة على الأقل بمبلغ أكبر من صفر.'); return False
        sum_splits=Q2(sum(pos_amounts,Decimal('0.00')))
        total_val=Q2(self.total_amount.data if self.total_amount.data is not None else Decimal('0.00'))
        if sum_splits!=total_val:
            self.total_amount.errors.append('❌ مجموع الدفعات الجزئية يجب أن يساوي المبلغ الكلي'); return False
        if not (self.method.data or '').strip() and used: self.method.data=next(iter(used))
        et=(self.entity_type.data or '').upper(); fn=self._entity_field_map.get(et); ids=self._get_entity_ids()
        if not fn: self.entity_type.errors.append('❌ نوع الكيان غير معروف.'); return False
        raw_id=ids.get(fn); rid_str='' if raw_id is None else (raw_id.strip() if isinstance(raw_id,str) else str(raw_id)); rid_val=self.to_int_any(rid_str) if rid_str else None
        if not rid_val and et=='CUSTOMER':
            try:
                from models import Customer
                st=(getattr(self,'customer_search').data or '').strip() if hasattr(self,'customer_search') else ''
                if st:
                    m=Customer.query.filter(Customer.name.ilike(f'%{st}%')).first()
                    if m: rid_val=m.id
            except Exception: pass
        if not rid_val:
            if et=='CUSTOMER': self.customer_search.errors.append('❌ يجب اختيار العميل لهذه الدفعة.')
            else: getattr(self,fn).errors.append('❌ يجب اختيار المرجع المناسب للكيان المحدد.')
            return False
        filled=[k for k,v in ids.items() if self._nz(v)]
        if len(filled)>1:
            for k in filled:
                if k!=fn: getattr(self,k).errors.append('❌ لا يمكن تحديد أكثر من مرجع.')
            return False
        self.entity_id.data=str(rid_val)
        for k in ids.keys(): setattr(getattr(self,k),'data',str(rid_val) if k==fn else '')
        v=(self.direction.data or '').upper()
        if et in self._incoming_entities and v not in {'IN','INCOMING'}: self.direction.errors.append('❌ هذا الكيان يجب أن تكون حركته وارد (IN).'); return False
        if et in self._outgoing_entities and v not in {'OUT','OUTGOING'}: self.direction.errors.append('❌ هذا الكيان يجب أن تكون حركته صادر (OUT).'); return False
        v=(self.direction.data or '').upper()
        if v not in {'IN','INCOMING','OUT','OUTGOING'}: self.direction.errors.append('❌ اتجاه غير صالح.'); return False
        self.direction.data='IN' if v in {'IN','INCOMING'} else 'OUT'
        m=(self.method.data or '').strip().upper()
        if m in {'CHEQUE','CHECK'}:
            try: self._validate_cheque(self.check_number.data,self.check_bank.data,self.check_due_date.data,op_date=self.payment_date.data)
            except ValidationError as e:
                msg=str(e)
                if 'رقم الشيك' in msg: self.check_number.errors.append(msg)
                elif 'اسم البنك' in msg: self.check_bank.errors.append(msg)
                else: self.check_due_date.errors.append(msg); return False
        elif m=='CARD':
            try:
                last4=self._validate_card_payload(self.card_number.data,self.card_holder.data,self.card_expiry.data)
                self.card_number.data=last4; self.card_cvv.data=None
            except ValidationError as e:
                msg=str(e)
                if 'رقم البطاقة' in msg: self.card_number.errors.append(msg)
                elif 'الانتهاء' in msg: self.card_expiry.errors.append(msg)
                elif 'حامل البطاقة' in msg: self.card_holder.errors.append(msg)
                else: self.method.errors.append(msg); return False
        elif m in {'BANK','TRANSFER','WIRE'}:
            try: self._validate_bank(self.bank_transfer_ref.data)
            except ValidationError as e: self.bank_transfer_ref.errors.append(str(e)); return False
        elif m=='ONLINE':
            try: self._validate_online(self.online_gateway.data,self.online_ref.data)
            except ValidationError as e:
                msg=str(e)
                if 'بوابة' in msg: self.online_gateway.errors.append(msg)
                elif 'مرجع' in msg: self.online_ref.errors.append(msg)
                else: self.method.errors.append(msg); return False
        return True

class PreOrderForm(FlaskForm):
    reference = StrippedStringField('مرجع الحجز', validators=[Optional(), Length(max=50)])
    preorder_date = UnifiedDateTimeField('تاريخ الحجز', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'autocomplete': 'off', 'dir': 'ltr'})
    expected_date = UnifiedDateTimeField('تاريخ التسليم المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'autocomplete': 'off', 'dir': 'ltr'})
    status = SelectField('الحالة', choices=[(PreOrderStatus.PENDING.value, 'معلق'), (PreOrderStatus.CONFIRMED.value, 'مؤكد'), (PreOrderStatus.FULFILLED.value, 'منفذ'), (PreOrderStatus.CANCELLED.value, 'ملغي')], default=PreOrderStatus.PENDING.value, validators=[DataRequired()])
    customer_id = AjaxSelectField('العميل', endpoint='api.search_customers', get_label='name', validators=[DataRequired()])
    product_id = AjaxSelectField('القطعة', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    supplier_id = AjaxSelectField('المورد', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    prepaid_amount = MoneyField('المدفوع مسبقاً', validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    payment_method = SelectField('طريقة الدفع', choices=[(PaymentMethod.CASH.value, 'نقدي'), (PaymentMethod.CARD.value, 'بطاقة'), (PaymentMethod.BANK.value, 'تحويل'), (PaymentMethod.CHEQUE.value, 'شيك'), (PaymentMethod.ONLINE.value, 'دفع إلكتروني')], default=PaymentMethod.CASH.value, validators=[Optional()], coerce=str)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('تأكيد الحجز')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.preorder_date.data and self.expected_date.data and self.expected_date.data < self.preorder_date.data:
            self.expected_date.errors.append('❌ تاريخ التسليم المتوقع يجب أن يكون بعد تاريخ الحجز')
            return False
        st = (self.status.data or '').strip()
        if st not in {s.value for s in PreOrderStatus}:
            self.status.errors.append('❌ حالة الحجز غير معروفة')
            return False
        pm = (self.payment_method.data or '').strip()
        if pm not in {m.value for m in PaymentMethod}:
            self.payment_method.errors.append('❌ طريقة الدفع غير معروفة')
            return False
        qty = to_int(self.quantity.data) or 0
        pid = to_int(self.product_id.data)
        if pid and qty > 0:
            try:
                prod = Product.query.get(pid)
                price = D(getattr(prod, 'price', 0) or 0)
                base = D(qty) * price
                tax = Q2(base * D(self.tax_rate.data or 0) / D("100"))
                total = Q2(base + tax)
                paid = D(self.prepaid_amount.data or 0)
                if paid > total:
                    self.prepaid_amount.errors.append('❌ الدفعة المسبقة تتجاوز إجمالي الطلب بعد الضريبة')
                    return False
            except Exception:
                pass
        return True

    def apply_to(self, preorder: PreOrder) -> PreOrder:
        preorder.reference = (self.reference.data or '').strip() or preorder.reference
        preorder.preorder_date = self.preorder_date.data or preorder.preorder_date
        preorder.expected_date = self.expected_date.data or None
        preorder.status = (self.status.data or PreOrderStatus.PENDING.value)
        preorder.product_id = to_int(self.product_id.data) if self.product_id.data else None
        preorder.warehouse_id = to_int(self.warehouse_id.data) if self.warehouse_id.data else None
        preorder.customer_id = to_int(self.customer_id.data) if self.customer_id.data else None
        preorder.supplier_id = to_int(self.supplier_id.data) if self.supplier_id.data else None
        preorder.partner_id = to_int(self.partner_id.data) if self.partner_id.data else None
        preorder.quantity = to_int(self.quantity.data) or 0
        preorder.prepaid_amount = self.prepaid_amount.data or 0
        preorder.tax_rate = self.tax_rate.data or 0
        preorder.payment_method = (self.payment_method.data or PaymentMethod.CASH.value)
        preorder.notes = (self.notes.data or '').strip() or None
        return preorder

class ServiceRequestForm(FlaskForm):
    service_number = StrippedStringField('رقم الخدمة', validators=[Optional(), Length(max=50)])
    customer_id = AjaxSelectField('العميل', endpoint='api.search_customers', get_label='name', validators=[DataRequired()])
    mechanic_id = AjaxSelectField('الفني', endpoint='api.search_users', get_label='username', validators=[Optional()])
    vehicle_type_id = AjaxSelectField('نوع المعدة/المركبة', endpoint='api.search_equipment_types', get_label='name', validators=[Optional()])
    vehicle_vrn = StrippedStringField('لوحة المركبة', validators=[DataRequired(), Length(max=50)])
    vehicle_model = StrippedStringField('موديل المركبة/المعدة', validators=[Optional(), Length(max=100)])
    chassis_number = StrippedStringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    problem_description = TextAreaField('وصف المشكلة', validators=[Optional(), Length(max=2000)])
    diagnosis = TextAreaField('التشخيص', validators=[Optional(), Length(max=4000)])
    resolution = TextAreaField('المعالجة', validators=[Optional(), Length(max=4000)])
    notes = TextAreaField('ملاحظات عامة', validators=[Optional(), Length(max=4000)])
    engineer_notes = TextAreaField('ملاحظات المهندس', validators=[Optional(), Length(max=4000)])
    description = TextAreaField('وصف عام', validators=[Optional(), Length(max=2000)])
    priority = SelectField('الأولوية', choices=SERVICE_PRIORITY_CHOICES, validators=[Optional()], default='')
    status   = SelectField('الحالة',   choices=SERVICE_STATUS_CHOICES,  validators=[Optional()], default='')
    estimated_duration = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    actual_duration = IntegerField('المدة الفعلية (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost = MoneyField('التكلفة المتوقعة', validators=[Optional(), NumberRange(min=0)])
    total_cost = MoneyField('التكلفة النهائية', validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    start_time = DateField('تاريخ البدء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])
    end_time = DateField('تاريخ الانتهاء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])
    received_at = UnifiedDateTimeField('وقت الاستلام', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    started_at = UnifiedDateTimeField('وقت البدء الفعلي', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    expected_delivery = UnifiedDateTimeField('موعد التسليم المتوقع', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    completed_at = UnifiedDateTimeField('وقت الإكمال', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    discount_total = MoneyField('إجمالي الخصومات', validators=[Optional(), NumberRange(min=0)])
    parts_total = MoneyField('إجمالي قطع الغيار', validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    labor_total = MoneyField('إجمالي الأجور', validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    total_amount = MoneyField('الإجمالي النهائي', validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    warranty_days = IntegerField('مدة الضمان (أيام)', validators=[Optional(), NumberRange(min=0)])
    consume_stock = BooleanField('استهلاك من المخزون؟', default=True)
    submit = SubmitField('حفظ طلب الصيانة')
    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators): return False
        st, et = self.start_time.data, self.end_time.data
        if st and et and et < st: self.end_time.errors.append('❌ وقت الانتهاء يجب أن يكون بعد وقت البدء'); return False
        ra, sa = self.received_at.data, self.started_at.data
        if ra and sa and sa < ra: self.started_at.errors.append('❌ وقت البدء الفعلي يجب أن يكون بعد وقت الاستلام'); return False
        if st and sa and sa.date() < st: self.started_at.errors.append('❌ وقت البدء الفعلي يجب أن يكون في أو بعد تاريخ البدء التخطيطي'); return False
        ed = self.expected_delivery.data
        if sa and ed and ed < sa: self.expected_delivery.errors.append('❌ التسليم المتوقع يجب أن يكون بعد وقت البدء الفعلي'); return False
        if st and ed and ed.date() < st: self.expected_delivery.errors.append('❌ التسليم المتوقع يجب أن يكون بعد تاريخ البدء'); return False
        ct = self.completed_at.data
        if sa and ct and ct < sa: self.completed_at.errors.append('❌ الإكمال يجب أن يكون بعد وقت البدء الفعلي'); return False
        if st and ct and ct.date() < st: self.completed_at.errors.append('❌ الإكمال يجب أن يكون بعد تاريخ البدء'); return False
        parts, labor, disc = D(self.parts_total.data), D(self.labor_total.data), D(self.discount_total.data)
        base = Q2(max(D("0"), parts + labor - disc))
        taxr = D(self.tax_rate.data)
        if taxr < D("0") or taxr > D("100"): self.tax_rate.errors.append('❌ نسبة الضريبة يجب أن تكون بين 0 و 100'); return False
        expected_total = Q2(base * (D("1") + taxr / D("100")))
        if self.total_cost.data is None: self.total_cost.data = base
        elif D(self.total_cost.data) + D("0.01") < base:
            if self.total_amount.data is not None and Q2(self.total_amount.data) != expected_total:
                self.total_amount.errors.append('❌ الإجمالي النهائي لا يطابق المبلغ المتوقع بعد الضريبة'); return False
        return True
    @staticmethod
    def _set_if_has(obj, attr, value):
        if hasattr(obj, attr): setattr(obj, attr, value)
    def apply_to(self, sr):
        sr.service_number = (self.service_number.data or '').strip() or sr.service_number
        sr.customer_id = int(self.customer_id.data) if self.customer_id.data else None
        sr.mechanic_id = int(self.mechanic_id.data) if self.mechanic_id.data else None
        vt_id = int(self.vehicle_type_id.data) if self.vehicle_type_id.data else None
        self._set_if_has(sr, 'vehicle_type_id', vt_id)
        sr.vehicle_vrn = (self.vehicle_vrn.data or '').strip()
        sr.vehicle_model = (self.vehicle_model.data or '').strip() or None
        sr.chassis_number = (self.chassis_number.data or '').strip() or None
        sr.problem_description = (self.problem_description.data or '').strip() or None
        sr.diagnosis = (self.diagnosis.data or '').strip() or None
        sr.resolution = (self.resolution.data or '').strip() or None
        sr.notes = (self.notes.data or '').strip() or None
        sr.engineer_notes = (self.engineer_notes.data or '').strip() or None
        sr.description = (self.description.data or '').strip() or None
        sr.priority = self.priority.data or None
        sr.status = self.status.data or None
        sr.estimated_duration = self.estimated_duration.data or 0
        sr.actual_duration = self.actual_duration.data or 0
        sr.estimated_cost = self.estimated_cost.data or 0
        sr.total_cost = self.total_cost.data or 0
        sr.tax_rate = self.tax_rate.data or 0
        sr.start_time = self.start_time.data or None
        sr.end_time = self.end_time.data or None
        sr.received_at = self.received_at.data or None
        sr.started_at = self.started_at.data or None
        sr.expected_delivery = self.expected_delivery.data or None
        sr.completed_at = self.completed_at.data or None
        sr.currency = (self.currency.data or 'ILS').upper()
        sr.discount_total = self.discount_total.data or 0
        sr.parts_total = self.parts_total.data or 0
        sr.labor_total = self.labor_total.data or 0
        sr.total_amount = self.total_amount.data or 0
        sr.warranty_days = self.warranty_days.data or 0
        sr.consume_stock = bool(self.consume_stock.data)
        return sr

class ShipmentItemForm(FlaskForm):
    class Meta:
        csrf = False

    shipment_id = HiddenField(validators=[Optional()])
    product_id = AjaxSelectField("الصنف", endpoint="api.search_products",
        get_label="name", coerce=int, validators=[DataRequired()])
    warehouse_id = AjaxSelectField("المخزن", endpoint="api.search_warehouses",
        get_label="name", coerce=int, validators=[DataRequired()])
    quantity = IntegerField("الكمية", validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = MoneyField("سعر الوحدة", validators=[DataRequired(), NumberRange(min=0)])
    declared_value = MoneyField("القيمة المعلنة", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=1000)])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        qty = int(self.quantity.data or 0)
        uc = self.unit_cost.data or 0
        dv = self.declared_value.data
        if dv is not None and dv < (qty * uc):
            self.declared_value.errors.append("القيمة المعلنة يجب ألا تقل عن (الكمية × سعر الوحدة).")
            return False
        return True

class ShipmentPartnerForm(FlaskForm):
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()], coerce=int)
    role = StrippedStringField('الدور', validators=[Optional(), Length(max=50)])
    identity_number = StrippedStringField('رقم الهوية', validators=[Optional(), Length(max=100)])
    phone_number = StrippedStringField('هاتف الشريك', validators=[Optional(), Length(max=20)])
    address = StrippedStringField('العنوان', validators=[Optional(), Length(max=200)])
    unit_price_before_tax = DecimalField('سعر قبل الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])
    expiry_date = UnifiedDateField('تاريخ الانتهاء', format='%Y-%m-%d', formats=['%Y-%m-%d','%d-%m-%Y','%d/%m/%Y','%m/%d/%Y'], validators=[Optional()], render_kw={'type':'date','dir':'ltr'})
    share_percentage = DecimalField('نسبة المشاركة (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount = DecimalField('حصة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ')
    
class ShipmentForm(FlaskForm):
    shipment_number = StrippedStringField('رقم الشحنة', validators=[Optional(), Length(max=50)])
    shipment_date = UnifiedDateTimeField('تاريخ الشحن', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'autocomplete':'off','dir':'ltr','step':'60','type':'datetime-local'})
    expected_arrival = UnifiedDateTimeField('الوصول المتوقع', format='%Y-%m-%d %H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    actual_arrival = UnifiedDateTimeField('الوصول الفعلي', format='%Y-%m-%dT%H:%M', formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()], render_kw={'type':'datetime-local','step':'60'})
    origin = StrippedStringField('المنشأ', validators=[Optional(), Length(max=100)])
    destination = StrippedStringField('الوجهة', validators=[Optional(), Length(max=100)])
    destination_id = QuerySelectField('مخزن الوجهة', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), allow_blank=False, get_label='name')
    status = SelectField('الحالة', choices=[], default='DRAFT', validators=[DataRequired()], coerce=str, validate_choice=False)
    value_before = MoneyField('قيمة البضائع قبل المصاريف', validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    shipping_cost = MoneyField('تكلفة الشحن', validators=[Optional(), NumberRange(min=0)])
    customs = MoneyField('الجمارك', validators=[Optional(), NumberRange(min=0)])
    vat = MoneyField('ضريبة القيمة المضافة', validators=[Optional(), NumberRange(min=0)])
    insurance = MoneyField('التأمين', validators=[Optional(), NumberRange(min=0)])
    total_value = MoneyField('الإجمالي', validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    carrier = StrippedStringField('شركة النقل', validators=[Optional(), Length(max=100)])
    tracking_number = StrippedStringField('رقم التتبع', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='USD', validators=[DataRequired()])
    sale_id = QuerySelectField('البيع المرتبط', query_factory=lambda: Sale.query.order_by(Sale.sale_number).all(), allow_blank=True, get_label='sale_number')
    items = FieldList(FormField(ShipmentItemForm), min_entries=1)
    partners = FieldList(FormField(ShipmentPartnerForm), min_entries=0)
    submit = SubmitField('حفظ الشحنة')
    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators): return False
        forms = [e.form for e in self.items]
        if not any(f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1 for f in forms):
            self.items.errors.append('أدخل عنصرًا واحدًا على الأقل.'); return False
        seen = set()
        for f in forms:
            pid, wid, qty = f.product_id.data, f.warehouse_id.data, f.quantity.data or 0
            if pid and wid and qty >= 1:
                key = (int(pid), int(wid))
                if key in seen:
                    f.product_id.errors.append('تكرار نفس الصنف لنفس المخزن في نفس الشحنة غير مسموح.')
                    self.items.errors.append('تجنّب تكرار (الصنف، المخزن) داخل الشحنة.'); return False
                seen.add(key)
        total_pct = 0.0
        for e in self.partners.entries:
            f = e.form
            if getattr(f, "partner_id", None) and f.partner_id.data:
                try: total_pct += float(f.share_percentage.data or 0)
                except Exception: pass
        if total_pct > 100.000001:
            self.partners.errors.append('مجموع نسب الشركاء لا يجوز أن يتجاوز 100٪.')
            if self.partners.entries: self.partners.entries[0].form.share_percentage.errors.append('يجب ألا يتجاوز مجموع النسب 100٪.')
            return False
        return True
    def apply_to(self, shipment):
        shipment.shipment_number = (self.shipment_number.data or '').strip() or shipment.shipment_number
        shipment.shipment_date = self.shipment_date.data or shipment.shipment_date
        shipment.expected_arrival = self.expected_arrival.data or None
        shipment.actual_arrival = self.actual_arrival.data or None
        shipment.origin = (self.origin.data or '').strip() or None
        shipment.destination = (self.destination.data or '').strip() or None
        shipment.status = (self.status.data or '').strip().upper() or 'DRAFT'
        shipment.currency = (self.currency.data or 'USD').upper()
        shipment.value_before = self.value_before.data or None
        shipment.shipping_cost = self.shipping_cost.data or None
        shipment.customs = self.customs.data or None
        shipment.vat = self.vat.data or None
        shipment.insurance = self.insurance.data or None
        shipment.carrier = (self.carrier.data or '').strip() or None
        shipment.tracking_number = (self.tracking_number.data or '').strip() or None
        shipment.notes = (self.notes.data or '').strip() or None
        dest_obj = self.destination_id.data; shipment.destination_id = dest_obj.id if dest_obj else None
        sale_obj = self.sale_id.data; shipment.sale_id = sale_obj.id if sale_obj else None
        shipment.items = [ShipmentItem(product_id=int(f.product_id.data), warehouse_id=int(f.warehouse_id.data), quantity=int(f.quantity.data), unit_cost=f.unit_cost.data or 0, declared_value=f.declared_value.data, notes=(f.notes.data or '').strip() or None) for f in (e.form for e in self.items) if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1]
        shipment.partners = [ShipmentPartner(partner_id=int(f.partner_id.data), role=(f.role.data or '').strip() or None, notes=(f.notes.data or '').strip() or None, identity_number=(f.identity_number.data or '').strip() or None, phone_number=(f.phone_number.data or '').strip() or None, address=(f.address.data or '').strip() or None, unit_price_before_tax=f.unit_price_before_tax.data or None, expiry_date=f.expiry_date.data or None, share_percentage=f.share_percentage.data or None, share_amount=f.share_amount.data or None) for f in (e.form for e in self.partners) if f.partner_id.data]
        return shipment

class UniversalReportForm(FlaskForm):
    table = SelectField('نوع التقرير', choices=[], validators=[Optional()])
    date_field = SelectField('حقل التاريخ', choices=[], validators=[Optional()])
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    selected_fields = SelectMultipleField('أعمدة التقرير', choices=[], coerce=str, validators=[Optional()])
    submit = SubmitField('عرض التقرير')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append("تاريخ النهاية يجب أن يكون بعد أو مساويًا لتاريخ البداية.")
            return False
        return True


class AuditLogFilterForm(FlaskForm):
    model_name = SelectField('النموذج', choices=[('', 'الكل'), ('Customer', 'عملاء'), ('Product', 'منتجات'), ('Sale', 'مبيعات')], validators=[Optional()])
    action = SelectField('الإجراء', choices=[('', 'الكل'), ('CREATE', 'إنشاء'), ('UPDATE', 'تحديث'), ('DELETE', 'حذف')], validators=[Optional()])
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    export_format = SelectField('تصدير كـ', choices=[('pdf', 'PDF'), ('csv', 'CSV'), ('excel', 'Excel')], default='pdf')
    include_details = SelectField('تضمين التفاصيل', choices=[('0', 'لا'), ('1', 'نعم')], default='0')
    submit = SubmitField('تصفية السجلات')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append("تاريخ النهاية يجب أن يكون بعد أو مساويًا لتاريخ البداية.")
            return False
        return True


class CustomReportForm(FlaskForm):
    report_type = SelectField('نوع التقرير', choices=[('inventory', 'المخزون'), ('sales', 'المبيعات'), ('customers', 'العملاء'), ('financial', 'مالي')], validators=[DataRequired()])
    parameters = TextAreaField('المعايير (JSON)', validators=[Optional()])
    submit = SubmitField('إنشاء التقرير')


class EmployeeForm(FlaskForm):
    name = StrippedStringField('الاسم', validators=[DataRequired(), Length(max=100)])
    position = StrippedStringField('الوظيفة', validators=[Optional(), Length(max=100)])
    phone = StrippedStringField('الجوال', validators=[Optional(), Length(max=20)])
    email = StrippedStringField('البريد', validators=[Optional(), Email(), Length(max=120)])
    bank_name = StrippedStringField('البنك', validators=[Optional(), Length(max=100)])
    account_number = StrippedStringField('رقم الحساب', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit = SubmitField('حفظ الموظف')

    def validate_phone(self, field):
        s = (field.data or "").strip()
        if s:
            s = re.sub(r"\D+", "", s)
            if len(s) < 6 or len(s) > 15:
                raise ValidationError("❌ رقم الجوال غير صالح")
        field.data = s or None

    def validate_email(self, field):
        e = (field.data or "").strip().lower()
        field.data = e or None


class ExpenseTypeForm(FlaskForm):
    id = HiddenField(validators=[Optional()])
    name = StrippedStringField('اسم نوع المصروف', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('وصف اختياري', validators=[Optional(), Length(max=500)])
    is_active = BooleanField('مُفعّل', default=True)
    submit = SubmitField('حفظ')

    def validate_name(self, field):
        name = (field.data or "").strip()
        qry = ExpenseType.query.filter(func.lower(ExpenseType.name) == name.lower())
        if (self.id.data or "").isdigit():
            qry = qry.filter(ExpenseType.id != int(self.id.data))
        if qry.first():
            raise ValidationError("اسم نوع المصروف موجود مسبقًا.")

    def apply_to(self, obj):
        obj.name = (self.name.data or "").strip()
        obj.description = (self.description.data or "").strip() or None
        obj.is_active = bool(self.is_active.data)
        return obj


class QuickExpenseForm(PaymentDetailsMixin, FlaskForm):
    date = DateField('التاريخ', validators=[DataRequired()], default=date.today)
    amount = MoneyField('المبلغ', validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    type_id = SelectField('نوع المصروف', coerce=int, validators=[DataRequired()])
    paid_to = StrippedStringField('الجهة المستفيدة', validators=[Optional(), Length(max=200)])
    payment_method = SelectField('طريقة الدفع', choices=enum_choices(PaymentMethod, labels_map=METHOD_LABELS_AR, include_blank=False), validators=[DataRequired()], coerce=str, validate_choice=False)
    check_number = StrippedStringField('رقم الشيك', validators=[Optional(), Length(max=100)])
    check_bank = StrippedStringField('اسم البنك', validators=[Optional(), Length(max=100)])
    check_due_date = DateField('تاريخ الاستحقاق', validators=[Optional()])
    bank_transfer_ref = StrippedStringField('مرجع الحوالة', validators=[Optional(), Length(max=100)])
    card_number = StrippedStringField('رقم البطاقة', validators=[Optional(), Length(max=19)])
    card_holder = StrippedStringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_expiry = StrippedStringField('تاريخ انتهاء البطاقة', validators=[Optional(), Length(max=7)])
    online_gateway = StrippedStringField('البوابة الإلكترونية', validators=[Optional(), Length(max=50)])
    online_ref = StrippedStringField('مرجع العملية', validators=[Optional(), Length(max=100)])
    payment_details = TextAreaField('تفاصيل إضافية', validators=[Optional(), Length(max=255)])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.filter_by(is_active=True).order_by(ExpenseType.name).all()]

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        m = (self.payment_method.data or '').strip().upper()
        try:
            if m == 'CHEQUE':
                self._validate_cheque(self.check_number.data, self.check_bank.data, self.check_due_date.data, op_date=self.date.data)
            elif m == 'BANK':
                self._validate_bank(self.bank_transfer_ref.data)
            elif m == 'CARD':
                last4 = self._validate_card_payload(self.card_number.data, self.card_holder.data, self.card_expiry.data)
                self.card_number.data = last4
            elif m == 'ONLINE':
                self._validate_online(self.online_gateway.data, self.online_ref.data)
        except ValidationError as e:
            msg = str(e)
            if 'شيك' in msg:
                if 'رقم' in msg: self.check_number.errors.append(msg)
                elif 'البنك' in msg: self.check_bank.errors.append(msg)
                else: self.check_due_date.errors.append(msg)
            elif 'تحويل' in msg:
                self.bank_transfer_ref.errors.append(msg)
            elif 'بطاقة' in msg or 'MM/YY' in msg:
                if 'رقم' in msg: self.card_number.errors.append(msg)
                elif 'حامل' in msg: self.card_holder.errors.append(msg)
                else: self.card_expiry.errors.append(msg)
            elif 'بوابة' in msg or 'مرجع' in msg:
                if 'بوابة' in msg: self.online_gateway.errors.append(msg)
                else: self.online_ref.errors.append(msg)
            else:
                self.payment_method.errors.append(msg)
            return False
        return True

    def build_payment_details(self):
        m = (self.payment_method.data or '').strip().upper()
        last4 = None
        if m == 'CARD':
            last4 = self._validate_card_payload(self.card_number.data, self.card_holder.data, self.card_expiry.data)
        return self.build_payment_details_json(
            m,
            check_number=self.check_number.data,
            check_bank=self.check_bank.data,
            check_due_date=self.check_due_date.data,
            bank_transfer_ref=self.bank_transfer_ref.data,
            card_last4=last4,
            card_holder=self.card_holder.data,
            card_expiry=self.card_expiry.data,
            online_gateway=self.online_gateway.data,
            online_ref=self.online_ref.data,
            extra=self.payment_details.data,
            card_brand=None
        )

class ExpenseForm(PaymentDetailsMixin, FlaskForm):
    date = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[DataRequired()])
    amount = MoneyField('المبلغ', validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    type_id = SelectField('نوع المصروف', coerce=int, validators=[DataRequired()])
    employee_id = AjaxSelectField('الموظف', endpoint='api.search_employees', get_label='name', validators=[Optional()], coerce=int)
    shipment_id = AjaxSelectField('الشحنة', endpoint='api.search_shipments', get_label='shipment_number', validators=[Optional()], coerce=int)
    utility_account_id = AjaxSelectField('حساب المرفق', endpoint='api.search_utility_accounts', get_label='alias', validators=[Optional()], coerce=int)
    stock_adjustment_id = AjaxSelectField('تسوية مخزون', endpoint='api.search_stock_adjustments', get_label='id', validators=[Optional()], coerce=int)
    warehouse_id = AjaxSelectField('المستودع', endpoint='api.search_warehouses', get_label='name', validators=[Optional()], coerce=int)
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()], coerce=int)
    beneficiary_name = StrippedStringField('اسم الجهة المستفيدة', validators=[Optional(), Length(max=200)])
    paid_to = StrippedStringField('مدفوع إلى', validators=[Optional(), Length(max=200)])
    period_start = DateField('بداية الفترة', validators=[Optional()])
    period_end = DateField('نهاية الفترة', validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=enum_choices(PaymentMethod, labels_map=METHOD_LABELS_AR, include_blank=False), validators=[DataRequired()], coerce=str, validate_choice=False)
    check_number = StrippedStringField('رقم الشيك', validators=[Optional(), Length(max=100)])
    check_bank = StrippedStringField('البنك', validators=[Optional(), Length(max=100)])
    check_due_date = DateField('تاريخ الاستحقاق', format='%Y-%m-%d', validators=[Optional()])
    bank_transfer_ref = StrippedStringField('مرجع التحويل', validators=[Optional(), Length(max=100)])
    card_number = StrippedStringField('رقم البطاقة', validators=[Optional(), Length(max=19)])
    card_holder = StrippedStringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_expiry = StrippedStringField('MM/YY', validators=[Optional(), Length(max=7)])
    online_gateway = StrippedStringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    online_ref = StrippedStringField('مرجع العملية', validators=[Optional(), Length(max=100)])
    payment_details = StrippedStringField('تفاصيل إضافية', validators=[Optional(), Length(max=255)])
    description = StrippedStringField('وصف مختصر', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    tax_invoice_number = StrippedStringField('رقم فاتورة ضريبية', validators=[Optional(), Length(max=100)])
    submit = SubmitField('حفظ')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.filter_by(is_active=True).order_by(ExpenseType.name).all()]

    def _resolve_kind(self):
        t = ExpenseType.query.get(int(self.type_id.data)) if self.type_id.data else None
        n = (t.name if t else '').strip().lower()
        if any(k in n for k in ['راتب','رواتب','salary','salaries']): return 'SALARY'
        if any(k in n for k in ['جمرك','جمارك','custom']): return 'CUSTOMS'
        if any(k in n for k in ['كهرب','electric']): return 'ELECTRICITY'
        if any(k in n for k in ['مياه','ماء','water']): return 'WATER'
        if any(k in n for k in ['تالف','هدر','damag']): return 'DAMAGED'
        if any(k in n for k in ['استخدام','محل','داخلي','store']): return 'STORE_USE'
        return 'MISC'

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        kind = self._resolve_kind()
        if self.period_start.data and self.period_end.data and self.period_end.data < self.period_start.data:
            self.period_end.errors.append('نهاية الفترة يجب أن تكون بعد بدايتها')
            return False
        if kind == 'SALARY':
            if not self.employee_id.data:
                self.employee_id.errors.append('اختر الموظف')
                return False
            if not self.period_start.data or not self.period_end.data:
                self.period_end.errors.append('حدد فترة الرواتب')
                return False
        elif kind == 'CUSTOMS':
            if not self.shipment_id.data:
                self.shipment_id.errors.append('اختر الشحنة')
                return False
        elif kind in ('ELECTRICITY','WATER'):
            if not self.utility_account_id.data:
                self.utility_account_id.errors.append('اختر حساب المرفق')
                return False
            if not self.period_start.data or not self.period_end.data:
                self.period_end.errors.append('حدد فترة الفاتورة')
                return False
        elif kind in ('DAMAGED','STORE_USE'):
            if not self.stock_adjustment_id.data:
                self.stock_adjustment_id.errors.append('اختر تسوية مخزون')
                return False
        else:
            if not (self.beneficiary_name.data or self.paid_to.data):
                self.beneficiary_name.errors.append('أدخل اسم الجهة المستفيدة')
                return False
        m = (self.payment_method.data or '').strip().upper()
        try:
            if m == 'CHEQUE':
                self._validate_cheque(self.check_number.data, self.check_bank.data, self.check_due_date.data, op_date=self.date.data)
            elif m == 'BANK':
                self._validate_bank(self.bank_transfer_ref.data)
            elif m == 'CARD':
                last4 = self._validate_card_payload(self.card_number.data, self.card_holder.data, self.card_expiry.data)
                self.card_number.data = last4
            elif m == 'ONLINE':
                self._validate_online(self.online_gateway.data, self.online_ref.data)
        except ValidationError as e:
            msg = str(e)
            if 'شيك' in msg:
                if 'رقم' in msg: self.check_number.errors.append(msg)
                elif 'البنك' in msg: self.check_bank.errors.append(msg)
                else: self.check_due_date.errors.append(msg)
            elif 'تحويل' in msg:
                self.bank_transfer_ref.errors.append(msg)
            elif 'بطاقة' in msg or 'MM/YY' in msg:
                if 'رقم' in msg: self.card_number.errors.append(msg)
                elif 'حامل' in msg: self.card_holder.errors.append(msg)
                else: self.card_expiry.errors.append(msg)
            elif 'بوابة' in msg or 'مرجع' in msg:
                if 'بوابة' in msg: self.online_gateway.errors.append(msg)
                else: self.online_ref.errors.append(msg)
            else:
                self.payment_method.errors.append(msg)
            return False
        return True

    def build_payment_details(self):
        m = (self.payment_method.data or '').strip().upper()
        last4 = None
        if m == 'CARD':
            last4 = self._validate_card_payload(
                self.card_number.data,
                self.card_holder.data,
                self.card_expiry.data
            )
        return self.build_payment_details_json(
            m,
            check_number=self.check_number.data,
            check_bank=self.check_bank.data,
            check_due_date=self.check_due_date.data,
            bank_transfer_ref=self.bank_transfer_ref.data,
            card_last4=last4,
            card_holder=self.card_holder.data,
            card_expiry=self.card_expiry.data,
            online_gateway=self.online_gateway.data,
            online_ref=self.online_ref.data,
            extra=self.payment_details.data,
            card_brand=None
        )

    def apply_to(self, exp):
        exp.date = datetime.combine(self.date.data, datetime.min.time())
        exp.amount = self.amount.data
        exp.currency = (self.currency.data or 'ILS').upper()
        exp.type_id = int(self.type_id.data) if self.type_id.data else None
        exp.employee_id = int(self.employee_id.data) if getattr(self.employee_id, "data", None) else None
        exp.warehouse_id = int(self.warehouse_id.data) if getattr(self.warehouse_id, "data", None) else None
        exp.partner_id = int(self.partner_id.data) if getattr(self.partner_id, "data", None) else None
        exp.shipment_id = int(self.shipment_id.data) if getattr(self.shipment_id, "data", None) else None
        exp.utility_account_id = int(self.utility_account_id.data) if getattr(self.utility_account_id, "data", None) else None
        exp.stock_adjustment_id = int(self.stock_adjustment_id.data) if getattr(self.stock_adjustment_id, "data", None) else None
        exp.period_start = self.period_start.data or None
        exp.period_end = self.period_end.data or None
        exp.paid_to = (self.paid_to.data or '').strip() or None
        exp.description = (self.description.data or '').strip() or None
        exp.notes = (self.notes.data or '').strip() or None
        exp.tax_invoice_number = (self.tax_invoice_number.data or '').strip() or None
        exp.payment_method = (self.payment_method.data or '').strip().upper()
        exp.payment_details = self.build_payment_details()
        exp.check_number = (self.check_number.data or '').strip() or None
        exp.check_bank = (self.check_bank.data or '').strip() or None
        exp.check_due_date = self.check_due_date.data or None
        exp.bank_transfer_ref = (self.bank_transfer_ref.data or '').strip() or None
        exp.card_holder = (self.card_holder.data or '').strip() or None
        exp.card_expiry = (self.card_expiry.data or '').strip() or None
        exp.card_number = only_digits(self.card_number.data or '')[-4:] if self.card_number.data else None
        exp.online_gateway = (self.online_gateway.data or '').strip() or None
        exp.online_ref = (self.online_ref.data or '').strip() or None
        kind = self._resolve_kind()
        if kind == 'SALARY' and exp.employee_id:
            emp = Employee.query.get(exp.employee_id)
            exp.payee_type = 'EMPLOYEE'
            exp.payee_entity_id = exp.employee_id
            exp.payee_name = emp.name if emp else (self.paid_to.data or None)
            if not exp.paid_to: exp.paid_to = exp.payee_name
        elif kind == 'CUSTOMS':
            exp.payee_type = 'OTHER'
            exp.payee_entity_id = None
            exp.payee_name = (self.beneficiary_name.data or self.paid_to.data or '').strip() or None
            if not exp.paid_to: exp.paid_to = exp.payee_name
        elif kind in ('ELECTRICITY','WATER'):
            exp.payee_type = 'UTILITY'
            exp.payee_entity_id = exp.utility_account_id
            ua = UtilityAccount.query.get(exp.utility_account_id) if exp.utility_account_id else None
            exp.payee_name = (ua.alias or ua.provider) if ua else (self.beneficiary_name.data or self.paid_to.data or None)
            if not exp.paid_to: exp.paid_to = exp.payee_name
        elif kind in ('DAMAGED','STORE_USE'):
            exp.payee_type = 'OTHER'
            exp.payee_entity_id = None
            exp.payee_name = 'تسوية مخزون'
            sa = StockAdjustment.query.get(exp.stock_adjustment_id) if exp.stock_adjustment_id else None
            if sa and sa.total_cost is not None: exp.amount = sa.total_cost
            if not exp.paid_to: exp.paid_to = exp.payee_name
        else:
            exp.payee_type = 'OTHER'
            exp.payee_entity_id = None
            exp.payee_name = (self.beneficiary_name.data or self.paid_to.data or '').strip() or None
            if not exp.paid_to: exp.paid_to = exp.payee_name
        return exp

class UtilityAccountForm(FlaskForm):
    id = HiddenField(validators=[Optional()])
    utility_type = SelectField('نوع المرفق', choices=[('ELECTRICITY', 'كهرباء'), ('WATER', 'مياه')], validators=[DataRequired()])
    provider = StrippedStringField('المزوّد', validators=[DataRequired(), Length(max=120)])
    account_no = StrippedStringField('رقم الحساب', validators=[Optional(), Length(max=100)])
    meter_no = StrippedStringField('رقم العداد', validators=[Optional(), Length(max=100)])
    alias = StrippedStringField('اسم مختصر', validators=[Optional(), Length(max=120)])
    is_active = BooleanField('مُفعّل', default=True)
    submit = SubmitField('حفظ')

    def apply_to(self, obj):
        obj.utility_type = (self.utility_type.data or '').upper()
        obj.provider = (self.provider.data or '').strip()
        obj.account_no = (self.account_no.data or '').strip() or None
        obj.meter_no = (self.meter_no.data or '').strip() or None
        obj.alias = (self.alias.data or '').strip() or None
        obj.is_active = bool(self.is_active.data)
        return obj

class StockAdjustmentItemForm(FlaskForm):
    class Meta: csrf = False
    product_id = AjaxSelectField('المنتج', endpoint='api.search_products', get_label='name', validators=[DataRequired()], coerce=int)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = MoneyField('تكلفة الوحدة', validators=[DataRequired(), NumberRange(min=0)])
    notes = StrippedStringField('ملاحظات', validators=[Optional(), Length(max=200)])

class StockAdjustmentForm(FlaskForm):
    date = DateField('التاريخ', validators=[DataRequired()], default=date.today)
    warehouse_id = AjaxSelectField('المستودع', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()], coerce=int)
    reason = SelectField('السبب', choices=[('DAMAGED','تالف'),('STORE_USE','استخدام داخلي')], validators=[DataRequired()])
    items = FieldList(FormField(StockAdjustmentItemForm), min_entries=1)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ')
    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators): return False
        rv = (self.reason.data or '').strip().upper()
        if rv not in ('DAMAGED','STORE_USE'):
            self.reason.errors.append('سبب غير صالح.')
            return False
        self.reason.data = rv
        valids = [e.form for e in self.items if e.form.product_id.data and (e.form.quantity.data or 0) >= 1]
        if not valids:
            self.items.errors.append('أضف بندًا واحدًا على الأقل.')
            return False
        return True

class CustomerFormOnline(FlaskForm):
    name = StrippedStringField('الاسم الكامل', validators=[DataRequired(), Length(max=100)])
    email = StrippedStringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StrippedStringField('رقم الجوال', validators=[DataRequired(), Length(min=7, max=20)])
    whatsapp = StrippedStringField('واتساب', validators=[DataRequired(), Length(min=7, max=20)])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password', message="كلمتا المرور غير متطابقتين")])
    address = StrippedStringField('العنوان', validators=[Optional(), Length(max=200)])
    category = SelectField('فئة العميل', choices=[('عادي', 'عادي'), ('ذهبي', 'ذهبي'), ('بلاتيني', 'بلاتيني')], default='عادي')
    submit = SubmitField('تسجيل')

    def validate_phone(self, field):
        v = (field.data or "").strip()
        v = re.sub(r"\s+", "", v)
        if v.startswith("+"):
            v = "+" + re.sub(r"\D", "", v[1:])
        else:
            v = re.sub(r"\D", "", v)
        digits = re.sub(r"\D", "", v)
        if len(digits) < 7 or len(digits) > 15:
            raise ValidationError("رقم الجوال غير صالح")
        field.data = v

    def validate_whatsapp(self, field):
        v = (field.data or "").strip()
        v = re.sub(r"\s+", "", v)
        if v.startswith("+"):
            v = "+" + re.sub(r"\D", "", v[1:])
        else:
            v = re.sub(r"\D", "", v)
        digits = re.sub(r"\D", "", v)
        if len(digits) < 7 or len(digits) > 15:
            raise ValidationError("رقم واتساب غير صالح")
        field.data = v

    def validate_password(self, field):
        pw = (field.data or "").strip()
        if len(pw) < 8:
            raise ValidationError("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
        if not any(c.isdigit() for c in pw):
            raise ValidationError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل.")
        if not any(c.isalpha() for c in pw):
            raise ValidationError("كلمة المرور يجب أن تحتوي على حرف واحد على الأقل.")


class CustomerPasswordResetRequestForm(FlaskForm):
    email = StrippedStringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    submit = SubmitField('إرسال رابط إعادة تعيين')


class CustomerPasswordResetForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password', message="كلمتا المرور غير متطابقتين")])
    submit = SubmitField('تحديث كلمة المرور')

class AddToOnlineCartForm(FlaskForm):
    product_id = HiddenField()
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1, max=9999)])
    submit = SubmitField('أضف للسلة')
    
class OnlinePaymentForm(FlaskForm):
    payment_ref = StringField('مرجع الدفع', validators=[DataRequired(), Length(max=100)])
    order_id = IntegerField('رقم الطلب', validators=[DataRequired(), NumberRange(min=1)])
    amount = MoneyField('المبلغ', validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    method = StringField('وسيلة الدفع', validators=[Optional(), Length(max=50)])
    gateway = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    status = SelectField('حالة المعاملة',
        choices=[('PENDING','قيد الانتظار'),('SUCCESS','مكتملة'),('FAILED','فاشلة'),
                 ('REFUNDED','مُرجعة'),('COMPLETED','مكتملة (Alias)')],
        default='PENDING', validators=[DataRequired()], validate_choice=False)
    transaction_data = TextAreaField('بيانات المعاملة (JSON)', validators=[Optional()])
    processed_at = UnifiedDateTimeField('تاريخ المعالجة', format='%Y-%m-%d %H:%M',
        formats=['%Y-%m-%d %H:%M','%Y-%m-%dT%H:%M'], validators=[Optional()],
        render_kw={'type':'datetime-local','step':'60'})
    card_last4 = StringField('آخر 4 أرقام', validators=[Optional(), Length(min=4, max=4)])
    card_encrypted = TextAreaField('بيانات البطاقة المشفّرة', validators=[Optional(), Length(max=8000)])
    card_expiry = StringField('انتهاء البطاقة (MM/YY)', validators=[Optional(), Length(max=7)])
    cardholder_name = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_brand = SelectField('نوع البطاقة',
        choices=[('','غير محدد'),('VISA','VISA'),('MASTERCARD','MASTERCARD'),
                 ('AMEX','AMEX'),('DISCOVER','DISCOVER'),('OTHER','OTHER')], validators=[Optional()])
    card_fingerprint = StringField('بصمة البطاقة', validators=[Optional(), Length(max=128)])
    submit = SubmitField('حفظ الدفع')

    def validate_transaction_data(self, field):
        if field.data:
            try:
                json.loads(field.data)
            except Exception:
                raise ValidationError("❌ بيانات JSON غير صالحة")

    def validate_card_last4(self, field):
        v = (field.data or "").strip()
        if v and (len(v) != 4 or not v.isdigit()):
            raise ValidationError("يجب أن تكون 4 أرقام.")

    def validate_card_expiry(self, field):
        v = (field.data or "").strip()
        if v and not is_valid_expiry_mm_yy(v):
            raise ValidationError("صيغة خاطئة أو تاريخ منتهي. استخدم MM/YY.")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        st = (self.status.data or "").upper()
        if st == "COMPLETED":
            self.status.data = "SUCCESS"
            st = "SUCCESS"
        if st in {"SUCCESS", "REFUNDED"} and not self.processed_at.data:
            self.processed_at.errors.append("مطلوب عند إتمام/إرجاع العملية.")
            return False
        has_card_payload = any([
            (self.card_encrypted.data or "").strip(),
            (self.card_brand.data or "").strip(),
            (self.card_last4.data or "").strip()
        ])
        if has_card_payload:
            if not (self.card_brand.data or "").strip():
                self.card_brand.errors.append("حدد نوع البطاقة.")
                return False
            if not (self.card_last4.data or "").strip():
                self.card_last4.errors.append("أدخل آخر 4 أرقام.")
                return False
            if not (self.card_expiry.data or "").strip():
                self.card_expiry.errors.append("أدخل تاريخ الانتهاء.")
                return False
        return True

class ExchangeTransactionForm(FlaskForm):
    id = HiddenField()
    product_id = AjaxSelectField('الصنف', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()])
    direction = SelectField('النوع', choices=[], validators=[DataRequired()], coerce=str, validate_choice=False)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = MoneyField('التكلفة للوحدة', validators=[Optional(), NumberRange(min=0)])
    is_priced = BooleanField('مسعّر', default=False)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ')

    def __init__(self, *args, require_pricing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_pricing = bool(require_pricing)
        self.warnings = []

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        self.direction.data = (self.direction.data or "").upper()
        wid = to_int(self.warehouse_id.data)
        if wid:
            try:
                from models import Warehouse, WarehouseType
                wh = Warehouse.query.get(wid)
                wt = getattr(wh.warehouse_type, "value", wh.warehouse_type) if wh else None
                if not wh or wt != WarehouseType.EXCHANGE.value:
                    self.warehouse_id.errors.append('يجب أن تكون الحركة على مخزن تبادل.')
                    return False
                if not getattr(wh, "supplier_id", None):
                    self.warehouse_id.errors.append('مخزن التبادل يجب أن يكون مربوطًا بمورد.')
                    return False
            except Exception as e:
                current_app.logger.warning("Warehouse check failed (wid=%s): %s", wid, e)
                self.warehouse_id.errors.append('تعذر التحقق من المخزن.')
                return False

        if (self.direction.data or '') == 'OUT':
            pid = to_int(self.product_id.data)
            qty = to_int(self.quantity.data) or 0
            if pid and wid and qty:
                try:
                    from models import StockLevel
                    sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
                    avail = (sl.quantity if sl else 0) - (sl.reserved_quantity if sl else 0)
                    if qty > max(int(avail or 0), 0):
                        self.quantity.errors.append('الكمية غير كافية في المخزن.')
                        return False
                except Exception as e:
                    current_app.logger.warning("Stock check failed (pid=%s, wid=%s): %s", pid, wid, e)

        uc = to_dec(self.unit_cost.data)
        priced_flag = bool(self.is_priced.data)

        if self.require_pricing:
            if uc is None or uc <= 0:
                self.unit_cost.errors.append('هذه تسوية: أدخل تكلفة موجبة للوحدة.')
                return False
            self.is_priced.data = True
        else:
            if priced_flag and (uc is None or uc <= 0):
                self.unit_cost.errors.append('عند اختيار "مسعّر" يجب إدخال تكلفة موجبة.')
                return False
            if (not priced_flag) and (uc is not None and uc > 0):
                self.is_priced.data = True
            if (not self.is_priced.data) and (uc is None or uc <= 0):
                self.warnings.append('تنبيه: لم تُدخل تكلفة، ستُحفظ الحركة كغير مسعّرة وسيُطلب تسعيرها لاحقًا.')

        return True

    def apply_to(self, xt):
        xt.product_id = to_int(self.product_id.data)
        xt.warehouse_id = to_int(self.warehouse_id.data)
        xt.partner_id = to_int(self.partner_id.data) if self.partner_id.data else None
        xt.direction = (self.direction.data or '').upper()
        xt.quantity = to_int(self.quantity.data) or 1
        uc = to_dec(self.unit_cost.data)
        xt.unit_cost = uc if (uc is not None and uc > 0) else None
        xt.is_priced = bool(xt.unit_cost)
        xt.notes = (self.notes.data or '').strip() or None
        return xt

class EquipmentTypeForm(FlaskForm):
    name = StrippedStringField('اسم نوع المعدة', validators=[DataRequired(), Length(max=100)])
    model_number = StrippedStringField('رقم النموذج', validators=[Optional(), Length(max=100)])
    chassis_number = StrippedStringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    category = StrippedStringField('الفئة', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ نوع المعدة')

class ServiceTaskForm(FlaskForm):
    class Meta: csrf = False
    service_id = HiddenField(validators=[DataRequired()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    description = StrippedStringField('وصف المهمة', validators=[DataRequired(), Length(max=200)])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = MoneyField('سعر الوحدة', validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StrippedStringField('ملاحظات', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ المهمة')
    def apply_to(self, task):
        task.service_id = int(self.service_id.data) if self.service_id.data else None
        task.partner_id = int(self.partner_id.data) if self.partner_id.data else None
        task.share_percentage = self.share_percentage.data or None
        task.description = (self.description.data or '').strip()
        task.quantity = int(self.quantity.data or 0)
        task.unit_price = self.unit_price.data or 0
        task.discount = self.discount.data or 0
        task.tax_rate = self.tax_rate.data or 0
        task.note = (self.note.data or '').strip() or None
        return task

class ServiceDiagnosisForm(FlaskForm):
    problem_description = TextAreaField('المشكلة', validators=[DataRequired()])
    diagnosis = TextAreaField('السبب', validators=[DataRequired()])
    resolution = TextAreaField('الحل المقترح', validators=[DataRequired()])
    estimated_duration = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost = MoneyField('التكلفة المتوقعة', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('حفظ التشخيص')
    def apply_to(self, diag):
        diag.problem_description = (self.problem_description.data or '').strip()
        diag.diagnosis = (self.diagnosis.data or '').strip()
        diag.resolution = (self.resolution.data or '').strip()
        diag.estimated_duration = int(self.estimated_duration.data or 0) if self.estimated_duration.data else None
        diag.estimated_cost = self.estimated_cost.data or None
        return diag

class ServicePartForm(FlaskForm):
    class Meta: csrf = False
    service_id = HiddenField(validators=[Optional()])
    part_id = AjaxSelectField('القطعة/المكوّن', endpoint=None, get_label='name', validators=[DataRequired()], render_kw={"data-endpoint-by-warehouse":"/api/warehouses/0/products","data-product-info":"/api/products/0/info"})
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = MoneyField('سعر الوحدة', validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StrippedStringField('ملاحظة قصيرة', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ')
    def apply_to(self, sp):
        sp.service_id = int(self.service_id.data) if self.service_id.data else None
        sp.part_id = int(self.part_id.data) if self.part_id.data else None
        sp.warehouse_id = int(self.warehouse_id.data) if self.warehouse_id.data else None
        sp.quantity = int(self.quantity.data or 0)
        sp.unit_price = self.unit_price.data or 0
        sp.discount = self.discount.data or 0
        sp.tax_rate = self.tax_rate.data or 0
        sp.note = (self.note.data or '').strip() or None
        sp.notes = (self.notes.data or '').strip() or None
        return sp
    
class SaleLineForm(FlaskForm):
    class Meta:
        csrf = False
    sale_id       = HiddenField(validators=[Optional()])
    product_id    = AjaxSelectField('الصنف', endpoint='api.search_products', get_label='name', coerce=int, validators=[Optional()])
    warehouse_id  = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', coerce=int, validators=[Optional()])
    quantity      = IntegerField('الكمية', validators=[Optional(), NumberRange(min=1)])
    unit_price = MoneyField('سعر الوحدة', validators=[Optional(), NumberRange(min=0)])
    discount_rate = DecimalField('خصم %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate      = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    note          = StrippedStringField('ملاحظات', validators=[Optional(), Length(max=200)])

class SaleForm(FlaskForm):
    sale_number    = StrippedStringField('رقم البيع', validators=[Optional(), Length(max=50)])
    sale_date = UnifiedDateTimeField(
        'تاريخ البيع',
        format='%Y-%m-%d %H:%M',
        formats=['%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M'],
        validators=[Optional()],
        render_kw={'type':'datetime-local', 'step':'60'}
    )
    customer_id    = AjaxSelectField('العميل', endpoint='api.search_customers', get_label='name', coerce=int, validators=[DataRequired()])
    seller_id      = AjaxSelectField('البائع', endpoint='api.search_users', get_label='username', coerce=int, validators=[DataRequired()])
    status         = SelectField('الحالة', choices=[
        (SaleStatus.DRAFT.value, 'مسودة'),
        (SaleStatus.CONFIRMED.value, 'مؤكد'),
        (SaleStatus.CANCELLED.value, 'ملغي'),
        (SaleStatus.REFUNDED.value, 'مرتجع')
    ], default=SaleStatus.DRAFT.value, validators=[DataRequired()])
    payment_status = SelectField('حالة السداد', choices=[
        (PaymentProgress.PENDING.value, 'PENDING'),
        (PaymentProgress.PARTIAL.value, 'PARTIAL'),
        (PaymentProgress.PAID.value, 'PAID'),
        (PaymentProgress.REFUNDED.value, 'REFUNDED')
    ], default=PaymentProgress.PENDING.value, validators=[DataRequired()])
    currency         = SelectField('عملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    tax_rate         = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    discount_total = MoneyField('خصم إجمالي', validators=[Optional(), NumberRange(min=0)], default=0)
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=500)])
    billing_address  = TextAreaField('عنوان الفواتير', validators=[Optional(), Length(max=500)])
    shipping_cost = MoneyField('تكلفة الشحن', validators=[Optional(), NumberRange(min=0)], default=0)
    notes            = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    total_amount = MoneyField('الإجمالي النهائي', validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    lines            = FieldList(FormField(SaleLineForm), min_entries=1)
    preorder_id      = IntegerField('رقم الحجز', validators=[Optional()])
    submit           = SubmitField('حفظ البيع')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        ok = any(
            f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1 and (f.unit_price.data or 0) >= 0
            for f in (entry.form for entry in self.lines)
        )
        if not ok:
            self.lines.errors.append('❌ أضف بندًا واحدًا على الأقل ببيانات صحيحة.')
            return False
        return True

    def apply_to(self, sale):
        sale.sale_number      = (self.sale_number.data or '').strip() or sale.sale_number
        sale.sale_date        = self.sale_date.data or sale.sale_date
        sale.customer_id      = int(self.customer_id.data) if self.customer_id.data else None
        sale.seller_id        = int(self.seller_id.data) if self.seller_id.data else None
        sale.preorder_id      = int(self.preorder_id.data) if self.preorder_id.data else None
        sale.status = (self.status.data or SaleStatus.DRAFT.value)
        sale.payment_status   = (self.payment_status.data or PaymentProgress.PENDING.value)
        sale.currency         = (self.currency.data or 'ILS').upper()
        sale.tax_rate         = self.tax_rate.data or 0
        sale.discount_total   = self.discount_total.data or 0
        sale.shipping_address = (self.shipping_address.data or '').strip() or None
        sale.billing_address  = (self.billing_address.data or '').strip() or None
        sale.shipping_cost    = self.shipping_cost.data or 0
        sale.notes            = (self.notes.data or '').strip() or None

        valid_line_forms = [
            f for f in (entry.form for entry in self.lines)
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1
        ]
        sale.lines = [
            SaleLine(
                product_id=int(f.product_id.data),
                warehouse_id=int(f.warehouse_id.data),
                quantity=int(f.quantity.data),
                unit_price=f.unit_price.data or 0,
                discount_rate=f.discount_rate.data or 0,
                tax_rate=f.tax_rate.data or 0,
                note=(f.note.data or '').strip() or None
            )
            for f in valid_line_forms
        ]

        lines_total = D(0)
        for f in valid_line_forms:
            qty   = D(f.quantity.data)
            price = D(f.unit_price.data or 0)
            disc  = D(f.discount_rate.data or 0)
            line_base = qty * price * (D(1) - (disc / D(100)))
            lines_total += line_base

        subtotal = lines_total
        subtotal_after_discount = subtotal - D(self.discount_total.data or 0)
        if subtotal_after_discount < D(0):
            subtotal_after_discount = D(0)
        sale_tax_rate = D(self.tax_rate.data or 0)
        after_sale_tax = subtotal_after_discount * (D(1) + sale_tax_rate / D(100))
        grand_total = after_sale_tax + D(self.shipping_cost.data or 0)

        if grand_total < D(0):
            grand_total = D(0)
        sale.total_amount = Q2(grand_total)
        return sale

def _norm_invoice_no(v: str | None) -> str | None:
    s = (v or "").strip()
    s = re.sub(r"\s+", "", s)
    return s.upper() or None

class InvoiceLineForm(FlaskForm):
    class Meta:
        csrf = False
    invoice_id  = HiddenField(validators=[Optional()])
    product_id  = AjaxSelectField('الصنف', endpoint='api.search_products', get_label='name', coerce=int, validators=[DataRequired()])
    description = StrippedStringField('الوصف', validators=[DataRequired(), Length(max=200)])
    quantity    = DecimalField('الكمية', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    unit_price = MoneyField('سعر الوحدة', validators=[DataRequired(), NumberRange(min=0)])
    tax_rate    = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    discount    = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])

class InvoiceForm(FlaskForm):
    id = HiddenField()
    invoice_number = StringField("رقم الفاتورة", validators=[DataRequired(), Length(max=50)])
    invoice_date = UnifiedDateTimeField("تاريخ الفاتورة", default=datetime.utcnow, validators=[DataRequired()], render_kw={"type":"datetime-local","step":"60"})
    due_date = UnifiedDateTimeField("تاريخ الاستحقاق", validators=[Optional()], render_kw={"type":"datetime-local","step":"60"})
    customer_id = AjaxSelectField("العميل", coerce=int, allow_blank=True)
    supplier_id = AjaxSelectField("المورد", coerce=int, allow_blank=True)
    partner_id = AjaxSelectField("الشريك", coerce=int, allow_blank=True)
    sale_id = AjaxSelectField("البيع", coerce=int, allow_blank=True)
    service_id = AjaxSelectField("طلب الصيانة", coerce=int, allow_blank=True)
    preorder_id = AjaxSelectField("الطلب المسبق", coerce=int, allow_blank=True)
    source = SelectField("المصدر", choices=[(e.value,e.value) for e in InvoiceSource], validators=[DataRequired()])
    status = SelectField("الحالة", choices=[(e.value,e.value) for e in InvoiceStatus], validators=[DataRequired()])
    currency = StringField("العملة", default="ILS", validators=[DataRequired(), Length(max=10)])
    total_amount = MoneyField("المجموع", validators=[DataRequired(), NumberRange(min=0)])
    tax_amount = MoneyField("الضريبة", validators=[Optional(), NumberRange(min=0)])
    discount_amount = MoneyField("الخصم", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("ملاحظات", validators=[Optional()])
    terms = TextAreaField("الشروط", validators=[Optional()])
    lines = FieldList(FormField(InvoiceLineForm), min_entries=1)
    submit = SubmitField("حفظ")


class ProductPartnerForm(FlaskForm):
    id = HiddenField()
    product_id = AjaxSelectField("المنتج", endpoint="api.search_products", get_label="name", coerce=int, validators=[DataRequired()])
    partner_id = AjaxSelectField("الشريك", endpoint="api.search_partners", get_label="name", coerce=int, validators=[DataRequired()])
    share_percent = DecimalField("نسبة الشريك %", places=3, default=0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    share_amount = MoneyField("حصة الشريك", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("حفظ")

class ProductPartnerShareForm(FlaskForm):
    product_id = HiddenField(validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()])
    share_percentage = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount = MoneyField('قيمة مساهمة الشريك', validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        sp = self.share_percentage.data
        sa = self.share_amount.data
        if (sp in (None, '') or float(sp or 0) == 0) and (sa in (None, '') or float(sa or 0) == 0):
            self.share_percentage.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            self.share_amount.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            return False
        return True
class WarehousePartnerShareForm(FlaskForm):
    id = HiddenField()
    partner_id   = AjaxSelectField("الشريك",   endpoint="api.search_partners",  get_label="name", coerce=int, validators=[DataRequired()])
    warehouse_id = AjaxSelectField("المستودع", endpoint="api.search_warehouses", get_label="name", coerce=int, allow_blank=True)
    product_id   = AjaxSelectField("المنتج",   endpoint="api.search_products",  get_label="name", coerce=int, allow_blank=True)
    share_percentage = DecimalField("نسبة الشريك %", places=3, default=0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    share_amount     = MoneyField("حصة الشريك", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("ملاحظات", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("حفظ")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok: return False

        if not self.product_id.data and not self.warehouse_id.data:
            msg = "❌ اختر منتجًا أو مستودعًا واحدًا على الأقل."
            self.product_id.errors.append(msg); self.warehouse_id.errors.append(msg)
            ok = False

        pct = Decimal(str(self.share_percentage.data or "0"))
        amt = Decimal(str(self.share_amount.data or "0"))
        if pct <= 0 and amt <= 0:
            self.share_percentage.errors.append("❌ أدخل نسبة > 0 أو مبلغًا > 0.")
            ok = False

        try:
            pid = int(self.partner_id.data) if self.partner_id.data else None
            wid = int(self.warehouse_id.data) if self.warehouse_id.data else None
            prd = int(self.product_id.data) if self.product_id.data else None
            q = WarehousePartnerShare.query.filter_by(partner_id=pid, warehouse_id=wid, product_id=prd)
            if self.id.data:
                q = q.filter(WarehousePartnerShare.id != int(self.id.data))
            if q.first():
                self.product_id.errors.append("❌ يوجد سجل لنفس (الشريك/المستودع/المنتج).")
                ok = False
        except Exception:
            pass

        return ok


class ProductCategoryForm(FlaskForm):
    name = StrippedStringField('اسم الفئة', validators=[DataRequired(), Length(max=100)])
    parent_id = AjaxSelectField('الفئة الأب', endpoint='api.search_categories', get_label='name', validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    image_url = StrippedStringField('رابط الصورة', validators=[Optional()])
    is_active = BooleanField('نشطة', default=True)
    submit = SubmitField('حفظ الفئة')


class ImportForm(FlaskForm):
    warehouse_id = AjaxSelectField('المستودع', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    file = FileField('ملف المنتجات (CSV/XLSX)', validators=[DataRequired(), FileAllowed(['csv', 'xlsx', 'xls'])])
    duplicate_strategy = SelectField('سياسة التكرار', choices=[
        ('skip', 'تخطي المكررات'),
        ('update_product', 'تحديث المنتج عند التطابق'),
        ('stock_only', 'تحديث المخزون فقط')
    ], validators=[DataRequired()])
    dry_run = BooleanField('فحص فقط (بدون ترحيل)', default=True)
    continue_after_warnings = BooleanField('المتابعة رغم التحذيرات', default=False)
    submit = SubmitField('متابعة')

class ProductForm(FlaskForm):
    id = HiddenField()
    sku = StrippedStringField('SKU', validators=[
        Optional(), Length(max=50),
        Unique(Product, 'sku', message='SKU مستخدم بالفعل.', case_insensitive=True,
               normalizer=lambda v: (v or '').strip().upper())
    ])
    name = StrippedStringField('الاسم', validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('الوصف', validators=[Optional()])
    part_number = StrippedStringField('رقم القطعة', validators=[Optional(), Length(max=100)])
    brand = StrippedStringField('الماركة', validators=[Optional(), Length(max=100)])
    commercial_name = StrippedStringField('الاسم التجاري', validators=[Optional(), Length(max=100)])
    chassis_number = StrippedStringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    serial_no = StrippedStringField('الرقم التسلسلي', validators=[
        Optional(), Length(max=100),
        Unique(Product, 'serial_no', message='الرقم التسلسلي مستخدم بالفعل.', case_insensitive=True,
               normalizer=lambda v: (v or '').strip().upper())
    ])
    barcode = StrippedStringField('الباركود', validators=[
        Optional(), Length(max=100),
        Unique(Product, 'barcode', message='الباركود مستخدم بالفعل.', case_insensitive=True,
               normalizer=normalize_barcode)
    ])
    cost_before_shipping = MoneyField('التكلفة قبل الشحن', validators=[Optional(), NumberRange(min=0)])
    cost_after_shipping  = MoneyField('التكلفة بعد الشحن', validators=[Optional(), NumberRange(min=0)])
    unit_price_before_tax= MoneyField('سعر الوحدة قبل الضريبة', validators=[Optional(), NumberRange(min=0)])
    price         = MoneyField('السعر الأساسي', validators=[DataRequired(), NumberRange(min=0)])
    purchase_price= MoneyField('سعر الشراء', validators=[Optional(), NumberRange(min=0)])
    selling_price = MoneyField('سعر البيع', validators=[Optional(), NumberRange(min=0)])
    min_price     = MoneyField('السعر الأدنى', validators=[Optional(), NumberRange(min=0)])
    max_price     = MoneyField('السعر الأعلى', validators=[Optional(), NumberRange(min=0)])
    online_price  = MoneyField('سعر المتجر الإلكتروني', validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('نسبة الضريبة', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    unit = StrippedStringField('الوحدة', validators=[Optional(), Length(max=50)])
    min_qty = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    reorder_point = IntegerField('نقطة إعادة الطلب', validators=[Optional(), NumberRange(min=0)])
    condition = SelectField('الحالة', choices=[
        (ProductCondition.NEW.value, 'جديد'),
        (ProductCondition.USED.value, 'مستعمل'),
        (ProductCondition.REFURBISHED.value, 'مجدّد'),
    ], validators=[DataRequired()])
    origin_country = StrippedStringField('بلد المنشأ', validators=[Optional(), Length(max=50)])
    warranty_period = IntegerField('مدة الضمان', validators=[Optional(), NumberRange(min=0)])
    weight = DecimalField('الوزن', places=2, validators=[Optional(), NumberRange(min=0)])
    dimensions = StrippedStringField('الأبعاد', validators=[Optional(), Length(max=50)])
    image = StrippedStringField('صورة', validators=[Optional(), Length(max=255)])
    online_name  = StrippedStringField('اسم المتجر الإلكتروني', validators=[Optional(), Length(max=255)])
    online_image = StrippedStringField('صورة المتجر الإلكتروني', validators=[Optional(), Length(max=255)])
    is_active   = BooleanField('نشط', default=True)
    is_digital  = BooleanField('منتج رقمي', default=False)
    is_exchange = BooleanField('قابل للتبادل', default=False)
    vehicle_type_id = AjaxSelectField('نوع المركبة', endpoint='api.search_equipment_types',
                                      get_label='name', validators=[Optional()], coerce=int)
    category_id = AjaxSelectField('الفئة', endpoint='api.search_categories', get_label='name',
                                  coerce=int, validators=[DataRequired(message="يجب اختيار فئة للمنتج")],
                                  render_kw={'required': True})
    category_name = StrippedStringField('اسم الفئة (نصي)', validators=[Optional(), Length(max=100)])
    supplier_id = AjaxSelectField('المورد الرئيسي', endpoint='api.search_suppliers',
                                  get_label='name', validators=[Optional()], coerce=int)
    supplier_international_id = AjaxSelectField('المورد الدولي', endpoint='api.search_suppliers',
                                  get_label='name', validators=[Optional()], coerce=int)
    supplier_local_id = AjaxSelectField('المورد المحلي', endpoint='api.search_suppliers',
                                  get_label='name', validators=[Optional()], coerce=int)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ')

    @staticmethod
    def _ival(v):
        try: return int(v) if v is not None else None
        except Exception: return None

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators): return False
        if not self.category_id.data:
            self.category_id.errors.append("يجب اختيار فئة للمنتج"); return False
        pp, pr, sp, op = self.purchase_price.data, self.price.data, self.selling_price.data, self.online_price.data
        mn, mx = self.min_price.data, self.max_price.data
        if sp is None and pr is not None:
            sp = pr; self.selling_price.data = sp
        if pr is None and sp is not None:
            pr = sp; self.price.data = pr
        if mn is not None and mx is not None and mn > mx:
            self.max_price.errors.append('السعر الأعلى يجب أن يكون ≥ السعر الأدنى.'); return False
        if pp is not None:
            if pr is not None and pr < pp: self.price.errors.append('السعر الأساسي لا يجب أن يكون أقل من سعر الشراء.'); return False
            if sp is not None and sp < pp: self.selling_price.errors.append('سعر البيع لا يجب أن يكون أقل من سعر الشراء.'); return False
            if op is not None and op < pp: self.online_price.errors.append('سعر المتجر الإلكتروني لا يجب أن يكون أقل من سعر الشراء.'); return False
        if mn is not None:
            if pr is not None and pr < mn: self.price.errors.append('السعر الأساسي أقل من السعر الأدنى.'); return False
            if sp is not None and sp < mn: self.selling_price.errors.append('سعر البيع أقل من السعر الأدنى.'); return False
            if op is not None and op < mn: self.online_price.errors.append('سعر المتجر الإلكتروني أقل من السعر الأدنى.'); return False
        if mx is not None:
            if pr is not None and pr > mx: self.price.errors.append('السعر الأساسي أعلى من السعر الأعلى.'); return False
            if sp is not None and sp > mx: self.selling_price.errors.append('سعر البيع أعلى من السعر الأعلى.'); return False
            if op is not None and op > mx: self.online_price.errors.append('سعر المتجر الإلكتروني أعلى من السعر الأعلى.'); return False
        rq, mq = self.reorder_point.data, self.min_qty.data
        if rq is not None and mq is not None and rq < mq:
            self.reorder_point.errors.append('نقطة إعادة الطلب يجب أن تكون ≥ الحد الأدنى للمخزون.'); return False
        return True

    def validate_barcode(self, field):
        if not field.data: return
        r = validate_barcode(field.data)
        if not r["normalized"]: raise ValidationError("الباركود يجب أن يكون 12 أو 13 خانة رقمية.")
        if not r["valid"]:
            if r.get("suggested"): raise ValidationError(f"الباركود غير صالح. المُقترَح الصحيح: {r['suggested']}")
            raise ValidationError("الباركود غير صالح.")
        field.data = r["normalized"]

    def _clean_image(self, v):
        if not v: return None
        s = (v or "").strip()
        if not s: return None
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"): return s
        try:
            import os
            return os.path.basename(s)
        except Exception:
            return s

    def apply_to(self, p: Product) -> Product:
        p.sku             = ((self.sku.data or '').strip() or None)
        p.sku             = (p.sku.upper() if p.sku else None)
        p.name            = (self.name.data or '').strip()
        p.description     = (self.description.data or '').strip() or None
        pn                = (self.part_number.data or '').strip() or None
        p.part_number     = (pn.upper() if pn else None)
        p.brand           = (self.brand.data or '').strip() or None
        p.commercial_name = (self.commercial_name.data or '').strip() or None
        p.chassis_number  = (self.chassis_number.data or '').strip() or None
        sn                = (self.serial_no.data or '').strip() or None
        p.serial_no       = (sn.upper() if sn else None)
        p.barcode         = (self.barcode.data or '').strip() or None
        p.cost_before_shipping  = self.cost_before_shipping.data or 0
        p.cost_after_shipping   = self.cost_after_shipping.data or 0
        p.unit_price_before_tax = self.unit_price_before_tax.data or 0
        base_price = self.price.data
        sell_price = self.selling_price.data or base_price
        if base_price is None and sell_price is not None: base_price = sell_price
        p.price          = base_price or 0
        p.selling_price  = sell_price or 0
        p.purchase_price = self.purchase_price.data or 0
        p.min_price      = self.min_price.data or None
        p.max_price      = self.max_price.data or None
        p.tax_rate       = self.tax_rate.data or 0
        p.unit           = (self.unit.data or '').strip() or None
        p.min_qty        = self._ival(self.min_qty.data) or 0
        p.reorder_point  = self._ival(self.reorder_point.data)
        p.condition      = self.condition.data or ProductCondition.NEW.value
        p.origin_country = (self.origin_country.data or '').strip() or None
        p.warranty_period= self._ival(self.warranty_period.data)
        p.weight         = self.weight.data or None
        p.dimensions     = (self.dimensions.data or '').strip() or None
        p.image        = self._clean_image(self.image.data)
        p.online_name  = (self.online_name.data or '').strip() or None
        p.online_price = self.online_price.data if self.online_price.data is not None else None
        p.online_image = self._clean_image(self.online_image.data)
        p.is_active   = bool(self.is_active.data)
        p.is_digital  = bool(self.is_digital.data)
        p.is_exchange = bool(self.is_exchange.data)
        p.vehicle_type_id           = self._ival(self.vehicle_type_id.data)
        p.category_id               = self._ival(self.category_id.data)
        p.category_name             = (self.category_name.data or '').strip() or None
        p.supplier_id               = self._ival(self.supplier_id.data)
        p.supplier_international_id = self._ival(self.supplier_international_id.data)
        p.supplier_local_id         = self._ival(self.supplier_local_id.data)
        p.notes = (self.notes.data or '').strip() or None
        return p

class CheckoutForm(FlaskForm):
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=500)])
    billing_address  = TextAreaField('عنوان الفواتير', validators=[Optional(), Length(max=500)])
    transaction_data = HiddenField()  

class WarehouseForm(FlaskForm):
    id = HiddenField(validators=[Optional()])
    name = StrippedStringField('اسم المستودع', validators=[DataRequired(), Length(max=100)])
    warehouse_type = SelectField('نوع المستودع', choices=[(t.value, t.value) for t in WarehouseType], validators=[DataRequired()], coerce=str)
    location = StrippedStringField('الموقع', validators=[Optional(), Length(max=200)])
    parent_id = AjaxSelectField('المستودع الأب', endpoint='api.search_warehouses', get_label='name', validators=[Optional()], coerce=int)
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()], coerce=int)
    supplier_id = AjaxSelectField('المورد', endpoint='api.search_suppliers', get_label='name', validators=[Optional()], coerce=int)
    share_percent = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    capacity = IntegerField('السعة القصوى', validators=[Optional(), NumberRange(min=0)])
    current_occupancy = IntegerField('المشغول حاليًا', validators=[Optional(), NumberRange(min=0)])
    online_slug = StrippedStringField('معرّف الأونلاين', validators=[Optional(), Length(max=150)])
    online_is_default = BooleanField('المستودع الافتراضي للأونلاين', default=False)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    is_active = BooleanField('نشط', default=True)
    submit = SubmitField('حفظ المستودع')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        cap = self.capacity.data
        occ = self.current_occupancy.data
        if cap is not None and occ is not None and occ > cap:
            self.current_occupancy.errors.append('المشغول حاليًا لا يمكن أن يتجاوز السعة القصوى.')
            return False

        wt = (self.warehouse_type.data or '').strip().upper()
        if wt != 'PARTNER':
            if self.share_percent.data is None:
                self.share_percent.data = 0
        if wt == 'PARTNER' and not self.partner_id.data:
            self.partner_id.errors.append('يجب اختيار شريك لمستودع الشريك.')
            return False
        if wt == 'EXCHANGE' and not self.supplier_id.data:
            self.supplier_id.errors.append('مستودع التسوية يتطلب موردًا.')
            return False
        if wt == 'ONLINE':
            self.partner_id.data = None
            self.supplier_id.data = None
            slug = (self.online_slug.data or '').strip()
            if slug:
                try:
                    cur_id = to_int(self.id.data) if self.id.data else None
                    q = Warehouse.query.filter(Warehouse.warehouse_type == WarehouseType.ONLINE.value, Warehouse.online_slug == slug)
                    if cur_id:
                        q = q.filter(Warehouse.id != cur_id)
                    if q.first():
                        self.online_slug.errors.append('المعرّف مستخدم بالفعل.')
                        return False
                except Exception:
                    pass
            if bool(self.online_is_default.data):
                try:
                    cur_id = to_int(self.id.data) if self.id.data else None
                    q = Warehouse.query.filter(Warehouse.warehouse_type == WarehouseType.ONLINE.value, Warehouse.online_is_default.is_(True))
                    if cur_id:
                        q = q.filter(Warehouse.id != cur_id)
                    if q.first():
                        self.online_is_default.errors.append('يوجد مستودع أونلاين افتراضي واحد بالفعل.')
                        return False
                except Exception:
                    pass
        else:
            self.online_is_default.data = False
            if (self.online_slug.data or '').strip():
                self.online_slug.errors.append('هذا الحقل متاح لمستودع الأونلاين فقط.')
                return False

        pid = to_int(self.parent_id.data) if self.parent_id.data else None
        cur_id = to_int(self.id.data) if self.id.data else None
        if pid and cur_id and pid == cur_id:
            self.parent_id.errors.append('لا يمكن اختيار المستودع الأب نفسه.')
            return False

        return True

    def apply_to(self, w):
        w.name = (self.name.data or '').strip()
        w.warehouse_type = (self.warehouse_type.data or '').strip().upper()
        w.location = (self.location.data or '').strip() or None
        w.parent_id = to_int(self.parent_id.data) if self.parent_id.data else None
        w.partner_id = to_int(self.partner_id.data) if self.partner_id.data else None
        w.supplier_id = to_int(self.supplier_id.data) if self.supplier_id.data else None
        w.share_percent = self.share_percent.data or 0
        w.capacity = self.capacity.data or None
        w.current_occupancy = self.current_occupancy.data or None
        w.online_slug = (self.online_slug.data or '').strip() or None
        w.online_is_default = bool(self.online_is_default.data) if w.warehouse_type == 'ONLINE' else False
        w.notes = (self.notes.data or '').strip() or None
        w.is_active = bool(self.is_active.data)
        return w

class PartnerShareForm(FlaskForm):
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()], coerce=int)
    share_percentage = DecimalField('نسبة المشاركة (%)', places=2, validators=[DataRequired(), NumberRange(min=0, max=100)])
    partner_phone = StrippedStringField('هاتف الشريك', validators=[Optional(), Length(max=20)])
    partner_identity = StrippedStringField('هوية الشريك', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ')


class ExchangeVendorForm(FlaskForm):
    supplier_id = AjaxSelectField('المورّد / التاجر', endpoint='api.search_suppliers', get_label='name', validators=[DataRequired()])
    vendor_phone = StrippedStringField('هاتف المورد', validators=[Optional(), Length(max=50)])
    vendor_paid = MoneyField('المبلغ المدفوع', validators=[Optional(), NumberRange(min=0)])
    vendor_price = MoneyField('سعر المورد', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('حفظ')


class StockLevelForm(FlaskForm):
    id = HiddenField()
    product_id = AjaxSelectField('الصنف', endpoint='api.search_products', get_label='name', validators=[Optional()], coerce=int)
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()], coerce=int)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=0)])
    reserved_quantity = IntegerField('محجوز', validators=[Optional(), NumberRange(min=0)], default=0)
    min_stock = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    max_stock = IntegerField('الحد الأقصى', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('حفظ')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        qty = to_int(self.quantity.data) or 0
        rq = to_int(self.reserved_quantity.data) or 0
        if rq > qty:
            self.reserved_quantity.errors.append('المحجوز لا يجوز أن يتجاوز الكمية.')
            return False
        mn = to_int(self.min_stock.data) if self.min_stock.data not in (None, "") else None
        mx = to_int(self.max_stock.data) if self.max_stock.data not in (None, "") else None
        if mn is not None and mx is not None and mx < mn:
            self.max_stock.errors.append('الحد الأقصى يجب أن يكون ≥ الحد الأدنى.')
            return False
        pid = to_int(self.product_id.data)
        wid = to_int(self.warehouse_id.data)
        if not pid or not wid:
            return False
        try:
            from models import StockLevel
            existing = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
            cur_id = to_int(self.id.data) if self.id.data else None
            if existing and (cur_id is None or existing.id != cur_id):
                self.warehouse_id.errors.append('يوجد صف مخزون لنفس الصنف والمخزن.')
                return False
        except Exception:
            pass
        return True

    def apply_to(self, sl):
        sl.product_id = to_int(self.product_id.data)
        sl.warehouse_id = to_int(self.warehouse_id.data)
        sl.quantity = to_int(self.quantity.data) or 0
        sl.reserved_quantity = to_int(self.reserved_quantity.data) or 0
        sl.min_stock = to_int(self.min_stock.data) if self.min_stock.data not in (None, "") else None
        sl.max_stock = to_int(self.max_stock.data) if self.max_stock.data not in (None, "") else None
        return sl


class InventoryAdjustmentForm(FlaskForm):
    product_id = AjaxSelectField('المنتج', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    adjustment_type = SelectField('نوع التعديل', choices=[('IN', 'إضافة'), ('OUT', 'إزالة'), ('ADJUSTMENT', 'تصحيح')], default='ADJUSTMENT', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('السبب', validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField('تطبيق التعديل')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        dirv = (self.adjustment_type.data or '').upper()
        if dirv == 'OUT':
            pid = to_int(self.product_id.data)
            wid = to_int(self.warehouse_id.data)
            qty = to_int(self.quantity.data) or 0
            if pid and wid and qty:
                try:
                    from models import StockLevel
                    sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
                    avail = (sl.quantity if sl else 0) - (sl.reserved_quantity if sl else 0)
                    if qty > max(int(avail or 0), 0):
                        self.quantity.errors.append('❌ الكمية غير كافية في هذا المخزن.')
                        return False
                except Exception:
                    pass
        return True

class NoteForm(FlaskForm):
    author_id   = HiddenField(validators=[Optional()])
    content     = TextAreaField('المحتوى', validators=[DataRequired(), Length(max=1000)])
    entity_type = SelectField(
        'نوع الكيان',
        choices=[
            ('', '— لا شيء —'),
            ('CUSTOMER', 'عميل'),
            ('SUPPLIER', 'مورد'),
            ('PARTNER', 'شريك'),
            ('PRODUCT', 'منتج'),
            ('SALE', 'بيع'),
            ('INVOICE', 'فاتورة'),
            ('SERVICE', 'خدمة'),
            ('SHIPMENT', 'شحنة'),
        ],
        validators=[Optional()],
        default=''
    )
    entity_id   = StrippedStringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    is_pinned   = BooleanField('مثبّتة', default=False)
    priority    = SelectField(
        'الأولوية',
        choices=[('LOW', 'منخفضة'), ('MEDIUM', 'متوسطة'), ('HIGH', 'عالية'), ('URGENT', 'عاجلة')],
        default='MEDIUM',
        validators=[DataRequired()]
    )
    submit      = SubmitField('حفظ')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        eid = (self.entity_id.data or "").strip()
        if eid and not re.match(r"^\d+$", eid):
            self.entity_id.errors.append("معرّف الكيان يجب أن يكون رقمًا صحيحًا.")
            return False
        return True

    def apply_to(self, note_obj):
        note_obj.author_id  = int(self.author_id.data) if (self.author_id.data or '').strip().isdigit() else None
        note_obj.content    = (self.content.data or '').strip()
        et                  = (self.entity_type.data or '').strip().upper()
        note_obj.entity_type = et or None
        note_obj.entity_id   = int(self.entity_id.data) if (self.entity_id.data or '').strip().isdigit() else None
        note_obj.is_pinned   = bool(self.is_pinned.data)
        note_obj.priority    = (self.priority.data or 'MEDIUM').upper()
        return note_obj
    
class AccountForm(FlaskForm):
    id = HiddenField()
    code = StrippedStringField('كود الحساب', validators=[
        DataRequired(),
        Length(max=20),
        Unique(Account, 'code', message='الكود مستخدم مسبقًا', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())
    ])
    name = StrippedStringField('اسم الحساب', validators=[DataRequired(), Length(max=100)])
    type = SelectField('النوع', validators=[DataRequired()], choices=[(t.value, t.value) for t in AccountType])
    parent_id = AjaxSelectField('الحساب الأب', endpoint='api.search_accounts', get_label='name', allow_blank=True, validators=[Optional()])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[DataRequired()])
    is_active = BooleanField('نشط', default=True)
    opening_balance = MoneyField('الرصيد الافتتاحي', validators=[Optional(), NumberRange(min=0)])
    opening_balance_date = DateField('تاريخ الرصيد الافتتاحي', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ الحساب')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        cur_id = to_int(self.id.data)
        pid = to_int(self.parent_id.data)
        if cur_id and pid and cur_id == pid:
            self.parent_id.errors.append('لا يمكن تعيين الحساب كأب لنفسه.')
            return False
        return True

    def apply_to(self, acc: Account) -> Account:
        acc.code = (self.code.data or '').strip().upper()
        acc.name = (self.name.data or '').strip()
        acc.type = (self.type.data or '').strip()
        acc.parent_id = int(self.parent_id.data) if self.parent_id.data else None
        acc.currency = self.currency.data
        acc.is_active = bool(self.is_active.data)
        acc.opening_balance = self.opening_balance.data or 0
        acc.opening_balance_date = self.opening_balance_date.data or None
        acc.notes = (self.notes.data or '').strip() or None
        return acc


class JournalLineForm(FlaskForm):
    class Meta: csrf = False
    account_id = AjaxSelectField('الحساب', endpoint='api.search_accounts', get_label='name', validators=[DataRequired()])
    debit = MoneyField('مدين', validators=[Optional(), NumberRange(min=0)])
    credit = MoneyField('دائن', validators=[Optional(), NumberRange(min=0)])
    entity_type = SelectField('نوع الكيان', choices=[('', '—'), ('CUSTOMER', 'CUSTOMER'), ('SUPPLIER', 'SUPPLIER'), ('PARTNER', 'PARTNER'), ('INVOICE', 'INVOICE'), ('SALE', 'SALE'), ('EXPENSE', 'EXPENSE'), ('SERVICE', 'SERVICE')], validators=[Optional()])
    entity_id = StrippedStringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    note = StrippedStringField('ملاحظة', validators=[Optional(), Length(max=200)])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        db_amt = D(self.debit.data)
        cr_amt = D(self.credit.data)
        if db_amt <= 0 and cr_amt <= 0:
            self.debit.errors.append('أدخل مبلغًا في المدين أو الدائن')
            return False
        if db_amt > 0 and cr_amt > 0:
            self.credit.errors.append('لا يجوز أن يكون السطر مدينًا ودائنًا معًا')
            return False
        if (self.entity_id.data or '').strip() and not (self.entity_type.data or '').strip():
            self.entity_type.errors.append('حدد نوع الكيان')
            return False
        eid = (self.entity_id.data or '').strip()
        if eid and not re.match(r'^\d+$', eid):
            self.entity_id.errors.append('معرّف الكيان يجب أن يكون رقمًا صحيحًا.')
            return False
        return True
    
class JournalEntryForm(FlaskForm):
    entry_date = DateTimeLocalField('تاريخ القيد', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    reference = StrippedStringField('المرجع', validators=[Optional(), Length(max=50)])
    description = TextAreaField('البيان', validators=[Optional(), Length(max=1000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[DataRequired()])
    post_now = BooleanField('ترحيل فورًا', default=True)
    lines = FieldList(FormField(JournalLineForm), min_entries=2)
    submit = SubmitField('حفظ القيد')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        used = [lf for lf in self.lines if (D(lf.form.debit.data) > 0) or (D(lf.form.credit.data) > 0)]
        if not used:
            self.lines.errors.append('❌ أضف سطرًا واحدًا على الأقل')
            return False
        total_debit = sum(D(f.form.debit.data) for f in used)
        total_credit = sum(D(f.form.credit.data) for f in used)
        if Q2(total_debit) != Q2(total_credit):
            self.lines.errors.append('❌ مجموع المدين يجب أن يساوي مجموع الدائن')
            return False
        self._used_lines_count = len(used)
        return True

    def apply_to(self, je: 'JournalEntry') -> 'JournalEntry':
        from models import JournalLine
        je.entry_date = self.entry_date.data
        je.reference = (self.reference.data or '').strip() or None
        je.description = (self.description.data or '').strip() or None
        je.currency = self.currency.data
        je.posted = bool(self.post_now.data)
        new_lines = []
        for lf in self.lines:
            f = lf.form
            if not ((D(f.debit.data) > 0) or (D(f.credit.data) > 0)):
                continue
            acc_id = int(f.account_id.data) if f.account_id.data else None
            if not acc_id:
                continue
            jl = JournalLine(
                account_id=acc_id,
                debit=D(f.debit.data) if D(f.debit.data) > 0 else Decimal("0.00"),
                credit=D(f.credit.data) if D(f.credit.data) > 0 else Decimal("0.00"),
                entity_type=(f.entity_type.data or '').strip() or None,
                entity_id=(f.entity_id.data or '').strip() or None,
                note=(f.note.data or '').strip() or None
            )
            new_lines.append(jl)
        je.lines = new_lines
        return je

class GeneralLedgerFilterForm(FlaskForm):
    account_ids = AjaxSelectMultipleField('الحسابات', endpoint='api.search_accounts', get_label='name', validators=[Optional()])
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    include_unposted = BooleanField('تضمين غير المرحلة', default=False)
    submit = SubmitField('عرض الدفتر')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        if not getattr(self, 'hints', None):
            self.hints = []
        if not (self.account_ids.data or []):
            self.hints.append('ℹ️ لم تُحدِّد حسابات؛ سيتم عرض كل الحسابات المطابقة للفترة.')
        return True


class TrialBalanceFilterForm(FlaskForm):
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[Optional()])
    include_zero = BooleanField('إظهار الحسابات الصفرية', default=False)
    submit = SubmitField('عرض الميزان')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        if not getattr(self, 'hints', None):
            self.hints = []
        if not (self.currency.data or '').strip():
            self.hints.append('ℹ️ لم تُحدِّد عملة؛ سيتم استخدام الإعداد الافتراضي للتقارير.')
        return True


class ClosingEntryForm(FlaskForm):
    start_date = DateField('من تاريخ', validators=[DataRequired()])
    end_date = DateField('إلى تاريخ', validators=[DataRequired()])
    revenue_accounts = AjaxSelectMultipleField('حسابات الإيرادات', endpoint='api.search_accounts', get_label='name', validators=[Optional()])
    expense_accounts = AjaxSelectMultipleField('حسابات المصاريف', endpoint='api.search_accounts', get_label='name', validators=[Optional()])
    retained_earnings_account = AjaxSelectField('حساب الأرباح المحتجزة / النتائج', endpoint='api.search_accounts', get_label='name', validators=[DataRequired()])
    submit = SubmitField('إنشاء قيد الإقفال')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        return True

class ExportContactsForm(FlaskForm):
    customer_ids = AjaxSelectMultipleField('اختر العملاء', endpoint='api.search_customers', get_label='name', validators=[DataRequired(message='❌ اختر عميلًا واحدًا على الأقل')])
    fields = SelectMultipleField('الحقول', choices=[('name', 'الاسم'), ('phone', 'الجوال'), ('whatsapp', 'واتساب'), ('email', 'البريد الإلكتروني'), ('address', 'العنوان'), ('notes', 'ملاحظات')], default=['name', 'phone', 'email'], coerce=str, validators=[Optional()])
    format = SelectField('صيغة التصدير', choices=[('vcf', 'vCard'), ('csv', 'CSV'), ('excel', 'Excel')], default='vcf', validators=[DataRequired()], coerce=str)
    submit = SubmitField('تصدير')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if not self.customer_ids.data:
            self.customer_ids.errors.append('❌ اختر عميلًا واحدًا على الأقل')
            return False
        allowed = {k for k, _ in self.fields.choices}
        sel = [f for f in (self.fields.data or []) if f in allowed]
        if not sel:
            self.fields.errors.append('❌ اختر حقلًا واحدًا على الأقل للتصدير')
            return False
        order = {k: i for i, (k, _) in enumerate(self.fields.choices)}
        sel.sort(key=lambda k: order.get(k, 1_000_000))
        self.fields.data = sel
        return True

class OnlineCartPaymentForm(PaymentDetailsMixin, FlaskForm):
    payment_method = SelectField('طريقة الدفع', choices=[('card', 'بطاقة')], default='card', validators=[DataRequired()], coerce=str)
    card_holder = StrippedStringField('اسم حامل البطاقة', validators=[Optional(), Length(max=100)])
    card_number = StrippedStringField('رقم البطاقة', validators=[Optional(), Length(min=12, max=19)])
    expiry = StrippedStringField('تاريخ الانتهاء (MM/YY)', validators=[Optional(), Length(min=5, max=5)])
    cvv = StrippedStringField('CVV', validators=[Optional(), Length(min=3, max=4)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=300)])
    billing_address = TextAreaField('عنوان الفاتورة', validators=[Optional(), Length(max=300)])
    transaction_data = TextAreaField('بيانات إضافية للبوابة (JSON)', validators=[Optional()])
    save_card = BooleanField('حفظ البطاقة')
    submit = SubmitField('تأكيد الدفع')

    def _digits(self, s):
        return only_digits(s).translate(_AR_DIGITS)

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        pm = (self.payment_method.data or '').strip().lower()
        if pm != 'card':
            self.payment_method.errors.append('طريقة دفع غير مدعومة')
            return False
        self.card_number.data = self._digits(self.card_number.data or '')
        self.cvv.data = self._digits(self.cvv.data or '')
        try:
            _ = self._validate_card_payload(
                self.card_number.data,
                self.card_holder.data,
                (self.expiry.data or '').strip()
            )
        except ValidationError as e:
            msg = str(e)
            if 'رقم البطاقة' in msg:
                self.card_number.errors.append(msg)
            elif 'حامل البطاقة' in msg:
                self.card_holder.errors.append(msg)
            elif 'MM/YY' in msg or 'الانتهاء' in msg:
                self.expiry.errors.append(msg)
            else:
                self.payment_method.errors.append(msg)
            return False
        if not self.cvv.data or not self.cvv.data.isdigit() or len(self.cvv.data) not in (3, 4):
            self.cvv.errors.append('CVV غير صالح')
            return False
        if self.transaction_data.data:
            try:
                json.loads(self.transaction_data.data)
            except Exception:
                self.transaction_data.errors.append('JSON غير صالح')
                return False
        return True

    def gateway_payload(self):
        last4 = (self.card_number.data or '')[-4:] if self.card_number.data else None
        extra = None
        if self.transaction_data.data:
            try:
                extra = json.loads(self.transaction_data.data)
            except Exception:
                extra = None
        payload = {
            'method': 'card',
            'card': {
                'holder': (self.card_holder.data or '').strip(),
                'number': (self.card_number.data or '').strip(),
                'expiry': (self.expiry.data or '').strip(),
                'cvv': (self.cvv.data or '').strip(),
                'save': bool(self.save_card.data),
                'last4': last4,
            },
            'shipping_address': (self.shipping_address.data or '').strip() or None,
            'billing_address': (self.billing_address.data or '').strip() or None,
            'extra': extra,
        }
        self.card_number.data = last4
        self.cvv.data = None
        return payload
