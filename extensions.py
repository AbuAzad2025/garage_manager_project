from __future__ import annotations

import json
import logging
import os
import sys
import glob
import sqlite3
from datetime import datetime, timezone

from flask import g, has_request_context
from apscheduler.schedulers.background import BackgroundScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_caching import Cache
try:
    from flask_compress import Compress
except ImportError:
    class Compress:
        def __init__(self, *args, **kwargs):
            pass
        def init_app(self, app):
            pass
from sqlalchemy import event
from sqlalchemy.engine import Engine

try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except Exception:
    pdfmetrics = None
    TTFont = None

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _Fore:
        BLUE = ""; GREEN = ""; YELLOW = ""; RED = ""
    class _Style:
        BRIGHT = ""; RESET_ALL = ""
    Fore, Style = _Fore(), _Style()
    def colorama_init(*args, **kwargs):
        return

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
except Exception:
    sentry_sdk = None


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
        else:
            record.request_id = "-"
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in (
                "name","msg","args","levelname","levelno","pathname","filename",
                "module","exc_info","exc_text","stack_info","lineno","funcName",
                "created","msecs","relativeCreated","thread","threadName",
                "processName","process","request_id"
            ):
                continue
            try:
                json.dumps({k: v})
                base[k] = v
            except Exception:
                base[k] = str(v)
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":   Fore.BLUE,
        "INFO":    Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR":   Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = Style.RESET_ALL
        req_id = getattr(record, "request_id", "-")
        base = f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] {color}{record.levelname}{reset} {req_id} {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(app):
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    out_handler = logging.StreamHandler(sys.stdout)
    out_handler.setLevel(level)
    out_handler.addFilter(RequestIdFilter())
    out_handler.setFormatter(JSONFormatter() if app.config.get("JSON_LOGS") else ColorFormatter())

    err_handler = logging.StreamHandler(sys.stderr)
    err_handler.setLevel(logging.ERROR)
    err_handler.addFilter(RequestIdFilter())
    err_handler.setFormatter(JSONFormatter() if app.config.get("JSON_LOGS") else ColorFormatter())

    for lg in (app.logger, logging.getLogger(), logging.getLogger("sqlalchemy.engine")):
        lg.handlers.clear()
        lg.setLevel(level)
        lg.addHandler(out_handler)
        lg.addHandler(err_handler)
        lg.propagate = False


def setup_sentry(app):
    dsn = (app.config.get("SENTRY_DSN") or "").strip()
    if not dsn or not sentry_sdk:
        app.logger.info("Sentry disabled (no DSN configured).")
        return
    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0),
            profiles_sample_rate=app.config.get("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
            environment=app.config.get("APP_ENV", "production"),
            release=app.config.get("APP_VERSION") or None,
            send_default_pii=False,
            max_breadcrumbs=100,
        )
        app.logger.info("Sentry initialized.")
    except Exception as e:
        app.logger.warning("Sentry setup failed: %s", e)


db = SQLAlchemy(session_options={"expire_on_commit": False})
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
compress = Compress()
socketio = SocketIO(cors_allowed_origins="*", logger=False, engineio_logger=False)

# نظام الإشعارات الفورية
def send_notification(user_id: int, notification_type: str, title: str, message: str, data: dict = None):
    """
    إرسال إشعار فوري للمستخدم
    
    ⚠️ معطّل: كان يسبب تعليق في النظام
    """
    # ❌ معطّل مؤقتاً - كان يسبب مشاكل أداء
    return
    
    # الكود القديم (معطّل):
    # try:
    #     notification = {
    #         "type": notification_type,
    #         "title": title,
    #         "message": message,
    #         "timestamp": datetime.now(timezone.utc).isoformat(),
    #         "data": data or {}
    #     }
    #     socketio.emit('notification', notification, room=f'user_{user_id}')
    # except Exception as e:
    #     logging.getLogger(__name__).error(f"Failed to send notification: {e}")

def send_broadcast_notification(notification_type: str, title: str, message: str, data: dict = None):
    """
    إرسال إشعار عام لجميع المستخدمين
    
    ⚠️ معطّل: كان يسبب تعليق في النظام
    """
    # ❌ معطّل مؤقتاً - كان يسبب مشاكل أداء
    return
    
    # الكود القديم (معطّل):
    # try:
    #     notification = {
    #         "type": notification_type,
    #         "title": title,
    #         "message": message,
    #         "timestamp": datetime.now(timezone.utc).isoformat(),
    #         "data": data or {}
    #     }
    #     socketio.emit('broadcast_notification', notification)
    # except Exception as e:
    #     logging.getLogger(__name__).error(f"Failed to send broadcast notification: {e}")

def send_system_alert(alert_type: str, message: str, severity: str = "warning"):
    """
    إرسال تنبيه نظام
    
    ⚠️ معطّل: كان يسبب تعليق في النظام
    """
    # ❌ معطّل مؤقتاً - كان يسبب مشاكل أداء
    return
    
    # الكود القديم (معطّل):
    # try:
    #     alert = {
    #         "type": "system_alert",
    #         "alert_type": alert_type,
    #         "message": message,
    #         "severity": severity,
    #         "timestamp": datetime.now(timezone.utc).isoformat()
    #     }
    #     socketio.emit('system_alert', alert)
    # except Exception as e:
    #     logging.getLogger(__name__).error(f"Failed to send system alert: {e}")
cache = Cache()


def _rate_limit_key():
    try:
        from flask_login import current_user
        if getattr(current_user, "is_authenticated", False):
            return f"user:{current_user.get_id()}"
    except Exception:
        pass
    return get_remote_address()


limiter = Limiter(key_func=_rate_limit_key, default_limits=[])
scheduler = BackgroundScheduler()


@event.listens_for(Engine, "connect")
def _sqlite_pragmas_on_connect(dbapi_connection, connection_record):
    try:
        if isinstance(dbapi_connection, sqlite3.Connection):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA cache_size=-64000")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.execute("PRAGMA mmap_size=268435456")
            cur.execute("PRAGMA page_size=4096")
            cur.execute("PRAGMA auto_vacuum=INCREMENTAL")
            cur.close()
    except Exception:
        pass


def perform_backup_db(app):
    """Database backup utility"""
    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite:///"):
            app.logger.warning("Backup skipped: Database is not SQLite")
            return
        
        db_path = uri.replace("sqlite:///", "")
        if not os.path.exists(db_path):
            app.logger.error(f"Database file not found: {db_path}")
            return
        
        backup_dir = app.config.get("BACKUP_DB_DIR")
        os.makedirs(backup_dir, exist_ok=True)
        
        # إضافة معلومات إضافية للنسخة الاحتياطية
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{ts}.db")
        
        # نسخ احتياطي مع التحقق من التكامل
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(backup_path)
        
        try:
            # نسخ احتياطي مع التحقق
            src.backup(dst)
            
            # التحقق من صحة النسخة الاحتياطية
            dst.execute("PRAGMA integrity_check")
            result = dst.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                app.logger.error(f"Backup integrity check failed: {result[0]}")
                dst.close()
                os.remove(backup_path)
                return
            
            # إضافة معلومات النسخة الاحتياطية
            backup_info = {
                "timestamp": ts,
                "original_size": os.path.getsize(db_path),
                "backup_size": os.path.getsize(backup_path),
                "version": app.config.get("APP_VERSION", "unknown")
            }
            
            # حفظ معلومات النسخة الاحتياطية
            info_path = os.path.join(backup_dir, f"backup_{ts}.info")
            with open(info_path, "w") as f:
                import json
                json.dump(backup_info, f, indent=2)
            
            app.logger.info(f"Database backup completed: {backup_path}")
            
        except Exception as e:
            app.logger.error(f"Backup failed: {e}")
            if os.path.exists(backup_path):
                os.remove(backup_path)
        finally:
            src.close()
            dst.close()
        
        # تنظيف النسخ القديمة
        keep_last = app.config.get("BACKUP_KEEP_LAST", 5)
        backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.db")))
        if len(backups) > keep_last:
            for old in backups[:-keep_last]:
                try:
                    os.remove(old)
                    # حذف ملف المعلومات أيضاً
                    info_file = old.replace(".db", ".info")
                    if os.path.exists(info_file):
                        os.remove(info_file)
                except Exception as e:
                    app.logger.warning(f"Failed to remove old backup {old}: {e}")
                    
    except Exception as e:
        app.logger.error(f"Backup process failed: {e}")


def update_exchange_rates_job(app):
    """تحديث أسعار الصرف دورياً من السيرفرات العالمية"""
    try:
        with app.app_context():
            from models import auto_update_missing_rates
            
            result = auto_update_missing_rates()
            
            if result.get('success'):
                updated = result.get('updated_rates', 0)
                app.logger.info(f"[FX Update] Updated {updated} exchange rates")
            else:
                app.logger.warning(f"[FX Update] Failed: {result.get('message', 'Unknown error')}")
                
    except Exception as e:
        app.logger.error(f"[FX Update] Job failed: {e}")


def perform_backup_sql(app):
    """نسخ احتياطي SQL محسن"""
    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite:///"):
            app.logger.warning("SQL backup skipped: Database is not SQLite")
            return
        
        db_path = uri.replace("sqlite:///", "")
        if not os.path.exists(db_path):
            app.logger.error(f"Database file not found: {db_path}")
            return
        
        backup_dir = app.config.get("BACKUP_SQL_DIR")
        os.makedirs(backup_dir, exist_ok=True)
        
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{ts}.sql")
        
        conn = sqlite3.connect(db_path)
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                # إضافة معلومات النسخة الاحتياطية
                f.write(f"-- Database Backup\n")
                f.write(f"-- Timestamp: {ts}\n")
                f.write(f"-- Version: {app.config.get('APP_VERSION', 'unknown')}\n")
                f.write(f"-- Original Size: {os.path.getsize(db_path)} bytes\n\n")
                
                # نسخ البيانات
                for line in conn.iterdump():
                    f.write(f"{line}\n")
            
            app.logger.info(f"SQL backup completed: {backup_path}")
            
        except Exception as e:
            app.logger.error(f"SQL backup failed: {e}")
            if os.path.exists(backup_path):
                os.remove(backup_path)
        finally:
            conn.close()
        
        # تنظيف النسخ القديمة
        keep_last = app.config.get("BACKUP_KEEP_LAST", 5)
        backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.sql")))
        if len(backups) > keep_last:
            for old in backups[:-keep_last]:
                try:
                    os.remove(old)
                except Exception as e:
                    app.logger.warning(f"Failed to remove old SQL backup {old}: {e}")
                    
    except Exception as e:
        app.logger.error(f"SQL backup process failed: {e}")


def register_fonts(app=None):
    try:
        if not pdfmetrics or not TTFont:
            return
        base_path = os.path.join(app.root_path if app else os.getcwd(), "static", "fonts")
        fonts = {
            "Amiri": "Amiri-Regular.ttf",
            "Amiri-Bold": "Amiri-Bold.ttf",
            "Amiri-Italic": "Amiri-Italic.ttf",
            "Amiri-BoldItalic": "Amiri-BoldItalic.ttf",
        }
        for name, file in fonts.items():
            path = os.path.join(base_path, file)
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
    except Exception as e:
        logging.error("Font registration failed: %s", e)


def _safe_start_scheduler(app):
    skip_cmds = ("db", "seed", "shell", "migrate", "upgrade", "downgrade", "init")
    if any(cmd in sys.argv for cmd in skip_cmds):
        app.logger.info("Scheduler skipped: CLI context.")
        return
    if os.environ.get("DISABLE_SCHEDULER"):
        app.logger.info("Scheduler disabled by environment variable.")
        return
    try:
        if not scheduler.running:
            scheduler.start()
            app.logger.info("APScheduler started.")
        else:
            app.logger.info("APScheduler already running; skip start.")
    except Exception as e:
        app.logger.warning(f"Scheduler start skipped: {e}")


def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = app.config.get("LOGIN_VIEW", "auth.login")
    login_manager.login_message_category = app.config.get("LOGIN_MESSAGE_CATEGORY", "warning")

    csrf.init_app(app)
    mail.init_app(app)
    
    compress.init_app(app)
    app.config.setdefault('COMPRESS_MIMETYPES', [
        'text/html', 'text/css', 'text/xml', 'text/javascript',
        'application/json', 'application/javascript'
    ])
    app.config.setdefault('COMPRESS_LEVEL', 6)
    app.config.setdefault('COMPRESS_MIN_SIZE', 500)

    # تعطيل SocketIO في Development mode لتجنب أخطاء WebSocket
    # يمكن تفعيله في Production مع gunicorn + gevent
    if not app.config.get('SOCKETIO_ENABLED', False):
        # تهيئة بدون websocket transport (polling only)
        socketio.init_app(
            app,
            async_mode='threading',  # استخدام threading بدل eventlet/gevent
            cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
            logger=False,
            engineio_logger=False,
            ping_timeout=20,
            ping_interval=25,
            transports=['polling']  # فقط polling، بدون websocket
        )
    else:
        # في Production mode
        socketio.init_app(
            app,
            async_mode=app.config.get("SOCKETIO_ASYNC_MODE"),
            message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
            cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
            logger=app.config.get("SOCKETIO_LOGGER", False),
            engineio_logger=app.config.get("SOCKETIO_ENGINEIO_LOGGER", False),
            ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 20),
            ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 25),
            max_http_buffer_size=app.config.get("SOCKETIO_MAX_HTTP_BUFFER_SIZE", 100_000_000),
        )

    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    app.config.setdefault("RATELIMIT_EXEMPT_SUPER", True)

    limiter.init_app(app)
    cache.init_app(app)

    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        if isinstance(default_limit, (list, tuple)):
            limiter.default_limits = [str(x).strip() for x in default_limit if str(x).strip()]
        else:
            parts = [p.strip() for p in str(default_limit).split(";") if p.strip()]
            limiter.default_limits = parts

    if app.config.get("RATELIMIT_EXEMPT_SUPER", True):
        @limiter.request_filter
        def _exempt_super_admin():
            try:
                from flask_login import current_user
                if getattr(current_user, "is_authenticated", False):
                    if getattr(current_user, "is_super_role", False):
                        return True
                    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).strip().lower()
                    if role_name == "super_admin":
                        return True
            except Exception:
                return False
            return False

    try:
        scheduler.add_job(
            lambda: perform_backup_db(app),
            "interval",
            seconds=app.config.get("BACKUP_DB_INTERVAL").total_seconds(),
            id="db_backup",
            replace_existing=True,
        )
        scheduler.add_job(
            lambda: perform_backup_sql(app),
            "interval",
            seconds=app.config.get("BACKUP_SQL_INTERVAL").total_seconds(),
            id="sql_backup",
            replace_existing=True,
        )
        
        # مهمة تحديث أسعار الصرف دورياً
        scheduler.add_job(
            lambda: update_exchange_rates_job(app),
            "interval",
            hours=1,  # كل ساعة
            id="update_fx_rates",
            replace_existing=True,
        )
    except Exception as e:
        app.logger.warning(f"Scheduler job registration failed: {e}")

    _safe_start_scheduler(app)
    register_fonts(app)
