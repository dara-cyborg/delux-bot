"""
Tenant-aware data storage layer using SQLite.
Manages tenant configuration, sessions, orders, and comments.
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import uuid

# SQLite database path
DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "tenant_data.db"


def _get_db() -> sqlite3.Connection:
    """Get database connection with row factory for dict-like access"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize SQLite database schema for multi-tenant support"""
    conn = _get_db()
    cursor = conn.cursor()

    # Tenants table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT
        )
    """)

    # Tenant Telegram configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_telegram_config (
            tenant_id TEXT PRIMARY KEY,
            telegram_enabled BOOLEAN NOT NULL DEFAULT 0,
            telegram_bot_token TEXT,
            telegram_chat_id TEXT,
            telegram_message_template TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE
        )
    """)

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            session_name TEXT,
            session_date TEXT NOT NULL,
            session_state TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT,
            PRIMARY KEY (tenant_id, session_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE
        )
    """)

    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            commenter TEXT NOT NULL,
            comment TEXT NOT NULL,
            comment_id TEXT,
            collected_at TEXT NOT NULL,
            printed_at TEXT,
            profile_url TEXT,
            order_date TEXT,
            source_host TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE,
            FOREIGN KEY (tenant_id, session_id) REFERENCES sessions(tenant_id, session_id)
                ON DELETE CASCADE
        )
    """)

    # Create indexes for common queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_tenant_session 
        ON orders(tenant_id, session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_tenant_date 
        ON orders(tenant_id, order_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_tenant 
        ON sessions(tenant_id, session_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_telegram_chat_id 
        ON tenant_telegram_config(telegram_chat_id)
    """)

    conn.commit()
    conn.close()


def get_or_create_tenant(tenant_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get or create a tenant"""
    conn = _get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Check if tenant exists
    cursor.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()

    if row:
        conn.close()
        return dict(row)

    # Create new tenant
    cursor.execute("""
        INSERT INTO tenants (tenant_id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?)
    """, (tenant_id, now, now, json.dumps(metadata or {})))
    conn.commit()

    cursor.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
    result = dict(cursor.fetchone())
    conn.close()
    return result


def save_tenant_telegram_config(
    tenant_id: str,
    enabled: bool,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    message_template: Optional[str] = None,
) -> Dict[str, Any]:
    """Save or update tenant Telegram configuration"""
    conn = _get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Ensure tenant exists
    get_or_create_tenant(tenant_id)

    # Check if config exists
    cursor.execute(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
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
        cursor.execute("""
            INSERT INTO tenant_telegram_config
            (tenant_id, telegram_enabled, telegram_bot_token,
             telegram_chat_id, telegram_message_template, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tenant_id, enabled, bot_token if enabled else None,
              chat_id if enabled else None, message_template if enabled else None,
              now, now))

    conn.commit()

    cursor.execute(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )
    result = dict(cursor.fetchone())
    conn.close()
    return result


def get_tenant_telegram_config(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant Telegram configuration"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM tenant_telegram_config WHERE tenant_id = ?",
        (tenant_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_tenant_by_chat_id(chat_id: str) -> Optional[Dict[str, Any]]:
    """
    Lookup tenant by Telegram chat ID.
    Used for webhook to identify which tenant sent a message.
    
    Returns:
        Dictionary with tenant_id and telegram config, or None if not found
    """
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT t.*, tc.* FROM tenants t
           INNER JOIN tenant_telegram_config tc ON t.tenant_id = tc.tenant_id
           WHERE tc.telegram_chat_id = ? AND tc.telegram_enabled = 1""",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "tenant_id": row["tenant_id"],
        "telegram_chat_id": row["telegram_chat_id"],
        "telegram_bot_token": row["telegram_bot_token"],
        "telegram_enabled": bool(row["telegram_enabled"]),
        "telegram_message_template": row["telegram_message_template"],
    }


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
    conn = _get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    order_id = str(uuid.uuid4())

    # Ensure tenant and session exist
    get_or_create_tenant(tenant_id)
    get_or_create_session(tenant_id, session_id, session_date=order_date or now.split("T")[0])

    cursor.execute("""
        INSERT INTO orders
        (order_id, tenant_id, session_id, commenter, comment, comment_id,
         collected_at, printed_at, profile_url, order_date, source_host,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, tenant_id, session_id, commenter, comment, comment_id,
          collected_at or now, now, profile_url, order_date or now.split("T")[0],
          source_host or "api", now, now))

    conn.commit()

    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    result = dict(cursor.fetchone())
    conn.close()
    return result


def get_or_create_session(
    tenant_id: str,
    session_id: str,
    session_name: Optional[str] = None,
    session_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Get or create a session for a tenant"""
    conn = _get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    session_date = session_date or now.split("T")[0]

    # Check if session exists
    cursor.execute(
        "SELECT * FROM sessions WHERE session_id = ? AND tenant_id = ?",
        (session_id, tenant_id)
    )
    row = cursor.fetchone()

    if row:
        conn.close()
        return dict(row)

    # Create new session
    cursor.execute("""
        INSERT INTO sessions
        (session_id, tenant_id, session_name, session_date, session_state,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, tenant_id, session_name or session_id, session_date,
          "active", now, now))

    conn.commit()

    cursor.execute(
        "SELECT * FROM sessions WHERE session_id = ? AND tenant_id = ?",
        (session_id, tenant_id)
    )
    result = dict(cursor.fetchone())
    conn.close()
    return result


def get_tenant_sessions(tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all sessions for a tenant"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.*, COUNT(o.order_id) as order_count
        FROM sessions s
        LEFT JOIN orders o
            ON s.tenant_id = o.tenant_id
            AND s.session_id = o.session_id
        WHERE s.tenant_id = ?
        GROUP BY s.session_id
        ORDER BY s.session_date DESC
        LIMIT ?
    """, (tenant_id, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_session_orders(
    tenant_id: str,
    session_id: str,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Get all orders for a session"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND session_id = ?
        ORDER BY collected_at DESC
        LIMIT ?
    """, (tenant_id, session_id, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_order(tenant_id: str, order_id: str) -> Optional[Dict[str, Any]]:
    """Get a single order"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND order_id = ?
    """, (tenant_id, order_id))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_order(
    tenant_id: str,
    order_id: str,
    comment: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update an order"""
    conn = _get_db()
    cursor = conn.cursor()

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
        conn.close()
        return get_order(tenant_id, order_id)

    updates.append("updated_at = ?")
    params.extend([now, tenant_id, order_id])

    cursor.execute(
        f"UPDATE orders SET {', '.join(updates)} WHERE tenant_id = ? AND order_id = ?",
        params
    )
    conn.commit()

    result = get_order(tenant_id, order_id)
    conn.close()
    return result


def get_tenant_orders_by_date(
    tenant_id: str,
    order_date: str,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Get orders for a tenant by date"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM orders
        WHERE tenant_id = ? AND order_date = ?
        ORDER BY collected_at DESC
        LIMIT ?
    """, (tenant_id, order_date, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
