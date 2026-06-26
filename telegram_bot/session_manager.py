"""Telegram session manager for command and callback handlers."""

from typing import List, Dict, Optional

from telegram_bot.local_orders import order_history_by_commenter
from telegram_bot.storage import (
    get_sessions_paginated as storage_get_sessions_paginated,
    get_session_orders as storage_get_session_orders,
    get_tenant_orders_by_date as storage_get_tenant_orders_by_date,
)


def _get_live_session_summary() -> Dict[str, Optional[int]]:
    total_orders = sum(len(entry.get('comments', [])) for entry in order_history_by_commenter.values())
    total_customers = len(order_history_by_commenter)
    return {
        'session_name': 'Live Session',
        'order_count': total_orders,
        'customer_count': total_customers,
        'start_time': None,
    }


def get_sessions_paginated(tenant_id: str, page: int, page_size: int = 10) -> List[Dict[str, str]]:
    """Return paginated sessions for a tenant."""
    try:
        # Query tenant database. The storage callback owns pagination so that
        # database-backed providers can use LIMIT/OFFSET-style access.
        sessions = storage_get_sessions_paginated(tenant_id, page, page_size=page_size)

        # Calculate customer count for each session
        results = []
        for s in sessions:
            session_id = s['session_id']
            orders_list = storage_get_session_orders(tenant_id, session_id, limit=1000)
            customers = set(o['commenter'] for o in orders_list)
            
            results.append({
                'session_id': session_id,
                'session_name': s['session_name'] or session_id,
                'session_date': s['session_date'],
                'order_count': s.get('order_count', 0),
                'customer_count': len(customers),
                'session_state': s.get('session_state', 'active'),
            })
        
        return results
    except Exception:
        if page != 0:
            return []
        summary = _get_live_session_summary()
        return [{
            'session_id': 'current',
            'session_name': summary['session_name'],
            'session_date': None,
            'order_count': summary['order_count'],
            'customer_count': summary['customer_count'],
            'session_state': 'active',
        }]


def get_session_summary(tenant_id: str, session_id: str) -> Dict[str, str]:
    """Return session summary."""
    try:
        # Query tenant database
        orders_list = storage_get_session_orders(tenant_id, session_id, limit=1000)
        
        # Get unique customers
        customers = set(o['commenter'] for o in orders_list)
        
        return {
            'session_id': session_id,
            'session_name': session_id,
            'order_count': len(orders_list),
            'customer_count': len(customers),
            'session_state': 'active',
        }
    except Exception:
        if session_id != 'current':
            return {
                'session_name': 'Unknown',
                'order_count': 0,
                'customer_count': 0,
                'start_time': None,
            }
        return _get_live_session_summary()


def get_customers_for_session(tenant_id: str, session_id: str) -> List[Dict[str, str]]:
    """Return customers for a session."""
    try:
        # Query tenant database
        orders_list = storage_get_session_orders(tenant_id, session_id, limit=1000)
        
        # Group by commenter (customer)
        customer_orders: Dict[str, List] = {}
        for order in orders_list:
            name = order['commenter']
            if name not in customer_orders:
                customer_orders[name] = []
            customer_orders[name].append(order)
        
        # Build customer list with stats
        customers = [
            {
                'name': name,
                'order_count': len(order_list),
                'last_comment': order_list[-1].get('comment', '') if order_list else '',
                'collected_at': order_list[-1].get('collected_at', '') if order_list else '',
            }
            for name, order_list in customer_orders.items()
        ]
        
        # Sort by order count (descending), then by name (ascending)
        customers.sort(key=lambda item: (-item['order_count'], item['name'].lower()))
        return customers
    except Exception:
        if session_id != 'current':
            return []
        
        customers = []
        for entry in order_history_by_commenter.values():
            customers.append({
                'name': entry.get('commenter', 'Unknown'),
                'order_count': int(entry.get('print_count', 0)),
                'last_comment': entry.get('comments', [])[-1].get('comment', '') if entry.get('comments') else '',
            })
        
        customers.sort(key=lambda item: (-item['order_count'], item['name'].lower()))
        return customers


def get_orders_for_customer(tenant_id: str, session_id: str, customer_name: str) -> List[Dict[str, str]]:
    """Return orders for a single customer in a session."""
    try:
        # Query tenant database
        orders_list = storage_get_session_orders(tenant_id, session_id, limit=1000)
        
        # Filter by commenter
        customer_orders = [
            o for o in orders_list 
            if o['commenter'].lower() == customer_name.lower()
        ]
        
        return [
            {
                'order_id': o['order_id'],
                'commenter': o['commenter'],
                'comment': o['comment'],
                'collected_at': o['collected_at'],
                'comment_id': o['comment_id'],
                'printed_at': o['printed_at'],
                'profile_url': o['profile_url'],
            }
            for o in customer_orders
        ]
    except Exception:
        if session_id != 'current' or not customer_name:
            return []
        
        key = customer_name.strip().lower()
        entry = order_history_by_commenter.get(key)
        if not entry:
            return []
        
        return [
            {
                'comment': comment.get('comment', ''),
                'collected_at': comment.get('collected_at', ''),
                'comment_id': comment.get('comment_id', ''),
                'printed_at': comment.get('printed_at', ''),
            }
            for comment in entry.get('comments', [])
        ]
