from flask import Blueprint, request, jsonify
from flask_login import login_required
from extensions import db, limiter
from models import Product
from barcodes import validate_barcode


bp_barcode = Blueprint("bp_barcode", __name__, url_prefix="/api")

@bp_barcode.get("/barcode/validate")
def barcode_validate():
    code = request.args.get("code", "", type=str).strip()
    r = validate_barcode(code)
    exists = False
    if r["normalized"] and r["valid"]:
        exists = db.session.query(Product.id).filter_by(barcode=r["normalized"]).first() is not None
    return jsonify({"input": code, "normalized": r["normalized"], "valid": r["valid"], "exists": exists})
