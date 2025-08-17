import re
import pytest
from flask import url_for

SKIP_RE = re.compile(r"(logout|delete|remove|restore|reset|clear|drop|shutdown)", re.I)

@pytest.mark.parametrize("follow", [True])
def test_all_safe_get_routes(client, app, follow):
    hit = 0
    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods:
                continue
            if rule.endpoint.startswith("static"):
                continue
            if SKIP_RE.search(rule.rule) or SKIP_RE.search(rule.endpoint):
                continue
            # تجنّب الباراميترات الإلزامية
            if rule.arguments:
                defaults = rule.defaults or {}
                if not all(arg in defaults for arg in rule.arguments):
                    continue
            try:
                url = url_for(rule.endpoint, **(rule.defaults or {}))
            except Exception:
                continue

            resp = client.get(url, follow_redirects=follow)
            assert resp.status_code < 500, f"{rule.endpoint} -> {resp.status_code}"
            hit += 1
    assert hit > 0
