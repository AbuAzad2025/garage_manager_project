from flask import current_app

from extensions import db
from models import Customer, Partner, Payment, PaymentDirection, Supplier, User


def _clean(value):
    if not value:
        return ""
    return str(value).strip()


def _counterparty_name(payment: Payment) -> str:
    for rel, model, attr in (
        (payment.customer_id, Customer, "name"),
        (payment.supplier_id, Supplier, "name"),
        (payment.partner_id, Partner, "name"),
    ):
        if not rel:
            continue
        obj = db.session.get(model, rel)
        val = getattr(obj, attr, None) if obj else None
        name = _clean(val)
        if name:
            return name
    fallback = _clean(getattr(payment, "reference", None)) or _clean(getattr(payment, "notes", None))
    if fallback:
        return fallback
    return "غير محدد"


def _owner_name() -> str:
    owner = (
        db.session.query(User)
        .filter(
            db.func.lower(User.username) == "__owner__"
        )
        .first()
    )
    if owner:
        name = _clean(getattr(owner, "display_name", None) or getattr(owner, "username", None))
        if name:
            return name
    return "Owner"


def _creator_name(payment: Payment) -> str:
    creator_id = getattr(payment, "created_by", None)
    if not creator_id:
        return ""
    user = db.session.get(User, creator_id)
    if not user:
        return ""
    for attr in ("display_name", "full_name", "name", "username", "email"):
        val = _clean(getattr(user, attr, None))
        if val:
            return val
    return ""


def backfill_payment_roles():
    owner = _owner_name()
    updates = 0
    payments = (
        db.session.query(Payment)
        .filter(
            db.or_(
                Payment.deliverer_name.is_(None),
                Payment.deliverer_name == "",
                Payment.receiver_name.is_(None),
                Payment.receiver_name == "",
            )
        )
        .all()
    )

    for payment in payments:
        deliverer = _clean(getattr(payment, "deliverer_name", None))
        receiver = _clean(getattr(payment, "receiver_name", None))

        counterparty = _counterparty_name(payment)
        creator = _creator_name(payment) or owner

        direction_val = getattr(payment.direction, "value", payment.direction)
        direction_val = (direction_val or "").upper()

        if direction_val == PaymentDirection.IN.value:
            if not deliverer:
                deliverer = counterparty
            if not receiver:
                receiver = creator
        elif direction_val == PaymentDirection.OUT.value:
            if not deliverer:
                deliverer = owner
            if not receiver:
                receiver = counterparty
        else:
            if not deliverer:
                deliverer = counterparty
            if not receiver:
                receiver = creator

        deliverer = deliverer or owner
        receiver = receiver or counterparty

        if deliverer != getattr(payment, "deliverer_name", None) or receiver != getattr(payment, "receiver_name", None):
            payment.deliverer_name = deliverer
            payment.receiver_name = receiver
            updates += 1

    if updates:
        db.session.commit()

    current_app.logger.info("Backfill complete. Updated %s payments.", updates)
from __future__ import annotations

from flask import current_app

from extensions import db
from models import Customer, Partner, Payment, PaymentDirection, Supplier, User


def _clean(value):
    if not value:
        return ""
    return str(value).strip()


def _counterparty_name(payment: Payment) -> str:
    for rel, model, attr in (
        (payment.customer_id, Customer, "name"),
        (payment.supplier_id, Supplier, "name"),
        (payment.partner_id, Partner, "name"),
    ):
        if not rel:
            continue
        obj = db.session.get(model, rel)
        val = getattr(obj, attr, None) if obj else None
        name = _clean(val)
        if name:
            return name
    fallback = _clean(getattr(payment, "reference", None)) or _clean(getattr(payment, "notes", None))
    if fallback:
        return fallback
    return "غير محدد"


def _owner_name() -> str:
    owner = (
        db.session.query(User)
        .filter(
            db.func.lower(User.username) == "__owner__"
        )
        .first()
    )
    if owner:
        name = _clean(getattr(owner, "display_name", None) or getattr(owner, "username", None))
        if name:
            return name
    return "Owner"


def _creator_name(payment: Payment) -> str:
    creator_id = getattr(payment, "created_by", None)
    if not creator_id:
        return ""
    user = db.session.get(User, creator_id)
    if not user:
        return ""
    for attr in ("display_name", "full_name", "name", "username", "email"):
        val = _clean(getattr(user, attr, None))
        if val:
            return val
    return ""


def backfill_payment_roles():
    owner = _owner_name()
    updates = 0
    payments = (
        db.session.query(Payment)
        .filter(
            db.or_(
                Payment.deliverer_name.is_(None),
                Payment.deliverer_name == "",
                Payment.receiver_name.is_(None),
                Payment.receiver_name == "",
            )
        )
        .all()
    )

    for payment in payments:
        deliverer = _clean(getattr(payment, "deliverer_name", None))
        receiver = _clean(getattr(payment, "receiver_name", None))

        counterparty = _counterparty_name(payment)
        creator = _creator_name(payment) or owner

        direction_val = getattr(payment.direction, "value", payment.direction)
        direction_val = (direction_val or "").upper()

        if direction_val == PaymentDirection.IN.value:
            if not deliverer:
                deliverer = counterparty
            if not receiver:
                receiver = creator
        elif direction_val == PaymentDirection.OUT.value:
            if not deliverer:
                deliverer = owner
            if not receiver:
                receiver = counterparty
        else:
            if not deliverer:
                deliverer = counterparty
            if not receiver:
                receiver = creator

        deliverer = deliverer or owner
        receiver = receiver or counterparty

        if deliverer != getattr(payment, "deliverer_name", None) or receiver != getattr(payment, "receiver_name", None):
            payment.deliverer_name = deliverer
            payment.receiver_name = receiver
            updates += 1

    if updates:
        db.session.commit()

    current_app.logger.info("Backfill complete. Updated %s payments.", updates)

