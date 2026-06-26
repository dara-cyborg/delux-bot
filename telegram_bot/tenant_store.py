"""
Tenant-aware data storage layer.
Manages tenant configuration, sessions, orders, and comments.
Supports both SQLite (local development) and Postgres (production).
"""

import json
import secrets
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo
import uuid

from telegram_bot.database import get_db, init_database


def init_db():
    """Initialize database schema for multi-tenant support"""
    init_database()


def get_or_create_tenant(tenant_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get or create a tenant"""
    db = get_db()
    now = datetime.now().isoformat()

    # Check if tenant exists
    row = db.execute_one("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
    if row:
        return row

    # Create new tenant
    db.execute("""
        INSERT INTO tenants (tenant_id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?)
    """, (tenant_id, now, now, json.dumps(metadata or {})))

    return db.execute_one("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))



def save_tenant_telegram_config(
    tenant_id: str,
    enabled: bool,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    message_template: Optional[str] = None,
) -> Dict[str, Any]:
    """Save or update tenant Telegram configuration"""
    db = get_db()
    now = datetime.now().isoformat()

    # Ensure tenant exists
    get_or_create_tenant(tenant_id)

    # Check if config exists
    existing = db.execute_one(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )

    if existing:
        db.execute("""
            UPDATE tenant_telegram_config
            SET telegram_enabled = ?, telegram_bot_token = ?,
                telegram_chat_id = ?, telegram_message_template = ?,
                updated_at = ?
            WHERE tenant_id = ?
        """, (enabled, bot_token if enabled else None,
              chat_id if enabled else None,
              message_template if enabled else None,
              now, tenant_id))
    else:
        db.execute("""
            INSERT INTO tenant_telegram_config
            (tenant_id, telegram_enabled, telegram_bot_token,
             telegram_chat_id, telegram_message_template, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tenant_id, enabled, bot_token if enabled else None,
              chat_id if enabled else None, message_template if enabled else None,
              now, now))

    return db.execute_one(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )


def get_tenant_telegram_config(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant Telegram configuration"""
    db = get_db()
    return db.execute_one(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )


def get_tenant_by_chat_id(chat_id: str) -> Optional[Dict[str, Any]]:
    """
    Lookup tenant by Telegram chat ID.
    Used for webhook to identify which tenant sent a message.
    
    Returns:
        Dictionary with tenant_id and telegram config, or None if not found
    """
    db = get_db()
    chat_id = str(chat_id)
    row = db.execute_one(
        """SELECT t.tenant_id, tc.telegram_chat_id, tc.telegram_bot_token,
                  tc.telegram_enabled, tc.telegram_message_template
           FROM tenants t
           INNER JOIN tenant_telegram_config tc ON t.tenant_id = tc.tenant_id
           WHERE tc.telegram_chat_id = ? AND tc.telegram_enabled = 1""",
        (chat_id,)
    )
    return row


def save_order(
    tenant_id: str,
    session_id: str,
    commenter: str,
    comment: str,
    comment_id: Optional[str] = None,
    collected_at: Optional[str] = None,
    profile_url: Optional[str] = None,
    order_date: Optional[str] = None,
    source_host: Optional[str] = None,
) -> Dict[str, Any]:
    """Save an order for a tenant"""
    db = get_db()
    now = datetime.now().isoformat()
    order_id = str(uuid.uuid4())

    # Ensure tenant and session exist
    get_or_create_tenant(tenant_id)
    get_or_create_session(tenant_id, session_id, session_date=order_date or now.split("T")[0])

    db.execute("""
        INSERT INTO orders
        (order_id, tenant_id, session_id, commenter, comment, comment_id,
         collected_at, printed_at, profile_url, order_date, source_host,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, tenant_id, session_id, commenter, comment, comment_id,
          collected_at or now, now, profile_url, order_date or now.split("T")[0],
          source_host or "api", now, now))

    return db.execute_one("SELECT * FROM orders WHERE order_id = ?", (order_id,))


def _format_cambodia_session_name(session_date: str) -> str:
    """Format a session name using Cambodia local date."""
    try:
        date_obj = datetime.fromisoformat(session_date).date()
    except ValueError:
        date_obj = datetime.now(ZoneInfo("Asia/Phnom_Penh")).date()
    return date_obj.strftime("%d-%b-%Y")


def get_or_create_session(
    tenant_id: str,
    session_id: str,
    session_name: Optional[str] = None,
    session_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Get or create a session for a tenant"""
    db = get_db()
    now = datetime.now().isoformat()
    session_date = session_date or now.split("T")[0]

    # Check if session exists
    row = db.execute_one(
        "SELECT * FROM sessions WHERE session_id = ? AND tenant_id = ?",
        (session_id, tenant_id)
    )
    if row:
        return row

    # Create new session using a readable Cambodia date if no explicit name is provided
    session_name = session_name or _format_cambodia_session_name(session_date)

    db.execute("""
        INSERT INTO sessions
        (session_id, tenant_id, session_name, session_date, session_state,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, tenant_id, session_name, session_date,
          "active", now, now))

    return db.execute_one(
        "SELECT * FROM sessions WHERE session_id = ? AND tenant_id = ?",
        (session_id, tenant_id)
    )


def get_tenant_sessions(tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all sessions for a tenant"""
    db = get_db()
    return db.execute_all("""
        SELECT s.*, COALESCE(o.order_count, 0) AS order_count
        FROM sessions s
        LEFT JOIN (
            SELECT tenant_id, session_id, COUNT(order_id) AS order_count
            FROM orders
            WHERE tenant_id = ?
            GROUP BY tenant_id, session_id
        ) o
            ON s.tenant_id = o.tenant_id
            AND s.session_id = o.session_id
        WHERE s.tenant_id = ?
        ORDER BY s.session_date DESC
        LIMIT ?
    """, (tenant_id, tenant_id, limit))


def get_session_orders(
    tenant_id: str,
    session_id: str,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Get all orders for a session"""
    db = get_db()
    return db.execute_all("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND session_id = ?
        ORDER BY collected_at DESC
        LIMIT ?
    """, (tenant_id, session_id, limit))


def get_order(tenant_id: str, order_id: str) -> Optional[Dict[str, Any]]:
    """Get a single order"""
    db = get_db()
    return db.execute_one("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND order_id = ?
    """, (tenant_id, order_id))


def update_order(
    tenant_id: str,
    order_id: str,
    comment: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update an order"""
    db = get_db()
    now = datetime.now().isoformat()
    updates = []
    params = []

    if comment is not None:
        updates.append("comment = ?")
        params.append(comment)
    if profile_url is not None:
        updates.append("profile_url = ?")
        params.append(profile_url)

    if not updates:
        return get_order(tenant_id, order_id)

    updates.append("updated_at = ?")
    params.extend([now, tenant_id, order_id])

    db.execute(
        f"UPDATE orders SET {', '.join(updates)} WHERE tenant_id = ? AND order_id = ?",
        tuple(params)
    )

    return get_order(tenant_id, order_id)


def get_tenant_orders_by_date(
    tenant_id: str,
    order_date: str,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Get orders for a tenant by date"""
    db = get_db()
    return db.execute_all("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND order_date = ?
        ORDER BY collected_at DESC
        LIMIT ?
    """, (tenant_id, order_date, limit))


def get_or_create_tenant_webhook_secret(tenant_id: str) -> str:
    """
    Get existing webhook secret for tenant, or create and save a new one.
    Webhook secrets are used to validate incoming webhook requests.
    """
    db = get_db()
    
    # Check if secret already exists
    row = db.execute_one(
        "SELECT webhook_secret FROM tenant_webhook_secrets WHERE tenant_id = ?",
        (tenant_id,)
    )
    
    if row:
        return row['webhook_secret']
    
    # Generate new secret (32 bytes = 256 bits of entropy)
    new_secret = secrets.token_urlsafe(32)
    now = datetime.now().isoformat()
    
    db.execute("""
        INSERT INTO tenant_webhook_secrets
        (tenant_id, webhook_secret, created_at, updated_at)
        VALUES (?, ?, ?, ?)
    """, (tenant_id, new_secret, now, now))
    
    return new_secret


def get_tenant_webhook_secret(tenant_id: str) -> Optional[str]:
    """Get webhook secret for a tenant, or None if not found."""
    db = get_db()
    row = db.execute_one(
        "SELECT webhook_secret FROM tenant_webhook_secrets WHERE tenant_id = ?",
        (tenant_id,)
    )
    return row['webhook_secret'] if row else None


def validate_webhook_secret(tenant_id: str, secret: str) -> bool:
    """Validate a webhook secret for a tenant."""
    stored_secret = get_tenant_webhook_secret(tenant_id)
    if not stored_secret:
        return False
    return secrets.compare_digest(secret, stored_secret)
