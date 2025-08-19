from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from extensions import db
from models import OnlinePayment, OnlinePreOrder, Customer
from utils import log_audit

admin_reports_bp = Blueprint("admin_reports", __name__, url_prefix="/admin/reports", template_folder="templates/admin/reports")

def _is_super_admin(u):
    try:
        return (getattr(getattr(u, "role", None), "name", "") or "").lower() == "super_admin"
    except Exception:
        return False

def super_admin_required(f):
    @wraps(f)
    @login_required
    def inner(*a, **kw):
        if not _is_super_admin(current_user):
            abort(403)
        return f(*a, **kw)
    return inner

@admin_reports_bp.route("/cards", methods=["GET"], endpoint="cards")
@super_admin_required
def cards():
    q = OnlinePayment.query.join(OnlinePreOrder, OnlinePayment.order_id == OnlinePreOrder.id).join(Customer, OnlinePreOrder.customer_id == Customer.id)
    start = request.args.get("start")
    end = request.args.get("end")
    status = request.args.get("status")
    search = (request.args.get("q") or "").strip()

    if start:
        try:
            dt = datetime.strptime(start, "%Y-%m-%d")
            q = q.filter(OnlinePayment.created_at >= dt)
        except Exception:
            pass
    if end:
        try:
            dt = datetime.strptime(end, "%Y-%m-%d")
            q = q.filter(OnlinePayment.created_at < (dt.replace(hour=23, minute=59, second=59)))
        except Exception:
            pass
    if status and status in ("PENDING", "SUCCESS", "FAILED", "REFUNDED"):
        q = q.filter(OnlinePayment.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            OnlinePayment.payment_ref.ilike(like),
            Customer.name.ilike(like),
            Customer.phone.ilike(like),
        ))

    rows = q.order_by(OnlinePayment.created_at.desc()).limit(500).all()
    return render_template("admin/reports/cards.html", rows=rows)

@admin_reports_bp.route("/cards/<int:pid>/reveal", methods=["POST"], endpoint="cards_reveal")
@super_admin_required
def cards_reveal(pid: int):
    op = db.session.get(OnlinePayment, pid)
    if not op:
        abort(404)
    pan = op.decrypt_card_number()
    if not pan:
        return jsonify({"ok": False, "error": "لا يمكن فك التشفير"}), 400
    log_audit("OnlinePayment", op.id, "reveal_card", old_data=None, new_data={"payment_ref": op.payment_ref})
    return jsonify({
        "ok": True,
        "payment_ref": op.payment_ref,
        "pan": pan,
        "brand": op.card_brand,
        "last4": op.card_last4,
        "holder": op.cardholder_name,
        "expiry": op.card_expiry,
        "amount": float(op.amount or 0),
        "currency": op.currency,
        "created_at": op.created_at.isoformat() if getattr(op, "created_at", None) else None,
    })
