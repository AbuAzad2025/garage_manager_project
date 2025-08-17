# tests/views/test_payments_cov_extra.py
from flask import url_for

def _login_admin(client, app):
    # أنشئ super_admin وسجّل دخول حتى نمر من permission_required
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
        db.session.add_all([role, user]); db.session.commit()
    client.post(url_for('auth.login'), data={'username':'cov_admin','password':'x'})

def test_payments_index_json_and_filters_matrix(client, app):
    _login_admin(client, app)

    # بدون بيانات: نتأكد ما بتكسر مع كل الفلاتر/التقسيم
    combos = [
        # لا فلاتر
        {},
        # فلاتر صحيحة بالأسماء الحديثة
        {'entity_type':'SUPPLIER','status':'COMPLETED','direction':'OUT','method':'cash',
         'start_date':'2025-01-01','end_date':'2025-12-31','page':1,'per_page':5},
        # method غير معروف ليمر فرع fallback
        {'method':'unknown'},
        # entity_id مع نوع لكي يمرّ فرع switch على الحقول
        {'entity_type':'supplier','entity_id':999},
    ]
    for qs in combos:
        resp = client.get(url_for('payments.index', **qs),
                          headers={'Accept':'application/json'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'payments' in data and 'total_pages' in data and 'current_page' in data

def test_payments_index_html_paths_ok(client, app):
    _login_admin(client, app)
    # HTML افتراضي
    resp = client.get(url_for('payments.index'))
    assert resp.status_code == 200
    # ترقيم صفحات بدون بيانات
    resp = client.get(url_for('payments.index', page=2, per_page=1))
    assert resp.status_code == 200
