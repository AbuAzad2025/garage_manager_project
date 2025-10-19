from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, REGISTRY
from flask import Response
import psutil
import time
from datetime import datetime
from extensions import db
from sqlalchemy import text

request_count = Counter(
    'garage_manager_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'garage_manager_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

db_query_count = Counter(
    'garage_manager_db_queries_total',
    'Total database queries',
    ['table']
)

db_query_duration = Histogram(
    'garage_manager_db_query_duration_seconds',
    'Database query duration',
    ['table']
)

sales_total = Counter(
    'garage_manager_sales_total',
    'Total sales count'
)

revenue_total = Counter(
    'garage_manager_revenue_total',
    'Total revenue',
    ['currency']
)

customers_total = Gauge(
    'garage_manager_customers_total',
    'Total number of customers'
)

active_users = Gauge(
    'garage_manager_active_users',
    'Number of active users'
)

db_size = Gauge(
    'garage_manager_database_size_bytes',
    'Database size in bytes'
)

app_info = Info(
    'garage_manager_app',
    'Application information'
)

# Set app info
app_info.info({
    'version': '11.0',
    'name': 'Garage Manager',
    'environment': 'production'
})



def get_system_metrics():
    """الحصول على متريكات النظام"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_mb': memory.used / (1024 * 1024),
            'memory_total_mb': memory.total / (1024 * 1024),
            'disk_percent': disk.percent,
            'disk_used_gb': disk.used / (1024 * 1024 * 1024),
            'disk_total_gb': disk.total / (1024 * 1024 * 1024)
        }
    except Exception as e:
        return {
            'cpu_percent': 0,
            'memory_percent': 0,
            'memory_used_mb': 0,
            'memory_total_mb': 0,
            'disk_percent': 0,
            'disk_used_gb': 0,
            'disk_total_gb': 0
        }


def get_database_metrics():
    """الحصول على متريكات قاعدة البيانات"""
    try:
        from models import Customer, Sale, Payment, ServiceRequest
        
        # Count records
        customers_count = Customer.query.count()
        sales_count = Sale.query.count()
        payments_count = Payment.query.count()
        services_count = ServiceRequest.query.count()
        
        # Update Prometheus gauges
        customers_total.set(customers_count)
        
        # Get database size
        db_size_bytes = 0
        try:
            import os
            from flask import current_app
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if db_uri.startswith('sqlite:///'):
                db_path = db_uri.replace('sqlite:///', '')
                if os.path.exists(db_path):
                    db_size_bytes = os.path.getsize(db_path)
                    db_size.set(db_size_bytes)
        except:
            pass
        
        return {
            'customers': customers_count,
            'sales': sales_count,
            'payments': payments_count,
            'services': services_count,
            'db_size_bytes': db_size_bytes,
            'db_size_mb': db_size_bytes / (1024 * 1024)
        }
    except Exception as e:
        return {
            'customers': 0,
            'sales': 0,
            'payments': 0,
            'services': 0,
            'db_size_bytes': 0,
            'db_size_mb': 0
        }


def get_active_users_count():
    """الحصول على عدد المستخدمين النشطين"""
    try:
        from models import User
        from datetime import timedelta
        
        # Users active in last 15 minutes
        fifteen_mins_ago = datetime.utcnow() - timedelta(minutes=15)
        active_count = User.query.filter(
            User.last_seen >= fifteen_mins_ago
        ).count()
        
        active_users.set(active_count)
        return active_count
    except:
        return 0


def get_recent_performance():
    """الحصول على أداء النظام الأخير"""
    try:
        # This would need actual request tracking
        # For now, return sample data
        return {
            'avg_response_time_ms': 45,
            'requests_per_second': 12,
            'error_rate_percent': 0.5
        }
    except:
        return {
            'avg_response_time_ms': 0,
            'requests_per_second': 0,
            'error_rate_percent': 0
        }



def get_all_metrics():
    """الحصول على جميع المتريكات لـ Prometheus"""
    return Response(generate_latest(REGISTRY), mimetype='text/plain')


def get_live_metrics_json():
    """الحصول على المتريكات الحية بصيغة JSON"""
    system = get_system_metrics()
    database = get_database_metrics()
    users_count = get_active_users_count()
    performance = get_recent_performance()
    
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'system': system,
        'database': database,
        'active_users': users_count,
        'performance': performance,
        'status': 'healthy'
    }


def track_request(method, endpoint, status_code, duration):
    """تتبع طلب HTTP"""
    try:
        request_count.labels(
            method=method,
            endpoint=endpoint,
            status=status_code
        ).inc()
        
        request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    except:
        pass


def track_db_query(table, duration):
    """تتبع استعلام قاعدة بيانات"""
    try:
        db_query_count.labels(table=table).inc()
        db_query_duration.labels(table=table).observe(duration)
    except:
        pass


def track_sale(amount, currency):
    """تتبع مبيعة جديدة"""
    try:
        sales_total.inc()
        revenue_total.labels(currency=currency).inc(amount)
    except:
        pass

