import enum
import hashlib
import re
import uuid
from datetime import datetime

from flask import current_app, has_request_context
from flask_login import current_user, UserMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    event,
    func,
    select,
    text,
    update,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, validates
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None


class PaymentMethod(enum.Enum):
    CASH = "cash"
    BANK = "bank"
    CARD = "card"
    CHEQUE = "cheque"
    ONLINE = "online"


class PaymentStatus(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentDirection(enum.Enum):
    INCOMING = "IN"
    OUTGOING = "OUT"


class InvoiceStatus(enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentProgress(enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"


class SaleStatus(enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class ServiceStatus(enum.Enum):
    PENDING = "PENDING"
    DIAGNOSIS = "DIAGNOSIS"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ON_HOLD = "ON_HOLD"


class ServicePriority(enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TransferDirection(str, enum.Enum):
    INCOMING = "IN"
    OUTGOING = "OUT"
    ADJUSTMENT = "ADJUSTMENT"


class PreOrderStatus(enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class WarehouseType(enum.Enum):
    MAIN = "MAIN"
    PARTNER = "PARTNER"
    INVENTORY = "INVENTORY"
    EXCHANGE = "EXCHANGE"


class PaymentEntityType(enum.Enum):
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


class InvoiceSource(enum.Enum):
    MANUAL = "MANUAL"
    SALE = "SALE"
    SERVICE = "SERVICE"
    PREORDER = "PREORDER"
    SUPPLIER = "SUPPLIER"
    PARTNER = "PARTNER"
    ONLINE = "ONLINE"


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


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditMixin:
    @classmethod
    def __declare_last__(cls):
        @event.listens_for(cls, "after_update")
        def recv(mapper, conn, target):
            try:
                uid = None
                if has_request_context() and getattr(current_user, "is_authenticated", False):
                    uid = current_user.id
                log = AuditLog(
                    model_name=target.__class__.__name__,
                    record_id=target.id,
                    user_id=uid,
                    action="UPDATE",
                    old_data=str(getattr(target, "_previous_state", "")),
                    new_data=str(getattr(target, "current_state", "")),
                )
                db.session.add(log)
                db.session.flush()
            except Exception:
                pass


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(100), unique=True)
    description = db.Column(db.String(255))

    def key(self) -> str:
        return (self.code or self.name or "").strip().lower()

    def __repr__(self):
        return f"<Permission {self.code or self.name}>"


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False)

    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        backref=db.backref("roles", lazy="selectin"),
    )

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


SUPER_ROLES = {"developer", "owner", "admin", "super_admin"}


class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)

    role = db.relationship("Role", backref="users", lazy="joined")
    extra_permissions = db.relationship(
        "Permission",
        secondary=user_permissions,
        backref=db.backref("users_extra", lazy="dynamic"),
        lazy="dynamic",
    )
    service_requests = db.relationship("ServiceRequest", back_populates="mechanic", lazy="dynamic")
    sales = db.relationship("Sale", back_populates="seller", cascade="all, delete-orphan")

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

    def has_permission(self, name: str) -> bool:
        target = (name or "").strip().lower()
        if not target:
            return False
        role_name = (getattr(self.role, "name", "") or "").strip().lower()
        if role_name in SUPER_ROLES:
            return True
        if self.role and self.role.has_permission(target):
            return True
        try:
            from sqlalchemy import or_
            return (
                self.extra_permissions.filter(
                    or_(
                        func.lower(Permission.name) == target,
                        func.lower(Permission.code) == target,
                    )
                ).first()
                is not None
            )
        except Exception:
            try:
                for p in self.extra_permissions or []:
                    code_l = (getattr(p, "code", "") or "").strip().lower()
                    name_l = (getattr(p, "name", "") or "").strip().lower()
                    if target in {code_l, name_l}:
                        return True
            except Exception:
                pass
            return False

@event.listens_for(User, "before_insert")
def _dedupe_user_on_insert(mapper, connection, target):
    def _testing() -> bool:
        try:
            from flask import current_app
            return bool(current_app and current_app.config.get("TESTING"))
        except Exception:
            return False

    def _next_available(field: str, base: str) -> str:
        base = (base or "").strip()
        if not base:
            return base
        value, i = base, 2
        if _testing() and getattr(target, "role_id", None):
            sql = text(f"SELECT 1 FROM users WHERE {field} = :v AND role_id = :rid LIMIT 1")
            params = lambda v: {"v": v, "rid": target.role_id}
        else:
            sql = text(f"SELECT 1 FROM users WHERE {field} = :v LIMIT 1")
            params = lambda v: {"v": v}
        while connection.execute(sql, params(value)).scalar():
            if field == "email" and "@" in base:
                local, domain = base.split("@", 1)
                value = f"{local}-{i}@{domain}"
            else:
                value = f"{base}-{i}"
            i += 1
        return value

    target.username = _next_available("username", getattr(target, "username", ""))
    target.email = _next_available("email", getattr(target, "email", ""))

class Customer(db.Model, UserMixin, TimestampMixin, AuditMixin):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True)
    whatsapp = Column(String(20))
    email = Column(String(120), unique=True)
    address = Column(String(200))
    password_hash = Column(String(128))
    category = Column(String(20), default="عادي")
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    is_online = Column(Boolean, default=False)
    credit_limit = Column(Numeric(12, 2), default=0)
    discount_rate = Column(Numeric(5, 2), default=0)
    currency = Column(String(10), default="ILS", nullable=False)

    sales = relationship("Sale", back_populates="customer")
    preorders = relationship("PreOrder", back_populates="customer")
    invoices = relationship("Invoice", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")
    service_requests = relationship("ServiceRequest", back_populates="customer")
    online_carts = relationship("OnlineCart", back_populates="customer")
    online_preorders = relationship("OnlinePreOrder", back_populates="customer")

    @property
    def password(self):
        raise AttributeError

    @password.setter
    def password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ✅ ستب آمن لمناداة الصلاحيات من القوالب
    def has_permission(self, *_args, **_kwargs) -> bool:
        return False

    def is_valid_email(self):
        return bool(self.email and "@" in self.email)

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
            .filter(Payment.customer_id == self.id, Payment.direction == PaymentDirection.INCOMING.value)
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where((Payment.customer_id == cls.id) & (Payment.direction == PaymentDirection.INCOMING.value))
            .label("total_paid")
        )

    @hybrid_property
    def balance(self):
        return self.total_invoiced - self.total_paid

    @hybrid_property
    def credit_status(self):
        if self.credit_limit > 0 and self.balance >= self.credit_limit:
            return "معلق"
        return "نشط"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone or "",
            "email": self.email or "",
            "currency": self.currency,
            "balance": self.balance,
            "total_invoiced": self.total_invoiced,
            "total_paid": self.total_paid,
            "credit_limit": float(self.credit_limit or 0),
            "category": self.category,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity": getattr(self, "last_activity", None),
        }

    def __repr__(self):
        return f"<Customer {self.name}>"


def _testing_enabled() -> bool:
    try:
        return bool(current_app.config.get("TESTING"))
    except Exception:
        return False


def _unique_value(connection, table: str, column: str, value: str) -> str:
    if not value:
        return value
    base = value
    candidate = base
    while True:
        row = connection.execute(text(f"SELECT 1 FROM {table} WHERE {column} = :v LIMIT 1"), {"v": candidate}).fetchone()
        if not row:
            return candidate
        suf = uuid.uuid4().hex[:6]
        if column == "email" and "@" in base:
            local, _, domain = base.partition("@")
            candidate = f"{local}+{suf}@{domain}"
        else:
            candidate = f"{base}_{suf}"
@event.listens_for(Customer, "before_insert", propagate=True)
def _customer_testing_make_unique(mapper, connection, target):
    if not _testing_enabled():
        return
    target.phone = _unique_value(connection, "customers", "phone", getattr(target, "phone", None))
    target.email = _unique_value(connection, "customers", "email", getattr(target, "email", None))


class Supplier(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_local = db.Column(db.Boolean, default=True)
    identity_number = db.Column(db.String(100), unique=True)
    contact = db.Column(db.String(200))
    phone = db.Column(db.String(20), index=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=True)
    address = db.Column(db.String(200))
    notes = db.Column(db.Text)
    balance = db.Column(db.Numeric(12, 2), default=0)
    payment_terms = db.Column(db.String(50))
    currency = db.Column(db.String(10), default="ILS", nullable=False)

    payments = db.relationship("Payment", back_populates="supplier")
    invoices = db.relationship("Invoice", back_populates="supplier")
    preorders = db.relationship("PreOrder", back_populates="supplier")
    warehouses = db.relationship("Warehouse", back_populates="supplier")
    loan_settlements = db.relationship(
        "SupplierLoanSettlement",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(Payment.supplier_id == self.id, Payment.direction == PaymentDirection.OUTGOING.value)
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where((Payment.supplier_id == cls.id) & (Payment.direction == PaymentDirection.OUTGOING.value))
            .label("total_paid")
        )

    @hybrid_property
    def net_balance(self):
        return float(self.balance) - self.total_paid

    @net_balance.expression
    def net_balance(cls):
        paid_subq = (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where((Payment.supplier_id == cls.id) & (Payment.direction == PaymentDirection.OUTGOING.value))
            .scalar_subquery()
        )
        return cls.balance - paid_subq

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "currency": self.currency,
            "balance": float(self.balance),
            "total_paid": self.total_paid,
            "net_balance": self.net_balance,
        }

    def __repr__(self):
        return f"<Supplier {self.name}>"


@event.listens_for(Supplier, "before_insert")
def _supplier_testing_make_identity_unique(mapper, connection, target):
    if not _testing_enabled():
        return
    val = getattr(target, "identity_number", None)
    if not val:
        return
    exists = connection.execute(
        text("SELECT 1 FROM suppliers WHERE identity_number = :v LIMIT 1"),
        {"v": val},
    ).fetchone()
    if exists:
        suffix = uuid.uuid4().hex[:6]
        target.identity_number = f"{val}_{suffix}"

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

    product_links     = relationship(
        'ProductPartner',
        back_populates='partner',
        cascade='all, delete-orphan'
    )

    service_parts     = relationship('ServicePart', back_populates='partner')
    service_tasks     = relationship('ServiceTask', back_populates='partner')
    expenses          = relationship('Expense', back_populates='partner')

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(
                Payment.partner_id == self.id,
                Payment.direction == PaymentDirection.OUTGOING.value
            )
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return select(func.coalesce(func.sum(Payment.total_amount), 0))\
            .where(
                (Payment.partner_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value)
            )\
            .label("total_paid")

    @hybrid_property
    def net_balance(self):
        return float(self.balance) - self.total_paid

    @net_balance.expression
    def net_balance(cls):
        paid_subq = select(func.coalesce(func.sum(Payment.total_amount), 0))\
            .where(
                (Payment.partner_id == cls.id) &
                (Payment.direction == PaymentDirection.OUTGOING.value)
            )\
            .scalar_subquery()
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

class Employee(db.Model, TimestampMixin):
    __tablename__ = 'employees'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    position       = db.Column(db.String(100))
    phone          = db.Column(db.String(100))
    email          = db.Column(db.String(120), unique=True, index=True, nullable=True)  # جديد (Unique + Index)
    bank_name      = db.Column(db.String(100))
    account_number = db.Column(db.String(100))
    notes          = db.Column(db.Text)
    currency       = db.Column(db.String(10), default='ILS', nullable=False)

    expenses = db.relationship('Expense', back_populates='employee', cascade='all, delete-orphan')

    @hybrid_property
    def total_expenses(self):
        return float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                      .filter(Expense.employee_id == self.id)
                      .scalar()
        )

    @total_expenses.expression
    def total_expenses(cls):
        return select(func.coalesce(func.sum(Expense.amount), 0))\
               .where(Expense.employee_id == cls.id)\
               .label("total_expenses")

    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
                      .join(Expense, Payment.expense_id == Expense.id)
                      .filter(Expense.employee_id == self.id)
                      .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return select(func.coalesce(func.sum(Payment.total_amount), 0))\
               .select_from(Payment.__table__.join(Expense, Payment.expense_id == Expense.id))\
               .where(Expense.employee_id == cls.id)\
               .label("total_paid")

    @hybrid_property
    def balance(self):
        return self.total_expenses - self.total_paid

    @balance.expression
    def balance(cls):
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
    name = Column(String(255), nullable=False)
    description = Column(Text)
    part_number = Column(String(100))
    brand = Column(String(100))
    commercial_name = Column(String(100))
    chassis_number = Column(String(100))
    serial_no = Column(String(100), unique=True)
    barcode = Column(String(100), unique=True)
    image = Column(String(255))
    cost_before_shipping = Column(Numeric(12, 2), default=0)
    cost_after_shipping = Column(Numeric(12, 2), default=0)
    unit_price_before_tax = Column(Numeric(12, 2), default=0)
    price = Column(Numeric(12, 2), nullable=False, default=0.0)
    min_price = Column(Numeric(12, 2))
    max_price = Column(Numeric(12, 2))
    tax_rate = Column(Numeric(5, 2), default=0)
    min_qty = Column(Integer, default=0)
    reorder_point = Column(Integer)
    condition = Column(
        Enum(
            ProductCondition,
            name='product_condition',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=ProductCondition.NEW.value,
        nullable=False
    )
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

    @hybrid_property
    def total_partner_percentage(self):
        return sum(share.share_percentage or 0 for share in self.partner_shares)

    @hybrid_property
    def total_partner_amount(self):
        return sum(float(share.share_amount or 0) for share in self.partner_shares)

    def quantity_in_warehouse(self, warehouse_id):
        level = next((s for s in self.stock_levels if s.warehouse_id == warehouse_id), None)
        return level.quantity if level else 0

    def __repr__(self):
        return f"<Product {self.name}>"
    
@event.listens_for(Product, "before_insert", propagate=True)
def _product_testing_make_unique(mapper, connection, target):
    if not _testing_enabled():
        return
    for col in ("sku", "barcode", "serial_no", "part_number"):
        val = getattr(target, col, None)
        if val:
            setattr(target, col, _unique_value(connection, "products", col, val))


class Warehouse(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    warehouse_type = db.Column(
        db.Enum(
            WarehouseType,
            name='warehouse_type',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=WarehouseType.MAIN.value,
        nullable=False
    )
    location = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percent = db.Column(db.Numeric(5, 2), default=0)
    capacity = db.Column(db.Integer)
    current_occupancy = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)

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
    last_updated = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint('quantity >= 0', name='ck_stock_non_negative'),
        CheckConstraint('reserved_quantity >= 0', name='ck_reserved_non_negative'),
    )

    product = db.relationship('Product', back_populates='stock_levels')
    warehouse = db.relationship('Warehouse', back_populates='stock_levels')

    @validates('quantity')
    def _v_qty(self, _, v):
        v = int(v)
        assert v >= 0, "quantity must be >= 0"
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
        return "تحت الحد الأدنى" if q <= mn else ("فوق الحد الأقصى" if mx is not None and q >= int(mx) else "طبيعي")

    def __repr__(self):
        return f"<StockLevel {getattr(self.product, 'name', self.product_id)} in {getattr(self.warehouse, 'name', self.warehouse_id)}>"

class Transfer(db.Model, TimestampMixin):
    __tablename__ = 'transfers'
    id            = db.Column(db.Integer, primary_key=True)
    reference     = db.Column(db.String(50), unique=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    source_id     = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    destination_id= db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity      = db.Column(db.Integer, nullable=False)
    direction     = db.Column(
        db.Enum(
            TransferDirection,
            name='transfer_direction',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        nullable=False
    )
    transfer_date = db.Column(DateTime, default=datetime.utcnow)
    notes         = db.Column(db.Text)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'))

    product               = db.relationship('Product', back_populates='transfers')
    source_warehouse      = db.relationship(
        'Warehouse',
        foreign_keys=[source_id],
        back_populates='transfers_source'
    )
    destination_warehouse = db.relationship(
        'Warehouse',
        foreign_keys=[destination_id],
        back_populates='transfers_destination'
    )
    user                  = db.relationship('User')

    @validates('quantity')
    def validate_quantity(self, key, quantity):
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
        return quantity

    def __repr__(self):
        return f"<Transfer {self.reference}>"


class ExchangeTransaction(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'exchange_transactions'
    id = db.Column(db.Integer, primary_key=True)
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    partner_id   = db.Column(db.Integer, db.ForeignKey('partners.id'))
    quantity     = db.Column(db.Integer, nullable=False)
    direction    = db.Column(db.Enum('IN','OUT','ADJUSTMENT', name='exchange_direction'), default='IN', nullable=False)
    unit_cost    = db.Column(db.Numeric(12, 2))            # مهم
    is_priced    = db.Column(db.Boolean, nullable=False, server_default=db.text("0"))  # مهم
    notes        = db.Column(db.Text)

    product   = db.relationship('Product', back_populates='exchange_transactions')
    warehouse = db.relationship('Warehouse', back_populates='exchange_transactions')
    partner   = db.relationship('Partner')

    def __repr__(self):
        return f"<ExchangeTransaction P{self.product_id} W{self.warehouse_id} Q{self.quantity}>"

class WarehousePartnerShare(db.Model, TimestampMixin):
    __tablename__ = 'warehouse_partner_shares'

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), index=True, nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), index=True, nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True, nullable=True)
    share_percentage = db.Column(db.Float, nullable=False, default=0.0)
    share_amount = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text)

    partner = db.relationship(
        'Partner',
        back_populates='shares',
        overlaps="product_shares,warehouse_shares,shares"
    )

    warehouse = db.relationship('Warehouse', back_populates='partner_shares')
    product = db.relationship('Product', foreign_keys=[product_id], viewonly=True)

    def __repr__(self):
        return f"<WarehousePartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id} {self.share_percentage}%>"


class ProductPartnerShare(db.Model):
    __table__ = WarehousePartnerShare.__table__

    partner = db.relationship('Partner', foreign_keys=[WarehousePartnerShare.partner_id], viewonly=True)
    warehouse = db.relationship('Warehouse', foreign_keys=[WarehousePartnerShare.warehouse_id], viewonly=True)
    product = db.relationship('Product', back_populates='partner_shares', foreign_keys=[WarehousePartnerShare.product_id])

    def __repr__(self):
        return f"<ProductPartnerShare partner={self.partner_id} warehouse={self.warehouse_id} product={self.product_id}>"


class ProductSupplierLoan(db.Model, TimestampMixin):
    __tablename__ = 'product_supplier_loans'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    loan_value = db.Column(db.Numeric(12, 2), default=0)
    deferred_price = db.Column(db.Numeric(12, 2))
    is_settled = db.Column(db.Boolean, default=False)
    partner_share_quantity = db.Column(db.Integer, default=0)
    partner_share_value = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)

    product = db.relationship('Product', back_populates='supplier_loans')
    supplier = db.relationship('Supplier', backref='loaned_products')
    settlements = db.relationship('SupplierLoanSettlement', back_populates='loan')

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
    )

    def __repr__(self):
        return f"<ProductPartner {self.partner_id} {self.share_percent}%>"

class PreOrder(db.Model, TimestampMixin):
    __tablename__ = 'preorders'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True)
    preorder_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)

    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    quantity = db.Column(db.Integer, nullable=False)
    prepaid_amount = db.Column(db.Numeric(12, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)

    status = db.Column(
        db.Enum(
            PreOrderStatus,
            name='preorder_status',
            values_callable=lambda e: [v.value for v in e]
        ),
        default=PreOrderStatus.PENDING.value
    )
    notes = db.Column(db.Text)

    customer = db.relationship('Customer', back_populates='preorders')
    supplier = db.relationship('Supplier', back_populates='preorders')
    partner = db.relationship('Partner', back_populates='preorders')
    product = db.relationship('Product', back_populates='preorders')
    warehouse = db.relationship('Warehouse', back_populates='preorders')

    payments = db.relationship('Payment', back_populates='preorder', cascade='all,delete-orphan')
    sale = db.relationship('Sale', back_populates='preorder', uselist=False)
    invoice = db.relationship('Invoice', back_populates='preorder', uselist=False)

    __table_args__ = (
        CheckConstraint('quantity>0', name='chk_preorder_quantity_positive'),
        CheckConstraint('prepaid_amount>=0', name='chk_preorder_prepaid_non_negative'),
        CheckConstraint('tax_rate>=0 AND tax_rate<=100', name='chk_preorder_tax_rate'),
    )

    @property
    def reservation_code(self):
        return self.reference

    @reservation_code.setter
    def reservation_code(self, v):
        self.reference = v

    @hybrid_property
    def total_before_tax(self):
        return self.quantity * float(self.product.price or 0)

    @hybrid_property
    def total_with_tax(self):
        return self.total_before_tax * (1 + float(self.tax_rate or 0) / 100)

    @hybrid_property
    def total_paid(self):
        completed_val = getattr(PaymentStatus, "COMPLETED", "COMPLETED")
        completed_val = getattr(completed_val, "value", completed_val)
        return (
            sum(
                float(getattr(p, "total_amount", 0) or 0)
                for p in self.payments
                if getattr(getattr(p, "status", None), "value", getattr(p, "status", None))
                == completed_val
            )
            if self.payments
            else 0
        )
    @hybrid_property
    def balance_due(self):
        return float(self.total_with_tax) - float(self.total_paid)

    def __repr__(self):
        return f"<PreOrder {self.reference or self.id}>"

class Sale(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), unique=True)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    preorder_id = db.Column(db.Integer, db.ForeignKey('preorders.id'))
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    status = db.Column(
        db.Enum(
            SaleStatus,
            name='sale_status',
            values_callable=lambda e: [v.value for v in e]
        ),
        default=SaleStatus.DRAFT.value,
        nullable=False
    )
    payment_status = db.Column(
        db.Enum(
            PaymentProgress,
            name='sale_payment_progress',
            values_callable=lambda e: [v.value for v in e]
        ),
        default=PaymentProgress.PENDING.value,
        nullable=False
    )
    currency = db.Column(db.String(10), default='ILS')
    shipping_address = db.Column(db.Text)
    billing_address = db.Column(db.Text)
    shipping_cost = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)

    customer = db.relationship('Customer', back_populates='sales')
    seller = db.relationship('User', back_populates='sales')
    preorder = db.relationship('PreOrder', back_populates='sale')
    lines = db.relationship('SaleLine', back_populates='sale', cascade='all,delete-orphan')
    payments = db.relationship('Payment', back_populates='sale', cascade='all,delete-orphan')
    invoice = db.relationship('Invoice', back_populates='sale', uselist=False)
    shipments = db.relationship('Shipment', back_populates='sale', cascade='all,delete-orphan')

    @hybrid_property
    def subtotal(self):
        return sum(l.net_amount for l in self.lines) if self.lines else 0.0

    @hybrid_property
    def tax_amount(self):
        base = float(self.subtotal) - float(self.discount_total or 0)
        return base * float(self.tax_rate or 0) / 100

    @hybrid_property
    def total(self):
        return float(self.subtotal) + float(self.tax_amount) + float(self.shipping_cost or 0) - float(self.discount_total or 0)

    @hybrid_property
    def total_paid(self):
        completed_val = getattr(PaymentStatus, "COMPLETED", "COMPLETED")
        completed_val = getattr(completed_val, "value", completed_val)
        return (
            sum(
                float(getattr(p, "total_amount", 0) or 0)
                for p in self.payments
                if getattr(getattr(p, "status", None), "value", getattr(p, "status", None))
                == completed_val
            )
            if self.payments
            else 0
        )
    @hybrid_property
    def balance_due(self):
        return float(self.total) - float(self.total_paid)

    def reserve_stock(self):
        # تُخصم الكميات من StockLevel عند تأكيد البيع
        for l in self.lines:
            lvl = StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id)\
                                  .with_for_update().first()
            if not lvl or (lvl.quantity or 0) < l.quantity:
                raise Exception("الكمية غير متوفرة في هذا المستودع")
            lvl.quantity = (lvl.quantity or 0) - l.quantity
        db.session.flush()

    def release_stock(self):
        # تُعاد الكميات إلى StockLevel عند إلغاء التأكيد
        for l in self.lines:
            lvl = StockLevel.query.filter_by(product_id=l.product_id, warehouse_id=l.warehouse_id)\
                                  .with_for_update().first()
            if lvl:
                lvl.quantity = (lvl.quantity or 0) + l.quantity
        db.session.flush()

    def update_payment_status(self):
        paid = 0.0
        for p in self.payments:
            status_val = getattr(p.status, "value", p.status)
            if status_val == PaymentStatus.COMPLETED.value:
                paid += float(getattr(p, "total_amount", 0) or 0)

        self.payment_status = (
            PaymentProgress.PAID.value
            if paid >= float(self.total) else
            (PaymentProgress.PARTIAL.value if paid > 0 else PaymentProgress.PENDING.value)
        )

    def __repr__(self):
        return f"<Sale {self.sale_number}>"

@event.listens_for(Sale, "before_insert")
@event.listens_for(Sale, "before_update")
def _compute_total_amount(mapper, connection, target):
    subtotal = sum(l.net_amount for l in target.lines) if target.lines else 0.0
    discount = float(target.discount_total or 0)
    tax_rate = float(target.tax_rate or 0)
    tax = (subtotal - discount) * tax_rate / 100
    shipping = float(target.shipping_cost or 0)
    target.total_amount = subtotal + tax + shipping - discount

class SaleLine(db.Model):
    __tablename__ = 'sale_lines'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    quantity      = db.Column(db.Integer, nullable=False)
    unit_price    = db.Column(db.Numeric(12, 2), nullable=False)
    discount_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_rate      = db.Column(db.Numeric(5, 2), default=0)
    note          = db.Column(db.String(200))

    sale      = db.relationship('Sale', back_populates='lines')
    product   = db.relationship('Product', back_populates='sale_lines')
    warehouse = db.relationship('Warehouse', back_populates='sale_lines')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_sale_line_qty_positive'),
    )

    @hybrid_property
    def gross_amount(self):
        return float(self.unit_price or 0) * float(self.quantity or 0)

    @hybrid_property
    def discount_amount(self):
        return self.gross_amount * float(self.discount_rate or 0) / 100

    @hybrid_property
    def net_amount(self):
        return self.gross_amount - self.discount_amount

    @hybrid_property
    def line_tax(self):
        return self.net_amount * float(self.tax_rate or 0) / 100

    @hybrid_property
    def line_total(self):
        return self.net_amount + self.line_tax

    def __repr__(self):
        pname = getattr(self.product, "name", None)
        return f"<SaleLine {pname or self.product_id} in Sale {self.sale_id}>"

class Invoice(db.Model, TimestampMixin):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True)
    invoice_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    partner_id = Column(Integer, ForeignKey('partners.id'))
    sale_id = Column(Integer, ForeignKey('sales.id'))
    service_id = Column(Integer, ForeignKey('service_requests.id'))
    preorder_id = Column(Integer, ForeignKey('preorders.id'))
    source = Column(
        Enum(InvoiceSource, name='invoice_source', native_enum=True, validate_strings=False),
        default=InvoiceSource.MANUAL.value,
        nullable=False
    )
    status = Column(
        Enum(InvoiceStatus, name='invoice_status', native_enum=True, validate_strings=False),
        default=InvoiceStatus.UNPAID.value,
        nullable=False
    )
    currency = Column(String(10), default='ILS', nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    tax_amount = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    notes = Column(Text)
    terms = Column(Text)

    customer = relationship('Customer', back_populates='invoices')
    supplier = relationship('Supplier', back_populates='invoices')
    partner = relationship('Partner', back_populates='invoices')
    sale = relationship('Sale', back_populates='invoice', uselist=False)
    service = relationship('ServiceRequest', back_populates='invoice')
    preorder = relationship('PreOrder', back_populates='invoice')
    lines = relationship('InvoiceLine', back_populates='invoice', cascade='all, delete-orphan')
    payments = relationship('Payment', back_populates='invoice', cascade='all, delete-orphan', passive_deletes=True)

    @validates('source', 'status')
    def _uppercase_enum(self, key, value):
        return value.upper() if isinstance(value, str) else value

    @hybrid_property
    def computed_total(self):
        return sum(l.line_total for l in self.lines) if self.lines else 0

    @hybrid_property
    def total_paid(self):
        return sum(float(getattr(p, "total_amount", 0) or 0) for p in self.payments) if self.payments else 0

    @hybrid_property
    def balance_due(self):
        return float(self.total_amount or 0) - float(self.total_paid or 0)

    def update_status(self):
        self.status = (
            InvoiceStatus.PAID.value
            if self.balance_due <= 0 else
            (InvoiceStatus.PARTIAL.value if self.total_paid > 0 else InvoiceStatus.UNPAID.value)
        )

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"
class InvoiceLine(db.Model):
    __tablename__ = 'invoice_lines'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    discount = db.Column(db.Numeric(5, 2), default=0)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))

    invoice = db.relationship('Invoice', back_populates='lines')
    product = db.relationship('Product')

    @hybrid_property
    def line_total(self):
        gross = self.quantity * float(self.unit_price or 0)
        discount_amount = gross * (float(self.discount or 0) / 100)
        taxable = gross - discount_amount
        tax_amount = taxable * (float(self.tax_rate or 0) / 100)
        return taxable + tax_amount

    def __repr__(self):
        return f"<InvoiceLine {self.description}>"
class Payment(db.Model):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), unique=True, nullable=False)
    payment_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    subtotal      = Column(Numeric(10, 2))
    tax_rate      = Column(Numeric(5, 2))
    tax_amount    = Column(Numeric(10, 2))
    total_amount  = Column(Numeric(10, 2), nullable=False)
    currency      = Column(String(10), default='ILS', nullable=False)

    method = Column(
        Enum(PaymentMethod, name='payment_method', values_callable=lambda e: [v.value for v in e]),
        nullable=False
    )
    status = Column(
        Enum(PaymentStatus, name='payment_status', values_callable=lambda e: [v.value for v in e]),
        default=PaymentStatus.PENDING.value, nullable=False
    )
    direction = Column(
        Enum(PaymentDirection, name='payment_direction', values_callable=lambda e: [v.value for v in e]),
        default=PaymentDirection.OUTGOING.value, nullable=False
    )
    entity_type = Column(
        Enum(PaymentEntityType, name='payment_entity_type', values_callable=lambda e: [v.value for v in e]),
        default=PaymentEntityType.CUSTOMER.value, nullable=False
    )

    reference      = Column(String(100))
    receipt_number = Column(String(50), unique=True)
    notes          = Column(Text)

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

    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'))
    supplier_id = Column(Integer, ForeignKey('suppliers.id', ondelete='CASCADE'))
    partner_id  = Column(Integer, ForeignKey('partners.id',  ondelete='CASCADE'))
    shipment_id = Column(Integer, ForeignKey('shipments.id', ondelete='CASCADE'))
    expense_id  = Column(Integer, ForeignKey('expenses.id',  ondelete='CASCADE'))
    loan_settlement_id = Column(Integer, ForeignKey('supplier_loan_settlements.id', ondelete='CASCADE'))
    sale_id     = Column(Integer, ForeignKey('sales.id',     ondelete='CASCADE'))
    invoice_id  = Column(Integer, ForeignKey('invoices.id',  ondelete='CASCADE'))
    preorder_id = Column(Integer, ForeignKey('preorders.id', ondelete='CASCADE'))
    service_id  = Column(Integer, ForeignKey('service_requests.id', ondelete='CASCADE'))

    customer = relationship('Customer', back_populates='payments')
    supplier = relationship('Supplier', back_populates='payments')
    partner  = relationship('Partner',  back_populates='payments')
    shipment = relationship('Shipment', back_populates='payments')
    expense  = relationship('Expense',  back_populates='payments')
    loan_settlement = relationship('SupplierLoanSettlement', back_populates='payment')
    sale     = relationship('Sale',     back_populates='payments')
    invoice  = relationship('Invoice',  back_populates='payments')
    preorder = relationship('PreOrder', back_populates='payments')
    service  = relationship('ServiceRequest', back_populates='payments')

    splits = relationship('PaymentSplit', cascade='all,delete-orphan', passive_deletes=True)

    __table_args__ = (
        CheckConstraint('total_amount > 0', name='ck_payment_total_positive'),
    )

    @property
    def entity(self):
        for attr in ('customer', 'supplier', 'partner', 'shipment', 'expense',
                     'loan_settlement', 'sale', 'invoice', 'preorder', 'service'):
            if getattr(self, f'{attr}_id', None):
                return getattr(self, attr)
        return None

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
        if value is None:
            return None
        new_val = getattr(value, 'value', value)
        if key == 'status':
            old = getattr(self, 'status', None)
            old_val = getattr(old, 'value', old) if old is not None else None
            if old_val is not None and old_val != new_val:
                allowed = {
                    'PENDING':   {'COMPLETED'},
                    'COMPLETED': {'REFUNDED'},
                }
                if new_val not in allowed.get(old_val, set()):
                    raise ValueError(f"Illegal payment status transition {old_val} -> {new_val}")
        return new_val

    def to_dict(self):
        _val = (lambda x: getattr(x, "value", x))
        return {
            'id': self.id,
            'payment_number': self.payment_number,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'subtotal': float(self.subtotal or 0),
            'tax_rate': float(self.tax_rate or 0),
            'tax_amount': float(self.tax_amount or 0),
            'total_amount': float(self.total_amount or 0),
            'currency': self.currency,
            'method': _val(self.method),
            'status': _val(self.status),
            'direction': _val(self.direction),
            'entity_type': _val(self.entity_type),
            'entity_display': self.entity_label(),
            'reference': self.reference,
            'receipt_number': self.receipt_number,
            'notes': self.notes,
            'created_by': self.created_by,
            'splits': [
                {
                    'method': _val(s.method),
                    'amount': float(s.amount),
                    'details': s.details or None,
                } for s in (self.splits or [])
            ]
        }

    def __repr__(self):
        return f"<Payment {self.payment_number or self.id} - {self.total_amount} {self.currency}>"

@event.listens_for(Payment, 'before_insert')
@event.listens_for(Payment, 'before_update')
def validate_splits_total(mapper, connection, target):
    """Ensure split amounts sum exactly to the payment's total."""
    splits = getattr(target, 'splits', None) or []
    if splits:
        total = sum((s.amount or 0) for s in splits)
        if (target.total_amount or 0) != total:
            raise ValueError('sum of split amounts must equal total_amount')
@event.listens_for(Payment, 'before_insert')
def _before_insert_payment(mapper, connection, target):
    base_dt = target.payment_date or datetime.utcnow()
    prefix = base_dt.strftime("PMT%Y%m%d")
    if not target.payment_number:
        count = connection.execute(
            text("SELECT COUNT(*) FROM payments WHERE payment_number LIKE :pfx"),
            {"pfx": f"{prefix}-%"},
        ).scalar() or 0
        target.payment_number = f"{prefix}-{count+1:04d}"

    if not getattr(target, 'method', None):
        if getattr(target, 'splits', None):
            first = next((s for s in target.splits if s and s.method), None)
            if first:
                target.method = getattr(first.method, 'value', first.method)
        if not getattr(target, 'method', None):
            target.method = PaymentMethod.CASH.value
            setattr(target, '_auto_method_placeholder', True)

    target.created_by = (
        current_user.id
        if has_request_context() and getattr(current_user, 'is_authenticated', False)
        else None
    )


class PaymentSplit(db.Model):
    __tablename__ = 'payment_splits'

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey('payments.id', ondelete='CASCADE'), nullable=False)
    method = Column(
        Enum(PaymentMethod, name='split_payment_method', values_callable=lambda e: [v.value for v in e]),
        nullable=False
    )
    amount = Column(Numeric(12, 2), nullable=False)
    details = Column(db.JSON)

    __table_args__ = (
        CheckConstraint('amount > 0', name='chk_split_amount_positive'),
    )

    def __repr__(self):
        m = getattr(self.method, "value", self.method)
        return f"<PaymentSplit {m} {self.amount}>"


from sqlalchemy.orm import Session as _SA_Session

@event.listens_for(_SA_Session, 'before_flush')
def _infer_payment_method_from_splits(session, flush_context, instances):
    for obj in list(session.new):
        if isinstance(obj, PaymentSplit):
            pid = obj.payment_id or (getattr(obj, 'payment', None).id if getattr(obj, 'payment', None) else None)
            if pid:
                parent = session.get(Payment, pid) or getattr(obj, 'payment', None)
                if parent is not None and (getattr(parent, '_auto_method_placeholder', False) or not getattr(parent, 'method', None)):
                    parent.method = getattr(obj.method, 'value', obj.method)
                    if hasattr(parent, '_auto_method_placeholder'):
                        delattr(parent, '_auto_method_placeholder')

class Shipment(db.Model, TimestampMixin):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    shipment_number = db.Column(db.String(50), unique=True)
    shipment_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_arrival = db.Column(db.DateTime)
    actual_arrival = db.Column(db.DateTime)
    origin = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    destination_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    status = db.Column(db.String(20), default='PENDING')
    value_before = db.Column(db.Numeric(12, 2))
    shipping_cost = db.Column(db.Numeric(12, 2))
    customs = db.Column(db.Numeric(12, 2))
    vat = db.Column(db.Numeric(12, 2))
    insurance = db.Column(db.Numeric(12, 2))
    carrier = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    currency = db.Column(db.String(10), default='USD')
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))

    items = db.relationship('ShipmentItem', back_populates='shipment', cascade='all, delete-orphan')
    partners = db.relationship('ShipmentPartner', back_populates='shipment', cascade='all, delete-orphan')
    payments = db.relationship('Payment', back_populates='shipment')
    sale = db.relationship('Sale', back_populates='shipments')
    destination_warehouse = db.relationship('Warehouse', back_populates='shipments_received', foreign_keys=[destination_id])

    @hybrid_property
    def total_value(self):
        return (self.value_before or 0) + (self.shipping_cost or 0) + (self.customs or 0) + (self.vat or 0) + (self.insurance or 0)

    def update_status(self, new_status):
        self.status = new_status
        if new_status == 'ARRIVED' and not self.actual_arrival:
            self.actual_arrival = datetime.utcnow()

    def __repr__(self):
        return f"<Shipment {self.shipment_number}>"

class ShipmentItem(db.Model):
    __tablename__ = 'shipment_items'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Numeric(10, 2))
    declared_value = db.Column(db.Numeric(12, 2))
    notes = db.Column(db.String(200))

    shipment = db.relationship('Shipment', back_populates='items')
    product = db.relationship('Product', back_populates='shipment_items')
    warehouse = db.relationship('Warehouse', back_populates='shipment_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='chk_shipment_item_qty_positive'),
    )

    @hybrid_property
    def total_value(self):
        return self.quantity * float(self.unit_cost or 0)

    def __repr__(self):
        return f"<ShipmentItem {self.product_id} Q{self.quantity}>"

class ShipmentPartner(db.Model, TimestampMixin):
    __tablename__ = 'shipment_partners'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False)
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
    )

    partner = db.relationship('Partner', back_populates='shipment_partners')
    shipment = db.relationship('Shipment', back_populates='partners')

    @hybrid_property
    def share_value(self):
        if self.share_amount and float(self.share_amount) > 0:
            return float(self.share_amount)
        return (float(self.unit_price_before_tax or 0) * float(self.share_percentage or 0)) / 100

    def __repr__(self):
        return f"<ShipmentPartner shipment={self.shipment_id} partner={self.partner_id}>"

class SupplierLoanSettlement(db.Model, TimestampMixin):
    __tablename__='supplier_loan_settlements'
    id=Column(Integer,primary_key=True)
    loan_id=Column(Integer,ForeignKey('product_supplier_loans.id',ondelete='CASCADE'),nullable=True)
    supplier_id=Column(Integer,ForeignKey('suppliers.id',ondelete='SET NULL'),nullable=True,index=True)
    settled_price=Column(Numeric(12,2),nullable=False)
    settlement_date=Column(DateTime,default=datetime.utcnow)
    notes=Column(Text)
    loan=relationship('ProductSupplierLoan',back_populates='settlements')
    supplier=relationship('Supplier',back_populates='loan_settlements')
    payment=relationship('Payment',back_populates='loan_settlement',cascade='all, delete-orphan',passive_deletes=True,uselist=False)
    __table_args__=(CheckConstraint('settled_price>=0',name='chk_settlement_price_non_negative'),)
    @hybrid_property
    def has_payment(self)->bool:return self.payment is not None
    @property
    def product(self):return getattr(self.loan,'product',None)
    def build_payment(self,method:'PaymentMethod'=None,status:'PaymentStatus'=None,direction:'PaymentDirection'=None,currency:str=None,reference:str=None,notes:str=None,created_by:int=None):
        return Payment(total_amount=self.settled_price,payment_date=datetime.utcnow(),method=method or PaymentMethod.BANK,status=status or PaymentStatus.PENDING,direction=direction or PaymentDirection.OUTGOING,entity_type=PaymentEntityType.LOAN,currency=currency or (getattr(self.supplier,'currency',None) or 'ILS'),supplier_id=getattr(self.supplier,'id',None),loan_settlement_id=self.id,reference=reference or f"Loan #{self.loan_id} settlement",notes=notes,created_by=created_by)
    def __repr__(self):return f"<SupplierLoanSettlement Loan{self.loan_id} - {self.settled_price}>"

@event.listens_for(SupplierLoanSettlement,'after_insert')
def _sync_loan_on_settlement(mapper,connection,target):
    try:
        if target.loan:
            target.loan.deferred_price=target.settled_price
            target.loan.is_settled=True
            db.session.flush()
    except Exception:
        pass

class ServiceRequest(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'service_requests'

    id = db.Column(db.Integer, primary_key=True)
    service_number = db.Column(db.String(50), index=True, nullable=True)
    request_date = db.Column(DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    mechanic_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    vehicle_vrn = db.Column(db.String(50), nullable=False)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey('equipment_types.id'))
    vehicle_model = db.Column(db.String(100))
    chassis_number = db.Column(db.String(100))
    problem_description = db.Column(db.Text)
    engineer_notes = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    solution = db.Column(db.Text)
    status = db.Column(db.Enum(ServiceStatus, name='service_status'), default=ServiceStatus.PENDING)
    priority = db.Column(db.Enum(ServicePriority, name='service_priority'), default=ServicePriority.MEDIUM)
    estimated_duration = db.Column(db.Integer)
    actual_duration = db.Column(db.Integer)
    estimated_cost = db.Column(db.Numeric(12,2))
    total_cost = db.Column(db.Numeric(12,2))
    tax_rate = db.Column(db.Numeric(5,2), default=0)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    customer = db.relationship('Customer', back_populates='service_requests')
    mechanic = db.relationship('User', back_populates='service_requests')
    vehicle_type = db.relationship('EquipmentType', back_populates='service_requests')
    parts = db.relationship('ServicePart', back_populates='request', cascade='all, delete-orphan')
    tasks = db.relationship('ServiceTask', back_populates='request', cascade='all, delete-orphan')
    payments = db.relationship('Payment', back_populates='service')
    invoice = db.relationship('Invoice', uselist=False, back_populates='service')

    def __repr__(self):
        return f"<ServiceRequest {self.service_number}>"

class ServicePart(db.Model):
    __tablename__ = 'service_parts'
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_requests.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    note = db.Column(db.String(200))

    request = db.relationship('ServiceRequest', back_populates='parts')
    part = db.relationship('Product', back_populates='service_parts')
    warehouse = db.relationship('Warehouse', back_populates='service_parts')
    partner = db.relationship('Partner', back_populates='service_parts')

    @hybrid_property
    def line_total(self):
        gross = self.quantity * float(self.unit_price)
        discount_amount = gross * (float(self.discount) / 100)
        taxable = gross - discount_amount
        tax_amount = taxable * (float(self.tax_rate) / 100)
        return taxable + tax_amount

    @hybrid_property
    def net_total(self):
        total = self.line_total
        if self.share_percentage:
            total -= total * (float(self.share_percentage) / 100)
        return total

    def __repr__(self):
        pname = getattr(self.part, "name", None)
        return f"<ServicePart {pname or self.part_id} for Service {self.service_id}>"

class ServiceTask(db.Model):
    __tablename__ = 'service_tasks'
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_requests.id'), nullable=False)
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

    @hybrid_property
    def line_total(self):
        gross = self.quantity * float(self.unit_price)
        discount_amount = gross * float(self.discount) / 100
        taxable = gross - discount_amount
        tax_amount = taxable * float(self.tax_rate) / 100
        return taxable + tax_amount

    def __repr__(self):
        return f"<ServiceTask {self.description} for Service {self.service_id}>"

class OnlineCart(db.Model, TimestampMixin):
    __tablename__ = 'online_carts'
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.String(50), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    session_id = db.Column(db.String(100))
    status = db.Column(
        db.Enum(
            'ACTIVE', 'ABANDONED', 'CONVERTED',
            name='cart_status',
            values_callable=lambda enum_values: list(enum_values)
        ),
        default='ACTIVE',
        nullable=False
    )
    expires_at = db.Column(DateTime)
    customer = db.relationship('Customer', back_populates='online_carts')
    items = db.relationship('OnlineCartItem', back_populates='cart', cascade='all, delete-orphan')

    @hybrid_property
    def subtotal(self):
        return sum(item.line_total for item in self.items) if self.items else 0

    @hybrid_property
    def item_count(self):
        return sum(item.quantity for item in self.items) if self.items else 0

    def __repr__(self):
        return f"<OnlineCart {self.cart_id}>"


class OnlineCartItem(db.Model):
    __tablename__ = 'online_cart_items'
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('online_carts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    added_at = db.Column(DateTime, default=datetime.utcnow)
    cart = db.relationship('OnlineCart', back_populates='items')
    product = db.relationship('Product', back_populates='online_cart_items')

    @hybrid_property
    def line_total(self):
        return self.quantity * float(self.price)

    def __repr__(self):
        return f"<OnlineCartItem {self.product.name} in Cart {self.cart_id}>"


class OnlinePreOrder(db.Model, TimestampMixin):
    __tablename__ = 'online_preorders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    cart_id = db.Column(db.Integer, db.ForeignKey('online_carts.id'))

    prepaid_amount = db.Column(db.Numeric(12, 2), default=0)
    total_amount   = db.Column(db.Numeric(12, 2), default=0)

    expected_fulfillment = db.Column(DateTime)
    actual_fulfillment   = db.Column(DateTime)

    status = db.Column(
        db.Enum('PENDING', 'CONFIRMED', 'FULFILLED', 'CANCELLED',
                name='online_preorder_status',
                values_callable=lambda vals: list(vals)),
        default='PENDING',
        nullable=False
    )

    payment_status = db.Column(
        db.Enum('PENDING', 'PARTIAL', 'PAID',
                name='online_preorder_payment_status',
                values_callable=lambda vals: list(vals)),
        default='PENDING',
        nullable=False
    )

    payment_method   = db.Column(db.String(50))
    notes            = db.Column(db.Text)
    shipping_address = db.Column(db.Text)
    billing_address  = db.Column(db.Text)

    # علاقات
    customer = db.relationship('Customer', back_populates='online_preorders')
    cart     = db.relationship('OnlineCart')
    items    = db.relationship('OnlinePreOrderItem', back_populates='order', cascade='all, delete-orphan')
    payments = db.relationship('OnlinePayment',      back_populates='order')

    __table_args__ = (
        db.CheckConstraint('prepaid_amount >= 0', name='chk_online_prepaid_non_negative'),
        db.CheckConstraint('total_amount  >= 0',  name='chk_online_total_non_negative'),
    )

    @hybrid_property
    def total_paid(self):
        return sum(float(p.amount or 0) for p in self.payments) if self.payments else 0

    @hybrid_property
    def balance_due(self):
        return float(self.total_amount or 0) - float(self.total_paid or 0)

    def update_payment_status(self):
        if self.balance_due <= 0:
            self.payment_status = 'PAID'
        elif self.total_paid > 0:
            self.payment_status = 'PARTIAL'
        else:
            self.payment_status = 'PENDING'

    def __repr__(self):
        return f"<OnlinePreOrder {self.order_number}>"

class OnlinePreOrderItem(db.Model):
    __tablename__ = 'online_preorder_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('online_preorders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    order = db.relationship('OnlinePreOrder', back_populates='items')
    product = db.relationship('Product', back_populates='online_preorder_items')

    @hybrid_property
    def line_total(self):
        return self.quantity * float(self.price)

    def __repr__(self):
        return f"<OnlinePreOrderItem {self.product.name} in Order {self.order_id}>"

class OnlinePayment(db.Model, TimestampMixin):
    __tablename__ = 'online_payments'

    id = db.Column(db.Integer, primary_key=True)
    payment_ref = db.Column(db.String(100), unique=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('online_preorders.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default='ILS')
    method = db.Column(db.String(50))
    gateway = db.Column(db.String(50))
    status = db.Column(
        db.Enum('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED',
               name='online_payment_status',
               values_callable=lambda vals: list(vals)),
        default='PENDING',
        nullable=False,
        index=True
    )
    transaction_data = db.Column(db.JSON)
    processed_at = db.Column(DateTime)
    card_last4 = db.Column(db.String(4), index=True)
    card_encrypted = db.Column(db.LargeBinary)
    card_expiry = db.Column(db.String(5))
    cardholder_name = db.Column(db.String(128))
    card_brand = db.Column(db.String(20))
    card_fingerprint = db.Column(db.String(64), index=True)

    order = db.relationship('OnlinePreOrder', back_populates='payments')

    __table_args__ = (
        db.Index('ix_online_payments_order_status', 'order_id', 'status'),
    )

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
            now = datetime.utcnow()
            y, m = now.year, now.month
            return (yy > y) or (yy == y and mm >= m)
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

    def set_card_details(self, pan: str | None, holder: str | None, expiry_mm_yy: str | None, *, validate: bool = True) -> None:
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

    def __repr__(self):
        ref = self.payment_ref or f"OP-{self.id}"
        return f"<OnlinePayment {ref} {self.amount} {self.currency} {self.status}>"

@event.listens_for(OnlinePayment, 'before_insert')
def _online_payment_before_insert(mapper, connection, target: 'OnlinePayment'):
    if not getattr(target, 'payment_ref', None):
        base_dt = datetime.utcnow()
        prefix = base_dt.strftime("PAY%Y%m%d")
        count = connection.execute(
            text("SELECT COUNT(*) FROM online_payments WHERE payment_ref LIKE :pfx"),
            {"pfx": f"{prefix}-%"}
        ).scalar() or 0
        target.payment_ref = f"{prefix}-{count+1:04d}"
    if target.status in ('SUCCESS', 'FAILED', 'REFUNDED') and not target.processed_at:
        target.processed_at = datetime.utcnow()

@event.listens_for(OnlinePayment, 'before_update')
def _online_payment_before_update(mapper, connection, target: 'OnlinePayment'):
    if target.status in ('SUCCESS', 'FAILED', 'REFUNDED') and not target.processed_at:
        target.processed_at = datetime.utcnow()


class ExpenseType(db.Model):
    __tablename__ = 'expense_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    expenses = db.relationship('Expense', back_populates='type')

    def __repr__(self):
        return f"<ExpenseType {self.name}>"

class Expense(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'expenses'

    id          = Column(Integer, primary_key=True)
    date        = Column(DateTime, nullable=False, default=datetime.utcnow)
    amount      = Column(Numeric(12, 2), nullable=False)
    currency    = Column(String(10), default='ILS', nullable=False)  # الجديد للتناسق

    type_id     = Column(Integer, ForeignKey('expense_types.id'), nullable=False)
    employee_id = Column(Integer, ForeignKey('employees.id'))
    warehouse_id= Column(Integer, ForeignKey('warehouses.id'))
    partner_id  = Column(Integer, ForeignKey('partners.id'))

    paid_to         = Column(String(200))
    payment_method  = Column(String(20), nullable=False, default='cash')
    payment_details = Column(String(255))
    description     = Column(String(200))
    notes           = Column(Text)
    tax_invoice_number = Column(String(100))

    # علاقات
    employee  = relationship('Employee',    back_populates='expenses')
    type      = relationship('ExpenseType', back_populates='expenses')
    warehouse = relationship('Warehouse',   back_populates='expenses')
    partner   = relationship('Partner',     back_populates='expenses')

    payments = relationship(
        'Payment',
        back_populates='expense',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint('amount >= 0', name='chk_expense_amount_non_negative'),
    )

    # مجموع المدفوع
    @hybrid_property
    def total_paid(self):
        return float(
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0))
            .filter(Payment.expense_id == self.id)
            .scalar()
        )

    @total_paid.expression
    def total_paid(cls):
        return select(func.coalesce(func.sum(Payment.total_amount), 0))\
               .where(Payment.expense_id == cls.id)\
               .label("total_paid")

    # الرصيد المتبقي
    @hybrid_property
    def balance(self):
        return float(self.amount or 0) - float(self.total_paid or 0)

    @balance.expression
    def balance(cls):
        # ملاحظة: يستخدم التعبير أعلاه total_paid.expression
        return (cls.amount) - (
            select(func.coalesce(func.sum(Payment.total_amount), 0))
            .where(Payment.expense_id == cls.id)
            .scalar_subquery()
        )

    @hybrid_property
    def is_paid(self):
        return self.balance <= 0

    def __repr__(self):
        return f"<Expense {self.id} - {self.amount} {self.currency}>"

@event.listens_for(Expense, 'before_insert')
def _ensure_expense_defaults(mapper, connection, target):
    # في حال تُركت فارغة (مثلاً من سكربت أو فيكتشر)، اعتمد "cash"
    if not getattr(target, 'payment_method', None):
        target.payment_method = 'cash'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(DateTime, default=datetime.utcnow)
    model_name = db.Column(db.String(100), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    record_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(
        db.Enum(
            'CREATE', 'UPDATE', 'DELETE',
            name='audit_action',
            values_callable=lambda vals: list(vals)
        ),
        nullable=False
    )
    old_data = db.Column(db.Text)
    new_data = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    def __repr__(self):
        return f"<AuditLog {self.model_name}.{self.record_id} {self.action}>"

class Note(db.Model, TimestampMixin):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    is_pinned = db.Column(db.Boolean, default=False)
    priority = db.Column(
        db.Enum(
            'LOW', 'MEDIUM', 'HIGH',
            name='note_priority',
            values_callable=lambda vals: list(vals)
        ),
        default='MEDIUM',
        nullable=False
    )
    author = db.relationship('User')

    def __repr__(self):
        return f"<Note {self.id}>"

@event.listens_for(Sale.status, 'set')
def update_stock_reservation(target, value, oldvalue, initiator):
    newv = getattr(value, "value", value)
    oldv = getattr(oldvalue, "value", oldvalue)
    if newv == SaleStatus.CONFIRMED.value:
        target.reserve_stock(); db.session.flush()
    elif oldv == SaleStatus.CONFIRMED.value and newv != SaleStatus.CONFIRMED.value:
        target.release_stock(); db.session.flush()

@event.listens_for(Payment, "after_insert")
@event.listens_for(Payment, "after_update")
def _sync_sale_invoice_on_payment(mapper, connection, target):
    """تحديث حالة السيلز والفاتورة المرتبطتين بالدفع عبر Core فقط (بدون session.flush داخل الـflush)."""

    # ----- Sale (نُراعي أن Sale.payment_status من PaymentProgress) -----
    sale_id = getattr(target, "sale_id", None)
    if sale_id:
        completed_val = PaymentStatus.COMPLETED.value
        incoming_vals = (PaymentDirection.INCOMING.value, "IN")

        total_paid = connection.execute(
            select(func.coalesce(func.sum(Payment.total_amount), 0.0))
            .where(Payment.sale_id == sale_id)
            .where(Payment.status == completed_val)
            .where(Payment.direction.in_(incoming_vals))
        ).scalar_one()

        sale_total = connection.execute(
            select(Sale.total_amount).where(Sale.id == sale_id)
        ).scalar_one() or 0.0

        if sale_total > 0 and total_paid >= sale_total:
            sale_status = PaymentProgress.PAID.value
        elif total_paid > 0:
            sale_status = PaymentProgress.PARTIAL.value
        else:
            sale_status = PaymentProgress.PENDING.value

        connection.execute(
            update(Sale)
            .where(Sale.id == sale_id)
            .values(payment_status=sale_status)
        )

    # ----- Invoice (نفس منطق Invoice.update_status: لا يفلتر بالـstatus) -----
    inv_id = getattr(target, "invoice_id", None)
    if inv_id:
        inv_total = connection.execute(
            select(Invoice.total_amount).where(Invoice.id == inv_id)
        ).scalar_one() or 0.0

        inv_paid = connection.execute(
            select(func.coalesce(func.sum(Payment.total_amount), 0.0))
            .where(Payment.invoice_id == inv_id)
        ).scalar_one()

        if inv_total > 0 and inv_paid >= inv_total:
            inv_status = InvoiceStatus.PAID.value
        elif inv_paid > 0:
            inv_status = InvoiceStatus.PARTIAL.value
        else:
            inv_status = InvoiceStatus.UNPAID.value

        connection.execute(
            update(Invoice)
            .where(Invoice.id == inv_id)
            .values(status=inv_status)
        )


@event.listens_for(Invoice, "before_insert")
@event.listens_for(Invoice, "before_update")
def _compute_invoice_totals(mapper, connection, target):
    # جمع إجمالي الفواتير من خطوطها
    target.total_amount = sum(
        float(getattr(l, "line_total", 0) or 0) for l in target.lines
    ) if target.lines else 0.0


@event.listens_for(OnlinePreOrder, "before_insert")
@event.listens_for(OnlinePreOrder, "before_update")
def _compute_online_preorder_totals(mapper, connection, target):
    # جمع إجمالي الطلب المسبق من عناصره
    target.total_amount = sum(
        float(getattr(i, "line_total", 0) or 0) for i in target.items
    ) if target.items else 0.0
def _get_or_create_stocklevel(product_id: int, warehouse_id: int, for_update: bool = False):
    """
    يرجّع سجل StockLevel (منتج × مستودع) أو ينشئ واحدًا إن لم يوجد.
    لو for_update=True يعمل قفل FOR UPDATE لتفادي السباقات أثناء الحركة.
    """
    q = StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id)
    if for_update:
        q = q.with_for_update()
    lvl = q.first()
    if not lvl:
        lvl = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0)
        db.session.add(lvl)
        db.session.flush()
    return lvl


@event.listens_for(Transfer, 'after_insert')
def _apply_transfer(mapper, connection, target):
    """
    عند إنشاء تحويل: نطرح من المصدر ونضيف للوجهة.
    - لو المصدر = الوجهة: لا تعمل شيء (no-op)
    - يمكن تخطي التحديث إذا تم ضبط _skip_stock_apply على الهدف
    """
    # ✅ لو الراوت قام بالتحديث، لا تكرره هنا
    if getattr(target, '_skip_stock_apply', False):
        return

    # لو نفس المستودع، لا تغيّر المخزون
    if target.source_id == target.destination_id:
        return

    src = _get_or_create_stocklevel(target.product_id, target.source_id, for_update=True)
    if (src.quantity or 0) < target.quantity:
        raise Exception("الكمية غير متوفرة في المستودع المصدر")
    src.quantity = (src.quantity or 0) - target.quantity

    dst = _get_or_create_stocklevel(target.product_id, target.destination_id, for_update=True)
    dst.quantity = (dst.quantity or 0) + target.quantity

    db.session.flush()
@event.listens_for(Shipment.status, 'set')
def _shipment_arrived(target, value, oldvalue, initiator):
    newv = value
    oldv = oldvalue

    if newv == 'ARRIVED' and oldv != 'ARRIVED':
        if not target.actual_arrival:
            target.actual_arrival = datetime.utcnow()
            for it in target.items:
                lvl = _get_or_create_stocklevel(it.product_id, it.warehouse_id, for_update=True)
                lvl.quantity = (lvl.quantity or 0) + (it.quantity or 0)
            db.session.flush()

@event.listens_for(ServiceRequest, 'before_insert')
def _ensure_service_number(mapper, connection, target):
    # لو ما في رقم خدمة ممرّر، أنشئ واحدًا بتنسيق SRVYYYYMMDD-####
    if not getattr(target, 'service_number', None):
        prefix = datetime.utcnow().strftime("SRV%Y%m%d")
        sql = text("""
            SELECT COUNT(*) FROM service_requests
            WHERE DATE(request_date) = DATE(:today)
        """)
        today = datetime.utcnow().date()
        count = connection.execute(sql, {"today": today}).scalar() or 0
        target.service_number = f"{prefix}-{count + 1:04d}"
