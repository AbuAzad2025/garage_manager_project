import pytest
from flask import url_for
from werkzeug.exceptions import TooManyRequests
from routes.api import ratelimit_handler, server_error

# --- Basic GET checks for multiple API endpoints ---
@pytest.mark.parametrize("endpoint", [
    "/api/customers",
    "/api/suppliers",
    "/api/partners",
    "/api/products",
    "/api/search_categories",
    "/api/warehouses",
    "/api/users",
    "/api/employees",
    "/api/equipment_types",
    "/api/invoices",
    "/api/services",
    "/api/loan_settlements",
    "/api/search_payments"
])
def test_api_get_basic(client, endpoint):
    res = client.get(endpoint)
    assert res.status_code == 200
    js = res.get_json()
    assert isinstance(js, list)

# --- Specific query searches ---
def test_api_customers_search(client):
    res = client.get("/api/customers?q=test")
    assert res.status_code == 200

def test_api_suppliers_search(client):
    res = client.get("/api/suppliers?q=supp")
    assert res.status_code == 200

# --- Product search includes price/sku extras ---
def test_api_products_extras(client):
    res = client.get("/api/products?q=air")
    assert res.status_code == 200
    js = res.get_json()
    if js:
        assert "price" in js[0]
        assert "sku" in js[0]

# --- Not found handler ---
def test_api_error_handlers(client):
    res = client.get("/api/nonexistent")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Not Found"

# --- Simulated rate limit error handler ---
def test_api_rate_limit_error():
    res = ratelimit_handler(TooManyRequests(description="Rate limit hit"))
    assert isinstance(res, tuple)
    assert res[1] == 429
    assert res[0].json["error"] == "Too Many Requests"

# --- Simulated 500 server error ---
def test_api_server_error_handler():
    class DummyErr(Exception):
        description = "fail"

    res = server_error(DummyErr())
    assert isinstance(res, tuple)
    assert res[1] == 500
    assert res[0].json["error"] == "Server Error"
