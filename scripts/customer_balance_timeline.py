from datetime import datetime
from decimal import Decimal
import json
import sys
from app import app
from extensions import db
from sqlalchemy import func, or_, and_, cast, String, exists
from models import (
    Customer, Sale, SaleReturn, Invoice, ServiceRequest, PreOrder, OnlinePreOrder,
    Payment, PaymentSplit, Check, PaymentDirection, PaymentStatus, PaymentMethod, Expense, ExpenseType, convert_amount
)

def to_ils(amount, currency, date=None):
    amt = Decimal(str(amount or 0))
    cur = (currency or 'ILS')
    if cur == 'ILS':
        return amt
    try:
        return Decimal(str(convert_amount(amt, cur, 'ILS', date)))
    except Exception:
        return amt

def service_total_ils(srv):
    subtotal = Decimal(str(srv.parts_total or 0)) + Decimal(str(srv.labor_total or 0))
    discount = Decimal(str(srv.discount_total or 0))
    base = subtotal - discount
    if base < 0:
        base = Decimal('0.00')
    tax_rate = Decimal(str(srv.tax_rate or 0))
    tax = base * (tax_rate / Decimal('100'))
    total = base + tax
    return to_ils(total, getattr(srv, 'currency', 'ILS'), getattr(srv, 'received_at', None))

def main():
    name_target = sys.argv[1] if len(sys.argv) > 1 else 'تجريبي 26-11-2025'
    with app.app_context():
        cust = db.session.query(Customer).filter(Customer.name == name_target).first()
        if not cust:
            cust = db.session.query(Customer).filter(Customer.name.ilike('%'+name_target+'%')).first()
        if not cust:
            print(json.dumps({"error":"customer_not_found","name":name_target}, ensure_ascii=False))
            return
        cid = cust.id
        events = []
        ob = Decimal(str(cust.opening_balance or 0))
        ob_ils = to_ils(ob, cust.currency, None)
        events.append({"ts": cust.created_at.isoformat() if cust.created_at else None, "type":"opening_balance", "label":"رصيد افتتاحي", "flow":"IN" if ob_ils>0 else ("OUT" if ob_ils<0 else "ZERO"), "amount": float(ob_ils)})
        for s in db.session.query(Sale).filter(Sale.customer_id==cid, Sale.status=='CONFIRMED').all():
            amt = to_ils(s.total_amount, s.currency, s.sale_date)
            events.append({"ts": (s.sale_date.isoformat() if s.sale_date else s.created_at.isoformat() if s.created_at else None), "type":"sale", "label":"مبيعات", "flow":"OUT", "amount": float(amt), "id": s.id})
        for r in db.session.query(SaleReturn).filter(SaleReturn.customer_id==cid, SaleReturn.status=='CONFIRMED').all():
            amt = to_ils(r.total_amount, r.currency, r.created_at)
            events.append({"ts": (r.created_at.isoformat() if r.created_at else None), "type":"sale_return", "label":"مرتجع مبيعات", "flow":"IN", "amount": float(amt), "id": r.id})
        for inv in db.session.query(Invoice).filter(Invoice.customer_id==cid, Invoice.cancelled_at.is_(None)).all():
            amt = to_ils(inv.total_amount, inv.currency, inv.invoice_date)
            events.append({"ts": (inv.invoice_date.isoformat() if inv.invoice_date else inv.created_at.isoformat() if inv.created_at else None), "type":"invoice", "label":"فاتورة", "flow":"OUT", "amount": float(amt), "id": inv.id})
        for srv in db.session.query(ServiceRequest).filter(ServiceRequest.customer_id==cid).all():
            amt = service_total_ils(srv)
            events.append({"ts": (srv.received_at.isoformat() if srv.received_at else srv.created_at.isoformat() if srv.created_at else None), "type":"service", "label":"صيانة", "flow":"OUT", "amount": float(amt), "id": srv.id})
        for oo in db.session.query(OnlinePreOrder).filter(OnlinePreOrder.customer_id==cid, OnlinePreOrder.payment_status!='CANCELLED').all():
            amt = to_ils(oo.total_amount, oo.currency, oo.created_at)
            events.append({"ts": (oo.created_at.isoformat() if oo.created_at else None), "type":"online_preorder", "label":"طلب أونلاين", "flow":"OUT", "amount": float(amt), "id": oo.id})
        payments_in_qs = []
        payments_in_qs.extend(db.session.query(Payment).outerjoin(Check, Check.payment_id==Payment.id).outerjoin(PreOrder, Payment.preorder_id==PreOrder.id).filter(Payment.customer_id==cid, Payment.direction=='IN', Payment.status.in_(['COMPLETED','PENDING']), or_(Payment.preorder_id.is_(None), Payment.sale_id.isnot(None), PreOrder.status=='FULFILLED')).all())
        payments_in_qs.extend(db.session.query(Payment).join(Sale, Payment.sale_id==Sale.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Sale.customer_id==cid, Payment.direction=='IN', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_in_qs.extend(db.session.query(Payment).join(Invoice, Payment.invoice_id==Invoice.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Invoice.customer_id==cid, Payment.direction=='IN', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_in_qs.extend(db.session.query(Payment).join(ServiceRequest, Payment.service_id==ServiceRequest.id).outerjoin(Check, Check.payment_id==Payment.id).filter(ServiceRequest.customer_id==cid, Payment.direction=='IN', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_in_qs.extend(db.session.query(Payment).join(PreOrder, Payment.preorder_id==PreOrder.id).outerjoin(Check, Check.payment_id==Payment.id).filter(PreOrder.customer_id==cid, Payment.direction=='IN', Payment.status.in_(['COMPLETED','PENDING']), or_(PreOrder.status=='FULFILLED', Payment.sale_id.isnot(None))).all())
        seen_ids=set(); payments_in=[]
        for p in payments_in_qs:
            if p.id in seen_ids: continue
            seen_ids.add(p.id)
            splits = db.session.query(PaymentSplit).filter(PaymentSplit.payment_id==p.id).all()
            if splits:
                total_splits = Decimal('0.00')
                for split in splits:
                    split_amt = Decimal(str(split.amount or 0))
                    split_conv_amt = Decimal(str(getattr(split,'converted_amount',0) or 0))
                    split_conv_cur = (getattr(split,'converted_currency',None) or split.currency or 'ILS').upper()
                    if split_conv_amt>0 and split_conv_cur=='ILS':
                        total_splits += split_conv_amt
                    elif (split.currency or 'ILS')=='ILS':
                        total_splits += split_amt
                    else:
                        total_splits += to_ils(split_amt, split.currency, p.payment_date)
                amt = total_splits
            else:
                amt = Decimal(str(p.total_amount or 0))
                amt = to_ils(amt, p.currency, p.payment_date)
            payments_in.append((p, amt))
        for p, amt in payments_in:
            events.append({"ts": (p.payment_date.isoformat() if p.payment_date else p.created_at.isoformat() if p.created_at else None), "type":"payment_in", "label":"دفعة واردة", "flow":"IN", "amount": float(amt), "id": p.id, "status": getattr(getattr(p,'status',None),'value', getattr(p,'status',None))})
        for chk in db.session.query(Check).filter(Check.customer_id==cid, Check.payment_id.is_(None), Check.direction=='IN', ~Check.status.in_(['RETURNED','BOUNCED','CANCELLED','ARCHIVED'])).all():
            amt = to_ils(chk.amount, chk.currency, chk.check_date)
            events.append({"ts": (chk.check_date.isoformat() if chk.check_date else chk.created_at.isoformat() if chk.created_at else None), "type":"manual_check_in", "label":"شيك وارد معلق", "flow":"IN", "amount": float(amt), "id": chk.id, "status": str(chk.status)})
        payments_out_qs = []
        payments_out_qs.extend(db.session.query(Payment).outerjoin(Check, Check.payment_id==Payment.id).filter(Payment.customer_id==cid, Payment.direction=='OUT', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_out_qs.extend(db.session.query(Payment).join(Sale, Payment.sale_id==Sale.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Sale.customer_id==cid, Payment.direction=='OUT', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_out_qs.extend(db.session.query(Payment).join(Invoice, Payment.invoice_id==Invoice.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Invoice.customer_id==cid, Payment.direction=='OUT', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_out_qs.extend(db.session.query(Payment).join(ServiceRequest, Payment.service_id==ServiceRequest.id).outerjoin(Check, Check.payment_id==Payment.id).filter(ServiceRequest.customer_id==cid, Payment.direction=='OUT', Payment.status.in_(['COMPLETED','PENDING'])).all())
        payments_out_qs.extend(db.session.query(Payment).join(PreOrder, Payment.preorder_id==PreOrder.id).outerjoin(Check, Check.payment_id==Payment.id).filter(PreOrder.customer_id==cid, Payment.direction=='OUT', Payment.status.in_(['COMPLETED','PENDING'])).all())
        seen_o=set(); payments_out=[]
        for p in payments_out_qs:
            if p.id in seen_o: continue
            seen_o.add(p.id)
            splits = db.session.query(PaymentSplit).filter(PaymentSplit.payment_id==p.id).all()
            if splits:
                total_splits = Decimal('0.00')
                for split in splits:
                    split_amt = Decimal(str(split.amount or 0))
                    split_conv_amt = Decimal(str(getattr(split,'converted_amount',0) or 0))
                    split_conv_cur = (getattr(split,'converted_currency',None) or split.currency or 'ILS').upper()
                    if split_conv_amt>0 and split_conv_cur=='ILS':
                        total_splits += split_conv_amt
                    elif (split.currency or 'ILS')=='ILS':
                        total_splits += split_amt
                    else:
                        total_splits += to_ils(split_amt, split.currency, p.payment_date)
                amt = total_splits
            else:
                amt = Decimal(str(p.total_amount or 0))
                amt = to_ils(amt, p.currency, p.payment_date)
            payments_out.append((p, amt))
        for p, amt in payments_out:
            events.append({"ts": (p.payment_date.isoformat() if p.payment_date else p.created_at.isoformat() if p.created_at else None), "type":"payment_out", "label":"دفعة صادرة", "flow":"OUT", "amount": float(amt), "id": p.id, "status": getattr(getattr(p,'status',None),'value', getattr(p,'status',None))})
        for chk in db.session.query(Check).filter(Check.customer_id==cid, Check.payment_id.is_(None), Check.direction=='OUT', ~Check.status.in_(['RETURNED','BOUNCED','CANCELLED','ARCHIVED'])).all():
            amt = to_ils(chk.amount, chk.currency, chk.check_date)
            events.append({"ts": (chk.check_date.isoformat() if chk.check_date else chk.created_at.isoformat() if chk.created_at else None), "type":"manual_check_out", "label":"شيك صادر معلق", "flow":"OUT", "amount": float(amt), "id": chk.id, "status": str(chk.status)})
        returned_in_sets = []
        returned_in_sets.extend(db.session.query(Payment).outerjoin(Check, Check.payment_id==Payment.id).filter(Payment.customer_id==cid, Payment.direction=='IN', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_in_sets.extend(db.session.query(Payment).join(Sale, Payment.sale_id==Sale.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Sale.customer_id==cid, Payment.direction=='IN', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_in_sets.extend(db.session.query(Payment).join(Invoice, Payment.invoice_id==Invoice.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Invoice.customer_id==cid, Payment.direction=='IN', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_in_sets.extend(db.session.query(Payment).join(ServiceRequest, Payment.service_id==ServiceRequest.id).outerjoin(Check, Check.payment_id==Payment.id).filter(ServiceRequest.customer_id==cid, Payment.direction=='IN', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_in_sets.extend(db.session.query(Payment).join(PreOrder, Payment.preorder_id==PreOrder.id).outerjoin(Check, Check.payment_id==Payment.id).filter(PreOrder.customer_id==cid, Payment.direction=='IN', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_in_sets.extend(db.session.query(Payment).join(PaymentSplit, PaymentSplit.payment_id==Payment.id).filter(Payment.customer_id==cid, Payment.direction=='IN', or_(cast(PaymentSplit.method, String).like('%CHECK%'), cast(PaymentSplit.method, String).like('%CHEQUE%'), PaymentSplit.method==PaymentMethod.CHEQUE.value), exists().where(and_(Check.reference_number==func.concat('PMT-SPLIT-', PaymentSplit.id), Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED'))).all())
        seen_ret_in=set()
        for p in returned_in_sets:
            if p.id in seen_ret_in: continue
            seen_ret_in.add(p.id)
            splits = db.session.query(PaymentSplit).filter(PaymentSplit.payment_id==p.id).all()
            added=False
            if splits:
                for split in splits:
                    is_cheque_split = (getattr(split,'method',None)==PaymentMethod.CHEQUE.value) or (getattr(split,'method',None)==PaymentMethod.CHEQUE) or ('CHEQUE' in str(split.method).upper() or 'CHECK' in str(split.method).upper())
                    if is_cheque_split:
                        split_checks = db.session.query(Check).filter(Check.reference_number==f"PMT-SPLIT-{split.id}", Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED').all()
                        for check in split_checks:
                            amt = to_ils(check.amount, (check.currency or split.currency or p.currency or 'ILS'), check.check_date if check else p.payment_date)
                            events.append({"ts": (check.check_date.isoformat() if check.check_date else p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_in", "label":"شيك وارد مرتجع", "flow":"OUT", "amount": float(amt), "id": check.id, "payment_id": p.id})
                            added=True
                if not added:
                    for split in splits:
                        det = split.details or {}
                        if isinstance(det,str):
                            try:
                                import json as _json
                                det=_json.loads(det)
                            except:
                                det={}
                        st = (det.get('check_status','') or '').upper()
                        if st in ['RETURNED','BOUNCED']:
                            amt = to_ils(split.amount, (split.currency or p.currency or 'ILS'), p.payment_date)
                            events.append({"ts": (p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_in", "label":"Split مرتجع", "flow":"OUT", "amount": float(amt), "id": f"split-{split.id}", "payment_id": p.id})
            else:
                returned_checks = db.session.query(Check).filter(Check.payment_id==p.id, Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED').all()
                for check in returned_checks:
                    amt = to_ils(check.amount, (check.currency or p.currency or 'ILS'), check.check_date if check else p.payment_date)
                    events.append({"ts": (check.check_date.isoformat() if check.check_date else p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_in", "label":"شيك وارد مرتجع", "flow":"OUT", "amount": float(amt), "id": check.id, "payment_id": p.id})
                if not returned_checks and p.status=='FAILED' and getattr(p,'method',None)==PaymentMethod.CHEQUE.value:
                    amt = to_ils(p.total_amount, p.currency, p.payment_date)
                    events.append({"ts": (p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_in", "label":"دفعة شيك فاشلة", "flow":"OUT", "amount": float(amt), "id": f"payment-{p.id}", "payment_id": p.id})
        returned_out_sets = []
        returned_out_sets.extend(db.session.query(Payment).outerjoin(Check, Check.payment_id==Payment.id).filter(Payment.customer_id==cid, Payment.direction=='OUT', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_out_sets.extend(db.session.query(Payment).join(Sale, Payment.sale_id==Sale.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Sale.customer_id==cid, Payment.direction=='OUT', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_out_sets.extend(db.session.query(Payment).join(Invoice, Payment.invoice_id==Invoice.id).outerjoin(Check, Check.payment_id==Payment.id).filter(Invoice.customer_id==cid, Payment.direction=='OUT', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_out_sets.extend(db.session.query(Payment).join(ServiceRequest, Payment.service_id==ServiceRequest.id).outerjoin(Check, Check.payment_id==Payment.id).filter(ServiceRequest.customer_id==cid, Payment.direction=='OUT', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_out_sets.extend(db.session.query(Payment).join(PreOrder, Payment.preorder_id==PreOrder.id).outerjoin(Check, Check.payment_id==Payment.id).filter(PreOrder.customer_id==cid, Payment.direction=='OUT', or_(Check.status.in_(['RETURNED','BOUNCED']), and_(Payment.status=='FAILED', Payment.method==PaymentMethod.CHEQUE.value))).all())
        returned_out_sets.extend(db.session.query(Payment).join(PaymentSplit, PaymentSplit.payment_id==Payment.id).filter(Payment.customer_id==cid, Payment.direction=='OUT', or_(cast(PaymentSplit.method, String).like('%CHECK%'), cast(PaymentSplit.method, String).like('%CHEQUE%'), PaymentSplit.method==PaymentMethod.CHEQUE.value), exists().where(and_(Check.reference_number==func.concat('PMT-SPLIT-', PaymentSplit.id), Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED'))).all())
        seen_ret_out=set()
        for p in returned_out_sets:
            if p.id in seen_ret_out: continue
            seen_ret_out.add(p.id)
            splits = db.session.query(PaymentSplit).filter(PaymentSplit.payment_id==p.id).all()
            added=False
            if splits:
                for split in splits:
                    is_cheque_split = (getattr(split,'method',None)==PaymentMethod.CHEQUE.value) or (getattr(split,'method',None)==PaymentMethod.CHEQUE) or ('CHEQUE' in str(split.method).upper() or 'CHECK' in str(split.method).upper())
                    if is_cheque_split:
                        split_checks = db.session.query(Check).filter(Check.reference_number==f"PMT-SPLIT-{split.id}", Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED').all()
                        for check in split_checks:
                            amt = to_ils(check.amount, (check.currency or split.currency or p.currency or 'ILS'), check.check_date if check else p.payment_date)
                            events.append({"ts": (check.check_date.isoformat() if check.check_date else p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_out", "label":"شيك صادر مرتجع", "flow":"IN", "amount": float(amt), "id": check.id, "payment_id": p.id})
                            added=True
                if not added:
                    for split in splits:
                        det = split.details or {}
                        if isinstance(det,str):
                            try:
                                import json as _json
                                det=_json.loads(det)
                            except:
                                det={}
                        st = (det.get('check_status','') or '').upper()
                        if st in ['RETURNED','BOUNCED']:
                            amt = to_ils(split.amount, (split.currency or p.currency or 'ILS'), p.payment_date)
                            events.append({"ts": (p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_out", "label":"Split مرتجع", "flow":"IN", "amount": float(amt), "id": f"split-{split.id}", "payment_id": p.id})
            else:
                returned_checks = db.session.query(Check).filter(Check.payment_id==p.id, Check.status.in_(['RETURNED','BOUNCED']), Check.status!='CANCELLED').all()
                for check in returned_checks:
                    amt = to_ils(check.amount, (check.currency or p.currency or 'ILS'), check.check_date if check else p.payment_date)
                    events.append({"ts": (check.check_date.isoformat() if check.check_date else p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_out", "label":"شيك صادر مرتجع", "flow":"IN", "amount": float(amt), "id": check.id, "payment_id": p.id})
                if not returned_checks and p.status=='FAILED' and getattr(p,'method',None)==PaymentMethod.CHEQUE.value:
                    amt = to_ils(p.total_amount, p.currency, p.payment_date)
                    events.append({"ts": (p.payment_date.isoformat() if p.payment_date else None), "type":"returned_check_out", "label":"دفعة شيك فاشلة", "flow":"IN", "amount": float(amt), "id": f"payment-{p.id}", "payment_id": p.id})
        for exp in db.session.query(Expense).filter(Expense.customer_id==cid).all():
            amt_ils = to_ils(exp.amount, exp.currency, exp.date)
            exp_type_code = None
            if exp.type_id:
                et = db.session.query(ExpenseType).filter_by(id=exp.type_id).first()
                exp_type_code = (et.code or '').strip().upper() if et else None
            is_service_expense = (
                exp_type_code in ('PARTNER_EXPENSE','SERVICE_EXPENSE') or
                (exp.partner_id and exp.payee_type and exp.payee_type.upper()=='PARTNER') or
                (exp.supplier_id and exp.payee_type and exp.payee_type.upper()=='SUPPLIER')
            )
            events.append({"ts": (exp.date.isoformat() if exp.date else exp.created_at.isoformat() if exp.created_at else None), "type":("service_expense" if is_service_expense else "expense"), "label":("توريد خدمات" if is_service_expense else "مصروف/خصم"), "flow":("IN" if is_service_expense else "OUT"), "amount": float(amt_ils), "id": exp.id})
        def _ts(e):
            t = e.get('ts')
            try:
                return datetime.fromisoformat(t.replace('Z','')) if t else datetime.min
            except Exception:
                return datetime.min
        events = sorted(events, key=_ts)
        running = float(ob_ils)
        rights_sum = 0.0
        obligations_sum = 0.0
        by_type = {}
        for e in events[1:]:
            t = e.get('type')
            by_type.setdefault(t, {'IN': 0.0, 'OUT': 0.0, 'count': 0})
            by_type[t][e['flow']] = by_type[t].get(e['flow'], 0.0) + e['amount']
            by_type[t]['count'] += 1
            if e['flow']=='IN':
                rights_sum += e['amount']
                running += e['amount']
            elif e['flow']=='OUT':
                obligations_sum += e['amount']
                running -= e['amount']
        out = {
            "customer": {"id": cid, "name": cust.name, "currency": cust.currency or 'ILS'},
            "opening_balance_ils": float(ob_ils),
            "stored_balance": float(Decimal(str(cust.current_balance or 0))),
            "calculated_balance": running,
            "difference": running - float(Decimal(str(cust.current_balance or 0))),
            "events": events,
            "rights_sum": rights_sum,
            "obligations_sum": obligations_sum,
            "by_type": by_type
        }
        print(f"opening_balance_ils={out['opening_balance_ils']}")
        print(f"stored_balance={out['stored_balance']}")
        print(f"calculated_balance={out['calculated_balance']}")
        print(f"difference={out['difference']}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(json.dumps({"__summary__": {
            "opening_balance_ils": out['opening_balance_ils'],
            "stored_balance": out['stored_balance'],
            "calculated_balance": out['calculated_balance'],
            "difference": out['difference']
        }}, ensure_ascii=False))

if __name__ == '__main__':
    main()
