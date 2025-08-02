# forms.py

import json, re
from datetime import datetime

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField

from wtforms import (
    BooleanField, DateField, DecimalField, FieldList,
    FormField, HiddenField, IntegerField, PasswordField,
    SelectField, SelectMultipleField, StringField,
    SubmitField, TextAreaField, ValidationError
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField

from models import (
    Customer, EquipmentType, Expense, OnlineCart, Partner,
    Permission, PaymentDirection, PaymentEntityType,
    PaymentMethod, PaymentStatus, Product, ProductCategory,
    Role, Shipment, StockLevel, Supplier,
    SupplierLoanSettlement, User, Warehouse, TransferDirection
)

# --- CSRF protection for list views ---
class CSRFProtectForm(FlaskForm):
    """نموذج فارغ لإمداد كل قوالب القوائم برمز CSRF"""
    pass

# --- Data Import & Restore ---
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
    db_file = FileField('نسخة .db', validators=[
        DataRequired(message='اختر ملف .db'),
        FileAllowed(['db'], 'ملف db فقط')
    ])
    submit = SubmitField('استعادة النسخة')

# --- Transfer ---
class TransferForm(FlaskForm):
    date           = DateField('التاريخ', format='%Y-%m-%d', default=datetime.utcnow, validators=[Optional()])
    product_id     = SelectField('الصنف', coerce=int, validators=[DataRequired()])
    source_id      = SelectField('مخزن المصدر', coerce=int, validators=[DataRequired()])
    destination_id = SelectField('مخزن الوجهة', coerce=int, validators=[DataRequired()])
    quantity       = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    direction      = SelectField('الاتجاه', choices=[(d.value, d.name) for d in TransferDirection], validators=[DataRequired()])
    notes          = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit         = SubmitField('حفظ التحويل')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [(p.id, p.name) for p in Product.query.order_by(Product.name).all()]
        wh_choices = [(w.id, w.name) for w in Warehouse.query.order_by(Warehouse.name).all()]
        self.source_id.choices      = wh_choices
        self.destination_id.choices = wh_choices

# --- Auth ---
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3,50)])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')
    submit = SubmitField('تسجيل الدخول')

class RegistrationForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3,50)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('الدور', coerce=int, validators=[DataRequired()])
    submit = SubmitField('تسجيل')

class PasswordResetForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('تحديث')

class PasswordResetRequestForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    submit = SubmitField('إرسال رابط إعادة')

# --- Users & Roles ---
class UserForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(3,50)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    role = QuerySelectField('الدور', query_factory=lambda: Role.query.order_by(Role.name).all(),
                            get_label='name', allow_blank=False)
    extra_permissions = QuerySelectMultipleField('صلاحيات إضافية',
                            query_factory=lambda: Permission.query.order_by(Permission.name).all(),
                            get_label='name', validators=[Optional()])
    password = PasswordField('كلمة المرور (جديدة)', validators=[Optional(), Length(min=6)])
    submit = SubmitField('حفظ')

class RoleForm(FlaskForm):
    name = StringField('اسم الدور', validators=[DataRequired(), Length(max=50)])
    description = StringField('الوصف', validators=[Optional(), Length(max=200)])
    permissions = QuerySelectMultipleField('الأذونات',
                  query_factory=lambda: Permission.query.order_by(Permission.name).all(),
                  get_label='name', validators=[Optional()])
    submit = SubmitField('حفظ')

class PermissionForm(FlaskForm):
    name = StringField('اسم الإذن', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('حفظ')
# --- Customers, Suppliers, Partners ---
class CustomerForm(FlaskForm):
    name = StringField('اسم العميل', validators=[DataRequired()])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email()])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    whatsapp = StringField('واتساب', validators=[Optional(), Length(max=20)])
    category = SelectField('تصنيف العميل',
        choices=[('عادي','عادي'),('فضي','فضي'),('ذهبي','ذهبي'),('مميز','مميز')], default='عادي')
    credit_limit = DecimalField('حد الائتمان', places=2, validators=[Optional(), NumberRange(min=0)])
    discount_rate = DecimalField('معدل الخصم (%)', places=2, validators=[Optional(), NumberRange(0,100)])
    is_active = BooleanField('نشط', default=True)
    is_online = BooleanField('عميل أونلاين', default=False)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    password = PasswordField('كلمة المرور', validators=[Optional(), Length(min=6)])
    confirm = PasswordField('تأكيد كلمة المرور',
        validators=[Optional(), EqualTo('password', message='يجب أن تتطابق كلمتا المرور')])
    submit = SubmitField('حفظ العميل')

class ProductSupplierLoanForm(FlaskForm):
    supplier_id = QuerySelectField('المورد/التاجر',
                                   query_factory=lambda: Supplier.query.order_by(Supplier.name).all(),
                                   get_label='name', allow_blank=False)
    loan_value = DecimalField('قيمة الدين التقديرية', places=2, validators=[Optional(), NumberRange(min=0)])
    deferred_price = DecimalField('السعر النهائي بعد التسوية', places=2, validators=[Optional(), NumberRange(min=0)])
    is_settled = BooleanField('تمت التسوية؟')
    partner_share_quantity = IntegerField('كمية شراكة التاجر', validators=[Optional(), NumberRange(min=0)])  # ✅ مضاف
    partner_share_value = DecimalField('قيمة شراكة التاجر', places=2, validators=[Optional(), NumberRange(min=0)])  # ✅ مضاف
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

class SupplierForm(FlaskForm):
    name = StringField('اسم المورد', validators=[DataRequired(), Length(max=100)])
    is_local = BooleanField('محلي', default=True)
    identity_number = StringField('رقم الهوية/السجل', validators=[Optional(), Length(max=100)])
    contact = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    balance = DecimalField('الرصيد', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    payment_terms = StringField('شروط الدفع', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ المورد')

class PartnerForm(FlaskForm):
    name = StringField('اسم الشريك', validators=[DataRequired(), Length(max=100)])
    contact_info = StringField('معلومات التواصل', validators=[Optional(), Length(max=200)])
    identity_number = StringField('رقم الهوية', validators=[Optional(), Length(max=100)])
    phone_number = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    balance = DecimalField('الرصيد', places=2, validators=[Optional(), NumberRange(min=0)])
    share_percentage = DecimalField('نسبة الشريك (%)', places=2,
                                    validators=[Optional(), NumberRange(min=0, max=100)])
    submit = SubmitField('حفظ الشريك')

class BaseServicePartForm(FlaskForm):
    part_id      = SelectField('القطعة',    coerce=int, validators=[DataRequired()])
    warehouse_id = SelectField('المخزن',    coerce=int, validators=[DataRequired()])
    quantity     = IntegerField('الكمية',    validators=[DataRequired(), NumberRange(min=1)])
    unit_price   = DecimalField('سعر الوحدة',places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount     = DecimalField('الخصم (%)', places=2, default=0, validators=[Optional(), NumberRange(0,100)])
    tax_rate     = DecimalField('ضريبة (%)', places=2, default=0, validators=[Optional(), NumberRange(0,100)])
    note         = StringField('ملاحظة',     validators=[Optional(), Length(max=200)])

# --- Split Entry ---
class splitEntryForm(FlaskForm):
    method = SelectField('طريقة الدفع',
             choices=[('cash','نقداً'),('cheque','شيك'),('bank','تحويل بنكي'),
                      ('card','بطاقة ائتمان'),('online','دفع إلكتروني')],
             validators=[DataRequired()])
    amount = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    check_number = StringField('رقم الشيك', validators=[Optional()])
    check_bank = StringField('البنك', validators=[Optional()])
    check_due_date = DateField('تاريخ استحقاق الشيك', validators=[Optional()])
    card_number = StringField('رقم البطاقة', validators=[Optional()])
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional()])
    card_expiry = StringField('تاريخ انتهاء البطاقة', validators=[Optional(), Length(max=10)])
    bank_transfer_ref = StringField('مرجع التحويل', validators=[Optional()])
    def validate(self, **kwargs):
        if not super().validate(**kwargs): return False
        if self.method.data == 'cheque' and (not self.check_number.data or
           not self.check_bank.data or not self.check_due_date.data):
            for f in [self.check_number, self.check_bank, self.check_due_date]:
                f.errors.append('❌ يجب إدخال بيانات الشيك كاملة')
            return False
        return True

# --- Payments ---
class PaymentAllocationForm(FlaskForm):
    payment_id = IntegerField('معرّف الدفعة', validators=[DataRequired()])
    invoice_ids = SelectMultipleField('الفواتير', coerce=int, validators=[Optional()])
    service_ids = SelectMultipleField('طلبات الصيانة', coerce=int, validators=[Optional()])
    allocation_amounts = FieldList(DecimalField('مبلغ التوزيع', places=2), min_entries=1)
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=300)])
    submit = SubmitField('توزيع')

class RefundForm(FlaskForm):
    original_payment_id = IntegerField('رقم الدفعة الأصلية', validators=[DataRequired()])
    refund_amount = DecimalField('المبلغ المرجع', places=2,
                                 validators=[DataRequired(), NumberRange(min=0.01)])
    reason = TextAreaField('سبب الإرجاع', validators=[Optional(), Length(max=500)])
    refund_method = SelectField('طريقة الإرجاع',
                     choices=[('cash','نقدي'),('bank','تحويل بنكي'),('card','بطاقة')],
                     validators=[DataRequired()])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=300)])
    submit = SubmitField('إرجاع')

class BulkPaymentForm(FlaskForm):
    payer_type = SelectField('نوع الدافع',
                 choices=[('customer','عميل'),('partner','شريك'),('supplier','مورد')],
                 validators=[DataRequired()])
    payer_id = IntegerField('معرّف الدافع', validators=[DataRequired()])
    total_amount = DecimalField('إجمالي المبلغ', places=2,
                                validators=[DataRequired(), NumberRange(min=0.01)])
    allocations = FieldList(FormField(PaymentAllocationForm), min_entries=1)
    method = SelectField('طريقة الدفع',
             choices=[('cash','نقدي'),('bank','تحويل'),('card','بطاقة'),('cheque','شيك')],
             validators=[DataRequired()])
    currency = SelectField('العملة', choices=[('ILS','شيكل'),('USD','دولار'),('EUR','يورو')],
                           default='ILS')
    submit = SubmitField('حفظ الدفعة')

class LoanSettlementPaymentForm(FlaskForm):
    settlement_id = QuerySelectField('تسوية المورد',
                     query_factory=lambda: SupplierLoanSettlement.query.all(),
                     get_label='id', allow_blank=False)
    amount = DecimalField('قيمة الدفع', places=2,
                          validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField('طريقة الدفع',
             choices=[('cash','نقدي'),('bank','تحويل'),('cheque','شيك')],
             validators=[DataRequired()])
    reference = StringField('مرجع الدفع', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=300)])
    submit = SubmitField('دفع')

class PaymentSplitForm(FlaskForm):
    method = SelectField('طريقة الدفع',
             choices=[('CASH','نقدي'),('CHECK','شيك'),('BANK_TRANSFER','تحويل بنكي'),
                      ('CREDIT_CARD','بطاقة ائتمان')], validators=[DataRequired()])
    amount = DecimalField('المبلغ', places=2,
                          validators=[DataRequired(), NumberRange(min=0.01)])
    check_number = StringField('رقم الشيك', validators=[Optional()])
    check_bank = StringField('البنك', validators=[Optional()])
    check_due_date = DateField('تاريخ الاستحقاق', validators=[Optional()])
    card_number = StringField('رقم البطاقة', validators=[Optional()])
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional()])
    card_expiry = StringField('تاريخ انتهاء البطاقة', validators=[Optional(), Length(max=10)])
    card_cvv = StringField('CVV', validators=[Optional(), Length(max=4)])
    bank_transfer_ref = StringField('مرجع التحويل', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=300)])

class PaymentForm(FlaskForm):
    payment_number = StringField('رقم الدفع', validators=[Optional(), Length(max=50)])
    payment_date = DateField('تاريخ الدفع', format='%Y-%m-%d', default=datetime.utcnow, validators=[DataRequired()])
    subtotal = DecimalField('المجموع قبل الضريبة', places=2)
    tax_rate = DecimalField('نسبة الضريبة (%)', places=2)
    tax_amount = DecimalField('قيمة الضريبة', places=2)
    total_amount = DecimalField('المجموع النهائي', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=[('ILS','شيكل'),('USD','دولار'),('EUR','يورو')], default='ILS')

    # ✅ ربط بالـEnums
    method = SelectField(
        'طريقة الدفع',
        choices=[(m.value, m.name) for m in PaymentMethod],
        validators=[DataRequired()]
    )
    status = SelectField(
        'الحالة',
        choices=[(s.value, s.name) for s in PaymentStatus],
        default=PaymentStatus.PENDING.value,
        validators=[DataRequired()]
    )
    direction = SelectField(
        'نوع العملية',
        choices=[(d.value, d.name) for d in PaymentDirection],
        default=PaymentDirection.OUTGOING.value,
        validators=[DataRequired()]
    )

    # فصل حقلي entity_type و entity_id
    entity_type = SelectField(
        'نوع الكيان',
        choices=[(e.value, e.name) for e in PaymentEntityType],
        default=PaymentEntityType.CUSTOMER.value,
        validators=[DataRequired()]
    )
    entity_id = HiddenField(validators=[DataRequired()])

    # ✅ العلاقات
    customer_id = QuerySelectField('العميل', query_factory=lambda: Customer.query.order_by(Customer.name).all(), get_label='name', allow_blank=True)
    supplier_id = QuerySelectField('المورد', query_factory=lambda: Supplier.query.order_by(Supplier.name).all(), get_label='name', allow_blank=True)
    partner_id  = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(), get_label='name', allow_blank=True)
    shipment_id = QuerySelectField('الشحنة', query_factory=lambda: Shipment.query.order_by(Shipment.shipment_number).all(), get_label='shipment_number', allow_blank=True)
    expense_id  = QuerySelectField('المصروف', query_factory=lambda: Expense.query.order_by(Expense.description).all(), get_label='description', allow_blank=True)
    loan_settlement_id = QuerySelectField('تسوية دين', query_factory=lambda: SupplierLoanSettlement.query.all(), get_label='id', allow_blank=True)

    # ✅ الحقول الإضافية
    receipt_number = StringField('رقم الإيصال', validators=[Optional(), Length(max=50)])
    reference = StringField('مرجع', validators=[Optional(), Length(max=100)])
    check_number = StringField('رقم الشيك')
    check_bank = StringField('البنك')
    check_due_date = DateField('تاريخ استحقاق الشيك')
    card_number = StringField('رقم البطاقة')
    card_holder = StringField('اسم حامل البطاقة')
    card_expiry = StringField('تاريخ انتهاء البطاقة', validators=[Length(max=10)])
    card_cvv = StringField('CVV', validators=[Length(max=4)])
    bank_transfer_ref = StringField('مرجع التحويل البنكي', validators=[Length(max=100)])

    splits = FieldList(FormField(splitEntryForm), min_entries=1, max_entries=5)
    additional_splits = FieldList(FormField(PaymentSplitForm), min_entries=0)
    notes = TextAreaField('ملاحظات', validators=[Length(max=500)])
    submit = SubmitField('💾 حفظ الدفعة')

    # ✅ التحقق من تساوي المجاميع
    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        total_splits = sum(float(s['amount']) for s in self.splits.data if s.get('amount'))
        if abs(total_splits - float(self.total_amount.data or 0)) > 0.01:
            self.total_amount.errors.append("❌ مجموع الدفعات الجزئية يجب أن يساوي المبلغ الكلي")
            return False
        return True

# --- PreOrder Forms ---
class PreOrderForm(FlaskForm):
    reference = StringField('مرجع الحجز', validators=[Optional(), Length(max=50)])
    preorder_date = DateField('تاريخ الحجز', format='%Y-%m-%d', validators=[Optional()])
    expected_date = DateField('تاريخ التسليم المتوقع', format='%Y-%m-%d', validators=[Optional()])
    status = SelectField('الحالة',
             choices=[('PENDING','معلق'),('CONFIRMED','مؤكد'),
                      ('FULFILLED','منفذ'),('CANCELLED','ملغي')],
             default='PENDING', validators=[DataRequired()])
    entity_type = SelectField('نوع الجهة',
                  choices=[('customer','عميل'),('supplier','مورد'),('partner','شريك')],
                  validators=[DataRequired()])
    customer_id = QuerySelectField('العميل', query_factory=lambda: Customer.query.order_by(Customer.name).all(),
                                   get_label='name', allow_blank=True, blank_text='-- اختر عميل --')
    supplier_id = QuerySelectField('المورد', query_factory=lambda: Supplier.query.order_by(Supplier.name).all(),
                                   get_label='name', allow_blank=True, blank_text='-- اختر مورد --')
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(),
                                  get_label='name', allow_blank=True, blank_text='-- اختر شريك --')
    product_id = QuerySelectField('القطعة', query_factory=lambda: Product.query.order_by(Product.name).all(),
                                  get_label='name', allow_blank=False)
    warehouse_id = QuerySelectField('المخزن', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
                                    get_label='name', allow_blank=False)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    prepaid_amount = DecimalField('المدفوع مسبقاً', places=2,
                                  validators=[DataRequired(), NumberRange(min=0)])
    payment_method = SelectField('طريقة الدفع',
                     choices=[('cash','نقداً'),('card','بطاقة'),('bank','تحويل'),('cheque','شيك')],
                     validators=[Optional()])
    tax_rate = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(0,100)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    submit = SubmitField('تأكيد الحجز')

class ShopPreorderForm(FlaskForm):
    quantity = IntegerField('الكمية المحجوزة',
                            validators=[DataRequired(), NumberRange(min=1, message="❌ الكمية يجب أن تكون 1 أو أكثر")])
    prepaid_amount = DecimalField('المبلغ المدفوع مسبقاً', places=2,
                                  validators=[DataRequired(), NumberRange(min=0, message="❌ المبلغ لا يمكن أن يكون سالباً")])
    payment_method = SelectField('طريقة الدفع',
                     choices=[('cash','نقدي'),('card','بطاقة'),('bank','تحويل'),('cheque','شيك')],
                     validators=[Optional()])
    submit = SubmitField('تأكيد الحجز')

class ServiceRequestForm(FlaskForm):
    customer_id = QuerySelectField(
        'العميل',
        query_factory=lambda: Customer.query.order_by(Customer.name).all(),
        get_label='name',
        allow_blank=False
    )
    name = StringField('اسم العميل', validators=[DataRequired(), Length(max=100)])
    phone = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=100)])
    vehicle_vrn = StringField('لوحة المركبة', validators=[DataRequired(), Length(max=50)])
    vehicle_type_id = QuerySelectField(
        'نوع المعدة/المركبة',
        query_factory=lambda: EquipmentType.query.order_by(EquipmentType.name).all(),
        get_label='name',
        allow_blank=True
    )
    vehicle_model = StringField('موديل المركبة/المعدة', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    problem_description = TextAreaField('وصف المشكلة', validators=[Optional(), Length(max=1000)])
    engineer_notes = TextAreaField('ملاحظات المهندس', validators=[Optional(), Length(max=2000)])
    description = TextAreaField('وصف عام', validators=[Optional(), Length(max=500)])
    priority = SelectField(
        'الأولوية',
        choices=[('LOW', 'منخفضة'), ('MEDIUM', 'متوسطة'),
                 ('HIGH', 'عالية'), ('URGENT', 'عاجلة')],
        default='MEDIUM',
        validators=[Optional()]
    )
    estimated_duration = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    actual_duration = IntegerField('المدة الفعلية (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost = DecimalField('التكلفة المتوقعة', places=2, validators=[Optional(), NumberRange(min=0)])
    total_cost = DecimalField('التكلفة النهائية', places=2, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(0, 100)])
    start_time = DateField('وقت البدء', format='%Y-%m-%d', validators=[Optional()])
    end_time = DateField('وقت الانتهاء', format='%Y-%m-%d', validators=[Optional()])
    status = SelectField(
        'الحالة',
        choices=[('PENDING', 'معلق'), ('DIAGNOSIS', 'تشخيص'),
                 ('IN_PROGRESS', 'قيد التنفيذ'), ('COMPLETED', 'مكتمل'),
                 ('CANCELLED', 'ملغي'), ('ON_HOLD', 'مؤجل')],
        default='PENDING',
        validators=[DataRequired()]
    )

    submit = SubmitField('إرسال')

# الحقل الاختياري للفني
    mechanic_id         = QuerySelectField(
                              'الفني',
                              query_factory=lambda: User.query.filter_by(is_active=True).all(),
                              get_label='username',
                              allow_blank=True
                          )

    submit              = SubmitField('حفظ طلب الصيانة')


class ShipmentItemForm(FlaskForm):
    product_id     = QuerySelectField(
        'الصنف',
        query_factory=lambda: Product.query.order_by(Product.name).all(),
        get_label='name',
        allow_blank=False
    )
    warehouse_id   = QuerySelectField(
        'المخزن',
        query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
        get_label='name',
        allow_blank=False
    )
    quantity       = IntegerField(
        'الكمية',
        validators=[DataRequired(), NumberRange(min=1)]
    )
    unit_cost      = DecimalField(
        'سعر الوحدة',
        places=2,
        validators=[DataRequired(message="❌ أدخل سعرًا لكل وحدة"), NumberRange(min=0)]
    )
    declared_value = DecimalField(
        'القيمة المعلنة',
        places=2,
        validators=[Optional(), NumberRange(min=0)]
    )
    notes          = None  # إذا تستعمل حقل ملاحظات في _form.html يمكنك إضافته هنا
    submit         = SubmitField('حفظ البند')

class ShipmentPartnerForm(FlaskForm):
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(),
                                  get_label='name', allow_blank=False)
    identity_number = StringField('رقم الهوية/السجل', validators=[Optional(), Length(max=100)])
    phone_number = StringField('رقم الجوال', validators=[Optional(), Length(max=20)])
    address = StringField('العنوان', validators=[Optional(), Length(max=200)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', validators=[Optional(), NumberRange(min=0)], places=2)  # ✅ مضاف
    expiry_date = DateField('تاريخ الانتهاء', validators=[Optional()])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=500)])
    share_percentage = DecimalField('نسبة الشريك (%)', validators=[Optional(), NumberRange(min=0, max=100)], places=2)  # ✅ مضاف
    share_amount = DecimalField('مساهمة الشريك', validators=[Optional(), NumberRange(min=0)], places=2)  # ✅ مضاف
    submit = SubmitField('حفظ مساهمة الشريك')


class ShipmentForm(FlaskForm):
    shipment_number   = StringField('رقم الشحنة', validators=[DataRequired(), Length(max=50)])
    shipment_date     = DateField('تاريخ الشحنة', format='%Y-%m-%d', validators=[Optional()])
    expected_arrival  = DateField('تاريخ الوصول المتوقع', format='%Y-%m-%d', validators=[Optional()])
    actual_arrival    = DateField('التاريخ الفعلي للوصول', format='%Y-%m-%d', validators=[Optional()])
    origin            = StringField('مكان الإرسال', validators=[Optional(), Length(max=100)])
    destination_id    = QuerySelectField(
        'وجهة المستودع',
        query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
        get_label='name',
        allow_blank=False
    )
    carrier           = StringField('شركة الشحن', validators=[Optional(), Length(max=100)])
    tracking_number   = StringField('رقم التتبع', validators=[Optional(), Length(max=100)])
    status            = SelectField(
        'الحالة',
        choices=[
            ('PENDING','معلق'),
            ('IN_TRANSIT','قيد الشحن'),
            ('ARRIVED','مستلم'),
            ('DELAYED','متأخر'),
            ('CANCELLED','ملغي')
        ],
        default='PENDING'
    )
    value_before      = DecimalField('القيمة قبل التكاليف', places=2, validators=[Optional()])
    shipping_cost     = DecimalField('تكلفة الشحن', places=2, validators=[Optional()])
    customs           = DecimalField('الجمارك', places=2, validators=[Optional()])
    vat               = DecimalField('الضريبة (VAT)', places=2, validators=[Optional()])
    insurance         = DecimalField('التأمين', places=2, validators=[Optional()])
    total_value       = DecimalField('القيمة الإجمالية', places=2, validators=[Optional()])
    notes             = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    partner_links     = FieldList(FormField(ShipmentPartnerForm), min_entries=1)
    items             = FieldList(FormField(ShipmentItemForm),      min_entries=1)
    submit            = SubmitField('حفظ الشحنة')


# --- Universal & Custom Reports ---
class UniversalReportForm(FlaskForm):
    table = SelectField('نوع التقرير', choices=[], validators=[Optional()])
    date_field = SelectField('حقل التاريخ', choices=[], validators=[Optional()])
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    selected_fields = SelectMultipleField('أعمدة التقرير', choices=[], coerce=str, validators=[Optional()])
    submit = SubmitField('عرض التقرير')

class AuditLogFilterForm(FlaskForm):
    model_name = SelectField('النموذج', choices=[('', 'الكل'), ('Customer','عملاء'), ('Product','منتجات'), ('Sale','مبيعات')], validators=[Optional()])
    action = SelectField('الإجراء', choices=[('', 'الكل'), ('CREATE','إنشاء'), ('UPDATE','تحديث'), ('DELETE','حذف')], validators=[Optional()])
    start_date = DateField('من تاريخ', validators=[Optional()])
    end_date = DateField('إلى تاريخ', validators=[Optional()])
    export_format = SelectField('تصدير كـ', choices=[('pdf','PDF'),('csv','CSV'),('excel','Excel')], default='pdf')
    include_details = BooleanField('تضمين التفاصيل الكاملة')
    submit = SubmitField('تصفية السجلات')

    def validate(self):
        rv = super().validate()
        if not rv:
            return False
        if self.start_date.data and self.end_date.data and self.start_date.data > self.end_date.data:
            self.end_date.errors.append('❌ تاريخ النهاية يجب أن يكون بعد تاريخ البداية')
            return False
        return True


class CustomReportForm(FlaskForm):
    report_type = SelectField('نوع التقرير', choices=[('inventory','المخزون'),('sales','المبيعات'),('customers','العملاء'),('financial','مالي')], validators=[DataRequired()])
    parameters = TextAreaField('المعايير (JSON)', validators=[Optional()])
    submit = SubmitField('إنشاء التقرير')

# --- Employee & Expense Forms ---
class EmployeeForm(FlaskForm):
    name = StringField('اسم الموظف', validators=[DataRequired()])
    position = StringField('الوظيفة', validators=[Optional()])
    phone = StringField('الهاتف', validators=[Optional()])
    bank_name = StringField('اسم البنك', validators=[Optional()])
    account_number = StringField('رقم الحساب', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

class ExpenseTypeForm(FlaskForm):
    name = StringField('اسم نوع المصروف', validators=[DataRequired()])
    description = StringField('وصف اختياري', validators=[Optional()])
    submit = SubmitField('حفظ')

class ExpenseForm(FlaskForm):
    date = DateField('التاريخ', validators=[DataRequired()])
    amount = DecimalField('المبلغ', validators=[DataRequired(), NumberRange(min=0)])
    type_id = SelectField('نوع المصروف', coerce=int, validators=[DataRequired()])
    employee_id = SelectField('الموظف', coerce=int, validators=[Optional()])
    paid_to = StringField('مدفوع إلى', validators=[Optional(), Length(max=200)])
    payment_method = SelectField('طريقة الدفع',
                     choices=[('cash','نقدًا'),('cheque','شيك'),
                              ('bank','تحويل بنكي'),('visa','فيزا/ائتمان'),('other','أخرى')],
                     validators=[DataRequired()])
    payment_details = StringField('تفاصيل الدفع', validators=[Optional(), Length(max=255)])
    description = StringField('وصف مختصر', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    tax_invoice_number = StringField('رقم فاتورة ضريبية', validators=[Optional(), Length(max=100)])
    warehouse_id = QuerySelectField('المستودع', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
                                    get_label='name', allow_blank=True, blank_text='(لا يوجد)')
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(),
                                  get_label='name', allow_blank=True, blank_text='(لا يوجد)')
    submit = SubmitField('حفظ')
# --- Online Customer & Cart Forms ---
class CustomerFormOnline(FlaskForm):
    name = StringField('الاسم الكامل', validators=[DataRequired()])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    phone = StringField('رقم الجوال', validators=[DataRequired()])
    whatsapp = StringField('واتساب', validators=[Optional()])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    address = StringField('العنوان', validators=[Optional()])
    submit = SubmitField('تسجيل')

class AddToOnlineCartForm(FlaskForm):
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1, message="❌ الحد الأدنى 1")])
    submit = SubmitField('أضف للسلة')

class OnlinePaymentForm(FlaskForm):
    payment_ref = StringField('مرجع الدفع', validators=[DataRequired(), Length(max=100)])
    order_id = IntegerField('رقم الطلب', validators=[DataRequired()])
    amount = DecimalField('المبلغ', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=[('ILS','ILS'),('USD','USD'),('EUR','EUR')], default='ILS', validators=[DataRequired()])
    method = StringField('وسيلة الدفع', validators=[Optional(), Length(max=50)])
    gateway = StringField('بوابة الدفع', validators=[Optional(), Length(max=50)])
    status = SelectField('حالة المعاملة',
             choices=[('PENDING','قيد المعالجة'),('SUCCESS','ناجح'),('FAILED','فشل'),('REFUNDED','مرجوع')],
             default='PENDING', validators=[DataRequired()])
    transaction_data = TextAreaField('بيانات المعاملة (JSON)', validators=[Optional()])
    processed_at = DateField('تاريخ المعالجة', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('حفظ الدفع')
    def validate_transaction_data(self, field):
        if field.data:
            try: json.loads(field.data)
            except ValueError: raise ValidationError("❌ بيانات JSON غير صالحة")

# --- Exchange Transaction ---
class ExchangeTransactionForm(FlaskForm):
    product_id = QuerySelectField('المنتج', query_factory=lambda: Product.query.all())
    warehouse_id = QuerySelectField('المخزن', query_factory=lambda: Warehouse.query.all())
    quantity = IntegerField('الكمية', validators=[NumberRange(min=1)])
    direction = SelectField('النوع', choices=[('in','استلام'),('out','صرف'),('adjustment','تعديل')])
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.all())
    notes = TextAreaField('ملاحظات')
    submit = SubmitField('حفظ المعاملة')

# --- Equipment Type ---
class EquipmentTypeForm(FlaskForm):
    name = StringField('اسم نوع المعدة', validators=[DataRequired(), Length(max=100)])
    model_number = StringField('رقم النموذج', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    category = StringField('الفئة', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('ملاحظات إضافية', validators=[Optional(), Length(max=200)])
    submit = SubmitField('حفظ نوع المعدة')

class ServiceTaskForm(FlaskForm):
    description = StringField('وصف المهمة', validators=[DataRequired(), Length(max=200)])
    quantity    = IntegerField('الكمية',     validators=[DataRequired(), NumberRange(min=1)])
    unit_price  = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount    = DecimalField('خصم %',      places=2, validators=[Optional(), NumberRange(0,100)])
    tax_rate    = DecimalField('ضريبة %',    places=2, validators=[Optional(), NumberRange(0,100)])
    note        = StringField('ملاحظات',    validators=[Optional(), Length(max=200)])
    submit      = SubmitField('حفظ المهمة')

# 2) ServiceDiagnosisForm
class ServiceDiagnosisForm(FlaskForm):
    problem             = TextAreaField('المشكلة',           validators=[DataRequired()])
    cause               = TextAreaField('السبب',             validators=[DataRequired()])
    solution            = TextAreaField('الحل المقترح',      validators=[DataRequired()])
    estimated_duration  = IntegerField('المدة المتوقعة (دقيقة)', validators=[Optional(), NumberRange(min=0)])
    estimated_cost      = DecimalField('التكلفة المتوقعة',   places=2, validators=[Optional(), NumberRange(min=0)])
    submit              = SubmitField('حفظ التشخيص')
    
# --- Sale & Invoice Forms ---
class ServicePartForm(FlaskForm):
    part_id = QuerySelectField('القطعة/المكوّن',
                               query_factory=lambda: Product.query.order_by(Product.name).all(),
                               get_label='name', allow_blank=False)
    warehouse_id = QuerySelectField('المخزن',
                                    query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
                                    get_label='name', allow_blank=False)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(min=0, max=100)])
    note = StringField('ملاحظات', validators=[Optional(), Length(max=200)])
    partner_id = QuerySelectField('الشريك',
                                  query_factory=lambda: Partner.query.order_by(Partner.name).all(),
                                  get_label='name', allow_blank=True, blank_text='(بدون شريك)')
    share_percentage = DecimalField('نسبة الشريك (%)', places=2, validators=[Optional(), NumberRange(min=0, max=100)])  # ✅ أعيدت صياغتها صحيحة
    submit = SubmitField('حفظ المكوّن')


class InvoiceLineForm(FlaskForm):
    description = StringField('الوصف', validators=[DataRequired(), Length(max=200)])
    quantity = DecimalField('الكمية', places=2, validators=[DataRequired(), NumberRange(min=0)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(0,100)])
    discount = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(0,100)])
    submit = SubmitField('إضافة سطر')

class SaleLineForm(FlaskForm):
    product_id = QuerySelectField('الصنف', query_factory=lambda: Product.query.order_by(Product.name).all(), get_label='name')
    warehouse_id = QuerySelectField('المخزن', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), get_label='name')
    quantity = DecimalField('الكمية', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    unit_price = DecimalField('سعر الوحدة', places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount_rate = DecimalField('خصم %', places=2, validators=[Optional(), NumberRange(0,100)], default=0)
    tax_rate = DecimalField('ضريبة %', places=2, validators=[Optional(), NumberRange(0,100)], default=0)
    note = StringField('ملاحظات', validators=[Optional(), Length(max=200)])
    submit = SubmitField('إضافة سطر')

class SaleForm(FlaskForm):
    sale_number = StringField('رقم البيع', validators=[Optional(), Length(max=50)])
    sale_date = DateField('تاريخ البيع', format='%Y-%m-%d', validators=[Optional()])
    customer_id = QuerySelectField('العميل', query_factory=lambda: Customer.query.order_by(Customer.name).all(), get_label='name', allow_blank=False)
    seller_id = QuerySelectField('البائع', query_factory=lambda: User.query.order_by(User.username).all(), get_label='username', allow_blank=False)
    status = SelectField('الحالة', choices=[('DRAFT','مسودة'),('CONFIRMED','مؤكد'),('CANCELLED','ملغي'),('REFUNDED','مرتجع')], default='DRAFT', validators=[DataRequired()])
    currency = SelectField('عملة', choices=[('ILS','ILS'),('USD','USD'),('EUR','EUR')], default='ILS')
    tax_rate = DecimalField('ضريبة %', places=2, default=0, validators=[Optional(), NumberRange(0,100)])
    discount_total = DecimalField('خصم إجمالي', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=500)])
    billing_address = TextAreaField('عنوان الفواتير', validators=[Optional(), Length(max=500)])
    shipping_cost = DecimalField('تكلفة الشحن', places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=500)])
    lines = FieldList(FormField(SaleLineForm), min_entries=1)
    preorder_id = IntegerField('رقم الحجز', validators=[Optional()])
    submit = SubmitField('حفظ البيع')

class InvoiceForm(FlaskForm):
    source = SelectField('مصدر الفاتورة', choices=[
        ('manual','يدوي'),('sale','بيع'),('service','صيانة'),
        ('preorder','حجز مسبق'),('supplier','مورد'),
        ('partner','شريك'),('online','أونلاين')
    ], default='manual', validators=[DataRequired()])
    customer_id = QuerySelectField('العميل', query_factory=lambda: Customer.query.all(), get_label='name', allow_blank=False)
    supplier_id = QuerySelectField('المورد', query_factory=lambda: Supplier.query.all(), get_label='name', allow_blank=True)
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.all(), get_label='name', allow_blank=True)
    sale_id = IntegerField('رقم البيع', validators=[Optional()])
    service_id = IntegerField('رقم الصيانة', validators=[Optional()])
    preorder_id = IntegerField('رقم الحجز', validators=[Optional()])
    date = DateField('تاريخ الفاتورة', format='%Y-%m-%d', validators=[Optional()])
    due_date = DateField('تاريخ الاستحقاق', format='%Y-%m-%d', validators=[Optional()])
    status = SelectField('الحالة', choices=[
        ('UNPAID','غير مدفوعة'),('PARTIALLY_PAID','مدفوعة جزئياً'),
        ('PAID','مدفوعة'),('ON_HOLD','مؤجلة')
    ], validators=[DataRequired()])
    total_amount = DecimalField('المبلغ الإجمالي', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    terms = TextAreaField('شروط الفاتورة', validators=[Optional(), Length(max=500)])
    is_cancelled = BooleanField('ملغاة')
    lines = FieldList(FormField(InvoiceLineForm), min_entries=1)
    submit = SubmitField('حفظ الفاتورة')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        # ✅ تحقق من ارتباط المصدر بجهة صحيحة
        mapping = {
            'sale': self.sale_id.data,
            'service': self.service_id.data,
            'preorder': self.preorder_id.data,
            'supplier': self.supplier_id.data,
            'partner': self.partner_id.data,
            'manual': True,
            'online': True
        }
        if not mapping.get(self.source.data):
            self.source.errors.append(f"❌ يجب ربط الفاتورة بـ {self.source.data} صالح.")
            return False
        # ✅ تحقق من وجود عميل للفواتير التي تتطلبه
        if self.source.data in ['manual','sale','service','preorder','online'] and not self.customer_id.data:
            self.customer_id.errors.append("❌ يجب اختيار العميل لهذه الفاتورة.")
            return False
        # ✅ تحقق من وجود بنود
        if not self.lines.entries or all(not line.form.description.data for line in self.lines):
            self.lines.errors.append("❌ يجب إضافة بند واحد على الأقل إلى الفاتورة.")
            return False
        return True


# --- Product & Partner Share ---
class ProductPartnerShareForm(FlaskForm):
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(), get_label='name', allow_blank=False)
    share_percentage = DecimalField('نسبة الشريك %', places=2, validators=[DataRequired(), NumberRange(0,100)])
    share_amount = DecimalField('قيمة مساهمة الشريك', places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

class ProductForm(FlaskForm):
    sku = StringField('SKU', validators=[Optional(), Length(max=50)])
    name = StringField('الاسم', validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('الوصف')
    part_number = StringField('رقم القطعة', validators=[Optional(), Length(max=100)])
    brand = StringField('الماركة', validators=[Optional(), Length(max=100)])
    commercial_name = StringField('الاسم التجاري', validators=[Optional(), Length(max=100)])
    chassis_number = StringField('رقم الشاصي', validators=[Optional(), Length(max=100)])
    serial_no = StringField('الرقم التسلسلي', validators=[Optional(), Length(max=100)])
    barcode = StringField('الباركود', validators=[Optional(), Length(max=100)])
    cost_before_shipping = DecimalField('التكلفة قبل الشحن', validators=[Optional(), NumberRange(min=0)])
    cost_after_shipping = DecimalField('التكلفة بعد الشحن', validators=[Optional(), NumberRange(min=0)])
    unit_price_before_tax = DecimalField('سعر الوحدة قبل الضريبة', validators=[Optional(), NumberRange(min=0)])
    price = DecimalField('السعر', validators=[DataRequired(), NumberRange(min=0)])
    min_price = DecimalField('السعر الأدنى', validators=[Optional(), NumberRange(min=0)])
    max_price = DecimalField('السعر الأعلى', validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('نسبة الضريبة', validators=[Optional(), NumberRange(0,100)])
    on_hand = IntegerField('المتوفر', validators=[Optional(), NumberRange(min=0)])
    reserved_quantity = IntegerField('الكمية المحجوزة', validators=[Optional(), NumberRange(min=0)])
    quantity = IntegerField('الكمية', validators=[Optional(), NumberRange(min=0)])
    min_qty = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    reorder_point = IntegerField('نقطة إعادة الطلب', validators=[Optional(), NumberRange(min=0)])
    condition = SelectField('الحالة', choices=[('NEW','جديد'),('USED','مستعمل'),('REFURBISHED','مجدّد')])
    origin_country = StringField('بلد المنشأ', validators=[Optional(), Length(max=50)])
    warranty_period = IntegerField('مدة الضمان', validators=[Optional(), NumberRange(min=0)])
    weight = DecimalField('الوزن', validators=[Optional(), NumberRange(min=0)])
    dimensions = StringField('الأبعاد', validators=[Optional(), Length(max=50)])
    is_active = BooleanField('نشط')
    is_digital = BooleanField('رقمي')
    is_exchange = BooleanField('قابل للتبادل')
    vehicle_type_id = QuerySelectField('نوع المركبة', query_factory=lambda: EquipmentType.query.all(), allow_blank=True, get_label='name')
    category_id = QuerySelectField('الفئة', query_factory=lambda: ProductCategory.query.all(), allow_blank=True, get_label='name')
    supplier_id = QuerySelectField('المورد الرئيسي', query_factory=lambda: Supplier.query.all(), allow_blank=True, get_label='name')
    supplier_international_id = QuerySelectField('المورد الدولي', query_factory=lambda: Supplier.query.all(), allow_blank=True, get_label='name')
    supplier_local_id = QuerySelectField('المورد المحلي', query_factory=lambda: Supplier.query.all(), allow_blank=True, get_label='name')
    partners = FieldList(FormField(ProductPartnerShareForm), min_entries=1)
    submit = SubmitField('حفظ')

# --- Warehouse & Category ---
class WarehouseForm(FlaskForm):
    name = StringField('اسم المستودع', validators=[DataRequired(), Length(max=100)])
    warehouse_type = SelectField('نوع المستودع', choices=[('INVENTORY','مخزون'),('PARTNER','مخزن شركاء'),('EXCHANGE','مخزن تبادل')], validators=[DataRequired()])
    location = StringField('الموقع', validators=[Optional(), Length(max=200)])
    parent_id = QuerySelectField('المستودع الأب', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), get_label='name', allow_blank=True, blank_text='(لا يوجد)')
    partner_id = QuerySelectField('الشريك', query_factory=lambda: Partner.query.order_by(Partner.name).all(), get_label='name', allow_blank=True, blank_text='(لا يوجد)')
    share_percent = DecimalField('نسبة الشريك %', places=2, validators=[Optional(), NumberRange(0,100)])
    capacity = IntegerField('السعة القصوى', validators=[Optional(), NumberRange(min=0)])
    current_occupancy = IntegerField('المشغول حالياً', validators=[Optional(), NumberRange(min=0)])
    is_active = BooleanField('نشط', default=True)
    submit = SubmitField('حفظ المستودع')

class ProductCategoryForm(FlaskForm):
    name = StringField('اسم الفئة', validators=[DataRequired(), Length(max=100)])
    parent_id = QuerySelectField('الفئة الأب', query_factory=lambda: ProductCategory.query.all(), get_label='name', allow_blank=True, blank_text='(لا يوجد)')
    description = TextAreaField('الوصف', validators=[Optional()])
    image_url = StringField('رابط الصورة', validators=[Optional()])
    submit = SubmitField('حفظ الفئة')

class ImportForm(FlaskForm):
    warehouse_id = QuerySelectField(
        'المستودع',
        query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(),
        get_label='name',
        allow_blank=False
    )
    file = FileField(
        'ملف CSV',
        validators=[DataRequired(), FileAllowed(['csv'])]
    )
    submit = SubmitField('استيراد')


class NoteForm(FlaskForm):
    content     = TextAreaField('المحتوى', validators=[DataRequired(), Length(max=1000)])
    entity_type = SelectField('نوع الكيان', choices=[], validators=[Optional()])
    entity_id   = StringField('معرّف الكيان', validators=[Optional(), Length(max=50)])
    is_pinned   = BooleanField('مثبّتة')
    priority    = SelectField('الأولوية', choices=[('LOW','منخفضة'),('MEDIUM','متوسطة'),('HIGH','عالية')], default='MEDIUM', validators=[Optional()])
    submit      = SubmitField('💾 حفظ الملاحظة')

# --- Stock & Inventory ---
class StockLevelForm(FlaskForm):
    product_id = QuerySelectField('المنتج', query_factory=lambda: Product.query.order_by(Product.name).all(), get_label='name', allow_blank=False)
    warehouse_id = QuerySelectField('المخزن', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), get_label='name', allow_blank=False)
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=0)])
    min_stock = IntegerField('الحد الأدنى', validators=[Optional(), NumberRange(min=0)])
    max_stock = IntegerField('الحد الأقصى', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('حفظ مستوى المخزون')

class InventoryAdjustmentForm(FlaskForm):
    product_id = QuerySelectField('المنتج', query_factory=lambda: Product.query.order_by(Product.name).all(), get_label='name', allow_blank=False)
    warehouse_id = QuerySelectField('المخزن', query_factory=lambda: Warehouse.query.order_by(Warehouse.name).all(), get_label='name', allow_blank=False)
    adjustment_type = SelectField('نوع التعديل', choices=[('ADD','إضافة'),('REMOVE','إزالة'),('CORRECTION','تصحيح')], default='CORRECTION')
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('السبب', validators=[DataRequired()])
    submit = SubmitField('تطبيق التعديل')
# ----------------------------------------
# Form لتصدير جهات اتصال العملاء
# ----------------------------------------
class ExportContactsForm(FlaskForm):
    customer_ids = SelectMultipleField(
        'اختر العملاء',
        coerce=int,
        validators=[DataRequired(message='❌ اختر عميلًا واحدًا على الأقل')]
    )
    fields = SelectMultipleField(
        'الحقول',
        choices=[
            ('name','الاسم'),
            ('phone','الجوال'),
            ('whatsapp','واتساب'),
            ('email','البريد الإلكتروني'),
            ('address','العنوان'),
            ('notes','ملاحظات')
        ],
        default=['name','phone','email']
    )
    format = SelectField(
        'صيغة التصدير',
        choices=[('vcf','vCard (VCF)'),('csv','CSV'),('excel','Excel')],
        default='vcf'
    )
    submit = SubmitField('تصدير')

# --- Online Cart Payment ---
def luhn_check(card_number):
    """تحقق من صحة البطاقة بخوارزمية Luhn"""
    num = [int(ch) for ch in card_number if ch.isdigit()]
    checksum = 0
    reverse = num[::-1]
    for i, digit in enumerate(reverse):
        if i % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0

class OnlineCartPaymentForm(FlaskForm):
    payment_method = SelectField(
        'طريقة الدفع',
        choices=[('card', 'بطاقة'), ('bank', 'تحويل بنكي'), ('cash', 'نقدي')],
        validators=[DataRequired()]
    )
    card_holder = StringField('اسم حامل البطاقة', validators=[Optional(), Length(max=100)])
    card_number = StringField('رقم البطاقة', validators=[Optional(), Length(min=12, max=19)])
    expiry = StringField('تاريخ الانتهاء (MM/YY)', validators=[Optional(), Length(min=5, max=5)])
    cvv = StringField('CVV', validators=[Optional(), Length(min=3, max=4)])
    shipping_address = TextAreaField('عنوان الشحن', validators=[Optional(), Length(max=300)])
    billing_address = TextAreaField('عنوان الفاتورة', validators=[Optional(), Length(max=300)])
    transaction_data = TextAreaField('بيانات إضافية للبوابة (JSON)', validators=[Optional()])
    submit = SubmitField('تأكيد الدفع')

    def validate_card_number(self, field):
        if self.payment_method.data == 'card':
            if not field.data or not field.data.isdigit() or not luhn_check(field.data):
                raise ValidationError("❌ رقم البطاقة غير صالح")

    def validate_expiry(self, field):
        if self.payment_method.data == 'card':
            if not re.match(r'^(0[1-9]|1[0-2])\/\d{2}$', field.data or ""):
                raise ValidationError("❌ تاريخ الانتهاء يجب أن يكون بصيغة MM/YY")

class ExportPaymentsForm(FlaskForm):
    payment_ids = SelectMultipleField(
        'اختر الدفعات',
        coerce=int,
        validators=[DataRequired(message='❌ اختر دفعة واحدة على الأقل')]
    )
    format = SelectField(
        'صيغة التصدير',
        choices=[('csv','CSV'),('excel','Excel')],
        default='csv'
    )
    submit = SubmitField('تصدير')
