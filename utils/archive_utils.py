# archive_utils.py - Unified Archive Functions
# Location: /garage_manager/utils/archive_utils.py
# Description: Centralized archive and restore operations

from datetime import datetime
from flask import flash
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models import Archive

def archive_record(record, reason=None, user_id=None):
    """
    Archive a record using the unified Archive.archive_record method
    """
    try:
        if user_id is None and current_user and current_user.is_authenticated:
            user_id = current_user.id
        
        archive = Archive.archive_record(
            record=record,
            reason=reason or 'أرشفة تلقائية',
            user_id=user_id
        )
        
        # Update the original record's archive status
        record.is_archived = True
        record.archived_at = datetime.utcnow()
        record.archived_by = user_id
        record.archive_reason = reason or 'أرشفة تلقائية'
        
        db.session.commit()
        return archive
        
    except SQLAlchemyError as e:
        db.session.rollback()
        raise e

def restore_record(archive_id):
    """
    Restore an archived record
    """
    try:
        archive = Archive.query.get_or_404(archive_id)
        
        # Model mapping for restoration
        model_map = {
            'service_requests': 'ServiceRequest',
            'payments': 'Payment', 
            'sales': 'Sale',
            'expenses': 'Expense',
            'checks': 'Check',
            'customers': 'Customer',
            'suppliers': 'Supplier',
            'partners': 'Partner',
            'shipments': 'Shipment'
        }
        
        model_name = model_map.get(archive.record_type)
        if not model_name:
            raise ValueError(f'نوع السجل غير مدعوم للاستعادة: {archive.record_type}')
        
        # Import the model dynamically
        from models import ServiceRequest, Payment, Sale, Expense, Check, Customer, Supplier, Partner, Shipment
        model_map_actual = {
            'ServiceRequest': ServiceRequest,
            'Payment': Payment,
            'Sale': Sale, 
            'Expense': Expense,
            'Check': Check,
            'Customer': Customer,
            'Supplier': Supplier,
            'Partner': Partner,
            'Shipment': Shipment
        }
        
        model_class = model_map_actual.get(model_name)
        if not model_class:
            raise ValueError(f'نموذج غير موجود: {model_name}')
        
        # Find the original record
        original_record = model_class.query.get(archive.record_id)
        
        if original_record:
            # Restore the record
            original_record.is_archived = False
            original_record.archived_at = None
            original_record.archived_by = None
            original_record.archive_reason = None
            
            # Delete the archive entry
            db.session.delete(archive)
            db.session.commit()
            
            return original_record
        else:
            # Record was hard deleted, create new one from archive data
            import json
            archived_data = json.loads(archive.archived_data)
            
            new_record = model_class()
            for key, value in archived_data.items():
                if hasattr(new_record, key) and key not in ['id', 'is_archived', 'archived_at', 'archived_by', 'archive_reason']:
                    setattr(new_record, key, value)
            
            db.session.add(new_record)
            db.session.flush()
            
            # Delete the archive entry
            db.session.delete(archive)
            db.session.commit()
            
            return new_record
            
    except SQLAlchemyError as e:
        db.session.rollback()
        raise e

def check_archive_permissions(record_type, user=None):
    """
    Check if user has permission to archive this record type
    """
    if user is None:
        user = current_user
    
    if not user or not user.is_authenticated:
        return False
    
    # Permission mapping
    permission_map = {
        'service_requests': 'manage_service',
        'payments': 'manage_payments',
        'sales': 'manage_sales', 
        'expenses': 'manage_expenses',
        'checks': 'manage_checks',
        'customers': 'manage_customers',
        'suppliers': 'manage_vendors',
        'partners': 'manage_vendors',
        'shipments': 'manage_shipments'
    }
    
    required_permission = permission_map.get(record_type)
    if not required_permission:
        return False
    
    # Check if user has the required permission
    return user.has_permission(required_permission)

def get_archive_stats():
    """
    Get archive statistics
    """
    from sqlalchemy import func
    from datetime import datetime
    
    total_archives = Archive.query.count()
    
    type_stats = db.session.query(
        Archive.record_type,
        func.count(Archive.id).label('count')
    ).group_by(Archive.record_type).all()
    
    current_month = datetime.now().replace(day=1)
    monthly_archives = Archive.query.filter(
        Archive.archived_at >= current_month
    ).count()
    
    return {
        'total_archives': total_archives,
        'type_stats': type_stats,
        'monthly_archives': monthly_archives
    }
