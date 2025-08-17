# tests/views/test_payments_cov_extra.py
from flask import url_for

def _login_admin(client, app):
    from models import Role, User
    with app.app_context():
        role = Role.query.filter_by(name='super_admin').first()
        if not role:
            role = Role(name='super_admin', description='full access')
        user = User.query.filter_by(username='cov_admin').first()
        if not user:
            user = User(username='cov_admin', email='cov_admin@test.local')
            user.set_password('x')
            user.role = role
        from extensions import db
        db.session.add_all([role, user])
        db.session.commit()
    client.post(url_for('auth.login'), data={'username': 'cov_admin', 'password': 'x'})

def test_payments_index_json_and_filters_matrix(client, app):
    _login_admin(client, app)

    combos = [
        {},
        {'entity_type': 'SUPPLIER', 'status': 'COMPLETED', 'direction': 'OUT', 'method': 'cash',
         'start_date': '2025-01-01', 'end_date': '2025-12-31', 'page': 1, 'per_page': 5},
        {'method': 'unknown'},
        {'entity_type': 'supplier', 'entity_id': 999},
        {'entity_type': 'customer', 'entity_id': 999},
        {'entity_type': 'partner', 'entity_id': 999},
        {'entity_type': 'sale', 'entity_id': 999},
        {'entity_type': 'invoice', 'entity_id': 999},
        {'entity_type': 'preorder', 'entity_id': 999},
        {'entity_type': 'service', 'entity_id': 999},
        {'entity_type': 'expense', 'entity_id': 999},
        {'entity_type': 'shipment', 'entity_id': 999},
        {'entity_type': 'loan', 'entity_id': 999},
    ]

    for qs in combos:
        resp = client.get(url_for('payments.list_payments', **qs), headers={'Accept': 'application/json'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'payments' in data
        assert 'total_pages' in data
        assert 'current_page' in data

def test_payments_index_html_paths_ok(client, app):
    _login_admin(client, app)

    resp = client.get(url_for('payments.list_payments'))
    assert resp.status_code == 200

    resp = client.get(url_for('payments.list_payments', page=2, per_page=1))
    assert resp.status_code == 200
