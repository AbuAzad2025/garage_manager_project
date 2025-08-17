# File: tests/unit/test_reports_logic.py
import pytest

try:
    from reports import age_bucket
    _HAS = callable(age_bucket)
except Exception:
    _HAS = False


@pytest.mark.skipif(not _HAS, reason="age_bucket غير موجود")
@pytest.mark.parametrize(
    "inp,expected",
    [
        # 0-30
        (0, "0-30"), (1, "0-30"), (30, "0-30"),
        # 31-60
        (31, "31-60"), (60, "31-60"),
        # 61-90
        (61, "61-90"), (90, "61-90"),
        # 90+
        (91, "90+"), (365, "90+"),
        # حالات إدخال غريبة
        (-1, "0-30"),          # السالب يُقصّ لـ 0
        ("15", "0-30"),        # نص رقمي
        ("مش رقم", "0-30"),    # نص غير رقمي → يعامل كـ 0
    ],
)
def test_age_bucket_edges(inp, expected):
    assert age_bucket(inp) == expected
