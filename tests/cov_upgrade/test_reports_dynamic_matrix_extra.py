import pytest
from flask import url_for

@pytest.mark.usefixtures("app", "client")
def test_reports_endpoints_with_filter_matrix(client, app):
    endpoints = []
    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods:
                continue
            ep = rule.endpoint
            if not (ep.startswith("reports") or "reports" in ep or ep.startswith("reports_bp")):
                continue
            if rule.arguments:
                defaults = rule.defaults or {}
                if not all(arg in defaults for arg in rule.arguments):
                    continue
            try:
                url = url_for(rule.endpoint, **(rule.defaults or {}))
            except Exception:
                continue
            endpoints.append(url)

    qs_list = [
        {},
        {"format": "html"},
        {"format": "json"},
        {"group_by": "day"},
        {"group_by": "month"},
        {"status": "PAID"},
        {"date_from": "2025-01-01", "date_to": "2025-12-31"},
        {"format": "csv", "group_by": "status", "date_from": "2025-01-01", "date_to": "2025-12-31"},
    ]

    hit = 0
    for url in endpoints:
        for q in qs_list:
            r = client.get(url, query_string=q, follow_redirects=True)
            assert r.status_code == 200
            hit += 1

    assert hit > 0
