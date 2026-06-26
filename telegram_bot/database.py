"""
Database abstraction layer for multi-backend support (SQLite and Postgres).

This module provides a unified interface for tenant-aware data storage,
automatically selecting Postgres when DATABASE_URL is set, falling back to SQLite.
"""

from __future__ import annotations

import os
import sqlite3
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import uuid

try:
    import psycopg
except ImportError:
    psycopg = None


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def init_schema(self) -> None:
        """Initialize database schema idempotently."""
        pass

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query and return result."""
        pass

    @abstractmethod
    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a query and return single row as dict."""
        pass

    @abstractmethod
    def execute_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return all rows as list of dicts."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend for local development."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db_dir()
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure_db_dir(self) -> None:
        """Ensure database directory exists."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def init_schema(self) -> None:
        """Initialize SQLite database schema for multi-tenant support."""
        conn = self._get_conn()
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

        # Tenant webhook secrets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_webhook_secrets (
                tenant_id TEXT PRIMARY KEY,
                webhook_secret TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
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

        # Unique index for enabled telegram chats (ensures no duplicate enabled chats)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_enabled_tenant_chat
            ON tenant_telegram_config (telegram_chat_id)
            WHERE telegram_enabled = 1
        """)

        conn.commit()

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor

    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a query and return single row as dict."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def execute_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return all rows as list of dicts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class PostgresBackend(DatabaseBackend):
    """Postgres database backend for production."""

    def __init__(self, connection_string: str):
        if psycopg is None:
            raise ImportError(
                "psycopg is required for Postgres support. "
                "Install it with: pip install psycopg[binary]"
            )
        self.connection_string = connection_string
        self._conn: Optional[Any] = None

    def _get_conn(self) -> Any:
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.connection_string)
        return self._conn

    @staticmethod
    def _convert_placeholders(query: str) -> str:
        """Convert SQLite ? placeholders to Postgres %s placeholders."""
        return query.replace('?', '%s')

    def init_schema(self) -> None:
        """Initialize Postgres database schema for multi-tenant support."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Tenants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata JSONB
            )
        """)

        # Tenant Telegram configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_telegram_config (
                tenant_id TEXT PRIMARY KEY,
                telegram_enabled BOOLEAN NOT NULL DEFAULT FALSE,
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
                metadata JSONB,
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
                metadata JSONB,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (tenant_id, session_id) REFERENCES sessions(tenant_id, session_id)
                    ON DELETE CASCADE
            )
        """)

        # Tenant webhook secrets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_webhook_secrets (
                tenant_id TEXT PRIMARY KEY,
                webhook_secret TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
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

        # Unique index for enabled telegram chats (ensures no duplicate enabled chats)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_enabled_tenant_chat
            ON tenant_telegram_config (telegram_chat_id)
            WHERE telegram_enabled = true
        """)

        conn.commit()

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(self._convert_placeholders(query), params)
        conn.commit()
        return cursor

    def _dict_from_cursor_row(self, cursor: Any, row: Any) -> Optional[Dict[str, Any]]:
        """Convert a cursor row to a dictionary safely for psycopg cursors."""
        if row is None:
            return None
        try:
            return dict(row)
        except (TypeError, ValueError):
            column_names = [column[0] for column in cursor.description or []]
            return dict(zip(column_names, row))

    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a query and return single row as dict."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(self._convert_placeholders(query), params)
        row = cursor.fetchone()
        return self._dict_from_cursor_row(cursor, row)

    def execute_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return all rows as list of dicts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(self._convert_placeholders(query), params)
        rows = cursor.fetchall()
        return [self._dict_from_cursor_row(cursor, row) for row in rows if row is not None]

    def close(self) -> None:
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


def get_database_backend() -> DatabaseBackend:
    """
    Get the appropriate database backend.
    Uses Postgres if DATABASE_URL is set, otherwise SQLite for local development.
    """
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        return PostgresBackend(database_url)
    else:
        db_dir = Path(__file__).parent.parent / "data"
        db_path = str(db_dir / "tenant_data.db")
        return SQLiteBackend(db_path)


# Global database instance
_db_backend: Optional[DatabaseBackend] = None


def init_database() -> None:
    """Initialize the database backend and schema."""
    global _db_backend
    _db_backend = get_database_backend()
    _db_backend.init_schema()


def get_db() -> DatabaseBackend:
    """Get the global database backend instance."""
    global _db_backend
    if _db_backend is None:
        init_database()
    return _db_backend


def close_database() -> None:
    """Close database connection."""
    global _db_backend
    if _db_backend:
        _db_backend.close()
        _db_backend = None
