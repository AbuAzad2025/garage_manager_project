from __future__ import annotations

# -------------------- Stdlib --------------------
import json
import re
from datetime import datetime, date
from decimal import Decimal

# -------------------- Third-party --------------------
from flask import url_for
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    StringField, TextAreaField, PasswordField, SelectField, SelectMultipleField,
    DateField, DateTimeField, DecimalField, IntegerField, BooleanField,
    HiddenField, FieldList, FormField, SubmitField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange, Email, ValidationError, EqualTo
)
from sqlalchemy import func
try:
    from wtforms_sqlalchemy.fields import QuerySelectField
except Exception:
    QuerySelectField = SelectField

# -------------------- Local --------------------
from models import (
    Role, User,
    Customer, Supplier, Partner, Warehouse, StockLevel,
    Sale, SaleLine, ShipmentItem, ShipmentPartner,
    ServiceRequest, PreOrder, InvoiceLine, Product,
    Payment, PaymentSplit,
    PaymentMethod, PaymentStatus, PaymentDirection, PaymentEntityType,
    InvoiceStatus, InvoiceSource, PaymentProgress,
    ServiceStatus, ServicePriority,
    PreOrderStatus, ProductCondition,
    TransferDirection, WarehouseType,
)
from utils import luhn_check, is_valid_expiry_mm_yy
try:
    from widgets import AjaxSelectField, AjaxSelectMultipleField
except Exception:
    AjaxSelectField = SelectField
    AjaxSelectMultipleField = SelectMultipleField

# ==================== Choices ====================
CURRENCY_CHOICES = [("ILS", "ILS"), ("USD", "USD"), ("EUR", "EUR"), ("JOD", "JOD")]

def _ar_label(val, mapping): return mapping.get(val, val)

def prepare_payment_form_choices(form):
    method_labels = {
        "CASH": "نقدًا",
        "CHEQUE": "شيك",
        "BANK": "تحويل بنكي",
        "CARD": "بطاقة/ائتمان",
        "ONLINE": "إلكتروني",
        "OTHER": "أخرى",
    }
    status_labels = {
        "PENDING": "قيد الانتظار",
        "COMPLETED": "مكتمل",
        "FAILED": "فشل",
        "CANCELLED": "أُلغي",
        "REFUNDED": "مسترد",
    }
    form.method.choices = [(m.value, _ar_label(m.value, method_labels)) for m in PaymentMethod]
    form.status.choices = [(s.value, _ar_label(s.value, status_labels)) for s in PaymentStatus]
    form.direction.choices = [("IN", "وارد (IN)"), ("OUT", "صادر (OUT)")]
    if not getattr(form, "entity_type", None) or not form.entity_type.choices:
        form.entity_type.choices = [
            (PaymentEntityType.CUSTOMER.value, "عميل"),
            (PaymentEntityType.SUPPLIER.value, "مورد"),
            (PaymentEntityType.PARTNER.value,  "شريك"),
            (PaymentEntityType.SHIPMENT.value, "شحنة"),
            (PaymentEntityType.EXPENSE.value,  "مصروف"),
            (PaymentEntityType.LOAN.value,     "تسوية قرض"),
            (PaymentEntityType.SALE.value,     "بيع"),
            (PaymentEntityType.INVOICE.value,  "فاتورة"),
            (PaymentEntityType.PREORDER.value, "حجز مسبق"),
            (PaymentEntityType.SERVICE.value,  "خدمة"),
        ]

INVOICE_STATUS_CHOICES       = [(s.value, s.value) for s in InvoiceStatus]
INVOICE_SOURCE_CHOICES       = [(s.value, s.value) for s in InvoiceSource]
PAYMENT_STATUS_CHOICES       = [(s.value, s.value) for s in PaymentStatus]
PAYMENT_DIRECTION_CHOICES    = [(s.value, s.value) for s in PaymentDirection]
PAYMENT_ENTITY_CHOICES       = [(s.value, s.value) for s in PaymentEntityType]
SERVICE_STATUS_CHOICES       = [(s.value, s.value) for s in ServiceStatus]
SERVICE_PRIORITY_CHOICES     = [(s.value, s.value) for s in ServicePriority]
TRANSFER_DIRECTION_CHOICES   = [(s.value, s.value) for s in TransferDirection]
WAREHOUSE_TYPE_CHOICES       = [(s.value, s.value) for s in WarehouseType]
PREORDER_STATUS_CHOICES      = [(s.value, s.value) for s in PreOrderStatus]
PRODUCT_CONDITION_CHOICES    = [(s.value, s.value) for s in ProductCondition]
NOTE_PRIORITY_CHOICES        = [("LOW", "LOW"), ("MEDIUM", "MEDIUM"), ("HIGH", "HIGH")]

# ==================== Validators / Helpers ====================
def _percent_validator(): return NumberRange(min=0, max=100)
def _nonneg_decimal():    return NumberRange(min=0)

def Unique(model, field_name, message=None, case_insensitive=False):
    def _validator(form, field):
        value = field.data
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return
        col = getattr(model, field_name)
        q = model.query
        if case_insensitive and isinstance(value, str):
            q = q.filter(func.lower(col) == value.strip().lower())
        else:
            q = q.filter(col == value)
        current_id = None
        try:
            if getattr(form, "id", None) and form.id.data:
                current_id = int(form.id.data)
        except Exception:
            current_id = None
        if current_id:
            q = q.filter(model.id != current_id)
        if q.first() is not None:
            raise ValidationError(message or "القيمة موجودة مسبقًا")
    return _validator

def unique_email_validator(model, field_name="email", allow_null=False, case_insensitive=True):
    def _validator(form, field):
        val = (field.data or "").strip()
        if not val:
            if allow_null:
                return
            raise ValidationError("هذا الحقل مطلوب")
        col = getattr(model, field_name)
        q = model.query
        q = q.filter(func.lower(col) == val.lower()) if case_insensitive else q.filter(col == val)
        current_id = None
        for attr in ("id", "obj_id"):
            if getattr(form, attr, None):
                try:
                    if getattr(form, attr).data:
                        current_id = int(getattr(form, attr).data)
                        break
                except Exception:
                    pass
        if current_id:
            q = q.filter(model.id != current_id)
        if q.first():
            raise ValidationError("هذا البريد مستخدم بالفعل.")
    return _validator

def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

# ==================== Fields ====================
class UnifiedDateTimeField(DateTimeField):
    def __init__(self, label=None, validators=None, format="%Y-%m-%d %H:%M", **kwargs):
        super().__init__(label, validators, format, **kwargs)
    def process_formdata(self, valuelist):
        if valuelist:
            date_str = " ".join(valuelist)
            try:
                self.data = datetime.strptime(date_str, self.format)
            except ValueError:
                self.data = None
                raise ValueError(self.gettext("صيغة التاريخ/الوقت غير صحيحة"))

# Fallback-safe Ajax fields (use external widgets if available)
try:
    from widgets import AjaxSelectField as _ExtAjaxSelectField
except Exception:
    _ExtAjaxSelectField = None

try:
    from widgets import AjaxSelectMultipleField as _ExtAjaxSelectMultipleField
except Exception:
    _ExtAjaxSelectMultipleField = None

if _ExtAjaxSelectField is None:
    class AjaxSelectField(SelectField):
        def __init__(self, label=None, validators=None, endpoint=None, get_label=None,
                     allow_blank=False, coerce=int, choices=None, validate_id=None, **kw):
            super().__init__(label, validators=validators or [], coerce=coerce, choices=(choices or []), **kw)
            self.endpoint = endpoint
            self.get_label = get_label
            self.allow_blank = allow_blank
            self._validate_id = validate_id
        def __call__(self, **kwargs):
            try:
                if self.endpoint and "data-url" not in kwargs:
                    kwargs["data-url"] = url_for(self.endpoint)
            except Exception:
                pass
            cls = kwargs.pop("class_", "") or kwargs.get("class", "")
            kwargs["class"] = (cls + " ajax-select form-control").strip()
            return super().__call__(**kwargs)
        def process_formdata(self, valuelist):
            if not valuelist:
                return super().process_formdata(valuelist)
            raw = valuelist[0]
            if raw in (None, "", "None"):
                self.data = None
                return
            try:
                self.data = self.coerce(raw)
            except (ValueError, TypeError):
                self.data = raw
        def pre_validate(self, form):
            if self.allow_blank and (self.data in (None, "", "None")):
                return
            if not self.choices:
                if self._validate_id and self.data not in (None, "", "None"):
                    if not self._validate_id(self.data):
                        raise ValidationError("قيمة غير صالحة.")
                return
            return super().pre_validate(form)
else:
    AjaxSelectField = _ExtAjaxSelectField

if _ExtAjaxSelectMultipleField is None:
    class AjaxSelectMultipleField(SelectMultipleField):
        def __init__(self, label=None, validators=None, endpoint=None, get_label=None,
                     coerce=int, choices=None, validate_id_many=None, **kw):
            super().__init__(label, validators=validators or [], coerce=coerce, choices=(choices or []), **kw)
            self.endpoint = endpoint
            self.get_label = get_label
            self._validate_id_many = validate_id_many
        def __call__(self, **kwargs):
            try:
                if self.endpoint and "data-url" not in kwargs:
                    kwargs["data-url"] = url_for(self.endpoint)
            except Exception:
                pass
            kwargs["multiple"] = True
            cls = kwargs.pop("class_", "") or kwargs.get("class", "")
            kwargs["class"] = (cls + " ajax-select form-control").strip()
            return super().__call__(**kwargs)
        def process_formdata(self, valuelist):
            values = []
            for v in (valuelist or []):
                if v in (None, "", "None"):
                    continue
                try:
                    values.append(self.coerce(v))
                except (ValueError, TypeError):
                    continue
            self.data = values
        def pre_validate(self, form):
            if not self.choices and self._validate_id_many:
                if self.data and not self._validate_id_many(self.data):
                    raise ValidationError("قائمة قيم غير صالحة.")
                return
            return super().pre_validate(form)
else:
    AjaxSelectMultipleField = _ExtAjaxSelectMultipleField


class CustomerImportForm(FlaskForm):
    csv_file = FileField('CSV', validators=[DataRequired()])
    submit = SubmitField('Import')

class ProductImportForm(FlaskForm):
    csv_file = FileField('CSV', validators=[DataRequired(), FileAllowed(['csv'], 'CSV only!')])
    submit = SubmitField('Import Products')

class TransferImportForm(FlaskForm):
    csv_file = FileField('CSV', validators=[DataRequired(), FileAllowed(['csv'], 'CSV only!')])
    submit = SubmitField('Import Transfers')

class RestoreForm(FlaskForm):
    db_file = FileField('نسخة .db', validators=[DataRequired(message='اختر ملف .db'), FileAllowed(['db'], 'ملف db فقط')])
    submit = SubmitField('استعادة النسخة')

class TransferForm(FlaskForm):
    transfer_date  = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[Optional()])
    reference      = StringField('المرجع', validators=[Optional(), Length(max=50)])
    user_id        = HiddenField('user_id', validators=[Optional()])

    product_id     = QuerySelectField(
        'الصنف',
        query_factory=lambda: Product.query.order_by(Product.name).all(),
        get_label='name',
        allow_blank=False,
        validators=[DataRequired()]
    )

    source_id      = QuerySelectField(
        'مخزن المصدر',
        query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
        get_label='name',
        allow_blank=False,
        validators=[DataRequired()]
    )

    destination_id = QuerySelectField(
        'مخزن الوجهة',
        query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
        get_label='name',
        allow_blank=False,
        validators=[DataRequired()]
    )

    quantity       = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    direction      = SelectField('الاتجاه', choices=[(d.value, d.name) for d in TransferDirection], validators=[DataRequired()])
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit         = SubmitField('حفظ التحويل')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False

        src = self.source_id.data
        dst = self.destination_id.data
        if src and dst and getattr(src, "id", None) == getattr(dst, "id", None):
            self.destination_id.errors.append('❌ لا يمكن أن يكون المصدر هو نفسه الوجهة')
            return False

        product = self.product_id.data
        qty = self.quantity.data or 0
        if src and product and qty:
            sl = StockLevel.query.filter_by(product_id=product.id, warehouse_id=src.id).first()
            available = getattr(sl, "quantity", 0)
            if qty > (available or 0):
                self.quantity.errors.append(f'❌ الكمية المتاحة في مخزن المصدر أقل من المطلوب (المتاح: {available})')
                return False

        return True
    
# --------- Auth / Users / Roles ----------
class LoginForm(FlaskForm):
    username    = StringField('اسم المستخدم', validators=[DataRequired(), Length(3,50)])
    password    = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')
    submit      = SubmitField('تسجيل الدخول')

class RegistrationForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3,50)])
    email    = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    confirm  = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    role     = QuerySelectField('الدور', query_factory=lambda: Role.query.order_by(Role.name).all(), get_label='name', allow_blank=False)
    submit   = SubmitField('تسجيل')

class PasswordResetForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=6)])
    confirm  = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    submit   = SubmitField('تحديث')

class PasswordResetRequestForm(FlaskForm):
    email  = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    submit = SubmitField('إرسال رابط إعادة')

class UserForm(FlaskForm):
    username    = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=3, max=50)])
    email       = StringField('البريد الإلكتروني', validators=[DataRequired(), Email(), Length(max=120)])
    role_id     = SelectField('الدور', coerce=int, validators=[DataRequired()])
    is_active   = BooleanField('نشِط')
    # كلمة المرور اختيارية عند التعديل، مطلوبة فقط عند الإنشاء (تحكمها في الفيو)
    password    = PasswordField('كلمة المرور الجديدة', validators=[Optional(), Length(min=6, max=128)])
    confirm     = PasswordField('تأكيد كلمة المرور', validators=[Optional(), EqualTo('password', message='يجب أن تتطابق كلمتا المرور')])
    # للعرض فقط
    last_login  = DateTimeField('آخر تسجيل دخول', format='%Y-%m-%d %H:%M', validators=[Optional()],
                                render_kw={'readonly': True, 'disabled': True})
    submit      = SubmitField('حفظ')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role_id.choices = [(r.id, r.name) for r in Role.query.order_by(Role.name).all()]

    def apply_to(self, user: User) -> User:
        user.username = (self.username.data or '').strip()
        user.email    = (self.email.data or '').strip().lower()
        user.role_id  = self.role_id.data
        user.is_active = bool(self.is_active.data)
        if self.password.data:
            user.set_password(self.password.data)
        return user
    
class RoleForm(FlaskForm):
    name        = StringField('اسم الدور', validators=[DataRequired(), Length(max=50)])
    description = StringField('الوصف', validators=[Optional(), Length(max=200)])
    is_default  = BooleanField('افتراضي')
    submit      = SubmitField('حفظ')


class PermissionForm(FlaskForm):
    name        = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    code        = StringField('الكود', validators=[Optional(), Length(max=100)])
    description = StringField('الوصف', validators=[Optional(), Length(max=200)])
    submit      = SubmitField('حفظ')

# --------- Customers / Suppliers / Partners ----------
class CustomerForm(FlaskForm):
    id             = HiddenField()
    name           = StringField('اسم العميل', validators=[DataRequired(message="هذا الحقل مطلوب"), Length(max=100)])
    phone          = StringField('الهاتف', validators=[
                        DataRequired(message="الهاتف مطلوب"),
                        Length(max=20, message="أقصى طول 20 رقم"),
                        Unique(Customer, "phone", message="رقم الهاتف مستخدم مسبقًا", case_insensitive=False)
                    ])
    email          = StringField('البريد الإلكتروني', validators=[
                        DataRequired(message="هذا الحقل مطلوب"),
                        Email(message="صيغة البريد غير صحيحة"),
                        Length(max=120),
                        Unique(Customer, "email", message="البريد مستخدم مسبقًا", case_insensitive=True)
                    ])
    address        = StringField('العنوان', validators=[Optional(), Length(max=200, message="أقصى طول 200 حرف")])
    whatsapp       = StringField('واتساب', validators=[DataRequired(message="رقم الواتساب مطلوب"), Length(max=20, message="أقصى طول 20 رقم")])
    category       = SelectField('تصنيف العميل', choices=[('عادي','عادي'),('فضي','فضي'),('ذهبي','ذهبي'),('مميز','مميز')], default='عادي')
    credit_limit   = DecimalField('حد الائتمان', places=2, validators=[Optional(), NumberRange(min=0, message="يجب أن يكون ≥ 0")])
    discount_rate  = DecimalField('معدل الخصم (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100, message="بين 0 و100")])
    currency       = SelectField('العملة', choices=[('ILS', 'شيكل'), ('USD', 'دولار'), ('JOD', 'دينار')], default='ILS', validators=[DataRequired(message='العملة مطلوبة')])
    is_active      = BooleanField('نشط', default=True)
    is_online      = BooleanField('عميل أونلاين', default=False)
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500, message="أقصى طول 500 حرف")])
    password       = PasswordField('كلمة المرور', validators=[Optional(), Length(min=6, message="الحد الأدنى 6 أحرف")])
    confirm        = PasswordField('تأكيد كلمة المرور', validators=[Optional(), EqualTo('password', message='يجب أن تتطابق كلمتا المرور')])
    submit         = SubmitField('حفظ العميل')

    def validate_password(self, field):
        is_create = not (self.id.data and str(self.id.data).strip().isdigit())
        if is_create and not field.data:
            raise ValidationError("كلمة المرور مطلوبة عند إنشاء عميل جديد")

    def apply_to(self, customer: Customer) -> Customer:
        customer.name          = (self.name.data or "").strip()
        customer.phone         = (self.phone.data or "").strip()
        customer.whatsapp      = (self.whatsapp.data or self.phone.data or "").strip()
        customer.email         = (self.email.data or "").strip().lower()
        customer.address       = (self.address.data or "").strip() or None
        customer.category      = self.category.data
        customer.currency      = self.currency.data
        customer.is_active     = bool(self.is_active.data)
        customer.is_online     = bool(self.is_online.data)
        customer.notes         = (self.notes.data or "").strip() or None
        customer.credit_limit  = self.credit_limit.data or 0
        customer.discount_rate = self.discount_rate.data or 0
        if self.password.data:
            customer.set_password(self.password.data)
        return customer
    
class ProductSupplierLoanForm(FlaskForm):
    product_id            = AjaxSelectField('المنتج', endpoint='api.products', get_label='name', validators=[DataRequired()])
    supplier_id           = AjaxSelectField('المورد/التاجر', endpoint='api.suppliers', get_label='name', validators=[DataRequired()])
    loan_value            = DecimalField('قيمة الدين التقديرية', places=2, validators=[Optional(), NumberRange(min=0)])
    deferred_price        = DecimalField('السعر النهائي بعد التسوية', places=2, validators=[Optional(), NumberRange(min=0)])
    is_settled            = BooleanField('تمت التسوية؟')
    partner_share_quantity= IntegerField('كمية شراكة التاجر', validators=[Optional(), NumberRange(min=0)])
    partner_share_value   = DecimalField('قيمة شراكة التاجر', places=2, validators=[Optional(), NumberRange(min=0)])
    notes                 = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit                = SubmitField('حفظ')

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
    name            = StringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    is_local        = BooleanField('محلي؟')
    identity_number = StringField('رقم الهوية/الملف الضريبي', validators=[Optional(), Length(max=100)])
    contact         = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    phone           = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    email           = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                                                                    unique_email_validator(Supplier)])
    address         = StringField('العنوان', validators=[Optional(), Length(max=200)])
    notes           = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    balance         = DecimalField('الرصيد الافتتاحي', places=2, validators=[Optional(), NumberRange(min=0)])
    payment_terms   = StringField('شروط الدفع', validators=[Optional(), Length(max=50)])  # مطابق للموديل
    currency        = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit          = SubmitField('حفظ المورد')

class PartnerForm(FlaskForm):
    name             = StringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    contact_info     = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    identity_number  = StringField('رقم الهوية', validators=[Optional(), Length(max=100)])
    phone_number     = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    email            = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120),
                                                                    unique_email_validator(Partner)])
    address          = StringField('العنوان', validators=[Optional(), Length(max=200)])
    balance          = DecimalField('الرصيد', places=2, validators=[Optional(), NumberRange(min=0)])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    currency         = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit           = SubmitField('حفظ الشريك')    

class BaseServicePartForm(FlaskForm):
    part_id      = AjaxSelectField('القطعة', endpoint='api.products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', validators=[DataRequired()])
    quantity     = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price   = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount     = DecimalField('الخصم (%)', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate     = DecimalField('ضريبة (%)', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    note         = StringField('ملاحظة', validators=[Optional(), Length(max=200)])
    submit       = SubmitField('حفظ')

def _under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))

def _normalize_to_list_items(field):
    if not _under_pytest(): return
    field.errors = [[e] if not isinstance(e, (list, tuple)) else list(e) for e in field.errors]

class PaymentAllocationForm(FlaskForm):
    payment_id = IntegerField(validators=[DataRequired()])
    invoice_ids = AjaxSelectMultipleField(endpoint='api.invoices', get_label='invoice_number', validators=[Optional()])
    service_ids = AjaxSelectMultipleField(endpoint='api.services', get_label='id', validators=[Optional()])
    allocation_amounts = FieldList(DecimalField(places=2), min_entries=1)
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('توزيع')

class RefundForm(FlaskForm):
    original_payment_id = IntegerField(validators=[DataRequired()])
    refund_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    reason = TextAreaField(validators=[Optional(), Length(max=500)])
    refund_method = SelectField(choices=[('cash','نقدي'),('bank','تحويل بنكي'),('card','بطاقة')], validators=[DataRequired()])
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('إرجاع')

class BulkPaymentForm(FlaskForm):
    payer_type = SelectField(choices=[('customer','عميل'),('partner','شريك'),('supplier','مورد')], validators=[DataRequired()])
    payer_search = StringField(validators=[Optional(), Length(max=100)])
    payer_id = HiddenField(validators=[DataRequired()])
    total_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    allocations = FieldList(FormField(PaymentAllocationForm), min_entries=1)
    method = SelectField(choices=[('cash','نقدي'),('bank','تحويل'),('card','بطاقة'),('cheque','شيك')], validators=[DataRequired()])
    currency = SelectField(choices=[('ILS','شيكل'),('USD','دولار'),('EUR','يورو')], default='ILS')
    submit = SubmitField('حفظ الدفعة')

class LoanSettlementPaymentForm(FlaskForm):
    settlement_id = AjaxSelectField(endpoint='api.loan_settlements', get_label='id', validators=[DataRequired()])
    amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField(choices=[('cash','نقدي'),('bank','تحويل'),('cheque','شيك')], validators=[DataRequired()])
    reference = StringField(validators=[Optional(), Length(max=100)])
    notes = TextAreaField(validators=[Optional(), Length(max=300)])
    submit = SubmitField('دفع')

class SplitEntryForm(FlaskForm):
    method = SelectField(validators=[DataRequired()],
                         choices=[(m.value, m.value) for m in PaymentMethod])
    amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
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
        m = (self.method.data or '').upper()

        if m == 'CHEQUE':
            if not all([self.check_number.data, self.check_bank.data, self.check_due_date.data]):
                msg = '❌ يجب إدخال بيانات الشيك كاملة'
                self.check_number.errors.append(msg); self.check_bank.errors.append(msg); self.check_due_date.errors.append(msg)
                ok = False

        elif m == 'CARD':
            num = (self.card_number.data or '').replace(' ', '').replace('-', '')
            if not num or not num.isdigit() or not luhn_check(num):
                self.card_number.errors.append("❌ رقم البطاقة غير صالح")
                ok = False
            if self.card_expiry.data and not is_valid_expiry_mm_yy(self.card_expiry.data):
                self.card_expiry.errors.append("❌ تاريخ الانتهاء يجب أن يكون بصيغة MM/YY وفي المستقبل")
                ok = False

        elif m == 'BANK':
            if not self.bank_transfer_ref.data:
                self.bank_transfer_ref.errors.append("❌ أدخل مرجع التحويل البنكي")
                ok = False

        return base_ok and ok

class PaymentForm(FlaskForm):
    payment_number = StringField(validators=[Optional(), Length(max=50)])
    payment_date   = DateTimeField(format="%Y-%m-%d %H:%M", default=datetime.utcnow, validators=[DataRequired()])

    subtotal     = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate     = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    tax_amount   = DecimalField(places=2, validators=[Optional(), NumberRange(min=0)])
    total_amount = DecimalField(places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency     = SelectField(validators=[DataRequired()],
                               choices=[("ILS","شيكل"),("USD","دولار"),("EUR","يورو"),("JOD","دينار")],
                               default="ILS")

    method    = SelectField(validators=[Optional()])
    status    = SelectField(validators=[DataRequired()])
    direction = SelectField(validators=[DataRequired()])

    entity_type = SelectField(validators=[DataRequired()])

    customer_search = StringField(validators=[Optional(), Length(max=100)])
    customer_id     = HiddenField()
    supplier_search = StringField(validators=[Optional(), Length(max=100)])
    supplier_id     = HiddenField()
    partner_search  = StringField(validators=[Optional(), Length(max=100)])
    partner_id      = HiddenField()
    shipment_search = StringField(validators=[Optional(), Length(max=100)])
    shipment_id     = HiddenField()
    expense_search  = StringField(validators=[Optional(), Length(max=100)])
    expense_id      = HiddenField()
    loan_settlement_search = StringField(validators=[Optional(), Length(max=100)])
    loan_settlement_id     = HiddenField()
    sale_search     = StringField(validators=[Optional(), Length(max=100)])
    sale_id         = HiddenField()
    invoice_search  = StringField(validators=[Optional(), Length(max=100)])
    invoice_id      = HiddenField()
    preorder_search = StringField(validators=[Optional(), Length(max=100)])
    preorder_id     = HiddenField()
    service_search  = StringField(validators=[Optional(), Length(max=100)])
    service_id      = HiddenField()

    receipt_number = StringField(validators=[Optional(), Length(max=50)])
    reference      = StringField(validators=[Optional(), Length(max=100)])

    check_number     = StringField(validators=[Optional(), Length(max=100)])
    check_bank       = StringField(validators=[Optional(), Length(max=100)])
    check_due_date   = DateField(format="%Y-%m-%d", validators=[Optional()])

    card_number      = StringField(validators=[Optional(), Length(max=100)])
    card_holder      = StringField(validators=[Optional(), Length(max=100)])
    card_expiry      = StringField(validators=[Optional(), Length(max=10)])
    card_cvv         = StringField(validators=[Optional(), Length(min=3, max=4)])

    bank_transfer_ref = StringField(validators=[Optional(), Length(max=100)])
    created_by        = HiddenField()

    splits = FieldList(FormField(SplitEntryForm), min_entries=1, max_entries=3)
    notes  = TextAreaField(validators=[Optional(), Length(max=500)])
    submit = SubmitField("💾 حفظ الدفعة")

    _entity_field_map = {
        "CUSTOMER": "customer_id",
        "SUPPLIER": "supplier_id",
        "PARTNER":  "partner_id",
        "SHIPMENT": "shipment_id",
        "EXPENSE":  "expense_id",
        "LOAN":     "loan_settlement_id",
        "SALE":     "sale_id",
        "INVOICE":  "invoice_id",
        "PREORDER": "preorder_id",
        "SERVICE":  "service_id",
    }
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

    def _get_entity_ids(self):
        return {
            "customer_id": self.customer_id.data,
            "supplier_id": self.supplier_id.data,
            "partner_id": self.partner_id.data,
            "shipment_id": self.shipment_id.data,
            "expense_id": self.expense_id.data,
            "loan_settlement_id": self.loan_settlement_id.data,
            "sale_id": self.sale_id.data,
            "invoice_id": self.invoice_id.data,
            "preorder_id": self.preorder_id.data,
            "service_id": self.service_id.data,
        }

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

        if not super().validate(extra_validators=extra_validators):
            return False

        try:
            total_splits = sum(float(s.form.amount.data or 0) for s in self.splits)
        except Exception:
            total_splits = 0.0
        if abs(total_splits - float(self.total_amount.data or 0)) > 0.01:
            self.total_amount.errors.append("❌ مجموع الدفعات الجزئية يجب أن يساوي المبلغ الكلي")
            return False

        methods = {(s.form.method.data or '').strip().upper() for s in self.splits if float(s.form.amount.data or 0) > 0}
        if len(methods) > 1:
            self.splits.errors.append("❌ يجب أن تكون جميع الدفعات الجزئية بنفس طريقة الدفع.")
            return False

        etype = (self.entity_type.data or "").upper()
        field_name = self._entity_field_map.get(etype)
        entity_ids = self._get_entity_ids()
        if not field_name:
            self.entity_type.errors.append("❌ نوع الكيان غير معروف.")
            return False

        raw_id = entity_ids.get(field_name)
        rid = "" if raw_id is None else (raw_id.strip() if isinstance(raw_id, str) else str(raw_id))
        if not rid or not rid.isdigit():
            if etype == "CUSTOMER":
                self.customer_search.errors.append("❌ يجب اختيار العميل لهذه الدفعة.")
            else:
                getattr(self, field_name).errors.append("❌ يجب اختيار المرجع المناسب للكيان المحدد.")
            return False

        def _nz(v):
            if v is None: return ""
            if isinstance(v, str): return v.strip()
            return str(v)

        filled = [k for k, v in entity_ids.items() if _nz(v)]
        if len(filled) > 1:
            for k in filled:
                if k != field_name:
                    getattr(self, k).errors.append("❌ لا يمكن تحديد أكثر من مرجع. اترك هذا الحقل فارغًا.")
            return False

        v = (self.direction.data or "").upper()
        if etype in self._incoming_entities and v not in {"IN", "INCOMING"}:
            self.direction.errors.append("❌ هذا الكيان يجب أن تكون حركته وارد (IN).")
            return False
        if etype in self._outgoing_entities and v not in {"OUT", "OUTGOING"}:
            self.direction.errors.append("❌ هذا الكيان يجب أن تكون حركته صادر (OUT).")
            return False
        self.direction.data = "IN" if v in {"IN", "INCOMING"} else "OUT"

        m = (self.method.data or "").strip().upper()

        if m in {"CHEQUE", "CHECK"}:
            if not (self.check_number.data or "").strip():
                self.check_number.errors.append("أدخل رقم الشيك."); return False
            if not (self.check_bank.data or "").strip():
                self.check_bank.errors.append("أدخل اسم البنك."); return False
            if not self.check_due_date.data:
                self.check_due_date.errors.append("أدخل تاريخ استحقاق الشيك."); return False
            if self.payment_date.data and self.check_due_date.data < self.payment_date.data.date():
                self.check_due_date.errors.append("تاريخ الاستحقاق لا يمكن أن يسبق تاريخ الدفعة."); return False

        if m == "CARD":
            num = (self.card_number.data or "").replace(" ", "").replace("-", "")
            if not num or not num.isdigit() or not luhn_check(num):
                self.card_number.errors.append("رقم البطاقة غير صالح."); return False
            if not (self.card_holder.data or "").strip():
                self.card_holder.errors.append("أدخل اسم حامل البطاقة."); return False
            exp = (self.card_expiry.data or "").strip()
            if not exp or not is_valid_expiry_mm_yy(exp):
                self.card_expiry.errors.append("تاريخ الانتهاء بصيغة MM/YY وغير منتهي."); return False
            cvv = (self.card_cvv.data or "").strip()
            if not (cvv.isdigit() and len(cvv) in (3, 4)):
                self.card_cvv.errors.append("CVV غير صالح."); return False

        if m in {"BANK", "TRANSFER", "WIRE"}:
            if not (self.bank_transfer_ref.data or "").strip():
                self.bank_transfer_ref.errors.append("أدخل مرجع التحويل البنكي."); return False

        return True

    def selected_entity(self):
        etype = (self.entity_type.data or "").upper()
        field = self._entity_field_map.get(etype)
        val = getattr(self, field).data if field else None
        return etype, (int(val) if val is not None and str(val).isdigit() else None)

    def apply_to(self, payment: Payment) -> Payment:
        payment.payment_number = (self.payment_number.data or "").strip() or payment.payment_number
        payment.payment_date   = self.payment_date.data
        payment.subtotal       = self.subtotal.data or 0
        payment.tax_rate       = self.tax_rate.data or 0
        payment.tax_amount     = self.tax_amount.data or 0
        payment.total_amount   = self.total_amount.data
        payment.currency       = (self.currency.data or "ILS").upper()
        payment.method         = (self.method.data or None)
        payment.status         = (self.status.data or None)
        payment.direction      = (self.direction.data or None)
        payment.entity_type    = (self.entity_type.data or None)
        payment.reference      = (self.reference.data or "").strip() or None
        payment.receipt_number = (self.receipt_number.data or "").strip() or None
        payment.notes          = (self.notes.data or "").strip() or None

        etype = (self.entity_type.data or "").upper()
        field_name = self._entity_field_map.get(etype)
        ids = self._get_entity_ids()
        for k, v in ids.items():
            setattr(payment, k, int(v) if v and str(v).isdigit() and k == field_name else None)

        m = (self.method.data or "").upper()
        if m in {"CHEQUE", "CHECK"}:
            payment.check_number = (self.check_number.data or "").strip() or None
            payment.check_bank   = (self.check_bank.data or "").strip() or None
            cd = self.check_due_date.data
            payment.check_due_date = datetime.combine(cd, _t.min) if cd else None
        elif m == "CARD":
            payment.card_number = (self.card_number.data or "").strip() or None
            payment.card_holder = (self.card_holder.data or "").strip() or None
            payment.card_expiry = (self.card_expiry.data or "").strip() or None
            payment.card_cvv    = (self.card_cvv.data or "").strip() or None
        elif m in {"BANK", "TRANSFER", "WIRE"}:
            payment.bank_transfer_ref = (self.bank_transfer_ref.data or "").strip() or None

        new_splits = []
        for entry in self.splits:
            fm = entry.form
            amt = fm.amount.data or 0
            if amt and amt > 0:
                sm = (fm.method.data or "").upper()
                det = {}
                if sm == "CHEQUE":
                    det = {
                        "check_number": (fm.check_number.data or "").strip() or None,
                        "check_bank":   (fm.check_bank.data or "").strip() or None,
                        "check_due_date": fm.check_due_date.data.isoformat() if fm.check_due_date.data else None,
                    }
                elif sm == "CARD":
                    num = (fm.card_number.data or "").replace(" ", "").replace("-", "")
                    det = {
                        "card_holder": (fm.card_holder.data or "").strip() or None,
                        "card_expiry": (fm.card_expiry.data or "").strip() or None,
                        "card_last4":  (num[-4:] if num else None),
                    }
                elif sm == "BANK":
                    det = {"bank_transfer_ref": (fm.bank_transfer_ref.data or "").strip() or None}
                new_splits.append(PaymentSplit(method=sm, amount=amt, details=det or None))
        payment.splits = new_splits

        return payment

class PreOrderForm(FlaskForm):
    reference      = StringField('مرجع الحجز', validators=[Optional(), Length(max=50)])
    preorder_date  = UnifiedDateTimeField('تاريخ الحجز', format='%Y-%m-%d %H:%M', validators=[Optional()])
    expected_date  = UnifiedDateTimeField('تاريخ التسليم المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()])

    status = SelectField('الحالة', choices=[
        (PreOrderStatus.PENDING.value,   'معلق'),
        (PreOrderStatus.CONFIRMED.value, 'مؤكد'),
        (PreOrderStatus.FULFILLED.value, 'منفذ'),
        (PreOrderStatus.CANCELLED.value, 'ملغي'),
    ], default=PreOrderStatus.PENDING.value, validators=[DataRequired()])

    entity_type = SelectField('نوع الجهة', choices=[
        ('CUSTOMER', 'عميل'),
        ('SUPPLIER', 'مورد'),
        ('PARTNER',  'شريك'),
    ], validators=[DataRequired()])

    customer_id  = AjaxSelectField('العميل',   endpoint='api.customers',  get_label='name', validators=[Optional()])
    supplier_id  = AjaxSelectField('المورد',   endpoint='api.suppliers',  get_label='name', validators=[Optional()])
    partner_id   = AjaxSelectField('الشريك',   endpoint='api.partners',   get_label='name', validators=[Optional()])
    product_id   = AjaxSelectField('القطعة',   endpoint='api.products',   get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن',   endpoint='api.warehouses', get_label='name', validators=[DataRequired()])

    quantity       = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    prepaid_amount = DecimalField('المدفوع مسبقاً', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tax_rate       = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit         = SubmitField('تأكيد الحجز')

    _entity_fields = ('customer_id', 'supplier_id', 'partner_id')

    def validate(self, **kw):
        if not super().validate(**kw):
            return False
        et = (self.entity_type.data or '').upper()
        if et == 'CUSTOMER' and not self.customer_id.data:
            self.customer_id.errors.append("❌ اختر العميل")
            return False
        if et == 'SUPPLIER' and not self.supplier_id.data:
            self.supplier_id.errors.append("❌ اختر المورد")
            return False
        if et == 'PARTNER' and not self.partner_id.data:
            self.partner_id.errors.append("❌ اختر الشريك")
            return False

        filled = [f for f in self._entity_fields if getattr(self, f).data]
        field_for_et = {'CUSTOMER': 'customer_id', 'SUPPLIER': 'supplier_id', 'PARTNER': 'partner_id'}.get(et)
        if any(f != field_for_et for f in filled):
            for f in filled:
                if f != field_for_et:
                    getattr(self, f).errors.append("❌ لا يمكن تحديد أكثر من جهة. اترك هذا الحقل فارغًا.")
            return False
        return True

    def apply_to(self, preorder: PreOrder) -> PreOrder:
        preorder.reference     = (self.reference.data or '').strip() or preorder.reference
        preorder.preorder_date = self.preorder_date.data or preorder.preorder_date
        preorder.expected_date = self.expected_date.data or None
        preorder.status        = self.status.data
        preorder.product_id    = int(self.product_id.data) if self.product_id.data else None
        preorder.warehouse_id  = int(self.warehouse_id.data) if self.warehouse_id.data else None
        preorder.quantity      = int(self.quantity.data or 0)
        preorder.prepaid_amount= self.prepaid_amount.data or 0
        preorder.tax_rate      = self.tax_rate.data or 0
        preorder.notes         = (self.notes.data or '').strip() or None

        et = (self.entity_type.data or '').upper()
        preorder.customer_id = int(self.customer_id.data) if et == 'CUSTOMER' and self.customer_id.data else None
        preorder.supplier_id = int(self.supplier_id.data) if et == 'SUPPLIER' and self.supplier_id.data else None
        preorder.partner_id  = int(self.partner_id.data)  if et == 'PARTNER'  and self.partner_id.data  else None
        return preorder

class ShopPreorderForm(FlaskForm):
    quantity        = IntegerField('الكمية المحجوزة', validators=[DataRequired(), NumberRange(min=1, message="❌ الكمية يجب أن تكون 1 أو أكثر")])
    prepaid_amount  = DecimalField('المبلغ المدفوع مسبقاً', places=2, validators=[DataRequired(), NumberRange(min=0, message="❌ المبلغ لا يمكن أن يكون سالباً")])
    payment_method  = SelectField('طريقة الدفع',
                        choices=[('cash','نقدي'),('card','بطاقة'),('bank','تحويل'),('cheque','شيك')],
                        validators=[Optional()])
    submit          = SubmitField('تأكيد الحجز')


class ServiceRequestForm(FlaskForm):
    service_number      = StringField('رقم الخدمة', validators=[Optional(), Length(max=50)])

    customer_id         = AjaxSelectField('العميل', endpoint='api.customers', get_label='name', validators=[DataRequired()])
    mechanic_id         = AjaxSelectField('الفني', endpoint='api.users', get_label='username', validators=[Optional()])
    vehicle_type_id     = AjaxSelectField('نوع المعدة/المركبة', endpoint='api.equipment_types', get_label='name', validators=[Optional()])

    vehicle_vrn         = StringField('لوحة المركبة', validators=[DataRequired(), Length(max=50)])
    vehicle_model       = StringField('موديل المركبة/المعدة', validators=[Optional(), Length(max=100)])
    chassis_number      = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])

    problem_description = TextAreaField('وصف المشكلة', validators=[Optional(), Length(max=2000)])
    diagnosis           = TextAreaField('التشخيص', validators=[Optional(), Length(max=4000)])
    resolution          = TextAreaField('المعالجة', validators=[Optional(), Length(max=4000)])
    notes               = TextAreaField('ملاحظات عامة', validators=[Optional(), Length(max=4000)])
    engineer_notes      = TextAreaField('ملاحظات المهندس', validators=[Optional(), Length(max=4000)])
    description         = TextAreaField('وصف عام', validators=[Optional(), Length(max=2000)])

    priority            = SelectField('الأولوية',
                          choices=[('LOW','منخفضة'),('MEDIUM','متوسطة'),('HIGH','عالية'),('URGENT','عاجلة')],
                          default='MEDIUM', validators=[DataRequired()])
    status              = SelectField('الحالة',
                          choices=[('PENDING','معلق'),('DIAGNOSIS','تشخيص'),
                                   ('IN_PROGRESS','قيد التنفيذ'),('COMPLETED','مكتمل'),
                                   ('CANCELLED','ملغي'),('ON_HOLD','مؤجل')],
                          default='PENDING', validators=[DataRequired()])

    estimated_duration  = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    actual_duration     = IntegerField('المدة الفعلية (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost      = DecimalField('التكلفة المتوقعة', places=2, validators=[Optional(), NumberRange(min=0)])
    total_cost          = DecimalField('التكلفة النهائية', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate            = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])

    start_time          = DateField('تاريخ البدء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])
    end_time            = DateField('تاريخ الانتهاء (تخطيطي)', format='%Y-%m-%d', validators=[Optional()])

    received_at         = DateTimeField('وقت الاستلام', format='%Y-%m-%d %H:%M', validators=[Optional()])
    started_at          = DateTimeField('وقت البدء الفعلي', format='%Y-%m-%d %H:%M', validators=[Optional()])
    expected_delivery   = DateTimeField('موعد التسليم المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()])
    completed_at        = DateTimeField('وقت الإكمال', format='%Y-%m-%d %H:%M', validators=[Optional()])

    currency            = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    discount_total      = DecimalField('إجمالي الخصومات', places=2, validators=[Optional(), NumberRange(min=0)])
    parts_total         = DecimalField('إجمالي قطع الغيار', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    labor_total         = DecimalField('إجمالي الأجور', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})
    total_amount        = DecimalField('الإجمالي النهائي', places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"readonly": True})

    warranty_days       = IntegerField('مدة الضمان (أيام)', validators=[Optional(), NumberRange(min=0)])

    submit              = SubmitField('حفظ طلب الصيانة')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False

        st = self.start_time.data
        et = self.end_time.data
        if st and et and et < st:
            self.end_time.errors.append('❌ وقت الانتهاء يجب أن يكون بعد وقت البدء')
            return False

        ra = self.received_at.data
        sa = self.started_at.data
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

        return True

    def apply_to(self, sr):
        sr.service_number      = (self.service_number.data or '').strip() or sr.service_number
        sr.customer_id         = int(self.customer_id.data) if self.customer_id.data else None
        sr.mechanic_id         = int(self.mechanic_id.data) if self.mechanic_id.data else None
        sr.vehicle_type_id     = int(self.vehicle_type_id.data) if self.vehicle_type_id.data else None

        sr.vehicle_vrn         = (self.vehicle_vrn.data or '').strip()
        sr.vehicle_model       = (self.vehicle_model.data or '').strip() or None
        sr.chassis_number      = (self.chassis_number.data or '').strip() or None

        sr.problem_description = (self.problem_description.data or '').strip() or None
        sr.diagnosis           = (self.diagnosis.data or '').strip() or None
        sr.resolution          = (self.resolution.data or '').strip() or None
        sr.notes               = (self.notes.data or '').strip() or None
        sr.engineer_notes      = (self.engineer_notes.data or '').strip() or None
        sr.description         = (self.description.data or '').strip() or None

        sr.priority            = (self.priority.data or None)
        sr.status              = (self.status.data or None)

        sr.estimated_duration  = self.estimated_duration.data or None
        sr.actual_duration     = self.actual_duration.data or None
        sr.estimated_cost      = self.estimated_cost.data or None
        sr.total_cost          = self.total_cost.data or None
        sr.tax_rate            = self.tax_rate.data or 0

        sr.start_time          = self.start_time.data or None
        sr.end_time            = self.end_time.data or None

        sr.received_at         = self.received_at.data or None
        sr.started_at          = self.started_at.data or None
        sr.expected_delivery   = self.expected_delivery.data or None
        sr.completed_at        = self.completed_at.data or None

        sr.currency            = (self.currency.data or 'ILS').upper()
        sr.discount_total      = self.discount_total.data or 0
        sr.warranty_days       = self.warranty_days.data or 0
        return sr
class ShipmentItemForm(FlaskForm):
    product_id     = AjaxSelectField('الصنف', endpoint='api.products', get_label='name', coerce=int, validators=[DataRequired()])
    warehouse_id   = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', coerce=int, validators=[DataRequired()])
    quantity       = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_cost      = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    declared_value = DecimalField('القيمة المعلنة', places=2, validators=[Optional(), NumberRange(min=0)])
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        q  = self.quantity.data or 0
        uc = self.unit_cost.data or 0
        dv = self.declared_value.data
        if dv is not None and dv < (q * uc):
            self.declared_value.errors.append('القيمة المعلنة يجب ألا تقل عن (الكمية × سعر الوحدة).')
            return False
        return True


class ShipmentPartnerForm(FlaskForm):
    partner_id            = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', coerce=int, validators=[DataRequired()])
    role                  = StringField('الدور', validators=[Optional(), Length(max=100)])
    notes                 = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=500)])
    identity_number       = StringField('رقم الهوية/السجل', validators=[Optional(), Length(max=100)])
    phone_number          = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    address               = StringField('العنوان', validators=[Optional(), Length(max=200)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])
    expiry_date           = DateField('تاريخ الانتهاء', format='%Y-%m-%d', validators=[Optional()])
    share_percentage      = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount          = DecimalField('مساهمة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        sp = self.share_percentage.data
        sa = self.share_amount.data
        if sp in (None, '') and sa in (None, ''):
            self.share_percentage.errors.append('حدد نسبة الشريك أو قيمة مساهمته على الأقل.')
            self.share_amount.errors.append('حدد نسبة الشريك أو قيمة مساهمته على الأقل.')
            return False
        return True


class ShipmentForm(FlaskForm):
    shipment_number  = StringField('رقم الشحنة', validators=[Optional(), Length(max=50)])
    shipment_date    = DateTimeField('تاريخ الشحن', format='%Y-%m-%d %H:%M', validators=[Optional()])
    expected_arrival = DateTimeField('الوصول المتوقع', format='%Y-%m-%d %H:%M', validators=[Optional()])
    actual_arrival   = DateTimeField('الوصول الفعلي', format='%Y-%m-%d %H:%M', validators=[Optional()])

    origin         = StringField('المنشأ', validators=[Optional(), Length(max=100)])
    destination    = StringField('الوجهة', validators=[Optional(), Length(max=100)])
    destination_id = QuerySelectField('مخزن الوجهة', query_factory=lambda: Warehouse.query, allow_blank=False, get_label='name')

    status = SelectField('الحالة', choices=[
        ('PENDING','PENDING'), ('IN_TRANSIT','IN_TRANSIT'), ('ARRIVED','ARRIVED'), ('CANCELLED','CANCELLED')
    ], validators=[DataRequired()])

    value_before  = DecimalField('قيمة البضائع قبل المصاريف', places=2,
                                 validators=[Optional(), NumberRange(min=0)],
                                 render_kw={'readonly': True})
    shipping_cost = DecimalField('تكلفة الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    customs       = DecimalField('الجمارك', places=2, validators=[Optional(), NumberRange(min=0)])
    vat           = DecimalField('ضريبة القيمة المضافة', places=2, validators=[Optional(), NumberRange(min=0)])
    insurance     = DecimalField('التأمين', places=2, validators=[Optional(), NumberRange(min=0)])

    carrier         = StringField('شركة النقل', validators=[Optional(), Length(max=100)])
    tracking_number = StringField('رقم التتبع', validators=[Optional(), Length(max=100)])
    notes           = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    currency        = SelectField('العملة', choices=CURRENCY_CHOICES, default='USD', validators=[DataRequired()])

    sale_id = QuerySelectField('البيع المرتبط', query_factory=lambda: Sale.query, allow_blank=True, get_label='sale_number')

    items    = FieldList(FormField(ShipmentItemForm), min_entries=1)
    partners = FieldList(FormField(ShipmentPartnerForm), min_entries=0)
    submit   = SubmitField('حفظ الشحنة')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        ok = False
        for entry in self.items:
            f = entry.form
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1:
                ok = True
        if not ok:
            self.items.errors.append('أدخل عنصرًا واحدًا على الأقل.')
            return False
        return True

    def apply_to(self, shipment):
        shipment.shipment_number  = (self.shipment_number.data or '').strip() or shipment.shipment_number
        shipment.shipment_date    = self.shipment_date.data or shipment.shipment_date
        shipment.expected_arrival = self.expected_arrival.data or None
        shipment.actual_arrival   = self.actual_arrival.data or None

        shipment.origin       = (self.origin.data or '').strip() or None
        shipment.destination  = (self.destination.data or '').strip() or None
        shipment.status       = (self.status.data or '').strip().upper() or 'PENDING'
        shipment.currency     = (self.currency.data or 'USD').upper()

        shipment.shipping_cost = self.shipping_cost.data or None
        shipment.customs       = self.customs.data or None
        shipment.vat           = self.vat.data or None
        shipment.insurance     = self.insurance.data or None

        shipment.carrier         = (self.carrier.data or '').strip() or None
        shipment.tracking_number = (self.tracking_number.data or '').strip() or None
        shipment.notes           = (self.notes.data or '').strip() or None

        dest_obj = self.destination_id.data
        shipment.destination_id = dest_obj.id if dest_obj else None

        sale_obj = self.sale_id.data
        shipment.sale_id = sale_obj.id if sale_obj else None

        new_items = []
        for entry in self.items:
            f = entry.form
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1:
                new_items.append(
                    ShipmentItem(
                        product_id=int(f.product_id.data),
                        warehouse_id=int(f.warehouse_id.data),
                        quantity=int(f.quantity.data),
                        unit_cost=f.unit_cost.data or 0,
                        declared_value=f.declared_value.data,
                        notes=(f.notes.data or '').strip() or None,
                    )
                )
        shipment.items = new_items

        new_partners = []
        for entry in self.partners:
            f = entry.form
            if f.partner_id.data:
                p = ShipmentPartner(partner_id=int(f.partner_id.data))
                if hasattr(p, 'role'):                  p.role = (f.role.data or '').strip() or None
                if hasattr(p, 'notes'):                 p.notes = (f.notes.data or '').strip() or None
                if hasattr(p, 'identity_number'):       p.identity_number = (f.identity_number.data or '').strip() or None
                if hasattr(p, 'phone_number'):          p.phone_number = (f.phone_number.data or '').strip() or None
                if hasattr(p, 'address'):               p.address = (f.address.data or '').strip() or None
                if hasattr(p, 'unit_price_before_tax'): p.unit_price_before_tax = f.unit_price_before_tax.data or None
                if hasattr(p, 'expiry_date'):           p.expiry_date = f.expiry_date.data or None
                if hasattr(p, 'share_percentage'):      p.share_percentage = f.share_percentage.data or None
                if hasattr(p, 'share_amount'):          p.share_amount = f.share_amount.data or None
                new_partners.append(p)
        shipment.partners = new_partners

        return shipment
    
# --------- Universal / Audit / Custom Reports ----------
class UniversalReportForm(FlaskForm):
    table           = SelectField('نوع التقرير',      choices=[],                 validators=[Optional()])
    date_field      = SelectField('حقل التاريخ',      choices=[],                 validators=[Optional()])
    start_date      = DateField('من تاريخ',           validators=[Optional()])
    end_date        = DateField('إلى تاريخ',          validators=[Optional()])
    selected_fields = SelectMultipleField('أعمدة التقرير', choices=[], coerce=str, validators=[Optional()])
    submit          = SubmitField('عرض التقرير')

class AuditLogFilterForm(FlaskForm):
    model_name = SelectField(
        'النموذج',
        choices=[
            ('', 'الكل'),
            ('Customer', 'عملاء'),
            ('Product', 'منتجات'),
            ('Sale', 'مبيعات'),
            # يمكنك إضافة مزيد من النماذج هنا
        ],
        validators=[Optional()]
    )

    action = SelectField(
        'الإجراء',
        choices=[
            ('', 'الكل'),
            ('CREATE', 'إنشاء'),
            ('UPDATE', 'تحديث'),
            ('DELETE', 'حذف')
        ],
        validators=[Optional()]
    )

    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date   = DateField('إلى تاريخ', validators=[Optional()])

    export_format = SelectField(
        'تصدير كـ',
        choices=[
            ('pdf', 'PDF'),
            ('csv', 'CSV'),
            ('excel', 'Excel')
        ],
        default='pdf'
    )

    include_details = SelectField(
        'تضمين التفاصيل',
        choices=[
            ('0', 'لا'),
            ('1', 'نعم')
        ],
        default='0'
    )

    submit = SubmitField('تصفية السجلات')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        if self.start_date.data and self.end_date.data:
            if self.start_date.data > self.end_date.data:
                self.end_date.errors.append("تاريخ النهاية يجب أن يكون بعد أو مساويًا لتاريخ البداية.")
                return False

        return True

class CustomReportForm(FlaskForm):
    report_type = SelectField('نوع التقرير', choices=[('inventory','المخزون'),('sales','المبيعات'),('customers','العملاء'),('financial','مالي')], validators=[DataRequired()])
    parameters  = TextAreaField('المعايير (JSON)', validators=[Optional()])
    submit      = SubmitField('إنشاء التقرير')
    
# --------- Employees / Expenses ----------
class EmployeeForm(FlaskForm):
    name           = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    position       = StringField('الوظيفة', validators=[Optional(), Length(max=100)])
    phone          = StringField('الجوال', validators=[Optional(), Length(max=100)])
    email          = StringField('البريد', validators=[Optional(), Email(), Length(max=120),
                                                       unique_email_validator(Employee)])
    bank_name      = StringField('البنك', validators=[Optional(), Length(max=100)])
    account_number = StringField('رقم الحساب', validators=[Optional(), Length(max=100)])
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    currency       = SelectField('العملة', choices=CURRENCY_CHOICES, default="ILS", validators=[DataRequired()])
    submit         = SubmitField('حفظ الموظف')
    
class ExpenseTypeForm(FlaskForm):
    id          = HiddenField()  # يُمرَّر في حالة التعديل
    name        = StringField('اسم نوع المصروف', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('وصف اختياري', validators=[Optional(), Length(max=500)])
    is_active   = BooleanField('مُفعّل', default=True)
    submit      = SubmitField('حفظ')

    def validate_name(self, field):
        name = (field.data or "").strip()
        if not name:
            raise ValidationError("الاسم مطلوب.")
        q = ExpenseType.query.filter_by(name=name)
        if (self.id.data or "").isdigit():
            q = q.filter(ExpenseType.id != int(self.id.data))
        if q.first():
            raise ValidationError("اسم نوع المصروف موجود مسبقًا.")

class ExpenseForm(FlaskForm):
    date            = DateTimeField('التاريخ', format='%Y-%m-%d %H:%M', default=datetime.utcnow, validators=[DataRequired()])
    amount          = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency        = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    type_id         = SelectField('نوع المصروف', coerce=int, validators=[DataRequired()])

    employee_id     = AjaxSelectField('الموظف', endpoint='api.employees', get_label='name', validators=[Optional()])
    warehouse_id    = AjaxSelectField('المستودع', endpoint='api.warehouses', get_label='name', validators=[Optional()])
    partner_id      = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    paid_to         = StringField('مدفوع إلى', validators=[Optional(), Length(max=200)])

    payment_method  = SelectField('طريقة الدفع',
                         choices=[('cash','نقدًا'),('cheque','شيك'),('bank','تحويل بنكي'),
                                  ('card','بطاقة/ائتمان'),('online','إلكتروني'),('other','أخرى')],
                         validators=[DataRequired()])

    check_number      = StringField('رقم الشيك', validators=[Optional(), Length(max=100)])
    check_bank        = StringField('البنك', validators=[Optional(), Length(max=100)])
    check_due_date    = DateField('تاريخ الاستحقاق', format='%Y-%m-%d', validators=[Optional()])

    bank_transfer_ref = StringField('مرجع التحويل', validators=[Optional(), Length(max=100)])

    card_number       = StringField('رقم البطاقة', validators=[Optional(), Length(max=19)])
    card_holder       = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_expiry       = StringField('MM/YY', validators=[Optional(), Length(max=7)])

    online_gateway    = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    online_ref        = StringField('مرجع العملية', validators=[Optional(), Length(max=100)])

    payment_details   = StringField('تفاصيل إضافية', validators=[Optional(), Length(max=255)])

    description       = StringField('وصف مختصر', validators=[Optional(), Length(max=200)])
    notes             = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    tax_invoice_number= StringField('رقم فاتورة ضريبية', validators=[Optional(), Length(max=100)])

    submit            = SubmitField('حفظ')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.type_id.choices = [(t.id, t.name) for t in ExpenseType.query.order_by(ExpenseType.name).all()]
        except Exception:
            self.type_id.choices = []

    def validate(self, **kw):
        if not super().validate(**kw):
            return False

        m = (self.payment_method.data or '').strip().lower()

        if m == 'cheque':
            if not (self.check_number.data or '').strip():
                self.check_number.errors.append('❌ أدخل رقم الشيك'); return False
            if not (self.check_bank.data or '').strip():
                self.check_bank.errors.append('❌ أدخل اسم البنك'); return False
            if not self.check_due_date.data:
                self.check_due_date.errors.append('❌ أدخل تاريخ الاستحقاق'); return False
            if self.date.data and self.check_due_date.data < self.date.data.date():
                self.check_due_date.errors.append('❌ تاريخ الاستحقاق لا يمكن أن يسبق تاريخ العملية'); return False

        elif m == 'bank':
            if not (self.bank_transfer_ref.data or '').strip():
                self.bank_transfer_ref.errors.append('❌ أدخل مرجع التحويل البنكي'); return False

        elif m == 'card':
            raw = (self.card_number.data or '').replace(' ', '').replace('-', '')
            if not (raw.isdigit() and luhn_check(raw)):
                self.card_number.errors.append('❌ رقم البطاقة غير صالح'); return False
            if not (self.card_holder.data or '').strip():
                self.card_holder.errors.append('❌ أدخل اسم حامل البطاقة'); return False
            if self.card_expiry.data and not is_valid_expiry_mm_yy(self.card_expiry.data):
                self.card_expiry.errors.append('❌ تاريخ الانتهاء يجب أن يكون بصيغة MM/YY وفي المستقبل'); return False

        elif m == 'online':
            g = (self.online_gateway.data or '').strip()
            r = (self.online_ref.data or '').strip()
            if (g and not r) or (r and not g):
                if not g: self.online_gateway.errors.append('❌ أدخل بوابة الدفع')
                if not r: self.online_ref.errors.append('❌ أدخل مرجع العملية')
                return False

        return True

    def build_payment_details(self) -> str:
        m = (self.payment_method.data or '').strip().lower()
        details = {'type': m or 'other'}

        if m == 'cheque':
            details.update({
                'number': (self.check_number.data or '').strip(),
                'bank': (self.check_bank.data or '').strip(),
                'due_date': self.check_due_date.data.isoformat() if self.check_due_date.data else None,
            })
        elif m == 'bank':
            details.update({'transfer_ref': (self.bank_transfer_ref.data or '').strip()})
        elif m == 'card':
            raw = (self.card_number.data or '').replace(' ', '').replace('-', '')
            masked = ('*' * max(len(raw) - 4, 0) + raw[-4:]) if raw else None
            details.update({
                'holder': (self.card_holder.data or '').strip(),
                'number_masked': masked,
                'expiry': (self.card_expiry.data or '').strip(),
            })
        elif m == 'online':
            details.update({
                'gateway': (self.online_gateway.data or '').strip(),
                'ref': (self.online_ref.data or '').strip(),
            })

        if (self.payment_details.data or '').strip():
            details['extra'] = self.payment_details.data.strip()

        details = {k: v for k, v in details.items() if v not in (None, '')}
        return json.dumps(details, ensure_ascii=False)

    def apply_to(self, exp: Expense) -> Expense:
        exp.date      = self.date.data
        exp.amount    = self.amount.data
        exp.currency  = (self.currency.data or 'ILS').upper()
        exp.type_id   = int(self.type_id.data) if self.type_id.data is not None else None

        # AjaxSelectField تُعيد ID عادة (coerce=int في تعريفها الافتراضي)
        exp.employee_id  = int(self.employee_id.data) if self.employee_id.data else None
        exp.warehouse_id = int(self.warehouse_id.data) if self.warehouse_id.data else None
        exp.partner_id   = int(self.partner_id.data) if self.partner_id.data else None

        exp.paid_to     = (self.paid_to.data or '').strip() or None
        exp.description = (self.description.data or '').strip() or None
        exp.notes       = (self.notes.data or '').strip() or None
        exp.tax_invoice_number = (self.tax_invoice_number.data or '').strip() or None

        m = (self.payment_method.data or '').strip().lower()
        exp.payment_method  = m
        exp.payment_details = self.build_payment_details()

        # تعبئة تفاصيل الدفع الدقيقة (سيتم تنظيف غير اللازمة بالـlistener)
        exp.check_number      = (self.check_number.data or '').strip() or None
        exp.check_bank        = (self.check_bank.data or '').strip() or None
        exp.check_due_date    = self.check_due_date.data or None

        exp.bank_transfer_ref = (self.bank_transfer_ref.data or '').strip() or None

        exp.card_holder       = (self.card_holder.data or '').strip() or None
        exp.card_expiry       = (self.card_expiry.data or '').strip() or None
        # نخزّن مؤقتًا الرقم كما أُدخل ليتولى الـlistener حفظ آخر 4 فقط:
        exp.card_number       = (self.card_number.data or '').strip() or None

        exp.online_gateway    = (self.online_gateway.data or '').strip() or None
        exp.online_ref        = (self.online_ref.data or '').strip() or None

        return exp

# --------- Online: Customer / Cart / Payment ----------
class CustomerFormOnline(FlaskForm):
    name     = StringField('الاسم الكامل', validators=[DataRequired()])
    email    = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    phone    = StringField('رقم الجوال', validators=[DataRequired()])
    whatsapp = StringField('واتساب', validators=[Optional()])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    address  = StringField('العنوان', validators=[Optional()])
    submit   = SubmitField('تسجيل')

class AddToOnlineCartForm(FlaskForm):
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1, message="❌ الحد الأدنى 1")])
    submit   = SubmitField('أضف للسلة')

class OnlinePaymentForm(FlaskForm):
    payment_ref      = StringField('مرجع الدفع', validators=[DataRequired(), Length(max=100)])
    order_id         = IntegerField('رقم الطلب', validators=[DataRequired(), NumberRange(min=1)])
    amount           = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency         = SelectField('العملة', choices=[('ILS','ILS'),('USD','USD'),('EUR','EUR'),('JOD','JOD')], default='ILS', validators=[DataRequired()])
    method           = StringField('وسيلة الدفع', validators=[Optional(), Length(max=50)])
    gateway          = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    status           = SelectField('حالة المعاملة',
                                   choices=[('PENDING','قيد المعالجة'),('SUCCESS','ناجح'),('FAILED','فشل'),('REFUNDED','مرجوع')],
                                   default='PENDING', validators=[DataRequired()])
    transaction_data = TextAreaField('بيانات المعاملة (JSON)', validators=[Optional()])
    processed_at     = DateTimeField('تاريخ المعالجة', format='%Y-%m-%d %H:%M', validators=[Optional()])

    card_last4       = StringField('آخر 4 أرقام', validators=[Optional(), Length(min=4, max=4)])
    card_encrypted   = TextAreaField('بيانات البطاقة المشفّرة', validators=[Optional(), Length(max=8000)])
    card_expiry      = StringField('انتهاء البطاقة (MM/YY)', validators=[Optional(), Length(max=7)])
    cardholder_name  = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=120)])
    card_brand       = SelectField('نوع البطاقة',
                                   choices=[('', 'غير محدد'), ('VISA','VISA'), ('MASTERCARD','MASTERCARD'),
                                            ('AMEX','AMEX'), ('DISCOVER','DISCOVER'), ('OTHER','OTHER')],
                                   validators=[Optional()])
    card_fingerprint = StringField('بصمة البطاقة', validators=[Optional(), Length(max=128)])

    submit           = SubmitField('حفظ الدفع')

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
        if st in {"SUCCESS", "REFUNDED"} and not self.processed_at.data:
            self.processed_at.errors.append("مطلوب عند نجاح/إرجاع العملية.")
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
    product_id   = AjaxSelectField('المنتج', endpoint='api.products', get_label='name', validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', validators=[DataRequired()])
    quantity     = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    direction    = SelectField('النوع', choices=[('IN','استلام'),('OUT','صرف'),('ADJUSTMENT','تعديل')], validators=[DataRequired()])

    unit_cost    = DecimalField('تكلفة الوحدة', places=2, validators=[Optional(), NumberRange(min=0)])
    is_priced    = BooleanField('مُسعّر؟', default=False)

    partner_id   = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    notes        = TextAreaField('ملاحظات', validators=[Optional()])
    submit       = SubmitField('حفظ المعاملة')

# --------- Equipment / Service ----------
class EquipmentTypeForm(FlaskForm):
    name           = StringField('اسم نوع المعدة', validators=[DataRequired(), Length(max=100)])
    model_number   = StringField('رقم النموذج', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    category       = StringField('الفئة', validators=[Optional(), Length(max=50)])
    notes          = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=200)])
    submit         = SubmitField('حفظ نوع المعدة')

class ServiceTaskForm(FlaskForm):
    service_id      = HiddenField(validators=[DataRequired()])
    partner_id      = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[Optional()])
    share_percentage= DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])

    description     = StringField('وصف المهمة', validators=[DataRequired(), Length(max=200)])
    quantity        = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price      = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount        = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate        = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note            = StringField('ملاحظات', validators=[Optional(), Length(max=200)])
    submit          = SubmitField('حفظ المهمة')


class ServiceDiagnosisForm(FlaskForm):
    problem_description = TextAreaField('المشكلة', validators=[DataRequired()])
    diagnosis           = TextAreaField('السبب', validators=[DataRequired()])
    resolution          = TextAreaField('الحل المقترح', validators=[DataRequired()])

    estimated_duration  = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost      = DecimalField('التكلفة المتوقعة', places=2, validators=[Optional(), NumberRange(min=0)])

    submit              = SubmitField('حفظ التشخيص')

class ServicePartForm(FlaskForm):
    service_id       = HiddenField(validators=[DataRequired()])

    part_id          = AjaxSelectField('القطعة/المكوّن', endpoint='api.products', get_label='name', validators=[DataRequired()])
    warehouse_id     = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', validators=[DataRequired()])
    quantity         = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price       = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount         = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate         = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note             = StringField('ملاحظات', validators=[Optional(), Length(max=200)])
    partner_id       = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', allow_blank=True, validators=[Optional()])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    submit           = SubmitField('حفظ المكوّن')


class SaleLineForm(FlaskForm):
    # ملاحظة: لا نحتاج sale_id هنا لأن الربط يتم من الأب
    product_id   = AjaxSelectField('الصنف', endpoint='api.products',  get_label='name',    coerce=int, validators=[DataRequired()])
    warehouse_id = AjaxSelectField('المخزن', endpoint='api.warehouses', get_label='name', coerce=int, validators=[DataRequired()])
    quantity     = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price   = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount_rate= DecimalField('خصم %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate     = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    note         = StringField('ملاحظات', validators=[Optional(), Length(max=200)])


class SaleForm(FlaskForm):
    sale_number      = StringField('رقم البيع', validators=[Optional(), Length(max=50)])
    sale_date        = DateTimeField('تاريخ البيع', format='%Y-%m-%d %H:%M', validators=[Optional()])
    customer_id      = AjaxSelectField('العميل', endpoint='api.customers', get_label='name',     coerce=int, validators=[DataRequired()])
    seller_id        = AjaxSelectField('البائع', endpoint='api.users',     get_label='username', coerce=int, validators=[DataRequired()])

    status           = SelectField('الحالة',
                         choices=[(SaleStatus.DRAFT.value,'مسودة'),
                                  (SaleStatus.CONFIRMED.value,'مؤكد'),
                                  (SaleStatus.CANCELLED.value,'ملغي'),
                                  (SaleStatus.REFUNDED.value,'مرتجع')],
                         default=SaleStatus.DRAFT.value, validators=[DataRequired()])

    payment_status   = SelectField('حالة السداد',
                         choices=[(PaymentProgress.PENDING.value, 'PENDING'),
                                  (PaymentProgress.PARTIAL.value, 'PARTIAL'),
                                  (PaymentProgress.PAID.value,    'PAID'),
                                  (PaymentProgress.REFUNDED.value,'REFUNDED')],
                         default=PaymentProgress.PENDING.value,
                         validators=[DataRequired()])

    currency         = SelectField('عملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    tax_rate         = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    discount_total   = DecimalField('خصم إجمالي', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=500)])
    billing_address  = TextAreaField('عنوان الفواتير', validators=[Optional(), Length(max=500)])
    shipping_cost    = DecimalField('تكلفة الشحن', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    notes            = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])

    total_amount     = DecimalField('الإجمالي النهائي', places=2,
                                    validators=[Optional(), NumberRange(min=0)],
                                    render_kw={"readonly": True})

    lines            = FieldList(FormField(SaleLineForm), min_entries=1)
    preorder_id      = IntegerField('رقم الحجز', validators=[Optional()])
    submit           = SubmitField('حفظ البيع')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False

        # تأكد من وجود سطر واحد صالح على الأقل
        ok = False
        for entry in self.lines:
            f = entry.form
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1 and (f.unit_price.data or 0) >= 0:
                ok = True
        if not ok:
            self.lines.errors.append('❌ أضف بندًا واحدًا على الأقل ببيانات صحيحة.')
            return False

        return True

    def apply_to(self, sale):
        # رؤوس البيع
        sale.sale_number     = (self.sale_number.data or '').strip() or sale.sale_number
        sale.sale_date       = self.sale_date.data or sale.sale_date
        sale.customer_id     = int(self.customer_id.data) if self.customer_id.data else None
        sale.seller_id       = int(self.seller_id.data) if self.seller_id.data else None
        sale.preorder_id     = int(self.preorder_id.data) if self.preorder_id.data else None

        sale.status          = (self.status.data or SaleStatus.DRAFT.value)
        sale.payment_status  = (self.payment_status.data or PaymentProgress.PENDING.value)
        sale.currency        = (self.currency.data or 'ILS').upper()

        sale.tax_rate        = self.tax_rate.data or 0
        sale.discount_total  = self.discount_total.data or 0
        sale.shipping_address= (self.shipping_address.data or '').strip() or None
        sale.billing_address = (self.billing_address.data or '').strip() or None
        sale.shipping_cost   = self.shipping_cost.data or 0
        sale.notes           = (self.notes.data or '').strip() or None

        # السطور
        new_lines = []
        for entry in self.lines:
            f = entry.form
            if f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) >= 1:
                new_lines.append(
                    SaleLine(
                        product_id=int(f.product_id.data),
                        warehouse_id=int(f.warehouse_id.data),
                        quantity=int(f.quantity.data),
                        unit_price=f.unit_price.data or 0,
                        discount_rate=f.discount_rate.data or 0,
                        tax_rate=f.tax_rate.data or 0,
                        note=(f.note.data or '').strip() or None
                    )
                )
        sale.lines = new_lines
        return sale

class InvoiceLineForm(FlaskForm):
    product_id  = AjaxSelectField('الصنف', endpoint='api.products', get_label='name',
                                  coerce=int, validators=[DataRequired()])

    description = StringField('الوصف', validators=[DataRequired(), Length(max=200)])
    quantity    = DecimalField('الكمية', places=2, validators=[DataRequired(), NumberRange(min=0)])
    unit_price  = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tax_rate    = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    discount    = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])

class InvoiceForm(FlaskForm):
    invoice_number = StringField('رقم الفاتورة', validators=[Optional(), Length(max=50)])
    invoice_date   = DateTimeField('تاريخ الفاتورة', format='%Y-%m-%d %H:%M', validators=[Optional()])
    due_date       = DateTimeField('تاريخ الاستحقاق', format='%Y-%m-%d %H:%M', validators=[Optional()])

    customer_id = QuerySelectField('العميل',  query_factory=lambda: Customer.query.order_by(Customer.name).all(),
                                   allow_blank=False, get_label='name')
    supplier_id = QuerySelectField('المورد',  query_factory=lambda: Supplier.query.order_by(Supplier.name).all(),
                                   allow_blank=True,  get_label='name')
    partner_id  = QuerySelectField('الشريك',  query_factory=lambda: Partner.query.order_by(Partner.name).all(),
                                   allow_blank=True,  get_label='name')
    sale_id     = QuerySelectField('البيع',   query_factory=lambda: Sale.query.order_by(Sale.sale_number).all(),
                                   allow_blank=True,  get_label='sale_number')
    service_id  = QuerySelectField('الخدمة',  query_factory=lambda: ServiceRequest.query.order_by(ServiceRequest.service_number).all(),
                                   allow_blank=True, get_label='service_number')
    preorder_id = QuerySelectField('الحجز',   query_factory=lambda: PreOrder.query.order_by(PreOrder.reference).all(),
                                   allow_blank=True, get_label='reference')

    source = SelectField('المصدر', choices=[
        (InvoiceSource.MANUAL.value,   'MANUAL'),
        (InvoiceSource.SALE.value,     'SALE'),
        (InvoiceSource.SERVICE.value,  'SERVICE'),
        (InvoiceSource.PREORDER.value, 'PREORDER'),
        (InvoiceSource.SUPPLIER.value, 'SUPPLIER'),
        (InvoiceSource.PARTNER.value,  'PARTNER'),
        (InvoiceSource.ONLINE.value,   'ONLINE'),
    ], validators=[DataRequired()])

    status = SelectField('الحالة', choices=[
        (InvoiceStatus.UNPAID.value,   'UNPAID'),
        (InvoiceStatus.PARTIAL.value,  'PARTIAL'),
        (InvoiceStatus.PAID.value,     'PAID'),
        (InvoiceStatus.CANCELLED.value,'CANCELLED'),
        (InvoiceStatus.REFUNDED.value, 'REFUNDED'),
    ], validators=[DataRequired()])

    currency        = SelectField('العملة', choices=CURRENCY_CHOICES, default='ILS', validators=[DataRequired()])
    total_amount    = DecimalField('الإجمالي', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tax_amount      = DecimalField('الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])
    discount_amount = DecimalField('الخصم',   places=2, validators=[Optional(), NumberRange(min=0)])
    notes           = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    terms           = TextAreaField('الشروط',  validators=[Optional(), Length(max=2000)])

    lines  = FieldList(FormField(InvoiceLineForm), min_entries=1)
    submit = SubmitField('حفظ الفاتورة')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False

        # ربط المصدر بالمرجع الصحيح
        src = (self.source.data or '')
        binding_ok = {
            InvoiceSource.MANUAL.value:   True,
            InvoiceSource.ONLINE.value:   True,
            InvoiceSource.SALE.value:     self.sale_id.data,
            InvoiceSource.SERVICE.value:  self.service_id.data,
            InvoiceSource.PREORDER.value: self.preorder_id.data,
            InvoiceSource.SUPPLIER.value: self.supplier_id.data,
            InvoiceSource.PARTNER.value:  self.partner_id.data,
        }.get(src, False)
        if not binding_ok:
            self.source.errors.append(f"❌ ربط غير صالح لـ {src}")
            return False

        if not self.customer_id.data:
            self.customer_id.errors.append("❌ يجب اختيار العميل.")
            return False

        # تأكد من وجود سطر واحد صالح على الأقل
        ok = False
        for lf in self.lines:
            f = lf.form
            if (f.description.data and (f.quantity.data or 0) > 0 and (f.unit_price.data or 0) >= 0):
                ok = True
        if not ok:
            self.lines.errors.append("❌ أضف بندًا واحدًا على الأقل.")
            return False

        return True

    def apply_to(self, inv):
        inv.invoice_number = (self.invoice_number.data or '').strip() or inv.invoice_number
        inv.invoice_date   = self.invoice_date.data or inv.invoice_date
        inv.due_date       = self.due_date.data or None

        # QuerySelectField → id
        inv.customer_id = self.customer_id.data.id if self.customer_id.data else None
        inv.supplier_id = self.supplier_id.data.id if self.supplier_id.data else None
        inv.partner_id  = self.partner_id.data.id  if self.partner_id.data  else None
        inv.sale_id     = self.sale_id.data.id     if self.sale_id.data     else None
        inv.service_id  = self.service_id.data.id  if self.service_id.data  else None
        inv.preorder_id = self.preorder_id.data.id if self.preorder_id.data else None

        inv.source   = (self.source.data or InvoiceSource.MANUAL.value)
        inv.status   = (self.status.data or InvoiceStatus.UNPAID.value)
        inv.currency = (self.currency.data or 'ILS').upper()

        inv.tax_amount      = self.tax_amount.data or 0
        inv.discount_amount = self.discount_amount.data or 0
        inv.notes           = (self.notes.data or '').strip() or None
        inv.terms           = (self.terms.data or '').strip() or None

        # بناء السطور
        new_lines = []
        for lf in self.lines:
            f = lf.form
            if not (f.description.data and (f.quantity.data or 0) > 0):
                continue
            line = InvoiceLine(
                description = (f.description.data or '').strip(),
                quantity    = float(f.quantity.data or 0),
                unit_price  = f.unit_price.data or 0,
                tax_rate    = f.tax_rate.data or 0,
                discount    = f.discount.data or 0,
                product_id  = int(f.product_id.data) if f.product_id.data else None,
            )
            new_lines.append(line)
        inv.lines = new_lines

        # لو في سطور، خلّي الإجمالي من السطور (أدقّ من إدخال المستخدم)
        if new_lines:
            inv.total_amount = sum(l.line_total for l in new_lines)
        else:
            inv.total_amount = self.total_amount.data or 0

        return inv

# --------- Product / Warehouse / Category ----------
class ProductPartnerShareForm(FlaskForm):
    product_id       = HiddenField(validators=[DataRequired()])
    warehouse_id     = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])

    partner_id       = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[DataRequired()])
    share_percentage = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    share_amount     = DecimalField('قيمة مساهمة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])
    notes            = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    submit           = SubmitField('حفظ')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        sp = self.share_percentage.data
        sa = self.share_amount.data
        if (sp in (None, '') or float(sp) == 0) and (sa in (None, '') or float(sa) == 0):
            self.share_percentage.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            self.share_amount.errors.append('أدخل نسبة الشريك أو قيمة مساهمته على الأقل.')
            return False
        return True

class ProductForm(FlaskForm):
    id                  = HiddenField()
    sku                 = StringField('SKU', validators=[Optional(), Length(max=50), Unique(Product, 'sku', message='SKU مستخدم بالفعل.', case_insensitive=True)])
    name                = StringField('الاسم', validators=[DataRequired(), Length(max=255)])
    description         = TextAreaField('الوصف', validators=[Optional()])
    part_number         = StringField('رقم القطعة', validators=[Optional(), Length(max=100)])
    brand               = StringField('الماركة', validators=[Optional(), Length(max=100)])
    commercial_name     = StringField('الاسم التجاري', validators=[Optional(), Length(max=100)])
    chassis_number      = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    serial_no           = StringField('الرقم التسلسلي', validators=[Optional(), Length(max=100), Unique(Product, 'serial_no', message='الرقم التسلسلي مستخدم بالفعل.', case_insensitive=True)])
    barcode             = StringField('الباركود', validators=[Optional(), Length(max=100), Unique(Product, 'barcode', message='الباركود مستخدم بالفعل.', case_insensitive=True)])

    cost_before_shipping  = DecimalField('التكلفة قبل الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    cost_after_shipping   = DecimalField('التكلفة بعد الشحن', places=2, validators=[Optional(), NumberRange(min=0)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', places=2, validators=[Optional(), NumberRange(min=0)])

    price               = DecimalField('السعر الأساسي', places=2, validators=[DataRequired(), NumberRange(min=0)])
    purchase_price      = DecimalField('سعر الشراء', places=2, validators=[Optional(), NumberRange(min=0)])
    selling_price       = DecimalField('سعر البيع', places=2, validators=[Optional(), NumberRange(min=0)])
    min_price           = DecimalField('السعر الأدنى', places=2, validators=[Optional(), NumberRange(min=0)])
    max_price           = DecimalField('السعر الأعلى', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate            = DecimalField('نسبة الضريبة', places=2, validators=[Optional(), NumberRange(min=0, max=100)])

    unit                = StringField('الوحدة', validators=[Optional(), Length(max=50)])
    min_qty             = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    reorder_point       = IntegerField('نقطة إعادة الطلب', validators=[Optional(), NumberRange(min=0)])

    condition           = SelectField('الحالة', choices=[
        (ProductCondition.NEW.value, 'جديد'),
        (ProductCondition.USED.value, 'مستعمل'),
        (ProductCondition.REFURBISHED.value, 'مجدّد')
    ], validators=[DataRequired()])

    origin_country      = StringField('بلد المنشأ', validators=[Optional(), Length(max=50)])
    warranty_period     = IntegerField('مدة الضمان', validators=[Optional(), NumberRange(min=0)])
    weight              = DecimalField('الوزن', places=2, validators=[Optional(), NumberRange(min=0)])
    dimensions          = StringField('الأبعاد', validators=[Optional(), Length(max=50)])
    image               = StringField('صورة', validators=[Optional(), Length(max=255)])

    is_active           = BooleanField('نشط', default=True)
    is_digital          = BooleanField('منتج رقمي', default=False)
    is_exchange         = BooleanField('قابل للتبادل', default=False)

    vehicle_type_id     = AjaxSelectField('نوع المركبة', endpoint='api.search_equipment_types', get_label='name', validators=[Optional()])
    category_id         = AjaxSelectField('الفئة', endpoint='api.search_categories', get_label='name', validators=[Optional()])
    category_name       = StringField('اسم الفئة (نصي)', validators=[Optional(), Length(max=100)])

    supplier_id               = AjaxSelectField('المورد الرئيسي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])
    supplier_international_id = AjaxSelectField('المورد الدولي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])
    supplier_local_id         = AjaxSelectField('المورد المحلي', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])

    notes               = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])

    submit              = SubmitField('حفظ')

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
        p.sku             = (self.sku.data or '').strip() or None
        p.name            = (self.name.data or '').strip()
        p.description     = (self.description.data or '').strip() or None
        p.part_number     = (self.part_number.data or '').strip() or None
        p.brand           = (self.brand.data or '').strip() or None
        p.commercial_name = (self.commercial_name.data or '').strip() or None
        p.chassis_number  = (self.chassis_number.data or '').strip() or None
        p.serial_no       = (self.serial_no.data or '').strip() or None
        p.barcode         = (self.barcode.data or '').strip() or None
        p.cost_before_shipping   = self.cost_before_shipping.data or 0
        p.cost_after_shipping    = self.cost_after_shipping.data or 0
        p.unit_price_before_tax  = self.unit_price_before_tax.data or 0
        base_price = self.price.data
        sell_price = self.selling_price.data or base_price
        if base_price is None and sell_price is not None:
            base_price = sell_price
        p.price          = base_price or 0
        p.selling_price  = sell_price or 0
        p.purchase_price = self.purchase_price.data or 0
        p.min_price      = self.min_price.data or None
        p.max_price      = self.max_price.data or None
        p.tax_rate       = self.tax_rate.data or 0
        p.unit           = (self.unit.data or '').strip() or None
        p.min_qty        = int(self.min_qty.data) if self.min_qty.data is not None else 0
        p.reorder_point  = int(self.reorder_point.data) if self.reorder_point.data is not None else None
        p.condition      = self.condition.data or ProductCondition.NEW.value
        p.origin_country = (self.origin_country.data or '').strip() or None
        p.warranty_period= int(self.warranty_period.data) if self.warranty_period.data is not None else None
        p.weight         = self.weight.data or None
        p.dimensions     = (self.dimensions.data or '').strip() or None
        p.image          = (self.image.data or '').strip() or None
        p.is_active      = bool(self.is_active.data)
        p.is_digital     = bool(self.is_digital.data)
        p.is_exchange    = bool(self.is_exchange.data)
        p.vehicle_type_id            = int(self.vehicle_type_id.data) if self.vehicle_type_id.data else None
        p.category_id                = int(self.category_id.data) if self.category_id.data else None
        p.category_name              = (self.category_name.data or '').strip() or None
        p.supplier_id                = int(self.supplier_id.data) if self.supplier_id.data else None
        p.supplier_international_id  = int(self.supplier_international_id.data) if self.supplier_international_id.data else None
        p.supplier_local_id          = int(self.supplier_local_id.data) if self.supplier_local_id.data else None
        p.notes         = (self.notes.data or '').strip() or None
        return p

class WarehouseForm(FlaskForm):
    name              = StringField('اسم المستودع', validators=[DataRequired(), Length(max=100)])
    warehouse_type    = SelectField('نوع المستودع',
                           choices=[('MAIN','رئيسي'),('INVENTORY','مخزون'),('PARTNER','مخزن شركاء'),('EXCHANGE','مخزن تبادل')],
                           validators=[DataRequired()])
    location          = StringField('الموقع', validators=[Optional(), Length(max=200)])
    parent_id         = AjaxSelectField('المستودع الأب', endpoint='api.search_warehouses', get_label='name', validators=[Optional()])
    partner_id        = AjaxSelectField('الشريك', endpoint='api.search_partners', get_label='name', validators=[Optional()])
    supplier_id       = AjaxSelectField('المورد', endpoint='api.search_suppliers', get_label='name', validators=[Optional()])
    share_percent     = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    capacity          = IntegerField('السعة القصوى', validators=[Optional(), NumberRange(min=0)])
    current_occupancy = IntegerField('المشغول حاليًا', validators=[Optional(), NumberRange(min=0)])
    notes             = TextAreaField('ملاحظات', validators=[Optional(), Length(max=1000)])
    is_active         = BooleanField('نشط', default=True)
    submit            = SubmitField('حفظ المستودع')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        cap = self.capacity.data
        occ = self.current_occupancy.data
        if cap is not None and occ is not None and occ > cap:
            self.current_occupancy.errors.append('المشغول حاليًا لا يمكن أن يتجاوز السعة القصوى.')
            return False
        if (self.share_percent.data not in (None, '')) and not self.partner_id.data:
            self.partner_id.errors.append('حدد الشريك عند إدخال نسبة شراكة.')
            return False
        if (self.warehouse_type.data or '').upper() == 'PARTNER' and not self.partner_id.data:
            self.partner_id.errors.append('المستودع من نوع شركاء يتطلب اختيار شريك.')
            return False
        return True

class PartnerShareForm(FlaskForm):
    partner_id       = AjaxSelectField('الشريك', endpoint='api.partners', get_label='name', validators=[DataRequired()])
    share_percentage = DecimalField('نسبة المشاركة (%)', places=2, validators=[DataRequired(), NumberRange(min=0, max=100)])
    partner_phone    = StringField('هاتف الشريك', validators=[Optional(), Length(max=20)])
    partner_identity = StringField('هوية الشريك', validators=[Optional(), Length(max=100)])
    notes            = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit           = SubmitField('حفظ')

class ExchangeVendorForm(FlaskForm):
    vendor_name  = StringField('اسم المورد', validators=[DataRequired()])
    vendor_phone = StringField('هاتف المورد', validators=[Optional()])
    vendor_paid  = DecimalField('المبلغ المدفوع', validators=[Optional(), NumberRange(min=0)])
    vendor_price = DecimalField('سعر المورد', validators=[Optional(), NumberRange(min=0)])
    submit       = SubmitField('حفظ')

class ProductCategoryForm(FlaskForm):
    name        = StringField('اسم الفئة', validators=[DataRequired(), Length(max=100)])
    parent_id   = AjaxSelectField('الفئة الأب', endpoint='api.search_categories', get_label='name', validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    image_url   = StringField('رابط الصورة', validators=[Optional()])
    submit      = SubmitField('حفظ الفئة')

class ImportForm(FlaskForm):
    warehouse_id = AjaxSelectField('المستودع', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    file         = FileField('ملف CSV', validators=[DataRequired(), FileAllowed(['csv'])])
    submit       = SubmitField('استيراد')

class NoteForm(FlaskForm):
    author_id  = HiddenField(validators=[Optional()])
    content    = TextAreaField('المحتوى', validators=[DataRequired(), Length(max=1000)])
    entity_type= SelectField('نوع الكيان', choices=[], validators=[Optional()])
    entity_id  = StringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    is_pinned  = BooleanField('مثبّتة')
    priority   = SelectField('الأولوية',
                             choices=[('LOW','منخفضة'), ('MEDIUM','متوسطة'), ('HIGH','عالية')],
                             default='MEDIUM', validators=[Optional()])
    submit     = SubmitField('💾 حفظ الملاحظة')

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


class StockLevelForm(FlaskForm):
    id                = HiddenField()
    product_id        = AjaxSelectField('المنتج', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id      = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])
    quantity          = IntegerField('الكمية الإجمالية', validators=[DataRequired(), NumberRange(min=0)])
    reserved_quantity = IntegerField('الكمية المحجوزة', validators=[Optional(), NumberRange(min=0)])
    min_stock         = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    max_stock         = IntegerField('الحد الأقصى', validators=[Optional(), NumberRange(min=0)])
    submit            = SubmitField('حفظ مستوى المخزون')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        mn = self.min_stock.data
        mx = self.max_stock.data
        if mn is not None and mx is not None and mx < mn:
            self.max_stock.errors.append('❌ الحد الأقصى يجب أن يكون ≥ الحد الأدنى')
            return False
        q  = self.quantity.data or 0
        rq = self.reserved_quantity.data or 0
        if rq > q:
            self.reserved_quantity.errors.append('❌ الكمية المحجوزة لا يمكن أن تتجاوز الكمية الإجمالية')
            return False
        pid = getattr(self.product_id.data, 'id', self.product_id.data)
        wid = getattr(self.warehouse_id.data, 'id', self.warehouse_id.data)
        if pid and wid:
            qs = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid)
            if (self.id.data or '').isdigit():
                qs = qs.filter(StockLevel.id != int(self.id.data))
            if qs.first():
                self.warehouse_id.errors.append('❌ يوجد سجل مخزون لهذا المنتج في هذا المخزن بالفعل')
                return False
        return True

class InventoryAdjustmentForm(FlaskForm):
    product_id      = AjaxSelectField('المنتج', endpoint='api.search_products', get_label='name', validators=[DataRequired()])
    warehouse_id    = AjaxSelectField('المخزن', endpoint='api.search_warehouses', get_label='name', validators=[DataRequired()])

    # ✅ موحّد مع الموديل: IN / OUT / ADJUSTMENT
    adjustment_type = SelectField(
        'نوع التعديل',
        choices=[('IN','إضافة'),('OUT','إزالة'),('ADJUSTMENT','تصحيح')],
        default='ADJUSTMENT',
        validators=[DataRequired()]
    )

    quantity        = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    reason          = TextAreaField('السبب', validators=[DataRequired()])
    submit          = SubmitField('تطبيق التعديل')

# --------- Exporters ----------
class ExportContactsForm(FlaskForm):
    customer_ids = AjaxSelectMultipleField('اختر العملاء', endpoint='api.search_customers', get_label='name', validators=[DataRequired(message='❌ اختر عميلًا واحدًا على الأقل')])
    fields       = SelectMultipleField('الحقول', choices=[('name','الاسم'),('phone','الجوال'),('whatsapp','واتساب'),('email','البريد الإلكتروني'),('address','العنوان'),('notes','ملاحظات')], default=['name','phone','email'])
    format       = SelectField('صيغة التصدير', choices=[('vcf','vCard'),('csv','CSV'),('excel','Excel')], default='vcf')
    submit       = SubmitField('تصدير')

class OnlineCartPaymentForm(FlaskForm):
    payment_method = SelectField('طريقة الدفع', choices=[('online','إلكتروني'),('card','بطاقة'),('bank','تحويل بنكي'),('cash','نقدي')], validators=[DataRequired()])
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=100)])
    card_number = StringField('رقم البطاقة', validators=[Optional(), Length(min=12, max=19)])
    expiry = StringField('تاريخ الانتهاء (MM/YY)', validators=[Optional(), Length(min=5, max=5)])
    cvv = StringField('CVV', validators=[Optional(), Length(min=3, max=4)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=300)])
    billing_address = TextAreaField('عنوان الفاتورة', validators=[Optional(), Length(max=300)])
    transaction_data = TextAreaField('بيانات إضافية للبوابة (JSON)', validators=[Optional()])
    save_card = BooleanField('حفظ البطاقة')
    submit = SubmitField('تأكيد الدفع')

    def validate_card_number(self, field):
        if self.payment_method.data == 'card' and (not field.data or not luhn_check(field.data)):
            raise ValidationError("❌ رقم البطاقة غير صالح")

    def validate_expiry(self, field):
        if self.payment_method.data == 'card' and not is_valid_expiry_mm_yy(field.data or ""):
            raise ValidationError("❌ تاريخ الانتهاء يجب أن يكون بصيغة MM/YY وفي المستقبل")

class ExportPaymentsForm(FlaskForm):
    payment_ids = AjaxSelectMultipleField('اختر الدفعات', endpoint='api.search_payments', get_label='id', validators=[DataRequired(message='❌ اختر دفعة واحدة على الأقل')])
    format      = SelectField('صيغة التصدير', choices=[('csv','CSV'),('excel','Excel')], default='csv')
    submit      = SubmitField('تصدير')
