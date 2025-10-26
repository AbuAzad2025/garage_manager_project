from __future__ import annotations
import enum
import re, hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from flask import current_app, has_request_context, request
from flask_login import UserMixin, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    and_,
    case,
    event,
    func,
    insert,
    or_,
    select,
    text as sa_text,
    update,
    inspect,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Session as _SA_Session, relationship, object_session, validates

from extensions import db
from barcodes import normalize_barcode

class Archive(db.Model):
    __tablename__ = 'archives'
    
    id = Column(Integer, primary_key=True)
    record_type = Column(String(50), nullable=False, index=True)
    record_id = Column(Integer, nullable=False, index=True)
    table_name = Column(String(100), nullable=False)
    archived_data = Column(Text, nullable=False)
    archive_reason = Column(String(200))
    archived_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    archived_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    original_created_at = Column(DateTime)
    original_updated_at = Column(DateTime)
    user = relationship('User', backref='archives')
    
    def __repr__(self):
        return f'<Archive {self.record_type}:{self.record_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'record_type': self.record_type,
            'record_id': self.record_id,
            'table_name': self.table_name,
            'archived_data': json.loads(self.archived_data) if self.archived_data else {},
            'archive_reason': self.archive_reason,
            'archived_by': self.archived_by,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
            'original_created_at': self.original_created_at.isoformat() if self.original_created_at else None,
            'original_updated_at': self.original_updated_at.isoformat() if self.original_updated_at else None,
            'user_name': self.user.username if self.user else None
        }
    
    @classmethod
    def archive_record(cls, record, reason=None, user_id=None):
        if not user_id:
            user_id = current_user.id if current_user and current_user.is_authenticated else None
        
        record_dict = {}
        for column in record.__table__.columns:
            value = getattr(record, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, Decimal):
                value = float(value)
            record_dict[column.name] = value
        archive = cls(
            record_type=record.__tablename__,
            record_id=record.id,
            table_name=record.__tablename__,
            archived_data=json.dumps(record_dict, ensure_ascii=False, default=str),
            archive_reason=reason,
            archived_by=user_id,
            original_created_at=getattr(record, 'created_at', None),
            original_updated_at=getattr(record, 'updated_at', None)
        )
        
        db.session.add(archive)
        db.session.flush()
        return archive

user_permissions = db.Table(
    "user_permissions",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)

def sa_str_enum(enum_or_values, name=None):
    native = False
    if isinstance(enum_or_values, type) and issubclass(enum_or_values, enum.Enum):
        try:
            return SAEnum(enum_or_values, name=name, values_callable=lambda e: [m.value for m in e], native_enum=native)
        except TypeError:
            vals = [m.value for m in enum_or_values]
            return SAEnum(*vals, name=name, native_enum=native)
    try:
        vals = [(m.value if isinstance(m, enum.Enum) else str(m)) for m in enum_or_values]
    except TypeError:
        vals = [str(enum_or_values)]
    return SAEnum(*vals, name=name, native_enum=native)

CURRENCY_CHOICES = [
    ("ILS", "شيكل إسرائيلي"), 
    ("USD", "دولار أمريكي"), 
    ("EUR", "يورو"), 
    ("JOD", "دينار أردني"), 
    ("AED", "درهم إماراتي"), 
    ("SAR", "ريال سعودي"),
    ("EGP", "جنيه مصري"),
    ("GBP", "جنيه إسترليني")
]
CENT = Decimal("0.01")
TWOPLACES = Decimal("0.01")
TWO = TWOPLACES

def D(x):
    try:
        return Decimal(str(x)) if x is not None else Decimal("0.00")
    except Exception:
        return Decimal("0.00")

def q(x) -> Decimal:
    try:
        return Decimal(str(x or 0)).quantize(TWOPLACES, ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def _ar_label(val, mapping):
    return mapping.get(val, val)

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).translate(_AR_DIGITS)
    s = re.sub(r"\D+", "", s)
    return s[:20]

def normalize_email(raw: str | None) -> str:
    return (raw or "").strip().lower()

class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    BANK = "bank"
    CARD = "card"
    CHEQUE = "cheque"
    ONLINE = "online"

    @property
    def label(self):
        return {
            "cash": "نقدًا",
            "bank": "تحويل بنكي",
            "card": "بطاقة",
            "cheque": "شيك",
            "online": "أونلاين",
        }[self.value]


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"

    @property
    def label(self):
        return {
            "PENDING": "قيد الانتظار",
            "COMPLETED": "مكتمل",
            "FAILED": "فشل",
            "REFUNDED": "مسترجع",
            "CANCELLED": "ملغي",
        }[self.value]


class PaymentDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"

    @property
    def label(self):
        return {"IN": "وارد", "OUT": "صادر"}[self.value]


class InvoiceStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

    @property
    def label(self):
        return {
            "UNPAID": "غير مدفوعة",
            "PARTIAL": "مدفوعة جزئيًا",
            "PAID": "مدفوعة",
            "CANCELLED": "ملغاة",
            "REFUNDED": "مسترجعة",
        }[self.value]


class PaymentProgress(str, enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    REFUNDED = "REFUNDED"

    @property
    def label(self):
        return {
            "PENDING": "قيد الانتظار",
            "PARTIAL": "مدفوعة جزئيًا",
            "PAID": "مدفوعة",
            "REFUNDED": "مسترجعة",
        }[self.value]


class SaleStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "completed"  # للتوافق مع البيانات القديمة
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

    @property
    def label(self):
        return {
            "DRAFT": "مسودة",
            "CONFIRMED": "مؤكدة",
            "completed": "مكتملة",  # للتوافق مع البيانات القديمة
            "CANCELLED": "ملغاة",
            "REFUNDED": "مسترجعة",
        }[self.value]


_ALLOWED_SALE_TRANSITIONS = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"CANCELLED", "REFUNDED"},
    "completed": {"CANCELLED", "REFUNDED"},  # للتوافق مع البيانات القديمة
    "CANCELLED": set(),
    "REFUNDED": set(),
}


class ServiceStatus(str, enum.Enum):
    PENDING = "PENDING"
    DIAGNOSIS = "DIAGNOSIS"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ON_HOLD = "ON_HOLD"

    @property
    def label(self):
        return {
            "PENDING": "قيد الانتظار",
            "DIAGNOSIS": "تشخيص",
            "IN_PROGRESS": "قيد التنفيذ",
            "COMPLETED": "مكتملة",
            "CANCELLED": "ملغاة",
            "ON_HOLD": "معلقة",
        }[self.value]


class ServicePriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"

    @property
    def label(self):
        return {
            "LOW": "منخفضة",
            "MEDIUM": "متوسطة",
            "HIGH": "عالية",
            "URGENT": "عاجلة",
        }[self.value]


class TransferDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"
    ADJUSTMENT = "ADJUSTMENT"

    @property
    def label(self):
        return {
            "IN": "وارد",
            "OUT": "صادر",
            "ADJUSTMENT": "تسوية",
        }[self.value]


class PreOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"

    @property
    def label(self):
        return {
            "PENDING": "قيد الانتظار",
            "CONFIRMED": "مؤكدة",
            "FULFILLED": "مكتملة",
            "CANCELLED": "ملغاة",
        }[self.value]


class WarehouseType(str, enum.Enum):
    MAIN = "MAIN"
    PARTNER = "PARTNER"
    INVENTORY = "INVENTORY"
    EXCHANGE = "EXCHANGE"
    ONLINE = "ONLINE"

    @property
    def label(self):
        return {
            "MAIN": "رئيسي",
            "PARTNER": "شريك",
            "INVENTORY": "ملكيتي",
            "EXCHANGE": "تبادل",
            "ONLINE": "أونلاين",
        }[self.value]


class PaymentEntityType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    PARTNER = "PARTNER"
    SHIPMENT = "SHIPMENT"
    EXPENSE = "EXPENSE"
    LOAN = "LOAN"
    SALE = "SALE"
    INVOICE = "INVOICE"
    PREORDER = "PREORDER"
    SERVICE = "SERVICE"

    @property
    def label(self):
        return {
            "CUSTOMER": "عميل",
            "SUPPLIER": "مورد",
            "PARTNER": "شريك",
            "SHIPMENT": "شحنة",
            "EXPENSE": "مصاريف",
            "LOAN": "قرض",
            "SALE": "بيع",
            "INVOICE": "فاتورة",
            "PREORDER": "طلب مسبق",
            "SERVICE": "صيانة",
        }[self.value]


class InvoiceSource(str, enum.Enum):
    MANUAL = "MANUAL"
    SALE = "SALE"
    SERVICE = "SERVICE"
    PREORDER = "PREORDER"
    SUPPLIER = "SUPPLIER"
    PARTNER = "PARTNER"
    ONLINE = "ONLINE"

    @property
    def label(self):
        return {
            "MANUAL": "يدوي",
            "SALE": "بيع",
            "SERVICE": "صيانة",
            "PREORDER": "طلب مسبق",
            "SUPPLIER": "مورد",
            "PARTNER": "شريك",
            "ONLINE": "أونلاين",
        }[self.value]


class PartnerSettlementStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

    @property
    def label(self):
        return {
            "DRAFT": "مسودة",
            "CONFIRMED": "مؤكدة",
            "CANCELLED": "ملغاة",
        }[self.value]


class SupplierSettlementStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

    @property
    def label(self):
        return {
            "DRAFT": "مسودة",
            "CONFIRMED": "مؤكدة",
            "CANCELLED": "ملغاة",
        }[self.value]


class SupplierSettlementMode(str, enum.Enum):
    ON_RECEIPT = "ON_RECEIPT"
    ON_CONSUME = "ON_CONSUME"

    @property
    def label(self):
        return {
            "ON_RECEIPT": "عند الاستلام",
            "ON_CONSUME": "عند الاستهلاك",
        }[self.value]


class ProductCondition(str, enum.Enum):
    NEW = "NEW"
    USED = "USED"
    REFURBISHED = "REFURBISHED"

    @property
    def label(self):
        return {
            "NEW": "جديد",
            "USED": "مستعمل",
            "REFURBISHED": "مجدّد",
        }[self.value]


class ShipmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    IN_CUSTOMS = "IN_CUSTOMS"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"

    @property
    def label(self):
        return {
            "DRAFT": "مسودة",
            "PENDING": "قيد الانتظار",
            "IN_TRANSIT": "قيد النقل",
            "IN_CUSTOMS": "في الجمارك",
            "ARRIVED": "وصلت",
            "DELIVERED": "تم التسليم",
            "CANCELLED": "ملغاة",
            "RETURNED": "مرتجعة",
        }[self.value]

    @property
    def color(self):
        return {
            "DRAFT": "secondary",
            "PENDING": "warning",
            "IN_TRANSIT": "info",
            "IN_CUSTOMS": "primary",
            "ARRIVED": "success",
            "DELIVERED": "success",
            "CANCELLED": "danger",
            "RETURNED": "warning",
        }[self.value]

    @property
    def icon(self):
        return {
            "DRAFT": "fa-edit",
            "PENDING": "fa-clock",
            "IN_TRANSIT": "fa-truck",
            "IN_CUSTOMS": "fa-building",
            "ARRIVED": "fa-check-circle",
            "DELIVERED": "fa-check-double",
            "CANCELLED": "fa-times-circle",
            "RETURNED": "fa-undo",
        }[self.value]


class ShipmentPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

    @property
    def label(self):
        return {
            "LOW": "منخفضة",
            "NORMAL": "عادية",
            "HIGH": "عالية",
            "URGENT": "عاجلة",
        }[self.value]

    @property
    def color(self):
        return {
            "LOW": "success",
            "NORMAL": "info",
            "HIGH": "warning",
            "URGENT": "danger",
        }[self.value]

    @property
    def icon(self):
        return {
            "LOW": "fa-arrow-down",
            "NORMAL": "fa-minus",
            "HIGH": "fa-arrow-up",
            "URGENT": "fa-exclamation-triangle",
        }[self.value]


class DeliveryMethod(str, enum.Enum):
    STANDARD = "STANDARD"
    EXPRESS = "EXPRESS"
    OVERNIGHT = "OVERNIGHT"
    SAME_DAY = "SAME_DAY"
    PICKUP = "PICKUP"

    @property
    def label(self):
        return {
            "STANDARD": "عادي",
            "EXPRESS": "سريع",
            "OVERNIGHT": "ليلي",
            "SAME_DAY": "نفس اليوم",
            "PICKUP": "استلام",
        }[self.value]

    @property
    def color(self):
        return {
            "STANDARD": "info",
            "EXPRESS": "warning",
            "OVERNIGHT": "primary",
            "SAME_DAY": "success",
            "PICKUP": "secondary",
        }[self.value]


class AccountType(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

    @property
    def label(self):
        return {
            "ASSET": "أصل",
            "LIABILITY": "التزام",
            "EQUITY": "حقوق ملكية",
            "REVENUE": "إيراد",
            "EXPENSE": "مصروف",
        }[self.value]


class DeletionType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    PARTNER = "PARTNER"
    SALE = "SALE"
    INVOICE = "INVOICE"
    PAYMENT = "PAYMENT"
    PURCHASE = "PURCHASE"
    EXPENSE = "EXPENSE"
    SERVICE = "SERVICE"
    CHECK = "CHECK"
    SHIPMENT = "SHIPMENT"
    PREORDER = "PREORDER"

    @property
    def label(self):
        return {
            "CUSTOMER": "عميل",
            "SUPPLIER": "مورد",
            "PARTNER": "شريك",
            "SALE": "بيع",
            "INVOICE": "فاتورة",
            "PAYMENT": "دفعة",
            "PURCHASE": "مشتريات",
            "EXPENSE": "مصروف",
            "SERVICE": "طلب صيانة",
            "CHECK": "شيك",
            "SHIPMENT": "شحنة",
            "PREORDER": "حجز مسبق"
        }[self.value]


class DeletionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RESTORED = "RESTORED"

    @property
    def label(self):
        return {
            "PENDING": "قيد الانتظار",
            "COMPLETED": "مكتمل",
            "FAILED": "فشل",
            "RESTORED": "مستعاد",
        }[self.value]

    @property
    def color(self):
        return {
            "PENDING": "warning",
            "COMPLETED": "success",
            "FAILED": "danger",
            "RESTORED": "info",
        }[self.value]

class SystemSettings(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    data_type = db.Column(db.String(20), default='string')  # string, boolean, number, json
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @classmethod
    def get_setting(cls, key, default=None):
        """Get a system setting value"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.data_type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        elif setting.data_type == 'number':
            try:
                return float(setting.value)
            except (ValueError, TypeError):
                return default
        elif setting.data_type == 'json':
            try:
                return json.loads(setting.value)
            except (ValueError, TypeError):
                return default
        else:
            return setting.value or default

    @classmethod
    def set_setting(cls, key, value, description=None, data_type='string', is_public=False):
        """Set a system setting value"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(
                key=key,
                description=description,
                data_type=data_type,
                is_public=is_public
            )
            db.session.add(setting)
        
        if data_type == 'json':
            setting.value = json.dumps(value)
        else:
            setting.value = str(value)
        
        setting.description = description or setting.description
        setting.data_type = data_type
        setting.is_public = is_public
        setting.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        return setting

class Currency(db.Model):
    __tablename__ = "currencies"
    code = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    symbol = db.Column(db.String(10))
    decimals = db.Column(db.Integer, nullable=False, server_default=sa_text("2"), default=2)
    is_active = db.Column(db.Boolean, nullable=False, server_default=sa_text("1"), default=True)
    __table_args__ = ()


class DeletionLog(db.Model):
    """سجل عمليات الحذف القوي مع إمكانية الاستعادة"""
    __tablename__ = "deletion_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    deletion_type = db.Column(db.String(20), nullable=False, index=True)  # DeletionType
    entity_id = db.Column(db.Integer, nullable=False, index=True)  # معرف الكيان المحذوف
    entity_name = db.Column(db.String(200), nullable=False)  # اسم الكيان المحذوف
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)  # DeletionStatus
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # تفاصيل الحذف
    deleted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    deletion_reason = db.Column(db.Text)  # سبب الحذف
    confirmation_code = db.Column(db.String(50), unique=True, index=True)  # كود التأكيد
    
    # البيانات المحذوفة (JSON)
    deleted_data = db.Column(db.JSON)  # البيانات المحذوفة للاستعادة
    related_entities = db.Column(db.JSON)  # الكيانات المرتبطة المحذوفة
    
    # تفاصيل العمليات العكسية
    stock_reversals = db.Column(db.JSON)  # عمليات إرجاع المخزون
    accounting_reversals = db.Column(db.JSON)  # عمليات إرجاع المحاسبة
    balance_reversals = db.Column(db.JSON)  # عمليات إرجاع الأرصدة
    
    # تفاصيل الاستعادة
    restored_at = db.Column(db.DateTime)
    restored_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    restoration_notes = db.Column(db.Text)
    
    # علاقات
    deleted_by_user = db.relationship("User", foreign_keys=[deleted_by], backref="deletions_made")
    restored_by_user = db.relationship("User", foreign_keys=[restored_by], backref="deletions_restored")
    
    __table_args__ = (
        db.Index('ix_deletion_type_status', 'deletion_type', 'status'),
        db.Index('ix_deletion_entity', 'deletion_type', 'entity_id'),
        db.CheckConstraint('status IN ("PENDING","COMPLETED","FAILED","RESTORED")', name='chk_deletion_status'),
    )
    
    def __repr__(self):
        return f"<DeletionLog {self.deletion_type}:{self.entity_id} by {self.deleted_by}>"
    
    @property
    def can_restore(self):
        """هل يمكن استعادة هذا الحذف؟"""
        return self.status == DeletionStatus.COMPLETED.value and self.deleted_data is not None
    
    @property
    def is_restored(self):
        """هل تم استعادة هذا الحذف؟"""
        return self.status == DeletionStatus.RESTORED.value
    
    def mark_completed(self, deleted_data=None, related_entities=None, 
                      stock_reversals=None, accounting_reversals=None, balance_reversals=None):
        """تسجيل اكتمال الحذف"""
        self.status = DeletionStatus.COMPLETED.value
        self.deleted_data = deleted_data
        self.related_entities = related_entities
        self.stock_reversals = stock_reversals
        self.accounting_reversals = accounting_reversals
        self.balance_reversals = balance_reversals
    
    def mark_failed(self, error_message):
        """تسجيل فشل الحذف"""
        self.status = DeletionStatus.FAILED.value
        self.deletion_reason = f"{self.deletion_reason or ''}\nخطأ: {error_message}"
    
    def mark_restored(self, restored_by, notes=None):
        """تسجيل الاستعادة"""
        self.status = DeletionStatus.RESTORED.value
        self.restored_at = datetime.now(timezone.utc)
        self.restored_by = restored_by
        self.restoration_notes = notes

class ExchangeRate(db.Model):
    __tablename__ = "exchange_rates"
    id = db.Column(db.Integer, primary_key=True)
    base_code = db.Column(db.String(10), db.ForeignKey("currencies.code"), nullable=False, index=True)
    quote_code = db.Column(db.String(10), db.ForeignKey("currencies.code"), nullable=False, index=True)
    rate = db.Column(Numeric(18, 8), nullable=False)
    valid_from = db.Column(db.DateTime, nullable=False, index=True, server_default=func.now(), default=func.now())
    source = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, nullable=False, server_default=sa_text("1"), default=True)
    __table_args__ = (
        db.UniqueConstraint("base_code", "quote_code", "valid_from", name="uq_fx_pair_from"),
    )

def _currency_codes_from_db() -> set[str]:
    try:
        rows = db.session.query(Currency.code).filter(Currency.is_active.is_(True)).all()
        s = {str(r[0]).upper().strip() for r in rows}
        return {c for c in s if c}
    except Exception:
        return set()

def currency_codes() -> set[str]:
    dynamic = _currency_codes_from_db()
    if dynamic:
        return dynamic
    return {c for c, _ in CURRENCY_CHOICES}

def currency_decimals(code: str | None) -> int:
    c = (code or "").upper().strip()
    try:
        row = db.session.query(Currency.decimals).filter(Currency.code == c).one_or_none()
        if row and isinstance(row[0], int):
            return row[0]
    except Exception:
        pass
    return 2

ALLOWED_PAYMENT_DIRECTIONS: dict[PaymentEntityType, set[str]] = {
    PaymentEntityType.CUSTOMER: {"IN", "OUT"},
    PaymentEntityType.SUPPLIER: {"IN", "OUT"},
    PaymentEntityType.PARTNER: {"IN", "OUT"},
    PaymentEntityType.SALE: {"IN", "OUT"},
    PaymentEntityType.SERVICE: {"IN", "OUT"},
    PaymentEntityType.INVOICE: {"IN", "OUT"},
    PaymentEntityType.PREORDER: {"IN", "OUT"},
    PaymentEntityType.LOAN: {"IN", "OUT"},
    PaymentEntityType.EXPENSE: {"OUT"},  # المصاريف دائماً صادرة
    PaymentEntityType.SHIPMENT: {"IN", "OUT"},
}

def is_direction_allowed(entity_type: PaymentEntityType | str, direction: PaymentDirection | str) -> bool:
    try:
        # إذا كان entity_type هو بالفعل PaymentEntityType، نستخدمه مباشرة
        if isinstance(entity_type, PaymentEntityType):
            et = entity_type
        else:
            # إذا كان string، نحوله
            et = PaymentEntityType(str(entity_type))
    except Exception:
        return False
    try:
        # إذا كان direction هو بالفعل PaymentDirection، نحصل على value
        if isinstance(direction, PaymentDirection):
            d = direction.value
        else:
            # نحاول التحويل
            d = PaymentDirection(str(direction)).value
    except Exception:
        # إذا فشل، نستخدم الـ string مباشرة
        d = str(direction).upper()
    allowed = ALLOWED_PAYMENT_DIRECTIONS.get(et, set())
    return d in allowed

MONEY_QUANT = TWOPLACES

def money(x) -> Decimal:
    try:
        return Decimal(str(x or 0)).quantize(MONEY_QUANT, ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def generate_idempotency_key(prefix: str = "pay") -> str:
    raw = f"{prefix}:{uuid.uuid4()}:{datetime.now(timezone.utc).timestamp()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

def ensure_currency(cur: str | None, default: str = "ILS") -> str:
    base = (default or "ILS").upper().strip()
    c = (cur or base).upper().strip()
    pool = currency_codes()
    return c if c in pool else base

def _get_payment_model():
    P = globals().get("Payment")
    if P is not None:
        return P
    try:
        from models import Payment as _P
        return _P
    except Exception:
        return None

def fx_rate(base: str, quote: str, at: datetime | None = None, raise_on_missing: bool = False) -> Decimal:
    """سعر الصرف الذكي - محلي أولاً، ثم عالمي
    
    Args:
        base: العملة الأساسية
        quote: العملة المقابلة
        at: التاريخ (اختياري)
        raise_on_missing: إذا True، يرمي استثناء بدلاً من إرجاع صفر
    
    Returns:
        سعر الصرف أو Decimal("0") أو يرمي استثناء
    """
    b = ensure_currency(base)
    qv = ensure_currency(quote)
    if b == qv:
        return Decimal("1")
    t = at or datetime.now(timezone.utc)
    
    # 1. البحث عن سعر محلي (مدخل من الادمن)
    q = (
        db.session.query(ExchangeRate.rate)
        .filter(
            ExchangeRate.base_code == b,
            ExchangeRate.quote_code == qv,
            ExchangeRate.is_active.is_(True),
            ExchangeRate.valid_from <= t,
        )
        .order_by(ExchangeRate.valid_from.desc())
    )
    v = q.first()
    if v:
        return Decimal(str(v[0]))
    
    # 2. في حال عدم وجود سعر محلي، جرب السيرفرات العالمية
    try:
        online_rate = _fetch_external_fx_rate(b, qv, t)
        if online_rate and online_rate > Decimal("0"):
            return online_rate
    except Exception as e:
        if raise_on_missing:
            raise ValueError(f"⚠️ سعر الصرف غير متوفر لـ {b}/{qv}. يرجى:\n1. إدخال سعر يدوي من إعدادات العملات\n2. تفعيل السيرفر الأونلاين\n3. إعادة المحاولة لاحقاً")
    
    # 3. إذا فشل كل شيء
    if raise_on_missing:
        raise ValueError(f"⚠️ سعر الصرف غير متوفر لـ {b}/{qv}. يرجى:\n1. إدخال سعر يدوي من إعدادات العملات\n2. تفعيل السيرفر الأونلاين\n3. إعادة المحاولة لاحقاً")
    
    return Decimal("0")

def _fetch_external_fx_rate(base: str, quote: str, at: datetime) -> Decimal:
    """سحب سعر الصرف من السيرفرات العالمية مع التحكم في الإعدادات"""
    import requests
    import json
    from decimal import Decimal
    
    # التحقق من إعدادات النظام
    try:
        from models import SystemSettings
        online_fx_enabled = SystemSettings.get_setting('online_fx_enabled', True)
        if not online_fx_enabled:
            return None
    except:
        # في حالة عدم وجود SystemSettings، استمر بالطريقة العادية
        pass
    
    # قائمة السيرفرات العالمية (بترتيب الأولوية)
    fx_services = [
        _fetch_from_fixer_io,
        _fetch_from_exchangerate_api,
        _fetch_from_currencylayer,
        _fetch_from_exchangerate_host
    ]
    
    for service in fx_services:
        try:
            rate = service(base, quote, at)
            if rate and rate > Decimal("0"):
                # حفظ السعر في قاعدة البيانات للاستخدام المستقبلي
                _save_external_rate(base, quote, rate, at)
                return rate
        except Exception:
            continue
    
    raise ValueError("fx.external_services_unavailable")

def _fetch_from_fixer_io(base: str, quote: str, at: datetime) -> Decimal:
    """سحب من Fixer.io"""
    import requests
    from decimal import Decimal
    
    # Fixer.io API (مجاني مع حدود)
    url = f"http://data.fixer.io/api/latest"
    params = {
        'access_key': 'YOUR_FIXER_API_KEY',  # يحتاج API key
        'base': base,
        'symbols': quote
    }
    
    response = requests.get(url, params=params, timeout=10)
    data = response.json()
    
    if data.get('success') and quote in data.get('rates', {}):
        return Decimal(str(data['rates'][quote]))
    
    raise ValueError("fixer_io_failed")

def _fetch_from_exchangerate_api(base: str, quote: str, at: datetime) -> Decimal:
    """سحب من ExchangeRate-API.com"""
    import requests
    from decimal import Decimal
    
    # ExchangeRate-API.com (مجاني بدون API key)
    url = f"https://api.exchangerate-api.com/v4/latest/{base}"
    
    response = requests.get(url, timeout=10)
    data = response.json()
    
    if 'rates' in data and quote in data['rates']:
        return Decimal(str(data['rates'][quote]))
    
    raise ValueError("exchangerate_api_failed")

def _fetch_from_currencylayer(base: str, quote: str, at: datetime) -> Decimal:
    """سحب من CurrencyLayer"""
    import requests
    from decimal import Decimal
    
    # CurrencyLayer API
    url = f"http://api.currencylayer.com/live"
    params = {
        'access_key': 'YOUR_CURRENCYLAYER_API_KEY',  # يحتاج API key
        'currencies': quote,
        'source': base
    }
    
    response = requests.get(url, params=params, timeout=10)
    data = response.json()
    
    if data.get('success') and f"{base}{quote}" in data.get('quotes', {}):
        return Decimal(str(data['quotes'][f"{base}{quote}"]))
    
    raise ValueError("currencylayer_failed")

def _fetch_from_exchangerate_host(base: str, quote: str, at: datetime) -> Decimal:
    """سحب من ExchangeRate-Host"""
    import requests
    from decimal import Decimal
    
    # ExchangeRate-Host (مجاني)
    url = f"https://api.exchangerate.host/latest"
    params = {
        'base': base,
        'symbols': quote
    }
    
    response = requests.get(url, params=params, timeout=10)
    data = response.json()
    
    if data.get('success') and 'rates' in data and quote in data['rates']:
        return Decimal(str(data['rates'][quote]))
    
    raise ValueError("exchangerate_host_failed")

def _save_external_rate(base: str, quote: str, rate: Decimal, at: datetime):
    """حفظ السعر الخارجي في قاعدة البيانات"""
    try:
        # استخدام connection منفصل لتجنب مشاكل flush
        from sqlalchemy import text as sa_text
        
        # التحقق من وجود السعر مسبقاً
        result = db.session.connection().execute(
            sa_text("""
                SELECT id FROM exchange_rates 
                WHERE base_code = :base 
                AND quote_code = :quote 
                AND DATE(valid_from) = DATE(:valid_from)
                LIMIT 1
            """),
            {"base": base, "quote": quote, "valid_from": at}
        ).fetchone()
        
        if not result:
            # إدراج السعر مباشرة باستخدام SQL
            db.session.connection().execute(
                sa_text("""
                    INSERT INTO exchange_rates 
                    (base_code, quote_code, rate, valid_from, source, is_active)
                    VALUES (:base, :quote, :rate, :valid_from, 'External API', 1)
                """),
                {"base": base, "quote": quote, "rate": float(rate), "valid_from": at}
            )
    except Exception:
        # في حال فشل الحفظ، لا نريد إيقاف العملية
        pass

def convert_amount(amount: Decimal | float | str, from_code: str, to_code: str, at: datetime | None = None) -> Decimal:
    amt = money(amount)
    r = fx_rate(from_code, to_code, at)
    if r <= Decimal("0"):
        raise ValueError("fx.rate_unavailable")
    return money(amt * r)

def auto_update_missing_rates():
    """تحديث تلقائي للأسعار المفقودة من السيرفرات العالمية"""
    try:
        # الحصول على جميع العملات النشطة
        currencies = db.session.query(Currency).filter_by(is_active=True).all()
        currency_codes = [c.code for c in currencies]
        
        updated_count = 0
        today = datetime.now(timezone.utc).date()
        
        for base_code in currency_codes:
            for quote_code in currency_codes:
                if base_code == quote_code:
                    continue
                
                # التحقق من وجود سعر لهذا اليوم
                existing_rate = db.session.query(ExchangeRate).filter(
                    ExchangeRate.base_code == base_code,
                    ExchangeRate.quote_code == quote_code,
                    ExchangeRate.valid_from == today
                ).first()
                
                if not existing_rate:
                    try:
                        # محاولة سحب السعر من السيرفرات العالمية
                        rate = _fetch_external_fx_rate(base_code, quote_code, datetime.now(timezone.utc))
                        if rate and rate > Decimal("0"):
                            updated_count += 1
                    except Exception:
                        continue
        
        return {
            'success': True,
            'updated_rates': updated_count,
            'message': f'تم تحديث {updated_count} سعر صرف'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'فشل في التحديث التلقائي'
        }

def get_fx_rate_with_fallback(base: str, quote: str, at: datetime | None = None) -> dict:
    """الحصول على سعر الصرف مع معلومات المصدر والبديل الذكي"""
    try:
        # محاولة جلب السعر من السيرفرات الأونلاين أولاً
        try:
            online_rate = _fetch_external_fx_rate(base, quote, at or datetime.now(timezone.utc))
            if online_rate and online_rate > Decimal("0"):
                return {
                    'rate': float(online_rate),
                    'source': 'online',
                    'base': base,
                    'quote': quote,
                    'timestamp': at or datetime.now(timezone.utc),
                    'success': True
                }
        except:
            pass
        
        # في حالة فشل الأونلاين، جرب السعر المحلي
        try:
            local_rate = fx_rate(base, quote, at)
            if local_rate and local_rate > Decimal("0"):
                return {
                    'rate': float(local_rate),
                    'source': 'manual',
                    'base': base,
                    'quote': quote,
                    'timestamp': at or datetime.now(timezone.utc),
                    'success': True
                }
        except:
            pass
        
        # في حالة فشل كل شيء، استخدم سعر افتراضي
        return {
            'rate': 1.0,
            'source': 'default',
            'base': base,
            'quote': quote,
            'timestamp': at or datetime.now(timezone.utc),
            'success': False,
            'error': 'No exchange rate available'
        }
        
    except Exception as e:
        return {
            'rate': 0.0,
            'source': 'failed',
            'base': base,
            'quote': quote,
            'timestamp': at or datetime.now(timezone.utc),
            'success': False,
            'error': str(e)
        }

def _payment_fk_column_for_type(PaymentModel, et: PaymentEntityType | str):
    etv = PaymentEntityType(str(et)).value
    mapping = {
        "CUSTOMER": PaymentModel.customer_id,
        "SUPPLIER": PaymentModel.supplier_id,
        "PARTNER": PaymentModel.partner_id,
        "SHIPMENT": PaymentModel.shipment_id,
        "EXPENSE": PaymentModel.expense_id,
        "LOAN": PaymentModel.loan_settlement_id,
        "SALE": PaymentModel.sale_id,
        "INVOICE": PaymentModel.invoice_id,
        "PREORDER": PaymentModel.preorder_id,
        "SERVICE": PaymentModel.service_id,
    }
    return mapping.get(etv)

def refundable_amount_for(entity_type: PaymentEntityType | str, entity_id: int, currency: str | None = None) -> Decimal:
    PaymentModel = _get_payment_model()
    if PaymentModel is None:
        return Decimal("0.00")

    et = PaymentEntityType(str(entity_type))
    ccy = ensure_currency(currency)
    fk_col = _payment_fk_column_for_type(PaymentModel, et)
    if fk_col is None:
        return Decimal("0.00")

    sess = db.session

    total_in_completed = Decimal(str(
        sess.query(func.coalesce(func.sum(PaymentModel.total_amount), 0))
        .filter(
            PaymentModel.entity_type == et.value,
            fk_col == int(entity_id),
            PaymentModel.currency == ccy,
            PaymentModel.direction == PaymentDirection.IN.value,
            PaymentModel.status == PaymentStatus.COMPLETED.value,
        ).scalar() or 0
    ))

    total_out_pending_completed = Decimal(str(
        sess.query(func.coalesce(func.sum(PaymentModel.total_amount), 0))
        .filter(
            PaymentModel.entity_type == et.value,
            fk_col == int(entity_id),
            PaymentModel.currency == ccy,
            PaymentModel.direction == PaymentDirection.OUT.value,
            PaymentModel.status.in_([PaymentStatus.PENDING.value, PaymentStatus.COMPLETED.value]),
        ).scalar() or 0
    ))

    remaining = total_in_completed - total_out_pending_completed
    return money(remaining)

def receivable_amount_for(entity_type: PaymentEntityType | str, entity_id: int, currency: str | None = None) -> Decimal:
    PaymentModel = _get_payment_model()
    if PaymentModel is None:
        return Decimal("0.00")

    et = PaymentEntityType(str(entity_type))
    ccy = ensure_currency(currency)
    fk_col = _payment_fk_column_for_type(PaymentModel, et)
    if fk_col is None:
        return Decimal("0.00")

    sess = db.session

    total_out_completed = Decimal(str(
        sess.query(func.coalesce(func.sum(PaymentModel.total_amount), 0))
        .filter(
            PaymentModel.entity_type == et.value,
            fk_col == int(entity_id),
            PaymentModel.currency == ccy,
            PaymentModel.direction == PaymentDirection.OUT.value,
            PaymentModel.status == PaymentStatus.COMPLETED.value,
        ).scalar() or 0
    ))

    total_in_pending_completed = Decimal(str(
        sess.query(func.coalesce(func.sum(PaymentModel.total_amount), 0))
        .filter(
            PaymentModel.entity_type == et.value,
            fk_col == int(entity_id),
            PaymentModel.currency == ccy,
            PaymentModel.direction == PaymentDirection.IN.value,
            PaymentModel.status.in_([PaymentStatus.PENDING.value, PaymentStatus.COMPLETED.value]),
        ).scalar() or 0
    ))

    remaining = total_out_completed - total_in_pending_completed
    return money(remaining)


def validate_payment_policies(*, entity_type: PaymentEntityType | str, entity_id: int, direction: PaymentDirection | str, amount, currency: str | None = None) -> None:
    amt = money(amount)
    if amt <= Decimal("0.00"):
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")

    cur = ensure_currency(currency)

    try:
        dval = PaymentDirection(str(direction)).value
    except Exception:
        dval = str(direction).upper()

    et = PaymentEntityType(str(entity_type))

    # السماح بجميع الاتجاهات للجميع عدا النفقات
    # النفقات دائماً صادرة فقط
    if et == PaymentEntityType.EXPENSE and dval == "IN":
        raise ValueError("النفقات دائماً صادرة فقط")

    # إزالة القيود الأخرى للسماح بمرونة أكبر في الدفعات
    # يمكن إضافة قيود إضافية هنا حسب الحاجة

class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=func.now(), index=True)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=func.now(), onupdate=func.now(), index=True)

class AuditMixin:
    @classmethod
    def __declare_last__(cls):
        from sqlalchemy import event as _evt

        @_evt.listens_for(cls, "before_update", propagate=True)
        def _capture_prev_state(mapper, connection, target):
            try:
                insp = inspect(target)
                prev = {}
                for attr in mapper.column_attrs:
                    hist = insp.attrs[attr.key].history
                    if hist.has_changes() and hist.deleted:
                        prev[attr.key] = hist.deleted[0]
                setattr(target, "_previous_state", prev)
            except Exception:
                setattr(target, "_previous_state", {})

class AuthEvent(str, enum.Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAIL = "LOGIN_FAIL"
    PASSWORD_SET = "PASSWORD_SET"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    USER_ACTIVATE = "USER_ACTIVATE"
    USER_DEACTIVATE = "USER_DEACTIVATE"
    ROLE_CHANGE = "ROLE_CHANGE"
    PERM_GRANT = "PERM_GRANT"
    PERM_REVOKE = "PERM_REVOKE"


class AuthAudit(db.Model):
    __tablename__ = "auth_audit"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=True)
    event = db.Column(db.String(40), nullable=False, index=True)
    success = db.Column(db.Boolean, nullable=False, server_default=sa_text("1"))
    ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    note = db.Column(db.String(255))
    meta = db.Column("metadata", db.JSON, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), index=True)

    user = relationship("User", backref=db.backref("auth_events", lazy="dynamic"))

    __table_args__ = ()


def _auth_log(
    event: AuthEvent | str,
    *,
    user_id: int | None,
    success: bool = True,
    note: str | None = None,
    meta: dict | None = None,
) -> None:
    try:
        ip = request.remote_addr if has_request_context() else None
        ua = request.user_agent.string if has_request_context() and request.user_agent else None
    except Exception:
        ip, ua = None, None

    rec = AuthAudit(
        user_id=user_id,
        event=str(event),
        success=bool(success),
        ip=ip,
        user_agent=ua,
        note=note,
        meta=meta or {},
    )

    try:
        cu = getattr(current_user, "_get_current_object", lambda: None)()
    except Exception:
        cu = None

    sess = None
    if cu is not None:
        try:
            sess = object_session(cu)
        except Exception:
            sess = None
    if sess is None:
        sess = db.session

    try:
        sess.add(rec)
        sess.flush()
    except Exception:
        pass

class User(db.Model, UserMixin, TimestampMixin, AuditMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), index=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=sa_text("1"))
    is_system_account = db.Column(db.Boolean, nullable=False, server_default=sa_text("0"), index=True)  # حساب نظام مخفي محمي
    last_login = db.Column(db.DateTime)
    last_seen = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(64))
    login_count = db.Column(db.Integer, nullable=False, server_default=sa_text("0"))
    avatar_url = db.Column(db.String(500))
    notes_text = db.Column(db.Text)
    role = relationship("Role", backref="users", lazy="select")  # ⚡ Changed from 'joined' to 'select' for better performance
    extra_permissions = relationship(
        "Permission",
        secondary=user_permissions,
        backref=db.backref("extra_users", lazy="dynamic"),
        lazy="dynamic",
    )

    mechanic_service_requests = relationship(
        "ServiceRequest",
        back_populates="mechanic",
        lazy="dynamic",
        foreign_keys="[ServiceRequest.mechanic_id]",
    )
    cancelled_service_requests = relationship(
        "ServiceRequest",
        back_populates="cancelled_by_user",
        lazy="dynamic",
        foreign_keys="[ServiceRequest.cancelled_by]",
    )

    sales = relationship(
        "Sale",
        back_populates="seller",
        lazy="dynamic",
        foreign_keys="[Sale.seller_id]",
    )
    cancelled_sales = relationship(
        "Sale",
        back_populates="cancelled_by_user",
        lazy="dynamic",
        foreign_keys="[Sale.cancelled_by]",
    )

    __table_args__ = ()

    @validates("email")
    def _v_email(self, key, value):
        return (value or "").strip().lower()

    @validates("username")
    def _v_username(self, key, value):
        return (value or "").strip()

    @property
    def role_name_l(self) -> str:
        return (getattr(self.role, "name", "") or "").strip().lower()

    @property
    def is_system(self) -> bool:
        """حساب نظام محمي ومخفي"""
        return bool(getattr(self, 'is_system_account', False)) or self.username == '__OWNER__'
    
    @property
    def is_super_role(self) -> bool:
        return self.role_name_l in {"developer", "owner", "super_admin"} or self.is_system

    @property
    def is_admin_role(self) -> bool:
        return self.role_name_l == "admin"

    def set_password(self, password: str) -> None:
        if not password or not isinstance(password, str):
            raise ValueError("password required")
        prev = bool(self.password_hash)
        self.password_hash = generate_password_hash(password)
        try:
            from flask import has_request_context
            if has_request_context():
                _auth_log(
                    AuthEvent.PASSWORD_CHANGE if prev else AuthEvent.PASSWORD_SET,
                    user_id=getattr(self, "id", None),
                    success=True,
                )
        except Exception:
            pass

    def check_password(self, password: str) -> bool:
        try:
            ok = bool(self.password_hash) and check_password_hash(self.password_hash, password or "")
            if not ok:
                try:
                    from flask import has_request_context
                    if has_request_context():
                        _auth_log(AuthEvent.LOGIN_FAIL, user_id=getattr(self, "id", None), success=False)
                except Exception:
                    pass
            return ok
        except Exception:
            try:
                from flask import has_request_context
                if has_request_context():
                    _auth_log(AuthEvent.LOGIN_FAIL, user_id=getattr(self, "id", None), success=False, note="exception")
            except Exception:
                pass
            return False

    def mark_login(self, ip: str | None = None) -> None:
        self.last_login = datetime.now(timezone.utc)
        self.last_seen = self.last_login
        if ip:
            self.last_login_ip = ip
        try:
            self.login_count = int(self.login_count or 0) + 1
        except Exception:
            self.login_count = 1
        try:
            from flask import has_request_context
            if has_request_context():
                _auth_log(AuthEvent.LOGIN_SUCCESS, user_id=getattr(self, "id", None), success=True)
        except Exception:
            pass

    def has_role(self, *names: str) -> bool:
        r = self.role_name_l
        return any(r == (n or "").strip().lower() for n in names if n)

    def has_permission(self, code: str) -> bool:
        if not code:
            return False
        if self.is_super_role:
            return True
        from utils import _expand_perms, _get_user_permissions
        targets = {c.strip().lower() for c in _expand_perms(code)}
        perms = _get_user_permissions(self) or set()
        return bool(perms & targets)

    def touch(self) -> None:
        self.last_seen = datetime.now(timezone.utc)

    @property
    def avatar_or_initials(self) -> str:
        """Returns avatar URL if available, otherwise returns initials"""
        if self.avatar_url:
            return self.avatar_url
        
        # Generate initials from username or email
        name = self.username or self.email or "U"
        initials = "".join([word[0].upper() for word in name.split()[:2]])
        return initials[:2] if initials else "U"

    @property
    def display_name(self) -> str:
        """Returns display name for the user"""
        return self.username or self.email or f"User {self.id}"

    def __repr__(self):
        return f"<User {self.username or self.id}>"

class Permission(db.Model, AuditMixin):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    code = db.Column(db.String(100), unique=True, index=True)
    description = db.Column(db.String(255))
    name_ar = db.Column(db.String(120))
    module = db.Column(db.String(50), index=True)
    is_protected = db.Column(db.Boolean, nullable=False, server_default=sa_text("0"), default=False)
    aliases = db.Column(db.JSON, default=list)

    __table_args__ = ()

    @validates("name", "code")
    def _v_norm(self, key, value):
        v = (value or "").strip()
        if key == "code":
            v = v.lower()
        return v

    @validates("module")
    def _v_module(self, _, v):
        v = (v or "").strip().lower()
        return v or None

    @validates("is_protected")
    def _v_protected(self, _, v):
        return bool(v)

    @validates("aliases")
    def _v_aliases(self, _, v):
        if not v:
            return []
        if isinstance(v, str):
            try:
                arr = json.loads(v)
            except Exception:
                arr = [x for x in v.split(",")]
        elif isinstance(v, (list, tuple, set)):
            arr = list(v)
        else:
            arr = []
        out = []
        for a in arr:
            s = str(a or "").strip().lower()
            s = re.sub(r"[\s\-]+", "_", s)
            s = re.sub(r"[^a-z0-9_]+", "", s)
            s = re.sub(r"_+", "_", s).strip("_")
            if s and s not in out:
                out.append(s)
        return out

    @property
    def display_name(self) -> str:
        try:
            nm_ar = getattr(self, "name_ar", None)
            return (nm_ar or self.name or "").strip()
        except Exception:
            return (self.name or "").strip()

    def key(self) -> str:
        return (self.code or self.name or "").strip().lower()

    @property
    def aliases_set(self) -> set[str]:
        return set(self.aliases or [])

    @property
    def all_keys(self) -> set[str]:
        base = {self.key()}
        nm = (self.name or "").strip().lower()
        if nm:
            base.add(nm)
        return base | self.aliases_set

    def __repr__(self):
        return f"<Permission {self.code or self.name}>"

class Role(db.Model, AuditMixin):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        backref=db.backref("role_permissions", lazy="selectin"),
    )

    __table_args__ = ()

    @validates("name")
    def _v_name(self, key, value):
        return (value or "").strip()

    def has_permission(self, code: str) -> bool:
        from utils import _expand_perms, get_role_permissions
        if not code:
            return False
        targets = {c.strip().lower() for c in _expand_perms(code)}
        perms = get_role_permissions(self) or set()
        return bool(perms & targets)

    def __repr__(self):
        return f"<Role {self.name}>"

class Customer(db.Model, TimestampMixin, AuditMixin, UserMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    whatsapp = Column(String(20), nullable=True)  # ✅ يسمح بـ NULL
    email = Column(String(120), unique=True, nullable=True)  # ✅ يسمح بـ NULL
    address = Column(String(200))
    password_hash = Column(String(128))
    category = Column(String(20), default="عادي")
    notes = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False, server_default=sa_text("1"))
    is_online = Column(Boolean, default=False, nullable=False, server_default=sa_text("0"))
    is_archived = Column(Boolean, default=False, nullable=False, server_default=sa_text("0"))
    archived_at = Column(DateTime, index=True)
    archived_by = Column(Integer, ForeignKey("users.id"), index=True)
    archive_reason = Column(String(200))
    credit_limit = Column(Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"))
    discount_rate = Column(Numeric(5, 2), default=0, nullable=False, server_default=sa_text("0"))
    currency = Column(String(10), default="ILS", nullable=False, server_default=sa_text("'ILS'"))
    opening_balance = Column(Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"), comment="الرصيد الافتتاحي (سالب=عليه لنا، موجب=له علينا)")

    sales = relationship("Sale", back_populates="customer")
    preorders = relationship("PreOrder", back_populates="customer")
    invoices = relationship("Invoice", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")
    service_requests = relationship("ServiceRequest", back_populates="customer")
    online_carts = relationship("OnlineCart", back_populates="customer")
    online_preorders = relationship("OnlinePreOrder", back_populates="customer")
    archived_by_user = relationship("User", foreign_keys=[archived_by])

    __table_args__ = (
        CheckConstraint("credit_limit >= 0", name="ck_customer_credit_limit_non_negative"),
        CheckConstraint("discount_rate >= 0 AND discount_rate <= 100", name="ck_customer_discount_0_100"),
    )

    @property
    def password(self):
        raise AttributeError("Password access not allowed")

    @password.setter
    def password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password or "")

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        try:
            return bool(self.password_hash) and check_password_hash(self.password_hash, password or "")
        except Exception:
            return False

    def has_permission(self, *_args, **_kwargs) -> bool:
        return False

    def is_valid_email(self):
        return bool(self.email and "@" in self.email)

    @validates("email")
    def _v_email(self, _, v):
        result = (v or "").strip().lower()
        return result or None  # ✅ تحويل الفارغ إلى None

    @validates("name", "address", "notes")
    def _v_strip(self, _, v):
        s = (v or "").strip()
        return s or None

    @validates("phone", "whatsapp")
    def _v_phone_like(self, key, v):
        s = (v or "").strip()
        s = re.sub(r"\s+", "", s)
        s = "+" + re.sub(r"\D", "", s[1:]) if s.startswith("+") else re.sub(r"\D", "", s)
        digits = re.sub(r"\D", "", s)
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError(f"{key} must have 7-15 digits")
        return s

    @validates("category")
    def _v_category(self, _, v):
        allowed = {"عادي", "ذهبي", "بلاتيني"}
        val = (v or "عادي").strip()
        return val if val in allowed else "عادي"

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("discount_rate")
    def _v_discount_rate(self, _, v):
        if v is None:
            return 0
        f = float(v)
        if f < 0 or f > 100:
            raise ValueError("discount_rate must be between 0 and 100")
        return v

    @validates("credit_limit")
    def _v_credit_limit(self, _, v):
        if v is None:
            return 0
        if float(v) < 0:
            raise ValueError("credit_limit must be >= 0")
        return v

    @hybrid_property
    def total_invoiced(self):
        return float(
            db.session.query(func.coalesce(func.sum(Invoice.total_amount), 0))
            .filter(
                Invoice.customer_id == self.id,
                Invoice.status.in_(
                    [InvoiceStatus.UNPAID.value, InvoiceStatus.PARTIAL.value, InvoiceStatus.PAID.value]
                ),
            )
            .scalar()
            or 0
        )

    @total_invoiced.expression
    def total_invoiced(cls):
        return (
            select(func.coalesce(func.sum(Invoice.total_amount), 0))
            .where(
                (Invoice.customer_id == cls.id)
                & (
                    Invoice.status.in_(
                        [InvoiceStatus.UNPAID.value, InvoiceStatus.PARTIAL.value, InvoiceStatus.PAID.value]
                    )
                )
            )
            .scalar_subquery()
        )

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.customer_id == self.id,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.COMPLETED.value,
            )
            .scalar()
            or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.customer_id == cls.id)
                & (Payment.direction == PaymentDirection.IN.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )

    @hybrid_property
    def balance(self):
        """الرصيد الحقيقي = الرصيد الافتتاحي + المعاملات - الدفعات"""
        try:
            from sqlalchemy.orm import object_session
            session = object_session(self)
            if not session:
                return 0.0
            
            # الرصيد الافتتاحي
            ob = float(self.opening_balance or 0)
            
            # المبيعات المؤكدة
            sales_total = float(session.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
                Sale.customer_id == self.id,
                Sale.status == 'CONFIRMED'
            ).scalar() or 0)
            
            # الفواتير
            invoices_total = float(session.query(func.coalesce(func.sum(Invoice.total_amount), 0)).filter(
                Invoice.customer_id == self.id,
                Invoice.status.in_(['UNPAID', 'PARTIAL', 'PAID'])
            ).scalar() or 0)
            
            # الخدمات
            services_total = float(session.query(func.coalesce(func.sum(ServiceRequest.total_amount), 0)).filter(
                ServiceRequest.customer_id == self.id
            ).scalar() or 0)
            
            # الحجوزات المسبقة
            preorders_total = float(session.query(func.coalesce(func.sum(PreOrder.total_amount), 0)).filter(
                PreOrder.customer_id == self.id
            ).scalar() or 0)
            
            # الدفعات الواردة (مباشرة + من المبيعات + من الفواتير + من الخدمات)
            # ✅ COMPLETED + PENDING (الشيكات المعلقة تُحسب)
            # ❌ نستبعد BOUNCED/FAILED/CANCELLED (ملغاة)
            payments_in_direct = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(
                Payment.customer_id == self.id,
                Payment.direction == 'IN',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_in_sales = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).join(
                Sale, Payment.sale_id == Sale.id
            ).filter(
                Sale.customer_id == self.id,
                Payment.direction == 'IN',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_in_invoices = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).join(
                Invoice, Payment.invoice_id == Invoice.id
            ).filter(
                Invoice.customer_id == self.id,
                Payment.direction == 'IN',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_in_services = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).join(
                ServiceRequest, Payment.service_id == ServiceRequest.id
            ).filter(
                ServiceRequest.customer_id == self.id,
                Payment.direction == 'IN',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_in = payments_in_direct + payments_in_sales + payments_in_invoices + payments_in_services
            
            # الدفعات الصادرة (مباشرة + من المبيعات + من الفواتير + من الخدمات)
            payments_out_direct = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(
                Payment.customer_id == self.id,
                Payment.direction == 'OUT',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_out_sales = float(session.query(func.coalesce(func.sum(Payment.total_amount), 0)).join(
                Sale, Payment.sale_id == Sale.id
            ).filter(
                Sale.customer_id == self.id,
                Payment.direction == 'OUT',
                Payment.status.in_(['COMPLETED', 'PENDING'])
            ).scalar() or 0)
            
            payments_out = payments_out_direct + payments_out_sales
            
            # 🎯 الرصيد النهائي بالطريقة المحاسبية الصحيحة (مدين - دائن)
            # الرصيد الافتتاحي:
            #   - إذا سالب (-11200) = عليه لنا (مدين) → يضاف للمدين بقيمة موجبة
            #   - إذا موجب (+11200) = له علينا (دائن) → يضاف للدائن
            
            # المدين (Debit): ما عليه لنا
            debit = 0.0
            if ob < 0:  # رصيد افتتاحي سالب = عليه لنا
                debit += abs(ob)
            # المبيعات والفواتير والخدمات والحجوزات
            debit += sales_total + invoices_total + services_total + preorders_total
            
            # الدائن (Credit): ما له علينا
            credit = 0.0
            if ob > 0:  # رصيد افتتاحي موجب = له علينا
                credit += ob
            credit += payments_in  # الدفعات الواردة
            credit -= payments_out  # الدفعات الصادرة تنقص من الدائن
            
            # الرصيد النهائي = الدائن - المدين
            # سالب (-X) = عليه لنا (مدين)
            # موجب (+X) = له علينا (دائن)
            final_balance = credit - debit
            
            return final_balance
        except Exception as e:
            import sys
            print(f"⚠️ خطأ في حساب رصيد العميل #{self.id}: {e}", file=sys.stderr)
            return 0.0

    @hybrid_property
    def balance_in_ils(self):
        """الرصيد بالشيكل - حساب دقيق مع تحويل العملات"""
        try:
            # حساب المدفوعات بالشيكل
            payments = db.session.query(Payment).filter(
                Payment.customer_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value
            ).all()
            
            total_paid_ils = Decimal("0.00")
            for payment in payments:
                amount = Decimal(str(payment.total_amount or 0))
                currency = payment.currency or "ILS"
                direction = payment.direction
                
                # تحويل للشيكل باستخدام الأسعار الحقيقية
                if currency == "ILS":
                    converted_amount = amount
                else:
                    try:
                        # استخدام الأسعار اليدوية فقط لتجنب مشاكل قاعدة البيانات
                        converted_amount = convert_amount(amount, currency, "ILS", payment.payment_date)
                    except Exception as e:
                        # تسجيل الخطأ - لا نستخدم المبلغ الأصلي لأنه بعملة مختلفة
                        try:
                            from flask import current_app
                            current_app.logger.error(f"❌ خطأ في تحويل العملة لحساب رصيد العميل #{self.id}: {str(e)}")
                        except:
                            pass
                        # تجاهل هذا المبلغ من الحساب
                        continue
                
                # تطبيق اتجاه الدفع
                if direction == PaymentDirection.IN.value:
                    total_paid_ils += converted_amount
                else:
                    total_paid_ils -= converted_amount
            
            # حساب الفواتير بالشيكل
            invoices = db.session.query(Invoice).filter(
                Invoice.customer_id == self.id,
                Invoice.status.in_(["UNPAID", "PARTIAL", "PAID"])
            ).all()
            
            total_invoiced_ils = Decimal("0.00")
            for invoice in invoices:
                amount = Decimal(str(invoice.total_amount or 0))
                currency = getattr(invoice, 'currency', 'ILS')
                
                if currency == "ILS":
                    total_invoiced_ils += amount
                else:
                    try:
                        converted_amount = convert_amount(amount, currency, "ILS", invoice.invoice_date)
                        total_invoiced_ils += converted_amount
                    except Exception as e:
                        # تسجيل الخطأ عند فشل التحويل
                        try:
                            from flask import current_app
                            current_app.logger.error(f"❌ خطأ في تحويل العملة للفاتورة #{invoice.id}: {str(e)}")
                        except:
                            pass
                        # تجاهل هذا المبلغ
                        continue
            
            return total_invoiced_ils - total_paid_ils
        except Exception:
            return Decimal("0.00")

    @hybrid_property
    def credit_status(self):
        try:
            if float(self.credit_limit or 0) > 0 and float(self.balance or 0) >= float(self.credit_limit or 0):
                return "معلق"
        except Exception:
            pass
        return "نشط"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone or "",
            "whatsapp": self.whatsapp or "",
            "email": self.email or "",
            "address": self.address or "",
            "category": self.category,
            "currency": self.currency,
            "is_active": bool(self.is_active),
            "is_online": bool(self.is_online),
            "is_archived": bool(self.is_archived),
            "discount_rate": float(self.discount_rate or 0),
            "credit_limit": float(self.credit_limit or 0),
            "total_invoiced": self.total_invoiced,
            "total_paid": self.total_paid,
            "balance": self.balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_id(self) -> str:
        return f"c:{self.id}"

    def __repr__(self):
        return f"<Customer {self.name}>"


@event.listens_for(Customer, "before_insert")
@event.listens_for(Customer, "before_update")
def _customer_normalize(_m, _c, t: Customer):
    t.email = (t.email or "").strip().lower()
    for key in ("phone", "whatsapp"):
        val = getattr(t, key, None)
        if val is not None:
            s = str(val).strip()
            s = re.sub(r"\s+", "", s)
            s = "+" + re.sub(r"\D", "", s[1:]) if s.startswith("+") else re.sub(r"\D", "", s)
            setattr(t, key, s)
    t.category = (t.category or "عادي").strip() or "عادي"
    t.currency = (t.currency or "ILS").upper()


@event.listens_for(Customer, "after_insert")
@event.listens_for(Customer, "after_update")
def _customer_opening_balance_gl(mapper, connection, target: "Customer"):
    """
    إنشاء/تحديث GLBatch للرصيد الافتتاحي للعميل
    
    ⚡ محسّن: يفحص إذا تغير opening_balance فعلاً قبل إنشاء GL
    """
    try:
        # ⚡ تحسين: فحص التغيير فقط على update
        if mapper and connection:
            try:
                hist = inspect(target).attrs.get('opening_balance')
                if hist and hasattr(hist, 'history'):
                    if not hist.history.has_changes():
                        return  # لم يتغير opening_balance - لا داعي للقيد
            except:
                pass  # في حالة after_insert لن يكون هناك history
        
        opening_balance = float(getattr(target, 'opening_balance', 0) or 0)
        if opening_balance == 0:
            return
        
        # القيد المحاسبي للرصيد الافتتاحي:
        # موجب = له علينا: دائن AR، مدين رأس المال
        # سالب = عليه لنا: مدين AR، دائن رأس المال
        if opening_balance > 0:  # موجب = له علينا
            entries = [
                ("3000_EQUITY", abs(opening_balance), 0),  # مدين
                (GL_ACCOUNTS.get("AR", "1100_AR"), 0, abs(opening_balance)),  # دائن
            ]
        else:  # سالب = عليه لنا
            entries = [
                (GL_ACCOUNTS.get("AR", "1100_AR"), abs(opening_balance), 0),  # مدين
                ("3000_EQUITY", 0, abs(opening_balance)),  # دائن
            ]
        
        memo = f"رصيد افتتاحي - {target.name}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="CUSTOMER",
            source_id=target.id,
            purpose="OPENING_BALANCE",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=f"OB-CUST-{target.id}",
            entity_type="CUSTOMER",
            entity_id=target.id
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للرصيد الافتتاحي للعميل #{target.id}: {e}", file=sys.stderr)


class Supplier(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_local = db.Column(db.Boolean, default=True, nullable=False, server_default=sa_text("1"))
    identity_number = db.Column(db.String(100), unique=True)
    contact = db.Column(db.String(200))
    phone = db.Column(db.String(20), index=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=True)
    address = db.Column(db.String(200))
    notes = db.Column(db.Text)
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"))
    payment_terms = db.Column(db.String(50))
    currency = db.Column(db.String(10), default="ILS", nullable=False, server_default=sa_text("'ILS'"))
    opening_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"), comment="الرصيد الافتتاحي (موجب=له علينا، سالب=عليه لنا)")
    
    # ربط تلقائي مع جدول العملاء
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True, nullable=True)
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    # العلاقات
    customer = db.relationship("Customer", foreign_keys=[customer_id], backref="supplier_link")
    payments = db.relationship("Payment", back_populates="supplier")
    invoices = db.relationship("Invoice", back_populates="supplier")
    preorders = db.relationship("PreOrder", back_populates="supplier")
    warehouses = db.relationship("Warehouse", back_populates="supplier")
    loan_settlements = db.relationship("SupplierLoanSettlement", back_populates="supplier", cascade="all, delete-orphan")
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])

    __table_args__ = ()

    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower() or None

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("name", "contact", "address", "notes", "payment_terms", "phone", "identity_number")
    def _v_strip(self, _, v):
        s = (v or "").strip()
        return s or None

    @hybrid_property
    def total_paid(self):
        direct = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.supplier_id == self.id,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.COMPLETED.value,
            )
            .scalar()
            or 0
        )
        via_loans = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .join(SupplierLoanSettlement, SupplierLoanSettlement.id == Payment.loan_settlement_id)
            .filter(
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.COMPLETED.value,
                SupplierLoanSettlement.supplier_id == self.id,
            )
            .scalar()
            or 0
        )
        return q(direct) + q(via_loans)

    @total_paid.expression
    def total_paid(cls):
        direct_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.supplier_id == cls.id)
                & (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )
        via_loans_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .select_from(Payment.__table__.join(SupplierLoanSettlement, SupplierLoanSettlement.id == Payment.loan_settlement_id))
            .where(
                (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (SupplierLoanSettlement.supplier_id == cls.id)
            )
            .scalar_subquery()
        )
        return direct_subq + via_loans_subq

    @hybrid_property
    def net_balance(self):
        return q(self.balance or 0) - q(self.total_paid or 0)

    @net_balance.expression
    def net_balance(cls):
        direct_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.supplier_id == cls.id)
                & (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )
        via_loans_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .select_from(Payment.__table__.join(SupplierLoanSettlement, SupplierLoanSettlement.id == Payment.loan_settlement_id))
            .where(
                (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (SupplierLoanSettlement.supplier_id == cls.id)
            )
            .scalar_subquery()
        )
        return cls.balance - (direct_subq + via_loans_subq)

    @hybrid_property
    def balance_in_ils(self):
        """الرصيد بالشيكل - حساب دقيق مع تحويل العملات"""
        try:
            # حساب المدفوعات بالشيكل
            payments = db.session.query(Payment).filter(
                Payment.supplier_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value
            ).all()
            
            total_paid_ils = Decimal("0.00")
            for payment in payments:
                amount = Decimal(str(payment.total_amount or 0))
                currency = payment.currency or "ILS"
                direction = payment.direction
                
                # تحويل للشيكل باستخدام الأسعار الحقيقية
                if currency == "ILS":
                    converted_amount = amount
                else:
                    try:
                        # استخدام الأسعار اليدوية فقط لتجنب مشاكل قاعدة البيانات
                        converted_amount = convert_amount(amount, currency, "ILS", payment.payment_date)
                    except Exception as e:
                        # تسجيل الخطأ - لا نستخدم المبلغ الأصلي لأنه بعملة مختلفة
                        try:
                            from flask import current_app
                            current_app.logger.error(f"❌ خطأ في تحويل العملة لحساب رصيد المورد #{self.id}: {str(e)}")
                        except:
                            pass
                        # تجاهل هذا المبلغ من الحساب
                        continue
                
                # تطبيق اتجاه الدفع
                if direction == PaymentDirection.OUT.value:
                    total_paid_ils += converted_amount
                else:
                    total_paid_ils -= converted_amount
            
            # حساب الرصيد الأساسي بالشيكل
            base_balance = Decimal(str(self.balance or 0))
            if self.currency == "ILS":
                base_balance_ils = base_balance
            else:
                try:
                    base_balance_ils = convert_amount(base_balance, self.currency, "ILS")
                except Exception:
                    base_balance_ils = base_balance
            
            return base_balance_ils - total_paid_ils
        except Exception:
            return Decimal("0.00")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "currency": self.currency,
            "balance": float(q(self.balance or 0)),
            "total_paid": float(q(self.total_paid or 0)),
            "net_balance": float(q(self.net_balance or 0)),
        }

    def __repr__(self):
        return f"<Supplier {self.name}>"
    
    def ensure_customer_link(self):
        """إنشاء أو ربط عميل تلقائياً"""
        if not self.customer_id and self.id:
            # البحث عن عميل موجود بنفس البيانات
            existing = Customer.query.filter(
                (Customer.phone == self.phone) if self.phone else False
            ).first()
            
            if existing:
                self.customer_id = existing.id
            else:
                # إنشاء عميل جديد بنفس الاسم
                customer = Customer(
                    name=self.name,  # نفس الاسم بدون إضافات
                    phone=self.phone or '0000000',
                    whatsapp=self.phone or '0000000',
                    email=self.email or f'supplier_{self.id}@system.local',
                    address=self.address,
                    currency=self.currency,
                    credit_limit=0,
                    notes=f"حساب مرتبط بالمورد #{self.id}"
                )
                db.session.add(customer)
                db.session.flush()
                self.customer_id = customer.id


# Event listener لإنشاء عميل تلقائياً للمورد الجديد
@event.listens_for(Supplier, "after_insert")  
def supplier_after_insert_create_customer(mapper, connection, target):
    """إنشاء عميل تلقائياً بعد إضافة مورد"""
    if not target.customer_id:
        from sqlalchemy import insert as sa_insert, select as sa_select, update as sa_update
        
        # البحث عن عميل موجود بالهاتف
        existing_customer_id = None
        if target.phone:
            result = connection.execute(
                sa_select(Customer.id).where(Customer.phone == target.phone)
            ).first()
            if result:
                existing_customer_id = result[0]
        
        if existing_customer_id:
            # ربط بالعميل الموجود
            connection.execute(
                sa_update(Supplier).where(Supplier.id == target.id).values(customer_id=existing_customer_id)
            )
            # تحديث اسم العميل
            connection.execute(
                sa_update(Customer).where(Customer.id == existing_customer_id).values(
                    name=sa_text(f"name || ' (مورد)'")
                )
            )
        else:
            # إنشاء عميل جديد
            result = connection.execute(
                sa_insert(Customer).values(
                    name=f"{target.name} (مورد)",
                    phone=target.phone or "0000000000",  # قيمة افتراضية إذا لم يكن هناك رقم
                    whatsapp=target.phone or "0000000000",
                    email=target.email or f"supplier_{target.id}@temp.local",
                    address=target.address,
                    currency=target.currency,
                    credit_limit=0,
                    notes=f"عميل مرتبط بالمورد #{target.id}",
                    created_at=datetime.now(timezone.utc)
                ).returning(Customer.id)
            )
            customer_id = result.scalar_one()
            
            # ربط المورد بالعميل
            connection.execute(
                sa_update(Supplier).where(Supplier.id == target.id).values(customer_id=customer_id)
            )


@event.listens_for(Supplier, "before_insert")
def _supplier_before_insert(_m, _c, t: Supplier):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()

@event.listens_for(Supplier, "before_update")
def _supplier_before_update(_m, _c, t: Supplier):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()


@event.listens_for(Supplier, "after_insert")
@event.listens_for(Supplier, "after_update")
def _supplier_opening_balance_gl(mapper, connection, target: "Supplier"):
    """
    إنشاء/تحديث GLBatch للرصيد الافتتاحي للمورد
    
    ⚡ محسّن: يفحص إذا تغير opening_balance فعلاً قبل إنشاء GL
    """
    try:
        # ⚡ تحسين: فحص التغيير فقط على update
        if mapper and connection:
            try:
                hist = inspect(target).attrs.get('opening_balance')
                if hist and hasattr(hist, 'history'):
                    if not hist.history.has_changes():
                        return  # لم يتغير opening_balance - لا داعي للقيد
            except:
                pass  # في حالة after_insert لن يكون هناك history
        
        opening_balance = float(getattr(target, 'opening_balance', 0) or 0)
        if opening_balance == 0:
            return
        
        # القيد المحاسبي للرصيد الافتتاحي:
        # موجب = له علينا: دائن AP، مدين رأس المال
        # سالب = عليه لنا: مدين AP، دائن رأس المال
        if opening_balance > 0:  # موجب = له علينا
            entries = [
                ("3000_EQUITY", abs(opening_balance), 0),  # مدين
                (GL_ACCOUNTS.get("AP", "2000_AP"), 0, abs(opening_balance)),  # دائن
            ]
        else:  # سالب = عليه لنا
            entries = [
                (GL_ACCOUNTS.get("AP", "2000_AP"), abs(opening_balance), 0),  # مدين
                ("3000_EQUITY", 0, abs(opening_balance)),  # دائن
            ]
        
        memo = f"رصيد افتتاحي - {target.name}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="SUPPLIER",
            source_id=target.id,
            purpose="OPENING_BALANCE",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=f"OB-SUP-{target.id}",
            entity_type="SUPPLIER",
            entity_id=target.id
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للرصيد الافتتاحي للمورد #{target.id}: {e}", file=sys.stderr)


class SupplierSettlement(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "supplier_settlements"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False, index=True)
    from_date = db.Column(db.DateTime, nullable=False)
    to_date = db.Column(db.DateTime, nullable=False)
    currency = db.Column(db.String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    status = db.Column(
        sa_str_enum(SupplierSettlementStatus, name="supplier_settlement_status"),
        default=SupplierSettlementStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    mode = db.Column(
        sa_str_enum(SupplierSettlementMode, name="supplier_settlement_mode"),
        default=SupplierSettlementMode.ON_RECEIPT.value,
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)
    total_gross = db.Column(db.Numeric(12, 2), default=0)
    total_due = db.Column(db.Numeric(12, 2), default=0)

    supplier = db.relationship("Supplier", backref="settlements")
    lines = db.relationship("SupplierSettlementLine", back_populates="settlement", cascade="all, delete-orphan")

    __table_args__ = ()

    @validates("status", "mode")
    def _v_str_enums(self, _, v):
        return getattr(v, "value", v)

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @hybrid_property
    def total_paid(self):
        ref = f"SupplierSettle:{self.code or ''}"
        if not self.code:
            return 0.0
        val = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.entity_type == PaymentEntityType.SUPPLIER.value,
                Payment.supplier_id == self.supplier_id,
                Payment.reference == ref,
            )
            .scalar()
            or 0
        )
        return float(q(val))

    @hybrid_property
    def remaining(self):
        return float(q(self.total_due or 0) - q(self.total_paid or 0))

    def ensure_code(self):
        if self.code:
            return
        prefix = datetime.now(timezone.utc).strftime("SS-%Y%m")
        cnt = db.session.query(func.count(SupplierSettlement.id)).filter(SupplierSettlement.code.like(f"{prefix}-%")).scalar() or 0
        self.code = f"{prefix}-{cnt + 1:04d}"

    def mark_confirmed(self):
        self.status = SupplierSettlementStatus.CONFIRMED.value


class SupplierSettlementLine(db.Model, TimestampMixin):
    __tablename__ = "supplier_settlement_lines"

    id = db.Column(db.Integer, primary_key=True)
    settlement_id = db.Column(db.Integer, db.ForeignKey("supplier_settlements.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = db.Column(db.String(30), nullable=False)
    source_id = db.Column(db.Integer, index=True)
    description = db.Column(db.String(255))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    quantity = db.Column(db.Numeric(12, 3))
    unit_price = db.Column(db.Numeric(12, 2))
    gross_amount = db.Column(db.Numeric(12, 2))
    needs_pricing = db.Column(db.Boolean, default=False, nullable=False, index=True)
    cost_source = db.Column(db.String(20))

    settlement = db.relationship("SupplierSettlement", back_populates="lines")
    product = db.relationship("Product")

    __table_args__ = ()


def _ex_dir_sign(direction: str) -> int:
    d = (getattr(direction, "value", direction) or "").upper()
    if d == "IN":
        return 1
    if d == "OUT":
        return -1
    if d == "ADJUSTMENT":
        return 1
    raise ValueError(f"Unknown exchange direction: {direction}")


class SupplierLoanSettlement(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "supplier_loan_settlements"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("product_supplier_loans.id", ondelete="CASCADE"), nullable=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    settled_price = db.Column(db.Numeric(12, 2), nullable=False)
    settlement_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text)

    loan = db.relationship("ProductSupplierLoan", back_populates="settlements")
    supplier = db.relationship("Supplier", back_populates="loan_settlements")
    payment = db.relationship("Payment", back_populates="loan_settlement", cascade="all, delete-orphan", passive_deletes=True, uselist=False)

    __table_args__ = (db.CheckConstraint("settled_price >= 0", name="chk_settlement_price_non_negative"),)

    @hybrid_property
    def has_payment(self) -> bool:
        return self.payment is not None

    @property
    def product(self):
        return getattr(self.loan, "product", None)

    def build_payment(
        self,
        method: "PaymentMethod" = None,
        status: "PaymentStatus" = None,
        direction: "PaymentDirection" = None,
        currency: str = None,
        reference: str = None,
        notes: str = None,
        created_by: int = None,
    ) -> "Payment":
        return Payment(
            total_amount=self.settled_price,
            payment_date=datetime.now(timezone.utc),
            method=method or PaymentMethod.BANK,
            status=status or PaymentStatus.PENDING,
            direction=direction or PaymentDirection.OUT,
            entity_type=PaymentEntityType.LOAN,
            currency=currency or (getattr(self.supplier, "currency", None) or "ILS"),
            supplier_id=getattr(self.supplier, "id", None),
            loan_settlement_id=self.id,
            reference=reference or f"Loan #{self.loan_id} settlement",
            notes=notes,
            created_by=created_by,
        )

    def __repr__(self):
        return f"<SupplierLoanSettlement Loan{self.loan_id} - {self.settled_price}>"


@event.listens_for(SupplierLoanSettlement, "after_insert")
def _sync_loan_on_settlement(_m, connection, target: "SupplierLoanSettlement"):
    if target.loan_id:
        connection.execute(
            update(ProductSupplierLoan)
            .where(ProductSupplierLoan.id == target.loan_id)
            .values(deferred_price=target.settled_price, is_settled=True)
        )


def _recompute_supplier_settlement_totals(connection, settlement_id: int):
    gross_sum = connection.execute(
        select(func.coalesce(func.sum(SupplierSettlementLine.gross_amount), 0)).where(SupplierSettlementLine.settlement_id == settlement_id)
    ).scalar_one() or 0
    connection.execute(
        update(SupplierSettlement).where(SupplierSettlement.id == settlement_id).values(total_gross=gross_sum, total_due=gross_sum)
    )


@event.listens_for(SupplierSettlement, "before_insert")
def _ss_before_insert(_m, _c, t: SupplierSettlement):
    t.currency = (t.currency or "ILS").upper()
    t.status = getattr(t.status, "value", t.status)
    t.mode = getattr(t.mode, "value", t.mode)
    if not t.code:
        prefix = datetime.now(timezone.utc).strftime("SS-%Y%m")
        cnt = db.session.query(func.count(SupplierSettlement.id)).filter(SupplierSettlement.code.like(f"{prefix}-%")).scalar() or 0
        t.code = f"{prefix}-{cnt + 1:04d}"

@event.listens_for(SupplierSettlement, "before_update")
def _ss_before_update(_m, connection, t: SupplierSettlement):
    t.currency = (t.currency or "ILS").upper()
    t.status = getattr(t.status, "value", t.status)
    t.mode = getattr(t.mode, "value", t.mode)
    if t.status == SupplierSettlementStatus.CONFIRMED.value:
        cnt_unpriced = (
            connection.execute(
                select(func.count(SupplierSettlementLine.id)).where(
                    SupplierSettlementLine.settlement_id == t.id, SupplierSettlementLine.needs_pricing.is_(True)
                )
            ).scalar_one()
            or 0
        )
        if int(cnt_unpriced) > 0:
            raise ValueError("لا يمكن تأكيد التسوية وفيها بنود بحاجة تسعير")
        dup_cnt = (
            connection.execute(
                select(func.count(SupplierSettlementLine.id))
                .select_from(
                    SupplierSettlementLine.__table__.join(SupplierSettlement.__table__, SupplierSettlementLine.settlement_id == SupplierSettlement.id)
                )
                .where(
                    SupplierSettlement.id != t.id,
                    SupplierSettlement.supplier_id == t.supplier_id,
                    SupplierSettlement.status == SupplierSettlementStatus.CONFIRMED.value,
                    SupplierSettlementLine.source_type.in_(select(SupplierSettlementLine.source_type).where(SupplierSettlementLine.settlement_id == t.id)),
                    SupplierSettlementLine.source_id.in_(select(SupplierSettlementLine.source_id).where(SupplierSettlementLine.settlement_id == t.id)),
                )
            ).scalar_one()
            or 0
        )
        if int(dup_cnt) > 0:
            raise ValueError("يوجد مصادر مستخدمة سابقًا في تسويات مؤكّدة لنفس المورد")

@event.listens_for(SupplierSettlement, "before_delete")
def _ss_before_delete(_m, _c, t: SupplierSettlement):
    if t.status == SupplierSettlementStatus.CONFIRMED.value:
        raise ValueError("لا يمكن حذف تسوية مؤكّدة")

@event.listens_for(SupplierSettlementLine, "before_insert")
@event.listens_for(SupplierSettlementLine, "before_update")
def _ssl_before_save(_m, connection, t: SupplierSettlementLine):
    if t.quantity is not None and float(t.quantity) < 0:
        raise ValueError("الكمية يجب أن تكون ≥ 0")
    if t.unit_price is not None and float(t.unit_price) < 0:
        raise ValueError("سعر الوحدة يجب أن يكون ≥ 0")
    if t.gross_amount is None:
        qv = Decimal(str(t.quantity or 0))
        uv = Decimal(str(t.unit_price or 0))
        t.gross_amount = q(qv * uv)
    if float(t.gross_amount or 0) < 0:
        raise ValueError("القيمة الإجمالية يجب أن تكون ≥ 0")

@event.listens_for(SupplierSettlementLine, "after_insert")
@event.listens_for(SupplierSettlementLine, "after_update")
@event.listens_for(SupplierSettlementLine, "after_delete")
def _ssl_touch_settlement(_m, connection, t: SupplierSettlementLine):
    if t.settlement_id:
        _recompute_supplier_settlement_totals(connection, int(t.settlement_id))

@event.listens_for(SupplierSettlementLine, "before_delete")
def _ssl_before_delete(_m, _c, t: SupplierSettlementLine):
    s = t.settlement
    if s and s.status == SupplierSettlementStatus.CONFIRMED.value:
        raise ValueError("لا يمكن حذف بنود من تسوية مؤكّدة")


def _ok(data=None, http=200, **extra):
    payload = {"success": True}
    if data is not None:
        payload.update(data if isinstance(data, dict) else {"data": data})
    payload.update(extra)
    return jsonify(payload), http

def _created(location: str = None, data=None):
    headers = {}
    payload = {"success": True}
    if location:
        headers["Location"] = location
        payload["location"] = location
    if data is not None:
        payload.update(data if isinstance(data, dict) else {"data": data})
    return jsonify(payload), 201, headers

def _err(code: str, message: str = "", http: int = 400, details=None):
    body = {"success": False, "code": code}
    if message:
        body["message"] = message
    if details:
        body["details"] = details
    return jsonify(body), http


class Partner(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "partners"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    contact_info = db.Column(db.String(200))
    identity_number = db.Column(db.String(100), unique=True)
    phone_number = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=True)
    address = db.Column(db.String(200))
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"))
    share_percentage = db.Column(db.Numeric(5, 2), default=0, nullable=False, server_default=sa_text("0"))
    currency = db.Column(db.String(10), default="ILS", nullable=False, server_default=sa_text("'ILS'"))
    opening_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"), comment="الرصيد الافتتاحي (موجب=له علينا، سالب=عليه لنا)")
    notes = db.Column(db.Text)
    
    # ربط تلقائي مع جدول العملاء
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True, nullable=True)
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    # العلاقات
    customer = db.relationship("Customer", foreign_keys=[customer_id], backref="partner_link")
    warehouses = db.relationship("Warehouse", back_populates="partner")
    payments = db.relationship("Payment", back_populates="partner")
    preorders = db.relationship("PreOrder", back_populates="partner")
    invoices = db.relationship("Invoice", back_populates="partner")
    shipment_partners = db.relationship("ShipmentPartner", back_populates="partner")
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])

    warehouse_shares = db.relationship("WarehousePartnerShare", back_populates="partner", cascade="all, delete-orphan", overlaps="shares,product_shares")
    shares = db.relationship("WarehousePartnerShare", back_populates="partner", cascade="all, delete-orphan", overlaps="warehouse_shares,product_shares")
    product_shares = db.relationship("ProductPartnerShare", back_populates="partner", cascade="all, delete-orphan", overlaps="shares,warehouse_shares")
    product_links = db.relationship("ProductPartner", back_populates="partner", cascade="all, delete-orphan")
    service_parts = db.relationship("ServicePart", back_populates="partner")
    service_tasks = db.relationship("ServiceTask", back_populates="partner")
    expenses = db.relationship("Expense", back_populates="partner")

    __table_args__ = ()

    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower() or None

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("share_percentage")
    def _v_share(self, _, v):
        if v is None:
            return 0
        fv = float(v)
        if fv < 0 or fv > 100:
            raise ValueError("share_percentage must be between 0 and 100")
        return v

    @validates("name", "contact_info", "address", "identity_number", "phone_number", "notes")
    def _v_strip(self, _, v):
        s = (v or "").strip()
        return s or None

    @hybrid_property
    def total_paid(self):
        val = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.partner_id == self.id,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.COMPLETED.value,
            )
            .scalar()
            or 0
        )
        return q(val)

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.partner_id == cls.id)
                & (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )

    @hybrid_property
    def balance_in_ils(self):
        """الرصيد بالشيكل - حساب دقيق مع تحويل العملات"""
        try:
            # حساب المدفوعات بالشيكل
            payments = db.session.query(Payment).filter(
                Payment.partner_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value
            ).all()

            total_paid_ils = Decimal("0.00")
            for payment in payments:
                amount = Decimal(str(payment.total_amount or 0))
                currency = payment.currency or "ILS"
                direction = payment.direction

                # تحويل للشيكل باستخدام الأسعار الحقيقية
                if currency == "ILS":
                    converted_amount = amount
                else:
                    try:
                        # استخدام الأسعار اليدوية فقط لتجنب مشاكل قاعدة البيانات
                        converted_amount = convert_amount(amount, currency, "ILS", payment.payment_date)
                    except Exception as e:
                        # تسجيل الخطأ - لا نستخدم المبلغ الأصلي لأنه بعملة مختلفة
                        try:
                            from flask import current_app
                            current_app.logger.error(f"❌ خطأ في تحويل العملة لحساب رصيد الشريك #{self.id}: {str(e)}")
                        except:
                            pass
                        # تجاهل هذا المبلغ من الحساب
                        continue

                # تطبيق اتجاه الدفع
                if direction == PaymentDirection.OUT.value:
                    total_paid_ils += converted_amount
                else:
                    total_paid_ils -= converted_amount

            # حساب الرصيد الأساسي بالشيكل
            base_balance = Decimal(str(self.balance or 0))
            if self.currency == "ILS":
                base_balance_ils = base_balance
            else:
                try:
                    base_balance_ils = convert_amount(base_balance, self.currency, "ILS")
                except Exception:
                    base_balance_ils = base_balance

            return base_balance_ils - total_paid_ils
        except Exception:
            return Decimal("0.00")

    @hybrid_property
    def net_balance(self):
        return q(self.balance or 0) - q(self.total_paid or 0)

    @net_balance.expression
    def net_balance(cls):
        paid_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.partner_id == cls.id)
                & (Payment.direction == PaymentDirection.OUT.value)
                & (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )
        return cls.balance - paid_subq

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "currency": self.currency,
            "balance": float(q(self.balance or 0)),
            "total_paid": float(q(self.total_paid or 0)),
            "net_balance": float(q(self.net_balance or 0)),
        }

    def __repr__(self):
        return f"<Partner {self.name}>"
    
    def ensure_customer_link(self):
        """إنشاء أو ربط عميل تلقائياً"""
        if not self.customer_id and self.id:
            # البحث عن عميل موجود بنفس البيانات
            existing = Customer.query.filter(
                (Customer.phone == self.phone_number) if self.phone_number else False
            ).first()
            
            if existing:
                self.customer_id = existing.id
            else:
                # إنشاء عميل جديد بنفس الاسم
                customer = Customer(
                    name=self.name,  # نفس الاسم بدون إضافات
                    phone=self.phone_number or '0000000',
                    whatsapp=self.phone_number or '0000000',
                    email=self.email or f'partner_{self.id}@system.local',
                    address=self.address,
                    currency=self.currency,
                    credit_limit=0,
                    notes=f"حساب مرتبط بالشريك #{self.id}"
                )
                db.session.add(customer)
                db.session.flush()
                self.customer_id = customer.id


# Event listener لإنشاء عميل تلقائياً للشريك الجديد
@event.listens_for(Partner, "after_insert")
def partner_after_insert_create_customer(mapper, connection, target):
    """إنشاء عميل تلقائياً بعد إضافة شريك"""
    if not target.customer_id:
        from sqlalchemy import insert as sa_insert, select as sa_select, update as sa_update
        
        # البحث عن عميل موجود بنفس رقم الهاتف
        existing_customer_id = None
        if target.phone_number:
            result = connection.execute(
                sa_select(Customer.id).where(Customer.phone == target.phone_number)
            ).first()
            if result:
                existing_customer_id = result[0]
        
        if existing_customer_id:
            # ربط بالعميل الموجود (بدون تغيير اسمه)
            connection.execute(
                sa_update(Partner).where(Partner.id == target.id).values(customer_id=existing_customer_id)
            )
        else:
            # إنشاء عميل جديد بنفس الاسم
            result = connection.execute(
                sa_insert(Customer).values(
                    name=target.name,  # نفس الاسم بدون إضافة
                    phone=target.phone_number or '0000000',
                    whatsapp=target.phone_number or '0000000',
                    email=target.email or f'partner_{target.id}@system.local',
                    address=target.address,
                    currency=target.currency,
                    credit_limit=0,
                    notes=f"حساب مرتبط بالشريك #{target.id}",
                    created_at=datetime.now(timezone.utc),
                    is_active=True
                ).returning(Customer.id)
            )
            customer_id = result.scalar_one()
            
            # ربط الشريك بالعميل
            connection.execute(
                sa_update(Partner).where(Partner.id == target.id).values(customer_id=customer_id)
            )


# ==========================================
@event.listens_for(Partner, "before_insert")
def _partner_before_insert(_m, _c, t: Partner):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()
    t.name = (t.name or "").strip()

@event.listens_for(Partner, "before_update")
def _partner_before_update(_m, _c, t: Partner):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()
    t.name = (t.name or "").strip()


@event.listens_for(Partner, "after_insert")
@event.listens_for(Partner, "after_update")
def _partner_opening_balance_gl(mapper, connection, target: "Partner"):
    """
    إنشاء/تحديث GLBatch للرصيد الافتتاحي للشريك
    
    ⚡ محسّن: يفحص إذا تغير opening_balance فعلاً قبل إنشاء GL
    """
    try:
        # ⚡ تحسين: فحص التغيير فقط على update
        if mapper and connection:
            try:
                hist = inspect(target).attrs.get('opening_balance')
                if hist and hasattr(hist, 'history'):
                    if not hist.history.has_changes():
                        return  # لم يتغير opening_balance - لا داعي للقيد
            except:
                pass  # في حالة after_insert لن يكون هناك history
        
        opening_balance = float(getattr(target, 'opening_balance', 0) or 0)
        if opening_balance == 0:
            return
        
        # القيد المحاسبي للرصيد الافتتاحي:
        # موجب = له علينا: دائن AP، مدين رأس المال
        # سالب = عليه لنا: مدين AP، دائن رأس المال
        if opening_balance > 0:  # موجب = له علينا
            entries = [
                ("3000_EQUITY", abs(opening_balance), 0),  # مدين
                (GL_ACCOUNTS.get("AP", "2000_AP"), 0, abs(opening_balance)),  # دائن
            ]
        else:  # سالب = عليه لنا
            entries = [
                (GL_ACCOUNTS.get("AP", "2000_AP"), abs(opening_balance), 0),  # مدين
                ("3000_EQUITY", 0, abs(opening_balance)),  # دائن
            ]
        
        memo = f"رصيد افتتاحي - {target.name}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="PARTNER",
            source_id=target.id,
            purpose="OPENING_BALANCE",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=f"OB-PARTNER-{target.id}",
            entity_type="PARTNER",
            entity_id=target.id
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للرصيد الافتتاحي للشريك #{target.id}: {e}", file=sys.stderr)


def update_partner_balance(partner_id: int, connection=None):
    """
    تحديث رصيد الشريك تلقائياً بناءً على جميع المعاملات
    """
    from datetime import datetime
    from sqlalchemy import text as sa_text
    
    # استخدام connection إذا كان متاحاً (داخل event listener)
    # وإلا استخدام db.session
    if connection is None:
        connection = db.session.connection()
    
    # حساب الرصيد من جميع المعاملات
    # هذا استعلام SQL مباشر لتجنب مشاكل الـ circular imports
    query = sa_text("""
        WITH partner_data AS (
            SELECT :partner_id as pid
        ),
        -- حقوق الشريك (نصيبه من المبيعات)
        sales_share AS (
            SELECT COALESCE(SUM(
                sl.quantity * sl.unit_price * 
                COALESCE(pp.share_percent, wps.share_percentage, 0) / 100
            ), 0) as total
            FROM sales s
            JOIN sale_lines sl ON sl.sale_id = s.id
            JOIN products p ON p.id = sl.product_id
            LEFT JOIN product_partners pp ON pp.product_id = p.id AND pp.partner_id = :partner_id
            LEFT JOIN warehouse_partner_shares wps ON wps.product_id = p.id AND wps.partner_id = :partner_id
            WHERE s.status = 'CONFIRMED'
            AND (pp.partner_id IS NOT NULL OR wps.partner_id IS NOT NULL)
        ),
        -- التزامات الشريك (مبيعات له كعميل)
        sales_to_partner AS (
            SELECT COALESCE(SUM(s.total_amount), 0) as total
            FROM sales s
            JOIN partners par ON par.customer_id = s.customer_id
            WHERE par.id = :partner_id
            AND s.status = 'CONFIRMED'
        ),
        -- الدفعات الواردة من الشريك
        payments_in AS (
            SELECT COALESCE(SUM(p.total_amount), 0) as total
            FROM payments p
            LEFT JOIN sales s ON s.id = p.sale_id
            LEFT JOIN partners par ON par.customer_id = s.customer_id
            WHERE p.status = 'COMPLETED'
            AND p.direction = 'IN'
            AND (
                p.partner_id = :partner_id
                OR p.customer_id = (SELECT customer_id FROM partners WHERE id = :partner_id)
                OR par.id = :partner_id
            )
        ),
        -- الدفعات الصادرة للشريك
        payments_out AS (
            SELECT COALESCE(SUM(p.total_amount), 0) as total
            FROM payments p
            WHERE p.status = 'COMPLETED'
            AND p.direction = 'OUT'
            AND p.partner_id = :partner_id
        ),
        -- نصيب الشريك من المخزون (ProductPartner)
        inventory_share AS (
            SELECT COALESCE(SUM(pp.share_amount), 0) as total
            FROM product_partners pp
            WHERE pp.partner_id = :partner_id
        )
        SELECT 
            -- ✅ الحقوق: نسبة من القطع (مباعة وغير مباعة)
            (SELECT total FROM sales_share) + 
            (SELECT total FROM inventory_share) - 
            -- ❌ الالتزامات: ما لنا عليهم
            (SELECT total FROM sales_to_partner) - 
            -- ❌ الدفعات الصادرة: ما دفعناه لهم (نخصمها من حقوقهم)
            (SELECT total FROM payments_out) + 
            -- ✅ الدفعات الواردة: ما دفعوه لنا (نخصمها من التزاماتهم)
            (SELECT total FROM payments_in) + 
            COALESCE((SELECT opening_balance FROM partners WHERE id = :partner_id), 0) as balance
    """)
    
    result = connection.execute(query, {"partner_id": partner_id}).fetchone()
    balance = float(result[0] if result else 0)
    
    # تحديث رصيد الشريك
    update_query = sa_text("UPDATE partners SET balance = :balance WHERE id = :partner_id")
    connection.execute(update_query, {"balance": balance, "partner_id": partner_id})
    
    return balance

def update_supplier_balance(supplier_id: int, connection=None):
    """
    تحديث رصيد المورد تلقائياً بناءً على جميع المعاملات
    """
    from sqlalchemy import text as sa_text
    
    if connection is None:
        connection = db.session.connection()
    
    # حساب الرصيد من جميع المعاملات
    query = sa_text("""
        WITH supplier_data AS (
            SELECT :supplier_id as sid
        ),
        -- حقوق المورد (قيمة القطع في مستودع التبادل)
        exchange_items AS (
            SELECT COALESCE(SUM(et.quantity * et.unit_cost), 0) as total
            FROM exchange_transactions et
            WHERE et.supplier_id = :supplier_id
            AND et.direction IN ('IN', 'PURCHASE', 'CONSIGN_IN')
        ),
        -- التزامات المورد (مبيعات له كعميل)
        sales_to_supplier AS (
            SELECT COALESCE(SUM(s.total_amount), 0) as total
            FROM sales s
            JOIN suppliers sup ON sup.customer_id = s.customer_id
            WHERE sup.id = :supplier_id
            AND s.status = 'CONFIRMED'
        ),
        -- الدفعات الواردة
        payments_in AS (
            SELECT COALESCE(SUM(p.total_amount), 0) as total
            FROM payments p
            LEFT JOIN sales s ON s.id = p.sale_id
            LEFT JOIN suppliers sup ON sup.customer_id = s.customer_id
            WHERE p.status = 'COMPLETED'
            AND p.direction = 'IN'
            AND (
                p.supplier_id = :supplier_id
                OR p.customer_id = (SELECT customer_id FROM suppliers WHERE id = :supplier_id)
                OR sup.id = :supplier_id
            )
        ),
        -- الدفعات الصادرة
        payments_out AS (
            SELECT COALESCE(SUM(p.total_amount), 0) as total
            FROM payments p
            WHERE p.status = 'COMPLETED'
            AND p.direction = 'OUT'
            AND p.supplier_id = :supplier_id
        ),
        -- المرتجعات
        returns_out AS (
            SELECT COALESCE(SUM(et.quantity * et.unit_cost), 0) as total
            FROM exchange_transactions et
            WHERE et.supplier_id = :supplier_id
            AND et.direction IN ('OUT', 'RETURN')
        ),
        -- الحجوزات المسبقة للمورد (إذا كان عميلاً)
        preorders_to_supplier AS (
            SELECT COALESCE(SUM(p.price * po.quantity * (1 + COALESCE(po.tax_rate, 0) / 100.0)), 0) as total
            FROM preorders po
            JOIN products p ON p.id = po.product_id
            JOIN suppliers sup ON sup.customer_id = po.customer_id
            WHERE sup.id = :supplier_id
            AND po.status IN ('CONFIRMED', 'COMPLETED', 'DELIVERED')
        )
        SELECT 
            -- ✅ الحقوق: قطع التوريد
            (SELECT total FROM exchange_items) - 
            -- ❌ الالتزامات: المبيعات + الحجوزات + المرتجعات
            (SELECT total FROM sales_to_supplier) - 
            (SELECT total FROM preorders_to_supplier) - 
            (SELECT total FROM returns_out) - 
            -- ❌ الدفعات الصادرة: ما دفعناه لهم (نخصمها من حقوقهم)
            (SELECT total FROM payments_out) + 
            -- ✅ الدفعات الواردة: ما دفعوه لنا (نخصمها من التزاماتهم)
            (SELECT total FROM payments_in) + 
            COALESCE((SELECT opening_balance FROM suppliers WHERE id = :supplier_id), 0) as balance
    """)
    
    result = connection.execute(query, {"supplier_id": supplier_id}).fetchone()
    balance = float(result[0] if result else 0)
    
    # تحديث رصيد المورد
    update_query = sa_text("UPDATE suppliers SET balance = :balance WHERE id = :supplier_id")
    connection.execute(update_query, {"balance": balance, "supplier_id": supplier_id})
    
    return balance


class PartnerSettlement(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "partner_settlements"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey("partners.id"), nullable=False, index=True)
    from_date = db.Column(db.DateTime, nullable=False, index=True)
    to_date = db.Column(db.DateTime, nullable=False, index=True)
    currency = db.Column(db.String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    status = db.Column(sa_str_enum(PartnerSettlementStatus, name="partner_settlement_status"), default=PartnerSettlementStatus.DRAFT.value, nullable=False, index=True)
    notes = db.Column(db.Text)
    total_gross = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_share = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_costs = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_due = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    partner = db.relationship("Partner", backref="settlements")
    lines = db.relationship("PartnerSettlementLine", back_populates="settlement", cascade="all, delete-orphan")

    __table_args__ = ()

    @hybrid_property
    def total_paid(self):
        ref = f"PartnerSettle:{self.code or ''}"
        if not self.code:
            return 0.0
        val = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.partner_id == self.partner_id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.entity_type == PaymentEntityType.PARTNER.value,
                Payment.reference == ref,
            )
            .scalar()
            or 0
        )
        return float(q(val))

    @hybrid_property
    def remaining(self):
        return float(q(self.total_due or 0) - q(self.total_paid or 0))

    def ensure_code(self):
        if self.code:
            return
        prefix = datetime.now(timezone.utc).strftime("PS-%Y%m")
        cnt = db.session.query(func.count(PartnerSettlement.id)).filter(PartnerSettlement.code.like(f"{prefix}-%")).scalar() or 0
        self.code = f"{prefix}-{cnt + 1:04d}"

    def mark_confirmed(self):
        self.status = PartnerSettlementStatus.CONFIRMED.value


@event.listens_for(PartnerSettlement, "before_insert")
def _ps_before_insert(_m, _c, t: PartnerSettlement):
    t.currency = (t.currency or "ILS").upper()
    if not t.code:
        t.ensure_code()
    if t.from_date and t.to_date and t.to_date < t.from_date:
        t.from_date, t.to_date = t.to_date, t.from_date

@event.listens_for(PartnerSettlement, "before_update")
def _ps_before_update(_m, _c, t: PartnerSettlement):
    t.currency = (t.currency or "ILS").upper()
    if not t.code:
        t.ensure_code()
    if t.from_date and t.to_date and t.to_date < t.from_date:
        t.from_date, t.to_date = t.to_date, t.from_date


class PartnerSettlementLine(db.Model, TimestampMixin):
    __tablename__ = "partner_settlement_lines"

    id = db.Column(db.Integer, primary_key=True)
    settlement_id = db.Column(db.Integer, db.ForeignKey("partner_settlements.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = db.Column(db.String(30), nullable=False, index=True)
    source_id = db.Column(db.Integer, index=True)
    description = db.Column(db.String(255))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))
    quantity = db.Column(db.Numeric(12, 3))
    unit_price = db.Column(db.Numeric(12, 2))
    gross_amount = db.Column(db.Numeric(12, 2))
    share_percent = db.Column(db.Numeric(6, 3))
    share_amount = db.Column(db.Numeric(12, 2))

    settlement = db.relationship("PartnerSettlement", back_populates="lines")
    product = db.relationship("Product")
    warehouse = db.relationship("Warehouse")

    __table_args__ = ()


def _find_partner_share_percentage(partner_id: int, product_id: int | None, warehouse_id: int | None) -> float:
    pct = 0.0
    if product_id:
        row2 = (
            db.session.query(ProductPartner.share_percent)
            .filter(ProductPartner.partner_id == partner_id, ProductPartner.product_id == product_id)
            .first()
        )
        if row2:
            return float(row2[0] or 0)
        row = (
            db.session.query(WarehousePartnerShare.share_percentage)
            .filter(WarehousePartnerShare.partner_id == partner_id, WarehousePartnerShare.product_id == product_id)
            .first()
        )
        if row:
            return float(row[0] or 0)
    if warehouse_id:
        row3 = (
            db.session.query(WarehousePartnerShare.share_percentage)
            .filter(
                WarehousePartnerShare.partner_id == partner_id,
                WarehousePartnerShare.warehouse_id == warehouse_id,
                WarehousePartnerShare.product_id.is_(None),
            )
            .first()
        )
        if row3:
            return float(row3[0] or 0)
    return pct


def build_partner_settlement_draft(partner_id: int, date_from: datetime, date_to: datetime, *, currency: str = "ILS") -> PartnerSettlement:
    ps = PartnerSettlement(partner_id=partner_id, from_date=date_from, to_date=date_to, currency=(currency or "ILS").upper(), status=PartnerSettlementStatus.DRAFT.value)
    total_gross = Decimal("0.00")
    total_share = Decimal("0.00")

    parts_q = (
        db.session.query(ServicePart)
        .join(ServiceRequest, ServiceRequest.id == ServicePart.service_id)
        .filter(
            ServiceRequest.received_at >= date_from,
            ServiceRequest.received_at <= date_to,
            or_(ServicePart.partner_id == partner_id, ServicePart.partner_id.is_(None)),
        )
    )
    for sp in parts_q:
        base = q(sp.line_total)
        sp_share_pct = float(sp.share_percentage or 0)
        if sp.partner_id != partner_id:
            sp_share_pct = _find_partner_share_percentage(partner_id, sp.part_id, sp.warehouse_id)
        pct_dec = Decimal(str(sp_share_pct)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        share_amt = q(base * Decimal(str(sp_share_pct / 100.0))) if sp_share_pct else Decimal("0.00")
        if share_amt > 0:
            ps.lines.append(
                PartnerSettlementLine(
                    source_type="SERVICE_PART",
                    source_id=sp.id,
                    description=f"ServicePart #{sp.id}",
                    product_id=sp.part_id,
                    warehouse_id=sp.warehouse_id,
                    quantity=sp.quantity,
                    unit_price=sp.unit_price,
                    gross_amount=base,
                    share_percent=pct_dec,
                    share_amount=share_amt,
                )
            )
            total_gross += q(base)
            total_share += q(share_amt)

    sl_q = db.session.query(SaleLine).join(Sale, Sale.id == SaleLine.sale_id).filter(Sale.sale_date >= date_from, Sale.sale_date <= date_to)
    for sl in sl_q:
        base = q(getattr(sl, "line_total", (Decimal(str(sl.quantity or 0)) * Decimal(str(sl.unit_price or 0)))))
        pct = float(getattr(sl, "share_percentage", 0) or 0)
        if not pct:
            pct = _find_partner_share_percentage(partner_id, getattr(sl, "product_id", None), getattr(sl, "warehouse_id", None))
        pct_dec = Decimal(str(pct)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        share_amt = q(base * Decimal(str(pct / 100.0))) if pct else Decimal("0.00")
        if share_amt > 0:
            ps.lines.append(
                PartnerSettlementLine(
                    source_type="SALE_LINE",
                    source_id=sl.id,
                    description=f"SaleLine #{sl.id}",
                    product_id=getattr(sl, "product_id", None),
                    warehouse_id=getattr(sl, "warehouse_id", None),
                    quantity=getattr(sl, "quantity", None),
                    unit_price=getattr(sl, "unit_price", None),
                    gross_amount=base,
                    share_percent=pct_dec,
                    share_amount=share_amt,
                )
            )
            total_gross += q(base)
            total_share += q(share_amt)

    ps.total_gross = q(total_gross)
    ps.total_share = q(total_share)
    ps.total_costs = q(0)
    ps.total_due = q(total_share)
    ps.ensure_code()
    return ps

class Employee(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    position = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), unique=True, index=True, nullable=True)
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    currency = db.Column(db.String(10), default="ILS", nullable=False, server_default=sa_text("'ILS'"))

    expenses = relationship("Expense", back_populates="employee", cascade="all, delete-orphan")

    __table_args__ = ()

    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower() or None

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("name", "position", "phone", "bank_name", "account_number", "notes")
    def _v_strip(self, _, v):
        s = (v or "").strip()
        return s or None

    @hybrid_property
    def total_expenses(self):
        return float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.employee_id == self.id).scalar())

    @total_expenses.expression
    def total_expenses(cls):
        return select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.employee_id == cls.id).scalar_subquery()

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .join(Expense, Payment.expense_id == Expense.id)
            .filter(
                Expense.employee_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUT.value,
            )
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .select_from(Payment.__table__.join(Expense, Payment.expense_id == Expense.id))
            .where(
                (Expense.employee_id == cls.id)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (Payment.direction == PaymentDirection.OUT.value)
            )
            .scalar_subquery()
        )

    @hybrid_property
    def balance(self):
        return self.total_expenses - self.total_paid

    @balance.expression
    def balance(cls):
        return cls.total_expenses - cls.total_paid

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "position": self.position,
            "phone": self.phone,
            "currency": self.currency,
            "total_expenses": self.total_expenses,
            "total_paid": self.total_paid,
            "balance": self.balance,
        }

    def __repr__(self):
        return f"<Employee {self.name}>"

class EquipmentType(db.Model, TimestampMixin):
    __tablename__ = 'equipment_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    model_number = db.Column(db.String(100))
    chassis_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    category = db.Column(db.String(50))
    products = db.relationship('Product', back_populates='vehicle_type')
    service_requests = db.relationship('ServiceRequest', back_populates='vehicle_type')
    def __repr__(self): return f"<EquipmentType {self.name}>"

class ProductCategory(db.Model, TimestampMixin):
    __tablename__ = 'product_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('product_categories.id'))
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    parent = db.relationship('ProductCategory', remote_side=[id], backref='subcategories')
    products = db.relationship('Product', back_populates='category')
    __table_args__ = ()
    @validates("name", "description", "image_url")
    def _v_strip(self, _, v):
        return (v or "").strip() or None
    def __repr__(self): return f"<ProductCategory {self.name}>"

class Product(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(50))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    part_number = Column(String(100), index=True)
    brand = Column(String(100), index=True)
    commercial_name = Column(String(100))
    chassis_number = Column(String(100))
    serial_no = Column(String(100))
    barcode = Column(String(100))
    unit = Column(String(50))
    category_name = Column(String(100))
    purchase_price = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    selling_price = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    cost_before_shipping = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    cost_after_shipping = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    unit_price_before_tax = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    price = Column(Numeric(12, 2), nullable=False, default=0, server_default=sa_text("0"))
    min_price = Column(Numeric(12, 2))
    max_price = Column(Numeric(12, 2))
    tax_rate = Column(Numeric(5, 2), nullable=False, default=0, server_default=sa_text("0"))
    min_qty = Column(Integer, nullable=False, default=0, server_default=sa_text("0"))
    reorder_point = Column(Integer)
    image = Column(String(255))
    notes = Column(Text)
    condition = Column(sa_str_enum(ProductCondition, name="product_condition"), default=ProductCondition.NEW.value, nullable=False, server_default=sa_text("'NEW'"))
    origin_country = Column(String(50))
    warranty_period = Column(Integer)
    weight = Column(Numeric(10, 2))
    dimensions = Column(String(50))
    is_active = Column(Boolean, default=True, nullable=False, server_default=sa_text("1"))
    is_digital = Column(Boolean, default=False, nullable=False, server_default=sa_text("0"))
    is_exchange = Column(Boolean, default=False, nullable=False, server_default=sa_text("0"))
    is_published = Column(Boolean, default=True, nullable=False, server_default=sa_text("1"))
    vehicle_type_id = Column(Integer, ForeignKey("equipment_types.id"))
    category_id = Column(Integer, ForeignKey("product_categories.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    supplier_international_id = Column(Integer, ForeignKey("suppliers.id"))
    supplier_local_id = Column(Integer, ForeignKey("suppliers.id"))
    online_name = Column(String(255))
    online_price = Column(Numeric(12, 2), default=0, server_default=sa_text("0"))
    online_image = Column(String(255))
    
    # ✅ حقول العملة وسعر الصرف
    currency = Column(String(10), default='ILS', nullable=False, server_default=sa_text("'ILS'"))
    fx_rate_used = Column(Numeric(10, 6))
    fx_rate_source = Column(String(20))
    fx_rate_timestamp = Column(DateTime)
    fx_base_currency = Column(String(10))
    fx_quote_currency = Column(String(10))
    
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_price_ge_0"),
        CheckConstraint("purchase_price >= 0", name="ck_product_purchase_ge_0"),
        CheckConstraint("selling_price >= 0", name="ck_product_selling_ge_0"),
        CheckConstraint("cost_before_shipping >= 0", name="ck_product_cost_before_ge_0"),
        CheckConstraint("cost_after_shipping >= 0", name="ck_product_cost_after_ge_0"),
        CheckConstraint("unit_price_before_tax >= 0", name="ck_product_unit_before_tax_ge_0"),
        CheckConstraint("min_price IS NULL OR min_price >= 0", name="ck_product_min_price_ge_0"),
        CheckConstraint("max_price IS NULL OR max_price >= 0", name="ck_product_max_price_ge_0"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="ck_product_tax_rate_0_100"),
        CheckConstraint("min_qty >= 0", name="ck_product_min_qty_ge_0"),
        CheckConstraint("reorder_point IS NULL OR reorder_point >= 0", name="ck_product_reorder_ge_0"),
        CheckConstraint("weight IS NULL OR weight >= 0", name="ck_product_weight_ge_0"),
        CheckConstraint("online_price IS NULL OR online_price >= 0", name="ck_product_online_price_ge_0"),
        Index("ix_products_brand_part", "brand", "part_number"),
        Index("uq_products_sku_ci", func.lower(sku), unique=True, postgresql_where=sku.isnot(None)),
        Index("uq_products_barcode", barcode, unique=True, postgresql_where=barcode.isnot(None)),
        Index("uq_products_serial_ci", func.lower(serial_no), unique=True, postgresql_where=serial_no.isnot(None)),
        Index("ix_products_category_active", "category_id", "is_active"),
    )
    category = relationship("ProductCategory", back_populates="products")
    vehicle_type = relationship("EquipmentType", back_populates="products")
    supplier_general = relationship("Supplier", foreign_keys=[supplier_id])
    supplier_international = relationship("Supplier", foreign_keys=[supplier_international_id])
    supplier_local = relationship("Supplier", foreign_keys=[supplier_local_id])
    partners = relationship("ProductPartner", back_populates="product")
    partner_shares = relationship("ProductPartnerShare", back_populates="product")
    supplier_loans = relationship("ProductSupplierLoan", back_populates="product")
    transfers = relationship("Transfer", back_populates="product")
    preorders = relationship("PreOrder", back_populates="product")
    shipment_items = relationship("ShipmentItem", back_populates="product")
    exchange_transactions = relationship("ExchangeTransaction", back_populates="product")
    sale_lines = relationship("SaleLine", back_populates="product")
    service_parts = relationship("ServicePart", back_populates="part")
    online_cart_items = relationship("OnlineCartItem", back_populates="product")
    online_preorder_items = relationship("OnlinePreOrderItem", back_populates="product")
    stock_levels = relationship("StockLevel", back_populates="product")
    stock_adjustment_items = relationship("StockAdjustmentItem", back_populates="product", cascade='all, delete-orphan')
    def __init__(self, **kwargs):
        self.category_name = (kwargs.pop("category", None) or None)
        self.unit = (kwargs.pop("unit", None) or None)
        self.purchase_price = kwargs.pop("purchase_price", 0)
        self.selling_price = kwargs.pop("selling_price", kwargs.get("price", 0))
        self.notes = kwargs.pop("notes", None)
        super().__init__(**kwargs)
    @validates('currency')
    def _v_currency(self, _, v):
        return ensure_currency(v or 'ILS')
    @validates("sku", "serial_no", "barcode")
    def _v_strip_norm_ids(self, key, v):
        if v is None: return None
        v = str(v).strip()
        if key in ("sku", "serial_no"): v = v.upper()
        if key == "barcode": v = normalize_barcode(v) or None
        return v
    @validates("name","brand","part_number","commercial_name","chassis_number","category_name","origin_country","dimensions","unit","online_name","online_image","image","description","notes")
    def _v_strip_texts(self, key, v):
        if v is None: return None
        v = str(v).strip()
        return v or None
    @validates("purchase_price","selling_price","cost_before_shipping","cost_after_shipping","unit_price_before_tax","price","min_price","max_price","tax_rate","weight","online_price")
    def _v_money_numeric(self, key, v):
        if v is None or v == "":
            return 0 if key in ("price","purchase_price","selling_price","cost_before_shipping","cost_after_shipping","unit_price_before_tax") else None
        if isinstance(v, str): v = v.replace("$","").replace(",","").strip()
        d = Decimal(str(v))
        if key == "tax_rate" and (d < 0 or d > Decimal("100")): raise ValueError("tax_rate must be between 0 and 100")
        if d < 0: raise ValueError(f"{key} must be >= 0")
        return d
    @validates("min_qty","reorder_point","warranty_period")
    def _v_int_nonneg(self, key, v):
        if v in (None,""): return None if key == "reorder_point" else 0
        i = int(v)
        if i < 0: raise ValueError(f"{key} must be >= 0")
        return i
    @hybrid_property
    def total_partner_percentage(self):
        return sum(float(share.share_percentage or 0) for share in (self.partner_shares or []))
    @hybrid_property
    def total_partner_amount(self):
        return sum(float(share.share_amount or 0) for share in (self.partner_shares or []))
    def quantity_in_warehouse(self, warehouse_id):
        level = next((s for s in (self.stock_levels or []) if s.warehouse_id == warehouse_id), None)
        return level.quantity if level else 0
    @hybrid_property
    def condition_display(self):
        m = {ProductCondition.NEW.value:"جديد", ProductCondition.USED.value:"مستعمل", ProductCondition.REFURBISHED.value:"مجدّد"}
        v = getattr(self.condition,"value",self.condition)
        return m.get(v, v)
    @hybrid_property
    def effective_name(self):
        return self.online_name or self.name
    @hybrid_property
    def effective_price(self):
        return self.online_price if self.online_price is not None else self.price
    @hybrid_property
    def effective_image(self):
        return self.online_image or self.image
    def __repr__(self): return f"<Product {self.name}>"

@event.listens_for(Product, "before_insert")
@event.listens_for(Product, "before_update")
def _product_before_save(mapper, connection, t: Product):
    from decimal import Decimal as _D
    if (t.selling_price or 0) == 0 and (t.price or 0) > 0: t.selling_price = t.price
    if (t.price or 0) == 0 and (t.selling_price or 0) > 0: t.price = t.selling_price
    if t.min_price is not None and t.max_price is not None:
        if _D(str(t.min_price)) > _D(str(t.max_price)):
            t.min_price, t.max_price = t.max_price, t.min_price
        mn = _D(str(t.min_price)); mx = _D(str(t.max_price))
        if t.price is not None:
            p = _D(str(t.price))
            if p < mn: t.price = mn
            elif p > mx: t.price = mx
    try:
        from flask import current_app
        if not t.image:
            t.image = current_app.config.get("DEFAULT_PRODUCT_IMAGE") or t.image
    except Exception:
        pass
    t.is_active = bool(t.is_active)
    t.is_digital = bool(t.is_digital)
    t.is_exchange = bool(t.is_exchange)
    t.is_published = bool(t.is_published)

class Warehouse(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'warehouses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    warehouse_type = db.Column(sa_str_enum(WarehouseType, name='warehouse_type'), default=WarehouseType.MAIN.value, nullable=False, index=True, server_default=sa_text("'MAIN'"))
    location = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default=sa_text("1"))
    parent_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percent = db.Column(db.Numeric(5, 2), default=0, server_default=sa_text("0"))
    capacity = db.Column(db.Integer)
    current_occupancy = db.Column(db.Integer, default=0, server_default=sa_text("0"))
    notes = db.Column(db.Text)
    online_slug = db.Column(db.String(150), unique=True)
    online_is_default = db.Column(db.Boolean, nullable=False, default=False, server_default=sa_text("0"))
    parent = db.relationship('Warehouse', remote_side=[id], backref='children')
    supplier = db.relationship('Supplier', back_populates='warehouses')
    partner = db.relationship('Partner', back_populates='warehouses')
    stock_levels = db.relationship('StockLevel', back_populates='warehouse')
    transfers_source = db.relationship('Transfer', back_populates='source_warehouse', foreign_keys='Transfer.source_id')
    transfers_destination = db.relationship('Transfer', back_populates='destination_warehouse', foreign_keys='Transfer.destination_id')
    sale_lines = db.relationship('SaleLine', back_populates='warehouse')
    service_parts = db.relationship('ServicePart', back_populates='warehouse')
    exchange_transactions = db.relationship('ExchangeTransaction', back_populates='warehouse')
    shipment_items = db.relationship('ShipmentItem', back_populates='warehouse')
    shipments_received = db.relationship('Shipment', back_populates='destination_warehouse', foreign_keys='Shipment.destination_id')
    preorders = db.relationship('PreOrder', back_populates='warehouse')
    partner_shares = db.relationship('WarehousePartnerShare', back_populates='warehouse')
    expenses = db.relationship('Expense', back_populates='warehouse')
    stock_adjustments = db.relationship('StockAdjustment', back_populates='warehouse', passive_deletes=True)
    __table_args__ = ()
    @validates('name','location','notes','online_slug')
    def _v_strip(self,_,v): return (v or '').strip() or None
    @validates('warehouse_type')
    def _v_warehouse_type(self,_,v):
        if isinstance(v,WarehouseType): return v.value
        s=(str(v or '')).strip().upper()
        allowed={e.value for e in WarehouseType}
        return s if s in allowed else WarehouseType.MAIN.value
    @validates('share_percent')
    def _v_share_percent(self,_,v):
        if v is None: return 0
        f=float(v)
        if f<0 or f>100: raise ValueError('share_percent must be between 0 and 100')
        return f
    @validates('capacity')
    def _v_capacity(self,_,v):
        if v is None: return None
        iv=int(v)
        if iv<0: raise ValueError('capacity must be >= 0')
        if self.current_occupancy is not None and self.current_occupancy>iv:
            raise ValueError('current_occupancy cannot exceed capacity')
        return iv
    @validates('current_occupancy')
    def _v_current_occupancy(self,_,v):
        if v is None: return 0
        iv=int(v)
        if iv<0: raise ValueError('current_occupancy must be >= 0')
        if self.capacity is not None and iv>int(self.capacity):
            raise ValueError('current_occupancy cannot exceed capacity')
        return iv
    @hybrid_property
    def warehouse_type_display(self):
        m={WarehouseType.MAIN.value:"رئيسي",WarehouseType.INVENTORY.value:"مخزن",WarehouseType.EXCHANGE.value:"تبادل",WarehouseType.PARTNER.value:"شريك",WarehouseType.ONLINE.value:"أونلاين",WarehouseType.SUPPLIER.value:"مورد"}
        wt=getattr(self,'warehouse_type',None); key=getattr(wt,'value',wt)
        return m.get(key,key)
    @hybrid_property
    def is_online(self):
        wt=getattr(self,'warehouse_type',None); key=getattr(wt,'value',wt)
        return key==WarehouseType.ONLINE.value
    def __repr__(self): return f"<Warehouse {self.name}>"

@event.listens_for(Warehouse, 'before_insert')
@event.listens_for(Warehouse, 'before_update')
def _warehouse_guard(mapper, connection, target: Warehouse):
    wt = (
        target.warehouse_type.value
        if isinstance(target.warehouse_type, WarehouseType)
        else str(target.warehouse_type or "")
    ).upper()

    if wt == WarehouseType.PARTNER.value:
        target.supplier_id = None
    elif wt == WarehouseType.EXCHANGE.value:
        target.partner_id = None
        target.share_percent = 0
    elif wt == WarehouseType.INVENTORY.value:
        target.partner_id = None
        target.supplier_id = None
        target.share_percent = 0
    elif wt == WarehouseType.MAIN.value:
        target.partner_id = None
        target.supplier_id = None
        target.share_percent = 0
    elif wt == WarehouseType.ONLINE.value:
        if not (target.online_slug or "").strip():
            nm = (target.name or "").strip().lower()
            slug = re.sub(r"[^a-z0-9]+", "-", nm).strip("-") if nm else None
            target.online_slug = slug or target.online_slug
        target.supplier_id = None
        target.partner_id = None
        target.share_percent = 0

@event.listens_for(Warehouse, "before_insert")
@event.listens_for(Warehouse, "before_update")
def _enforce_single_online_default(mapper, connection, target):
    try:
        if getattr(target, "warehouse_type", None) == WarehouseType.ONLINE.value and getattr(target, "online_is_default", False):
            q = """
            SELECT id
            FROM warehouses
            WHERE warehouse_type = :wt
              AND online_is_default = 1
              AND (:cur_id IS NULL OR id <> :cur_id)
            LIMIT 1
            """
            other = connection.execute(
                sa_text(q),
                {"wt": WarehouseType.ONLINE.value, "cur_id": getattr(target, "id", None)},
            ).first()
            if other:
                connection.execute(
                    sa_text("UPDATE warehouses SET online_is_default = 0 WHERE id = :id"),
                    {"id": other[0]},
                )
    except Exception:
        pass

class StockLevel(db.Model, TimestampMixin):
    __tablename__ = 'stock_levels'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    reserved_quantity = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    min_stock = db.Column(db.Integer)
    max_stock = db.Column(db.Integer)
    __table_args__ = (
        db.CheckConstraint('quantity >= 0', name='ck_stock_non_negative'),
        db.CheckConstraint('reserved_quantity >= 0', name='ck_reserved_non_negative'),
        # تم تعطيل هذا القيد لأننا لم نعد نستخدم نظام الحجز
        # db.CheckConstraint('(quantity - reserved_quantity) >= 0', name='ck_stock_reserved_leq_qty'),
        db.CheckConstraint('(min_stock IS NULL OR min_stock >= 0)', name='ck_min_non_negative'),
        db.CheckConstraint('(max_stock IS NULL OR max_stock >= 0)', name='ck_max_non_negative'),
        db.CheckConstraint('(min_stock IS NULL OR max_stock IS NULL OR max_stock >= min_stock)', name='ck_max_ge_min'),
        db.UniqueConstraint('product_id', 'warehouse_id', name='uq_stock_product_wh'),
        db.Index('ix_stock_product_wh', 'product_id', 'warehouse_id'),
    )
    product = db.relationship('Product', back_populates='stock_levels')
    warehouse = db.relationship('Warehouse', back_populates='stock_levels')
    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v or 0)
        if v < 0: raise ValueError("quantity must be >= 0")
        return v
    @validates('reserved_quantity')
    def _v_reserved_qty(self, _, v):
        v = int(v or 0)
        if v < 0: raise ValueError("reserved_quantity must be >= 0")
        return v
    @hybrid_property
    def available_quantity(self):
        return max(0, int(self.quantity or 0) - int(self.reserved_quantity or 0))
    @hybrid_property
    def partner_share_quantity(self):
        wh = getattr(self, 'warehouse', None)
        if not wh: return 0
        wt = getattr(wh.warehouse_type, 'value', wh.warehouse_type)
        share = float(getattr(wh, 'share_percent', 0) or 0)
        return self.quantity * share / 100.0 if wt == WarehouseType.PARTNER.value and share else 0
    @hybrid_property
    def company_share_quantity(self):
        wh = getattr(self, 'warehouse', None)
        if not wh: return self.quantity
        wt = getattr(wh.warehouse_type, 'value', wh.warehouse_type)
        return self.quantity - self.partner_share_quantity if wt == WarehouseType.PARTNER.value and wh.share_percent else self.quantity
    @hybrid_property
    def status(self):
        qv = int(self.quantity or 0); mn = int(self.min_stock or 0); mx = self.max_stock
        if qv == mn: return "عند الحد الأدنى"
        elif qv < mn: return "تحت الحد الأدنى"
        elif mx is not None:
            if qv == int(mx): return "عند الحد الأقصى"
            elif qv > int(mx): return "فوق الحد الأقصى"
        return "طبيعي"
    @property
    def last_updated(self): return self.updated_at
    def __repr__(self): return f"<StockLevel P{self.product_id} W{self.warehouse_id} Q{self.quantity} R{self.reserved_quantity}>"

class ImportRun(db.Model, TimestampMixin):
    __tablename__ = "import_runs"
    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    filename = db.Column(db.String(255))
    file_sha256 = db.Column(db.String(64))
    dry_run = db.Column(db.Boolean, nullable=False, default=False, server_default=sa_text("0"), index=True)
    inserted = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    updated = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    skipped = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    errors = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    duration_ms = db.Column(db.Integer, nullable=False, default=0, server_default=sa_text("0"))
    report_path = db.Column(db.String(255))
    notes = db.Column(db.String(255))
    meta = db.Column(db.JSON, default=dict)
    warehouse = db.relationship("Warehouse", backref=db.backref("import_runs", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("import_runs", lazy="dynamic"))
    __table_args__ = ()
    def __repr__(self) -> str:
        return f"<ImportRun id={self.id} wh={self.warehouse_id} dry={self.dry_run} ins={self.inserted} upd={self.updated} skp={self.skipped} err={self.errors}>"

def _ensure_stock_row(connection, product_id: int, warehouse_id: int):
    row = connection.execute(sa_text("SELECT id FROM stock_levels WHERE product_id = :p AND warehouse_id = :w"), {"p": product_id, "w": warehouse_id}).first()
    if row: return row
    dialect = getattr(connection, "dialect", None); dname = getattr(dialect, "name", "") if dialect else ""
    try:
        if dname.startswith("postgre"):
            connection.execute(sa_text("INSERT INTO stock_levels (product_id, warehouse_id, quantity, reserved_quantity) VALUES (:p, :w, 0, 0) ON CONFLICT (product_id, warehouse_id) DO NOTHING"), {"p": product_id, "w": warehouse_id})
        else:
            connection.execute(sa_text("INSERT INTO stock_levels (product_id, warehouse_id, quantity, reserved_quantity) SELECT :p, :w, 0, 0 WHERE NOT EXISTS (SELECT 1 FROM stock_levels WHERE product_id = :p AND warehouse_id = :w)"), {"p": product_id, "w": warehouse_id})
    except Exception:
        pass
    return connection.execute(sa_text("SELECT id FROM stock_levels WHERE product_id = :p AND warehouse_id = :w"), {"p": product_id, "w": warehouse_id}).first()

def _apply_stock_delta(connection, product_id: int, warehouse_id: int, delta_qty: int):
    row = _ensure_stock_row(connection, product_id, warehouse_id); sid = row._mapping["id"]; qv = int(delta_qty or 0)
    if qv == 0:
        qty = connection.execute(sa_text("SELECT quantity FROM stock_levels WHERE id = :id"), {"id": sid}).scalar_one()
        return int(qty)
    if qv > 0:
        connection.execute(sa_text("UPDATE stock_levels SET quantity = quantity + :q WHERE id = :id"), {"id": sid, "q": qv})
    else:
        res = connection.execute(sa_text("UPDATE stock_levels SET quantity = quantity + :q WHERE id = :id AND quantity + :q >= 0 AND quantity + :q >= reserved_quantity"), {"id": sid, "q": qv})
        if getattr(res, "rowcount", None) != 1:
            raise ValueError(f"الكمية غير كافية للمنتج {product_id} في المستودع {warehouse_id}")
    qty = connection.execute(sa_text("SELECT quantity FROM stock_levels WHERE id = :id"), {"id": sid}).scalar_one()
    return int(qty)

def _apply_reservation_delta(connection, product_id: int, warehouse_id: int, delta_qty: int):
    row = _ensure_stock_row(connection, product_id, warehouse_id); sid = row._mapping["id"]; qv = int(delta_qty or 0)
    if qv == 0: return
    if qv > 0:
        res = connection.execute(sa_text("UPDATE stock_levels SET reserved_quantity = reserved_quantity + :q WHERE id = :id AND (quantity - reserved_quantity) >= :q"), {"id": sid, "q": qv})
        if getattr(res, "rowcount", 0) != 1:
            raise ValueError("الكمية المتاحة غير كافية للحجز")
    else:
        connection.execute(sa_text("UPDATE stock_levels SET reserved_quantity = CASE WHEN reserved_quantity + :q < 0 THEN 0 ELSE reserved_quantity + :q END WHERE id = :id"), {"id": sid, "q": qv})

class Transfer(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'transfers'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    direction = db.Column(sa_str_enum(TransferDirection, name='transfer_direction'), nullable=False)
    transfer_date = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    product = db.relationship('Product', back_populates='transfers')
    source_warehouse = db.relationship('Warehouse', foreign_keys=[source_id], back_populates='transfers_source')
    destination_warehouse = db.relationship('Warehouse', foreign_keys=[destination_id], back_populates='transfers_destination')
    user = db.relationship('User')
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_transfer_qty_positive'),
        db.CheckConstraint('source_id <> destination_id', name='chk_transfer_diff_wh'),
    )
    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v or 0)
        if v <= 0: raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
        return v
    def __repr__(self): return f"<Transfer {self.reference}>"

@event.listens_for(Transfer, 'before_insert', propagate=True)
def _ensure_transfer_reference(mapper, connection, target: "Transfer"):
    if getattr(target, 'reference', None): return
    prefix = datetime.now(timezone.utc).strftime("TRF%Y%m%d"); unique = uuid.uuid4().hex[:8].upper()
    target.reference = f"{prefix}-{unique}"

@event.listens_for(Transfer, "after_insert", propagate=True)
def _transfer_after_insert(mapper, connection, target: "Transfer"):
    if getattr(target, "_skip_stock_apply", False): return
    qty = int(target.quantity or 0)
    if qty <= 0: return
    _apply_stock_delta(connection, target.product_id, target.source_id, -qty)
    _apply_stock_delta(connection, target.product_id, target.destination_id, +qty)

@event.listens_for(Transfer, "after_update", propagate=True)
def _transfer_after_update(mapper, connection, target: "Transfer"):
    hist = inspect(target)
    def _old_new(attr):
        h = hist.attrs[attr].history
        old = h.deleted[0] if h.deleted else getattr(target, attr)
        new = h.added[0]   if h.added   else getattr(target, attr)
        return old, new
    touched = any(hist.attrs[a].history.has_changes() for a in ("product_id", "source_id", "destination_id", "quantity"))
    if not touched: return
    p_old, p_new = _old_new("product_id"); s_old, s_new = _old_new("source_id"); d_old, d_new = _old_new("destination_id"); q_old, q_new = _old_new("quantity")
    _apply_stock_delta(connection, int(p_old), int(s_old), +int(q_old or 0))
    _apply_stock_delta(connection, int(p_old), int(d_old), -int(q_old or 0))
    _apply_stock_delta(connection, int(p_new), int(s_new), -int(q_new or 0))
    _apply_stock_delta(connection, int(p_new), int(d_new), +int(q_new or 0))

@event.listens_for(Transfer, "after_delete", propagate=True)
def _transfer_after_delete(mapper, connection, target: "Transfer"):
    qty = int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.source_id, +qty)
    _apply_stock_delta(connection, target.product_id, target.destination_id, -qty)

def _ex_dir_sign(direction: str) -> int:
    d = (getattr(direction, "value", direction) or "").upper()
    if d == "IN": return 1
    if d == "OUT": return -1
    if d == "ADJUSTMENT": return 1
    raise ValueError(f"Unknown exchange direction: {direction}")

class ExchangeTransaction(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'exchange_transactions'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), index=True, nullable=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    quantity = db.Column(db.Integer, nullable=False)
    direction = db.Column(sa_str_enum(TransferDirection, name='exchange_direction'), default='IN', nullable=False, index=True, server_default=sa_text("'IN'"))
    unit_cost = db.Column(db.Numeric(12, 2))
    is_priced = db.Column(db.Boolean, nullable=False, server_default=sa_text("0"))
    notes = db.Column(db.Text)
    product = db.relationship('Product', back_populates='exchange_transactions')
    warehouse = db.relationship('Warehouse', back_populates='exchange_transactions')
    supplier = db.relationship('Supplier')
    partner = db.relationship('Partner')
    gl_batches = db.relationship("GLBatch", primaryjoin="and_(foreign(GLBatch.source_id)==ExchangeTransaction.id, GLBatch.source_type=='EXCHANGE')", viewonly=True, order_by="GLBatch.id")
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_exchange_qty_positive'),
        db.Index('ix_exchange_prod_wh', 'product_id', 'warehouse_id'),
        db.Index('ix_exchange_supplier', 'supplier_id'),
        CheckConstraint('unit_cost IS NULL OR unit_cost >= 0', name='ck_exchange_unit_cost_non_negative'),
    )
    @validates('direction')
    def _v_direction(self, _, v):
        return (getattr(v, 'value', v) or '').strip().upper()
    def __repr__(self): return f"<ExchangeTransaction P{self.product_id} W{self.warehouse_id} Q{self.quantity}>"

@event.listens_for(ExchangeTransaction, "before_insert")
@event.listens_for(ExchangeTransaction, "before_update")
def _xt_guard_and_price(mapper, connection, target: "ExchangeTransaction"):
    wh = connection.execute(sa_text("SELECT id, warehouse_type, supplier_id FROM warehouses WHERE id=:wid"), {"wid": target.warehouse_id}).mappings().first()
    if not wh: raise ValueError("Warehouse not found.")
    wt = (wh["warehouse_type"] or "").upper()
    
    # ملاحظة: المستودع ليس مرتبطاً بمورد محدد
    # المورد يُحدد في ExchangeTransaction نفسه (target.supplier_id)
    # لذلك نستخدم supplier_id من المعاملة وليس من المستودع
    if wt == WarehouseType.EXCHANGE.value:
        # إذا لم يكن supplier_id محدد في المعاملة، نستخدم من المستودع (إن وجد)
        if not target.supplier_id and wh["supplier_id"]:
            target.supplier_id = wh["supplier_id"]
    else:
        target.supplier_id = None
    
    uc = D(target.unit_cost or 0)
    if uc <= 0:
        price = connection.execute(sa_text("SELECT COALESCE(purchase_price,0) AS p FROM products WHERE id=:pid"), {"pid": target.product_id}).scalar() or 0
        target.unit_cost = q(price); target.is_priced = bool(D(price) > 0)
    else:
        target.unit_cost = q(uc); target.is_priced = True
    target.direction = (getattr(target.direction, "value", target.direction) or "").strip().upper()

@event.listens_for(ExchangeTransaction, "after_insert")
def _exchange_after_insert(mapper, connection, target: "ExchangeTransaction"):
    if getattr(target, "_skip_stock_apply", False): return
    delta = _ex_dir_sign(target.direction) * int(target.quantity or 0)
    if delta: _apply_stock_delta(connection, target.product_id, target.warehouse_id, delta)
    _maybe_post_gl_exchange(connection, target)
    
    # تحديث رصيد المورد
    if hasattr(target, 'supplier_id') and target.supplier_id:
        try:
            update_supplier_balance(target.supplier_id, connection)
        except Exception as e:
            pass

@event.listens_for(ExchangeTransaction, "after_update")
def _exchange_after_update(mapper, connection, target: "ExchangeTransaction"):
    hist = inspect(target)
    def old_new(attr):
        h = hist.attrs[attr].history
        old = h.deleted[0] if h.deleted else getattr(target, attr)
        new = h.added[0]   if h.added   else getattr(target, attr)
        return old, new
    p_old, p_new = old_new("product_id"); w_old, w_new = old_new("warehouse_id"); q_old, q_new = old_new("quantity"); d_old, d_new = old_new("direction")
    touched = any(hist.attrs[a].history.has_changes() for a in ("product_id","warehouse_id","quantity","direction"))
    if touched:
        undo_delta = -_ex_dir_sign(d_old) * int(q_old or 0)
        if undo_delta: _apply_stock_delta(connection, int(p_old), int(w_old), undo_delta)
        redo_delta = _ex_dir_sign(d_new) * int(q_new or 0)
        if redo_delta: _apply_stock_delta(connection, int(p_new), int(w_new), redo_delta)
    _maybe_post_gl_exchange(connection, target)
    
    # تحديث رصيد المورد
    if hasattr(target, 'supplier_id') and target.supplier_id:
        try:
            update_supplier_balance(target.supplier_id, connection)
        except Exception as e:
            pass

@event.listens_for(ExchangeTransaction, "after_delete")
def _exchange_after_delete(mapper, connection, target: "ExchangeTransaction"):
    delta = -_ex_dir_sign(target.direction) * int(target.quantity or 0)
    if delta: _apply_stock_delta(connection, target.product_id, target.warehouse_id, delta)
    
    # تحديث رصيد المورد
    if hasattr(target, 'supplier_id') and target.supplier_id:
        try:
            update_supplier_balance(target.supplier_id, connection)
        except Exception as e:
            pass

def _maybe_post_gl_exchange(connection, tx: "ExchangeTransaction"):
    try:
        from flask import current_app
        cfg = current_app.config or {}
    except Exception:
        cfg = {}
    if not bool(cfg.get("GL_AUTO_POST_ON_EXCHANGE", False)): return
    # استخدام الدالة من models.py مباشرة بدلاً من accounting module المفقود
    # GL_ACCOUNTS و _gl_upsert_batch_and_entries موجودين في نهاية models.py
    inv_acc  = (cfg.get("GL_EXCHANGE_INV_ACCOUNT")  or GL_ACCOUNTS.get("INV_EXCHANGE"))
    cogs_acc = (cfg.get("GL_EXCHANGE_COGS_ACCOUNT") or GL_ACCOUNTS.get("COGS_EXCHANGE"))
    ap_acc   = (cfg.get("GL_EXCHANGE_AP_ACCOUNT")   or GL_ACCOUNTS.get("AP"))
    if not inv_acc: return
    direction = (getattr(tx, "direction", "") or "").upper()
    qty = int(tx.quantity or 0)
    if qty <= 0: return
    unit_cost = D(tx.unit_cost or 0); amount = float(q(qty * unit_cost))
    if amount <= 0: return
    currency = (cfg.get("DEFAULT_CURRENCY") or "ILS")
    ref = f"EX-{tx.id}"; memo = f"Exchange {direction} P{tx.product_id} W{tx.warehouse_id} Q{qty}"
    if direction in ("IN", "ADJUSTMENT"):
        if not ap_acc: return
        entries = [(str(inv_acc).upper(), amount, 0.0), (str(ap_acc).upper(), 0.0, amount)]
        purpose = direction
    elif direction == "OUT":
        if not cogs_acc: return
        entries = [(str(cogs_acc).upper(), amount, 0.0), (str(inv_acc).upper(), 0.0, amount)]
        purpose = "OUT"
    else:
        return
    _gl_upsert_batch_and_entries(connection, source_type="EXCHANGE", source_id=int(tx.id), purpose=str(purpose).upper(), currency=str(currency).upper(), memo=memo, entries=entries, ref=ref, entity_type="SUPPLIER" if tx.supplier_id else None, entity_id=int(tx.supplier_id) if tx.supplier_id else None)

class WarehousePartnerShare(db.Model, TimestampMixin):
    __tablename__ = 'warehouse_partner_shares'
    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), index=True, nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), index=True, nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True, nullable=True)
    share_percentage = db.Column(db.Float, nullable=False, default=0.0)
    share_amount = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text)
    partner = db.relationship('Partner', back_populates='shares', overlaps="product_shares,warehouse_shares,shares")
    warehouse = db.relationship('Warehouse', back_populates='partner_shares')
    product = db.relationship('Product', foreign_keys=[product_id], viewonly=True)
    __table_args__ = (
        db.UniqueConstraint('partner_id', 'warehouse_id', 'product_id', name='uq_wps_partner_wh_prod'),
        db.Index('ix_wps_partner_wh_prod', 'partner_id', 'warehouse_id', 'product_id'),
        CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='ck_wps_share_percentage_range'),
        CheckConstraint('share_amount >= 0', name='ck_wps_share_amount_non_negative'),
    )
    def __repr__(self): return f"<WarehousePartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id} {self.share_percentage}%>"

class ProductPartnerShare(db.Model):
    __table__ = WarehousePartnerShare.__table__
    partner = db.relationship('Partner', foreign_keys=[WarehousePartnerShare.partner_id], viewonly=True)
    warehouse = db.relationship('Warehouse', foreign_keys=[WarehousePartnerShare.warehouse_id], viewonly=True)
    product = db.relationship('Product', back_populates='partner_shares', foreign_keys=[WarehousePartnerShare.product_id])
    def __repr__(self): return f"<ProductPartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id}>"

class ProductPartner(db.Model):
    __tablename__ = 'product_partners'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False)
    share_percent = db.Column(db.Float, nullable=False, default=0.0)
    share_amount = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text)
    product = db.relationship('Product', back_populates='partners')
    partner = db.relationship('Partner', back_populates='product_links')
    __table_args__ = (
        db.CheckConstraint('share_percent >= 0 AND share_percent <= 100', name='chk_partner_share'),
        db.Index('ix_product_partner_pair', 'product_id', 'partner_id'),
        CheckConstraint('share_amount >= 0', name='ck_product_partner_share_amount_non_negative'),
    )
    def __repr__(self): return f"<ProductPartner {self.partner_id} {self.share_percent}%>"

class PreOrder(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'preorders'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, index=True)
    preorder_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expected_date = db.Column(db.DateTime)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    prepaid_amount = db.Column(db.Numeric(12, 2), default=0, server_default=sa_text("0"))
    tax_rate = db.Column(db.Numeric(5, 2), default=0, server_default=sa_text("0"))
    status = db.Column(sa_str_enum(PreOrderStatus, name='preorder_status'), default=PreOrderStatus.PENDING.value, nullable=False, index=True, server_default=sa_text("'PENDING'"))
    notes = db.Column(db.Text)
    payment_method = db.Column(sa_str_enum(PaymentMethod, name='preorder_payment_method'), default=PaymentMethod.CASH.value, nullable=False, server_default=sa_text("'cash'"))
    currency = db.Column(db.String(10), default='ILS', nullable=False, server_default=sa_text("'ILS'"))
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    refunded_total = db.Column(db.Numeric(12, 2), default=0, nullable=False, server_default=sa_text("0"))
    refund_of_id = db.Column(db.Integer, db.ForeignKey('preorders.id', ondelete='SET NULL'), index=True)
    idempotency_key = db.Column(db.String(64), unique=True, index=True)
    cancelled_at = db.Column(db.DateTime, index=True)
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    cancel_reason = db.Column(db.String(200))
    customer = db.relationship('Customer', back_populates='preorders')
    supplier = db.relationship('Supplier', back_populates='preorders')
    partner = db.relationship('Partner', back_populates='preorders')
    product = db.relationship('Product', back_populates='preorders')
    warehouse = db.relationship('Warehouse', back_populates='preorders')
    cancelled_by_user = db.relationship('User', foreign_keys=[cancelled_by])
    refund_of = db.relationship('PreOrder', remote_side=[id])
    payments = db.relationship('Payment', back_populates='preorder', cascade='all, delete-orphan')
    sale = db.relationship('Sale', back_populates='preorder', uselist=False)
    invoice = db.relationship('Invoice', back_populates='preorder', uselist=False)
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_preorder_quantity_positive'),
        db.CheckConstraint('prepaid_amount >= 0', name='chk_preorder_prepaid_non_negative'),
        db.CheckConstraint('tax_rate >= 0 AND tax_rate <= 100', name='chk_preorder_tax_rate'),
        db.CheckConstraint('refunded_total >= 0', name='chk_preorder_refunded_total_non_negative'),
        db.Index('ix_preorders_cust_status', 'customer_id', 'status'),
        db.Index('ix_preorders_partner_status', 'partner_id', 'status'),
        db.Index('ix_preorders_supplier_status', 'supplier_id', 'status'),
        db.Index('ix_preorders_prod_wh', 'product_id', 'warehouse_id'),
    )
    @property
    def reservation_code(self): return self.reference
    @reservation_code.setter
    def reservation_code(self, v): self.reference = v
    @validates('quantity')
    def _v_qty(self, _, v):
        i = int(v or 0)
        if i <= 0: raise ValueError('quantity must be > 0')
        return i
    @validates('prepaid_amount', 'refunded_total')
    def _v_money(self, _, v):
        if v in (None, ''): return D('0.00')
        dv = q(v)
        if dv < 0: raise ValueError('amount must be >= 0')
        return dv
    @validates('currency')
    def _v_curr(self, _, v): return ensure_currency(v or 'ILS')
    @hybrid_property
    def total_before_tax(self):
        price = D(getattr(self.product, "price", 0)); qty = D(self.quantity or 0)
        return qty * price
    @total_before_tax.expression
    def total_before_tax(cls):
        return (select(func.coalesce(Product.price, 0) * cls.quantity).select_from(Product).where(Product.id == cls.product_id).scalar_subquery())
    @hybrid_property
    def total_with_tax(self):
        base = D(self.total_before_tax); tr = D(self.tax_rate or 0)
        return base * (Decimal("1") + tr / Decimal("100"))
    @total_with_tax.expression
    def total_with_tax(cls):
        base = (select(func.coalesce(Product.price, 0) * cls.quantity).select_from(Product).where(Product.id == cls.product_id).scalar_subquery())
        return base * (1 + (func.coalesce(cls.tax_rate, 0) / 100.0))
    @hybrid_property
    def total_amount(self): return self.total_with_tax
    @total_amount.expression
    def total_amount(cls): return cls.total_with_tax
    @hybrid_property
    def total_paid(self):
        return float(db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(Payment.preorder_id == self.id, Payment.status == PaymentStatus.COMPLETED.value, Payment.direction == PaymentDirection.IN.value).scalar() or 0)
    @total_paid.expression
    def total_paid(cls):
        return (select(func.coalesce(func.sum(Payment.total_amount), 0)).where((Payment.preorder_id == cls.id) & (Payment.status == PaymentStatus.COMPLETED.value) & (Payment.direction == PaymentDirection.IN.value)).scalar_subquery())
    @hybrid_property
    def balance_due(self): return D(self.total_amount) - D(self.total_paid or 0)
    @balance_due.expression
    def balance_due(cls):
        total_expr = (select((Product.price * cls.quantity) * (1 + (func.coalesce(cls.tax_rate, 0) / 100.0))).select_from(Product).where(Product.id == cls.product_id).scalar_subquery())
        paid_expr = (select(func.coalesce(func.sum(Payment.total_amount), 0)).where((Payment.preorder_id == cls.id) & (Payment.status == PaymentStatus.COMPLETED.value) & (Payment.direction == PaymentDirection.IN.value)).scalar_subquery())
        return total_expr - paid_expr
    @hybrid_property
    def net_balance(self): return self.balance_due
    @hybrid_property
    def refundable_amount(self): return float(q(self.prepaid_amount or 0) - q(self.refunded_total or 0))
    def can_refund(self, amount): amt = q(amount or 0); return amt > 0 and amt <= q(self.refundable_amount)
    def apply_refund(self, amount):
        if not self.can_refund(amount): raise ValueError("preorder.refund_exceeds_allowed")
        self.refunded_total = q(self.refunded_total or 0) + q(amount or 0)
    def cancel(self, by_user_id: int | None = None, reason: str | None = None):
        self.cancelled_at = datetime.now(timezone.utc); self.cancelled_by = by_user_id; self.cancel_reason = (reason or None); self.status = PreOrderStatus.CANCELLED.value
    def __repr__(self): return f"<PreOrder {self.reference or self.id}>"

_ALLOWED_PREORDER_TRANSITIONS = {"PENDING":{"CONFIRMED","CANCELLED","FULFILLED"},"CONFIRMED":{"FULFILLED","CANCELLED"},"FULFILLED":set(),"CANCELLED":set()}

@event.listens_for(PreOrder, 'before_insert')
def _preorder_before_insert(mapper, connection, target):
    if not getattr(target, 'reference', None):
        prefix = datetime.now(timezone.utc).strftime("PRE%Y%m%d"); unique = uuid.uuid4().hex[:8].upper()
        target.reference = f"{prefix}-{unique}"
    target.currency = ensure_currency(target.currency or 'ILS')

@event.listens_for(PreOrder, 'before_update')
def _preorder_before_update(mapper, connection, target):
    from sqlalchemy.orm.attributes import get_history
    target.currency = ensure_currency(target.currency or 'ILS')
    h = get_history(target, "status")
    oldv = (getattr(h, "deleted", None) or [getattr(target, "status", None)])[0]
    newv = getattr(target, "status", None)
    o = (getattr(oldv, "value", oldv) or "PENDING"); n = getattr(newv, "value", newv)
    if o != n:
        allowed = _ALLOWED_PREORDER_TRANSITIONS.get(o, set())
        if n not in allowed: raise ValueError("preorder.invalid_status_transition")

@event.listens_for(PreOrder, "after_update")
def _preorder_reservation_flow(mapper, connection, target: "PreOrder"):
    hist = inspect(target); h = hist.attrs['status'].history
    old_status = (h.deleted[0] if h.deleted else getattr(target, "status", "") or "").upper()
    new_status = (h.added[0] if h.added else getattr(target, "status", "") or "").upper()
    if old_status == new_status: return
    wid = getattr(target, "warehouse_id", None); pid = getattr(target, "product_id", None); qty = int(getattr(target, "quantity", 0) or 0)
    if not (wid and pid and qty > 0): return
    if new_status == "CONFIRMED" and old_status != "CONFIRMED":
        try: _apply_reservation_delta(connection, pid, wid, +qty)
        except Exception: pass
    elif new_status == "FULFILLED":
        try:
            _apply_reservation_delta(connection, pid, wid, -qty)
            _apply_stock_delta(connection, pid, wid, -qty)
        except Exception: pass
    elif old_status == "CONFIRMED" and new_status != "CONFIRMED":
        try: _apply_reservation_delta(connection, pid, wid, -qty)
        except Exception: pass

class Sale(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), unique=True, index=True)
    sale_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    preorder_id = db.Column(db.Integer, db.ForeignKey("preorders.id"), index=True)

    tax_rate = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    discount_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    notes = db.Column(db.Text)
    receiver_name = db.Column(db.String(200))  # اسم مستلم البضاعة

    status = db.Column(sa_str_enum(SaleStatus, name="sale_status"), default=SaleStatus.DRAFT.value, nullable=False, index=True)
    payment_status = db.Column(sa_str_enum(PaymentProgress, name="sale_payment_progress"), default=PaymentProgress.PENDING.value, nullable=False, index=True)

    currency = db.Column(db.String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    shipping_address = db.Column(db.Text)
    billing_address = db.Column(db.Text)
    shipping_cost = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_paid = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    balance_due = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    refunded_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    refund_of_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), index=True)
    idempotency_key = db.Column(db.String(64), unique=True, index=True)

    cancelled_at = db.Column(db.DateTime, index=True)
    cancelled_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    cancel_reason = db.Column(db.String(200))
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    customer = db.relationship("Customer", back_populates="sales")
    seller = db.relationship("User", back_populates="sales", foreign_keys=[seller_id])
    cancelled_by_user = db.relationship("User", back_populates="cancelled_sales", foreign_keys=[cancelled_by])
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])
    preorder = db.relationship("PreOrder", back_populates="sale")
    refund_of = db.relationship("Sale", remote_side=[id])

    lines = db.relationship("SaleLine", back_populates="sale", cascade="all,delete-orphan", order_by="SaleLine.id")
    payments = db.relationship("Payment", back_populates="sale", cascade="all,delete-orphan", order_by="Payment.id")
    invoice = db.relationship("Invoice", back_populates="sale", uselist=False)
    shipments = db.relationship("Shipment", back_populates="sale", cascade="all,delete-orphan", order_by="Shipment.id")

    gl_batches = db.relationship("GLBatch", primaryjoin="and_(foreign(GLBatch.source_id)==Sale.id, GLBatch.source_type=='SALE')", viewonly=True, order_by="GLBatch.id")

    __table_args__ = (
        db.CheckConstraint("discount_total >= 0", name="ck_sale_discount_non_negative"),
        db.CheckConstraint("shipping_cost >= 0", name="ck_sale_shipping_cost_non_negative"),
        db.CheckConstraint("total_amount >= 0", name="ck_sale_total_amount_non_negative"),
        db.CheckConstraint("total_paid >= 0", name="ck_sale_total_paid_non_negative"),
        # السماح بـ balance_due سالب للمبيعات للموردين/الشركاء
        # db.CheckConstraint("balance_due >= 0", name="ck_sale_balance_due_non_negative"),
        db.CheckConstraint("refunded_total >= 0", name="ck_sale_refunded_total_non_negative"),
        db.Index("ix_sales_customer_status_date", "customer_id", "status", "sale_date"),
        db.Index("ix_sales_payment_status_date", "payment_status", "sale_date"),
    )

    @hybrid_property
    def subtotal(self):
        return sum(D(l.net_amount) for l in (self.lines or [])) if self.lines else Decimal("0.00")

    @hybrid_property
    def tax_amount(self):
        base = D(self.subtotal) - D(self.discount_total or 0)
        return base * D(self.tax_rate or 0) / Decimal("100.0")

    @hybrid_property
    def total(self):
        return D(self.subtotal) + D(self.tax_amount) + D(self.shipping_cost or 0) - D(self.discount_total or 0)

    @hybrid_property
    def refundable_amount(self):
        return float(q(self.total_amount or 0) - q(self.refunded_total or 0))

    def can_refund(self, amount: Decimal | float | int) -> bool:
        amt = q(amount or 0)
        return amt > 0 and amt <= q(self.refundable_amount)

    def apply_refund(self, amount: Decimal | float | int):
        if not self.can_refund(amount):
            raise ValueError("sale.refund_exceeds_allowed")
        self.refunded_total = q(self.refunded_total or 0) + q(amount or 0)
        if q(self.refunded_total) >= q(self.total_amount or 0):
            self.status = SaleStatus.REFUNDED.value

    def cancel(self, by_user_id: int | None = None, reason: str | None = None):
        self.status = SaleStatus.CANCELLED.value
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancelled_by = by_user_id
        self.cancel_reason = (reason or None)

    def reserve_stock(self):
        for l in (self.lines or []):
            lvl = (
                StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id)
                .with_for_update()
                .first()
            )
            if not lvl:
                raise Exception("لا يوجد صف مخزون لهذا المنتج/المستودع")
            available = int(lvl.quantity or 0) - int(lvl.reserved_quantity or 0)
            need = int(l.quantity or 0)
            if available < need:
                raise Exception("الكمية المتاحة للحجز غير كافية في هذا المستودع")
            lvl.reserved_quantity = int(lvl.reserved_quantity or 0) + need

    def release_stock(self):
        for l in (self.lines or []):
            lvl = (
                StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id)
                .with_for_update()
                .first()
            )
            if lvl:
                need = int(l.quantity or 0)
                cur = int(lvl.reserved_quantity or 0)
                lvl.reserved_quantity = max(0, cur - need)

    def update_payment_status(self):
        """تحديث حالة الدفع وحساب المبلغ المدفوع من الدفعات المرتبطة"""
        from sqlalchemy import func
        
        # حساب total_paid من الدفعات المكتملة المرتبطة بهذا البيع
        paid_sum = db.session.query(
            func.coalesce(func.sum(Payment.total_amount), 0)
        ).filter(
            Payment.sale_id == self.id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.direction == PaymentDirection.IN
        ).scalar() or 0
        
        self.total_paid = float(paid_sum)
        total = float(self.total or 0)
        
        self.payment_status = (
            PaymentProgress.PAID.value if self.total_paid >= total
            else PaymentProgress.PARTIAL.value if self.total_paid > 0
            else PaymentProgress.PENDING.value
        )
        
        # ✅ تأكيد الفاتورة تلقائياً عند إضافة أي دفعة
        if self.status == SaleStatus.DRAFT.value and self.total_paid > 0:
            self.status = SaleStatus.CONFIRMED.value

    @validates("currency")
    def _v_currency(self, _, v):
        return ensure_currency(v or "ILS")

    @validates("tax_rate", "discount_total", "shipping_cost", "total_amount", "total_paid", "balance_due", "refunded_total")
    def _v_amounts(self, key, v):
        dv = q(v or 0)
        if key == "tax_rate" and (dv < 0 or dv > 100):
            raise ValueError("invalid tax_rate")
        if dv < 0:
            raise ValueError(f"{key} must be >= 0")
        return dv

    def __repr__(self):
        return f"<Sale {self.sale_number}>"

@event.listens_for(Sale, "before_insert")
def _sale_before_insert_ref(mapper, connection, target: "Sale"):
    if not getattr(target, "sale_number", None):
        prefix = datetime.now(timezone.utc).strftime("SAL%Y%m%d")
        count = connection.execute(sa_text("SELECT COUNT(*) FROM sales WHERE sale_number LIKE :pfx"), {"pfx": f"{prefix}-%"}).scalar() or 0
        target.sale_number = f"{prefix}-{count+1:04d}"

@event.listens_for(Sale, "after_insert", propagate=True)
@event.listens_for(Sale, "after_update", propagate=True)
@event.listens_for(Sale, "after_delete", propagate=True)
def _update_partner_supplier_balance_on_sale(mapper, connection, target: "Sale"):
    """تحديث رصيد الشريك/المورد عند إنشاء/تعديل/حذف المبيعة"""
    try:
        # التحقق من أن الفاتورة مؤكدة
        if target.status != SaleStatus.CONFIRMED.value:
            return
        
        # جلب العميل المرتبط بالمبيعة
        customer_id = getattr(target, "customer_id", None)
        if not customer_id:
            return
        
        from sqlalchemy import text as sa_text
        
        # التحقق من وجود مورد مرتبط بهذا العميل
        supplier_result = connection.execute(
            sa_text("SELECT id FROM suppliers WHERE customer_id = :cid"),
            {"cid": customer_id}
        ).fetchone()
        
        if supplier_result:
            supplier_id = supplier_result[0]
            update_supplier_balance(supplier_id, connection)
        
        # التحقق من وجود شريك مرتبط بهذا العميل
        partner_result = connection.execute(
            sa_text("SELECT id FROM partners WHERE customer_id = :cid"),
            {"cid": customer_id}
        ).fetchone()
        
        if partner_result:
            partner_id = partner_result[0]
            update_partner_balance(partner_id, connection)
    
    except Exception as e:
        pass

@event.listens_for(Sale, "before_insert")
@event.listens_for(Sale, "before_update")
def _compute_total_amount(mapper, connection, target: "Sale"):
    subtotal = sum(q(l.net_amount) for l in (target.lines or []))
    discount = q(target.discount_total)
    tax_rate = q(target.tax_rate)
    shipping = q(target.shipping_cost)
    base = subtotal - discount
    if base < 0:
        base = Decimal("0.00")
    tax = q(base * tax_rate / Decimal("100"))
    target.total_amount = q(subtotal + tax + shipping - discount)
    target.balance_due = q(target.total_amount or 0) - q(target.total_paid or 0)

@event.listens_for(Sale, "before_update")
def _sale_enforce_status(mapper, connection, target: "Sale"):
    from sqlalchemy.orm.attributes import get_history
    h = get_history(target, "status")
    oldv = (getattr(h, "deleted", None) or [getattr(target, "status", None)])[0]
    newv = getattr(target, "status", None)
    o = (getattr(oldv, "value", oldv) or "DRAFT")
    n = getattr(newv, "value", newv)
    if o != n:
        allowed = _ALLOWED_SALE_TRANSITIONS.get(o, set())
        if n not in allowed:
            raise ValueError("sale.invalid_status_transition")

@event.listens_for(Sale.status, "set")
def _reserve_release_on_status_change(target, value, oldvalue, initiator):
    """
    تم تعطيل نظام الحجز - الخصم يتم مباشرة عند الدفع
    """
    newv = getattr(value, "value", value)
    oldv = getattr(oldvalue, "value", oldvalue)
    if newv == SaleStatus.CONFIRMED.value and oldv != SaleStatus.CONFIRMED.value:
        # التحقق من حد الائتمان فقط
        if target.customer and float(target.customer.credit_limit or 0) > 0:
            cur_bal = float(target.customer.balance or 0)
            new_total = float(getattr(target, "total", None) or getattr(target, "total_amount", 0) or 0)
            if cur_bal + new_total > float(target.customer.credit_limit or 0):
                raise Exception("تأكيد البيع مرفوض: حد الائتمان للعميل سيتجاوز المسموح.")
        # تم تعطيل: target.reserve_stock()
    # elif oldv == SaleStatus.CONFIRMED.value and newv != SaleStatus.CONFIRMED.value:
        # تم تعطيل: target.release_stock()


# ═══════════════════════════════════════════════════════════════════════
# 📊 Accounting Listeners - إنشاء GLBatch تلقائي للمبيعات
# ═══════════════════════════════════════════════════════════════════════

@event.listens_for(Sale, "after_insert")
@event.listens_for(Sale, "after_update")
def _sale_gl_batch_upsert(mapper, connection, target: "Sale"):
    """إنشاء/تحديث GLBatch للبيع تلقائياً"""
    # فقط للمبيعات المؤكدة
    if target.status != SaleStatus.CONFIRMED.value:
        return
    
    try:
        from models import fx_rate
        
        # تحويل المبلغ للشيقل
        amount = float(target.total_amount or 0)
        if amount <= 0:
            return
        
        # تحويل العملة
        amount_ils = amount
        if target.currency and target.currency != 'ILS':
            try:
                rate = fx_rate(target.currency, 'ILS', target.sale_date or datetime.utcnow(), raise_on_missing=False)
                if rate and rate > 0:
                    amount_ils = float(amount * float(rate))
            except:
                pass
        
        # جلب SaleLines لتحليل نسب الشركاء/الموردين
        from sqlalchemy import select as sa_select
        sale_lines = connection.execute(
            sa_select(
                SaleLine.id,
                SaleLine.product_id,
                SaleLine.warehouse_id,
                SaleLine.quantity,
                SaleLine.unit_price,
                SaleLine.discount_rate,
                SaleLine.tax_rate
            ).where(SaleLine.sale_id == target.id)
        ).fetchall()
        
        if not sale_lines:
            return  # لا توجد بنود
        
        # القيد المحاسبي الأساسي
        entries = []
        
        # مدين: حسابات العملاء (AR) - المبلغ الكامل
        entries.append((GL_ACCOUNTS.get("AR", "1100_AR"), amount_ils, 0))
        
        # تحليل كل SaleLine
        total_revenue_company = 0.0
        total_revenue_partners = {}  # {partner_id: amount}
        total_cogs_suppliers = {}    # {supplier_id: amount}
        
        for line in sale_lines:
            line_id, product_id, warehouse_id, qty, unit_price, disc_rate, tax_rate = line
            
            # حساب صافي المبلغ للبند
            gross = float(qty or 0) * float(unit_price or 0)
            discount = gross * (float(disc_rate or 0) / 100.0)
            taxable = gross - discount
            tax = taxable * (float(tax_rate or 0) / 100.0)
            line_total = taxable + tax
            
            # جلب نوع المستودع
            wh_result = connection.execute(
                sa_text("SELECT warehouse_type, partner_id, supplier_id, share_percent FROM warehouses WHERE id = :wid"),
                {"wid": warehouse_id}
            ).fetchone()
            
            if not wh_result:
                # مستودع غير موجود - نعتبره MAIN
                total_revenue_company += line_total
                continue
            
            wh_type, wh_partner_id, wh_supplier_id, wh_share_pct = wh_result
            
            # تحليل حسب نوع المستودع
            if wh_type == 'PARTNER':
                # بضاعة شريك - جلب الشركاء والنسب
                partners_result = connection.execute(
                    sa_text("""
                        SELECT partner_id, share_percent FROM product_partners
                        WHERE product_id = :pid
                        UNION
                        SELECT partner_id, share_percentage FROM warehouse_partner_shares
                        WHERE product_id = :pid AND warehouse_id = :wid
                    """),
                    {"pid": product_id, "wid": warehouse_id}
                ).fetchall()
                
                if partners_result:
                    # تقسيم الإيراد حسب النسب
                    total_partner_share = sum(float(p[1] or 0) for p in partners_result)
                    company_share_pct = 100.0 - total_partner_share
                    
                    # نصيب الشركة
                    if company_share_pct > 0:
                        total_revenue_company += line_total * (company_share_pct / 100.0)
                    
                    # نصيب الشركاء
                    for partner_id, share_pct in partners_result:
                        partner_amount = line_total * (float(share_pct or 0) / 100.0)
                        total_revenue_partners[partner_id] = total_revenue_partners.get(partner_id, 0.0) + partner_amount
                else:
                    # لا توجد نسب محددة - نعتبره 100% للشركة
                    total_revenue_company += line_total
            
            elif wh_type == 'EXCHANGE':
                # بضاعة عهدة - جلب المورد والتكلفة
                exchange_result = connection.execute(
                    sa_text("""
                        SELECT supplier_id, unit_cost
                        FROM exchange_transactions
                        WHERE product_id = :pid AND warehouse_id = :wid
                          AND supplier_id IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    """),
                    {"pid": product_id, "wid": warehouse_id}
                ).fetchone()
                
                if exchange_result:
                    supplier_id, unit_cost = exchange_result
                    cogs_amount = float(qty or 0) * float(unit_cost or 0)
                    
                    # الإيراد للشركة
                    total_revenue_company += line_total
                    
                    # COGS للمورد
                    total_cogs_suppliers[supplier_id] = total_cogs_suppliers.get(supplier_id, 0.0) + cogs_amount
                else:
                    # لا توجد معاملات عهدة - نعتبره MAIN
                    total_revenue_company += line_total
            
            else:  # MAIN أو غير محدد
                total_revenue_company += line_total
        
        # دائن: إيرادات الشركة
        if total_revenue_company > 0:
            entries.append((GL_ACCOUNTS.get("REV", "4000_SALES"), 0, total_revenue_company))
        
        # دائن: حسابات الشركاء (AP)
        for partner_id, amount in total_revenue_partners.items():
            if amount > 0:
                entries.append((GL_ACCOUNTS.get("AP", "2000_AP"), 0, amount))
        
        # مدين: COGS + دائن: حسابات الموردين (AP)
        for supplier_id, cogs in total_cogs_suppliers.items():
            if cogs > 0:
                entries.append((GL_ACCOUNTS.get("COGS", "5100_COGS"), cogs, 0))  # مدين
                entries.append((GL_ACCOUNTS.get("AP", "2000_AP"), 0, cogs))      # دائن
        
        customer_name = target.customer.name if target.customer else "عميل"
        memo = f"فاتورة مبيعات #{target.sale_number or target.id} - {customer_name}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="SALE",
            source_id=target.id,
            purpose="REVENUE",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=target.sale_number or f"SALE-{target.id}",
            entity_type="CUSTOMER",
            entity_id=target.customer_id
        )
    except Exception as e:
        # تسجيل الخطأ لكن عدم إيقاف العملية
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للبيع #{target.id}: {e}", file=sys.stderr)


@event.listens_for(Sale, "after_delete")
def _sale_gl_batch_delete(mapper, connection, target: "Sale"):
    """حذف GLBatch للبيع عند الحذف"""
    try:
        # حذف جميع GLBatch المرتبطة بالبيع
        connection.execute(
            sa_text("""
                DELETE FROM gl_batches
                WHERE source_type = 'SALE' AND source_id = :sid
            """),
            {"sid": target.id}
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في حذف GLBatch للبيع #{target.id}: {e}", file=sys.stderr)


class SaleLine(db.Model, TimestampMixin):
    __tablename__ = "sale_lines"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_rate = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    line_receiver = db.Column(db.String(200))  # مستلم البضاعة لهذا البند
    note = db.Column(db.String(200))  # ملاحظات البند

    sale = db.relationship("Sale", back_populates="lines")
    product = db.relationship("Product", back_populates="sale_lines")
    warehouse = db.relationship("Warehouse", back_populates="sale_lines")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="chk_sale_line_qty_positive"),
        db.CheckConstraint("unit_price >= 0", name="chk_sale_line_unit_price_non_negative"),
        db.CheckConstraint("discount_rate >= 0 AND discount_rate <= 100", name="chk_sale_line_discount_rate_range"),
        db.CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="chk_sale_line_tax_rate_range"),
        db.Index("ix_sale_line_sale", "sale_id"),
    )

    @hybrid_property
    def gross_amount(self):
        return D(self.unit_price) * D(self.quantity)

    @hybrid_property
    def discount_amount(self):
        return self.gross_amount * (D(self.discount_rate or 0) / Decimal("100"))

    @hybrid_property
    def net_amount(self):
        return self.gross_amount - self.discount_amount

    @hybrid_property
    def line_tax(self):
        return self.net_amount * (D(self.tax_rate or 0) / Decimal("100"))

    @hybrid_property
    def line_total(self):
        return self.net_amount + self.line_tax

    def __repr__(self):
        pname = getattr(self.product, "name", None)
        return f"<SaleLine {pname or self.product_id} in Sale {self.sale_id}>"

def _recompute_sale_total_amount(connection, sale_id: int):
    subtotal_float = connection.execute(
        select(
            func.coalesce(
                func.sum(
                    (SaleLine.quantity * SaleLine.unit_price)
                    * (1 - (func.coalesce(SaleLine.discount_rate, 0) / 100.0))
                ),
                0.0,
            )
        ).where(SaleLine.sale_id == sale_id)
    ).scalar_one() or 0.0
    tr, sh, disc = connection.execute(select(Sale.tax_rate, Sale.shipping_cost, Sale.discount_total).where(Sale.id == sale_id)).first()
    subtotal = Decimal(str(subtotal_float))
    tax_rate = Decimal(str(tr or 0))
    shipping = Decimal(str(sh or 0))
    discount = Decimal(str(disc or 0))
    base = subtotal - discount
    if base < Decimal("0"):
        base = Decimal("0")
    tax = (base * tax_rate / Decimal("100"))
    total = subtotal + tax + shipping - discount
    connection.execute(update(Sale).where(Sale.id == sale_id).values(total_amount=total, balance_due=(total - func.coalesce(Sale.total_paid, 0))))

@event.listens_for(SaleLine, "after_insert")
@event.listens_for(SaleLine, "after_update")
@event.listens_for(SaleLine, "after_delete")
def _sale_line_touch_sale_total(mapper, connection, target: "SaleLine"):
    sid = getattr(target, "sale_id", None)
    if sid:
        # تحديث أرصدة الشركاء/الموردين المرتبطين بالقطعة
        try:
            from sqlalchemy import text as sa_text
            pid = getattr(target, "product_id", None)
            if pid:
                # تحديث أرصدة الشركاء المرتبطين بهذه القطعة
                partner_results = connection.execute(
                    sa_text("""
                        SELECT DISTINCT partner_id 
                        FROM warehouse_partner_shares 
                        WHERE product_id = :pid
                        UNION
                        SELECT DISTINCT partner_id 
                        FROM product_partners 
                        WHERE product_id = :pid
                    """),
                    {"pid": pid}
                ).fetchall()
                
                for partner_row in partner_results:
                    if partner_row[0]:
                        update_partner_balance(partner_row[0], connection)
        except Exception as e:
            pass
    if sid:
        _recompute_sale_total_amount(connection, int(sid))

class SaleReturn(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "sale_returns"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    reason = db.Column(db.String(200))
    status = db.Column(sa_str_enum(["DRAFT","CONFIRMED","CANCELLED"], name="sale_return_status"), nullable=False, default="DRAFT", index=True)
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Numeric(12,2), nullable=False, default=0)
    currency = db.Column(db.String(10), nullable=False, default="ILS")
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    credit_note_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="SET NULL"), index=True)

    sale = db.relationship("Sale")
    customer = db.relationship("Customer")
    warehouse = db.relationship("Warehouse")
    credit_note = db.relationship("Invoice")
    lines = db.relationship("SaleReturnLine", back_populates="sale_return", cascade="all, delete-orphan", order_by="SaleReturnLine.id")

    __table_args__ = ()

class SaleReturnLine(db.Model):
    __tablename__ = "sale_return_lines"

    id = db.Column(db.Integer, primary_key=True)
    sale_return_id = db.Column(db.Integer, db.ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12,2), nullable=False, default=0)
    notes = db.Column(db.String(200))

    sale_return = db.relationship("SaleReturn", back_populates="lines")
    product = db.relationship("Product")
    warehouse = db.relationship("Warehouse")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sale_return_qty_pos"),
        db.CheckConstraint("unit_price >= 0", name="ck_sale_return_price_ge0"),
        db.Index("ix_sale_return_line_prod_wh", "product_id", "warehouse_id"),
    )

@event.listens_for(SaleReturnLine, "after_insert")
def _srl_after_insert(mapper, connection, t: "SaleReturnLine"):
    if t.warehouse_id:
        _apply_stock_delta(connection, t.product_id, t.warehouse_id, +int(t.quantity or 0))
    if t.sale_return_id:
        total = connection.execute(
            select(func.coalesce(func.sum(SaleReturnLine.quantity * SaleReturnLine.unit_price), 0)).where(SaleReturnLine.sale_return_id == t.sale_return_id)
        ).scalar_one() or 0
        connection.execute(update(SaleReturn).where(SaleReturn.id == t.sale_return_id).values(total_amount=q(total)))

@event.listens_for(SaleReturnLine, "after_delete")
def _srl_after_delete(mapper, connection, t: "SaleReturnLine"):
    if t.warehouse_id:
        _apply_stock_delta(connection, t.product_id, t.warehouse_id, -int(t.quantity or 0))
    if t.sale_return_id:
        total = connection.execute(
            select(func.coalesce(func.sum(SaleReturnLine.quantity * SaleReturnLine.unit_price), 0)).where(SaleReturnLine.sale_return_id == t.sale_return_id)
        ).scalar_one() or 0
        connection.execute(update(SaleReturn).where(SaleReturn.id == t.sale_return_id).values(total_amount=q(total)))

class Invoice(db.Model, TimestampMixin):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    invoice_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    due_date = Column(DateTime, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), index=True)
    service_id = Column(Integer, ForeignKey("service_requests.id"), index=True)
    preorder_id = Column(Integer, ForeignKey("preorders.id"), index=True)

    source = Column(sa_str_enum(InvoiceSource, name="invoice_source"), default=InvoiceSource.MANUAL.value, nullable=False, index=True)
    status = Column(sa_str_enum(InvoiceStatus, name="invoice_status"), default=InvoiceStatus.UNPAID.value, nullable=False, index=True)
    kind = Column(sa_str_enum(["INVOICE", "CREDIT_NOTE"], name="invoice_kind"), default="INVOICE", nullable=False, index=True)

    credit_for_id = Column(Integer, ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    refund_of_id = Column(Integer, ForeignKey("invoices.id", ondelete="SET NULL"), index=True)

    currency = Column(String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = Column(Numeric(10, 6))
    fx_rate_source = Column(String(20))
    fx_rate_timestamp = Column(DateTime)
    fx_base_currency = Column(String(10))
    fx_quote_currency = Column(String(10))
    
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(12, 2), default=0, nullable=False)
    notes = Column(Text)
    terms = Column(Text)

    refunded_total = Column(Numeric(12, 2), default=0, nullable=False)
    idempotency_key = Column(String(64), unique=True, index=True)
    cancelled_at = Column(DateTime, index=True)
    cancelled_by = Column(Integer, ForeignKey("users.id"), index=True)
    cancel_reason = Column(String(200))

    customer = relationship("Customer", back_populates="invoices", lazy="joined")
    supplier = relationship("Supplier", back_populates="invoices", lazy="joined")
    partner = relationship("Partner", back_populates="invoices", lazy="joined")
    sale = relationship("Sale", back_populates="invoice", uselist=False, lazy="joined")
    service = relationship("ServiceRequest", back_populates="invoice", lazy="joined")
    preorder = relationship("PreOrder", back_populates="invoice", lazy="joined")

    cancelled_by_user = relationship("User", foreign_keys=[cancelled_by], lazy="joined")

    refund_of = relationship("Invoice", remote_side=[id], foreign_keys=[refund_of_id], backref=db.backref("refunds", lazy="selectin"), lazy="joined")
    credit_for = relationship("Invoice", remote_side=[id], foreign_keys=[credit_for_id], backref=db.backref("credit_notes", lazy="selectin"), lazy="joined")

    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id", lazy="selectin")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True, order_by="Payment.id", lazy="selectin")

    gl_batches = relationship("GLBatch", primaryjoin="and_(foreign(GLBatch.source_id)==Invoice.id, GLBatch.source_type=='INVOICE')", viewonly=True, order_by="GLBatch.id", lazy="selectin")

    __table_args__ = ()

    @validates("source", "status", "kind")
    def _uppercase_enum(self, key, value):
        return getattr(value, "value", value).upper() if value else value

    @validates("currency")
    def _v_currency(self, _, v):
        return ensure_currency(v or "ILS")

    @validates("invoice_number")
    def _v_norm_number(self, _, v):
        s = (v or "").strip()
        s = re.sub(r"\s+", "", s)
        return s.upper() or None

    @hybrid_property
    def is_credit_note(self):
        k = getattr(self.kind, "value", self.kind)
        return (k or "").upper() == "CREDIT_NOTE"

    @hybrid_property
    def computed_total(self):
        return sum(D(l.line_total) for l in (self.lines or [])) if self.lines else Decimal("0.00")

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.invoice_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.IN.value,
            )
            .scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.invoice_id == cls.id)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (Payment.direction == PaymentDirection.IN.value)
            ).scalar_subquery()
        )

    @hybrid_property
    def balance_due(self):
        return float(q(self.total_amount or 0) - q(self.total_paid or 0))

    @hybrid_property
    def refundable_amount(self):
        return float(q(self.total_amount or 0) - q(self.refunded_total or 0))

    def apply_refund(self, amount):
        amt = q(amount or 0)
        if amt <= 0 or amt > q(self.refundable_amount):
            raise ValueError("invoice.refund_exceeds_allowed")
        self.refunded_total = q(self.refunded_total or 0) + amt

    def cancel(self, by_user_id: int | None = None, reason: str | None = None):
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancelled_by = by_user_id
        self.cancel_reason = (reason or None)
        self.status = InvoiceStatus.CANCELLED.value

    def update_status(self):
        if self.cancelled_at:
            self.status = InvoiceStatus.CANCELLED.value
        elif q(self.refunded_total or 0) >= q(self.total_amount or 0) and q(self.total_amount or 0) > 0:
            self.status = InvoiceStatus.REFUNDED.value
        elif q(self.balance_due) <= 0:
            self.status = InvoiceStatus.PAID.value
        elif q(self.total_paid) > 0:
            self.status = InvoiceStatus.PARTIAL.value
        else:
            self.status = InvoiceStatus.UNPAID.value

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"

class InvoiceLine(db.Model):
    __tablename__ = "invoice_lines"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), index=True)

    invoice = db.relationship("Invoice", back_populates="lines")
    product = db.relationship("Product")

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_invoice_line_quantity_non_negative"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_line_unit_price_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="ck_invoice_line_tax_rate_range"),
        CheckConstraint("discount >= 0 AND discount <= 100", name="ck_invoice_line_discount_range"),
    )

    @hybrid_property
    def line_total(self):
        gross = D(self.quantity) * D(self.unit_price)
        discount_amount = gross * (D(self.discount or 0) / Decimal("100.0"))
        taxable = gross - discount_amount
        tax_amount = taxable * (D(self.tax_rate or 0) / Decimal("100.0"))
        return taxable + tax_amount

@event.listens_for(Invoice, "before_insert")
def _invoice_normalize_and_total_insert(mapper, connection, target: "Invoice"):
    target.currency = ensure_currency(target.currency or "ILS")
    
    # حفظ سعر الصرف تلقائياً للفواتير (فقط عند الإنشاء)
    invoice_currency = target.currency
    default_currency = "ILS"
    
    if invoice_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(invoice_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = invoice_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass
    
    target.total_amount = q(target.total_amount or 0)
    target.tax_amount = q(target.tax_amount or 0)
    target.discount_amount = q(target.discount_amount or 0)
    target.refunded_total = q(target.refunded_total or 0)
    k = getattr(target, "kind", None)
    if hasattr(k, "value"):
        k = k.value
    target.kind = (k or "INVOICE").upper()


@event.listens_for(Invoice, "before_update")
def _invoice_normalize_and_total_update(mapper, connection, target: "Invoice"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = ensure_currency(target.currency or "ILS")
    target.total_amount = q(target.total_amount or 0)
    target.tax_amount = q(target.tax_amount or 0)
    target.discount_amount = q(target.discount_amount or 0)
    target.refunded_total = q(target.refunded_total or 0)
    k = getattr(target, "kind", None)
    if hasattr(k, "value"):
        k = k.value
    target.kind = (k or "INVOICE").upper()
    s = getattr(target, "status", None)
    if hasattr(s, "value"):
        s = s.value
    target.status = (s or InvoiceStatus.UNPAID.value).upper()
    src = getattr(target, "source", None)
    if hasattr(src, "value"):
        src = src.value
    target.source = (src or InvoiceSource.MANUAL.value).upper()

def _recompute_invoice_totals(connection, invoice_id: int):
    gross_before_disc = func.coalesce(func.sum(InvoiceLine.quantity * InvoiceLine.unit_price), 0.0)
    disc_amount = func.coalesce(func.sum((InvoiceLine.quantity * InvoiceLine.unit_price) * (func.coalesce(InvoiceLine.discount, 0) / 100.0)), 0.0)
    taxable = gross_before_disc - disc_amount
    tax = func.coalesce(
        func.sum(((InvoiceLine.quantity * InvoiceLine.unit_price) * (1 - (func.coalesce(InvoiceLine.discount, 0) / 100.0))) * (func.coalesce(InvoiceLine.tax_rate, 0) / 100.0)),
        0.0,
    )
    total_expr = taxable + tax
    connection.execute(update(Invoice).where(Invoice.id == invoice_id).values(total_amount=total_expr, tax_amount=tax, discount_amount=disc_amount))

@event.listens_for(Invoice, "after_insert")
@event.listens_for(Invoice, "after_update")
def _inv_touch_totals(mapper, connection, target: "Invoice"):
    if target.id:
        _recompute_invoice_totals(connection, int(target.id))

@event.listens_for(InvoiceLine, "after_insert")
@event.listens_for(InvoiceLine, "after_update")
@event.listens_for(InvoiceLine, "after_delete")
def _inv_line_touch_invoice(mapper, connection, target: "InvoiceLine"):
    if target.invoice_id:
        _recompute_invoice_totals(connection, int(target.invoice_id))

class ProductSupplierLoan(db.Model, TimestampMixin):
    __tablename__ = 'product_supplier_loans'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)

    loan_value = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    deferred_price = db.Column(db.Numeric(12, 2))
    is_settled = db.Column(db.Boolean, default=False, index=True)

    partner_share_quantity = db.Column(db.Integer, default=0, nullable=False)
    partner_share_value = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    notes = db.Column(db.Text)

    product = db.relationship('Product', back_populates='supplier_loans')
    supplier = db.relationship('Supplier', backref='loaned_products')
    settlements = db.relationship('SupplierLoanSettlement', back_populates='loan', cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint('loan_value >= 0', name='ck_psl_loan_value_ge_0'),
        db.CheckConstraint('deferred_price IS NULL OR deferred_price >= 0', name='ck_psl_deferred_price_ge_0'),
        db.CheckConstraint('partner_share_quantity >= 0', name='ck_psl_share_qty_ge_0'),
        db.CheckConstraint('partner_share_value >= 0', name='ck_psl_share_val_ge_0'),
        db.Index('ix_psl_product_supplier', 'product_id', 'supplier_id'),
        db.Index('ix_psl_supplier_settled', 'supplier_id', 'is_settled'),
    )

    @validates('loan_value', 'deferred_price', 'partner_share_value')
    def _v_money(self, _, v):
        if v in (None, ''):
            return None
        d = Decimal(str(v))
        if d < 0:
            raise ValueError("monetary values must be >= 0")
        return d

    @validates('partner_share_quantity')
    def _v_share_qty(self, _, v):
        iv = int(v or 0)
        if iv < 0:
            raise ValueError("partner_share_quantity must be >= 0")
        return iv

    @validates('notes')
    def _v_notes(self, _, v):
        return (str(v).strip() or None) if v is not None else None

    @hybrid_property
    def effective_price(self):
        v = self.deferred_price if self.deferred_price not in (None, 0) else self.loan_value
        if not v or v <= 0:
            pp = getattr(self.product, 'purchase_price', 0) or 0
            return float(pp or 0)
        return float(v)

    @hybrid_property
    def outstanding_value(self):
        return 0.0 if bool(self.is_settled) else float(self.effective_price or 0)

    def mark_settled(self, final_price: Decimal | float | int):
        self.deferred_price = Decimal(str(final_price))
        self.is_settled = True

    def __repr__(self):
        return f"<ProductSupplierLoan P{self.product_id}-S{self.supplier_id}>"

@event.listens_for(ProductSupplierLoan, 'before_insert')
def _psl_before_insert(mapper, connection, target: 'ProductSupplierLoan'):
    if not target.loan_value or Decimal(str(target.loan_value)) <= 0:
        prod = db.session.get(Product, target.product_id) if target.product_id else None
        pp = getattr(prod, 'purchase_price', 0) or 0
        target.loan_value = Decimal(str(pp or 0))
    if target.deferred_price is not None and Decimal(str(target.deferred_price)) >= 0:
        target.is_settled = True
    target.partner_share_quantity = int(target.partner_share_quantity or 0)
    target.partner_share_value = Decimal(str(target.partner_share_value or 0))

@event.listens_for(ProductSupplierLoan, 'before_update')
def _psl_before_update(mapper, connection, target: 'ProductSupplierLoan'):
    if not target.loan_value or Decimal(str(target.loan_value)) <= 0:
        prod = db.session.get(Product, target.product_id) if target.product_id else None
        pp = getattr(prod, 'purchase_price', 0) or 0
        target.loan_value = Decimal(str(pp or 0))
    if target.deferred_price is not None and Decimal(str(target.deferred_price)) >= 0:
        target.is_settled = True
    target.partner_share_quantity = int(target.partner_share_quantity or 0)
    target.partner_share_value = Decimal(str(target.partner_share_value or 0))

class Payment(db.Model):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), unique=True, nullable=False, index=True)
    payment_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    subtotal = Column(Numeric(12, 2))
    tax_rate = Column(Numeric(5, 2))
    tax_amount = Column(Numeric(12, 2))
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = Column(Numeric(10, 6))  # السعر المستخدم في التحويل
    fx_rate_source = Column(String(20))    # مصدر السعر (online, manual, default)
    fx_rate_timestamp = Column(DateTime)   # وقت الحصول على السعر
    fx_base_currency = Column(String(10))  # العملة الأساسية
    fx_quote_currency = Column(String(10))  # العملة المقابلة

    method = Column(sa_str_enum(PaymentMethod, name="payment_method"), nullable=False, index=True)
    status = Column(sa_str_enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING.value, nullable=False, index=True)
    direction = Column(sa_str_enum(PaymentDirection, name="payment_direction"), default=PaymentDirection.IN.value, nullable=False, index=True)
    entity_type = Column(sa_str_enum(PaymentEntityType, name="payment_entity_type"), default=PaymentEntityType.CUSTOMER.value, nullable=False, index=True)

    reference = Column(String(100))
    receipt_number = Column(String(50), unique=True, index=True)
    notes = Column(Text)
    receiver_name = Column(String(200))  # اسم مستلم الدفعة

    check_number = Column(String(100))
    check_bank = Column(String(100))
    check_due_date = Column(DateTime)
    card_holder = Column(String(100))
    card_expiry = Column(String(10))
    card_last4 = Column(String(4))
    bank_transfer_ref = Column(String(100))

    created_by = Column(Integer, ForeignKey("users.id"), index=True)
    creator = relationship("User", backref="payments_created", foreign_keys=[created_by])

    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="CASCADE"), index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), index=True)
    loan_settlement_id = Column(Integer, ForeignKey("supplier_loan_settlements.id", ondelete="CASCADE"), index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    preorder_id = Column(Integer, ForeignKey("preorders.id", ondelete="CASCADE"), index=True)
    service_id = Column(Integer, ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)

    refund_of_id = Column(Integer, ForeignKey("payments.id", ondelete="SET NULL"), index=True)
    idempotency_key = Column(String(64), unique=True, index=True)
    
    # حقول الأرشيف
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    archived_at = Column(DateTime, index=True)
    archived_by = Column(Integer, ForeignKey("users.id"), index=True)
    archive_reason = Column(String(200))

    customer = relationship("Customer", back_populates="payments")
    supplier = relationship("Supplier", back_populates="payments")
    partner = relationship("Partner", back_populates="payments")
    shipment = relationship("Shipment", back_populates="payments")
    expense = relationship("Expense", back_populates="payments")
    loan_settlement = relationship("SupplierLoanSettlement", back_populates="payment")
    sale = relationship("Sale", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    preorder = relationship("PreOrder", back_populates="payments")
    service = relationship("ServiceRequest", back_populates="payments")
    refund_of = relationship("Payment", remote_side=[id])
    archived_by_user = relationship("User", foreign_keys=[archived_by])

    splits = relationship("PaymentSplit", back_populates="payment", cascade="all,delete-orphan", passive_deletes=True, order_by="PaymentSplit.id")

    gl_batches = relationship(
        "GLBatch",
        primaryjoin="and_(foreign(GLBatch.source_id)==Payment.id, GLBatch.source_type=='PAYMENT')",
        viewonly=True,
        order_by="GLBatch.id",
    )

    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_payment_total_positive"),
        CheckConstraint("""(
            (CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN supplier_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN partner_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN shipment_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN expense_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN loan_settlement_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN sale_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN invoice_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN preorder_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN service_id IS NOT NULL THEN 1 ELSE 0 END)
        ) = 1""", name="ck_payment_one_target"),
        db.Index("ix_pay_sale_status_dir", "sale_id", "status", "direction"),
        db.Index("ix_pay_inv_status_dir", "invoice_id", "status", "direction"),
        db.Index("ix_pay_supplier_status_dir", "supplier_id", "status", "direction"),
        db.Index("ix_pay_partner_status_dir", "partner_id", "status", "direction"),
        db.Index("ix_pay_preorder_status_dir", "preorder_id", "status", "direction"),
        db.Index("ix_pay_reversal", "refund_of_id"),
        db.Index("ix_pay_dir_stat_type", "direction", "status", "entity_type"),
        db.Index("ix_pay_status", "status"),
        db.Index("ix_pay_direction", "direction"),
        db.Index("ix_pay_currency", "currency"),
        db.Index("ix_pay_created_at", "payment_date"),
    )

    @property
    def entity(self):
        for attr in ("customer", "supplier", "partner", "shipment", "expense", "loan_settlement", "sale", "invoice", "preorder", "service"):
            if getattr(self, f"{attr}_id", None):
                obj = getattr(self, attr, None)
                if obj is not None:
                    return obj
                raise ValueError("Bad link")
        raise ValueError("No link")

    def entity_label(self):
        if self.customer: return f"العميل: {self.customer.name}"
        if self.supplier: return f"المورد: {self.supplier.name}"
        if self.partner: return f"الشريك: {self.partner.name}"
        if self.invoice: return f"فاتورة #{self.invoice.invoice_number or self.invoice.id}"
        if self.sale: return f"فاتورة مبيعات #{self.sale.sale_number or self.sale.id}"
        if self.shipment: return f"شحنة #{self.shipment.shipment_number or self.shipment.id}"
        if self.service: return f"طلب صيانة #{self.service.service_number or self.service.id}"
        if self.preorder: return f"طلب مسبق #{self.preorder.reference or self.preorder.id}"
        if self.expense: return f"مصروف #{self.expense.id}"
        if self.loan_settlement: return f"تسوية قرض #{self.loan_settlement.id}"
        return "غير مرتبط"

    @validates("payment_number", "receipt_number")
    def _v_norm_numbers(self, _, v):
        s = (v or "").strip()
        s = re.sub(r"\s+", "", s)
        return s.upper() or None

    @validates("subtotal", "tax_rate", "tax_amount", "total_amount")
    def _v_amounts(self, key, value):
        if value is None:
            return None if key in ("subtotal", "tax_rate", "tax_amount") else D("0.00")
        v = q(value)
        if key == "tax_rate" and (v < 0 or v > 100):
            raise ValueError("invalid tax_rate")
        if key in ("subtotal", "tax_amount") and v < 0:
            raise ValueError(f"{key} must be >= 0")
        if key == "total_amount" and v <= 0:
            raise ValueError("total_amount must be > 0")
        return v

    @validates("method", "status", "direction", "entity_type")
    def _coerce_enums(self, key, value):
        return getattr(value, "value", value) if value else None

    @validates("currency")
    def _v_payment_currency(self, key, v):
        return ensure_currency((v or "ILS"))

    def to_dict(self):
        _v = lambda x: getattr(x, "value", x)
        _f = lambda x: float(q(x or 0))
        return {
            "id": self.id,
            "payment_number": self.payment_number,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "subtotal": _f(self.subtotal),
            "tax_rate": _f(self.tax_rate),
            "tax_amount": _f(self.tax_amount),
            "total_amount": _f(self.total_amount),
            "currency": self.currency,
            "method": _v(self.method),
            "status": _v(self.status),
            "direction": _v(self.direction),
            "entity_type": _v(self.entity_type),
            "entity_display": self.entity_label(),
            "reference": self.reference,
            "receipt_number": self.receipt_number,
            "notes": self.notes,
            "created_by": self.created_by,
            "customer_id": self.customer_id,
            "supplier_id": self.supplier_id,
            "partner_id": self.partner_id,
            "shipment_id": self.shipment_id,
            "expense_id": self.expense_id,
            "loan_settlement_id": self.loan_settlement_id,
            "sale_id": self.sale_id,
            "invoice_id": self.invoice_id,
            "preorder_id": self.preorder_id,
            "service_id": self.service_id,
            "refund_of_id": self.refund_of_id,
            "idempotency_key": self.idempotency_key,
            "splits": [s.to_dict() for s in self.splits or []],
        }

    def __repr__(self):
        return f"<Payment {self.payment_number or self.id} - {self.total_amount} {self.currency}>"


def _payment_target_fk_for_type(et: str) -> str | None:
    m = {
        "CUSTOMER": "customer_id",
        "SUPPLIER": "supplier_id",
        "PARTNER": "partner_id",
        "SHIPMENT": "shipment_id",
        "EXPENSE": "expense_id",
        "LOAN": "loan_settlement_id",
        "SALE": "sale_id",
        "INVOICE": "invoice_id",
        "PREORDER": "preorder_id",
        "SERVICE": "service_id",
    }
    return m.get((et or "").upper())


def _payment_detect_entity_type(target: "Payment") -> str | None:
    pairs = [
        ("CUSTOMER", target.customer_id),
        ("SUPPLIER", target.supplier_id),
        ("PARTNER", target.partner_id),
        ("SHIPMENT", target.shipment_id),
        ("EXPENSE", target.expense_id),
        ("LOAN", target.loan_settlement_id),
        ("SALE", target.sale_id),
        ("INVOICE", target.invoice_id),
        ("PREORDER", target.preorder_id),
        ("SERVICE", target.service_id),
    ]
    for et, vid in pairs:
        if vid:
            return et
    return None


_ALLOWED_TRANSITIONS = {
    "PENDING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": {"REFUNDED"},
    "FAILED": set(),
    "CANCELLED": set(),
    "REFUNDED": set(),
}


def _payment_enforce_transition(old: str | None, new: str) -> None:
    o = (old or "PENDING").upper()
    n = (new or "").upper()
    if o == n:
        return
    allowed = _ALLOWED_TRANSITIONS.get(o, set())
    if n not in allowed:
        raise ValueError("payment.invalid_status_transition")


def _payment_entity_id_for(target: "Payment") -> int:
    et = (getattr(target, "entity_type", "") or "").upper()
    fk = _payment_target_fk_for_type(et)
    if fk:
        return int(getattr(target, fk) or 0)
    return 0


# ═══════════════════════════════════════════════════════════════════════
# 📊 Accounting Listeners - إنشاء GLBatch تلقائي للدفعات
# ═══════════════════════════════════════════════════════════════════════

@event.listens_for(Payment, "after_insert")
@event.listens_for(Payment, "after_update")
def _payment_gl_batch_upsert(mapper, connection, target: "Payment"):
    """إنشاء/تحديث GLBatch للدفعة تلقائياً"""
    # ✅ التعامل مع الحالات المختلفة:
    # PENDING (شيك معلق) → قيد: شيكات تحت التحصيل ↔ AR
    # COMPLETED → قيد: بنك/صندوق ↔ AR (للنقد) أو تحديث الشيك (للشيك)
    # BOUNCED/FAILED → حذف القيد (إلغاء)
    
    # إذا الدفعة ملغاة أو مرفوضة، حذف أي GLBatch موجود
    if target.status in [PaymentStatus.FAILED.value, PaymentStatus.BOUNCED.value, PaymentStatus.CANCELLED.value]:
        try:
            connection.execute(
                sa_text("""
                    DELETE FROM gl_batches
                    WHERE source_type = 'PAYMENT' AND source_id = :sid
                """),
                {"sid": target.id}
            )
        except:
            pass
        return
    
    # ✅ للشيكات المعلقة: إنشاء قيد في "شيكات تحت التحصيل"
    # للدفعات المكتملة: إنشاء قيد عادي في البنك/الصندوق
    if target.status not in [PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value]:
        return
    
    # ✅ فحص إذا كانت شيك معلق
    is_pending_check = (target.status == PaymentStatus.PENDING.value and 
                       target.method == PaymentMethod.CHEQUE.value)
    
    try:
        from models import fx_rate
        
        # تحويل المبلغ للشيقل
        amount = float(target.total_amount or 0)
        if amount <= 0:
            return
        
        # تحويل العملة
        amount_ils = amount
        if target.currency and target.currency != 'ILS':
            try:
                rate = fx_rate(target.currency, 'ILS', target.payment_date or datetime.utcnow(), raise_on_missing=False)
                if rate and rate > 0:
                    amount_ils = float(amount * float(rate))
            except:
                pass
        
        # تحديد الحساب النقدي حسب طريقة الدفع والحالة
        # ✅ للشيكات المعلقة: استخدام "شيكات تحت التحصيل" (وارد) أو "شيكات مستحقة" (صادر)
        # ✅ للدفعات المكتملة: استخدام البنك/الصندوق
        if is_pending_check:
            # تحديد حسب الاتجاه
            if target.direction == PaymentDirection.IN.value:
                cash_account = "1150_CHEQUES_RECEIVABLE"  # شيكات تحت التحصيل (أصل)
            else:
                cash_account = "2150_CHEQUES_PAYABLE"  # شيكات مستحقة الدفع (خصم)
        elif target.method == PaymentMethod.BANK.value:
            cash_account = GL_ACCOUNTS.get("BANK", "1010_BANK")
        elif target.method == PaymentMethod.CARD.value:
            cash_account = GL_ACCOUNTS.get("CARD", "1020_CARD_CLEARING")
        else:
            cash_account = GL_ACCOUNTS.get("CASH", "1000_CASH")
        
        # تحديد الحساب الآخر حسب نوع الكيان
        entity_account = GL_ACCOUNTS.get("AR", "1100_AR")  # افتراضي للعملاء
        entity_name = "عميل"
        
        if target.entity_type == PaymentEntityType.SUPPLIER.value or target.supplier_id:
            entity_account = GL_ACCOUNTS.get("AP", "2000_AP")
            entity_name = "مورد"
        elif target.entity_type == PaymentEntityType.PARTNER.value or target.partner_id:
            entity_account = GL_ACCOUNTS.get("AP", "2000_AP")  # الشركاء يُعاملون كـ AP
            entity_name = "شريك"
        elif target.entity_type == PaymentEntityType.EXPENSE.value or target.expense_id:
            entity_account = GL_ACCOUNTS.get("EXP", "5000_EXPENSES")
            entity_name = "مصروف"
        
        # القيد المحاسبي حسب الاتجاه:
        # IN (وارد): مدين النقدية/الشيكات، دائن العميل/المورد
        # OUT (صادر): مدين العميل/المورد، دائن النقدية/الشيكات
        if target.direction == PaymentDirection.IN.value:
            entries = [
                (cash_account, amount_ils, 0),  # مدين: النقدية أو شيكات تحت التحصيل
                (entity_account, 0, amount_ils),  # دائن: العميل/المورد
            ]
            if is_pending_check:
                memo = f"شيك معلق من {entity_name} - {target.check_number or target.payment_number or target.id}"
            else:
                memo = f"قبض من {entity_name} - {target.payment_number or target.id}"
        else:  # OUT
            entries = [
                (entity_account, amount_ils, 0),  # مدين: العميل/المورد
                (cash_account, 0, amount_ils),  # دائن: النقدية أو شيكات مستحقة
            ]
            if is_pending_check:
                memo = f"شيك صادر لـ {entity_name} - {target.check_number or target.payment_number or target.id}"
            else:
                memo = f"سداد لـ {entity_name} - {target.payment_number or target.id}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="PAYMENT",
            source_id=target.id,
            purpose="PAYMENT",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=target.payment_number or f"PMT-{target.id}",
            entity_type=target.entity_type,
            entity_id=_payment_entity_id_for(target)
        )
    except Exception as e:
        # تسجيل الخطأ لكن عدم إيقاف العملية
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للدفعة #{target.id}: {e}", file=sys.stderr)


@event.listens_for(Payment, "after_delete")
def _payment_gl_batch_delete(mapper, connection, target: "Payment"):
    """حذف GLBatch للدفعة عند الحذف"""
    try:
        # حذف جميع GLBatch المرتبطة بالدفعة
        connection.execute(
            sa_text("""
                DELETE FROM gl_batches
                WHERE source_type = 'PAYMENT' AND source_id = :sid
            """),
            {"sid": target.id}
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في حذف GLBatch للدفعة #{target.id}: {e}", file=sys.stderr)


@event.listens_for(Payment, "after_insert", propagate=True)
def _payment_create_check_auto(mapper, connection, target: "Payment"):
    """✅ إنشاء سجل Check تلقائياً عند إنشاء دفعة بطريقة شيك"""
    try:
        # فحص طريقة الدفع
        method_str = str(getattr(target, 'method', '')).upper()
        if 'CHECK' not in method_str and 'CHEQUE' not in method_str:
            return
        
        # فحص معلومات الشيك
        check_number = (getattr(target, 'check_number', None) or '').strip()
        check_bank = (getattr(target, 'check_bank', None) or '').strip()
        
        if not check_number or not check_bank:
            return
        
        # تحويل check_due_date
        check_due_date = getattr(target, 'check_due_date', None)
        if not check_due_date:
            payment_date = getattr(target, 'payment_date', None)
            check_due_date = payment_date or datetime.now(timezone.utc)
        
        # التحقق من created_by_id
        created_by_id = getattr(target, 'created_by', None)
        if not created_by_id or created_by_id == 0:
            # جلب أول مستخدم كـ fallback
            from models import User
            first_user_result = connection.execute(
                sa_text("SELECT id FROM users ORDER BY id LIMIT 1")
            ).scalar()
            created_by_id = first_user_result if first_user_result else 1
        
        # إنشاء سجل الشيك
        connection.execute(
            Check.__table__.insert().values(
                check_number=check_number,
                check_bank=check_bank,
                check_date=getattr(target, 'payment_date', None) or datetime.now(timezone.utc),
                check_due_date=check_due_date,
                amount=float(getattr(target, 'total_amount', 0) or 0),
                currency=(getattr(target, 'currency', None) or 'ILS').upper(),
                direction=str(getattr(target, 'direction', 'IN')).upper(),
                status='PENDING',
                customer_id=getattr(target, 'customer_id', None),
                supplier_id=getattr(target, 'supplier_id', None),
                partner_id=getattr(target, 'partner_id', None),
                reference_number=f"PMT-{target.id}",
                notes=f"شيك من دفعة رقم {getattr(target, 'payment_number', None) or target.id}",
                created_by_id=created_by_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        )
        
        import sys
        print(f"✅ تم إنشاء سجل شيك رقم {check_number} من دفعة #{target.id}", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"⚠️ فشل إنشاء سجل شيك من دفعة #{target.id}: {str(e)}", file=sys.stderr)


class PaymentSplit(db.Model):
    __tablename__ = "payment_splits"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    method = Column(sa_str_enum(PaymentMethod, name="split_payment_method"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    details = Column(db.JSON, default=dict, nullable=False)

    payment = relationship("Payment", back_populates="splits")

    __table_args__ = (CheckConstraint("amount > 0", name="chk_split_amount_positive"),)

    def clean_details(self):
        if not isinstance(self.details, dict):
            try:
                if isinstance(self.details, str):
                    self.details = json.loads(self.details)
                else:
                    self.details = {}
            except Exception:
                self.details = {}
        self.details = {k: v for k, v in self.details.items() if v not in (None, "", [])}

    def label(self):
        self.clean_details()
        m = getattr(self.method, "value", self.method)
        names = {
            PaymentMethod.CASH.value: "نقدًا",
            PaymentMethod.CHEQUE.value: "شيك",
            PaymentMethod.CARD.value: "بطاقة",
            PaymentMethod.BANK.value: "تحويل بنكي",
            PaymentMethod.ONLINE.value: "دفع إلكتروني",
        }
        return f"{names.get(m, m)} - {q(self.amount):,.2f}"

    def __repr__(self):
        return f"<PaymentSplit {self.label()}>"

    def to_dict(self):
        self.clean_details()
        return {
            "id": self.id,
            "payment_id": self.payment_id,
            "method": getattr(self.method, "value", self.method),
            "amount": float(q(self.amount)),
            "details": self.details,
            "label": self.label(),
        }


def _next_payment_number(connection) -> str:
    prefix = datetime.now(timezone.utc).strftime("PMT%Y%m%d")
    # استخدام MAX بدلاً من COUNT لتجنب التكرار
    result = connection.execute(
        sa_text("SELECT payment_number FROM payments WHERE payment_number LIKE :pfx ORDER BY payment_number DESC LIMIT 1"), 
        {"pfx": f"{prefix}-%"}
    ).scalar()
    
    if result:
        # استخراج الرقم الأخير وزيادته
        try:
            last_num = int(result.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    
    # محاولة إنشاء رقم فريد، وفي حالة الفشل نحاول حتى نجد رقم متاح
    max_attempts = 100
    for attempt in range(max_attempts):
        candidate = f"{prefix}-{next_num:04d}"
        # التحقق من عدم وجود الرقم
        exists = connection.execute(
            sa_text("SELECT 1 FROM payments WHERE payment_number = :num LIMIT 1"),
            {"num": candidate}
        ).scalar()
        if not exists:
            return candidate
        next_num += 1
    
    # في حالة الفشل، استخدم timestamp
    import time
    return f"{prefix}-{int(time.time() * 1000) % 10000:04d}"


@event.listens_for(Payment, "before_insert")
@event.listens_for(Payment, "before_update")
def _payment_policy_shipment(mapper, connection, t: "Payment"):
    et = getattr(t, "entity_type", None)
    if hasattr(et, "value"):
        et = et.value
    if (et or "").upper() != "SHIPMENT":
        return
    if not getattr(t, "shipment_id", None):
        raise ValueError("shipment_id مطلوب عند entity_type=SHIPMENT")
    dirv = getattr(t, "direction", None)
    if hasattr(dirv, "value"):
        dirv = dirv.value
    dirv = (dirv or "").upper()
    if dirv == "OUT":
        return
    if dirv == "IN":
        ref = (getattr(t, "reference", None) or "").strip()
        notes = (getattr(t, "notes", None) or "").strip()
        if not (ref or notes):
            raise ValueError("لا يُسمح بقبض لشحنة إلا كتعويض/استرداد مع توثيق السبب في reference أو notes")
        return
    raise ValueError("اتجاه غير مسموح لدفعات الشحن")


@event.listens_for(Payment, "before_insert", propagate=True)
def _payment_before_insert(mapper, connection, target: "Payment"):
    if not getattr(target, "payment_number", None):
        target.payment_number = _next_payment_number(connection)
    for k in ("method", "status", "direction", "entity_type"):
        v = getattr(target, k, None)
        if v is not None:
            setattr(target, k, getattr(v, "value", v))
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    
    # حفظ سعر الصرف المستخدم تلقائياً (فقط عند الإنشاء)
    payment_currency = target.currency
    default_currency = "ILS"
    
    if payment_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(payment_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = payment_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass
    
    detected = _payment_detect_entity_type(target)
    if detected:
        target.entity_type = detected
    et = target.entity_type
    eid = _payment_entity_id_for(target)
    validate_payment_policies(
        entity_type=et,
        entity_id=eid,
        direction=getattr(target, "direction", PaymentDirection.IN),
        amount=getattr(target, "total_amount", 0),
        currency=getattr(target, "currency", "ILS"),
    )


@event.listens_for(Payment, "before_update", propagate=True)
def _payment_before_update(mapper, connection, target: "Payment"):
    from sqlalchemy.orm.attributes import get_history
    for k in ("method", "status", "direction", "entity_type"):
        v = getattr(target, k, None)
        if v is not None:
            setattr(target, k, getattr(v, "value", v))
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    detected = _payment_detect_entity_type(target)
    if detected:
        target.entity_type = detected
    h = get_history(target, "status")
    prev = (h.deleted[0] if h.deleted else getattr(target, "status", None))
    _payment_enforce_transition(prev, getattr(target, "status", None))
    et = target.entity_type
    eid = _payment_entity_id_for(target)
    validate_payment_policies(
        entity_type=et,
        entity_id=eid,
        direction=getattr(target, "direction", PaymentDirection.IN),
        amount=getattr(target, "total_amount", 0),
        currency=getattr(target, "currency", "ILS"),
    )


@event.listens_for(Payment, "before_insert")
@event.listens_for(Payment, "before_update")
def _payment_refund_guard(mapper, connection, t: "Payment"):
    rid = getattr(t, "refund_of_id", None)
    if not rid:
        return
    row = connection.execute(
        sa_text("""
            SELECT id, total_amount, currency, direction, entity_type,
                   customer_id, supplier_id, partner_id, shipment_id,
                   expense_id, loan_settlement_id, sale_id, invoice_id,
                   preorder_id, service_id
              FROM payments
             WHERE id = :rid
        """),
        {"rid": rid},
    ).mappings().first()
    if not row:
        raise ValueError("دفعة الأصل غير موجودة للاسترداد")
    if (row["currency"] or "").upper() != (getattr(t, "currency", None) or "ILS").upper():
        raise ValueError("عملة الاسترداد يجب أن تطابق دفعة الأصل")
    dirv = (getattr(t, "direction", "") or "")
    if hasattr(dirv, "value"):
        dirv = dirv.value
    dirv = dirv.upper()
    orig_dir = (row["direction"] or "").upper()
    if orig_dir == "IN" and dirv != "OUT":
        raise ValueError("استرداد دفعة IN يجب أن يكون OUT")
    if orig_dir == "OUT" and dirv != "IN":
        raise ValueError("استرداد دفعة OUT يجب أن يكون IN")
    for fk in ("customer_id","supplier_id","partner_id","shipment_id","expense_id","loan_settlement_id","sale_id","invoice_id","preorder_id","service_id"):
        if getattr(t, fk) != row[fk]:
            raise ValueError("هدف الاسترداد يجب أن يطابق دفعة الأصل")
    used = connection.execute(
        sa_text("""
            SELECT COALESCE(SUM(total_amount),0) AS s
              FROM payments
             WHERE refund_of_id = :rid
               AND id <> COALESCE(:cid, -1)
               AND status IN ('PENDING','COMPLETED')
        """),
        {"rid": rid, "cid": getattr(t, "id", None)},
    ).scalar() or 0
    if Decimal(str(used)) + Decimal(str(t.total_amount or 0)) - Decimal(str(row["total_amount"])) > Decimal("0"):
        raise ValueError("قيمة الاسترداد تتجاوز المبلغ الأصلي")


@event.listens_for(PaymentSplit, "before_insert", propagate=True)
@event.listens_for(PaymentSplit, "before_update", propagate=True)
def _split_before_save(mapper, connection, target: "PaymentSplit"):
    target.amount = q(target.amount)
    m = getattr(target, "method", None)
    if hasattr(m, "value"):
        target.method = m.value
    if not isinstance(target.details, dict) or target.details is None:
        target.details = {}
    else:
        target.details = {k: v for k, v in target.details.items() if v not in (None, "", [])}


@event.listens_for(PaymentSplit, "after_insert", propagate=True)
def _payment_split_create_check_auto(mapper, connection, target: "PaymentSplit"):
    """✅ إنشاء سجل Check تلقائياً عند إنشاء دفعة جزئية بطريقة شيك"""
    try:
        # فحص طريقة الدفع
        method_str = str(getattr(target, 'method', '')).upper()
        if 'CHECK' not in method_str and 'CHEQUE' not in method_str:
            return
        
        # جلب معلومات الشيك من details
        details = getattr(target, 'details', {}) or {}
        if not isinstance(details, dict):
            try:
                import json
                details = json.loads(details) if isinstance(details, str) else {}
            except:
                details = {}
        
        check_number = (details.get('check_number', '') or '').strip()
        check_bank = (details.get('check_bank', '') or '').strip()
        
        if not check_number or not check_bank:
            return
        
        # جلب معلومات الدفعة الأصلية
        payment_row = connection.execute(
            sa_text("""
                SELECT id, payment_number, payment_date, currency, direction, 
                       customer_id, supplier_id, partner_id, created_by
                FROM payments 
                WHERE id = :pid
            """),
            {"pid": target.payment_id}
        ).mappings().first()
        
        if not payment_row:
            return
        
        # تحويل check_due_date
        check_due_date_raw = details.get('check_due_date')
        check_due_date = None
        
        if check_due_date_raw:
            try:
                if isinstance(check_due_date_raw, str):
                    from dateutil import parser as date_parser
                    check_due_date = date_parser.isoparse(check_due_date_raw)
                else:
                    check_due_date = check_due_date_raw
            except:
                pass
        
        if not check_due_date:
            check_due_date = payment_row['payment_date'] or datetime.now(timezone.utc)
        
        # التحقق من created_by_id
        created_by_id = payment_row['created_by']
        if not created_by_id or created_by_id == 0:
            first_user_result = connection.execute(
                sa_text("SELECT id FROM users ORDER BY id LIMIT 1")
            ).scalar()
            created_by_id = first_user_result if first_user_result else 1
        
        # إنشاء سجل الشيك
        connection.execute(
            Check.__table__.insert().values(
                check_number=check_number,
                check_bank=check_bank,
                check_date=payment_row['payment_date'] or datetime.now(timezone.utc),
                check_due_date=check_due_date,
                amount=float(getattr(target, 'amount', 0) or 0),
                currency=(payment_row['currency'] or 'ILS').upper(),
                direction=str(payment_row['direction'] or 'IN').upper(),
                status='PENDING',
                customer_id=payment_row['customer_id'],
                supplier_id=payment_row['supplier_id'],
                partner_id=payment_row['partner_id'],
                reference_number=f"PMT-SPLIT-{target.id}",
                notes=f"شيك من دفعة جزئية #{target.id} - دفعة رقم {payment_row['payment_number']}",
                created_by_id=created_by_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        )
        
        import sys
        print(f"✅ تم إنشاء سجل شيك رقم {check_number} من دفعة جزئية #{target.id}", file=sys.stderr)
    except Exception as e:
        import sys
        import traceback
        print(f"⚠️ فشل إنشاء سجل شيك من دفعة جزئية #{target.id}: {str(e)}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)


# ===== تحديث total_paid و balance_due في Sales تلقائياً =====
def _update_sale_payment_totals(connection, sale_id):
    """تحديث total_paid و balance_due في جدول Sales"""
    if not sale_id:
        return
    
    # حساب total_paid من جدول Payments
    total_paid_result = connection.execute(
        sa_text("""
            SELECT COALESCE(SUM(total_amount), 0) 
            FROM payments 
            WHERE sale_id = :sale_id 
              AND direction = 'IN'
              AND status = 'COMPLETED'
        """),
        {"sale_id": sale_id}
    ).scalar() or 0
    
    # جلب total_amount من Sale
    sale_total = connection.execute(
        sa_text("SELECT total_amount FROM sales WHERE id = :sale_id"),
        {"sale_id": sale_id}
    ).scalar() or 0
    
    # حساب balance_due
    balance_due = float(sale_total) - float(total_paid_result)
    balance_due = max(0, balance_due)  # لا يمكن أن يكون سالب
    
    # تحديث الحقول في جدول Sales
    connection.execute(
        sa_text("""
            UPDATE sales 
            SET total_paid = :total_paid,
                balance_due = :balance_due,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :sale_id
        """),
        {
            "sale_id": sale_id,
            "total_paid": float(total_paid_result),
            "balance_due": balance_due
        }
    )


@event.listens_for(Payment, "after_insert", propagate=True)
@event.listens_for(Payment, "after_update", propagate=True)
@event.listens_for(Payment, "after_delete", propagate=True)
def _update_partner_supplier_balance_on_payment(mapper, connection, target: "Payment"):
    """تحديث رصيد الشريك/المورد عند تغيير الدفعة"""
    try:
        # تحديث رصيد الشريك
        if hasattr(target, 'partner_id') and target.partner_id:
            update_partner_balance(target.partner_id, connection)
        
        # تحديث رصيد المورد
        if hasattr(target, 'supplier_id') and target.supplier_id:
            update_supplier_balance(target.supplier_id, connection)
        
        # تحديث عبر customer_id للشريك
        if hasattr(target, 'customer_id') and target.customer_id:
            from sqlalchemy import text as sa_text
            # البحث عن الشريك/المورد المرتبط بهذا العميل
            partner_result = connection.execute(
                sa_text("SELECT id FROM partners WHERE customer_id = :cid"),
                {"cid": target.customer_id}
            ).fetchone()
            if partner_result:
                update_partner_balance(partner_result[0], connection)
            
            supplier_result = connection.execute(
                sa_text("SELECT id FROM suppliers WHERE customer_id = :cid"),
                {"cid": target.customer_id}
            ).fetchone()
            if supplier_result:
                update_supplier_balance(supplier_result[0], connection)
        
        # تحديث عبر sale_id
        if hasattr(target, 'sale_id') and target.sale_id:
            from sqlalchemy import text as sa_text
            sale_result = connection.execute(
                sa_text("SELECT customer_id FROM sales WHERE id = :sid"),
                {"sid": target.sale_id}
            ).fetchone()
            if sale_result and sale_result[0]:
                # البحث عن الشريك/المورد
                partner_result = connection.execute(
                    sa_text("SELECT id FROM partners WHERE customer_id = :cid"),
                    {"cid": sale_result[0]}
                ).fetchone()
                if partner_result:
                    update_partner_balance(partner_result[0], connection)
                
                supplier_result = connection.execute(
                    sa_text("SELECT id FROM suppliers WHERE customer_id = :cid"),
                    {"cid": sale_result[0]}
                ).fetchone()
                if supplier_result:
                    update_supplier_balance(supplier_result[0], connection)
    except Exception as e:
        # لا نريد أن يفشل الـ transaction بسبب تحديث الرصيد
        pass

@event.listens_for(Payment, "after_insert", propagate=True)
@event.listens_for(Payment, "after_update", propagate=True)
@event.listens_for(Payment, "after_delete", propagate=True)
def _update_sale_on_payment_change(mapper, connection, target: "Payment"):
    """تحديث total_paid و balance_due في Sale عند تغيير Payment"""
    if hasattr(target, 'sale_id') and target.sale_id:
        _update_sale_payment_totals(connection, target.sale_id)


# ===== تحديث total_paid و balance_due في Invoices تلقائياً =====
def _update_invoice_payment_totals(connection, invoice_id):
    """تحديث total_paid و balance_due في جدول Invoices"""
    if not invoice_id:
        return
    
    # حساب total_paid من جدول Payments
    total_paid_result = connection.execute(
        sa_text("""
            SELECT COALESCE(SUM(total_amount), 0) 
            FROM payments 
            WHERE invoice_id = :invoice_id 
              AND direction = 'IN'
              AND status = 'COMPLETED'
        """),
        {"invoice_id": invoice_id}
    ).scalar() or 0
    
    # جلب total_amount من Invoice
    invoice_total = connection.execute(
        sa_text("SELECT total_amount FROM invoices WHERE id = :invoice_id"),
        {"invoice_id": invoice_id}
    ).scalar() or 0
    
    # حساب balance_due
    balance_due = float(invoice_total) - float(total_paid_result)
    balance_due = max(0, balance_due)
    
    # تحديث الحقول في جدول Invoices
    connection.execute(
        sa_text("""
            UPDATE invoices 
            SET total_paid = :total_paid,
                balance_due = :balance_due,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :invoice_id
        """),
        {
            "invoice_id": invoice_id,
            "total_paid": float(total_paid_result),
            "balance_due": balance_due
        }
    )


@event.listens_for(Payment, "after_insert", propagate=True)
@event.listens_for(Payment, "after_update", propagate=True)
@event.listens_for(Payment, "after_delete", propagate=True)
def _update_invoice_on_payment_change(mapper, connection, target: "Payment"):
    """تحديث total_paid و balance_due في Invoice عند تغيير Payment"""
    if hasattr(target, 'invoice_id') and target.invoice_id:
        _update_invoice_payment_totals(connection, target.invoice_id)


def _avg_cost_until(product_id: int, supplier_id: int, as_of: datetime) -> Decimal:
    qsum = db.session.query(
        func.coalesce(func.sum(ExchangeTransaction.quantity * func.nullif(ExchangeTransaction.unit_cost, 0)), 0),
        func.coalesce(func.sum(ExchangeTransaction.quantity), 0)
    ).filter(
        ExchangeTransaction.product_id == product_id,
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.created_at <= as_of,
        ExchangeTransaction.direction.in_(("IN", "ADJUSTMENT")),
        func.coalesce(ExchangeTransaction.unit_cost, 0) > 0
    ).first()
    total_val = Decimal(str(qsum[0] or 0))
    total_qty = Decimal(str(qsum[1] or 0))
    if total_qty > 0:
        return (total_val / total_qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prod = db.session.get(Product, product_id) if product_id else None
    pp = Decimal(str(getattr(prod, "purchase_price", 0) or 0))
    if pp > 0:
        return pp.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal("0.00")


def _default_mode_for_supplier(supplier_id: int) -> str:
    sup = db.session.get(Supplier, supplier_id)
    terms = (getattr(sup, "payment_terms", "") or "").upper()
    if "CONSUME" in terms or "ON_CONSUME" in terms or "CONSUMPTION" in terms:
        return SupplierSettlementMode.ON_CONSUME.value
    return SupplierSettlementMode.ON_RECEIPT.value


def _used_sources_for_supplier(supplier_id: int):
    rows = (
        db.session.query(SupplierSettlementLine.source_type, SupplierSettlementLine.source_id)
        .join(SupplierSettlement, SupplierSettlement.id == SupplierSettlementLine.settlement_id)
        .filter(
            SupplierSettlement.supplier_id == supplier_id,
            SupplierSettlement.status == SupplierSettlementStatus.CONFIRMED.value
        ).all()
    )
    return {(r[0], int(r[1] or 0)) for r in rows if r[1] is not None}


def build_supplier_settlement_draft(
    supplier_id: int,
    date_from: datetime,
    date_to: datetime,
    *,
    currency: str = "ILS",
    mode: str | None = None
) -> SupplierSettlement:
    from sqlalchemy.orm import joinedload

    final_mode = (mode or _default_mode_for_supplier(supplier_id)).upper()
    ss = SupplierSettlement(
        supplier_id=supplier_id,
        from_date=date_from,
        to_date=date_to,
        currency=(currency or "ILS").upper(),
        status=SupplierSettlementStatus.DRAFT.value,
        mode=final_mode
    )

    used = _used_sources_for_supplier(supplier_id)

    total_purchases = Decimal("0.00")
    total_returns = Decimal("0.00")
    total_loans = Decimal("0.00")
    total_consumption = Decimal("0.00")
    total_invoices = Decimal("0.00")

    if final_mode == SupplierSettlementMode.ON_RECEIPT.value:
        txs = (
            db.session.query(ExchangeTransaction)
            .join(Warehouse, Warehouse.id == ExchangeTransaction.warehouse_id)
            .options(joinedload(ExchangeTransaction.product))
            .filter(
                Warehouse.warehouse_type == WarehouseType.EXCHANGE.value,
                Warehouse.supplier_id == supplier_id,
                ExchangeTransaction.created_at >= date_from,
                ExchangeTransaction.created_at <= date_to,
            )
            .all()
        )
        for tx in txs:
            if ("EXCHANGE_PURCHASE", tx.id) in used or ("EXCHANGE_RETURN", tx.id) in used or ("EXCHANGE_ADJUST", tx.id) in used:
                continue
            dirv = (getattr(tx, "direction", "") or "").upper()
            qty = Decimal(str(tx.quantity or 0))
            unit_price = Decimal(str(tx.unit_cost or 0))
            cost_source = "TX_PRICE"
            if unit_price <= 0:
                unit_price = _avg_cost_until(tx.product_id, supplier_id, date_to)
                cost_source = "TX_AVG" if unit_price > 0 else "MISSING"
            amount = (qty * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            needs_pricing = bool(unit_price <= 0)
            if dirv == "IN":
                total_purchases += amount
                ss.lines.append(SupplierSettlementLine(
                    source_type="EXCHANGE_PURCHASE",
                    source_id=tx.id,
                    description=f"توريد تبادل #{tx.id}",
                    product_id=tx.product_id,
                    quantity=qty,
                    unit_price=unit_price if unit_price > 0 else None,
                    gross_amount=amount,
                    needs_pricing=needs_pricing,
                    cost_source=cost_source
                ))
            elif dirv == "OUT":
                total_returns += amount
                ss.lines.append(SupplierSettlementLine(
                    source_type="EXCHANGE_RETURN",
                    source_id=tx.id,
                    description=f"مرتجع تبادل #{tx.id}",
                    product_id=tx.product_id,
                    quantity=qty,
                    unit_price=unit_price if unit_price > 0 else None,
                    gross_amount=amount,
                    needs_pricing=needs_pricing,
                    cost_source=cost_source
                ))
            elif dirv == "ADJUSTMENT":
                total_purchases += amount
                ss.lines.append(SupplierSettlementLine(
                    source_type="EXCHANGE_ADJUST",
                    source_id=tx.id,
                    description=f"تسوية مخزون (تبادل) #{tx.id}",
                    product_id=tx.product_id,
                    quantity=qty,
                    unit_price=unit_price if unit_price > 0 else None,
                    gross_amount=amount,
                    needs_pricing=needs_pricing,
                    cost_source=cost_source
                ))

    if final_mode == SupplierSettlementMode.ON_CONSUME.value:
        s_lines = (
            db.session.query(SaleLine)
            .join(Warehouse, Warehouse.id == SaleLine.warehouse_id)
            .filter(
                Warehouse.warehouse_type == WarehouseType.EXCHANGE.value,
                Warehouse.supplier_id == supplier_id,
                SaleLine.created_at >= date_from,
                SaleLine.created_at <= date_to
            ).all()
        )
        for sl in s_lines:
            if ("CONSUME_SALE", sl.id) in used:
                continue
            qty = Decimal(str(sl.quantity or 0))
            unit_price = _avg_cost_until(sl.product_id, supplier_id, date_to)
            cost_source = "TX_AVG" if unit_price > 0 else "MISSING"
            needs_pricing = bool(unit_price <= 0)
            amount = (qty * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_consumption += amount
            ss.lines.append(SupplierSettlementLine(
                source_type="CONSUME_SALE",
                source_id=sl.id,
                description=f"استهلاك بيع #{sl.sale_id}-{sl.id}",
                product_id=sl.product_id,
                quantity=qty,
                unit_price=unit_price if unit_price > 0 else None,
                gross_amount=amount,
                needs_pricing=needs_pricing,
                cost_source=cost_source
            ))
        sp_lines = (
            db.session.query(ServicePart)
            .join(Warehouse, Warehouse.id == ServicePart.warehouse_id)
            .filter(
                Warehouse.warehouse_type == WarehouseType.EXCHANGE.value,
                Warehouse.supplier_id == supplier_id,
                ServicePart.created_at >= date_from,
                ServicePart.created_at <= date_to
            ).all()
        )
        for sp in sp_lines:
            if ("CONSUME_SERVICE", sp.id) in used:
                continue
            qty = Decimal(str(sp.quantity or 0))
            unit_price = _avg_cost_until(sp.part_id, supplier_id, date_to)
            cost_source = "TX_AVG" if unit_price > 0 else "MISSING"
            needs_pricing = bool(unit_price <= 0)
            amount = (qty * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_consumption += amount
            ss.lines.append(SupplierSettlementLine(
                source_type="CONSUME_SERVICE",
                source_id=sp.id,
                description=f"استهلاك صيانة #{sp.service_id}-{sp.id}",
                product_id=sp.part_id,
                quantity=qty,
                unit_price=unit_price if unit_price > 0 else None,
                gross_amount=amount,
                needs_pricing=needs_pricing,
                cost_source=cost_source
            ))

    loans_q = (
        db.session.query(SupplierLoanSettlement)
        .options(joinedload(SupplierLoanSettlement.loan))
        .filter(
            SupplierLoanSettlement.supplier_id == supplier_id,
            SupplierLoanSettlement.settlement_date >= date_from,
            SupplierLoanSettlement.settlement_date <= date_to
        )
    )
    for ls in loans_q:
        if ("LOAN_SETTLEMENT", ls.id) in used:
            continue
        amount = q(ls.settled_price)
        prod_id = getattr(getattr(ls, "loan", None), "product_id", None)
        total_loans += amount
        ss.lines.append(SupplierSettlementLine(
            source_type="LOAN_SETTLEMENT",
            source_id=ls.id,
            description=f"تسوية قرض #{ls.id}",
            product_id=prod_id,
            quantity=None,
            unit_price=None,
            gross_amount=amount,
            needs_pricing=False,
            cost_source="FIXED"
        ))

    invs = db.session.query(Invoice).filter(Invoice.supplier_id == supplier_id).all()
    for inv in invs:
        if inv.balance_due > 0:
            if ("SUPPLIER_INVOICE", inv.id) in used:
                continue
            amount = Decimal(str(inv.balance_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_invoices += amount
            ss.lines.append(SupplierSettlementLine(
                source_type="SUPPLIER_INVOICE",
                source_id=inv.id,
                description=f"فاتورة مورد #{inv.invoice_number or inv.id}",
                product_id=None,
                quantity=None,
                unit_price=None,
                gross_amount=amount,
                needs_pricing=False,
                cost_source="INVOICE"
            ))

    if final_mode == SupplierSettlementMode.ON_RECEIPT.value:
        gross = q(total_purchases + total_loans + total_invoices)
        due = q(total_purchases + total_loans + total_invoices - total_returns)
    else:
        gross = q(total_consumption + total_loans + total_invoices)
        due = q(total_consumption + total_loans + total_invoices)

    ss.total_gross = gross
    ss.total_due = due
    ss.ensure_code()
    return ss

class ShipmentItem(db.Model):
    __tablename__ = "shipment_items"

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    declared_value = db.Column(db.Numeric(12, 2))
    landed_extra_share = db.Column(db.Numeric(12, 2), default=0)
    landed_unit_cost = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.String(200))

    shipment = db.relationship("Shipment", back_populates="items")
    product  = db.relationship("Product",  back_populates="shipment_items")
    warehouse= db.relationship("Warehouse",back_populates="shipment_items")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="chk_shipment_item_qty_positive"),
        db.UniqueConstraint("shipment_id","product_id","warehouse_id", name="uq_shipment_item_unique"),
        db.Index("ix_shipment_items_prod_wh", "product_id","warehouse_id"),
        db.CheckConstraint("unit_cost >= 0", name="ck_shipment_item_unit_cost_non_negative"),
        db.CheckConstraint("declared_value >= 0", name="ck_shipment_item_declared_value_non_negative"),
        db.CheckConstraint("landed_extra_share >= 0", name="ck_shipment_item_landed_extra_share_non_negative"),
        db.CheckConstraint("landed_unit_cost >= 0", name="ck_shipment_item_landed_unit_cost_non_negative"),
    )

    @validates("quantity")
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("Quantity must be positive")
        return v

    @hybrid_property
    def total_value(self):
        return q(D(self.quantity or 0) * D(self.unit_cost or 0))

    @hybrid_property
    def landed_total_value(self):
        return q(D(self.quantity or 0) * (D(self.unit_cost or 0) + D(self.landed_extra_share or 0) / (D(self.quantity or 1))))

    def __repr__(self):
        return f"<ShipmentItem {self.product_id} Q{self.quantity}>"

@event.listens_for(ShipmentItem, "before_insert")
@event.listens_for(ShipmentItem, "before_update")
def _shipitem_before_save(mapper, connection, it: "ShipmentItem"):
    q_qty = D(it.quantity or 0)
    base_uc = q(D(it.unit_cost or 0))
    extra   = q(D(it.landed_extra_share or 0))
    if q_qty <= 0:
        return
    it.landed_unit_cost = q(base_uc + (extra / q_qty))


class Shipment(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "shipments"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), unique=True, index=True)
    shipment_number = db.Column(db.String(50), unique=True, index=True)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    shipment_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expected_arrival = db.Column(db.DateTime)
    actual_arrival   = db.Column(db.DateTime)
    delivered_date = db.Column(db.DateTime)

    origin = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    destination_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    status = db.Column(db.String(20), default="DRAFT", nullable=False, index=True, server_default=sa_text("'DRAFT'"))

    value_before = db.Column(db.Numeric(12, 2))
    shipping_cost = db.Column(db.Numeric(12, 2))
    customs = db.Column(db.Numeric(12, 2))
    vat = db.Column(db.Numeric(12, 2))
    insurance = db.Column(db.Numeric(12, 2))
    total_cost = db.Column(db.Numeric(12, 2))

    carrier = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100), index=True)
    notes = db.Column(db.Text)
    currency = db.Column(db.String(10), default="USD", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), index=True)
    
    # حقول إضافية للشحنات
    weight = db.Column(db.Numeric(10, 3))  # الوزن بالكيلو
    dimensions = db.Column(db.String(100))  # الأبعاد
    package_count = db.Column(db.Integer, default=1)  # عدد الطرود
    priority = db.Column(db.String(20), default="NORMAL")  # الأولوية
    delivery_method = db.Column(db.String(50))  # طريقة التسليم
    delivery_instructions = db.Column(db.Text)  # تعليمات التسليم
    customs_declaration = db.Column(db.String(100))  # رقم البيان الجمركي
    customs_cleared_date = db.Column(db.DateTime)  # تاريخ التخليص الجمركي
    delivery_attempts = db.Column(db.Integer, default=0)  # محاولات التسليم
    last_delivery_attempt = db.Column(db.DateTime)  # آخر محاولة تسليم
    return_reason = db.Column(db.Text)  # سبب الإرجاع
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    items    = db.relationship("ShipmentItem", back_populates="shipment", cascade="all, delete-orphan", order_by="ShipmentItem.id")
    partners = db.relationship("ShipmentPartner", back_populates="shipment", cascade="all, delete-orphan", order_by="ShipmentPartner.id")
    payments = db.relationship("Payment", back_populates="shipment", order_by="Payment.id")
    sale     = db.relationship("Sale", back_populates="shipments")
    destination_warehouse = db.relationship("Warehouse", back_populates="shipments_received", foreign_keys=[destination_id])
    expenses = db.relationship("Expense", back_populates="shipment", passive_deletes=True, order_by="Expense.id")
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])

    gl_batches = db.relationship(
        "GLBatch",
        primaryjoin="and_(foreign(GLBatch.source_id)==Shipment.id, GLBatch.source_type=='SHIPMENT')",
        viewonly=True,
        order_by="GLBatch.id",
    )

    __table_args__ = (
        db.CheckConstraint("status IN ('DRAFT','PENDING','IN_TRANSIT','IN_CUSTOMS','ARRIVED','DELIVERED','CANCELLED','RETURNED','CREATED')", name="chk_shipment_status_allowed"),
        db.Index("ix_shipments_dest_status", "destination_id", "status"),
        db.CheckConstraint("value_before >= 0", name="ck_shipment_value_before_non_negative"),
        db.CheckConstraint("shipping_cost >= 0", name="ck_shipment_shipping_cost_non_negative"),
        db.CheckConstraint("customs >= 0", name="ck_shipment_customs_non_negative"),
        db.CheckConstraint("vat >= 0", name="ck_shipment_vat_non_negative"),
        db.CheckConstraint("insurance >= 0", name="ck_shipment_insurance_non_negative"),
    )

    @validates("status")
    def _v_status(self, _, v):
        return (str(v or "")).strip().upper()

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "USD").upper()

    @hybrid_property
    def total_value(self):
        return q(
            D(self.value_before or 0)
            + D(self.shipping_cost or 0)
            + D(self.customs or 0)
            + D(self.vat or 0)
            + D(self.insurance or 0)
        )

    @hybrid_property
    def landed_total_value(self):
        return q(sum(q(it.landed_unit_cost) * D(it.quantity or 0) for it in (self.items or [])))

    def update_status(self, new_status: str):
        self.status = (new_status or "").strip().upper()
        if self.status == "ARRIVED" and not self.actual_arrival:
            self.actual_arrival = datetime.now(timezone.utc)

    def _apply_arrival_stock(self):
        for it in (self.items or []):
            lvl = StockLevel.query.filter_by(product_id=it.product_id, warehouse_id=it.warehouse_id).with_for_update().first()
            if not lvl:
                lvl = StockLevel(product_id=it.product_id, warehouse_id=it.warehouse_id, quantity=0, reserved_quantity=0)
                db.session.add(lvl)
                db.session.flush()
            lvl.quantity = int(lvl.quantity or 0) + int(it.quantity or 0)

    def _revert_arrival_stock(self):
        for it in (self.items or []):
            lvl = StockLevel.query.filter_by(product_id=it.product_id, warehouse_id=it.warehouse_id).with_for_update().first()
            if not lvl:
                continue
            new_q = int(lvl.quantity or 0) - int(it.quantity or 0)
            if new_q < 0:
                raise Exception("لا يمكن عكس مخزون الشحنة: سيصبح المخزون سالبًا")
            lvl.quantity = new_q

    def __repr__(self):
        return f"<Shipment {self.number or self.shipment_number or self.id}>"

def _recompute_shipment_value_before(shp: "Shipment"):
    vb = sum(q(D(it.quantity or 0) * D(it.unit_cost or 0)) for it in (shp.items or []))
    shp.value_before = q(vb)

def _allocate_landed_costs(shp: "Shipment"):
    items = shp.items or []
    if not items:
        return
    base_vals = [q(D(it.quantity or 0) * D(it.unit_cost or 0)) for it in items]
    total_base = q(sum(base_vals))
    if total_base <= 0:
        per_item = q(D(shp.shipping_cost or 0) + D(shp.customs or 0) + D(shp.vat or 0) + D(shp.insurance or 0)) / D(len(items))
        for it in items:
            it.landed_extra_share = q(per_item)
        return

    total_extras = q(D(shp.shipping_cost or 0) + D(shp.customs or 0) + D(shp.vat or 0) + D(shp.insurance or 0))
    if total_extras <= 0:
        for it in items:
            it.landed_extra_share = q(0)
        return

    for it, base in zip(items, base_vals):
        share = q(total_extras * (base / total_base))
        it.landed_extra_share = q(share)

@event.listens_for(Shipment, "before_insert")
def _shipment_before_insert(mapper, connection, target: "Shipment"):
    if not getattr(target, "shipment_number", None) and not getattr(target, "number", None):
        import hashlib
        
        # نظام تسلسل ذكي عصري عالمي مثل FedEx/DHL/UPS
        # التنسيق: AZD-YYYYMMDD-XXXX-CCC
        # AZD = رمز الشركة (Azad)
        # YYYYMMDD = التاريخ
        # XXXX = رقم تسلسلي يومي (hexadecimal)
        # CCC = checksum للتحقق
        
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y%m%d")
        
        # حساب العدد اليومي
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = connection.execute(
            sa_text("SELECT COUNT(*) FROM shipments WHERE shipment_date >= :start"),
            {"start": today_start},
        ).scalar() or 0
        
        # رقم تسلسلي hexadecimal (أكثر احترافية وأقصر)
        seq_hex = format(count + 1, '04X')  # 0001, 0002, ..., FFFF
        
        # بناء الرقم الأساسي
        base_number = f"AZD-{date_part}-{seq_hex}"
        
        # حساب checksum (آخر 3 أحرف من hash)
        hash_value = hashlib.md5(base_number.encode()).hexdigest()[:3].upper()
        
        # الرقم النهائي
        tracking_number = f"{base_number}-{hash_value}"
        
        target.shipment_number = tracking_number
        target.number = tracking_number
        
        # إذا لم يكن هناك tracking_number، نستخدم نفس الرقم
        if not getattr(target, "tracking_number", None):
            target.tracking_number = tracking_number
            
    elif getattr(target, "shipment_number", None) and not getattr(target, "number", None):
        target.number = target.shipment_number
    elif getattr(target, "number", None) and not getattr(target, "shipment_number", None):
        target.shipment_number = target.number

    # تم نقل ضبط العملة إلى _shipment_normalize_insert (السطر 7968)
    if not getattr(target, "date", None) and getattr(target, "shipment_date", None):
        target.date = target.shipment_date
    if not getattr(target, "shipment_date", None) and getattr(target, "date", None):
        target.shipment_date = target.date

    _recompute_shipment_value_before(target)
    _allocate_landed_costs(target)

@event.listens_for(Shipment, "before_update")
def _shipment_before_update(mapper, connection, target: "Shipment"):
    # تم نقل ضبط العملة إلى _shipment_normalize_update (السطر 7989)
    if not getattr(target, "date", None) and getattr(target, "shipment_date", None):
        target.date = target.shipment_date
    if not getattr(target, "shipment_date", None) and getattr(target, "date", None):
        target.shipment_date = target.date
    if getattr(target, "shipment_number", None) and not getattr(target, "number", None):
        target.number = target.shipment_number
    if getattr(target, "number", None) and not getattr(target, "shipment_number", None):
        target.shipment_number = target.number

    _recompute_shipment_value_before(target)
    _allocate_landed_costs(target)

@event.listens_for(Shipment.status, "set")
def _shipment_status_toggle(target, value, oldvalue, initiator):
    def _normalize(val):
        if val is None:
            return ""
        if hasattr(val, "value"):
            val = val.value
        return str(val).strip().upper()

    old = _normalize(oldvalue)
    new = _normalize(value)
    if old == new:
        return

    if old != "ARRIVED" and new == "ARRIVED":
        target._apply_arrival_stock()
        if not getattr(target, "actual_arrival", None):
            target.actual_arrival = datetime.now(timezone.utc)
    elif old == "ARRIVED" and new != "ARRIVED":
        target._revert_arrival_stock()

@event.listens_for(Shipment, "after_update")
def _gl_on_shipment_arrived(mapper, connection, target: "Shipment"):
    try:
        hist = inspect(target).attrs.status.history
        changed = hist.has_changes()
        oldv = str(hist.deleted[0]).upper() if hist.deleted else None
        newv = str(hist.added[0]).upper() if hist.added else str(getattr(target, "status", "")).upper()
    except Exception:
        changed = True
        oldv = None
        newv = str(getattr(target, "status", "")).upper()

    if not changed or newv != "ARRIVED" or oldv == "ARRIVED":
        return

    from flask import current_app
    cfg = {}
    try:
        cfg = current_app.config or {}
    except Exception:
        pass
    if not bool(cfg.get("GL_AUTO_POST_ON_SHIPMENT_ARRIVAL", False)):
        return

    inv_acc   = cfg.get("GL_SHIPMENT_INV_ACCOUNT")
    offset_acc= cfg.get("GL_SHIPMENT_OFFSET_ACCOUNT")
    if not inv_acc or not offset_acc:
        return

    total = float(q(sum(q(D(it.landed_unit_cost or it.unit_cost or 0)) * D(it.quantity or 0) for it in (target.items or []))))
    if total <= 0:
        return

    # استخدام الدالة من models.py مباشرة
    currency = (getattr(target, "currency", None) or "USD").upper()
    ref  = str(getattr(target, "shipment_number", None) or target.id)
    memo = f"Shipment {ref} arrived"

    entries = [
        (str(inv_acc).upper(),    total, 0.0),
        (str(offset_acc).upper(), 0.0,   total)
    ]
    _gl_upsert_batch_and_entries(
        connection,
        source_type="SHIPMENT",
        source_id=target.id,
        purpose="ARRIVAL",
        currency=currency,
        memo=memo,
        entries=entries,
        ref=ref,
        entity_type=None,
        entity_id=None,
    )

class ShipmentPartner(db.Model, TimestampMixin):
    __tablename__ = 'shipment_partners'

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id', ondelete='CASCADE'), nullable=False, index=True)
    identity_number = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    address = db.Column(db.String(200))
    unit_price_before_tax = db.Column(db.Numeric(12, 2))
    expiry_date = db.Column(db.Date)
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    share_amount = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='chk_shipment_partner_share'),
        db.UniqueConstraint('shipment_id', 'partner_id', name='uq_shipment_partner_unique'),
        db.Index('ix_shipment_partner_pair', 'shipment_id', 'partner_id'),
        CheckConstraint('unit_price_before_tax >= 0', name='ck_shipment_partner_unit_price_non_negative'),
        CheckConstraint('share_amount >= 0', name='ck_shipment_partner_share_amount_non_negative'),
    )

    partner = db.relationship('Partner', back_populates='shipment_partners')
    shipment = db.relationship('Shipment', back_populates='partners')

    @hybrid_property
    def share_value(self):
        if self.share_amount and D(self.share_amount) > 0:
            return q(D(self.share_amount))
        return q(D(self.unit_price_before_tax or 0) * (D(self.share_percentage or 0) / Decimal("100")))

    @share_value.expression
    def share_value(cls):
        amt = func.coalesce(cls.share_amount, 0)
        base = func.coalesce(cls.unit_price_before_tax, 0)
        pct = func.coalesce(cls.share_percentage, 0)
        return case((amt > 0, amt), else_=(base * (pct / 100.0)))

    def __repr__(self):
        return f"<ShipmentPartner shipment={self.shipment_id} partner={self.partner_id}>"

class ServiceRequest(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)
    service_number = db.Column(db.String(50), unique=True, index=True, nullable=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True, nullable=False)
    mechanic_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey("equipment_types.id"), index=True)

    status = db.Column(sa_str_enum(ServiceStatus, name="service_status"), default=ServiceStatus.PENDING.value, nullable=False, index=True)
    priority = db.Column(sa_str_enum(ServicePriority, name="service_priority"), default=ServicePriority.MEDIUM.value, nullable=False, index=True)

    vehicle_vrn = db.Column(db.String(50))
    vehicle_model = db.Column(db.String(100))
    chassis_number = db.Column(db.String(100))
    engineer_notes = db.Column(db.Text)
    description = db.Column(db.Text)
    estimated_duration = db.Column(db.Integer)
    actual_duration = db.Column(db.Integer)
    estimated_cost = db.Column(db.Numeric(12, 2))
    total_cost = db.Column(db.Numeric(12, 2))
    start_time = db.Column(db.Date)
    end_time = db.Column(db.Date)
    problem_description = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    resolution = db.Column(db.Text)
    notes = db.Column(db.Text)

    received_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    started_at = db.Column(db.DateTime)
    expected_delivery = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    currency = db.Column(db.String(10), nullable=False, default="ILS")
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    parts_total = db.Column(db.Numeric(12, 2), default=0)
    labor_total = db.Column(db.Numeric(12, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    consume_stock = db.Column(db.Boolean, default=True, nullable=False)
    warranty_days = db.Column(db.Integer, default=0)

    refunded_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    refund_of_id = db.Column(db.Integer, db.ForeignKey("service_requests.id", ondelete="SET NULL"), index=True)
    idempotency_key = db.Column(db.String(64), unique=True, index=True)
    cancelled_at = db.Column(db.DateTime, index=True)
    cancelled_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    cancel_reason = db.Column(db.String(200))
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    customer = db.relationship("Customer", back_populates="service_requests")
    mechanic = db.relationship("User", back_populates="mechanic_service_requests", foreign_keys=[mechanic_id])
    cancelled_by_user = db.relationship("User", back_populates="cancelled_service_requests", foreign_keys=[cancelled_by])
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])
    vehicle_type = db.relationship("EquipmentType", back_populates="service_requests")
    invoice = db.relationship("Invoice", back_populates="service", uselist=False)

    payments = db.relationship("Payment", back_populates="service", cascade="all, delete-orphan", order_by="Payment.id")
    parts = db.relationship("ServicePart", back_populates="request", cascade="all, delete-orphan", order_by="ServicePart.id")
    tasks = db.relationship("ServiceTask", back_populates="request", cascade="all, delete-orphan", order_by="ServiceTask.id")
    gl_batches = db.relationship("GLBatch", primaryjoin="and_(foreign(GLBatch.source_id)==ServiceRequest.id, GLBatch.source_type=='SERVICE')", viewonly=True, order_by="GLBatch.id")

    refund_of = db.relationship("ServiceRequest", remote_side=[id])

    __table_args__ = ()

    @validates("status", "priority")
    def _v_enum_strings(self, _, v): return getattr(v, "value", v)

    @validates("currency")
    def _v_currency(self, _, v): return ensure_currency(v or "ILS")

    @validates("discount_total", "parts_total", "labor_total", "total_amount", "total_cost", "estimated_duration", "actual_duration", "warranty_days", "refunded_total")
    def _v_non_negative(self, key, v):
        if v in (None, ""):
            return 0 if key in ("estimated_duration", "actual_duration", "warranty_days") else _Q2(0)
        d = _D(v)
        if d < 0:
            raise ValueError(f"{key} must be >= 0")
        return int(d) if key in ("estimated_duration", "actual_duration", "warranty_days") else _Q2(d)

    @hybrid_property
    def subtotal(self): return float(_Q2(_D(self.parts_total or 0) + _D(self.labor_total or 0)))

    @subtotal.expression
    def subtotal(cls):
        return func.coalesce(cls.parts_total, 0) + func.coalesce(cls.labor_total, 0)

    @hybrid_property
    def tax_amount(self):
        base = _D(self.subtotal) - _D(self.discount_total or 0)
        if base < 0: base = Decimal("0.00")
        return float(_Q2(base * (_D(self.tax_rate or 0) / Decimal("100"))))

    @tax_amount.expression
    def tax_amount(cls):
        base = (func.coalesce(cls.parts_total, 0) + func.coalesce(cls.labor_total, 0)) - func.coalesce(cls.discount_total, 0)
        base_pos = case((base < 0, 0), else_=base)
        return base_pos * (func.coalesce(cls.tax_rate, 0) / 100.0)

    @hybrid_property
    def total(self):
        if self.total_amount is not None: return float(_Q2(_D(self.total_amount or 0)))
        base = _D(self.subtotal) - _D(self.discount_total or 0)
        if base < 0: base = Decimal("0.00")
        tax = base * (_D(self.tax_rate or 0) / Decimal("100"))
        return float(_Q2(base + tax))

    @total.expression
    def total(cls):
        base = (func.coalesce(cls.parts_total, 0) + func.coalesce(cls.labor_total, 0)) - func.coalesce(cls.discount_total, 0)
        base_pos = case((base < 0, 0), else_=base)
        calc = base_pos + (base_pos * (func.coalesce(cls.tax_rate, 0) / 100.0))
        return func.coalesce(cls.total_amount, calc)

    @hybrid_property
    def total_paid(self):
        return float(db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(Payment.service_id == self.id, Payment.status == PaymentStatus.COMPLETED.value, Payment.direction == PaymentDirection.IN.value).scalar() or 0)

    @total_paid.expression
    def total_paid(cls):
        return select(func.coalesce(func.sum(Payment.total_amount), 0)).where((Payment.service_id == cls.id) & (Payment.status == PaymentStatus.COMPLETED.value) & (Payment.direction == PaymentDirection.IN.value)).scalar_subquery()

    @hybrid_property
    def balance_due(self):
        val = _Q2(_D(self.total) - _D(self.total_paid))
        return float(val if val > 0 else Decimal("0.00"))

    @balance_due.expression
    def balance_due(cls):
        bd = (cls.total - cls.total_paid)
        return case((bd < 0, 0), else_=bd)

    @hybrid_property
    def warranty_until(self):
        if not self.warranty_days: return None
        anchor = self.completed_at or self.updated_at or self.created_at
        return anchor + timedelta(days=self.warranty_days) if anchor else None

    @hybrid_property
    def refundable_amount(self):
        return float(_Q2(_D(self.total_paid or 0) - _D(self.refunded_total or 0)))

    def can_refund(self, amount):
        amt = _Q2(amount or 0)
        return amt > 0 and amt <= _Q2(self.refundable_amount)

    def apply_refund(self, amount):
        if not self.can_refund(amount):
            raise ValueError("service.refund_exceeds_allowed")
        self.refunded_total = _Q2(_D(self.refunded_total or 0) + _D(amount or 0))

    def cancel(self, by_user_id=None, reason=None):
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancelled_by = by_user_id
        self.cancel_reason = (reason or None)
        self.status = ServiceStatus.CANCELLED.value

    def mark_started(self):
        if not self.started_at: self.started_at = datetime.now(timezone.utc)
        if self.status == ServiceStatus.PENDING.value: self.status = ServiceStatus.IN_PROGRESS.value

    def mark_completed(self):
        self.status = ServiceStatus.COMPLETED.value
        if not self.completed_at: self.completed_at = datetime.now(timezone.utc)

    def __repr__(self): return f"<ServiceRequest {self.service_number or self.id}>"

    def to_dict(self):
        return {"id": self.id,"service_number": self.service_number,"status": getattr(self.status, "value", self.status),"priority": getattr(self.priority, "value", self.priority),"customer_id": self.customer_id,"mechanic_id": self.mechanic_id,"vehicle_type_id": self.vehicle_type_id,"problem_description": self.problem_description,"diagnosis": self.diagnosis,"resolution": self.resolution,"notes": self.notes,"received_at": self.received_at.isoformat() if self.received_at else None,"started_at": self.started_at.isoformat() if self.started_at else None,"expected_delivery": self.expected_delivery.isoformat() if self.expected_delivery else None,"completed_at": self.completed_at.isoformat() if self.completed_at else None,"currency": self.currency,"tax_rate": float(self.tax_rate or 0),"discount_total": float(self.discount_total or 0),"parts_total": float(self.parts_total or 0),"labor_total": float(self.labor_total or 0),"total_amount": float(self.total_amount or 0),"subtotal": float(self.subtotal),"tax_amount": float(self.tax_amount),"total": float(self.total),"total_paid": float(self.total_paid),"balance_due": float(self.balance_due),"warranty_days": self.warranty_days,"warranty_until": self.warranty_until.isoformat() if self.warranty_until else None,"refunded_total": float(self.refunded_total or 0),"refundable_amount": float(self.refundable_amount),"refund_of_id": self.refund_of_id,"idempotency_key": self.idempotency_key,"cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,"cancelled_by": self.cancelled_by,"cancel_reason": self.cancel_reason,"parts": [p.to_dict() for p in self.parts] if self.parts else [],"tasks": [t.to_dict() for t in self.tasks] if self.tasks else []}

def _D(x):
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def _Q2(x):
    return _D(x).quantize(Decimal("0.01"), ROUND_HALF_UP)

def _calc_parts_sum(service_id: int) -> Decimal:
    rows = db.session.query(
        ServicePart.quantity, ServicePart.unit_price, ServicePart.discount
    ).filter(ServicePart.service_id == service_id).all()
    total = Decimal("0")
    for q, u, d in rows:
        qd = _D(q)
        ud = _D(u)
        dd = _D(d) / Decimal("100")
        gross = qd * ud
        taxable = gross * (Decimal("1") - dd)
        total += taxable
    return _Q2(total)

def _calc_tasks_sum(service_id: int) -> Decimal:
    rows = db.session.query(
        ServiceTask.quantity, ServiceTask.unit_price, ServiceTask.discount
    ).filter(ServiceTask.service_id == service_id).all()
    total = Decimal("0")
    for q, u, d in rows:
        qd = _D(q)
        ud = _D(u)
        dd = _D(d) / Decimal("100")
        gross = qd * ud
        taxable = gross * (Decimal("1") - dd)
        total += taxable
    return _Q2(total)

from flask import current_app

def _service_consumes_stock(sr: "ServiceRequest") -> bool:
    if not sr:
        return False
    if not bool(current_app.config.get("SERVICE_CONSUMES_STOCK", True)):
        return False
    status = str(getattr(sr, "status", "")).upper()
    return bool(getattr(sr, "consume_stock", True)) and status in ("IN_PROGRESS", "COMPLETED")

def _recalc_service_request_totals(sr: "ServiceRequest"):
    if sr is None:
        return
    parts_sum = _calc_parts_sum(sr.id) if getattr(sr, "id", None) else _Q2(getattr(sr, "parts_total", 0) or 0)
    tasks_sum = _calc_tasks_sum(sr.id) if getattr(sr, "id", None) else _Q2(getattr(sr, "labor_total", 0) or 0)
    discount_total = _Q2(getattr(sr, "discount_total", 0) or 0)
    tax_rate = _D(getattr(sr, "tax_rate", 0) or 0) / Decimal("100")
    sr.parts_total = _Q2(parts_sum)
    sr.labor_total = _Q2(tasks_sum)
    base = parts_sum + tasks_sum - discount_total
    if base < 0:
        base = Decimal("0.00")
    tax = base * tax_rate
    sr.total_amount = _Q2(base + tax)
    sr.currency = ensure_currency(getattr(sr, "currency", None) or "ILS")
    tc = _D(getattr(sr, "total_cost", 0) or 0)
    sr.total_cost = _Q2(base) if tc < base else _Q2(tc)

_ALLOWED_SERVICE_TRANSITIONS = {
    "PENDING": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

@event.listens_for(ServiceRequest, "before_insert")
@event.listens_for(ServiceRequest, "before_update")
def _compute_service_totals(mapper, connection, target: ServiceRequest):
    _recalc_service_request_totals(target)

@event.listens_for(ServiceRequest, "before_update")
def _srv_enforce_transitions(mapper, connection, target: ServiceRequest):
    from sqlalchemy.orm.attributes import get_history
    h = get_history(target, "status")
    oldv = (h.deleted[0] if h.deleted else getattr(target, "status", None))
    newv = getattr(target, "status", None)
    o = (getattr(oldv, "value", oldv) or "PENDING")
    n = getattr(newv, "value", newv)
    if o != n:
        allowed = _ALLOWED_SERVICE_TRANSITIONS.get(o, set())
        if n not in allowed:
            raise ValueError("service.invalid_status_transition")

@event.listens_for(ServiceRequest, "before_insert")
def _ensure_service_number(mapper, connection, target: ServiceRequest):
    if getattr(target, "service_number", None):
        return
    prefix = datetime.now(timezone.utc).strftime("SRV%Y%m%d")
    cnt = connection.execute(
        sa_text("SELECT COUNT(*) FROM service_requests WHERE service_number LIKE :pfx"),
        {"pfx": f"{prefix}-%"},
    ).scalar() or 0
    target.service_number = f"{prefix}-{cnt + 1:04d}"

@event.listens_for(ServiceRequest.status, "set")
def _set_completed_at_on_status_change(target, value, oldvalue, initiator):
    newv = getattr(value, "value", value)
    if newv == ServiceStatus.COMPLETED.value and not target.completed_at:
        target.completed_at = datetime.now(timezone.utc)

@event.listens_for(ServiceRequest, "after_update")
def _gl_on_service_complete(mapper, connection, target: "ServiceRequest"):
    try:
        hist = inspect(target).attrs.status.history
        changed = hist.has_changes()
        oldv = getattr(hist.deleted[0], "value", hist.deleted[0]) if hist.deleted else None
        newv = getattr(hist.added[0], "value", hist.added[0]) if hist.added else getattr(target, "status", None)
    except Exception:
        changed = True
        oldv = None
        newv = getattr(target, "status", None)
    if not changed or newv != ServiceStatus.COMPLETED.value or oldv == ServiceStatus.COMPLETED.value:
        return
    if getattr(target, "invoice_id", None):
        return
    cfg = {}
    try:
        cfg = current_app.config
    except Exception:
        pass
    if not bool(cfg.get("GL_AUTO_POST_ON_SERVICE_COMPLETE", False)):
        return
    parts = _D(getattr(target, "parts_total", 0) or 0)
    labor = _D(getattr(target, "labor_total", 0) or 0)
    discount = _D(getattr(target, "discount_total", 0) or 0)
    tax_rate = _D(getattr(target, "tax_rate", 0) or 0)
    currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    subtotal = parts + labor
    base = subtotal - discount
    if base < 0:
        base = Decimal("0.00")
    tax = base * (tax_rate / Decimal("100"))
    total = base + tax
    if total <= 0:
        return
    # استخدام الدالة من models.py مباشرة
    entries = [
        (GL_ACCOUNTS["AR"],  float(_Q2(total)),      0.0),
        (GL_ACCOUNTS["VAT"], 0.0,                    float(_Q2(tax))),
        (GL_ACCOUNTS["REV"], 0.0,                    float(_Q2(total - tax))),
    ]
    ref = str(getattr(target, "service_number", None) or target.id)
    memo = f"Service {ref} completed"
    _gl_upsert_batch_and_entries(
        connection,
        source_type="SERVICE",
        source_id=target.id,
        purpose="SERVICE_COMPLETE",
        currency=currency,
        memo=memo,
        entries=entries,
        ref=ref,
        entity_type="CUSTOMER",
        entity_id=target.customer_id,
    )

class ServicePart(db.Model, TimestampMixin):
    __tablename__ = 'service_parts'

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_requests.id', ondelete="CASCADE"), nullable=False, index=True)
    part_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    note = db.Column(db.String(200))
    notes = db.Column(db.Text)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), index=True)
    share_percentage = db.Column(db.Numeric(5, 2), default=0)

    request = db.relationship('ServiceRequest', back_populates='parts')
    part = db.relationship('Product', back_populates='service_parts')
    warehouse = db.relationship('Warehouse', back_populates='service_parts')
    partner = db.relationship('Partner', back_populates='service_parts')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_service_part_qty_positive'),
        db.CheckConstraint('unit_price >= 0', name='chk_service_part_price_non_negative'),
        db.CheckConstraint('discount >= 0 AND discount <= 100', name='chk_service_part_discount_range'),
        db.CheckConstraint('tax_rate >= 0 AND tax_rate <= 100', name='chk_service_part_tax_range'),
        db.CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='chk_service_part_share_range'),
        db.UniqueConstraint('service_id', 'part_id', 'warehouse_id', name='uq_service_part_unique'),
        db.Index('ix_service_part_pair', 'service_id', 'part_id'),
        db.Index('ix_service_part_partner', 'partner_id'),
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @validates('unit_price', 'discount', 'tax_rate', 'share_percentage')
    def _v_money_pct(self, key, v):
        if v in (None, ''):
            return 0
        d = _D(v)
        if key in ('discount', 'tax_rate', 'share_percentage') and (d < 0 or d > _D(100)):
            raise ValueError(f"{key} must be between 0 and 100")
        if key == 'unit_price' and d < 0:
            raise ValueError("unit_price must be >= 0")
        return _Q2(d) if key == 'unit_price' else d

    @validates('note', 'notes')
    def _v_strip(self, _, v):
        return (str(v).strip() or None) if v is not None else None

    @hybrid_property
    def gross_amount(self):
        return _Q2(_D(self.quantity or 0) * _D(self.unit_price or 0))

    @hybrid_property
    def discount_amount(self):
        return _Q2(_D(self.gross_amount) * (_D(self.discount or 0) / _D(100)))

    @hybrid_property
    def taxable_amount(self):
        return _Q2(_D(self.gross_amount) - _D(self.discount_amount))

    @hybrid_property
    def tax_amount(self):
        return _Q2(_D(self.taxable_amount) * (_D(self.tax_rate or 0) / _D(100)))

    @hybrid_property
    def line_total(self):
        return _Q2(_D(self.taxable_amount) + _D(self.tax_amount))

    @hybrid_property
    def net_total(self):
        share = _D(self.share_percentage or 0) / _D(100)
        return _Q2(_D(self.line_total) * (_D(1) - share))

    def to_dict(self):
        return {
            "id": self.id,
            "service_id": self.service_id,
            "part_id": self.part_id,
            "warehouse_id": self.warehouse_id,
            "partner_id": self.partner_id,
            "share_percentage": float(self.share_percentage or 0),
            "quantity": int(self.quantity or 0),
            "unit_price": float(self.unit_price or 0),
            "discount": float(self.discount or 0),
            "tax_rate": float(self.tax_rate or 0),
            "note": self.note,
            "notes": self.notes,
            "gross_amount": float(self.gross_amount),
            "discount_amount": float(self.discount_amount),
            "taxable_amount": float(self.taxable_amount),
            "tax_amount": float(self.tax_amount),
            "line_total": float(self.line_total),
            "net_total": float(self.net_total),
        }

    def __repr__(self):
        pname = getattr(self.part, "name", None)
        return f"<ServicePart {pname or self.part_id} for Service {self.service_id}>"

class ServiceTask(db.Model, TimestampMixin):
    __tablename__ = 'service_tasks'

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_requests.id', ondelete="CASCADE"), nullable=False, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    note = db.Column(db.String(200))

    request = db.relationship('ServiceRequest', back_populates='tasks')
    partner = db.relationship('Partner', back_populates='service_tasks')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_service_task_qty_positive'),
        db.CheckConstraint('unit_price >= 0', name='chk_service_task_price_non_negative'),
        db.CheckConstraint('discount >= 0 AND discount <= 100', name='chk_service_task_discount_range'),
        db.CheckConstraint('tax_rate >= 0 AND tax_rate <= 100', name='chk_service_task_tax_range'),
        db.CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='chk_service_task_share_range'),
        db.Index('ix_service_task_service', 'service_id'),
        db.Index('ix_service_task_partner', 'partner_id'),
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @validates('unit_price', 'discount', 'tax_rate', 'share_percentage')
    def _v_money_pct(self, key, v):
        if v in (None, ''):
            return 0
        d = _D(v)
        if key in ('discount', 'tax_rate', 'share_percentage') and (d < 0 or d > _D(100)):
            raise ValueError(f"{key} must be between 0 and 100")
        if key == 'unit_price' and d < 0:
            raise ValueError("unit_price must be >= 0")
        return _Q2(d) if key == 'unit_price' else d

    @validates('description', 'note')
    def _v_strip(self, _, v):
        return (str(v).strip() or None) if v is not None else None

    @hybrid_property
    def gross_amount(self):
        return _Q2(_D(self.quantity or 0) * _D(self.unit_price or 0))

    @hybrid_property
    def discount_amount(self):
        return _Q2(_D(self.gross_amount) * (_D(self.discount or 0) / _D(100)))

    @hybrid_property
    def taxable_amount(self):
        return _Q2(_D(self.gross_amount) - _D(self.discount_amount))

    @hybrid_property
    def tax_amount(self):
        return _Q2(_D(self.taxable_amount) * (_D(self.tax_rate or 0) / _D(100)))

    @hybrid_property
    def line_total(self):
        return _Q2(_D(self.taxable_amount) + _D(self.tax_amount))

    @hybrid_property
    def net_total(self):
        share = _D(self.share_percentage or 0) / _D(100)
        return _Q2(_D(self.line_total) * (_D(1) - share))

    def to_dict(self):
        return {
            "id": self.id,
            "service_id": self.service_id,
            "partner_id": self.partner_id,
            "share_percentage": float(self.share_percentage or 0),
            "description": self.description,
            "quantity": int(self.quantity or 0),
            "unit_price": float(self.unit_price or 0),
            "discount": float(self.discount or 0),
            "tax_rate": float(self.tax_rate or 0),
            "note": self.note,
            "gross_amount": float(self.gross_amount),
            "discount_amount": float(self.discount_amount),
            "taxable_amount": float(self.taxable_amount),
            "tax_amount": float(self.tax_amount),
            "line_total": float(self.line_total),
            "net_total": float(self.net_total),
        }

    def __repr__(self):
        return f"<ServiceTask {self.description} for Service {self.service_id}>"

@event.listens_for(ServicePart, "after_insert")
def _sp_after_insert(mapper, connection, target: ServicePart):
    if target and target.request:
        _recalc_service_request_totals(target.request)

@event.listens_for(ServicePart, "after_update")
def _sp_after_update(mapper, connection, target: ServicePart):
    if target and target.request:
        _recalc_service_request_totals(target.request)

@event.listens_for(ServicePart, "after_delete")
def _sp_after_delete(mapper, connection, target: ServicePart):
    if target and target.request:
        _recalc_service_request_totals(target.request)

@event.listens_for(ServiceTask, "after_insert")
@event.listens_for(ServiceTask, "after_update")
@event.listens_for(ServiceTask, "after_delete")
def _st_sync_totals(mapper, connection, target: ServiceTask):
    if target and target.request:
        _recalc_service_request_totals(target.request)

class OnlineCart(db.Model, TimestampMixin):
    __tablename__ = 'online_carts'

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.String(50), unique=True, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), index=True)
    session_id = db.Column(db.String(100), index=True)
    status = db.Column(sa_str_enum(['ACTIVE', 'ABANDONED', 'CONVERTED'], name='cart_status'),
                       default='ACTIVE', nullable=False, index=True)
    expires_at = db.Column(db.DateTime, index=True)

    customer = db.relationship('Customer', back_populates='online_carts')
    items = db.relationship('OnlineCartItem', back_populates='cart', cascade='all, delete-orphan')

    __table_args__ = ()

    @hybrid_property
    def subtotal(self) -> float:
        total = _D(0)
        for i in (self.items or []):
            total += _D(i.line_total or 0)
        return float(_Q2(total))

    @hybrid_property
    def item_count(self) -> int:
        return sum(int(i.quantity or 0) for i in (self.items or []))

    @hybrid_property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "cart_id": self.cart_id,
            "customer_id": self.customer_id,
            "session_id": self.session_id,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "item_count": self.item_count,
            "subtotal": self.subtotal,
            "is_expired": self.is_expired,
        }

    def __repr__(self):
        return f"<OnlineCart {self.cart_id or self.id}>"


@event.listens_for(OnlineCart, 'before_insert')
def _cart_before_insert(mapper, connection, target: 'OnlineCart'):
    if not getattr(target, 'cart_id', None):
        prefix = datetime.now(timezone.utc).strftime("CRT%Y%m%d")
        count = connection.execute(
            sa_text("SELECT COUNT(*) FROM online_carts WHERE cart_id LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.cart_id = f"{prefix}-{count+1:04d}"
    if not getattr(target, 'expires_at', None):
        target.expires_at = datetime.now(timezone.utc) + timedelta(days=7)


class OnlineCartItem(db.Model):
    __tablename__ = 'online_cart_items'

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('online_carts.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'),
                           nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    cart = db.relationship('OnlineCart', back_populates='items')
    product = db.relationship('Product', back_populates='online_cart_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_cart_item_qty_positive'),
        db.CheckConstraint('price >= 0', name='chk_cart_item_price_non_negative'),
        db.Index('ix_cart_item_cart_product', 'cart_id', 'product_id'),
        db.UniqueConstraint('cart_id', 'product_id', name='uq_cart_item_cart_product'),
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def line_total(self) -> Decimal:
        return _Q2(_D(self.quantity or 0) * _D(self.price or 0))

    def to_dict(self):
        return {
            "id": self.id,
            "cart_id": self.cart_id,
            "product_id": self.product_id,
            "quantity": int(self.quantity or 0),
            "price": float(self.price or 0),
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "line_total": float(self.line_total),
        }

    def __repr__(self):
        pname = getattr(self.product, 'name', None)
        return f"<OnlineCartItem {pname or self.product_id} x{self.quantity}>"


@event.listens_for(OnlineCartItem, 'before_insert')
@event.listens_for(OnlineCartItem, 'before_update')
def _cart_item_price_default(mapper, connection, target: 'OnlineCartItem'):
    if target.price in (None, 0):
        price = connection.execute(
            sa_text("SELECT COALESCE(online_price, price) FROM products WHERE id = :pid"),
            {"pid": target.product_id}
        ).scalar()
        target.price = _Q2(price or 0)


class OnlinePreOrder(db.Model, TimestampMixin):
    __tablename__ = 'online_preorders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('online_carts.id', ondelete='SET NULL'))
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='SET NULL'), index=True)
    warehouse = db.relationship('Warehouse')

    prepaid_amount = db.Column(db.Numeric(12, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    currency = db.Column(db.String(10), default='ILS', nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    expected_fulfillment = db.Column(db.DateTime)
    actual_fulfillment = db.Column(db.DateTime)

    status = db.Column(sa_str_enum(['PENDING', 'CONFIRMED', 'FULFILLED', 'CANCELLED'], name='online_preorder_status'),
                       default='PENDING', nullable=False, index=True)
    payment_status = db.Column(sa_str_enum(['PENDING', 'PARTIAL', 'PAID'], name='online_preorder_payment_status'),
                               default='PENDING', nullable=False, index=True)

    payment_method = db.Column(db.String(50))
    notes = db.Column(db.Text)
    shipping_address = db.Column(db.Text)
    billing_address = db.Column(db.Text)

    customer = db.relationship('Customer', back_populates='online_preorders')
    cart = db.relationship('OnlineCart')
    items = db.relationship('OnlinePreOrderItem', back_populates='order', cascade='all, delete-orphan')
    payments = db.relationship('OnlinePayment', back_populates='order')

    __table_args__ = (
        db.CheckConstraint('prepaid_amount >= 0', name='chk_online_prepaid_non_negative'),
        db.CheckConstraint('total_amount  >= 0', name='chk_online_total_non_negative'),
        db.Index('ix_online_preorders_customer_status', 'customer_id', 'status'),
        db.Index('ix_online_preorders_status_paystatus', 'status', 'payment_status'),
    )

    @validates('status', 'payment_status')
    def _upper(self, _, v):
        return v.upper() if isinstance(v, str) else v

    @hybrid_property
    def items_subtotal(self) -> float:
        total = _D(0)
        for i in (self.items or []):
            total += _D(i.line_total or 0)
        return float(_Q2(total))

    @hybrid_property
    def total_paid(self) -> float:
        total = _D(0)
        for p in (self.payments or []):
            if getattr(p, 'status', None) == 'SUCCESS':
                total += _D(p.amount or 0)
        return float(_Q2(total))

    @hybrid_property
    def balance_due(self) -> float:
        return float(_Q2(_D(self.total_amount or 0) - (_D(self.prepaid_amount or 0) + _D(self.total_paid or 0))))

    def update_totals_and_status(self):
        total = _D(0)
        for i in (self.items or []):
            total += _D(i.line_total or 0)
        self.total_amount = _Q2(total)

        paid_total = float(_Q2(_D(self.total_paid or 0) + _D(self.prepaid_amount or 0)))
        total_num = float(self.total_amount or 0)
        if total_num > 0 and paid_total >= total_num:
            self.payment_status = 'PAID'
        elif paid_total > 0:
            self.payment_status = 'PARTIAL'
        else:
            self.payment_status = 'PENDING'

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "customer_id": self.customer_id,
            "cart_id": self.cart_id,
            "prepaid_amount": float(self.prepaid_amount or 0),
            "total_amount": float(self.total_amount or 0),
            "expected_fulfillment": self.expected_fulfillment.isoformat() if self.expected_fulfillment else None,
            "actual_fulfillment": self.actual_fulfillment.isoformat() if self.actual_fulfillment else None,
            "status": self.status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "notes": self.notes,
            "shipping_address": self.shipping_address,
            "billing_address": self.billing_address,
            "items_subtotal": self.items_subtotal,
            "total_paid": self.total_paid,
            "balance_due": self.balance_due,
        }

    def __repr__(self):
        return f"<OnlinePreOrder {self.order_number or self.id}>"


@event.listens_for(OnlinePreOrder, 'before_insert')
def _op_before_insert(mapper, connection, target: 'OnlinePreOrder'):
    if not getattr(target, 'order_number', None):
        prefix = datetime.now(timezone.utc).strftime("OPR%Y%m%d")
        count = connection.execute(
            sa_text("SELECT COUNT(*) FROM online_preorders WHERE order_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.order_number = f"{prefix}-{count + 1:04d}"

    if not getattr(target, 'warehouse_id', None):
        tval = WarehouseType.ONLINE.value
        row = connection.execute(
            sa_text("SELECT id FROM warehouses WHERE warehouse_type = :t AND is_active = 1 ORDER BY id LIMIT 1"),
            {"t": tval}
        ).first()
        if row:
            target.warehouse_id = row._mapping["id"]
        else:
            connection.execute(
                sa_text("INSERT INTO warehouses (name, warehouse_type, is_active) VALUES (:n, :t, 1)"),
                {"n": "ONLINE", "t": tval}
            )
            row2 = connection.execute(
                sa_text("SELECT id FROM warehouses WHERE warehouse_type = :t AND name = :n ORDER BY id DESC LIMIT 1"),
                {"t": tval, "n": "ONLINE"}
            ).first()
            if row2:
                target.warehouse_id = row2._mapping["id"]

    target.update_totals_and_status()


@event.listens_for(OnlinePreOrder, 'before_update')
def _op_before_update(mapper, connection, target: 'OnlinePreOrder'):
    target.update_totals_and_status()


@event.listens_for(OnlinePreOrder, "after_update")
def _op_reservation_flow(mapper, connection, target: "OnlinePreOrder"):
    hist = inspect(target)
    h = hist.attrs['status'].history
    old_status = (h.deleted[0] if h.deleted else getattr(target, "status", "") or "").upper()
    new_status = (h.added[0] if h.added else getattr(target, "status", "") or "").upper()
    if old_status == new_status:
        return

    wid = getattr(target, "warehouse_id", None)
    if not wid:
        tval = WarehouseType.ONLINE.value
        row = connection.execute(
            sa_text("SELECT id FROM warehouses WHERE warehouse_type = :t AND is_active = 1 ORDER BY id LIMIT 1"),
            {"t": tval}
        ).first()
        if row:
            wid = row._mapping["id"]
        else:
            return

    def _each_item(fn):
        for it in (target.items or []):
            pid = getattr(it, "product_id", None)
            qty = int(getattr(it, "quantity", 0) or 0)
            if pid and qty > 0:
                fn(pid, qty)

    if new_status == "CONFIRMED" and old_status != "CONFIRMED":
        _each_item(lambda pid, qty: _apply_reservation_delta(connection, pid, wid, +qty))
    elif new_status == "FULFILLED":
        def _consume(pid, qty):
            _apply_reservation_delta(connection, pid, wid, -qty)
            _apply_stock_delta(connection, pid, wid, -qty)
        _each_item(_consume)
    elif old_status == "CONFIRMED" and new_status != "CONFIRMED":
        _each_item(lambda pid, qty: _apply_reservation_delta(connection, pid, wid, -qty))


class OnlinePreOrderItem(db.Model):
    __tablename__ = 'online_preorder_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('online_preorders.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'),
                           nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)

    order = db.relationship('OnlinePreOrder', back_populates='items')
    product = db.relationship('Product', back_populates='online_preorder_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_online_item_qty_positive'),
        db.CheckConstraint('price >= 0', name='chk_online_item_price_non_negative'),
        db.Index('ix_online_item_order_product', 'order_id', 'product_id'),
        db.UniqueConstraint('order_id', 'product_id', name='uq_online_item_order_product'),
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def line_total(self) -> Decimal:
        return _Q2(_D(self.quantity or 0) * _D(self.price or 0))

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "product_id": self.product_id,
            "quantity": int(self.quantity or 0),
            "price": float(self.price or 0),
            "line_total": float(self.line_total),
        }

    def __repr__(self):
        pname = getattr(self.product, 'name', None)
        return f"<OnlinePreOrderItem {pname or self.product_id} x{self.quantity}>"


@event.listens_for(OnlinePreOrderItem, 'before_insert')
@event.listens_for(OnlinePreOrderItem, 'before_update')
def _op_item_price_default(mapper, connection, target: 'OnlinePreOrderItem'):
    if target.price in (None, 0):
        price = connection.execute(
            sa_text("SELECT COALESCE(online_price, price) FROM products WHERE id = :pid"),
            {"pid": target.product_id}
        ).scalar()
        target.price = _Q2(price or 0)

@event.listens_for(OnlinePreOrderItem, "after_insert")
@event.listens_for(OnlinePreOrderItem, "after_update")
@event.listens_for(OnlinePreOrderItem, "after_delete")
def _op_items_touch_order(mapper, connection, target: "OnlinePreOrderItem"):
    try:
        if target and target.order:
            target.order.update_totals_and_status()
    except Exception:
        pass


class OnlinePayment(db.Model, TimestampMixin):
    __tablename__ = 'online_payments'

    id = db.Column(db.Integer, primary_key=True)
    payment_ref = db.Column(db.String(100), unique=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('online_preorders.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default='ILS', nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))
    
    method = db.Column(db.String(50))
    gateway = db.Column(db.String(50))
    status = db.Column(sa_str_enum(['PENDING','SUCCESS','FAILED','REFUNDED'], name='online_payment_status'),
                       default='PENDING', nullable=False, index=True)
    transaction_data = db.Column(db.JSON)
    processed_at = db.Column(db.DateTime)
    card_last4 = db.Column(db.String(4), index=True)
    card_encrypted = db.Column(db.LargeBinary)
    card_expiry = db.Column(db.String(5))
    cardholder_name = db.Column(db.String(128))
    card_brand = db.Column(db.String(20))
    card_fingerprint = db.Column(db.String(64), index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='SET NULL'), index=True)
    idempotency_key = db.Column(db.String(64), unique=True, index=True)

    order = db.relationship('OnlinePreOrder', back_populates='payments')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='chk_online_payment_amount_positive'),
        db.Index('ix_online_payments_order_status', 'order_id', 'status'),
        db.Index('ix_online_payments_gateway_status', 'gateway', 'status'),
    )

    @validates('amount')
    def _v_amount(self, _, v):
        if v is None or float(v) <= 0:
            raise ValueError("amount must be > 0")
        return _Q2(v)

    @validates('currency')
    def _v_currency(self, _, v):
        return ensure_currency(v or 'ILS')

    @validates('status')
    def _v_status(self, _, v):
        return v.upper() if isinstance(v, str) else v

    @validates('method', 'gateway')
    def _v_lower(self, _, v):
        return (v or None).lower() if isinstance(v, str) and v else v

    @staticmethod
    def _luhn_check(pan_digits: str) -> bool:
        if not pan_digits or not pan_digits.isdigit():
            return False
        s, alt = 0, False
        for d in pan_digits[::-1]:
            n = ord(d) - 48
            if alt:
                n *= 2
                if n > 9:
                    n -= 9
            s += n
            alt = not alt
        return s % 10 == 0

    @staticmethod
    def _is_valid_expiry_mm_yy(exp: str) -> bool:
        if not exp or not re.match(r'^\d{2}/\d{2}$', exp):
            return False
        mm, yy = exp.split('/')
        try:
            mm = int(mm)
            yy = int('20' + yy)
            if not (1 <= mm <= 12):
                return False
            now = datetime.now(timezone.utc)
            return (yy > now.year) or (yy == now.year and mm >= now.month)
        except Exception:
            return False

    @staticmethod
    def _detect_brand(pan_digits: str) -> str:
        if not pan_digits:
            return 'UNKNOWN'
        if pan_digits.startswith('4'):
            return 'VISA'
        i2 = int(pan_digits[:2]) if len(pan_digits) >= 2 else -1
        i4 = int(pan_digits[:4]) if len(pan_digits) >= 4 else -1
        if 51 <= i2 <= 55 or (2221 <= i4 <= 2720):
            return 'MASTERCARD'
        if i2 in (34, 37):
            return 'AMEX'
        return 'UNKNOWN'

    @staticmethod
    def _get_fernet():
        try:
            from cryptography.fernet import Fernet
            key = current_app.config.get('CARD_ENC_KEY')
            if not key:
                return None
            if isinstance(key, str):
                key = key.encode('utf-8')
            return Fernet(key)
        except Exception:
            return None

    def set_card_details(self, pan: str | None, holder: str | None,
                         expiry_mm_yy: str | None, *, validate: bool = True) -> None:
        pan_digits = ''.join((pan or '')).strip()
        pan_digits = ''.join(ch for ch in pan_digits if ch.isdigit())

        self.cardholder_name = (holder or '').strip() or None
        self.card_expiry = (expiry_mm_yy or '').strip() or None

        if pan_digits:
            if validate and not self._luhn_check(pan_digits):
                raise ValueError("Invalid card number (Luhn check failed)")
            self.card_last4 = pan_digits[-4:]
            self.card_fingerprint = hashlib.sha256(pan_digits.encode('utf-8')).hexdigest()
            self.card_brand = self._detect_brand(pan_digits)
            f = self._get_fernet()
            self.card_encrypted = f.encrypt(pan_digits.encode('utf-8')) if f else None
        else:
            self.card_last4 = None
            self.card_fingerprint = None
            self.card_brand = None
            self.card_encrypted = None

        if self.card_expiry and validate and not self._is_valid_expiry_mm_yy(self.card_expiry):
            raise ValueError("Invalid card expiry (MM/YY)")

    def decrypt_card_number(self) -> str | None:
        if not self.card_encrypted:
            return None
        f = self._get_fernet()
        if not f:
            return None
        try:
            return f.decrypt(self.card_encrypted).decode('utf-8')
        except Exception:
            return None

    def masked_card(self) -> str | None:
        return f"**** **** **** {self.card_last4}" if self.card_last4 else None

    @property
    def has_encrypted_card(self) -> bool:
        return bool(self.card_encrypted)

    def to_dict(self):
        return {
            "id": self.id,
            "payment_ref": self.payment_ref,
            "order_id": self.order_id,
            "amount": float(self.amount or 0),
            "currency": self.currency,
            "method": self.method,
            "gateway": self.gateway,
            "status": self.status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "card_brand": self.card_brand,
            "card_last4": self.card_last4,
            "card_masked": self.masked_card(),
            "payment_id": self.payment_id,
            "idempotency_key": self.idempotency_key,
        }

    def __repr__(self):
        ref = self.payment_ref or f"OP-{self.id}"
        return f"<OnlinePayment {ref} {self.amount} {self.currency} {self.status}>"


_ALLOWED_OPAY_TRANSITIONS = {
    "PENDING": {"SUCCESS", "FAILED", "REFUNDED"},
    "SUCCESS": {"REFUNDED"},
    "FAILED": set(),
    "REFUNDED": set(),
}

def _opay_enforce_transition(old: str | None, new: str) -> None:
    o = (old or "PENDING").upper()
    n = (new or "").upper()
    if o == n:
        return
    allowed = _ALLOWED_OPAY_TRANSITIONS.get(o, set())
    if n not in allowed:
        raise ValueError("online_payment.invalid_status_transition")


@event.listens_for(OnlinePayment, "after_insert")
@event.listens_for(OnlinePayment, "after_update")
@event.listens_for(OnlinePayment, "after_delete")
def _opay_touch_order(mapper, connection, target: "OnlinePayment"):
    try:
        if target.order:
            target.order.update_totals_and_status()
    except Exception:
        pass


@event.listens_for(OnlinePayment, "before_insert")
def _opay_before_insert(mapper, connection, target: "OnlinePayment"):
    if not getattr(target, "payment_ref", None):
        prefix = datetime.now(timezone.utc).strftime("OPAY%Y%m%d")
        count = connection.execute(
            sa_text("SELECT COUNT(*) FROM online_payments WHERE payment_ref LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.payment_ref = f"{prefix}-{count+1:04d}"
    target.currency = ensure_currency(target.currency or "ILS")
    st = (target.status or "").upper()
    if st in ("SUCCESS", "FAILED", "REFUNDED") and not target.processed_at:
        target.processed_at = datetime.now(timezone.utc)


@event.listens_for(OnlinePayment, "before_update")
def _opay_before_update(mapper, connection, target: "OnlinePayment"):
    from sqlalchemy.orm.attributes import get_history
    target.currency = ensure_currency(target.currency or "ILS")
    h = get_history(target, "status")
    prev = (h.deleted[0] if h.deleted else getattr(target, "status", None))
    _opay_enforce_transition(prev, getattr(target, "status", None))
    st = (target.status or "").upper()
    if st in ("SUCCESS", "FAILED", "REFUNDED") and not target.processed_at:
        target.processed_at = datetime.now(timezone.utc)


class UtilityAccount(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "utility_accounts"

    id = db.Column(db.Integer, primary_key=True)
    utility_type = db.Column(db.String(20), nullable=False, index=True)
    provider = db.Column(db.String(120), nullable=False)
    account_no = db.Column(db.String(100), index=True)
    meter_no = db.Column(db.String(100), index=True)
    alias = db.Column(db.String(120), index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    expenses = relationship("Expense", back_populates="utility_account", order_by="Expense.id")

    __table_args__ = (
        CheckConstraint("utility_type IN ('ELECTRICITY','WATER')", name="ck_utility_type_allowed"),
        db.UniqueConstraint("utility_type", "provider", "account_no", name="uq_utility_key"),
        db.Index("ix_utility_active_type", "is_active", "utility_type"),
    )

    @validates("utility_type")
    def _v_utype(self, _, v):
        s = (v or "").strip().upper()
        if s not in {"ELECTRICITY", "WATER"}:
            raise ValueError("invalid utility_type")
        return s

    @validates("provider", "account_no", "meter_no", "alias")
    def _v_strip(self, _, v):
        return (v or "").strip() or None

    def __repr__(self):
        return f"<UtilityAccount {self.utility_type}:{self.alias or self.account_no}>"


class StockAdjustment(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "stock_adjustments"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    reason = db.Column(db.String(20), nullable=False, index=True)
    notes = db.Column(db.Text)
    total_cost = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    warehouse = db.relationship("Warehouse", back_populates="stock_adjustments")
    items = db.relationship("StockAdjustmentItem", back_populates="adjustment", cascade="all, delete-orphan", order_by="StockAdjustmentItem.id")
    expense = db.relationship("Expense", back_populates="stock_adjustment", uselist=False)

    __table_args__ = (
        CheckConstraint("reason IN ('DAMAGED','STORE_USE')", name="ck_stock_adjustment_reason_allowed"),
        CheckConstraint("total_cost >= 0", name="ck_stock_adjustment_total_cost_non_negative"),
        db.Index("ix_stock_adjust_wh_reason_date", "warehouse_id", "reason", "date"),
    )

    @validates("reason")
    def _v_reason(self, _, v):
        s = (v or "").strip().upper()
        if s not in {"DAMAGED", "STORE_USE"}:
            raise ValueError("invalid reason")
        return s

    def __repr__(self):
        return f"<StockAdjustment {self.reason} #{self.id}>"


class StockAdjustmentItem(db.Model):
    __tablename__ = "stock_adjustment_items"

    id = db.Column(db.Integer, primary_key=True)
    adjustment_id = db.Column(db.Integer, db.ForeignKey("stock_adjustments.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='SET NULL'), index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.String(200))

    adjustment = db.relationship("StockAdjustment", back_populates="items")
    product = db.relationship("Product", back_populates="stock_adjustment_items")
    warehouse = db.relationship('Warehouse')

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_adjustment_item_qty_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_stock_adjustment_item_cost_non_negative"),
        db.Index("ix_sai_prod_wh", "product_id", "warehouse_id"),
    )

    @validates("quantity")
    def _v_qty(self, _, v):
        v = int(v or 0)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @validates("unit_cost")
    def _v_cost(self, _, v):
        d = q(v or 0)
        if d < 0:
            raise ValueError("unit_cost must be >= 0")
        return d

    @hybrid_property
    def line_total(self):
        return q(D(self.quantity or 0) * D(self.unit_cost or 0))

    def __repr__(self):
        return f"<StockAdjustmentItem P{self.product_id} Q{self.quantity}>"


def _recompute_stock_adjustment_total(connection, adjustment_id: int):
    total = connection.execute(
        select(func.coalesce(func.sum(StockAdjustmentItem.quantity * StockAdjustmentItem.unit_cost), 0.0))
        .where(StockAdjustmentItem.adjustment_id == adjustment_id)
    ).scalar_one() or 0.0
    connection.execute(
        update(StockAdjustment)
        .where(StockAdjustment.id == adjustment_id)
        .values(total_cost=q(total))
    )


@event.listens_for(StockAdjustment, "before_insert")
@event.listens_for(StockAdjustment, "before_update")
def _sa_normalize(mapper, connection, target: StockAdjustment):
    target.reason = (target.reason or "").strip().upper()


@event.listens_for(StockAdjustment, "after_update")
def _sa_sync_expense_amount(mapper, connection, target: StockAdjustment):
    if getattr(target, "expense", None) and target.id:
        connection.execute(
            update(Expense)
            .where(Expense.stock_adjustment_id == int(target.id))
            .values(amount=q(target.total_cost or 0))
        )


@event.listens_for(StockAdjustmentItem, "after_insert")
def _sai_after_insert(mapper, connection, target: StockAdjustmentItem):
    if target.warehouse_id:
        _apply_stock_delta(connection, target.product_id, target.warehouse_id, -int(target.quantity or 0))
    if target.adjustment_id:
        _recompute_stock_adjustment_total(connection, int(target.adjustment_id))


@event.listens_for(StockAdjustmentItem, "after_delete")
def _sai_after_delete(mapper, connection, target: StockAdjustmentItem):
    if target.warehouse_id:
        _apply_stock_delta(connection, target.product_id, target.warehouse_id, +int(target.quantity or 0))
    if target.adjustment_id:
        _recompute_stock_adjustment_total(connection, int(target.adjustment_id))


@event.listens_for(StockAdjustmentItem, "after_update")
def _sai_after_update(mapper, connection, target: StockAdjustmentItem):
    from sqlalchemy.orm.attributes import get_history
    pid_hist = get_history(target, "product_id")
    wid_hist = get_history(target, "warehouse_id")
    qty_hist = get_history(target, "quantity")

    old_pid = (pid_hist.deleted[0] if pid_hist.deleted else target.product_id)
    old_wid = (wid_hist.deleted[0] if wid_hist.deleted else target.warehouse_id)
    old_qty = (qty_hist.deleted[0] if qty_hist.deleted else target.quantity)

    new_pid = target.product_id
    new_wid = target.warehouse_id
    new_qty = target.quantity

    if old_wid:
        _apply_stock_delta(connection, int(old_pid), int(old_wid), +int(old_qty or 0))
    if new_wid:
        _apply_stock_delta(connection, int(new_pid), int(new_wid), -int(new_qty or 0))

    if target.adjustment_id:
        _recompute_stock_adjustment_total(connection, int(target.adjustment_id))

# ===================== ExpenseType =====================
class ExpenseType(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "expense_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    expenses = relationship("Expense", back_populates="type", order_by="Expense.id")

    __table_args__ = ()

    @validates("name")
    def _v_name(self, _, v):
        s = (v or "").strip()
        if not s:
            raise ValueError("name is required")
        return s.title()

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description, "is_active": self.is_active}

    def __repr__(self):
        return f"<ExpenseType {self.name}>"


class Expense(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="ILS", nullable=False)
    
    # حقول سعر الصرف
    fx_rate_used = db.Column(db.Numeric(10, 6))
    fx_rate_source = db.Column(db.String(20))
    fx_rate_timestamp = db.Column(db.DateTime)
    fx_base_currency = db.Column(db.String(10))
    fx_quote_currency = db.Column(db.String(10))

    type_id = db.Column(db.Integer, db.ForeignKey("expense_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey("partners.id", ondelete="SET NULL"), index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id", ondelete="SET NULL"), index=True)
    utility_account_id = db.Column(db.Integer, db.ForeignKey("utility_accounts.id", ondelete="SET NULL"), index=True)
    stock_adjustment_id = db.Column(db.Integer, db.ForeignKey("stock_adjustments.id", ondelete="SET NULL"), index=True)

    payee_type = db.Column(db.String(20), nullable=False, default="OTHER", index=True)
    payee_entity_id = db.Column(db.Integer, index=True)
    payee_name = db.Column(db.String(200), index=True)

    beneficiary_name = db.Column(db.String(200))
    paid_to = db.Column(db.String(200), index=True)

    period_start = db.Column(db.Date, index=True)
    period_end = db.Column(db.Date, index=True)

    payment_method = db.Column(db.String(20), nullable=False, default="cash")
    payment_details = db.Column(db.Text)

    description = db.Column(db.String(200))
    notes = db.Column(db.Text)
    tax_invoice_number = db.Column(db.String(100), index=True)

    check_number = db.Column(db.String(100))
    check_bank = db.Column(db.String(100))
    check_due_date = db.Column(db.Date)

    bank_transfer_ref = db.Column(db.String(100))

    card_number = db.Column(db.String(8))
    card_holder = db.Column(db.String(120))
    card_expiry = db.Column(db.String(10))

    online_gateway = db.Column(db.String(50))
    online_ref = db.Column(db.String(100))
    
    # حقول الأرشيف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    archive_reason = db.Column(db.String(200))

    employee = relationship("Employee", back_populates="expenses")
    type = relationship("ExpenseType", back_populates="expenses")
    warehouse = relationship("Warehouse", back_populates="expenses")
    partner = relationship("Partner", back_populates="expenses")
    shipment = relationship("Shipment", back_populates="expenses")
    utility_account = relationship("UtilityAccount", back_populates="expenses")
    stock_adjustment = relationship("StockAdjustment", back_populates="expense")
    archived_by_user = relationship("User", foreign_keys=[archived_by])
    payments = relationship("Payment", back_populates="expense", cascade="all, delete-orphan", passive_deletes=True, order_by="Payment.id")

    gl_batches = relationship(
        "GLBatch",
        primaryjoin="and_(foreign(GLBatch.source_id)==Expense.id, GLBatch.source_type=='EXPENSE')",
        viewonly=True,
        order_by="GLBatch.id",
    )

    __table_args__ = (
        db.CheckConstraint("amount >= 0", name="chk_expense_amount_non_negative"),
        db.CheckConstraint("payment_method IN ('cash','cheque','bank','card','online','other')", name="chk_expense_payment_method_allowed"),
        CheckConstraint("payee_type IN ('EMPLOYEE','SUPPLIER','UTILITY','OTHER')", name="ck_expense_payee_type_allowed"),
        db.UniqueConstraint("stock_adjustment_id", name="uq_expenses_stock_adjustment_id"),
        db.Index("ix_expense_type_date", "type_id", "date"),
        db.Index("ix_expense_partner_date", "partner_id", "date"),
        db.Index("ix_expense_shipment_date", "shipment_id", "date"),
    )

    @validates("amount")
    def _v_amount(self, _, v):
        if v is None:
            raise ValueError("amount is required")
        if isinstance(v, str):
            v = v.replace("$", "").replace(",", "").strip()
        d = Decimal(str(v))
        if d < 0:
            raise ValueError("amount must be >= 0")
        return q(d)

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("payment_method")
    def _v_payment_method(self, _, v):
        allowed = {"cash", "cheque", "bank", "card", "online", "other"}
        val = (v or "cash").lower()
        if val not in allowed:
            raise ValueError(f"Invalid payment_method: {v}")
        return val

    @validates(
        "beneficiary_name",
        "paid_to",
        "payee_name",
        "check_number",
        "check_bank",
        "bank_transfer_ref",
        "card_number",
        "card_holder",
        "card_expiry",
        "online_gateway",
        "online_ref",
        "tax_invoice_number",
        "description",
        "payment_details",
        "notes",
    )
    def _v_strip(self, _, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @validates("payee_type")
    def _v_payee_type(self, _, v):
        s = (str(v or "OTHER")).strip().upper()
        if s not in {"EMPLOYEE", "SUPPLIER", "UTILITY", "OTHER"}:
            raise ValueError("invalid payee_type")
        return s

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.expense_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUT.value,
            )
            .scalar()
            or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.expense_id == cls.id)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (Payment.direction == PaymentDirection.OUT.value)
            )
            .scalar_subquery()
        )

    @hybrid_property
    def balance(self):
        return float(q(D(self.amount or 0) - D(self.total_paid or 0)))

    @balance.expression
    def balance(cls):
        paid_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.expense_id == cls.id)
                & (Payment.status == PaymentStatus.COMPLETED.value)
                & (Payment.direction == PaymentDirection.OUT.value)
            )
            .scalar_subquery()
        )
        return cls.amount - paid_subq

    @hybrid_property
    def is_paid(self):
        return self.balance <= 0

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "amount": float(self.amount or 0),
            "currency": self.currency,
            "type_id": self.type_id,
            "employee_id": self.employee_id,
            "warehouse_id": self.warehouse_id,
            "partner_id": self.partner_id,
            "shipment_id": self.shipment_id,
            "utility_account_id": self.utility_account_id,
            "stock_adjustment_id": self.stock_adjustment_id,
            "payee_type": self.payee_type,
            "payee_entity_id": self.payee_entity_id,
            "payee_name": self.payee_name,
            "beneficiary_name": self.beneficiary_name,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "paid_to": self.paid_to,
            "payment_method": self.payment_method,
            "payment_details": self.payment_details,
            "description": self.description,
            "notes": self.notes,
            "tax_invoice_number": self.tax_invoice_number,
            "check_number": self.check_number,
            "check_bank": self.check_bank,
            "check_due_date": self.check_due_date.isoformat() if self.check_due_date else None,
            "bank_transfer_ref": self.bank_transfer_ref,
            "card_number": self.card_number,
            "card_holder": self.card_holder,
            "card_expiry": self.card_expiry,
            "online_gateway": self.online_gateway,
            "online_ref": self.online_ref,
            "total_paid": self.total_paid,
            "balance": self.balance,
            "is_paid": self.is_paid,
        }


@event.listens_for(Expense, "before_insert")
def _expense_normalize_insert(mapper, connection, target: "Expense"):
    target.payment_method = (target.payment_method or "cash").lower()
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً للنفقات (فقط عند الإنشاء)
    expense_currency = target.currency
    default_currency = "ILS"
    
    if expense_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(expense_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = expense_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass
    
    target.payee_type = (target.payee_type or "OTHER").upper()
    if not target.paid_to:
        target.paid_to = (target.payee_name or None)


@event.listens_for(Expense, "before_update")
def _expense_normalize_update(mapper, connection, target: "Expense"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.payment_method = (target.payment_method or "cash").lower()
    target.currency = (target.currency or "ILS").upper()
    target.payee_type = (target.payee_type or "OTHER").upper()
    if not target.paid_to:
        target.paid_to = (target.payee_name or None)


@event.listens_for(Expense, "after_insert")
@event.listens_for(Expense, "after_update")
def _expense_gl_batch_upsert(mapper, connection, target: "Expense"):
    """إنشاء/تحديث GLBatch للمصروف تلقائياً"""
    try:
        from models import fx_rate
        
        # تحويل المبلغ للشيقل
        amount = float(target.amount or 0)
        if amount <= 0:
            return
        
        # تحويل العملة
        amount_ils = amount
        if target.currency and target.currency != 'ILS':
            try:
                rate = fx_rate(target.currency, 'ILS', target.date or datetime.utcnow(), raise_on_missing=False)
                if rate and rate > 0:
                    amount_ils = float(amount * float(rate))
            except:
                pass
        
        # القيد المحاسبي:
        # مدين: المصروفات (EXPENSES)
        # دائن: النقدية (حسب طريقة الدفع)
        cash_account = GL_ACCOUNTS.get("CASH", "1000_CASH")
        if target.payment_method == 'bank':
            cash_account = GL_ACCOUNTS.get("BANK", "1010_BANK")
        elif target.payment_method == 'card':
            cash_account = GL_ACCOUNTS.get("CARD", "1020_CARD_CLEARING")
        
        entries = [
            (GL_ACCOUNTS.get("EXP", "5000_EXPENSES"), amount_ils, 0),  # مدين
            (cash_account, 0, amount_ils),  # دائن
        ]
        
        memo = f"مصروف - {target.description or target.payee_name or 'مصروف عام'}"
        
        _gl_upsert_batch_and_entries(
            connection,
            source_type="EXPENSE",
            source_id=target.id,
            purpose="EXPENSE",
            currency="ILS",
            memo=memo,
            entries=entries,
            ref=f"EXP-{target.id}",
            entity_type=target.payee_type,
            entity_id=target.payee_entity_id
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في إنشاء GLBatch للمصروف #{target.id}: {e}", file=sys.stderr)


@event.listens_for(Expense, "after_delete")
def _expense_gl_batch_delete(mapper, connection, target: "Expense"):
    """حذف GLBatch للمصروف عند الحذف"""
    try:
        connection.execute(
            sa_text("""
                DELETE FROM gl_batches
                WHERE source_type = 'EXPENSE' AND source_id = :sid
            """),
            {"sid": target.id}
        )
    except Exception as e:
        import sys
        print(f"⚠️ خطأ في حذف GLBatch للمصروف #{target.id}: {e}", file=sys.stderr)


@event.listens_for(PreOrder, "before_insert")
def _preorder_normalize_insert(mapper, connection, target: "PreOrder"):
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    
    # حفظ سعر الصرف تلقائياً للحجوزات (فقط عند الإنشاء)
    preorder_currency = target.currency
    default_currency = "ILS"
    
    if preorder_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(preorder_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = preorder_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(PreOrder, "before_update")
def _preorder_normalize_update(mapper, connection, target: "PreOrder"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")


@event.listens_for(Sale, "before_insert")
def _sale_normalize_insert(mapper, connection, target: "Sale"):
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    
    # حفظ سعر الصرف تلقائياً للمبيعات (فقط عند الإنشاء)
    sale_currency = target.currency
    default_currency = "ILS"
    
    if sale_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(sale_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = sale_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(Sale, "before_update")
def _sale_normalize_update(mapper, connection, target: "Sale"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")


@event.listens_for(SaleReturn, "before_insert")
def _sale_return_normalize_insert(mapper, connection, target: "SaleReturn"):
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")
    
    # حفظ سعر الصرف تلقائياً لمرتجعات المبيعات (فقط عند الإنشاء)
    return_currency = target.currency
    default_currency = "ILS"
    
    if return_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(return_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = return_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(SaleReturn, "before_update")
def _sale_return_normalize_update(mapper, connection, target: "SaleReturn"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = ensure_currency(getattr(target, "currency", None) or "ILS")


@event.listens_for(Shipment, "before_insert")
def _shipment_normalize_insert(mapper, connection, target: "Shipment"):
    target.currency = ensure_currency(getattr(target, "currency", None) or "USD")
    
    # حفظ سعر الصرف تلقائياً للشحنات (فقط عند الإنشاء)
    shipment_currency = target.currency
    default_currency = "ILS"
    
    if shipment_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(shipment_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = shipment_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(Shipment, "before_update")
def _shipment_normalize_update(mapper, connection, target: "Shipment"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = ensure_currency(getattr(target, "currency", None) or "USD")


@event.listens_for(ServiceRequest, "before_insert")
def _service_request_normalize_insert(mapper, connection, target: "ServiceRequest"):
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً لطلبات الخدمة (فقط عند الإنشاء)
    service_currency = target.currency
    default_currency = "ILS"
    
    if service_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(service_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = service_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(ServiceRequest, "before_update")
def _service_request_normalize_update(mapper, connection, target: "ServiceRequest"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = (target.currency or "ILS").upper()


@event.listens_for(OnlinePreOrder, "before_insert")
def _online_preorder_normalize_insert(mapper, connection, target: "OnlinePreOrder"):
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً للحجوزات الأونلاين (فقط عند الإنشاء)
    online_currency = target.currency
    default_currency = "ILS"
    
    if online_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(online_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = online_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(OnlinePreOrder, "before_update")
def _online_preorder_normalize_update(mapper, connection, target: "OnlinePreOrder"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = (target.currency or "ILS").upper()


@event.listens_for(OnlinePayment, "before_insert")
def _online_payment_normalize_insert(mapper, connection, target: "OnlinePayment"):
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً للمدفوعات الأونلاين (فقط عند الإنشاء)
    payment_currency = target.currency
    default_currency = "ILS"
    
    if payment_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(payment_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = payment_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(OnlinePayment, "before_update")
def _online_payment_normalize_update(mapper, connection, target: "OnlinePayment"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = (target.currency or "ILS").upper()


@event.listens_for(SupplierSettlement, "before_insert")
def _supplier_settlement_normalize_insert(mapper, connection, target: "SupplierSettlement"):
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً لتسويات الموردين (فقط عند الإنشاء)
    settlement_currency = target.currency
    default_currency = "ILS"
    
    if settlement_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(settlement_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = settlement_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(SupplierSettlement, "before_update")
def _supplier_settlement_normalize_update(mapper, connection, target: "SupplierSettlement"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = (target.currency or "ILS").upper()


@event.listens_for(PartnerSettlement, "before_insert")
def _partner_settlement_normalize_insert(mapper, connection, target: "PartnerSettlement"):
    target.currency = (target.currency or "ILS").upper()
    
    # حفظ سعر الصرف تلقائياً لتسويات الشركاء (فقط عند الإنشاء)
    settlement_currency = target.currency
    default_currency = "ILS"
    
    if settlement_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(settlement_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_used = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_source = rate_info.get('source', 'unknown')
                target.fx_rate_timestamp = datetime.now(timezone.utc)
                target.fx_base_currency = settlement_currency
                target.fx_quote_currency = default_currency
        except Exception:
            pass


@event.listens_for(PartnerSettlement, "before_update")
def _partner_settlement_normalize_update(mapper, connection, target: "PartnerSettlement"):
    # تحديث الحقول فقط، بدون تغيير سعر الصرف
    target.currency = (target.currency or "ILS").upper()
    m = target.payment_method
    if m != "cheque":
        target.check_number = None
        target.check_bank = None
        target.check_due_date = None
    if m != "bank":
        target.bank_transfer_ref = None
    if m != "card":
        target.card_holder = None
        target.card_expiry = None
        target.card_number = None
    if m != "online":
        target.online_gateway = None
        target.online_ref = None
    if m == "card" and target.card_number:
        digits = "".join(ch for ch in (target.card_number or "") if ch.isdigit())
        target.card_number = (digits[-4:] if digits else None)


# ===================== Audit Log Model =====================
class AuditLog(db.Model, TimestampMixin):
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    model_name  = db.Column(db.String(100), nullable=False, index=True)
    record_id   = db.Column(db.Integer, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), index=True, nullable=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True)

    action      = db.Column(db.String(20), nullable=False, index=True)
    old_data    = db.Column(db.Text)
    new_data    = db.Column(db.Text)

    ip_address  = db.Column(db.String(45))
    user_agent  = db.Column(db.String(255))

    __table_args__ = ()

    @validates('action')
    def _v_action(self, _, v):
        return (v or '').strip().upper()

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if getattr(self, "created_at", None) else None,
            "model_name": self.model_name,
            "record_id": self.record_id,
            "customer_id": self.customer_id,
            "user_id": self.user_id,
            "action": self.action,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    def __repr__(self):
        return f"<AuditLog {self.model_name}#{self.record_id} {self.action}>"


@event.listens_for(_SA_Session, "before_flush")
def _capture_previous(session, ctx, instances=None):
    for obj in session.dirty:
        try:
            insp = inspect(obj)
        except Exception:
            continue
        prev = getattr(obj, "_previous_state", None)
        if prev is None:
            obj._previous_state = prev = {}
        for attr in insp.mapper.column_attrs:
            hist = insp.attrs[attr.key].history
            if hist.has_changes() and hist.deleted:
                if attr.key not in prev:
                    obj._previous_state[attr.key] = hist.deleted[0]


@event.listens_for(_SA_Session, "after_flush_postexec")
def _audit_after_flush_postexec(session, ctx):
    uid = None
    customer_id = None
    ip = None
    ua = None

    if has_request_context():
        if getattr(current_user, "is_authenticated", False):
            uid = current_user.id
            customer_id = getattr(current_user, "customer_id", None)
        ip = request.remote_addr
        ua = request.headers.get("User-Agent")

    def add_log(action, obj, old_data=None, new_data=None):
        try:
            session.add(AuditLog(
                model_name=obj.__class__.__name__,
                record_id=getattr(obj, "id", None),
                customer_id=customer_id,
                user_id=uid,
                action=(action or "").upper(),
                old_data=json.dumps(old_data, default=str) if old_data else None,
                new_data=json.dumps(new_data, default=str) if new_data else None,
                ip_address=ip,
                user_agent=ua,
            ))
        except Exception:
            pass

    for obj in session.new:
        if isinstance(obj, AuditMixin):
            try:
                curr = {c.key: getattr(obj, c.key, None) for c in inspect(obj).mapper.column_attrs}
            except Exception:
                curr = None
            add_log("CREATE", obj, new_data=curr)

    for obj in session.deleted:
        if isinstance(obj, AuditMixin):
            try:
                prev = {c.key: getattr(obj, c.key, None) for c in inspect(obj).mapper.column_attrs}
            except Exception:
                prev = None
            add_log("DELETE", obj, old_data=prev)

    for obj in session.dirty:
        if not isinstance(obj, AuditMixin):
            continue
        prev = getattr(obj, "_previous_state", None)
        if not prev:
            continue
        try:
            curr = {c.key: getattr(obj, c.key, None) for c in inspect(obj).mapper.column_attrs}
        except Exception:
            curr = None
        add_log("UPDATE", obj, old_data=prev, new_data=curr)

class Note(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    entity_type = db.Column(db.String(50), index=True)
    entity_id = db.Column(db.String(50), index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, server_default=sa_text("0"), index=True)
    priority = db.Column(sa_str_enum(['LOW', 'MEDIUM', 'HIGH', 'URGENT'], name='note_priority'), default='MEDIUM', nullable=False, index=True)
    
    # حقول جديدة للمستهدفين والإشعارات
    target_type = db.Column(db.String(50), index=True)  # نوع المستهدفين
    target_ids = db.Column(db.Text)  # معرفات المستهدفين مفصولة بفاصلة
    notification_type = db.Column(db.String(50), index=True)  # نوع الإشعار
    notification_date = db.Column(db.DateTime, index=True)  # تاريخ الإشعار
    is_sent = db.Column(db.Boolean, nullable=False, server_default=sa_text("0"), index=True)  # تم الإرسال

    author = relationship('User', backref='notes')

    __table_args__ = ()

    @validates('content')
    def _v_content(self, _, v):
        v = (v or '').strip()
        if not v:
            raise ValueError("content must not be empty")
        return v

    @validates('entity_type')
    def _v_entity_type(self, _, v):
        s = (v or '').strip().upper()
        return s or None

    @validates('entity_id')
    def _v_entity_id(self, _, v):
        s = (str(v or '')).strip()
        return s or None

    @validates('priority')
    def _v_priority(self, _, v):
        return getattr(v, 'value', (v or '')).strip().upper() or 'MEDIUM'

    @hybrid_property
    def short_preview(self) -> str:
        c = (self.content or '').strip()
        return (c[:97] + '...') if len(c) > 100 else c

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "author_id": self.author_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "is_pinned": bool(self.is_pinned),
            "priority": getattr(self.priority, "value", self.priority),
            "created_at": self.created_at.isoformat() if getattr(self, "created_at", None) else None,
            "updated_at": self.updated_at.isoformat() if getattr(self, "updated_at", None) else None,
        }

    def __repr__(self):
        et = (self.entity_type or '').upper()
        return f"<Note {self.id} {et}#{self.entity_id} pinned={bool(self.is_pinned)}>"


class Account(db.Model, TimestampMixin):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(sa_str_enum(["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"], name="account_type"), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = ()

    @validates("code", "name")
    def _v_req_strip(self, _, v):
        s = (v or "").strip()
        if not s:
            raise ValueError("value required")
        return s

    @validates("type")
    def _v_type(self, _, v):
        return getattr(v, "value", v)

    def __repr__(self):
        return f"<Account {self.code} {self.name}>"


class GLBatch(db.Model, TimestampMixin):
    __tablename__ = "gl_batches"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, index=True)
    source_type = db.Column(db.String(30), index=True)
    source_id = db.Column(db.Integer, index=True)
    purpose = db.Column(db.String(30), index=True)
    memo = db.Column(db.String(255))
    posted_at = db.Column(db.DateTime, index=True)
    currency = db.Column(db.String(10), default="ILS", nullable=False)
    entity_type = db.Column(db.String(30), index=True)
    entity_id = db.Column(db.Integer, index=True)
    status = db.Column(sa_str_enum(["DRAFT", "POSTED", "VOID"], name="gl_batch_status"), default="DRAFT", nullable=False, index=True)

    entries = db.relationship("GLEntry", backref="batch", cascade="all, delete-orphan", passive_deletes=True, order_by="GLEntry.id")

    __table_args__ = (
        db.UniqueConstraint("source_type", "source_id", "purpose", name="uq_gl_source_purpose"),
        db.Index("ix_gl_entity", "entity_type", "entity_id"),
        db.Index("ix_gl_status_source", "status", "source_type", "source_id"),
    )

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("status")
    def _v_status(self, _, v):
        return (getattr(v, "value", v) or "DRAFT").upper()

    def __repr__(self):
        return f"<GLBatch {self.code} {self.source_type}:{self.source_id}>"


@event.listens_for(GLBatch, "before_insert")
def _glb_before_insert(mapper, connection, target: "GLBatch"):
    target.currency = (target.currency or "ILS").upper()
    if not target.code:
        target.code = f"{target.source_type or 'SRC'}-{target.source_id or 0}-{target.purpose or 'PUR'}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if (target.status or "DRAFT").upper() == "POSTED" and not target.posted_at:
        target.posted_at = datetime.now(timezone.utc)


@event.listens_for(GLBatch, "before_update")
def _glb_before_update(mapper, connection, target: "GLBatch"):
    target.currency = (target.currency or "ILS").upper()
    st = (target.status or "DRAFT").upper()
    if st == "POSTED" and not target.posted_at:
        target.posted_at = datetime.now(timezone.utc)
    if st != "POSTED":
        target.posted_at = None


class GLEntry(db.Model, TimestampMixin):
    __tablename__ = "gl_entries"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("gl_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    account = db.Column(db.String(20), db.ForeignKey("accounts.code", ondelete="RESTRICT"), nullable=False, index=True)
    debit = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    credit = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="ILS", nullable=False)
    ref = db.Column(db.String(100))

    __table_args__ = (
        db.CheckConstraint("debit >= 0", name="ck_gl_debit_ge_0"),
        db.CheckConstraint("credit >= 0", name="ck_gl_credit_ge_0"),
        db.CheckConstraint("(debit > 0 OR credit > 0)", name="ck_gl_entry_nonzero"),
        db.CheckConstraint("(debit = 0 OR credit = 0)", name="ck_gl_entry_one_side"),
        db.Index("ix_gl_entries_account_currency", "account", "currency"),
        db.Index("ix_gl_entries_batch_account", "batch_id", "account"),
    )

    @validates("account")
    def _v_account(self, _, v):
        s = (v or "").strip().upper()
        if not s:
            raise ValueError("account required")
        return s

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("debit", "credit")
    def _v_amounts(self, key, v):
        if v is None:
            return 0
        if float(v) < 0:
            raise ValueError(f"{key} must be >= 0")
        return q(v)

    def __repr__(self):
        return f"<GLEntry {self.account} D:{self.debit} C:{self.credit}>"


GL_ACCOUNTS = {
    "AR": "1100_AR",
    "REV": "4000_SALES",
    "VAT": "2100_VAT_PAYABLE",
    "CASH": "1000_CASH",
    "BANK": "1010_BANK",
    "CARD": "1020_CARD_CLEARING",
    "AP": "2000_AP",
    "EXP": "5000_EXPENSES",
    "INV_EXCHANGE": "1205_INV_EXCHANGE",
    "COGS_EXCHANGE": "5105_COGS_EXCHANGE",
}


def _gl_upsert_batch_and_entries(
    connection,
    *,
    source_type: str,
    source_id: int,
    purpose: str,
    currency: str,
    memo: str,
    entries: list[tuple[str, float, float]],
    ref: str,
    entity_type: str | None,
    entity_id: int | None,
):
    if not entries:
        raise ValueError("entries required")
    rows = [(str(a or "").strip().upper(), float(d or 0), float(c or 0)) for a, d, c in entries]
    if any(d < 0 or c < 0 for _, d, c in rows):
        raise ValueError("negative amounts not allowed")
    total_debit = round(sum(d for _, d, _ in rows), 2)
    total_credit = round(sum(c for _, _, c in rows), 2)
    if total_debit != total_credit or total_debit <= 0:
        raise ValueError("unbalanced or zero batch")

    accs = [r[0] for r in rows]
    found = connection.execute(
        select(func.count(Account.code)).where(
            Account.code.in_(accs),
            Account.is_active.is_(True)
        )
    ).scalar() or 0
    if int(found) != len(set(accs)):
        raise ValueError("invalid or inactive account(s)")

    posted_exists = connection.execute(
        sa_text("""
            SELECT COUNT(1) FROM gl_batches
             WHERE source_type = :st AND source_id = :sid AND purpose = :p
               AND status = 'POSTED'
        """),
        {"st": source_type, "sid": source_id, "p": purpose}
    ).scalar() or 0
    if int(posted_exists) > 0:
        raise ValueError("cannot upsert: existing POSTED GL batch for same source/purpose")

    connection.execute(
        sa_text("""
            DELETE FROM gl_batches
             WHERE source_type = :st AND source_id = :sid AND purpose = :p
               AND status <> 'POSTED'
        """),
        {"st": source_type, "sid": source_id, "p": purpose}
    )

    batch_code = f"{source_type}-{source_id}-{purpose}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    cur = connection.execute(
        sa_text("""
            INSERT INTO gl_batches
                (code, source_type, source_id, purpose, memo, posted_at, currency, entity_type, entity_id, status, created_at, updated_at)
            VALUES
                (:code, :st, :sid, :p, :memo, NULL, :cur, :etype, :eid, 'DRAFT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """),
        {
            "code": batch_code,
            "st": source_type,
            "sid": source_id,
            "p": purpose,
            "memo": memo or "",
            "cur": (currency or "ILS").upper(),
            "etype": entity_type,
            "eid": entity_id,
        }
    )
    batch_id = cur.scalar_one()

    for acct, debit, credit in rows:
        connection.execute(
            sa_text("""
                INSERT INTO gl_entries
                    (batch_id, account, debit, credit, currency, ref, created_at, updated_at)
                VALUES
                    (:bid, :acc, :d, :c, :cur, :ref, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"bid": batch_id, "acc": acct, "d": debit, "c": credit, "cur": (currency or "ILS").upper(), "ref": ref or ""}
        )

    return int(batch_id)


# ===== نظام تقييمات المنتجات =====

class ProductRating(db.Model, TimestampMixin, AuditMixin):
    """تقييمات المنتجات"""
    __tablename__ = "product_ratings"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)  # يمكن أن يكون تقييم مجهول
    rating = Column(Integer, nullable=False)  # من 1 إلى 5
    title = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False, nullable=False)
    is_approved = Column(Boolean, default=True, nullable=False)  # للمراجعة
    helpful_count = Column(Integer, default=0, nullable=False)
    
    # العلاقات
    product = relationship("Product", backref="ratings")
    customer = relationship("Customer", backref="product_ratings")
    
    # فهارس
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
        Index("ix_product_ratings_product_id", "product_id"),
        Index("ix_product_ratings_customer_id", "customer_id"),
        Index("ix_product_ratings_rating", "rating"),
    )
    
    def to_dict(self):
        """تحويل التقييم إلى قاموس"""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else "عميل مجهول",
            "rating": self.rating,
            "title": self.title,
            "comment": self.comment,
            "is_verified_purchase": self.is_verified_purchase,
            "is_approved": self.is_approved,
            "helpful_count": self.helpful_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def get_product_ratings(cls, product_id, approved_only=True):
        """الحصول على تقييمات منتج معين"""
        query = cls.query.filter_by(product_id=product_id)
        if approved_only:
            query = query.filter_by(is_approved=True)
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_product_average_rating(cls, product_id):
        """الحصول على متوسط تقييم المنتج"""
        result = cls.query.filter_by(
            product_id=product_id,
            is_approved=True
        ).with_entities(
            func.avg(cls.rating).label('avg_rating'),
            func.count(cls.id).label('total_ratings')
        ).first()
        
        if result and result.avg_rating:
            return {
                'average': round(float(result.avg_rating), 1),
                'total': result.total_ratings
            }
        return {'average': 0, 'total': 0}
    
    @classmethod
    def get_rating_distribution(cls, product_id):
        """الحصول على توزيع التقييمات"""
        results = cls.query.filter_by(
            product_id=product_id,
            is_approved=True
        ).with_entities(
            cls.rating,
            func.count(cls.id).label('count')
        ).group_by(cls.rating).all()
        
        distribution = {i: 0 for i in range(1, 6)}
        for result in results:
            distribution[result.rating] = result.count
        
        return distribution


class ProductRatingHelpful(db.Model, TimestampMixin):
    """تقييمات مفيدة للتقييمات"""
    __tablename__ = "product_rating_helpful"
    
    id = Column(Integer, primary_key=True)
    rating_id = Column(Integer, ForeignKey("product_ratings.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    ip_address = Column(String(45), nullable=True)  # للعملاء غير المسجلين
    is_helpful = Column(Boolean, nullable=False)
    
    # العلاقات
    rating = relationship("ProductRating")
    customer = relationship("Customer")
    
    # فهارس
    __table_args__ = (
        Index("ix_rating_helpful_rating_id", "rating_id"),
        Index("ix_rating_helpful_customer_id", "customer_id"),
        Index("ix_rating_helpful_ip", "ip_address"),
    )
    
    @classmethod
    def mark_helpful(cls, rating_id, customer_id=None, ip_address=None, is_helpful=True):
        """تحديد التقييم كمفيد أو غير مفيد"""
        # التحقق من عدم التكرار
        existing = cls.query.filter_by(rating_id=rating_id)
        if customer_id:
            existing = existing.filter_by(customer_id=customer_id)
        elif ip_address:
            existing = existing.filter_by(ip_address=ip_address)
        
        existing = existing.first()
        
        if existing:
            existing.is_helpful = is_helpful
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_helpful = cls(
                rating_id=rating_id,
                customer_id=customer_id,
                ip_address=ip_address,
                is_helpful=is_helpful
            )
            db.session.add(new_helpful)
        
        # تحديث عداد المفيد
        rating = ProductRating.query.get(rating_id)
        if rating:
            helpful_count = cls.query.filter_by(
                rating_id=rating_id,
                is_helpful=True
            ).count()
            rating.helpful_count = helpful_count
            db.session.add(rating)
        
        db.session.commit()


# ===== نظام الولاء للعملاء =====

class CustomerLoyalty(db.Model, TimestampMixin, AuditMixin):
    """نظام الولاء للعملاء"""
    __tablename__ = "customer_loyalty"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True)
    total_points = Column(Integer, default=0, nullable=False)
    available_points = Column(Integer, default=0, nullable=False)
    used_points = Column(Integer, default=0, nullable=False)
    loyalty_tier = Column(String(50), default="BRONZE", nullable=False)  # BRONZE, SILVER, GOLD, PLATINUM
    total_spent = Column(Numeric(12, 2), default=0, nullable=False)
    last_activity = Column(DateTime, nullable=True)
    
    # العلاقات
    customer = relationship("Customer", backref="loyalty")
    
    # فهارس
    __table_args__ = (
        Index("ix_customer_loyalty_customer_id", "customer_id"),
        Index("ix_customer_loyalty_tier", "loyalty_tier"),
    )
    
    def to_dict(self):
        """تحويل بيانات الولاء إلى قاموس"""
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "total_points": self.total_points,
            "available_points": self.available_points,
            "used_points": self.used_points,
            "loyalty_tier": self.loyalty_tier,
            "total_spent": float(self.total_spent),
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }
    
    def add_points(self, points, reason="شراء"):
        """إضافة نقاط للعميل"""
        self.total_points += points
        self.available_points += points
        self.last_activity = datetime.now(timezone.utc)
        
        # إنشاء سجل النقاط
        point_record = CustomerLoyaltyPoints(
            customer_id=self.customer_id,
            points=points,
            reason=reason,
            type="EARNED"
        )
        db.session.add(point_record)
        
        # تحديث المستوى
        self.update_tier()
        
        db.session.add(self)
        db.session.commit()
    
    def use_points(self, points, reason="استرداد"):
        """استخدام نقاط العميل"""
        if self.available_points < points:
            raise ValueError("نقاط غير كافية")
        
        self.available_points -= points
        self.used_points += points
        self.last_activity = datetime.now(timezone.utc)
        
        # إنشاء سجل النقاط
        point_record = CustomerLoyaltyPoints(
            customer_id=self.customer_id,
            points=-points,
            reason=reason,
            type="USED"
        )
        db.session.add(point_record)
        
        db.session.add(self)
        db.session.commit()
    
    def update_tier(self):
        """تحديث مستوى الولاء"""
        spent = float(self.total_spent)
        
        if spent >= 10000:
            self.loyalty_tier = "PLATINUM"
        elif spent >= 5000:
            self.loyalty_tier = "GOLD"
        elif spent >= 2000:
            self.loyalty_tier = "SILVER"
        else:
            self.loyalty_tier = "BRONZE"
    
    @classmethod
    def get_or_create(cls, customer_id):
        """الحصول على أو إنشاء سجل ولاء للعميل"""
        loyalty = cls.query.filter_by(customer_id=customer_id).first()
        if not loyalty:
            loyalty = cls(customer_id=customer_id)
            db.session.add(loyalty)
            db.session.commit()
        return loyalty


class CustomerLoyaltyPoints(db.Model, TimestampMixin):
    """سجل نقاط الولاء"""
    __tablename__ = "customer_loyalty_points"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    points = Column(Integer, nullable=False)  # يمكن أن يكون سالب للاستخدام
    reason = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # EARNED, USED, EXPIRED, BONUS
    reference_id = Column(Integer, nullable=True)  # مرجع للعملية (مثل معرف الدفعة)
    reference_type = Column(String(50), nullable=True)  # نوع المرجع (PAYMENT, PURCHASE, etc.)
    expires_at = Column(DateTime, nullable=True)
    
    # العلاقات
    customer = relationship("Customer", backref="loyalty_points")
    
    # فهارس
    __table_args__ = (
        Index("ix_loyalty_points_customer_id", "customer_id"),
        Index("ix_loyalty_points_type", "type"),
        Index("ix_loyalty_points_expires", "expires_at"),
    )
    
    def to_dict(self):
        """تحويل سجل النقاط إلى قاموس"""
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "points": self.points,
            "reason": self.reason,
            "type": self.type,
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==========================================
# نموذج الشيكات المستقلة (Independent Checks)
# ==========================================

class CheckStatus(str, enum.Enum):
    """حالات الشيك"""
    PENDING = "PENDING"
    CASHED = "CASHED"
    RETURNED = "RETURNED"
    BOUNCED = "BOUNCED"
    RESUBMITTED = "RESUBMITTED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"
    
    @property
    def label(self):
        return {
            "PENDING": "معلق",
            "CASHED": "تم الصرف",
            "RETURNED": "مرتجع",
            "BOUNCED": "مرفوض",
            "RESUBMITTED": "أعيد للبنك",
            "CANCELLED": "ملغي",
            "OVERDUE": "متأخر"
        }[self.value]


class Check(db.Model, TimestampMixin, AuditMixin):
    """
    نموذج الشيكات المستقلة - للشيكات التي لا ترتبط بمدفوعات أو مصروفات
    يمكن إضافتها يدوياً من قبل المستخدم
    """
    __tablename__ = "checks"
    
    id = Column(Integer, primary_key=True)
    
    # معلومات الشيك الأساسية
    check_number = Column(String(100), nullable=False, index=True)
    check_bank = Column(String(200), nullable=False)
    check_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    check_due_date = Column(DateTime, nullable=False, index=True)
    
    # المبلغ والعملة
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="ILS", nullable=False)
    
    # سعر الصرف وقت إصدار الشيك (تاريخ المعاملة)
    fx_rate_issue = Column(Numeric(10, 6))  # سعر الصرف عند الإصدار
    fx_rate_issue_source = Column(String(20))  # مصدر السعر (online, manual, default)
    fx_rate_issue_timestamp = Column(DateTime)  # وقت الحصول على السعر
    fx_rate_issue_base = Column(String(10))  # العملة الأساسية
    fx_rate_issue_quote = Column(String(10))  # العملة المقابلة (ILS)
    
    # سعر الصرف وقت صرف الشيك (تاريخ الصرف الفعلي)
    fx_rate_cash = Column(Numeric(10, 6))  # سعر الصرف عند الصرف
    fx_rate_cash_source = Column(String(20))  # مصدر السعر
    fx_rate_cash_timestamp = Column(DateTime)  # وقت الصرف الفعلي
    fx_rate_cash_base = Column(String(10))  # العملة الأساسية
    fx_rate_cash_quote = Column(String(10))  # العملة المقابلة (ILS)
    
    # الاتجاه والحالة
    direction = Column(sa_str_enum(PaymentDirection, name="check_direction"), 
                      default=PaymentDirection.IN.value, nullable=False, index=True)
    status = Column(sa_str_enum(CheckStatus, name="check_status"), 
                   default=CheckStatus.PENDING.value, nullable=False, index=True)
    
    # معلومات الساحب (من يصدر الشيك)
    drawer_name = Column(String(200))  # اسم الساحب
    drawer_phone = Column(String(20))  # هاتف الساحب
    drawer_id_number = Column(String(50))  # رقم هوية الساحب
    drawer_address = Column(Text)  # عنوان الساحب
    
    # معلومات المستفيد (من يستلم الشيك)
    payee_name = Column(String(200))  # اسم المستفيد
    payee_phone = Column(String(20))  # هاتف المستفيد
    payee_account = Column(String(50))  # رقم حساب المستفيد
    
    # معلومات إضافية
    notes = Column(Text)  # ملاحظات عامة
    internal_notes = Column(Text)  # ملاحظات داخلية (لا تظهر للعميل)
    reference_number = Column(String(100))  # رقم مرجعي
    
    # تاريخ التغييرات (JSON)
    status_history = Column(Text)  # JSON array of status changes
    
    # الربط بعميل أو مورد (اختياري)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="SET NULL"), index=True)
    
    # من أنشأ الشيك
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # حقول الأرشيف
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    archived_at = Column(DateTime, index=True)
    archived_by = Column(Integer, ForeignKey("users.id"), index=True)
    archive_reason = Column(String(200))
    
    # العلاقات
    customer = relationship("Customer", backref="independent_checks")
    supplier = relationship("Supplier", backref="independent_checks")
    partner = relationship("Partner", backref="independent_checks")
    created_by = relationship("User", backref="checks_created", foreign_keys=[created_by_id])
    archived_by_user = relationship("User", foreign_keys=[archived_by])
    
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_check_amount_positive"),
        Index("ix_checks_status_due_date", "status", "check_due_date"),
        Index("ix_checks_direction_status", "direction", "status"),
    )
    
    def __repr__(self):
        return f"<Check {self.check_number} - {self.check_bank} - {self.amount} {self.currency}>"
    
    @hybrid_property
    def is_overdue(self):
        """هل الشيك متأخر"""
        if self.status in [CheckStatus.CASHED.value, CheckStatus.CANCELLED.value]:
            return False
        return self.check_due_date < datetime.now(timezone.utc)
    
    @hybrid_property
    def days_until_due(self):
        """عدد الأيام حتى الاستحقاق"""
        if isinstance(self.check_due_date, datetime):
            due_date = self.check_due_date.date()
        else:
            due_date = self.check_due_date
        today = datetime.now(timezone.utc).date()
        return (due_date - today).days
    
    @hybrid_property
    def is_due_soon(self):
        """هل الشيك قريب من الاستحقاق (خلال 7 أيام)"""
        return 0 <= self.days_until_due <= 7
    
    def add_status_change(self, new_status, reason=None, user=None):
        """إضافة تغيير حالة إلى السجل"""
        import json
        
        # تحميل السجل الحالي
        history = []
        if self.status_history:
            try:
                history = json.loads(self.status_history)
            except:
                history = []
        
        # إضافة التغيير الجديد
        change = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_status": self.status,
            "new_status": new_status,
            "reason": reason,
            "user": user.username if user else None
        }
        history.append(change)
        
        # حفظ السجل
        self.status_history = json.dumps(history, ensure_ascii=False)
        self.status = new_status
    
    def get_status_history(self):
        """الحصول على سجل التغييرات"""
        import json
        if not self.status_history:
            return []
        try:
            return json.loads(self.status_history)
        except:
            return []
    
    def get_entity_name(self):
        """الحصول على اسم الجهة المرتبطة"""
        if self.customer:
            return self.customer.name
        elif self.supplier:
            return self.supplier.name
        elif self.partner:
            return self.partner.name
        elif self.direction == PaymentDirection.IN.value:
            return self.drawer_name or "غير محدد"
        else:
            return self.payee_name or "غير محدد"
    
    def to_dict(self):
        """تحويل إلى قاموس"""
        return {
            "id": self.id,
            "check_number": self.check_number,
            "check_bank": self.check_bank,
            "check_date": self.check_date.isoformat() if self.check_date else None,
            "check_due_date": self.check_due_date.isoformat() if self.check_due_date else None,
            "amount": float(self.amount),
            "currency": self.currency,
            "direction": self.direction,
            "status": self.status,
            "drawer_name": self.drawer_name,
            "drawer_phone": self.drawer_phone,
            "payee_name": self.payee_name,
            "payee_phone": self.payee_phone,
            "notes": self.notes,
            "reference_number": self.reference_number,
            "entity_name": self.get_entity_name(),
            "is_overdue": self.is_overdue,
            "days_until_due": self.days_until_due,
            "is_due_soon": self.is_due_soon,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

# ==================== Event Listeners للشيكات ====================

@event.listens_for(Check, "before_insert", propagate=True)
def _check_before_insert(mapper, connection, target: "Check"):
    """تعيين سعر الصرف وقت إصدار الشيك تلقائياً"""
    check_currency = getattr(target, "currency", None) or "ILS"
    default_currency = "ILS"
    
    # تعيين سعر الصرف وقت الإصدار فقط إذا كانت العملة مختلفة
    if check_currency != default_currency:
        try:
            rate_info = get_fx_rate_with_fallback(check_currency, default_currency)
            if rate_info and rate_info.get('success'):
                target.fx_rate_issue = Decimal(str(rate_info.get('rate', 0)))
                target.fx_rate_issue_source = rate_info.get('source', 'unknown')
                target.fx_rate_issue_timestamp = datetime.now(timezone.utc)
                target.fx_rate_issue_base = check_currency
                target.fx_rate_issue_quote = default_currency
        except Exception:
            pass


@event.listens_for(Check, "before_update", propagate=True)
def _check_before_update(mapper, connection, target: "Check"):
    """تعيين سعر الصرف وقت صرف الشيك عند تغيير الحالة إلى CASHED"""
    check_currency = getattr(target, "currency", None) or "ILS"
    default_currency = "ILS"
    
    # الحصول على الحالة السابقة
    insp = inspect(target)
    hist = insp.attrs.status.history
    
    # إذا تم تغيير الحالة إلى CASHED وكانت العملة مختلفة
    if hist.has_changes() and target.status == CheckStatus.CASHED.value:
        if check_currency != default_currency and not target.fx_rate_cash:
            try:
                # محاولة الحصول على السعر الأونلاين أولاً
                try:
                    online_rate = _fetch_external_fx_rate(check_currency, default_currency, datetime.now(timezone.utc))
                    if online_rate and online_rate > Decimal("0"):
                        target.fx_rate_cash = online_rate
                        target.fx_rate_cash_source = 'online'
                        target.fx_rate_cash_timestamp = datetime.now(timezone.utc)
                        target.fx_rate_cash_base = check_currency
                        target.fx_rate_cash_quote = default_currency
                        return  # نجح الحصول على السعر الأونلاين
                except Exception:
                    pass  # إذا فشل، نستخدم السعر المحلي
                
                # إذا فشل الأونلاين، استخدم get_fx_rate_with_fallback
                rate_info = get_fx_rate_with_fallback(check_currency, default_currency)
                if rate_info and rate_info.get('success'):
                    target.fx_rate_cash = Decimal(str(rate_info.get('rate', 0)))
                    target.fx_rate_cash_source = rate_info.get('source', 'unknown')
                    target.fx_rate_cash_timestamp = datetime.now(timezone.utc)
                    target.fx_rate_cash_base = check_currency
                    target.fx_rate_cash_quote = default_currency
            except Exception:
                pass


# إضافة العلاقات المطلوبة لحل تحذيرات SQLAlchemy
# هذه العلاقات مطلوبة لحل التحذيرات المتعلقة بالعلاقات المتداخلة

# إضافة العلاقة في User model
User.archived_records = relationship(
    "Archive",
    foreign_keys="[Archive.archived_by]",
    back_populates="archiver",
    overlaps="archives,user"
)

# إضافة العلاقة في Archive model
Archive.archiver = relationship(
    "User",
    foreign_keys="[Archive.archived_by]",
    back_populates="archived_records",
    overlaps="archives,user"
)


# ========================================================================
# Event Listeners - تحديث أرصدة الشركاء تلقائياً
# ========================================================================

@event.listens_for(WarehousePartnerShare, 'after_insert')
@event.listens_for(WarehousePartnerShare, 'after_update')
@event.listens_for(WarehousePartnerShare, 'after_delete')
def _update_partner_on_share_change(mapper, connection, target):
    """
    تحديث رصيد الشريك عند تغيير نسبته في منتج
    """
    try:
        partner_id = target.partner_id
        if partner_id:
            # استخدام connection المتاح بدلاً من إنشاء session جديد
            update_partner_balance(partner_id, connection=connection)
    except Exception as e:
        pass


@event.listens_for(ShipmentItem, 'after_insert')
@event.listens_for(ShipmentItem, 'after_update') 
@event.listens_for(ShipmentItem, 'after_delete')
def _update_partner_on_shipment_item_change(mapper, connection, target):
    """
    تحديث أرصدة الشركاء المرتبطين بالمنتج عند تغيير بند الشحنة
    """
    try:
        # جلب الشركاء المرتبطين بهذا المنتج
        if target.product_id:
            result = connection.execute(
                sa_text("""
                    SELECT DISTINCT partner_id 
                    FROM warehouse_partner_shares 
                    WHERE product_id = :pid AND partner_id IS NOT NULL
                """),
                {"pid": target.product_id}
            )
            partner_ids = [row[0] for row in result]
            
            # تحديث رصيد كل شريك
            for partner_id in partner_ids:
                update_partner_balance(partner_id, connection=connection)
    except Exception as e:
        pass
