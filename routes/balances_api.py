from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from models import Supplier, Partner, Customer
from extensions import cache, db

balances_api_bp = Blueprint('balances_api', __name__, url_prefix='/api/balances')

@balances_api_bp.route('/dashboard', methods=['GET'])
@login_required
def balances_dashboard():
    suppliers = Supplier.query.filter_by(is_archived=False).limit(10000).all()
    partners = Partner.query.filter_by(is_archived=False).limit(10000).all()
    customers = Customer.query.filter_by(is_archived=False).limit(10000).all()
    
    suppliers_total = sum(s.balance for s in suppliers)
    partners_total = sum(p.balance for p in partners)
    customers_total = sum(c.balance for c in customers)
    
    summary = {
        'suppliers': {
            'count': len(suppliers),
            'total_balance': suppliers_total,
            'positive': len([s for s in suppliers if s.balance > 0]),
            'negative': len([s for s in suppliers if s.balance < 0])
        },
        'partners': {
            'count': len(partners),
            'total_balance': partners_total,
            'positive': len([p for p in partners if p.balance > 0]),
            'negative': len([p for p in partners if p.balance < 0])
        },
        'customers': {
            'count': len(customers),
            'total_balance': customers_total,
            'positive': len([c for c in customers if c.balance > 0]),
            'negative': len([c for c in customers if c.balance < 0])
        }
    }
    
    top_suppliers = sorted([s for s in suppliers if s.balance > 0], key=lambda x: x.balance, reverse=True)[:10]
    top_customers = sorted([c for c in customers if c.balance < 0], key=lambda x: x.balance)[:10]
    
    return render_template('reports/balances_dashboard.html',
                         summary=summary,
                         top_suppliers=top_suppliers,
                         top_customers=top_customers)

@balances_api_bp.route('/supplier/<int:supplier_id>', methods=['GET'])
@login_required
def get_supplier_balance(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    return jsonify({
        'success': True,
        'entity_id': supplier.id,
        'entity_type': 'supplier',
        'name': supplier.name,
        'balance': supplier.balance,
        'balance_in_ils': supplier.balance_in_ils,
        'currency': supplier.currency,
        'opening_balance': float(supplier.opening_balance or 0),
        'total_paid': float(supplier.total_paid or 0),
        'net_balance': float(supplier.net_balance or 0)
    })

@balances_api_bp.route('/partner/<int:partner_id>', methods=['GET'])
@login_required
def get_partner_balance(partner_id):
    partner = Partner.query.get_or_404(partner_id)
    return jsonify({
        'success': True,
        'entity_id': partner.id,
        'entity_type': 'partner',
        'name': partner.name,
        'balance': partner.balance,
        'balance_in_ils': partner.balance_in_ils,
        'currency': partner.currency,
        'opening_balance': float(partner.opening_balance or 0),
        'share_percentage': float(partner.share_percentage or 0)
    })

@balances_api_bp.route('/customer/<int:customer_id>', methods=['GET'])
@login_required
def get_customer_balance(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return jsonify({
        'success': True,
        'entity_id': customer.id,
        'entity_type': 'customer',
        'name': customer.name,
        'balance': customer.balance,
        'currency': customer.currency,
        'opening_balance': float(customer.opening_balance or 0),
        'credit_limit': float(customer.credit_limit or 0)
    })

@balances_api_bp.route('/summary', methods=['GET'])
@login_required
def get_balances_summary():
    cache_key = 'balances_summary_v1'
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)
    
    suppliers = Supplier.query.filter_by(is_archived=False).limit(10000).all()
    partners = Partner.query.filter_by(is_archived=False).limit(10000).all()
    customers = Customer.query.filter_by(is_archived=False).limit(10000).all()
    
    suppliers_total = sum(s.balance for s in suppliers)
    partners_total = sum(p.balance for p in partners)
    customers_total = sum(c.balance for c in customers)
    
    summary = {
        'success': True,
        'timestamp': db.func.now(),
        'suppliers': {
            'count': len(suppliers),
            'total_balance': suppliers_total,
            'positive': len([s for s in suppliers if s.balance > 0]),
            'negative': len([s for s in suppliers if s.balance < 0])
        },
        'partners': {
            'count': len(partners),
            'total_balance': partners_total,
            'positive': len([p for p in partners if p.balance > 0]),
            'negative': len([p for p in partners if p.balance < 0])
        },
        'customers': {
            'count': len(customers),
            'total_balance': customers_total,
            'positive': len([c for c in customers if c.balance > 0]),
            'negative': len([c for c in customers if c.balance < 0])
        },
        'net_position': customers_total - suppliers_total - partners_total
    }
    
    cache.set(cache_key, summary, timeout=180)
    return jsonify(summary)

@balances_api_bp.route('/clear-cache', methods=['POST'])
@login_required
def clear_balance_cache():
    entity_type = request.json.get('entity_type')
    entity_id = request.json.get('entity_id')
    
    if entity_type and entity_id:
        cache_key = f'{entity_type}_balance_{entity_id}'
        cache.delete(cache_key)
    else:
        cache.delete('balances_summary_v1')
        cache.delete('suppliers_summary_v2')
        cache.delete('partners_summary_v2')
    
    return jsonify({'success': True, 'message': 'تم مسح الكاش'})

