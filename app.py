# File: app.py

import os
from datetime import datetime

from flask import Flask
from flask_cors import CORS
from flask_login import AnonymousUserMixin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_mail import Mail
from flask_socketio import SocketIO

from config import Config
from extensions import db, migrate, login_manager, socketio, mail, csrf
from utils import qr_to_base64, init_app

from routes.auth        import auth_bp
from routes.main        import main_bp
from routes.users       import users_bp
from routes.service     import service_bp
from routes.customers   import customers_bp
from routes.sales       import sales_bp
from routes.notes       import notes_bp
from routes.reports     import reports_bp
from routes.shop        import shop_bp
from routes.expenses    import expenses_bp
from routes.vendors     import vendors_bp
from routes.shipments   import shipments_bp
from routes.warehouses  import warehouses_bp
from routes.parts       import parts_bp
from routes.payments    import payments_bp
from routes.permissions import permissions_bp
from routes.roles       import roles_bp


class MyAnonymousUser(AnonymousUserMixin):
    def has_permission(self, perm_name):
        return False


def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(Config)

    csrf.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})
    Limiter(key_func=get_remote_address,
            default_limits=[app.config.get("RATELIMIT_DEFAULT")],
            storage_uri=app.config.get("REDIS_URL")
    ).init_app(app)
    init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.anonymous_user = MyAnonymousUser
    login_manager.session_protection = 'strong'
    socketio.init_app(app, async_mode='threading')
    mail.init_app(app)

    app.jinja_env.filters['qr_to_base64'] = qr_to_base64
    app.jinja_env.globals['now'] = datetime.utcnow

    for bp in (
        auth_bp, main_bp, users_bp, service_bp, customers_bp,
        sales_bp, notes_bp, reports_bp, shop_bp, expenses_bp,
        vendors_bp, shipments_bp, warehouses_bp, parts_bp,
        payments_bp, permissions_bp, roles_bp
    ):
        app.register_blueprint(bp)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app


app = create_app()

if __name__ == '__main__':
    socketio.run(
        app,
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=app.config.get('DEBUG', False)
    )
