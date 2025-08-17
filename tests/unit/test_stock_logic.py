# -*- coding: utf-8 -*-
import pytest
from extensions import db
import models as M

_HAS = all(hasattr(M, n) for n in ("StockLevel", "Product", "Warehouse"))

@pytest.mark.skipif(not _HAS, reason="Stock models not found")
def test_stock_quantity_never_negative(app):
    """ممنوع أي قيمة سالبة للمخزون: إمّا يفشل عند الإسناد (validator) أو عند commit (DB CHECK)."""
    with app.app_context():
        prod = M.Product(name="__tprod__")
        wh = M.Warehouse(name="__twh__")
        db.session.add_all([prod, wh]); db.session.commit()

        sl = M.StockLevel(product_id=prod.id, warehouse_id=wh.id, quantity=0)
        db.session.add(sl); db.session.commit()

        # جرّب القيم السالبة
        try:
            sl.quantity = -1  # إن وُجد validator سيفشل هنا
        except Exception:
            db.session.rollback()
        else:
            # لو ما فشل عند الإسناد، لازم يفشل عند commit بسبب قيد الـDB
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()
