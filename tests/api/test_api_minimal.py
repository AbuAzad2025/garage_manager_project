# tests/api/test_api_minimal.py
import pytest

def test_api_404_returns_json(client):
    r = client.get("/api/__nope__")  # مسار غير موجود
    assert r.status_code == 404
    assert r.is_json
    assert r.get_json().get("error") == "Not Found"
