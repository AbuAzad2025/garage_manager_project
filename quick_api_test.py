from app import app
from models import User

with app.test_client() as c:
    with app.app_context():
        u = User.query.filter_by(username='azad').first()
        with c.session_transaction() as s:
            s['_user_id'] = str(u.id)
        
        r = c.get('/checks/api/checks')
        print(f'Status: {r.status_code}')
        if r.status_code == 200:
            d = r.get_json()
            print(f'Total: {d.get("total")}')
        else:
            print(f'Error: {r.get_data(as_text=True)[:200]}')

