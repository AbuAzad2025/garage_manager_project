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

def test_payments_list_with_filters_no_data(client, app):
    _login_admin(client, app)

    qs = {
        'entity_type': 'SUPPLIER',
        'status': 'COMPLETED',
        'direction': 'OUT',
        'method': 'cash',
        'start_date': '2025-01-01',
        'end_date': '2025-12-31',
        'page': 1
    }
    resp = client.get(url_for('payments.list_payments', **qs))
    assert resp.status_code == 200

    qs['entity_type'] = 'CUSTOMER'
    qs['direction'] = 'IN'
    resp = client.get(url_for('payments.list_payments', **qs))
    assert resp.status_code == 200
