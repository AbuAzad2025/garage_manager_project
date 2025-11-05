from extensions import socketio, cache

def emit_balance_update(entity_type, entity_id, balance):
    try:
        cache_key = f'{entity_type}_balance_{entity_id}'
        cache.delete(cache_key)
        
        socketio.emit('balance_updated', {
            'entity_type': entity_type,
            'entity_id': entity_id,
            'balance': float(balance)
        })
    except Exception as e:
        from flask import current_app
        try:
            current_app.logger.warning(f'Failed to emit balance update: {e}')
        except Exception:
            pass

def clear_all_balance_cache():
    try:
        cache.delete('balances_summary_v1')
        cache.delete('suppliers_summary_v2')
        cache.delete('partners_summary_v2')
        cache.delete('customers_summary_v2')
    except Exception:
        pass

