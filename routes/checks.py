from dataclasses import dataclass, field
from typing import Optional
import logging

from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import current_user, login_required
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import and_, or_, desc, func, select
from sqlalchemy.orm import joinedload, sessionmaker
from extensions import db
try:
    from extensions import limiter
except ImportError:
    limiter = None
from models import (
    Payment, PaymentSplit, Expense, PaymentMethod, PaymentStatus, PaymentDirection, 
    Check, CheckStatus, Customer, Supplier, Partner, GLBatch, GLEntry, Account,
    _ALLOWED_TRANSITIONS,
)
import utils
from decimal import Decimal
import json
import uuid

checks_bp = Blueprint('checks', __name__, url_prefix='/checks')


from sqlalchemy import event


class CheckException(Exception):
    def __init__(self, message, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class CheckValidationError(CheckException):
    pass


class CheckAccountingError(CheckException):
    pass


class CheckStateError(CheckException):
    pass


class PaymentStatusSyncService:
    @staticmethod
    def sync_payment_status_from_check(check, connection):
        from sqlalchemy import text as sa_text
        from models import PaymentMethod, PaymentStatus
        
        payment_id = getattr(check, 'payment_id', None)
        if not payment_id:
            return None
        
        check_status = str(getattr(check, 'status', '')).upper()
        
        payment_query = connection.execute(
            sa_text("SELECT id, status, total_amount FROM payments WHERE id = :payment_id"),
            {"payment_id": payment_id}
        ).fetchone()
        
        if not payment_query:
            return None
        
        payment_status = payment_query[1] or 'PENDING'
        
        payment_notes_query = connection.execute(
            sa_text("SELECT notes FROM payments WHERE id = :payment_id"),
            {"payment_id": payment_id}
        ).fetchone()
        payment_notes = payment_notes_query[0] if payment_notes_query else ''
        is_settled = '[SETTLED=true]' in (payment_notes or '').upper()
        
        splits_query = connection.execute(
            sa_text("""
                SELECT ps.id, ps.method, ps.amount 
                FROM payment_splits ps 
                WHERE ps.payment_id = :payment_id
            """),
            {"payment_id": payment_id}
        ).fetchall()
        
        has_splits = len(splits_query) > 0
        
        new_payment_status = None
        
        if has_splits:
            cheque_method = PaymentMethod.CHEQUE.value
            cheque_splits = [s for s in splits_query if str(s[1]).upper() == str(cheque_method).upper()]
            non_cheque_splits = [s for s in splits_query if str(s[1]).upper() != str(cheque_method).upper()]
            
            new_payment_status = PaymentStatusSyncService._calculate_status_with_splits(
                check, check_status, cheque_splits, non_cheque_splits, is_settled, connection
            )
        else:
            new_payment_status = PaymentStatusSyncService._calculate_status_without_splits(check_status)
        
        if new_payment_status and new_payment_status != payment_status:
            from flask import current_app
            current_app.logger.info(f"✅ تمت مزامنة حالة الدفعة #{payment_id} مع الشيك #{getattr(check, 'id', '?')} - {check_status} → {new_payment_status}")
            return new_payment_status
        
        return None
    
    @staticmethod
    def _calculate_status_with_splits(check, check_status, cheque_splits, non_cheque_splits, is_settled, connection):
        from sqlalchemy import text as sa_text
        from models import PaymentMethod, PaymentStatus
        
        if check_status in ['RETURNED', 'BOUNCED']:
            if is_settled:
                if len(non_cheque_splits) > 0:
                    return PaymentStatus.COMPLETED.value
                else:
                    all_cheque_splits_settled = True
                    for split in cheque_splits:
                        split_check = connection.execute(
                            sa_text("""
                                SELECT c.status, p.notes 
                                FROM checks c
                                JOIN payments p ON c.payment_id = p.id
                                WHERE c.reference_number LIKE :ref_pattern
                            """),
                            {"ref_pattern": f"PMT-SPLIT-{split[0]}-%"}
                        ).fetchone()
                        
                        if split_check:
                            split_status = split_check[0]
                            split_payment_notes = split_check[1] if len(split_check) > 1 else ''
                            split_is_settled = '[SETTLED=true]' in (split_payment_notes or '').upper()
                            
                            if split_status in ['RETURNED', 'BOUNCED'] and not split_is_settled:
                                all_cheque_splits_settled = False
                                break
                    
                    if all_cheque_splits_settled:
                        return PaymentStatus.COMPLETED.value
                    else:
                        return None
            else:
                check_reference = getattr(check, 'reference_number', '') or ''
                is_split_check = 'PMT-SPLIT-' in check_reference
                
                if is_split_check:
                    try:
                        split_id_str = check_reference.split('PMT-SPLIT-')[1].split('-')[0]
                        split_id = int(split_id_str)
                        
                        affected_split = next((s for s in cheque_splits if s[0] == split_id), None)
                        
                        if affected_split:
                            if len(non_cheque_splits) > 0:
                                return PaymentStatus.COMPLETED.value
                            else:
                                all_cheque_splits_returned = True
                                for split in cheque_splits:
                                    split_check = connection.execute(
                                        sa_text("""
                                            SELECT status FROM checks 
                                            WHERE reference_number LIKE :ref_pattern
                                        """),
                                        {"ref_pattern": f"PMT-SPLIT-{split[0]}-%"}
                                    ).fetchone()
                                    
                                    if not split_check or split_check[0] not in ['RETURNED', 'BOUNCED']:
                                        all_cheque_splits_returned = False
                                        break
                                
                                if all_cheque_splits_returned:
                                    return PaymentStatus.FAILED.value
                                else:
                                    return PaymentStatus.COMPLETED.value
                        else:
                            return None
                    except (ValueError, IndexError):
                        return None
                else:
                    if len(non_cheque_splits) > 0:
                        return PaymentStatus.COMPLETED.value
                    elif len(cheque_splits) == 1:
                        return PaymentStatus.FAILED.value
                    else:
                        return None
        
        elif check_status == 'RESUBMITTED':
            check_reference = getattr(check, 'reference_number', '') or ''
            is_split_check = 'PMT-SPLIT-' in check_reference
            
            if is_split_check:
                try:
                    split_id_str = check_reference.split('PMT-SPLIT-')[1].split('-')[0]
                    split_id = int(split_id_str)
                    
                    affected_split = next((s for s in cheque_splits if s[0] == split_id), None)
                    
                    if affected_split:
                        if len(non_cheque_splits) > 0:
                            return PaymentStatus.COMPLETED.value
                        else:
                            all_cheque_splits_resubmitted_or_cashed = True
                            has_pending_cheque_splits = False
                            
                            for split in cheque_splits:
                                if split[0] != split_id:
                                    split_check = connection.execute(
                                        sa_text("""
                                            SELECT status FROM checks 
                                            WHERE reference_number LIKE :ref_pattern
                                        """),
                                        {"ref_pattern": f"PMT-SPLIT-{split[0]}-%"}
                                    ).fetchone()
                                    
                                    if split_check:
                                        split_status = split_check[0]
                                        if split_status not in ['CASHED', 'RESUBMITTED', 'PENDING']:
                                            all_cheque_splits_resubmitted_or_cashed = False
                                        if split_status in ['PENDING', 'RESUBMITTED']:
                                            has_pending_cheque_splits = True
                            
                            if all_cheque_splits_resubmitted_or_cashed and not has_pending_cheque_splits:
                                return PaymentStatus.COMPLETED.value
                            else:
                                return PaymentStatus.PENDING.value
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
                else:
                    if len(non_cheque_splits) > 0:
                        return PaymentStatus.COMPLETED.value
                    else:
                        return PaymentStatus.PENDING.value

        elif check_status == 'PENDING':
            if len(non_cheque_splits) > 0:
                return PaymentStatus.COMPLETED.value
            else:
                return PaymentStatus.PENDING.value
        
        elif check_status == 'CASHED':
            if len(non_cheque_splits) == 0:
                all_cheque_splits_cashed = True
                for split in cheque_splits:
                    split_check = connection.execute(
                        sa_text("""
                            SELECT status FROM checks 
                            WHERE reference_number LIKE :ref_pattern
                        """),
                        {"ref_pattern": f"PMT-SPLIT-{split[0]}-%"}
                    ).fetchone()
                    
                    if not split_check or split_check[0] != 'CASHED':
                        all_cheque_splits_cashed = False
                        break
                
                if all_cheque_splits_cashed:
                    return PaymentStatus.COMPLETED.value
                else:
                    return PaymentStatus.PENDING.value
            else:
                return PaymentStatus.COMPLETED.value
        
        elif check_status == 'CANCELLED':
            check_reference = getattr(check, 'reference_number', '') or ''
            is_split_check = 'PMT-SPLIT-' in check_reference
            
            if is_split_check:
                try:
                    split_id_str = check_reference.split('PMT-SPLIT-')[1].split('-')[0]
                    split_id = int(split_id_str)
                    
                    affected_split = next((s for s in cheque_splits if s[0] == split_id), None)
                    
                    if affected_split:
                        all_cheque_splits_settled_or_cashed = True
                        has_active_cheque_splits = False
                        
                        for split in cheque_splits:
                            if split[0] != split_id:
                                split_check = connection.execute(
                                    sa_text("""
                                        SELECT status FROM checks 
                                        WHERE reference_number LIKE :ref_pattern
                                    """),
                                    {"ref_pattern": f"PMT-SPLIT-{split[0]}-%"}
                                ).fetchone()
                                
                                if split_check:
                                    split_status = split_check[0]
                                    if split_status not in ['CASHED', 'CANCELLED']:
                                        all_cheque_splits_settled_or_cashed = False
                                    if split_status not in ['CANCELLED']:
                                        has_active_cheque_splits = True
                        
                        if len(non_cheque_splits) > 0:
                            return PaymentStatus.COMPLETED.value
                        elif all_cheque_splits_settled_or_cashed and not has_active_cheque_splits:
                            return PaymentStatus.COMPLETED.value
                        else:
                            return PaymentStatus.COMPLETED.value
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                if len(cheque_splits) == 1 and len(non_cheque_splits) == 0:
                    return PaymentStatus.COMPLETED.value
                elif len(non_cheque_splits) > 0:
                    return PaymentStatus.COMPLETED.value
                else:
                    return PaymentStatus.COMPLETED.value
        
        return None
    
    @staticmethod
    def _calculate_status_without_splits(check_status):
        from models import PaymentStatus
        
        if check_status in ['RETURNED', 'BOUNCED']:
            return PaymentStatus.FAILED.value
        elif check_status == 'PENDING':
            return PaymentStatus.PENDING.value
        elif check_status == 'RESUBMITTED':
            return PaymentStatus.PENDING.value
        elif check_status == 'CASHED':
            return PaymentStatus.COMPLETED.value
        elif check_status == 'CANCELLED':
            return PaymentStatus.CANCELLED.value
        else:
            return None


def create_check_record(
    *,
    amount,
    check_number,
    check_bank,
    payment=None,
    currency=None,
    direction=None,
    check_date=None,
    check_due_date=None,
    customer_id=None,
    supplier_id=None,
    partner_id=None,
    reference_number=None,
    notes=None,
    payee_name=None,
    created_by_id=None,
    status=None
):
    if amount is None:
        return None, False
    check_number = (check_number or "").strip()
    check_bank = (check_bank or "").strip()
    if not check_number or not check_bank:
        return None, False
    def _to_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None
    check_date_obj = _to_datetime(check_date) or datetime.utcnow()
    check_due_date_obj = _to_datetime(check_due_date) or check_date_obj
    if check_due_date_obj < check_date_obj:
        check_due_date_obj = check_date_obj
    if payment and getattr(payment, "id", None):
        existing = Check.query.filter_by(payment_id=payment.id, check_number=check_number).first()
        if existing:
            return existing, False
    resolved_currency = currency or getattr(payment, "currency", None) or "ILS"
    resolved_direction = direction or getattr(payment, "direction", None) or PaymentDirection.OUT.value
    resolved_status = status or CheckStatus.PENDING.value
    resolved_customer = customer_id if customer_id is not None else getattr(payment, "customer_id", None)
    resolved_supplier = supplier_id if supplier_id is not None else getattr(payment, "supplier_id", None)
    resolved_partner = partner_id if partner_id is not None else getattr(payment, "partner_id", None)
    resolved_reference = reference_number or (f"PMT-{payment.id}" if payment and getattr(payment, "id", None) else None)
    resolved_created_by = created_by_id or getattr(payment, "created_by", None) or (current_user.id if current_user.is_authenticated else None)
    check = Check(
        payment_id=getattr(payment, "id", None),
        check_number=check_number,
        check_bank=check_bank,
        check_date=check_date_obj,
        check_due_date=check_due_date_obj,
        amount=Decimal(str(amount)),
        currency=resolved_currency,
        direction=resolved_direction,
        status=resolved_status,
        customer_id=resolved_customer,
        supplier_id=resolved_supplier,
        partner_id=resolved_partner,
        reference_number=resolved_reference,
        notes=notes,
        payee_name=payee_name,
        created_by_id=resolved_created_by
    )
    db.session.add(check)
    return check, True

@event.listens_for(Check, 'before_delete')
def _check_gl_batch_reverse(mapper, connection, target):
    """إنشاء قيد عكسي عند حذف الشيك (أصح محاسبياً)"""
    try:
        if hasattr(target, '_skip_gl_reversal') and target._skip_gl_reversal:
            from sqlalchemy import text as sa_text
            connection.execute(
                sa_text("DELETE FROM gl_batches WHERE source_type = 'CHECK' AND source_id = :cid"),
                {"cid": target.id}
            )
            return
        
        amount = float(target.amount or 0)
        if amount <= 0:
            return
        
        from models import fx_rate, GL_ACCOUNTS, PAYMENT_GL_MAP
        
        amount_ils = amount
        if target.currency and target.currency != 'ILS':
            try:
                rate = fx_rate(target.currency, 'ILS', target.check_date or datetime.utcnow(), raise_on_missing=False)
                if rate and rate > 0:
                    amount_ils = float(amount * float(rate))
            except Exception:
                pass
            try:
                connection = db.engine.connect()
                try:
                    new_payment_status = PaymentStatusSyncService.sync_payment_status_from_check(check, connection)
                    if new_payment_status:
                        old_status_val = getattr(ctx.payment, 'status', None)
                        old = getattr(old_status_val, 'value', old_status_val) if old_status_val else 'PENDING'
                        old_upper = str(old).upper()
                        new_upper = new_payment_status.upper()
                        if old_upper != new_upper:
                            allowed = _ALLOWED_TRANSITIONS.get(old_upper, set())
                            if new_upper in allowed:
                                ctx.payment.status = new_payment_status
                            else:
                                ctx.payment.notes = (ctx.payment.notes or '') + f"\n[SKIP_STATUS_SYNC] {old_upper} → {new_upper}"
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass
            except Exception:
                pass
        
        bank_account = GL_ACCOUNTS.get("BANK", "1010_BANK")
        ar_account = GL_ACCOUNTS.get("AR", "1100_AR")
        
        check_type = getattr(target, 'check_type', 'RECEIVED')
        if check_type == 'RECEIVED':
            entries = [(ar_account, amount_ils, 0), (bank_account, 0, amount_ils)]
        else:
            ap_account = GL_ACCOUNTS.get("AP", "2000_AP")
            entries = [(ap_account, 0, amount_ils), (bank_account, amount_ils, 0)]
        
        from models import _gl_upsert_batch_and_entries
        _gl_upsert_batch_and_entries(
            connection,
            source_type="CHECK_REVERSAL",
            source_id=target.id,
            purpose="REVERSAL",
            currency="ILS",
            memo=f"عكس قيد - حذف شيك #{target.check_number}",
            entries=entries,
            ref=f"REV-CHK-{target.id}",
            entity_type="OTHER",
            entity_id=None
        )
    except Exception as e:
        try:
            current_app.logger.error(f"⚠️ خطأ في عكس قيد الشيك #{getattr(target, 'id', '?')}: {e}")
            
        except Exception:
            logging.getLogger(__name__).error(f"⚠️ خطأ في عكس قيد الشيك #{getattr(target, 'id', '?')}: {e}")


@event.listens_for(Payment, 'before_delete')
def _payment_check_before_delete(mapper, connection, target):
    try:
        if target.method == PaymentMethod.CHEQUE:
            connection.execute(
                GLBatch.__table__.delete().where(
                    (GLBatch.source_type == 'check_payment') & 
                    (GLBatch.source_id == target.id)
                )
            )
    except Exception as e:
        try:
            current_app.logger.error(f"خطأ في حذف القيود المحاسبية للدفعة {getattr(target, 'id', '?')}: {str(e)}")
            
        except Exception:
            pass


@event.listens_for(GLBatch, 'before_delete')
def _glbatch_before_delete(mapper, connection, target):
    """عند حذف قيد محاسبي مرتبط بشيك، إلغاء الشيك تلقائياً"""
    try:
        source_type = getattr(target, 'source_type', None)
        source_id = getattr(target, 'source_id', None)
        
        if not source_type or not source_id:
            return
        
        warning_line = '⚠️ تم إلغاء الشيك بسبب حذف القيد المحاسبي'
        if source_type == 'check_check':
            existing_notes = connection.execute(
                select(Check.notes).where(Check.id == source_id)
            ).scalar()
            combined_notes = warning_line if not existing_notes else f"{existing_notes}\n{warning_line}"
            connection.execute(
                Check.__table__.update().where(Check.id == source_id).values(
                    status='CANCELLED',
                    notes=combined_notes
                )
            )
        elif source_type == 'check_payment':
            existing_notes = connection.execute(
                select(Payment.notes).where(Payment.id == source_id)
            ).scalar()
            combined_notes = warning_line if not existing_notes else f"{existing_notes}\n{warning_line}"
            connection.execute(
                Payment.__table__.update().where(Payment.id == source_id).values(
                    notes=combined_notes
                )
            )
    except Exception as e:
        try:
            current_app.logger.error(f"خطأ في إلغاء الشيك عند حذف القيد (type={getattr(target, 'source_type', '?')}, id={getattr(target, 'source_id', '?')}): {str(e)}")
            
        except Exception:
            pass


_check_gl_queue = []

@event.listens_for(db.session, 'after_commit')
def _process_check_gl_queue(session):
    _create_check_gl_after_commit()

def _create_check_gl_after_commit():
    """إنشاء GL للشيكات المعلقة بعد commit"""
    global _check_gl_queue
    if not _check_gl_queue:
        return
    
    queue_copy = _check_gl_queue.copy()
    _check_gl_queue.clear()
    
    for item in queue_copy:
        try:
            create_gl_entry_for_check(
                check_id=item['check_id'],
                check_type=item['check_type'],
                amount=item['amount'],
                currency=item['currency'],
                direction=item['direction'],
                new_status=item['check_status'],
                old_status=None,
                entity_name=item['entity_name'],
                notes=item['notes'],
                entity_type=item['entity_type'],
                entity_id=item['entity_id'],
                connection=None
            )
        except Exception as e:
            current_app.logger.error(f"❌ خطأ في إنشاء GL بعد commit للشيك {item.get('check_id', '?')}: {e}")

@event.listens_for(Check, 'after_insert', propagate=True)
def _check_manual_gl_on_insert(mapper, connection, target):
    """ترحيل الشيكات اليدوية (بدون payment_id) لدفتر الأستاذ عند إنشائها"""
    try:
        if target.payment_id is not None:
            return
        
        if hasattr(target, '_skip_gl_creation') and target._skip_gl_creation:
            return
        
        check_status = str(getattr(target, 'status', 'PENDING') or 'PENDING').upper()
        if check_status not in ['PENDING', 'CASHED', 'RETURNED', 'BOUNCED']:
            return
        
        entity_name = ''
        entity_id = None
        entity_type = None
        
        from sqlalchemy import text as sa_text
        
        try:
            if target.customer_id:
                customer = connection.execute(
                    sa_text("SELECT name FROM customers WHERE id = :id"),
                    {"id": target.customer_id}
                ).scalar_one_or_none()
                entity_name = customer or 'عميل'
                entity_id = target.customer_id
                entity_type = 'CUSTOMER'
            elif target.supplier_id:
                supplier = connection.execute(
                    sa_text("SELECT name FROM suppliers WHERE id = :id"),
                    {"id": target.supplier_id}
                ).scalar_one_or_none()
                entity_name = supplier or 'مورد'
                entity_id = target.supplier_id
                entity_type = 'SUPPLIER'
            elif target.partner_id:
                partner = connection.execute(
                    sa_text("SELECT name FROM partners WHERE id = :id"),
                    {"id": target.partner_id}
                ).scalar_one_or_none()
                entity_name = partner or 'شريك'
                entity_id = target.partner_id
                entity_type = 'PARTNER'
        except Exception as e:
            current_app.logger.warning(f"⚠️ خطأ في جلب اسم الكيان للشيك #{getattr(target, 'id', '?')}: {e}")
            
            return
        
        if not entity_id:
            return
        direction = str(getattr(target, 'direction', 'IN') or 'IN')
        amount = float(target.amount or 0)
        currency = target.currency or 'ILS'
        check_type = 'manual'
        
        _check_gl_queue.append({
            'check_id': target.id,
            'check_type': check_type,
            'amount': amount,
            'currency': currency,
            'direction': direction,
            'check_status': check_status,
            'entity_name': entity_name,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'notes': target.notes or 'شيك يدوي'
        })
    except Exception as e:
        current_app.logger.warning(f"⚠️ خطأ في وضع علامة لإنشاء GL للشيك #{getattr(target, 'id', '?')}: {e}")
        


@event.listens_for(Check, 'after_insert', propagate=True)
def _check_create_payment_auto(mapper, connection, target):
    """إنشاء دفعة تلقائياً عند إنشاء شيك يدوي"""
    try:
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] بدء إنشاء دفعة للشيك #{getattr(target, 'id', '?')}")
        
        if target.payment_id is not None:
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] الشيك #{getattr(target, 'id', '?')} لديه payment_id بالفعل: {target.payment_id}")
            return
        
        entity_id = None
        entity_type = None
        
        if target.customer_id:
            entity_id = target.customer_id
            entity_type = 'CUSTOMER'
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] الشيك #{getattr(target, 'id', '?')} مرتبط بعميل #{entity_id}")
        elif target.supplier_id:
            entity_id = target.supplier_id
            entity_type = 'SUPPLIER'
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] الشيك #{getattr(target, 'id', '?')} مرتبط بمورد #{entity_id}")
        elif target.partner_id:
            entity_id = target.partner_id
            entity_type = 'PARTNER'
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] الشيك #{getattr(target, 'id', '?')} مرتبط بشريك #{entity_id}")
        
        if not entity_id:
            current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] الشيك #{getattr(target, 'id', '?')} غير مرتبط بأي جهة - تخطي إنشاء الدفعة")
            return
        
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] محاولة الحصول على session للشيك #{getattr(target, 'id', '?')}")
        from sqlalchemy.orm import Session
        session = Session.object_session(target)
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] Session.object_session(target) = {session}")
        
        if not session:
            current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] Session.object_session عاد None - استخدام db.session")
            session = db.session
        else:
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] استخدام session من object_session")
        
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] Session النهائي: {session}, نوعه: {type(session)}")
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] Session.is_active: {getattr(session, 'is_active', 'N/A')}")
        
        check_status = str(getattr(target, 'status', 'PENDING') or 'PENDING').upper()
        direction = str(getattr(target, 'direction', 'IN') or 'IN')
        
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] حالة الشيك: {check_status}, الاتجاه: {direction}")
        
        payment_status = PaymentStatus.PENDING.value
        if check_status == 'CASHED':
            payment_status = PaymentStatus.COMPLETED.value
        elif check_status in ['RETURNED', 'BOUNCED']:
            payment_status = PaymentStatus.FAILED.value
        elif check_status == 'CANCELLED':
            payment_status = PaymentStatus.CANCELLED.value
        
        created_by_id = getattr(target, 'created_by_id', None)
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] created_by_id من الشيك: {created_by_id}")
        
        if not created_by_id:
            try:
                from sqlalchemy import text as sa_text
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] محاولة جلب أول مستخدم من قاعدة البيانات")
                first_user_result = session.execute(
                    sa_text("SELECT id FROM users ORDER BY id LIMIT 1")
                ).scalar()
                created_by_id = first_user_result if first_user_result else 1
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] تم جلب created_by_id: {created_by_id}")
            except Exception as e:
                created_by_id = 1
                current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] خطأ في جلب created_by_id: {e} - استخدام 1 كقيمة افتراضية")
        
        from sqlalchemy import text as sa_text
        from sqlalchemy.orm import Session as SQLSession
        
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] استخدام connection.execute() مباشرة...")
        current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] connection type: {type(connection)}")
        
        use_new_connection = False
        connection_from_event = connection is not None
        
        if connection is None:
            use_new_connection = True
            connection = db.engine.connect()
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] connection كان None - إنشاء connection جديد")
        elif isinstance(connection, SQLSession):
            try:
                connection = connection.connection()
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] connection كان Session - تحويل إلى connection")
            except Exception as e:
                current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] فشل تحويل Session إلى connection: {e} - استخدام connection جديد")
                use_new_connection = True
                connection = db.engine.connect()
        else:
            try:
                if hasattr(connection, 'closed') and connection.closed:
                    current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] connection مغلق - استخدام connection جديد")
                    use_new_connection = True
                    connection = db.engine.connect()
            except:
                pass
        
        try:
            ins = Payment.__table__.insert().values(
                payment_date=target.check_date or datetime.utcnow(),
                total_amount=float(target.amount),
                currency=target.currency or 'ILS',
                method=PaymentMethod.CHEQUE.value,
                direction=direction,
                status=payment_status,
                check_number=target.check_number,
                check_bank=target.check_bank,
                check_due_date=target.check_due_date,
                reference=f"شيك يدوي - {target.check_number or ''}",
                notes=(target.notes or f"شيك يدوي رقم {target.check_number}") + "\n[FROM_MANUAL_CHECK=true]",
                customer_id=target.customer_id,
                supplier_id=target.supplier_id,
                partner_id=target.partner_id,
                entity_type=entity_type,
                created_by_id=created_by_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] تنفيذ INSERT...")
            result = connection.execute(ins)
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] تم تنفيذ INSERT - result: {result}")
            
            payment_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
            current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] payment_id من inserted_primary_key: {payment_id}")
            
            if not payment_id:
                current_app.logger.warning(f"🔍 [CHECK_PAYMENT_AUTO] inserted_primary_key فارغ - محاولة SELECT...")
                payment_id = connection.execute(
                    sa_text("SELECT id FROM payments WHERE check_number = :cn AND customer_id = :cid ORDER BY id DESC LIMIT 1"),
                    {"cn": target.check_number, "cid": target.customer_id}
                ).scalar()
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] payment_id من SELECT: {payment_id}")
            
            if payment_id:
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] Payment ID: {payment_id} - تحديث payment_id للشيك...")
                connection.execute(
                    Check.__table__.update().where(Check.id == target.id).values(payment_id=payment_id)
                )
                target.payment_id = payment_id
                current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] تم تحديث payment_id للشيك: {target.payment_id}")
            
            if use_new_connection and not connection_from_event:
                try:
                    connection.close()
                    current_app.logger.info(f"🔍 [CHECK_PAYMENT_AUTO] تم إغلاق connection الجديد")
                except:
                    pass
        except Exception as conn_e:
            if use_new_connection and not connection_from_event:
                try:
                    connection.close()
                except:
                    pass
            raise conn_e
        
        current_app.logger.info(f"✅ تم إنشاء دفعة تلقائياً للشيك اليدوي #{target.id} - Payment #{payment_id}")
    except Exception as e:
        current_app.logger.error(f"❌ [CHECK_PAYMENT_AUTO] خطأ في إنشاء دفعة تلقائية للشيك اليدوي #{getattr(target, 'id', '?')}: {e}")
        


@event.listens_for(Check, 'after_update', propagate=True)
def _check_manual_gl_on_update(mapper, connection, target):
    """ترحيل الشيكات اليدوية (بدون payment_id) لدفتر الأستاذ عند تحديث حالتها"""
    try:
        from sqlalchemy import text as sa_text
        from sqlalchemy.orm.attributes import get_history
        from extensions import cache
        
        if target.payment_id is not None:
            return
        
        if hasattr(target, '_skip_gl_creation') and target._skip_gl_creation:
            return
        
        history = get_history(target, 'status')
        
        if not history.has_changes():
            return
        
        old_status = None
        if history.deleted:
            old_status = str(history.deleted[0] or 'PENDING').upper()
        new_status = str(getattr(target, 'status', 'PENDING') or 'PENDING').upper()
        
        if old_status == new_status:
            return
        
        if new_status not in ['PENDING', 'CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED', 'RESUBMITTED']:
            return
        
        entity_name = ''
        entity_id = None
        entity_type = None
        
        if target.customer_id:
            customer = connection.execute(
                sa_text("SELECT name FROM customers WHERE id = :id"),
                {"id": target.customer_id}
            ).scalar_one_or_none()
            entity_name = customer or 'عميل'
            entity_id = target.customer_id
            entity_type = 'CUSTOMER'
        elif target.supplier_id:
            supplier = connection.execute(
                sa_text("SELECT name FROM suppliers WHERE id = :id"),
                {"id": target.supplier_id}
            ).scalar_one_or_none()
            entity_name = supplier or 'مورد'
            entity_id = target.supplier_id
            entity_type = 'SUPPLIER'
        elif target.partner_id:
            partner = connection.execute(
                sa_text("SELECT name FROM partners WHERE id = :id"),
                {"id": target.partner_id}
            ).scalar_one_or_none()
            entity_name = partner or 'شريك'
            entity_id = target.partner_id
            entity_type = 'PARTNER'
        
        if not entity_id:
            return
        
        try:
            if entity_type == 'SUPPLIER':
                cache.delete(f'supplier_balance_unified_{entity_id}')
            elif entity_type == 'PARTNER':
                cache.delete(f'partner_balance_unified_{entity_id}')
            elif entity_type == 'CUSTOMER':
                cache.delete(f'customer_balance_{entity_id}')
        except Exception:
            pass
        
        direction = str(getattr(target, 'direction', 'IN') or 'IN')
        amount = float(target.amount or 0)
        currency = target.currency or 'ILS'
        
        check_type = 'manual'
        
        existing_batch = connection.execute(
            sa_text("""
                SELECT id FROM gl_batches 
                WHERE source_type = :source_type 
                AND source_id = :source_id 
                AND status = 'POSTED'
                ORDER BY created_at DESC 
                LIMIT 1
            """),
            {
                "source_type": f'check_{check_type}',
                "source_id": target.id
            }
        ).fetchone()
        
        if existing_batch:
            current_app.logger.info(f"⚠️ يوجد GL batch موجود للشيك اليدوي #{target.id} - تخطي الإنشاء")
            return
        
        create_gl_entry_for_check(
            check_id=target.id,
            check_type=check_type,
            amount=amount,
            currency=currency,
            direction=direction,
            new_status=new_status,
            old_status=old_status,
            entity_name=entity_name,
            notes=target.notes or 'شيك يدوي',
            entity_type=entity_type,
            entity_id=entity_id,
            connection=connection
        )
    except Exception as e:
        current_app.logger.warning(f"⚠️ خطأ في ترحيل الشيك اليدوي #{getattr(target, 'id', '?')} لدفتر الأستاذ عند التحديث: {e}")
        


def ensure_check_accounts():
    """التأكد من وجود جميع حسابات دفتر الأستاذ المطلوبة"""
    try:
        required_accounts = [
            ('1000_CASH', 'الصندوق', 'ASSET'),
            ('1010_BANK', 'البنك', 'ASSET'),
            ('1020_CARD_CLEARING', 'بطاقات الائتمان', 'ASSET'),
            ('1100_AR', 'العملاء (ذمم مدينة)', 'ASSET'),
            ('1150_CHEQUES_RECEIVABLE', 'شيكات تحت التحصيل', 'ASSET'),
            ('1205_INV_EXCHANGE', 'المخزون - تبادل', 'ASSET'),
            
            ('2000_AP', 'الموردين (ذمم دائنة)', 'LIABILITY'),
            ('2100_VAT_PAYABLE', 'ضريبة القيمة المضافة', 'LIABILITY'),
            ('2150_CHEQUES_PAYABLE', 'شيكات تحت الدفع', 'LIABILITY'),
            
            ('4000_SALES', 'المبيعات', 'REVENUE'),
            
            ('5000_EXPENSES', 'المصروفات العامة', 'EXPENSE'),
            ('5105_COGS_EXCHANGE', 'تكلفة البضاعة المباعة', 'EXPENSE'),
        ]
        
        for code, name, acc_type in required_accounts:
            existing = Account.query.filter_by(code=code).first()
            if not existing:
                new_account = Account(code=code, name=name, type=acc_type, is_active=True)
                db.session.add(new_account)
                current_app.logger.info(f"✅ تم إنشاء حساب: {code} - {name}")
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إنشاء حسابات دفتر الأستاذ: {str(e)}")
        db.session.rollback()


def _create_gl_batch(connection, batch_code, check_type, check_id, currency, entity_name, notes, entity_type, entity_id, check_type_label):
    from sqlalchemy import text as sa_text
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    is_sqlite = uri.startswith("sqlite")
    
    batch_data = {
        "code": batch_code,
        "source_type": f'check_{check_type}',
        "source_id": int(check_id) if str(check_id).replace('-', '').isdigit() else check_id,
        "currency": currency or 'ILS',
        "status": 'POSTED',
        "memo": f"قيد {check_type_label}: {entity_name} - {notes}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    if is_sqlite:
        connection.execute(
            sa_text("""
                INSERT INTO gl_batches (code, source_type, source_id, currency, status, memo, entity_type, entity_id, created_at, updated_at)
                VALUES (:code, :source_type, :source_id, :currency, :status, :memo, :entity_type, :entity_id, :created_at, :updated_at)
            """),
            batch_data
        )
        return connection.execute(sa_text("SELECT last_insert_rowid()")).scalar()
    else:
        result = connection.execute(
            sa_text("""
                INSERT INTO gl_batches (code, source_type, source_id, currency, status, memo, entity_type, entity_id, created_at, updated_at)
                VALUES (:code, :source_type, :source_id, :currency, :status, :memo, :entity_type, :entity_id, :created_at, :updated_at)
                RETURNING id
            """),
            batch_data
        )
        return result.scalar()


def _create_gl_entries_for_pending(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming):
    entries = []
    if is_incoming:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"{check_type_label} وارد معلق من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AR'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"{check_type_label} وارد معلق من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    else:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AP'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"{check_type_label} صادر معلق إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"{check_type_label} صادر معلق إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    return entries


def _create_gl_entries_for_cashed(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming):
    entries = []
    if is_incoming:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['BANK'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"صرف {check_type_label} وارد من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"صرف {check_type_label} وارد من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    else:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"صرف {check_type_label} صادر إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['BANK'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"صرف {check_type_label} صادر إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    return entries


def _create_gl_entries_for_returned(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming):
    entries = []
    if is_incoming:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AR'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"إرجاع {check_type_label} من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"إرجاع {check_type_label} من {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    else:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"إرجاع {check_type_label} إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AP'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"إرجاع {check_type_label} إلى {entity_name}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    return entries


def _create_gl_entries_for_resubmitted(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming):
    return _create_gl_entries_for_pending(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming)


def _create_gl_entries_for_cancelled(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming, old_status):
    entries = []
    if old_status in ['RETURNED', 'BOUNCED']:
        if is_incoming:
            entries.extend([
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['AR'],
                    "debit": 0.0,
                    "credit": float(amount_decimal),
                    "currency": currency or 'ILS',
                    "ref": f"✅ تسوية {check_type_label} وارد من {entity_name} (كان مرتد)",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                    "debit": float(amount_decimal),
                    "credit": 0.0,
                    "currency": currency or 'ILS',
                    "ref": f"✅ تسوية {check_type_label} وارد من {entity_name} (كان مرتد)",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            ])
        else:
            entries.extend([
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                    "debit": 0.0,
                    "credit": float(amount_decimal),
                    "currency": currency or 'ILS',
                    "ref": f"✅ تسوية {check_type_label} صادر إلى {entity_name} (كان مرتد)",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['AP'],
                    "debit": float(amount_decimal),
                    "credit": 0.0,
                    "currency": currency or 'ILS',
                    "ref": f"✅ تسوية {check_type_label} صادر إلى {entity_name} (كان مرتد)",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            ])
    else:
        if is_incoming:
            entries.extend([
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['AR'],
                    "debit": float(amount_decimal),
                    "credit": 0.0,
                    "currency": currency or 'ILS',
                    "ref": f"⛔ إلغاء {check_type_label} وارد من {entity_name}",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                    "debit": 0.0,
                    "credit": float(amount_decimal),
                    "currency": currency or 'ILS',
                    "ref": f"⛔ إلغاء {check_type_label} وارد من {entity_name}",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            ])
        else:
            entries.extend([
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                    "debit": float(amount_decimal),
                    "credit": 0.0,
                    "currency": currency or 'ILS',
                    "ref": f"⛔ إلغاء {check_type_label} صادر إلى {entity_name}",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                {
                    "batch_id": batch_id,
                    "account": GL_ACCOUNTS_CHECKS['AP'],
                    "debit": 0.0,
                    "credit": float(amount_decimal),
                    "currency": currency or 'ILS',
                    "ref": f"⛔ إلغاء {check_type_label} صادر إلى {entity_name}",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            ])
    return entries


def _create_gl_entries_for_reverse_cancelled(amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming, new_status):
    entries = []
    if is_incoming:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AR'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"↩️ عكس إلغاء {check_type_label} وارد من {entity_name} - إرجاع للحالة: {new_status}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_RECEIVABLE'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"↩️ عكس إلغاء {check_type_label} وارد من {entity_name} - إرجاع للحالة: {new_status}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    else:
        entries.extend([
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['CHEQUES_PAYABLE'],
                "debit": 0.0,
                "credit": float(amount_decimal),
                "currency": currency or 'ILS',
                "ref": f"↩️ عكس إلغاء {check_type_label} صادر إلى {entity_name} - إرجاع للحالة: {new_status}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "batch_id": batch_id,
                "account": GL_ACCOUNTS_CHECKS['AP'],
                "debit": float(amount_decimal),
                "credit": 0.0,
                "currency": currency or 'ILS',
                "ref": f"↩️ عكس إلغاء {check_type_label} صادر إلى {entity_name} - إرجاع للحالة: {new_status}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ])
    return entries


def create_gl_entry_for_check(check_id, check_type, amount, currency, direction, 
                               new_status, old_status=None, entity_name='', notes='', 
                               entity_type=None, entity_id=None, connection=None):
    """
    إنشاء قيد محاسبي عند تغيير حالة الشيك
    
    Args:
        connection: SQLAlchemy connection object (من event listener) - إذا كان None، يستخدم db.session
    
    القيود المحاسبية:
    1. عند استلام شيك من عميل (INCOMING):
       - مدين: شيكات تحت التحصيل (أصل)
       - دائن: العملاء (أصل - تخفيض)
       
    2. عند صرف شيك وارد (CASHED - INCOMING):
       - مدين: البنك (أصل - زيادة)
       - دائن: شيكات تحت التحصيل (أصل - تخفيض)
       
    3. عند إرجاع شيك وارد (RETURNED - INCOMING):
       - مدين: العملاء (أصل - زيادة)
       - دائن: شيكات تحت التحصيل (أصل - تخفيض)
       
    4. عند إعطاء شيك لمورد (OUTGOING):
       - مدين: الموردين (خصم - تخفيض)
       - دائن: شيكات تحت الدفع (خصم - زيادة)
       
    5. عند صرف شيك صادر (CASHED - OUTGOING):
       - مدين: شيكات تحت الدفع (خصم - تخفيض)
       - دائن: البنك (أصل - تخفيض)
       
    6. عند إرجاع شيك صادر (RETURNED - OUTGOING):
       - مدين: شيكات تحت الدفع (خصم - تخفيض)
       - دائن: الموردين (خصم - زيادة)
    """
    try:
        ensure_check_accounts()
        
        is_incoming = (direction == 'IN')
        amount_decimal = Decimal(str(amount))
        
        check_type_label = "شيك يدوي" if check_type == "manual" else "شيك"
        
        batch_code = f"CHK-{check_type.upper()}-{check_id}-{uuid.uuid4().hex[:8].upper()}"
        
        from sqlalchemy import text as sa_text
        from sqlalchemy.orm import Session as SQLSession
        
        should_close_connection = False
        connection_from_event = connection is not None
        
        if connection is None:
            connection = db.engine.connect()
            should_close_connection = True
        elif isinstance(connection, SQLSession):
            try:
                connection = connection.connection()
            except Exception:
                connection = db.engine.connect()
                should_close_connection = True
                connection_from_event = False
        
        if connection_from_event:
            try:
                if hasattr(connection, 'closed') and connection.closed:
                    current_app.logger.warning(f"⚠️ connection مغلق في create_gl_entry_for_check - استخدام db.engine.connect()")
                    if should_close_connection:
                        try:
                            connection.close()
                        except:
                            pass
                    connection = db.engine.connect()
                    should_close_connection = True
                    connection_from_event = False
            except Exception:
                if should_close_connection:
                    try:
                        connection.close()
                    except:
                        pass
                connection = db.engine.connect()
                should_close_connection = True
                connection_from_event = False
        
        try:
            batch_id = _create_gl_batch(
                connection, batch_code, check_type, check_id, currency, 
                entity_name, notes, entity_type, entity_id, check_type_label
            )
        except Exception as conn_e:
            if "closed" in str(conn_e).lower() or "not connected" in str(conn_e).lower():
                current_app.logger.warning(f"⚠️ connection مغلق - استخدام connection جديد")
                if should_close_connection:
                    try:
                        connection.close()
                    except:
                        pass
                connection = db.engine.connect()
                should_close_connection = True
                connection_from_event = False
                batch_id = _create_gl_batch(
                    connection, batch_code, check_type, check_id, currency, 
                    entity_name, notes, entity_type, entity_id, check_type_label
                )
            else:
                if should_close_connection:
                    try:
                        connection.close()
                    except:
                        pass
                raise CheckAccountingError(f"فشل إنشاء GL batch: {str(conn_e)}", code='GL_BATCH_CREATION_FAILED')
        except Exception as e:
            if should_close_connection:
                try:
                    connection.close()
                except:
                    pass
            raise CheckAccountingError(f"خطأ في إنشاء GL batch: {str(e)}", code='GL_BATCH_ERROR')
        
        entries_data = []
        
        try:
            if new_status == 'PENDING' and old_status is None:
                entries_data = _create_gl_entries_for_pending(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming
                )
            elif new_status == 'CASHED':
                entries_data = _create_gl_entries_for_cashed(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming
                )
            elif new_status == 'RETURNED' or new_status == 'BOUNCED':
                entries_data = _create_gl_entries_for_returned(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming
                )
            elif new_status == 'RESUBMITTED':
                entries_data = _create_gl_entries_for_resubmitted(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming
                )
            elif new_status == 'CANCELLED':
                entries_data = _create_gl_entries_for_cancelled(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming, old_status
                )
            elif old_status == 'CANCELLED' and new_status in ['RETURNED', 'PENDING', 'RESUBMITTED']:
                entries_data = _create_gl_entries_for_reverse_cancelled(
                    amount_decimal, currency, batch_id, check_type_label, entity_name, is_incoming, new_status
                )
        except Exception as e:
            current_app.logger.error(f"خطأ في إنشاء GL entries: {e}")
            raise CheckAccountingError(f"فشل إنشاء GL entries: {str(e)}", code='GL_ENTRIES_CREATION_FAILED')
        
        if entries_data:
            from sqlalchemy import insert
            try:
                stmt = insert(GLEntry.__table__).values(entries_data)
                connection.execute(stmt)
            except Exception as entries_e:
                if "closed" in str(entries_e).lower() or "not connected" in str(entries_e).lower():
                    current_app.logger.warning(f"⚠️ connection مغلق عند إضافة entries - استخدام connection جديد")
                    if should_close_connection:
                        try:
                            connection.close()
                        except:
                            pass
                    connection = db.engine.connect()
                    should_close_connection = True
                    connection_from_event = False
                    stmt = insert(GLEntry.__table__).values(entries_data)
                    connection.execute(stmt)
                else:
                    raise
        
        if should_close_connection and not connection_from_event:
            try:
                connection.close()
            except:
                pass
        
        current_app.logger.info(f"✅ تم إنشاء قيد محاسبي للشيك {check_id} - Batch: {batch_code}")
        if connection_from_event:
            batch_row = connection.execute(
                sa_text("SELECT id, code FROM gl_batches WHERE id = :id"),
                {"id": batch_id}
            ).first()
            if batch_row:
                batch = GLBatch()
                batch.id = batch_row[0]
                batch.code = batch_row[1]
            else:
                batch = None
        else:
            batch = GLBatch.query.get(batch_id)
        return batch
        
    except Exception as e:
        current_app.logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للشيك {check_id}: {str(e)}")
        try:
            if 'should_close_connection' in locals() and should_close_connection and connection:
                try:
                    connection.close()
                except:
                    pass
        except:
            pass
        return None

CHECK_STATUS = {
    'PENDING': {'ar': 'معلق', 'color': 'info', 'icon': 'fa-clock'},
    'CASHED': {'ar': 'تم الصرف', 'color': 'success', 'icon': 'fa-check-circle'},
    'RETURNED': {'ar': 'مرتجع', 'color': 'warning', 'icon': 'fa-undo'},
    'BOUNCED': {'ar': 'مرفوض', 'color': 'danger', 'icon': 'fa-ban'},
    'RESUBMITTED': {'ar': 'أعيد للبنك', 'color': 'primary', 'icon': 'fa-recycle'},
    'CANCELLED': {'ar': 'ملغي', 'color': 'secondary', 'icon': 'fa-times-circle'},
    'ARCHIVED': {'ar': 'مؤرشف', 'color': 'dark', 'icon': 'fa-archive'},
    'OVERDUE': {'ar': 'متأخر', 'color': 'danger', 'icon': 'fa-exclamation-triangle'},
}

GL_ACCOUNTS_CHECKS = {
    'CHEQUES_RECEIVABLE': '1150_CHEQUES_RECEIVABLE',
    'CHEQUES_PAYABLE': '2150_CHEQUES_PAYABLE',
    'BANK': '1010_BANK',
    'CASH': '1000_CASH',
    'AR': '1100_AR',
    'AP': '2000_AP',
}

CHECK_LIFECYCLE = {
    'PENDING': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'RETURNED': ['RESUBMITTED', 'CANCELLED', 'PENDING'],
    'BOUNCED': ['RESUBMITTED', 'CANCELLED'],
    'RESUBMITTED': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'OVERDUE': ['CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'],
    'CASHED': [],
    'CANCELLED': ['RETURNED', 'PENDING', 'RESUBMITTED']
}

def _current_user_is_owner() -> bool:
    try:
        if not getattr(current_user, 'is_authenticated', False):
            return False
        if getattr(current_user, 'is_system_account', False):
            return True
        username = (getattr(current_user, 'username', None) or '').strip().lower()
        if username in {'owner', '__owner__'}:
            return True
        role = getattr(current_user, 'role', None)
        role_name = (getattr(role, 'name', '') or '').strip().lower()
        return role_name in {'owner', 'developer'}
    except Exception:
        return False

@dataclass
class CheckActionContext:
    token: str
    kind: str
    payment: Optional[Payment] = None
    split: Optional[PaymentSplit] = None
    expense: Optional[Expense] = None
    manual: Optional[Check] = None
    direction: str = PaymentDirection.IN.value
    amount: Decimal = field(default_factory=lambda: Decimal("0"))
    currency: str = "ILS"
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None


class CheckActionService:
    STATUS_SET = {'PENDING', 'CASHED', 'RETURNED', 'BOUNCED', 'RESUBMITTED', 'CANCELLED', 'ARCHIVED'}
    LEDGER_STATUSES = {'CASHED', 'RETURNED', 'BOUNCED', 'CANCELLED'}
    PAYMENT_STATUS_MAP = {
        'PENDING': PaymentStatus.PENDING.value,
        'RESUBMITTED': PaymentStatus.PENDING.value,
        'CASHED': PaymentStatus.COMPLETED.value,
        'RETURNED': PaymentStatus.FAILED.value,
        'BOUNCED': PaymentStatus.FAILED.value,
        'CANCELLED': PaymentStatus.CANCELLED.value,
        'ARCHIVED': PaymentStatus.CANCELLED.value,
    }
    STATUS_MARKERS = {
        'PENDING': '\u23f3',
        'RESUBMITTED': '\u21bb',
        'CASHED': '\u2705',
        'RETURNED': '\u27f2',
        'BOUNCED': '\u274c',
        'CANCELLED': '\u26d4',
        'ARCHIVED': '\U0001f4e6',
    }

    def __init__(self, actor):
        self.actor = actor

    def run(self, identifier, target_status, note_text):
        try:
            ctx = self._resolve(identifier)
            status = (target_status or '').strip().upper()
            
            if status not in self.STATUS_SET:
                raise CheckValidationError(
                    f'حالة غير صالحة: {status}. الحالات المسموحة: {", ".join(sorted(self.STATUS_SET))}',
                    code='INVALID_STATUS'
                )
            
            previous = self._current_status(ctx)
            
            if previous == status:
                try:
                    if ctx.kind == 'payment_split' and ctx.split:
                        details = self._load_split_details(ctx.split)
                        history = details.get('check_history') or []
                        history.append(self._history_entry(status))
                        details['check_history'] = history
                        details['check_status'] = status
                        if note_text:
                            details['check_note'] = note_text
                        ctx.split.details = details
                        chk = Check.query.filter(Check.reference_number == f"PMT-SPLIT-{ctx.split.id}").first()
                        if chk:
                            chk.status = status
                            if note_text:
                                chk.notes = (chk.notes or '') + self._compose_note(status, note_text, f"Split #{ctx.split.id}")
                            self._link_check_to_entity(chk, ctx)
                    elif ctx.kind == 'payment' and ctx.payment:
                        chk = Check.query.filter(Check.payment_id == ctx.payment.id).first()
                        if chk and str(getattr(chk, 'status', '')).upper() != status:
                            chk.status = status
                            if note_text:
                                chk.notes = (chk.notes or '') + self._compose_note(status, note_text, None)
                            self._link_check_to_entity(chk, ctx)
                except Exception:
                    pass
                return {
                    'token': ctx.token,
                    'kind': ctx.kind,
                    'new_status': status,
                    'new_status_ar': CHECK_STATUS.get(status, {}).get('ar', status),
                    'previous_status': previous,
                    'balance': None,
                    'gl_batch_id': None,
                }
            
            if previous and CHECK_LIFECYCLE.get(previous):
                allowed = CHECK_LIFECYCLE[previous]
                if status not in allowed:
                    raise CheckStateError(
                        f'الانتقال غير مسموح من {previous} إلى {status}. الانتقالات المسموحة: {", ".join(allowed)}',
                        code='INVALID_TRANSITION',
                        details={'from': previous, 'to': status, 'allowed': allowed}
                    )
            
            if status == 'RESUBMITTED':
                if ctx.kind == 'manual' and ctx.manual:
                    resubmit_count = self._count_state_records(ctx, 'RESUBMITTED')
                    allowed_count = self._get_resubmit_allowed_count(ctx)
                    if resubmit_count >= allowed_count:
                        raise CheckStateError(
                            f'لا يمكن إعادة تقديم الشيك أكثر من {allowed_count} مرة (تم الإعادة {resubmit_count} مرة)',
                            code='RESUBMIT_LIMIT_EXCEEDED'
                        )
            
            self._validate_check_context(ctx)
            
            savepoint = None
            try:
                # التحقق من وجود transaction نشط بطريقة متوافقة مع SQLAlchemy 2.0
                try:
                    # محاولة استخدام db.session.in_transaction() مباشرة (SQLAlchemy 2.0)
                    if hasattr(db.session, 'in_transaction') and db.session.in_transaction():
                        savepoint = db.session.begin_nested()
                    else:
                        # محاولة استخدام inspect على session
                        from sqlalchemy import inspect as sa_inspect
                        session_inspect = sa_inspect(db.session.bind) if db.session.bind else None
                        if session_inspect and hasattr(session_inspect, 'in_transaction') and session_inspect.in_transaction():
                            savepoint = db.session.begin_nested()
                except (AttributeError, TypeError):
                    # إذا فشل التحقق، نحاول إنشاء savepoint مباشرة
                    try:
                        savepoint = db.session.begin_nested()
                    except Exception:
                        # لا يوجد transaction نشط، لا نحتاج savepoint
                        pass
                
                result = self._apply(ctx, status, note_text or '', previous)
                result['previous_status'] = previous
                if savepoint:
                    savepoint.commit()
                return result
            except Exception as e:
                if savepoint:
                    savepoint.rollback()
                raise
            
        except (CheckValidationError, CheckStateError, CheckAccountingError):
            raise
        except Exception as e:
            current_app.logger.error(f"خطأ غير متوقع في CheckActionService.run: {e}")
            raise CheckException(f"خطأ في معالجة الشيك: {str(e)}", code='UNEXPECTED_ERROR')

    def _validate_check_context(self, ctx):
        if not ctx:
            raise CheckValidationError("سياق الشيك غير صالح", code='INVALID_CONTEXT')
        
        if ctx.amount is None or ctx.amount <= 0:
            raise CheckValidationError("مبلغ الشيك يجب أن يكون أكبر من الصفر", code='INVALID_AMOUNT')
        
        if ctx.kind == 'manual' and ctx.manual:
            if not ctx.manual.check_number or not ctx.manual.check_bank:
                raise CheckValidationError("رقم الشيك والبنك مطلوبان", code='MISSING_CHECK_DETAILS')
        
        if ctx.entity_type and ctx.entity_id:
            if ctx.entity_type == 'CUSTOMER':
                customer = Customer.query.get(ctx.entity_id)
                if not customer:
                    raise CheckValidationError(f"العميل #{ctx.entity_id} غير موجود", code='ENTITY_NOT_FOUND')
            elif ctx.entity_type == 'SUPPLIER':
                supplier = Supplier.query.get(ctx.entity_id)
                if not supplier:
                    raise CheckValidationError(f"المورد #{ctx.entity_id} غير موجود", code='ENTITY_NOT_FOUND')
            elif ctx.entity_type == 'PARTNER':
                partner = Partner.query.get(ctx.entity_id)
                if not partner:
                    raise CheckValidationError(f"الشريك #{ctx.entity_id} غير موجود", code='ENTITY_NOT_FOUND')

    def _apply(self, ctx, status, note_text, previous):
        try:
            if ctx.kind == 'payment':
                self._apply_payment(ctx, status, note_text)
            elif ctx.kind == 'payment_split':
                self._apply_split(ctx, status, note_text)
            elif ctx.kind == 'expense':
                self._apply_expense(ctx, status, note_text)
            elif ctx.kind == 'manual':
                self._apply_manual(ctx, status, note_text)
            else:
                raise CheckValidationError(f'نوع شيك غير مدعوم: {ctx.kind}', code='UNSUPPORTED_CHECK_TYPE')
            
            balance_value = None
            if ctx.entity_type and ctx.entity_id:
                try:
                    balance_value = self._update_balance(ctx.entity_type, ctx.entity_id)
                except Exception as e:
                    current_app.logger.warning(f"خطأ في تحديث الرصيد للجهة {ctx.entity_type} #{ctx.entity_id}: {e}")
            
            gl_batch = None
            try:
                gl_batch = self._maybe_create_gl(ctx, status, previous, note_text)
            except Exception as e:
                current_app.logger.error(f"خطأ في إنشاء القيد المحاسبي: {e}")
                raise CheckAccountingError(f"فشل إنشاء القيد المحاسبي: {str(e)}", code='GL_CREATION_FAILED')
            
            return {
                'token': ctx.token,
                'kind': ctx.kind,
                'new_status': status,
                'new_status_ar': CHECK_STATUS.get(status, {}).get('ar', status),
                'balance': balance_value,
                'gl_batch_id': getattr(gl_batch, 'id', None),
            }
        except (CheckValidationError, CheckAccountingError, CheckStateError):
            raise
        except Exception as e:
            current_app.logger.error(f"خطأ في _apply: {e}")
            raise CheckException(f"خطأ في تطبيق تغيير الحالة: {str(e)}", code='APPLY_FAILED')

    def _link_check_to_entity(self, check, ctx, expense=None):
        if ctx.entity_type == 'CUSTOMER' and ctx.entity_id:
            check.customer_id = ctx.entity_id
            check.supplier_id = None
            check.partner_id = None
        elif ctx.entity_type == 'SUPPLIER' and ctx.entity_id:
            check.supplier_id = ctx.entity_id
            check.customer_id = None
            check.partner_id = None
        elif ctx.entity_type == 'PARTNER' and ctx.entity_id:
            check.partner_id = ctx.entity_id
            check.customer_id = None
            check.supplier_id = None
        elif expense:
            if expense.customer_id:
                check.customer_id = expense.customer_id
                check.supplier_id = None
                check.partner_id = None
            elif expense.supplier_id:
                check.supplier_id = expense.supplier_id
                check.customer_id = None
                check.partner_id = None
            elif expense.partner_id:
                check.partner_id = expense.partner_id
                check.customer_id = None
                check.supplier_id = None
            else:
                check.customer_id = None
                check.supplier_id = None
                check.partner_id = None
        elif ctx.payment:
            if ctx.payment.customer_id:
                check.customer_id = ctx.payment.customer_id
                check.supplier_id = None
                check.partner_id = None
            elif ctx.payment.supplier_id:
                check.supplier_id = ctx.payment.supplier_id
                check.customer_id = None
                check.partner_id = None
            elif ctx.payment.partner_id:
                check.partner_id = ctx.payment.partner_id
                check.customer_id = None
                check.supplier_id = None
            else:
                from models import Sale, Invoice, ServiceRequest, PreOrder
                if ctx.payment.sale_id:
                    sale = Sale.query.get(ctx.payment.sale_id)
                    if sale and sale.customer_id:
                        check.customer_id = sale.customer_id
                        check.supplier_id = None
                        check.partner_id = None
                elif ctx.payment.invoice_id:
                    invoice = Invoice.query.get(ctx.payment.invoice_id)
                    if invoice and invoice.customer_id:
                        check.customer_id = invoice.customer_id
                        check.supplier_id = None
                        check.partner_id = None
                elif ctx.payment.service_id:
                    service = ServiceRequest.query.get(ctx.payment.service_id)
                    if service and service.customer_id:
                        check.customer_id = service.customer_id
                        check.supplier_id = None
                        check.partner_id = None
                elif ctx.payment.preorder_id:
                    preorder = PreOrder.query.get(ctx.payment.preorder_id)
                    if preorder and preorder.customer_id:
                        check.customer_id = preorder.customer_id
                        check.supplier_id = None
                        check.partner_id = None

    def _apply_payment(self, ctx, status, note_text):
        self._touch_payment(ctx.payment, status, note_text, None)
        
        check = Check.query.filter(
            Check.payment_id == ctx.payment.id
        ).first()
        if check:
            check.status = status
            if note_text:
                check.notes = (check.notes or '') + self._compose_note(status, note_text, None)
            self._link_check_to_entity(check, ctx)
            try:
                notes_upper = ((note_text or '') + (ctx.payment.notes or '')).upper()
                is_bank_reason = '[RETURN_REASON=BANK]' in notes_upper
                if is_bank_reason:
                    if status == 'RETURNED':
                        self._auto_refund_payment(ctx.payment)
                    elif status == 'RESUBMITTED':
                        self._auto_unrefund_payment(ctx.payment)
                        # إعادة تقديم للبنك يجب أن يعيد الحالة إلى "معلق"
                        check.status = 'PENDING'
                        ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note('PENDING', None, None)
                elif status == 'RESUBMITTED':
                    # حتى بدون وسم السبب البنكي، إعادة التقديم تُعيد الشيك إلى "معلق" وتلغي أي استرجاعات
                    try:
                        self._auto_unrefund_payment(ctx.payment)
                    except Exception:
                        pass
                    check.status = 'PENDING'
                    ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note('PENDING', None, None)
                else:
                    previous_check_status = self._guess_status_from_notes(ctx.payment.notes) or 'PENDING'
                    if status in ['RETURNED', 'BOUNCED', 'CASHED', 'CANCELLED']:
                        connection = db.engine.connect()
                        try:
                            create_gl_entry_for_check(
                                check_id=check.id,
                                check_type='payment',
                                amount=float(Decimal(str(check.amount or ctx.amount or 0))),
                                currency=check.currency or ctx.currency or 'ILS',
                                direction=ctx.direction,
                                new_status=status,
                                old_status=str(previous_check_status).upper(),
                                entity_name=ctx.entity_name or '',
                                notes=note_text or '',
                                entity_type=ctx.entity_type,
                                entity_id=ctx.entity_id,
                                connection=connection
                            )
                        finally:
                            try:
                                connection.close()
                            except Exception:
                                pass
            except Exception:
                pass

    def _apply_split(self, ctx, status, note_text):
        split = ctx.split
        details = self._load_split_details(split)
        previous_check_status = str(details.get('check_status') or 'PENDING').upper()
        history = details.get('check_history')
        if not isinstance(history, list):
            history = []
        history.append(self._history_entry(status))
        details['check_history'] = history
        details['check_status'] = status
        if note_text:
            details['check_note'] = note_text
        split.details = details
        
        check = Check.query.filter(
            Check.reference_number == f"PMT-SPLIT-{split.id}"
        ).first()
        if check:
            check.status = status
            if note_text:
                check.notes = (check.notes or '') + self._compose_note(status, note_text, f"Split #{split.id}")
            self._link_check_to_entity(check, ctx)
            
            connection = db.engine.connect()
            try:
                notes_upper = ((note_text or '') + (ctx.payment.notes or '')).upper()
                is_bank_reason = '[RETURN_REASON=BANK]' in notes_upper
                if status in ['RETURNED', 'BOUNCED', 'CASHED', 'CANCELLED'] and not is_bank_reason:
                    check_amount = Decimal(str(check.amount or split.amount or 0))
                    check_currency = check.currency or split.currency or ctx.currency or 'ILS'
                    
                    create_gl_entry_for_check(
                        check_id=check.id,
                        check_type='payment_split',
                        amount=float(check_amount),
                        currency=check_currency,
                        direction=ctx.direction,
                        new_status=status,
                        old_status=previous_check_status,
                        entity_name=ctx.entity_name or '',
                        notes=f"{note_text or ''} - Split #{split.id}",
                        entity_type=ctx.entity_type,
                        entity_id=ctx.entity_id,
                        connection=connection
                    )
                if status == 'RETURNED' and is_bank_reason:
                    try:
                        self._auto_refund_split(ctx.payment, split)
                    except Exception:
                        pass
                elif status == 'RESUBMITTED' and is_bank_reason:
                    try:
                        self._auto_unrefund_split(ctx.payment, split)
                    except Exception:
                        pass
                    # إعادة تقديم للبنك يعيد الحالة إلى "معلق" على مستوى split والشيك
                    try:
                        details = self._load_split_details(split)
                        details['check_status'] = 'PENDING'
                        split.details = details
                    except Exception:
                        pass
                    check.status = 'PENDING'
                    ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note('PENDING', None, f"Split #{split.id}")
                elif status == 'RESUBMITTED':
                    # إعادة تقديم بدون وسم السبب البنكي: أعد للحالة "معلق" وألغِ أي استرجاع سابق
                    try:
                        self._auto_unrefund_split(ctx.payment, split)
                    except Exception:
                        pass
                    try:
                        details = self._load_split_details(split)
                        details['check_status'] = 'PENDING'
                        split.details = details
                    except Exception:
                        pass
                    check.status = 'PENDING'
                    ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note('PENDING', None, f"Split #{split.id}")

                new_payment_status = PaymentStatusSyncService.sync_payment_status_from_check(check, connection)
                if new_payment_status:
                    old_status_val = getattr(ctx.payment, 'status', None)
                    old = getattr(old_status_val, 'value', old_status_val) if old_status_val else 'PENDING'
                    old_upper = str(old).upper()
                    new_upper = new_payment_status.upper()
                    if old_upper != new_upper:
                        allowed = _ALLOWED_TRANSITIONS.get(old_upper, set())
                        if new_upper in allowed:
                            ctx.payment.status = new_payment_status
                            ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note(status, note_text, f"Split #{split.id}")
                        else:
                            ctx.payment.notes = (ctx.payment.notes or '') + f"\n[SKIP_STATUS_SYNC] {old_upper} → {new_upper} غير مسموح"
                    else:
                        ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note(status, note_text, f"Split #{split.id}")
                else:
                    ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note(status, note_text, f"Split #{split.id}")
            finally:
                try:
                    connection.close()
                except Exception:
                    pass
        else:
            ctx.payment.notes = (ctx.payment.notes or '') + self._compose_note(status, note_text, f"Split #{split.id}")

    def _apply_expense(self, ctx, status, note_text):
        exp = ctx.expense
        exp.notes = (exp.notes or '') + self._compose_note(status, note_text, None)
        
        check = None
        if exp.payments:
            for payment in exp.payments:
                check = Check.query.filter(Check.payment_id == payment.id).first()
                if check:
                    break
        
        if not check:
            check = Check.query.filter(
                Check.reference_number.in_([f"EXP-{exp.id}", f"EXPENSE-{exp.id}"])
            ).first()
        
        if check:
            check.status = status
            if note_text:
                check.notes = (check.notes or '') + self._compose_note(status, note_text, None)
            self._link_check_to_entity(check, ctx, expense=exp)
            try:
                connection = db.engine.connect()
                try:
                    new_payment_status = PaymentStatusSyncService.sync_payment_status_from_check(check, connection)
                    if new_payment_status:
                        payment_obj = Payment.query.get(getattr(check, 'payment_id', None))
                        if payment_obj:
                            old_status_val = getattr(payment_obj, 'status', None)
                            old = getattr(old_status_val, 'value', old_status_val) if old_status_val else 'PENDING'
                            old_upper = str(old).upper()
                            new_upper = new_payment_status.upper()
                            if old_upper != new_upper:
                                allowed = _ALLOWED_TRANSITIONS.get(old_upper, set())
                                if new_upper in allowed:
                                    payment_obj.status = new_payment_status
                                else:
                                    payment_obj.notes = (payment_obj.notes or '') + f"\n[SKIP_STATUS_SYNC] {old_upper} → {new_upper}"
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass
            except Exception:
                pass

    def _apply_manual(self, ctx, status, note_text):
        manual = ctx.manual
        manual.status = status
        try:
            manual.add_status_change(status, note_text, self.actor)
        except Exception:
            pass
        manual.notes = (manual.notes or '') + self._compose_note(status, note_text, None)
        manual._skip_gl_creation = True

    def _touch_payment(self, payment, status, note_text, label):
        if not payment:
            return
        mapped = self.PAYMENT_STATUS_MAP.get(status)
        if mapped:
            old_status_val = getattr(payment, 'status', None)
            old = getattr(old_status_val, 'value', old_status_val) or 'PENDING'
            new = mapped or ''
            o = str(old).upper()
            n = str(new).upper()
            if o != n:
                allowed = _ALLOWED_TRANSITIONS.get(o, set())
                if n not in allowed:
                    raise CheckStateError(
                        f"انتقال حالة الدفعة غير مسموح: من {o} إلى {n}. الانتقالات المسموحة: {', '.join(allowed) if allowed else 'لا يوجد'}",
                        code='INVALID_PAYMENT_TRANSITION'
                    )
            payment.status = mapped
        payment.notes = (payment.notes or '') + self._compose_note(status, note_text, label)

    def _maybe_create_gl(self, ctx, status, previous, note_text):
        if status not in self.LEDGER_STATUSES and previous != 'CANCELLED':
            return None
        amount = ctx.amount or Decimal('0')
        if amount <= 0:
            return None
        direction = 'IN' if ctx.direction == PaymentDirection.IN.value else 'OUT'
        
        source_id = self._ledger_source_id(ctx)
        check_type_for_gl = ctx.kind
        
        if ctx.kind == 'manual' and ctx.manual:
            existing_batch = GLBatch.query.filter(
                GLBatch.source_type == f'check_{check_type_for_gl}',
                GLBatch.source_id == source_id,
                GLBatch.status == 'POSTED'
            ).order_by(GLBatch.created_at.desc()).first()
            
            if existing_batch:
                current_app.logger.info(f"⚠️ يوجد GL batch موجود للشيك اليدوي #{source_id} - تخطي الإنشاء")
                return existing_batch
        
        if previous == 'CANCELLED' and status in ['RETURNED', 'PENDING', 'RESUBMITTED']:
            return create_gl_entry_for_check(
                check_id=source_id,
                check_type=check_type_for_gl,
                amount=float(amount),
                currency=ctx.currency or 'ILS',
                direction=direction,
                new_status=status,
                old_status=previous,
                entity_name=ctx.entity_name or '',
                notes=f"إرجاع شيك مسوى - {note_text or ''}",
                entity_type=ctx.entity_type,
                entity_id=ctx.entity_id
            )
        
        if status in self.LEDGER_STATUSES:
            return create_gl_entry_for_check(
                check_id=source_id,
                check_type=check_type_for_gl,
                amount=float(amount),
                currency=ctx.currency or 'ILS',
                direction=direction,
                new_status=status,
                old_status=previous,
                entity_name=ctx.entity_name or '',
                notes=note_text or '',
                entity_type=ctx.entity_type,
                entity_id=ctx.entity_id
            )
        return None

    def _auto_refund_payment(self, payment):
        try:
            existing = Payment.query.filter(
                Payment.refund_of_id == payment.id,
                Payment.notes.ilike('%[AUTO_REFUND_FROM_BANK=true]%'),
                Payment.status != PaymentStatus.CANCELLED.value
            ).first()
            if existing:
                return
            splits = list(getattr(payment, 'splits', []) or [])
            cheque_splits = [s for s in splits if getattr(s.method, 'value', s.method) == PaymentMethod.CHEQUE.value]
            if cheque_splits:
                total_amount = sum(Decimal(str(getattr(s, 'amount', 0) or 0)) for s in cheque_splits)
            else:
                method_val = getattr(payment.method, 'value', payment.method)
                if str(method_val).upper() == PaymentMethod.CHEQUE.value:
                    total_amount = Decimal(str(payment.total_amount or 0))
                else:
                    return
            direction = PaymentDirection.OUT.value if payment.direction == PaymentDirection.IN.value else PaymentDirection.IN.value
            entity_name = None
            try:
                entity_name = (
                    getattr(getattr(payment, 'customer', None), 'name', None) or
                    getattr(getattr(payment, 'supplier', None), 'name', None) or
                    getattr(getattr(payment, 'partner', None), 'name', None)
                )
            except Exception:
                entity_name = None
            # تفاصيل الشيك لإضافتها للملاحظات
            check_num = getattr(payment, 'check_number', None)
            check_bank = getattr(payment, 'check_bank', None)
            if not check_num or not check_bank:
                try:
                    first = cheque_splits[0] if cheque_splits else None
                    det = getattr(first, 'details', {}) or {}
                    if isinstance(det, str):
                        import json as _json
                        try:
                            det = _json.loads(det)
                        except Exception:
                            det = {}
                    check_num = check_num or (det.get('check_number') or None)
                    check_bank = check_bank or (det.get('check_bank') or None)
                except Exception:
                    pass
            # إعداد ملاحظات العكس
            reverse_note = f"\nعكس قيد لل{('عميل' if payment.customer_id else ('مورد' if payment.supplier_id else ('شريك' if payment.partner_id else 'جهة')))} {entity_name or ''} بسبب ارجاع الشيك".strip()
            if check_num or check_bank:
                reverse_note += f" (رقم {check_num or '—'} بنك {check_bank or '—'} من البنك)"
            refund = Payment(
                entity_type=payment.entity_type,
                customer_id=payment.customer_id,
                supplier_id=payment.supplier_id,
                partner_id=payment.partner_id,
                sale_id=payment.sale_id,
                invoice_id=payment.invoice_id,
                service_id=payment.service_id,
                expense_id=payment.expense_id,
                preorder_id=payment.preorder_id,
                shipment_id=payment.shipment_id,
                loan_settlement_id=payment.loan_settlement_id,
                direction=direction,
                status=PaymentStatus.COMPLETED.value,
                payment_date=datetime.utcnow(),
                total_amount=float(total_amount),
                currency=(payment.currency or 'ILS'),
                method=(getattr(payment.method, 'value', payment.method) or PaymentMethod.CHEQUE.value),
                reference=(
                    f"قيد عكسي بسبب ارجاع شيك رقم {check_num or '—'} بنك {check_bank or '—'} من البنك"
                    if (check_num or check_bank) else f"عكس تلقائي لدفعة #{payment.id} بسبب مرتجع بنك"
                ),
                notes=((payment.notes or '') + "\n[AUTO_REFUND_FROM_BANK=true]" + reverse_note),
                refund_of_id=payment.id,
                receiver_name=getattr(payment, 'receiver_name', None),
                deliverer_name=getattr(payment, 'deliverer_name', None),
            )
            # تعيين حقول سعر الصرف للدفعة المسترجعة اعتماداً على دفعة الأصل
            try:
                if payment.currency and payment.currency != 'ILS':
                    refund.fx_rate_used = payment.fx_rate_used
                    refund.fx_rate_source = getattr(payment, 'fx_rate_source', None) or 'original'
                    refund.fx_rate_timestamp = datetime.utcnow()
                    refund.fx_base_currency = payment.fx_base_currency or payment.currency
                    refund.fx_quote_currency = 'ILS'
            except Exception:
                pass
            from routes.payments import _ensure_payment_number
            _ensure_payment_number(refund)
            db.session.add(refund)
            if cheque_splits:
                for sp in cheque_splits:
                    try:
                        det = getattr(sp, 'details', {}) or {}
                        if isinstance(det, str):
                            import json as _json
                            try:
                                det = _json.loads(det)
                            except Exception:
                                det = {}
                        det.update({'auto_refund': True, 'reverse_entry': True})
                        db.session.add(PaymentSplit(
                            payment=refund,
                            method=sp.method,
                            amount=sp.amount,
                            currency=sp.currency,
                            converted_amount=(sp.converted_amount or Decimal(str(getattr(sp, 'amount', 0) or 0))),
                            converted_currency=(sp.converted_currency or 'ILS'),
                            fx_rate_used=getattr(sp, 'fx_rate_used', None),
                            fx_rate_source=getattr(sp, 'fx_rate_source', None),
                            fx_rate_timestamp=getattr(sp, 'fx_rate_timestamp', None),
                            fx_base_currency=getattr(sp, 'fx_base_currency', None),
                            fx_quote_currency=getattr(sp, 'fx_quote_currency', None),
                            details=det
                        ))
                    except Exception:
                        db.session.add(PaymentSplit(
                            payment=refund,
                            method=sp.method,
                            amount=sp.amount,
                            currency=sp.currency,
                            converted_amount=Decimal(str(getattr(sp, 'converted_amount', 0) or getattr(sp, 'amount', 0) or 0)),
                            converted_currency=(getattr(sp, 'converted_currency', None) or 'ILS'),
                            details={'auto_refund': True, 'reverse_entry': True}
                        ))
            else:
                # في حال كانت الدفعة شيك بدون splits، إنشاء split واحد للاسترجاع
                try:
                    base = (payment.currency or 'ILS')
                    rate_used = Decimal(str(getattr(payment, 'fx_rate_used', 0) or 0))
                    converted_amt = Decimal(str(total_amount or 0))
                    if base != 'ILS' and rate_used and rate_used > 0:
                        converted_amt = (converted_amt * rate_used)
                    db.session.add(PaymentSplit(
                        payment=refund,
                        method=(getattr(payment.method, 'value', payment.method) or PaymentMethod.CHEQUE.value),
                        amount=Decimal(str(total_amount or 0)),
                        currency=base,
                        converted_amount=converted_amt,
                        converted_currency='ILS',
                        fx_rate_used=(rate_used if rate_used and rate_used > 0 else None),
                        fx_rate_source=getattr(payment, 'fx_rate_source', None),
                        fx_rate_timestamp=getattr(payment, 'fx_rate_timestamp', None),
                        fx_base_currency=(getattr(payment, 'fx_base_currency', None) or (base if base != 'ILS' else None)),
                        fx_quote_currency=(getattr(payment, 'fx_quote_currency', None) or ('ILS' if base != 'ILS' else None)),
                        details={'auto_refund': True, 'reverse_entry': True}
                    ))
                except Exception:
                    db.session.add(PaymentSplit(
                        payment=refund,
                        method=(getattr(payment.method, 'value', payment.method) or PaymentMethod.CHEQUE.value),
                        amount=Decimal(str(total_amount or 0)),
                        currency=(payment.currency or 'ILS'),
                        converted_amount=Decimal(str(total_amount or 0)),
                        converted_currency='ILS',
                        details={'auto_refund': True, 'reverse_entry': True}
                    ))
        except Exception:
            pass

    def _auto_unrefund_payment(self, payment):
        try:
            refunds = Payment.query.filter(
                Payment.refund_of_id == payment.id,
                Payment.notes.ilike('%[AUTO_REFUND_FROM_BANK=true]%'),
                Payment.status == PaymentStatus.COMPLETED.value
            ).all()
            for r in refunds:
                r.status = PaymentStatus.CANCELLED.value
                r.notes = (r.notes or '') + "\n[REVERSAL_ON_RESUBMIT=true]"
                db.session.add(r)
        except Exception:
            pass

    def _auto_refund_split(self, payment, split):
        try:
            existing = Payment.query.filter(
                Payment.refund_of_id == payment.id,
                Payment.notes.ilike('%[AUTO_REFUND_FROM_BANK=true]%'),
                Payment.status != PaymentStatus.CANCELLED.value
            ).first()
            if existing:
                return
            direction = PaymentDirection.OUT.value if payment.direction == PaymentDirection.IN.value else PaymentDirection.IN.value
            entity_name = None
            try:
                entity_name = (
                    getattr(getattr(payment, 'customer', None), 'name', None) or
                    getattr(getattr(payment, 'supplier', None), 'name', None) or
                    getattr(getattr(payment, 'partner', None), 'name', None)
                )
            except Exception:
                entity_name = None
            # تفاصيل الشيك لإضافتها للملاحظات
            check_num = getattr(payment, 'check_number', None)
            check_bank = getattr(payment, 'check_bank', None)
            try:
                det = getattr(split, 'details', {}) or {}
                if isinstance(det, str):
                    import json as _json
                    try:
                        det = _json.loads(det)
                    except Exception:
                        det = {}
                check_num = check_num or (det.get('check_number') or None)
                check_bank = check_bank or (det.get('check_bank') or None)
            except Exception:
                pass
            reverse_note = f"\nعكس قيد لل{('عميل' if payment.customer_id else ('مورد' if payment.supplier_id else ('شريك' if payment.partner_id else 'جهة')))} {entity_name or ''} بسبب ارجاع الشيك".strip()
            if check_num or check_bank:
                reverse_note += f" (رقم {check_num or '—'} بنك {check_bank or '—'} من البنك)"
            refund = Payment(
                entity_type=payment.entity_type,
                customer_id=payment.customer_id,
                supplier_id=payment.supplier_id,
                partner_id=payment.partner_id,
                sale_id=payment.sale_id,
                invoice_id=payment.invoice_id,
                service_id=payment.service_id,
                expense_id=payment.expense_id,
                preorder_id=payment.preorder_id,
                shipment_id=payment.shipment_id,
                loan_settlement_id=payment.loan_settlement_id,
                direction=direction,
                status=PaymentStatus.COMPLETED.value,
                payment_date=datetime.utcnow(),
                total_amount=float(Decimal(str(getattr(split, 'amount', 0) or 0))),
                currency=(payment.currency or 'ILS'),
                method=(getattr(split.method, 'value', split.method) or PaymentMethod.CHEQUE.value),
                reference=(
                    f"قيد عكسي بسبب ارجاع شيك رقم {check_num or '—'} بنك {check_bank or '—'} من البنك"
                    if (check_num or check_bank) else f"عكس تلقائي لجزء #{split.id} من الدفعة #{payment.id} بسبب مرتجع بنك"
                ),
                notes=((payment.notes or '') + "\n[AUTO_REFUND_FROM_BANK=true]" + reverse_note),
                refund_of_id=payment.id,
                receiver_name=getattr(payment, 'receiver_name', None),
                deliverer_name=getattr(payment, 'deliverer_name', None),
            )
            try:
                if payment.currency and payment.currency != 'ILS':
                    refund.fx_rate_used = payment.fx_rate_used
                    refund.fx_rate_source = getattr(payment, 'fx_rate_source', None) or 'original'
                    refund.fx_rate_timestamp = datetime.utcnow()
                    refund.fx_base_currency = payment.fx_base_currency or payment.currency
                    refund.fx_quote_currency = 'ILS'
            except Exception:
                pass
            from routes.payments import _ensure_payment_number
            _ensure_payment_number(refund)
            db.session.add(refund)
            try:
                det = getattr(split, 'details', {}) or {}
                if isinstance(det, str):
                    import json as _json
                    try:
                        det = _json.loads(det)
                    except Exception:
                        det = {}
                det.update({'auto_refund': True, 'reverse_entry': True})
                db.session.add(PaymentSplit(
                    payment=refund,
                    method=split.method,
                    amount=split.amount,
                    currency=split.currency,
                    converted_amount=(split.converted_amount or Decimal(str(getattr(split, 'amount', 0) or 0))),
                    converted_currency=(split.converted_currency or 'ILS'),
                    fx_rate_used=getattr(split, 'fx_rate_used', None),
                    fx_rate_source=getattr(split, 'fx_rate_source', None),
                    fx_rate_timestamp=getattr(split, 'fx_rate_timestamp', None),
                    fx_base_currency=getattr(split, 'fx_base_currency', None),
                    fx_quote_currency=getattr(split, 'fx_quote_currency', None),
                    details=det
                ))
            except Exception:
                db.session.add(PaymentSplit(
                    payment=refund,
                    method=split.method,
                    amount=split.amount,
                    currency=split.currency,
                    converted_amount=Decimal(str(getattr(split, 'converted_amount', 0) or getattr(split, 'amount', 0) or 0)),
                    converted_currency=(getattr(split, 'converted_currency', None) or 'ILS'),
                    details={'auto_refund': True, 'reverse_entry': True}
                ))
        except Exception:
            pass

    def _auto_unrefund_split(self, payment, split):
        try:
            refunds = Payment.query.filter(
                Payment.refund_of_id == payment.id,
                Payment.notes.ilike('%[AUTO_REFUND_FROM_BANK=true]%'),
                Payment.status == PaymentStatus.COMPLETED.value
            ).all()
            for r in refunds:
                r.status = PaymentStatus.CANCELLED.value
                r.notes = (r.notes or '') + "\n[REVERSAL_ON_RESUBMIT=true]"
                db.session.add(r)
        except Exception:
            pass

    # تم إزالة منطق إنشاء دفعات عكس تلقائية؛ سيتم إنشاء قيود دفتر الأستاذ مباشرة عند تغيير حالة الشيك

    def _ledger_source_id(self, ctx):
        if ctx.manual:
            return ctx.manual.id
        if ctx.split:
            return ctx.split.id
        if ctx.payment:
            return ctx.payment.id
        if ctx.expense:
            return ctx.expense.id
        return ctx.token

    def _update_balance(self, entity_type, entity_id):
        try:
            entity_type_lower = entity_type.lower() if entity_type else ""
            if entity_type_lower == "customer":
                from utils.customer_balance_updater import update_customer_balance_components
                SessionFactory = sessionmaker(bind=db.engine)
                session = SessionFactory()
                try:
                    update_customer_balance_components(entity_id, session)
                    session.commit()
                    customer = session.get(Customer, entity_id)
                    return float(customer.current_balance or 0) if customer else None
                finally:
                    session.close()
            else:
                return utils.update_entity_balance(entity_type_lower, entity_id)
        except Exception:
            return None

    def _history_entry(self, status):
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'status': status,
        }
        if self.actor:
            entry['user'] = self.actor.username
        return entry

    def _compose_note(self, status, note_text, label):
        label_part = f"{label} " if label else ''
        marker = self.STATUS_MARKERS.get(status, '\u21bb')
        status_label = CHECK_STATUS.get(status, {}).get('ar', status)
        line = f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {marker} {label_part}حالة الشيك: {status_label}"
        if note_text:
            line += f"\n   💬 {note_text}"
        if self.actor:
            line += f"\n   👤 {self.actor.username}"
        line += f"\n   [STATE={status}]"
        return line

    def _has_state_record(self, ctx, status):
        status = (status or '').upper()
        if not status:
            return False
        if ctx.kind == 'payment_split' and ctx.split:
            details = self._load_split_details(ctx.split)
            history = details.get('check_history') or []
            return any((entry.get('status') or '').upper() == status for entry in history)
        if ctx.kind == 'payment' and ctx.payment:
            return self._notes_state_marker(ctx.payment.notes, status)
        if ctx.kind == 'expense' and ctx.expense:
            return self._notes_state_marker(ctx.expense.notes, status)
        if ctx.kind == 'manual' and ctx.manual:
            try:
                history = ctx.manual.get_status_history()
            except Exception:
                history = []
            if history:
                return any((entry.get('new_status') or '').upper() == status for entry in history)
            return self._notes_state_marker(ctx.manual.notes, status)
        return False

    def _notes_state_marker(self, notes, status):
        marker = f"[STATE={status}]"
        return marker in (notes or '')
    
    def _count_state_records(self, ctx, status):
        """حساب عدد مرات ظهور حالة معينة في السجل"""
        status = (status or '').upper()
        if not status:
            return 0
        count = 0
        if ctx.kind == 'payment_split' and ctx.split:
            details = self._load_split_details(ctx.split)
            history = details.get('check_history') or []
            count = sum(1 for entry in history if (entry.get('status') or '').upper() == status)
        elif ctx.kind == 'payment' and ctx.payment:
            notes = ctx.payment.notes or ''
            marker = f"[STATE={status}]"
            count = notes.count(marker)
        elif ctx.kind == 'expense' and ctx.expense:
            notes = ctx.expense.notes or ''
            marker = f"[STATE={status}]"
            count = notes.count(marker)
        elif ctx.kind == 'manual' and ctx.manual:
            try:
                history = ctx.manual.get_status_history()
            except Exception:
                history = []
            if history:
                count = sum(1 for entry in history if (entry.get('new_status') or '').upper() == status)
            else:
                notes = ctx.manual.notes or ''
                marker = f"[STATE={status}]"
                count = notes.count(marker)
        return count
    
    def _get_resubmit_allowed_count(self, ctx):
        if ctx.kind == 'manual' and ctx.manual:
            count = getattr(ctx.manual, 'resubmit_allowed_count', None)
            if count is None:
                return 1
            return int(count) if count else 1
        return 1
    
    def _get_legal_return_allowed_count(self, ctx):
        """الحصول على عدد مرات السماح بالرجوع من الحالة القانونية"""
        if ctx.kind == 'manual' and ctx.manual:
            return getattr(ctx.manual, 'legal_return_allowed_count', 1) or 1
        return 1
    
    def _current_status(self, ctx):
        if ctx.kind == 'manual' and ctx.manual:
            return self._normalize_status(getattr(ctx.manual, 'status', None))
        if ctx.kind == 'payment_split' and ctx.split:
            details = self._load_split_details(ctx.split)
            value = details.get('check_status')
            if value:
                return self._normalize_status(value)
        if ctx.kind == 'expense' and ctx.expense:
            text_status = self._guess_status_from_notes(ctx.expense.notes)
            if text_status:
                return text_status
        if ctx.payment:
            mapped = self._normalize_status(getattr(ctx.payment, 'status', None))
            return self._status_from_payment(mapped)
        return 'PENDING'

    def _status_from_payment(self, payment_status):
        if payment_status == PaymentStatus.COMPLETED.value:
            return 'CASHED'
        if payment_status == PaymentStatus.FAILED.value:
            return 'RETURNED'
        if payment_status == PaymentStatus.CANCELLED.value:
            return 'CANCELLED'
        if payment_status == PaymentStatus.PENDING.value:
            return 'PENDING'
        return 'PENDING'

    def _normalize_status(self, value):
        if value is None:
            return None
        if hasattr(value, 'value'):
            value = value.value
        return str(value).upper()

    def _resolve(self, identifier):
        token = str(identifier).strip()
        prefix, numeric = self._decode_token(token)
        if prefix == 'payment':
            return self._ctx_from_payment(token, self._fetch_payment(numeric))
        if prefix == 'split':
            return self._ctx_from_split(token, self._fetch_split(numeric))
        if prefix == 'expense':
            return self._ctx_from_expense(token, self._fetch_expense(numeric))
        if prefix == 'check':
            return self._ctx_from_manual(token, self._fetch_manual(numeric))
        return self._resolve_numeric(token)

    def _resolve_numeric(self, token):
        numeric = self._safe_int(token)
        if numeric is None:
            raise CheckValidationError(f'معرف غير صالح: {token}', code='INVALID_IDENTIFIER')
        split = PaymentSplit.query.get(numeric)
        if split and self._is_cheque_split(split):
            return self._ctx_from_split(token, split)
        expense = Expense.query.get(numeric)
        if expense and self._is_cheque_expense(expense):
            return self._ctx_from_expense(token, expense)
        manual = Check.query.get(numeric)
        if manual:
            return self._ctx_from_manual(token, manual)
        payment = Payment.query.get(numeric)
        if payment and self._is_cheque_payment(payment):
            return self._ctx_from_payment(token, payment)
        raise CheckValidationError(f'لم يتم العثور على الشيك المطلوب بالمعرف: {token}', code='CHECK_NOT_FOUND')

    def _ctx_from_payment(self, token, payment):
        entity_type, entity_id, entity_name = self._entity_from_payment(payment)
        direction = getattr(payment.direction, 'value', payment.direction)
        amount = Decimal(str(payment.total_amount or 0))
        currency = payment.currency or 'ILS'
        return CheckActionContext(
            token=token,
            kind='payment',
            payment=payment,
            direction=direction or PaymentDirection.IN.value,
            amount=amount,
            currency=currency,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
        )

    def _ctx_from_split(self, token, split):
        payment = split.payment
        entity_type, entity_id, entity_name = self._entity_from_payment(payment)
        direction = getattr(payment.direction, 'value', payment.direction)
        amount = Decimal(str(split.amount or 0))
        currency = split.currency or payment.currency or 'ILS'
        return CheckActionContext(
            token=token,
            kind='payment_split',
            payment=payment,
            split=split,
            direction=direction or PaymentDirection.IN.value,
            amount=amount,
            currency=currency,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
        )

    def _ctx_from_expense(self, token, expense):
        entity_type = None
        entity_id = None
        entity_name = expense.payee_name or expense.paid_to or ''
        if expense.supplier_id:
            entity_type = 'SUPPLIER'
            entity_id = expense.supplier_id
            if expense.supplier:
                entity_name = expense.supplier.name
        elif expense.partner_id:
            entity_type = 'PARTNER'
            entity_id = expense.partner_id
            if expense.partner:
                entity_name = expense.partner.name
        elif expense.customer_id:
            entity_type = 'CUSTOMER'
            entity_id = expense.customer_id
            if expense.customer:
                entity_name = expense.customer.name
        amount = Decimal(str(expense.amount or 0))
        currency = expense.currency or 'ILS'
        return CheckActionContext(
            token=token,
            kind='expense',
            expense=expense,
            direction=PaymentDirection.OUT.value,
            amount=amount,
            currency=currency,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
        )

    def _ctx_from_manual(self, token, manual):
        direction = getattr(manual.direction, 'value', manual.direction)
        amount = Decimal(str(manual.amount or 0))
        currency = manual.currency or 'ILS'
        entity_type = manual.entity_type
        entity_id = manual.entity_id
        entity_name = manual.entity_name
        if entity_type:
            entity_type = entity_type.upper()
        return CheckActionContext(
            token=token,
            kind='manual',
            manual=manual,
            direction=direction or PaymentDirection.IN.value,
            amount=amount,
            currency=currency,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
        )

    def _entity_from_payment(self, payment):
        if payment.customer_id:
            name = payment.customer.name if payment.customer else ''
            return 'CUSTOMER', payment.customer_id, name
        if payment.supplier_id:
            name = payment.supplier.name if payment.supplier else ''
            return 'SUPPLIER', payment.supplier_id, name
        if payment.partner_id:
            name = payment.partner.name if payment.partner else ''
            return 'PARTNER', payment.partner_id, name
        sale = getattr(payment, 'sale', None)
        if sale and sale.customer_id:
            name = sale.customer.name if getattr(sale, 'customer', None) else ''
            return 'CUSTOMER', sale.customer_id, name
        invoice = getattr(payment, 'invoice', None)
        if invoice and invoice.customer_id:
            customer = getattr(invoice, 'customer', None)
            name = customer.name if customer else ''
            return 'CUSTOMER', invoice.customer_id, name
        preorder = getattr(payment, 'preorder', None)
        if preorder and preorder.customer_id:
            customer = getattr(preorder, 'customer', None)
            name = customer.name if customer else ''
            return 'CUSTOMER', preorder.customer_id, name
        service = getattr(payment, 'service', None)
        if service and service.customer_id:
            customer = getattr(service, 'customer', None)
            name = customer.name if customer else ''
            return 'CUSTOMER', service.customer_id, name
        return None, None, ''

    def _load_split_details(self, split):
        details = split.details or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}
        if not isinstance(details, dict):
            details = {}
        return dict(details)

    def _guess_status_from_notes(self, notes_text):
        if not notes_text:
            return None
        lower = notes_text.lower()
        if 'تم الصرف' in lower or 'مسحوب' in lower or 'cashed' in lower:
            return 'CASHED'
        if 'مرتجع' in lower or 'returned' in lower:
            return 'RETURNED'
        if 'مرفوض' in lower or 'bounced' in lower:
            return 'BOUNCED'
        if 'أعيد' in lower or 'resubmitted' in lower:
            return 'RESUBMITTED'
        if 'ملغي' in lower or 'cancelled' in lower:
            return 'CANCELLED'
        if 'مؤرشف' in lower or 'archived' in lower:
            return 'ARCHIVED'
        return None

    def _decode_token(self, token):
        lowered = token.lower()
        if lowered.startswith('payment-split-'):
            return 'split', self._safe_int(token.split('-')[-1])
        if lowered.startswith('split-'):
            return 'split', self._safe_int(token.split('-')[-1])
        if lowered.startswith('expense-'):
            return 'expense', self._safe_int(token.split('-')[-1])
        if lowered.startswith('check-'):
            return 'check', self._safe_int(token.split('-')[-1])
        if lowered.startswith('payment-'):
            return 'payment', self._safe_int(token.split('-')[-1])
        return None, None

    def _fetch_payment(self, pid):
        if pid is None:
            raise CheckValidationError('دفعة غير معروفة: معرف فارغ', code='EMPTY_PAYMENT_ID')
        payment = Payment.query.get(pid)
        if not payment:
            raise CheckValidationError(f'الدفعة غير موجودة: {pid}', code='PAYMENT_NOT_FOUND')
        if not self._is_cheque_payment(payment):
            raise CheckValidationError(f'الدفعة #{pid} ليست شيكاً', code='NOT_A_CHEQUE_PAYMENT')
        return payment

    def _fetch_split(self, sid):
        if sid is None:
            raise CheckValidationError('الجزء غير معروف: معرف فارغ', code='EMPTY_SPLIT_ID')
        split = PaymentSplit.query.get(sid)
        if not split:
            raise CheckValidationError(f'الجزء غير موجود: {sid}', code='SPLIT_NOT_FOUND')
        if not self._is_cheque_split(split):
            raise CheckValidationError(f'الجزء #{sid} ليس شيكاً', code='NOT_A_CHEQUE_SPLIT')
        return split

    def _fetch_expense(self, eid):
        if eid is None:
            raise CheckValidationError('المصروف غير معروف: معرف فارغ', code='EMPTY_EXPENSE_ID')
        exp = Expense.query.get(eid)
        if not exp:
            raise CheckValidationError(f'المصروف غير موجود: {eid}', code='EXPENSE_NOT_FOUND')
        if not self._is_cheque_expense(exp):
            raise CheckValidationError(f'المصروف #{eid} ليس شيكاً', code='NOT_A_CHEQUE_EXPENSE')
        return exp

    def _fetch_manual(self, cid):
        if cid is None:
            raise CheckValidationError('شيك غير معروف: معرف فارغ', code='EMPTY_CHECK_ID')
        chk = Check.query.get(cid)
        if not chk:
            raise CheckValidationError(f'لم يتم العثور على الشيك اليدوي: {cid}', code='MANUAL_CHECK_NOT_FOUND')
        return chk

    def _is_cheque_payment(self, payment):
        method = getattr(payment.method, 'value', payment.method)
        if method and method.upper() == PaymentMethod.CHEQUE.value:
            return True
        if any(getattr(s.method, 'value', s.method) == PaymentMethod.CHEQUE.value for s in payment.splits or []):
            return True
        return False

    def _is_cheque_split(self, split):
        method = getattr(split.method, 'value', split.method)
        return method == PaymentMethod.CHEQUE.value

    def _is_cheque_expense(self, expense):
        method = (expense.payment_method or '').lower()
        return method in ('cheque', 'check')

    def _safe_int(self, value):
        try:
            return int(str(value))
        except Exception:
            return None


def _build_check_groups(checks):
    def _add(bucket, key, amount):
        entry = bucket.setdefault(key, {"count": 0, "amount": 0.0})
        entry["count"] += 1
        entry["amount"] += amount

    direction_totals = {"in": {"count": 0, "amount": 0.0}, "out": {"count": 0, "amount": 0.0}}
    status_totals = {}
    source_totals = {}

    for item in checks:
        amount = float(item.get("converted_amount") or item.get("amount") or 0)
        direction_key = (item.get("direction_en") or "").lower()
        if direction_key in direction_totals:
            direction_totals[direction_key]["count"] += 1
            direction_totals[direction_key]["amount"] += amount
        status_key = (item.get("status") or "").lower()
        if status_key:
            _add(status_totals, status_key, amount)
        source_key = (item.get("type") or "").lower() or "unknown"
        _add(source_totals, source_key, amount)

    for bucket in (direction_totals, status_totals, source_totals):
        for info in bucket.values():
            info["amount"] = round(info["amount"], 2)

    return {
        "direction": direction_totals,
        "status": status_totals,
        "source": source_totals,
}


@checks_bp.route('/')
def index():
    """صفحة عرض الشيكات"""
    return render_template('checks/index.html', is_owner=_current_user_is_owner())


@checks_bp.route('/api/checks')
@login_required
def get_checks():
    """
    API لجلب الشيكات من جميع المصادر مع الفلاتر
    المصادر: Payment + Expense + Check (اليدوي)
    """
    try:
        direction = request.args.get('direction')
        status = request.args.get('status')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        source_filter = request.args.get('source')
        
        checks = []
        today = datetime.now(timezone.utc).date()
        check_ids = set()

        current_app.logger.info(f"🔍 get_checks API - بدء الجلب من جميع المصادر...")
        
        if not source_filter or source_filter in ['all', 'payment']:
            parsed_from = None
            parsed_to = None
            if from_date:
                try:
                    parsed_from = datetime.strptime(from_date, '%Y-%m-%d').date()
                except Exception:
                    parsed_from = None
            if to_date:
                try:
                    parsed_to = datetime.strptime(to_date, '%Y-%m-%d').date()
                except Exception:
                    parsed_to = None

            def _extract_manual_status(notes_text: str | None) -> str | None:
                if not notes_text:
                    return None
                try:
                    lines = [ln.strip() for ln in notes_text.splitlines() if ln.strip()]
                except Exception:
                    lines = []
                for line in reversed(lines):
                    if 'حالة الشيك:' not in line:
                        continue
                    label = line.split('حالة الشيك:')[-1].strip()
                    if 'مسحوب' in label:
                        return 'CASHED'
                    if 'مرتجع' in label:
                        return 'RETURNED'
                    if 'ملغي' in label:
                        return 'CANCELLED'
                    if 'أعيد' in label or 'معاد' in label:
                        return 'RESUBMITTED'
                    if 'مؤرشف' in label:
                        return 'CANCELLED'
                return None

            def _status_snapshot(manual_status: str | None, status_value: str | None, due_days: int | None):
                manual = (manual_status or '').upper()
                if manual in {'RETURNED', 'BOUNCED'}:
                    return 'RETURNED', 'مرتجع', 'warning'
                if manual == 'CANCELLED':
                    return 'CANCELLED', 'ملغي', 'secondary'
                if manual == 'RESUBMITTED':
                    if due_days is not None:
                        if due_days < 0:
                            return 'OVERDUE', 'متأخر', 'danger'
                        if due_days <= 7:
                            return 'DUE_SOON', 'قريب الاستحقاق', 'warning'
                    return 'PENDING', 'معلق', 'info'
                if manual == 'ARCHIVED':
                    return 'CANCELLED', 'ملغي', 'secondary'
                if manual == 'CASHED':
                    # إذا كان الشيك مسحوب، يجب أن يظهر كمسحوب بغض النظر عن ميعاد الاستحقاق
                    return 'CASHED', 'تم الصرف', 'success'

                if due_days is not None:
                    if due_days < 0:
                        return 'OVERDUE', 'متأخر', 'danger'
                    if due_days <= 7:
                        return 'DUE_SOON', 'قريب الاستحقاق', 'warning'
                return 'PENDING', 'معلق', 'info'

            def _resolve_entity(payment):
                if payment.customer:
                    name = payment.customer.name
                    return name, 'عميل', f"/customers/{payment.customer.id}", 'CUSTOMER', payment.customer.id
                sale = getattr(payment, 'sale', None)
                if sale and getattr(sale, 'customer', None):
                    name = sale.customer.name
                    return name, 'عميل', f"/customers/{sale.customer.id}", 'CUSTOMER', sale.customer.id
                invoice = getattr(payment, 'invoice', None)
                if invoice and getattr(invoice, 'customer', None):
                    name = invoice.customer.name
                    return name, 'عميل', f"/customers/{invoice.customer.id}", 'CUSTOMER', invoice.customer.id
                preorder = getattr(payment, 'preorder', None)
                if preorder and getattr(preorder, 'customer', None):
                    name = preorder.customer.name
                    return name, 'عميل', f"/customers/{preorder.customer.id}", 'CUSTOMER', preorder.customer.id
                service_request = getattr(payment, 'service', None)
                if service_request and getattr(service_request, 'customer', None):
                    name = service_request.customer.name
                    return name, 'عميل', f"/customers/{service_request.customer.id}", 'CUSTOMER', service_request.customer.id
                if payment.supplier:
                    name = payment.supplier.name
                    return name, 'مورد', f"/vendors/{payment.supplier.id}", 'SUPPLIER', payment.supplier.id
                if payment.partner:
                    name = payment.partner.name
                    return name, 'شريك', f"/partners/{payment.partner.id}", 'PARTNER', payment.partner.id
                return '', '', '', None, None

            def _split_due_date(payment, split):
                details = getattr(split, 'details', {}) or {}
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except Exception:
                        details = {}
                raw_val = details.get('check_due_date') or details.get('due_date')
                if raw_val:
                    try:
                        return datetime.fromisoformat(raw_val).date()
                    except Exception:
                        try:
                            return datetime.strptime(raw_val, '%Y-%m-%d').date()
                        except Exception:
                            return None
                if payment.check_due_date:
                    if isinstance(payment.check_due_date, datetime):
                        return payment.check_due_date.date()
                    return payment.check_due_date
                if payment.payment_date and isinstance(payment.payment_date, datetime):
                    return payment.payment_date.date()
                return None

            payment_query = db.session.query(Payment).options(
                joinedload(Payment.splits),
                joinedload(Payment.customer),
                joinedload(Payment.supplier),
                joinedload(Payment.partner),
                joinedload(Payment.sale),
                joinedload(Payment.invoice),
                joinedload(Payment.preorder),
                joinedload(Payment.service),
            )

            if direction == 'in':
                payment_query = payment_query.filter(Payment.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                payment_query = payment_query.filter(Payment.direction == PaymentDirection.OUT.value)

            if status == 'pending':
                payment_query = payment_query.filter(Payment.status == PaymentStatus.PENDING.value)
            elif status == 'completed':
                payment_query = payment_query.filter(Payment.status == PaymentStatus.COMPLETED.value)
            elif status == 'overdue':
                payment_query = payment_query.filter(
                    and_(
                        Payment.status == PaymentStatus.PENDING.value,
                        Payment.check_due_date < datetime.utcnow()
                    )
                )

            payments = payment_query.filter(
                or_(
                    Payment.method == PaymentMethod.CHEQUE.value,
                    Payment.splits.any(PaymentSplit.method == PaymentMethod.CHEQUE.value)
                )
            ).order_by(
                (Payment.check_due_date.is_(None)).asc(),
                Payment.check_due_date.asc(),
                Payment.payment_date.asc(),
                Payment.id.asc()
            ).all()

            # تحسين الأداء: جلب جميع الشيكات المرتبطة بـ Splits في استعلام واحد
            all_split_ids = []
            for payment in payments:
                for split in payment.splits or []:
                    split_method = getattr(split.method, 'value', split.method)
                    if split_method == PaymentMethod.CHEQUE.value:
                        all_split_ids.append(split.id)
            
            # جلب جميع الشيكات المرتبطة بـ Splits في استعلام واحد
            split_checks_map = {}
            if all_split_ids:
                # بناء شروط البحث بشكل صحيح
                conditions = []
                for sid in all_split_ids:
                    conditions.append(Check.reference_number == f"PMT-SPLIT-{sid}")
                    conditions.append(Check.reference_number.like(f"PMT-SPLIT-{sid}-%"))
                
                if conditions:
                    split_checks = Check.query.filter(or_(*conditions)).all()
                    # إنشاء map للبحث السريع: split_id -> check
                    for check in split_checks:
                        ref = check.reference_number or ''
                        if ref.startswith('PMT-SPLIT-'):
                            split_id_str = ref.replace('PMT-SPLIT-', '').split('-')[0]
                            try:
                                split_id = int(split_id_str)
                                if split_id not in split_checks_map:
                                    split_checks_map[split_id] = check
                            except ValueError:
                                pass

            processed_split_count = 0
            for payment in payments:
                notes_upper_all = (payment.notes or '').upper()
                if getattr(payment, 'refund_of_id', None):
                    continue
                if '[AUTO_REFUND_FROM_BANK=true]' in notes_upper_all:
                    continue
                entity_name, entity_type, entity_link, entity_type_code, entity_id = _resolve_entity(payment)
                status_value = payment.status.value if hasattr(payment.status, 'value') else str(payment.status or '')
                direction_value = payment.direction.value if hasattr(payment.direction, 'value') else str(payment.direction or '')
                is_incoming = direction_value == PaymentDirection.IN.value

                base_due = None
                if payment.check_due_date:
                    base_due = payment.check_due_date.date() if isinstance(payment.check_due_date, datetime) else payment.check_due_date
                elif payment.payment_date and isinstance(payment.payment_date, datetime):
                    base_due = payment.payment_date.date()

                manual_status = _extract_manual_status(payment.notes)

                has_cheque_splits = any(
                    getattr(s.method, 'value', s.method) == PaymentMethod.CHEQUE.value
                    for s in (payment.splits or [])
                )

                # عرض شيك الدفعة الرئيسي فقط إذا لم يكن هناك شيكات جزئية
                if payment.method == PaymentMethod.CHEQUE.value and not has_cheque_splits:
                    due_date = base_due or today
                    days_until_due = (due_date - today).days if due_date else None
                    check_status, status_ar, badge_color = _status_snapshot(manual_status, status_value, days_until_due)

                    skip_entry = False
                    if parsed_from and due_date and due_date < parsed_from:
                        skip_entry = True
                    if parsed_to and due_date and due_date > parsed_to:
                        skip_entry = True
                    if status == 'pending' and (check_status or '').upper() not in ('PENDING', 'DUE_SOON'):
                        skip_entry = True
                    if status == 'completed' and check_status != 'CASHED':
                        skip_entry = True
                    if status == 'overdue' and check_status != 'OVERDUE':
                        skip_entry = True

                    if not skip_entry:
                        key = f"payment-{payment.id}"
                        if key in check_ids:
                            continue
                        check_ids.add(key)
                        checks.append({
                            'token': f'payment-{payment.id}',
                            'id': payment.id,
                            'type': 'payment',
                            'source': 'دفعة',
                            'source_badge': 'primary',
                            'check_number': payment.check_number or '',
                            'check_bank': payment.check_bank or '',
                            'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                            'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                            'amount': float(payment.total_amount or 0),
                            'currency': payment.currency or 'ILS',
                            'fx_rate_issue': float(payment.fx_rate_used) if payment.fx_rate_used else None,
                            'fx_rate_issue_source': payment.fx_rate_source,
                            'fx_rate_issue_timestamp': payment.fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if payment.fx_rate_timestamp else None,
                            'fx_rate_cash': None,
                            'fx_rate_cash_source': None,
                            'fx_rate_cash_timestamp': None,
                            'direction': 'وارد' if is_incoming else 'صادر',
                            'direction_en': 'in' if is_incoming else 'out',
                            'is_incoming': is_incoming,
                            'status': check_status,
                            'status_ar': status_ar,
                            'badge_color': badge_color,
                            'days_until_due': days_until_due if days_until_due is not None else 0,
                            'entity_name': entity_name,
                            'entity_type': entity_type,
                            'entity_link': entity_link,
                            'entity_type_code': entity_type_code or None,
                            'entity_id': entity_id,
                            'drawer_name': 'شركتنا' if not is_incoming else entity_name,
                            'payee_name': entity_name if not is_incoming else 'شركتنا',
                            'description': f"دفعة {'من' if is_incoming else 'إلى'} {entity_name}" + (f" ({entity_type})" if entity_type else ''),
                            'purpose': 'دفعة مالية',
                            'notes': payment.notes or '',
                            'is_settled': '[SETTLED=true]' in (payment.notes or '').upper(),
                            'is_legal': 'دائرة قانونية' in (payment.notes or ''),
                            'created_at': payment.payment_date.strftime('%Y-%m-%d %H:%M') if payment.payment_date else '',
                            'receipt_number': payment.receipt_number or '',
                            'reference': payment.receipt_number or ''
                        })

                # دمج الشيكات المكررة حسب رقم الشيك داخل نفس الدفعة
                split_agg_map = {}
                for split in payment.splits or []:
                    split_method = getattr(split.method, 'value', split.method)
                    if split_method != PaymentMethod.CHEQUE.value:
                        continue

                    # التحقق من حالة الشيك الفعلية من جدول checks إذا كان موجوداً
                    split_manual_status = manual_status  # نبدأ بالحالة من payment.notes
                    # استخدام الـ map للبحث السريع بدلاً من استعلام منفصل
                    split_check = split_checks_map.get(split.id)
                    if split_check:
                        # استخراج حالة الشيك من enum - CheckStatus هو str, enum.Enum
                        check_status_obj = getattr(split_check, 'status', None)
                        if check_status_obj:
                            # استخراج القيمة من enum - CheckStatus.value يعطي القيمة الفعلية
                            split_check_status = (check_status_obj.value if hasattr(check_status_obj, 'value') else str(check_status_obj)).upper()
                        else:
                            split_check_status = 'PENDING'
                        # إذا كان الشيك موجود في جدول checks، نستخدم حالته مباشرة
                        if split_check_status == 'CASHED':
                            split_manual_status = 'CASHED'
                        elif split_check_status in ['RETURNED', 'BOUNCED', 'CANCELLED', 'RESUBMITTED']:
                            split_manual_status = split_check_status
                    
                    # إذا لم يكن هناك شيك في جدول checks، نتحقق من details
                    if not split_check:
                        details = getattr(split, 'details', {}) or {}
                        if isinstance(details, str):
                            try:
                                details = json.loads(details)
                            except Exception:
                                details = {}
                        split_details_status = details.get('check_status')
                        if split_details_status:
                            split_details_status = str(split_details_status).upper()
                            if split_details_status == 'CASHED':
                                split_manual_status = 'CASHED'
                            elif split_details_status in ['RETURNED', 'BOUNCED', 'CANCELLED', 'RESUBMITTED']:
                                split_manual_status = split_details_status

                    due_date = _split_due_date(payment, split) or today
                    days_until_due = (due_date - today).days if due_date else None
                    check_status, status_ar, badge_color = _status_snapshot(split_manual_status, status_value, days_until_due)

                    if parsed_from and due_date and due_date < parsed_from:
                        continue
                    if parsed_to and due_date and due_date > parsed_to:
                        continue
                    if status == 'pending' and (check_status or '').upper() not in ('PENDING', 'DUE_SOON'):
                        continue
                    if status == 'completed' and check_status != 'CASHED':
                        continue
                    if status == 'overdue' and check_status != 'OVERDUE':
                        continue

                    details = getattr(split, 'details', {}) or {}
                    if isinstance(details, str):
                        try:
                            details = json.loads(details)
                        except Exception:
                            details = {}

                    check_number = details.get('check_number') or getattr(payment, 'check_number', '')
                    check_bank = details.get('check_bank') or getattr(payment, 'check_bank', '')
                    split_currency = (getattr(split, 'currency', None) or getattr(payment, 'currency', 'ILS') or 'ILS').upper()
                    converted_currency = (getattr(split, 'converted_currency', None) or getattr(payment, 'currency', 'ILS') or 'ILS').upper()
                    amount = float(getattr(split, 'amount', 0) or 0)
                    converted_amount = getattr(split, 'converted_amount', None)
                    if converted_amount is not None:
                        converted_amount = float(converted_amount or 0)
                    fx_rate_used = getattr(split, 'fx_rate_used', None)
                    fx_rate_source = getattr(split, 'fx_rate_source', None)
                    fx_rate_timestamp = getattr(split, 'fx_rate_timestamp', None)

                    split_key = f"payment-split-{payment.id}-{getattr(split, 'id', '0')}"
                    if split_key in check_ids:
                        continue
                    check_ids.add(split_key)

                    # إذا كان نفس رقم الشيك ظهر سابقاً في نفس الدفعة، نجمع القيم بدلاً من إضافة صف جديد
                    existing_index = split_agg_map.get(check_number) if check_number else None
                    if existing_index is not None:
                        try:
                            prev = checks[existing_index]
                            prev_amt = float(prev.get('amount') or 0)
                            prev_conv = float(prev.get('converted_amount') or 0)
                            prev['amount'] = round(prev_amt + (amount or 0), 2)
                            if converted_amount is not None:
                                prev['converted_amount'] = round(prev_conv + (converted_amount or 0), 2)
                            # اختيار أقرب تاريخ استحقاق
                            prev_days = prev.get('days_until_due')
                            if days_until_due is not None and (prev_days is None or days_until_due < prev_days):
                                prev['days_until_due'] = days_until_due
                                prev['due_date_formatted'] = due_date.strftime('%d/%m/%Y') if due_date else ''
                        except Exception:
                            pass
                        processed_split_count += 1
                        continue
                    entry_index = len(checks)
                    if check_number:
                        split_agg_map[check_number] = entry_index
                    checks.append({
                        'token': f"split-{getattr(split, 'id', 0)}",
                        'id': getattr(split, 'id', 0),
                        'payment_id': payment.id,
                        'type': 'payment_split',
                        'source': 'دفعة جزئية',
                        'source_badge': 'info',
                        'check_number': check_number or '',
                        'check_bank': check_bank or '',
                        'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                        'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                        'amount': amount,
                        'currency': split_currency,
                        'converted_amount': converted_amount,
                        'converted_currency': converted_currency,
                        'fx_rate_issue': float(fx_rate_used) if fx_rate_used else None,
                        'fx_rate_issue_source': fx_rate_source,
                        'fx_rate_issue_timestamp': fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if isinstance(fx_rate_timestamp, datetime) else None,
                        'direction': 'وارد' if is_incoming else 'صادر',
                        'direction_en': 'in' if is_incoming else 'out',
                        'is_incoming': is_incoming,
                        'status': check_status,
                        'status_ar': status_ar,
                        'badge_color': badge_color,
                        'days_until_due': days_until_due if days_until_due is not None else 0,
                        'entity_name': entity_name,
                        'entity_type': entity_type,
                        'entity_link': entity_link,
                        'entity_type_code': entity_type_code or None,
                        'entity_id': entity_id,
                        'drawer_name': 'شركتنا' if not is_incoming else entity_name,
                        'payee_name': entity_name if not is_incoming else 'شركتنا',
                        'description': f"جزء من سند {'من' if is_incoming else 'إلى'} {entity_name}" + (f" ({entity_type})" if entity_type else ''),
                        'purpose': 'دفعة جزئية',
                        'notes': payment.notes or '',
                        'is_settled': '[SETTLED=true]' in (payment.notes or '').upper(),
                        'is_legal': 'دائرة قانونية' in (payment.notes or ''),
                        'created_at': payment.payment_date.strftime('%Y-%m-%d %H:%M') if payment.payment_date else '',
                        'receipt_number': payment.receipt_number or '',
                        'reference': payment.receipt_number or ''
                    })
                    processed_split_count += 1

            current_app.logger.info(f"📊 تم تضمين {processed_split_count} شيكات من الدفعات الجزئية")
        
        if not source_filter or source_filter in ['all', 'expense']:
            expense_checks = Expense.query.filter(
                Expense.payment_method == 'cheque'
            )
            
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    expense_checks = expense_checks.filter(Expense.check_due_date >= from_dt)
                except Exception:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    expense_checks = expense_checks.filter(Expense.check_due_date <= to_dt)
                except Exception:
                    pass
            
            for expense in expense_checks.all():
                if not expense.check_due_date:
                    continue
                
                due_date = expense.check_due_date.date() if isinstance(expense.check_due_date, datetime) else expense.check_due_date
                days_until_due = (due_date - today).days
                
                is_paid = expense.is_paid if hasattr(expense, 'is_paid') else False
                notes_lower = (expense.notes or '').lower()
                
                if is_paid:
                    check_status = 'CASHED'
                    status_ar = 'تم الصرف'
                    badge_color = 'success'
                elif 'مرتجع' in notes_lower or 'returned' in notes_lower:
                    check_status = 'RETURNED'
                    status_ar = 'مرتجع'
                    badge_color = 'warning'
                elif 'مرفوض' in notes_lower or 'bounced' in notes_lower:
                    check_status = 'BOUNCED'
                    status_ar = 'مرفوض'
                    badge_color = 'danger'
                elif 'ملغي' in notes_lower or 'cancelled' in notes_lower:
                    check_status = 'CANCELLED'
                    status_ar = 'ملغي'
                    badge_color = 'secondary'
                elif days_until_due < 0:
                    check_status = 'OVERDUE'
                    status_ar = 'متأخر'
                    badge_color = 'danger'
                elif days_until_due <= 7:
                    check_status = 'DUE_SOON'
                    status_ar = 'قريب الاستحقاق'
                    badge_color = 'warning'
                else:
                    check_status = 'PENDING'
                    status_ar = 'معلق'
                    badge_color = 'info'
                
                check_key = f"expense-{expense.id}"
                if check_key in check_ids:
                    continue
                check_ids.add(check_key)
                
                entity_type_code = None
                entity_id = None
                if expense.supplier_id:
                    entity_type_code = 'SUPPLIER'
                    entity_id = expense.supplier_id
                elif expense.partner_id:
                    entity_type_code = 'PARTNER'
                    entity_id = expense.partner_id
                elif expense.customer_id:
                    entity_type_code = 'CUSTOMER'
                    entity_id = expense.customer_id
                
                checks.append({
                    'token': f'expense-{expense.id}',
                    'id': expense.id,
                    'type': 'expense',
                    'source': 'مصروف',
                    'source_badge': 'danger',
                    'check_number': expense.check_number or '',
                    'check_bank': expense.check_bank or '',
                    'check_due_date': due_date.strftime('%Y-%m-%d'),
                    'due_date_formatted': due_date.strftime('%d/%m/%Y'),
                    'amount': float(expense.amount or 0),
                    'currency': expense.currency or 'ILS',
                    'fx_rate_issue': float(expense.fx_rate_used) if expense.fx_rate_used else None,
                    'fx_rate_issue_source': expense.fx_rate_source,
                    'fx_rate_issue_timestamp': expense.fx_rate_timestamp.strftime('%Y-%m-%d %H:%M') if expense.fx_rate_timestamp else None,
                    'fx_rate_cash': None,
                    'fx_rate_cash_source': None,
                    'fx_rate_cash_timestamp': None,
                    'direction': 'صادر',
                    'direction_en': 'out',
                    'is_incoming': False,
                    'status': check_status,
                    'status_ar': status_ar,
                    'badge_color': badge_color,
                    'days_until_due': days_until_due,
                    'entity_name': expense.paid_to or expense.payee_name or '',
                    'entity_type': 'مصروف',
                    'entity_link': '',
                    'entity_type_code': entity_type_code,
                    'entity_id': entity_id,
                    'notes': expense.description or expense.notes or '',
                    'is_settled': '[SETTLED=true]' in ((expense.notes or expense.description or '').upper()),
                    'is_legal': 'دائرة قانونية' in (expense.notes or expense.description or ''),
                    'created_at': expense.date.strftime('%Y-%m-%d') if expense.date else '',
                    'receipt_number': expense.tax_invoice_number or ''
                })
        
        if not source_filter or source_filter in ['all', 'manual']:
            # عرض الشيكات اليدوية فقط (تخطي الشيكات المرتبطة بـ Splits لأنها تظهر من PaymentSplit)
            manual_checks_query = Check.query.filter(
                and_(
                    Check.payment_id.is_(None),
                    or_(
                        Check.reference_number.is_(None),
                        ~Check.reference_number.like('PMT-SPLIT-%')
                    )
                )
            )

            if direction == 'in':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.IN.value)
            elif direction == 'out':
                manual_checks_query = manual_checks_query.filter(Check.direction == PaymentDirection.OUT.value)
            
            if status == 'pending':
                manual_checks_query = manual_checks_query.filter(Check.status == CheckStatus.PENDING.value)
            elif status == 'completed':
                manual_checks_query = manual_checks_query.filter(Check.status == CheckStatus.CASHED.value)
            elif status == 'overdue':
                manual_checks_query = manual_checks_query.filter(
                    and_(
                        Check.status == CheckStatus.PENDING.value,
                        Check.check_due_date < datetime.utcnow()
                    )
                )
            
            if from_date:
                try:
                    from_dt = datetime.strptime(from_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date >= from_dt)
                except Exception:
                    pass
            
            if to_date:
                try:
                    to_dt = datetime.strptime(to_date, '%Y-%m-%d')
                    manual_checks_query = manual_checks_query.filter(Check.check_due_date <= to_dt)
                except Exception:
                    pass
            
            for check in manual_checks_query.all():
                due_date = None
                if check.check_due_date:
                    if isinstance(check.check_due_date, datetime):
                        due_date = check.check_due_date.date()
                    else:
                        due_date = check.check_due_date
                if not due_date:
                    due_date = today
                days_until_due = (due_date - today).days if due_date else None

                status_value = check.status.value if hasattr(check.status, 'value') else str(check.status or '')
                manual_status = status_value
                check_status, status_ar, badge_color = _status_snapshot(manual_status, status_value, days_until_due)

                entity_name = check.entity_name
                entity_type_code_raw = (check.entity_type or '').lower()
                entity_link = ''
                entity_type = ''

                if entity_type_code_raw == 'customer':
                    entity_type = 'عميل'
                    entity_link = f'/customers/{check.entity_id}'
                elif entity_type_code_raw == 'supplier':
                    entity_type = 'مورد'
                    entity_link = f'/vendors/suppliers/{check.entity_id}'
                elif entity_type_code_raw == 'partner':
                    entity_type = 'شريك'
                    entity_link = f'/vendors/partners/{check.entity_id}'
                else:
                    entity_type = 'ساحب' if check.direction == PaymentDirection.IN.value else 'مستفيد'
                resolved_entity_type_code = entity_type_code_raw.upper() if entity_type_code_raw else None

                check_key = f"check-{check.id}"
                if check_key in check_ids:
                    continue
                check_ids.add(check_key)

                checks.append({
                    'token': f'check-{check.id}',
                    'id': check.id,
                    'type': 'manual',
                    'source': 'يدوي',
                    'source_badge': 'success',
                    'check_number': check.check_number,
                    'check_bank': check.check_bank,
                    'check_due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                    'due_date_formatted': due_date.strftime('%d/%m/%Y') if due_date else '',
                    'amount': float(check.amount or 0),
                    'currency': check.currency or 'ILS',
                    'fx_rate_issue': float(check.fx_rate_issue) if check.fx_rate_issue else None,
                    'fx_rate_issue_source': check.fx_rate_issue_source,
                    'fx_rate_issue_timestamp': check.fx_rate_issue_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_issue_timestamp else None,
                    'fx_rate_cash': float(check.fx_rate_cash) if check.fx_rate_cash else None,
                    'fx_rate_cash_source': check.fx_rate_cash_source,
                    'fx_rate_cash_timestamp': check.fx_rate_cash_timestamp.strftime('%Y-%m-%d %H:%M') if check.fx_rate_cash_timestamp else None,
                    'direction': 'وارد' if check.direction == PaymentDirection.IN.value else 'صادر',
                    'direction_en': (check.direction.value if hasattr(check.direction, 'value') else str(check.direction)).lower(),
                    'is_incoming': check.direction == PaymentDirection.IN.value,
                    'status': check_status,
                    'status_ar': status_ar,
                    'badge_color': badge_color,
                    'days_until_due': days_until_due if days_until_due is not None else 0,
                    'entity_name': entity_name,
                    'entity_type': entity_type,
                    'entity_link': entity_link,
                    'entity_type_code': resolved_entity_type_code,
                    'entity_id': check.entity_id,
                    'notes': check.notes or '',
                    'is_settled': '[SETTLED=true]' in (check.notes or '').upper(),
                    'is_legal': 'دائرة قانونية' in (check.notes or ''),
                    'created_at': check.created_at.strftime('%Y-%m-%d') if check.created_at else '',
                    'receipt_number': check.reference_number or ''
                })
        
        # إزالة التكرارات حسب رقم الشيك + الجهة + تاريخ الاستحقاق (تجميع الأجزاء لنفس الشيك)
        try:
            unique_map = {}
            aggregated = []
            for chk in checks:
                cn = (chk.get('check_number') or '').strip()
                en = (chk.get('entity_name') or '').strip()
                dd = (chk.get('due_date_formatted') or '').strip()
                key = f"{cn}|{en}|{dd}"
                if not cn:
                    aggregated.append(chk)
                    continue
                idx = unique_map.get(key)
                if idx is None:
                    unique_map[key] = len(aggregated)
                    aggregated.append(chk)
                else:
                    try:
                        prev = aggregated[idx]
                        # جمع المبالغ الأساسية
                        prev_amt = float(prev.get('amount') or 0)
                        cur_amt = float(chk.get('amount') or 0)
                        prev['amount'] = round(prev_amt + cur_amt, 2)
                        # جمع المبالغ المحوّلة إن وجدت
                        prev_conv = float(prev.get('converted_amount') or 0)
                        cur_conv = float(chk.get('converted_amount') or 0)
                        if (chk.get('converted_amount') is not None) or (prev.get('converted_amount') is not None):
                            prev['converted_amount'] = round(prev_conv + cur_conv, 2)
                        # اختيار الاتجاه: إذا وُجد أي وارد، يبقى وارد
                        prev_in = bool(prev.get('is_incoming'))
                        cur_in = bool(chk.get('is_incoming'))
                        merged_in = prev_in or cur_in
                        prev['is_incoming'] = merged_in
                        prev['direction'] = 'وارد' if merged_in else 'صادر'
                        prev['direction_en'] = 'in' if merged_in else 'out'
                    except Exception:
                        pass
            checks = aggregated
        except Exception:
            pass

        checks.sort(key=lambda x: x['check_due_date'])
        
        return jsonify({
            'success': True,
            'checks': checks,
            'total': len(checks),
            'groups': _build_check_groups(checks),
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching checks: {str(e)}")
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/statistics')
@login_required
def get_statistics():
    """
    API للحصول على إحصائيات الشيكات
    """
    try:
        today = datetime.utcnow().date()
        week_ahead = today + timedelta(days=7)
        month_ahead = today + timedelta(days=30)
        
        from decimal import Decimal
        from models import convert_amount
        
        incoming_checks = db.session.query(Payment).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).all()
        
        incoming_total = Decimal('0.00')
        incoming_overdue = 0
        incoming_overdue_amount = Decimal('0.00')
        
        for p in incoming_checks:
            amt = Decimal(str(p.total_amount or 0))
            if p.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            incoming_total += amt_ils
            if p.check_due_date and p.check_due_date < datetime.now(timezone.utc):
                incoming_overdue += 1
                incoming_overdue_amount += amt_ils
        
        incoming_total = float(incoming_total)
        incoming_overdue_amount = float(incoming_overdue_amount)
        
        incoming_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.IN.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(
                    datetime.now(timezone.utc),
                    datetime.combine(week_ahead, datetime.max.time())
                )
            )
        ).scalar() or 0
        
        outgoing_checks = db.session.query(Payment).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value
            )
        ).all()
        
        outgoing_total = Decimal('0.00')
        outgoing_overdue = 0
        outgoing_overdue_amount = Decimal('0.00')
        
        for p in outgoing_checks:
            amt = Decimal(str(p.total_amount or 0))
            if p.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, p.currency, "ILS", p.payment_date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            outgoing_total += amt_ils
            if p.check_due_date and p.check_due_date < datetime.utcnow():
                outgoing_overdue += 1
                outgoing_overdue_amount += amt_ils
        
        outgoing_total = float(outgoing_total)
        outgoing_overdue_amount = float(outgoing_overdue_amount)
        
        outgoing_this_week = db.session.query(db.func.count(Payment.id)).filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.direction == PaymentDirection.OUT.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.now(timezone.utc), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).scalar() or 0
        
        expense_checks = db.session.query(Expense).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.isnot(None),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).all()
        
        expense_total = Decimal('0.00')
        expense_overdue = 0
        expense_overdue_amount = Decimal('0.00')
        
        for exp in expense_checks:
            amt = Decimal(str(exp.amount or 0))
            if exp.currency == "ILS":
                amt_ils = amt
            else:
                try:
                    amt_ils = convert_amount(amt, exp.currency, "ILS", exp.date)
                except Exception:
                    amt_ils = Decimal('0.00')
            
            expense_total += amt_ils
            if exp.check_due_date and exp.check_due_date < datetime.now(timezone.utc):
                expense_overdue += 1
                expense_overdue_amount += amt_ils
        
        expense_total = float(expense_total)
        expense_overdue_amount = float(expense_overdue_amount)
        
        expense_this_week = db.session.query(db.func.count(Expense.id)).filter(
            and_(
                Expense.payment_method == 'cheque',
                Expense.check_due_date.between(datetime.now(timezone.utc), datetime.combine(week_ahead, datetime.max.time())),
                or_(Expense.is_paid == False, Expense.is_paid.is_(None))
            )
        ).scalar() or 0
        
        total_outgoing_value = float(outgoing_total or 0) + float(expense_total or 0)
        total_outgoing_overdue = outgoing_overdue + expense_overdue
        total_outgoing_overdue_amount = float(outgoing_overdue_amount or 0) + float(expense_overdue_amount or 0)
        total_outgoing_this_week = outgoing_this_week + expense_this_week
        
        return jsonify({
            'success': True,
            'statistics': {
                'incoming': {
                    'total_amount': float(incoming_total or 0),
                    'overdue_count': incoming_overdue,
                    'overdue_amount': float(incoming_overdue_amount or 0),  # ✅ إضافة المبلغ المتأخر
                    'this_week_count': incoming_this_week
                },
                'outgoing': {
                    'total_amount': total_outgoing_value,
                    'overdue_count': total_outgoing_overdue,
                    'overdue_amount': total_outgoing_overdue_amount,  # ✅ إضافة المبلغ المتأخر
                    'this_week_count': total_outgoing_this_week
                }
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check statistics: {str(e)}")
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/first-incomplete', methods=['GET'])
@login_required
def get_first_incomplete_check():
    try:
        split_candidates = (
            PaymentSplit.query
            .options(joinedload(PaymentSplit.payment))
            .filter(PaymentSplit.method == PaymentMethod.CHEQUE.value)
            .order_by(PaymentSplit.id.asc())
            .all()
        )
        for split in split_candidates:
            details = getattr(split, 'details', {}) or {}
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}
            check_number = (details.get('check_number') or '').strip()
            check_bank = (details.get('check_bank') or '').strip()
            due_raw = details.get('check_due_date')
            if not due_raw and split.payment:
                due_raw = getattr(split.payment, 'check_due_date', None) or getattr(split.payment, 'payment_date', None)
            if not check_number or not check_bank or not due_raw:
                token = f"split-{getattr(split, 'id', 0)}"
                return jsonify({
                    'success': True,
                    'type': 'payment_split',
                    'token': token,
                    'id': getattr(split, 'id', 0),
                    'payment_id': getattr(split, 'payment_id', None),
                })
        manual_check = (
            Check.query
            .filter(
                or_(
                    Check.check_number.is_(None),
                    Check.check_number == '',
                    Check.check_bank.is_(None),
                    Check.check_bank == '',
                    Check.check_due_date.is_(None),
                )
            )
            .order_by(Check.id.asc())
            .first()
        )
        if manual_check:
            token = f"check-{manual_check.id}"
            return jsonify({
                'success': True,
                'type': 'manual',
                'token': token,
                'id': manual_check.id,
            })
        expense_check = (
            Expense.query
            .filter(Expense.payment_method == 'cheque')
            .filter(
                or_(
                    Expense.check_number.is_(None),
                    Expense.check_number == '',
                    Expense.check_bank.is_(None),
                    Expense.check_bank == '',
                    Expense.check_due_date.is_(None),
                )
            )
            .order_by(Expense.id.asc())
            .first()
        )
        if expense_check:
            token = f"expense-{expense_check.id}"
            return jsonify({
                'success': True,
                'type': 'expense',
                'token': token,
                'id': expense_check.id,
            })
        return jsonify({
            'success': True,
            'type': None,
            'token': None,
            'id': None,
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching first incomplete check: {str(e)}")
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checks_bp.route('/api/check-lifecycle/<int:check_id>/<check_type>')
def get_check_lifecycle(check_id, check_type):
    """
    الحصول على دورة حياة الشيك الكاملة
    """
    try:
        if check_type == 'payment':
            check = Payment.query.get_or_404(check_id)
        else:
            check = Expense.query.get_or_404(check_id)
        
        notes = check.notes or ''
        lifecycle_events = []
        
        for line in notes.split('\n'):
            if '[' in line and ']' in line:
                lifecycle_events.append({
                    'timestamp': line[line.find('[')+1:line.find(']')],
                    'description': line[line.find(']')+1:].strip()
                })
        
        lifecycle_events.insert(0, {
            'timestamp': check.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(check, 'created_at') else 'غير محدد',
            'description': f'إنشاء الشيك رقم {check.check_number or "N/A"} - البنك: {check.check_bank or "N/A"} - المبلغ: {check.amount} {getattr(check, "currency", "ILS")}'
        })
        
        return jsonify({
            'success': True,
            'lifecycle': lifecycle_events,
            'current_status': get_current_check_status(check, check_type)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check lifecycle: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_current_check_status(check, check_type):
    """تحديد الحالة الحالية للشيك"""
    if check_type == 'payment':
        if check.status == PaymentStatus.COMPLETED.value:
            return 'CASHED'
        elif check.status == PaymentStatus.FAILED.value:
            notes_lower = (check.notes or '').lower()
            if 'مرتجع' in notes_lower or 'returned' in notes_lower:
                if 'أعيد' in notes_lower or 'resubmitted' in notes_lower:
                    return 'RESUBMITTED'
                return 'RETURNED'
            return 'BOUNCED'
        elif check.status == PaymentStatus.CANCELLED.value:
            return 'CANCELLED'
        return 'PENDING'
    else:
        is_paid = getattr(check, 'is_paid', False)
        notes_lower = (check.notes or '').lower()
        
        if is_paid:
            return 'CASHED'
        elif 'أعيد' in notes_lower or 'resubmitted' in notes_lower:
            return 'RESUBMITTED'
        elif 'مرتجع' in notes_lower or 'returned' in notes_lower:
            return 'RETURNED'
        elif 'مرفوض' in notes_lower or 'bounced' in notes_lower:
            return 'BOUNCED'
        elif 'ملغي' in notes_lower or 'cancelled' in notes_lower:
            return 'CANCELLED'
        return 'PENDING'


@checks_bp.route('/api/update-status/<check_id>', methods=['POST'])
@login_required
def update_check_status(check_id):
    try:
        data = request.get_json() or {}
        new_status = (data.get('status') or '').strip().upper()
        if not new_status:
            return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
        notes = (data.get('notes') or '').strip()
        return_reason = (data.get('return_reason') or data.get('refund_reason') or data.get('reason') or '').strip().upper()
        
        try:
            service = CheckActionService(current_user)
            if new_status == 'RETURNED' and return_reason == 'PAYMENT_REFUND':
                base_note = 'تم ارجاعه للزبون بسبب ارجاع الدفعة'
                ctx = service._resolve(check_id)
                prev = service._current_status(ctx)
                composed_note = base_note if not notes else f"{base_note} - {notes}"
                composed_note = composed_note + ' [RETURN_REASON=PAYMENT_REFUND]'
                target = 'RETURNED'
                if prev == 'RETURNED':
                    target = 'PENDING'
                    composed_note = notes
                result = service.run(check_id, target, composed_note or '')
            elif new_status == 'RETURNED' and return_reason and return_reason != 'PAYMENT_REFUND':
                marked_notes = (notes + ' [RETURN_REASON=BANK]').strip()
                result = service.run(check_id, new_status, marked_notes)
            elif new_status == 'RESUBMITTED' and return_reason and return_reason != 'PAYMENT_REFUND':
                marked_notes = (notes + ' [RETURN_REASON=BANK]').strip()
                result = service.run(check_id, new_status, marked_notes)
            else:
                result = service.run(check_id, new_status, notes)
            db.session.commit()
            next_list = 'pending'
            if result['new_status'] in ['RETURNED','BOUNCED']:
                next_list = 'returned'
            elif result['new_status'] == 'CASHED':
                next_list = 'cashed'
            elif result['new_status'] == 'CANCELLED':
                next_list = 'cancelled'
            ctx = service._resolve(check_id)
            amount = None
            currency = None
            direction = None
            method = None
            payment_id = None
            check_id_res = None
            entity_type = None
            entity_id = None
            try:
                if ctx.kind == 'payment' and ctx.payment:
                    amount = float(getattr(ctx.payment, 'total_amount', 0) or 0)
                    currency = getattr(ctx.payment, 'currency', None)
                    direction = getattr(getattr(ctx.payment, 'direction', None), 'value', getattr(ctx.payment, 'direction', None))
                    method = getattr(getattr(ctx.payment, 'method', None), 'value', getattr(ctx.payment, 'method', None))
                    payment_id = ctx.payment.id
                    entity_type = getattr(getattr(ctx.payment, 'entity_type', None), 'value', getattr(ctx.payment, 'entity_type', None))
                    entity_id = getattr(ctx.payment, 'customer_id', None) or getattr(ctx.payment, 'supplier_id', None) or getattr(ctx.payment, 'partner_id', None)
                    chk = Check.query.filter(Check.payment_id == payment_id).first()
                    check_id_res = chk.id if chk else None
                elif ctx.kind == 'payment_split' and ctx.split:
                    amount = float(getattr(ctx.split, 'amount', 0) or 0)
                    currency = getattr(ctx.split, 'currency', None)
                    direction = getattr(getattr(ctx.payment, 'direction', None), 'value', getattr(ctx.payment, 'direction', None)) if ctx.payment else None
                    method = getattr(getattr(ctx.split, 'method', None), 'value', getattr(ctx.split, 'method', None))
                    payment_id = ctx.split.payment_id
                    entity_type = getattr(getattr(ctx.payment, 'entity_type', None), 'value', getattr(ctx.payment, 'entity_type', None)) if ctx.payment else None
                    entity_id = getattr(ctx.payment, 'customer_id', None) or getattr(ctx.payment, 'supplier_id', None) or getattr(ctx.payment, 'partner_id', None) if ctx.payment else None
                    chk = Check.query.filter(Check.reference_number == f"PMT-SPLIT-{ctx.split.id}").first()
                    check_id_res = chk.id if chk else None
                elif ctx.kind == 'manual' and ctx.manual:
                    amount = float(getattr(ctx.manual, 'amount', 0) or 0)
                    currency = getattr(ctx.manual, 'currency', None)
                    direction = getattr(ctx.manual, 'direction', None)
                    payment_id = getattr(ctx.manual, 'payment_id', None)
                    check_id_res = ctx.manual.id
                    entity_type = getattr(ctx.manual, 'entity_type', None)
                    entity_id = getattr(ctx.manual, 'customer_id', None) or getattr(ctx.manual, 'supplier_id', None) or getattr(ctx.manual, 'partner_id', None)
            except Exception:
                pass
            return jsonify({
                'success': True,
                'message': f"تم تحديث حالة الشيك إلى: {result['new_status_ar']}",
                'new_status': result['new_status'],
                'new_status_ar': result['new_status_ar'],
                'previous_status': result.get('previous_status'),
                'balance': result.get('balance'),
                'gl_batch_id': result.get('gl_batch_id'),
                'token': result['token'],
                'kind': result['kind'],
                'amount': amount,
                'currency': currency,
                'direction': direction,
                'method': method,
                'payment_id': payment_id,
                'check_id': check_id_res,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'next_list': next_list,
            })
        except (CheckValidationError, CheckStateError) as err:
            db.session.rollback()
            current_app.logger.warning(f"Validation/State error updating check status {check_id}: {str(err)}")
            return jsonify({'success': False, 'message': str(err), 'code': getattr(err, 'code', None)}), 400
        except CheckAccountingError as err:
            db.session.rollback()
            current_app.logger.error(f"Accounting error updating check status {check_id}: {str(err)}")
            return jsonify({'success': False, 'message': f"خطأ محاسبي: {str(err)}", 'code': getattr(err, 'code', None)}), 500
        except CheckException as err:
            db.session.rollback()
            current_app.logger.error(f"Check error updating check status {check_id}: {str(err)}")
            return jsonify({'success': False, 'message': str(err), 'code': getattr(err, 'code', None)}), 500
    except Exception as err:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error updating check status {check_id}: {err}")
        return jsonify({'success': False, 'error': str(err)}), 500


@checks_bp.route('/api/get-details/<check_token>', methods=['GET'])
@login_required
def get_check_details(check_token):
    if not _current_user_is_owner():
        return jsonify({'success': False, 'message': 'مسموح للمالك فقط'}), 403
    try:
        service = CheckActionService(current_user)
        ctx = service._resolve(check_token)
        result = {
            'success': True,
            'resubmit_allowed_count': 1,
            'legal_return_allowed_count': 1
        }
        if ctx.kind == 'manual' and ctx.manual:
            result['resubmit_allowed_count'] = getattr(ctx.manual, 'resubmit_allowed_count', 1) or 1
            result['legal_return_allowed_count'] = getattr(ctx.manual, 'legal_return_allowed_count', 1) or 1
        return jsonify(result)
    except Exception as err:
        current_app.logger.error(f"Error getting check details {check_token}: {err}")
        return jsonify({'success': False, 'error': str(err)}), 500

@checks_bp.route('/api/update-details/<check_token>', methods=['POST'])
@login_required
def update_check_details(check_token):
    if not _current_user_is_owner():
        return jsonify({'success': False, 'message': 'مسموح للمالك فقط'}), 403
    try:
        payload = request.get_json() or {}
        service = CheckActionService(current_user)
        ctx = service._resolve(check_token)
        _update_check_details(ctx, payload, service)
        db.session.commit()
        return jsonify({'success': True, 'message': 'تم تحديث بيانات الشيك بنجاح'})
    except (CheckValidationError, CheckStateError) as err:
        db.session.rollback()
        current_app.logger.warning(f"Validation/State error updating check details {check_token}: {str(err)}")
        return jsonify({'success': False, 'message': str(err), 'code': getattr(err, 'code', None)}), 400
    except Exception as err:
        db.session.rollback()
        current_app.logger.error(f"Error updating check details {check_token}: {err}")
        return jsonify({'success': False, 'error': str(err)}), 500


@checks_bp.route('/api/mark-settled/<check_token>', methods=['POST'])
@login_required
def mark_check_settled(check_token):
    if not _current_user_is_owner():
        return jsonify({'success': False, 'message': 'مسموح للمالك فقط'}), 403
    try:
        service = CheckActionService(current_user)
        ctx = service._resolve(check_token)
        
        current_status = service._current_status(ctx)
        if current_status in ['CANCELLED', 'CASHED']:
            return jsonify({'success': True, 'message': 'الشيك مسوى أو ملغي مسبقاً'})
        
        note_text = "تم تسوية الشيك مرتجع عن طريق دفع بديل"
        
        if ctx.kind == 'payment' and ctx.payment:
            if current_status == 'PENDING':
                result = service.run(check_token, 'CANCELLED', note_text)
                return jsonify({
                    'success': True, 
                    'message': 'تم إلغاء الشيك المعلق (لم يتم الدفع فعلياً)',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar')
                })
            else:
                note_suffix = "\n[SETTLED=true] " + note_text
                if '[SETTLED=true]' in (ctx.payment.notes or ''):
                    return jsonify({'success': True, 'message': 'تمت التسوية مسبقاً'})
                ctx.payment.notes = (ctx.payment.notes or '') + note_suffix
                
                from models import PaymentSplit, PaymentMethod
                splits = PaymentSplit.query.filter(PaymentSplit.payment_id == ctx.payment.id).all()
                if splits:
                    cheque_splits = [s for s in splits if s.method == PaymentMethod.CHEQUE.value]
                    non_cheque_splits = [s for s in splits if s.method != PaymentMethod.CHEQUE.value]
                    
                    if len(non_cheque_splits) > 0:
                        ctx.payment.status = PaymentStatus.COMPLETED
                    else:
                        all_cheque_splits_settled = True
                        for split in cheque_splits:
                            split_check = Check.query.filter(
                                or_(
                                    Check.reference_number == f"PMT-SPLIT-{split.id}",
                                    Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                                )
                            ).first()
                            
                            if split_check and split_check.status in ['RETURNED', 'BOUNCED']:
                                split_payment_notes = ctx.payment.notes or ''
                                if '[SETTLED=true]' not in split_payment_notes.upper():
                                    all_cheque_splits_settled = False
                                    break
                        
                        if all_cheque_splits_settled:
                            ctx.payment.status = PaymentStatus.COMPLETED
                else:
                    ctx.payment.status = PaymentStatus.COMPLETED
        elif ctx.kind == 'payment_split' and ctx.payment:
            if current_status == 'PENDING':
                result = service.run(check_token, 'CANCELLED', note_text)
                return jsonify({
                    'success': True, 
                    'message': 'تم إلغاء الشيك المعلق (لم يتم الدفع فعلياً)',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar')
                })
            else:
                note_suffix = "\n[SETTLED=true] " + note_text
                if '[SETTLED=true]' in (ctx.payment.notes or ''):
                    return jsonify({'success': True, 'message': 'تمت التسوية مسبقاً'})
                ctx.payment.notes = (ctx.payment.notes or '') + note_suffix
                
                from models import PaymentSplit, PaymentMethod
                splits = PaymentSplit.query.filter(PaymentSplit.payment_id == ctx.payment.id).all()
                if splits:
                    cheque_splits = [s for s in splits if s.method == PaymentMethod.CHEQUE.value]
                    non_cheque_splits = [s for s in splits if s.method != PaymentMethod.CHEQUE.value]
                    
                    if len(non_cheque_splits) > 0:
                        ctx.payment.status = PaymentStatus.COMPLETED
                    else:
                        all_cheque_splits_settled = True
                        for split in cheque_splits:
                            split_check = Check.query.filter(
                                or_(
                                    Check.reference_number == f"PMT-SPLIT-{split.id}",
                                    Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                                )
                            ).first()
                            
                            if split_check and split_check.status in ['RETURNED', 'BOUNCED']:
                                split_payment_notes = ctx.payment.notes or ''
                                if '[SETTLED=true]' not in split_payment_notes.upper():
                                    all_cheque_splits_settled = False
                                    break
                        
                        if all_cheque_splits_settled:
                            ctx.payment.status = PaymentStatus.COMPLETED
                else:
                    ctx.payment.status = PaymentStatus.COMPLETED
        elif ctx.kind == 'expense' and ctx.expense:
            note_suffix = "\n[SETTLED=true] " + note_text
            if '[SETTLED=true]' in (ctx.expense.notes or ''):
                return jsonify({'success': True, 'message': 'تمت التسوية مسبقاً'})
            ctx.expense.notes = (ctx.expense.notes or '') + note_suffix
        elif ctx.kind == 'manual' and ctx.manual:
            if current_status == 'PENDING':
                result = service.run(check_token, 'CANCELLED', note_text)
                return jsonify({
                    'success': True, 
                    'message': 'تم إلغاء الشيك المعلق (لم يتم الدفع فعلياً)',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar')
                })
            else:
                note_suffix = "\n[SETTLED=true] " + note_text
                if '[SETTLED=true]' in (ctx.manual.notes or ''):
                    return jsonify({'success': True, 'message': 'تمت التسوية مسبقاً'})
                ctx.manual.notes = (ctx.manual.notes or '') + note_suffix
        else:
            raise CheckValidationError("نوع الشيك غير مدعوم للتسوية", code='UNSUPPORTED_SETTLEMENT_TYPE')
        db.session.commit()
        return jsonify({'success': True, 'message': 'تم تعليم الشيك كمُسوّى بنجاح'})
    except (CheckValidationError, CheckStateError) as err:
        db.session.rollback()
        current_app.logger.warning(f"Validation/State error marking check settled {check_token}: {str(err)}")
        return jsonify({'success': False, 'message': str(err), 'code': getattr(err, 'code', None)}), 400
    except Exception as err:
        db.session.rollback()
        current_app.logger.error(f"Error marking check settled {check_token}: {err}")
        return jsonify({'success': False, 'error': str(err)}), 500


@checks_bp.route('/api/unsettle/<check_token>', methods=['POST'])
@login_required
def unsettle_check(check_token):
    if not _current_user_is_owner():
        return jsonify({'success': False, 'message': 'مسموح للمالك فقط'}), 403
    try:
        service = CheckActionService(current_user)
        ctx = service._resolve(check_token)
        
        current_status = service._current_status(ctx)
        
        if ctx.kind == 'payment' and ctx.payment:
            notes = ctx.payment.notes or ''
            if '[SETTLED=true]' not in notes:
                return jsonify({'success': True, 'message': 'الشيك غير مسوى أصلاً'})
            
            lines = notes.split('\n')
            new_lines = []
            for line in lines:
                if '[SETTLED=true]' not in line and 'تم تسوية الشيك مرتجع' not in line:
                    new_lines.append(line)
            
            ctx.payment.notes = '\n'.join(new_lines).strip()
            
            if current_status == 'CANCELLED':
                previous_status = 'RETURNED'
                
                from models import PaymentSplit, PaymentMethod, Check, Payment
                splits = PaymentSplit.query.filter(PaymentSplit.payment_id == ctx.payment.id).all()
                has_non_cheque = False
                if splits:
                    non_cheque_splits = [s for s in splits if s.method != PaymentMethod.CHEQUE.value]
                    has_non_cheque = len(non_cheque_splits) > 0
                
                result = service.run(check_token, previous_status, 'تم إلغاء التسوية وإرجاع الشيك لحالته السابقة')
                
                if not has_non_cheque:
                    cheque_splits = [s for s in splits if s.method == PaymentMethod.CHEQUE.value] if splits else []
                    all_cheque_splits_returned = True
                    for split in cheque_splits:
                        split_check = Check.query.filter(
                            or_(
                                Check.reference_number == f"PMT-SPLIT-{split.id}",
                                Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                            )
                        ).first()
                        if split_check and split_check.status not in ['RETURNED', 'BOUNCED']:
                            all_cheque_splits_returned = False
                            break
                    
                    if all_cheque_splits_returned and ctx.payment.status == PaymentStatus.COMPLETED:
                        ctx.payment.status = PaymentStatus.FAILED
                
                entity_id = ctx.entity_id
                entity_type = ctx.entity_type
                if entity_id and entity_type:
                    if entity_type == 'CUSTOMER':
                        settlement_payments = Payment.query.filter(
                            Payment.customer_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    elif entity_type == 'SUPPLIER':
                        settlement_payments = Payment.query.filter(
                            Payment.supplier_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    elif entity_type == 'PARTNER':
                        settlement_payments = Payment.query.filter(
                            Payment.partner_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    else:
                        settlement_payments = []
                    
                    for settlement_payment in settlement_payments:
                        settlement_payment._skip_gl_reversal = True
                        db.session.delete(settlement_payment)
                
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': f'تم إلغاء التسوية وإرجاع الشيك من CANCELLED إلى {previous_status}',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar'),
                    'gl_batch_id': result.get('gl_batch_id'),
                    'payment_status': ctx.payment.status.value if ctx.payment.status else None
                })
            
        elif ctx.kind == 'payment_split' and ctx.payment:
            notes = ctx.payment.notes or ''
            if '[SETTLED=true]' not in notes:
                return jsonify({'success': True, 'message': 'الشيك غير مسوى أصلاً'})
            
            lines = notes.split('\n')
            new_lines = []
            for line in lines:
                if '[SETTLED=true]' not in line and 'تم تسوية الشيك مرتجع' not in line:
                    new_lines.append(line)
            
            ctx.payment.notes = '\n'.join(new_lines).strip()
            
            if current_status == 'CANCELLED':
                previous_status = 'RETURNED'
                
                from models import PaymentSplit, PaymentMethod, Check, Payment
                splits = PaymentSplit.query.filter(PaymentSplit.payment_id == ctx.payment.id).all()
                has_non_cheque = False
                if splits:
                    non_cheque_splits = [s for s in splits if s.method != PaymentMethod.CHEQUE.value]
                    has_non_cheque = len(non_cheque_splits) > 0
                
                result = service.run(check_token, previous_status, 'تم إلغاء التسوية وإرجاع الشيك لحالته السابقة')
                
                if not has_non_cheque:
                    cheque_splits = [s for s in splits if s.method == PaymentMethod.CHEQUE.value] if splits else []
                    all_cheque_splits_returned = True
                    for split in cheque_splits:
                        split_check = Check.query.filter(
                            or_(
                                Check.reference_number == f"PMT-SPLIT-{split.id}",
                                Check.reference_number.like(f"PMT-SPLIT-{split.id}-%")
                            )
                        ).first()
                        if split_check and split_check.status not in ['RETURNED', 'BOUNCED']:
                            all_cheque_splits_returned = False
                            break
                    
                    if all_cheque_splits_returned and ctx.payment.status == PaymentStatus.COMPLETED:
                        ctx.payment.status = PaymentStatus.FAILED
                
                entity_id = ctx.entity_id
                entity_type = ctx.entity_type
                if entity_id and entity_type:
                    if entity_type == 'CUSTOMER':
                        settlement_payments = Payment.query.filter(
                            Payment.customer_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    elif entity_type == 'SUPPLIER':
                        settlement_payments = Payment.query.filter(
                            Payment.supplier_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    elif entity_type == 'PARTNER':
                        settlement_payments = Payment.query.filter(
                            Payment.partner_id == entity_id,
                            Payment.notes.like(f'%{check_token}%'),
                            Payment.notes.like('%[SETTLED=true]%'),
                            Payment.notes.like('%تم تسوية الشيك مرتجع%')
                        ).all()
                    else:
                        settlement_payments = []
                    
                    for settlement_payment in settlement_payments:
                        settlement_payment._skip_gl_reversal = True
                        db.session.delete(settlement_payment)
                
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': f'تم إلغاء التسوية وإرجاع الشيك من CANCELLED إلى {previous_status}',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar'),
                    'gl_batch_id': result.get('gl_batch_id'),
                    'payment_status': ctx.payment.status.value if ctx.payment.status else None
                })
            
        elif ctx.kind == 'expense' and ctx.expense:
            notes = ctx.expense.notes or ''
            if '[SETTLED=true]' not in notes:
                return jsonify({'success': True, 'message': 'الشيك غير مسوى أصلاً'})
            
            lines = notes.split('\n')
            new_lines = []
            for line in lines:
                if '[SETTLED=true]' not in line and 'تم تسوية الشيك مرتجع' not in line:
                    new_lines.append(line)
            
            ctx.expense.notes = '\n'.join(new_lines).strip()
            
        elif ctx.kind == 'manual' and ctx.manual:
            notes = ctx.manual.notes or ''
            if '[SETTLED=true]' not in notes:
                return jsonify({'success': True, 'message': 'الشيك غير مسوى أصلاً'})
            
            lines = notes.split('\n')
            new_lines = []
            for line in lines:
                if '[SETTLED=true]' not in line and 'تم تسوية الشيك مرتجع' not in line:
                    new_lines.append(line)
            
            ctx.manual.notes = '\n'.join(new_lines).strip()
            
            if current_status == 'CANCELLED':
                previous_status = 'RETURNED'
                result = service.run(check_token, previous_status, 'تم إلغاء التسوية وإرجاع الشيك لحالته السابقة')
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': f'تم إلغاء التسوية وإرجاع الشيك من CANCELLED إلى {previous_status}',
                    'new_status': result.get('new_status'),
                    'new_status_ar': result.get('new_status_ar'),
                    'gl_batch_id': result.get('gl_batch_id')
                })
        else:
            raise CheckValidationError("نوع الشيك غير مدعوم", code='UNSUPPORTED_CHECK_TYPE')
        
        db.session.commit()
        
        if ctx.entity_type and ctx.entity_id:
            service._update_balance(ctx.entity_type, ctx.entity_id)
        
        return jsonify({
            'success': True,
            'message': 'تم إلغاء التسوية بنجاح. الشيك عاد لحالته السابقة.',
            'current_status': current_status
        })
    except (CheckValidationError, CheckStateError) as err:
        db.session.rollback()
        current_app.logger.warning(f"Validation/State error unsetting check {check_token}: {str(err)}")
        return jsonify({'success': False, 'message': str(err), 'code': getattr(err, 'code', None)}), 400
    except Exception as err:
        db.session.rollback()
        current_app.logger.error(f"Error unsetting check {check_token}: {err}")
        return jsonify({'success': False, 'error': str(err)}), 500


@checks_bp.route('/api/alerts')
@login_required
def get_alerts():
    """
    API للحصول على التنبيهات - محسّن لجلب من جميع المصادر
    """
    try:
        today = datetime.now(timezone.utc).date()
        week_ahead = today + timedelta(days=7)
        
        alerts = []
        
        overdue_manual_checks = Check.query.filter(
            and_(
                Check.status == CheckStatus.PENDING.value,
                Check.check_due_date < datetime.now(timezone.utc)
            )
        ).all()
        
        for check in overdue_manual_checks:
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            else:
                entity_name = check.drawer_name or check.payee_name or 'غير محدد'
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            days_overdue = (today - check.check_due_date.date()).days
            
            alerts.append({
                'type': 'overdue',
                'severity': 'danger',
                'icon': 'fas fa-exclamation-triangle',
                'title': f'🚨 شيك متأخر {days_overdue} يوم',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - المبلغ: {float(check.amount):,.2f} {check.currency}',
                'link': '/checks',
                'amount': float(check.amount),
                'currency': check.currency,
                'days_overdue': days_overdue,
                'check_number': check.check_number
            })
        
        overdue_payment_checks = Payment.query.filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date < datetime.now(timezone.utc),
                Payment.check_number.isnot(None)
            )
        ).all()
        
        for check in overdue_payment_checks:
            if Check.query.filter_by(reference_number=f'PMT-{check.id}').first():
                continue
            
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            else:
                entity_name = 'غير محدد'
            
            days_overdue = (today - check.check_due_date.date()).days
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            alerts.append({
                'type': 'overdue',
                'severity': 'danger',
                'icon': 'fas fa-exclamation-circle',
                'title': f'🚨 شيك متأخر {days_overdue} يوم',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - المبلغ: {float(check.total_amount or 0):,.2f} {check.currency}',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_overdue,
                'link': f'/checks?id={check.id}'
            })
        
        due_soon_checks = Payment.query.filter(
            and_(
                Payment.method == PaymentMethod.CHEQUE.value,
                Payment.status == PaymentStatus.PENDING.value,
                Payment.check_due_date.between(datetime.now(timezone.utc), datetime.combine(week_ahead, datetime.max.time()))
            )
        ).all()
        
        for check in due_soon_checks:
            entity_name = ''
            if check.customer:
                entity_name = check.customer.name
            elif check.supplier:
                entity_name = check.supplier.name
            elif check.partner:
                entity_name = check.partner.name
            else:
                entity_name = 'غير محدد'
            
            days_until = (check.check_due_date.date() - today).days
            
            is_incoming = check.direction == PaymentDirection.IN.value
            if is_incoming:
                direction_text = f'وارد من {entity_name}'
            else:
                direction_text = f'صادر لـ {entity_name}'
            
            alerts.append({
                'type': 'due_soon',
                'severity': 'warning',
                'icon': 'fas fa-clock',
                'title': f'⚠️ شيك قريب الاستحقاق',
                'message': f'شيك {direction_text} - رقم: {check.check_number} - يستحق خلال {days_until} يوم - المبلغ: {float(check.total_amount or 0):,.2f} {check.currency}',
                'amount': float(check.total_amount or 0),
                'currency': check.currency,
                'check_number': check.check_number,
                'due_date': check.check_due_date.strftime('%Y-%m-%d'),
                'days': days_until,
                'link': f'/checks?id={check.id}'
            })
        
        alerts.sort(key=lambda x: (x['type'] != 'overdue', x.get('days', x.get('days_overdue', 0))))
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'count': len(alerts)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching check alerts: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




@checks_bp.route("/new", methods=["GET", "POST"])
@login_required
def add_check():
    """إضافة شيك يدوي جديد"""
    if request.method == "POST":
        try:
            check_number = request.form.get("check_number")
            check_bank = request.form.get("check_bank")
            check_date_str = request.form.get("check_date")
            check_due_date_str = request.form.get("check_due_date")
            amount = Decimal(request.form.get("amount", 0))
            currency = request.form.get("currency", "ILS")
            direction = request.form.get("direction")
            
            drawer_name = request.form.get("drawer_name")
            drawer_phone = request.form.get("drawer_phone")
            drawer_id_number = request.form.get("drawer_id_number")
            drawer_address = request.form.get("drawer_address")
            payee_name = request.form.get("payee_name")
            payee_phone = request.form.get("payee_phone")
            payee_account = request.form.get("payee_account")
            
            notes = request.form.get("notes")
            internal_notes = request.form.get("internal_notes")
            reference_number = request.form.get("reference_number")
            
            customer_id_raw = request.form.get("customer_id") or None
            supplier_id_raw = request.form.get("supplier_id") or None
            partner_id_raw = request.form.get("partner_id") or None
            
            if not check_number or not check_bank or not amount or not direction:
                flash("يرجى ملء جميع الحقول المطلوبة", "danger")
                return redirect(url_for("checks.add_check"))
            
            check_date = datetime.strptime(check_date_str, "%Y-%m-%d") if check_date_str else datetime.now(timezone.utc)
            check_due_date = datetime.strptime(check_due_date_str, "%Y-%m-%d") if check_due_date_str else datetime.now(timezone.utc)
            
            customer_id = int(customer_id_raw) if customer_id_raw else None
            supplier_id = int(supplier_id_raw) if supplier_id_raw else None
            partner_id = int(partner_id_raw) if partner_id_raw else None
            
            new_check = Check(
                check_number=check_number,
                check_bank=check_bank,
                check_date=check_date,
                check_due_date=check_due_date,
                amount=amount,
                currency=currency,
                direction=direction,
                status=CheckStatus.PENDING.value,
                drawer_name=drawer_name,
                drawer_phone=drawer_phone,
                drawer_id_number=drawer_id_number,
                drawer_address=drawer_address,
                payee_name=payee_name,
                payee_phone=payee_phone,
                payee_account=payee_account,
                notes=notes,
                internal_notes=internal_notes,
                reference_number=reference_number,
                customer_id=customer_id,
                supplier_id=supplier_id,
                partner_id=partner_id,
                created_by_id=current_user.id
            )
            
            db.session.add(new_check)
            db.session.flush()
            
            db.session.commit()
            
            _create_check_gl_after_commit()
            
            flash(f"تم إضافة الشيك رقم {check_number} بنجاح", "success")
            return redirect(url_for("checks.index"))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding check: {str(e)}")
            flash(f"حدث خطأ أثناء إضافة الشيك: {str(e)}", "danger")
            return redirect(url_for("checks.add_check"))
    
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).limit(1000).all()
    suppliers = Supplier.query.order_by(Supplier.name).limit(1000).all()
    partners = Partner.query.order_by(Partner.name).limit(1000).all()
    
    return render_template("checks/form.html",
                         customers=customers,
                         suppliers=suppliers,
                         partners=partners,
                         check=None,
                         currencies=["ILS", "USD", "EUR", "JOD"])


@checks_bp.route("/edit/<int:check_id>", methods=["GET", "POST"])
@login_required
def edit_check(check_id):
    """تعديل شيك"""
    check = Check.query.get_or_404(check_id)
    
    if request.method == "POST":
        try:
            check.check_number = request.form.get("check_number")
            check.check_bank = request.form.get("check_bank")
            check.check_date = datetime.strptime(request.form.get("check_date"), "%Y-%m-%d")
            check.check_due_date = datetime.strptime(request.form.get("check_due_date"), "%Y-%m-%d")
            check.amount = Decimal(request.form.get("amount", 0))
            check.currency = request.form.get("currency", "ILS")
            check.direction = request.form.get("direction")
            
            check.drawer_name = request.form.get("drawer_name")
            check.drawer_phone = request.form.get("drawer_phone")
            check.drawer_id_number = request.form.get("drawer_id_number")
            check.drawer_address = request.form.get("drawer_address")
            check.payee_name = request.form.get("payee_name")
            check.payee_phone = request.form.get("payee_phone")
            check.payee_account = request.form.get("payee_account")
            
            check.notes = request.form.get("notes")
            check.internal_notes = request.form.get("internal_notes")
            check.reference_number = request.form.get("reference_number")
            
            customer_id_raw = request.form.get("customer_id")
            supplier_id_raw = request.form.get("supplier_id")
            partner_id_raw = request.form.get("partner_id")
            
            check.customer_id = int(customer_id_raw) if customer_id_raw else None
            check.supplier_id = int(supplier_id_raw) if supplier_id_raw else None
            check.partner_id = int(partner_id_raw) if partner_id_raw else None
            
            db.session.commit()
            
            flash(f"تم تعديل الشيك رقم {check.check_number} بنجاح", "success")
            return redirect(url_for("checks.check_detail", check_id=check.id))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating check: {str(e)}")
            flash(f"حدث خطأ أثناء تعديل الشيك: {str(e)}", "danger")
    
    customers = Customer.query.filter_by(is_active=True, is_archived=False).order_by(Customer.name).limit(1000).all()
    suppliers = Supplier.query.order_by(Supplier.name).limit(1000).all()
    partners = Partner.query.order_by(Partner.name).limit(1000).all()
    
    return render_template("checks/form.html",
                         check=check,
                         customers=customers,
                         suppliers=suppliers,
                         partners=partners,
                         currencies=["ILS", "USD", "EUR", "JOD"])


@checks_bp.route("/detail/<int:check_id>")
@login_required
def check_detail(check_id):
    """عرض تفاصيل شيك"""
    check = Check.query.get_or_404(check_id)
    status_history = check.get_status_history()
    
    return render_template("checks/detail.html",
                         check=check,
                         status_history=status_history,
                         CHECK_STATUS=CHECK_STATUS)


@checks_bp.route("/delete/<int:check_id>", methods=["POST"])
@login_required
def delete_check(check_id):
    """حذف شيك"""
    try:
        check = Check.query.get_or_404(check_id)
        check_number = check.check_number
        
        db.session.delete(check)
        db.session.commit()
        
        flash(f"تم حذف الشيك رقم {check_number} بنجاح", "success")
        return redirect(url_for("checks.index"))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting check: {str(e)}")
        flash(f"حدث خطأ أثناء حذف الشيك: {str(e)}", "danger")
        return redirect(url_for("checks.index"))


@checks_bp.route("/reports")
@login_required
def reports():
    """صفحة التقارير - من جميع المصادر"""
    today = datetime.now(timezone.utc).date()
    
    all_checks_response = get_checks()
    all_checks_data = all_checks_response.get_json()
    all_checks = all_checks_data.get('checks', []) if all_checks_data.get('success') else []
    
    current_app.logger.info(f"📊 التقارير - عدد الشيكات: {len(all_checks)}")
    
    independent_checks = Check.query.limit(10000).all()
    
    stats_by_status = {}
    for check in all_checks:
        status = check.get('status', 'UNKNOWN')
        original_status = status  # للـ logging
        
        notes = (check.get('notes', '') or '').lower()
        if 'حالة الشيك: مسحوب' in notes or 'حالة الشيك: تم الصرف' in notes:
            status = 'CASHED'
        elif 'حالة الشيك: مرتجع' in notes:
            status = 'RETURNED'
        elif 'حالة الشيك: ملغي' in notes:
            status = 'CANCELLED'
        elif 'حالة الشيك: أعيد للبنك' in notes:
            status = 'RESUBMITTED'
        elif 'حالة الشيك: مؤرشف' in notes:
            status = 'CANCELLED'
        elif 'حالة الشيك: مرفوض' in notes:
            status = 'BOUNCED'
        
        if status not in stats_by_status:
            stats_by_status[status] = {'status': status, 'count': 0, 'total_amount': 0}
        stats_by_status[status]['count'] += 1
        stats_by_status[status]['total_amount'] += float(check.get('amount', 0))
    
    current_app.logger.info(f"📊 إحصائيات الحالات: {stats_by_status}")
    current_app.logger.info(f"📊 عدد الحالات المختلفة: {len(stats_by_status)}")
    
    stats_by_status = list(stats_by_status.values())
    
    stats_by_direction = {'IN': {'direction': 'IN', 'count': 0, 'total_amount': 0},
                          'OUT': {'direction': 'OUT', 'count': 0, 'total_amount': 0}}
    
    for check in all_checks:
        direction = 'IN' if check.get('is_incoming') else 'OUT'
        stats_by_direction[direction]['count'] += 1
        stats_by_direction[direction]['total_amount'] += float(check.get('amount', 0))
    
    stats_by_direction = list(stats_by_direction.values())
    
    overdue_checks = []
    due_soon_checks = []
    
    for c in all_checks:
        notes = (c.get('notes', '') or '').lower()
        actual_status = c.get('status', '').upper()
        
        if 'حالة الشيك: مسحوب' in notes:
            continue  # مسحوب - تخطي
        elif 'حالة الشيك: ملغي' in notes or 'حالة الشيك: مؤرشف' in notes:
            continue  # ملغي/مؤرشف - تخطي
        elif 'حالة الشيك: مرتجع' in notes:
            continue  # مرتجع - تخطي
        
        if actual_status == 'OVERDUE':
            overdue_checks.append(c)
        elif actual_status == 'DUE_SOON':
            due_soon_checks.append(c)
    
    return render_template("checks/reports.html",
                         independent_checks=independent_checks,
                         all_checks=all_checks,
                         stats_by_status=stats_by_status,
                         stats_by_direction=stats_by_direction,
                         overdue_checks=overdue_checks,
                         due_soon_checks=due_soon_checks,
                         CheckStatus=CheckStatus,
                         PaymentDirection=PaymentDirection,
                         CHECK_STATUS=CHECK_STATUS)


def _parse_due_date_value(raw_value):
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, date):
        return datetime.combine(raw_value, datetime.min.time())
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if not candidate:
            return None
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
    raise ValueError("تاريخ الاستحقاق غير صالح")


def _normalize_entity_inputs(entity_type, entity_id):
    if not entity_type:
        return None, None
    normalized_type = str(entity_type).strip().upper()
    if normalized_type not in {"CUSTOMER", "SUPPLIER", "PARTNER"}:
        raise ValueError("نوع الجهة غير صالح")
    if entity_id is None or str(entity_id).strip() == "":
        raise ValueError("يجب تحديد معرف الجهة")
    try:
        normalized_id = int(entity_id)
    except (TypeError, ValueError):
        raise ValueError("معرف الجهة غير صالح")
    if normalized_id <= 0:
        raise ValueError("معرف الجهة غير صالح")
    return normalized_type, normalized_id


def _assign_payment_entity(payment, entity_type, entity_id):
    payment.customer_id = None
    payment.supplier_id = None
    payment.partner_id = None
    if not entity_type:
        payment.entity_type = None
        return
    if entity_type == "CUSTOMER":
        payment.customer_id = entity_id
    elif entity_type == "SUPPLIER":
        payment.supplier_id = entity_id
    elif entity_type == "PARTNER":
        payment.partner_id = entity_id
    payment.entity_type = entity_type


def _assign_expense_entity(expense, entity_type, entity_id):
    expense.customer_id = None
    expense.supplier_id = None
    expense.partner_id = None
    if not entity_type:
        expense.payee_type = "OTHER"
        expense.payee_entity_id = None
        return
    if entity_type == "CUSTOMER":
        expense.customer_id = entity_id
    elif entity_type == "SUPPLIER":
        expense.supplier_id = entity_id
    elif entity_type == "PARTNER":
        expense.partner_id = entity_id
    expense.payee_type = entity_type
    expense.payee_entity_id = entity_id


def _assign_manual_entity(check, entity_type, entity_id):
    check.customer_id = None
    check.supplier_id = None
    check.partner_id = None
    if not entity_type:
        return
    if entity_type == "CUSTOMER":
        check.customer_id = entity_id
    elif entity_type == "SUPPLIER":
        check.supplier_id = entity_id
    elif entity_type == "PARTNER":
        check.partner_id = entity_id


def _update_check_details(ctx: CheckActionContext, payload: dict, service: CheckActionService):
    if not payload:
        raise ValueError("بيانات ناقصة")
    entity_type_raw = payload.get("entity_type")
    entity_id_raw = payload.get("entity_id")
    entity_type, entity_id = _normalize_entity_inputs(entity_type_raw, entity_id_raw)
    amount_val = payload.get("amount")
    if amount_val is None:
        raise ValueError("المبلغ مطلوب")
    try:
        amount_decimal = Decimal(str(amount_val))
    except Exception:
        raise ValueError("قيمة المبلغ غير صحيحة")
    if amount_decimal <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    currency_val = (payload.get("currency") or ctx.currency or "ILS").strip().upper()
    bank_val = (payload.get("bank") or "").strip()
    due_date_val = payload.get("due_date")
    due_dt = _parse_due_date_value(due_date_val) if due_date_val else None

    if ctx.kind == 'payment':
        if not ctx.payment:
            raise ValueError("تعذر العثور على الدفعة المرتبطة")
        payment = ctx.payment
        _assign_payment_entity(payment, entity_type, entity_id)
        payment.total_amount = amount_decimal
        payment.currency = currency_val
        if due_dt:
            payment.check_due_date = due_dt
        if bank_val or bank_val == "":
            payment.check_bank = bank_val or None
        ctx.amount = amount_decimal
        ctx.currency = currency_val
    elif ctx.kind == 'payment_split':
        if not ctx.split or not ctx.payment:
            raise ValueError("تعذر العثور على بيانات الدفعة الجزئية")
        split = ctx.split
        split.amount = amount_decimal
        split.currency = currency_val
        details = service._load_split_details(split)
        if due_dt:
            details['check_due_date'] = due_dt.date().isoformat()
        if bank_val or bank_val == "":
            details['check_bank'] = bank_val
        split.details = details
        if entity_type:
            _assign_payment_entity(ctx.payment, entity_type, entity_id)
        ctx.amount = amount_decimal
        ctx.currency = currency_val
    elif ctx.kind == 'expense':
        if not ctx.expense:
            raise ValueError("تعذر العثور على المصروف المرتبط")
        expense = ctx.expense
        _assign_expense_entity(expense, entity_type, entity_id)
        expense.amount = amount_decimal
        expense.currency = currency_val
        if due_dt:
            expense.check_due_date = due_dt.date()
        if bank_val or bank_val == "":
            expense.check_bank = bank_val or None
        ctx.amount = amount_decimal
        ctx.currency = currency_val
    elif ctx.kind == 'manual':
        if not ctx.manual:
            raise ValueError("تعذر العثور على الشيك اليدوي")
        check = ctx.manual
        _assign_manual_entity(check, entity_type, entity_id)
        check.amount = amount_decimal
        check.currency = currency_val
        if due_dt:
            check.check_due_date = due_dt
        if bank_val or bank_val == "":
            check.check_bank = bank_val or None
        # تحديث عدد مرات السماح إذا تم توفيره
        resubmit_count = payload.get("resubmit_allowed_count")
        if resubmit_count is not None:
            try:
                count_val = int(resubmit_count)
                if count_val >= 1:
                    check.resubmit_allowed_count = count_val
                    current_app.logger.info(f"Updated resubmit_allowed_count to {count_val} for check {check.id}")
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Failed to update resubmit_allowed_count: {e}")
        legal_return_count = payload.get("legal_return_allowed_count")
        if legal_return_count is not None:
            try:
                count_val = int(legal_return_count)
                if count_val >= 1:
                    check.legal_return_allowed_count = count_val
                    current_app.logger.info(f"Updated legal_return_allowed_count to {count_val} for check {check.id}")
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Failed to update legal_return_allowed_count: {e}")
        ctx.amount = amount_decimal
        ctx.currency = currency_val
    else:
        raise CheckValidationError("نوع الشيك غير مدعوم للتعديل", code='UNSUPPORTED_EDIT_TYPE')
