"""
⚡ AI Action Executor - محرك تنفيذ العمليات
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تنفيذ العمليات التي يطلبها المستخدم في المحادثة
- إضافة عميل، فاتورة، منتج، دفعة، إلخ
- التفاعل مع قاعدة البيانات مباشرة
- التحقق من الصلاحيات
- تسجيل العمليات (Audit)

Created: 2025-11-01
Version: 1.0
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from decimal import Decimal
from extensions import db
from models import AuditLog


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 ACTION EXECUTOR - محرك التنفيذ الرئيسي
# ═══════════════════════════════════════════════════════════════════════════

class ActionExecutor:
    """
    محرك تنفيذ العمليات الذكي
    
    يستطيع تنفيذ أي عملية في النظام بناءً على طلب المستخدم
    """
    
    def __init__(self, user_id: int = None):
        """
        Args:
            user_id: معرف المستخدم الذي يطلب العملية
        """
        self.user_id = user_id
        self.last_action = None
        self.errors = []
    
    def execute_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        تنفيذ عملية
        
        Args:
            action_type: نوع العملية (add_customer, create_invoice, etc.)
            params: معاملات العملية
        
        Returns:
            {
                'success': True/False,
                'message': 'رسالة النتيجة',
                'data': البيانات المُنشأة,
                'id': معرف السجل الجديد
            }
        """
        try:
            # تحديد العملية المطلوبة
            action_map = {
                'add_customer': self.add_customer,
                'add_supplier': self.add_supplier,
                'add_product': self.add_product,
                'create_sale': self.create_sale,
                'create_invoice': self.create_invoice,
                'create_payment': self.create_payment,
                'create_expense': self.create_expense,
                'create_service': self.create_service,
                'add_warehouse': self.add_warehouse,
                'transfer_stock': self.transfer_stock,
                'adjust_stock': self.adjust_stock
            }
            
            action_func = action_map.get(action_type)
            
            if not action_func:
                return {
                    'success': False,
                    'message': f'❌ العملية "{action_type}" غير معروفة',
                    'available_actions': list(action_map.keys())
                }
            
            # تنفيذ العملية
            result = action_func(params)
            
            # تسجيل في Audit Log
            if result['success']:
                self._log_action(action_type, params, result)
            
            self.last_action = {
                'type': action_type,
                'params': params,
                'result': result,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'message': f'❌ خطأ في التنفيذ: {str(e)}',
                'error': str(e)
            }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 👥 CUSTOMER ACTIONS - عمليات العملاء
    # ═══════════════════════════════════════════════════════════════════════
    
    def add_customer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إضافة عميل جديد
        
        Required params:
            - name: اسم العميل (required)
            - phone: رقم الهاتف (required)
        
        Optional params:
            - email: البريد الإلكتروني
            - address: العنوان
            - city: المدينة
            - tax_id: الرقم الضريبي
            - opening_balance: الرصيد الافتتاحي
            - notes: ملاحظات
        """
        try:
            from models import Customer
            
            # التحقق من البيانات المطلوبة
            if not params.get('name'):
                return {'success': False, 'message': '❌ الاسم مطلوب'}
            
            if not params.get('phone'):
                return {'success': False, 'message': '❌ رقم الهاتف مطلوب'}
            
            # التحقق من عدم التكرار
            existing = Customer.query.filter_by(phone=params['phone']).first()
            if existing:
                return {
                    'success': False,
                    'message': f'❌ العميل موجود مسبقاً (ID: {existing.id})',
                    'existing_customer': {
                        'id': existing.id,
                        'name': existing.name,
                        'phone': existing.phone
                    }
                }
            
            # إنشاء العميل
            customer = Customer(
                name=params['name'].strip(),
                phone=params['phone'].strip(),
                email=params.get('email', '').strip() if params.get('email') else None,
                address=params.get('address', '').strip() if params.get('address') else None,
                city=params.get('city', '').strip() if params.get('city') else None,
                tax_id=params.get('tax_id', '').strip() if params.get('tax_id') else None,
                opening_balance=Decimal(str(params.get('opening_balance', 0))),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                is_active=True,
                created_by_id=self.user_id
            )
            
            db.session.add(customer)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إضافة العميل "{customer.name}" بنجاح',
                'customer_id': customer.id,
                'data': {
                    'id': customer.id,
                    'name': customer.name,
                    'phone': customer.phone,
                    'email': customer.email,
                    'address': customer.address,
                    'opening_balance': float(customer.opening_balance)
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': f'❌ فشل إضافة العميل: {str(e)}',
                'error': str(e)
            }
    
    def add_supplier(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إضافة مورد جديد
        
        Required params:
            - name: اسم المورد
            - phone: رقم الهاتف
        
        Optional params:
            - email, address, city, tax_id, opening_balance, notes
        """
        try:
            from models import Supplier
            
            if not params.get('name'):
                return {'success': False, 'message': '❌ الاسم مطلوب'}
            
            if not params.get('phone'):
                return {'success': False, 'message': '❌ رقم الهاتف مطلوب'}
            
            # التحقق من التكرار
            existing = Supplier.query.filter_by(phone=params['phone']).first()
            if existing:
                return {
                    'success': False,
                    'message': f'❌ المورد موجود مسبقاً (ID: {existing.id})'
                }
            
            supplier = Supplier(
                name=params['name'].strip(),
                phone=params['phone'].strip(),
                email=params.get('email', '').strip() if params.get('email') else None,
                address=params.get('address', '').strip() if params.get('address') else None,
                city=params.get('city', '').strip() if params.get('city') else None,
                tax_id=params.get('tax_id', '').strip() if params.get('tax_id') else None,
                opening_balance=Decimal(str(params.get('opening_balance', 0))),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                is_active=True,
                created_by_id=self.user_id
            )
            
            db.session.add(supplier)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إضافة المورد "{supplier.name}" بنجاح',
                'supplier_id': supplier.id,
                'data': {
                    'id': supplier.id,
                    'name': supplier.name,
                    'phone': supplier.phone
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📦 PRODUCT ACTIONS - عمليات المنتجات
    # ═══════════════════════════════════════════════════════════════════════
    
    def add_product(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إضافة منتج جديد
        
        Required params:
            - name: اسم المنتج
            - sku: رمز المنتج
            - price: السعر
        
        Optional params:
            - barcode: الباركود
            - cost: التكلفة
            - category: الفئة
            - description: الوصف
            - min_stock: الحد الأدنى للمخزون
            - max_stock: الحد الأقصى
        """
        try:
            from models import Product
            
            if not params.get('name'):
                return {'success': False, 'message': '❌ اسم المنتج مطلوب'}
            
            if not params.get('sku'):
                return {'success': False, 'message': '❌ رمز المنتج (SKU) مطلوب'}
            
            if not params.get('price'):
                return {'success': False, 'message': '❌ السعر مطلوب'}
            
            # التحقق من التكرار
            existing_sku = Product.query.filter_by(sku=params['sku']).first()
            if existing_sku:
                return {
                    'success': False,
                    'message': f'❌ رمز المنتج موجود مسبقاً (ID: {existing_sku.id})'
                }
            
            product = Product(
                name=params['name'].strip(),
                sku=params['sku'].strip(),
                barcode=params.get('barcode', '').strip() if params.get('barcode') else None,
                price=Decimal(str(params['price'])),
                cost=Decimal(str(params.get('cost', 0))),
                category=params.get('category', '').strip() if params.get('category') else None,
                description=params.get('description', '').strip() if params.get('description') else None,
                min_stock=int(params.get('min_stock', 0)),
                max_stock=int(params.get('max_stock', 0)),
                is_active=True,
                created_by_id=self.user_id
            )
            
            db.session.add(product)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إضافة المنتج "{product.name}" بنجاح',
                'product_id': product.id,
                'data': {
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'price': float(product.price)
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 💰 PAYMENT ACTIONS - عمليات الدفعات
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_payment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إنشاء دفعة
        
        Required params:
            - amount: المبلغ
            - direction: الاتجاه (IN/OUT)
            - payment_method: طريقة الدفع (CASH/BANK/CARD/CHECK)
        
        Optional params:
            - customer_id: معرف العميل
            - supplier_id: معرف المورد
            - partner_id: معرف الشريك
            - notes: ملاحظات
            - reference: المرجع
        """
        try:
            from models import Payment
            
            if not params.get('amount'):
                return {'success': False, 'message': '❌ المبلغ مطلوب'}
            
            if not params.get('direction'):
                return {'success': False, 'message': '❌ الاتجاه مطلوب (IN أو OUT)'}
            
            if params['direction'] not in ['IN', 'OUT']:
                return {'success': False, 'message': '❌ الاتجاه يجب أن يكون IN أو OUT'}
            
            if not params.get('payment_method'):
                return {'success': False, 'message': '❌ طريقة الدفع مطلوبة'}
            
            # التحقق من وجود كيان واحد على الأقل
            if not any([params.get('customer_id'), params.get('supplier_id'), params.get('partner_id')]):
                return {'success': False, 'message': '❌ يجب تحديد عميل أو مورد أو شريك'}
            
            payment = Payment(
                total_amount=Decimal(str(params['amount'])),
                direction=params['direction'],
                method=params['payment_method'],
                customer_id=params.get('customer_id'),
                supplier_id=params.get('supplier_id'),
                partner_id=params.get('partner_id'),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                reference=params.get('reference', '').strip() if params.get('reference') else None,
                payment_date=datetime.now(timezone.utc),
                status='COMPLETED',
                created_by=self.user_id,
                entity_type='CUSTOMER' if params.get('customer_id') else 'SUPPLIER' if params.get('supplier_id') else 'PARTNER'
            )
            
            db.session.add(payment)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم تسجيل الدفعة بمبلغ {float(payment.amount)} ₪',
                'payment_id': payment.id,
                'data': {
                    'id': payment.id,
                    'amount': float(payment.amount),
                    'direction': payment.direction,
                    'method': payment.payment_method
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🧾 INVOICE & SALE ACTIONS - عمليات الفواتير والمبيعات
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_sale(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إنشاء عملية بيع
        
        Required params:
            - customer_id: معرف العميل
            - warehouse_id: معرف المستودع
            - items: قائمة المنتجات [{'product_id': 1, 'quantity': 2, 'price': 100}]
        
        Optional params:
            - discount: الخصم
            - notes: ملاحظات
            - vat_enabled: تفعيل الضريبة (True/False)
        """
        try:
            from models import Sale, SaleLine, Product, StockLevel
            
            if not params.get('customer_id'):
                return {'success': False, 'message': '❌ معرف العميل مطلوب'}
            
            if not params.get('warehouse_id'):
                return {'success': False, 'message': '❌ معرف المستودع مطلوب'}
            
            if not params.get('items') or len(params['items']) == 0:
                return {'success': False, 'message': '❌ يجب إضافة منتج واحد على الأقل'}
            
            # حساب الإجمالي
            subtotal = Decimal('0')
            lines_data = []
            
            for item in params['items']:
                if not all(k in item for k in ['product_id', 'quantity', 'price']):
                    return {'success': False, 'message': '❌ بيانات المنتج غير كاملة'}
                
                quantity = Decimal(str(item['quantity']))
                price = Decimal(str(item['price']))
                discount = Decimal(str(item.get('discount', 0)))
                
                line_total = (quantity * price) - discount
                subtotal += line_total
                
                lines_data.append({
                    'product_id': item['product_id'],
                    'quantity': quantity,
                    'price': price,
                    'discount': discount,
                    'total': line_total
                })
            
            # الخصم العام
            general_discount = Decimal(str(params.get('discount', 0)))
            subtotal_after_discount = subtotal - general_discount
            
            # الضريبة
            vat_rate = Decimal('0.16')  # 16%
            vat_amount = Decimal('0')
            
            if params.get('vat_enabled', True):
                vat_amount = subtotal_after_discount * vat_rate
            
            total = subtotal_after_discount + vat_amount
            
            # إنشاء البيع
            sale = Sale(
                customer_id=params['customer_id'],
                warehouse_id=params['warehouse_id'],
                sale_date=datetime.now(timezone.utc),
                subtotal=subtotal,
                discount=general_discount,
                vat_amount=vat_amount,
                sale_total=total,
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                status='CONFIRMED',
                created_by_id=self.user_id
            )
            
            db.session.add(sale)
            db.session.flush()  # للحصول على sale.id
            
            # إضافة السطور
            for line_data in lines_data:
                sale_line = SaleLine(
                    sale_id=sale.id,
                    product_id=line_data['product_id'],
                    quantity=line_data['quantity'],
                    price=line_data['price'],
                    discount=line_data['discount'],
                    total=line_data['total']
                )
                db.session.add(sale_line)
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إنشاء عملية البيع بمبلغ {float(total)} ₪',
                'sale_id': sale.id,
                'data': {
                    'id': sale.id,
                    'customer_id': sale.customer_id,
                    'subtotal': float(subtotal),
                    'discount': float(general_discount),
                    'vat': float(vat_amount),
                    'total': float(total),
                    'items_count': len(lines_data)
                }
            }
            
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def create_invoice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إنشاء فاتورة
        
        Required params:
            - customer_id أو supplier_id
            - invoice_type: 'CUSTOMER' أو 'SUPPLIER'
            - items: قائمة المنتجات
            - total: الإجمالي
        """
        try:
            from models import Invoice
            
            if not params.get('invoice_type'):
                return {'success': False, 'message': '❌ نوع الفاتورة مطلوب'}
            
            if not params.get('total'):
                return {'success': False, 'message': '❌ الإجمالي مطلوب'}
            
            invoice = Invoice(
                invoice_type=params['invoice_type'],
                customer_id=params.get('customer_id'),
                supplier_id=params.get('supplier_id'),
                total_amount=Decimal(str(params['total'])),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                created_by_id=self.user_id
            )
            
            db.session.add(invoice)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إنشاء الفاتورة بمبلغ {float(invoice.total_amount)} ₪',
                'invoice_id': invoice.id
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def create_expense(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إنشاء مصروف
        
        Required params:
            - amount: المبلغ
            - description: الوصف
        
        Optional params:
            - expense_type: نوع المصروف
            - payment_method: طريقة الدفع
        """
        try:
            from models import Expense
            
            if not params.get('amount'):
                return {'success': False, 'message': '❌ المبلغ مطلوب'}
            
            if not params.get('description'):
                return {'success': False, 'message': '❌ الوصف مطلوب'}
            
            expense = Expense(
                amount=Decimal(str(params['amount'])),
                description=params['description'].strip(),
                expense_type=params.get('expense_type', 'OTHER'),
                payment_method=params.get('payment_method', 'CASH'),
                date=datetime.now(timezone.utc),
                created_by_id=self.user_id
            )
            
            db.session.add(expense)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم تسجيل المصروف بمبلغ {float(expense.amount)} ₪',
                'expense_id': expense.id
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def create_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إنشاء طلب صيانة
        
        Required params:
            - customer_id: معرف العميل
            - issue_description: وصف العطل
        
        Optional params:
            - vehicle_model: موديل السيارة
            - vehicle_plate: رقم اللوحة
        """
        try:
            from models import ServiceRequest
            
            if not params.get('customer_id'):
                return {'success': False, 'message': '❌ معرف العميل مطلوب'}
            
            if not params.get('issue_description'):
                return {'success': False, 'message': '❌ وصف العطل مطلوب'}
            
            service = ServiceRequest(
                customer_id=params['customer_id'],
                issue_description=params['issue_description'].strip(),
                vehicle_model=params.get('vehicle_model', '').strip() if params.get('vehicle_model') else None,
                vehicle_plate=params.get('vehicle_plate', '').strip() if params.get('vehicle_plate') else None,
                status='pending',
                created_by_id=self.user_id
            )
            
            db.session.add(service)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إنشاء طلب الصيانة رقم {service.id}',
                'service_id': service.id
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def add_warehouse(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        إضافة مستودع
        
        Required params:
            - name: اسم المستودع
            - warehouse_type: MAIN/ONLINE/PARTNER/INVENTORY/EXCHANGE
        """
        try:
            from models import Warehouse
            
            if not params.get('name'):
                return {'success': False, 'message': '❌ اسم المستودع مطلوب'}
            
            if not params.get('warehouse_type'):
                return {'success': False, 'message': '❌ نوع المستودع مطلوب'}
            
            warehouse = Warehouse(
                name=params['name'].strip(),
                warehouse_type=params['warehouse_type'],
                partner_id=params.get('partner_id'),
                supplier_id=params.get('supplier_id'),
                is_active=True,
                created_by_id=self.user_id
            )
            
            db.session.add(warehouse)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إضافة المستودع "{warehouse.name}"',
                'warehouse_id': warehouse.id
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def transfer_stock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحويل مخزون بين مستودعات
        
        Required params:
            - product_id: معرف المنتج
            - from_warehouse_id: من مستودع
            - to_warehouse_id: إلى مستودع
            - quantity: الكمية
        """
        try:
            from models import StockTransfer
            
            if not all(k in params for k in ['product_id', 'from_warehouse_id', 'to_warehouse_id', 'quantity']):
                return {'success': False, 'message': '❌ بيانات ناقصة'}
            
            transfer = StockTransfer(
                product_id=params['product_id'],
                from_warehouse_id=params['from_warehouse_id'],
                to_warehouse_id=params['to_warehouse_id'],
                quantity=int(params['quantity']),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                status='PENDING',
                created_by_id=self.user_id
            )
            
            db.session.add(transfer)
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم إنشاء طلب التحويل',
                'transfer_id': transfer.id
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    def adjust_stock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        تعديل مخزون (جرد)
        
        Required params:
            - product_id: معرف المنتج
            - warehouse_id: معرف المستودع
            - new_quantity: الكمية الجديدة
            - reason: السبب
        """
        try:
            from models import StockLevel, StockAdjustment
            
            if not all(k in params for k in ['product_id', 'warehouse_id', 'new_quantity', 'reason']):
                return {'success': False, 'message': '❌ بيانات ناقصة'}
            
            # الحصول على المخزون الحالي
            stock = StockLevel.query.filter_by(
                product_id=params['product_id'],
                warehouse_id=params['warehouse_id']
            ).first()
            
            old_quantity = stock.quantity if stock else 0
            new_quantity = int(params['new_quantity'])
            difference = new_quantity - old_quantity
            
            # إنشاء سجل التعديل
            adjustment = StockAdjustment(
                product_id=params['product_id'],
                warehouse_id=params['warehouse_id'],
                old_quantity=old_quantity,
                new_quantity=new_quantity,
                difference=difference,
                reason=params['reason'].strip(),
                notes=params.get('notes', '').strip() if params.get('notes') else None,
                created_by_id=self.user_id
            )
            
            db.session.add(adjustment)
            
            # تحديث المخزون
            if stock:
                stock.quantity = new_quantity
            else:
                stock = StockLevel(
                    product_id=params['product_id'],
                    warehouse_id=params['warehouse_id'],
                    quantity=new_quantity
                )
                db.session.add(stock)
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'✅ تم تعديل المخزون من {old_quantity} إلى {new_quantity}',
                'adjustment_id': adjustment.id,
                'difference': difference
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': f'❌ خطأ: {str(e)}'}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📝 AUDIT & LOGGING - التسجيل والمراجعة
    # ═══════════════════════════════════════════════════════════════════════
    
    def _log_action(self, action_type: str, params: Dict, result: Dict):
        """تسجيل العملية في Audit Log"""
        try:
            log = AuditLog(
                user_id=self.user_id,
                action=f'ai_action_{action_type}',
                entity_type=action_type.replace('add_', '').replace('create_', ''),
                entity_id=result.get('customer_id') or result.get('product_id') or result.get('sale_id'),
                details=f"AI executed: {action_type}",
                ip_address='AI_SYSTEM',
                user_agent='AI Assistant v5.0'
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            pass  # لا نريد أن يفشل التنفيذ بسبب الـ logging


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 HELPER FUNCTIONS - دوال مساعدة
# ═══════════════════════════════════════════════════════════════════════════

def parse_user_request(message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    تحليل طلب المستخدم واستخراج العملية والمعاملات
    
    Args:
        message: رسالة المستخدم
    
    Returns:
        (action_type, params) أو None
    
    Examples:
        "أضف عميل اسمه أحمد هاتفه 0599123456"
        → ('add_customer', {'name': 'أحمد', 'phone': '0599123456'})
    """
    message_lower = message.lower()
    
    # استخدام Regex لاستخراج المعلومات من النص الطبيعي
    
    if any(word in message_lower for word in ['أضف عميل', 'إضافة عميل', 'add customer']):
        # محاولة استخراج الاسم والهاتف
        params = {}
        
        # استخراج الاسم
        import re
        name_match = re.search(r'اسمه?\s+([^\s]+)', message)
        if name_match:
            params['name'] = name_match.group(1)
        
        # استخراج الهاتف
        phone_match = re.search(r'(?:هاتفه?|موبايل|phone)\s+([\d\-]+)', message)
        if phone_match:
            params['phone'] = phone_match.group(1)
        
        if params:
            return ('add_customer', params)
    
    return None


__all__ = [
    'ActionExecutor',
    'parse_user_request'
]

