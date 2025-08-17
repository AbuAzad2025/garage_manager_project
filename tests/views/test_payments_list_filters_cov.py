from flask import url_for

def test_payments_list_with_filters_no_data(client, app):
    qs = {
        'entity': 'SUPPLIER',
        'status': 'COMPLETED',
        'direction': 'OUT',
        'method': 'cash',
        'start': '2025-01-01',
        'end': '2025-12-31',
        'page': 1,
    }
    resp = client.get(url_for('payments.list', **qs))
    assert resp.status_code in (200, 302)  # حسب الصلاحيات قد يعيد تحويل، المهم لا 5xx

    qs['entity'] = 'CUSTOMER'
    qs['direction'] = 'IN'
    resp = client.get(url_for('payments.list', **qs))
    assert resp.status_code in (200, 302)
