from decimal import Decimal
from datetime import datetime
from sqlalchemy import func, or_, and_
from extensions import db


def convert_amount(amount, from_currency, to_currency, date=None):
    from models import convert_amount as _convert_amount
    return _convert_amount(amount, from_currency, to_currency, date)


def calculate_partner_balance_components(partner_id, session=None):
    if not partner_id:
        return None
    
    from models import Partner
    from sqlalchemy.orm import Session, sessionmaker
    
    use_new_session = False
    if not session:
        try:
            session = db.session
            try:
                session.execute(db.text("SELECT 1"))
            except Exception as e:
                error_str = str(e).lower()
                if "committed" in error_str or "closed" in error_str or "no further sql" in error_str:
                    session = sessionmaker(bind=db.engine)()
                    use_new_session = True
                else:
                    raise
        except Exception as e:
            error_str = str(e).lower()
            if "committed" in error_str or "closed" in error_str or "no further sql" in error_str:
                session = sessionmaker(bind=db.engine)()
                use_new_session = True
            else:
                raise
    elif isinstance(session, Session):
        try:
            try:
                session.execute(db.text("SELECT 1"))
            except Exception as e:
                error_str = str(e).lower()
                if "committed" in error_str or "closed" in error_str or "no further sql" in error_str:
                    session = sessionmaker(bind=db.engine)()
                    use_new_session = True
                else:
                    raise
        except Exception as e:
            error_str = str(e).lower()
            if "committed" in error_str or "closed" in error_str or "no further sql" in error_str:
                session = sessionmaker(bind=db.engine)()
                use_new_session = True
            else:
                raise
    
    try:
        partner = session.get(Partner, partner_id)
        if not partner:
            if use_new_session:
                try:
                    session.close()
                except:
                    pass
            return None
    except Exception as e:
        if use_new_session:
            try:
                session.close()
            except:
                pass
        return None
    
    result = {
        'inventory_balance': Decimal('0.00'),
        'sales_share_balance': Decimal('0.00'),
        'sales_to_partner_balance': Decimal('0.00'),
        'service_fees_balance': Decimal('0.00'),
        'preorders_to_partner_balance': Decimal('0.00'),
        'preorders_prepaid_balance': Decimal('0.00'),
        'damaged_items_balance': Decimal('0.00'),
        'payments_in_balance': Decimal('0.00'),
        'payments_out_balance': Decimal('0.00'),
        'returned_checks_in_balance': Decimal('0.00'),
        'returned_checks_out_balance': Decimal('0.00'),
        'expenses_balance': Decimal('0.00'),
        'service_expenses_balance': Decimal('0.00'),
    }
    
    try:
        from routes.partner_settlements import (
            _get_partner_inventory,
            _get_partner_sales_share,
            _get_partner_sales_returns,
            _get_partner_payments_received,
            _get_partner_preorders_prepaid,
            _get_payments_to_partner,
            _get_partner_sales_as_customer,
            _get_partner_service_fees,
            _get_partner_preorders_as_customer,
            _get_partner_damaged_items,
            _get_partner_expenses,
            _get_returned_checks_from_partner,
            _get_returned_checks_to_partner
        )
        from models import Expense, ExpenseType
        
        date_from = datetime(2024, 1, 1)
        date_to = datetime.utcnow()
        
        inventory = _get_partner_inventory(partner_id, date_from, date_to)
        if isinstance(inventory, dict):
            result['inventory_balance'] = Decimal(str(inventory.get("total_ils", 0) or 0))
        
        sales_share = _get_partner_sales_share(partner_id, date_from, date_to)
        sales_share_total = Decimal('0.00')
        if isinstance(sales_share, dict):
            sales_share_total = Decimal(str(sales_share.get("total_share_ils", 0) or 0))
        
        sales_returns = _get_partner_sales_returns(partner_id, date_from, date_to)
        sales_returns_total = Decimal('0.00')
        if isinstance(sales_returns, dict):
            sales_returns_total = Decimal(str(sales_returns.get("total_return_share_ils", 0) or 0))
        
        result['sales_share_balance'] = sales_share_total - sales_returns_total
        
        payments_from_partner = _get_partner_payments_received(partner_id, partner, date_from, date_to)
        payments_in_total = Decimal('0.00')
        if isinstance(payments_from_partner, dict):
            payments_in_total = Decimal(str(payments_from_partner.get("total_ils", 0) or 0))
        
        preorders_prepaid = _get_partner_preorders_prepaid(partner_id, partner, date_from, date_to)
        preorders_prepaid_total = Decimal('0.00')
        if isinstance(preorders_prepaid, dict):
            preorders_prepaid_total = Decimal(str(preorders_prepaid.get("total_ils", 0) or 0))
        
        result['payments_in_balance'] = payments_in_total + preorders_prepaid_total
        result['preorders_prepaid_balance'] = preorders_prepaid_total
        
        payments_to_partner = _get_payments_to_partner(partner_id, partner, date_from, date_to)
        if isinstance(payments_to_partner, dict):
            result['payments_out_balance'] = Decimal(str(payments_to_partner.get("total_ils", 0) or 0))
        
        sales_to_partner = _get_partner_sales_as_customer(partner_id, partner, date_from, date_to)
        if isinstance(sales_to_partner, dict):
            result['sales_to_partner_balance'] = Decimal(str(sales_to_partner.get("total_ils", 0) or 0))
        
        service_fees = _get_partner_service_fees(partner_id, partner, date_from, date_to)
        if isinstance(service_fees, dict):
            result['service_fees_balance'] = Decimal(str(service_fees.get("total_ils", 0) or 0))
        
        preorders_to_partner = _get_partner_preorders_as_customer(partner_id, partner, date_from, date_to)
        if isinstance(preorders_to_partner, dict):
            result['preorders_to_partner_balance'] = Decimal(str(preorders_to_partner.get("total_ils", 0) or 0))
        
        damaged_items = _get_partner_damaged_items(partner_id, date_from, date_to)
        if isinstance(damaged_items, dict):
            result['damaged_items_balance'] = Decimal(str(damaged_items.get("total_ils", 0) or 0))
        
        expenses_deducted = _get_partner_expenses(partner_id, date_from, date_to)
        result['expenses_balance'] = Decimal(str(expenses_deducted or 0))
        
        from models import Check, CheckStatus, PaymentDirection
        manual_checks_in = session.query(Check).filter(
            Check.partner_id == partner_id,
            Check.payment_id.is_(None),
            Check.direction == PaymentDirection.IN,
            ~Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED, CheckStatus.CANCELLED, CheckStatus.ARCHIVED])
        ).all()
        
        for check in manual_checks_in:
            amt = Decimal(str(check.amount or 0))
            if check.currency != "ILS":
                try:
                    amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                except Exception:
                    pass
            result['payments_in_balance'] += amt
        
        manual_checks_out = session.query(Check).filter(
            Check.partner_id == partner_id,
            Check.payment_id.is_(None),
            Check.direction == PaymentDirection.OUT,
            ~Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED, CheckStatus.CANCELLED, CheckStatus.ARCHIVED])
        ).all()
        
        for check in manual_checks_out:
            amt = Decimal(str(check.amount or 0))
            if check.currency != "ILS":
                try:
                    amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                except Exception:
                    pass
            result['payments_out_balance'] += amt
        
        manual_returned_checks_in = session.query(Check).filter(
            Check.partner_id == partner_id,
            Check.payment_id.is_(None),
            Check.direction == PaymentDirection.IN,
            Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED])
        ).all()
        
        for check in manual_returned_checks_in:
            amt = Decimal(str(check.amount or 0))
            if check.currency != "ILS":
                try:
                    amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                except Exception:
                    pass
            result['returned_checks_in_balance'] += amt
        
        manual_returned_checks_out = session.query(Check).filter(
            Check.partner_id == partner_id,
            Check.payment_id.is_(None),
            Check.direction == PaymentDirection.OUT,
            Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED])
        ).all()
        
        for check in manual_returned_checks_out:
            amt = Decimal(str(check.amount or 0))
            if check.currency != "ILS":
                try:
                    amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                except Exception:
                    pass
            result['returned_checks_out_balance'] += amt
        
        if partner.customer_id:
            customer_manual_checks_in = session.query(Check).filter(
                Check.customer_id == partner.customer_id,
                Check.payment_id.is_(None),
                Check.direction == PaymentDirection.IN,
                ~Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED, CheckStatus.CANCELLED, CheckStatus.ARCHIVED])
            ).all()
            
            for check in customer_manual_checks_in:
                amt = Decimal(str(check.amount or 0))
                if check.currency != "ILS":
                    try:
                        amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                    except Exception:
                        pass
                result['payments_in_balance'] += amt
            
            customer_manual_checks_out = session.query(Check).filter(
                Check.customer_id == partner.customer_id,
                Check.payment_id.is_(None),
                Check.direction == PaymentDirection.OUT,
                ~Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED, CheckStatus.CANCELLED, CheckStatus.ARCHIVED])
            ).all()
            
            for check in customer_manual_checks_out:
                amt = Decimal(str(check.amount or 0))
                if check.currency != "ILS":
                    try:
                        amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                    except Exception:
                        pass
                result['payments_out_balance'] += amt
            
            customer_manual_returned_checks_in = session.query(Check).filter(
                Check.customer_id == partner.customer_id,
                Check.payment_id.is_(None),
                Check.direction == PaymentDirection.IN,
                Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED])
            ).all()
            
            for check in customer_manual_returned_checks_in:
                amt = Decimal(str(check.amount or 0))
                if check.currency != "ILS":
                    try:
                        amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                    except Exception:
                        pass
                result['returned_checks_in_balance'] += amt
            
            customer_manual_returned_checks_out = session.query(Check).filter(
                Check.customer_id == partner.customer_id,
                Check.payment_id.is_(None),
                Check.direction == PaymentDirection.OUT,
                Check.status.in_([CheckStatus.RETURNED, CheckStatus.BOUNCED])
            ).all()
            
            for check in customer_manual_returned_checks_out:
                amt = Decimal(str(check.amount or 0))
                if check.currency != "ILS":
                    try:
                        amt = convert_amount(amt, check.currency, "ILS", check.check_date or datetime.utcnow())
                    except Exception:
                        pass
                result['returned_checks_out_balance'] += amt
        
        returned_checks_in = _get_returned_checks_from_partner(partner_id, partner, date_from, date_to)
        if isinstance(returned_checks_in, dict):
            result['returned_checks_in_balance'] = Decimal(str(returned_checks_in.get("total_ils", 0) or 0))
        
        returned_checks_out = _get_returned_checks_to_partner(partner_id, partner, date_from, date_to)
        if isinstance(returned_checks_out, dict):
            result['returned_checks_out_balance'] = Decimal(str(returned_checks_out.get("total_ils", 0) or 0))
        
        from sqlalchemy import func
        expenses_to_partner = session.query(Expense).join(ExpenseType).filter(
            or_(
                Expense.partner_id == partner_id,
                and_(Expense.payee_type == "PARTNER", Expense.payee_entity_id == partner_id)
            ),
            func.upper(ExpenseType.code) == "PARTNER_EXPENSE"
        ).all()
        
        partner_service_total = Decimal('0.00')
        for exp in expenses_to_partner:
            amt = Decimal(str(exp.amount or 0))
            if exp.currency == "ILS":
                partner_service_total += amt
            else:
                try:
                    amt_ils = convert_amount(amt, exp.currency, "ILS", exp.date)
                    partner_service_total += amt_ils
                except Exception:
                    pass
        
        result['service_expenses_balance'] = partner_service_total
        
    except Exception as e:
        from flask import current_app
        try:
            current_app.logger.error(f"خطأ في حساب مكونات رصيد الشريك #{partner_id}: {e}")
        except:
            pass
        return None
    finally:
        if use_new_session:
            try:
                session.close()
            except:
                pass
    
    return result

