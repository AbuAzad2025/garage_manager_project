
from flask import Blueprint, request, jsonify
from flask_login import login_required
from extensions import db, limiter
from models import Product
from barcodes import validate_barcode

bp_barcode = Blueprint("bp_barcode", __name__, url_prefix="/api")

@bp_barcode.get("/barcode/validate", endpoint="barcode_validate")
@login_required
@limiter.limit("120/minute")
def barcode_validate():
    code = (request.args.get("code") or "").strip()
    r = validate_barcode(code)
    exists = False
    if r.get("normalized") and r.get("valid"):
        exists = db.session.query(Product.id).filter_by(barcode=r["normalized"]).first() is not None
    return jsonify({
        "input": code,
        "normalized": r.get("normalized"),
        "valid": bool(r.get("valid")),
        "exists": bool(exists),
    })
