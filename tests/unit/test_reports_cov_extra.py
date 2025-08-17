# tests/unit/test_reports_cov_extra.py
from datetime import date, timedelta
import reports

def test_reports_sales_and_aging_no_data():
    end = date.today()
    start = end - timedelta(days=7)
    # لا بيانات = ترجع هياكل آمنة بدون كسر
    sr = reports.sales_report(start, end)
    assert isinstance(sr, dict)
    for key in ['daily_labels','daily_values','total_revenue']:
        assert key in sr

    ar = reports.ar_aging_report(start, end)
    assert isinstance(ar, dict)
