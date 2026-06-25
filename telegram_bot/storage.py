"""
Storage abstraction for Telegram Bot data access.

This module allows the Telegram Bot package to remain independent of the
backend package by registering external tenant-aware storage callbacks.
If no storage provider is registered, the bot falls back to a local in-memory
order storage implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from telegram_bot.local_orders import order_history_by_commenter

SessionsCallback = Callable[[str, int, int], List[Dict[str, Any]]]
SessionOrdersCallback = Callable[[str, str, int], List[Dict[str, Any]]]
OrdersByDateCallback = Callable[[str, str, int], List[Dict[str, Any]]]
TenantLookupCallback = Callable[[int | str], Optional[str]]


_sessions_callback: Optional[SessionsCallback] = None
_session_orders_callback: Optional[SessionOrdersCallback] = None
_orders_by_date_callback: Optional[OrdersByDateCallback] = None
_tenant_lookup_callback: Optional[TenantLookupCallback] = None


def register_storage_provider(
    get_sessions_paginated: Optional[SessionsCallback] = None,
    get_session_orders: Optional[SessionOrdersCallback] = None,
    get_tenant_orders_by_date: Optional[OrdersByDateCallback] = None,
    get_tenant_by_chat_id: Optional[TenantLookupCallback] = None,
) -> None:
    """Register tenant-aware storage callbacks for the Telegram Bot."""
    global _sessions_callback, _session_orders_callback, _orders_by_date_callback, _tenant_lookup_callback
    _sessions_callback = get_sessions_paginated
    _session_orders_callback = get_session_orders
    _orders_by_date_callback = get_tenant_orders_by_date
    _tenant_lookup_callback = get_tenant_by_chat_id


def reset_storage_provider() -> None:
    """Clear any registered tenant-aware storage callbacks."""
    global _sessions_callback, _session_orders_callback, _orders_by_date_callback, _tenant_lookup_callback
    _sessions_callback = None
    _session_orders_callback = None
    _orders_by_date_callback = None
    _tenant_lookup_callback = None


def _default_get_sessions_paginated(
    tenant_id: str,
    page: int,
    page_size: int = 10,
) -> List[Dict[str, Any]]:
    if page != 0:
        return []

    total_orders = sum(entry.get("print_count", 0) for entry in order_history_by_commenter.values())
    total_customers = len(order_history_by_commenter)

    return [
        {
            "session_id": "current",
            "session_name": "Live Session",
            "session_date": None,
            "order_count": total_orders,
            "customer_count": total_customers,
            "session_state": "active",
        }
    ]


def _default_get_session_orders(
    tenant_id: str,
    session_id: str,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    if session_id != "current":
        return []

    orders = []
    for entry in order_history_by_commenter.values():
        commenter = entry.get("commenter", "Unknown")
        for comment in entry.get("comments", []):
            orders.append({
                "order_id": None,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "commenter": commenter,
                "comment": comment.get("comment", ""),
                "collected_at": comment.get("collected_at", ""),
                "comment_id": comment.get("comment_id"),
                "printed_at": comment.get("printed_at"),
                "profile_url": comment.get("profile_url"),
            })

    orders.sort(key=lambda order: order.get("collected_at", ""), reverse=True)
    return orders[:limit]


def _default_get_tenant_orders_by_date(
    tenant_id: str,
    order_date: str,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    orders = []
    for entry in order_history_by_commenter.values():
        commenter = entry.get("commenter", "Unknown")
        for comment in entry.get("comments", []):
            collected_at = comment.get("collected_at", "")
            if collected_at.split(" ")[0] == order_date:
                orders.append({
                    "order_id": None,
                    "tenant_id": tenant_id,
                    "session_id": "current",
                    "commenter": commenter,
                    "comment": comment.get("comment", ""),
                    "collected_at": collected_at,
                    "comment_id": comment.get("comment_id"),
                    "printed_at": comment.get("printed_at"),
                    "profile_url": comment.get("profile_url"),
                })

    orders.sort(key=lambda order: order.get("collected_at", ""), reverse=True)
    return orders[:limit]


def get_sessions_paginated(
    tenant_id: str,
    page: int,
    page_size: int = 10,
) -> List[Dict[str, Any]]:
    if _sessions_callback:
        return _sessions_callback(tenant_id, page, page_size)
    return _default_get_sessions_paginated(tenant_id, page, page_size)


def get_session_orders(
    tenant_id: str,
    session_id: str,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    if _session_orders_callback:
        return _session_orders_callback(tenant_id, session_id, limit)
    return _default_get_session_orders(tenant_id, session_id, limit)


def get_tenant_orders_by_date(
    tenant_id: str,
    order_date: str,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    if _orders_by_date_callback:
        return _orders_by_date_callback(tenant_id, order_date, limit)
    return _default_get_tenant_orders_by_date(tenant_id, order_date, limit)


def get_tenant_by_chat_id(chat_id: int | str) -> Optional[str]:
    """
    Look up tenant_id by Telegram chat_id.
    
    This is used by the webhook to resolve which tenant owns a Telegram chat.
    The backend should implement this callback to query the tenant-chat mapping table.
    
    Args:
        chat_id: Telegram chat ID (can be int or str)
    
    Returns:
        tenant_id if found, None otherwise
    """
    if _tenant_lookup_callback:
        return _tenant_lookup_callback(chat_id)
    # Default: no tenant found in local mode
    return None
