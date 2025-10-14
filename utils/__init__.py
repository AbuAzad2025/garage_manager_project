# __init__.py - Utils Package
# Location: /garage_manager/utils/__init__.py
# Description: Utils package initialization

# Import calculation functions
from .calculations import (
    D, q0, q2, _q2, money_fmt, 
    line_total_decimal, safe_divide, calculate_percentage
)

# Import archive functions  
from .archive_utils import (
    archive_record, restore_record, 
    check_archive_permissions, get_archive_stats
)

# Import existing security functions
from .security import (
    sanitize_input, is_safe_url, validate_email, validate_phone,
    validate_password_strength, sanitize_filename, check_sql_injection,
    check_xss, validate_amount, rate_limit_key, log_security_event,
    constant_time_compare, timing_safe_login_check, require_ownership,
    prevent_race_condition, validate_amount_change, log_suspicious_activity,
    check_request_signature, rate_limit_by_user
)

# Note: permission_required and super_only are imported from the main utils.py file
# They are not included here to avoid circular imports

__all__ = [
    # Calculation functions
    'D', 'q0', 'q2', '_q2', 'money_fmt',
    'line_total_decimal', 'safe_divide', 'calculate_percentage',
    
    # Archive functions
    'archive_record', 'restore_record', 
    'check_archive_permissions', 'get_archive_stats',
    
    # Security functions
    'sanitize_input', 'is_safe_url', 'validate_email', 'validate_phone',
    'validate_password_strength', 'sanitize_filename', 'check_sql_injection',
    'check_xss', 'validate_amount', 'rate_limit_key', 'log_security_event',
    'constant_time_compare', 'timing_safe_login_check', 'require_ownership',
    'prevent_race_condition', 'validate_amount_change', 'log_suspicious_activity',
    'check_request_signature', 'rate_limit_by_user'
]
