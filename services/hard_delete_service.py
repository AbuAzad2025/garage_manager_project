"""
خدمة الحذف القوي مع العمليات العكسية والاستعادة
"""
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any

from flask import current_app
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import (
    Customer, Supplier, Partner, Payment, 
    StockLevel, Product, Warehouse, DeletionLog, DeletionType, DeletionStatus,
    User, GLBatch
)
from utils import format_currency


class HardDeleteService:
    """خدمة الحذف القوي مع العمليات العكسية"""
    
    def __init__(self):
        self.deletion_log = None
        self.rollback_data = {}
    
    def generate_confirmation_code(self) -> str:
        """توليد كود تأكيد فريد"""
        return f"DEL_{uuid.uuid4().hex[:8].upper()}"
    
    def create_deletion_log(self, deletion_type: str, entity_id: int, entity_name: str, 
                          deleted_by: int, reason: str = None) -> DeletionLog:
        """إنشاء سجل حذف جديد"""
        confirmation_code = self.generate_confirmation_code()
        
        self.deletion_log = DeletionLog(
            deletion_type=deletion_type,
            entity_id=entity_id,
            entity_name=entity_name,
            deleted_by=deleted_by,
            deletion_reason=reason,
            confirmation_code=confirmation_code,
            status=DeletionStatus.PENDING.value
        )
        
        db.session.add(self.deletion_log)
        db.session.flush()
        return self.deletion_log
    
    def delete_customer(self, customer_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للعميل مع العمليات العكسية"""
        try:
            # 1. جلب العميل
            customer = db.session.get(Customer, customer_id)
            if not customer:
                return {"success": False, "error": "العميل غير موجود"}
            
            customer_name = customer.name
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.CUSTOMER.value, 
                customer_id, 
                customer_name, 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة (بسيط)
            try:
                related_data = self._collect_customer_related_data(customer_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل جمع البيانات المرتبطة: {str(e)}")
                related_data = {"customer_data": {}, "related_entities": {}}
            
            # 4. تنفيذ العمليات العكسية (بسيط)
            try:
                reversals = self._reverse_customer_operations(customer_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل العمليات العكسية: {str(e)}")
                reversals = {"stock_reversals": [], "accounting_reversals": [], "balance_reversals": []}
            
            # 5. حذف البيانات
            self._delete_customer_data(customer_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data.get("customer_data"),
                related_entities=related_data.get("related_entities"),
                stock_reversals=reversals.get("stock_reversals"),
                accounting_reversals=reversals.get("accounting_reversals"),
                balance_reversals=reversals.get("balance_reversals")
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف العميل {customer_name} بنجاح",
                "deletion_id": deletion_log.id
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ خطأ في حذف العميل: {str(e)}")
            import traceback
            traceback.print_exc()
            if self.deletion_log:
                try:
                    self.deletion_log.mark_failed(str(e))
                    db.session.commit()
                except:
                    pass
            return {"success": False, "error": f"فشل في حذف العميل: {str(e)}"}
    
    def delete_sale(self, sale_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للبيع مع العمليات العكسية"""
        try:
            # 1. جلب البيع
            from models import Sale
            sale = db.session.get(Sale, sale_id)
            if not sale:
                return {"success": False, "error": "البيع غير موجود"}
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.SALE.value, 
                sale_id, 
                f"بيع #{sale.sale_number or sale.id}", 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة
            related_data = self._collect_sale_related_data(sale_id)
            
            # 4. تنفيذ العمليات العكسية
            reversals = self._reverse_sale_operations(sale_id)
            
            # 5. حذف البيانات
            self._delete_sale_data(sale_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data["sale_data"],
                related_entities=related_data["related_entities"],
                stock_reversals=reversals["stock_reversals"],
                accounting_reversals=reversals["accounting_reversals"],
                balance_reversals=reversals["balance_reversals"]
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف البيع {sale.sale_number or sale.id} بنجاح",
                "deletion_id": deletion_log.id,
                "confirmation_code": deletion_log.confirmation_code
            }
            
        except Exception as e:
            db.session.rollback()
            if self.deletion_log:
                self.deletion_log.mark_failed(str(e))
                db.session.commit()
            return {"success": False, "error": f"فشل في حذف البيع: {str(e)}"}
    
    def delete_payment(self, payment_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للدفعة مع العمليات العكسية"""
        try:
            # 1. جلب الدفعة
            payment = db.session.get(Payment, payment_id)
            if not payment:
                return {"success": False, "error": "الدفعة غير موجودة"}
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.PAYMENT.value, 
                payment_id, 
                f"دفعة #{payment.id}", 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة
            related_data = self._collect_payment_related_data(payment_id)
            
            # 4. تنفيذ العمليات العكسية
            reversals = self._reverse_payment_operations(payment_id)
            
            # 5. حذف البيانات
            self._delete_payment_data(payment_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data["payment_data"],
                related_entities=related_data["related_entities"],
                stock_reversals=reversals["stock_reversals"],
                accounting_reversals=reversals["accounting_reversals"],
                balance_reversals=reversals["balance_reversals"]
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف الدفعة #{payment.id} بنجاح",
                "deletion_id": deletion_log.id,
                "confirmation_code": deletion_log.confirmation_code
            }
            
        except Exception as e:
            db.session.rollback()
            if self.deletion_log:
                self.deletion_log.mark_failed(str(e))
                db.session.commit()
            return {"success": False, "error": f"فشل في حذف الدفعة: {str(e)}"}
    
    def delete_supplier(self, supplier_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للمورد مع العمليات العكسية"""
        try:
            # 1. جلب المورد
            supplier = db.session.get(Supplier, supplier_id)
            if not supplier:
                return {"success": False, "error": "المورد غير موجود"}
            
            supplier_name = supplier.name
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.SUPPLIER.value, 
                supplier_id, 
                supplier_name, 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة (بسيط)
            try:
                related_data = self._collect_supplier_related_data(supplier_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل جمع البيانات المرتبطة للمورد: {str(e)}")
                related_data = {"supplier_data": {}, "related_entities": {}}
            
            # 4. تنفيذ العمليات العكسية (بسيط)
            try:
                reversals = self._reverse_supplier_operations(supplier_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل العمليات العكسية للمورد: {str(e)}")
                reversals = {"stock_reversals": [], "accounting_reversals": [], "balance_reversals": []}
            
            # 5. حذف البيانات
            self._delete_supplier_data(supplier_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data.get("supplier_data"),
                related_entities=related_data.get("related_entities"),
                stock_reversals=reversals.get("stock_reversals"),
                accounting_reversals=reversals.get("accounting_reversals"),
                balance_reversals=reversals.get("balance_reversals")
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف المورد {supplier_name} بنجاح",
                "deletion_id": deletion_log.id
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ خطأ في حذف المورد: {str(e)}")
            import traceback
            traceback.print_exc()
            if self.deletion_log:
                try:
                    self.deletion_log.mark_failed(str(e))
                    db.session.commit()
                except:
                    pass
            return {"success": False, "error": f"فشل في حذف المورد: {str(e)}"}
    
    def delete_partner(self, partner_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للشريك مع العمليات العكسية"""
        try:
            # 1. جلب الشريك
            partner = db.session.get(Partner, partner_id)
            if not partner:
                return {"success": False, "error": "الشريك غير موجود"}
            
            partner_name = partner.name
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.PARTNER.value, 
                partner_id, 
                partner_name, 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة (بسيط)
            try:
                related_data = self._collect_partner_related_data(partner_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل جمع البيانات المرتبطة للشريك: {str(e)}")
                related_data = {"partner_data": {}, "related_entities": {}}
            
            # 4. تنفيذ العمليات العكسية (بسيط)
            try:
                reversals = self._reverse_partner_operations(partner_id)
            except Exception as e:
                print(f"⚠️ تحذير: فشل العمليات العكسية للشريك: {str(e)}")
                reversals = {"stock_reversals": [], "accounting_reversals": [], "balance_reversals": []}
            
            # 5. حذف البيانات
            self._delete_partner_data(partner_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data.get("partner_data"),
                related_entities=related_data.get("related_entities"),
                stock_reversals=reversals.get("stock_reversals"),
                accounting_reversals=reversals.get("accounting_reversals"),
                balance_reversals=reversals.get("balance_reversals")
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف الشريك {partner_name} بنجاح",
                "deletion_id": deletion_log.id
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ خطأ في حذف الشريك: {str(e)}")
            import traceback
            traceback.print_exc()
            if self.deletion_log:
                try:
                    self.deletion_log.mark_failed(str(e))
                    db.session.commit()
                except:
                    pass
            return {"success": False, "error": f"فشل في حذف الشريك: {str(e)}"}
    
    def _collect_customer_related_data(self, customer_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالعميل"""
        customer = db.session.get(Customer, customer_id)
        if not customer:
            return {}
        
        # بيانات العميل
        customer_data = {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "address": customer.address,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "updated_at": customer.updated_at.isoformat() if customer.updated_at else None
        }
        
        # المبيعات المرتبطة (إذا كانت موجودة)
        sales_data = []
        # TODO: إضافة نماذج المبيعات عند توفرها
        
        # الدفعات المرتبطة
        payments = db.session.query(Payment).filter_by(customer_id=customer_id).all()
        payments_data = []
        for payment in payments:
            payments_data.append({
                "id": payment.id,
                "total_amount": float(payment.total_amount or 0),
                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                "method": payment.method,
                "status": payment.status
            })
        
        return {
            "customer_data": customer_data,
            "related_entities": {
                "sales": sales_data,
                "payments": payments_data
            }
        }
    
    def _collect_sale_related_data(self, sale_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالبيع"""
        from models import Sale
        sale = db.session.get(Sale, sale_id)
        if not sale:
            return {}
        
        # بيانات البيع
        sale_data = {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "customer_id": sale.customer_id,
            "total_amount": float(sale.total_amount or 0),
            "sale_date": sale.sale_date.isoformat() if sale.sale_date else None,
            "status": sale.status,
            "currency": sale.currency
        }
        
        return {
            "sale_data": sale_data,
            "related_entities": []
        }
    
    def _collect_payment_related_data(self, payment_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالدفعة"""
        payment = db.session.get(Payment, payment_id)
        if not payment:
            return {}
        
        # بيانات الدفعة
        payment_data = {
            "id": payment.id,
            "payment_number": payment.payment_number,
            "entity_type": payment.entity_type,
            "customer_id": payment.customer_id,
            "supplier_id": payment.supplier_id,
            "partner_id": payment.partner_id,
            "expense_id": payment.expense_id,
            "sale_id": payment.sale_id,
            "total_amount": float(payment.total_amount or 0),
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "method": payment.method,
            "status": payment.status,
            "direction": payment.direction
        }
        
        return {
            "payment_data": payment_data,
            "related_entities": {}
        }
    
    def _reverse_customer_operations(self, customer_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للعميل"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. إرجاع المخزون من المبيعات (إذا كانت موجودة)
        # TODO: إضافة منطق إرجاع المخزون من المبيعات عند توفر نماذج المبيعات
        
        # 2. حذف السجلات المحاسبية
        payments = db.session.query(Payment).filter_by(customer_id=customer_id).all()
        if payments:
            gl_batches = db.session.query(GLBatch).filter(
                and_(GLBatch.source_type == "PAYMENT", GLBatch.source_id.in_([p.id for p in payments]))
            ).all()
        else:
            gl_batches = []
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _reverse_sale_operations(self, sale_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للبيع"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. إرجاع المخزون (إذا كانت موجودة)
        # TODO: إضافة منطق إرجاع المخزون من المبيعات عند توفر نماذج المبيعات
        
        # 2. حذف السجلات المحاسبية
        gl_batches = db.session.query(GLBatch).filter_by(
            source_type="SALE", 
            source_id=sale_id
        ).all()
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _reverse_payment_operations(self, payment_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للدفعة"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. حذف السجلات المحاسبية
        gl_batches = db.session.query(GLBatch).filter_by(
            source_type="PAYMENT", 
            source_id=payment_id
        ).all()
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _delete_customer_data(self, customer_id: int):
        """حذف بيانات العميل"""
        from models import Sale, SaleLine, SaleReturn, SaleReturnLine, ServiceRequest, Expense
        
        # 1. جلب جميع المبيعات المرتبطة بالعميل
        sales = db.session.query(Sale).filter_by(customer_id=customer_id).all()
        
        for sale in sales:
            # حذف بنود البيع
            db.session.query(SaleLine).filter_by(sale_id=sale.id).delete()
            
            # حذف بنود المرتجعات
            sale_returns = db.session.query(SaleReturn).filter_by(sale_id=sale.id).all()
            for sale_return in sale_returns:
                db.session.query(SaleReturnLine).filter_by(sale_return_id=sale_return.id).delete()
                db.session.delete(sale_return)
            
            # حذف البيع
            db.session.delete(sale)
        
        # 2. حذف الدفعات المرتبطة بالعميل
        db.session.query(Payment).filter_by(customer_id=customer_id).delete()
        
        # 3. حذف المرتجعات المباشرة (بدون بيع)
        sale_returns_direct = db.session.query(SaleReturn).filter_by(customer_id=customer_id, sale_id=None).all()
        for sale_return in sale_returns_direct:
            db.session.query(SaleReturnLine).filter_by(sale_return_id=sale_return.id).delete()
            db.session.delete(sale_return)
        
        # 4. حذف طلبات الصيانة المرتبطة بالعميل
        service_requests = db.session.query(ServiceRequest).filter_by(customer_id=customer_id).all()
        for service in service_requests:
            # حذف المهام والقطع المرتبطة بالصيانة
            try:
                from models import ServiceTask, ServicePart
                db.session.query(ServiceTask).filter_by(service_id=service.id).delete()
                db.session.query(ServicePart).filter_by(service_id=service.id).delete()
            except:
                pass
            db.session.delete(service)
        
        # 5. حذف النفقات المرتبطة بالعميل
        db.session.query(Expense).filter_by(
            payee_type='CUSTOMER',
            payee_entity_id=customer_id
        ).delete()
        
        # 6. حذف الحجوزات (إذا كانت موجودة)
        try:
            from models import Preorder
            db.session.query(Preorder).filter_by(customer_id=customer_id).delete()
        except:
            pass
        
        # 7. حذف العميل
        db.session.query(Customer).filter_by(id=customer_id).delete()
    
    def _delete_sale_data(self, sale_id: int):
        """حذف بيانات البيع"""
        from models import Sale, SaleLine, SaleReturn, SaleReturnLine
        
        # 1. حذف بنود البيع
        db.session.query(SaleLine).filter_by(sale_id=sale_id).delete()
        
        # 2. حذف مرتجعات البيع
        sale_returns = db.session.query(SaleReturn).filter_by(sale_id=sale_id).all()
        for sale_return in sale_returns:
            db.session.query(SaleReturnLine).filter_by(sale_return_id=sale_return.id).delete()
            db.session.delete(sale_return)
        
        # 3. حذف الدفعات المرتبطة بالبيع
        db.session.query(Payment).filter_by(sale_id=sale_id).delete()
        
        # 4. حذف البيع
        db.session.query(Sale).filter_by(id=sale_id).delete()
    
    def _delete_payment_data(self, payment_id: int):
        """حذف بيانات الدفعة"""
        db.session.query(Payment).filter_by(id=payment_id).delete()
    
    def _collect_expense_related_data(self, expense_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالنفقة"""
        from models import Expense
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return {}
        
        # بيانات النفقة
        expense_data = {
            "id": expense.id,
            "description": expense.description,
            "amount": float(expense.amount or 0),
            "date": expense.date.isoformat() if expense.date else None,
            "currency": expense.currency,
            "type_id": expense.type_id,
            "payee_type": expense.payee_type,
            "payee_entity_id": expense.payee_entity_id,
            "payee_name": expense.payee_name,
            "beneficiary_name": expense.beneficiary_name,
            "payment_method": expense.payment_method,
            "notes": expense.notes
        }
        
        # الدفعات المرتبطة
        payments = db.session.query(Payment).filter_by(expense_id=expense_id).all()
        payments_data = []
        for payment in payments:
            payments_data.append({
                "id": payment.id,
                "total_amount": float(payment.total_amount or 0),
                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                "method": payment.method,
                "status": payment.status
            })
        
        return {
            "expense_data": expense_data,
            "related_entities": {
                "payments": payments_data
            }
        }
    
    def _reverse_expense_operations(self, expense_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للنفقة"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. حذف السجلات المحاسبية
        payments = db.session.query(Payment).filter_by(expense_id=expense_id).all()
        if payments:
            gl_batches = db.session.query(GLBatch).filter(
                and_(GLBatch.source_type == "PAYMENT", GLBatch.source_id.in_([p.id for p in payments]))
            ).all()
        else:
            gl_batches = []
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _delete_expense_data(self, expense_id: int):
        """حذف بيانات النفقة"""
        # حذف الدفعات
        db.session.query(Payment).filter_by(expense_id=expense_id).delete()
        
        # حذف النفقة
        from models import Expense
        db.session.query(Expense).filter_by(id=expense_id).delete()
    
    def _collect_supplier_related_data(self, supplier_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالمورد"""
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return {}
        
        # بيانات المورد
        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "phone": supplier.phone,
            "email": supplier.email,
            "address": supplier.address,
            "created_at": supplier.created_at.isoformat() if supplier.created_at else None,
            "updated_at": supplier.updated_at.isoformat() if supplier.updated_at else None
        }
        
        # المشتريات المرتبطة (إذا كانت موجودة)
        purchases_data = []
        # TODO: إضافة نماذج المشتريات عند توفرها
        
        # الدفعات المرتبطة
        payments = db.session.query(Payment).filter_by(supplier_id=supplier_id).all()
        payments_data = []
        for payment in payments:
            payments_data.append({
                "id": payment.id,
                "total_amount": float(payment.total_amount or 0),
                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                "method": payment.method,
                "status": payment.status
            })
        
        return {
            "supplier_data": supplier_data,
            "related_entities": {
                "purchases": purchases_data,
                "payments": payments_data
            }
        }
    
    def _collect_partner_related_data(self, partner_id: int) -> Dict[str, Any]:
        """جمع البيانات المرتبطة بالشريك"""
        partner = db.session.get(Partner, partner_id)
        if not partner:
            return {}
        
        # بيانات الشريك
        partner_data = {
            "id": partner.id,
            "name": partner.name,
            "phone": partner.phone,
            "email": partner.email,
            "address": partner.address,
            "created_at": partner.created_at.isoformat() if partner.created_at else None,
            "updated_at": partner.updated_at.isoformat() if partner.updated_at else None
        }
        
        # المبيعات المرتبطة (إذا كانت موجودة)
        sales_data = []
        # TODO: إضافة نماذج المبيعات عند توفرها
        
        # الدفعات المرتبطة
        payments = db.session.query(Payment).filter_by(partner_id=partner_id).all()
        payments_data = []
        for payment in payments:
            payments_data.append({
                "id": payment.id,
                "total_amount": float(payment.total_amount or 0),
                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                "method": payment.method,
                "status": payment.status
            })
        
        return {
            "partner_data": partner_data,
            "related_entities": {
                "sales": sales_data,
                "payments": payments_data
            }
        }
    
    def _reverse_supplier_operations(self, supplier_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للمورد"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. إرجاع المخزون من المشتريات (إذا كانت موجودة)
        # TODO: إضافة منطق إرجاع المخزون من المشتريات عند توفر نماذج المشتريات
        
        # 2. حذف السجلات المحاسبية
        gl_batches = db.session.query(GLBatch).filter(
            GLBatch.source_type == "PAYMENT",
            GLBatch.source_id.in_([p.id for p in db.session.query(Payment).filter_by(supplier_id=supplier_id).all()])
        ).all()
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _reverse_partner_operations(self, partner_id: int) -> Dict[str, Any]:
        """تنفيذ العمليات العكسية للشريك"""
        reversals = {
            "stock_reversals": [],
            "accounting_reversals": [],
            "balance_reversals": []
        }
        
        # 1. إرجاع المخزون من المبيعات (إذا كانت موجودة)
        # TODO: إضافة منطق إرجاع المخزون من المبيعات عند توفر نماذج المبيعات
        
        # 2. حذف السجلات المحاسبية
        payments = db.session.query(Payment).filter_by(partner_id=partner_id).all()
        if payments:
            gl_batches = db.session.query(GLBatch).filter(
                and_(GLBatch.source_type == "PAYMENT", GLBatch.source_id.in_([p.id for p in payments]))
            ).all()
        else:
            gl_batches = []
        
        for batch in gl_batches:
            reversals["accounting_reversals"].append({
                "batch_id": batch.id,
                "source_type": batch.source_type,
                "source_id": batch.source_id
            })
            db.session.delete(batch)
        
        return reversals
    
    def _delete_supplier_data(self, supplier_id: int):
        """حذف بيانات المورد"""
        from models import Expense
        
        # 1. حذف النفقات المرتبطة بالمورد
        db.session.query(Expense).filter_by(
            payee_type='SUPPLIER',
            payee_entity_id=supplier_id
        ).delete()
        
        # 2. حذف الدفعات المرتبطة بالمورد
        db.session.query(Payment).filter_by(supplier_id=supplier_id).delete()
        
        # 3. حذف المورد
        db.session.query(Supplier).filter_by(id=supplier_id).delete()
    
    def _delete_partner_data(self, partner_id: int):
        """حذف بيانات الشريك"""
        from models import Expense
        
        # 1. حذف النفقات المرتبطة بالشريك
        db.session.query(Expense).filter_by(
            payee_type='PARTNER',
            payee_entity_id=partner_id
        ).delete()
        
        # 2. حذف الدفعات المرتبطة بالشريك
        db.session.query(Payment).filter_by(partner_id=partner_id).delete()
        
        # 3. حذف الشريك
        db.session.query(Partner).filter_by(id=partner_id).delete()
    
    def delete_expense(self, expense_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للنفقة مع العمليات العكسية"""
        try:
            # 1. جلب النفقة
            from models import Expense
            expense = db.session.get(Expense, expense_id)
            if not expense:
                return {"success": False, "error": "النفقة غير موجودة"}
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.EXPENSE.value, 
                expense_id, 
                f"النفقة #{expense.id}", 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة
            related_data = self._collect_expense_related_data(expense_id)
            
            # 4. تنفيذ العمليات العكسية
            reversals = self._reverse_expense_operations(expense_id)
            
            # 5. حذف البيانات
            self._delete_expense_data(expense_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data["expense_data"],
                related_entities=related_data["related_entities"],
                stock_reversals=reversals["stock_reversals"],
                accounting_reversals=reversals["accounting_reversals"],
                balance_reversals=reversals["balance_reversals"]
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف النفقة #{expense.id} بنجاح",
                "deletion_id": deletion_log.id,
                "confirmation_code": deletion_log.confirmation_code
            }
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": f"فشل في حذف النفقة: {str(e)}"}
    
    def delete_payment(self, payment_id: int, deleted_by: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي للدفعة مع العمليات العكسية"""
        try:
            # 1. جلب الدفعة
            payment = db.session.get(Payment, payment_id)
            if not payment:
                return {"success": False, "error": "الدفعة غير موجودة"}
            
            # 2. إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                DeletionType.PAYMENT.value, 
                payment_id, 
                f"الدفعة #{payment.payment_number or payment.id}", 
                deleted_by, 
                reason
            )
            
            # 3. جمع البيانات المرتبطة
            related_data = self._collect_payment_related_data(payment_id)
            
            # 4. تنفيذ العمليات العكسية
            reversals = self._reverse_payment_operations(payment_id)
            
            # 5. حذف البيانات
            self._delete_payment_data(payment_id)
            
            # 6. تسجيل اكتمال الحذف
            deletion_log.mark_completed(
                deleted_data=related_data["payment_data"],
                related_entities=related_data["related_entities"],
                stock_reversals=reversals["stock_reversals"],
                accounting_reversals=reversals["accounting_reversals"],
                balance_reversals=reversals["balance_reversals"]
            )
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف الدفعة #{payment.payment_number or payment.id} بنجاح",
                "deletion_id": deletion_log.id,
                "confirmation_code": deletion_log.confirmation_code
            }
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": f"فشل في حذف الدفعة: {str(e)}"}
    
    def restore_deletion(self, deletion_id: int, restored_by: int, notes: str = None) -> Dict[str, Any]:
        """استعادة عملية حذف"""
        try:
            deletion_log = db.session.get(DeletionLog, deletion_id)
            if not deletion_log:
                return {"success": False, "error": "سجل الحذف غير موجود"}
            
            if not deletion_log.can_restore:
                return {"success": False, "error": "لا يمكن استعادة هذا الحذف"}
            
            # تنفيذ الاستعادة حسب نوع الحذف
            if deletion_log.deletion_type == DeletionType.CUSTOMER.value:
                result = self._restore_customer(deletion_log)
            elif deletion_log.deletion_type == DeletionType.SALE.value:
                result = self._restore_sale(deletion_log)
            elif deletion_log.deletion_type == DeletionType.PAYMENT.value:
                result = self._restore_payment(deletion_log)
            elif deletion_log.deletion_type == DeletionType.EXPENSE.value:
                result = self._restore_expense(deletion_log)
            else:
                return {"success": False, "error": "نوع الحذف غير مدعوم للاستعادة"}
            
            if result["success"]:
                deletion_log.mark_restored(restored_by, notes)
                db.session.commit()
                return {"success": True, "message": "تم استعادة البيانات بنجاح"}
            else:
                return result
                
        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": f"فشل في الاستعادة: {str(e)}"}
    
    def _restore_customer(self, deletion_log: DeletionLog) -> Dict[str, Any]:
        """استعادة العميل"""
        try:
            customer_data = deletion_log.deleted_data
            if not customer_data:
                return {"success": False, "error": "بيانات العميل غير متوفرة"}
            
            # إنشاء العميل
            customer = Customer(
                id=customer_data["id"],
                name=customer_data["name"],
                phone=customer_data.get("phone"),
                email=customer_data.get("email"),
                address=customer_data.get("address")
            )
            db.session.add(customer)
            
            # استعادة المبيعات (إذا كانت موجودة)
            # TODO: إضافة نماذج المبيعات عند توفرها
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": f"فشل في استعادة العميل: {str(e)}"}
    
    def _restore_sale(self, deletion_log: DeletionLog) -> Dict[str, Any]:
        """استعادة البيع"""
        try:
            sale_data = deletion_log.deleted_data
            if not sale_data:
                return {"success": False, "error": "بيانات البيع غير متوفرة"}
            
            # TODO: إضافة نماذج المبيعات عند توفرها
            return {"success": False, "error": "نماذج المبيعات غير متوفرة حالياً"}
            
        except Exception as e:
            return {"success": False, "error": f"فشل في استعادة البيع: {str(e)}"}
    
    def _restore_payment(self, deletion_log: DeletionLog) -> Dict[str, Any]:
        """استعادة الدفعة"""
        try:
            payment_data = deletion_log.deleted_data
            if not payment_data:
                return {"success": False, "error": "بيانات الدفعة غير متوفرة"}
            
            # إنشاء الدفعة
            payment = Payment(
                id=payment_data["id"],
                entity_type=payment_data["entity_type"],
                entity_id=payment_data["entity_id"],
                total_amount=Decimal(str(payment_data["total_amount"])),
                payment_date=datetime.fromisoformat(payment_data["payment_date"]) if payment_data.get("payment_date") else None,
                method=payment_data["method"],
                status=payment_data["status"],
                direction=payment_data["direction"]
            )
            db.session.add(payment)
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": f"فشل في استعادة الدفعة: {str(e)}"}
    
    def _restore_expense(self, deletion_log: DeletionLog) -> Dict[str, Any]:
        """استعادة النفقة"""
        try:
            expense_data = deletion_log.deleted_data
            if not expense_data:
                return {"success": False, "error": "بيانات النفقة غير متوفرة"}
            
            # إنشاء النفقة
            from models import Expense
            expense = Expense(
                id=expense_data["id"],
                amount=Decimal(str(expense_data["amount"])),
                currency=expense_data["currency"],
                type_id=expense_data["type_id"],
                payee_type=expense_data["payee_type"],
                payee_entity_id=expense_data.get("payee_entity_id"),
                payee_name=expense_data.get("payee_name"),
                payment_method=expense_data["payment_method"],
                description=expense_data.get("description"),
                notes=expense_data.get("notes"),
                date=datetime.fromisoformat(expense_data["date"]) if expense_data.get("date") else datetime.utcnow()
            )
            db.session.add(expense)
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": f"فشل في استعادة النفقة: {str(e)}"}

    def delete_service(self, service_id: int, user_id: int, reason: str = None) -> Dict[str, Any]:
        """حذف قوي لطلب صيانة"""
        try:
            from models import ServiceRequest, ServicePart, ServiceTask
            
            # البحث عن طلب الصيانة
            service = ServiceRequest.query.get(service_id)
            if not service:
                return {"success": False, "error": "طلب الصيانة غير موجود"}
            
            # إنشاء سجل الحذف
            deletion_log = self.create_deletion_log(
                deletion_type=DeletionType.SERVICE.value,
                entity_id=service_id,
                entity_name=f"طلب صيانة {service.service_number}",
                deleted_by=user_id,
                reason=reason
            )
            
            # جمع البيانات المرتبطة
            service_data = {
                "id": service.id,
                "service_number": service.service_number,
                "customer_id": service.customer_id,
                "customer_name": service.customer.name if service.customer else service.name,
                "vehicle_vrn": service.vehicle_vrn,
                "vehicle_make": service.vehicle_make,
                "vehicle_model": service.vehicle_model,
                "vehicle_year": service.vehicle_year,
                "priority": service.priority.value if service.priority else None,
                "status": service.status.value if service.status else None,
                "request_date": service.request_date.isoformat() if service.request_date else None,
                "completion_date": service.completion_date.isoformat() if service.completion_date else None,
                "description": service.description,
                "notes": service.notes,
                "total_cost": float(service.total_cost) if service.total_cost else 0,
                "currency": service.currency,
                "created_at": service.created_at.isoformat() if service.created_at else None,
                "updated_at": service.updated_at.isoformat() if service.updated_at else None
            }
            
            # جمع قطع الغيار
            parts_data = []
            for part in service.parts:
                parts_data.append({
                    "id": part.id,
                    "product_id": part.product_id,
                    "product_name": part.product.name if part.product else None,
                    "quantity": part.quantity,
                    "unit_price": float(part.unit_price) if part.unit_price else 0,
                    "discount": float(part.discount) if part.discount else 0,
                    "tax_rate": float(part.tax_rate) if part.tax_rate else 0,
                    "notes": part.notes
                })
            
            # جمع المهام
            tasks_data = []
            for task in service.tasks:
                tasks_data.append({
                    "id": task.id,
                    "task_name": task.task_name,
                    "description": task.description,
                    "quantity": task.quantity,
                    "unit_price": float(task.unit_price) if task.unit_price else 0,
                    "discount": float(task.discount) if task.discount else 0,
                    "tax_rate": float(task.tax_rate) if task.tax_rate else 0,
                    "status": task.status.value if task.status else None,
                    "assigned_to": task.assigned_to,
                    "start_date": task.start_date.isoformat() if task.start_date else None,
                    "end_date": task.end_date.isoformat() if task.end_date else None,
                    "notes": task.notes
                })
            
            # حفظ البيانات في سجل الحذف
            deletion_log.rollback_data = json.dumps({
                "service": service_data,
                "parts": parts_data,
                "tasks": tasks_data
            })
            
            # حذف البيانات المرتبطة
            ServicePart.query.filter_by(service_id=service_id).delete()
            ServiceTask.query.filter_by(service_id=service_id).delete()
            
            # حذف طلب الصيانة
            db.session.delete(service)
            
            # تحديث حالة سجل الحذف
            deletion_log.status = DeletionStatus.COMPLETED.value
            deletion_log.deleted_at = datetime.utcnow()
            
            db.session.commit()
            
            return {"success": True, "message": "تم حذف طلب الصيانة بنجاح"}
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": f"فشل في حذف طلب الصيانة: {str(e)}"}


class DeletionConfirmationService:
    """خدمة تأكيد الحذف"""
    
    @staticmethod
    def confirm_deletion(confirmation_code: str, user_id: int) -> Dict[str, Any]:
        """تأكيد عملية الحذف"""
        try:
            deletion_log = db.session.query(DeletionLog).filter_by(
                confirmation_code=confirmation_code,
                status=DeletionStatus.PENDING.value
            ).first()
            
            if not deletion_log:
                return {"success": False, "error": "كود التأكيد غير صحيح أو منتهي الصلاحية"}
            
            # تنفيذ الحذف
            hard_delete_service = HardDeleteService()
            
            if deletion_log.deletion_type == DeletionType.CUSTOMER.value:
                result = hard_delete_service.delete_customer(
                    deletion_log.entity_id, 
                    user_id, 
                    deletion_log.deletion_reason
                )
            elif deletion_log.deletion_type == DeletionType.SALE.value:
                result = hard_delete_service.delete_sale(
                    deletion_log.entity_id, 
                    user_id, 
                    deletion_log.deletion_reason
                )
            elif deletion_log.deletion_type == DeletionType.PAYMENT.value:
                result = hard_delete_service.delete_payment(
                    deletion_log.entity_id, 
                    user_id, 
                    deletion_log.deletion_reason
                )
            else:
                return {"success": False, "error": "نوع الحذف غير مدعوم"}
            
            return result
            
        except Exception as e:
            return {"success": False, "error": f"فشل في تأكيد الحذف: {str(e)}"}
