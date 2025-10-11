# other_systems.py - Other Systems Routes
# Location: /garage_manager/routes/other_systems.py
# Description: Integration with external systems routes

from flask import Blueprint, render_template

other_systems_bp = Blueprint("other_systems", __name__, url_prefix="/other-systems")

@other_systems_bp.route("/", methods=["GET"], endpoint="index")
def other_systems_index():
    """صفحة أنظمتنا الأخرى"""
    return render_template("other_systems/index.html")
