"""
نظام تقييمات المنتجات
Product Ratings System
"""

from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, and_, or_
from extensions import db
from models import Product, ProductRating, ProductRatingHelpful, Customer
from utils import permission_required, _get_or_404
from datetime import datetime

# Blueprint definition
ratings_bp = Blueprint('ratings', __name__, url_prefix='/ratings')


@ratings_bp.route("/product/<int:product_id>", methods=["GET"], endpoint="product_ratings")
def product_ratings(product_id):
    """عرض تقييمات منتج معين"""
    product = _get_or_404(Product, product_id)
    
    # الحصول على التقييمات
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    
    ratings_query = ProductRating.get_product_ratings(product_id, approved_only=True)
    ratings = ratings_query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # الحصول على متوسط التقييم
    avg_rating = ProductRating.get_product_average_rating(product_id)
    
    # الحصول على توزيع التقييمات
    distribution = ProductRating.get_rating_distribution(product_id)
    
    if request.is_json or request.args.get("format") == "json":
        return jsonify({
            "product_id": product_id,
            "product_name": product.name,
            "average_rating": avg_rating,
            "rating_distribution": distribution,
            "ratings": [rating.to_dict() for rating in ratings.items],
            "pagination": {
                "page": ratings.page,
                "pages": ratings.pages,
                "per_page": ratings.per_page,
                "total": ratings.total
            }
        })
    
    return render_template(
        "ratings/product_ratings.html",
        product=product,
        ratings=ratings,
        average_rating=avg_rating,
        distribution=distribution
    )


@ratings_bp.route("/product/<int:product_id>/add", methods=["POST"], endpoint="add_rating")
@login_required
def add_rating(product_id):
    """إضافة تقييم جديد لمنتج"""
    product = _get_or_404(Product, product_id)
    
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        rating_value = int(data.get("rating", 0))
        title = data.get("title", "").strip()
        comment = data.get("comment", "").strip()
        
        # التحقق من صحة البيانات
        if rating_value < 1 or rating_value > 5:
            return jsonify({"error": "التقييم يجب أن يكون بين 1 و 5"}), 400
        
        # التحقق من عدم وجود تقييم سابق من نفس العميل
        existing_rating = ProductRating.query.filter_by(
            product_id=product_id,
            customer_id=current_user.id
        ).first()
        
        if existing_rating:
            return jsonify({"error": "لقد قمت بتقييم هذا المنتج مسبقاً"}), 400
        
        # إنشاء التقييم الجديد
        rating = ProductRating(
            product_id=product_id,
            customer_id=current_user.id,
            rating=rating_value,
            title=title if title else None,
            comment=comment if comment else None,
            is_verified_purchase=False,  # يمكن ربطه بنظام الطلبات
            is_approved=True
        )
        
        db.session.add(rating)
        db.session.commit()
        
        # إرسال إشعار
        try:
            from notifications import notify_system_alert
            notify_system_alert(
                "تقييم جديد",
                f"تم إضافة تقييم جديد للمنتج {product.name}",
                priority="MEDIUM"
            )
        except ImportError:
            pass
        
        return jsonify({
            "success": True,
            "message": "تم إضافة التقييم بنجاح",
            "rating": rating.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/rating/<int:rating_id>/helpful", methods=["POST"], endpoint="mark_helpful")
def mark_helpful(rating_id):
    """تحديد التقييم كمفيد أو غير مفيد"""
    rating = _get_or_404(ProductRating, rating_id)
    
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        is_helpful = data.get("helpful", True)
        
        # الحصول على IP للعملاء غير المسجلين
        ip_address = request.remote_addr if not current_user.is_authenticated else None
        customer_id = current_user.id if current_user.is_authenticated else None
        
        # تحديث التقييم
        ProductRatingHelpful.mark_helpful(
            rating_id=rating_id,
            customer_id=customer_id,
            ip_address=ip_address,
            is_helpful=is_helpful
        )
        
        return jsonify({
            "success": True,
            "message": "تم تحديث التقييم",
            "helpful_count": rating.helpful_count
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/rating/<int:rating_id>/edit", methods=["PUT"], endpoint="edit_rating")
@login_required
def edit_rating(rating_id):
    """تعديل تقييم موجود"""
    rating = _get_or_404(ProductRating, rating_id)
    
    # التحقق من أن المستخدم هو صاحب التقييم
    if rating.customer_id != current_user.id:
        return jsonify({"error": "غير مصرح لك بتعديل هذا التقييم"}), 403
    
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        rating_value = int(data.get("rating", rating.rating))
        title = data.get("title", "").strip()
        comment = data.get("comment", "").strip()
        
        # التحقق من صحة البيانات
        if rating_value < 1 or rating_value > 5:
            return jsonify({"error": "التقييم يجب أن يكون بين 1 و 5"}), 400
        
        # تحديث التقييم
        rating.rating = rating_value
        rating.title = title if title else None
        rating.comment = comment if comment else None
        rating.updated_at = datetime.utcnow()
        
        db.session.add(rating)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم تحديث التقييم بنجاح",
            "rating": rating.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/rating/<int:rating_id>/delete", methods=["DELETE"], endpoint="delete_rating")
@login_required
def delete_rating(rating_id):
    """حذف تقييم"""
    rating = _get_or_404(ProductRating, rating_id)
    
    # التحقق من أن المستخدم هو صاحب التقييم أو مدير
    if rating.customer_id != current_user.id and not getattr(current_user, 'is_admin', False):
        return jsonify({"error": "غير مصرح لك بحذف هذا التقييم"}), 403
    
    try:
        # حذف التقييمات المفيدة المرتبطة
        ProductRatingHelpful.query.filter_by(rating_id=rating_id).delete()
        
        # حذف التقييم
        db.session.delete(rating)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم حذف التقييم بنجاح"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/admin/pending", methods=["GET"], endpoint="pending_ratings")
@login_required
@permission_required("manage_products")
def pending_ratings():
    """عرض التقييمات المعلقة للمراجعة"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    
    ratings_query = ProductRating.query.filter_by(is_approved=False).order_by(
        ProductRating.created_at.desc()
    )
    
    ratings = ratings_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    if request.is_json or request.args.get("format") == "json":
        return jsonify({
            "ratings": [rating.to_dict() for rating in ratings.items],
            "pagination": {
                "page": ratings.page,
                "pages": ratings.pages,
                "per_page": ratings.per_page,
                "total": ratings.total
            }
        })
    
    return render_template("ratings/pending_ratings.html", ratings=ratings)


@ratings_bp.route("/admin/rating/<int:rating_id>/approve", methods=["POST"], endpoint="approve_rating")
@login_required
@permission_required("manage_products")
def approve_rating(rating_id):
    """الموافقة على تقييم"""
    rating = _get_or_404(ProductRating, rating_id)
    
    try:
        rating.is_approved = True
        rating.updated_at = datetime.utcnow()
        
        db.session.add(rating)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم الموافقة على التقييم"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/admin/rating/<int:rating_id>/reject", methods=["POST"], endpoint="reject_rating")
@login_required
@permission_required("manage_products")
def reject_rating(rating_id):
    """رفض تقييم"""
    rating = _get_or_404(ProductRating, rating_id)
    
    try:
        # حذف التقييمات المفيدة المرتبطة
        ProductRatingHelpful.query.filter_by(rating_id=rating_id).delete()
        
        # حذف التقييم
        db.session.delete(rating)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم رفض التقييم"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@ratings_bp.route("/stats", methods=["GET"], endpoint="rating_stats")
@login_required
@permission_required("manage_products")
def rating_stats():
    """إحصائيات التقييمات"""
    try:
        # إجمالي التقييمات
        total_ratings = ProductRating.query.count()
        
        # التقييمات المعلقة
        pending_ratings = ProductRating.query.filter_by(is_approved=False).count()
        
        # متوسط التقييم العام
        avg_rating = db.session.query(func.avg(ProductRating.rating)).filter_by(
            is_approved=True
        ).scalar() or 0
        
        # توزيع التقييمات
        distribution = db.session.query(
            ProductRating.rating,
            func.count(ProductRating.id).label('count')
        ).filter_by(
            is_approved=True
        ).group_by(ProductRating.rating).all()
        
        rating_dist = {i: 0 for i in range(1, 6)}
        for rating, count in distribution:
            rating_dist[rating] = count
        
        # أفضل المنتجات تقييماً
        top_products = db.session.query(
            Product.id,
            Product.name,
            func.avg(ProductRating.rating).label('avg_rating'),
            func.count(ProductRating.id).label('total_ratings')
        ).join(
            ProductRating, Product.id == ProductRating.product_id
        ).filter(
            ProductRating.is_approved == True
        ).group_by(
            Product.id, Product.name
        ).having(
            func.count(ProductRating.id) >= 5  # على الأقل 5 تقييمات
        ).order_by(
            func.avg(ProductRating.rating).desc()
        ).limit(10).all()
        
        stats = {
            "total_ratings": total_ratings,
            "pending_ratings": pending_ratings,
            "average_rating": round(float(avg_rating), 1) if avg_rating else 0,
            "rating_distribution": rating_dist,
            "top_products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "average_rating": round(float(p.avg_rating), 1),
                    "total_ratings": p.total_ratings
                }
                for p in top_products
            ]
        }
        
        if request.is_json or request.args.get("format") == "json":
            return jsonify(stats)
        
        return render_template("ratings/stats.html", stats=stats)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

