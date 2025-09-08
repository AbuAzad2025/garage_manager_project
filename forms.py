from __future__ import annotations
import re
from datetime import date, datetime
from decimal import Decimal
import json

from barcodes import validate_barcode
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
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
        def __init__(self, label=None, validators=None, format='%Y-%m-%dT%H:%M', **kwargs):
            kwargs = dict(kwargs or {})
            rk = dict(kwargs.get('render_kw') or {})
            rk.setdefault('type', 'datetime-local')
            rk.setdefault('step', '60')
            kwargs['render_kw'] = rk
            super().__init__(label, validators or [], format=format, **kwargs)

from models import (
    User,
    Customer,
    Supplier,
    Partner,
    Warehouse,
    Product,
    StockLevel,
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
    Sale, SaleLine,
    ShipmentItem, ShipmentPartner,
    GLBatch, GLEntry,
)

from utils import is_valid_ean13, luhn_check, is_valid_expiry_mm_yy, prepare_payment_form_choices, D, q
from validators import Unique

CURRENCY_CHOICES = [("ILS", "ILS"), ("USD", "USD"), ("EUR", "EUR"), ("JOD", "JOD")]
CENT = Decimal("0.01")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


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
        pass

    def process_formdata(self, valuelist):
        if not valuelist:
            self.data = None
            return
        v = (valuelist[0] or "").strip()
        if self.allow_blank and v in ("", "0", "None", "null"):
            self.data = None
            return
        try:
            self.data = int(v)
        except Exception:
            self.data = v

    def process_data(self, value):
        if value in (None, "", 0, "0", "None"):
            self.data = None
            return
        try:
            self.data = int(getattr(value, "id", value))
        except Exception:
            self.data = value


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
            s = (v or "").strip()
            if not s:
                continue
            try:
                out.append(int(s))
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
            try:
                out.append(int(getattr(v, "id", v)))
            except Exception:
                out.append(v)
        self.data = out


try:
    from wtforms_sqlalchemy.fields import QuerySelectField  # type: ignore
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
            if self.allow_blank and v in ("", "None"):
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
            pass


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
            self.data = None
            return
        raw = " ".join([v for v in valuelist if v is not None]).strip()
        if not raw:
            self.data = None
            return
        s = raw.replace("T", " ").strip()
        for fmt in self.formats:
            try:
                self.data = datetime.strptime(s, fmt)
                return
            except Exception:
                continue
        try:
            self.data = datetime.fromtimestamp(float(s))
            return
        except Exception:
            pass
        self.data = None
        raise ValueError(self.gettext("صيغة التاريخ/الوقت غير صحيحة"))


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

    def _to_int(self, v):
        try:
            return int(str(v).translate(_AR_DIGITS).strip())
        except Exception:
            return None

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        src = self._to_int(self.source_id.data)
        dst = self._to_int(self.destination_id.data)
        if src and dst and src == dst:
            self.destination_id.errors.append("يجب اختيار مخزن مختلف عن المصدر.")
            return False
        pid = self._to_int(self.product_id.data)
        qty = self._to_int(self.quantity.data) or 0
        if pid and src and qty:
            try:
                from models import StockLevel
                sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=src).first()
                avail = (sl.quantity if sl else 0) - (sl.reserved_quantity if sl else 0)
                if qty > max(avail, 0):
                    self.quantity.errors.append("الكمية غير كافية في المخزن المصدر.")
                    return False
            except Exception:
                pass
        return True

    def apply_to(self, t):
        t.reference = (self.reference.data or "").strip() or t.reference
        t.product_id = self._to_int(self.product_id.data)
        t.source_id = self._to_int(self.source_id.data)
        t.destination_id = self._to_int(self.destination_id.data)
        t.quantity = self._to_int(self.quantity.data) or 1
        t.direction = (self.direction.data or "").upper()
        t.transfer_date = self.transfer_date.data or datetime.utcnow()
        t.notes = (self.notes.data or "").strip() or None
        return t


class SettlementRangeForm(FlaskForm):
    start = DateField("من", validators=[Optional()])
    end = DateField("إلى", validators=[Optional()])
    submit = SubmitField("عرض")

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
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
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
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
        q = User.query.filter(User.username == name)
        if getattr(self, "_editing_user_id", None):
            q = q.filter(User.id != self._editing_user_id)
        if q.first():
            raise ValidationError("اسم المستخدم مستخدم بالفعل.")

    def validate_email(self, field):
        email_l = (field.data or '').strip().lower()
        q = User.query.filter(User.email == email_l)
        if getattr(self, "_editing_user_id", None):
            q = q.filter(User.id != self._editing_user_id)
        if q.first():
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
        q = Role.query.filter(Role.name == s)
        if self.id.data and str(self.id.data).strip().isdigit():
            q = q.filter(Role.id != int(self.id.data))
        if q.first():
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
    name = StringField('اسم العميل', validators=[DataRequired(message="هذا الحقل مطلوب"), Length(max=100)])
    phone = StringField('الهاتف', validators=[DataRequired(message="الهاتف مطلوب"), Length(max=20, message="أقصى طول 20 رقم"),
                      Unique(Customer, "phone", message="رقم الهاتف مستخدم مسبقًا", case_insensitive=False, normalizer=normalize_phone)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(message="هذا الحقل مطلوب"), Email(message="صيغة البريد غير صحيحة"), Length(max=120),
                      Unique(Customer, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200, message="أقصى طول 200 حرف")])
    whatsapp = StringField('واتساب', validators=[Optional(), Length(max=20, message="أقصى طول 20 رقم")])
    category = SelectField('تصنيف العميل', choices=[('عادي','عادي'),('فضي','فضي'),('ذهبي','ذهبي'),('مميز','مميز')], default='عادي')
    credit_limit = DecimalField('حد الائتمان', places=2, validators=[Optional(), NumberRange(min=0, message="يجب أن يكون ≥ 0")])
    discount_rate = DecimalField('معدل الخصم (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100, message="بين 0 و100")])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired(message='العملة مطلوبة')])
    is_active = BooleanField('نشط', default=True)
    is_online = BooleanField('عميل أونلاين', default=False)
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
        val = (field.data or "").strip()
        if not val:
            field.data = normalize_phone(self.phone.data)

    def apply_to(self, customer: Customer) -> Customer:
        customer.name = (self.name.data or "").strip()
        customer.phone = normalize_phone(self.phone.data)
        customer.whatsapp = normalize_phone(self.whatsapp.data or self.phone.data)
        customer.email = normalize_email(self.email.data)
        customer.address = (self.address.data or "").strip() or None
        customer.category = self.category.data
        customer.currency = self.currency.data
        customer.is_active = bool(self.is_active.data)
        customer.is_online = bool(self.is_online.data)
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
    product_id = AjaxSelectField('المنتج', endpoint='api.products', get_label='name', validators=[DataRequired()])
    supplier_id = AjaxSelectField('المورد/التاجر', endpoint='api.suppliers', get_label='name', validators=[DataRequired()])
    loan_value = DecimalField('قيمة الدين التقديرية', places=2, validators=[Optional(), NumberRange(min=0)])
    deferred_price = DecimalField('السعر النهائي بعد التسوية', places=2, validators=[Optional(), NumberRange(min=0)])
    is_settled = BooleanField('تمت التسوية؟')
    partner_share_quantity = IntegerField('كمية شراكة التاجر', validators=[Optional(), NumberRange(min=0)])
    partner_share_value = DecimalField('قيمة شراكة التاجر', places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        lv = self.loan_value.data or 0
        dp = self.deferred_price.data or 0
        if lv <= 0 and dp <= 0:
            self.loan_value.errors.append('يجب إدخال قيمة الدين أو السعر بعد التسوية.')
            return False
        return True


class SupplierForm(FlaskForm):
    id = HiddenField(filters=[lambda v: int(v) if v and str(v).strip().isdigit() else None])
    name = StringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    is_local = BooleanField('محلي؟')
    identity_number = StringField('رقم الهوية/الملف الضريبي', validators=[Optional(), Length(max=100)])
    contact = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20),
                      Unique(Supplier, "phone", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                      Unique(Supplier, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    balance = DecimalField('الرصيد الافتتاحي', places=2, validators=[Optional(), NumberRange(min=0)])
    payment_terms = StringField('شروط الدفع', validators=[Optional(), Length(max=50)])
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
        supplier.currency = self.currency.data
        return supplier


class PartnerForm(FlaskForm):
    id = HiddenField(filters=[lambda v: int(v) if v and str(v).strip().isdigit() else None])
    name = StringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    contact_info = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    identity_number = StringField('رقم الهوية', validators=[Optional(), Length(max=100)])
    phone_number = StringField('رقم الجوال', validators=[Optional(), Length(max=20),
                      Unique(Partner, "phone_number", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                      Unique(Partner, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    balance = DecimalField('الرصيد', places=2, validators=[Optional(), NumberRange(min=0)])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
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
        partner.currency = self.currency.data
        return partner


class QuickSupplierForm(FlaskForm):
    name = StringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20),
                    Unique(Supplier, "phone", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                    Unique(Supplier, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
    submit = SubmitField('إضافة سريعة')

    def validate_phone(self, field):
        if field.data:
            field.data = normalize_phone(field.data)

    def validate_email(self, field):
        if field.data:
            field.data = normalize_email(field.data)


class QuickPartnerForm(FlaskForm):
    name = StringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20),
                    Unique(Partner, "phone_number", message="رقم الهاتف مستخدم مسبقًا", normalizer=normalize_phone)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                    Unique(Partner, "email", message="البريد مستخدم مسبقًا", case_insensitive=True, normalizer=normalize_email)])
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
    payment_id = IntegerField(validators=[Optional()])
    invoice_ids = AjaxSelectMultipleField(endpoint='api.invoices', get_label='invoice_number', validators=[Optional()])
    service_ids = AjaxSelectMultipleField(endpoint='api.services', get_label='service_number', validators=[Optional()])
    expense_ids = AjaxSelectMultipleField(endpoint='api.expenses', get_label='id', validators=[Optional()])
    shipment_ids = AjaxSelectMultipleField(endpoint='api.shipments', get_label='shipment_number', validators=[Optional()])
    allocation_amounts = FieldList(DecimalField(places=2, validators=[Optional(), NumberRange(min=0.01)]), min_entries=1)
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

class SupplierSettlementForm(FlaskForm):
    supplier_id = AjaxSelectField('المورد', endpoint='api.search_suppliers', get_label='name', validators=[DataRequired()])
    settlement_date = DateTimeField('تاريخ التسوية', format='%Y-%m-%d %H:%M', default=datetime.utcnow, validators=[DataRequired()], render_kw={'type': 'datetime-local', 'step': '60'})
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    method = SelectField(choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod], validators=[DataRequired()], coerce=str, default='')
    total_amount = DecimalField('المبلغ الكلي', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    allocations = FieldList(FormField(PaymentAllocationForm), min_entries=1)
    reference = StringField('مرجع', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ التسوية')

    def validate(self, **kwargs):
        ok = super().validate(**kwargs)
        try:
            total = float(self.total_amount.data or 0)
        except Exception:
            total = 0.0
        sum_alloc = 0.0
        nonempty = False
        for entry in self.allocations:
            fm = entry.form
            for fld in getattr(fm, 'allocation_amounts', []):
                val = fld.data or 0
                try:
                    v = float(val)
                except Exception:
                    v = 0.0
                if v > 0:
                    nonempty = True
                    sum_alloc += v
            if getattr(fm, 'service_ids', None) and (fm.service_ids.data or []):
                fm.service_ids.errors.append('❌ لا يُسمح بخدمات العملاء ضمن تسوية المورد.')
                ok = False
        if not nonempty:
            self.allocations.errors.append('❌ أضف عنصر توزيع واحدًا على الأقل.')
            ok = False
        if abs(sum_alloc - total) > 0.01:
            self.total_amount.errors.append('❌ مجموع مبالغ التوزيع يجب أن يساوي المبلغ الكلي.')
            ok = False
        sid = (self.supplier_id.data or "").__str__().strip()
        if not sid or not sid.isdigit() or int(sid) <= 0:
            self.supplier_id.errors.append('❌ اختر المورد بشكل صحيح.')
            ok = False
        return ok

class RefundForm(FlaskForm):
    original_payment_id = IntegerField(validators=[DataRequired()])
    refund_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    reason = TextAreaField(validators=[Optional(), Length(max=500)])
    refund_method = SelectField(
        choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod],
        validators=[DataRequired()],
        coerce=str,
        default='',
    )
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('إرجاع')


class BulkPaymentForm(FlaskForm):
    payer_type = SelectField(
        choices=[('customer', 'عميل'), ('partner', 'شريك'), ('supplier', 'مورد')],
        validators=[DataRequired()],
        coerce=str,
    )
    payer_search = StringField(validators=[Optional(), Length(max=100)])
    payer_id = HiddenField(validators=[DataRequired()])
    total_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    allocations = FieldList(FormField(PaymentAllocationForm), min_entries=1)
    method = SelectField(
        choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod],
        validators=[DataRequired()],
        coerce=str,
        default='',
    )
    currency = SelectField(
        choices=[('ILS', 'شيكل'), ('USD', 'دولار'), ('EUR', 'يورو'), ('JOD', 'دينار')],
        default='ILS',
        validators=[DataRequired()],
        coerce=str,
    )
    submit = SubmitField('حفظ الدفعة')

    def validate(self, **kwargs):
        ok = super().validate(**kwargs)
        try:
            total = float(self.total_amount.data or 0)
        except Exception:
            total = 0.0
        sum_alloc = 0.0
        nonempty = False
        for entry in self.allocations:
            fm = entry.form
            for fld in getattr(fm, 'allocation_amounts', []):
                val = fld.data or 0
                try:
                    v = float(val)
                except Exception:
                    v = 0.0
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
        if abs(sum_alloc - total) > 0.01:
            self.total_amount.errors.append('❌ مجموع مبالغ التوزيع يجب أن يساوي المبلغ الكلي.')
            ok = False
        pid = (self.payer_id.data or "").strip()
        if not pid.isdigit() or int(pid) <= 0:
            self.payer_id.errors.append('❌ اختر الدافع بشكل صحيح.')
            ok = False
        return ok


class LoanSettlementPaymentForm(FlaskForm):
    settlement_id = AjaxSelectField(endpoint='api.loan_settlements', get_label='id', validators=[DataRequired()])
    amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField(
        choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod],
        validators=[DataRequired()],
        coerce=str,
        default='',
    )
    reference = StringField(validators=[Optional(), Length(max=100)])
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('دفع')


class SplitEntryForm(FlaskForm):
    method = SelectField(
        choices=[('', '— اختر الطريقة —')] + [(m.value, m.value) for m in PaymentMethod],
        validators=[Optional()],
        default='',
        coerce=str,
    )
    amount = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)], default=Decimal('0.00'))
    check_number = StringField(validators=[Optional(), Length(max=100)])
    check_bank = StringField(validators=[Optional(), Length(max=100)])
    check_due_date = DateField(format='%Y-%m-%d', validators=[Optional()])
    card_number = StringField(validators=[Optional(), Length(max=100)])
    card_holder = StringField(validators=[Optional(), Length(max=100)])
    card_expiry = StringField(validators=[Optional(), Length(max=10)])
    bank_transfer_ref = StringField(validators=[Optional(), Length(max=100)])

    def validate(self, **kwargs):
        base_ok = super().validate(**kwargs)
        ok = True
        amt = self.amount.data
        try:
            amt_val = float(amt) if amt is not None else 0.0
        except Exception:
            amt_val = 0.0
        m = (self.method.data or '').strip().lower()
        if amt_val <= 0:
            details_filled = any([
                (self.check_number.data or '').strip(),
                (self.check_bank.data or '').strip(),
                bool(self.check_due_date.data),
                (self.card_number.data or '').strip(),
                (self.card_holder.data or '').strip(),
                (self.card_expiry.data or '').strip(),
                (self.bank_transfer_ref.data or '').strip(),
            ])
            if m or details_filled:
                self.amount.errors.append('❌ أدخل مبلغًا أكبر من صفر لهذه الدفعة.')
                ok = False
            return base_ok and ok
        if not m:
            self.method.errors.append('❌ اختر طريقة الدفع.')
            return False
        if m in {'cheque', 'check'}:
            if not (self.check_number.data or '').strip():
                self.check_number.errors.append('❌ يجب إدخال بيانات الشيك كاملة')
                ok = False
            if not (self.check_bank.data or '').strip():
                self.check_bank.errors.append('❌ يجب إدخال بيانات الشيك كاملة')
                ok = False
            if not self.check_due_date.data:
                self.check_due_date.errors.append('❌ يجب إدخال بيانات الشيك كاملة')
                ok = False
        elif m == 'card':
            num = (self.card_number.data or '').replace(' ', '').replace('-', '')
            if not num or not num.isdigit() or not luhn_check(num):
                self.card_number.errors.append('❌ رقم البطاقة غير صالح')
                ok = False
            exp = (self.card_expiry.data or '').strip()
            if not exp or not is_valid_expiry_mm_yy(exp):
                self.card_expiry.errors.append('❌ تاريخ الانتهاء يجب أن يكون بصيغة MM/YY وفي المستقبل')
                ok = False
            if not (self.card_holder.data or '').strip():
                self.card_holder.errors.append('❌ أدخل اسم حامل البطاقة')
                ok = False
        elif m in {'bank', 'transfer', 'wire'}:
            if not (self.bank_transfer_ref.data or '').strip():
                self.bank_transfer_ref.errors.append('❌ أدخل مرجع التحويل البنكي')
                ok = False
        return base_ok and ok


class PaymentForm(FlaskForm):
    id = HiddenField()
    payment_number = StringField(validators=[Optional(), Length(max=50), Unique(Payment, 'payment_number', message='رقم الدفعة مستخدم بالفعل.', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())])
    payment_date = DateTimeField(format="%Y-%m-%dT%H:%M", default=datetime.utcnow, validators=[DataRequired()], render_kw={"type": "datetime-local", "step": "60"})
    subtotal = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    tax_amount = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    total_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField(validators=[DataRequired()], choices=[("ILS","شيكل"),("USD","دولار"),("EUR","يورو"),("JOD","دينار")], default="ILS")
    method = SelectField(validators=[Optional()], coerce=str)
    status = SelectField(validators=[DataRequired()], coerce=str)
    direction = SelectField(validators=[DataRequired()], coerce=str)
    entity_type = SelectField(validators=[DataRequired()], coerce=str)
    entity_id = HiddenField(validators=[Optional()])
    customer_search = StringField(validators=[Optional(), Length(max=100)])
    customer_id = HiddenField()
    supplier_search = StringField(validators=[Optional(), Length(max=100)])
    supplier_id = HiddenField()
    partner_search = StringField(validators=[Optional(), Length(max=100)])
    partner_id = HiddenField()
    shipment_search = StringField(validators=[Optional(), Length(max=100)])
    shipment_id = HiddenField()
    expense_search = StringField(validators=[Optional(), Length(max=100)])
    expense_id = HiddenField()
    loan_settlement_search = StringField(validators=[Optional(), Length(max=100)])
    loan_settlement_id = HiddenField()
    sale_search = StringField(validators=[Optional(), Length(max=100)])
    sale_id = HiddenField()
    invoice_search = StringField(validators=[Optional(), Length(max=100)])
    invoice_id = HiddenField()
    preorder_search = StringField(validators=[Optional(), Length(max=100)])
    preorder_id = HiddenField()
    service_search = StringField(validators=[Optional(), Length(max=100)])
    service_id = HiddenField()
    receipt_number = StringField(validators=[Optional(), Length(max=50), Unique(Payment, 'receipt_number', message='رقم الإيصال مستخدم بالفعل.', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())])
    reference = StringField(validators=[Optional(), Length(max=100)])
    check_number = StringField(validators=[Optional(), Length(max=100)])
    check_bank = StringField(validators=[Optional(), Length(max=100)])
    check_due_date = DateField(format="%Y-%m-%d", validators=[Optional()])
    card_number = StringField(validators=[Optional(), Length(max=100)])
    card_holder = StringField(validators=[Optional(), Length(max=100)])
    card_expiry = StringField(validators=[Optional(), Length(max=10)])
    card_cvv = StringField(validators=[Optional(), Length(min=3, max=4)])
    request_token = HiddenField(validators=[Optional()])
    bank_transfer_ref = StringField(validators=[Optional(), Length(max=100)])
    created_by = HiddenField()
    splits = FieldList(FormField(SplitEntryForm), min_entries=1, max_entries=3)
    notes = TextAreaField(validators=[Optional(), Length(max=500)])
    submit = SubmitField("💾 حفظ الدفعة")

    _entity_field_map = {"CUSTOMER": "customer_id","SUPPLIER": "supplier_id","PARTNER": "partner_id","SHIPMENT": "shipment_id","EXPENSE": "expense_id","LOAN": "loan_settlement_id","SALE": "sale_id","INVOICE": "invoice_id","PREORDER": "preorder_id","SERVICE": "service_id"}
    _incoming_entities = {"CUSTOMER", "SALE", "INVOICE", "PREORDER", "SERVICE"}
    _outgoing_entities = {"SUPPLIER", "PARTNER", "SHIPMENT", "EXPENSE", "LOAN"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        prepare_payment_form_choices(self)
        if not self.splits.entries:
            self.splits.append_entry()
        et = (self.entity_type.data or "").upper()
        dirv = (self.direction.data or "").upper()
        if et and dirv not in {"IN", "OUT"}:
            if et in self._incoming_entities:
                self.direction.data = "IN"
            elif et in self._outgoing_entities:
                self.direction.data = "OUT"
        self._sync_entity_id_for_render()

    def _nz(self, v):
        if v is None: return ""
        if isinstance(v, str): return v.strip()
        return str(v)

    def _get_entity_ids(self):
        return {"customer_id": self.customer_id.data,"supplier_id": self.supplier_id.data,"partner_id": self.partner_id.data,"shipment_id": self.shipment_id.data,"expense_id": self.expense_id.data,"loan_settlement_id": self.loan_settlement_id.data,"sale_id": self.sale_id.data,"invoice_id": self.invoice_id.data,"preorder_id": self.preorder_id.data,"service_id": self.service_id.data}

    @staticmethod
    def _norm_dir(val):
        if val is None: return None
        v = val.value if hasattr(val, "value") else val
        v = str(v).strip().upper()
        if v in ("IN", "INCOMING", "INCOME", "RECEIVE"): return "IN"
        if v in ("OUT", "OUTGOING", "PAY", "PAYMENT", "EXPENSE"): return "OUT"
        return v

    @classmethod
    def _dir_to_db(cls, v):
        vv = cls._norm_dir(v)
        if vv == "IN": return "INCOMING"
        if vv == "OUT": return "OUTGOING"
        return vv

    def _sync_entity_id_for_render(self):
        et = (self.entity_type.data or "").upper()
        field_name = self._entity_field_map.get(et)
        if field_name:
            raw = getattr(self, field_name).data
            self.entity_id.data = "" if raw is None else (raw if isinstance(raw, str) else str(raw))
        else:
            self.entity_id.data = ""

    def _push_entity_id_to_specific(self):
        et = (self.entity_type.data or "").upper()
        field_name = self._entity_field_map.get(et)
        if not field_name: return
        rid = self._nz(self.entity_id.data)
        if rid:
            for k in self._get_entity_ids().keys():
                setattr(getattr(self, k), "data", rid if k == field_name else "")

    def _to_int(self, s):
        try:
            trans = str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')
            ss = str(s).translate(trans).strip()
            return int(ss)
        except Exception:
            return None

    def validate(self, extra_validators=None):
        if not (self.method.data or "").strip() and getattr(self, "splits", None):
            for entry in self.splits:
                fm = entry.form
                try: amt = float(fm.amount.data or 0)
                except Exception: amt = 0.0
                mv = (getattr(fm, "method").data or "").strip()
                if amt > 0 and mv:
                    self.method.data = mv
                    break
        self._push_entity_id_to_specific()
        if not super().validate(extra_validators=extra_validators): return False
        try: total_splits = sum(float(s.form.amount.data or 0) for s in self.splits)
        except Exception: total_splits = 0.0
        if abs(total_splits - float(self.total_amount.data or 0)) > 0.01:
            self.total_amount.errors.append("❌ مجموع الدفعات الجزئية يجب أن يساوي المبلغ الكلي"); return False
        etype = (self.entity_type.data or "").upper()
        field_name = self._entity_field_map.get(etype)
        entity_ids = self._get_entity_ids()
        if not field_name:
            self.entity_type.errors.append("❌ نوع الكيان غير معروف."); return False
        raw_id = entity_ids.get(field_name)
        rid_str = "" if raw_id is None else (raw_id.strip() if isinstance(raw_id, str) else str(raw_id))
        rid_val = self._to_int(rid_str) if rid_str else None
        if not rid_val and etype == "CUSTOMER":
            try:
                from models import Customer
                search_text = (getattr(self, "customer_search").data or "").strip() if hasattr(self, "customer_search") else ""
                if search_text:
                    m = Customer.query.filter(Customer.name.ilike(f"%{search_text}%")).first()
                    if m: rid_val = m.id
            except Exception: pass
        if not rid_val:
            if etype == "CUSTOMER": self.customer_search.errors.append("❌ يجب اختيار العميل لهذه الدفعة.")
            else: getattr(self, field_name).errors.append("❌ يجب اختيار المرجع المناسب للكيان المحدد.")
            return False
        filled = [k for k, v in entity_ids.items() if self._nz(v)]
        if len(filled) > 1:
            for k in filled:
                if k != field_name: getattr(self, k).errors.append("❌ لا يمكن تحديد أكثر من مرجع.")
            return False
        self.entity_id.data = str(rid_val)
        for k in entity_ids.keys():
            setattr(getattr(self, k), "data", str(rid_val) if k == field_name else "")
        v = (self.direction.data or "").upper()
        if etype in self._incoming_entities and v not in {"IN","INCOMING"}:
            self.direction.errors.append("❌ هذا الكيان يجب أن تكون حركته وارد (IN)."); return False
        if etype in self._outgoing_entities and v not in {"OUT","OUTGOING"}:
            self.direction.errors.append("❌ هذا الكيان يجب أن تكون حركته صادر (OUT)."); return False
        self.direction.data = "IN" if v in {"IN","INCOMING"} else "OUT"
        m = (self.method.data or "").strip().lower()
        if m in {"cheque","check"}:
            if not (self.check_number.data or "").strip(): self.check_number.errors.append("أدخل رقم الشيك."); return False
            if not (self.check_bank.data or "").strip(): self.check_bank.errors.append("أدخل اسم البنك."); return False
            if not self.check_due_date.data: self.check_due_date.errors.append("أدخل تاريخ استحقاق الشيك."); return False
            if self.payment_date.data and self.check_due_date.data < self.payment_date.data.date():
                self.check_due_date.errors.append("تاريخ الاستحقاق لا يمكن أن يسبق تاريخ الدفعة."); return False
        if m == "card":
            num = only_digits(self.card_number.data or "")
            if num and not luhn_check(num): self.card_number.errors.append("رقم البطاقة غير صالح."); return False
            exp = (self.card_expiry.data or "").strip()
            if exp and not is_valid_expiry_mm_yy(exp): self.card_expiry.errors.append("تاريخ الانتهاء بصيغة MM/YY."); return False
            cvv = (self.card_cvv.data or "").strip()
            if cvv and (not cvv.isdigit() or len(cvv) not in (3,4)): self.card_cvv.errors.append("CVV غير صالح."); return False
        return True
class PreOrderForm(FlaskForm):
    reference = StringField('مرجع الحجز', validators=[Optional(), Length(max=50)])
    preorder_date = UnifiedDateTimeField('تاريخ الحجز', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'autocomplete': 'off', 'dir': 'ltr'})
    expected_date = UnifiedDateTimeField('تاريخ التسليم المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()], render_kw={'autocomplete': 'off', 'dir': 'ltr'})
    status = SelectField('الحالة',
                         choices=[
                             (PreOrderStatus.PENDING.value, 'معلق'),
                             (PreOrderStatus.CONFIRMED.value, 'مؤكد'),
                             (PreOrderStatus.FULFILLED.value, 'منفذ'),
                             (PreOrderStatus.CANCELLED.value, 'ملغي')
                         ],
                         default=PreOrderStatus.PENDING.value,
                         validators=[DataRequired()])
    customer_id = AjaxSelectField('العميل', endpoint='api.search_customers', get_label='name', validators=[DataRequired()])
    product_id = AjaxSelectField('القطعة', endpoint='api.products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', validators=[DataRequired()])
    supplier_id = AjaxSelectField('المورد', endpoint='api.suppliers', get_label='name', validators=[Optional()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    prepaid_amount = DecimalField('المدفوع مسبقاً', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    payment_method = SelectField('طريقة الدفع',
                                 choices=[
                                     (PaymentMethod.CASH.value, 'نقدي'),
                                     (PaymentMethod.CARD.value, 'بطاقة'),
                                     (PaymentMethod.BANK.value, 'تحويل'),
                                     (PaymentMethod.CHEQUE.value, 'شيك'),
                                     (PaymentMethod.ONLINE.value, 'دفع إلكتروني')
                                 ],
                                 default=PaymentMethod.CASH.value,
                                 validators=[Optional()],
                                 coerce=str)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('تأكيد الحجز')

    def _to_int(self, v):
        try:
            return int(str(v).translate(_AR_DIGITS).strip())
        except Exception:
            return None

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if self.preorder_date.data and self.expected_date.data and self.expected_date.data < self.preorder_date.data:
            self.expected_date.errors.append('❌ تاريخ التسليم المتوقع يجب أن يكون بعد تاريخ الحجز')
            return False
        pm = (self.payment_method.data or '').strip()
        if pm not in {str(m.value) for m in PaymentMethod}:
            self.payment_method.errors.append('❌ طريقة الدفع غير معروفة')
            return False
        qty = self._to_int(self.quantity.data) or 0
        pid = self._to_int(self.product_id.data)
        if pid and qty > 0:
            try:
                prod = Product.query.get(pid)
                price = float(getattr(prod, 'price', 0) or 0)
                base = qty * price
                tax = base * float(self.tax_rate.data or 0) / 100.0
                total = base + tax
                paid = float(self.prepaid_amount.data or 0)
                if paid > total + 0.0001:
                    self.prepaid_amount.errors.append('❌ الدفعة المسبقة تتجاوز إجمالي الطلب بعد الضريبة')
                    return False
            except Exception:
                pass
        return True

    def apply_to(self, preorder: PreOrder) -> PreOrder:
        preorder.reference = (self.reference.data or '').strip() or preorder.reference
        preorder.preorder_date = self.preorder_date.data or preorder.preorder_date
        preorder.expected_date = self.expected_date.data or None
        preorder.status = self.status.data
        preorder.product_id = self._to_int(self.product_id.data) if self.product_id.data else None
        preorder.warehouse_id = self._to_int(self.warehouse_id.data) if self.warehouse_id.data else None
        preorder.customer_id = self._to_int(self.customer_id.data) if self.customer_id.data else None
        preorder.supplier_id = self._to_int(self.supplier_id.data) if self.supplier_id.data else None
        preorder.partner_id = self._to_int(self.partner_id.data) if self.partner_id.data else None
        preorder.quantity = self._to_int(self.quantity.data) or 0
        preorder.prepaid_amount = self.prepaid_amount.data or 0
        preorder.tax_rate = self.tax_rate.data or 0
        preorder.payment_method = (self.payment_method.data or PaymentMethod.CASH.value)
        preorder.notes = (self.notes.data or '').strip() or None
        return preorder

class ServiceRequestForm(FlaskForm):
    service_number = StringField('رقم الخدمة', validators=[Optional(), Length(max=50)])
    customer_id = AjaxSelectField('العميل', endpoint='api.customers', get_label='name', validators=[DataRequired()])
    mechanic_id = AjaxSelectField('الفني', endpoint='api.users', get_label='username', validators=[Optional()])
    vehicle_type_id = AjaxSelectField('نوع المعدة/المركبة', endpoint='api.equipment_types', get_label='name', validators=[Optional()])
    vehicle_vrn = StringField('لوحة المركبة', validators=[DataRequired(), Length(max=50)])
    vehicle_model = StringField('موديل المركبة/المعدة', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    problem_description = TextAreaField('وصف المشكلة', validators=[Optional(), Length(max=2000)])
    diagnosis = TextAreaField('التشخيص', validators=[Optional(), Length(max=4000)])
    resolution = TextAreaField('المعالجة', validators=[Optional(), Length(max=4000)])
    notes = TextAreaField('ملاحظات عامة', validators=[Optional(), Length(max=4000)])
    engineer_notes = TextAreaField('ملاحظات المهندس', validators=[Optional(), Length(max=4000)])
    description = TextAreaField('وصف عام', validators=[Optional(), Length(max=2000)])
    priority = SelectField('الأولوية', choices=[('LOW','منخفضة'),('MEDIUM','متوسطة'),('HIGH','عالية'),('URGENT','عاجلة')], default='MEDIUM', validators=[DataRequired()])
    status = SelectField('الحالة', choices=[('PENDING','معلق'),('DIAGNOSIS','تشخيص'),('IN_PROGRESS','قيد التنفيذ'),('COMPLETED','مكتمل'),('CANCELLED','ملغي'),('ON_HOLD','مؤجل')], default='PENDING', validators=[DataRequired()])
    estimated_duration = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    actual_duration = IntegerField('المدة الفعلية (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost = DecimalField('التكلفة المتوقعة', places=2, validators=[Optional(), NumberRange(min=0)])
    total_cost = DecimalField('التكلفة النهائية', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    start_time = DateField('تاريخ البدء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])
    end_time = DateField('تاريخ الانتهاء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])
    received_at = DateTimeField('وقت الاستلام', format='%Y-%m-%d %H:%M', validators=[Optional()])
    started_at = DateTimeField('وقت البدء الفعلي', format='%Y-%m-%d %H:%M', validators=[Optional()])
    expected_delivery = DateTimeField('موعد التسليم المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()])
    completed_at = DateTimeField('وقت الإكمال', format='%Y-%m-%d %H:%M', validators=[Optional()])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    discount_total = DecimalField('إجمالي الخصومات', places=2, validators=[Optional(), NumberRange(min=0)])
    parts_total = DecimalField('إجمالي قطع الغيار', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    labor_total = DecimalField('إجمالي الأجور', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    total_amount = DecimalField('الإجمالي النهائي', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    warranty_days = IntegerField('مدة الضمان (أيام)', validators=[Optional(), NumberRange(min=0)])
    consume_stock = BooleanField("استهلاك من المخزون؟", default=True)
    submit = SubmitField('حفظ طلب الصيانة')

    @staticmethod
    def _d(x):
        from decimal import Decimal
        return Decimal(str(x or 0))

    @staticmethod
    def _q2(x):
        from decimal import Decimal, ROUND_HALF_UP
        return ServiceRequestForm._d(x).quantize(Decimal("0.01"), ROUND_HALF_UP)

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        st, et = self.start_time.data, self.end_time.data
        if st and et and et < st:
            self.end_time.errors.append('❌ وقت الانتهاء يجب أن يكون بعد وقت البدء')
            return False
        ra, sa = self.received_at.data, self.started_at.data
        if ra and sa and sa < ra:
            self.started_at.errors.append('❌ وقت البدء الفعلي يجب أن يكون بعد وقت الاستلام')
            return False
        if st and sa and sa.date() < st:
            self.started_at.errors.append('❌ وقت البدء الفعلي يجب أن يكون في أو بعد تاريخ البدء التخطيطي')
            return False
        ed = self.expected_delivery.data
        if sa and ed and ed < sa:
            self.expected_delivery.errors.append('❌ التسليم المتوقع يجب أن يكون بعد وقت البدء الفعلي')
            return False
        if st and ed and ed.date() < st:
            self.expected_delivery.errors.append('❌ التسليم المتوقع يجب أن يكون بعد تاريخ البدء')
            return False
        ct = self.completed_at.data
        if sa and ct and ct < sa:
            self.completed_at.errors.append('❌ الإكمال يجب أن يكون بعد وقت البدء الفعلي')
            return False
        if st and ct and ct.date() < st:
            self.completed_at.errors.append('❌ الإكمال يجب أن يكون بعد تاريخ البدء')
            return False
        parts = self._d(self.parts_total.data)
        labor = self._d(self.labor_total.data)
        disc = self._d(self.discount_total.data)
        base = self._q2(parts + labor - disc if (parts + labor - disc) >= 0 else 0)
        taxr = self._d(self.tax_rate.data)
        if taxr < 0 or taxr > self._d(100):
            self.tax_rate.errors.append('❌ نسبة الضريبة يجب أن تكون بين 0 و 100')
            return False
        expected_total = self._q2(base * (self._d(1) + taxr / self._d(100)))
        if self.total_cost.data is None:
            self.total_cost.data = base
        elif self._d(self.total_cost.data) + self._d("0.01") < base:
            self.total_cost.errors.append('❌ التكلفة النهائية لا يمكن أن تكون أقل من (قطع + أجور − خصم)')
            return False
        if self.total_amount.data is not None and self._q2(self.total_amount.data) != expected_total:
            self.total_amount.errors.append('❌ الإجمالي النهائي لا يطابق المبلغ المتوقع بعد الضريبة')
            return False
        return True

    @staticmethod
    def _set_if_has(obj, attr, value):
        if hasattr(obj, attr):
            setattr(obj, attr, value)

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
    shipment_id = HiddenField(validators=[Optional()])
    product_id = AjaxSelectField('الصنف', endpoint='api.products', get_label='name', coerce=int, validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    declared_value = DecimalField('القيمة المعلنة', places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        q = self.quantity.data or 0
        uc = self.unit_cost.data or 0
        dv = self.declared_value.data
        if dv is not None and dv < (q * uc):
            self.declared_value.errors.append('القيمة المعلنة يجب ألا تقل عن (الكمية × سعر الوحدة).')
            return False
        return True


class ShipmentPartnerForm(FlaskForm):
    shipment_id = HiddenField(validators=[Optional()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', coerce=int, validators=[DataRequired()])
    role = StringField('الدور', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=500)])
    identity_number = StringField('رقم الهوية/السجل', validators=[Optional(), Length(max=100)])
    phone_number = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])
    expiry_date = DateField('تاريخ الانتهاء', format='%Y-%m-%d', validators=[Optional()])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount = DecimalField('مساهمة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        sp, sa = self.share_percentage.data, self.share_amount.data
        if sp in (None, '') and sa in (None, ''):
            self.share_percentage.errors.append('حدد نسبة الشريك أو قيمة مساهمته على الأقل.')
            self.share_amount.errors.append('حدد نسبة الشريك أو قيمة مساهمته على الأقل.')
            return False
        return True


class ShipmentForm(FlaskForm):
    shipment_number = StringField('رقم الشحنة', validators=[Optional(), Length(max=50)])
    shipment_date = DateTimeField('تاريخ الشحن', format='%Y-%m-%d %H:%M',
                                  validators=[Optional()],
                                  render_kw={'autocomplete':'off','dir':'ltr','class':'dtp'})
    expected_arrival = DateTimeField('الوصول المتوقع', format='%Y-%m-%d %H:%M',
                                     validators=[Optional()],
                                     render_kw={'autocomplete':'off','dir':'ltr','class':'dtp'})
    actual_arrival = DateTimeField('الوصول الفعلي', format='%Y-%m-%d %H:%M',
                                   validators=[Optional()],
                                   render_kw={'autocomplete':'off','dir':'ltr','class':'dtp'})
    origin = StringField('المنشأ', validators=[Optional(), Length(max=100)])
    destination = StringField('الوجهة', validators=[Optional(), Length(max=100)])
    destination_id = QuerySelectField('مخزن الوجهة', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), allow_blank=False, get_label='name')
    status = SelectField('الحالة', choices=[('DRAFT','DRAFT'), ('IN_TRANSIT','IN_TRANSIT'), ('ARRIVED','ARRIVED'), ('CANCELLED','CANCELLED')], default='DRAFT', validators=[DataRequired()])
    value_before = DecimalField('قيمة البضائع قبل المصاريف', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={'readonly': True})
    shipping_cost = DecimalField('تكلفة الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    customs = DecimalField('الجمارك', places=2, validators=[Optional(), NumberRange(min=0)])
    vat = DecimalField('ضريبة القيمة المضافة', places=2, validators=[Optional(), NumberRange(min=0)])
    insurance = DecimalField('التأمين', places=2, validators=[Optional(), NumberRange(min=0)])
    total_value = DecimalField('الإجمالي', places=2, validators=[Optional(), NumberRange(min=0)])
    carrier = StringField('شركة النقل', validators=[Optional(), Length(max=100)])
    tracking_number = StringField('رقم التتبع', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='USD', validators=[DataRequired()])
    sale_id = QuerySelectField('البيع المرتبط', query_factory=lambda: Sale.query.order_by(Sale.sale_number).all(), allow_blank=True, get_label='sale_number')
    items = FieldList(FormField(ShipmentItemForm), min_entries=1)
    partners = FieldList(FormField(ShipmentPartnerForm), min_entries=0)
    submit = SubmitField('حفظ الشحنة')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if not any(f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1 for f in (entry.form for entry in self.items)):
            self.items.errors.append('أدخل عنصرًا واحدًا على الأقل.')
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
        shipment.total_value = self.total_value.data or None
        shipment.carrier = (self.carrier.data or '').strip() or None
        shipment.tracking_number = (self.tracking_number.data or '').strip() or None
        shipment.notes = (self.notes.data or '').strip() or None
        dest_obj = self.destination_id.data
        shipment.destination_id = dest_obj.id if dest_obj else None
        sale_obj = self.sale_id.data
        shipment.sale_id = sale_obj.id if sale_obj else None
        shipment.items = [ShipmentItem(product_id=int(f.product_id.data), warehouse_id=int(f.warehouse_id.data), quantity=int(f.quantity.data), unit_cost=f.unit_cost.data or 0, declared_value=f.declared_value.data, notes=(f.notes.data or '').strip() or None) for f in (entry.form for entry in self.items) if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1]
        shipment.partners = [ShipmentPartner(partner_id=int(f.partner_id.data), role=(f.role.data or '').strip() or None, notes=(f.notes.data or '').strip() or None, identity_number=(f.identity_number.data or '').strip() or None, phone_number=(f.phone_number.data or '').strip() or None, address=(f.address.data or '').strip() or None, unit_price_before_tax=f.unit_price_before_tax.data or None, expiry_date=f.expiry_date.data or None, share_percentage=f.share_percentage.data or None, share_amount=f.share_amount.data or None) for f in (entry.form for entry in self.partners) if f.partner_id.data]
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
    name = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    position = StringField('الوظيفة', validators=[Optional(), Length(max=100)])
    phone = StringField('الجوال', validators=[Optional(), Length(max=100)])
    email = StringField('البريد', validators=[Optional(), Email(), Length(max=120)])
    bank_name = StringField('البنك', validators=[Optional(), Length(max=100)])
    account_number = StringField('رقم الحساب', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit = SubmitField('حفظ الموظف')

    def validate_phone(self, field):
        s = (field.data or "").strip()
        if s:
            s = re.sub(r"\D+", "", s)
        field.data = s or None

    def validate_email(self, field):
        e = (field.data or "").strip().lower()
        field.data = e or None


class ExpenseTypeForm(FlaskForm):
    id = HiddenField(validators=[Optional()])
    name = StringField('اسم نوع المصروف', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('وصف اختياري', validators=[Optional(), Length(max=500)])
    is_active = BooleanField('مُفعّل', default=True)
    submit = SubmitField('حفظ')

    def validate_name(self, field):
        name = (field.data or "").strip()
        qy = ExpenseType.query.filter(func.lower(ExpenseType.name) == name.lower())
        if (self.id.data or "").isdigit():
            qy = qy.filter(ExpenseType.id != int(self.id.data))
        if qy.first():
            raise ValidationError("اسم نوع المصروف موجود مسبقًا.")

    def apply_to(self, obj):
        obj.name = (self.name.data or "").strip()
        obj.description = (self.description.data or "").strip() or None
        obj.is_active = bool(self.is_active.data)
        return obj


class ExpenseForm(FlaskForm):
    date = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[DataRequired()])
    amount = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    type_id = SelectField('نوع المصروف', coerce=int, validators=[DataRequired()])
    employee_id = AjaxSelectField('الموظف', endpoint='api.employees', get_label='name', validators=[Optional()])
    warehouse_id = AjaxSelectField('المستودع', endpoint='api.warehouses', get_label='name', validators=[Optional()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    paid_to = StringField('مدفوع إلى', validators=[Optional(), Length(max=200)])
    payment_method = SelectField('طريقة الدفع', choices=[('cash', 'نقدًا'), ('cheque', 'شيك'), ('bank', 'تحويل بنكي'), ('card', 'بطاقة/ائتمان'), ('online', 'إلكتروني'), ('other', 'أخرى')], validators=[DataRequired()])
    check_number = StringField('رقم الشيك', validators=[Optional(), Length(max=100)])
    check_bank = StringField('البنك', validators=[Optional(), Length(max=100)])
    check_due_date = DateField('تاريخ الاستحقاق', format='%Y-%m-%d', validators=[Optional()])
    bank_transfer_ref = StringField('مرجع التحويل', validators=[Optional(), Length(max=100)])
    card_number = StringField('رقم البطاقة', validators=[Optional(), Length(max=19)])
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_expiry = StringField('MM/YY', validators=[Optional(), Length(max=7)])
    online_gateway = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    online_ref = StringField('مرجع العملية', validators=[Optional(), Length(max=100)])
    payment_details = StringField('تفاصيل إضافية', validators=[Optional(), Length(max=255)])
    description = StringField('وصف مختصر', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    tax_invoice_number = StringField('رقم فاتورة ضريبية', validators=[Optional(), Length(max=100)])
    submit = SubmitField('حفظ')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        m = (self.payment_method.data or '').lower()
        if m == 'cheque':
            if not self.check_number.data:
                self.check_number.errors.append('❌ أدخل رقم الشيك')
                return False
            if not self.check_bank.data:
                self.check_bank.errors.append('❌ أدخل اسم البنك')
                return False
            if not self.check_due_date.data:
                self.check_due_date.errors.append('❌ أدخل تاريخ الاستحقاق')
                return False
            if self.date.data and self.check_due_date.data and self.check_due_date.data < self.date.data:
                self.check_due_date.errors.append('❌ تاريخ الاستحقاق لا يمكن أن يسبق تاريخ العملية')
                return False
        elif m == 'bank':
            if not self.bank_transfer_ref.data:
                self.bank_transfer_ref.errors.append('❌ أدخل مرجع التحويل البنكي')
                return False
        elif m == 'card':
            raw = only_digits(self.card_number.data or '')
            if not (raw.isdigit() and luhn_check(raw)):
                self.card_number.errors.append('❌ رقم البطاقة غير صالح')
                return False
            if not self.card_holder.data:
                self.card_holder.errors.append('❌ أدخل اسم حامل البطاقة')
                return False
            if self.card_expiry.data and not is_valid_expiry_mm_yy(self.card_expiry.data):
                self.card_expiry.errors.append('❌ تاريخ الانتهاء غير صالح')
                return False
        elif m == 'online':
            if not self.online_gateway.data:
                self.online_gateway.errors.append('❌ أدخل بوابة الدفع')
                return False
            if not self.online_ref.data:
                self.online_ref.errors.append('❌ أدخل مرجع العملية')
                return False
        return True

    def build_payment_details(self):
        m = (self.payment_method.data or '').lower()
        details = {'type': m or 'other'}
        if m == 'cheque':
            details.update({'number': self.check_number.data, 'bank': self.check_bank.data, 'due_date': self.check_due_date.data.isoformat() if self.check_due_date.data else None})
        elif m == 'bank':
            details.update({'transfer_ref': self.bank_transfer_ref.data})
        elif m == 'card':
            raw = only_digits(self.card_number.data or '')
            masked = ('*' * max(len(raw) - 4, 0) + raw[-4:]) if raw else None
            details.update({'holder': self.card_holder.data, 'number_masked': masked, 'expiry': self.card_expiry.data})
        elif m == 'online':
            details.update({'gateway': self.online_gateway.data, 'ref': self.online_ref.data})
        if self.payment_details.data:
            details['extra'] = self.payment_details.data
        return json.dumps({k: v for k, v in details.items() if v}, ensure_ascii=False)

    def apply_to(self, exp):
        exp.date = datetime.combine(self.date.data, datetime.min.time())
        exp.amount = self.amount.data
        exp.currency = (self.currency.data or 'ILS').upper()
        exp.type_id = int(self.type_id.data) if self.type_id.data else None
        exp.employee_id = int(self.employee_id.data) if getattr(self.employee_id, "data", None) else None
        exp.warehouse_id = int(self.warehouse_id.data) if getattr(self.warehouse_id, "data", None) else None
        exp.partner_id = int(self.partner_id.data) if getattr(self.partner_id, "data", None) else None
        exp.paid_to = (self.paid_to.data or '').strip() or None
        exp.description = (self.description.data or '').strip() or None
        exp.notes = (self.notes.data or '').strip() or None
        exp.tax_invoice_number = (self.tax_invoice_number.data or '').strip() or None
        exp.payment_method = (self.payment_method.data or '').lower()
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
        return exp


class CustomerFormOnline(FlaskForm):
    name = StringField('الاسم الكامل', validators=[DataRequired(), Length(max=100)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('رقم الجوال', validators=[DataRequired(), Length(min=7, max=20)])
    whatsapp = StringField('واتساب', validators=[DataRequired(), Length(min=7, max=20)])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6, max=128)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
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


class CustomerPasswordResetRequestForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    submit = SubmitField('إرسال رابط إعادة تعيين')


class CustomerPasswordResetForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password', message="كلمتا المرور غير متطابقتين")])
    submit = SubmitField('تحديث كلمة المرور')


class AddToOnlineCartForm(FlaskForm):
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1, message="❌ الحد الأدنى 1")])
    submit = SubmitField('أضف للسلة')


class OnlinePaymentForm(FlaskForm):
    payment_ref = StringField('مرجع الدفع', validators=[DataRequired(), Length(max=100)])
    order_id = IntegerField('رقم الطلب', validators=[DataRequired(), NumberRange(min=1)])
    amount = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=[('ILS', 'ILS'), ('USD', 'USD'), ('EUR', 'EUR'), ('JOD', 'JOD')], default='ILS', validators=[DataRequired()])
    method = StringField('وسيلة الدفع', validators=[Optional(), Length(max=50)])
    gateway = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    status = SelectField('حالة المعاملة', choices=[('PENDING', 'قيد الانتظار'), ('SUCCESS', 'مكتملة'), ('FAILED', 'فاشلة'), ('REFUNDED', 'مُرجعة')], default='PENDING', validators=[DataRequired()])
    transaction_data = TextAreaField('بيانات المعاملة (JSON)', validators=[Optional()])
    processed_at = DateTimeField('تاريخ المعالجة', format='%Y-%m-%d %H:%M', validators=[Optional()])
    card_last4 = StringField('آخر 4 أرقام', validators=[Optional(), Length(min=4, max=4)])
    card_encrypted = TextAreaField('بيانات البطاقة المشفّرة', validators=[Optional(), Length(max=8000)])
    card_expiry = StringField('انتهاء البطاقة (MM/YY)', validators=[Optional(), Length(max=7)])
    cardholder_name = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_brand = SelectField('نوع البطاقة', choices=[('', 'غير محدد'), ('VISA', 'VISA'), ('MASTERCARD', 'MASTERCARD'), ('AMEX', 'AMEX'), ('DISCOVER', 'DISCOVER'), ('OTHER', 'OTHER')], validators=[Optional()])
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

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        st = (self.status.data or "").upper()
        if st == "COMPLETED":
            st = "SUCCESS"
            self.status.data = "SUCCESS"
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
    direction = SelectField('النوع', choices=[('IN', 'إدخال'), ('OUT', 'إخراج'), ('ADJUSTMENT', 'تسوية')], validators=[DataRequired()], coerce=str)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = DecimalField('التكلفة للوحدة', places=2, validators=[Optional(), NumberRange(min=0)])
    is_priced = BooleanField('مسعّر', default=False)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ')

    def _numstr(self, v):
        if v in (None, ""):
            return None
        s = str(v).strip()
        s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
        s = s.replace("٫", ".").replace("٬", "").replace(",", "")
        return s

    def _to_int(self, v):
        try:
            s = self._numstr(v)
            return int(s) if s is not None and s != "" else None
        except Exception:
            return None

    def _d(self, x):
        from decimal import Decimal, InvalidOperation
        s = self._numstr(x)
        if not s:
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError, TypeError):
            return None

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        self.direction.data = (self.direction.data or "").upper()
        wid = self._to_int(self.warehouse_id.data)
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
            except Exception:
                self.warehouse_id.errors.append('تعذر التحقق من المخزن.')
                return False
        if (self.direction.data or '').upper() == 'OUT':
            pid = self._to_int(self.product_id.data)
            q = self._to_int(self.quantity.data) or 0
            if pid and wid and q:
                try:
                    from models import StockLevel
                    sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
                    avail = (sl.quantity if sl else 0) - (sl.reserved_quantity if sl else 0)
                    if q > max(int(avail or 0), 0):
                        self.quantity.errors.append('الكمية غير كافية في المخزن.')
                        return False
                except Exception:
                    pass
        return True

    def apply_to(self, xt):
        xt.product_id = self._to_int(self.product_id.data)
        xt.warehouse_id = self._to_int(self.warehouse_id.data)
        xt.partner_id = self._to_int(self.partner_id.data) if self.partner_id.data else None
        xt.direction = (self.direction.data or '').upper()
        xt.quantity = self._to_int(self.quantity.data) or 1
        uc = self._d(self.unit_cost.data)
        xt.unit_cost = uc if uc is not None else None
        xt.is_priced = bool(uc is not None and uc > 0)
        xt.notes = (self.notes.data or '').strip() or None
        return xt


class EquipmentTypeForm(FlaskForm):
    name = StringField('اسم نوع المعدة', validators=[DataRequired(), Length(max=100)])
    model_number = StringField('رقم النموذج', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    category = StringField('الفئة', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ نوع المعدة')


class ServiceTaskForm(FlaskForm):
    service_id = HiddenField(validators=[DataRequired()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    description = StringField('وصف المهمة', validators=[DataRequired(), Length(max=200)])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StringField('ملاحظات', validators=[Optional(), Length(max=200)])
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
    estimated_cost = DecimalField('التكلفة المتوقعة', places=2, validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('حفظ التشخيص')

    def apply_to(self, diag):
        diag.problem_description = (self.problem_description.data or '').strip()
        diag.diagnosis = (self.diagnosis.data or '').strip()
        diag.resolution = (self.resolution.data or '').strip()
        diag.estimated_duration = int(self.estimated_duration.data or 0) if self.estimated_duration.data else None
        diag.estimated_cost = self.estimated_cost.data or None
        return diag


class ServicePartForm(FlaskForm):
    service_id = HiddenField(validators=[Optional()])
    part_id = AjaxSelectField('القطعة/المكوّن', endpoint='api.products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StringField('ملاحظة', validators=[Optional(), Length(max=200)])
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
        return sp

class SaleLineForm(FlaskForm):
    class Meta:
        csrf = False
    sale_id       = HiddenField(validators=[Optional()])
    product_id    = AjaxSelectField('الصنف', endpoint='api.products', get_label='name', coerce=int, validators=[Optional()])
    warehouse_id  = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', coerce=int, validators=[Optional()])
    quantity      = IntegerField('الكمية', validators=[Optional(), NumberRange(min=1)])
    unit_price    = DecimalField('سعر الوحدة', places=2, validators=[Optional(), NumberRange(min=0)])
    discount_rate = DecimalField('خصم %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate      = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    note          = StringField('ملاحظات', validators=[Optional(), Length(max=200)])


class SaleForm(FlaskForm):
    sale_number    = StringField('رقم البيع', validators=[Optional(), Length(max=50)])
    sale_date      = DateTimeLocalField('تاريخ البيع', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    customer_id    = AjaxSelectField('العميل', endpoint='api.customers', get_label='name', coerce=int, validators=[DataRequired()])
    seller_id      = AjaxSelectField('البائع', endpoint='api.users', get_label='username', coerce=int, validators=[DataRequired()])
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
    discount_total   = DecimalField('خصم إجمالي', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=500)])
    billing_address  = TextAreaField('عنوان الفواتير', validators=[Optional(), Length(max=500)])
    shipping_cost    = DecimalField('تكلفة الشحن', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    notes            = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    total_amount     = DecimalField('الإجمالي النهائي', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    lines            = FieldList(FormField(SaleLineForm), min_entries=1)
    preorder_id      = IntegerField('رقم الحجز', validators=[Optional()])
    submit           = SubmitField('حفظ البيع')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
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
        sale.status           = (self.status.data or SaleStatus.DRAFT.value)
        sale.payment_status   = (self.payment_status.data or PaymentProgress.PENDING.value)
        sale.currency         = (self.currency.data or 'ILS').upper()
        sale.tax_rate         = self.tax_rate.data or 0
        sale.discount_total   = self.discount_total.data or 0
        sale.shipping_address = (self.shipping_address.data or '').strip() or None
        sale.billing_address  = (self.billing_address.data or '').strip() or None
        sale.shipping_cost    = self.shipping_cost.data or 0
        sale.notes            = (self.notes.data or '').strip() or None
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
            for f in (entry.form for entry in self.lines)
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1
        ]
        return sale


def _norm_invoice_no(v: str | None) -> str | None:
    s = (v or "").strip()
    s = re.sub(r"\s+", "", s)
    return s.upper() or None


class InvoiceLineForm(FlaskForm):
    invoice_id  = HiddenField(validators=[Optional()])
    product_id  = AjaxSelectField('الصنف', endpoint='api.products', get_label='name', coerce=int, validators=[DataRequired()])
    description = StringField('الوصف', validators=[DataRequired(), Length(max=200)])
    quantity    = DecimalField('الكمية', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    unit_price  = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tax_rate    = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    discount    = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])


class ProductPartnerShareForm(FlaskForm):
    product_id = HiddenField(validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()])
    share_percentage = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount = DecimalField('قيمة مساهمة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('حفظ')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        sp = self.share_percentage.data
        sa = self.share_amount.data
        if (sp in (None, '') or float(sp or 0) == 0) and (sa in (None, '') or float(sa or 0) == 0):
            self.share_percentage.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            self.share_amount.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            return False
        return True


class ProductCategoryForm(FlaskForm):
    name = StringField('اسم الفئة', validators=[DataRequired(), Length(max=100)])
    parent_id = AjaxSelectField('الفئة الأب', endpoint='api.search_categories', get_label='name', validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    image_url = StringField('رابط الصورة', validators=[Optional()])
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
    sku = StringField('SKU', validators=[
        Optional(),
        Length(max=50),
        Unique(Product, 'sku', message='SKU مستخدم بالفعل.', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())
    ])
    name = StringField('الاسم', validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('الوصف', validators=[Optional()])
    part_number = StringField('رقم القطعة', validators=[Optional(), Length(max=100)])
    brand = StringField('الماركة', validators=[Optional(), Length(max=100)])
    commercial_name = StringField('الاسم التجاري', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    serial_no = StringField('الرقم التسلسلي', validators=[
        Optional(),
        Length(max=100),
        Unique(Product, 'serial_no', message='الرقم التسلسلي مستخدم بالفعل.', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())
    ])
    barcode = StringField('الباركود', validators=[
        Optional(),
        Length(max=100),
        Unique(Product, 'barcode', message='الباركود مستخدم بالفعل.', case_insensitive=True, normalizer=normalize_barcode)
    ])
    cost_before_shipping = DecimalField('التكلفة قبل الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    cost_after_shipping = DecimalField('التكلفة بعد الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])
    price = DecimalField('السعر الأساسي', places=2, validators=[DataRequired(), NumberRange(min=0)])
    purchase_price = DecimalField('سعر الشراء', places=2, validators=[Optional(), NumberRange(min=0)])
    selling_price = DecimalField('سعر البيع', places=2, validators=[Optional(), NumberRange(min=0)])
    min_price = DecimalField('السعر الأدنى', places=2, validators=[Optional(), NumberRange(min=0)])
    max_price = DecimalField('السعر الأعلى', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('نسبة الضريبة', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    unit = StringField('الوحدة', validators=[Optional(), Length(max=50)])
    min_qty = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    reorder_point = IntegerField('نقطة إعادة الطلب', validators=[Optional(), NumberRange(min=0)])
    condition = SelectField('الحالة', choices=[
        (ProductCondition.NEW.value, 'جديد'),
        (ProductCondition.USED.value, 'مستعمل'),
        (ProductCondition.REFURBISHED.value, 'مجدّد')
    ], validators=[DataRequired()])
    origin_country = StringField('بلد المنشأ', validators=[Optional(), Length(max=50)])
    warranty_period = IntegerField('مدة الضمان', validators=[Optional(), NumberRange(min=0)])
    weight = DecimalField('الوزن', places=2, validators=[Optional(), NumberRange(min=0)])
    dimensions = StringField('الأبعاد', validators=[Optional(), Length(max=50)])
    image = StringField('صورة', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('نشط', default=True)
    is_digital = BooleanField('منتج رقمي', default=False)
    is_exchange = BooleanField('قابل للتبادل', default=False)
    vehicle_type_id = AjaxSelectField('نوع المركبة', endpoint='api.search_equipment_types', get_label='name', validators=[Optional()], coerce=int)
    category_id = AjaxSelectField('الفئة', endpoint='api.search_categories', get_label='name', coerce=int, validators=[DataRequired(message="يجب اختيار فئة للمنتج")], render_kw={'required': True})
    category_name = StringField('اسم الفئة (نصي)', validators=[Optional(), Length(max=100)])
    supplier_id = AjaxSelectField('المورد الرئيسي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()], coerce=int)
    supplier_international_id = AjaxSelectField('المورد الدولي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()], coerce=int)
    supplier_local_id = AjaxSelectField('المورد المحلي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()], coerce=int)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        pp = self.purchase_price.data
        pr = self.price.data
        sp = self.selling_price.data
        if sp is None and pr is not None:
            sp = pr
            self.selling_price.data = sp
        if pr is None and sp is not None:
            pr = sp
            self.price.data = pr
        if pp is not None:
            if pr is not None and pr < pp:
                self.price.errors.append('السعر الأساسي لا يجب أن يكون أقل من سعر الشراء.')
                return False
            if sp is not None and sp < pp:
                self.selling_price.errors.append('سعر البيع لا يجب أن يكون أقل من سعر الشراء.')
                return False
        mn = self.min_price.data
        mx = self.max_price.data
        if mn is not None:
            if pr is not None and pr < mn:
                self.price.errors.append('السعر الأساسي أقل من السعر الأدنى.')
                return False
            if sp is not None and sp < mn:
                self.selling_price.errors.append('سعر البيع أقل من السعر الأدنى.')
                return False
        if mx is not None:
            if pr is not None and pr > mx:
                self.price.errors.append('السعر الأساسي أعلى من السعر الأعلى.')
                return False
            if sp is not None and sp > mx:
                self.selling_price.errors.append('سعر البيع أعلى من السعر الأعلى.')
                return False
        rq = self.reorder_point.data
        mq = self.min_qty.data
        if rq is not None and mq is not None and rq < mq:
            self.reorder_point.errors.append('نقطة إعادة الطلب يجب أن تكون ≥ الحد الأدنى للمخزون.')
            return False
        return True

    def apply_to(self, p: Product) -> Product:
        p.sku = (self.sku.data or '').strip() or None
        p.name = (self.name.data or '').strip()
        p.description = (self.description.data or '').strip() or None
        p.part_number = (self.part_number.data or '').strip() or None
        p.brand = (self.brand.data or '').strip() or None
        p.commercial_name = (self.commercial_name.data or '').strip() or None
        p.chassis_number = (self.chassis_number.data or '').strip() or None
        p.serial_no = (self.serial_no.data or '').strip() or None
        p.barcode = (self.barcode.data or '').strip() or None
        p.cost_before_shipping = self.cost_before_shipping.data or 0
        p.cost_after_shipping = self.cost_after_shipping.data or 0
        p.unit_price_before_tax = self.unit_price_before_tax.data or 0
        base_price = self.price.data
        sell_price = self.selling_price.data or base_price
        if base_price is None and sell_price is not None:
            base_price = sell_price
        p.price = base_price or 0
        p.selling_price = sell_price or 0
        p.purchase_price = self.purchase_price.data or 0
        p.min_price = self.min_price.data or None
        p.max_price = self.max_price.data or None
        p.tax_rate = self.tax_rate.data or 0
        p.unit = (self.unit.data or '').strip() or None
        p.min_qty = int(self.min_qty.data) if self.min_qty.data is not None else 0
        p.reorder_point = int(self.reorder_point.data) if self.reorder_point.data is not None else None
        p.condition = self.condition.data or ProductCondition.NEW.value
        p.origin_country = (self.origin_country.data or '').strip() or None
        p.warranty_period = int(self.warranty_period.data) if self.warranty_period.data is not None else None
        p.weight = self.weight.data or None
        p.dimensions = (self.dimensions.data or '').strip() or None
        p.image = (self.image.data or '').strip() or None
        p.is_active = bool(self.is_active.data)
        p.is_digital = bool(self.is_digital.data)
        p.is_exchange = bool(self.is_exchange.data)
        p.vehicle_type_id = int(self.vehicle_type_id.data) if self.vehicle_type_id.data else None
        p.category_id = int(self.category_id.data) if self.category_id.data else None
        p.category_name = (self.category_name.data or '').strip() or None
        p.supplier_id = int(self.supplier_id.data) if self.supplier_id.data else None
        p.supplier_international_id = int(self.supplier_international_id.data) if self.supplier_international_id.data else None
        p.supplier_local_id = int(self.supplier_local_id.data) if self.supplier_local_id.data else None
        p.notes = (self.notes.data or '').strip() or None
        return p

    def validate_barcode(self, field):
        if not field.data:
            return
        r = validate_barcode(field.data)
        if not r["normalized"]:
            raise ValidationError("الباركود يجب أن يكون 12 أو 13 خانة رقمية.")
        if not r["valid"]:
            if r.get("suggested"):
                raise ValidationError(f"الباركود غير صالح. المُقترَح الصحيح: {r['suggested']}")
            raise ValidationError("الباركود غير صالح.")
        field.data = r["normalized"]

class WarehouseForm(FlaskForm):
    name = StringField('اسم المستودع', validators=[DataRequired(), Length(max=100)])
    warehouse_type = SelectField(
        'نوع المستودع',
        choices=[(t.value, t.value) for t in WarehouseType],
        validators=[DataRequired()],
        coerce=str
    )
    location = StringField('الموقع', validators=[Optional(), Length(max=200)])
    parent_id = AjaxSelectField('المستودع الأب', endpoint='api.search_warehouses', get_label='name', validators=[Optional()])
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()])
    supplier_id = AjaxSelectField('المورد', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])
    share_percent = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    capacity = IntegerField('السعة القصوى', validators=[Optional(), NumberRange(min=0)])
    current_occupancy = IntegerField('المشغول حاليًا', validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    is_active = BooleanField('نشط', default=True)
    submit = SubmitField('حفظ المستودع')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False

        cap = self.capacity.data
        occ = self.current_occupancy.data
        if cap is not None and occ is not None and occ > cap:
            self.current_occupancy.errors.append('المشغول حاليًا لا يمكن أن يتجاوز السعة القصوى.')
            return False

        wt = (self.warehouse_type.data or '').upper()
        if wt != 'PARTNER' and self.share_percent.data is None:
            self.share_percent.data = 0

        return True

class PartnerShareForm(FlaskForm):
    partner_id = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()])
    share_percentage = DecimalField('نسبة المشاركة (%)', places=2, validators=[DataRequired(), NumberRange(min=0, max=100)])
    partner_phone = StringField('هاتف الشريك', validators=[Optional(), Length(max=20)])
    partner_identity = StringField('هوية الشريك', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ')


class ExchangeVendorForm(FlaskForm):
    supplier_id = AjaxSelectField('المورّد / التاجر', endpoint='api.search_suppliers', get_label='name', validators=[DataRequired()])
    vendor_phone = StringField('هاتف المورد', validators=[Optional(), Length(max=50)])
    vendor_paid = DecimalField('المبلغ المدفوع', places=2, validators=[Optional(), NumberRange(min=0)])
    vendor_price = DecimalField('سعر المورد', places=2, validators=[Optional(), NumberRange(min=0)])
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

    def _to_int(self, v):
        try:
            trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
            return int(str(v).translate(trans).strip())
        except Exception:
            return None

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        q = self._to_int(self.quantity.data) or 0
        rq = self._to_int(self.reserved_quantity.data) or 0
        if rq > q:
            self.reserved_quantity.errors.append('المحجوز لا يجوز أن يتجاوز الكمية.')
            return False
        mn = self._to_int(self.min_stock.data) if self.min_stock.data not in (None, "") else None
        mx = self._to_int(self.max_stock.data) if self.max_stock.data not in (None, "") else None
        if mn is not None and mx is not None and mx < mn:
            self.max_stock.errors.append('الحد الأقصى يجب أن يكون ≥ الحد الأدنى.')
            return False
        pid = self._to_int(self.product_id.data)
        wid = self._to_int(self.warehouse_id.data)
        if not pid or not wid:
            return False
        try:
            from models import StockLevel
            existing = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
            cur_id = self._to_int(self.id.data) if self.id.data else None
            if existing and (cur_id is None or existing.id != cur_id):
                self.warehouse_id.errors.append('يوجد صف مخزون لنفس الصنف والمخزن.')
                return False
        except Exception:
            pass
        return True

    def apply_to(self, sl):
        sl.product_id = self._to_int(self.product_id.data)
        sl.warehouse_id = self._to_int(self.warehouse_id.data)
        sl.quantity = self._to_int(self.quantity.data) or 0
        sl.reserved_quantity = self._to_int(self.reserved_quantity.data) or 0
        sl.min_stock = self._to_int(self.min_stock.data) if self.min_stock.data not in (None, "") else None
        sl.max_stock = self._to_int(self.max_stock.data) if self.max_stock.data not in (None, "") else None
        return sl


class InventoryAdjustmentForm(FlaskForm):
    product_id = AjaxSelectField('المنتج', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    adjustment_type = SelectField('نوع التعديل', choices=[('IN', 'إضافة'), ('OUT', 'إزالة'), ('ADJUSTMENT', 'تصحيح')], default='ADJUSTMENT', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('السبب', validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField('تطبيق التعديل')


class NoteForm(FlaskForm):
    author_id = HiddenField(validators=[Optional()])
    content = TextAreaField('المحتوى', validators=[DataRequired(), Length(max=1000)])
    entity_type = SelectField('نوع الكيان', choices=[], validators=[Optional()])
    entity_id = StringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    is_pinned = BooleanField('مثبّتة')
    priority = SelectField('الأولوية', choices=[('LOW', 'منخفضة'), ('MEDIUM', 'متوسطة'), ('HIGH', 'عالية'), ('URGENT', 'عاجلة')], default='MEDIUM', validators=[Optional()])
    submit = SubmitField('💾 حفظ')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        et = (self.entity_type.data or '').strip()
        eid = (self.entity_id.data or '').strip()
        if et and not eid:
            self.entity_id.errors.append('أدخل معرّف الكيان.')
            return False
        if eid and not et:
            self.entity_type.errors.append('حدد نوع الكيان.')
            return False
        return True

# --------- Accounting / Ledger ----------

class AccountForm(FlaskForm):
    id = HiddenField()
    code = StringField('كود الحساب', validators=[
        DataRequired(),
        Length(max=20),
        Unique(Account, 'code', message='الكود مستخدم مسبقًا', case_insensitive=True, normalizer=lambda v: (v or '').strip().upper())
    ])
    name = StringField('اسم الحساب', validators=[DataRequired(), Length(max=100)])
    type = SelectField('النوع', validators=[DataRequired()], choices=[(t.value, t.value) for t in AccountType])
    parent_id = AjaxSelectField('الحساب الأب', endpoint='api.search_accounts', get_label='name', allow_blank=True, validators=[Optional()])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[DataRequired()])
    is_active = BooleanField('نشط', default=True)
    opening_balance = DecimalField('الرصيد الافتتاحي', places=2, validators=[Optional()])
    opening_balance_date = DateField('تاريخ الرصيد الافتتاحي', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('حفظ الحساب')

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
    account_id = AjaxSelectField('الحساب', endpoint='api.search_accounts', get_label='name', validators=[DataRequired()])
    debit = DecimalField('مدين', places=2, validators=[Optional(), NumberRange(min=0)])
    credit = DecimalField('دائن', places=2, validators=[Optional(), NumberRange(min=0)])
    entity_type = SelectField('نوع الكيان', choices=[('', '—'), ('CUSTOMER', 'CUSTOMER'), ('SUPPLIER', 'SUPPLIER'), ('PARTNER', 'PARTNER'), ('INVOICE', 'INVOICE'), ('SALE', 'SALE'), ('EXPENSE', 'EXPENSE'), ('SERVICE', 'SERVICE')], validators=[Optional()])
    entity_id = StringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    note = StringField('ملاحظة', validators=[Optional(), Length(max=200)])

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        db = D(self.debit.data)
        cr = D(self.credit.data)
        if db <= 0 and cr <= 0:
            self.debit.errors.append('أدخل مبلغًا في المدين أو الدائن')
            return False
        if db > 0 and cr > 0:
            self.credit.errors.append('لا يجوز أن يكون السطر مدينًا ودائنًا معًا')
            return False
        if (self.entity_id.data or '').strip() and not (self.entity_type.data or '').strip():
            self.entity_type.errors.append('حدد نوع الكيان')
            return False
        return True


class JournalEntryForm(FlaskForm):
    entry_date = DateTimeLocalField('تاريخ القيد', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    reference = StringField('المرجع', validators=[Optional(), Length(max=50)])
    description = TextAreaField('البيان', validators=[Optional(), Length(max=1000)])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[DataRequired()])
    post_now = BooleanField('ترحيل فورًا', default=True)
    lines = FieldList(FormField(JournalLineForm), min_entries=2)
    submit = SubmitField('حفظ القيد')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        total_debit = sum(D(f.form.debit.data) for f in self.lines)
        total_credit = sum(D(f.form.credit.data) for f in self.lines)
        if (total_debit - total_credit).copy_abs() > CENT:
            self.lines.errors.append('❌ مجموع المدين يجب أن يساوي مجموع الدائن')
            return False
        if not any(((f.form.debit.data or 0) > 0) or ((f.form.credit.data or 0) > 0) for f in self.lines):
            self.lines.errors.append('❌ أضف سطرًا واحدًا على الأقل')
            return False
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

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        return True


class TrialBalanceFilterForm(FlaskForm):
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    currency = SelectField('العملة', choices=CURRENCY_CHOICES, validators=[Optional()])
    include_zero = BooleanField('إظهار الحسابات الصفرية', default=False)
    submit = SubmitField('عرض الميزان')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        return True


class ClosingEntryForm(FlaskForm):
    start_date = DateField('من تاريخ', validators=[DataRequired()])
    end_date = DateField('إلى تاريخ', validators=[DataRequired()])
    revenue_accounts = AjaxSelectMultipleField('حسابات الإيرادات', endpoint='api.search_accounts', get_label='name', validators=[Optional()])
    expense_accounts = AjaxSelectMultipleField('حسابات المصاريف', endpoint='api.search_accounts', get_label='name', validators=[Optional()])
    retained_earnings_account = AjaxSelectField('حساب الأرباح المحتجزة / النتائج', endpoint='api.search_accounts', get_label='name', validators=[DataRequired()])
    submit = SubmitField('إنشاء قيد الإقفال')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ "من" يجب أن يسبق "إلى"')
            return False
        return True


# --------- Exporters ----------

class ExportContactsForm(FlaskForm):
    customer_ids = AjaxSelectMultipleField('اختر العملاء', endpoint='api.search_customers', get_label='name', validators=[DataRequired(message='❌ اختر عميلًا واحدًا على الأقل')])
    fields = SelectMultipleField('الحقول', choices=[('name', 'الاسم'), ('phone', 'الجوال'), ('whatsapp', 'واتساب'), ('email', 'البريد الإلكتروني'), ('address', 'العنوان'), ('notes', 'ملاحظات')], default=['name', 'phone', 'email'], coerce=str, validators=[Optional()])
    format = SelectField('صيغة التصدير', choices=[('vcf', 'vCard'), ('csv', 'CSV'), ('excel', 'Excel')], default='vcf', validators=[DataRequired()], coerce=str)
    submit = SubmitField('تصدير')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if not self.customer_ids.data:
            self.customer_ids.errors.append('❌ اختر عميلًا واحدًا على الأقل')
            return False
        allowed = {k for k, _ in self.fields.choices}
        sel = [f for f in (self.fields.data or []) if f in allowed]
        if not sel:
            self.fields.errors.append('❌ اختر حقلًا واحدًا على الأقل للتصدير')
            return False
        self.fields.data = sel
        return True


class OnlineCartPaymentForm(FlaskForm):
    payment_method = SelectField('طريقة الدفع', choices=[('card', 'بطاقة')], default='card', validators=[DataRequired()], coerce=str)
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=100)])
    card_number = StringField('رقم البطاقة', validators=[Optional(), Length(min=12, max=19)])
    expiry = StringField('تاريخ الانتهاء (MM/YY)', validators=[Optional(), Length(min=5, max=5)])
    cvv = StringField('CVV', validators=[Optional(), Length(min=3, max=4)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=300)])
    billing_address = TextAreaField('عنوان الفاتورة', validators=[Optional(), Length(max=300)])
    transaction_data = TextAreaField('بيانات إضافية للبوابة (JSON)', validators=[Optional()])
    save_card = BooleanField('حفظ البطاقة')
    submit = SubmitField('تأكيد الدفع')

    def _digits(self, s):
        return only_digits(s).translate(_AR_DIGITS)

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        pm = (self.payment_method.data or '').strip().lower()
        if pm != 'card':
            self.payment_method.errors.append('طريقة دفع غير مدعومة')
            return False
        self.card_number.data = self._digits(self.card_number.data or '')
        self.cvv.data = self._digits(self.cvv.data or '')
        if not (self.card_holder.data or '').strip():
            self.card_holder.errors.append('اسم حامل البطاقة مطلوب')
            return False
        if not self.card_number.data or not luhn_check(self.card_number.data):
            self.card_number.errors.append('رقم البطاقة غير صالح')
            return False
        if not is_valid_expiry_mm_yy(self.expiry.data or ''):
            self.expiry.errors.append('تاريخ الانتهاء بصيغة MM/YY وفي المستقبل')
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
        return {
            'method': 'card',
            'card': {
                'holder': (self.card_holder.data or '').strip(),
                'number': self.card_number.data,
                'expiry': (self.expiry.data or '').strip(),
                'cvv': (self.cvv.data or '').strip(),
                'save': bool(self.save_card.data),
                'last4': last4,
            },
            'shipping_address': (self.shipping_address.data or '').strip() or None,
            'billing_address': (self.billing_address.data or '').strip() or None,
            'extra': extra,
        }
