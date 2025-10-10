from flask import Blueprint, render_template

user_guide_bp = Blueprint("user_guide", __name__, url_prefix="/user-guide")

@user_guide_bp.route("/", methods=["GET"], endpoint="index")
def user_guide():
    """دليل المستخدم - متاح بدون تسجيل دخول"""
    return render_template("user_guide.html")
