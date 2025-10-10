from flask import Blueprint, render_template

pricing_bp = Blueprint("pricing", __name__, url_prefix="/pricing")

@pricing_bp.route("/", methods=["GET"], endpoint="index")
def pricing_index():
    """صفحة الأسعار"""
    return render_template("pricing/index.html")
