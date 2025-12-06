from decimal import Decimal
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import object_session
from models import (
    Customer, Sale, SaleReturn, Invoice, ServiceRequest, PreOrder, OnlinePreOrder,
    Payment, PaymentSplit, Check, PaymentDirection, PaymentStatus, PaymentMethod, Expense, ExpenseType
)
from extensions import db


def convert_amount(amount, from_currency, to_currency, date=None):
    from models import convert_amount as _convert_amount
    return _convert_amount(amount, from_currency, to_currency, date)


def calculate_customer_balance_components(customer_id, session=None):
    """حساب جميع مكونات رصيد العميل"""
    if not session:
        session = db.session
    
    try:
        from sqlalchemy.orm import Session
        from sqlalchemy import text as sa_text
        if isinstance(session, Session):
            try:
                session.execute(sa_text("SELECT 1"))
            except Exception:
                from sqlalchemy.orm import sessionmaker
                session = sessionmaker(bind=db.engine)()
    except Exception:
        pass
    
    customer = session.get(Customer, customer_id)
    if not customer:
        return None
    
    result = {
        'sales_balance': Decimal('0.00'),
        'returns_balance': Decimal('0.00'),
        'invoices_balance': Decimal('0.00'),
        'services_balance': Decimal('0.00'),
        'preorders_balance': Decimal('0.00'),
        'online_orders_balance': Decimal('0.00'),
        'payments_in_balance': Decimal('0.00'),
        'payments_out_balance': Decimal('0.00'),
        'checks_in_balance': Decimal('0.00'),
        'checks_out_balance': Decimal('0.00'),
        'returned_checks_in_balance': Decimal('0.00'),
        'returned_checks_out_balance': Decimal('0.00'),
        'expenses_balance': Decimal('0.00'),
        'service_expenses_balance': Decimal('0.00'),
    }
    
    try:
        ils_sales_sum = session.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            Sale.customer_id == customer_id,
            Sale.status == 'CONFIRMED',
            Sale.currency == 'ILS'
        ).scalar() or 0
        result['sales_balance'] += Decimal(str(ils_sales_sum))
        
        other_currency_sales = session.query(Sale).filter(
            Sale.customer_id == customer_id,
            Sale.status == 'CONFIRMED',
            Sale.currency != 'ILS'
        ).all()
        for s in other_currency_sales:
            amt = Decimal(str(s.total_amount or 0))
            try:
                result['sales_balance'] += convert_amount(amt, s.currency, "ILS", s.sale_date)
            except Exception:
                pass
        
        ils_returns_sum = session.query(func.coalesce(func.sum(SaleReturn.total_amount), 0)).filter(
            SaleReturn.customer_id == customer_id,
            SaleReturn.status == 'CONFIRMED',
            SaleReturn.currency == 'ILS'
        ).scalar() or 0
        result['returns_balance'] += Decimal(str(ils_returns_sum))
        
        other_currency_returns = session.query(SaleReturn).filter(
            SaleReturn.customer_id == customer_id,
            SaleReturn.status == 'CONFIRMED',
            SaleReturn.currency != 'ILS'
        ).all()
        for r in other_currency_returns:
            amt = Decimal(str(r.total_amount or 0))
            try:
                result['returns_balance'] += convert_amount(amt, r.currency, "ILS", r.created_at)
            except Exception:
                pass
        
        ils_invoices_sum = session.query(func.coalesce(func.sum(Invoice.total_amount), 0)).filter(
            Invoice.customer_id == customer_id,
            Invoice.cancelled_at.is_(None),
            Invoice.currency == 'ILS'
        ).scalar() or 0
        result['invoices_balance'] += Decimal(str(ils_invoices_sum))
        
        other_currency_invoices = session.query(Invoice).filter(
            Invoice.customer_id == customer_id,
            Invoice.cancelled_at.is_(None),
            Invoice.currency != 'ILS'
        ).all()
        for inv in other_currency_invoices:
            amt = Decimal(str(inv.total_amount or 0))
            try:
                result['invoices_balance'] += convert_amount(amt, inv.currency, "ILS", inv.invoice_date)
            except Exception:
                pass
        
        ils_services = session.query(ServiceRequest).filter(
            ServiceRequest.customer_id == customer_id,
            ServiceRequest.currency == 'ILS'
        ).all()
        for srv in ils_services:
            subtotal = Decimal(str(srv.parts_total or 0)) + Decimal(str(srv.labor_total or 0))
            discount = Decimal(str(srv.discount_total or 0))
            base = subtotal - discount
            if base < 0:
                base = Decimal('0.00')
            tax_rate = Decimal(str(srv.tax_rate or 0))
            tax = base * (tax_rate / Decimal('100'))
            total = base + tax
            result['services_balance'] += total
        
        other_currency_services = session.query(ServiceRequest).filter(
            ServiceRequest.customer_id == customer_id,
            ServiceRequest.currency != 'ILS'
        ).all()
        for srv in other_currency_services:
            subtotal = Decimal(str(srv.parts_total or 0)) + Decimal(str(srv.labor_total or 0))
            discount = Decimal(str(srv.discount_total or 0))
            base = subtotal - discount
            if base < 0:
                base = Decimal('0.00')
            tax_rate = Decimal(str(srv.tax_rate or 0))
            tax = base * (tax_rate / Decimal('100'))
            total = base + tax
            try:
                result['services_balance'] += convert_amount(total, srv.currency, "ILS", srv.received_at)
            except Exception:
                pass
        
        result['preorders_balance'] = Decimal('0.00')
        
        ils_online_orders_sum = session.query(func.coalesce(func.sum(OnlinePreOrder.total_amount), 0)).filter(
            OnlinePreOrder.customer_id == customer_id,
            OnlinePreOrder.payment_status != 'CANCELLED',
            OnlinePreOrder.currency == 'ILS'
        ).scalar() or 0
        result['online_orders_balance'] += Decimal(str(ils_online_orders_sum))
        
        other_currency_online_orders = session.query(OnlinePreOrder).filter(
            OnlinePreOrder.customer_id == customer_id,
            OnlinePreOrder.payment_status != 'CANCELLED',
            OnlinePreOrder.currency != 'ILS'
        ).all()
        for oo in other_currency_online_orders:
            amt = Decimal(str(oo.total_amount or 0))
            try:
                result['online_orders_balance'] += convert_amount(amt, oo.currency, "ILS", oo.created_at)
            except Exception:
                pass
        
        payments_in_direct = session.query(Payment).outerjoin(
            Check, Check.payment_id == Payment.id
        ).outerjoin(
            PreOrder, Payment.preorder_id == PreOrder.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None),
            or_(
                Payment.preorder_id.is_(None),
                Payment.sale_id.isnot(None),
                PreOrder.status == 'FULFILLED'
            )
        ).all()
        
        payments_in_from_sales = session.query(Payment).join(
            Sale, Payment.sale_id == Sale.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Sale.customer_id == customer_id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_in_from_invoices = session.query(Payment).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Invoice.customer_id == customer_id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_in_from_services = session.query(Payment).join(
            ServiceRequest, Payment.service_id == ServiceRequest.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            ServiceRequest.customer_id == customer_id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_in_from_preorders = session.query(Payment).join(
            PreOrder, Payment.preorder_id == PreOrder.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            PreOrder.customer_id == customer_id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None),
            or_(
                PreOrder.status == 'FULFILLED',
                Payment.sale_id.isnot(None)
            )
        ).all()
        
        seen_payment_ids = set()
        payments_in_all = []
        for p in (payments_in_direct + payments_in_from_sales + payments_in_from_invoices + 
                 payments_in_from_services + payments_in_from_preorders):
            if p.id not in seen_payment_ids:
                seen_payment_ids.add(p.id)
                payments_in_all.append(p)
        
        for p in payments_in_all:
            splits = session.query(PaymentSplit).filter(
                PaymentSplit.payment_id == p.id
            ).all()
            
            if splits:
                total_splits = Decimal('0.00')
                
                payment_checks = session.query(Check).filter(
                    Check.payment_id == p.id
                ).all()
                
                returned_check_amounts = {}
                for check in payment_checks:
                    if check.status in ['RETURNED', 'BOUNCED']:
                        if check.reference_number and 'PMT-SPLIT-' in check.reference_number:
                            try:
                                split_id = int(check.reference_number.split('PMT-SPLIT-')[1].split('-')[0])
                                returned_check_amounts[split_id] = Decimal(str(check.amount or 0))
                            except:
                                pass
                        elif check.check_number:
                            for split in splits:
                                split_details = split.details or {}
                                if isinstance(split_details, str):
                                    try:
                                        import json
                                        split_details = json.loads(split_details)
                                    except:
                                        split_details = {}
                                if split_details.get('check_number') == check.check_number:
                                    returned_check_amounts[split.id] = Decimal(str(check.amount or 0))
                                    break
                
                for split in splits:
                    split_amt = Decimal(str(split.amount or 0))
                    split_converted_amt = Decimal(str(getattr(split, 'converted_amount', 0) or 0))
                    split_converted_currency = (getattr(split, 'converted_currency', None) or split.currency or 'ILS').upper()
                    
                    if split_converted_amt > 0 and split_converted_currency == 'ILS':
                        total_splits += split_converted_amt
                    elif split.currency == "ILS":
                        total_splits += split_amt
                    else:
                        try:
                            total_splits += convert_amount(split_amt, split.currency, "ILS", p.payment_date)
                        except Exception:
                            pass
                
                amt = total_splits
            else:
                amt = Decimal(str(p.total_amount or 0))
            
            if p.currency == "ILS":
                result['payments_in_balance'] += amt
            else:
                try:
                    result['payments_in_balance'] += convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    pass
        
        active_preorders = session.query(PreOrder).filter(
            PreOrder.customer_id == customer_id,
            PreOrder.prepaid_amount > 0,
            PreOrder.status != 'FULFILLED',
            PreOrder.status != 'CANCELLED'
        ).all()
        
        for po in active_preorders:
            has_payment_for_sale = session.query(Payment).filter(
                Payment.preorder_id == po.id,
                Payment.sale_id.isnot(None)
            ).first() is not None
            
            if not has_payment_for_sale:
                prepaid_amt = Decimal(str(po.prepaid_amount or 0))
                if po.currency == "ILS":
                    result['payments_in_balance'] += prepaid_amt
                else:
                    try:
                        result['payments_in_balance'] += convert_amount(prepaid_amt, po.currency, "ILS", po.preorder_date or po.created_at)
                    except Exception:
                        pass
        
        ils_manual_checks_in_sum = session.query(func.coalesce(func.sum(Check.amount), 0)).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'IN',
            ~Check.status.in_(['RETURNED', 'BOUNCED', 'CANCELLED', 'ARCHIVED']),
            Check.currency == 'ILS'
        ).scalar() or 0
        checks_in_manual = Decimal(str(ils_manual_checks_in_sum))
        
        other_currency_manual_checks_in = session.query(Check).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'IN',
            ~Check.status.in_(['RETURNED', 'BOUNCED', 'CANCELLED', 'ARCHIVED']),
            Check.currency != 'ILS'
        ).all()
        for check in other_currency_manual_checks_in:
            amt = Decimal(str(check.amount or 0))
            try:
                checks_in_manual += convert_amount(amt, check.currency, "ILS", check.check_date)
            except Exception:
                pass
        
        result['checks_in_balance'] = checks_in_manual
        result['payments_in_balance'] += checks_in_manual
        
        payments_out_direct = session.query(Payment).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'OUT',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_out_from_sales = session.query(Payment).join(
            Sale, Payment.sale_id == Sale.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Sale.customer_id == customer_id,
            Payment.direction == 'OUT',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_out_from_invoices = session.query(Payment).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Invoice.customer_id == customer_id,
            Payment.direction == 'OUT',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_out_from_services = session.query(Payment).join(
            ServiceRequest, Payment.service_id == ServiceRequest.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            ServiceRequest.customer_id == customer_id,
            Payment.direction == 'OUT',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        payments_out_from_preorders = session.query(Payment).join(
            PreOrder, Payment.preorder_id == PreOrder.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            PreOrder.customer_id == customer_id,
            Payment.direction == 'OUT',
            Payment.status.in_(['COMPLETED', 'PENDING']),
            Payment.expense_id.is_(None)
        ).all()
        
        seen_payment_ids_out = set()
        payments_out_all = []
        for p in (payments_out_direct + payments_out_from_sales + payments_out_from_invoices + 
                 payments_out_from_services + payments_out_from_preorders):
            if p.id not in seen_payment_ids_out:
                seen_payment_ids_out.add(p.id)
                payments_out_all.append(p)
        
        for p in payments_out_all:
            splits = session.query(PaymentSplit).filter(
                PaymentSplit.payment_id == p.id
            ).all()
            
            if splits:
                total_splits = Decimal('0.00')
                
                payment_checks = session.query(Check).filter(
                    Check.payment_id == p.id
                ).all()
                
                returned_check_amounts = {}
                for check in payment_checks:
                    if check.status in ['RETURNED', 'BOUNCED']:
                        if check.reference_number and 'PMT-SPLIT-' in check.reference_number:
                            try:
                                split_id = int(check.reference_number.split('PMT-SPLIT-')[1].split('-')[0])
                                returned_check_amounts[split_id] = Decimal(str(check.amount or 0))
                            except:
                                pass
                        elif check.check_number:
                            for split in splits:
                                split_details = split.details or {}
                                if isinstance(split_details, str):
                                    try:
                                        import json
                                        split_details = json.loads(split_details)
                                    except:
                                        split_details = {}
                                if split_details.get('check_number') == check.check_number:
                                    returned_check_amounts[split.id] = Decimal(str(check.amount or 0))
                                    break
                
                # حساب مجموع جميع splits (بما فيها المرتجة)
                for split in splits:
                    split_amt = Decimal(str(split.amount or 0))
                    split_converted_amt = Decimal(str(getattr(split, 'converted_amount', 0) or 0))
                    split_converted_currency = (getattr(split, 'converted_currency', None) or split.currency or 'ILS').upper()
                    
                    if split_converted_amt > 0 and split_converted_currency == 'ILS':
                        total_splits += split_converted_amt
                    elif split.currency == "ILS":
                        total_splits += split_amt
                    else:
                        try:
                            total_splits += convert_amount(split_amt, split.currency, "ILS", p.payment_date)
                        except Exception:
                            pass
                
                amt = total_splits
            else:
                amt = Decimal(str(p.total_amount or 0))
            
            if p.currency == "ILS":
                result['payments_out_balance'] += amt
            else:
                try:
                    result['payments_out_balance'] += convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    pass
        
        ils_manual_checks_out_sum = session.query(func.coalesce(func.sum(Check.amount), 0)).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'OUT',
            ~Check.status.in_(['RETURNED', 'BOUNCED', 'CANCELLED', 'ARCHIVED']),
            Check.currency == 'ILS'
        ).scalar() or 0
        checks_out_manual = Decimal(str(ils_manual_checks_out_sum))
        
        other_currency_manual_checks_out = session.query(Check).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'OUT',
            ~Check.status.in_(['RETURNED', 'BOUNCED', 'CANCELLED', 'ARCHIVED']),
            Check.currency != 'ILS'
        ).all()
        for check in other_currency_manual_checks_out:
            amt = Decimal(str(check.amount or 0))
            try:
                checks_out_manual += convert_amount(amt, check.currency, "ILS", check.check_date)
            except Exception:
                pass
        
        result['checks_out_balance'] = checks_out_manual
        result['payments_out_balance'] += checks_out_manual
        
        returned_in_direct = session.query(Payment).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_in_from_sales = session.query(Payment).join(
            Sale, Payment.sale_id == Sale.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Sale.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_in_from_invoices = session.query(Payment).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Invoice.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_in_from_services = session.query(Payment).join(
            ServiceRequest, Payment.service_id == ServiceRequest.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            ServiceRequest.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_in_from_preorders = session.query(Payment).join(
            PreOrder, Payment.preorder_id == PreOrder.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            PreOrder.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        from sqlalchemy import cast, String, exists
        returned_in_with_splits = session.query(Payment).join(
            PaymentSplit, PaymentSplit.payment_id == Payment.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'IN',
            or_(
                cast(PaymentSplit.method, String).like('%CHECK%'),
                cast(PaymentSplit.method, String).like('%CHEQUE%'),
                PaymentSplit.method == PaymentMethod.CHEQUE.value
            ),
            exists().where(
                and_(
                    Check.reference_number == func.concat('PMT-SPLIT-', PaymentSplit.id),
                    Check.status.in_(['RETURNED', 'BOUNCED']),
                    Check.status != 'CANCELLED'
                )
            )
        ).all()
        
        seen_returned_in_ids = set()
        returned_in_all = []
        for p in (returned_in_direct + returned_in_from_sales + returned_in_from_invoices + 
                 returned_in_from_services + returned_in_from_preorders + returned_in_with_splits):
            if p.id not in seen_returned_in_ids:
                seen_returned_in_ids.add(p.id)
                returned_in_all.append(p)
        
        for p in returned_in_all:
            splits = session.query(PaymentSplit).filter(
                PaymentSplit.payment_id == p.id
            ).all()
            
            if splits:
                for split in splits:
                    is_cheque_split = (
                        split.method == PaymentMethod.CHEQUE.value or
                        split.method == PaymentMethod.CHEQUE or
                        (split.method and ('CHEQUE' in str(split.method).upper() or 'CHECK' in str(split.method).upper()))
                    )
                    if is_cheque_split:
                        split_checks = session.query(Check).filter(
                            Check.reference_number == f"PMT-SPLIT-{split.id}",
                            Check.status.in_(['RETURNED', 'BOUNCED']),
                            Check.status != 'CANCELLED'
                        ).all()
                        if split_checks:
                            for check in split_checks:
                                amt = Decimal(str(check.amount or 0))
                                check_currency = check.currency or split.currency or p.currency or "ILS"
                                if check_currency == "ILS":
                                    result['returned_checks_in_balance'] += amt
                                else:
                                    try:
                                        check_date = check.check_date if check else p.payment_date
                                        result['returned_checks_in_balance'] += convert_amount(amt, check_currency, "ILS", check_date)
                                    except Exception:
                                        pass
                        else:
                            split_details = split.details or {}
                            if isinstance(split_details, str):
                                try:
                                    import json
                                    split_details = json.loads(split_details)
                                except:
                                    split_details = {}
                            
                            check_status = split_details.get('check_status', '').upper() if split_details else ''
                            
                            if check_status in ['RETURNED', 'BOUNCED']:
                                split_amt = Decimal(str(split.amount or 0))
                                split_converted_amt = Decimal(str(getattr(split, 'converted_amount', 0) or 0))
                                split_converted_currency = (getattr(split, 'converted_currency', None) or split.currency or 'ILS').upper()
                                split_currency = split.currency or p.currency or "ILS"
                                
                                if split_converted_amt > 0 and split_converted_currency == 'ILS':
                                    amt = split_converted_amt
                                elif split_currency == "ILS":
                                    amt = split_amt
                                else:
                                    try:
                                        amt = convert_amount(split_amt, split_currency, "ILS", p.payment_date)
                                    except Exception:
                                        amt = split_amt
                                
                                result['returned_checks_in_balance'] += amt
            else:
                returned_checks = session.query(Check).filter(
                    Check.payment_id == p.id,
                    Check.status.in_(['RETURNED', 'BOUNCED']),
                    Check.status != 'CANCELLED'
                ).all()
                
                for check in returned_checks:
                    amt = Decimal(str(check.amount or 0))
                    check_currency = check.currency or p.currency or "ILS"
                    if check_currency == "ILS":
                        result['returned_checks_in_balance'] += amt
                    else:
                        try:
                            check_date = check.check_date if check else p.payment_date
                            result['returned_checks_in_balance'] += convert_amount(amt, check_currency, "ILS", check_date)
                        except Exception:
                            pass
                
                if not splits and not returned_checks and p.status == 'FAILED' and p.method == PaymentMethod.CHEQUE.value:
                    amt = Decimal(str(p.total_amount or 0))
                    check_currency = p.currency or "ILS"
                    if check_currency == "ILS":
                        result['returned_checks_in_balance'] += amt
                    else:
                        try:
                            result['returned_checks_in_balance'] += convert_amount(amt, check_currency, "ILS", p.payment_date)
                        except Exception:
                            pass
        
        ils_manual_returned_checks_in_sum = session.query(func.coalesce(func.sum(Check.amount), 0)).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            or_(
                Check.reference_number.is_(None),
                ~Check.reference_number.like('PMT-SPLIT-%')
            ),
            Check.direction == 'IN',
            Check.status.in_(['RETURNED', 'BOUNCED']),
            Check.status != 'CANCELLED',
            Check.currency == 'ILS'
        ).scalar() or 0
        result['returned_checks_in_balance'] += Decimal(str(ils_manual_returned_checks_in_sum))
        
        other_currency_manual_returned_checks_in = session.query(Check).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            or_(
                Check.reference_number.is_(None),
                ~Check.reference_number.like('PMT-SPLIT-%')
            ),
            Check.direction == 'IN',
            Check.status.in_(['RETURNED', 'BOUNCED']),
            Check.status != 'CANCELLED',
            Check.currency != 'ILS'
        ).all()
        for check in other_currency_manual_returned_checks_in:
            amt = Decimal(str(check.amount or 0))
            try:
                result['returned_checks_in_balance'] += convert_amount(amt, check.currency, "ILS", check.check_date)
            except Exception:
                pass
        
        returned_out_direct = session.query(Payment).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_out_from_sales = session.query(Payment).join(
            Sale, Payment.sale_id == Sale.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Sale.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_out_from_invoices = session.query(Payment).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            Invoice.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_out_from_services = session.query(Payment).join(
            ServiceRequest, Payment.service_id == ServiceRequest.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            ServiceRequest.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        returned_out_from_preorders = session.query(Payment).join(
            PreOrder, Payment.preorder_id == PreOrder.id
        ).outerjoin(
            Check, Check.payment_id == Payment.id
        ).filter(
            PreOrder.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                Check.status.in_(['RETURNED', 'BOUNCED']),
                and_(
                    Payment.status == 'FAILED',
                    Payment.method == PaymentMethod.CHEQUE.value
                )
            )
        ).all()
        
        from sqlalchemy import cast, String, exists
        returned_out_with_splits = session.query(Payment).join(
            PaymentSplit, PaymentSplit.payment_id == Payment.id
        ).filter(
            Payment.customer_id == customer_id,
            Payment.direction == 'OUT',
            or_(
                cast(PaymentSplit.method, String).like('%CHECK%'),
                cast(PaymentSplit.method, String).like('%CHEQUE%'),
                PaymentSplit.method == PaymentMethod.CHEQUE.value
            ),
            exists().where(
                and_(
                    Check.reference_number == func.concat('PMT-SPLIT-', PaymentSplit.id),
                    Check.status.in_(['RETURNED', 'BOUNCED']),
                    Check.status != 'CANCELLED'
                )
            )
        ).all()
        
        seen_returned_out_ids = set()
        returned_out_all = []
        for p in (returned_out_direct + returned_out_from_sales + returned_out_from_invoices + 
                 returned_out_from_services + returned_out_from_preorders + returned_out_with_splits):
            if p.id not in seen_returned_out_ids:
                seen_returned_out_ids.add(p.id)
                returned_out_all.append(p)
        
        for p in returned_out_all:
            splits = session.query(PaymentSplit).filter(
                PaymentSplit.payment_id == p.id
            ).all()
            
            if splits:
                for split in splits:
                    is_cheque_split = (
                        split.method == PaymentMethod.CHEQUE.value or
                        split.method == PaymentMethod.CHEQUE or
                        (split.method and ('CHEQUE' in str(split.method).upper() or 'CHECK' in str(split.method).upper()))
                    )
                    if is_cheque_split:
                        split_checks = session.query(Check).filter(
                            Check.reference_number == f"PMT-SPLIT-{split.id}",
                            Check.status.in_(['RETURNED', 'BOUNCED']),
                            Check.status != 'CANCELLED'
                        ).all()
                        if split_checks:
                            for check in split_checks:
                                amt = Decimal(str(check.amount or 0))
                                check_currency = check.currency or split.currency or p.currency or "ILS"
                                if check_currency == "ILS":
                                    result['returned_checks_out_balance'] += amt
                                else:
                                    try:
                                        check_date = check.check_date if check else p.payment_date
                                        result['returned_checks_out_balance'] += convert_amount(amt, check_currency, "ILS", check_date)
                                    except Exception:
                                        pass
                        else:
                            split_details = split.details or {}
                            if isinstance(split_details, str):
                                try:
                                    import json
                                    split_details = json.loads(split_details)
                                except:
                                    split_details = {}
                            
                            check_status = split_details.get('check_status', '').upper() if split_details else ''
                            
                            if check_status in ['RETURNED', 'BOUNCED']:
                                split_amt = Decimal(str(split.amount or 0))
                                split_converted_amt = Decimal(str(getattr(split, 'converted_amount', 0) or 0))
                                split_converted_currency = (getattr(split, 'converted_currency', None) or split.currency or 'ILS').upper()
                                split_currency = split.currency or p.currency or "ILS"
                                
                                if split_converted_amt > 0 and split_converted_currency == 'ILS':
                                    amt = split_converted_amt
                                elif split_currency == "ILS":
                                    amt = split_amt
                                else:
                                    try:
                                        amt = convert_amount(split_amt, split_currency, "ILS", p.payment_date)
                                    except Exception:
                                        amt = split_amt
                                
                                result['returned_checks_out_balance'] += amt
            else:
                returned_checks = session.query(Check).filter(
                    Check.payment_id == p.id,
                    Check.status.in_(['RETURNED', 'BOUNCED']),
                    Check.status != 'CANCELLED'
                ).all()
                
                for check in returned_checks:
                    amt = Decimal(str(check.amount or 0))
                    check_currency = check.currency or p.currency or "ILS"
                    if check_currency == "ILS":
                        result['returned_checks_out_balance'] += amt
                    else:
                        try:
                            check_date = check.check_date if check else p.payment_date
                            result['returned_checks_out_balance'] += convert_amount(amt, check_currency, "ILS", check_date)
                        except Exception:
                            pass
                
                if not returned_checks and p.status == 'FAILED' and p.method == PaymentMethod.CHEQUE.value:
                    amt = Decimal(str(p.total_amount or 0))
                    check_currency = p.currency or "ILS"
                    if check_currency == "ILS":
                        result['returned_checks_out_balance'] += amt
                    else:
                        try:
                            result['returned_checks_out_balance'] += convert_amount(amt, check_currency, "ILS", p.payment_date)
                        except Exception:
                            pass
        
        ils_manual_returned_checks_out_sum = session.query(func.coalesce(func.sum(Check.amount), 0)).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'OUT',
            Check.status.in_(['RETURNED', 'BOUNCED']),
            Check.status != 'CANCELLED',
            Check.currency == 'ILS'
        ).scalar() or 0
        result['returned_checks_out_balance'] += Decimal(str(ils_manual_returned_checks_out_sum))
        
        other_currency_manual_returned_checks_out = session.query(Check).filter(
            Check.customer_id == customer_id,
            Check.payment_id.is_(None),
            Check.direction == 'OUT',
            Check.status.in_(['RETURNED', 'BOUNCED']),
            Check.status != 'CANCELLED',
            Check.currency != 'ILS'
        ).all()
        for check in other_currency_manual_returned_checks_out:
            amt = Decimal(str(check.amount or 0))
            try:
                result['returned_checks_out_balance'] += convert_amount(amt, check.currency, "ILS", check.check_date)
            except Exception:
                pass
        
        expenses = session.query(Expense).filter(
            Expense.customer_id == customer_id
        ).all()
        
        for exp in expenses:
            amt = Decimal(str(exp.amount or 0))
            amt_ils = amt
            if exp.currency and exp.currency != "ILS":
                try:
                    amt_ils = convert_amount(amt, exp.currency, "ILS", exp.date)
                except Exception:
                    pass
            
            exp_type_code = None
            if exp.type_id:
                exp_type = session.query(ExpenseType).filter_by(id=exp.type_id).first()
                if exp_type:
                    exp_type_code = (exp_type.code or "").strip().upper()
            
            is_service_expense = (
                exp_type_code in ('PARTNER_EXPENSE', 'SERVICE_EXPENSE') or
                (exp.partner_id and exp.payee_type and exp.payee_type.upper() == "PARTNER") or
                (exp.supplier_id and exp.payee_type and exp.payee_type.upper() == "SUPPLIER")
            )
            
            if is_service_expense:
                result['service_expenses_balance'] += amt_ils
            else:
                result['expenses_balance'] += amt_ils
        
    except Exception as e:
        from flask import current_app
        try:
            current_app.logger.error(f"خطأ في حساب مكونات رصيد العميل #{customer_id}: {e}")
        except:
            pass
        return None
    
    return result


def build_customer_balance_view(customer_id, session=None):
    if not customer_id:
        return {"success": False, "error": "customer_id is required"}
    session = session or db.session
    customer = session.get(Customer, customer_id)
    if not customer:
        return {"success": False, "error": "Customer not found"}
    components = calculate_customer_balance_components(customer_id, session)
    if not components:
        return {"success": False, "error": "Unable to calculate customer balance"}

    def _dec(value):
        return Decimal(str(value or 0))

    def _component(key):
        return _dec(components.get(key, 0))

    opening_balance = _dec(customer.opening_balance or 0)
    if customer.currency and customer.currency != "ILS":
        try:
            opening_balance = convert_amount(opening_balance, customer.currency, "ILS")
        except Exception:
            pass

    rights_rows = [
        {"key": "payments_in_balance", "label": "دفعات واردة", "flow": "IN", "amount": _component("payments_in_balance")},
        {"key": "returns_balance", "label": "مرتجعات مبيعات", "flow": "IN", "amount": _component("returns_balance")},
        {"key": "returned_checks_out_balance", "label": "شيكات صادرة مرتدة", "flow": "IN", "amount": _component("returned_checks_out_balance")},
        {"key": "service_expenses_balance", "label": "توريد خدمات لصالحه", "flow": "IN", "amount": _component("service_expenses_balance")},
    ]

    obligations_rows = [
        {"key": "sales_balance", "label": "مبيعات", "flow": "OUT", "amount": _component("sales_balance")},
        {"key": "invoices_balance", "label": "فواتير", "flow": "OUT", "amount": _component("invoices_balance")},
        {"key": "services_balance", "label": "صيانة", "flow": "OUT", "amount": _component("services_balance")},
        {"key": "preorders_balance", "label": "حجوزات مسبقة", "flow": "OUT", "amount": _component("preorders_balance")},
        {"key": "online_orders_balance", "label": "طلبات أونلاين", "flow": "OUT", "amount": _component("online_orders_balance")},
        {"key": "payments_out_balance", "label": "دفعات صادرة", "flow": "OUT", "amount": _component("payments_out_balance")},
        {"key": "returned_checks_in_balance", "label": "شيكات واردة مرتدة", "flow": "OUT", "amount": _component("returned_checks_in_balance")},
        {"key": "expenses_balance", "label": "مصاريف / خصومات", "flow": "OUT", "amount": _component("expenses_balance")},
    ]

    rights_total = sum((row["amount"] for row in rights_rows), Decimal("0.00"))
    obligations_total = sum((row["amount"] for row in obligations_rows), Decimal("0.00"))
    calculated_balance = opening_balance + rights_total - obligations_total
    stored_balance = _dec(customer.current_balance or 0)
    difference = calculated_balance - stored_balance
    tolerance = Decimal("0.01")

    def _serialize(rows):
        ordered = sorted(rows, key=lambda r: r["amount"], reverse=True)
        return [
            {
                "key": row["key"],
                "label": row["label"],
                "flow": row.get("flow"),
                "amount": float(row["amount"]),
            }
            for row in ordered
        ]

    def _direction_text(amount):
        if amount > 0:
            return "له عندنا"
        if amount < 0:
            return "عليه لنا"
        return "متوازن"

    def _action_text(amount):
        if amount > 0:
            return "يجب أن ندفع له"
        if amount < 0:
            return "يجب أن يدفع لنا"
        return "لا يوجد رصيد مستحق"

    formula = f"({float(opening_balance):.2f} + {float(rights_total):.2f} - {float(obligations_total):.2f}) = {float(calculated_balance):.2f}"

    return {
        "success": True,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "currency": customer.currency or "ILS",
        },
        "opening_balance": {
            "amount": float(opening_balance),
            "direction": _direction_text(opening_balance),
        },
        "rights": {
            "total": float(rights_total),
            "items": _serialize(rights_rows),
        },
        "obligations": {
            "total": float(obligations_total),
            "items": _serialize(obligations_rows),
        },
        "payments": {
            "received": float(_component("payments_in_balance")),
            "paid": float(_component("payments_out_balance")),
            "returned_in": float(_component("returned_checks_in_balance")),
            "returned_out": float(_component("returned_checks_out_balance")),
        },
        "checks": {
            "in_progress": float(_component("checks_in_balance")),
            "outstanding": float(_component("checks_out_balance")),
        },
        "balance": {
            "amount": float(calculated_balance),
            "direction": _direction_text(calculated_balance),
            "action": _action_text(calculated_balance),
            "formula": formula,
            "matches_stored": difference.copy_abs() <= tolerance,
            "stored": float(stored_balance),
            "difference": float(difference),
        },
        "components": {key: float(_dec(val)) for key, val in components.items()},
    }
