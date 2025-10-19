import sys
import os

# Add your project directory to the sys.path
project_home = '/home/Azad/garage_manager'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['FLASK_ENV'] = 'production'
os.environ['APP_ENV'] = 'production'
os.environ['PYTHONUTF8'] = '1'

# Import your Flask app - استخدام create_app factory
from app import app as application

# إذا كان عندك create_app فقط، استخدم هذا بدلاً:
# from app import create_app
# application = create_app()
