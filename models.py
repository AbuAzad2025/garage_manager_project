from __future__ import annotations

import enum
import json
import re
from datetime import datetime, timedelta
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
    inspect,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import object_session, relationship, Session as _SA_Session, validates

from extensions import db
from barcodes import normalize_barcode

TWO = Decimal("0.01")


def q(x) -> Decimal:
    try:
        return Decimal(str(x or 0)).quantize(TWO, ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None
# -------------------- Helpers --------------------
def sa_str_enum(enum_or_values, *, name: str):
    vals = [e.value for e in enum_or_values] if hasattr(enum_or_values, "__members__") else list(enum_or_values)
    return SAEnum(*vals, name=name, native_enum=False, validate_strings=True)

# ===================== Enums =====================
class PaymentMethod(str, enum.Enum):
    CASH   = "cash"
    BANK   = "bank"
    CARD   = "card"
    CHEQUE = "cheque"
    ONLINE = "online"

class PaymentStatus(str, enum.Enum):
    PENDING   = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    REFUNDED  = "REFUNDED"

class PaymentDirection(str, enum.Enum):
    INCOMING = "IN"
    OUTGOING = "OUT"

class InvoiceStatus(str, enum.Enum):
    UNPAID    = "UNPAID"
    PARTIAL   = "PARTIAL"
    PAID      = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED  = "REFUNDED"

class PaymentProgress(str, enum.Enum):
    PENDING  = "PENDING"
    PARTIAL  = "PARTIAL"
    PAID     = "PAID"
    REFUNDED = "REFUNDED"

class SaleStatus(str, enum.Enum):
    DRAFT     = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REFUNDED  = "REFUNDED"


class ServiceStatus(str, enum.Enum):
    PENDING      = "PENDING"
    DIAGNOSIS    = "DIAGNOSIS"
    IN_PROGRESS  = "IN_PROGRESS"
    COMPLETED    = "COMPLETED"
    CANCELLED    = "CANCELLED"
    ON_HOLD      = "ON_HOLD"

class ServicePriority(str, enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    URGENT = "URGENT"

class TransferDirection(str, enum.Enum):
    INCOMING   = "IN"
    OUTGOING   = "OUT"
    ADJUSTMENT = "ADJUSTMENT"

class PreOrderStatus(str, enum.Enum):
    PENDING   = "PENDING"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"

class WarehouseType(str, enum.Enum):
    MAIN      = "MAIN"
    PARTNER   = "PARTNER"
    INVENTORY = "INVENTORY"
    EXCHANGE  = "EXCHANGE"

class PaymentEntityType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    PARTNER  = "PARTNER"
    SHIPMENT = "SHIPMENT"
    EXPENSE  = "EXPENSE"
    LOAN     = "LOAN"
    SALE     = "SALE"
    INVOICE  = "INVOICE"
    PREORDER = "PREORDER"
    SERVICE  = "SERVICE"

class InvoiceSource(str, enum.Enum):
    MANUAL   = "MANUAL"
    SALE     = "SALE"
    SERVICE  = "SERVICE"
    PREORDER = "PREORDER"
    SUPPLIER = "SUPPLIER"
    PARTNER  = "PARTNER"
    ONLINE   = "ONLINE"

# ===================== M2M Tables =====================
user_permissions = db.Table(
    "user_permissions",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
    extend_existing=True,
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
    extend_existing=True,
)

# ===================== TimestampMixin =====================
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

# ===================== AuditMixin =====================
class AuditMixin:
    @classmethod
    def __declare_last__(cls):
        from sqlalchemy import inspect, event as _evt

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

# ===================== Permissions / Roles / Users =====================
class Permission(db.Model, AuditMixin):
    __tablename__ = "permissions"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False, index=True)
    code        = db.Column(db.String(100), unique=True, index=True)
    description = db.Column(db.String(255))

    @validates("name", "code")
    def _v_norm(self, key, value):
        v = (value or "").strip()
        if key == "code":
            v = v.lower()
        return v

    def key(self) -> str:
        return (self.code or self.name or "").strip().lower()

    def __repr__(self):
        return f"<Permission {self.code or self.name}>"

class Role(db.Model, AuditMixin):
    __tablename__ = "roles"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(200))
    is_default  = db.Column(db.Boolean, default=False, nullable=False)

    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        backref=db.backref("roles", lazy="selectin"),
    )

    __table_args__ = (
        db.Index("ix_roles_default_name", "is_default", "name"),
    )

    @validates("name")
    def _v_name(self, key, value):
        return (value or "").strip()

    def has_permission(self, perm_name: str) -> bool:
        if not perm_name:
            return False
        target = (perm_name or "").strip().lower()
        for p in self.permissions or []:
            code_l = (getattr(p, "code", "") or "").strip().lower()
            name_l = (getattr(p, "name", "") or "").strip().lower()
            if target in {code_l, name_l}:
                return True
        return False

    def __repr__(self):
        return f"<Role {self.name}>"

SUPER_ROLES = {"developer", "owner", "super_admin"}

class User(db.Model, UserMixin, TimestampMixin, AuditMixin):
    __tablename__ = "users"

    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(50),  unique=True, nullable=False, index=True)
    email           = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash   = db.Column(db.String(128), nullable=False)
    role_id         = db.Column(db.Integer, db.ForeignKey("roles.id"), index=True)
    _is_active      = db.Column("is_active", db.Boolean, nullable=False, server_default=text("1"))
    last_login      = db.Column(db.DateTime)
    last_seen       = db.Column(db.DateTime)
    last_login_ip   = db.Column(db.String(64))
    login_count     = db.Column(db.Integer, nullable=False, server_default=text("0"))

    role = relationship("Role", backref="users", lazy="joined")

    extra_permissions = relationship(
        "Permission",
        secondary=user_permissions,
        backref=db.backref("users_extra", lazy="dynamic"),
        lazy="dynamic",
    )

    service_requests = relationship("ServiceRequest", back_populates="mechanic", lazy="dynamic")
    sales            = relationship("Sale", back_populates="seller", cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_users_role_active", "role_id", "is_active"),
    )

    @property
    def is_active(self):
        return bool(self._is_active)

    @is_active.setter
    def is_active(self, value):
        self._is_active = bool(value)

    @property
    def role_name_l(self) -> str:
        return (getattr(self.role, "name", "") or "").strip().lower()

    @property
    def is_super_role(self) -> bool:
        return self.role_name_l in {"developer", "owner", "super_admin"}

    @property
    def is_admin_role(self) -> bool:
        return self.role_name_l == "admin"

    @validates("email")
    def _v_email(self, key, value):
        return (value or "").strip().lower()

    @validates("username")
    def _v_username(self, key, value):
        return (value or "").strip()

    def set_password(self, password: str) -> None:
        method = "scrypt"
        try:
            from flask import current_app as _ca
            if _ca:
                method = _ca.config.get("PASSWORD_HASH_METHOD") or "scrypt"
        except Exception:
            pass
        try:
            self.password_hash = generate_password_hash(password, method=method)
        except Exception:
            self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        try:
            return check_password_hash(self.password_hash, password)
        except Exception:
            return False

    def has_role(self, *names: str) -> bool:
        r = (getattr(self.role, "name", "") or "").strip().lower()
        return any(r == (n or "").strip().lower() for n in names if n)

    def has_permission(self, name: str) -> bool:
        target = (name or "").strip().lower()
        if not target:
            return False
        if self.is_super_role:
            return True
        try:
            if self.role and hasattr(self.role, "has_permission") and callable(self.role.has_permission):
                if self.role.has_permission(target):
                    return True
        except Exception:
            pass
        try:
            if hasattr(self, "extra_permissions") and hasattr(self.extra_permissions, "filter"):
                return self.extra_permissions.filter(
                    or_(
                        func.lower(Permission.name) == target,
                        func.lower(Permission.code) == target,
                    )
                ).first() is not None
        except Exception:
            try:
                for p in (self.extra_permissions or []):
                    code_l = (getattr(p, "code", "") or "").strip().lower()
                    name_l = (getattr(p, "name", "") or "").strip().lower()
                    if target in {code_l, name_l}:
                        return True
            except Exception:
                pass
        return False

    def __repr__(self):
        return f"<User {self.username or self.id}>"
# ===================== Customers =====================
class Customer(db.Model, UserMixin, TimestampMixin, AuditMixin):
    __tablename__ = "customers"

    id            = Column(Integer, primary_key=True)
    name          = Column(String(100), nullable=False)
    phone         = Column(String(20), unique=True, nullable=False)
    whatsapp      = Column(String(20), nullable=False)
    email         = Column(String(120), unique=True, nullable=False)
    address       = Column(String(200))
    password_hash = Column(String(128))
    category      = Column(String(20), default="عادي")
    notes         = Column(Text)
    is_active     = Column(Boolean, default=True)
    is_online     = Column(Boolean, default=False)
    credit_limit  = Column(Numeric(12, 2), default=0)
    discount_rate = Column(Numeric(5, 2), default=0)
    currency      = Column(String(10), default="ILS", nullable=False)

    sales            = relationship("Sale", back_populates="customer")
    preorders        = relationship("PreOrder", back_populates="customer")
    invoices         = relationship("Invoice", back_populates="customer")
    payments         = relationship("Payment", back_populates="customer")
    service_requests = relationship("ServiceRequest", back_populates="customer")
    online_carts     = relationship("OnlineCart", back_populates="customer")
    online_preorders = relationship("OnlinePreOrder", back_populates="customer")

    __table_args__ = (
        db.Index("ix_customers_active_online", "is_active", "is_online"),
        db.Index("ix_customers_name", "name"),
    )

    @property
    def password(self):
        raise AttributeError("Password access not allowed")

    @password.setter
    def password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, *_args, **_kwargs) -> bool:
        return False

    def is_valid_email(self):
        return bool(self.email and "@" in self.email)

    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower()

    @validates("name", "address", "category", "notes")
    def _v_strip(self, _, v):
        return (v or "").strip() or None

    @validates("phone", "whatsapp")
    def _v_phone(self, key, v):
        return (v or "").strip()

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("discount_rate")
    def _v_discount_rate(self, _, v):
        if v is None:
            return 0
        if float(v) < 0 or float(v) > 100:
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
            .filter(Invoice.customer_id == self.id)
            .scalar()
        )

    @total_invoiced.expression
    def total_invoiced(cls):
        return (
            select(func.coalesce(func.sum(Invoice.total_amount), 0))
            .where(Invoice.customer_id == cls.id)
            .label("total_invoiced")
        )

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.customer_id == self.id,
                Payment.direction == PaymentDirection.INCOMING.value,
                Payment.status == PaymentStatus.COMPLETED.value,
            )
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.customer_id == cls.id) &
                (Payment.direction == PaymentDirection.INCOMING.value) &
                (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def balance(self):
        return self.total_invoiced - self.total_paid

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
            "discount_rate": float(self.discount_rate or 0),
            "credit_limit": float(self.credit_limit or 0),
            "total_invoiced": self.total_invoiced,
            "total_paid": self.total_paid,
            "balance": self.balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Customer {self.name}>"

@event.listens_for(Customer, "before_insert")
def _customer_before_insert(_mapper, _connection, target: Customer):
    target.email = (target.email or "").strip().lower()
    target.phone = (target.phone or "").strip()
    target.whatsapp = (target.whatsapp or target.phone or "").strip()
    target.currency = (target.currency or "ILS").upper()
@event.listens_for(Customer, "before_update")
def _customer_before_update(_mapper, _connection, target: Customer):
    target.email = (target.email or "").strip().lower()
    target.phone = (target.phone or "").strip()
    target.whatsapp = (target.whatsapp or target.phone or "").strip()
    target.currency = (target.currency or "ILS").upper()
# ===================== Suppliers =====================
class Supplier(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "suppliers"

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    is_local        = db.Column(db.Boolean, default=True)
    identity_number = db.Column(db.String(100), unique=True)
    contact         = db.Column(db.String(200))
    phone           = db.Column(db.String(20), index=True)
    email           = db.Column(db.String(120), unique=True, index=True, nullable=True)
    address         = db.Column(db.String(200))
    notes           = db.Column(db.Text)
    balance         = db.Column(db.Numeric(12, 2), default=0)
    payment_terms   = db.Column(db.String(50))
    currency        = db.Column(db.String(10), default="ILS", nullable=False)

    payments         = db.relationship("Payment", back_populates="supplier")
    invoices         = db.relationship("Invoice", back_populates="supplier")
    preorders        = db.relationship("PreOrder", back_populates="supplier")
    warehouses       = db.relationship("Warehouse", back_populates="supplier")
    loan_settlements = db.relationship(
        "SupplierLoanSettlement",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.Index("ix_suppliers_name", "name"),
    )

    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower() or None

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("name", "contact", "address", "notes", "payment_terms", "phone", "identity_number")
    def _v_strip(self, _, v):
        return (v or "").strip() or None

    # --- Aggregates ---
    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.supplier_id == self.id,
                Payment.direction == PaymentDirection.OUTGOING.value,
                Payment.status == PaymentStatus.COMPLETED.value
            )
            .scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.supplier_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value) &
                (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def net_balance(self):
        return float(self.balance or 0) - self.total_paid

    @net_balance.expression
    def net_balance(cls):
        paid_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.supplier_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value) &
                (Payment.status == PaymentStatus.COMPLETED.value)
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
            "balance": float(self.balance or 0),
            "total_paid": self.total_paid,
            "net_balance": self.net_balance,
        }

    def __repr__(self):
        return f"<Supplier {self.name}>"

@event.listens_for(Supplier, "before_insert")
def _supplier_before_insert(_m, _c, t: Supplier):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()
@event.listens_for(Supplier, "before_update")
def _supplier_before_update(_m, _c, t: Supplier):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()
# ===================== Partners =====================
class Partner(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'partners'

    id               = Column(Integer, primary_key=True)
    name             = Column(String(100), nullable=False)
    contact_info     = Column(String(200))
    identity_number  = Column(String(100), unique=True)
    phone_number     = Column(String(20), unique=True)
    email            = Column(String(120), unique=True, index=True, nullable=True)
    address          = Column(String(200))
    balance          = Column(Numeric(12, 2), default=0)
    share_percentage = Column(Numeric(5, 2), default=0)
    currency         = Column(String(10), default='ILS', nullable=False)

    warehouses        = relationship('Warehouse', back_populates='partner')
    payments          = relationship('Payment', back_populates='partner')
    preorders         = relationship('PreOrder', back_populates='partner')
    invoices          = relationship('Invoice', back_populates='partner')
    shipment_partners = relationship('ShipmentPartner', back_populates='partner')

    warehouse_shares = relationship(
        'WarehousePartnerShare',
        back_populates='partner',
        cascade='all, delete-orphan',
        overlaps="shares,product_shares"
    )
    shares = relationship(
        'WarehousePartnerShare',
        back_populates='partner',
        cascade='all, delete-orphan',
        overlaps="warehouse_shares,product_shares"
    )
    product_shares = relationship(
        'ProductPartnerShare',
        back_populates='partner',
        cascade='all, delete-orphan',
        overlaps="shares,warehouse_shares"
    )

    product_links = relationship(
        'ProductPartner',
        back_populates='partner',
        cascade='all, delete-orphan'
    )

    service_parts = relationship('ServicePart', back_populates='partner')
    service_tasks = relationship('ServiceTask', back_populates='partner')
    expenses      = relationship('Expense', back_populates='partner')

    __table_args__ = (
        db.Index("ix_partners_name", "name"),
    )

    # --- Validations ---
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
        if float(v) < 0 or float(v) > 100:
            raise ValueError("share_percentage must be between 0 and 100")
        return v

    @validates("name", "contact_info", "address", "identity_number", "phone_number")
    def _v_strip(self, _, v):
        return (v or "").strip() or None

    # --- Aggregates ---
    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.partner_id == self.id,
                Payment.direction == PaymentDirection.OUTGOING.value,
                Payment.status == PaymentStatus.COMPLETED.value
            )
            .scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.partner_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value) &
                (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def net_balance(self):
        return float(self.balance or 0) - self.total_paid

    @net_balance.expression
    def net_balance(cls):
        paid_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.partner_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value) &
                (Payment.status == PaymentStatus.COMPLETED.value)
            )
            .scalar_subquery()
        )
        return cls.balance - paid_subq

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'email':       self.email,
            'currency':    self.currency,
            'balance':     float(self.balance or 0),
            'total_paid':  self.total_paid,
            'net_balance': self.net_balance,
        }

    def __repr__(self):
        return f"<Partner {self.name}>"


@event.listens_for(Partner, "before_insert")
def _partner_before_insert(_m, _c, t: Partner):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()

@event.listens_for(Partner, "before_update")
def _partner_before_update(_m, _c, t: Partner):
    t.email = (t.email or "").strip().lower() or None
    t.currency = (t.currency or "ILS").upper()
# ===================== Employees =====================
class Employee(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'employees'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    position       = db.Column(db.String(100))
    phone          = db.Column(db.String(100))
    email          = db.Column(db.String(120), unique=True, index=True, nullable=True)
    bank_name      = db.Column(db.String(100))
    account_number = db.Column(db.String(100))
    notes          = db.Column(db.Text)
    currency       = db.Column(db.String(10), default='ILS', nullable=False)

    expenses = db.relationship(
        'Expense',
        back_populates='employee',
        cascade='all, delete-orphan'
    )

    __table_args__ = (
        db.Index("ix_employees_name", "name"),
    )

    # --- Validations ---
    @validates("email")
    def _v_email(self, _, v):
        return (v or "").strip().lower() or None

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @validates("name", "position", "phone", "bank_name", "account_number", "notes")
    def _v_strip(self, _, v):
        return (v or "").strip() or None

    # --- إجمالي المصاريف ---
    @hybrid_property
    def total_expenses(self):
        return float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(Expense.employee_id == self.id)
            .scalar()
        )

    @total_expenses.expression
    def total_expenses(cls):
        return (
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.employee_id == cls.id)
            .label("total_expenses")
        )

    # --- المدفوع ---
    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .join(Expense, Payment.expense_id == Expense.id)
            .filter(
                Expense.employee_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUTGOING.value,
            )
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .select_from(
                Payment.__table__.join(Expense, Payment.expense_id == Expense.id)
            )
            .where(
                (Expense.employee_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.OUTGOING.value)
            )
            .label("total_paid")
        )

    # --- الرصيد ---
    @hybrid_property
    def balance(self):
        return self.total_expenses - self.total_paid

    @balance.expression
    def balance(cls):
        # استخدام التعبيرات المعرفة للأعلى يضمن SQL صحيح
        return cls.total_expenses - cls.total_paid

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'email':          self.email,
            'position':       self.position,
            'phone':          self.phone,
            'currency':       self.currency,
            'total_expenses': self.total_expenses,
            'total_paid':     self.total_paid,
            'balance':        self.balance,
        }

    def __repr__(self):
        return f"<Employee {self.name}>"
    
# ==================== Catalog & Inventory =====================
class EquipmentType(db.Model, TimestampMixin):
    __tablename__ = 'equipment_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    model_number = db.Column(db.String(100))
    chassis_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    category = db.Column(db.String(50))

    products = db.relationship('Product', back_populates='vehicle_type')
    service_requests = db.relationship('ServiceRequest', back_populates='vehicle_type')

    def __repr__(self):
        return f"<EquipmentType {self.name}>"

class ProductCategory(db.Model, TimestampMixin):
    __tablename__ = 'product_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('product_categories.id'))
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))

    parent = db.relationship('ProductCategory', remote_side=[id], backref='subcategories')
    products = db.relationship('Product', back_populates='category')

    def __repr__(self):
        return f"<ProductCategory {self.name}>"

class ProductCondition(enum.Enum):
    NEW         = "NEW"
    USED        = "USED"
    REFURBISHED = "REFURBISHED"
    
class Product(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    part_number = Column(String(100), index=True)
    brand = Column(String(100), index=True)
    commercial_name = Column(String(100))
    chassis_number = Column(String(100))
    serial_no = Column(String(100), unique=True)
    barcode = Column(String(100), unique=True)
    unit = Column(String(50))
    category_name = Column(String(100))
    purchase_price = Column(Numeric(12, 2), default=0)
    selling_price = Column(Numeric(12, 2), default=0)
    cost_before_shipping = Column(Numeric(12, 2), default=0)
    cost_after_shipping = Column(Numeric(12, 2), default=0)
    unit_price_before_tax = Column(Numeric(12, 2), default=0)
    price = Column(Numeric(12, 2), nullable=False, default=0)
    min_price = Column(Numeric(12, 2))
    max_price = Column(Numeric(12, 2))
    tax_rate = Column(Numeric(5, 2), default=0)
    min_qty = Column(Integer, default=0)
    reorder_point = Column(Integer)
    image = Column(String(255))
    notes = Column(Text)
    condition = Column(sa_str_enum(ProductCondition, name='product_condition'), default=ProductCondition.NEW.value, nullable=False)
    origin_country = Column(String(50))
    warranty_period = Column(Integer)
    weight = Column(Numeric(10, 2))
    dimensions = Column(String(50))
    is_active = Column(Boolean, default=True)
    is_digital = Column(Boolean, default=False)
    is_exchange = Column(Boolean, default=False)
    vehicle_type_id = Column(Integer, ForeignKey('equipment_types.id'))
    category_id = Column(Integer, ForeignKey('product_categories.id'))
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    supplier_international_id = Column(Integer, ForeignKey('suppliers.id'))
    supplier_local_id = Column(Integer, ForeignKey('suppliers.id'))

    __table_args__ = (
        CheckConstraint('price >= 0', name='ck_product_price_ge_0'),
        CheckConstraint('purchase_price >= 0', name='ck_product_purchase_ge_0'),
        CheckConstraint('selling_price >= 0', name='ck_product_selling_ge_0'),
        CheckConstraint('cost_before_shipping >= 0', name='ck_product_cost_before_ge_0'),
        CheckConstraint('cost_after_shipping >= 0', name='ck_product_cost_after_ge_0'),
        CheckConstraint('unit_price_before_tax >= 0', name='ck_product_unit_before_tax_ge_0'),
        CheckConstraint('min_price IS NULL OR min_price >= 0', name='ck_product_min_price_ge_0'),
        CheckConstraint('max_price IS NULL OR max_price >= 0', name='ck_product_max_price_ge_0'),
        CheckConstraint('tax_rate >= 0 AND tax_rate <= 100', name='ck_product_tax_rate_0_100'),
        CheckConstraint('min_qty >= 0', name='ck_product_min_qty_ge_0'),
        CheckConstraint('reorder_point IS NULL OR reorder_point >= 0', name='ck_product_reorder_ge_0'),
        CheckConstraint('weight IS NULL OR weight >= 0', name='ck_product_weight_ge_0'),
        Index('ix_products_brand_part', 'brand', 'part_number'),
    )

    category = relationship('ProductCategory', back_populates='products')
    vehicle_type = relationship('EquipmentType', back_populates='products')
    supplier_general = relationship('Supplier', foreign_keys=[supplier_id])
    supplier_international = relationship('Supplier', foreign_keys=[supplier_international_id])
    supplier_local = relationship('Supplier', foreign_keys=[supplier_local_id])
    partners = relationship('ProductPartner', back_populates='product')
    partner_shares = relationship('ProductPartnerShare', back_populates='product')
    supplier_loans = relationship('ProductSupplierLoan', back_populates='product')
    transfers = relationship('Transfer', back_populates='product')
    preorders = relationship('PreOrder', back_populates='product')
    shipment_items = relationship('ShipmentItem', back_populates='product')
    exchange_transactions = relationship('ExchangeTransaction', back_populates='product')
    sale_lines = relationship('SaleLine', back_populates='product')
    service_parts = relationship('ServicePart', back_populates='part')
    online_cart_items = relationship('OnlineCartItem', back_populates='product')
    online_preorder_items = relationship('OnlinePreOrderItem', back_populates='product')
    stock_levels = relationship('StockLevel', back_populates='product')

    def __init__(self, **kwargs):
        self.category_name = (kwargs.pop('category', None) or None)
        self.unit = (kwargs.pop('unit', None) or None)
        self.purchase_price = kwargs.pop('purchase_price', 0)
        self.selling_price = kwargs.pop('selling_price', kwargs.get('price', 0))
        self.notes = kwargs.pop('notes', None)
        super().__init__(**kwargs)

    @validates('sku', 'serial_no', 'barcode')
    def _v_strip_norm_ids(self, key, v):
        if v is None:
            return None
        v = str(v).strip()
        if key in ('sku', 'serial_no'):
            v = v.upper()
        if key == 'barcode':
            from barcodes import normalize_barcode
            v = normalize_barcode(v) or None
        return v

    @validates('name', 'brand', 'part_number', 'commercial_name', 'chassis_number', 'category_name', 'origin_country', 'dimensions', 'unit')
    def _v_strip_texts(self, key, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @validates('purchase_price', 'selling_price', 'cost_before_shipping', 'cost_after_shipping', 'unit_price_before_tax', 'price', 'min_price', 'max_price', 'tax_rate', 'weight')
    def _v_money_numeric(self, key, v):
        if v is None or v == "":
            return 0 if key in ('price', 'purchase_price', 'selling_price', 'cost_before_shipping', 'cost_after_shipping', 'unit_price_before_tax') else None
        if isinstance(v, str):
            v = v.replace('$', '').replace(',', '').strip()
        d = Decimal(str(v))
        if key == 'tax_rate' and (d < 0 or d > Decimal('100')):
            raise ValueError("tax_rate must be between 0 and 100")
        if d < 0:
            raise ValueError(f"{key} must be >= 0")
        return d

    @validates('min_qty', 'reorder_point', 'warranty_period')
    def _v_int_nonneg(self, key, v):
        if v in (None, ""):
            return None if key == 'reorder_point' else 0
        i = int(v)
        if i < 0:
            raise ValueError(f"{key} must be >= 0")
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
        mapping = {
            ProductCondition.NEW.value: "جديد",
            ProductCondition.USED.value: "مستعمل",
            ProductCondition.REFURBISHED.value: "مجدّد",
        }
        val = getattr(self.condition, "value", self.condition)
        return mapping.get(val, val)

    def __repr__(self):
        return f"<Product {self.name}>"
       
class Warehouse(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'warehouses'

    id            = Column(db.Integer, primary_key=True)
    name          = Column(db.String(100), nullable=False)

    warehouse_type = Column(sa_str_enum(WarehouseType, name='warehouse_type'),
                            default=WarehouseType.MAIN.value, nullable=False)

    location           = Column(db.String(200))
    is_active          = Column(db.Boolean, default=True)
    parent_id          = Column(db.Integer, db.ForeignKey('warehouses.id'))
    supplier_id        = Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id         = Column(db.Integer, db.ForeignKey('partners.id'))
    share_percent      = Column(db.Numeric(5, 2), default=0)
    capacity           = Column(db.Integer)
    current_occupancy  = Column(db.Integer, default=0)
    notes              = Column(db.Text)

    parent   = db.relationship('Warehouse', remote_side=[id], backref='children')
    supplier = db.relationship('Supplier', back_populates='warehouses')
    partner  = db.relationship('Partner', back_populates='warehouses')

    stock_levels            = db.relationship('StockLevel', back_populates='warehouse')
    transfers_source        = db.relationship('Transfer', back_populates='source_warehouse', foreign_keys='Transfer.source_id')
    transfers_destination   = db.relationship('Transfer', back_populates='destination_warehouse', foreign_keys='Transfer.destination_id')
    sale_lines              = db.relationship('SaleLine', back_populates='warehouse')
    service_parts           = db.relationship('ServicePart', back_populates='warehouse')
    exchange_transactions   = db.relationship('ExchangeTransaction', back_populates='warehouse')
    shipment_items          = db.relationship('ShipmentItem', back_populates='warehouse')
    shipments_received      = db.relationship('Shipment', back_populates='destination_warehouse', foreign_keys='Shipment.destination_id')
    preorders               = db.relationship('PreOrder', back_populates='warehouse')
    partner_shares          = db.relationship('WarehousePartnerShare', back_populates='warehouse')
    expenses                = db.relationship('Expense', back_populates='warehouse')

    @hybrid_property
    def warehouse_type_display(self):
        mapping = {
            WarehouseType.MAIN.value: "رئيسي",
            WarehouseType.INVENTORY.value: "مخزن",
            WarehouseType.EXCHANGE.value: "تبادل",
            WarehouseType.PARTNER.value: "شريك",
        }
        wt = getattr(self, "warehouse_type", None)
        key = getattr(wt, "value", wt)
        return mapping.get(key, key)

    def __repr__(self):
        return f"<Warehouse {self.name}>"

class StockLevel(db.Model, TimestampMixin):
    __tablename__ = 'stock_levels'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reserved_quantity = db.Column(db.Integer, nullable=False, default=0)
    min_stock = db.Column(db.Integer)
    max_stock = db.Column(db.Integer)

    __table_args__ = (
        CheckConstraint('quantity >= 0', name='ck_stock_non_negative'),
        CheckConstraint('reserved_quantity >= 0', name='ck_reserved_non_negative'),
        CheckConstraint('(min_stock IS NULL OR min_stock >= 0)', name='ck_min_non_negative'),
        CheckConstraint('(max_stock IS NULL OR max_stock >= 0)', name='ck_max_non_negative'),
        CheckConstraint('(min_stock IS NULL OR max_stock IS NULL OR max_stock >= min_stock)', name='ck_max_ge_min'),
        db.UniqueConstraint('product_id', 'warehouse_id', name='uq_stock_product_wh'),
        db.Index('ix_stock_product_wh', 'product_id', 'warehouse_id'),
    )

    product = db.relationship('Product', back_populates='stock_levels')
    warehouse = db.relationship('Warehouse', back_populates='stock_levels')

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v < 0:
            raise ValueError("quantity must be >= 0")
        return v

    @validates('reserved_quantity')
    def _v_reserved_qty(self, _, v):
        v = int(v)
        if v < 0:
            raise ValueError("reserved_quantity must be >= 0")
        return v

    @hybrid_property
    def available_quantity(self):
        return int(self.quantity or 0) - int(self.reserved_quantity or 0)

    @hybrid_property
    def partner_share_quantity(self):
        wh = getattr(self, 'warehouse', None)
        if not wh:
            return 0
        wt = getattr(wh.warehouse_type, 'value', wh.warehouse_type)
        share = float(getattr(wh, 'share_percent', 0) or 0)
        return self.quantity * share / 100.0 if wt == WarehouseType.PARTNER.value and share else 0

    @hybrid_property
    def company_share_quantity(self):
        wh = getattr(self, 'warehouse', None)
        if not wh:
            return self.quantity
        wt = getattr(wh.warehouse_type, 'value', wh.warehouse_type)
        return self.quantity - self.partner_share_quantity if wt == WarehouseType.PARTNER.value and wh.share_percent else self.quantity

    @hybrid_property
    def status(self):
        q = int(self.quantity or 0)
        mn = int(self.min_stock or 0)
        mx = self.max_stock
        if q == mn:
            return "عند الحد الأدنى"
        elif q < mn:
            return "تحت الحد الأدنى"
        elif mx is not None:
            if q == int(mx):
                return "عند الحد الأقصى"
            elif q > int(mx):
                return "فوق الحد الأقصى"
        return "طبيعي"

    @property
    def last_updated(self):
        return self.updated_at

# ---------- Stock helpers (atomic) ----------
def _ensure_stock_row(connection, product_id: int, warehouse_id: int):
    row = connection.execute(
        text("SELECT id FROM stock_levels WHERE product_id = :p AND warehouse_id = :w"),
        {"p": product_id, "w": warehouse_id}
    ).first()
    if row:
        return row
    # Upsert-ish create if missing
    dialect = getattr(connection, "dialect", None)
    dname = getattr(dialect, "name", "") if dialect else ""
    try:
        if dname.startswith("postgre"):
            connection.execute(
                text("""
                    INSERT INTO stock_levels (product_id, warehouse_id, quantity, reserved_quantity)
                    VALUES (:p, :w, 0, 0)
                    ON CONFLICT (product_id, warehouse_id) DO NOTHING
                """),
                {"p": product_id, "w": warehouse_id}
            )
        else:
            connection.execute(
                text("""
                    INSERT INTO stock_levels (product_id, warehouse_id, quantity, reserved_quantity)
                    SELECT :p, :w, 0, 0
                    WHERE NOT EXISTS (
                        SELECT 1 FROM stock_levels WHERE product_id = :p AND warehouse_id = :w
                    )
                """),
                {"p": product_id, "w": warehouse_id}
            )
    except Exception:
        pass
    return connection.execute(
        text("SELECT id FROM stock_levels WHERE product_id = :p AND warehouse_id = :w"),
        {"p": product_id, "w": warehouse_id}
    ).first()


def _apply_stock_delta(connection, product_id: int, warehouse_id: int, delta_qty: int):
    row = _ensure_stock_row(connection, product_id, warehouse_id)
    sid = row._mapping["id"]
    q = int(delta_qty or 0)
    if q == 0:
        qty = connection.execute(text("SELECT quantity FROM stock_levels WHERE id = :id"), {"id": sid}).scalar_one()
        return int(qty)
    if q > 0:
        connection.execute(
            text("UPDATE stock_levels SET quantity = quantity + :q WHERE id = :id"),
            {"id": sid, "q": q}
        )
    else:
        res = connection.execute(
            text("""
                UPDATE stock_levels
                SET quantity = quantity + :q
                WHERE id = :id
                  AND quantity + :q >= 0
                  AND quantity + :q >= reserved_quantity
            """),
            {"id": sid, "q": q}
        )
        if getattr(res, "rowcount", None) != 1:
            raise Exception("الكمية غير كافية في المخزن لهذا الإخراج/التعديل")
    qty = connection.execute(text("SELECT quantity FROM stock_levels WHERE id = :id"), {"id": sid}).scalar_one()
    return int(qty)

class Transfer(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'transfers'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    direction = db.Column(sa_str_enum(TransferDirection, name='transfer_direction'), nullable=False)
    transfer_date = db.Column(DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    product = db.relationship('Product', back_populates='transfers')
    source_warehouse = db.relationship('Warehouse', foreign_keys=[source_id], back_populates='transfers_source')
    destination_warehouse = db.relationship('Warehouse', foreign_keys=[destination_id], back_populates='transfers_destination')
    user = db.relationship('User')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_transfer_qty_positive'),
        db.CheckConstraint('source_id <> destination_id', name='chk_transfer_diff_wh'),
        db.Index('ix_transfers_transfer_date', 'transfer_date'),
    )

    @validates('quantity')
    def validate_quantity(self, key, quantity):
        if quantity is None or quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
        return int(quantity)

    def __repr__(self):
        return f"<Transfer {self.reference}>"

@event.listens_for(Transfer, 'before_insert', propagate=True)
def _ensure_transfer_reference(mapper, connection, target):
    if getattr(target, 'reference', None):
        return
    prefix = datetime.utcnow().strftime("TRF%Y%m%d")
    count = connection.execute(
        text("SELECT COUNT(*) FROM transfers WHERE reference LIKE :pfx"),
        {"pfx": f"{prefix}-%"}
    ).scalar() or 0
    target.reference = f"{prefix}-{count+1:04d}"


@event.listens_for(Transfer, "after_insert", propagate=True)
def _transfer_after_insert(mapper, connection, target: "Transfer"):
    qty = int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.source_id, -qty)
    _apply_stock_delta(connection, target.product_id, target.destination_id, +qty)

@event.listens_for(Transfer, "after_update", propagate=True)
def _transfer_after_update(mapper, connection, target: "Transfer"):
    prev = getattr(target, "_previous_state", None) or {}
    if not any(k in prev for k in ("product_id", "source_id", "destination_id", "quantity")):
        return
    old_pid = prev.get("product_id", target.product_id)
    old_src = prev.get("source_id", target.source_id)
    old_dst = prev.get("destination_id", target.destination_id)
    old_qty = int(prev.get("quantity", target.quantity) or 0)
    _apply_stock_delta(connection, old_pid, old_src, +old_qty)
    _apply_stock_delta(connection, old_pid, old_dst, -old_qty)
    new_qty = int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.source_id, -new_qty)
    _apply_stock_delta(connection, target.product_id, target.destination_id, +new_qty)

@event.listens_for(Transfer, "after_delete", propagate=True)
def _transfer_after_delete(mapper, connection, target: "Transfer"):
    qty = int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.source_id, +qty)
    _apply_stock_delta(connection, target.product_id, target.destination_id, -qty)

class ExchangeTransaction(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'exchange_transactions'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    quantity = db.Column(db.Integer, nullable=False)
    direction = db.Column(
        sa_str_enum(['IN', 'OUT', 'ADJUSTMENT'], name='exchange_direction'),
        default='IN',
        nullable=False,
        index=True,
    )
    unit_cost = db.Column(db.Numeric(12, 2))
    is_priced = db.Column(db.Boolean, nullable=False, server_default=db.text("0"))
    notes = db.Column(db.Text)

    product = db.relationship('Product', back_populates='exchange_transactions')
    warehouse = db.relationship('Warehouse', back_populates='exchange_transactions')
    partner = db.relationship('Partner')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_exchange_qty_positive'),
        db.Index('ix_exchange_prod_wh', 'product_id', 'warehouse_id'),
    )

    @validates('direction')
    def _v_direction(self, _, v):
        return (getattr(v, 'value', v) or '').strip().upper()

    def __repr__(self):
        return f"<ExchangeTransaction P{self.product_id} W{self.warehouse_id} Q{self.quantity}>"


def _ex_dir_sign(direction: str) -> int:
    d = (getattr(direction, "value", direction) or "").upper()
    if d == "IN":
        return 1
    if d == "OUT":
        return -1
    if d == "ADJUSTMENT":
        return 1  # إن أردت دعم تعديلات سالبة، غيّر المنطق والقيد في الجدول
    raise ValueError(f"Unknown exchange direction: {direction}")

@event.listens_for(ExchangeTransaction, "after_insert")
def _exchange_after_insert(mapper, connection, target: "ExchangeTransaction"):
    sign = _ex_dir_sign(target.direction)
    delta = sign * int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.warehouse_id, delta)

@event.listens_for(ExchangeTransaction, "after_update")
def _exchange_after_update(mapper, connection, target: "ExchangeTransaction"):
    prev = getattr(target, "_previous_state", None) or {}
    touched = any(k in prev for k in ("product_id", "warehouse_id", "quantity", "direction"))
    if not touched:
        return
    old_product_id = prev.get("product_id", target.product_id)
    old_warehouse_id = prev.get("warehouse_id", target.warehouse_id)
    old_quantity = prev.get("quantity", target.quantity)
    old_direction = prev.get("direction", target.direction)
    old_sign = _ex_dir_sign(old_direction)
    undo_delta = -old_sign * int(old_quantity or 0)
    _apply_stock_delta(connection, old_product_id, old_warehouse_id, undo_delta)
    new_sign = _ex_dir_sign(target.direction)
    new_delta = new_sign * int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.warehouse_id, new_delta)

@event.listens_for(ExchangeTransaction, "after_delete")
def _exchange_after_delete(mapper, connection, target: "ExchangeTransaction"):
    sign = _ex_dir_sign(target.direction)
    delta = -sign * int(target.quantity or 0)
    _apply_stock_delta(connection, target.product_id, target.warehouse_id, delta)

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
    )

    def __repr__(self):
        return f"<WarehousePartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id} {self.share_percentage}%>"

class ProductPartnerShare(db.Model):
    __table__ = WarehousePartnerShare.__table__

    partner   = db.relationship('Partner',   foreign_keys=[WarehousePartnerShare.partner_id],   viewonly=True)
    warehouse = db.relationship('Warehouse', foreign_keys=[WarehousePartnerShare.warehouse_id], viewonly=True)
    product   = db.relationship('Product',   back_populates='partner_shares',
                                foreign_keys=[WarehousePartnerShare.product_id])

    def __repr__(self):
        return f"<ProductPartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id}>"

class ProductSupplierLoan(db.Model, TimestampMixin):
    __tablename__ = 'product_supplier_loans'

    id                     = db.Column(db.Integer, primary_key=True)
    product_id             = db.Column(db.Integer, db.ForeignKey('products.id'),  nullable=False)
    supplier_id            = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    loan_value             = db.Column(db.Numeric(12, 2), default=0)
    deferred_price         = db.Column(db.Numeric(12, 2))
    is_settled             = db.Column(db.Boolean, default=False)
    partner_share_quantity = db.Column(db.Integer, default=0)
    partner_share_value    = db.Column(db.Numeric(12, 2), default=0)
    notes                  = db.Column(db.Text)

    product     = db.relationship('Product',  back_populates='supplier_loans')
    supplier    = db.relationship('Supplier', backref='loaned_products')
    settlements = db.relationship('SupplierLoanSettlement', back_populates='loan')

    __table_args__ = (
        db.CheckConstraint('loan_value >= 0', name='chk_loan_value_non_negative'),
        db.Index('ix_psl_product_supplier', 'product_id', 'supplier_id'),
    )

    @hybrid_property
    def effective_price(self):
        return float(self.deferred_price or self.loan_value or 0)

    def mark_settled(self, final_price):
        self.deferred_price = final_price
        self.is_settled = True

    def __repr__(self):
        return f"<ProductSupplierLoan P{self.product_id}-Supplier{self.supplier_id}>"

class ProductPartner(db.Model):
    __tablename__ = 'product_partners'

    id            = db.Column(db.Integer, primary_key=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.id'),  nullable=False)
    partner_id    = db.Column(db.Integer, db.ForeignKey('partners.id'),  nullable=False)
    share_percent = db.Column(db.Float,   nullable=False, default=0.0)
    share_amount  = db.Column(db.Numeric(12, 2), nullable=True)
    notes         = db.Column(db.Text)

    product = db.relationship('Product', back_populates='partners')
    partner = db.relationship('Partner', back_populates='product_links')

    __table_args__ = (
        db.CheckConstraint(
            'share_percent >= 0 AND share_percent <= 100',
            name='chk_partner_share'
        ),
        db.Index('ix_product_partner_pair', 'product_id', 'partner_id'),
    )

    def __repr__(self):
        return f"<ProductPartner {self.partner_id} {self.share_percent}%>"


class PreOrder(db.Model, TimestampMixin):
    __tablename__ = 'preorders'

    id            = db.Column(db.Integer, primary_key=True)
    reference     = db.Column(db.String(50), unique=True)
    preorder_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)

    customer_id  = db.Column(db.Integer, db.ForeignKey('customers.id'))
    supplier_id  = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id   = db.Column(db.Integer, db.ForeignKey('partners.id'))
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    quantity       = db.Column(db.Integer, nullable=False)
    prepaid_amount = db.Column(db.Numeric(12, 2), default=0)
    tax_rate       = db.Column(db.Numeric(5, 2), default=0)
    status         = db.Column(sa_str_enum(PreOrderStatus, name='preorder_status'),
                               default=PreOrderStatus.PENDING.value)
    notes          = db.Column(db.Text)
    payment_method = db.Column(db.String(20), nullable=False, default="cash", server_default="cash")

    customer  = db.relationship('Customer', back_populates='preorders')
    supplier  = db.relationship('Supplier', back_populates='preorders')
    partner   = db.relationship('Partner',   back_populates='preorders')
    product   = db.relationship('Product',   back_populates='preorders')
    warehouse = db.relationship('Warehouse', back_populates='preorders')

    payments = db.relationship('Payment', back_populates='preorder', cascade='all,delete-orphan')
    sale     = db.relationship('Sale',    back_populates='preorder', uselist=False)
    invoice  = db.relationship('Invoice', back_populates='preorder', uselist=False)

    __table_args__ = (
        CheckConstraint('quantity > 0', name='chk_preorder_quantity_positive'),
        CheckConstraint('prepaid_amount >= 0', name='chk_preorder_prepaid_non_negative'),
        CheckConstraint('tax_rate >= 0 AND tax_rate <= 100', name='chk_preorder_tax_rate'),
        CheckConstraint("payment_method IN ('cash','card','bank','cheque')", name='chk_preorder_payment_method'),
    )

    @property
    def reservation_code(self):
        return self.reference

    @reservation_code.setter
    def reservation_code(self, v):
        self.reference = v

    @hybrid_property
    def total_before_tax(self):
        price = float(getattr(self.product, "price", 0) or 0)
        return int(self.quantity or 0) * price

    @hybrid_property
    def total_with_tax(self):
        return self.total_before_tax * (1 + float(self.tax_rate or 0) / 100.0)

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.preorder_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.INCOMING.value
            ).scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.preorder_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.INCOMING.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def balance_due(self):
        return float(self.total_with_tax) - float(self.total_paid)

    def __repr__(self):
        return f"<PreOrder {self.reference or self.id}>"

@event.listens_for(PreOrder, 'before_insert')
def _preorder_before_insert(mapper, connection, target):
    if getattr(target, 'reference', None):
        return
    prefix = datetime.utcnow().strftime("PRE%Y%m%d")
    count = connection.execute(
        text("SELECT COUNT(*) FROM preorders WHERE reference LIKE :pfx"),
        {"pfx": f"{prefix}-%"}
    ).scalar() or 0
    target.reference = f"{prefix}-{count + 1:04d}"

class Sale(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'sales'

    id            = db.Column(db.Integer, primary_key=True)
    sale_number   = db.Column(db.String(50), unique=True)
    sale_date     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer_id   = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    seller_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    preorder_id   = db.Column(db.Integer, db.ForeignKey('preorders.id'))

    tax_rate       = db.Column(db.Numeric(5, 2),  default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    notes          = db.Column(db.Text)

    status         = db.Column(sa_str_enum(SaleStatus, name='sale_status'), default=SaleStatus.DRAFT.value, nullable=False)
    payment_status = db.Column(sa_str_enum(PaymentProgress, name='sale_payment_progress'), default=PaymentProgress.PENDING.value, nullable=False)

    currency         = db.Column(db.String(10), default='ILS')
    shipping_address = db.Column(db.Text)
    billing_address  = db.Column(db.Text)
    shipping_cost    = db.Column(db.Numeric(10, 2), default=0)
    total_amount     = db.Column(db.Numeric(12, 2), default=0)

    customer  = db.relationship('Customer', back_populates='sales')
    seller    = db.relationship('User',     back_populates='sales')
    preorder  = db.relationship('PreOrder', back_populates='sale')
    lines     = db.relationship('SaleLine', back_populates='sale', cascade='all,delete-orphan')
    payments  = db.relationship('Payment',  back_populates='sale', cascade='all,delete-orphan')
    invoice   = db.relationship('Invoice',  back_populates='sale', uselist=False)
    shipments = db.relationship('Shipment', back_populates='sale', cascade='all,delete-orphan')

    @hybrid_property
    def subtotal(self):
        return sum(l.net_amount for l in self.lines) if self.lines else 0.0

    @hybrid_property
    def tax_amount(self):
        base = float(self.subtotal) - float(self.discount_total or 0)
        return base * float(self.tax_rate or 0) / 100.0

    @hybrid_property
    def total(self):
        return float(self.subtotal) + float(self.tax_amount) + float(self.shipping_cost or 0) - float(self.discount_total or 0)

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.sale_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.INCOMING.value,
            )
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.sale_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.INCOMING.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def balance_due(self):
        return float(self.total) - float(self.total_paid or 0)

    def reserve_stock(self):
        for l in self.lines:
            lvl = StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id).with_for_update().first()
            if not lvl or (lvl.quantity or 0) < l.quantity:
                raise Exception("الكمية غير متوفرة في هذا المستودع")
            lvl.quantity = (lvl.quantity or 0) - int(l.quantity or 0)

    def release_stock(self):
        for l in self.lines:
            lvl = StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id).with_for_update().first()
            if lvl:
                lvl.quantity = (lvl.quantity or 0) + int(l.quantity or 0)

    def update_payment_status(self):
        paid = float(self.total_paid or 0)
        total = float(self.total or 0)
        self.payment_status = (
            PaymentProgress.PAID.value if paid >= total
            else PaymentProgress.PARTIAL.value if paid > 0
            else PaymentProgress.PENDING.value
        )

    def __repr__(self):
        return f"<Sale {self.sale_number}>"


@event.listens_for(Sale, "before_insert")
def _sale_before_insert_ref(mapper, connection, target: "Sale"):
    if not getattr(target, "sale_number", None):
        prefix = datetime.utcnow().strftime("SAL%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM sales WHERE sale_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.sale_number = f"{prefix}-{count+1:04d}"

@event.listens_for(Sale, "before_insert")
@event.listens_for(Sale, "before_update")
def _compute_total_amount(mapper, connection, target):
    subtotal = sum(q(l.net_amount) for l in (target.lines or []))
    discount = q(target.discount_total)
    tax_rate = q(target.tax_rate)
    shipping = q(target.shipping_cost)

    base = subtotal - discount
    if base < 0:
        base = Decimal('0.00')

    tax = q(base * tax_rate / Decimal('100'))
    target.total_amount = q(subtotal + tax + shipping - discount)

@event.listens_for(Sale.status, 'set')
def _reserve_release_on_status_change(target, value, oldvalue, initiator):
    newv = getattr(value, "value", value)
    oldv = getattr(oldvalue, "value", oldvalue)
    if newv == SaleStatus.CONFIRMED.value and oldv != SaleStatus.CONFIRMED.value:
        target.reserve_stock()
    elif oldv == SaleStatus.CONFIRMED.value and newv != SaleStatus.CONFIRMED.value:
        target.release_stock()

class SaleLine(db.Model):
    __tablename__ = 'sale_lines'

    id          = db.Column(db.Integer, primary_key=True)
    sale_id     = db.Column(db.Integer, db.ForeignKey('sales.id'),      nullable=False)
    product_id  = db.Column(db.Integer, db.ForeignKey('products.id'),   nullable=False)
    warehouse_id= db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    quantity      = db.Column(db.Integer,        nullable=False)
    unit_price    = db.Column(db.Numeric(12, 2), nullable=False)
    discount_rate = db.Column(db.Numeric(5, 2),  default=0)
    tax_rate      = db.Column(db.Numeric(5, 2),  default=0)
    note          = db.Column(db.String(200))

    sale      = db.relationship('Sale',      back_populates='lines')
    product   = db.relationship('Product',   back_populates='sale_lines')
    warehouse = db.relationship('Warehouse', back_populates='sale_lines')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_sale_line_qty_positive'),
        db.Index('ix_sale_line_sale', 'sale_id'),
    )

    @hybrid_property
    def gross_amount(self):
        return float(self.unit_price or 0) * float(self.quantity or 0)

    @hybrid_property
    def discount_amount(self):
        return self.gross_amount * float(self.discount_rate or 0) / 100.0

    @hybrid_property
    def net_amount(self):
        return self.gross_amount - self.discount_amount

    @hybrid_property
    def line_tax(self):
        return self.net_amount * float(self.tax_rate or 0) / 100.0

    @hybrid_property
    def line_total(self):
        return self.net_amount + self.line_tax

    def __repr__(self):
        pname = getattr(self.product, "name", None)
        return f"<SaleLine {pname or self.product_id} in Sale {self.sale_id}>"

class Invoice(db.Model, TimestampMixin):
    __tablename__ = 'invoices'

    id             = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True)
    invoice_date   = Column(DateTime, default=datetime.utcnow)
    due_date       = Column(DateTime)

    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    partner_id  = Column(Integer, ForeignKey('partners.id'))
    sale_id     = Column(Integer, ForeignKey('sales.id'))
    service_id  = Column(Integer, ForeignKey('service_requests.id'))
    preorder_id = Column(Integer, ForeignKey('preorders.id'))

    source = Column(
        sa_str_enum(InvoiceSource, name='invoice_source'),
        default=InvoiceSource.MANUAL.value,
        nullable=False
    )

    status = Column(
        sa_str_enum(InvoiceStatus, name='invoice_status'),
        default=InvoiceStatus.UNPAID.value,
        nullable=False
    )

    currency        = Column(String(10), default='ILS', nullable=False)
    total_amount    = Column(Numeric(12, 2), nullable=False)
    tax_amount      = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    notes           = Column(Text)
    terms           = Column(Text)
    customer = relationship('Customer', back_populates='invoices')
    supplier = relationship('Supplier', back_populates='invoices')
    partner  = relationship('Partner',  back_populates='invoices')
    sale     = relationship('Sale',     back_populates='invoice', uselist=False)
    service  = relationship('ServiceRequest', back_populates='invoice')
    preorder = relationship('PreOrder', back_populates='invoice')

    lines    = relationship('InvoiceLine', back_populates='invoice', cascade='all, delete-orphan')
    payments = relationship('Payment',     back_populates='invoice', cascade='all, delete-orphan', passive_deletes=True)

    __table_args__ = (
        db.Index('ix_invoices_customer_status', 'customer_id', 'status'),
    )

    @validates('source', 'status')
    def _uppercase_enum(self, key, value):
        return value.upper() if isinstance(value, str) else value

    @validates('currency')
    def _v_currency(self, _, v):
        return (v or 'ILS').upper()

    @hybrid_property
    def computed_total(self):
        return sum(l.line_total for l in self.lines) if self.lines else 0.0

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.invoice_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.INCOMING.value
            )
            .scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.invoice_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.INCOMING.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def balance_due(self):
        return float(self.total_amount or 0) - float(self.total_paid or 0)

    def update_status(self):
        self.status = (
            InvoiceStatus.PAID.value
            if self.balance_due <= 0
            else InvoiceStatus.PARTIAL.value
            if self.total_paid > 0
            else InvoiceStatus.UNPAID.value
        )

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"


class InvoiceLine(db.Model):
    __tablename__ = 'invoice_lines'

    id         = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    description= db.Column(db.String(200), nullable=False)
    quantity   = db.Column(db.Float,        nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate   = db.Column(db.Numeric(5, 2),  default=0)
    discount   = db.Column(db.Numeric(5, 2),  default=0)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))

    invoice = db.relationship('Invoice', back_populates='lines')
    product = db.relationship('Product')

    __table_args__ = (
        db.Index('ix_invoice_lines_invoice', 'invoice_id'),
    )

    @hybrid_property
    def line_total(self):
        gross = float(self.quantity or 0) * float(self.unit_price or 0)
        discount_amount = gross * (float(self.discount or 0) / 100.0)
        taxable = gross - discount_amount
        tax_amount = taxable * (float(self.tax_rate or 0) / 100.0)
        return taxable + tax_amount

    def __repr__(self):
        return f"<InvoiceLine {self.description}>"
# -------------------- Events (Invoice) --------------------
@event.listens_for(Invoice, 'before_insert')
@event.listens_for(Invoice, 'before_update')
def _invoice_normalize_and_total(mapper, connection, target: "Invoice"):
    target.currency = (target.currency or 'ILS').upper()
    try:
        total = sum(q(l.line_total) for l in (target.lines or []))
    except Exception:
        # fallback لو q مش متاحة
        from decimal import Decimal
        total = sum(Decimal(str(getattr(l, 'line_total', 0) or 0)) for l in (target.lines or []))
    target.total_amount = total
# ===================== Payment =====================
class Payment(db.Model):
    __tablename__ = 'payments'

    id              = Column(Integer, primary_key=True)
    payment_number  = Column(String(50), unique=True, nullable=False)
    payment_date    = Column(DateTime, default=datetime.utcnow, nullable=False)

    subtotal        = Column(Numeric(10, 2))
    tax_rate        = Column(Numeric(5, 2))
    tax_amount      = Column(Numeric(10, 2))
    total_amount    = Column(Numeric(10, 2), nullable=False)
    currency        = Column(String(10), default='ILS', nullable=False)

    method          = Column(sa_str_enum(PaymentMethod, name='payment_method'), nullable=False)
    status          = Column(sa_str_enum(PaymentStatus, name='payment_status'), default=PaymentStatus.PENDING.value, nullable=False)
    direction       = Column(sa_str_enum(PaymentDirection, name='payment_direction'), default=PaymentDirection.INCOMING.value, nullable=False)
    entity_type     = Column(sa_str_enum(PaymentEntityType, name='payment_entity_type'), default=PaymentEntityType.CUSTOMER.value, nullable=False)

    reference       = Column(String(100))
    receipt_number  = Column(String(50), unique=True)
    notes           = Column(Text)

    check_number      = Column(String(100))
    check_bank        = Column(String(100))
    check_due_date    = Column(DateTime)
    card_number       = Column(String(100))
    card_holder       = Column(String(100))
    card_expiry       = Column(String(10))
    card_cvv          = Column(String(4))
    bank_transfer_ref = Column(String(100))

    created_by = Column(Integer, ForeignKey('users.id'))
    creator    = relationship('User', backref='payments_created')

    customer_id         = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'))
    supplier_id         = Column(Integer, ForeignKey('suppliers.id', ondelete='CASCADE'))
    partner_id          = Column(Integer, ForeignKey('partners.id',  ondelete='CASCADE'))
    shipment_id         = Column(Integer, ForeignKey('shipments.id', ondelete='CASCADE'))
    expense_id          = Column(Integer, ForeignKey('expenses.id',  ondelete='CASCADE'))
    loan_settlement_id  = Column(Integer, ForeignKey('supplier_loan_settlements.id', ondelete='CASCADE'))
    sale_id             = Column(Integer, ForeignKey('sales.id',     ondelete='CASCADE'))
    invoice_id          = Column(Integer, ForeignKey('invoices.id',  ondelete='CASCADE'))
    preorder_id         = Column(Integer, ForeignKey('preorders.id', ondelete='CASCADE'))
    service_id          = Column(Integer, ForeignKey('service_requests.id', ondelete='CASCADE'))

    customer        = relationship('Customer', back_populates='payments')
    supplier        = relationship('Supplier', back_populates='payments')
    partner         = relationship('Partner',  back_populates='payments')
    shipment        = relationship('Shipment', back_populates='payments')
    expense         = relationship('Expense',  back_populates='payments')
    loan_settlement = relationship('SupplierLoanSettlement', back_populates='payment')
    sale            = relationship('Sale',     back_populates='payments')
    invoice         = relationship('Invoice',  back_populates='payments')
    preorder        = relationship('PreOrder', back_populates='payments')
    service         = relationship('ServiceRequest', back_populates='payments')

    splits = relationship(
        'PaymentSplit',
        back_populates='payment',
        cascade='all,delete-orphan',
        passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint('total_amount > 0', name='ck_payment_total_positive'),
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
        ) = 1""", name='ck_payment_one_target'),
    )

    @property
    def entity(self):
        for attr in (
            'customer', 'supplier', 'partner', 'shipment', 'expense',
            'loan_settlement', 'sale', 'invoice', 'preorder', 'service'
        ):
            if getattr(self, f'{attr}_id', None):
                obj = getattr(self, attr, None)
                if obj is not None:
                    return obj
                raise ValueError(f"⚠️ Payment points to {attr}_id but no relationship loaded.")
        raise ValueError("❌ Payment is not linked to any entity.")

    def entity_label(self):
        if self.customer: return self.customer.name
        if self.supplier: return self.supplier.name
        if self.partner:  return self.partner.name
        if self.invoice:  return self.invoice.invoice_number
        if self.sale:     return self.sale.sale_number
        if self.shipment: return self.shipment.shipment_number
        if self.service:  return self.service.service_number
        if self.preorder: return self.preorder.reference
        if self.expense:  return f"Expense #{self.expense.id}"
        if self.loan_settlement: return f"LoanSettle #{self.loan_settlement.id}"
        return None

    @validates('total_amount')
    def _validate_total_amount(self, key, value):
        if value is None or value <= 0:
            raise ValueError("total_amount must be > 0")
        return value

    @validates('method', 'status', 'direction', 'entity_type')
    def _coerce_enums(self, key, value):
        return getattr(value, 'value', value) if value else None

    @validates('currency')
    def _v_payment_currency(self, key, v):
        return (v or 'ILS').upper()

    def to_dict(self):
        _v = lambda x: getattr(x, "value", x)
        return {
            'id': self.id,
            'payment_number': self.payment_number,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'subtotal': float(self.subtotal or 0),
            'tax_rate': float(self.tax_rate or 0),
            'tax_amount': float(self.tax_amount or 0),
            'total_amount': float(self.total_amount or 0),
            'currency': self.currency,
            'method': _v(self.method),
            'status': _v(self.status),
            'direction': _v(self.direction),
            'entity_type': _v(self.entity_type),
            'entity_display': self.entity_label(),
            'reference': self.reference,
            'receipt_number': self.receipt_number,
            'notes': self.notes,
            'created_by': self.created_by,
            'customer_id': self.customer_id,
            'supplier_id': self.supplier_id,
            'partner_id': self.partner_id,
            'shipment_id': self.shipment_id,
            'expense_id': self.expense_id,
            'loan_settlement_id': self.loan_settlement_id,
            'sale_id': self.sale_id,
            'invoice_id': self.invoice_id,
            'preorder_id': self.preorder_id,
            'service_id': self.service_id,
            'splits': [s.to_dict() for s in self.splits or []],
        }

    def __repr__(self):
        return f"<Payment {self.payment_number or self.id} - {self.total_amount} {self.currency}>"
# ===================== PaymentSplit =====================
class PaymentSplit(db.Model):
    __tablename__ = 'payment_splits'

    id          = Column(Integer, primary_key=True)
    payment_id  = Column(Integer, ForeignKey('payments.id', ondelete='CASCADE'), nullable=False)
    method      = Column(sa_str_enum(PaymentMethod, name='split_payment_method'), nullable=False)
    amount      = Column(Numeric(12, 2), nullable=False)
    details     = Column(db.JSON)

    payment = relationship('Payment', back_populates='splits')

    __table_args__ = (
        CheckConstraint('amount > 0', name='chk_split_amount_positive'),
    )

    def __repr__(self):
        m = getattr(self.method, "value", self.method)
        return f"<PaymentSplit {m} {self.amount}>"

    def to_dict(self):
        return {
            'id': self.id,
            'payment_id': self.payment_id,
            'method': getattr(self.method, 'value', self.method),
            'amount': float(self.amount or 0),
            'details': self.details or None
        }

# ===================== حُرّاس الإدراج والتحديث =====================
INCOMING_TARGETS = {'customer_id', 'sale_id', 'invoice_id', 'preorder_id', 'service_id'}
OUTGOING_TARGETS = {'supplier_id', 'partner_id', 'shipment_id', 'expense_id', 'loan_settlement_id'}

def _guess_direction_from_links(p: "Payment") -> str | None:
    has_in = any(getattr(p, f, None) for f in INCOMING_TARGETS)
    has_out = any(getattr(p, f, None) for f in OUTGOING_TARGETS)
    if has_in and not has_out:
        return PaymentDirection.INCOMING.value
    if has_out and not has_in:
        return PaymentDirection.OUTGOING.value
    return None

@event.listens_for(Payment, 'before_insert')
@event.listens_for(Payment, 'before_update')
def _payment_guard(mapper, connection, target: "Payment"):
    for k in ('method', 'status', 'direction', 'entity_type'):
        v = getattr(target, k, None)
        if hasattr(v, 'value'):
            setattr(target, k, v.value)

    exp_dir = _guess_direction_from_links(target)
    if exp_dir and str(target.direction or "").upper() != exp_dir:
        target.direction = exp_dir

    splits = getattr(target, 'splits', [])
    if not target.method:
        if splits:
            target.method = getattr(splits[0].method, 'value', splits[0].method)
        else:
            raise ValueError("❌ Payment.method مطلوب إذا لم توجد PaymentSplits في نفس العملية.")

    if splits:
        total = sum(q(s.amount or 0) for s in splits)
        expected = q(target.total_amount or 0)
        if total != expected:
            raise ValueError(f"❌ مجموع PaymentSplits ({total}) لا يساوي total_amount ({expected}).")

        split_methods = {getattr(s.method, 'value', s.method) for s in splits}
        if len(split_methods) > 1:
            raise ValueError("❌ لا يمكن أن تحتوي PaymentSplits على أكثر من طريقة دفع مختلفة.")

    target.card_cvv = None
    target.card_number = None
    target.card_holder = None
    target.card_expiry = None

# ===================== Shipments =====================
class Shipment(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'shipments'

    id               = db.Column(db.Integer, primary_key=True)
    shipment_number  = db.Column(db.String(50), unique=True, index=True)
    shipment_date    = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expected_arrival = db.Column(db.DateTime)
    actual_arrival   = db.Column(db.DateTime)

    origin           = db.Column(db.String(100))
    destination      = db.Column(db.String(100))
    destination_id   = db.Column(db.Integer, db.ForeignKey('warehouses.id'), index=True)

    status           = db.Column(db.String(20), default='PENDING', nullable=False, index=True)

    value_before     = db.Column(db.Numeric(12, 2))  # مجموع (quantity * unit_cost) لعناصر الشحنة
    shipping_cost    = db.Column(db.Numeric(12, 2))
    customs          = db.Column(db.Numeric(12, 2))
    vat              = db.Column(db.Numeric(12, 2))
    insurance        = db.Column(db.Numeric(12, 2))

    carrier          = db.Column(db.String(100))
    tracking_number  = db.Column(db.String(100), index=True)
    notes            = db.Column(db.Text)
    currency         = db.Column(db.String(10), default='USD', nullable=False)

    sale_id          = db.Column(db.Integer, db.ForeignKey('sales.id'), index=True)

    items     = db.relationship('ShipmentItem', back_populates='shipment', cascade='all, delete-orphan')
    partners  = db.relationship('ShipmentPartner', back_populates='shipment', cascade='all, delete-orphan')
    payments  = db.relationship('Payment', back_populates='shipment')
    sale      = db.relationship('Sale', back_populates='shipments')
    destination_warehouse = db.relationship(
        'Warehouse',
        back_populates='shipments_received',
        foreign_keys=[destination_id]
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PENDING','IN_TRANSIT','ARRIVED','CANCELLED')",
            name='chk_shipment_status_allowed'
        ),
        db.Index('ix_shipments_dest_status', 'destination_id', 'status'),
    )

    @validates('status')
    def _v_status(self, _, v):
        return (v or '').strip().upper()

    @validates('currency')
    def _v_currency(self, _, v):
        return (v or 'USD').upper()

    @hybrid_property
    def total_value(self):
        vb = float(self.value_before or 0)
        return (
            vb +
            float(self.shipping_cost or 0) +
            float(self.customs or 0) +
            float(self.vat or 0) +
            float(self.insurance or 0)
        )

    def update_status(self, new_status: str):
        self.status = (new_status or '').strip().upper()
        if self.status == 'ARRIVED' and not self.actual_arrival:
            self.actual_arrival = datetime.utcnow()

    def _apply_arrival_stock(self):
        for it in (self.items or []):
            lvl = (StockLevel.query
                   .filter_by(product_id=it.product_id, warehouse_id=it.warehouse_id)
                   .with_for_update()
                   .first())
            if not lvl:
                lvl = StockLevel(
                    product_id=it.product_id,
                    warehouse_id=it.warehouse_id,
                    quantity=0,
                    reserved_quantity=0
                )
                db.session.add(lvl)
                db.session.flush()
            lvl.quantity = int(lvl.quantity or 0) + int(it.quantity or 0)

    def _revert_arrival_stock(self):
        for it in (self.items or []):
            lvl = (StockLevel.query
                   .filter_by(product_id=it.product_id, warehouse_id=it.warehouse_id)
                   .with_for_update()
                   .first())
            if not lvl:
                continue
            new_q = int(lvl.quantity or 0) - int(it.quantity or 0)
            if new_q < 0:
                raise Exception("لا يمكن عكس مخزون الشحنة: سيصبح المخزون سالبًا")
            lvl.quantity = new_q

    def __repr__(self):
        return f"<Shipment {self.shipment_number or self.id}>"

# ==================== Events ====================
@event.listens_for(Shipment, 'before_insert')
def _shipment_before_insert(mapper, connection, target: 'Shipment'):
    # رقم الشحنة
    if not getattr(target, 'shipment_number', None):
        prefix = datetime.utcnow().strftime("SHP%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM shipments WHERE shipment_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"}
        ).scalar() or 0
        target.shipment_number = f"{prefix}-{count+1:04d}"
    # تطبيع العملة
    target.currency = (target.currency or 'USD').upper()
    # احتساب value_before من العناصر
    vb = sum((it.quantity or 0) * float(it.unit_cost or 0) for it in (target.items or []))
    target.value_before = vb

@event.listens_for(Shipment, 'before_update')
def _shipment_before_update(mapper, connection, target: 'Shipment'):
    target.currency = (target.currency or 'USD').upper()
    vb = sum((it.quantity or 0) * float(it.unit_cost or 0) for it in (target.items or []))
    target.value_before = vb
@event.listens_for(Shipment.status, 'set')
def _shipment_status_stock(target: Shipment, value, oldvalue, initiator):
    def normalize(v):
        if hasattr(v, "value"):
            v = v.value
        if isinstance(v, int):
            v = str(v)
        return (v or "").strip().upper()

    newv = normalize(value)
    oldv = normalize(oldvalue)

    if newv == 'ARRIVED' and oldv != 'ARRIVED':
        if not getattr(target, 'actual_arrival', None):
            target.actual_arrival = datetime.utcnow()
        try:
            target._apply_arrival_stock()
        except Exception as e:
            raise
    elif oldv == 'ARRIVED' and newv != 'ARRIVED':
        target._revert_arrival_stock()

class ShipmentItem(db.Model):
    __tablename__ = 'shipment_items'

    id           = db.Column(db.Integer, primary_key=True)
    shipment_id  = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    quantity       = db.Column(db.Integer, nullable=False, default=0)
    unit_cost      = db.Column(db.Numeric(10, 2))
    declared_value = db.Column(db.Numeric(12, 2))
    notes          = db.Column(db.String(200))

    shipment  = db.relationship('Shipment', back_populates='items')
    product   = db.relationship('Product', back_populates='shipment_items')
    warehouse = db.relationship('Warehouse', back_populates='shipment_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_shipment_item_qty_positive'),
        db.UniqueConstraint('shipment_id', 'product_id', 'warehouse_id', name='uq_shipment_item_unique'),  # منع تكرار نفس المنتج لنفس المخزن ضمن الشحنة
        db.Index('ix_shipment_items_prod_wh', 'product_id', 'warehouse_id'),
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def total_value(self):
        return int(self.quantity or 0) * float(self.unit_cost or 0)

    def __repr__(self):
        return f"<ShipmentItem {self.product_id} Q{self.quantity}>"


@event.listens_for(ShipmentItem, 'before_insert')
def _si_before_insert(mapper, connection, target: 'ShipmentItem'):
    if not getattr(target, 'warehouse_id', None) and getattr(target, 'shipment', None):
        target.warehouse_id = target.shipment.destination_id

@event.listens_for(ShipmentItem, 'after_insert')
def _si_after_insert(mapper, connection, target: 'ShipmentItem'):
    sh = target.shipment
    if sh and (sh.status or '').upper() == 'ARRIVED':
        _apply_stock_delta(connection, target.product_id, target.warehouse_id, +int(target.quantity or 0))


@event.listens_for(ShipmentItem, 'after_update')
def _si_after_update(mapper, connection, target: 'ShipmentItem'):
    sh = target.shipment
    if not sh or (sh.status or '').upper() != 'ARRIVED':
        return
    prev = getattr(target, "_previous_state", None) or {}
    touched = any(k in prev for k in ("product_id", "warehouse_id", "quantity"))
    if not touched:
        return
    old_pid = prev.get("product_id", target.product_id)
    old_wid = prev.get("warehouse_id", target.warehouse_id)
    old_qty = int(prev.get("quantity", target.quantity) or 0)
    # تراجع القديم
    _apply_stock_delta(connection, old_pid, old_wid, -old_qty)
    # تطبيق الجديد
    _apply_stock_delta(connection, target.product_id, target.warehouse_id, +int(target.quantity or 0))
@event.listens_for(ShipmentItem, 'after_delete')
def _si_after_delete(mapper, connection, target: 'ShipmentItem'):
    sh = target.shipment
    if sh and (sh.status or '').upper() == 'ARRIVED':
        _apply_stock_delta(connection, target.product_id, target.warehouse_id, -int(target.quantity or 0))

class ShipmentPartner(db.Model, TimestampMixin):
    __tablename__ = 'shipment_partners'

    id              = db.Column(db.Integer, primary_key=True)
    shipment_id     = db.Column(
        db.Integer,
        db.ForeignKey('shipments.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    partner_id      = db.Column(
        db.Integer,
        db.ForeignKey('partners.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    identity_number = db.Column(db.String(100))
    phone_number    = db.Column(db.String(20))
    address         = db.Column(db.String(200))

    unit_price_before_tax = db.Column(db.Numeric(12, 2))
    expiry_date     = db.Column(db.Date)

    share_percentage= db.Column(db.Numeric(5, 2), default=0)     
    share_amount    = db.Column(db.Numeric(12, 2), default=0)    

    notes           = db.Column(db.Text)

    __table_args__ = (
        db.CheckConstraint(
            'share_percentage >= 0 AND share_percentage <= 100',
            name='chk_shipment_partner_share'
        ),
        db.UniqueConstraint(
            'shipment_id', 'partner_id',
            name='uq_shipment_partner_unique'
        ),  
        db.Index('ix_shipment_partner_pair', 'shipment_id', 'partner_id'),
    )

    partner  = db.relationship('Partner', back_populates='shipment_partners')
    shipment = db.relationship('Shipment', back_populates='partners')

    @hybrid_property
    def share_value(self):
        """قيمة حصة الشريك النهائية: إما مبلغ مباشر أو محسوبة من النسبة."""
        if self.share_amount and float(self.share_amount) > 0:
            return float(self.share_amount)
        return (float(self.unit_price_before_tax or 0) * float(self.share_percentage or 0)) / 100.0

    def __repr__(self):
        return f"<ShipmentPartner shipment={self.shipment_id} partner={self.partner_id}>"

class SupplierLoanSettlement(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'supplier_loan_settlements'

    id              = db.Column(db.Integer, primary_key=True)
    loan_id         = db.Column(db.Integer, db.ForeignKey('product_supplier_loans.id', ondelete='CASCADE'), nullable=True, index=True)
    supplier_id     = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, index=True)

    settled_price   = db.Column(db.Numeric(12, 2), nullable=False)
    settlement_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes           = db.Column(db.Text)

    loan     = db.relationship('ProductSupplierLoan', back_populates='settlements')
    supplier = db.relationship('Supplier', back_populates='loan_settlements')

    payment  = db.relationship('Payment', back_populates='loan_settlement',
                               cascade='all, delete-orphan', passive_deletes=True, uselist=False)

    __table_args__ = (
        db.CheckConstraint('settled_price >= 0', name='chk_settlement_price_non_negative'),
    )

    @hybrid_property
    def has_payment(self) -> bool:
        return self.payment is not None

    @property
    def product(self):
        return getattr(self.loan, 'product', None)

    def build_payment(self, method: 'PaymentMethod' = None, status: 'PaymentStatus' = None,
                      direction: 'PaymentDirection' = None, currency: str = None,
                      reference: str = None, notes: str = None, created_by: int = None) -> 'Payment':
        return Payment(
            total_amount=self.settled_price,
            payment_date=datetime.utcnow(),
            method=method or PaymentMethod.BANK,
            status=status or PaymentStatus.PENDING,
            direction=direction or PaymentDirection.OUTGOING,   
            entity_type=PaymentEntityType.LOAN,
            currency=currency or (getattr(self.supplier, 'currency', None) or 'ILS'),
            supplier_id=getattr(self.supplier, 'id', None),
            loan_settlement_id=self.id,
            reference=reference or f"Loan #{self.loan_id} settlement",
            notes=notes,
            created_by=created_by,
        )

    def __repr__(self):
        return f"<SupplierLoanSettlement Loan{self.loan_id} - {self.settled_price}>"


@event.listens_for(SupplierLoanSettlement, 'after_insert')
def _sync_loan_on_settlement(mapper, connection, target: 'SupplierLoanSettlement'):
    if target.loan_id:
        connection.execute(
            update(ProductSupplierLoan)
            .where(ProductSupplierLoan.id == target.loan_id)
            .values(
                deferred_price=target.settled_price,
                is_settled=True
            )
        )
# ===================== Service =====================
class ServiceRequest(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)
    service_number = db.Column(db.String(50), unique=True, index=True, nullable=True)

    customer_id     = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True, nullable=False)
    mechanic_id     = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey("equipment_types.id"), index=True)

    status = db.Column(
        sa_str_enum(ServiceStatus, name='service_status'),
        default=ServiceStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    priority = db.Column(
        sa_str_enum(ServicePriority, name='service_priority'),
        default=ServicePriority.MEDIUM.value,
        nullable=False,
        index=True,
    )

    vehicle_vrn        = db.Column(db.String(50))
    vehicle_model      = db.Column(db.String(100))
    chassis_number     = db.Column(db.String(100))
    engineer_notes     = db.Column(db.Text)
    description        = db.Column(db.Text)
    estimated_duration = db.Column(db.Integer)
    actual_duration    = db.Column(db.Integer)
    estimated_cost     = db.Column(db.Numeric(12, 2))
    total_cost         = db.Column(db.Numeric(12, 2))
    start_time         = db.Column(db.Date)
    end_time           = db.Column(db.Date)

    problem_description = db.Column(db.Text)
    diagnosis           = db.Column(db.Text)
    resolution          = db.Column(db.Text)
    notes               = db.Column(db.Text)

    received_at       = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    started_at        = db.Column(db.DateTime)
    expected_delivery = db.Column(db.DateTime)
    completed_at      = db.Column(db.DateTime)

    currency        = db.Column(db.String(10), nullable=False, default="ILS")
    tax_rate        = db.Column(db.Numeric(5, 2), default=0)
    discount_total  = db.Column(db.Numeric(12, 2), default=0)
    parts_total     = db.Column(db.Numeric(12, 2), default=0)
    labor_total     = db.Column(db.Numeric(12, 2), default=0)
    total_amount    = db.Column(db.Numeric(12, 2), default=0)

    warranty_days = db.Column(db.Integer, default=0)

    customer     = db.relationship("Customer", back_populates="service_requests")
    mechanic     = db.relationship("User", back_populates="service_requests")
    vehicle_type = db.relationship("EquipmentType", back_populates="service_requests")
    invoice      = db.relationship("Invoice", back_populates="service", uselist=False)
    payments     = db.relationship("Payment", back_populates="service", cascade="all, delete-orphan")
    parts        = db.relationship("ServicePart", back_populates="request", cascade="all, delete-orphan")
    tasks        = db.relationship("ServiceTask", back_populates="request", cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_service_customer_status", "customer_id", "status"),
        db.Index("ix_service_mechanic_status", "mechanic_id", "status"),
    )

    @validates("status", "priority")
    def _v_enum_strings(self, _, v):
        return getattr(v, "value", v)

    @validates("currency")
    def _v_currency(self, _, v):
        return (v or "ILS").upper()

    @hybrid_property
    def subtotal(self):
        return float(self.parts_total or 0) + float(self.labor_total or 0)

    @hybrid_property
    def tax_amount(self):
        base = max(self.subtotal - float(self.discount_total or 0), 0.0)
        return base * float(self.tax_rate or 0) / 100.0

    @hybrid_property
    def total(self):
        if self.total_amount is not None:
            return float(self.total_amount)
        return self.subtotal + self.tax_amount - float(self.discount_total or 0)

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.service_id == self.id,
                Payment.status == 'COMPLETED',
                Payment.direction == 'IN',
            ).scalar()
        )

    @hybrid_property
    def balance_due(self):
        val = self.total - self.total_paid
        return val if val > 0 else 0.0

    @hybrid_property
    def warranty_until(self):
        if not self.warranty_days:
            return None
        anchor = self.completed_at or self.updated_at or self.created_at
        return anchor + timedelta(days=self.warranty_days) if anchor else None

    def mark_started(self):
        if not self.started_at:
            self.started_at = datetime.utcnow()
        if self.status == ServiceStatus.PENDING.value:
            self.status = ServiceStatus.IN_PROGRESS.value

    def mark_completed(self):
        self.status = ServiceStatus.COMPLETED.value
        if not self.completed_at:
            self.completed_at = datetime.utcnow()

    def __repr__(self):
        return f"<ServiceRequest {self.service_number or self.id}>"

    def to_dict(self):
        return {
            "id": self.id,
            "service_number": self.service_number,
            "status": getattr(self.status, "value", self.status),
            "priority": getattr(self.priority, "value", self.priority),
            "customer_id": self.customer_id,
            "mechanic_id": self.mechanic_id,
            "vehicle_type_id": self.vehicle_type_id,
            "problem_description": self.problem_description,
            "diagnosis": self.diagnosis,
            "resolution": self.resolution,
            "notes": self.notes,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expected_delivery": self.expected_delivery.isoformat() if self.expected_delivery else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "currency": self.currency,
            "tax_rate": float(self.tax_rate or 0),
            "discount_total": float(self.discount_total or 0),
            "parts_total": float(self.parts_total or 0),
            "labor_total": float(self.labor_total or 0),
            "total_amount": float(self.total_amount or 0),
            "subtotal": float(self.subtotal),
            "tax_amount": float(self.tax_amount),
            "total": float(self.total),
            "total_paid": float(self.total_paid),
            "balance_due": float(self.balance_due),
            "warranty_days": self.warranty_days,
            "warranty_until": self.warranty_until.isoformat() if self.warranty_until else None,
            "parts": [p.to_dict() for p in self.parts] if self.parts else [],
            "tasks": [t.to_dict() for t in self.tasks] if self.tasks else [],
        }

def _D(x):
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def _calc_parts_sum(service_id: int) -> Decimal:
    rows = db.session.query(
        ServicePart.quantity, ServicePart.unit_price, ServicePart.discount, ServicePart.tax_rate
    ).filter(ServicePart.service_id == service_id).all()
    total = Decimal("0")
    for q, u, d, t in rows:
        qd = _D(q)
        ud = _D(u)
        dd = _D(d) / Decimal("100")
        td = _D(t) / Decimal("100")
        gross = qd * ud
        taxable = gross * (Decimal("1") - dd)
        line_total = taxable * (Decimal("1") + td)
        total += line_total
    return total

def _calc_tasks_sum(service_id: int) -> Decimal:
    rows = db.session.query(
        ServiceTask.quantity, ServiceTask.unit_price, ServiceTask.discount, ServiceTask.tax_rate
    ).filter(ServiceTask.service_id == service_id).all()
    total = Decimal("0")
    for q, u, d, t in rows:
        qd = _D(q)
        ud = _D(u)
        dd = _D(d) / Decimal("100")
        td = _D(t) / Decimal("100")
        gross = qd * ud
        taxable = gross * (Decimal("1") - dd)
        line_total = taxable * (Decimal("1") + td)
        total += line_total
    return total

def _recalc_service_request_totals(sr: "ServiceRequest"):
    parts_sum = _calc_parts_sum(sr.id)
    tasks_sum = _calc_tasks_sum(sr.id)
    discount_total = _D(sr.discount_total)
    tax_rate = _D(sr.tax_rate) / Decimal("100")
    sr.parts_total = parts_sum
    sr.labor_total = tasks_sum
    base = parts_sum + tasks_sum - discount_total
    if base < 0:
        base = Decimal("0")
    tax = base * tax_rate
    sr.total_amount = base + tax
    sr.currency = (sr.currency or "ILS").upper()

def _service_consumes_stock(sr: "ServiceRequest") -> bool:
    st = (getattr(sr.status, "value", sr.status) or "").upper()
    return st in ("IN_PROGRESS", "COMPLETED")

@event.listens_for(ServiceRequest, "before_insert")
@event.listens_for(ServiceRequest, "before_update")
def _compute_service_totals(mapper, connection, target: ServiceRequest):
    _recalc_service_request_totals(target)

@event.listens_for(ServiceRequest, "before_insert")
def _ensure_service_number(mapper, connection, target: ServiceRequest):
    if getattr(target, "service_number", None):
        return
    prefix = datetime.utcnow().strftime("SRV%Y%m%d")
    cnt = connection.execute(
        text("SELECT COUNT(*) FROM service_requests WHERE service_number LIKE :pfx"),
        {"pfx": f"{prefix}-%"},
    ).scalar() or 0
    target.service_number = f"{prefix}-{cnt + 1:04d}"

@event.listens_for(ServiceRequest.status, "set")
def _set_completed_at_on_status_change(target, value, oldvalue, initiator):
    newv = getattr(value, "value", value)
    if newv == ServiceStatus.COMPLETED.value and not target.completed_at:
        target.completed_at = datetime.utcnow()

# ===================== Service Parts =====================
class ServicePart(db.Model):
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
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def gross_amount(self):
        return int(self.quantity or 0) * float(self.unit_price or 0)

    @hybrid_property
    def discount_amount(self):
        return float(self.gross_amount) * float(self.discount or 0) / 100.0

    @hybrid_property
    def taxable_amount(self):
        return float(self.gross_amount) - float(self.discount_amount)

    @hybrid_property
    def tax_amount(self):
        return float(self.taxable_amount) * float(self.tax_rate or 0) / 100.0

    @hybrid_property
    def line_total(self):
        return float(self.taxable_amount) + float(self.tax_amount)

    @hybrid_property
    def net_total(self):
        share = float(self.share_percentage or 0) / 100.0
        return float(self.line_total) * (1.0 - share)

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
            "gross_amount": self.gross_amount,
            "discount_amount": self.discount_amount,
            "taxable_amount": self.taxable_amount,
            "tax_amount": self.tax_amount,
            "line_total": self.line_total,
            "net_total": self.net_total,
        }

    def __repr__(self):
        pname = getattr(self.part, "name", None)
        return f"<ServicePart {pname or self.part_id} for Service {self.service_id}>"

@event.listens_for(ServicePart, 'after_insert', propagate=True)
@event.listens_for(ServicePart, 'after_update', propagate=True)
@event.listens_for(ServicePart, 'after_delete', propagate=True)
def _sp_changed(mapper, connection, target):
    sess = object_session(target) or db.session
    sr = sess.get(ServiceRequest, target.service_id)
    if sr:
        _recalc_service_request_totals(sr)
# ===================== Service Tasks =====================
class ServiceTask(db.Model):
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
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def gross_amount(self):
        return int(self.quantity or 0) * float(self.unit_price or 0)

    @hybrid_property
    def discount_amount(self):
        return float(self.gross_amount) * float(self.discount or 0) / 100.0

    @hybrid_property
    def taxable_amount(self):
        return float(self.gross_amount) - float(self.discount_amount)

    @hybrid_property
    def tax_amount(self):
        return float(self.taxable_amount) * float(self.tax_rate or 0) / 100.0

    @hybrid_property
    def line_total(self):
        return float(self.taxable_amount) + float(self.tax_amount)

    @hybrid_property
    def net_total(self):
        share = float(self.share_percentage or 0) / 100.0
        return float(self.line_total) * (1.0 - share)

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
            "gross_amount": self.gross_amount,
            "discount_amount": self.discount_amount,
            "taxable_amount": self.taxable_amount,
            "tax_amount": self.tax_amount,
            "line_total": self.line_total,
            "net_total": self.net_total,
        }

    def __repr__(self):
        return f"<ServiceTask {self.description} for Service {self.service_id}>"

@event.listens_for(ServiceTask, 'after_insert')
@event.listens_for(ServiceTask, 'after_update')
@event.listens_for(ServiceTask, 'after_delete')
def _st_changed(mapper, connection, target):
    sess = object_session(target) or db.session
    sr = sess.get(ServiceRequest, target.service_id)
    if sr:
        _recalc_service_request_totals(sr)

# -------------------- Events: Sync totals + stock on parts/tasks --------------------
def _maybe_apply_part_stock(connection, sp: ServicePart, sign: int):
    """يطبّق دلتا المخزون لقطعة خدمة إذا كانت حالة الخدمة تستهلك مخزوناً."""
    sr = sp.request
    if not sr or not _service_consumes_stock(sr):
        return
    qty = int(sp.quantity or 0)
    delta = -sign * qty  # استهلاك من المخزون عند الإضافة (sign=+1) → -qty
    _apply_stock_delta(connection, sp.part_id, sp.warehouse_id, delta)

@event.listens_for(ServicePart, "after_insert")
def _sp_after_insert(mapper, connection, target: ServicePart):
    _recalc_service_request_totals(target.request)
    _maybe_apply_part_stock(connection, target, sign=+1)

@event.listens_for(ServicePart, "after_update")
def _sp_after_update(mapper, connection, target: ServicePart):
    _recalc_service_request_totals(target.request)
    prev = getattr(target, "_previous_state", None) or {}
    touched = any(k in prev for k in ("part_id", "warehouse_id", "quantity"))
    if touched and _service_consumes_stock(target.request):
        old_pid = prev.get("part_id", target.part_id)
        old_wid = prev.get("warehouse_id", target.warehouse_id)
        old_qty = int(prev.get("quantity", target.quantity) or 0)
        # تراجع استهلاك القديم (إرجاع للستوك)
        _apply_stock_delta(connection, old_pid, old_wid, +old_qty)
        # استهلاك الجديد
        _apply_stock_delta(connection, target.part_id, target.warehouse_id, -int(target.quantity or 0))

@event.listens_for(ServicePart, "after_delete")
def _sp_after_delete(mapper, connection, target: ServicePart):
    _recalc_service_request_totals(target.request)
    # إذا كانت الخدمة تستهلك مخزوناً، حذف القطعة يعيد الكمية للمخزون
    if _service_consumes_stock(target.request):
        _apply_stock_delta(connection, target.part_id, target.warehouse_id, +int(target.quantity or 0))

@event.listens_for(ServiceTask, "after_insert")
@event.listens_for(ServiceTask, "after_update")
@event.listens_for(ServiceTask, "after_delete")
def _st_sync_totals(mapper, connection, target: ServiceTask):
    if target.request:
        _recalc_service_request_totals(target.request)

# ===================== Online (Cart / PreOrder / Payment) =====================
class OnlineCart(db.Model, TimestampMixin):
    __tablename__ = 'online_carts'

    id          = db.Column(db.Integer, primary_key=True)
    cart_id     = db.Column(db.String(50), unique=True, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), index=True)
    session_id  = db.Column(db.String(100), index=True)

    status = db.Column(
        sa_str_enum(['ACTIVE', 'ABANDONED', 'CONVERTED'], name='cart_status'),
        default='ACTIVE', nullable=False, index=True
    )

    expires_at = db.Column(db.DateTime, index=True)

    customer = db.relationship('Customer', back_populates='online_carts')
    items    = db.relationship('OnlineCartItem', back_populates='cart',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_online_cart_customer_status', 'customer_id', 'status'),
    )

    @hybrid_property
    def subtotal(self) -> float:
        return sum(float(i.line_total or 0) for i in (self.items or []))

    @hybrid_property
    def item_count(self) -> int:
        return sum(int(i.quantity or 0) for i in (self.items or []))

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
        }

    def __repr__(self):
        return f"<OnlineCart {self.cart_id or self.id}>"


@event.listens_for(OnlineCart, 'before_insert')
def _cart_before_insert(mapper, connection, target: 'OnlineCart'):
    if not getattr(target, 'cart_id', None):
        prefix = datetime.utcnow().strftime("CRT%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM online_carts WHERE cart_id LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.cart_id = f"{prefix}-{count+1:04d}"
    if not getattr(target, 'expires_at', None):
        target.expires_at = datetime.utcnow() + timedelta(days=7)


# ---------- Online Cart Item ----------
class OnlineCartItem(db.Model):
    __tablename__ = 'online_cart_items'

    id         = db.Column(db.Integer, primary_key=True)
    cart_id    = db.Column(db.Integer, db.ForeignKey('online_carts.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'),
                           nullable=False, index=True)

    quantity   = db.Column(db.Integer, default=1, nullable=False)
    price      = db.Column(db.Numeric(12, 2), nullable=False)
    added_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    cart    = db.relationship('OnlineCart', back_populates='items')
    product = db.relationship('Product', back_populates='online_cart_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_cart_item_qty_positive'),
        db.CheckConstraint('price >= 0',   name='chk_cart_item_price_non_negative'),
        db.Index('ix_cart_item_cart_product', 'cart_id', 'product_id'),
        db.UniqueConstraint('cart_id', 'product_id', name='uq_cart_item_cart_product'),  # ← منع تكرار المنتج في نفس السلة
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def line_total(self) -> float:
        return int(self.quantity or 0) * float(self.price or 0)

    def to_dict(self):
        return {
            "id": self.id,
            "cart_id": self.cart_id,
            "product_id": self.product_id,
            "quantity": int(self.quantity or 0),
            "price": float(self.price or 0),
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "line_total": self.line_total,
        }

    def __repr__(self):
        pname = getattr(self.product, 'name', None)
        return f"<OnlineCartItem {pname or self.product_id} x{self.quantity}>"


class OnlinePreOrder(db.Model, TimestampMixin):
    __tablename__ = 'online_preorders'

    id           = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, index=True)

    customer_id  = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    cart_id      = db.Column(db.Integer, db.ForeignKey('online_carts.id', ondelete='SET NULL'))

    prepaid_amount = db.Column(db.Numeric(12, 2), default=0)
    total_amount   = db.Column(db.Numeric(12, 2), default=0)

    expected_fulfillment = db.Column(db.DateTime)
    actual_fulfillment   = db.Column(db.DateTime)

    status = db.Column(
        sa_str_enum(['PENDING', 'CONFIRMED', 'FULFILLED', 'CANCELLED'], name='online_preorder_status'),
        default='PENDING', nullable=False, index=True
    )
    payment_status = db.Column(
        sa_str_enum(['PENDING', 'PARTIAL', 'PAID'], name='online_preorder_payment_status'),
        default='PENDING', nullable=False, index=True
    )

    payment_method   = db.Column(db.String(50))
    notes            = db.Column(db.Text)
    shipping_address = db.Column(db.Text)
    billing_address  = db.Column(db.Text)

    customer = db.relationship('Customer', back_populates='online_preorders')
    cart     = db.relationship('OnlineCart')
    items    = db.relationship('OnlinePreOrderItem', back_populates='order', cascade='all, delete-orphan')
    payments = db.relationship('OnlinePayment', back_populates='order')

    __table_args__ = (
        db.CheckConstraint('prepaid_amount >= 0', name='chk_online_prepaid_non_negative'),
        db.CheckConstraint('total_amount  >= 0',  name='chk_online_total_non_negative'),
        db.Index('ix_online_preorders_customer_status', 'customer_id', 'status'),
    )

    @validates('status', 'payment_status')
    def _upper(self, _, v):
        return v.upper() if isinstance(v, str) else v

    @hybrid_property
    def items_subtotal(self) -> float:
        return sum(float(i.line_total or 0) for i in (self.items or []))

    @hybrid_property
    def total_paid(self) -> float:
        return sum(float(p.amount or 0) for p in (self.payments or []) if getattr(p, 'status', None) == 'SUCCESS')

    @hybrid_property
    def balance_due(self) -> float:
        return float(self.total_amount or 0) - float(self.total_paid or 0)

    def update_totals_and_status(self):
        self.total_amount = float(self.items_subtotal or 0)
        if self.balance_due <= 0 and self.total_amount > 0:
            self.payment_status = 'PAID'
        elif self.total_paid > 0:
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
        prefix = datetime.utcnow().strftime("OPR%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM online_preorders WHERE order_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.order_number = f"{prefix}-{count + 1:04d}"
    target.update_totals_and_status()
@event.listens_for(OnlinePreOrder, 'before_update')
def _op_before_update(mapper, connection, target: 'OnlinePreOrder'):
    target.update_totals_and_status()

# ---------- Online PreOrder Item ----------
class OnlinePreOrderItem(db.Model):
    __tablename__ = 'online_preorder_items'

    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('online_preorders.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'),
                           nullable=False, index=True)

    quantity   = db.Column(db.Integer, default=1, nullable=False)
    price      = db.Column(db.Numeric(12, 2), nullable=False)

    order   = db.relationship('OnlinePreOrder', back_populates='items')
    product = db.relationship('Product', back_populates='online_preorder_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_online_item_qty_positive'),
        db.CheckConstraint('price >= 0',   name='chk_online_item_price_non_negative'),
        db.Index('ix_online_item_order_product', 'order_id', 'product_id'),
        db.UniqueConstraint('order_id', 'product_id', name='uq_online_item_order_product'),  # ← منع تكرار المنتج في نفس الطلب
    )

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @hybrid_property
    def line_total(self) -> float:
        return int(self.quantity or 0) * float(self.price or 0)

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "product_id": self.product_id,
            "quantity": int(self.quantity or 0),
            "price": float(self.price or 0),
            "line_total": self.line_total,
        }

    def __repr__(self):
        pname = getattr(self.product, 'name', None)
        return f"<OnlinePreOrderItem {pname or self.product_id} x{self.quantity}>"

# ---------- Online Payment (Gateway) ----------
class OnlinePayment(db.Model, TimestampMixin):
    __tablename__ = 'online_payments'

    id          = db.Column(db.Integer, primary_key=True)
    payment_ref = db.Column(db.String(100), unique=True, index=True)

    order_id = db.Column(db.Integer, db.ForeignKey('online_preorders.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    amount   = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default='ILS', nullable=False)
    method   = db.Column(db.String(50))    # e.g., 'card', 'paypal', 'apple_pay'
    gateway  = db.Column(db.String(50))    # e.g., 'stripe', 'checkout', 'adyen'

    status = db.Column(
        sa_str_enum(['PENDING','SUCCESS','FAILED','REFUNDED'], name='online_payment_status'),
        default='PENDING', nullable=False, index=True
    )

    transaction_data = db.Column(db.JSON)
    processed_at     = db.Column(db.DateTime)

    card_last4       = db.Column(db.String(4), index=True)
    card_encrypted   = db.Column(db.LargeBinary)
    card_expiry      = db.Column(db.String(5))   # MM/YY
    cardholder_name  = db.Column(db.String(128))
    card_brand       = db.Column(db.String(20))
    card_fingerprint = db.Column(db.String(64), index=True)

    order = db.relationship('OnlinePreOrder', back_populates='payments')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='chk_online_payment_amount_positive'),
        db.Index('ix_online_payments_order_status', 'order_id', 'status'),
    )

    @validates('amount')
    def _v_amount(self, _, v):
        if v is None or float(v) <= 0:
            raise ValueError("amount must be > 0")
        return v

    @validates('currency')
    def _v_currency(self, _, v):
        return (v or 'ILS').upper()

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
                if n > 9: n -= 9
            s += n
            alt = not alt
        return s % 10 == 0

    @staticmethod
    def _is_valid_expiry_mm_yy(exp: str) -> bool:
        if not exp or not re.match(r'^\d{2}/\d{2}$', exp):
            return False
        mm, yy = exp.split('/')
        try:
            mm = int(mm); yy = int('20' + yy)
            if not (1 <= mm <= 12):
                return False
            now = datetime.utcnow()
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
            key = current_app.config.get('CARD_ENC_KEY')
            if not key or Fernet is None:
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
        self.card_expiry     = (expiry_mm_yy or '').strip() or None

        if pan_digits:
            if validate and not self._luhn_check(pan_digits):
                raise ValueError("Invalid card number (Luhn check failed)")
            self.card_last4       = pan_digits[-4:]
            self.card_fingerprint = hashlib.sha256(pan_digits.encode('utf-8')).hexdigest()
            self.card_brand       = self._detect_brand(pan_digits)
            f = self._get_fernet()
            self.card_encrypted   = f.encrypt(pan_digits.encode('utf-8')) if f else None
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
        }

    def __repr__(self):
        ref = self.payment_ref or f"OP-{self.id}"
        return f"<OnlinePayment {ref} {self.amount} {self.currency} {self.status}>"


@event.listens_for(OnlinePayment, 'before_insert')
def _online_payment_before_insert(mapper, connection, target: 'OnlinePayment'):
    if not getattr(target, 'payment_ref', None):
        prefix = datetime.utcnow().strftime("PAY%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM online_payments WHERE payment_ref LIKE :pfx"),
            {"pfx": f"{prefix}-%"}
        ).scalar() or 0
        target.payment_ref = f"{prefix}-{count+1:04d}"
    target.currency = (target.currency or 'ILS').upper()
    target.status = (target.status or 'PENDING').upper()
    if target.method:
        target.method = target.method.lower()
    if target.gateway:
        target.gateway = target.gateway.lower()
    if target.status in ('SUCCESS', 'FAILED', 'REFUNDED') and not target.processed_at:
        target.processed_at = datetime.utcnow()


@event.listens_for(OnlinePayment, 'before_update')
def _online_payment_before_update(mapper, connection, target: 'OnlinePayment'):
    target.currency = (target.currency or 'ILS').upper()
    if target.status:
        target.status = target.status.upper()
    if target.method:
        target.method = target.method.lower()
    if target.gateway:
        target.gateway = target.gateway.lower()
    if target.status in ('SUCCESS', 'FAILED', 'REFUNDED') and not target.processed_at:
        target.processed_at = datetime.utcnow()

@event.listens_for(OnlinePayment, 'after_insert')
@event.listens_for(OnlinePayment, 'after_update')
def _online_payment_sync_order(_mapper, _connection, target: 'OnlinePayment'):
    if target.order is not None:
        try:
            target.order.update_totals_and_status()
        except Exception:
            pass
# ===================== ExpenseType =====================
class ExpenseType(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'expense_types'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    is_active   = db.Column(db.Boolean, default=True, nullable=False)

    expenses = relationship('Expense', back_populates='type')

    def __repr__(self):
        return f"<ExpenseType {self.name}>"
# ===================== Expense =====================
class Expense(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer, primary_key=True)
    date         = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    currency     = db.Column(db.String(10), default='ILS', nullable=False)

    type_id      = db.Column(db.Integer, db.ForeignKey('expense_types.id', ondelete='RESTRICT'), nullable=False, index=True)
    employee_id  = db.Column(db.Integer, db.ForeignKey('employees.id',  ondelete='SET NULL'), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='SET NULL'), index=True)
    partner_id   = db.Column(db.Integer, db.ForeignKey('partners.id',   ondelete='SET NULL'), index=True)

    paid_to         = db.Column(db.String(200))
    payment_method  = db.Column(db.String(20), nullable=False, default='cash')
    payment_details = db.Column(db.String(255))
    description     = db.Column(db.String(200))
    notes           = db.Column(db.Text)
    tax_invoice_number = db.Column(db.String(100), index=True)

    check_number      = db.Column(db.String(100))
    check_bank        = db.Column(db.String(100))
    check_due_date    = db.Column(db.Date)

    bank_transfer_ref = db.Column(db.String(100))

    # نخزّن آخر 4 فقط في card_number
    card_number       = db.Column(db.String(8))
    card_holder       = db.Column(db.String(120))
    card_expiry       = db.Column(db.String(10))  # MM/YY أو MM/YYYY

    online_gateway    = db.Column(db.String(50))
    online_ref        = db.Column(db.String(100))

    employee  = relationship('Employee', back_populates='expenses')
    type      = relationship('ExpenseType', back_populates='expenses')
    warehouse = relationship('Warehouse', back_populates='expenses')
    partner   = relationship('Partner',   back_populates='expenses')

    payments = relationship(
        'Payment',
        back_populates='expense',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    __table_args__ = (
        db.CheckConstraint('amount >= 0', name='chk_expense_amount_non_negative'),
        db.CheckConstraint(
            "payment_method IN ('cash','cheque','bank','card','online','other')",
            name='chk_expense_payment_method_allowed'
        ),
    )

    @validates('amount')
    def _v_amount(self, _, v):
        if v is None:
            raise ValueError("amount is required")
        if float(v) < 0:
            raise ValueError("amount must be >= 0")
        return v

    @validates('currency')
    def _v_currency(self, _, v):
        return (v or 'ILS').upper()

    @validates('payment_method')
    def _v_payment_method(self, _, v):
        allowed = {'cash', 'cheque', 'bank', 'card', 'online', 'other'}
        val = (v or 'cash').lower()
        if val not in allowed:
            raise ValueError(f"Invalid payment_method: {v}")
        return val

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.expense_id == self.id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.direction == PaymentDirection.OUTGOING.value,
            )
            .scalar() or 0
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.expense_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.OUTGOING.value)
            )
            .label("total_paid")
        )

    @hybrid_property
    def balance(self):
        return float(self.amount or 0) - float(self.total_paid or 0)

    @balance.expression
    def balance(cls):
        subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(
                (Payment.expense_id == cls.id) &
                (Payment.status == PaymentStatus.COMPLETED.value) &
                (Payment.direction == PaymentDirection.OUTGOING.value)
            )
            .scalar_subquery()
        )
        return cls.amount - subq

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
@event.listens_for(Expense, 'before_insert')
@event.listens_for(Expense, 'before_update')
def _expense_normalize(mapper, connection, target: 'Expense'):
    target.payment_method = (target.payment_method or 'cash').lower()
    target.currency = (target.currency or 'ILS').upper()

    m = target.payment_method
    if m != 'cheque':
        target.check_number = None
        target.check_bank = None
        target.check_due_date = None
    if m != 'bank':
        target.bank_transfer_ref = None
    if m != 'card':
        target.card_holder = None
        target.card_expiry = None
        target.card_number = None
    if m != 'online':
        target.online_gateway = None
        target.online_ref = None

    if m == 'card' and target.card_number:
        digits = ''.join(ch for ch in (target.card_number or '') if ch.isdigit())
        target.card_number = (digits[-4:] if digits else None)

# ===================== Audit Log Model =====================
class AuditLog(db.Model, TimestampMixin):
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    model_name  = db.Column(db.String(100), nullable=False, index=True)
    record_id   = db.Column(db.Integer, index=True)  # قد يكون None لحالات خاصة
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), index=True, nullable=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True)

    action      = db.Column(db.String(20), nullable=False, index=True)  # CREATE / UPDATE / DELETE
    old_data    = db.Column(db.Text)
    new_data    = db.Column(db.Text)

    ip_address  = db.Column(db.String(45))    # IPv4/IPv6
    user_agent  = db.Column(db.String(255))

    __table_args__ = (
        db.Index("ix_audit_model_record", "model_name", "record_id"),
        db.Index("ix_audit_user_time", "user_id", "created_at"),
    )

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

# ===================== Unified Audit Listener =====================
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
        try:
            delattr(obj, "_previous_state")
        except Exception:
            pass
# ===================== Number generators (Invoice/Payment) =====================
if not getattr(Invoice, "_number_listener_attached", False):
    @event.listens_for(Invoice, 'before_insert')
    def _ensure_invoice_number(mapper, connection, target: 'Invoice'):
        if getattr(target, 'invoice_number', None):
            return
        prefix = datetime.utcnow().strftime("INV%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"}
        ).scalar() or 0
        target.invoice_number = f"{prefix}-{count+1:04d}"

    Invoice._number_listener_attached = True

if not getattr(Payment, "_number_listeners_attached", False):
    @event.listens_for(Payment, 'before_insert')
    def _ensure_payment_numbers(mapper, connection, target: 'Payment'):
        if not getattr(target, 'payment_number', None):
            pfx = datetime.utcnow().strftime("PMT%Y%m%d")
            cnt = connection.execute(
                text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"),
                {"pfx": f"{pfx}-%"}
            ).scalar() or 0
            target.payment_number = f"{pfx}-{cnt+1:04d}"

        if not getattr(target, 'receipt_number', None):
            rpfx = datetime.utcnow().strftime("RCT%Y%m%d")
            rcnt = connection.execute(
                text("SELECT COUNT(*) FROM payments WHERE receipt_number LIKE :pfx"),
                {"pfx": f"{rpfx}-%"}
            ).scalar() or 0
            target.receipt_number = f"{rpfx}-{rcnt+1:04d}"

    Payment._number_listeners_attached = True

# ======================= Totals & statuses =======================
if not getattr(Invoice, "_totals_listener_attached", False):
    @event.listens_for(Invoice, "before_insert")
    @event.listens_for(Invoice, "before_update")
    def _compute_invoice_totals(mapper, connection, target: 'Invoice'):
        total = sum(q(getattr(l, "line_total", 0)) for l in (target.lines or [])) if target.lines else Decimal('0.00')
        target.total_amount = total

    Invoice._totals_listener_attached = True

if not getattr(Payment, "_sync_listeners_attached", False):
    @event.listens_for(Payment, "after_insert")
    @event.listens_for(Payment, "after_update")
    def _sync_sale_invoice_on_payment(mapper, connection, target: 'Payment'):
        completed_val = PaymentStatus.COMPLETED.value
        incoming_vals = (PaymentDirection.INCOMING.value, "IN")
        sale_id = getattr(target, "sale_id", None)
        if sale_id:
            total_paid = connection.execute(
                select(func.coalesce(func.sum(Payment.total_amount), 0.0))
                .where(and_(
                    Payment.sale_id == sale_id,
                    Payment.status == completed_val,
                    Payment.direction.in_(incoming_vals)
                ))
            ).scalar_one() or 0.0

            sale_total = connection.execute(
                select(Sale.total_amount).where(Sale.id == sale_id)
            ).scalar_one() or 0.0

            sale_status = (
                PaymentProgress.PAID.value if sale_total > 0 and total_paid >= sale_total
                else PaymentProgress.PARTIAL.value if total_paid > 0
                else PaymentProgress.PENDING.value
            )

            connection.execute(
                update(Sale).where(Sale.id == sale_id).values(payment_status=sale_status)
            )

        inv_id = getattr(target, "invoice_id", None)
        if inv_id:
            inv_total = connection.execute(
                select(Invoice.total_amount).where(Invoice.id == inv_id)
            ).scalar_one() or 0.0

            inv_paid = connection.execute(
                select(func.coalesce(func.sum(Payment.total_amount), 0.0))
                .where(and_(
                    Payment.invoice_id == inv_id,
                    Payment.status == completed_val,
                    Payment.direction.in_(incoming_vals)
                ))
            ).scalar_one() or 0.0

            inv_status = (
                InvoiceStatus.PAID.value if inv_total > 0 and inv_paid >= inv_total
                else InvoiceStatus.PARTIAL.value if inv_paid > 0
                else InvoiceStatus.UNPAID.value
            )

            connection.execute(
                update(Invoice).where(Invoice.id == inv_id).values(status=inv_status)
            )
    Payment._sync_listeners_attached = True

# =============================== Notes ===============================
class Note(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'notes'

    id          = db.Column(db.Integer, primary_key=True)
    content     = db.Column(db.Text, nullable=False)
    author_id   = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
                            nullable=True, index=True)
    entity_type = db.Column(db.String(50), index=True)
    entity_id   = db.Column(db.Integer, index=True)

    is_pinned   = db.Column(db.Boolean, nullable=False, server_default=text("0"), index=True)
    priority    = db.Column(
        sa_str_enum(['LOW', 'MEDIUM', 'HIGH'], name='note_priority'),
        default='MEDIUM', nullable=False, index=True
    )

    author = relationship('User', backref='notes')

    __table_args__ = (
        db.Index('ix_notes_entity', 'entity_type', 'entity_id'),
        db.Index('ix_notes_entity_pinned_created', 'entity_type', 'entity_id', 'is_pinned', 'created_at'),
    )
    # -------------------- Validations / Normalization --------------------
    @validates('content')
    def _v_content(self, _, v):
        v = (v or '').strip()
        if not v:
            raise ValueError("content must not be empty")
        return v

    @validates('entity_type')
    def _v_entity_type(self, _, v):
        return (v or '').strip().upper() or None

    @validates('priority')
    def _v_priority(self, _, v):
        # يدعم كلٍ من string و Enum-backed string
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
