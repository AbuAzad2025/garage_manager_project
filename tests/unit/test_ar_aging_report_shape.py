# tests/unit/test_ar_aging_report_shape.py
from reports import ar_aging_report

def test_ar_aging_report_shape(app):
    with app.app_context():
        rpt = ar_aging_report()
        assert isinstance(rpt, dict)
        assert "data" in rpt and isinstance(rpt["data"], list)
        assert "totals" in rpt and isinstance(rpt["totals"], dict)
        # لو في بيانات، تأكد الحقول الأساسية:
        for row in rpt["data"]:
            assert "customer" in row
            assert "balance" in row
            assert "buckets" in row
            for key in ("0-30", "31-60", "61-90", "90+"):
                assert key in row["buckets"]
