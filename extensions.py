# File: extensions.py
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

# Database
db = SQLAlchemy()

# Database migrations
migrate = Migrate()

# User session management
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.session_protection = "strong"

# SocketIO for real-time events
socketio = SocketIO()

# Mail service
mail = Mail()

# CSRF protection for forms
csrf = CSRFProtect()
