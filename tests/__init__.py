def login_owner(app, client):
    try:
        app.config['WTF_CSRF_ENABLED'] = False
        from extensions import db
        from models import User, Role
        owner_role = Role.query.filter(Role.name.ilike('owner')).first()
        if not owner_role:
            owner_role = Role(name='owner', description='Owner role')
            db.session.add(owner_role)
            db.session.commit()
        user = User.query.filter(User.username.ilike('owner')).first()
        if not user:
            user = User(username='owner', email='owner@example.com', role=owner_role, is_active=True)
            user.set_password('OwnerPass2024!')
            db.session.add(user)
            db.session.commit()
        client.post('/auth/login', data={'username': 'owner', 'password': 'OwnerPass2024!'}, follow_redirects=False)
    except Exception:
        pass
