import enum
from datetime import datetime

from flask import has_request_context
from flask_login import UserMixin, current_user

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    event,
    func,
    or_,
    text,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, validates

from extensions import db

# ============== تعريفات الأنماط ==============
class PaymentMethod(enum.Enum):
    CASH    = "cash"
    BANK    = "bank"
    CARD    = "card"
    CHEQUE  = "cheque"
    ONLINE  = "online"

class PaymentStatus(enum.Enum):
    PENDING   = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    REFUNDED  = "REFUNDED"

class PaymentDirection(enum.Enum):
    INCOMING = "IN"
    OUTGOING = "OUT"

class InvoiceStatus(enum.Enum):
    UNPAID    = "UNPAID"
    PARTIAL   = "PARTIAL"
    PAID      = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED  = "REFUNDED"

class SaleStatus(enum.Enum):
    DRAFT     = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REFUNDED  = "REFUNDED"

class ServiceStatus(enum.Enum):
    PENDING     = "PENDING"
    DIAGNOSIS   = "DIAGNOSIS"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"
    ON_HOLD     = "ON_HOLD"

class ServicePriority(enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    URGENT = "URGENT"

class TransferDirection(enum.Enum):
    INCOMING   = "IN"
    OUTGOING   = "OUT"
    ADJUSTMENT = "ADJUSTMENT"

class PreOrderStatus(enum.Enum):
    PENDING   = "PENDING"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"

class WarehouseType(enum.Enum):
    MAIN      = "MAIN"
    PARTNER   = "PARTNER"
    INVENTORY = "INVENTORY"
    EXCHANGE  = "EXCHANGE"

class PaymentEntityType(enum.Enum):
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

class InvoiceSource(enum.Enum):
    MANUAL   = "MANUAL"
    SALE     = "SALE"
    SERVICE  = "SERVICE"
    PREORDER = "PREORDER"
    SUPPLIER = "SUPPLIER"
    PARTNER  = "PARTNER"
    ONLINE   = "ONLINE"

class ProductCondition(enum.Enum):
    NEW         = "NEW"
    USED        = "USED"
    REFURBISHED = "REFURBISHED"


# ============== جداول الصلاحيات والأدوار ==============
user_permissions = db.Table(
    'user_permissions',
    db.Column('user_id',       db.Integer, db.ForeignKey('users.id'),       primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True),
    extend_existing=True
)

role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id',       db.Integer, db.ForeignKey('roles.id'),       primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True),
    extend_existing=True
)

# ============== الخلاصات الأساسية ==============
class TimestampMixin:
    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditMixin:
    @classmethod
    def __declare_last__(cls):
        @event.listens_for(cls, 'after_update')
        def recv(mapper, conn, target):
            try:
                uid = None
                if has_request_context() and getattr(current_user, 'is_authenticated', False):
                    uid = current_user.id
                log = AuditLog(
                    model_name=target.__class__.__name__,
                    record_id=target.id,
                    user_id=uid,
                    action='UPDATE',
                    old_data=str(target._previous_state),
                    new_data=str(target.current_state)
                )
                db.session.add(log)
                db.session.flush()
            except Exception:
                db.session.rollback()


# ============== نماذج النظام الأساسي ==============
class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    def __repr__(self):
        return f"<Permission {self.name}>"

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False)
    permissions = db.relationship(
        'Permission', secondary=role_permissions,
        backref=db.backref('roles', lazy='dynamic'),
        lazy='dynamic'
    )
    
    def has_permission(self, perm_name: str) -> bool:
        return self.permissions.filter_by(name=perm_name).first() is not None

    def __repr__(self):
        return f"<Role {self.name}>"

class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(50), unique=True, nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.String(128), nullable=False)
    role_id        = db.Column(db.Integer, db.ForeignKey('roles.id'))
    is_active      = db.Column(db.Boolean, default=True)
    last_login     = db.Column(db.DateTime)

    role             = db.relationship('Role', backref='users')
    extra_permissions = db.relationship(
        'Permission', secondary=user_permissions,
        backref=db.backref('users', lazy='select'),
        lazy='select'
    )
    audit_logs       = db.relationship('AuditLog', backref='user')
    sales            = db.relationship('Sale', back_populates='seller')

    # تم تعديل العلاقة لتستخدم back_populates بدلاً من backref
    service_requests = db.relationship(
        'ServiceRequest',
        back_populates='mechanic',
        lazy='dynamic'
    )

    def set_password(self, password: str):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def has_permission(self, name: str) -> bool:
        if self.email == "rafideen.ahmadghannam@gmail.com":
            return True
        if self.role and self.role.has_permission(name):
            return True
        return self.extra_permissions.filter_by(name=name).first() is not None

    def __repr__(self):
        return f"<User {self.username}>"

# ============== نماذج العملاء والشركاء ==============
# models.py

class Customer(db.Model, UserMixin, TimestampMixin, AuditMixin):
    __tablename__ = 'customers'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    phone          = db.Column(db.String(20), unique=True)
    whatsapp       = db.Column(db.String(20))
    email          = db.Column(db.String(120), unique=True)
    address        = db.Column(db.String(200))
    password_hash  = db.Column(db.String(128))
    category       = db.Column(db.String(20), default="عادي")
    notes          = db.Column(db.Text)
    is_active      = db.Column(db.Boolean, default=True)
    is_online      = db.Column(db.Boolean, default=False)
    credit_limit   = db.Column(db.Numeric(12, 2), default=0)
    discount_rate  = db.Column(db.Numeric(5, 2), default=0)
    balance        = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    sales            = db.relationship('Sale',            back_populates='customer')
    preorders        = db.relationship('PreOrder',         back_populates='customer')
    invoices         = db.relationship('Invoice',          back_populates='customer')
    payments         = db.relationship('Payment',          back_populates='customer')
    service_requests = db.relationship('ServiceRequest',   back_populates='customer')
    online_carts     = db.relationship('OnlineCart',       back_populates='customer')
    online_preorders = db.relationship('OnlinePreOrder',   back_populates='customer')

    @property
    def password(self):
        raise AttributeError("كلمة المرور غير قابلة للقراءة")

    @password.setter
    def password(self, raw_password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(raw_password)

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    @property
    def credit_status(self):
        if self.credit_limit > 0 and self.balance >= self.credit_limit:
            return "معلق"
        return "نشط"

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'phone':         self.phone or '',
            'email':         self.email or '',
            'balance':       float(self.balance),
            'credit_limit':  float(self.credit_limit or 0),
            'category':      self.category,
            'is_active':     self.is_active,
            'created_at':    self.created_at.isoformat() if self.created_at else None,
            'last_activity': getattr(self, 'last_activity', None)
        }

    def __repr__(self):
        return f"<Customer {self.name}>"


# ============== التاجر المحلي أو العالمي ==============
class Supplier(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'suppliers'

    id              = Column(Integer, primary_key=True)
    name            = Column(String(100), nullable=False)
    is_local        = Column(Boolean, default=True)
    identity_number = Column(String(100), unique=True)
    contact         = Column(String(200))
    phone           = Column(String(20), unique=True)
    address         = Column(String(200))
    notes           = Column(Text)
    balance         = Column(Numeric(12, 2), default=0)
    payment_terms   = Column(String(50))

    # علاقات
    payments   = relationship('Payment',  back_populates='supplier')
    invoices   = relationship('Invoice',  back_populates='supplier')
    preorders  = relationship('PreOrder', back_populates='supplier')
    warehouses = relationship('Warehouse', back_populates='supplier')

    @property
    def products(self):
        return Product.query.filter_by(supplier_local_id=self.id).all()

    @hybrid_property
    def net_balance(self):
        paid = db.session.query(
            func.coalesce(func.sum(Payment.total_amount), 0)
        ).filter(
            Payment.supplier_id == self.id,
            Payment.direction   == PaymentDirection.OUTGOING
        ).scalar()
        return float(self.balance) - float(paid or 0)

    @net_balance.expression
    def net_balance(cls):
        paid_subq = select([
            func.coalesce(func.sum(Payment.total_amount), 0)
        ]).where(
            (Payment.supplier_id == cls.id) &
            (Payment.direction   == PaymentDirection.OUTGOING)
        ).scalar_subquery()
        return cls.balance - paid_subq

    def __repr__(self):
        return f"<Supplier {self.name}>"

# ============== نموذج الموظف ==============
class Employee(db.Model, TimestampMixin):
    __tablename__ = 'employees'

    id             = Column(Integer, primary_key=True)
    name           = Column(String(100), nullable=False)
    position       = Column(String(100))
    phone          = Column(String(20))
    bank_name      = Column(String(100))
    account_number = Column(String(100))
    notes          = Column(Text)

    # العلاقة ثنائية الاتجاه مع المصروفات
    expenses = relationship(
        'Expense',
        back_populates='employee',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<Employee {self.name}>"
    
# ============== الشريك ==============
class Partner(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'partners'

    id               = Column(Integer, primary_key=True)
    name             = Column(String(100), nullable=False)
    contact_info     = Column(String(200))
    identity_number  = Column(String(100), unique=True)
    phone_number     = Column(String(20), unique=True)
    address          = Column(String(200))
    balance          = Column(Numeric(12, 2), default=0)
    share_percentage = Column(Numeric(5, 2),  default=0)

    # علاقات
    warehouses        = relationship('Warehouse',             back_populates='partner')
    payments          = relationship('Payment',               back_populates='partner')
    preorders         = relationship('PreOrder',              back_populates='partner')
    shipment_partners = relationship('ShipmentPartner',       back_populates='partner')
    warehouse_shares  = relationship('WarehousePartnerShare', back_populates='partner')
    product_shares    = relationship('ProductPartnerShare',   back_populates='partner')
    product_links     = relationship('ProductPartner',        back_populates='partner')
    service_parts     = relationship('ServicePart',           back_populates='partner')
    service_tasks     = relationship('ServiceTask',           back_populates='partner')
    invoices          = relationship('Invoice',               back_populates='partner',
                                     cascade='all, delete-orphan',
                                     passive_deletes=True)
    expenses          = relationship('Expense',               back_populates='partner',
                                     cascade='all, delete-orphan',
                                     passive_deletes=True)

    @hybrid_property
    def net_balance(self):
        paid = db.session.query(
            func.coalesce(func.sum(Payment.total_amount), 0)
        ).filter(
            Payment.partner_id == self.id,
            Payment.direction  == PaymentDirection.OUTGOING
        ).scalar()
        return float(self.balance) - float(paid or 0)

    @net_balance.expression
    def net_balance(cls):
        paid_subq = select([
            func.coalesce(func.sum(Payment.total_amount), 0)
        ]).where(
            (Payment.partner_id == cls.id) &
            (Payment.direction  == PaymentDirection.OUTGOING)
        ).scalar_subquery()
        return cls.balance - paid_subq

    def __repr__(self):
        return f"<Partner {self.name}>"

# ============== نماذج المخازن والمعدات ==============
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

    id                        = Column(Integer, primary_key=True)
    sku                       = Column(String(50), unique=True)
    name                      = Column(String(255), nullable=False)
    description               = Column(Text)
    part_number               = Column(String(100))
    brand                     = Column(String(100))
    commercial_name           = Column(String(100))
    chassis_number            = Column(String(100))
    serial_no                 = Column(String(100), unique=True)
    barcode                   = Column(String(100), unique=True)
    image                     = Column(String(255))
    cost_before_shipping      = Column(Numeric(12, 2), default=0)
    cost_after_shipping       = Column(Numeric(12, 2), default=0)
    unit_price_before_tax     = Column(Numeric(12, 2), default=0)
    price                     = Column(Numeric(12, 2), nullable=False, default=0.0)
    min_price                 = Column(Numeric(12, 2))
    max_price                 = Column(Numeric(12, 2))
    tax_rate                  = Column(Numeric(5, 2), default=0)
    on_hand                   = Column(Integer, default=0)
    reserved_quantity         = Column(Integer, default=0)
    min_qty                   = Column(Integer, default=0)
    reorder_point             = Column(Integer)
    condition                 = Column(
        Enum(
            ProductCondition,
            name='product_condition',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=ProductCondition.NEW.value,
        nullable=False
    )
    origin_country            = Column(String(50))
    warranty_period           = Column(Integer)
    weight                    = Column(Numeric(10, 2))
    dimensions                = Column(String(50))
    is_active                 = Column(Boolean, default=True)
    is_digital                = Column(Boolean, default=False)
    is_exchange               = Column(Boolean, default=False)
    vehicle_type_id           = Column(Integer, ForeignKey('equipment_types.id'))
    category_id               = Column(Integer, ForeignKey('product_categories.id'))
    supplier_id               = Column(Integer, ForeignKey('suppliers.id'))
    supplier_international_id = Column(Integer, ForeignKey('suppliers.id'))
    supplier_local_id         = Column(Integer, ForeignKey('suppliers.id'))
    warehouse_id              = Column(Integer, ForeignKey('warehouses.id'))

    category                = relationship('ProductCategory', back_populates='products')
    vehicle_type            = relationship('EquipmentType',    back_populates='products')
    supplier_general        = relationship('Supplier', foreign_keys=[supplier_id])
    supplier_international  = relationship('Supplier', foreign_keys=[supplier_international_id])
    supplier_local          = relationship('Supplier', foreign_keys=[supplier_local_id])
    warehouse               = relationship('Warehouse', back_populates='products')
    partners                = relationship('ProductPartner',       back_populates='product')
    partner_shares          = relationship('ProductPartnerShare',  back_populates='product')
    supplier_loans          = relationship('ProductSupplierLoan',  back_populates='product')
    transfers               = relationship('Transfer',             back_populates='product')
    preorders               = relationship('PreOrder',             back_populates='product')
    shipment_items          = relationship('ShipmentItem',         back_populates='product')
    exchange_transactions   = relationship('ExchangeTransaction',  back_populates='product')
    sale_lines              = relationship('SaleLine',             back_populates='product')
    service_parts           = relationship('ServicePart',          back_populates='part')
    online_cart_items       = relationship('OnlineCartItem',       back_populates='product')
    online_preorder_items   = relationship('OnlinePreOrderItem',   back_populates='product')
    stock_levels            = relationship('StockLevel',           back_populates='product')

    @hybrid_property
    def available_quantity(self):
        return (self.on_hand or 0) - (self.reserved_quantity or 0)

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

class Warehouse(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'warehouses'

    id                   = db.Column(db.Integer, primary_key=True)
    name                 = db.Column(db.String(100), nullable=False)
    warehouse_type       = db.Column(
        db.Enum(
            WarehouseType,
            name='warehouse_type',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=WarehouseType.MAIN.value,
        nullable=False
    )
    location             = db.Column(db.String(200))
    is_active            = db.Column(db.Boolean, default=True)
    parent_id            = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    supplier_id          = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    partner_id           = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percent        = db.Column(db.Numeric(5, 2), default=0)
    capacity             = db.Column(db.Integer)
    current_occupancy    = db.Column(db.Integer, default=0)
    notes                = db.Column(db.Text)

    parent               = db.relationship('Warehouse', remote_side=[id], backref='children')
    supplier             = db.relationship('Supplier', back_populates='warehouses')
    partner              = db.relationship('Partner',  back_populates='warehouses')
    products             = db.relationship('Product', back_populates='warehouse', lazy='dynamic')
    stock_levels         = db.relationship('StockLevel',           back_populates='warehouse')
    transfers_source     = db.relationship('Transfer',             back_populates='source_warehouse',      foreign_keys='Transfer.source_id')
    transfers_destination= db.relationship('Transfer',             back_populates='destination_warehouse', foreign_keys='Transfer.destination_id')
    sale_lines           = db.relationship('SaleLine',             back_populates='warehouse')
    service_parts        = db.relationship('ServicePart',          back_populates='warehouse')
    exchange_transactions= db.relationship('ExchangeTransaction',  back_populates='warehouse')
    shipment_items       = db.relationship('ShipmentItem',         back_populates='warehouse')
    shipments_received   = db.relationship('Shipment',             back_populates='destination_warehouse', foreign_keys='Shipment.destination_id')
    preorders            = db.relationship('PreOrder',             back_populates='warehouse')
    partner_shares       = db.relationship('WarehousePartnerShare',back_populates='warehouse')
    expenses             = db.relationship('Expense',              back_populates='warehouse')

    @hybrid_property
    def warehouse_type_display(self):
        mapping = {
            WarehouseType.MAIN.value:      "رئيسي",
            WarehouseType.INVENTORY.value: "مخزن",
            WarehouseType.EXCHANGE.value:  "تبادل",
            WarehouseType.PARTNER.value:   "شريك",
        }
        return mapping.get(self.warehouse_type, self.warehouse_type)

    def __repr__(self):
        return f"<Warehouse {self.name}>"

# -------- Arabic display for warehouse_type --------
    @hybrid_property
    def warehouse_type_display(self):
        mapping = {
            WarehouseType.MAIN.value:      "رئيسي",
            WarehouseType.INVENTORY.value: "مخزن",
            WarehouseType.EXCHANGE.value:  "تبادل",
            WarehouseType.PARTNER.value:   "شريك",
        }
        return mapping.get(self.warehouse_type, self.warehouse_type)

    def __repr__(self):
        return f"<Warehouse {self.name}>"

class StockLevel(db.Model, TimestampMixin):
    __tablename__ = 'stock_levels'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer)
    max_stock = db.Column(db.Integer)
    last_updated = db.Column(DateTime, default=datetime.utcnow)

    product = db.relationship('Product', back_populates='stock_levels')
    warehouse = db.relationship('Warehouse', back_populates='stock_levels')

    @hybrid_property
    def partner_share_quantity(self):
        if self.warehouse.warehouse_type == WarehouseType.PARTNER and self.warehouse.share_percent:
            return self.quantity * float(self.warehouse.share_percent) / 100
        return 0

    @hybrid_property
    def company_share_quantity(self):
        if self.warehouse.warehouse_type == WarehouseType.PARTNER and self.warehouse.share_percent:
            return self.quantity - self.partner_share_quantity
        return self.quantity

    @hybrid_property
    def status(self):
        if self.quantity <= (self.min_stock or 0):
            return "تحت الحد الأدنى"
        elif self.max_stock and self.quantity >= self.max_stock:
            return "فوق الحد الأقصى"
        return "طبيعي"

    def __repr__(self):
        return f"<StockLevel {self.product.name} in {self.warehouse.name}>"

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
    id           = db.Column(db.Integer, primary_key=True)
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    partner_id   = db.Column(db.Integer, db.ForeignKey('partners.id'))
    quantity     = db.Column(db.Integer, nullable=False)
    direction    = db.Column(
        db.Enum('IN', 'OUT', 'ADJUSTMENT', name='exchange_direction'),
        default='IN',
        nullable=False
    )
    notes        = db.Column(db.Text)

    product      = db.relationship('Product', back_populates='exchange_transactions')
    warehouse    = db.relationship('Warehouse', back_populates='exchange_transactions')
    partner      = db.relationship('Partner')

    def __repr__(self):
        return f"<ExchangeTransaction P{self.product_id} W{self.warehouse_id} Q{self.quantity}>"

class WarehousePartnerShare(db.Model, TimestampMixin):
    __tablename__ = 'warehouse_partner_shares'
    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False)
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    share_amount = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    
    warehouse = db.relationship('Warehouse', back_populates='partner_shares')
    partner = db.relationship('Partner', back_populates='warehouse_shares')
    
    __table_args__ = (
        db.CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='chk_wh_partner_share'),
    )
    
    @hybrid_property
    def share_value(self): 
        return float(self.share_amount or 0)
        
    def __repr__(self): 
        return f"<WarehousePartnerShare W{self.warehouse_id}-P{self.partner_id} {self.share_percentage}%>"

class ProductPartnerShare(db.Model, TimestampMixin):
    __tablename__ = 'product_partner_shares'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False)
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    share_amount = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)

    product = db.relationship('Product', back_populates='partner_shares')
    partner = db.relationship('Partner', back_populates='product_shares')

    __table_args__ = (
        db.CheckConstraint('share_percentage >= 0 AND share_percentage <= 100', name='chk_product_partner_share'),
    )

    def __repr__(self):
        return f"<ProductPartnerShare P{self.product_id}-Partner{self.partner_id} {self.share_percentage}%>"

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
        return f"<ProductPartner {self.partner.name} {self.share_percent}%>"

# ============== نماذج المبيعات والطلبات ==============
class PreOrder(db.Model,TimestampMixin):
    __tablename__='preorders'
    id=db.Column(db.Integer,primary_key=True);reference=db.Column(db.String(50),unique=True);preorder_date=db.Column(db.DateTime,default=datetime.utcnow)
    expected_date=db.Column(db.DateTime);customer_id=db.Column(db.Integer,db.ForeignKey('customers.id'))
    supplier_id=db.Column(db.Integer,db.ForeignKey('suppliers.id'));partner_id=db.Column(db.Integer,db.ForeignKey('partners.id'))
    product_id=db.Column(db.Integer,db.ForeignKey('products.id'),nullable=False);warehouse_id=db.Column(db.Integer,db.ForeignKey('warehouses.id'),nullable=False)
    quantity=db.Column(db.Integer,nullable=False);prepaid_amount=db.Column(db.Numeric(12,2),default=0);tax_rate=db.Column(db.Numeric(5,2),default=0)
    status=db.Column(db.Enum(PreOrderStatus,name='preorder_status'),default=PreOrderStatus.PENDING);notes=db.Column(db.Text)
    customer=db.relationship('Customer',back_populates='preorders');supplier=db.relationship('Supplier',back_populates='preorders')
    partner=db.relationship('Partner',back_populates='preorders');product=db.relationship('Product',back_populates='preorders')
    warehouse=db.relationship('Warehouse',back_populates='preorders')
    payments=db.relationship('Payment',back_populates='preorder',cascade='all,delete-orphan')
    sale=db.relationship('Sale',back_populates='preorder',uselist=False);invoice=db.relationship('Invoice',back_populates='preorder',uselist=False)
    __table_args__=(CheckConstraint('quantity>0',name='chk_preorder_quantity_positive'),
                    CheckConstraint('prepaid_amount>=0',name='chk_preorder_prepaid_non_negative'),
                    CheckConstraint('tax_rate>=0 AND tax_rate<=100',name='chk_preorder_tax_rate'))
    @hybrid_property
    def total_before_tax(self):return self.quantity*float(self.product.price or 0)
    @hybrid_property
    def total_with_tax(self):return self.total_before_tax*(1+float(self.tax_rate or 0)/100)
    @hybrid_property
    def total_paid(self):return sum(p.amount for p in self.payments) if self.payments else 0
    @hybrid_property
    def balance_due(self):return float(self.total_with_tax)-float(self.total_paid)
    def __repr__(self):return f"<PreOrder {self.reference}>"


from sqlalchemy import event

class Sale(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'sales'
    id              = db.Column(db.Integer, primary_key=True)
    sale_number     = db.Column(db.String(50), unique=True)
    sale_date       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    customer_id     = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    seller_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    preorder_id     = db.Column(db.Integer, db.ForeignKey('preorders.id'))
    tax_rate        = db.Column(db.Numeric(5, 2), default=0)
    discount_total  = db.Column(db.Numeric(12, 2), default=0)
    notes           = db.Column(db.Text)
    status          = db.Column(
        db.Enum(
            SaleStatus,
            name='sale_status',
            values_callable=lambda e: [v.value for v in e]
        ),
        default=SaleStatus.DRAFT.value,
        nullable=False
    )
    payment_status  = db.Column(
        db.Enum(
            PaymentStatus,
            name='payment_status',
            values_callable=lambda e: [v.value for v in e]
        ),
        default=PaymentStatus.PENDING.value,
        nullable=False
    )
    currency        = db.Column(db.String(10), default='ILS')
    shipping_address= db.Column(db.Text)
    billing_address = db.Column(db.Text)
    shipping_cost   = db.Column(db.Numeric(10, 2), default=0)
    total_amount    = db.Column(db.Numeric(12, 2), default=0)

    customer  = db.relationship('Customer', back_populates='sales')
    seller    = db.relationship('User', back_populates='sales')
    preorder  = db.relationship('PreOrder', back_populates='sale')
    lines     = db.relationship('SaleLine', back_populates='sale', cascade='all,delete-orphan')
    payments  = db.relationship('Payment', back_populates='sale', cascade='all,delete-orphan')
    invoice   = db.relationship('Invoice', back_populates='sale', uselist=False)
    shipments = db.relationship('Shipment', back_populates='sale', cascade='all,delete-orphan')

    @hybrid_property
    def subtotal(self):
        return sum(l.net_amount for l in self.lines) if self.lines else 0

    @hybrid_property
    def tax_amount(self):
        return (self.subtotal - self.discount_total) * float(self.tax_rate or 0) / 100

    @hybrid_property
    def total(self):
        return float(self.subtotal) + float(self.tax_amount) + float(self.shipping_cost or 0) - float(self.discount_total or 0)

    @hybrid_property
    def total_paid(self):
        return sum(p.amount for p in self.payments) if self.payments else 0

    @hybrid_property
    def balance_due(self):
        return self.total - self.total_paid

    def reserve_stock(self):
        for l in self.lines:
            if l.product.available_quantity < l.quantity:
                raise Exception("الكمية غير متوفرة")
            l.product.reserved_quantity += l.quantity
        # apply changes to session without committing here
        db.session.flush()

    def release_stock(self):
        for l in self.lines:
            l.product.reserved_quantity -= l.quantity
        # apply changes to session without committing here
        db.session.flush()

    def update_payment_status(self):
        paid = sum(p.amount for p in self.payments if p.status == PaymentStatus.COMPLETED)
        self.payment_status = (
            PaymentStatus.PAID.value
            if paid >= self.total
            else (PaymentStatus.PARTIAL.value if paid > 0 else PaymentStatus.PENDING.value)
        )

    def __repr__(self):
        return f"<Sale {self.sale_number}>"

@event.listens_for(Sale, "before_insert")
@event.listens_for(Sale, "before_update")
def _compute_total_amount(mapper, connection, target):
    subtotal = sum(l.net_amount for l in target.lines) if target.lines else 0
    tax = (subtotal - target.discount_total) * float(target.tax_rate or 0) / 100
    target.total_amount = subtotal + tax + float(target.shipping_cost or 0) - float(target.discount_total or 0)

    
class SaleLine(db.Model):
    __tablename__ = 'sale_lines'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    discount_rate = db.Column(db.Float, default=0)
    tax_rate = db.Column(db.Float, default=0)
    note = db.Column(db.String(200))

    sale = db.relationship('Sale', back_populates='lines')
    product = db.relationship('Product', back_populates='sale_lines')
    warehouse = db.relationship('Warehouse', back_populates='sale_lines')

    @hybrid_property
    def gross_amount(self):
        return float(self.unit_price) * self.quantity

    @hybrid_property
    def discount_amount(self):
        return self.gross_amount * float(self.discount_rate) / 100

    @hybrid_property
    def net_amount(self):
        return self.gross_amount - self.discount_amount

    @hybrid_property
    def line_tax(self):
        return self.net_amount * float(self.tax_rate) / 100

    @hybrid_property
    def line_total(self):
        return self.net_amount + self.line_tax

    def __repr__(self):
        return f"<SaleLine {self.product.name} in Sale {self.sale_id}>"

class Invoice(db.Model, TimestampMixin):
    __tablename__ = 'invoices'

    id               = Column(Integer, primary_key=True)
    invoice_number   = Column(String(50), unique=True)
    invoice_date     = Column(DateTime, default=datetime.utcnow)
    due_date         = Column(DateTime)
    customer_id      = Column(Integer, ForeignKey('customers.id'), nullable=False)
    supplier_id      = Column(Integer, ForeignKey('suppliers.id'))
    partner_id       = Column(Integer, ForeignKey('partners.id'))
    sale_id          = Column(Integer, ForeignKey('sales.id'))
    service_id       = Column(Integer, ForeignKey('service_requests.id'))
    preorder_id      = Column(Integer, ForeignKey('preorders.id'))
    source           = Column(
        db.Enum(InvoiceSource, name='invoice_source'),
        default=InvoiceSource.MANUAL.value,
        nullable=False
    )
    status           = Column(
        db.Enum(InvoiceStatus, name='invoice_status'),
        default=InvoiceStatus.UNPAID.value,
        nullable=False
    )
    total_amount     = Column(Numeric(12,2), nullable=False)
    tax_amount       = Column(Numeric(12,2), default=0)
    discount_amount  = Column(Numeric(12,2), default=0)
    notes            = Column(Text)
    terms            = Column(Text)

    customer = relationship('Customer',      back_populates='invoices')
    supplier = relationship('Supplier',      back_populates='invoices')
    partner  = relationship('Partner',       back_populates='invoices')
    sale     = relationship('Sale',          back_populates='invoice', uselist=False)
    service  = relationship('ServiceRequest', back_populates='invoice')
    preorder = relationship('PreOrder',      back_populates='invoice')
    lines    = relationship('InvoiceLine',   back_populates='invoice', cascade='all, delete-orphan')
    payments = relationship('Payment',       back_populates='invoice', cascade='all, delete-orphan', passive_deletes=True)

    @hybrid_property
    def computed_total(self):
        return sum(l.line_total for l in self.lines) if self.lines else 0

    @hybrid_property
    def total_paid(self):
        return sum(p.amount for p in self.payments) if self.payments else 0

    @hybrid_property
    def balance_due(self):
        return float(self.total_amount) - float(self.total_paid)

    def update_status(self):
        self.status = (
            InvoiceStatus.PAID.value if self.balance_due <= 0
            else (InvoiceStatus.PARTIAL.value if self.total_paid > 0 else InvoiceStatus.UNPAID.value)
        )

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"
    
class InvoiceLine(db.Model):
    __tablename__ = 'invoice_lines'
    id          = db.Column(db.Integer, primary_key=True)
    invoice_id  = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity    = db.Column(db.Float, nullable=False)
    unit_price  = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate    = db.Column(db.Numeric(5, 2), default=0)
    discount    = db.Column(db.Numeric(5, 2), default=0)
    product_id  = db.Column(db.Integer, db.ForeignKey('products.id'))

    invoice = db.relationship('Invoice', back_populates='lines')
    product = db.relationship('Product')

    @hybrid_property
    def line_total(self):
        gross = self.quantity * float(self.unit_price)
        discount_amount = gross * (float(self.discount) / 100)
        taxable = gross - discount_amount
        tax_amount = taxable * (float(self.tax_rate) / 100)
        return taxable + tax_amount

    def __repr__(self): 
        return f"<InvoiceLine {self.description}>"

class Payment(db.Model):
    __tablename__ = 'payments'
    id                  = db.Column(db.Integer, primary_key=True)
    payment_number      = db.Column(db.String(50), unique=True)
    payment_date        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    subtotal            = db.Column(db.Numeric(10,2))
    tax_rate            = db.Column(db.Numeric(5,2))
    tax_amount          = db.Column(db.Numeric(10,2))
    total_amount        = db.Column(db.Numeric(10,2), nullable=False)
    currency            = db.Column(db.String(10), default='ILS', nullable=False)
    method              = db.Column(
        db.Enum(
            PaymentMethod,
            name='payment_method',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        nullable=False
    )
    status              = db.Column(
        db.Enum(
            PaymentStatus,
            name='payment_status',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=PaymentStatus.PENDING.value,
        nullable=False
    )
    direction           = db.Column(
        db.Enum(
            PaymentDirection,
            name='payment_direction',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=PaymentDirection.OUTGOING.value,
        nullable=False
    )
    entity_type         = db.Column(
        db.Enum(
            PaymentEntityType,
            name='payment_entity_type',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        default=PaymentEntityType.CUSTOMER.value,
        nullable=False
    )
    reference           = db.Column(db.String(100))
    receipt_number      = db.Column(db.String(50), unique=True)
    notes               = db.Column(db.Text)
    check_number        = db.Column(db.String(100))
    check_bank          = db.Column(db.String(100))
    check_due_date      = db.Column(db.DateTime)
    card_number         = db.Column(db.String(100))
    card_holder         = db.Column(db.String(100))
    card_expiry         = db.Column(db.String(10))
    card_cvv            = db.Column(db.String(4))
    bank_transfer_ref   = db.Column(db.String(100))
    customer_id         = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'))
    supplier_id         = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='CASCADE'))
    partner_id          = db.Column(db.Integer, db.ForeignKey('partners.id', ondelete='CASCADE'))
    shipment_id         = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'))
    expense_id          = db.Column(db.Integer, db.ForeignKey('expenses.id', ondelete='CASCADE'))
    loan_settlement_id  = db.Column(db.Integer, db.ForeignKey('supplier_loan_settlements.id', ondelete='CASCADE'))
    sale_id             = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='CASCADE'))
    invoice_id          = db.Column(db.Integer, db.ForeignKey('invoices.id', ondelete='CASCADE'))
    preorder_id         = db.Column(db.Integer, db.ForeignKey('preorders.id', ondelete='CASCADE'))
    service_id          = db.Column(db.Integer, db.ForeignKey('service_requests.id', ondelete='CASCADE'))
    splits              = db.relationship('PaymentSplit', cascade='all,delete-orphan', passive_deletes=True)
    customer            = db.relationship('Customer', back_populates='payments')
    supplier            = db.relationship('Supplier', back_populates='payments')
    partner             = db.relationship('Partner', back_populates='payments')
    shipment            = db.relationship('Shipment', back_populates='payments')
    expense             = db.relationship('Expense', back_populates='payment')
    loan_settlement     = db.relationship('SupplierLoanSettlement', back_populates='payment')
    sale                = db.relationship('Sale', back_populates='payments')
    invoice             = db.relationship('Invoice', back_populates='payments')
    preorder            = db.relationship('PreOrder', back_populates='payments')
    service             = db.relationship('ServiceRequest', back_populates='payments')

    @property
    def entity(self):
        for attr in ('customer','supplier','partner','shipment','expense','loan_settlement','sale','invoice','preorder','service'):
            if getattr(self, f"{attr}_id", None):
                return getattr(self, attr)
        return None

    def to_dict(self):
        return {
            'id':               self.id,
            'payment_number':   self.payment_number,
            'subtotal':         float(self.subtotal or 0),
            'tax_rate':         float(self.tax_rate or 0),
            'tax_amount':       float(self.tax_amount or 0),
            'total_amount':     float(self.total_amount),
            'currency':         self.currency,
            'method':           self.method.value if self.method else None,
            'status':           self.status.value if self.status else None,
            'direction':        self.direction.value if self.direction else None,
            'entity_type':      self.entity_type.value if self.entity_type else None,
            'entity':           getattr(self.entity, 'name', None),
            'reference':        self.reference,
            'receipt_number':   self.receipt_number,
            'notes':            self.notes
        }

    def __repr__(self):
        return f"<Payment {self.payment_number or self.id} - {self.total_amount} {self.currency}>"


class PaymentSplit(db.Model):
    __tablename__ = 'payment_splits'
    id         = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='CASCADE'), nullable=False)
    method     = db.Column(
        db.Enum(
            PaymentMethod,
            name='split_payment_method',
            values_callable=lambda enum_cls: [e.value for e in enum_cls]
        ),
        nullable=False
    )
    amount     = db.Column(db.Numeric(12, 2), nullable=False)
    details    = db.Column(db.JSON)

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='chk_split_amount_positive'),
    )

    def __repr__(self):
        return f"<PaymentSplit {self.method.value} {self.amount}>"


# ============== نماذج الشحنات والتسويات ==============
class Shipment(db.Model, TimestampMixin):
    __tablename__ = 'shipments'
    id                  = db.Column(db.Integer, primary_key=True)
    shipment_number     = db.Column(db.String(50), unique=True)
    shipment_date       = db.Column(db.DateTime, default=datetime.utcnow)
    expected_arrival    = db.Column(db.DateTime)
    actual_arrival      = db.Column(db.DateTime)
    origin              = db.Column(db.String(100))
    destination         = db.Column(db.String(100))
    destination_id      = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    status              = db.Column(db.String(20), default='PENDING')
    value_before        = db.Column(db.Numeric(12, 2))
    shipping_cost       = db.Column(db.Numeric(12, 2))
    customs             = db.Column(db.Numeric(12, 2))
    vat                 = db.Column(db.Numeric(12, 2))
    insurance           = db.Column(db.Numeric(12, 2))
    carrier             = db.Column(db.String(100))
    tracking_number     = db.Column(db.String(100))
    notes               = db.Column(db.Text)
    currency            = db.Column(db.String(10), default='USD')
    sale_id             = db.Column(db.Integer, db.ForeignKey('sales.id'))

    items               = db.relationship('ShipmentItem', back_populates='shipment', cascade='all, delete-orphan')
    partners            = db.relationship('ShipmentPartner', back_populates='shipment', cascade='all, delete-orphan')
    payments            = db.relationship('Payment', back_populates='shipment')
    sale                = db.relationship('Sale', back_populates='shipments')
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
    __tablename__ = 'supplier_loan_settlements'

    id              = Column(Integer, primary_key=True)
    loan_id         = Column(Integer, ForeignKey('product_supplier_loans.id'), nullable=False)
    settled_price   = Column(Numeric(12, 2), nullable=False)
    settlement_date = Column(DateTime, default=datetime.utcnow)
    notes           = Column(Text)

    # العلاقات الصحيحة ضمن هذا الكلاس
    loan    = relationship('ProductSupplierLoan', back_populates='settlements')
    payment = relationship(
        'Payment', back_populates='loan_settlement',
        cascade='all,delete-orphan', passive_deletes=True
    )

    def __repr__(self):
        return f"<SupplierLoanSettlement Loan{self.loan_id} - {self.settled_price}>"
    
# =================== ServiceRequest ===================
class ServiceRequest(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'service_requests'

    id                 = db.Column(db.Integer, primary_key=True)
    service_number     = db.Column(db.String(50), unique=True)
    request_date       = db.Column(DateTime, default=datetime.utcnow)
    customer_id        = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    mechanic_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # اختياري
    vehicle_vrn        = db.Column(db.String(50), nullable=False)
    vehicle_type_id    = db.Column(db.Integer, db.ForeignKey('equipment_types.id'))
    vehicle_model      = db.Column(db.String(100))
    chassis_number     = db.Column(db.String(100))
    problem_description= db.Column(db.Text)
    engineer_notes     = db.Column(db.Text)
    diagnosis          = db.Column(db.Text)
    solution           = db.Column(db.Text)
    status             = db.Column(db.Enum(ServiceStatus,   name='service_status'),
                                   default=ServiceStatus.PENDING)
    priority           = db.Column(db.Enum(ServicePriority, name='service_priority'),
                                   default=ServicePriority.MEDIUM)
    estimated_duration = db.Column(db.Integer)
    actual_duration    = db.Column(db.Integer)
    estimated_cost     = db.Column(db.Numeric(12,2))
    total_cost         = db.Column(db.Numeric(12,2))
    tax_rate           = db.Column(db.Numeric(5,2), default=0)
    start_time         = db.Column(db.DateTime)
    end_time           = db.Column(db.DateTime)

    # ✅ حقول بيانات العميل (المضافة)
    name               = db.Column(db.String(100))
    phone              = db.Column(db.String(20))
    email              = db.Column(db.String(100))

    # العلاقات
    customer     = db.relationship('Customer',     back_populates='service_requests')
    mechanic     = db.relationship('User',         back_populates='service_requests')
    vehicle_type = db.relationship('EquipmentType', back_populates='service_requests')
    parts        = db.relationship('ServicePart',   back_populates='request', cascade='all, delete-orphan')
    tasks        = db.relationship('ServiceTask',   back_populates='request', cascade='all, delete-orphan')
    payments     = db.relationship('Payment',       back_populates='service')
    invoice      = db.relationship('Invoice',       uselist=False, back_populates='service')

    def __repr__(self):
        return f"<ServiceRequest {self.service_number}>"

class ServicePart(db.Model):
    __tablename__ = 'service_parts'
    id           = db.Column(db.Integer, primary_key=True)
    service_id   = db.Column(db.Integer, db.ForeignKey('service_requests.id'), nullable=False)
    part_id      = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    partner_id   = db.Column(db.Integer, db.ForeignKey('partners.id'))
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    quantity     = db.Column(db.Integer, nullable=False)
    unit_price   = db.Column(db.Numeric(10, 2), nullable=False)
    discount     = db.Column(db.Numeric(5, 2), default=0)
    tax_rate     = db.Column(db.Numeric(5, 2), default=0)
    note         = db.Column(db.String(200))

    # ربط ثنائي الاتجاه مع ServiceRequest
    request   = db.relationship('ServiceRequest', back_populates='parts')
    part      = db.relationship('Product', back_populates='service_parts')
    warehouse = db.relationship('Warehouse', back_populates='service_parts')
    partner   = db.relationship('Partner', back_populates='service_parts')

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
        return f"<ServicePart {self.part.name} for Service {self.service_id}>"

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

# ============== نماذج التجارة الإلكترونية ==============
class OnlineCart(db.Model, TimestampMixin):
    __tablename__ = 'online_carts'
    id          = db.Column(db.Integer, primary_key=True)
    cart_id     = db.Column(db.String(50), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    session_id  = db.Column(db.String(100))
    status      = db.Column(
        db.Enum(
            'ACTIVE', 'ABANDONED', 'CONVERTED',
            name='cart_status',
            values_callable=lambda enum_values: list(enum_values)
        ),
        default='ACTIVE',
        nullable=False
    )
    expires_at  = db.Column(DateTime)

    customer = db.relationship('Customer', back_populates='online_carts')
    items    = db.relationship('OnlineCartItem', back_populates='cart', cascade='all, delete-orphan')

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
    id                   = db.Column(db.Integer, primary_key=True)
    order_number         = db.Column(db.String(50), unique=True)
    customer_id          = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    cart_id              = db.Column(db.Integer, db.ForeignKey('online_carts.id'))
    prepaid_amount       = db.Column(db.Numeric(12, 2), default=0)
    total_amount         = db.Column(db.Numeric(12, 2), default=0)
    expected_fulfillment = db.Column(DateTime)
    actual_fulfillment   = db.Column(DateTime)
    status               = db.Column(
        db.Enum(
            'PENDING', 'CONFIRMED', 'FULFILLED', 'CANCELLED',
            name='online_preorder_status',
            values_callable=lambda vals: list(vals)
        ),
        default='PENDING',
        nullable=False
    )
    payment_status       = db.Column(
        db.Enum(
            'PENDING', 'PARTIAL', 'PAID',
            name='online_payment_status',
            values_callable=lambda vals: list(vals)
        ),
        default='PENDING',
        nullable=False
    )
    payment_method       = db.Column(db.String(50))
    notes                = db.Column(db.Text)
    shipping_address     = db.Column(db.Text)
    billing_address      = db.Column(db.Text)

    customer = db.relationship('Customer', back_populates='online_preorders')
    cart     = db.relationship('OnlineCart')
    items    = db.relationship('OnlinePreOrderItem', back_populates='order', cascade='all, delete-orphan')
    payments = db.relationship('OnlinePayment', back_populates='order')

    @hybrid_property
    def total_paid(self):
        return sum(payment.amount for payment in self.payments) if self.payments else 0

    @hybrid_property
    def balance_due(self):
        return float(self.total_amount) - float(self.total_paid)

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
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('online_preorders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity   = db.Column(db.Integer, default=1)
    price      = db.Column(db.Numeric(12, 2), nullable=False)

    order   = db.relationship('OnlinePreOrder', back_populates='items')
    product = db.relationship('Product', back_populates='online_preorder_items')

    @hybrid_property
    def line_total(self):
        return self.quantity * float(self.price)

    def __repr__(self):
        return f"<OnlinePreOrderItem {self.product.name} in Order {self.order_id}>"

class OnlinePayment(db.Model, TimestampMixin):
    __tablename__      = 'online_payments'
    id                  = db.Column(db.Integer, primary_key=True)
    payment_ref         = db.Column(db.String(100), unique=True)
    order_id            = db.Column(db.Integer, db.ForeignKey('online_preorders.id'), nullable=False)
    amount              = db.Column(db.Numeric(12, 2), nullable=False)
    currency            = db.Column(db.String(10), default='ILS')
    method              = db.Column(db.String(50))
    gateway             = db.Column(db.String(50))
    status              = db.Column(
        db.Enum(
            'PENDING', 'SUCCESS', 'FAILED', 'REFUNDED',
            name='online_payment_status',
            values_callable=lambda vals: list(vals)
        ),
        default='PENDING',
        nullable=False
    )
    transaction_data    = db.Column(db.JSON)
    processed_at        = db.Column(DateTime)

    order = db.relationship('OnlinePreOrder', back_populates='payments')

    def __repr__(self):
        return f"<OnlinePayment {self.payment_ref}>"

class ExpenseType(db.Model):
    __tablename__ = 'expense_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))

    expenses = db.relationship('Expense', back_populates='type')

    def __repr__(self): 
        return f"<ExpenseType {self.name}>"

# ============== نموذج المصروف ==============
class Expense(db.Model, TimestampMixin, AuditMixin):
    __tablename__ = 'expenses'

    id                  = Column(Integer, primary_key=True)
    date                = Column(DateTime, nullable=False)
    amount              = Column(Numeric(12, 2), nullable=False)
    type_id             = Column(Integer, ForeignKey('expense_types.id'), nullable=False)
    employee_id         = Column(Integer, ForeignKey('employees.id'))
    paid_to             = Column(String(200))
    payment_method      = Column(String(20), nullable=False)
    payment_details     = Column(String(255))
    description         = Column(String(200))
    notes               = Column(Text)
    tax_invoice_number  = Column(String(100))
    warehouse_id        = Column(Integer, ForeignKey('warehouses.id'))
    partner_id          = Column(Integer, ForeignKey('partners.id'))

    # العلاقات ثنائية الاتجاه
    employee  = relationship('Employee',  back_populates='expenses')
    type      = relationship('ExpenseType', back_populates='expenses')
    warehouse = relationship('Warehouse',   back_populates='expenses')
    partner   = relationship('Partner',     back_populates='expenses')
    payment   = relationship(
        'Payment',
        back_populates='expense',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return f"<Expense {self.id} - {self.amount}>"
# ============== نماذج التدقيق والسجلات ==============
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id          = db.Column(db.Integer, primary_key=True)
    timestamp   = db.Column(DateTime, default=datetime.utcnow)
    model_name  = db.Column(db.String(100), nullable=False)
    customer_id  = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    record_id   = db.Column(db.Integer, nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    action      = db.Column(
        db.Enum(
            'CREATE', 'UPDATE', 'DELETE',
            name='audit_action',
            values_callable=lambda vals: list(vals)
        ),
        nullable=False
    )
    old_data    = db.Column(db.Text)
    new_data    = db.Column(db.Text)
    ip_address  = db.Column(db.String(50))
    user_agent  = db.Column(db.String(255))

    def __repr__(self):
        return f"<AuditLog {self.model_name}.{self.record_id} {self.action}>"


class Note(db.Model, TimestampMixin):
    __tablename__  = 'notes'
    id             = db.Column(db.Integer, primary_key=True)
    content        = db.Column(db.Text, nullable=False)
    author_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    entity_type    = db.Column(db.String(50))
    entity_id      = db.Column(db.Integer)
    is_pinned      = db.Column(db.Boolean, default=False)
    priority       = db.Column(
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


# ============== مستمعات الأحداث ==============
@event.listens_for(Sale.status, 'set')
def update_stock_reservation(target, value, oldvalue, initiator):
    if value == SaleStatus.CONFIRMED:
        target.reserve_stock()
        db.session.flush()
    elif oldvalue == SaleStatus.CONFIRMED and value != SaleStatus.CONFIRMED:
        target.release_stock()
        db.session.flush()
        
@event.listens_for(Payment, 'after_insert')
@event.listens_for(Payment, 'after_update')
def update_sale_payment_status(mapper, connection, target):
    if target.sale_id:
        sale = Sale.query.get(target.sale_id)
        if sale:
            sale.update_payment_status()
            db.session.flush()

